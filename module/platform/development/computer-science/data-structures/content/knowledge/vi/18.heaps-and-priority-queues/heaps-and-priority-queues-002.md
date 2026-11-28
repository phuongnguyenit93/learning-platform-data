# Min-heap, max-heap và bất biến thứ tự bộ phận

## 1. Vì sao cần heap thay vì cứ sắp xếp toàn bộ?

Một hệ thống có nhiều công việc đang chờ xử lý. Mỗi công việc mang một **độ ưu tiên** (*priority*). Ta cần liên tục:

1. Thêm một công việc mới.
2. Biết công việc nào cần xử lý tiếp.
3. Lấy công việc quan trọng nhất ra khỏi tập chờ.

Nếu lưu các công việc trong **mảng chưa sắp xếp**, việc thêm cuối thường nhanh, nhưng muốn biết công việc quan trọng nhất có thể phải quét cả mảng. Nếu luôn giữ **mảng đã sắp xếp**, có thể nhìn ngay phần tử đầu hoặc cuối, nhưng việc chèn đúng vị trí thường phải dịch nhiều phần tử.

**Heap** là một cấu trúc dữ liệu dung hòa hai yêu cầu: không cố sắp toàn bộ dữ liệu, mà chỉ duy trì **một bất biến đủ mạnh để phần tử ưu tiên nhất luôn nằm ở gốc**. Với *binary heap* (heap nhị phân) điển hình, có thể:

- Xem phần tử ưu tiên nhất: `O(1)`.
- Thêm một phần tử: `O(\log n)`.
- Lấy và xóa phần tử ưu tiên nhất: `O(\log n)`.

Chính sự **chỉ sắp xếp một phần** này giúp heap phù hợp làm nền tảng của **hàng đợi ưu tiên** (*priority queue*).

Sau bài học, bạn sẽ biết:

- Phân biệt **min-heap** và **max-heap**.
- Phát biểu chính xác hai bất biến của binary heap: **hình dạng** và **thứ tự cha–con**.
- Giải thích vì sao heap **không phải** mảng đã sắp xếp hay cây tìm kiếm nhị phân.
- Biểu diễn heap bằng mảng, tính chỉ số cha/con và kiểm tra bất biến.
- Theo dõi thao tác `sift-up`, `sift-down`, `push`, `pop` và `heapify`.
- Phân tích `O(1)`, `O(\log n)`, `O(n)` và các điều kiện áp dụng.
- Xử lý giá trị trùng nhau, cập nhật khóa và thiết kế hàng đợi ưu tiên thực tế.

Đây là bài thuộc chương **Heap và hàng đợi ưu tiên** của học phần **Cấu trúc dữ liệu**. Cách phân tích bất biến và đánh đổi thời gian, bộ nhớ ở đây liên hệ trực tiếp tới mảng, danh sách liên kết, stack, queue, bảng băm, cây và đồ thị.

## 2. Hai bất biến của binary heap

Ta tập trung vào **binary heap**, là một cách triển khai heap rất phổ biến. Một binary heap thông thường phải đồng thời thỏa **hai điều kiện khác nhau**.

### 2.1. Bất biến hình dạng: cây nhị phân hoàn chỉnh

Binary heap có dạng **cây nhị phân hoàn chỉnh** (*complete binary tree*):

- Mọi tầng, trừ tầng cuối, được lấp đầy.
- Những nút của tầng cuối được đặt **liên tiếp từ trái sang phải**, không có chỗ trống xen kẽ.

Ví dụ cây có bảy nút:

```text
                  (0)
                 /   \
              (1)     (2)
             /   \   /   \
           (3)  (4) (5)  (6)

Mỗi số trong ngoặc là CHỈ SỐ nút, chưa phải giá trị.
```

Cây có sáu nút sẽ dừng ở chỉ số `5`, tức có nút con bên trái của nút `(2)`, nhưng chưa có nút con bên phải `(6)`. Không được để một chỗ trống bên trái trong khi vẫn có nút ở phía bên phải cùng tầng.

**Hoàn chỉnh** không có nghĩa mọi nút đều có hai con. Một cây hoàn chỉnh có thể có nút chỉ có con trái ở tầng áp cuối. Cũng không đồng nghĩa với “cây nhị phân đầy đủ mọi tầng” (*perfect binary tree*).

Do cấu trúc này, đường từ gốc tới bất kỳ nút nào có độ dài không vượt quá chiều cao:

\[
h=\lfloor\log_2 n\rfloor \quad\text{với } n\ge1.
\]

Chiều cao được đếm theo **số cạnh** trên đường dài nhất từ gốc xuống lá. Heap rỗng không có gốc, nên công thức trên chỉ dành cho `n\ge1`.

### 2.2. Bất biến thứ tự: cha so với từng con

Với mỗi cạnh từ nút cha `p` đến nút con `c`:

**Min-heap** yêu cầu:

\[
\boxed{key(p)\le key(c).}
\]

**Max-heap** yêu cầu:

\[
\boxed{key(p)\ge key(c).}
\]

Đây là **bất biến thứ tự bộ phận** (*heap-order property*): chỉ có những quan hệ thứ tự nhất định giữa các nút bị ràng buộc. Các giá trị không bắt buộc tăng dần hoặc giảm dần khi duyệt theo hàng, theo thứ tự chỉ số mảng hay từ nhánh trái sang nhánh phải.

Nếu các khóa bằng nhau, quan hệ `\le` hoặc `\ge` vẫn đúng; vì vậy heap **cho phép giá trị trùng lặp**.

> Thuật ngữ “thứ tự bộ phận” ở đây nói đến **phạm vi các cặp nút mà cấu trúc buộc phải có quan hệ thứ tự**. Phép so sánh giữa các khóa có thể vẫn là thứ tự toàn phần (như số nguyên thông thường). Không cần hiểu rằng bản thân toán tử so sánh luôn là một *partial order* theo nghĩa lý thuyết tập hợp.

## 3. Min-heap: phần tử nhỏ nhất ở gốc

Xét các khóa:

```text
                      2
                    /   \
                   4     3
                  / \   / \
                 9   7 8   5

Biểu diễn mảng theo thứ tự tầng:
Chỉ số: [0, 1, 2, 3, 4, 5, 6]
Giá trị:[2, 4, 3, 9, 7, 8, 5]
```

Kiểm tra các quan hệ cha–con:

| Cha | Con | Quan hệ |
|---:|---:|---|
| `2` | `4`, `3` | `2\le4` và `2\le3` |
| `4` | `9`, `7` | `4\le9` và `4\le7` |
| `3` | `8`, `5` | `3\le8` và `3\le5` |

Tất cả đều đúng nên đây là một **min-heap hợp lệ**.

### Vì sao gốc là nhỏ nhất?

Từ gốc đi xuống một nút bất kỳ sẽ đi qua một dãy các cạnh cha–con. Trên mỗi cạnh của min-heap, khóa cha không lớn hơn khóa con. Áp dụng tính bắc cầu của quan hệ `\le`:

\[
key(root)\le key(v)\quad\text{với mọi nút }v.
\]

Do đó, **gốc chứa một khóa nhỏ nhất của toàn heap**, và trong biểu diễn mảng, đó là phần tử `A[0]` khi mảng không rỗng.

Nhưng hãy nhìn hai con của gốc: `4` ở bên trái và `3` ở bên phải. `4>3` **không vi phạm** điều gì. Heap không yêu cầu nhánh trái luôn nhỏ hơn nhánh phải.

### Min-heap không phải mảng được sắp tăng

Mảng `[2,4,3,9,7,8,5]` thỏa bất biến heap nhưng **không tăng dần**, vì `4>3` và `9>7`. Nó cũng không phải một *binary search tree* (BST): cây tìm kiếm nhị phân có những ràng buộc giữa **toàn bộ cây con trái và cây con phải**, còn heap chỉ có quan hệ giữa cha và con.

**Hệ quả quan trọng:** trong min-heap, đọc `A[0]` biết ngay giá trị nhỏ nhất, nhưng tìm xem giá trị `7` nằm ở đâu không thể mặc nhiên dùng **tìm kiếm nhị phân trên mảng**. Thứ tự mảng chưa đủ để loại bỏ một nửa.

## 4. Max-heap: phần tử lớn nhất ở gốc

Với **max-heap**, đảo chiều quan hệ so sánh:

```text
                      90
                    /    \
                  70      80
                 /  \    /  \
               30   60  50   40

Mảng: [90, 70, 80, 30, 60, 50, 40]
```

Các bất biến:

- `90\ge70`, `90\ge80`.
- `70\ge30`, `70\ge60`.
- `80\ge50`, `80\ge40`.

Mọi nút đều không lớn hơn gốc `90`. Vì vậy, **phần tử lớn nhất nằm ở `A[0]`**. Dù vậy, hai nút `70` và `80` ở cùng tầng vẫn có thể đứng theo thứ tự tùy ý.

### Bảng đối chiếu

| Thuộc tính | Min-heap | Max-heap |
|---|---|---|
| Bất biến trên từng cạnh | `parent\le child` | `parent\ge child` |
| Gốc lưu | Khóa nhỏ nhất | Khóa lớn nhất |
| Ý nghĩa ưu tiên | Giá trị khóa nhỏ hơn được lấy trước | Giá trị khóa lớn hơn được lấy trước |
| Chèn mới | Đưa cuối, có thể đẩy **lên** | Đưa cuối, có thể đẩy **lên** |
| Xóa gốc | Chuyển phần tử cuối lên, có thể đẩy **xuống** | Chuyển phần tử cuối lên, có thể đẩy **xuống** |
| Mảng lưu trữ có được sắp toàn phần? | Không | Không |
| Có cho phép khóa trùng nhau? | Có | Có |

Hai loại heap khác nhau ở chiều so sánh, không khác ở quy tắc hình dạng cây nhị phân hoàn chỉnh.

## 5. Một vài phản ví dụ giúp nhận diện bất biến

Đừng chỉ kiểm tra “gốc có vẻ nhỏ nhất” hoặc “gốc có vẻ lớn nhất”.

### 5.1. Gốc nhỏ nhất nhưng chưa phải min-heap

```text
                     1
                   /   \
                  4     2
                 /
                3

Mảng: [1, 4, 2, 3]
```

Gốc `1` đúng là nhỏ nhất, nhưng cạnh `4\to3` vi phạm `4\le3`. Vì vậy, **không phải min-heap**.

Điều kiện “gốc là nhỏ nhất” là **hệ quả** của bất biến heap, không phải điều kiện **đủ** để xác định heap hợp lệ.

### 5.2. Các cạnh đúng nhưng cây không hoàn chỉnh

```text
                    1
                  /   \
                 3     5
                      /
                     7
```

Mọi cha đều `\le` con, nhưng nút ở tầng cuối xuất hiện dưới nhánh phải khi những vị trí bên trái của tầng đó còn trống. Đây **không** phải binary heap theo định nghĩa hình dạng hoàn chỉnh. Cần kiểm tra **cả hình dạng và thứ tự**.

### 5.3. Mọi phần tử đều tăng dần thì có phải min-heap?

Mảng `[1,2,3,4,5]` khi được xem như cây nhị phân hoàn chỉnh **đúng là một min-heap**, vì cha ở chỉ số nhỏ hơn con nên giá trị cha không lớn hơn giá trị con. Nhưng đây chỉ là **một trong nhiều** cách bố trí min-heap. Heap không yêu cầu mảng tăng dần.

Tương tự, mảng giảm dần là một max-heap hợp lệ khi được xem theo quy tắc chỉ số của binary heap, nhưng không phải mọi max-heap đều có mảng giảm dần.

## 6. Biểu diễn binary heap bằng mảng

Một lợi thế lớn của binary heap là **không cần lưu con trỏ `left` hoặc `right` cho từng nút**. Do cây luôn hoàn chỉnh, ta biểu diễn nó bằng mảng theo thứ tự từng tầng, từ trái sang phải.

Cho mảng `A` có `n` phần tử, chỉ số bắt đầu từ `0`:

\[
\boxed{parent(i)=\left\lfloor\frac{i-1}{2}\right\rfloor},\qquad i>0.
\]

\[
\boxed{left(i)=2i+1},\qquad
\boxed{right(i)=2i+2}.
\]

Chỉ số con hợp lệ nếu **nhỏ hơn `n`**. Gốc `i=0` không có cha; không được gọi `parent(0)` rồi sử dụng kết quả như chỉ số cha hợp lệ.

Ví dụ `A=[2,4,3,9,7,8,5]`:

| Nút `i` | Giá trị `A[i]` | Cha | Con trái | Con phải |
|---:|---:|---|---|---|
| `0` | `2` | Không có | `1` (4) | `2` (3) |
| `1` | `4` | `0` (2) | `3` (9) | `4` (7) |
| `2` | `3` | `0` (2) | `5` (8) | `6` (5) |
| `3` | `9` | `1` (4) | Không có | Không có |
| `4` | `7` | `1` (4) | Không có | Không có |

### Các nút lá nằm ở đâu?

Với `n>0`, những nút có chỉ số:

\[
\left\lfloor n/2\right\rfloor,\ldots,n-1
\]

là **lá**: chúng không có con trái hợp lệ vì `2i+1\ge n`. Các nút có chỉ số `0,\ldots,\lfloor n/2\rfloor-1` là **nút trong**, có ít nhất một con.

Đây là cơ sở cho thuật toán **heapify từ dưới lên**: các lá tự thỏa bất biến cha–con vì không có con; chỉ cần sửa các nút trong.

### Độ phức tạp của phép lấy cha/con

Công thức chỉ số sử dụng một số phép toán số học cố định, nên tính cha/con là `O(1)`. Một bộ đệm mảng thông thường cũng đọc `A[i]` trong `O(1)`. Bộ nhớ cần cho `n` khóa là `O(n)` ô; phần liên kết cây không cần cấp phát `O(n)` con trỏ riêng.

Trong ngôn ngữ dùng số nguyên độ rộng cố định, hãy bảo đảm phép tính `2i+1` hoặc `2i+2` không tràn kiểu trước khi kiểm tra `<n`.

## 7. Kiểm tra một mảng có thỏa min-heap hay max-heap

Với biểu diễn mảng theo thứ tự tầng, **bất biến hình dạng đã được bảo đảm** nếu ta coi toàn bộ `n` vị trí `0..n-1` là các nút liên tiếp. Bài toán còn lại là kiểm tra bất biến thứ tự giữa cha và mỗi con.

```python
def is_min_heap(values: list[int]) -> bool:
    n = len(values)
    for i in range(n // 2):
        left = 2 * i + 1
        right = 2 * i + 2

        if left < n and values[i] > values[left]:
            return False
        if right < n and values[i] > values[right]:
            return False
    return True


def is_max_heap(values: list[int]) -> bool:
    n = len(values)
    for i in range(n // 2):
        left = 2 * i + 1
        right = 2 * i + 2

        if left < n and values[i] < values[left]:
            return False
        if right < n and values[i] < values[right]:
            return False
    return True


print(is_min_heap([2, 4, 3, 9, 7, 8, 5]))  # True
print(is_min_heap([1, 4, 2, 3]))          # False
print(is_max_heap([90, 70, 80, 30, 60, 50, 40]))  # True
print(is_min_heap([]))                    # True
print(is_max_heap([7]))                   # True
```

Một heap **rỗng** hoặc chỉ có một phần tử thỏa bất biến một cách hiển nhiên: không có cạnh cha–con nào vi phạm. Tuy nhiên, thao tác **xem phần tử gốc** phải báo rỗng thay vì đọc `A[0]` khi `n=0`.

Độ phức tạp của phép kiểm tra là `O(n)` thời gian, `O(1)` bộ nhớ phụ, giả định so sánh hai khóa tốn `O(1)`. Không thể kết luận một mảng là heap hợp lệ chỉ bằng việc kiểm tra phần tử gốc.

## 8. Thêm phần tử: chèn cuối rồi đẩy lên (sift-up)

Giả sử một min-heap đang có mảng:

```text
[2, 4, 3, 9, 7, 8, 5]
```

Ta muốn thêm khóa `1`.

**Bước 1 — giữ bất biến hình dạng.** Thêm vào cuối mảng, tương ứng vị trí trống kế tiếp ở tầng cuối:

```text
[2, 4, 3, 9, 7, 8, 5, 1]
                          ^
                    vị trí mới i=7
```

**Bước 2 — khôi phục bất biến thứ tự.** So sánh khóa mới với cha; nếu khóa mới nhỏ hơn cha, hoán đổi hai ô rồi tiếp tục đi lên:

```text
Sau thêm cuối:
[2, 4, 3, 9, 7, 8, 5, 1]

Hoán đổi 1 với cha 9 (i=7 và i=3):
[2, 4, 3, 1, 7, 8, 5, 9]

Hoán đổi 1 với cha 4 (i=3 và i=1):
[2, 1, 3, 4, 7, 8, 5, 9]

Hoán đổi 1 với cha 2 (i=1 và i=0):
[1, 2, 3, 4, 7, 8, 5, 9]
```

Kết quả là một min-heap hợp lệ có gốc mới bằng `1`.

### Mã giả

```text
MIN_PUSH(A, x):
    A.append(x)
    i = length(A) - 1

    while i > 0:
        p = (i - 1) // 2
        if A[p] <= A[i]:
            break
        swap(A[p], A[i])
        i = p
```

**Bất biến khi đẩy lên:** trước khi chèn, các cạnh đều hợp lệ; sau khi thêm cuối, chỉ cạnh giữa phần tử mới và cha của nó **có thể** sai. Sau mỗi lần hoán đổi với cha lớn hơn, các quan hệ ở nhánh bên dưới được phục hồi, và vị trí có thể vi phạm chuyển lên phía cha mới. Khi gặp cha `\le` phần tử hoặc đến gốc, toàn bộ heap hợp lệ.

Mỗi lần đổi chỗ đưa phần tử lên **một tầng**. Chiều cao cây là `O(\log n)` nên phần đẩy lên mất `O(\log n)` trong trường hợp xấu nhất. Nếu mảng động cần mở rộng vùng chứa, một lần `append` riêng lẻ còn có thể tốn `O(n)` do cấp phát lại; khi phân tích cấu trúc heap, ta thường tách chi phí duy trì heap `O(\log n)` khỏi chi phí tăng sức chứa, hoặc xem `append` có chi phí `O(1)` khấu hao.

Với max-heap, chỉ đổi dấu so sánh: nếu khóa mới **lớn hơn** cha thì hoán đổi và đi lên.

## 9. Lấy gốc: thay bằng phần tử cuối rồi đẩy xuống (sift-down)

Muốn lấy phần tử nhỏ nhất của min-heap `[2,4,3,9,7,8,5]`, ta cần xóa **gốc** `2`, nhưng vẫn phải giữ cây hoàn chỉnh.

Các bước:

1. Lưu giá trị gốc `2` để trả về.
2. Lấy phần tử **cuối** `5` đặt vào vị trí gốc, rồi giảm kích thước mảng. Nhờ bỏ ô cuối nên **hình dạng cây vẫn hoàn chỉnh**.
3. Nếu khóa gốc mới lớn hơn một nút con, hoán đổi với **con nhỏ hơn** để khôi phục min-heap, rồi tiếp tục đi xuống.

```text
Ban đầu:
[2, 4, 3, 9, 7, 8, 5]

Lưu gốc 2; đưa 5 cuối lên gốc:
[5, 4, 3, 9, 7, 8]
    ^     ^
    5 > 3: cạnh cha-con sai

Đổi với con nhỏ nhất là 3:
[3, 4, 5, 9, 7, 8]

Trả về 2; heap còn lại hợp lệ.
```

### Vì sao phải chọn con nhỏ hơn?

Giả sử gốc mới là `8`, hai con là `3` và `5`. Nếu hoán đổi `8` với `5`, gốc sau đổi sẽ là `5` nhưng con còn lại `3` nhỏ hơn gốc, nên bất biến vẫn sai. Chọn **con có khóa nhỏ nhất** giúp gốc sau đổi không lớn hơn cả hai con.

Mã giả:

```text
MIN_POP(A):
    require A is not empty
    answer = A[0]
    last = remove_last(A)
    if A is now empty:
        return answer

    A[0] = last
    i = 0
    while left(i) < length(A):
        child = left(i)
        if right(i) < length(A) and A[right(i)] < A[child]:
            child = right(i)
        if A[i] <= A[child]:
            break
        swap(A[i], A[child])
        i = child

    return answer
```

Với max-heap, chọn **con lớn hơn**, và chỉ hoán đổi khi khóa cha **nhỏ hơn** khóa con ấy.

**Bất biến khi đẩy xuống:** hai cây con của vị trí đang xét đã là heap hợp lệ; chỉ quan hệ tại vị trí chứa phần tử vừa đưa xuống có thể vi phạm. Đưa phần tử xuống phía con phù hợp sẽ sửa quan hệ ở vị trí hiện tại; mọi vi phạm còn lại (nếu có) nằm ở tầng bên dưới.

Số tầng phải đi xuống tối đa `O(\log n)`, nên xóa gốc mất `O(\log n)`. Heap có một phần tử trả về ngay sau khi bỏ phần tử cuối, không được cố đẩy xuống trên mảng rỗng.

## 10. Cài đặt min-heap bằng Python thuần

Đoạn dưới tự cài đặt ba thao tác cốt lõi để nhìn rõ cách duy trì bất biến. Mảng đầu vào phải là **min-heap hợp lệ** trước khi gọi `push` hoặc `pop`; hàm `heapify` ở phần tiếp theo dùng để chuyển một mảng bất kỳ thành min-heap.

```python
def sift_up(heap: list[int], index: int) -> None:
    while index > 0:
        parent = (index - 1) // 2
        if heap[parent] <= heap[index]:
            break
        heap[parent], heap[index] = heap[index], heap[parent]
        index = parent


def sift_down(heap: list[int], index: int) -> None:
    n = len(heap)
    while True:
        left = 2 * index + 1
        if left >= n:
            break  # Không có con

        right = left + 1
        smaller = left
        if right < n and heap[right] < heap[left]:
            smaller = right

        if heap[index] <= heap[smaller]:
            break

        heap[index], heap[smaller] = heap[smaller], heap[index]
        index = smaller


def min_push(heap: list[int], value: int) -> None:
    heap.append(value)
    sift_up(heap, len(heap) - 1)


def min_pop(heap: list[int]) -> int:
    if not heap:
        raise IndexError("Không thể lấy gốc từ heap rỗng")

    answer = heap[0]
    last = heap.pop()
    if heap:
        heap[0] = last
        sift_down(heap, 0)
    return answer


heap = [2, 4, 3, 9, 7, 8, 5]  # Đã là min-heap
min_push(heap, 1)
print(heap)           # [1, 2, 3, 4, 7, 8, 5, 9]
print(min_pop(heap))  # 1
print(heap)           # [2, 4, 3, 9, 7, 8, 5]
```

Nếu viết max-heap bằng chính thuật toán này, phải **đảo chiều so sánh trong cả `sift_up` và `sift_down`** (bao gồm cách chọn con), không chỉ đảo dấu ở một chỗ.

Để tính `peek` khi heap không rỗng, chỉ cần đọc `heap[0]` trong `O(1)`. Việc kiểm tra rỗng cần thiết vì với `heap=[]` không có nút gốc.

## 11. Tạo heap từ mảng bất kỳ: bottom-up heapify

Giả sử dữ liệu ban đầu là mảng chưa có bất biến heap:

```text
[9, 4, 7, 1, 2, 8, 3]
```

Có hai cách xây min-heap:

1. Bắt đầu từ heap rỗng và thêm từng phần tử bằng `push`. Mỗi lần `O(\log n)`, tổng **`O(n\log n)`** trong trường hợp xấu nhất.
2. Giữ nguyên mảng, duyệt các **nút trong từ phải sang trái, từ dưới lên**, gọi `sift_down` tại từng vị trí. Thuật toán **bottom-up heapify** chỉ mất **`O(n)`** thời gian.

### Thuật toán bottom-up

Các nút lá ở chỉ số `\lfloor n/2\rfloor,\ldots,n-1` đã là heap có một phần tử, nên không cần sửa. Ta bắt đầu ở **nút cha cuối cùng**:

\[
i_{\text{last parent}}=\left\lfloor\frac n2\right\rfloor-1.
\]

```python
def min_heapify(values: list[int]) -> None:
    """Biến đổi trực tiếp values thành một min-heap."""
    for index in range(len(values) // 2 - 1, -1, -1):
        sift_down(values, index)


values = [9, 4, 7, 1, 2, 8, 3]
min_heapify(values)
print(values)             # [1, 2, 3, 4, 9, 8, 7]
print(is_min_heap(values))  # True

empty: list[int] = []
min_heapify(empty)        # Không làm gì; không đọc chỉ số âm.
```

**Đầu ra không bắt buộc có đúng một hoán vị duy nhất.** Nhiều cách bố trí mảng đều có thể thỏa bất biến min-heap trên cùng một tập giá trị; thuật toán, quy tắc xử lý khi bằng nhau và thứ tự cập nhật có thể dẫn tới những heap hợp lệ khác nhau.

### Vì sao heapify có thể O(n), dù sift-down O(log n)?

Không phải mọi nút đều cần đi xuống tối đa `\log n` tầng:

- Khoảng một nửa số nút là **lá**, không phải đi xuống.
- Các nút ở gần đáy chỉ có thể đi xuống một vài tầng.
- Chỉ một số rất ít nút gần gốc có thể đi xuống `O(\log n)` tầng.

Đếm theo **chiều cao còn có thể đi xuống** `h`, số nút ở mức đó có cận tỷ lệ `n/2^{h+1}`. Tổng công việc bị chặn bởi:

\[
T(n)
\le O\!\left(n\sum_{h=0}^{\lfloor\log_2 n\rfloor}
\frac{h}{2^{h+1}}\right).
\]

Chuỗi vô hạn `\sum_{h=0}^{\infty}h/2^{h+1}=1` hội tụ, nên:

\[
\boxed{T(n)=O(n)}.
\]

Một heapify tổng quát còn phải đọc một lượng dữ liệu tỷ lệ `n`, vì vậy với đầu vào mảng bất kỳ và mô hình so sánh cơ bản, ta thường nói độ phức tạp xây heap từ dưới lên là **`\Theta(n)`**.

Hàm `min_heapify` sửa mảng **tại chỗ**, sử dụng `O(1)` biến phụ ngoài dữ liệu đang có khi `sift_down` được cài dạng lặp; không cần tạo thêm mảng chứa `n` phần tử.

## 12. Tổng hợp độ phức tạp các thao tác

Xét binary heap trên mảng, `n` là số phần tử, so sánh khóa `O(1)`; các cận dưới đây nói về thuật toán heap, với mảng đã cấp đủ vùng hoặc chi phí cấp phát được xét riêng.

| Thao tác | Min-heap | Max-heap | Thời gian |
|---|---|---|---|
| Xem gốc `peek` | Nhỏ nhất | Lớn nhất | `O(1)` |
| Thêm phần tử `push` | `sift-up` | `sift-up` | `O(\log n)` xấu nhất |
| Lấy và xóa gốc `pop` | `sift-down` | `sift-down` | `O(\log n)` xấu nhất |
| Xây từ mảng bằng `heapify` | Duy trì cha `\le` con | Duy trì cha `\ge` con | `O(n)` |
| Tìm **giá trị bất kỳ** | Không có thứ tự toàn phần | Không có thứ tự toàn phần | `O(n)` xấu nhất |
| Đọc phần tử tại chỉ số mảng `i` | Không gắn với thứ hạng | Không gắn với thứ hạng | `O(1)` nếu biết `i` |
| Xóa phần tử tại chỉ số `i` đã biết | Khôi phục bất biến | Khôi phục bất biến | `O(\log n)` |
| Cập nhật khóa tại chỉ số `i` đã biết | Đẩy lên/xuống theo chiều đổi khóa | Đẩy lên/xuống tương ứng | `O(\log n)` |
| Lấy **phần tử lớn nhất** từ min-heap | Không luôn ở gốc | — | `O(n)` xấu nhất |
| Lấy **phần tử nhỏ nhất** từ max-heap | — | Không luôn ở gốc | `O(n)` xấu nhất |
| Duyệt đủ `n` phần tử | Không theo thứ tự đã sắp | Không theo thứ tự đã sắp | `O(n)` |

Vì min-heap chỉ ràng buộc cha nhỏ hơn hoặc bằng con, **phần tử lớn nhất trong min-heap không có vị trí cố định**; nó nằm trong một nút lá khi `n>0`, nhưng có thể cần quét các lá để tìm, tức `O(n)`. Đối xứng, phần tử nhỏ nhất trong max-heap cũng có thể phải tìm trong các lá.

Về **bộ nhớ**, heap dùng mảng `O(n)` ô dữ liệu, với `O(1)` biến phụ cho các thao tác đẩy lên/đẩy xuống dạng lặp. Mảng động có thể dự phòng sức chứa; nếu sao chép input sang một mảng heap mới thì cần thêm `O(n)` bộ nhớ cho bản sao.

## 13. Xóa hoặc đổi khóa của một phần tử không ở gốc

Các thao tác `pop` và `peek` tập trung vào **gốc**. Một số ứng dụng, như lập lịch, còn cần sửa độ ưu tiên của một công việc đã biết.

### 13.1. Đổi khóa trong min-heap

Giả sử ta **đã biết chỉ số `i` hiện tại của phần tử**, và ghi đè bằng giá trị mới `x`:

- Nếu `x` **nhỏ hơn** khóa cũ, phần tử có thể nhỏ hơn cha → dùng `sift-up`.
- Nếu `x` **lớn hơn** khóa cũ, phần tử có thể lớn hơn con → dùng `sift-down`.
- Nếu bằng khóa cũ, không cần thay đổi.

```python
def min_change_key(heap: list[int], index: int, new_value: int) -> None:
    if not 0 <= index < len(heap):
        raise IndexError("Chỉ số không hợp lệ")
    old_value = heap[index]
    heap[index] = new_value
    if new_value < old_value:
        sift_up(heap, index)
    elif new_value > old_value:
        sift_down(heap, index)


h = [2, 4, 3, 9, 7, 8, 5]
min_change_key(h, 4, 1)   # Đổi 7 thành 1, rồi đẩy lên.
print(h)                  # [1, 2, 3, 9, 4, 8, 5]
print(is_min_heap(h))     # True
```

Với max-heap, chiều xử lý đảo lại: **tăng** khóa có thể đẩy lên; **giảm** khóa có thể đẩy xuống.

### 13.2. Nếu chỉ biết mã công việc, chưa biết vị trí

Tìm kiếm tùy ý trong heap có thể mất `O(n)`, bởi bất biến heap không phải chỉ mục theo mã. Muốn hỗ trợ cập nhật một công việc theo `id` trong `O(\log n)`, ta có thể kết hợp heap với **bảng băm ánh xạ `id → index`**.

Nhưng mỗi lần hoán đổi hai phần tử của heap, các chỉ số mới trong bảng băm **phải được cập nhật cùng lúc**. Nếu quên bảo trì, chỉ mục phụ trỏ tới vị trí sai, dẫn đến thay đổi độ ưu tiên của nhầm công việc.

Một lựa chọn khác là **xóa lười** (*lazy deletion*): thêm một bản ghi mới khi độ ưu tiên thay đổi, đánh dấu bản ghi cũ đã lỗi thời và bỏ qua nó khi lấy khỏi heap. Cách này đơn giản ở một số tình huống nhưng có thể làm heap phình lớn và cần quy tắc loại phần tử hết hiệu lực.

### 13.3. Xóa ở chỉ số i đã biết

Có thể đổi chỗ phần tử cần xóa với phần tử cuối, bỏ phần tử cuối, rồi **đẩy lên hoặc đẩy xuống** tùy quan hệ giữa giá trị thay thế và láng giềng. Vì đường di chuyển có nhiều nhất `O(\log n)` tầng, việc duy trì bất biến sau xóa tại vị trí đã biết có thể đạt `O(\log n)`. Tìm ra vị trí trước đó vẫn là chi phí riêng.

## 14. Giá trị bằng nhau và tính ổn định của thứ tự ưu tiên

Min-heap cho phép khóa bằng nhau:

```text
              2
            /   \
           2     3
          / \
         5   2

Mảng [2, 2, 3, 5, 2] là min-heap hợp lệ.
```

Không có bất biến nào buộc các phần tử cùng khóa `2` phải được lấy ra theo **thứ tự chúng được thêm vào**. Heap nhị phân thông thường không tự bảo đảm tính **ổn định** (*stability*).

Nếu yêu cầu “cùng độ ưu tiên thì công việc đến trước được xử lý trước”, hãy dùng khóa ghép:

\[
(\text{priority},\ \text{sequence}).
\]

Trong min-heap, so sánh trước theo priority, khi bằng nhau mới xét `sequence` tăng dần.

```python
import heapq
from itertools import count

sequence = count()
jobs: list[tuple[int, int, str]] = []

heapq.heappush(jobs, (2, next(sequence), "việc A"))
heapq.heappush(jobs, (1, next(sequence), "việc B"))
heapq.heappush(jobs, (2, next(sequence), "việc C"))

print(heapq.heappop(jobs)[2])  # việc B: độ ưu tiên 1
print(heapq.heappop(jobs)[2])  # việc A: cùng mức 2 nhưng đến trước
print(heapq.heappop(jobs)[2])  # việc C
```

Số thứ tự `sequence` nên là duy nhất trong vòng đời của các công việc cần so sánh. Với tuple `(priority, sequence, payload)`, khi hai trường đầu đã quyết định thứ tự, Python không cần so sánh trực tiếp các `payload` có thể thuộc các kiểu không so sánh được.

**Đừng lẫn “heap có thể chứa nhiều giá trị bằng nhau” với “heap giữ nguyên thứ tự chèn khi giá trị bằng nhau”**. Hai đặc tính này khác nhau.

## 15. Dùng thư viện Python heapq

Python có module chuẩn `heapq` cung cấp heap **kiểu min-heap** trên `list`. `heapq` không tạo lớp danh sách riêng: nó duy trì bất biến trên chính mảng được truyền vào.

```python
import heapq

priorities = [7, 2, 9, 4, 1]
heapq.heapify(priorities)   # Biến đổi tại chỗ, O(n).

print(priorities[0])        # 1: khóa nhỏ nhất, O(1).

heapq.heappush(priorities, 3)
print(heapq.heappop(priorities))  # 1
print(heapq.heappop(priorities))  # 2

# Các phần tử còn trong priorities vẫn tạo thành một heap,
# không nhất thiết ở thứ tự tăng dần khi nhìn toàn mảng.
```

Để lấy **tất cả** phần tử theo thứ tự tăng dần, ta có thể lặp `heappop` đến rỗng:

```python
data = [7, 2, 9, 4, 1]
heapq.heapify(data)

ascending = []
while data:
    ascending.append(heapq.heappop(data))
print(ascending)  # [1, 2, 4, 7, 9]
```

Xây heap `O(n)` và thực hiện `n` lần `pop` `O(\log n)` cho tổng thời gian **`O(n\log n)`**. Danh sách `ascending` là bộ nhớ cho kết quả đầu ra, không phải chi phí phụ của một lần lấy gốc.

### Mô phỏng max-heap với khóa số

Đối với các khóa số có phép đổi dấu phù hợp, ta có thể lưu **giá trị âm** rồi dùng min-heap:

```python
import heapq

values = [4, 9, 2, 7]
negated = [-value for value in values]
heapq.heapify(negated)

print(-heapq.heappop(negated))  # 9
print(-heapq.heappop(negated))  # 7
```

Đây là **mẹo đổi khóa**, không phải quy định rằng mọi max-heap luôn dùng số âm. Với các đối tượng có phép so sánh khác, có thể dùng một comparator/thứ tự khóa phù hợp hoặc API max-heap tương ứng của môi trường đang dùng. Đối với số nguyên độ rộng cố định ở một số ngôn ngữ, đổi dấu giá trị nhỏ nhất có thể gây tràn; không nên áp dụng mẹo này một cách mù quáng.

**Lưu ý:** các phép sửa `priorities[i] = ...` trực tiếp có thể làm mất bất biến heap. Hãy dùng thao tác duy trì heap, `heapify` lại khi cần, hoặc một cách quản lý chỉ mục/cập nhật đã được thiết kế.

## 16. Heap so với mảng đã sắp, BST và queue thông thường

Heap được thiết kế cho câu hỏi “**ai ưu tiên nhất lúc này?**”, không phải thay thế mọi cấu trúc tìm kiếm.

| Cấu trúc | Xem phần tử ưu tiên nhất | Thêm mới | Xóa phần tử ưu tiên nhất | Tìm giá trị bất kỳ |
|---|---|---|---|---|
| Mảng chưa sắp | `O(n)` để tìm min/max | `O(1)` khấu hao thêm cuối | `O(n)` tìm, sau đó xử lý xóa | `O(n)` |
| Mảng luôn sắp tăng | `O(1)` tại đầu/cuối | `O(n)` xấu nhất vì dịch | Có thể `O(1)` ở cuối nếu chọn cực đại, hoặc `O(n)` ở đầu nếu giữ thứ tự | `O(\log n)` bằng tìm nhị phân |
| Binary min-heap | `O(1)` xem min | `O(\log n)` | `O(\log n)` | `O(n)` |
| Binary max-heap | `O(1)` xem max | `O(\log n)` | `O(\log n)` | `O(n)` |
| Cây tìm kiếm cân bằng | `O(\log n)` tìm min/max tổng quát; có thể `O(1)` nếu lưu con trỏ cực trị | `O(\log n)` | `O(\log n)` | `O(\log n)` |
| Queue FIFO | `O(1)` xem phần tử đến trước | `O(1)` theo biểu diễn phù hợp | `O(1)` lấy đầu | `O(n)` tổng quát |

Bảng giả định thao tác so sánh khóa có thời gian hằng số, các cấu trúc triển khai điển hình và chưa có chỉ mục phụ. Chi phí bộ nhớ, ổn định thứ tự, duy trì con trỏ và xử lý khóa trùng có thể khác nhau đáng kể.

**Heap khác FIFO:** queue lấy phần tử theo thứ tự đến trước, bất kể “quan trọng” hay “không quan trọng”. Priority queue dùng heap lấy phần tử theo **khóa ưu tiên** (có thể thêm tiêu chí phụ để xử lý hòa).

**Heap khác BST:** trong BST, nhánh trái và phải bị ràng buộc theo khóa để hỗ trợ tìm kiếm; trong heap, thứ tự giữa các nhánh không đủ để tìm khóa bất kỳ nhanh.

## 17. Ứng dụng thực tế và lúc nào nên dùng loại nào

### 17.1. Hàng đợi tác vụ theo mức ưu tiên

Giả sử hệ thống dùng số nhỏ hơn nghĩa là khẩn cấp hơn:

```text
Task A: priority=5
Task B: priority=1
Task C: priority=3
```

Dùng min-heap, `Task B` được lấy trước; sau đó tùy trạng thái cập nhật, gốc mới sẽ là task có khóa nhỏ nhất. Thao tác nối thêm task không cần sắp lại toàn bộ danh sách.

Nếu số lớn hơn nghĩa là khẩn cấp hơn, dùng max-heap hoặc đảo chiều phép so sánh. **Min/max là quy ước về thứ tự của khóa, không phải đánh giá đạo đức rằng mức nào “thật sự quan trọng”.**

### 17.2. Thuật toán Dijkstra và Prim

Trong các thuật toán đồ thị dùng **hàng đợi ưu tiên**, ta thường cần lặp lại việc lấy đỉnh có **nhãn khoảng cách** nhỏ nhất (Dijkstra) hoặc trọng số cạnh phù hợp nhỏ nhất (Prim). Min-heap là lựa chọn tự nhiên vì cho `pop` khóa nhỏ nhất trong `O(\log n)`.

Một số cài đặt Dijkstra thêm bản ghi mới mỗi khi khoảng cách tốt hơn và bỏ qua bản ghi lỗi thời khi pop; cách khác dùng `decrease-key` với chỉ mục. Cần chú ý Dijkstra chuẩn giả định trọng số cạnh không âm. Chi phí toàn thuật toán phụ thuộc số đỉnh, số cạnh và cách duy trì priority queue, không chỉ chi phí của một lần `pop`.

### 17.3. Giữ k phần tử lớn nhất trong luồng

Muốn giữ **k giá trị lớn nhất** trong một dòng dữ liệu dài, có thể duy trì **min-heap kích thước tối đa k**:

- Gốc là giá trị nhỏ nhất **trong nhóm k giá trị lớn nhất đang giữ**.
- Khi đọc một giá trị mới lớn hơn gốc, thay gốc bằng giá trị mới rồi khôi phục heap.
- Nếu giá trị không lớn hơn gốc, có thể bỏ qua.

Khi duy trì một heap kích thước `k`, mỗi giá trị mới cần nhiều nhất `O(\log k)` thời gian, bộ nhớ cho nhóm giữ lại là `O(k)`. Với `n` giá trị đầu vào, tổng thời gian `O(n\log k)` trong trường hợp xấu nhất; nếu `k` là hằng số nhỏ, đây là cách tránh sắp cả `n` giá trị.

**Đối xứng:** muốn giữ `k` phần tử **nhỏ nhất**, có thể sử dụng max-heap kích thước `k` và thay gốc khi tìm thấy khóa nhỏ hơn.

## 18. Những lỗi và hiểu lầm thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| “Min-heap là mảng tăng dần.” | Chỉ bắt buộc cha `\le` con; các nhánh không có thứ tự toàn phần | Kiểm tra từng cạnh |
| “Gốc nhỏ nhất là đủ để xác nhận min-heap.” | Một nút con có thể nhỏ hơn cha của chính nó | Kiểm tra mọi cha–con và hình dạng |
| “Có thể tìm nhị phân trên mảng heap.” | Mảng không bảo đảm tăng hoặc giảm dần | Dùng tìm tuyến tính hoặc chỉ mục khác |
| “Heap là BST.” | BST ràng buộc cả cây con trái/phải; heap chỉ cha–con | Phân biệt bất biến |
| “Heap cho phép mỗi nút có bao nhiêu con tùy ý.” | Binary heap có tối đa hai con và hình dạng hoàn chỉnh | Đúng miền và chỉ số con |
| “Dùng `A[0]` để xem gốc dù heap rỗng.” | `n=0` không có chỉ số hợp lệ | Kiểm tra rỗng |
| “`parent(0)` là một chỉ số cha hợp lệ.” | Gốc không có cha | Chỉ tính parent khi `i>0` |
| “Khi sift-down có thể chọn bất cứ con nào nhỏ hơn cha.” | Có thể để con còn lại nhỏ hơn cha mới | Min-heap chọn **con nhỏ hơn**; max-heap chọn con lớn hơn |
| “`push` không cần sift-up.” | Khóa mới có thể nhỏ hơn cha ở đáy | Đẩy lên tới khi bất biến đúng |
| “`pop` chỉ việc xóa đầu mảng.” | Xóa đầu bằng dịch mảng `O(n)` và không theo chiến lược heap | Đưa phần tử cuối lên, rồi sift-down |
| “`heapify` cần `O(n\log n)` vì mọi nút sift-down.” | Hầu hết nút gần lá, chỉ đi xuống rất ít | Phân tích tổng theo chiều cao, `O(n)` |
| “Giá trị trùng được pop theo thứ tự chèn.” | Heap cơ bản không ổn định | Dùng khóa phụ `sequence` |
| “Sửa bất kỳ khóa nào trong heap mà không cần cập nhật.” | Có thể phá bất biến | Dùng sift-up/down hoặc heapify |
| “Tìm và cập nhật một `id` bất kỳ trong `O(\log n)`.” | Chưa chắc biết vị trí hiện tại | Dùng `id→index` và cập nhật sau mỗi hoán đổi |
| “Chọn max-heap vì độ ưu tiên số nhỏ là quan trọng.” | Chiều so sánh không khớp quy ước | Chọn min-heap hoặc đổi khóa |
| “Mọi giá trị đều so sánh được và quan hệ luôn nhất quán.” | `NaN` hoặc phép so sánh bất thường có thể phá suy luận | Chuẩn hóa khóa và xác định quan hệ thứ tự hợp lệ |

## 19. Bài tập tự kiểm tra

Cho các mảng sau, xem chúng là biểu diễn theo thứ tự tầng của **binary heap**:

```text
H1 = [2, 5, 3, 9, 7, 8, 4]
H2 = [9, 6, 8, 2, 5, 3, 7]
H3 = [1, 6, 4, 3, 8]
```

**Bài 1.** Trong ba mảng trên, mảng nào là min-heap hợp lệ? Mảng nào là max-heap hợp lệ? Nếu không hợp lệ, hãy chỉ ra một cặp cha–con vi phạm.

**Bài 2.** Với mảng dài `n=12`, nút ở chỉ số `i=4` có cha ở chỉ số nào, con trái/con phải ở chỉ số nào? Các con có hợp lệ không?

**Bài 3.** Với min-heap `A=[2,4,3,9,7,8,5]`, hãy mô phỏng thêm khóa `1` và ghi mảng cuối. Phần tử `1` đi qua bao nhiêu tầng?

**Bài 4.** Với cùng min-heap ban đầu, hãy mô phỏng một lần `pop` lấy khóa nhỏ nhất. Giá trị được trả về và mảng còn lại là gì?

**Bài 5.** Giải thích vì sao `[1,4,2,3]` không phải min-heap dù phần tử đầu là nhỏ nhất.

**Bài 6.** Mảng `[1,2,3,4,5]` có phải min-heap không? Điều đó có nghĩa min-heap luôn sắp tăng không?

**Bài 7.** Vì sao `heapify` từ dưới lên có thời gian `O(n)` dù mỗi lần `sift-down` riêng lẻ có thể là `O(\log n)`?

**Bài 8.** Một min-heap chứa `n` khóa. Vì sao tìm **khóa lớn nhất** thường mất `O(n)`? Có thể giới hạn tìm ở nhóm nút nào?

**Bài 9.** Trong min-heap, khi giảm khóa của một nút đã biết chỉ số, nên dùng `sift-up` hay `sift-down`? Còn tăng khóa thì sao?

**Bài 10.** Một hệ thống cần lấy tác vụ có `priority` nhỏ hơn trước, nhưng khi bằng nhau phải xử lý tác vụ đến trước. Hãy đề xuất khóa so sánh trong min-heap.

**Bài 11.** Muốn giữ `k=100` giá trị lớn nhất của một luồng có một triệu giá trị, nên dùng min-heap hay max-heap kích thước `100`? Vì sao?

**Bài 12.** Với mảng rỗng `[]` và mảng một phần tử `[42]`, xác định kết quả của phép kiểm tra bất biến min-heap, `peek` và `pop` ở mỗi trường hợp.

**Bài 13.** Một chương trình dùng `id→index` để cập nhật khóa trong heap. Sau khi hoán đổi hai phần tử ở chỉ số `i` và `j`, phải bảo trì thêm điều gì?

**Bài 14.** Một heap có `n=31` phần tử. Chiều cao của binary heap là bao nhiêu cạnh? Điều đó giải thích cận độ phức tạp nào cho phép chèn/xóa gốc?

### Đáp án và giải thích

1. `H1` là **min-heap**: `2\le5,3`; `5\le9,7`; `3\le8,4`. `H2` là **max-heap**: `9\ge6,8`; `6\ge2,5`; `8\ge3,7`. `H3` không phải min-heap vì `6>3` (cha ở chỉ số `1`, con ở chỉ số `3`); cũng không phải max-heap vì `1<6` (cha ở `0`, con ở `1`).
2. Cha: `(4-1)//2=1`. Con trái: `2×4+1=9`; con phải `2×4+2=10`; cả hai hợp lệ vì nhỏ hơn `12`.
3. Kết quả `[1,2,3,4,7,8,5,9]`. Khóa `1` hoán đổi lên qua `3` cạnh/tầng: từ chỉ số `7→3→1→0`.
4. Trả `2`. Đưa `5` lên gốc và đổi với con `3`, còn `[3,4,5,9,7,8]`.
5. Nút `4` ở chỉ số `1` có con `3` ở chỉ số `3`; `4>3` vi phạm min-heap.
6. Có. Mảng tăng dần là một min-heap hợp lệ khi diễn giải như cây hoàn chỉnh, nhưng heap hợp lệ có thể có mảng không tăng dần, ví dụ `[2,4,3,9,7,8,5]`.
7. Khoảng một nửa nút là lá và không cần đẩy; các nút gần đáy chỉ đẩy vài tầng; tổng chi phí theo chiều cao có cận `n\sum_{h\ge0}h/2^{h+1}=O(n)`.
8. Chỉ có ràng buộc cha nhỏ hơn hoặc bằng con, nên không xác định được vị trí khóa lớn nhất. Một phần tử lớn nhất nằm ở **lá** (khi heap không rỗng); có thể quét các chỉ số `\lfloor n/2\rfloor,\ldots,n-1`, mất `O(n)`.
9. Giảm khóa có thể vi phạm với cha, nên dùng `sift-up`. Tăng khóa có thể vi phạm với con, nên dùng `sift-down`.
10. Dùng khóa ghép `(priority, sequence)`, trong đó `sequence` là số tăng dần khi thêm tác vụ. Khóa nhỏ hơn được lấy trước, khi bằng priority thì sequence nhỏ hơn được lấy trước.
11. Dùng **min-heap** kích thước `100`; gốc là nhỏ nhất trong số `100` giá trị đang giữ. Bỏ qua các giá trị mới không lớn hơn gốc, thay gốc khi gặp giá trị lớn hơn.
12. `[]` và `[42]` đều thỏa bất biến min-heap. Với `[]`, `peek` và `pop` phải báo rỗng. Với `[42]`, `peek` trả `42`; `pop` trả `42` rồi heap thành rỗng.
13. Phải cập nhật `index` của **cả hai `id` bị hoán đổi** để ánh xạ luôn trỏ đúng vị trí hiện tại. Nếu không, các lần thay đổi khóa sau có thể sửa nhầm phần tử.
14. `\lfloor\log_2 31\rfloor=4` cạnh. Chèn và xóa gốc chỉ đi qua một đường có tối đa `4` cạnh ở heap này; nói chung thời gian `O(\log n)`.

## 20. Ghi nhớ

**Binary heap** đồng thời duy trì **hình dạng cây nhị phân hoàn chỉnh** và **thứ tự bộ phận trên từng cạnh cha–con**. Min-heap yêu cầu `parent\le child` nên gốc chứa **khóa nhỏ nhất**; max-heap yêu cầu `parent\ge child` nên gốc chứa **khóa lớn nhất**. Hai loại heap **không sắp toàn bộ mảng** và **không phải cây tìm kiếm nhị phân**, vì vậy tìm giá trị bất kỳ vẫn có thể `O(n)`. Biểu diễn mảng dùng chỉ số cha `(i-1)//2`, con trái `2i+1` và con phải `2i+2`, không cần con trỏ liên kết. `Push` sửa bằng `sift-up`, `pop` sửa bằng `sift-down` trong `O(\log n)`; xây heap từ dưới lên bằng `heapify` mất `O(n)`. Khi dùng heap làm **hàng đợi ưu tiên**, phải xác định chiều của khóa, cách xử lý trường hợp trùng nhau và cơ chế duy trì chỉ mục nếu cần sửa hoặc xóa một công việc không nằm ở gốc.
