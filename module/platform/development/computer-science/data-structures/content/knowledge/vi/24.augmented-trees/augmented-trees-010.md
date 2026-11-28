# Danh sách khối (unrolled linked list) và kết hợp lưu liên tiếp với liên kết

## 1. Bài toán: mảng liên tục hay danh sách liên kết?

Trong học phần **Cấu trúc dữ liệu**, mảng và danh sách liên kết có những ưu và nhược điểm bổ sung cho nhau:

- **Mảng (array):** các ô dữ liệu hoặc các tham chiếu phần tử được bố trí liên tục, thuận lợi cho truy cập theo chỉ số và duyệt tuần tự; nhưng chèn/xóa giữa một mảng có thể phải dịch nhiều phần tử.
- **Danh sách liên kết (linked list):** có thể tháo/gắn nút tại vị trí đã biết bằng một số thao tác con trỏ; nhưng mỗi phần tử thường cần nút và con trỏ riêng, việc đi tới vị trí thứ `i` phải lần theo nhiều liên kết.
- **Danh sách khối (unrolled linked list):** mỗi nút liên kết không lưu một phần tử, mà lưu **một nhóm phần tử trong một mảng nhỏ**. Các khối được nối với nhau bằng con trỏ.

Tình huống có thể gặp:

- Một dãy bản ghi được duyệt liên tục nhưng đôi khi cần chèn/xóa ở giữa.
- Danh sách sự kiện của một hệ thống cần giảm số lần cấp phát nút.
- Bộ sưu tập phần tử có kích thước lớn, muốn tận dụng tính cục bộ bộ nhớ tốt hơn danh sách liên kết từng phần tử.
- Cấu trúc dãy cần chèn/xóa, nhưng chưa cần hệ thống cây cân bằng phức tạp như rope hoặc implicit treap.

Một danh sách liên kết đơn lưu sáu giá trị như sau:

```text
head
 |
 v
[10|next] -> [20|next] -> [30|next] -> [40|next] -> [50|next] -> [60|null]
```

Nếu dùng danh sách khối, ta có thể lưu:

```text
head
 |
 v
[10 20 30] <--> [40 50 60]
   block 1          block 2
```

**Thứ tự logic** vẫn là:

```text
[10, 20, 30, 40, 50, 60]
```

Điểm khác biệt là một liên kết `next` hoặc `prev` có thể đưa ta qua **nhiều phần tử**, thay vì chỉ một phần tử.

> **Tư tưởng trung tâm:** kết hợp **lưu một nhóm phần tử liền nhau trong mỗi khối** với **khả năng nối, tách và gộp các khối bằng liên kết**. Đây là cấu trúc dãy động dựa trên các khối mảng, không phải một loại cây.

Dù bài nằm trong chương **Cây tăng cường**, unrolled linked list **không phải cây tăng cường**. Việc so sánh nó với các cấu trúc cây lưu độ dài cây con rất hữu ích để lựa chọn cách biểu diễn dãy theo đặc tính truy cập, chỉnh sửa, thời gian và bộ nhớ.

## 2. Cấu trúc một nút khối

### 2.1. Nút không chỉ có một phần tử

Một nút khối có thể được mô tả bằng:

```text
Block
┌────────────────────────────────────────┐
│ prev │ count │ values[0..B-1] │ next  │
└────────────────────────────────────────┘
```

Trong đó:

- `prev`: liên kết tới khối trước (nếu dùng danh sách liên kết đôi).
- `next`: liên kết tới khối sau.
- `values`: một mảng nhỏ chứa các phần tử của khối theo đúng thứ tự.
- `count`: số phần tử **đang sử dụng** trong khối.
- `B`: sức chứa tối đa của một khối.

Một thiết kế dùng mảng cố định `B` ô cần lưu riêng `count`; các ô còn lại không thuộc dãy logic. Với Python, ta có thể dùng `list` biến độ dài và lấy `count=len(values)`.

### 2.2. Ví dụ với sức chứa `B=6`

Danh sách có 14 phần tử:

```text
Giá trị:
[1,2,3,4,5,6,7,8,9,10,11,12,13,14]

Các khối:
[1,2,3,4,5,6] <-> [7,8,9,10,11] <-> [12,13,14]
  6 phần tử          5 phần tử            3 phần tử
```

Ở đây mỗi khối chứa tối đa `6` phần tử, nhưng không nhất thiết phải đầy. Việc cho phép những khối có ít phần tử là quan trọng để có thể **chèn/xóa cục bộ mà không tái tổ chức toàn bộ dãy**.

### 2.3. Danh sách đơn hay đôi?

Có thể dùng:

- **Liên kết đơn:** mỗi khối chỉ có `next`. Ít con trỏ hơn, nhưng muốn gộp với khối trước thường phải giữ tham chiếu tới khối trước trong lúc duyệt.
- **Liên kết đôi:** mỗi khối có `prev` và `next`. Dễ mượn, gộp, xóa khối và duyệt từ hai phía, nhưng tốn thêm một con trỏ cho mỗi khối.

Trong bài, cài đặt Python dùng **danh sách liên kết đôi với nút lính canh (sentinel)**. Đây là một lựa chọn thiết kế, không phải yêu cầu bắt buộc của unrolled linked list.

### 2.4. Đặc điểm lưu liên tiếp cần hiểu chính xác

Một khối Python dùng `list` có **mảng tham chiếu liên tục** tới các đối tượng Python, nhưng **bản thân các đối tượng** không nhất thiết liên tiếp trong bộ nhớ.

Trong C/C++:

- Mảng cố định `T values[B]` có thể đặt các giá trị `T` trực tiếp sát nhau trong một khối.
- Một `std::vector<T>` dùng vùng nhớ động chứa các phần tử `T` liên tiếp.
- Việc chọn kiểu phần tử, căn chỉnh, cấp phát khối và kích thước cache line quyết định hiệu quả cục bộ bộ nhớ thực tế.

Vì vậy, khái niệm **cục bộ bộ nhớ (memory locality)** là lợi thế thường có của danh sách khối, nhưng không được tuyên bố mọi triển khai Python đều lưu **toàn bộ dữ liệu đối tượng** liên tiếp.

## 3. Bất biến của danh sách khối

Ta ký hiệu:

- `n`: tổng số phần tử của dãy.
- `m`: số khối **thực sự chứa phần tử**.
- `B`: sức chứa tối đa một khối.
- `s_i`: số phần tử trong khối thứ `i`.

### 3.1. Bất biến cấu trúc

Một danh sách khối hợp lệ cần thỏa:

1. Mỗi khối chứa một dãy có thứ tự gồm `s_i` phần tử.
2. Với khối không rỗng: `1≤s_i≤B`.
3. Các khối nối thành **một chuỗi liên kết**, không có chu trình ngoài vòng sentinel được định nghĩa trước.
4. Liên kết `next` và `prev` phải nhất quán nếu dùng danh sách đôi.
5. Thứ tự phần tử logic bằng phép nối dãy của tất cả khối theo thứ tự liên kết.
6. Tổng kích thước phải đúng:

\[
\boxed{n=\sum_{i=1}^{m}s_i}.
\]

Khi danh sách logic rỗng, ta chọn `m=0` và chỉ giữ sentinel; không lưu một **khối dữ liệu rỗng** không cần thiết.

### 3.2. Bất biến mức lấp đầy (occupancy)

Nếu chỉ yêu cầu `1≤s_i≤B`, có thể xuất hiện rất nhiều khối gần rỗng:

```text
[1] <-> [2] <-> [3] <-> [4] <-> ...
```

Khi đó, danh sách khối thoái hóa về gần giống danh sách liên kết thông thường và mất lợi ích giảm số liên kết.

Một chính sách phổ biến là đặt **ngưỡng lấp đầy tối thiểu**:

\[
\boxed{L=\left\lceil\frac B2\right\rceil}
\]

và cố giữ mỗi khối có ít nhất `L` phần tử, ngoại trừ khi **toàn bộ dãy chỉ có một khối**.

Trong cài đặt minh họa, ta chọn **`B` chẵn và `B≥4`**, nên:

\[
L=\frac B2.
\]

Bất biến cụ thể:

- Nếu `m=0`: danh sách rỗng.
- Nếu `m=1`: khối duy nhất có `1≤s_1≤B`.
- Nếu `m≥2`: mọi khối có **`L≤s_i≤B`**.

Lưu ý: có những biến thể chỉ bắt buộc khối ở giữa đủ đầy và cho phép khối đầu/cuối nhỏ hơn ngưỡng. Bài này chọn quy tắc chặt hơn để **dễ kiểm tra bằng chương trình**.

### 3.3. Vì sao ngưỡng lấp đầy giúp giảm số khối?

Khi `m≥2` và mỗi khối chứa ít nhất `L` phần tử:

\[
n=\sum_{i=1}^{m}s_i\ge mL.
\]

Do đó:

\[
\boxed{m\le\frac nL}.
\]

Với `B` chẵn và `L=B/2`:

\[
\boxed{m\le\frac{2n}{B}}.
\]

Đây là cơ sở của ước lượng **`O(n/B)` khối** khi cần đi qua dãy. Nếu không duy trì ngưỡng, ta chỉ có thể bảo đảm `m≤n`.

### 3.4. Minh họa khối đủ và thiếu

Với `B=6`, ta có `L=3`.

```text
Hợp lệ khi có nhiều khối:
[10 20 30] <-> [40 50 60 70]
    3 phần tử        4 phần tử

Không hợp lệ theo quy tắc đã chọn:
[10] <-> [20 30 40 50 60]
  1              5
```

Danh sách thứ hai có đủ phần tử và không vượt sức chứa, nhưng khối đầu chỉ có `1<L`; thuật toán xóa phải **mượn** từ khối lân cận hoặc **gộp** khối để khôi phục bất biến.

## 4. Truy cập phần tử theo chỉ số logic

### 4.1. Chỉ số toàn dãy khác chỉ số trong khối

Giả sử:

```text
Block A          Block B          Block C
[10 20 30]  <->  [40 50 60 70] <-> [80 90 100]

Global index:
 0  1  2         3  4  5  6       7  8   9
```

Muốn đọc phần tử tại **chỉ số logic `i=5`**, ta đi qua:

1. Khối A có `3` phần tử; `5≥3`, trừ `3` → chỉ số còn lại `2`.
2. Khối B có `4` phần tử; `2<4`, nên phần tử nằm tại **`B.values[2]`**, tức `60`.

Mã giả:

```text
LOCATE(i):
    require 0 <= i < n
    block = first_block
    remaining = i

    while remaining >= len(block.values):
        remaining -= len(block.values)
        block = block.next

    return (block, remaining)
```

Ở đây `remaining` là **chỉ số bên trong khối hiện tại**, không phải chỉ số toàn dãy.

### 4.2. Thời gian truy cập

Nếu phải đi qua `m` khối, việc xác định khối có thể tốn `O(m)` thời gian. Sau khi biết khối, đọc `values[offset]` trong mảng mất `O(1)`.

Vì duy trì mức lấp đầy tối thiểu `L=B/2`:

\[
\boxed{T_{\text{access}}=O(m)=O\left(1+\frac nB\right).}
\]

Đây **không phải truy cập `O(1)` tổng thể** nếu chỉ có danh sách liên kết các khối và không có chỉ mục phụ. Dù mảng bên trong mỗi khối cho phép truy cập `O(1)`, ta vẫn cần **tìm đúng khối**.

### 4.3. Giữ con trỏ tới khối đã biết có lợi thế gì?

Nếu thuật toán đã có:

```text
block = khối đang thao tác
offset = vị trí trong khối
```

thì việc đọc `block.values[offset]` là `O(1)`, còn chèn/xóa trong khối chỉ có chi phí liên quan tới số phần tử **trong một khối**.

Do đó cần phân biệt:

- **Truy cập theo chỉ số toàn dãy:** phải tìm khối, `O(m)`.
- **Truy cập khi đã biết khối và vị trí nội bộ:** thường `O(1)`.
- **Chỉnh sửa khi đã có một iterator/handle phù hợp:** không phải đi lại từ đầu danh sách, nhưng iterator có thể mất hiệu lực khi khối bị tách/gộp.

## 5. Chèn một phần tử vào một khối

### 5.1. Khối còn chỗ

Với `B=6`:

```text
Khối trước chèn:
[10 20 30 40]  (size=4)

Chèn 25 vào trước 30:
[10 20 25 30 40]  (size=5)
```

Trong mảng của khối, có thể phải dịch `30,40` sang phải để tạo chỗ.

**Chi phí bên trong khối:** `O(B)` trong trường hợp xấu nhất, vì một khối có nhiều nhất `B` phần tử.

Không cần dời dữ liệu ở **các khối phía sau**.

### 5.2. Khối đã đầy: phải tách khối (*split block*)

Vẫn với `B=6`, khối có:

```text
[10 20 30 40 50 60]  (size=6)
```

Chèn `35` vào vị trí trước `40`:

```text
Tạm thời sau chèn vào mảng nội bộ:
[10 20 30 35 40 50 60]  (size=7 > B)
```

Tách sau ba phần tử:

```text
[10 20 30] <-> [35 40 50 60]
  size=3           size=4
```

Hai khối đều thỏa:

\[
L=3\le size\le B=6.
\]

Vì **chỉ một khối** đã nhận thêm đúng một phần tử, độ dài tạm thời tối đa `B+1`. Tách tại:

\[
\boxed{mid=\left\lfloor\frac{B+1}{2}\right\rfloor}
\]

sẽ tạo hai khối có kích thước `\lfloor(B+1)/2\rfloor` và `\lceil(B+1)/2\rceil`, cùng lớn hơn hoặc bằng `B/2` khi `B` chẵn.

### 5.3. Trường hợp chèn ở ranh giới hai khối

Nếu chèn ngay trước phần tử đầu tiên của khối B, có thể:

- Chèn cuối khối A nếu A còn chỗ.
- Hoặc chèn đầu khối B.
- Nếu khối được chọn đầy, tách khối đó.

Cả hai lựa chọn có thể tạo **hình dạng khối khác nhau** nhưng phải giữ **cùng dãy logic**.

Trong mã Python, quy tắc cố định là: **với vị trí `i<n`, tìm khối đang chứa phần tử `i` và chèn trước phần tử đó**. Với `i=n`, chèn cuối khối cuối cùng. Cách này làm hợp đồng dễ kiểm tra.

### 5.4. Thao tác với liên kết

Sau khi tạo khối mới ở bên phải khối `A`:

```text
Trước:
P <-> A <-> N

Sau:
P <-> A <-> NEW <-> N
```

Phải cập nhật nhất quán:

- `A.next=NEW`.
- `NEW.prev=A`.
- `NEW.next=N`.
- `N.prev=NEW`.

Nếu dùng sentinel vòng tròn, trường hợp chèn ở cuối cũng không cần phân biệt `N=None`: `N` có thể chính là sentinel.

**Tách khối không làm tăng tổng số phần tử ngoài phần tử vừa chèn**; nó chỉ thay đổi cách **phân nhóm** các phần tử.

## 6. Xóa phần tử: không chỉ bỏ một ô khỏi mảng

### 6.1. Khối vẫn đủ phần tử sau xóa

Ví dụ `B=6,L=3`:

```text
Trước:
[10 20 30 40]

Xóa 20:
[10 30 40]  (size=3, vẫn hợp lệ)
```

Các phần tử sau vị trí xóa trong khối dịch sang trái. Chi phí nội bộ `O(B)`.

### 6.2. Khối thiếu phần tử: mượn từ khối kế bên

Giả sử sau xóa:

```text
[10 30] <-> [35 40 50 60]
 size=2             size=4
```

Khối trái có `2<L=3`. Khối phải có `4>L`, nên có thể **mượn phần tử đầu của khối phải** và đưa về **cuối khối trái**:

```text
[10 30 35] <-> [40 50 60]
  size=3           size=3
```

Thứ tự logic trước và sau mượn đều là:

```text
[10, 30, 35, 40, 50, 60]
```

Nếu mượn từ **khối bên trái**, cần chuyển **phần tử cuối của khối trái** vào **đầu khối đang thiếu**.

**Không được mượn một phần tử tùy ý** từ khối kế bên: chỉ lấy ở **ranh giới** để bảo toàn thứ tự của dãy.

### 6.3. Không thể mượn: gộp hai khối (*merge blocks*)

Nếu cả hai khối có kích thước nhỏ và khối lân cận không đủ phần tử để cho mượn:

```text
[10 35] <-> [40 50 60]
 size=2          size=3
```

Ta có thể gộp thành:

```text
[10 35 40 50 60]
      size=5
```

Với `B=6,L=3`:

\[
( L-1 )+L=2L-1=B-1\le B.
\]

Vậy hai khối đủ để gộp mà **không vượt sức chứa**.

Khi gộp, khối bị loại phải được tháo khỏi danh sách liên kết bằng cách sửa `prev/next` ở các khối lân cận. Tổng số phần tử **không đổi do bước gộp**, vì nó chỉ chuyển cách lưu.

### 6.4. Ưu tiên mượn trước, gộp sau

Một chiến lược dễ kiểm soát sau khi xóa:

1. Nếu chỉ còn **một khối**, cho phép khối có ít hơn `L` phần tử; nếu rỗng, loại khối.
2. Nếu khối có `size≥L`, kết thúc.
3. Nếu khối kế tiếp có **nhiều hơn `L`** phần tử, mượn phần tử đầu của khối tiếp theo.
4. Nếu khối kế trước có **nhiều hơn `L`**, mượn phần tử cuối của khối trước.
5. Nếu không thể mượn, gộp với một khối kề bên.

Cách này giữ ngưỡng tối thiểu **sau mỗi thao tác**, giúp số khối được chặn bởi `O(n/B)`.

### 6.5. Ví dụ xóa hai lần liên tiếp

Bắt đầu từ kết quả chèn `35` ở mục 5:

```text
[10 20 30] <-> [35 40 50 60]
```

Xóa phần tử `20`:

```text
Sau xóa ở khối trái:
[10 30] <-> [35 40 50 60]
```

Mượn `35` từ khối phải:

```text
[10 30 35] <-> [40 50 60]
```

Xóa tiếp phần tử `30`:

```text
[10 35] <-> [40 50 60]
```

Khối phải chỉ có `L=3` phần tử, không thể cho mượn mà vẫn giữ mức tối thiểu. Gộp:

```text
[10 35 40 50 60]
```

Kết quả logic sau hai lần xóa là:

```text
[10, 35, 40, 50, 60]
```

Không có phần tử nào bị xóa thêm do thao tác **mượn** hoặc **gộp**.

## 7. Vai trò của sentinel trong danh sách liên kết đôi

### 7.1. Sentinel là nút kỹ thuật, không chứa dữ liệu

Có thể tạo một nút đặc biệt `S` với:

```text
Danh sách rỗng:

   ┌─────────┐
   │    S    │
   │ prev ↻  │
   │ next ↻  │
   └─────────┘
```

Về liên kết:

```text
S.next = S
S.prev = S
```

Khi có hai khối:

```text
S <-> [10 20 30] <-> [40 50 60] <-> S
```

Vòng này **cố ý tồn tại** vì sentinel giúp tránh xử lý riêng đầu/cuối trong thao tác cập nhật liên kết. Nhưng **các nút dữ liệu** không được tạo vòng lặp khác hoặc bị dùng chung.

### 7.2. Chèn một khối mới sau khối hiện tại

```text
INSERT_AFTER(block, fresh):
    right = block.next

    fresh.prev = block
    fresh.next = right

    block.next = fresh
    right.prev = fresh
```

### 7.3. Tháo một khối

```text
UNLINK(block):
    block.prev.next = block.next
    block.next.prev = block.prev

    # Tùy thiết kế, làm rỗng prev/next của block cũ
    # để không cho dùng tiếp như khối đang hoạt động.
```

Mỗi thao tác liên kết chỉ sửa một số hằng con trỏ, nên **`O(1)`** nếu đã có tham chiếu tới khối.

**Nhưng đừng nhầm** `UNLINK(block)=O(1)` với xóa phần tử theo chỉ số trong toàn danh sách `O(1)`: còn có chi phí tìm khối, dời phần tử nội bộ và mượn/gộp.

## 8. Chọn kích thước khối: vì sao `B` quan trọng?

Kích thước khối tạo ra một **đánh đổi**:

- `B` nhỏ: mỗi khối ít phần tử, dịch trong khối rẻ; nhưng phải đi qua nhiều liên kết khi tìm theo chỉ số.
- `B` lớn: ít khối và ít con trỏ, duyệt theo chỉ số có thể nhanh hơn; nhưng chèn/xóa giữa một khối có thể phải dời nhiều phần tử.

Với `n` phần tử, các khối có khoảng `\Theta(B)` phần tử nhờ duy trì ngưỡng lấp đầy:

\[
m=O\left(1+\frac nB\right).
\]

### 8.1. Chi phí tìm khối và chỉnh sửa nội bộ

Khi chèn hoặc xóa tại **chỉ số bất kỳ**:

\[
T(n,B)=O\left(1+\frac nB+B\right).
\]

Hai thành phần:

- `n/B`: tìm khối bằng cách đi qua danh sách.
- `B`: thao tác `list.insert`, `list.pop`, tách, mượn hoặc gộp tối đa một lượng `O(B)` phần tử trong các khối kề nhau.

Đây là một **chặn trên**, không phải cam kết rằng mọi thao tác đều chạm đúng `n/B+B` phần tử.

### 8.2. Vì sao đôi khi chọn `B≈√n`?

Bỏ qua hằng số, cần cân bằng:

\[
\frac nB+B.
\]

Với `B>0`, hai vế gần bằng nhau khi:

\[
\frac nB\approx B
\quad\Longrightarrow\quad
B\approx\sqrt n.
\]

Khi đó:

\[
T(n,B)=O(\sqrt n).
\]

Đây là trực giác của **chia khối căn bậc hai** (*square-root decomposition*).

**Điều kiện quan trọng:** nếu `n` thay đổi rất nhiều, một `B` chọn một lần từ `n` ban đầu không tự duy trì quan hệ `B=\Theta(\sqrt n)`. Muốn giữ bảo đảm theo `n` mới, có thể cần **điều chỉnh kích thước khối và xây lại theo ngưỡng**.

### 8.3. Kích thước khối thực tế không chỉ dựa trên Big-O

Trong một ngôn ngữ hệ thống, kích thước khối còn chịu ảnh hưởng của:

- Kích thước đối tượng/phần tử.
- Dung lượng **cache line** và số ô mảng có thể đọc liên tiếp.
- Chi phí cấp phát bộ nhớ, phân mảnh và thu gom rác.
- Tỉ lệ thao tác duyệt so với thao tác chèn/xóa.
- Số lượng nút/khối phải giữ trong bộ nhớ.
- Chi phí di chuyển/chép phần tử (giá trị lớn hay con trỏ nhỏ).

Bởi vậy, lựa chọn `B≈√n` là một **mô hình thuật toán** hữu ích, nhưng **không phải con số tối ưu cho mọi workload**. Trong thực tế có thể chọn `B` cố định vừa với đặc tính bộ nhớ rồi đo hiệu năng.

## 9. Cài đặt Python đầy đủ: danh sách liên kết đôi theo khối

Ta xây một cấu trúc có các phương thức:

- `append(value)`: thêm cuối.
- `insert(index,value)`: chèn trước chỉ số `index`.
- `pop(index)`: xóa và trả phần tử tại chỉ số.
- `get(index)` và `set(index,value)`: đọc/sửa một phần tử.
- `to_list()`: xuất dãy logic.
- `blocks()`: xem snapshot các khối để minh họa.
- `validate()`: kiểm tra bất biến sau thao tác.

### 9.1. Quy ước rõ ràng

- Chỉ số là **số nguyên từ `0`**.
- `insert(i,x)` hợp lệ khi `0≤i≤n`; `i=n` nghĩa là thêm cuối.
- `get/set/pop(i)` hợp lệ khi `0≤i<n`.
- Không dùng chỉ số âm kiểu Python list để giảm nhập nhằng; chỉ số âm sẽ báo lỗi.
- Giá trị phần tử có thể là bất kỳ đối tượng Python, **kể cả `None`**. Sentinel được phân biệt bằng đối tượng nút, không phải bằng giá trị dữ liệu.
- Sức chứa khối `B` chọn **số chẵn ≥4**; `L=B//2`.
- Mọi khối dữ liệu có tối đa `B` phần tử. Với ít nhất hai khối, mỗi khối có tối thiểu `L` phần tử.

Mã sau là **một ví dụ học thuật hoàn chỉnh**, dùng `list` Python làm phần lưu liên tục các **tham chiếu** bên trong mỗi khối.

### 9.2. Lớp nút khối

```python
class _Block:
    __slots__ = ("values", "prev", "next")

    def __init__(self, values=None):
        self.values = [] if values is None else list(values)
        self.prev = None
        self.next = None
```

Tên bắt đầu bằng dấu gạch dưới nhấn mạnh đây là cấu trúc **nội bộ**, không nên cho mã sử dụng tùy tiện chỉnh `values/prev/next` của các khối.

### 9.3. Khởi tạo cấu trúc và sentinel

```python
class UnrolledList:
    def __init__(self, values=(), block_capacity=6):
        if (
            type(block_capacity) is not int
            or block_capacity < 4
            or block_capacity % 2 != 0
        ):
            raise ValueError(
                "block_capacity phải là số chẵn >= 4"
            )

        self.B = block_capacity
        self.L = block_capacity // 2

        self._sentinel = _Block()
        self._sentinel.prev = self._sentinel
        self._sentinel.next = self._sentinel

        self._size = 0
        self._block_count = 0

        for value in values:
            self.append(value)

    def __len__(self):
        return self._size

    @property
    def block_count(self):
        return self._block_count

    def _first(self):
        return self._sentinel.next

    def _last(self):
        return self._sentinel.prev
```

**Quan trọng về ghép các đoạn code:** các đoạn tiếp theo từ mục 9.4 đến 9.11 là **những phương thức còn lại của cùng lớp `UnrolledList`**. Khi viết vào tệp Python, hãy đặt chúng bên trong `class UnrolledList:` ở **cùng mức thụt lề** với `__len__` và `_first`.

### 9.4. Liên kết và tháo khối trong `O(1)`

```python
    def _insert_block_after(self, block, fresh):
        right = block.next

        fresh.prev = block
        fresh.next = right
        block.next = fresh
        right.prev = fresh

        self._block_count += 1

    def _unlink_block(self, block):
        if block is self._sentinel:
            raise ValueError("Không được xóa sentinel")

        block.prev.next = block.next
        block.next.prev = block.prev

        block.prev = None
        block.next = None
        self._block_count -= 1
```

Các hàm nội bộ được gọi khi khối đã được xác định. Không cần tìm lại khối trước hoặc khối sau vì đây là danh sách liên kết đôi.

### 9.5. Tìm khối chứa chỉ số toàn dãy

```python
    def _check_index(self, index, allow_end=False):
        if type(index) is not int:
            raise TypeError("index phải là int")

        upper = self._size if allow_end else self._size - 1

        if not 0 <= index <= upper:
            raise IndexError("index ngoài phạm vi")

    def _locate(self, index):
        """Đầu vào: 0 <= index < size.

        Trả (block, offset) chứa phần tử index.
        """
        remaining = index
        block = self._first()

        while block is not self._sentinel:
            count = len(block.values)

            if remaining < count:
                return block, remaining

            remaining -= count
            block = block.next

        raise RuntimeError("Cấu trúc khối không nhất quán")
```

Vòng lặp chỉ đi qua các khối, **không** đi qua từng phần tử bên trong. Với bất biến tối thiểu `L=B/2`, có `O(1+n/B)` khối.

Để `append` không phải quét hết khối, mã sẽ **chọn trực tiếp khối cuối bằng `_last()`** khi thêm cuối.

### 9.6. Chèn và tách khối quá đầy

```python
    def insert(self, index, value):
        self._check_index(index, allow_end=True)

        if self._block_count == 0:
            fresh = _Block([value])
            self._insert_block_after(self._sentinel, fresh)
            self._size += 1
            return

        if index == self._size:
            block = self._last()
            offset = len(block.values)
        else:
            block, offset = self._locate(index)

        block.values.insert(offset, value)
        self._size += 1

        if len(block.values) <= self.B:
            return

        # Một khối tạm có B+1 phần tử: tách gần giữa.
        middle = len(block.values) // 2
        right_values = block.values[middle:]
        del block.values[middle:]

        right_block = _Block(right_values)
        self._insert_block_after(block, right_block)

    def append(self, value):
        self.insert(self._size, value)
```

Phân tích:

- Tìm khối có thể tốn `O(n/B)`.
- Chèn bằng `list.insert` có thể dịch tới `B` tham chiếu: `O(B)`.
- Nếu khối vượt `B`, chia thành hai mảng nhỏ và nối một nút mới: `O(B)`.
- Chèn thêm ở cuối dùng tham chiếu khối cuối, nên **không phải trả chi phí quét `O(n/B)`**; mỗi lần append vẫn có thể phải tách khối và chép `O(B)` phần tử.

Với `B` được coi là một **hằng số cố định**, append có chặn trên `O(1)` theo số lượng phần tử `n` trong mô hình này. Nhưng nếu phân tích cả `B` như một tham số thay đổi, phải ghi rõ chi phí `O(B)` khi tách.

### 9.7. Khôi phục mức lấp đầy sau xóa

```python
    def _repair_underfull(self, block):
        """block còn 1..L-1 phần tử; có >=2 khối."""
        if self._block_count <= 1:
            return
        if len(block.values) >= self.L:
            return

        right = block.next
        left = block.prev
        sent = self._sentinel

        # Ưu tiên mượn từ khối kế bên phải.
        if right is not sent and len(right.values) > self.L:
            value = right.values.pop(0)
            block.values.append(value)
            return

        # Nếu không, thử mượn từ khối trước.
        if left is not sent and len(left.values) > self.L:
            value = left.values.pop()
            block.values.insert(0, value)
            return

        # Hai khối kề đều không thể cho mượn:
        # gộp với khối kế bên phải nếu có.
        if right is not sent:
            block.values.extend(right.values)
            self._unlink_block(right)
            return

        # Nếu block là khối cuối, gộp vào khối trước.
        left.values.extend(block.values)
        self._unlink_block(block)
```

**Tại sao không bị tràn?** Sau khi xóa đúng một phần tử khỏi khối trước đó hợp lệ, khối thiếu chỉ còn `L-1` phần tử. Nếu không thể mượn, khối kề có `L` phần tử (theo bất biến đầu vào). Kích thước sau gộp là:

\[
(L-1)+L=2L-1=B-1<B.
\]

Nếu chỉ còn một khối, quy tắc cho phép khối đó có ít hơn `L`. Hàm không cần tạo một khối rỗng để biểu diễn danh sách rỗng.

### 9.8. Xóa phần tử tại một chỉ số

```python
    def pop(self, index):
        self._check_index(index)

        block, offset = self._locate(index)
        removed = block.values.pop(offset)
        self._size -= 1

        if not block.values:
            # Theo bất biến, điều này chỉ xảy ra khi
            # trước xóa chỉ có đúng một khối chứa 1 phần tử.
            self._unlink_block(block)
            return removed

        if self._block_count > 1 and len(block.values) < self.L:
            self._repair_underfull(block)

        return removed
```

**Tại sao không xóa nhầm phần tử khi mượn/gộp?** Giá trị `removed` đã được lấy ra. Phần mượn/gộp chỉ di chuyển những giá trị **vẫn còn trong dãy** giữa hai khối kề nhau, không thêm và không xóa thêm giá trị logic nào.

### 9.9. Đọc và cập nhật một phần tử

```python
    def get(self, index):
        self._check_index(index)
        block, offset = self._locate(index)
        return block.values[offset]

    def set(self, index, value):
        self._check_index(index)
        block, offset = self._locate(index)

        old = block.values[offset]
        block.values[offset] = value
        return old
```

Thay giá trị bằng `set` **không** thay số phần tử trong khối, không thay tổng độ dài `n` và không đòi hỏi mượn/gộp. Nhưng `set` vẫn cần **tìm đúng khối**, nên thời gian là `O(n/B)` trong thiết kế chưa có chỉ mục khối phụ.

### 9.10. Duyệt và xem các khối

```python
    def __iter__(self):
        block = self._first()

        while block is not self._sentinel:
            for value in block.values:
                yield value
            block = block.next

    def to_list(self):
        return list(self)

    def blocks(self):
        """Snapshot để quan sát; không trả mảng nội bộ."""
        result = []
        block = self._first()

        while block is not self._sentinel:
            result.append(list(block.values))
            block = block.next

        return result
```

**Lưu ý:** nếu thay đổi cấu trúc trong lúc đang duyệt `__iter__`, kết quả iterator không được bảo đảm. Mã minh họa không triển khai cơ chế *fail-fast iteration* hoặc đồng bộ.

Hàm `blocks()` trả **bản sao của từng mảng trong khối** nhằm tránh cho người dùng tùy tiện phá bất biến bằng cách sửa mảng nội bộ.

### 9.11. Kiểm tra bất biến độc lập

```python
    def validate(self):
        sent = self._sentinel

        if sent.next is None or sent.prev is None:
            return False
        if sent.next.prev is not sent:
            return False
        if sent.prev.next is not sent:
            return False

        seen = set()
        block = sent.next
        count_blocks = 0
        count_values = 0

        while block is not sent:
            if not isinstance(block, _Block):
                return False

            identity = id(block)
            if identity in seen:
                return False
            seen.add(identity)

            if block.prev is None or block.next is None:
                return False
            if block.prev.next is not block:
                return False
            if block.next.prev is not block:
                return False

            block_size = len(block.values)

            if not 1 <= block_size <= self.B:
                return False
            if self._block_count >= 2 and block_size < self.L:
                return False

            count_blocks += 1
            count_values += block_size
            block = block.next

        if count_blocks != self._block_count:
            return False
        if count_values != self._size:
            return False
        if (self._size == 0) != (self._block_count == 0):
            return False

        return True
```

Hàm duyệt các khối và kiểm tra liên kết hai chiều, giới hạn kích thước và tổng số phần tử. Với `m` khối, chi phí kiểm tra bản thân **`O(m)` thời gian** và bộ nhớ `O(m)` cho `seen`. Nó không sao chép toàn bộ giá trị.

**Giới hạn của validator:** nó xác nhận tính nhất quán **cấu trúc**; nếu một thao tác vô tình hoán đổi hai giá trị mà vẫn giữ các liên kết và kích thước đúng, validator không thể biết dãy logic mong đợi. Khi kiểm thử, phải **đối chiếu thêm với một danh sách tham chiếu độc lập**.

### 9.12. Cách ghép các code block thành một tệp Python

Để thực hành:

1. Đặt khai báo `class _Block` ở mức đầu tệp.
2. Đặt đoạn `class UnrolledList` ở mục 9.3 ngay sau đó.
3. Chép các phương thức của mục 9.4–9.11 **vào bên trong cùng lớp `UnrolledList`**, với cùng mức thụt lề của `__len__`.
4. Chạy các ví dụ ở những mục tiếp theo.

Các đoạn mã đã được chia nhỏ để giải thích từng thao tác, nhưng cùng tạo thành **một cài đặt hoàn chỉnh** khi ghép đúng vị trí.

## 10. Truy vết Python: chèn, tách, mượn và gộp

### 10.1. Chèn khi khối đầy

```python
u = UnrolledList(
    [10, 20, 30, 40, 50, 60],
    block_capacity=6
)

print(u.to_list())
# [10, 20, 30, 40, 50, 60]

print(u.blocks())
# [[10, 20, 30, 40, 50, 60]]

u.insert(3, 35)

print(u.to_list())
# [10, 20, 30, 35, 40, 50, 60]

print(u.blocks())
# [[10, 20, 30], [35, 40, 50, 60]]

assert u.validate()
```

Mã áp dụng đúng quy tắc: chèn trước chỉ số `3` rồi tách khối `7` phần tử thành hai khối có kích thước `3` và `4`.

### 10.2. Xóa gây mượn từ khối kế bên

```python
print(u.pop(1))  # 20

print(u.to_list())
# [10, 30, 35, 40, 50, 60]

print(u.blocks())
# [[10, 30, 35], [40, 50, 60]]

assert u.validate()
```

Sau khi xóa `20`, khối đầu còn `[10,30]`, tức `2<L=3`. Khối phải có `4` phần tử nên có thể cho mượn `35`.

### 10.3. Xóa tiếp gây gộp

```python
print(u.pop(1))  # 30

print(u.to_list())
# [10, 35, 40, 50, 60]

print(u.blocks())
# [[10, 35, 40, 50, 60]]

assert u.validate()
```

Ở lần xóa này, khối trái còn `2` phần tử, khối phải có đúng `3=L` nên không thể cho mượn. Hai khối được gộp thành một khối có `5≤B` phần tử.

### 10.4. Thêm ở đầu và cuối

```python
u = UnrolledList([2, 3, 4], block_capacity=6)

u.insert(0, 1)
u.append(5)
u.append(6)

assert u.to_list() == [1, 2, 3, 4, 5, 6]
assert u.blocks() == [[1, 2, 3, 4, 5, 6]]
assert u.validate()
```

### 10.5. Trường hợp rỗng và một phần tử

```python
u = UnrolledList(block_capacity=6)

assert len(u) == 0
assert u.block_count == 0
assert u.blocks() == []
assert u.validate()

u.append(None)
assert len(u) == 1
assert u.get(0) is None
assert u.validate()

assert u.pop(0) is None
assert len(u) == 0
assert u.block_count == 0
assert u.validate()
```

Việc chấp nhận `None` như một giá trị hợp lệ cho thấy sentinel là **một đối tượng cấu trúc riêng**, không phải một giá trị phần tử đặc biệt.

### 10.6. Đọc, sửa và tìm lỗi chỉ số

```python
u = UnrolledList([10, 20, 30], block_capacity=4)

assert u.get(1) == 20
assert u.set(1, 99) == 20
assert u.to_list() == [10, 99, 30]

try:
    u.get(-1)
except IndexError:
    pass
else:
    raise AssertionError("Phải từ chối chỉ số âm")

try:
    u.insert(5, 0)
except IndexError:
    pass
else:
    raise AssertionError("Phải từ chối chỉ số ngoài n")
```

Mã không dùng trực tiếp chính sách chỉ số âm của `list` Python. Quy tắc chỉ số được định nghĩa tường minh trong hợp đồng của `UnrolledList`.

## 11. Vì sao tách, mượn và gộp giữ đúng thứ tự?

### 11.1. Tách khối

Một khối có dãy:

\[
S=A+B.
\]

Khi tách tại `mid`:

- Khối cũ giữ phần đầu `A`.
- Khối mới giữ phần sau `B`.
- Liên kết được nối theo thứ tự: **khối A rồi khối B**.

Vì vậy, thứ tự logic là:

\[
inorderBlocks'=A+B=S.
\]

Tách **không tự thêm hoặc xóa phần tử**; sự thay đổi số phần tử chỉ xảy ra ở phép chèn dẫn tới tách.

### 11.2. Mượn từ khối phải

Giả sử hai khối kề chứa:

\[
A=[a_1,\ldots,a_p],\qquad
B=[b_1,b_2,\ldots,b_q].
\]

Mượn phần tử đầu `b_1` từ B về **cuối A**:

\[
A'=[a_1,\ldots,a_p,b_1],
\qquad
B'=[b_2,\ldots,b_q].
\]

Khi nối:

\[
A'+B'=A+B.
\]

Do đó thứ tự logic không đổi.

### 11.3. Mượn từ khối trái

Nếu khối bên trái là:

\[
A=[a_1,\ldots,a_p]
\]

và bên phải là:

\[
B=[b_1,\ldots,b_q],
\]

mượn **phần tử cuối `a_p`** của A vào **đầu B**:

\[
A'=[a_1,\ldots,a_{p-1}],
\]

\[
B'=[a_p,b_1,\ldots,b_q].
\]

Khi đó vẫn có `A'+B'=A+B`.

### 11.4. Gộp khối

Gộp hai khối kề `A` rồi `B` thành một khối có:

\[
C=A+B.
\]

Sau khi sửa liên kết, nơi trước đây lưu `A,B` giờ lưu `C`, nên thứ tự logic vẫn đúng.

### 11.5. Chứng minh tổng thể theo quy nạp thao tác

**Cơ sở:** danh sách rỗng có tổng kích thước `0`, không có khối dữ liệu và liên kết sentinel hợp lệ.

**Bước chèn:**

1. Tìm đúng vị trí `i`.
2. Chèn một phần tử vào đúng offset trong khối.
3. Nếu vượt sức chứa, tách khối nhưng không thay thứ tự dãy.
4. Tăng `n` đúng một.

**Bước xóa:**

1. Tìm đúng vị trí `i`.
2. Bỏ đúng một phần tử và giảm `n` một.
3. Nếu khối thiếu, mượn hoặc gộp với khối kề nhưng không làm đổi dãy logic còn lại.
4. Giữ mức lấp đầy và liên kết hợp lệ.

Vì thế, nếu trạng thái trước thao tác đúng và các hàm nội bộ giữ hợp đồng, trạng thái sau thao tác vẫn là một **unrolled linked list hợp lệ** biểu diễn đúng dãy logic.

## 12. Phân tích độ phức tạp chi tiết

Ký hiệu:

- `n`: tổng số phần tử.
- `B`: sức chứa tối đa mỗi khối.
- `L=B/2`: ngưỡng lấp đầy tối thiểu khi có nhiều khối.
- `m`: số khối; với mức lấp đầy, `m=O(1+n/B)`.

### 12.1. Bảng thời gian

| Thao tác | Thời gian theo `n,B` | Ghi chú |
|---|---|---|
| `len(u)` | `O(1)` | Dùng biến `_size` |
| Đọc `get(i)` | `O(1+n/B)` | Quét khối rồi đọc mảng `O(1)` |
| Sửa `set(i,x)` | `O(1+n/B)` | Quét khối, gán mảng `O(1)` |
| Chèn `insert(i,x)` | `O(1+n/B+B)` | Tìm khối và dời/tách tối đa `O(B)` |
| Xóa `pop(i)` | `O(1+n/B+B)` | Tìm khối, dời, mượn/gộp tối đa `O(B)` |
| `append(x)` | `O(B)` trường hợp xấu nhất theo `B` | Có tail pointer; có thể tách khối |
| Đọc khi đã có `block,offset` | `O(1)` | Không tìm từ đầu |
| Tháo/gắn liên kết một khối đã biết | `O(1)` | Chỉ con trỏ, chưa tính chép phần tử |
| Duyệt toàn bộ giá trị | `O(n+m)=O(n)` | Duyệt từng khối và từng phần tử |
| `to_list()` | `O(n)` | Tạo danh sách đầu ra |
| Tìm giá trị tùy ý `x` | `O(n)` | Không có thứ tự theo giá trị |
| `validate()` | `O(m)` | Kiểm tra cấu trúc các khối |

**Không thể kết luận** `get(i)=O(1)` tổng thể chỉ vì mỗi khối là một mảng, bởi còn phải tìm đúng khối trong chuỗi liên kết.

### 12.2. Chi phí thao tác khi biết khối

Nếu mã gọi đã có một con trỏ đến khối thích hợp:

- `block.values[offset]`: `O(1)`.
- `block.values.insert(offset,x)`: `O(B)` xấu nhất.
- `block.values.pop(offset)`: `O(B)` xấu nhất.
- Tách hoặc gộp hai khối: `O(B)`.
- Chỉ đổi liên kết giữa khối: `O(1)`.

Điều này cho thấy **nguồn chi phí khác nhau**: tìm vị trí toàn dãy theo liên kết và di chuyển dữ liệu bên trong mảng nhỏ.

### 12.3. Bộ nhớ

Một mô hình với mỗi khối có mảng cố định `B` ô và hai con trỏ cần:

\[
O(mB+m)
\]

ô bộ nhớ, cộng các metadata hằng số.

Vì `m=O(1+n/B)`, dung lượng khối có thể bị chặn:

\[
O(n+B).
\]

Nếu `n≥B` và giữ mức lấp đầy, dung lượng cấp cho dữ liệu là **`O(n)`**. Nếu `n<B` nhưng vẫn có một khối mảng cố định `B` ô, chi phí có thể là **`O(B)`** dù danh sách chỉ chứa một phần tử.

Trong **cài đặt Python** ở mục 9, các `values` là danh sách biến độ dài, nên tổng số tham chiếu phần tử đang dùng là `n` và chi phí quản lý khối là `O(m)` về bậc tăng trưởng, chưa tính vùng dự phòng nội bộ của từng `list`. Bộ nhớ có thể phân mảnh và các đối tượng Python có chi phí riêng.

### 12.4. So với danh sách liên kết từng phần tử

Nếu một linked list lưu **mỗi phần tử trong một nút**, nó cần khoảng `n` nút và `O(n)` liên kết.

Với unrolled linked list, số khối khoảng:

\[
m=O(n/B).
\]

Số trường con trỏ giữa các khối giảm theo cùng tỷ lệ bậc này, với giả thiết các khối được lấp đầy đủ. Đổi lại, một lần sửa trong khối có thể cần dịch **`O(B)` phần tử**.

Về Big-O bộ nhớ tổng thể, cả hai đều có thể là `O(n)`, nhưng **hệ số hằng, cấp phát và tính cục bộ bộ nhớ** khác nhau đáng kể.

## 13. Bài toán tìm kiếm theo giá trị và thứ tự dữ liệu

### 13.1. Dãy không mặc định được sắp theo giá trị

Danh sách khối trong bài lưu:

```text
[8, 1, 5, 1, 9, 3]
```

giữ **đúng thứ tự người dùng chèn**. Việc các phần tử nằm trong mảng nhỏ không có nghĩa chúng được sắp tăng dần.

Do đó:

- Tìm một giá trị `x` bất kỳ vẫn có thể phải duyệt đủ `n` phần tử: **`O(n)`**.
- Tìm phần tử thứ `i` dùng vị trí trong các khối: **`O(n/B)`**.
- Không thể dùng tìm kiếm nhị phân toàn bộ dãy nếu dữ liệu không sắp và không có chỉ mục phù hợp.

### 13.2. Nếu các khối được sắp thì sao?

Một biến thể có thể duy trì:

- Các phần tử **trong mỗi khối** được sắp.
- Một chỉ mục theo **giá trị đầu/cuối** của khối.
- Thứ tự các khối theo khóa.

Khi đó, ta đã tiến gần các cấu trúc **block-based ordered sequence**, **B-tree/B+ tree** hoặc các thiết kế chỉ mục lai. Cần chứng minh riêng quy tắc tìm khóa và bảo trì khi tách/gộp.

**Không thể lấy độ phức tạp của B-tree rồi gán cho unrolled linked list chỉ có `prev/next`**, vì danh sách khối cơ bản không có cấu trúc chỉ mục cây để chọn khối theo khóa trong `O(\log n)`.

## 14. Có thể tăng tốc truy cập theo vị trí bằng chỉ mục phụ không?

Cấu trúc cơ bản tìm chỉ số bằng cách **cộng kích thước từng khối**, nên cần tới `O(n/B)` bước.

Nếu muốn nhanh hơn, có thể xây một cấu trúc chỉ mục phụ lưu:

```text
Khối A: 4 phần tử
Khối B: 5 phần tử
Khối C: 3 phần tử
Khối D: 6 phần tử
```

Một chỉ mục theo tổng tiền tố sẽ giúp biết vị trí `i` thuộc khối nào mà không cần quét toàn bộ khối trước đó.

Một số lựa chọn:

- **Cây cân bằng** chứa mỗi khối là một nút lá và lưu **số phần tử của cây con**: tìm khối theo rank bằng đường cây.
- **Fenwick tree hoặc segment tree** trên các kích thước khối, nếu có cách duy trì chỉ số khối khi chèn/xóa khối.
- **Skip list có span/width** để đi theo số phần tử đã bỏ qua.

### 14.1. Lợi ích và chi phí

Nếu dùng một cây chỉ mục cân bằng trên `m` khối:

- Xác định khối chứa chỉ số `i` có thể giảm từ `O(m)` xuống **`O(\log m)`**.
- Thao tác nội bộ khối vẫn có thể cần **`O(B)`** để dịch giá trị.
- Sau tách/gộp, phải cập nhật **kích thước khối và tổng kích thước cây con** dọc đường chỉ mục.

Với chỉ mục được bảo trì đúng, một thao tác theo vị trí có thể đạt dạng:

\[
O(\log m+B).
\]

Nhưng đây **không còn là danh sách khối cơ bản chỉ có các liên kết tuyến tính**. Chúng ta đã thêm một lớp cấu trúc dữ liệu khác, cần trả chi phí triển khai và bảo trì.

### 14.2. Liên hệ với cây tăng cường

Trong cây Order-Statistic Tree hoặc implicit treap, kích thước cây con giúp xác định phần tử thứ `k` **trên một đường trong cây**. Unrolled linked list cơ bản không có các cây con để cộng trực tiếp; nó chỉ có **chuỗi các khối**.

Nếu thêm một cây chỉ mục kích thước khối, ta đã kết hợp:

- **Lưu các phần tử thành khối liên tiếp** ở tầng lá.
- **Liên kết/tổ chức theo cây có metadata kích thước** ở tầng chỉ mục.

Đây là một hướng thiết kế gần với **rope** hoặc một cây có **lá là các chunk**. Sự kết hợp giúp xử lý dãy lớn linh hoạt hơn, nhưng phức tạp hơn danh sách khối chỉ có `prev/next`.

## 15. So sánh với array, linked list, deque, gap buffer, rope và treap

### 15.1. Bảng đối chiếu

| Cấu trúc | Truy cập theo chỉ số | Chèn/xóa ở giữa | Tính chất chính |
|---|---|---|---|
| Mảng động | `O(1)` | `O(n)` xấu nhất do dời phần đuôi | Dữ liệu/tham chiếu liên tiếp |
| Danh sách liên kết từng phần tử | `O(n)` | `O(1)` nếu đã có nút và vị trí liên kết | Nhiều nút, nhiều con trỏ |
| **Unrolled linked list** | **`O(n/B)`** | **`O(n/B+B)`** | Mỗi nút chứa một khối liên tiếp |
| Deque vòng trên mảng | Phụ thuộc hiện thực; thường `O(1)` tại hai đầu | Chèn/xóa giữa thường không phải lợi thế chính | Tối ưu hai đầu |
| Gap buffer | `O(1)` đọc ký tự | Tại gap `O(1)`, di chuyển gap `O(d)` | Tối ưu sửa quanh một con trỏ |
| Rope cân bằng | Thường `O(\log n)` theo độ dài/chunk | Theo thiết kế split/concat | Cây chứa các khối văn bản |
| Implicit treap | `O(\log n)` **kỳ vọng** | `O(\log n)` **kỳ vọng** | Cây theo vị trí, split/merge |

**Các dòng rope/deque phụ thuộc biến thể và hiện thực.** Các giá trị của danh sách khối là cho mô hình **có `O(n/B)` khối** nhờ duy trì mức lấp đầy, không có chỉ mục phụ.

### 15.2. Vì sao có thể duyệt nhanh hơn danh sách liên kết thường?

Khi duyệt:

- Linked list từng phần tử thường cần **đọc một con trỏ để tới phần tử tiếp theo**.
- Unrolled list đọc nhiều phần tử **trong một khối mảng** trước khi theo `next` sang khối khác.

Điều này có thể giảm:

- Số lần lần theo con trỏ.
- Số nút phải cấp phát.
- Chi phí bộ nhớ metadata trên mỗi phần tử.
- Một phần lỗi cache do truy cập phân tán.

Nhưng hiệu quả thực tế còn phụ thuộc cache, kích thước khối, kiểu phần tử và bộ cấp phát. Không có bảo đảm rằng mọi unrolled list sẽ **luôn nhanh hơn** mảng khi duyệt tuyến tính.

### 15.3. Tại sao vẫn cần cân nhắc mảng?

Nếu thao tác chủ yếu là:

```text
get(0), get(1000), get(500000), ...
```

với truy cập ngẫu nhiên rất nhiều, mảng động có lợi thế rõ ràng vì mỗi lần đọc theo chỉ số là `O(1)`. Danh sách khối cơ bản phải **tìm khối**, dù số khối ít hơn số phần tử.

Nếu chủ yếu thao tác **chèn/xóa gần một iterator đã có** rồi duyệt liên tục, unrolled list có thể phù hợp hơn.

## 16. Biến thể dùng khối cố định và khối biến độ dài

### 16.1. Khối cố định

Mỗi nút cấp phát ngay mảng `B` ô:

```text
values = [slot0, slot1, ..., slot(B-1)]
count = số ô đầu đang dùng
```

Ưu điểm:

- Số ô mỗi khối xác định.
- Có thể bố trí trường metadata và mảng trong một cấu trúc bộ nhớ cụ thể.
- Tránh cấp phát lại mảng nội bộ khi chèn/xóa trong giới hạn `B`.

Nhược điểm:

- Có thể lãng phí các ô không sử dụng.
- Di chuyển các đối tượng lớn khi chèn/xóa trong khối có thể tốn kém.
- Phải quản lý rõ `count` và các ô trống.

### 16.2. Khối biến độ dài

Mỗi khối chứa một `list`/`vector` với giới hạn độ dài không vượt `B`.

Ưu điểm:

- Dễ viết bằng ngôn ngữ cấp cao.
- Không cần quản lý thủ công các ô trống nội bộ.
- Hợp với phần tử là tham chiếu hoặc đối tượng có cơ chế di chuyển thích hợp.

Nhược điểm:

- Mỗi mảng nhỏ có metadata bộ nhớ riêng.
- Có thể phát sinh cấp phát lại bên trong `list/vector`.
- Việc cấp phát từng khối có thể gây phân mảnh.

Mã Python của bài dùng cách này để minh họa **thuật toán tách–mượn–gộp** rõ ràng. Hai cách đều dựa trên **cùng bất biến thứ tự và sức chứa**.

## 17. Tính ổn định của iterator và quyền sở hữu dữ liệu

### 17.1. Iterator vào phần tử có thể mất hiệu lực

Giả sử một iterator lưu:

```text
(block, offset)
```

Sau khi chèn trước vị trí đó trong cùng khối:

- Các phần tử có thể bị dịch offset.
- Nếu khối bị tách, phần tử có thể chuyển sang khối mới.
- Nếu gộp, một khối có thể bị tháo khỏi danh sách.

Vì vậy, cặp `(block,offset)` **không tự động là một handle ổn định** sau mọi phép cập nhật.

Nếu ứng dụng cần tham chiếu bền tới một đối tượng cụ thể, có thể lưu **ID riêng** của đối tượng hoặc dùng cơ chế ánh xạ handle phù hợp. Điều đó có chi phí và bất biến bổ sung.

### 17.2. Tháo/gộp khối và tham chiếu cũ

Trong hàm `_unlink_block`, mã đặt:

```python
block.prev = None
block.next = None
```

sau khi tháo khỏi danh sách. Điều này giúp phát hiện việc sử dụng sai một **khối đã bị loại**.

Tuy nhiên, nếu mã ngoài vẫn giữ tham chiếu trực tiếp tới `block.values`, nó vẫn có thể quan sát hoặc sửa dữ liệu của khối không còn thuộc danh sách.

Vì vậy, API công khai trong bài chỉ cho phép người dùng lấy:

- Giá trị qua `get`.
- Bản sao mảng các khối qua `blocks()`.
- Dãy kết quả qua `to_list()`.

Không công khai quyền ghi trực tiếp vào các liên kết và mảng nội bộ.

### 17.3. Lưu phần tử lớn

Nếu mỗi phần tử là một đối tượng lớn, việc chuyển **đối tượng thực** giữa các khối có thể tốn kém. Một lựa chọn là lưu **tham chiếu hoặc con trỏ** tới đối tượng trong các mảng khối, chỉ di chuyển con trỏ khi tách/gộp.

Mã Python tự nhiên di chuyển **tham chiếu đối tượng**, không sao chép sâu đối tượng trong `values`. Nhưng ứng dụng vẫn cần quản lý rõ **định danh và vòng đời đối tượng**.

## 18. Tự kiểm tra bằng mô hình tham chiếu

### 18.1. Vì sao chỉ kiểm tra liên kết chưa đủ?

Một danh sách khối có thể:

- Có đủ liên kết hai chiều.
- Không khối nào vượt `B`.
- Tổng số phần tử đúng bằng `n`.

nhưng **thứ tự giá trị bị thay đổi** do mượn sai đầu khối.

Ví dụ:

```text
Dãy mong đợi:
[10,20,30,40]

Dãy lỗi:
[10,30,20,40]
```

Cả hai đều có cùng số phần tử. Validator cấu trúc có thể trả đúng, nhưng ngữ nghĩa của thao tác chèn/xóa đã sai.

Vì vậy khi học nên đối chiếu với một **Python list thông thường** làm mô hình tham chiếu.

### 18.2. Một chuỗi thao tác đối chiếu

```python
reference = [10, 20, 30, 40, 50, 60]
u = UnrolledList(reference, block_capacity=6)

assert u.to_list() == reference
assert u.validate()

# Chèn.
reference.insert(3, 35)
u.insert(3, 35)
assert u.to_list() == reference
assert u.validate()

# Xóa gây mượn.
assert u.pop(1) == reference.pop(1)
assert u.to_list() == reference
assert u.validate()

# Xóa gây gộp.
assert u.pop(1) == reference.pop(1)
assert u.to_list() == reference
assert u.validate()

# Thêm cuối và sửa một giá trị.
reference.append(70)
u.append(70)
assert u.set(0, 5) == reference[0]
reference[0] = 5

assert u.to_list() == reference
assert len(u) == len(reference)
assert u.validate()
```

### 18.3. Đề xuất các kiểm thử biên

Nên có các trường hợp:

- Khởi tạo từ dãy rỗng.
- Chèn/xóa phần tử duy nhất.
- Chèn ở đầu, cuối, ranh giới hai khối và giữa một khối.
- Chèn đúng lúc khối có `B` phần tử → **tách**.
- Xóa để khối còn `L-1` phần tử → **mượn**.
- Xóa khi hai khối kề chỉ còn đúng ngưỡng `L` → **gộp**.
- Xóa trong khối cuối khi chỉ có thể mượn/gộp với khối trái.
- Truy cập phần tử đầu và cuối.
- Chỉ số `-1`, `n` và `n+1` theo hợp đồng.
- Giá trị trùng nhau, giá trị `None`, chuỗi và đối tượng.
- Chuỗi thao tác chèn/xóa dài làm số khối tăng rồi giảm nhiều lần.

Các `assert` trong bài là **ví dụ để người học tự chạy và kiểm chứng**, không phải tuyên bố đã chạy test tự động trong tác vụ biên soạn.

## 19. Những sai lầm phổ biến

1. **Cho rằng mỗi nút liên kết chỉ lưu một phần tử.** Điểm khác biệt của unrolled list là **mỗi nút lưu một khối**.
2. **Chỉ xét `len(values)≤B` mà không kiểm soát mức lấp đầy.** Nhiều khối gần rỗng làm số liên kết tăng.
3. **Nhầm độ dài khối với độ dài toàn dãy.** `n` là tổng độ dài tất cả khối.
4. **Không cập nhật `_size` sau chèn/xóa.** Kết quả `len` và kiểm tra chỉ số có thể sai.
5. **Không cập nhật `_block_count` khi tách hoặc gộp.** Validator và phân tích số khối mất chính xác.
6. **Dùng chỉ số toàn dãy trực tiếp bên trong khối.** Phải trừ kích thước những khối đã đi qua.
7. **Cho rằng phần tử trong khối truy cập `O(1)` kéo theo `get(i)=O(1)`.** Còn chi phí tìm khối.
8. **Dùng `list.insert` vào khối đầy nhưng không tách.** Phá giới hạn `B`.
9. **Tách khối làm đảo hoặc bỏ sót phần tử.** Phải giữ phần đầu ở khối trước và phần sau ở khối mới.
10. **Tách khối tại vị trí khiến một khối dưới ngưỡng `L`.** Mất bảo đảm `m=O(n/B)`.
11. **Chèn khối mới nhưng quên cập nhật một trong bốn liên kết đôi.** Có thể tạo liên kết bất đối xứng.
12. **Xóa một phần tử rồi bỏ qua việc mượn/gộp khi khối dưới ngưỡng.** Phá occupancy invariant.
13. **Mượn phần tử giữa khối kề thay vì phần tử ở ranh giới.** Làm sai thứ tự logic.
14. **Mượn từ khối có đúng `L` phần tử.** Làm khối cho mượn trở thành dưới ngưỡng.
15. **Gộp hai khối mà không kiểm tra khả năng chứa đủ.** Có thể vượt sức chứa `B`.
16. **Xóa khối cuối nhưng không sửa `sentinel.prev`.** Tham chiếu tail có thể trỏ vào khối đã tháo.
17. **Cho phép xóa sentinel như một khối dữ liệu.** Sentinel không thuộc dãy logic.
18. **Quên xử lý khối duy nhất khi xóa hết phần tử.** Danh sách rỗng không nên giữ một khối dữ liệu rỗng ngoài sentinel.
19. **Cho rằng unlink khối `O(1)` nghĩa là xóa phần tử theo chỉ số `O(1)`.** Tìm khối và dịch nội bộ vẫn tốn thời gian.
20. **Dùng B rất nhỏ hoặc B rất lớn mà không xét workload.** Có thể trả giá ở khâu đi qua khối hoặc dịch trong khối.
21. **Khẳng định chọn `B≈√n` luôn tối ưu thực tế.** Nó chỉ cân bằng mô hình `n/B+B`, chưa xét cache và cấp phát.
22. **Giữ B cố định từ n ban đầu nhưng vẫn áp kết luận `O(\sqrt n)` cho mọi n sau này.** Có thể cần đổi B và xây lại.
23. **Mặc định dữ liệu tự sắp theo giá trị vì nằm trong mảng.** Thứ tự của unrolled list là **thứ tự chèn**, không phải thứ tự khóa.
24. **Gán độ phức tạp B-tree cho danh sách khối không có chỉ mục cây.** Danh sách liên kết các khối không tự cho truy cập logarit.
25. **Không phân biệt số khối `m` với số phần tử `n`.** Mỗi bước `next` đi qua một khối, không phải một phần tử.
26. **Giữ một iterator `(block,offset)` qua split/merge mà không kiểm tra hiệu lực.** Phần tử có thể chuyển khối hoặc đổi offset.
27. **Cho mã ngoài sửa trực tiếp `values` hoặc `prev/next`.** Có thể phá toàn bộ bất biến.
28. **Coi Python list chứa toàn bộ object liên tục.** Nó lưu các tham chiếu liên tiếp, đối tượng có thể nằm rải rác.
29. **Dùng mảng cố định B ô nhưng báo bộ nhớ chỉ `O(n)` trong mọi trường hợp.** Với một khối nhỏ, còn có chi phí tối thiểu `O(B)`.
30. **Đánh giá hiệu năng chỉ bằng Big-O mà bỏ qua kích thước đối tượng và cache.** Cục bộ bộ nhớ là lợi thế phụ thuộc hiện thực.
31. **Chỉ chạy validator liên kết mà không đối chiếu thứ tự dãy.** Có thể đảo giá trị mà liên kết vẫn hợp lệ.
32. **Cho rằng tìm giá trị `x` nhanh hơn `O(n)` chỉ vì dữ liệu được chia khối.** Nếu không sắp và không có chỉ mục giá trị, vẫn cần quét.
33. **Gọi validator trên mọi thao tác sản xuất rồi tính chèn/xóa chỉ `O(n/B+B)`.** Cần cộng chi phí validation riêng.
34. **Không đồng bộ khi có nhiều luồng sửa cấu trúc.** Người đọc có thể quan sát trạng thái tách/gộp đang thực hiện dở.
35. **Tưởng khối liền kề về liên kết cũng liền kề vật lý.** Các khối có thể được cấp phát ở các vùng bộ nhớ khác nhau.
36. **Quên kiểm tra chỉ số ngoài phạm vi và chính sách chỉ số âm.** Hợp đồng API phải thống nhất.
37. **Tuyên bố danh sách khối là cây tăng cường.** Nó là cấu trúc lai **mảng trong nút liên kết**, chỉ trở thành thiết kế cây khi thêm tầng chỉ mục cây riêng.

## 20. Bài tập thực hành có đáp án

### Bài 1. Nhận diện cấu trúc

So sánh cách lưu sáu giá trị `[10,20,30,40,50,60]` bằng linked list từng phần tử và unrolled list có `B=3`.

**Đáp án:** Linked list thường có sáu nút dữ liệu, mỗi nút lưu một giá trị. Unrolled list có thể dùng **hai khối**: `[10,20,30]` và `[40,50,60]`, mỗi khối chứa một mảng nhỏ và liên kết với khối kia.

### Bài 2. Tính số phần tử

Ba khối lần lượt có `4`, `6` và `3` phần tử. Độ dài logic `n` bằng bao nhiêu?

**Đáp án:** `n=4+6+3=13`.

### Bài 3. Kiểm tra mức lấp đầy

Với `B=6,L=3` và có hai khối kích thước `2` và `5`, cấu trúc có hợp lệ theo quy tắc bài này không?

**Đáp án:** **Không.** Khối đầu có `2<L=3`. Cần mượn từ khối thứ hai hoặc gộp.

### Bài 4. Chặn trên số khối

Nếu mọi khối khi `m≥2` có ít nhất `B/2` phần tử, chứng minh `m≤2n/B`.

**Đáp án:** Từ `n=\sum s_i` và `s_i≥B/2`, suy ra `n≥mB/2`; do đó `m≤2n/B`.

### Bài 5. Tìm phần tử theo chỉ số

Có các khối:

```text
[10 20 30] <-> [40 50 60 70] <-> [80 90 100]
```

Phần tử tại chỉ số logic `5` là gì?

**Đáp án:** **`60`**. Bỏ qua `3` phần tử khối đầu, offset trong khối thứ hai là `5-3=2`.

### Bài 6. Chi phí `get(i)`

Tại sao `get(i)` của unrolled list cơ bản không có bảo đảm `O(1)` như mảng?

**Đáp án:** Vì phải **đi qua các khối** để tìm khối chứa `i`, tốn `O(n/B)` bước khi các khối đủ đầy; chỉ bước đọc phần tử trong khối là `O(1)`.

### Bài 7. Chèn trong khối chưa đầy

Với `B=6`, khối `[10,20,30,40]` chèn `25` trước `30`. Kết quả?

**Đáp án:** `[10,20,25,30,40]`. Chưa cần tách vì khối có `5≤6` phần tử.

### Bài 8. Tách khi khối đầy

Với `B=6`, khối `[10,20,30,40,50,60]` chèn `35` trước `40`. Chia theo quy tắc `middle=floor(7/2)`, được gì?

**Đáp án:** Hai khối **`[10,20,30]`** và **`[35,40,50,60]`**.

### Bài 9. Chi phí split block

Tách một khối có `B+1` phần tử thành hai khối tốn thời gian bao nhiêu theo `B` nếu phải sao chép/move phần tử?

**Đáp án:** **`O(B)`**, vì chỉ di chuyển phần tử trong khối có độ dài tối đa `B+1`.

### Bài 10. Mượn từ khối phải

Hai khối `[10,30]` và `[35,40,50,60]`, `L=3`. Cách mượn đúng để giữ thứ tự?

**Đáp án:** Lấy phần tử **`35` đầu khối phải** đưa tới **cuối khối trái**, được `[10,30,35]` và `[40,50,60]`.

### Bài 11. Mượn từ khối trái

Hai khối `[10,20,30,40]` và `[50,60]`, `L=3`. Cách mượn đúng?

**Đáp án:** Lấy **`40` cuối khối trái** đưa tới **đầu khối phải**, được `[10,20,30]` và `[40,50,60]`.

### Bài 12. Gộp khi không mượn được

Hai khối `[10,35]` và `[40,50,60]`, `B=6,L=3`. Có thể gộp không? Kết quả?

**Đáp án:** Có. Gộp thành **`[10,35,40,50,60]`** dài `5≤6`, rồi tháo một nút khối khỏi danh sách.

### Bài 13. Tại sao không tràn sau gộp?

Khối thiếu sau xóa còn `L-1` phần tử; khối kế bên không thể cho mượn vì chỉ có `L`. Với `B=2L`, độ dài gộp?

**Đáp án:** `(L-1)+L=2L-1=B-1≤B`. Hai khối có thể nằm trong một khối.

### Bài 14. Chèn cuối với tail pointer

Nếu giữ con trỏ tới khối cuối, `append(x)` có nhất thiết đi qua `O(n/B)` khối không?

**Đáp án:** **Không.** Có thể truy cập trực tiếp khối cuối. Chi phí nội bộ có thể `O(B)` khi phải tách, nhưng không phải quét từ đầu.

### Bài 15. Khi đã có khối

Nếu đã biết chính xác `block` và `offset`, đọc phần tử tại offset mất bao nhiêu?

**Đáp án:** **`O(1)`** trong mô hình mảng hỗ trợ truy cập theo chỉ số hằng thời gian.

### Bài 16. Tổng chi phí chèn/xóa theo vị trí

Vì sao biểu thức `O(n/B+B)` xuất hiện?

**Đáp án:** `n/B` là số khối có thể phải đi qua để tìm vị trí; `B` là số phần tử tối đa có thể phải dịch/tách/gộp trong các khối cục bộ.

### Bài 17. Lựa chọn `B≈√n`

Với mô hình chi phí `f(B)=n/B+B`, nên chọn `B` bậc nào để cân bằng hai hạng?

**Đáp án:** **`B≈√n`**, cho `f(B)=O(\sqrt n)`. Đây là phân tích lý thuyết; chọn B thực tế còn tùy cache và workload.

### Bài 18. Bộ nhớ mảng cố định

Nếu danh sách chỉ có một phần tử nhưng mỗi khối cấp sẵn `B=1024` ô, có thể kết luận chi phí ô dữ liệu là `O(1)` theo mọi tham số không?

**Đáp án:** **Không.** Nếu `B` là một tham số, một khối vẫn cấp **`O(B)`** ô dù chỉ chứa một phần tử. Nếu coi B là hằng cố định, biểu diễn Big-O theo n riêng sẽ khác.

### Bài 19. Duyệt toàn bộ

Với `n` phần tử chia trong `m` khối, chi phí duyệt từng phần tử là bao nhiêu?

**Đáp án:** **`O(n+m)=O(n)`** khi các khối dữ liệu đều không rỗng và do đó `m≤n`.

### Bài 20. Tìm theo giá trị

Các khối lưu `[8,1,5]` và `[1,9,3]` không theo thứ tự giá trị. Tìm xem có phần tử `9` hay không có bảo đảm nhanh hơn `O(n)` không?

**Đáp án:** **Không.** Không có thứ tự hoặc chỉ mục khóa thì trường hợp xấu nhất vẫn phải quét đủ `n` phần tử.

### Bài 21. Iterator sau split

Một iterator lưu `(block,offset)` trỏ tới phần tử đang ở giữa một khối. Nếu khối bị tách do chèn, iterator có chắc còn đúng không?

**Đáp án:** **Không.** Phần tử có thể chuyển sang khối mới hoặc đổi offset. Cần quy tắc vô hiệu hóa/cập nhật iterator hoặc handle ổn định riêng.

### Bài 22. Kiểm tra sentinel

Khi danh sách rỗng dùng sentinel vòng, hai trường `sent.next` và `sent.prev` phải trỏ tới đâu?

**Đáp án:** **Chính sentinel**. Đây là vòng có chủ đích, khác với chu trình lỗi trong các khối dữ liệu.

### Bài 23. Sửa liên kết khi chèn khối

Đang có `A<->N`, muốn chèn khối `X` ngay sau A. Cần thiết lập các liên kết gì?

**Đáp án:** `X.prev=A`, `X.next=N`, `A.next=X`, `N.prev=X`.

### Bài 24. Xóa khối dữ liệu cuối cùng

Danh sách chỉ còn một khối chứa một phần tử. Sau khi xóa phần tử ấy, cần trạng thái gì?

**Đáp án:** Tổng phần tử `n=0`, số khối `m=0`, sentinel trỏ vào chính nó theo cả hai hướng. Không giữ khối dữ liệu rỗng.

### Bài 25. So với gap buffer

Vì sao gap buffer có thể phù hợp hơn unrolled list khi người dùng gõ liên tiếp tại một con trỏ?

**Đáp án:** Gap buffer giữ **một vùng trống ngay tại con trỏ**, nên chèn liên tiếp có thể `O(1)` mỗi ký tự khi còn chỗ. Unrolled list cần quản lý các khối và có thể phải tìm vị trí/tách khối; hiệu quả tùy cách lưu handle và kích thước B.

### Bài 26. So với implicit treap

Nếu thường xuyên cần truy cập một chỉ số ngẫu nhiên trong dãy rất dài, implicit treap có lợi thế độ phức tạp nào so với unrolled list cơ bản?

**Đáp án:** Implicit treap có thể tìm phần tử theo rank trong **`O(\log n)` kỳ vọng** dưới giả thiết priority ngẫu nhiên phù hợp; unrolled list cơ bản cần **`O(n/B)`** bước tìm khối.

### Bài 27. Thêm chỉ mục phụ

Muốn giảm chi phí tìm khối theo chỉ số, có thể bổ sung cấu trúc nào?

**Đáp án:** Một **cây cân bằng lưu tổng kích thước các khối**, Fenwick/segment tree được duy trì phù hợp khi khối đổi số lượng, hoặc skip list có span. Các cấu trúc này bổ sung chi phí và bất biến riêng.

### Bài 28. Python list và bộ nhớ

Tại sao mảng `values` là `list` Python không đồng nghĩa mọi đối tượng trong khối nằm sát nhau trong bộ nhớ?

**Đáp án:** Python list thường lưu **tham chiếu tới đối tượng** liên tiếp; đối tượng có thể được cấp phát ở nhiều vị trí khác nhau. Dù vậy, duyệt mảng tham chiếu vẫn có thể có lợi so với đi theo con trỏ từng phần tử.

### Bài 29. Kiểm thử bằng mô hình tham chiếu

Nêu một cách phát hiện lỗi mượn khiến thứ tự phần tử thay đổi dù độ dài khối vẫn hợp lệ.

**Đáp án:** Duy trì một **Python list tham chiếu** và áp dụng cùng chuỗi chèn/xóa; sau mỗi bước, so sánh `u.to_list()` với list tham chiếu, đồng thời gọi `u.validate()` để kiểm tra liên kết/kích thước.

### Bài 30. Chọn cấu trúc cho workload

Một ứng dụng chủ yếu duyệt tuần tự hàng triệu phần tử và chèn một ít phần tử quanh vị trí đang duyệt, không đòi hỏi truy cập ngẫu nhiên rất nhanh. Danh sách khối có điểm hấp dẫn gì?

**Đáp án:** Có thể giảm số nút và số lần theo con trỏ so với linked list từng phần tử; chèn/xóa gần **khối đã biết** chỉ ảnh hưởng dữ liệu trong một vài khối, thay vì dời toàn bộ phần đuôi của mảng. Cần chọn B và kiểm nghiệm hiệu năng thực tế.

## 21. Tổng kết

**Danh sách khối (unrolled linked list)** là cấu trúc lai giữa **mảng nhỏ lưu liên tiếp** và **danh sách liên kết các khối**. Dãy logic là phép nối các mảng trong các khối theo thứ tự `next`. Hai bất biến quan trọng nhất là:

\[
\boxed{
n=\sum_i size(block_i),\qquad 1\le size(block_i)\le B
}
\]

và, nếu chọn chính sách mức lấp đầy như bài này, mỗi khối trong danh sách có nhiều khối phải chứa ít nhất:

\[
\boxed{L=B/2}
\]

phần tử khi `B` chẵn.

Nhờ ngưỡng ấy, số khối là **`O(n/B)`**. Truy cập phần tử theo chỉ số cần tìm khối rồi truy cập offset nội bộ, tốn **`O(n/B)`** thời gian. Chèn/xóa theo chỉ số có thêm chi phí dời phần tử và **tách/mượn/gộp khối**, nên chặn trên là **`O(n/B+B)`**. Nếu `B≈\sqrt n`, mô hình lý thuyết cho **`O(\sqrt n)`**; nhưng chọn kích thước khối trong phần mềm thực tế còn phải xét cache, loại dữ liệu và phân bố thao tác.

Danh sách khối có thể giảm chi phí **nút liên kết và cấp phát** so với danh sách liên kết thông thường, đồng thời tránh dời toàn bộ phần đuôi của **mảng lớn** khi sửa một vùng cục bộ. Tuy vậy, nó **không cung cấp truy cập `O(1)` theo chỉ số toàn dãy như mảng**, cũng **không tự cung cấp tìm kiếm theo thứ hạng `O(\log n)` như cây có chỉ mục kích thước**.

Điều cần nhớ là **hai tầng trật tự**: các giá trị giữ thứ tự trong mỗi mảng khối, còn các khối giữ thứ tự qua liên kết. Mọi lần chèn, xóa, tách, mượn hoặc gộp phải bảo toàn cả hai tầng, đồng thời giữ kích thước và liên kết nhất quán. Hiểu được đánh đổi này giúp lựa chọn hợp lý giữa mảng, linked list, gap buffer, rope và các cây tăng cường theo vị trí.
