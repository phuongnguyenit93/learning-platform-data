# Khóa phân cách, sao chép khóa và liên kết giữa các lá

Một **B+ tree** (*B-plus tree*) không chỉ là cây tìm kiếm có nhiều khóa trong mỗi nút. Điểm làm nó đặc biệt hữu ích cho chỉ mục dữ liệu là sự phối hợp giữa ba cơ chế:

1. **Khóa phân cách** (*separator keys*) trong các nút trong giúp chọn một cây con mà không phải đi thử mọi nhánh.
2. **Sao chép khóa phân cách khi tách lá** (*copy-up*) giúp tăng số nhánh định tuyến mà vẫn giữ nguyên mục dữ liệu ở tầng lá.
3. **Liên kết giữa các lá** (*leaf links*) giúp duyệt các mục theo thứ tự, đặc biệt khi tìm một khoảng khóa.

Ba cơ chế có liên hệ chặt chẽ. Nếu khóa phân cách được đặt sai, tìm kiếm có thể đi nhầm lá. Nếu tách lá mà bỏ khóa dữ liệu đã sao chép lên cha, bản ghi sẽ biến mất khỏi tầng lá. Nếu quên nối lá mới vào chuỗi liên kết, tìm chính xác từng khóa vẫn có thể đúng nhưng truy vấn khoảng lại bỏ sót dữ liệu.

Bài này sử dụng một **quy ước B+ tree cụ thể**: khóa phân cách ở nút trong bằng **khóa nhỏ nhất của cây con ngay bên phải**; các khóa dữ liệu là **duy nhất**, còn mục dữ liệu luôn nằm ở **lá**. Ta sẽ theo dõi các bất biến, phân biệt tách lá với tách nút trong, xử lý cập nhật/xóa, phân tích chi phí và xây dựng ví dụ Java cho thao tác thêm, tìm và quét khoảng.

## 1. Ba lớp thông tin trong một B+ tree

Xét một chỉ mục lưu các cặp `(mã khách hàng, thông tin)`:

```text
                              NÚT TRONG
                              [30 | 50 | 70]
                             /     |    |     \
                            /      |    |      \
NÚT LÁ       [10:A | 20:B] [30:C | 40:D] [50:E | 60:F] [70:G | 80:H]
                  |              |              |              |
                  +---- next --->+---- next --->+---- next ---> null
```

**Nút trong** chứa separator `30`, `50`, `70` và bốn con trỏ. **Nút lá** chứa những mục dữ liệu thực sự: `10:A`, `20:B`, `30:C`, v.v. Giá trị khóa `30` tồn tại ở **hai vị trí với hai vai trò khác nhau**:

- Ở nút trong: `30` là **ranh giới định tuyến**.
- Ở lá thứ hai: `30:C` là **mục dữ liệu** cần truy xuất.

Việc lặp một giá trị khóa ở hai tầng **không có nghĩa có hai bản ghi**. Khi đếm `n` mục dữ liệu, ta đếm các mục ở lá, không cộng thêm các bản sao khóa phân cách ở nút trong.

| Thành phần | Dữ liệu giữ bên trong | Vai trò |
| --- | --- | --- |
| Khóa của nút trong | Separator, ví dụ `30` | Chọn đúng cây con theo khoảng |
| Con trỏ nút trong | Trang/nút con `P0..Pk` | Dẫn tới tầng tiếp theo |
| Khóa và mục của lá | `30:C` hoặc `30 → record_id` | Cung cấp kết quả của phép tìm kiếm |
| Liên kết `next` giữa lá | Tham chiếu lá kế tiếp | Duyệt tăng dần mà không quay lại gốc |
| Liên kết `prev` (nếu có) | Tham chiếu lá trước | Duyệt giảm dần và hỗ trợ một số cập nhật |

Trong chỉ mục thực tế, lá có thể giữ **toàn bộ bản ghi** hoặc chỉ **vị trí/định danh bản ghi** (`RID`). “Dữ liệu ở lá” nghĩa là **mục dữ liệu của chỉ mục** nằm tại lá, không bắt buộc toàn bộ hàng dữ liệu nghiệp vụ phải nằm cùng trang lá.

## 2. Bất biến khóa phân cách: mỗi khóa tạo thêm một khoảng

Giả sử một nút trong chứa `k` separator phân biệt theo thứ tự:

\[
S_0 < S_1 < \cdots < S_{k-1},
\]

và có đúng `k+1` con:

\[
P_0,\ P_1,\ \ldots,\ P_k.
\]

Ta chọn quy ước **separator là khóa nhỏ nhất của cây con ngay bên phải**:

\[
\boxed{S_i=\minKey(P_{i+1})},\qquad 0\le i<k.
\]

Ở đây `minKey(P)` là **khóa dữ liệu nhỏ nhất nằm trong các lá** thuộc cây con `P`. Điều kiện này mô tả giá trị separator **chính xác**, không chỉ một cận xấp xỉ. Với một cây hợp lệ và không rỗng, mỗi cây con đều có ít nhất một mục để xác định `minKey`.

Sơ đồ định tuyến:

```text
                              [30 | 50 | 70]
                             /     |    |     \
                            P0     P1   P2     P3

P0: x < 30
P1: 30 <= x < 50
P2: 50 <= x < 70
P3: 70 <= x
```

| Nhánh | Khoảng khóa theo quy ước của bài |
| --- | --- |
| `P0` | `x < S0` |
| `Pi` với `1 <= i < k` | `S{i-1} <= x < Si` |
| `Pk` | `x >= S{k-1}` |

Vì separator là **khóa nhỏ nhất của nhánh phải**, dấu **bằng thuộc nhánh phải**. Nếu tìm khóa `50` tại nút `[30|50|70]`, ta phải chọn `P2`, **không** chọn `P1` và **không** dừng tìm ngay ở nút trong.

### Thuật toán `upper_bound` để chọn nhánh

Với dãy separator đã sắp, tìm vị trí đầu tiên có giá trị **lớn hơn hẳn** khóa `x`:

\[
i=\min\{j:S_j>x\}.
\]

Nếu không có separator nào lớn hơn `x`, dùng `i=k`. Ký hiệu thuật toán là `upper_bound(x)`.

```text
separators = [30, 50, 70]

x =  9  -> i = 0 -> P0
x = 30  -> i = 1 -> P1
x = 45  -> i = 1 -> P1
x = 50  -> i = 2 -> P2
x = 69  -> i = 2 -> P2
x = 70  -> i = 3 -> P3
x = 99  -> i = 3 -> P3
```

Mã giả:

```text
upperBound(separators, x):
    lo = 0
    hi = separators.length
    while lo < hi:
        mid = lo + (hi - lo) // 2
        if separators[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo
```

Chỉ số trả về có thể bằng `k`: `children[k]` là nhánh ngoài cùng bên phải và **hợp lệ với nút trong**, trong khi `separators[k]` là truy cập ngoài biên. Cần phân biệt **`k` separator** với **`k+1` con trỏ con**.

### `lower_bound` dùng tại lá

Đến lá, ta tìm vị trí đầu tiên có **khóa không nhỏ hơn** `x`:

\[
j=\min\{r:\text{leaf.keys}[r]\ge x\}.
\]

Đó là `lower_bound(x)`. Nếu `j < leaf.size` và `leaf.keys[j] == x` thì tìm thấy mục dữ liệu; nếu không, khóa vắng mặt. Như vậy, trong quy ước này:

- **Nút trong:** `upper_bound` để chọn **con**.
- **Nút lá:** `lower_bound` để tìm **mục dữ liệu hoặc vị trí chèn**.

Hai phép toán khác nhau ở cách xử lý **giá trị bằng separator**; nhầm lẫn chúng là lỗi phổ biến khi cài đặt B+ tree.

## 3. Vì sao separator có thể lặp lại giá trị khóa ở lá?

Trong B-tree cổ điển, một khóa đẩy lên cha khi tách có thể được **chuyển hẳn khỏi nút con** và trở thành khóa của nút trong. Với B+ tree đang xét, **toàn bộ mục dữ liệu phải ở lá**, nên separator chỉ là **bản sao của giá trị khóa**, không phải di chuyển mục dữ liệu lên trên.

```text
                           [30]
                          /    \
                        /        \
                    [10,20] -> [30,40]

Giá trị khóa 30:
  tại nút trong:  separator = 30
  tại lá phải:    mục dữ liệu có khóa 30

Tổng số mục dữ liệu ở lá: 4, không phải 5.
```

Điều này dẫn đến hai yêu cầu:

1. Tìm thấy separator bằng khóa cần tra **chưa hoàn tất phép tìm**; phải xuống lá.
2. Nếu separator ở tầng trong thay đổi do tách/gộp, các mục dữ liệu ở lá **không được tự động mất hoặc tạo thêm**.

Separator có thể được **sao chép** từ giá trị nhỏ nhất ở lá hoặc một cây con, nhưng bản thân separator vẫn phải là một phần của cấu trúc định tuyến đúng quy ước.

### “Sao chép” không có nghĩa sao chép bản ghi lớn

Nếu lá chứa `(customer_id, record_id)`, khi tách ta thường chỉ gửi lên cha **giá trị separator** (hoặc một biểu diễn rút gọn hợp lệ của nó), không nhân đôi bản ghi khách hàng. Điều này giúp nút trong dành phần lớn dung lượng cho **khóa và con trỏ**, tăng số nhánh có thể chọn trong một lần đọc trang.

Tùy cơ sở dữ liệu, separator có thể được nén tiền tố hay rút gọn để định tuyến. Khi dùng separator rút gọn, bất biến `separator=minKey(right)` có thể được thay bằng quy tắc cận phù hợp; bài này **không dùng** kiểu rút gọn đó để giữ lập luận rõ ràng.

## 4. Tách lá: **copy-up** khóa đầu của lá phải

Giả sử một lá được phép chứa tối đa **3 mục dữ liệu**. Khi nó đang có `[10:A, 20:B, 30:C]` và chèn thêm `40:D`, danh sách tạm có 4 mục:

```text
Trước chèn:
    L = [10:A | 20:B | 30:C]          (đầy)

Sau khi thêm 40 theo thứ tự:
    L = [10:A | 20:B | 30:C | 40:D]   (tràn tạm)

Chia thành 2 lá:
    L = [10:A | 20:B]
    R = [30:C | 40:D]

Separator sao chép lên cha:
    separator = minKey(R) = 30
```

Nếu `L` đang là gốc, tạo nút trong mới:

```text
                       [30]                   <- separator
                      /    \
         [10:A | 20:B] -> [30:C | 40:D]       <- các mục vẫn ở lá
```

**Điều không được làm:** chuyển mục `30:C` từ lá phải lên nút trong. Cách đó sẽ vi phạm hợp đồng **mọi mục dữ liệu nằm ở tầng lá**, làm tìm kiếm hoặc quét khoảng có thể không thấy `30:C`.

Mã giả cốt lõi:

```text
splitLeaf(L):
    tạo lá mới R
    chia dãy các mục đã sắp của L thành hai phần còn hợp lệ
    chuyển các mục thuộc nửa phải sang R
    R.next = L.next
    nếu R.next != null và dùng liên kết prev:
        R.next.prev = R
    R.prev = L            # nếu dùng liên kết prev
    L.next = R
    return (separator = R.keys[0], rightNode = R)
```

Separator được trả về cho cha để cha chèn nó vào dãy phân cách, đồng thời thêm một con trỏ tới `R` ngay sau con trỏ tới `L`.

### Chứng minh không mất hoặc nhân đôi mục dữ liệu

Gọi `E` là tập mục có trong lá trước tách cộng mục mới. Việc chia chỉ **phân hoạch** các mục:

\[
E = E_L\,\dot\cup\,E_R.
\]

Hai tập mục trái/phải không trùng nhau nếu các khóa duy nhất. Khóa separator tại cha **không được đếm là mục dữ liệu**. Vì vậy sau tách:

\[
\text{recordCount}_{\text{mới}}
=\text{recordCount}_{\text{cũ}}+1
\]

khi chèn một khóa mới; việc **tách** tự nó không tăng thêm bản ghi nào.

## 5. Tách nút trong: **push-up** khóa định tuyến

Một nút trong giữ separator và các con, không giữ mục dữ liệu. Khi nó vượt số separator tối đa, thuật toán chia các separator cùng các con thành hai nút trong. Một separator sẽ được **đẩy lên cha** (*push-up/promote*) và có thể **không còn ở hai nút trong con**.

Ví dụ nút trong có tối đa 3 separator, nhưng tạm chứa 4:

```text
Trước khi tách:
                   [20 | 40 | 60 | 80]
                  /    |    |    |     \
                 P0   P1   P2   P3     P4

Tách:
  separator 60 được đẩy lên cha.

                         [60]
                        /    \
                   [20 | 40]  [80]
                   /   |   \   /  \
                  P0   P1  P2 P3  P4
```

Lưu ý:

- Nút trong trái có **2 separator / 3 con**.
- Nút trong phải có **1 separator / 2 con**.
- Giá trị `60` giờ là separator của cha, không phải khóa dữ liệu bị mất.
- `minKey(P3)=60` theo bất biến của nút trước tách; do đó separator `60` tại cha bằng khóa nhỏ nhất của cây con phải mới.
- Mọi **mục dữ liệu ở tầng lá** phía dưới `P0..P4` vẫn giữ nguyên.

### Tại sao phép chia khác tách lá?

| Vấn đề | Tách **lá** | Tách **nút trong** |
| --- | --- | --- |
| Dữ liệu được chia | Các mục khóa–giá trị | Các separator và con trỏ con |
| Khóa báo lên cha | **Sao chép** khóa nhỏ nhất của lá phải | **Đẩy** một separator của nút trong lên |
| Khóa báo lên còn ở tầng vừa chia? | **Có**: mục dữ liệu còn ở lá phải | **Không nhất thiết**: separator có thể bị loại khỏi hai nút trong con |
| Việc xử lý con trỏ con | Lá không có con cây | Phải chia đủ số con theo từng nhóm |
| Việc xử lý `next/prev` | Phải nối lá mới vào chuỗi lá | Không tạo một liên kết lá mới chỉ vì tách nút trong |

Điểm chung là mọi nút trong sau tách vẫn phải có **`k+1` con cho `k` separator**. Không được trộn quy tắc `copy-up` của lá với `push-up` của nút trong, hoặc giữ nguyên các con trỏ ở nút trái sau khi chia khóa.

## 6. Liên kết lá: một đường đi có thứ tự độc lập với tầng trong

Các lá B+ tree được sắp theo thứ tự khóa và thường có một liên kết **`next`**:

```text
                Các nút trong (phục vụ tìm kiếm)
                          [30 | 50 | 70]
                         /     |    |     \
                        v      v    v      v

Lá 1             Lá 2            Lá 3             Lá 4
[10,20] --next-> [30,40] --next-> [50,60] --next-> [70,80] --> null
```

Đối với tìm chính xác, có thể đi theo cây từ gốc đến đúng lá. Đối với truy vấn phạm vi, sau khi tìm được lá đầu, **theo `next`** là cách duyệt đến những mục kế tiếp mà không phải đi ngược lên các nút trong để tìm lá kế.

Một số hệ thống dùng liên kết đôi:

```text
null <-- [10,20] <--> [30,40] <--> [50,60] <--> [70,80] --> null
          L0             L1             L2             L3
```

Với cấu trúc liên kết đôi, các bất biến tối thiểu là:

\[
L.next=R\quad\Longrightarrow\quad R.prev=L
\]

và

\[
\maxKey(L)<\minKey(R)
\]

trong mô hình khóa duy nhất, với hai lá kề nhau không rỗng. Không được tồn tại vòng lặp `next` hoặc một lá đang thuộc cây nhưng bị bỏ qua trong chuỗi.

**Không nhầm liên kết lá với liên kết con.** `children[i]` của nút trong dẫn xuống một khoảng khóa; `leaf.next` dẫn **ngang** sang lá kế tiếp trong thứ tự khóa. Hai loại con trỏ phục vụ những thao tác khác nhau.

## 7. Tách lá phải giữ nguyên chuỗi liên kết

Giả sử trước tách có các lá:

```text
    A = [10,20] -> L = [30,40,50,60] -> B = [70,80] -> null
```

Tách `L` thành:

```text
    L = [30,40]
    R = [50,60]
```

Ta phải nối:

```text
    A -> L -> R -> B -> null
```

Các phép gán với liên kết đơn:

```text
R.next = L.next    # lưu lại liên kết tới B
L.next = R         # chèn R ngay sau L
```

Nếu là liên kết đôi:

```text
R.next = L.next
R.prev = L
if R.next != null:
    R.next.prev = R
L.next = R
```

### Một lỗi nguy hiểm

Nếu thực hiện `L.next = R` trước rồi mới viết `R.next = L.next`, ta tạo:

```text
L.next = R
R.next = R          <- vòng lặp tự trỏ
```

Liên kết tới lá `B` bị mất và vòng quét có thể chạy vô hạn. Vì vậy phải lưu `L.next` **trước khi** thay thế bằng `R`.

Nếu cấu trúc đang dùng liên kết đôi, quên cập nhật `B.prev` cũng khiến đường đi ngược từ `B` không nhất quán với đường đi xuôi từ `L`.

## 8. Truy vấn khoảng: một lần tìm điểm đầu, rồi quét lá

Với hai cận `a` và `b`, truy vấn khoảng đóng `[a,b]` cần trả các mục thỏa:

\[
a\le key\le b.
\]

Thuật toán:

1. Nếu `a>b`, kết quả rỗng.
2. Từ gốc, dùng `upper_bound(a)` ở từng nút trong để tìm **lá có thể chứa `a`**.
3. Trong lá đó, dùng `lower_bound(a)` để tìm vị trí mục đầu tiên không nhỏ hơn `a`.
4. Đọc mục từ vị trí đó cho tới hết lá hoặc gặp khóa `>b`.
5. Nếu cần, chuyển sang `leaf.next` và tiếp tục từ đầu lá mới.
6. Dừng khi vượt `b` hoặc `next=null`.

```text
Các lá:
[10,20] -> [30,40] -> [50,60] -> [70,80] -> null

Truy vấn [25,65]:
  lower_bound(25) tại lá [10,20]: hết lá
  next -> [30,40]: lấy 30,40
  next -> [50,60]: lấy 50,60
  next -> [70,80]: gặp 70 > 65, dừng

Kết quả: [30, 40, 50, 60]
```

Khi một cận nằm **trong khoảng trống giữa hai lá**, như `a=25`, thuật toán vẫn đúng: có thể bắt đầu ở lá kết thúc trước 25 rồi chuyển một lần sang lá kế tiếp. Không nên tự kết luận không có kết quả chỉ vì lá đầu tiên không chứa khóa `a`.

### Tại sao không tìm từ gốc cho từng mục?

Nếu có `r` mục trong khoảng, cách tìm lại từ gốc cho mỗi khóa có thể gây `r` lần đi qua cây. Liên kết lá cho phép đọc một chuỗi trang theo thứ tự, thường có lợi về truy cập trang và tính cục bộ I/O. Điều đó đặc biệt quan trọng cho thao tác **liệt kê danh sách, lấy dữ liệu theo tháng, phân trang theo khóa** và truy vấn có điều kiện `BETWEEN`.

Việc liên kết lá giúp **đi tiếp** từ một lá đã biết; nó không thay thế bước tìm điểm bắt đầu của khoảng. Với một khoảng nằm ở cuối dữ liệu, bắt đầu từ lá trái nhất vẫn có thể phải quét rất nhiều mục không liên quan.

## 9. Khi chèn hoặc xóa làm khóa phân cách thay đổi

Với quy ước chính xác `S_i=minKey(P_{i+1})`, separator phải phản ánh **giá trị nhỏ nhất hiện có trong cây con phải**. Do đó sau các thao tác cập nhật, cần kiểm tra hai loại bất biến:

1. **Các cây con còn được định tuyến đúng khoảng hay không?**
2. **Giá trị separator còn bằng đúng min của cây con phải không?**

### 9.1. Chèn một khóa mới vào lá

Nếu một khóa mới nằm trong khoảng của một lá và không làm tràn, ta chỉ chèn theo thứ tự vào lá. Với cách định tuyến `upper_bound` và khóa duy nhất, khóa nhỏ nhất **của một cây con không phải nhánh trái đầu tiên** thường không bị giảm bởi phép chèn đơn lẻ đi đúng đường theo separator hiện tại: các khóa nhỏ hơn separator của nó đã được định tuyến sang nhánh trái.

Tuy nhiên, khi **tách lá**, cây xuất hiện một con mới và cần separator mới bằng `minKey` của **lá phải vừa tạo**. Nếu việc tách tiếp tục làm nút trong tràn, phải tách nút trong và đẩy khóa phân cách lên tầng cao hơn.

Khi dùng một cách định nghĩa separator khác hoặc cho phép khóa trùng, quy tắc cập nhật có thể khác. Không nên coi khả năng giữ nguyên separator sau một lần chèn không tràn là định luật cho mọi loại B+ tree.

### 9.2. Xóa khóa nhỏ nhất khỏi một lá còn đủ mục

Xét cây đơn giản:

```text
                          [30 | 50]
                         /    |     \
                  [10,20,25] [30,40,45] [50,60]
```

Giả sử lá chứa tối đa ba mục và không phải gốc cần ít nhất hai mục. Xóa `30` ở lá giữa sẽ để lại `[40,45]`, **vẫn hợp lệ về mức lấp đầy**.

Nhưng separator cũ `30` không còn bằng `minKey` của cây con giữa. Phải cập nhật:

```text
Trước:               [30 | 50]
                    /    |     \
              [10,20,25] [30,40,45] [50,60]

Xóa 30, sửa separator:
                     [40 | 50]
                    /    |     \
              [10,20,25] [40,45] [50,60]
```

Nếu **không cập nhật** và giữ separator `30`, một số phép tìm trong hình vẽ này vẫn có thể tình cờ đi đúng hướng. Tuy nhiên, bất biến **separator bằng khóa nhỏ nhất của con phải** đã bị vi phạm, các thuật toán sửa nút hoặc kiểm chứng dựa trên quy ước đó sẽ không còn đáng tin cậy. Một số biến thể dùng *fence keys* cho phép cận không khớp hoàn toàn với khóa nhỏ nhất, nhưng **đó là một hợp đồng khác**, không phải mô hình của bài.

### 9.3. Khi mượn hoặc gộp lá

Nếu xóa làm một lá còn ít mục hơn ngưỡng cho phép, thuật toán có thể **mượn từ anh em** hoặc **gộp hai lá**.

- **Mượn từ trái:** lá nhận có thể nhận khóa lớn nhất từ lá trái; **khóa nhỏ nhất của lá nhận** có thể đổi, nên separator liên quan phải cập nhật.
- **Mượn từ phải:** lá nhận có thể nhận khóa nhỏ nhất của lá phải; **khóa nhỏ nhất mới của lá phải** thay đổi, nên separator tương ứng phải cập nhật.
- **Gộp lá:** mục của lá bị gộp phải chuyển sang lá còn lại theo thứ tự, cha **bỏ một con và một separator** thích hợp, và chuỗi `next/prev` phải **bỏ qua lá bị xóa**.

Ví dụ với mỗi lá cần ít nhất hai mục:

```text
Trước:
                        [30 | 50]
                       /    |     \
                 [10,20] [30,40] [50,60]
                    |       |       |
                    +------>+------>+----> null

Xóa 30: lá giữa còn [40], dưới ngưỡng 2.
Hai anh em đều chỉ có 2 mục, không thể cho mượn.

Gộp lá giữa vào lá trái:
                        [50]
                       /    \
                [10,20,40] [50,60]
                      |       |
                      +------>+----> null
```

Separator `30` mất vì nhánh thứ hai cũ đã bị loại; separator `50` còn để định tuyến đến lá phải mới. Không phải cứ xóa `30` là thay separator bằng `40` rồi kết thúc: trong tình huống này còn phải **sửa thiếu mục và liên kết lá**.

### 9.4. Min của một cây con có thể làm đổi separator ở tổ tiên

Một nút trong chỉ lưu separator cho các con `P1..Pk`, **không lưu riêng min của con `P0`**. Nếu khóa nhỏ nhất trong **con đầu tiên** thay đổi, có thể không có separator tại nút cha đó cần sửa. Nhưng nếu cả **cây con hiện tại** là một nhánh bên phải của **tổ tiên**, thì một separator của tổ tiên có thể cần thay đổi.

Vì vậy, cập nhật min không chỉ được hiểu là “sửa một khóa ở nút cha trực tiếp”. Một cài đặt có thể:

- Lan truyền thông tin `minKey` mới lên đường tổ tiên khi cần.
- Tính lại separator của các nhánh bị ảnh hưởng sau tách/mượn/gộp.
- Duy trì thông tin min theo nút để tránh duyệt lặp lại các cây con lớn.

Mã giả kiểm tra cục bộ, **chỉ dùng sau khi các con đã hợp lệ và không rỗng**:

```text
refreshSeparators(internal):
    for i = 0 .. internal.children.count - 2:
        internal.keys[i] = minKey(internal.children[i + 1])
```

Đây là cách diễn đạt bất biến, **không nhất thiết là thuật toán cập nhật hiệu quả nhất**. Nếu `minKey(child)` phải đi xuống nhiều tầng mỗi lần gọi, tính lại tất cả separator sau mọi thao tác có thể tăng chi phí. Một triển khai thực tế nên chỉ cập nhật những đường/nút bị ảnh hưởng và áp dụng quy tắc mức lấp đầy của biến thể đang dùng.

## 10. Mã Java tự chứa: separator, tách lá và hai chiều liên kết

Chương trình sau mô phỏng một B+ tree với những điều kiện rõ ràng:

- Khóa là số nguyên `int` **không trùng**; thêm lại khóa cũ chỉ **cập nhật giá trị**.
- Giá trị là `String` **không `null`**, để `get` trả `null` khi không có khóa.
- Mỗi lá có tối đa **3 mục**, mỗi nút trong có tối đa **3 separator**.
- Nút trong dùng `S_i=minKey(P_{i+1})` và định tuyến bằng `upper_bound`.
- Chèn có thể tách **lá**, tách **nút trong**, tạo gốc mới; lá có cả `next` và `prev`.
- Ví dụ triển khai **`put`, `get`, `range` và in chuỗi lá**, chưa triển khai xóa.

Mảng `keys` và `children` được biểu diễn bằng `ArrayList` cho đơn giản. Trong một B+ tree trên đĩa, mỗi nút thường là một trang và các liên kết tới con/lá có thể là mã trang thay vì tham chiếu đối tượng Java.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BPlusSeparatorLinksDemo {
    static final int MAX_KEYS = 3;

    static final class Node {
        final boolean leaf;
        final List<Integer> keys = new ArrayList<>();
        final List<String> values = new ArrayList<>();
        final List<Node> children = new ArrayList<>();
        Node next;
        Node prev;

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
        private int size;

        // Chi so dau tien keys[i] >= x (tai la).
        private static int lowerBound(List<Integer> keys, int x) {
            int lo = 0, hi = keys.size();
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (keys.get(mid) < x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        // Chi so dau tien separators[i] > x (tai nut trong).
        private static int upperBound(List<Integer> separators, int x) {
            int lo = 0, hi = separators.size();
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (separators.get(mid) <= x) {
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
                node = node.children.get(upperBound(node.keys, key));
            }
            return node;
        }

        String get(int key) {
            Node leaf = findLeaf(key);
            if (leaf == null) {
                return null;
            }
            int i = lowerBound(leaf.keys, key);
            if (i < leaf.keys.size() && leaf.keys.get(i) == key) {
                return leaf.values.get(i);
            }
            return null;
        }

        // True: khoa moi; false: cap nhat gia tri cua khoa cu.
        boolean put(int key, String value) {
            Objects.requireNonNull(value, "value");

            if (root == null) {
                root = new Node(true);
                root.keys.add(key);
                root.values.add(value);
                size = 1;
                return true;
            }

            boolean isNew = get(key) == null;
            Split split = insert(root, key, value);
            if (split != null) {
                Node newRoot = new Node(false);
                newRoot.keys.add(split.separator);
                newRoot.children.add(root);
                newRoot.children.add(split.right);
                root = newRoot;
            }
            if (isNew) {
                size++;
            }
            return isNew;
        }

        // Tra ve thong tin nut phai neu nut hien tai bi tach.
        private Split insert(Node node, int key, String value) {
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

                // 4 muc tam thoi: chia 2 trai va 2 phai.
                int leftCount = (node.keys.size() + 1) / 2;
                Node right = new Node(true);
                right.keys.addAll(
                    node.keys.subList(leftCount, node.keys.size()));
                right.values.addAll(
                    node.values.subList(leftCount, node.values.size()));
                node.keys.subList(leftCount, node.keys.size()).clear();
                node.values.subList(leftCount, node.values.size()).clear();

                // Noi la moi vao giua node va la next cu.
                right.next = node.next;
                right.prev = node;
                if (right.next != null) {
                    right.next.prev = right;
                }
                node.next = right;

                // COPY-UP: muc voi khoa separator van o la phai.
                return new Split(right.keys.get(0), right);
            }

            int index = upperBound(node.keys, key);
            Split split = insert(node.children.get(index), key, value);
            if (split == null) {
                return null;
            }

            node.keys.add(index, split.separator);
            node.children.add(index + 1, split.right);
            if (node.keys.size() <= MAX_KEYS) {
                return null;
            }

            // 4 separator, 5 con: tach nut trong.
            int mid = node.keys.size() / 2;
            int promoted = node.keys.get(mid);
            Node right = new Node(false);
            right.keys.addAll(
                node.keys.subList(mid + 1, node.keys.size()));
            right.children.addAll(
                node.children.subList(mid + 1, node.children.size()));

            node.keys.subList(mid, node.keys.size()).clear();
            node.children.subList(mid + 1, node.children.size()).clear();

            // PUSH-UP: separator o giua len cha, khong giu
            // separator do trong hai nut trong con.
            return new Split(promoted, right);
        }

        List<String> range(int from, int to) {
            List<String> result = new ArrayList<>();
            if (from > to) {
                return result;
            }

            Node leaf = findLeaf(from);
            if (leaf == null) {
                return result;
            }
            int index = lowerBound(leaf.keys, from);
            while (leaf != null) {
                while (index < leaf.keys.size()) {
                    int key = leaf.keys.get(index);
                    if (key > to) {
                        return result;
                    }
                    result.add(key + ":" + leaf.values.get(index));
                    index++;
                }
                leaf = leaf.next;
                index = 0;
            }
            return result;
        }

        // In chuoi la va kiem tra next/prev doi xung.
        String leafChain() {
            if (root == null) {
                return "(empty)";
            }
            Node node = root;
            while (!node.leaf) {
                node = node.children.get(0);
            }

            StringBuilder out = new StringBuilder();
            Node previous = null;
            while (node != null) {
                if (node.prev != previous) {
                    throw new IllegalStateException("Broken prev link");
                }
                if (out.length() > 0) {
                    out.append(" <-> ");
                }
                out.append(node.keys);
                previous = node;
                node = node.next;
            }
            return out.toString();
        }

        String rootSeparators() {
            if (root == null) {
                return "(empty)";
            }
            return root.keys.toString();
        }

        int size() {
            return size;
        }
    }

    public static void main(String[] args) {
        BPlusTree tree = new BPlusTree();
        for (int key : new int[] {
                10, 20, 30, 40, 50, 60, 70, 80, 90, 100}) {
            tree.put(key, "V" + key);
        }

        System.out.println("Root separators: "
            + tree.rootSeparators());
        System.out.println("Leaf chain: " + tree.leafChain());
        System.out.println("Get 70: " + tree.get(70));
        System.out.println("Get 35: " + tree.get(35));
        System.out.println("Range [25,85]: "
            + tree.range(25, 85));

        System.out.println("Insert duplicate 50: "
            + tree.put(50, "Updated"));
        System.out.println("Range [40,60]: "
            + tree.range(40, 60));
        System.out.println("Size: " + tree.size());
    }
}
```

Kết quả dự kiến:

```text
Root separators: [70]
Leaf chain: [10, 20] <-> [30, 40] <-> [50, 60] <-> [70, 80] <-> [90, 100]
Get 70: V70
Get 35: null
Range [25,85]: [30:V30, 40:V40, 50:V50, 60:V60, 70:V70, 80:V80]
Insert duplicate 50: false
Range [40,60]: [40:V40, 50:Updated, 60:V60]
Size: 10
```

### Truy vết tại thời điểm gốc bị tách

Sau khi chèn tới `80`, gốc là nút trong `[30,50,70]` với bốn lá. Chèn `90` vào lá cuối nhưng chưa làm tràn. Khi chèn `100`:

1. Lá `[70,80,90]` tạm thành `[70,80,90,100]` rồi tách thành `[70,80]` và `[90,100]`.
2. **Sao chép `90` lên nút trong gốc**, làm nó tạm chứa `[30,50,70,90]`.
3. Nút trong gốc tràn; **đẩy `70` lên gốc mới**.
4. Nút trong trái giữ `[30,50]` và ba lá đầu; nút trong phải giữ `[90]` và hai lá cuối.
5. Liên kết giữa **năm lá** vẫn giữ thứ tự `[10,20] <-> [30,40] <-> [50,60] <-> [70,80] <-> [90,100]`.

Hình dạng cây:

```text
                                   [70]               gốc mới
                                 /      \
                            [30 | 50]   [90]           nút trong
                           /   |    \    /   \
                         L0   L1    L2  L3   L4

L0=[10,20] <-> L1=[30,40] <-> L2=[50,60] <->
L3=[70,80] <-> L4=[90,100]
```

Hai điều đáng kiểm tra khi đọc mã là **separator `70` vẫn có mục dữ liệu `70:V70` ở lá**, và **năm lá vẫn tạo thành một chuỗi** dù cấu trúc các nút trong đã thay đổi.

### Giới hạn của chương trình

Ví dụ cố ý dùng `MAX_KEYS=3`, dữ liệu nhỏ và thao tác chèn/tìm/quét khoảng để minh họa. Nó **chưa có phép xóa hoặc tái cân bằng sau xóa**, cũng chưa có lưu trữ bền vững, tranh chấp truy cập đồng thời, cơ chế rollback hay bảo đảm khi cấp phát bộ nhớ thất bại. Phần cập nhật separator lúc xóa được mô tả ở Mục 9, **không được coi là đã triển khai trong mã Java**.

## 11. Kiểm tra bất biến sau cập nhật

Việc xem `get` trả đúng một số khóa **chưa đủ** để chứng minh cây đúng. Một bộ kiểm chứng B+ tree có thể áp dụng các bước:

| Kiểm tra | Điều kiện cần đạt theo mô hình bài |
| --- | --- |
| Khóa trong một lá | Tăng nghiêm ngặt, không trùng |
| Khóa trong một nút trong | Separator tăng nghiêm ngặt |
| Số con ở nút trong | `childCount = separatorCount + 1` |
| Giá trị separator | `keys[i] = minKey(children[i+1])` |
| Phạm vi cây con | Mọi khóa trong con thuộc khoảng tương ứng |
| Độ sâu lá | Mọi lá cùng độ sâu |
| Chuỗi `next` | Thăm toàn bộ lá đúng một lần, theo thứ tự tăng |
| Chuỗi `prev` nếu có | Mỗi liên kết ngược khớp liên kết xuôi |
| Mục dữ liệu | Chỉ xuất hiện ở lá, không được đếm bản sao separator |
| Đếm mục `size` | Bằng tổng số mục ở tất cả lá |

### Một cách tự kiểm tra chuỗi lá

Đối với dữ liệu nhỏ, có thể:

1. Duyệt cây từ gốc và thu thập **các lá theo thứ tự trái sang phải**.
2. Tìm lá đầu từ gốc, đi theo `next` và thu thập dãy lá thứ hai.
3. So sánh **đối tượng lá và thứ tự** của hai dãy.
4. Với từng lá liền nhau, so sánh `maxKey(left) < minKey(right)`, đồng thời xác minh `next/prev` nếu có.
5. Đếm tất cả mục lá và đối chiếu `size`.

Cách kiểm thử này sẽ phát hiện tình huống các separator và con trỏ con vẫn đúng nhưng chuỗi lá bị đứt sau khi tách/gộp.

### Một lưu ý về liên kết đôi và độ bền

Trong bộ nhớ, sửa `next` và `prev` là vài phép gán. Với chỉ mục được lưu trên đĩa hoặc được nhiều luồng cùng truy cập, việc sửa nhiều trang cần thêm **quy trình đồng bộ, thứ tự ghi, logging và khôi phục** để tránh trạng thái đọc được nửa chừng. Bài này tập trung vào bất biến cấu trúc; cách bảo đảm tính nguyên tử và an toàn đồng thời thuộc thiết kế hệ lưu trữ.

## 12. Phân tích độ phức tạp và tính cục bộ trang

Gọi:

- `n` là số **mục dữ liệu ở lá**.
- `F` là số nhánh hiệu dụng của nút trong.
- `L` là số mục lá trung bình/tối thiểu được duy trì ở mức hợp lý.
- `h` là chiều cao theo số cạnh từ gốc đến lá.
- `r` là số mục cần trả cho một truy vấn khoảng.

Ở B+ tree cân bằng và có quy tắc lấp đầy, chiều cao có bậc:

\[
h=O(\log_F n)
\]

theo mô hình fan-out được giới hạn và duy trì phù hợp. Nếu nút trong có `k` separator, tìm nhị phân để chọn nhánh tốn `O(\log(k+1))` phép so sánh; tìm trong lá có chi phí tương tự theo số mục lá.

| Thao tác | Công việc chủ yếu | Nhận xét |
| --- | --- | --- |
| Tìm một khóa | Đi theo một nhánh mỗi tầng, tìm trong lá | O(log n) theo mô hình RAM với sức chứa nút cố định |
| Chèn khóa mới | Tìm lá, thêm mục; có thể tách nhiều tầng | O(log n) khi sức chứa nút cố định |
| Tách lá | Chia mục và sửa liên kết, báo separator | O(L) theo sức chứa một lá |
| Tách nút trong | Chia separator và con, đẩy separator | O(F) theo sức chứa nút trong |
| Quét `r` mục liên tiếp | Tìm lá đầu rồi quét qua liên kết lá | O(log n + r) khi mỗi mục được xử lý O(1) |

Trong mô hình **mỗi nút tương ứng một trang**, số lần truy cập trang để tìm vị trí bắt đầu tỷ lệ với chiều cao. Để quét `r` mục, nếu các lá giữ khoảng `L` mục theo mức lấp đầy ổn định, số trang lá được thăm có bậc:

\[
O\left(\left\lceil\frac{r}{L}\right\rceil+1\right),
\]

với `+1` đại diện cho lá bắt đầu hoặc kết thúc chỉ có ít hoặc không có mục phù hợp. Như vậy chi phí tiếp cận trang cho truy vấn khoảng thường được mô tả:

\[
O\left(\log_F n + \left\lceil\frac{r}{L}\right\rceil+1\right).
\]

Những ký hiệu này **không khẳng định mỗi lần thăm nút chắc chắn là một I/O đĩa**: trang có thể nằm trong cache, hoặc sau khi tìm mục lá có thể phải truy cập vùng lưu bản ghi riêng.

### Khi trang trong và trang lá có sức chứa khác nhau

Nút trong thường lưu **separator + con trỏ trang**, nên có thể chứa nhiều nhánh. Lá lưu **mục dữ liệu** hoặc `RID` và thêm liên kết giữa lá. Vì vậy `F` và `L` không nhất thiết bằng nhau.

Ví dụ minh họa với trang 4 KiB:

- Header 128 byte, separator 16 byte, con trỏ trang 8 byte: nút trong có thể chứa tối đa `165` separator và `166` con trong mô hình đơn giản.
- Header 128 byte, liên kết lá 8 byte, khóa 16 byte và `RID` 8 byte: lá có thể chứa tối đa `165` mục theo mô hình đơn giản.
- Nếu mục lá giữ dữ liệu bản ghi 256 byte thay `RID` 8 byte, số mục tối đa giảm đáng kể.

Con số thực tế còn phụ thuộc metadata, căn chỉnh, nén khóa, kích thước giá trị và quy tắc bố cục trang. Lợi ích chính của B+ tree là **nhiều thông tin định tuyến trên một trang trong** kết hợp với **chuỗi lá hỗ trợ quét tuần tự**.

## 13. Lỗi phổ biến khi viết B+ tree

1. **Xem separator là một bản ghi.** Giá trị khóa ở nút trong là định tuyến, không phải một mục dữ liệu bổ sung.
2. **Tìm thấy khóa ở nút trong rồi dừng.** Theo mô hình bài, phải đi xuống lá để lấy giá trị hoặc `RID`.
3. **Cho khóa bằng separator đi sang trái.** Với `separator=minKey(right)`, dấu bằng thuộc **nhánh phải**.
4. **Dùng `lower_bound` thay cho `upper_bound` ở nút trong.** Có thể chọn sai nhánh đúng tại ranh giới.
5. **Nút trong có `k` separator nhưng chỉ có `k` con.** Phải có `k+1` con thực.
6. **Tách lá bằng cách đẩy hẳn khóa nhỏ nhất bên phải lên cha.** Mục dữ liệu tại lá phải sẽ bị mất; phải **sao chép separator**, không bỏ mục.
7. **Tách nút trong nhưng vẫn giữ nguyên toàn bộ con ở nút trái.** Số con và khoảng khóa sẽ sai.
8. **Nhầm `copy-up` của lá với `push-up` của nút trong.** Hai thao tác có hợp đồng giữ lại separator khác nhau.
9. **Chỉ cập nhật `L.next=R` mà quên `R.next` cũ.** Chuỗi lá có thể đứt hoặc tạo vòng lặp.
10. **Cập nhật `L.next` trước khi lưu lá tiếp theo.** Có thể làm `R.next=R` nếu lấy lại `L.next` sau đó.
11. **Dùng liên kết đôi nhưng quên cập nhật `R.next.prev`.** Chuỗi đi xuôi và ngược không còn đối xứng.
12. **Gộp hai lá nhưng quên bỏ lá bị gộp khỏi `next/prev`.** Truy vấn khoảng có thể đọc dư, lặp hoặc thiếu mục.
13. **Xóa khóa nhỏ nhất của một nhánh mà không sửa separator.** Vi phạm bất biến `separator=minKey(childRight)` nếu min đã đổi.
14. **Chỉ sửa separator của cha gần nhất.** Nếu min của cả cây con thay đổi, separator cần cập nhật có thể nằm ở tổ tiên.
15. **Xóa khiến lá thiếu mục mà chỉ sửa separator.** Cần phục hồi mức lấp đầy bằng mượn/gộp theo biến thể cây.
16. **Đếm các bản sao separator như mục dữ liệu.** `n` và `size` phải đếm những mục ở lá.
17. **Cho rằng truy vấn khoảng cần tìm lại từ gốc cho mỗi lá.** Có thể quét qua `next` sau khi định vị lá đầu.
18. **Mặc định một hệ quản trị cụ thể dùng đúng separator=minKey(right).** Một số hệ thống dùng ranh giới/fence key hoặc biểu diễn nén khác; phải tuân hợp đồng thực tế.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một nút trong B+ tree có ba separator `[30,50,70]`. Theo quy tắc `separator=minKey(right)`, nút có bao nhiêu con và tìm `50` chọn con nào?

**Đáp án:** Có bốn con `P0..P3`. Tìm `50` chọn `P2` vì khóa bằng separator thuộc nhánh phải.

**Câu 2.** Tại sao cùng giá trị `30` ở nút trong và lá không có nghĩa B+ tree chứa hai bản ghi có khóa `30`?

**Đáp án:** `30` ở nút trong chỉ là separator; mục dữ liệu `30:value` nằm ở lá. Chỉ mục dữ liệu ở lá mới được tính là bản ghi/mục.

**Câu 3.** Với quy ước separator là min của cây con phải, hàm chọn con ở nút trong nên dùng `lower_bound` hay `upper_bound`?

**Đáp án:** Dùng `upper_bound`, tìm separator đầu tiên **lớn hơn hẳn** khóa cần tìm, để xử lý đúng trường hợp bằng separator.

**Câu 4.** Tại sao khi đến lá, tìm chính xác khóa lại dùng `lower_bound`?

**Đáp án:** Vì cần tìm vị trí đầu tiên có khóa **lớn hơn hoặc bằng** khóa cần tìm, rồi kiểm tra bằng nhau để trả về mục dữ liệu.

**Câu 5.** Tách lá `[10,20,30,40]` thành `[10,20]` và `[30,40]` theo mô hình bài: separator nào lên cha và khóa đó có còn ở lá không?

**Đáp án:** Sao chép `30` lên cha. Mục dữ liệu `30` vẫn nằm ở lá phải.

**Câu 6.** Tách nút trong `[20,40,60,80]` có năm con `P0..P4` theo ví dụ: khóa nào được đẩy lên và chia các con thế nào?

**Đáp án:** Đẩy `60` lên cha. Nút trái giữ `[20,40]` với `P0,P1,P2`; nút phải giữ `[80]` với `P3,P4`.

**Câu 7.** Vì sao không thể dùng cùng một quy tắc “bỏ khóa giữa khỏi nút con” cho tách lá và tách nút trong?

**Đáp án:** Mọi mục dữ liệu phải tồn tại ở lá. Tách lá cần sao chép giá trị separator nhưng **không được bỏ mục dữ liệu** của khóa đó; tách nút trong có thể đưa separator lên cha và bỏ nó khỏi hai nút con vì nó chỉ là thông tin định tuyến.

**Câu 8.** Trước tách có `L.next=B`. Sau khi tách `L` thành `L` và `R`, phải gán `R.next` và `L.next` theo thứ tự nào?

**Đáp án:** Đặt `R.next=L.next` trước, rồi `L.next=R`. Khi dùng liên kết đôi, còn đặt `R.prev=L` và cập nhật `B.prev=R` nếu `B` tồn tại.

**Câu 9.** Điều gì có thể xảy ra nếu gán `L.next=R` rồi `R.next=L.next`?

**Đáp án:** `R.next` sẽ trỏ tới chính `R`, tạo vòng lặp và làm mất liên kết tới lá đứng sau ban đầu.

**Câu 10.** Các lá `[10,20]->[30,40]->[50,60]->[70,80]`. Truy vấn khoảng `[25,65]` trả về những khóa nào?

**Đáp án:** `[30,40,50,60]`.

**Câu 11.** Nếu `lower_bound(25)` tại lá `[10,20]` trả về vị trí hết lá, truy vấn khoảng có phải lập tức kết thúc không?

**Đáp án:** Không. Phải theo `next` sang lá kế tiếp để tiếp tục tìm những khóa `>=25`.

**Câu 12.** Một cây có separator `[30,50]` với các lá `[10,20,25]`, `[30,40,45]` và `[50,60]`. Sau khi xóa `30` khỏi lá giữa mà lá vẫn đủ mục, cần đổi separator nào?

**Đáp án:** Đổi separator thứ nhất từ `30` thành `40`, vì `40` là khóa nhỏ nhất mới của cây con ở giữa.

**Câu 13.** Nếu xóa `30` khỏi lá `[30,40]` khi mức tối thiểu là hai mục/lá và hai lá anh em đều chỉ có hai mục, có thể chỉ sửa separator rồi dừng không?

**Đáp án:** Không. Lá còn một mục, bị thiếu mức lấp đầy. Cần gộp (hoặc tái cân bằng theo quy tắc biến thể), cập nhật separator/con trỏ và nối lại chuỗi lá.

**Câu 14.** Tại sao separator bị ảnh hưởng khi thay đổi khóa nhỏ nhất của một cây con có thể nằm ở tổ tiên, không chỉ ở cha trực tiếp?

**Đáp án:** Min của con đầu tiên không có separator riêng tại nút cha đó, nhưng **min của cả cây con** có thể là separator cho nhánh phải của một tổ tiên. Thay đổi min cần được truyền tới vị trí định tuyến tương ứng.

**Câu 15.** Phần mã Java có triển khai xóa và gộp lá không?

**Đáp án:** Không. Nó triển khai thêm/cập nhật, tìm chính xác, quét khoảng và nối `next/prev` khi tách; xóa và tái cân bằng được giải thích riêng trong bài.

**Câu 16.** Trong mã Java, sau khi chèn `10,20,...,100`, separator ở gốc cuối cùng là bao nhiêu và vì sao?

**Đáp án:** `[70]`. Khi chèn `100`, lá cuối tách và báo separator `90`, khiến nút trong gốc tràn; nút trong đó được tách, đẩy separator `70` lên gốc mới.

**Câu 17.** Vì sao liên kết lá cải thiện truy vấn khoảng nhưng không làm số trang phải đọc luôn bằng một?

**Đáp án:** Liên kết lá tránh phải tìm lại từ gốc giữa các lá. Tuy nhiên, nếu kết quả trải qua nhiều trang lá, vẫn phải đọc các trang ấy và có thể phải đọc thêm bản ghi ở vùng lưu riêng.

**Câu 18.** Những điều kiện nào nên được kiểm tra sau khi tách lá để tránh lỗi truy vấn khoảng?

**Đáp án:** Các khóa trong mỗi lá tăng, không mất mục dữ liệu, separator lên cha bằng min của lá phải theo quy ước, chuỗi `next` đi qua lá mới đúng thứ tự và `prev` đối xứng nếu có.

**Điểm ghi nhớ:** Trong B+ tree, **khóa phân cách là thông tin định tuyến**, còn **mục dữ liệu ở lá**. Với quy ước `separator=minKey(cây con phải)`, khóa bằng separator phải đi **nhánh phải**. Khi tách lá, separator được **sao chép lên cha nhưng mục vẫn ở lá**; khi tách nút trong, separator được **đẩy lên tầng trên**. Liên kết giữa các lá giúp tìm một lần rồi quét cả khoảng khóa. Chèn, xóa và gộp phải cùng lúc giữ đúng **separator, cấu trúc con và chuỗi lá**.
