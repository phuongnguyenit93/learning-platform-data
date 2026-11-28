# Ngăn xếp đơn điệu và bất biến thứ tự

## 1. Ngăn xếp đơn điệu giải quyết vấn đề gì?

**Ngăn xếp (stack)** là kiểu dữ liệu trừu tượng tuân theo nguyên tắc **LIFO (Last In, First Out)**: phần tử được thêm sau cùng sẽ được lấy ra đầu tiên. Với stack thông thường, ta có các phép `push(x)`, `pop()` và `peek()`; nội dung trên stack không nhất thiết phải có thứ tự tăng hay giảm.

**Ngăn xếp đơn điệu (monotonic stack)** là **kỹ thuật sử dụng stack** trong đó ta duy trì thêm một **bất biến về thứ tự giá trị** của các phần tử từ đáy đến đỉnh. Trước khi đưa một phần tử mới vào, thuật toán có thể liên tục lấy khỏi đỉnh những phần tử không còn phù hợp với bất biến hoặc không còn cần thiết cho truy vấn đang xét.

Ví dụ, cho dãy:

```text
Chỉ số:   0  1  2  3  4
Giá trị:  2  1  2  4  3
```

Ta muốn biết **phần tử đầu tiên nằm bên phải và lớn hơn hẳn** mỗi phần tử hiện tại. Với `2` ở vị trí `0`, đáp án là `4` ở vị trí `3`; với `1` ở vị trí `1`, đáp án là `2` ở vị trí `2`. Quét toàn bộ phần bên phải cho từng phần tử có thể mất `O(n²)` thời gian. Ngăn xếp đơn điệu giúp xử lý toàn bộ dãy trong **`O(n)` thời gian**.

Kỹ thuật này xuất hiện trong bài toán **phần tử lớn hơn/nhỏ hơn gần nhất**, **Daily Temperatures**, **Stock Span**, **hình chữ nhật lớn nhất trong histogram** và một số bước xử lý ranh giới của dãy số.

Trong học phần **Cấu trúc dữ liệu**, đây là ví dụ điển hình về việc lựa chọn một cấu trúc dựa trên **bất biến**, **thao tác** và **độ phức tạp thời gian, bộ nhớ**. Stack vẫn hoạt động theo LIFO; điểm bổ sung là thuật toán quyết định **khi nào pop** để giữ trật tự mong muốn.

## 2. Hiểu chính xác “đơn điệu”

Một dãy được gọi là **không giảm** nếu mỗi phần tử sau lớn hơn hoặc bằng phần tử trước; **không tăng** nếu mỗi phần tử sau nhỏ hơn hoặc bằng phần tử trước. Nếu chỉ cho phép dấu lớn hơn hoặc nhỏ hơn thật sự, ta gọi là **tăng nghiêm ngặt** hoặc **giảm nghiêm ngặt**.

Khi biểu diễn thứ tự **từ đáy lên đỉnh**, có bốn dạng thường dùng:

| Bất biến giá trị của stack | Điều kiện giữa hai phần tử kề nhau | Khi thêm `x`, pop trong khi đỉnh `top` thỏa |
|---|---|---|
| Không giảm | `s₀ ≤ s₁ ≤ ... ≤ sₖ` | `top > x` |
| Tăng nghiêm ngặt | `s₀ < s₁ < ... < sₖ` | `top >= x` |
| Không tăng | `s₀ ≥ s₁ ≥ ... ≥ sₖ` | `top < x` |
| Giảm nghiêm ngặt | `s₀ > s₁ > ... > sₖ` | `top <= x` |

Ở đây, `top` trong điều kiện được hiểu là **giá trị của phần tử tại đỉnh**, còn `s₀, ..., sₖ` là giá trị các phần tử đang lưu. Các dấu trong bảng là quy tắc duy trì *thứ tự*, **chưa tự quyết định thuật toán đúng cho một truy vấn cụ thể**; với từng bài toán, còn phải xét ý nghĩa của phần tử bị loại bỏ và yêu cầu gần nhất, lớn/nhỏ nghiêm ngặt hay cho phép bằng nhau.

### Một ví dụ duy trì stack tăng nghiêm ngặt

Lần lượt đưa `[3, 1, 4, 2]` vào stack bằng quy tắc “pop khi đỉnh lớn hơn **hoặc bằng** giá trị mới”:

```text
Ban đầu: []

x = 3: push 3             → [3]
x = 1: pop 3, push 1      → [1]
x = 4: push 4             → [1, 4]
x = 2: pop 4, push 2      → [1, 2]
```

Stack cuối có giá trị tăng nghiêm ngặt. Nó **không chứa toàn bộ dữ liệu đầu vào**: các phần tử `3` và `4` đã bị loại. Điều này phù hợp nếu chúng không còn cần cho loại truy vấn đang xét; nhưng nếu bài toán cần giữ mọi phần tử, một stack đơn điệu đơn lẻ như vậy không thể thay thế việc lưu toàn bộ dữ liệu.

Cũng cần thống nhất cách gọi: một số tài liệu đặt tên “stack tăng” theo thứ tự **từ đỉnh xuống đáy** hoặc theo mục tiêu tìm phần tử lớn hơn/nhỏ hơn. Để tránh mơ hồ, bài này **luôn mô tả bất biến từ đáy đến đỉnh** và ghi rõ điều kiện `pop`.

## 3. Hai câu hỏi khi thiết kế thuật toán

Trước khi viết vòng lặp với `while stack`, hãy xác định:

1. **Muốn tìm “gần nhất” về phía nào?** Phần tử gần nhất **bên trái** thường xử lý bằng cách quét từ trái sang phải và truy vấn stack sau khi loại phần tử không phù hợp. Phần tử gần nhất **bên phải** có thể quét từ phải sang trái; hoặc quét từ trái sang phải và lưu các vị trí **đang chờ lời giải**.
2. **Quan hệ so sánh là nghiêm ngặt hay cho phép bằng nhau?** “Lớn hơn” là `>`, còn “lớn hơn hoặc bằng” là `>=`. Quy tắc pop khác nhau đúng ở trường hợp giá trị trùng lặp.

**Lưu chỉ số hay giá trị?** Đối với bài toán cần khoảng cách, vị trí, ranh giới hoặc phần tử gần nhất, thường nên lưu **chỉ số** trên stack. Giá trị của nó lấy qua `arr[index]`. Chỉ lưu giá trị có thể làm mất thông tin phân biệt hai phần tử bằng nhau ở hai vị trí khác nhau.

## 4. Bài toán 1: phần tử lớn hơn đầu tiên ở bên phải

Cho mảng `a` dài `n`. Tại mỗi chỉ số `i`, cần tìm chỉ số `j` nhỏ nhất thỏa:

\[
j>i \quad\text{và}\quad a[j]>a[i].
\]

Nếu không tồn tại `j`, kết quả tại `i` là “không có”.

### Ý tưởng quét trái sang phải

Duy trì stack gồm **chỉ số những phần tử chưa tìm thấy phần tử lớn hơn bên phải**. Các giá trị ứng với stack, từ đáy lên đỉnh, **không tăng**.

Khi gặp giá trị mới `x = a[i]`:

- Nếu `x` **lớn hơn hẳn** giá trị ở đỉnh, vị trí đỉnh vừa gặp phần tử lớn hơn đầu tiên, chính là `i`. Ta `pop` vị trí đó và ghi kết quả.
- Lặp lại khi `x` còn lớn hơn đỉnh mới.
- `push(i)` vì `a[i]` cần chờ một phần tử lớn hơn nằm về sau.

### Ví dụ Python

```python
def next_greater_right(a):
    result = [None] * len(a)
    stack = []  # Chỉ số chưa có đáp án; giá trị không tăng từ đáy đến đỉnh

    for i, value in enumerate(a):
        while stack and a[stack[-1]] < value:
            j = stack.pop()
            result[j] = value
        stack.append(i)

    return result


a = [2, 1, 2, 4, 3]
print(next_greater_right(a))
# [4, 2, 4, None, None]
```

Hàm trả **giá trị** của phần tử lớn hơn tiếp theo. Nếu bài toán yêu cầu **chỉ số** hoặc **khoảng cách**, thay `result[j] = value` bằng `result[j] = i` hoặc `result[j] = i - j`.

Dùng `None` để biểu diễn “không tìm thấy” giúp tránh nhầm với một giá trị thật, chẳng hạn `-1` có thể xuất hiện trong mảng dữ liệu.

### Truy vết từng bước

Quy ước stack lưu **chỉ số**, bảng ghi thêm giá trị tương ứng cho dễ nhìn:

| `i`, `a[i]` | Các vị trí bị pop vì gặp phần tử lớn hơn | Stack sau bước, đáy → đỉnh | Kết quả được xác định |
|---|---|---|---|
| `0, 2` | Không | `[0]` — giá trị `[2]` | — |
| `1, 1` | Không | `[0, 1]` — `[2, 1]` | — |
| `2, 2` | `1` | `[0, 2]` — `[2, 2]` | `result[1] = 2` |
| `3, 4` | `2, 0` | `[3]` — `[4]` | `result[2] = 4`; `result[0] = 4` |
| `4, 3` | Không | `[3, 4]` — `[4, 3]` | — |

Khi đọc `a[2] = 2`, ta **không** pop `a[0] = 2` vì đề yêu cầu “**lớn hơn**”, không phải “lớn hơn hoặc bằng”. Hai giá trị bằng nhau có thể cùng nằm trên stack; bất biến ở đây là **không tăng** (`>=`), chứ không phải giảm nghiêm ngặt.

Khi thuật toán kết thúc, các chỉ số còn trên stack không có phần tử lớn hơn nằm phía bên phải; kết quả của chúng giữ `None`.

### Bất biến và lập luận tính đúng

Sau khi xử lý các vị trí `0..i`:

- Stack chỉ chứa các chỉ số chưa tìm thấy phần tử lớn hơn nằm bên phải trong đoạn đã quét.
- Các chỉ số trên stack tăng từ đáy đến đỉnh, vì được `push` theo thứ tự duyệt.
- Các giá trị `a[index]` tương ứng **không tăng** từ đáy đến đỉnh.
- Nếu vị trí `j` bị pop tại `i`, `a[i] > a[j]`, và **không có vị trí `k` với `j < k < i` mà `a[k] > a[j]`**. Nếu đã có, `j` phải bị pop khi xử lý `k`. Do đó `i` đúng là vị trí phần tử lớn hơn đầu tiên bên phải `j`.

Đầu tiên stack rỗng nên các điều kiện đúng. Mỗi vòng `while` loại đúng những vị trí vừa có đáp án và duy trì thứ tự không tăng của các giá trị còn lại. Thêm `i` sau khi vòng `while` kết thúc cũng giữ bất biến. Vì vậy kết quả đúng sau khi duyệt hết.

## 5. Hai hướng quét và sự khác nhau giữa dấu `<`, `<=`

Có hai cách phổ biến để tìm phần tử lớn hơn đầu tiên ở bên phải:

**Cách A — trái sang phải, giải quyết vị trí đang chờ.** Đây là cách ở phần 4: khi gặp `a[i]`, pop các vị trí `j` có `a[j] < a[i]` và ghi kết quả cho `j`. Stack giữ giá trị **không tăng**.

**Cách B — phải sang trái, loại ứng viên vô ích.** Trước khi tìm đáp án cho `a[i]`, loại mọi phần tử ở đỉnh có giá trị **nhỏ hơn hoặc bằng** `a[i]`. Sau đó, nếu stack còn phần tử thì đỉnh là vị trí lớn hơn gần nhất bên phải.

```python
def next_greater_right_index(a):
    result = [-1] * len(a)
    stack = []  # Chỉ số ứng viên; giá trị giảm nghiêm ngặt

    for i in range(len(a) - 1, -1, -1):
        while stack and a[stack[-1]] <= a[i]:
            stack.pop()
        if stack:
            result[i] = stack[-1]
        stack.append(i)

    return result


print(next_greater_right_index([2, 1, 2, 4, 3]))
# [3, 2, 3, -1, -1]
```

Hai mã có điều kiện pop khác nhau vì **vai trò của stack khác nhau**:

- Quét trái → phải: stack chứa **vị trí đang chờ** một giá trị lớn hơn. Giá trị bằng nhau chưa giải quyết được vị trí cũ, nên không pop khi bằng.
- Quét phải → trái: stack chứa **ứng viên** để trả lời cho vị trí ở bên trái. Một ứng viên bằng hoặc nhỏ hơn giá trị hiện tại không thể làm đáp án “lớn hơn nghiêm ngặt”, nên bị loại.

Cả hai đều trả đúng khái niệm **phần tử lớn hơn đầu tiên bên phải**. Không nên học thuộc dấu so sánh tách rời **hướng quét và ý nghĩa của stack**.

## 6. Bài toán 2: phần tử nhỏ hơn gần nhất ở bên trái

Với mỗi vị trí `i`, tìm chỉ số `j` lớn nhất thỏa:

\[
j<i \quad\text{và}\quad a[j]<a[i].
\]

Đây là bài toán **phần tử nhỏ hơn nghiêm ngặt gần nhất bên trái (Previous Smaller Element)**.

Quét từ trái sang phải, dùng stack chứa các chỉ số ứng viên. Trước khi xét `a[i]`, loại mọi đỉnh có giá trị **lớn hơn hoặc bằng** `a[i]`. Nếu còn phần tử, đỉnh là ứng viên nhỏ hơn gần nhất.

```python
def previous_smaller_index(a):
    result = [-1] * len(a)
    stack = []  # Giá trị tăng nghiêm ngặt từ đáy đến đỉnh

    for i, value in enumerate(a):
        while stack and a[stack[-1]] >= value:
            stack.pop()

        if stack:
            result[i] = stack[-1]

        stack.append(i)

    return result


a = [5, 2, 2, 4, 1, 3]
print(previous_smaller_index(a))
# [-1, -1, -1, 2, -1, 4]
```

Ở vị trí `2`, `a[2] = 2`, phần tử `2` tại vị trí `1` **không nhỏ hơn hẳn**, nên kết quả vẫn `-1`. Tại vị trí `3`, `a[3] = 4`, vị trí nhỏ hơn gần nhất là `2` (giá trị `2`). Khi gặp `a[4] = 1`, thuật toán pop mọi ứng viên `>= 1` vì chúng không thể trả lời “nhỏ hơn nghiêm ngặt” cho vị trí `4` hoặc hữu ích hơn `1` cho những vị trí về sau.

Sau mỗi bước, các giá trị ứng với stack **tăng nghiêm ngặt** từ đáy đến đỉnh. Đỉnh còn lại sau khi loại phần tử không đủ nhỏ chính là vị trí gần nhất bên trái có giá trị nhỏ hơn.

### Bảng quy tắc cho bài toán “gần nhất”

Với mảng được quét từ trái sang phải để tìm **phần tử bên trái gần nhất**, ta thường dùng:

| Truy vấn cần trả cho `a[i]` | Pop khi giá trị đỉnh... | Bất biến sau push |
|---|---|---|
| Nhỏ hơn nghiêm ngặt, `< a[i]` | `>= a[i]` | Tăng nghiêm ngặt |
| Nhỏ hơn hoặc bằng, `<= a[i]` | `> a[i]` | Không giảm |
| Lớn hơn nghiêm ngặt, `> a[i]` | `<= a[i]` | Giảm nghiêm ngặt |
| Lớn hơn hoặc bằng, `>= a[i]` | `< a[i]` | Không tăng |

Bảng này dành cho mẫu **“bỏ ứng viên không hợp lệ, đọc đỉnh để lấy vị trí gần nhất bên trái, rồi push vị trí hiện tại”**. Với bài toán tìm vị trí bên phải hoặc muốn xử lý phần tử đang chờ, cần điều chỉnh theo hướng quét như phần 5.

## 7. Phần tử bằng nhau: quyết định đúng dấu so sánh

Dữ liệu trùng lặp là nơi nhiều lời giải monotonic stack sai dù chạy đúng trên dãy gồm các giá trị khác nhau.

Xét `a = [4, 4, 5]`:

- **Next greater nghiêm ngặt (`>`)** của vị trí `0` là `5` tại vị trí `2`, không phải `4` ở vị trí `1`.
- **Next greater or equal (`>=`)** của vị trí `0` là `4` tại vị trí `1`.
- **Previous smaller nghiêm ngặt (`<`)** của vị trí `1` không tồn tại; giá trị `4` ở vị trí `0` chỉ bằng nhau.
- **Previous smaller or equal (`<=`)** của vị trí `1` là giá trị `4` ở vị trí `0`.

Nếu muốn đổi thuật toán trái → phải ở phần 4 sang tìm phần tử **lớn hơn hoặc bằng** bên phải, điều kiện pop chuyển từ `a[stack[-1]] < value` thành `a[stack[-1]] <= value`. Đây là thay đổi nhỏ về mã nhưng là thay đổi lớn về hợp đồng bài toán.

Khi bài toán yêu cầu đếm số đoạn con hoặc xác định ranh giới cho **mỗi phần tử trùng nhau** một cách không chồng lặp, đôi khi cần dùng **một phía nghiêm ngặt, phía kia không nghiêm ngặt**. Ví dụ, đếm một cực tiểu xuất hiện nhiều lần trong đoạn cần gán đoạn cho một trong các vị trí bằng nhau theo một quy tắc cố định. Không nên tùy tiện dùng `>=` ở cả hai phía rồi tính số lượng đóng góp, vì có thể đếm cùng một đoạn nhiều lần.

## 8. Vì sao vòng `while pop` vẫn cho thời gian `O(n)`?

Xét thuật toán với `n` phần tử. Bên trong vòng `for` có vòng `while stack`, trông giống hai vòng lặp lồng nhau và có thể khiến người mới nghĩ rằng thời gian là `O(n²)`. Tuy nhiên, **mỗi chỉ số chỉ được push một lần và pop nhiều nhất một lần**.

Với `n` chỉ số:

- Có đúng `n` lần `push` nếu thuật toán xét mỗi vị trí một lần.
- Có **tối đa `n` lần `pop`** trong toàn bộ quá trình.
- Mỗi lần so sánh đỉnh có chi phí hằng số nếu phép so sánh phần tử là `O(1)`.
- Sau mỗi lần so sánh không dẫn đến pop, vòng `while` kết thúc ở lượt xử lý đó; số lần như vậy cũng không vượt quá cỡ `n`.

Vì thế tổng số thao tác push/pop và so sánh là **`O(n)`**, mặc dù một vòng `for` riêng lẻ có thể pop rất nhiều phần tử.

```text
a = [1, 2, 3, 4, 5]

Nếu tìm next greater (quét trái → phải):
  i = 0: push 0
  i = 1: pop 0, push 1
  i = 2: pop 1, push 2
  ...

a = [5, 4, 3, 2, 1, 6]

Khi gặp 6, có thể pop nhiều vị trí trong một lượt.
Nhưng các vị trí đó sẽ KHÔNG bị pop lần thứ hai.
```

Ta có thể hiểu `push` là tạo một “phiếu” cho phần tử; `pop` tiêu thụ phiếu đó vĩnh viễn. Tổng số phiếu tối đa là `n`. Đây là **phân tích trung bình phân bổ (amortized analysis)** trên cả dãy thao tác, không phải lời khẳng định mọi vòng `while` riêng lẻ đều tốn `O(1)`.

Bộ nhớ phụ cho stack và danh sách kết quả là **`O(n)` trong trường hợp xấu nhất**; riêng stack có thể giữ tới `n` chỉ số, chẳng hạn dãy giảm dần khi tìm next greater theo cách lưu vị trí đang chờ.

## 9. Bài toán 3: Daily Temperatures

Cho nhiệt độ của các ngày `temperatures[i]`. Với mỗi ngày, tìm **số ngày cần chờ** đến khi có nhiệt độ **cao hơn nghiêm ngặt**. Nếu không có ngày ấm hơn phía sau, trả `0`.

Ví dụ:

```text
Ngày:       0   1   2   3   4   5   6   7
Nhiệt độ:  73  74  75  71  69  72  76  73
Kết quả:    1   1   4   2   1   1   0   0
```

Áp dụng mẫu **next greater quét trái → phải**: stack chứa chỉ số ngày chưa biết thời điểm ấm hơn. Khi gặp ngày `i` có nhiệt độ cao hơn `temperatures[stack[-1]]`, ta pop ngày `j` và lưu `i - j`.

```python
def daily_temperatures(temperatures):
    wait = [0] * len(temperatures)
    stack = []

    for i, temperature in enumerate(temperatures):
        while stack and temperatures[stack[-1]] < temperature:
            previous_day = stack.pop()
            wait[previous_day] = i - previous_day
        stack.append(i)

    return wait


print(daily_temperatures([73, 74, 75, 71, 69, 72, 76, 73]))
# [1, 1, 4, 2, 1, 1, 0, 0]
```

Nhiệt độ **bằng nhau** chưa đáp ứng điều kiện “cao hơn”, nên không pop khi bằng. Mỗi ngày được push đúng một lần, pop tối đa một lần, vì vậy thời gian **`O(n)`**, bộ nhớ phụ **`O(n)`** trong trường hợp xấu nhất.

## 10. Bài toán 4: Stock Span

Giả sử biết giá cổ phiếu từng ngày `prices[0..n-1]`. **Stock Span** của ngày `i` là số ngày liên tiếp tính lùi về trước, **bao gồm cả hôm nay**, mà giá trong từng ngày đó **không lớn hơn** giá hôm nay.

Ví dụ:

```text
Giá:      [100, 80, 60, 70, 60, 75, 85]
Span:     [  1,  1,  1,  2,  1,  4,  6]
```

Với ngày giá `75` (chỉ số `5`), ta lùi qua `60`, `70`, `60` và chính ngày `75`; gặp `80` thì dừng, nên span bằng `4`.

Bài toán tương đương tìm **vị trí gần nhất bên trái có giá lớn hơn nghiêm ngặt**. Nếu vị trí đó là `j`, span bằng `i - j`; nếu không tồn tại, span là `i + 1`.

```python
def stock_span(prices):
    span = [0] * len(prices)
    stack = []  # Ứng viên ngày gần nhất có giá lớn hơn

    for i, price in enumerate(prices):
        # Giá bằng hôm nay vẫn nằm trong khoảng span.
        while stack and prices[stack[-1]] <= price:
            stack.pop()

        previous_greater = stack[-1] if stack else -1
        span[i] = i - previous_greater
        stack.append(i)

    return span


print(stock_span([100, 80, 60, 70, 60, 75, 85]))
# [1, 1, 1, 2, 1, 4, 6]

print(stock_span([100, 100, 100]))
# [1, 2, 3]
```

**Tại sao phải pop cả giá bằng?** Vì định nghĩa span cho phép giá những ngày trước **bằng** giá hôm nay. Chỉ một ngày có giá **lớn hơn hẳn** mới chặn khoảng. Nếu chỉ pop `<` và giữ các giá bằng, ví dụ `[100, 100]` sẽ bị tính span ngày thứ hai thành `1` thay vì `2`.

Stack ứng viên trong thuật toán có giá trị **giảm nghiêm ngặt** từ đáy lên đỉnh. Mỗi phần tử chỉ push một lần và pop tối đa một lần, nên tổng thời gian **`O(n)`**, bộ nhớ phụ **`O(n)`**.

### Xử lý giá đến liên tục

Nếu giá cổ phiếu tới từng ngày thay vì có sẵn toàn bộ mảng, ta có thể duy trì stack các cặp `(price, span)`. Khi nhận giá mới, cộng dồn span của các nhóm đỉnh có giá `<=` giá mới, rồi push kết quả:

```python
class OnlineStockSpan:
    def __init__(self):
        self._stack = []  # (price, span_of_block)

    def next(self, price):
        span = 1
        while self._stack and self._stack[-1][0] <= price:
            span += self._stack.pop()[1]
        self._stack.append((price, span))
        return span


tracker = OnlineStockSpan()
print([tracker.next(p) for p in [100, 80, 60, 70, 60, 75, 85]])
# [1, 1, 1, 2, 1, 4, 6]
```

Mỗi nhóm trong stack đại diện cho một khối ngày liên tiếp đã được gộp, nên có thể tính span của ngày mới **mà không duyệt từng ngày trong khối**. Một lượt `next()` có thể pop nhiều nhóm, nhưng qua `n` lần gọi tổng số push/pop vẫn `O(n)`: **`O(1)` thời gian trung bình phân bổ mỗi ngày**, **`O(n)` bộ nhớ** trong trường hợp xấu nhất.

## 11. Bài toán 5: hình chữ nhật lớn nhất trong histogram

Cho một histogram gồm các cột có độ rộng `1`, chiều cao lần lượt là `heights[i]`, với `heights[i] >= 0`. Tìm **diện tích hình chữ nhật lớn nhất** nằm dưới các cột liên tiếp.

Ví dụ:

```text
heights = [2, 1, 5, 6, 2, 3]

Cột có chiều cao 5 và 6 đứng cạnh nhau;
chọn chiều cao 5, chiều rộng 2 → diện tích 10.
Đó là diện tích lớn nhất của ví dụ này.
```

Nếu cố định một cột có chiều cao `h`, hình chữ nhật cao `h` có thể kéo dài sang trái và phải chừng nào các cột còn có chiều cao **ít nhất bằng `h`**. Vậy ta cần tìm ranh giới **thấp hơn `h`** gần nhất ở hai phía.

Một thuật toán hiệu quả quét từ trái sang phải, dùng stack chứa **chỉ số các cột có chiều cao không giảm**. Khi gặp cột mới có chiều cao **thấp hơn đỉnh**, cột trên đỉnh vừa tìm được ranh giới phải cho hình chữ nhật có chiều cao đó.

### Quy tắc tính độ rộng khi pop

Giả sử đang ở chỉ số `i`, vừa pop chỉ số `k` có chiều cao `h = heights[k]`:

- Vị trí `i` là **ranh giới bên phải** với chiều cao nhỏ hơn `h`. Hình chữ nhật cao `h` chỉ có thể kéo dài tối đa đến `i - 1`.
- Sau khi pop `k`, đỉnh mới (nếu có) là ranh giới bên trái cần xét, gọi là `left`. Nếu stack rỗng, đặt `left = -1`.
- Số cột hợp lệ trong khoảng giữa hai ranh giới là `i - left - 1`.
- Diện tích ứng viên là `h * (i - left - 1)`.

```python
def largest_rectangle_area(heights):
    stack = []  # Chỉ số cột, chiều cao không giảm
    best = 0
    n = len(heights)

    for i in range(n + 1):
        # Cột ảo chiều cao 0 ở cuối để xử lý các cột còn lại.
        current = heights[i] if i < n else 0

        while stack and heights[stack[-1]] > current:
            height = heights[stack.pop()]
            left = stack[-1] if stack else -1
            width = i - left - 1
            best = max(best, height * width)

        if i < n:
            stack.append(i)

    return best


print(largest_rectangle_area([2, 1, 5, 6, 2, 3]))  # 10
print(largest_rectangle_area([2, 4]))              # 4
print(largest_rectangle_area([2, 2, 2]))           # 6
print(largest_rectangle_area([]))                  # 0
```

### Vì sao cách tính đúng khi có cột bằng nhau?

Ở đây, điều kiện pop là `>`, nên cột bằng chiều cao nhau **có thể cùng tồn tại** trên stack. Khi một chiều cao nhỏ hơn xuất hiện, cột bằng nhau ở bên phải có thể được pop trước và tạo một hình chữ nhật hẹp hơn; sau đó các cột bằng nhau đứng trước cũng được pop, mở rộng độ rộng ra toàn bộ đoạn hợp lệ.

Ví dụ `[2, 2, 2]`: khi gặp cột ảo `0` ở cuối, lần lượt pop ba cột `2` và tính được các độ rộng `1`, `2`, `3`. Diện tích lớn nhất là `2 * 3 = 6`.

Có thể chọn quy tắc pop `>=` để loại cột bằng nhau sớm hơn, nhưng khi làm vậy phải kiểm tra lại cách xác định ranh giới và xử lý giá trị trùng. Trong phiên bản ở trên, việc giữ stack **không giảm** và pop khi `>` là một quy tắc nhất quán.

**Độ phức tạp:** mỗi chỉ số được push một lần, pop tối đa một lần; toàn bộ thuật toán tốn **`O(n)` thời gian** và stack cần tối đa **`O(n)` bộ nhớ phụ**.

### Bất biến quan trọng

Ngay sau mỗi vòng lặp và trước khi xét cột tiếp theo, stack lưu các chỉ số theo thứ tự tăng, với chiều cao **không giảm** từ đáy lên đỉnh. Các cột còn trên stack chưa gặp một cột thấp hơn làm kết thúc vùng mà chúng có thể mở rộng sang phải. Khi một cột bị pop, hình chữ nhật tương ứng được tính đúng trước khi mất thông tin về vị trí đó.

## 12. Stack đơn điệu khác stack thường, heap và deque thế nào?

| Cấu trúc/kỹ thuật | Thao tác chính | Bất biến đặc trưng | Bài toán phù hợp |
|---|---|---|---|
| **Stack thường** | `push`, `pop` ở đỉnh | LIFO | Undo, đệ quy tường minh, ngoặc |
| **Stack đơn điệu** | `push`, pop có điều kiện trước khi push | Thứ tự giá trị của các phần tử còn lưu | Phần tử lớn/nhỏ gần nhất, Stock Span, histogram |
| **Heap/Priority Queue** | Đưa vào, lấy phần tử ưu tiên | Quan hệ heap giữa cha và con | Lấy min/max toàn cục theo ưu tiên |
| **Deque đơn điệu** | Thêm/xóa ở hai đầu theo điều kiện | Thứ tự ứng viên cộng giới hạn cửa sổ | Min/max của cửa sổ trượt theo chỉ số |

**Stack đơn điệu không phải danh sách đã sắp xếp toàn bộ dữ liệu đầu vào.** Nó giữ các ứng viên cần thiết cho truy vấn và loại phần tử ở đỉnh theo quy tắc. Cũng không phải cấu trúc cho phép lấy phần tử nhỏ nhất tùy ý: thao tác pop luôn lấy ở đỉnh của stack.

Đối với bài toán **cực trị trong cửa sổ trượt** (ví dụ min của mỗi đoạn gồm `k` phần tử liên tiếp), khi một chỉ số cũ đi ra khỏi cửa sổ, ta thường cần xóa nó ở **đầu** danh sách ứng viên. **Deque đơn điệu** phù hợp vì có thể loại ứng viên ở cả hai đầu; stack đơn điệu đơn lẻ không hỗ trợ tự nhiên việc này.

## 13. Những lỗi thường gặp và cách tự kiểm tra

1. **Nhầm “lớn hơn” với “lớn hơn hoặc bằng”.** Với `[4, 4, 5]`, next greater nghiêm ngặt của phần tử đầu là `5`, còn next greater or equal là `4` thứ hai. Hãy kiểm thử phần tử trùng lặp.
2. **Học thuộc dấu pop mà quên hướng quét.** Cùng bài toán next greater bên phải, mã quét trái → phải để giải vị trí chờ dùng `<`, mã quét phải → trái để loại ứng viên dùng `<=`.
3. **Lưu giá trị khi bài toán cần vị trí.** Nếu phải trả số ngày chờ hoặc khoảng cách, cần lưu chỉ số, nếu không sẽ khó xác định khoảng cách đúng cho các giá trị bằng nhau.
4. **Pop phần tử rồi quên ghi đáp án.** Trong mẫu vị trí đang chờ, lúc pop chính là lúc tìm được câu trả lời; phải lưu lại trước khi chỉ số rời stack.
5. **Quên xử lý những phần tử còn trên stack.** Với next greater, chúng không có đáp án và phải nhận giá trị quy ước “không tồn tại”; với histogram, cần duyệt thêm cột ảo hoặc xả stack ở cuối.
6. **Đặt tên “tăng” mà không nêu chiều.** Hãy viết rõ “tăng nghiêm ngặt từ đáy lên đỉnh” hoặc “không tăng từ đáy lên đỉnh” để tránh hiểu ngược.
7. **Nghĩ có `while` trong `for` nghĩa là `O(n²)`.** Chứng minh lại tổng số push/pop: mỗi chỉ số chỉ vào một lần và rời tối đa một lần.
8. **Nhầm `O(n)` tổng với `O(1)` của từng vòng lặp.** Một lần thêm phần tử có thể pop `O(n)` vị trí; toàn bộ `n` lượt vẫn chỉ `O(n)`.
9. **Dùng kỹ thuật đơn điệu khi cần giữ toàn bộ dữ liệu.** Phần tử bị pop khỏi stack ứng viên không còn nằm ở đó; dữ liệu đầu vào vẫn phải tồn tại riêng nếu ứng dụng còn cần truy cập toàn bộ.
10. **Không kiểm tra đầu vào rỗng hoặc các dãy đặc biệt.** Thử `[]`, một phần tử, toàn phần tử bằng nhau, tăng đều, giảm đều và dữ liệu âm.

Các đoạn kiểm tra nhanh sau sử dụng các hàm đã xây dựng ở trên:

```python
assert next_greater_right([]) == []
assert next_greater_right([4, 4, 5]) == [5, 5, None]
assert previous_smaller_index([2, 2, 3]) == [-1, -1, 1]
assert daily_temperatures([70, 70, 71]) == [2, 1, 0]
assert stock_span([100, 100, 90]) == [1, 2, 1]
assert largest_rectangle_area([0, 0, 0]) == 0
assert largest_rectangle_area([2, 2, 2]) == 6
```

## 14. Bài tập tự luyện tập có đáp án

### Bài 1. Next greater bên phải

Cho `a = [3, 1, 4, 2, 5]`. Hãy trả giá trị phần tử lớn hơn đầu tiên bên phải cho từng vị trí.

**Đáp án:** `[4, 4, 5, 5, None]`. Với `3`, giá trị lớn hơn đầu tiên là `4`; với `1` cũng là `4`; với `4` và `2` đều là `5`; phần tử `5` cuối không có phần tử lớn hơn bên phải.

### Bài 2. Stack ứng viên nhỏ hơn bên trái

Cho `a = [6, 3, 3, 5, 2]`. Hãy trả chỉ số phần tử **nhỏ hơn nghiêm ngặt gần nhất bên trái** của từng phần tử.

**Đáp án:** `[-1, -1, -1, 2, -1]`. Tại vị trí `2`, giá trị `3` ở vị trí `1` không nhỏ hơn nghiêm ngặt nên đáp án vẫn `-1`. Tại vị trí `3` (giá trị `5`), chỉ số nhỏ hơn gần nhất là `2`.

### Bài 3. Giá trị bằng nhau

Với dãy `[2, 2, 2]`, next greater nghiêm ngặt của từng phần tử là gì? Nếu đổi đề thành next greater or equal, kết quả là gì?

**Đáp án:** Next greater nghiêm ngặt đều không tồn tại: `[None, None, None]`. Next greater or equal theo thứ tự vị trí gần nhất bên phải là `[2, 2, None]`.

### Bài 4. Tính Stock Span

Cho dãy giá `[30, 20, 20, 25, 35]`. Tính span từng ngày theo định nghĩa “các ngày liên tiếp gần nhất có giá `<=` giá hôm nay, tính cả hôm nay”.

**Đáp án:** `[1, 1, 2, 3, 5]`. Ngày giá `25` bao gồm `20, 20, 25` và dừng ở `30`; ngày giá `35` bao phủ toàn bộ năm ngày.

### Bài 5. Hình chữ nhật histogram

Cho `heights = [3, 1, 3, 3]`. Diện tích lớn nhất là bao nhiêu?

**Đáp án:** `6`, vì hai cột cuối có chiều cao `3` đứng cạnh nhau nên có hình chữ nhật cao `3`, rộng `2`, diện tích `6`. Hình chữ nhật chiều cao `1` kéo dài bốn cột chỉ có diện tích `4`.

### Bài 6. Phân tích tổng thao tác

Với dãy gồm `n` phần tử, một thuật toán stack đơn điệu push mỗi chỉ số đúng một lần. Một số vòng lặp có thể pop nhiều chỉ số. Tối đa có bao nhiêu lần pop trong toàn thuật toán?

**Đáp án:** Tối đa `n` lần pop. Mỗi chỉ số chỉ được đưa vào một lần và khi bị pop sẽ không quay lại. Vì vậy tổng thao tác stack là `O(n)`.

### Bài 7. Chọn cấu trúc phù hợp

Một chương trình cần biết giá trị lớn nhất trong **mỗi cửa sổ trượt dài `k`** và phải loại những phần tử đã ra khỏi cửa sổ. Có nên dùng một stack đơn điệu chỉ cho phép pop đỉnh không?

**Đáp án:** Thường nên dùng **deque đơn điệu** chứa chỉ số. Cần loại phần tử quá cũ ở đầu deque, đồng thời loại các ứng viên yếu ở cuối. Stack chỉ thao tác ở một đầu không hỗ trợ tự nhiên cả hai việc này.

## 15. Những điều cần ghi nhớ

Ngăn xếp đơn điệu là **stack LIFO có thêm bất biến thứ tự giá trị**. Để duy trì bất biến, thuật toán `pop` các phần tử ở đỉnh không còn phù hợp rồi mới `push` phần tử hiện tại. Điều kiện pop phải được chọn từ **hướng quét, loại truy vấn và cách xử lý giá trị bằng nhau**.

Với bài toán phần tử lớn hơn hoặc nhỏ hơn gần nhất, stack thường lưu **chỉ số** để vừa so sánh giá trị vừa xác định vị trí và khoảng cách. Mỗi chỉ số được đưa vào stack một lần và lấy ra nhiều nhất một lần, giúp nhiều bài toán vốn có lời giải quét đôi `O(n²)` được xử lý trong **`O(n)` thời gian**, dùng tối đa **`O(n)` bộ nhớ phụ**.

Điểm quan trọng nhất khi vận dụng là phát biểu chính xác **bất biến từ đáy đến đỉnh**, giải thích được **vì sao phần tử bị pop không còn cần thiết**, rồi kiểm tra lại thuật toán với trường hợp **giá trị trùng, dãy rỗng, tăng, giảm**. Đó cũng là cách lựa chọn và chứng minh đúng một cấu trúc dữ liệu trong các bài toán về mảng, stack và thuật toán.
