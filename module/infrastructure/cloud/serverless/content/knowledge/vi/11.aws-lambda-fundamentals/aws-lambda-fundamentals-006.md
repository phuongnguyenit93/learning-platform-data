# Reserved concurrency và provisioned concurrency trên Lambda

AWS Lambda tự điều chỉnh số execution environment theo lượng invocation, nhưng hai câu hỏi vận hành thường xuất hiện khi đưa function vào production: làm sao bảo đảm một function còn phần concurrency để phục vụ workload quan trọng, và làm sao giảm độ trễ khởi tạo khi request đến? Lambda cung cấp hai cơ chế có tên gần giống nhau nhưng giải quyết hai vấn đề khác nhau: **reserved concurrency** và **provisioned concurrency**.

Reserved concurrency dành một phần concurrency của account cho một function và đồng thời đặt giới hạn concurrency tối đa của function đó. Provisioned concurrency chuẩn bị sẵn một số execution environment đã khởi tạo để function có thể phục vụ request nhanh hơn. Có thể dùng từng cơ chế riêng hoặc kết hợp, nhưng phải hiểu cách chúng tương tác với quota account, alias/version, scaling và chi phí.

Trong module **CLOUD_SERVERLESS**, người học triển khai Java function qua HTTP, message hoặc event và cần kiểm soát cold start, mở rộng, quyền truy cập, retry cùng chi phí. Bài này tập trung vào hai cấu hình concurrency của AWS Lambda, cách chọn giá trị và cách theo dõi chúng trong production.

## 1. Concurrency trong AWS Lambda là gì?

Concurrency là số invocation đang được xử lý đồng thời. Mỗi invocation đang chạy cần một phần năng lực thực thi của Lambda. Với một function đồng bộ, nếu một request mất trung bình 200 ms và có 50 request mỗi giây, số invocation đồng thời trung bình xấp xỉ:

\[
Concurrency = RequestsPerSecond \times AverageDurationSeconds
\]

Ví dụ:

\[
50 \times 0.2 = 10
\]

Function cần khoảng 10 concurrency ở mức tải đó. Đây là ước lượng dựa trên lưu lượng và thời gian xử lý trung bình; khi lập kế hoạch production cần thêm headroom cho burst, biến động latency, retry và các phân vị tải cao.

Lambda tạo hoặc tái sử dụng execution environment để xử lý invocation. Một environment chỉ xử lý một invocation tại một thời điểm theo mô hình Lambda thông thường; khi nhiều invocation đến đồng thời, Lambda cần nhiều environment. Nếu function nhận tải cao hơn năng lực concurrency hiện có, invocation có thể bị throttling hoặc phải chờ/retry tùy loại trigger và cơ chế gọi.

Concurrency của một function bị ảnh hưởng bởi nhiều giới hạn:

- **Account concurrency quota:** tổng concurrency khả dụng cho các function trong một AWS account và Region.
- **Reserved concurrency của function:** phần capacity dành riêng cho function và cũng là mức trần concurrency của function.
- **Provisioned concurrency:** số environment đã được khởi tạo trước cho một version hoặc alias; request vượt số này có thể dùng capacity on-demand nếu còn khả dụng.
- **Giới hạn của trigger và dependency:** API Gateway, event source mapping, queue, database hoặc dịch vụ downstream có thể có quota riêng.

## 2. Reserved concurrency: dành capacity và đặt giới hạn tối đa

Reserved concurrency là số concurrency được dành riêng cho một Lambda function từ account concurrency pool. Khi đặt giá trị này, Lambda bảo đảm function có thể sử dụng phần capacity đã dành trong phạm vi quota và giới hạn dịch vụ, đồng thời không cho function vượt quá con số đó.

Ví dụ, đặt reserved concurrency của orders-api là 120:

- Tối đa 120 invocation của function có thể chạy đồng thời.
- Phần concurrency này không bị các function khác sử dụng.
- Các function khác không có reserved concurrency dùng phần pool còn lại.
- Nếu orders-api nhận invocation vượt quá 120 đồng thời, phần vượt sẽ bị throttling.

Reserved concurrency có hai tác dụng đồng thời:

1. **Capacity reservation:** bảo vệ một phần concurrency cho workload quan trọng, tránh function khác trong cùng account chiếm hết capacity.
2. **Concurrency cap:** giới hạn mức song song tối đa để bảo vệ downstream như database, payment provider hoặc API đối tác.

Reserved concurrency không tạo sẵn execution environment. Function vẫn có thể cold start khi cần environment mới. Cơ chế này cũng không làm request nhanh hơn và không tính phí riêng chỉ vì cấu hình reserved concurrency; chi phí invocation và duration vẫn được tính theo cách Lambda áp dụng.

### Reserved concurrency bằng 0

Đặt reserved concurrency bằng 0 sẽ giới hạn function ở mức không nhận invocation mới theo cơ chế thực thi bình thường, khiến Lambda throttling các invocation được gửi đến function. Đây là cách khẩn cấp để tạm dừng một function khi cần ngăn side effect hoặc bảo vệ hệ thống downstream. Cần nhớ rằng producer/trigger có thể tiếp tục gửi hoặc retry event; việc đặt về 0 không tự xử lý backlog và có thể làm tăng tuổi message hoặc số lần retry.

### Tác động lên account concurrency pool

Tổng reserved concurrency của các function lấy capacity khỏi pool dùng chung. Nếu dành quá nhiều cho những function ít sử dụng, các function khác có thể thiếu capacity dù tổng nhu cầu thực tế của account không cao. AWS cũng yêu cầu duy trì một phần concurrency cho các function không được reserve theo quy tắc quota hiện hành; kiểm tra quota của Region và account trước khi phân bổ.

Reserved concurrency là công cụ phân bổ capacity ở cấp function, không phải cách tăng account quota. Nếu tổng nhu cầu thực tế vượt quota, cần tối ưu workload hoặc gửi yêu cầu tăng quota theo quy trình AWS.

## 3. Provisioned concurrency: chuẩn bị sẵn execution environment

Provisioned concurrency cấu hình trước một số execution environment cho một Lambda version hoặc alias. Lambda khởi tạo các environment này trước khi nhận request và giữ chúng sẵn sàng trong thời gian cấu hình còn hiệu lực. Với Java, bước initialization có thể bao gồm khởi động runtime, nạp class, chạy static initializer và khởi tạo framework/dependency theo lifecycle của Lambda.

Nếu một alias có provisioned concurrency bằng 50, Lambda chuẩn bị 50 environment đã khởi tạo cho version mà alias trỏ tới. Khi tối đa 50 invocation đồng thời đi vào đúng alias/version đó, chúng có thể được xử lý bằng capacity đã chuẩn bị, giúp giảm cold start do khởi tạo environment.

Provisioned concurrency hữu ích khi:

- HTTP API có mục tiêu latency chặt, đặc biệt ở p95/p99.
- Workload có thời điểm cao điểm dự đoán được như đầu giờ làm việc, đợt mở bán hoặc chiến dịch.
- Java function có startup tương đối dài do framework hoặc dependency.
- Request đầu tiên sau thời gian nhàn rỗi cần phản hồi nhanh.

Provisioned concurrency không làm function vô hạn capacity và không loại bỏ mọi nguyên nhân latency. Nó không tăng tốc logic nghiệp vụ, truy vấn database hoặc network call trong handler. Nếu request đồng thời vượt số environment provisioned, Lambda có thể phục vụ phần vượt bằng on-demand concurrency nếu capacity và quota cho phép; các invocation spillover đó vẫn có thể gặp cold start.

Provisioned concurrency được thiết kế cho đường gọi đồng bộ. Với lời gọi bất đồng bộ do Lambda quản lý hàng đợi hoặc dịch vụ tích hợp gửi event, không giả định cấu hình này sẽ giữ sẵn environment cho mọi loại trigger; hãy kiểm tra ma trận hỗ trợ và semantics invocation của integration cụ thể. Event source mapping vẫn có cơ chế scaling, batch và giới hạn concurrency riêng.

### Provisioned concurrency phải gắn với version hoặc alias

Provisioned concurrency không được cấu hình trực tiếp trên $LATEST. Hãy publish một version bất biến rồi gắn provisioned concurrency vào version hoặc alias trỏ đến version đó. Trong production, alias như prod thường thuận tiện hơn vì deployment có thể cập nhật alias sang version mới.

Điều quan trọng là **traffic phải gọi đúng qualified ARN** của alias hoặc version đã cấu hình provisioned concurrency. Nếu API Gateway, Function URL, event source hoặc client gọi unqualified function ARN hay $LATEST, request có thể không sử dụng capacity provisioned như mong đợi.

Trước khi chuyển traffic sang alias/version mới, chờ trạng thái provisioned concurrency là READY. Trong khi cấu hình đang IN_PROGRESS, chưa nên giả định toàn bộ capacity đã sẵn sàng. Nếu initialization thất bại, kiểm tra trạng thái và lý do lỗi trước khi chuyển traffic.

## 4. So sánh trực tiếp hai cơ chế

| Tiêu chí | Reserved concurrency | Provisioned concurrency |
|---|---|---|
| Mục tiêu | Dành capacity cho function và đặt mức concurrency tối đa | Chuẩn bị trước environment đã khởi tạo để giảm cold start |
| Đơn vị cấu hình | Lambda function | Published version hoặc alias |
| Tạo environment trước? | Không | Có |
| Giới hạn concurrency tối đa? | Có, bằng giá trị reserved | Không tự đặt trần tổng concurrency của function |
| Request vượt cấu hình | Vượt reserved sẽ bị throttling | Vượt provisioned có thể spill sang on-demand nếu còn capacity |
| Bảo vệ downstream | Có thể giới hạn mức song song tối đa | Không thay thế concurrency cap; cần reserved concurrency hoặc giới hạn khác nếu muốn bảo vệ downstream |
| Giảm cold start | Không | Có, trong phạm vi capacity đã provisioned và traffic đi đúng alias/version |
| Chi phí cấu hình riêng | Không có phí riêng cho reservation | Có phí cho capacity provisioned theo thời gian, ngoài phí invocation thông thường |
| Khi phù hợp | Function quan trọng cần capacity hoặc cần giới hạn tải | Function nhạy latency và có tải dự đoán được hoặc cần environment luôn sẵn sàng |

Hai cơ chế bổ sung cho nhau. Reserved concurrency trả lời “function được chạy tối đa bao nhiêu invocation đồng thời và có capacity dành riêng không?”. Provisioned concurrency trả lời “trong số capacity có thể dùng, bao nhiêu environment được khởi tạo trước?”.

## 5. Cách hai cơ chế tương tác

Khi một function có cả reserved concurrency và provisioned concurrency, provisioned concurrency phải nằm trong giới hạn reserved concurrency đã cấp. Reserved concurrency là mức trần; provisioned concurrency là phần capacity đã chuẩn bị sẵn bên trong mức trần đó.

Ví dụ:

~~~text
Reserved concurrency = 120
+-------------------------------------------------------+
| 50 provisioned environments | 70 capacity chưa warm  |
+-------------------------------------------------------+
Tổng concurrency tối đa của function = 120
~~~

Trong ví dụ này:

- 50 invocation đầu tiên có thể sử dụng provisioned environments đã sẵn sàng.
- Khi concurrency vượt 50, phần invocation vượt provisioned có thể dùng on-demand capacity.
- Tổng concurrency của function vẫn không vượt 120.
- Nếu concurrency vượt 120, phần vượt bị throttling.

Phần 70 còn lại không phải 70 environment luôn chạy sẵn. Lambda chỉ tạo environment on-demand khi cần và có thể phát sinh cold start. Nếu không đặt reserved concurrency, provisioned concurrency vẫn tiêu thụ capacity từ account pool; cần tính cả capacity này và nhu cầu spillover trong kế hoạch quota.

## 6. Ví dụ chọn cấu hình cho Java HTTP API

Giả sử một API xử lý đơn hàng có tải giờ cao điểm khoảng 160 request/giây. Thời gian xử lý trung bình là 250 ms:

\[
160 \times 0.25 = 40
\]

Concurrency trung bình ước tính khoảng 40. Nếu muốn dự phòng cho biến động tải và latency, nhóm có thể thử provisioned concurrency 60 hoặc 70, sau đó đo thực tế. Giả sử nhóm đặt:

- Reserved concurrency: 100 để giới hạn mức song song và bảo vệ database.
- Provisioned concurrency: 60 để giữ sẵn 60 environment trong giờ cao điểm.
- Alias: prod trỏ đến version đã publish và được cấu hình provisioned concurrency.

Với cấu hình đó, function có tối đa 100 invocation đồng thời. 60 environment được chuẩn bị trước; tối đa 40 invocation vượt phần provisioned có thể dùng capacity on-demand trong reserved limit. Nếu database chỉ chịu được 80 request đồng thời, reserved concurrency 100 có thể vẫn quá cao; cần tính giới hạn downstream và connection pool thay vì chỉ dựa trên năng lực Lambda.

Ví dụ này là điểm bắt đầu cho thử nghiệm. Không lấy RPS nhân với thời gian trung bình làm giá trị provisioned cuối cùng mà không đo burst, p95/p99 duration, batch behavior, retry và khả năng chịu tải của dependency.

## 7. Ước lượng concurrency và đặt headroom

### Công thức cơ bản

Với workload HTTP đồng bộ:

\[
RequiredConcurrency \approx PeakRPS \times AverageDurationSeconds
\]

Ví dụ, 80 request/giây với duration trung bình 0,4 giây cần khoảng 32 concurrency. Nếu duration tăng lên 0,8 giây do database chậm, cùng lưu lượng sẽ cần khoảng 64 concurrency. Vì vậy, memory/CPU, GC và latency của dependency cũng tác động đến nhu cầu concurrency.

### Không chỉ dùng average

Average giúp ước lượng tổng quan, nhưng API production cần xem:

- Peak RPS theo cửa sổ ngắn, không chỉ trung bình cả ngày.
- p50, p95 và p99 duration.
- Burst traffic khi nhiều client đồng thời retry hoặc mở phiên.
- Thời gian function chờ dependency, vì invocation vẫn chiếm concurrency trong lúc chờ.
- Batch size và concurrency của event source mapping đối với queue/stream.
- Số invocation phát sinh từ retry, duplicate delivery hoặc workflow fan-out.

### Chọn reserved concurrency

Reserved concurrency nên được xác định từ hai giới hạn: capacity cần bảo đảm cho workload và mức tải tối đa mà dependency có thể chịu. Nếu database có connection limit nhỏ, có thể đặt reserved concurrency thấp hơn năng lực tối đa lý thuyết của Lambda. Nếu function cần ưu tiên capacity, dành phần đủ lớn nhưng vẫn để account pool cho các function khác.

### Chọn provisioned concurrency

Provisioned concurrency nên dựa trên concurrency ở giờ cao điểm hoặc mức tải mà SLA yêu cầu không bị cold start. Có thể bắt đầu với p95 concurrency trong khung giờ mục tiêu cộng headroom, sau đó điều chỉnh từ metric spillover và utilization. Nếu chỉ cần giảm cold start cho một phần traffic quan trọng, không nhất thiết phải provision toàn bộ reserved concurrency.

## 8. Autoscaling provisioned concurrency

Provisioned concurrency có thể được điều chỉnh thủ công, theo lịch hoặc tự động bằng Application Auto Scaling. Với tải có lịch rõ ràng, scheduled scaling có thể tăng capacity trước giờ cao điểm và giảm sau khi kết thúc. Với tải biến động, target tracking có thể dùng metric LambdaProvisionedConcurrencyUtilization để điều chỉnh số environment provisioned.

### Scheduled scaling

Ví dụ một API bán vé thường có lượng truy cập tăng lúc 08:00. Có thể lên lịch tăng provisioned concurrency trước thời điểm đó, chẳng hạn 07:45, để Lambda có thời gian chuẩn bị environment. Sau khi đợt cao điểm kết thúc, giảm về mức nền.

Không nên đặt lịch đúng thời điểm traffic tăng nếu initialization cần thời gian. Hãy quan sát thời gian chuyển trạng thái sang READY và đặt lịch sớm hơn. Lịch nên tính theo timezone và ngày nghỉ/chiến dịch thực tế; lịch AWS thường cần khai báo timezone hoặc dùng UTC rõ ràng.

### Target tracking

Application Auto Scaling có thể theo dõi tỷ lệ sử dụng provisioned concurrency. Khi utilization tăng, dịch vụ tăng số provisioned environments; khi giảm, có thể giảm capacity theo chính sách. Autoscaling có độ trễ, nên không bảo đảm xử lý tức thời mọi burst đột ngột. Nếu latency yêu cầu nghiêm ngặt, giữ một mức min capacity và kết hợp scheduled scaling cho đợt tải đã biết.

### Phối hợp với reserved concurrency

Giá trị provisioned tối đa phải phù hợp với reserved concurrency và account quota. Khi autoscaling, max capacity không được vượt giới hạn có thể cấp. Nếu provisioned concurrency tăng nhưng reserved concurrency hoặc account pool không đủ, cấu hình có thể không đạt trạng thái mong muốn hoặc gây thiếu capacity cho function khác.

## 9. Theo dõi metrics và phát hiện spillover

CloudWatch metrics giúp đánh giá cấu hình có đáp ứng workload không:

| Metric | Ý nghĩa | Cách đọc |
|---|---|---|
| ConcurrentExecutions | Số invocation đồng thời đang chạy | So sánh với reserved concurrency và peak traffic |
| UnreservedConcurrentExecutions | Concurrency đang dùng từ pool không reserve | Theo dõi capacity còn lại cho function dùng chung |
| Throttles | Số invocation bị throttling | Kiểm tra reserved cap, account quota và giới hạn khác |
| ProvisionedConcurrentExecutions | Số provisioned environments đang được sử dụng | Đối chiếu với capacity provisioned |
| ProvisionedConcurrencyUtilization | Tỷ lệ sử dụng provisioned concurrency | Dùng để điều chỉnh mức provisioned hoặc autoscaling target |
| ProvisionedConcurrencySpilloverInvocations | Invocation vượt provisioned capacity và chạy bằng on-demand | Nếu tăng trong giờ SLA nhạy cold start, cân nhắc tăng provisioned capacity |
| ProvisionedConcurrencyInvocations | Invocation được phục vụ bởi provisioned concurrency | Đánh giá mức sử dụng capacity đã trả phí |
| Duration | Thời gian xử lý invocation | Duration tăng làm nhu cầu concurrency tăng |

Ngoài metrics, cần xem log initialization và Init Duration trong Lambda REPORT log khi có cold start. Throttles không chỉ do reserved concurrency; có thể do account quota, scaling rate hoặc giới hạn của trigger. Luôn đối chiếu metric của Lambda với API Gateway, queue, event source mapping và downstream.

### Cách diễn giải nhanh

- **Utilization cao, spillover tăng:** provisioned concurrency có thể thấp hơn nhu cầu ở khung giờ đó.
- **Utilization thấp kéo dài:** có thể đang provision thừa và trả phí cho capacity ít dùng.
- **Throttles tăng nhưng provisioned utilization thấp:** kiểm tra reserved concurrency, account quota, alias/ARN, trigger và lỗi cấu hình trước khi tăng provisioned concurrency.
- **Spillover tăng dù đã provision đủ:** kiểm tra traffic có gọi đúng alias/version, metric có cùng dimension và concurrency burst có vượt mức dự kiến không.
- **Duration tăng:** tìm bottleneck trong handler hoặc dependency; tăng provisioned concurrency chỉ giải quyết capacity/cold start, không sửa được xử lý chậm.

## 10. Chi phí của reserved và provisioned concurrency

Reserved concurrency không có khoản phí riêng chỉ vì giữ một con số concurrency. Tuy nhiên, việc dành capacity có chi phí cơ hội: các function khác không thể dùng phần capacity đó. Invocation vẫn được tính request và duration theo mô hình Lambda thông thường.

Provisioned concurrency có phí theo lượng concurrency được cấu hình, memory được cấp và thời gian cấu hình hoạt động. Invocation chạy trên provisioned capacity vẫn có chi phí request và duration theo giá tương ứng. Do đó, một function giữ nhiều provisioned environments trong thời gian nhàn rỗi vẫn phát sinh chi phí provisioned.

Khi ước lượng chi phí, hãy tính:

1. Số provisioned environments theo từng khung thời gian.
2. Memory size của function.
3. Số giờ/ngày hoặc thời lượng provisioned capacity được duy trì.
4. Invocation request và duration trên provisioned capacity.
5. Invocation spillover chạy bằng on-demand.
6. Chi phí API Gateway, CloudWatch Logs, data transfer và dependency như database.

Đơn giá khác nhau theo Region, kiến trúc, runtime và thời điểm. Dùng AWS Pricing Calculator hoặc bảng giá hiện hành của Region để tính chính xác. Không so sánh chỉ dựa trên chi phí Lambda: giảm cold start có thể cải thiện conversion/SLA, còn provision quá nhiều có thể làm chi phí tăng đáng kể.

### Khi nào provisioned concurrency đáng tiền?

Provisioned concurrency thường hợp lý khi latency của cold start gây ảnh hưởng rõ đến trải nghiệm hoặc SLA, tải có thể dự đoán hoặc có mức nền ổn định, và lợi ích của latency thấp lớn hơn phí duy trì environment. Nếu workload ít request, không nhạy latency hoặc có thể chấp nhận cold start, reserved concurrency hoặc on-demand concurrency có thể đủ.

## 11. Cấu hình bằng AWS CLI

Các lệnh dưới đây minh họa function orders-api và alias prod. Thực hiện trong đúng AWS account và Region; IAM principal cần quyền Lambda tương ứng.

### Đặt reserved concurrency

~~~bash
aws lambda put-function-concurrency \
  --function-name orders-api \
  --reserved-concurrent-executions 100
~~~

Đọc cấu hình:

~~~bash
aws lambda get-function-concurrency \
  --function-name orders-api
~~~

### Publish version và tạo alias

~~~bash
aws lambda publish-version \
  --function-name orders-api

aws lambda create-alias \
  --function-name orders-api \
  --name prod \
  --function-version 42
~~~

Nếu alias đã tồn tại, dùng update-alias để chuyển alias sang version mới sau khi deployment đã sẵn sàng. Ví dụ version 42 chỉ là giá trị minh họa.

### Đặt provisioned concurrency cho alias

~~~bash
aws lambda put-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier prod \
  --provisioned-concurrent-executions 60
~~~

Kiểm tra trạng thái:

~~~bash
aws lambda get-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier prod
~~~

Chờ Status chuyển sang READY trước khi chuyển traffic production sang alias. Nếu trả về IN_PROGRESS, tiếp tục theo dõi; nếu FAILED, xem StatusReason và kiểm tra initialization/configuration.

### Xóa cấu hình khi không còn cần

~~~bash
aws lambda delete-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier prod

aws lambda delete-function-concurrency \
  --function-name orders-api
~~~

Lệnh đầu xóa provisioned concurrency của alias; lệnh sau xóa reserved concurrency của function để function quay về dùng account pool theo chính sách mặc định. Chỉ thực hiện khi đã đánh giá ảnh hưởng đến traffic và downstream.

## 12. Triển khai version và alias an toàn

Một quy trình triển khai thường dùng:

1. Build và deploy code mới lên $LATEST.
2. Chạy test hoặc smoke test trên version mới.
3. Publish version bất biến.
4. Cấu hình provisioned concurrency cho version hoặc alias sẽ nhận traffic.
5. Chờ trạng thái provisioned concurrency là READY.
6. Chuyển alias production sang version mới.
7. Theo dõi error rate, duration, spillover, utilization và throttles.
8. Nếu có sự cố, chuyển alias về version trước theo quy trình rollback.

Không publish version mới rồi lập tức đổi alias nếu mục tiêu là tránh cold start cho traffic đầu tiên. Hãy chuẩn bị capacity trên target version trước. Cũng cần xác nhận API Gateway integration hoặc client gọi alias ARN chứ không gọi $LATEST hay unqualified ARN.

Nếu dùng weighted alias routing để canary, cần hiểu capacity provisioned được cấu hình và phân bổ cho alias/version như thế nào. Kiểm thử đường đi của traffic thực tế để bảo đảm request vào đúng qualifier đã chuẩn bị.

## 13. Kết hợp với Java function và cold start

Provisioned concurrency khởi tạo environment trước, vì vậy nó có thể hấp thụ một phần chi phí startup Java trước khi request đến. Những việc như nạp class, chạy static initializer, khởi tạo framework và tạo client dùng chung có thể được thực hiện trong giai đoạn initialization của environment.

Tuy nhiên, vẫn cần tối ưu code:

- Giữ static initializer ngắn, không gọi database hoặc API ngoài đồng bộ.
- Giảm dependency và component scan không cần thiết.
- Tái sử dụng HTTP/SDK client thread-safe ở cấp environment.
- Không giữ request/user state trong static field.
- Thiết lập connection pool theo tổng concurrency có thể phát sinh, bao gồm nhiều environment.
- Đo init duration, handler duration và downstream latency riêng biệt.

Với Java, SnapStart là một lựa chọn khác trên các runtime/phiên bản Lambda được hỗ trợ. SnapStart lưu snapshot của execution environment sau initialization để phục hồi nhanh hơn. Khả năng kết hợp SnapStart với provisioned concurrency và các giới hạn tương thích phụ thuộc phiên bản/runtime; hãy kiểm tra tài liệu AWS hiện hành trước khi chọn thiết kế. Dù dùng cơ chế nào, phải xử lý đúng tính duy nhất của random value, credential và kết nối sau restore.

## 14. Reserved concurrency để bảo vệ downstream

Giả sử function create-invoice gọi một database có connection pool và database chỉ chịu được 40 truy vấn đồng thời từ function đó. Nếu Lambda scale function lên hàng trăm environment, database có thể quá tải dù Lambda vẫn còn quota.

Đặt reserved concurrency ở mức phù hợp giúp giới hạn số invocation đồng thời. Nhưng cần tính tổng connection từ mọi function và service khác cùng truy cập database. Nếu mỗi invocation mở nhiều connection hoặc giữ connection lâu, reserved concurrency phải được đặt thấp hơn con số suy ra từ connection limit.

Với queue consumer, reserved concurrency có thể giới hạn tốc độ tiêu thụ gián tiếp bằng cách giới hạn số function invocation đồng thời. Tuy nhiên, event source mapping còn có batch size, maximum concurrency và scaling configuration riêng. Hãy phối hợp các giới hạn này để tránh message backlog tăng quá nhanh hoặc database bị dồn tải.

Không dùng provisioned concurrency làm circuit breaker. Nếu downstream lỗi, các environment đã provisioned vẫn có thể tiếp tục gọi downstream. Dùng timeout, retry có giới hạn, backoff, circuit breaker hoặc giảm concurrency để kiểm soát sự cố.

## 15. Những hiểu lầm và lỗi cấu hình thường gặp

| Hiểu lầm/lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ reserved concurrency làm function luôn warm | Vẫn gặp cold start khi tạo environment mới | Dùng provisioned concurrency nếu cần chuẩn bị environment |
| Nghĩ provisioned concurrency đặt trần concurrency | Function có thể spill sang on-demand và tiếp tục scale | Dùng reserved concurrency nếu cần giới hạn tối đa |
| Cấu hình provisioned concurrency trên $LATEST | Không hỗ trợ qualifier mong muốn | Publish version và dùng version/alias |
| API gọi unqualified ARN thay vì alias | Request có thể không dùng capacity provisioned | Kiểm tra integration URI và qualifier |
| Chuyển traffic khi trạng thái chưa READY | Request đầu có thể chưa có capacity đã khởi tạo | Chờ cấu hình sẵn sàng rồi mới chuyển alias |
| Provisioned concurrency lớn hơn reserved concurrency | Cấu hình không hợp lệ hoặc không thể cấp đủ | Đặt reserved concurrency >= provisioned concurrency |
| Đặt reserved concurrency quá cao | Chiếm account pool và làm function khác throttling | Lập ngân sách account-level và theo dõi unreserved pool |
| Đặt provisioned concurrency quá thấp | Spillover tăng, request vẫn cold start | Dựa trên peak concurrency và metric spillover |
| Provision quá nhiều cả ngày | Trả phí cho capacity nhàn rỗi | Scheduled/target tracking scaling và min/max hợp lý |
| Chỉ nhìn Throttles để tăng PC | Có thể không giải quyết đúng nguyên nhân | Kiểm tra account quota, reserved cap, alias và trigger |
| Tăng PC để xử lý database chậm | Tăng số request đến downstream và có thể làm lỗi nặng hơn | Tối ưu dependency và giới hạn concurrency |

## 16. Quy trình lựa chọn và kiểm thử

Khi thiết kế một Lambda function, có thể đi theo các bước:

1. **Đo baseline:** lấy RPS, duration, concurrency, cold start, p95/p99 và error rate.
2. **Xác định mục tiêu:** cần bảo vệ capacity, giới hạn downstream hay giảm cold start?
3. **Chọn reserved concurrency:** tính mức song song tối đa dependency chịu được và capacity function cần bảo đảm.
4. **Chọn provisioned concurrency:** ước lượng concurrency cần warm ở khung giờ/SLA quan trọng; cộng headroom có căn cứ.
5. **Kiểm tra account quota:** tính tổng reserved, provisioned và nhu cầu của các function khác trong Region.
6. **Cấu hình qualifier:** publish version, cấu hình alias và bảo đảm traffic gọi đúng ARN.
7. **Chờ READY:** xác nhận provisioned capacity đã được khởi tạo trước khi chuyển traffic.
8. **Kiểm thử burst:** tăng RPS đột ngột để quan sát spillover, throttles, duration và dependency saturation.
9. **Kiểm thử deployment:** cập nhật version, chuyển alias, rollback và xác nhận capacity của từng version.
10. **Theo dõi chi phí:** so sánh phí provisioned với lợi ích latency và giảm cold start; điều chỉnh lịch hoặc autoscaling.

Nên kiểm thử các trường hợp: concurrency thấp hơn PC, bằng PC, vượt PC nhưng thấp hơn reserved, vượt reserved, account pool gần hết, initialization thất bại, alias trỏ nhầm version, scheduled scaling trễ và downstream bị throttling. Những phép thử này giúp xác định chính xác request nào được phục vụ bằng provisioned capacity, request nào spillover và khi nào function bị throttling.

## 17. Kết luận

Reserved concurrency và provisioned concurrency giải quyết hai nhu cầu khác nhau. Reserved concurrency dành capacity cho một function và đặt giới hạn concurrency tối đa, hữu ích để bảo vệ workload quan trọng và kiểm soát áp lực lên downstream. Provisioned concurrency chuẩn bị sẵn execution environment cho một version hoặc alias, hữu ích khi cần giảm cold start và giữ latency ổn định.

Khi kết hợp, provisioned concurrency phải nằm trong reserved limit nếu function có cấu hình reserved concurrency. Hãy tính concurrency từ peak request rate và duration, thêm headroom, kiểm tra account quota, route traffic qua alias/version đã chuẩn bị, chờ trạng thái READY và theo dõi utilization, spillover cùng throttles. Chọn giá trị dựa trên dữ liệu thực tế để cân bằng latency, khả năng chịu tải và chi phí.
