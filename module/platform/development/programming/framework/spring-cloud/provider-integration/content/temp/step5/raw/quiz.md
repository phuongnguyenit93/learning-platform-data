Câu 1. Các thư viện Spring Cloud cho AWS, Azure và GCP giúp ứng dụng Spring Boot điều gì?
A. Tạo client và cấu hình credential để gọi managed service.
B. Đồng bộ credential giữa provider qua một Spring bean chung.
C. Thay IAM policy bằng annotation Spring Security ở client.
D. Áp chung transaction boundary cho API của ba provider.
Đáp án đúng: A

Câu 2. Ứng dụng Spring Boot muốn tải tệp lên Amazon S3; thành phần nào thích hợp?
A. Spring Cloud AWS `SecretsManagerClient` cho object.
B. AWS `SqsTemplate` để trao đổi message SQS.
C. Spring Cloud AWS `SnsTemplate` hoặc AWS SNS client.
D. Spring Cloud AWS `S3Template` hoặc AWS S3 client.
Đáp án đúng: D

Câu 3. Trong Spring Cloud Azure, client nào thích hợp để thao tác Blob Storage?
A. Azure `SecretClient` để đọc dữ liệu từ Key Vault.
B. Azure `CosmosClient` để thao tác với document database.
C. Azure `BlobServiceClient` cho upload và download Blob.
D. Azure `ServiceBusSenderClient` để gửi dữ liệu tới queue.
Đáp án đúng: C

Câu 4. Ứng dụng Spring Boot tích hợp Google Cloud Storage nên dùng client nào?
A. Google Cloud `BigQuery` client cho dataset và table.
B. Google Cloud `Storage` client cho bucket và object.
C. Google Cloud `Firestore` client cho collection và document.
D. Google Cloud `Publisher` client cho topic và message.
Đáp án đúng: B

Câu 5. Ứng dụng chạy trên AWS cần quyền đọc S3; cách cấp credential nào phù hợp?
A. Đưa token AWS CLI từ máy lập trình viên vào lúc deploy.
B. Dùng IAM role của workload qua AWS credential chain.
C. Cấp role administrator chung cho tất cả replica của app.
D. Đưa access key dài hạn vào Spring profile của service.
Đáp án đúng: B

Câu 6. Ứng dụng trên Azure có Managed Identity; cách xác thực nào phù hợp?
A. Dùng `DefaultAzureCredential` với identity đã được cấp RBAC.
B. Dùng SAS token dùng chung thay cho quyền identity của app.
C. Dùng `ClientSecretCredential` với secret ghi trong source code.
D. Dùng storage account key dài hạn đưa vào application YAML.
Đáp án đúng: A

Câu 7. Khi chạy Spring Boot trên Google Cloud, ADC giúp xác thực thế nào?
A. Dùng API key public để truy cập tài nguyên có IAM.
B. Dùng một file JSON key chung cho các môi trường.
C. Dùng project ID làm token thay cho service account.
D. Lấy credential từ service account gắn với workload.
Đáp án đúng: D

Câu 8. Muốn chạy local và production mà không đưa secret vào mã nguồn, nên làm gì?
A. Chia sẻ file key của developer cho tất cả CI runner.
B. Dùng credential của production trong cả profile local.
C. Đặt access token cố định trong image để tái sử dụng.
D. Dùng credential chain và identity riêng theo môi trường.
Đáp án đúng: D

Câu 9. Service chỉ đọc object trong một bucket; quyền cloud IAM nào hợp lý nhất?
A. Cấp quyền đọc đúng bucket hoặc prefix mà workload cần.
B. Cấp quyền quản trị mọi bucket để giảm lỗi permission.
C. Cấp quyền ghi và xóa toàn account cho service đọc.
D. Cấp quyền dựa trên hostname thay vì action và resource.
Đáp án đúng: A

Câu 10. Khi triển khai đa region hoặc đa project, cách cấu hình nào tránh truy cập sai tài nguyên?
A. Giữ region mặc định và thử tên bucket khác nếu lỗi.
B. Giữ chung một endpoint khi chạy trên nhiều cloud region.
C. Chọn region, account hoặc project theo từng môi trường.
D. Thay tên Spring application để provider chọn project.
Đáp án đúng: C

Câu 11. Cần cho client tải object riêng mà không mở public bucket, giải pháp nào phù hợp?
A. Đổi bucket sang public-read trong thời gian download.
B. Đưa access key backend vào URL để client tự ký request.
C. Cấp URL có chữ ký, hết hạn và giới hạn thao tác.
D. Dùng URL nội bộ không auth và không có thời gian hết hạn.
Đáp án đúng: C

Câu 12. Cần mã hóa dữ liệu lưu trong cloud storage bằng khóa do tổ chức quản lý; làm gì?
A. Bật server-side encryption dùng KMS hoặc customer-managed key.
B. Chỉ dùng presigned URL thay cho cấu hình mã hóa at-rest.
C. Bật TLS khi upload nhưng giữ dữ liệu at-rest chưa mã hóa.
D. Đổi tên bucket theo môi trường để provider đổi khóa mã hóa.
Đáp án đúng: A

Câu 13. Consumer xử lý xong message Amazon SQS; bước nào tránh nhận lại message đó?
A. Đợi visibility timeout kết thúc để SQS tự đánh dấu đã ack.
B. Gọi `basicAck` trên AMQP channel để broker xóa message.
C. Xóa SNS subscription để queue tự loại message đã nhận.
D. Delete message bằng receipt handle sau khi xử lý thành công.
Đáp án đúng: D

Câu 14. Muốn một event AWS đến hai queue phục vụ hai hệ thống, thiết kế nào phù hợp?
A. Gửi event vào S3 rồi dùng visibility timeout phân phối.
B. Gửi message vào một SQS queue với hai consumer group.
C. Gửi một SQS message để hai consumer lấy cùng bản sao.
D. Publish lên SNS topic đã subscribe tới hai SQS queue.
Đáp án đúng: D

Câu 15. Azure Service Bus topic có hai subscription; mô hình phân phối nào đúng?
A. Subscription được tạo sớm nhất có ưu tiên độc quyền.
B. Mỗi subscription nhận bản message phù hợp và ack độc lập.
C. Hai subscription chia luân phiên cùng một bản message.
D. Topic đợi subscription đầu ack rồi mới gửi tới nơi khác.
Đáp án đúng: B

Câu 16. Google Cloud Pub/Sub có hai subscription tới cùng topic; điều gì đúng?
A. Publisher nhận phản hồi sẽ thay cả hai subscription tự ACK.
B. Mỗi message được route ngẫu nhiên tới một subscription duy nhất.
C. Mỗi subscription theo dõi tiến độ ACK riêng cho message.
D. ACK một subscription đồng thời xóa message ở subscription kia.
Đáp án đúng: C

Câu 17. Visibility timeout của SQS ảnh hưởng thế nào khi consumer chưa xóa message?
A. Message bị khóa vĩnh viễn tới khi producer publish lại.
B. Message bị xóa ngay khi API receive trả về.
C. Message chuyển vào SNS topic để chờ xác nhận từ publisher.
D. Message tạm ẩn và có thể được giao lại khi hết hạn.
Đáp án đúng: D

Câu 18. Azure Service Bus ở chế độ PeekLock: consumer xử lý thành công nên làm gì?
A. Đợi lock hết hạn để Service Bus tự xác nhận đã xử lý.
B. Defer message để xác nhận hoàn thành thay cho Complete.
C. Complete message đang khóa để xác nhận đã xử lý.
D. Abandon message để xóa khỏi queue sau khi hoàn tất.
Đáp án đúng: C

Câu 19. Handler của Google Pub/Sub xử lý lâu hơn ACK deadline; biện pháp nào phù hợp?
A. Không gửi ACK vì provider tự biết handler đã hoàn thành.
B. Gia hạn ACK deadline khi cần trong thời gian xử lý.
C. Xóa subscription sau khi xử lý để tránh redelivery.
D. Tăng thời gian lưu topic để ACK deadline tự gia hạn.
Đáp án đúng: B

Câu 20. Consumer cloud messaging có thể nhận lại event sau lỗi mạng; giải pháp nào phù hợp?
A. Tăng số consumer để sự kiện không bị nhận lặp.
B. Lưu event ID hoặc khóa nghiệp vụ để xử lý idempotent.
C. Dựa vào cờ redelivery để bỏ mọi event được gửi lại.
D. Chỉ retry bằng cách đổi message ID sau mỗi lần đọc.
Đáp án đúng: B

Câu 21. Khi managed messaging trả lỗi tạm thời, nên thiết kế retry thế nào?
A. ACK trước khi xử lý lại để loại lỗi ở broker.
B. Đổi tên subscription để broker tự reset lỗi consumer.
C. Giới hạn retry và dùng backoff, jitter cùng DLQ phù hợp.
D. Retry không giới hạn ngay lập tức trên cùng một thread.
Đáp án đúng: C

Câu 22. Khi chuyển consumer từ SQS FIFO sang dịch vụ messaging cloud khác, cần kiểm tra gì?
A. Bỏ kiểm tra giao trùng vì ordering bảo đảm exactly-once.
B. So sánh bảo đảm thứ tự, ACK và retry của provider đích.
C. Dùng chung visibility timeout vì mọi provider đều có SQS API.
D. Giữ ordering key cũ mà không kiểm tra semantics.
Đáp án đúng: B

Câu 23. Dịch vụ nào dùng cho secret tương ứng ở AWS, Azure và Google Cloud?
A. AWS S3, Azure Blob Storage và Google Cloud Storage.
B. AWS Secrets Manager, Azure Key Vault và Google Secret Manager.
C. AWS SNS, Azure Service Bus và Google Cloud Pub/Sub.
D. AWS CloudWatch, Azure Monitor và Google Cloud Logging.
Đáp án đúng: B

Câu 24. Khi một secret được rotate mà ứng dụng cache credential, cần xử lý gì?
A. Làm mới credential và kết nối bị ảnh hưởng khi cần.
B. Tiếp tục dùng secret cũ dù nó đã bị thu hồi.
C. Ghi secret mới vào Git rồi triển khai lại toàn bộ hệ thống.
D. Tăng HTTP timeout để secret cũ tiếp tục được chấp nhận.
Đáp án đúng: A

Câu 25. Với API cloud dùng IAM và kết nối TLS, cấu hình bảo mật nào phù hợp?
A. Dùng TLS certificate để thay toàn bộ quyền truy cập resource.
B. Xem IAM policy là đủ để bảo vệ dữ liệu khi truyền.
C. Xác minh TLS endpoint và cấp quyền IAM tối thiểu.
D. Ẩn hostname endpoint để request không cần authentication.
Đáp án đúng: C

Câu 26. Spring Boot kết nối PostgreSQL managed trên cloud theo cách nào?
A. Dùng JDBC DataSource với driver, network, TLS và auth đúng.
B. Gửi SQL qua S3 client với câu query làm object key.
C. Dùng Secret Manager làm JDBC driver truy vấn database.
D. Gửi SQL qua Pub/Sub topic để nhận row từ subscriber.
Đáp án đúng: A

Câu 27. Dùng `@Transactional` ghi DB rồi publish cloud message; điều nào đúng?
A. Provider messaging tự rollback database khi publish timeout.
B. Commit database sẽ tự ACK message ở provider bên ngoài.
C. Cho rằng `@Transactional` bao gồm cả bước publish.
D. Transaction DB không tự làm atomic bước publish từ xa.
Đáp án đúng: D

Câu 28. Muốn tránh mất event sau khi database commit, giải pháp nào phù hợp?
A. Publish event trước rồi mới ghi vào DB.
B. Ghi event vào public bucket để thay cơ chế messaging.
C. Ghi outbox trong transaction DB và publish sau đó.
D. Phát event nhiều lần mà không cần kiểm tra bản ghi trùng.
Đáp án đúng: C

Câu 29. Test local AWS, Azure Blob và Google Pub/Sub; bộ công cụ nào phù hợp?
A. LocalStack, Azurite và Google Pub/Sub emulator.
B. WireMock, PostgreSQL và H2 thay cloud messaging.
C. LocalStack, Redis và Docker Registry cùng nhau.
D. MinIO, Kafka Streams và Liquibase cho mọi provider.
Đáp án đúng: A

Câu 30. Vì sao emulator chưa đủ để xác nhận hành vi của managed service production?
A. Emulator có thể khác ở IAM, quota hoặc hành vi edge case.
B. Emulator tái hiện đầy đủ IAM và quota production.
C. Emulator dùng chung endpoint và network ACL với production.
D. Emulator tự nhận workload identity thật trên cloud provider.
Đáp án đúng: A

Câu 31. Khi giám sát hệ thống cloud messaging, nhóm tín hiệu nào sát nhu cầu hơn?
A. CPU, RAM, thread pool và log level của JVM ứng dụng.
B. Thời gian build image, commit SHA và trạng thái CI.
C. Tốc độ upload object, storage quota và bucket lifecycle.
D. Backlog, retry, DLQ, latency và trace/correlation ID.
Đáp án đúng: D

Câu 32. Muốn nghiệp vụ dễ chuyển đổi giữa AWS, Azure và Google Cloud, thiết kế nào phù hợp?
A. Cho domain model phụ thuộc vào kiểu request AWS SDK.
B. Tách interface domain khỏi adapter và kiểm thử hợp đồng.
C. Giữ nguyên ack và IAM rule khi đổi cloud provider.
D. Đưa cả ba provider SDK vào một service method chung.
Đáp án đúng: B
