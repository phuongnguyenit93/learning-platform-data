# Cấu trúc dữ liệu là gì và vì sao cần tổ chức dữ liệu?

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **cấu trúc dữ liệu** là gì và phân biệt dữ liệu, kiểu dữ liệu, cấu trúc dữ liệu với thuật toán.
- Nhận diện các thao tác mà một ứng dụng cần thực hiện trên dữ liệu: truy cập, tìm kiếm, thêm, xóa, cập nhật, duyệt và sắp xếp.
- Hiểu vì sao cùng một tập dữ liệu nhưng cách tổ chức khác nhau có thể dẫn đến chi phí thời gian và bộ nhớ rất khác nhau.
- Nhận biết vai trò ban đầu của mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.
- Đặt đúng câu hỏi khi lựa chọn cấu trúc dữ liệu cho một bài toán thực tế.

## 1. Dữ liệu có mặt ở khắp nơi, nhưng lưu được chưa có nghĩa là dùng được

Hãy hình dung một thư viện có hàng trăm nghìn cuốn sách. Nếu tất cả sách được xếp thành một đống, thư viện vẫn **có đầy đủ dữ liệu** về sách, nhưng tìm một cuốn theo mã, liệt kê sách của một tác giả hoặc lấy cuốn đến hạn trả sớm nhất sẽ rất khó. Khi sách được đặt trên kệ theo chủ đề, có mục lục tra theo mã và có danh sách mượn trả, cùng lượng sách ấy trở nên dễ khai thác hơn.

Phần mềm gặp vấn đề tương tự. Một nền tảng học tập có thể lưu bài học, tài khoản, tiến độ, bài kiểm tra và quan hệ tiên quyết giữa các khóa học. Các câu hỏi đặt ra không chỉ là *có lưu được không*, mà còn là:

- Tìm bài học mang mã `lesson-104` nhanh đến mức nào?
- Hiển thị các bài theo đúng thứ tự trong chương bằng cách nào?
- Đưa yêu cầu chấm bài vào hàng đợi và xử lý theo thứ tự nào?
- Chọn tác vụ có độ ưu tiên cao nhất ra sao?
- Biết được cần học những chủ đề nào trước một chủ đề khác bằng cách nào?

**Cấu trúc dữ liệu (data structure)** là cách tổ chức và biểu diễn các phần tử dữ liệu cùng các quan hệ giữa chúng, sao cho những thao tác cần thiết có thể được thực hiện theo những quy tắc và mức chi phí phù hợp.

Hai ý quan trọng nằm trong định nghĩa này:

1. **Tổ chức:** các phần tử nằm theo một thứ tự, được nối với nhau, được ánh xạ bởi khóa hay được liên kết thành các quan hệ.
2. **Thao tác:** chương trình có cách truy cập, thêm, xóa, tìm, duyệt hoặc lấy phần tử theo một quy tắc xác định.

Không có cấu trúc dữ liệu nào tốt nhất cho mọi câu hỏi. Cách tổ chức phù hợp phụ thuộc vào **thao tác được dùng thường xuyên**, quy mô dữ liệu và các ràng buộc của bài toán.

## 2. Phân biệt dữ liệu, kiểu dữ liệu, cấu trúc dữ liệu và thuật toán

| Khái niệm | Trả lời câu hỏi | Ví dụ trong hệ thống bài học |
| --- | --- | --- |
| **Dữ liệu** | Ta đang lưu thông tin gì? | `"lesson-104"`, `25`, tên bài học, thời điểm hoàn thành |
| **Kiểu dữ liệu** | Một giá trị thuộc loại nào và có thể dùng các phép toán gì? | Chuỗi, số nguyên, boolean, đối tượng `Lesson` |
| **Cấu trúc dữ liệu** | Nhiều giá trị được tổ chức và thao tác ra sao? | Danh sách bài học, bảng ánh xạ mã bài học đến đối tượng bài học |
| **Thuật toán** | Các bước để giải quyết một nhiệm vụ là gì? | Tìm bài theo mã, duyệt các bài tiên quyết, sắp xếp theo hạn nộp |

Cấu trúc dữ liệu và thuật toán gắn bó chặt chẽ: thuật toán thao tác **trên** cấu trúc dữ liệu; cách tổ chức dữ liệu quyết định những thao tác nào nhanh, chậm hoặc phức tạp khi triển khai.

Một điểm phân biệt khác là **kiểu dữ liệu trừu tượng (abstract data type — ADT)** và **cách cài đặt**. Chẳng hạn, stack được mô tả bằng quy tắc *vào sau, ra trước* cùng thao tác `push`/`pop`; stack có thể được cài đặt bằng mảng động hoặc danh sách liên kết. Quy tắc sử dụng là một phần của mô hình trừu tượng; việc chọn vùng nhớ và liên kết các phần tử thuộc về cách cài đặt cụ thể.

## 3. Tại sao tổ chức dữ liệu lại quan trọng?

### 3.1. Cùng dữ liệu, khác chi phí tìm kiếm

Giả sử hệ thống lưu các đơn đăng ký học dưới dạng một danh sách và cần tìm đăng ký theo mã:

```python
registrations = [
    {"id": "r-101", "learner": "An", "course": "DS"},
    {"id": "r-102", "learner": "Bình", "course": "DS"},
    {"id": "r-103", "learner": "Chi", "course": "Algo"},
]


def find_by_id_linear(registration_id):
    for item in registrations:
        if item["id"] == registration_id:
            return item
    return None


# Tạo chỉ mục: mã đăng ký -> bản ghi đăng ký.
registrations_by_id = {item["id"]: item for item in registrations}


def find_by_id_indexed(registration_id):
    return registrations_by_id.get(registration_id)


assert find_by_id_linear("r-103") == find_by_id_indexed("r-103")
```

Hai hàm trả về cùng kết quả, nhưng cách tìm khác nhau:

- **Duyệt danh sách:** so sánh lần lượt từng bản ghi; với `n` phần tử, trường hợp xấu nhất cần xem `n` phần tử, tức độ phức tạp thời gian **O(n)**.
- **Tra bảng băm:** `dict` của Python dùng bảng băm; tra theo khóa thường có thời gian trung bình kỳ vọng **O(1)**, nhưng trường hợp xấu nhất có thể lên đến **O(n)**.

Nếu có một triệu bản ghi, tìm tuyến tính có thể phải kiểm tra đến một triệu phần tử cho mỗi lần truy vấn. Bảng tra cứu theo khóa thường hữu ích khi hệ thống liên tục tìm bằng mã định danh. Tuy nhiên, chỉ mục bổ sung cần **O(n) bộ nhớ**, phải được xây dựng và phải cập nhật khi dữ liệu thay đổi.

Ví dụ khi thêm một đăng ký mới, cả danh sách lẫn bảng tra cứu phải thống nhất:

```python
def add_registration(item):
    if item["id"] in registrations_by_id:
        raise ValueError("Mã đăng ký đã tồn tại")
    registrations.append(item)
    registrations_by_id[item["id"]] = item


add_registration({"id": "r-104", "learner": "Dung", "course": "DS"})
assert find_by_id_indexed("r-104")["learner"] == "Dung"
```

Đây là ví dụ đơn giản chạy trong một tiến trình; ứng dụng thực tế còn phải xử lý lỗi giữa các bước cập nhật, ghi bền vững và truy cập đồng thời để tránh hai cách biểu diễn dữ liệu mất đồng bộ.

### 3.2. Các thao tác khác nhau cần cách tổ chức khác nhau

Khi câu hỏi đổi từ *tìm theo mã* sang *lấy đăng ký mới nhất*, *lấy yêu cầu cũ nhất* hay *lấy bài cần xử lý gấp nhất*, bảng băm không còn tự động là câu trả lời tốt nhất. Có thể cần một cấu trúc giữ thứ tự, một queue hoặc một heap.

Ví dụ, yêu cầu chấm bài thường được tiếp nhận trước thì xử lý trước, tức nguyên tắc **FIFO — vào trước, ra trước**:

```python
from collections import deque

grading_queue = deque(["submission-01", "submission-02"])
grading_queue.append("submission-03")  # Thêm vào cuối hàng đợi.

next_submission = grading_queue.popleft()  # Lấy phần tử đầu tiên.
assert next_submission == "submission-01"
```

Với `collections.deque`, thêm cuối và lấy đầu đều có chi phí **O(1)**. Ngược lại, nếu dùng `list.pop(0)` trong Python, các phần tử còn lại phải dịch vị trí nên thao tác này mất **O(n)**. Đây là ví dụ cho thấy *cách cài đặt* ảnh hưởng trực tiếp đến chi phí của cùng một thao tác logic.

### 3.3. Tính đúng đắn cũng phụ thuộc vào tổ chức dữ liệu

Cấu trúc dữ liệu không chỉ có mục tiêu tăng tốc. Nó còn giúp biểu diễn và bảo vệ **bất biến (invariant)** — những điều kiện phải luôn đúng sau mỗi thao tác hợp lệ:

- Bảng tra theo mã đăng ký: mỗi mã định danh duy nhất tương ứng một bản ghi.
- Stack lịch sử hoàn tác: thao tác được thêm gần nhất là thao tác được lấy ra đầu tiên.
- Queue chấm bài: nếu không có chính sách ưu tiên khác, yêu cầu được đưa vào trước được lấy ra trước.
- Min-heap: mỗi nút cha có độ ưu tiên không lớn hơn các nút con, nên phần tử nhỏ nhất nằm ở gốc.
- Cây tìm kiếm nhị phân: các khóa trong cây con trái nhỏ hơn khóa nút gốc, các khóa trong cây con phải lớn hơn (với quy ước khóa phân biệt).

Khi bất biến bị phá vỡ, kết quả có thể sai dù chương trình vẫn chạy. Ví dụ, thay đổi hạn xử lý của một phần tử đang nằm trong heap mà không khôi phục thuộc tính heap có thể khiến hệ thống chọn nhầm việc tiếp theo.

## 4. Bản đồ các nhóm cấu trúc dữ liệu nền tảng

| Cấu trúc | Cách tổ chức hoặc quy tắc chính | Phù hợp khi | Cần chú ý |
| --- | --- | --- | --- |
| **Mảng / mảng động (array / dynamic array)** | Các phần tử được truy cập theo vị trí chỉ số | Cần truy cập vị trí, duyệt tuần tự; ví dụ thứ tự bài học | Chèn hoặc xóa giữa dãy thường phải dịch phần tử |
| **Danh sách liên kết (linked list)** | Các nút giữ liên kết đến nút kế tiếp (có thể cả nút trước) | Thường xuyên chèn, xóa tại vị trí nút đã biết | Tìm theo chỉ số cần đi qua các nút; thêm chi phí liên kết |
| **Stack** | LIFO — vào sau, ra trước | Hoàn tác, xử lý biểu thức, lời gọi hàm, duyệt quay lui | Chỉ truy cập có chủ đích ở đỉnh stack |
| **Queue** | FIFO — vào trước, ra trước | Xử lý yêu cầu theo thứ tự đến, BFS | Cần cách cài đặt cho phép lấy đầu hiệu quả |
| **Bảng băm (hash table)** | Ánh xạ khóa sang vị trí lưu trữ thông qua hàm băm | Tra cứu, thêm, xóa theo khóa; kiểm tra thành viên | Tốn bộ nhớ phụ; không tự bảo đảm thứ tự khóa đã sắp xếp |
| **Cây (tree)** | Quan hệ cha — con, không có chu trình trong một cây | Phân cấp chương, cấu trúc thư mục, tìm kiếm theo thứ tự | Hiệu năng tìm kiếm phụ thuộc loại cây và khả năng cân bằng |
| **Heap** | Cây có ràng buộc thứ tự cục bộ giữa cha và con | Lấy phần tử ưu tiên cao nhất/thấp nhất nhanh | Không phù hợp để tìm tùy ý theo khóa |
| **Đồ thị (graph)** | Các đỉnh và cạnh mô tả những quan hệ tổng quát | Môn học tiên quyết, mạng kết nối, định tuyến | Có thể có chu trình; cần chọn cách biểu diễn và thuật toán duyệt phù hợp |

Một cấu trúc có thể phục vụ nhiều mục đích, và một nghiệp vụ có thể cần **kết hợp nhiều cấu trúc**. Chẳng hạn, danh sách giữ đúng thứ tự bài học; bảng băm tra nhanh theo mã; đồ thị lưu các quan hệ tiên quyết giữa bài học.

## 5. Đọc chi phí thời gian và bộ nhớ như thế nào?

Khi so sánh cấu trúc dữ liệu, ta thường dùng **độ phức tạp tiệm cận** để mô tả mức tăng tài nguyên khi lượng dữ liệu lớn lên. Ký hiệu `n` là số phần tử:

- **O(1):** chi phí bị chặn bởi một hằng số theo `n`, ví dụ truy cập phần tử mảng bằng chỉ số hợp lệ.
- **O(log n):** số bước tăng chậm khi `n` tăng, thường gặp khi liên tục chia đôi phạm vi tìm kiếm.
- **O(n):** số bước tăng tuyến tính theo `n`, ví dụ duyệt hết một danh sách.
- **O(n log n):** thường gặp ở những thuật toán sắp xếp so sánh hiệu quả.
- **O(n²):** chi phí tăng theo bình phương `n`, có thể xuất hiện khi so sánh mọi cặp phần tử bằng hai vòng lặp lồng nhau.

Ví dụ, khi `n` từ 1.000 tăng lên 1.000.000, một phép duyệt tuyến tính có số phần tử phải kiểm tra tối đa tăng 1.000 lần; còn phép tra cứu có số bước tỷ lệ với `log₂(n)` chỉ tăng khoảng từ 10 lên 20 bước trong mô hình lý tưởng.

Các chi phí tham khảo dưới đây giả định cách cài đặt thông dụng:

| Cấu trúc / thao tác | Tra cứu hoặc truy cập | Thêm | Xóa / lấy ra |
| --- | --- | --- | --- |
| Mảng động, theo chỉ số | **O(1)** | Cuối dãy: **O(1) khấu hao**; giữa dãy: **O(n)** | Giữa dãy: **O(n)** |
| Danh sách liên kết | Theo vị trí: **O(n)** | Đầu danh sách hoặc tại nút đã biết: **O(1)** | **O(1)** nếu đã có đủ tham chiếu cần thiết; tìm nút: **O(n)** |
| Stack | Đỉnh: **O(1)** | Push: **O(1)** (hoặc khấu hao với mảng động) | Pop: **O(1)** (hoặc khấu hao với mảng động) |
| Queue cài bằng deque | Đầu hàng: **O(1)** | Cuối hàng: **O(1)** | Đầu hàng: **O(1)** |
| Bảng băm | Theo khóa: **O(1)** kỳ vọng | **O(1)** kỳ vọng, khấu hao | **O(1)** kỳ vọng |
| Cây tìm kiếm nhị phân cân bằng | Theo khóa: **O(log n)** | **O(log n)** | **O(log n)** |
| Heap nhị phân | Xem phần tử ở đỉnh: **O(1)**; tìm khóa bất kỳ: **O(n)** | **O(log n)** | Lấy đỉnh: **O(log n)** |

> **Đọc bảng đúng cách:** `O(1)` là tốc độ tăng trưởng theo kích thước đầu vào, không có nghĩa là “một nano giây”. Các con số không tự nói lên hằng số thực thi, cache CPU hay chi phí cấp phát bộ nhớ. Với bảng băm, các mức `O(1)` là kỳ vọng trong điều kiện băm và phân bố khóa phù hợp; trường hợp xấu nhất có thể là `O(n)`. Với cây tìm kiếm không cân bằng, thao tác có thể suy giảm đến `O(n)`.

**Độ phức tạp bộ nhớ** cũng quan trọng. Một mảng hoặc tập bản ghi cần ít nhất chỗ lưu cho `n` phần tử, tức **O(n)**. Một bảng băm thường thêm vùng chứa chỉ mục; danh sách liên kết lưu thêm tham chiếu; đồ thị có danh sách kề thường cần **O(V + E)** bộ nhớ, với `V` là số đỉnh và `E` là số cạnh. Khi dữ liệu rất lớn, chi phí bộ nhớ có thể quyết định cấu trúc nào khả thi.

## 6. Bài toán mẫu: tổ chức dữ liệu cho nền tảng học tập

Giả sử ta xây dựng chức năng quản lý bài học. Hệ thống cần đáp ứng nhiều loại truy vấn:

| Nhu cầu nghiệp vụ | Cách tổ chức gợi ý | Lý do |
| --- | --- | --- |
| Hiển thị các bài trong một chương theo thứ tự | Mảng động / danh sách có thứ tự | Duyệt tuần tự, truy cập theo vị trí |
| Mở bài học theo mã `lessonId` | Bảng băm `lessonId → Lesson` | Tra cứu nhanh theo khóa khi gọi lặp lại |
| Hoàn tác thao tác biên tập gần nhất | Stack | Hành động mới nhất được hoàn tác đầu tiên |
| Xử lý yêu cầu chấm bài theo thứ tự đến | Queue | Đảm bảo FIFO với quy tắc nghiệp vụ tương ứng |
| Chọn tác vụ có hạn chót sớm nhất | Min-heap với khóa là hạn chót | Xem hạn sớm nhất O(1), thêm/lấy ra O(log n) |
| Tổ chức chương và mục nội dung lồng nhau | Cây | Biểu diễn trực tiếp quan hệ cha — con |
| Liệt kê các học phần tiên quyết | Đồ thị có hướng | Một học phần có thể phụ thuộc vào nhiều học phần khác |

Với đồ thị tiên quyết, mỗi học phần là một **đỉnh**, và cạnh có hướng `A → B` có thể được quy ước là *phải học A trước B*. Khi đó, tìm lộ trình hợp lệ liên quan đến duyệt đồ thị và sắp xếp tô pô nếu đồ thị không có chu trình. Nếu tồn tại chu trình kiểu `A → B → C → A`, không thể xếp một thứ tự học thỏa tất cả các quan hệ ấy; hệ thống cần phát hiện và xử lý lỗi dữ liệu.

Ví dụ biểu diễn ngắn gọn bằng danh sách kề:

```python
# Mỗi khóa là học phần, giá trị là các học phần có thể học tiếp ngay sau đó.
next_courses = {
    "Cơ sở lập trình": ["Cấu trúc dữ liệu"],
    "Cấu trúc dữ liệu": ["Giải thuật", "Cơ sở dữ liệu"],
    "Giải thuật": [],
    "Cơ sở dữ liệu": [],
}

assert next_courses["Cấu trúc dữ liệu"] == ["Giải thuật", "Cơ sở dữ liệu"]
```

Đây là một biểu diễn đồ thị bằng bảng ánh xạ tới các danh sách kề, khác với cây phân cấp: một đỉnh trong đồ thị có thể có nhiều cạnh đến hoặc đi, và đồ thị tổng quát có thể chứa chu trình. Với biểu diễn danh sách kề, duyệt BFS/DFS toàn đồ thị có chi phí **O(V + E)**.

## 7. Chọn cấu trúc dữ liệu bằng cách đặt câu hỏi đúng

Trước khi chọn mảng, queue hay bảng băm, hãy phân tích **khối lượng và mẫu thao tác** của bài toán:

1. **Truy vấn chủ yếu là gì?** Lấy theo vị trí, tra theo mã, tìm phần tử nhỏ nhất hay duyệt quan hệ?
2. **Tần suất đọc so với ghi?** Tìm kiếm hàng nghìn lần cho mỗi lần cập nhật có thể xứng đáng với một chỉ mục phụ; dữ liệu đổi liên tục sẽ làm chi phí duy trì chỉ mục rõ rệt hơn.
3. **Cần bảo toàn thứ tự nào?** Thứ tự chèn, thứ tự sắp xếp theo khóa, FIFO, LIFO hay thứ tự ưu tiên?
4. **Quy mô bao nhiêu?** Vài chục, vài triệu hay hàng tỷ phần tử? Dữ liệu có vừa bộ nhớ không?
5. **Bất biến nào phải luôn đúng?** Khóa duy nhất, không có chu trình tiên quyết, độ ưu tiên hợp lệ hay không bỏ sót yêu cầu?
6. **Giới hạn tài nguyên là gì?** Thời gian phản hồi, bộ nhớ, chi phí cập nhật, tính cục bộ bộ nhớ và số lượt truy cập đồng thời.
7. **Cần đo đạc gì?** Dùng dữ liệu và tỷ lệ truy vấn gần với thực tế để đo thời gian, bộ nhớ và độ ổn định, vì ký hiệu Big O chỉ là một phần của bức tranh.

Ví dụ: nếu chỉ có 20 bài học và người dùng thỉnh thoảng tìm bằng mã, duyệt một danh sách tuyến tính có thể đủ đơn giản và hiệu quả. Nếu có hàng triệu mục và mỗi giây nhận hàng nghìn truy vấn bằng mã, chỉ mục băm sẽ trở nên đáng cân nhắc. Không nên tăng độ phức tạp triển khai khi nhu cầu chưa đòi hỏi.

## 8. Những hiểu lầm thường gặp

- **“Cứ O(1) là luôn nhanh hơn O(n).”** Sai: Big O so sánh tốc độ tăng theo quy mô, còn dữ liệu nhỏ, hằng số thực thi và cách truy cập bộ nhớ vẫn ảnh hưởng lớn.
- **“Bảng băm luôn cho dữ liệu được sắp xếp.”** Sai: bảng băm phục vụ ánh xạ khóa. Python `dict` giữ thứ tự chèn theo đặc tả ngôn ngữ hiện đại, nhưng điều đó không có nghĩa các khóa được sắp xếp theo giá trị.
- **“Danh sách liên kết luôn chèn nhanh hơn mảng.”** Thiếu điều kiện: chèn tại nút đã biết có thể O(1), nhưng tìm ra vị trí chèn thường mất O(n). Mảng động có thể tốt hơn nhờ tính cục bộ bộ nhớ và truy cập theo chỉ số.
- **“Chỉ cần một cấu trúc cho toàn bộ ứng dụng.”** Sai: các thao tác thường đòi hỏi những cách tổ chức bổ trợ nhau; đổi lại, ứng dụng phải giữ các cách biểu diễn nhất quán.
- **“Đã chọn được cấu trúc thì không cần thuật toán.”** Sai: một cấu trúc chỉ quy định cách lưu và những thao tác nền tảng; vẫn cần thuật toán để giải quyết những nhiệm vụ như tìm đường, kiểm tra chu trình hoặc sắp xếp.

## 9. Tự kiểm tra hiểu biết

**Tình huống 1.** Một trang học tập hiển thị 100 bài theo vị trí thứ nhất, thứ hai, ... và hiếm khi chèn vào giữa. Cấu trúc nào là lựa chọn khởi đầu hợp lý?

*Gợi ý:* Mảng động đáp ứng truy cập theo chỉ số O(1) và duyệt tuần tự thuận tiện. Chưa cần một cấu trúc phức tạp hơn chỉ vì dữ liệu có 100 phần tử.

**Tình huống 2.** Hệ thống cần kiểm tra liên tục xem `userId` đã đăng ký một khóa hay chưa. Vì sao một tập hợp băm (hash set) hoặc bảng băm phù hợp hơn việc quét toàn danh sách?

*Gợi ý:* Kiểm tra thành viên theo khóa thường là O(1) kỳ vọng, trong khi tìm tuyến tính là O(n); đổi lại cần bộ nhớ và chi phí duy trì cấu trúc băm.

**Tình huống 3.** Một học phần `A` phụ thuộc `B`, còn `B` lại phụ thuộc `A`. Nên dùng mô hình nào để nhận diện vấn đề?

*Gợi ý:* Biểu diễn quan hệ tiên quyết bằng đồ thị có hướng rồi kiểm tra chu trình; không có thứ tự học hợp lệ khi tồn tại chu trình phụ thuộc.

## Kết luận

Cấu trúc dữ liệu là cách **tổ chức dữ liệu theo những quy tắc phục vụ thao tác cụ thể**. Nó quyết định sự cân bằng giữa tốc độ truy cập, chi phí cập nhật, bộ nhớ sử dụng và khả năng duy trì tính đúng đắn. Để chọn đúng, hãy bắt đầu từ những câu hỏi hệ thống phải trả lời; sau đó mới so sánh mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap hay đồ thị dựa trên thao tác, bất biến và độ phức tạp thời gian — bộ nhớ.
