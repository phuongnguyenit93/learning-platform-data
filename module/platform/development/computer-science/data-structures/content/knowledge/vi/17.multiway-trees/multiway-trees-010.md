# Truy vấn khoảng trên B+-tree

**Truy vấn khoảng** (*range query*) không chỉ hỏi một khóa có tồn tại hay không, mà cần lấy **tất cả mục dữ liệu có khóa nằm trong một đoạn**. Ví dụ: liệt kê đơn hàng có mã từ 2500 đến 2700, lấy giao dịch trong một khoảng thời gian, hoặc trả về 20 sản phẩm tiếp theo theo thứ tự giá. Một phép tìm chính xác chỉ trả về một mục là chưa đủ cho những nhu cầu này.

**B+ tree** (*B-plus tree*) đặc biệt phù hợp với truy vấn khoảng nhờ kết hợp hai cách di chuyển:

1. **Đi dọc cây:** Từ nút gốc, dùng khóa phân cách trong các nút trong để tìm nhanh lá có thể chứa điểm bắt đầu.
2. **Đi ngang tầng lá:** Đọc các mục đã sắp theo thứ tự, chuyển sang lá kế tiếp qua liên kết `next`, và dừng khi vượt cận trên.

Điểm quan trọng là **không phải tìm lại từ gốc sau mỗi mục hoặc mỗi lá**. Sau một lần định vị, ta có thể quét tuần tự những lá chứa dữ liệu cần lấy.

Bài này trình bày mô hình B+ tree với khóa nguyên **không trùng**, mục dữ liệu chỉ ở lá, separator của nút trong là **khóa nhỏ nhất của cây con bên phải**. Ta sẽ xét các loại biên mở/đóng, truy vết truy vấn qua nhiều tầng, mã Java tự chứa, phân trang theo khóa, phân tích CPU/I/O và các lỗi cần tránh.

## 1. Vì sao tìm kiếm chính xác không giải quyết hết bài toán?

Giả sử hệ thống lưu các mã đơn hàng:

```text
10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95
```

Hai câu hỏi khác nhau:

| Bài toán | Kết quả cần có | Đặc điểm |
| --- | --- | --- |
| Tìm mã `50` | Một mục `50` hoặc “không tồn tại” | *Point lookup* |
| Tìm mã từ `25` đến `82` | Tất cả mã trong `[25,82]`, theo thứ tự | *Range scan* |

Nếu dùng thao tác tìm chính xác nhiều lần cho từng số nguyên từ 25 đến 82, ta vừa có thể thực hiện những lượt tìm không cần thiết cho khóa vắng mặt, vừa đi lại nhiều đường từ gốc xuống lá. Nếu truy vấn theo thời gian với đơn vị mili-giây hoặc khóa kiểu chuỗi, cách liệt kê mọi giá trị trong miền còn không khả thi.

B+ tree giải quyết bằng cách **tìm một vị trí bắt đầu** rồi **duyệt các mục thực sự tồn tại**. Thời gian duyệt do số mục cần xử lý và số lá bị thăm quyết định, không do độ rộng số học của khoảng `b-a`.

## 2. Hai cấu trúc liên kết trong B+ tree

Trong B+ tree thông dụng:

- **Nút trong** có `k` separator tăng dần và `k+1` con trỏ đến nút con; nó định tuyến tìm kiếm.
- **Nút lá** chứa những mục `(khóa, giá trị)`, `(khóa, bản ghi)` hoặc `(khóa, mã vị trí bản ghi)`.
- Các lá ở **cùng độ sâu**; từng lá chứa mục đã sắp tăng theo khóa.
- Các lá thường có liên kết `next` tới lá kế tiếp, đôi khi có cả `prev` để hỗ trợ quét ngược.

Ví dụ B+ tree ba tầng:

```text
                            [40 | 70]                         tầng 0: gốc
                          /     |     \
                         /      |      \
                    [20|30]  [50|60]  [80|90]                  tầng 1: nút trong
                    /  |  \   / |  \   / |   \
                   /   |   \ /  |   \ /  |    \
Lá:           [10,15] [20,25] [30,35] [40,45] [50,55] [60,65]
                L0       L1      L2       L3      L4      L5

              [70,75] [80,85] [90,95]
                 L6      L7      L8

Chuỗi lá theo thứ tự:
L0 -> L1 -> L2 -> L3 -> L4 -> L5 -> L6 -> L7 -> L8 -> null
```

Sơ đồ trên tách dòng cho dễ đọc, nhưng tất cả chín lá `L0..L8` cùng ở **tầng 2**. Gốc có hai separator nên có ba con; mỗi nút trong tầng 1 có hai separator nên có ba con. Các mục dữ liệu chỉ nằm ở tầng lá.

**Hai loại con trỏ không giống nhau:** `children[i]` đi **xuống một nhánh tìm kiếm**; `leaf.next` đi **ngang sang lá tiếp theo theo thứ tự khóa**. Truy vấn khoảng sử dụng cả hai, nhưng tại các giai đoạn khác nhau.

### Lá giữ bản ghi hay mã bản ghi?

Với một chỉ mục phân cụm, mục tại lá có thể chứa dữ liệu bản ghi; với chỉ mục phụ, lá có thể chứa `(khóa, record_id)` và cần đọc thêm trang dữ liệu thật. Thuật toán quét B+ tree vẫn tìm các mục **ở lá** theo cùng cơ chế, nhưng số lần đọc dữ liệu ngoài chỉ mục có thể khác đáng kể.

## 3. Khóa phân cách quyết định lá bắt đầu

Trong bài, các separator được định nghĩa theo quy ước:

\[
S_i=\minKey(P_{i+1}),
\]

nghĩa là separator `S_i` bằng khóa **nhỏ nhất** ở cây con ngay bên phải. Với nút có `k` separator, nó có `k+1` con.

Ví dụ nút gốc:

```text
                           [40 | 70]
                          /    |     \
                         P0    P1     P2

P0: x < 40
P1: 40 <= x < 70
P2: x >= 70
```

Để định tuyến khóa `x`, tìm separator đầu tiên **lớn hơn hẳn** `x`, hay `upper_bound(x)`:

\[
i=\min\{j\mid S_j>x\},
\]

và đặt `i=k` khi không có separator như vậy. Chỉ số `i` chính là chỉ số `children[i]` cần đi.

| Khóa bắt đầu `x` | `upper_bound([40,70],x)` | Chọn nhánh |
| ---: | ---: | --- |
| 25 | 0 | `P0` |
| 40 | 1 | `P1` |
| 55 | 1 | `P1` |
| 70 | 2 | `P2` |
| 95 | 2 | `P2` |

**Khi khóa bằng separator, nó phải đi về nhánh phải.** Nếu tìm 40 mà đi `P0`, thuật toán sẽ tìm ở những lá có khóa nhỏ hơn 40 và có thể kết luận sai.

### Tìm vị trí trong lá bằng `lower_bound`

Sau khi tìm được lá bắt đầu, cần xác định mục đầu tiên **không nhỏ hơn cận dưới** `a`:

\[
j=\min\{r\mid leaf.keys[r]\ge a\}.
\]

Đây là `lower_bound(a)`. Nếu khóa ở vị trí `j` là `a`, ta lấy mục đó khi cận dưới **bao gồm** `a`. Nếu `a` nằm giữa hai khóa, `j` trỏ tới khóa tiếp theo lớn hơn `a`.

Nếu `j` bằng số mục của lá thì **không được đọc ngoài mảng**; thay vào đó, bắt đầu từ vị trí 0 ở `leaf.next`, nếu có.

Trong cùng một truy vấn, ta dùng hai phép so sánh khác nhau:

| Giai đoạn | Phép toán | Mục tiêu |
| --- | --- | --- |
| Nút trong | `upper_bound(a)` | Chọn cây con, xử lý đúng dấu bằng separator |
| Nút lá với cận dưới đóng | `lower_bound(a)` | Lấy mục đầu tiên `key >= a` |
| Nút lá với cận dưới mở | `upper_bound(a)` | Lấy mục đầu tiên `key > a` |
| Khi đang quét | So sánh với cận trên | Quyết định lấy mục hay dừng |

## 4. Thuật toán hai pha cho đoạn đóng `[a,b]`

Với `a\le b`, đoạn **đóng** `[a,b]` gồm mọi mục có khóa thỏa:

\[
a\le key\le b.
\]

Thuật toán cơ bản:

```text
rangeQuery(root, a, b):
    result = []
    nếu a > b hoặc root rỗng:
        return result

    # Pha 1: định vị lá theo cận dưới.
    node = root
    while node không phải lá:
        i = upperBound(node.separators, a)
        node = node.children[i]

    leaf = node
    pos = lowerBound(leaf.keys, a)

    # Pha 2: quét các lá đã liên kết.
    while leaf != null:
        while pos < leaf.keyCount:
            key = leaf.keys[pos]
            nếu key > b:
                return result

            result.add(leaf.entries[pos])
            pos = pos + 1

        leaf = leaf.next
        pos = 0

    return result
```

Điều kiện dừng `key > b` là đủ vì các khóa trong từng lá và toàn bộ chuỗi lá **tăng dần**. Một khi gặp khóa vượt cận trên, tất cả mục phía sau cũng lớn hơn `b`.

**Không cần quay lại gốc để chuyển lá.** Sau khi đọc hết một lá, chỉ cần theo `next` rồi tiếp tục từ vị trí đầu tiên của lá kế.

### Bất biến của vòng quét

Tại thời điểm bắt đầu một lần lặp bên trong:

1. Mọi mục đã được thêm vào `result` đều có khóa thuộc `[a,b]`.
2. Các mục trong `result` tăng theo khóa và chưa bị thêm trùng.
3. Mọi mục chưa được xét có thể thỏa truy vấn đều nằm từ vị trí hiện tại trở về sau trên chuỗi lá.

Khi gặp `key > b`, do các lá tăng thứ tự, không mục nào phía sau thỏa điều kiện, nên có thể dừng mà không bỏ sót kết quả.

## 5. Truy vết qua một cây ba tầng

Dùng cây ở Mục 2, truy vấn:

\[
[25,82].
\]

### Pha 1: định vị lá đầu tiên

1. Ở gốc `[40,70]`, `upper_bound(25)=0`, chọn con trái.
2. Ở nút trong `[20,30]`, `upper_bound(25)=1`, chọn con giữa.
3. Đến lá `L1=[20,25]`; `lower_bound(25)=1`.
4. Vị trí bắt đầu là **mục 25**, không cần đọc các lá trước đó.

```text
                       [40 | 70]
                           |
                         P0
                           v
                       [20 | 30]
                           |
                         P1
                           v
                       [20 | 25]
                              ^
                       bắt đầu ở 25
```

### Pha 2: quét qua liên kết lá

| Lá | Khóa được xét | Khóa được trả về |
| --- | --- | --- |
| `L1=[20,25]` | Từ vị trí của 25 | 25 |
| `L2=[30,35]` | 30, 35 | 30, 35 |
| `L3=[40,45]` | 40, 45 | 40, 45 |
| `L4=[50,55]` | 50, 55 | 50, 55 |
| `L5=[60,65]` | 60, 65 | 60, 65 |
| `L6=[70,75]` | 70, 75 | 70, 75 |
| `L7=[80,85]` | 80, **85** | 80; dừng tại 85 vì `85>82` |

Kết quả:

```text
[25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]
```

Không cần đọc các mục `10`, `15`, `20` ở phía trước cận dưới, cũng không cần quét các lá `L8=[90,95]` sau khi đã gặp `85>82`.

### Khi cận dưới không tồn tại trong cây

Truy vấn `[26,33]`:

- `26` được định tuyến đến lá `[20,25]`.
- `lower_bound(26)` trả về **hết lá**, vì cả 20 và 25 đều nhỏ hơn 26.
- Theo `next` đến lá `[30,35]`, lấy `30`.
- Gặp `35>33` thì dừng; kết quả `[30]`.

**Sai lầm phổ biến:** kết luận không có kết quả khi cận dưới `26` không phải một khóa hiện hữu. Cận dưới là **ranh giới tìm kiếm**, không bắt buộc là phần tử của chỉ mục.

## 6. Biên mở và biên đóng

Không phải mọi truy vấn đều là đoạn đóng. Bốn kiểu thường gặp:

| Ký hiệu | Điều kiện | Khóa bằng cận dưới | Khóa bằng cận trên |
| --- | --- | --- | --- |
| `[a,b]` | `a <= key <= b` | Lấy | Lấy |
| `[a,b)` | `a <= key < b` | Lấy | Bỏ |
| `(a,b]` | `a < key <= b` | Bỏ | Lấy |
| `(a,b)` | `a < key < b` | Bỏ | Bỏ |

Khi **cận dưới mở**, vị trí bắt đầu ở lá được tìm bằng `upper_bound(a)`, tức **khóa đầu tiên lớn hơn hẳn `a`**. Khi **cận dưới đóng**, dùng `lower_bound(a)`, tức khóa đầu tiên **lớn hơn hoặc bằng `a`**.

Cận trên được xử lý khi quét:

```text
Nếu cận trên đóng:
    dừng khi key > b

Nếu cận trên mở:
    dừng khi key >= b
```

Ví dụ trên tập khóa đã cho:

| Truy vấn | Kết quả |
| --- | --- |
| `[30,70]` | `[30,35,40,45,50,55,60,65,70]` |
| `[30,70)` | `[30,35,40,45,50,55,60,65]` |
| `(30,70]` | `[35,40,45,50,55,60,65,70]` |
| `(30,70)` | `[35,40,45,50,55,60,65]` |
| `[35,35]` | `[35]` |
| `(35,35]` | `[]` |
| `[49,49]` | `[]` vì không có khóa 49 |

### Trường hợp biên cần xử lý

- Nếu `a>b`, kết quả rỗng.
- Nếu `a=b` mà **một trong hai cận mở**, khoảng rỗng.
- Nếu cây rỗng, kết quả rỗng.
- Nếu `a` nhỏ hơn mọi khóa, bắt đầu từ lá trái nhất hoặc lá mà thuật toán định tuyến tới.
- Nếu `a` lớn hơn mọi khóa, vị trí bắt đầu có thể nằm sau khóa cuối cùng; kết quả rỗng.
- Nếu `b` nhỏ hơn khóa đầu tiên được xét, dừng ngay với kết quả rỗng.

Để chuyển `(a,b]` thành `[a+1,b]` trong miền số nguyên, đôi khi người học định cộng 1 vào `a`. **Không nên làm như vậy**: khóa có thể là số thực, chuỗi, thời điểm hoặc `Integer.MAX_VALUE`; cộng 1 có thể tràn số hoặc không có ý nghĩa. Hãy xử lý trực tiếp dấu `<`, `<=` và dùng `lower_bound`/`upper_bound` phù hợp.

## 7. Truy vấn một phía và giới hạn số kết quả

Hệ thống thực tế còn dùng các dạng:

- **Từ một mốc về sau:** `key >= a`, không có cận trên.
- **Đến một mốc:** `key < b`, không có cận dưới.
- **Lấy N mục đầu tiên trong một khoảng:** `LIMIT N`.

Nếu **không có cận dưới**, ta có thể bắt đầu từ lá **trái nhất** của cây; đó là kết quả của việc liên tục chọn con `children[0]` từ gốc cho tới lá.

Nếu **không có cận trên**, quét tới khi hết chuỗi lá hoặc đủ số mục cần thiết.

Với `LIMIT N`, có thể dừng ngay khi đã thu được `N` mục, ngay cả khi chưa vượt cận trên. Điều này rất quan trọng cho giao diện hiển thị một trang dữ liệu.

Ví dụ với đoạn `[25,82]` và `LIMIT 5`:

```text
[25, 30, 35, 40, 45]
```

Thuật toán không cần tiếp tục quét tới `82` sau khi đã lấy đủ năm mục. Một giá trị `LIMIT=0` hợp lý sẽ trả về danh sách rỗng; `LIMIT` âm nên bị từ chối hoặc xử lý theo hợp đồng API rõ ràng.

## 8. Java hoàn chỉnh: quét khoảng có biên và LIMIT

Chương trình dưới đây **dựng sẵn một B+ tree hợp lệ** với ba tầng như sơ đồ ở Mục 2. Nó không cài đặt chèn/xóa, vì chủ đề bài học là **truy vấn khoảng**. Các nút trong chỉ chứa separator và con trỏ con; những mục `key:Vkey` được lưu ở lá. Các lá có liên kết `next` và `prev` để minh họa thứ tự.

API `range(from, includeFrom, to, includeTo, limit)` chấp nhận:

- `from` và `to` kiểu `Integer`; giá trị `null` nghĩa là **không có cận** phía đó.
- Hai cờ boolean quyết định cận **đóng** hay **mở**.
- `limit` là số mục nhiều nhất được trả về, phải không âm.

Việc dùng `Integer` thay vì giá trị đánh dấu như `-1` cho cận không có giúp không làm mất khả năng truy vấn các khóa âm hoặc khóa ở biên kiểu `int`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class BPlusRangeQueryDemo {
    static final class Node {
        final boolean leaf;
        final int[] keys;         // La: khoa du lieu; trong: separator.
        final String[] values;    // Chi la co gia tri.
        final Node[] children;    // Chi nut trong co con.
        Node next;
        Node prev;

        private Node(boolean leaf, int[] keys,
                     String[] values, Node[] children) {
            this.leaf = leaf;
            this.keys = keys.clone();
            this.values = values;
            this.children = children;
            for (int i = 1; i < this.keys.length; i++) {
                if (this.keys[i - 1] >= this.keys[i]) {
                    throw new IllegalArgumentException("Keys not ordered");
                }
            }
        }

        static Node leaf(int... keys) {
            if (keys.length == 0) {
                throw new IllegalArgumentException("Empty leaf");
            }
            String[] values = new String[keys.length];
            for (int i = 0; i < keys.length; i++) {
                values[i] = "V" + keys[i];
            }
            return new Node(true, keys, values, new Node[0]);
        }

        static Node internal(int[] separators, Node... children) {
            if (children.length != separators.length + 1) {
                throw new IllegalArgumentException("Need k+1 children");
            }
            for (int i = 0; i < children.length; i++) {
                if (children[i] == null) {
                    throw new IllegalArgumentException("Null child");
                }
            }
            for (int i = 0; i < separators.length; i++) {
                if (separators[i] != minKey(children[i + 1])) {
                    throw new IllegalArgumentException(
                        "Separator differs from right-subtree min"
                    );
                }
            }
            return new Node(false, separators, new String[0],
                            children.clone());
        }

        static int minKey(Node node) {
            while (!node.leaf) {
                node = node.children[0];
            }
            return node.keys[0];
        }
    }

    static final class BPlusTree {
        private final Node root;

        BPlusTree(Node root) {
            this.root = root;
        }

        // Khoa dau tien >= x; thuong dung tai la.
        private static int lowerBound(int[] keys, int x) {
            int lo = 0, hi = keys.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (keys[mid] < x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        // Khoa dau tien > x; dung de chon con o nut trong.
        private static int upperBound(int[] keys, int x) {
            int lo = 0, hi = keys.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (keys[mid] <= x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        private Node findLeaf(int x) {
            Node current = root;
            while (current != null && !current.leaf) {
                current = current.children[upperBound(current.keys, x)];
            }
            return current;
        }

        private Node leftmostLeaf() {
            Node current = root;
            while (current != null && !current.leaf) {
                current = current.children[0];
            }
            return current;
        }

        List<String> range(Integer from, boolean includeFrom,
                           Integer to, boolean includeTo, int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("Negative limit");
            }
            List<String> result = new ArrayList<>();
            if (limit == 0 || root == null) {
                return result;
            }
            if (from != null && to != null) {
                if (from > to || (from.equals(to)
                        && (!includeFrom || !includeTo))) {
                    return result;
                }
            }

            Node leaf = from == null ? leftmostLeaf() : findLeaf(from);
            int pos = from == null ? 0
                : (includeFrom
                    ? lowerBound(leaf.keys, from)
                    : upperBound(leaf.keys, from));

            while (leaf != null) {
                while (pos < leaf.keys.length) {
                    int key = leaf.keys[pos];
                    if (to != null
                            && (key > to || (!includeTo && key == to))) {
                        return result;
                    }

                    result.add(key + ":" + leaf.values[pos]);
                    if (result.size() == limit) {
                        return result;
                    }
                    pos++;
                }

                leaf = leaf.next;
                pos = 0;
            }
            return result;
        }
    }

    static BPlusTree exampleTree() {
        Node[] leaves = {
            Node.leaf(10, 15), Node.leaf(20, 25),
            Node.leaf(30, 35), Node.leaf(40, 45),
            Node.leaf(50, 55), Node.leaf(60, 65),
            Node.leaf(70, 75), Node.leaf(80, 85),
            Node.leaf(90, 95)
        };

        for (int i = 0; i < leaves.length; i++) {
            leaves[i].prev = i == 0 ? null : leaves[i - 1];
            leaves[i].next =
                i + 1 == leaves.length ? null : leaves[i + 1];
        }

        Node first = Node.internal(new int[] {20, 30},
            leaves[0], leaves[1], leaves[2]);
        Node middle = Node.internal(new int[] {50, 60},
            leaves[3], leaves[4], leaves[5]);
        Node last = Node.internal(new int[] {80, 90},
            leaves[6], leaves[7], leaves[8]);

        Node root = Node.internal(new int[] {40, 70},
            first, middle, last);
        return new BPlusTree(root);
    }

    public static void main(String[] args) {
        BPlusTree tree = exampleTree();
        int noLimit = Integer.MAX_VALUE;

        System.out.println("[25,82]: "
            + tree.range(25, true, 82, true, noLimit));
        System.out.println("(30,70): "
            + tree.range(30, false, 70, false, noLimit));
        System.out.println("[35,35]: "
            + tree.range(35, true, 35, true, noLimit));
        System.out.println("(35,35]: "
            + tree.range(35, false, 35, true, noLimit));
        System.out.println("[100,120]: "
            + tree.range(100, true, 120, true, noLimit));
        System.out.println("(-infinity,25]: "
            + tree.range(null, true, 25, true, noLimit));

        List<String> page1 = tree.range(25, true, 82, true, 5);
        List<String> page2 = tree.range(45, false, 82, true, 5);
        List<String> page3 = tree.range(70, false, 82, true, 5);
        System.out.println("Page 1: " + page1);
        System.out.println("Page 2: " + page2);
        System.out.println("Page 3: " + page3);
    }
}
```

Đầu ra dự kiến:

```text
[25,82]: [25:V25, 30:V30, 35:V35, 40:V40, 45:V45, 50:V50, 55:V55, 60:V60, 65:V65, 70:V70, 75:V75, 80:V80]
(30,70): [35:V35, 40:V40, 45:V45, 50:V50, 55:V55, 60:V60, 65:V65]
[35,35]: [35:V35]
(35,35]: []
[100,120]: []
(-infinity,25]: [10:V10, 15:V15, 20:V20, 25:V25]
Page 1: [25:V25, 30:V30, 35:V35, 40:V40, 45:V45]
Page 2: [50:V50, 55:V55, 60:V60, 65:V65, 70:V70]
Page 3: [75:V75, 80:V80]
```

### Cách đọc chương trình

| Thành phần | Tác dụng |
| --- | --- |
| `Node.leaf` | Phân biệt lá chứa mục với nút trong chứa separator |
| `Node.internal` | Kiểm tra số con bằng `k+1` và separator đúng min của cây con phải |
| `findLeaf` | Đi xuống từ gốc, dùng `upperBound` ở mọi nút trong |
| `leftmostLeaf` | Định vị lá đầu tiên khi không có cận dưới |
| `lowerBound` ở lá | Bắt đầu tại khóa `>= from` khi cận dưới đóng |
| `upperBound` ở lá | Bắt đầu tại khóa `> from` khi cận dưới mở |
| `leaf.next` | Sang lá kế tiếp mà không quay về gốc |
| `includeTo` | Quy định khi nào dừng tại cận trên |
| `limit` | Dừng sớm khi đã đủ số kết quả |
| `null` ở cận | Biểu diễn khoảng không giới hạn về phía đó |

**Giới hạn của ví dụ:** Cây được dựng sẵn, không triển khai chèn/xóa hay đảm bảo an toàn khi các nút thay đổi trong lúc quét. Constructor kiểm tra một số bất biến quan trọng như thứ tự khóa, số con và separator, nhưng **không phải bộ kiểm chứng toàn diện** cho mọi cây B+ tree tùy ý (chưa kiểm tra độ sâu lá, mọi khoảng cây con và chuỗi lá theo cấu trúc cây). Các giả định đó được bảo đảm bằng cách dựng mẫu cụ thể.

## 9. Phân trang theo khóa thay vì OFFSET

Đối với API trả về nhiều kết quả, có thể tách một truy vấn khoảng thành các trang nhỏ:

```text
GET /orders?from=25&to=82&limit=5

Trang 1: 25, 30, 35, 40, 45
Trang 2: 50, 55, 60, 65, 70
Trang 3: 75, 80
```

Cách thông dụng là **phân trang theo khóa** (*keyset pagination*):

1. Trang đầu chạy `key >= 25` và `key <= 82`, `LIMIT 5`.
2. Ghi nhớ **khóa cuối trang**, ở đây `lastKey=45`.
3. Trang sau chạy `key > 45` và `key <= 82`, `LIMIT 5`.
4. Lặp lại với `lastKey=70` rồi nhận `75,80`.

Ví dụ Java ở Mục 8 dùng trực tiếp `range(45, false, 82, true, 5)` cho trang 2. Dùng **cận dưới mở** tại khóa cuối trang trước sẽ tránh trả lại khóa `45` ở đầu trang sau.

### Vì sao không chỉ dùng OFFSET?

Với `OFFSET 100000 LIMIT 20`, tùy hệ thống và kế hoạch truy vấn, bộ máy có thể phải bỏ qua rất nhiều mục trước khi trả 20 mục cuối. Với keyset pagination, một B+ tree có thể tìm vị trí bắt đầu theo `lastKey` rồi lấy tiếp một nhóm nhỏ.

Nhưng cần phân biệt:

- **Dữ liệu tĩnh và khóa duy nhất:** keyset pagination theo một khóa là trực tiếp.
- **Khóa trùng:** cursor cần khóa thứ tự đủ duy nhất, ví dụ bộ `(created_at, order_id)`; chỉ nhớ `created_at` có thể bỏ sót bản ghi cùng thời điểm.
- **Dữ liệu bị sửa giữa hai trang:** ngay cả phân trang theo khóa vẫn có thể nhìn thấy mục mới hoặc bỏ qua mục vừa đổi khóa, nếu không có snapshot hoặc chính sách nhất quán.

Một hệ thống sản xuất có thể dùng snapshot transaction, MVCC, hoặc một token cursor gắn thêm thông tin phiên bản. Bài chỉ minh họa **đường quét có thứ tự trong một cấu trúc tĩnh**.

## 10. Quét ngược và liên kết `prev`

Một số B+ tree hỗ trợ `prev` bên cạnh `next`:

```text
null <- [10,15] <-> [20,25] <-> [30,35] <-> ... <-> [90,95] -> null
```

Nếu muốn lấy các mục theo thứ tự **giảm dần** trong `[a,b]`, có thể:

1. Định vị lá có thể chứa cận **trên** `b`.
2. Tìm vị trí **khóa cuối cùng `<= b`** nếu cận trên đóng, hoặc **`< b`** nếu cận trên mở.
3. Duyệt các mục trong lá từ phải sang trái.
4. Khi đi hết lá, theo `prev` sang lá trước và bắt đầu từ khóa cuối của lá đó.
5. Dừng khi gặp khóa nhỏ hơn cận dưới (hoặc bằng cận dưới nếu cận dưới mở).

Để xác định vị trí bắt đầu:

| Cận trên | Vị trí mục cuối được phép |
| --- | --- |
| `key <= b` | `upper_bound(b) - 1` |
| `key < b` | `lower_bound(b) - 1` |

Nếu chỉ số tính được bằng `-1`, lá hiện tại không có khóa phù hợp trước cận trên; chuyển sang `prev`. **Không** đọc `keys[-1]`.

Nếu chưa có liên kết `prev`, vẫn có thể duyệt ngược bằng cách quay lên cây hoặc giữ đường đi của một iterator, nhưng cách triển khai khác. Không phải mọi B+ tree đều bắt buộc có liên kết lá hai chiều.

## 11. Độ phức tạp CPU và số lần truy cập trang

Gọi:

- `n`: tổng số **mục dữ liệu ở lá**.
- `F`: số nhánh hiệu dụng của nút trong (*fan-out*), thường lớn hơn 2.
- `L`: số mục lá điển hình trên một trang, với mức lấp đầy được duy trì.
- `h`: số cạnh từ gốc đến lá.
- `r`: số mục **thực sự được trả về** của truy vấn, sau khi áp dụng `LIMIT` nếu có.

Khi cây cân bằng và các nút đáp ứng điều kiện mức lấp đầy phù hợp:

\[
h=O(\log_F n)
\]

theo mô hình phân nhánh hiệu dụng `F`. Truy vấn gồm **một đường tìm từ gốc xuống lá**, sau đó **một đoạn quét lá liên tiếp**.

### Chi phí xử lý trong RAM

Nếu tìm nhị phân trong các nút:

- Chọn nhánh ở một nút trong có `k` separator: O(log(`k+1`)) phép so sánh.
- Định vị lá bắt đầu: O(`h \log F`) theo mô hình nút có số khóa cùng bậc với `F`.
- Quét và xuất `r` mục: O(r) bước xử lý mục, cộng chi phí đọc một phần của lá bắt đầu và lá kết thúc.

Khi sức chứa nút **cố định**, thời gian thông thường cho truy vấn khoảng là:

\[
\boxed{O(\log n+r)}.
\]

Nếu `r=0`, thuật toán vẫn thường phải tìm từ gốc xuống lá để xác định không có mục nào trong khoảng, trừ khi có thể kết luận rỗng từ điều kiện biên ngay đầu vào.

### Chi phí trong mô hình trang lưu trữ

Nếu mỗi nút là một trang và mỗi lá chứa khoảng `L` mục ở mức lấp đầy tương đối ổn định, chi phí tiếp cận trang có thể được ước lượng:

\[
O\left(h+\left\lceil\frac{r}{L}\right\rceil+1\right).
\]

Đây là **mô hình lý tưởng có điều kiện**: một số lá ở hai đầu chỉ cung cấp ít kết quả, còn phần giữa được quét liên tiếp. Khi lá có cận lấp đầy là một tỷ lệ `\alpha L`, số lá chứa `r` mục phù hợp có thể được chặn ở bậc O(`r/(\alpha L)+1`). Nếu không có bảo đảm về mức lấp đầy, không nên tự dùng chính xác `ceil(r/L)` làm số trang tuyệt đối.

| Thành phần | Mức chi phí |
| --- | --- |
| Đọc đường từ gốc tới lá đầu | Xấp xỉ `h+1` nút logic |
| Quét liên tiếp nhiều lá | Tỷ lệ với số lá thực sự chứa/bao quanh khoảng kết quả |
| Xuất `r` mục | Ít nhất Ω(r) nếu phải vật hóa từng mục |
| Tách dữ liệu thật khỏi chỉ mục | Có thể thêm truy cập trang bản ghi ngoài B+ tree |
| Cache đã giữ sẵn trang | Không nhất thiết phát sinh I/O thiết bị cho mỗi nút |

Vì vậy, **độ phức tạp phép so sánh CPU** và **số trang cần truy cập** là hai đại lượng khác nhau. B+ tree thường đặc biệt mạnh trong môi trường phân trang vì có fan-out lớn và chuỗi lá thuận lợi cho đọc tuần tự.

### So với hai cách tổ chức khác

| Cấu trúc | Tìm một khóa | Truy vấn khoảng |
| --- | --- | --- |
| Mảng đã sắp | O(log n) bằng tìm nhị phân | O(log n+r) bằng tìm điểm đầu rồi quét mảng |
| Cây tìm kiếm nhị phân cân bằng | O(log n) | O(log n+r) bằng duyệt theo thứ tự thích hợp |
| B+ tree cân bằng | O(log n) theo cấu hình nút cố định | O(log n+r), đồng thời thường thuận lợi về số trang và quét lá |
| Bảng băm thông dụng | Trung bình O(1) cho tìm chính xác | Không hỗ trợ trực tiếp thứ tự; có thể phải quét/sắp thêm |

Đây là so sánh **khả năng và bậc chi phí**, không phải tuyên bố B+ tree luôn nhanh nhất. Mảng đã sắp có thể rất hiệu quả cho dữ liệu gần như chỉ đọc; B+ tree được chọn nhiều khi cần **cập nhật động**, tìm theo khóa và quét khoảng có thứ tự trên tập lớn.

## 12. Những vấn đề khi cây được cập nhật trong lúc quét

Ở ví dụ Java, cây không thay đổi khi `range` đang chạy. Một hệ thống thực tế có thể vừa quét vừa có thao tác chèn hoặc xóa. Khi đó:

- **Tách lá:** một lá mới được chèn vào chuỗi `next`. Nếu iterator giữ liên kết cũ hoặc đọc nửa chừng, có thể bỏ sót mục.
- **Gộp lá:** một lá bị loại khỏi cây; iterator đang trỏ vào nó cần quy tắc hợp lệ.
- **Đổi separator:** định tuyến cho một lần tìm mới có thể khác trước; truy vấn nhiều trang cần ngữ nghĩa nhìn thấy dữ liệu nhất quán.
- **Cập nhật khóa:** một bản ghi có thể chuyển từ vị trí này sang vị trí khác trong thứ tự, gây nguy cơ thấy lặp hoặc bị bỏ qua nếu không có cơ chế quản lý.

Giải pháp tùy hệ thống: khóa trang phù hợp, **latch coupling**, cấu trúc B-link tree, MVCC/snapshot, phiên bản hóa cursor hoặc cơ chế phục hồi. Không cần cài đặt các kỹ thuật này để hiểu thuật toán quét **trên B+ tree tĩnh**, nhưng phải nhận ra rằng con trỏ lá không tự bảo đảm tính đúng đắn khi có nhiều người cập nhật đồng thời.

### Sau tách/gộp phải giữ các bất biến nào?

Đối với một B+ tree sử dụng `separator=minKey(cây con phải)`, cần kiểm tra:

1. Separator của các nút trong vẫn đúng giá trị min cây con phải.
2. Nút trong có đúng `k+1` con với `k` separator.
3. Các lá vẫn ở cùng độ sâu, các mục trong lá đã sắp tăng.
4. Chuỗi `next` đi qua tất cả lá **đúng một lần, đúng thứ tự**.
5. Nếu có `prev`, liên kết xuôi/ngược tương thích.
6. Các mục không bị mất hoặc nhân đôi khi tách/gộp; khóa dữ liệu không bị nhầm thành bản sao separator.

Truy vấn khoảng là bài kiểm thử rất hữu ích cho chất lượng liên kết lá: một cây có thể trả lời đúng `get(key)` nhưng vẫn trả thiếu mục khi `next` bị đứt.

## 13. Các sai lầm phổ biến

1. **Duyệt tất cả các lá từ đầu cây cho mọi truy vấn.** Điều này bỏ qua lợi thế định vị cận dưới bằng nút trong.
2. **Tìm lại từ gốc sau khi đọc hết mỗi lá.** Liên kết `next` có thể dẫn trực tiếp tới lá kế tiếp.
3. **Cho khóa bằng separator đi sang trái.** Trong quy ước `separator=minKey(right)`, dấu bằng thuộc nhánh phải.
4. **Tìm thấy separator thì kết thúc như tìm được bản ghi.** Mục dữ liệu của B+ tree thông dụng nằm ở tầng lá.
5. **Dùng `lower_bound` ở nút trong dù định tuyến theo min nhánh phải.** Trường hợp bằng separator có thể chọn sai con.
6. **Đòi hỏi cận dưới phải tồn tại như một khóa.** `[26,33]` vẫn có thể trả mục `30` dù không có `26`.
7. **Dừng khi hết khóa trong lá bắt đầu.** Phải sang `next`; khóa hợp lệ có thể ở lá tiếp theo.
8. **Đọc `keys[keyCount]` khi `lower_bound` trả về cuối mảng.** Đây là vị trí trống; phải kiểm tra giới hạn.
9. **Nhầm dấu dừng của cận trên đóng và mở.** Đóng dừng khi `key>b`; mở dừng khi `key>=b`.
10. **Dùng `a+1` để mô phỏng cận dưới mở.** Không an toàn với khóa liên tục, chuỗi hoặc số nguyên cực đại.
11. **Không kiểm tra `a>b` hoặc khoảng rỗng.** Có thể đi tìm vô ích hoặc trả sai mục.
12. **Không dừng ở LIMIT.** Tốn thêm CPU/trang và có thể vi phạm yêu cầu số kết quả tối đa.
13. **Phân trang tiếp theo với `key>=lastKey`.** Khóa cuối trang trước sẽ bị lặp; với khóa duy nhất phải dùng `key>lastKey`.
14. **Dùng khóa không duy nhất làm cursor mà không có khóa phụ.** Có thể bỏ sót những bản ghi trùng khóa.
15. **Coi số mục trả về bằng độ dài số học của khoảng.** Chỉ các khóa thực sự có trong cây mới được trả về.
16. **Coi mỗi nút được thăm là một lần đọc đĩa chắc chắn.** Bộ nhớ đệm có thể tránh I/O vật lý.
17. **Cho rằng quét `r` mục luôn cần đúng `ceil(r/L)` lá.** Hai lá biên có thể chỉ cho ít mục; mức đầy thực tế quyết định số lá.
18. **Quên cập nhật liên kết lá khi tách/gộp.** Tìm chính xác có thể vẫn đúng nhưng truy vấn khoảng bị thiếu/lặp dữ liệu.

## 14. Tự kiểm tra

**Câu 1.** Hai giai đoạn cơ bản của truy vấn khoảng trên B+ tree là gì?

**Đáp án:** Đi từ gốc xuống để xác định lá bắt đầu, rồi quét các mục và các lá liên tiếp qua `next` cho đến khi vượt cận trên hoặc đủ LIMIT.

**Câu 2.** Với nút trong `[40|70]` và quy ước separator bằng min của cây con phải, tìm cận dưới `70` phải chọn con nào?

**Đáp án:** `P2`, vì `upper_bound(70)=2` và dấu bằng thuộc nhánh phải.

**Câu 3.** Trong một lá `[20,25]`, `lower_bound(26)` trả về vị trí nào và thuật toán quét khoảng cần làm gì?

**Đáp án:** Trả về `2`, bằng số khóa trong lá. Thuật toán không đọc `keys[2]` mà sang lá `next` để tiếp tục.

**Câu 4.** Trên cây ví dụ, truy vấn `[25,82]` bắt đầu ở lá nào?

**Đáp án:** Lá `L1=[20,25]`, tại vị trí khóa 25. Đường đi là `[40,70] -> [20,30] -> [20,25]`.

**Câu 5.** Kết quả của `[26,33]` trên cây ví dụ là gì? Cận dưới `26` có nhất thiết phải có trong cây không?

**Đáp án:** `[30]`. Cận dưới không cần tồn tại như một khóa.

**Câu 6.** Khác biệt giữa `[30,70]` và `(30,70)` là gì?

**Đáp án:** Đoạn đóng gồm cả 30 và 70; đoạn mở loại cả hai cận. Trong tập ví dụ, `(30,70)` trả `[35,40,45,50,55,60,65]`.

**Câu 7.** Với cận dưới mở `(a,...`, nên lấy vị trí đầu ở lá bằng phép nào?

**Đáp án:** `upper_bound(a)`, tức khóa đầu tiên **lớn hơn hẳn `a`**.

**Câu 8.** Với cận trên mở `... , b)`, phải dừng khi gặp khóa thỏa điều kiện gì?

**Đáp án:** Dừng khi `key>=b`. Với cận trên đóng, chỉ dừng khi `key>b`.

**Câu 9.** Khi `a=b` và cận dưới mở nhưng cận trên đóng, kết quả là gì?

**Đáp án:** Rỗng, vì không giá trị nào đồng thời lớn hơn `a` và nhỏ hơn hoặc bằng chính `a`.

**Câu 10.** Với `LIMIT 5`, truy vấn `[25,82]` trên tập ví dụ trả năm khóa đầu nào?

**Đáp án:** `[25,30,35,40,45]`.

**Câu 11.** Trang đầu kết thúc ở khóa 45. Để lấy trang kế tiếp mà không lặp 45, cận dưới mới nên là gì?

**Đáp án:** Dùng **`key>45`** (cận dưới mở), giữ cận trên `key<=82` nếu truy vấn ban đầu là `[25,82]`.

**Câu 12.** Vì sao chỉ lưu `created_at` làm cursor có thể sai nếu nhiều bản ghi có cùng thời điểm?

**Đáp án:** Khóa không duy nhất; nếu trang kết thúc giữa một nhóm cùng `created_at`, điều kiện `created_at>lastTime` sẽ bỏ sót các bản ghi cùng thời điểm còn lại. Nên dùng khóa ghép đủ duy nhất, như `(created_at,id)`.

**Câu 13.** Khi không có cận dưới, thuật toán có thể lấy lá bắt đầu bằng cách nào?

**Đáp án:** Từ gốc luôn chọn con đầu tiên `children[0]` cho tới lá trái nhất, rồi quét qua `next`.

**Câu 14.** Nếu có liên kết `prev`, quét ngược với cận trên đóng `b` bắt đầu ở vị trí khóa nào trong lá tìm được?

**Đáp án:** Ở chỉ số `upper_bound(b)-1`, tức khóa cuối cùng nhỏ hơn hoặc bằng `b`. Nếu kết quả là `-1`, chuyển sang lá trước.

**Câu 15.** Vì sao kết quả truy vấn khoảng thường có độ phức tạp O(log n+r) khi sức chứa nút cố định?

**Đáp án:** Tìm điểm đầu mất O(log n) trên cây cân bằng; xử lý `r` mục theo thứ tự qua các lá mất O(r) cộng hằng số cho các biên.

**Câu 16.** Công thức xấp xỉ số trang lá `ceil(r/L)` có phải luôn chính xác không?

**Đáp án:** Không. Lá đầu và lá cuối có thể chỉ chứa một phần mục phù hợp, mức đầy thực tế khác nhau, và có thể phải thăm thêm một lá để xác định đã vượt cận trên.

**Câu 17.** Có thể vì sao một `get(50)` đúng trong khi truy vấn khoảng `[40,60]` trả thiếu mục 50?

**Đáp án:** Định tuyến từ gốc tới lá chứa 50 vẫn đúng, nhưng liên kết `next` giữa các lá có thể bị đứt hoặc đi sai thứ tự, khiến quét khoảng bỏ qua lá đó.

**Câu 18.** Khi B+ tree đang bị chèn/xóa đồng thời với range scan, chỉ có con trỏ `next` có đủ bảo đảm kết quả nhất quán không?

**Đáp án:** Không. Cần chính sách đồng thời hoặc snapshot phù hợp để tránh bỏ sót, đọc lặp hoặc nhìn thấy trạng thái trung gian khi tách/gộp.

**Câu 19.** Khi lá chứa `record_id` thay vì bản ghi thật, bước lấy kết quả khoảng có thể cần thêm công việc gì?

**Đáp án:** Sau khi quét được các mục `(key,record_id)`, hệ thống có thể phải truy xuất bản ghi thật ở vùng dữ liệu riêng; chi phí phụ thuộc tính cục bộ dữ liệu và cache.

**Câu 20.** Trong mã Java, vì sao tham số cận được khai báo `Integer` thay vì dùng giá trị đặc biệt như `-1` để biểu thị không có cận?

**Đáp án:** `null` cho phép biểu diễn cận không giới hạn mà không đánh mất một giá trị khóa nguyên hợp lệ, kể cả khóa âm hoặc giá trị cực đại/cực tiểu của `int`.

**Điểm ghi nhớ:** Truy vấn khoảng trên B+ tree gồm **tìm nhanh lá bắt đầu từ nút gốc** rồi **quét tuần tự các lá qua `next`**. Với separator bằng khóa nhỏ nhất của cây con phải, chọn nhánh bằng `upper_bound`; tại lá, dùng `lower_bound` hay `upper_bound` theo cận dưới đóng/mở. Dừng đúng khi vượt cận trên hoặc đủ LIMIT. Trên cây cân bằng có sức chứa nút cố định, chi phí thường là **O(log n+r)** với `r` mục trả về; lợi ích quan trọng trong hệ thống lưu theo trang là giảm việc đi lại qua gốc và hỗ trợ quét lá liên tiếp.
