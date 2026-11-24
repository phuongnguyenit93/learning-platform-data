# Giới hạn của tính di động giữa các nhà cung cấp

Một ứng dụng Spring Boot có thể dùng cùng một interface để ghi object lên Amazon S3, Azure Blob Storage hoặc Google Cloud Storage. Điều đó giúp thay đổi implementation mà không sửa nhiều mã nghiệp vụ, nhưng **không có nghĩa ba dịch vụ có cùng hành vi**. Chúng khác nhau về mô hình tài nguyên, conditional write, versioning, consistency, identity, policy, giới hạn request, retry, event delivery, transaction, observability và cách tính phí. Một abstraction quá đơn giản có thể che mất khác biệt mà use case đang phụ thuộc; một abstraction quá rộng lại tạo ra nhiều tham số tùy chọn và hành vi không nhất quán.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua thư viện Spring Cloud tương ứng, từ danh tính/quyền, storage, messaging, dữ liệu và secret đến kiểm thử tích hợp. Trọng tâm bài này là xác định **tính di động thực sự nằm ở đâu, giới hạn ở đâu và cách thiết kế để thay provider có kiểm soát**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt portability ở cấp mã nguồn, API, semantics, dữ liệu, bảo mật, vận hành và chi phí.
- Giải thích vì sao một interface chung không bảo đảm các dịch vụ cloud tương đương.
- So sánh object storage, messaging và managed database giữa AWS, Azure và Google Cloud.
- Thiết kế **common contract + provider capability** mà không biến interface thành bản sao SDK.
- Chọn giữa lowest common denominator, provider-specific extension và nhiều adapter có chủ đích.
- Lập kế hoạch contract test, cloud test và migration rehearsal để phát hiện khác biệt trước khi chuyển production.

## 2. Portability có nhiều tầng

Khi nói “ứng dụng portable”, cần nói rõ **portable ở tầng nào**:

| Tầng | Có thể di động đến đâu? | Ví dụ giới hạn |
| --- | --- | --- |
| **Business logic** | Thường có thể giữ nguyên nếu hợp đồng use case ổn định | Quy tắc phát hành hóa đơn không phụ thuộc bucket |
| **Application port** | Có thể dùng chung phần semantics thực sự chung | `DocumentStore.put` không tự thể hiện versioning hoặc create-if-absent |
| **Framework/API** | Có thể dùng Spring abstraction nếu provider integration hỗ trợ | Template/listener/property khác nhau theo Spring Cloud family |
| **Service semantics** | Thường chỉ tương đương một phần | S3 version ID, Blob ETag, GCS generation không thể thay thế máy móc |
| **Identity và authorization** | Chỉ thống nhất được nguyên tắc và policy mục tiêu | IAM role, Azure Managed Identity/RBAC, Google ADC/IAM khác mô hình |
| **Network và deployment** | Một số phần dùng chung; topology vẫn đặc thù | PrivateLink, Private Endpoint, Private Service Connect và DNS khác nhau |
| **Reliability và operations** | Có thể chuẩn hóa mục tiêu; cách thực thi khác | Queue visibility, lock, ack deadline, DLQ và quota |
| **Cost và performance** | Không thể suy ra từ API giống nhau | Request pricing, egress, retrieval tier, replication và throughput khác nhau |

~~~mermaid
flowchart TD
    A[Business use case] --> B[Portable application contract]
    B --> C[Provider adapter]
    C --> D[AWS service]
    C --> E[Azure service]
    C --> F[Google Cloud service]
    D --> G[Provider-specific semantics]
    E --> G
    F --> G
    G --> H[Identity / network / reliability / cost]
~~~

**Mục tiêu thực tế** thường là giữ ổn định business logic và hợp đồng cần thiết, đồng thời cô lập những phần khác nhau trong adapter, configuration và deployment. Không phải mọi khác biệt đều đáng được trừu tượng hóa; một số khác biệt cần được giữ lại như capability rõ ràng.

## 3. Vì sao cùng một method không bảo đảm cùng một hành vi?

Giả sử cả ba adapter đều triển khai:

~~~java
public interface DocumentStore {
    void put(String key, byte[] content, String contentType);
}
~~~

Chữ ký này chỉ cho biết đầu vào và thời điểm method trả về. Nó **chưa nói**:

- Nếu object đã tồn tại thì ghi đè, tạo version mới hay trả conflict?
- Khi timeout, object có thể đã được lưu chưa?
- Khi method trả về, dữ liệu đã có thể đọc từ mọi vị trí chưa?
- Content type và metadata có giới hạn nào?
- Version ID, generation hoặc ETag nào được trả lại?
- Có thể tải theo range, stream hoặc resumable upload không?
- Encryption key, retention, legal hold và lifecycle được cấu hình ở đâu?
- Identity nào được dùng, quyền nào được kiểm tra và network đi qua đâu?

Một interface có thể làm các adapter **cùng gọi được**, nhưng không chứng minh các câu hỏi trên có câu trả lời giống nhau. Nếu application dựa vào một bảo đảm mà port không mô tả, code đang phụ thuộc vào hành vi ngầm của provider.

## 4. Object storage: S3, Azure Blob và Cloud Storage

### 4.1. Mô hình tài nguyên và thao tác

| Khái niệm | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Tài nguyên chứa object | Bucket | Storage account và container | Bucket |
| Object | Object/key | Blob name trong container | Object name |
| Java client tiêu biểu | AWS SDK v2 `S3Client` / `S3AsyncClient` | Azure SDK `BlobServiceClient`, `BlobContainerClient`, `BlobClient` | Google Cloud Java `Storage` |
| Ghi dữ liệu | `PutObject`, multipart API | Upload block/blob APIs | `Storage.create`, writer/resumable API |
| Version/concurrency | Versioning, conditional request và ETag theo API | Blob versioning, ETag/access conditions | Object versioning và generation/metageneration preconditions |
| Identity thường gặp | IAM role/credential chain | Managed Identity/DefaultAzureCredential + RBAC | ADC/workload identity/service account + IAM |

Các tên trên là những API/khái niệm tiêu biểu; cấu hình và khả năng chính xác phụ thuộc account, API, SDK và phiên bản. Ví dụ S3 **bucket/key**, Azure **account/container/blob**, GCS **bucket/object** có thể được ánh xạ vào một **object key** của ứng dụng, nhưng adapter vẫn phải biết resource locator tương ứng.

### 4.2. Versioning và conditional write không đồng nhất

Các provider có cơ chế bảo vệ cập nhật đồng thời, nhưng không nên xem chúng là một trường chung:

- **Amazon S3:** versioning có thể tạo version ID; API hỗ trợ conditional request theo các điều kiện phù hợp, ví dụ kiểm tra điều kiện tồn tại/ETag trong những thao tác được hỗ trợ.
- **Azure Blob:** ETag và access conditions có thể được dùng để thực hiện cập nhật có điều kiện; Blob versioning là một tính năng riêng.
- **Google Cloud Storage:** generation và metageneration preconditions có thể ngăn thao tác ghi đè khi generation không còn đúng; object versioning có semantics riêng.

**ETag không mặc nhiên là checksum nội dung** và không tương đương giữa các provider. Multipart upload, encryption và cách triển khai API có thể làm thay đổi ý nghĩa. Version ID, generation và ETag cũng không phải cùng một kiểu định danh.

Nếu nghiệp vụ yêu cầu “chỉ tạo tài liệu nếu chưa tồn tại”, hãy định nghĩa port theo **create-if-absent** và dùng precondition nguyên tử phù hợp trong từng adapter. Tránh mẫu **HEAD → PUT** rời rạc: hai request đồng thời có thể cùng thấy object chưa tồn tại rồi cùng ghi. Contract test phải chạy tình huống race để xác minh đúng bảo đảm.

### 4.3. Consistency và khả năng đọc sau ghi

Không suy ra consistency từ tên method `put`. Cần đọc tài liệu dịch vụ và API đang sử dụng cho các trường hợp: đọc object ngay sau ghi, liệt kê prefix, đọc metadata/version, ghi đồng thời và replication đa vùng. Một hệ thống chuyển provider có thể gặp lỗi nếu trước đây ứng dụng dựa vào thứ tự hoặc độ trễ xuất hiện trong list operation.

Thiết kế an toàn hơn:

- Dùng object key/operation ID ổn định để định vị dữ liệu.
- Nếu cần đọc ngay sau ghi, kiểm thử đúng API read-after-write và đường network/replication thực tế.
- Không dùng list prefix làm nguồn sự thật duy nhất cho trạng thái nghiệp vụ; lưu metadata trạng thái trong database nếu cần truy vấn nhất quán theo nghiệp vụ.
- Với cập nhật đồng thời, định nghĩa version/precondition và xử lý conflict thay vì dựa vào “last write wins” không được nêu rõ.

### 4.4. Upload lớn, streaming và giới hạn

Một method chung `put(byte[])` chỉ phù hợp với payload nhỏ đã được giới hạn. Các dịch vụ có API riêng cho multipart, block upload hoặc resumable upload; chúng khác nhau về:

- Kích thước tối đa, số phần, kích thước phần và số request.
- Cách khởi tạo, hoàn tất hoặc hủy upload session.
- Retry một phần dữ liệu và phục hồi sau khi process dừng.
- Checksum, metadata, điều kiện ghi và khả năng resume.
- Cách SDK sử dụng buffer, thread, connection và backpressure.

Nếu nghiệp vụ chỉ cần upload file nhỏ, một port đơn giản có thể đủ. Nếu cần resume hoặc streaming, hãy định nghĩa **upload session/stream contract** phù hợp hoặc cung cấp capability riêng. Đừng ép multipart và resumable upload vào một method `byte[]` rồi giữ toàn bộ file trong heap.

### 4.5. Metadata, encryption, retention và lifecycle

Các provider đều có metadata và encryption nhưng cấu hình không giống nhau:

| Yêu cầu | Cần so sánh |
| --- | --- |
| Metadata | User metadata, HTTP headers, custom metadata, giới hạn kích thước và quy tắc ký tự |
| Encryption at rest | Provider-managed key, customer-managed key, key rotation và quyền dùng key |
| Retention/legal hold | Object lock, immutability policy, retention duration và khả năng xóa |
| Lifecycle/tiering | Quy tắc chuyển tier, archive/retrieval, expiration và phí khôi phục |
| Replication | Phạm vi vùng, thời gian lan truyền, quyền và chi phí egress |
| Signed URL | Cách ký, danh tính được phép ký, thời hạn và giới hạn request |

Một interface chung chỉ nên chứa các tùy chọn có ngữ nghĩa rõ và có thể kiểm tra trên các provider cần hỗ trợ. Nếu legal hold là yêu cầu bắt buộc mà một adapter chưa thể bảo đảm, không được lặng lẽ bỏ qua cấu hình; phải từ chối cấu hình hoặc biểu diễn capability không hỗ trợ.

## 5. Messaging: cùng là gửi message nhưng semantics khác

| Khía cạnh | Amazon SQS/SNS | Azure Service Bus | Google Cloud Pub/Sub |
| --- | --- | --- | --- |
| Mô hình phổ biến | Queue, topic và subscription tùy dịch vụ | Queue, topic/subscription | Topic và subscription |
| Consumer | Receive/delete, visibility timeout | Receive/settle, lock duration | Pull/push, ack deadline |
| Giao nhận | Có thể giao lại; thiết kế idempotent | Lock, abandon/dead-letter và redelivery | Ack deadline, redelivery và dead-letter policy |
| Ordering/dedup | FIFO queue có các tính năng riêng | Session và các tính năng theo tier | Ordering key và tính năng theo cấu hình |
| Retry/dead-letter | Redrive policy/DLQ | Dead-letter queue | Retry và dead-letter topic/policy |
| API Java tiêu biểu | `SqsClient`, `SqsAsyncClient`, Spring Cloud AWS listener/template | Azure Service Bus client/processor và Spring Cloud Azure integration | Publisher/Subscriber, `ApiFuture`, Spring Cloud GCP integration |

Các semantics này không thể chuẩn hóa bằng một method **send(String queue, Object payload)**. Cần xác định:

- Khi publish trả thành công, message đã được broker chấp nhận hay consumer đã xử lý?
- Consumer ack khi nào? Nếu handler async, listener có chờ completion thật không?
- Message bị giao lại thì application xử lý trùng thế nào?
- Ordering cần trong phạm vi nào: toàn queue, session, partition hay ordering key?
- Poison message được retry bao nhiêu lần và đi đâu?
- Message attributes, size limit, schema, delay và scheduling có tương đương không?

Port publisher có thể chuẩn hóa hợp đồng “broker đã chấp nhận event” và event ID ổn định. Consumer adapter phải giữ semantics ack/lock của broker; application handler phải idempotent. Nếu một use case cần session ordering hoặc FIFO dedup, hãy biểu diễn capability đó rõ thay vì giả định mọi broker hỗ trợ giống nhau.

**Transactional outbox** có thể giúp ghi business state và event record trong cùng transaction database, sau đó publisher worker gửi tới broker. Nó không tạo transaction phân tán giữa database và queue, cũng không bảo đảm broker/consumer không bao giờ giao trùng; event ID và idempotency vẫn cần.

## 6. Managed database: repository chung có giới hạn

### 6.1. Database tương thích giao thức và datastore đặc thù

Với PostgreSQL managed trên **Amazon RDS**, **Azure Database for PostgreSQL** hoặc **Google Cloud SQL**, ứng dụng thường có thể giữ cùng JDBC driver, Spring Data JPA/JDBC và migration nếu phiên bản engine/tính năng tương thích. Nhưng vẫn phải cấu hình riêng:

- Endpoint, TLS, network/private access và DNS.
- Connection pool, failover, timeout và retry.
- Authentication bằng password, IAM/database identity hoặc cơ chế riêng.
- Engine version, extension, collation, parameter group/flags và migration.
- Backup, point-in-time recovery, replica, failover và maintenance window.

Với **DynamoDB**, **Azure Cosmos DB**, **Firestore** hoặc **Spanner**, mô hình query, partition key, transaction, consistency và index khác nhau. Một interface `Repository.save/findById` có thể cùng compile nhưng hiệu năng và semantics không giống nhau. Ví dụ query scan toàn bộ collection, transaction giới hạn phạm vi hoặc partition key không phù hợp có thể làm chi phí/latency tăng mạnh sau migration.

### 6.2. Không giả định transaction giống nhau

Transaction của JPA/JDBC thường gắn với database connection/engine. Transaction của NoSQL có thể giới hạn theo document, partition, entity group hoặc số operation. Không đưa `@Transactional` lên một service rồi kết luận object storage, message broker và mọi managed database cùng rollback khi một bước thất bại.

Nếu cần chuyển database:

1. Liệt kê query, index, unique constraint, isolation level và transaction đang được sử dụng.
2. Kiểm tra kiểu dữ liệu, timezone, numeric precision, collation và encoding.
3. Kiểm thử race condition và cập nhật đồng thời.
4. Chạy migration/reconciliation trên bản sao dữ liệu đại diện.
5. Đo query plan, latency, throughput và chi phí theo workload thực.

## 7. Identity, authorization và network không portable chỉ bằng config

Ba nền tảng có cách cấp danh tính và quyền khác nhau:

| Chủ đề | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Identity runtime phổ biến | IAM role, credential chain, workload identity | Managed Identity, service principal hoặc credential chain Azure | ADC, service account, Workload Identity Federation |
| Authorization | IAM policy, resource policy, bucket/queue policy | Azure RBAC, resource/data-plane role và policy | IAM role/binding ở project/resource |
| Scope | Principal, action, resource, condition | Principal, role, scope và data action | Principal, role, resource hierarchy |
| Network riêng | PrivateLink/VPC endpoint và VPC networking | Private Endpoint/VNet/DNS | Private Service Connect/VPC/DNS |
| Secret/key | Secrets Manager, KMS | Key Vault, Key Vault Managed HSM | Secret Manager, Cloud KMS |

Một port không thể làm cho ba policy language trở thành một. Có thể chuẩn hóa **ý định quyền** ở cấp ứng dụng (ví dụ workload chỉ ghi đúng tài liệu thuộc service này) rồi triển khai policy riêng theo provider. Cần kiểm tra cả permission trên dịch vụ và permission dùng encryption key; quyền ghi object có thể vẫn thất bại nếu không được dùng key.

Tách hai quyết định:

- **Business authorization:** caller có quyền xem/tạo tài liệu hoặc phát hành invoice không? Kiểm tra trong application/security boundary.
- **Workload authorization:** service account/role của ứng dụng có quyền gọi bucket, queue, database hoặc secret không? Kiểm tra trong IAM/RBAC và cấu hình hạ tầng.

Khi chuyển cloud, cần xác minh DNS, TLS, outbound rules, proxy, private endpoint, certificate trust, egress và endpoint resolution. Một cấu hình endpoint cùng tên trong YAML không bảo đảm cùng topology hoặc trust boundary.

## 8. Reliability, retry và kết quả không xác định

Một thao tác có thể thất bại trước khi gửi request, bị từ chối bởi service, hoặc đã được thực hiện nhưng response bị mất. Các provider có mã lỗi và retry guidance khác nhau. Adapter cần phân loại theo **ý nghĩa**, không chỉ so status code.

| Nhóm lỗi | Hành vi ứng dụng cần cân nhắc |
| --- | --- |
| Input không hợp lệ | Không retry; trả lỗi validation |
| Workload thiếu quyền | Không retry vô hạn; sửa identity/policy |
| Resource không tồn tại | Kiểm tra tên, project/account, region và provisioning |
| Conflict/precondition | Đọc trạng thái/version hoặc xử lý conflict nghiệp vụ |
| Throttling/quota/temporary service error | Retry có backoff, jitter, deadline và giới hạn concurrency |
| Timeout sau side effect | **Outcome unknown**; reconcile trước khi retry nếu cần |

Đối với object storage, một key ổn định giúp hướng retry về cùng tài nguyên nhưng chưa đủ để chống ghi đè hoặc bảo đảm create-once. Đối với messaging, broker có thể đã nhận event dù producer mất response; consumer cần deduplicate theo event ID. Với database, retry transaction có thể chạy lại một phần logic hoặc gặp unique constraint khác với lần đầu.

Không để retry ở SDK, Spring Retry, Reactor và broker nhân lên không kiểm soát. Xác định **retry budget tổng**, timeout budget, loại lỗi được retry và điều kiện idempotency. Khi chuyển provider, chạy thử fault injection để kiểm chứng mã lỗi thực tế và số lần request được gửi.

## 9. Capability model: giữ phần chung, bộc lộ phần khác

Một port tối thiểu có thể phù hợp với use case đơn giản:

~~~java
public interface DocumentStore {
    StoredDocument put(DocumentWrite request);
    Optional<DocumentContent> get(String objectKey);
}
~~~

Nhưng nếu use case cần tạo mới không ghi đè, trả version, signed URL hoặc multipart session, không nên thêm một loạt tham số nullable vào cùng một method. Có thể biểu diễn **capability** tách biệt:

~~~java
public interface ConditionalDocumentStore {
    StoredDocument createIfAbsent(DocumentWrite request);
}

public interface VersionedDocumentStore {
    StoredDocument putNewVersion(DocumentWrite request);
}

public interface TemporaryDownloadLinkProvider {
    URI createReadLink(String objectKey, Duration validFor);
}
~~~

Đây là ví dụ thiết kế, không phải mọi provider đều hỗ trợ mọi capability với cùng bảo đảm. Khi khởi tạo adapter, ứng dụng có thể:

- Chọn implementation đáp ứng capability bắt buộc và **fail fast** nếu thiếu.
- Dùng interface cơ bản cho use case portable và interface capability riêng cho use case chuyên biệt.
- Trả về kết quả capability rõ ràng nếu ứng dụng chấp nhận fallback có chủ đích.

Tránh kiểm tra kiểu `instanceof S3DocumentStore` trong application service hoặc để business logic biết tên provider. Capability phải được xác định ở wiring/configuration hoặc application boundary; adapter thực hiện API provider cụ thể.

### 9.1. Lowest common denominator có thể quá thấp

Chỉ giữ phần giao nhau giữa các dịch vụ giúp portable nhưng có thể bỏ các tính năng quan trọng: versioning, conditional write, ordered messaging, transactions, retention, query hoặc identity. Nếu use case thật sự cần những tính năng đó, có ba lựa chọn:

1. **Chấp nhận giới hạn chung:** thiết kế business process chỉ dùng bảo đảm thấp nhất nhưng vẫn đáp ứng yêu cầu.
2. **Capability có tên:** use case cần capability và hệ thống chỉ triển khai ở provider đã hỗ trợ; deployment không tương thích phải từ chối.
3. **Provider-specific workflow:** giữ một phần use case/adapter riêng khi semantics khác nhau quá lớn để che bằng interface chung.

Không nên tuyên bố “đa cloud” nếu chỉ có thể chạy ở một provider mà không có kiểm tra capability. Cũng không nên bỏ tính năng có giá trị chỉ để đạt một interface giống nhau trên giấy.

## 10. Ví dụ chọn contract cho object storage

Giả sử yêu cầu là **lưu tài liệu mới, không ghi đè tài liệu đã có**. Contract cần diễn đạt điều kiện nguyên tử:

~~~java
public interface ImmutableDocumentStore {
    StoredDocument createIfAbsent(DocumentWrite request)
        throws DocumentAlreadyExistsException;
}
~~~

Adapter AWS có thể dùng cơ chế conditional write phù hợp với API S3 và cấu hình bucket/versioning hiện tại; adapter Azure dùng access condition/ETag phù hợp; adapter GCS dùng generation precondition. Từng adapter phải kiểm tra cách SDK biểu diễn điều kiện, loại lỗi conflict và trường hợp timeout sau khi ghi. Nếu API/provider configuration không đáp ứng contract, không được fallback sang một chuỗi kiểm tra không nguyên tử rồi vẫn trả “đã tạo duy nhất”.

Kết quả nên mang thông tin ứng dụng thực sự cần:

~~~java
public record StoredDocument(
    String objectKey,
    Optional<String> providerVersion
) {}
~~~

Chỉ dùng `providerVersion` nếu ứng dụng hiểu nó là một **opaque token** dùng lại với đúng adapter đã tạo ra. Nếu cần so sánh/version semantics xuyên provider, định nghĩa một **application revision** do ứng dụng quản lý thay vì giả định S3 version ID, Azure version ID và GCS generation có thể so sánh trực tiếp.

## 11. Migration là bài toán dữ liệu và vận hành, không chỉ đổi adapter

Một kế hoạch chuyển S3 sang Azure Blob hoặc GCS cần xem ít nhất:

1. **Inventory:** bucket/container/object count, dung lượng, kích thước object, metadata, version, retention, lifecycle, encryption, access log và traffic pattern.
2. **Mapping:** bucket/key → account/container/blob hoặc project/bucket/object; metadata, content type, custom headers, tags và version semantics.
3. **Identity/network:** workload identity mới, IAM/RBAC, key permissions, private endpoint, DNS, TLS và egress.
4. **Data movement:** công cụ copy, tốc độ, checksum, retry, version/metadata preservation, chi phí egress và thời gian đồng bộ thay đổi mới.
5. **Application:** adapter, config, timeout, retry, streaming, signed URL, error mapping và capability checks.
6. **Verification:** số lượng object, checksum/size, metadata, quyền đọc/ghi, conditional write và các use case quan trọng.
7. **Cutover:** freeze/write pause hoặc dual-write có kiểm soát, routing, rollback, xử lý dữ liệu phát sinh trong cửa sổ chuyển đổi.
8. **Retirement:** chỉ xóa nguồn khi đối soát, retention, backup, audit và thời gian rollback đều đạt tiêu chí.

~~~mermaid
flowchart TD
    A[Inventory nguồn] --> B[Mapping semantics + capability]
    B --> C[Copy dữ liệu / đồng bộ thay đổi]
    C --> D[Đối soát checksum + metadata + quyền]
    D --> E{Smoke test và business test đạt?}
    E -->|Không| F[Giữ nguồn, sửa mapping hoặc rollback]
    F --> C
    E -->|Có| G[Cutover traffic có kiểm soát]
    G --> H[Theo dõi và giữ cửa sổ rollback]
    H --> I[Retire nguồn theo policy]
~~~

**Dual-write** có thể tạo dữ liệu lệch nếu một provider ghi thành công và provider kia thất bại. Nếu dùng, cần operation ID, trạng thái từng đích, retry/reconciliation và quy tắc xác định nguồn sự thật. Không chỉ thêm hai adapter rồi gọi cả hai trong một method mà không có workflow bù trừ.

## 12. Kiểm thử portability bằng contract và ma trận provider

Một bộ test dùng chung có thể xác minh hợp đồng **DocumentStore**, nhưng mỗi adapter cần test bổ sung cho semantics riêng:

| Nhóm test | Hợp đồng chung | Provider-specific |
| --- | --- | --- |
| Put/get | Nội dung, content type và key đúng | Metadata/header limits, encoding, checksum |
| Create-if-absent | Không ghi đè khi object đã tồn tại | S3 conditional request, Blob access condition, GCS generation precondition |
| Versioning | Ứng dụng nhận revision hợp lệ | Version ID, Blob version, generation semantics |
| Concurrent write | Conflict được phát hiện theo contract | Race condition và mã lỗi thực tế |
| Timeout | Không báo thành công sai khi outcome unknown | SDK retry, request ID, service behavior |
| Authorization | Workload thiếu quyền không thể ghi | IAM policy, Azure RBAC, Google IAM |
| Large object | Không vượt memory budget | Multipart/block/resumable upload |
| Delete/retention | Không xóa khi policy nghiệp vụ cấm | Object lock, immutability, retention và lifecycle |

Kiểm thử nên có ba mức:

- **Unit test:** application service dùng fake port, không cần cloud credentials.
- **Adapter/contract test:** mock SDK để kiểm tra mapping và lỗi; emulator (LocalStack, Azurite hoặc môi trường GCP phù hợp) cho luồng tích hợp.
- **Cloud test thật:** identity, policy, network, quota, conditional write, retention, failover và semantics mà emulator không mô phỏng đủ.

Không chỉ chạy cùng test suite và đếm “pass” trên ba cloud. Cần có ma trận **capability × provider × phiên bản × cấu hình**; test chỉ đánh dấu hỗ trợ nếu môi trường triển khai thật đáp ứng bảo đảm. Mọi capability không hỗ trợ phải được ghi rõ và fail fast khi use case yêu cầu.

## 13. Đánh đổi về hiệu năng và chi phí

Một adapter portable có thể làm tăng số lần gọi API nếu phải kiểm tra trạng thái trước/sau thao tác. Tải file qua ứng dụng thay vì upload trực tiếp có thể làm tăng bandwidth và chi phí compute. Chuyển provider cũng có thể thay đổi:

- **Request pricing:** PUT/GET/LIST, transaction, operation batch, message publish/receive/ack.
- **Storage pricing:** tier nóng/lạnh/archive, minimum storage duration và phí retrieval.
- **Network pricing:** egress, cross-region, private connectivity, interconnect và traffic qua NAT.
- **Performance:** latency vùng, throughput, request rate, partition/hot key, connection pool và concurrency.
- **Operations:** backup, replication, monitoring, key management, log retention và support plan.

Không thể kết luận provider rẻ hơn chỉ bằng giá mỗi GB hoặc một benchmark local. Hãy xây workload đại diện: kích thước object, read/write ratio, concurrency, số lần list/query, retention, vùng dữ liệu và lượng egress. Đo **p50/p95/p99 latency**, lỗi/throttling, chi phí theo operation và chi phí di chuyển dữ liệu.

## 14. Các anti-pattern làm portability kém đi

| Anti-pattern | Vì sao nguy hiểm | Cách thay thế |
| --- | --- | --- |
| Interface `CloudStorage` với hàng chục tham số nullable | Hợp đồng mơ hồ, mỗi adapter bỏ qua trường khác nhau | Port theo use case + capability rõ |
| Dùng tên chung nhưng semantics khác | Method trả thành công sai bảo đảm | Định nghĩa precondition, version, ack và outcome |
| Expose SDK request/exception ra application | Business layer phụ thuộc provider | Map ở adapter, giữ root cause nội bộ |
| Chỉ test bằng mock | Không thấy IAM, network, quota, consistency và API behavior | Emulator + cloud smoke/contract tests |
| Hard-code bucket/account/project vào business service | Mỗi environment/provider phải sửa code | Configuration và adapter sở hữu resource mapping |
| Coi mọi 403 là lỗi caller | Workload identity có thể thiếu quyền | Phân biệt business authorization và cloud authorization |
| Dual-write mà không reconciliation | Hai provider có thể lệch dữ liệu | Operation state, outbox/reconciliation, cutover có kiểm soát |
| Chọn lowest common denominator bất kể yêu cầu | Mất tính năng cần thiết hoặc bảo đảm yếu hơn | Capability có tên và kiểm tra hỗ trợ |
| Chỉ so sánh API, bỏ qua chi phí/network | Migration chạy được nhưng không đáp ứng SLA/chi phí | Workload benchmark và TCO theo vùng/tier |

## 15. Quy trình ra quyết định cho một use case

Trước khi chọn adapter hoặc cam kết hỗ trợ nhiều cloud, ghi lại:

1. **Business outcome:** người dùng cần điều gì và điều gì phải luôn đúng?
2. **Required semantics:** create/update, version, consistency, ordering, ack, transaction, retention và idempotency.
3. **Required capabilities:** những tính năng bắt buộc và những tính năng có thể bỏ.
4. **Provider mapping:** API, identity, policy, network, limits và error mapping của từng cloud.
5. **Failure model:** timeout trước/sau side effect, retry, conflict, quota và reconciliation.
6. **Operational model:** metric, log, trace, alert, backup, restore và shutdown.
7. **Cost/performance:** workload benchmark, egress, request, storage tier và migration cost.
8. **Test evidence:** contract, emulator, cloud smoke và migration rehearsal.

Chỉ sau khi hoàn tất ma trận này mới nên tuyên bố một use case **portable giữa AWS, Azure và Google Cloud**. Nếu provider chỉ hỗ trợ một phần, thể hiện điều đó trong deployment/capability configuration và từ chối startup khi cấu hình yêu cầu vượt khả năng adapter.

## 16. Bài tập thực hành

**Bài tập 1 — Object storage portability.** Một ứng dụng cần upload PDF, tải theo range, versioning và không cho ghi đè. Hãy lập ma trận S3/Blob/GCS cho từng yêu cầu. Chỉ ra phần nào có thể đưa vào `DocumentStore`, phần nào cần capability riêng và phần nào phải giữ provider-specific.

**Bài tập 2 — Messaging semantics.** Một consumer xử lý thanh toán chỉ được thực hiện business effect một lần theo event ID. So sánh visibility timeout của SQS, lock của Service Bus và ack deadline của Pub/Sub. Thiết kế idempotency ở database và quy trình dead-letter; giải thích vì sao một interface `receive/ack` không tự đảm bảo exactly-once.

**Bài tập 3 — Managed database.** Ứng dụng dùng PostgreSQL trên RDS muốn chuyển sang Cloud SQL. Liệt kê những phần có thể giữ nguyên (JDBC/JPA, entity, repository) và những phần phải kiểm tra (extensions, version, network, IAM auth, TLS, pool, failover, backup, parameter settings).

**Bài tập 4 — Conditional create.** Hai instance cùng ghi một object key. Thiết kế contract `createIfAbsent` và mapping precondition cho S3, Azure Blob, GCS. Viết test chạy đồng thời và xác định chỉ một thao tác được phép thành công.

**Bài tập 5 — Capability check.** Một ứng dụng yêu cầu signed URL và retention lock. Hãy thiết kế capability interface, biểu diễn adapter nào đáp ứng trong cấu hình deployment, và hành vi startup nếu provider đã chọn không đáp ứng một capability bắt buộc.

**Bài tập 6 — Migration rehearsal.** Lập kế hoạch chuyển 10 TB object từ S3 sang Azure Blob hoặc GCS. Bao gồm inventory, copy, checksum, metadata/version mapping, dual-write hoặc write freeze, cutover, rollback, egress cost và điều kiện được phép retire nguồn.

**Bài tập 7 — Đánh giá tuyên bố portability.** Một nhóm nói “chỉ cần thay Spring Cloud starter là chạy được trên cả ba cloud”. Hãy yêu cầu bằng chứng ở tầng API, semantics, IAM/RBAC, network, reliability, observability, performance, cost và integration tests trước khi chấp nhận tuyên bố.

## 17. Ghi nhớ

- **Portability không phải một thuộc tính nhị phân.** Business logic và một phần application contract có thể dùng chung, trong khi service semantics, identity, network, reliability và cost vẫn khác nhau.
- **Cùng method signature không bảo đảm cùng semantics.** Versioning, conditional write, consistency, streaming, message ack và transaction phải được mô tả và kiểm thử rõ.
- Dùng **common contract** cho nhu cầu thật sự chung; dùng **capability** hoặc provider-specific workflow cho tính năng đặc thù. Không ép mọi cloud vào một interface quá rộng hoặc quá yếu.
- **Identity, IAM/RBAC, network, retry và observability** cần cấu hình/kiểm chứng riêng cho từng provider; không được nhầm quyền workload với quyền người dùng cuối.
- Migration cần inventory, mapping, copy, reconciliation, smoke test, cutover và rollback. **Đổi adapter không tự chuyển dữ liệu hoặc policy.**
- Chỉ cam kết portable khi có **contract test + cloud test + workload/cost evidence** trên các provider và phiên bản triển khai thực tế.
