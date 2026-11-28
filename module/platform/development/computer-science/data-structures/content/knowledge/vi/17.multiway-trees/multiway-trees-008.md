# B+-tree và việc lưu bản ghi ở tầng lá

**B+ tree** (*B-plus tree*) là một biến thể quan trọng của cây tìm kiếm nhiều nhánh cân bằng. Điểm đặc trưng của mô hình B+ tree thông dụng là **nút trong dùng khóa phân cách và con trỏ để định tuyến**, còn **các mục dữ liệu có thể truy xuất** được tổ chức ở **tầng lá**. Các lá thường nối với nhau theo thứ tự khóa, cho phép vừa tìm một khóa nhanh vừa duyệt một khoảng khóa thuận tiện.

Hãy tưởng tượng một chỉ mục khách hàng chứa hàng triệu mã khách hàng. Để tìm mã `1050`, chương trình không muốn đi qua từng bản ghi; nó đọc một số trang **nút trong** để chọn đúng nhánh rồi tới **trang lá** chứa mục chỉ mục. Để tìm tất cả khách hàng có mã từ `1050` tới `1100`, chương trình có thể tìm lá đầu tiên, sau đó tiếp tục quét các lá kế tiếp.

Bài này làm rõ ý nghĩa của từ **“bản ghi nằm ở lá”**, sự khác nhau giữa bản ghi thật và con trỏ tới bản ghi, quy tắc so sánh khi khóa bằng khóa phân cách, cách tách nút lá/nút trong, độ phức tạp và ví dụ Java triển khai B+ tree nhỏ cho các phép **thêm, tìm kiếm và quét khoảng**.

## 1. B+ tree khác B-tree ở điểm nào?

Trong một mô hình **B-tree cổ điển**, cả nút trong và lá có thể chứa **khóa gắn với dữ liệu**. Do đó, khi tìm thấy khóa ở nút trong, thuật toán có thể lấy kết quả ngay tại đó.

Trong **B+ tree thông dụng**:

- **Nút trong** (*internal node*) chứa các **khóa phân cách** (*separator keys*) và con trỏ tới những trang/nút con; nhiệm vụ chính là **định tuyến**.
- **Nút lá** (*leaf node*) chứa các mục **khóa → giá trị**, **khóa → bản ghi**, hoặc **khóa → định danh/vị trí bản ghi** tùy thiết kế chỉ mục.
- **Mọi mục dữ liệu có thể truy xuất bằng khóa** đều được tìm ở lá. Việc một giá trị khóa xuất hiện ở nút trong **không có nghĩa bản ghi tương ứng nằm tại nút trong**.
- **Mọi lá cùng độ sâu**, giống tinh thần cân bằng của họ B-tree; các lá thường có liên kết `next` và đôi khi `prev`.

Ví dụ:

```text
                         NÚT TRONG
                         [30 | 50 | 70]
                        /     |    |     \
                       /      |    |      \
NÚT LÁ       [10:An, 20:Bình] [30:Chi, 40:Dũng] [50:Hà, 60:Lan] [70:Mai, 80:Nam]
                 |                 |                 |                 |
                 +------ next ---->+------ next ---->+------ next ----> null

Ở đây "30" xuất hiện ở cả:
  - nút trong: chỉ làm ranh giới định tuyến;
  - nút lá: là khóa của mục dữ liệu 30:Chi.
```

Sơ đồ sử dụng giá trị ngắn như `An`, `Bình` cho dễ quan sát. Trong chỉ mục thật, lá có thể giữ địa chỉ bản ghi chứ không chứa toàn bộ thông tin của khách hàng.

| Tiêu chí | B-tree theo mô hình khóa/dữ liệu tại mọi tầng | B+ tree thông dụng |
| --- | --- | --- |
| Nút trong | Có thể chứa khóa gắn với dữ liệu | Chủ yếu chứa khóa phân cách và con trỏ con |
| Nơi có các mục dữ liệu tìm được theo khóa | Có thể ở nút trong hoặc lá | **Ở lá** |
| Khi gặp khóa bằng khóa nút trong | Có thể hoàn tất tìm kiếm | **Thường tiếp tục xuống lá** |
| Truy vấn khoảng | Có thể duyệt cây theo thứ tự | Dễ quét liên tiếp nhờ liên kết giữa lá |
| Khóa được lặp ở nhiều tầng | Không cần lặp theo kiểu separator–leaf | Có thể có cùng giá trị khóa ở nút trong và lá |
| Mức sử dụng nút trong | Có thể dành chỗ cho dữ liệu | Thường dành nhiều chỗ cho thông tin định tuyến |

**Lưu ý về thuật ngữ:** Không phải mọi biến thể B-tree hay B+ tree đều có bố cục vật lý giống nhau. Bài học dùng một mô hình B+ tree rõ ràng để suy luận, còn chi tiết trang, nén khóa, lưu bản ghi và xử lý trùng khóa phụ thuộc hệ quản trị hoặc thư viện cụ thể.

## 2. “Bản ghi nằm ở lá” nghĩa là gì?

Cần phân biệt ba thứ thường được gọi chung là “dữ liệu”:

1. **Khóa** (*key*): giá trị dùng để tìm kiếm, như `customer_id = 1050`.
2. **Mục chỉ mục** (*index entry*): ánh xạ từ khóa đến một giá trị hoặc vị trí liên quan.
3. **Bản ghi thật** (*record/row*): toàn bộ dữ liệu nghiệp vụ, có thể rất lớn.

Có hai tổ chức thường gặp.

### 2.1. Lá chứa trực tiếp bản ghi hoặc dữ liệu liên quan

```text
Nút trong:       [1050 | 1100]
                   /    |    \
                  ...  ...   ...

Một lá:         [1050 | Tên, địa chỉ, trạng thái ...]
                [1060 | Tên, địa chỉ, trạng thái ...]
```

Khi tìm tới lá, ứng dụng có thể đọc dữ liệu từ chính mục ở lá. Cách tổ chức này gần với **chỉ mục phân cụm** hoặc cấu trúc mà các lá chứa bản ghi, dù ý nghĩa “clustered” còn phụ thuộc hệ quản trị cơ sở dữ liệu.

### 2.2. Lá chỉ giữ con trỏ hoặc mã bản ghi

```text
Nút trong:       [1050 | 1100]           (định tuyến)

Nút lá:          [1050 -> RID_7]
                 [1060 -> RID_19]
                          |
                          v
                 Vùng lưu bản ghi riêng
                    RID_19 -> hàng đầy đủ
```

Một chỉ mục phụ có thể lưu `(khóa, record_id)`, định danh trang/slot, khóa chính của bản ghi, hoặc cách trỏ khác. Khi đó, tìm tới lá mới có **mục chỉ mục**, sau đó có thể cần thêm thao tác lấy bản ghi thật.

Vì vậy, phát biểu chính xác là:

> **B+ tree tổ chức các mục dữ liệu của chỉ mục ở lá; mục lá có thể chứa bản ghi thật hoặc tham chiếu tới bản ghi tùy cài đặt.**

Không nên hiểu rằng mọi B+ tree bắt buộc nhét toàn bộ hàng dữ liệu vào trang lá. Cũng không nên cho rằng nút trong hoàn toàn không lưu byte nào liên quan đến khóa dữ liệu: nó vẫn phải chứa **các khóa phân cách** để dẫn đường.

## 3. Bất biến định tuyến: `k` khóa phân cách, `k+1` con

Giả sử một nút trong chứa `k` khóa phân cách tăng nghiêm ngặt:

\[
S_0<S_1<\dots<S_{k-1}.
\]

Nút có `k+1` con trỏ:

\[
P_0,P_1,\dots,P_k.
\]

Trong bài này, ta chọn quy ước rất phổ biến: **`S_i` bằng khóa nhỏ nhất trong cây con nằm ngay bên phải `P_{i+1}`** (tức `S_i = min(P_{i+1})`). Theo quy ước đó:

| Con | Khoảng giá trị được định tuyến |
| --- | --- |
| `P0` | `x < S0` |
| `Pi` với `1 <= i < k` | `S{i-1} <= x < Si` |
| `Pk` | `x >= S{k-1}` |

Sơ đồ:

```text
                            [30 | 50 | 70]
                           /     |    |     \
                          P0     P1   P2     P3

P0: x < 30
P1: 30 <= x < 50
P2: 50 <= x < 70
P3: x >= 70
```

**Điểm mấu chốt là dấu bằng nằm ở nhánh phải.** Nếu tìm `50`, thuật toán phải đi `P2`, vì khóa `50` nằm ở lá của cây con bắt đầu bằng `50`.

### `upper_bound` thay vì kết thúc khi bằng khóa

Để chọn con, tìm chỉ số đầu tiên có separator **lớn hơn hẳn** `x`:

\[
i=\min\{j\mid S_j>x\},
\]

và nếu không có separator thỏa điều kiện, đặt `i=k`.

Đó là thao tác **`upper_bound(x)`**:

```text
separators = [30, 50, 70]

x =  9  -> upper_bound = 0 -> P0
x = 30  -> upper_bound = 1 -> P1  (bằng separator, đi PHẢI)
x = 45  -> upper_bound = 1 -> P1
x = 50  -> upper_bound = 2 -> P2
x = 70  -> upper_bound = 3 -> P3
x = 99  -> upper_bound = 3 -> P3
```

Trong B-tree cổ điển lưu dữ liệu tại nút trong, một thuật toán `lower_bound` có thể dừng khi khóa bằng khóa trong nút. **Không được áp dụng quy tắc dừng đó cho B+ tree này**, vì separator chỉ phục vụ định tuyến.

Một số hệ thống dùng khóa lớn nhất của cây con bên trái thay vì khóa nhỏ nhất của cây con bên phải, hoặc có cách biểu diễn khóa phân cách ngắn hơn khóa thật. Khi đó, quy tắc xử lý dấu bằng phải được xác định lại theo hợp đồng cài đặt; `upper_bound` ở đây chỉ đúng cho **quy ước đã nêu**.

## 4. Tìm chính xác một khóa: luôn đi tới lá

Xét:

```text
                    [30 | 50 | 70]
                   /     |    |      \
                  /      |    |       \
             [10, 20] [30, 40] [50, 60] [70, 80]
                 |        |        |        |
                 +------->+------->+-------> null
```

Tìm `50`:

1. Tại gốc, tính `upper_bound([30,50,70], 50)=2`.
2. Theo `P2` tới lá `[50,60]`.
3. Tại lá, dùng `lower_bound(50)` để tìm vị trí khóa **đầu tiên không nhỏ hơn 50**.
4. Phát hiện khóa bằng `50` và trả về mục dữ liệu tương ứng.

Tìm `55`:

1. Ở gốc, `upper_bound(55)=2` nên chọn `P2`.
2. Lá `[50,60]` không có khóa 55; trả về **không tìm thấy**.
3. Không cần thăm các lá còn lại: các khoảng định tuyến bảo đảm kết luận.

Tìm `30`:

1. `upper_bound(30)=1` nên chọn `P1`, **không dừng ở gốc**.
2. Tìm khóa 30 trong lá `[30,40]` và trả về mục dữ liệu.

### Mã giả tìm kiếm

```text
find(root, x):
    if root == null:
        return NOT_FOUND

    node = root
    while node is not a leaf:
        i = upperBound(node.separators, x)
        node = node.children[i]

    j = lowerBound(node.keys, x)
    if j < node.keyCount and node.keys[j] == x:
        return node.values[j]    # hoặc record ID / con trỏ bản ghi
    return NOT_FOUND
```

Tìm kiếm thất bại khi lá không có mục khóa cần tìm, chứ không phải khi một khóa bất kỳ “thiếu” ở nút trong. Một separator bằng `x` chỉ quyết định con nào sẽ giữ khóa `x`.

## 5. Liên kết lá làm truy vấn khoảng trở nên tự nhiên

Nếu cần tìm **tất cả khóa trong đoạn `[a,b]`**, thực hiện:

1. Đi từ gốc tới **lá có thể chứa `a`**, bằng quy tắc `upper_bound` tại từng nút trong.
2. Tìm `lower_bound(a)` bên trong lá đó.
3. Đọc lần lượt những mục có `a <= key <= b`.
4. Khi hết một lá, theo con trỏ `next` sang **lá kế tiếp**.
5. Dừng ngay khi gặp khóa `> b` hoặc hết chuỗi lá.

Ví dụ:

```text
                        [30 | 50 | 70]
                       /     |    |      \
            [10,20] -> [30,40] -> [50,60] -> [70,80] -> null

Tìm khoảng [25, 65]:
   - định tuyến theo 25 tới lá [10,20]
   - lower_bound(25) ở lá đầu = hết lá
   - next tới [30,40], lấy 30,40
   - next tới [50,60], lấy 50,60
   - next tới [70,80], thấy 70 > 65 nên dừng

Kết quả: [30, 40, 50, 60]
```

Không cần quay lại nút gốc sau mỗi mục, cũng không phải duyệt tất cả các nút trong theo thứ tự. Đây là ưu điểm rất quan trọng của **liên kết lá** đối với truy vấn phạm vi, duyệt có thứ tự và những phép lấy một dải khóa.

### Vì sao không bắt buộc đi từ lá đầu tiên?

Với tập có hàng triệu khóa, bắt đầu quét từ lá trái nhất để tìm `a` có thể rất tốn thời gian. B+ tree tận dụng hai cơ chế:

- **Nút trong** đưa trực tiếp tới vùng bắt đầu của khoảng.
- **Liên kết lá** đưa nhanh qua các vùng giá trị kế tiếp.

Kết hợp này giúp truy vấn `[a,b]` không phải duyệt các phần tử nằm trước `a`.

## 6. Tách nút lá: sao chép khóa phân cách lên cha

Khi chèn vào một lá đang đầy, B+ tree phải tạo thêm một lá để giữ các mục dữ liệu. Điểm đặc biệt là **khóa phân cách đưa lên cha thường vẫn được giữ lại trong lá**, thay vì bị đưa hẳn khỏi tầng lá như mô hình tách B-tree cổ điển.

Giả sử một **lá có sức chứa tối đa ba mục** và cần thêm `40` vào lá `[10,20,30]`:

```text
Trước chèn:
                [10:A | 20:B | 30:C]       (lá đầy)

Chèn tạm vào danh sách đã sắp:
                [10:A | 20:B | 30:C | 40:D]

Tách lá:
                [10:A | 20:B] --> [30:C | 40:D]
                                    ^
                              min của lá phải = 30

Đưa bản sao khóa 30 lên nút cha để định tuyến:

                              [30]
                             /    \
                     [10:A,20:B]  [30:C,40:D]
```

Khóa `30` tại nút trong **không có bản ghi `C` kèm theo** trong mô hình bài này; bản ghi `30:C` vẫn nằm tại lá phải. Nút cha chỉ cần khóa phân cách `30` để điều hướng tìm kiếm.

### Tại sao phải sao chép khóa ở lá?

Nếu đưa khóa `30` lên cha rồi **xóa nó khỏi lá**, một phép tìm `30` đi xuống lá theo quy tắc của B+ tree lại không tìm thấy bản ghi. Quy tắc “mọi mục dữ liệu ở lá” sẽ bị phá.

Phép tách lá đúng phải giữ đủ các mục cũ và mục mới:

\[
\text{các mục lá trái} \cup \text{các mục lá phải}
= \text{các mục trước tách cộng mục mới}.
\]

Khóa `30` ở cha là **bản sao định tuyến**, không phải một bản ghi mới. Do đó, **số mục dữ liệu không tăng chỉ vì có separator mới ở tầng trong**.

### Cập nhật liên kết `next`

Nếu lá cũ là `L`, lá mới là `R`:

```text
R.next = L.next
L.next = R
```

Nếu trước tách `L` đã trỏ tới một lá `T`, sau tách chuỗi phải là `L -> R -> T`. Quên cập nhật liên kết có thể khiến tìm kiếm chính xác vẫn đúng nhưng **truy vấn khoảng bỏ sót cả một lá**.

## 7. Tách nút trong: chỉ phân phối thông tin định tuyến

Nút trong giữ khóa phân cách và con trỏ con. Khi một nút trong bị tràn, ta chia **mảng khóa phân cách và mảng con** thành hai nút, đưa một khóa phân cách phù hợp lên cha.

Ví dụ nút trong đã có bốn khóa phân cách và năm con, trong khi sức chứa tối đa theo mô hình minh họa là ba khóa:

```text
Trước tách:
                 [20 | 40 | 60 | 80]
                /   |    |    |     \
               P0  P1   P2   P3     P4

Tách:
                         (đẩy 60 lên cha)
                        /                \
                   [20 | 40]            [80]
                   /   |    \           /   \
                  P0  P1    P2         P3   P4
```

Nút trái giữ hai separator, ba con. Nút phải giữ một separator, hai con. Khóa `60` đã đưa lên cha **không cần tiếp tục tồn tại như separator trong hai nút trong con**, miễn các khoảng định tuyến còn đúng. Những **mục dữ liệu có khóa 60** vẫn nằm ở lá sâu hơn nếu có.

**Khác biệt cần ghi nhớ:**

| Thao tác | Khóa lên cha | Khóa ở tầng dưới sau tách |
| --- | --- | --- |
| **Tách lá** | **Sao chép** khóa nhỏ nhất của lá phải làm separator | Khóa cùng mục dữ liệu **vẫn nằm ở lá phải** |
| **Tách nút trong** | **Đẩy** separator thích hợp lên cha | Separator được đẩy có thể **không còn trong hai nút trong con**; dữ liệu ở lá không bị mất |

Không nên dùng cùng một phép chia mảng một cách máy móc cho hai loại nút. Tách nút trong còn phải bảo đảm mỗi nút có **số con bằng số separator cộng một**, và các con phải nằm đúng khoảng.

## 8. Ví dụ từng bước: từ một lá tới chuỗi lá

Để dễ mô phỏng, giả định:

- Mỗi **lá** được chứa tối đa **3 mục khóa–giá trị**.
- Mỗi **nút trong** được chứa tối đa **3 separator**, tương ứng tối đa 4 con.
- Khóa là số nguyên **không trùng**; cập nhật khóa cũ sẽ thay giá trị.
- Khi lá có 4 mục sau chèn, tách thành **2 mục trái + 2 mục phải**.

Chèn lần lượt `10,20,30,40,50,60,70,80`.

### Giai đoạn 1: lá đầu tiên đầy rồi tách

```text
Chèn 10,20,30:
                [10,20,30]            (gốc là lá)

Chèn 40, tách lá:
                     [30]
                    /    \
               [10,20] -> [30,40] -> null
```

Chính khóa `30` của lá phải được **sao chép lên gốc**.

### Giai đoạn 2: tiếp tục tách lá phải

```text
Chèn 50:
                     [30]
                    /    \
               [10,20] -> [30,40,50]

Chèn 60 làm lá phải tràn, tách tại 50:

                       [30 | 50]
                      /    |      \
                [10,20] -> [30,40] -> [50,60] -> null
```

Khóa `50` tại gốc là separator, còn mục dữ liệu `50` vẫn nằm trong lá thứ ba.

### Giai đoạn 3: nhiều lá, một nút trong

```text
Chèn 70 vào lá cuối:  [50,60,70]

Chèn 80 làm lá cuối tràn:

                     [30 | 50 | 70]
                    /     |     |      \
              [10,20] -> [30,40] -> [50,60] -> [70,80] -> null
```

Các lá có 2 mục mỗi lá và nằm ở **cùng độ sâu một cạnh dưới gốc**. Nút gốc chứa ba separator, bốn con.

### Chèn tiếp để làm nút trong tràn

Giả sử sau đó chèn `90`, `100`. Lá phải tách lần nữa và đưa separator `90` lên gốc:

```text
Nút trong tạm có bốn separator:

                      [30 | 50 | 70 | 90]
                     /     |     |    |    \
                [10,20] [30,40] [50,60] [70,80] [90,100]
```

Phải **tách nút trong** và tạo gốc mới; theo quy tắc ví dụ ở Mục 7, đưa `70` lên:

```text
                                 [70]                    (gốc mới)
                              /        \
                         [30 | 50]     [90]              (nút trong)
                        /   |    \      /  \
                    [10,20][30,40][50,60][70,80][90,100] (lá)

Liên kết lá vẫn là:
[10,20] -> [30,40] -> [50,60] -> [70,80] -> [90,100] -> null
```

Giờ một đường từ gốc đến lá đi qua hai cạnh. **Mọi lá đều cùng tăng độ sâu**, vì nút gốc mới được thêm phía trên toàn cây.

## 9. Java hoàn chỉnh: thêm, tìm và quét khoảng

Ví dụ sau hiện thực B+ tree nhỏ, với **khóa `int` phân biệt và giá trị `String` không `null`**. Mục dữ liệu chỉ xuất hiện trong các **nút lá**; nút trong chỉ giữ separator và con. Các lá được liên kết bằng `next`.

Để tập trung vào nguyên lý, chương trình dùng `ArrayList` cho mảng khóa/giá trị/con thay vì quản lý thủ công từng ô của bộ đệm. Bản cài đặt có **`MAX_KEYS = 3`**, nghĩa là nút trong chứa tối đa 3 separator và lá tối đa 3 mục. Phương thức `put` cập nhật giá trị nếu khóa đã có, còn khóa mới sẽ được thêm vào lá.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BPlusTreeLeafRecordsDemo {
    static final int MAX_KEYS = 3;

    static final class Node {
        final boolean leaf;
        final List<Integer> keys = new ArrayList<>();
        final List<String> values = new ArrayList<>(); // Chi la moi su dung.
        final List<Node> children = new ArrayList<>();  // Chi nut trong su dung.
        Node next; // Chi la moi su dung: lien ket la ke tiep.

        Node(boolean leaf) {
            this.leaf = leaf;
        }
    }

    static final class Split {
        final int separator;
        final Node right;

        Split(int separator, Node right) {
            this.separator = separator;
            this.right = right;
        }
    }

    static final class BPlusTree {
        private Node root;
        private int recordCount;

        int size() {
            return recordCount;
        }

        // Vi tri dau tien keys[i] >= key (dung tai la).
        private int lowerBound(List<Integer> keys, int key) {
            int lo = 0, hi = keys.size();
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (keys.get(mid) < key) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        // Vi tri dau tien separators[i] > key (chon con).
        private int upperBound(List<Integer> separators, int key) {
            int lo = 0, hi = separators.size();
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (separators.get(mid) <= key) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        private Node findLeaf(int key) {
            Node node = root;
            while (node != null && !node.leaf) {
                int index = upperBound(node.keys, key);
                node = node.children.get(index);
            }
            return node;
        }

        String get(int key) {
            Node leaf = findLeaf(key);
            if (leaf == null) {
                return null;
            }
            int index = lowerBound(leaf.keys, key);
            if (index < leaf.keys.size()
                    && leaf.keys.get(index) == key) {
                return leaf.values.get(index);
            }
            return null; // Khong co khoa.
        }

        // Tra true neu la khoa moi; false neu chi cap nhat gia tri.
        boolean put(int key, String value) {
            Objects.requireNonNull(value, "value");
            if (root == null) {
                root = new Node(true);
                root.keys.add(key);
                root.values.add(value);
                recordCount = 1;
                return true;
            }

            boolean isNew = (get(key) == null);
            Split split = insertRecursive(root, key, value);
            if (split != null) {
                Node newRoot = new Node(false);
                newRoot.keys.add(split.separator);
                newRoot.children.add(root);
                newRoot.children.add(split.right);
                root = newRoot;
            }
            if (isNew) {
                recordCount++;
            }
            return isNew;
        }

        // Co the tra split de nut cha gan separator va nut phai.
        private Split insertRecursive(Node node, int key, String value) {
            if (node.leaf) {
                int i = lowerBound(node.keys, key);
                if (i < node.keys.size() && node.keys.get(i) == key) {
                    node.values.set(i, value);
                    return null;
                }

                node.keys.add(i, key);
                node.values.add(i, value);
                if (node.keys.size() <= MAX_KEYS) {
                    return null;
                }

                // Tran 4 muc: chia 2 trai + 2 phai.
                int leftCount = (node.keys.size() + 1) / 2;
                Node right = new Node(true);
                right.keys.addAll(
                    node.keys.subList(leftCount, node.keys.size()));
                right.values.addAll(
                    node.values.subList(leftCount, node.values.size()));
                node.keys.subList(leftCount, node.keys.size()).clear();
                node.values.subList(leftCount, node.values.size()).clear();

                right.next = node.next;
                node.next = right;
                // Separator la min cua LA PHAI, van nam trong la.
                return new Split(right.keys.get(0), right);
            }

            int childIndex = upperBound(node.keys, key);
            Split childSplit = insertRecursive(
                node.children.get(childIndex), key, value);
            if (childSplit == null) {
                return null;
            }

            node.keys.add(childIndex, childSplit.separator);
            node.children.add(childIndex + 1, childSplit.right);
            if (node.keys.size() <= MAX_KEYS) {
                return null;
            }

            // Nut trong co 4 separator va 5 con: tach.
            int middle = node.keys.size() / 2;
            int promoted = node.keys.get(middle);
            Node right = new Node(false);
            right.keys.addAll(
                node.keys.subList(middle + 1, node.keys.size()));
            right.children.addAll(
                node.children.subList(middle + 1, node.children.size()));

            node.keys.subList(middle, node.keys.size()).clear();
            node.children.subList(middle + 1, node.children.size()).clear();

            // Promoted roi khoi mang separator cua nut trong cu,
            // nhung ban ghi co khoa do van nam trong tang la.
            return new Split(promoted, right);
        }

        List<String> range(int fromInclusive, int toInclusive) {
            List<String> result = new ArrayList<>();
            if (fromInclusive > toInclusive) {
                return result;
            }
            Node leaf = findLeaf(fromInclusive);
            if (leaf == null) {
                return result;
            }

            int i = lowerBound(leaf.keys, fromInclusive);
            while (leaf != null) {
                while (i < leaf.keys.size()) {
                    int key = leaf.keys.get(i);
                    if (key > toInclusive) {
                        return result;
                    }
                    result.add(key + ":" + leaf.values.get(i));
                    i++;
                }
                leaf = leaf.next;
                i = 0;
            }
            return result;
        }

        String leaves() {
            if (root == null) {
                return "(empty)";
            }
            Node node = root;
            while (!node.leaf) {
                node = node.children.get(0);
            }
            StringBuilder out = new StringBuilder();
            while (node != null) {
                if (out.length() > 0) {
                    out.append(" -> ");
                }
                out.append(node.keys);
                node = node.next;
            }
            return out.toString();
        }

        List<Integer> rootSeparators() {
            return root == null
                ? new ArrayList<>()
                : new ArrayList<>(root.keys);
        }
    }

    public static void main(String[] args) {
        BPlusTree tree = new BPlusTree();
        for (int key : new int[] {10, 20, 30, 40, 50, 60, 70, 80}) {
            tree.put(key, "V" + key);
        }

        System.out.println("Root: " + tree.rootSeparators());
        System.out.println("Leaves: " + tree.leaves());
        System.out.println("Get 50: " + tree.get(50));
        System.out.println("Get 35: " + tree.get(35));

        boolean isNew = tree.put(50, "V50*");
        System.out.println("Put duplicate adds record: " + isNew);
        System.out.println("Range [25,65]: " + tree.range(25, 65));
        System.out.println("Size: " + tree.size());
    }
}
```

Kết quả dự kiến:

```text
Root: [30, 50, 70]
Leaves: [10, 20] -> [30, 40] -> [50, 60] -> [70, 80]
Get 50: V50
Get 35: null
Put duplicate adds record: false
Range [25,65]: [30:V30, 40:V40, 50:V50*, 60:V60]
Size: 8
```

### Đọc cấu trúc mã

| Thành phần | Trách nhiệm |
| --- | --- |
| `Node.leaf` | Phân biệt nút lá với nút trong |
| `keys` của lá | Các khóa dữ liệu thực sự được tìm thấy |
| `values` của lá | Giá trị gắn với từng khóa, đúng cùng vị trí |
| `keys` của nút trong | Separator để định tuyến, **không phải bản ghi** |
| `children` của nút trong | `k+1` con tương ứng các khoảng |
| `next` | Liên kết sang lá kế tiếp để duyệt theo thứ tự |
| `lowerBound` | Tìm khóa hoặc vị trí chèn trong lá |
| `upperBound` | Quyết định nhánh, đưa khóa bằng separator sang **bên phải** |
| `Split.separator` | Khóa phân cách báo lên cha sau khi tách |
| `range` | Tìm lá bắt đầu rồi quét các lá liên tiếp |

Chương trình cố tình giới hạn mỗi nút ba khóa để hình dạng cây dễ theo dõi. Với cây thực tế lưu trên đĩa, số khóa có thể lớn hơn nhiều, nút thường đại diện một trang, liên kết con có thể là mã trang thay cho đối tượng Java trực tiếp.

**Giới hạn của ví dụ:** Cài đặt chỉ hỗ trợ **thêm/cập nhật, tìm chính xác và quét khoảng**. Nó chưa triển khai **xóa**, cân bằng lại sau xóa, truy cập đồng thời, lưu trữ bền vững hoặc xử lý lỗi cấp phát. Không dùng nguyên mẫu này thay cho chỉ mục cơ sở dữ liệu sản xuất.

## 10. Xóa trong B+ tree và cập nhật separator

Khi xóa một mục khỏi lá, có hai vấn đề độc lập:

1. **Mức lấp đầy:** sau xóa, lá có thể còn dưới số mục tối thiểu; phải **mượn mục từ lá anh em** hoặc **gộp lá**, tương tự tư tưởng tái cân bằng B-tree.
2. **Tính đúng của separator:** vì separator theo quy ước này phản ánh **khóa nhỏ nhất ở cây con phải**, nếu khóa nhỏ nhất thay đổi thì các separator liên quan phải được cập nhật.

### Ví dụ xóa làm thay khóa nhỏ nhất của một lá

```text
Ban đầu:
                       [30 | 50]
                      /    |     \
                 [10,20] [30,40] [50,60]
                             ^
                       min lá giữa = 30

Giả sử xóa khóa 30 khỏi lá giữa:
                       [40]            (min mới của lá giữa)
```

Nếu lá giữa vẫn đạt mức lấp đầy hợp lệ theo chính sách cụ thể, separator của nhánh đó phải chuyển từ `30` thành **`40`**:

```text
                       [40 | 50]
                      /    |     \
                 [10,20]  [40]  [50,60]
```

Trong cấu hình ví dụ ở Mục 9, lá tối đa ba mục và thường cần ít nhất hai mục nếu không phải gốc, nên lá chỉ còn một mục **chưa đủ lấp đầy**. Khi ấy phải mượn/gộp và cập nhật separator theo **trạng thái cuối cùng**; sơ đồ `[40]` ở trên chỉ minh họa nhu cầu cập nhật separator, không phải trạng thái hoàn chỉnh hợp lệ cho mọi cấu hình.

**Quan trọng:** Khi khóa nhỏ nhất của **một cây con** thay đổi, separator cần sửa có thể nằm ở **tổ tiên**, không chỉ ở cha trực tiếp. Thuật toán xóa hoặc cân bằng lại phải giữ bất biến định tuyến trên toàn đường liên quan.

### Gộp lá và nối lại chuỗi

Nếu gộp lá `L` với lá kế bên `R`:

- Chuyển các mục dữ liệu của `R` sang `L` theo thứ tự.
- Đặt `L.next = R.next` để bỏ `R` khỏi chuỗi lá.
- Xóa con trỏ tới `R` cùng separator phân cách tương ứng trong cha.
- Nếu cha thiếu khóa/con, tiếp tục mượn/gộp ở tầng trên.
- Nếu gốc mất separator cuối và còn một con, **nâng con đó làm gốc mới**.

Khác với việc xóa một khóa khỏi B-tree có dữ liệu ở nút trong, xóa B+ tree phải bảo đảm **mục dữ liệu ở lá được xóa**, còn separator là thông tin định tuyến được bảo trì theo các lá đang tồn tại.

## 11. Fan-out, bố cục trang và chi phí truy vấn

### Nút trong có thể chứa rất nhiều con trỏ

Giả sử một trang chỉ mục có 4.096 byte, phần header chiếm 128 byte; mỗi separator dài 16 byte và mỗi định danh trang con dài 8 byte. Với `k` separator và `k+1` con:

\[
128+16k+8(k+1)\le4096.
\]

Suy ra:

\[
136+24k\le4096\quad\Rightarrow\quad k\le165.
\]

Trong mô hình rất đơn giản này, một trang nút trong có thể chứa tối đa **165 separator và 166 con trỏ con**. Hệ số phân nhánh (*fan-out*) cao giúp giảm chiều cao cây, từ đó thường giảm số lần cần chuyển trang khi tìm.

Đây chỉ là phép tính minh họa. Trang thực tế cần thêm slot directory, cờ, thông tin cấp phát, nén tiền tố khóa, căn chỉnh hoặc metadata khác, nên sức chứa khác nhau giữa các hệ thống.

### Lá có sức chứa phụ thuộc kiểu mục dữ liệu

Giữ giả định trang 4.096 byte và header 128 byte. Nếu lá còn dùng 8 byte để lưu liên kết tới lá kế tiếp, mỗi mục chứa khóa 16 byte và `record_id` 8 byte, số mục `r` thỏa:

\[
128+8+(16+8)r\le4096\quad\Rightarrow\quad r\le165.
\]

Nếu thay `record_id` bằng bản ghi cố định 256 byte (cùng khóa 16 byte), cùng mô hình có:

\[
128+8+(16+256)r\le4096\quad\Rightarrow\quad r\le14.
\]

| Kiểu dữ liệu của mục lá (giả định) | Sức chứa tính được trên trang 4 KiB |
| --- | ---: |
| Khóa 16 B + mã bản ghi 8 B | 165 mục |
| Khóa 16 B + dữ liệu bản ghi 256 B | 14 mục |

Đây là lý do cần phân biệt **“lá giữ bản ghi thật”** và **“lá giữ vị trí bản ghi”**. Cùng một B+ tree về mặt ý tưởng nhưng bố cục vật lý khác nhau có thể làm thay đổi số mục mỗi lá, số lá, số trang phải đọc và chi phí cập nhật.

### Độ phức tạp của tìm và quét khoảng

Gọi:

- `n` là số mục dữ liệu (không đếm các bản sao separator).
- `F` là hệ số phân nhánh hiệu dụng của nút trong.
- `L` là số mục lá được giữ trên mỗi trang lá khi các trang có mức lấp đầy được kiểm soát.
- `r` là số mục trả về của truy vấn khoảng.

| Thao tác | Chi phí điển hình |
| --- | --- |
| Tìm chính xác | Đi qua O(log_F n) tầng, cộng công tìm bên trong từng nút |
| Chèn một mục | Tìm lá, rồi có thể tách lá và lan tách nút trong tới gốc |
| Xóa một mục | Tìm lá, rồi có thể mượn/gộp và cập nhật separator |
| Quét `r` mục liên tiếp | Tìm lá đầu, sau đó đọc các lá kế tiếp chứa những mục cần trả |

Trong mô hình **mỗi nút là một trang**, truy vấn khoảng có số lần tiếp cận trang xấp xỉ:

\[
O\left(\log_F n+\left\lceil\frac{r}{L}\right\rceil+1\right),
\]

khi các lá có mức lấp đầy tương đối đều, các mục được phân bố thích hợp và không tính thêm bước đọc bản ghi thật ở vùng lưu riêng. Hằng số `+1` phản ánh việc có thể cần thăm một lá kết thúc hoặc lá bắt đầu chưa có kết quả. Nếu bản ghi thật nằm ngoài chỉ mục, mỗi mục hoặc nhóm mục có thể kéo theo thêm truy cập để lấy dữ liệu.

Khi `F` và `L` được xem là các hằng số theo cấu hình cây, thời gian tìm chính xác thường được mô tả O(log n); quét `r` mục có chi phí tổng O(log n + r) trong mô hình RAM với xử lý mục O(1). Trong thực tế, số lần I/O vật lý còn tùy trang đã được cache hay chưa và cách tổ chức bản ghi.

## 12. Khóa trùng và thứ tự nhiều bản ghi

Ví dụ Java chỉ cho phép **một mục cho mỗi khóa**: chèn lại khóa cũ là **cập nhật giá trị**. Nhưng trong một **chỉ mục phụ**, nhiều hàng có thể chia sẻ một giá trị khóa, chẳng hạn cùng `department_id`.

Các thiết kế thường gặp:

- Mỗi khóa trỏ tới một **danh sách định danh bản ghi**.
- Lưu nhiều mục dưới một **khóa ghép** như `(department_id, record_id)` để mỗi khóa vật lý là duy nhất.
- Dùng định dạng lá và quy tắc separator hỗ trợ các khóa trùng chạy qua nhiều lá.

Với khóa ghép `(department_id, record_id)`, một truy vấn theo phòng ban có thể tìm vị trí đầu cho `department_id` rồi quét các mục liên tiếp. Việc so sánh phải dùng **thứ tự từ điển nhất quán trên cả hai trường**.

Không thể chỉ thêm nhiều khóa bằng nhau vào ví dụ đang giả định các separator tăng nghiêm ngặt, bởi dấu bằng ở ranh giới giữa các lá sẽ cần một hợp đồng định tuyến mới. Trước khi hỗ trợ khóa trùng, phải định nghĩa rõ cách nhóm và cách tìm tất cả bản ghi khớp.

## 13. Những nhầm lẫn thường gặp

1. **“B+ tree không có khóa ở nút trong.”** Sai: nút trong có **khóa phân cách**, chỉ không giữ mục dữ liệu bản ghi theo mô hình này.
2. **“Gặp separator bằng khóa cần tìm là đã lấy được bản ghi.”** Sai: phải tiếp tục đi xuống lá.
3. **“Mọi B+ tree bắt buộc lưu cả hàng dữ liệu trong lá.”** Sai: lá có thể chứa `record_id` hoặc con trỏ đến bản ghi ở nơi khác.
4. **“Nút trong có `k` khóa thì cần `k` con.”** Sai: cần `k+1` con để biểu diễn đủ các khoảng.
5. **“Khóa bằng separator luôn chọn nhánh trái.”** Với quy ước `separator=min(right subtree)` của bài, khóa bằng phải **chọn nhánh phải**.
6. **“Dùng `lower_bound` để chọn nhánh trong mọi trường hợp.”** Với quy ước này, cần `upper_bound` để khóa bằng separator đi vào đúng nhánh.
7. **“Tách lá và đưa khóa đầu lá phải lên cha nghĩa là bỏ khóa đó khỏi lá.”** Sai: phải **giữ mục dữ liệu ở lá**; separator ở cha chỉ là bản sao định tuyến.
8. **“Tách nút trong giống hệt tách lá.”** Sai: nút trong còn phải chia con trỏ và có thể **đẩy separator ra khỏi hai nút con**.
9. **“Tìm khoảng cần quay về gốc sau mỗi bản ghi.”** Khi lá có liên kết, chỉ cần theo `next` giữa các lá.
10. **“Cứ lấy lá trái nhất để thực hiện mọi truy vấn khoảng.”** Nếu cận dưới lớn, nên tìm thẳng lá chứa vị trí bắt đầu để tránh đọc dữ liệu không liên quan.
11. **“Gộp/xóa lá không cần sửa separator.”** Nếu khóa nhỏ nhất của cây con phải thay đổi hoặc số con thay đổi, separator liên quan phải được cập nhật.
12. **“Gộp lá không ảnh hưởng chuỗi liên kết.”** Sai: phải cập nhật `next` để không bỏ sót hoặc duyệt lại một lá đã bị loại.
13. **“Chiều cao thấp đồng nghĩa mọi truy vấn nhanh O(1).”** Vẫn cần định tuyến qua các tầng và xử lý nhiều mục nếu truy vấn khoảng.
14. **“Số separator và số bản ghi có thể cộng làm một `n` cho phân tích.”** Separator có thể lặp khóa ở lá; quy mô dữ liệu `n` nên được xác định theo **số mục lá** hoặc theo mô hình cụ thể.
15. **“Liên kết lá luôn giảm số I/O của truy vấn khoảng xuống một.”** Quét nhiều lá vẫn cần đọc nhiều trang; liên kết lá chỉ tránh phải tìm lại đường từ gốc giữa các lá kế tiếp.

## 14. Tự kiểm tra

**Câu 1.** Trong B+ tree thông dụng, nút trong và nút lá có nhiệm vụ khác nhau như thế nào?

**Đáp án:** Nút trong chứa separator và con trỏ để định tuyến. Nút lá chứa các mục dữ liệu của chỉ mục (bản ghi, giá trị hoặc định danh bản ghi tùy thiết kế).

**Câu 2.** Với separator `[30,50,70]` theo quy ước khóa nhỏ nhất của nhánh phải, tìm khóa `50` phải chọn `P1` hay `P2`?

**Đáp án:** `P2`. Khóa bằng separator thuộc nhánh phải tương ứng; `upper_bound(50)=2`.

**Câu 3.** Nút trong có ba separator thì phải có bao nhiêu con trỏ con?

**Đáp án:** Bốn con, vì ba ranh giới tạo bốn khoảng giá trị.

**Câu 4.** Vì sao tìm thấy separator bằng `30` ở nút trong không có nghĩa đã tìm thấy bản ghi `30`?

**Đáp án:** Separator là thông tin định tuyến. Mục dữ liệu `30` nằm trong lá, hoặc lá giữ vị trí bản ghi tương ứng.

**Câu 5.** Nếu lá chỉ chứa `(khóa, record_id)`, cần thêm bước gì để lấy bản ghi đầy đủ?

**Đáp án:** Dùng định danh/vị trí bản ghi để đọc bản ghi từ vùng lưu trữ tương ứng, trừ khi hệ thống đã có dữ liệu cần thiết trong chỉ mục hoặc cache.

**Câu 6.** Tách lá `[10,20,30,40]` thành hai lá `[10,20]` và `[30,40]` theo mô hình bài. Khóa nào được sao chép lên cha, và khóa đó có còn ở lá không?

**Đáp án:** Sao chép `30` lên cha. Mục dữ liệu có khóa `30` vẫn nằm trong lá phải.

**Câu 7.** Khi tách nút trong có separator `[20,40,60,80]` và năm con, bài chọn separator nào đưa lên cha? Các nút con giữ bao nhiêu separator?

**Đáp án:** Đẩy `60` lên cha; nút trong trái giữ `[20,40]` (ba con), nút trong phải giữ `[80]` (hai con).

**Câu 8.** Tại sao tách lá phải cập nhật `next`?

**Đáp án:** Để lá mới xuất hiện đúng vị trí trong chuỗi lá theo thứ tự, bảo đảm truy vấn khoảng không bỏ sót hoặc lặp lại các mục.

**Câu 9.** Với các lá `[10,20] -> [30,40] -> [50,60] -> [70,80]`, truy vấn `[25,65]` trả về gì?

**Đáp án:** `[30,40,50,60]`.

**Câu 10.** Sau khi tìm lá đầu cho truy vấn khoảng, có cần quay về gốc để tìm từng lá kế tiếp không?

**Đáp án:** Không, nếu các lá được nối bằng `next`. Có thể quét trực tiếp các lá kế tiếp cho đến khi vượt cận trên.

**Câu 11.** Một lá đang có khóa nhỏ nhất `30`, xóa `30` khiến khóa nhỏ nhất mới là `40`. Điều gì có thể phải cập nhật ngoài lá?

**Đáp án:** Separator phản ánh khóa nhỏ nhất của cây con đó có thể phải đổi từ 30 sang 40, đồng thời cần sửa mức lấp đầy qua mượn/gộp nếu lá thiếu mục.

**Câu 12.** Vì sao khi xóa/gộp một lá phải cập nhật liên kết giữa các lá?

**Đáp án:** Vì lá bị loại không còn thuộc chuỗi lá hợp lệ; con trỏ `next` của lá trước phải dẫn tới lá kế tiếp đúng.

**Câu 13.** Với trang 4 KiB, header 128 B, liên kết lá 8 B, khóa 16 B và mã bản ghi 8 B mỗi mục, sức chứa lý tưởng của lá là bao nhiêu?

**Đáp án:** `floor((4096-128-8)/(16+8))=165` mục, chưa tính các metadata hay căn chỉnh khác.

**Câu 14.** Nếu thay mã bản ghi 8 B bằng dữ liệu 256 B thì sức chứa cùng mô hình trở thành bao nhiêu mục?

**Đáp án:** `floor(3960/(16+256))=14` mục.

**Câu 15.** Vì sao độ phức tạp của truy vấn khoảng thường gồm cả chi phí tìm điểm bắt đầu và chi phí quét lá?

**Đáp án:** Trước tiên phải định tuyến đến lá có cận dưới trong O(log_F n) tầng; sau đó phải xử lý các mục thuộc khoảng và những trang lá liên tiếp được quét.

**Câu 16.** Nếu chỉ mục có nhiều bản ghi trùng `department_id`, có những cách nào để B+ tree lưu chúng?

**Đáp án:** Có thể lưu danh sách `record_id` dưới một khóa, hoặc dùng khóa ghép `(department_id, record_id)`, hoặc định nghĩa quy tắc hỗ trợ khóa trùng rõ ràng trong nhiều lá.

**Câu 17.** B+ tree và B-tree có giống nhau hoàn toàn về xử lý khóa bằng khóa nút trong không?

**Đáp án:** Không. Trong mô hình B-tree có dữ liệu tại nút trong, có thể dừng khi tìm thấy khóa. Trong B+ tree thông dụng, nút trong dùng để định tuyến nên phải đi xuống lá để lấy mục dữ liệu.

**Điểm ghi nhớ:** **B+ tree phân tách nhiệm vụ định tuyến và lưu mục dữ liệu**: nút trong giữ separator cùng các con trỏ, còn các mục khóa–giá trị hoặc khóa–vị trí bản ghi nằm tại **tầng lá**. Với quy ước `separator=min(cây con phải)`, khóa bằng separator phải đi **nhánh phải**; tách lá **sao chép** separator lên cha nhưng giữ mục dữ liệu ở lá. Các lá nối tiếp nhau giúp truy vấn khoảng bắt đầu bằng một lần tìm kiếm rồi quét tuần tự, trong khi các nút trong với fan-out lớn giữ cho cây có chiều cao thấp.
