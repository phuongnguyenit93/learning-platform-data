# Kiểm tra bất biến cây nhiều nhánh sau chuỗi cập nhật

Một thao tác chèn hoặc xóa trên **cây tìm kiếm nhiều nhánh** có thể chạy xong mà không phát sinh ngoại lệ nhưng vẫn để lại **cấu trúc sai**. Ví dụ, một nút trong có đủ khóa và đủ con nhưng một con trỏ bị gán vào sai khoảng; tìm kiếm một số khóa vẫn thành công, trong khi các khóa khác đột nhiên “biến mất”. Với **B+ tree**, việc quên nối lại liên kết giữa hai lá có thể làm truy vấn khoảng bỏ sót bản ghi dù phép tìm chính xác vẫn đúng.

Vì vậy, kiểm thử thuật toán không nên dừng ở câu hỏi “`insert(42)` có chạy không?”. Sau **mỗi phép cập nhật**, cần kiểm tra đồng thời:

1. **Bất biến cấu trúc:** số khóa/con, thứ tự, khoảng khóa, độ sâu lá và liên kết.
2. **Bất biến nội dung:** tập khóa sau cập nhật đúng bằng tập khóa mong đợi.
3. **Hành vi thao tác:** thêm/xóa thành công hoặc thất bại đúng quy ước; không làm mất hay nhân đôi khóa khác.

Bài này xây dựng một phương pháp kiểm chứng cho **B-tree với bậc tối thiểu `t`**, mở rộng sang **B+ tree**, mô phỏng các chuỗi cập nhật gây tách/mượn/gộp/hạ gốc và cung cấp chương trình **Java tự chứa** gồm B-tree chèn/xóa, bộ kiểm tra bất biến độc lập, đối chiếu với `TreeSet` và kiểm thử ngẫu nhiên có seed cố định.

Mục đích là học cách phát hiện lỗi **ngay tại bước đầu tiên làm hỏng cây**, thay vì phải lần ngược từ một truy vấn sai sau hàng nghìn lần cập nhật.

## 1. Vì sao kiểm tra chỉ kết quả tìm kiếm là chưa đủ?

Xét B-tree `t=2`:

```text
                           [40]
                          /    \
                     [10, 20] [50, 60]
```

Nếu sau một lần xoay hoặc gộp, lập trình viên vô tình hoán đổi hai con:

```text
                           [40]
                          /    \
                     [50, 60] [10, 20]      <- SAI KHOẢNG
```

Hai lá vẫn có số khóa hợp lệ, từng lá vẫn sắp tăng, gốc có đúng hai con, và các lá cùng độ sâu. Nhưng `find(10)` sẽ chọn con trái vì `10<40` và không tìm thấy, trong khi khóa 10 vẫn tồn tại ở lá phải!

Đó là lỗi **bất biến toàn cục**: khóa của mỗi cây con phải tuân theo các giới hạn do **mọi tổ tiên** áp đặt. Một bộ kiểm tra chỉ xem xét độ dài mảng hoặc số con sẽ không phát hiện được.

Một ví dụ khác với B+ tree:

```text
Nút trong:                [30 | 50]
                         /    |     \
Lá:                   [10,20] [30,40] [50,60]

Liên kết next bị lỗi:  [10,20] ----------> [50,60] -> null
                               [30,40] bị bỏ qua
```

Tìm chính xác 30 bằng đường từ gốc vẫn có thể thành công; nhưng truy vấn `[10,60]` theo `next` bỏ sót 30 và 40. Muốn phát hiện loại lỗi này, phải kiểm tra **chuỗi lá**, không chỉ cây phân cấp.

**Nguyên tắc:** kiểm tra **hình dạng** và **tập dữ liệu** là hai việc bổ sung cho nhau, không thay thế nhau.

## 2. Chốt mô hình trước khi viết bộ kiểm tra

Công thức bất biến phụ thuộc biến thể cây. Trong phần chính và mã Java, ta dùng:

- **B-tree**, bậc tối thiểu `t\ge2`.
- Khóa nguyên `int` và **không trùng**; thêm trùng hoặc xóa khóa không tồn tại trả về `false`.
- Khóa dữ liệu có thể nằm ở **nút trong hoặc lá**, không lặp giữa hai nút.
- Nút có `count` khóa có hiệu lực trong `keys[0..count-1]`. Những ô mảng ngoài phạm vi `count` chỉ là vùng dự trữ.
- Nút trong có **đúng `count+1` con thực**, lá không có con.
- Cây rỗng được biểu diễn bằng `root=null`.

Sau đó bài mở rộng sang **B+ tree** với mục dữ liệu ở lá, separator `S_i=minKey(children[i+1])` và liên kết `next/prev`; đây là **một bộ bất biến khác**, không dùng nguyên xi quy tắc “khóa không lặp giữa nút trong và lá”.

### Bảng những giả định khác biệt

| Đặc điểm | B-tree của bài | B+ tree minh họa |
| --- | --- | --- |
| Khóa ở nút trong | Khóa dữ liệu thật | Khóa phân cách (*separator*) |
| Dữ liệu của một khóa | Có thể tại mọi tầng | Mục dữ liệu nằm ở lá |
| Trùng giá trị khóa giữa hai tầng | Không theo mô hình khóa duy nhất | Separator **có thể bằng** khóa của mục lá |
| Khi tìm bằng khóa ở nút trong | Có thể trả kết quả ngay | Tiếp tục đi xuống lá |
| Bất biến số con | `k` khóa → `k+1` con | `k` separator → `k+1` con |
| Liên kết các lá theo thứ tự | Không bắt buộc | Thường có `next`, đôi khi `prev` |

Không được áp những giả định chưa nêu cho một thư viện có **khóa trùng**, **B-link tree**, **fence key**, **separator rút gọn** hoặc quy ước “order `m`” khác với bậc tối thiểu `t`.

## 3. Bộ bất biến B-tree cần xác minh

### 3.1. Giới hạn số khóa

Với bậc tối thiểu `t`:

\[
\begin{aligned}
\text{MAX\_KEYS} &= 2t-1,\\
t-1 \le count &\le 2t-1 &&\text{cho nút không phải gốc}.
\end{aligned}
\]

Gốc của **cây không rỗng** có ít nhất một khóa; gốc được phép ít khóa hơn `t-1`. Nếu xóa hết mục và gốc là lá, nên đưa cây về trạng thái rỗng. Nếu gốc trong đã mất khóa cuối sau gộp, phải **hạ gốc** bằng cách nâng con duy nhất lên.

Ví dụ `t=3`: nút không phải gốc phải có **2–5 khóa**. Một nút chỉ còn một khóa là thiếu khóa (*underflow*) dù mảng của nó không rỗng.

### 3.2. Số con và loại nút

Với nút trong có `k` khóa, phải có **`k+1` con không `null`**; lá không có con. Kiểm tra phải dùng **`count` logic**, không nhầm với dung lượng mảng con đã cấp phát.

```text
Nút trong hợp lệ:
                       [20 | 40 | 60]
                      /     |    |     \
                     P0     P1   P2     P3

3 khóa  -> 4 con thực
```

Trong mã dùng mảng cố định, một lỗi tinh vi là `count=2` nhưng `children[3]` vẫn giữ tham chiếu tới một nút đã bị gộp. Tìm kiếm có thể không đọc ô đó, nhưng cấu trúc nội bộ vẫn giữ tham chiếu thừa. Bộ kiểm tra có thể **yêu cầu mọi ô con ngoài `[0..count]` đều là `null`** để bắt lỗi quản lý liên kết.

### 3.3. Thứ tự khóa trong nút

Với `k=count`:

\[
keys[0] < keys[1] < \cdots < keys[k-1].
\]

Thứ tự phải tăng **nghiêm ngặt** vì mô hình không cho khóa trùng. Không nên dùng phép trừ `a-b` để so sánh hai khóa `int`: phép trừ có thể tràn số. Nên dùng `a<b`, `a>b` hoặc `Integer.compare`.

### 3.4. Khoảng khóa do toàn bộ tổ tiên áp đặt

Cho nút trong có các khóa `[20,40,60]` và một khoảng tổ tiên `(low,high)`. Mỗi con được kiểm tra theo:

| Con | Cận dưới loại trừ | Cận trên loại trừ |
| --- | --- | --- |
| `P0` | `low` | `20` |
| `P1` | `20` | `40` |
| `P2` | `40` | `60` |
| `P3` | `60` | `high` |

Khi đệ quy, **mang theo `low, high` từ tổ tiên**, không chỉ so sánh con với khóa cha gần nhất. Như vậy sẽ phát hiện trường hợp một khóa ở sâu nhiều tầng nằm ngoài miền hợp lệ.

```text
                    [50]
                   /    \
                [20]    [80]
               /    \
             [10]   [60]          <- SAI

Khóa 60 ở dưới nhánh trái của 50.
Dù 60 > 20, nó vẫn không được phép ở đây vì 60 > cận 50.
```

Để kiểm tra toàn bộ miền số nguyên `int`, có thể dùng cận `long` với giá trị đầu `Long.MIN_VALUE` và `Long.MAX_VALUE`, rồi kiểm tra:

\[
low < key < high.
\]

Cách này không vô tình loại bỏ khóa hợp lệ `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`.

### 3.5. Tất cả lá cùng độ sâu

Một B-tree cân bằng có **mọi lá ở cùng độ sâu** tính từ gốc:

```text
Hợp lệ:                       Sai:

        [40]                       [40]
       /    \                     /    \
     [20]  [60]                 [20]   [60]
     / \    / \                 / \      \
   [..][..][..][..]           [..][..]   [..]
                                           \
                                          [..]
```

Tại lá đầu tiên, ghi nhận `expectedLeafDepth`. Mọi lá tiếp theo phải có `depth == expectedLeafDepth`. Tách gốc làm **mọi lá tăng độ sâu một**, còn hạ gốc làm **mọi lá giảm độ sâu một**; không được chỉ thay độ sâu của một nhánh.

### 3.6. Không chu trình và không dùng chung một nút theo hai đường

Trong mô hình cây, một nút phải được truy cập từ gốc theo **đúng một đường cha–con**. Nếu một con trỏ trỏ ngược về tổ tiên, sẽ tạo chu trình. Nếu hai vị trí con trỏ cùng trỏ đến **một đối tượng nút**, cấu trúc là đồ thị có nút chia sẻ, không còn là cây.

Kiểm tra bằng **tập đối tượng đã thăm theo định danh**, không dùng `equals` theo giá trị khóa. Trong Java, `IdentityHashMap` có thể làm nền cho `Set<Node>` để nhận ra cùng đối tượng xuất hiện lần thứ hai.

### 3.7. Số lượng và tập khóa

Một lần thêm khóa mới `x` phải làm `size` tăng 1; thêm trùng không tăng. Xóa khóa có trong cây giảm 1; xóa khóa vắng mặt không giảm. Nhưng đếm đúng chưa đủ:

```text
Trước: {10, 20, 30}
Sau lỗi: {10, 20, 40}

Số khóa vẫn là 3, nhưng 30 bị mất và 40 xuất hiện sai.
```

Vì thế, ngoài `size`, cần **duyệt toàn bộ cây theo thứ tự** rồi so sánh với tập chuẩn (*reference oracle*), ví dụ `java.util.TreeSet<Integer>`.

## 4. Thứ tự kiểm tra tốt nhất sau mỗi phép cập nhật

Một bộ xác minh nên làm theo trình tự có khả năng chỉ ra lỗi rõ ràng:

1. **Kiểm tra gốc:** cây rỗng hay không; nếu không rỗng, `root.count` trong giới hạn.
2. **Duyệt cấu trúc từ gốc:** phát hiện chu trình/nút dùng chung, số khóa và các con hợp lệ.
3. **Kiểm tra khóa theo cận tổ tiên:** tất cả khóa trong nút và cây con nằm đúng khoảng.
4. **Kiểm tra độ sâu lá:** mọi lá có cùng `depth`.
5. **Thu thập khóa theo thứ tự:** đúng số lượng và đúng thứ tự tăng.
6. **Đối chiếu oracle:** tập khóa thực trong cây bằng tập mong đợi sau chuỗi thao tác.
7. **Thử một số truy vấn quan trọng:** các khóa ở biên nút, khóa vắng mặt, phần tử đầu/cuối, nếu API có tìm kiếm.

Nếu bước 2 phát hiện chu trình, phải **dừng duyệt** thay vì tiếp tục đệ quy vô hạn. Khi cấu trúc đã sai, so sánh thêm các truy vấn tìm kiếm thường không giúp xác định nguyên nhân gốc.

### Hai cấp kiểm tra

| Cấp | Thời điểm phù hợp | Kiểm tra |
| --- | --- | --- |
| **Cục bộ** | Trong nội bộ `splitChild`, `borrow`, `merge` | Số khóa, số con và vị trí phân cách của vài nút đang sửa |
| **Toàn cục** | Sau mỗi phép cập nhật hoàn tất, trong test/debug | Toàn cây, cận tổ tiên, độ sâu lá, con trỏ, tập khóa |

Kiểm tra toàn bộ cây có chi phí O(n) nếu phải thăm mọi khóa. Điều đó **không biến chèn/xóa B-tree thành O(n)** trong ứng dụng sản xuất nếu bộ kiểm tra chỉ được chạy trong **test hoặc debug**. Không nên bật quét O(n) sau mọi thao tác ở môi trường tải lớn nếu không có chủ đích.

## 5. Ví dụ các chuỗi cập nhật cần kiểm tra

Với B-tree `t=2`, nút chứa tối đa 3 khóa và các nút không phải gốc chứa tối thiểu 1 khóa.

### 5.1. Chèn tạo gốc mới

```text
insert(10) -> [10]
insert(20) -> [10 | 20]
insert(30) -> [10 | 20 | 30]    (gốc đầy)

insert(40): tách gốc đầy trước khi đi xuống

                  [20]
                 /    \
               [10]  [30 | 40]
```

Sau mỗi `insert` cần khẳng định tập khóa lần lượt là:

```text
{10}
{10,20}
{10,20,30}
{10,20,30,40}
```

Đặc biệt, sau khi tách, khóa `20` chuyển lên gốc nhưng **không bị mất**, mọi lá cùng độ sâu 1 và tổng khóa tăng đúng một chỉ vì thêm `40`.

### 5.2. Mượn từ anh em phải

```text
Trước xóa, t=2:

                     [40]
                    /    \
                  [10]  [50 | 60]

delete(10): chuẩn bị con trái (1 khóa) bằng mượn từ phải

    [40] -> [50]        (50 lên cha, 40 xuống con trái)
    [10] -> [10 | 40]  (trước khi xóa)
    [50 | 60] -> [60]

Sau xóa:
                     [50]
                    /    \
                  [40]   [60]
```

Bộ kiểm tra phải thấy tập khóa đổi từ `{10,40,50,60}` thành `{40,50,60}`, chứ không được đếm nhầm khóa `50` vì nó được chuyển lên cha.

### 5.3. Mượn từ anh em trái

```text
Trước:
                     [40]
                    /    \
                [10 | 20] [50]

delete(50):
  - 20 từ anh em trái lên cha
  - 40 từ cha xuống con phải

Sau:
                     [20]
                    /    \
                  [10]   [40]
```

Tổng khóa trước là `{10,20,40,50}`, sau là `{10,20,40}`. Các cận khoảng của hai con cũng đổi theo khóa phân cách mới tại gốc.

### 5.4. Gộp làm hạ gốc

```text
Trước:
                       [40]
                      /    \
                    [10]   [50]

Gộp qua khóa cha:
                [10 | 40 | 50]     (nâng nút gộp lên)

delete(10) ->   [40 | 50]         (gốc là lá)
```

Sau khi hoàn tất, cây vẫn có hai khóa và không còn một **gốc rỗng với một con**. Mọi khóa khác được giữ nguyên; chiều cao giảm từ 1 xuống 0.

### 5.5. Xóa khóa trong nút trong

```text
Trước:
                     [40]
                    /    \
                [10 | 20] [50]

delete(40): dùng tiền nhiệm = 20 ở con trái.

Sau:
                     [20]
                    /    \
                  [10]   [50]
```

Nếu chỉ thay `40` bằng `20` mà không xóa bản gốc `20` khỏi lá, bộ kiểm tra sẽ phát hiện **khóa trùng**, sai số lượng hoặc không khớp oracle.

### Bảng các checkpoint nên có trong bộ test

| Loại cập nhật | Hành vi phải quan sát | Bất biến dễ bị phá |
| --- | --- | --- |
| Chèn vào lá chưa đầy | Chèn đúng vị trí, tăng `size` | Thứ tự khóa |
| Tách lá/gốc đầy | Khóa giữa lên cha, hai nhóm khóa hợp lệ | Tổng khóa, độ sâu lá |
| Tách nút trong | Chia thêm các con trỏ | `k+1` con, khoảng tổ tiên |
| Xóa lá còn dư | Dịch khóa, giảm `size` | Thứ tự, số lượng |
| Mượn từ trái/phải | Luân chuyển khóa qua cha, có thể chuyển con | Khoảng khóa, mức tối thiểu |
| Gộp hai nút | Khóa cha đi xuống, cha giảm khóa/con | Đếm khóa, chu trình, con trỏ |
| Xóa khóa nút trong | Tiền nhiệm/kế nhiệm hoặc gộp | Trùng khóa, khoảng |
| Hạ gốc | Nâng con duy nhất làm gốc | Gốc hợp lệ, chiều cao |
| Xóa đến cây rỗng | `root=null`, `size=0` | Trường hợp biên |
| Thêm trùng, xóa khóa vắng | Không đổi tập dữ liệu | Tác dụng ngoài ý muốn |

## 6. Oracle độc lập: `TreeSet` đối chiếu sau từng bước

Một cách kiểm thử **độc lập với cấu trúc cây** là duy trì một tập khóa tham chiếu `TreeSet<Integer>`. Với mỗi thao tác, áp dụng **cùng ý định cập nhật** lên cả hệ thống cần kiểm tra (*system under test*, SUT) và tập chuẩn:

```text
oracle = TreeSet()
tree = BTree(t=2)

for operation in operations:
    actual = tree.execute(operation)
    expected = oracle.execute(operation)

    assert actual == expected           # kết quả thành công/thất bại
    verifyStructure(tree)               # bất biến B-tree
    assert inOrder(tree) == sorted(oracle)
    assert tree.size == oracle.size()
```

`TreeSet` trong Java là một tập có thứ tự, cho phép thêm/xóa trả về boolean tùy có thay đổi tập hay không. Không cần biết nó dùng cách cân bằng nào để sử dụng như một oracle **tập khóa**; điều quan trọng là oracle có cài đặt riêng và không dựa vào các con trỏ nội bộ của B-tree đang được thử.

**Điều `TreeSet` không kiểm tra được:** một cây có thể chứa đúng tập khóa nhưng sai hình dạng, ví dụ nút dưới mức đầy tối thiểu hoặc lá không cùng độ sâu. Vì vậy, **so sánh oracle phải đi cùng bộ kiểm tra cấu trúc**, không thay thế bộ kiểm tra đó.

### Các phép thử nên bao gồm khóa biên

Nếu dùng `int`, nên có:

- `0` và các khóa âm.
- `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.
- Những khóa đúng bằng **khóa phân cách** ở nút trong.
- Một khóa nhỏ hơn mọi khóa đang có, lớn hơn mọi khóa đang có.
- Khóa trùng và khóa đã xóa rồi xóa lại.

Không nên xác định cận kiểm tra bằng phép `min-1` hoặc `max+1` trên `int`: có thể tràn số. Trong chương trình dưới đây, cận tổ tiên dùng `long`.

## 7. Java hoàn chỉnh: B-tree có bộ kiểm tra bất biến sau mỗi cập nhật

Ví dụ này cài đặt B-tree với **bậc tối thiểu `t \ge 2`**, có các thao tác `insert`, `delete`, `contains` và `verifyAgainst`. Một tập tham chiếu `TreeSet` được cập nhật song song; sau mỗi thao tác, chương trình **duyệt toàn cây**, kiểm tra bất biến và so sánh tất cả khóa theo thứ tự.

Để người học có thể tự chạy trong một tệp, các lớp được lồng trong `BTreeInvariantSequenceDemo`. Nội dung chú trọng **độc lập giữa thao tác cập nhật và logic xác minh**: thuật toán chèn/xóa không được gọi để “chứng minh” rằng chính nó đúng.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.TreeSet;

public class BTreeInvariantSequenceDemo {
    static final class Node {
        final int[] keys;
        final Node[] children;
        final boolean leaf;
        int count;

        Node(int t, boolean leaf) {
            keys = new int[2 * t - 1];
            children = new Node[2 * t];
            this.leaf = leaf;
        }
    }

    static final class Stats {
        // Dùng identity thay vì equals/hashCode theo nội dung khóa.
        final Set<Node> seen =
            Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        final List<Integer> inOrder = new ArrayList<>();
        int leafDepth = -1;
        int nodesVisited;
    }

    static final class BTree {
        private final int t;
        private Node root;
        private int size;

        BTree(int minimumDegree) {
            if (minimumDegree < 2
                    || minimumDegree > Integer.MAX_VALUE / 2) {
                throw new IllegalArgumentException("Invalid degree");
            }
            t = minimumDegree;
        }

        int size() {
            return size;
        }

        // Đầu tiên có keys[i] >= x, hoặc i == count.
        private static int lowerBound(Node node, int x) {
            int i = 0;
            while (i < node.count && node.keys[i] < x) {
                i++;
            }
            return i;
        }

        boolean contains(int x) {
            Node current = root;
            while (current != null) {
                int i = lowerBound(current, x);
                if (i < current.count && current.keys[i] == x) {
                    return true;
                }
                if (current.leaf) {
                    return false;
                }
                current = current.children[i];
            }
            return false;
        }

        boolean insert(int x) {
            if (root == null) {
                root = new Node(t, true);
                root.keys[0] = x;
                root.count = 1;
                size = 1;
                return true;
            }
            if (contains(x)) {
                return false;
            }
            if (root.count == 2 * t - 1) {
                Node newRoot = new Node(t, false);
                newRoot.children[0] = root;
                splitChild(newRoot, 0);
                root = newRoot;
            }
            insertNonFull(root, x);
            size++;
            return true;
        }

        // parent chưa đầy; con tại index có đúng 2t-1 khóa.
        private void splitChild(Node parent, int index) {
            Node full = parent.children[index];
            Node right = new Node(t, full.leaf);
            int middle = full.keys[t - 1];

            right.count = t - 1;
            for (int j = 0; j < t - 1; j++) {
                right.keys[j] = full.keys[j + t];
            }
            if (!full.leaf) {
                for (int j = 0; j < t; j++) {
                    right.children[j] = full.children[j + t];
                    full.children[j + t] = null;
                }
            }
            full.count = t - 1;

            for (int j = parent.count; j >= index + 1; j--) {
                parent.children[j + 1] = parent.children[j];
            }
            parent.children[index + 1] = right;
            for (int j = parent.count - 1; j >= index; j--) {
                parent.keys[j + 1] = parent.keys[j];
            }
            parent.keys[index] = middle;
            parent.count++;
        }

        private void insertNonFull(Node node, int x) {
            int i = node.count - 1;
            if (node.leaf) {
                while (i >= 0 && x < node.keys[i]) {
                    node.keys[i + 1] = node.keys[i];
                    i--;
                }
                node.keys[i + 1] = x;
                node.count++;
                return;
            }
            while (i >= 0 && x < node.keys[i]) {
                i--;
            }
            i++;
            if (node.children[i].count == 2 * t - 1) {
                splitChild(node, i);
                if (x > node.keys[i]) {
                    i++;
                }
            }
            insertNonFull(node.children[i], x);
        }

        boolean delete(int x) {
            if (root == null || !contains(x)) {
                return false; // Khóa vắng: không đổi hình dạng cây.
            }
            remove(root, x);

            if (root.count == 0) {
                root = root.leaf ? null : root.children[0];
            }
            size--;
            return true;
        }

        private void remove(Node node, int x) {
            int i = lowerBound(node, x);

            if (i < node.count && node.keys[i] == x) {
                if (node.leaf) {
                    removeFromLeaf(node, i);
                } else {
                    removeFromInternal(node, i);
                }
                return;
            }
            if (node.leaf) {
                return; // Không xảy ra nếu delete đã contains.
            }

            boolean wasRightmost = (i == node.count);
            if (node.children[i].count == t - 1) {
                fill(node, i);
            }
            // Khi gộp con cuối với anh em trái, vị trí mới là i-1.
            if (wasRightmost && i > node.count) {
                remove(node.children[i - 1], x);
            } else {
                remove(node.children[i], x);
            }
        }

        private void removeFromLeaf(Node node, int index) {
            for (int j = index + 1; j < node.count; j++) {
                node.keys[j - 1] = node.keys[j];
            }
            node.keys[--node.count] = 0; // Ô dự trữ, không phải khóa.
        }

        private static int predecessor(Node node, int index) {
            Node p = node.children[index];
            while (!p.leaf) {
                p = p.children[p.count];
            }
            return p.keys[p.count - 1];
        }

        private static int successor(Node node, int index) {
            Node p = node.children[index + 1];
            while (!p.leaf) {
                p = p.children[0];
            }
            return p.keys[0];
        }

        private void removeFromInternal(Node node, int index) {
            int x = node.keys[index];
            Node left = node.children[index];
            Node right = node.children[index + 1];

            if (left.count >= t) {
                int pred = predecessor(node, index);
                node.keys[index] = pred;
                remove(left, pred);
            } else if (right.count >= t) {
                int succ = successor(node, index);
                node.keys[index] = succ;
                remove(right, succ);
            } else {
                merge(node, index);
                remove(node.children[index], x);
            }
        }

        private void fill(Node parent, int i) {
            if (i > 0 && parent.children[i - 1].count >= t) {
                borrowFromPrev(parent, i);
            } else if (i < parent.count
                    && parent.children[i + 1].count >= t) {
                borrowFromNext(parent, i);
            } else if (i < parent.count) {
                merge(parent, i);
            } else {
                merge(parent, i - 1);
            }
        }

        private void borrowFromPrev(Node parent, int i) {
            Node child = parent.children[i];
            Node sibling = parent.children[i - 1];

            for (int j = child.count - 1; j >= 0; j--) {
                child.keys[j + 1] = child.keys[j];
            }
            if (!child.leaf) {
                for (int j = child.count; j >= 0; j--) {
                    child.children[j + 1] = child.children[j];
                }
                child.children[0] = sibling.children[sibling.count];
                sibling.children[sibling.count] = null;
            }
            child.keys[0] = parent.keys[i - 1];
            parent.keys[i - 1] = sibling.keys[sibling.count - 1];
            sibling.keys[sibling.count - 1] = 0;
            sibling.count--;
            child.count++;
        }

        private void borrowFromNext(Node parent, int i) {
            Node child = parent.children[i];
            Node sibling = parent.children[i + 1];

            child.keys[child.count] = parent.keys[i];
            if (!child.leaf) {
                child.children[child.count + 1] =
                    sibling.children[0];
                for (int j = 1; j <= sibling.count; j++) {
                    sibling.children[j - 1] = sibling.children[j];
                }
                sibling.children[sibling.count] = null;
            }
            parent.keys[i] = sibling.keys[0];
            for (int j = 1; j < sibling.count; j++) {
                sibling.keys[j - 1] = sibling.keys[j];
            }
            sibling.keys[sibling.count - 1] = 0;
            sibling.count--;
            child.count++;
        }

        private void merge(Node parent, int i) {
            Node left = parent.children[i];
            Node right = parent.children[i + 1];
            int leftCount = left.count;

            left.keys[leftCount] = parent.keys[i];
            for (int j = 0; j < right.count; j++) {
                left.keys[leftCount + 1 + j] = right.keys[j];
            }
            if (!left.leaf) {
                for (int j = 0; j <= right.count; j++) {
                    left.children[leftCount + 1 + j] =
                        right.children[j];
                    right.children[j] = null;
                }
            }
            left.count += right.count + 1;

            for (int j = i + 1; j < parent.count; j++) {
                parent.keys[j - 1] = parent.keys[j];
            }
            parent.keys[parent.count - 1] = 0;
            for (int j = i + 2; j <= parent.count; j++) {
                parent.children[j - 1] = parent.children[j];
            }
            parent.children[parent.count] = null;
            parent.count--;
        }

        private static void fail(String message) {
            throw new IllegalStateException(message);
        }

        // Chỉ dùng cho bộ kiểm chứng, không gọi từ insert/delete.
        private void walk(Node node, long low, long high,
                          int depth, boolean isRoot, Stats s) {
            if (node == null) {
                fail("Missing child at depth " + depth);
            }
            if (!s.seen.add(node)) {
                fail("Cycle or shared child at depth " + depth);
            }
            s.nodesVisited++;

            if (node.keys.length != 2 * t - 1
                    || node.children.length != 2 * t) {
                fail("Wrong node capacity at depth " + depth);
            }
            int minCount = isRoot ? 1 : t - 1;
            if (node.count < minCount || node.count > 2 * t - 1) {
                fail("Wrong key count at depth " + depth
                    + ": " + node.count);
            }

            long previous = low;
            for (int i = 0; i < node.count; i++) {
                long key = node.keys[i];
                if (key <= previous || key >= high) {
                    fail("Unsorted or out-of-range key " + key
                        + " at depth " + depth
                        + " with bounds (" + low + "," + high + ")");
                }
                previous = key;
            }

            if (node.leaf) {
                for (Node child : node.children) {
                    if (child != null) {
                        fail("Leaf contains a child pointer");
                    }
                }
                if (s.leafDepth == -1) {
                    s.leafDepth = depth;
                } else if (s.leafDepth != depth) {
                    fail("Leaves at different depths: "
                        + s.leafDepth + " vs " + depth);
                }
                for (int i = 0; i < node.count; i++) {
                    s.inOrder.add(node.keys[i]);
                }
                return;
            }

            // Kiểm tra chính xác k+1 con thực.
            for (int i = 0; i <= node.count; i++) {
                if (node.children[i] == null) {
                    fail("Internal node missing child " + i);
                }
            }
            for (int i = node.count + 1;
                    i < node.children.length; i++) {
                if (node.children[i] != null) {
                    fail("Stale child pointer at index " + i);
                }
            }

            // Truyền cận của TẤT CẢ tổ tiên xuống mỗi con.
            for (int i = 0; i <= node.count; i++) {
                long childLow =
                    i == 0 ? low : node.keys[i - 1];
                long childHigh =
                    i == node.count ? high : node.keys[i];
                walk(node.children[i], childLow, childHigh,
                     depth + 1, false, s);
                if (i < node.count) {
                    s.inOrder.add(node.keys[i]);
                }
            }
        }

        void verifyAgainst(TreeSet<Integer> oracle) {
            if (oracle == null) {
                throw new IllegalArgumentException("Null oracle");
            }
            if (size != oracle.size()) {
                fail("Wrong size: tree=" + size
                    + " oracle=" + oracle.size());
            }
            if (root == null) {
                if (size != 0) {
                    fail("Null root with nonzero size");
                }
                return;
            }
            if (size == 0) {
                fail("Non-null root for empty tree");
            }

            Stats s = new Stats();
            walk(root, Long.MIN_VALUE, Long.MAX_VALUE,
                 0, true, s);

            List<Integer> reference = new ArrayList<>(oracle);
            if (!s.inOrder.equals(reference)) {
                fail("In-order keys differ from oracle. actual="
                    + s.inOrder + ", expected=" + reference);
            }
            if (s.inOrder.size() != size) {
                fail("Traversal count differs from size");
            }
        }
    }

    // Mỗi step áp cùng thao tác lên cây thử nghiệm và tập chuẩn.
    static void checkStep(BTree tree, TreeSet<Integer> oracle,
                          boolean insert, int key) {
        boolean expected = insert
            ? oracle.add(key) : oracle.remove(key);
        boolean actual = insert
            ? tree.insert(key) : tree.delete(key);
        if (actual != expected) {
            throw new IllegalStateException(
                (insert ? "insert " : "delete ") + key
                + ": result mismatch, tree=" + actual
                + ", oracle=" + expected);
        }
        tree.verifyAgainst(oracle); // Kiểm tra SAU MỖI cập nhật.
    }

    public static void main(String[] args) {
        BTree tree = new BTree(2);
        TreeSet<Integer> oracle = new TreeSet<>();
        int passed = 0;

        // Đủ khóa để gây tách lá, tách nút trong và tách gốc.
        int[] additions = {
            40, 10, 20, 30, 50, 60, 70, 80, 90, 100,
            25, 35, 45, 55, 65, 75, 85, 95
        };
        for (int key : additions) {
            checkStep(tree, oracle, true, key);
            passed++;
        }

        // Hai thao tác không đổi tập khóa.
        checkStep(tree, oracle, true, 50);
        passed++;
        checkStep(tree, oracle, false, 999);
        passed++;

        // Nhiều đường xóa, có thể kích hoạt mượn/gộp/hạ gốc.
        int[] removals = {
            10, 40, 70, 25, 30, 50, 90, 80, 85,
            95, 20, 35, 45, 55, 60, 65, 75, 100
        };
        for (int key : removals) {
            checkStep(tree, oracle, false, key);
            passed++;
        }

        // Kiểm tra cực trị và khóa âm/zero.
        int[] boundaryKeys = {
            Integer.MIN_VALUE, Integer.MAX_VALUE, -1, 0
        };
        for (int key : boundaryKeys) {
            checkStep(tree, oracle, true, key);
            passed++;
        }
        for (int key : boundaryKeys) {
            checkStep(tree, oracle, false, key);
            passed++;
        }

        // Chuỗi ngẫu nhiên có thể tái hiện bằng seed cố định.
        Random random = new Random(20261128L);
        for (int i = 0; i < 500; i++) {
            int key = random.nextInt(101) - 50;
            boolean doInsert = random.nextBoolean();
            checkStep(tree, oracle, doInsert, key);
            passed++;
        }

        // Xóa hết phần còn lại bằng bản sao để không sửa
        // TreeSet trực tiếp trong vòng for-each.
        for (int key : new ArrayList<>(oracle)) {
            checkStep(tree, oracle, false, key);
            passed++;
        }

        System.out.println("All checks passed: " + passed);
        System.out.println("Final size: " + tree.size());
    }
}
```

Khi triển khai đúng và mọi bất biến được giữ, chương trình sẽ kết thúc bằng dạng:

```text
All checks passed: <số bước đã được xác minh>
Final size: 0
```

Số bước cuối cùng phụ thuộc số khóa còn trong `oracle` sau chuỗi ngẫu nhiên; do đó bài **không cố định một con số dự kiến** cho dòng `All checks passed`. Nếu bộ kiểm tra tìm thấy lỗi, chương trình ném `IllegalStateException` ở bước đầu tiên phát hiện sai, thay vì in thông báo thành công.

### Đọc mã theo mục tiêu kiểm tra

| Thành phần | Vì sao cần |
| --- | --- |
| `lowerBound` | Tìm/chèn/xóa trong nút dựa trên thứ tự khóa |
| `splitChild` | Tách nút đầy và chuyển con khi nút là nút trong |
| `borrowFromPrev`, `borrowFromNext` | Luân chuyển khóa cha/anh em, chuyển đúng cây con |
| `merge` | Gộp hai nút qua khóa cha, loại con trỏ cũ |
| `verifyAgainst` | Đối chiếu số khóa và tập khóa thực tế với oracle |
| `walk` | Kiểm tra cấu trúc theo cận tổ tiên và độ sâu lá |
| `IdentityHashMap` | Phát hiện chu trình hoặc hai cha dùng chung một nút |
| `s.inOrder` | Thu thập tất cả khóa thực để phát hiện mất/trùng/sai khóa |
| `checkStep` | Kiểm tra **ngay sau từng lần insert/delete** |
| `Random(seed)` | Tạo chuỗi thao tác ngẫu nhiên **có thể tái hiện** |

### Chỗ dễ bị bỏ qua trong bộ kiểm tra

**Không đọc khóa ngoài `count`.** Sau khi tách một nút, mảng `keys` có thể vẫn chứa số cũ ở các ô chưa sử dụng, nhưng chúng không còn là khóa logic. Validator chỉ duyệt `keys[0..count-1]`, không kiểm tra tất cả phần tử vật lý như thể chúng thuộc cây.

**Có thể kiểm tra con trỏ ngoài phạm vi.** Với mảng con trỏ được xóa sạch ở phần dư, việc đòi mọi `children[i]` ngoài `[0..count]` là `null` giúp phát hiện tham chiếu còn sót sau gộp/mượn. Nếu một hệ thống chủ đích cho phép rác ở các ô dự trữ, quy tắc đó cần chuyển thành **kiểm tra vệ sinh bộ nhớ**, không phải bất biến logic bắt buộc của mọi biến thể.

**Kiểm tra khoảng sử dụng `long`.** Nhờ đó, khóa `Integer.MIN_VALUE` và `Integer.MAX_VALUE` được xét như mọi khóa khác. Không lấy `min-1` hay `max+1` bằng kiểu `int`.

**Bộ kiểm tra độc lập với thủ tục cập nhật.** Phương thức `walk` không tin rằng `splitChild` hay `merge` đã sửa đúng; nó đọc lại **toàn bộ cấu trúc sau thao tác** và chứng minh các cận bằng một lần duyệt riêng.

### Giới hạn của ví dụ

Mã Java là **minh họa thuật toán trong RAM**, không phải bộ chỉ mục phân trang sản xuất. Nó chưa hỗ trợ khóa trùng, chạy đồng thời, nhật ký phục hồi, dữ liệu độ dài biến thiên hoặc lỗi cấp phát giữa chừng. Bộ test với seed cố định là **một tập trường hợp hữu hạn**, chưa phải chứng minh hình thức thuật toán đúng với mọi chuỗi thao tác. Phần QA học thuật sâu và thử nghiệm phần mềm thực tế có thể tiếp tục bổ sung các tình huống khác.

## 8. Kiểm tra B+ tree: phải bổ sung bất biến separator và chuỗi lá

Với B+ tree, chỉ kiểm tra số khóa, số con và chiều sâu lá **vẫn chưa đủ**. Ta sử dụng quy ước:

\[
S_i = \minKey(children[i+1]).
\]

Nghĩa là **separator trong nút trong bằng khóa nhỏ nhất của cây con ngay bên phải**. Từ đó phát sinh những điều cần kiểm tra thêm:

1. **Mục dữ liệu thật chỉ xuất hiện ở lá.** Các separator ở nút trong không được đếm là mục dữ liệu.
2. **Nút trong có `k+1` con cho `k` separator.**
3. **Các separator tăng nghiêm ngặt** trong mô hình khóa phân biệt.
4. **`S_i` bằng đúng min của cây con `children[i+1]`**, không chỉ là một cận ngẫu nhiên.
5. **Các con tuân theo khoảng nửa mở**, với dấu bằng thuộc **nhánh phải**.
6. **Tất cả lá cùng độ sâu** và đáp ứng mức lấp đầy của biến thể được chọn.
7. **Chuỗi `next`** đi qua mọi lá đúng một lần, theo thứ tự tăng.
8. Nếu có `prev`, phải có quan hệ đối xứng `leaf.next.prev == leaf`.
9. **Số mục dữ liệu** phải bằng tổng số mục ở lá và khớp oracle.

### Ví dụ: separator sai sau khi xóa khóa nhỏ nhất của lá

```text
Trước xóa:
                            [30 | 50]
                           /    |     \
                    [10,20,25] [30,40,45] [50,60]

Xóa 30 ở lá giữa, còn [40,45].

Sai: giữ gốc [30 | 50] dù min nhánh giữa đã thành 40.
Đúng theo quy ước của bài:

                            [40 | 50]
                           /    |     \
                    [10,20,25] [40,45] [50,60]
```

Nếu mức lấp đầy tối thiểu là hai mục, lá `[40,45]` vẫn hợp lệ. Nhưng nếu separator gốc không đổi, bất biến **separator=min con phải** bị phá dù `get(40)` có thể tình cờ trả đúng.

### Ví dụ: gộp lá nhưng bỏ sót cập nhật `next`

```text
Trước:
L0=[10,20] -> L1=[30,40] -> L2=[50,60] -> null

Gộp L1 vào L0 sau xóa một mục:
L0=[10,20,40]   L2=[50,60]

Đúng: L0.next = L2
Sai:  L0.next vẫn trỏ tới L1 đã tách khỏi cây
```

Quét dọc cây phân cấp có thể không thấy `L1`, nhưng duyệt qua `next` vẫn chạm vào nút cũ. Bộ kiểm tra phải **đối chiếu danh sách lá đi từ gốc** với **danh sách lá đi theo liên kết**, không chỉ kiểm tra từng lá riêng lẻ.

## 9. Mã giả kiểm tra cấu trúc và chuỗi lá B+ tree

Để kiểm tra B+ tree, ta có thể duyệt từ gốc và tạo danh sách `leavesInTreeOrder`. Bộ duyệt trả về `min`, `max` và số mục của từng cây con, rồi kiểm tra separator:

```text
validateBPlus(root):
    if root is null:
        assert recordedSize == 0
        return

    leafDepth = UNKNOWN
    seenTreeNodes = identitySet()
    leavesInTreeOrder = []

    validateNode(root, low=-infinity, high=+infinity, depth=0)
    validateLeafChain(leavesInTreeOrder)
    assert collectedLeafEntries == expectedEntries

validateNode(node, low, high, depth):
    assert node not in seenTreeNodes
    mark node as seen
    assert node's occupancy is valid by this B+ tree definition

    if node is a leaf:
        assert keys strictly increasing
        assert each key in [low, high) using proper boundary rules
        assert values have the same count as keys
        assert depth == leafDepth (or initialize leafDepth)
        leavesInTreeOrder.append(node)
        return (minKey(node), maxKey(node), entryCount(node))

    assert children.count == separators.count + 1
    assert separators strictly increasing
    for each child i:
        childLow = (i==0 ? low : separators[i-1])
        childHigh = (i==k ? high : separators[i])
        summary[i] = validateNode(child[i], childLow,
                                  childHigh, depth+1)

    for i from 0 to k-1:
        assert separators[i] == summary[i+1].min
        assert summary[i].max < summary[i+1].min

    return (summary[0].min, summary[k].max,
            sum of child entryCounts)
```

**Lưu ý về biên:** B+ tree có separator bằng min nhánh phải nên các khoảng được viết `[low,high)` thay vì `(low,high)` kiểu B-tree khóa dữ liệu ở nút trong. Với cây con ngoài cùng bên trái hoặc phải, các cận vô cực được xử lý riêng. Nếu hỗ trợ khóa trùng, dấu bằng và điều kiện `max(left)<min(right)` cần được điều chỉnh theo chính sách khóa ghép hoặc định tuyến của cài đặt.

Kiểm tra liên kết lá:

```text
validateLeafChain(leavesInTreeOrder):
    current = leavesInTreeOrder[0]
    previous = null
    visitedLeaves = identitySet()
    index = 0

    while current != null:
        assert current not in visitedLeaves
        visitedLeaves.add(current)
        assert index < leavesInTreeOrder.length
        assert current is leavesInTreeOrder[index]
        if prev links are supported:
            assert current.prev is previous
        if previous != null:
            assert previous.maxKey < current.minKey
        previous = current
        current = current.next
        index++

    assert index == leavesInTreeOrder.length
```

Kiểm tra này phát hiện:

- **Lá bị bỏ qua** trong chuỗi `next`.
- **Vòng lặp** `next` do gán nhầm.
- **Lá lạ** xuất hiện trên chuỗi nhưng không còn thuộc cây từ gốc.
- **Thứ tự lá sai** khi gộp/tách.
- **Liên kết `prev` không đối xứng**, nếu cấu trúc có `prev`.

Không có một validator chung duy nhất áp được cho mọi B+ tree: một số triển khai lưu separator rút gọn, có khóa trùng, cho phép nút với mức lấp đầy tính theo **byte**, hoặc dùng sibling link ở cả nút trong. Khi kiểm thử, **bất biến phải bắt nguồn từ hợp đồng cấu trúc đã chọn**.

## 10. Thiết kế chuỗi cập nhật để bắt lỗi sâu

Một vài tình huống đơn lẻ không thể phủ hết các nhánh của thuật toán chèn/xóa. Một kế hoạch kiểm thử tốt kết hợp **kịch bản có chủ đích** và **chuỗi ngẫu nhiên có thể tái hiện**.

### 10.1. Chuỗi kịch bản có chủ đích

| Kịch bản | Dãy thao tác gợi ý | Mục tiêu |
| --- | --- | --- |
| Cây rỗng | Xóa một khóa vắng, thêm một khóa, xóa khóa cuối | `root=null` và `size=0` đúng |
| Gốc lá đầy | Thêm khóa tăng cho tới khi gốc đầy rồi thêm một khóa nữa | Tách gốc, đồng độ sâu lá |
| Nhiều mức | Thêm đủ khóa để tạo nút trong đầy | Chuyển đủ con trỏ khi tách |
| Mượn trái | Chuẩn bị anh em trái có `t` khóa, con cần xóa có `t-1` | Đúng chiều luân chuyển khóa/con |
| Mượn phải | Chuẩn bị anh em phải có `t` khóa | Đúng khóa lên cha và con chuyển |
| Gộp | Hai anh em đều có `t-1` khóa | Cha giảm một khóa và một con |
| Xóa ở nút trong | Xóa separator dữ liệu với con trái đủ khóa | Tiền nhiệm/kế nhiệm không bị nhân đôi |
| Hạ gốc | Xóa cho tới khi gốc chỉ còn một con sau gộp | Không giữ gốc rỗng |
| Trùng/vắng mặt | Thêm lại một khóa và xóa khóa chưa có | Không thay tập khóa trái quy ước |
| Khóa biên | Dùng min/max `int` và khóa âm | Không tràn khi so sánh cận |
| Chuỗi dài | Trộn thêm/xóa với seed cố định | Tìm lỗi phát sinh sau nhiều lần sửa |

**Không nên chỉ thêm theo thứ tự tăng.** Chuỗi tăng dần thường kích hoạt nhiều tách ở một phía nhưng có thể không kích hoạt các trường hợp **mượn từ trái** hoặc **gộp nhánh giữa**.

### 10.2. Randomized differential testing

Phương pháp **kiểm thử vi sai** (*differential testing*) tạo một chuỗi lệnh và áp dụng lên SUT cùng oracle. Seed cố định giúp tái hiện:

```text
seed = 20261128
operations = random sequence of insert/delete keys in [-50, 50]

for each operation number i:
    execute on TreeSet oracle
    execute on B-tree implementation
    check result/structure/contents
    if mismatch:
        print seed, i, operation and recent history
        stop at first failure
```

Chọn miền khóa tương đối hẹp giúp **khóa trùng, xóa vắng mặt và thêm lại khóa từng bị xóa** xuất hiện thường xuyên, nhờ đó tăng cơ hội đi vào các nhánh ít gặp.

Để tăng phạm vi kiểm tra, nên thử:

- Nhiều giá trị bậc tối thiểu như `t=2,3,4,8`.
- Nhiều seed độc lập nhưng được ghi lại khi thất bại.
- Phân bố khóa ngẫu nhiên đều, khóa theo cụm và chuỗi gần tăng/giảm.
- Những chuỗi cố ý làm cây lớn lên nhiều tầng rồi co lại về rỗng.

### 10.3. Thu nhỏ chuỗi gây lỗi

Nếu lỗi chỉ xuất hiện sau 5.000 thao tác, không dễ đọc toàn bộ log. Có thể dùng kỹ thuật **giảm thiểu ca lỗi** (*delta debugging*):

1. Lưu seed và toàn bộ chuỗi thao tác đã tái hiện lỗi.
2. Thử loại bỏ một nhóm thao tác, chạy lại xem lỗi còn xảy ra không.
3. Tiếp tục giảm dần tới chuỗi ngắn hơn vẫn gây lỗi.
4. In cây trước/sau thao tác cuối để xác định bất biến bị phá.

Một chuỗi dài có thể rút xuống vài bước như “chèn để tạo hai tầng → xóa một khóa ở nút trong → gộp nhánh cuối”. Khi đó lỗi chỉ số con hoặc chuyển nhầm cây con trở nên rõ ràng hơn.

## 11. Kiểm tra bằng thao tác tìm, thứ tự và phân đoạn

Sau khi cấu trúc và oracle khớp, vẫn nên kiểm tra **API quan sát được** của cây:

- `contains(x)` cho **mọi khóa trong oracle** phải trả `true`.
- Với một tập khóa không thuộc oracle, `contains(x)` phải trả `false`.
- Duyệt theo thứ tự phải tăng và bằng `new ArrayList<>(oracle)`.
- `min()` và `max()` nếu có phải trùng `oracle.first()` và `oracle.last()` khi tập không rỗng.
- `predecessor(x)` và `successor(x)` phải tương ứng `oracle.lower(x)` và `oracle.higher(x)` nếu API có.
- Với B+ tree, kết quả `range(a,b)` phải bằng phép lọc oracle theo khoảng, giữ thứ tự và xử lý đúng biên mở/đóng.

### Ví dụ đối chiếu khoảng

Giả sử oracle có:

```text
{10, 20, 30, 40, 50, 60}
```

Kết quả cần đạt:

| Truy vấn | Kết quả |
| --- | --- |
| `range[20,50]` | `[20,30,40,50]` |
| `range(20,50)` | `[30,40]` |
| `range[25,45]` | `[30,40]` |
| `range[70,90]` | `[]` |

Đối với B+ tree, kiểm tra khoảng giúp phát hiện lỗi `leaf.next` mà một lượt `get(30)` thông thường có thể không chỉ ra.

**Cảnh báo:** việc dùng một hàm duyệt có lỗi làm oracle cũng có lỗi tương tự là điều cần tránh. Bộ kiểm tra nên thu thập mục từ **cấu trúc cây** bằng một cách độc lập với API tìm kiếm/quét mà mình đang thử.

## 12. Cách chẩn đoán khi bộ kiểm tra thất bại

Một thông báo tốt không nên chỉ là `AssertionError`. Nó nên cho biết:

- **Thao tác thứ mấy**, ví dụ `delete(40)` ở bước 273.
- **Seed** của chuỗi random hoặc danh sách thao tác tối thiểu tái hiện.
- **Đường từ gốc** tới nút lỗi, ví dụ `root/P2/P0`.
- **Loại bất biến** bị vi phạm: số khóa, khóa ngoài cận, độ sâu lá, child alias, separator hay `next`.
- **Giá trị thực tế và mong đợi**: `count=0` nhưng min `t-1=1`, hoặc `key=60` không thuộc `(20,50)`.

Ví dụ nhật ký có ích:

```text
seed=20261128 step=273 operation=delete(40)
path=root/P1/P2
VIOLATION: key 60 outside allowed interval (20,50)
treeSize=57 expectedSize=57
```

Số lượng vẫn đúng nhưng một khóa nằm sai khoảng giúp thu hẹp nghi vấn vào **chuyển con trỏ khi mượn/gộp**, thay vì lỗi `size++` hoặc `size--`.

### Thêm cảnh báo khi cập nhật bị ngắt giữa chừng

Bộ validator mô tả **trạng thái sau khi thao tác hoàn tất**. Trong quá trình tách/gộp, có thể xuất hiện những trạng thái **tạm thời** như gốc mới chưa có khóa hoặc gốc cũ chưa hạ. Không nên chạy bộ kiểm tra yêu cầu cây hoàn chỉnh đúng vào **giữa một thao tác chưa kết thúc** rồi xem trạng thái trung gian là lỗi.

Nếu có nhiều luồng hoặc nhiều tiến trình truy cập cây cùng lúc, việc “đọc toàn cây sau một cập nhật” cần một cách nhìn **nhất quán** như lock, snapshot hoặc cơ chế đồng bộ phù hợp. Nếu không, validator có thể nhìn thấy nửa trước và nửa sau của các cập nhật khác nhau, tạo báo lỗi giả.

## 13. Độ phức tạp của bộ kiểm tra

Với B-tree hoặc B+ tree hợp lệ có `n` khóa/mục và số nút `v`:

- Kiểm tra số khóa, cận và các con bằng một lần duyệt: **O(n+v)**.
- Thu thập `n` khóa theo thứ tự: **O(n)**.
- So sánh với danh sách từ `TreeSet`: **O(n)** thời gian cho lần so sánh sau khi có hai danh sách, cộng chi phí chuẩn bị oracle.
- Bộ nhớ để giữ tập nút đã thăm và danh sách khóa: **O(n+v)** trong cách cài đặt ở bài.
- Độ sâu ngăn xếp đệ quy: **O(h)** với `h` là chiều cao cây hợp lệ; nếu cấu trúc bị chu trình, tập `seen` giúp dừng khi gặp lại nút.

Vì mỗi nút hợp lệ có ít nhất một số lượng khóa nhất định, người ta thường mô tả đơn giản chi phí kiểm tra toàn cây là **O(n)**. Bộ kiểm tra **không chạy để thay thế** độ phức tạp chèn/xóa O(log n) của thuật toán B-tree với bậc cố định.

| Công việc | Khi chạy | Chi phí điển hình |
| --- | --- | --- |
| Tìm kiếm/chèn/xóa B-tree cân bằng, `t` cố định | Runtime bình thường | O(log n) |
| Kiểm tra cục bộ các nút vừa tách/mượn/gộp | Có thể hỗ trợ debug | O(t) trên mỗi nút |
| Kiểm tra bất biến **toàn cây** | Sau mỗi phép cập nhật trong test | O(n) |
| Đối chiếu toàn bộ tập với oracle | Trong test | O(n) để đọc và so sánh danh sách |
| Kiểm tra chuỗi lá B+ tree | Trong test | O(số lá + số mục được kiểm) |

Khi cần kiểm tra hệ thống lưu trang, còn có chi phí **đọc trang từ đĩa**, có thể lớn hơn CPU. Các hệ thống sản xuất thường chọn tần suất kiểm tra hợp lý, có kiểm tra cấu trúc chuyên biệt hoặc dùng bộ công cụ kiểm tra chỉ mục ngoài thời gian xử lý yêu cầu.

## 14. Những lỗi kiểm thử thường gặp

1. **Chỉ kiểm tra `size`.** Có thể mất một khóa và thêm nhầm một khóa khác nhưng số lượng vẫn đúng.
2. **Chỉ kiểm tra thứ tự trong từng nút.** Không bắt được khóa nằm sai cận do tổ tiên.
3. **Chỉ kiểm tra nút trong có đủ số con.** Không bắt được hai con trỏ cùng trỏ tới một đối tượng hoặc trỏ sai khoảng.
4. **Nhầm `array.length` với `count`.** Có thể đếm cả các ô dự trữ sau tách/gộp như khóa dữ liệu.
5. **Áp mức tối thiểu `t-1` cho gốc.** Gốc là ngoại lệ; nhưng gốc không rỗng vẫn phải có ít nhất một khóa.
6. **Cho phép gốc rỗng có một con sau khi xóa hoàn tất.** Phải hạ gốc hoặc biểu diễn cây rỗng đúng cách.
7. **Không kiểm tra độ sâu lá.** Một nhánh có thể sâu hơn nhưng mọi nút riêng lẻ vẫn có số khóa hợp lệ.
8. **Dùng phép trừ `a-b` để so sánh.** Có thể tràn với khóa `int` cực trị.
9. **Dùng `HashSet<Node>` với `equals` theo khóa để phát hiện alias.** Hai nút khác nhau có thể bị coi như cùng đối tượng; cần so sánh theo identity.
10. **Dùng oracle cùng một logic định tuyến bị lỗi của SUT.** Có nguy cơ hai bên cùng sai theo một cách.
11. **Không kiểm tra thao tác thất bại.** Thêm trùng hoặc xóa vắng mặt có thể làm biến đổi cấu trúc không mong muốn.
12. **Chỉ kiểm tra sau khi cả chuỗi cập nhật kết thúc.** Có thể không tìm ra thao tác đầu tiên phá bất biến hoặc lỗi bị thao tác sau che lấp.
13. **Không ghi seed random.** Không tái hiện được lỗi xuất hiện ngẫu nhiên.
14. **Chỉ dùng một thứ tự chèn.** Bỏ sót những nhánh mượn/gộp hiếm xảy ra.
15. **Dùng cận mở `(low,high)` của B-tree cho mọi khóa lá B+ tree.** Theo quy ước min nhánh phải, khoảng B+ tree là `[low,high)`.
16. **Đếm separator B+ tree như bản ghi.** Dẫn tới báo sai số lượng ngay khi tách lá lần đầu.
17. **Chỉ duyệt cây từ gốc trong B+ tree, không duyệt `next`.** Không phát hiện chuỗi lá đứt hoặc vòng.
18. **Kiểm tra lúc thao tác đang ở trạng thái trung gian.** Có thể đánh dấu lỗi giả trước khi gốc được điều chỉnh.
19. **Bỏ qua vấn đề đồng thời.** Validator có thể nhìn thấy trạng thái bị xé nếu các cập nhật khác vẫn chạy.
20. **Dùng kết quả test như bằng chứng tuyệt đối về tính đúng đắn.** Test hữu hạn làm tăng độ tin cậy; chứng minh hình thức và kiểm thử đa dạng vẫn có vai trò riêng.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Sau khi chèn/xóa B-tree, ba nhóm điều kiện nên kiểm tra là gì?

**Đáp án:** Bất biến cấu trúc, tập khóa/nội dung thực tế và kết quả thao tác theo API (thành công/thất bại, thay đổi đúng một khóa).

**Câu 2.** Với B-tree `t=3`, nút không phải gốc phải có bao nhiêu khóa?

**Đáp án:** Từ 2 tới 5 khóa. Gốc cây không rỗng có thể có ít khóa hơn cận dưới đó.

**Câu 3.** Một nút trong B-tree có bốn khóa thì cần bao nhiêu con thực?

**Đáp án:** Năm con, vì `k` khóa tạo `k+1` khoảng.

**Câu 4.** Vì sao phải mang theo cận của toàn bộ tổ tiên khi kiểm tra khoảng khóa?

**Đáp án:** Một cây con có thể đúng so với cha gần nhất nhưng sai so với cận của tổ tiên cao hơn; chỉ mang cận toàn đường mới phát hiện lỗi.

**Câu 5.** B-tree gốc `[40]` có lá trái `[50,60]` và lá phải `[10,20]`. Những kiểm tra cục bộ nào vẫn có thể qua, và bất biến nào chắc chắn sai?

**Đáp án:** Số khóa, thứ tự cục bộ, số con và độ sâu lá vẫn hợp lệ; **khoảng khóa cây con** sai vì nhánh trái phải nhỏ hơn 40 và nhánh phải phải lớn hơn 40.

**Câu 6.** Tại sao bộ kiểm tra dùng `IdentityHashMap` cho tập nút đã thăm?

**Đáp án:** Để phát hiện cùng **đối tượng nút** xuất hiện hai lần (chu trình hoặc dùng chung con), không phụ thuộc phương thức `equals` so sánh nội dung.

**Câu 7.** Vì sao `Integer.MIN_VALUE` và `Integer.MAX_VALUE` là ca thử cần có?

**Đáp án:** Chúng giúp phát hiện lỗi tràn khi trừ khóa hoặc tạo cận bằng `min-1`/`max+1`. Sử dụng cận `long` giúp kiểm tra toàn miền `int`.

**Câu 8.** B-tree `t=2` có gốc `[40]` và hai lá `[10]`, `[50,60]`. Xóa `10` nên cho kết quả nào?

**Đáp án:** Mượn từ phải qua cha, rồi xóa 10; gốc `[50]` và hai lá `[40]`, `[60]`.

**Câu 9.** Vì sao chỉ kiểm tra `size` không phát hiện được mọi lỗi?

**Đáp án:** Một khóa bị mất và một khóa khác xuất hiện sai có thể giữ nguyên `size`. Phải so sánh **toàn bộ tập khóa** với oracle.

**Câu 10.** `TreeSet` giúp kiểm tra điều gì và không kiểm tra được điều gì?

**Đáp án:** Giúp đối chiếu kết quả thêm/xóa, số lượng và tập khóa theo thứ tự; không tự xác minh độ sâu lá, số con, mức lấp đầy hoặc con trỏ nội bộ của B-tree.

**Câu 11.** Sau khi xóa làm gốc trong B-tree có 0 khóa và một con, cần làm gì?

**Đáp án:** Nâng con duy nhất lên thành gốc mới để hạ chiều cao; không giữ gốc rỗng như trạng thái cuối cùng của cây không rỗng.

**Câu 12.** Vì sao bộ kiểm tra trong mã chỉ đọc `keys[0..count-1]`?

**Đáp án:** Các ô còn lại của mảng là vùng dự trữ, có thể chứa giá trị cũ sau tách; chúng không thuộc tập khóa logic.

**Câu 13.** Bộ kiểm tra toàn cây nên chạy sau hay giữa các phép gán trong `splitChild`?

**Đáp án:** Sau khi một thao tác chèn/xóa hoàn tất và cây quay về trạng thái hợp lệ; trạng thái trung gian đang sửa có thể tạm vi phạm bất biến.

**Câu 14.** Vì sao chuỗi random có seed cố định hữu ích?

**Đáp án:** Khi gặp lỗi, có thể tạo lại đúng chuỗi thao tác và tìm bước đầu tiên phá bất biến, phục vụ chẩn đoán hoặc giảm thiểu ca lỗi.

**Câu 15.** Với B+ tree theo quy ước `separator=minKey(cây con phải)`, xóa khóa nhỏ nhất của lá giữa mà lá vẫn đủ mục có thể cần sửa gì?

**Đáp án:** Cập nhật separator phản ánh min mới của cây con, kể cả separator ở tổ tiên nếu min của cả cây con thay đổi.

**Câu 16.** Vì sao validator B+ tree cần đối chiếu `leavesInTreeOrder` với chuỗi `next`?

**Đáp án:** Vì một lá có thể vẫn tìm được từ gốc nhưng bị bỏ qua trong chuỗi `next`, làm truy vấn khoảng thiếu kết quả.

**Câu 17.** Trong B+ tree của bài, cận đúng cho nhánh phải của separator `30` có bao gồm `30` không?

**Đáp án:** Có. Nhánh phải chứa khóa `>=30` tới cận trên tiếp theo; cần kiểm tra khoảng kiểu **nửa mở** `[30,high)`.

**Câu 18.** Nếu bộ kiểm tra báo “size khớp nhưng khóa ngoài khoảng (20,50)” ngay sau `merge`, nên nghi ngờ loại lỗi nào?

**Đáp án:** Chuyển khóa phân cách hoặc cây con sang sai vị trí khi mượn/gộp, không nhất thiết là lỗi tăng/giảm `size`.

**Câu 19.** Thời gian kiểm tra toàn cây sau một phép cập nhật thường có bậc nào?

**Đáp án:** O(n) theo số khóa/mục được kiểm, vì phải duyệt toàn bộ cấu trúc. Nó phù hợp với test/debug nhưng không phải chi phí bắt buộc của thao tác chèn/xóa runtime.

**Câu 20.** Một lượt kiểm thử 500 thao tác random đều qua có đủ chứng minh thuật toán đúng với mọi chuỗi không?

**Đáp án:** Không. Nó tăng độ tin cậy nhưng vẫn là tập hữu hạn; cần thêm các kịch bản góc, nhiều seed/bậc cây, kiểm thử vi sai rộng hơn và lập luận bất biến.

**Điểm ghi nhớ:** Sau mỗi lần cập nhật cây nhiều nhánh, không chỉ hỏi **khóa còn hay mất**. Hãy kiểm tra **số khóa, số con, thứ tự, cận tổ tiên, độ sâu lá, gốc, con trỏ và tập khóa**. Với B+ tree, cần thêm **separator chính xác, mọi mục ở lá và liên kết giữa các lá**. Dùng một oracle có thứ tự như `TreeSet`, kiểm tra ngay sau **từng** chèn/xóa, lưu seed và dừng ở lỗi đầu tiên để truy ra đúng thao tác phá cấu trúc.
