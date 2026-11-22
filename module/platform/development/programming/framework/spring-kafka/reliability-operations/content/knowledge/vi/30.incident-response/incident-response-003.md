# Runbook khi DLT tăng đột biến

## Mục tiêu và phạm vi

Runbook này hướng dẫn xử lý khi số bản ghi được đưa vào Dead Letter Topic (DLT) tăng nhanh trong một ứng dụng Spring Kafka. Mục tiêu của incident là:

1. Xác nhận mức độ ảnh hưởng và khoanh vùng listener, consumer group, topic, partition hoặc loại message đang lỗi.
2. Ngăn lỗi tiếp tục khuếch đại qua retry, rebalance hoặc replay không kiểm soát.
3. Bảo toàn message cùng metadata cần thiết để điều tra và xử lý lại.
4. Khôi phục luồng xử lý bình thường, sau đó replay có kiểm soát những message đã vào DLT.
5. Đối soát để chứng minh message không bị mất, xử lý trùng hoặc bỏ sót.

DLT là nơi lưu các bản ghi mà cơ chế xử lý lỗi đã quyết định không retry thêm hoặc không thể tiếp tục xử lý theo chính sách hiện tại. DLT tăng đột biến thường là dấu hiệu của lỗi ở consumer, dữ liệu, dependency hoặc cấu hình retry. Bản thân DLT có thể vẫn hoạt động đúng khi tiếp nhận các message lỗi.

Runbook áp dụng cho cả hai cách triển khai thường gặp trong Spring Kafka:

- **Blocking retry**: container gọi `DefaultErrorHandler`, retry bản ghi theo `BackOff`, sau đó chuyển bản ghi đã hết lượt retry qua `DeadLetterPublishingRecoverer`.
- **Non-blocking retry**: `@RetryableTopic` chuyển bản ghi qua các retry topic theo lịch; khi hết số lần thử, bản ghi được chuyển đến DLT. Cách này thường có `@DltHandler` hoặc một listener riêng để xử lý DLT.

Tên topic và hành vi thực tế phụ thuộc cấu hình ứng dụng. Ví dụ, `DeadLetterPublishingRecoverer` thường dùng tên dạng `<topic>.DLT`, trong khi retry-topic infrastructure thường dùng hậu tố `-dlt`; ứng dụng cũng có thể đặt tên tùy chỉnh. Luôn xác định tên topic từ cấu hình đang chạy trước khi thao tác.

## Khi nào kích hoạt runbook

Kích hoạt khi một hoặc nhiều tín hiệu sau xuất hiện:

- Tốc độ ghi mới vào DLT tăng vượt nền thông thường trong nhiều cửa sổ đo liên tiếp.
- Alert DLT theo topic, consumer group hoặc service chuyển sang trạng thái critical.
- Tỷ lệ xử lý lỗi hoặc số lần gọi recoverer tăng mạnh sau một lần triển khai.
- Retry topic tăng backlog nhanh và nhiều message cuối cùng đi vào DLT.
- DLT consumer không theo kịp, khiến backlog DLT tiếp tục tăng dù tốc độ ghi mới đã giảm.

Phân biệt hai chỉ số: **DLT ingress rate** là tốc độ message mới được ghi vào DLT; **DLT consumer lag** là số message đang chờ consumer DLT xử lý. Ingress rate tăng cho thấy nhiều bản ghi đang thất bại ở luồng nghiệp vụ. Lag tăng có thể chỉ ra DLT consumer hoặc hệ thống xử lý sau DLT đang chậm. Hai vấn đề có thể xảy ra cùng lúc nhưng cần xử lý riêng.

Ngưỡng ví dụ để tạo alert có thể là DLT ingress rate cao hơn ba lần baseline trong năm phút, hoặc vượt ngưỡng tuyệt đối do đội vận hành đặt. Đây chỉ là giá trị khởi điểm; hãy dùng baseline, lưu lượng và SLO của từng hệ thống để cấu hình ngưỡng thực tế.

## Mức độ ảnh hưởng và vai trò

Đánh giá mức độ dựa trên tác động nghiệp vụ, tốc độ tăng, phạm vi topic và khả năng khôi phục:

| Mức độ | Dấu hiệu tham khảo | Hướng xử lý |
|---|---|---|
| SEV-1 | Nhiều luồng quan trọng cùng lỗi; dữ liệu hoặc giao dịch trọng yếu bị đình trệ; không còn khả năng xử lý an toàn | Kích hoạt incident process cấp cao, chỉ định Incident Commander, thông báo các nhóm phụ thuộc và ưu tiên khôi phục dịch vụ |
| SEV-2 | Một luồng nghiệp vụ quan trọng có DLT tăng liên tục; backlog hoặc độ trễ vượt SLO | Điều phối nhóm ứng dụng, Kafka và nhóm sở hữu dependency liên quan; cập nhật tình hình theo chu kỳ ngắn |
| SEV-3 | Phạm vi hẹp, có workaround; message được lưu an toàn và chưa ảnh hưởng đáng kể đến SLO | Nhóm sở hữu service xử lý theo runbook, theo dõi sát ingress rate và backlog |

Incident Commander điều phối quyết định và cập nhật trạng thái. Application Owner phân tích exception, release và logic listener. Kafka/Platform Owner kiểm tra broker, topic, ACL, producer và consumer group. Data hoặc downstream Owner hỗ trợ kiểm tra schema, dữ liệu và dependency. Một người ghi lại mốc thời gian, thay đổi đã thực hiện và kết quả từng bước.

## Thông tin cần ghi nhận

Trước khi thay đổi cấu hình hoặc replay, tạo một bản ghi incident có tối thiểu:

| Nhóm thông tin | Trường cần ghi |
|---|---|
| Thời gian | Thời điểm bắt đầu, thời điểm alert, thời điểm phát hiện, timezone |
| Phạm vi | Environment, service, listener/container, consumer group, source topic, DLT và retry topic liên quan |
| Kafka | Partition, offset, consumer lag, tốc độ ghi DLT, tốc độ đọc DLT, trạng thái broker và producer |
| Ứng dụng | Phiên bản đang chạy, thời điểm deploy gần nhất, cấu hình retry/backoff, số consumer instance và concurrency |
| Lỗi | Exception class, message lỗi đã làm sạch dữ liệu nhạy cảm, stack trace mẫu, số lượng theo nhóm lỗi |
| Message | Key, timestamp, schema/version nếu có, correlation/trace ID và các DLT header hiện diện |
| Tác động | Nghiệp vụ bị ảnh hưởng, số bản ghi ước tính, SLO và workaround đang áp dụng |

Chỉ lưu payload đầy đủ trong nơi được phép truy cập và có kiểm soát. Log, ticket hoặc kênh incident không nên chứa token, thông tin định danh, dữ liệu thanh toán hay payload nhạy cảm. Dùng key, offset và trace ID để liên kết bản ghi khi có thể.

## Quy trình xử lý ban đầu: 0–5 phút

### 1. Xác nhận alert

1. Kiểm tra dashboard và log để xác nhận có message mới được ghi vào DLT.
2. So sánh ingress rate với baseline cùng khung giờ; kiểm tra số liệu theo từng topic và partition.
3. Kiểm tra alert có đang phản ánh backlog DLT cũ hay thực sự có lỗi mới.
4. Ghi nhận thời điểm bắt đầu tăng và đối chiếu với lần deploy, thay đổi cấu hình, thay đổi schema hoặc sự cố dependency gần nhất.

Không kết luận sự cố chỉ từ số lượng message hiện có trong DLT. Một DLT có retention dài có thể chứa backlog cũ dù hệ thống đã hoạt động bình thường.

### 2. Khoanh vùng phạm vi

Kiểm tra lần lượt:

- Một hay nhiều source topic đang đẩy message vào DLT?
- Một hay nhiều consumer group bị ảnh hưởng?
- Lỗi xuất hiện trên mọi partition hay tập trung ở một vài partition/key?
- Nhiều service cùng lỗi hay chỉ một service?
- Retry topic có tăng trước khi DLT tăng không?
- DLT consumer có đang đọc được message không?

Nếu nhiều service và nhiều topic cùng lỗi trong một thời điểm, ưu tiên kiểm tra dependency dùng chung, broker, network, credential hoặc thay đổi nền tảng. Nếu chỉ một topic hoặc một nhóm key lỗi, ưu tiên kiểm tra payload, schema và logic xử lý của service đó.

### 3. Bảo toàn bằng chứng

Lấy một số message đại diện cho từng nhóm exception, không chỉ lấy message đầu tiên. Ghi lại topic, partition, offset, key, timestamp, trace ID, schema/version và các header gốc. Đếm số lượng theo exception class, source topic và partition để biết lỗi có cùng một nguyên nhân hay nhiều nguyên nhân khác nhau.

Không xóa DLT, không reset offset, không chạy replay hàng loạt và không tăng retry vô hạn trong giai đoạn xác nhận. Những thao tác này có thể làm mất bằng chứng, tạo vòng lặp lỗi hoặc tăng tải lên dependency đang gặp sự cố.

### 4. Kiểm tra đường ghi DLT

Xác nhận producer của recoverer có thể ghi vào DLT:

- Topic đích tồn tại và có đủ partition cho chiến lược định tuyến đang dùng.
- Producer có quyền ghi; ACL, credential và TLS còn hợp lệ.
- Broker khỏe, không có lỗi network, quota, ISR hoặc metadata bất thường.
- Log của `DeadLetterPublishingRecoverer` và producer không báo send failure hoặc timeout.
- Cấu hình xử lý kết quả gửi của recoverer phù hợp với yêu cầu độ tin cậy của ứng dụng.

Nếu gửi DLT thất bại, phải xử lý lỗi của đường ghi trước. Không được coi message đã được bảo toàn chỉ vì error handler đã gọi recoverer; cần xác nhận thao tác publish thành công theo cơ chế xác nhận mà ứng dụng cấu hình.

## Chẩn đoán nguyên nhân

Dùng bảng sau để chọn hướng điều tra. Một exception đơn lẻ chưa đủ để xác nhận nguyên nhân; hãy đối chiếu với thời điểm, phạm vi và log ở cả consumer lẫn dependency.

| Dấu hiệu | Nguyên nhân có thể | Cần kiểm tra | Hành động ưu tiên |
|---|---|---|---|
| Nhiều topic cùng tăng sau deploy | Regression, thay đổi contract hoặc cấu hình chung | Release diff, image/config version, log khởi động, thay đổi serializer/deserializer | Đánh giá rollback hoặc hotfix theo quy trình release |
| `DeserializationException` hoặc lỗi schema tập trung ở một loại message | Payload sai định dạng, schema không tương thích, serializer/deserializer lệch version | Schema ID/version, subject compatibility, `ErrorHandlingDeserializer`, dữ liệu producer gửi | Sửa contract hoặc xử lý dữ liệu lỗi; xác minh với mẫu trước khi replay |
| `ClassCastException`, conversion hoặc mapping exception | Consumer kỳ vọng kiểu dữ liệu khác với message thực tế | DTO, type header, message converter, schema và thay đổi model | Sửa mapping hoặc phát hành consumer tương thích |
| Timeout, connection reset hoặc lỗi truy cập DB/API | Dependency chậm, mất kết nối, pool cạn hoặc downstream quá tải | Latency/error rate dependency, connection pool, timeout, circuit breaker và network | Khôi phục dependency; giảm hoặc tạm dừng tiêu thụ có chọn lọc nếu cần |
| `AuthorizationException` hoặc lỗi xác thực | ACL, credential, secret rotation hoặc principal sai | Principal của consumer/producer, quyền đọc source và ghi DLT, thời điểm rotate secret | Khôi phục quyền hoặc credential đúng phạm vi |
| Lỗi chỉ tập trung ở một partition hoặc key | Dữ liệu độc, ordering, partition skew hoặc trạng thái nghiệp vụ riêng | Key, offset liền kề, partition assignment, payload và trạng thái dữ liệu | Cô lập nhóm message lỗi và xử lý nguyên nhân theo key/partition |
| Retry topic tăng trước, sau đó DLT tăng | Dependency hoặc nghiệp vụ không hồi phục trong cửa sổ retry | Retry attempts, delay, số lần thử, tuổi message và trạng thái dependency | Khôi phục nguyên nhân gốc; không chỉ kéo dài retry để che lỗi |
| DLT ingress ổn định nhưng DLT lag tăng | DLT consumer chậm, lỗi xử lý DLT hoặc downstream sau DLT quá tải | Consumer group lag, listener error, concurrency, dependency và throughput | Khôi phục DLT consumer hoặc hệ thống nhận tiếp theo |
| Log báo recoverer send failure hoặc DLT không tăng như dự kiến | Producer DLT, topic, ACL hoặc broker gặp lỗi | Producer callback/result, topic metadata, partition count, ACL và broker log | Khôi phục đường ghi DLT; kiểm tra message chưa được xác nhận xử lý |

### Phân biệt lỗi nghiệp vụ và lỗi hạ tầng

- **Lỗi nghiệp vụ/dữ liệu** thường lặp lại với cùng loại payload, key hoặc schema; các message khác vẫn được xử lý bình thường.
- **Lỗi dependency** thường có tương quan với latency, timeout hoặc error rate của DB/API; nhiều loại message có thể cùng thất bại.
- **Lỗi Kafka/platform** thường ảnh hưởng nhiều consumer hoặc producer, có biểu hiện ở broker, network, ACL, quota, metadata hoặc rebalance.
- **Lỗi cấu hình retry** thường thể hiện ở số lần thử, thời gian chờ, phân loại exception hoặc định tuyến DLT không đúng kỳ vọng.

Kiểm tra cả exception đầu tiên và exception cuối cùng. Một message có thể đi qua nhiều lần retry và chỉ được ghi nhận bằng exception cuối; log của lần thử đầu có thể chứa manh mối về nguyên nhân ban đầu.

## Các điểm cần kiểm tra trong Spring Kafka

### Blocking retry với `DefaultErrorHandler`

Kiểm tra bean `DefaultErrorHandler` và các cấu hình liên quan:

- `BackOff` đang dùng là fixed, exponential hay custom; số lần retry và khoảng cách giữa các lần thử là bao nhiêu.
- Exception nào được retry, exception nào được phân loại là không retry.
- Recoverer thực tế là `DeadLetterPublishingRecoverer` hay implementation khác.
- Có cấu hình retry theo record hay batch; listener đang dùng ack mode nào.
- Cách xử lý lỗi khi publish DLT thất bại và cách xác nhận offset/recovery đang được cấu hình ra sao.
- Có exception bị wrap hoặc phân loại sai khiến lỗi không retry được retry quá nhiều lần hay không.

Với `DefaultErrorHandler`, bản ghi có thể được thử lại trong luồng xử lý của container trước khi recoverer được gọi. Khi hết retry, recoverer thường publish bản ghi sang DLT. Hành vi commit/ack sau recovery phụ thuộc ack mode, cấu hình error handler, transaction và phiên bản Spring Kafka. Trước khi thay đổi offset hoặc ack behavior, hãy xác minh cấu hình đang chạy và kiểm tra khả năng phát sinh xử lý lặp.

### Non-blocking retry với `@RetryableTopic`

Kiểm tra:

- Số attempt, backoff, delay và danh sách retry topic thực tế.
- Quy tắc đặt tên topic, DLT suffix và partition của từng retry topic.
- `@DltHandler` hoặc DLT listener đang ghi log, lưu trữ, cảnh báo hay thực hiện nghiệp vụ gì.
- Retry topic có đủ partition, retention và quyền truy cập không.
- Message đang chờ ở retry topic nào và tuổi của message lớn nhất.

Non-blocking retry chuyển message qua các topic khác nhau nên thứ tự xử lý giữa các message cùng key có thể thay đổi. Khi khôi phục hoặc replay, phải đánh giá tác động ordering đối với nghiệp vụ trước khi chạy song song.

### Header và metadata của DLT

Spring Kafka thường bổ sung header mô tả nguồn và lỗi, ví dụ:

- `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET`.
- `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` và `DLT_ORIGINAL_TIMESTAMP_TYPE`.
- `KafkaHeaders.DLT_EXCEPTION_FQCN`, `DLT_EXCEPTION_MESSAGE`, `DLT_EXCEPTION_STACKTRACE`.
- `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP`.

Tên header và mức độ hiện diện phụ thuộc phiên bản, recoverer và cấu hình. Hãy kiểm tra header thực tế của message mẫu. Khi replay, giữ lại metadata nguồn cần cho audit và correlation; tránh để header exception cũ làm hệ thống xử lý lần replay hiểu nhầm rằng lỗi cũ vẫn đang xảy ra.

## Hành động giảm thiểu theo nguyên nhân

Thực hiện một thay đổi tại một thời điểm, ghi lại người thực hiện, thời gian, lý do và metric trước/sau. Sau mỗi thay đổi, quan sát ít nhất một cửa sổ đủ dài để xác định xu hướng.

### Nếu lỗi bắt đầu sau một lần deploy

1. Xác nhận phiên bản và cấu hình của các instance đang chạy.
2. So sánh thay đổi liên quan đến listener, DTO, serializer/deserializer, schema, exception handling và dependency client.
3. Nếu có bằng chứng regression và rollback an toàn, thực hiện rollback theo quy trình release.
4. Theo dõi DLT ingress rate, lỗi mới và consumer lag sau rollback.
5. Giữ lại message đã vào DLT để xử lý sau khi phiên bản tương thích được khôi phục.

### Nếu dependency đang chậm hoặc không khả dụng

1. Phối hợp với owner của dependency để xác nhận trạng thái và thời gian phục hồi dự kiến.
2. Kiểm tra retry/backoff, timeout, connection pool và circuit breaker để tránh tạo thêm tải.
3. Nếu consumer tiếp tục tiêu thụ làm tăng lỗi hoặc gây quá tải, cân nhắc pause listener hoặc giảm tốc độ tiêu thụ ở phạm vi nhỏ nhất có thể. Ghi rõ consumer group, listener và partition bị tác động.
4. Kiểm tra retention của source topic và retry topic để bảo đảm message còn đủ thời gian chờ dependency phục hồi.
5. Resume theo từng bước khi dependency khỏe; quan sát error rate và latency trước khi khôi phục toàn bộ concurrency.

Không tăng concurrency hoặc số lần retry một cách máy móc. Nếu dependency là nút thắt, các thay đổi này có thể làm tải tăng và khiến sự cố kéo dài hơn.

### Nếu có message không hợp lệ hoặc không tương thích schema

1. Gom nhóm message theo schema/version, exception, key và producer.
2. Xác minh producer có phát message sai contract hay consumer vừa thay đổi cách deserialize.
3. Chọn hướng sửa contract, bổ sung tương thích ngược hoặc tạo quy trình xử lý riêng cho dữ liệu không hợp lệ.
4. Nếu cần bỏ qua một loại dữ liệu, phải có quyết định nghiệp vụ được ghi nhận, danh sách message cụ thể và bằng chứng lưu trữ/audit.
5. Chỉ replay các message đã được xác nhận có thể xử lý.

Không xóa message chỉ vì một nhóm dữ liệu gây lỗi. Việc loại bỏ phải có phê duyệt nghiệp vụ và bằng chứng đối soát theo quy trình của hệ thống.

### Nếu đường ghi DLT gặp lỗi

1. Kiểm tra topic đích, partition count, ACL, credential, producer config và sức khỏe broker.
2. Xác minh recoverer có nhận được kết quả publish thành công hay thất bại.
3. Kiểm tra transaction và error handler để biết consumer sẽ retry, dừng hay tiếp tục trong trường hợp publish DLT lỗi.
4. Khôi phục đường ghi DLT trước khi cho phép luồng xử lý lỗi chạy lại bình thường.
5. Đối chiếu offset/source record với DLT để tìm bản ghi chưa được xác nhận publish.

Không tự tạo topic hoặc đổi partition mapping trong production nếu chưa xác minh chiến lược định tuyến của recoverer. Thay đổi không tương thích có thể khiến publish DLT tiếp tục thất bại.

## Khôi phục và replay message từ DLT

Replay là thao tác có rủi ro xử lý trùng hoặc sai thứ tự. Chỉ bắt đầu khi nguyên nhân gốc đã được sửa hoặc có workaround đã kiểm chứng, đường ghi/đọc Kafka ổn định và owner nghiệp vụ chấp thuận phạm vi replay.

### Điều kiện trước replay

- Đã xác định source topic, DLT, retry topic, consumer group và chiến lược định tuyến.
- Đã phân loại message theo exception, schema/version, key, partition và khoảng offset.
- Đã chọn tập message cần replay; loại trừ message đã xử lý thủ công hoặc đã được xác nhận không cần xử lý.
- Consumer phiên bản mới có thể đọc payload và tương thích schema.
- Dependency nhận message đã khỏe và có đủ capacity.
- Nghiệp vụ có idempotency hoặc cơ chế deduplication phù hợp.
- Đã xác định cách giữ ordering, partition mapping, metadata nguồn và audit.
- Đã thử với một nhóm nhỏ hoặc môi trường kiểm thử đại diện.

### Các bước replay an toàn

1. **Lập manifest**: ghi lại DLT topic, partition, offset, key, timestamp, trace ID, loại lỗi và quyết định replay cho từng nhóm.
2. **Chọn đích**: xác định replay về source topic, một replay topic riêng hay một luồng xử lý có kiểm soát. Chọn theo thiết kế của ứng dụng và quy tắc nghiệp vụ.
3. **Kiểm tra partition**: nếu giữ partition gốc, bảo đảm topic đích có partition tương ứng. Xác minh key và partitioner để tránh thay đổi phân vùng ngoài dự kiến.
4. **Chạy thử nhỏ**: replay một lượng nhỏ message đã chọn; xác nhận consumer xử lý thành công, dữ liệu đích đúng và không tạo side effect trùng.
5. **Tăng dần tốc độ**: chia thành batch có giới hạn, tăng theo capacity thực tế. Theo dõi throughput, latency, consumer lag, error rate và DLT ingress rate sau mỗi batch.
6. **Ghi nhận kết quả**: lưu số message đã đọc, publish thành công, xử lý thành công, thất bại lại và còn chờ; lưu liên kết tới manifest và trace.
7. **Dừng khi có dấu hiệu xấu**: dừng batch tiếp theo nếu DLT ingress tăng trở lại, dependency vượt ngưỡng, consumer lag tăng mất kiểm soát hoặc phát hiện side effect trùng.

### Những điểm phải kiểm soát

- **Idempotency**: cùng một message có thể được xử lý lại nếu consumer đã tạo side effect nhưng chưa commit offset, hoặc nếu replay được chạy nhiều lần. Dùng idempotency key, unique constraint, inbox/deduplication store hoặc cơ chế tương đương của hệ thống.
- **Ordering**: nếu nghiệp vụ yêu cầu thứ tự theo key, replay theo partition/key và không chạy song song tùy tiện. Retry topic có thể đã làm thay đổi thứ tự ban đầu.
- **Offset**: replay bằng consumer group riêng hoặc công cụ chuyên dụng theo quy trình vận hành. Không reset offset của consumer group production để thay thế replay có chọn lọc.
- **Header**: giữ metadata nguồn cần thiết để audit; thêm replay ID hoặc correlation ID mới nếu hệ thống hỗ trợ; xử lý header lỗi cũ theo chính sách rõ ràng.
- **Transaction**: publish lại và đánh dấu message DLT đã xử lý có thể là hai thao tác riêng. Nếu không có transaction hoặc cơ chế bù trừ phù hợp, phải thiết kế replay có thể chạy lại an toàn.
- **Retention**: kiểm tra retention của DLT trước và trong incident. Không thay đổi retention để dọn dữ liệu khi chưa đối soát và chưa có bản lưu được phê duyệt.

Không dùng việc tăng offset, xóa DLT hoặc replay toàn bộ topic làm cách khôi phục mặc định. Các thao tác đó có thể bỏ qua message chưa xử lý hoặc tạo tác động nghiệp vụ lặp.

## Theo dõi sau khắc phục

Sau khi nguyên nhân đã được xử lý, theo dõi đồng thời các chỉ số sau:

| Chỉ số | Kỳ vọng sau khắc phục |
|---|---|
| DLT ingress rate | Trở về baseline hoặc giảm về ngưỡng bình thường; không xuất hiện nhóm lỗi mới |
| Source consumer lag | Giảm ổn định, không tăng lại sau khi khôi phục concurrency |
| Retry topic backlog | Giảm theo kế hoạch; không tiếp tục chuyển hàng loạt sang DLT |
| DLT consumer lag | Được xử lý theo capacity đã xác nhận; không có lỗi mới ở DLT listener |
| Consumer error rate | Trở về mức bình thường; exception gốc không tái xuất hiện |
| Dependency latency/error rate | Ổn định dưới ngưỡng SLO và đủ capacity nhận tải phục hồi |
| Replay result | Số lượng đọc, publish, xử lý, thất bại và còn chờ được đối soát |

Giữ theo dõi ít nhất qua vài cửa sổ đánh giá phù hợp với lưu lượng của hệ thống. Với luồng ít message, cần quan sát đủ lâu để có cơ hội xuất hiện traffic đại diện; không đóng incident chỉ vì metric tức thời bằng không.

## Điều kiện đóng incident

Chỉ đóng khi tất cả điều kiện phù hợp đã được xác nhận:

- Nguyên nhân gốc hoặc workaround đã được ghi lại, có owner chịu trách nhiệm.
- DLT ingress rate và consumer error rate trở về mức chấp nhận được trong khoảng quan sát đã thống nhất.
- Source consumer, retry topic và DLT consumer không còn backlog tăng bất thường.
- Dependency liên quan ổn định và có capacity xử lý lưu lượng bình thường.
- Message trong DLT đã được phân loại: replay thành công, chờ xử lý có owner/SLA, hoặc được loại bỏ theo quyết định nghiệp vụ có audit.
- Số lượng message đã nhận, đã xử lý, đang chờ và được loại bỏ đã được đối soát.
- Các thay đổi tạm thời như pause listener, giảm concurrency hoặc thay đổi cấu hình đã được khôi phục hoặc chuyển thành thay đổi chính thức có review.
- Dashboard, alert và tài liệu vận hành đã được cập nhật nếu incident phát hiện thiếu sót.

## Mẫu ghi nhận incident

Sao chép mẫu dưới đây vào ticket hoặc incident log:

```text
Incident ID:
Environment:
Service / Listener:
Consumer group:
Source topic(s):
Retry topic(s):
DLT topic(s):
First seen / Alert time (timezone):
DLT ingress rate / baseline:
Source lag / DLT lag:
Affected partitions / offsets:
Top exception groups:
Last deployment or config change:
Dependency status:
Business impact:

Mitigation applied:
Owner and timestamp for each change:
Root cause / current hypothesis:
Replay manifest:
Replay read / published / processed / failed / pending:
Reconciliation result:
Follow-up actions and owners:
Incident closed by / time:
```

## Checklist nhanh cho người trực

- [ ] Xác nhận DLT ingress rate tăng hay chỉ DLT consumer lag tăng.
- [ ] Xác định source topic, consumer group, listener, partition và thời điểm bắt đầu.
- [ ] Đối chiếu với deploy, schema change, credential rotation và dependency incident.
- [ ] Lấy mẫu message an toàn; nhóm theo exception, key và schema/version.
- [ ] Kiểm tra retry topic và đường publish DLT, gồm topic, partition, ACL và producer result.
- [ ] Chọn biện pháp giảm thiểu theo nguyên nhân; ghi lại mọi thay đổi.
- [ ] Chỉ replay sau khi có manifest, kiểm tra idempotency, ordering, capacity và phê duyệt cần thiết.
- [ ] Theo dõi metric sau khắc phục và đối soát đầy đủ message.
- [ ] Ghi nguyên nhân, quyết định, owner và hành động phòng ngừa trước khi đóng incident.
