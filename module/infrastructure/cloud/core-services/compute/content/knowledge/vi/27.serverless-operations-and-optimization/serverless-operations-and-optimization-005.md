# Giới hạn mức đồng thời để bảo vệ hệ thống phía sau

Serverless có thể tạo thêm execution environment hoặc instance khi số yêu cầu tăng. Khả năng mở rộng nhanh giúp ứng dụng đáp ứng tải đột biến, nhưng cũng có thể đẩy quá nhiều yêu cầu cùng lúc đến database, API bên thứ ba, hệ thống thanh toán hoặc dịch vụ nội bộ. Những hệ thống phía sau thường có giới hạn kết nối, thông lượng và năng lực xử lý thấp hơn khả năng mở rộng của lớp serverless.

Giới hạn mức đồng thời (concurrency limit) đặt trần cho số lần thực thi hoặc yêu cầu đang xử lý cùng lúc. Khi chọn đúng giới hạn, ứng dụng tận dụng được khả năng mở rộng mà vẫn giữ tải trong phạm vi dependency có thể chịu được. Giới hạn quá cao có thể gây nghẽn dây chuyền; giới hạn quá thấp làm tăng thời gian chờ, hàng đợi và độ trễ dù hệ thống phía sau còn dư năng lực.

Sau bài học, bạn có thể:

- Phân biệt concurrency với tốc độ yêu cầu và số instance.
- Ước tính mức đồng thời an toàn dựa trên thời gian xử lý và giới hạn của dependency.
- Cấu hình giới hạn ở nền tảng serverless, API gateway và consumer của hàng đợi.
- Kiểm tra throttling, độ sâu hàng đợi, kết nối database và hành vi retry khi hệ thống quá tải.

## 1. Mức đồng thời là gì?

Concurrency là số công việc đang được xử lý tại cùng một thời điểm. Với một hàm serverless xử lý yêu cầu HTTP, một invocation đang chạy thường chiếm một đơn vị concurrency của hàm. Với nền tảng container serverless như Cloud Run, một instance có thể nhận nhiều yêu cầu đồng thời; khi đó concurrency của service phụ thuộc cả số instance và số yêu cầu tối đa trên mỗi instance.

Ba khái niệm cần tách biệt:

- **Concurrency:** số yêu cầu hoặc tác vụ đang chạy cùng lúc.
- **Request rate/throughput:** số yêu cầu được nhận hoặc hoàn tất trong một giây, thường đo bằng requests per second (RPS).
- **Instance count:** số execution environment hoặc instance đang tồn tại. Một instance có thể xử lý một hay nhiều yêu cầu đồng thời tùy runtime và cấu hình.

Concurrency và RPS liên quan với nhau nhưng không thể thay thế cho nhau. Theo định luật Little, trong trạng thái ổn định:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số yêu cầu trung bình đang ở trong hệ thống.
- `λ` là tốc độ yêu cầu trung bình, tính bằng yêu cầu/giây.
- `W` là thời gian trung bình một yêu cầu ở trong hệ thống, tính bằng giây.

Ví dụ, service nhận trung bình 100 yêu cầu/giây và mỗi yêu cầu mất 0,5 giây thì mức đồng thời trung bình xấp xỉ 50. Nếu thời gian xử lý tăng lên 2 giây trong khi RPS không đổi, concurrency trung bình tăng lên khoảng 200. Khi dependency chậm, yêu cầu nằm trong hệ thống lâu hơn và chiếm slot lâu hơn; đây là lý do một đợt chậm ở database có thể làm concurrency tăng mạnh.

Con số tính theo trung bình chỉ là điểm xuất phát. Khi thiết kế giới hạn, cần đo tải đỉnh, phân bố thời gian xử lý, burst, thời gian chờ ở pool kết nối và phần năng lực phải dành cho các ứng dụng khác. Không lấy một giá trị trung bình làm giới hạn production mà không thử tải.

## 2. Vì sao cần bảo vệ hệ thống phía sau?

Giả sử một hàm xử lý đơn hàng có thể mở rộng lên hàng trăm execution environment. Mỗi lần thực thi gọi database để đọc tồn kho, ghi đơn hàng và cập nhật trạng thái thanh toán. Database chỉ có một số lượng kết nối hữu hạn. Nếu mọi execution environment cùng mở kết nối, database có thể hết connection, tăng thời gian chờ, từ chối kết nối hoặc cạn CPU và I/O.

Một chuỗi sự cố thường diễn ra như sau:

1. Lưu lượng đầu vào tăng đột ngột.
2. Nền tảng serverless mở rộng số lần thực thi để xử lý yêu cầu.
3. Nhiều execution environment đồng thời gọi database hoặc API phía sau.
4. Dependency chạm giới hạn kết nối hoặc thông lượng, khiến thời gian phản hồi tăng.
5. Invocation giữ tài nguyên lâu hơn; số yêu cầu đang chạy tiếp tục tăng.
6. Timeout và retry tạo thêm tải, làm tình trạng quá tải kéo dài ngay cả khi đợt traffic ban đầu đã giảm.

Giới hạn concurrency giúp cắt chuỗi khuếch đại bằng cách giới hạn số công việc được phép đi sâu vào dependency. Phần tải vượt quá khả năng xử lý có thể bị throttling, được giữ trong hàng đợi hoặc bị từ chối có kiểm soát tùy kiến trúc.

Các dependency cần xem xét gồm database và connection pool, cache, hệ thống tìm kiếm, API đối tác, dịch vụ gửi email/SMS, hệ thống thanh toán, filesystem hoặc dịch vụ lưu trữ có giới hạn thông lượng. Mỗi dependency có thể cần một giới hạn riêng; một con số concurrency chung cho toàn ứng dụng có thể chưa đủ.

## 3. Ước tính giới hạn an toàn

Hãy bắt đầu từ năng lực của dependency yếu nhất trên đường xử lý. Với database, cần xem xét đồng thời số kết nối tối đa, số kết nối dành cho workload khác, kích thước pool của mỗi instance và số truy vấn mà database có thể xử lý ổn định.

Một cách tính giới hạn kết nối đơn giản:

\[
 C_{\text{app}} \leq \frac{D - R - H}{P}
\]

Trong đó:

- `D`: số kết nối tối đa database cho phép.
- `R`: số kết nối dự kiến dành cho ứng dụng hoặc tác vụ khác.
- `H`: phần dự phòng cho quản trị, migration và biến động.
- `P`: số kết nối tối đa mà mỗi execution environment hoặc instance có thể giữ.
- `C_app`: số execution environment tối đa có thể tồn tại mà không vượt ngân sách kết nối đã tính.

Ví dụ: database cho phép tối đa 120 kết nối. Dành 30 kết nối cho dịch vụ khác và tác vụ quản trị, giữ thêm 20 kết nối dự phòng. Ứng dụng serverless còn ngân sách 70 kết nối. Nếu mỗi execution environment chỉ giữ tối đa một kết nối, giới hạn lý thuyết là 70 environment. Nhóm có thể bắt đầu thử nghiệm ở mức 50 hoặc 60 để còn khoảng đệm. Nếu mỗi environment có pool tối đa hai kết nối, số environment tương ứng phải giảm còn tối đa 35 theo phép tính này.

Đối với nền tảng xử lý nhiều request trên một instance, cần tính cả concurrency và pool. Ví dụ, service có tối đa 10 instance, mỗi instance nhận tối đa 5 request đồng thời, nên tổng số request đồng thời do cấu hình này cho phép là 50. Nếu mỗi instance có pool database tối đa 4 kết nối, số kết nối tối đa theo pool là 40. Hai giới hạn kiểm soát hai tài nguyên khác nhau: concurrency kiểm soát công việc đang chạy, còn pool kiểm soát số kết nối mà instance có thể mở.

Có thể dùng định luật Little để kiểm tra thông lượng mục tiêu. Nếu hệ thống phía sau xử lý ổn định 80 yêu cầu/giây và thời gian xử lý trung bình là 0,25 giây, concurrency trung bình tương ứng khoảng 20. Nhưng nếu có burst hoặc thời gian xử lý tăng, mức đồng thời cần thiết sẽ cao hơn. Hãy xác định rõ mục tiêu: giới hạn để bảo vệ dependency, mục tiêu độ trễ và mức throughput cần duy trì. Nếu ba mục tiêu không thể đồng thời đạt được, cần tăng năng lực dependency, giảm công việc mỗi yêu cầu hoặc điều chỉnh SLA.

Quy trình thực tế:

1. Đo tải nền, tải đỉnh, burst và thời gian xử lý của từng dependency.
2. Xác định quota, connection limit, throughput và giới hạn rate của từng dependency.
3. Tính ngân sách kết nối và concurrency, tính cả các ứng dụng khác dùng chung dependency.
4. Chọn giá trị ban đầu thấp hơn giới hạn lý thuyết để có headroom.
5. Chạy thử tải tăng dần, theo dõi độ trễ, lỗi, connection pool và CPU/I/O của dependency.
6. Điều chỉnh giới hạn đến khi đạt thông lượng mục tiêu mà dependency vẫn ổn định.

## 4. Đặt giới hạn ở những lớp nào?

Một hệ thống có thể áp dụng nhiều lớp kiểm soát. Mỗi lớp bảo vệ một ranh giới khác nhau:

| Lớp | Cơ chế | Mục đích |
|---|---|---|
| API gateway/ingress | Rate limit, burst limit, quota theo client hoặc tenant | Chặn lưu lượng quá nhanh trước khi kích hoạt function |
| Function/service | Reserved concurrency, maximum instances, concurrency per instance | Giới hạn số lần thực thi hoặc request đi vào workload |
| Application | Semaphore, giới hạn worker, connection pool | Giới hạn số thao tác đồng thời gọi một dependency cụ thể |
| Queue consumer | Maximum concurrency, số consumer hoặc batch size | Điều tiết tốc độ lấy thông điệp và làm phẳng burst |
| Dependency | Connection limit, query limit, quota, rate limit | Bảo vệ tài nguyên tại chính hệ thống nhận tải |

Nên đặt giới hạn gần nơi có thể đo và kiểm soát tài nguyên. Ví dụ, một function gọi hai dependency có năng lực khác nhau có thể cần semaphore riêng cho từng dependency. Giới hạn concurrency toàn function vẫn hữu ích để kiểm soát tổng số invocation, nhưng không thay thế giới hạn cho từng pool hoặc API đối tác.

### Phân biệt concurrency limit và rate limit

Concurrency limit giới hạn số yêu cầu đang chạy cùng lúc. Rate limit giới hạn số yêu cầu được chấp nhận trong một khoảng thời gian. Một service cho phép 20 yêu cầu đồng thời nhưng mỗi yêu cầu chỉ mất 0,1 giây có thể xử lý khoảng 200 RPS trong điều kiện ổn định. Nếu mỗi yêu cầu mất 2 giây, throughput tương ứng chỉ khoảng 10 RPS. Vì vậy, concurrency cap không tự bảo đảm giới hạn RPS.

Nếu đối tác chỉ cho phép 50 request/giây, cần rate limiter hoặc token bucket ở lớp gọi đối tác, kể cả khi concurrency của function đã được giới hạn. Ngược lại, rate limit theo phút có thể vẫn cho phép một burst lớn trong vài mili giây; concurrency cap giúp giới hạn số công việc đang chiếm tài nguyên tại cùng thời điểm.

## 5. Ví dụ cấu hình trên các nền tảng serverless

Tên gọi và phạm vi cấu hình khác nhau theo nhà cung cấp. Cần đọc giới hạn quota của tài khoản, vùng và runtime đang dùng trước khi triển khai.

### AWS Lambda

Với Lambda, reserved concurrency đặt mức concurrency tối đa cho một function và đồng thời dành riêng phần concurrency đó cho function trong tài khoản. Đây là cơ chế hữu ích để bảo vệ database: nếu function được đặt reserved concurrency là 40, function không mở rộng vượt quá 40 invocation đồng thời. Khi nhu cầu vượt mức này, invocation có thể bị throttling hoặc được xử lý theo cơ chế retry/queue của nguồn sự kiện.

Ví dụ đặt reserved concurrency bằng AWS CLI:

```bash
aws lambda put-function-concurrency \
  --function-name orders-handler \
  --reserved-concurrent-executions 40
```

Với Lambda nhận sự kiện từ Amazon SQS, event source mapping có thể đặt maximum concurrency để giới hạn mức song song mà poller sử dụng cho queue đó. Nếu một function có nhiều event source mapping, cần kiểm tra tổng các mức maximum concurrency so với reserved concurrency của function. Nếu tổng mức cho phép của các nguồn sự kiện cao hơn reserved concurrency, chúng có thể cạnh tranh và gây throttling ở cấp function.

API Gateway có thể đặt throttling ở stage hoặc method để kiểm soát tốc độ và burst trước khi yêu cầu đến Lambda. Provisioned concurrency giữ sẵn execution environment đã khởi tạo để giảm cold start; nó không phải cơ chế bảo vệ database. Hãy phân biệt provisioned concurrency với reserved concurrency: một cơ chế chuẩn bị môi trường sẵn sàng, cơ chế còn lại giới hạn và dành phần concurrency cho function.

### Google Cloud Run

Cloud Run có hai thông số cần phối hợp:

- **Concurrency per instance:** số request tối đa một instance nhận đồng thời.
- **Maximum instances:** số instance tối đa service được phép tạo.

Ví dụ đặt concurrency bằng 5 và maximum instances bằng 10 sẽ giới hạn lý thuyết ở khoảng 50 request đồng thời trên toàn service. Nếu ứng dụng dùng pool database 4 kết nối cho mỗi instance, pool có thể mở tối đa khoảng 40 kết nối khi tất cả instance hoạt động. Cần kiểm tra giới hạn pool thực tế và các client khác cùng dùng database.

Đặt concurrency quá cao có thể làm CPU hoặc bộ nhớ của một instance bị tranh chấp, khiến thời gian phản hồi tăng. Đặt maximum instances quá cao có thể làm database quá tải khi service scale out. Hãy chọn cả hai dựa trên thử nghiệm tải và cấu hình pool, sau đó kiểm tra quota và giới hạn theo vùng.

### Azure Functions

Azure Functions có cơ chế giới hạn scale-out theo plan và cấu hình host/trigger. Với trigger xử lý thông điệp, các thiết lập concurrency của extension có thể giới hạn số message được xử lý song song trên một host; giới hạn số instance kiểm soát mức scale-out tổng thể. Tên setting và phạm vi áp dụng phụ thuộc trigger, extension và hosting plan.

Ví dụ, với Azure Service Bus trigger, `maxConcurrentCalls` trong cấu hình extension điều khiển số message đồng thời mà một instance xử lý cho một function. Giới hạn này cần được xem cùng số instance tối đa và năng lực database phía sau. Không nên giả định một setting trong `host.json` áp dụng giống nhau cho mọi trigger hoặc mọi plan; hãy kiểm tra tài liệu của extension đang sử dụng và xác nhận bằng metric khi chạy thử.

## 6. Dùng hàng đợi để hấp thụ burst

Nếu hệ thống phía sau không thể xử lý ngay toàn bộ tải đến, hàng đợi giúp tách tốc độ nhận yêu cầu khỏi tốc độ xử lý. API có thể xác thực và ghi một thông điệp vào queue rồi trả phản hồi chấp nhận; một nhóm serverless consumer đọc thông điệp với maximum concurrency đã giới hạn.

Ví dụ, một chiến dịch bán hàng tạo ra 2.000 yêu cầu đặt hàng trong thời gian ngắn, trong khi database chỉ xử lý an toàn 100 tác vụ ghi mỗi giây. API có thể đưa công việc vào queue. Consumer được giới hạn để xử lý gần năng lực database. Hàng đợi hấp thụ phần tải vượt công suất tạm thời; backlog sẽ giảm khi tốc độ xử lý lớn hơn tốc độ thông điệp mới đi vào.

Hàng đợi không tạo thêm năng lực xử lý. Nếu tốc độ đến luôn cao hơn tốc độ xử lý, backlog và tuổi thông điệp sẽ tăng liên tục. Cần theo dõi queue depth, oldest message age và thời gian hoàn tất; khi vượt ngưỡng, có thể giảm tải đầu vào, tăng năng lực dependency nếu còn dư địa hoặc thông báo tình trạng chậm cho client.

Với consumer bất đồng bộ, cần thiết kế thêm:

- Xử lý idempotent để một thông điệp được giao lại không tạo giao dịch trùng.
- Visibility timeout hoặc lock duration đủ dài cho thời gian xử lý dự kiến.
- Retry có giới hạn và dead-letter queue cho thông điệp lỗi kéo dài.
- Batch size phù hợp để một lần gọi không tạo quá nhiều thao tác song song.
- Cơ chế xác nhận thông điệp chỉ sau khi xử lý thành công theo semantics của queue.

## 7. Backpressure, timeout và retry

Khi đạt giới hạn concurrency, hệ thống phải có cách phản hồi rõ ràng. Với request đồng bộ, có thể trả `429 Too Many Requests` khi client vượt quota hoặc `503 Service Unavailable` khi service tạm thời không thể nhận thêm tải. Nếu phù hợp, trả `Retry-After` để hướng dẫn client chờ trước khi thử lại. Không nên nhận yêu cầu rồi để chúng chờ vô hạn trong bộ nhớ.

Với công việc có thể xử lý bất đồng bộ, hãy đưa vào queue và kiểm soát tốc độ consumer. Đây là backpressure: tốc độ xử lý được điều chỉnh theo khả năng thực tế của dependency. Ở lớp ứng dụng, semaphore hoặc bounded worker pool giúp giới hạn thao tác đồng thời đến từng dependency; bounded queue trong process cần có giới hạn dung lượng để tránh tăng bộ nhớ vô hạn.

Retry có thể giúp vượt qua lỗi tạm thời, nhưng retry ngay lập tức và không giới hạn sẽ khuếch đại tải. Hãy áp dụng exponential backoff có jitter, số lần thử tối đa và deadline tổng thể. Chỉ retry các lỗi có khả năng hồi phục; tôn trọng `Retry-After` khi nhận 429 hoặc 503. Với thao tác ghi, dùng idempotency key hoặc cơ chế chống xử lý trùng. Khi hết số lần thử, đưa thông điệp vào dead-letter queue hoặc ghi nhận để xử lý thủ công.

Timeout cũng cần phối hợp với concurrency. Timeout quá dài giữ slot và connection trong lúc dependency đã không thể phản hồi; timeout quá ngắn tạo retry dù dependency vẫn có thể hoàn thành. Đặt timeout của từng lời gọi nhỏ hơn deadline tổng của invocation, giải phóng connection khi timeout và tránh retry đồng thời ở nhiều tầng mà không có ngân sách retry chung.

## 8. Ví dụ thiết kế giới hạn cho API đặt hàng

Giả sử `orders-api` chạy trên một nền tảng function serverless. Mỗi invocation đọc tồn kho và ghi đơn hàng vào database. Database cho phép 120 kết nối; 30 kết nối dành cho dịch vụ khác và 20 kết nối dự phòng. Như vậy, ứng dụng có ngân sách 70 kết nối. Nhóm quyết định mỗi execution environment chỉ giữ tối đa một kết nối và đặt giới hạn concurrency ban đầu là 50.

Luồng xử lý được thiết kế như sau:

1. API gateway giới hạn tốc độ theo client và giới hạn burst để bảo vệ điểm vào.
2. Function có concurrency cap 50 để giới hạn số invocation đồng thời.
3. Connection pool mỗi execution environment có giới hạn 1 kết nối và thời gian chờ lấy connection hữu hạn.
4. Công việc ghi đơn hàng có thể chuyển sang queue khi cần xử lý bất đồng bộ; consumer có maximum concurrency riêng.
5. Khi database chậm, function áp dụng timeout, không retry dồn dập và trả trạng thái phù hợp hoặc để queue tiếp tục xử lý theo chính sách.
6. Dashboard theo dõi concurrency, throttles, duration, lỗi, connection đang dùng, pool wait time và độ sâu hàng đợi.

Giới hạn 50 là giá trị khởi đầu cho thử nghiệm, không phải cam kết database luôn xử lý được 50 giao dịch đồng thời. Một invocation có thể chạy nhiều truy vấn, truy vấn có thể giữ connection lâu hoặc các workload khác có thể dùng chung database. Nhóm phải tăng tải theo từng bước và điều chỉnh dựa trên kết quả đo.

## 9. Kiểm chứng giới hạn trong thực tế

Trước khi phát hành, hãy thực hiện kiểm thử theo các pha:

1. **Baseline:** chạy tải thấp để đo latency, throughput, connection count, CPU, bộ nhớ và thời gian chờ pool khi dependency khỏe.
2. **Ramp-up:** tăng dần số client hoặc tốc độ gửi yêu cầu; xác nhận concurrency không vượt cap và dependency không vượt ngân sách.
3. **Burst:** gửi một đợt yêu cầu ngắn cao hơn năng lực xử lý; xác nhận gateway throttling, queue buffering hoặc phản hồi overload diễn ra đúng thiết kế.
4. **Dependency slowdown:** mô phỏng database/API phía sau phản hồi chậm hoặc trả 429/503; kiểm tra timeout, backpressure và retry có giới hạn.
5. **Recovery:** khôi phục dependency và xác nhận backlog giảm, lỗi giảm, hệ thống không tạo retry storm.
6. **Fairness:** nếu có nhiều tenant hoặc nguồn sự kiện, xác nhận một client không chiếm toàn bộ concurrency và làm nghẽn các client còn lại.

Các metric nên quan sát:

| Nhóm | Metric cần theo dõi | Dấu hiệu cần điều tra |
|---|---|---|
| Serverless | Concurrent executions/requests, active instances, throttles, duration, errors | Concurrency chạm trần kéo dài, throttles tăng, duration tăng bất thường |
| API gateway | Request rate, burst, 429, 5xx, latency | Burst vượt quota, lỗi tăng trước khi vào function |
| Database | Active/max connections, CPU, I/O, lock wait, query latency | Connection gần cạn, query chậm, lock wait tăng |
| Connection pool | Active/idle connections, pending acquisition, wait time, timeout | Nhiều invocation chờ lấy connection dù database chưa đạt giới hạn |
| Queue | Visible messages, oldest message age, receive count, dead-letter count | Backlog hoặc tuổi thông điệp tăng liên tục |
| Retry | Attempt count, retry rate, timeout, 429/503 từ dependency | Số lần thử tăng nhanh hơn số tác vụ hoàn tất |

Tạo cảnh báo cho concurrency chạm ngưỡng trong một khoảng thời gian, throttles tăng đột biến, connection gần giới hạn, pool wait time cao, queue age vượt SLA và dead-letter tăng. Đặt ngưỡng cảnh báo theo baseline của workload thay vì chỉ dùng một giá trị chung.

## Checklist cấu hình an toàn

- [ ] Đã phân biệt concurrency, RPS và số instance trong thiết kế.
- [ ] Đã xác định dependency giới hạn nhất và quota thực tế của nó.
- [ ] Đã tính phần kết nối dành cho workload khác, phần dự phòng và kích thước pool mỗi instance.
- [ ] Đã đặt concurrency cap hoặc maximum instances ở nền tảng serverless.
- [ ] Đã đặt rate limit/burst limit ở gateway khi dependency có giới hạn RPS.
- [ ] Đã giới hạn pool, semaphore hoặc worker song song ở cấp ứng dụng.
- [ ] Đã đặt maximum concurrency và chính sách backlog cho queue consumer.
- [ ] Đã cấu hình timeout, retry có backoff/jitter, idempotency và dead-letter handling.
- [ ] Đã kiểm thử ramp-up, burst, dependency slowdown và recovery.
- [ ] Đã có dashboard và cảnh báo cho throttles, connection, pool wait, queue age và retry.

Giới hạn concurrency là một phần của thiết kế năng lực và khả năng chịu lỗi. Hãy đặt giới hạn theo sức chịu tải đã đo của dependency, kết hợp rate limit và backpressure ở đúng lớp, rồi xác minh bằng kiểm thử tải. Khi năng lực phía sau thay đổi, cần đo lại và điều chỉnh giới hạn cùng các cảnh báo liên quan.
