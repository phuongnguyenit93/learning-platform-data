# Tìm kiếm khóa trong một nút và chọn nhánh con

Ở cây tìm kiếm nhị phân, mỗi nút chứa một khóa và thuật toán chỉ cần chọn nhánh **trái** hoặc **phải**. Trong cây tìm kiếm **nhiều nhánh** (*multiway search tree*) như **B-tree**, một nút có thể chứa nhiều khóa đã sắp xếp và nhiều con trỏ con. Khi tìm một giá trị, câu hỏi quan trọng không chỉ là “khóa có nằm ở đây không?” mà còn là **“nếu chưa có, phải đi theo nhánh con nào?”**.

Chọn sai chỉ số nhánh dù chỉ lệch một đơn vị có thể khiến thuật toán kết luận “không tồn tại” đối với một khóa thực sự có trong cây. Ngược lại, một quy tắc tìm kiếm nhất quán sẽ giúp loại bỏ tất cả những cây con không thể chứa khóa đang tìm ngay sau khi xử lý một nút.

Bài này xây dựng quy tắc chọn nhánh từ bất biến sắp xếp, trình bày cách tìm tuyến tính và tìm nhị phân bên trong nút, mô phỏng những đường đi thành công/thất bại, cài đặt Java hoàn chỉnh và phân biệt điều kiện **bằng khóa phân cách** trong B-tree với B+ tree.

## 1. Một nút trong B-tree chứa khóa và con trỏ thế nào?

Xét mô hình **B-tree lưu các khóa phân biệt**, trong đó một khóa có thể xuất hiện tại nút trong hoặc nút lá. Một nút trong giữ `k` khóa tăng nghiêm ngặt:

\[
K_0<K_1<\cdots<K_{k-1},
\]

và có **chính xác `k+1` con trỏ con**:

\[
P_0,P_1,\ldots,P_k.
\]

Các khóa là **ranh giới giữa các miền giá trị**; các con trỏ dẫn tới các cây con thuộc từng miền:

```text
                        [20 | 40 | 60]
                       /     |    |     \
                      P0     P1   P2     P3

    P0: x < 20
    P1: 20 < x < 40
    P2: 40 < x < 60
    P3: x > 60
```

Một nút có ba khóa tạo **bốn khoảng**. Đó là lý do nút trong cần bốn con, chứ không phải ba con. Với một nút có `k` khóa, số khoảng luôn là `k+1`.

| Vị trí nhánh | Điều kiện đối với khóa `x`, khi chưa bằng khóa ở nút |
| --- | --- |
| `P0` | `x < K0` |
| `Pi`, `1 <= i < k` | `K{i-1} < x < Ki` |
| `Pk` | `x > K{k-1}` |

Trong một B-tree hợp lệ, mọi khóa trong **toàn bộ cây con** `Pi` phải tuân theo khoảng tương ứng, kể cả những khóa nằm sâu nhiều tầng dưới nút cha. Đây là **bất biến khoảng khóa** (*key-range invariant*), không chỉ là quy tắc sắp xếp các khóa trong một nút.

**Phân biệt hai loại nút:** một **nút trong** có các con trỏ đi xuống; một **nút lá** (*leaf*) không có con. Nút lá vẫn có thể chứa nhiều khóa để tìm trực tiếp, nhưng khi không tìm thấy trong lá thì kết luận **không có khóa** — không được truy cập một con trỏ không tồn tại.

## 2. Bài toán cốt lõi: tìm vị trí đầu tiên không nhỏ hơn khóa cần tìm

Cho mảng khóa đã sắp của một nút:

```text
keys = [20, 40, 60]
index   0   1   2
```

Khi tìm khóa `x`, ta cần chỉ số:

\[
i=\min\{j\mid 0\le j<k,\ K_j\ge x\}.
\]

Nếu không có khóa nào trong nút lớn hơn hoặc bằng `x`, ta đặt `i=k`. Quy tắc này chính là **`lower_bound(x)`**, tức **vị trí đầu tiên có khóa không nhỏ hơn `x`** (*first key greater than or equal to x*).

Sau khi xác định `i`, thuật toán B-tree phân thành ba trường hợp:

1. Nếu `i < k` và `K_i=x`: **tìm thấy ngay tại nút hiện tại**.
2. Nếu không bằng và nút là **lá**: **khóa không tồn tại trong cây**.
3. Nếu không bằng và nút là **nút trong**: **đi xuống `children[i]`**.

Điểm quan trọng là **cùng một chỉ số `i`** vừa chỉ vị trí đầu tiên có khóa không nhỏ hơn `x`, vừa xác định **nhánh con cần đi xuống nếu không tìm thấy khóa tại nút**.

### Bảng ví dụ với `[20, 40, 60]`

| Khóa cần tìm `x` | `lower_bound(x)` | Kiểm tra tại nút | Quyết định nếu là nút trong |
| ---: | ---: | --- | --- |
| 5 | 0 | `20 != 5` | Đi `P0` |
| 20 | 0 | `20 == 20` | **Tìm thấy**, không đi xuống |
| 25 | 1 | `40 != 25` | Đi `P1` |
| 40 | 1 | `40 == 40` | **Tìm thấy** |
| 50 | 2 | `60 != 50` | Đi `P2` |
| 60 | 2 | `60 == 60` | **Tìm thấy** |
| 75 | 3 | `i == k` | Đi `P3` |

Trường hợp `i=k` cần được xử lý đặc biệt: **không được đọc `keys[k]`**, vì khóa cuối nằm ở `keys[k-1]`. Tuy nhiên, nếu là nút trong hợp lệ thì **`children[k]` tồn tại**; đó là nhánh ngoài cùng bên phải.

### Một cách hiểu bằng phép đếm

Khi không tìm thấy khóa `x` tại nút, `i` cũng là **số khóa trong nút nhỏ hơn `x`**. Nếu không có khóa nào nhỏ hơn `x` thì `i=0`, chọn nhánh trái nhất. Nếu cả `k` khóa đều nhỏ hơn `x` thì `i=k`, chọn nhánh phải nhất.

Như vậy, có thể xác định nhánh bằng việc đếm bao nhiêu khóa phân cách đứng trước `x`. Tìm nhị phân chỉ là cách thực hiện việc đếm đó hiệu quả hơn với nút lớn.

## 3. Truy vết tìm kiếm trên một cây cụ thể

Xét B-tree nhỏ sau (các khóa đều phân biệt):

```text
                             [20 | 40 | 60]
                            /      |      |      \
                           /       |      |       \
                       [5,10]  [25,30] [45,50] [70,80]
                         P0       P1      P2      P3

Gốc chứa 3 khóa, 4 con.
Các lá cùng độ sâu và chứa các khóa đúng khoảng.
```

### Ví dụ A: tìm khóa `50`

1. Đọc gốc `[20, 40, 60]`.
2. `lower_bound(50)=2`, vì `60` là khóa đầu tiên không nhỏ hơn 50.
3. `60 != 50`, nên đi theo **`P2`**, miền `40 < x < 60`.
4. Đọc lá `[45, 50]`. Tại đây, `lower_bound(50)=1` và `keys[1]=50`.
5. **Trả về tìm thấy**. Thuật toán đã thăm **2 nút**.

```text
[20 | 40 | 60] --P2--> [45 | 50]
                               ^
                            tìm thấy 50
```

### Ví dụ B: tìm khóa `35` không có trong cây

1. Ở gốc `[20, 40, 60]`, `lower_bound(35)=1`.
2. `40 != 35`; đi xuống **`P1`** vì `20 < 35 < 40`.
3. Đến lá `[25, 30]`. `lower_bound(35)=2` bằng số khóa của lá.
4. Lá không có con và không chứa `35`. **Trả về không tìm thấy** sau 2 nút.

Lưu ý rằng thuật toán **không đi qua `P2` hay `P3`** để tìm tiếp. Bất biến khoảng khóa bảo đảm các nhánh đó không thể chứa `35`.

### Ví dụ C: tìm khóa `60` ngay ở nút trong

Ở gốc, `lower_bound(60)=2` và `keys[2]=60`, nên tìm thấy ngay; không cần đọc bất kỳ lá nào. Với mô hình B-tree bài này, **khóa có thể là dữ liệu của chính nút trong**.

### Ví dụ D: tìm khóa ngoài mọi khoảng giữa

Tìm `100`: `lower_bound(100)=3`, đi `P3` tới lá `[70, 80]` rồi kết luận không thấy. Tìm `-5`: `lower_bound(-5)=0`, đi `P0` tới lá `[5, 10]` rồi kết luận không thấy.

Tóm tắt:

| Khóa cần tìm | Nhánh từ gốc | Nút cuối được kiểm tra | Kết quả | Số nút thăm |
| ---: | --- | --- | --- | ---: |
| 50 | `P2` | `[45, 50]` | Có | 2 |
| 35 | `P1` | `[25, 30]` | Không | 2 |
| 60 | Không cần đi xuống | Gốc `[20, 40, 60]` | Có | 1 |
| 100 | `P3` | `[70, 80]` | Không | 2 |
| -5 | `P0` | `[5, 10]` | Không | 2 |

## 4. Tìm tuyến tính trong nút và tìm nhị phân trong nút

Các khóa trong một nút được sắp sẵn, nên có hai cách xác định `lower_bound(x)`.

### 4.1. Quét tuyến tính

```text
lowerBoundLinear(keys, k, x):
    i = 0
    while i < k and keys[i] < x:
        i = i + 1
    return i
```

Thuật toán chạy từ khóa đầu tiên, dừng ở khóa đầu tiên `>= x` hoặc ở cuối mảng. Nó có chi phí **O(k)** so sánh trong trường hợp xấu nhất với một nút chứa `k` khóa.

Đặc điểm: đơn giản, dễ kiểm tra, và đôi khi có lợi về chi phí hằng số khi một nút chỉ có rất ít khóa.

### 4.2. Tìm nhị phân `lower_bound`

```text
lowerBoundBinary(keys, k, x):
    lo = 0
    hi = k             # khoảng tìm kiếm nửa mở [lo, hi)

    while lo < hi:
        mid = lo + (hi - lo) // 2
        if keys[mid] < x:
            lo = mid + 1
        else:
            hi = mid

    return lo
```

Tìm nhị phân duy trì một **khoảng chỉ số nửa mở** `[lo, hi)`. Khi `keys[mid] < x`, tất cả khóa đến `mid` đều nhỏ hơn `x` và bị loại; nếu không, vị trí đáp án chưa thể nằm sau `mid`, nên hạ `hi` xuống `mid`.

Sau vòng lặp, `lo == hi` và là chỉ số đầu tiên có khóa `>=x`, hoặc `k` nếu không có. Độ phức tạp tìm trong nút là **O(log(k+1))** phép so sánh.

### So sánh hai cách

| Tiêu chí | Quét tuyến tính | Tìm nhị phân |
| --- | --- | --- |
| Đầu vào | Mảng `k` khóa tăng | Mảng `k` khóa tăng |
| Chỉ số trả về | `0..k` | `0..k` |
| Chi phí trường hợp xấu | O(k) | O(log(k+1)) |
| Cài đặt | Dễ và ngắn | Cần xử lý biên vòng lặp cẩn thận |
| Nút rất nhỏ | Có thể đủ hiệu quả | Có thể không hơn rõ về thời gian thực |
| Nút nhiều khóa | Có thể so sánh nhiều lần | Thường giảm số phép so sánh |

Trong thực tế, hiệu năng CPU còn phụ thuộc tính cục bộ bộ nhớ, dự đoán nhánh, cách biểu diễn khóa và độ dài khóa. Big-O là nền tảng phân tích, **không đủ để khẳng định một cách tìm luôn nhanh hơn trên mọi phần cứng và kích thước nút**.

## 5. Thuật toán tìm kiếm toàn cây theo mô hình B-tree

Từ thao tác tìm trong một nút, ta xây dựng tìm kiếm toàn cây. Giả sử mỗi nút lưu `keys[0..k-1]` và, nếu không phải lá, có `children[0..k]`.

```text
contains(root, x):
    current = root

    while current != null:
        i = lowerBound(current.keys, current.keyCount, x)

        if i < current.keyCount and current.keys[i] == x:
            return true

        if current.isLeaf:
            return false

        current = current.children[i]

    return false         # cây rỗng
```

### Vì sao thuật toán đúng?

Có thể chứng minh theo **bất biến đường tìm kiếm**:

> Trước mỗi lần kiểm tra nút `current`, nếu `x` có trong cây thì nó phải nằm ở nút `current` hoặc trong một cây con của nút này.

Ban đầu, `current=root` nên điều kiện hiển nhiên đúng. Nếu khóa bằng một trong các khóa ở nút, thuật toán trả về `true` chính xác. Nếu không bằng, các khóa phân cách chia giá trị thành những khoảng loại trừ nhau, nên **chỉ một cây con `children[i]` có thể chứa `x`**. Chuyển xuống cây con đó duy trì bất biến.

Nếu thuật toán đi tới lá mà không có khóa `x`, không tồn tại nhánh nào sâu hơn để tiếp tục tìm; bởi vậy trả về `false` là đúng. Nếu cây ban đầu rỗng (`root=null`), `false` cũng chính xác.

**Điều kiện của chứng minh:** cây phải tuân theo bất biến thứ tự khóa và khoảng cây con. Nếu các con trỏ bị đặt nhầm, hoặc có khóa nằm ngoài khoảng do tổ tiên quy định, việc không tìm thấy không thể được dùng để kết luận khóa thực sự vắng mặt.

### Tìm thấy khóa và tìm thấy bản ghi không luôn là một

Khi một nút chứa cả khóa và dữ liệu đi kèm, thuật toán có thể trả về **vị trí nút cùng chỉ số khóa** (hoặc bản ghi tương ứng) thay vì chỉ `true`. Ví dụ kiểu kết quả:

```text
SearchResult:
    found: true/false
    node: nút chứa khóa, nếu có
    index: chỉ số khóa trong nút, nếu có
```

Việc trả về vị trí hữu ích cho thao tác đọc/cập nhật giá trị, nhưng nếu cấu trúc bị chèn, xóa hoặc thay đổi bộ đệm sau đó, con trỏ/iterator đến vị trí cũ có thể không còn ổn định. Hợp đồng về hiệu lực vị trí cần được xác định theo cài đặt cụ thể.

## 6. Mã Java hoàn chỉnh: trả kết quả kèm đường đi

Đoạn Java sau tạo B-tree minh họa ở Mục 3 và tìm kiếm theo `lower_bound`. Nó trả về việc có tìm thấy hay không, số nút đã thăm và đường đi qua các nhánh. Cách viết sử dụng vòng lặp, không cần ngăn xếp đệ quy cho tìm kiếm.

```java
import java.util.Arrays;
import java.util.Objects;

public class BTreeSearchPathDemo {
    static final class Node {
        final int[] keys;
        final Node[] children;

        Node(int[] keys, Node... children) {
            Objects.requireNonNull(keys, "keys");
            Objects.requireNonNull(children, "children");
            if (keys.length == 0) {
                throw new IllegalArgumentException("Empty node");
            }
            this.keys = keys.clone();
            this.children = children.clone();

            for (int i = 1; i < this.keys.length; i++) {
                if (this.keys[i - 1] >= this.keys[i]) {
                    throw new IllegalArgumentException(
                        "Keys must be strictly increasing"
                    );
                }
            }

            // La khong co con, nut trong phai co k + 1 con.
            if (this.children.length != 0
                    && this.children.length != this.keys.length + 1) {
                throw new IllegalArgumentException(
                    "Internal node needs k + 1 children"
                );
            }
            for (Node child : this.children) {
                Objects.requireNonNull(child, "child");
            }
        }

        boolean isLeaf() {
            return children.length == 0;
        }
    }

    static final class SearchResult {
        final boolean found;
        final int visitedNodes;
        final String path;

        SearchResult(boolean found, int visitedNodes, String path) {
            this.found = found;
            this.visitedNodes = visitedNodes;
            this.path = path;
        }
    }

    // Tra ve chi so dau tien ma keys[i] >= target, hoac keys.length.
    static int lowerBound(int[] keys, int target) {
        int lo = 0;
        int hi = keys.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (keys[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    static SearchResult search(Node root, int target) {
        if (root == null) {
            return new SearchResult(false, 0, "(empty tree)");
        }

        Node current = root;
        int visited = 0;
        StringBuilder path = new StringBuilder();

        while (current != null) {
            if (path.length() > 0) {
                path.append(" -> ");
            }
            path.append(Arrays.toString(current.keys));
            visited++;

            int i = lowerBound(current.keys, target);
            if (i < current.keys.length
                    && current.keys[i] == target) {
                return new SearchResult(true, visited, path.toString());
            }

            if (current.isLeaf()) {
                return new SearchResult(false, visited, path.toString());
            }

            path.append(" [P").append(i).append("]");
            current = current.children[i];
        }

        // Khong den day neu cac con tro cua cay hop le.
        return new SearchResult(false, visited, path.toString());
    }

    static void show(Node root, int target) {
        SearchResult result = search(root, target);
        System.out.println("x=" + target
            + ", found=" + result.found
            + ", nodes=" + result.visitedNodes
            + ", path=" + result.path);
    }

    public static void main(String[] args) {
        Node p0 = new Node(new int[] {5, 10});
        Node p1 = new Node(new int[] {25, 30});
        Node p2 = new Node(new int[] {45, 50});
        Node p3 = new Node(new int[] {70, 80});

        Node root = new Node(
            new int[] {20, 40, 60}, p0, p1, p2, p3
        );

        for (int x : new int[] {50, 35, 60, 100, -5}) {
            show(root, x);
        }
        show(null, 20);
    }
}
```

Kết quả dự kiến:

```text
x=50, found=true, nodes=2, path=[20, 40, 60] [P2] -> [45, 50]
x=35, found=false, nodes=2, path=[20, 40, 60] [P1] -> [25, 30]
x=60, found=true, nodes=1, path=[20, 40, 60]
x=100, found=false, nodes=2, path=[20, 40, 60] [P3] -> [70, 80]
x=-5, found=false, nodes=2, path=[20, 40, 60] [P0] -> [5, 10]
x=20, found=false, nodes=0, path=(empty tree)
```

Hai điểm trong cài đặt đáng chú ý:

- `lowerBound` có thể trả về `keys.length`; điều kiện `i < keys.length` được kiểm tra **trước khi** đọc `keys[i]` để không vượt biên.
- Khi không tìm thấy ở nút trong, `children[i]` luôn nằm trong đoạn con hợp lệ `0..k` **nếu cây thỏa bất biến số con**.

Constructor chỉ kiểm tra **thứ tự khóa cục bộ, số con và con không `null`**. Nó chưa kiểm tra các khóa ở **toàn bộ cây con** thuộc đúng khoảng, mức lấp đầy tối thiểu của B-tree hay mọi lá cùng độ sâu. Đó là nhiệm vụ của một bộ xác minh bất biến riêng; ví dụ đã dựng sẵn ở đây thỏa những điều kiện cần thiết.

Chương trình dùng `int` và so sánh trực tiếp, không trừ hai số để so sánh. Cách này cũng tránh lỗi tràn số khi khóa ở gần `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`.

## 7. Một lưu ý quan trọng: B+ tree có quy tắc khóa bằng khác B-tree

Trong **B-tree** như mô hình trên, nếu khóa cần tìm **bằng** khóa đang lưu ở nút trong, thuật toán có thể trả về thành công ngay tại đó. Nhưng trong **B+ tree** thông dụng, khóa tại nút trong chủ yếu là **khóa phân cách để định tuyến**; các bản ghi hoặc liên kết tới bản ghi được lưu ở **lá**.

Vì vậy, không thể dùng nguyên xi quy tắc “`keys[i] == x` thì dừng tìm” cho mọi B+ tree.

### Ví dụ quy ước khóa đầu tiên của nhánh phải

Giả sử nút trong B+ tree chứa các khóa phân cách `[20 | 40]`, mỗi khóa bằng **khóa nhỏ nhất của cây con ngay bên phải**:

```text
                           [20 | 40]
                          /    |     \
                       [5,10] [20,30] [40,50]
                         P0     P1      P2

P0: x < 20
P1: 20 <= x < 40
P2: x >= 40
```

Ở đây:

- Tìm `20` phải đi xuống **`P1`**, không kết thúc ở khóa phân cách `20`.
- Tìm `40` phải đi xuống **`P2`**, không chọn `P1`.
- Tìm `35` đi `P1`; tìm `5` đi `P0`.

Quy tắc định tuyến là lấy chỉ số **khóa phân cách đầu tiên lớn hơn hẳn `x`** (*`upper_bound(x)`*):

\[
i=\min\{j\mid K_j>x\},
\]

và đặt `i=k` nếu không tìm được. Khi các khóa phân cách bằng giá trị nhỏ nhất ở nhánh phải, chỉ số này chọn đúng nhánh cho cả trường hợp `x` bằng separator.

```java
// B+ tree dung quy uoc key dau tien cua nhanh ben phai.
static int upperBound(int[] separators, int target) {
    int lo = 0, hi = separators.length;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (separators[mid] <= target) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return lo; // Chi so nhanh con, ke ca khi target bang separator.
}
```

**Đây không phải quy tắc bất biến cho tất cả B+ tree.** Một số cài đặt dùng khóa lớn nhất của nhánh trái hoặc quy ước biên khác, nên lựa chọn khi bằng separator có thể đổi theo. Quy tắc đúng phải được xác định từ **hợp đồng định tuyến của chính cấu trúc đó**.

| Vấn đề | B-tree theo mô hình bài học | B+ tree theo quy ước separator là khóa nhỏ nhất của nhánh phải |
| --- | --- | --- |
| Khóa ở nút trong | Có thể là khóa dữ liệu | Dùng để định tuyến |
| Nếu `x` bằng khóa trong nút trong | Có thể trả về “tìm thấy” | Tiếp tục xuống con bên phải tương ứng |
| Chọn con khi chưa tìm thấy tại nút | `lower_bound` rồi `children[i]` | `upper_bound` để định tuyến qua separator |
| Nơi lấy bản ghi | Có thể ở nút trong hoặc lá | Thường ở lá |

## 8. Độ phức tạp: phép so sánh trong nút và số tầng của cây

Gọi:

- `n` là tổng số khóa của cây.
- `k` là số khóa trong nút hiện tại.
- `h` là chiều cao tính bằng số **cạnh từ gốc tới lá**.
- `t` là bậc tối thiểu nếu dùng quy ước B-tree tiêu chuẩn (`2t-1` khóa tối đa mỗi nút).

Thuật toán đi qua **tối đa `h+1` nút** nếu mỗi lượt chỉ chọn một con. Tại một nút, tìm `lower_bound` bằng quét tuyến tính cần O(k) so sánh, còn tìm nhị phân cần O(log(k+1)) so sánh.

| Thành phần | Quét tuyến tính | Tìm nhị phân |
| --- | --- | --- |
| Xử lý một nút `k` khóa | O(k) | O(log(k+1)) |
| Một đường có tối đa `h+1` nút, `k <= 2t-1` | O((h+1)t) | O((h+1)log t) |
| Với `t` cố định, B-tree cân bằng | O(log n) | O(log n) |
| Số nút đi qua | O(h+1) | O(h+1) |

Với bậc tối thiểu `t`, các bất biến mức lấp đầy và cùng độ sâu của lá cho phép chặn chiều cao:

\[
h\le\log_t\left(\frac{n+1}{2}\right)
\]

cho cây không rỗng, theo quy ước chiều cao bằng số cạnh. Như vậy số tầng thường được diễn đạt là **O(log_t n)**, còn tổng số so sánh CPU phụ thuộc cách tìm trong nút.

Trong hệ thống lưu trữ theo trang, khi **mỗi nút nằm trong một trang** và trang chưa có trong bộ nhớ đệm, một đường tìm có thể phải nạp từng trang trên đường đó, tối đa khoảng `h+1` trang. Fan-out lớn giúp giảm chiều cao và do đó có thể giảm I/O. Nhưng nếu trang đã được cache thì không phải mỗi lượt thăm nút đều gây đọc thiết bị.

### Vì sao không duyệt tất cả cây con?

Một nút nhiều nhánh có thể có hàng chục hoặc hàng trăm con trỏ. Tìm kiếm **không** thử từng con rồi quay lui: sau khi so sánh khóa phân cách, nó chọn **duy nhất một con**. Chính bất biến khoảng khóa khiến tìm kiếm có chi phí theo **chiều cao**, thay vì duyệt toàn bộ cây với O(n) phần tử.

## 9. Khi khóa không phải số nguyên

Các khóa trong chỉ mục thực tế có thể là chuỗi, thời gian, mã định danh hoặc một bộ nhiều thuộc tính. Khi đó, thuật toán phải dùng **một quy tắc so sánh toàn phần, nhất quán** giữa:

1. Sắp thứ tự các khóa trong nút.
2. Chọn nhánh lúc tìm kiếm.
3. Chèn khóa mới và xử lý trùng khóa.

Ví dụ Java dùng `Comparator<String>`:

```java
import java.util.Comparator;

static int lowerBoundStrings(
        String[] keys, String target,
        Comparator<String> comparator) {
    int lo = 0, hi = keys.length;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (comparator.compare(keys[mid], target) < 0) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return lo;
}
```

Nếu chỉ mục được tạo với so sánh **không phân biệt chữ hoa/chữ thường** nhưng lúc tìm dùng so sánh phân biệt chữ hoa/chữ thường, đường đi có thể sai. Tương tự, nếu một cài đặt hỗ trợ nhiều bản ghi có cùng khóa, cần quyết định cách lưu giá trị trùng hoặc cách tìm tất cả giá trị trùng; không thể giả định quy tắc khóa phân biệt của ví dụ luôn áp dụng.

Việc xử lý `null`, độ dài khóa, so sánh theo locale và quan hệ bằng nhau đều cần được quy định rõ trong API. Sự nhất quán của bộ so sánh quan trọng hơn việc chọn tìm tuyến tính hay tìm nhị phân.

## 10. Lỗi thường gặp khi chọn nhánh

1. **Nhầm số con với số khóa.** Nút trong có `k` khóa cần `k+1` con; nhánh phải nhất có chỉ số `k`, không phải `k-1`.
2. **Đọc `keys[i]` trước khi kiểm tra `i<k`.** Nếu `x` lớn hơn mọi khóa thì `lower_bound(x)=k`, truy cập `keys[k]` sẽ vượt biên.
3. **Không kiểm tra trường hợp bằng khóa ở nút trong B-tree.** Nếu đã có `x` tại nút mà vẫn chọn nhánh, thuật toán có thể bỏ qua đáp án.
4. **Đi xuống con khi đang ở lá.** Lá không có con. Không tìm thấy ở lá nghĩa là tìm kiếm thất bại.
5. **Chọn `P{i+1}` thay vì `Pi`.** Với `lower_bound` khi không có khóa bằng `x`, chỉ số `i` đã là đúng nhánh cần đi.
6. **Nhầm `lower_bound` với `upper_bound`.** Hai cách khác nhau ở **giá trị bằng khóa phân cách**; B+ tree cần quy ước biên cụ thể.
7. **Tìm nhị phân trên khóa chưa sắp xếp.** Thuật toán phụ thuộc mảng khóa tăng; dữ liệu sai thứ tự có thể làm chọn nhánh sai.
8. **Kiểm tra chỉ khóa của nút con mà quên khoảng do tổ tiên.** Khóa nằm sai cây con có thể khiến tìm kiếm kết luận sai dù từng nút vẫn được sắp.
9. **Quên kiểm tra trường hợp cây rỗng.** Khi `root=null`, thuật toán phải trả về không tìm thấy mà không giải tham chiếu nút.
10. **Dùng phép trừ số nguyên để so sánh khóa lớn/nhỏ.** `a-b` có thể tràn số; nên so sánh trực tiếp hoặc dùng bộ so sánh thích hợp.
11. **Coi một lần thăm nút luôn bằng một lần I/O.** Trang có thể nằm trong cache, còn chi phí so sánh trong nút là một khoản riêng.
12. **Cho rằng tìm trong nút O(log k) làm tổng tìm kiếm O(1).** Vẫn phải đi qua các tầng của cây, trừ khi khóa được tìm ngay tại nút đang xét.

## 11. Tự kiểm tra

**Câu 1.** Một nút trong có năm khóa phân biệt đã sắp tăng. Nó cần bao nhiêu con trỏ con để phân định các khoảng?

**Đáp án:** Sáu con trỏ, đánh chỉ số `P0` đến `P5`.

**Câu 2.** Với `keys=[20,40,60]`, `lower_bound(50)` bằng bao nhiêu và chọn nhánh nào?

**Đáp án:** Bằng `2`, vì `60` là khóa đầu tiên không nhỏ hơn 50. Chọn `P2` nếu không có khóa bằng 50 tại nút.

**Câu 3.** Với cùng nút, tìm `60` theo mô hình B-tree của bài có đi xuống nhánh `P2` không?

**Đáp án:** Không. `lower_bound(60)=2` và `keys[2]=60`, nên tìm thấy tại nút hiện tại.

**Câu 4.** Với `keys=[20,40,60]`, `lower_bound(90)` trả về bao nhiêu? Vì sao không được đọc `keys[3]`?

**Đáp án:** Trả về `3`, bằng số khóa `k`. `keys[3]` nằm ngoài đoạn khóa hợp lệ `[0,3)`; thay vào đó, nếu là nút trong phải chọn `children[3]`.

**Câu 5.** Trên cây ví dụ `[20|40|60]` có các lá `[5,10]`, `[25,30]`, `[45,50]`, `[70,80]`, đường tìm `35` đi qua những nút nào?

**Đáp án:** Đi từ `[20,40,60]` theo `P1` đến lá `[25,30]`, rồi trả về không tìm thấy. Tổng cộng thăm hai nút.

**Câu 6.** Nếu tìm `-5` trên cây ví dụ, cần chọn nhánh nào ở gốc?

**Đáp án:** `P0` vì `-5` nhỏ hơn khóa nhỏ nhất `20`.

**Câu 7.** Tìm nhị phân trong một nút có `k` khóa cần bao nhiêu phép so sánh ở trường hợp xấu nhất, theo Big-O?

**Đáp án:** O(log(k+1)), so với O(k) nếu quét tuyến tính.

**Câu 8.** Một nút B-tree có hai khóa nhưng mảng `children` chỉ chứa hai con thực. Bất biến nào bị vi phạm?

**Đáp án:** Nút trong hai khóa phải có **ba con** ứng với ba khoảng. Thiếu con giữa hoặc ngoài cùng làm định tuyến không đầy đủ.

**Câu 9.** Trong B+ tree dùng separator bằng khóa nhỏ nhất của nhánh phải, khóa `40` tại nút trong `[20|40]` phải đi `P1` hay `P2`?

**Đáp án:** `P2`. Quy tắc này dùng `upper_bound(40)=2` và tiếp tục xuống lá, không kết thúc tại khóa phân cách.

**Câu 10.** Trong B+ tree dùng một quy ước separator khác, có thể vẫn áp dụng `upper_bound` mà không kiểm tra không?

**Đáp án:** Không. Phải xác định ranh giới thuộc nhánh trái hay nhánh phải và quy tắc xử lý khóa bằng separator theo cài đặt.

**Câu 11.** Nếu khóa ở từng nút đều tăng nhưng một cây con chứa khóa vượt quá cận do tổ tiên đặt ra, thuật toán chọn một nhánh có còn bảo đảm đúng không?

**Đáp án:** Không. Chứng minh tính đúng đắn dựa vào mọi cây con tuân theo khoảng khóa của **tất cả tổ tiên**, không chỉ nút hiện tại.

**Câu 12.** Vì sao B-tree có nhiều con trên mỗi nút thường phù hợp với chỉ mục dữ liệu phân trang?

**Đáp án:** Mỗi trang chứa nhiều khóa phân cách và con trỏ; tìm kiếm chọn một nhánh ở mỗi tầng. Fan-out lớn làm giảm chiều cao và có thể giảm số trang cần nạp trên đường tìm.

**Câu 13.** Trong hàm `lowerBound` của Java, nếu mảng có khóa là `Integer.MIN_VALUE`, dùng phép so sánh `keys[mid] < target` có an toàn hơn việc dùng `keys[mid] - target < 0` không?

**Đáp án:** Có. So sánh trực tiếp không bị tràn số nguyên như phép trừ có thể gây ra.

**Câu 14.** Một cây rỗng có `root=null`. Phương thức `contains(root, 10)` nên trả về kết quả gì?

**Đáp án:** `false` mà không đọc bất kỳ nút nào.

**Điểm ghi nhớ:** Với B-tree chứa khóa phân biệt, một nút có `k` khóa tăng và `k+1` con nếu là nút trong. Tìm `lower_bound(x)` để lấy chỉ số `i`; **nếu `keys[i] == x` thì tìm thấy**, nếu không và nút là lá thì thất bại, còn nếu là nút trong thì **chọn `children[i]`**. Quy tắc biên khi bằng khóa phân cách phải được thiết kế riêng cho B+ tree. Khi các bất biến của cây được duy trì, mỗi bước chỉ theo một nhánh và chi phí tìm kiếm gắn với số tầng của cây.
