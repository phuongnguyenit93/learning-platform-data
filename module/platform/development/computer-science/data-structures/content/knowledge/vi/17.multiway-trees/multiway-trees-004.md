# Bất biến số khóa, số con và độ sâu của các lá

Một **B-tree** là cây tìm kiếm nhiều nhánh được cân bằng, trong đó mỗi nút có thể giữ nhiều khóa đã sắp xếp và các liên kết tới cây con. Cây không chỉ phải tìm đúng khóa: sau hàng nghìn lần chèn và xóa, nó còn phải giữ được những **bất biến** (*invariants*) về số khóa, số con và độ sâu của các lá.

Những bất biến này là hợp đồng cấu trúc để thuật toán tìm kiếm có thể loại bỏ các nhánh không liên quan, thuật toán cập nhật biết lúc nào cần tách hoặc gộp nút, và chiều cao cây không tăng bất thường. Chỉ cần một nút trong thiếu con, một khóa nằm sai khoảng hoặc một lá sâu hơn các lá khác, cấu trúc đã không còn là B-tree hợp lệ theo mô hình chuẩn.

Bài học sử dụng quy ước **bậc tối thiểu `t \ge 2`** (*minimum degree*), giả định các khóa phân biệt, và phân tích cụ thể:

- Số khóa tối thiểu/tối đa của từng loại nút.
- Quan hệ giữa `k` khóa và `k + 1` con ở nút trong.
- Quy tắc mọi lá cùng độ sâu và cách kiểm tra.
- Cách chèn/xóa giữ các bất biến, cùng mã Java kiểm chứng một cây dựng sẵn.

## 1. Phân biệt số khóa thực, số con thực và sức chứa

Một nút B-tree thường có các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `keys` | Dãy khóa trong nút, được sắp tăng |
| `keyCount = k` | Số khóa **thực sự đang dùng** |
| `children` | Các liên kết đến cây con, nếu là nút trong |
| `isLeaf` | Cho biết nút có phải lá, không có con hay không |
| `t` | Bậc tối thiểu chung cho cây theo quy ước của bài |

Trong triển khai dùng các mảng có sức chứa cố định, mảng `keys` có thể có `2t - 1` ô và mảng `children` có thể có `2t` ô. Tuy nhiên, **sức chứa của mảng không đồng nghĩa số khóa hoặc số con thực tế**. Nút có `keyCount = 2` không tự động trở thành nút có năm khóa chỉ vì mảng `keys` còn ba ô dự trữ.

Một nút trong chứa ba khóa:

```text
                          [20 | 40 | 60]
                         /    |    |     \
                        P0    P1   P2     P3

Số khóa thực: 3
Số nhánh con thực: 4
```

Các khóa chia miền tìm kiếm thành bốn khoảng:

| Liên kết con | Miền khóa được phép chứa |
| --- | --- |
| `P0` | Nhỏ hơn `20` |
| `P1` | Lớn hơn `20`, nhỏ hơn `40` |
| `P2` | Lớn hơn `40`, nhỏ hơn `60` |
| `P3` | Lớn hơn `60` |

Vì thế, với một **nút trong chứa `k` khóa phân biệt**, điều kiện về số con là:

\[
\boxed{\text{childCount}=k+1.}
\]

Một **lá** cũng có thể chứa `k` khóa nhưng **không có con**. Không được yêu cầu lá phải có `k+1` con trỏ hợp lệ chỉ vì nút trong có quy tắc đó.

## 2. Bất biến thứ nhất: giới hạn số khóa theo bậc tối thiểu `t`

Với một B-tree có bậc tối thiểu là số nguyên `t \ge 2`, mỗi nút có **nhiều nhất `2t-1` khóa**. Các nút **không phải gốc** phải có **ít nhất `t-1` khóa**.

| Loại nút | Số khóa tối thiểu | Số khóa tối đa | Số con |
| --- | ---: | ---: | --- |
| Lá không phải gốc | `t-1` | `2t-1` | 0 |
| Nút trong không phải gốc | `t-1` | `2t-1` | `k+1`, tức từ `t` đến `2t` |
| Gốc là lá, cây không rỗng | 1 | `2t-1` | 0 |
| Gốc là nút trong | 1 | `2t-1` | `k+1`, tức từ 2 đến `2t` |
| Cây rỗng | Không có khóa | Không áp dụng | Có thể biểu diễn bằng `root = null` |

Lưu ý rằng **gốc là ngoại lệ của cận dưới**. Chẳng hạn khi `t=4`, mỗi nút không phải gốc cần ít nhất ba khóa; nhưng gốc có đúng một khóa và hai con vẫn hoàn toàn hợp lệ.

### Ví dụ tính giới hạn

| `t` | Số khóa nút không phải gốc | Số con của nút trong không phải gốc | Số khóa tối đa của gốc |
| ---: | --- | --- | ---: |
| 2 | 1–3 | 2–4 | 3 |
| 3 | 2–5 | 3–6 | 5 |
| 4 | 3–7 | 4–8 | 7 |
| 8 | 7–15 | 8–16 | 15 |

Với `t=2`, các nút không rỗng có thể chứa một, hai hoặc ba khóa; đây là quy tắc của **cây 2–3–4**. Với `t=3`, một lá không phải gốc chỉ có một khóa là **nút thiếu khóa** (*underfull*), dù khóa đó vẫn được sắp đúng.

### Phân biệt ba tình trạng của nút

```text
Ví dụ t = 3:

Nút chưa đầy nhưng hợp lệ: [10 | 20]              (2 khóa)
Nút đầy:                   [10 | 20 | 30 | 40 | 50] (5 khóa)
Nút thiếu khóa:            [10]                   (1 khóa, nếu không phải gốc)
```

- **Đầy** nghĩa là đã đạt `2t-1` khóa; muốn thêm, thuật toán phải chuẩn bị cách tách hoặc phân phối lại.
- **Thiếu khóa** nghĩa là một nút không phải gốc có ít hơn `t-1` khóa, phải được sửa trước khi kết thúc thao tác xóa.
- **Hợp lệ nhưng chưa đầy** nghĩa là số khóa nằm trong đoạn quy định; không nhất thiết mọi nút đều phải sử dụng hết sức chứa.

## 3. Bất biến thứ hai: nút trong có đúng `k+1` con

Nếu nút trong lưu `k` khóa thì **không thể tùy ý có ít hoặc nhiều con hơn `k+1`**. Đây không chỉ là quy tắc đếm: `k` khóa phân cách tạo ra chính xác `k+1` khoảng để định tuyến tìm kiếm.

Xét gốc `[30 | 60]`:

```text
Hợp lệ:
                          [30 | 60]
                         /    |    \
                      [10]  [40]  [80]

2 khóa gốc -> đúng 3 con.

Không hợp lệ:
                          [30 | 60]
                         /       \
                      [10]       [80]

2 khóa gốc nhưng chỉ 2 con:
không có nhánh ứng với khoảng (30, 60).
```

Với các nút trong:

\[
\text{minChildren}=\text{minKeys}+1,\qquad
\text{maxChildren}=\text{maxKeys}+1.
\]

Vì vậy, nút trong không phải gốc của B-tree `t` có từ `t` đến `2t` con. Gốc là nút trong có từ **2** đến `2t` con.

### Không để nút trong có con “hổng”

Giả sử một nút báo `keyCount = 2` và mảng `children` có ba vị trí đang dùng, nhưng `children[1] = null`. Nút đó chưa hợp lệ: khoảng khóa giữa hai khóa phân cách **không có cây con tương ứng**. Một cài đặt có thể dùng mảng vật lý nhiều ô và để trống phần **ngoài số con thực**, nhưng không được để thiếu một con bên trong đoạn được coi là đang sử dụng.

Tương tự, nếu một nút được đánh dấu **lá** thì không được có con thực. Phân biệt kiểu nút và số con phải nhất quán trong toàn bộ cây.

## 4. Bất biến thứ ba: khóa trong nút và cây con đều đúng thứ tự

Giới hạn số khóa và số con **chưa đủ** để tạo một cây tìm kiếm đúng. Cần duy trì:

1. Khóa trong từng nút tăng nghiêm ngặt: `K0 < K1 < ...`.
2. Với một nút trong có khóa `[K0, K1, ..., K{k-1}]`, toàn bộ cây con `P_i` chỉ chứa các khóa **thuộc khoảng** do khóa cha xác định.
3. Các khoảng của tổ tiên vẫn có hiệu lực với mọi nút nằm sâu bên dưới.

Ví dụ:

```text
                          [30 | 60]
                         /    |     \
                   [10,20] [40,50] [70,80]

Mọi khóa ở cây con giữa phải nằm trong (30, 60).
```

Nếu thay nút giữa thành `[40, 65]`, nút con vẫn có hai khóa được sắp tăng và đúng sức chứa với `t=2`, nhưng **65 nằm sai khoảng**: nó lớn hơn `60` mà lại ở nhánh giữa.

Cũng có thể xảy ra lỗi sâu hơn:

```text
Gốc [30 | 60]
    |
    +-- nhánh giữa: nút [40]
                         \
                         [65]   <- sai vì cả nhánh giữa phải < 60
```

Để xác minh toàn cây, thuật toán kiểm tra nên truyền **cận dưới và cận trên tích lũy từ tổ tiên**, chứ không chỉ so sánh nút con với nút cha ngay sát nó.

**Phạm vi:** Bài này mô hình hóa tập khóa phân biệt. Nếu ứng dụng cho phép khóa trùng, phải xác định quy tắc giữ bản ghi trùng, bộ đếm hay các biên so sánh được phép bằng nhau; không được thay đổi bất biến `<` và `>` tùy hứng.

## 5. Bất biến thứ tư: tất cả lá ở cùng độ sâu

**Độ sâu** (*depth*) của một nút là số **cạnh** trên đường từ gốc đến nút đó. Gốc có độ sâu 0. **Chiều cao** (*height*) của B-tree được tính bằng số cạnh trên một đường từ gốc tới lá; vì mọi lá cùng độ sâu nên không phụ thuộc lựa chọn lá.

Ví dụ B-tree `t=2` hợp lệ:

```text
                           [40]                    độ sâu 0
                         /      \
                       [20]     [60]                độ sâu 1
                      /    \    /    \
                   [10]  [30] [50]  [70 | 80]       độ sâu 2

Tất cả lá ở độ sâu 2.
```

Các lá có thể chứa **số khóa khác nhau**, miễn vẫn tuân giới hạn. Lá `[10]` có một khóa, lá `[70 | 80]` có hai khóa: điều này **không vi phạm** quy tắc cân bằng.

Ngược lại, cấu trúc sau không hợp lệ:

```text
                             [40]                   độ sâu 0
                           /      \
                         [20]     [60]              độ sâu 1
                        /    \    /    \
                     [10]  [30] [50]  [70]           độ sâu 2
                                                   /    \
                                                [65]    [75]    độ sâu 3

Nhánh qua [70] sâu hơn các nhánh khác.
```

Dù mỗi nút có số khóa trong giới hạn và các khóa đã sắp xếp, **độ sâu lá không đồng nhất** khiến cấu trúc không còn là B-tree.

### Vì sao phải kiểm tra tất cả lá?

Với một B-tree hợp lệ, tìm kiếm một khóa vắng mặt sẽ đi đến **một lá** rồi kết luận không tìm thấy. Nếu các lá nằm ở những độ sâu khác nhau, chi phí tìm kiếm trên các đường đi sẽ khác nhau bất thường, và quan trọng hơn, các thuật toán chèn/xóa chuẩn vốn dựa vào bất biến cân bằng không còn được phép giả định cấu trúc hợp lệ.

Cách kiểm tra trực tiếp là duyệt DFS:

1. Đặt `firstLeafDepth` chưa xác định.
2. Khi gặp lá đầu tiên, ghi lại độ sâu của nó.
3. Với mọi lá sau, so sánh độ sâu hiện tại với `firstLeafDepth`.
4. Nếu có lá khác độ sâu, kết luận cây vi phạm bất biến.

Thời gian duyệt toàn bộ là O(n) theo tổng số khóa/nút (với `t` cố định) vì phải thăm tất cả nút. Việc kiểm tra lá không được thay bằng cách chỉ đo **chiều cao lớn nhất**, vì như vậy không phát hiện một lá kết thúc sớm hơn các lá khác.

## 6. Kiểm tra cấu trúc hợp lệ và các trường hợp biên

Một bộ kiểm tra B-tree dựa trên `t` nên áp dụng điều kiện theo đúng thứ tự:

| Kiểm tra | Điều kiện hợp lệ |
| --- | --- |
| Tham số cây | `t >= 2` |
| Cây rỗng | `root == null`, hoặc quy ước gốc rỗng rõ ràng |
| Gốc của cây không rỗng | Có ít nhất một khóa |
| Mọi nút | Không quá `2t-1` khóa |
| Mọi nút không phải gốc | Không ít hơn `t-1` khóa |
| Khóa trong nút | Sắp tăng, không trùng |
| Khóa so với tổ tiên | Thuộc đúng khoảng được truyền xuống |
| Nút trong có `k` khóa | Đúng `k+1` con thực |
| Nút lá | Không có con |
| Tất cả lá | Cùng độ sâu |

### Cây rỗng và cây chỉ có gốc

```text
Cây rỗng:       root = null

Cây một nút:    root -> [42]
                          (lá, không có con)
```

Với cây không rỗng chỉ chứa gốc, nút gốc vừa là lá vừa có thể chỉ có một khóa. Không được áp dụng cận dưới `t-1` của **nút không phải gốc** cho trường hợp này.

Khi xóa khóa cuối cùng, cây có thể trở về `root = null`. Khi gộp làm gốc không còn khóa nhưng còn đúng một con, thuật toán phải **nâng con duy nhất lên làm gốc**; không giữ nút gốc rỗng có một con như trạng thái hợp lệ cuối cùng của cây không rỗng.

### B-tree dùng “order m” có công thức khác

Trong bài, `t` là **bậc tối thiểu**. Một tài liệu khác có thể định nghĩa `order m` là **số con tối đa**, khi đó nút trong không phải gốc có từ `ceil(m/2)` đến `m` con và từ `ceil(m/2)-1` đến `m-1` khóa.

Hai bộ công thức tương đương khi `m = 2t`. Khi `m` lẻ, không nên tự đặt `t=ceil(m/2)` rồi áp cận tối đa `2t`, vì cận đó có thể lớn hơn `m`. Dù theo quy ước nào, **đếm `k` khóa thì nút trong vẫn cần đúng `k+1` con**, và mọi lá vẫn phải cùng độ sâu.

## 7. Tách, mượn và gộp: sửa cây mà không phá bất biến

Các thuật toán cập nhật B-tree thường tạo trạng thái **trung gian** chưa thỏa một số điều kiện. Công việc quan trọng là khôi phục đủ bất biến trước khi thao tác kết thúc.

### 7.1. Khi chèn gặp nút đầy

Với `t=2`, nút đầy có `2t-1=3` khóa:

```text
Gốc trước tách:     [10 | 20 | 30]

Tách nút đầy:
                            [20]
                           /    \
                         [10]  [30]
```

Khóa giữa `20` được đưa lên, hai nút còn lại mỗi nút chứa `t-1=1` khóa. Nếu là nút trong, bốn cây con cũ cũng phải được phân về hai nút theo các khoảng bên trái và bên phải khóa giữa.

Một ví dụ có cha sẵn:

```text
Trước, gốc có 1 khóa và 2 con:

                         [50]
                        /    \
                 [10|20|30] [60|70]

Tách con trái và đưa 20 lên gốc:

                       [20 | 50]
                      /    |     \
                    [10]  [30]  [60 | 70]

Tất cả lá vẫn ở độ sâu 1 và mỗi nút có số khóa hợp lệ.
```

Tách nút giúp tránh giữ một nút có quá nhiều khóa. Khi cần tách gốc, việc thêm một gốc mới **tăng độ sâu của tất cả lá cùng một đơn vị**, không chỉ tăng riêng một nhánh.

### 7.2. Khi xóa khiến nút thiếu khóa

Với `t=2`, mỗi nút không phải gốc cần ít nhất một khóa. Giả sử xóa `10` trong cây:

```text
Ban đầu:                     Sau khi xóa 10 tạm thời:

         [40]                           [40]
        /    \                         /    \
      [10] [50 | 60]                 [ ] [50 | 60]

Lá trái thiếu khóa.
```

Vì lá phải có hai khóa (nhiều hơn mức tối thiểu một khóa), có thể **mượn qua cha**:

```text
Đưa 40 từ cha xuống lá trái, đưa 50 từ lá phải lên cha:

                            [50]
                           /    \
                         [40]  [60]
```

Những bất biến được bảo toàn: nút trái và nút phải đều có một khóa, gốc vẫn có một khóa, hai nhánh con đúng khoảng và lá cùng độ sâu.

Nếu anh em cũng chỉ có số khóa tối thiểu, có thể **gộp**:

```text
Ban đầu:                   [40]
                          /    \
                        [10]   [50]

Muốn xóa 10: hai con đều có 1 khóa.
Gộp hai con cùng khóa phân cách 40:

                        [10 | 40 | 50]

Xóa 10 trong nút đã gộp:

                        [40 | 50]

Gốc trung gian trở nên rỗng; nút đã gộp thành gốc mới.
```

Khi gộp hai nút mỗi nút có `t-1` khóa cùng **một khóa phân cách** của cha, nút mới có:

\[
(t-1)+1+(t-1)=2t-1
\]

khóa, vừa đúng số khóa tối đa. Với nút trong, các con của hai nút cũ phải được nối theo đúng thứ tự. Nếu cha bị thiếu khóa sau gộp, thuật toán tiếp tục xử lý lên trên.

**Mục tiêu của tách/mượn/gộp không chỉ là đếm đủ khóa:** mọi thao tác còn phải bảo toàn thứ tự khóa, số con thực và độ sâu đồng đều của các lá.

## 8. Các bất biến giúp chứng minh chiều cao O(log n)

Gọi `n` là tổng số khóa của cây không rỗng và `h` là số cạnh từ gốc đến lá. Với `t\ge2`:

- Gốc là nút trong có ít nhất một khóa và hai con.
- Mọi nút trong không phải gốc có ít nhất `t` con.
- Mọi nút không phải gốc có ít nhất `t-1` khóa.
- Mọi lá ở cùng độ sâu `h`.

Với `h\ge1`, số nút ở độ sâu 1 ít nhất là 2; ở độ sâu 2 ít nhất `2t`; ở độ sâu 3 ít nhất `2t^2`; và tương tự.

Do đó, số khóa ít nhất trong cây cao `h` là:

\[
\begin{aligned}
n_{\min}(h)
&=1+2(t-1)\sum_{i=0}^{h-1}t^i\\
&=1+2(t-1)\frac{t^h-1}{t-1}\\
&=\boxed{2t^h-1}.
\end{aligned}
\]

Suy ra:

\[
n\ge2t^h-1
\quad\Longrightarrow\quad
h\le\log_t\left(\frac{n+1}{2}\right)=O(\log_t n).
\]

Với cây chỉ có gốc (`h=0`), số khóa tối thiểu là 1, cũng khớp công thức `2t^0-1=1`.

Ở phía trên, khi mọi nút chứa tối đa `2t-1` khóa và các nút trong có `2t` con, số khóa tối đa ở chiều cao `h` là:

\[
n_{\max}(h)=(2t)^{h+1}-1.
\]

Ví dụ:

| Bậc tối thiểu | Chiều cao `h` | Số khóa tối thiểu | Số khóa tối đa |
| ---: | ---: | ---: | ---: |
| `t=2` | 1 | 3 | 15 |
| `t=2` | 2 | 7 | 63 |
| `t=3` | 1 | 5 | 35 |
| `t=3` | 2 | 17 | 215 |

**Liên hệ tới tìm kiếm:** Với `t` cố định, mỗi nút chỉ chứa O(`t`) khóa và một đường tìm đi qua O(log `n`) tầng. Tìm kiếm, chèn và xóa có thể đạt O(log `n`) trong mô hình tính toán chuẩn. Với `t` lớn và cây được lưu theo trang, số tầng O(log_t `n`) đặc biệt quan trọng khi mỗi tầng có thể cần truy cập trang khác.

Kết quả này dựa vào **cả cận dưới số con và bất biến độ sâu lá**. Nếu bỏ cận dưới số con hoặc cho các lá lệch độ sâu tùy ý, suy luận về số nút tăng theo mỗi tầng có thể không còn đúng.

## 9. Java: xây bộ kiểm tra tất cả bất biến trên cây dựng sẵn

Ví dụ sau mô hình hóa mỗi nút bằng mảng `keys` và mảng `children`. Lá có `children.length == 0`. Bộ xác minh kiểm tra số khóa theo `t`, số con, khoảng khóa từ tổ tiên, độ sâu lá, đồng thời phát hiện nếu một đối tượng nút bị dùng lại ở nhiều nhánh hoặc tạo chu trình.

Đây là **mã kiểm tra** chứ không phải bộ cài đặt B-tree đầy đủ: nó không chèn hoặc xóa. Việc cho phép xây cây không hợp lệ là chủ ý để minh họa thông báo lỗi.

```java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class BTreeInvariantChecker {
    static final class Node {
        final int[] keys;
        final Node[] children;

        Node(int[] keys, Node... children) {
            this.keys = keys.clone();
            this.children = children.clone();
        }

        boolean isLeaf() {
            return children.length == 0;
        }
    }

    static final class Validator {
        private final int t;
        private final Set<Node> visited =
            Collections.newSetFromMap(new IdentityHashMap<Node, Boolean>());
        private int firstLeafDepth;
        private String error;

        Validator(int minimumDegree) {
            if (minimumDegree < 2
                    || minimumDegree > Integer.MAX_VALUE / 2) {
                throw new IllegalArgumentException("Invalid minimum degree");
            }
            this.t = minimumDegree;
        }

        String verify(Node root) {
            visited.clear();
            firstLeafDepth = -1;
            error = "";

            if (root == null) {
                return "VALID (empty tree)";
            }
            boolean ok = check(root, true,
                Long.MIN_VALUE, Long.MAX_VALUE, 0);
            return ok
                ? "VALID (leafDepth=" + firstLeafDepth + ")"
                : "INVALID: " + error;
        }

        private boolean fail(String message) {
            error = message;
            return false;
        }

        private boolean check(Node node, boolean isRoot,
                              long lower, long upper, int depth) {
            if (node == null) {
                return fail("missing child at depth " + depth);
            }
            if (!visited.add(node)) {
                return fail("repeated node or cycle at depth " + depth);
            }

            int k = node.keys.length;
            int minimum = isRoot ? 1 : t - 1;
            int maximum = 2 * t - 1;

            if (k < minimum || k > maximum) {
                return fail("key count " + k
                    + " outside [" + minimum + ", " + maximum
                    + "] at depth " + depth);
            }

            for (int i = 0; i < k; i++) {
                int key = node.keys[i];
                if (key <= lower || key >= upper) {
                    return fail("key " + key + " outside ancestor range");
                }
                if (i > 0 && node.keys[i - 1] >= key) {
                    return fail("keys are not strictly increasing");
                }
            }

            if (node.isLeaf()) {
                if (firstLeafDepth == -1) {
                    firstLeafDepth = depth;
                }
                if (firstLeafDepth != depth) {
                    return fail("leaf depths differ: "
                        + firstLeafDepth + " vs " + depth);
                }
                return true;
            }

            if (node.children.length != k + 1) {
                return fail("internal node with " + k
                    + " keys needs " + (k + 1) + " children");
            }

            for (int i = 0; i <= k; i++) {
                long childLower =
                    i == 0 ? lower : node.keys[i - 1];
                long childUpper =
                    i == k ? upper : node.keys[i];

                if (!check(node.children[i], false,
                        childLower, childUpper, depth + 1)) {
                    return false;
                }
            }
            return true;
        }
    }

    static Node leaf(int... keys) {
        return new Node(keys);
    }

    public static void main(String[] args) {
        Node valid = new Node(new int[] {20, 40},
            leaf(5, 10), leaf(25, 30), leaf(50, 60, 70));

        Node wrongRange = new Node(new int[] {20, 40},
            leaf(5, 10), leaf(25, 45), leaf(50, 60));

        Node wrongChildCount = new Node(new int[] {20, 40},
            leaf(5, 10), leaf(50, 60));

        Node wrongDepth = new Node(new int[] {20, 40},
            leaf(5, 10),
            new Node(new int[] {30}, leaf(25), leaf(35)),
            leaf(50, 60));

        Node underfilled = new Node(new int[] {30, 60},
            leaf(5, 10), leaf(40), leaf(70, 80));

        Validator forT2 = new Validator(2);
        System.out.println("Valid: " + forT2.verify(valid));
        System.out.println("Wrong range: "
            + forT2.verify(wrongRange));
        System.out.println("Wrong children: "
            + forT2.verify(wrongChildCount));
        System.out.println("Wrong leaf depth: "
            + forT2.verify(wrongDepth));
        System.out.println("Underfilled for t=3: "
            + new Validator(3).verify(underfilled));
    }
}
```

Kết quả dự kiến (rút gọn phần thông báo lỗi):

```text
Valid: VALID (leafDepth=1)
Wrong range: INVALID: key 45 outside ancestor range
Wrong children: INVALID: internal node with 2 keys needs 3 children
Wrong leaf depth: INVALID: leaf depths differ: 1 vs 2
Underfilled for t=3: INVALID: key count 1 outside [2, 5] at depth 1
```

### Vì sao chương trình dùng cận kiểu `long`?

Khóa có kiểu `int`, có thể là `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`. Nếu dùng chính hai giá trị cực trị này làm cận mở rồi so sánh `key > lower` và `key < upper`, một khóa bằng cực trị sẽ bị loại sai. Chọn `Long.MIN_VALUE` và `Long.MAX_VALUE` tạo cận ngoài miền `int`, nên mọi khóa `int` đều có thể được kiểm tra chính xác.

### Độ phức tạp của bộ kiểm tra

Nếu tổng số khóa là `n`, số nút là `N`, bộ kiểm tra duyệt mỗi nút một lần và so sánh từng khóa một lần:

- **Thời gian:** O(`n+N`), tương đương O(n) với B-tree không rỗng hợp lệ khi mỗi nút có ít nhất một khóa.
- **Ngăn xếp đệ quy:** O(`h`), tức O(log n) trên một B-tree hợp lệ.
- **Tập `visited`:** O(`N`) bộ nhớ bổ sung để phát hiện chu trình hoặc một nút bị chia sẻ bởi nhiều cha.

Trong bài toán chắc chắn dữ liệu đầu vào đã là cây hợp lệ về mặt liên kết, có thể bỏ `visited` để giảm bộ nhớ; khi đó phải chấp nhận bộ kiểm tra không phát hiện được chu trình hoặc nút dùng chung.

## 10. Danh sách kiểm tra khi cài đặt chèn/xóa

Khi viết thuật toán cập nhật B-tree, nên kiểm tra trạng thái **sau khi hoàn tất mỗi thao tác**, không vội đánh giá các bước trung gian:

1. **Có khóa bị mất hoặc nhân đôi không?** Với tập khóa phân biệt, mọi khóa cũ không bị xóa phải còn đúng một lần; khóa mới phải xuất hiện đúng một lần sau chèn thành công.
2. **Các khóa trong mỗi nút đã sắp tăng chưa?** Sau dịch mảng khóa hoặc đẩy khóa phân cách, không được làm đảo thứ tự.
3. **Giới hạn khóa còn đúng không?** Ngoại trừ gốc, mỗi nút phải có từ `t-1` đến `2t-1` khóa.
4. **Mọi nút trong có đúng `k+1` con chưa?** Các con phải được chuyển theo đúng thứ tự khi tách/gộp.
5. **Cận khoảng của từng cây con còn đúng không?** Không chỉ so sánh khóa trực tiếp với cha; cần xét cả các khóa phân cách ở tổ tiên.
6. **Mọi lá còn cùng độ sâu không?** Tách gốc tăng chiều cao toàn cây; gộp làm gốc rỗng có thể giảm chiều cao toàn cây.
7. **Đã xử lý gốc rỗng chưa?** Cây rỗng cần trạng thái quy ước rõ ràng; gốc trung gian rỗng có một con phải được thay bằng con đó.
8. **Đã phân biệt trạng thái nút trong và lá chưa?** Không để một nút lá có con thực hoặc một nút trong thiếu con.

Trong kiểm thử tự động, có thể tạo các chuỗi ngẫu nhiên gồm chèn và xóa khóa, sau mỗi thao tác chạy một **bộ kiểm chứng bất biến độc lập** như ví dụ. Song song, so sánh tập khóa duyệt từ cây với một tập tham chiếu giúp phát hiện trường hợp cây vẫn cân bằng nhưng **trả về dữ liệu sai**.

## 11. Những nhầm lẫn phổ biến

1. **“Nút trong có `k` khóa thì có `k` con.”** Sai: nó cần `k+1` con để phân chia đầy đủ các khoảng.
2. **“Nút lá cũng phải có `k+1` con.”** Sai: lá không có nhánh con. Nó chỉ cần tuân giới hạn khóa.
3. **“Mọi nút, kể cả gốc, phải có ít nhất `t-1` khóa.”** Sai: gốc của cây không rỗng có thể chỉ có một khóa, dù `t` lớn.
4. **“Mọi nút cần đúng `2t-1` khóa.”** Sai: đó là **cận trên**, còn các nút hợp lệ được phép chưa đầy.
5. **“Mọi lá cần số khóa bằng nhau.”** Sai: chúng chỉ cần cùng **độ sâu**, không bắt buộc có cùng số khóa.
6. **“Nếu khóa trong từng nút đã sắp tăng thì toàn cây hợp lệ.”** Sai: cần kiểm tra khoảng khóa của toàn bộ các cây con.
7. **“Cây có mọi lá ở cùng độ sâu thì chắc chắn là B-tree.”** Sai: vẫn có thể sai số khóa, thiếu con hoặc khóa đặt sai khoảng.
8. **“Sau khi xóa không cần sửa nút thiếu khóa vì tìm kiếm vẫn có thể chạy.”** Sai: việc bỏ qua sửa lỗi phá bất biến mức lấp đầy và những bảo đảm của thuật toán.
9. **“Chỉ kiểm tra số phần tử trong mảng `keys` vật lý là đủ.”** Sai: cài đặt có thể cấp phát dư; phải dùng số khóa **đang dùng**.
10. **“Gộp hai nút có thể làm số khóa vượt `2t-1` mà vẫn hợp lệ.”** Sai: với cách gộp chuẩn, hai nút tối thiểu và một khóa cha tạo đúng `2t-1` khóa.
11. **“Độ sâu đồng đều đảm bảo thời gian tìm O(1).”** Sai: chiều cao vẫn tăng theo O(log n), chứ không bị chặn bởi một hằng số cho mọi quy mô.
12. **“Bất biến B-tree và B+ tree hoàn toàn giống nhau ở mọi loại nút.”** Không. B+ tree thường dùng khóa phân cách tại nút trong và bản ghi ở lá; mức lấp đầy, xử lý khóa bằng nhau và cấu trúc lá cần theo quy ước triển khai cụ thể.

## 12. Tự kiểm tra

**Câu 1.** B-tree có bậc tối thiểu `t=3`. Một lá không phải gốc có một khóa có hợp lệ không?

**Đáp án:** Không. Lá không phải gốc cần ít nhất `t-1=2` khóa.

**Câu 2.** Với `t=4`, một nút trong không phải gốc có năm khóa. Nó phải có bao nhiêu con, và số khóa có hợp lệ không?

**Đáp án:** Phải có **sáu con**. Nút chứa năm khóa là hợp lệ vì giới hạn là `3` đến `7` khóa.

**Câu 3.** B-tree có gốc là nút trong chứa một khóa, hai con; `t=6`. Có vi phạm cận dưới không?

**Đáp án:** Không. Gốc là ngoại lệ về mức lấp đầy: một khóa và hai con vẫn hợp lệ khi cây không rỗng.

**Câu 4.** Một nút trong chứa `[20 | 40]` và có hai con trỏ. Sai điều gì?

**Đáp án:** Hai khóa tạo ba khoảng; nút trong phải có **ba** con thực, không phải hai.

**Câu 5.** Các lá của một cây `t=2` lần lượt chứa 1, 2 và 3 khóa, đều nằm ở độ sâu 2. Có tự động sai bất biến cân bằng không?

**Đáp án:** Không. Số khóa 1–3 đều nằm trong giới hạn, và mọi lá cùng độ sâu. Cần kiểm tra thêm cấu trúc nút trong và khoảng khóa trước khi kết luận toàn cây hợp lệ.

**Câu 6.** Cây có gốc `[30 | 60]` và nút ở nhánh giữa chứa `[40 | 65]`. Dù nút giữa được sắp tăng, lỗi nằm ở đâu?

**Đáp án:** `65` vượt cận trên `60` của nhánh giữa. Nút giữa vi phạm bất biến khoảng khóa do gốc xác định.

**Câu 7.** Một cây có tất cả nút chứa đúng số khóa và con nhưng một lá sâu hơn các lá khác một tầng. Nó có phải B-tree hợp lệ không?

**Đáp án:** Không. B-tree phải có tất cả lá cùng độ sâu.

**Câu 8.** Với `t=2`, tách nút đầy `[10 | 20 | 30]` thành những nút nào?

**Đáp án:** Đẩy `20` lên cha (hoặc tạo gốc mới), giữ `[10]` ở nút trái và `[30]` ở nút phải. Nếu là nút trong, phải phân chia bốn cây con đúng khoảng.

**Câu 9.** Vì sao gộp hai nút mỗi nút có `t-1` khóa cùng một khóa ở cha tạo ra nút hợp lệ?

**Đáp án:** Tổng khóa là `(t-1)+1+(t-1)=2t-1`, đúng mức tối đa của B-tree bậc tối thiểu `t`.

**Câu 10.** Với `t=3` và chiều cao `h=2` tính theo số cạnh, cây không rỗng có ít nhất bao nhiêu khóa?

**Đáp án:** `2t^h-1=2\times 3^2-1=17` khóa.

**Câu 11.** Tại sao bộ kiểm tra sâu nên truyền cận dưới và cận trên từ tổ tiên xuống mỗi nút?

**Đáp án:** Một nút có thể đặt khóa nằm đúng so với cha gần nhất nhưng vẫn vi phạm một cận do tổ tiên cao hơn quy định. Truyền cận tích lũy phát hiện trường hợp đó.

**Câu 12.** Khi nào được dùng `root = null` để biểu diễn B-tree?

**Đáp án:** Khi cây rỗng theo quy ước cài đặt. Cây không rỗng phải có gốc chứa ít nhất một khóa.

**Câu 13.** Trong bộ kiểm tra Java, vì sao một lá với `children.length == 0` không bị yêu cầu phải có `keyCount+1` con?

**Đáp án:** Vì quy tắc `k+1` con chỉ áp dụng cho **nút trong**. Lá là điểm kết thúc đường tìm kiếm và không có con.

**Câu 14.** Nếu một cây được khai báo theo `order m=5` là tối đa năm con, có thể áp ngay quy tắc `t=3` và cho nút sáu con không?

**Đáp án:** Không. Với `m=5`, giới hạn tối đa vẫn là **năm con**. Quy tắc `t=3` cho tối đa sáu con; hai quy ước không tương đương hoàn toàn ở trường hợp này.

**Câu 15.** Những bất biến nào cần kiểm tra sau một phép xóa làm gốc trung gian không còn khóa?

**Đáp án:** Nếu gốc rỗng có đúng một con, nâng con ấy làm gốc mới; sau đó kiểm tra giới hạn khóa, số con, khoảng khóa và độ sâu của các lá. Nếu cây hết khóa, chuyển về biểu diễn cây rỗng phù hợp.

**Điểm ghi nhớ:** B-tree không chỉ là một cây có nhiều khóa trên mỗi nút. Theo bậc tối thiểu `t`, mỗi nút không phải gốc có **`t-1` đến `2t-1` khóa**, mỗi nút trong có **`k+1` con thực**, các cây con nằm trong **đúng khoảng khóa**, và **mọi lá cùng độ sâu**. Các bất biến kết hợp với ngoại lệ của gốc làm cây cân bằng, giúp tìm kiếm và cập nhật giữ chi phí theo chiều cao O(log n).
