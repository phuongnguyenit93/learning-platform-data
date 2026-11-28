# Kiểu dữ liệu trừu tượng hàng đợi ưu tiên và khóa ưu tiên

Trong một **hàng đợi thông thường** (*queue*), phần tử được lấy ra theo thứ tự vào trước, ra trước (**FIFO**). Nhưng nhiều hệ thống cần phục vụ phần tử **quan trọng nhất** hoặc **đến hạn sớm nhất**, thay vì phục vụ phần tử đến trước. Cấu trúc mô tả nhu cầu ấy là **hàng đợi ưu tiên** (*priority queue*).

Ví dụ, một ứng dụng có ba công việc:

| Thứ tự đến | Công việc | Mức ưu tiên (số nhỏ hơn là ưu tiên hơn) |
| ---: | --- | ---: |
| 1 | Tạo báo cáo định kỳ | 4 |
| 2 | Khôi phục dịch vụ bị lỗi | 1 |
| 3 | Gửi thông báo | 3 |

Hàng đợi FIFO xử lý theo thứ tự **báo cáo → khôi phục → thông báo**. Một **min-priority queue** lại lấy **khôi phục → thông báo → báo cáo**, bởi phần tử có **khóa ưu tiên nhỏ nhất** được chọn trước.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu của mô-đun là hiểu bất biến, thao tác, độ phức tạp thời gian/bộ nhớ của các cấu trúc từ mảng và danh sách liên kết đến cây, heap và đồ thị. Vì vậy, trước khi học kỹ về heap, ta cần phân biệt **kiểu dữ liệu trừu tượng** cần cung cấp những gì với **cấu trúc dữ liệu cụ thể** được dùng để triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Định nghĩa **priority queue** như một **kiểu dữ liệu trừu tượng (ADT)** gồm tập phần tử, quy tắc chọn phần tử và các thao tác.
- Phân biệt **khóa ưu tiên (priority key)**, **dữ liệu công việc (payload)**, **định danh công việc (ID)** và **thứ tự thêm vào**.
- Mô tả hợp đồng **insert/push**, **peek/min**, **extract_min/pop**, **is_empty**, **size** và những thao tác mở rộng như **change_priority**.
- Giải thích hai biến thể **min-priority queue** và **max-priority queue**.
- Phân tích cách xử lý **khóa bằng nhau**, tính ổn định (*stability*) và nguy cơ so sánh payload ngoài ý muốn.
- Lựa chọn cài đặt bằng danh sách chưa sắp xếp, danh sách đã sắp xếp hoặc **binary heap** theo đặc điểm tải công việc.
- Sử dụng **heapq** của Python để triển khai hàng đợi ưu tiên tối thiểu có xử lý hòa ưu tiên theo thứ tự đến.
- Phân biệt thao tác cập nhật khóa với việc sửa trực tiếp một đối tượng đang nằm trong heap.
- Ước lượng độ phức tạp, nhận diện tình huống **starvation** và áp dụng cho lập lịch, mô phỏng sự kiện hoặc thuật toán đồ thị.

## 2. Kiểu dữ liệu trừu tượng khác với cách lưu trữ

**Kiểu dữ liệu trừu tượng (abstract data type, ADT)** mô tả những hành vi mà người dùng có thể quan sát:

- Phần tử nào có thể được thêm vào?
- Khi yêu cầu lấy phần tử tiếp theo, phần tử nào được chọn?
- Các thao tác có làm thay đổi trạng thái không?
- Kết quả và lỗi ở trạng thái rỗng là gì?

ADT **không bắt buộc** phải dùng một cách lưu trữ cụ thể.

Hàng đợi ưu tiên có thể được cài đặt bằng **mảng**, **danh sách liên kết**, **mảng đã sắp xếp**, **cây tìm kiếm cân bằng** hoặc **heap**. Các cách ấy có thể cho cùng kết quả ở mức ADT nhưng khác nhau về thời gian thực thi và bộ nhớ.

### 2.1. Trạng thái trừu tượng

Ta xem hàng đợi ưu tiên là một tập hợp **các lần xuất hiện của phần tử**, trong đó mỗi lần xuất hiện có ít nhất:

~~~text
entry = (priority_key, payload)
~~~

Ví dụ:

~~~text
(1, "Khôi phục dịch vụ")
(4, "Tạo báo cáo")
(3, "Gửi thông báo")
~~~

Cần dùng khái niệm **các lần xuất hiện** thay vì tập hợp toán học không trùng lặp: cùng một công việc hoặc cùng một mức ưu tiên có thể được thêm nhiều lần. Hai bản ghi giống nhau không đương nhiên bị loại bỏ.

Với **min-priority queue**, khi không rỗng, thao tác lấy phần tử tiếp theo chọn một entry có **priority_key nhỏ nhất** trong tất cả entry đang chờ.

Với **max-priority queue**, thao tác ấy chọn một entry có **priority_key lớn nhất**.

**Khóa ưu tiên không nhất thiết là ID hay payload.** Khóa có thể là số nguyên mức ưu tiên, thời điểm hết hạn, chi phí ước lượng hoặc một bộ giá trị được so sánh theo quy tắc định trước.

### 2.2. ADT khác binary heap

**Binary heap** là một cấu trúc cây nhị phân gần đầy đủ thường lưu trong mảng và duy trì một quan hệ thứ tự giữa cha và con. Nó là **một cách triển khai** priority queue, không phải đồng nghĩa với priority queue.

~~~text
HỢP ĐỒNG ADT
  push(key, data)
  peek()
  pop()
  size()
      │
      ├── Danh sách chưa sắp xếp
      ├── Danh sách đã sắp xếp
      ├── Cây tìm kiếm cân bằng
      └── Binary heap
~~~

Khi xét “priority queue hỗ trợ pop” là đang nói về **hành vi**; khi xét “sift-up, sift-down, chỉ số con trái/phải” là đang nói về **chi tiết triển khai bằng heap**.

## 3. Khóa ưu tiên và ý nghĩa của thứ tự

### 3.1. Khóa là căn cứ chọn phần tử

Ví dụ một công việc có dữ liệu:

~~~text
id       = "ticket-135"
title    = "Xử lý sự cố truy cập"
priority = 1
owner    = "Nhóm vận hành"
~~~

Priority queue không cần so sánh tiêu đề hoặc người phụ trách nếu **priority = 1** đã là khóa cần dùng. Tách khóa khỏi payload giúp quy tắc xử lý rõ ràng.

Nếu dùng min-priority queue với khóa số nguyên:

~~~text
priority = 1: ưu tiên cao
priority = 2: ưu tiên trung bình
priority = 3: ưu tiên thấp
~~~

Số **nhỏ hơn** được lấy trước. Đây là **quy ước của ứng dụng**, không phải quy luật bắt buộc của mọi priority queue. Một ứng dụng khác có thể quy ước điểm cao hơn nghĩa là ưu tiên hơn và chọn max-priority queue.

### 3.2. Khóa phải có phép so sánh phù hợp

Để xác định phần tử “ưu tiên hơn”, chương trình cần một **quan hệ thứ tự nhất quán** trên khóa:

- **Tính nhất quán:** kết quả so sánh không thay đổi tùy ý giữa các lần gọi.
- **Tính bắc cầu:** nếu a ưu tiên trước b và b trước c, thì a phải ưu tiên trước c.
- **Xử lý được hai khóa bằng nhau:** có thể trả lời hai entry có cùng mức ưu tiên hay không.
- **Kiểu dữ liệu có thể so sánh với nhau:** các giá trị khóa được đưa vào cùng hàng đợi phải hỗ trợ cách so sánh mà cài đặt sử dụng.

Ví dụ so sánh số nguyên 1, 2, 3 tương đối dễ. Nhưng nếu dùng hỗn hợp số và chuỗi trong một heap Python, những phép so sánh có thể gây **TypeError**. Khóa dạng số thực đặc biệt như **NaN** cũng có thể làm mất tính chất thứ tự mong đợi; không nên đưa vào mà không có quy tắc xử lý riêng.

### 3.3. Khóa phức hợp (composite key)

Đôi khi một yếu tố chưa đủ. Giả sử hệ thống phục vụ:

1. Công việc có **deadline sớm hơn** trước.
2. Nếu deadline bằng nhau, công việc có **mức khẩn cấp lớn hơn** trước.

Có thể dùng một khóa tuple:

~~~text
key = (deadline_timestamp, -urgency_score)
~~~

Khi so sánh **theo từ điển** (*lexicographic order*):

- Thành phần deadline được so sánh trước.
- Nếu deadline bằng nhau, số âm của urgency nhỏ hơn khi urgency lớn hơn.

Ví dụ:

~~~text
(100, -9) ưu tiên hơn (100, -3)
(100, -3) ưu tiên hơn (120, -10)
~~~

Bởi deadline được ưu tiên trước urgency.

**Lưu ý:** Đó là ví dụ với deadline/urgency dạng số. Nếu các thành phần cần quy tắc so sánh khác hoặc có giá trị thiếu, hãy định nghĩa hàm ánh xạ sang khóa hợp lệ thay vì mặc định tuple sẽ xử lý mọi trường hợp.

## 4. Min-priority queue và max-priority queue

Hai biến thể thường gặp chỉ khác quy tắc lựa chọn.

| Đặc điểm | Min-priority queue | Max-priority queue |
| --- | --- | --- |
| Phần tử được chọn | Khóa **nhỏ nhất** | Khóa **lớn nhất** |
| Thao tác thường dùng | find_min, extract_min | find_max, extract_max |
| Ví dụ khóa | Deadline sớm nhất | Điểm đánh giá cao nhất |
| Quan hệ trong min/max heap | Cha ≤ con | Cha ≥ con |
| Độ phức tạp với binary heap | Peek O(1), pop O(log n) | Peek O(1), pop O(log n) |

Ví dụ khóa [8, 3, 5, 1]:

~~~text
Min-priority queue lấy ra: 1, 3, 5, 8
Max-priority queue lấy ra: 8, 5, 3, 1
~~~

Để chuyển từ min sang max cho **khóa số**, một kỹ thuật thường gặp trong Python là lưu **-priority** trong min-heap. Nhưng đó chỉ là mẹo mã hóa; cần khôi phục dấu khi trả kết quả và chú ý nếu khóa là tuple, chuỗi, kiểu tùy chỉnh hoặc không hỗ trợ phép lấy đối.

**Không có biến thể nào “đúng hơn” trong mọi tình huống.** Quy ước khóa phải phù hợp nghĩa nghiệp vụ. Nếu số 1 biểu thị công việc khẩn cấp nhất thì min-priority queue thích hợp; nếu 100 điểm là quan trọng nhất thì max-priority queue có thể tự nhiên hơn.

## 5. Hợp đồng thao tác của ADT

Chọn **min-priority queue** làm ví dụ và quy ước mỗi lần thêm là một phần tử riêng biệt.

| Thao tác | Tiền điều kiện | Kết quả và tác động |
| --- | --- | --- |
| **insert(key, payload)** hoặc **push** | Khóa hợp lệ | Thêm một entry; tăng số phần tử lên 1 |
| **find_min() / peek()** | Không rỗng | Trả entry có khóa nhỏ nhất; **không xóa** |
| **extract_min() / pop()** | Không rỗng | Trả và loại bỏ một entry có khóa nhỏ nhất |
| **is_empty()** | Không có | Cho biết hàng đợi có phần tử chờ hay không |
| **size()** | Không có | Số entry hiện còn trong hàng đợi |
| **clear()** *(tùy chọn)* | Không có | Loại bỏ mọi entry |
| **change_priority(handle, key)** *(tùy chọn)* | Handle hợp lệ, entry còn tồn tại | Đổi khóa của một entry |
| **remove(handle)** *(tùy chọn)* | Handle hợp lệ | Xóa đúng entry được định danh |

Hai thao tác cuối **không bắt buộc** có trong mọi priority queue. Nếu API không hỗ trợ cập nhật khóa, người dùng có thể cần phương pháp khác như thêm phiên bản mới và bỏ qua bản cũ khi lấy ra.

### 5.1. Điều gì xảy ra khi rỗng?

Một ADT cần quy định rõ cách trả kết quả khi gọi peek/pop trên hàng đợi rỗng. Các lựa chọn có thể là:

- Ném ngoại lệ (ví dụ **IndexError** trong Python).
- Trả một kiểu kết quả có trạng thái (**Option / Result**).
- Trả **(success, value)** để phân biệt thành công và thất bại.

Không nên tự dùng **None** như dấu hiệu rỗng nếu payload hợp lệ cũng có thể là None; nếu cần, hãy dùng một đối tượng đánh dấu riêng hoặc trạng thái trả về rõ ràng.

### 5.2. Peek khác pop

Với các entry:

~~~text
(2, "A"), (1, "B"), (3, "C")
~~~

Kết quả:

~~~text
peek() → (1, "B")     hàng đợi vẫn có 3 entry
peek() → (1, "B")     vẫn không xóa
pop()  → (1, "B")     chỉ còn 2 entry
peek() → (2, "A")     entry nhỏ nhất còn lại
~~~

Nhìn vào kết quả trả về thôi chưa đủ: phải kiểm tra cả **trạng thái sau thao tác** để biết implement đúng hợp đồng.

### 5.3. Bất biến trừu tượng

Dù dùng mảng hay heap, một priority queue đúng cần bảo đảm:

1. Mỗi lần push thành công thêm đúng **một lần xuất hiện**.
2. Mỗi lần pop thành công lấy một entry có khóa ưu tiên nhất theo quy ước.
3. Peek không thay đổi tập entry.
4. Không có entry bị nhân đôi hoặc thất lạc ngoài những thao tác được phép.
5. Size bằng số entry còn chờ.
6. Với khóa bằng nhau, hành vi phải phù hợp **quy định về hòa ưu tiên** của API.

Bất biến này là **bất biến hành vi ADT**, khác với bất biến **cha/con** bên trong một binary heap.

## 6. Khóa bằng nhau và tính ổn định

Giả sử ba công việc cùng có khóa ưu tiên 2:

~~~text
Lần đến 1: (2, "A")
Lần đến 2: (2, "B")
Lần đến 3: (2, "C")
~~~

Hợp đồng **min-priority queue cơ bản** chỉ bắt buộc pop trả entry có khóa nhỏ nhất. Nếu tất cả cùng khóa 2, một trong A, B, C đều thỏa yêu cầu chọn khóa nhỏ nhất.

Nếu ứng dụng muốn **A → B → C** theo thứ tự thêm, nó yêu cầu **tính ổn định** (*stable priority queue*). Tính ổn định **không mặc nhiên là thuộc tính của mọi heap**.

### 6.1. Dùng số thứ tự tăng dần

Đưa thêm một số **sequence_number** tăng dần theo mỗi lần push:

~~~text
(priority, sequence_number, payload)

(2, 0, "A")
(2, 1, "B")
(2, 2, "C")
~~~

Khi so sánh theo tuple trong Python, thứ tự là:

1. Khóa ưu tiên thấp hơn đứng trước.
2. Nếu khóa bằng nhau, sequence nhỏ hơn đứng trước.
3. Payload **không cần tham gia so sánh**, vì sequence của mỗi lần thêm là duy nhất.

Nhờ vậy, trong cùng mức ưu tiên, hàng đợi hoạt động giống FIFO.

### 6.2. Vì sao không chỉ lưu (priority, payload)?

Giả sử payload là một đối tượng **Task** không cài đặt phép so sánh thứ tự. Nếu lưu:

~~~python
heapq.heappush(heap, (2, task_a))
heapq.heappush(heap, (2, task_b))
~~~

Khi hai khóa 2 bằng nhau, Python có thể thử so sánh **task_a** với **task_b** để quyết định thứ tự tuple; nếu Task không hỗ trợ so sánh, sẽ gây lỗi **TypeError**.

Mẫu **(priority, sequence, payload)** tránh buộc so sánh payload trong trường hợp cùng ưu tiên.

### 6.3. Tính ổn định không giống bảo đảm công bằng

Thứ tự FIFO **trong cùng mức ưu tiên** không đảm bảo mọi công việc đều được xử lý. Nếu liên tục xuất hiện công việc khóa 1, một công việc khóa 5 có thể phải chờ mãi. Đó là tình huống **starvation** (*bị đói tài nguyên*). Các cơ chế như **aging** (tăng độ ưu tiên theo thời gian chờ), hạn mức công việc hoặc lập lịch luân phiên giữa các mức có thể cần thiết theo yêu cầu ứng dụng.

## 7. So sánh priority queue với queue và stack

Ba ADT đều hỗ trợ thêm và lấy phần tử, nhưng quy tắc lấy khác nhau.

| Cấu trúc | Quy tắc lấy | Ví dụ lần thêm | Thứ tự lấy |
| --- | --- | --- | --- |
| **Queue (FIFO)** | Vào trước ra trước | A, B, C | A, B, C |
| **Stack (LIFO)** | Vào sau ra trước | A, B, C | C, B, A |
| **Min-priority queue** | Khóa nhỏ nhất trước | A:3, B:1, C:2 | B, C, A |
| **Max-priority queue** | Khóa lớn nhất trước | A:3, B:1, C:2 | A, C, B |

**Đừng suy luận thứ tự ưu tiên theo thời điểm đến** nếu ứng dụng chưa quy định tie-breaking. FIFO và LIFO là thành phần định nghĩa của queue/stack; còn priority queue có thể xử lý các entry khóa bằng nhau theo chính sách riêng.

### Một ví dụ giúp phân biệt

~~~text
Thời điểm t0: thêm A (priority 5)
Thời điểm t1: thêm B (priority 2)
Thời điểm t2: thêm C (priority 4)
Thời điểm t3: pop()
~~~

Min-priority queue sẽ trả **B**, dù B không phải công việc đến sớm nhất hoặc muộn nhất.

Nếu sau mỗi lần pop có một lần push công việc khẩn cấp hơn, thứ tự lấy tiếp theo phụ thuộc **toàn bộ trạng thái hiện tại**, không phải một danh sách kết quả đã cố định khi khởi tạo.

## 8. Bất biến và cách lưu bằng heap

Một **binary min-heap** thường được lưu trong một mảng **a** và duy trì:

- **Hình dạng:** biểu diễn một cây nhị phân **gần đầy đủ**; mọi tầng trừ tầng cuối đầy đủ, tầng cuối điền từ trái sang phải.
- **Thứ tự heap:** mỗi nút cha có khóa **không lớn hơn** khóa ở các nút con trực tiếp.

Ví dụ:

~~~text
           1
         /   \
        3     2
       / \   /
      8   4 6

Mảng theo thứ tự mức:
[1, 3, 2, 8, 4, 6]
~~~

Nếu chỉ số mảng bắt đầu từ 0:

~~~text
parent(i)      = (i - 1) // 2     (với i > 0)
left_child(i)  = 2 * i + 1
right_child(i) = 2 * i + 2
~~~

**Điều quan trọng:** Heap **không bắt buộc toàn bộ mảng được sắp xếp**. Trong ví dụ, 3 đứng trước 2 trên mảng, nhưng vẫn là min-heap vì mỗi cha ≤ các con trực tiếp của nó.

Bất biến heap chỉ bảo đảm **phần tử nhỏ nhất nằm ở gốc** (a[0]), nhờ vậy peek O(1). Nó không bảo đảm có thể đọc phần tử nhỏ thứ hai bằng a[1] mà không xét các ứng viên khác.

### Vì sao insert và pop là O(log n)?

Khi thêm một entry:

1. Đưa entry vào cuối mảng để giữ hình dạng cây gần đầy đủ.
2. Nếu khóa nhỏ hơn cha, hoán đổi lên trên (*sift-up*).
3. Dừng khi quan hệ cha/con hợp lệ.

Khi lấy phần tử nhỏ nhất:

1. Lấy gốc làm kết quả.
2. Đưa phần tử cuối lên vị trí gốc rồi loại bỏ vị trí cuối cũ.
3. Hoán đổi xuống dưới với nút con phù hợp (*sift-down*) tới khi heap hợp lệ.

Chiều cao của binary heap có n nút là **Θ(log n)** khi n đủ lớn. Mỗi thao tác sửa trên một đường từ gốc đến lá hoặc ngược lại dùng tối đa O(log n) mức.

**Xây heap từ một mảng n entry bằng heapify từ dưới lên có thể là Θ(n)**, không phải Θ(n log n). Kết luận này đến từ việc phần lớn nút nằm gần lá và chỉ cần sửa rất ít tầng.

## 9. Cài đặt priority queue ổn định bằng Python heapq

Python cung cấp thư viện chuẩn **heapq**, triển khai các thao tác cho **min-heap trên một list**. Thư viện này không tự đóng gói một lớp priority queue với mọi tính năng; ta có thể viết lớp bọc thực hiện hợp đồng ADT.

Ví dụ sau chọn quy ước **số priority càng nhỏ càng ưu tiên**, và sử dụng sequence tăng dần để bảo toàn FIFO khi khóa bằng nhau.

~~~python
import heapq
from itertools import count


class StableMinPriorityQueue:
    def __init__(self):
        self._heap = []
        self._sequence = count()

    def push(self, priority: int, payload):
        seq = next(self._sequence)
        entry = (priority, seq, payload)
        heapq.heappush(self._heap, entry)

    def peek(self):
        if not self._heap:
            raise IndexError("Hàng đợi ưu tiên rỗng")
        priority, _seq, payload = self._heap[0]
        return priority, payload

    def pop(self):
        if not self._heap:
            raise IndexError("Hàng đợi ưu tiên rỗng")
        priority, _seq, payload = heapq.heappop(self._heap)
        return priority, payload

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def __len__(self) -> int:
        return len(self._heap)


pq = StableMinPriorityQueue()

pq.push(3, "Gửi thông báo")
pq.push(1, "Khôi phục dịch vụ")
pq.push(1, "Xử lý cảnh báo tiếp theo")
pq.push(2, "Kiểm tra nhật ký")

assert len(pq) == 4
assert pq.peek() == (1, "Khôi phục dịch vụ")
assert len(pq) == 4           # peek không xóa.

assert pq.pop() == (1, "Khôi phục dịch vụ")
assert pq.pop() == (1, "Xử lý cảnh báo tiếp theo")
assert pq.pop() == (2, "Kiểm tra nhật ký")
assert pq.pop() == (3, "Gửi thông báo")

assert pq.is_empty()
assert len(pq) == 0

try:
    pq.pop()
except IndexError:
    pass
else:
    raise AssertionError("Phải báo lỗi khi pop hàng đợi rỗng")
~~~

### 9.1. Vì sao trình tự pop ở trên đúng?

Trên tập entry có khóa [3, 1, 1, 2]:

- Hai entry có khóa 1 được lấy trước.
- Giữa hai entry khóa 1, entry được thêm sớm hơn có sequence nhỏ hơn nên được chọn trước.
- Sau đó tới khóa 2, cuối cùng tới khóa 3.

Hàm **peek** không thay đổi heap; **pop** loại bỏ một entry. Khi pop hết, hàng đợi rỗng.

### 9.2. Payload có thể không so sánh được

Để thấy sequence thực sự có ích, thử payload là các đối tượng tùy chỉnh không định nghĩa phép so sánh:

~~~python
class Task:
    def __init__(self, title):
        self.title = title


queue = StableMinPriorityQueue()
first = Task("A")
second = Task("B")

queue.push(5, first)
queue.push(5, second)

assert queue.pop()[1] is first
assert queue.pop()[1] is second
~~~

Ở đây Python không cần so sánh hai đối tượng Task vì sequence là duy nhất. Mỗi thao tác push/pop dùng O(log n) thời gian, peek O(1); hàm **len** và is_empty O(1).

### 9.3. Nếu muốn max-priority queue

Với **khóa số hữu hạn** và quy tắc “số lớn hơn ưu tiên hơn”, có thể lưu **-priority** thay cho priority trong một min-heap. Khi đọc kết quả cần đổi dấu trở lại. Ví dụ:

~~~python
max_heap = []
heapq.heappush(max_heap, (-100, 0, "A"))
heapq.heappush(max_heap, (-200, 1, "B"))
heapq.heappush(max_heap, (-150, 2, "C"))

negative_priority, _seq, payload = heapq.heappop(max_heap)
assert (-negative_priority, payload) == (200, "B")
~~~

Ví dụ dùng sequence riêng để tránh so sánh payload khi khóa bằng nhau. Mẹo dấu âm áp dụng cho khóa số; với các kiểu khóa khác cần quy tắc so sánh hoặc một cài đặt max-heap phù hợp.

## 10. Không dùng heap vẫn có thể triển khai cùng ADT

ADT priority queue không bắt buộc phải dùng heap. Có thể bắt đầu bằng một list chưa sắp xếp:

- **push**: thêm vào cuối list, thường O(1) trung bình khấu hao.
- **peek**: quét toàn bộ list tìm khóa nhỏ nhất, Θ(n).
- **pop**: tìm khóa nhỏ nhất và xóa entry, Θ(n) trong trường hợp xấu nhất.

Đây là cài đặt dễ hiểu và hữu ích khi số phần tử ít hoặc phần lớn thao tác là thêm, rất ít khi lấy phần tử ưu tiên.

### 10.1. Ví dụ tham chiếu bằng list chưa sắp xếp

Để so sánh với heap, cài đặt dùng sequence tương tự nhằm giữ thứ tự ổn định giữa các khóa bằng nhau.

~~~python
from itertools import count


class UnsortedMinPriorityQueue:
    def __init__(self):
        self._items = []
        self._sequence = count()

    def push(self, priority: int, payload):
        self._items.append((priority, next(self._sequence), payload))

    def _best_index(self) -> int:
        if not self._items:
            raise IndexError("Hàng đợi ưu tiên rỗng")
        return min(
            range(len(self._items)),
            key=lambda i: (self._items[i][0], self._items[i][1]),
        )

    def peek(self):
        priority, _seq, payload = self._items[self._best_index()]
        return priority, payload

    def pop(self):
        index = self._best_index()
        priority, _seq, payload = self._items.pop(index)
        return priority, payload

    def __len__(self):
        return len(self._items)


slow_queue = UnsortedMinPriorityQueue()
slow_queue.push(4, "A")
slow_queue.push(2, "B")
slow_queue.push(2, "C")
slow_queue.push(1, "D")

assert slow_queue.peek() == (1, "D")
assert slow_queue.pop() == (1, "D")
assert slow_queue.pop() == (2, "B")
assert slow_queue.pop() == (2, "C")
assert slow_queue.pop() == (4, "A")
assert len(slow_queue) == 0
~~~

Trong phương thức pop, **tìm best_index** đã mất Θ(n) ở trường hợp phổ biến; thao tác **list.pop(index)** có thể dịch nhiều phần tử và mất thêm O(n). Tổng thể vẫn là **Θ(n)** trong trường hợp xấu nhất, không phải Θ(n²) cho một lần pop.

### 10.2. Nếu giữ list đã sắp xếp?

Có thể lưu các entry theo thứ tự **giảm dần** để phần tử nhỏ nhất nằm ở **cuối list**:

~~~text
List: [key 8, key 6, key 3, key 1]
                                  ▲
                              min ở cuối
~~~

Khi đó:

- Peek phần tử cuối: Θ(1).
- Pop phần tử cuối: Θ(1).
- Insert cần tìm vị trí và dịch các phần tử: O(n) trong trường hợp xấu nhất.

Lựa chọn này phù hợp khi đọc/lấy phần tử ưu tiên xảy ra rất nhiều so với số lần thêm. Nhưng nó không làm mọi thao tác O(1); công việc sắp thứ tự đã được chuyển sang lúc insert.

### 10.3. Bảng so sánh các cài đặt

| Cấu trúc | Push | Peek min | Pop min | Xây từ n entry | Bộ nhớ |
| --- | --- | --- | --- | --- | --- |
| List chưa sắp xếp | O(1) khấu hao | O(n) | O(n) | O(n) bằng append | O(n) |
| List sắp xếp, min ở cuối | O(n) | O(1) | O(1) | O(n log n) bằng sort so sánh | O(n) |
| Binary min-heap | O(log n) | O(1) | O(log n) | **O(n)** bằng bottom-up heapify | O(n) |
| Cây tìm kiếm cân bằng (kèm xử lý khóa trùng) | O(log n) | O(log n) tìm min, có thể O(1) nếu giữ trỏ min | O(log n) | O(n log n) bằng chèn lần lượt | O(n) |

Các chi phí là mô hình thường gặp khi phép so sánh khóa là O(1); các chi tiết phụ thuộc cài đặt. Ví dụ, chi phí push trên list chưa sắp xếp là O(1) **khấu hao**, không phải một chặn trên tuyệt đối cho mọi lần mở rộng vùng nhớ.

**Heap thường cân bằng tốt** khi hệ thống liên tục trộn push và pop, nhưng không phải luôn là lựa chọn tốt nhất. Hãy chọn theo tần suất thao tác và các yêu cầu mở rộng như cập nhật khóa hoặc duyệt theo thứ tự.

## 11. Thay đổi độ ưu tiên và định danh entry

Một hàng đợi ưu tiên thực tế có thể cần thay đổi khóa của một công việc đang chờ:

~~~text
Công việc "ticket-135":
priority cũ = 5
priority mới = 1  (khẩn cấp hơn)
~~~

Về mặt ADT, ta có thể muốn **change_priority(handle, 1)**. Tuy nhiên, để cập nhật **đúng entry**, cần một **handle/ID duy nhất**, vì nhiều công việc có thể cùng payload hoặc cùng priority.

### 11.1. Giảm khóa và tăng khóa trong min-heap

Nếu đã biết **vị trí index** của entry trong heap và dùng min-heap:

- Khi **giảm khóa** (*decrease-key*), entry có thể cần đi **lên** bằng sift-up.
- Khi **tăng khóa** (*increase-key*), entry có thể cần đi **xuống** bằng sift-down.

Mỗi hướng sửa thường tốn **O(log n)** vì chiều cao heap là O(log n). Nhưng muốn tìm entry theo ID, có thể cần thêm một **bảng băm ánh xạ ID → vị trí heap** và cập nhật bảng băm mỗi khi hoán đổi các entry.

Chỉ nói “change_priority O(log n)” là chưa đủ nếu cài đặt chưa giải quyết bài toán định vị entry.

### 11.2. Vì sao không sửa trực tiếp priority bên trong payload?

Giả sử heap lưu khóa bằng cách đọc **task.priority**, và một thành phần khác làm:

~~~python
task.priority = 1
~~~

Nếu heap đã được tổ chức theo giá trị cũ, việc đổi trường trong đối tượng **không tự chạy sift-up/sift-down**. Bất biến thứ tự cha/con có thể không còn đúng. Một lần peek/pop tiếp theo có thể không trả entry mà ứng dụng nghĩ là ưu tiên cao nhất.

**Quy tắc an toàn:** thay đổi khóa phải đi qua một API có khả năng **sửa cấu trúc** hoặc tuân theo quy trình đánh dấu entry cũ không hợp lệ rồi thêm entry mới.

### 11.3. Cách thêm phiên bản mới và bỏ qua bản cũ

Nếu dùng Python **heapq** cơ bản, một kỹ thuật là:

1. Mỗi công việc có **ID** hoặc handle riêng.
2. Duy trì bản ghi **phiên bản mới nhất** hoặc trạng thái active/inactive của ID đó.
3. Khi đổi khóa, thêm một entry mới với khóa mới; đánh dấu entry cũ là **stale** (không còn hiệu lực).
4. Khi peek/pop, bỏ qua các entry stale trước khi trả kết quả.

Lưu ý:

- Heap có thể chứa **nhiều bản ghi vật lý** cho cùng một công việc; **size logic** và **len(heap)** có thể khác nhau.
- Bước làm sạch stale có thể khiến **một lần peek** phải bỏ nhiều entry trước khi tìm được entry hợp lệ, nên không thể tuyên bố mọi peek O(1) cho cài đặt lazy.
- Tổng số entry lưu trong heap có thể lớn hơn số công việc còn hiệu lực; đôi khi cần xây lại heap để thu hồi phần tử stale.
- Khi thay đổi khóa, chính sách giữ nguyên thứ tự đến hay cấp sequence mới phải được quy định. Đó là một quyết định về **ổn định/công bằng**, không phải chi tiết không quan trọng.

Trong các thuật toán đường đi ngắn như **Dijkstra** (khi trọng số cạnh không âm), có thể dùng decrease-key với handle hoặc thêm entry mới và bỏ qua entry lỗi thời nếu có kiểm tra khoảng cách hiện tại. Hai cách có yêu cầu và chi phí triển khai khác nhau.

## 12. Khóa ưu tiên, dữ liệu trùng nhau và hợp đồng so sánh

### 12.1. Khóa trùng không có nghĩa entry trùng

Ví dụ:

~~~text
(1, "Công việc A")
(1, "Công việc B")
(1, "Công việc A")
~~~

Có **ba lần push**, nên size logic là 3 nếu chưa pop. Hai bản ghi có cùng payload "Công việc A" vẫn là hai lần xuất hiện. Nếu ứng dụng muốn ngăn thêm trùng ID, phải triển khai thêm quy tắc riêng.

### 12.2. Không nhầm ID với priority

ID trả lời **“đây là công việc nào?”**, trong khi priority trả lời **“công việc này được chọn khi nào so với công việc khác?”**. Một công việc có thể đổi priority nhưng ID vẫn giữ nguyên. Nếu dùng priority làm ID, hai công việc có cùng ưu tiên sẽ bị nhập làm một cách sai lầm.

### 12.3. Khóa có thể gồm nhiều trường

Ví dụ xử lý yêu cầu theo hạn chót rồi độ khẩn cấp:

~~~python
entry = (
    deadline_timestamp,
    -urgency_score,
    sequence_number,
    payload,
)
~~~

Với kiểu tuple này, hai yêu cầu deadline giống nhau sẽ được so sánh theo urgency cao trước; nếu cả hai yếu tố bằng nhau, sequence nhỏ hơn được chọn trước.

**Không tự trộn thứ tự nghiệp vụ:** nếu yêu cầu “sự cố mức cao luôn đứng trước mọi deadline”, thứ tự thành phần phải thay đổi, chẳng hạn đặt urgency trước deadline. So sánh khóa tuple áp dụng **thứ tự các trường từ trái sang phải**, không tự hiểu ý nghĩa của từng trường.

### 12.4. Khóa không nên thay đổi ngầm

Nếu priority được tính theo thời gian hiện tại, ví dụ “càng chờ lâu càng ưu tiên”, khóa có thể thay đổi theo đồng hồ. Heap không tự tái cấu trúc mỗi khi thời gian trôi qua. Cần chọn một cơ chế:

- Cập nhật khóa định kỳ và sửa heap.
- Tính khóa cố định tại lúc thêm theo quy tắc phù hợp.
- Hoặc sử dụng cấu trúc và thuật toán lập lịch khác hỗ trợ ưu tiên động.

Một quan hệ so sánh dựa trên trạng thái thay đổi liên tục trong khi heap đang chứa entry có thể phá giả định về **thứ tự ổn định trong khoảng thời gian giữa các lần tái cấu trúc**.

## 13. Những lỗi thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi priority queue luôn FIFO | Bỏ qua khóa ưu tiên; lấy sai công việc | Phân biệt FIFO và quy tắc chọn khóa |
| Coi heap đồng nghĩa với priority queue | Nhầm ADT với cài đặt cụ thể | Nêu rõ hợp đồng và cấu trúc lưu trữ |
| Cho rằng số priority lớn luôn ưu tiên hơn | Sai nếu hệ thống quy ước số nhỏ hơn ưu tiên hơn | Chọn rõ min hay max trước khi viết mã |
| Nhầm peek với pop | Thay đổi size sai hoặc không loại entry đã xử lý | Peek chỉ xem, pop phải xóa |
| Dùng payload để so sánh khi khóa bằng nhau | TypeError hoặc thứ tự hòa không mong muốn | Thêm sequence độc lập |
| Mặc định heap tự ổn định | Công việc bằng khóa có thể đổi thứ tự đến | Dùng sequence nếu cần FIFO khi hòa |
| Dùng value hoặc priority làm ID duy nhất | Xóa/cập nhật nhầm khi có bản ghi trùng | Dùng handle/ID riêng |
| Sửa trực tiếp thuộc tính priority của task trong heap | Bất biến heap có thể bị hỏng | Qua API change-key hoặc tạo entry mới hợp lệ |
| Không xử lý stale entry sau khi cập nhật lazy | Trả công việc đã hủy hoặc khóa cũ | Đánh dấu và bỏ qua stale khi lấy |
| Dùng len(heap) làm số công việc active với lazy deletion | Size báo lớn hơn thực tế | Duy trì size logic riêng |
| Cho rằng toàn bộ mảng heap được sắp xếp | Đọc nhầm phần tử nhỏ thứ hai | Chỉ gốc được bảo đảm nhỏ nhất |
| Cho rằng heapify phải O(n log n) | Phân tích quá cao | Bottom-up heapify đạt Θ(n) |
| Quên kiểm tra rỗng trước peek/pop | Lỗi không kiểm soát hoặc kết quả không rõ | Quy định và thực thi lỗi rỗng |
| Trộn số và chuỗi làm priority trong heap Python | TypeError khi so sánh | Chuẩn hóa các khóa cùng kiểu/thứ tự |
| Dùng NaN làm khóa số thực mà không có chính sách | Quan hệ thứ tự có thể không đúng mong đợi | Từ chối hoặc xử lý NaN riêng |
| Để nguồn công việc khẩn cấp đến liên tục | Công việc thấp ưu tiên có thể không bao giờ được phục vụ | Thiết kế aging/quota/fairness |

Một bộ kiểm thử tốt phải bao gồm **hàng đợi rỗng**, **một phần tử**, **nhiều khóa khác nhau**, **khóa trùng**, **payload không so sánh được**, **push xen pop** và **đổi/hủy ưu tiên** nếu API hỗ trợ.

## 14. Ứng dụng thực tế và cách lựa chọn

### 14.1. Lập lịch công việc

Một hệ thống xử lý nền có thể đặt priority nhỏ hơn cho công việc có tính khẩn cấp cao hơn. Hàng đợi ưu tiên chọn tác vụ tiếp theo theo quy tắc này.

Cần bổ sung chính sách **công bằng** nếu không muốn tác vụ thấp ưu tiên chờ vô hạn. Trong các hệ thống có nhiều loại công việc, việc chia hàng đợi hoặc phân bổ thời gian giữa các mức ưu tiên có thể quan trọng không kém cấu trúc dữ liệu.

### 14.2. Mô phỏng sự kiện rời rạc

Mỗi sự kiện được gắn **thời điểm dự kiến xảy ra**. Min-priority queue dùng **timestamp** làm khóa, nên pop lấy sự kiện có thời gian nhỏ nhất còn chờ. Với các sự kiện cùng timestamp, sequence có thể giữ thứ tự thêm vào để kết quả mô phỏng xác định được.

~~~text
(10, "Bắt đầu tải")
(12, "Nhận gói")
(11, "Gửi gói")

Thứ tự xử lý: t=10 → t=11 → t=12
~~~

Đây là một trường hợp điển hình của thao tác push/pop xen kẽ, nơi binary min-heap thường phù hợp.

### 14.3. Thuật toán tìm đường và đồ thị

Trong Dijkstra, hàng đợi ưu tiên thường chọn đỉnh có **khoảng cách tạm thời nhỏ nhất**. Khóa ưu tiên là chi phí đường đi dự kiến/tốt nhất đã biết tại thời điểm đưa vào hàng đợi. Khi khám phá đường đi tốt hơn, thuật toán cần cơ chế cập nhật khóa hoặc thêm ứng viên mới và loại entry lỗi thời khi pop.

Sự chính xác của thuật toán đồ thị **không chỉ phụ thuộc heap**: Dijkstra chuẩn còn yêu cầu trọng số cạnh không âm và các bất biến về khoảng cách.

### 14.4. Chọn cấu trúc theo đặc điểm tải

Nếu chỉ có vài phần tử và hầu hết thao tác là thêm, list chưa sắp xếp có thể đủ đơn giản. Nếu thường lấy phần tử nhỏ nhất và ít thêm, list đã sắp xếp có thể hợp lý. Nếu push/pop đều thường xuyên, binary heap thường cân bằng chi phí hai thao tác.

Nếu yêu cầu **xóa theo ID**, **truy xuất các phần tử theo khoảng khóa**, **duyệt tất cả theo thứ tự** hoặc **cập nhật nhiều khóa**, có thể cần kết hợp index, cây tìm kiếm cân bằng hoặc cấu trúc khác. Không nên chọn heap chỉ vì tên gọi “hàng đợi ưu tiên”.

## 15. Bài tập tự luyện có đáp án

**Bài 1 — Phân biệt FIFO.** Thêm A(priority 4), B(priority 1), C(priority 3) vào min-priority queue. Thứ tự pop là gì?

*Đáp án:* **B → C → A**, vì 1 < 3 < 4. FIFO theo thứ tự A, B, C sẽ khác.

**Bài 2 — Max-priority queue.** Với cùng ba entry A:4, B:1, C:3, thứ tự lấy ra của max-priority queue là gì?

*Đáp án:* **A → C → B**, bởi 4 > 3 > 1.

**Bài 3 — Peek và pop.** Queue chứa (2, X), (1, Y). Sau peek rồi pop, size thay đổi như thế nào?

*Đáp án:* Peek trả (1, Y) nhưng size vẫn 2; pop trả (1, Y) và size còn 1.

**Bài 4 — Hàng đợi rỗng.** Nếu payload có thể là None, trả None từ pop để báo rỗng có thể gây khó khăn gì?

*Đáp án:* Không phân biệt được pop thành công với payload None và pop thất bại. Nên dùng exception hoặc kết quả có trạng thái.

**Bài 5 — Khóa bằng nhau.** Thêm (2, A), (2, B), (2, C) vào priority queue cơ bản. Có luôn phải pop A, B, C theo thứ tự thêm không?

*Đáp án:* Không. ADT cơ bản chỉ yêu cầu lấy một entry có khóa nhỏ nhất. Nếu cần FIFO khi khóa bằng nhau, phải chỉ định **tính ổn định**.

**Bài 6 — Số thứ tự.** Các entry (3, 10, A), (3, 11, B), (2, 12, C) được so sánh theo (priority, sequence). Thứ tự pop là gì?

*Đáp án:* **C → A → B**, vì khóa 2 đi trước 3; A có sequence 10 nhỏ hơn 11 nên đi trước B.

**Bài 7 — Payload không so sánh.** Vì sao lưu (priority, payload) có thể gây TypeError trong heapq khi hai priority bằng nhau?

*Đáp án:* Python so sánh thành phần thứ hai khi thành phần đầu bằng nhau; payload có thể là các đối tượng không hỗ trợ thứ tự. Thêm sequence duy nhất ở giữa để không cần so payload.

**Bài 8 — Heap có sắp toàn mảng không?** Dãy [1, 3, 2, 8, 4, 6] có thể là min-heap dù 3 đứng trước 2 không?

*Đáp án:* Có. Min-heap chỉ yêu cầu khóa ở mỗi cha ≤ khóa các con, không bắt buộc toàn mảng tăng dần.

**Bài 9 — Độ phức tạp.** Với binary min-heap n phần tử, thời gian peek, push, pop lần lượt là bao nhiêu?

*Đáp án:* **O(1)**, **O(log n)**, **O(log n)** theo mô hình chuẩn; push/pop tốn tối đa số mức tương ứng chiều cao heap.

**Bài 10 — Heapify.** Vì sao xây binary heap từ n entry bằng bottom-up heapify không nhất thiết tốn n lần O(log n)?

*Đáp án:* Phần lớn nút nằm gần lá nên mỗi nút chỉ có thể đi xuống ít tầng. Tổng công việc của các bước sift-down từ dưới lên là **Θ(n)**.

**Bài 11 — So sánh hai list.** List chưa sắp xếp và list sắp xếp (min ở cuối) có chi phí push/pop thế nào?

*Đáp án:* List chưa sắp xếp: push O(1) khấu hao, pop O(n). List sắp xếp: push O(n), pop O(1).

**Bài 12 — Thay đổi khóa.** Vì sao đổi task.priority từ 5 sang 1 mà không sửa heap là nguy hiểm?

*Đáp án:* Vị trí entry được quyết định theo khóa trước đó. Đổi khóa có thể phá bất biến cha/con; cần gọi update phù hợp hoặc thêm entry mới và vô hiệu hóa entry cũ.

**Bài 13 — Khóa phức hợp.** Hai việc có khóa (100, -9) và (100, -3). Việc nào được lấy trước trong min-priority queue?

*Đáp án:* (100, -9) đi trước vì deadline bằng nhau và -9 < -3, tương ứng mức khẩn cấp 9 cao hơn 3.

**Bài 14 — Starvation.** Vì sao priority queue ổn định vẫn có thể khiến một công việc priority 9 chờ mãi?

*Đáp án:* Tính ổn định chỉ giải quyết hòa khóa; nếu công việc priority 1 liên tục được thêm trước khi queue hết nhóm ưu tiên cao, công việc priority 9 không được chọn. Cần cơ chế fairness/aging nếu ứng dụng yêu cầu.

**Bài 15 — Lựa chọn ADT.** Một hệ thống mô phỏng thường thêm sự kiện mới rồi lấy sự kiện có timestamp nhỏ nhất. Cấu trúc nào phù hợp?

*Đáp án:* **Min-priority queue**, thường triển khai bằng **binary min-heap**, vì cần push/pop xen kẽ với chi phí O(log n) và peek O(1).

**Bài 16 — ADT và cài đặt.** Một người nói “priority queue chính là binary heap và mọi phần tử đã được sắp xếp trong mảng”. Hãy chỉ ra hai sai sót.

*Đáp án:* Priority queue là **ADT**, còn binary heap chỉ là một cách triển khai. Mảng của min-heap chỉ bảo đảm quan hệ **cha ≤ con**, không phải thứ tự tăng dần của toàn mảng.

**Ghi nhớ:** **Hàng đợi ưu tiên là một hợp đồng chọn phần tử theo khóa**, không phải tên gọi của riêng heap. Cần định nghĩa rõ **min/max**, **khóa ưu tiên**, **hành vi khi khóa bằng nhau**, **lỗi khi rỗng** và **cập nhật khóa** nếu có. Binary heap thường cung cấp **peek O(1)**, **push/pop O(log n)** và **heapify O(n)**, nhưng một priority queue vẫn có thể cài bằng cấu trúc khác. Khi dùng Python heapq, mẫu **(priority, sequence, payload)** giúp ổn định thứ tự trong cùng mức ưu tiên và tránh so sánh payload ngoài ý muốn.
