# Sampling theo môi trường

Trong module **SPRING_BOOT_OBSERVABILITY**, Spring Boot sử dụng Micrometer Observation để kết nối hoạt động của ứng dụng với metrics, logs và distributed tracing. Khi triển khai production, số lượng request và span có thể rất lớn. Gửi toàn bộ trace lên backend giúp giữ lại nhiều chi tiết nhưng làm tăng băng thông, dung lượng lưu trữ và chi phí xử lý. Sampling giải quyết bài toán này bằng cách chọn một phần trace để ghi nhận và xuất đi.

Tỷ lệ sampling cần phù hợp với từng môi trường. Ở máy phát triển, nhóm thường cần quan sát gần như mọi request để debug. Ở staging, cần đủ dữ liệu để kiểm tra hành vi gần production. Ở production, tỷ lệ phải cân bằng giữa khả năng điều tra và ngân sách vận hành. Không có một con số phù hợp cho mọi hệ thống; quyết định cần dựa trên lưu lượng, số span trung bình mỗi trace, yêu cầu điều tra sự cố và năng lực của tracing backend.

## 1. Sampling là gì và giải quyết vấn đề nào?

Một distributed trace mô tả đường đi của một request qua nhiều thành phần, từ service nhận request đến các lời gọi HTTP, truy vấn cơ sở dữ liệu hoặc message consumer. Mỗi hoạt động thường được biểu diễn bằng một span. Khi lưu lượng tăng, số lượng trace và span tăng theo, kéo theo chi phí truyền tải, lưu trữ, lập chỉ mục và truy vấn.

Sampling là quyết định có ghi nhận và xuất một trace hay không. Nếu tỷ lệ sampling là 0.1, hệ thống chọn xấp xỉ 10% trace đủ điều kiện. Tỷ lệ 1.0 tương ứng chọn tất cả; tỷ lệ 0.0 tương ứng không chọn trace nào theo sampler đó.

Sampling thường được áp dụng cho tracing. Nó không nên được hiểu là tỷ lệ lấy mẫu cho toàn bộ observability:

- Metrics thường vẫn được ghi nhận cho các request theo handler metrics đã cấu hình, kể cả khi trace không được lấy mẫu. Điều này giúp biểu đồ request rate, error rate và latency phản ánh toàn bộ lưu lượng.
- Logs ứng dụng vẫn được ghi theo cấu hình logging. Việc một trace có được export hay không là quyết định riêng; khả năng tìm thấy trace tương ứng từ log còn phụ thuộc cách tracer và logging tích hợp context.
- Tracing sampling quyết định trace/span nào được ghi nhận hoặc export bởi tracing pipeline.

Vì metrics và tracing phục vụ hai mục tiêu khác nhau, không nên giảm sampling trace rồi dùng số trace được export để suy ra tổng số request. Hãy dùng metrics làm nguồn đo lường tổng thể, còn trace để điều tra đường đi của các request được chọn.

## 2. Head-based sampling và tail-based sampling

Hai cách tổ chức sampling phổ biến là head-based và tail-based.

**Head-based sampling** đưa ra quyết định sớm, thường tại thời điểm trace được tạo. Với xác suất đã cấu hình, sampler chọn trace ngay từ đầu. Cách này đơn giản, có chi phí thấp và phù hợp khi cần giới hạn lượng dữ liệu ngay trong ứng dụng.

Ưu điểm của head sampling:

- Giảm số span được ghi và gửi ngay tại service.
- Dễ cấu hình theo môi trường bằng application properties.
- Quyết định sớm nên hạn chế chi phí bộ nhớ và mạng ở các service.
- Phù hợp với hệ thống có lưu lượng lớn và yêu cầu sampling tương đối đồng đều.

Hạn chế là sampler chưa biết kết quả cuối cùng của request tại thời điểm quyết định. Một request sau đó trả về lỗi hoặc chậm bất thường vẫn có thể bị loại khỏi trace nếu quyết định ban đầu không chọn nó. Tăng tỷ lệ sampling giúp tăng khả năng bắt gặp các trường hợp hiếm, nhưng đồng thời làm tăng chi phí.

**Tail-based sampling** trì hoãn quyết định đến khi collector đã nhận đủ thông tin của trace hoặc đủ dữ liệu để áp dụng chính sách. Collector có thể ưu tiên giữ trace có lỗi, thời gian xử lý vượt ngưỡng hoặc thuộc nhóm cần theo dõi đặc biệt.

Tail sampling hữu ích khi cần giữ lại các trường hợp hiếm như lỗi production hoặc request vượt ngưỡng latency. Đổi lại, collector phải buffer span trong một khoảng thời gian, ghép các span thuộc cùng trace và có đủ tài nguyên để xử lý. Các span của cùng một trace cần được định tuyến đến cùng collector instance hoặc cùng một tầng có khả năng tập hợp trace.

Nếu ứng dụng đã loại phần lớn trace bằng head sampling, collector không thể khôi phục các trace đã bị loại để tail sampling. Vì vậy, kiến trúc tail sampling thường yêu cầu ứng dụng gửi một tập trace đầu vào đủ rộng, sau đó collector quyết định trace nào được giữ. Cách này tăng tải lên collector và mạng, nên phải được thiết kế cùng giới hạn tài nguyên và chính sách bảo vệ hệ thống.

| Tiêu chí | Head-based sampling | Tail-based sampling |
| --- | --- | --- |
| Thời điểm quyết định | Khi trace bắt đầu hoặc rất sớm trong vòng đời trace | Sau khi collector nhận được dữ liệu cần thiết |
| Thông tin có thể dùng | Context và thông tin có sẵn lúc bắt đầu | Kết quả, lỗi, latency và các span đã nhận |
| Ưu điểm | Đơn giản, giảm tải sớm, dễ cấu hình trong ứng dụng | Có thể ưu tiên trace lỗi hoặc chậm |
| Hạn chế | Có thể bỏ sót lỗi hoặc latency bất thường hiếm gặp | Cần buffer, tài nguyên collector và định tuyến trace phù hợp |
| Nơi thường cấu hình | Sampler trong ứng dụng hoặc tracing SDK | Collector/pipeline hỗ trợ tail sampling |

Không có yêu cầu phải chọn một cơ chế duy nhất cho mọi hệ thống. Có thể dùng head sampling để giới hạn lưu lượng đầu vào và tail sampling cho một luồng riêng, nhưng cần hiểu rằng tail sampler chỉ có thể lựa chọn trong số trace đã đến được collector.

## 3. Cấu hình sampling theo profile Spring Boot

Với Spring Boot 3.x tích hợp Micrometer Tracing, tỷ lệ sampling của tracing có thể được cấu hình bằng thuộc tính:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Giá trị là xác suất trong khoảng từ 0.0 đến 1.0. Nên quản lý giá trị theo cấu hình của môi trường để thay đổi tỷ lệ mà không phải sửa mã nghiệp vụ.

Ví dụ dưới đây minh họa một bộ giá trị khởi đầu. Đây là giá trị tham khảo để thiết kế và thử nghiệm, không phải định mức chung:

**application-dev.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

**application-staging.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.5
~~~

**application-prod.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Trong ví dụ này, dev lấy toàn bộ trace để thuận tiện debug; staging lấy khoảng một nửa để thử nghiệm; production lấy khoảng 5% để kiểm soát lưu lượng. Một service production có lưu lượng thấp và yêu cầu điều tra cao có thể cần tỷ lệ lớn hơn. Một service nhận hàng chục nghìn request mỗi giây có thể cần tỷ lệ thấp hơn hoặc chính sách sampling riêng.

Kích hoạt profile bằng cấu hình triển khai, ví dụ:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Có thể đặt trực tiếp thuộc tính qua biến môi trường để nền tảng triển khai kiểm soát giá trị:

~~~text
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.05
~~~

Khi dùng biến môi trường, hãy kiểm tra thứ tự ưu tiên cấu hình của Spring Boot. Giá trị bên ngoài có thể ghi đè giá trị trong file profile. Điều này hữu ích cho Kubernetes hoặc các nền tảng triển khai khác, nhưng cũng có thể khiến cấu hình thực tế khác với file trong repository. Nên hiển thị hoặc ghi nhận giá trị cấu hình hiệu lực theo cách an toàn trong quá trình khởi động và kiểm tra deployment manifest khi điều tra.

Tránh đặt một tỷ lệ duy nhất trong file cấu hình dùng chung rồi sao chép sang mọi môi trường. Hãy để giá trị mặc định hợp lý cho môi trường phát triển, đồng thời định nghĩa rõ override cho staging và production. Với môi trường production, nên quản lý thay đổi sampling như một thay đổi vận hành có thể theo dõi và rollback.

## 4. Chọn tỷ lệ dựa trên lưu lượng và ngân sách

Tỷ lệ sampling không trực tiếp cho biết số span sẽ được gửi. Số span còn phụ thuộc số trace gốc, số service tham gia và số span trung bình trong mỗi trace.

Có thể ước lượng sơ bộ:

~~~text
số trace được chọn mỗi giây
    = số trace gốc mỗi giây × sampling probability

số span được gửi mỗi giây
    ≈ số trace được chọn mỗi giây × số span trung bình mỗi trace
~~~

Ví dụ, một service nhận khoảng 20.000 trace gốc mỗi giây, dùng xác suất 0.02 và mỗi trace có trung bình 12 span:

- Trace được chọn ước tính: 20.000 × 0.02 = 400 trace/giây.
- Span được gửi ước tính: 400 × 12 = 4.800 span/giây.

Đây chỉ là phép ước lượng. Số liệu thực tế có thể khác do trace phân tán qua nhiều service, span bị loại hoặc bổ sung ở từng tầng, retry, batch, traffic không đồng đều và cấu hình exporter.

Khi chọn tỷ lệ production, cần xem xét:

1. **Lưu lượng và độ rộng trace.** Một request đi qua nhiều service có thể tạo ra nhiều span. Không chỉ nhìn request rate của một service.
2. **Dung lượng và thời gian lưu trữ.** Xác định ngân sách ingest, retention, index và truy vấn của tracing backend.
3. **Mục tiêu điều tra.** Nếu cần phân tích lỗi hiếm, tỷ lệ quá thấp có thể khiến thời gian chờ bắt gặp một trace hữu ích rất dài.
4. **Tính đại diện.** Trace được chọn cần phản ánh đủ loại endpoint, client và luồng nghiệp vụ quan trọng.
5. **Tác động lên ứng dụng.** Theo dõi CPU, bộ nhớ, hàng đợi exporter và băng thông khi tăng sampling.

Một cách triển khai an toàn là bắt đầu từ tỷ lệ thấp đã được tính toán, đo tải thực tế, sau đó tăng dần khi backend còn đủ năng lực. Nếu thay đổi tỷ lệ, hãy ghi lại thời điểm và giá trị mới để người xem dashboard hiểu vì sao số trace hoặc span thay đổi.

## 5. Giữ quyết định sampling nhất quán giữa các service

Distributed tracing chỉ hữu ích khi các span của cùng một request được liên kết thành một trace. Trong hệ thống nhiều service, quyết định sampling ở đầu trace cần được truyền cùng trace context qua HTTP, message hoặc các ranh giới thực thi có hỗ trợ propagation.

Ví dụ, service A nhận request và quyết định lấy mẫu. Khi gọi service B, A truyền trace context trong header. Service B cần tiếp tục xử lý theo quyết định của trace cha theo cơ chế parent-based của tracer đang dùng. Nếu mỗi service tự quyết định độc lập, một phần trace có thể được export trong khi các phần khác bị bỏ, làm trace thiếu span và khó đọc.

Hãy cấu hình propagation nhất quán, chẳng hạn W3C Trace Context hoặc B3 theo chuẩn mà hệ thống đã chọn. Tránh để các service dùng cấu hình propagation không tương thích. Khi có nhiều tracing bridge hoặc SDK, cần kiểm tra hành vi sampler của đúng bridge và phiên bản đang chạy.

Sampling probability là cấu hình cho quyết định sampling tại nguồn; nó không thay thế propagation. Nếu context bị mất khi qua executor, message broker hoặc thread boundary, span có thể bắt đầu một trace mới hoặc không còn quan hệ cha-con dù tỷ lệ sampling đã đúng. Vì vậy, cần kiểm tra cả propagation lẫn sampling khi thấy trace bị chia nhỏ.

Với luồng bất đồng bộ, message producer thường truyền trace context trong metadata/header của message. Consumer tiếp nhận context đó để tạo span tiếp nối. Nếu message được xử lý lại hoặc tạo một luồng mới theo nghiệp vụ, cần xác định rõ quan hệ parent-child hay span link phù hợp thay vì mặc định mọi lần xử lý đều là cùng một request đồng bộ.

## 6. Kết hợp sampling với metrics và logs

Không nên giảm mức ghi nhận metrics chỉ vì muốn giảm lượng trace. Metrics cung cấp góc nhìn thống kê tổng thể: tổng request, tỷ lệ lỗi, latency phân vị và mức sử dụng tài nguyên. Tracing cung cấp chi tiết từng lần thực thi được chọn. Hai loại tín hiệu bổ sung cho nhau.

Một quy trình điều tra điển hình:

1. Dùng metrics phát hiện tỷ lệ lỗi hoặc p95/p99 latency tăng.
2. Xác định service, endpoint hoặc khoảng thời gian có vấn đề.
3. Dùng trace đã được sampling để xem request đi qua những service nào, span nào chậm hoặc thất bại.
4. Dùng logs đã liên kết trace ID/span ID để xem thông tin thực thi liên quan.

Khi trace không được lấy mẫu, ứng dụng vẫn có thể ghi log chứa trace ID tùy tracer và cấu hình. Tuy nhiên, backend tracing có thể không có span tương ứng để mở. Vì vậy, dashboard cần xử lý trường hợp log có trace ID nhưng trace không tồn tại trong backend.

Không ghi dữ liệu nhạy cảm vào span attribute hoặc log chỉ vì trace đã được sampling. Sampling không phải cơ chế bảo vệ dữ liệu. Các định danh, token, thông tin cá nhân và dữ liệu thanh toán vẫn phải tuân thủ chính sách lọc, che dữ liệu và phân quyền truy cập.

## 7. Xử lý các trường hợp hiếm và lỗi production

Head-based sampling theo xác suất đều có thể bỏ qua lỗi hiếm. Nếu một lỗi chỉ xuất hiện ở 1 trong 100.000 request, tỷ lệ lấy mẫu 1% có thể cần rất nhiều request mới thu được một trace lỗi. Có thể cải thiện khả năng điều tra bằng các cách sau:

- Tăng tỷ lệ sampling tạm thời khi đang xử lý sự cố, sau khi đánh giá tải và dung lượng backend.
- Dùng tail-based sampling ở collector để ưu tiên trace có status lỗi hoặc latency vượt ngưỡng, nếu kiến trúc cho phép collector nhận đủ trace đầu vào.
- Duy trì metrics và logs phù hợp để nhận biết lỗi ngay cả khi không có trace được chọn.
- Tạo alert dựa trên error rate, latency và saturation thay vì dựa vào số trace lỗi đã export.

Nếu dùng tail sampling, cần đặt chính sách rõ ràng: giữ trace có lỗi, giữ trace vượt ngưỡng latency, giữ một tỷ lệ nhỏ trace bình thường và giới hạn tổng lượng trace được giữ. Chính sách cần xét đến trace có nhiều span, thời gian chờ đủ span và hành vi khi collector quá tải. Khi collector không đủ bộ nhớ hoặc bị restart trước khi hoàn tất trace, chính sách tail sampling có thể làm mất dữ liệu đang buffer.

Không nên bật sampling 100% trên toàn bộ production chỉ để điều tra một endpoint nếu lưu lượng tổng thể lớn. Hãy cân nhắc một phạm vi hẹp, thời gian áp dụng, mức tải tăng thêm và kế hoạch đưa cấu hình về mức bình thường. Nếu dùng sampler tùy chỉnh theo thuộc tính request, hãy ưu tiên thuộc tính ổn định như route đã chuẩn hóa; không dùng URL chứa ID hoặc dữ liệu người dùng làm điều kiện phân nhánh không kiểm soát.

## 8. Thay đổi sampling an toàn trong production

Thay đổi sampling làm thay đổi số lượng trace và span quan sát được. Dashboard ingest có thể tăng hoặc giảm ngay cả khi lưu lượng request không thay đổi. Vì vậy, hãy ghi nhận sampling probability cùng thời điểm rollout để tránh hiểu nhầm thay đổi telemetry là thay đổi hành vi ứng dụng.

Một quy trình thay đổi có thể gồm:

1. Ghi lại tỷ lệ hiện tại, request rate, span rate, dung lượng backend và mục tiêu của thay đổi.
2. Ước lượng số trace/span mới dựa trên lưu lượng và số span trung bình mỗi trace.
3. Thay đổi cấu hình qua profile hoặc biến môi trường của đúng môi trường.
4. Rollout có kiểm soát, sau đó kiểm tra giá trị cấu hình hiệu lực trên instance.
5. Theo dõi exporter queue, lỗi gửi dữ liệu, CPU, bộ nhớ, network và ingest rate của backend.
6. Xác minh trace có đầy đủ span qua các service và propagation vẫn hoạt động.
7. Ghi lại kết quả, giữ cấu hình mới nếu ổn định hoặc rollback nếu vượt ngân sách.

Nếu tăng tỷ lệ mà exporter thường xuyên timeout, queue đầy hoặc backend từ chối ingest, cần giảm tải hoặc mở rộng pipeline trước khi tiếp tục. Nếu tỷ lệ trace thấp nhưng metrics cho thấy sự cố, kiểm tra quyết định sampling ở root service, propagation header và cấu hình sampler của từng bridge.

## 9. Checklist vận hành

Trước khi phát hành cấu hình sampling, hãy xác nhận:

- Mỗi môi trường có tỷ lệ sampling được định nghĩa rõ ràng.
- Giá trị hiệu lực của management.tracing.sampling.probability đúng với cấu hình triển khai.
- Tỷ lệ được chọn dựa trên request rate, số span mỗi trace và ngân sách backend.
- Các service tuân thủ quyết định sampling được truyền trong trace context.
- Metrics vẫn phản ánh toàn bộ lưu lượng theo cấu hình metrics handler.
- Logs không phụ thuộc vào việc trace được export để ghi nhận lỗi quan trọng.
- Collector có đủ năng lực nếu sử dụng tail sampling.
- Dashboard và alert phân biệt thay đổi sampling với thay đổi lưu lượng thực.
- Có cách tăng hoặc giảm sampling tạm thời và khôi phục cấu hình sau sự cố.

Sampling theo môi trường là một quyết định vận hành có ảnh hưởng trực tiếp đến chi phí và khả năng điều tra. Với Spring Boot và Micrometer Tracing, hãy cấu hình tỷ lệ rõ ràng theo môi trường, truyền quyết định nhất quán qua các service và theo dõi lượng dữ liệu thực tế ở exporter/backend. Dùng metrics để quan sát toàn bộ hệ thống, logs để giữ thông tin vận hành và traces được sampling để phân tích chi tiết từng luồng thực thi.
