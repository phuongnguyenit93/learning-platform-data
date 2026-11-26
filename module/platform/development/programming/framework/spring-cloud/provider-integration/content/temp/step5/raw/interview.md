Bạn lựa chọn dịch vụ managed của AWS, Azure hoặc Google Cloud cho một ứng dụng Spring Boot dựa trên những tiêu chí nào?
Bạn phân biệt SDK của cloud provider với thư viện tích hợp Spring Cloud tương ứng về trách nhiệm như thế nào?
Bạn thiết kế lớp adapter để business service không phụ thuộc trực tiếp vào API của một provider ra sao?
Bạn phân biệt tính di động của mã nguồn với khả năng di chuyển dữ liệu và hạ tầng giữa các cloud như thế nào?
Bạn xác định ranh giới giữa domain logic, Spring integration starter và provider SDK như thế nào?
Bạn đánh giá vendor lock-in khi dùng tính năng riêng của storage, messaging và managed database như thế nào?
Bạn so sánh sử dụng dịch vụ managed với tự vận hành broker hoặc database trong Kubernetes ra sao?
Bạn chọn cloud service theo latency, data residency, availability và tổng chi phí như thế nào?
Bạn lập danh sách phụ thuộc cloud của một microservice để đánh giá blast radius khi provider gặp lỗi ra sao?
Bạn lựa chọn single-cloud hay multi-cloud architecture dựa trên yêu cầu khôi phục và nguồn lực nào?
Bạn phân biệt multi-region trong một provider với multi-cloud về tính nhất quán và độ phức tạp ra sao?
Bạn thiết kế contract chung khi các provider có retry và delivery semantics khác nhau như thế nào?
Bạn xác định phần nào không nên trừu tượng hóa để giữ khả năng khai thác thế mạnh provider ra sao?
Bạn đánh giá rủi ro startup phụ thuộc đồng thời quá nhiều managed services như thế nào?
Bạn mô tả luồng dữ liệu Spring Boot qua object storage, message queue và managed database như thế nào?
Bạn lựa chọn tích hợp HTTP đồng bộ hoặc messaging bất đồng bộ theo yêu cầu nghiệp vụ nào?
Bạn xác định yêu cầu encryption, audit, backup và disaster recovery trước khi chọn cloud service ra sao?
Bạn ước lượng egress cost khi dữ liệu phải đi giữa nhiều cloud hoặc region như thế nào?
Bạn phân tích latency khi ứng dụng chạy ở một cloud nhưng database đặt tại cloud khác ra sao?
Bạn phân biệt lỗi application, SDK và provider outage thông qua những bằng chứng nào?
Bạn thiết kế môi trường phát triển local khi production sử dụng nhiều cloud managed services như thế nào?
Bạn xác định loại test nào cần chạy trên cloud thật thay vì emulator dựa trên rủi ro nào?
Bạn phân công quyền sở hữu cloud resources giữa đội ứng dụng và đội nền tảng như thế nào?
Bạn tổ chức region và project configuration riêng cho từng adapter mà không hardcode domain logic ra sao?
Bạn xây dựng kế hoạch thay provider cho một dịch vụ managed đã không còn đáp ứng yêu cầu như thế nào?
Bạn kiểm tra compatibility matrix giữa Spring Boot, Spring Cloud và Spring Cloud AWS theo cách nào?
Bạn quản lý BOM và dependency versions của Spring Cloud Azure phù hợp với release train như thế nào?
Bạn lựa chọn thư viện tích hợp Google Cloud với Spring phù hợp phiên bản đang dùng ra sao?
Bạn phân biệt dependency starter và dependency SDK khi một cloud client được auto-configure như thế nào?
Bạn kiểm tra các bean auto-configuration được tạo khi thêm starter object storage như thế nào?
Bạn xử lý xung đột bean khi ứng dụng dùng nhiều accounts hoặc regions trong cùng provider ra sao?
Bạn tổ chức @ConfigurationProperties cho region, endpoint, project và credential source như thế nào?
Bạn phân biệt cấu hình SDK client với business configuration của adapter theo trách nhiệm nào?
Bạn thiết kế cấu hình các môi trường để không kết nối nhầm tài nguyên staging sang production ra sao?
Bạn xác định thứ tự ưu tiên environment variables và application properties đối với cloud starters như thế nào?
Bạn quyết định lúc nào cần tự tạo SDK client bean thay vì dùng auto-configuration như thế nào?
Bạn quản lý shutdown của SDK clients và HTTP connection pools cùng Spring ApplicationContext ra sao?
Bạn ngăn cloud auto-configuration kết nối production trong một unit test thiếu cấu hình như thế nào?
Bạn phân biệt lỗi dependency resolution với lỗi credentials hoặc network khi cloud client chạy ra sao?
Bạn xác minh property names thay đổi giữa hai phiên bản cloud integration starter như thế nào?
Bạn tránh đặt static access keys trong application.yml hoặc Docker image bằng biện pháp nào?
Bạn tổ chức profile dành riêng cho emulator mà không thay artifact phát hành như thế nào?
Bạn tách cloud adapters thành modules để hạn chế component scanning tạo bean không sử dụng như thế nào?
Bạn kiểm soát số SDK client instances được khởi tạo khi ứng dụng kết nối nhiều managed services ra sao?
Bạn chẩn đoán startup lỗi thiếu region hoặc project ID trước khi có network call bằng cách nào?
Bạn kiểm tra retry và HTTP connection pooling mặc định của SDK theo phiên bản đang dùng ra sao?
Bạn cấu hình proxy, timeout và endpoint override khác nhau giữa production và sandbox như thế nào?
Bạn thiết kế smoke test xác minh cloud client hướng đúng AWS account, Azure subscription hoặc GCP project ra sao?
Bạn quản lý nâng cấp cloud SDK tránh phá vỡ binary compatibility của Spring integration starter như thế nào?
Bạn phân biệt AWS IAM user credential với IAM role credentials được cấp tạm thời cho workload như thế nào?
Bạn xác định nguồn credentials được AWS SDK provider chain chọn trên local, CI và production như thế nào?
Bạn cấu hình Spring Boot trên EC2 hoặc ECS sử dụng role mà không lưu access key ra sao?
Bạn thiết kế workload identity cho ứng dụng Spring Boot trên EKS theo phương thức được hạ tầng hỗ trợ như thế nào?
Bạn sử dụng AWS STS AssumeRole khi ứng dụng cần truy cập tài nguyên ở account khác như thế nào?
Bạn thiết kế trust policy và resource policy cho truy cập cross-account theo least privilege ra sao?
Bạn giới hạn IAM policy để service chỉ đọc object thuộc prefix cho phép trong S3 như thế nào?
Bạn đánh giá rủi ro IAM wildcard permissions cho SQS, SNS hoặc S3 ở production ra sao?
Bạn xử lý credentials tạm thời hết hạn khi upload file hoặc chạy batch kéo dài như thế nào?
Bạn truy nguyên AWS AccessDenied đến identity, resource ARN và policy thiếu bằng cách nào?
Bạn phân biệt IAM identity policy với S3 bucket policy trong quá trình authorize ra sao?
Bạn phân quyền riêng publisher, consumer và operator trên cùng SQS queue theo nguyên tắc nào?
Bạn phân biệt Azure Managed Identity và service principal chứa client secret như thế nào?
Bạn sử dụng DefaultAzureCredential để tránh chọn nhầm developer credential trong production ra sao?
Bạn cấu hình Azure workload identity cho pod Kubernetes truy cập managed services theo điều kiện nào?
Bạn phân biệt Azure RBAC role assignment với quyền ở cấp resource và data plane ra sao?
Bạn thiết kế identity chỉ có quyền đọc đúng container Azure Blob Storage cần thiết như thế nào?
Bạn phân biệt tenant ID, subscription ID và resource scope trong cấu hình Azure SDK như thế nào?
Bạn xử lý Azure SDK lấy token thành công nhưng Blob Storage hoặc Service Bus vẫn trả 403 ra sao?
Bạn rotate service principal client secret hoặc certificate mà không làm gián đoạn ứng dụng như thế nào?
Bạn kiểm tra nguồn credential của DefaultAzureCredential mà không ghi token vào log ra sao?
Bạn phân biệt Google Application Default Credentials với service account key file tĩnh như thế nào?
Bạn sử dụng GCP Workload Identity Federation cho ứng dụng ngoài GCP để tránh JSON keys như thế nào?
Bạn cấu hình quyền cho Spring Boot chạy trên GKE gọi Cloud Storage và Pub/Sub ra sao?
Bạn chọn IAM role tối thiểu cho service account chỉ được publish Pub/Sub messages như thế nào?
Bạn phân biệt GCP project ID, project number và service account email trong cloud configuration ra sao?
Bạn xử lý lỗi quota project hoặc thiếu permission khi ADC đã được tạo thành công như thế nào?
Bạn ngăn việc phát tán JSON service account keys giữa các CI runners bằng kiểm soát nào?
Bạn sử dụng cloud audit logs để biết service account nào đã đọc một secret hoặc object ra sao?
Bạn so sánh AWS STS, Azure Entra workload identity và Google ADC về thời hạn token như thế nào?
Bạn thiết kế credential abstraction không làm lộ provider token vào business service ra sao?
Bạn phân biệt xác thực workload với phân quyền tài nguyên ở cả ba cloud providers như thế nào?
Bạn áp dụng OIDC federation cho pipeline CI thay cho long-lived cloud secrets theo cách nào?
Bạn xác minh một workload không được cấp quyền ngoài phạm vi sau khi thêm dịch vụ managed mới như thế nào?
Bạn xây dựng negative test chứng minh app không truy cập được tài nguyên của tenant khác ra sao?
Bạn lập quy trình thu hồi quyền khẩn cấp khi một workload identity bị xâm phạm như thế nào?
Bạn kiểm soát truy cập cross-account, cross-subscription và cross-project khi một ứng dụng phục vụ nhiều tenant ra sao?
Bạn xử lý rủi ro SDK lấy nhầm credentials từ máy developer trong integration tests như thế nào?
Bạn phân biệt object storage với filesystem khi xây tính năng upload file trong Spring Boot như thế nào?
Bạn lựa chọn Amazon S3, Azure Blob Storage hoặc Google Cloud Storage theo durability và locality như thế nào?
Bạn thiết kế object key, prefix và naming rules để cô lập dữ liệu nhiều tenant ra sao?
Bạn tổ chức một storage port để business layer thao tác metadata và content stream mà không biết provider như thế nào?
Bạn chọn streaming upload thay vì giữ cả file trong heap dựa trên kích thước và tải như thế nào?
Bạn xác thực kích thước file và content type trước khi lưu object lên cloud như thế nào?
Bạn thiết kế S3 multipart upload hoặc cơ chế block upload tương ứng cho file lớn ra sao?
Bạn dọn incomplete multipart uploads khi client bị ngắt giữa chừng bằng cơ chế nào?
Bạn xây dựng bước checksum validation sau upload để phát hiện dữ liệu bị hỏng như thế nào?
Bạn phân biệt ETag với checksum nội dung khi dùng multipart upload hoặc encryption ra sao?
Bạn thiết kế object metadata gồm tenant, business key và retention class theo nguyên tắc nào?
Bạn phân biệt object versioning với đặt version trong tên object để khôi phục dữ liệu ra sao?
Bạn xử lý optimistic concurrency khi hai clients cùng cập nhật một object như thế nào?
Bạn kiểm tra conditional update theo ETag hoặc generation ID trong từng cloud provider ra sao?
Bạn thiết kế presigned hoặc signed URL để client upload trực tiếp không qua backend như thế nào?
Bạn giới hạn signed URL về method, path, expiration và authorization theo cách nào?
Bạn ngăn upload trái phép file vượt dung lượng hoặc không đúng loại qua signed URL như thế nào?
Bạn đánh giá rủi ro dùng public bucket thay cho signed download URLs ra sao?
Bạn phân biệt provider-managed encryption keys và customer-managed keys cho object storage như thế nào?
Bạn cấu hình encryption và key access khi upload file nhạy cảm theo ràng buộc nào?
Bạn xử lý key rotation để object cũ vẫn giải mã được theo chính sách lưu trữ nào?
Bạn tổ chức lifecycle policies để xóa hoặc chuyển storage tier của object đã cũ như thế nào?
Bạn lựa chọn storage class hoặc access tier dựa trên tần suất download và chi phí retrieval ra sao?
Bạn thiết kế soft delete và retention lock khi object có yêu cầu kiểm toán như thế nào?
Bạn thực hiện yêu cầu xóa dữ liệu cá nhân khi versioning và backup còn giữ bản sao như thế nào?
Bạn phân biệt object không tồn tại và không đủ quyền đọc trong cách trả lỗi ra sao?
Bạn thiết kế pagination khi liệt kê hàng triệu objects mà không giữ tất cả trong bộ nhớ như thế nào?
Bạn xác định giới hạn khi dùng list objects thay cho truy vấn metadata trong database ra sao?
Bạn xử lý object event đến trước khi transaction lưu metadata commit như thế nào?
Bạn bảo đảm consistency giữa database metadata và cloud object khi không có transaction chung như thế nào?
Bạn triển khai compensation xóa object mồ côi khi ghi database thất bại sau upload ra sao?
Bạn đối soát objects và database references để phát hiện dữ liệu thiếu hoặc mồ côi như thế nào?
Bạn chống retry upload ghi đè một object mới hơn khi cùng key được tái sử dụng như thế nào?
Bạn streaming download với backpressure khi client nhận dữ liệu chậm như thế nào?
Bạn sử dụng range requests hoặc partial download để giảm tải với file lớn ra sao?
Bạn xác định khi nào nên dùng CDN trước object storage thay vì phục vụ file qua Spring Boot ra sao?
Bạn bảo vệ object key khỏi path traversal và truy cập cross-tenant bằng kiểm tra nào?
Bạn giám sát upload success, download latency, error rate và egress bytes theo storage adapter như thế nào?
Bạn thiết kế cùng bộ contract tests cho S3, Azure Blob và GCS để đánh giá độ tương đương như thế nào?
Bạn đánh giá giới hạn của emulator S3 khi mô phỏng hành vi riêng Azure Blob hoặc GCS như thế nào?
Bạn phân biệt queue và pub-sub topic trong hệ thống xử lý sự kiện bất đồng bộ ra sao?
Bạn lựa chọn Amazon SQS, Azure Service Bus hoặc Google Pub/Sub theo delivery semantics nào?
Bạn phân biệt SNS fan-out với SQS competing consumers trong kiến trúc AWS như thế nào?
Bạn tổ chức SNS-to-SQS subscriptions để mỗi microservice nhận bản sao event độc lập ra sao?
Bạn sử dụng SqsTemplate hoặc @SqsListener trong Spring Cloud AWS theo phiên bản đang dùng như thế nào?
Bạn phân biệt SQS visibility timeout với thời gian xử lý nghiệp vụ của consumer ra sao?
Bạn điều chỉnh visibility timeout khi một SQS message cần xử lý lâu hơn dự kiến như thế nào?
Bạn cấu hình SQS dead-letter queue và maxReceiveCount để tránh retry vô hạn ra sao?
Bạn thiết kế idempotent consumer cho SQS Standard khi message có thể được giao nhiều lần như thế nào?
Bạn lựa chọn SQS FIFO khi cần ordering và deduplication theo nghiệp vụ nào?
Bạn phân biệt FIFO message group ID và deduplication ID về trách nhiệm ra sao?
Bạn đánh giá ảnh hưởng của số message groups đến khả năng xử lý đồng thời trong SQS FIFO như thế nào?
Bạn chẩn đoán SQS listener không nhận message do queue URL, region hoặc IAM permission sai ra sao?
Bạn phân quyền SendMessage, ReceiveMessage và DeleteMessage theo producer hoặc consumer như thế nào?
Bạn đặt acknowledgment sau database commit để giảm lỗi xử lý trùng hoặc mất message như thế nào?
Bạn lựa chọn batch receive hoặc batch send của SQS theo throughput và giới hạn nào?
Bạn so sánh SQS long polling và short polling về latency và chi phí request như thế nào?
Bạn xử lý batch messages trong đó chỉ một phần tử lỗi mà không bỏ qua các phần tử khác ra sao?
Bạn dùng EventBridge khi cần routing events theo patterns và tích hợp với SaaS như thế nào?
Bạn so sánh EventBridge với SNS theo mức độ lọc sự kiện và quản lý contract như thế nào?
Bạn lựa chọn Azure Service Bus queue hoặc topic/subscription theo mô hình fan-out nào?
Bạn phân biệt Service Bus peek-lock và receive-and-delete về độ tin cậy xử lý ra sao?
Bạn quản lý lock duration và lock renewal khi consumer xử lý message lâu như thế nào?
Bạn sử dụng Service Bus dead-letter subqueue để lưu thông tin lỗi và replay như thế nào?
Bạn dùng Service Bus sessions khi cần thứ tự xử lý theo aggregate ID ra sao?
Bạn kiểm soát session lock và concurrency khi có nhiều Azure Service Bus consumers như thế nào?
Bạn phân biệt duplicate detection của Service Bus với business idempotency trong database ra sao?
Bạn thiết kế subscription filters cho Service Bus topic để tránh lộ event cross-tenant như thế nào?
Bạn xử lý trường hợp message đã complete nhưng downstream chưa xác nhận side effect như thế nào?
Bạn đánh giá khi nào Azure Event Hubs phù hợp hơn Service Bus cho streaming telemetry ra sao?
Bạn phân biệt Event Hubs partitions và consumer groups với Service Bus sessions như thế nào?
Bạn quản lý Event Hubs offset checkpoint sau khi xử lý một batch thành công như thế nào?
Bạn chọn số Event Hubs partitions dựa trên throughput và yêu cầu ordering ra sao?
Bạn tổ chức Google Pub/Sub topics và subscriptions để nhiều consumer groups nhận event như thế nào?
Bạn phân biệt Google Pub/Sub pull và push subscriptions theo bảo mật và network ra sao?
Bạn gia hạn Pub/Sub ack deadline khi xử lý message kéo dài theo cơ chế nào?
Bạn xử lý Pub/Sub redelivery do ack deadline hết hạn dù xử lý trước đó gần hoàn thành ra sao?
Bạn sử dụng Pub/Sub ordering keys để giữ thứ tự sự kiện của một thực thể như thế nào?
Bạn phân biệt dead-letter topic với retry policy của Pub/Sub subscription ra sao?
Bạn đánh giá giới hạn của Pub/Sub exactly-once delivery với tính đúng đắn của business side effects như thế nào?
Bạn giới hạn flow control của Pub/Sub subscriber để không làm cạn database connections ra sao?
Bạn phân biệt Pub/Sub message retention và acknowledgment deadline về khả năng replay như thế nào?
Bạn cấu hình quyền publisher và subscriber riêng bằng Google Cloud IAM ra sao?
Bạn chọn PubSubTemplate hoặc provider client tương ứng theo phiên bản Spring tích hợp GCP như thế nào?
Bạn xây dựng event contract chung cho SNS, Service Bus và Pub/Sub nhưng giữ provider-specific metadata ở đâu?
Bạn so sánh ordering guarantees của SQS FIFO, Service Bus sessions và Pub/Sub ordering keys như thế nào?
Bạn phân biệt SQS visibility timeout, Service Bus lock và Pub/Sub ack deadline khi thiết kế retry ra sao?
Bạn thiết kế consumer adapter tránh đưa lệnh ack của từng broker vào business service như thế nào?
Bạn xử lý poison message không thể phục hồi mà không gây tắc queue chính ra sao?
Bạn chặn duplicate business side effects khi một event được gửi bởi nhiều subscriptions như thế nào?
Bạn sử dụng transactional outbox khi database write và cloud message publish không chung transaction như thế nào?
Vì sao publisher acknowledgment không chứng minh consumer đã xử lý nghiệp vụ thành công?
Bạn thiết kế outbox dispatcher với polling hoặc CDC để tránh mất message sau database commit như thế nào?
Bạn phân biệt transport retry và business retry khi một downstream service bị lỗi ra sao?
Bạn áp dụng exponential backoff và jitter với lỗi rate limit hoặc mất kết nối như thế nào?
Bạn kiểm soát retry storm khi cloud broker tạm thời quá tải nhiều applications ra sao?
Bạn giảm tốc độ producer khi backlog tăng nhanh vượt khả năng xử lý của consumers như thế nào?
Bạn quản lý schema evolution khi đổi cloud broker nhưng consumer DTO còn ở phiên bản cũ ra sao?
Bạn truyền event ID, correlation ID và trace context qua cloud message headers như thế nào?
Bạn ngăn tenant metadata từ message chưa xác thực được dùng trực tiếp để quyết định quyền ra sao?
Bạn xây dựng quy trình replay dead-letter messages có phê duyệt và audit như thế nào?
Bạn tính chi phí request, throughput, retention và egress của một luồng cloud messaging ra sao?
Bạn lựa chọn managed relational database hoặc NoSQL theo transaction và access patterns nào?
Bạn phân biệt Amazon RDS hoặc Aurora với DynamoDB về mô hình dữ liệu và query ra sao?
Bạn sử dụng Spring Data JDBC/JPA với Amazon RDS theo cấu hình nào?
Bạn cấu hình TLS, HikariCP và credentials để kết nối Spring Boot tới RDS như thế nào?
Bạn dùng IAM database authentication cho RDS ở điều kiện engine hỗ trợ như thế nào?
Bạn xử lý RDS failover khi connection pool giữ connection tới node cũ ra sao?
Bạn truy cập DynamoDB thông qua AWS SDK và adapter Spring mà không lộ schema ra domain layer như thế nào?
Bạn chọn DynamoDB partition key và sort key dựa trên query patterns như thế nào?
Bạn xác định consistency và transaction capability của DynamoDB phù hợp với workflow nào?
Bạn dùng conditional writes trong DynamoDB để chống xử lý trùng event như thế nào?
Bạn đánh giá hot partition và chi phí read/write capacity của DynamoDB theo workload như thế nào?
Bạn phân biệt Azure SQL Database và Cosmos DB khi cần transactions hoặc scale ngang ra sao?
Bạn chọn JDBC/JPA với Azure SQL hay Cosmos DB client theo contract dữ liệu nào?
Bạn xác định Cosmos DB partition key tránh cross-partition queries tốn kém như thế nào?
Bạn sử dụng ETag của Cosmos DB để xử lý optimistic concurrency ra sao?
Bạn so sánh Cosmos DB consistency levels và yêu cầu read-after-write của ứng dụng như thế nào?
Bạn đánh giá cross-partition query về latency và request units của Cosmos DB ra sao?
Bạn xử lý Cosmos DB HTTP 429 bằng retry policy có giới hạn như thế nào?
Bạn phân biệt Cloud SQL, Firestore và Bigtable của Google Cloud theo access pattern nào?
Bạn kết nối Spring Boot tới Cloud SQL qua JDBC theo yêu cầu mạng và xác thực như thế nào?
Bạn lựa chọn private IP, cloud connector hoặc proxy cho Cloud SQL dựa trên bảo mật như thế nào?
Bạn xử lý Cloud SQL failover bằng connection validation và retry policy ra sao?
Bạn thiết kế Firestore transactions khi nhiều clients cập nhật cùng document như thế nào?
Bạn phân biệt Firestore collection path với document ID trong multi-tenant design như thế nào?
Bạn thiết kế Firestore indexes theo filter và orderBy để giảm lỗi query ra sao?
Bạn phân quyền service account chỉ truy cập dữ liệu Firestore cần thiết như thế nào?
Bạn so sánh DynamoDB, Cosmos DB và Firestore khi lưu trạng thái đơn hàng thay đổi liên tục như thế nào?
Bạn đánh giá rủi ro giả định mọi NoSQL managed services hỗ trợ transaction xuyên records giống nhau ra sao?
Bạn thiết kế repository port để thay database provider mà vẫn giữ business invariants như thế nào?
Bạn tổ chức schema migration khi chuyển managed relational database giữa các providers ra sao?
Bạn kiểm tra timezone, decimal precision và Unicode khi đồng bộ dữ liệu cross-cloud như thế nào?
Bạn xử lý replication lag và conflicts khi ứng dụng ghi dữ liệu nhiều regions như thế nào?
Bạn xác minh backup và point-in-time restore theo RPO/RTO của managed database như thế nào?
Bạn lập kế hoạch migration dữ liệu lớn tính đến downtime, checksum và egress cost ra sao?
Bạn phân biệt database credentials, workload identity và data-plane permissions như thế nào?
Bạn giới hạn số connections khi hàng trăm Spring Boot pods dùng chung SQL instance ra sao?
Bạn retry database transaction sau lỗi transient mà không lặp external side effects như thế nào?
Bạn dùng managed cache bên cạnh cloud database mà không làm dữ liệu stale quá thời hạn cho phép ra sao?
Bạn lựa chọn dịch vụ Redis managed của từng provider theo failover và network topology nào?
Bạn thiết kế fallback khi managed cache outage để tránh database thừa tải ra sao?
Bạn phân biệt secrets và non-secret config như region, endpoint hoặc project ID theo tiêu chí nào?
Bạn chọn AWS Secrets Manager hay Systems Manager Parameter Store cho các dạng bí mật như thế nào?
Bạn dùng AWS KMS trong kiến trúc mã hóa dữ liệu nhạy cảm mà vẫn bảo vệ key permissions như thế nào?
Bạn cung cấp secret AWS cho Spring Boot mà không hardcode trong source code ra sao?
Bạn rotate RDS password lưu trong Secrets Manager khi pool còn connection cũ như thế nào?
Bạn xác định TTL cache secret để cân bằng API cost và nguy cơ dùng secret đã thu hồi ra sao?
Bạn phân biệt Azure Key Vault secret, key và certificate theo mục đích quản lý nào?
Bạn tích hợp Spring Boot với Azure Key Vault theo starter hoặc SDK phù hợp phiên bản nào?
Bạn quản lý Key Vault permissions qua Azure RBAC hoặc chính sách hiện có như thế nào?
Bạn xử lý Key Vault throttling và private endpoint failures khi nhiều pods khởi động ra sao?
Bạn xoay vòng chứng chỉ TLS lấy từ Key Vault mà không dừng mọi requests như thế nào?
Bạn dùng Google Secret Manager với workload identity để nạp secrets vào Spring Boot ra sao?
Bạn version và alias secrets trong Google Secret Manager khi rolling deployment như thế nào?
Bạn điều phối refresh credentials và tái tạo database connection pool sau rotation như thế nào?
Bạn kiểm soát quyền đọc secrets ở AWS, Azure và GCP để không app nào được đọc mọi secret ra sao?
Bạn thiết kế audit log cho truy cập secrets mà không ghi lại giá trị vào log ra sao?
Bạn xử lý secret bị revoked khi application vẫn giữ giá trị cũ trong bộ nhớ như thế nào?
Bạn bảo vệ Actuator env, traces và exception messages khỏi lộ secrets ra sao?
Bạn phân biệt server-side encryption của storage với TLS và application-layer encryption như thế nào?
Bạn lựa chọn customer-managed key khi cần khả năng kiểm soát rotation hoặc revocation ra sao?
Bạn đánh giá hậu quả KMS key bị disable đối với dữ liệu đã mã hóa như thế nào?
Bạn thiết kế break-glass recovery cho keys và secrets với đủ audit như thế nào?
Bạn ngăn credentials bị đưa vào container image hoặc CI artifacts bằng công cụ nào?
Bạn dùng OIDC federation trong CI để deploy sang nhiều clouds mà không giữ long-lived keys ra sao?
Bạn kiểm tra workload identity policy không cấp quyền rộng ngoài ý muốn như thế nào?
Bạn kiểm thử URL hoặc resource name do người dùng cung cấp không thể truy cập bucket của tenant khác ra sao?
Bạn ghi nhận cloud audit logs phục vụ điều tra nhưng không lộ payload bí mật như thế nào?
Bạn thiết kế data residency khi object và database replicas trải qua nhiều cloud regions như thế nào?
Bạn tuân thủ yêu cầu xóa dữ liệu cá nhân ở cloud storage, backup và replicated datasets ra sao?
Bạn phân biệt shared responsibility của cloud provider với trách nhiệm của ứng dụng Spring Boot như thế nào?
Bạn xử lý thay đổi IAM policy gây HTTP 403 đồng loạt theo quy trình incident như thế nào?
Bạn xác định quota, API request size và rate limits trước khi thiết kế adapter như thế nào?
Bạn cấu hình retry budget của SDK để không khuếch đại sự cố provider khi có nhiều pods như thế nào?
Bạn phân biệt connect timeout, request timeout và business deadline của cloud operation như thế nào?
Bạn quản lý HTTP pooling và SDK lifecycle khi có nhiều cloud accounts và regions ra sao?
Bạn lựa chọn synchronous hoặc asynchronous cloud SDK trong Spring MVC và WebFlux như thế nào?
Bạn ngăn blocking I/O trên WebFlux event loop khi dùng SDK client đồng bộ ra sao?
Bạn quản lý cancellation khi HTTP client ngắt kết nối trong lúc SDK đang download object như thế nào?
Bạn phân biệt provider idempotency token với business idempotency key trong xử lý giao dịch như thế nào?
Bạn thiết kế bulkhead để storage outage không chiếm toàn bộ HTTP threads của ứng dụng ra sao?
Bạn dùng circuit breaker khi cloud API timeout mà không che giấu lỗi permanent như thiếu quyền ra sao?
Bạn thiết kế degraded mode khi object storage lỗi nhưng metadata vẫn sẵn sàng như thế nào?
Bạn phân biệt availability zone outage với region-wide outage trong managed cloud services ra sao?
Bạn phân loại retryable errors theo HTTP status và SDK exception types của từng provider ra sao?
Bạn ngăn API request quota bị tiêu hao bởi một lỗi retry lặp vô hạn như thế nào?
Bạn phân tích tác động của retry ở SDK, Spring Retry và broker redelivery cùng lúc như thế nào?
Bạn đặt application và managed service cùng region để giảm latency hoặc egress cost ra sao?
Bạn thiết kế private network connectivity cho cloud managed endpoints theo ràng buộc nào?
Bạn so sánh AWS VPC Endpoint, Azure Private Endpoint và Google Private Service Connect về bảo mật như thế nào?
Bạn chẩn đoán private DNS lỗi khác với authentication failure bằng cách nào?
Bạn xây dựng multi-region failover không giả định dữ liệu được đồng bộ ngay giữa các regions ra sao?
Bạn lựa chọn active-passive hoặc active-active theo database consistency và traffic patterns nào?
Bạn kiểm chứng business invariants khi dữ liệu được khôi phục từ region dự phòng như thế nào?
Bạn xây dựng metrics cho provider SDK latency, 4xx/5xx, throttling, retries và cost ra sao?
Bạn dùng Micrometer Observation để trace upload, message publish và database calls như thế nào?
Bạn truyền W3C trace context từ HTTP ingress qua cloud broker đến consumer như thế nào?
Bạn tránh metric cardinality cao khi object key hoặc tenant ID được dùng làm tag như thế nào?
Bạn tạo dashboard so sánh p95 latency và error rate theo cùng một business operation qua nhiều clouds ra sao?
Bạn phân biệt provider throttling với application connection pool exhaustion bằng tín hiệu nào?
Bạn đặt cảnh báo khi dead-letter backlog tăng nhanh nhưng producer vẫn báo thành công ra sao?
Bạn xác định SLO end-to-end từ lúc upload file đến khi downstream hoàn tất xử lý như thế nào?
Bạn liên kết audit logs của provider và application correlation IDs để truy nguyên một giao dịch ra sao?
Bạn giới hạn PII và secrets xuất hiện trong SDK logs, traces và error reports như thế nào?
Bạn ước lượng cost per transaction từ requests, storage, throughput và egress như thế nào?
Bạn tìm nguyên nhân hóa đơn cloud tăng khi request volume không thay đổi bằng những metrics nào?
Bạn thiết kế tenant quotas và cost alerts để tránh một workload chiếm toàn bộ budget ra sao?
Bạn phân biệt cloud quota limit với application misconfiguration khi API errors tăng như thế nào?
Bạn nâng cloud starters và SDK sau khi provider deprecate một API bằng quy trình nào?
Bạn kiểm tra breaking changes trước khi rolling upgrade nhiều Spring Boot services ra sao?
Bạn xây dựng test matrix theo JDK, Spring Boot và provider starter versions như thế nào?
Bạn unit test storage adapter bằng fake client thay vì cloud credentials thật như thế nào?
Bạn dùng cùng contract tests để kiểm chứng lưu, đọc, xóa object trên S3, Blob và GCS như thế nào?
Bạn sử dụng LocalStack cho AWS services trong phạm vi emulator hỗ trợ như thế nào?
Bạn dùng Azurite kiểm thử Azure Blob và phát hiện khác biệt với production ra sao?
Bạn lựa chọn GCP emulator hoặc fake service cho Pub/Sub và Firestore theo giới hạn nào?
Bạn thiết kế integration tests trên sandbox cloud account/subscription/project mà không truy cập production như thế nào?
Bạn đặt tên test resources để hai CI jobs không cùng xóa một queue hoặc bucket như thế nào?
Bạn sử dụng Testcontainers chạy emulator khi CI không có quyền truy cập cloud public như thế nào?
Bạn kiểm tra application không fallback sang production credentials khi emulator cấu hình thiếu ra sao?
Bạn mô phỏng cloud SDK trả 401, 403, 404, 409, 429 và 5xx để kiểm tra error mapping như thế nào?
Bạn kiểm thử credential expiry và refresh bằng test clock hoặc controllable provider như thế nào?
Bạn xác minh least-privilege IAM bằng negative integration tests ra sao?
Bạn kiểm thử expiration, path scope và method restrictions của signed URLs như thế nào?
Bạn thử hủy multipart upload giữa chừng và kiểm tra cleanup như thế nào?
Bạn xác minh content checksum sau khi streaming upload và download nhiều chunks ra sao?
Bạn kiểm thử SQS visibility timeout làm redelivery và đánh giá idempotency nghiệp vụ như thế nào?
Bạn mô phỏng Service Bus lock expiry trước complete và xác minh hành vi consumer như thế nào?
Bạn kiểm thử Pub/Sub ack deadline và redelivery mà không dựa trên Thread.sleep cố định ra sao?
Bạn kiểm tra ordering theo key khi dùng SQS FIFO, Service Bus sessions và Pub/Sub ordering keys như thế nào?
Bạn kiểm thử dead-letter flow của từng provider trước khi phát hành consumer ra sao?
Bạn mô phỏng database commit thành công nhưng publisher timeout để kiểm tra transactional outbox như thế nào?
Bạn phân biệt giá trị của test binder hoặc mock client với integration test dùng managed broker thật như thế nào?
Bạn mô phỏng managed SQL failover để phát hiện stale connections và retry sai như thế nào?
Bạn kiểm thử DynamoDB conditional write, Cosmos DB ETag và Firestore transaction theo cơ chế riêng như thế nào?
Bạn xác minh dữ liệu round-trip giữa managed databases khác provider bằng checksum như thế nào?
Bạn bảo vệ PII khi tạo synthetic data cho sandbox integration tests như thế nào?
Bạn thiết kế chaos test cho lỗi DNS hoặc network partition khi gọi cloud services ra sao?
Bạn quyết định test nào chạy trong pull request và test nào chạy định kỳ dựa trên cost như thế nào?
Bạn thu thập emulator logs và SDK traces khi integration test thất bại như thế nào?
Bạn triển khai infrastructure as code để tạo và dọn test resources một cách kiểm soát như thế nào?
Bạn bảo vệ test teardown khỏi vô tình xóa bucket hoặc topic production bằng guardrails nào?
Bạn đặt tiêu chí pass/fail khi thay provider adapter theo correctness, latency, security và cost như thế nào?
Nếu Spring Boot trên EKS lỗi AWS AccessDenied nhưng chạy local bình thường, bạn sẽ kiểm tra workload identity ra sao?
Nếu Azure Blob upload trả 403 dù lấy được token, bạn sẽ kiểm tra data-plane RBAC và network access như thế nào?
Nếu GCP Pub/Sub publisher báo permission denied trên project mới, bạn sẽ kiểm tra ADC và IAM ra sao?
Nếu AWS SDK chọn developer credentials trong CI, bạn sẽ điều chỉnh credential provider chain như thế nào?
Nếu upload file lớn gây OutOfMemoryError, bạn sẽ thay buffer-all bằng streaming như thế nào?
Nếu S3 multipart upload thất bại, bạn sẽ dọn incomplete parts và thiết kế retry an toàn ra sao?
Nếu signed URL truy cập được object ngoài phạm vi, bạn sẽ kiểm tra signing policy và prefix validation ra sao?
Nếu database ghi metadata thành công nhưng object upload thất bại, bạn sẽ thiết kế compensation hoặc retry ra sao?
Nếu object đã upload nhưng database rollback, bạn sẽ xử lý orphaned object bằng cơ chế nào?
Nếu SQS consumer tạo đơn hàng trùng do visibility timeout, bạn sẽ bổ sung inbox và deduplication như thế nào?
Nếu Service Bus message lock hết hạn trước khi handler complete, bạn sẽ thiết kế lock renewal ra sao?
Nếu Pub/Sub backlog tăng dù pods đã scale, bạn sẽ tìm bottleneck từ flow control và database như thế nào?
Nếu SNS fan-out thiếu một subscription, bạn sẽ kiểm tra resource policy và delivery status ra sao?
Nếu Event Hubs checkpoint trước commit làm mất event, bạn sẽ thay đổi transaction boundary như thế nào?
Nếu Pub/Sub ordering keys làm throughput giảm, bạn sẽ phân tích key distribution như thế nào?
Nếu poison message liên tục quay lại, bạn sẽ thiết kế retry cap và DLQ replay như thế nào?
Nếu DynamoDB hot partition bị throttling, bạn sẽ điều chỉnh partition strategy như thế nào?
Nếu Cosmos DB thường xuyên trả 429 sau truy vấn mới, bạn sẽ kiểm tra request units và indexes ra sao?
Nếu Firestore transaction xung đột do quá nhiều workers cập nhật cùng document, bạn sẽ giảm contention như thế nào?
Nếu Cloud SQL failover làm Spring connection pool giữ stale connections, bạn sẽ phục hồi ra sao?
Nếu rotate secret trong Key Vault làm ứng dụng mất kết nối, bạn sẽ cập nhật pool và rollback như thế nào?
Nếu AWS KMS key bị disable khiến object không đọc được, bạn sẽ xác định blast radius như thế nào?
Nếu Secret Manager secret bị revoked nhưng app vẫn dùng cache cũ, bạn sẽ điều chỉnh TTL và refresh như thế nào?
Nếu cloud SDK retry liên tục làm chi phí API tăng cao, bạn sẽ điều chỉnh retry budget và rate limiting như thế nào?
Nếu một cloud region outage xảy ra khi replication chưa hoàn tất, bạn sẽ quyết định failover dựa trên RPO ra sao?
Nếu nâng Spring cloud starter làm storage adapter lỗi, bạn sẽ chẩn đoán dependency graph ra sao?
Nếu integration test trên emulator xanh nhưng production lỗi message serialization, bạn sẽ thêm loại test nào?
Nếu cloud IAM policy bị thay đổi làm storage và messaging cùng lỗi 403, bạn sẽ dùng audit logs ra sao?
Nếu chuyển workflow từ AWS sang Azure, bạn sẽ so sánh IAM, object storage, messaging và transaction semantics như thế nào?
Nếu chi phí cross-cloud egress tăng sau deploy, bạn sẽ dùng tracing và network metrics để tối ưu ra sao?
Bạn xây dựng runbook khi workload identity, storage và messaging của một provider cùng suy giảm trong giờ cao điểm như thế nào?
