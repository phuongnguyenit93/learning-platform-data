# Compatibility giữa manager và worker khi triển khai Spring Batch

## 1. Vì sao compatibility quyết định khả năng mở rộng?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, chúng ta học mở rộng Spring Batch cho workload dữ liệu lớn qua **multi-threaded step**, **parallel steps**, **partitioning** và các mô hình xử lý phân tán; đồng thời đo nút thắt, giữ thread safety, bảo đảm retry/restart và chọn kiến trúc theo năng lực hạ tầng.

Khi manager và worker chạy trong các tiến trình hoặc máy khác nhau, việc scale không chỉ là tăng số replica. Các tiến trình phải hiểu **cùng một hợp đồng xử lý**: thông điệp điều phối, tên step, định dạng dữ liệu, cơ chế lưu trạng thái và quy tắc giao dịch. Nếu thay đổi riêng một bên, job có thể chờ phản hồi mãi, đọc sai dữ liệu, lỗi deserialize hoặc xử lý trùng sau restart.

**Compatibility (tính tương thích) giữa manager và worker** là khả năng các phiên bản được triển khai đồng thời trao đổi đúng dữ liệu, thực thi đúng công việc, cập nhật trạng thái và phục hồi an toàn dù có retry, duplicate delivery hoặc triển khai từng phần.

Sau bài học, bạn có thể:

- Phân biệt hợp đồng giữa manager và worker trong **remote partitioning** và **remote chunking**.
- Liệt kê những lớp tương thích cần kiểm tra: phiên bản thư viện, thông điệp, dữ liệu, JobRepository, messaging và vận hành.
- Thiết kế ma trận tương thích và bài kiểm thử trước khi triển khai.
- Chọn cách rollout, drain và rollback phù hợp với message/job đang xử lý.
- Xác định triệu chứng của version mismatch và quy trình khắc phục mà không làm mất tiến độ job.

> **Phạm vi:** Bài này tập trung vào triển khai Spring Batch phân tán. Multi-threaded step và parallel steps chạy trong một JVM thường dùng chung classpath nên ít gặp vấn đề phiên bản giữa các tiến trình, nhưng vẫn chịu ràng buộc về dữ liệu, thread safety và tài nguyên.

## 2. Manager và worker trao đổi với nhau những gì?

Hợp đồng thay đổi theo topology. Không nên dùng từ “worker” chung chung rồi giả định mọi luồng dữ liệu đều giống nhau.

### 2.1. Remote partitioning

Manager chia dữ liệu thành nhiều **partition**, tạo các **StepExecution** tương ứng và chuyển yêu cầu thực thi đến worker. Worker tìm StepExecution được chỉ định, thực thi worker step và cập nhật trạng thái. Trong cấu hình remote partitioning điển hình của Spring Batch, manager và worker truy cập **cùng kho metadata JobRepository** (cùng cơ sở dữ liệu logic, cấu trúc metadata tương thích); message đóng vai trò điều phối, còn tiến độ là trạng thái được lưu bền vững.

~~~mermaid
flowchart LR
    M[Manager: partitioner] -->|StepExecution request| Q[(Request channel / broker)]
    Q --> W1[Worker A: worker step]
    Q --> W2[Worker B: worker step]
    W1 --> R[(Reply channel)]
    W2 --> R
    R --> M
    M --- DB[(Shared JobRepository)]
    W1 --- DB
    W2 --- DB
~~~

Những dữ liệu thường phải thống nhất:

- **Định danh execution:** job/step execution ID, tên step và cách worker truy xuất metadata tương ứng.
- **Worker step:** tên step được đăng ký trong worker; định nghĩa reader, processor, writer và transaction manager phù hợp.
- **Partition ExecutionContext:** khóa, kiểu và ý nghĩa của tham số như `minId`, `maxId`, `fileName`, `tenant`; reader của worker sử dụng chính các khóa đó.
- **JobRepository:** schema, serializer của ExecutionContext, transaction và quyền truy cập metadata.
- **Reply/correlation:** thông điệp phản hồi cần tới đúng manager đang chờ, phản ánh đúng StepExecution và trạng thái thực tế.

Ví dụ manager đặt `minId=1000` và `maxId=1999` vào ExecutionContext, còn bản worker mới lại chờ `startInclusive` và `endExclusive`. Message vẫn có thể truyền thành công, nhưng reader không còn hiểu partition như trước. Đây là lỗi **hợp đồng nghiệp vụ** dù mạng, broker và Java đều hoạt động bình thường.

### 2.2. Remote chunking

Với remote chunking, manager thường **đọc dữ liệu, chia chunk và gửi yêu cầu xử lý**; worker nhận item, thực hiện processing/writing và trả phản hồi. Vì **dữ liệu item đi qua đường truyền**, tương thích payload và bộ chuyển đổi thông điệp đặc biệt quan trọng.

~~~mermaid
flowchart LR
    RD[Manager: reader + chunk orchestration] -->|Chunk request chứa items| MQ[(Message broker)]
    MQ --> WA[Worker A: processor / writer]
    MQ --> WB[Worker B: processor / writer]
    WA -->|Chunk response| RP[(Reply channel)]
    WB -->|Chunk response| RP
    RP --> RD
~~~

Các bên cần thống nhất:

- Kiểu và cấu trúc item, danh sách item trong chunk, quy tắc null/enum/ngày giờ/số thập phân.
- Định dạng tuần tự hóa (serialization), type headers và cách deserialize các message type thuộc Spring Batch Integration.
- Sequence/correlation ID và cách manager ghép phản hồi với chunk đang chờ.
- Chính sách ack, redelivery, timeout, retry, idempotency và tính nhất quán của tác dụng phụ khi worker ghi dữ liệu.

**Lưu ý về transaction:** gửi message, ghi database tại worker và xác nhận message không mặc nhiên cùng một giao dịch end-to-end. Khi có lỗi ở ranh giới các bước này, cùng một chunk có thể đến lại. Thiết kế writer phải xét trường hợp xử lý lặp, thay vì suy ra exactly-once từ việc dùng Spring Batch.

### 2.3. Những điểm giống và khác cần ghi trong thiết kế

| Khía cạnh | Remote partitioning | Remote chunking |
|---|---|---|
| Đơn vị chuyển giao | Yêu cầu chạy **StepExecution/partition** | Yêu cầu xử lý **chunk/items** |
| Dữ liệu nghiệp vụ qua broker | Thường là metadata điều phối, không phải toàn bộ item | Có thể gồm tất cả item của chunk |
| Tính quan trọng của shared JobRepository | Rất quan trọng trong mô hình chuẩn vì worker lấy/cập nhật StepExecution | Manager điều phối JobRepository; worker cần tương thích giao thức request/response và quy tắc trạng thái tương ứng |
| Điểm lỗi phổ biến | Worker không tìm thấy step/execution, lệch ExecutionContext, trạng thái không được cập nhật | Không deserialize được item, sai response correlation, xử lý lại chunk |
| Mối quan tâm khi nâng cấp | Schema metadata, step naming, serializer ExecutionContext, wire message | DTO/schema item, serializer/converter, versioning message và idempotent writer |

Các chi tiết chính xác phụ thuộc phiên bản Spring Batch/Spring Integration và cách ứng dụng cấu hình channel, binder, handler. Vì vậy phải kiểm thử với **topology thật**, thay vì chỉ xác minh các service khởi động được.

## 3. Bảy lớp compatibility phải kiểm tra

| Lớp | Những thứ cần tương thích | Ví dụ vấn đề khi lệch |
|---|---|---|
| **1. Runtime & dependency** | JDK, Spring Boot, Spring Batch, Spring Integration, messaging adapter, thư viện serializer | `NoSuchMethodError`, `ClassNotFoundException`, khác kiểu payload/framework message |
| **2. Wire protocol** | Tên channel/queue/topic, routing key, reply destination, headers, correlation, encoding | Manager gửi được request nhưng không nhận reply |
| **3. Message schema** | Class/type ID, trường bắt buộc, enum, kiểu ngày/giờ, số, null và serializer | Deserialization error, giá trị bị đọc sai hoặc bị bỏ qua |
| **4. Execution metadata** | JobRepository schema, ExecutionContext serializer, stepName và job/step execution ID | Worker không tìm thấy execution, không đọc được context, lỗi cập nhật trạng thái |
| **5. Business semantics** | Ý nghĩa partition range, quy tắc lọc dữ liệu, thuật toán processor và nghiệp vụ writer | Không lỗi kỹ thuật nhưng thiếu/trùng bản ghi, sai tổng tiền |
| **6. Failure semantics** | Ack, retry, timeout, backoff, redelivery, restart, idempotency | Retry storm, xử lý lại gây double write hoặc job chờ vô hạn |
| **7. Operations & security** | Replica routing, quyền truy cập DB/broker, TLS, định dạng log/trace, health readiness | Worker sẵn sàng giả, consumer nhận sai queue, thiếu quyền DB |

Một hệ thống chỉ thực sự tương thích khi **cả giao tiếp lẫn tính đúng đắn của dữ liệu** được xác minh. Kiểm tra `/actuator/health` thành công mới chứng minh một phần điều kiện chạy, không chứng minh được worker nhận và xử lý đúng một partition/chunk.

## 4. Dependency và runtime: đồng bộ thứ cần đồng bộ

Trong cấu hình chuẩn, manager và worker thường khai báo dependency riêng vì chúng chạy ở các artifact khác nhau. Nếu để mỗi service tự chọn phiên bản `spring-batch-core`, `spring-batch-integration`, `spring-integration-*`, Jackson và messaging driver, nguy cơ lệch API hoặc định dạng message sẽ tăng.

Quy tắc triển khai an toàn:

1. Dùng **một bộ phiên bản đã kiểm chứng** cho manager và worker ở mỗi release, tốt nhất quản lý qua BOM/dependency management và lock/manifest của bản build.
2. Đồng bộ các thành phần trực tiếp tham gia message contract, đặc biệt **Spring Batch Integration**, Spring Integration và serializer/converter.
3. Bảo đảm mỗi artifact có JDK phù hợp với bytecode và các phiên bản framework của chính nó. Hai JVM không bắt buộc dùng cùng bản vá JDK để truyền message, nhưng phải qua kiểm thử liên thông của bộ runtime được hỗ trợ.
4. Đảm bảo thay đổi trong **domain DTO** và các library dùng chung được quản lý theo phiên bản, tránh một phía nhận class cũ còn phía kia gửi class mới.
5. Không dựa vào suy đoán rằng “chỉ tăng minor version thì mọi wire format đều backward-compatible”. Tính tương thích xuyên phiên bản chỉ được coi là có khi có cam kết phù hợp hoặc đã kiểm thử với cặp phiên bản cụ thể.

Nên tạo **compatibility manifest** cho từng bản phát hành, lưu cùng artifact và in trong log khởi động:

| Thành phần | Manager release | Worker release | Điều kiện chấp nhận |
|---|---|---|---|
| JDK | Bản được hỗ trợ | Bản được hỗ trợ | Cả hai chạy hợp lệ, các kiểu dữ liệu trên wire tương thích |
| Spring Batch/Integration | Phiên bản A | Phiên bản B | Cặp A/B nằm trong ma trận đã thử |
| Message protocol | `rp-v2` | `rp-v2` | Cùng hợp đồng do ứng dụng định nghĩa |
| Serialization | JSON profile S2 | JSON profile S2 | Type/headers/schema đọc và ghi nhất quán |
| Worker step | `importWorkerStep` | `importWorkerStep` | Trùng định danh và semantics được mong đợi |
| JobRepository | schema M | schema M | Cả hai phiên bản được kiểm tra với schema này |
| Business rules | release R | release R | Không mâu thuẫn đầu ra của cùng job |

Các tên `rp-v2`, `S2`, `M` và `R` ở bảng là **nhãn quản lý nội bộ minh họa**, không phải protocol version hay thuộc tính tự có của Spring Batch.

## 5. Message contract: không chỉ là JSON hợp lệ

Khi đi qua broker, message thường có **payload** và **headers**. Hợp đồng phải mô tả:

- Loại thông điệp: request hay reply, loại partition/chunk, identifier của job/step.
- Tên destination: request queue, reply queue, topic, routing key và consumer group nếu có.
- Hình thức tuần tự hóa: JSON, AMQP/JMS message converter hoặc cơ chế khác được cấu hình thực tế; charset, content type, type mapping.
- Trường bắt buộc, optional, giá trị mặc định; điều kiện schema evolution.
- Correlation: request ID, chunk sequence hoặc execution ID và quy tắc gắn phản hồi.
- Policy khi nhận bản không hiểu: từ chối có kiểm soát, DLQ/quarantine, cảnh báo và cách xử lý lại.

**Không tự ý thay thế message type mặc định của Spring Batch bằng một JSON tự đặt tên.** Nếu cần envelope có version, phải xây adapter và kiểm thử nó, hoặc dùng versioning tại lớp routing/manifest bên ngoài. Đặc biệt, Spring Integration và messaging framework có thể dùng type header, serializer hoặc object mapper riêng: producer và consumer cần đồng ý cả **kiểu Java trên wire** lẫn cách biểu diễn.

Ví dụ *hợp đồng ứng dụng tự thiết kế* cho một adapter quản lý version (không phải payload mặc định của Spring Batch):

~~~json
{
  "contractVersion": 2,
  "messageId": "partition-request-4821",
  "jobExecutionId": 150,
  "stepExecutionId": 4821,
  "stepName": "importWorkerStep",
  "partition": {
    "minIdInclusive": 1000,
    "maxIdInclusive": 1999
  }
}
~~~

Nếu dự án sử dụng adapter này, cần định nghĩa rõ `maxIdInclusive` là **bao gồm** điểm cuối, không phải `endExclusive`; người viết reader phải nhất quán. Trong remote partitioning dùng Spring Batch mặc định, partition context thường được lưu trong StepExecution/ExecutionContext và worker đọc theo execution ID, thay vì nhất thiết truyền mọi key qua JSON như ví dụ tự thiết kế.

### 5.1. Thay đổi schema theo cách có kiểm soát

| Thay đổi | Mức rủi ro | Biện pháp |
|---|---|---|
| Thêm trường optional với default an toàn | Có thể thấp nếu consumer bỏ qua field lạ | Thử cả **new producer → old consumer** và chiều ngược lại |
| Đổi tên trường hoặc đổi kiểu | Cao | Duy trì alias/adapter hoặc nâng version contract và queue |
| Thêm giá trị enum mới | Trung bình đến cao | Kiểm tra default/fallback; đừng giả định old worker chấp nhận |
| Đổi Java package/type header | Cao | Đồng bộ converter/type mapping hoặc version hóa giao thức |
| Đổi key trong ExecutionContext | Cao với job đang chạy/restart | Đọc được key cũ trong giai đoạn chuyển tiếp, có test restart |
| Đổi semantics của range/ID | Rất cao | Bắt buộc contract test và đối soát bản ghi, thường cần tách version |
| Thay thứ tự trường JSON | Thường thấp với JSON object | Chỉ an toàn nếu serializer dùng tên field, không dựa vị trí |

Phân biệt **backward compatibility** (mã mới hiểu dữ liệu cũ) và **forward compatibility** (mã cũ hiểu dữ liệu mới). Khi rolling deploy, cả hai chiều có thể xảy ra vì worker cũ và worker mới cùng nhận message; chỉ đạt một chiều là chưa đủ.

## 6. JobRepository, ExecutionContext và restart

Trong remote partitioning, metadata Spring Batch đóng vai trò điều phối giữa các tiến trình. Các bảng lưu **JobInstance, JobExecution, StepExecution, ExecutionContext** cần được quản lý như một hợp đồng chung.

### 6.1. Những điểm dễ vỡ

- **Schema metadata:** thay đổi version framework có thể yêu cầu migration SQL; không được giả định schema cũ/mới luôn tương thích hai chiều.
- **ExecutionContext serializer:** cùng khóa nhưng không giải mã được object có thể làm worker không khởi chạy hoặc restart thất bại. Nếu lưu class tùy biến, thay đổi class/package/kiểu dữ liệu cần được kiểm thử với các bản context đã ghi.
- **Định danh Step:** manager gửi tên step mà worker không đăng ký; worker không tìm thấy step hoặc thực thi phiên bản logic khác.
- **Transaction/update:** worker cần cập nhật StepExecution và metadata đúng cơ chế, quyền DB và mức isolation phù hợp.
- **Cùng JobInstance:** khi retry/restart, JobParameters xác định JobInstance; tạo JobParameters mới vô ý có thể sinh lần xử lý độc lập, làm trùng side effect.

Đối với job đã chạy dở, **tính tương thích của dữ liệu lưu bền vững quan trọng không kém message đang nằm trên broker**. Bạn cần kiểm tra cả trường hợp worker mới đọc ExecutionContext do worker cũ lưu trước khi lỗi.

### 6.2. Bài kiểm thử restart qua phiên bản

1. Khởi chạy job bằng release hiện tại, cho commit một số chunk/partition rồi tạo lỗi có kiểm soát.
2. Ghi lại JobInstance/JobExecution, StepExecution, ExecutionContext và số bản ghi thực đã commit.
3. Nâng lên bản manager/worker dự kiến, giữ nguyên kho metadata hợp lệ.
4. Restart theo cơ chế Spring Batch với cùng JobInstance, xác minh đọc được state cũ.
5. Đối soát đầu ra với baseline, tìm trùng/thiếu và kiểm tra các side effect bên ngoài DB (API, file, message).

Trường hợp rollback cũng phải chạy phép thử tương tự: bản cũ có thể **không đọc được** metadata được bản mới ghi. Vì vậy “rollback image” chưa đủ để bảo đảm rollback an toàn nếu schema hoặc định dạng ExecutionContext đã thay đổi.

## 7. Broker, channel, correlation và delivery semantics

Ngay cả khi code và dữ liệu tương thích, manager có thể chờ vô hạn nếu message đi sai route hoặc reply không được nhận.

| Đối tượng | Cần nhất quán | Lỗi có thể gặp |
|---|---|---|
| Request destination | Queue/topic/exchange, routing key, tenant hoặc namespace | Worker không nhận việc |
| Reply destination | Reply queue, header đích, correlation | Worker xử lý xong nhưng manager không biết |
| Consumer group / competing consumers | Các worker của đúng release và đúng job nhận việc | Worker sai phiên bản nhận payload mới |
| Serialization & content type | Message converter, type headers, object mapper, charset | Deserialize thất bại trước khi vào handler |
| Ack/requeue/DLQ | Quy tắc khi lỗi tạm thời hay lỗi không tương thích | Message bị lặp vô hạn hoặc trôi vào DLQ mà không cảnh báo |
| Retention, TTL, retry delay | Thời gian message còn tồn tại và thời gian manager chờ | Reply đến sau deadline hoặc bị hết hạn |
| Security | Credential, TLS, ACL trên destination và metadata DB | Consumer khởi động nhưng không có quyền subscribe/ack |

**At-least-once delivery** là trường hợp phải dự phòng trong nhiều hệ thống broker: message có thể được giao lại sau crash, mất ack hoặc timeout. Với broker và transaction cấu hình khác nhau, mức bảo đảm thực tế khác nhau; luôn kiểm thử kịch bản “đã ghi dữ liệu nhưng reply/ack bị mất”.

Để chống trùng:

- Gắn khóa nghiệp vụ duy nhất cho bản ghi và cân nhắc UPSERT/deduplication.
- Giữ tính idempotent của writer và những side effect không nằm trong transaction DB.
- Không retry vô hạn lỗi deserialize/class mismatch: đó thường là lỗi cấu hình hoặc version, không phải lỗi thoáng qua.
- Sử dụng log có `jobExecutionId`, `stepExecutionId`, `partitionId` hoặc `chunkSequence` và `messageId/correlationId` khi có để lần theo request/reply.

**Không tự sửa trực tiếp trạng thái BATCH_STEP_EXECUTION hoặc BATCH_JOB_EXECUTION để “gỡ kẹt”** khi chưa xác định nguyên nhân. Cần kiểm tra trạng thái job thật, transaction, worker còn chạy và quy trình restart hợp lệ trước.

## 8. Thiết kế một compatibility contract cho deployment

Ngoài dependency manifest, có thể khai báo một cấu hình thống nhất cho pipeline triển khai. Ví dụ dưới đây là **manifest tùy biến của dự án**, dùng để chặn phát hành sai trước khi nạp workload; Spring Batch **không tự đọc** các field này và không tự kiểm tra contract version.

~~~yaml
deploymentContract:
  release: "2026.11-r3"
  topology: "remote-partitioning"
  messageRevision: "partition-v2"
  executionContextRevision: "import-context-v2"
  workerStepName: "importWorkerStep"
  repositorySchemaRevision: "approved-schema-17"
  routingRevision: "import-r2"

destinations:
  request: "batch.import.v2.request"
  reply: "batch.import.v2.reply"
~~~

Trong CI/CD, pipeline có thể so sánh manifest giữa hai artifact sắp kết nối với nhau, kiểm tra các destination tồn tại và xác minh chúng trỏ đến đúng release. Bài kiểm thử integration vẫn là bằng chứng quyết định. Hai manifest trùng nhau không bảo đảm code xử lý thật sự đúng.

Ví dụ đơn giản minh họa việc **fail fast ở deployment gate**, không phải một bean hoặc tính năng có sẵn của Spring Batch:

~~~java
public final class CompatibilityGate {
    private CompatibilityGate() {}

    public record DeploymentContract(
        String topology,
        String messageRevision,
        String executionContextRevision,
        String workerStepName,
        String repositorySchemaRevision,
        String routingRevision
    ) {}

    public static void requireCompatible(
            DeploymentContract manager,
            DeploymentContract worker) {
        if (!manager.topology().equals(worker.topology())
                || !manager.messageRevision().equals(worker.messageRevision())
                || !manager.executionContextRevision().equals(
                        worker.executionContextRevision())
                || !manager.workerStepName().equals(worker.workerStepName())
                || !manager.repositorySchemaRevision().equals(
                        worker.repositorySchemaRevision())
                || !manager.routingRevision().equals(worker.routingRevision())) {
            throw new IllegalStateException(
                "Manager/worker deployment contract mismatch"
            );
        }
    }
}
~~~

Đoạn kiểm tra cần được gắn vào pipeline, registry hoặc một handshake tự xây dựng để nhận **manifest thật của cả manager và worker**. Nếu mỗi tiến trình chỉ so sánh hai chuỗi hard-code trong chính mình thì không phát hiện được việc chạy lệch release. Phép so sánh bằng nhau cũng là chính sách **bảo thủ**: nếu dự án có ma trận tương thích nhiều version đã được chứng minh, deployment gate có thể dùng quan hệ phiên bản được phép thay cho equality.

## 9. Chiến lược triển khai và giới hạn rolling upgrade

### 9.1. Khi có thể rolling upgrade?

Rolling upgrade nghĩa là một thời gian ngắn **manager/worker cũ và mới cùng tồn tại**. Chỉ nên thực hiện khi kiểm thử đã chứng minh:

1. Old manager ↔ new worker và new manager ↔ old worker đều hiểu message trong suốt khoảng chồng lấn, hoặc broker/routing tách được hai nhóm.
2. Hai bản đọc/ghi JobRepository và ExecutionContext chung an toàn trong thời gian đó.
3. Message còn tồn trong queue có thể được consumer đúng phiên bản xử lý.
4. Một partition/chunk không bị xử lý trùng do hai nhóm tranh nhau cùng message hoặc do chuyển traffic quá sớm.
5. Việc rollback binary không bị schema/database migration hoặc business side effect làm mất khả năng quay về.

Nếu bất kỳ điều kiện nào chưa được chứng minh, hãy ưu tiên rollout **có drain/quiesce** thay vì cho các version cùng tiêu thụ một queue.

### 9.2. Quy trình triển khai có drain

Đây là trình tự tham khảo cho hệ thống không bảo đảm mixed-version compatibility:

1. **Đóng nguồn việc mới:** tạm dừng scheduler/trigger của manager và yêu cầu producer không gửi thêm job cho release cũ.
2. **Drain:** quan sát active StepExecution/chunk, in-flight requests/replies, unacked message và consumer lag; đợi trạng thái ổn định theo chính sách timeout. Không xóa thủ công message chưa được xử lý.
3. **Chụp trạng thái:** ghi phiên bản artifact, cấu hình, schema, trạng thái JobRepository và backlog; chuẩn bị kế hoạch restart khi có job FAILED/STOPPED.
4. **Cắt nhận việc của worker cũ:** dừng consumer đúng cách sau khi xử lý/ack các việc hiện có trong phạm vi cho phép.
5. **Triển khai thay đổi được kiểm chứng:** thực hiện migration schema (nếu có và đã được lập kế hoạch), triển khai worker và manager tương thích, xác minh kết nối DB/broker.
6. **Canary:** chạy một job/partition/chunk thử có thể đối soát và kiểm tra request/reply, trạng thái JobRepository, output và trace.
7. **Mở lại tải:** kích hoạt scheduler/producer theo mức tăng dần, theo dõi retry, DLQ, backlog, timeout và throughput.

Nếu job không thể dừng hoặc drain ngay, cần chính sách riêng: để bản cũ hoàn tất, dùng queue versioned cho bản mới hoặc kiểm thử restart xuyên phiên bản trước khi cắt. Tránh chọn giờ triển khai chỉ dựa trên thời điểm “ít người dùng” khi batch job có thể chạy qua đêm.

### 9.3. Blue/green và queue theo version

Khi contract thay đổi không tương thích, tách destination giúp cô lập:

~~~text
Manager/Worker release A -> request.v1 / reply.v1
Manager/Worker release B -> request.v2 / reply.v2
~~~

Chỉ có một nhóm nên sở hữu việc xử lý tương ứng. Cần chuyển scheduler/producer có kiểm soát, bảo đảm request cũ được worker cũ xử lý xong hoặc có quy trình chuyển đổi message. Queue mới **không tự chuyển đổi** job metadata, dữ liệu item, checkpoint hay side effect. Hai nhóm cũng phải không cùng cập nhật những business key gây xung đột ngoài ý muốn.

### 9.4. Rollback không chỉ là đổi Docker image

Rollback có thể thất bại nếu:

- DB metadata hoặc business schema đã đổi theo hướng bản cũ không đọc được.
- Message mới còn tồn trong broker mà worker cũ không deserialize được.
- ExecutionContext mới chứa type/key mà phiên bản cũ không hiểu.
- Tác dụng phụ (file/API/DB) đã được bản mới thực hiện theo semantics khác.

Kế hoạch rollback nên xác định **điểm còn đảo ngược được**, dữ liệu nào cần migration ngược hoặc conversion, cách drain/quarantine message mới và bài test restart từ trạng thái thật.

## 10. Ma trận contract test trước khi release

Thử hai artifact thật (hoặc container tương đương production) với cùng broker và JobRepository của môi trường test. Không chỉ test DTO unit riêng lẻ.

| Kịch bản | Tạo điều kiện | Điều kiện PASS |
|---|---|---|
| Same-version smoke | Manager A + Worker A | Giao việc, có reply, Step/Job kết thúc và đối soát đúng |
| Mixed-version theo hướng 1 | Manager A + Worker B | Đúng kết quả hoặc bị deployment gate chặn có thông báo rõ |
| Mixed-version theo hướng 2 | Manager B + Worker A | Đúng kết quả hoặc bị gate chặn, không nhận nhầm message |
| Message tồn đọng | Tạo request cũ trước rollout, để trên queue rồi nâng worker | Được xử lý an toàn hoặc tách/quarantine theo quy trình |
| Context cũ | Tạo StepExecution/ExecutionContext ở A rồi restart với B | Không lỗi deserialize, không mất/trùng output |
| Thay đổi DTO | Message chứa field optional, enum mới, null hoặc số lớn | Consumer xử lý đúng hoặc từ chối có kiểm soát, không âm thầm sai dữ liệu |
| Duplicate/redelivery | Gửi lại một request sau khi worker đã ghi nhưng reply/ack bị mất | Không nhân đôi side effect |
| Worker crash | Kill worker test giữa transaction hoặc trước ack/reply | Job phát hiện lỗi và phục hồi/restart đúng |
| Manager crash | Dừng manager khi worker đang chạy hoặc có reply chờ | Trạng thái nhất quán, cơ chế recovery đúng phiên bản |
| Reply misroute | Cố tình dùng reply destination/correlation sai trong test | Bị timeout/cảnh báo rõ, không đánh dấu COMPLETED giả |
| Database/broker outage | Ngắt dependency test rồi khôi phục | Retry có giới hạn, cảnh báo và restart đúng |
| Scale & resource | Tăng số worker trong quota CPU/JDBC và queue phù hợp | Throughput/latency đạt mục tiêu, không gây nghẽn metadata DB |

Với mỗi case, ghi **producer version, consumer version, message type, schema revision, JobRepository revision, test input, số bản ghi ra, error/rollback và kết luận**. Muốn tuyên bố “hỗ trợ rolling upgrade A → B”, bắt buộc phải có test cho toàn bộ các cặp phiên bản cùng tồn tại và bối cảnh message còn tồn đọng.

### Đối soát kết quả quan trọng hơn chỉ nhìn trạng thái COMPLETED

Ví dụ batch nhập 1 triệu giao dịch:

- So khớp số giao dịch theo business ID và số lượng key duy nhất.
- So khớp tổng tiền theo loại tiền, số bản ghi bị lọc/skip đúng quy tắc.
- Kiểm tra không có key trùng dù request được gửi lại.
- Xác minh StepExecution đã hoàn tất và JobRepository không còn execution mồ côi ở trạng thái không phù hợp.
- Đối với side effect bên ngoài (API, event, file), kiểm tra bằng idempotency key hoặc audit log.

Một job có thể báo `COMPLETED` dù bản worker mới đã thay đổi quy tắc lọc dẫn đến thiếu dữ liệu. Tính tương thích cần được chứng minh ở **ngữ nghĩa nghiệp vụ**.

## 11. Giám sát compatibility khi vận hành

Để phân biệt lỗi version mismatch với lỗi tài nguyên, log và metric nên gắn nhãn **release manager/worker**, topology, job/step execution ID, partition/chunk identifier và message correlation.

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xác minh |
|---|---|---|
| `ClassNotFoundException`, `InvalidTypeIdException`, lỗi deserialize | Class/type mapping/serializer lệch | So sánh dependency và raw message metadata trong môi trường kiểm thử |
| Worker báo không tìm thấy step | Tên worker step hoặc bean registry khác | So sánh `stepName`, tên cấu hình step, package scanning |
| Worker không tìm thấy StepExecution | Không cùng JobRepository hoặc execution ID sai | Xác nhận datasource/schema/JobExplorer và execution ID |
| `ExecutionContext` không đọc được | Serializer, object class hoặc key/type thay đổi | Kiểm tra metadata cũ và test restart xuyên release |
| Manager chờ reply nhưng worker đã ghi xong | Reply queue/routing/correlation, timeout hoặc mất ack | Theo trace request → worker → reply và backlog/DLQ |
| Message lặp trong DLQ | Poison message, version mismatch hoặc policy retry | Kiểm tra lỗi gốc; dừng retry vô hạn |
| Cùng item xuất hiện nhiều lần | Redelivery và writer thiếu idempotency | Đối chiếu business ID, commit/ack/reply timeline |
| Chỉ lỗi khi scale worker | Worker replica nhận sai release, connection/CPU/DB quá tải | Kiểm tra pod labels, queues, active JDBC/CPU/threads |

Phân biệt lỗi **tương thích** với lỗi **bão hòa**:

- Lỗi deserialize hoặc thiếu step xuất hiện ngay ở một cặp release cụ thể thường là mismatch cấu hình/schema.
- Timeout tăng theo số worker, JDBC pending/DB lock wait tăng, CPU hoặc queue đầy thường cho thấy tài nguyên bị bão hòa.
- Hai hiện tượng có thể đồng thời xuất hiện: một poison message lặp lại liên tục cũng gây tốn CPU và queue.

Các cảnh báo hữu ích gồm tỷ lệ request không có reply trong deadline, số message vào DLQ, số execution chạy quá lâu, lỗi deserialize theo version, tỷ lệ retry/redelivery, worker lạc release, cùng metrics heap/GC, CPU, JDBC pool, broker lag và queue depth.

## 12. Runbook khi manager và worker không tương thích

Khi phát hiện mismatch trong lúc đang chạy job:

1. **Hạn chế phát sinh việc mới** đối với release bị ảnh hưởng; tránh thêm partition/chunk mới lên queue lỗi.
2. **Xác định phạm vi:** manager/worker release nào, destination nào, job/step execution ID nào, message nào đã được ack hoặc nằm trong DLQ.
3. **Giữ bằng chứng:** log lỗi, header/payload đã làm sạch dữ liệu nhạy cảm, metric broker, trạng thái metadata và cấu hình release; tránh xóa queue hoặc sửa DB trực tiếp.
4. **Phân loại lỗi:** serializer/DTO, worker step name, ExecutionContext, JobRepository schema, routing/reply hay resource exhaustion.
5. **Khôi phục cặp tương thích:** route message về worker đúng version, dùng adapter đã thử hoặc drain và deploy cặp release đồng bộ.
6. **Xử lý backlog an toàn:** chỉ replay message sau khi xác định trạng thái commit và cơ chế deduplication; message poison cần quarantine và sửa nguyên nhân.
7. **Restart đúng job:** dùng cơ chế restart của Spring Batch, đối soát dữ liệu và side effect trước khi mở lại toàn bộ tải.

Đừng “sửa nhanh” bằng việc xóa toàn bộ request/reply queue, đánh dấu job là COMPLETED thủ công hoặc ép consumer mới nhận payload không hiểu. Các thao tác này có thể làm mất công việc đã được manager ghi nhận hoặc nhân đôi bản ghi sau restart.

## 13. Bài thực hành triển khai

**Bối cảnh:** Ứng dụng đang dùng remote partitioning để nhập 8 triệu bản ghi. Manager bản A và 6 worker bản A chia sẻ JobRepository. Nhóm chuẩn bị triển khai worker bản B với reader được cải tiến, thay khóa context từ `minId/maxId` sang `startInclusive/endExclusive`. Một số StepExecution đang ở trạng thái chạy dở, request vẫn còn trên broker. Nhóm muốn rollout worker B trước, sau đó manager B.

Hãy xây dựng kế hoạch dựa trên các câu hỏi:

1. Việc đổi tên khóa và đổi semantics của cận trên ảnh hưởng thế nào đến partition cũ, partition mới và restart?
2. Nếu manager A tiếp tục gửi request cho worker B trên cùng queue, điều kiện nào khiến dữ liệu bị bỏ sót hoặc lặp?
3. Nên sửa worker B để đọc được **cả context cũ và mới** với semantics rõ ràng, hay nên tách queue/release? Các trường hợp nào cho phép mixed rollout và trường hợp nào cần drain?
4. Những phép thử nào phải PASS trước khi mở scheduler trở lại? Gợi ý: A/A, A/B, B/A, B/B, restart A → B, duplicate delivery, broker backlog.
5. Nếu B đã ghi ExecutionContext mới và sau đó phải rollback về A, cần chứng minh điều gì trước khi chạy lại?
6. Chọn metric và dấu hiệu vận hành để phát hiện lỗi: unknown step, deserialize failure, request timeout, reply correlation, DB lock wait, duplicate business key.

Một lời giải khả thi là giữ **compatibility adapter cho context cũ** trong worker B, phiên bản hóa rõ quy tắc cận inclusive/exclusive, rồi kiểm thử cùng JobRepository và backlog cũ. Nếu không thể bảo đảm hai chiều, dừng tạo partition mới, để bản A drain và triển khai B theo một đợt có kiểm soát; sau đó mới cho phép công việc mới chạy. Quyết định cuối cùng phải dựa trên kết quả contract test và khả năng phục hồi dữ liệu đã commit.

## 14. Checklist trước khi bật production

- [ ] Có bảng version của JDK, Spring Batch, Spring Integration, messaging adapter, converter và DTO library cho cả hai phía.
- [ ] Xác định topology (remote partitioning hay remote chunking), message type, request/reply channel, headers và correlation.
- [ ] Worker đăng ký đúng step name; partition ExecutionContext giữ đúng key, kiểu và semantics.
- [ ] JobRepository schema/serializer, quyền truy cập và migration đã được kiểm chứng với phiên bản đang cùng tồn tại.
- [ ] Đã thử A/A, B/B và mọi cặp mixed-version được phép chạy; có test queue tồn đọng và restart xuyên phiên bản.
- [ ] Đã kiểm thử redelivery, ack/reply loss, poison message, timeout, retry giới hạn và idempotency của writer.
- [ ] Có kế hoạch rollout/drain hoặc blue/green/queue versioned, cùng điểm rollback an toàn.
- [ ] Canary đối soát dữ liệu và side effect, log theo release/correlation và cảnh báo DLQ/reply timeout.
- [ ] Kiểm thử throughput, CPU/heap, JDBC connection, queue depth và tác động lên JobRepository tại concurrency dự kiến.
- [ ] Đã thống nhất người vận hành được phép mở scheduler, tạm dừng tiêu thụ và kích hoạt quy trình recovery.

## 15. Ghi nhớ

**Manager và worker tương thích** khi chúng có thể hiểu đúng thông điệp, tìm đúng execution, diễn giải đúng dữ liệu, cập nhật trạng thái và phục hồi chính xác sau lỗi. Trong **remote partitioning**, đặc biệt chú ý StepExecution, ExecutionContext và JobRepository dùng chung; trong **remote chunking**, đặc biệt chú ý schema item, serialization, correlation và idempotent writer. Cùng dependency version là điểm khởi đầu tốt, nhưng bằng chứng thực sự nằm ở **contract test với hai artifact thật, trạng thái job chạy dở và message còn tồn đọng**. Chỉ rolling upgrade khi tất cả các cặp version có thể gặp nhau đã được kiểm chứng; nếu chưa, dùng drain hoặc tách routing để bảo vệ tính đúng đắn của batch job.
