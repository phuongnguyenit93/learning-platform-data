# Xác định mẫu đọc, ghi và tần suất truy cập

> **Chương:** Yêu cầu lưu trữ  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Bối cảnh:** Khi thiết kế persistence cho ứng dụng Java, cần hiểu dữ liệu được đọc và ghi như thế nào, bao nhiêu lần, vào thời điểm nào và với cam kết về độ trễ, tính nhất quán, bảo mật, phục hồi ra sao. Các đặc điểm này định hướng việc chọn mô hình dữ liệu, schema, truy vấn, chỉ mục, giao dịch, quản lý kết nối và tối ưu hiệu năng.

## 1. Vì sao phải xác định mẫu truy cập trước khi thiết kế lưu trữ?

Hai ứng dụng có thể cùng lưu bảng đơn hàng với các trường `id`, `customer_id`, `status` và `created_at` nhưng có yêu cầu lưu trữ rất khác nhau:

- Ứng dụng A chủ yếu **đọc** lịch sử đơn của từng khách; mỗi ngày phát sinh ít đơn mới.
- Ứng dụng B nhận hàng nghìn sự kiện cập nhật trạng thái mỗi phút; các đơn mới liên tục được ghi, còn lịch sử hiếm khi được xem.
- Ứng dụng C phải vừa tiếp nhận đơn trong giờ cao điểm, vừa xuất báo cáo tổng hợp trên dữ liệu nhiều năm.

Nếu chỉ nhìn vào **các trường dữ liệu**, ta chưa biết nên tạo chỉ mục nào, phân trang ra sao, cache ở đâu, bố trí giao dịch như thế nào hoặc giới hạn connection pool bao nhiêu. Cần hiểu **mẫu truy cập** (*access pattern*) và **tải công việc** (*workload*).

Một yêu cầu tốt nên mô tả được:

1. **Đọc hoặc ghi cái gì?** Một bản ghi, một tập con, nhiều bảng, một aggregate hay một file lớn?
2. **Tìm bằng cách nào?** Theo khóa, khoảng thời gian, trạng thái, điều kiện lọc, sắp xếp hay tìm kiếm toàn văn?
3. **Bao nhiêu lần?** Trung bình, giờ cao điểm, đột biến trong vài giây và tốc độ tăng theo thời gian.
4. **Bao nhiêu tác nhân cùng thực hiện?** Số request đồng thời, số luồng ghi trên cùng bản ghi và phạm vi chia sẻ giữa các instance.
5. **Cần cam kết gì?** Độ trễ, độ mới của dữ liệu, tính nguyên tử, độ bền, khôi phục và quyền truy cập.

Đích của bài là **lập được bản mô tả workload đủ định lượng để thiết kế và kiểm chứng**, không chỉ gắn nhãn hệ thống “đọc nhiều” hay “ghi nhiều”.

## 2. Khái niệm nền tảng: request, thao tác dữ liệu và tài nguyên

**Request nghiệp vụ** là một lần ứng dụng phục vụ một hành động: mở danh sách đơn, xem chi tiết, tạo đơn hoặc xác nhận thanh toán.

**Thao tác đọc logic** là một lần truy vấn hoặc lấy dữ liệu mà ứng dụng yêu cầu; **thao tác ghi logic** là một lần chèn, cập nhật hoặc xóa theo hợp đồng truy cập dữ liệu. Một request có thể tạo nhiều thao tác ở database.

**Truy cập vật lý** là công việc thực tế ở tầng lưu trữ như đọc trang dữ liệu, truy cập index, ghi log giao dịch hoặc đồng bộ thiết bị. Không thể suy ra chính xác số thao tác vật lý chỉ từ số câu lệnh SQL; cần đo đạc, xem kế hoạch truy vấn và hiểu công nghệ được sử dụng.

| Đơn vị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **RPS** (*requests per second*) | Số request nghiệp vụ mỗi giây | 20 lượt xem đơn/giây |
| **QPS** (*queries per second*) | Số query/giây; phải nêu rõ phạm vi và loại query | 50 câu `SELECT`/giây tại database |
| **Write ops/s** | Số thao tác ghi logic/giây | 10 lệnh `INSERT`/`UPDATE`/giây |
| **TPS** (*transactions per second*) | Số transaction/giây được hoàn tất theo cách hệ thống định nghĩa | 5 giao dịch tạo đơn/giây |
| **Latency** | Thời gian một thao tác mất để hoàn tất | p95 truy vấn danh sách = 80 ms |
| **Concurrency** | Số thao tác/request đang diễn ra cùng lúc | 30 request đang chờ xử lý |
| **Throughput** | Khối lượng công việc xử lý trên mỗi đơn vị thời gian | 3.000 sự kiện ghi nhận/phút |

Đừng tự đồng nhất `RPS = QPS = TPS`. Một request lấy chi tiết đơn có thể chạy nhiều query. Một transaction tạo đơn có thể chứa ba câu lệnh ghi và hai câu lệnh đọc. Một câu `UPDATE` lại có thể làm thay đổi nhiều trang dữ liệu, nhiều index và nhật ký giao dịch.

**Lưu ý về thuật ngữ:** Nhiều công cụ gọi “QPS” là tổng số câu lệnh, bao gồm cả ghi; một số dashboard chỉ thống kê truy vấn đọc. Khi trình bày, hãy ghi rõ “read queries/s”, “write statements/s” hoặc loại thao tác cụ thể.

## 3. Phân loại mẫu đọc theo cách lấy và sử dụng dữ liệu

Mỗi màn hình/API thường có một số mẫu đọc chủ đạo:

| Mẫu đọc | Ví dụ | Hệ quả thiết kế |
| --- | --- | --- |
| **Tra cứu theo khóa** (*point lookup*) | Mở đơn bằng `order_id` | Khóa chính hoặc index có tính chọn lọc cao |
| **Lọc theo thuộc tính** | Các đơn `PAID` của một khách | Thứ tự cột của composite index và độ chọn lọc |
| **Truy vấn khoảng** (*range query*) | Đơn được tạo trong 7 ngày qua | Index hỗ trợ phạm vi thời gian, lưu ý phân vùng khi đủ lớn |
| **Danh sách có sắp xếp và phân trang** | 20 đơn mới nhất của một khách | Index khớp bộ lọc/thứ tự; phân trang ổn định |
| **Đọc quan hệ** | Đơn kèm các dòng hàng và trạng thái thanh toán | Join/batch để tránh N+1 query |
| **Tổng hợp** (*aggregate*) | Doanh thu từng ngày hoặc số đơn theo trạng thái | Tần suất, phạm vi quét, có thể cần bảng tổng hợp/materialized view |
| **Quét/đọc hàng loạt** | Xuất báo cáo 1 triệu đơn | Batch/stream, lịch chạy riêng, hạn chế ảnh hưởng OLTP |
| **Đọc rất mới** | Kiểm tra đã trừ tiền hay chưa | Yêu cầu đọc nhất quán; thận trọng với cache/replica có độ trễ |
| **Đọc chấp nhận dữ liệu cũ** | Danh mục sản phẩm tham khảo | Cache hoặc bản sao đọc có thể phù hợp |

Mẫu đọc phải gồm cả **bộ lọc** và **thứ tự trả về**. Câu “đọc đơn hàng theo khách hàng” chưa đủ nếu UI thực sự cần “20 đơn gần nhất của khách, sắp xếp giảm theo thời điểm và ID”.

### 3.1. Lấy đúng lượng dữ liệu cần thiết

So sánh hai cách đọc:

~~~sql
-- Rộng và không có giới hạn số bản ghi:
SELECT *
FROM orders
WHERE customer_id = :customerId;

-- Phục vụ màn hình danh sách có giới hạn:
SELECT id, status, total_minor, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Truy vấn thứ hai mô tả rõ mục tiêu hơn: chọn đúng cột, giới hạn số hàng và có thứ tự xác định. Hai câu trên đều là ví dụ theo cú pháp PostgreSQL; các tham số dạng `:customerId` đại diện cho giá trị được bind từ ứng dụng, không phải cú pháp SQL trực tiếp trong mọi console.

Nếu danh sách có nhiều trang, **offset pagination** có thể ngày càng tốn công với offset lớn và dễ dịch chuyển kết quả khi dữ liệu mới xuất hiện. Với dòng dữ liệu có thứ tự ổn định, **keyset/cursor pagination** thường phù hợp:

~~~sql
SELECT id, status, total_minor, created_at
FROM orders
WHERE customer_id = :customerId
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Với trang đầu, bỏ điều kiện cursor. Tổ hợp `(created_at, id)` giúp phá thế hòa nếu nhiều đơn có cùng thời điểm tạo. Người thiết kế cần thống nhất điều kiện cursor với hướng sắp xếp và chính sách xử lý dữ liệu thay đổi giữa các lần phân trang.

## 4. Phân loại mẫu ghi theo ngữ nghĩa nghiệp vụ

Đối với ghi, câu hỏi quan trọng là **thay đổi có ý nghĩa gì** và **có cần bảo vệ cùng với thay đổi nào khác**:

| Mẫu ghi | Ví dụ | Điều cần làm rõ |
| --- | --- | --- |
| **Insert/append** | Tạo đơn mới, ghi sự kiện | Tần suất, khóa duy nhất, xử lý retry và ghi trùng |
| **Update theo khóa** | Sửa địa chỉ trên đơn nháp | Điều kiện trạng thái, version, quyền và xung đột |
| **Tăng/giảm có điều kiện** | Trừ tồn kho | Atomic update, kiểm tra số hàng, không để số lượng âm |
| **Ghi nhiều bảng trong một giao dịch** | Tạo đơn và dòng hàng | Ranh giới commit/rollback và bất biến nghiệp vụ |
| **Upsert/idempotent write** | Đồng bộ profile theo định danh | Khóa duy nhất và ý nghĩa khi lệnh gửi lại |
| **Batch write/import** | Nhập hàng nghìn sản phẩm | Batch size, giới hạn transaction, lỗi từng dòng |
| **Delete/retention** | Xóa bản ghi quá hạn | Soft/hard delete, khóa ngoại, thời gian lưu giữ và audit |
| **Event-driven write** | Webhook thanh toán hoặc sự kiện vận chuyển | Tính trùng lặp, thứ tự đến, sự kiện muộn, đối soát |

Một request có thể có **nhiều ghi nhưng vẫn chỉ là một giao dịch**. Chẳng hạn, tạo đơn gồm `INSERT orders`, nhiều `INSERT order_items` và một `UPDATE inventory`. Việc đếm “ba thao tác ghi” chỉ là mô hình sơ bộ; số statement thực tế còn phụ thuộc số dòng hàng, cách batch và logic nghiệp vụ.

### 4.1. Ghi nóng trên cùng một bản ghi

Một bảng có tổng lưu lượng ghi vừa phải vẫn có thể khó xử lý nếu nhiều request cùng cập nhật **một hàng**. Ví dụ 1.000 request/giây cùng tăng bộ đếm của một sản phẩm có thể cạnh tranh trên hàng đó.

Vì vậy, cần đo cả **tổng write ops/s** và **phân bố khóa bị ghi**. Dữ liệu phân tán đều theo 100.000 đơn khác với 100.000 request cùng tranh chấp một mã sản phẩm. Giải pháp có thể gồm cập nhật có điều kiện, gom sự kiện, phân chia bộ đếm, hoặc thay đổi thiết kế nghiệp vụ; phải cân nhắc yêu cầu chính xác và độ mới trước khi áp dụng.

### 4.2. Ghi đều và ghi thành từng đợt

Thao tác tạo đơn trực tiếp từ người dùng thường đến liên tục và nhạy với độ trễ. Công việc nhập dữ liệu có thể dồn 100.000 hàng trong một đợt; muốn nhanh có thể dùng batch, nhưng batch quá lớn có thể kéo dài transaction, giữ khóa lâu và tiêu thụ nhiều tài nguyên.

Hai mẫu ghi có cùng **tổng số hàng/ngày** nhưng yêu cầu khác nhau về giới hạn bộ nhớ, timeout, kích thước batch, connection pool và lịch chạy.

## 5. Tần suất truy cập phải được mô tả theo cửa sổ thời gian

Nói “mỗi ngày có 100.000 lượt đọc” mới là tổng khối lượng, chưa nói hệ thống phải chịu **tải đỉnh**. Nếu mọi lượt đọc diễn ra trong 10 phút, yêu cầu hoàn toàn khác so với phân bố đều trong 24 giờ.

Cần thu thập hoặc ước lượng:

- **Số lần/ngày** cho từng use case, làm điểm xuất phát cho dung lượng và chi phí.
- **Trung bình theo phút/giờ**, nhận biết khung giờ cao điểm và thời gian vắng.
- **Đỉnh theo cửa sổ ngắn**, ví dụ 1 giây, 10 giây hoặc 1 phút; lưu ý bản thân cửa sổ đo ảnh hưởng đến con số peak.
- **Burst và sự kiện ngoại lệ**: flash sale, chiến dịch marketing, cron job, import, retry storm.
- **Tính mùa vụ và tăng trưởng**: ngày trong tuần, cuối tháng, cuối năm, số khách mới, dữ liệu tích lũy.
- **Tỷ trọng đọc/ghi** theo API và theo điểm lưu trữ; một dịch vụ có thể đọc nhiều nhưng một bảng riêng lại ghi nhiều.

Tần suất trung bình là:

~~~text
request/s trung bình = tổng request / số giây của kỳ quan sát

read queries/s ≈ tổng trên mỗi use case:
                 request/s của use case × số query đọc/request

write statements/s ≈ tổng trên mỗi use case:
                     request/s của use case × số statement ghi/request
~~~

Với một ngày, mẫu số là `86.400 giây`. Các công thức trên ước lượng **lệnh logic**, chưa tính lượng truy cập vật lý, index maintenance, WAL, replication hoặc cache hit.

### 5.1. Ví dụ định lượng: API đơn hàng

Giả sử nhóm phát triển thống kê hoặc ước lượng workload như sau. Đây là **số minh họa**, không phải số đo của một hệ thống thật:

| Use case | Request/ngày | Đọc/request | Ghi/request | Đỉnh request/s |
| --- | ---: | ---: | ---: | ---: |
| Danh sách đơn theo khách | 120.000 | 1 | 0 | 12 |
| Xem chi tiết đơn | 60.000 | 2 | 0 | 8 |
| Tạo đơn | 12.000 | 2 | 3 | 3 |
| Nhận thông báo thanh toán | 12.000 | 1 | 2 | 5 |
| **Tổng request** | **204.000** | — | — | **28*** |

\*`28 request/s` là **giả định các đỉnh xảy ra cùng lúc**, dùng để thiết lập một kịch bản tải bảo thủ. Trong thực tế phải đối chiếu cùng cửa sổ thời gian, không tự động cộng những đỉnh xuất hiện ở các giờ khác nhau.

Các phép tính:

~~~text
Request trung bình:
204.000 / 86.400 ≈ 2,36 request/s

Query đọc/ngày:
120.000×1 + 60.000×2 + 12.000×2 + 12.000×1
= 276.000 read queries/ngày ≈ 3,19 query/s trung bình

Statement ghi/ngày:
12.000×3 + 12.000×2
= 60.000 write statements/ngày ≈ 0,69 statement/s trung bình

Nếu các đỉnh trùng thời điểm:
Read queries/s = 12×1 + 8×2 + 3×2 + 5×1 = 39
Write statements/s = 3×3 + 5×2 = 19
~~~

Từ đây có thể thấy:

1. Tỷ lệ đọc/ghi trung bình xấp xỉ `276.000 : 60.000 = 4,6 : 1`.
2. Khi đỉnh trùng nhau, tỷ lệ đọc/ghi theo số statement xấp xỉ `39 : 19 = 2,1 : 1`. Workload có thể nghiêng về ghi hơn trong giờ cao điểm.
3. Trung bình chỉ khoảng `2,36 request/s` nhưng kịch bản đỉnh là `28 request/s`. Thiết kế chỉ theo trung bình sẽ đánh giá thấp yêu cầu.
4. Một request thanh toán có thể gây tải lớn hơn một lần xem danh sách vì phát sinh nhiều ghi, khóa, log giao dịch và kiểm tra tính duy nhất.

Nếu số dòng hàng mỗi đơn tăng từ 1 lên 20, giả định “ba lệnh ghi cho một đơn” có thể không còn đúng. Cần đo số statement hoặc số hàng ghi theo **phân phối**, không chỉ một giá trị cố định.

## 6. Đọc nhiều, ghi nhiều: đừng chỉ nhìn tỷ lệ tổng

Tỷ lệ read/write là tín hiệu hữu ích nhưng chưa đủ để chọn thiết kế. Hãy hỏi tiếp:

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Đọc từ **bảng nào**, theo khóa hay theo khoảng? | Quyết định index và cách tổ chức bản ghi |
| Ghi vào **những hàng nào**, có bị dồn vào một khóa không? | Quyết định mức tranh chấp và chiến lược đồng thời |
| Đọc phải thấy dữ liệu mới nhất không? | Quyết định có dùng replica/cache và chính sách nhất quán hay không |
| Ghi có thể bị lặp lại không? | Quyết định khóa duy nhất, idempotency và xử lý retry |
| Độ lớn dữ liệu trả về là bao nhiêu? | Quyết định chi phí I/O, băng thông, bộ nhớ ứng dụng |
| Ghi có phát sinh nhiều index/log/replica? | Quyết định write amplification và giới hạn throughput |
| Tải có mang tính batch/đột biến không? | Quyết định hàng đợi, giới hạn tốc độ và tách lịch chạy |

Ví dụ, một hệ thống có `95%` số thao tác là đọc nhưng mỗi lần ghi phải cập nhật một hàng nóng có thể vẫn bị nghẽn bởi khóa ghi. Ngược lại, một ứng dụng ghi nhiều event append-only có thể đạt thông lượng cao nếu ghi tuần tự và không cần khóa chéo nhiều bản ghi.

### 6.1. Kiểu phân bố dữ liệu cũng là yêu cầu

Đếm số bản ghi được lưu chưa cho thấy dữ liệu **lệch** đến mức nào. Một khách có 2 triệu đơn và các khách khác chỉ có vài đơn sẽ tạo workload khác với 2 triệu đơn chia đều cho hàng trăm nghìn khách.

Nên đo số bản ghi/khóa, top N khóa nóng, tỷ lệ query trên khách hàng lớn, bản ghi lớn bất thường và khả năng có **tenant ồn ào** trong hệ thống nhiều tenant. Những thông tin này giúp phát hiện index hoặc partition “đúng trên dữ liệu trung bình” nhưng yếu ở trường hợp thực tế.

## 7. Khối lượng dữ liệu: tần suất truy cập gắn với tốc độ tăng trưởng

Khi thiết kế yêu cầu lưu trữ, phải phân biệt:

- **Số bản ghi hiện tại:** tổng tập dữ liệu mà query sẽ đi qua hoặc index sẽ quản lý.
- **Số bản ghi mới/ngày:** tốc độ phát sinh dữ liệu.
- **Kích thước bản ghi:** kích thước thuộc tính, metadata và dữ liệu con.
- **Thời gian lưu giữ:** giữ bao nhiêu ngày/năm; có chính sách xóa hoặc lưu trữ lịch sử không?
- **Số bản sao:** replica, backup, môi trường dự phòng và khu vực triển khai.

Ví dụ, giả sử tạo `12.000 đơn/ngày` và trung bình mỗi đơn cùng các dòng hàng liên quan chiếm `1,5 KiB` ở mức dữ liệu thô:

~~~text
12.000 đơn/ngày × 1,5 KiB/đơn = 18.000 KiB/ngày
                                 ≈ 17,6 MiB/ngày
Sau 365 ngày: ≈ 6,3 GiB dữ liệu thô/năm
~~~

Đây chỉ là **ước lượng sơ bộ**. Database còn có index, metadata trang, khoảng trống, nhật ký giao dịch, lịch sử cập nhật, bản sao và backup. Đối với MVCC, các bản cập nhật còn có thể sinh phiên bản hàng cũ cần dọn dẹp. Không nên lấy kích thước này làm số liệu cuối cùng để cấp dung lượng đĩa.

**Đọc một năm dữ liệu** có thể trở nên chậm dù QPS không tăng. Cần tính cả lượng dữ liệu tích lũy, số hàng được quét và xu hướng của các truy vấn theo thời gian.

## 8. Độ trễ và mức độ ưu tiên của từng mẫu truy cập

Hai thao tác có thể có cùng QPS nhưng yêu cầu tốc độ khác nhau:

- Khi người dùng xem chi tiết đơn, ứng dụng có thể cần thời gian phản hồi thấp và ổn định.
- Khi xuất báo cáo tháng, xử lý lâu hơn có thể chấp nhận nếu công việc chạy nền và có thể tra cứu tiến độ.
- Khi xác nhận thanh toán, **tính đúng đắn và xác định kết quả ghi** có thể quan trọng hơn việc giảm vài mili giây.

Định nghĩa mục tiêu cho mỗi luồng:

| Luồng | Ví dụ mục tiêu để thảo luận | Mục đích |
| --- | --- | --- |
| Đọc đơn theo khóa | p95 truy vấn từ ứng dụng đến database dưới 50 ms | Phục vụ tương tác nhanh |
| Danh sách 20 đơn | p95 dưới 100 ms | Kiểm soát độ trễ và phân trang |
| Tạo đơn có transaction | p95 dưới 200 ms | Cân bằng độ trễ và tính nguyên tử |
| Báo cáo tháng | Hoàn tất trong 10 phút | Phân biệt batch với request tương tác |

**Các con số trên là mục tiêu giả định để minh họa**, không phải tiêu chuẩn bắt buộc. Khi xác định SLO thực tế, cần nêu rõ tính tại lớp nào (chỉ SQL, repository, API hay toàn bộ end-to-end), cửa sổ đo, tỷ lệ lỗi, tải đồng thời và điều kiện kiểm thử.

Đo **p50, p95, p99** cùng với thông lượng và tỷ lệ lỗi sẽ hữu ích hơn chỉ đo trung bình: một số request chậm bất thường có thể tạo trải nghiệm kém dù giá trị trung bình đẹp.

### 8.1. Ước lượng số request đang xử lý

Với hệ thống tương đối ổn định, có thể dùng định luật Little để ước lượng:

~~~text
Số request đang xử lý trung bình ≈ throughput (request/s)
                                × thời gian xử lý trung bình (giây)
~~~

Nếu tại một khoảng ổn định có `28 request/s` và thời gian xử lý trung bình `0,2 s` thì số request đồng thời trung bình xấp xỉ `5,6`. Con số này **không phải** số connection database bắt buộc: request có thể dành thời gian cho nghiệp vụ, mạng, cache hoặc một phần thời gian dùng connection.

Không thay thời gian xử lý trung bình bằng p95 khi áp dụng công thức trên. Khi hệ thống gần bão hòa, thời gian chờ tăng và mối quan hệ thực tế có thể thay đổi đáng kể.

## 9. Biến access pattern thành schema, truy vấn và chỉ mục

Giả sử bảng đơn hàng PostgreSQL có các cột:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    total_minor BIGINT NOT NULL CHECK (total_minor >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Hai mẫu đọc chính:

1. **Xem chi tiết:** `SELECT ... WHERE id = :orderId`. Primary key đã cung cấp chỉ mục cho tra cứu theo ID trong hầu hết hệ quản trị quan hệ.
2. **Danh sách theo khách và thời gian:** `WHERE customer_id = ... ORDER BY created_at DESC, id DESC LIMIT ...`. Có thể cân nhắc index ghép:

~~~sql
CREATE INDEX idx_orders_customer_recent
    ON orders (customer_id, created_at DESC, id DESC);
~~~

Với bộ lọc equality theo `customer_id` và sắp xếp theo thời gian, index này có khả năng hỗ trợ tốt đường đọc danh sách. Tuy nhiên:

- **Không tạo index vì “có cột”**: mỗi index thêm dung lượng và chi phí khi insert/update/delete.
- **Không tối ưu chỉ theo tỷ lệ đọc/ghi**: cần xem query nào chậm, tần suất, lượng hàng quét và độ chọn lọc thực tế.
- **Không giả định một index giải quyết mọi query**: thêm `WHERE status = ...` hoặc thay thứ tự sắp xếp có thể làm kế hoạch truy vấn khác đi.
- **Không đo chỉ bằng thời gian một lần chạy**: dữ liệu trong cache, kích thước bảng, đồng thời và thống kê của query planner đều ảnh hưởng.

Có thể dùng `EXPLAIN` để xem kế hoạch, và `EXPLAIN (ANALYZE, BUFFERS)` khi cần đo thực thi trên môi trường an toàn với dữ liệu đại diện. **ANALYZE thực sự chạy câu lệnh**, nên phải thận trọng đặc biệt với lệnh ghi và tải production.

### 9.1. Mối liên hệ giữa mẫu ghi và chỉ mục

Giả sử ứng dụng liên tục cập nhật `status`. Một index chứa `status` cần được bảo trì khi giá trị trạng thái thay đổi, có thể tăng chi phí ghi. Nếu truy vấn theo trạng thái hiếm khi xảy ra, index đó có thể không đáng giá.

Ngược lại, nếu một job mỗi phút lấy “đơn chưa xử lý cũ nhất”, cần ghi rõ query thực tế. Trong PostgreSQL, index một phần (*partial index*) có thể phù hợp với tập hàng đang chờ, nhưng điều kiện phải phản ánh chính xác truy vấn và phải được kiểm chứng trên dữ liệu/khối lượng thật.

## 10. Java: biểu diễn mẫu đọc bằng repository có giới hạn

Một repository phục vụ use case **20 đơn gần nhất theo khách hàng** nên nhận đủ thông tin cần thiết thay vì trả toàn bộ bảng cho service tự lọc.

Ví dụ Java 17+ dùng JDBC và `DataSource`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;

record OrderSummary(
        UUID id,
        String status,
        long totalMinor,
        OffsetDateTime createdAt) {}

final class OrderQueries {
    private final DataSource dataSource;

    OrderQueries(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    List<OrderSummary> latestByCustomer(long customerId, int requestedLimit)
            throws SQLException {
        if (customerId <= 0 || requestedLimit <= 0) {
            throw new IllegalArgumentException("Tham so truy van khong hop le");
        }
        int limit = Math.min(requestedLimit, 100);

        String sql = """
            SELECT id, status, total_minor, created_at
            FROM orders
            WHERE customer_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);
            statement.setInt(2, limit);

            try (ResultSet rs = statement.executeQuery()) {
                List<OrderSummary> result = new ArrayList<>();
                while (rs.next()) {
                    result.add(new OrderSummary(
                            rs.getObject("id", UUID.class),
                            rs.getString("status"),
                            rs.getLong("total_minor"),
                            rs.getObject("created_at", OffsetDateTime.class)));
                }
                return result;
            }
        }
    }
}
~~~

Ví dụ cho thấy một hợp đồng repository có ý nghĩa workload:

- **Một use case rõ ràng:** lấy danh sách gần nhất theo khách.
- **Query có tham số:** không ghép trực tiếp đầu vào vào câu SQL.
- **Giới hạn kết quả:** tránh vô tình trả hàng triệu hàng.
- **Chỉ chọn cột cần thiết:** giảm lượng dữ liệu qua mạng và khối lượng object.
- **Quản lý tài nguyên:** `try-with-resources` đóng `ResultSet`, statement và connection.

Đây là ví dụ truy vấn trang đầu, chưa phải API phân trang hoàn chỉnh. Để hỗ trợ các trang tiếp theo, nên bổ sung cursor ổn định như phần 3.1. Trong hệ thống thực tế cũng cần xác thực người gọi được quyền đọc `customerId` và cấu hình timeout, pool, tracing phù hợp.

### 10.1. Hạn chế N+1 query

Giả sử mỗi lần mở danh sách 20 đơn, ứng dụng chạy một query lấy 20 đơn và thêm 20 query lấy dòng hàng của từng đơn. Một request tạo ra **21 query**, không còn là “1 query/request” như bảng ước lượng.

Nếu API cần dòng hàng, có thể cân nhắc join có kiểm soát, batch theo tập `order_id` hoặc một query chuyên biệt. Join quan hệ một-nhiều có thể làm số dòng trả về nhân lên, vì vậy cần đo tổng dung lượng và cách phân trang. **Bản đồ truy cập phải bám sát truy vấn thực thi**, không chỉ số lần gọi endpoint.

## 11. Write path: giao dịch, tranh chấp và độ mới

Ví dụ trừ tồn kho khi có nhiều đơn cạnh tranh:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :quantity
WHERE product_id = :productId
  AND available_qty >= :quantity;
~~~

Ứng dụng phải kiểm tra số hàng cập nhật bằng 1; nếu không, xử lý hết hàng hoặc không tìm thấy sản phẩm. Nếu việc tạo đơn và trừ kho phải thành một đơn vị nghiệp vụ, hai thao tác phải được bảo vệ trong một transaction phù hợp.

Nơi ghi càng nhiều và càng tập trung vào cùng bản ghi, chi phí chờ khóa và nguy cơ deadlock càng quan trọng. Khi lập yêu cầu cần ghi:

- **Giao dịch nào gồm những thao tác gì**, số hàng dự kiến và thời gian giữ transaction.
- **Những khóa có thể tranh chấp**, tỷ lệ ghi đồng thời trên cùng khóa, rủi ro lost update.
- **Mức cô lập và nhất quán** cần thiết; không cho rằng mọi transaction mặc định đều ngăn mọi bất thường.
- **Điều kiện thử lại**: lỗi nào có thể retry, có idempotency key không, có nguy cơ tác động lặp không.
- **Khi nào trả thành công**: sau khi commit hoặc sau khi nhận vào hàng đợi, và mỗi cách có cam kết khác nhau.

Nếu ứng dụng trả “đã tạo đơn” trước khi ghi bền vững hoàn tất, phải làm rõ điều đó trong hợp đồng API. Một tác vụ bất đồng bộ có thể trả “đã tiếp nhận xử lý” sớm hơn, nhưng cần trạng thái theo dõi và cơ chế phục hồi.

## 12. Cache, replica và batch: dùng theo mẫu truy cập

### 12.1. Cache phù hợp khi nào?

Cache có thể hiệu quả với mẫu **đọc lặp lại cùng dữ liệu**, tính toán đắt hoặc dữ liệu thay đổi ít. Ví dụ cache danh mục sản phẩm ngắn hạn có thể giảm số read queries đến database.

Trước khi dùng cache cần trả lời:

1. Dữ liệu có thể chấp nhận cũ trong bao lâu?
2. Khi ghi dữ liệu gốc, cache được cập nhật hay vô hiệu bằng cách nào?
3. Có hiện tượng nhiều request đồng thời cùng đọc một key vừa hết hạn (*cache stampede*) không?
4. Tỷ lệ cache hit/miss thực tế là bao nhiêu, cache tốn bao nhiêu RAM và có dễ bị quét đầy bởi các khóa ít dùng không?
5. Nếu cache mất, ứng dụng có thể lấy lại dữ liệu từ nguồn bền vững không?

Không nên giả định “thêm cache là QPS database giảm 90%” nếu không biết **phân bố khóa** và **hit ratio**. Cache cũng làm yêu cầu consistency phức tạp hơn.

### 12.2. Read replica phù hợp khi nào?

Read replica có thể giảm tải đọc trên primary khi một phần request chấp nhận dữ liệu **chậm hơn bản chính**. Nhưng replica có thể có replication lag. Nếu người dùng vừa thanh toán xong rồi mở lại đơn, đọc từ replica chưa bắt kịp có thể khiến UI hiển thị trạng thái cũ.

Những luồng cần **read-after-write** hoặc điều kiện quyết định ghi quan trọng nên được định tuyến theo chính sách nhất quán phù hợp (chẳng hạn đọc từ primary hoặc một cơ chế bảo đảm nhìn thấy phiên bản mới). Replica không tự khắc phục truy vấn kém hay thiếu chỉ mục.

### 12.3. Batch và queue phù hợp khi nào?

Những tác vụ xuất báo cáo, import, tổng hợp số liệu, làm giàu dữ liệu có thể được đưa vào hàng đợi hoặc xử lý batch để tránh cạnh tranh với API thời gian thực.

Khi chọn batch size cần đo thông lượng, bộ nhớ, thời gian commit, khóa, kích thước log và khả năng phục hồi từ checkpoint. Hàng đợi giúp hấp thụ đột biến theo thiết kế, nhưng nếu producer duy trì tốc độ cao hơn consumer quá lâu thì backlog vẫn tăng; phải có giới hạn và kế hoạch mở rộng.

## 13. Đo và kiểm chứng workload trên hệ thống chạy thật

Nếu có sẵn hệ thống, hãy bắt đầu bằng **số đo**. Nếu chưa có, dùng ước lượng có giả định và cập nhật khi có traffic thật.

| Nhóm số liệu | Ví dụ cần thu thập | Giúp phát hiện |
| --- | --- | --- |
| API/use case | RPS, p95/p99, tỷ lệ lỗi theo endpoint | Luồng quan trọng, đỉnh bất thường |
| Repository/SQL | Số query/request, thời gian query, số hàng trả về | N+1, truy vấn lặp hoặc kéo quá nhiều dữ liệu |
| Database | Slow query, query plan, rows scanned/returned | Thiếu index, chọn index kém, full scan |
| Kết nối | Pool active/idle/wait, thời gian đợi connection | Nghẽn pool hoặc transaction giữ connection quá lâu |
| Giao dịch | TPS, rollback, deadlock, thời gian chờ khóa | Tranh chấp, xung đột, retry |
| Tài nguyên | CPU, RAM, disk IOPS/throughput, network, log | Giới hạn hạ tầng và write amplification |
| Cache/replica | Hit ratio, eviction, replication lag | Dữ liệu cũ, cache miss hoặc replica không theo kịp |
| Dữ liệu | Số hàng, tăng trưởng, phân bố key, top khóa nóng | Lệch tải, bảng/index tăng quá nhanh |

Với Java có thể dùng metrics tại controller, service, repository và pool kết nối; với database dùng cơ chế quan sát query phù hợp từng sản phẩm. Tracing giúp nối một request đến những lệnh SQL thật sự chạy. **Không log nguyên văn dữ liệu nhạy cảm, token hoặc tham số truy vấn chứa thông tin cá nhân** chỉ để đo hiệu năng.

### 13.1. Quy trình kiểm chứng theo từng bước

1. **Liệt kê use case** và xây dựng bảng “request → query/transaction → bảng/khóa”.
2. **Gắn tần suất** trung bình, p95/p99 độ trễ, cửa sổ đỉnh và tỉ lệ lỗi theo use case.
3. **Dùng dữ liệu đại diện** về số hàng, kích thước hàng và phân bố khách hàng/khóa.
4. **Xem truy vấn chậm** và kế hoạch thực thi; đo số hàng quét, lượng dữ liệu trả về và tác động của index.
5. **Kiểm thử tải trộn** đúng tỷ lệ đọc/ghi và các luồng cạnh tranh trên cùng khóa.
6. **Thử kịch bản đỉnh, batch và lỗi**, ví dụ cache miss hàng loạt, mất kết nối tạm thời hoặc retry.
7. **So sánh kết quả với mục tiêu**, rồi cập nhật thiết kế hoặc giả định workload.

Kiểm thử 1.000 query đọc đơn riêng lẻ không đại diện cho giờ cao điểm nếu thực tế còn có transaction ghi, cập nhật tồn kho và job tổng hợp cùng lúc.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Thiết kế theo số người đăng ký thay vì traffic thật | Ước lượng quá cao hoặc quá thấp | Đo số request và hành vi của người dùng hoạt động |
| Chỉ tính request/ngày | Không dự báo được đỉnh theo giây/phút | Xây dựng biểu đồ theo thời gian và kịch bản burst |
| Coi mỗi request là một query | Bỏ sót N+1, các ghi nhiều bảng | Đếm query và transaction thật trên mỗi use case |
| Cộng các đỉnh không cùng thời điểm mà không nêu giả định | Tạo kịch bản tải thiếu cơ sở | Phân biệt kịch bản đồng thời bảo thủ và peak quan sát |
| Dùng chỉ số trung bình để cam kết độ trễ | Bỏ sót request đuôi chậm | Theo dõi p95/p99 và tỷ lệ lỗi |
| Tạo index cho mọi cột | Tốn disk, giảm tốc ghi | Gắn index với query cụ thể, đo trước/sau |
| Thấy đọc nhiều là dùng cache ngay | Dữ liệu cũ hoặc hit ratio thấp | Nêu rõ độ mới cần thiết, đo hit/miss |
| Bỏ qua phân bố khóa | Một bản ghi nóng gây nghẽn ghi | Theo dõi hot key và tranh chấp |
| Xem cache/replica như bản ghi mới nhất | Quyết định nghiệp vụ trên dữ liệu cũ | Xác định read-after-write và tuyến đọc phù hợp |
| Cho batch chạy cạnh tranh không giới hạn với API | Giao dịch giữ khóa dài, p99 xấu | Chia nhỏ batch, kiểm soát tốc độ và lịch |
| Retry toàn bộ ghi khi timeout không có định danh ổn định | Có thể tạo đơn/thanh toán trùng | Thiết kế idempotency và cách xác minh commit |

## 15. Thực hành: xây dựng hồ sơ truy cập cho một chức năng

Hãy chọn tính năng “lịch sử đơn hàng và đặt hàng” của một ứng dụng Java. Hoàn thành mẫu dưới đây cho **từng use case**:

| Trường mô tả | Giá trị cần điền |
| --- | --- |
| Use case/API | Ví dụ: `GET /customers/me/orders` |
| Kiểu truy cập | Point lookup / range / list / aggregate / insert / update / batch |
| Bộ lọc, sắp xếp, kích thước kết quả | Ví dụ: theo `customer_id`, mới nhất trước, 20 hàng/trang |
| Số query đọc và statement ghi/request | Đo hoặc ghi giả định rõ ràng |
| Request/ngày và đỉnh theo cửa sổ | Ví dụ: 120.000/ngày, peak 12 request/s trong 1 phút |
| Phân bố key và dữ liệu | Số đơn/khách, khách có dữ liệu nhiều nhất |
| Mục tiêu hiệu năng | Ví dụ: p95 ở repository, p99 API, tỷ lệ lỗi |
| Yêu cầu đúng đắn | Độ mới, transaction, ràng buộc, idempotency |
| Hành vi khi lỗi | Timeout, retry, kiểm tra kết quả, thông báo người dùng |
| Quan sát được | Counter, histogram, query plan, pool metrics |

### Bài tập 1: Tính tải logic

Một API có `4.800 request/phút` trong 10 phút cao điểm. Mỗi request chạy 3 câu `SELECT` và 1 câu `UPDATE`.

Hãy tính số request/s, read queries/s và write statements/s theo giả định mọi request có cùng số lệnh.

**Gợi ý đáp án:** `4.800 / 60 = 80 request/s`; `80 × 3 = 240 read queries/s`; `80 × 1 = 80 write statements/s`. Đây là tần suất lệnh logic; không phải số I/O vật lý.

### Bài tập 2: Tranh chấp ghi

Một sản phẩm chỉ còn 1 đơn vị, nhưng nhiều khách đồng thời đặt mua. Workload tổng thể chỉ 10 write statements/s, nhưng phần lớn lệnh cập nhật cùng `product_id`. Hãy giải thích vì sao chỉ nhìn write ops/s không đủ và đề xuất cách bảo vệ số lượng tồn kho.

**Gợi ý:** Đây là **hot key** và rủi ro lost update/oversell. Dùng cập nhật có điều kiện, kiểm tra số hàng, transaction bao trùm tạo đơn và trừ tồn kho; đo thời gian chờ khóa.

### Bài tập 3: Chọn nơi đọc sau khi ghi

Ứng dụng lưu thành công trạng thái `PAID` ở primary, rồi ngay lập tức chuyển khách sang trang chi tiết đơn. Read replica đang trễ 2 giây. Hãy giải thích vì sao có thể hiển thị `SUBMITTED` và đề xuất chính sách đọc phù hợp.

**Gợi ý:** Replica chưa áp dụng xong thay đổi. Nếu màn hình yêu cầu read-after-write, cần đọc từ nguồn hoặc cơ chế nhất quán đáp ứng yêu cầu đó.

### Bài tập 4: Index theo mục tiêu truy vấn

Hai truy vấn được sử dụng:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :id
ORDER BY created_at DESC, id DESC
LIMIT 20;

SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime;
~~~

Hãy giải thích vì sao index `(customer_id, created_at DESC, id DESC)` phù hợp với truy vấn thứ nhất, nhưng chưa chắc là lựa chọn tốt nhất cho truy vấn thứ hai. Nêu những thông tin cần đo trước khi bổ sung index khác.

**Gợi ý:** Truy vấn thứ hai không lọc theo `customer_id`; cần biết độ chọn lọc của trạng thái/thời gian, số hàng, tần suất truy vấn và chi phí ghi trước khi quyết định.

## 16. Checklist trước khi chốt yêu cầu lưu trữ

- [ ] Đã liệt kê các use case đọc/ghi quan trọng và bảng/khóa chúng tác động.
- [ ] Đã mô tả chính xác điều kiện lọc, thứ tự, phân trang và số hàng/byte mỗi lần đọc.
- [ ] Đã xác định các kiểu ghi, số hàng thay đổi, ranh giới transaction và khả năng bị retry.
- [ ] Đã có request/ngày, tải trung bình, đỉnh theo cửa sổ rõ ràng và tốc độ tăng trưởng.
- [ ] Đã phân biệt RPS, read queries/s, write statements/s, TPS và I/O vật lý.
- [ ] Đã đo hoặc ước lượng phân bố khóa nóng, mức đồng thời và thời gian giữ khóa.
- [ ] Đã có mục tiêu p95/p99, tỷ lệ lỗi, mức nhất quán và yêu cầu read-after-write theo luồng.
- [ ] Đã tính dung lượng dữ liệu thô, lịch sử, index, bản sao và thời gian lưu giữ.
- [ ] Mọi index/cache/replica/batch đề xuất đều gắn với mẫu truy cập và giả định có thể kiểm chứng.
- [ ] Đã có metrics, tracing và cách thử tải trộn để kiểm tra sau khi triển khai.

## 17. Ghi nhớ

**Mẫu đọc và ghi mô tả hệ thống sử dụng dữ liệu như thế nào; tần suất truy cập cho biết hệ thống phải thực hiện công việc ấy ở quy mô nào.** Hai phần thông tin cần đi cùng nhau. Một truy vấn đơn giản có thể trở thành điểm nghẽn khi gọi hàng trăm lần mỗi giây; một thao tác ghi hiếm gặp vẫn có thể gây lỗi nghiêm trọng nếu cập nhật sai khi có cạnh tranh.

Với `DATA_PERSISTENCE_FUNDAMENTALS`, việc bắt đầu từ workload giúp người học thiết kế ranh giới persistence cho Java trên cơ sở kiểm chứng được: **chọn schema và index theo query thực**, **dùng transaction và kiểm soát đồng thời cho ghi quan trọng**, **thiết kế cache và replica theo yêu cầu độ mới**, và **đo khả năng phục hồi, chi phí cùng hiệu năng khi dữ liệu phát triển**. Một bản mô tả workload tốt sẽ được cập nhật bằng số liệu vận hành thực tế trong suốt vòng đời hệ thống.
