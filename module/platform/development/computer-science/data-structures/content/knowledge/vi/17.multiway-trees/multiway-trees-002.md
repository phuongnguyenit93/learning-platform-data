# Cây 2–3, cây 2–3–4 và quy tắc số con

Trong cây tìm kiếm nhị phân, mỗi nút có tối đa hai nhánh con. **Cây 2–3** (*2–3 tree*) và **cây 2–3–4** (*2–3–4 tree*) mở rộng ý tưởng này: một nút có thể chứa **nhiều khóa đã sắp xếp** và định tuyến sang **nhiều cây con**. Nhờ cho phép các nút có số nhánh khác nhau nhưng vẫn buộc mọi lá nằm ở cùng độ sâu, hai cấu trúc duy trì chiều cao O(log n) khi thêm và xóa khóa.

Điểm dễ nhầm nhất nằm ở tên gọi: **nút 2, nút 3, nút 4 được đặt tên theo số nhánh con tiềm năng, không phải số khóa**. Một nút 3 có **hai khóa**; một nút 4 có **ba khóa**. Với nút trong chứa `k` khóa phân biệt, ta cần `k + 1` nhánh con để phân chia đúng các khoảng tìm kiếm.

Bài này đi từ cách biểu diễn nút, bất biến về khoảng khóa và độ cao, đến cách tìm kiếm, chèn và tách nút, xử lý xóa, phân tích độ phức tạp và ví dụ Java cài đặt thao tác thêm/tìm cho cây 2–3–4.

## 1. Quy tắc cơ bản: tên nút chỉ số con

Với một **nút trong** (*internal node*) của cây tìm kiếm nhiều nhánh, các khóa được sắp tăng nghiêm ngặt:

\[
K_0 < K_1 < \cdots < K_{k-1}.
\]

Các khóa tạo ra `k + 1` khoảng giá trị, do đó nút trong có `k + 1` con trỏ con:

\[
P_0, P_1, \ldots, P_k.
\]

Ba kiểu nút cơ bản:

| Tên nút | Số khóa lưu trong nút | Số nhánh con của nút trong | Hình thức |
| --- | ---: | ---: | --- |
| **Nút 2** (*2-node*) | 1 | 2 | `[K0]` |
| **Nút 3** (*3-node*) | 2 | 3 | `[K0 \| K1]` |
| **Nút 4** (*4-node*) | 3 | 4 | `[K0 \| K1 \| K2]` |

Sơ đồ:

```text
Nút 2:                 Nút 3:                     Nút 4:
      [20]                   [20 | 40]                  [20 | 40 | 60]
      /  \                   /   |   \                  /    |    |    \
    P0    P1               P0    P1   P2              P0    P1   P2    P3

  1 khóa, 2 con         2 khóa, 3 con              3 khóa, 4 con
```

**Cần phân biệt nút trong và lá:** nút lá có thể lưu một, hai hoặc ba khóa tùy loại cây, nhưng **không có con trỏ đi xuống cây con**. Các con số 2, 3, 4 mô tả số nhánh **nếu nút đó là nút trong**. Cây lá chỉ gồm một nút vẫn là cây hợp lệ khi chứa số khóa cho phép.

### Các khoảng tìm kiếm

Ví dụ nút 3 giữ hai khóa `[20 | 40]`:

```text
                      [20 | 40]
                      /   |   \
                     /    |    \
                x < 20   20<x<40  x > 40
                   P0       P1      P2
```

Nếu cần tìm `35`, chỉ chọn nhánh `P1`. Nếu cần tìm `50`, chọn `P2`. Nếu đang dùng mô hình B-tree với khóa dữ liệu lưu trong cả nút trong, tìm `20` hoặc `40` có thể kết thúc ngay tại nút đó.

Trong bài, ta giả định **các khóa không trùng nhau**. Nếu bài toán cho phép trùng khóa, cài đặt phải dùng quy tắc xử lý riêng như từ chối trùng, đếm tần suất hoặc gắn danh sách giá trị với mỗi khóa; không được phá bất biến các khoảng.

## 2. Cây 2–3: nút trong có 2 hoặc 3 con

Cây 2–3 là một cây tìm kiếm cân bằng với hai loại nút không rỗng:

- **Nút 2:** chứa một khóa; nếu là nút trong, có đúng hai con.
- **Nút 3:** chứa hai khóa; nếu là nút trong, có đúng ba con.

Một cấu trúc ví dụ:

```text
                          [20 | 40]
                         /    |    \
                      [10]  [30]  [50 | 60]

Tất cả lá đều ở cùng độ sâu.
```

Ở nút gốc, khóa `20` và `40` tách thành ba khoảng. Các lá lần lượt chứa `10`, `30`, `50` và `60` theo đúng miền tìm kiếm.

### Các bất biến cần giữ

1. Trong mỗi nút, khóa luôn được sắp tăng nghiêm ngặt.
2. Mỗi nút không rỗng chỉ có **một hoặc hai khóa**.
3. Nếu là nút trong, một khóa đi kèm **hai con**, hai khóa đi kèm **ba con**.
4. Khóa trong mỗi cây con thuộc đúng khoảng do khóa ở nút cha xác định.
5. **Mọi lá nằm ở cùng độ sâu**, không có nhánh dài ngắn tùy ý.
6. Gốc có thể là lá; khi cây trống thì không có nút chứa khóa. Sau khi xóa, nếu gốc trở thành nút trung gian rỗng với một con, ta nâng con đó lên làm gốc.

Những điều kiện này giúp cây 2–3 **không thoái hóa thành một chuỗi nút dài** như cây nhị phân tìm kiếm không được cân bằng.

### Tìm kiếm trong cây 2–3

Tại nút 2 `[K]`, nếu `x != K`, chọn nhánh trái khi `x < K`, ngược lại chọn nhánh phải. Tại nút 3 `[A | B]`, lần lượt kiểm tra:

| Điều kiện | Quyết định |
| --- | --- |
| `x == A` hoặc `x == B` | Đã tìm thấy khóa |
| `x < A` | Đi con thứ nhất |
| `A < x < B` | Đi con thứ hai |
| `x > B` | Đi con thứ ba |

Vì chỉ có tối đa hai khóa trên mỗi nút, việc chọn nhánh cần O(1) phép so sánh. Thời gian tìm chủ yếu phụ thuộc số tầng của cây.

## 3. Cây 2–3–4: cho phép thêm nút 4

Cây 2–3–4 sử dụng các nút 2, 3 và 4:

- Nút 2: một khóa và hai con nếu không phải lá.
- Nút 3: hai khóa và ba con nếu không phải lá.
- Nút 4: ba khóa và bốn con nếu không phải lá.

Một cây ví dụ:

```text
                            [20 | 40]
                           /    |    \
                       [10]   [30]   [50 | 60 | 70]

Gốc là nút 3; lá cuối là nút 4.
```

Tương tự cây 2–3, mọi khóa trong nút được sắp xếp, mọi nhánh con thuộc đúng khoảng khóa, và tất cả lá ở cùng độ sâu. Khác biệt chính là **sức chứa tối đa một nút được nâng từ hai khóa lên ba khóa**.

Một nút 4 `[20 | 40 | 60]` có bốn khoảng:

| Khoảng | Con trỏ |
| --- | --- |
| `x < 20` | `P0` |
| `20 < x < 40` | `P1` |
| `40 < x < 60` | `P2` |
| `x > 60` | `P3` |

Nếu `x` bằng một trong ba khóa thì tìm thấy khóa ngay trong nút theo mô hình lưu khóa tại nút trong. Chọn một trong bốn nhánh làm lượng thông tin định tuyến của mỗi tầng nhiều hơn cây nhị phân.

## 4. So sánh cây 2–3 và cây 2–3–4

| Tiêu chí | Cây 2–3 | Cây 2–3–4 |
| --- | --- | --- |
| Các kiểu nút hợp lệ | Nút 2 và nút 3 | Nút 2, nút 3, nút 4 |
| Số khóa tối đa mỗi nút | 2 | 3 |
| Số con tối đa của nút trong | 3 | 4 |
| Số con tối thiểu của nút trong không phải gốc | 2 | 2 |
| Vị trí các lá | Cùng độ sâu | Cùng độ sâu |
| Thời gian tìm kiếm | O(log n) | O(log n) |
| Thời gian chèn/xóa với tái cân bằng | O(log n) | O(log n) |
| Mục đích của tách/gộp/luân chuyển khóa | Giữ số khóa, khoảng con và độ cao hợp lệ | Tương tự, nhưng nút có thêm một mức sức chứa |

Không nên kết luận rằng cây 2–3–4 **luôn** thấp hơn cây 2–3 với cùng `n`. Số khóa thực tế trong từng nút quyết định số tầng cụ thể. Cây 2–3–4 có **khả năng chứa nhiều khóa hơn mỗi nút**, nhưng vẫn có thể gồm nhiều nút 2 nếu dữ liệu và quy tắc cập nhật tạo ra trạng thái như vậy.

Về phân loại, cây 2–3 và cây 2–3–4 là hai trường hợp cụ thể của **cây tìm kiếm nhiều nhánh cân bằng**, gần với họ B-tree. Theo quy ước lấy *order* là số con tối đa, cây 2–3 tương ứng mức tối đa ba con, còn cây 2–3–4 là B-tree với **bậc tối thiểu `t = 2`**, tối đa ba khóa và bốn con. Một số tài liệu định nghĩa `order` khác nhau; phải kiểm tra quy ước trước khi áp dụng công thức.

## 5. Chèn vào cây 2–3: nút tràn phải tách

Chèn khóa mới trước hết đi theo đường tìm kiếm đến một lá thích hợp. Nếu lá còn chỗ (là nút 2), có thể thêm khóa vào lá và biến nó thành nút 3. Nếu lá đã có hai khóa, việc thêm tạo ra trạng thái tạm thời **ba khóa**, không thuộc các kiểu nút hợp lệ của cây 2–3. Khi đó cần **tách nút và đẩy khóa giữa lên cha**.

Ví dụ chèn lần lượt `10, 20, 30, 40, 50`:

```text
Chèn 10:             [10]

Chèn 20:          [10 | 20]

Chèn 30:        tạm [10 | 20 | 30]
               đẩy 20 lên làm gốc

                         [20]
                        /    \
                      [10]  [30]

Chèn 40:
                         [20]
                        /    \
                      [10]  [30 | 40]

Chèn 50:          tạm [30 | 40 | 50] ở lá phải
                 tách lá và đẩy 40 lên gốc

                         [20 | 40]
                        /    |     \
                      [10]  [30]  [50]
```

Trong lần chèn `30`, khóa giữa `20` được đẩy lên; hai khóa `10` và `30` trở thành hai nút con. Khi chèn `50`, nút lá `[30 | 40]` bị tràn tạm thời; khóa `40` đi lên gốc, hai nút mới giữ `30` và `50`.

### Điều gì nếu nút cha cũng đầy?

Nếu khóa giữa được đẩy vào một nút cha 3 vốn đã có hai khóa, nút cha tạm thời có ba khóa, nên nó cũng phải tách. Quá trình có thể **lan lên các tổ tiên**. Nếu tách tới gốc, một gốc mới được tạo:

```text
Trước: gốc đã chứa tối đa 2 khóa
Khi đẩy khóa lên: gốc tạm có 3 khóa
Tách gốc: khóa giữa làm gốc mới

Chiều cao cây tăng đúng 1, và tất cả lá vẫn cùng độ sâu.
```

Đây là cơ chế giữ cân bằng quan trọng: cây không cho phép một nhánh tự lớn dài hơn các nhánh khác khi chèn.

## 6. Chèn vào cây 2–3–4: tách nút 4 trước khi đi xuống

Một chiến lược phổ biến cho cây 2–3–4 là **tách nút 4 trên đường đi xuống** (*top-down splitting*). Nút 4 đã chứa ba khóa, tức đầy; trước khi đi tiếp vào nó, có thể tách thành hai nút 2 và đưa khóa giữa lên cha.

```text
Nút 4 đang đầy:
            [10 | 20 | 30]

Tách:
                  [20]           <- khóa giữa đẩy lên cha
                 /    \
               [10]  [30]        <- hai nút 2
```

Nếu nút đầy là **nút trong**, không chỉ khóa mà **bốn cây con cũ** cũng phải được phân chia đúng:

```text
Trước tách:
                     [10 | 20 | 30]
                    /    |    |    \
                   A     B    C     D

Sau tách:
                          [20]
                         /    \
                      [10]    [30]
                      /  \    /  \
                     A    B  C    D
```

Điều này bảo toàn miền giá trị của từng cây con: các khóa ở `A` nhỏ hơn `10`, `B` nằm giữa `10` và `20`, `C` giữa `20` và `30`, còn `D` lớn hơn `30`.

### Ví dụ từng bước

Chèn `10, 20, 30, 40, 50, 60` theo chiến lược tách nút 4 trước khi đi sâu:

```text
Sau ba lần thêm:
                [10 | 20 | 30]      <- gốc đầy (nút 4)

Trước khi thêm 40, tách gốc:
                      [20]
                     /    \
                   [10]  [30]

Thêm 40 vào lá phải:
                      [20]
                     /    \
                   [10]  [30 | 40]

Thêm 50:
                      [20]
                     /    \
                   [10]  [30 | 40 | 50]   <- lá phải đầy

Trước khi thêm 60, tách lá phải và đẩy 40 lên:
                        [20 | 40]
                       /    |    \
                     [10]  [30]  [50]

Thêm 60 ở lá phải:
                        [20 | 40]
                       /    |    \
                     [10]  [30]  [50 | 60]
```

**Vì sao tách khi đi xuống giúp cài đặt thuận tiện?** Sau khi xử lý các nút đầy trên đường tìm kiếm, thuật toán đi vào một nút con chưa đầy, nên đến lá có thể chèn khóa mà không cần xử lý một đợt tràn quay ngược lên trên. Để làm vậy, trước khi tách một nút con, cha cần còn chỗ; chiến lược tách từ trên xuống bảo đảm điều kiện này trên đường đang xét, còn trường hợp gốc đầy được xử lý riêng bằng cách tạo gốc mới.

Một thuật toán chèn từ dưới lên cũng có thể được thiết kế đúng. Hai chiến lược khác về thứ tự sửa cấu trúc, nhưng đều phải bảo toàn các bất biến của cây.

## 7. Xóa khóa: tránh nút bị thiếu khóa

Xóa khó hơn chèn vì có thể làm một nút không phải gốc trở nên **không còn khóa nào**, vi phạm quy tắc tối thiểu một khóa trên mỗi nút không rỗng.

Khi xóa, có ba công việc thường gặp:

1. **Định vị khóa.** Nếu khóa nằm ở nút trong, thường đổi với khóa tiền nhiệm (*predecessor*) hoặc kế nhiệm (*successor*) phù hợp để chuyển bài toán về xóa ở lá; các liên kết con và khoảng khóa phải được giữ chính xác.
2. **Xóa tại lá.** Nếu lá còn ít nhất một khóa, chỉ cần bỏ khóa. Nếu lá trở thành rỗng, phải tái cân bằng.
3. **Sửa trạng thái thiếu khóa.** Có thể mượn một khóa từ anh em qua khóa phân cách của cha (*redistribution/rotation*) hoặc gộp các nút qua khóa ở cha (*merge*). Nếu cha cũng thiếu khóa, sửa tiếp lên trên.

### Ví dụ xóa khỏi cây 2–3: mượn khóa

```text
Ban đầu:
                        [20]
                       /    \
                     [10]  [30 | 40]

Xóa 10: lá trái rỗng. Lá phải có 2 khóa và có thể chia sẻ.
Chuyển 20 từ cha xuống trái; đưa 30 từ phải lên cha:

                        [30]
                       /    \
                     [20]  [40]
```

Hai lá vẫn có một khóa và cùng độ sâu; gốc còn một khóa. Nhờ điều chỉnh khóa phân cách, các khoảng tìm kiếm vẫn đúng.

### Ví dụ xóa khỏi cây 2–3: gộp và giảm chiều cao

```text
Ban đầu:
                         [20]
                        /    \
                      [10]  [30]

Xóa 10: lá trái rỗng, lá phải chỉ có một khóa, không cho mượn.
Gộp khóa phân cách 20 với lá còn lại 30:

                       [20 | 30]

Gốc trung gian trở nên rỗng nên bỏ đi;
nút đã gộp trở thành gốc mới và là lá.
```

Với **cây 2–3–4**, một kỹ thuật xóa từ trên xuống có thể bảo đảm không đi vào một nút 2 nếu có thể sửa trước: mượn từ anh em đủ khóa, hoặc gộp **hai nút 2** cùng khóa phân cách ở cha thành **một nút 4** ba khóa. Đây là phép gộp hợp lệ của cây 2–3–4.

Không nên áp dụng nguyên xi phép gộp đó để tạo một nút 4 như **trạng thái tồn tại lâu dài trong cây 2–3**, bởi cây 2–3 chỉ cho phép nút 2 và nút 3. Khi xóa theo cách sửa nút thiếu khóa của cây 2–3, một nút đang rỗng có thể gộp với một nút 2 và khóa phân cách, tạo nút 3 hợp lệ.

Xóa có thể làm chiều cao giảm một khi gốc cũ trở nên rỗng và được thay bằng con duy nhất. Dù trường hợp nào, **mọi lá của cây sau khi xử lý xong vẫn phải cùng độ sâu**.

## 8. Vì sao chiều cao luôn O(log n)?

Với cả hai cấu trúc, mọi **nút trong** không phải gốc đều có ít nhất hai con; gốc nếu là nút trong cũng có ít nhất hai con. Mọi lá cùng độ sâu. Do đó cây không thể có một đường đi dài mà chỉ nối đơn lẻ từng nút như một cây nhị phân mất cân bằng.

Gọi `h` là số **cạnh từ gốc đến lá** (cây chỉ có gốc có `h = 0`), `n` là tổng số khóa:

- Với số nhánh tối thiểu 2 và mỗi nút ít nhất một khóa, cây cao `h` có ít nhất

  \[
  n_{\min}(h)=1+2+2^2+\cdots+2^h=2^{h+1}-1.
  \]

- Với cây 2–3, nếu mọi nút đều là nút 3 (hai khóa, ba con nếu ở trong), số khóa tối đa ở chiều cao `h` là

  \[
  n_{\max}^{(2\text{–}3)}(h)=3^{h+1}-1.
  \]

- Với cây 2–3–4, nếu mọi nút đều là nút 4 (ba khóa, bốn con nếu ở trong), số khóa tối đa là

  \[
  n_{\max}^{(2\text{–}3\text{–}4)}(h)=4^{h+1}-1.
  \]

Từ `n \ge 2^{h+1}-1` suy ra:

\[
h\le \log_2(n+1)-1=O(\log n).
\]

Các công thức trên dành cho cây **không rỗng**, nút trong có đủ các con theo số khóa, và tất cả lá ở cùng độ sâu. Trạng thái tạm thời trong lúc tách/gộp có thể khác trước khi thuật toán khôi phục bất biến.

**Ví dụ:** với `h = 2` (từ gốc đi qua hai cạnh tới lá):

| Cấu trúc | Số khóa ít nhất | Số khóa nhiều nhất |
| --- | ---: | ---: |
| Cây 2–3 | 7 | 26 |
| Cây 2–3–4 | 7 | 63 |

Vì mỗi nút xử lý tối đa ba khóa nên việc chọn một nhánh là O(1). Tìm kiếm, chèn và xóa với các thao tác tách/mượn/gộp ở số lượng tầng O(log n) đều có **thời gian O(log n)**. Bộ nhớ ngăn xếp của cài đặt đệ quy là O(log n); cài đặt lặp có thể giữ số lượng biến phụ trợ hằng số cho tìm kiếm.

## 9. Ví dụ Java: chèn và tìm trong cây 2–3–4

Đoạn mã sau minh họa một cây 2–3–4 lưu **khóa `int` phân biệt**. Mỗi nút có tối đa ba khóa và bốn con trỏ, chèn theo cách **tách nút 4 trên đường đi xuống**, hỗ trợ `contains` và in hình dạng cây. Đây là cài đặt học tập cho **tìm/chèn**; chưa triển khai thuật toán xóa và kiểm thử chịu tải của một thư viện sản xuất.

```java
import java.util.Arrays;

public class Tree234Demo {
    static final class Node {
        int count = 0;
        int[] keys = new int[3];
        Node[] children = new Node[4];

        boolean isLeaf() {
            return children[0] == null;
        }

        String keysText() {
            return Arrays.toString(Arrays.copyOf(keys, count));
        }
    }

    static final class Tree234 {
        private Node root;

        boolean contains(int value) {
            Node current = root;
            while (current != null) {
                int i = 0;
                while (i < current.count && value > current.keys[i]) {
                    i++;
                }
                if (i < current.count && value == current.keys[i]) {
                    return true;
                }
                if (current.isLeaf()) {
                    return false;
                }
                current = current.children[i];
            }
            return false;
        }

        boolean insert(int value) {
            if (root == null) {
                root = new Node();
                root.keys[0] = value;
                root.count = 1;
                return true;
            }

            if (contains(value)) {
                return false; // Khong chen trung khoa.
            }

            if (root.count == 3) {
                Node newRoot = new Node();
                newRoot.children[0] = root;
                splitChild(newRoot, 0);
                root = newRoot;
            }

            Node current = root;
            while (!current.isLeaf()) {
                int i = 0;
                while (i < current.count && value > current.keys[i]) {
                    i++;
                }

                if (current.children[i].count == 3) {
                    splitChild(current, i);
                    if (value > current.keys[i]) {
                        i++;
                    }
                }
                current = current.children[i];
            }

            // La chua day: dich khoa sang phai roi chen dung vi tri.
            int j = current.count - 1;
            while (j >= 0 && value < current.keys[j]) {
                current.keys[j + 1] = current.keys[j];
                j--;
            }
            current.keys[j + 1] = value;
            current.count++;
            return true;
        }

        // Tach mot nut day 3 khoa; parent phai con cho.
        private void splitChild(Node parent, int index) {
            Node full = parent.children[index];
            Node right = new Node();
            int middle = full.keys[1];

            right.keys[0] = full.keys[2];
            right.count = 1;

            if (!full.isLeaf()) {
                right.children[0] = full.children[2];
                right.children[1] = full.children[3];
                full.children[2] = null;
                full.children[3] = null;
            }

            full.count = 1; // full gio la nut trai giu keys[0].

            for (int j = parent.count; j >= index + 1; j--) {
                parent.children[j + 1] = parent.children[j];
            }
            for (int j = parent.count - 1; j >= index; j--) {
                parent.keys[j + 1] = parent.keys[j];
            }

            parent.keys[index] = middle;
            parent.children[index + 1] = right;
            parent.count++;
        }

        void printTree() {
            printNode(root, 0);
        }

        private void printNode(Node node, int depth) {
            if (node == null) {
                return;
            }
            for (int i = 0; i < depth; i++) {
                System.out.print("  ");
            }
            System.out.println(node.keysText());
            if (!node.isLeaf()) {
                for (int i = 0; i <= node.count; i++) {
                    printNode(node.children[i], depth + 1);
                }
            }
        }
    }

    public static void main(String[] args) {
        Tree234 tree = new Tree234();
        for (int x : new int[] {10, 20, 30, 40, 50, 60}) {
            tree.insert(x);
        }

        tree.printTree();
        System.out.println("contains(30) = " + tree.contains(30));
        System.out.println("contains(35) = " + tree.contains(35));
        System.out.println("insert(20) = " + tree.insert(20));
    }
}
```

Đầu ra dự kiến:

```text
[20, 40]
  [10]
  [30]
  [50, 60]
contains(30) = true
contains(35) = false
insert(20) = false
```

Lưu ý khi đọc mã:

- `count` là **số khóa thực** trong nút; mảng `keys` có ba ô và mảng `children` có bốn ô là **sức chứa tối đa**, không có nghĩa mọi ô đều được sử dụng.
- `contains` định tuyến theo khoảng đã sắp, kết thúc khi gặp khóa hoặc đi tới lá không có khóa.
- `insert` kiểm tra khóa trùng trước khi thay đổi cây; quy tắc minh họa là từ chối chèn trùng.
- Trước khi đi vào một con đầy, `splitChild` đưa khóa giữa lên cha, chuyển khóa phải và nếu cần chuyển hai nhánh con phải sang nút mới.
- Nút lá thêm khóa mới vào vị trí đã sắp xếp. Vì đã tách các nút đầy trên đường đi, lá đích còn chỗ để nhận khóa.

Mã chỉ giới thiệu nguyên tắc chèn từ trên xuống trong cây 2–3–4. Nó không thể thay thế một cấu trúc dữ liệu đầy đủ cho hệ thống sản xuất khi chưa có xóa, kiểm tra bất biến sau mọi thao tác, cơ chế đồng bộ nếu truy cập đồng thời và xử lý các trường hợp lỗi tài nguyên.

## 10. Những nhầm lẫn thường gặp

1. **“Nút 3 có ba khóa.”** Sai: nút 3 có hai khóa và ba con nếu là nút trong. Nút 4 có ba khóa và bốn con.
2. **“Lá phải chứa đủ hai hoặc ba con trỏ.”** Lá không có con trỏ đi xuống. Quy tắc số con áp dụng cho nút trong.
3. **“Cây 2–3 có thể giữ nút 4 sau khi chèn.”** Nút ba khóa chỉ là trạng thái tạm thời để tách trong cách chèn từ dưới lên; cây 2–3 hoàn chỉnh chỉ có nút 2 và nút 3.
4. **“Cây 2–3–4 bắt buộc mọi nút có bốn con.”** Các nút trong được phép có 2, 3 hoặc 4 con, tùy số khóa.
5. **“Chỉ cần sắp khóa trong từng nút là cây tìm kiếm đúng.”** Khóa của **mọi cây con** cũng phải thuộc đúng khoảng do nút cha xác định.
6. **“Có thể chèn khóa vào bất kỳ lá nào còn chỗ.”** Phải đi theo đường tìm kiếm đến lá thuộc đúng khoảng giá trị.
7. **“Tách nút chỉ là chia đôi mảng khóa.”** Với nút trong, phải chuyển các con trỏ con đúng nhóm để bảo toàn phạm vi tìm kiếm.
8. **“Gốc được tách nghĩa là chỉ một nhánh dài thêm.”** Tách gốc tạo một tầng mới phía trên toàn bộ cây; mọi lá vẫn cùng độ sâu.
9. **“Xóa khóa chỉ là xóa một ô trong nút.”** Xóa có thể làm nút thiếu khóa, cần mượn/gộp và có thể sửa tiếp lên cha.
10. **“Cây 2–3 và 2–3–4 luôn có cùng hình dạng.”** Cùng tập khóa có thể biểu diễn bằng nhiều cây hợp lệ, với cách phân nhóm khóa khác nhau, miễn giữ các bất biến.
11. **“Một nút có nhiều con hơn thì mọi thao tác chắc chắn O(1).”** Tìm kiếm, chèn và xóa vẫn đi qua O(log n) tầng; chỉ chi phí xử lý *mỗi nút* được chặn hằng số với hai loại cây này.
12. **“Sức chứa ba khóa của cây 2–3–4 là một giả định về số byte của trang đĩa.”** Đây là số lượng khóa theo định nghĩa cấu trúc; B-tree tổng quát có thể có fan-out lớn hơn tùy cách tổ chức trang.

## 11. Tự kiểm tra

**Câu 1.** Nút 2, nút 3 và nút 4 lần lượt chứa bao nhiêu khóa? Nếu là nút trong, có bao nhiêu nhánh con?

**Đáp án:** Nút 2 chứa 1 khóa/2 con; nút 3 chứa 2 khóa/3 con; nút 4 chứa 3 khóa/4 con.

**Câu 2.** Với nút `[15 | 35]`, tìm khóa `25` phải đi theo nhánh nào nếu các con được đánh số `P0, P1, P2` từ trái sang phải?

**Đáp án:** `P1`, vì `15 < 25 < 35`.

**Câu 3.** Một nút 4 chứa `[10 | 30 | 50]`. Nếu tìm `60` mà khóa chưa nằm trong nút, cần chọn con nào trong `P0, P1, P2, P3`?

**Đáp án:** `P3`, vì `60 > 50`.

**Câu 4.** Trong cây 2–3, chèn `30` vào lá `[10 | 20]` cần xử lý thế nào?

**Đáp án:** Tạm có ba khóa `[10 | 20 | 30]`; tách thành hai nút `[10]` và `[30]`, đưa khóa giữa `20` lên cha (hoặc tạo gốc mới nếu lá chính là gốc).

**Câu 5.** Trong cây 2–3–4, tách nút trong `[10 | 20 | 30]` có bốn cây con `A, B, C, D` thì phải phân chia chúng thế nào?

**Đáp án:** Đưa `20` lên cha, tạo nút trái `[10]` giữ `A, B` và nút phải `[30]` giữ `C, D`.

**Câu 6.** Một cây 2–3 có một lá ở độ sâu 2 và một lá ở độ sâu 4 có hợp lệ không?

**Đáp án:** Không. Một bất biến của cây 2–3 cân bằng là tất cả lá cùng độ sâu.

**Câu 7.** Với cây 2–3–4 cao `h = 2` cạnh từ gốc tới lá, số khóa tối đa là bao nhiêu nếu mọi nút đều là nút 4?

**Đáp án:** `4^{h+1} - 1 = 4^3 - 1 = 63` khóa.

**Câu 8.** Với cùng chiều cao `h = 2`, số khóa tối thiểu của cây 2–3 hoặc cây 2–3–4 không rỗng là bao nhiêu?

**Đáp án:** `2^{h+1} - 1 = 2^3 - 1 = 7` khóa khi mọi nút đều là nút 2.

**Câu 9.** Vì sao chèn vào cây 2–3–4 theo chiến lược tách từ trên xuống thường không phải sửa tràn ngược lên từ lá?

**Đáp án:** Thuật toán tách các nút 4 đầy trước khi đi sâu, kể cả xử lý gốc đầy trước, nên lá đích có chỗ để thêm khóa khi đến nơi.

**Câu 10.** Khi xóa một khóa khiến lá trong cây 2–3 không còn khóa nào, có những cách sửa chính nào?

**Đáp án:** Mượn khóa từ anh em đủ khóa qua khóa phân cách của cha hoặc gộp nút thiếu khóa với anh em và khóa phân cách; có thể phải sửa tiếp nút cha.

**Câu 11.** Tại sao tìm kiếm trong hai cây này có độ phức tạp O(log n) theo số khóa?

**Đáp án:** Mọi nút trong có ít nhất hai con và tất cả lá cùng độ sâu, nên chiều cao O(log n). Mỗi nút chỉ chứa tối đa hai (cây 2–3) hoặc ba khóa (cây 2–3–4), làm công so sánh/chọn nhánh tại một tầng là O(1).

**Câu 12.** Một cây 2–3–4 có thể có gốc `[20 | 40]` và ba lá `[10]`, `[30]`, `[50 | 60]` không? Vì sao?

**Đáp án:** Có. Gốc là nút 3 với hai khóa, ba nhánh con ứng với các khoảng `x < 20`, `20 < x < 40` và `x > 40`. Các lá đều cùng độ sâu và số khóa của mỗi nút hợp lệ.

**Câu 13.** Nếu một nút trong của cây 2–3 có ba khóa sau khi kết thúc thao tác chèn, bất biến nào bị vi phạm?

**Đáp án:** Cây 2–3 chỉ cho phép nút 2 và nút 3, tức tối đa **hai khóa** trên một nút. Nút ba khóa phải được tách; nó chỉ có thể xuất hiện tạm trong quá trình chỉnh sửa.

**Điểm ghi nhớ:** Trong cây 2–3 và cây 2–3–4, **nút `m` có `m - 1` khóa và `m` con nếu là nút trong**. Cây 2–3 cho phép nút 2/3; cây 2–3–4 thêm nút 4. Các thao tác tách, mượn và gộp khóa duy trì những khoảng tìm kiếm đúng cùng điều kiện **mọi lá nằm ở cùng độ sâu**, nhờ đó tìm, chèn và xóa có độ phức tạp O(log n).
