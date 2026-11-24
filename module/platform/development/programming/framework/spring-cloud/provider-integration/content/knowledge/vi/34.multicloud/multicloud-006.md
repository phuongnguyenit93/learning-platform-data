# Chuyển dữ liệu, danh tính, endpoint và quy trình vận hành

Khi chuyển một ứng dụng Spring Boot từ một cloud provider sang provider khác, phần khó nhất thường không nằm ở việc thay một SDK. Dữ liệu đã tích lũy, quyền truy cập của workload, địa chỉ dịch vụ, chính sách mạng và quy trình vận hành đều gắn với nền tảng hiện tại. Nếu chỉ đổi endpoint hoặc thay thư viện Spring Cloud, ứng dụng có thể khởi động thành công nhưng vẫn mất dữ liệu, thiếu quyền, gửi thông điệp sai hoặc không thể khôi phục khi có sự cố.

Trong phạm vi tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, cần xem việc chuyển đổi là một thay đổi có kiểm soát ở cả bốn lớp: dữ liệu, danh tính, endpoint và vận hành. Spring Cloud AWS, Spring Cloud Azure và các thư viện tích hợp Google Cloud giúp ứng dụng sử dụng dịch vụ tương ứng theo cách quen thuộc với Spring, nhưng không làm cho các dịch vụ của ba nhà cung cấp có cùng ngữ nghĩa hay cùng mô hình bảo mật.

## Mục tiêu

Sau bài học, bạn có thể:

- Lập danh mục dữ liệu và phụ thuộc dịch vụ trước khi chuyển provider.
- Chọn cách chuyển object, cơ sở dữ liệu và thông điệp phù hợp với yêu cầu nhất quán.
- Chuyển danh tính workload sang cơ chế cấp quyền gốc của cloud đích mà không nhúng khóa dài hạn vào ứng dụng.
- Cấu hình endpoint, vùng, mạng riêng và TLS qua cấu hình theo môi trường.
- Thiết kế cutover, kiểm chứng, rollback và giám sát sau chuyển đổi.
- Tách nghiệp vụ khỏi SDK của từng provider bằng các adapter có ranh giới rõ ràng.

## 1. Kiểm kê trước khi chuyển đổi

Trước tiên, hãy liệt kê mọi tài nguyên mà ứng dụng đọc, ghi hoặc phụ thuộc khi khởi động. Danh mục phải bao gồm cả tài nguyên được gọi trực tiếp từ mã Java và tài nguyên được truy cập gián tiếp qua Spring configuration, secret, biến môi trường hoặc hạ tầng mạng.

| Nhóm phụ thuộc | Cần ghi nhận | Câu hỏi khi chuyển đổi |
|---|---|---|
| Object storage | Bucket/container, key, metadata, version, lifecycle, mã hóa | Tên object, metadata và chính sách lưu trữ có được giữ nguyên không? |
| Cơ sở dữ liệu | Engine, schema, index, extension, transaction, replica | Kiểu dữ liệu, sequence và hành vi transaction có tương thích không? |
| Messaging | Queue/topic, retention, ordering, acknowledgement, DLQ | Provider đích có cùng mô hình giao nhận và retry không? |
| Danh tính | Role, service account, managed identity, policy | Workload nào được phép thao tác trên tài nguyên nào? |
| Secret và khóa | Secret store, key encryption, rotation, quyền giải mã | Ai được đọc secret và dữ liệu cũ được giải mã bằng khóa nào? |
| Endpoint và mạng | Region, DNS, private endpoint, firewall, proxy, TLS | Ứng dụng có thể kết nối tới đích từ đúng network không? |
| Vận hành | Log, metric, trace, alert, backup, runbook | Đội vận hành phát hiện và xử lý lỗi bằng tín hiệu nào? |

Tiếp theo, phân loại dữ liệu. Dữ liệu nguồn có thẩm quyền cần được chuyển và đối soát chặt chẽ. Dữ liệu có thể tái tạo như cache hoặc index tìm kiếm có thể được dựng lại. Thông điệp đang chờ xử lý cần một kế hoạch riêng vì trạng thái acknowledgement, thứ tự và thời hạn lưu trữ có thể khác giữa các broker.

Với mỗi nhóm dữ liệu, xác định ít nhất:

- Dung lượng hiện tại, tốc độ phát sinh dữ liệu mới và thời gian cho phép để chuyển.
- RPO (mức mất dữ liệu có thể chấp nhận) và RTO (thời gian khôi phục mục tiêu).
- Yêu cầu về vùng lưu trữ, mã hóa, lưu giữ, xóa và kiểm toán.
- Tiêu chí nghiệm thu có thể đo được, chẳng hạn số bản ghi, số object, tổng byte và checksum.
- Cách quay lại nguồn nếu đích không đạt tiêu chí sau cutover.

Không bắt đầu sao chép trước khi xác định hệ thống nào là nơi ghi dữ liệu có thẩm quyền ở từng giai đoạn. Hai nơi cùng nhận ghi mà không có chiến lược phân xử xung đột sẽ tạo ra trạng thái khó đối soát.

## 2. Chuyển dữ liệu theo từng loại

### 2.1. Object storage

AWS S3, Azure Blob Storage và Google Cloud Storage đều lưu object, nhưng cách biểu diễn quyền, version, metadata, tag, lifecycle, retention và mã hóa có điểm khác nhau. Một object chuyển thành công về nội dung vẫn có thể mất thuộc tính nghiệp vụ nếu chỉ sao chép byte.

Quy trình phù hợp thường có bốn giai đoạn:

1. **Sao chép ban đầu:** dùng công cụ truyền dữ liệu hoặc dịch vụ migration phù hợp với cặp nguồn/đích và quy mô dữ liệu. Với khối lượng lớn, không nên dùng request của ứng dụng Spring Boot để tải toàn bộ object về rồi tải lên lại; cách đó tiêu tốn tài nguyên ứng dụng và làm tăng rủi ro timeout.
2. **Bắt kịp thay đổi:** tiếp tục chuyển object mới, object được cập nhật và object bị xóa kể từ thời điểm bắt đầu sao chép. Có thể dùng inventory, nhật ký thay đổi hoặc cơ chế đồng bộ tăng dần mà dịch vụ nguồn hỗ trợ.
3. **Đối soát:** so sánh danh sách key, số lượng, kích thước, metadata cần giữ và checksum nội dung. Lưu manifest của lần chuyển để có thể chạy lại và điều tra object lỗi.
4. **Chuyển quyền ghi:** tại thời điểm cutover, dừng hoặc khóa ghi ở nguồn trong khoảng thời gian đã định, chuyển phần thay đổi cuối cùng, kiểm tra lại rồi chuyển ứng dụng sang đích.

Không nên mặc định ETag của object luôn là MD5 của nội dung. Với upload nhiều phần hoặc một số chế độ mã hóa, ETag có thể không mang ý nghĩa checksum nội dung. Hãy dùng checksum được provider hỗ trợ hoặc tự tính SHA-256 trong quy trình truyền khi yêu cầu toàn vẹn đòi hỏi điều đó.

Hãy lập bảng ánh xạ cho các thuộc tính không tương đương. Ví dụ, ACL của nguồn có thể phải chuyển thành IAM policy hoặc role assignment ở đích; lifecycle rule có thể phải viết lại; khóa mã hóa của provider nguồn không tự chuyển sang provider đích. Nếu dữ liệu được mã hóa bằng khóa do khách hàng quản lý, cần xác định quy trình giải mã tại nguồn và mã hóa lại bằng khóa đích, đồng thời giữ khả năng truy cập dữ liệu trong suốt thời gian chuyển.

### 2.2. Cơ sở dữ liệu

Chuyển cơ sở dữ liệu cần xử lý cả cấu trúc lẫn dữ liệu. Ngoài bảng và bản ghi, hãy kiểm tra kiểu dữ liệu, collation, timezone, sequence/identity, index, constraint, trigger, stored procedure, extension và mức cô lập transaction. Một schema hợp lệ ở engine nguồn chưa chắc chạy nguyên trạng trên engine đích.

Với dữ liệu lớn hoặc yêu cầu downtime thấp, quy trình thường gồm tải dữ liệu ban đầu rồi dùng replication hoặc Change Data Capture (CDC) để chuyển tiếp các thay đổi phát sinh. Công cụ migration phải hỗ trợ engine và topology thực tế. Spring Boot tiếp tục xử lý nghiệp vụ; không nên biến mỗi request của ứng dụng thành một bước sao chép cơ sở dữ liệu.

Trước cutover, kiểm tra số bản ghi theo bảng, khóa ngoại, constraint, tổng hợp nghiệp vụ và các truy vấn quan trọng. Nếu dùng sequence, xác nhận giá trị tiếp theo ở đích lớn hơn giá trị đã cấp ở nguồn để tránh cấp trùng khóa sau chuyển đổi.

Tránh dual-write trực tiếp vào hai cơ sở dữ liệu nếu không có cơ chế giải quyết giao dịch phân tán. Một request có thể ghi thành công ở nguồn nhưng thất bại ở đích, hoặc ngược lại. Nếu cần phát sự kiện để đồng bộ, cân nhắc Transactional Outbox: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction, sau đó một tiến trình phát sự kiện có retry và idempotency.

### 2.3. Queue, topic và sự kiện

Không coi việc chuyển message backlog giống như sao chép file. SQS/SNS, Azure Service Bus/Event Grid và Google Pub/Sub có khác biệt về acknowledgement, visibility hoặc ack deadline, ordering, retention, subscription, dead-letter và retry. Một message được xác nhận ở broker nguồn không đồng nghĩa message đó đã được xử lý ở broker đích.

Trước khi chuyển broker, xác định:

- Producer nào sẽ ngừng gửi vào nguồn và thời điểm ngừng.
- Consumer nào phải hoàn tất message đang xử lý trước khi dừng.
- Message chưa xử lý sẽ được drain, replay hay chuyển bằng công cụ migration.
- Khóa idempotency nào ngăn một sự kiện được áp dụng hai lần.
- Thứ tự sự kiện nào là yêu cầu nghiệp vụ và phạm vi ordering cần giữ.
- Cách chuyển message lỗi và dead-letter queue để không làm mất dấu vết điều tra.

Thiết kế consumer theo hướng idempotent ngay từ đầu. Khi một message được giao lại, consumer có thể nhận ra sự kiện đã xử lý và không lặp lại tác động nghiệp vụ. Nếu cần giữ thứ tự, hãy xác định khóa phân vùng hoặc session phù hợp với broker đích; không giả định thứ tự toàn cục được bảo toàn sau khi đổi provider.

## 3. Chuyển danh tính workload và quyền truy cập

Ứng dụng chạy trên cloud nên nhận danh tính từ môi trường thực thi. Không đóng gói access key, client secret hoặc service account key dài hạn trong file YAML, image container, mã nguồn hay biến môi trường được lưu cố định trong pipeline.

| Provider | Danh tính workload thường dùng | Cách ứng dụng nhận thông tin xác thực |
|---|---|---|
| AWS | IAM role gắn với EC2, ECS task hoặc workload trên EKS | AWS SDK credential provider chain lấy thông tin từ môi trường runtime hoặc cơ chế workload identity đã cấu hình |
| Azure | Managed Identity trên dịch vụ hỗ trợ hoặc Workload Identity cho AKS | Azure Identity credential chain, thường thông qua `DefaultAzureCredential` |
| Google Cloud | Service account gắn với workload hoặc Workload Identity Federation/Workload Identity cho GKE | Application Default Credentials (ADC) hoặc thư viện xác thực tương ứng |

Tên cơ chế có thể khác theo nền tảng chạy, nhưng nguyên tắc chung là danh tính được cấp từ runtime và quyền được quản lý bên ngoài ứng dụng. Ví dụ, một pod trên EKS có thể nhận IAM role qua IRSA hoặc EKS Pod Identity; workload trên AKS có thể dùng Workload Identity; workload trên GKE có thể ánh xạ Kubernetes service account sang Google service account. Chọn đúng cơ chế được hỗ trợ bởi phiên bản nền tảng và cấu hình cluster đang dùng.

Áp dụng quyền tối thiểu theo từng workload. Một service chỉ tải object nên có quyền đọc đúng bucket hoặc container cần thiết; không cấp quyền quản trị toàn bộ storage account. Tách role của ứng dụng khỏi role triển khai hạ tầng. Với môi trường production, giới hạn cả phạm vi tài nguyên, hành động, vùng và điều kiện truy cập khi provider hỗ trợ.

Trong ứng dụng Spring Boot, ưu tiên để thư viện SDK và starter tương ứng tự tìm credential từ chuỗi xác thực chuẩn của provider. Không tự đọc access key rồi tạo client thủ công nếu SDK đã hỗ trợ workload identity. Khi phát triển local, dùng profile hoặc công cụ đăng nhập dành cho nhà phát triển; không sao chép credential production về máy cá nhân.

### 3.1. Secret và khóa mã hóa

Secret như mật khẩu cơ sở dữ liệu, token bên thứ ba và private key nên được lưu trong dịch vụ quản lý secret phù hợp, chẳng hạn AWS Secrets Manager hoặc Parameter Store, Azure Key Vault và Google Secret Manager. Ứng dụng chỉ nhận quyền đọc đúng secret cần thiết. Việc đọc secret phải có audit log, cơ chế rotation và xử lý khi secret hết hạn.

Phân biệt secret với cấu hình thông thường. Region, tên bucket hoặc endpoint thường là cấu hình; password, token và private key là secret. Không đưa secret vào log, exception message, actuator environment endpoint hoặc metric label. Nếu secret được xoay vòng, kiểm tra xem connection pool và client có nạp lại giá trị mới hay cần restart.

Khóa mã hóa dữ liệu cần một kế hoạch riêng. Khóa của KMS, Key Vault hoặc Cloud KMS có policy, version và vòng đời riêng. Không xóa khóa nguồn chỉ vì bản sao dữ liệu đã xuất hiện ở đích; chỉ hủy hoặc thu hồi sau khi đã xác nhận dữ liệu, backup và bản lưu trữ cần thiết đều có thể giải mã theo chính sách lưu giữ.

## 4. Chuyển endpoint và cấu hình kết nối

Endpoint là một phần của hợp đồng triển khai. Ứng dụng có thể cần endpoint cho storage, database, broker, secret manager, API nội bộ và dịch vụ quan sát. Khi đổi provider, các giá trị này thường thay đổi cùng region, account/project, network và cách xác thực.

Đưa các giá trị có thể thay đổi theo môi trường ra khỏi mã nguồn. Ví dụ cấu hình ứng dụng:

```yaml
app:
  cloud:
    provider: ${CLOUD_PROVIDER:aws}
    region: ${CLOUD_REGION:ap-southeast-1}
  storage:
    container: ${STORAGE_CONTAINER:documents}
    endpoint: ${STORAGE_ENDPOINT:}
```

Đây là cấu hình thuộc ứng dụng; adapter của từng provider sẽ ánh xạ các giá trị này sang client và thuộc tính riêng của SDK tương ứng. Không giả định một thuộc tính `endpoint` chung có thể thay thế mọi cấu hình đặc thù như account URL của Azure, region/endpoint của S3 hoặc project và bucket của Google Cloud. Chỉ cấu hình endpoint tùy chỉnh khi có lý do rõ ràng, chẳng hạn private endpoint, proxy, emulator hoặc môi trường kiểm thử.

Khi dựng kết nối ở cloud đích, kiểm tra các lớp sau:

1. **Định tuyến mạng:** workload có route tới subnet hoặc network chứa dịch vụ không; security group, firewall, route table và egress policy có cho phép kết nối không?
2. **DNS:** tên endpoint phân giải thành địa chỉ dự kiến từ chính môi trường chạy ứng dụng không? Private endpoint thường cần private DNS zone và liên kết đúng network.
3. **TLS:** chứng thư có hợp lệ với hostname không; trust store của JVM có tin cậy CA cần thiết không; proxy có thay đổi chuỗi chứng thư không?
4. **Vùng và phạm vi tài nguyên:** region, project, subscription, account, bucket/container và database có khớp với cấu hình triển khai không?
5. **Timeout và giới hạn:** connect/read timeout, connection pool, request size, rate limit và quota có phù hợp với độ trễ và giới hạn của dịch vụ đích không?

Không tắt xác minh hostname hoặc TLS để khắc phục lỗi chứng thư trong production. Hãy sửa trust chain, DNS hoặc cấu hình proxy. Với endpoint riêng, kiểm thử từ đúng subnet hoặc cluster; một lần gọi thành công trên máy phát triển không chứng minh workload production có cùng đường mạng.

Nếu endpoint là API công khai mà client bên ngoài gọi vào, có thể chuyển hướng qua API gateway, load balancer hoặc DNS có health check. Giảm TTL trước thời điểm chuyển có thể giúp một số client cập nhật nhanh hơn, nhưng DNS cache ở resolver và ứng dụng vẫn có thể giữ địa chỉ cũ. Vì vậy, cần duy trì nguồn cũ trong thời gian chuyển tiếp và kiểm tra kết nối thực tế sau khi đổi route.

## 5. Giữ nghiệp vụ ổn định bằng adapter theo provider

Mã nghiệp vụ không nên phụ thuộc trực tiếp vào lớp client của S3, Azure Blob hoặc Google Cloud Storage. Hãy định nghĩa một cổng (port) theo nhu cầu nghiệp vụ, rồi triển khai adapter cho từng provider. Cổng nên chứa các thao tác mà ứng dụng thực sự cần, thay vì cố gắng mô phỏng toàn bộ API của mọi cloud.

Ví dụ cổng lưu tài liệu:

```java
public interface DocumentStorage {
    void upload(String key, InputStream content, long contentLength,
                Map<String, String> metadata);

    InputStream download(String key);

    void delete(String key);
}
```

Các adapter như `S3DocumentStorage`, `AzureBlobDocumentStorage` và `GcsDocumentStorage` chịu trách nhiệm ánh xạ thao tác sang SDK tương ứng. Adapter cũng xử lý khác biệt về metadata, phân trang, retry, checksum và lỗi provider. Nếu một nghiệp vụ cần tính năng chỉ có ở một provider, hãy biểu diễn rõ năng lực đó trong hợp đồng hoặc một cổng chuyên biệt; đừng âm thầm bỏ qua thuộc tính khi chuyển provider.

Có thể chọn adapter bằng cấu hình Spring:

```java
@Configuration
class DocumentStorageConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "app.storage", name = "provider",
                           havingValue = "aws")
    DocumentStorage s3Storage(S3Client client) {
        return new S3DocumentStorage(client);
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.storage", name = "provider",
                           havingValue = "azure")
    DocumentStorage azureStorage(BlobServiceClient client) {
        return new AzureBlobDocumentStorage(client);
    }
}
```

Đây là ví dụ về cách ghép adapter; các client phải được cấu hình bằng starter/SDK và credential chain phù hợp với phiên bản Spring Boot, Spring Cloud và thư viện provider của dự án. Adapter Google Cloud có thể được đăng ký theo cùng mẫu. Khi chạy, ứng dụng chỉ nhận một implementation cho mỗi cổng.

Giữ khác biệt cấu hình ở lớp tích hợp. Chẳng hạn, adapter AWS dùng `S3Client`, adapter Azure dùng `BlobServiceClient`, còn adapter Google Cloud dùng client của Cloud Storage. Không đưa các kiểu dữ liệu này vào controller hoặc service nghiệp vụ. Nhờ đó, việc chuyển provider chủ yếu tác động tới cấu hình, adapter và quy trình dữ liệu.

Tuy vậy, abstraction không xóa được khác biệt về dịch vụ. Spring Cloud giúp tích hợp với hệ sinh thái của provider, nhưng không đảm bảo queue, storage, database hoặc IAM có cùng hành vi. Hãy viết kiểm thử hợp đồng cho những hành vi mà nghiệp vụ phụ thuộc: ghi/đọc object, metadata, xử lý lỗi, retry, quyền truy cập và tính idempotent.

## 6. Lập kế hoạch cutover và rollback

Cutover là thời điểm chuyển hệ thống có thẩm quyền từ nguồn sang đích. Một kế hoạch tốt xác định rõ người chịu trách nhiệm, thời điểm, tiêu chí tiếp tục/dừng, thao tác thủ công và cách khôi phục.

Quy trình tham khảo:

1. **Chuẩn bị đích:** tạo tài nguyên, network, role, policy, secret, endpoint, backup và dashboard. Chạy smoke test từ workload thực tế.
2. **Chuyển dữ liệu ban đầu:** sao chép object, schema và dữ liệu cơ sở dữ liệu; lưu manifest và kết quả kiểm tra.
3. **Đồng bộ phần thay đổi:** bật replication/CDC hoặc cơ chế đồng bộ tăng dần. Theo dõi độ trễ và xác nhận backlog giảm về ngưỡng đã thống nhất.
4. **Kiểm thử trước cutover:** chạy truy vấn đối soát, kiểm tra quyền đọc/ghi, xử lý message thử nghiệm và xác nhận các chỉ số SLO.
5. **Khóa ghi hoặc chuyển producer:** đưa nguồn về chế độ chỉ đọc, dừng producer hoặc áp dụng hàng rào ghi để không phát sinh hai nguồn dữ liệu có thẩm quyền.
6. **Đồng bộ cuối và xác nhận:** chuyển phần thay đổi còn lại, so sánh số liệu, xác nhận consumer và trạng thái message.
7. **Chuyển traffic:** cập nhật cấu hình, feature flag, gateway hoặc DNS theo kế hoạch; triển khai canary trước khi mở rộng toàn bộ.
8. **Theo dõi:** kiểm tra lỗi xác thực, latency, throughput, retry, DLQ, quota, chi phí và các chỉ số nghiệp vụ trong cửa sổ giám sát.
9. **Kết thúc migration:** chỉ ngừng tài nguyên nguồn sau khi hết thời gian rollback, backup đã được kiểm tra và chủ sở hữu dữ liệu xác nhận nghiệm thu.

Định nghĩa tiêu chí dừng trước khi chạy. Ví dụ: không chuyển traffic nếu còn chênh lệch số bản ghi chưa giải thích, replication lag vượt ngưỡng, workload chưa đọc được secret, hoặc consumer đích làm tăng DLQ bất thường. Tiêu chí cần gắn với dữ liệu và SLO thực tế của hệ thống.

Rollback không chỉ là đổi lại DNS. Nếu đích đã nhận ghi sau cutover, nguồn có thể đã lỗi thời. Trước khi cho phép ghi ở đích, phải xác định cách quay lại: giữ nguồn chỉ đọc, thiết lập replication ngược, phục hồi từ log/outbox hay chấp nhận một khoảng downtime để đồng bộ. Nếu không có cách bảo toàn các thay đổi đã ghi ở đích, không được coi việc quay lại nguồn là an toàn.

Tránh duy trì hai nơi cùng ghi trong thời gian dài trừ khi ứng dụng có mô hình xung đột rõ ràng. Nếu cần chạy song song để so sánh, ưu tiên shadow read hoặc gửi bản sao request không tạo tác động nghiệp vụ. Mọi thao tác ghi thử phải có khóa idempotency và cơ chế ngăn phát sinh side effect trùng lặp.

## 7. Vận hành sau khi chuyển đổi

Sau cutover, giữ dashboard và cảnh báo theo cả góc nhìn ứng dụng lẫn provider. Một request lỗi có thể do ứng dụng, credential, DNS, network, quota hoặc dịch vụ managed. Log chỉ ghi `AccessDenied` là chưa đủ để điều tra; cần correlation ID, tên thao tác, provider, region và loại tài nguyên, đồng thời tuyệt đối không ghi token hoặc secret.

Các tín hiệu nên theo dõi gồm:

- **Tính sẵn sàng:** tỷ lệ request thành công, lỗi theo mã, health check và số lần kết nối thất bại.
- **Độ trễ:** latency p50/p95/p99 của storage, database, broker và các API phụ thuộc.
- **Thông lượng:** số request, byte truyền, số message nhận/gửi và tốc độ xử lý consumer.
- **Độ tin cậy dữ liệu:** replication lag, số bản ghi/object chưa đối soát, message retry và DLQ.
- **Bảo mật:** lỗi xác thực, lỗi phân quyền, thay đổi role/policy, truy cập secret và hoạt động quản lý khóa.
- **Tài nguyên và chi phí:** quota, throttling, connection pool, egress, request count, dung lượng và chi phí truyền liên vùng.

Đặt timeout rõ ràng cho client và dùng retry có giới hạn, exponential backoff cùng jitter. Chỉ retry lỗi tạm thời; lỗi xác thực hoặc lỗi dữ liệu thường cần xử lý cấu hình hay nghiệp vụ. Với thao tác ghi, bảo đảm idempotency trước khi bật retry. Circuit breaker và bulkhead có thể bảo vệ phần còn lại của ứng dụng khi dịch vụ managed suy giảm, nhưng ngưỡng phải dựa trên latency và SLO quan sát được.

Kiểm tra backup bằng cách khôi phục thử, không chỉ kiểm tra trạng thái job backup. Runbook cần chỉ ra cách xác minh danh tính, kiểm tra DNS/TLS, xem quota, xử lý DLQ, chuyển traffic và khôi phục dữ liệu. Sau vài ngày hoặc một chu kỳ tải cao, so sánh chi phí thực tế với dự toán, đặc biệt là phí egress, request, replication và lưu trữ phiên bản.

## 8. Ví dụ: chuyển kho tài liệu từ S3 sang Azure Blob

Giả sử một dịch vụ Spring Boot lưu tài liệu khách hàng trên S3. Mục tiêu là chuyển sang Azure Blob Storage trong khi API nghiệp vụ `upload`, `download` và `delete` vẫn giữ nguyên.

**Bước 1 – Tách hợp đồng nghiệp vụ.** Controller và service chỉ gọi `DocumentStorage`. Adapter S3 hiện tại chịu trách nhiệm truy cập bucket. Thêm adapter Azure Blob và kiểm thử hợp đồng để cả hai cùng đáp ứng các hành vi cần thiết.

**Bước 2 – Cấp danh tính đích.** Gắn Managed Identity hoặc Workload Identity cho workload trên Azure. Cấp role dữ liệu phù hợp ở phạm vi storage account hoặc container cần thiết, chẳng hạn quyền đọc/ghi blob theo đúng trách nhiệm của service. Cấu hình Azure SDK sử dụng credential chain của môi trường runtime; không thêm account key vào `application.yml`.

**Bước 3 – Chuẩn bị endpoint.** Cấu hình account URL của Blob Storage, container, region và private endpoint nếu kiến trúc yêu cầu. Từ pod hoặc máy chạy ứng dụng, xác minh DNS, route, TLS và quyền truy cập bằng một thao tác đọc/ghi thử trên container kiểm thử.

**Bước 4 – Chuyển dữ liệu.** Dùng công cụ migration phù hợp để sao chép object từ S3 sang Blob. Lưu manifest gồm key, kích thước, checksum, metadata và trạng thái. Ánh xạ ACL, tag, versioning, retention và encryption theo chính sách đích; ghi lại những thuộc tính không thể chuyển nguyên trạng.

**Bước 5 – Đối soát và cutover.** So sánh số object, tổng dung lượng, checksum và metadata quan trọng. Đồng bộ phần thay đổi cuối, khóa ghi ở S3, sau đó chuyển `app.storage.provider` sang `azure` qua cấu hình triển khai. Bật canary, theo dõi lỗi xác thực, latency, số lần retry và lỗi nghiệp vụ trước khi chuyển toàn bộ traffic.

**Bước 6 – Giữ khả năng phục hồi.** Trong cửa sổ rollback, giữ S3 ở chế độ chỉ đọc và bảo toàn backup/manifest. Nếu Azure đã nhận ghi mới, phải có phương án đồng bộ ngược hoặc khôi phục các thay đổi đó trước khi chuyển lại. Chỉ xóa bucket nguồn sau khi chủ sở hữu dữ liệu nghiệm thu và thời hạn lưu giữ cho phép.

Ví dụ này cho thấy thay đổi trong Spring Boot có thể tập trung ở adapter và cấu hình, nhưng công việc migration còn bao gồm dữ liệu, quyền, network, xác minh và vận hành. Nếu bỏ qua một trong các phần đó, ứng dụng có thể chạy nhưng hệ thống chưa thực sự chuyển đổi an toàn.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Ứng dụng chạy local nhưng lỗi quyền trên cloud | Local credential có quyền rộng; workload identity hoặc role binding chưa đúng | Kiểm tra principal thực tế của workload và policy ở đúng tài nguyên |
| Kết nối timeout sau khi chuyển endpoint | Private DNS, route, firewall hoặc egress chưa đúng | Kiểm tra phân giải DNS và kết nối từ chính runtime production |
| Object có đủ byte nhưng thiếu metadata | Chỉ sao chép nội dung, chưa ánh xạ metadata/tag/ACL | Đối chiếu manifest và kiểm tra thuộc tính ở provider đích |
| Dữ liệu database bị lệch sau cutover | CDC lag, ghi đồng thời hoặc thiếu đồng bộ cuối | Kiểm tra replication lag, hàng rào ghi và số liệu đối soát |
| Message bị xử lý lặp | Broker giao lại message hoặc consumer không idempotent | Dùng event ID/idempotency key và kiểm tra acknowledgement/DLQ |
| Rollback làm mất dữ liệu mới | Đích đã nhận ghi nhưng nguồn không được đồng bộ ngược | Xác định nguồn có thẩm quyền và kế hoạch bảo toàn write sau cutover |
| Chi phí tăng sau migration | Egress, request, replication hoặc lưu nhiều phiên bản | Phân tích billing theo dịch vụ, region và workload |

## 10. Checklist nghiệm thu

- [ ] Đã kiểm kê object, database, broker, secret, identity, endpoint và phụ thuộc vận hành.
- [ ] Đã xác định RPO, RTO, cửa sổ cutover, nguồn dữ liệu có thẩm quyền và tiêu chí rollback.
- [ ] Dữ liệu đã được chuyển, đồng bộ phần thay đổi và đối soát bằng số liệu có thể kiểm tra.
- [ ] Metadata, version, retention, encryption và dead-letter đã được ánh xạ hoặc ghi nhận ngoại lệ.
- [ ] Workload dùng danh tính runtime, quyền tối thiểu và secret manager phù hợp.
- [ ] Endpoint, DNS, route, TLS, timeout và quota đã được kiểm tra từ môi trường triển khai.
- [ ] Adapter của provider đích vượt qua kiểm thử hợp đồng và kiểm thử tích hợp cần thiết.
- [ ] Cutover có hàng rào ghi, canary, dashboard, người chịu trách nhiệm và điều kiện dừng.
- [ ] Rollback bảo toàn được dữ liệu phát sinh sau cutover.
- [ ] Backup, runbook, cảnh báo và chi phí đã được kiểm tra sau chuyển đổi.

Chuyển đổi đa đám mây thành công khi ứng dụng truy cập đúng dữ liệu bằng đúng danh tính, kết nối đúng endpoint và đội vận hành có thể quan sát, xử lý cũng như khôi phục hệ thống. Các thư viện Spring Cloud giúp chuẩn hóa cách tích hợp trong mã Spring Boot; kế hoạch dữ liệu, quyền và vận hành mới quyết định việc chuyển đổi có an toàn hay không.
