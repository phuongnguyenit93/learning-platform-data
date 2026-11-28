# Đánh đổi giữa tốc độ, bộ nhớ và độ phức tạp cài đặt

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao lựa chọn cấu trúc dữ liệu thường là bài toán **đánh đổi** giữa thời gian xử lý, bộ nhớ và chi phí xây dựng, bảo trì chương trình.
- Đọc đúng ký hiệu **O lớn (Big O)**, phân biệt trường hợp xấu nhất, kỳ vọng và khấu hao; tránh kết luận hiệu năng chỉ từ một con số.
- So sánh các phương án lưu dữ liệu bằng mảng, danh sách liên kết, bảng băm, cây cân bằng, heap và đồ thị trong những tình huống có mẫu thao tác khác nhau.
- Tính chi phí tổng của việc **xây dựng chỉ mục, truy vấn và cập nhật**, thay vì chỉ xem xét một phép tìm kiếm.
- Đề xuất một thiết kế đơn giản, nêu rõ **bất biến cần giữ** và xác định khi nào cần đo đạc hay thêm chỉ mục.

## 1. Bài toán chọn cấu trúc dữ liệu có nhiều mục tiêu

Giả sử nền tảng học tập lưu bài học và thường xuyên cần mở một bài theo mã `lesson_id`. Hai phương án ban đầu có thể là:

1. Lưu mọi bài trong một **danh sách**; mỗi lần tìm, duyệt từ đầu cho đến khi gặp mã phù hợp.
2. Lưu hoặc tạo thêm **bảng băm** ánh xạ mã sang bản ghi; mỗi lần tìm, tra trực tiếp theo khóa.

Phương án thứ hai thường tìm nhanh hơn khi số bài lớn và truy vấn lặp lại nhiều lần. Tuy nhiên, nó cần thêm bộ nhớ cho chỉ mục và có thêm công việc để cập nhật chỉ mục khi thêm, xóa hoặc đổi mã. Phương án thứ nhất có thể là lựa chọn tốt khi danh sách rất nhỏ, ít truy vấn hoặc yêu cầu triển khai đơn giản.

Có ba nhóm chi phí cần cân nhắc:

| Góc đánh giá | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Tốc độ** | Truy vấn, cập nhật và duyệt mất bao nhiêu thời gian? | Tra theo mã, thêm bài, lấy việc ưu tiên nhất |
| **Bộ nhớ** | Cần bao nhiêu dung lượng lâu dài và tạm thời? | Mảng dự phòng, nút liên kết, bảng băm, hàng đợi |
| **Độ phức tạp cài đặt** | Có bao nhiêu trạng thái, bất biến, trường hợp lỗi và thao tác phải bảo trì? | Đồng bộ danh sách và bảng tra; xử lý xóa, chu trình |

Ba góc đánh giá này liên quan đến nhau nhưng không thể thay thế lẫn nhau. Một phương án tăng tốc độ đọc có thể làm tăng bộ nhớ và tăng rủi ro dữ liệu không nhất quán; một phương án tiết kiệm bộ nhớ có thể làm truy vấn chậm hơn; một cấu trúc tối ưu về lý thuyết có thể khó kiểm tra hoặc khó sử dụng đúng.

> **Nguyên tắc xuất phát:** Chọn cấu trúc theo những **phép toán cần hỗ trợ và tần suất của chúng**, sau đó mới so sánh chi phí. Không có cấu trúc dữ liệu tốt nhất trong mọi tình huống.

## 2. Hiểu đúng chi phí thời gian trước khi so sánh

### 2.1. Big O mô tả xu hướng tăng trưởng

Với `n` là số phần tử, độ phức tạp tiệm cận mô tả cách số bước xử lý tăng khi `n` lớn lên:

| Ký hiệu | Ví dụ điển hình | Ý nghĩa trực quan |
| --- | --- | --- |
| **O(1)** | Truy cập phần tử mảng theo chỉ số hợp lệ | Không tăng theo số phần tử trong mô hình phân tích |
| **O(log n)** | Tìm nhị phân trên mảng đã sắp xếp | Phạm vi cần xét giảm một tỷ lệ cố định mỗi bước |
| **O(n)** | Duyệt toàn bộ danh sách | Công việc tăng theo số phần tử |
| **O(n log n)** | Một thuật toán sắp xếp so sánh hiệu quả | Tăng nhanh hơn tuyến tính nhưng chậm hơn bậc hai |
| **O(n²)** | So sánh mọi cặp phần tử bằng hai vòng lặp | Công việc có thể tăng gần bình phương quy mô |

Big O là giới hạn trên tiệm cận; muốn phát biểu chặt chẽ về tốc độ tăng *đúng bậc* thường dùng ký hiệu **Θ**. Trong những bảng chi phí nhập môn, “thao tác O(n)” thường là cách nói tắt về một giới hạn hữu ích dưới các giả định đã nêu.

**O(1) không có nghĩa luôn nhanh hơn O(n) trong mọi trường hợp thực tế.** Một phép tra bảng băm gồm tính băm, truy cập vùng chứa và kiểm tra khóa; quét một danh sách rất ngắn có thể ít tốn chi phí thực thi hơn. Big O không bao gồm đầy đủ hằng số, cache CPU, bộ cấp phát bộ nhớ hay chi phí gọi hàm.

### 2.2. Phải phân biệt trường hợp xấu nhất, kỳ vọng và khấu hao

- **Trường hợp xấu nhất (worst case):** giới hạn cho tình huống bất lợi nhất trong phạm vi giả định. Tìm tuyến tính trong danh sách `n` phần tử có thể phải kiểm tra đủ `n` phần tử.
- **Trung bình hoặc kỳ vọng (average/expected):** chi phí dựa trên một mô hình phân bố đầu vào hay giả định về thuật toán. Tra cứu bảng băm thường **O(1) kỳ vọng**, nhưng va chạm bất lợi có thể dẫn đến **O(n)**.
- **Khấu hao (amortized):** xem tổng chi phí của một chuỗi thao tác. Thêm cuối mảng động thường **O(1) khấu hao**: đôi khi phải mở rộng vùng nhớ và sao chép **O(n)** phần tử, nhưng không cần làm vậy ở mọi lần thêm.

Ba thuật ngữ này trả lời các câu hỏi khác nhau. Một dịch vụ cần giới hạn độ trễ nghiêm ngặt có thể quan tâm nhiều đến **trường hợp xấu nhất**, trong khi một công cụ xử lý dữ liệu nội bộ có thể chấp nhận biến động nếu thông lượng tổng tốt.

### 2.3. Độ phức tạp của một thao tác không phải chi phí của cả hệ thống

Giả sử có:

- `n`: số bài học;
- `q`: số lượt tìm theo mã;
- `u`: số lượt cập nhật bài hoặc chỉ mục.

Nếu không dùng chỉ mục, `q` lần quét danh sách có chi phí xấu nhất **O(qn)**. Nếu xây một bảng băm từ danh sách, chi phí xây ban đầu thường là **O(n)** thời gian kỳ vọng và **O(n)** bộ nhớ bổ sung; `q` lần tìm sau đó mất **O(q)** thời gian kỳ vọng. Tổng là **O(n + q)** nếu bỏ qua cập nhật và giả sử băm phân bố phù hợp.

Khi dữ liệu thay đổi, phải cộng chi phí `u` lần cập nhật. Nếu lưu cả danh sách và bảng băm, một số cập nhật có thể phải sửa **cả hai**. Trên một dịch vụ đang chạy, chi phí duy trì chỉ mục có thể quan trọng không kém tốc độ đọc.

## 3. Ví dụ: đánh đổi khi tìm bài học theo mã

Đoạn mã sau so sánh hai cách tổ chức **cùng một tập bản ghi**:

```python
lessons = [
    {"id": "ds-array", "title": "Mảng"},
    {"id": "ds-stack", "title": "Stack"},
    {"id": "ds-queue", "title": "Queue"},
]


def find_linear(lesson_id):
    for lesson in lessons:
        if lesson["id"] == lesson_id:
            return lesson
    return None


# Một chỉ mục bổ sung chứa tham chiếu tới bản ghi đã có.
by_id = {lesson["id"]: lesson for lesson in lessons}


def find_indexed(lesson_id):
    return by_id.get(lesson_id)


assert find_linear("ds-stack") == find_indexed("ds-stack")
assert find_linear("ds-missing") is None
assert find_indexed("ds-missing") is None
```

| Phương án | Tìm theo mã | Thêm dữ liệu | Bộ nhớ bổ sung | Độ phức tạp bảo trì |
| --- | --- | --- | --- | --- |
| Chỉ dùng danh sách | **O(n)** xấu nhất | Thêm cuối **O(1) khấu hao** | Không có chỉ mục theo mã | Ít trạng thái cần giữ đồng bộ |
| Danh sách + bảng băm `by_id` | **O(1) kỳ vọng** | Cập nhật danh sách và bảng băm | **O(n)** cho chỉ mục | Phải xử lý khóa trùng, xóa và đồng bộ |

Để tránh trả lời sai, bảng `by_id` phải phản ánh đúng tập bản ghi trong `lessons`. Nếu thêm một bài mới chỉ vào danh sách, `find_indexed` sẽ không tìm thấy bài dù dữ liệu đã tồn tại. Nếu xóa khỏi danh sách mà quên xóa khóa ở bảng băm, kết quả tra lại chứa bản ghi đã bị loại.

### 3.1. Cài đặt một lớp giữ nhất quán giữa hai biểu diễn

Một cách giảm lỗi là gom các thao tác cập nhật vào cùng một giao diện:

```python
class LessonCatalog:
    def __init__(self):
        self._ordered = []       # Giữ thứ tự nhập bài.
        self._by_id = {}         # Tra chính xác theo mã.

    def add(self, lesson_id, title):
        if lesson_id in self._by_id:
            raise ValueError("Mã bài học đã tồn tại")

        lesson = {"id": lesson_id, "title": title}
        self._ordered.append(lesson)
        self._by_id[lesson_id] = lesson

    def get(self, lesson_id):
        return self._by_id.get(lesson_id)

    def get_at(self, index):
        return self._ordered[index]

    def remove(self, lesson_id):
        if lesson_id not in self._by_id:
            raise KeyError("Bài học không tồn tại")

        lesson = self._by_id[lesson_id]
        self._ordered.remove(lesson)
        del self._by_id[lesson_id]
        return lesson


catalog = LessonCatalog()
catalog.add("ds-array", "Mảng")
catalog.add("ds-stack", "Stack")
catalog.add("ds-queue", "Queue")
assert catalog.get("ds-stack") == catalog.get_at(1)

removed = catalog.remove("ds-stack")
assert removed["id"] == "ds-stack"
assert catalog.get("ds-stack") is None
assert catalog.get_at(1)["id"] == "ds-queue"
```

Trong ví dụ này, `get` theo mã thường **O(1) kỳ vọng**, `get_at` theo chỉ số **O(1)**, `add` thường **O(1) khấu hao/kỳ vọng**, còn `remove` có thể mất **O(n)** vì phải tìm bản ghi trong danh sách và dồn những phần tử sau nó. Bảng băm không làm phép xóa khỏi danh sách trở thành O(1).

**Bất biến quan trọng:** mỗi bài trong `_ordered` có đúng một mã trong `_by_id`, và bảng băm trỏ đến đúng bản ghi ở danh sách. Đây là mô hình minh họa trong một tiến trình; chương trình thực tế còn cần xử lý trường hợp cập nhật lỗi giữa chừng, lưu bền vững và truy cập đồng thời. Việc **đóng gói giao diện cập nhật** giúp dễ kiểm soát bất biến, nhưng không tự thay thế cơ chế giao dịch khi cần.

### 3.2. Khi nào chỉ mục phụ đáng giá?

Chỉ mục thường có ích khi:

1. Dữ liệu đủ lớn để quét tuyến tính gây độ trễ đáng kể.
2. Truy vấn cùng loại được lặp lại nhiều lần.
3. Bộ nhớ đủ để chứa cấu trúc bổ sung.
4. Tần suất cập nhật và chi phí giữ chỉ mục nhất quán là chấp nhận được.

Ngược lại, với vài chục phần tử được tra cứu thỉnh thoảng, một danh sách và phép quét có thể là giải pháp sáng sủa nhất. Đừng tạo chỉ mục chỉ để đạt một ký hiệu Big O đẹp hơn nếu nhu cầu thực tế chưa yêu cầu.

## 4. Cùng là lưu một dãy: mảng động, danh sách liên kết, stack và queue

Mỗi cấu trúc có một “hồ sơ chi phí” khác nhau theo từng thao tác:

| Thao tác | Mảng động | Danh sách liên kết đơn | Ý nghĩa thực tế |
| --- | --- | --- | --- |
| Lấy phần tử thứ `i` | **O(1)** | **O(n)** xấu nhất | Mảng thuận lợi cho truy cập theo vị trí |
| Duyệt tuần tự `n` phần tử | **O(n)** | **O(n)** | Cùng bậc nhưng tính cục bộ bộ nhớ khác nhau |
| Thêm cuối | **O(1) khấu hao** | **O(1)** nếu có con trỏ cuối | Mảng có lúc mở rộng; danh sách cấp phát nút |
| Chèn tại vị trí đã biết | Có thể **O(n)** vì dồn phần tử | **O(1)** nếu có đủ tham chiếu liên kết | Tìm được vị trí trước đó có thể đã mất O(n) |
| Tìm theo giá trị không có chỉ mục | **O(n)** | **O(n)** | Đều có thể phải đi qua toàn bộ dãy |
| Bộ nhớ cho `n` phần tử | **O(n)**, có sức chứa dự phòng | **O(n)**, thêm vùng cho liên kết/nút | Cùng bậc nhưng số byte thực tế khác |

**Mảng động** thường thuận lợi khi đọc theo chỉ số hoặc duyệt tuần tự, nhờ các ô tham chiếu đặt gần nhau trong bộ nhớ. **Danh sách liên kết** thích hợp khi thường xuyên chèn/xóa ở vị trí nút đã biết và có lợi từ việc không phải dịch cả dãy. Tuy nhiên, mỗi nút tốn thêm tham chiếu và chi phí cấp phát; việc đi theo những con trỏ rải rác có thể kém thân thiện với cache.

Stack và queue là những **kiểu dữ liệu trừu tượng (ADT)** mô tả thứ tự lấy phần tử:

- **Stack:** LIFO, vào sau ra trước; dùng cho lịch sử hoàn tác, DFS.
- **Queue:** FIFO, vào trước ra trước; dùng cho hàng đợi yêu cầu, BFS.

Một queue dùng `collections.deque` của Python có thể thêm cuối và lấy đầu trong **O(1)**. Nếu lại dùng `list.pop(0)`, mỗi lần lấy đầu mất **O(n)** vì các phần tử còn lại phải dịch chuyển. **Cùng hợp đồng FIFO** nhưng cách cài đặt làm thay đổi tốc độ. Cấu trúc dữ liệu phải được đánh giá theo đúng **phép toán mà thuật toán gọi thường xuyên**.

## 5. Đổi chi phí lấy cực trị: heap hay danh sách đã sắp xếp?

Giả sử hệ thống chấm bài phải luôn xử lý **bài nộp có hạn chót sớm nhất**. Các cách tổ chức dữ liệu đều có thể trả kết quả đúng, nhưng chi phí khác nhau:

| Cách lưu công việc | Xem hạn sớm nhất | Thêm công việc | Lấy và xóa hạn sớm nhất |
| --- | --- | --- | --- |
| Danh sách không sắp xếp | **O(n)** để tìm nhỏ nhất | **O(1) khấu hao** | **O(n)** để tìm và xóa |
| Mảng luôn sắp xếp tăng theo hạn | **O(1)** ở đầu | **O(n)** do chèn dịch phần tử | **O(n)** nếu lấy đầu và dịch phần tử |
| Min-heap nhị phân | **O(1)** tại gốc | **O(log n)** | **O(log n)** |

Với một khối lượng công việc chỉ thêm liên tục và đôi khi cần lấy cực trị, **min-heap** thường cân bằng tốt các thao tác. Khi dùng heap, phải giữ bất biến: **độ ưu tiên của mỗi nút cha không lớn hơn các nút con**. Cấu trúc heap không bảo đảm toàn bộ mảng đã được sắp xếp, nên truy vấn “liệt kê các công việc theo hạn tăng dần mà không phá hủy heap” có thể cần thêm xử lý.

```python
import heapq

pending = []

# Tuple: (hạn chót, thứ tự đến, mã bài nộp).
# Bộ đếm thứ tự đến bảo đảm FIFO nếu hai hạn chót bằng nhau.
heapq.heappush(pending, (12, 0, "submission-a"))
heapq.heappush(pending, (8, 1, "submission-b"))
heapq.heappush(pending, (8, 2, "submission-c"))

assert pending[0][2] == "submission-b"
assert heapq.heappop(pending)[2] == "submission-b"
assert heapq.heappop(pending)[2] == "submission-c"
```

Với bài toán cần **xóa một công việc bất kỳ theo mã**, heap đơn thuần không giúp tra nhanh mã bất kỳ. Có thể bổ sung bảng băm, dùng cơ chế xóa lười (*lazy deletion*) hoặc thiết kế heap có chỉ mục. Đổi lại, mã cài đặt và số bất biến cần kiểm soát tăng lên. Chỉ nên bổ sung khi yêu cầu thực sự có thao tác đó.

## 6. Đồ thị: tiết kiệm bộ nhớ hay tăng tốc kiểm tra cạnh?

Đồ thị gồm **`V` đỉnh** và **`E` cạnh**. Ví dụ trong nền tảng học tập, đỉnh là bài học và cạnh có hướng biểu diễn quan hệ tiên quyết. Hai cách lưu thông dụng:

**Danh sách kề:** với mỗi bài, lưu các bài kề hoặc các bài tiên quyết tương ứng.

```python
prerequisites = {
    "intro": [],
    "arrays": ["intro"],
    "stack": ["arrays"],
    "queue": ["arrays"],
    "graph": ["stack", "queue"],
}
```

**Ma trận kề:** tạo bảng `V × V`; ô `[u][v]` thể hiện có hay không có cạnh từ đỉnh `u` tới đỉnh `v`.

| Phép toán / tài nguyên | Danh sách kề | Ma trận kề |
| --- | --- | --- |
| Bộ nhớ | **O(V + E)** | **O(V²)** |
| Kiểm tra có cạnh `u → v` | **O(deg(u))** với danh sách; **O(1) kỳ vọng** nếu lưu hàng xóm bằng tập băm | **O(1)** khi đã biết chỉ số của hai đỉnh |
| Liệt kê các đỉnh kề `u` | **O(deg(u))** | **O(V)** để quét hàng |
| Duyệt BFS/DFS toàn bộ | **O(V + E)** | Thường **O(V²)** |

Trong đó `deg(u)` là số cạnh đi ra từ đỉnh `u` trong đồ thị có hướng. Nếu số cạnh ít so với `V²`, đồ thị được gọi là **thưa**; danh sách kề thường tiết kiệm bộ nhớ hơn nhiều.

Chẳng hạn, với `V = 10.000` đỉnh, một ma trận có **100 triệu ô** dù đồ thị chỉ có vài chục nghìn cạnh. Không thể suy ra chính xác số byte nếu chưa biết ô được biểu diễn bằng bit, byte hay đối tượng; nhưng mức tăng **theo bình phương số đỉnh** là vấn đề thiết kế cần lưu ý.

Ở đồ thị **dày đặc**, `E` có thể cùng bậc với `V²`, khiến chi phí bộ nhớ của danh sách kề và ma trận kề đều thuộc O(V²), song các thao tác kiểm tra cạnh và liệt kê hàng xóm vẫn có đặc điểm khác nhau.

**Bất biến quan trọng:** mọi cạnh phải tham chiếu đến đỉnh hợp lệ; nếu bài học có quan hệ tiên quyết, đồ thị phải **không có chu trình có hướng** để tồn tại một thứ tự học thỏa điều kiện. Tiết kiệm bộ nhớ bằng cách bỏ dữ liệu kiểm tra quan hệ sẽ không có giá trị nếu thuật toán không còn đưa ra kết quả đúng.

## 7. Cây tìm kiếm và bảng băm: đánh đổi thứ tự để tra khóa

Khi thao tác chủ yếu là **tra chính xác theo mã**, bảng băm là một ứng viên phù hợp. Khi cần thêm **truy vấn khoảng, duyệt theo khóa tăng dần hoặc tìm phần tử ngay trước/sau**, cấu trúc giữ thứ tự trở nên hữu ích.

| Nhu cầu | Bảng băm | Cây tìm kiếm cân bằng |
| --- | --- | --- |
| Tra chính xác theo khóa | **O(1) kỳ vọng** | **O(log n)** |
| Thêm / xóa theo khóa | **O(1) kỳ vọng, khấu hao** | **O(log n)** |
| Duyệt tất cả khóa đã sắp | Phải sắp xếp thêm, thường **O(n log n)** | Duyệt theo thứ tự **O(n)** |
| Tìm các khóa trong một khoảng | Không tự có lợi thế theo thứ tự | **O(log n + k)** để tìm và xuất `k` kết quả với cách duyệt phù hợp |
| Bộ nhớ | **O(n)** cho vùng băm và sức chứa dự phòng | **O(n)** cho các nút, liên kết và metadata cân bằng |
| Độ phức tạp cài đặt | Xử lý băm, va chạm, mở rộng | Xử lý thứ tự và thao tác cân bằng cây |

**Không phải mọi cây nhị phân đều có độ sâu O(log n)**. Một cây tìm kiếm nhị phân không cân bằng có thể biến thành chuỗi nút, khiến tìm/chèn/xóa tốn **O(n)**. Kết quả trong bảng cần điều kiện **cây được cân bằng**.

Nếu một bảng dữ liệu luôn cần hiển thị theo thứ tự biên tập nhưng tra theo mã rất nhiều, có thể kết hợp **mảng theo vị trí** và **bảng băm theo mã**. Nếu cần truy vấn cả theo mã, theo khoảng thời lượng và theo quan hệ tiên quyết, có thể phải duy trì thêm chỉ mục sắp xếp và đồ thị. Mỗi yêu cầu thêm vào hệ thống mang theo một chi phí cập nhật và kiểm chứng nhất quán.

## 8. Độ phức tạp cài đặt là một chi phí có thật

Không có ký hiệu Big O chuẩn nào đo trực tiếp “độ khó bảo trì”. Tuy nhiên, có thể đánh giá bằng những câu hỏi cụ thể:

1. **Có bao nhiêu nguồn trạng thái?** Một danh sách dễ kiểm soát hơn khi chỉ có một nguồn dữ liệu; thêm chỉ mục tạo ra nhiều biểu diễn phải đồng bộ.
2. **Có bao nhiêu bất biến?** Khóa duy nhất, thứ tự sắp xếp, tính chất heap, cha – con của cây và điều kiện không chu trình đều cần được duy trì.
3. **Có bao nhiêu trường hợp biên?** Dữ liệu rỗng, khóa trùng, xóa phần tử không tồn tại, tràn sức chứa, quan hệ tham chiếu bị xóa.
4. **Cập nhật có thể thất bại ở giữa không?** Ghi bản ghi thành công nhưng cập nhật chỉ mục thất bại khiến dữ liệu không nhất quán nếu không có cơ chế khôi phục.
5. **Có truy cập đồng thời không?** Nhiều luồng hoặc nhiều yêu cầu cùng sửa dữ liệu có thể cần khóa, giao dịch hoặc cấu trúc hỗ trợ đồng thời.
6. **Đội ngũ có thư viện đã được kiểm chứng chưa?** Cài lại heap, cây cân bằng hoặc bảng băm từ đầu có thể tăng lỗi và chi phí bảo trì khi thư viện chuẩn đã đáp ứng yêu cầu.

Ví dụ, một cấu trúc heap kèm bảng tra `job_id → vị trí trong heap` có thể tăng tốc việc cập nhật ưu tiên một công việc cụ thể. Nhưng sau **mỗi lần hoán đổi hai nút heap**, bảng vị trí cũng phải được cập nhật. Nếu quên một lần, việc sửa ưu tiên về sau có thể tác động sai công việc dù heap nhìn bên ngoài vẫn có vẻ hợp lệ.

Đối với bài toán đơn giản, việc **dùng cấu trúc được cung cấp sẵn và giới hạn số chỉ mục phụ** thường giúp giảm bề mặt lỗi. Khi phải xây cấu trúc riêng, cần mô tả hợp đồng và bất biến, cùng kiểm tra các trường hợp cập nhật làm thay đổi thứ tự hoặc liên kết.

## 9. Tối ưu bộ nhớ cũng cần xem xét hành vi truy cập

Hai cấu trúc đều dùng **O(n)** bộ nhớ nhưng số byte và hiệu quả sử dụng cache có thể rất khác nhau:

- **Mảng động** có thể giữ sức chứa dự phòng; các ô tham chiếu thường nằm gần nhau, thuận tiện cho duyệt tuần tự.
- **Danh sách liên kết** cần thêm vùng lưu nút và tham chiếu; các nút có thể phân tán trong bộ nhớ, làm tăng chi phí cấp phát và truy cập.
- **Bảng băm** cần duy trì vùng chứa đủ rộng để tìm kiếm hiệu quả; hệ số tải và chiến lược giải quyết va chạm ảnh hưởng thời gian lẫn bộ nhớ.
- **Đồ thị danh sách kề** tiết kiệm khi thưa; **ma trận kề** có thể hữu ích khi mật độ cạnh cao hoặc kiểm tra cạnh chiếm tỷ trọng lớn.
- **Cấu trúc bất biến có chia sẻ cấu trúc** có thể tái sử dụng nhiều phần không đổi giữa các phiên bản, nhưng các phiên bản còn được tham chiếu vẫn chiếm bộ nhớ.

Cần phân biệt **bộ nhớ giữ lâu dài**, **bộ nhớ phụ trong một thuật toán** và **bộ nhớ cao nhất tại thời điểm xử lý**. Chẳng hạn, tạo mảng kết quả đã sắp xếp có thể cần thêm O(n) bộ nhớ trong lúc xây dựng; một lần tái phân bổ mảng động cũng có thể tạm thời cần cả vùng cũ và vùng mới.

Một đánh đổi quen thuộc là **đổi bộ nhớ lấy thời gian**: lưu kết quả đã tính, tạo chỉ mục, duy trì tập `visited` khi duyệt đồ thị. Nhưng đổi bộ nhớ lấy thời gian chỉ hợp lý nếu bộ nhớ bổ sung nằm trong giới hạn và kết quả được cập nhật hoặc vô hiệu hóa đúng lúc khi dữ liệu thay đổi.

## 10. Từ nhu cầu đến quyết định: một ví dụ tổng hợp

Một dịch vụ học tập cần đồng thời:

- Hiển thị bài trong chương theo thứ tự biên tập.
- Mở bài theo mã nhanh.
- Lấy bài có thời lượng trong một khoảng.
- Kiểm tra các bài học tiên quyết.
- Tiếp nhận bài nộp theo thứ tự đến.

Có thể bắt đầu bằng những cấu trúc phục vụ trực tiếp các phép toán:

| Phép toán nghiệp vụ | Cấu trúc khởi đầu | Chi phí chính cần theo dõi |
| --- | --- | --- |
| Lấy bài thứ `i` trong chương | Mảng động chứa mã bài | Truy cập O(1); thay vị trí giữa dãy O(n) |
| Mở bài theo `lesson_id` | Bảng băm ánh xạ mã đến bản ghi | Tra O(1) kỳ vọng; bộ nhớ và đồng bộ chỉ mục |
| Tìm theo khoảng thời lượng | Lúc đầu quét toàn bộ hoặc sắp xếp khi cần | O(n) khi quét; nếu sắp xếp lại mỗi lần có thể O(n log n) |
| Kiểm tra quan hệ tiên quyết | Đồ thị có hướng với danh sách kề | Duyệt tới O(V + E); kiểm tra chu trình khi sửa cạnh |
| Lấy yêu cầu chấm bài đến sớm nhất | Queue dùng deque | Thêm cuối/lấy đầu O(1) |

Nếu truy vấn theo khoảng thời lượng trở nên thường xuyên và tốn thời gian, mới cân nhắc duy trì **chỉ mục có thứ tự**. Khi bổ sung nó, cần xác định việc sửa thời lượng hoặc xóa bài ảnh hưởng đến chỉ mục ra sao. Đó là quyết định dựa trên **phép đo và mẫu sử dụng**, không phải cố gắng dùng mọi cấu trúc ngay từ đầu.

### 10.1. Mô hình chi phí theo khối lượng công việc

Có thể ước lượng tương đối bằng cách chia việc thành các nhóm:

| Đại lượng | Ý nghĩa |
| --- | --- |
| `n` | Số phần tử hoặc bản ghi |
| `q_id` | Số lượt tra theo mã |
| `q_range` | Số lượt tìm theo khoảng |
| `u` | Số lượt thêm, xóa hoặc sửa |
| `V, E` | Số đỉnh và cạnh của đồ thị quan hệ |

Nếu hệ thống **không có chỉ mục mã**, chi phí tra mã trong trường hợp xấu nhất là O(`q_id · n`). Nếu duy trì bảng băm, việc xây chỉ mục mất O(n) kỳ vọng, `q_id` lần tra mất O(`q_id`) kỳ vọng, và còn chi phí cập nhật chỉ mục khi có `u` lần ghi.

Nếu hệ thống **sắp xếp lại từ đầu cho mọi truy vấn khoảng**, mỗi truy vấn có thể tốn O(n log n + k) trong mô hình sắp xếp so sánh. Nếu lưu dãy đã sắp xếp và giữ nó nhất quán, truy vấn khoảng có thể O(log n + k), nhưng thêm hoặc xóa ở giữa dãy vẫn có thể O(n).

Đây là các **mô hình để so sánh**, chưa phải thời gian tính bằng mili giây. Muốn ra quyết định vận hành, cần đo trên dữ liệu thực tế, đúng tỷ lệ đọc/ghi, thời gian phản hồi ở các mức tải và dung lượng bộ nhớ lớn nhất cho phép.

### 10.2. Một quy trình ra quyết định thực tế

1. **Chốt chức năng đúng:** xác định thao tác, thứ tự cần bảo toàn, khóa duy nhất và các bất biến.
2. **Ước lượng mẫu tải:** số phần tử, loại truy vấn, tần suất cập nhật và giới hạn tài nguyên.
3. **Chọn phương án đơn giản đáp ứng yêu cầu:** có thể bắt đầu từ danh sách, bảng băm, deque hoặc cấu trúc tiêu chuẩn của ngôn ngữ.
4. **Tính chi phí tổng:** kể cả chuẩn bị, đọc, ghi, bộ nhớ phụ, xử lý lỗi và giữ nhất quán.
5. **Đo trước khi tối ưu:** thử dữ liệu nhỏ/lớn, trường hợp điển hình và bất lợi; theo dõi độ trễ và bộ nhớ.
6. **Chỉ thêm cấu trúc phụ khi có lợi rõ ràng:** lưu tài liệu về các bất biến và những nơi phải cập nhật chỉ mục.
7. **Kiểm tra lại sau khi thay đổi:** một chỉ mục mới có thể tăng tốc đọc nhưng làm chậm ghi hoặc phát sinh rủi ro đồng bộ.

## 11. Những hiểu lầm thường gặp

- **“O(1) luôn nhanh hơn O(n).”** Không đúng với mọi `n`: hằng số thực thi và vị trí dữ liệu trong bộ nhớ ảnh hưởng đáng kể, nhất là khi tập dữ liệu nhỏ.
- **“Bảng băm tra O(1) nên không tốn bộ nhớ thêm.”** Sai: nó cần không gian cho các khóa, vùng chứa và có thể cả chỉ mục phụ.
- **“Danh sách liên kết luôn thêm/xóa nhanh hơn mảng.”** Thiếu điều kiện: chỉ nhanh ở vị trí đã có đủ tham chiếu; tìm vị trí có thể mất O(n), và nút liên kết tốn thêm bộ nhớ.
- **“Dùng cây là tự động có O(log n).”** Sai: cần cây tìm kiếm **cân bằng** và thuật toán duy trì cân bằng phù hợp.
- **“Heap có thể tìm bất kỳ phần tử nhanh như bảng băm.”** Sai: heap được tổ chức để lấy cực trị; tìm một khóa tùy ý có thể mất O(n).
- **“Đã thêm chỉ mục thì mọi thao tác đều nhanh hơn.”** Sai: đọc có thể tốt hơn nhưng cập nhật, bộ nhớ và độ phức tạp giữ nhất quán tăng.
- **“Độ phức tạp cài đặt chỉ liên quan đến số dòng mã.”** Sai: những bất biến, trường hợp lỗi, cập nhật đồng thời và chi phí bảo trì quan trọng hơn số dòng.
- **“Chỉ cần đo trên một triệu phần tử là đủ.”** Chưa đủ: phải mô phỏng các loại thao tác và tỷ lệ đọc/ghi tương ứng với sản phẩm.

## 12. Bài tập vận dụng

**Bài 1 — Có nên xây bảng băm?** Một ứng dụng có 40 bài học và mỗi ngày chỉ mở bài bằng mã vài lần. Một ứng dụng khác có hàng triệu bài và liên tục tra theo mã. Hãy giải thích vì sao lựa chọn cấu trúc ban đầu có thể khác nhau.

*Gợi ý:* Với 40 phần tử, quét tuyến tính đơn giản và có thể đủ nhanh. Với lượng dữ liệu lớn, nhiều truy vấn, bảng băm có thể giảm thời gian tìm theo khóa; phải trả chi phí xây dựng, bộ nhớ và duy trì chỉ mục.

**Bài 2 — Chọn cấu trúc cho lịch xử lý.** Hệ thống luôn cần lấy bài nộp có hạn chót sớm nhất. So sánh danh sách không sắp xếp và min-heap về thêm, xem và lấy phần tử sớm nhất.

*Gợi ý:* Danh sách không sắp xếp thêm cuối O(1) khấu hao nhưng tìm cực trị O(n); min-heap xem O(1), thêm/lấy O(log n), đổi lại phải bảo vệ tính chất heap.

**Bài 3 — Đồ thị thưa.** Một đồ thị có `V = 20.000` đỉnh và khoảng `E = 60.000` cạnh. Vì sao danh sách kề thường tiết kiệm bộ nhớ hơn ma trận kề? Có trường hợp nào ma trận kề đáng xem xét?

*Gợi ý:* Danh sách kề tăng theo O(V + E), ma trận theo O(V²). Ma trận có lợi thế kiểm tra trực tiếp cạnh theo chỉ số O(1) và có thể phù hợp cho đồ thị dày đặc.

**Bài 4 — Bất biến giữa chỉ mục.** Một bài học bị xóa khỏi danh sách nhưng vẫn tồn tại trong bảng băm tra mã. Hệ quả là gì? Cần bảo đảm những gì khi xóa?

*Gợi ý:* Hai cách truy cập đưa ra kết quả trái nhau. Thao tác xóa phải điều chỉnh mọi biểu diễn liên quan hoặc dùng cơ chế cập nhật nhất quán có khả năng phục hồi lỗi.

**Bài 5 — Tối ưu có đo lường.** Mỗi ngày hệ thống nhận hàng trăm lần thêm bài, nhưng rất hiếm khi tìm theo khoảng thời lượng. Có nên luôn duy trì một cây tìm kiếm cân bằng chỉ cho truy vấn khoảng?

*Gợi ý:* So sánh lợi ích của vài truy vấn hiếm với bộ nhớ và chi phí cập nhật cây ở mọi lần ghi. Ban đầu quét hoặc sắp xếp khi cần có thể hợp lý hơn.

**Bài 6 — Đọc đúng Big O.** Vì sao có thể nói `list.append` của Python là O(1) khấu hao dù đôi khi một lần thêm cuối phải sao chép nhiều tham chiếu?

*Gợi ý:* Với chiến lược mở rộng dung lượng thích hợp, chi phí lớn xuất hiện thưa hơn khi mảng tăng trưởng; chia tổng chi phí của nhiều lần thêm cho số lần thêm cho ra chi phí trung bình khấu hao bị chặn bởi hằng số.

## Tổng kết

Lựa chọn cấu trúc dữ liệu là quyết định về **toàn bộ chi phí của bài toán**, gồm tốc độ đọc/ghi, bộ nhớ và mức khó duy trì mã đúng. Mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị có những ưu thế khác nhau tùy phép toán. Một giải pháp có thể đổi bộ nhớ lấy thời gian bằng chỉ mục phụ, đổi tính linh hoạt lấy thao tác đơn giản, hoặc chấp nhận thuật toán chậm hơn trên dữ liệu nhỏ để giảm lỗi và chi phí bảo trì. Hãy bắt đầu từ **bất biến và hành vi đúng**, tính chi phí theo tải thực tế, đo hiệu năng rồi mới bổ sung cấu trúc phức tạp khi lợi ích đã rõ.
