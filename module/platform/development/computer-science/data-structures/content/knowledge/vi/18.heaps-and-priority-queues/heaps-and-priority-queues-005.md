# Lấy phần tử ưu tiên nhất bằng đẩy xuống

## 1. Bài toán: lấy đúng phần tử và giữ heap hợp lệ

Một hệ thống xử lý công việc đang giữ các yêu cầu theo **độ ưu tiên**. Mỗi khi bộ xử lý rảnh, nó cần lấy yêu cầu quan trọng nhất ra khỏi hàng đợi và tiếp tục phục vụ các yêu cầu còn lại.

Nếu quy ước **số nhỏ hơn nghĩa là ưu tiên cao hơn**, ta có thể dùng **min-heap**: gốc chứa khóa nhỏ nhất. Ngược lại, nếu **số lớn hơn nghĩa là ưu tiên cao hơn**, ta dùng **max-heap**: gốc chứa khóa lớn nhất.

Ví dụ min-heap:

```text
                    2
                  /   \
                 5     3
                / \   / \
               9   7 8   4

Mảng lưu theo thứ tự tầng:
Chỉ số:  0  1  2  3  4  5  6
Giá trị: 2  5  3  9  7  8  4
```

Lấy gốc `2` thì dễ: đọc `A[0]` mất `O(1)`. Nhưng **lấy đồng thời xóa gốc** (*extract-min*, *extract-max*, hay `pop` của hàng đợi ưu tiên) khó hơn: sau khi bỏ `2`, cấu trúc còn lại **phải tiếp tục là một heap hợp lệ**.

Thuật toán tiêu biểu gồm ba việc:

1. Lưu khóa tại gốc để trả về.
2. Chuyển phần tử **cuối mảng** lên chỗ gốc rồi bỏ ô cuối để giữ hình dạng cây hoàn chỉnh.
3. Đưa phần tử vừa chuyển xuống theo hướng thích hợp (*sift-down*) cho tới khi khôi phục bất biến thứ tự.

Đây là chủ đề của chương **Heap và hàng đợi ưu tiên** trong học phần **Cấu trúc dữ liệu**. Việc hiểu bất biến, phép thao tác và độ phức tạp thời gian/bộ nhớ giúp chọn đúng cấu trúc giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

### Bạn sẽ học được gì?

- Phân biệt **xem gốc** `peek` với **lấy và xóa gốc** `pop`.
- Giải thích vì sao phải lấy **nút cuối** thay thế gốc.
- Chọn đúng con để hoán đổi trong **min-heap** và **max-heap**.
- Mô phỏng chi tiết quá trình đẩy xuống, kể cả trường hợp có một con hoặc khóa bằng nhau.
- Viết thuật toán Python, nêu bất biến vòng lặp và lập luận tính đúng đắn.
- Chứng minh thời gian `O(\log n)`, phân biệt chi phí của heap với cấp phát mảng động.
- Sử dụng `heapq.heappop` và tránh nhầm với những thao tác có tên gần giống.

## 2. Hai bất biến phải duy trì sau phép lấy

Trong bài này, **binary heap** được triển khai bằng mảng theo thứ tự từng tầng của một **cây nhị phân hoàn chỉnh**.

### Bất biến hình dạng

Tất cả các tầng trước tầng cuối được lấp đầy; tầng cuối chứa những nút từ **trái sang phải**, không có khoảng trống xen kẽ.

Với mảng `A` có `n` phần tử và chỉ số bắt đầu từ `0`:

\[
parent(i)=\left\lfloor\frac{i-1}{2}\right\rfloor,\quad i>0
\]

\[
left(i)=2i+1,\qquad right(i)=2i+2.
\]

Một chỉ số con chỉ tồn tại khi `<n`. Mảng `A[0],A[1],\ldots,A[n-1]` chính là cách liệt kê các vị trí hợp lệ của cây hoàn chỉnh.

### Bất biến thứ tự

Với mọi cạnh từ cha `p` đến con `c`:

- **Min-heap:** `key(p)\le key(c)`.
- **Max-heap:** `key(p)\ge key(c)`.

Vì quan hệ ấy đúng dọc mọi đường từ gốc xuống lá, gốc chứa một phần tử có khóa nhỏ nhất (min-heap) hoặc lớn nhất (max-heap).

**Heap không yêu cầu mảng được sắp xếp hoàn toàn.** Chẳng hạn `[2,5,3,9,7,8,4]` là min-heap hợp lệ dù `5>3` và `9>7`. Ta chỉ cần bảo toàn thứ tự **giữa cha và con**, không cần so sánh mọi cặp phần tử.

## 3. Vì sao không xóa thẳng ô đầu mảng?

Giả sử heap nằm trong một mảng động. Nếu gọi phép xóa đầu thông thường, ví dụ `heap.pop(0)` với Python `list`:

```text
Trước: [2, 5, 3, 9, 7, 8, 4]

Xóa đầu và dồn trái:
        [5, 3, 9, 7, 8, 4]
```

Phép dồn này phải dịch tới `n-1` phần tử, tốn `O(n)`. Hơn nữa, mảng kết quả **không nhất thiết** thỏa heap-order: trong ví dụ, cha `5` lớn hơn con `3`.

Cũng không thể xóa riêng nút gốc khỏi sơ đồ cây rồi để vị trí gốc trống: cây mới không còn là cây hoàn chỉnh có thể biểu diễn từ chỉ số `0` đến `n-2`.

**Giải pháp của heap:** không dồn toàn bộ đuôi. Ta đưa phần tử cuối lên gốc, xóa **cuối mảng** và chỉ sửa thứ tự theo **một đường đi** trong cây.

```text
Trước:
                    2
                  /   \
                 5     3
                / \   / \
               9   7 8   4  <-- phần tử cuối

Sau khi lưu 2 và chuyển 4 lên gốc:
                    4
                  /   \
                 5     3
                / \   /
               9   7 8
```

Bỏ nút cuối làm tầng cuối ngắn đi đúng một vị trí ở **bên phải**, nên bất biến **hình dạng** vẫn đúng. Tuy nhiên, `4` ở gốc lớn hơn con `3`, nên bất biến **thứ tự** có thể sai. Đó là việc `sift-down` phải sửa.

Nếu heap chỉ có **một** phần tử, lấy phần tử cuối cũng chính là lấy gốc; mảng trở thành rỗng, không còn gì để đẩy xuống.

## 4. Quy trình extract-min từng bước

Với một min-heap không rỗng `A`:

1. Gán `answer = A[0]`.
2. Lấy phần tử cuối bằng `last = A.pop()`. Lúc này độ dài giảm một.
3. Nếu mảng đã rỗng, trả `answer` ngay.
4. Nếu còn phần tử, ghi `A[0] = last`.
5. Từ gốc, lặp: tìm **con có khóa nhỏ hơn**; nếu cha đang lớn hơn con đó, hoán đổi và chuyển xuống vị trí con. Nếu không, dừng.
6. Trả `answer`.

Mã giả:

```text
EXTRACT_MIN(A):
    require length(A) > 0

    answer = A[0]
    last = REMOVE_LAST(A)

    if length(A) == 0:
        return answer

    A[0] = last
    i = 0

    while 2*i + 1 < length(A):
        left  = 2*i + 1
        right = 2*i + 2
        best  = left

        if right < length(A) AND A[right] < A[left]:
            best = right

        if A[i] <= A[best]:
            break

        SWAP(A[i], A[best])
        i = best

    return answer
```

**Chú ý thứ tự thao tác:** `REMOVE_LAST(A)` được gọi **sau khi đã lưu `A[0]`**, và kết quả `answer` không thay đổi dù các phần tử khác được hoán đổi.

Nếu phần tử gốc ban đầu trùng khóa với một phần tử khác, ta vẫn trả đúng **một phần tử gốc đã chọn**, không phải tự động xóa tất cả phần tử có cùng khóa.

## 5. Mô phỏng min-heap: một lần đẩy xuống nhiều tầng

Xét heap sau:

```text
                       1
                    /     \
                   4       2
                  / \     / \
                 7   5   3   6
                / \ /
              10  8 9

Mảng A:
Chỉ số:   0  1  2  3  4  5  6   7  8  9
Giá trị: [1, 4, 2, 7, 5, 3, 6, 10, 8, 9]
```

Mọi cha không lớn hơn con, và mảng có `n=10` phần tử.

### Bước 1 — lưu gốc và bỏ phần tử cuối

Lưu `answer = 1`. Lấy `last = 9` từ cuối mảng rồi đặt lên gốc:

```text
[9, 4, 2, 7, 5, 3, 6, 10, 8]
 ^
 i=0
```

Hình dạng cây còn `9` nút và vẫn hoàn chỉnh. Bất biến có thể vi phạm tại gốc: `9>4` và `9>2`.

### Bước 2 — chọn con nhỏ nhất của gốc

Ở `i=0`, con trái là `A[1]=4`, con phải là `A[2]=2`. Ta chọn **con phải** có khóa `2` vì `2<4`.

Hoán đổi `9` và `2`:

```text
[2, 4, 9, 7, 5, 3, 6, 10, 8]
       ^
       i=2: phần tử 9 cần được xét tiếp
```

Ở gốc, `2\le4` và `2\le9` nên quan hệ với hai con đã hợp lệ. Ta chưa được dừng: `9` giờ nằm ở chỉ số `2`, có thể lớn hơn các con của nó.

### Bước 3 — tiếp tục ở chỉ số 2

Con trái của `i=2` là `2\cdot2+1=5` với khóa `3`; con phải là `6` với khóa `6`. Chọn `3` rồi hoán đổi:

```text
[2, 4, 3, 7, 5, 9, 6, 10, 8]
                ^
                i=5
```

Nút ở chỉ số `5` là lá, nên dừng.

**Trạng thái cuối:**

```text
Giá trị trả về: 1
Heap còn lại:   [2, 4, 3, 7, 5, 9, 6, 10, 8]
Số hoán đổi:   2
```

Kiểm tra lại: `2\le4,3`; `4\le7,5`; `3\le9,6`; `7\le10,8`. Tất cả các cạnh còn lại đều thỏa điều kiện min-heap.

### Bảng theo dõi trạng thái

| Giai đoạn | Mảng | Chỉ số của phần tử đang đẩy |
|---|---|---:|
| Ban đầu | `[1,4,2,7,5,3,6,10,8,9]` | Gốc `0` sẽ bị lấy |
| Đưa phần tử cuối lên | `[9,4,2,7,5,3,6,10,8]` | `0` |
| Hoán đổi với `2` | `[2,4,9,7,5,3,6,10,8]` | `2` |
| Hoán đổi với `3` | `[2,4,3,7,5,9,6,10,8]` | `5` |
| Kết thúc | `[2,4,3,7,5,9,6,10,8]` | `5` là lá |

## 6. Quy tắc chọn con: chi tiết quyết định tính đúng

Khi đẩy xuống trong min-heap, ta **không thể chọn tùy ý một con nhỏ hơn cha**. Phải chọn con có **khóa nhỏ nhất** trong số các con hiện có.

Ví dụ tại một vị trí:

```text
                 8
               /   \
              3     5
```

Nếu đổi `8` với `5`:

```text
                 5
               /   \
              3     8
```

Cha mới `5` vẫn lớn hơn con `3`. Bất biến min-heap chưa được sửa tại vị trí cha. Nếu đổi với con nhỏ nhất `3`:

```text
                 3
               /   \
              8     5
```

Cha mới `3` không lớn hơn bất kỳ con nào; phần tử `8` cần được kiểm tra tiếp **ở nhánh vừa đi xuống**.

Do đó, một vòng lặp min-heap phải:

1. Xác định những con **thật sự tồn tại**.
2. Chọn con có khóa **nhỏ nhất**.
3. Nếu `A[i]\le A[best]`, **dừng** vì cha đã không lớn hơn cả hai con.
4. Nếu `A[i]>A[best]`, **hoán đổi** rồi tiếp tục tại vị trí `best`.

Nếu chỉ có **con trái**, ta dùng con trái, không đọc con phải. Trong cây nhị phân hoàn chỉnh biểu diễn theo mảng, một nút có đúng một con thì con đó phải là **con trái**.

### Khi hai con bằng nhau

Nếu hai con có cùng khóa, chọn **trái hoặc phải** đều có thể duy trì bất biến, miễn cách chọn nhất quán. Ví dụ mã của bài dùng điều kiện `right < left` (so sánh khóa) để chọn con phải, nên khi **bằng nhau**, ta giữ con trái.

Điều này **không** làm heap trở thành hàng đợi ưu tiên ổn định theo thời gian đến; tính ổn định cần một khóa phụ nếu ứng dụng yêu cầu.

## 7. Đẩy xuống của max-heap: đảo chiều mọi phép so sánh

Với max-heap, gốc có khóa **lớn nhất** và quan hệ cha–con là `parent\ge child`. Khi chuyển phần tử cuối lên gốc, phần tử ấy có thể **nhỏ hơn** một con, nên phải đổi với **con lớn nhất**.

Ví dụ:

```text
Ban đầu: [90, 70, 80, 30, 60, 50, 40]
          ^
          pop trả 90

Đưa 40 cuối lên gốc:
         [40, 70, 80, 30, 60, 50]

Chọn con lớn hơn là 80, hoán đổi:
         [80, 70, 40, 30, 60, 50]

Ở vị trí 2, con trái là 50; đổi 40 với 50:
         [80, 70, 50, 30, 60, 40]

Trả về: 90
```

Vì `80\ge70,50`; `70\ge30,60`; `50\ge40`, max-heap đã được khôi phục.

| Quyết định trong vòng lặp | Min-heap | Max-heap |
|---|---|---|
| Chọn con để so sánh | Con có **khóa nhỏ nhất** | Con có **khóa lớn nhất** |
| Điều kiện dừng | `parent\le best_child` | `parent\ge best_child` |
| Điều kiện hoán đổi | `parent>best_child` | `parent<best_child` |
| Giá trị trả về khi lấy gốc | Một khóa **nhỏ nhất** | Một khóa **lớn nhất** |

**Không chỉ đảo một phép so sánh.** Nếu chọn con nhỏ hơn nhưng dùng điều kiện dừng của max-heap, thuật toán có thể để lại bất biến bị vi phạm.

## 8. Mã Python thuần: lấy gốc min-heap

Triển khai sau dùng một `list[int]` đã là **min-heap hợp lệ**. Hàm `sift_down_min` chỉ cần xem các con của vị trí hiện tại; nó không sắp lại toàn bộ mảng.

```python
def sift_down_min(heap: list[int], start: int = 0) -> None:
    """Khôi phục min-heap bằng cách đẩy phần tử ở start xuống.

    Tiền điều kiện: các cây con của start đã là min-heap.
    """
    n = len(heap)
    if not 0 <= start < n:
        raise IndexError("Chỉ số bắt đầu không hợp lệ")

    i = start
    while True:
        left = 2 * i + 1
        if left >= n:
            break  # Không có con.

        right = left + 1
        smaller = left
        if right < n and heap[right] < heap[left]:
            smaller = right

        if heap[i] <= heap[smaller]:
            break

        heap[i], heap[smaller] = heap[smaller], heap[i]
        i = smaller


def extract_min(heap: list[int]) -> int:
    """Lấy và xóa khóa nhỏ nhất, sửa trực tiếp mảng heap."""
    if not heap:
        raise IndexError("Không thể lấy từ heap rỗng")

    answer = heap[0]   # Lưu gốc để trả về.
    last = heap.pop()  # Xóa cuối, không dịch các phần tử còn lại.

    if heap:
        heap[0] = last
        sift_down_min(heap)

    return answer


heap = [1, 4, 2, 7, 5, 3, 6, 10, 8, 9]
value = extract_min(heap)

print(value)  # 1
print(heap)   # [2, 4, 3, 7, 5, 9, 6, 10, 8]
```

Điểm cần chú ý:

- `heap.pop()` **không có chỉ số** sẽ xóa phần tử **cuối** của `list` Python, thường `O(1)` khấu hao.
- Chỉ ghi `heap[0]` khi vẫn còn phần tử. Với heap có một phần tử, `pop()` đã làm mảng rỗng.
- Hàm sửa **trực tiếp** mảng được truyền vào. Các biến khác đang tham chiếu cùng `list` có thể quan sát kết quả.
- Hàm giả định **toàn bộ mảng đầu vào đã là min-heap**. Nếu đưa mảng ngẫu nhiên chưa heapify vào, thuật toán không có bảo đảm tạo ra heap hợp lệ.
- Phép so sánh `<=` và `<` giả định các khóa có thứ tự nhất quán. Với khóa phức tạp, cần một chính sách so sánh rõ ràng.

### Kiểm tra kết quả bằng bất biến

```python
def is_min_heap(data: list[int]) -> bool:
    return all(
        data[(i - 1) // 2] <= data[i]
        for i in range(1, len(data))
    )


assert is_min_heap(heap)
assert len(heap) == 9
assert heap[0] == 2
```

Đoạn `is_min_heap` kiểm tra mỗi nút (trừ gốc) so với cha của nó. Hàm kiểm tra tốn `O(n)` thời gian, `O(1)` bộ nhớ phụ theo quy ước lặp; **đây là kiểm thử**, không phải phần cần thực hiện sau mỗi lần `pop` trong triển khai hiệu năng cao.

## 9. Mã Python thuần: lấy gốc max-heap

Với max-heap, ta giữ nguyên cấu trúc vòng lặp, nhưng chọn con **lớn hơn** và dừng khi cha đã `\ge` con tốt nhất.

```python
def sift_down_max(heap: list[int], start: int = 0) -> None:
    n = len(heap)
    if not 0 <= start < n:
        raise IndexError("Chỉ số bắt đầu không hợp lệ")

    i = start
    while True:
        left = 2 * i + 1
        if left >= n:
            break

        right = left + 1
        larger = left
        if right < n and heap[right] > heap[left]:
            larger = right

        if heap[i] >= heap[larger]:
            break

        heap[i], heap[larger] = heap[larger], heap[i]
        i = larger


def extract_max(heap: list[int]) -> int:
    if not heap:
        raise IndexError("Không thể lấy từ heap rỗng")

    answer = heap[0]
    last = heap.pop()
    if heap:
        heap[0] = last
        sift_down_max(heap)
    return answer


max_heap = [90, 70, 80, 30, 60, 50, 40]
print(extract_max(max_heap))  # 90
print(max_heap)              # [80, 70, 50, 30, 60, 40]
```

Nếu dùng kiểu số thực có giá trị `NaN` hoặc đối tượng có phép so sánh không nhất quán, lập luận chọn con lớn nhất/nhỏ nhất có thể không còn đúng. Nên chuẩn hóa khóa và quy ước thứ tự trước khi lưu vào heap.

## 10. Vì sao thuật toán đúng? Bất biến vòng lặp sift-down

Ta xét **min-heap**, trường hợp max-heap tương tự khi đảo chiều so sánh.

### Bước khởi đầu: chỉ có thể sai ở gốc

Trước khi lấy, mọi cạnh của heap đều thỏa quan hệ `cha\le con`.

Khi bỏ nút cuối và đưa khóa của nó lên gốc:

- Tất cả các nút còn lại vẫn chiếm những chỉ số `0,\ldots,n-2`, nên cây vẫn hoàn chỉnh.
- Các cây con bên dưới gốc không đổi quan hệ nội bộ; chúng vẫn là min-heap.
- Chỉ những cạnh **xuất phát từ gốc mới** có thể vi phạm bất biến, vì khóa đặt tại gốc đã thay đổi.

### Bất biến trong mỗi vòng lặp

Tại đầu một vòng đẩy xuống ở vị trí `i`:

1. Hai cây con của `i` (nếu tồn tại) đều thỏa min-heap.
2. Những cạnh **không nối trực tiếp vị trí `i` với một con của nó** đều đã thỏa bất biến trong cấu trúc đang xét.
3. Phần tử cần sửa hiện đang ở vị trí `i`; chỉ quan hệ giữa nó với con có thể sai.

Khi chọn `best` là con nhỏ nhất:

- Nếu `A[i]\le A[best]` thì `A[i]` không lớn hơn **bất kỳ con nào**. Do các cây con đã hợp lệ, toàn bộ heap hợp lệ và có thể dừng.
- Nếu `A[i]>A[best]`, hoán đổi hai giá trị. Khóa mới ở vị trí `i` là nhỏ nhất trong hai con cũ, nên không lớn hơn con còn lại; khóa lớn hơn được chuyển xuống vị trí `best`. Mọi vị trí khác không đổi, nên điểm **có thể** còn vi phạm đã dịch xuống một tầng.

Vì chọn đúng con ưu tiên nhất, ta không để lại vi phạm ở vị trí vừa đi qua.

### Bước kết thúc

Mỗi lần hoán đổi làm vị trí `i` **xuống sâu một tầng**, không thể đi mãi trên cây hữu hạn. Thuật toán dừng khi:

- Đến **lá** (không có con), hoặc
- Quan hệ `A[i]\le A[best]` đã đúng.

Lúc đó không còn cạnh nào vi phạm bất biến, nên mảng còn lại là min-heap hợp lệ.

Giá trị `answer` được lưu từ gốc cũ trước khi thay thế, vì thế vẫn là **một giá trị nhỏ nhất của heap ban đầu**. Nếu có nhiều phần tử cùng khóa nhỏ nhất, thuật toán chỉ lấy **một phần tử**, không cam kết đó là phần tử được thêm sớm nhất.

## 11. Độ phức tạp thời gian và bộ nhớ

Giả sử heap có `n` phần tử **trước khi lấy**; phép so sánh và trao đổi hai khóa kích thước cố định có chi phí `O(1)`.

### Chi phí của một lần sift-down

Ở mỗi tầng, thuật toán:

1. Tính tối đa hai chỉ số con.
2. So sánh tối đa hai khóa để chọn con ưu tiên hơn.
3. So sánh cha với con đã chọn.
4. Hoán đổi nhiều nhất một lần rồi xuống một tầng.

Vì binary heap là cây nhị phân hoàn chỉnh có chiều cao:

\[
h=\lfloor\log_2 n\rfloor \quad(n\ge1),
\]

phần tử thay thế chỉ đi xuống tối đa `h` tầng. Do đó:

\[
\boxed{T_{\mathrm{sift\text{-}down}}(n)=O(\log n)}
\]

cho trường hợp xấu nhất khi `n\ge2`. Ở heap nhỏ hoặc khi khóa chuyển lên đã không lớn hơn các con, thuật toán có thể dừng ngay, với **`O(1)` bước**.

### Chi phí lấy gốc

| Thành phần | Thời gian điển hình |
|---|---|
| Kiểm tra heap rỗng, lưu `A[0]` | `O(1)` |
| Lấy phần tử cuối của mảng động | `O(1)` khấu hao |
| Ghi khóa cuối lên `A[0]` nếu mảng còn phần tử | `O(1)` |
| `sift-down` theo một đường từ gốc tới lá | `O(\log n)` xấu nhất |
| Tổng thao tác theo mô hình heap thông dụng | **`O(\log n)`** |

Một số thư viện mảng động có thể cấp phát lại hoặc co vùng chứa ở một lần giảm kích thước. Khi cần phân tích trường hợp xấu nhất cực kỳ chặt theo **một triển khai cụ thể**, phải tính cả chính sách quản lý bộ nhớ. Kết luận `O(\log n)` ở đây là độ phức tạp của phép **duy trì binary heap**, với giả định thông dụng về thao tác xóa cuối của vùng lưu.

### Bộ nhớ phụ

Thuật toán dạng lặp chỉ cần vài biến `answer`, `last`, `i`, `left`, `right`, `best`, nên sử dụng:

\[
\boxed{O(1)\ \text{bộ nhớ phụ}}
\]

ngoài vùng mảng heap `O(n)` đã tồn tại. Phiên bản `sift-down` viết bằng **đệ quy** có thể dùng `O(\log n)` bộ nhớ ngăn xếp lời gọi.

Nếu một lần so sánh khóa tốn `T_{\mathrm{cmp}}` thay vì `O(1)`, phần sửa heap cần xét thêm chi phí ấy; ví dụ chuỗi dài có thể không so sánh trong thời gian hằng số.

### Lấy liên tiếp k phần tử

Lấy `k` phần tử ưu tiên nhất từ heap có `n` phần tử, với `0\le k\le n`, cần tối đa:

\[
O(k\log(n+1))
\]

thời gian để đẩy xuống, vì mỗi lần lấy làm kích thước giảm. Nếu lấy sạch `n` phần tử, tổng thời gian là **`O(n\log n)`**, và các giá trị được lấy lần lượt theo thứ tự ưu tiên. Đó là cơ sở liên quan đến sắp xếp bằng heap (*heapsort*).

## 12. Những trường hợp biên phải xử lý trước

### Heap rỗng

```text
A = []
```

Không tồn tại `A[0]` hay nút cuối. Phải **từ chối phép lấy**, ví dụ ném `IndexError` trong Python hoặc trả trạng thái không thành công theo giao diện thiết kế.

### Heap có một phần tử

```text
A = [42]
```

Lưu `answer=42`, lấy phần tử cuối, mảng thành `[]`, trả `42`. Không đặt lại `A[0]` và không gọi `sift-down`.

### Heap có hai phần tử

```text
Min-heap ban đầu: [2, 5]
Lấy gốc 2; đưa phần tử cuối 5 lên.
Heap còn lại:    [5]
```

Nút mới là lá, nên không có con để so sánh.

### Nút chỉ có con trái

Ví dụ sau khi thay gốc, ở vị trí `i` có chỉ số con trái hợp lệ nhưng chỉ số con phải đã bằng `n`. Khi đó **chỉ so với con trái**. Mọi phép đọc `A[right]` phải kiểm tra `right<n` trước.

### Khóa bằng nhau

```text
Min-heap: [2, 2, 3, 2, 5]
```

Các quan hệ `cha\le con` vẫn đúng. Khi so sánh bằng nhau, thuật toán có thể dừng mà không cần hoán đổi. Không nên dùng điều kiện `cha<con` để bắt buộc đổi các khóa bằng nhau, vì có thể gây những hoán đổi không cần thiết.

### Toán học chỉ số và giới hạn kiểu số

Trong các ngôn ngữ với kiểu số nguyên cố định, phép tính `2i+1`, `2i+2` có thể tràn nếu `i` quá lớn. Phải chọn kiểu số phù hợp hoặc kiểm tra trước khi nhân/cộng. Python hỗ trợ số nguyên có độ chính xác tùy ý, nhưng vẫn cần kiểm tra chỉ số hợp lệ.

## 13. Lấy một phần tử không giống lấy phần tử nhỏ thứ hai

Một hiểu lầm thường gặp: “Nếu gốc là nhỏ nhất, thì phần tử nhỏ thứ hai chắc ở chỉ số `1`”.

Thực tế, trong min-heap, phần tử nhỏ thứ hai (nếu có ít nhất hai phần tử) là **một trong hai con của gốc**, chứ không nhất thiết là con trái.

Ví dụ:

```text
Heap: [2, 5, 3, 9, 7, 8, 4]
Gốc nhỏ nhất: 2
Hai con: 5 và 3
Nhỏ thứ hai: 3, nằm ở chỉ số 2
```

Sau khi `extract_min` trả `2`, min-heap được khôi phục và **gốc mới** là `3`. Vì thế, để lấy lần lượt những giá trị ưu tiên nhất, ta lặp lại `extract_min`, thay vì giả định các chỉ số `1,2,3,...` của mảng ban đầu đã là thứ tự tăng.

Tìm giá trị bất kỳ trong heap vẫn có thể phải duyệt `O(n)`; ưu thế của heap là **lấy cực trị**, không phải tìm theo khóa tùy ý hay truy cập phần tử có hạng `k` theo một công thức chỉ số đơn giản.

## 14. Thực hành với thư viện chuẩn heapq

Python có module chuẩn `heapq` duy trì **min-heap** trên một `list`. Muốn đưa danh sách bất kỳ về dạng heap, ta dùng `heapq.heapify` trước khi lấy:

```python
import heapq

priorities = [7, 2, 9, 4, 1]
heapq.heapify(priorities)       # O(n), sửa trực tiếp list.

print(priorities[0])           # 1: chỉ xem gốc.

first = heapq.heappop(priorities)
print(first)                   # 1: lấy và xóa min.
print(priorities[0])           # 2: gốc mới.

while priorities:
    print(heapq.heappop(priorities))
# In các giá trị còn lại theo thứ tự tăng: 2, 4, 7, 9.
```

Với `heapq`, ta **không cần tự gọi** `sift-down`: `heappop` đã xử lý việc duy trì bất biến. Muốn hiểu tại sao phép lấy có `O(\log n)` thời gian, hãy liên hệ với quá trình thay gốc và đẩy xuống đã mô phỏng.

### Phân biệt heappop, heapreplace và heappushpop

Ba tên hàm này khá giống nhau nhưng có ý nghĩa khác nhau:

| Hàm | Chức năng | Kích thước heap |
|---|---|---|
| `heapq.heappop(h)` | Lấy và xóa min hiện tại | Giảm một |
| `heapq.heapreplace(h, x)` | Lấy min cũ, **thay** bằng `x` và khôi phục heap | Giữ nguyên, yêu cầu heap không rỗng |
| `heapq.heappushpop(h, x)` | Thêm `x` rồi lấy min của tập mới, tối ưu trong một thao tác | Giữ nguyên nếu heap ban đầu không rỗng |

Ví dụ minh họa khác biệt quan trọng khi `x` nhỏ hơn gốc cũ:

```python
import heapq

h = [2, 5, 3]  # Min-heap hợp lệ.
print(heapq.heapreplace(h, 1))  # 2: lấy min CŨ.
print(h)                        # [1, 5, 3]

h = [2, 5, 3]
print(heapq.heappushpop(h, 1))  # 1: lấy min SAU KHI thêm.
print(h)                        # [2, 5, 3], không đổi.
```

`heapreplace` trên heap rỗng báo lỗi; `heappushpop` trên heap rỗng có thể trả chính `x` mà không giữ phần tử nào. Đây là **những thao tác khác yêu cầu “lấy gốc và giảm kích thước”**, không được đánh đồng.

### Max-heap và khóa ưu tiên

Với các khóa số mà phép đổi dấu hợp lệ, có thể lưu `-priority` trong min-heap để lấy **priority lớn nhất** trước:

```python
import heapq

max_like = [-value for value in [4, 9, 2, 7]]
heapq.heapify(max_like)

print(-heapq.heappop(max_like))  # 9
print(-heapq.heappop(max_like))  # 7
```

Đó là kỹ thuật **đổi khóa** cho dữ liệu số, không có nghĩa mọi loại đối tượng đều hỗ trợ phép đổi dấu. Ở ngôn ngữ dùng số nguyên giới hạn, đảo dấu giá trị nhỏ nhất còn có thể tràn.

## 15. Khi nhiều công việc có cùng mức ưu tiên

Heap cơ bản **không bảo đảm** những phần tử có cùng khóa được lấy theo thứ tự chèn. Sau nhiều phép hoán đổi, các công việc cùng priority có thể đổi thứ tự tương đối.

Nếu quy tắc nghiệp vụ yêu cầu:

1. Priority nhỏ hơn được xử lý trước.
2. Khi priority bằng nhau, công việc đến **sớm hơn** được xử lý trước.

hãy dùng **khóa ghép** `(priority, sequence)`, trong đó `sequence` tăng dần mỗi lần thêm.

```python
import heapq
from itertools import count

counter = count()
queue: list[tuple[int, int, str]] = []

heapq.heappush(queue, (2, next(counter), "A"))
heapq.heappush(queue, (1, next(counter), "B"))
heapq.heappush(queue, (2, next(counter), "C"))

print(heapq.heappop(queue)[2])  # B
print(heapq.heappop(queue)[2])  # A
print(heapq.heappop(queue)[2])  # C
```

Mỗi lần `heappop` vẫn lấy **khóa nhỏ nhất theo thứ tự từ điển của tuple**. Khi bằng `priority`, `sequence` quyết định. Đây là cách bổ sung tính ổn định ở **mức khóa**, chứ không phải thuộc tính có sẵn của binary heap.

Nếu chỉ cần lấy phần tử ưu tiên nhất, vẫn không cần sắp toàn bộ hàng đợi: các phần tử khác chỉ cần tuân theo bất biến heap-order với khóa ghép.

## 16. Ứng dụng: hàng đợi xử lý yêu cầu và đỉnh đồ thị

### 16.1. Hàng đợi theo thời điểm đến hạn

Một bộ lập lịch có các công việc gắn với `deadline`. Nếu thời điểm nhỏ hơn nghĩa là phải xử lý sớm hơn, `deadline` có thể làm khóa của min-heap.

```text
Jobs: [(deadline=15, A), (deadline=8, B), (deadline=20, C)]

Gốc ưu tiên:  B (deadline=8)
Lấy B:       đưa phần tử cuối lên, đẩy xuống nếu cần.
Gốc kế tiếp: A (deadline=15)
```

Trong hệ thống thực, thời gian hiện tại, tài nguyên và trạng thái hủy công việc còn cần được xử lý; heap chỉ tổ chức **thứ tự ưu tiên**, không tự quyết định khi nào công việc sẵn sàng thực thi.

### 16.2. Dijkstra với min-priority queue

Trong thuật toán Dijkstra cho đồ thị có trọng số cạnh **không âm**, hàng đợi ưu tiên thường lưu các cặp `(distance, vertex)`. Mỗi bước lấy cặp có **khoảng cách tạm thời nhỏ nhất** bằng phép `pop` của min-heap.

Một cách phổ biến là thêm bản ghi mới khi tìm được khoảng cách tốt hơn và **bỏ qua bản ghi lỗi thời** lúc lấy ra:

```python
import heapq

# Minh họa ý tưởng "bỏ bản ghi lỗi thời", không phải Dijkstra đầy đủ.
best = {"A": 2, "B": 5}
pending = [(7, "A"), (2, "A"), (5, "B")]
heapq.heapify(pending)

while pending:
    distance, vertex = heapq.heappop(pending)
    if distance != best[vertex]:
        continue  # Bản ghi cũ không còn là khoảng cách tốt nhất.
    print(vertex, distance)
# A 2
# B 5
```

Ví dụ cho thấy `heappop` luôn trả phần tử ưu tiên nhất **trong các bản ghi đang còn ở heap**, nhưng ứng dụng có thể có tiêu chuẩn nghiệp vụ để loại bản ghi lỗi thời sau khi lấy. Nếu cần xóa/cập nhật một mục theo `id` nhanh, một cấu trúc heap hỗ trợ chỉ mục `id → vị trí` phải cập nhật ánh xạ sau mọi lần hoán đổi.

## 17. Bảng phân biệt thao tác trên heap với thao tác trên mảng

| Bài toán | Cách làm | Thời gian khi dữ liệu đã sẵn sàng |
|---|---|---|
| Chỉ xem ưu tiên nhất của heap không rỗng | Đọc `A[0]` | `O(1)` |
| Lấy và **xóa** ưu tiên nhất | Lấy gốc, thay bằng cuối, `sift-down` | `O(\log n)` |
| Lấy phần tử ở cuối mảng động | `A.pop()` | `O(1)` khấu hao |
| Xóa phần tử đầu của mảng động | `A.pop(0)` | `O(n)` do dịch đuôi |
| Lấy min của mảng chưa sắp | Quét để tìm min | `O(n)` |
| Tìm một khóa bất kỳ trong heap | Duyệt / chỉ mục phụ | `O(n)` nếu không có chỉ mục |
| Tạo min-heap từ mảng bất kỳ | `heapify` từ dưới lên | `O(n)` |
| Lấy toàn bộ `n` phần tử theo thứ tự | Lặp lại `pop` | `O(n\log n)` |
| Đổi khóa ở vị trí heap đã biết | `sift-up` hoặc `sift-down` | `O(\log n)` |

Lưu ý trường hợp `n=0` phải được xử lý riêng đối với `peek` và `pop`. Cận `O(\log n)` thường viết cho kích thước đủ lớn; trong thuật toán cụ thể, mọi trường hợp rỗng hoặc chỉ có một phần tử đều được xử lý bằng một số bước hằng số.

## 18. Những lỗi dễ gặp khi cài phép lấy ưu tiên nhất

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi `A[0]` khi mảng rỗng | Truy cập vượt biên | Kiểm tra rỗng trước khi lưu gốc |
| Lấy phần tử cuối rồi vẫn ghi `A[0]` khi heap có một phần tử | Mảng đã rỗng | Chỉ đặt lại gốc khi mảng còn phần tử |
| Dùng `pop(0)` để xóa gốc | Dịch `O(n)` ô và có thể phá heap-order | Dùng `pop()` cuối, thay gốc, `sift-down` |
| Xóa gốc khỏi cây nhưng để lỗ trống | Phá hình dạng cây hoàn chỉnh | Bù bằng nút cuối |
| Chọn một con bất kỳ nhỏ hơn cha trong min-heap | Sau đổi, cha mới vẫn có thể lớn hơn con còn lại | Chọn con **nhỏ nhất** |
| Đọc `A[right]` mà không kiểm tra `right<n` | Vượt biên ở nút chỉ có con trái | Kiểm tra con tồn tại trước |
| Dừng sau hoán đổi ở gốc | Vi phạm có thể chuyển xuống tầng sâu hơn | Lặp đến lá hoặc đến khi cha hợp lệ |
| Dùng dấu so sánh min-heap cho max-heap | Lấy sai thứ tự ưu tiên | Đảo cả cách chọn con và điều kiện dừng |
| Không lưu gốc trước khi thay | Mất phần tử cần trả | `answer=A[0]` trước khi sửa mảng |
| Coi kết quả của `sift-down` là mảng sắp hoàn toàn | Heap chỉ thỏa cha–con | Đừng giả định `A[1]` là khóa nhỏ thứ hai |
| Dùng `extract_min` trên mảng chưa có bất biến heap | Không có bảo đảm kết quả đúng | `heapify` trước hoặc xây heap bằng push |
| Giữ chỉ số của một công việc sau các lần hoán đổi | Chỉ số có thể đã thay đổi | Bảo trì bảng `id→index` nếu cần |
| Cho rằng hai công việc cùng khóa luôn theo FIFO | Heap không ổn định mặc định | Dùng khóa phụ `sequence` |
| Dùng `heapreplace` như thể nó giảm kích thước heap | Kích thước không đổi | Dùng `heappop` nếu cần xóa |
| Dùng `heappushpop` như thể luôn trả gốc cũ | Phần tử mới có thể bị lấy ngay | Phân biệt thứ tự thêm/lấy |
| Tính `2i+1` với kiểu số giới hạn mà không kiểm soát tràn | Có thể tạo chỉ số sai | Dùng kiểu phù hợp và kiểm tra giới hạn |

## 19. Bài tập tự kiểm tra

**Bài 1.** Cho min-heap `H=[2,5,3,9,7,8,4]`. Hãy mô phỏng một lần lấy gốc: giá trị trả về là gì, phần tử nào thay vào gốc và mảng cuối là gì?

**Bài 2.** Với `H=[1,4,2,7,5,3,6,10,8,9]`, hãy liệt kê các chỉ số mà phần tử `9` đi qua trong quá trình đẩy xuống sau khi lấy `1`. Có bao nhiêu lần hoán đổi?

**Bài 3.** Xét max-heap `[90,70,80,30,60,50,40]`. Sau một lần `extract_max`, giá trị trả về và heap còn lại là gì?

**Bài 4.** Vì sao không thể đổi cha `8` với con `5` trước khi xét con `3` trong đoạn cây có cha `8`, hai con `3` và `5`?

**Bài 5.** Một nút ở chỉ số `i=4` trong mảng heap `n=10` có những con nào? Nếu `n=9` thì sao?

**Bài 6.** Viết kết quả `extract_min` khi heap là `[]`, `[42]` và `[2,5]`. Trường hợp nào cần gọi `sift-down`?

**Bài 7.** Sau khi đưa phần tử cuối lên gốc, bất biến **hình dạng** của binary heap có còn đúng không? Vì sao bất biến **thứ tự** vẫn có thể bị phá?

**Bài 8.** Chứng minh ngắn gọn vì sao chọn con **nhỏ nhất** của min-heap khiến quan hệ cha với các con ở vị trí vừa xử lý trở nên hợp lệ sau khi hoán đổi.

**Bài 9.** Với heap có `n=31` phần tử, chiều cao tối đa là bao nhiêu cạnh? Một lần `sift-down` có thể thực hiện tối đa bao nhiêu lần hoán đổi theo chiều cao đó?

**Bài 10.** Vì sao `heapq.heappop(h)` và `h.pop(0)` không tương đương cả về độ phức tạp lẫn việc duy trì heap?

**Bài 11.** Với `h=[2,5,3]` và `x=1`, `heapq.heapreplace(h,x)` khác `heapq.heappushpop(h,x)` ra sao về giá trị trả về và mảng còn lại?

**Bài 12.** Một hàng đợi min-heap chứa các công việc `(priority, sequence, name)`: `(2,0,A)`, `(1,1,B)`, `(2,2,C)`. Nếu liên tiếp lấy ba phần tử, thứ tự tên là gì? Vai trò của `sequence` là gì?

**Bài 13.** Khi lấy hết `n` phần tử từ một heap bằng `n` lần `heappop`, tổng thời gian là bao nhiêu? Tại sao điều này không có nghĩa một lần pop là `O(n\log n)`?

**Bài 14.** Một ứng dụng đã biết `id` công việc nhưng không biết chỉ số hiện tại của nó trong heap. Có thể dùng bất biến min-heap để tìm vị trí theo `id` trong `O(\log n)` không? Nên bổ sung cấu trúc nào để cập nhật theo `id` hiệu quả?

**Bài 15.** Nếu trong min-heap phần tử đưa lên gốc đã nhỏ hơn hoặc bằng cả hai con, điều gì xảy ra với `sift-down`? Thời gian trong trường hợp này?

### Đáp án và giải thích

1. Trả `2`. Lấy `4` cuối thay gốc: `[4,5,3,9,7,8]`. Đổi `4` với con nhỏ nhất `3`, kết quả `[3,5,4,9,7,8]`.
2. Phần tử `9` bắt đầu ở gốc `i=0`, chuyển xuống `i=2` rồi `i=5`; **hai** lần hoán đổi. Heap cuối là `[2,4,3,7,5,9,6,10,8]`.
3. Trả `90`. Đưa `40` lên, đổi với `80` rồi `50`; kết quả `[80,70,50,30,60,40]`.
4. Đổi với `5` sẽ để cha mới `5` lớn hơn con `3`, chưa sửa được quan hệ tại vị trí cha. Phải đổi với con nhỏ nhất `3`.
5. Với `n=10`, con trái `2\cdot4+1=9` hợp lệ, con phải `10` không hợp lệ. Với `n=9`, cả hai chỉ số `9` và `10` đều không hợp lệ; nút là lá.
6. `[]` phải báo rỗng; `[42]` trả `42` và thành `[]`; `[2,5]` trả `2` và còn `[5]`. Không trường hợp nào trong ba trường hợp ấy cần thực hiện hoán đổi đẩy xuống.
7. Có. Xóa ô **cuối cùng** tương ứng xóa nút phải nhất ở tầng cuối, nên cây vẫn hoàn chỉnh. Nhưng khóa cuối đưa lên gốc có thể lớn hơn con trong min-heap (hoặc nhỏ hơn con trong max-heap).
8. Con được đưa lên vị trí cha là **khỏe nhất về độ ưu tiên** giữa các con; trong min-heap, đó là con nhỏ nhất. Giá trị ấy không lớn hơn con còn lại, còn khóa lớn hơn của cha được chuyển xuống nhánh đã chọn để xét tiếp.
9. Chiều cao `\lfloor\log_2 31\rfloor=4` cạnh. Một đường từ gốc tới lá có nhiều nhất `4` cạnh nên tối đa `4` lần hoán đổi.
10. `heappop` lấy gốc rồi sửa heap trong `O(\log n)`, còn `pop(0)` xóa đầu và dịch toàn bộ đuôi `O(n)`, không tự sửa heap-order.
11. `heapreplace` trả gốc cũ `2` và còn `[1,5,3]`. `heappushpop` thêm `1` rồi lấy khóa nhỏ nhất `1`, nên còn `[2,5,3]`.
12. Thứ tự là `B, A, C`. `sequence` tăng dần giúp phân xử khi `priority` bằng nhau để công việc đến sớm được lấy trước.
13. Tổng `O(n\log n)` vì có `n` lần lấy, mỗi lần tối đa `O(\log n)` với kích thước hiện tại. Một lần `pop` riêng lẻ vẫn chỉ đi qua tối đa một đường dài `O(\log n)`.
14. Không. Heap chỉ có thứ tự cha–con theo **khóa ưu tiên**, không tạo chỉ mục thứ tự theo `id`. Có thể dùng bảng băm `id→index` và cập nhật các vị trí sau mỗi phép hoán đổi, hoặc dùng cơ chế lazy deletion theo hợp đồng riêng.
15. `sift-down` dừng ngay, không cần hoán đổi. Thời gian của phần sửa bất biến là `O(1)` trong trường hợp này.

## 20. Ghi nhớ

**Lấy phần tử ưu tiên nhất** trong binary heap khác với chỉ **xem gốc**. Để `pop` mà vẫn giữ cấu trúc đúng, ta **lưu khóa gốc**, **đưa phần tử cuối lên thay gốc**, **bỏ ô cuối** để duy trì hình dạng cây hoàn chỉnh, rồi **đẩy xuống** theo một đường đến khi bất biến cha–con được khôi phục. Trong **min-heap**, phải chọn **con nhỏ nhất** và dừng khi cha `\le` con ấy; trong **max-heap**, chọn **con lớn nhất** và dừng khi cha `\ge` con ấy. Mỗi lần đẩy đi xuống nhiều nhất một tầng, nên phần duy trì heap sau phép lấy mất **`O(\log n)` thời gian xấu nhất** và **`O(1)` bộ nhớ phụ** với triển khai lặp. Cần xử lý heap rỗng, heap một phần tử, nút chỉ có một con và khóa trùng; khi dùng `heapq`, `heappop` mới là thao tác lấy gốc và giảm kích thước, khác với `heapreplace` và `heappushpop`.
