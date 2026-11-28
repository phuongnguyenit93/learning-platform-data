# Cây khoảng (interval tree) và phát hiện các khoảng giao nhau

## 1. Từ dữ liệu điểm đến dữ liệu khoảng

Trong môn **Cấu trúc dữ liệu**, BST giúp tìm một khóa cụ thể dựa trên thứ tự nhỏ hơn/lớn hơn. Nhưng nhiều bài toán không lưu một con số đơn lẻ: đối tượng được biểu diễn bằng **một khoảng** có đầu và cuối.

Ví dụ:

- Phòng họp được đặt từ phút thứ `540` đến phút thứ `600` trong ngày.
- Một công việc sử dụng tài nguyên trong khoảng thời gian nhất định.
- Một đoạn đường, một vùng giá trị hoặc một phần dữ liệu có phạm vi `[low,high]`.
- Một sự kiện trong trục thời gian cần kiểm tra có **xung đột** với sự kiện mới không.
- Một đặc tính trên hệ tọa độ một chiều nằm trong đoạn `[start,end]`.

Nếu một hệ thống liên tục **thêm**, **xóa** các khoảng và hỏi **có khoảng nào giao với khoảng mới không?**, duyệt tuyến tính toàn bộ `n` khoảng mỗi lần sẽ tốn `O(n)` thời gian. Khi có nhiều truy vấn và các khoảng thay đổi động, ta có thể dùng **cây khoảng (interval tree)**.

> Ý tưởng: sử dụng **BST sắp theo đầu trái** của khoảng và **tăng cường mỗi nút bằng đầu phải lớn nhất trong cây con**. Thông tin này giúp loại bỏ những cây con chắc chắn không thể có khoảng giao với truy vấn.

Trong bài này, *interval tree* được hiểu cụ thể là **cây tìm kiếm nhị phân tăng cường trường `maxHigh`**, có thể đặt trên một BST tự cân bằng như AVL hoặc Red–Black Tree. Trong tài liệu khác, “interval tree” còn có thể chỉ cấu trúc chia khoảng theo tâm (*centered interval tree*); những cách tổ chức đó khác thuật toán lưu `maxHigh` ở đây.

Bài học tập trung vào định nghĩa giao khoảng, bất biến của cây, chứng minh điều kiện cắt nhánh, thao tác chèn/xóa/xoay, ví dụ Python và chi phí thời gian–bộ nhớ.

## 2. Khoảng và quan hệ giao nhau: quy ước phải rõ

### 2.1. Khoảng đóng `[low,high]`

Trong phần chính của bài, mỗi đối tượng là một **khoảng đóng**:

\[
I=[low(I),high(I)],\qquad low(I)\le high(I).
\]

Khoảng đóng **chứa cả hai đầu mút**. Ví dụ:

- `[3,8]` chứa `3` và `8`.
- `[3,8]` và `[8,12]` **giao nhau tại đúng điểm `8`**.
- `[3,8]` và `[9,12]` **không giao**.
- Khoảng `[5,5]` là một **điểm duy nhất**, không phải khoảng rỗng.

Với hai khoảng đóng hợp lệ `A=[a,b]` và `B=[c,d]`:

\[
\boxed{A\cap B\ne\varnothing
\iff a\le d\ \text{và}\ c\le b.}
\]

Tương đương, hai khoảng **không giao nhau** khi:

\[
\boxed{b<c\quad\text{hoặc}\quad d<a.}
\]

Một điều kiện khác rất gọn là:

\[
\boxed{\max(a,c)\le\min(b,d).}
\]

Ba công thức này đều mô tả cùng quan hệ giao nhau của **khoảng đóng**.

### 2.2. Sơ đồ trên trục số

```text
A = [2, 7]        2 ├─────────┤ 7
B = [5,10]              5 ├─────────┤ 10
                  A và B giao tại [5,7]

C = [7,12]                  7 ├─────────┤ 12
                  A và C giao tại điểm 7

D = [8,11]                    8 ├─────┤ 11
                  A và D không giao: 7 < 8
```

**Đừng nhầm** “giao nhau” với “một khoảng chứa trọn khoảng khác”. Khoảng `[3,20]` giao với `[7,9]` dù chiều dài của chúng rất khác nhau. Chỉ cần **ít nhất một điểm chung**.

### 2.3. Khoảng nửa mở là bài toán liên quan nhưng khác

Trong hệ thống đặt lịch, người ta thường dùng khoảng **nửa mở** `[start,end)`:

- Bao gồm thời điểm bắt đầu.
- **Không bao gồm** thời điểm kết thúc.
- Hai lượt đặt `[9:00,10:00)` và `[10:00,11:00)` **không trùng thời gian**.

Với hai khoảng nửa mở **không rỗng** `[a,b)`, `[c,d)`, điều kiện giao là:

\[
\boxed{a<d\quad\text{và}\quad c<b.}
\]

Với khoảng nửa mở, `start=end` là **khoảng rỗng**, cần xử lý riêng. Những bất đẳng thức cắt nhánh dựa trên `maxHigh` cũng cần đổi từ `<`/`\ge` sang phiên bản phù hợp.

**Toàn bộ mã Python của bài dùng khoảng đóng với đầu mút số nguyên.** Không được lấy nguyên hàm kiểm tra giao của khoảng đóng áp vào lịch nửa mở mà không sửa điều kiện biên.

### 2.4. Bảng phân biệt nhanh

| Khoảng A | Khoảng B | Giao nếu đều đóng? | Giao nếu đều nửa mở? |
|---|---|---|---|
| `[2,5]` | `[4,7]` | Có | Có |
| `[2,5]` | `[5,7]` | Có, tại `5` | Không |
| `[2,5]` | `[6,8]` | Không | Không |
| `[2,8]` | `[3,5]` | Có | Có |
| `[5,5]` | `[5,5]` | Có, tại `5` | Không, khoảng rỗng |

Trong bảng, khi xét nửa mở, ký hiệu ở cột dữ liệu được hiểu với **cùng hai đầu mút nhưng bỏ đầu phải**, tức `[a,b)`.

## 3. Tại sao BST chỉ sắp theo `low` chưa đủ?

Nếu các khoảng được sắp theo **đầu trái `low`**, một BST có thể cho phép tìm một khoảng có đúng khóa `low=x`. Nhưng truy vấn giao với `Q=[L,R]` còn phụ thuộc **đầu phải `high`**.

Xét các khoảng:

```text
[5, 8], [8, 9], [15,23], [16,21], [17,19],
[25,30], [26,40]
```

Một khoảng bắt đầu ở `15` nhưng kéo dài đến `23` vẫn giao với truy vấn `[22,24]`, dù `15<22`.

Nếu chỉ so `L=22` với khóa `low=16` ở nút hiện tại, ta **không thể kết luận** toàn bộ cây con trái không có kết quả. Các khoảng ở đó có thể bắt đầu sớm nhưng kết thúc rất muộn.

### 3.1. Đường đi khóa không đủ để kiểm tra giao nhau

Với tìm khóa đúng, BST có thể bỏ cả phía trái nếu `x>key(u)`. Với tìm giao khoảng:

- Khoảng hiện tại không giao **không đồng nghĩa** toàn bộ cây con trái không giao.
- Khoảng hiện tại không giao **không đồng nghĩa** toàn bộ cây con phải không giao.
- Một khoảng có đầu trái nhỏ vẫn có thể kéo dài sang vùng truy vấn.

Điều còn thiếu là một **thống kê về đầu phải của các khoảng trong từng cây con**.

### 3.2. Trường tăng cường `maxHigh`

Tại mỗi nút `u` lưu một khoảng `[u.low,u.high]` và:

\[
\boxed{
maxHigh(u)=
\max\left(
u.high,\,
maxHigh(u.left),\,
maxHigh(u.right)
\right).
}
\]

Với cây rỗng, ta dùng giá trị toán học:

\[
maxHigh(\varnothing)=-\infty.
\]

**Ý nghĩa:** `maxHigh(u)` là đầu phải lớn nhất của **mọi khoảng trong cây con gốc `u`**, bao gồm khoảng tại chính `u`.

Nếu cây con `T` có:

\[
maxHigh(T)<L,
\]

thì **mọi** khoảng trong `T` đều kết thúc trước đầu trái `L` của truy vấn đóng `[L,R]`. Không một khoảng nào trong `T` có thể giao với `Q`. Vì vậy, ta có thể **bỏ qua toàn bộ cây con ấy**.

## 4. Bất biến của cây khoảng tăng cường

### 4.1. Mỗi nút cần lưu gì?

Một nút interval tree trong bài chứa:

```text
IntervalNode
┌────────────────────────────────────┐
│ low: đầu trái                      │
│ high: đầu phải                     │
│ uid: định danh duy nhất            │
│ left, right: hai cây con BST       │
│ max_high: đầu phải lớn nhất subtree│
│ height: chiều cao AVL (theo cạnh)  │
└────────────────────────────────────┘
```

Có hai nhóm bất biến:

1. **BST:** sắp nút theo khóa `(low,uid)` tăng dần. Dùng `uid` làm khóa phụ để nhiều khoảng có cùng `low` vẫn phân biệt được.
2. **Augmentation:** `max_high` phải bằng đầu phải lớn nhất của mọi khoảng trong cây con hiện tại.

Nếu dùng AVL làm cây nền, còn có:

\[
height(u)=1+\max(height(u.left),height(u.right))
\]

và:

\[
|height(u.left)-height(u.right)|\le 1.
\]

**Quan trọng:** thứ tự BST dựa trên `low` (và `uid`), còn điều kiện giao phụ thuộc cả `low` lẫn `high`. Hai vai trò này **không được đánh đồng**.

### 4.2. Vì sao cần `uid`?

Hai lượt đặt lịch có thể đều là `[9,11]`, hoặc hai khoảng có cùng đầu trái nhưng đầu phải khác:

```text
[9,11], [9,11], [9,14]
```

Chúng có thể là **ba bản ghi riêng**, có ID khác nhau. Nếu chỉ dùng `low=9` làm khóa BST, ta phải lựa chọn chính sách lưu trùng và bảo trì nó rất cẩn thận.

Bài này chọn khóa:

\[
key(u)=(u.low,u.uid)
\]

so sánh **theo thứ tự từ điển**. Mỗi lần thêm khoảng tạo một `uid` duy nhất, nên các nút có cùng `low` vẫn nằm ở những vị trí có thứ tự rõ ràng trong BST.

Lưu ý `uid` **không ảnh hưởng điều kiện giao**; nó chỉ giúp phân biệt, tìm và xóa chính xác bản ghi.

### 4.3. Cây ví dụ xuyên suốt

Xét bảy khoảng đóng:

```text
                       [16,21]
                      maxHigh=40
                     /          \
                    /            \
             [8,9]               [25,30]
           maxHigh=23            maxHigh=40
           /       \              /       \
        [5,8]     [15,23]      [17,19]   [26,40]
        max=8       max=23      max=19     max=40
```

Hình vẽ thể hiện BST theo **đầu trái**:

- Cây con trái của nút `[16,21]` có `low=5,8,15`, đều nhỏ hơn `16`.
- Cây con phải có `low=17,25,26`, đều lớn hơn `16`.
- Ở nút `[8,9]`, đầu phải lớn nhất của cây con là `23` do khoảng `[15,23]`, mặc dù đầu phải của chính nút là `9`.
- Gốc có `maxHigh=40` do khoảng `[26,40]`.

Đây là cây nhị phân cân bằng về hình dạng, dùng làm ví dụ đọc thuật toán. Một cây khoảng **không bắt buộc** có chính xác hình dạng này sau các thao tác chèn/xóa: các phép xoay có thể thay đổi vị trí nút nhưng không thay đổi tập khoảng hay tính đúng của `maxHigh`.

### 4.4. Tự tính metadata từng nút

| Khoảng tại nút | `maxHigh(left)` | `maxHigh(right)` | `maxHigh(u)` |
|---|---:|---:|---:|
| `[5,8]` | `-\infty` | `-\infty` | 8 |
| `[15,23]` | `-\infty` | `-\infty` | 23 |
| `[8,9]` | 8 | 23 | 23 |
| `[17,19]` | `-\infty` | `-\infty` | 19 |
| `[26,40]` | `-\infty` | `-\infty` | 40 |
| `[25,30]` | 19 | 40 | 40 |
| `[16,21]` | 23 | 40 | 40 |

Bảng này minh họa quy tắc cốt lõi: **metadata phải được tính từ hai cây con đã đúng, rồi mới tính nút cha**.

## 5. Truy vấn tìm **một** khoảng giao: `INTERVAL-SEARCH`

### 5.1. Thuật toán một đường đi

Đầu vào là cây có gốc `root` và khoảng truy vấn đóng `Q=[L,R]`, `L≤R`.

Tại nút `u`:

1. Nếu khoảng tại `u` giao với `Q`, **trả kết quả ngay**.
2. Nếu có cây con trái và `maxHigh(u.left)≥L`, thử đi **sang trái**.
3. Nếu không, đi **sang phải**.
4. Nếu đi tới `None`, kết luận **không có khoảng giao**.

```text
INTERVAL-SEARCH(root, [L,R]):
    u = root

    while u != None:
        if OVERLAP([u.low,u.high], [L,R]):
            return u

        if u.left != None and u.left.maxHigh >= L:
            u = u.left
        else:
            u = u.right

    return None
```

**Chú ý:** hàm chỉ cần trả **một** khoảng bất kỳ giao với truy vấn, không bảo đảm khoảng giao **sớm nhất, ngắn nhất** hay khoảng có đầu trái nhỏ nhất.

### 5.2. Truy vết `Q=[22,24]`

Xét cây ví dụ:

```text
                      [16,21] max=40
                     /                 \
             [8,9] max=23           [25,30] max=40
              /       \               /      \
           [5,8]    [15,23]       [17,19]  [26,40]
```

Từng bước:

| Bước | Nút hiện tại | Có giao `[22,24]`? | Nhìn cây trái | Quyết định |
|---|---|---|---|---|
| 1 | `[16,21]` | Không, `21<22` | `maxHigh(left)=23≥22` | Đi trái |
| 2 | `[8,9]` | Không, `9<22` | `maxHigh(left)=8<22` | Đi phải |
| 3 | `[15,23]` | **Có**, vì `15≤24` và `22≤23` | Không cần | Trả `[15,23]` |

Ta chỉ xem **ba nút**, thay vì kiểm tra tất cả bảy khoảng.

### 5.3. Truy vết truy vấn không có kết quả

Với `Q=[10,14]`:

- Tại `[16,21]`, không giao; cây trái có `maxHigh=23≥10`, đi trái.
- Tại `[8,9]`, không giao; cây trái có `maxHigh=8<10`, đi phải.
- Tại `[15,23]`, không giao vì `15>14`; không có con trái, đi phải đến `None`.
- Kết luận **không có khoảng giao** với `[10,14]`.

Với `Q=[21,21]`, khoảng `[16,21]` **giao tại đúng điểm `21`**, nên trả kết quả ngay tại gốc. Đây là hệ quả trực tiếp của **quy ước khoảng đóng**.

## 6. Vì sao việc chọn một nhánh **không bỏ sót kết quả**?

Phần chứng minh này quyết định tính đúng của thuật toán. Điều kiện `maxHigh(left)≥L` **chưa đủ** để nói chắc cây trái có một khoảng giao, nhưng vẫn đủ để chọn nhánh mà **không bỏ lỡ một kết quả có thể tồn tại ở nhánh khác**.

### 6.1. Trường hợp chọn phải

Giả sử `u` không giao với `Q=[L,R]` và cây trái rỗng hoặc:

\[
maxHigh(u.left)<L.
\]

Khi đó **mọi khoảng bên trái** đều có đầu phải nhỏ hơn `L` nên **chắc chắn không giao**.

Vì chính khoảng tại `u` cũng không giao, nếu tồn tại khoảng giao trong cây con gốc `u` thì nó chỉ có thể nằm ở **cây phải**.

Do đó, đi phải không làm mất một ứng viên hợp lệ.

### 6.2. Trường hợp chọn trái khi `maxHigh(left)≥L`

Giả sử `u` không giao và cây trái có ít nhất một khoảng `J` với:

\[
high(J)\ge L.
\]

Nhờ BST sắp theo `low`:

\[
low(J)\le low(u).
\]

Xét hai trường hợp:

**Trường hợp A — `low(u)≤R`.**

Kết hợp với `low(J)≤low(u)≤R` và `high(J)≥L`, ta có:

\[
low(J)\le R,\qquad L\le high(J).
\]

Vậy **`J` giao với `Q`**. Nghĩa là trong trường hợp này, **cây trái chắc chắn có một kết quả**, nên có thể tập trung đi trái.

**Trường hợp B — `low(u)>R`.**

Mọi khoảng trong cây phải của `u` đều có đầu trái **không nhỏ hơn `low(u)`**, nên:

\[
low(\text{mọi khoảng bên phải})\ge low(u)>R.
\]

Cây phải **không thể có khoảng giao**. Khi đó đi trái là lựa chọn duy nhất có thể dẫn tới kết quả.

Vì vậy, **khi thuật toán chọn trái và bỏ qua phải, nó không làm mất đáp án**. Tương tự, chọn phải chỉ xảy ra sau khi đã chứng minh cây trái không thể chứa đáp án.

### 6.3. Bất biến vòng lặp

Trước mỗi vòng lặp, giữ mệnh đề:

> Nếu vẫn còn một khoảng giao trong phần cây đã xét từ đầu, thì cây con gốc tại `u` hiện tại vẫn chứa **ít nhất một** khoảng giao.

Nếu `u` giao, trả đúng một kết quả. Nếu `u` không giao, lập luận hai trường hợp ở trên bảo toàn mệnh đề khi đi sang con được chọn.

Khi tới `None`, mệnh đề cho thấy **không tồn tại kết quả** trong cây ban đầu.

### 6.4. Phân biệt điều kiện loại trừ với điều kiện xác nhận

- `maxHigh(left)<L` là **chứng cứ chắc chắn để loại bỏ cây trái**.
- `maxHigh(left)≥L` **không tự khẳng định cây trái có giao** nếu chưa xét vị trí `low`.
- Việc thuật toán đi một nhánh vẫn đúng là nhờ **kết hợp metadata `maxHigh` và bất biến BST theo `low`**, như chứng minh phía trên.

Nếu bỏ một trong hai bất biến, chứng minh không còn hiệu lực.

## 7. Tìm **tất cả** khoảng giao không giống tìm một khoảng

### 7.1. Định nghĩa kết quả

Với tập khoảng `S` và truy vấn `Q`:

\[
Report(Q)=\{I\in S:I\cap Q\ne\varnothing\}.
\]

Một hệ thống lập lịch có thể không chỉ cần biết **có xung đột hay không**, mà muốn liệt kê **mọi sự kiện xung đột**, để hiển thị cho người dùng.

Hàm tìm một kết quả có thể **dừng ngay** khi gặp khoảng giao. Hàm liệt kê mọi kết quả **không được dừng sớm** và có thể phải đi xuống **cả hai nhánh**, dù vẫn nên loại các nhánh chắc chắn không có giao.

### 7.2. Cắt tỉa khi liệt kê

Khi xét một cây con gốc `u`, có hai quy tắc hữu ích:

**Quy tắc 1 — Loại cây con kết thúc quá sớm.**

Nếu:

\[
maxHigh(u)<L,
\]

mọi khoảng trong cây con đều có đầu phải `<L`, nên **bỏ toàn bộ cây con**.

**Quy tắc 2 — Loại cây phải nếu đầu trái hiện tại quá muộn.**

Nếu:

\[
u.low>R,
\]

chính khoảng tại `u` và toàn bộ cây con phải đều có đầu trái `>R`, nên **chỉ cần tìm trong cây trái**.

Nếu không thuộc các trường hợp loại trừ, ta:

1. Kiểm tra khoảng tại `u`, thêm vào kết quả nếu giao.
2. Xét cả hai cây con còn có khả năng chứa kết quả.

### 7.3. Mã giả liệt kê

```text
REPORT-OVERLAPS(root, [L,R]):
    result = []
    stack = [root] nếu root tồn tại

    while stack không rỗng:
        u = stack.pop()

        if u.maxHigh < L:
            continue           # Cả subtree kết thúc trước L.

        if u.low > R:
            if u.left != None:
                stack.push(u.left)
            continue           # Phải chắc chắn bắt đầu sau R.

        if OVERLAP(u.interval, [L,R]):
            result.append(u.interval)

        if u.right != None:
            stack.push(u.right)
        if u.left != None:
            stack.push(u.left)

    return result
```

**Không áp dụng quy tắc “chỉ chọn một nhánh” của `INTERVAL-SEARCH`** khi cần liệt kê đủ kết quả: nếu cả hai nhánh có khoảng giao, hàm liệt kê phải khám phá cả hai.

### 7.4. Ví dụ nhiều giao nhau

Với cây bảy khoảng ở mục 4:

- `Q=[21,21]` giao `[16,21]` và `[15,23]`.
- `Q=[30,30]` giao `[25,30]` và `[26,40]`.
- `Q=[18,22]` giao `[15,23]`, `[16,21]` và `[17,19]`.
- `Q=[24,24]` **không** giao khoảng nào trong cây mẫu.

Hàm dùng stack ở trên có thể trả kết quả theo **thứ tự duyệt**, không nhất thiết theo `low` tăng dần. Nếu API yêu cầu kết quả theo thứ tự, có thể duyệt inorder với cắt nhánh hoặc sắp xếp danh sách kết quả; cần tính chi phí bổ sung khi sắp xếp.

### 7.5. Độ phức tạp khác biệt

Gọi `h` là chiều cao cây, `n` số khoảng, `k` số khoảng thực sự giao truy vấn.

- **Tìm một khoảng giao:** đi tối đa một đường, `O(h+1)` thời gian.
- **Liệt kê tất cả:** trong trường hợp xấu nhất phải kiểm tra tới `n` nút và trả `k` phần tử; chặn trên an toàn là **`O(n)` thời gian**, cộng công việc lưu/xuất kết quả.
- Nếu dùng danh sách trả về, bộ nhớ kết quả là **`O(k)`**. Stack DFS trên cây cân bằng có thể dùng **`O(h+1)`** chỗ chờ trong thuật toán này.
- Không được quảng cáo hàm liệt kê ở trên luôn có thời gian **`O(\log n+k)`** nếu chưa chứng minh một cơ chế báo cáo đầu ra nhạy với `k`.

Một cây AVL cao `O(\log n)` chỉ bảo đảm **đường đi đơn ngắn**, không có nghĩa **việc liệt kê hàng nghìn khoảng giao nhau** chỉ mất `O(\log n)`. Bản thân việc xuất `k` kết quả đã cần ít nhất `\Omega(k)` thời gian.

## 8. Cài đặt Python: AVL interval tree với `max_high`

Để cho thấy cấu trúc duy trì được metadata sau thay đổi, ta xây một cây **AVL tăng cường**, thay vì BST có thể suy biến thành đường thẳng.

Thiết kế cài đặt:

- Chỉ nhận các khoảng **đóng có đầu mút nguyên** `[low,high]`, `low≤high`.
- Mỗi bản ghi có một `uid` riêng, do cây cấp phát tăng dần.
- BST sắp theo cặp khóa `(low,uid)`.
- Mỗi nút lưu `max_high` và `height`.
- `add(low,high)` trả về một **handle** `(low,uid)` để sau này xóa đúng bản ghi.
- `remove(handle)` xóa đúng bản ghi tương ứng; khoảng khác cùng đầu mút không bị xóa.
- `find_any(L,R)` trả một khoảng giao hoặc `None`.
- `find_all(L,R)` trả toàn bộ các khoảng giao, **không cam kết thứ tự**.

Mã tập trung vào bất biến cấu trúc và metadata, không bao gồm xử lý đồng thời, giao dịch, lưu bền hay thay đổi ID của bản ghi.

### 8.1. Nút và các hàm nền

```python
class IntervalNode:
    def __init__(self, low, high, uid):
        self.low = low
        self.high = high
        self.uid = uid

        self.left = None
        self.right = None

        # Cây một nút: metadata đúng ngay.
        self.height = 0
        self.max_high = high

    @property
    def key(self):
        return (self.low, self.uid)


def h(node):
    """Chiều cao tính theo số cạnh."""
    return -1 if node is None else node.height


def pull(node):
    """Hai cây con đã có metadata đúng."""
    node.height = 1 + max(h(node.left), h(node.right))

    maximum = node.high
    if node.left is not None:
        maximum = max(maximum, node.left.max_high)
    if node.right is not None:
        maximum = max(maximum, node.right.max_high)

    node.max_high = maximum


def balance_factor(node):
    return h(node.left) - h(node.right)


def overlaps(node, low, high):
    """Giao của hai khoảng đóng; low <= high."""
    return node.low <= high and low <= node.high
```

Ở hàm `pull`, ta không phải lưu `-\infty` trong nút rỗng; nếu con không tồn tại, chỉ không xét nó khi tính `maximum`. Điều này tương đương với công thức toán học có `maxHigh(\varnothing)=-\infty`.

**Một lần `pull` là `O(1)`**, vì chỉ cần hai con và một số hằng phép `max`.

### 8.2. Hai phép xoay giữ đúng `max_high`

```python
def rotate_left(x):
    y = x.right
    if y is None:
        raise ValueError("Không thể xoay trái khi thiếu con phải")

    x.right = y.left
    y.left = x

    # x có các con mới, phải tính trước y.
    pull(x)
    pull(y)

    return y


def rotate_right(y):
    x = y.left
    if x is None:
        raise ValueError("Không thể xoay phải khi thiếu con trái")

    y.left = x.right
    x.right = y

    # y bị đẩy xuống, tính trước gốc mới x.
    pull(y)
    pull(x)

    return x
```

Phép xoay **không làm thay đổi tập khoảng trong vùng xoay**, chỉ đổi cấu trúc nội bộ. Tuy nhiên, `max_high` tại các nút bị đẩy xuống/nâng lên có thể khác trước, nên **không được bỏ qua `pull`**.

### 8.3. Tái cân bằng AVL

```python
def rebalance(node):
    """Hai cây con của node đã cân bằng và có metadata đúng."""
    pull(node)
    bf = balance_factor(node)

    if bf > 1:
        # Nặng trái: LL hoặc LR.
        if balance_factor(node.left) < 0:
            node.left = rotate_left(node.left)
        return rotate_right(node)

    if bf < -1:
        # Nặng phải: RR hoặc RL.
        if balance_factor(node.right) > 0:
            node.right = rotate_right(node.right)
        return rotate_left(node)

    return node
```

AVL có chiều cao `O(\log(n+1))` nhờ kiểm soát chênh lệch chiều cao của hai cây con tại **mọi** nút. Trong trường hợp mất cân bằng ở một mức sau chèn/xóa, `rebalance` chỉ thực hiện một hoặc hai phép xoay, với chi phí **`O(1)` tại mức đó**.

Khi xóa, một số mức trên đường tới gốc có thể cần tái cân bằng liên tiếp. Không được giả định cứ xoay xong tại một nút là có thể bỏ qua tất cả tổ tiên.

### 8.4. Chèn nút theo cặp khóa `(low,uid)`

```python
def insert_node(root, fresh):
    if root is None:
        return fresh

    if fresh.key < root.key:
        root.left = insert_node(root.left, fresh)
    elif fresh.key > root.key:
        root.right = insert_node(root.right, fresh)
    else:
        raise ValueError("Hai nút không được trùng handle")

    # Sau khi con đã đúng, tính lại và cân bằng gốc vùng.
    return rebalance(root)
```

Khóa `(low,uid)` là duy nhất do `uid` không được tái sử dụng trong cùng một cây. Vì vậy hai khoảng hoàn toàn giống nhau, ví dụ `[10,15]` và `[10,15]`, vẫn có thể được lưu như **hai nút khác nhau**.

**Chi phí:** chèn đi xuống một đường AVL, rồi cập nhật từ dưới lên: **`O(\log(n+1))` thời gian**.

### 8.5. Tách nút nhỏ nhất của cây con

Khi xóa một nút có hai con, cần tìm **kế nhiệm theo khóa BST** — nút nhỏ nhất trong cây con phải, tức cực trái của cây con ấy.

Ta dùng một hàm tách **nguyên đối tượng nút**:

```python
def pop_min_node(root):
    """Trả (gốc_còn_lại, nút_nhỏ_nhất_đã_tách)."""
    if root.left is None:
        rest = root.right
        root.right = None
        return rest, root

    root.left, minimum = pop_min_node(root.left)
    return rebalance(root), minimum
```

**Vì sao tách nguyên nút?** Một interval node chứa cả `low,high,uid`. Nếu chỉ sao chép `low` của kế nhiệm lên nút bị xóa mà bỏ qua `high/uid`, bản ghi sẽ bị **ghép sai đầu mút hoặc sai định danh**. Di chuyển nguyên nút kế nhiệm giúp giữ bộ ba thông tin nhất quán.

Nút nhỏ nhất không có con trái nhưng **có thể có con phải**. Trong trường hợp đó, `rest=root.right` phải được nối về đúng vị trí cũ; không được bỏ cây con này.

### 8.6. Xóa đúng một handle

```python
def delete_node(root, key):
    """Trả (gốc_mới, removed), key là (low, uid)."""
    if root is None:
        return None, False

    if key < root.key:
        root.left, removed = delete_node(root.left, key)

    elif key > root.key:
        root.right, removed = delete_node(root.right, key)

    else:
        # Đã tìm thấy đúng đối tượng bản ghi.
        if root.left is None:
            return root.right, True
        if root.right is None:
            return root.left, True

        # Hai con: dùng NGUYÊN nút kế nhiệm làm gốc vùng mới.
        new_right, successor = pop_min_node(root.right)

        successor.left = root.left
        successor.right = new_right

        # Không cần giữ liên kết ở nút đã bị loại khỏi cây.
        root.left = None
        root.right = None

        return rebalance(successor), True

    if not removed:
        return root, False

    return rebalance(root), True
```

**Chú ý:** nếu kết quả gốc của vùng con thay đổi sau xóa hoặc xoay, các khung đệ quy phía trên phải **gán lại con trỏ**. Khi xóa gốc toàn cây, mã gọi phải gán `self.root = new_root`.

Hàm không cố thay đổi `low` hoặc `high` của một nút còn đang sống trong BST. Để sửa một khoảng, cách đơn giản là **xóa handle cũ rồi thêm khoảng mới**, hoặc thiết kế API cập nhật có bảo trì thứ tự và metadata đầy đủ.

### 8.7. Lớp `IntervalTree` và các hàm truy vấn

```python
class IntervalTree:
    def __init__(self):
        self.root = None
        self.next_uid = 0
        self.length = 0

    @staticmethod
    def check_interval(low, high):
        # Phạm vi ví dụ: đầu mút nguyên; từ chối bool, float, NaN.
        if type(low) is not int or type(high) is not int:
            raise TypeError("Đầu mút phải là số nguyên")
        if low > high:
            raise ValueError("low phải <= high")

    def __len__(self):
        return self.length

    def add(self, low, high):
        """Trả handle (low, uid) dùng để xóa đúng bản ghi."""
        self.check_interval(low, high)

        uid = self.next_uid
        self.next_uid += 1

        fresh = IntervalNode(low, high, uid)
        self.root = insert_node(self.root, fresh)
        self.length += 1

        return (low, uid)

    def remove(self, handle):
        """Xóa đúng handle do add trả về."""
        if not (
            isinstance(handle, tuple)
            and len(handle) == 2
            and type(handle[0]) is int
            and type(handle[1]) is int
        ):
            raise TypeError("handle phải là cặp (low, uid)")

        self.root, removed = delete_node(self.root, handle)
        if removed:
            self.length -= 1
        return removed

    def find_any(self, low, high):
        """Tìm một khoảng đóng giao với [low, high]."""
        self.check_interval(low, high)

        node = self.root
        while node is not None:
            if overlaps(node, low, high):
                return (node.low, node.high, node.uid)

            if (
                node.left is not None
                and node.left.max_high >= low
            ):
                node = node.left
            else:
                node = node.right

        return None

    def find_all(self, low, high):
        """Trả tất cả khoảng giao, không bảo đảm thứ tự."""
        self.check_interval(low, high)

        result = []
        stack = [self.root] if self.root is not None else []

        while stack:
            node = stack.pop()

            # Cả cây con kết thúc trước đầu trái truy vấn.
            if node.max_high < low:
                continue

            # Nút hiện tại và toàn bộ cây con phải bắt đầu
            # sau đầu phải truy vấn.
            if node.low > high:
                if node.left is not None:
                    stack.append(node.left)
                continue

            if overlaps(node, low, high):
                result.append(
                    (node.low, node.high, node.uid)
                )

            if node.right is not None:
                stack.append(node.right)
            if node.left is not None:
                stack.append(node.left)

        return result

    def find_point(self, point):
        """Các khoảng đóng chứa điểm point."""
        return self.find_all(point, point)
```

Các tuple kết quả có dạng `(low,high,uid)`. Handle của `add` là `(low,uid)`, bởi đó là **khóa nhận diện BST**, còn `high` là dữ liệu của khoảng được lưu.

**Giới hạn:** mã hỗ trợ số nguyên hữu hạn. Với mốc thời gian, ngày tháng hoặc số thực, cần điều chỉnh kiểu đầu mút, so sánh và hợp đồng về độ chính xác. Với thời điểm nửa mở, phải sửa điều kiện giao và điều kiện cắt nhánh như đã nêu ở mục 2.

## 9. Thực hành: tạo cây, tìm giao và xóa

### 9.1. Dựng cây ví dụ

```python
intervals = [
    (16, 21),
    (8, 9),
    (25, 30),
    (5, 8),
    (15, 23),
    (17, 19),
    (26, 40),
]

tree = IntervalTree()
handles = []

for low, high in intervals:
    handles.append(tree.add(low, high))

print(len(tree))                # 7
print(tree.root.max_high)       # 40
```

Trong cài đặt AVL, hình dạng thực tế có thể thay đổi tùy thứ tự chèn và cách tái cân bằng, nhưng **mọi kết quả truy vấn đúng phải độc lập với hình dạng cuối cùng**.

### 9.2. Tìm một khoảng giao

```python
found = tree.find_any(22, 24)
print(found is not None)     # True
print(found[:2])             # (15, 23) ở tập dữ liệu mẫu.

print(tree.find_any(10, 14)) # None
print(tree.find_any(24, 24)) # None
```

Với `[22,24]`, chỉ khoảng `[15,23]` giao, nên kết quả có thể xác định rõ. Với các truy vấn có nhiều khoảng giao, `find_any` **không cam kết chọn khoảng nào**.

### 9.3. Liệt kê tất cả khoảng giao

```python
def endpoint_pairs(items):
    return sorted((low, high) for low, high, uid in items)


print(endpoint_pairs(tree.find_all(21, 21)))
# [(15, 23), (16, 21)]

print(endpoint_pairs(tree.find_all(30, 30)))
# [(25, 30), (26, 40)]

print(endpoint_pairs(tree.find_all(18, 22)))
# [(15, 23), (16, 21), (17, 19)]

print(endpoint_pairs(tree.find_all(24, 24)))
# []
```

Hàm `endpoint_pairs` chỉ phục vụ **hiển thị đầu mút đã sắp**, không phải một phần thuật toán tìm giao. Nó làm mất `uid`, nên không phù hợp để xóa khi có nhiều bản ghi khoảng trùng nhau.

### 9.4. Xóa chính xác một bản ghi

```python
# handles[4] là handle của khoảng [15,23].
removed_handle = handles[4]

print(tree.remove(removed_handle))  # True
print(tree.remove(removed_handle))  # False: đã xóa rồi.
print(len(tree))                    # 6
print(tree.find_any(22, 24))        # None

# Những khoảng khác vẫn tồn tại.
print(endpoint_pairs(tree.find_all(21, 21)))
# [(16, 21)]
```

**Điểm quan trọng:** sau khi xóa `[15,23]`, truy vấn `[22,24]` không còn giao khoảng nào; nếu `max_high` ở các tổ tiên không được tính lại, hàm có thể đi xuống các nhánh vô ích. Metadata cũ có thể gây mất hiệu quả hoặc làm thuật toán thiếu cơ sở chứng minh, dù một số truy vấn cụ thể vẫn tình cờ trả đúng.

### 9.5. Hai khoảng giống hệt nhau vẫn là hai bản ghi

```python
tree = IntervalTree()

first = tree.add(10, 20)
second = tree.add(10, 20)

print(first == second)   # False: UID khác.
print(len(tree))         # 2
print(len(tree.find_all(15, 15)))  # 2

assert tree.remove(first)
print(len(tree.find_all(15, 15)))  # 1
assert tree.remove(second)
print(len(tree.find_all(15, 15)))  # 0
```

Một BST chỉ sắp theo `low` mà không có chính sách rõ ràng với khóa trùng có thể nhầm lẫn các bản ghi này. Cặp khóa `(low,uid)` là một cách xử lý đơn giản.

## 10. Duy trì `maxHigh` sau chèn: cập nhật từ dưới lên

### 10.1. Chèn một lá mới

Giả sử cây có:

```text
                    [16,21] maxHigh=30
                       /          \
                [8,9] max=9     [25,30] max=30
```

Chèn `[15,23]`:

- Theo khóa `low=15`: `15<16` nên đi trái tới `[8,9]`; `15>8` nên thêm bên phải.
- Nút mới có `maxHigh=23`.
- Tính lại `[8,9]`: `max(9,23)=23`.
- Tính lại `[16,21]`: `max(21,23,30)=30`.

```text
                    [16,21] maxHigh=30
                       /          \
              [8,9] max=23       [25,30] max=30
                 \
                [15,23] max=23
```

Mặc dù `maxHigh` ở gốc **không đổi**, metadata của nút `[8,9]` đã thay đổi. Không nên tối ưu bằng cách “chỉ sửa `maxHigh(root)`”.

### 10.2. Cập nhật đường đi

Khi chèn một lá, **chỉ các tổ tiên của vị trí chèn** có thể có `maxHigh` khác trước; những cây con ở nơi khác không đổi.

Cách triển khai đệ quy:

1. Gọi chèn tại cây con phù hợp.
2. Nhận gốc cây con mới, gán lại `left/right`.
3. Gọi `rebalance`, trong đó `pull` tính lại `height/maxHigh`.
4. Trả gốc mới lên khung gọi cha.

Thứ tự gọi như vậy bảo đảm **con đúng trước cha**.

### 10.3. Chi phí chèn

Mỗi lần đi xuống BST là một phép so sánh khóa. Mỗi mức đi ngược cần một số hằng phép gộp và nhiều nhất một hoặc hai phép xoay trong quy tắc AVL.

Với AVL `n` nút:

\[
T_{\text{insert}}(n)=O(\log(n+1)).
\]

Với BST tăng cường **không cân bằng**, chiều cao có thể bằng `n-1` và chèn có thể thành `O(n)`. **Thêm `maxHigh` không tự tạo cân bằng.**

## 11. Duy trì `maxHigh` sau xóa: vì sao cần tính lại?

### 11.1. Xóa nút giữ đầu phải lớn nhất

Giả sử một cây con có:

```text
            [25,30] maxHigh=40
                 \
                 [26,40] maxHigh=40
```

Xóa `[26,40]`, cây con còn:

```text
            [25,30] maxHigh=30
```

Nếu `maxHigh` ở nút `[25,30]` vẫn bằng `40`, nó không còn mô tả đúng dữ liệu. Truy vấn có `L=35` có thể bị dẫn vào nhánh không chứa kết quả.

Trong cây cân bằng có thể còn các phép xoay phát sinh sau xóa, nên phải tính lại **mọi nút bị thay đổi con**, bao gồm các nút ở vùng xoay.

### 11.2. Ba trường hợp xóa cơ bản

**Xóa lá:** thay liên kết từ cha tới lá thành `None`, rồi tính lại metadata trên đường lên gốc.

**Xóa nút một con:** đưa con duy nhất lên thay nút bị xóa; cây con còn lại đã có metadata đúng, cha phía trên cần tổng hợp lại.

**Xóa nút hai con:** chọn nút kế nhiệm inorder để thay nút bị xóa, sau đó nối lại cây con phải đã được tách kế nhiệm.

Nếu bản ghi chứa `low,high,uid`, phải giữ cả **ba trường cùng một đối tượng logic**. Mã ở mục 8 dùng **nguyên nút kế nhiệm** làm gốc vùng mới, tránh việc sao chép đầu trái nhưng quên đầu phải hoặc ID.

### 11.3. Cập nhật theo thứ tự phụ thuộc

Ở trường hợp hai con:

1. `pop_min_node` cập nhật/tái cân bằng **cây con phải đã bị tách kế nhiệm**.
2. Nút kế nhiệm được gắn hai cây con phù hợp.
3. `rebalance(successor)` tính lại `height/max_high` với hai con **đã đúng**.
4. Các tổ tiên ở bên ngoài vùng này tiếp tục `rebalance` khi đệ quy trở về.

Chỉ tính lại `max_high` ở gốc toàn cây là **không đủ**, vì thuật toán tìm giao đọc metadata **ở các cây con giữa đường đi**.

### 11.4. Khi cập nhật đầu mút thay vì thêm/xóa

Nếu sửa `high` của một khoảng:

- Thứ tự BST theo `(low,uid)` **không đổi**.
- Nhưng `maxHigh` của chính nút và các tổ tiên **có thể đổi**.
- Nếu không có tham chiếu cha, có thể tìm nút theo handle rồi tính lại trên đường trở về.

Nếu sửa `low`:

- **Khóa BST thay đổi**, có thể phá thứ tự trái/phải.
- Không được chỉ sửa `low` tại chỗ.
- Có thể xóa handle cũ rồi thêm khoảng mới, hoặc triển khai giao dịch đổi khóa có tái tổ chức cây.

Trong mã minh họa, API **không có hàm update**; việc xóa rồi thêm sẽ tạo `uid` mới. Nếu ứng dụng cần ID bền vững, phải thiết kế thêm giao diện cập nhật giữ định danh và các bất biến tương ứng.

## 12. Sau phép xoay, `maxHigh` nào cần tính lại?

### 12.1. Xoay trái

```text
Trước xoay trái:                     Sau xoay trái:

        x                                 y
       / \                               / \
      A   y                             x   C
         / \                           / \
        B   C                         A   B
```

Giả sử:

- `A,B,C` là các cây con có metadata đúng.
- Khoảng tại `x` là `I_x`, tại `y` là `I_y`.

Sau xoay:

\[
maxHigh(x)=\max(high(I_x),maxHigh(A),maxHigh(B)),
\]

\[
maxHigh(y)=\max(high(I_y),maxHigh(x),maxHigh(C)).
\]

Phải gọi **`pull(x)` trước `pull(y)`**. Nếu làm ngược lại, `y` có thể đọc `maxHigh(x)` cũ, trong đó có cả những khoảng nay đã nằm ngoài cây con `x`.

### 12.2. Xoay phải

Xoay phải tại `y` có `x=y.left`:

```text
Trước:                              Sau:

        y                                 x
       / \                               / \
      x   C                             A   y
     / \                                   / \
    A   B                                 B   C
```

Sau xoay phải:

1. Gắn `y.left=B`, `x.right=y`.
2. Gọi **`pull(y)` trước**.
3. Gọi **`pull(x)` sau**.
4. Trả `x` làm gốc vùng mới.

Một phép xoay đơn dùng **`O(1)` thao tác liên kết và metadata**.

### 12.3. Vì sao metadata ở gốc vùng xoay có thể giữ nguyên?

Nếu chỉ xét **tập các khoảng**, vùng trước và sau xoay chứa đúng các khoảng ở `A,B,C,x,y`. Do đó đầu phải lớn nhất của **cả vùng** không đổi.

Tuy nhiên, trường `maxHigh` tại **nút bị đẩy xuống** thường có thể thay đổi, vì tập hậu duệ của nó đổi. Điều này tạo một nguyên tắc chung cho **cây tăng cường**:

> Một phép xoay có thể bảo toàn thống kê của **toàn vùng**, nhưng vẫn làm thống kê của **những nút bên trong vùng** phải tính lại.

Với AVL, `height` còn có thể thay đổi do hình dạng đổi. Việc bảo trì `height` là điều kiện để các lần tái cân bằng tiếp theo đúng.

### 12.4. Xoay kép

- **LL:** xoay phải một lần.
- **RR:** xoay trái một lần.
- **LR:** xoay trái ở con trái, rồi xoay phải.
- **RL:** xoay phải ở con phải, rồi xoay trái.

Mỗi xoay đơn tự cập nhật metadata tại hai nút bị ảnh hưởng. Vì số xoay trong một lần `rebalance` là hằng, chi phí xử lý metadata tại một mức vẫn `O(1)`.

Không được quên **gán lại gốc vùng xoay** cho cha hoặc cho biến gốc toàn cây.

## 13. Chi phí thời gian và bộ nhớ

Ký hiệu:

- `n`: số **bản ghi khoảng** (có thể có đầu mút giống nhau nhưng ID khác nhau).
- `h`: chiều cao cây theo số cạnh.
- `k`: số kết quả giao nhau được báo ra.
- Giả định so sánh đầu mút và ID mất `O(1)`.

| Thao tác | BST tăng cường bất kỳ | AVL interval tree |
|---|---|---|
| Tìm **một** khoảng giao | `O(h+1)` | `O(\log(n+1))` |
| Tìm **tất cả** khoảng giao | `O(n)` trường hợp xấu nhất | `O(n)` trường hợp xấu nhất |
| Chèn một khoảng | `O(h+1)` nếu duy trì metadata theo đường đi | `O(\log(n+1))` |
| Xóa theo handle `(low,uid)` | `O(h+1)` | `O(\log(n+1))` |
| Cập nhật `maxHigh` tại một nút | `O(1)` | `O(1)` |
| Một phép xoay đơn + cập nhật metadata | `O(1)` | `O(1)` |
| Dựng metadata bằng hậu thứ tự từ một cây đã hợp lệ | `O(n)` | `O(n)` |
| Lưu các nút và metadata | `O(n)` | `O(n)` |

### 13.1. Bộ nhớ phụ

- `find_any` là vòng lặp đi theo một nhánh: **`O(1)` bộ nhớ phụ**.
- `find_all` dùng stack DFS: tối đa **`O(h+1)` bộ nhớ công việc** trên cây hợp lệ với cách duyệt cắt nhánh hiện tại; danh sách kết quả thêm **`O(k)`**.
- `insert_node`, `delete_node`, `pop_min_node` dùng đệ quy: **`O(h+1)` khung gọi**, tức `O(\log(n+1))` trên AVL hợp lệ.
- Mỗi nút lưu `max_high` và `height`: thêm **`O(n)` bộ nhớ metadata**.
- Biến `length`, `next_uid` trong cây chỉ cần số trường hằng, không đổi bậc `O(n)` của cấu trúc.

### 13.2. Cân bằng giúp thao tác nào?

AVL bảo đảm một đường từ gốc xuống lá dài `O(\log(n+1))`. Vì thế:

- Tìm một khoảng giao dùng **một đường**, nhanh theo logarit.
- Chèn/xóa tìm đúng vị trí rồi cập nhật dọc **một đường** (cộng một số xoay), nhanh theo logarit.
- Liệt kê **mọi** khoảng có thể thăm rất nhiều nhánh, nên **không thể suy ra `O(\log n)`** chỉ từ cây cân bằng.

Nếu truy vấn có `k=n` kết quả, riêng việc xuất đủ kết quả đã cần `\Omega(n)` thời gian.

### 13.3. Chi phí tạo cây từ nhiều khoảng

Nếu chèn lần lượt `n` khoảng vào AVL rỗng, tổng thời gian chặn trên:

\[
O(n\log(n+1)).
\]

Không nên kết luận tổng là `O(n)` chỉ vì mỗi lần `pull` cần `O(1)`. Phải tính cả đường tìm vị trí và cân bằng của từng lần chèn.

Nếu đầu vào được chuẩn bị, sắp theo khóa và dùng một thuật toán dựng cây cân bằng hàng loạt, có thể thiết kế cách xây nhanh hơn, nhưng cần xây dựng đúng cả metadata và bất biến cân bằng. Đó là một thuật toán riêng, không phải thuộc tính mặc định của vòng lặp `add`.

## 14. Hàm xác thực độc lập cây khoảng

Một interval tree có thể sai mà truy vấn đơn giản chưa phát hiện. Ví dụ:

- `max_high` tại một nút được lưu nhỏ hơn đầu phải lớn nhất thật của cây con → có thể **cắt nhầm** một nhánh chứa đáp án.
- `max_high` bị lưu lớn hơn thực tế → có thể vẫn tìm đúng nhưng tốn thêm công việc.
- `height` sai → `rebalance` chọn sai phép xoay.
- Một nút bị dùng chung hoặc tham chiếu tạo chu trình → duyệt có thể không kết thúc.
- Thứ tự `(low,uid)` sai → chứng minh chọn nhánh trong `find_any` không còn đúng.

Vì vậy, khi học và tự kiểm thử, nên **tính lại mọi thông tin từ cấu trúc thực**, không tin vào metadata đang lưu.

### 14.1. Validator hậu thứ tự bằng stack

```python
def validate_interval_avl(tree):
    """Kiểm tra toàn bộ BST, AVL, interval và max_high."""
    root = tree.root
    if root is None:
        return len(tree) == 0

    seen_objects = set()
    seen_uids = set()
    actual = {}
    # (node, lower_key, upper_key, ready)
    frames = [(root, None, None, False)]

    while frames:
        node, low_key, high_key, ready = frames.pop()

        if node is None:
            continue
        if not isinstance(node, IntervalNode):
            return False

        if not ready:
            marker = id(node)
            if marker in seen_objects:
                return False  # Chu trình hoặc dùng chung một nút.
            seen_objects.add(marker)

            if (
                type(node.low) is not int
                or type(node.high) is not int
                or type(node.uid) is not int
                or node.low > node.high
            ):
                return False

            if node.uid in seen_uids:
                return False
            seen_uids.add(node.uid)

            key = node.key
            if low_key is not None and key <= low_key:
                return False
            if high_key is not None and key >= high_key:
                return False

            frames.append((node, low_key, high_key, True))
            frames.append((node.right, key, high_key, False))
            frames.append((node.left, low_key, key, False))

        else:
            lh, lmax = actual.get(node.left, (-1, None))
            rh, rmax = actual.get(node.right, (-1, None))

            expected_height = 1 + max(lh, rh)
            expected_max = node.high

            if lmax is not None:
                expected_max = max(expected_max, lmax)
            if rmax is not None:
                expected_max = max(expected_max, rmax)

            if node.height != expected_height:
                return False
            if node.max_high != expected_max:
                return False
            if abs(lh - rh) > 1:
                return False

            actual[node] = (expected_height, expected_max)

    return len(seen_objects) == len(tree)
```

Hàm duyệt **toàn bộ `n` nút**, dùng `O(n)` thời gian và `O(n)` bộ nhớ phụ do bảng kết quả, tập ID đã thăm và stack. Nó dành cho **kiểm thử, xác thực và điều tra lỗi**, không phải một phần bắt buộc của mỗi lần cập nhật cần `O(\log n)`.

### 14.2. Các phép kiểm tra ví dụ

```python
tree = IntervalTree()
assert validate_interval_avl(tree)

records = [
    (16, 21), (8, 9), (25, 30),
    (5, 8), (15, 23), (17, 19), (26, 40)
]
handles = []

for low, high in records:
    handles.append(tree.add(low, high))
    assert validate_interval_avl(tree)

assert len(tree) == 7
assert tree.root.max_high == 40
assert tree.find_any(22, 24)[:2] == (15, 23)
assert tree.find_any(24, 24) is None

assert tree.remove(handles[4])
assert validate_interval_avl(tree)
assert tree.find_any(22, 24) is None

# Gây lỗi nhân tạo để thấy validator phát hiện.
tree.root.max_high = -1
assert not validate_interval_avl(tree)
```

Các `assert` minh họa kỳ vọng và cách kiểm chứng cho người học. Chúng **không đại diện một lần chạy test thực tế** trong quy trình viết bài này.

### 14.3. Đối chiếu với thuật toán tuyến tính đơn giản

Để kiểm thử nghiêm túc khi triển khai một cây khoảng, có thể duy trì một tập tham chiếu `reference` độc lập:

```text
Sau mỗi add(low, high):
    lưu (low, high, uid) vào reference

Sau mỗi remove(handle):
    bỏ đúng bản ghi có handle ấy khỏi reference

Với nhiều truy vấn [L,R]:
    expected = mọi bản ghi I trong reference
               thỏa I.low <= R và L <= I.high

    actual = tree.find_all(L,R)

    so sánh hai tập theo (low, high, uid)
    kiểm tra tree.find_any(L,R) là None
        khi và chỉ khi expected rỗng
    nếu find_any trả khoảng thì khoảng ấy thuộc expected
```

Đây là cách kiểm tra chéo **tính đúng** bằng một thuật toán chậm nhưng đơn giản. Một lần quét tuyến tính làm mốc so sánh tốn `O(n)` mỗi truy vấn, hợp lý trong bộ thử nghiệm quy mô nhỏ, nhưng không nên dùng trong đường truy vấn sản xuất nếu mục tiêu là tăng tốc.

## 15. Các tình huống biên thường làm lộ lỗi

### 15.1. Cây rỗng

```python
tree = IntervalTree()

assert tree.find_any(1, 5) is None
assert tree.find_all(1, 5) == []
assert tree.find_point(3) == []
assert len(tree) == 0
```

Không được đọc `root.max_high` khi gốc bằng `None`.

### 15.2. Một khoảng là một điểm

```python
tree = IntervalTree()
tree.add(5, 5)

assert tree.find_any(5, 5) is not None
assert tree.find_any(4, 4) is None
assert tree.find_any(6, 6) is None
```

Vì đây là **khoảng đóng**, `[5,5]` có đúng một điểm và là một khoảng hợp lệ.

### 15.3. Giao đúng một đầu mút

```python
tree = IntervalTree()
tree.add(2, 8)

assert tree.find_any(8, 12) is not None
assert tree.find_any(9, 12) is None
```

Nếu bài toán là lịch **nửa mở**, kết quả cho khoảng chạm đúng tại `8` phải được xử lý **khác**.

### 15.4. Đầu mút âm và khoảng bao chứa

```python
tree = IntervalTree()
tree.add(-20, 20)
tree.add(-5, -1)
tree.add(3, 4)

assert len(tree.find_all(0, 3)) == 2
# [-20,20] và [3,4] giao; [-5,-1] không giao với [0,3].
```

Giá trị âm không gây vấn đề về mặt thuật toán, vì `maxHigh` dựa trên **so sánh đầu mút**, không dựa trên việc chúng có dương hay không.

### 15.5. Khoảng bao chứa và khoảng bị chứa

```text
A = [-100,100]
B = [0,1]
Q = [0,0]

A và B đều giao với Q, dù A chứa B.
```

Không được thay điều kiện giao bằng yêu cầu “đầu trái của khoảng lưu phải nằm bên trong truy vấn”. Quy tắc như vậy sẽ bỏ sót `A`.

### 15.6. Dữ liệu đầu vào không hợp lệ

```python
tree = IntervalTree()

try:
    tree.add(9, 3)
except ValueError:
    pass

try:
    tree.find_any(10, 2)
except ValueError:
    pass

try:
    tree.add(1.5, 3.5)
except TypeError:
    pass
```

Bài này **không tự đổi chỗ `low/high`** khi người dùng nhập ngược. Việc chuẩn hóa đầu vào phải được quyết định ở API; im lặng đổi chỗ có thể che giấu một lỗi nghiệp vụ.

## 16. Khi nào cấu trúc này phù hợp hơn cách khác?

### 16.1. So sánh với mảng tuyến tính

Một danh sách các khoảng rất đơn giản:

```python
def linear_find_any(intervals, low, high):
    for a, b in intervals:
        if a <= high and low <= b:
            return (a, b)
    return None
```

- **Ưu điểm:** code ngắn, bộ nhớ cấu trúc phụ nhỏ, dễ kiểm chứng.
- **Nhược điểm:** `O(n)` thời gian mỗi lần tìm trong trường hợp xấu nhất.
- **Phù hợp:** dữ liệu nhỏ, truy vấn hiếm, ít cần thêm/xóa hoặc chỉ một lần xử lý.

Interval tree có thêm trường metadata, thao tác cân bằng và chi phí duy trì, nên **không phải mọi bài toán đều cần cây khoảng**.

### 16.2. So sánh với danh sách đã sắp theo đầu trái

Nếu các khoảng được lưu trong mảng sắp theo `low`:

- Có thể tìm nhanh vị trí theo đầu trái bằng tìm nhị phân.
- Nhưng các khoảng bắt đầu rất sớm và kết thúc rất muộn vẫn có thể giao với truy vấn.
- Chèn/xóa giữa mảng cần dời nhiều phần tử, tới `O(n)`.
- Chỉ thứ tự đầu trái chưa đủ để bỏ các khoảng có đầu phải kéo dài.

Interval tree tăng cường `maxHigh` giúp **loại cây con theo đầu phải lớn nhất**, điều mà danh sách sắp theo `low` không tự cung cấp.

### 16.3. So sánh với segment tree

**Segment tree** thường rất phù hợp khi:

- Có **miền tọa độ/điểm chỉ số** cố định hoặc có thể nén.
- Cần cập nhật/truy vấn **giá trị tổng hợp trên đoạn** như tổng, min, max.
- Có thể cần lazy propagation cho cập nhật hàng loạt.

Cây khoảng trong bài quản lý **các đối tượng là những khoảng riêng**, cần tìm khoảng **giao** và có thể xóa đúng một bản ghi theo ID. Đây là mục tiêu khác với segment tree thông thường.

Không nên dùng tên “cây đoạn” và “cây khoảng” như hai tên đồng nghĩa. Chúng có thể giải quyết những bài toán liên quan nhưng khác nhau về bất biến và API.

### 16.4. So sánh với sweep line

Nếu có **một bộ khoảng cố định** và muốn tìm tất cả các cặp giao nhau hoặc xử lý sự kiện theo thứ tự đầu mút, phương pháp **quét đường thẳng (sweep line)** với một tập sự kiện được sắp xếp có thể hiệu quả và đơn giản hơn.

Nếu các khoảng **thêm/xóa liên tục** và có nhiều truy vấn giao nhau độc lập, interval tree tự cân bằng là lựa chọn tự nhiên.

### 16.5. So sánh với cấu trúc nhiều chiều

Khoảng một chiều biểu diễn bằng hai đầu mút `low,high`. Với **hình chữ nhật hai chiều** hoặc vùng không gian nhiều chiều, bài toán giao nhau có thêm trục tọa độ và có thể cần **range tree, R-tree, k-d tree** hoặc một cấu trúc không gian khác.

Không áp dụng trực tiếp công thức `maxHigh` một chiều để kết luận giao nhau trong không gian nhiều chiều.

## 17. Những sai lầm thường gặp

1. **Không nói rõ loại khoảng.** Với khoảng đóng, chạm đầu mút là giao; với nửa mở, không nhất thiết.
2. **Dùng `<` thay cho `≤` trong phép giao khoảng đóng.** Sẽ bỏ sót trường hợp chạm đúng đầu mút.
3. **Cho phép `low>high` mà không có hợp đồng xử lý.** Có thể sinh các khoảng vô nghĩa và phá giả thiết chứng minh.
4. **Nhầm giao nhau với chứa trọn.** Hai khoảng chỉ cần một điểm chung để giao.
5. **Sắp BST theo `low` rồi cho rằng đủ tìm giao nhanh.** Một khoảng bắt đầu sớm nhưng kết thúc muộn vẫn có thể giao.
6. **Lưu `maxHigh` bằng đầu phải của chính nút.** Phải lấy **max trên toàn bộ cây con**.
7. **Chỉ cập nhật `maxHigh` ở gốc sau chèn/xóa.** Các nút trung gian cũng phải đúng để cắt nhánh.
8. **Quên `maxHigh` của cây con rỗng.** Công thức toán dùng `-\infty` hoặc xử lý `None` rõ ràng.
9. **Kết luận `maxHigh(left)≥L` có nghĩa chắc chắn có giao trong cây trái.** Đây chỉ là điều kiện còn khả năng; cần kết hợp BST và lập luận chọn nhánh.
10. **Chỉ kiểm tra `maxHigh(left)<L` rồi bỏ qua điều kiện BST.** Chứng minh đi một nhánh phụ thuộc cả thứ tự `low`.
11. **Dùng `find_any` để liệt kê tất cả khoảng giao.** Thuật toán một đường chỉ được phép trả **một** kết quả.
12. **Duyệt cả hai nhánh nhưng không cắt cây con có `maxHigh<L`.** Vẫn đúng nhưng làm mất lợi ích tăng cường.
13. **Bỏ cây phải khi `node.low≤R` mà không có chứng cứ.** Nhánh phải vẫn có thể chứa nhiều kết quả.
14. **Cho rằng AVL cân bằng thì liệt kê `k` kết quả luôn mất `O(\log n)`.** Phải trả `k` phần tử, có thể phải thăm nhiều nhánh.
15. **Không xử lý các khoảng trùng đầu trái.** Phải có khóa phụ hoặc chính sách trùng nhất quán.
16. **Dùng cặp `(low,high)` để nhận dạng duy nhất nếu có khoảng trùng hoàn toàn.** Hai bản ghi giống đầu mút vẫn có thể có ID khác nhau.
17. **Sửa trực tiếp `low` của nút.** Có thể phá thứ tự BST; cần tái định vị bản ghi.
18. **Sửa trực tiếp `high` mà không cập nhật `maxHigh` ở tổ tiên.** Metadata sẽ cũ.
19. **Xóa nút có hai con chỉ sao chép `low` của kế nhiệm.** Làm lệch `high`, ID và ý nghĩa bản ghi.
20. **Quên con phải của nút kế nhiệm khi tách nút cực trái.** Có thể làm mất cả một cây con.
21. **Xoay cây rồi không gọi `pull`.** Các nút bị thay đổi hậu duệ có thể giữ `maxHigh` sai.
22. **Gọi `pull` trên gốc mới trước nút bị đẩy xuống.** Có thể dùng metadata cũ của con.
23. **Quên nối gốc vùng xoay vào cha hoặc gốc toàn cây.** Cấu trúc có thể bị đứt liên kết.
24. **Cho rằng lưu `maxHigh` là đủ để cây tự cân bằng.** Cây nền vẫn có thể suy biến; cần AVL/Red–Black nếu muốn chặn logarit.
25. **Nhầm thời gian cập nhật một nút `O(1)` với thời gian chèn toàn cây `O(1)`.** Vẫn phải đi xuống và lên một đường.
26. **Cho truy vấn đọc trong khi thao tác chỉnh cây chưa hoàn tất.** Có thể thấy liên kết và metadata không đồng nhất.
27. **Dùng đầu mút số thực chứa `NaN` mà không có chính sách so sánh.** `NaN` có thể phá tính thứ tự cần cho BST.
28. **Không kiểm tra khoảng điểm `[x,x]`.** Nó hợp lệ dưới quy ước khoảng đóng.
29. **Đổi thời gian sang số nhưng quên múi giờ hoặc quy tắc mốc kết thúc.** Lỗi mô hình hóa có thể khiến kết quả giao sai dù cây đúng.
30. **Chạy xác thực toàn cây `O(n)` sau mọi cập nhật rồi vẫn gọi tổng chi phí `O(\log n)`.** Validation là bước riêng.
31. **Cho rằng `maxHigh` luôn giúp loại ngay mọi nhánh không có kết quả.** Điều kiện metadata là cận trên, có thể dẫn đến thăm nhánh không chứa khoảng giao.
32. **Giả định thứ tự kết quả `find_all` luôn tăng theo `low`.** DFS stack minh họa không có cam kết sắp xếp.

## 18. Bài tập thực hành có đáp án

### Bài 1. Xác định giao khoảng đóng

Hai khoảng `A=[4,10]` và `B=[10,15]` có giao nhau không?

**Đáp án:** **Có**, tại điểm `10`. Với khoảng **đóng**, điều kiện `4≤15` và `10≤10` đều đúng.

### Bài 2. Cùng đầu mút nhưng khoảng nửa mở

Nếu hai lượt đặt là `[4,10)` và `[10,15)` thì sao?

**Đáp án:** **Không giao**, vì mốc `10` không thuộc khoảng thứ nhất. Không thể dùng nguyên điều kiện `≤` của khoảng đóng.

### Bài 3. Khoảng điểm

`[7,7]` có phải khoảng rỗng không? Nó có giao với `[6,8]` không?

**Đáp án:** Trong quy ước **khoảng đóng**, `[7,7]` chứa một điểm `7` nên **không rỗng** và có giao với `[6,8]`.

### Bài 4. Công thức giao

Với `A=[a,b]` và `B=[c,d]` đóng, viết điều kiện cần và đủ để hai khoảng giao nhau.

**Đáp án:** `a≤d` và `c≤b`, tương đương `max(a,c)≤min(b,d)`.

### Bài 5. Tính `maxHigh` ở nút trong

Một nút chứa `[8,9]`, cây trái có `maxHigh=8`, cây phải có `maxHigh=23`. `maxHigh` tại nút là bao nhiêu?

**Đáp án:** `max(9,8,23)=23`.

### Bài 6. Tính metadata gốc

Cây có gốc `[16,21]`, cây trái `maxHigh=23` và cây phải `maxHigh=40`. Tính `maxHigh(root)`.

**Đáp án:** `max(21,23,40)=40`.

### Bài 7. Cắt một cây con chắc chắn không giao

Truy vấn đóng `Q=[22,24]`, cây con `T` có `maxHigh(T)=18`. Có thể bỏ cả `T` không?

**Đáp án:** **Có.** Mọi khoảng trong `T` kết thúc ở điểm `≤18<22`, nên không thể giao truy vấn.

### Bài 8. Cận trên chưa đủ xác nhận

Truy vấn `[10,14]`, một cây con có `maxHigh=23`. Có thể khẳng định cây con đó chắc chắn chứa khoảng giao không?

**Đáp án:** **Không.** `maxHigh≥10` chỉ nói có khoảng kết thúc đủ muộn; đầu trái của khoảng đó có thể `>14`. Phải xét thêm bất biến BST và các nút cụ thể.

### Bài 9. Truy vết tìm một khoảng

Trên cây ví dụ ở mục 4, `find_any([22,24])` đi qua những nút nào?

**Đáp án:** `[16,21] → [8,9] → [15,23]`, rồi trả `[15,23]`.

### Bài 10. Truy vấn không có kết quả

Trên cùng cây, `find_any([10,14])` trả gì?

**Đáp án:** `None`. Các khoảng trong cây đều kết thúc trước `10` hoặc bắt đầu sau `14` đối với những ứng viên có thể bị xét.

### Bài 11. Liệt kê tất cả khoảng giao tại một điểm

Với `Q=[21,21]`, những khoảng nào ở cây mẫu giao với truy vấn?

**Đáp án:** `[16,21]` và `[15,23]`. Cả hai chứa điểm `21`.

### Bài 12. Hai khoảng giao tại điểm `30`

Truy vấn `[30,30]` giao những khoảng nào ở cây mẫu?

**Đáp án:** `[25,30]` và `[26,40]`.

### Bài 13. Vì sao không dùng một nhánh để liệt kê tất cả?

Giả sử ở một nút, cả cây trái và cây phải đều có khoảng giao với truy vấn. Thuật toán chỉ đi một nhánh sẽ trả thiếu gì?

**Đáp án:** Nó có thể bỏ sót **các khoảng giao ở nhánh còn lại**. `find_any` có thể chỉ đi một nhánh vì cần một đáp án; `find_all` phải khám phá mọi nhánh chưa bị chứng minh là không có kết quả.

### Bài 14. Điều kiện bỏ cây phải

Trong một BST sắp theo `low`, nút đang xét có `low(u)=30` và truy vấn có đầu phải `R=25`. Có thể bỏ cây phải không?

**Đáp án:** **Có.** Mọi nút bên phải có đầu trái `≥30>25`, nên không thể giao truy vấn; chỉ còn khả năng ở cây trái.

### Bài 15. Chèn khoảng mới

Một nút chứa `[8,9]`, chưa có cây phải. Chèn `[15,23]` làm con phải. `maxHigh` của nút `[8,9]` từ `9` thành bao nhiêu?

**Đáp án:** Thành **`23`**. Sau đó phải cập nhật các tổ tiên theo thứ tự từ dưới lên.

### Bài 16. Xóa đầu phải lớn nhất

Cây con gồm `[25,30]` và con phải `[26,40]`, `maxHigh=40`. Sau khi xóa `[26,40]`, `maxHigh` mới là bao nhiêu?

**Đáp án:** **`30`**, vì chỉ còn khoảng `[25,30]`.

### Bài 17. Khóa trùng đầu trái

Có hai bản ghi `[10,15]` và `[10,25]`. Nếu BST chỉ dùng `low` làm khóa, vấn đề gì có thể xảy ra? Bài dùng cách nào?

**Đáp án:** Hai bản ghi cùng `low=10` có thể bị nhầm là một nếu không có chính sách trùng. Bài dùng khóa ghép **`(low,uid)`** với ID riêng, bảo đảm mỗi bản ghi có một vị trí BST xác định.

### Bài 18. Khoảng trùng hoàn toàn

Thêm hai lần `[10,20]` với hai UID khác nhau. Xóa handle của một khoảng thì kết quả tìm `[15,15]` còn mấy bản ghi?

**Đáp án:** **Một bản ghi**, vì mỗi lượt thêm tạo một nút riêng và chỉ xóa đúng handle đã chọn.

### Bài 19. Xoay trái và metadata

Trong phép xoay trái tại `x`, với `y=x.right`, tại sao phải tính lại `maxHigh(x)` trước `maxHigh(y)`?

**Đáp án:** Sau xoay, `x` có cây con mới và trở thành con trái của `y`. `maxHigh(y)` phụ thuộc **giá trị mới** của `maxHigh(x)` nên phải tính `x` trước.

### Bài 20. Xóa nút có hai con

Khi xóa một nút chứa `(low,high,uid)` và dùng kế nhiệm inorder, vì sao không được sao chép chỉ `low` từ kế nhiệm?

**Đáp án:** Vì sẽ ghép `low` của một bản ghi với `high/uid` của bản ghi khác, làm dữ liệu không nhất quán. Phải di chuyển nguyên nút hoặc sao chép **đầy đủ** các trường bản ghi theo một quy tắc đúng.

### Bài 21. Độ phức tạp tìm một khoảng

Với AVL chứa `n` khoảng, `find_any` mất bao lâu trong trường hợp xấu nhất?

**Đáp án:** **`O(\log(n+1))`**, vì thuật toán chỉ đi tối đa một đường từ gốc xuống và AVL có chiều cao logarit.

### Bài 22. Độ phức tạp tìm tất cả

Với cây AVL chứa `n` khoảng, truy vấn có `k` kết quả. Có thể bảo đảm `find_all` ở mục 8 luôn mất `O(\log n+k)` không?

**Đáp án:** **Không có bảo đảm đó từ thuật toán minh họa.** Chặn trên an toàn là **`O(n)`** trường hợp xấu nhất, với bộ nhớ kết quả `O(k)`; còn phải tính chi phí duyệt những nhánh chưa loại được.

### Bài 23. Truy vấn điểm

Một hàm `find_point(x)` tìm mọi khoảng chứa điểm `x` có thể quy đổi thành truy vấn khoảng nào?

**Đáp án:** Tìm mọi khoảng giao với **`[x,x]`** dưới quy ước khoảng đóng.

### Bài 24. Chi phí cập nhật `maxHigh`

Một nút có `high=15`, cây trái `maxHigh=18`, cây phải `maxHigh=30`. Tính lại metadata tại nút mất thời gian bao nhiêu và cho giá trị gì?

**Đáp án:** **`O(1)`** thời gian vì chỉ so sánh ba giá trị; `maxHigh=30`. Thời gian cập nhật toàn cây còn phụ thuộc số tổ tiên cần tính lại.

### Bài 25. BST không cân bằng

Nếu ta thêm `maxHigh` vào một BST suy biến có chiều cao `h=n-1`, có bảo đảm truy vấn một khoảng giao `O(\log n)` không?

**Đáp án:** **Không.** Thuật toán đi một đường dài tối đa `O(h+1)=O(n)`. Metadata không tự cân bằng cây; cần AVL/Red–Black hoặc một cây nền thích hợp.

### Bài 26. Chọn cấu trúc theo bài toán

Một ứng dụng phải thường xuyên thêm/xóa các cuộc hẹn và hỏi “có cuộc hẹn nào trùng với khoảng mới không?” Nên cân nhắc cấu trúc nào?

**Đáp án:** **Interval tree tự cân bằng** phù hợp vì chèn/xóa và tìm một giao theo khoảng có chặn trên **`O(\log n)`**. Phải quyết định rõ cuộc hẹn dùng khoảng đóng hay nửa mở để áp dụng đúng quy tắc chạm đầu mút.

### Bài 27. Validator cần tính lại gì?

Một hàm kiểm tra cho AVL interval tree nên xác minh những bất biến nào?

**Đáp án:** Liên kết tạo cây hợp lệ không chu trình/nút dùng chung, khóa `(low,uid)` theo thứ tự BST ở mọi cây con, `low≤high`, UID duy nhất, `height` và `maxHigh` bằng giá trị **tính lại độc lập** từ con, và chênh chiều cao AVL không quá `1`.

### Bài 28. Thay đổi đầu trái

Một khoảng đã lưu là `[10,20]` được đổi thành `[30,40]`. Có thể chỉ gán `node.low=30` trong BST theo `low` không?

**Đáp án:** **Không.** Vị trí của nút theo khóa BST có thể không còn hợp lệ. Cần xóa/chèn lại hoặc dùng API cập nhật đã thiết kế để tái định vị và duy trì metadata.

### Bài 29. Khi nào tuyến tính tốt hơn?

Chỉ có ba khoảng cố định và mỗi ngày hỏi một truy vấn giao. Có nhất thiết phải triển khai interval tree không?

**Đáp án:** **Không.** Duyệt tuyến tính `O(n)` rất đơn giản và có thể thực tế hơn với dữ liệu nhỏ, truy vấn hiếm. Chi phí bảo trì cây, ID, cân bằng và metadata có thể không đáng so với lợi ích.

### Bài 30. Vì sao không thay bằng segment tree một cách máy móc?

Một hệ thống cần tìm **đúng bản ghi khoảng** giao với truy vấn và xóa theo UID, không chỉ tính tổng giá trị trên một dãy chỉ số. Tại sao cần cân nhắc mô hình cấu trúc?

**Đáp án:** Cây khoảng theo BST lưu trực tiếp **các đối tượng khoảng và ID**, cung cấp truy vấn giao và xóa đúng bản ghi. Segment tree thường tổng hợp giá trị trên **miền chỉ số/khoảng tọa độ** và có API khác; muốn dùng nó cho các bản ghi khoảng động phải thiết kế thêm quy tắc lưu và truy xuất đối tượng.

## 19. Tổng kết

**Cây khoảng (interval tree)** trong bài là một **BST tăng cường**, lưu mỗi khoảng đóng `[low,high]` ở một nút, sắp theo `(low,uid)` và duy trì:

\[
\boxed{
maxHigh(u)=\max\bigl(
u.high,\,
maxHigh(u.left),\,
maxHigh(u.right)
\bigr)
}
\]

Trường `maxHigh` giúp **loại toàn bộ cây con** nếu đầu phải lớn nhất của chúng vẫn nhỏ hơn đầu trái truy vấn. Kết hợp với **bất biến BST theo đầu trái**, thuật toán `INTERVAL-SEARCH` có thể **tìm một khoảng giao bằng một đường đi**; trên AVL, thời gian là **`O(\log(n+1))`**.

Khi cần **liệt kê tất cả khoảng giao**, thuật toán phải xét nhiều nhánh chưa thể loại bỏ; chặn trên của cách duyệt minh họa là **`O(n)`** trường hợp xấu nhất, với thêm `O(k)` bộ nhớ để lưu `k` kết quả. Không nên đánh đồng truy vấn **một kết quả** với truy vấn **tất cả kết quả**.

Để cập nhật động đúng, mọi phép **chèn, xóa và xoay** phải bảo trì cả thứ tự BST, cân bằng AVL và `maxHigh` **từ dưới lên**. Xóa nút có hai con cần giữ nguyên bộ thông tin `low,high,uid` của bản ghi kế nhiệm; các khoảng trùng đầu mút vẫn phải được phân biệt. Cuối cùng, cách hiểu **giao ở đầu mút** phải nhất quán với loại khoảng mà ứng dụng dùng.

Nguyên tắc cốt lõi của cây tăng cường không chỉ là “thêm một trường vào nút”, mà là **chọn thông tin đủ để cắt nhánh, chứng minh điều kiện cắt nhánh không bỏ sót đáp án, rồi duy trì thông tin ấy sau mọi thay đổi cấu trúc**. Đó là cơ sở để chọn interval tree phù hợp với các bài toán tìm giao động, đồng thời hiểu rõ giới hạn thời gian và bộ nhớ của từng loại truy vấn.
