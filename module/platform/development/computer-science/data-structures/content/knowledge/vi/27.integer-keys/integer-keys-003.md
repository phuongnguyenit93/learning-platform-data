# Tập hợp thưa (sparse set) và ánh xạ hai chiều giữa phần tử với vị trí

Khi quản lý các khóa số nguyên trong một miền hữu hạn, có hai yêu cầu tưởng như mâu thuẫn: **kiểm tra một khóa có mặt thật nhanh** và **duyệt chỉ những khóa đang có mà không quét hết miền**. Một mảng địa chỉ trực tiếp cho phép kiểm tra khóa bằng một lần truy cập, nhưng để liệt kê toàn bộ phần tử có thể phải xem cả những ô trống. Một danh sách đặc chỉ chứa các phần tử hiện có thì duyệt nhanh, nhưng tìm một khóa bất kỳ có thể phải dò từng phần tử.

**Sparse set** (tập hợp thưa dùng hai mảng `sparse/dense`) kết hợp hai ưu điểm đó: giữ các phần tử hiện có trong mảng **`dense` liên tiếp**, đồng thời dùng mảng **`sparse` để tra vị trí của một khóa trong `dense`**. Với khóa nguyên trong miền đã biết, cấu trúc hỗ trợ kiểm tra thuộc tập, thêm và xóa rất hiệu quả; đặc biệt, xóa có thể dùng thủ thuật **đổi với phần tử cuối** (*swap-with-last*) mà không phải dịch cả dãy.

Ví dụ: một trò chơi quản lý tối đa 100.000 mã thực thể, nhưng tại một thời điểm chỉ có 300 thực thể đang hoạt động. Ta muốn kiểm tra `id=712` có hoạt động không, đồng thời mỗi khung hình chỉ lặp qua **300 thực thể hiện có**, không đi qua 100.000 mã có thể có. Sparse set là một lựa chọn đáng cân nhắc.

Điều cần nhớ ngay từ đầu: tên gọi **“thưa”** mô tả số phần tử đang lưu và cách **duyệt mảng đặc**, **không có nghĩa bản cài đặt hai mảng cổ điển chỉ dùng O(n) bộ nhớ**. Mảng `sparse` vẫn thường được cấp phát theo **kích thước miền khóa `U`**.

## 1. Mô hình khóa và các phép toán cần hỗ trợ

Giả sử tập khóa hợp lệ nằm trong đoạn nguyên đóng:

\[
\mathcal{U}=[a,b]\cap\mathbb Z,\qquad U=b-a+1.
\]

Ta duy trì một tập `S` gồm `n` khóa **phân biệt** từ miền này, do đó:

\[
0\le n=|S|\le U.
\]

Các thao tác:

| Phép toán | Ý nghĩa |
| --- | --- |
| `contains(x)` | Có khóa `x` trong tập hay không? |
| `add(x)` | Thêm `x` nếu chưa có |
| `remove(x)` | Xóa `x` nếu có |
| `size()` | Số phần tử đang có |
| `getAt(i)` | Lấy phần tử đang nằm ở vị trí đặc `i` |
| `clear()` | Làm tập rỗng |
| `elements()` | Liệt kê các khóa đang lưu |

Ở bài này, `add` và `remove` trả **boolean**: `true` khi tập thực sự thay đổi, `false` nếu thêm trùng hoặc xóa khóa vắng. Khóa ngoài đoạn `[a,b]` bị từ chối theo hợp đồng API của ví dụ Java.

### Phân biệt `U`, `n` và `capacity`

- `U`: tổng số **giá trị khóa có thể có** trong miền, ví dụ 0–99 cho `U=100`.
- `n`: số **khóa đang có mặt**, ví dụ `n=4`.
- `capacity` của `dense`: số ô đã cấp phát cho mảng đặc; có thể lớn hơn `n` và **không nhất thiết bằng `U`**.

Trong biến thể cơ bản, `sparse` có `U` vị trí; `dense` có thể cấp phát `U` vị trí ngay từ đầu hoặc tăng dần khi thêm khóa. Với cách tăng dần, chi phí mở rộng cần được tính riêng.

## 2. Hai mảng `dense` và `sparse`

Với miền `0..9`, giả sử tập hiện có:

\[
S=\{3,5,6,8\}.
\]

Thứ tự phần tử trong `dense` **không bắt buộc là thứ tự tăng của khóa**. Ví dụ:

```text
size = 4

dense:
       index:   0    1    2    3      4    5    ...
              +----+----+----+----+-----+-----+
       value: |  3 |  8 |  5 |  6 |  ?  |  ?  |
              +----+----+----+----+-----+-----+
               <---- vùng đang hoạt động ---->

sparse (chỉ đánh dấu các giá trị quan trọng):
       key:       0  1  2  3  4  5  6  7  8  9
       sparse:    ?  ?  ?  0  ?  2  3  ?  1  ?
                            |     |  |     |
                            v     v  v     v
                         dense[0] [2][3] [1]
```

Ở đây:

\[
\begin{aligned}
dense[0]&=3,&sparse[3]&=0,\\
dense[1]&=8,&sparse[8]&=1,\\
dense[2]&=5,&sparse[5]&=2,\\
dense[3]&=6,&sparse[6]&=3.
\end{aligned}
\]

**Mảng đặc (dense):** ở các chỉ số `0..n-1`, mỗi ô chứa **một phần tử đang thuộc tập**. Vì phần này liên tiếp, duyệt tập mất O(n), không cần xem các khóa vắng mặt.

**Mảng thưa (sparse):** ở vị trí tương ứng với một khóa `x`, nó giữ **chỉ số của `x` trong `dense`**, nếu khóa đang có mặt.

Hai hướng ánh xạ:

```text
     khóa x ----sparse[x]----> vị trí i
        ^                        |
        |                        |
        +------dense[i]----------+

Khi x có mặt:
    dense[sparse[x]] == x
```

Đây là một **song ánh giữa các khóa đang hoạt động và các vị trí đặc `0..n-1`**, chứ không phải song ánh giữa toàn bộ `U` khóa có thể có với các vị trí trong `dense`.

### Khóa không thuộc tập thì `sparse[x]` chứa gì?

Trong một triển khai phổ biến, giá trị ở `sparse[x]` khi `x` **không có mặt** được phép **cũ, không có ý nghĩa hoặc là giá trị khởi tạo mặc định**. Không được suy rằng chỉ cần đọc `sparse[x]` là biết ngay `x` tồn tại.

Điều đó dẫn đến phép kiểm tra membership đặc trưng của sparse set.

## 3. Bất biến cốt lõi và cách kiểm tra thuộc tập

Gọi `n=size`. Các bất biến của mô hình khóa duy nhất là:

1. `0\le n\le U` và `0\le n\le dense.capacity`.
2. **Vùng `dense[0..n-1]` chứa chính xác `n` khóa phân biệt, hợp lệ**.
3. Với mọi `i` đang hoạt động:

   \[
   \boxed{sparse[dense[i]]=i.}
   \]

4. Với mọi khóa `x` đang có mặt, `p=sparse[x]` phải thuộc `[0,n-1]` và `dense[p]=x`.
5. Không có giả định bắt buộc về nội dung của `dense[n..capacity-1]` hoặc `sparse[x]` đối với khóa vắng mặt.

Do đó:

\[
\boxed{
contains(x)\iff
0\le p=sparse[x]<n\ \land\ dense[p]=x
}
\]

với `x` đã được xác nhận thuộc miền.

### Tại sao cần cả hai kiểm tra?

Giả sử `sparse[7]=1` nhưng `dense[1]=8`, trong khi `size=4`. Nếu chỉ hỏi:

```text
sparse[7] < size     -> 1 < 4 -> true
```

ta sẽ **kết luận sai** rằng 7 có trong tập. Điều kiện:

```text
dense[sparse[7]] == 7
```

sẽ trả `false` vì `dense[1]=8`.

Tương tự, nếu `sparse[7]=9` nhưng `size=4` thì **không được đọc `dense[9]`** trước khi kiểm tra giới hạn; vị trí ấy có thể nằm ngoài mảng hoặc ngoài vùng đang hoạt động.

Mã giả với khóa chuẩn hóa `0..U-1`:

```text
contains(x):
    require 0 <= x < U
    p = sparse[x]
    return 0 <= p AND p < size AND dense[p] == x
```

Ở Java, mảng `int[]` khởi tạo các ô bằng 0. Với tập rỗng `size=0`, phép kiểm tra trả `false` cho **mọi khóa**, kể cả `x=0`, vì không có vị trí hoạt động. Vì vậy không cần dùng `-1` để khởi tạo toàn mảng `sparse` trong biến thể này.

### Chứng minh điều kiện membership

**Nếu `x` thuộc tập:** vì mỗi phần tử có đúng một vị trí `i` trong `dense[0..n-1]` và bất biến ánh xạ ngược `sparse[dense[i]]=i`, ta có `p=sparse[x]=i<n`, và `dense[p]=x`. Hàm trả `true`.

**Nếu hàm trả `true`:** `p<n` và `dense[p]=x`. Theo bất biến vùng hoạt động, mọi giá trị ở `dense[0..n-1]` đều là phần tử thuộc tập, nên `x` thuộc tập.

Không cần xóa toàn bộ mảng `sparse` sau từng thao tác để giữ được chứng minh này.

## 4. Thêm phần tử: chèn cuối mảng đặc

Để thêm `x`:

1. Kiểm tra `x` thuộc miền khóa.
2. Nếu `contains(x)` đúng, trả `false`: không thêm trùng.
3. Nếu `dense` chưa đủ chỗ, mở rộng dung lượng.
4. Đặt `dense[size]=x`.
5. Đặt `sparse[x]=size`.
6. Tăng `size`, trả `true`.

```text
add(x):
    require x belongs to universe
    if contains(x):
        return false
    ensureDenseCapacity(size + 1)
    dense[size] = x
    sparse[x] = size
    size = size + 1
    return true
```

Ví dụ trước khi thêm 4:

```text
size = 4
dense = [3, 8, 5, 6 | ...]

add(4):
    dense[4] = 4
    sparse[4] = 4
    size = 5

dense = [3, 8, 5, 6, 4 | ...]
```

Không có thao tác dịch các phần tử `3,8,5,6`, vì cấu trúc **không duy trì thứ tự sắp theo khóa**.

### Độ phức tạp khi `dense` được cấp phát sẵn

Nếu `dense` có sẵn `U` ô, kiểm tra tồn tại và ghi hai mảng chỉ gồm một số thao tác hằng số, nên `add` đạt **O(1) trường hợp xấu nhất** sau khi bảng được khởi tạo, với mô hình Word-RAM.

Nếu `dense` **tăng dung lượng bằng nhân đôi** như ví dụ Java, phần lớn lần thêm là O(1), nhưng một lần tăng dung lượng có thể phải sao chép O(n) phần tử. Khi đó:

- `add`: **O(1) khấu hao** (*amortized*), **O(n) trường hợp xấu nhất** cho một lần thêm gây resize.
- `contains`: **O(1) worst-case** sau khi mảng đã tồn tại.
- `remove`: **O(1) worst-case** theo mô hình của bài, vì không thu nhỏ `dense` khi xóa.

Không nên tuyên bố `add` luôn O(1) worst-case khi có bước sao chép mảng lúc resize.

## 5. Xóa phần tử: đổi với phần tử cuối (`swap-with-last`)

Nếu `dense` là một danh sách có thứ tự cần giữ, xóa ở giữa sẽ phải dịch phần tử phía sau. Sparse set **không cần giữ thứ tự**, nên ta lấp lỗ trống bằng **phần tử đang ở cuối vùng hoạt động**.

Xét:

```text
size = 4
index:      0   1   2   3
dense:     [3,  8,  5,  6]
                 ^
               xóa 8

sparse[8] = 1
sparse[6] = 3
```

Các bước `remove(8)`:

1. Xác nhận 8 đang có mặt; lấy `p=sparse[8]=1`.
2. Đọc khóa cuối `last=dense[size-1]=6`.
3. Ghi `dense[p]=last`, tức `dense[1]=6`.
4. Cập nhật `sparse[last]=p`, tức `sparse[6]=1`.
5. Giảm `size` từ 4 xuống 3.
6. Tùy cài đặt, có thể dọn ô `dense[3]` cũ về giá trị mặc định.

```text
Trước:                  Sau:

index: 0  1  2  3        index: 0  1  2    (size=3)
       [3, 8, 5, 6]             [3, 6, 5]
           ^     |                  ^
           +-----+        last=6 chuyển về vị trí 1

sparse[6] từ 3 thành 1
sparse[8] có thể vẫn bằng 1 (stale)
```

Giá trị `sparse[8]=1` **không cần xóa** để phép `contains(8)` chính xác:

```text
p = sparse[8] = 1
p < size      = 1 < 3             -> true
dense[p] == 8 = dense[1] == 8     -> 6 == 8 -> false
```

Đây là một ưu điểm quan trọng: **sửa đúng hai ánh xạ còn hoạt động, không cần quét hoặc khởi tạo lại cả miền**.

### Mã giả

```text
remove(x):
    require x belongs to universe
    if not contains(x):
        return false

    p = sparse[x]
    lastIndex = size - 1
    last = dense[lastIndex]

    if p != lastIndex:
        dense[p] = last
        sparse[last] = p

    size = size - 1
    optionally clear dense[size]
    return true
```

**Trường hợp xóa phần tử cuối:** khi `p=lastIndex`, không có phần tử khác cần di chuyển; chỉ giảm `size`. Khóa vừa xóa mất khỏi vùng hoạt động, kể cả khi `sparse[x]` còn giữ chỉ số cũ.

### Chứng minh phép xóa không làm mất khóa khác

Trước xóa, vùng hoạt động chứa `n` phần tử phân biệt. Xóa `x` tại `p`:

- Nếu `p=n-1`, `x` là phần tử cuối; giảm `size` còn `n-1` và mọi phần tử khác giữ nguyên.
- Nếu `p<n-1`, giá trị `last=dense[n-1]` khác `x` vì tập không có khóa trùng. Di chuyển `last` từ vị trí cuối về `p` rồi đặt `sparse[last]=p`, nên `last` **vẫn xuất hiện đúng một lần** trong vùng mới. Các vị trí khác không thay đổi.

Vì vậy sau thao tác:

\[
S_{\text{new}}=S_{\text{old}}\setminus\{x\},
\qquad
size_{\text{new}}=size_{\text{old}}-1.
\]

Một lần xóa chỉ cần vài truy cập mảng: **O(1) worst-case** khi không phải làm công việc thu nhỏ hoặc cấu trúc phụ khác.

## 6. Vì sao vị trí `dense` không ổn định?

Sparse set **ưu tiên khả năng duyệt đặc và xóa nhanh**, không giữ nguyên vị trí của các phần tử khác.

Trước `remove(8)`:

```text
dense[3] = 6
```

Sau `remove(8)`:

```text
dense[1] = 6
```

**Phần tử 6 vẫn có mặt, nhưng vị trí đổi từ 3 sang 1.** Nếu một thành phần bên ngoài đã lưu `positionOf(6)=3` rồi dùng lại sau khi xóa khóa khác, nó có thể truy cập vào phần tử sai hoặc vùng không còn hoạt động.

Vì vậy:

- **Khóa số nguyên `x`** là định danh dùng để hỏi membership.
- **Vị trí `i` trong `dense`** là chỉ số nội bộ có thể thay đổi sau `remove`, `clear` hoặc tái cấu trúc.
- Không cung cấp một vị trí đặc như **handle ổn định** trừ khi có cơ chế cập nhật hoặc phiên bản hóa bổ sung.

Đây là đánh đổi khác với danh sách có thứ tự được duy trì bằng phép dịch mảng. Nếu ứng dụng bắt buộc giữ **thứ tự chèn**, **thứ tự tăng theo khóa** hoặc **chỉ số ổn định**, cần cấu trúc khác hoặc một lớp gián tiếp.

### Vòng lặp vừa duyệt vừa xóa

Xóa một phần tử có thể đưa phần tử cuối về vị trí đang xét. Nếu ngay sau đó tăng `i`, ta sẽ **bỏ qua** phần tử vừa được chuyển tới.

**Cách dễ sai:**

```text
for i = 0 to size-1:
    if shouldRemove(dense[i]):
        remove(dense[i])
    # i tăng dù phần tử mới đã được chuyển vào i
```

**Cách đúng cho việc duyệt và xóa tại chỗ:**

```text
i = 0
while i < size:
    x = dense[i]
    if shouldRemove(x):
        remove(x)
        # Không tăng i, phải xét phần tử vừa chuyển vào i.
    else:
        i++
```

Ví dụ nếu muốn xóa mọi khóa chẵn, `dense=[5,2,8,3]`: xóa 2 tại vị trí 1 đưa 3 vào vị trí 1. Duyệt lại vị trí 1 rồi tiếp tục là an toàn; không được mặc định phần tử tại vị trí cũ vẫn là 2.

## 7. Làm rỗng tập trong O(1) bằng cách đặt `size=0`

Nếu membership chỉ dựa vào hai điều kiện `p<size` và `dense[p]==x`, một phép làm rỗng rất đơn giản là:

```text
clear():
    size = 0
```

Sau đó, với mọi khóa hợp lệ:

```text
p = sparse[x]                # Có thể là một chỉ số cũ.
p < size == p < 0            # Luôn false nếu p không âm.
contains(x) == false
```

Ta **không cần đặt lại `U` ô của `sparse`** và cũng không cần đi qua toàn bộ `dense` để kết luận tập rỗng. Do vậy, `clear()` có thể là **O(1)** trong biến thể này.

### Tại sao thêm lại sau `clear` vẫn an toàn?

Trước khi làm rỗng:

```text
dense = [3, 8, 5, 6] , size=4
sparse[8]=1
```

Sau `clear()`:

```text
size=0
sparse[8] vẫn có thể bằng 1
```

Thêm 7:

```text
dense[0]=7
sparse[7]=0
size=1
```

Kiểm tra 8: `sparse[8]=1` nhưng `1<size` sai, nên không có. Nếu `sparse[3]=0` thì điều kiện so sánh `dense[0]==3` cũng sai vì `dense[0]=7`. Do đó các chỉ số cũ không gây **dương tính giả**.

### Giới hạn của `clear` chỉ đổi `size`

Cách này **chỉ làm rỗng về mặt logic**. Nếu `dense` giữ tham chiếu tới đối tượng, các ô cũ vẫn có thể giữ đối tượng sống trong bộ nhớ, gây giữ bộ nhớ không mong muốn. Khi đó cần xóa tham chiếu thật hoặc dùng một cách bố trí khác; thời gian dọn tham chiếu có thể O(n).

Nếu các giá trị mang thông tin nhạy cảm, đặt `size=0` cũng **không phải xóa dữ liệu an toàn khỏi bộ nhớ**. Nếu cấu trúc yêu cầu bảo mật hoặc giải phóng tài nguyên, phải tính chi phí dọn thật chứ không quảng cáo mọi `clear` đều O(1).

## 8. Ánh xạ miền khóa không bắt đầu ở 0

Trong thực tế, khóa có thể nằm trong `[-5,14]` thay vì `[0,19]`. Ta dùng **offset** để chuẩn hóa:

\[
offset(x)=x-a,
\qquad a\le x\le b.
\]

Với miền `[-5,14]`:

\[
U=14-(-5)+1=20.
\]

| Khóa `x` | `offset(x)` | Ý nghĩa |
| ---: | ---: | --- |
| -5 | 0 | Khóa nhỏ nhất |
| -2 | 3 | Khóa âm |
| 0 | 5 | Khóa 0 |
| 7 | 12 | Khóa dương |
| 14 | 19 | Khóa lớn nhất |

Mảng `dense` vẫn lưu **giá trị khóa nguyên gốc**, ví dụ `-2` hoặc `7`, nhưng mảng `sparse` được truy cập qua **`offset(x)`**:

```text
contains(x):
    o = x - minKey
    p = sparse[o]
    return p < size && dense[p] == x

add(x):
    o = x - minKey
    dense[size] = x
    sparse[o] = size
    size++
```

Khi chuyển phần tử cuối `last` về vị trí `p` lúc xóa, phải cập nhật:

```text
sparse[offset(last)] = p
```

**Không dùng `sparse[last]` trực tiếp** nếu `last` có thể là khóa âm hoặc miền bắt đầu ở giá trị khác 0.

### Cẩn thận tràn số khi tính offset

Với khóa kiểu Java `int`, đoạn từ `Integer.MIN_VALUE` tới `Integer.MAX_VALUE` có `2^{32}` khóa có thể có; `U` **không vừa trong `int` có dấu**. Trước khi trừ:

```java
long universe = (long) maxKey - (long) minKey + 1L;
long offset = (long) key - (long) minKey;
```

Chỉ ép `offset` sang `int` sau khi đã kiểm tra:

- Khóa nằm trong miền.
- Miền `U` không vượt quá khả năng biểu diễn chỉ số mảng.
- Ngân sách bộ nhớ cho `sparse` và `dense` phù hợp.

Một số nguyên có thể biểu diễn được trong kiểu `long` **không có nghĩa máy có đủ RAM để cấp phát `sparse[U]`**.

## 9. Phân tích thời gian và bộ nhớ

Xét biến thể dùng một `int[U]` cho `sparse` và một mảng `dense` tăng dung lượng theo nhân đôi.

| Thao tác | Thời gian | Giải thích |
| --- | --- | --- |
| `contains(x)` | **O(1) worst-case** | Một lần đọc `sparse`, kiểm tra biên và một lần đọc `dense` |
| `add(x)` khi `dense` còn chỗ | **O(1)** | Ghi vào cuối mảng đặc và cập nhật ánh xạ |
| `add(x)` có thể tăng dung lượng | **O(1) khấu hao; O(n) worst-case** | Lúc resize có thể sao chép `n` mục |
| `remove(x)` | **O(1) worst-case** | Đổi với phần tử cuối, không dịch dãy và không shrink |
| `size()` | **O(1)** | Đọc biến đếm |
| `getAt(i)` | **O(1)** | Đọc phần tử tại vị trí đặc hợp lệ |
| `clear()` logic | **O(1)** | Đặt `size=0`, không quét các mảng |
| Duyệt tất cả `n` phần tử | **O(n)** | Chỉ đọc `dense[0..n-1]` |
| Kiểm tra bất biến trên các mục hoạt động | **O(n)** trung bình với tập kiểm tra băm, hoặc O(n) nếu dùng mảng đánh dấu phù hợp | Duyệt và xác minh các vị trí đặc |
| Khởi tạo `sparse` | **O(U)** trong mô hình mảng đã khởi tạo | Cần cấp phát/chuẩn bị các ô cho toàn miền |

Chi phí bộ nhớ:

\[
\boxed{S=O(U+\operatorname{capacity}(dense))=O(U+n)}
\]

với `dense` được quản lý để sức chứa không lớn hơn `U` và khi `n>0` thì tăng theo cấp số nhân. Vì `n\le U`, có thể viết **O(U)** theo cận trên tổng; nhưng cách viết `O(U+n)` làm rõ nguồn gốc hai phần bộ nhớ.

### “Sparse” không đồng nghĩa O(n) bộ nhớ

Ví dụ `U=1\,000\,000` và `n=30`:

- `sparse` kiểu `int[U]` chiếm **4.000.000 byte payload**.
- `dense` chỉ cần vài chục đến vài chục ô dự trữ, có thể rất nhỏ.
- Tổng vẫn bị chi phối bởi **`sparse`**, dù chỉ có 30 phần tử.

Tên gọi “sparse set” nói về cách **lưu/duyệt tập thưa trong phần `dense`** và ánh xạ vị trí, không cam kết bộ nhớ tỷ lệ với số phần tử đang có. Nếu `U` khổng lồ và `n` rất nhỏ, bảng băm hoặc cấu trúc sparse phân trang có thể tiết kiệm bộ nhớ hơn.

### So sánh duyệt toàn tập

| Cấu trúc | Tra thuộc tập | Liệt kê `n` khóa đang có | Bộ nhớ chính |
| --- | --- | --- | --- |
| Mảng boolean địa chỉ trực tiếp | O(1) | O(U) nếu quét mảng | O(U) ô |
| Bitset dày đặc | O(1) theo từ máy | Thường phụ thuộc số từ cần quét và `n` | O(U) bit |
| **Sparse set hai mảng** | **O(1)** | **O(n)** | O(U+n) ô |
| Bảng băm | O(1) trung bình/kỳ vọng | O(n+capacity) khi duyệt cả bucket, hoặc theo cách cài | O(n) kỳ vọng theo mức tải |
| Cây cân bằng | O(log n) | O(n) bằng in-order | O(n) nút |

Sparse set thường có tính cục bộ bộ nhớ tốt cho vòng lặp duyệt `dense`. Tuy nhiên, membership vẫn có thể truy cập một ô `sparse` ở vị trí xa trong RAM; **O(1) về số thao tác** không bảo đảm một độ trễ CPU thực tế cố định vì cache miss.

## 10. Ví dụ diễn tiến: thêm, xóa, thêm lại và làm rỗng

Xét miền `[-2,8]`; chỉ số vào `sparse` được tính bằng `x-(-2)=x+2`.

### Trạng thái sau bốn lần thêm

Lần lượt:

```text
add(4), add(-2), add(7), add(0)
```

Ta có:

```text
size = 4
dense index:   0    1    2    3
dense value:  [4,  -2,   7,   0]

sparse[offset(4)]  = sparse[6] = 0
sparse[offset(-2)] = sparse[0] = 1
sparse[offset(7)]  = sparse[9] = 2
sparse[offset(0)]  = sparse[2] = 3
```

### Xóa khóa ở giữa

`remove(-2)`: vị trí của `-2` là 1, phần tử cuối là `0` ở vị trí 3. Di chuyển `0` vào vị trí 1, đổi `sparse[offset(0)]` từ 3 thành 1:

```text
size = 3
dense = [4, 0, 7]
sparse[2] = 1

sparse[0] của -2 có thể vẫn là 1
contains(-2) -> dense[1] == -2 ? 0 == -2 -> false
```

### Thêm khóa 6 rồi xóa 4

`add(6)` gắn vào cuối:

```text
dense = [4, 0, 7, 6], size=4
```

`remove(4)`: khóa 4 đang ở vị trí 0, chuyển khóa 6 từ vị trí cuối về vị trí 0:

```text
dense = [6, 0, 7], size=3
sparse[offset(6)] = 0
```

Tập hiện có là `\{0,6,7\}`; **thứ tự dense `[6,0,7]` không được sắp**. Một truy vấn muốn kết quả tăng theo khóa phải **sắp riêng** hoặc chọn cấu trúc duy trì thứ tự.

### Làm rỗng và thêm lại

`clear()` đặt `size=0`, sau đó `add(-2)` ghi `dense[0]=-2` và `sparse[0]=0`. Mọi khóa khác không còn thuộc tập dù các ô `sparse` vẫn có thể lưu chỉ số cũ.

Đây là tình huống thử quan trọng: nếu chỉ kiểm tra `sparse[x]<size` mà quên `dense[sparse[x]]==x`, trạng thái sau clear/insert mới có thể gây **dương tính giả**.

## 11. Java hoàn chỉnh: `IntSparseSet` có miền hữu hạn

Chương trình sau thực hiện đầy đủ:

- Khóa `int` trong miền đóng `[minKey,maxKey]`, kể cả số âm.
- `sparse` có một ô cho mỗi khóa hợp lệ; `dense` mở rộng theo nhân đôi khi cần.
- `contains` sử dụng **cả giới hạn `p<size` và phép đối chiếu `dense[p]==key`**.
- `add` không thêm trùng, `remove` dùng swap-with-last.
- `clear` chỉ đặt `size=0`.
- `getAt` và `elements` cho phép duyệt phần đặc.
- `rangeSorted` lọc những phần tử trong khoảng rồi sắp **bản sao kết quả**, không đổi thứ tự nội bộ.
- `verify` kiểm tra tính một-một của ánh xạ cho những phần tử **đang hoạt động**.

Để tránh cấp phát quá lớn một cách vô ý, constructor nhận `maxUniverse`: ngân sách **số khóa có thể có** của ứng dụng minh họa. Đây không phải giới hạn lý thuyết của sparse set.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class SparseSetIntegerKeysDemo {

    static final class IntSparseSet {
        private final int minKey;
        private final int maxKey;
        private final int[] sparse;
        private int[] dense;
        private int size;

        IntSparseSet(int minKey, int maxKey, int maxUniverse) {
            if (minKey > maxKey || maxUniverse <= 0) {
                throw new IllegalArgumentException("Invalid universe");
            }
            long universe =
                (long) maxKey - (long) minKey + 1L;
            if (universe > Integer.MAX_VALUE
                    || universe > maxUniverse) {
                throw new IllegalArgumentException(
                    "Universe exceeds index or memory budget");
            }

            this.minKey = minKey;
            this.maxKey = maxKey;
            this.sparse = new int[(int) universe];
            // Initially compact; capacity grows only when needed.
            this.dense = new int[Math.min(4, sparse.length)];
        }

        int size() {
            return size;
        }

        int universeSize() {
            return sparse.length;
        }

        private int offset(int key) {
            if (key < minKey || key > maxKey) {
                throw new IllegalArgumentException(
                    "Key outside universe: " + key);
            }
            // Widen before subtracting to avoid int overflow.
            return (int) ((long) key - (long) minKey);
        }

        boolean contains(int key) {
            int p = sparse[offset(key)];
            return p >= 0 && p < size && dense[p] == key;
        }

        private void ensureRoomForOne() {
            if (size < dense.length) {
                return;
            }
            if (size >= sparse.length) {
                throw new IllegalStateException("Universe is full");
            }

            long doubled = 2L * dense.length;
            long desired = Math.max(
                doubled, (long) dense.length + 1L);
            int newCapacity = (int) Math.min(
                (long) sparse.length, desired);
            dense = Arrays.copyOf(dense, newCapacity);
        }

        // True for a new key; false when key was already present.
        boolean add(int key) {
            int o = offset(key);
            int p = sparse[o];
            if (p >= 0 && p < size && dense[p] == key) {
                return false;
            }

            ensureRoomForOne();
            dense[size] = key;
            sparse[o] = size;
            size++;
            return true;
        }

        // Uses swap-with-last; order of dense is not stable.
        boolean remove(int key) {
            int o = offset(key);
            int p = sparse[o];
            if (p < 0 || p >= size || dense[p] != key) {
                return false;
            }

            int lastIndex = size - 1;
            int last = dense[lastIndex];
            if (p != lastIndex) {
                dense[p] = last;
                sparse[offset(last)] = p;
            }
            dense[lastIndex] = 0; // Optional hygiene, not sentinel.
            size--;
            // sparse[o] is deliberately left stale; contains is safe.
            return true;
        }

        // Logical clear: old sparse indices can remain unchanged.
        void clear() {
            size = 0;
        }

        int getAt(int index) {
            if (index < 0 || index >= size) {
                throw new IndexOutOfBoundsException(
                    "Dense index: " + index);
            }
            return dense[index];
        }

        List<Integer> elements() {
            List<Integer> result = new ArrayList<>(size);
            for (int i = 0; i < size; i++) {
                result.add(dense[i]);
            }
            return result;
        }

        // Filtering is O(n); sorting r hits is O(r log r).
        List<Integer> rangeSorted(int from, int to) {
            List<Integer> result = new ArrayList<>();
            if (from > to) {
                return result;
            }
            for (int i = 0; i < size; i++) {
                int key = dense[i];
                if (from <= key && key <= to) {
                    result.add(key);
                }
            }
            Collections.sort(result);
            return result;
        }

        // For tests/debug: validate active inverse mapping.
        void verify() {
            if (size < 0 || size > dense.length
                    || size > sparse.length) {
                throw new IllegalStateException("Invalid size");
            }
            Set<Integer> seen = new HashSet<>();
            for (int i = 0; i < size; i++) {
                int key = dense[i];
                if (key < minKey || key > maxKey) {
                    throw new IllegalStateException(
                        "Active key outside universe");
                }
                if (!seen.add(key)) {
                    throw new IllegalStateException(
                        "Duplicate active key: " + key);
                }
                if (sparse[offset(key)] != i) {
                    throw new IllegalStateException(
                        "Broken reverse mapping for " + key);
                }
            }
            // Absent keys may have stale sparse values: allowed.
        }
    }

    public static void main(String[] args) {
        IntSparseSet set = new IntSparseSet(-2, 8, 1000);

        for (int key : new int[] {4, -2, 7, 0}) {
            System.out.println("add(" + key + ")=" + set.add(key));
        }

        System.out.println("Initial dense: " + set.elements());
        System.out.println("remove(-2)=" + set.remove(-2));
        System.out.println("After remove: " + set.elements());
        System.out.println("contains(-2)=" + set.contains(-2));
        System.out.println("contains(0)=" + set.contains(0));

        System.out.println("add(6)=" + set.add(6));
        System.out.println("remove(4)=" + set.remove(4));
        System.out.println("Dense now: " + set.elements());
        System.out.println("getAt(1)=" + set.getAt(1));
        System.out.println("add(7) again=" + set.add(7));
        System.out.println("rangeSorted[0,7]="
            + set.rangeSorted(0, 7));
        System.out.println("size=" + set.size());
        set.verify();

        set.clear();
        System.out.println("after clear, size=" + set.size());
        System.out.println("contains(7)=" + set.contains(7));
        System.out.println("add(-2)=" + set.add(-2));
        System.out.println("after reinsert: " + set.elements());
        System.out.println("contains(6)=" + set.contains(6));
        set.verify();
        System.out.println("Invariants: OK");
    }
}
```

Đầu ra dự kiến:

```text
add(4)=true
add(-2)=true
add(7)=true
add(0)=true
Initial dense: [4, -2, 7, 0]
remove(-2)=true
After remove: [4, 0, 7]
contains(-2)=false
contains(0)=true
add(6)=true
remove(4)=true
Dense now: [6, 0, 7]
getAt(1)=0
add(7) again=false
rangeSorted[0,7]=[0, 6, 7]
size=3
after clear, size=0
contains(7)=false
add(-2)=true
after reinsert: [-2]
contains(6)=false
Invariants: OK
```

### Đọc code theo bất biến hai chiều

**`contains`:** lấy vị trí từ `sparse[offset(key)]`, kiểm tra vị trí thuộc vùng hoạt động, rồi so sánh khóa trong `dense`. Bước so sánh cuối là điều ngăn **dương tính giả từ vị trí cũ**.

**`add`:** chỉ thêm khi chưa có; ghi `dense[size]` và `sparse[offset(key)]` cùng chỉ số, nên bất biến ánh xạ ngược đúng ngay sau khi tăng `size`.

**`remove`:** lấy phần tử cuối và cập nhật đúng vị trí của nó trong `sparse`. Không cần xóa toàn bộ những giá trị cũ ở mảng thưa; `contains` bảo vệ phép kiểm tra.

**`clear`:** làm tập rỗng bằng cách đặt `size=0`. Sau khi thêm lại, những vị trí bị ghi đè được cập nhật, còn các vị trí cũ khác không gây membership sai.

**`rangeSorted`:** chỉ lọc từ mảng đặc, **không quét toàn miền `U`**. Nếu có `r` phần tử nằm trong khoảng, chi phí là O(n + r log r) để lọc rồi sắp kết quả. Nó không có lợi thế tìm một cận bằng O(log n) như cây cân bằng; phải quét toàn bộ `n` mục trước.

**`verify`:** duyệt các phần tử đang hoạt động, kiểm tra chúng nằm trong miền, không trùng và ánh xạ ngược đúng. Nó cố ý **không yêu cầu `sparse` của khóa vắng mặt phải bằng -1 hoặc 0**.

### Giới hạn của cài đặt Java

Ví dụ là một cấu trúc **trong RAM**, chỉ lưu tập khóa nguyên phân biệt. Nó không cung cấp thứ tự phần tử ổn định, con trỏ/handle ổn định, truy cập đồng thời, lưu trữ bền vững hoặc giải phóng tham chiếu đối tượng. `maxUniverse` giúp từ chối một số miền quá lớn, nhưng ngay cả khi vượt qua giới hạn đó, cấp phát mảng vẫn có thể thất bại nếu RAM/JVM không đủ.

Phần `dense` tăng theo cấp số nhân nên có thể gây **một lần chèn O(n)** khi resize; nếu ứng dụng cần thời gian chèn worst-case O(1) và biết `U` nhỏ, có thể cấp phát trước `dense[U]`, chấp nhận thêm bộ nhớ.

## 12. Kiểm thử bằng tập chuẩn (`reference oracle`)

Để kiểm chứng phép thêm/xóa, có thể so sánh sparse set với `HashSet<Integer>` hoặc `TreeSet<Integer>` trên các khóa thuộc miền.

```text
reference = empty HashSet()
testSet   = empty SparseSet([a,b])

for each operation:
    expected = reference.add(x) / reference.remove(x)
    actual   = testSet.add(x) / testSet.remove(x)
    assert expected == actual

    assert testSet.size() == reference.size()
    testSet.verify()
    assert set(testSet.elements()) == reference
```

Điều quan trọng là **không so sánh thứ tự `elements()` với thứ tự thêm** hoặc `TreeSet` đã sắp: sau xóa bằng swap-with-last, hai tập có thể **bằng nhau về phần tử nhưng khác thứ tự**. Hãy so sánh **tập khóa** thay vì danh sách nguyên xi.

### Kịch bản bắt lỗi nên có

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Tập ban đầu rỗng | `size=0`, mọi khóa hợp lệ `contains=false` |
| Thêm phần tử đầu | `sparse[x]=0`, `dense[0]=x` |
| Thêm khóa trùng | `size` và tập không đổi |
| Xóa khóa ở cuối | Chỉ giảm `size`, không cần di chuyển khóa khác |
| Xóa khóa ở giữa | Khóa cuối chuyển vào vị trí bị xóa; ánh xạ của nó được cập nhật |
| Xóa khóa vắng mặt | Không làm giảm `size` |
| Xóa rồi thêm lại cùng khóa | Không có dương tính giả hoặc bản sao trùng |
| `clear` rồi thêm khóa khác | Chỉ số `sparse` cũ không bị hiểu là membership |
| Khóa âm và khóa 0 | Offset đúng, không nhầm giá trị mặc định |
| Khóa cực trị `int` trong miền nhỏ gần min/max | Không tràn khi trừ cận |
| Dense phải mở rộng | Không mất phần tử, mọi ánh xạ còn đúng |
| Vừa duyệt vừa xóa | Không bỏ qua phần tử được chuyển vào vị trí hiện tại |

### Kiểm thử ngẫu nhiên có seed

Để phát hiện lỗi chỉ xuất hiện sau một chuỗi dài:

```text
seed = 20261128
randomly choose keys from a small bounded universe
repeat 1000 times:
    choose add/remove with fixed random seed
    update reference HashSet and sparse set
    assert operation results match
    assert active elements and size match
    validate inverse mapping
```

Miền nhỏ làm các thao tác **thêm trùng, xóa vắng mặt và thêm lại** xuất hiện thường xuyên. Khi thất bại, lưu seed và chỉ số thao tác để tái hiện. Nếu có nhiều lần xóa trong khi duyệt, phải kiểm tra đúng logic **không tăng chỉ số sau khi xóa**.

## 13. Ứng dụng: ECS, tập thực thể và vòng lặp hiệu năng cao

Một ứng dụng điển hình của sparse set là **Entity Component System (ECS)**, nơi mỗi thực thể có một ID nguyên và một số thực thể sở hữu một loại thành phần.

Ví dụ:

```text
Miền Entity ID: 0..999999
Số entity hiện có thành phần Velocity: 300

denseEntities[0..299] = các entity id có Velocity
sparse[entityId]      = vị trí trong denseEntities
velocityData[i]       = dữ liệu Velocity tương ứng ở vị trí i
```

Khi cần cập nhật vị trí cho các entity có thành phần Velocity, vòng lặp:

```text
for i = 0 .. size-1:
    id = denseEntities[i]
    velocity = velocityData[i]
    update(id, velocity)
```

chỉ đi qua **300 entity đang có thành phần**, thay vì thử một triệu ID. Nếu `velocityData` cũng được lưu đặc, truy cập liên tiếp có thể thuận lợi cho cache CPU.

### Khi xóa một entity có payload song song

Giả sử `denseEntities[p]` là ID bị xóa. Nếu lấy ID cuối `lastId` để thay vào vị trí `p`, **mọi mảng payload song song phải chuyển cùng phần tử cuối**:

```text
denseEntities[p] = lastId
velocityData[p]  = velocityData[lastIndex]
sparse[lastId]   = p
size--
```

Nếu chỉ di chuyển ID mà **không di chuyển payload**, `denseEntities[p]` sẽ trỏ tới dữ liệu vận tốc của thực thể khác. Một sparse set **chỉ lưu membership** không tự phát sinh lỗi này, nhưng khi mở rộng thành **sparse-set map / ECS component pool**, bất biến ID–payload là phần bắt buộc.

### Generation counter và ID được tái sử dụng

Sparse set trả lời tốt “ID `x` **hiện có trong pool này** không?”. Nhưng nếu hệ thống tái sử dụng một ID cũ cho thực thể mới, một người giữ ID cũ có thể nhầm nó với thực thể mới (**vấn đề ABA**). Khi cần phát hiện handle cũ, có thể dùng **ID gồm chỉ số + generation counter**, hoặc một cơ chế phiên bản khác.

Đây là yêu cầu **quản lý vòng đời thực thể**, không được giải quyết chỉ bằng công thức `dense[sparse[x]]==x` khi cùng giá trị `x` đã được tái sử dụng hợp lệ.

### Giới hạn đối với truy cập đồng thời

Nếu một luồng đang duyệt `dense` trong khi luồng khác xóa bằng swap-with-last, thứ tự và số phần tử có thể thay đổi ngay giữa vòng lặp. Cần khóa, snapshot, cơ chế hàng đợi cập nhật hoặc thiết kế đồng bộ phù hợp. Một sparse set mảng thuần **không tự an toàn khi nhiều luồng sửa/đọc đồng thời**.

## 14. Sparse set so với các cấu trúc khác

| Tiêu chí | Sparse set hai mảng | Bảng địa chỉ trực tiếp có cờ | Bitset | HashSet | Cây cân bằng |
| --- | --- | --- | --- | --- | --- |
| Miền khóa cần biết trước | Có, trong mô hình bài | Có | Có | Không bắt buộc | Không bắt buộc |
| Tra thuộc tập | O(1) worst-case | O(1) worst-case | O(1) theo từ máy | O(1) trung bình/kỳ vọng | O(log n) |
| Thêm | O(1) khấu hao nếu dense tăng | O(1) sau cấp phát | O(1) trên từ đã cấp phát | O(1) trung bình/kỳ vọng | O(log n) |
| Xóa | O(1) bằng swap-with-last | O(1) | O(1) trên từ đã cấp phát | O(1) trung bình/kỳ vọng | O(log n) |
| Duyệt toàn bộ tập | O(n) | O(U) nếu quét bảng | Phụ thuộc số từ phải quét | Thường phụ thuộc số bucket và phần tử | O(n) |
| Duy trì thứ tự tăng theo khóa | Không | Có thể quét chỉ số theo khóa, nhưng có ô trống | Có thể duyệt bit theo thứ tự | Không | Có |
| Bộ nhớ cơ bản | O(U+n) ô | O(U) ô | O(U) bit | O(n) trung bình/kỳ vọng | O(n) nút |
| Vị trí phần tử ổn định khi xóa khóa khác | **Không** | Có theo khóa–ô | Có theo bit của khóa | Không có vị trí đặc dạng mảng | Vị trí node tùy triển khai |

**Sparse set phù hợp** nếu:

- Miền `U` đủ nhỏ để cấp phát mảng chỉ số.
- Tập hiện có `n` có thể nhỏ hơn nhiều so với `U`.
- Cần kiểm tra thuộc tập, thêm/xóa nhiều lần, **duyệt tất cả phần tử hiện có**.
- Không cần giữ thứ tự trong `dense`.

**Không phù hợp trực tiếp** nếu:

- Miền ID cực lớn (ví dụ 64 bit tự do) nhưng tập chỉ có vài khóa; `sparse[U]` không thể cấp phát.
- Cần `min`, `max`, `predecessor`, `successor` hoặc `range` được tối ưu theo **thứ tự khóa**.
- Cần vị trí phần tử luôn cố định hoặc thứ tự thêm ổn định.
- Cần cập nhật đồng thời mà chưa có cơ chế đồng bộ.

### Biến thể sparse phân trang

Nếu miền rất lớn nhưng ID phân bố theo các khối, có thể lưu `sparse` theo **trang/khối được cấp phát theo nhu cầu** thay vì cấp cả `U` ô. Ví dụ dùng một bảng ánh xạ từ số khối tới mảng nhỏ các vị trí. Khi đó chi phí bộ nhớ có thể giảm với tập thưa, nhưng:

- Membership cần thêm bước tìm khối.
- Độ phức tạp và overhead phụ thuộc cấu trúc ánh xạ khối.
- Không còn đúng nguyên xi công thức bộ nhớ và thời gian của sparse set **hai mảng dày đặc** trong bài.

Không nên gọi mọi cấu trúc có tên “sparse set” là một thuật toán có cùng bảo đảm bộ nhớ O(U+n).

## 15. Các lỗi thường gặp

1. **Chỉ kiểm tra `sparse[x]<size`.** Giá trị stale có thể trỏ vào vị trí đang chứa khóa khác; phải so sánh thêm `dense[sparse[x]]==x`.
2. **Đọc `dense[p]` trước khi kiểm tra `p<size`.** Có thể đọc ngoài vùng hoạt động hoặc ngoài mảng.
3. **Cho rằng `sparse[x]` của khóa vắng luôn bằng -1.** Không đúng trong biến thể không dọn sparse khi xóa/clear.
4. **Dùng `sparse[x]` trực tiếp cho khóa âm.** Phải ánh xạ `offset(x)=x-minKey` sau khi kiểm tra miền.
5. **Quên cập nhật `sparse[last]` khi swap-with-last.** Khóa cuối sẽ có ánh xạ vị trí cũ, làm membership sai.
6. **Giảm `size` trước rồi đọc `dense[size-1]` theo công thức cũ.** Dễ lấy nhầm phần tử áp chót; hãy lưu `lastIndex=size-1` trước.
7. **Không xử lý xóa phần tử cuối.** Không cần di chuyển khóa khác; vẫn phải giảm `size` đúng một.
8. **Thêm trùng vẫn tăng `size`.** Một tập khóa duy nhất phải giữ mỗi khóa đúng một lần.
9. **Xóa khóa vắng vẫn giảm `size`.** Làm vùng hoạt động mất một phần tử hợp lệ.
10. **Giữ một chỉ số `dense` như ID vĩnh viễn.** Swap-with-last có thể di chuyển phần tử dù khóa ấy không bị xóa.
11. **Tăng chỉ số vòng lặp sau khi xóa tại vị trí hiện tại.** Có thể bỏ qua phần tử cuối vừa được chuyển vào.
12. **Cho rằng `clear` O(1) nghĩa là toàn bộ byte và tham chiếu cũ đã bị xóa.** Chỉ bảo đảm tập rỗng về mặt logic.
13. **Gọi `add` có resize là O(1) worst-case.** Với mảng tăng dung lượng, một lần mở rộng cần sao chép O(n).
14. **Gọi sparse set cổ điển là O(n) bộ nhớ.** Mảng sparse vẫn thường có `U` ô.
15. **Cho rằng dense luôn tăng theo khóa.** Thứ tự phụ thuộc trình tự thêm và các lần xóa.
16. **Đối chiếu danh sách dense với TreeSet bằng thứ tự phần tử.** Tập có thể bằng nhau nhưng dense không sắp.
17. **Chỉ cập nhật entity ID mà bỏ quên payload song song.** Khi dùng ECS pool, ID và dữ liệu phải di chuyển cùng nhau.
18. **Tái sử dụng ID mà không quan tâm handle cũ.** Có thể cần generation counter để tránh nhầm thực thể cũ/mới.
19. **Tính `maxKey-minKey+1` bằng `int` khi cận cực trị.** Có thể tràn; mở rộng sang `long` trước khi trừ.
20. **Suy rằng O(1) membership nghĩa là không có cache miss hoặc bảo đảm thread-safe.** Big-O không thay thế đánh giá bộ nhớ và đồng bộ.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai mảng `dense` và `sparse` có vai trò gì?

**Đáp án:** `dense[0..size-1]` chứa các khóa đang có liên tiếp; `sparse[offset(x)]` ghi vị trí của khóa `x` trong `dense` khi khóa có mặt.

**Câu 2.** Tập đang có `n=5` khóa trong miền `U=1\,000`. Cần duyệt bao nhiêu phần tử của `dense` để liệt kê toàn bộ tập?

**Đáp án:** Đọc đúng 5 vị trí hoạt động, O(n); không phải quét 1.000 khả năng.

**Câu 3.** Viết điều kiện kiểm tra `contains(x)` an toàn trong sparse set hai mảng.

**Đáp án:** Sau khi xác nhận khóa hợp lệ, đặt `p=sparse[offset(x)]`; trả đúng khi `0\le p<size` và `dense[p]==x`.

**Câu 4.** Vì sao không thể chỉ dùng điều kiện `sparse[x]<size`?

**Đáp án:** Giá trị `sparse[x]` của khóa đã xóa hoặc chưa từng thêm có thể là chỉ số cũ trỏ vào phần tử khác.

**Câu 5.** Cho `dense=[3,8,5,6]`, `size=4`. Sau `remove(8)`, `dense` và `sparse[6]` phải là gì?

**Đáp án:** `dense=[3,6,5]`, `size=3` và `sparse[6]=1` vì 6 được chuyển từ vị trí 3 tới vị trí 1.

**Câu 6.** Sau xóa 8 như trên, `sparse[8]` còn bằng 1 có làm `contains(8)` sai không?

**Đáp án:** Không, vì `dense[1]=6\ne8` nên kiểm tra membership trả `false`.

**Câu 7.** Tại sao xóa phần tử ở giữa không cần dịch toàn bộ phần tử phía sau?

**Đáp án:** Sparse set không yêu cầu thứ tự phần tử; có thể chuyển phần tử cuối vào vị trí trống và cập nhật ánh xạ ngược trong O(1).

**Câu 8.** Khi xóa phần tử cuối của `dense`, có cần di chuyển một phần tử khác không?

**Đáp án:** Không. Chỉ cần giảm `size` và dọn ô cuối nếu cài đặt muốn.

**Câu 9.** Thêm một khóa trùng có làm thay đổi `size` không?

**Đáp án:** Không. `add` trả `false`, giữ nguyên tập theo hợp đồng của bài.

**Câu 10.** Vì sao `clear()` có thể là O(1) mà không xóa các giá trị trong `sparse`?

**Đáp án:** Đặt `size=0` khiến mọi chỉ số `p` đều không thuộc vùng hoạt động; sau khi thêm lại, kiểm tra `dense[p]==x` ngăn các chỉ số cũ tạo dương tính giả.

**Câu 11.** Khi `dense` được mở rộng theo nhân đôi, thời gian chèn là O(1) worst-case hay O(1) khấu hao?

**Đáp án:** O(1) khấu hao; lần chèn gây resize có thể phải sao chép O(n) phần tử.

**Câu 12.** Vì sao sparse set cổ điển không nhất thiết tiết kiệm bộ nhớ hơn HashSet khi `U` rất lớn và `n` nhỏ?

**Đáp án:** Vì `sparse` vẫn cần O(U) ô, trong khi HashSet thường dùng bộ nhớ theo `n` và hệ số tải.

**Câu 13.** Với miền `[-5,14]`, khóa `7` được dùng để truy cập ô `sparse` nào?

**Đáp án:** `offset(7)=7-(-5)=12`.

**Câu 14.** Tại sao `rangeSorted(a,b)` trong chương trình cần quét `dense` và sắp kết quả?

**Đáp án:** `dense` không sắp theo khóa; phải lọc các phần tử đang hoạt động, rồi sắp những phần tử phù hợp nếu API yêu cầu thứ tự tăng.

**Câu 15.** Một vòng lặp xóa các phần tử thỏa điều kiện tại vị trí `i` nên tăng `i` sau khi xóa không?

**Đáp án:** Không; phần tử cuối có thể vừa được chuyển vào vị trí `i`, cần xét lại chính vị trí đó.

**Câu 16.** Có nên lưu vĩnh viễn chỉ số `dense` của một entity để truy cập lại sau nhiều lần xóa entity khác không?

**Đáp án:** Không, vì swap-with-last có thể làm entity chuyển vị trí. Dùng khóa/ID hoặc một cơ chế handle có cập nhật/phiên bản phù hợp.

**Câu 17.** Khi áp dụng sparse set cho ECS có mảng payload `velocityData[]` song song, xóa một entity ở giữa cần làm gì với payload?

**Đáp án:** Chuyển payload của entity cuối về cùng vị trí được lấp trong `dense`, đồng thời cập nhật ánh xạ của ID được chuyển.

**Câu 18.** Nếu một ID được tái sử dụng cho entity mới, công thức membership của sparse set có tự phân biệt handle cũ không?

**Đáp án:** Không. Khi cùng ID lại có mặt, cần generation/version để phân biệt vòng đời cũ và mới nếu hệ thống yêu cầu.

**Câu 19.** Vì sao phép `contains` vẫn có thể bị cache miss dù Big-O là O(1)?

**Đáp án:** Nó đọc `sparse[offset(x)]`, một vị trí có thể nằm ở trang/cache line chưa có trong cache; Big-O đếm số thao tác, không bảo đảm độ trễ vật lý.

**Câu 20.** Sau khi `clear` rồi thêm một khóa mới, các chỉ số `sparse` cũ có bắt buộc trở thành -1 không?

**Đáp án:** Không. Với điều kiện `p<size` và `dense[p]==x`, những giá trị cũ của khóa vắng mặt không làm membership sai.

**Điểm ghi nhớ:** Sparse set hai mảng dùng **`dense` để lưu liên tiếp `n` phần tử đang có** và **`sparse` để ánh xạ khóa → vị trí**. Bất biến quan trọng là `sparse[dense[i]]=i` cho mọi `i<size`; khi tra membership, bắt buộc kiểm tra **vị trí còn hoạt động và khóa trong `dense` khớp**. Thêm vào cuối, xóa bằng **swap-with-last**, và `clear` logic bằng `size=0` giúp thao tác nhanh; đánh đổi là **thứ tự/vị trí không ổn định** và phần `sparse` vẫn thường chiếm **O(U)** bộ nhớ. Chọn cấu trúc này khi cần **membership nhanh kết hợp duyệt đặc O(n)** trên một miền khóa số nguyên đủ nhỏ để cấp phát.
