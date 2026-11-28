# Độ phức tạp thời gian và không gian phụ trợ

> **Chương:** Đặc tả và chi phí · **Bài học:** Độ phức tạp thời gian và không gian phụ trợ

Một thuật toán có thể chạy rất nhanh nhưng cần thêm một bảng tra cứu lớn; thuật toán khác tiết kiệm bộ nhớ nhưng phải duyệt lại dữ liệu nhiều lần. Nếu chỉ so sánh tốc độ, ta có thể chọn giải pháp vượt giới hạn RAM. Nếu chỉ so sánh số byte lưu trữ, ta có thể chọn giải pháp phản hồi quá chậm. Vì vậy, khi đánh giá cấu trúc dữ liệu phải quan sát **hai trục chi phí: thời gian và không gian**.

Trong mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`), từ mảng, danh sách liên kết, stack, queue đến bảng băm, cây, heap và đồ thị, mọi lựa chọn đều gắn với bất biến, tập thao tác và mức tài nguyên cần dùng. Bài học này cung cấp cách đo **độ phức tạp thời gian** (*time complexity*) và **độ phức tạp không gian phụ trợ** (*auxiliary space complexity*) để so sánh các phương án một cách nhất quán.

## 1. Kết quả học tập

Hoàn thành bài học, bạn có thể:

1. Xác định đúng biến đo kích thước đầu vào và mô hình chi phí cho một thao tác.
2. Phân biệt thời gian thực thi đo bằng đồng hồ với độ phức tạp thời gian theo số bước.
3. Dùng O, Ω và Θ để mô tả giới hạn tăng trưởng; nhận diện tốt nhất, xấu nhất, trung bình, kỳ vọng và khấu hao.
4. Phân biệt **bộ nhớ đầu vào**, **đầu ra**, **không gian phụ trợ**, **bộ nhớ lưu cấu trúc** và **đỉnh bộ nhớ sử dụng**.
5. Phân tích vòng lặp, hàm gọi lồng nhau, đệ quy và cấu trúc dữ liệu thông dụng theo cả thời gian lẫn bộ nhớ.
6. Đánh giá các đánh đổi thời gian–không gian và kiểm tra chúng bằng ví dụ thực tế.

## 2. Hai câu hỏi đo lường khác nhau

### 2.1. Độ phức tạp thời gian là số công việc tăng thế nào?

Gọi `n` là kích thước đầu vào đã được định nghĩa. `T(n)` mô tả số bước tính toán theo một **mô hình chi phí**. Ví dụ, hàm duyệt mảng:

```python
def contains_linear(values, target):
    for value in values:
        if value == target:
            return True
    return False
```

Với `n = len(values)`, nếu một lần so sánh khóa có chi phí O(1), trường hợp không tìm thấy cần `n` lần so sánh. Do đó **thời gian xấu nhất** là Θ(n). Nếu phần tử đầu đã trùng, thời gian **tốt nhất** với `n ≥ 1` chỉ là Θ(1).

Độ phức tạp không nói rằng máy sẽ chạy chính xác `n` micro giây. Nó nói cách lượng công việc tăng khi `n` thay đổi, dưới các giả định đã đặt.

### 2.2. Không gian phụ trợ là phần bộ nhớ thêm ngoài dữ liệu vào

Xét tiếp hàm `contains_linear`. Nó chỉ cần biến `value` của vòng lặp và một số trạng thái điều khiển kích thước không tăng theo `n`. Vì vậy:

\[
T_{\mathrm{worst}}(n)=\Theta(n),\qquad S_{\mathrm{aux}}(n)=O(1)
\]

Trong đó:

- `T(n)`: chi phí thời gian.
- `S_aux(n)`: bộ nhớ **phụ trợ** thuật toán cần thêm, không tính vùng chứa dữ liệu đầu vào vốn đã có.
- O(1): lượng bộ nhớ thêm bị chặn bởi một hằng số trong mô hình đang dùng.

Với Python, một phép duyệt qua list không tự tạo một danh sách mới dài `n`. Tuy nhiên, cách lập trình khác như `values[:]` lại tạo bản sao mới và cần O(n) bộ nhớ.

### 2.3. Phải định nghĩa biến kích thước

| Bài toán | Tham số thường dùng | Điểm cần ghi rõ |
| --- | --- | --- |
| Duyệt mảng | `n` = số phần tử | Chi phí xử lý từng phần tử có phải O(1) không? |
| So sánh hai dãy | `n` và `m` | Hai kích thước không nhất thiết bằng nhau |
| Xử lý chuỗi | `k` = số ký tự hoặc byte | Một phép so sánh có thể tốn O(k) |
| Tìm trong cây | `n` = số nút, `h` = chiều cao | Tìm kiếm thường phụ thuộc `h` |
| Thực hiện nhiều truy vấn | `n` = dữ liệu ban đầu, `q` = số truy vấn | Phải cộng chi phí xây cấu trúc |
| Duyệt đồ thị | `V` = số đỉnh, `E` = số cạnh | Ma trận kề và danh sách kề có chi phí khác |
| Mở rộng mảng động | `n` = số phần tử hiện tại, `C` = sức chứa | Bộ nhớ giữ lại có thể phụ thuộc `C` |

Nếu chỉ viết “O(n)” mà không cho biết `n` đo cái gì, kết luận chưa đủ để sử dụng.

## 3. Mô hình chi phí: một phép toán cơ bản có giá bao nhiêu?

Trong mô hình RAM thông dụng, ta giả sử mỗi bước như đọc/ghi một ô mảng theo chỉ số, tăng một biến đếm, so sánh hai khóa cỡ từ máy hoặc cập nhật một tham chiếu tốn O(1). Nhờ vậy ta có thể tập trung vào **số lần** các thao tác xuất hiện.

Ví dụ:

```python
def pairwise_equal(a, b):
    pairs = 0
    for x in a:
        for y in b:
            if x == y:
                pairs += 1
    return pairs
```

Nếu `n = len(a)` và `m = len(b)`, phép `x == y` diễn ra **đúng `nm` lần**. Khi `n,m ≥ 1` và mỗi phép so sánh O(1), thời gian là Θ(nm). Nếu `m=0`, vòng ngoài vẫn duyệt `n` phần tử nhưng vòng trong rỗng; thời gian đầy đủ của ví dụ là Θ(1+n+nm), với các biến kích thước không âm.

Bộ nhớ phụ trợ của mã này là O(1) theo mô hình số nguyên đếm có kích thước cố định. Nếu đếm chính xác với số nguyên có độ dài không giới hạn, kích thước biểu diễn biến `pairs` có thể tăng theo log(nm), và phép cộng không nhất thiết còn O(1) ở mức bit. Vì vậy hãy ghi rõ mô hình khi bài toán đòi độ chính xác đến mức bit.

**Không nên gộp mọi chi phí thành O(1) một cách máy móc.** Băm một chuỗi dài `k` ký tự có thể cần O(k) thời gian, cấp phát một mảng dài `n` thường cần O(n) không gian, và sao chép `n` phần tử cần O(n) thời gian.

## 4. Ký hiệu tăng trưởng: O, Ω và Θ

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `O(f(n))` | Chặn trên tiệm cận: thời gian không tăng nhanh hơn một hằng số nhân `f(n)` với `n` đủ lớn | `3n+7 = O(n)` |
| `Ω(f(n))` | Chặn dưới tiệm cận: thời gian không nhỏ hơn một hằng số nhân `f(n)` với `n` đủ lớn | `3n+7 = Ω(n)` |
| `Θ(f(n))` | Chặn chặt tiệm cận: đồng thời có chặn trên và dưới cùng bậc | `3n+7 = Θ(n)` |

Chẳng hạn, nếu một thuật toán luôn duyệt cả `n` phần tử, mỗi phần tử đúng một lần với chi phí hằng số, ta có thể viết thời gian Θ(n).

Nếu chỉ biết mã chạy **không quá** một số bước tỷ lệ với `n²`, ta có thể kết luận O(n²), nhưng chưa được tự khẳng định Θ(n²) nếu chưa có chặn dưới phù hợp.

### 4.1. Bỏ hằng số và số hạng bậc thấp khi xét tiệm cận

\[
T(n)=7n^2+20n+100=\Theta(n^2)
\]

Với `n` đủ lớn, số hạng `n²` chi phối tốc độ tăng. Tuy nhiên, hệ số 7 và 100 **vẫn có ảnh hưởng thực tế** ở kích thước nhỏ; Big-O không trực tiếp dự đoán thời gian chạy bằng giây.

### 4.2. Đọc ký hiệu theo thứ tự tăng trưởng

Một số bậc thường gặp:

```text
O(1)  <  O(log n)  <  O(n)  <  O(n log n)
      <  O(n²)    <  O(2^n)
```

Dấu `<` trong dòng này chỉ **thứ tự tốc độ tăng của các hàm đại diện** khi `n` lớn, không phải so sánh thời gian thực của hai chương trình bất kỳ. Một thuật toán O(n) có thể nhanh hơn thuật toán O(log n) trên một miền kích thước nhỏ vì hằng số và đặc điểm máy khác nhau.

### 4.3. Điều kiện biên và logarit

Với `n=0`, biểu thức `log n` không xác định. Do đó các công thức như O(log n) thường ngầm xét `n≥2`; khi muốn mô tả cả trường hợp nhỏ, có thể dùng `O(log(n+1)+1)` hoặc xử lý trường hợp rỗng riêng.

## 5. Trường hợp tốt nhất, xấu nhất, trung bình, kỳ vọng và khấu hao

Năm cách đo này trả lời các câu hỏi khác nhau.

| Cách đo | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Tốt nhất | Có đầu vào thuận lợi nào làm thuật toán kết thúc sớm nhất? | Tìm thấy ngay ở đầu mảng |
| Xấu nhất | Với kích thước này, trường hợp tốn nhất là bao nhiêu? | Tìm khóa vắng mặt bằng duyệt tuyến tính |
| Trung bình | Khi đầu vào tuân một phân bố đã nêu, thời gian trung bình là bao nhiêu? | Khóa có mặt với vị trí đầu phân bố đều |
| Kỳ vọng | Khi thuật toán hay dữ liệu có yếu tố ngẫu nhiên, kỳ vọng chi phí là gì? | Tra khóa trong bảng băm với phân bố hash phù hợp |
| Khấu hao | Trên một chuỗi thao tác, chi phí bình quân được chặn ra sao? | `append` mảng động có vài lần cấp phát lớn |

Giả sử tìm tuyến tính trong mảng `n` phần tử, mục tiêu chắc chắn có mặt và vị trí xuất hiện đầu tiên phân bố đều. Số phép so sánh trung bình bằng:

\[
\frac{1+2+\dots+n}{n}=\frac{n+1}{2}=\Theta(n)
\]

Kết quả dựa trên **giả định phân bố đều**, không đúng cho mọi tập truy vấn.

Với mảng động tăng gấp đôi sức chứa, một `append` khi đầy có thể tốn Θ(n), nhưng tổng chi phí của `n` lần `append` liên tiếp từ mảng rỗng là O(n). Chi phí **khấu hao** mỗi `append` vì thế là O(1), ngay cả khi không dùng xác suất.

**Ghi nhớ:** O(1) kỳ vọng, O(1) khấu hao và O(1) xấu nhất **không đồng nghĩa**.

## 6. Tính thời gian từ vòng lặp và lời gọi hàm

### 6.1. Một vòng lặp qua `n` phần tử

```python
def find_max(values):
    if not values:
        raise ValueError("empty input")

    result = values[0]
    for i in range(1, len(values)):
        if values[i] > result:
            result = values[i]
    return result
```

Với `n ≥ 1`, vòng lặp thực hiện đúng `n-1` lần so sánh. Thời gian Θ(n) khi `n` tăng, bộ nhớ phụ trợ O(1). Trường hợp `n=1` không có phép so sánh trong vòng; phần khởi tạo vẫn mất O(1).

### 6.2. Vòng lặp nối tiếp: cộng chi phí

```python
for x in a:
    consume(x)

for y in b:
    consume(y)
```

Nếu `consume` là O(1), `len(a)=n` và `len(b)=m`, tổng thời gian là Θ(1+n+m). Khi cả `n,m` cùng lớn, ta thường viết Θ(n+m).

### 6.3. Vòng lặp lồng nhau: tính tổng số lần

```python
for i in range(n):
    for j in range(i):
        work()
```

Với `work` mất O(1), số lời gọi đúng bằng:

\[
\sum_{i=0}^{n-1}i=\frac{n(n-1)}{2}
\]

Với `n≥2`, thời gian Θ(n²); phần bộ đếm vòng lặp chỉ cần O(1) bộ nhớ phụ trợ.

### 6.4. Vòng lặp chia đôi

```python
def count_halving(n):
    count = 0
    while n > 1:
        n //= 2
        count += 1
    return count
```

Với `n≥1`, số vòng đúng bằng `⌊log₂ n⌋`. Mỗi vòng O(1) theo mô hình số nguyên từ máy, nên thời gian O(log n) và bộ nhớ phụ O(1). Đây là kiểu tăng trưởng thường xuất hiện ở tìm kiếm nhị phân, cây cân bằng và thao tác heap.

### 6.5. Không đánh giá lời gọi lồng nhau bằng tên hàm

```python
for key in queries:
    index.search(key)
```

Nếu có `q` truy vấn và mỗi `search` tốn O(log n), tổng thời gian vòng lặp là O(q log n), **cộng thêm** chi phí xây dựng `index`. Nếu `index` phải sắp xếp `n` phần tử trước với chi phí O(n log n), tổng có thể là:

\[
T(n,q)=O(n\log n+q\log n)
\]

Phân tích mỗi lời gọi riêng rồi ghép lại theo tần suất thực tế giúp tránh kết luận thiếu chi phí tiền xử lý.

## 7. Bộ nhớ đầu vào, bộ nhớ phụ, đầu ra và bộ nhớ tổng

Để báo cáo chi phí không gian rõ ràng, cần xác định **đang tính phần nào**.

| Thành phần | Định nghĩa làm việc trong bài | Ví dụ |
| --- | --- | --- |
| **Đầu vào (input storage)** | Bộ nhớ đã dùng để chứa dữ liệu mà thuật toán nhận trước khi chạy | Mảng `values` có `n` phần tử |
| **Không gian phụ trợ (auxiliary space)** | Bộ nhớ thêm được cấp phát hoặc giữ để tính toán, **không tính vùng đầu vào và vùng kết quả** theo quy ước của bài | Biến đếm, bảng `visited`, stack đệ quy |
| **Đầu ra (output storage)** | Bộ nhớ để chứa kết quả được tạo ra | Mảng gồm `n` giá trị tiền tố |
| **Bộ nhớ tổng (total space)** | Tất cả thành phần cần thiết, kể cả đầu vào và đầu ra | Đầu vào + phụ trợ + đầu ra |
| **Bộ nhớ đỉnh (peak usage)** | Lượng bộ nhớ sống tối đa cùng lúc trong suốt quá trình | Lúc mảng cũ và mảng mới cùng tồn tại khi mở rộng |

Cần nói rõ **quy ước về đầu ra**: một số tài liệu gọi toàn bộ bộ nhớ thuật toán cấp phát, kể cả mảng kết quả, là “bộ nhớ phụ”. Trong bài này, ta trình bày riêng đầu ra và không gian phụ trợ để người đọc phân biệt mục đích sử dụng.

Về mặt ý tưởng:

\[
S_{\mathrm{total}}(n)
\approx S_{\mathrm{input}}(n)+S_{\mathrm{aux}}(n)+S_{\mathrm{output}}(n)
\]

Tổng trên mô tả các phần bộ nhớ cần xét; khi phân tích **đỉnh bộ nhớ**, phải xem các vùng nào tồn tại **đồng thời**, chứ không đơn giản cộng mọi lần cấp phát xuyên suốt vòng đời chương trình.

### 7.1. Ví dụ tạo đầu ra dài `n`

```python
def squares(values):
    result = []
    for x in values:
        result.append(x * x)
    return result
```

Với `n=len(values)` và giả định số nguyên kích thước cố định:

- Thời gian: Θ(n).
- Bộ nhớ đầu vào: Θ(n) ô phần tử.
- Bộ nhớ kết quả: Θ(n) ô phần tử.
- Không gian phụ trợ **ngoài `result`**: O(1).
- Không gian cấp phát bổ sung nếu tính cả đầu ra: Θ(n).

Nếu dùng thuật ngữ “không gian phụ trợ O(1)” mà không nói đã loại `result` khỏi phép đếm, hai người có thể hiểu khác nhau. Hãy ghi quy ước đo.

### 7.2. Phân biệt kích thước và số byte thực tế

Một danh sách có `n` tham chiếu và một danh sách có `n` đối tượng lớn đều có O(n) ô ở mức khái quát, nhưng số byte thực tế có thể khác nhiều. Trong Python, danh sách chứa **tham chiếu** đến các đối tượng; bản thân đối tượng có thể chiếm bộ nhớ riêng.

Với khóa chuỗi dài, cả thời gian so sánh lẫn bộ nhớ giữ khóa còn phụ thuộc tổng số ký tự. Khi `n` là số bản ghi nhưng kích thước mỗi bản ghi không cố định, phân tích chỉ theo `n` có thể bỏ sót một tham số quan trọng.

## 8. Phân tích bộ nhớ của biến, mảng mới, bản sao và generator

### 8.1. Đảo mảng tại chỗ

```python
def reverse_in_place(values):
    left = 0
    right = len(values) - 1

    while left < right:
        values[left], values[right] = values[right], values[left]
        left += 1
        right -= 1
```

Với mảng `n` phần tử, hàm đổi chỗ `⌊n/2⌋` cặp. Thời gian Θ(n) khi `n≥2`, bộ nhớ phụ O(1) vì chỉ dùng hai chỉ số và một lượng trạng thái tạm không tăng theo `n`. Hàm **thay đổi đầu vào**, điều này phải được cho phép trong hợp đồng.

### 8.2. Tạo bản sao đảo ngược

```python
def reverse_copy(values):
    return values[::-1]
```

Với Python `list`, cú pháp cắt tạo danh sách mới chứa các tham chiếu theo thứ tự ngược. Thời gian Θ(n), bộ nhớ đầu ra Θ(n) tham chiếu; không sao chép sâu mọi đối tượng được tham chiếu. Nếu gọi toàn bộ cấp phát bổ sung là “không gian phụ”, hàm này có O(n) không gian bổ sung.

Cùng một kết quả quan sát về thứ tự, hai API khác nhau ở **tác dụng phụ** và **bộ nhớ đầu ra**, nên không thể hoán đổi nếu người gọi yêu cầu giữ nguyên đầu vào.

### 8.3. Generator không lưu toàn bộ kết quả cùng lúc

```python
def squares_generator(values):
    for x in values:
        yield x * x
```

Một generator đọc từng phần tử và trả kết quả lần lượt. Nếu người gọi tiêu thụ từng kết quả rồi bỏ đi, generator không phải cấp phát danh sách kết quả dài `n`. Với `values` là list đã tồn tại, bản thân generator giữ một lượng trạng thái O(1) (giả định mỗi `x*x` có kích thước cố định), còn thời gian để tạo đủ `n` kết quả là Θ(n).

Nhưng nếu bên gọi viết `list(squares_generator(values))`, quá trình vật chất hóa tạo danh sách dài `n`, nên cần Θ(n) bộ nhớ cho đầu ra. Không thể gọi toàn bộ chương trình O(1) bộ nhớ chỉ vì một hàm trung gian dùng `yield`.

### 8.4. Khi dùng bản sao phòng vệ

Để ngăn mã bên ngoài sửa cấu trúc lưu trữ nội bộ, API có thể trả `list(items)` hoặc `tuple(items)`. Đây là bản sao nông có Θ(n) thời gian và Θ(n) vùng chứa kết quả. Đổi lại, ranh giới giao diện an toàn hơn khi người gọi không thể trực tiếp thêm/xóa phần tử trong container nội bộ.

Không gian phụ trợ vì vậy gắn với cả yêu cầu **đúng đắn và đóng gói**, không chỉ tốc độ.

## 9. Bộ nhớ của đệ quy và ngăn xếp lời gọi

Mỗi lần gọi hàm đệ quy thường cần một khung gọi (*stack frame*) giữ tham số, biến cục bộ và vị trí quay lại. Nếu tối đa `d` lời gọi chưa kết thúc cùng lúc, bộ nhớ ngăn xếp thường là O(d), giả định mỗi khung có kích thước O(1).

### 9.1. Duyệt danh sách bằng đệ quy

```python
class Node:
    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node


def count_nodes_recursive(node):
    if node is None:
        return 0
    return 1 + count_nodes_recursive(node.next)
```

Với danh sách liên kết đơn dài `n`:

- Thời gian: Θ(n), vì đi qua mỗi nút một lần.
- Bộ nhớ phụ cho stack lời gọi: Θ(n), vì độ sâu đệ quy đạt `n+1`.
- Bộ nhớ lưu các nút đầu vào: Θ(n), được tính riêng.

Trong Python, danh sách quá dài có thể vượt giới hạn độ sâu đệ quy; kết quả độ phức tạp **không bảo đảm** mã sẽ chạy thành công với `n` tùy ý.

### 9.2. Duyệt danh sách bằng vòng lặp

```python
def count_nodes_iterative(head):
    count = 0
    current = head
    while current is not None:
        count += 1
        current = current.next
    return count
```

Hàm này vẫn Θ(n) thời gian, nhưng bộ nhớ phụ O(1). Nó dùng một con trỏ `current` để đi dọc danh sách, thay vì giữ toàn bộ chuỗi khung gọi hàm.

**Kết luận theo ví dụ:** hai phương pháp có cùng thời gian tiệm cận nhưng **khác độ phức tạp không gian phụ trợ**.

### 9.3. Độ sâu trong cây và đồ thị

- Đệ quy tìm kiếm trên cây, nếu mỗi lời gọi chỉ đi vào một nhánh và chiều cao là `h`, có thể tốn O(h) không gian stack.
- Với cây cân bằng, `h=O(log n)`; với cây lệch, `h=Θ(n)`.
- DFS đồ thị bằng đệ quy có thể giữ O(V) khung lời gọi trong trường hợp xấu; thường còn cần một tập `visited` O(V) để tránh thăm lại.
- BFS đồ thị bằng queue không sử dụng cùng chiều sâu đệ quy, nhưng queue có thể giữ O(V) đỉnh chờ xử lý.

### 9.4. Tổng số lời gọi khác số lời gọi cùng tồn tại

Nếu một hàm lần lượt gọi đệ quy vào hai nhánh:

```python
def visit_tree(node):
    if node is None:
        return
    visit_tree(node.left)
    visit_tree(node.right)
```

Hàm có thể thăm Θ(n) nút trong thời gian, nhưng độ sâu stack đồng thời chỉ tương ứng với chiều cao cây `h`: O(h). Không được kết luận stack O(n) chỉ vì có `n` lời gọi xảy ra **trong toàn bộ thời gian chạy**.

Ngược lại, nếu lưu kết quả của từng nhánh thành một danh sách tại mỗi mức, phải tính cả những danh sách tạm và thời gian sao chép của chúng, không chỉ stack.

## 10. Ví dụ đệ quy có quan hệ truy hồi: Merge Sort

Merge Sort chia dãy thành hai nửa, sắp xếp từng nửa rồi trộn kết quả. Với triển khai tiêu chuẩn mà mỗi mức trộn các phần tử tổng cộng O(n):

\[
T(n)=2T(n/2)+\Theta(n)
\]

Nếu bỏ qua làm tròn khi chia, tổng thời gian là Θ(n log n) với `n≥2`.

### 10.1. Vì sao chỉ sâu logarit mà bộ nhớ vẫn tuyến tính?

Độ sâu đệ quy là O(log n), nhưng việc trộn hai dãy thường cần một vùng đệm phụ chứa O(n) phần tử tại mức lớn nhất. Khi thiết kế tái sử dụng một vùng đệm:

- Thời gian: Θ(n log n).
- Bộ nhớ ngăn xếp: O(log n).
- Bộ nhớ vùng trộn: O(n).
- Không gian phụ trợ tổng: O(n).

Không thể chỉ nhìn độ sâu lời gọi O(log n) rồi ghi Merge Sort dùng O(log n) không gian phụ trợ nếu cài đặt cần một mảng trộn dài `n`.

### 10.2. Cách viết mã có thể làm thay đổi chi phí

Một Merge Sort dùng các phép cắt như `left = values[:mid]` và `right = values[mid:]` sẽ cấp phát thêm danh sách con. Với thiết kế thông thường, bộ nhớ **đỉnh** vẫn có thể là O(n) vì tổng kích thước các lát cắt còn sống trên một đường đệ quy tạo thành một cấp số nhân giảm dần. Tuy nhiên, toàn bộ lượng dữ liệu được sao chép trên các mức có thể làm tăng tổng công việc, dù không gian đỉnh vẫn tuyến tính.

Nếu mã dùng nối danh sách liên tục theo cách kém hiệu quả, chi phí có thể khác đáng kể. Vì vậy, kết luận về thời gian và không gian cần gắn với **triển khai cụ thể**.

## 11. Chi phí thời gian và bộ nhớ trên các cấu trúc dữ liệu

Bảng dưới đặt trọng tâm vào hai câu hỏi:

- Một thao tác công khai thường tốn bao nhiêu **thời gian**?
- Cấu trúc giữ bao nhiêu **bộ nhớ nền** và thao tác cần bao nhiêu **bộ nhớ phụ**?

| Cấu trúc / thao tác | Thời gian thông dụng | Bộ nhớ lưu cấu trúc | Bộ nhớ phụ của thao tác |
| --- | --- | --- | --- |
| Mảng tĩnh: `a[i]` | O(1) | Θ(n) ô dữ liệu | O(1) |
| Mảng động: `append` | O(1) khấu hao; O(n) khi mở rộng | Θ(C) ô đã cấp, với `C` là sức chứa | O(1) nếu còn chỗ; có thể Θ(n) vùng tạm khi mở rộng |
| Danh sách liên kết: chèn đầu | O(1) | Θ(n) nút và liên kết | O(1) ngoài nút mới |
| Stack bằng liên kết: `push`/`pop` | O(1) | Θ(n) | O(1) mỗi lời gọi theo mô hình cấp phát |
| Queue bằng mảng vòng: `enqueue` | O(1) khấu hao nếu mở rộng gấp đôi | Θ(C) | O(1) thông thường; Θ(n) tạm khi mở rộng |
| Hash Map: `get` | O(1) kỳ vọng nếu băm/so sánh O(1) | O(n+b) với `b` bucket | O(1) cho tra cứu thông thường |
| Hash Map: rehash | O(n) khi cần phân bố lại `n` mục | O(n+b) sau mở rộng phù hợp | Có thể O(n+b) bộ nhớ tạm, tùy cài đặt |
| Cây tìm kiếm cân bằng: tìm | O(log n) xấu nhất | Θ(n) nút | O(1) nếu lặp; O(log n) stack nếu đệ quy |
| Heap nhị phân: `extract_min` | O(log n) | Θ(n) ô hoặc Θ(C) nếu mảng động dư sức chứa | O(1) nếu điều chỉnh lặp và không co mảng |
| BFS danh sách kề | O(V+E) khi duyệt mọi thành phần | Θ(V+E) đầu vào đồ thị | O(V) cho visited và queue |
| DFS đệ quy danh sách kề | O(V+E) khi duyệt mọi thành phần | Θ(V+E) đầu vào đồ thị | O(V) gồm visited và stack lời gọi |

**Các giới hạn đều có điều kiện:** bảng băm cần giả định phân bố và hệ số tải; cây phải tự cân bằng; chi phí cấp phát và so sánh khóa được xem là hằng số; thao tác chưa bao gồm việc trả bản sao toàn bộ dữ liệu nếu API yêu cầu.

### 11.1. Bộ nhớ lưu cấu trúc khác bộ nhớ phụ của thao tác

Ví dụ, một Stack bằng danh sách liên kết có `n` nút cần Θ(n) bộ nhớ để lưu dữ liệu. Nhưng một lần `pop` chỉ cập nhật con trỏ đỉnh và có O(1) bộ nhớ phụ. Nói “`pop` O(n) không gian” vì cả Stack có `n` nút là nhầm **bộ nhớ lưu cấu trúc** với **bộ nhớ thêm do thao tác**.

Tương tự, một Graph có O(V+E) bộ nhớ đầu vào, còn BFS bổ sung `visited` và Queue O(V). Khi báo cáo **không gian phụ trợ BFS O(V)**, ta đang tách phần cấu trúc đồ thị đầu vào khỏi vùng nhớ thuật toán cấp phát.

### 11.2. Mảng động và ý nghĩa của `capacity`

Giả sử một mảng động có sức chứa `C=1.024` nhưng đang chứa `n=10` phần tử do vừa xóa nhiều phần tử. Nếu cài đặt không thu nhỏ vùng đệm thì bộ nhớ giữ lại vẫn Θ(C), không phải Θ(n) theo số phần tử hiện tại.

Nếu phân tích chỉ một quá trình thêm từ rỗng theo chiến lược tăng gấp đôi, thường có `C=O(n+1)`. Nhưng kết luận ấy có thể không đúng sau những đợt xóa lớn mà không thu nhỏ. Phải nói rõ **trạng thái hoặc chuỗi thao tác** đang xét.

### 11.3. Chi phí bộ nhớ đỉnh lúc tăng sức chứa

Khi một mảng động mở rộng, có thể tồn tại đồng thời:

1. Vùng đệm cũ chứa `C` ô.
2. Vùng đệm mới chứa `2C` ô.
3. Dữ liệu trung gian cần sao chép.

Với triển khai cấp phát vùng mới rồi sao chép, bộ nhớ đỉnh có thể chứa cả hai vùng: khoảng `3C` ô chứa tham chiếu (bỏ qua phần quản lý bộ nhớ). Về Big-O vẫn là O(C), nhưng hằng số đỉnh quan trọng nếu thiết bị có RAM hạn chế. Đây là lý do phải xem **peak memory**, đặc biệt trong thao tác resize hoặc rehash.

## 12. Duyệt đồ thị: phân tích cả `V`, `E` và vùng nhớ phụ

Đồ thị là ví dụ tốt vì cùng một thao tác duyệt có chi phí khác nhau theo biểu diễn.

### 12.1. BFS trên danh sách kề

Ví dụ dùng `dict` ánh xạ mỗi đỉnh tới danh sách láng giềng:

```python
from collections import deque


def bfs(graph, start):
    visited = {start}
    queue = deque([start])
    order = []

    while queue:
        u = queue.popleft()
        order.append(u)

        for v in graph[u]:
            if v not in visited:
                visited.add(v)
                queue.append(v)

    return order
```

Giả sử `start` thuộc đồ thị, mỗi đỉnh được ánh xạ hợp lệ, và thao tác băm/so sánh định danh đỉnh có thời gian O(1) kỳ vọng:

- Mỗi đỉnh có thể tới được chỉ được đưa vào queue một lần.
- Mỗi cạnh đi ra từ các đỉnh đã thăm được xét theo biểu diễn danh sách kề.
- Thời gian cho thành phần có thể tới được: O(V_r + E_r) kỳ vọng, với `V_r` và `E_r` là số đỉnh/cạnh liên quan; nếu duyệt tất cả thành phần thì O(V+E).
- `visited` có thể chứa O(V_r) đỉnh; queue có thể giữ O(V_r) đỉnh.
- `order` là kết quả được giữ lại, có kích thước Θ(V_r).

Theo quy ước của bài, **không gian phụ trợ ngoài `order`** là O(V_r), còn **bộ nhớ đầu ra** là Θ(V_r). Nếu tính mọi bộ nhớ được tạo ra trong hàm, vẫn có O(V_r) bổ sung do ba cấu trúc cùng có kích thước tuyến tính.

### 12.2. Ma trận kề thay đổi thời gian, chưa chắc giảm bộ nhớ phụ BFS

Nếu đồ thị lưu bằng ma trận `V×V`, khi tìm láng giềng của `u` thường cần quét `V` ô. Duyệt toàn bộ các thành phần bằng BFS theo cách này mất O(V²) thời gian. `visited` và queue vẫn có thể cần O(V) bộ nhớ phụ.

Do đó:

| Biểu diễn đồ thị | Bộ nhớ đầu vào | Thời gian BFS toàn bộ | Bộ nhớ phụ BFS |
| --- | --- | --- | --- |
| Danh sách kề | O(V+E) | O(V+E) kỳ vọng với kiểm tra visited bằng băm | O(V) |
| Ma trận kề | Θ(V²) | O(V²) | O(V) |

Với đồ thị thưa (E nhỏ hơn nhiều so với V²), danh sách kề thường tiết kiệm đáng kể cả thời gian duyệt lẫn bộ nhớ lưu đồ thị. Với truy vấn kiểm tra cạnh `(u,v)` liên tục, ma trận kề có lợi thế O(1) theo chỉ số.

### 12.3. Phân biệt chạy một thành phần và toàn bộ

BFS từ một đỉnh có thể chỉ tới được một số nhỏ đỉnh. Khi đó, chi phí duyệt lõi nên gắn với `V_r,E_r`. Nếu mã cấp phát sẵn mảng `visited` dài `V` trước khi bắt đầu, phải cộng O(V) thời gian và bộ nhớ khởi tạo; phiên bản dùng tập động phía trên chỉ giữ những đỉnh đã được thăm.

Đừng tự động kết luận BFS từ một đỉnh luôn phải duyệt mọi cạnh của toàn bộ đồ thị.

## 13. Đánh đổi thời gian–không gian

Rất nhiều tối ưu tốc độ thực chất là **lưu thêm thông tin để tránh tính lại**, còn tối ưu bộ nhớ thường yêu cầu đọc hoặc tính lại thông tin nhiều lần.

### 13.1. Tìm lặp lại: duyệt tuyến tính hay tạo chỉ mục?

Giả sử có `n` bản ghi và `q` lần tìm theo khóa:

| Phương án | Chuẩn bị | Mỗi truy vấn | Bộ nhớ bổ sung |
| --- | --- | --- | --- |
| Duyệt tuyến tính mỗi lần | O(1) nếu dữ liệu đã nằm trong mảng | O(n) xấu nhất | O(1) |
| Tạo hash index | O(n) kỳ vọng trong điều kiện phù hợp | O(1) kỳ vọng | O(n) cho chỉ mục |
| Sắp bản sao chỉ mục rồi tìm nhị phân | O(n log n) | O(log n) | O(n) cho bản sao/chỉ mục |

Với `q` lớn, chỉ mục có thể tiết kiệm đáng kể thời gian. Nhưng chỉ mục phải được cập nhật khi dữ liệu thay đổi, và nó chiếm thêm bộ nhớ.

### 13.2. Memoization lưu kết quả để tránh tính lại

Ví dụ tính số Fibonacci thứ `n`:

```python
def fib_naive(n):
    if n < 2:
        return n
    return fib_naive(n - 1) + fib_naive(n - 2)
```

Số lời gọi tăng theo hàm mũ đối với `n` lớn, trong khi **độ sâu đệ quy đồng thời** chỉ O(n). Vì vậy thời gian là cấp số mũ, còn stack lời gọi O(n), nếu bỏ qua độ lớn của các số nguyên kết quả.

Dùng bảng nhớ kết quả:

```python
def fib_memo(n):
    cache = {0: 0, 1: 1}

    def compute(k):
        if k not in cache:
            cache[k] = compute(k - 1) + compute(k - 2)
        return cache[k]

    return compute(n)
```

Với `n≥1`, thuật toán chỉ tính mỗi chỉ số một lần. Nếu giả định phép cộng số nguyên có chi phí O(1), thời gian O(n), bộ nhớ bổ sung O(n) cho `cache` và O(n) stack lời gọi. Thực tế số Fibonacci lớn có độ dài bit tăng theo `n`, vì vậy khi đo chi phí bit chính xác, phép cộng và bộ nhớ lưu số nguyên lớn không còn hằng số.

Có thể dùng phiên bản **lặp** chỉ giữ hai số Fibonacci gần nhất để giảm số ô trạng thái xuống O(1) theo mô hình số từ máy (nhưng giá trị số nguyên lớn vẫn cần nhiều bit):

```python
def fib_iterative(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
```

Ví dụ cho thấy nên chọn mô hình đo phù hợp trước khi kết luận một kỹ thuật “nhanh hơn và ít bộ nhớ hơn”.

### 13.3. Tính sẵn (precompute) và tính khi cần (on demand)

Nếu ứng dụng thường xuyên hỏi cùng một tập dữ liệu về các giá trị tổng hợp, có thể tính sẵn và lưu. Nếu các câu hỏi ít xảy ra, tính khi cần tránh được bộ nhớ phụ lớn và chi phí cập nhật thông tin đã tính trước.

Ví dụ, một mảng tổng tiền tố `prefix` có thể trả tổng đoạn trong O(1) sau khi tính O(n) thời gian và lưu O(n) phần tử:

\[
\operatorname{sum}(l,r)=prefix[r+1]-prefix[l]
\]

Với `prefix[0]=0` và `prefix[i+1]=prefix[i]+a[i]`. Nếu mỗi lần chỉ hỏi một đoạn, duyệt đoạn trực tiếp có thể đủ; nếu hỏi nhiều đoạn trên dữ liệu bất biến, tiền xử lý thường đáng cân nhắc.

## 14. Đánh giá tài nguyên thực tế ngoài Big-O

Độ phức tạp là công cụ quan trọng nhưng chưa diễn đạt hết hiệu năng trên máy thật.

### 14.1. Bộ nhớ đệm (cache) và tính cục bộ

Mảng thường lưu tham chiếu hoặc phần tử liền kề, nên duyệt tuần tự có thể tận dụng cache tốt. Danh sách liên kết gồm các nút nằm rải rác, có thể phải truy cập nhiều vùng nhớ khác nhau. Cả hai đều có thể có thời gian duyệt Θ(n), nhưng thời gian đo được khác nhau.

### 14.2. Cấp phát và thu gom bộ nhớ

Cấu trúc dùng nhiều nút nhỏ có chi phí cấp phát và quản lý tham chiếu. Mảng động có thể giữ sức chứa dư hoặc cần vùng nhớ đỉnh lớn khi resize. Ngôn ngữ quản lý bộ nhớ tự động còn có ảnh hưởng từ bộ gom rác.

### 14.3. Thời gian đo và lượng nhớ đo là hai phép đo bổ sung

Ví dụ Python để đo thời gian:

```python
from time import perf_counter

def elapsed_seconds(operation):
    start = perf_counter()
    operation()
    return perf_counter() - start
```

Muốn đo đáng tin cậy hơn, cần lặp nhiều lần, làm nóng môi trường, kiểm soát dữ liệu và tách chi phí dựng đầu vào khỏi thao tác chính. Với thời gian chạy rất nhỏ, `timeit` thường phù hợp hơn.

Khi đo bộ nhớ, cần phân biệt:

- **Bộ nhớ cấu trúc đang giữ lại** sau khi thao tác hoàn tất.
- **Bộ nhớ đỉnh** trong lúc tạo bản sao, resize hoặc rehash.
- **Bộ nhớ thực của đối tượng** trong ngôn ngữ, vốn có hệ số ẩn và chi phí quản lý.

Không thể suy ra con số byte thực tế chỉ từ nhãn O(n) mà không biết biểu diễn phần tử và môi trường chạy.

## 15. Những ngộ nhận cần tránh

| Ngộ nhận | Vì sao không đúng | Cách diễn đạt chính xác |
| --- | --- | --- |
| “O(1) nghĩa là chạy tức thì.” | Hằng số có thể lớn và khác nhau giữa hệ thống. | O(1) mô tả xu hướng tăng trưởng theo `n`. |
| “O(n) là chính xác `n` bước.” | Có hệ số, bước khởi tạo và nhiều loại thao tác. | O(n) là chặn trên tiệm cận; dùng công thức nếu cần số bước chính xác. |
| “Bộ nhớ phụ O(1) nghĩa là toàn chương trình chỉ dùng một lượng RAM cố định.” | Đầu vào và đầu ra có thể dài `n`. | Phải tách bộ nhớ lưu dữ liệu và bộ nhớ thêm. |
| “Mọi hàm trả list `n` phần tử đều có không gian phụ O(n).” | Phụ thuộc có tính đầu ra trong định nghĩa hay không. | Nêu quy ước; có Θ(n) vùng chứa đầu ra. |
| “Một hàm đệ quy gọi `n` lần thì có O(n) stack.” | Các lời gọi có thể kết thúc trước khi lời gọi kế tiếp bắt đầu. | Đếm độ sâu lời gọi **đồng thời** lớn nhất. |
| “BFS tốn O(V+E) bộ nhớ.” | Đây thường là bộ nhớ lưu đồ thị; `visited` và queue chỉ O(V). | Báo riêng đầu vào O(V+E) và phụ trợ O(V). |
| “Có generator thì chương trình O(1) bộ nhớ.” | Bên gọi có thể gom lại toàn bộ kết quả. | Phân tích cả luồng tiêu thụ kết quả. |
| “Append mảng động luôn O(1).” | Lần resize có thể sao chép O(n). | O(1) khấu hao khi tăng sức chứa thích hợp. |
| “Bảng băm O(1) nên luôn tối ưu.” | Phụ thuộc hash, khóa, thứ tự và bộ nhớ. | Dùng O(1) kỳ vọng kèm giả định. |
| “Cùng Big-O thì hiệu năng bằng nhau.” | Hằng số, cache, cấp phát và kích thước phần tử khác. | Kết hợp lý thuyết với đo đạc thực tế. |

## 16. Bài tập vận dụng kèm lời giải gợi ý

### Bài 1 — Tìm phần tử lớn nhất

Hàm duyệt mảng `n` số nguyên có kích thước từ máy, giữ một biến `max_value` và cập nhật khi gặp số lớn hơn. Hãy xác định thời gian và không gian phụ trợ.

**Gợi ý:** Với `n≥1`, có `n-1` lần so sánh; thời gian Θ(n) và bộ nhớ phụ O(1). Nếu không chấp nhận mảng rỗng, cần định nghĩa lỗi hoặc giá trị đặc biệt ở đầu vào rỗng.

### Bài 2 — Tạo danh sách mới và sửa tại chỗ

Cho mảng `a` dài `n`. Phương án A dùng `a.reverse()`; phương án B dùng `reversed_copy = a[::-1]`. So sánh thời gian, bộ nhớ và tác dụng phụ.

**Gợi ý:** Cả hai thường Θ(n) thời gian. `reverse()` trên list thay đổi đầu vào với O(1) bộ nhớ phụ; cắt lát tạo list mới có Θ(n) vùng chứa đầu ra, giữ nguyên list đầu vào. Nếu các phần tử là đối tượng mutable, cắt lát là bản sao nông.

### Bài 3 — Đệ quy trên danh sách liên kết

Hàm đệ quy đếm số nút đi theo `next` tới `None`. So sánh với hàm dùng vòng lặp.

**Gợi ý:** Cả hai Θ(n) thời gian; đệ quy có Θ(n) stack lời gọi, vòng lặp O(1) bộ nhớ phụ. Với danh sách rất dài, Python có giới hạn đệ quy.

### Bài 4 — Tìm kiếm nhị phân lặp và đệ quy

Với mảng đã sắp `n` phần tử và truy cập chỉ số O(1), một phiên bản tìm kiếm nhị phân dùng `while`; phiên bản khác gọi đệ quy lên một nửa mảng mỗi lần và chỉ truyền cặp chỉ số biên. Phân tích.

**Gợi ý:** Cả hai O(log n) thời gian xấu nhất với `n≥2`. Bản lặp cần O(1) bộ nhớ phụ. Bản đệ quy cần O(log n) stack vì có nhiều mức lời gọi, dù không sao chép mảng. Nếu bản đệ quy **cắt lát tạo danh sách mới ở mỗi bước**, phải tính thêm các vùng danh sách con.

### Bài 5 — BFS trên đồ thị thưa

Đồ thị có `V=10.000` đỉnh và `E=15.000` cạnh, biểu diễn bằng danh sách kề. Chạy BFS trên mọi thành phần và dùng mảng `visited` cùng queue. Hãy nêu thời gian, bộ nhớ đầu vào và phụ trợ.

**Gợi ý:** Thời gian O(V+E), bộ nhớ lưu đồ thị O(V+E), bộ nhớ phụ BFS O(V) cho visited và queue. Nếu lưu thứ tự duyệt thành list, đầu ra cần thêm Θ(V).

### Bài 6 — Mở rộng mảng động

Một mảng động ban đầu có sức chứa 1 và tăng gấp đôi khi đầy. Chèn liên tiếp `n` phần tử mà không xóa. Vì sao một lần chèn có thể O(n), nhưng chi phí khấu hao là O(1)?

**Gợi ý:** Các lần mở rộng sao chép xấp xỉ 1, 2, 4, 8, ... phần tử. Tổng phần tử bị sao chép trong chuỗi `n` lần thêm nhỏ hơn 2n, cộng với `n` lần ghi phần tử mới nên tổng O(n), bình quân O(1). Lúc mở rộng có thể đồng thời tồn tại vùng đệm cũ và mới, làm tăng bộ nhớ đỉnh.

### Bài 7 — Tra cứu nhiều lần

Có `n` khóa và `q` truy vấn theo khóa. So sánh duyệt tuyến tính mỗi lần và xây chỉ mục hash, biết hash và so sánh khóa O(1) trong phân bố phù hợp.

**Gợi ý:** Duyệt tuyến tính O(qn) trường hợp xấu và không cần chỉ mục bổ sung. Xây bảng băm O(n) kỳ vọng, sau đó `q` truy vấn O(q) kỳ vọng, cần O(n) bộ nhớ chỉ mục. Chọn theo `q`, mức cập nhật và giới hạn bộ nhớ.

### Bài 8 — Đỉnh bộ nhớ khi sao chép

Một mảng có sức chứa `C` ô cần mở rộng sang vùng mới `2C` ô, nhưng không thể giải phóng vùng cũ trước khi sao chép xong. Tại thời điểm mở rộng, bộ nhớ các vùng đệm là bao nhiêu?

**Gợi ý:** Khoảng `C + 2C = 3C` ô nếu cả hai vùng đồng thời còn tồn tại; vẫn là Θ(C) theo Big-O nhưng cần xét hệ số 3 khi RAM bị giới hạn.

### Bài 9 — Đánh giá bộ nhớ của Merge Sort

Một cài đặt Merge Sort trên `n` phần tử dùng mảng đệm `n` ô để trộn và đệ quy sâu O(log n). Hãy nêu thời gian, bộ nhớ phụ và thành phần nào chi phối.

**Gợi ý:** Thời gian Θ(n log n), mảng đệm O(n), stack O(log n); tổng không gian phụ trợ O(n), do vùng đệm chi phối.

### Bài 10 — Phản biện một kết luận

Một báo cáo viết: “Đồ thị dùng O(V+E) bộ nhớ, nên BFS có O(V+E) không gian phụ trợ.” Hãy tìm điểm chưa rõ.

**Gợi ý:** Báo cáo đã gộp bộ nhớ **lưu biểu diễn đồ thị đầu vào** với bộ nhớ **bổ sung của BFS**. Với danh sách kề và visited + queue, đồ thị lưu O(V+E), còn BFS cần thêm O(V) bộ nhớ phụ. Nếu tính toàn hệ thống thì có thể ghi O(V+E), nhưng phải nêu quy ước.

## 17. Mẫu phân tích đầy đủ một thao tác

Trước khi chọn cấu trúc dữ liệu, thử điền mẫu sau:

```text
Tên thuật toán / thao tác:
Đặc tả kết quả đúng:
Kích thước đầu vào và biến sử dụng:
Giả định mô hình chi phí:

Thời gian:
  Phép toán được đếm:
  Số vòng lặp / lời gọi:
  Trường hợp tốt nhất:
  Trường hợp xấu nhất:
  Trung bình, kỳ vọng hoặc khấu hao (nếu áp dụng):
  Chi phí chuẩn bị và chi phí cập nhật đi kèm:

Không gian:
  Bộ nhớ lưu dữ liệu đầu vào:
  Bộ nhớ lưu cấu trúc hoặc chỉ mục:
  Bộ nhớ phụ ngoài đầu ra:
  Bộ nhớ đầu ra:
  Bộ nhớ đỉnh khi cấp phát/tạo bản sao:
  Stack đệ quy hoặc cấu trúc trung gian:

Trường hợp biên và bất biến phải giữ:
Ràng buộc về độ trễ và bộ nhớ:
Kết luận / lý do chọn biểu diễn:
```

Áp dụng mẫu cho các cấu trúc dữ liệu sẽ giúp thấy rõ tại sao mảng phù hợp khi cần truy cập chỉ số và duyệt liên tục; danh sách liên kết phù hợp khi cần cập nhật gần nút đã có; bảng băm phục vụ tra cứu theo khóa dưới giả định phù hợp; cây cân bằng đem lại giới hạn logarit cho truy vấn có thứ tự; heap phục vụ hàng đợi ưu tiên; và danh sách kề tiết kiệm tài nguyên khi đồ thị thưa.

Độ phức tạp thời gian trả lời **công việc tăng nhanh đến mức nào**. Không gian phụ trợ trả lời **thuật toán cần thêm bao nhiêu bộ nhớ ngoài dữ liệu đang có**. Khi đo rõ cả hai, cộng chi phí của các thao tác thường dùng và kiểm tra bất biến, ta mới có cơ sở kỹ thuật để chọn cấu trúc dữ liệu phù hợp với bài toán cụ thể.
