# Kiểm thử tải, soak test và kiểm tra giới hạn mở rộng

## 1. Mục đích của kiểm thử hiệu năng trong đánh giá kiến trúc đám mây

Một kiến trúc ứng dụng trên đám mây có thể hoạt động đúng về chức năng nhưng vẫn thất bại khi lưu lượng tăng, khi chạy liên tục nhiều ngày hoặc khi hệ thống mở rộng sang nhiều instance. Vì vậy, đánh giá kiến trúc cần **bằng chứng đo được** về khả năng đáp ứng yêu cầu nghiệp vụ, thay vì chỉ dựa vào sơ đồ hoặc thông số cấu hình.

Ba nhóm kiểm tra có vai trò bổ sung cho nhau:

- **Load test (kiểm thử tải):** hệ thống đáp ứng tải thông thường và tải đỉnh dự kiến với độ trễ, tỷ lệ lỗi và năng lực xử lý như thế nào?
- **Soak/endurance test (kiểm thử chạy dài hạn):** khi duy trì tải trong thời gian đủ dài, tài nguyên, độ trễ, hàng đợi và trạng thái vận hành có suy giảm dần không?
- **Scalability/capacity test (kiểm tra mở rộng và giới hạn năng lực):** tăng tài nguyên có thực sự tăng thông lượng hữu ích không; thành phần nào bão hòa trước; hệ thống có thể phục vụ bao nhiêu tải mà vẫn đạt SLO?

Các phép kiểm tra này liên quan trực tiếp đến những đánh đổi của kiến trúc cloud: **độ tin cậy, hiệu năng, bảo mật, khả năng mở rộng, chi phí và vận hành**. Hệ thống xử lý được nhiều request không có nghĩa là đáng tin cậy nếu tỷ lệ lỗi tăng. Tăng replica chưa chắc đem lại năng lực lớn hơn nếu database, queue hoặc giới hạn nhà cung cấp đã bão hòa.

**Ví dụ xuyên suốt:** một nền tảng bán hàng dùng API gateway, dịch vụ đặt hàng chạy trên container, cơ sở dữ liệu được quản lý, cache và hàng đợi xử lý thanh toán. Doanh nghiệp dự kiến có đỉnh 600 yêu cầu/giây trong chiến dịch bán hàng, trong đó 10% là thao tác tạo đơn. Kiến trúc sư cần chứng minh luồng đặt hàng đáp ứng thời gian phản hồi đã cam kết, không mất hoặc tạo trùng đơn, và tiếp tục ổn định khi chiến dịch kéo dài.

> **Nguyên tắc:** Đánh giá năng lực theo **tải được phục vụ thành công trong phạm vi SLO**, không theo con số request/giây cao nhất mà hệ thống từng nhận trước khi lỗi.

## 2. Hiểu đúng các khái niệm đo lường

| Khái niệm | Ý nghĩa | Hiểu nhầm thường gặp |
|---|---|---|
| **Throughput** | Khối lượng công việc hoàn tất trong một đơn vị thời gian, ví dụ đơn hàng thành công/phút | Đếm mọi request, kể cả request lỗi, là năng lực nghiệp vụ thực |
| **Arrival rate** | Tốc độ công việc đến hệ thống, ví dụ 600 request/giây | Giả định tốc độ gửi vào luôn bằng tốc độ xử lý thành công |
| **Response time / latency** | Thời gian từ khi client bắt đầu đến khi nhận phản hồi theo phạm vi đo | Chỉ xem thời gian CPU của ứng dụng và bỏ qua chờ mạng, DB, queue |
| **Concurrency** | Số yêu cầu hoặc công việc cùng đang xử lý | Nhầm với tổng số người dùng đang đăng nhập |
| **Error rate** | Tỷ lệ yêu cầu thất bại theo định nghĩa SLI | Chỉ đếm HTTP 500, bỏ qua timeout, từ chối, sai nghiệp vụ hoặc lỗi được che bởi retry |
| **Saturation** | Mức cạn kiệt của tài nguyên giới hạn năng lực | Cứ CPU thấp là hệ thống chưa bão hòa |
| **Queue depth/lag** | Số lượng hoặc độ trễ công việc chưa xử lý trong hệ thống bất đồng bộ | API trả 202 nhanh thì toàn quy trình đã hoàn thành |
| **Capacity** | Mức tải tối đa *được chứng minh* vẫn đạt điều kiện phục vụ | Dùng giá trị cấu hình quota hoặc kết quả của một lần test ngắn |
| **Scalability** | Khả năng tăng năng lực nhờ tăng tài nguyên, xét cả thời gian và chi phí | Thêm 2 lần instance chắc chắn tăng 2 lần throughput |
| **SLO/SLI** | Mục tiêu và chỉ số thể hiện mức chất lượng dịch vụ | Dùng một mục tiêu độ trễ chung cho mọi endpoint và quy trình |

### 2.1. Độ trễ trung bình không mô tả trải nghiệm xấu nhất

Độ trễ nên được theo dõi theo phân phối, đặc biệt **p50, p95, p99** và số lượng request thuộc nhóm đuôi chậm. Ví dụ p95 = 500 ms có nghĩa khoảng 95% mẫu quan sát có độ trễ không vượt 500 ms, tùy cách công cụ tính và mẫu hợp lệ.

Trong hệ thống nhiều tầng, độ trễ p99 của một dịch vụ có thể ảnh hưởng mạnh đến thời gian hoàn thành giao dịch khi request phải chờ nhiều thành phần. Không cộng các p95 riêng lẻ để khẳng định p95 đầu-cuối: phân vị không có tính cộng đơn giản. Cần đo trực tiếp **hành trình người dùng** hoặc giao dịch nghiệp vụ.

### 2.2. Số người dùng ảo không tương đương request/giây

Một người dùng ảo (VU) thường mô phỏng chuỗi hành động, thời gian đọc/nghỉ (*think time*) và các bước nghiệp vụ. Số VU giữ nguyên không bảo đảm arrival rate giữ nguyên: khi hệ thống chậm, mỗi VU hoàn thành ít vòng lặp hơn. Điều này có thể khiến công cụ vô tình giảm tải vào đúng lúc hệ thống suy yếu.

Hai mô hình tạo tải quan trọng:

- **Closed workload model:** số VU đồng thời được kiểm soát; mỗi VU thường đợi công việc trước hoàn tất rồi mới bắt đầu công việc tiếp theo. Phù hợp mô phỏng phiên làm việc nhưng tốc độ gửi có thể giảm khi phản hồi chậm.
- **Open workload model:** công việc được đưa vào với arrival rate mục tiêu, độc lập hơn với thời gian phản hồi của công việc trước. Phù hợp kiểm tra khả năng chịu một tốc độ yêu cầu đến từ bên ngoài; cần đủ worker của công cụ phát tải.

Lựa chọn mô hình dựa vào hành vi thực. Chẳng hạn quá trình gửi webhook từ một hệ thống khác có thể gần với arrival-rate model; hành vi một người dùng duyệt và đọc sản phẩm có think time và giới hạn hành động đồng thời.

### 2.3. Mối liên hệ giữa tải, độ trễ và số yêu cầu đang xử lý

Ở trạng thái ổn định, **định luật Little** cho một phạm vi hệ thống được đo nhất quán:

\[
L = \lambda W
\]

Trong đó \(L\) là số công việc trung bình đang trong hệ thống, \(\lambda\) là tốc độ hoàn tất trung bình và \(W\) là thời gian một công việc lưu lại trong hệ thống. Ví dụ ở mức 300 yêu cầu/giây với thời gian đầu-cuối trung bình 0,2 giây, có khoảng \(300 \times 0,2 = 60\) yêu cầu đồng thời trong phạm vi đo.

Nếu độ trễ tăng lên 1 giây trong khi vẫn có 300 yêu cầu/giây được xử lý ổn định, số yêu cầu trong hệ thống tăng lên khoảng 300. Điều này có thể làm đầy connection pool, thread pool hoặc giới hạn in-flight. Công thức mô tả trạng thái cân bằng; khi hàng đợi tăng liên tục, hệ thống **chưa** ở trạng thái ổn định nên phải xem cả tốc độ đến, tốc độ xử lý và backlog.

## 3. Phân biệt các kiểu kiểm thử và câu hỏi kiến trúc

| Kiểu kiểm thử | Hình dạng tải điển hình | Câu hỏi muốn trả lời |
|---|---|---|
| **Baseline** | Tải thấp, ổn định, đủ làm nóng | Độ trễ và mức sử dụng tài nguyên bình thường là bao nhiêu? |
| **Load test** | Tải thường gặp và đỉnh dự báo | Hệ thống đạt SLO ở mức phục vụ dự kiến không? |
| **Stress test** | Tăng vượt tải mục tiêu theo bước có kiểm soát | Điểm bắt đầu quá tải ở đâu, lỗi diễn ra thế nào? |
| **Spike test** | Tăng hoặc giảm rất nhanh | Có hấp thụ được đột biến hoặc phục hồi sau đỉnh không? |
| **Soak/endurance test** | Tải vừa hoặc cao được duy trì lâu | Có memory leak, backlog, cạn connection hoặc suy giảm tích lũy? |
| **Scalability test** | Thay đổi tải cùng số lượng/kích thước tài nguyên | Mở rộng ngang/dọc có tăng năng lực thật và có hiệu quả chi phí? |
| **Recovery test** | Trở về tải thấp hoặc bỏ một thành phần theo kế hoạch | Sau khi quá tải/hỏng một phần, hệ thống trở lại trạng thái ổn định nhanh đến đâu? |

Một bài đánh giá kiến trúc có thể phối hợp nhiều kiểu nhưng **mỗi lần chạy cần một giả thuyết kiểm chứng rõ ràng**. Không nên trộn stress, đổi cấu hình, failover và thay dữ liệu cùng lúc rồi kết luận nguyên nhân chỉ từ một biểu đồ.

## 4. Từ yêu cầu nghiệp vụ đến mô hình tải

### 4.1. Mô tả giao dịch thay vì chỉ mô tả endpoint

Người dùng thường thực hiện các hành trình như xem sản phẩm, tìm kiếm, thêm giỏ, đặt hàng, thanh toán và theo dõi đơn. Mỗi hành trình có tỷ trọng lưu lượng, dữ liệu, độ trễ chấp nhận được và hậu quả lỗi khác nhau.

Một **workload profile minh họa** cho hệ thống bán hàng:

| Hành trình | Tỷ trọng request | Mức đỉnh tại 600 req/s | Đặc điểm |
|---|---:|---:|---|
| Xem danh mục / chi tiết | 50% | 300 req/s | Phần lớn là đọc, dễ chịu ảnh hưởng cache |
| Tìm kiếm | 25% | 150 req/s | Có truy vấn phức tạp và độ lệch theo từ khóa |
| Giỏ hàng | 15% | 90 req/s | Đọc/ghi, có phiên người dùng |
| Tạo đơn / checkout | 10% | 60 req/s | Ghi, giao dịch nghiệp vụ, thường liên quan DB và queue |
| **Tổng** | **100%** | **600 req/s** | Mô hình cần kiểm tra bằng số liệu thật |

Đây chỉ là giả định dạy học. Trong hệ thống thật, hãy lấy dữ liệu từ access log, APM, phân tích kinh doanh, sản lượng đơn, sự kiện chiến dịch, ngày cao điểm và dự báo tăng trưởng. Đừng lấy tỷ lệ của một ngày bình thường rồi mặc định áp dụng cho ngày flash sale.

Các tham số tải cần xác định:

1. **RPS/TPS đỉnh và trung bình:** kể cả tốc độ tăng tải (ramp rate), thời gian kéo dài đỉnh và dự báo tăng trưởng.
2. **Tỷ lệ đọc/ghi và hành trình:** một request tạo đơn có thể tạo nhiều lần ghi, sự kiện và yêu cầu xuống downstream.
3. **Đặc tính dữ liệu:** kích thước payload, số dòng trên bảng, phân bố ID, số lượng tenant, khóa “nóng”, số kết quả tìm kiếm.
4. **Phân bố người dùng:** theo vùng, thiết bị, phiên đăng nhập, token, địa chỉ mạng, tính mùa vụ và giờ cao điểm.
5. **Hành vi cache:** cold/warm cache, tỷ lệ hit, dữ liệu có thể cache và thời hạn hiệu lực.
6. **Phụ thuộc bên ngoài:** payment gateway, email, SMS, hệ thống ERP; giới hạn tốc độ và hành vi timeout/retry.
7. **Tính bất đồng bộ:** số event phát sinh từ mỗi hành động, độ trễ queue, độ dài xử lý hậu trường và điều kiện hoàn thành nghiệp vụ.

### 4.2. Kiểm soát việc tính tải từ dữ liệu kinh doanh

Giả sử doanh nghiệp kỳ vọng 36.000 đơn/giờ trong cao điểm. Tốc độ trung bình theo giờ là \(36.000/3.600 = 10\) đơn/giây. Con số này **không đồng nghĩa** 10 request/giây cho hệ thống:

- Mỗi đơn có thể cần nhiều request của hành trình checkout.
- Lưu lượng có thể dồn vào vài phút trong giờ cao điểm.
- Có người dùng duyệt sản phẩm nhưng không mua, tạo lưu lượng đọc lớn hơn nhiều.
- Client retry hoặc webhook có thể làm tăng request nhưng không tăng đơn hợp lệ.

Cần mô hình hóa số lượng **đơn thành công** và số request của từng thao tác riêng, tránh dùng tổng RPS làm đại diện duy nhất cho khả năng phục vụ.

## 5. Xác lập SLI, SLO và điều kiện nghiệm thu

Kiểm thử phải kết luận được *đạt hoặc không đạt* đối với một yêu cầu. SLO đặt theo mức trải nghiệm và mức rủi ro chấp nhận của doanh nghiệp, không lấy trực tiếp từ khả năng hiện tại của hạ tầng.

Ví dụ một bộ **tiêu chí minh họa**, cần điều chỉnh theo ứng dụng:

| Hạng mục | SLI | SLO/điều kiện trong kịch bản đỉnh |
|---|---|---|
| Duyệt sản phẩm | Độ trễ đầu-cuối p95 | Dưới 300 ms |
| Checkout | Độ trễ phản hồi tạo đơn p95 | Dưới 800 ms |
| Tạo đơn thành công | Tỷ lệ yêu cầu được xử lý đúng nghiệp vụ | Từ 99,5% trở lên, loại trừ lỗi đầu vào theo định nghĩa đã duyệt |
| Xử lý event thanh toán | Độ trễ từ nhận đến hoàn tất p95 | Dưới 10 giây |
| Khả năng xử lý | Đơn hợp lệ hoàn tất/phút | Đạt mức dự báo và không tăng backlog vô hạn |
| Phục hồi sau spike | Thời gian trở về SLO | Dưới mốc thỏa thuận, ví dụ 5 phút |
| Chi phí | Chi phí trên 1.000 giao dịch thành công | Không vượt ngân sách năng lực đã phê duyệt |

**Định nghĩa mẫu đo phải rõ:** độ trễ đo từ nơi phát tải hay từ gateway; có tính thời gian hàng đợi hay không; “thành công” là HTTP 202 hay đơn đã thật sự ghi nhận; timeout do client có được tính lỗi không; cửa sổ đo bao lâu. Với luồng bất đồng bộ, HTTP 202 chỉ cho biết yêu cầu có thể đã được nhận, chưa chứng minh hoàn tất nghiệp vụ.

Ngoài mục tiêu nghiệp vụ, cần đặt **guardrail** vận hành như CPU, memory, connection pool, quota, độ dài queue và mức tăng retry. Đây là chỉ báo chẩn đoán và dự phòng, không thay thế SLO đầu-cuối. Ví dụ CPU 80% có thể ổn ở một workload được tối ưu, trong khi CPU 30% vẫn có thể đi kèm database lock hoặc cạn số kết nối.

## 6. Thiết kế môi trường thử nghiệm đáng tin cậy

### 6.1. Mức độ tương đồng với production

Môi trường kiểm thử nên tương đồng các yếu tố ảnh hưởng kết quả: loại compute, số replica, autoscaling, cấu hình database, index, cache, network, service mesh/gateway, bảo mật, quota, observability và tập dữ liệu. Nếu sử dụng môi trường nhỏ hơn, cần ghi **sự khác biệt** và giới hạn suy luận; không tự nhân tuyến tính kết quả theo số core.

Một số yếu tố dễ làm sai lệch:

- Database chỉ có vài nghìn dòng trong thử nghiệm nhưng production có hàng chục triệu dòng.
- Tất cả request dùng một khóa cache nên tỷ lệ cache hit phi thực tế.
- Chạy công cụ tạo tải cùng máy với ứng dụng, gây tranh chấp CPU/băng thông.
- Dùng mock cho payment có độ trễ gần 0 rồi kết luận checkout thực sẽ nhanh như vậy.
- Tắt xác thực, TLS, WAF hoặc một middleware đắt đỏ để test, trong khi production luôn bật.
- Chỉ đo khi mọi cache đã nóng dù hệ thống thường trải qua restart, rollout hoặc failover.
- Không giữ tải đủ lâu để autoscaling, queue hoặc hệ thống lưu trữ bộc lộ trạng thái ổn định.

Mỗi khác biệt có thể chấp nhận nếu được ghi rõ và đánh giá ảnh hưởng. **Kết luận của bài kiểm thử chỉ có giá trị trong phạm vi môi trường, tải, dữ liệu và thời điểm đã đo.**

### 6.2. Phạm vi, quyền và an toàn thử nghiệm

Chỉ tạo tải trên môi trường/endpoint được chủ hệ thống cho phép. Thống nhất trước thời gian, mức tải tối đa, tác động đối với tenant và đối tác, ngưỡng dừng, người phụ trách trực và cách phục hồi. Với thao tác tạo đơn, thu tiền hoặc gửi thông báo:

- Dùng dữ liệu giả hoặc dữ liệu đã được xử lý theo chính sách.
- Dùng payment sandbox, chế độ giả lập hoặc stub có hành vi độ trễ/lỗi được quy định; không phát sinh thanh toán thật.
- Gắn ID của đợt thử nghiệm để nhận diện, làm sạch hoặc đối soát bản ghi.
- Hạn chế việc gửi email/SMS thật; kiểm soát rate limit và khả năng tính phí của dịch vụ ngoài.
- Bảo vệ secret và token bằng cơ chế quản lý bí mật; không hard-code trong kịch bản.
- Đặt điểm dừng nếu có dấu hiệu ảnh hưởng hệ thống ngoài phạm vi hoặc vượt ngân sách.

Không nên tự “thử ngưỡng” lên hệ thống bên thứ ba nếu chưa được phép. Với phụ thuộc thực có giới hạn, có thể dùng bộ mô phỏng kiểm soát được rồi chạy một phép xác minh tích hợp nhỏ trong hạn mức cho phép.

### 6.3. Kiến trúc một hệ thống đo

~~~mermaid
flowchart LR
    T[Load generator / Workers] --> E[API Gateway / LB]
    E --> A[Application replicas]
    A --> C[(Cache)]
    A --> D[(Database)]
    A --> Q[Queue / Event bus]
    Q --> W[Background workers]
    W --> D
    A --> S[External service hoặc Sandbox]
    T -. Client metrics .-> M[Metrics / Logs / Traces]
    E -. Telemetry .-> M
    A -. Telemetry .-> M
    D -. Telemetry .-> M
    Q -. Telemetry .-> M
    W -. Telemetry .-> M
    H[Autoscaler / Quotas] --> A
    H -. Events .-> M
~~~

Hệ thống tạo tải nên có metric riêng về CPU, network, số VU/worker và **khả năng đạt arrival rate**. Nếu máy tạo tải bị nghẽn, kết quả chỉ chứng minh giới hạn của công cụ đo.

## 7. Quan sát đầy đủ toàn bộ đường đi

Tối thiểu nên thu thập và gắn thời điểm chung cho những nhóm metric:

| Lớp | Metric trọng tâm | Câu hỏi chẩn đoán |
|---|---|---|
| **Load generator** | Requested/achieved rate, VU, dropped iterations, client timeout, latency | Công cụ có thực sự phát đủ tải mục tiêu? |
| **Gateway / LB** | Request count, status, 4xx/5xx, p95/p99, throttle, connection, TLS | Lưu lượng bị từ chối hay chậm từ mép hệ thống? |
| **Ứng dụng** | p50/p95/p99 theo endpoint, thread/worker pool, CPU, memory, GC, heap, request in-flight | Nghẽn ở xử lý ứng dụng hay chờ downstream? |
| **Database** | Query latency, wait/lock, connection pool, CPU/IOPS, replication lag, slow query | DB có giới hạn số kết nối, lock hoặc IO? |
| **Cache** | Hit ratio, eviction, memory, hot key, request latency | Cache có thực sự giảm tải backend? |
| **Queue / Worker** | Enqueue/dequeue rate, backlog, oldest age, retry, DLQ, consumer lag | API trả nhanh nhưng xử lý hậu trường có tụt lại? |
| **Cloud platform** | Replicas desired/ready, autoscaling event, startup/readiness, quota, rate limit | Tài nguyên có tăng đúng lúc và đạt readiness? |
| **Business** | Đơn thành công, đơn trùng, thanh toán lỗi, tồn kho, độ trễ hoàn tất | Số liệu kỹ thuật có khớp kết quả nghiệp vụ? |
| **Cost** | Compute, database, egress, cache, log, trace, dịch vụ bên ngoài | Đạt SLO ở mức chi phí nào? |

**Phân biệt các tầng độ trễ:** đo từ client cho thấy trải nghiệm mạng + ứng dụng; server span cho thấy thời gian xử lý một dịch vụ; database span hoặc query metric cho thấy thời gian gọi DB. Trace có thể làm rõ chuỗi phụ thuộc, nhưng sampling phải phù hợp tải; không nên bật trace chi tiết cho mọi request ở mức rất cao nếu chi phí và overhead vượt giới hạn.

Với percentile, sử dụng histogram hoặc phương pháp tổng hợp phân phối được công cụ hỗ trợ. **Không lấy trung bình cộng các p95 của nhiều instance** để suy ra p95 toàn hệ thống. Kết hợp dữ liệu ở mức phân phối hoặc tính từ dữ liệu quan sát phù hợp.

## 8. Lập ma trận và trình tự thử nghiệm

Một quy trình thực tế nên tiến từ kiểm tra nhỏ đến thử nghiệm gây áp lực cao, giúp phát hiện lỗi cấu hình trước khi tốn chi phí lớn.

| Giai đoạn | Tải minh họa | Thời lượng minh họa | Mục tiêu |
|---|---|---|---|
| **0. Smoke & dữ liệu** | 1–5 req/s | Vài phút | Xác nhận script đúng, dữ liệu tạo/đọc hợp lệ, metric đầy đủ |
| **1. Baseline** | 50 req/s | 10–15 phút | Ghi độ trễ, tỷ lệ lỗi và tài nguyên khi ổn định |
| **2. Load tăng dần** | 100 → 200 → 400 → 600 req/s | Đủ để ổn định ở mỗi mức | Tìm điểm bắt đầu tăng latency/error và quan sát autoscaling |
| **3. Peak** | 600 req/s | Theo độ dài đỉnh kinh doanh | Chứng minh đạt SLO tại mức đỉnh dự báo |
| **4. Stress/capacity** | 650 → 800 → ... | Từng bước có điều kiện dừng | Xác định vùng giới hạn và cách hệ thống thất bại |
| **5. Spike** | 100 → 600 → 100 req/s nhanh | Các đợt riêng | Kiểm tra phản ứng autoscaling, cache, backlog và phục hồi |
| **6. Soak** | 200–400 req/s hoặc tải đại diện | Nhiều giờ hoặc nhiều chu kỳ | Tìm suy giảm theo thời gian và lỗi tích lũy |
| **7. Scale-in/out** | Lặp mức tải với số replica/quota khác | Các lần chạy so sánh | Đo hiệu quả mở rộng và chi phí, phát hiện bottleneck mới |

Những con số trên không phải chuẩn bắt buộc. Với hệ thống khác, mức tải và thời gian phải được tính từ SLO, volume dữ liệu, giới hạn tác động và chu kỳ vận hành. Thời gian của mỗi stage phải đủ để thành phần cần đo tiến gần trạng thái ổn định, kể cả startup và warmup khi autoscaler hoạt động.

### 8.1. Kiểm soát biến số

Trong một loạt so sánh, cố gắng giữ cố định **phiên bản ứng dụng, dữ liệu, cấu hình, vùng mạng, mô hình tải, phương pháp ghi metric** và chỉ thay đổi biến muốn kiểm chứng. Nếu đồng thời tăng replica, thêm index và thay cache, không thể quy công cho riêng một thay đổi.

Ghi lại thời điểm test, commit/release, cấu hình hạ tầng, dữ liệu, mức tải, trạng thái cache, quota, và dịch vụ phụ thuộc. Một phép đo đơn lẻ có thể chứa nhiễu từ neighbor workload, cache, network hoặc hệ thống lưu trữ; các kết luận quan trọng nên được xác nhận bằng những lần chạy có điều kiện tương đương.

### 8.2. Tạo tải có phản hồi và giới hạn dừng

Cấu hình mức tải tối đa được phép và các điều kiện dừng như tỷ lệ lỗi cao kéo dài, quá tải database, chi phí vượt kế hoạch hoặc ảnh hưởng đến hệ thống liên quan. Ở điểm bão hòa, tiếp tục tăng tải không làm phép đo “chính xác hơn” nếu hệ thống và nguồn dữ liệu đã mất ổn định.

Trong một chương trình đánh giá, xác minh kế hoạch phục hồi và dọn dữ liệu thử trước khi chạy stress/soak dài.

## 9. Ví dụ kịch bản load test với k6

Ví dụ dưới đây tạo tải **đọc** cho endpoint minh họa /api/products. Nó sử dụng mô hình open arrival rate để yêu cầu công cụ tạo trung bình 50 iteration/giây trong 10 phút. Người vận hành cần thay endpoint, tỷ trọng hành trình, ngưỡng SLO và tài nguyên load generator cho đúng hệ thống.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    browse_products: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 100,
      maxVUs: 300,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    'http_req_duration{endpoint:products}': ['p(95)<500'],
    'http_req_failed{endpoint:products}': ['rate<0.01'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('Missing BASE_URL');
  }

  const response = http.get(
    baseUrl + '/api/products?limit=20',
    {
      headers: { 'X-Load-Test-Run': __ENV.RUN_ID || 'demo-run' },
      tags: { endpoint: 'products' },
      timeout: '5s',
    }
  );

  check(response, {
    'HTTP 200': (r) => r.status === 200,
    'JSON response': (r) => {
      const contentType = r.headers['Content-Type'] || '';
      return contentType.includes('application/json');
    },
  });
}
~~~

Ví dụ gọi từ môi trường được cho phép:

~~~bash
BASE_URL=https://performance.example.test RUN_ID=assessment-001 k6 run browse-products.js
~~~

Cú pháp đặt biến môi trường trên cùng dòng ở đây dành cho shell POSIX; với PowerShell/Windows cần đặt biến môi trường theo cú pháp của shell đó. Tên miền trong ví dụ chỉ là placeholder.

**Cách đọc kết quả:**

- Nếu **dropped_iterations > 0**, công cụ chưa phát được đủ iteration theo lịch; cần kiểm tra mức VU, CPU/mạng của máy tạo tải và thời gian xử lý.
- Nếu đạt 50 iteration/giây nhưng mỗi iteration phát nhiều HTTP request thì **RPS có thể khác 50**. Ở ví dụ này mỗi iteration gọi một GET nên hai giá trị gần nhau khi không có lỗi phát tải.
- Ngưỡng p95 và lỗi ở script chỉ là ví dụ; phải được thiết kế theo SLO thực. Trạng thái HTTP 200 không tự xác nhận dữ liệu trả về đúng nghiệp vụ.
- Khi chạy load test ghi dữ liệu, cần quản lý ID thử nghiệm, chống gửi trùng, xác minh trạng thái cuối và làm sạch dữ liệu.

Một load test nghiệp vụ hoàn chỉnh thường cần nhiều kịch bản được tổ chức theo tỷ lệ (xem, tìm kiếm, đặt đơn...), xử lý token hợp lệ, dữ liệu ngẫu nhiên có phân bố hợp lý và các bước kiểm chứng kết quả. Không nên copy kịch bản GET duy nhất rồi suy ra năng lực toàn hệ thống.

## 10. Tìm điểm bão hòa và giới hạn mở rộng

### 10.1. Biểu hiện của “điểm gối” trên đường cong tải

Khi tăng arrival rate, thông lượng thành công ban đầu tăng gần tuyến tính và độ trễ còn ổn. Đến vùng bão hòa, throughput tăng chậm lại nhưng **p95/p99, backlog và tỷ lệ timeout có thể tăng rất nhanh**. Sau điểm này, tăng request chỉ làm nhiều công việc chờ hoặc thất bại.

Ví dụ một loạt phép đo minh họa khi mỗi mức đã đủ thời gian ổn định:

| Arrival rate mục tiêu | Throughput hoàn tất (req/s) | p95 (ms) | Tỷ lệ lỗi | CPU ứng dụng | Backlog queue |
|---:|---:|---:|---:|---:|---:|
| 200 | 199 | 190 | 0,0% | 35% | 0 |
| 400 | 397 | 280 | 0,1% | 52% | 0 |
| 600 | 593 | 470 | 0,5% | 76% | 40 |
| 800 | 642 | 1.450 | 6,0% | 96% | 3.500 |

Nếu SLO của hành trình này là **p95 dưới 500 ms và tỷ lệ lỗi dưới 1%**, thì 600 req/s là **mức tải đã kiểm chứng đạt mục tiêu trong lần chạy minh họa**; 800 req/s không đạt. Chưa thể tuyên bố “năng lực tuyệt đối bằng 600 req/s”: cần đo thêm vùng giữa 600 và 800, kiểm tra backlog 40 có đang tăng và xác minh dưới soak test. Nếu backlog tăng không ngừng ở mức 600, mức này chưa bền vững dù p95 HTTP tạm đạt.

### 10.2. Phân biệt giới hạn của hệ thống và của công cụ đo

Đôi khi kết quả chỉ tăng đến 600 req/s vì **load generator hết CPU hoặc VU**, không phải vì hệ thống đích đã bão hòa. Hãy đối chiếu:

1. Tốc độ mong muốn, tốc độ phát thực tế và số iteration bị bỏ.
2. CPU, memory, network, DNS, TLS và file descriptor trên máy phát tải.
3. Throughput nhận từ gateway và throughput hoàn tất ở backend.
4. Tỷ lệ lỗi, timeout và đồ thị saturation của SUT.
5. Khả năng tăng tải khi phân tán load generator mà không thay cấu hình SUT.

Chỉ khi công cụ đo đủ năng lực mới có cơ sở xác định giới hạn của hệ thống cần kiểm thử (System Under Test – SUT).

### 10.3. Giới hạn kiến trúc thường không nằm ở CPU của service

Các điểm nghẽn điển hình:

- **Database:** connection pool đầy, lock contention, query plan xấu, write IOPS, giới hạn replica hoặc hot partition.
- **Cache:** cache stampede khi key hết hạn, hit rate giảm đột ngột, eviction quá mức.
- **Queue:** worker xử lý chậm hơn tốc độ enqueue, backlog/oldest message tăng.
- **Mạng và gateway:** giới hạn kết nối, NAT port, LB quota, TLS handshake, throttling của API gateway.
- **Compute:** CPU saturation, GC pause, thread/async worker pool, giới hạn memory hoặc file descriptor.
- **Hạ tầng cloud:** quota tài khoản/vùng, giới hạn autoscaling, số IP, số kết nối DB, giới hạn dịch vụ managed.
- **Phụ thuộc bên ngoài:** rate limit hoặc thời gian phản hồi của cổng thanh toán, e-mail, dịch vụ định danh.

Để kết luận đúng, luôn nối **triệu chứng trên client** với **bằng chứng tại thành phần giới hạn**. Ví dụ p99 tăng mạnh và CPU app chỉ 45% có thể do application chờ connection pool DB 100% sử dụng; thêm replica app có thể làm tình hình tệ hơn nếu tổng kết nối sang DB tiếp tục tăng.

## 11. Kiểm tra khả năng mở rộng ngang, dọc và theo nhu cầu

### 11.1. Scale-up, scale-out và giới hạn hạ nguồn

- **Scale-up (mở rộng dọc):** tăng CPU, RAM hoặc thông số một instance/DB. Có thể nhanh để giải quyết bottleneck cục bộ nhưng bị giới hạn kích thước, giá và khả năng dừng đổi cấu hình.
- **Scale-out (mở rộng ngang):** tăng replica xử lý, worker, partition hoặc shard khi phần mềm có thể phân phối tải. Có lợi cho cô lập lỗi và linh hoạt, nhưng đồng thời tăng kết nối, đồng bộ, cache phân tán và chi phí.
- **Autoscaling:** điều chỉnh năng lực theo metric/triggers và giới hạn đã cấu hình. Cần kiểm tra độ trễ phản ứng, tốc độ startup, readiness, cooldown, chi phí và hành vi scale-in.

Không có bảo đảm rằng thêm gấp đôi replica sẽ tăng gấp đôi throughput. Một tài nguyên dùng chung có thể trở thành giới hạn mới.

### 11.2. Thử nghiệm hiệu quả mở rộng

Giữ workload và điều kiện dữ liệu tương đương, đo nhiều cấu hình:

| Cấu hình minh họa | Throughput đạt SLO (req/s) | Hiệu quả tăng năng lực | Điều cần xem tiếp |
|---|---:|---|---|
| 2 replica | 300 | Mốc so sánh | CPU, DB, queue, p95/p99 |
| 4 replica | 540 | Tăng 1,8 lần so với 2 replica | Tại sao không đạt 2 lần? |
| 8 replica | 620 | Chỉ tăng 1,15 lần so với 4 replica | DB hay tài nguyên dùng chung đã bão hòa? |

Ví dụ này chỉ mang tính minh họa. **Scaling efficiency** giữa hai cấu hình có thể ước tính bằng:

\[
E = \frac{\text{Throughput mới} / \text{Throughput cũ}}
{\text{Tài nguyên mới} / \text{Tài nguyên cũ}}
\]

Nếu từ 2 lên 4 replica cho throughput tăng từ 300 lên 540 req/s, \(E = (540/300)/(4/2) = 0{,}9\), tức khoảng 90% hiệu quả mở rộng tương đối trong phép thử đó. Cần so sánh cùng SLO, cấu hình dữ liệu, loại tải và tính đủ chi phí DB/cache/network để tránh tối ưu một lớp mà làm tăng chi phí lớp khác.

### 11.3. Kiểm tra autoscaling theo thời gian

Ở mức 100 → 600 req/s, hãy ghi:

1. **Thời điểm metric vượt ngưỡng:** CPU, request concurrency, queue lag hoặc metric theo thiết kế.
2. **Thời điểm autoscaler yêu cầu thêm replica:** so với sự kiện tải tăng.
3. **Thời điểm replica mới sẵn sàng phục vụ:** bao gồm image pull, startup, warm cache, readiness probe.
4. **Độ trễ và lỗi trong khoảng chờ:** tài nguyên mới chưa ready nhưng traffic đã tăng.
5. **Hành vi sau đỉnh:** scale-in, đóng connection, xử lý in-flight và khả năng giữ ổn định.

Đừng đo riêng số replica cuối cùng. Với đỉnh kéo dài hai phút nhưng instance cần bốn phút mới sẵn sàng, autoscaler có thể không giúp được ở chính thời điểm quan trọng nhất. Có thể phải dùng **scheduled/pre-warming capacity**, min replica, queue buffering hoặc tối ưu thời gian khởi động.

Nếu autoscale theo CPU trong khi bottleneck thực nằm ở DB hoặc queue, metric điều khiển có thể phản ứng chậm hoặc sai. Lựa chọn metric phải gắn với tài nguyên giới hạn và nhu cầu phục vụ. Đặt upper/lower bound, rate limit và ngân sách để tránh tăng tài nguyên không kiểm soát.

### 11.4. Kiểm tra quota trước khi tin vào thiết kế mở rộng

Giả sử kế hoạch cần tăng từ 4 lên 20 replica để chống flash sale, nhưng node quota, subnet IP hoặc giới hạn kết nối database chỉ đáp ứng được 12 replica. Kiến trúc có autoscaling “đúng” trên YAML vẫn không đạt năng lực mục tiêu. Cần kiểm tra quota theo **account, region, resource type**, cả quota mềm và giới hạn cứng của dịch vụ.

## 12. Soak test: kiểm tra những lỗi chỉ xuất hiện theo thời gian

**Soak test** duy trì một mức tải có ý nghĩa đủ lâu để quan sát vòng đời tài nguyên và quy trình vận hành. Mục tiêu không chỉ là “không crash sau 24 giờ”, mà là xác minh chất lượng phục vụ không suy giảm, tài nguyên không tăng vô hạn và công việc không bị tích lũy.

### 12.1. Khi nào cần chạy đủ lâu?

Thời lượng phải đi theo rủi ro và chu kỳ:

- **Vài giờ:** phát hiện rò rỉ nhanh, retry tích lũy, connection leak, cache churn, memory/GC tăng liên tục.
- **Qua một hoặc nhiều chu kỳ vận hành:** kiểm tra token refresh, certificate rotation, log rotation, scheduled job, backup, cache TTL hoặc batch cuối ngày.
- **Nhiều ngày:** phát hiện vấn đề có tốc độ tích lũy chậm hoặc phụ thuộc lịch ngày/tuần, nếu ngân sách và môi trường cho phép.

Không có con số cố định dùng cho mọi ứng dụng. Một test 24 giờ không thể chứng minh hệ thống an toàn trong 90 ngày, nhất là khi chỉ số tăng chậm hoặc chưa bao phủ tác vụ định kỳ quan trọng.

### 12.2. Các chỉ báo suy giảm dài hạn

| Tín hiệu | Cách quan sát | Nguy cơ |
|---|---|---|
| Memory tăng đều theo giờ | Heap, RSS, GC, cache entries, memory sau mỗi chu kỳ | Memory leak hoặc cache không giới hạn |
| Số kết nối tăng dần | DB connections, HTTP pool, socket, file descriptor | Connection/resource leak |
| Queue backlog/lag tăng | Enqueue vs dequeue, age of oldest, retry, DLQ | Consumer không theo kịp trong tải lâu dài |
| p95/p99 tăng dù RPS ổn định | Latency time series, slow traces, DB waits | Tích lũy contention, heap, lock hoặc IO |
| Lỗi xuất hiện theo chu kỳ | Log rotation, batch, backup, refresh token | Cơ chế vận hành làm gián đoạn |
| Dung lượng log/storage tăng | Disk, object storage, telemetry volume, retention | Hết dung lượng hoặc chi phí quan sát ngoài dự kiến |
| Autoscaler dao động | Desired/ready replica, CPU, queue, cooldown | Scaling thrash, thiếu ổn định hoặc chi phí cao |
| Business state lệch dần | Đếm đơn, sự kiện, đối soát trạng thái | Retry hoặc xử lý bất đồng bộ tạo trùng/mất dữ liệu |

### 12.3. Phân biệt memory leak với bộ nhớ dùng hợp lệ

Không nên gọi mọi đường RSS tăng là leak. Khi khởi động, JIT, buffer, cache hoặc connection pool có thể tăng đến mức ổn định. Một số runtime giữ lại bộ nhớ đã cấp phát dù đã giải phóng đối tượng. Cần xem:

- Mức dùng bộ nhớ **sau warmup** và sau các chu kỳ GC liên quan.
- Xu hướng tăng lâu dài ở cùng mức tải và với tập dữ liệu tương đương.
- Cấu trúc heap, số object, kích thước cache, file descriptor và connection count.
- Sự khác biệt giữa tăng tạm thời, ổn định ở plateau và tăng không bị chặn.

Ví dụ nếu heap sau GC tăng từ 1,0 GB lên 1,6 GB trong 8 giờ với lượng công việc ổn định, đây là tín hiệu cần điều tra; chưa đủ bằng chứng kết luận leak nếu cache hợp lệ đang được làm nóng theo dataset lớn hơn.

### 12.4. Cách chạy và đánh giá soak test

1. Chạy warmup, ghi baseline khi trạng thái ổn định.
2. Giữ workload mix, dữ liệu đầu vào và arrival rate được kiểm soát; theo dõi achieved rate.
3. Thu thập liên tục telemetry ở các lớp và kiểm tra hoàn tất nghiệp vụ, không chỉ HTTP.
4. Ghi riêng những sự kiện có chủ ý: deployment, autoscaling, backup, rotation, cron job.
5. So sánh giai đoạn đầu, giữa và cuối về p95/p99, lỗi, queue lag và tài nguyên sau warmup.
6. Hạ tải và quan sát recovery: queue có thoát backlog không, memory/connection có trở về mức hợp lý không, cảnh báo có kết thúc không.

**Ví dụ điều kiện không đạt:** hệ thống giữ HTTP p95 dưới 500 ms trong 12 giờ nhưng mỗi giờ tồn thêm 100.000 event chưa xử lý. Dù endpoint trả nhanh, kiến trúc vẫn không có năng lực bền vững cho quy trình bất đồng bộ.

## 13. Mối quan hệ giữa hàng đợi, năng lực và nợ xử lý

Với luồng bất đồng bộ, hãy đo riêng tốc độ nhận công việc \(\lambda_{\text{in}}\) và tốc độ hoàn tất \(\mu_{\text{out}}\). Trong một khoảng quan sát, backlog biến thiên xấp xỉ:

\[
\Delta Q \approx (\lambda_{\text{in}}-\mu_{\text{out}})\Delta t
\]

Nếu queue nhận 600 event/giây nhưng consumer chỉ hoàn tất 550 event/giây, backlog tăng khoảng 50 event/giây, tương đương 180.000 event sau một giờ nếu mức chênh lệch được giữ đều và không có cơ chế loại bỏ khác.

Điều này giải thích vì sao **API response time tốt không bảo đảm hệ thống scale tốt**. Một API có thể trả 202 rất nhanh trong khi hàng đợi tích lũy nợ và người dùng chờ hàng giờ mới được xác nhận đơn. Khi đánh giá, cần SLO cho thời gian hoàn tất nghiệp vụ và giới hạn oldest-message age, không chỉ queue depth.

Queue buffering có thể hấp thụ spike ngắn nhưng không giải quyết tải cao liên tục khi capacity xử lý nhỏ hơn arrival rate. Giải pháp có thể là tăng/điều chỉnh worker, tối ưu xử lý, phân vùng hợp lý, backpressure, rate limit có thông báo rõ ràng hoặc điều chỉnh hành trình nghiệp vụ.

## 14. Phân tích nguyên nhân khi kết quả không đạt SLO

Một quy trình điều tra nên lần từ triệu chứng tới nguồn giới hạn:

~~~mermaid
flowchart TD
    A[Tải tăng, latency hoặc lỗi tăng] --> B{Generator đạt tải yêu cầu?}
    B -- Không --> C[Kiểm tra VU / CPU / mạng / dropped iterations]
    B -- Có --> D{Client đang bị từ chối?}
    D -- Có --> E[Gateway, rate limit, auth, quota, timeout]
    D -- Không --> F{CPU / memory app bão hòa?}
    F -- Có --> G[Profiling, GC, thread/worker pool, scale]
    F -- Không --> H{DB / cache / network / queue bão hòa?}
    H -- Có --> I[Query wait, pool, lock, IOPS, hit rate, backlog]
    H -- Không --> J[Trace hành trình và kiểm tra dependency bên ngoài]
    C --> K[Thay một biến, chạy lại và so sánh]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

Một số hướng xử lý theo bằng chứng:

| Bằng chứng | Giả thuyết cần kiểm chứng | Thay đổi có thể thử |
|---|---|---|
| App CPU cao, DB còn dư | Xử lý CPU-bound, serialization hoặc thuật toán kém | Profile CPU, giảm thao tác, scale app có kiểm soát |
| App CPU thấp, DB connection pool hết | Chờ DB hoặc giữ connection quá lâu | Tối ưu transaction/query, kích thước pool và giới hạn kết nối |
| p99 cao khi cache miss | Query chậm hoặc cache stampede | Tối ưu truy vấn, TTL jitter, request coalescing, kiểm tra hot key |
| Throughput chững khi tăng replica | DB, shared lock, gateway hoặc quota chung bão hòa | Đo resource chung, tối ưu/phân vùng hoặc tăng quota hợp lệ |
| HTTP ổn nhưng backlog tăng | Worker tiêu thụ kém hơn producer | Tối ưu consumer, thêm worker phù hợp và theo dõi lag |
| Spike tạo nhiều 429/503 | Rate limit, capacity warmup hoặc autoscaler chậm | Pre-scale, buffer, backpressure, chính sách từ chối có kiểm soát |
| Soak làm memory/connection tăng liên tục | Leak, cache không giới hạn hoặc cleanup không chạy | Heap/profile, kiểm soát lifetime, đóng connection và retry |

Sau khi sửa, kiểm chứng lại **cùng workload và cùng tiêu chí**, đồng thời đo chi phí và ảnh hưởng tới trụ cột khác. Tăng pool DB từ 50 lên 500 có thể giảm chờ tại app nhưng đẩy DB vào quá tải; một “tối ưu” cục bộ có thể làm kết quả toàn hệ thống xấu đi.

## 15. Chi phí, bảo mật và độ tin cậy trong quyết định mở rộng

### 15.1. Chi phí trên một đơn vị công việc thành công

Để so sánh cấu hình có ý nghĩa, dùng thước đo như:

\[
C_{\text{success}} =
\frac{\text{Chi phí liên quan trong cửa sổ quan sát}}
{\text{Số giao dịch nghiệp vụ thành công}}
\]

Chi phí liên quan có thể gồm compute, database, cache, network/egress, logging/tracing, queue, license và dịch vụ bên ngoài. Nếu so sánh giá theo 1.000 giao dịch, nhân kết quả với 1.000. Phải quy định phạm vi quy đổi và cách tính cho tài nguyên dùng chung.

Ví dụ hai cấu hình đều đạt 600 req/s nhưng một cấu hình cần gấp đôi số replica cùng chi phí trace lớn hơn, kiến trúc sư phải kiểm tra xem mức dự phòng, cô lập sự cố hoặc tốc độ phục hồi tăng thêm có đủ giá trị không. Không tối ưu chi phí bằng cách chấp nhận phá SLO.

### 15.2. Scale không loại bỏ nhu cầu dự phòng và cô lập sự cố

Kiểm tra năng lực khi một replica, một zone hoặc một phụ thuộc không sẵn sàng có thể khác đáng kể so với bài load test bình thường. Với kiến trúc cần chịu lỗi zone, capacity phải tính phần dự phòng phù hợp và kiểm tra cách phân phối lưu lượng sau sự cố. Không coi cấu hình “N replica khi tất cả khỏe mạnh” đương nhiên đủ cho tình huống thiếu một vùng sẵn sàng.

### 15.3. Lưu lượng kiểm thử phải đi qua các bảo vệ cần thiết

Auth, TLS, network policy, rate limiting, WAF và kiểm soát dữ liệu có thể ảnh hưởng latency và throughput. Nếu bài kiểm thử bỏ qua các tầng này, phải ghi rõ rằng kết quả **không đại diện trực tiếp** cho hành trình production. Đồng thời, thử nghiệm cần tránh tạo dữ liệu nhạy cảm hoặc vượt giới hạn bên thứ ba.

## 16. Liên hệ với sáu trụ cột Well-Architected

| Trụ cột | Câu hỏi khi xem kết quả thử nghiệm | Bằng chứng hoặc hành động |
|---|---|---|
| **Operational Excellence** | Có thể lặp lại bài test, so sánh kết quả và xử lý khi vi phạm SLO? | Runbook, dashboard, version, test report, ngưỡng dừng, owner |
| **Security** | Tăng tải có làm lộ điểm yếu của auth/rate limit, secret, WAF hoặc phân quyền? | Kiểm thử có kiểm soát qua đường bảo vệ, audit, quota |
| **Reliability** | Hệ thống có suy giảm có kiểm soát và phục hồi sau quá tải hoặc mất thành phần? | Error budget, timeout, retry, circuit breaker, backpressure, recovery time |
| **Performance Efficiency** | Phân phối tải, cache, database, compute và hàng đợi có sử dụng hiệu quả? | p95/p99, throughput thành công, saturation, profiling, scaling efficiency |
| **Cost Optimization** | Năng lực tăng có tương xứng tổng chi phí và lượng giao dịch thành công? | Cost per successful transaction, idle capacity, chi phí test và vận hành |
| **Sustainability** | Có cấp phát dư, xử lý lặp và truyền dữ liệu không cần thiết không? | Định cỡ, tránh retry bão, bỏ tài nguyên nhàn rỗi, hiệu quả theo khối lượng công việc |

Một kiến trúc được đánh giá là phù hợp khi **đáp ứng mục tiêu đã chọn và thể hiện các đánh đổi có căn cứ**. Không có cấu hình tối ưu tuyệt đối cho mọi nghiệp vụ. Ví dụ pre-scale trước flash sale có thể tăng chi phí nhưng giảm rủi ro chờ autoscaler và bảo vệ SLO ở giai đoạn doanh thu quan trọng.

## 17. Case study: đánh giá kiến trúc dịch vụ đặt hàng

### 17.1. Bối cảnh và giả thuyết

Nền tảng đặt hàng sử dụng:

- API gateway và 4 replica dịch vụ đặt hàng.
- Database quan hệ được quản lý và cache đọc.
- Queue đưa sự kiện sang worker thanh toán và cập nhật trạng thái.
- Autoscaling dựa trên CPU, giới hạn từ 4 đến 12 replica.

Yêu cầu nghiệp vụ dự báo 600 request/giây trong 2 giờ; trong đó khoảng 60 request/giây tạo đơn. Chủ sản phẩm yêu cầu checkout p95 dưới 800 ms, tỷ lệ tạo đơn thất bại dưới 0,5% và thời gian xác nhận thanh toán p95 dưới 10 giây.

Giả thuyết ban đầu: **4 replica đủ xử lý tải thông thường; autoscaling lên 12 replica sẽ đáp ứng 600 req/s**. Đây mới là giả thuyết, chưa phải kết luận kiến trúc.

### 17.2. Thiết kế thử nghiệm

1. Ghi baseline 100 req/s với workload mix và dataset đại diện.
2. Tăng 200, 400, 600 req/s, đo đạt tải, p95/p99, tỷ lệ lỗi, DB pool, cache hit, queue lag và autoscaler event.
3. Giữ tải đỉnh đủ lâu để quan sát ổn định; sau đó đo spike đột ngột.
4. Thử các cấu hình 4, 8, 12 replica ở cùng mức tải và giới hạn DB phù hợp.
5. Chạy soak ở tải nền dự kiến trong khoảng có bao phủ batch/rotation quan trọng.
6. Đối soát số lệnh tạo đơn, đơn lưu thành công, sự kiện thanh toán và tình trạng cuối.

### 17.3. Kết quả minh họa

| Quan sát giả định | Giải thích ban đầu | Kiểm tra tiếp |
|---|---|---|
| 400 req/s: checkout p95 520 ms, lỗi 0,1% | Đạt SLO ở mức này | Kiểm tra queue và độ ổn định |
| 600 req/s: checkout p95 1.100 ms, lỗi 1,8% | Không đạt SLO | Xem trace, DB pool, cache, throttle |
| Replica tăng từ 4 lên 10, throughput chỉ tăng nhẹ | Giới hạn có thể không ở CPU app | Đo DB wait, connection pool và query |
| DB active connection chạm mức cấu hình, chờ pool tăng | Database là ứng viên bottleneck | Tối ưu transaction/query trước khi tăng pool |
| Sau 6 giờ soak, queue oldest age tăng liên tục | Consumer không đủ capacity bền vững | Đo enqueue/dequeue rate, retry, worker lag |

**Không kết luận “chỉ cần thêm replica”.** Thử tối ưu query, giảm thời gian giữ connection, phân biệt read/write path và cải thiện năng lực consumer. Sau mỗi thay đổi, chạy lại workload 600 req/s và soak liên quan. Nếu sau chỉnh sửa checkout đạt p95 650 ms, lỗi 0,2%, queue ổn định và chi phí trong ngân sách thì mới có bằng chứng hỗ trợ thay đổi kiến trúc.

### 17.4. Quyết định nghiệm thu

Với kết quả minh họa ban đầu, trạng thái là **CHƯA ĐẠT** tại mức tải đỉnh, dù CPU app có thể chưa đạt 100%. Người ra quyết định cần một bảng vấn đề có owner, hành động, hạn giải quyết và phép đo kiểm chứng. Chỉ đổi sang **ĐẠT** khi có kết quả đủ cho các SLO và guardrail áp dụng trong thời gian dự kiến.

## 18. Mẫu kế hoạch và báo cáo đánh giá

Một hồ sơ kiểm thử có thể dùng cấu trúc sau để tái lập kết quả:

~~~yaml
assessment_id: architecture-load-001
system: order-platform
environment: performance
purpose: "Xác minh năng lực đỉnh và độ ổn định dài hạn"
owners:
  business: order-operations
  technical: platform-and-order-teams

workload:
  model: open-arrival-rate
  target_rps: 600
  test_mix:
    browse_percent: 50
    search_percent: 25
    cart_percent: 15
    checkout_percent: 10
  data_profile: "Tham chiếu mô tả dataset"
  scenario_duration: "Theo kế hoạch đã được phê duyệt"

slos:
  checkout_p95_ms_max: 800
  checkout_error_rate_max: 0.005
  payment_completion_p95_seconds_max: 10

environment_snapshot:
  app_version: "commit-or-release-id"
  app_replicas: 4
  database_size: "Tham chiếu cấu hình và volume dữ liệu"
  autoscaling: "min=4, max=12"
  known_differences_from_production: []

run_controls:
  authorized_scope: "Danh sách endpoint và service được phép"
  stop_conditions: "Ngưỡng lỗi, chi phí hoặc tác động đã duyệt"
  test_data_cleanup: "Quy trình và owner"

result:
  requested_rps: null
  achieved_rps: null
  successful_business_transactions: null
  error_rate: null
  latency_p95_ms: null
  backlog_trend: null
  limiting_resource: null
  cost_estimate: null
  verdict: PENDING

evidence:
  dashboards: []
  logs_and_traces: []
  test_tool_output: []
  deployment_snapshot: []
~~~

Các trường **PENDING/null** được để trống có chủ đích; không được thay chúng bằng số ước đoán rồi dùng làm bằng chứng. Link dashboard, trace, artifact của công cụ đo và ảnh chụp cấu hình cần được gắn đúng cửa sổ thử nghiệm.

Một bản tóm tắt gửi hội đồng kiến trúc nên trả lời được:

1. **Đã kiểm tra điều gì?** Cấu hình, mô hình tải, kịch bản, dữ liệu và phạm vi bao gồm/loại trừ.
2. **Yêu cầu là gì?** SLI, SLO, cửa sổ đánh giá, giới hạn chi phí và yêu cầu vận hành.
3. **Kết quả là gì?** Requested/achieved load, throughput thành công, latency, lỗi, backlog, tài nguyên, xu hướng theo thời gian.
4. **Giới hạn nằm ở đâu?** Bằng chứng metric/trace/quota và độ tin cậy của kết luận.
5. **Rủi ro còn lại?** Môi trường khác production, thiếu chu kỳ dài, test data chưa đủ lớn, phụ thuộc bị mock.
6. **Quyết định kế tiếp?** Đạt/không đạt, cải thiện gì, owner, thời hạn và phép thử xác minh lại.

## 19. Sai lầm thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ xem RPS cao nhất | Đánh giá nhầm năng lực khi nhiều request lỗi hoặc timeout | Đếm giao dịch thành công **trong SLO** |
| Chỉ thử một endpoint dễ cache | Không thấy bottleneck ở checkout, DB, queue | Dùng workload mix và hành trình nghiệp vụ |
| Dùng dữ liệu quá nhỏ hoặc lặp một ID | Cache hit và query plan không đại diện | Dataset đủ lớn, phân bố đầu vào và hot key thực tế |
| Dùng closed VU rồi cho rằng arrival rate ổn định | Tải tự giảm khi SUT chậm | Chọn workload model phù hợp, đo achieved rate |
| Không đo load generator | Kết luận nhầm SUT bão hòa | Theo dõi dropped iterations, CPU/network và phân tán nguồn tải khi cần |
| Lấy trung bình p95 các instance | Kết quả độ trễ toàn hệ thống không có ý nghĩa thống kê | Tổng hợp đúng phân phối/histogram |
| Thêm replica khi DB đang nghẽn | Tăng connection và chi phí, giảm ổn định | Trace và đo bottleneck trước khi scale |
| Chỉ nhìn HTTP 202, bỏ qua queue | Nợ xử lý tăng nhưng tưởng thành công | SLO cho nghiệp vụ cuối và oldest event age |
| Soak test quá ngắn hoặc không qua chu kỳ | Bỏ sót leak, rotation, batch cuối ngày | Thời lượng theo rủi ro và vòng đời tài nguyên |
| Test bỏ auth/TLS/WAF | Latency tốt giả tạo và thiếu tín hiệu bảo mật | Giữ đường bảo vệ phù hợp hoặc nêu rõ giới hạn |
| Thay nhiều yếu tố cùng lúc | Không phân biệt nguyên nhân cải thiện/xấu đi | Giữ baseline, thay một giả thuyết mỗi lần |
| Không xem chi phí/độ phục hồi | Cấu hình đạt RPS nhưng quá đắt hoặc mong manh | Đo cost per success, scale-in, failure/recovery |

## 20. Bài tập thực hành tự đánh giá

### Bài 1 — Tính tải và concurrency

Một API xử lý ổn định 250 request/giây, response time trung bình 400 ms. Hãy ước tính số request đang nằm trong phạm vi hệ thống đo. Sau đó giả sử độ trễ tăng lên 1.200 ms nhưng throughput vẫn giữ 250 request/giây. Điều gì xảy ra với nhu cầu concurrency?

**Đáp án gợi ý:** Theo Little's law, \(L \approx 250 \times 0{,}4 = 100\), tăng thành \(250 \times 1{,}2 = 300\). Nhu cầu request in-flight tăng gấp ba nếu điều kiện trạng thái ổn định và phạm vi đo không đổi. Connection, memory và thread/worker pool có thể trở thành giới hạn tiếp theo.

### Bài 2 — API nhanh nhưng người dùng vẫn đợi

Một dịch vụ tạo hóa đơn trả 202 trong 120 ms với 800 request/giây. Worker chỉ xử lý được 720 hóa đơn/giây. Sau 30 phút, backlog lý thuyết tăng bao nhiêu nếu tốc độ không đổi? Có đạt mục tiêu “hóa đơn hoàn tất trong 30 giây” không?

**Đáp án gợi ý:** Chênh lệch 80 việc/giây, tức khoảng \(80 \times 1.800 = 144.000\) việc tồn thêm. Không thể kết luận SLO 30 giây đạt; backlog tăng liên tục là tín hiệu rất mạnh rằng hệ thống không bền vững ở mức này. Cần xem thời gian xử lý của mỗi hóa đơn và lịch sử age của queue để định lượng vi phạm.

### Bài 3 — Đề xuất phương án scale

Một workload tăng từ 200 lên 700 req/s trong 20 giây. HPA cần 3 phút để tăng đủ replica. Database connection pool đang dùng 90%, checkout p95 vượt SLO trong 2 phút đầu. Hãy đề xuất thay đổi và phép kiểm chứng.

**Đáp án gợi ý:** Xem xét pre-scaling theo chiến dịch, min replica, thời gian startup, scale theo chỉ báo sớm; đồng thời xử lý thời gian giữ connection và năng lực DB. Thử spike cùng workload trước/sau, đo p95/p99, lỗi, thời gian ready, DB wait và backlog. Không chỉ tăng max replica khi DB đã gần bão hòa.

## 21. Checklist đánh giá trước khi phê duyệt kiến trúc

- [ ] Đã chuyển yêu cầu nghiệp vụ thành workload profile (giao dịch, tỷ lệ hành trình, RPS, đỉnh và thời gian kéo dài)?
- [ ] Đã định nghĩa SLI/SLO cho latency đầu-cuối, tỷ lệ thành công và luồng bất đồng bộ?
- [ ] Đã chọn open/closed workload model đúng mục đích, kiểm tra cả arrival rate mục tiêu và thực đạt?
- [ ] Môi trường, dataset, cache, auth, mạng, quota và phụ thuộc đủ đại diện; các khác biệt được ghi rõ?
- [ ] Có dashboard và evidence cho client, gateway, app, DB, cache, queue, autoscaler và giao dịch nghiệp vụ?
- [ ] Có baseline, peak load, stress, spike, scale-out/in, soak và recovery theo mức độ rủi ro phù hợp?
- [ ] Đã xác định **mức tải cao nhất được kiểm chứng đạt SLO**, không nhầm với đỉnh throughput thử được?
- [ ] Đã kiểm tra bottleneck thực trước khi tăng compute; biết các quota và giới hạn hạ nguồn?
- [ ] Soak test đủ bao phủ xu hướng tài nguyên, vòng đời token/connection/backup và xử lý queue?
- [ ] Có kết quả đối soát nghiệp vụ để phát hiện giao dịch mất, trùng hoặc xử lý trễ?
- [ ] Đã tính chi phí/năng lực và dự phòng cho tình huống tải đỉnh hoặc hỏng thành phần?
- [ ] Có điều kiện dừng, dữ liệu test an toàn, chủ sở hữu, hồ sơ run và phương án làm sạch/khôi phục?
- [ ] Đã ghi quyết định đạt/không đạt, giới hạn suy luận và nhiệm vụ kiểm chứng lại?

## 22. Kết luận

Kiểm thử tải trả lời liệu hệ thống có phục vụ được nhu cầu **ngay bây giờ**; soak test tìm xem khả năng ấy có **duy trì được theo thời gian**; kiểm tra giới hạn mở rộng cho biết **đến đâu, vì sao và với chi phí nào** có thể tăng năng lực. Ba loại bằng chứng phải được kết hợp với mô hình tải đại diện, SLO nghiệp vụ và telemetry xuyên suốt.

Trong đánh giá kiến trúc cloud theo nguyên tắc Well-Architected, mục tiêu không phải đạt một con số RPS thật lớn. Mục tiêu là **chứng minh một kiến trúc có đủ năng lực, ổn định, bảo mật, phục hồi được, có thể vận hành và có chi phí phù hợp** ở những tình huống doanh nghiệp thực sự cần.
