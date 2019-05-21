import math
import os


class ServerConfig:
    def __init__(self, h_thres, l_thres, max_obj_size, tracker_length,
                 boundary, intersection_threshold):
        self.high_threshold = h_thres
        self.low_threshold = l_thres
        self.max_object_size = max_obj_size
        self.tracker_length = tracker_length
        self.boundary = boundary
        self.intersection_threshold = intersection_threshold


class Region:
    def __init__(self, fid, x, y, w, h, conf, label, resolution,
                 origin="generic"):
        self.fid = fid
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.conf = conf
        self.label = label
        self.resolution = resolution
        self.origin = origin

    def to_str(self):
        string_rep = (f"{self.fid}, {self.x:0.3f}, {self.y:0.3f}, "
                      f"{self.w:0.3f}, {self.h:0.3f}, {self.conf:0.3f}, "
                      f"{self.resolution:0.3f}, {self.origin}")
        return string_rep

    def is_same(self, region_to_check, threshold=0.5):
        # If the fids or labels are different
        # then not the same
        if (self.fid != region_to_check.fid or
                self.label != region_to_check.label):
            return False

        # If the intersection to union area
        # ratio is greater than the threshold
        # then the regions are the same
        if calc_iou(self, region_to_check) > threshold:
            return True
        else:
            return False

    def copy(self):
        return Region(self.fid, self.x, self.y, self.w, self.h, self.conf,
                      self.label, self.resolution, self.origin)


class Results:
    def __init__(self):
        self.regions = []

    def results_len(self):
        return len(self.regions)

    def is_dup(self, result_to_add, threshold=0.5):
        for existing_result in self.regions:
            if existing_result.is_same(result_to_add, threshold):
                return existing_result
        return None

    def combine_results(self, additional_results, threshold=0.5):
        for result_to_add in additional_results.regions:
            dup_region = self.is_dup(result_to_add, threshold)
            if not dup_region:
                self.regions.append(result_to_add)
                self.regions.sort(key=lambda x: x.fid)
            else:
                # Update confidence to the max confidence that we see
                dup_region.conf = max(result_to_add.conf, dup_region.conf)
                # Replace the origin iff a high resolution result is
                # being added and the dup_region was a low resolution result
                if ("high" not in dup_region.origin and
                        "high" in result_to_add.origin):
                    dup_region.origin = result_to_add.origin

    def add_single_result(self, result_to_add, threshold=0.5):
        temp_results = Results()
        temp_results.regions = [result_to_add]
        self.combine_results(temp_results, threshold)

    def remove(self, region_to_remove):
        self.regions.remove(region_to_remove)

    def fill_gaps(self, number_of_frames):
        results_to_add = Results()
        max_resolution = max([e.resolution for e in self.regions])
        fids_in_results = [e.fid for e in self.regions]
        for i in range(number_of_frames):
            if i not in fids_in_results:
                results_to_add.regions.append(Region(i, 0, 0, 0, 0,
                                                     0.1, "no obj",
                                                     max_resolution))
        self.combine_results(results_to_add)


def read_results_txt_dict(fname):
    """Return a dictionary with fid mapped to
       and array that contains all SingleResult objects
       from that particular frame"""
    results_dict = {}

    with open(fname, "r") as f:
        lines = f.readlines()
        f.close()

    for line in lines:
        line = line.split(",")
        fid = int(line[0])
        x, y, w, h = [float(e) for e in line[1:5]]
        conf = float(line[6])
        label = line[5]
        resolution = float(line[7])
        origin = "generic"
        if len(line) > 8:
            origin = line[8]
        single_result = Region(fid, x, y, w, h, conf, label,
                               resolution, origin)

        if fid not in results_dict:
            results_dict[fid] = []

        if label != "no obj":
            results_dict[fid].append(single_result)

    return results_dict


def read_results_dict(fname, fmat="csv"):
    # TODO: Need to implement a CSV function
    if fmat == "txt":
        return read_results_txt_dict(fname)


def write_results_txt(results, fname):
    results_file = open(fname, "w")
    for result in results.regions:
        # prepare the string to write
        str_to_write = (f"{result.fid},{result.x},{result.y},"
                        f"{result.w},{result.h},"
                        f"{result.label},{result.conf},"
                        f"{result.resolution},{result.origin}\n")
        results_file.write(str_to_write)
    results_file.close()


def write_results(results, fname, fmat="csv"):
    if fmat == "txt":
        write_results_txt(results, fname)


def calc_intersection_area(a, b):
    to = max(a.y, b.y)
    le = max(a.x, b.x)
    bo = min(a.y + a.h, b.y + b.h)
    ri = min(a.x + a.w, b.x + b.w)

    w = max(0, ri - le)
    h = max(0, bo - to)

    return w * h


def calc_area(a):
    w = max(0, a.w)
    h = max(0, a.h)

    return w * h


def calc_iou(a, b):
    intersection_area = calc_intersection_area(a, b)
    union_area = calc_area(a) + calc_area(b) - intersection_area
    return intersection_area / union_area


def get_interval_area(width, all_yes):
    area = 0
    for y1, y2 in all_yes:
        area += (y2 - y1) * width
    return area


def insert_range_y(all_yes, y1, y2):
    ranges_length = len(all_yes)
    idx = 0
    while idx < ranges_length:
        if not (y1 > all_yes[idx][1] or all_yes[idx][0] > y2):
            # Overlapping
            y1 = min(y1, all_yes[idx][0])
            y2 = max(y2, all_yes[idx][1])
            del all_yes[idx]
            ranges_length = len(all_yes)
        else:
            idx += 1

    all_yes.append((y1, y2))


def get_y_ranges(regions, j, x1, x2):
    all_yes = []
    while j < len(regions):
        if (x1 < (regions[j].x + regions[j].w) and
                x2 > regions[j].x):
            y1 = regions[j].y
            y2 = regions[j].y + regions[j].h
            insert_range_y(all_yes, y1, y2)
        j += 1
    return all_yes


def compute_area_of_frame(regions):
    regions.sort(key=lambda r: r.x + r.w)

    all_xes = []
    for r in regions:
        all_xes.append(r.x)
        all_xes.append(r.x + r.w)
    all_xes.sort()

    area = 0
    j = 0
    for i in range(len(all_xes) - 1):
        x1 = all_xes[i]
        x2 = all_xes[i + 1]

        if x1 < x2:
            while (regions[j].x + regions[j].w) < x1:
                j += 1
            all_yes = get_y_ranges(regions, j, x1, x2)
            area += get_interval_area(x2 - x1, all_yes)

    return area


def compute_area_of_regions(results):
    if len(results.regions) == 0:
        return 0

    min_frame = min([r.fid for r in results.regions])
    max_frame = max([r.fid for r in results.regions])

    total_area = 0
    for fid in range(min_frame, max_frame + 1):
        regions_for_frame = [r for r in results.regions if r.fid == fid]
        total_area += compute_area_of_frame(regions_for_frame)

    return total_area


def evaluate(results, gt_dict, high_threshold, iou_threshold=0.5):
    gt_results = Results()
    for k, v in gt_dict.items():
        for single_result in v:
            if single_result.conf < high_threshold:
                continue
            gt_results.add_single_result(single_result)

    # Save regions count because the regions that match
    # will be removed from the gt_regions to ensure better
    # search speed
    gt_regions_count = gt_results.results_len()

    fp = 0.0
    tp = 0.0
    fn = 0.0
    for a in results.regions:
        # Make sure that the region has a high confidence
        if a.conf < high_threshold:
            continue

        # Find match in gt_results
        matching_region = None
        for b in gt_results.regions:
            if a.is_same(b, iou_threshold):
                tp += 1.0
                matching_region = b
                break

        if matching_region:
            # Remove region from ground truth if
            # it has already matched with a region in results
            gt_results.remove(matching_region)
        else:
            fp += 1.0

    fn = gt_regions_count - tp

    precision = tp / (fp + tp)
    recall = tp / (fn + tp)
    f1 = 2.0 * precision * recall / (precision + recall)

    if math.isnan(f1):
        f1 = 0.0

    return f1, (tp, fp, fn)


def write_stats_txt(fname, vid_name, bsize, config, f1, stats, bw):
    header_str = ("video-name,batch-size,low-threshold,high-threshold,"
                  "tracker-length,TP,FP,FN,F1,"
                  "low-bandwidth,high-bandwidth,total-bandwidth")
    results_str = (f"{vid_name},{bsize},{config.low_threshold},"
                   f"{config.high_threshold},{config.tracker_length},"
                   f"{stats[0]},{stats[1]},{stats[2]},"
                   f"{f1},{bw[0]},{bw[1]},{bw[0] + bw[1]}")

    if not os.path.isfile(fname):
        str_to_write = f"{header_str}\n{results_str}\n"
    else:
        str_to_write = f"{results_str}\n"

    with open(fname, "a") as f:
        f.write(str_to_write)


def write_stats(fname, vid_name, bsize, config, f1, stats, bw, fmat="csv"):
    if fmat == "txt":
        write_stats_txt(fname, vid_name, bsize, config, f1, stats, bw)
