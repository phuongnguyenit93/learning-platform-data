# Chèn, xóa và chi phí dịch chuyển phần tử

## 1. Khi thay đổi mảng, chuyện gì xảy ra với các phần tử?

Mảng hỗ trợ đọc và cập nhật phần tử theo chỉ số rất nhanh. Tuy nhiên, khi cần **chèn một phần tử vào giữa** hoặc **xóa một phần tử mà vẫn giữ nguyên thứ tự các phần tử còn lại**, ta phải tạo hoặc lấp một khoảng trống trong dãy vị trí. Trong cách biểu diễn mảng liên tiếp, các phần tử đứng phía sau thường phải **dịch chuyển**.

Ví dụ, danh sách lượt xếp hàng được lưu trong mảng theo đúng thứ tự đến:

```text
Ban đầu:     [An, Bình, Chi, Dũng]
Chỉ số:        0    1    2     3

Chèn Lan vào vị trí 1:
             [An, Lan, Bình, Chi, Dũng]
Chỉ số:        0    1    2    3     4
```

Để Bình, Chi và Dũng vẫn đứng sau Lan theo thứ tự ban đầu, ba phần tử phải chuyển sang vị trí có chỉ số lớn hơn một đơn vị. Máy tính không thể chỉ gán `A[1] = Lan` vì phép gán ấy sẽ ghi đè Bình.

Sau bài học, bạn có thể:

- Phân biệt **gán thay thế** một phần tử với **chèn** và **xóa** phần tử.
- Xác định miền chỉ số hợp lệ khi chèn và khi xóa; giải thích vì sao có thể chèn ở vị trí `n` nhưng không thể xóa phần tử `A[n]`.
- Tính chính xác số phần tử cần dịch khi chèn, xóa tại vị trí bất kỳ.
- Mô tả và triển khai hướng dịch phù hợp để tránh ghi đè dữ liệu.
- Phân tích độ phức tạp `O(1)`, `O(n)` và chi phí khấu hao của mảng động.
- Lựa chọn giữa mảng, danh sách liên kết, stack, queue và cấu trúc khác tùy yêu cầu thứ tự và thao tác thường xuyên.

Những nguyên tắc này thuộc chương **Mảng** của học phần **Cấu trúc dữ liệu**, nơi ta học bất biến, phép thao tác và chi phí thời gian, bộ nhớ để so sánh mảng với danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Phân biệt độ dài, sức chứa và ba loại thao tác

Giả sử mảng có `n` phần tử đang sử dụng, đánh chỉ số từ `0`. Nếu dùng một vùng đệm có thể dành trước chỗ trống, gọi `capacity` là số ô tối đa hiện có thể chứa mà chưa cần cấp phát lại. Ta luôn cần giữ:

\[
0\le n\le capacity
\]

Các phần tử đang dùng thuộc miền `[0, n)`, còn những ô từ `n` đến `capacity - 1` chỉ là chỗ dự phòng. Chúng chưa trở thành phần tử có thể truy cập bằng giao diện logic của mảng.

| Thao tác | Điều kiện chỉ số | Độ dài sau thao tác | Hệ quả lên thứ tự |
|---|---|---:|---|
| Gán `A[i] = x` | `0 <= i < n` | `n` | Thay giá trị tại một vị trí; không dịch phần tử |
| Chèn `x` trước vị trí `i` | `0 <= i <= n` | `n + 1` | Các phần tử từ vị trí `i` trở đi dịch phải |
| Xóa phần tử ở vị trí `i` | `0 <= i < n` | `n - 1` | Các phần tử sau `i` dịch trái |

**Vì sao chèn cho phép `i = n`?** Vị trí `n` là ranh giới ngay sau phần tử cuối; chèn tại đó chính là **thêm vào cuối** (*append*), không cần dịch các phần tử đang có. Nhưng `A[n]` vẫn không phải phần tử đã tồn tại để đọc hoặc xóa.

Một sự phân biệt quan trọng khác là **mảng có kích thước cố định** và **mảng động**. Với mảng cố định đã đầy, thao tác tăng số phần tử không thể thực hiện trên cùng vùng chứa nếu không có chỗ dự phòng. Mảng động thường có thể tăng `capacity` bằng cách cấp phát vùng chứa lớn hơn, sao chép dữ liệu rồi chèn phần tử.

## 3. Chèn phần tử và vì sao phải dịch từ phải sang trái

Giả sử mảng `A` có `n = 4` phần tử, `capacity >= 5`, và cần chèn `99` tại chỉ số `i = 1`:

```text
Trước chèn:
  Chỉ số:     0    1    2    3    4
  Giá trị:  [10 | 20 | 30 | 40 | __ ]
  n = 4, ô 4 đang trống

Bước 1: chuyển A[3] sang ô 4:  [10 | 20 | 30 | 40 | 40]
Bước 2: chuyển A[2] sang ô 3:  [10 | 20 | 30 | 30 | 40]
Bước 3: chuyển A[1] sang ô 2:  [10 | 20 | 20 | 30 | 40]
Bước 4: ghi 99 vào ô 1:        [10 | 99 | 20 | 30 | 40]
```

Ta phải **dịch từ cuối về đầu** (`n-1` xuống `i`), để khi chép `A[j-1]` sang `A[j]`, giá trị nguồn ở `j-1` vẫn chưa bị thay thế. Nếu bắt đầu chép từ trái sang phải, việc `A[2] = A[1]` sẽ ghi đè giá trị `30`; bước tiếp theo có thể sao chép nhầm `20` nhiều lần.

Thuật toán với vùng chứa đã đủ chỗ được mô tả như sau:

```text
INSERT(A, n, capacity, i, x)
    require 0 <= i <= n
    require n < capacity

    for j = n down to i + 1:
        A[j] = A[j - 1]

    A[i] = x
    n = n + 1
    return n
```

Khi vòng lặp kết thúc, các phần tử trước `i` giữ nguyên; `A[i]` chứa `x`; phần tử cũ tại `i` đã thành phần tử tại `i+1`. Nếu ký hiệu `A_old` và `A_new` là trạng thái trước/sau, bất biến kết quả là:

\[
\begin{cases}
A_{new}[j]=A_{old}[j] & 0\le j<i,\\
A_{new}[i]=x,\\
A_{new}[j]=A_{old}[j-1] & i<j\le n.
\end{cases}
\]

Ở đây `n` trong công thức là độ dài **trước khi chèn**; độ dài mới là `n+1`.

### Số phần tử phải dịch khi chèn

Các phần tử cũ từ `i` tới `n-1` phải chuyển đi. Số phần tử được dịch là:

\[
\boxed{\operatorname{moves}_{insert}=n-i}
\]

Vì vậy, khi đã có đủ sức chứa:

| Vị trí chèn | Số phần tử dịch | Thời gian |
|---|---:|---|
| Đầu mảng (`i = 0`) | `n` | `O(n)` |
| Giữa mảng (`i \approx n/2`) | Khoảng `n/2` | `O(n)` |
| Cuối mảng (`i = n`) | `0` | `O(1)` nếu còn chỗ |

Ví dụ với `n = 1000`, chèn ở chỉ số `200` cần dịch `1000 - 200 = 800` phần tử. Phép gán vào ô `200` chỉ là một bước cuối cùng; phần lớn chi phí đến từ việc giữ nguyên thứ tự của `800` phần tử đứng sau.

## 4. Xóa phần tử và vì sao phải dịch từ trái sang phải

Xét trạng thái sau khi chèn ở ví dụ trước:

```text
Chỉ số:       0    1    2    3    4
Giá trị:    [10 | 99 | 20 | 30 | 40]
```

Nếu xóa phần tử ở chỉ số `i = 2` (giá trị `20`) mà phải giữ thứ tự:

```text
Bước 1: chuyển A[3] sang ô 2:  [10 | 99 | 30 | 30 | 40]
Bước 2: chuyển A[4] sang ô 3:  [10 | 99 | 30 | 40 | 40]
Bước 3: giảm n từ 5 xuống 4:  [10 | 99 | 30 | 40] | ô ngoài độ dài
```

Lúc này, **dịch từ trái sang phải** (`i` lên `n-2`) là đúng: mỗi phần tử `A[j+1]` được đọc trước khi bị ghi đè trong bước sau. Ô vật lý cuối có thể còn chứa một bản sao cũ, nhưng nó không còn thuộc mảng logic. Với bộ đệm chứa tham chiếu đến đối tượng, cần xóa tham chiếu ở ô không sử dụng nếu cấu trúc phải giải phóng đối tượng; các thư viện mảng động thường tự xử lý phần này.

```text
DELETE(A, n, i)
    require 0 <= i < n

    removed = A[i]
    for j = i to n - 2:
        A[j] = A[j + 1]

    n = n - 1
    return n, removed
```

Sau khi xóa, các phần tử trước `i` vẫn giữ nguyên; những phần tử đứng sau dịch trái một vị trí:

\[
\begin{cases}
A_{new}[j]=A_{old}[j] & 0\le j<i,\\
A_{new}[j]=A_{old}[j+1] & i\le j<n-1.
\end{cases}
\]

Với `n` là độ dài **trước khi xóa**, số phần tử cũ đứng phía sau chỉ số `i` là:

\[
\boxed{\operatorname{moves}_{delete}=n-i-1}
\]

| Vị trí xóa | Số phần tử dịch | Thời gian |
|---|---:|---|
| Đầu mảng (`i = 0`, `n > 0`) | `n-1` | `O(n)` |
| Giữa mảng | Xấp xỉ `n/2` | `O(n)` |
| Cuối mảng (`i = n-1`) | `0` | `O(1)` thường gặp |

Nếu chỉ có một phần tử (`n=1`), xóa tại `i=0` không cần dịch và làm mảng trở thành rỗng. Nếu `n=0`, không có chỉ số nào hợp lệ để xóa: thuật toán phải từ chối thao tác, thay vì cố đọc `A[0]`.

## 5. Độ phức tạp: đã biết vị trí khác với cần tìm vị trí

Với mảng liên tiếp, các phép truy cập địa chỉ và gán một ô thường là `O(1)`. Sự khác biệt về chi phí nằm ở số ô cần dịch và khả năng phải cấp phát lại.

| Thao tác | Thời gian thông thường | Ghi chú |
|---|---|---|
| Đọc hoặc gán `A[i]` | `O(1)` | Khi `i` đã biết và hợp lệ |
| Chèn tại `i < n`, còn đủ sức chứa | `O(n-i+1)`, tối đa `O(n)` | Dịch `n-i` phần tử rồi ghi một ô |
| Chèn cuối (`i = n`), còn chỗ | `O(1)` | Không dịch phần tử |
| Chèn khi vùng chứa đầy | Có thể `O(n)` | Có thể cần cấp phát lại và sao chép `n` phần tử |
| Xóa tại `i < n`, giữ thứ tự | `O(n-i)`, tối đa `O(n)` | Dịch `n-i-1` phần tử; thu hồi dung lượng có thể có chi phí riêng |
| Xóa cuối | `O(1)` thường gặp | Không cần dịch phần tử; đôi lúc mảng động co vùng nhớ |
| Tìm giá trị rồi xóa lần xuất hiện đầu tiên | `O(n)` | Tìm tuyến tính và dịch phần đuôi, mỗi phần tối đa `O(n)` |

Trong cách viết độ phức tạp theo `n`, chèn/xóa tại đầu hoặc giữa có trường hợp xấu nhất `O(n)`. Khi phần tử nằm sát cuối, chi phí dịch chuyển có thể là hằng số; do đó phát biểu chính xác phải có điều kiện về **vị trí** và **sức chứa**.

### Thời gian và bộ nhớ phụ

Nếu đã có chỗ trong vùng đệm, một thao tác chèn/xóa theo dịch chuyển có thể dùng **`O(1)` bộ nhớ phụ**: chỉ cần biến chỉ số và giá trị tạm. Nhưng nếu mảng đầy và phải tạo vùng chứa lớn hơn, hệ thống cần vùng lưu mới chứa `O(n)` ô, ít nhất trong quá trình sao chép. Việc dùng thêm bộ nhớ này thuộc cơ chế **mở rộng mảng**, khác với số ô phải dịch do chèn tại vị trí `i`.

Đối với mảng các tham chiếu, dịch `n-i` ô thường là chuyển `n-i` **tham chiếu**; chi phí không nhất thiết tương đương sao chép toàn bộ đối tượng lớn mà các tham chiếu trỏ đến. Trong mảng cấu trúc lưu giá trị trực tiếp, mỗi ô có thể lớn hơn, nên lượng byte được di chuyển cũng tăng theo kích thước phần tử. Phân tích Big-O ở đây giả định mỗi ô có kích thước cố định và việc sao chép một ô là `O(1)`.

## 6. Mảng động: vì sao thêm cuối có thể là `O(1)` khấu hao?

Mảng động quản lý hai đại lượng: **độ dài** `n` và **sức chứa** `capacity`. Khi `n < capacity`, thêm cuối chỉ cần ghi vào vị trí `n` rồi tăng `n`; thao tác này thường là `O(1)`. Khi `n == capacity`, mảng phải phát triển vùng lưu trữ trước khi ghi.

Một chiến lược phổ biến là tăng sức chứa theo tỷ lệ, ví dụ gấp đôi (tỷ lệ thực tế tùy thư viện):

```text
Trước: capacity = 4, n = 4
       [10, 20, 30, 40]

Thêm 50: vùng chứa hết chỗ
       cấp phát capacity = 8
       sao chép 4 phần tử cũ → ghi 50

Sau:   [10, 20, 30, 40, 50, _, _, _]
       n = 5, capacity = 8
```

Một lần mở rộng có thể mất `O(n)`, nhưng các lần tiếp theo vẫn có chỗ trống. Với chiến lược tăng sức chứa theo cấp số nhân, tổng số phần tử phải sao chép qua **nhiều lần thêm cuối** là `O(n)`; do đó thêm cuối có chi phí **`O(1)` khấu hao** (*amortized*) cho mỗi thao tác. Điều này **không có nghĩa mỗi lần thêm cuối đều `O(1)`**.

Chèn giữa vẫn thường mất `O(n)` ngay cả khi còn nhiều chỗ trống, vì các phần tử phía sau phải dịch để giữ thứ tự. Việc cấp phát lại chỉ có thể làm một lần chèn tốn kém hơn; nó không loại bỏ yêu cầu sắp xếp lại các vị trí.

Xóa phần tử làm giảm độ dài. Một số mảng động có chính sách thu nhỏ sức chứa khi mức sử dụng quá thấp; việc thu nhỏ có thể phải cấp phát và sao chép lại. Vì vậy, nói xóa cuối là `O(1)` thường gặp là phù hợp với thao tác cơ bản, còn bảo đảm về trường hợp xấu nhất phụ thuộc chính sách cấp phát của triển khai.

## 7. Minh họa bằng Python: thao tác có sẵn và thao tác dịch thủ công

`list` trong Python là một mảng động. Các phương thức sau thể hiện đúng sự khác nhau giữa chèn, xóa và gán:

```python
numbers = [10, 20, 30, 40]

numbers[1] = 99       # Gán thay thế: [10, 99, 30, 40], O(1)
numbers.insert(2, 25) # Chèn: [10, 99, 25, 30, 40], O(n) xấu nhất
removed = numbers.pop(3)  # Xóa ở chỉ số 3, removed = 30
print(numbers)        # [10, 99, 25, 40]

numbers.append(50)    # Thêm cuối, O(1) khấu hao
last = numbers.pop()  # Xóa cuối, thường O(1); last = 50

# Tìm theo giá trị rồi xóa phần tử khớp đầu tiên:
numbers.remove(99)    # Phải tìm giá trị, sau đó dịch các ô nếu cần
print(numbers)        # [10, 25, 40]
```

`pop(index)` xóa theo **vị trí** và trả về giá trị vừa xóa; `remove(value)` xóa **lần xuất hiện đầu tiên của giá trị**, hoặc gây `ValueError` nếu không tìm thấy. `insert(index, value)` dùng quy tắc điều chỉnh chỉ số riêng của Python, bao gồm cả chỉ số âm và chỉ số vượt độ dài. Trong thuật toán tổng quát ở bài này, ta chủ động yêu cầu chỉ số chèn `0 <= index <= n` để tránh phụ thuộc vào cách từng ngôn ngữ diễn giải đầu vào ngoài phạm vi.

### Tự mô phỏng một vùng đệm có sức chứa cố định

Đoạn mã sau dùng một Python `list` có sáu ô để **mô phỏng** vùng đệm với `capacity=6`; biến `length` ghi số phần tử logic. Điều này giúp nhìn rõ từng phép dịch chuyển mà phương thức `insert()` hoặc `pop()` thường che đi.

```python
def insert_into_buffer(buffer: list[int | None], length: int,
                       index: int, value: int) -> int:
    if not 0 <= length <= len(buffer):
        raise ValueError("Độ dài logic không hợp lệ")
    if not 0 <= index <= length:
        raise IndexError("Vị trí chèn không hợp lệ")
    if length == len(buffer):
        raise OverflowError("Vùng đệm đã đầy")

    for j in range(length, index, -1):
        buffer[j] = buffer[j - 1]   # Dịch từ phải sang trái
    buffer[index] = value
    return length + 1


def delete_from_buffer(buffer: list[int | None], length: int,
                       index: int) -> int:
    if not 0 <= length <= len(buffer):
        raise ValueError("Độ dài logic không hợp lệ")
    if not 0 <= index < length:
        raise IndexError("Vị trí xóa không hợp lệ")

    for j in range(index, length - 1):
        buffer[j] = buffer[j + 1]   # Dịch từ trái sang phải
    buffer[length - 1] = None      # Xóa tham chiếu còn dư
    return length - 1


buffer: list[int | None] = [10, 20, 30, 40, None, None]
length = 4

length = insert_into_buffer(buffer, length, 1, 99)
print(buffer[:length])  # [10, 99, 20, 30, 40]

length = delete_from_buffer(buffer, length, 2)
print(buffer[:length])  # [10, 99, 30, 40]
```

Trong ví dụ, các giá trị đang sử dụng luôn là số nguyên, còn `None` chỉ biểu diễn ô dự phòng hoặc ô đã ngừng sử dụng. Hai hàm nhận và trả độ dài logic vì bản thân `len(buffer)` vẫn là `6`, bằng sức chứa của vùng đệm mô phỏng. Trong hệ thống thực, mảng động quản lý độ dài và sức chứa trong cấu trúc dữ liệu của nó.

## 8. Khi nào có thể xóa mà không cần giữ thứ tự?

Yêu cầu **giữ nguyên thứ tự** chính là lý do phải dịch trái sau khi xóa giữa. Nếu bài toán cho phép thay đổi thứ tự, ta có thể dùng kỹ thuật **đưa phần tử cuối vào chỗ phần tử bị xóa** (*swap with last*):

```text
Ban đầu:      [A, B, C, D, E]    n = 5
Xóa vị trí 1: [A, E, C, D]       n = 4
```

Chỉ cần ghi giá trị cuối `E` vào vị trí `1` rồi giảm độ dài, không phải dịch `C` và `D`. Khi đã biết chỉ số và cách biểu diễn cho phép ghi ô, thao tác này thường là **`O(1)`** và dùng `O(1)` bộ nhớ phụ:

```python
def remove_unordered(values: list[int], index: int) -> int:
    if not 0 <= index < len(values):
        raise IndexError("Vị trí xóa không hợp lệ")
    removed = values[index]
    values[index] = values[-1]
    values.pop()
    return removed


items = [10, 20, 30, 40, 50]
print(remove_unordered(items, 1))  # 20
print(items)                       # [10, 50, 30, 40]
```

Điều kiện quan trọng là ứng dụng **không dựa vào thứ tự** của dãy. Kỹ thuật này không thích hợp cho danh sách xếp hàng, lịch sử thao tác hoặc dữ liệu đã sắp xếp cần bảo toàn thứ tự. Nếu vẫn cần tìm phần tử theo giá trị trước khi xóa, bước tìm trong mảng chưa có chỉ mục vẫn có thể tốn `O(n)`; xóa nhanh không tự động làm toàn bộ thao tác “tìm rồi xóa” thành `O(1)`.

## 9. Lựa chọn cấu trúc dữ liệu theo thao tác thường xuyên

Sự dịch chuyển trong mảng tạo ra các đánh đổi khác nhau:

| Nhu cầu chính | Cấu trúc thường phù hợp | Lý do |
|---|---|---|
| Truy cập phần tử thứ `i`, duyệt tuần tự | Mảng / mảng động | Truy cập theo chỉ số `O(1)`, bộ nhớ thường có tính cục bộ tốt |
| Thêm và lấy phần tử ở cuối theo LIFO | Stack dùng mảng động | `push`/`pop` cuối thường `O(1)` khấu hao |
| Thêm ở cuối, lấy ở đầu theo FIFO | Queue dùng **bộ đệm vòng** hoặc deque | Tránh dịch toàn bộ phần tử khi lấy đầu |
| Chèn/xóa liên tục tại nút đã biết | Danh sách liên kết | Thay liên kết có thể `O(1)` nếu đã có đủ tham chiếu đến vị trí |
| Tra cứu, xóa theo khóa duy nhất | Bảng băm | Tra cứu/xóa theo khóa thường `O(1)` trung bình; không dựa vào vị trí liên tiếp |
| Luôn lấy phần tử có độ ưu tiên cao nhất | Heap | Dùng mảng bên trong nhưng duy trì bất biến heap qua thao tác `O(log n)` |

Lưu ý: trong danh sách liên kết, **tìm nút thứ `i`** từ đầu vẫn thường tốn `O(n)`. Nói “chèn/xóa danh sách liên kết `O(1)`” chỉ chính xác khi đã có vị trí nút và các liên kết cần thiết; nếu phải tìm nút trước thì tổng chi phí có thể là `O(n)`.

Tương tự, một hàng đợi triển khai bằng Python `list` và thường xuyên gọi `pop(0)` phải dịch gần như toàn bộ phần tử còn lại, dẫn đến `O(n)` cho mỗi lần lấy đầu. `collections.deque` hoặc bộ đệm vòng được thiết kế để thêm cuối và lấy đầu hiệu quả hơn.

### Khi sử dụng mảng cho hàng đợi: ý tưởng bộ đệm vòng

Nếu mỗi lần xóa đầu ta lại dịch các phần tử sang trái, chi phí sẽ cao. Một **bộ đệm vòng** giữ chỉ số `head` của phần tử đầu và sử dụng phép modulo để chuyển sang ô kế tiếp:

\[
head_{new}=(head+1)\bmod capacity
\]

Khi lấy một phần tử, ta chỉ thay `head` và giảm số phần tử logic, không cần dịch các ô phía sau. Với sức chứa đủ lớn, thao tác đó là `O(1)`. Đổi lại, ta phải duy trì bất biến về `head`, `tail`, số phần tử và xử lý lúc đầy; đây là đánh đổi về thiết kế và quản lý trạng thái để loại bỏ chi phí dịch chuyển.

## 10. Lỗi dễ mắc khi chèn, xóa

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chèn bằng cách dịch trái sang phải | Ghi đè nguồn, sao chép nhầm giá trị | Dịch từ `n-1` về `i` |
| Xóa bằng cách dịch phải sang trái | Ghi đè nguồn ở phía sau | Dịch từ `i` lên `n-2` |
| Chèn khi `n == capacity` mà không mở rộng | Ghi vượt vùng đệm | Kiểm tra sức chứa trước khi dịch |
| Đọc hoặc xóa tại `i == n` | Truy cập ngoài độ dài logic | Chỉ xóa khi `0 <= i < n` |
| Cấm chèn tại `i == n` | Không thêm cuối được | Cho phép `0 <= i <= n` |
| Quên cập nhật `n` | Phạm vi hợp lệ không khớp dữ liệu | Tăng `n` sau chèn, giảm `n` sau xóa |
| Giữ chỉ số cũ sau thao tác | Chỉ số có thể trỏ tới phần tử khác | Tính lại chỉ số hoặc lưu định danh riêng |
| Xóa theo giá trị nhưng giả định biết sẵn vị trí | Đánh giá thiếu bước tìm kiếm | Cộng cả chi phí tìm và dịch |
| Không xử lý mảng rỗng khi xóa | Đọc ngoài mảng | Kiểm tra `n > 0` và chỉ số hợp lệ |
| Giữ tham chiếu ở ô dư của bộ đệm thủ công | Đối tượng có thể bị giữ lại không cần thiết | Xóa tham chiếu ở ô không còn sử dụng |

Chèn/xóa trong mảng cũng có thể làm **mất hiệu lực của con trỏ, iterator hoặc tham chiếu đến vị trí** tùy cấu trúc và ngôn ngữ. Chẳng hạn, `std::vector` trong C++ có thể cấp phát lại khi chèn và khiến mọi con trỏ/iterator tới vùng lưu cũ không còn hợp lệ. Ngay cả khi không cấp phát lại, thao tác vẫn có thể thay đổi phần tử gắn với một vị trí. Cần tuân thủ quy tắc của thư viện khi giữ các tham chiếu dài hạn.

## 11. Bài tập tự kiểm tra

**Bài 1.** Mảng `A = [2, 4, 6, 8, 10]` có `n = 5` và sức chứa đủ lớn. Chèn `99` tại vị trí `i = 2`. Hãy viết mảng sau chèn, chỉ ra các phần tử phải dịch và đếm số lần dịch.

**Bài 2.** Từ kết quả bài 1, xóa phần tử tại chỉ số `4` trong khi vẫn giữ thứ tự. Mảng mới là gì? Có bao nhiêu phần tử phải dịch?

**Bài 3.** Với mảng `n = 10.000` phần tử, giả sử đã có đủ sức chứa: chèn tại `i = 2.500` cần dịch bao nhiêu phần tử? Xóa tại `i = 2.500` cần dịch bao nhiêu phần tử?

**Bài 4.** Một mảng động có `length = capacity = 8`. Thêm một phần tử vào cuối có nhất thiết mất `O(1)` ở lần thêm đó không? Vì sao thao tác này vẫn có thể được mô tả bằng `O(1)` khấu hao?

**Bài 5.** Giả sử cần xóa phần tử thứ hai trong `[A, B, C, D, E]` và **không yêu cầu giữ thứ tự**. Hãy nêu cách xóa với `O(1)` lần gán, và giải thích vì sao cách đó không phù hợp với một hàng người xếp theo thứ tự đến.

**Bài 6.** Một hàng đợi có hàng triệu thao tác thêm cuối và lấy đầu. Vì sao cài đặt lấy đầu bằng việc dịch trái toàn bộ mảng không phù hợp? Nêu một cấu trúc thay thế.

**Bài 7.** Nếu một danh sách liên kết có thể chèn một nút trong `O(1)` khi đã biết nút đứng trước, vì sao thao tác “chèn tại vị trí thứ `i`” chưa chắc nhanh hơn mảng?

### Đáp án gợi ý

1. Kết quả `[2, 4, 99, 6, 8, 10]`; ba phần tử `6`, `8`, `10` phải dịch phải. Số lần dịch bằng `n-i = 5-2 = 3`.
2. Xóa phần tử ở chỉ số `4` (giá trị `8`) trong mảng dài `6` cho `[2, 4, 99, 6, 10]`. Cần dịch trái một phần tử (`10`): `6-4-1 = 1`.
3. Chèn: `10.000-2.500 = 7.500` phần tử. Xóa: `10.000-2.500-1 = 7.499` phần tử.
4. Không. Khi đầy, mảng có thể phải cấp phát vùng mới và sao chép `8` phần tử, nên lần thêm đó có thể `O(n)`. Nếu sức chứa tăng theo cấp số nhân, chi phí phân bổ trên nhiều lần thêm cuối là `O(1)` khấu hao.
5. Thay `B` bằng phần tử cuối `E`, rồi giảm độ dài, cho `[A, E, C, D]`. Cách này làm đổi thứ tự đến nên không dùng được cho hàng đợi có yêu cầu FIFO.
6. Mỗi lần lấy đầu phải dịch `O(n)` phần tử, khiến tổng chi phí tăng mạnh khi lặp nhiều lần; có thể dùng `deque` hoặc bộ đệm vòng.
7. Danh sách liên kết vẫn thường phải đi từ đầu để tìm nút trước vị trí `i`, mất `O(n)`; chi phí tìm vị trí cần được tính vào toàn bộ thao tác.

## 12. Ghi nhớ

Với mảng có `n` phần tử, **chèn tại vị trí `i`** (hợp lệ khi `0 <= i <= n`) cần dịch phải `n-i` phần tử, theo thứ tự **từ phải sang trái**. **Xóa tại vị trí `i`** (hợp lệ khi `0 <= i < n`) cần dịch trái `n-i-1` phần tử, theo thứ tự **từ trái sang phải**. Vì vậy, chèn/xóa ở đầu hoặc giữa mảng liên tiếp thường có độ phức tạp `O(n)` khi phải giữ thứ tự; thêm hoặc xóa cuối thường nhanh hơn, đặc biệt khi mảng động còn đủ sức chứa. Khi chọn cấu trúc dữ liệu, cần xét cả yêu cầu giữ thứ tự, vị trí thao tác, khả năng cấp phát lại và số lần thực hiện, thay vì chỉ dựa vào khả năng truy cập theo chỉ số `O(1)` của mảng.
