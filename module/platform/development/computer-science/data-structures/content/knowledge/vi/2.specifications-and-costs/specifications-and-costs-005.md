# Chi phí truy cập, tìm kiếm, chèn, xóa và duyệt

> **Chương:** Đặc tả và chi phí · **Bài học:** Chi phí truy cập, tìm kiếm, chèn, xóa và duyệt

Một danh sách chứa 100.000 phần tử có thể cho phép lấy phần tử thứ 50.000 gần như tức thì, nhưng vẫn mất nhiều công sức để chèn một phần tử vào đầu. Một bảng băm có thể tìm theo khóa rất nhanh trong điều kiện thông thường, nhưng không tự cung cấp thứ tự tăng dần của các khóa. Một heap lấy phần tử ưu tiên cao nhất hiệu quả, song lại không phù hợp nếu ta thường xuyên tìm một phần tử bất kỳ.

Vậy phải chọn cấu trúc dữ liệu nào? Trước hết, cần **xác định chính xác phép toán ứng dụng sử dụng**, rồi so sánh **chi phí thời gian và bộ nhớ** của từng cách triển khai. Bài học này xem xét năm nhóm phép toán: **truy cập**, **tìm kiếm**, **chèn**, **xóa** và **duyệt**. Chúng được đặt trong phạm vi mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`), gồm mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời làm rõ bất biến và điều kiện để các kết luận về độ phức tạp có hiệu lực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt truy cập phần tử theo vị trí với tìm phần tử theo giá trị hoặc khóa; phân biệt xóa phần tử **đã biết vị trí** với xóa phần tử **cần tìm trước**.
2. Đọc và lập bảng độ phức tạp cho năm nhóm phép toán trên các cấu trúc dữ liệu thường gặp.
3. Phân biệt chi phí tốt nhất, xấu nhất, kỳ vọng và khấu hao, kèm các giả định về đầu vào và cài đặt.
4. Giải thích vì sao tìm kiếm nhanh không đồng nghĩa chèn hoặc xóa nhanh.
5. Tính chi phí của cả **chuỗi thao tác ứng dụng** và nhận biết sự đánh đổi giữa thời gian, bộ nhớ, thứ tự dữ liệu và tính đúng đắn.
6. Áp dụng kiến thức để chọn mảng, danh sách liên kết, bảng băm, cây cân bằng, heap hoặc cách biểu diễn đồ thị phù hợp.

## 2. Xác định chính xác năm nhóm phép toán

Cùng một từ như “truy cập” hay “xóa” có thể chỉ nhiều yêu cầu khác nhau. Để so sánh hợp lý, ta cần thống nhất ý nghĩa:

| Nhóm | Câu hỏi của người sử dụng | Ví dụ |
| --- | --- | --- |
| **Truy cập (access)** | Tôi biết vị trí, đầu/đuôi hoặc định danh; lấy phần tử tương ứng như thế nào? | `a[i]`; `stack.peek()`; `map.get(key)` |
| **Tìm kiếm (search)** | Tôi chưa biết phần tử nằm ở đâu; xác định nó có tồn tại hay không, ở đâu? | Tìm `x` trong mảng; tìm khóa trong cây |
| **Chèn (insert)** | Thêm một phần tử ở vị trí hoặc theo quy tắc nào? | `a.insert(i,x)`; `queue.enqueue(x)` |
| **Xóa (delete/remove)** | Bỏ phần tử nào và giữ bất biến gì? | Xóa tại chỉ số `i`; xóa nút có khóa `k` |
| **Duyệt (traverse/iterate)** | Xử lý lần lượt một tập hoặc tất cả phần tử nào? | Duyệt mảng, nút cây, cạnh đồ thị |

### 2.1. Vị trí, giá trị, khóa và nút đã biết là bốn loại đầu vào khác nhau

Ví dụ, với danh sách liên kết đơn có `n` nút:

- Lấy **nút đầu** khi đang giữ con trỏ `head` tốn O(1).
- Lấy **nút ở chỉ số `i`** tính từ đầu cần lần theo `next`, tốn O(i + 1) bước trong trường hợp thông thường.
- Tìm **nút có giá trị bằng `x`** cần so sánh lần lượt, xấu nhất O(n).
- Xóa **nút đầu** tốn O(1); xóa nút bất kỳ khi **đã có con trỏ tới nút trước nó** tốn O(1).
- Xóa theo **giá trị `x`** phải tìm trước, xấu nhất O(n).

Nếu một bảng chỉ ghi “xóa trong danh sách liên kết O(1)” mà không nói **đã biết nút và liên kết cần thiết**, người đọc rất dễ áp dụng sai.

### 2.2. Ký hiệu kích thước dữ liệu

Trong bài:

- `n`: số phần tử đang được lưu trong cấu trúc.
- `i`: chỉ số vị trí (tính từ 0 khi có chỉ số).
- `h`: chiều cao hoặc số nút trên đường tìm trong cây, tùy quy ước; O(h) có cùng ý nghĩa tăng trưởng trong cả hai cách đếm.
- `V`: số đỉnh của đồ thị; `E`: số cạnh.
- `deg(u)`: số cạnh kề cần xem khi làm việc với đỉnh `u`; đối với đồ thị có hướng và danh sách cạnh đi ra, đây là bậc ra.
- `k`: độ dài khóa khi khóa không có kích thước cố định.
- `q`: số truy vấn; `u`: số thao tác cập nhật (chèn hoặc xóa).

Hãy định nghĩa đơn vị ngay khi phân tích; đặc biệt không dùng một `n` để thay đồng thời số đỉnh và số cạnh của đồ thị.

## 3. Cách đọc độ phức tạp trước khi so sánh

Các ký hiệu tiệm cận mô tả tốc độ tăng của chi phí khi kích thước thay đổi, theo **mô hình chi phí đã nêu**.

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| O(1) | Bị chặn trên bởi hằng số khi kích thước tăng | Truy cập `a[i]` trong mảng |
| O(log n) | Tăng theo logarit | Tìm khóa trong cây tìm kiếm cân bằng |
| O(n) | Tăng tối đa tuyến tính | Duyệt `n` phần tử |
| O(n log n) | Thường gặp khi sắp xếp bằng so sánh | Sắp xếp `n` khóa |
| O(n²) | Thường gặp khi phải xem nhiều cặp phần tử | So sánh mọi cặp trong một dãy |

**O là chặn trên**, không tự khẳng định số thao tác chính xác hay chặn dưới. Khi có cả chặn trên và chặn dưới cùng bậc, ta viết Θ. Ví dụ, duyệt và xử lý mỗi phần tử đúng một lần với chi phí hằng số là Θ(n); một phép tìm kiếm có thể dừng sớm ở một bước nhưng vẫn có trường hợp xấu nhất Θ(n).

### 3.1. Tốt nhất, xấu nhất, trung bình, kỳ vọng và khấu hao

- **Tốt nhất (best case):** trường hợp thuận lợi nhất trong nhóm đầu vào đang xét; ví dụ tìm khóa đúng ở ô đầu.
- **Xấu nhất (worst case):** trường hợp tốn nhiều nhất với cùng kích thước; ví dụ tìm khóa không có trong mảng chưa sắp xếp.
- **Trung bình (average case):** chi phí trung bình theo **phân bố đầu vào đã xác định**.
- **Kỳ vọng (expected):** kỳ vọng theo yếu tố ngẫu nhiên cụ thể, chẳng hạn lựa chọn hàm băm hoặc phân bố khóa.
- **Khấu hao (amortized):** chi phí được phân bổ trên một **chuỗi thao tác**, cho phép vài lần đắt nhưng tổng chi phí nhỏ.

Một lần `append` vào mảng động có thể mất O(n) khi phải mở rộng. Nếu vùng đệm tăng gấp đôi theo quy tắc thông thường, `append` có chi phí O(1) **khấu hao** trên chuỗi nhiều lần thêm. Hai kết luận này không mâu thuẫn.

### 3.2. Những giả định sẽ dùng

Trừ khi ghi khác, ta giả định việc đọc/ghi một ô mảng theo chỉ số, cập nhật một tham chiếu và so sánh hai khóa vừa một từ máy mất O(1). Việc cấp phát một nút được xem có chi phí hằng số theo mô hình thông thường. Khóa là chuỗi dài có thể khiến tính hash hoặc so sánh tốn O(k); cấp phát thực tế, cache và đồng bộ luồng cũng có thể ảnh hưởng thời gian đo được.

Các bảng là **chi phí của cài đặt được nêu**, không phải định nghĩa bắt buộc của kiểu dữ liệu trừu tượng.

## 4. Mảng: truy cập nhanh, chèn/xóa giữa tốn di chuyển

Mảng lưu các phần tử tại những vị trí có thể truy cập trực tiếp theo chỉ số. Mảng động bổ sung khả năng mở rộng vùng đệm khi đầy.

| Phép toán | Mảng chưa sắp xếp | Mảng đã sắp xếp | Điều kiện |
| --- | --- | --- | --- |
| Truy cập `a[i]` | O(1) | O(1) | `i` hợp lệ |
| Tìm theo giá trị | O(n) xấu nhất | O(log n) nếu dùng tìm kiếm nhị phân | Đã sắp theo quan hệ so sánh phù hợp |
| Thêm vào cuối mảng động | O(1) khấu hao | Không nhất thiết giữ thứ tự | Tăng sức chứa theo chiến lược phù hợp |
| Chèn tại đầu hoặc giữa | O(n) xấu nhất | O(n) xấu nhất dù đã tìm vị trí bằng nhị phân | Phải dịch phần tử |
| Xóa phần tử cuối | O(1) nếu không thu nhỏ vùng đệm | Có thể O(1) khi phần tử cuối cần xóa | Không tính việc tái phân bổ |
| Xóa tại đầu hoặc giữa | O(n) xấu nhất | O(n) xấu nhất | Phải dồn các phần tử còn lại |
| Duyệt toàn bộ | Θ(n) | Θ(n) | Xử lý mỗi phần tử O(1) |

### 4.1. Vì sao truy cập theo chỉ số là O(1)?

Khi biết địa chỉ cơ sở, kích thước ô và chỉ số `i`, máy có thể tính vị trí ô cần đọc bằng phép toán địa chỉ có chi phí hằng số trong mô hình RAM:

```text
address(a[i]) = base_address + i * element_width
```

Không cần duyệt `a[0], a[1], …` để tới `a[i]`. Đây là ưu điểm lớn khi ứng dụng phải truy cập nhiều vị trí tùy ý.

### 4.2. Chèn vào đầu: một lần chèn cần nhiều lần dịch

Giả sử mảng đang chứa:

```text
Chỉ số:      0   1   2   3
Giá trị:    [A,  B,  C,  D]

Chèn X tại chỉ số 1:

Trước:      [A,  B,  C,  D]
Dịch phải:  [A,  _,  B,  C,  D]
Sau:        [A,  X,  B,  C,  D]
```

Cần di chuyển ba phần tử `B, C, D`. Với mảng kích thước `n`, chèn ở chỉ số `i` cần dịch `n - i` phần tử (giả sử còn sức chứa; nếu không còn thì phải mở rộng và sao chép thêm).

Nếu chèn đầu (`i = 0`), số lần dịch là `n`. Nếu thêm cuối (`i = n`), số lần dịch là 0; tuy nhiên mảng động có thể phải mở rộng.

### 4.3. Xóa cũng có nhiều trường hợp

Giả sử xóa `B` ở chỉ số 1 khỏi `[A,B,C,D]`. Để giữ các phần tử liên tục, mảng phải chuyển `C,D` sang trái. Số phần tử dịch là `n-i-1`.

Với `n=4, i=1`, cần dịch 2 phần tử. Xóa cuối (`i=n-1`) không phải dịch phần tử nào; xóa đầu dịch `n-1` phần tử.

**Phân biệt xóa theo chỉ số và xóa theo giá trị:** nếu người gọi chỉ đưa `"B"` mà chưa biết vị trí, mảng chưa sắp xếp còn phải tìm `"B"`, xấu nhất O(n). Sau đó mới xóa ở vị trí tìm được.

### 4.4. Mảng sắp xếp: tìm O(log n), chèn vẫn O(n)

Với mảng sắp tăng `[2,5,9,14]`, để chèn `7` ta có thể dùng tìm kiếm nhị phân tìm vị trí 2 trong O(log n), nhưng vẫn phải dịch `9` và `14` về bên phải.

```python
def insert_sorted_counted(values, value):
    """Chèn value trước phần tử đầu tiên >= value."""
    left, right = 0, len(values)
    probes = 0

    while left < right:
        mid = (left + right) // 2
        probes += 1
        if values[mid] < value:
            left = mid + 1
        else:
            right = mid

    position = left
    shifts = len(values) - position
    values.insert(position, value)
    return position, probes, shifts


data = [2, 5, 9, 14]
assert insert_sorted_counted(data, 7) == (2, 2, 2)
assert data == [2, 5, 7, 9, 14]
```

Trong ví dụ, `probes` đếm số lần khảo sát vị trí giữa; `shifts` đếm số phần tử phải dịch về mặt logic. Python `list.insert` không cung cấp bộ đếm dịch nội bộ, nên `shifts` là số lượng được suy ra từ vị trí chèn, không phải số đo chu kỳ CPU.

Chi phí tổng là O(log n + n) = O(n) trong trường hợp xấu nhất. Đây là ví dụ điển hình cho việc **tối ưu tìm vị trí chưa chắc làm toàn bộ thao tác chèn nhanh**.

## 5. Danh sách liên kết: cập nhật liên kết nhanh khi biết vị trí

Danh sách liên kết lưu các phần tử trong những nút nối bằng tham chiếu. Với danh sách liên kết đơn, mỗi nút có `value` và `next`; danh sách liên kết đôi còn có `prev`.

| Phép toán | Liên kết đơn có `head` | Liên kết đôi có `head, tail` | Điều kiện |
| --- | --- | --- | --- |
| Truy cập đầu | O(1) | O(1) | `head` đã có |
| Truy cập chỉ số `i` | O(i + 1), xấu nhất O(n) | O(min(i+1, n-i)) nếu duyệt từ đầu/đuôi | Không có truy cập ngẫu nhiên trực tiếp |
| Tìm giá trị | O(n) xấu nhất | O(n) xấu nhất | Từng nút có thể phải được xem |
| Chèn vào đầu | O(1) | O(1) | Chỉ đổi các tham chiếu biên |
| Thêm cuối | O(1) nếu giữ `tail`; nếu không thường O(n) | O(1) khi giữ `tail` | Cấp phát nút O(1) theo mô hình |
| Chèn sau nút đã biết | O(1) | O(1) | Có con trỏ tới nút thích hợp |
| Xóa đầu | O(1) | O(1) | Xử lý rỗng và cập nhật đầu/đuôi |
| Xóa một nút bất kỳ | O(1) nếu đã biết **nút trước nó** | O(1) nếu đã có nút cần xóa | Nếu còn phải tìm nút thì O(n) |
| Duyệt hết | Θ(n) | Θ(n) | Mỗi nút xử lý O(1) |

### 5.1. Truy cập theo vị trí khác chèn sau nút đã có

Danh sách `A → B → C → D` không có công thức tính địa chỉ nút thứ 3 từ con trỏ đầu. Muốn lấy `D` phải đi qua các liên kết đến `D`, mất Θ(n) nếu `n` nút và nút cần lấy ở cuối.

Nhưng nếu ta **đang giữ con trỏ trực tiếp tới nút `B`**, chèn `X` ngay sau `B` chỉ cần vài phép gán:

```python
# prev trỏ tới nút B đã được tìm thấy.
new_node.next = prev.next
prev.next = new_node
# A -> B -> X -> C -> D
```

Hai phép gán liên kết là O(1). Nếu phải tìm `B` theo giá trị từ `head` thì chi phí toàn thao tác lại có thể là O(n).

### 5.2. Vì sao xóa cuối của liên kết đơn thường O(n)?

Ngay cả khi giữ con trỏ `tail` tới nút cuối, để xóa nút cuối của danh sách **liên kết đơn**, ta cần tìm nút **ngay trước `tail`** để đặt `next = None` và cập nhật `tail`. Chỉ có liên kết `next` thì không thể tự đi lùi từ `tail`; tìm nút trước có thể mất O(n).

Danh sách **liên kết đôi** có `prev` nên xóa cuối là O(1) nếu cấu trúc giữ con trỏ `tail` hợp lệ.

### 5.3. Bất biến biểu diễn và bộ nhớ

Với danh sách có `head, tail, size`, các bất biến quan trọng có thể gồm:

- `size ≥ 0` và bằng số nút thực sự nối từ `head`.
- Khi `size=0`, `head = tail = None`.
- Khi `size > 0`, `tail` là nút cuối và `tail.next = None`.
- Danh sách không có chu trình ngoài ý muốn; với danh sách đôi, liên kết `prev` và `next` nhất quán.

Mỗi nút cần thêm bộ nhớ cho tham chiếu liên kết và có thể phải cấp phát riêng. Danh sách liên kết thường có tổng bộ nhớ O(n) nhưng hệ số ẩn lớn hơn một mảng chỉ lưu dữ liệu.

## 6. Stack, Queue và Deque: so sánh đúng các phép toán được phép

Stack và Queue là những **kiểu dữ liệu trừu tượng** với quy tắc lấy phần tử khác nhau. Bảng độ phức tạp phải nói rõ cách triển khai:

| ADT và thao tác | Cách triển khai | Thời gian | Ghi chú |
| --- | --- | --- | --- |
| Stack `push` | Mảng động, đỉnh ở cuối | O(1) khấu hao; O(n) ở lần mở rộng | Giữ thứ tự LIFO |
| Stack `pop`, `peek` | Mảng động, đỉnh ở cuối | O(1) | Giả định `pop` không co vùng đệm |
| Stack `push`, `pop`, `peek` | Liên kết đơn, đỉnh ở đầu | O(1) | Cập nhật đầu danh sách |
| Queue `enqueue`, `dequeue` | Mảng vòng có khả năng mở rộng | O(1) khấu hao cho enqueue; O(1) cho dequeue | Có thể sao chép khi tăng sức chứa |
| Queue `enqueue`, `dequeue` | Liên kết đơn giữ đầu và đuôi | O(1) | Duy trì cả `head` và `tail` |
| Queue `dequeue` | Mảng thông thường dùng xóa đầu, phải dồn phần tử | O(n) xấu nhất | Đúng FIFO nhưng có thể kém hiệu quả |
| Deque thêm/lấy ở cả hai đầu | Mảng vòng hoặc liên kết đôi phù hợp | O(1) khấu hao hoặc O(1) | Tùy cách quản lý vùng đệm/nút |

### 6.1. Nguy cơ khi suy từ tên phương thức

Ví dụ Python:

```python
queue = ["A", "B", "C"]
first = queue.pop(0)  # FIFO: A
# Các phần tử còn lại cần được dồn về đầu.
```

`pop(0)` lấy đúng phần tử đầu nhưng có chi phí O(n) do di chuyển các phần tử còn lại. Ngược lại:

```python
from collections import deque

queue = deque(["A", "B", "C"])
first = queue.popleft()  # FIFO: A, O(1)
```

`collections.deque` được thiết kế để thêm/lấy ở hai đầu hiệu quả; truy cập theo chỉ số ở gần giữa deque không có cùng lợi thế với mảng động. Lựa chọn triển khai phải xuất phát từ **tập thao tác ứng dụng thực hiện nhiều nhất**.

### 6.2. Tìm phần tử tùy ý không thuộc ưu thế của Stack/Queue

Các API Stack và Queue thông thường không cần hỗ trợ `find(x)` hoặc `get(i)`. Nếu vẫn bổ sung thao tác tìm `x` bằng cách duyệt lần lượt, chi phí thường O(n). Một thiết kế yêu cầu tìm và xóa theo mã định danh thường xuyên có thể cần thêm một bảng băm đi kèm, nhưng phải duy trì tính nhất quán giữa hai cấu trúc.

## 7. Bảng băm: truy cập theo khóa nhanh trong điều kiện phù hợp

Bảng băm (*hash table*) thường được dùng để cài đặt **Map** (khóa → giá trị) hoặc **Set** (tập phần tử không trùng).

Ý tưởng: tính giá trị băm của khóa, ánh xạ tới một bucket, rồi tìm khóa trong bucket hoặc trong chuỗi ô dò theo chiến lược va chạm.

| Phép toán với Map | Chi phí kỳ vọng/thông thường | Trường hợp xấu | Giả định |
| --- | --- | --- | --- |
| `get(key)` hoặc `contains(key)` | O(1) | O(n) | Hash và so sánh khóa O(1); hệ số tải được kiểm soát; phân bố tốt |
| `put(key, value)` | O(1) kỳ vọng/khấu hao tùy chiến lược | O(n) | Có thể cần xử lý va chạm hoặc mở rộng/rehash |
| `remove(key)` | O(1) kỳ vọng | O(n) | Phải tìm đúng khóa trước khi xóa |
| Duyệt tất cả mục | O(n + b) theo số mục và bucket | O(n + b) | `b` là số bucket; thường O(n) khi `b = O(n)` |
| Lấy toàn bộ khóa theo thứ tự tăng | Có thể O(n log n) | Phụ thuộc thuật toán sắp xếp | Map băm không tự bảo đảm thứ tự tăng |

Ở đây `n` là số khóa, `b` là số bucket. Nếu hàm băm phải đọc toàn bộ khóa chuỗi dài `k` ký tự, một lời gọi có thể thêm chi phí O(k), kể cả khi bucket chỉ chứa một khóa.

### 7.1. O(1) kỳ vọng đến từ đâu?

Giả sử hệ số tải `α = n/b` được duy trì trong một khoảng phù hợp và phân bố hash đủ đều. Số khóa cần xem trong một bucket có thể nhỏ theo kỳ vọng, nên các phép truy cập, tìm, chèn và xóa theo khóa thường là O(1) kỳ vọng khi chi phí hash và so sánh được xem là hằng số.

Nếu nhiều khóa va chạm vào cùng bucket, việc tìm hoặc xóa có thể phải xét O(n) khóa. Kết luận O(1) **không phải cam kết xấu nhất cho mọi đầu vào**.

### 7.2. Mở rộng, rehash và chi phí khấu hao

Khi bảng băm gần đầy theo ngưỡng đã chọn, cài đặt có thể tạo bảng bucket mới và đưa các khóa hiện có vào vị trí thích hợp. Một lần tái băm có thể mất O(n), trong khi số lần tái băm trên chuỗi dài chèn thường được phân bổ để có O(1) khấu hao **trong điều kiện chiến lược tăng trưởng và phân bố băm phù hợp**.

Cần phân biệt chi phí của thao tác đơn lẻ, kỳ vọng theo phân bố băm và khấu hao trên chuỗi cập nhật.

### 7.3. Một số nhu cầu không phù hợp nếu chỉ dùng bảng băm

Nếu ứng dụng yêu cầu duyệt khóa theo thứ tự tăng, tìm khóa nhỏ nhất/lớn nhất, hoặc truy vấn khoảng `[a,b]` thường xuyên, một cây tìm kiếm cân bằng có thể phù hợp hơn. Bảng băm vẫn có thể giải quyết bằng cách trích xuất và sắp xếp khóa, nhưng phải trả chi phí bổ sung.

Một số ngôn ngữ hoặc thư viện bảo đảm thứ tự chèn cho Map dựa trên bảng băm; **thứ tự chèn** vẫn khác với **thứ tự tăng dần theo khóa**. Cần đọc hợp đồng cụ thể, không suy ra từ tên “hash map”.

## 8. Cây tìm kiếm: chi phí đi theo chiều cao

Một cây tìm kiếm nhị phân (BST) lưu khóa theo quy tắc: khóa ở cây con trái nhỏ hơn khóa tại nút, khóa ở cây con phải lớn hơn (hoặc dùng một quy tắc rõ ràng khác cho khóa trùng).

Để tìm `key`, thuật toán so sánh tại gốc rồi chỉ đi tiếp một nhánh. Số nút đi qua phụ thuộc chiều cao `h`:

\[
T_{\text{search}}(n)=O(h)
\]

| Cây / phép toán | Tìm khóa | Chèn khóa | Xóa khóa | Duyệt toàn cây |
| --- | --- | --- | --- | --- |
| BST không tự cân bằng | O(h), xấu nhất O(n) | O(h), xấu nhất O(n) | O(h), xấu nhất O(n) | Θ(n) |
| BST tự cân bằng (ví dụ AVL, đỏ-đen) | O(log n) xấu nhất | O(log n) xấu nhất | O(log n) xấu nhất | Θ(n) |

Cây cân bằng duy trì bất biến giới hạn chiều cao ở O(log n), thông qua thao tác tái cân bằng như phép quay. Chi phí quay cục bộ thường O(1), nhưng việc tìm đường đi và bảo toàn bất biến có thể cần O(log n) công việc.

### 8.1. Ví dụ cây lệch

Nếu chèn lần lượt `1,2,3,4,5` vào BST thông thường không tự cân bằng, có thể nhận được:

```text
1
 \
  2
   \
    3
     \
      4
       \
        5
```

Tìm `5` đi qua năm nút, nên chi phí là Θ(n) trong cấu hình này. Một cây cân bằng lưu cùng năm khóa có chiều cao nhỏ hơn và bảo đảm tìm kiếm O(log n) cho mọi thứ tự chèn.

### 8.2. Truy cập theo thứ tự duyệt không đồng nghĩa truy cập theo chỉ số

BST phù hợp để tìm theo **khóa**. Nó không mặc định hỗ trợ lấy phần tử thứ `i` nhanh như `a[i]` của mảng. Nếu mỗi nút được bổ sung số lượng nút trong cây con và duy trì thông tin đó, một *order-statistic tree* cân bằng có thể chọn phần tử theo hạng trong O(log n). Đây là khả năng **bổ sung của cài đặt**, không mặc định cho BST.

Duyệt trung thứ tự (*inorder*) BST cho khóa tăng dần khi quan hệ so sánh và quy tắc xử lý khóa trùng được xác định phù hợp. Duyệt toàn bộ `n` nút tốn Θ(n); tìm `k` khóa trong một khoảng trên cây cân bằng có thể thực hiện trong O(log n + k) nếu thuật toán chỉ đi vào các nhánh liên quan.

## 9. Heap: tốt cho đỉnh ưu tiên, không tốt cho tìm bất kỳ

Heap nhị phân nhỏ nhất (*min-heap*) là cây nhị phân gần đầy, thường lưu bằng mảng, thỏa điều kiện khóa cha không lớn hơn khóa các con.

Điều này bảo đảm **phần tử nhỏ nhất nằm ở gốc**; không có nghĩa toàn bộ mảng đang sắp xếp tăng dần.

| Phép toán của min-heap | Thời gian | Lý do |
| --- | --- | --- |
| Xem phần tử nhỏ nhất (`peek_min`) | O(1) | Đọc gốc |
| Chèn một phần tử | O(log n) xấu nhất | Đưa lên dọc đường đến gốc nếu cần |
| Lấy và xóa phần tử nhỏ nhất (`extract_min`) | O(log n) xấu nhất | Thay gốc rồi đẩy xuống để phục hồi bất biến |
| Tìm một giá trị bất kỳ | O(n) xấu nhất | Quan hệ heap không đủ để tìm nhị phân toàn bộ |
| Xóa tại chỉ số heap đã biết | O(log n) xấu nhất | Sửa bằng đẩy lên hoặc đẩy xuống |
| Xóa theo giá trị chưa biết vị trí | O(n) xấu nhất | Tìm vị trí O(n) rồi sửa heap |
| Duyệt mọi phần tử, không yêu cầu thứ tự | Θ(n) | Đọc toàn bộ mảng |
| Lấy lần lượt tất cả phần tử theo thứ tự ưu tiên | O(n log n) | `n` lần `extract_min` |

Heap là lựa chọn tự nhiên cho Priority Queue. Nếu ứng dụng cần tìm và xóa một nhiệm vụ bất kỳ bằng mã định danh rất thường xuyên, có thể kết hợp heap với một bảng tra cứu định danh → chỉ số heap. Khi các phần tử đổi chỗ, bảng chỉ số phải được cập nhật để giữ đúng ánh xạ.

**Lưu ý:** xây dựng heap từ một mảng có sẵn bằng thuật toán *bottom-up heapify* chuẩn mất O(n), khác với việc chèn `n` phần tử từng cái một có chặn trên O(n log n).

## 10. Đồ thị: chi phí phụ thuộc cách biểu diễn cạnh

Với đồ thị, “truy cập” có thể là **kiểm tra một cạnh** giữa hai đỉnh, còn “duyệt” có thể là **liệt kê láng giềng** hoặc thực hiện BFS/DFS.

Cho đồ thị đơn có `V` đỉnh và `E` cạnh. Xét ba biểu diễn:

1. **Ma trận kề:** mảng `V × V`, ô `adj[u][v]` ghi quan hệ cạnh.
2. **Danh sách kề bằng danh sách:** mỗi đỉnh giữ các láng giềng trong danh sách.
3. **Danh sách kề bằng tập băm:** mỗi đỉnh giữ tập láng giềng cho phép kiểm tra thuộc nhanh theo kỳ vọng.

| Phép toán | Ma trận kề | Danh sách kề bằng danh sách | Tập kề băm |
| --- | --- | --- | --- |
| Kiểm tra `has_edge(u,v)` | O(1) | O(deg(u) + 1) | O(1) kỳ vọng |
| Thêm cạnh, nếu cho phép thêm trực tiếp | O(1) | O(1) khấu hao khi nối cuối | O(1) kỳ vọng |
| Thêm cạnh nhưng phải tránh trùng | O(1) | O(deg(u) + 1) | O(1) kỳ vọng |
| Xóa một cạnh | O(1) | O(deg(u) + 1) | O(1) kỳ vọng |
| Liệt kê toàn bộ láng giềng của `u` | O(V) | Θ(deg(u) + 1) | Θ(deg(u) + 1) trên cấu trúc tập thông thường |
| BFS/DFS toàn bộ các thành phần | O(V²) | O(V + E) | O(V + E) kỳ vọng cho thao tác tập phù hợp |
| Bộ nhớ lưu đồ thị | Θ(V²) | Θ(V + E) | O(V + E) kỳ vọng về số mục lưu |

Trong bảng, việc truy cập định danh đỉnh hoặc tìm cấu trúc kề của nó được xem là O(1); nếu phải ánh xạ định danh phức tạp, cần cộng chi phí đó. Với đồ thị vô hướng, thao tác thêm/xóa cạnh phải cập nhật cả hai phía; số phía là hằng số nên bậc chi phí không đổi.

Ký hiệu `+1` trong `O(deg(u)+1)` giúp thể hiện trường hợp đỉnh có bậc 0 vẫn có chi phí hữu hạn để kiểm tra hoặc trả lời.

### 10.1. Vì sao danh sách kề tốt cho đồ thị thưa?

Giả sử `V=10.000` và `E=20.000`. Ma trận kề cần một ô cho gần `V²` cặp đỉnh, bất kể có cạnh hay không. Danh sách kề chỉ lưu thông tin đỉnh và các cạnh thực sự có, nên quy mô tăng theo `V+E`.

Khi duyệt từ một đỉnh trong danh sách kề, ta đọc các cạnh thực sự nối với đỉnh đó. Với ma trận kề, thường phải quét cả hàng gồm `V` ô để xác định láng giềng.

### 10.2. Chi phí xóa đỉnh

Xóa **cạnh** và xóa **đỉnh** là hai thao tác khác nhau:

- Với danh sách kề, xóa đỉnh `v` có thể yêu cầu loại tất cả cạnh đi vào `v` trong những danh sách của đỉnh khác. Nếu không có chỉ mục cạnh đi vào, công việc có thể là O(V+E).
- Với ma trận kề, nếu phải xây lại ma trận đặc có kích thước `(V-1) × (V-1)`, chi phí có thể O(V²). Một thiết kế dùng ô đánh dấu đỉnh không hoạt động có thể chọn hành vi khác và giữ lại vùng nhớ cũ.
- Xóa đỉnh có thể buộc đổi chỉ số của đỉnh khác. Nếu API công khai định danh ổn định, cài đặt phải giữ cam kết này.

Đừng áp dụng giá O(1) của thao tác **xóa một cạnh trong ma trận** cho thao tác **xóa cả đỉnh**.

### 10.3. Duyệt từ một đỉnh và duyệt toàn bộ

BFS/DFS từ đỉnh bắt đầu chỉ xử lý thành phần có thể tới được. Nếu gọi `V_r, E_r` là số đỉnh/cạnh thực sự duyệt, chi phí xử lý lõi của một BFS/DFS dùng danh sách kề là O(V_r + E_r). Nếu mã còn khởi tạo mảng `visited` dài `V` thì phải tính thêm O(V) cho bước khởi tạo.

Để duyệt **mọi thành phần liên thông**, chi phí toàn bộ là O(V+E) với danh sách kề hoặc O(V²) với ma trận kề theo cách quét hàng.

## 11. Bảng tổng hợp nhanh: chọn cấu trúc theo thao tác

Bảng này tóm tắt **trường hợp xấu nhất**, trừ những ô ghi rõ khấu hao hoặc kỳ vọng. Để bảng gọn, các thao tác khác nhau theo kiểu dữ liệu được ghi trong cột đầu.

| Cấu trúc | Truy cập / xem | Tìm kiếm | Chèn | Xóa | Duyệt tất cả |
| --- | --- | --- | --- | --- | --- |
| Mảng động chưa sắp | Chỉ số O(1) | Giá trị O(n) | Cuối O(1) khấu hao; giữa O(n) | Cuối O(1); giữa O(n) | Θ(n) |
| Mảng sắp xếp | Chỉ số O(1) | Nhị phân O(log n) | Giữ thứ tự O(n) | Giữ thứ tự O(n) | Θ(n) |
| Liên kết đơn | Đầu O(1); chỉ số O(n) xấu nhất | Giá trị O(n) | Đầu/ sau nút đã biết O(1) | Đầu/ sau nút trước đã biết O(1) | Θ(n) |
| Liên kết đôi có đầu/đuôi | Hai đầu O(1); chỉ số O(n) xấu nhất | Giá trị O(n) | Hai đầu / cạnh nút đã biết O(1) | Hai đầu / nút đã biết O(1) | Θ(n) |
| Stack thích hợp | Đỉnh O(1) | Tùy API; duyệt tìm O(n) | `push` O(1) hoặc khấu hao | `pop` O(1) | Θ(n) |
| Queue thích hợp | Đầu O(1) | Tùy API; duyệt tìm O(n) | `enqueue` O(1) hoặc khấu hao | `dequeue` O(1) | Θ(n) |
| Hash Map | Theo khóa O(1) kỳ vọng | Theo khóa O(1) kỳ vọng | O(1) kỳ vọng/khấu hao | O(1) kỳ vọng | O(n+b) |
| Cây tìm kiếm cân bằng | Theo khóa O(log n) | Theo khóa O(log n) | O(log n) | O(log n) | Θ(n) |
| Heap nhị phân | Đỉnh O(1) | Giá trị tùy ý O(n) | O(log n) | Xóa đỉnh O(log n) | Θ(n), không sắp thứ tự |
| Danh sách kề đồ thị | Liệt kê kề O(deg(u)+1) | Kiểm tra cạnh O(deg(u)+1) | Thêm cạnh O(1) khấu hao nếu không dò trùng | Xóa cạnh O(deg(u)+1) | O(V+E) |
| Ma trận kề đồ thị | Kiểm tra cạnh O(1) | Kiểm tra cạnh O(1) | Thêm cạnh O(1) | Xóa cạnh O(1) | O(V²) nếu duyệt toàn bộ |

**Chú ý các điều kiện bị rút gọn trong bảng:** chi phí liên kết O(1) khi **đã giữ đúng con trỏ**; hash O(1) là kết quả theo giả định phân bố và khóa; mảng có thể phải tái cấp phát; cây phải tự cân bằng; đồ thị dùng danh sách kề bằng danh sách thường phải duyệt để tránh cạnh trùng. Nếu thay điều kiện, kết quả có thể đổi.

## 12. Đếm chi phí của cả quy trình: bài toán từ thực tế

Giả sử một dịch vụ quản lý hồ sơ có:

- `n` hồ sơ ban đầu.
- `q` lần tra cứu theo mã hồ sơ.
- `u` lần thêm hoặc xóa hồ sơ.
- Một số màn hình cần liệt kê hồ sơ theo thứ tự mã tăng dần.

Không có một lựa chọn nào luôn tốt nhất cho mọi yêu cầu. Ta thử mô hình hóa ba phương án.

### 12.1. Mảng có sắp xếp

Nếu dữ liệu ban đầu chưa sắp:

\[
T_{\text{array}}\approx O(n\log n)+O(q\log(n+u))+O(u(n+u))
\]

Ta tính chi phí sắp xếp ban đầu, mỗi lần tìm bằng nhị phân, và mỗi lần chèn/xóa có thể phải dịch một số lượng phần tử tỷ lệ với kích thước đang có. Nếu không có xóa và chỉ thêm vào cuối theo đúng thứ tự, chi phí cập nhật có thể thấp hơn; công thức trên là một chặn trên theo kịch bản cập nhật tùy vị trí.

Ưu điểm là truy cập theo chỉ số O(1) và duyệt tăng dần Θ(n+u) khi mảng đã duy trì thứ tự.

### 12.2. Cây tìm kiếm cân bằng

Nếu xây cây bằng `n` lần chèn và mỗi cập nhật duy trì cân bằng:

\[
T_{\text{tree}}=O((n+q+u)\log(n+u+1))
\]

Tra cứu và cập nhật đều có chặn trên logarit theo số khóa. Duyệt trung thứ tự trả hồ sơ theo mã tăng dần trong Θ(s) với `s` là số khóa hiện còn, khi quan hệ thứ tự được quy định. Cây có thêm chi phí nút, liên kết và thông tin cân bằng.

### 12.3. Bảng băm

Với hash và so sánh khóa O(1), hệ số tải phù hợp và tái băm có chiến lược tăng trưởng thích hợp:

\[
E[T_{\text{hash}}]=O(n+q+u)
\]

Đây là chi phí kỳ vọng/khấu hao theo các giả định, chưa bao gồm yêu cầu **liệt kê tăng dần**. Để đáp ứng yêu cầu đó, có thể trích tất cả khóa ra rồi sắp xếp, thường O(s log s) cho mỗi lần liệt kê. Nếu màn hình này được dùng nhiều, cây cân bằng hoặc một chỉ mục thứ tự có thể đáng cân nhắc.

### 12.4. Bài học từ ví dụ

- **Chủ yếu tra theo mã, ít cần thứ tự:** bảng băm thường đáng thử đầu tiên.
- **Tra cứu và cập nhật thường xuyên, đồng thời phải duyệt có thứ tự:** cây cân bằng phù hợp.
- **Dữ liệu khá ổn định, duyệt nhiều và truy cập chỉ số thường xuyên:** mảng đã sắp xếp có lợi thế; cập nhật giữa là điểm cần đánh giá.

Đây là **định hướng theo mô hình**, chưa thay thế đo đạc thực tế. Trong sản phẩm thật còn phải xét bộ nhớ, kích thước khóa, mức đồng thời và API cần bảo đảm.

## 13. Những lỗi thường gặp khi so sánh chi phí

| Nhận định thiếu chính xác | Vấn đề | Cách phát biểu đúng hơn |
| --- | --- | --- |
| “Danh sách liên kết chèn O(1).” | Có thể còn phải tìm vị trí O(n). | Chèn **sau nút đã biết** O(1); chèn tại chỉ số chưa biết có thể O(n). |
| “Mảng sắp xếp thao tác O(log n).” | Tìm nhị phân nhanh nhưng chèn/xóa dịch nhiều ô. | Tìm O(log n); chèn/xóa giữ thứ tự O(n) xấu nhất. |
| “Hash Map luôn tìm O(1).” | Va chạm, khóa dài, tái băm có thể tốn hơn. | O(1) kỳ vọng khi có giả định phù hợp; xấu nhất có thể O(n). |
| “Heap đã được sắp xếp.” | Heap chỉ đảm bảo quan hệ ưu tiên cha–con. | Xem đỉnh O(1), tìm phần tử tùy ý O(n) xấu nhất. |
| “Cây tìm kiếm có O(log n).” | BST không cân bằng có thể bị lệch. | Cây **cân bằng** bảo đảm O(log n) theo khóa. |
| “Duyệt đồ thị luôn O(V+E).” | Biểu diễn ma trận quét cả hàng cạnh không tồn tại. | Danh sách kề O(V+E); ma trận kề quét hàng O(V²). |
| “Xóa phần tử cuối danh sách liên kết đơn O(1) vì có tail.” | Cần tìm nút trước tail. | Xóa cuối có thể O(n) nếu chỉ liên kết `next`. |
| “Chỉ cần nhìn thời gian một thao tác.” | Bỏ qua chi phí xây dựng, cập nhật và các loại truy vấn. | Tính tổng chi phí của chuỗi thao tác với tần suất phù hợp. |
| “Duyệt O(n) nên mọi cách triển khai bằng nhau.” | Bộ nhớ, thứ tự, cache, cấp phát và kiểu khóa khác. | Big-O cho xu hướng; đo thêm trên tải thực tế. |

## 14. Bài tập thực hành có gợi ý đáp án

### Bài 1 — Chèn và xóa trong mảng

Cho mảng `[A,B,C,D,E,F]` kích thước `n=6`. Chèn `X` tại chỉ số 2, sau đó xóa phần tử ở chỉ số 4 của **mảng mới**. Hãy tính số phần tử cần di chuyển cho từng thao tác.

**Gợi ý:** Chèn tại `i=2` phải dịch `6−2=4` phần tử `C,D,E,F`. Mảng mới là `[A,B,X,C,D,E,F]`. Xóa tại chỉ số 4 (phần tử `D`) cần dịch `7−4−1=2` phần tử `E,F`. Sau xóa còn `[A,B,X,C,E,F]`.

### Bài 2 — Chèn sau nút đã biết

Danh sách liên kết đơn có 10.000 nút. Bạn đang giữ con trỏ đến nút `P` và muốn chèn `X` ngay sau `P`. Chi phí là bao nhiêu? Nếu chỉ biết `P` có khóa `k` thì sao?

**Gợi ý:** Chèn sau con trỏ có sẵn là O(1). Nếu phải tìm nút có khóa `k` từ đầu, tổng thời gian có thể O(n).

### Bài 3 — Chọn cấu trúc cho danh sách học viên

Ứng dụng cần tra cứu học viên bằng mã, thêm/xóa thường xuyên và thỉnh thoảng hiển thị tất cả học viên theo mã tăng dần. Hãy so sánh bảng băm với cây tìm kiếm cân bằng.

**Gợi ý:** Bảng băm thường tra và cập nhật O(1) kỳ vọng nhưng muốn sắp tăng dần có thể cần O(n log n) mỗi lần tạo danh sách. Cây cân bằng tra và cập nhật O(log n) xấu nhất, duyệt khóa theo thứ tự Θ(n). Tần suất hiển thị có thứ tự sẽ ảnh hưởng lựa chọn.

### Bài 4 — Stack/Queue và phần tử đầu

Một người dùng Queue thực hiện 100.000 lần lấy phần tử đầu. Một triển khai dùng `list.pop(0)`; triển khai khác dùng mảng vòng hoặc `deque.popleft()`. Phân tích khác biệt.

**Gợi ý:** Với `n` phần tử đang có, một `pop(0)` có thể tốn O(n) do dịch dữ liệu; lặp nhiều lần trên một danh sách đang giảm từ `n` tới rỗng có thể dẫn đến tổng Θ(n²) lần di chuyển. `popleft` trên deque hoặc xóa đầu của mảng vòng được thiết kế đúng có thể đạt O(1) mỗi lần, tổng Θ(n) cho `n` lần lấy.

### Bài 5 — Tìm kiếm trong heap

Min-heap có 1.000 phần tử. Hãy ước lượng bậc độ phức tạp khi (a) đọc giá trị nhỏ nhất, (b) thêm một giá trị, (c) tìm xem giá trị bất kỳ `x` có tồn tại không, (d) lấy và xóa giá trị nhỏ nhất.

**Gợi ý:** (a) O(1); (b) O(log n); (c) O(n) xấu nhất nếu không có chỉ mục bổ sung; (d) O(log n). Không dùng tìm kiếm nhị phân trên mảng heap vì thứ tự mảng không tăng dần.

### Bài 6 — Duyệt đồ thị thưa

Cho đồ thị có `V=8.000` đỉnh và `E=12.000` cạnh. So sánh biểu diễn ma trận kề với danh sách kề khi thường xuyên BFS duyệt toàn bộ các thành phần.

**Gợi ý:** Dùng ma trận kề và quét hàng, BFS có chi phí O(V²); với danh sách kề là O(V+E). Bộ nhớ ma trận cũng O(V²), còn danh sách kề O(V+E). Vì đồ thị thưa, danh sách kề thường phù hợp hơn.

### Bài 7 — Có thật mọi thao tác bảng băm đều O(1)?

Một Map dùng khóa chuỗi dài `k` ký tự. Một lần `get` phải tính hash bằng cách đọc toàn bộ chuỗi. Hãy phân tích phần công việc bị bỏ qua khi nói `get` O(1).

**Gợi ý:** Chỉ riêng việc tính hash đã có thể tốn O(k), nên chi phí thực phụ thuộc độ dài khóa. O(1) kỳ vọng theo số mục `n` thường dựa trên giả định khóa có chi phí hash và so sánh hằng số hoặc hash đã được tính/lưu theo cách phù hợp.

### Bài 8 — Số truy vấn có thể đổi lựa chọn

Có `n=100.000` khóa cố định và `q` truy vấn kiểm tra tồn tại. Bạn phân vân giữa mảng chưa sắp xếp với tìm tuyến tính và bảng băm phải xây trước. Hãy lập công thức và nêu khi nào cần benchmark.

**Gợi ý:** Mảng tìm tuyến tính có tổng O(qn) trường hợp xấu. Bảng băm cần O(n) kỳ vọng để xây và thêm O(q) kỳ vọng để truy vấn, với giả định hash/so sánh O(1). Nếu chỉ có vài truy vấn, chi phí chuẩn bị và bộ nhớ của bảng băm có thể chưa đáng; cần đo trên phân bố dữ liệu và phần cứng thực tế để chọn.

## 15. Mẫu tự kiểm tra khi chọn cấu trúc dữ liệu

Trước khi kết luận cấu trúc nào nhanh hơn, hãy điền các thông tin sau cho **từng thao tác**:

```text
1. Phép toán cụ thể:
   - truy cập theo chỉ số, khóa, con trỏ đã biết hay phần tử đầu?
   - tìm giá trị, kiểm tra tồn tại hay tìm khoảng?
   - chèn/xóa ở vị trí đã biết hay phải tìm trước?
   - duyệt tất cả, duyệt có thứ tự hay duyệt từ một đỉnh?

2. Kích thước:
   n = ?   h = ?   V = ?   E = ?   k = ?
   Bao nhiêu thao tác tìm q, cập nhật u?

3. Cài đặt:
   - mảng động, liên kết đơn/đôi, hash, cây cân bằng,
     heap, ma trận kề hay danh sách kề?
   - đã giữ con trỏ, chỉ mục hay không?
   - có duy trì bất biến thứ tự, dung lượng, cân bằng?

4. Chi phí:
   - thời gian tốt nhất, xấu nhất;
   - kỳ vọng hoặc khấu hao nếu có;
   - thời gian tiền xử lý và tổng chuỗi thao tác;
   - bộ nhớ dữ liệu và bộ nhớ phụ.

5. Điều kiện đúng:
   - yêu cầu về thứ tự, lỗi và giá trị trả về;
   - giới hạn độ trễ, bộ nhớ và tính đồng thời;
   - những giả định về khóa, phân bố và cấp phát.
```

Hãy luôn kết hợp **hợp đồng thao tác**, **bất biến của biểu diễn** và **tần suất sử dụng thực tế**. Mảng nổi bật ở truy cập theo chỉ số; danh sách liên kết mạnh ở cập nhật gần nút đã biết; bảng băm phù hợp cho truy cập theo khóa khi chấp nhận các giả định kỳ vọng; cây cân bằng hỗ trợ truy vấn có thứ tự; heap hiệu quả ở đầu ưu tiên; còn biểu diễn đồ thị phải lựa chọn theo mật độ cạnh và kiểu truy vấn. Khi đó, các con số O(1), O(log n), O(n) hay O(V+E) phản ánh đúng điều ứng dụng cần làm.
