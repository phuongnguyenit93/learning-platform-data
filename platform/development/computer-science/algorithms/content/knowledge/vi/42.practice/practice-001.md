# Phân loại bài toán trước khi chọn kỹ thuật

## 1. Vì sao phải phân loại trước?

Một đề thuật toán thường có nhiều cách giải, nhưng không phải cách nào cũng phù hợp với dữ liệu, thao tác và giới hạn của đề. Chọn kỹ thuật chỉ từ một từ khóa rất dễ sai: thấy “mảng” thì dùng two pointers, thấy “đường đi ngắn nhất” thì dùng BFS, thấy “tối ưu” thì dùng greedy. Cùng một hình dạng dữ liệu có thể đòi hỏi cấu trúc hoàn toàn khác nhau.

Ví dụ:

- Mảng tĩnh, nhiều truy vấn tổng đoạn: prefix sums.
- Mảng có point update xen kẽ range sum: Fenwick Tree hoặc Segment Tree.
- Range minimum tĩnh: Sparse Table.
- Range minimum có point assignment: Segment Tree.
- Shortest path không trọng số: BFS.
- Shortest path có trọng số không âm: Dijkstra.
- Shortest path có cạnh âm: Bellman–Ford hoặc khai thác cấu trúc đặc biệt.

**Phân loại bài toán** là quá trình chuyển đề thành một mô hình rõ ràng, sau đó chọn kỹ thuật thỏa hợp đồng và constraints. Trước khi code, cần xác định hình dạng dữ liệu, workload, thao tác, mục tiêu, ràng buộc, online/offline và các tính chất toán học.

Kỹ thuật tốt là kỹ thuật đúng, đủ nhanh, nằm trong giới hạn bộ nhớ, có thể chứng minh và dễ kiểm thử. Không nhất thiết phải chọn kỹ thuật phức tạp nhất.

## 2. Viết lại đề thành hợp đồng

Trước tiên hãy diễn đạt đề bằng các câu hỏi cụ thể:

~~~text
INPUT
- Dữ liệu có dạng gì?
- Kích thước và miền giá trị?
- Có bao nhiêu query/update?
- Các thao tác đến theo thứ tự nào?

OUTPUT
- Cần trả existence, count, min/max hay optimum?
- Có cần in vị trí, đường đi hoặc phương án cụ thể?
- Có cần trả lời sau từng query không?

CONSTRAINTS
- n, m, q tối đa?
- Thời gian và bộ nhớ?
- Giá trị âm, duplicate, cực trị có thể xuất hiện?
~~~

### Tách câu chuyện khỏi cấu trúc

- Thành phố và đường nối → graph.
- Số lượt mua theo ngày → sequence hoặc frequency table.
- Thời gian bắt đầu/kết thúc → intervals/events.
- Tìm chuỗi con → string matching.
- Chọn dự án trong ngân sách → optimization/knapsack.
- Nối các phần tử thành nhóm → connectivity/DSU.

Khi trừu tượng hóa, vẫn phải giữ các thuộc tính làm thay đổi tính đúng: graph có hướng hay vô hướng, trọng số có âm không, interval đóng hay nửa mở, được chọn lặp không, update là SET hay ADD.

Ví dụ đề cho n=5 trong sample không có nghĩa n luôn nhỏ. Hãy đọc constraints chính thức trước khi chốt độ phức tạp.

## 3. Trục thứ nhất: hình dạng dữ liệu

| Hình dạng | Dấu hiệu | Cấu trúc/kỹ thuật thường gặp |
| --- | --- | --- |
| Sequence/array | Dãy theo chỉ số, đoạn con | Prefix sum, two pointers, BIT, Segment Tree |
| String | Ký tự, prefix/suffix, pattern | KMP, Z, trie, suffix structures |
| Graph | Đỉnh, cạnh, đường đi | BFS, DFS, Dijkstra, DSU, topo sort |
| Tree | Cha-con, subtree | DFS, LCA, tree DP |
| Grid | Ô hàng/cột, lân cận | Flood fill, BFS/DFS, grid DP |
| Intervals/events | Khoảng thời gian, endpoint | Sweep line, sorting |
| Set/multiset | Thành viên, tần suất, rank | HashSet, TreeMap, BIT tần suất |
| Matrix | Hai chiều | 2D prefix sum, DP |
| State space | Trạng thái và chuyển trạng thái | BFS, shortest path, DP |
| Geometry | Điểm, đoạn thẳng, giao nhau | Orientation, sweep line, convex hull |

Hình dạng chỉ là bước đầu. Một bài graph có thể hỏi reachability, shortest path, số thành phần hoặc số đường đi; mỗi mục tiêu có kỹ thuật khác nhau. Một bài array không tự động phù hợp two pointers nếu thiếu tính đơn điệu cần thiết.

## 4. Trục thứ hai: workload và vòng đời dữ liệu

| Workload | Ý nghĩa | Ứng viên |
| --- | --- | --- |
| Static | Không có cập nhật | Prefix sum, Sparse Table |
| Point update | Sửa một vị trí | Fenwick, Segment Tree |
| Range update | Sửa cả đoạn | Difference array, lazy Segment Tree, biến thể BIT |
| Insert-only | Chỉ thêm phần tử/cạnh | DSU trong một số bài |
| Fully dynamic | Có thêm và xóa | Cấu trúc động chuyên biệt hoặc offline rollback |
| Streaming | Dữ liệu đến liên tục | Online aggregation, bounded queue, window |
| Batch/offline | Biết trước nhiều query | Sort query, sweep line, Mo, coordinate compression |

### Static khác dynamic

Với mảng tĩnh:

~~~text
prefix[0] = 0
prefix[i+1] = prefix[i] + a[i]
sum(L,R) = prefix[R+1] - prefix[L]
~~~

Build O(n), mỗi range sum O(1). Nếu một phần tử thay đổi, nhiều prefix phía sau có thể đổi. Với point update + range sum, Fenwick thường hợp lý hơn; với range assign, min/max hoặc nhiều loại lazy operation, Segment Tree có thể tổng quát hơn.

### Insert-only khác fully dynamic

DSU hỗ trợ hợp nhất thành phần khi thêm cạnh. Nó không tự xử lý xóa một cạnh tùy ý. Bài có add/remove và connectivity query có thể cần offline dynamic connectivity với segment tree trên thời gian và rollback DSU, hoặc một cấu trúc chuyên biệt.

## 5. Trục thứ ba: thao tác chính xác

Liệt kê các operation trước khi chọn cấu trúc:

~~~text
SET(i, x)               // thay a[i] bằng x
ADD(i, delta)           // cộng delta vào a[i]
ADD_RANGE(L, R, delta)  // cộng vào cả đoạn
ASSIGN_RANGE(L, R, x)   // gán cả đoạn
PREFIX(end)
SUM(L, R)
MIN(L, R)
FIND_FIRST(predicate)
UNION(x, y)
SHORTEST_PATH(s, t)
~~~

`SET(i,x)` khác `ADD(i,x)`. Nếu BIT hỗ trợ point add nhưng đề yêu cầu point set, phải lưu giá trị hiện tại và cập nhật `delta = newValue - oldValue`.

| Update | Query | Cấu trúc ứng viên |
| --- | --- | --- |
| Không có | Range sum | Prefix sums |
| Point add/set | Prefix/range sum | Fenwick hoặc Segment Tree |
| Range add | Point get | Difference array + BIT |
| Range add | Range sum | Hai BIT hoặc lazy Segment Tree |
| Point set | Range min/max | Segment Tree |
| Không có | Range min/max | Sparse Table |
| Add edge | Connectivity | DSU |
| Static graph | Reachability | BFS/DFS |
| Interval events | Max overlap | Sweep line |
| Insert/delete key, hỏi rank | Order-statistics tree hoặc BIT sau nén |

Cấu trúc phải hỗ trợ **tất cả** operations. BIT tổng cơ bản không hỗ trợ mọi range minimum hay range assignment chỉ vì đề có “query đoạn”.

## 6. Trục thứ tư: mục tiêu đầu ra

Phân biệt rõ:

- **Existence:** có phương án không?
- **Count:** có bao nhiêu phương án?
- **Min/Max:** giá trị nhỏ nhất/lớn nhất?
- **Optimization:** tìm giá trị tối ưu?
- **Witness/construction:** phải in ra phương án đạt tối ưu?
- **Reachability:** có đường đi?
- **Shortest/longest path:** tối ưu theo trọng số hay số cạnh?
- **Ordering/rank:** thứ hạng hoặc phần tử thứ k?
- **Matching:** ghép cặp?
- **Simulation:** trạng thái sau chuỗi sự kiện?

Đếm số cách không giống tìm một cách bất kỳ. Tìm giá trị tối ưu cũng không giống in ra witness. Nếu cần đường đi hoặc tập phần tử, có thể phải lưu parent, decision hoặc thông tin tái dựng.

## 7. Trục thứ năm: constraints và complexity

Ràng buộc quyết định giải pháp có khả thi không.

| Độ phức tạp | Tăng trưởng khi n≈200.000 |
| --- | --- |
| O(1) | Không phụ thuộc n |
| O(log n) | Khoảng 18 bước |
| O(n) | Khoảng 200 nghìn bước |
| O(n log n) | Vài triệu đơn vị |
| O(n²) | Khoảng 40 tỷ cặp |
| O(2^n) | Chỉ phù hợp n nhỏ |
| O(n!) | Chỉ phù hợp kích thước rất nhỏ hoặc pruning mạnh |

Đây là ước lượng quy mô, không phải dự báo thời gian chính xác. Hằng số, cache, I/O và ngôn ngữ triển khai đều quan trọng.

### Tính tổng số thao tác

Nếu có q query, mỗi query quét n phần tử thì tổng O(nq). Với n=q=200.000, cách này không khả thi. Nếu q rất nhỏ, scan trực tiếp có thể tốt hơn tiền xử lý O(n). Phải so tổng chi phí.

### Bộ nhớ và kiểu số

Một mảng `long[n]` cần khoảng 8n byte payload; hai mảng và metadata sẽ nhiều hơn. DP O(nm) có thể vượt RAM dù thời gian tính toán có vẻ chấp nhận được.

Hỏi thêm: giá trị có âm không, tổng có vượt `int` không, tích có thể overflow `long` không, sentinel có trùng giá trị hợp lệ không? Chọn kiểu và cận số học dựa trên constraints.

## 8. Trục thứ sáu: online, offline và streaming

**Online:** query hiện tại phải được trả lời trước khi biết query tương lai. Ví dụ ADD và SUM xen kẽ; Fenwick hoặc Segment Tree thường phù hợp.

**Offline:** biết trước toàn bộ query; có thể đổi thứ tự xử lý nếu lưu ID và xuất đáp án đúng thứ tự. Ví dụ sort query theo đầu phải, quét mảng và dùng BIT cho distinct range queries.

**Streaming:** dữ liệu đến liên tục và có thể không lưu hết. Cần biết cửa sổ, retention, độ trễ, khả năng spill và có chấp nhận xấp xỉ không.

Câu hỏi quyết định:

~~~text
Can I reorder operations without changing the required answers?
~~~

Nếu không, phải giữ thứ tự hoặc dùng cấu trúc online. Nếu có, sort offline, sweep line hoặc Mo có thể phù hợp. Mỗi query offline vẫn cần ID để khôi phục thứ tự đầu ra.

## 9. Trục thứ bảy: tính chất toán học

### Monotonicity

Binary search on answer cần predicate đơn điệu: khi ngưỡng tăng, trạng thái đúng/sai chỉ chuyển theo một hướng. Phải chứng minh, không suy ra từ một vài ví dụ.

### Non-negativity

Two pointers cho nhiều bài toán tổng cửa sổ dựa vào tính chất mở rộng cửa sổ không làm tổng giảm. Số âm có thể phá vỡ lập luận này. Dijkstra cần trọng số không âm; cạnh âm làm precondition không còn đúng.

### Associativity và identity

Tổng có phép gộp kết hợp và identity 0. Segment Tree có thể lưu các phép gộp kết hợp. Nhưng range minimum không thể lấy bằng phép trừ hai prefix minimum vì phép min không có nghịch đảo tương ứng.

### Invertibility

Prefix sum lấy range sum bằng hiệu hai prefix vì phép cộng có nghịch đảo. Không phải mọi phép gộp đều có thể dùng cách trừ prefix.

### Optimal substructure và greedy choice

DP cần trạng thái đủ mô tả bài toán con, transition và thứ tự tính. Greedy cần chứng minh lựa chọn cục bộ có thể xuất hiện trong một lời giải tối ưu, ví dụ exchange argument hoặc cut property. Một ví dụ chạy đúng không phải proof.

### Cấu trúc đặc biệt

DAG có topological order; cây có một đường đơn giữa hai đỉnh; interval có quy tắc endpoint; chuỗi có prefix/suffix; miền giá trị nhỏ có thể dùng counting array. Tìm cấu trúc đặc biệt có thể giảm đáng kể complexity.

## 10. Bản đồ kỹ thuật từ dấu hiệu đã xác nhận

| Dấu hiệu | Kỹ thuật ứng viên | Điều kiện |
| --- | --- | --- |
| Mảng tĩnh, nhiều range sum | Prefix sum | O(n) build, O(1) query |
| Point update + range sum | Fenwick | SET cần delta |
| Range update/query đa dạng | Segment Tree | Lazy propagation khi update đoạn |
| Range min tĩnh | Sparse Table | O(n log n) build, O(1) query |
| Mảng sort, tìm ngưỡng | Binary search | Invariant, duplicate boundary |
| Cửa sổ có tính đơn điệu | Two pointers | Chứng minh điều kiện |
| Shortest path không trọng số | BFS | Mỗi cạnh cùng cost |
| Shortest path trọng số không âm | Dijkstra | Không có cạnh âm |
| Có cạnh âm | Bellman–Ford hoặc cấu trúc đặc biệt | Xét negative cycle |
| Đồ thị DAG | Topological DP | Phụ thuộc theo topo |
| Connectivity, chỉ thêm cạnh | DSU | Không xóa tùy ý |
| Interval/events | Sweep line | Tie rule chính xác |
| Pattern matching | KMP/Z | O(n+m) |
| Rank trên miền đã nén | Fenwick/Segment Tree | Coordinate compression |
| Subset nhỏ | Bitmask DP | O(2^n) hoặc O(n2^n) |
| Optimization có trạng thái | DP | State/transition/base/order |
| Greedy choice có proof | Greedy | Exchange/cut argument |
| Nhiều query biết trước | Offline sort/Mo | Có thể đổi thứ tự |
| Top-K | Heap | Chọn k phần tử ưu tiên |
| Grid components | Flood fill | O(rows·cols) |

Đây là danh sách ứng viên, không phải bộ chọn tự động từ keyword.

## 11. Quy trình quyết định bảy bước

1. **Viết output contract:** existence, count, optimum, witness hay chuỗi câu trả lời?
2. **Trừu tượng hóa dữ liệu:** sequence, graph, tree, interval, string, grid hay state space?
3. **Liệt kê workload:** static, point/range update, insert-only, fully dynamic, streaming hay offline?
4. **Ghi constraints:** n, m, q, miền giá trị, thời gian, memory, số test.
5. **Tìm tính chất toán học:** sorted, monotone, nonnegative, associative, DAG, tree, bounded alphabet?
6. **Tạo 2–3 ứng viên và loại bỏ:** precondition sai hoặc complexity quá lớn thì loại.
7. **Chứng minh và kiểm thử:** invariant, proof idea, edge cases, oracle độc lập.

Phiếu phân loại:

~~~text
Goal/output:
Data shape:
n / m / q:
Static or dynamic:
Operations:
Online or offline:
Value/weight domain:
Mathematical properties:
Candidate A + complexity:
Candidate B + complexity:
Why candidates are valid:
What could invalidate them:
Proof idea:
Edge cases / oracle:
~~~

Nếu một thuộc tính bắt buộc chưa rõ, ví dụ trọng số cạnh có thể âm không, hãy đánh dấu “chưa rõ” và quay lại đặc tả. Đừng tự giả định điều kiện thuận lợi.

## 12. Ví dụ phân loại từng bước

### A. Range sum trên mảng tĩnh

Shape=sequence; workload=static; operation=range sum; output=exact sum. Prefix sum O(n) build, O(1) mỗi query, O(n) memory. Nếu chỉ có một query nhỏ, scan trực tiếp có thể đơn giản hơn.

### B. Point update xen kẽ range sum

Operation=ADD(i,delta) và SUM(L,R) online. Fenwick hoặc Segment Tree; nếu SET, lưu giá trị hiện tại và cập nhật bằng delta. Prefix sum tĩnh không phù hợp vì một update có thể làm đổi O(n) prefix.

### C. Shortest path

Hỏi edge weight trước:
- Cạnh không trọng số hoặc cùng cost: BFS.
- Trọng số không âm: Dijkstra.
- Có cạnh âm: Bellman–Ford hoặc khai thác DAG.
- Negative cycle reachable: shortest path hữu hạn có thể không tồn tại.

### D. Maximum overlapping meetings

Mỗi cuộc họp là `[start,end)`; tạo event +1 tại start và −1 tại end, sort rồi scan. Với interval nửa mở, ở cùng thời điểm phải xử lý end trước start (hoặc tie ordering tương đương). Với interval đóng, quy tắc khác. Chưa rõ semantics thì chưa thể chốt tie rule.

### E. Substring search

Tìm mọi vị trí pattern trong text: KMP hoặc Z O(n+m). Nếu cần giữ match chồng lấn, sau một match phải tiếp tục từ prefix state thích hợp.

### F. Dynamic connectivity

Chỉ thêm cạnh và hỏi cùng thành phần: DSU. Nếu có xóa cạnh, DSU thường không đủ. Hỏi query có biết trước không để cân nhắc offline dynamic connectivity và rollback.

## 13. Keyword giống nhau nhưng kỹ thuật khác nhau

| Keyword | Trường hợp 1 | Trường hợp 2 | Điều đổi kỹ thuật |
| --- | --- | --- | --- |
| Range query | Range sum tĩnh | Range min có update | Prefix vs Segment Tree |
| Shortest path | Không trọng số | Trọng số âm | BFS vs Bellman–Ford |
| Subarray | Tổng số không âm | Tổng có số âm | Two pointers có thể sai |
| Connectivity | Chỉ thêm cạnh | Add/remove cạnh | DSU vs dynamic connectivity |
| Interval | Max overlap | Chọn interval không giao nhau | Sweep line vs scheduling |
| Count | Tần suất giá trị | Số cách đạt tổng | Frequency vs DP |
| Optimization | Predicate đơn điệu | Objective không đơn điệu | Binary search có thể không áp dụng |
| Tree | Subtree sum | Dynamic path minimum | DFS vs HLD/Segment Tree |
| String | Một pattern | Nhiều pattern | KMP/Z vs Aho–Corasick |
| Top K | Một lần | Duy trì sau update | Heap vs cấu trúc động |

Những chi tiết cần hỏi thêm thường là endpoint đóng/nửa mở, SET hay ADD, trọng số cạnh, có cho phép lặp, substring hay subsequence, có xóa cạnh không, cần giá trị hay cả witness.

## 14. Java 17: bộ phân loại rule-based minh họa

Chương trình này **không đọc ngôn ngữ tự nhiên và không tự chứng minh thuật toán**. Người giải nhập các thuộc tính đã rút ra từ đề; bộ luật trả ứng viên và precondition/cảnh báo. Khi thiếu thông tin, nó yêu cầu làm rõ thay vì đoán.

Lưu thành `ProblemClassificationDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;

public class ProblemClassificationDemo {
    enum Shape {
        SEQUENCE, GRAPH, INTERVALS, STRING, GRID, UNKNOWN
    }

    enum Workload {
        STATIC, POINT_UPDATES, RANGE_UPDATES, STREAM
    }

    enum Goal {
        RANGE_SUM, RANGE_MIN, SHORTEST_PATH,
        MAX_OVERLAP, PATTERN_MATCH, CONNECTED_COMPONENTS
    }

    enum WeightModel {
        NOT_APPLICABLE, UNWEIGHTED,
        NON_NEGATIVE, MAY_BE_NEGATIVE, UNSPECIFIED
    }

    record Problem(String label, Shape shape,
                   Workload workload, Goal goal,
                   WeightModel weights) {
        Problem {
            Objects.requireNonNull(label, "label");
            Objects.requireNonNull(shape, "shape");
            Objects.requireNonNull(workload, "workload");
            Objects.requireNonNull(goal, "goal");
            Objects.requireNonNull(weights, "weights");
            if (label.isBlank()) {
                throw new IllegalArgumentException(
                        "label must not be blank");
            }
        }
    }

    record Recommendation(
            String technique, String complexity,
            String condition) {}

    static Recommendation recommend(Problem p) {
        Objects.requireNonNull(p, "problem");

        if (p.shape() == Shape.SEQUENCE
                && p.goal() == Goal.RANGE_SUM) {
            return switch (p.workload()) {
                case STATIC -> new Recommendation(
                        "Prefix sums",
                        "O(n) build, O(1) per query",
                        "No updates; repeated range sums");
                case POINT_UPDATES -> new Recommendation(
                        "Fenwick tree",
                        "O(log n) per update/query",
                        "SET requires current value and delta");
                case RANGE_UPDATES -> new Recommendation(
                        "Two Fenwick trees / lazy segment tree",
                        "O(log n) in common variants",
                        "Choose by exact update semantics");
                case STREAM -> new Recommendation(
                        "Need more problem specification",
                        "Depends on retention/window",
                        "Clarify whether old values can be discarded");
            };
        }

        if (p.shape() == Shape.SEQUENCE
                && p.goal() == Goal.RANGE_MIN) {
            return switch (p.workload()) {
                case STATIC -> new Recommendation(
                        "Sparse Table",
                        "O(n log n) build, O(1) per query",
                        "Static range minimum");
                case POINT_UPDATES -> new Recommendation(
                        "Segment Tree",
                        "O(log n) per update/query",
                        "Point assignment + range minimum");
                case RANGE_UPDATES -> new Recommendation(
                        "Lazy Segment Tree",
                        "O(log n) in common variants",
                        "Define lazy-tag composition");
                case STREAM -> new Recommendation(
                        "Need more problem specification",
                        "Depends on expiration",
                        "Clarify sliding-window semantics");
            };
        }

        if (p.shape() == Shape.GRAPH
                && p.goal() == Goal.SHORTEST_PATH) {
            return switch (p.weights()) {
                case UNWEIGHTED -> new Recommendation(
                        "BFS", "O(V + E)",
                        "All edges have equal cost");
                case NON_NEGATIVE -> new Recommendation(
                        "Dijkstra",
                        "O((V + E) log V) with binary heap",
                        "All edge weights must be non-negative");
                case MAY_BE_NEGATIVE -> new Recommendation(
                        "Bellman-Ford", "O(V * E)",
                        "Check reachable negative cycles");
                case UNSPECIFIED, NOT_APPLICABLE ->
                        new Recommendation(
                                "Clarify edge-weight contract",
                                "Do not choose BFS/Dijkstra yet",
                                "Weight domain changes correctness");
            };
        }

        if (p.shape() == Shape.INTERVALS
                && p.goal() == Goal.MAX_OVERLAP
                && p.workload() == Workload.STATIC) {
            return new Recommendation(
                    "Sweep line", "O(n log n) + O(n)",
                    "Endpoint tie order must match semantics");
        }

        if (p.shape() == Shape.STRING
                && p.goal() == Goal.PATTERN_MATCH
                && p.workload() == Workload.STATIC) {
            return new Recommendation(
                    "KMP or Z algorithm", "O(n + m)",
                    "Preserve overlaps when required");
        }

        if (p.shape() == Shape.GRID
                && p.goal() == Goal.CONNECTED_COMPONENTS
                && p.workload() == Workload.STATIC) {
            return new Recommendation(
                    "DFS/BFS flood fill",
                    "O(rows * columns)",
                    "Specify neighbor directions");
        }

        if (p.shape() == Shape.GRAPH
                && p.goal() == Goal.CONNECTED_COMPONENTS
                && p.workload() == Workload.STATIC) {
            return new Recommendation(
                    "DFS/BFS", "O(V + E)",
                    "Start from each unvisited vertex");
        }

        return new Recommendation(
                "Need more problem specification",
                "Cannot infer safely",
                "Clarify shape, operations, goal and constraints");
    }

    private static List<Problem> examples() {
        return List.of(
                new Problem("static range sum",
                        Shape.SEQUENCE, Workload.STATIC,
                        Goal.RANGE_SUM, WeightModel.NOT_APPLICABLE),
                new Problem("point updates + range sum",
                        Shape.SEQUENCE, Workload.POINT_UPDATES,
                        Goal.RANGE_SUM, WeightModel.NOT_APPLICABLE),
                new Problem("range add + range sum",
                        Shape.SEQUENCE, Workload.RANGE_UPDATES,
                        Goal.RANGE_SUM, WeightModel.NOT_APPLICABLE),
                new Problem("static range minimum",
                        Shape.SEQUENCE, Workload.STATIC,
                        Goal.RANGE_MIN, WeightModel.NOT_APPLICABLE),
                new Problem("point update + range minimum",
                        Shape.SEQUENCE, Workload.POINT_UPDATES,
                        Goal.RANGE_MIN, WeightModel.NOT_APPLICABLE),
                new Problem("unweighted shortest path",
                        Shape.GRAPH, Workload.STATIC,
                        Goal.SHORTEST_PATH, WeightModel.UNWEIGHTED),
                new Problem("nonnegative weighted shortest path",
                        Shape.GRAPH, Workload.STATIC,
                        Goal.SHORTEST_PATH, WeightModel.NON_NEGATIVE),
                new Problem("negative weighted shortest path",
                        Shape.GRAPH, Workload.STATIC,
                        Goal.SHORTEST_PATH, WeightModel.MAY_BE_NEGATIVE),
                new Problem("unknown edge weights",
                        Shape.GRAPH, Workload.STATIC,
                        Goal.SHORTEST_PATH, WeightModel.UNSPECIFIED),
                new Problem("maximum interval overlap",
                        Shape.INTERVALS, Workload.STATIC,
                        Goal.MAX_OVERLAP, WeightModel.NOT_APPLICABLE),
                new Problem("substring search",
                        Shape.STRING, Workload.STATIC,
                        Goal.PATTERN_MATCH, WeightModel.NOT_APPLICABLE),
                new Problem("grid components",
                        Shape.GRID, Workload.STATIC,
                        Goal.CONNECTED_COMPONENTS,
                        WeightModel.NOT_APPLICABLE),
                new Problem("static graph components",
                        Shape.GRAPH, Workload.STATIC,
                        Goal.CONNECTED_COMPONENTS,
                        WeightModel.NOT_APPLICABLE)
        );
    }

    private static void verifyRules(List<Problem> cases) {
        String[] expected = {
                "Prefix sums",
                "Fenwick tree",
                "Two Fenwick trees / lazy segment tree",
                "Sparse Table",
                "Segment Tree",
                "BFS",
                "Dijkstra",
                "Bellman-Ford",
                "Clarify edge-weight contract",
                "Sweep line",
                "KMP or Z algorithm",
                "DFS/BFS flood fill",
                "DFS/BFS"
        };

        if (cases.size() != expected.length) {
            throw new AssertionError("wrong example count");
        }
        for (int i = 0; i < expected.length; i++) {
            String actual = recommend(cases.get(i)).technique();
            if (!expected[i].equals(actual)) {
                throw new AssertionError(
                        "rule mismatch at case " + i
                                + ": " + actual);
            }
        }
    }

    public static void main(String[] args) {
        List<Problem> cases = examples();
        System.out.println("Problem classification examples:");
        for (Problem p : cases) {
            System.out.println(
                    p.label() + " -> "
                            + recommend(p).technique());
        }

        verifyRules(cases);
        System.out.println("rule checks = " + cases.size());

        try {
            new Problem(" ", Shape.SEQUENCE,
                    Workload.STATIC, Goal.RANGE_SUM,
                    WeightModel.NOT_APPLICABLE);
            throw new AssertionError(
                    "blank label was accepted");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid descriptor rejected = true");
        }

        System.out.println("all checks passed = true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ProblemClassificationDemo.java
java ProblemClassificationDemo
~~~

Stdout dự kiến chính xác:

~~~text
Problem classification examples:
static range sum -> Prefix sums
point updates + range sum -> Fenwick tree
range add + range sum -> Two Fenwick trees / lazy segment tree
static range minimum -> Sparse Table
point update + range minimum -> Segment Tree
unweighted shortest path -> BFS
nonnegative weighted shortest path -> Dijkstra
negative weighted shortest path -> Bellman-Ford
unknown edge weights -> Clarify edge-weight contract
maximum interval overlap -> Sweep line
substring search -> KMP or Z algorithm
grid components -> DFS/BFS flood fill
static graph components -> DFS/BFS
rule checks = 13
invalid descriptor rejected = true
all checks passed = true
~~~

Chương trình chỉ minh họa luật cho các descriptor đã được người giải nhập. Nó không tự đọc đề, tự tính constraints hay chứng minh precondition. Kỹ thuật được gợi ý vẫn phải được xác nhận trên bài thật.

## 15. Kiểm thử sau khi chọn kỹ thuật

Thiết kế test theo chính các điều kiện làm kỹ thuật được chọn:

- Prefix/range: n=0, đoạn một phần tử, đoạn toàn mảng, L=0, R=n−1.
- Binary search: mảng rỗng, duplicate, key ngoài miền.
- BFS: nguồn cô lập, đồ thị không liên thông, cạnh lặp nếu được phép.
- Dijkstra: trọng số 0, cạnh song song, không có cạnh âm.
- Sweep line: nhiều endpoint trùng, start=end, interval đóng/nửa mở.
- String matching: pattern dài hơn text, match chồng lấn, pattern rỗng theo hợp đồng.
- DP: base state, giá trị âm, modulo và overflow.

### Oracle brute force

Với n nhỏ, dùng cách đơn giản và khác ý tưởng làm oracle:

| Thuật toán tối ưu | Oracle nhỏ |
| --- | --- |
| Binary search | Linear scan |
| BFS | Floyd–Warshall |
| Prefix sum | Cộng trực tiếp đoạn |
| Greedy | Enumeration toàn bộ phương án |
| DSU | Gán nhãn component bằng BFS/DFS |
| DP | Brute-force recursion |

Test cố định, randomized test với seed, và property-based test bổ sung cho nhau. Một trace giúp hiểu một lần chạy; test suite kiểm nhiều input; proof giải thích mọi input thỏa precondition.

## 16. Lỗi thường gặp khi phân loại

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Chọn theo keyword | Bỏ qua operation/constraints | Viết contract |
| Thấy mảng là dùng two pointers | Thiếu monotonicity | Chứng minh invariant |
| Thấy shortest path là BFS | Bỏ qua trọng số | Xác định edge weights |
| Dijkstra với cạnh âm | Sai precondition | Bellman–Ford/đặc tính riêng |
| Prefix sum khi có update | Dữ liệu tiền xử lý lỗi thời | Fenwick/Segment Tree |
| Fenwick cho mọi range query | Không hỗ trợ mọi phép gộp | Xem algebra |
| DSU cho add/remove tùy ý | Không xử lý xóa cạnh | Dynamic connectivity |
| Greedy theo sample | Thiếu greedy-choice proof | Exchange/cut argument |
| DP không có state rõ | Recurrence mơ hồ | State/transition/base/order |
| Binary search thiếu proof đơn điệu | Predicate đổi nhiều lần | Chứng minh monotonicity |
| Chỉ xét thời gian | Có thể vượt RAM | Ước lượng memory |
| Bỏ qua witness | Không dựng được output | Lưu parent/choice |
| Nhầm count với existence | Trả thiếu yêu cầu | Đọc output contract |
| Không xét duplicate | Sai rank/match | Test bằng nhau |
| Không rõ endpoint | Sai tie handling | Định nghĩa interval |
| Offline sort quên query ID | Trả sai thứ tự | Lưu và khôi phục ID |
| Chỉ dùng average record/value | Bỏ qua outlier | Kiểm worst-case |
| Sentinel trùng giá trị hợp lệ | Trạng thái mơ hồ | Tách visited flag |
| Chọn cấu trúc quá phức tạp | Khó chứng minh và debug | Baseline trước |
| Oracle dùng lại cùng logic | Lỗi chung không bị phát hiện | Oracle độc lập |

Với mỗi ứng viên, hỏi: precondition đúng không, hỗ trợ đủ operations không, complexity và memory đạt không, online/offline có tương thích không, duplicate/negative/overflow/boundary đã xử lý chưa, có proof và oracle không?

## 17. Bài tập thực hành

1. Viết một đề thành input/output/constraints.
2. Phân loại các câu chuyện thành sequence, graph, interval, string hoặc state space.
3. So sánh mảng static query với point updates.
4. So range sum tĩnh với range minimum tĩnh.
5. Chọn cấu trúc cho point SET + range sum và giải thích delta.
6. Chọn cấu trúc cho range add + range sum.
7. Vì sao range assignment + range min cần mô hình khác hai BIT?
8. Liệt kê câu hỏi về trọng số trước khi chọn shortest path.
9. Tạo graph có cạnh âm và phân tích Dijkstra.
10. Phân loại maximum interval overlap và tie rule.
11. So interval scheduling với maximum overlap.
12. Phân biệt substring và subsequence.
13. Khi nào dùng KMP và khi nào dùng Aho–Corasick?
14. Nêu điều kiện two pointers cho subarray sum.
15. Tạo phản ví dụ số âm phá monotonicity.
16. Chứng minh predicate đơn điệu trong một bài binary search on answer.
17. Ước lượng O(n²) khi n=200.000.
18. Tính payload của ba mảng long kích thước n.
19. So O(n+q) và O(nq).
20. Chọn online hay offline cho chuỗi query.
21. Khôi phục thứ tự query bằng ID như thế nào?
22. Chọn DSU cho insert-only connectivity.
23. Nêu cách xử lý add/remove offline.
24. Xác định state/transition/base cho một DP.
25. Viết greedy-choice proof cho interval scheduling.
26. Phân biệt existence, counting, optimization.
27. Khi nào cần lưu parent/witness?
28. Chứng minh BFS cho shortest path không trọng số.
29. Nêu precondition của Dijkstra.
30. Nêu negative cycle trong Bellman–Ford.
31. Chọn Sparse Table cho static RMQ.
32. Vì sao Sparse Table khó hỗ trợ point update?
33. Chọn Segment Tree cho point update + range min.
34. Chọn sweep line cho sự kiện thời gian.
35. Dùng Fenwick cho frequency sau coordinate compression.
36. So top-K một lần và top-K động.
37. Phân loại grid components và state-space shortest path.
38. Tạo bảng quyết định shape/workload/goal.
39. Viết 5 edge cases cho một kỹ thuật đã chọn.
40. So lời giải tối ưu với brute oracle trên n nhỏ.
41. Vì sao trace không thay proof?
42. Thiết kế randomized test với seed cố định.
43. Nêu overflow có thể làm đổi kiểu số.
44. Tìm đề thiếu endpoint semantics và câu cần hỏi.
45. Chọn cấu trúc cho streaming không lưu hết input.
46. So static và fully dynamic data structures.
47. Phân biệt data shape và operation semantics.
48. Chọn kỹ thuật khi n lớn nhưng q rất nhỏ.
49. Đưa ví dụ cùng keyword nhưng khác kỹ thuật.
50. Viết phiếu phân loại và bảo vệ lựa chọn bằng complexity/proof.

## 18. Checklist trước khi code

- **Output:** existence, count, min/max, optimum, witness hay toàn bộ query answers?
- **Shape:** sequence, graph, tree, grid, interval, string, set, matrix hay state space?
- **Workload:** static, point/range update, insert-only, fully dynamic, offline hay stream?
- **Operations:** SET khác ADD; range assign khác range add.
- **Constraints:** n, m, q, tổng test, thời gian, memory, miền giá trị?
- **Math:** sorted, monotone, nonnegative, associative, invertible, DAG, tree?
- **Candidates:** đã có baseline và phương án tối ưu?
- **Elimination:** precondition nào khiến ứng viên không dùng được?
- **Complexity:** tổng thời gian và bộ nhớ có đạt?
- **Correctness:** có invariant/proof?
- **Testing:** có boundary, duplicate, negative, overflow và oracle?
- **Implementation:** có cần parent, witness, query ID hoặc snapshot?
- **Reproducibility:** có input nhỏ, seed và regression case?

**Kết luận:** đừng chọn kỹ thuật từ một từ khóa. Hãy chuyển đề thành hợp đồng, phân loại hình dạng dữ liệu, workload, operations, mục tiêu, constraints và tính chất toán học; lập vài ứng viên, loại các cách vi phạm precondition hoặc quá tốn tài nguyên, rồi chứng minh và kiểm thử. Prefix sum, Fenwick, Segment Tree, BFS, Dijkstra, sweep line, KMP, DP và greedy đều là công cụ. Chất lượng lời giải bắt đầu từ việc hiểu đúng bài toán mà công cụ phải giải.
