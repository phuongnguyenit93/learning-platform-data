# Đo hiệu năng với dữ liệu và tải thao tác đại diện

Một cấu trúc dữ liệu có thể có độ phức tạp lý thuyết tốt nhưng chạy chậm trong một ứng dụng cụ thể. Chẳng hạn, tra cứu trong bảng băm thường có thời gian kỳ vọng `O(1)`, nhưng hiệu quả còn phụ thuộc vào phân phối khóa, số lần tái băm, kích thước dữ liệu và cách sử dụng bộ nhớ. Danh sách liên kết có thể thêm ở đầu trong `O(1)`, nhưng duyệt tuần tự có thể kém hiệu quả hơn mảng liên tiếp do phải đi theo các con trỏ rải rác trong bộ nhớ.

Để lựa chọn đúng giữa mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị, ta cần **đo hiệu năng với dữ liệu và chuỗi thao tác đại diện cho nhu cầu thực tế**. Đo một phép toán trong một trường hợp dễ nhất chưa đủ để kết luận cấu trúc nào phù hợp.

Bài học trong chương **Kiểm chứng và thực hành** này hướng dẫn thiết kế phép đo có thể lặp lại, chọn bộ dữ liệu và tải thao tác, phân biệt độ trễ, thông lượng và bộ nhớ, đồng thời diễn giải kết quả dựa trên bất biến và phân tích độ phức tạp.

## 1. Đo điều gì, để quyết định điều gì?

Trước khi viết mã đo thời gian, hãy phát biểu quyết định cần đưa ra. Ví dụ:

> Một hệ thống xử lý yêu cầu cần thêm công việc vào cuối hàng đợi và lấy công việc cũ nhất ở đầu. Với hàng đợi thường có 10.000 phần tử và liên tục thêm/lấy, nên biểu diễn bằng `list` hay `deque` trong Python?

Câu hỏi này chứa ba yếu tố quan trọng:

1. **Thao tác:** thêm cuối và lấy đầu, không phải truy cập ngẫu nhiên.
2. **Quy mô:** thường có khoảng 10.000 phần tử đang chờ.
3. **Tải:** chuỗi cập nhật lặp lại, không phải một lần lấy khỏi hàng đợi rỗng.

Một câu hỏi khác như “cần đọc phần tử ở vị trí `i` liên tục” có thể dẫn đến quyết định khác, dù vẫn so `list` với `deque`.

### Chọn chỉ số đo phù hợp

| Chỉ số | Ý nghĩa | Khi nào quan trọng |
|---|---|---|
| **Độ trễ** (*latency*) | Thời gian hoàn thành một thao tác hoặc yêu cầu | Truy vấn tương tác, yêu cầu giới hạn thời gian |
| **Thông lượng** (*throughput*) | Số thao tác/yêu cầu hoàn thành mỗi giây | Xử lý luồng sự kiện hoặc khối lượng lớn |
| **Bộ nhớ sử dụng** | Dung lượng cần để lưu dữ liệu và cấu trúc phụ | Dữ liệu lớn, môi trường giới hạn RAM |
| **Bộ nhớ đỉnh** (*peak memory*) | Mức tiêu thụ cao nhất trong pha đo | Cấp phát lại mảng, rehash, xây chỉ mục |
| **Thời gian khởi tạo** | Chi phí tạo hoặc nạp cấu trúc ban đầu | Cấu trúc xây một lần, truy vấn nhiều lần |
| **Chi phí cập nhật** | Thời gian cho thêm/xóa/sửa và bảo trì chỉ mục | Ứng dụng ghi thường xuyên |
| **Độ trễ đuôi** (p95/p99) | Những thao tác chậm hơn phần lớn thao tác còn lại | Hệ thống yêu cầu phản hồi ổn định |

**Trung bình, trung vị và p99 không thay thế nhau.** Một mảng động có thể thêm cuối rất nhanh ở nhiều lần gọi nhưng phải sao chép dữ liệu khi tăng dung lượng. Chi phí khấu hao `O(1)` không có nghĩa mỗi lần gọi đều `O(1)`; vì vậy độ trễ của lần cấp phát lại cần được xem riêng nếu hệ thống có giới hạn độ trễ nghiêm ngặt.

Đừng dùng một số “thời gian tổng cộng” để trả lời mọi câu hỏi. Nếu yêu cầu là xử lý nhiều yêu cầu trong một giây, thông lượng quan trọng; nếu có thời hạn cho từng yêu cầu, cần quan sát cả phân phối độ trễ, đặc biệt các thao tác chậm bất thường.

## 2. Tải thao tác đại diện là gì?

Một **workload** là mô tả về dữ liệu ban đầu và chuỗi hành động mà hệ thống thực hiện. Nó phải bao gồm ít nhất:

- **Kích thước trạng thái:** số phần tử `n`, số khóa riêng biệt, số đỉnh/cạnh, dung lượng bộ đệm, độ dài khóa.
- **Tập phép toán:** tỷ lệ `get`, `put`, `remove`, truy vấn đoạn, `push`, `pop`, duyệt, v.v.
- **Thứ tự hành động:** đọc theo cụm, ghi đột biến, thêm rồi xóa luân phiên, có giai đoạn khởi động hay không.
- **Phân phối đầu vào:** khóa đều hay tập trung vào một nhóm “nóng”; dữ liệu đã sắp xếp hay xáo trộn; tỷ lệ giá trị trùng.
- **Tỷ lệ thành công:** tìm thấy/không tìm thấy khóa, Queue rỗng/đầy, truy vấn trong/ngoài bộ nhớ đệm.
- **Mức đồng thời:** một luồng hay nhiều luồng; có tranh chấp cập nhật cùng khóa hay không.
- **Điều kiện vận hành:** dữ liệu đã nằm trong RAM hay phải đọc từ đĩa; phiên bản runtime, phần cứng và giới hạn bộ nhớ.

Ví dụ: benchmark Map chỉ tìm khóa đã tồn tại với phân phối đều không đại diện cho dịch vụ có 80% truy vấn một nhóm nhỏ khóa và 20% tra cứu khóa chưa từng xuất hiện. Tỷ lệ *hit/miss*, tính cục bộ và kích thước khóa có thể thay đổi đáng kể kết quả.

### Ma trận workload theo cấu trúc dữ liệu

| Cấu trúc | Thao tác nên phối hợp | Biến đầu vào có ảnh hưởng |
|---|---|---|
| Mảng động | Đọc ngẫu nhiên, duyệt, thêm cuối, chèn/xóa giữa | `n`, vị trí cập nhật, tần suất tăng dung lượng |
| Danh sách liên kết | Thêm/xóa khi đã có con trỏ nút, tìm kiếm, duyệt | Độ dài danh sách, vị trí nút, chi phí cấp phát |
| Queue / Deque | Thêm cuối, lấy đầu, thêm/xóa hai đầu | Độ dài ổn định, đợt tăng tải, dung lượng, quấn vòng |
| HashMap / Set | Tra cứu, thêm, ghi đè, xóa, duyệt | Số khóa, độ dài khóa, phân phối truy cập, va chạm băm, hệ số tải |
| BST cân bằng | Tìm, chèn, xóa, duyệt theo thứ tự, truy vấn khoảng | Dữ liệu tăng dần/ngẫu nhiên, số khóa trùng, độ cao |
| Heap | `push`, `peek_min`, `pop_min` | Kích thước heap, tỷ lệ chèn/lấy, phân phối ưu tiên |
| DSU | `union`, `find`, truy vấn liên thông | Cách gộp tập, tỷ lệ `find`, độ sâu trước nén |
| Fenwick / Segment Tree | Cập nhật điểm, truy vấn đoạn | Độ dài mảng, độ dài/vị trí đoạn, tỷ lệ cập nhật |
| Đồ thị | Duyệt láng giềng, BFS/DFS, thêm/xóa cạnh | Số đỉnh `V`, số cạnh `E`, bậc đỉnh, tính thưa/dày |

Không cần chạy mọi tổ hợp ngay từ đầu. Hãy chọn một **workload chính** gần với ứng dụng, rồi thêm các workload phụ để thấy giới hạn: nhiều đọc/ít ghi, nhiều ghi/ít đọc, dữ liệu nhỏ/lớn, phân phối đều/tập trung, trạng thái gần ngưỡng tăng dung lượng.

## 3. Đặc điểm dữ liệu quan trọng ngang thuật toán

Hai bộ dữ liệu có cùng số phần tử `n` chưa chắc gây ra cùng chi phí.

### 3.1. Kích thước và phân phối khóa

Trong HashMap, khóa là số nguyên nhỏ khác khóa là chuỗi dài hoặc đối tượng phải thực hiện nhiều phép so sánh. Khi băm và kiểm tra bằng nhau tốn thời gian, chi phí thực tế có thể bị chi phối bởi **xử lý khóa** thay vì số thao tác truy cập bucket.

Nên thử dữ liệu có:

- Khóa duy nhất và khóa được cập nhật nhiều lần.
- Truy cập đều khắp không gian khóa và truy cập tập trung vào một nhóm nhỏ.
- Tỷ lệ khóa tìm thấy và không tìm thấy khác nhau.
- Va chạm băm có kiểm soát để khảo sát trường hợp khó, nhưng không nhầm kết quả đó với tải thông thường.

Đối với cây tìm kiếm, chèn khóa theo thứ tự tăng có thể tạo cây nghiêng nếu không cân bằng; cây cân bằng thường giữ độ cao `O(log n)` dù thứ tự chèn bất lợi. Vì thế, dữ liệu có thứ tự và dữ liệu ngẫu nhiên đều cần xuất hiện trong thí nghiệm.

### 3.2. Dữ liệu “nóng”, “lạnh” và bộ nhớ đệm

Nếu lặp đi lặp lại một nhóm khóa nhỏ, dữ liệu và nhánh thực thi có thể thường xuyên ở trong cache CPU. Khi truy cập các nút rải rác trên hàng triệu phần tử, chi phí truy cập bộ nhớ có thể trở nên lớn hơn nhiều.

Một benchmark có **trạng thái đã nạp sẵn** đo một bài toán khác với benchmark **đọc dữ liệu mới từ đĩa hoặc mạng**. Hãy phân biệt:

- **Warm workload:** cấu trúc đã được xây dựng, bộ nhớ/đường mã có cơ hội được làm nóng.
- **Cold workload:** tính cả khởi tạo, cấp phát, nạp dữ liệu hay khởi động hệ thống nếu đó là phần yêu cầu.
- **Streaming workload:** dữ liệu liên tục đến và bị xóa; trạng thái thay đổi theo thời gian.

### 3.3. Trùng lặp và biên dung lượng

Với heap, nhiều giá trị ưu tiên bằng nhau có thể thay đổi nhánh so sánh nhưng vẫn phải bảo toàn số lần xuất hiện. Với mảng động, thời điểm `size == capacity` dẫn đến một lần cấp phát lại đắt hơn các lần thêm thông thường. Với Queue vòng, việc `head` quấn vòng là tình huống điển hình mà một benchmark chỉ thêm phần tử trên Queue rỗng sẽ không tạo ra.

Bộ dữ liệu đại diện cũng phải **đúng về ngữ nghĩa**: không được sinh ra khóa trùng cho cấu trúc cấm trùng rồi bỏ qua lỗi, hoặc so hai cấu trúc có chính sách xử lý Queue đầy khác nhau như thể chúng thực hiện cùng workload.

## 4. Thiết kế phép đo công bằng

Một phép đo dùng để chọn cấu trúc dữ liệu cần kiểm soát các yếu tố ngoài thuật toán.

**Bước 1 — Kiểm tra tính đúng đắn trước.** Đối chiếu với mô hình tham chiếu, kiểm tra bất biến và các ca biên. Một cài đặt bỏ qua công việc hoặc làm mất phần tử có thể “nhanh” hơn chỉ vì nó làm thiếu việc.

**Bước 2 — Cùng hợp đồng và cùng workload.** Hai bản phải nhận cùng dữ liệu ban đầu, cùng chuỗi thao tác hợp lệ, cùng quy tắc về phần tử trùng và kết quả lỗi. Nếu một bản có thêm chỉ mục hỗ trợ truy vấn khác, cần đánh giá đúng lợi ích và chi phí bảo trì chỉ mục ấy.

**Bước 3 — Tách các pha.** Phân biệt thời gian tạo dữ liệu, khởi tạo cấu trúc, chạy thao tác và xác minh kết quả. Chỉ đưa pha nào vào bộ đo nếu pha đó thực sự thuộc quyết định. Ví dụ một chỉ mục được xây một lần rồi truy vấn hàng triệu lần có thể chấp nhận chi phí xây dựng cao.

**Bước 4 — Làm nóng và lặp lại.** Chạy một vài lượt không lấy số đo để giảm ảnh hưởng khởi động; chạy nhiều lượt độc lập, ghi số liệu từng lượt, xem trung vị và độ dao động. Khởi tạo lại trạng thái cho mỗi lượt để tránh thay đổi kích thước giữa các lượt làm lệch so sánh.

**Bước 5 — Cố định môi trường.** Ghi phiên bản Python/Java/C++, hệ điều hành, CPU, cấu hình bộ nhớ, số luồng và các tùy chọn runtime liên quan. Giảm tải nền không liên quan trong thời gian đo. Khi dùng máy ảo hoặc môi trường chia sẻ, cần lưu ý độ nhiễu.

**Bước 6 — Đo nhiều mức kích thước.** Dùng một dãy kích thước có ý nghĩa, chẳng hạn `100`, `1.000`, `10.000`, `100.000` nếu bộ nhớ và thời gian cho phép, để nhận ra xu hướng khi `n` tăng. Một kết quả ở `n = 100` không đủ để dự đoán hiệu năng ở `n = 10^6`.

Không nên sinh dữ liệu ngẫu nhiên, in log, kiểm tra toàn bộ bất biến hay xuất biểu đồ **bên trong vùng định thời** trừ khi ứng dụng thực tế cũng thực hiện những công việc đó. Các hoạt động phụ sẽ che khuất chi phí của cấu trúc cần so sánh.

## 5. Ví dụ đo Queue: `list.pop(0)` so với `deque.popleft()`

Ta muốn xử lý một hàng đợi FIFO trong Python. Hai cách triển khai:

- `list`: `append(x)` thêm cuối; `pop(0)` xóa phần tử đầu, phải dịch các phần tử còn lại, chi phí `O(n)` cho một lần lấy đầu.
- `collections.deque`: `append(x)` và `popleft()` được thiết kế cho hai đầu, có chi phí `O(1)` khấu hao.

Để quan sát ảnh hưởng của **độ dài Queue**, hãy giữ Queue gần như có đúng `n` phần tử bằng cách lặp một **cặp thao tác**: lấy đầu rồi thêm cuối. Nếu Queue chỉ có một phần tử, sự khác biệt có thể nhỏ; khi Queue lớn, việc dịch phần tử của `list` có khả năng chi phối thời gian.

### 5.1. Mã benchmark có thể chạy trực tiếp

Ví dụ tự chứa dưới đây đo cùng một khối lượng công việc bằng `time.perf_counter_ns()`. Mỗi lượt tạo Queue mới, nạp trước `n` phần tử, đo `steps` cặp lấy đầu/thêm cuối, rồi kiểm tra trạng thái sau **khi dừng đồng hồ**.

```python
from collections import deque
from statistics import median
from time import perf_counter_ns


def run_one_trial(kind: str, n: int, steps: int) -> int:
    if n < 1 or steps < 1:
        raise ValueError("n va steps phai duong")

    if kind == "list":
        queue = list(range(n))
    elif kind == "deque":
        queue = deque(range(n))
    else:
        raise ValueError("kind phai la 'list' hoac 'deque'")

    start = perf_counter_ns()

    if kind == "list":
        for value in range(n, n + steps):
            queue.pop(0)
            queue.append(value)
    else:
        for value in range(n, n + steps):
            queue.popleft()
            queue.append(value)

    elapsed_ns = perf_counter_ns() - start

    # Kiem tra sau khi dung dong ho:
    # Sau steps lan, Queue phai chua [steps, ..., steps+n-1].
    expected = list(range(steps, steps + n))
    if list(queue) != expected:
        raise AssertionError("Sai thu tu hoac mat phan tu")

    return elapsed_ns


def measure(kind: str, n: int, steps: int = 5000,
            warmups: int = 2, repeats: int = 7):
    # Warmup tu dau, moi lan deu tao trang thai moi.
    for _ in range(warmups):
        run_one_trial(kind, n, steps)

    # Moi cap pop/append = hai thao tac cong khai.
    ns_per_operation = [
        run_one_trial(kind, n, steps) / (2 * steps)
        for _ in range(repeats)
    ]

    return {
        "median_ns_per_op": median(ns_per_operation),
        "min_ns_per_op": min(ns_per_operation),
        "max_ns_per_op": max(ns_per_operation),
    }


for n in (10, 100, 1000, 10000):
    a = measure("list", n)
    b = measure("deque", n)
    print(
        f"n={n:5d} | "
        f"list={a['median_ns_per_op']:.1f} ns/op | "
        f"deque={b['median_ns_per_op']:.1f} ns/op"
    )
```

Chạy trong môi trường Python phù hợp, sau đó ghi lại các số đo thực tế. Bài học không đưa số liệu dựng sẵn vì kết quả phụ thuộc vào máy và phiên bản runtime.

**Diễn giải chính xác số đo:** giá trị `median_ns_per_op` là **trung vị qua nhiều lượt của thời gian trung bình trên một thao tác**, lấy tổng thời gian của cặp `pop` và `append` chia cho `2 * steps`. Đây **không phải** p50 độ trễ của từng lời gọi. `min`/`max` cũng là cực trị giữa các lượt đo trung bình, không phải độ trễ nhanh/chậm nhất của từng `pop`.

Mã đo còn bao gồm chi phí vòng lặp và sinh các số nguyên của `range` trong vùng định thời. Hai cách thực hiện cùng khối lượng đó, nhưng chi phí chung có thể che sự khác biệt khi `n` rất nhỏ. Nếu cần tách riêng `pop(0)` và `popleft()`, phải xây một phép đo khác với trạng thái và số lần thao tác tương đương; không thể suy số chính xác riêng của chúng từ benchmark cặp thao tác này.

### 5.2. Kỳ vọng dựa trên thuật toán

Với độ dài hàng đợi gần như cố định `n` và `steps = m`:

- Bản `list` phải dịch phần lớn `n` phần tử sau mỗi `pop(0)`, nên chi phí của workload thường tăng khoảng theo `m × n`.
- Bản `deque` thực hiện các thao tác hai đầu có chi phí khấu hao hằng số, nên chi phí thao tác thường tăng theo `m` và ít phụ thuộc `n` hơn.
- Với `n` rất nhỏ, chênh lệch thực tế có thể bị ảnh hưởng bởi hằng số, chi phí vòng lặp hoặc cơ chế thực thi của Python.

**Không suy ra rằng `deque` nhanh hơn `list` trong mọi bài toán.** Nếu ứng dụng chủ yếu truy cập phần tử ở vị trí ngẫu nhiên `i`, `list[i]` có thời gian `O(1)`, còn truy cập gần giữa `deque` có thể cần duyệt `O(n)`. Tải đại diện mới quyết định chọn cấu trúc nào.

## 6. Đo độ trễ, thông lượng và độ trễ đuôi

### 6.1. Đo theo lô và đo từng thao tác khác nhau ra sao?

Đo theo lô phù hợp với phép toán rất nhanh: định thời một loạt hàng nghìn thao tác rồi chia cho số thao tác, giảm nhiễu do gọi đồng hồ cho từng lệnh. Tuy nhiên, cách đo này **che độ trễ đuôi**.

Nếu phải biết độ trễ riêng của `push` hay `pop_min`, cần thu thập phân phối thời gian của từng thao tác (hoặc các đoạn quan sát có định nghĩa rõ). Trong chương trình đo riêng, có thể:

```python
samples_ns = []

for operation in scripted_operations:
    t0 = perf_counter_ns()
    apply_one_operation(structure, operation)
    samples_ns.append(perf_counter_ns() - t0)

samples_ns.sort()
```

Cách đặt đồng hồ quanh từng thao tác bổ sung **overhead đáng kể** với thao tác rất nhỏ. Khi phân tích độ trễ ở thang nano/micro giây, phải đánh giá chi phí đo, lấy đủ mẫu và cân nhắc công cụ benchmark hoặc profiler chuyên dụng.

Với danh sách `samples_ns` đã sắp xếp, một quy ước percentile dễ trình bày là **nearest rank**:

\[
p_q = samples[\lceil qN\rceil - 1],
\quad 0 < q \le 1,\;N = |samples|.
\]

Ở đây `q = 0.95` cho p95 và `q = 0.99` cho p99; phải có đủ mẫu để p99 có ý nghĩa. Các phần mềm có thể dùng quy tắc nội suy percentile khác, nên khi so báo cáo cần thống nhất định nghĩa.

### 6.2. Thông lượng

Nếu hoàn tất `m` thao tác trong thời gian `t` giây thì:

\[
\operatorname{throughput}=\frac{m}{t}
\quad\text{(thao tác/giây)}.
\]

Đối với workload hỗn hợp, có thể báo **thao tác/giây** cùng tỷ lệ `get/put/remove`; nếu đo theo yêu cầu nghiệp vụ gồm nhiều thao tác cấu trúc dữ liệu, nên báo **yêu cầu/giây** theo định nghĩa của ứng dụng. Không thể so hai con số throughput khi một bên tính một thao tác đọc đơn giản còn bên kia tính cả cập nhật và tái băm.

Trong môi trường nhiều luồng, thông lượng tăng theo số luồng không đồng nghĩa độ trễ từng yêu cầu không đổi. Tranh chấp khóa, đồng bộ và phân bổ CPU có thể làm p95/p99 tăng dù tổng số thao tác mỗi giây cao hơn.

## 7. Đo bộ nhớ và chi phí đỉnh

Hiệu năng không chỉ là thời gian. Một cấu trúc có chỉ mục phụ có thể giảm thời gian truy vấn nhưng tăng bộ nhớ lưu trữ và chi phí cập nhật.

Cần phân biệt:

- **Bộ nhớ logic:** số phần tử và các trường được lưu theo thiết kế.
- **Bộ nhớ dành chỗ:** dung lượng dự phòng của mảng, bucket của bảng băm, ô đã cấp phát nhưng chưa dùng.
- **Overhead biểu diễn:** con trỏ, đối tượng nút, metadata, bộ cấp phát.
- **Bộ nhớ tạm thời:** bản sao khi resize/rehash, bộ đệm của thuật toán và chi phí xây chỉ mục.
- **Bộ nhớ đỉnh:** mức cao nhất tại một thời điểm của pha chạy được đo.

Trong Python, `sys.getsizeof(obj)` thường chỉ phản ánh kích thước trực tiếp của **một đối tượng**, không cộng đệ quy bộ nhớ của các đối tượng nó tham chiếu. Không thể dùng riêng con số đó để kết luận tổng RAM của cây hay bảng băm.

Một công cụ hữu ích cho phân tích các cấp phát Python là `tracemalloc`:

```python
import tracemalloc


def measure_python_allocations(build):
    tracemalloc.start()
    try:
        # Reset moc dinh cua pha can do.
        tracemalloc.reset_peak()
        before_current, _ = tracemalloc.get_traced_memory()

        structure = build()  # Xay dung doi tuong can do

        after_current, peak = tracemalloc.get_traced_memory()
        retained_delta = after_current - before_current
        peak_delta = peak - before_current

        # Giu tham chieu structure cho den sau khi do.
        return retained_delta, peak_delta, structure
    finally:
        tracemalloc.stop()


used, peak, structure = measure_python_allocations(
    lambda: {i: i * 2 for i in range(10000)}
)
print("Tracked retained delta (bytes):", used)
print("Tracked peak delta (bytes):", peak)
```

**Giới hạn:** `tracemalloc` đo những vùng cấp phát được trình theo dõi của Python ghi nhận, không phải toàn bộ bộ nhớ cư trú (**RSS**) của tiến trình hoặc bộ nhớ mọi thư viện native. Giá trị chênh lệch còn chịu ảnh hưởng bởi hoạt động runtime trong pha đo. Muốn so dung lượng RAM tổng của các bản cài đặt có phần native, cần bổ sung đo RSS/heap bằng công cụ phù hợp với môi trường.

Nên đo bộ nhớ trong một lượt riêng với lượt định thời: bật trình theo dõi cấp phát hoặc profiler có thể làm thay đổi thời gian chạy. Các bản đo bộ nhớ phải nạp cùng dữ liệu và thực hiện cùng workload; bộ nhớ sau khi xóa cũng đáng đo nếu cấu trúc giữ lại dung lượng dự phòng.

## 8. Phân tích kết quả theo độ phức tạp lý thuyết

Phép đo có ý nghĩa nhất khi được đặt cạnh kỳ vọng từ thuật toán.

Giả sử `T(n)` là thời gian thực hiện cùng số lượng và loại thao tác khi trạng thái ban đầu có `n` phần tử:

- Nếu mỗi thao tác có chi phí `O(1)` theo `n`, thời gian đo **có thể** gần như không đổi khi `n` tăng, miễn là không xuất hiện yếu tố bộ nhớ/cache mới.
- Nếu chi phí `O(log n)`, thời gian tăng chậm theo `n`.
- Nếu chi phí `O(n)`, tăng `n` lên gấp đôi có thể khiến phần chi phí phụ thuộc `n` tăng xấp xỉ gấp đôi.
- Nếu một thao tác có chi phí `O(1)` **khấu hao**, nhiều lượt có thể rất nhanh nhưng một lượt kích hoạt resize có thể là `O(n)`.
- Nếu cấu trúc có chi phí `O(1)` **kỳ vọng** dưới giả thiết hàm băm/phân phối khóa, các workload va chạm có chủ đích có thể cho kết quả xấu hơn.

Những quan sát này là **xu hướng kỳ vọng**, không phải công thức suy trực tiếp từ vài số đo. Hằng số, cache CPU, cấp phát, thu gom rác, biên dịch JIT và độ lớn đối tượng có thể khiến kết quả lệch đáng kể.

### Tránh nhầm `n` với số thao tác `m`

Trong benchmark Queue ở trên, `n` là **số phần tử đang có**, còn `m` là **số cặp thao tác** được chạy. Nếu cùng tăng cả `n` và `m`, tổng thời gian tăng có thể do cả hai; rất khó rút ra chi phí phụ thuộc vào `n`.

Một cách thực hành là chạy hai nhóm phép đo:

1. **Cố định `m`, thay đổi `n`:** quan sát chi phí mỗi thao tác khi cấu trúc lớn hơn.
2. **Cố định `n`, thay đổi `m`:** quan sát chi phí theo khối lượng thao tác và phát hiện các sự kiện tích lũy như cấp phát lại.

Với cấu trúc tự mở rộng, cũng cần đánh giá mức dung lượng nằm **ngay trước và ngay sau** điểm resize. Chi phí của một lần tăng dung lượng có thể bị che nếu chỉ dùng thời gian trung bình trong một khối lượng dài.

### Phân biệt ba kiểu bảo đảm

| Kiểu phát biểu | Ý nghĩa | Ví dụ |
|---|---|---|
| Trường hợp xấu nhất (*worst-case*) | Giới hạn cho mọi đầu vào hợp lệ dưới mô hình phân tích | Tìm trong cây cân bằng: `O(log n)` |
| Kỳ vọng (*expected*) | Trung bình theo biến ngẫu nhiên/giả thiết phân phối được nêu | Tra cứu bảng băm: thường `O(1)` kỳ vọng |
| Khấu hao (*amortized*) | Trung bình chi phí trên một chuỗi thao tác, không nhất thiết từng thao tác | Thêm cuối mảng động nhân đôi dung lượng: `O(1)` khấu hao |

Một phép đo thực nghiệm không tự chứng minh kiểu bảo đảm nào trong bảng. Để có lập luận đúng, cần phân tích thuật toán và chỉ dùng phép đo để kiểm tra hành vi thực tế dưới các điều kiện cụ thể.

## 9. Một ví dụ thứ hai: workload hỗn hợp của Map

Giả sử ứng dụng sử dụng Map để tra thông tin người dùng. Hai thiết kế được cân nhắc là HashMap và cây tìm kiếm cân bằng. Workload đại diện có thể là:

```text
Quy mo ban dau: 100.000 khoa duy nhat
Tep khoa: so nguyen, chuoi ngan, chuoi dai
Thao tac: 80% get, 15% put/ghi de, 5% remove
Truy van: 90% khoa co mat, 10% khoa khong ton tai
Phan phoi: 70% get nham vao 10% khoa pho bien
Pha chay: nap du lieu -> warmup -> chay tai hon hop
```

Đây chỉ là **mẫu cấu hình**. Trong dự án thật, tỷ lệ phải lấy từ yêu cầu, quan sát hoặc giả thiết được ghi rõ. Chạy thêm một workload kiểm tra cực trị như chèn khóa đã sắp xếp, chuỗi va chạm băm nhiều hơn thông thường hoặc xóa rồi chèn liên tục để thấy điểm yếu.

Cần đo riêng:

- Thời gian và bộ nhớ **xây Map** từ đầu.
- Độ trễ `get` cho hit và miss; có thể khác nhau vì số phép so sánh và truy cập.
- Chi phí `put` cho khóa mới và ghi đè khóa cũ; thời điểm resize/rehash.
- Chi phí `remove` và hoạt động sau nhiều lần xóa.
- Thông lượng toàn workload trộn với tỷ lệ công bố.
- Nếu ứng dụng cần dữ liệu có thứ tự, chi phí **duyệt tăng dần hoặc truy vấn khoảng**; khả năng này có thể quyết định chọn cây dù `get` đơn lẻ không nhanh hơn.

Khi diễn giải, không nên chỉ nói “HashMap nhanh hơn cây”. Cần nêu **với số khóa, phân phối, tỷ lệ thao tác, chính sách sắp thứ tự và bộ nhớ nào** thì một thiết kế đáp ứng mục tiêu tốt hơn.

## 10. Lập báo cáo benchmark có thể kiểm chứng

Một báo cáo tốt cho phép người khác hiểu quyết định và chạy lại thí nghiệm. Có thể dùng mẫu sau:

| Trường | Nội dung cần ghi |
|---|---|
| Mục tiêu | Phép toán và yêu cầu thời gian/bộ nhớ cần tối ưu |
| Cấu trúc so sánh | Tên, phiên bản, cách cấu hình, hợp đồng hành vi |
| Môi trường | Máy, CPU, RAM, OS, runtime, số luồng |
| Dữ liệu | `n`, kiểu khóa, kích thước phần tử, tỷ lệ trùng, phân phối |
| Workload | Tỷ lệ, thứ tự thao tác, tổng số thao tác `m`, hit/miss |
| Warmup & lặp | Số lượt bỏ qua, số lượt đo, cách khởi tạo lại |
| Phạm vi định thời | Có/không tính tạo dữ liệu, khởi tạo, xác minh, I/O |
| Thước đo | Thông lượng, latency p50/p95/p99, bộ nhớ giữ lại và đỉnh |
| Độ dao động | Các mẫu gốc hoặc trung vị kèm khoảng phân tán |
| Tính đúng | Bộ kiểm tra kết quả và bất biến đã đạt |
| Kết luận giới hạn | Workload nào có lợi, workload nào còn chưa đo |

Ví dụ cách ghi kết luận có trách nhiệm:

> Trong workload FIFO với Queue giữ độ dài ổn định và liên tục lấy đầu/thêm cuối, `deque` phù hợp hơn `list.pop(0)` khi `n` lớn, đúng với phân tích chi phí thao tác. Kết quả của phép đo này không đánh giá truy cập ngẫu nhiên, bộ nhớ tổng hay hiệu năng khi nhiều luồng.

Kết luận nên gắn với phạm vi thí nghiệm. Nếu thay một yếu tố quan trọng, như dữ liệu chuyển từ RAM sang đĩa hoặc chuyển từ workload đọc nhiều sang cập nhật nhiều, cần đánh giá lại.

## 11. Những lỗi thường khiến số đo đánh lừa

1. **Chỉ đo một lần:** có thể trùng với hoạt động hệ điều hành, GC hoặc thay đổi xung nhịp CPU. Hãy lặp lại và báo độ dao động.
2. **Sinh dữ liệu trong đồng hồ:** phép đo vô tình đo hàm random hoặc I/O thay cho cấu trúc. Sinh trước, trừ khi chi phí sinh thuộc workload thật.
3. **Hai cấu trúc nhận dữ liệu khác nhau:** một bản có nhiều cache hit hay ít khóa trùng hơn nên không thể so trực tiếp.
4. **Không khôi phục trạng thái giữa các lượt:** cấu trúc ở lượt sau lớn hơn/nhỏ hơn, dẫn đến chi phí không cùng điều kiện.
5. **Chỉ so thời gian mà không so kết quả:** bản sai hoặc làm thiếu công việc vẫn có thể trông nhanh hơn.
6. **Lẫn thời gian khởi tạo với thời gian thao tác:** chỉ mục xây sẵn có thể nhanh khi đọc nhưng đắt khi dựng hoặc cập nhật.
7. **Đo bằng một kích thước quá nhỏ:** chi phí vòng lặp/đồng hồ lấn át chi phí thuật toán và cache giúp che các lần truy cập bộ nhớ.
8. **Dùng trung bình che độ trễ hiếm:** một lần resize hoặc rehash lớn có thể quan trọng với dịch vụ cần giới hạn thời gian phản hồi.
9. **So độ phức tạp từ đường cong ngắn:** vài điểm đo không đủ để suy chắc `O(log n)` hay `O(n)`, nhất là gần ranh giới cache.
10. **Bật kiểm tra bất biến trong benchmark hiệu năng:** kiểm tra toàn bộ `O(n)` sau mỗi cập nhật làm thay đổi chi phí thực của thao tác.
11. **Tuyên bố tổng RAM từ `getsizeof`:** phép gọi đó không tự cộng các đối tượng được tham chiếu và không phản ánh mọi cấp phát native.
12. **Bỏ qua quyền sở hữu và đồng thời:** so bản không có đồng bộ với bản cung cấp tính an toàn luồng có thể không phải cùng hợp đồng.

## 12. Bài tập tự kiểm tra

### Bài 1 — Chọn workload đúng

Một hệ thống có danh sách người đang chờ, gần như luôn có 20.000 phần tử. Nó liên tục lấy phần tử đầu và thêm phần tử mới vào cuối; hiếm khi đọc phần tử ở vị trí giữa. Hãy nêu hai cách biểu diễn và thiết kế phép đo công bằng.

**Gợi ý đáp án:** so `list` với `deque` (hoặc mảng vòng). Khởi tạo cùng `n = 20.000`, chạy cùng số cặp lấy đầu/thêm cuối, làm nóng và lặp lại trên trạng thái mới; xác minh thứ tự kết quả; báo trung vị thời gian theo thao tác và độ dao động. Nên đo bộ nhớ riêng và nhắc rằng kết luận chỉ áp dụng cho các thao tác hai đầu này.

### Bài 2 — Nhận diện phép đo gây nhiễu

Cho mã:

```python
start = perf_counter_ns()

for _ in range(10000):
    value = expensive_random_object()
    queue.enqueue(value)
    assert queue.check_all_invariants()

elapsed = perf_counter_ns() - start
```

Hãy xác định ít nhất hai nguồn chi phí đang được tính chung với `enqueue`.

**Gợi ý đáp án:** việc tạo đối tượng ngẫu nhiên và chạy `check_all_invariants` trong mỗi vòng; nếu hàm kiểm tra duyệt toàn bộ Queue thì chi phí có thể lớn hơn chính thao tác thêm. Cần tách pha tạo đầu vào và xác minh ra khỏi vùng đo nếu mục tiêu là đo riêng thao tác `enqueue`.

### Bài 3 — Phân biệt thông lượng và độ trễ

Một báo cáo ghi “thời gian trung bình trên một thao tác là 5 µs” từ tổng thời gian chạy 100.000 thao tác. Có thể suy trực tiếp rằng p99 của các thao tác bằng 5 µs không?

**Đáp án:** không. Thời gian tổng chia số thao tác chỉ cho **trung bình trên khối lượng đo**, không cho phân phối độ trễ. Một số thao tác có thể rất nhanh, một số khác bị trễ khi cấp phát lại, tái băm hoặc tranh chấp. Muốn biết p99 phải thu các mẫu độ trễ đủ nhiều với phương pháp phù hợp.

### Bài 4 — Tách kích thước và số thao tác

Bạn đo cùng một thuật toán với hai lần thử: lần A có `n = 1.000`, `m = 10.000`; lần B có `n = 10.000`, `m = 100.000`. Tổng thời gian lần B lớn hơn nhiều. Có thể kết luận một thao tác là `O(n)` không?

**Đáp án:** chưa thể. Cả kích thước lẫn số thao tác đều tăng. Hãy cố định `m` khi thay `n`, rồi cố định `n` khi thay `m`, đồng thời dùng phân tích thuật toán để giải thích đường cong quan sát được.

### Bài 5 — Đo HashMap theo tình huống thật

Hãy đề xuất một bảng thí nghiệm cho Map có 90% truy vấn đọc, 10% cập nhật, trong đó phần lớn truy vấn vào một tập khóa nóng; Map đôi khi phải tăng dung lượng.

**Gợi ý đáp án:** dùng một workload pha trộn với tỷ lệ rõ ràng, cùng tập khóa và seed ở mọi phiên bản; thử ít nhất hai kích thước dữ liệu, phân biệt hit/miss, khóa nóng/lạnh và ghi đè/thêm mới; đo thời gian tổng, phân phối độ trễ, các lần resize và bộ nhớ đỉnh. Kèm một workload phụ dùng phân phối đều để thấy mức nhạy cảm với tính cục bộ.

## 13. Quy trình thực hành khi chọn cấu trúc dữ liệu

1. **Viết yêu cầu:** phép toán nào chiếm nhiều thời gian, cần tối ưu tốc độ phản hồi, thông lượng hay RAM?
2. **Xác nhận hợp đồng:** cách xử lý phần tử trùng, lỗi, thứ tự, chỉ số và đồng thời có giống nhau giữa các phương án không?
3. **Chọn bộ dữ liệu đại diện:** kích thước, phân phối khóa/giá trị, trạng thái rỗng/đầy, mức cục bộ.
4. **Tạo chuỗi workload có thể tái hiện:** lưu seed, thao tác, tham số và tỷ lệ.
5. **Kiểm tra tính đúng đắn độc lập:** so với mô hình tham chiếu và bất biến cấu trúc.
6. **Đo có kiểm soát:** tách pha, warmup, lặp lại, ghi môi trường, không đưa công cụ xác minh vào đường định thời.
7. **Đo cả thời gian và bộ nhớ:** chú ý độ trễ đuôi, khởi tạo và cấp phát đỉnh.
8. **Phân tích độ tăng theo kích thước:** kiểm tra xu hướng dưới ánh sáng độ phức tạp trường hợp xấu nhất, kỳ vọng và khấu hao.
9. **Chốt lựa chọn theo tải thật:** ghi rõ điều kiện nào khiến lựa chọn còn phù hợp và khi nào cần đo lại.

Đo hiệu năng có giá trị khi phản ánh **đúng dữ liệu, đúng chuỗi thao tác và đúng yêu cầu quan sát được**. Độ phức tạp thuật toán giúp dự đoán xu hướng; một benchmark được thiết kế cẩn thận giúp biết sự đánh đổi về thời gian, bộ nhớ và độ ổn định có thực sự phù hợp với bài toán đang giải hay không.
