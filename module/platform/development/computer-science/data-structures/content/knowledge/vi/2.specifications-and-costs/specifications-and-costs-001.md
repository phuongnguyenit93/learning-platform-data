# Đặc tả kiểu dữ liệu trừu tượng bằng tập phép toán

> **Chủ đề:** Đặc tả và chi phí · **Bài học:** Đặc tả kiểu dữ liệu trừu tượng bằng tập phép toán

Khi chọn cấu trúc dữ liệu, câu hỏi đầu tiên không phải là “dùng mảng hay danh sách liên kết?”, mà là **chương trình cần những thao tác nào và mỗi thao tác phải có ý nghĩa gì?** Một *kiểu dữ liệu trừu tượng* (Abstract Data Type, viết tắt **ADT**) trả lời câu hỏi đó bằng cách xác định tập giá trị/trạng thái có thể có và **hợp đồng hành vi của các phép toán** trên chúng. Cách tổ chức này giúp ta kiểm chứng tính đúng đắn trước khi quyết định cách lưu trữ và tối ưu thời gian, bộ nhớ.

Trong mô-đun Cấu trúc dữ liệu, tư duy đặc tả sẽ được dùng xuyên suốt khi học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị: hiểu **bất biến**, **thao tác**, **chi phí** rồi mới chọn biểu diễn phù hợp.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt **ADT**, **giao diện lập trình** (interface/API) và **cấu trúc dữ liệu triển khai**.
2. Viết đặc tả của một ADT qua miền trạng thái, phép toán, điều kiện trước/sau và cách xử lý đầu vào không hợp lệ.
3. Diễn đạt quy tắc LIFO, FIFO và quan hệ khóa–giá trị bằng các phép toán có thể kiểm tra.
4. Dùng một đặc tả để đối chiếu nhiều cách cài đặt mà không nhầm hành vi với độ phức tạp.

## 2. Đặc tả ADT gồm những gì?

Xét chức năng “hoàn tác thao tác” trong trình soạn thảo. Ta cần:

- Ghi lại thao tác mới nhất.
- Xem thao tác mới nhất mà không xóa nó.
- Lấy thao tác mới nhất ra khỏi lịch sử.
- Biết khi nào lịch sử trống.

Đây là yêu cầu về **hành vi** của một stack. Chưa có yêu cầu nào buộc ta dùng mảng, danh sách liên kết hay một vùng nhớ cụ thể.

Có thể mô tả một ADT dưới dạng:

```text
ADT = (miền giá trị/trạng thái, trạng thái ban đầu,
       tập phép toán, quy tắc hành vi, điều kiện hợp lệ)
```

Một bản đặc tả hữu ích cần nói rõ:

| Thành phần | Câu hỏi phải trả lời | Ví dụ với stack |
| --- | --- | --- |
| Miền giá trị/trạng thái | Đối tượng trừu tượng có thể chứa gì? | Một dãy hữu hạn phần tử kiểu `T` |
| Trạng thái ban đầu | Đối tượng mới có trạng thái nào? | Dãy rỗng `[]` |
| Tên và kiểu phép toán | Có thể gọi gì, với tham số nào, trả về gì? | `push(S, x) → S'` |
| Tiền điều kiện | Khi nào lời gọi có nghĩa/hợp lệ? | `pop` yêu cầu stack không rỗng |
| Hậu điều kiện | Kết quả và trạng thái sau lời gọi ra sao? | `push` thêm `x` vào đỉnh |
| Bất biến | Tính chất gì luôn phải đúng? | Thứ tự các phần tử còn lại được giữ nguyên |
| Xử lý lỗi | Nếu vi phạm tiền điều kiện thì sao? | Báo lỗi `EmptyStack`, hoặc quy ước khác được ghi rõ |

**Đặc tả** xác định cái gì phải đúng; **cài đặt** xác định làm thế nào để điều đó đúng. Một interface chỉ khai báo những thao tác có thể gọi, còn hợp đồng của ADT bổ sung ý nghĩa của chúng. Chẳng hạn, biết rằng `pop()` trả về một giá trị kiểu `T` vẫn chưa đủ để biết đó phải là phần tử vừa được thêm gần nhất.

### Trạng thái trừu tượng và bất biến biểu diễn

**Trạng thái trừu tượng** là mô hình để suy luận. Stack có thể được mô hình hóa bằng dãy `[a, b, c]`, trong đó `c` là đỉnh; mô hình này **không bắt buộc** chương trình phải lưu phần tử trong một mảng.

**Bất biến trừu tượng** là tính chất mọi trạng thái hợp lệ đều tuân theo, ví dụ kích thước stack là số nguyên không âm và các thao tác bảo toàn thứ tự của các phần tử chưa bị lấy ra. **Bất biến biểu diễn** lại phụ thuộc cài đặt: stack bằng mảng động có thể phải bảo đảm `0 ≤ size ≤ capacity`; stack bằng danh sách liên kết phải bảo đảm liên kết không tạo chu trình ngoài ý muốn. Đó là hai tầng cần phân biệt.

## 3. Quy trình đặc tả bằng tập phép toán

Một quy trình thực dụng gồm năm bước:

1. **Xác định đối tượng và trạng thái có thể quan sát.** Ví dụ stack có tập phần tử theo thứ tự vào/ra.
2. **Liệt kê phép tạo, phép truy vấn và phép cập nhật.** Phép truy vấn không thay đổi trạng thái; phép cập nhật tạo trạng thái mới về mặt mô hình.
3. **Ghi chữ ký phép toán** (tên, kiểu đầu vào và đầu ra); đặt tên sao cho không mơ hồ.
4. **Đặt hợp đồng:** tiền điều kiện, hậu điều kiện, trường hợp biên và lỗi. Chỉ rõ có cho phép phần tử trùng, giá trị `null`/`None` hay không nếu điều đó liên quan.
5. **Viết quy tắc và kiểm tra bằng ví dụ.** Nếu cùng một đầu vào hợp lệ có hai cách hiểu trái nhau, đặc tả còn thiếu.

Trong phần tiếp theo, các phép toán được mô tả dưới dạng **hàm trên trạng thái trừu tượng**: một thao tác cập nhật nhận trạng thái `S` và trả về trạng thái mới `S'`. API thực tế có thể thay đổi đối tượng tại chỗ (*mutable*) thay vì trả về đối tượng mới; hai hình thức này có thể hiện thực cùng một hợp đồng hành vi.

## 4. Ví dụ hoàn chỉnh: ADT Stack (ngăn xếp)

### 4.1. Miền trạng thái và chữ ký

Stack tuân theo **LIFO** (*Last In, First Out*): phần tử được thêm sau cùng sẽ được lấy ra trước tiên.

Gọi `T` là kiểu của phần tử, `S = [x₁, x₂, …, xₙ]` là trạng thái trừu tượng, `n ≥ 0`; phần tử ở cuối dãy là **đỉnh**. Stack mới có trạng thái `[]`.

| Phép toán | Chữ ký trừu tượng | Ý nghĩa |
| --- | --- | --- |
| `empty` | `() → Stack<T>` | Tạo stack rỗng |
| `isEmpty` | `(S) → Bool` | Kiểm tra stack rỗng |
| `size` | `(S) → Nat` | Số phần tử |
| `push` | `(S, x: T) → Stack<T>` | Thêm `x` lên đỉnh, trả về trạng thái mới |
| `peek` | `(S) → T` | Xem đỉnh, không thay đổi stack |
| `pop` | `(S) → (T, Stack<T>)` | Lấy phần tử đỉnh và trạng thái sau khi bỏ đỉnh |

Ở đây, kiểu `Nat` là tập số nguyên không âm. Trong nhiều thư viện, `pop()` trả về phần tử bị lấy ra **và sửa chính đối tượng stack**; cặp `(T, Stack<T>)` ở bảng là cách biểu diễn tường minh cả giá trị lẫn thay đổi trạng thái.

### 4.2. Tiền điều kiện, hậu điều kiện và trường hợp rỗng

Đặt `S ++ [x]` là dãy `S` nối thêm `x` vào cuối.

| Phép toán | Tiền điều kiện | Hậu điều kiện |
| --- | --- | --- |
| `empty()` | Không có | Trả về `[]` |
| `isEmpty(S)` | `S` hợp lệ | Trả về `true` khi và chỉ khi `size(S) = 0`; không đổi `S` |
| `size(S)` | `S` hợp lệ | Trả về độ dài của `S`; không đổi `S` |
| `push(S, x)` | `S` hợp lệ, `x` thuộc `T` | Trả về `S' = S ++ [x]` |
| `peek(S)` | `size(S) > 0` | Trả về phần tử cuối `S`; không đổi `S` |
| `pop(S)` | `size(S) > 0` | Với `S = P ++ [x]`, trả về `(x, P)` |

**Trường hợp lỗi:** Đặc tả này chọn quy ước `peek` và `pop` trên stack rỗng là **lời gọi không hợp lệ**, và API triển khai phải báo lỗi `EmptyStack`. Một thiết kế khác có thể trả về kiểu `Option<T>`, nhưng cần nói rõ ngay từ đầu và giữ nhất quán. Không được âm thầm trả về `null` nếu `null` cũng có thể là phần tử hợp lệ.

### 4.3. Các quy luật đặc trưng

Với mọi stack hợp lệ `S` và phần tử `x`:

```text
isEmpty(empty())             = true
size(empty())                = 0
isEmpty(push(S, x))          = false
size(push(S, x))             = size(S) + 1
peek(push(S, x))             = x
pop(push(S, x))              = (x, S)
```

Hai quy luật cuối thể hiện chính xác LIFO: `push` đặt `x` lên đỉnh; `peek` thấy `x`; `pop` trả `x` và khôi phục trạng thái trước khi đẩy `x`. Chúng không hề nhắc tới vị trí ô nhớ hay con trỏ.

Không được áp dụng `peek(empty())` hoặc `pop(empty())` vì các biểu thức đó vi phạm tiền điều kiện đã chọn.

### 4.4. Theo dấu một chuỗi thao tác

Giả sử hệ thống lưu các nhãn hành động `A` và `B`:

| Bước | Thao tác | Kết quả trả về | Stack sau bước |
| --- | --- | --- | --- |
| 0 | `S₀ = empty()` | Stack rỗng | `[]` |
| 1 | `S₁ = push(S₀, "A")` | `S₁` | `[A]` |
| 2 | `S₂ = push(S₁, "B")` | `S₂` | `[A, B]` |
| 3 | `peek(S₂)` | `B` | `[A, B]` |
| 4 | `pop(S₂)` | `(B, [A])` | `[A]` |
| 5 | `pop([A])` | `(A, [])` | `[]` |

Một cài đặt lấy `A` ra ở bước 4 là **sai đặc tả**, dù thời gian chạy rất nhanh.

### 4.5. Biến đặc tả thành hợp đồng API

Giả sử API theo phong cách hướng đối tượng cung cấp `push(x)`, `peek()`, `pop()` trên một đối tượng có thể thay đổi. Ta có thể phát biểu hợp đồng của `pop()` như sau:

```text
requires: size_before > 0
returns:  phần tử ở đỉnh của stack trước khi gọi
ensures:  size_after = size_before - 1
          thứ tự các phần tử còn lại được giữ nguyên
          đỉnh cũ không còn nằm trong stack sau lời gọi
on error: nếu stack rỗng, báo EmptyStack và không thay đổi trạng thái
```

Ký hiệu `before`/`after` nhắc ta kiểm tra cả **giá trị trả về** lẫn **tác dụng phụ**. Khi xây dựng bộ kiểm thử, đừng chỉ kiểm tra `pop()` đã trả gì; hãy kiểm tra tiếp nội dung stack sau phép toán.

## 5. So sánh với Queue: cùng các động từ, khác hợp đồng

Queue (hàng đợi) tuân theo **FIFO** (*First In, First Out*): phần tử được thêm trước được lấy trước. Mô hình trừu tượng cũng là một dãy, nhưng **đầu dãy** là nơi lấy ra.

| Phép toán | Chữ ký trừu tượng | Quy tắc |
| --- | --- | --- |
| `emptyQueue()` | `() → Queue<T>` | Tạo `[]` |
| `enqueue(Q, x)` | `(Q, T) → Queue<T>` | Trả về `Q ++ [x]` |
| `front(Q)` | `(Q) → T` | Với `Q = [a] ++ R`, trả `a` |
| `dequeue(Q)` | `(Q) → (T, Queue<T>)` | Với `Q = [a] ++ R`, trả `(a, R)` |
| `size(Q)` | `(Q) → Nat` | Trả về độ dài `Q` |

`front` và `dequeue` yêu cầu `Q` không rỗng. Đặc tả chọn cùng cách báo lỗi rõ ràng như stack khi điều kiện này bị vi phạm.

Ví dụ:

```text
Q0 = []
Q1 = enqueue(Q0, "Khách 1")    # [Khách 1]
Q2 = enqueue(Q1, "Khách 2")    # [Khách 1, Khách 2]

dequeue(Q2) = ("Khách 1", [Khách 2])
```

Sự khác biệt giữa stack và queue không nằm ở việc có hay không có một phép “thêm” và một phép “lấy”; nó nằm ở **hợp đồng về thứ tự**. Khi đặc tả nói FIFO, một cài đặt lấy từ cuối dãy sẽ không đúng cho dù hàm có tên `dequeue`.

## 6. Một kiểu ADT khác: Map (ánh xạ khóa–giá trị)

Stack và queue lưu các phần tử theo thứ tự. Map mô tả một quan hệ từ **khóa duy nhất** đến **giá trị**. Đây là hành vi mà bảng băm hoặc cây tìm kiếm có thể triển khai.

Gọi `K` là kiểu khóa, `V` là kiểu giá trị, `M` là một hàm từng phần từ `K` sang `V`. Nghĩa là mỗi khóa trong miền xác định của `M` có **đúng một giá trị**, còn khóa chưa được thêm thì chưa tồn tại.

Chọn `lookup` trả về kiểu `Option<V>` gồm `Some(value)` hoặc `None` để phân biệt khóa không tồn tại với một giá trị dữ liệu có thể rỗng.

| Phép toán | Chữ ký | Hợp đồng |
| --- | --- | --- |
| `emptyMap()` | `() → Map<K,V>` | Không chứa khóa nào |
| `put(M, k, v)` | `(M, K, V) → Map<K,V>` | Gán `k ↦ v`; ghi đè giá trị cũ của cùng khóa |
| `lookup(M, k)` | `(M, K) → Option<V>` | `Some(v)` nếu `k` đang ánh xạ tới `v`; ngược lại `None` |
| `contains(M, k)` | `(M, K) → Bool` | Cho biết `k` có tồn tại không |
| `remove(M, k)` | `(M, K) → Map<K,V>` | Bỏ ánh xạ của `k`; nếu không có thì giữ nguyên |
| `size(M)` | `(M) → Nat` | Số khóa khác nhau đang tồn tại |

Các quy luật quan trọng:

```text
lookup(emptyMap(), k) = None
lookup(put(M, k, v), k) = Some(v)

Với k2 khác k:
lookup(put(M, k, v), k2) = lookup(M, k2)

contains(put(M, k, v), k) = true
contains(remove(M, k), k) = false
```

Nếu `k` chưa tồn tại trong `M` thì `size(put(M,k,v)) = size(M) + 1`. Nếu `k` đã tồn tại, `put` chỉ cập nhật giá trị, **không tăng** kích thước.

Ví dụ: sau `put(emptyMap(), "ma_hoc_vien", 7)` rồi `put(M, "ma_hoc_vien", 9)`, Map có **một** khóa và `lookup` trả `Some(9)`.

**Điểm phải chốt trong đặc tả:** Thế nào là “cùng khóa”? Ta cần một quan hệ bằng nhau nhất quán trên kiểu `K`. Hash table phải thêm quy tắc băm phù hợp với quan hệ đó ở **tầng cài đặt**; bản thân ADT Map không yêu cầu sử dụng hàm băm và cũng không mặc định duy trì thứ tự chèn.

## 7. Từ đặc tả đến lựa chọn cấu trúc dữ liệu và chi phí

Nội dung chương **Đặc tả và chi phí** có hai câu hỏi liên tiếp:

1. **Đặc tả:** Kết quả nào được coi là đúng?
2. **Phân tích chi phí:** Cài đặt nào đạt kết quả đó với thời gian và bộ nhớ phù hợp?

Có thể cùng hiện thực một ADT bằng nhiều cấu trúc dữ liệu:

| ADT và thao tác | Lựa chọn cài đặt | Chi phí thời gian thường gặp | Điều kiện cần nhớ |
| --- | --- | --- | --- |
| Stack: `push`, `pop` đỉnh | Mảng động, đỉnh ở cuối | `pop`: O(1); `push`: O(1) khấu hao | Lần cấp phát lại có thể khiến một `push` tốn O(n) |
| Stack: `push`, `pop` đỉnh | Danh sách liên kết, đỉnh ở đầu | O(1) mỗi phép | Mỗi nút mang thêm thông tin liên kết |
| Queue: `enqueue`, `dequeue` | Mảng vòng có khả năng mở rộng | O(1) khấu hao | Phải quản lý chỉ số đầu/cuối; có thể tốn O(n) khi mở rộng |
| Queue: `enqueue`, `dequeue` | Danh sách liên kết có đầu và đuôi | O(1) mỗi phép | Cần cập nhật đúng cả hai tham chiếu khi rỗng |
| Map: `put`, `lookup`, `remove` | Bảng băm | O(1) kỳ vọng/trung bình trong điều kiện phù hợp | Va chạm và phân bố băm có thể gây trường hợp xấu O(n) |
| Map: `put`, `lookup`, `remove` | Cây tìm kiếm cân bằng | O(log n) trường hợp xấu | Cần quan hệ thứ tự nhất quán giữa các khóa |

Ở bảng trên, `n` là số phần tử/khóa, O(1) **khấu hao** nghĩa là chi phí trung bình mỗi thao tác xét trên một chuỗi đủ dài, mặc dù từng lần riêng lẻ có thể tốn hơn. Với bảng băm, O(1) không phải bảo đảm tuyệt đối cho mọi đầu vào; với cây cân bằng, khả năng bảo đảm O(log n) phụ thuộc việc giữ đúng bất biến cân bằng.

**Cùng hợp đồng, khác hiệu năng.** Stack dùng mảng động và stack dùng danh sách liên kết đều phải trả phần tử thêm gần nhất khi gọi `pop`. Độ phức tạp, cách quản lý bộ nhớ và tính liên tục của vùng nhớ quyết định lựa chọn triển khai, không thay đổi quy tắc LIFO.

Ngược lại, **khác hợp đồng có thể đòi một ADT khác**: hàng đợi ưu tiên lấy theo độ ưu tiên, không phải theo thứ tự đến như FIFO. Cài bằng heap thường phù hợp, nhưng heap là cấu trúc lưu trữ; hợp đồng của *priority queue* mới xác định phần tử nào phải được lấy trước và xử lý ra sao khi hai phần tử có cùng độ ưu tiên.

## 8. Kiểm tra đặc tả bằng phép thử hành vi

Từ các quy luật, ta tạo kiểm thử độc lập với cách cài đặt. Ví dụ với giao diện hàm trên trạng thái:

```python
s0 = empty()
assert size(s0) == 0
assert is_empty(s0)

s1 = push(s0, "A")
s2 = push(s1, "B")
assert peek(s2) == "B"
assert size(s2) == 2

item, s3 = pop(s2)
assert item == "B"
assert peek(s3) == "A"
assert size(s3) == 1
```

Đây là **mã kiểm thử minh họa hợp đồng**, không phải cài đặt stack. Với API mutable, hãy thay các lời gọi nhận/trả trạng thái bằng kiểm tra trạng thái của đối tượng sau mỗi thao tác.

Một cách kiểm thử mạnh hơn là kiểm tra **thuộc tính** trên nhiều dãy thao tác tự sinh:

- Với mọi `S, x` hợp lệ, `peek(push(S,x)) == x`.
- Với mọi `S, x` hợp lệ, `pop(push(S,x)) == (x,S)` theo mô hình trừu tượng.
- Với mọi `M, k, v` hợp lệ, `lookup(put(M,k,v),k) == Some(v)`.
- Với mọi `Q` không rỗng, `dequeue(Q)` phải trả phần tử được thêm sớm nhất còn chưa bị lấy.

Các thuộc tính này phát hiện lỗi về thứ tự, cập nhật dữ liệu và xử lý phần tử trùng lặp mà một vài ví dụ “đẹp” dễ bỏ sót.

### Kiểm thử trường hợp biên

Phải kiểm tra cả trường hợp tạo mới rồi gọi `pop`, gọi `peek` trên stack rỗng, xóa khóa không tồn tại, ghi đè khóa cũ, thêm nhiều phần tử giống nhau, hoặc liên tục chuyển từ rỗng sang không rỗng và ngược lại. Kết quả mong đợi phải xuất phát từ **quy ước đã ghi trong đặc tả**, không tự suy ra từ một thư viện tình cờ được dùng.

## 9. Những lỗi thường gặp khi viết đặc tả

| Lỗi | Vì sao gây vấn đề | Cách sửa |
| --- | --- | --- |
| Chỉ liệt kê `push`, `pop` mà không nói LIFO | Một cài đặt FIFO vẫn có thể mang cùng tên hàm | Viết quy tắc `pop(push(S,x)) = (x,S)` |
| Không quy định thao tác trên trạng thái rỗng | Mỗi cài đặt có thể báo lỗi hoặc trả kết quả khác nhau | Định nghĩa tiền điều kiện và hành vi lỗi |
| Dùng `null` làm dấu “không tồn tại” nhưng cho phép lưu `null` | Không phân biệt được hai trường hợp | Dùng `Option` hoặc trả thêm cờ tồn tại |
| Không nói thao tác có thay đổi trạng thái hay không | Người gọi khó dự đoán tác dụng phụ | Ghi rõ mô hình immutable/mutable và hậu điều kiện |
| Lẫn bất biến trừu tượng với bất biến cài đặt | Đặc tả bị gắn chặt vào một cấu trúc lưu trữ | Mô tả trạng thái bằng dãy/ánh xạ; để con trỏ, capacity cho cài đặt |
| Viết “lookup O(1)” như định nghĩa của Map | Cây cân bằng cũng có thể cài Map đúng | Đặt độ phức tạp ở phần yêu cầu hiệu năng hoặc phân tích cài đặt |
| Không xác định thứ tự hoặc cách xử lý phần tử bằng nhau | Kết quả ở các trường hợp biên không xác định | Nêu rõ quan hệ so sánh, thứ tự ổn định hay không ổn định |

## 10. Mẫu đặc tả có thể tái sử dụng

Khi gặp một ADT mới như Set, List, Deque, Priority Queue hoặc Graph, có thể dùng khung sau:

```text
Tên ADT:
Mục đích sử dụng:

1. Kiểu tham số và miền trạng thái trừu tượng:
2. Trạng thái ban đầu:
3. Bất biến trừu tượng:
4. Các phép toán:
   - tên(đầu vào) -> đầu ra
   - tiền điều kiện
   - hậu điều kiện / tác dụng lên trạng thái
   - hành vi khi không hợp lệ
5. Những quy luật phải đúng với mọi trạng thái hợp lệ:
6. Ví dụ chuỗi thao tác và kết quả kỳ vọng:
7. Yêu cầu phi chức năng (nếu có):
   - độ phức tạp mục tiêu
   - giới hạn bộ nhớ / dung lượng
   - yêu cầu đồng thời hay ổn định thứ tự
8. Những cách cài đặt ứng viên và chi phí:
```

Mục 7–8 **bổ sung tiêu chí kỹ thuật** để chọn giải pháp sau khi đã hiểu hành vi. Đừng lấy chi phí dự đoán của một cách cài đặt làm quy luật bắt buộc của ADT nếu bài toán không yêu cầu.

## 11. Bài tập vận dụng có đáp án gợi ý

**Bài 1 — Stack có dung lượng giới hạn.** Thiết kế `BoundedStack<T>` với sức chứa tối đa `C`. Tiền điều kiện của `push` là gì?

*Gợi ý:* Chọn `C ≥ 0`, duy trì `0 ≤ size(S) ≤ C`. `push(S,x)` chỉ hợp lệ nếu `size(S) < C`; nếu đầy thì báo `FullStack` và giữ nguyên trạng thái. `pop` vẫn yêu cầu không rỗng. Đây là ràng buộc mới của ADT, không phải chi tiết của một loại mảng.

**Bài 2 — Hàng đợi in tài liệu.** Sau khi thêm lần lượt `A`, `B`, `C` rồi lấy hai lần, kết quả nào là đúng?

*Gợi ý:* Với Queue FIFO, thứ tự lấy là `A` rồi `B`; hàng đợi còn `[C]`. Với Stack LIFO, thứ tự lại là `C` rồi `B`. Tập thao tác và quy tắc thứ tự quyết định kết quả.

**Bài 3 — Map và khóa trùng.** Nếu `M` rỗng, thực hiện `put(M,"x",1)`, sau đó `put(M,"x",2)`, rồi `remove(M,"y")`, hãy xác định `size` và `lookup("x")`.

*Gợi ý:* `size = 1`, `lookup("x") = Some(2)`. Khóa `"x"` được cập nhật, còn xóa khóa `"y"` không tồn tại không làm thay đổi Map theo hợp đồng đã chọn.

**Bài 4 — Đánh giá một cài đặt.** Một queue lưu trong mảng và mỗi lần `dequeue` lại dồn toàn bộ các phần tử còn lại về đầu mảng. Nó có đúng ADT không? Có hiệu quả không?

*Gợi ý:* Nếu luôn lấy phần tử vào sớm nhất và giữ đúng thứ tự, cài đặt **đúng hợp đồng FIFO**. Tuy nhiên, mỗi lần dồn `n-1` phần tử mất O(n) thời gian; mảng vòng hoặc danh sách liên kết có đầu/đuôi có thể đáp ứng cùng hợp đồng với chi phí tốt hơn.

## 12. Tự kiểm tra trước khi sang bài tiếp theo

Hãy tự trả lời ba câu hỏi:

1. Nếu chuyển stack từ mảng động sang danh sách liên kết, phần nào của đặc tả LIFO phải thay đổi? **Không phần nào**; chỉ cách biểu diễn và phân tích chi phí thay đổi.
2. Vì sao `peek` và `pop` cần tiền điều kiện? Vì trên stack rỗng không tồn tại đỉnh; đặc tả phải quy định lời gọi đó hợp lệ hay báo lỗi.
3. Vì sao chữ ký `get(key) → Value` chưa đủ để đặc tả một Map? Vì chưa rõ hành vi khi khóa vắng mặt, giá trị trả về, cách so sánh khóa và tác dụng phụ.

Khi bạn có thể viết **phép toán + quy tắc + trường hợp biên** mà không đụng tới mảng hay con trỏ, bạn đã đặc tả được một ADT ở mức đủ rõ để triển khai, kiểm thử và sau đó so sánh độ phức tạp của các cấu trúc dữ liệu ứng viên.
