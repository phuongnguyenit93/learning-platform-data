# Kiểm thử đối kháng với đầu vào đã có thứ tự hoặc mất cân bằng

> **Chủ đề:** Computer Science Algorithms → **Cài đặt và kiểm thử**.  
> **Mục tiêu:** Thiết kế, chạy và diễn giải các bộ kiểm thử có chủ ý khai thác điểm yếu của thuật toán khi dữ liệu **đã sắp xếp**, **đảo ngược**, **nhiều phần tử trùng**, hoặc có **cấu trúc mất cân bằng**. Bài tập trung vào kiểm tra tính đúng, độ phức tạp và độ sâu bộ nhớ: QuickSort/pivot và partition, cây tìm kiếm nhị phân, đồ thị dạng đường đi/ngôi sao, kiểm thử so sánh với oracle, kiểm thử thuộc tính và tái lập lỗi bằng seed. Ví dụ dùng Java 17.

## 1. Kiểm thử đối kháng là gì?

**Adversarial testing** (*kiểm thử đối kháng*) là việc chủ động tạo đầu vào thỏa đúng hợp đồng bài toán nhưng gây khó cho một giả định hoặc một nhánh của thuật toán: dữ liệu đã có thứ tự, cực nhiều giá trị bằng nhau, một cấu trúc dữ liệu kéo dài thành chuỗi, hay tập dữ liệu tập trung phần lớn công việc vào một nhánh.

Mục đích không chỉ là tìm kết quả sai. Một thuật toán vẫn trả **đúng output** nhưng dùng số phép so sánh O(n²) thay vì O(n log n), dùng stack sâu O(n), hoặc phân bổ bộ nhớ vượt dự kiến. Các vấn đề này đều cần được phát hiện.

**Phân biệt ba loại phép thử:**

- **Correctness test:** So kết quả với đáp án chính xác, kiểm invariants và yêu cầu đầu vào/đầu ra.
- **Complexity stress:** Đo số phép toán, chiều cao cây, độ sâu đệ quy, bộ nhớ/queue; tìm trường hợp xấu về cấu trúc.
- **Performance benchmark:** Đo thời gian và tài nguyên thực tế trong môi trường có kiểm soát. Một test nhanh/chậm đơn lẻ không chứng minh được độ phức tạp.

Không được mặc định “random test chạy qua” nghĩa là không có worst case. Ví dụ QuickSort dùng phần tử cuối làm pivot thường không gặp đầu vào đã sắp xếp trong một bộ test ngẫu nhiên phân phối đều, dù đó là phản ví dụ rất đơn giản.

### 1.1. Đầu vào đối kháng phải hợp lệ

Nếu đề yêu cầu mảng số nguyên, dãy tăng, dãy giảm, dãy toàn phần tử bằng nhau đều **hợp lệ** trừ khi có ràng buộc loại trừ rõ ràng. Nếu đề không hỗ trợ null, một test null là kiểm tra validation input, không phải bằng chứng worst-case thuật toán.

Hãy ghi cụ thể: miền giá trị, n tối đa, có duplicate hay không, độ sâu/chiều rộng đồ thị, các ràng buộc về thứ tự, và bộ nhớ cho phép. Một case sai miền không nên được báo là thất bại của thuật toán trên miền hợp lệ.

## 2. Bộ mẫu dữ liệu có chủ đích

Với thuật toán sắp xếp hoặc tìm kiếm trên mảng, đừng chỉ tạo `Random` rồi gọi đó là kiểm thử đầy đủ. Nên có các họ đầu vào sau:

| Dạng | Ví dụ | Điểm yếu muốn phát hiện |
|---|---|---|
| Tăng dần | `[1,2,3,4,5,6]` | Pivot đầu/cuối gây chia lệch; cây BST chèn thành chuỗi |
| Giảm dần | `[6,5,4,3,2,1]` | Pivot cực trị; lỗi ranh giới |
| Tất cả bằng nhau | `[7,7,7,7,7]` | Partition hai nhánh với duplicate, vòng lặp không tiến |
| Miền giá trị rất nhỏ | `[0,1,0,1,0,1]` | Rất nhiều equal keys, mất cân bằng partition |
| Gần như đã sắp xếp | `[1,2,4,3,5,6]` | Thuật toán nhạy với ít nghịch thế/đổi vị trí |
| Organ-pipe | `[1,2,3,4,3,2,1]` | Mẫu có đỉnh ở giữa; test chiến lược chọn pivot |
| Sawtooth | `[0,1,2,0,1,2,0,1]` | Nhiều khóa lặp có cấu trúc |
| Xen kẽ cực trị | `[1,9,2,8,3,7,4,6]` | So sánh/partition thiếu kiểm soát |
| Đã sắp xếp với một ngoại lệ | `[1,2,3,100,4,5]` | Lỗi phân đoạn/điều kiện dừng |
| Rỗng hoặc một phần tử | `[]`, `[5]` | Base case, lệch chỉ số, đọc vượt mảng |

Các họ này **không đảm bảo** luôn là worst case cho mọi biến thể. Ví dụ pivot chọn ngẫu nhiên, median-of-three hoặc introsort có phản ứng khác hẳn pivot cuối. Đầu vào nào “đối kháng” phải gắn với **cơ chế thuật toán cụ thể**.

### 2.1. Thay đổi kích thước n

Chạy các n như `0,1,2,3,4,7,8,15,16,31,32,63,64,...`, và thêm giá trị gần giới hạn đề bài. Test ở một n nhỏ chứng minh ví dụ tính toán; test ở n lớn giúp phát hiện stack overflow, O(n²) hoặc lỗi cấp phát.

### 2.2. Số lượng duplicate là một chiều kiểm thử riêng

Các bộ test có đúng n giá trị phân biệt, 2 giá trị phân biệt, 1 giá trị phân biệt có thể làm thuật toán partition chạy rất khác. Tạo duplicate có chủ đích, đừng trông chờ bộ test ngẫu nhiên liên tục sinh ra đủ va chạm.

### 2.3. Kiểm soát nguồn ngẫu nhiên

Sử dụng seed cố định (`new Random(543)`) giúp tái lập bộ input khi test lỗi. Khi một random test thất bại, lưu cả seed, kích thước, mảng tối giản và version thuật toán. Seed chỉ tạo khả năng lặp lại, **không thay thế** oracle.

## 3. QuickSort và trường hợp chia lệch

Xét QuickSort với partition Lomuto:

1. Chọn phần tử **cuối** `a[hi]` làm pivot.
2. Duyệt `j=lo..hi−1`.
3. Đưa mọi phần tử `a[j] ≤ pivot` về phía trái.
4. Đưa pivot về vị trí phân hoạch rồi đệ quy hai nửa.

Nếu mảng tăng dần, pivot luôn là cực đại. Kết quả phân hoạch là hai phần kích thước `n−1` và `0`. Nếu mảng giảm dần, pivot cũng là cực trị (cực tiểu, rồi có thể luân phiên), tiếp tục tạo nhánh cực lệch.

Đối với mảng **toàn phần tử bằng nhau**, điều kiện `≤ pivot` khiến tất cả phần tử bị gom sang bên trái, nên cũng tạo chuỗi đệ quy dài.

### 3.1. Đếm phép so sánh thay vì chỉ nhìn đồng hồ

Tại một lần partition đoạn dài m, Lomuto duyệt m−1 phần tử. Nếu mỗi lần chỉ giảm kích thước 1, số lần so sánh là:

`C(n)=(n−1)+(n−2)+...+1=n(n−1)/2`.

Vậy:

- n=12 ⇒ C=**66**.
- n=64 ⇒ C=**2016**.
- n=1000 ⇒ C=**499500**.

Đây là O(n²), mặc dù output vẫn được sắp xếp đúng. Trong bản đệ quy trực tiếp, chiều sâu lời gọi có thể đạt O(n), nên input lớn có nguy cơ `StackOverflowError`.

### 3.2. Độ sâu đệ quy cũng là một metric

Trên mảng 12 phần tử tăng, giảm hoặc đều nhau, một implementation Lomuto pivot cuối với cách đếm “mỗi lời gọi trên đoạn không rỗng” có thể đạt `maxDepth=12`. Đừng chỉ assert mảng đầu ra đã sorted; hãy kiểm thêm `comparisons`, `maxDepth` và sự mất cân bằng.

### 3.3. Ba vùng cho duplicate

**Three-way partition / Dutch National Flag** chia thành:

`[<pivot] | [=pivot] | [>pivot]`.

Sau đó chỉ đệ quy vùng `<` và `>`, **không đệ quy vùng bằng**. Nếu mọi phần tử đều bằng pivot, chỉ cần quét n phần tử, không còn các lời gọi trên `n−1` phần tử: số lần so sánh được đếm theo vòng quét là **n**.

Tuy nhiên three-way **không tự bảo đảm O(n log n) trong mọi input**. Nếu luôn chọn pivot cực trị trên dữ liệu phân biệt, vẫn có thể chia lệch O(n²). Nó xử lý tốt trường hợp duplicate, không phải giải pháp đầy đủ cho mọi đầu vào đối kháng.

## 4. Những biện pháp chống suy biến và giới hạn của chúng

- **Randomized pivot:** giảm khả năng một mẫu đầu vào cố định ép pivot liên tục cực trị, nhưng không bảo đảm worst-case O(n log n) tuyệt đối cho mọi chuỗi chọn pivot; seed cần ghi lại khi debug.
- **Median-of-three:** thường tránh pivot cực trị trên mảng tăng đơn giản, nhưng vẫn có các mẫu đối kháng có cấu trúc; không phải chứng minh O(n log n) worst-case.
- **Three-way partition:** cải thiện dữ liệu nhiều duplicate, nhất là toàn bằng nhau.
- **Introsort:** theo dõi chiều sâu, đến ngưỡng chuyển sang heapsort hoặc thuật toán có worst-case phù hợp để tránh phân hoạch sâu vô hạn. Đây là kỹ thuật bảo vệ về độ phức tạp, không phải chỉ chọn pivot “khôn” hơn.
- **Đệ quy nhánh nhỏ trước, lặp trên nhánh lớn:** có thể giảm stack phụ xuống O(log n) ngay cả khi partition lệch, nhưng **không giảm** số phép so sánh O(n²) của pivot kém.

Trong Java 17, có thể dùng `Arrays.sort` làm oracle sắp xếp của test. Không được từ đó suy rằng tất cả implementation mang tên QuickSort đều có cùng hành vi; phải instrument implementation đang kiểm thử.

## 5. Java 17 — quan sát QuickSort đối kháng

Lưu file **PivotAdversarialDemo.java**. Đây là chương trình độc lập, có hai thuật toán tự cài đặt: Lomuto pivot cuối và three-way pivot đầu. Mỗi thuật toán đếm một phép so sánh mỗi khi kiểm một phần tử với pivot trong partition.

```java
import java.util.Arrays;

public class PivotAdversarialDemo {
    static final class Metrics {
        long comparisons = 0;
        int maxDepth = 0;
    }

    static void swap(int[] a, int i, int j) {
        int tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    static void quickLast(int[] a, int lo, int hi,
                          int depth, Metrics m) {
        if (lo > hi) return;
        m.maxDepth = Math.max(m.maxDepth, depth);
        if (lo == hi) return;

        int pivot = a[hi], i = lo;
        for (int j = lo; j < hi; j++) {
            m.comparisons++;
            if (a[j] <= pivot) {
                swap(a, i, j);
                i++;
            }
        }
        swap(a, i, hi);
        quickLast(a, lo, i - 1, depth + 1, m);
        quickLast(a, i + 1, hi, depth + 1, m);
    }

    static void quickThree(int[] a, int lo, int hi,
                           int depth, Metrics m) {
        if (lo > hi) return;
        m.maxDepth = Math.max(m.maxDepth, depth);
        if (lo == hi) return;

        int pivot = a[lo];
        int lt = lo, i = lo, gt = hi;
        while (i <= gt) {
            m.comparisons++;
            int cmp = Integer.compare(a[i], pivot);
            if (cmp < 0) {
                swap(a, lt++, i++);
            } else if (cmp > 0) {
                swap(a, i, gt--);
            } else {
                i++;
            }
        }
        quickThree(a, lo, lt - 1, depth + 1, m);
        quickThree(a, gt + 1, hi, depth + 1, m);
    }

    static void report(String label, int[] input, boolean threeWay) {
        int[] expected = input.clone();
        Arrays.sort(expected);

        int[] copy = input.clone();
        Metrics m = new Metrics();
        if (threeWay) {
            quickThree(copy, 0, copy.length - 1, 1, m);
        } else {
            quickLast(copy, 0, copy.length - 1, 1, m);
        }
        System.out.printf(
            "%s comparisons=%d depth=%d oracle=%s%n",
            label, m.comparisons, m.maxDepth,
            Arrays.equals(copy, expected));
    }

    public static void main(String[] args) {
        int n = 12;
        int[] sorted = new int[n];
        int[] reversed = new int[n];
        int[] equal = new int[n];
        for (int i = 0; i < n; i++) {
            sorted[i] = i;
            reversed[i] = n - i;
            equal[i] = 7;
        }

        report("sorted lastPivot", sorted, false);
        report("reversed lastPivot", reversed, false);
        report("allEqual lastPivot", equal, false);
        report("allEqual threeWay", equal, true);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PivotAdversarialDemo.java
java PivotAdversarialDemo
```

Stdout:

```text
sorted lastPivot comparisons=66 depth=12 oracle=true
reversed lastPivot comparisons=66 depth=12 oracle=true
allEqual lastPivot comparisons=66 depth=12 oracle=true
allEqual threeWay comparisons=12 depth=1 oracle=true
```

**Vì sao stdout xác định?** Input cố định, thuật toán đếm theo thao tác của nó; không phụ thuộc thời gian CPU, JIT hay scheduler.

**Lưu ý thực tế:** Đây là demo về trường hợp xấu, **không phải** một thư viện QuickSort production. Đừng đưa mảng hàng triệu phần tử đã sắp xếp vào hàm `quickLast` đệ quy không giới hạn; chính đó là ca stress có thể làm cạn stack. Với đầu vào lớn cần phiên bản có fallback/giới hạn stack hoặc thư viện đã được kiểm thử kỹ.

### 5.1. Bất biến phân hoạch

Lomuto: trước vòng lặp ở vị trí j, đoạn `[lo,i)` gồm các phần tử đã xét `≤pivot`, đoạn `[i,j)` gồm các phần tử đã xét `>pivot`, còn `[j,hi)` chưa xét. Sau khi đặt pivot vào i, mọi phần tử trước i `≤pivot`, mọi phần tử sau i `>pivot`.

Three-way: tại mọi bước, `[lo,lt)` nhỏ hơn pivot; `[lt,i)` bằng; `(gt,hi]` lớn hơn; `[i,gt]` chưa xử lý. Khi i>gt, vùng bằng được bỏ qua trong đệ quy. Điều này giải thích cả tính đúng lẫn độ cải thiện trên dữ liệu bằng nhau.

## 6. Đầu vào đã có thứ tự làm suy biến BST không tự cân bằng

Xét **binary search tree (BST)** thông thường, chèn một khóa bằng cách đi xuống trái nếu nhỏ hơn, phải nếu lớn hơn. Nếu chèn các khóa `1,2,...,n` theo đúng thứ tự tăng mà không có phép quay/cân bằng, mọi node mới đều đi sang phải.

BST có **n node nhưng chiều cao n** (đếm theo số node trên đường dài nhất). Khi đó:

- Tìm khóa nằm sâu nhất cần O(n) node visits.
- Chèn n khóa theo thứ tự tăng cần `0+1+...+(n−1)=n(n−1)/2` phép so sánh với node đã có, theo cách đếm trong demo.
- Đệ quy tìm kiếm/duyệt một cây cực dài có thể tràn stack.

Nếu chèn theo thứ tự giảm, cây suy biến sang trái với độ sâu tương tự. Nếu luôn đưa duplicate sang phải, input toàn khóa bằng nhau cũng có thể tạo chain, tùy **quy ước xử lý duplicate** của implementation.

### 6.1. Chèn cùng tập khóa theo thứ tự cân bằng

Với 15 khóa `1..15`, chèn midpoint trước:

`8,4,2,1,3,6,5,7,12,10,9,11,14,13,15`.

Cây thu được là BST hoàn hảo có chiều cao **4**. Tổng lượt so sánh khi chèn là **34** (một root0, hai node độ sâu1, bốn node độ sâu2, tám node độ sâu3).

Cả hai cây chứa **cùng bộ khóa**. Sự khác biệt nằm ở **thứ tự cập nhật**, không phải giá trị cuối của tập.

### 6.2. Không nhầm BST với cây tự cân bằng

AVL/Red-Black tree có tái cân bằng để tránh chain dài với các thao tác thường gặp, còn BST demo thì không. Trong Java, `TreeMap` dùng red-black tree; không được suy ra `TreeMap` suy biến giống class BST không quay ở dưới.

## 7. Java 17 — kiểm thử chiều cao BST và số phép so sánh

Lưu file **BstShapeAuditDemo.java**:

```java
import java.util.ArrayDeque;

public class BstShapeAuditDemo {
    static final class Node {
        final int key;
        Node left, right;
        Node(int key) { this.key = key; }
    }

    static final class Tree {
        Node root;
        long insertComparisons;

        void insert(int key) {
            if (root == null) {
                root = new Node(key);
                return;
            }
            Node at = root;
            while (true) {
                insertComparisons++;
                if (key < at.key) {
                    if (at.left == null) {
                        at.left = new Node(key);
                        return;
                    }
                    at = at.left;
                } else {
                    // Duplicate keys deliberately go right.
                    if (at.right == null) {
                        at.right = new Node(key);
                        return;
                    }
                    at = at.right;
                }
            }
        }

        int height() {
            if (root == null) return 0;
            ArrayDeque<Node> q = new ArrayDeque<>();
            q.add(root);
            int levels = 0;
            while (!q.isEmpty()) {
                int size = q.size();
                for (int i = 0; i < size; i++) {
                    Node at = q.remove();
                    if (at.left != null) q.add(at.left);
                    if (at.right != null) q.add(at.right);
                }
                levels++;
            }
            return levels;
        }

        int searchVisits(int key) {
            Node at = root;
            int visits = 0;
            while (at != null) {
                visits++;
                if (key == at.key) return visits;
                at = key < at.key ? at.left : at.right;
            }
            return visits;
        }
    }

    static void insertMedianFirst(Tree tree, int lo, int hi) {
        if (lo > hi) return;
        int mid = lo + (hi - lo) / 2;
        tree.insert(mid);
        insertMedianFirst(tree, lo, mid - 1);
        insertMedianFirst(tree, mid + 1, hi);
    }

    public static void main(String[] args) {
        Tree increasing = new Tree();
        Tree decreasing = new Tree();
        Tree medianFirst = new Tree();
        Tree duplicates = new Tree();

        for (int x = 1; x <= 15; x++) increasing.insert(x);
        for (int x = 15; x >= 1; x--) decreasing.insert(x);
        insertMedianFirst(medianFirst, 1, 15);
        for (int i = 0; i < 8; i++) duplicates.insert(7);

        System.out.printf(
            "sorted height=%d insertComparisons=%d search15=%d%n",
            increasing.height(), increasing.insertComparisons,
            increasing.searchVisits(15));
        System.out.printf(
            "reversed height=%d insertComparisons=%d%n",
            decreasing.height(), decreasing.insertComparisons);
        System.out.printf(
            "medianFirst height=%d insertComparisons=%d search15=%d%n",
            medianFirst.height(), medianFirst.insertComparisons,
            medianFirst.searchVisits(15));
        System.out.println("duplicateRight height="
                + duplicates.height());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 BstShapeAuditDemo.java
java BstShapeAuditDemo
```

Stdout:

```text
sorted height=15 insertComparisons=105 search15=15
reversed height=15 insertComparisons=105
medianFirst height=4 insertComparisons=34 search15=4
duplicateRight height=8
```

**Tính đúng:** Với chèn tăng, node mới luôn nối vào nhánh phải sâu nhất, tạo đường dài15. Với chèn giảm, tương tự về nhánh trái. Với chèn midpoint trước, cây phân đôi đều và có bốn tầng. Duplicate được đưa phải để phơi bày vấn đề xử lý khóa trùng; đây là **quy tắc của class demo**, không phải quy tắc bắt buộc của mọi BST.

**Chỉ số đo:** `insertComparisons` đếm số node đã tồn tại mà phép chèn mới so khóa với nó. Không tính riêng phép kiểm `root==null` cho lần chèn đầu. `searchVisits` đếm node đã thăm trong tìm kiếm.

**Phòng lỗi:** Bài chọn `height()` dạng BFS thay vì DFS đệ quy, để phép kiểm chiều cao tự nó không bị giới hạn bởi stack lời gọi trên cây dài. Trên cây cực sâu, phương thức chèn vòng lặp cũng tránh chồng stack; nhưng O(n²) công việc vẫn còn.

## 8. Cấu trúc mất cân bằng trong đồ thị

Đầu vào “mất cân bằng” không chỉ xảy ra ở mảng/cây tìm kiếm. Với cùng n đỉnh và n−1 cạnh, hình dạng đồ thị có thể làm bộ nhớ và độ sâu xử lý khác nhau:

- **Path graph:** `0—1—2—...—(n−1)`. DFS đệ quy từ0 có thể sâu **n**, BFS hàng đợi gần như chỉ chứa một đỉnh.
- **Star graph:** đỉnh0 nối tất cả đỉnh1..n−1. DFS đệ quy từ0 trong một cây sao có độ sâu tối đa **2**, trong khi BFS từ0 có thể chứa **n−1** đỉnh trong queue sau khi mở rộng tâm.

Hai đồ thị có cùng số đỉnh, cùng số cạnh, đều liên thông. Độ phức tạp thời gian BFS/DFS theo adjacency list đều O(V+E), nhưng **hình dạng quyết định peak recursion depth và peak queue size**.

### 8.1. Một test lớn có thể tự làm hỏng chương trình

DFS đệ quy trên path dài có thể gây `StackOverflowError`, dù thuật toán về mặt toán học vẫn duyệt đúng. Để tránh phụ thuộc độ sâu stack, dùng DFS lặp với `ArrayDeque` hoặc xem xét giới hạn độ sâu hợp lý. Java không cho một độ sâu đệ quy an toàn cố định cho mọi JVM/cấu hình.

### 8.2. Ghi visited khi enqueue

Trong BFS trên đồ thị có chu trình hoặc nhiều đường vào một đỉnh, đánh dấu `visited[v]=true` **ngay khi đưa vào queue** giúp tránh enqueue trùng. Nếu đánh dấu muộn sau khi dequeue, queue có thể phình và số lượt xử lý tăng.

### 8.3. Metric cần đo

Tách các biến sau:

- Số đỉnh reachable.
- Max recursion depth của DFS.
- Peak queue length của BFS.
- Tổng đỉnh/cạnh đã duyệt.
- Output đúng, ví dụ tập đỉnh visited.

Đừng so độ sâu DFS giữa hai thứ tự adjacency rồi khẳng định một thứ tự là bug; thứ tự duyệt có thể thay đổi theo graph representation.

## 9. Java 17 — path vs star, DFS depth và BFS queue

Lưu file **GraphTopologyStressDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

public class GraphTopologyStressDemo {
    static final class Graph {
        final List<List<Integer>> adj;

        Graph(int n) {
            adj = new ArrayList<>();
            for (int i = 0; i < n; i++)
                adj.add(new ArrayList<>());
        }

        void edge(int u, int v) {
            adj.get(u).add(v);
            adj.get(v).add(u);
        }

        int size() { return adj.size(); }
    }

    static Graph path(int n) {
        Graph g = new Graph(n);
        for (int i = 1; i < n; i++)
            g.edge(i - 1, i);
        return g;
    }

    static Graph star(int n) {
        Graph g = new Graph(n);
        for (int i = 1; i < n; i++)
            g.edge(0, i);
        return g;
    }

    // stats[0] = visited count; stats[1] = maximum call depth.
    static void dfs(Graph g, int u, int depth,
                    boolean[] visited, int[] stats) {
        visited[u] = true;
        stats[0]++;
        stats[1] = Math.max(stats[1], depth);
        for (int v : g.adj.get(u))
            if (!visited[v])
                dfs(g, v, depth + 1, visited, stats);
    }

    // Result: [visited count, maximum queue length].
    static int[] bfs(Graph g, int start) {
        boolean[] visited = new boolean[g.size()];
        ArrayDeque<Integer> q = new ArrayDeque<>();
        q.add(start);
        visited[start] = true;
        int count = 0, maxQueue = 0;
        while (!q.isEmpty()) {
            maxQueue = Math.max(maxQueue, q.size());
            int u = q.remove();
            count++;
            for (int v : g.adj.get(u)) {
                if (!visited[v]) {
                    visited[v] = true;
                    q.add(v);
                }
            }
        }
        return new int[] {count, maxQueue};
    }

    static int[] measure(Graph g) {
        boolean[] visited = new boolean[g.size()];
        int[] dfsStats = new int[2];
        dfs(g, 0, 1, visited, dfsStats);
        int[] bfsStats = bfs(g, 0);
        return new int[] {
            dfsStats[0], dfsStats[1],
            bfsStats[0], bfsStats[1]
        };
    }

    public static void main(String[] args) {
        int n = 15;
        int[] pathStats = measure(path(n));
        int[] starStats = measure(star(n));

        System.out.printf(
            "path reached=%d dfsMaxDepth=%d bfsMaxQueue=%d%n",
            pathStats[0], pathStats[1], pathStats[3]);
        System.out.printf(
            "star reached=%d dfsMaxDepth=%d bfsMaxQueue=%d%n",
            starStats[0], starStats[1], starStats[3]);
        System.out.println("sameReachability="
                + (pathStats[0] == pathStats[2]
                && starStats[0] == starStats[2]
                && pathStats[0] == n
                && starStats[0] == n));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 GraphTopologyStressDemo.java
java GraphTopologyStressDemo
```

Stdout:

```text
path reached=15 dfsMaxDepth=15 bfsMaxQueue=1
star reached=15 dfsMaxDepth=2 bfsMaxQueue=14
sameReachability=true
```

**Giải thích:** Trong path từ0, mỗi DFS call phát sinh một DFS call con sâu thêm một mức, đạt15. Trong star, các lá trả về ngay nên chỉ sâu2. BFS path chỉ có tối đa một node chưa xử lý; BFS star chứa 14 lá sau khi mở rộng node tâm.

**Phạm vi của code:** Để minh họa chiều sâu DFS, input cố định n=15; không cố tình gây StackOverflowError bằng graph khổng lồ. Nếu triển khai DFS trên graph rất sâu, thay recursion bằng stack lặp. `measure` yêu cầu graph có ít nhất một đỉnh; đây là hợp đồng demo, còn hệ thống chung phải xử lý n=0 riêng.

## 10. Kiểm thử xác suất không thay bộ test cấu trúc

Một chiến lược kiểm thử hiệu quả dùng **cả hai**:

1. **Structured adversarial cases:** đã tăng, đã giảm, trùng, organ-pipe, gần sorted, sawtooth, xen kẽ cực trị.
2. **Seeded randomized cases:** nhiều kích thước, nhiều giá trị trùng, âm/dương, biên n=0.
3. **Independent oracle:** ví dụ sort cần so với `Arrays.sort(copy)` và kiểm multiset/sortedness.
4. **Instrumented complexity:** số comparisons, chiều cao, độ sâu, max queue; không chỉ đúng/sai.
5. **Metamorphic properties:** sắp xếp hai lần không đổi, hoán vị input không đổi kết quả sorted, thay thứ tự chèn làm chiều cao BST thay đổi nhưng tập khóa không thay.
6. **Failure shrinking:** giảm n, loại bỏ phần tử không cần thiết để được phản ví dụ ngắn, giúp debug nhanh hơn.

### 10.1. Phân biệt oracle và bản cần kiểm

Không được “kiểm” QuickSort bằng cách gọi lại chính QuickSort ở cả hai bên. Oracle nên độc lập, ví dụ JDK `Arrays.sort` cho một thuật toán sort tự cài.

Oracle cũng phải phù hợp contract. Nếu thuật toán cần **stable sort** với cùng key, chỉ so dãy key sau sort là không đủ; cần giữ ID của các phần tử bằng nhau để so thứ tự tương đối.

### 10.2. Không benchmark bằng stdout

In ra nhiều triệu dòng hoặc log mỗi phép so sánh làm sai lệch toàn bộ benchmark. Đo counter trong bộ test complexity và đo elapsed time riêng với logging tắt. Một cải thiện độ phức tạp không cần được chứng minh bằng “máy của tôi chạy nhanh hơn trong một lần”.

## 11. Java 17 — test matrix tự động và đối chiếu Arrays.sort

Chương trình **AdversarialPropertyHarness.java** tự tạo bảy họ input cho mọi `n=0..64`, thêm 500 mảng pseudo-random có seed543, so QuickSort tự cài với JDK và kiểm tính idempotent.

```java
import java.util.Arrays;
import java.util.Random;

public class AdversarialPropertyHarness {
    static final class Stats {
        long comparisons;
    }

    static void swap(int[] a, int i, int j) {
        int tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    static void quick(int[] a, int lo, int hi, Stats s) {
        if (lo >= hi) return;
        int pivot = a[hi];
        int pos = lo;
        for (int j = lo; j < hi; j++) {
            s.comparisons++;
            if (a[j] <= pivot) swap(a, pos++, j);
        }
        swap(a, pos, hi);
        quick(a, lo, pos - 1, s);
        quick(a, pos + 1, hi, s);
    }

    static int[][] patterns(int n) {
        int[][] all = new int[7][n];
        for (int i = 0; i < n; i++) {
            all[0][i] = i;                    // Sorted.
            all[1][i] = n - i;                // Reversed.
            all[2][i] = 7;                    // All equal.
            all[3][i] = i;                    // Nearly sorted.
            all[4][i] = Math.min(i, n - 1 - i); // Organ-pipe.
            all[5][i] = i % 5;                // Sawtooth.
            all[6][i] = (i % 2 == 0)
                    ? i / 2 : n - 1 - i / 2; // Alternating low/high.
        }
        if (n >= 2) {
            int mid = n / 2;
            swap(all[3], mid, mid - 1);
        }
        return all;
    }

    // Returns the comparison count of the first sort.
    static long check(int[] input) {
        int[] oracle = input.clone();
        Arrays.sort(oracle);
        int[] result = input.clone();
        Stats s = new Stats();
        quick(result, 0, result.length - 1, s);
        if (!Arrays.equals(result, oracle))
            throw new AssertionError("Differential mismatch");

        int[] twice = result.clone();
        quick(twice, 0, twice.length - 1, new Stats());
        if (!Arrays.equals(twice, result))
            throw new AssertionError("Not idempotent");
        return s.comparisons;
    }

    public static void main(String[] args) {
        int shapes = 0;
        for (int n = 0; n <= 64; n++)
            for (int[] sample : patterns(n)) {
                check(sample);
                shapes++;
            }

        Random random = new Random(543);
        int randomCases = 500;
        for (int t = 0; t < randomCases; t++) {
            int n = random.nextInt(65);
            int[] a = new int[n];
            for (int i = 0; i < n; i++)
                a[i] = random.nextInt(21) - 10;
            check(a);
        }

        int[] ordered64 = new int[64];
        for (int i = 0; i < 64; i++) ordered64[i] = i;
        long comparisons = check(ordered64);
        long worstBound = 64L * 63L / 2L;
        if (comparisons != worstBound)
            throw new AssertionError("Expected degenerate pivot");

        System.out.println("shape cases=" + shapes + " PASS");
        System.out.println("random cases=" + randomCases + " PASS");
        System.out.println("idempotence cases="
                + (shapes + randomCases) + " PASS");
        System.out.printf(
            "sorted64 comparisons=%d worstBound=%d%n",
            comparisons, worstBound);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 AdversarialPropertyHarness.java
java AdversarialPropertyHarness
```

Stdout:

```text
shape cases=455 PASS
random cases=500 PASS
idempotence cases=955 PASS
sorted64 comparisons=2016 worstBound=2016
```

**Giải thích số lượng:** Có **65 kích thước** `0..64`, **7 hình dạng** mỗi kích thước, nên `65×7=455`. Có 500 random cases. Mỗi case kiểm một lần sort và một lần sort lặp lại nên có **955 idempotence checks**. Trường hợp ordered64 được kiểm riêng sau đó, không tính trong 955.

**Sự khác nhau giữa correctness và complexity assertion:**

- Kiểm `Arrays.equals(result,oracle)` chứng minh sort đúng trên bộ case đã thử.
- Kiểm idempotence giúp phát hiện tính không ổn định đầu ra sau sort lại; nhưng một thuật toán luôn trả mảng sai cố định vẫn có thể idempotent, vì vậy idempotence **không đủ** làm oracle.
- Kiểm `comparisons==2016` là một **complexity regression guard** cho chính biến thể pivot-cuối; với một implementation đã được cải thiện, regression guard này cần đổi thành cận thích hợp, không nên giữ yêu cầu “phải kém” mãi.

## 12. Cách thiết kế assertion cho từng loại bug

### 12.1. Tính đúng sau sort

So toàn bộ kết quả với oracle. Với input có duplicate, nên kiểm cả output không thiếu/phát sinh giá trị. Việc so với `Arrays.sort` thỏa kiểm permutation và nondecreasing cùng lúc trong phạm vi số nguyên.

Nếu test stable sort các bản ghi `(key,id)`, oracle phải kiểm relative order của các ID có key bằng nhau.

### 12.2. Budget so sánh

Với Lomuto pivot-cuối, đường suy biến cho `n(n−1)/2` comparisons. Nếu bạn sửa thành một thuật toán có **cam kết worst-case O(n log n)**, hãy viết ngưỡng phù hợp với implementation, ví dụ dựa trên một cận lý thuyết hoặc đo nội bộ có tài liệu, không tùy tiện assert rằng mọi lần chạy “phải dưới 100 ms”.

### 12.3. Depth budget

Đếm `maxDepth` thực tế (hoặc chiều cao cây), không suy từ số phần tử. BST tăng dần n node với insertion không tự cân bằng có height=n. Với cây tự cân bằng, cần dựa vào bất biến AVL/Red-Black cụ thể để đặt cận; không gắn ngưỡng BST không cân bằng vào `TreeMap`.

### 12.4. Stack và heap budget

Graph path tạo depth lớn cho DFS đệ quy; star tạo queue rộng cho BFS. Cùng O(V+E) time vẫn có cấu hình bộ nhớ xấu. Kiểm riêng peak stack/queue hoặc dùng iterative traversal.

### 12.5. Phân phối công việc

Với thuật toán chia task hay chia dữ liệu, một partition có 95% công việc cũng là input đối kháng. Kiểm `maxWorkerCost`, `minWorkerCost`, số task rỗng, độ lệch và idle time; “mỗi worker có cùng số item” không bảo đảm cùng thời gian khi chi phí mỗi item khác nhau.

## 13. Biên, kiểu số nguyên và comparator

Các bug chỉ xuất hiện tại ranh giới thường đi cùng dữ liệu đã sorted:

- Loop partition `j<hi` khác `j<=hi`.
- Điều kiện dừng `lo>=hi` cần chặn recursion rỗng/singleton.
- Index từ0 nên mid an toàn thường là `lo+(hi−lo)/2` thay vì `(lo+hi)/2` để tránh overflow.
- Comparator kiểu `return a-b` có thể overflow với `Integer.MIN_VALUE`/`MAX_VALUE`; dùng `Integer.compare(a,b)`.
- Sắp xếp dữ liệu all equal dễ phát hiện loop partition không tiến (`i`, `lt`, `gt` không đổi).
- Nếu có nhiều duplicate, thuật toán set-like không được tự xóa duplicate khi contract là sort một dãy có đa tập giá trị.

Ví dụ:

`Integer.MIN_VALUE=-2147483648`, `Integer.MAX_VALUE=2147483647`.

Phép trừ `MAX_VALUE-MIN_VALUE` trong `int` overflow. Comparator có thể trả dấu sai và vi phạm hợp đồng ordering. Đây là lý do cần test cực trị chứ không chỉ nặng về độ dài.

## 14. Tính tái lập và thu nhỏ phản ví dụ

Khi phát hiện lỗi, một bản báo cáo tốt nên chứa:

- Tên thuật toán và biến thể (pivot cuối, three-way, AVL hay BST thường).
- Input chính xác hoặc generator + seed.
- Kích thước, miền giá trị và thứ tự xuất hiện.
- Kết quả expected và actual; nếu performance regression, metric/cận đã dùng.
- JVM/Java version, các cài đặt quan trọng khi benchmark.
- Phản ví dụ đã **shrink** xuống ngắn nhất có thể.

**Shrinking:** Nếu n=1.000.000 sorted gây lỗi, thử giảm n theo lũy thừa2 để tìm ngưỡng, sau đó binary-search độ dài nhỏ nhất còn lỗi. Nếu random input 1000 phần tử làm wrong answer, thử xóa từng đoạn, thu hẹp giá trị, giảm số distinct keys.

Phân biệt lỗi tính đúng với lỗi tài nguyên: một case gây `StackOverflowError` ở n rất lớn nhưng output logic đúng trên n nhỏ cần báo “resource-safety failure”, không báo “wrong answer” nếu chưa có sai kết quả.

### 14.1. Hồi quy sau khi sửa

Sau khi sửa một lỗi, giữ lại minimal reproducer như **regression test cố định**. Không chỉ tăng số random cases. Tối ưu QuickSort để chống input sorted cần thêm test sorted/descending/equal vào bộ test vĩnh viễn.

## 15. Chiến lược bộ test nhiều tầng

| Tầng | Mục đích | Ví dụ |
|---|---|---|
| Tiny exhaustive | Kiểm tất cả mảng nhỏ từ miền nhỏ | n≤6, giá trị 0/1/2 |
| Structured | Đánh vào giả định thuật toán | sorted, reversed, equal, organ-pipe |
| Differential seeded | Tìm bug khó đoán và tái lập | 500 mảng Random(543) |
| Complexity assertion | Nhận diện suy biến | n(n−1)/2 comparisons, height=n |
| Resource stress | Kiểm stack/queue, cấp phát | path dài, star rộng |
| Benchmark | Đo throughput/latency thực | warmup, repeated runs, baseline |

Không nhất thiết chạy tất cả tầng trong một unit test nhanh. Tầng resource stress lớn có thể tách thành suite riêng, chạy trong môi trường có giới hạn và giám sát; tránh làm CI thường ngày bị treo bởi intentionally worst-case input.

### 15.1. Exhaustive trên miền nhỏ

Với miền `{-1,0,1}` và n=5, có `3^5=243` mảng. Có thể duyệt tất cả để test QuickSort của bạn trên trường hợp nhỏ, gồm rất nhiều duplicate và những thứ tự lạ. Exhaustive small cases bắt bug cấu trúc tốt, nhưng **không chứng minh** hành vi khi n lớn.

### 15.2. Nguyên tắc chi phí

Một test intentionally O(n²) với n quá lớn có thể khiến test suite chạy hàng giờ hoặc gây stack overflow ngay ở hệ thống test, không giúp chẩn đoán. Dùng **đếm phép toán** trên n vừa đủ; chỉ chạy resource stress lớn khi đã dự trù giới hạn CPU/RAM/stack.

## 16. Kiểm thử các thuật toán không phải sort

### 16.1. Binary search và nhiều duplicate

Binary search trên mảng đã sorted là **đầu vào cần thiết**, không phải tình huống xấu tự thân. Nhưng nếu bài yêu cầu chỉ số **đầu tiên** của x, việc trả một vị trí bất kỳ của x có thể sai.

Ví dụ `[1,2,2,2,5]`, tìm first occurrence của 2 ⇒ đáp án1, không phải2 hoặc3. Tạo case all equal và duplicate dài để kiểm `lower_bound`/`upper_bound`, không chỉ kiểm “có tìm thấy không”.

### 16.2. Heap và priority queue

Nếu test input có nhiều priority bằng nhau, thứ tự phần tử được lấy khỏi priority queue có thể **không ổn định** nếu comparator chỉ so priority. Nếu output cần tie-break, comparator phải có khóa phụ (ID). Tập input đã sorted không tự biến heap operations thành O(n²) theo cùng lý do của QuickSort.

### 16.3. Hash table và dữ liệu lệch

Nhiều khóa có cùng hash bucket có thể tăng độ dài chain hoặc gây rehash nhiều. Cần kiểm đúng key/value và điều kiện hiệu năng của **implementation thực tế**, không suy cứng worst-case của một hash table lên mọi loại table của Java.

### 16.4. Graph/tree có hình dạng lệch

Path, star, cây hoàn hảo, cây chain, nhiều thành phần rời rạc, đỉnh có degree rất lớn là những mẫu nên có. Thuật toán DFS đệ quy, BFS theo queue và xử lý phân cấp có thể có **đỉnh điểm bộ nhớ khác nhau** trên các mẫu này.

## 17. Đo đạc đúng cách và những suy luận sai

- **Không đồng nhất wall-clock với complexity:** JIT, GC, CPU turbo, cache, I/O và contention ảnh hưởng thời gian.
- **Không lấy một sample nhỏ để ngoại suy:** O(n²) có thể vẫn rất nhanh ở n=12.
- **Không coi test pass là chứng minh đầy đủ:** Random và structured tests bổ trợ cho bất biến thuật toán, không thay thế chúng.
- **Không mặc định Arrays.sort giống implementation bạn viết:** Oracle giúp kiểm kết quả, không định nghĩa cách chọn pivot.
- **Không khẳng định randomized pivot luôn tránh mọi worst case:** nó thay phân phối xác suất trên những đầu vào không thích nghi, không tạo đảm bảo tuyệt đối cho mọi hoàn cảnh.
- **Không ép stack overflow thật để học về stack risk:** đếm depth trên input nhỏ giúp chỉ ra xu hướng mà không làm hỏng môi trường test.
- **Không bỏ test sau khi tối ưu:** Sửa QuickSort để chống duplicate có thể gây lỗi non-termination trên các mẫu khác, nên phải giữ cả structured, seeded random và small exhaustive.

## 18. Các lỗi thường gặp

1. Chỉ dùng input random đều rồi tuyên bố đã test worst case.
2. Không test sorted/reversed vì nghĩ “chúng quá dễ”.
3. Chỉ test array distinct, bỏ all equal và low-cardinality.
4. Tưởng three-way bảo đảm O(n log n) trong mọi trường hợp.
5. Pivot cuối gây phân hoạch n−1/0 trên sorted nhưng không đo comparisons.
6. Quicksort trả đúng output nên bỏ qua đệ quy sâu.
7. Cố stress n quá lớn gây StackOverflowError không kiểm soát.
8. Chọn median-of-three rồi mặc định không còn mẫu xấu.
9. Đổi pivot mà không regression test duplicate.
10. Quên trường hợp n=0,1.
11. Partition không tăng i hoặc giảm gt ở một nhánh.
12. Không giữ duplicate dù contract là multiset sorting.
13. Chỉ so nondecreasing mà không so permutation.
14. Dùng một implementation làm cả algorithm và oracle.
15. Chỉ dùng idempotence, không đối chiếu expected.
16. So output stable sort nhưng quên original ID.
17. Không chốt seed, lỗi random khó tái lập.
18. Không lưu input đã shrink sau khi sửa.
19. Coi đồng hồ 1 lần là complexity proof.
20. Test tăng dần BST thường mà suy ra TreeMap cũng suy biến.
21. Không test thứ tự insert ngược hoặc duplicate.
22. Dùng recursive height check trên cây chain khổng lồ.
23. Đo BFS queue nhưng quên đánh dấu visited khi enqueue.
24. Dùng DFS recursive cho path dài mà không kiểm depth.
25. Coi graph cùng V,E sẽ có peak memory như nhau.
26. Bỏ qua hot keys, skew và một partition quá nặng.
27. Comparator `a-b` tràn số nguyên.
28. Mid `(lo+hi)/2` có thể overflow.
29. Đặt complexity budget không gắn implementation cụ thể.
30. Giữ assertion “phải có 2016 comparisons” sau khi cải thiện pivot.
31. Chạy resource stress lớn trong unit tests mặc định.
32. Không tách correctness, resource stress và benchmark.
33. Tưởng một test adversarial có thể đại diện mọi biến thể thuật toán.
34. Coi duplicate input là invalid khi hợp đồng cho phép.
35. Chỉ test một n, bỏ biên quanh lũy thừa hai.
36. Chỉ đo mean time, không xem tail latency hoặc memory peak.
37. Không kiểm giới hạn đầu vào của test generator.
38. Không ghi số liệu, version, seed khi báo regression.
39. Bỏ qua case toàn equal vì “không có thông tin”.
40. Không đọc đề để biết cần first/last occurrence hay any occurrence.

## 19. Bài tập có đáp án

### Bài 1 — Phản ví dụ pivot cuối

Mảng `[1,2,3,4,5]` với Lomuto pivot cuối chia thế nào ở bước đầu?

**Đáp án:** Một nhánh 4 phần tử, một nhánh0; pivot5 vào vị trí cuối.

### Bài 2 — So sánh n=12

`C(12)` của chuỗi partition n−1/0?

**Đáp án:** 12×11/2=66.

### Bài 3 — So sánh n=64

**Đáp án:** 64×63/2=2016.

### Bài 4 — Cận khi n=1000

**Đáp án:** 1000×999/2=499500.

### Bài 5 — Equal keys

Vì sao Lomuto dùng `<=` có thể suy biến trên all-equal?

**Đáp án:** Mọi phần tử vào một phía, còn một nhánh dài n−1.

### Bài 6 — Three-way all-equal

Với 12 phần tử bằng nhau, số lần so sánh phần tử-với-pivot của demo?

**Đáp án:** 12.

### Bài 7 — Three-way worst case

Three-way có bảo đảm worst-case O(n log n) với pivot đầu không?

**Đáp án:** Không, pivot cực trị lặp lại có thể gây O(n²).

### Bài 8 — Random pivot

Một seed cố định giúp gì?

**Đáp án:** Tái lập chuỗi lựa chọn để debug, không bảo đảm không có case xấu.

### Bài 9 — Introsort

Vì sao introsort dùng fallback?

**Đáp án:** Tránh đệ quy/partition lệch dẫn đến trường hợp xấu kéo dài.

### Bài 10 — BST sorted

Chèn `1..15` vào BST không cân bằng cho chiều cao?

**Đáp án:** 15.

### Bài 11 — BST giảm

Chèn `15..1` thì chiều cao?

**Đáp án:** 15, chain nhánh trái.

### Bài 12 — So sánh insert

Số so sánh trong BST chain15 theo demo?

**Đáp án:** 105.

### Bài 13 — Median-first

Chèn midpoint trước với 15 khóa liên tiếp cho height?

**Đáp án:** 4.

### Bài 14 — Balanced insert comparisons

**Đáp án:** 34.

### Bài 15 — Duplicates BST

Đưa 8 khóa7 vào BST duplicate-to-right?

**Đáp án:** Chain height8.

### Bài 16 — TreeMap

Có thể dùng kết quả BST chain để kết luận Java TreeMap cũng height15?

**Đáp án:** Không, TreeMap tự cân bằng bằng Red-Black tree.

### Bài 17 — Graph path

Path n15 có DFS max depth từ đầu mút?

**Đáp án:** 15 nếu tính số lời gọi chứa node.

### Bài 18 — Graph star

Star n15, DFS từ tâm max depth?

**Đáp án:** 2.

### Bài 19 — BFS star

Peak queue length sau mở rộng tâm star n15?

**Đáp án:** 14.

### Bài 20 — BFS path

Peak queue của BFS từ đầu mút path?

**Đáp án:** 1.

### Bài 21 — Bản chất input

Hai graph path/star có cùng V,E nhưng cùng peak memory không?

**Đáp án:** Không, độ sâu DFS và queue BFS khác nhau.

### Bài 22 — Binary search

First occurrence của2 trong `[1,2,2,2,5]`?

**Đáp án:** Index1 (0-based).

### Bài 23 — Comparator

Vì sao tránh `a-b`?

**Đáp án:** Overflow int làm sai dấu so sánh.

### Bài 24 — Tính tái lập

Random(543) dùng để làm gì?

**Đáp án:** Cố định chuỗi input random để có thể lặp lại và debug.

### Bài 25 — Số structured cases

Có 7 họ dữ liệu cho n=0..64, tổng số?

**Đáp án:** 65×7=455.

### Bài 26 — Test tổng

Thêm 500 random cases vào 455 structured cases?

**Đáp án:** 955 cases.

### Bài 27 — Idempotence

`sort(sort(a))=sort(a)` có đủ để chứng minh sort đúng?

**Đáp án:** Không, một thuật toán sai có thể trả cùng kết quả sai lần hai.

### Bài 28 — Oracle

Oracle độc lập phù hợp cho primitive integer sorting trong Java?

**Đáp án:** `Arrays.sort(copy)` và kiểm đầy đủ array.

### Bài 29 — Performance

Đếm số comparisons có lợi gì so với wall-clock ở n nhỏ?

**Đáp án:** Nhận diện chính xác chuỗi partition suy biến, giảm nhiễu runtime.

### Bài 30 — Resource safety

Có cần cố gây StackOverflowError với n cực lớn để phát hiện xu hướng không?

**Đáp án:** Không; đo max depth trên n nhỏ và dùng stress lớn có giới hạn riêng.

### Bài 31 — Stress size

Nên chỉ test n=1000?

**Đáp án:** Không; test cả n=0,1,2 và các n quanh biên quan trọng.

### Bài 32 — Regression

Sau khi sửa pivot, phải giữ lại input sorted đã gây lỗi?

**Đáp án:** Có, như test hồi quy cố định.

## 20. Checklist cho bộ kiểm thử đối kháng

1. Đã đọc đúng hợp đồng input và giới hạn?
2. Đã phân biệt correctness, complexity và benchmark?
3. Có n=0, n=1 và n=2?
4. Có array sorted?
5. Có array reversed?
6. Có all equal?
7. Có low-cardinality duplicates?
8. Có nearly sorted?
9. Có organ-pipe?
10. Có sawtooth?
11. Có alternating extremes?
12. Có case với `MIN_VALUE`/`MAX_VALUE`?
13. Có kiểm comparator overflow?
14. Có kiểm mid overflow?
15. Có chọn test gắn với biến thể pivot thật?
16. Có đếm comparisons?
17. Có theo dõi partition balance?
18. Có đo max recursion depth?
19. Có so oracle độc lập?
20. Có kiểm nondecreasing và permutation?
21. Nếu stable sort, có kiểm tie order?
22. Có kiểm idempotence?
23. Có dùng seed fixed?
24. Có lưu input thất bại?
25. Có shrink phản ví dụ?
26. Có random cases ngoài structured cases?
27. Có kiểm hành vi khi nhiều duplicate?
28. Có regression test sau khi sửa?
29. Có BST insertion sorted?
30. Có BST insertion reversed?
31. Có BST duplicate policy rõ ràng?
32. Có so height chain vs balanced?
33. Có phân biệt BST thường và TreeMap tự cân bằng?
34. Có graph path dài?
35. Có graph star rộng?
36. Có đo peak BFS queue?
37. Có đo DFS recursion depth?
38. Có visited-on-enqueue khi BFS?
39. Có kiểm graph reachability cùng oracle?
40. Có tránh cố tình làm sập test bằng stack khổng lồ?
41. Có phân phối skew/hot key cho bài partition?
42. Có đặt resource/time budget trong stress riêng?
43. Có benchmark với warmup và nhiều lần đo?
44. Có loại log khỏi benchmark?
45. Có ghi JVM, thuật toán, seed và n khi báo lỗi?
46. Có nêu rõ độ phức tạp chứng minh thay vì chỉ dựa vào số test?
47. Có kiểm output đúng ngay cả khi performance xấu?
48. Có đánh giá risk tràn bộ nhớ/stack riêng?
49. Có lưu test đối kháng vào CI phù hợp?
50. Có tránh biến một regression guard của phiên bản cũ thành rào cản cải thiện thuật toán?

**Tổng kết:** Đầu vào đã có thứ tự và mất cân bằng thường không phá hợp đồng tính toán, mà phá **giả định về cấu trúc**: pivot bị chọn cực trị, cây chèn thành chain, DFS quá sâu, BFS queue quá rộng hoặc một worker có quá nhiều việc. Một bộ kiểm thử đáng tin cần kết hợp **mẫu cấu trúc có chủ đích**, **oracle độc lập**, **phép đo có giải thích** và **regression test có thể tái lập**. Đúng kết quả, đúng worst-case và chạy nhanh là ba câu hỏi khác nhau; phải kiểm riêng từng câu.
