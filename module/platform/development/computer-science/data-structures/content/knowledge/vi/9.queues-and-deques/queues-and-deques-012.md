# Deque đơn điệu cho cực trị trên cửa sổ trượt

Khi xử lý một dãy số, ta thường cần tìm **giá trị lớn nhất hoặc nhỏ nhất trong mỗi đoạn liên tiếp có độ dài cố định**. Ví dụ, hệ thống giám sát muốn biết nhiệt độ cao nhất trong 60 mẫu gần nhất, hoặc một ứng dụng cần giá trị thấp nhất trong mỗi 10 phép đo liên tiếp. Cách duyệt lại tất cả phần tử của từng đoạn khá dễ viết nhưng có thể tốn nhiều thời gian khi số lượng phần tử lớn.

**Deque đơn điệu** (*monotonic deque*) giúp giải bài toán này trong **O(n) thời gian** với một dãy gồm `n` phần tử, thay vì O(nk) khi duyệt lại từng cửa sổ độ rộng `k`. Ý tưởng là chỉ giữ những **ứng viên còn có khả năng trở thành cực trị** và loại bỏ ngay các ứng viên đã hết hạn hoặc bị một phần tử mới hơn, tốt hơn chi phối.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong nền tảng cấu trúc dữ liệu từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap tới đồ thị, ví dụ này cho thấy một deque không chỉ là nơi thêm/lấy ở hai đầu: khi kết hợp với **bất biến về thứ tự**, nó tạo nên thuật toán có độ phức tạp được chứng minh bằng phân tích khấu hao.

## 1. Bài toán cực trị trên cửa sổ trượt

Cho dãy `a` gồm `n` giá trị:

```text
a = [1, 3, -1, -3, 5, 3, 6, 7]
k = 3
```

Một **cửa sổ trượt** độ dài `k` là đoạn gồm `k` phần tử liên tiếp. Với cửa sổ kết thúc ở chỉ số `i` (tính từ 0), đoạn hợp lệ là:

```text
[i - k + 1, i]    khi i >= k - 1
```

Với ví dụ trên:

| Cửa sổ | Chỉ số | Các giá trị | Cực đại | Cực tiểu |
|---:|---|---|---:|---:|
| 1 | `0..2` | `[1, 3, -1]` | 3 | -1 |
| 2 | `1..3` | `[3, -1, -3]` | 3 | -3 |
| 3 | `2..4` | `[-1, -3, 5]` | 5 | -3 |
| 4 | `3..5` | `[-3, 5, 3]` | 5 | -3 |
| 5 | `4..6` | `[5, 3, 6]` | 6 | 3 |
| 6 | `5..7` | `[3, 6, 7]` | 7 | 3 |

Kết quả mong muốn:

```text
Sliding maximum: [3, 3, 5, 5, 6, 7]
Sliding minimum: [-1, -3, -3, -3, 3, 3]
```

Nếu `1 ≤ k ≤ n`, sẽ có đúng `n - k + 1` cửa sổ. Ta cần đưa ra một kết quả cho mỗi cửa sổ theo thứ tự từ trái sang phải.

### Vì sao thuật toán trực tiếp tốn O(nk)?

Có thể duyệt qua từng vị trí bắt đầu và tính `max` hoặc `min` của đoạn `k` phần tử:

```python
def sliding_max_slow(a, k):
    if not 1 <= k <= len(a):
        raise ValueError("Cần 1 <= k <= len(a)")
    return [
        max(a[start:start + k])
        for start in range(len(a) - k + 1)
    ]
```

Có khoảng `n - k + 1` cửa sổ, mỗi lần tìm cực đại cần xem `k` phần tử. Thời gian là:

```text
Θ((n - k + 1) × k)
```

Thường được mô tả bằng cận trên **O(nk)**; trong trường hợp `k` tỷ lệ với `n` (chẳng hạn `k ≈ n/2`), thời gian có thể lên tới **Θ(n²)**. Mã trên còn tạo lát cắt `a[start:start+k]`, nên phát sinh bản sao đoạn dài `k` ở mỗi lần lặp; có thể tránh bản sao bằng vòng lặp duyệt trực tiếp, nhưng không loại được công việc quét lại.

Ta cần tận dụng thông tin từ cửa sổ trước khi cửa sổ dịch sang phải.

## 2. Vì sao deque phù hợp?

**Deque** (*double-ended queue*, hàng đợi hai đầu) hỗ trợ thêm và lấy ở **cả hai đầu**. Đối với bài toán cực đại, ta chỉ cần ba phép chính:

| Phép deque | Ý nghĩa đối với thuật toán |
|---|---|
| `append(i)` | Thêm **chỉ số** của phần tử mới vào cuối |
| `popleft()` | Loại phần tử ở đầu nếu nó đã **ra khỏi cửa sổ** |
| `pop()` | Loại ứng viên ở cuối bị phần tử mới **chi phối** |
| `dq[0]` | Đọc chỉ số của ứng viên cực đại/cực tiểu tốt nhất |

Ta giữ **chỉ số** thay vì chỉ giữ giá trị. Điều này cho phép đồng thời kiểm tra:

1. **Tuổi của phần tử:** một chỉ số có còn nằm trong cửa sổ hay không?
2. **Giá trị của phần tử:** nó có còn là ứng viên cực đại hay cực tiểu tốt nhất không?

Trong Python, `collections.deque` cung cấp `append`, `popleft` và `pop` hiệu quả ở hai đầu. Dùng một `list` và gọi `pop(0)` nhiều lần sẽ có thể gây dịch chuyển O(k) phần tử, làm mất ưu điểm của thuật toán.

### Hai loại phần tử bị loại khỏi deque

Tại bước đang xử lý chỉ số `i`, có hai lý do để loại một ứng viên:

- **Hết hạn:** chỉ số `j ≤ i - k`, nghĩa là `j` nằm trước biên trái cửa sổ mới `i - k + 1`. Ứng viên đó không được góp mặt trong kết quả.
- **Bị chi phối:** tồn tại phần tử **mới hơn** có giá trị **không nhỏ hơn** ứng viên cũ đối với bài toán cực đại, hoặc **không lớn hơn** đối với cực tiểu. Ứng viên cũ không còn cần thiết cho các cửa sổ hiện tại và tương lai.

Loại phần tử hết hạn ở **đầu**, loại ứng viên bị chi phối ở **cuối**: chính nhu cầu thao tác ở cả hai phía tạo nên sức mạnh của monotonic deque.

## 3. Deque đơn điệu giảm cho giá trị lớn nhất

Để tìm cực đại, ta giữ các **chỉ số** trong deque sao cho:

1. Các chỉ số tăng **nghiêm ngặt** từ đầu tới cuối, vì phần tử mới luôn có chỉ số lớn hơn.
2. Giá trị tại các chỉ số giảm **nghiêm ngặt** từ đầu tới cuối nếu ta loại phần tử cũ khi giá trị `≤` phần tử mới.
3. Mọi chỉ số còn lại đều thuộc phạm vi cửa sổ hợp lệ tại thời điểm xuất kết quả.
4. Khi cửa sổ đã đủ `k` phần tử, **đầu deque là chỉ số của cực đại**.

Ví dụ deque chứa các chỉ số `[4, 5]` với `a[4] = 5`, `a[5] = 3`:

```text
Deque ứng viên:
front                  back
  |                      |
  v                      v
 [4:5]  ───────────→   [5:3]

Chỉ số: 4 < 5
Giá trị: 5 > 3
Cực đại hiện tại = a[4] = 5
```

Nếu phần tử mới `a[6] = 6` xuất hiện:

- Giá trị `3 ≤ 6`, nên bỏ chỉ số `5` ở cuối.
- Giá trị `5 ≤ 6`, nên bỏ tiếp chỉ số `4`.
- Thêm chỉ số `6`. Deque chỉ còn `[6:6]`.

Ta không cần giữ `4` hoặc `5` làm ứng viên cực đại nữa: phần tử tại `6` vừa **lớn hơn** vừa **mới hơn**, nên trong mọi cửa sổ tương lai chứa một trong hai phần tử cũ và còn chứa `6`, phần tử `6` tốt hơn. Khi `6` hết hạn, các chỉ số `4` và `5` đã hết hạn từ trước.

### Quy tắc xử lý một chỉ số mới

Với mỗi `i`, ta làm theo thứ tự:

1. **Loại hết hạn ở đầu:** trong khi `dq[0] ≤ i - k`, gọi `popleft()`.
2. **Loại ứng viên yếu ở cuối:** trong khi `a[dq[-1]] ≤ a[i]`, gọi `pop()`.
3. **Thêm chỉ số mới:** `dq.append(i)`.
4. **Xuất kết quả:** nếu `i ≥ k - 1`, cực đại là `a[dq[0]]`.

Bước 2 sử dụng **`≤`**. Vì vậy, khi hai giá trị bằng nhau, ta bỏ chỉ số **cũ hơn** và giữ chỉ số **mới hơn**. Điều này giúp dãy giá trị trong deque giảm nghiêm ngặt, đồng thời có lợi về thời gian sống: ứng viên mới sẽ hết hạn muộn hơn hoặc cùng lúc ứng viên cũ (thực tế muộn hơn nếu chỉ số khác nhau).

### Giả mã sliding maximum

```text
SLIDING_MAX(a, k):
    require 1 <= k <= length(a)
    dq = deque rỗng, lưu các chỉ số
    answer = []

    for i = 0 đến length(a) - 1:
        while dq không rỗng và dq.front() <= i - k:
            dq.pop_front()               # Hết hạn

        while dq không rỗng và a[dq.back()] <= a[i]:
            dq.pop_back()                # Bị phần tử mới chi phối

        dq.push_back(i)

        if i >= k - 1:
            answer.append(a[dq.front()])

    return answer
```

Lưu ý **không cần chờ đủ `k` phần tử mới duy trì deque**. Thuật toán xử lý các phần tử ngay từ `i = 0`; chỉ trì hoãn việc ghi kết quả đến khi cửa sổ đầu tiên được hình thành.

## 4. Truy vết chi tiết một ví dụ cực đại

Xét lại:

```text
a = [1, 3, -1, -3, 5, 3, 6, 7]
k = 3
```

Bảng dưới ghi trạng thái deque **sau** khi loại hết hạn, loại phần tử bị chi phối và thêm chỉ số `i`. Mỗi mục `j:v` nghĩa là chỉ số `j` mang giá trị `v`.

| `i` | `a[i]` | Chỉ số bị loại do hết hạn | Chỉ số bị loại ở cuối | Deque sau bước (front → back) | Cực đại vừa xuất |
|---:|---:|---|---|---|---:|
| 0 | 1 | — | — | `[0:1]` | — |
| 1 | 3 | — | 0 | `[1:3]` | — |
| 2 | -1 | — | — | `[1:3, 2:-1]` | 3 |
| 3 | -3 | — | — | `[1:3, 2:-1, 3:-3]` | 3 |
| 4 | 5 | 1 | 3, 2 | `[4:5]` | 5 |
| 5 | 3 | — | — | `[4:5, 5:3]` | 5 |
| 6 | 6 | — | 5, 4 | `[6:6]` | 6 |
| 7 | 7 | — | 6 | `[7:7]` | 7 |

Ở `i = 4`, cửa sổ mới là `[2, 4]` với các giá trị `[-1, -3, 5]`. Chỉ số `1` đã ra khỏi cửa sổ nên bị lấy ở đầu. Sau đó `5` mới xuất hiện và lớn hơn các ứng viên còn lại, khiến `3` và `2` bị xóa từ cuối. Deque cuối bước chỉ còn `[4:5]`.

Kết quả theo thứ tự sáu cửa sổ:

```text
[3, 3, 5, 5, 6, 7]
```

**Không phải mọi phần tử trong cửa sổ đều nằm trong deque.** Deque chỉ lưu những ứng viên **chưa bị chi phối**. Ví dụ cửa sổ `[2, 4]` chứa ba phần tử nhưng deque chỉ lưu chỉ số `4`; đó là điều đúng đắn, không phải thiếu dữ liệu.

## 5. Cài đặt Python tìm cực đại cửa sổ

```python
from collections import deque


def sliding_window_max(nums, k):
    """Trả cực đại của mỗi cửa sổ liên tiếp độ rộng k."""
    n = len(nums)
    if not 1 <= k <= n:
        raise ValueError("Cần 1 <= k <= len(nums)")

    dq = deque()    # Lưu chỉ số, không lưu riêng giá trị.
    result = []

    for i, value in enumerate(nums):
        # Mọi chỉ số <= i-k đều nằm ngoài cửa sổ kết thúc tại i.
        while dq and dq[0] <= i - k:
            dq.popleft()

        # Loại ứng viên cũ có giá trị <= phần tử mới.
        while dq and nums[dq[-1]] <= value:
            dq.pop()

        dq.append(i)

        if i >= k - 1:
            result.append(nums[dq[0]])

    return result


a = [1, 3, -1, -3, 5, 3, 6, 7]
assert sliding_window_max(a, 3) == [3, 3, 5, 5, 6, 7]

assert sliding_window_max([4, 2, 12, 3, 8, 7], 3) == [12, 12, 12, 8]
assert sliding_window_max([9, 8, 7, 6], 2) == [9, 8, 7]
assert sliding_window_max([2, 2, 2], 2) == [2, 2]
```

Trong mã này, `dq` lưu các chỉ số theo thứ tự tăng, còn `nums[dq[0]]` là cực đại của cửa sổ hiện hành khi đủ `k` phần tử. Thao tác `append`, `pop` và `popleft` trên `collections.deque` có chi phí hằng số tại hai đầu, đúng với yêu cầu của thuật toán.

Đừng thay `popleft()` bằng `pop(0)` trên `list` nếu muốn giữ phân tích O(n), vì việc xóa đầu danh sách mảng có thể mất O(k) cho một lần.

## 6. Đối xứng: deque đơn điệu tăng cho giá trị nhỏ nhất

Đối với **cực tiểu**, ta giữ các chỉ số có giá trị **tăng nghiêm ngặt** từ đầu đến cuối. Ứng viên ở đầu có giá trị nhỏ nhất.

Ta chỉ cần đổi **bất đẳng thức khi loại ở cuối**:

- Tìm **cực đại**: bỏ `a[dq[-1]] ≤ a[i]`.
- Tìm **cực tiểu**: bỏ `a[dq[-1]] ≥ a[i]`.

Còn lại, thứ tự thao tác loại hết hạn, thêm chỉ số, xuất kết quả vẫn như nhau.

### Giả mã sliding minimum

```text
SLIDING_MIN(a, k):
    require 1 <= k <= length(a)
    dq = deque rỗng, lưu các chỉ số
    answer = []

    for i = 0 đến length(a) - 1:
        while dq không rỗng và dq.front() <= i - k:
            dq.pop_front()

        while dq không rỗng và a[dq.back()] >= a[i]:
            dq.pop_back()

        dq.push_back(i)

        if i >= k - 1:
            answer.append(a[dq.front()])

    return answer
```

### Cài đặt Python tìm cực tiểu

```python
from collections import deque


def sliding_window_min(nums, k):
    """Trả cực tiểu của mỗi cửa sổ liên tiếp độ rộng k."""
    n = len(nums)
    if not 1 <= k <= n:
        raise ValueError("Cần 1 <= k <= len(nums)")

    dq = deque()
    result = []

    for i, value in enumerate(nums):
        while dq and dq[0] <= i - k:
            dq.popleft()

        # Ở cực tiểu: giá trị mới <= giá trị cũ thì giữ chỉ số mới.
        while dq and nums[dq[-1]] >= value:
            dq.pop()

        dq.append(i)

        if i >= k - 1:
            result.append(nums[dq[0]])

    return result


a = [1, 3, -1, -3, 5, 3, 6, 7]
assert sliding_window_min(a, 3) == [-1, -3, -3, -3, 3, 3]
assert sliding_window_min([4, 2, 12, 3, 8, 7], 3) == [2, 2, 3, 3]
assert sliding_window_min([3, 3, 3], 2) == [3, 3]
```

**Cực đại và cực tiểu đều dùng chung ý tưởng:** chỉ giữ các ứng viên chưa bị phần tử mới chi phối, và loại chỉ số cũ khi nó ra khỏi cửa sổ. Thay đổi dấu so sánh tạo ra hai bất biến đơn điệu đối xứng.

## 7. Vì sao phải lưu chỉ số, không chỉ lưu giá trị?

Một cửa sổ trượt cần biết **khi nào phần tử hết hạn**. Nếu deque chỉ chứa các giá trị, ta khó xác định phần tử nào đã ra khỏi cửa sổ, đặc biệt khi có nhiều giá trị bằng nhau.

Xét:

```text
a = [5, 5, 1]
k = 2
```

Cửa sổ đầu là `[5, 5]`, cửa sổ tiếp theo là `[5, 1]`. Cực đại của cả hai cửa sổ đều bằng `5`, nhưng hai số `5` thuộc **hai chỉ số khác nhau**:

```text
Chỉ số:   0   1   2
Giá trị: [5,  5,  1]
           ^   ^
      cửa sổ đầu

Cửa sổ thứ hai: [chỉ số 1, chỉ số 2]
```

Nếu chỉ giữ giá trị `5` mà không biết nó đến từ chỉ số `0` hay `1`, việc loại đúng phần tử hết hạn trở nên nhập nhằng. Một phương án lưu giá trị cùng **số lượng hoặc thông tin thời điểm** cũng có thể hoạt động, nhưng việc lưu **chỉ số gốc** là đơn giản nhất cho dãy có thể truy cập theo chỉ số.

Chỉ số còn giúp xử lý phần tử trùng nhau chính xác mà không nhầm “bỏ ứng viên” với “bỏ một giá trị khỏi dãy gốc”. Thuật toán **không thay đổi mảng đầu vào**; nó chỉ thay đổi danh sách chỉ số ứng viên trong deque.

## 8. Xử lý các giá trị bằng nhau: chọn `<` hay `≤`?

Đối với cực đại, có hai cách đều đúng nếu được áp dụng nhất quán:

- **Dùng `≤`:** khi phần tử mới bằng ứng viên cuối, loại ứng viên cũ. Deque có các giá trị **giảm nghiêm ngặt**.
- **Dùng `<`:** khi phần tử mới bằng ứng viên cuối, **giữ cả hai chỉ số**. Deque có các giá trị **không tăng** (cho phép bằng nhau).

Với `a = [5, 5, 5]`:

```text
Dùng <= khi thêm:
i=0: [0]
i=1: [1]       (loại 0 vì a[0] <= a[1])
i=2: [2]       (loại 1 vì a[1] <= a[2])

Dùng < khi thêm:
i=0: [0]
i=1: [0, 1]    (giữ cả hai số 5)
i=2: [0, 1, 2]
```

Hai lựa chọn đều cho cùng giá trị cực đại trong các cửa sổ, nếu vẫn loại chỉ số hết hạn đúng lúc. Trong bài này, ta chọn **`≤` cho cực đại** và **`≥` cho cực tiểu** để ưu tiên phần tử có cùng giá trị nhưng **mới hơn**, làm số ứng viên trong deque không tăng vì các giá trị bằng nhau.

Việc loại chỉ số cũ bằng nhau là an toàn vì phần tử mới có **giá trị bằng** và **thời điểm hết hạn muộn hơn**. Không cần giữ cả hai để tính **giá trị cực trị**.

**Giới hạn quan trọng:** nếu bài toán yêu cầu **trả chỉ số xuất hiện sớm nhất** của cực đại (không chỉ giá trị), chính sách loại phần tử bằng nhau sẽ ảnh hưởng đến kết quả chỉ số. Khi đó có thể cần dùng `<` thay vì `≤` để giữ chỉ số cũ hơn khi còn hợp lệ. Tương tự, với cực tiểu và chỉ số xuất hiện sớm nhất, cân nhắc dùng `>` thay vì `≥`.

## 9. Chứng minh tính đúng đắn

Ta chứng minh cho **sliding maximum**; sliding minimum hoàn toàn tương tự nếu đổi chiều so sánh.

### 9.1. Bất biến về thời gian

Sau khi loại hết hạn tại bước `i`, mọi chỉ số còn lại phải **lớn hơn `i - k`**. Vì các chỉ số luôn được thêm theo thứ tự tăng, chỉ số nhỏ nhất luôn ở **đầu deque**. Do đó, chỉ cần liên tục xóa từ đầu cho tới khi đầu deque còn hợp lệ.

Bước thêm `i` đưa một chỉ số mới nằm trong cửa sổ vào cuối. Vì vậy, tại lúc xuất kết quả, mọi ứng viên đều có chỉ số thuộc đoạn `[i-k+1, i]`.

### 9.2. Bất biến về giá trị

Trước khi thêm `i`, giá trị ứng viên trong deque giảm nghiêm ngặt từ đầu tới cuối. Khi xử lý `a[i]`, ta bỏ mọi ứng viên cuối có giá trị `≤ a[i]`. Vì thế, nếu deque còn phần tử, giá trị cuối của nó **lớn hơn `a[i]`**. Thêm `i` vào cuối giữ thứ tự giảm nghiêm ngặt.

Thao tác xóa phần tử hết hạn ở đầu không phá thứ tự giảm. Theo quy nạp, bất biến đơn điệu giữ đúng sau mọi bước.

### 9.3. Vì sao bỏ ứng viên bị chi phối không làm mất cực đại?

Giả sử một chỉ số cũ `j` bị loại ở cuối khi phần tử mới `i` đến, với `j < i` và `a[j] ≤ a[i]`.

Xét bất kỳ cửa sổ hiện tại hoặc tương lai có chứa `j`. Do `i` nằm **sau `j`** và đã xuất hiện tại lúc loại ứng viên, cửa sổ đó nếu còn chứa `j` thì cũng chứa `i`, miễn cửa sổ kết thúc sau hoặc tại `i`. Vậy trong những cửa sổ còn liên quan, `a[i]` **không nhỏ hơn `a[j]`** và tồn tại ít nhất lâu bằng `j`.

Ứng viên `j` không bao giờ cần thiết để trả **giá trị cực đại**, nên xóa nó là an toàn.

Lập luận cũng áp dụng khi `a[j] == a[i]`, vì ta chỉ cần giá trị cực đại, không cần giữ chỉ số cũ nhất của một giá trị bằng nhau.

### 9.4. Vì sao phần tử ở đầu là cực đại?

Mọi chỉ số ứng viên trong deque đều hợp lệ theo cửa sổ và các giá trị giảm từ đầu tới cuối. Những phần tử bị xóa vì hết hạn không thuộc cửa sổ; những phần tử bị xóa vì bị chi phối đã có phần tử mới hơn có giá trị không nhỏ hơn thay thế. Vì vậy, không có phần tử hợp lệ nào bị bỏ mà có thể khiến cực đại thật lớn hơn cực đại của các ứng viên còn lại.

Phần tử ở đầu có giá trị lớn nhất trong deque, nên **`a[dq[0]]` là cực đại chính xác của cửa sổ**. Khi có ít nhất một phần tử đã được xử lý, deque không rỗng sau bước append; việc xuất kết quả chỉ diễn ra khi đã có đủ `k` phần tử.

## 10. Phân tích khấu hao: vì sao tổng thời gian là O(n)?

Một vòng lặp `while` có thể thực hiện nhiều `pop` ở một bước. Ví dụ một giá trị mới rất lớn có thể khiến ta xóa `k - 1` ứng viên từ cuối. Do đó, **một bước xử lý phần tử có thể tốn O(k)**. Tuy nhiên, không thể chỉ lấy thời gian tệ nhất của một bước rồi nhân với `n`, vì các lần xóa không thể lặp lại vô hạn trên cùng phần tử.

### 10.1. Đếm tổng số thao tác (aggregate analysis)

Trong cả quá trình:

1. Mỗi chỉ số `i` được `append` vào deque **đúng một lần**.
2. Một chỉ số được xóa **nhiều nhất một lần**: hoặc bị `popleft` do hết hạn, hoặc bị `pop` do phần tử mới tốt hơn.
3. Sau khi bị xóa, chỉ số đó **không bao giờ quay lại deque**.

Vì vậy, với `n` chỉ số đầu vào:

```text
Số lần append       = n
Số lần pop/popleft <= n

Tổng thao tác thêm/xóa <= 2n = O(n)
```

Mỗi lần so sánh thành công trong vòng `while` dẫn đến một lần xóa; ngoài ra mỗi vòng kiểm tra có nhiều nhất một lần thất bại trước khi dừng. Tổng số kiểm tra vẫn tuyến tính theo số phần tử. Do đó, toàn bộ thuật toán chạy trong **O(n) thời gian**, kể cả khi `k` lớn.

### 10.2. Cách nhìn bằng hàm thế năng

Đặt `Φ = |dq|`, tức số chỉ số đang ở trong deque. Thế năng ban đầu `0` và không bao giờ âm.

Xét một lần lặp trên chỉ số `i`, trong đó có tổng `p` ứng viên bị xóa (từ đầu hoặc cuối). Nếu mỗi thêm/xóa tính chi phí 1, thì:

```text
Chi phí thực do thao tác deque: c = p + 1

Độ thay đổi thế năng:
ΔΦ = Φ_sau - Φ_trước = 1 - p

Chi phí khấu hao:
ĉ = c + ΔΦ = (p + 1) + (1 - p) = 2
```

Các bước kiểm tra biên, so sánh và ghi kết quả có thêm chi phí O(1) khấu hao như giải thích ở trên. Tổng qua `n` bước vẫn O(n). Thế năng giải thích vì sao một vòng lặp có nhiều lần xóa **tiêu thụ các ứng viên đã được thêm từ những bước trước**, chứ không tạo ra chi phí lớn lặp đi lặp lại.

**O(n) là độ phức tạp của toàn bộ phép tính**, còn mỗi chỉ số được xử lý với **O(1) khấu hao**. Một vòng lặp cụ thể vẫn có thể xóa O(k) chỉ số.

### 10.3. Bộ nhớ O(k)

Tại bước `i`, sau khi loại hết hạn, tất cả chỉ số deque đều thuộc cửa sổ đang xét. Chúng được lưu theo thứ tự tăng và không trùng nhau; có tối đa `k` chỉ số.

Do đó:

- **Bộ nhớ phụ của deque:** **O(k)**.
- **Bộ nhớ của kết quả:** **O(n-k+1)** nếu lưu toàn bộ kết quả vào danh sách.
- **Tổng bộ nhớ phụ bao gồm kết quả:** O(k + n-k+1) = **O(n)** trong cách trả danh sách thông thường.

Nếu bài toán chỉ cần xử lý từng cực trị ngay khi tìm ra mà không giữ tất cả kết quả, có thể dùng kiểu luồng/generator để giảm phần lưu kết quả; bản thân deque vẫn chỉ cần O(k) bộ nhớ phụ.

## 11. So sánh với các cấu trúc và cách giải khác

| Phương án | Thời gian cho toàn bộ các cửa sổ | Bộ nhớ phụ (không tính đầu ra) | Đặc điểm |
|---|---:|---:|---|
| Quét lại từng cửa sổ | O(nk) | O(1) nếu không tạo lát cắt | Rất đơn giản nhưng có nhiều phép so sánh lặp |
| **Deque đơn điệu** | **O(n)** | **O(k)** | Cực trị trên cửa sổ trượt cố định, xử lý lần lượt |
| Heap ưu tiên có loại phần tử hết hạn kiểu lazy | Thường O(n log n) cho cách dùng heap chứa các ứng viên chưa dọn hết | Có thể O(n) do mục hết hạn chưa được loại ngay | Hữu ích trong bài toán ưu tiên khác; cần quản lý chỉ số cũ |
| Cây đa tập cân bằng (balanced search tree) | O(n log k) cho mỗi lần thêm/xóa O(log k) | O(k) | Hỗ trợ thêm/xóa tùy ý hoặc truy vấn thứ tự phong phú hơn |

Deque đơn điệu đặc biệt hiệu quả khi cửa sổ **di chuyển một chiều**, mỗi bước chỉ thêm một phần tử bên phải và bỏ phần tử quá cũ ở bên trái. Nếu bài toán yêu cầu xóa một phần tử **bất kỳ ở giữa**, hoặc truy vấn nhiều loại thứ tự thống kê như trung vị, một deque đơn điệu đơn lẻ thường không đủ.

Lưu ý rằng mô tả heap có thể khác tùy thuật toán dọn dữ liệu hết hạn; việc dùng heap không đồng nghĩa tự có O(k) bộ nhớ nếu chỉ xóa lười và không giới hạn số mục cũ tồn đọng.

## 12. Tình huống biên và các lỗi phổ biến

### Những trường hợp cần xét

| Dữ liệu | Kết quả/ghi chú |
|---|---|
| `k = 1` | Mỗi cửa sổ chỉ chứa một phần tử: cực đại và cực tiểu chính là dãy gốc |
| `k = n` | Có đúng **một** kết quả: max hoặc min của toàn dãy |
| `n = 0` | Không có cửa sổ hợp lệ với `k ≥ 1`; mã ví dụ báo `ValueError` |
| `k = 0` hoặc `k > n` | Mã ví dụ báo `ValueError` vì ngoài hợp đồng |
| Các giá trị bằng nhau | Có thể giữ chỉ số mới hơn khi dùng `≤`/`≥` |
| Giá trị âm | So sánh bình thường; không cần tách trường hợp đặc biệt |
| Dãy tăng nghiêm ngặt | Deque cực đại thường chỉ giữ phần tử mới nhất |
| Dãy giảm nghiêm ngặt | Deque cực đại có thể giữ tới `k` ứng viên trước khi chỉ số đầu hết hạn |

Với những giá trị **không có thứ tự so sánh nhất quán**, ví dụ `NaN` trong dữ liệu số thực, các bất biến dựa trên `≤` và `≥` có thể không áp dụng như mong đợi. Hãy chuẩn hóa dữ liệu hoặc quy định rõ cách xử lý giá trị thiếu trước khi dùng thuật toán.

### Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng queue FIFO thường, không có `pop` ở cuối | Không loại được ứng viên bị chi phối hiệu quả | Dùng deque hỗ trợ cả hai phía |
| Chỉ lưu giá trị mà không có thông tin thời điểm | Khó xác định phần tử nào đã hết hạn, nhất là khi bằng nhau | Lưu **chỉ số gốc** |
| Quên loại chỉ số `≤ i-k` | Trả cực trị của phần tử đã ra khỏi cửa sổ | Kiểm tra hạn ở đầu trước khi xuất kết quả |
| Dùng `dq[0] < i-k` thay vì `dq[0] <= i-k` | Giữ thừa phần tử đúng tại biên hết hạn | Cửa sổ là `[i-k+1, i]`, nên loại `≤ i-k` |
| Tìm cực đại nhưng loại khi `a[dq[-1]] >= a[i]` | Duy trì deque tăng và cho kết quả sai | Cực đại loại `≤`; cực tiểu loại `≥` |
| Xóa ứng viên bị chi phối ở **đầu** thay vì cuối | Có thể bỏ cực trị tốt nhất | Xóa bị chi phối từ **cuối**, xóa hết hạn từ **đầu** |
| Xuất kết quả trước khi có đủ `k` phần tử | Số cửa sổ/kết quả không đúng | Chỉ xuất khi `i >= k-1` |
| Dùng `list.pop(0)` làm deque | Có thể làm mỗi xóa đầu tốn O(k) | Dùng `collections.deque.popleft()` |
| Nghĩ mỗi bước đều O(1) trường hợp xấu nhất | Bỏ qua vòng lặp xóa nhiều ứng viên | Phân tích **O(1) khấu hao**, O(n) toàn chuỗi |
| Nghĩ deque chứa toàn bộ cửa sổ | Hiểu sai chức năng lọc ứng viên | Chỉ giữ những ứng viên chưa bị chi phối |
| Không thống nhất khi có giá trị bằng nhau | Trả sai chỉ số nếu bài yêu cầu chỉ số sớm nhất | Chọn rõ `<` hoặc `≤` tùy yêu cầu hòa |
| Trộn chỉ số logic với giá trị | Đọc nhầm `nums[dq[0]]` thành `dq[0]` | `dq[0]` là chỉ số; muốn giá trị phải tra `nums` |

## 13. Tự luyện với lời giải

**Bài 1 — Cực đại.** Cho `a = [4, 1, 3, 2, 5]` và `k = 2`. Hãy viết cực đại của từng cửa sổ.

*Lời giải:* Các cửa sổ là `[4,1]`, `[1,3]`, `[3,2]`, `[2,5]`. Kết quả **`[4, 3, 3, 5]`**.

**Bài 2 — Cực tiểu.** Vẫn với dãy trên, hãy viết cực tiểu của từng cửa sổ độ dài 2.

*Lời giải:* Kết quả **`[1, 1, 2, 2]`**.

**Bài 3 — Loại hết hạn.** Với `k = 4` và đang xử lý `i = 7`, những chỉ số nào chắc chắn đã ra khỏi cửa sổ?

*Lời giải:* Cửa sổ là `[4, 7]`. Mọi chỉ số `j ≤ i-k = 3` đều hết hạn. Chỉ giữ các ứng viên có chỉ số `4, 5, 6, 7`.

**Bài 4 — Loại bị chi phối.** Tìm cực đại; deque đang lưu `[1:9, 3:6, 4:2]`, phần tử mới là `a[5] = 7`, chưa có chỉ số hết hạn. Deque sau khi xử lý là gì?

*Lời giải:* Bỏ `4:2` rồi `3:6` vì chúng `≤7`; giữ `1:9` vì `9 > 7`; thêm `5:7`. Kết quả **`[1:9, 5:7]`**.

**Bài 5 — Giá trị bằng nhau.** Với `a = [5, 5, 5]` và `k = 2`, dùng điều kiện `≤` cho bài toán cực đại, deque sau khi xử lý `i=2` chứa những chỉ số nào?

*Lời giải:* Chỉ chứa **`[2]`** vì ứng viên cùng giá trị cũ bị loại khi gặp ứng viên mới hơn. Cả hai kết quả cực đại vẫn là 5.

**Bài 6 — Độ phức tạp.** Một bước thêm phần tử có thể khiến vòng `while` chạy O(k) lần. Vì sao thuật toán vẫn O(n) qua tất cả các cửa sổ?

*Lời giải:* Mỗi chỉ số được thêm một lần và xóa nhiều nhất một lần (do hết hạn hoặc bị chi phối). Có nhiều nhất `n` lần thêm và `n` lần xóa trong toàn bộ chuỗi, nên tổng công việc deque O(n).

**Bài 7 — Chỉ số cực đại sớm nhất.** Trong một cửa sổ có hai phần tử cùng cực đại, cần trả **chỉ số xuất hiện sớm nhất**. Có nên xóa ứng viên cũ khi gặp giá trị mới **bằng** nó không?

*Lời giải:* **Không**, nếu muốn giữ chỉ số sớm nhất. Với cực đại, dùng `<` thay vì `≤` khi loại từ cuối; hai ứng viên bằng nhau được giữ đến khi chỉ số cũ hết hạn.

**Bài 8 — Chọn cấu trúc.** Nếu cửa sổ trượt có độ rộng `k = 1.000` và đầu vào gồm `n = 1.000.000` giá trị, nên dùng quét lại từng cửa sổ hay deque đơn điệu?

*Lời giải:* Deque đơn điệu thường phù hợp hơn khi cần xử lý toàn dãy: O(n) thời gian và O(k) bộ nhớ phụ cho deque, so với cách quét lại có thể mất O(nk) thời gian. Kết quả vẫn cần O(n-k+1) ô nếu lưu thành danh sách.

**Ghi nhớ:** Deque đơn điệu giải cực đại/cực tiểu trên cửa sổ trượt bằng cách **lưu chỉ số**, xóa **hết hạn ở đầu** và xóa **ứng viên bị chi phối ở cuối**. Với cực đại, giữ các giá trị giảm dần và bỏ ứng viên cuối `≤` giá trị mới; với cực tiểu, giữ các giá trị tăng dần và bỏ ứng viên cuối `≥` giá trị mới. Mỗi chỉ số được thêm một lần, xóa nhiều nhất một lần, nên toàn bộ thuật toán đạt **O(n) thời gian**, deque dùng **O(k) bộ nhớ phụ**.
