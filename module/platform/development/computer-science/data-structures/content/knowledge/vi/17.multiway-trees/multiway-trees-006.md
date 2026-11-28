# Chèn vào B-tree bằng tách nút đầy

**B-tree** là cây tìm kiếm nhiều nhánh cân bằng, trong đó một nút có thể chứa nhiều khóa đã sắp xếp và nhiều liên kết đến các cây con. Khi thêm khóa mới, thuật toán phải tìm đúng vị trí theo thứ tự. Nhưng khác với cây tìm kiếm nhị phân, **không thể liên tục nhét khóa vào một nút đã đầy**: số khóa và số con của B-tree bị giới hạn bởi bậc cây.

Cách xử lý quan trọng là **tách nút đầy** (*node splitting*): chuyển khóa giữa của nút lên cha, chia các khóa nhỏ hơn và lớn hơn vào hai nút riêng, đồng thời phân phối lại các con trỏ con nếu nút bị tách là nút trong. Khi nút gốc đầy, thao tác tách có thể tạo **gốc mới** và làm chiều cao của toàn cây tăng một.

Bài học trình bày cơ chế chèn **từ trên xuống** (*top-down insertion*): tách nút đầy **trước khi đi sâu vào nút đó**. Đây là cách cài đặt kinh điển giúp bảo đảm nút được chọn để chèn luôn còn chỗ, không phải xử lý một chuỗi tràn từ lá quay ngược lên. Nội dung đi từ bất biến, ví dụ từng bước và mã giả đến chương trình Java tự chứa, phân tích độ phức tạp và các lỗi dễ mắc.

## 1. Các bất biến cần bảo toàn khi chèn

Ta sử dụng quy ước **bậc tối thiểu `t`** (*minimum degree*) với `t \ge 2` và giả định các khóa `int` **phân biệt**. Theo quy ước này:

| Loại nút | Số khóa tối thiểu | Số khóa tối đa | Số con nếu là nút trong |
| --- | ---: | ---: | --- |
| Nút không phải gốc | `t - 1` | `2t - 1` | Từ `t` đến `2t` |
| Gốc của cây không rỗng | 1 | `2t - 1` | Nếu là nút trong: từ 2 đến `2t` |
| Nút lá | Theo giới hạn khóa tương ứng | `2t - 1` | Không có con |

Một **nút trong có `k` khóa** phải có **đúng `k+1` con trỏ con thực**. Nếu các khóa là

\[
K_0<K_1<\cdots<K_{k-1},
\]

thì chúng phân chia miền tìm kiếm thành `k+1` khoảng, tương ứng với `k+1` cây con.

Các bất biến chính của B-tree là:

1. Khóa trong mỗi nút được **sắp tăng nghiêm ngặt**.
2. Mỗi cây con chỉ chứa các khóa thuộc **đúng khoảng** do khóa cha và các tổ tiên quy định.
3. Số khóa của mỗi nút nằm trong giới hạn, trừ trạng thái tạm thời khi thuật toán đang cập nhật.
4. Nút trong có **`k+1` con**; lá không có con.
5. **Tất cả lá cùng độ sâu**, nhờ đó cây duy trì cân bằng theo chiều cao.

Đặt `MAX_KEYS = 2t - 1`. Một nút có đúng `MAX_KEYS` khóa được gọi là **nút đầy** (*full node*). Ví dụ, `t=2` cho phép tối đa ba khóa trên một nút; `t=3` cho phép tối đa năm khóa.

> Chèn đúng không chỉ có nghĩa khóa mới xuất hiện trong cây. Sau khi hoàn thành, tất cả khóa cũ phải còn nguyên, thứ tự và khoảng cây con phải đúng, số khóa mỗi nút không vượt giới hạn và các lá vẫn cùng độ sâu.

## 2. Khi lá còn chỗ: chèn khóa theo thứ tự

Giả sử `t=2`, một lá có `[10 | 30]`. Vì sức chứa tối đa là ba khóa, có thể chèn `20` mà **không cần tách**:

```text
Trước chèn:         [10 | 30]

Dịch 30 sang phải:  [10 | _ | 30]

Ghi 20:             [10 | 20 | 30]
```

Thuật toán đặt khóa vào đúng thứ tự trong mảng khóa của lá:

```text
insertIntoNonFullLeaf(node, x):
    i = node.keyCount - 1
    while i >= 0 and x < node.keys[i]:
        node.keys[i + 1] = node.keys[i]
        i = i - 1
    node.keys[i + 1] = x
    node.keyCount = node.keyCount + 1
```

Vòng lặp **dịch từ phải sang trái** để không ghi đè giá trị chưa di chuyển. Với một lá chứa `k` khóa, chi phí đặt khóa là O(k), tối đa O(t) với quy ước bậc tối thiểu ở trên.

**Điều kiện bắt buộc:** chỉ gọi đoạn mã này khi lá **chưa đầy**, tức `keyCount < 2t - 1`. Nếu lá đã đầy, cố viết thêm một khóa có thể vượt kích thước mảng khóa hoặc phá giới hạn B-tree.

## 3. Tách một nút đầy: đưa khóa giữa lên cha

Xét `t=2` và nút đầy `[10 | 20 | 30]`, có `2t-1=3` khóa. Khóa ở vị trí `t-1=1` là **khóa giữa**, tức `20`.

```text
Nút đầy trước tách:

                    [10 | 20 | 30]

Tách:

                           [20]          <- đưa lên cha
                          /    \
                        [10]  [30]        <- hai nút còn lại
```

Với bậc tối thiểu `t` tổng quát, nút đầy có:

\[
2t-1\text{ khóa}.
\]

Tách thành ba phần:

- **`t-1` khóa nhỏ nhất** ở nút trái.
- **Khóa giữa thứ `t`** (chỉ số `t-1` nếu đánh chỉ số từ 0) được **đẩy lên cha**.
- **`t-1` khóa lớn nhất** ở nút phải.

Ví dụ `t=3`, nút đầy có năm khóa:

```text
Trước:      [10 | 20 | 30 | 40 | 50]
                       ^
                     khóa giữa

Sau:         [10 | 20]     30     [40 | 50]
               trái       lên cha    phải
```

Hai nút mới đều có đúng `t-1` khóa, bằng mức tối thiểu hợp lệ dành cho nút không phải gốc. Vì nút đầy có **số khóa lẻ**, việc chọn một khóa giữa chia được các khóa còn lại thành hai nhóm bằng nhau.

### Tách không đồng nghĩa làm mất khóa

Trước khi tách có `2t-1` khóa. Sau khi tách:

\[
(t-1)+1+(t-1)=2t-1.
\]

Khóa giữa **không bị xóa khỏi cây**; nó chuyển sang nút cha. Số khóa **trên toàn cây không thay đổi chỉ vì tách nút**. Chỉ khi thực sự ghi khóa mới vào một lá sau đó, tổng số khóa tăng thêm một.

## 4. Nếu nút đầy là nút trong: phải chuyển cả các cây con

Đây là chỗ một cài đặt B-tree thường xảy ra lỗi. Khi nút bị tách là **nút trong**, chỉ chia khóa mà quên di chuyển các con trỏ con sẽ làm sai các khoảng tìm kiếm.

Với `t=2`, nút trong đầy có ba khóa và bốn cây con:

```text
Trước tách:

                       [20 | 40 | 60]
                      /    |    |     \
                     A     B    C      D

A chứa khóa < 20
B chứa khóa trong (20, 40)
C chứa khóa trong (40, 60)
D chứa khóa > 60
```

Tách tại khóa giữa `40`:

```text
Sau tách:

                              [40]
                             /    \
                           [20]  [60]
                          /   \  /   \
                         A     B C    D
```

Nút trái `[20]` giữ hai con `A, B`. Nút phải `[60]` giữ hai con `C, D`. Mỗi nút trong mới có một khóa và đúng hai con.

Với bậc tối thiểu `t` tổng quát, nút trong đầy có `2t` cây con. Sau tách:

- `t` con đầu tiên thuộc nút trái.
- `t` con cuối thuộc nút phải.
- Khóa giữa được đưa lên cha; nó **không mang một cây con độc lập**.

| Thành phần cũ trước tách | Nơi đến |
| --- | --- |
| Khóa ở vị trí `0..t-2` | Nút trái |
| Khóa ở vị trí `t-1` | Nút cha |
| Khóa ở vị trí `t..2t-2` | Nút phải |
| Con ở vị trí `0..t-1` | Nút trái |
| Con ở vị trí `t..2t-1` | Nút phải |

**Bảo toàn thứ tự liên kết** quan trọng như bảo toàn thứ tự khóa. Nếu hai con `C`, `D` bị gán nhầm sang nút trái trong ví dụ, khóa ở những cây con đó sẽ nằm sai khoảng, và tìm kiếm có thể bỏ qua đáp án.

## 5. Chèn từ trên xuống: tách trước khi đi vào nút đầy

Có hai hướng tổ chức thuật toán chèn B-tree:

- **Từ dưới lên** (*bottom-up*): tìm lá, chèn (có thể tạo trạng thái tạm tràn), rồi tách và đẩy khóa lên cha, lặp tới khi hết tràn.
- **Từ trên xuống** (*top-down*): trên đường tới lá, **tách một nút con đã đầy trước khi đi vào nó**, sao cho lần gọi chèn ở tầng tiếp theo luôn nhận nút chưa đầy.

Bài sử dụng cách **từ trên xuống**, với hai thao tác cốt lõi:

1. `splitChild(parent, i)`: tách nút đầy `parent.children[i]` và đưa khóa giữa lên `parent`.
2. `insertNonFull(node, x)`: chèn khóa `x` vào **cây con có gốc `node`**, với tiền điều kiện `node` **không đầy**.

Điều kiện then chốt của `splitChild` là **`parent` còn chỗ nhận thêm một khóa**. Thuật toán xử lý gốc đầy trước, rồi chỉ đi xuống các nút đã được bảo đảm chưa đầy. Vì vậy, khi cần tách một con đầy trên đường đi xuống, nút cha hiện tại còn chỗ.

### Thuật toán tổng thể

```text
insert(tree, x):
    nếu tree.root là null:
        tạo một lá chứa x, gán làm root
        trả về

    nếu chính sách không cho khóa trùng và x đã có:
        không thay đổi cây
        trả về

    nếu root đang đầy (2t - 1 khóa):
        tạo newRoot rỗng, đánh dấu là nút trong
        newRoot.children[0] = root
        splitChild(newRoot, 0)
        root = newRoot

    insertNonFull(root, x)
```

Khi gốc đầy, ta tạo một gốc mới có **0 khóa tạm thời**, gắn gốc cũ làm con đầu tiên rồi tách gốc cũ. Sau `splitChild`, gốc mới nhận khóa giữa và có hai con, trở thành **gốc hợp lệ có một khóa**.

**Không được để nút gốc rỗng là trạng thái kết thúc của một B-tree không rỗng.** Trạng thái 0 khóa chỉ xuất hiện giữa những bước tổ chức lại.

### `splitChild(parent, i)`

```text
splitChild(parent, i):
    # Tiền điều kiện:
    #   parent chưa đầy
    #   child = parent.children[i] đang đầy (2t - 1 khóa)

    child = parent.children[i]
    right = nút mới có cùng trạng thái leaf với child
    middle = child.keys[t - 1]

    sao chép child.keys[t .. 2t-2] sang right.keys[0 .. t-2]
    right.keyCount = t - 1

    nếu child là nút trong:
        chuyển child.children[t .. 2t-1]
        sang right.children[0 .. t-1]

    child.keyCount = t - 1

    dịch các con hiện có của parent từ phải sang trái
    để mở chỗ tại parent.children[i + 1]
    parent.children[i + 1] = right

    dịch các khóa của parent từ phải sang trái
    để mở chỗ tại parent.keys[i]
    parent.keys[i] = middle
    parent.keyCount += 1
```

Trong thao tác này, `child` cũ **được tái sử dụng làm nút trái**. Nút `right` là nút vừa cấp phát. Khi nút đầy là nút trong, ta phải chuyển `t` con trỏ sang `right`, đồng thời **bỏ những tham chiếu cũ** tới các con đã chuyển khỏi vùng con đang sử dụng của nút trái để tránh cấu trúc nội bộ bị giữ sai hoặc có tham chiếu thừa.

### `insertNonFull(node, x)`

```text
insertNonFull(node, x):
    # Tiền điều kiện: node chưa đầy.

    nếu node là lá:
        dịch các khóa lớn hơn x sang phải
        ghi x vào đúng vị trí
        tăng keyCount
        trả về

    tìm chỉ số i sao cho x thuộc khoảng của children[i]

    nếu children[i] đang đầy:
        splitChild(node, i)
        # Một khóa giữa vừa được thêm vào node ở vị trí i.
        nếu x lớn hơn node.keys[i]:
            i = i + 1

    insertNonFull(node.children[i], x)
```

Sau khi tách, con cũ bị chia thành **hai con**, vì vậy phải **so sánh lại với khóa giữa vừa đẩy lên** để biết đi bên trái hay bên phải. Nếu bỏ bước này, thuật toán có thể chèn khóa vào **sai cây con**.

Trong mô hình không cho trùng khóa, ta có thể kiểm tra khóa đã tồn tại **trước khi bắt đầu sửa cây**. Nhờ đó, nếu `x` bằng khóa giữa sau tách thì đó là trường hợp không xảy ra với một khóa mới hợp lệ.

## 6. Truy vết đầy đủ với `t=2`

Ta chèn lần lượt các khóa:

```text
10, 20, 30, 40, 50, 60, 70, 80, 90, 100
```

Với `t=2`, mỗi nút chứa tối đa **3 khóa**, nút không phải gốc có tối thiểu **1 khóa**.

### Các bước đầu: gốc từ lá chuyển thành nút trong

```text
Chèn 10:
    [10]

Chèn 20:
    [10 | 20]

Chèn 30:
    [10 | 20 | 30]      <- gốc đầy

Trước khi chèn 40, tách gốc cũ:
           [20]
          /    \
        [10]  [30]

Đi về nhánh phải, thêm 40:
           [20]
          /    \
        [10] [30 | 40]
```

Gốc cũ đang có ba khóa trước lần thêm 40. Thuật toán **không** cố chèn `40` vào gốc đầy rồi mới tách; nó tách gốc trước, sau đó định tuyến khóa `40` tới lá phải còn chỗ.

### Tách nút con đầy

```text
Chèn 50:
               [20]
              /    \
            [10]  [30 | 40 | 50]      <- lá phải đầy

Trước khi chèn 60:
  tách lá phải và đưa khóa 40 lên cha

                     [20 | 40]
                    /    |    \
                  [10]  [30]  [50]

  60 > 40, đi con ngoài cùng bên phải rồi chèn:

                     [20 | 40]
                    /    |    \
                  [10]  [30]  [50 | 60]
```

Tiếp tục:

```text
Sau chèn 70:
                     [20 | 40]
                    /    |    \
                  [10]  [30]  [50 | 60 | 70]   <- đầy

Trước khi chèn 80, tách lá phải tại khóa 60:

                       [20 | 40 | 60]
                      /    |    |     \
                    [10] [30] [50]  [70 | 80]
                      gốc bây giờ đầy
```

### Chèn 90: tách **gốc là nút trong**

Trước lần thêm `90`, gốc `[20 | 40 | 60]` đã đầy. Gốc này có **bốn con**: `[10]`, `[30]`, `[50]` và `[70 | 80]`.

Thuật toán tạo gốc mới, đẩy `40` lên và phân các con thành hai nhóm:

```text
Trước:

                         [20 | 40 | 60]
                        /    |    |      \
                      [10] [30] [50]  [70 | 80]

Tách gốc:

                               [40]
                             /      \
                           [20]     [60]
                          /   \     /    \
                        [10] [30] [50] [70 | 80]
```

Khóa `90` lớn hơn `40` và `60`, nên đi tới lá `[70 | 80]` và thêm:

```text
                               [40]
                             /      \
                           [20]     [60]
                          /   \     /    \
                        [10] [30] [50] [70 | 80 | 90]
```

Tất cả các lá ban đầu ở độ sâu 1; sau khi tách gốc, **tất cả lá cùng chuyển xuống độ sâu 2**. Đây là lý do việc tăng chiều cao không phá điều kiện cân bằng.

### Chèn 100: tách một lá ở tầng dưới

Nút lá cuối `[70 | 80 | 90]` đã đầy. Khi xuống từ nút trong `[60]`, thuật toán tách nó tại khóa `80`:

```text
                               [40]
                             /      \
                           [20]   [60 | 80]
                          /   \    /   |     \
                        [10] [30] [50] [70]   [90]
```

Sau đó `100>80`, đi lá ngoài cùng bên phải và thêm:

```text
                               [40]
                             /      \
                           [20]   [60 | 80]
                          /   \    /   |      \
                        [10] [30] [50] [70] [90 | 100]
```

Toàn bộ **10 khóa phân biệt** vẫn tồn tại đúng một lần; mọi nút không phải gốc có 1–3 khóa, mỗi nút trong có số con bằng số khóa cộng một và tất cả lá ở cùng độ sâu.

### Bảng tóm tắt các điểm tách

| Khóa đang thêm | Nút đầy được tách trước khi đi sâu | Khóa được đẩy lên | Kết quả đáng chú ý |
| ---: | --- | ---: | --- |
| 40 | Gốc lá `[10,20,30]` | 20 | Tạo gốc trong mới |
| 60 | Lá `[30,40,50]` | 40 | Gốc thành `[20,40]` |
| 80 | Lá `[50,60,70]` | 60 | Gốc thành `[20,40,60]` |
| 90 | Gốc trong `[20,40,60]` | 40 | Tạo gốc mới; phân lại bốn cây con |
| 100 | Lá `[70,80,90]` | 80 | Nút cha thành `[60,80]` |

Các bước tách diễn ra **trước khi ghi khóa tương ứng vào lá**, nên `splitChild` bảo toàn tất cả khóa đã có; việc thêm khóa mới diễn ra ở cuối đường đi.

## 7. Cài đặt Java hoàn chỉnh cho chèn/tìm

Chương trình sau lưu các khóa `int` phân biệt, cho phép chọn bậc tối thiểu `t>=2`, cài đặt `contains`, `insert`, `splitChild` và in cấu trúc cây. Mỗi nút có một **mảng khóa với sức chứa `2t-1`** và một **mảng liên kết con với sức chứa `2t`**. Biến `count` xác định **số khóa thật sự dùng**, không phải độ dài vật lý của mảng.

```java
public class BTreeInsertSplitDemo {
    static final class Node {
        final int[] keys;
        final Node[] children;
        final boolean leaf;
        int count = 0;

        Node(int t, boolean leaf) {
            this.keys = new int[2 * t - 1];
            this.children = new Node[2 * t];
            this.leaf = leaf;
        }
    }

    static final class BTree {
        private final int t;
        private Node root;
        private int size = 0;

        BTree(int minimumDegree) {
            if (minimumDegree < 2
                    || minimumDegree > Integer.MAX_VALUE / 2) {
                throw new IllegalArgumentException("Invalid degree");
            }
            this.t = minimumDegree;
        }

        int size() {
            return size;
        }

        boolean contains(int key) {
            Node current = root;
            while (current != null) {
                int i = 0;
                while (i < current.count && key > current.keys[i]) {
                    i++;
                }
                if (i < current.count && key == current.keys[i]) {
                    return true;
                }
                if (current.leaf) {
                    return false;
                }
                current = current.children[i];
            }
            return false;
        }

        boolean insert(int key) {
            if (root == null) {
                root = new Node(t, true);
                root.keys[0] = key;
                root.count = 1;
                size = 1;
                return true;
            }

            // Chính sách minh họa: không cho phép khóa trùng.
            // Kiểm tra trước khi tách để không đổi cấu trúc vô ích.
            if (contains(key)) {
                return false;
            }

            if (root.count == 2 * t - 1) {
                Node newRoot = new Node(t, false);
                newRoot.children[0] = root;
                splitChild(newRoot, 0);
                root = newRoot;
            }

            insertNonFull(root, key);
            size++;
            return true;
        }

        // Tiền điều kiện:
        // parent chưa đầy, parent.children[index] có 2t - 1 khóa.
        private void splitChild(Node parent, int index) {
            Node full = parent.children[index];
            Node right = new Node(t, full.leaf);
            int middle = full.keys[t - 1];

            // Chuyển t-1 khóa lớn sang nút phải.
            right.count = t - 1;
            for (int j = 0; j < t - 1; j++) {
                right.keys[j] = full.keys[j + t];
            }

            // Nếu là nút trong, chuyển t con lớn sang phải.
            if (!full.leaf) {
                for (int j = 0; j < t; j++) {
                    right.children[j] = full.children[j + t];
                    full.children[j + t] = null;
                }
            }
            // Nút cũ trở thành nút trái, chỉ còn t-1 khóa.
            full.count = t - 1;

            // Mở vị trí index+1 trong mảng con của cha.
            for (int j = parent.count; j >= index + 1; j--) {
                parent.children[j + 1] = parent.children[j];
            }
            parent.children[index + 1] = right;

            // Mở vị trí index trong mảng khóa của cha.
            for (int j = parent.count - 1; j >= index; j--) {
                parent.keys[j + 1] = parent.keys[j];
            }
            parent.keys[index] = middle;
            parent.count++;
        }

        // Tiền điều kiện: node có ít hơn 2t-1 khóa.
        private void insertNonFull(Node node, int key) {
            int i = node.count - 1;

            if (node.leaf) {
                // Dịch từ phải sang trái; ghi khóa mới vào lá.
                while (i >= 0 && key < node.keys[i]) {
                    node.keys[i + 1] = node.keys[i];
                    i--;
                }
                node.keys[i + 1] = key;
                node.count++;
                return;
            }

            // Chọn cây con theo khoảng khóa.
            while (i >= 0 && key < node.keys[i]) {
                i--;
            }
            i++;

            if (node.children[i].count == 2 * t - 1) {
                splitChild(node, i);
                // Khóa giữa vừa xuất hiện tại node.keys[i].
                if (key > node.keys[i]) {
                    i++;
                }
            }

            insertNonFull(node.children[i], key);
        }

        void printTree() {
            printNode(root, 0);
        }

        private void printNode(Node node, int depth) {
            if (node == null) {
                System.out.println("(empty)");
                return;
            }
            StringBuilder line = new StringBuilder();
            for (int j = 0; j < depth; j++) {
                line.append("  ");
            }
            line.append("[");
            for (int j = 0; j < node.count; j++) {
                if (j > 0) {
                    line.append(", ");
                }
                line.append(node.keys[j]);
            }
            line.append("]");
            System.out.println(line);

            if (!node.leaf) {
                for (int j = 0; j <= node.count; j++) {
                    printNode(node.children[j], depth + 1);
                }
            }
        }
    }

    public static void main(String[] args) {
        BTree tree = new BTree(2);
        int[] values = {
            10, 20, 30, 40, 50,
            60, 70, 80, 90, 100
        };

        for (int x : values) {
            tree.insert(x);
        }

        tree.printTree();
        System.out.println("size = " + tree.size());
        System.out.println("contains(70) = " + tree.contains(70));
        System.out.println("contains(75) = " + tree.contains(75));
        System.out.println("insert(40) = " + tree.insert(40));
        System.out.println("size after duplicate = " + tree.size());
    }
}
```

Kết quả dự kiến:

```text
[40]
  [20]
    [10]
    [30]
  [60, 80]
    [50]
    [70]
    [90, 100]
size = 10
contains(70) = true
contains(75) = false
insert(40) = false
size after duplicate = 10
```

### Đọc mã theo các bất biến

| Dòng ý tưởng | Lý do |
| --- | --- |
| `root.count == 2*t-1` | Gốc đầy phải được tách trước khi chèn vào cây |
| `middle = full.keys[t-1]` | Lấy đúng khóa giữa (đánh số từ 0) |
| `right.keys[j] = full.keys[j+t]` | Chuyển đúng `t-1` khóa lớn sang nút phải |
| Chuyển `full.children[j+t]` | Với nút trong, phân chia đúng `t` con lớn |
| Dịch con của cha trước khi gắn `right` | Không ghi đè những con đã có của cha |
| Dịch khóa của cha rồi đặt `middle` | Giữ thứ tự khóa và số con tương ứng |
| `if (key > node.keys[i]) i++` | Chọn lại bên phải sau khi khóa giữa được đẩy lên |
| `size++` chỉ sau khi chèn thành công | Một lần tách không làm tăng tổng số khóa |

Phương thức `contains` quét tối đa `2t-1` khóa trong một nút. Cách này giúp mã rõ ràng khi `t` nhỏ; nếu nút rất lớn, có thể dùng tìm nhị phân để giảm số phép so sánh trong nút.

Mảng `keys` vẫn có thể còn những **giá trị số cũ** ở các ô sau `count` khi vừa tách; chúng **không thuộc tập khóa logic** của nút và không được đọc qua các thao tác tìm kiếm/chèn. Với mảng con trỏ `children`, ví dụ còn đặt `null` ở các ô vừa chuyển khỏi nút trái để tránh giữ những liên kết thừa ngoài số con đang dùng.

**Giới hạn minh họa:** Chương trình tập trung vào thêm/tìm khóa phân biệt, chưa có xóa, đồng bộ truy cập đồng thời, xử lý lỗi tài nguyên nâng cao, hay lưu/đọc nút theo trang đĩa. Các phương thức giả định không xảy ra lỗi cấp phát giữa chừng; một thư viện sản xuất cần quy định hành vi khi thao tác cấp phát hoặc ghi dữ liệu thất bại.

## 8. Vì sao thuật toán top-down giữ được bất biến?

Ta có thể xét theo từng bước:

### 8.1. Gốc luôn được xử lý trước

Nếu gốc chưa đầy, thuật toán bắt đầu từ một nút có đủ chỗ. Nếu gốc đã đầy, nó tạo gốc mới và tách gốc cũ. Sau đó gốc mới có một khóa, hai con và chưa đầy vì `t \ge 2`.

### 8.2. Không đi vào một nút đầy

Hàm `insertNonFull(node, x)` chỉ được gọi khi `node` chưa đầy. Nếu `node` là nút trong và đứa con cần đi tới đã đầy, chương trình gọi `splitChild(node, i)` **ngay tại nút cha còn chỗ**. Sau phép tách, hai nút con mới đều có `t-1` khóa, chắc chắn chưa đầy.

Như vậy, lời gọi đệ quy tiếp theo vẫn thỏa tiền điều kiện: **nút được đi vào còn chỗ**.

### 8.3. Tách nút bảo toàn trật tự tìm kiếm

Một nút đầy có các khóa đã sắp. Khi lấy khóa giữa lên cha:

- Các khóa bên trái khóa giữa được giữ trong nút trái.
- Các khóa bên phải khóa giữa được chuyển sang nút phải.
- Các cây con cũng đi theo nhóm khoảng tương ứng.
- Khóa giữa xuất hiện ở đúng vị trí phân cách trong cha.

Do đó, các khoảng khóa vẫn đúng. Việc so sánh lại `key` với khóa giữa giúp chọn chính xác một trong hai cây con mới.

### 8.4. Các lá vẫn cùng độ sâu

Nếu tách một nút không phải gốc, hai nút sau tách vẫn nằm ở **cùng độ sâu** với nút cũ. Khi tách gốc, gốc mới xuất hiện **phía trên toàn bộ cây**, nên độ sâu của mọi lá đều tăng một. Chèn khóa vào một lá không tạo thêm một tầng riêng cho lá đó.

Vì vậy, sau một lần chèn hoàn tất, bất biến mọi lá cùng độ sâu vẫn được giữ.

### 8.5. Vì sao không cần sửa tràn từ lá lên?

Đến thời điểm ghi `key` vào lá, nút lá **chưa đầy** do tiền điều kiện của `insertNonFull`. Thêm một khóa chỉ đưa số khóa của nó lên **tối đa `2t-1`**, vẫn hợp lệ. Khóa vừa thêm không làm nút bị tràn, nên thuật toán không cần quay ngược lên để tách thêm.

## 9. Phân tích độ phức tạp

Gọi:

- `n` là số khóa đã có trước khi thêm.
- `t \ge 2` là bậc tối thiểu.
- `h` là chiều cao cây tính theo số cạnh từ gốc tới lá.

Từ bất biến B-tree, với cây không rỗng:

\[
h\le \log_t\left(\frac{n+1}{2}\right).
\]

Thuật toán đi từ gốc xuống **một đường duy nhất**. Ở mỗi tầng, nó có thể tìm vị trí khóa, tách tối đa một nút con đầy đang được chọn, rồi đi tiếp vào một trong hai nút sau tách.

| Công việc | Chi phí trong mô hình mảng khóa/con trỏ |
| --- | --- |
| Chọn nhánh bằng quét các khóa trong nút | O(t) |
| Chèn khóa vào một lá chưa đầy | O(t) do dịch tối đa `2t-2` khóa |
| `splitChild` | O(t) để chuyển khóa, con và dịch các ô ở cha |
| Số tầng được đi qua | O(log_t n) |
| Tổng thời gian chèn với `t` biến thiên | O(t log_t n) theo mô hình đơn giản |
| Tổng thời gian khi `t` là hằng số | O(log n) |
| Ngăn xếp đệ quy `insertNonFull` | O(log_t n) tầng |

**Lưu ý về kiểm tra khóa trùng:** mã Java gọi `contains` trước khi chèn. Đây là một lượt tìm thêm, nhưng vẫn có cùng bậc O(t log_t n) theo mô hình quét tuyến tính trong từng nút; nó không đổi bậc độ phức tạp tổng thể.

Khi tổ chức mỗi nút B-tree trong **một trang lưu trữ**, số trang cần đọc dọc một đường tìm kiếm có thể tỷ lệ với O(log_t n), nhờ fan-out lớn. Tuy vậy, việc tách nút và cập nhật cha còn có thể cần ghi thêm trang. Không nên đồng nhất số phép so sánh CPU, số lần chuyển trang logic và số I/O thiết bị thực tế: trang có thể đã nằm trong bộ nhớ đệm, và cơ sở dữ liệu thường có thêm cơ chế quản lý ghi.

### B-tree và cây tìm kiếm nhị phân

| Tiêu chí | Cây nhị phân tìm kiếm cân bằng | B-tree |
| --- | --- | --- |
| Khóa trên mỗi nút | Thường 1 | Có thể nhiều khóa |
| Số nhánh trên nút trong | Tối đa 2 | Từ `t` đến `2t`, trừ ngoại lệ gốc |
| Độ cao cân bằng | O(log n) | O(log_t n) |
| Chi phí công việc trong một nút | O(1) | Có thể O(t) nếu dùng mảng khóa và quét tuyến tính |
| Lợi ích nổi bật khi dữ liệu theo trang | Có thể cần nhiều tầng hơn | Một trang chứa nhiều khóa và liên kết, tăng fan-out |

B-tree không tự động nhanh hơn mọi cấu trúc trong RAM. Hiệu năng thực tế còn tùy kích thước khóa, bộ nhớ đệm CPU, bậc cây, chính sách cập nhật và đặc điểm truy cập.

## 10. Các trường hợp biên và lỗi thường gặp

1. **Nhầm `t` với số khóa tối đa.** Theo *minimum degree*, nút có tối đa **`2t-1` khóa** và `2t` con; không phải `t` khóa.
2. **Chèn ngay vào nút đầy rồi mới dịch mảng mà không có chỗ tạm.** Với chèn top-down, phải tách trước để tránh ghi vượt sức chứa.
3. **Chọn sai khóa giữa.** Với mảng đánh từ 0, khóa giữa của nút `2t-1` khóa là `keys[t-1]`.
4. **Chia `t` khóa sang trái và `t-1` sang phải sau khi đẩy khóa giữa.** Khi đã đẩy một khóa lên, hai bên đều còn **`t-1` khóa**.
5. **Tách nút trong nhưng quên chia con.** Nút đầy `2t-1` khóa có `2t` con, cần chuyển `t` con lớn sang nút phải.
6. **Mở chỗ trong cha theo chiều trái sang phải.** Phép gán có thể ghi đè khóa hoặc liên kết chưa chuyển; khi dùng vòng lặp phải dịch từ cuối về đầu.
7. **Không xử lý gốc đầy.** Tách gốc cần tạo một gốc mới, giúp tăng chiều cao toàn cây đúng cách.
8. **Không so sánh lại khóa mới với khóa giữa sau tách.** Thuật toán có thể chọn nhánh trái mặc dù khóa cần chèn thuộc nhánh phải.
9. **Cho rằng tách làm tăng tổng số khóa.** Tách chỉ chuyển khóa cũ; tổng số khóa tăng một sau khi ghi **khóa mới** vào lá.
10. **Cho phép chèn khóa trùng mà không có chính sách.** Ví dụ Java từ chối trùng trước khi sửa cây. Nếu cần lưu nhiều bản ghi cùng khóa, phải xác định quy tắc riêng.
11. **Quên phân biệt `count` với độ dài mảng khóa.** Sau tách, các ô dự trữ có thể còn giá trị vật lý nhưng không thuộc tập khóa của nút.
12. **Cho rằng cây luôn tăng chiều cao khi tách bất kỳ nút nào.** Chỉ khi tạo **gốc mới** do tách gốc, chiều cao toàn cây mới tăng.
13. **Đem thuật toán tách trước của `2t-1` khóa áp máy móc cho mọi định nghĩa “order `m`”.** Nếu tài liệu dùng số con tối đa `m` lẻ, quy tắc tách nút đầy có thể khác; cần xác nhận tham số.
14. **Quên kiểm tra các khoảng khóa từ tổ tiên.** Cây vẫn có thể đúng số khóa/số con nhưng sai tính chất tìm kiếm nếu các liên kết con bị phân nhóm nhầm.
15. **Nhầm O(log n) theo bậc cố định với chi phí O(1) cho một lần chèn.** Chèn có thể đi qua nhiều tầng và phát sinh cấp phát/tách nút.

## 11. Tự kiểm tra

**Câu 1.** Với B-tree bậc tối thiểu `t=3`, một nút đầy có bao nhiêu khóa? Chỉ số khóa giữa theo cách đánh từ 0 là bao nhiêu?

**Đáp án:** Nút đầy có `2t-1=5` khóa, khóa giữa nằm ở chỉ số `t-1=2`.

**Câu 2.** Tách nút đầy `[10,20,30,40,50]` trong cây `t=3` sẽ đưa khóa nào lên cha? Hai nút mới giữ những khóa nào?

**Đáp án:** Đưa `30` lên cha; nút trái giữ `[10,20]`, nút phải giữ `[40,50]`.

**Câu 3.** Nếu nút đầy `t=3` là nút trong, trước tách nó có bao nhiêu con? Sau tách, mỗi nút trái/phải có bao nhiêu con?

**Đáp án:** Trước tách có `2t=6` con; sau tách mỗi nút mới giữ `t=3` con, phân theo các khoảng khóa.

**Câu 4.** Vì sao không thể chỉ chia khóa mà giữ nguyên toàn bộ liên kết con ở nút trái khi tách một nút trong?

**Đáp án:** Các cây con ở phía phải khóa giữa sẽ nằm sai khoảng và nút trái sẽ có nhiều con hơn `keyCount+1`; cây có thể tìm kiếm sai hoặc vi phạm cấu trúc.

**Câu 5.** Trong cây `t=2`, tại sao thao tác chèn `40` vào gốc đầy `[10,20,30]` khiến cây có gốc `[20]` và hai lá `[10]`, `[30,40]`?

**Đáp án:** Tách gốc trước: đưa `20` lên gốc mới, hai lá giữ `10` và `30`. Vì `40>20`, thêm nó vào lá phải còn chỗ.

**Câu 6.** Sau khi tách nút con tại chỉ số `i`, thuật toán cần làm gì trước khi đi xuống?

**Đáp án:** So sánh khóa mới với khóa giữa vừa thêm ở `parent.keys[i]`. Nếu lớn hơn, chọn con bên phải ở chỉ số `i+1`; nếu nhỏ hơn, giữ con bên trái `i`. Trường hợp bằng được xử lý theo chính sách khóa trùng.

**Câu 7.** Nút trong `[20,40,60]` có các cây con `A,B,C,D`. Khi tách tại khóa giữa 40, các con phải phân thế nào?

**Đáp án:** Nút trái `[20]` giữ `A,B`; nút phải `[60]` giữ `C,D`; `40` được đưa lên cha.

**Câu 8.** Khi tách gốc của một cây cao `h`, chiều cao mới là bao nhiêu? Điều kiện về độ sâu của các lá còn đúng không?

**Đáp án:** Chiều cao mới là `h+1`. Tất cả lá cùng tăng độ sâu một nên vẫn cùng độ sâu.

**Câu 9.** Một lần `splitChild` có tạo thêm khóa dữ liệu mới không? Vì sao?

**Đáp án:** Không. Nó chỉ phân phối lại các khóa đã có giữa nút trái, cha và nút phải. Tổng số khóa chỉ tăng khi `insertNonFull` thực sự ghi khóa mới vào lá.

**Câu 10.** Với `t=2`, sau khi tách một nút đầy ba khóa, mỗi nút con mới có bao nhiêu khóa và có còn đầy không?

**Đáp án:** Mỗi nút có một khóa, bằng `t-1`, nên **chưa đầy** vì mức tối đa là ba khóa.

**Câu 11.** Tại sao chèn từ trên xuống yêu cầu cha phải còn chỗ trước khi tách một con đầy?

**Đáp án:** Tách đẩy một khóa giữa lên cha. Nếu cha cũng đầy, cha không có ô để nhận khóa; xử lý các nút đầy từ trên xuống giúp cha luôn còn chỗ lúc tách con.

**Câu 12.** B-tree `t=3` có các nút tối đa năm khóa. Nếu mỗi nút được lưu bằng mảng có năm ô, cần dùng đại lượng nào để biết số khóa đang có thật?

**Đáp án:** Biến `keyCount` hoặc `count`, không phải độ dài vật lý năm ô của mảng.

**Câu 13.** Thuật toán chèn B-tree `t` bằng cách quét tuyến tính trong nút và tách khi cần có thời gian O(?) theo `t` và `n`?

**Đáp án:** O(`t\log_t n`) theo mô hình một thao tác khóa/con trỏ tốn hằng số, và O(log n) nếu `t` cố định.

**Câu 14.** Vì sao một B-tree có nhiều nhánh có thể phù hợp hơn cây nhị phân cho chỉ mục lưu trữ theo trang?

**Đáp án:** Một trang có thể chứa nhiều khóa và con trỏ, tăng fan-out và giảm số tầng. Tìm theo một đường thường cần ít lần chuyển trang hơn, dù vẫn phải xử lý nhiều khóa trong từng trang.

**Câu 15.** Sau khi chèn thành công, nên kiểm tra những bất biến nào trước khi kết luận cây đúng?

**Đáp án:** Khóa mỗi nút sắp tăng; số khóa trong giới hạn; nút trong có `keyCount+1` con; mọi cây con ở đúng khoảng; tất cả lá cùng độ sâu; tập khóa cũ không mất và khóa mới xuất hiện đúng một lần theo chính sách khóa phân biệt.

**Điểm ghi nhớ:** Trong B-tree có bậc tối thiểu `t`, nút đầy có **`2t-1` khóa**. Tách nút đầy bằng cách **đưa khóa giữa lên cha**, giữ **`t-1` khóa** ở mỗi nút trái/phải và, với nút trong, chia **`t` con** cho mỗi bên. Thuật toán chèn từ trên xuống **tách trước khi đi vào nút đầy**, nên luôn tới được một lá còn chỗ; nếu gốc đầy, tạo gốc mới để tăng chiều cao **đồng đều**. Khi các bất biến được giữ, chèn có chi phí O(log n) với `t` cố định.
