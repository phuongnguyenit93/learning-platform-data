# Thiết kế ranh giới service để mọi điểm vào đều được bảo vệ

## 1. Mục tiêu và bất biến bảo mật

Một nghiệp vụ Spring có thể được gọi qua HTTP controller, GraphQL resolver, WebSocket handler, message consumer, scheduler, CLI, một service khác hoặc một luồng xử lý bất đồng bộ. Nếu chính sách phân quyền chỉ đặt ở HTTP filter hoặc chỉ ở một controller, những đường vào khác có thể đi thẳng tới service/repository và bỏ qua việc kiểm tra.

**Mục tiêu thiết kế:** Mọi đường thực thi một use case nhạy cảm phải đi qua **ranh giới nghiệp vụ có kiểm soát quyền**, nơi xác định người thực hiện, phạm vi dữ liệu, quyền thao tác và điều kiện truy cập vào từng tài nguyên, **trước khi tạo side effect hoặc công bố dữ liệu**.

Ba câu hỏi cần được trả lời riêng:

1. **Ai gọi?** Một người dùng đã xác thực, một service identity đã được xác minh hay một job được ủy quyền? Danh tính không được lấy bằng cách tin một chuỗi `userId` hoặc `tenantId` từ request/event.
2. **Được làm gì?** Caller có authority cho hành động `document:write`, `document:read`, `document:archive` ... không?
3. **Được tác động lên tài nguyên nào?** Bản ghi có thuộc đúng tenant, project, nhóm, owner, ACL và trạng thái nghiệp vụ cho phép hay không?

Câu trả lời cho câu 2 không tự bảo đảm câu 3. Ví dụ `hasAuthority('document:write')` cho phép một loại thao tác nhưng **không** chứng minh caller được sửa mọi tài liệu.

**Bất biến kiểm chứng được:**

- Một thao tác có side effect chỉ được thực thi khi có danh tính tin cậy và quyết định quyền phù hợp với đúng resource.
- Những adapter khác nhau không được tạo ra các đường cập nhật dữ liệu có mức bảo vệ yếu hơn.
- Chính sách không phụ thuộc vào việc lời gọi có “đi từ controller” hay không.
- Các method có annotation Spring AOP chỉ được coi là đã bảo vệ khi đường gọi thật sự đi **qua Spring proxy**.
- Transaction bảo đảm tính nguyên tử/nhất quán ở mức được cấu hình; nó **không thay thế kiểm soát truy cập**.
- Khi thiếu danh tính, scope hoặc bằng chứng về quyền, không thực hiện thao tác đặc quyền.

## 2. Sơ đồ kiến trúc: adapter đến service, policy và dữ liệu

~~~text
REST / GraphQL / WebSocket    Message consumer     Scheduler / CLI
          |                         |                    |
          v                         v                    v
  Verify human identity     Verify message origin   Verify job/service
  and authentication        + actor/context        identity + purpose
          |                         |                    |
          +-------------+-----------+--------------------+
                        |
              Use-case adapter
                        |
                        v
             PUBLIC SERVICE BOUNDARY
        (Spring-managed bean through proxy)
              @PreAuthorize / guard
                        |
                        v
             @Transactional use case
                |
                +--> resolve TRUSTED scope
                +--> resource/tenant/ACL policy
                +--> validate business invariants
                |
                v
           scoped repository / domain
                |
                v
               database
~~~

Sơ đồ là nguyên tắc thiết kế; **không phải mọi adapter đều tự có Spring SecurityContext**. HTTP thường có context người dùng theo request. Message listener/scheduled task cần cơ chế xác minh và truyền danh tính riêng. Nếu một adapter không có authentication thích hợp, cần **từ chối hoặc dùng một use case hệ thống được bảo vệ riêng**, không gán ngầm quyền quản trị.

Khi hệ thống dùng Spring Security method security, tầng service là nơi tự nhiên đặt kiểm tra quyền **gọi thao tác**. Tầng query/domain policy kiểm tra quyền **trên từng đối tượng**. Có thể thêm database Row-Level Security (RLS), audit, validation và network authorization như các lớp bổ trợ; mỗi lớp có ranh giới rõ.

## 3. Vì sao chỉ bảo vệ controller là chưa đủ?

Giả sử endpoint sau được bảo vệ ở HTTP layer:

~~~java
@PatchMapping("/documents/{id}/title")
public ResponseEntity<Void> rename(
        @PathVariable long id,
        @RequestBody RenameRequest request) {
    documentService.rename(id, request.title());
    return ResponseEntity.noContent().build();
}
~~~

Mã là thành phần minh họa trong Spring MVC; `RenameRequest` và `documentService` do ứng dụng định nghĩa.

Một cấu hình request security có thể chỉ cho người dùng có authority `document:write` gọi `PATCH /documents/**`. Điều này bảo vệ request HTTP **đi qua đúng SecurityFilterChain**. Nhưng cùng method `documentService.rename(...)` có thể được gọi từ:

- `@KafkaListener`, `@RabbitListener` hoặc một message handler.
- Một service khác xử lý hàng loạt, import, nghiệp vụ liên kết.
- `@Scheduled`, command-line runner, event listener, integration test hoặc code quản trị.
- Một API khác được cấu hình security khác, chẳng hạn GraphQL hoặc gRPC.

Các lời gọi trên không mặc nhiên đi qua bộ lọc HTTP. Nếu service không tự kiểm tra quyền, lập trình viên bổ sung một đường gọi mới có thể vô tình tạo lỗ hổng.

**Nguyên tắc:** Controller xác nhận format request và chuyển use case; service chịu trách nhiệm ranh giới quyền nghiệp vụ; repository thực thi phạm vi dữ liệu thích hợp. Đừng biến controller thành nơi duy nhất biết policy.

## 4. Cách Spring Security method security bảo vệ service

Bật method security tường minh:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Spring Boot starter security không tự bật method security chỉ vì dependency hiện diện. Với cấu hình này, annotation như `@PreAuthorize` trên Spring-managed bean có thể được xử lý bằng interceptor. Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentCommandService {

    @PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
    public void rename(long documentId, String newTitle) {
        // Kiểm tra quyền trên đúng document rồi mới cập nhật.
    }
}
~~~

Hai nhận định quan trọng:

- `@PreAuthorize` được đánh giá **trước** phần thân method khi lời gọi đã đi qua interceptor. Với rule trên, một người dùng có authority ghi **chưa chắc** có quyền sửa tài liệu số 17 của tenant khác.
- Annotation là metadata cho AOP. Nó không tự kích hoạt trên một đối tượng được tạo bằng `new DocumentCommandService()` ngoài Spring, cũng không tự bảo vệ mọi lời gọi Java tới method nếu lời gọi không đi qua proxy.

`@EnableMethodSecurity` không đồng nghĩa với “mọi public method đều tự bị khóa”. Những method không có rule phù hợp vẫn có thể được gọi trừ khi một cơ chế authorization khác được thiết kế để chặn. Vì vậy phải **liệt kê các use case nhạy cảm** và gắn policy phù hợp, hoặc tổ chức một cơ chế áp dụng rule mặc định có thể kiểm thử.

## 5. Proxy boundary: lỗi self-invocation nguy hiểm

Trong chế độ AOP proxy thông thường:

~~~text
Other Spring bean --> Proxy --> @PreAuthorize interceptor --> target.method()
                         |
                         +--> @Transactional interceptor (theo cấu hình)
~~~

Nhưng lời gọi **nội bộ cùng object** không đi qua proxy:

~~~text
Other bean --> Proxy --> target.importBatch()
                              |
                              +--> this.rename(...)    // trực tiếp trong target
                                   @PreAuthorize trên rename bị bỏ qua
~~~

Ví dụ thiết kế sai:

~~~java
@Service
public class UnsafeDocumentService {

    public void importBatch(List<RenameCommand> commands) {
        for (RenameCommand command : commands) {
            this.rename(command.id(), command.title());
        }
    }

    @PreAuthorize("hasAuthority('document:write')")
    @Transactional
    public void rename(long id, String title) {
        // cập nhật database
    }
}
~~~

Nếu `importBatch` không có cơ chế quyền riêng, lời gọi qua service proxy đến `importBatch` rồi `this.rename(...)` **không kích hoạt interceptor gắn trên `rename`**. Tùy đường gọi, transaction của `rename` cũng không được bắt đầu theo annotation đó. Đây là nguyên nhân khiến API chính được bảo vệ còn chức năng import/batch chạy được mà thiếu kiểm tra.

**Sửa bằng cách tách ranh giới use case thành các bean khác nhau:**

~~~java
@Service
public class DocumentBatchService {
    private final DocumentCommandService commands;

    public DocumentBatchService(DocumentCommandService commands) {
        this.commands = commands;
    }

    @Transactional
    public void renameBatch(List<RenameCommand> items) {
        for (RenameCommand item : items) {
            commands.rename(item.id(), item.title());
        }
    }
}
~~~

Ở đây `commands` là bean được Spring inject nên lời gọi `commands.rename(...)` có thể đi qua proxy của `DocumentCommandService`. Mọi item đều phải qua cùng ranh giới quyền. Nếu muốn batch là một transaction, xử lý lỗi phải nhất quán: exception khiến batch bị từ chối không được bị nuốt rồi vẫn commit một phần theo ý muốn ngoài hợp đồng.

Mã tích hợp trên giả định đã định nghĩa `RenameCommand`, constructor dependencies và cấu hình transaction. Nếu import batch là hành động đặc quyền khác với rename thủ công, `renameBatch` cũng cần **quyền thực thi batch** riêng, ví dụ `@PreAuthorize("hasAuthority('document:bulk-write')")`; kiểm tra quyền từng tài liệu bên trong vẫn cần thiết.

**Không xem các cách vòng như gọi `AopContext.currentProxy()` hoặc self-inject proxy là lựa chọn mặc định**. Chúng làm lộ chi tiết hạ tầng vào nghiệp vụ, dễ sai cấu hình và khó test. Tách bean/service theo ranh giới rõ là cách đọc và chứng minh đơn giản hơn. Nếu ứng dụng thật sự dùng AspectJ weaving, semantics có thể khác proxy mode; phải xác nhận cấu hình thực.

### JDK proxy, CGLIB và method visibility

Cần biết kiểu proxy thực tế:

- JDK dynamic proxy thường làm việc qua interface mà proxy triển khai; caller phải đi qua interface proxy tương ứng.
- Class-based proxy (thường dựa trên CGLIB) cần method có thể bị override; `final` method và `private` method không phải điểm interception thông thường. Final class có thể gây vấn đề với proxy kiểu subclass.
- Khả năng áp dụng transaction lên một số method non-public thay đổi theo Spring version và kiểu proxy. Đối với authorization quan trọng, chọn **public service API rõ ràng trên bean do Spring quản lý**, gọi từ bean khác và kiểm thử bằng proxy thực tế.
- Annotation không chạy khi code cố tình lấy target object và gọi trực tiếp, khi dùng `new` hoặc khi một lời gọi đã bị bypass bằng kỹ thuật khác.

Tránh đặt quyết định truy cập nhạy cảm lên một method `private` rồi hy vọng `@PreAuthorize` bảo vệ method đó.

## 6. Đặt quyền thao tác và quyền tài nguyên tại cùng use case

Một thiết kế dễ kiểm tra dùng **hai lớp bảo vệ**:

1. `@PreAuthorize` chặn người không có authority phù hợp trước khi vào service method.
2. Bên trong service, từ scope tin cậy, truy vấn đúng tài nguyên và gọi policy domain để kiểm tra tenant/owner/ACL **trước khi sửa**.

Ví dụ dưới đây minh họa Spring Data JPA và method security; các kiểu domain `Document`, `Actor`, `ActorResolver`, `DocumentPolicy` cần do ứng dụng định nghĩa.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.UUID;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    Optional<Document> findByIdAndTenantId(Long id, UUID tenantId);
}
~~~

Service nghiệp vụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository repository;
    private final ActorResolver actorResolver;
    private final DocumentPolicy policy;

    public DocumentCommandService(
            DocumentRepository repository,
            ActorResolver actorResolver,
            DocumentPolicy policy) {
        this.repository = repository;
        this.actorResolver = actorResolver;
        this.policy = policy;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
    @Transactional
    public void rename(long documentId, String newTitle) {
        Actor actor = actorResolver.requireCurrentAuthenticatedActor();

        if (documentId <= 0 || newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Invalid rename request");
        }

        Document document = repository.findByIdAndTenantId(
                documentId, actor.tenantId()
        ).orElseThrow(() -> new ResourceNotFoundException(documentId));

        policy.requireCanRename(actor, document);
        document.rename(newTitle);
    }
}
~~~

Điều kiện thiết kế cần được thực thi:

- `ActorResolver` phải lấy danh tính/tenant từ nguồn **đã xác minh** (security context, principal chuẩn hóa hoặc cơ chế identity tương đương), không đọc trực tiếp `ownerId/tenantId` do client gửi rồi coi đó là quyền.
- Query `findByIdAndTenantId` giới hạn trước theo tenant. `DocumentPolicy.requireCanRename` kiểm tra mọi điều kiện còn lại: owner, share, trạng thái tài liệu, membership, quyền của tài khoản, v.v. Không suy ra owner permission chỉ từ authority chung.
- `Document.rename` là logic nghiệp vụ minh họa; JPA dirty checking chỉ hoạt động nếu entity đang được quản lý trong persistence context và transaction phù hợp. Nếu dùng update query hoặc API ngoài DB, triển khai side effect theo hợp đồng riêng.
- `ResourceNotFoundException` là exception ứng dụng; chỉ được trả thông báo an toàn theo chính sách chống lộ sự tồn tại tài nguyên. ID không đúng tenant thường có thể được xử lý như “không tìm thấy” thay vì xác nhận sự tồn tại của object.
- `IllegalArgumentException` thường dẫn tới phản hồi input lỗi khi adapter ánh xạ phù hợp; không đồng nghĩa với lỗi authorization.
- Trong triển khai thực tế, tránh quyền thay đổi giữa kiểm tra và ghi nếu rủi ro nghiệp vụ đòi hỏi: dùng transaction, isolation/lock hoặc điều kiện UPDATE có scope và version khi thích hợp.

**Một service, một hợp đồng quyền:** Các adapter người dùng gọi cùng method này qua bean Spring, nên không phải chép lại logic owner/ACL ở mỗi controller. Tuy nhiên, phải có quy ước để các adapter không được trực tiếp gọi `repository.save(...)` bỏ qua use case; kiến trúc gói module, kiểm thử và review cần ràng buộc điều đó.

## 7. Thiết kế cho nhiều điểm vào mà không giả định mọi caller là HTTP

| Điểm vào | Danh tính cần xác minh | Cách đi qua ranh giới |
|---|---|---|
| Spring MVC/REST | Authentication từ Spring Security filter chain | Controller gọi bean service có rule; service kiểm tra tài nguyên |
| GraphQL resolver | Principal/authentication của request GraphQL | Resolver gọi cùng service; không dựa duy nhất vào rule URL |
| WebSocket handler | Danh tính hợp lệ của kết nối/message, scope hành động | Handler xác minh quyền message rồi gọi use case |
| gRPC hoặc API nội bộ | Service-to-service identity/caller đã xác thực | Interceptor gateway và policy service/resource; không tin header tự khai |
| Kafka/RabbitMQ/queue consumer | Nguồn phát, signature/trust boundary, actor hoặc service identity | Adapter xác minh message; dùng user-bound use case hoặc hệ thống có policy riêng |
| Scheduled job | Job identity, nhiệm vụ và tập tenant/resource được phép | Use case quản trị được kiểm soát độc lập; không cấp mặc định quyền admin |
| CLI/admin command | Operator/service identity và phạm vi quyền | CLI adapter xác minh danh tính rồi gọi same policy boundary |
| Service gọi service | Ngữ cảnh tin cậy và public API proxy | Inject bean service, không dùng `this.method()` đến method có annotation |
| Async execution | Identity/scope được truyền đúng tới đơn vị thực thi | Giữ context có kiểm soát, hoặc đánh giá lại quyền tại worker |
| Integration test | Principal hoặc service identity do fixture mô phỏng hợp lệ | Test qua Spring bean/proxy và quan sát dữ liệu thật |

Sự hiện diện của một security context ở HTTP thread không có nghĩa message worker sẽ có context đó. Không được xử lý tình trạng thiếu authentication bằng `ROLE_ADMIN` mặc định.

### Thông điệp từ hệ thống ngoài không tự chứng minh người gửi

Event payload có thể chứa `userId`, `tenantId` hoặc `requestedBy` để phục vụ trace, nhưng những trường này là **dữ liệu**. Để sử dụng làm quyền, phải chứng minh provenance/identity bằng cơ chế tin cậy (mTLS, issuer xác minh chữ ký, broker ACL cùng hợp đồng trust, signed command, authorization ticket có hạn dùng...) và giới hạn quyền của nguồn phát.

Message có thể được nhận trùng, phát lại, thay đổi thứ tự, hoặc được tiêu thụ sau khi quyền người dùng bị thu hồi. Với hành động nhạy cảm, cân nhắc kiểm tra quyền **tại thời điểm thực thi**, policy replay/expiry, idempotency key, và cách xử lý trạng thái không còn hợp lệ.

### Scheduled/system operations là nghiệp vụ riêng

Một job dọn dữ liệu cũ có thể cần quyền nhiều tenant, khác quyền của một user chỉnh sửa tài liệu của mình. Đừng thêm method public `updateWithoutSecurity(...)` cho job rồi để mọi bean gọi được.

Thiết kế thay thế:

- Có **service identity** được xác minh với authority chuyên dụng, ví dụ `document:maintenance`, chỉ được cấp cho workload phù hợp.
- Có use case `archiveEligibleForTenant(...)` với rule scope nghiệp vụ riêng; kiểm tra tenant/job purpose và giới hạn tập dữ liệu.
- Nếu job không chạy trong Spring SecurityContext, policy service nhận một ngữ cảnh **được tạo và xác minh bởi infrastructure tin cậy**. Không xem một DTO do caller tùy ý tạo là chứng cứ đủ.
- Ghi audit về job identity, operation, tenant, lượng bản ghi và kết quả; không log credential/token.
- Test chắc chắn endpoint/user thường không thể gọi đường bảo trì chỉ nhờ biết tên method.

Một số hệ thống cần khai thác workload identity thay vì context của user. Trường hợp đó cần hai **ranh giới được bảo vệ rõ ràng**, không tạo một ngoại lệ “bypass” mơ hồ trong use case người dùng.

## 8. @Transactional không thay @PreAuthorize

`@Transactional` điều phối giao dịch: bắt đầu/tham gia transaction, commit/rollback theo quy tắc. Nó không xác minh người gọi, authority hoặc phạm vi bản ghi. Ngược lại, `@PreAuthorize` cho phép hoặc từ chối method nhưng không tự bảo đảm transaction, isolation hay rollback.

Nếu đặt cả hai annotation trên một public service method, có hai loại interceptor: authorization và transaction. **Thứ tự advice có thể được cấu hình**, không nên mặc định mọi phiên bản/trạng thái proxy đều có cùng thứ tự. Test đúng configuration của ứng dụng nếu thứ tự có ý nghĩa với side effect, audit hoặc performance.

Một cách triển khai an toàn cho lệnh ghi:

1. Chặn quyền thực thi hành động tại đầu service boundary, trước phần thân method.
2. Trong transaction, lấy object theo tenant/scope đã xác thực.
3. Kiểm tra policy trên chính object, trạng thái và điều kiện nghiệp vụ.
4. Chỉ sau các bước trên mới mutate/ghi; exception bảo mật phải khiến thao tác không thành công.
5. Commit theo quy tắc transaction; log/audit/outbox theo hợp đồng và không để side effect bên ngoài xảy ra trước khi quyền được xác nhận.

Trong Spring, exception kiểu runtime (chẳng hạn `AccessDeniedException`) mặc định dẫn tới rollback nếu thoát qua transaction interceptor; checked exception có quy tắc rollback khác nếu không cấu hình. Nếu code **bắt rồi nuốt** exception từ một thao tác bị từ chối, transaction ngoài có thể tiếp tục commit một phần dữ liệu. Cần xác định batch là atomic, partial-success có chủ đích, hay all-or-nothing; không tạo trạng thái “một số item lách kiểm tra”.

**Cảnh báo về `@PostAuthorize` cho lệnh ghi:** Nó được đánh giá **sau khi method chạy**. Nếu side effect đã được commit theo thứ tự transaction advice hoặc đã gọi dịch vụ ngoài, từ chối ở bước hậu kiểm không bảo đảm hoàn tác. Với write, ưu tiên preauthorization và resource policy **trước mutation**. Dùng `@PostAuthorize` thích hợp cho một số tình huống read authorization có chủ đích, có kiểm soát việc truy xuất dữ liệu trước đó.

## 9. Ranh giới giao dịch và TOCTOU

*Time of check to time of use* (TOCTOU) xảy ra khi hệ thống kiểm tra quyền ở thời điểm T1, nhưng tài liệu/ACL thay đổi ở T2 trước khi ghi.

~~~text
T1: check user A can edit document 7
    |
    +--- another transaction revokes A's membership
    |
T2: UPDATE document 7
~~~

Một `@PreAuthorize` chỉ kiểm tra authority chung sẽ không phát hiện thay đổi quyền trên tài liệu. Đặt kiểm tra domain policy ở gần thao tác ghi, trong transaction phù hợp, giảm khoảng cách nhưng **không tự loại bỏ mọi race**.

Tùy yêu cầu an toàn/nhất quán, có thể dùng:

- Query update ràng buộc theo tenant và permission, ví dụ `UPDATE ... WHERE id = :id AND tenant_id = :tenant AND ...`, kiểm tra số dòng cập nhật.
- Optimistic locking với `@Version` cho entity, hoặc pessimistic lock trên tài nguyên liên quan nếu chính sách nghiệp vụ yêu cầu.
- Transaction isolation và chiến lược đồng bộ ACL phù hợp; không mặc định việc đọc trong một transaction đồng nghĩa ACL không thể thay đổi.
- Với dịch vụ quyền ở ngoài database, định nghĩa rõ độ mới của quyết định, expiry/revocation, timeout, retry và cách từ chối khi không có quyết định hợp lệ.

Không cần áp dụng mức isolation cao nhất cho mọi thao tác. Hãy chọn dựa trên hậu quả của race, throughput và tính nhất quán cần thiết.

## 10. Những “đường tắt” thường phá vỡ ranh giới

### 10.1. @PreAuthorize trên private/helper method

~~~java
private void assertUserAllowed() { /* ... */ }
~~~

Nếu chỉ đặt annotation bảo mật trên private helper, proxy Spring AOP thông thường không chặn lời gọi nội bộ đến helper. **Sửa:** đặt rule trên public use-case method qua proxy, hoặc gọi policy Java trực tiếp trong method trước mutation.

### 10.2. Tạo service bằng new

~~~java
DocumentCommandService service = new DocumentCommandService(...);
service.rename(7L, "New title");
~~~

Object không được Spring quản lý như một bean proxy, nên annotation method security và transaction có thể không có hiệu lực. **Sửa:** inject service được Spring quản lý, test thông qua application context.

### 10.3. Caller đi thẳng tới repository

~~~java
documentRepository.deleteById(id);
~~~

Repository có thể không kiểm tra tenant/ACL nếu method dùng ID thô. **Sửa:** giới hạn các module được gọi repository, buộc các adapter đi qua application service, thiết kế query theo scope và thêm test kiến trúc để ngăn bypass.

### 10.4. Chỉ khóa URL nhưng mở lối message/CLI

SecurityFilterChain áp dụng theo request HTTP; một message handler không tự nhận rule đó. **Sửa:** mỗi adapter xác thực nguồn rồi gọi use case/authorization domain có hợp đồng cụ thể.

### 10.5. Dùng role chung thay quyền trên resource

`hasRole('ADMIN')` hoặc `hasAuthority('document:write')` có thể cho phép một use case, nhưng chưa chắc được tác động mọi tenant/owner. **Sửa:** kiểm tra scope thực tế trên từng tài nguyên.

### 10.6. Gán principal mặc định trong worker

Nếu scheduled task thiếu authentication, tự tạo token “superuser” không có quy trình cấp phát/thu hồi/audit sẽ làm mất trust boundary. **Sửa:** workload identity hoặc guard system operation riêng, chỉ nhận credentials từ nguồn tin cậy.

### 10.7. @Async không mang SecurityContext

Với security context gắn với thread trong xử lý imperative, chuyển sang thread khác làm mất context nếu không có propagation phù hợp. **Sửa:** dùng cơ chế truyền context được quản lý như `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextRunnable` khi thực sự cần, hoặc đánh giá lại identity ở worker. Chỉ truyền context từ nguồn đáng tin; dọn context sau xử lý để không lẫn người dùng giữa các task.

Với WebFlux/reactive, security context dùng Reactor context; không áp dụng máy móc `ThreadLocal` và transaction manager imperative cho pipeline reactive. Cần kiểm thử cách truyền context và thời điểm subscription của stack thực tế.

### 10.8. Mở API “internal” không có authorization

Nhãn `internal` trong class/package hoặc việc chạy trong cùng JVM không tạo quyền. Một caller đã có reference tới bean vẫn có thể thử gọi method. **Sửa:** định nghĩa rõ capability và kiểm tra ở ranh giới; internal helper cần hẹp quyền truy cập, không để public alternative bypass tồn tại.

## 11. Một pattern giao diện: mọi adapter vào cùng một use case người dùng

Với HTTP, adapter có thể rất mỏng:

~~~java
@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final DocumentCommandService commands;

    public DocumentController(DocumentCommandService commands) {
        this.commands = commands;
    }

    @PatchMapping("/{id}/title")
    public ResponseEntity<Void> rename(
            @PathVariable long id,
            @RequestBody RenameRequest request) {
        commands.rename(id, request.title());
        return ResponseEntity.noContent().build();
    }
}
~~~

Một service khác cũng gọi bean đã inject:

~~~java
@Service
public class DocumentWorkflowService {
    private final DocumentCommandService commands;

    public DocumentWorkflowService(DocumentCommandService commands) {
        this.commands = commands;
    }

    public void renameFromWorkflow(long id, String title) {
        commands.rename(id, title);
    }
}
~~~

Điều kiện tiên quyết: workflow thực sự đại diện cho actor đã xác thực trong security context hiện hành. Nếu không có actor, `@PreAuthorize` phải từ chối. Mã ở hai ví dụ là **mảnh ghép ứng dụng Spring**: cần DTO, bean, dependency và cấu hình security; không phải chương trình Java độc lập.

Cách này cũng cho phép tách ranh giới rõ theo nghiệp vụ thay vì có một “God service” phục vụ cả user, job, import, maintenance bằng các cờ `skipAuthorization=true`. Mỗi use case công khai cần hợp đồng quyền có thể đọc và test độc lập.

## 12. Java 17 độc lập: một chính sách được dùng ở nhiều lối vào

Đoạn Java sau không có Spring để chứng minh nguyên lý: **số lượng điểm vào có thể thay đổi, nhưng guard ở service vẫn chạy trong mọi đường gọi**. Nó không mô phỏng Spring proxy, transaction hay identity propagation.

Tạo tệp `ServiceBoundaryDemo.java`:

~~~java
import java.util.Set;

public class ServiceBoundaryDemo {
    record Actor(String name, String tenant, Set<String> authorities) { }

    static final class Document {
        private final int id;
        private final String tenant;
        private final String owner;
        private String title;

        Document(int id, String tenant, String owner, String title) {
            this.id = id;
            this.tenant = tenant;
            this.owner = owner;
            this.title = title;
        }
    }

    static final class DocumentService {
        private final Document document =
                new Document(7, "north", "an", "Draft");

        void rename(Actor actor, int documentId, String title) {
            if (actor == null
                    || actor.authorities() == null
                    || !actor.authorities().contains("document:write")
                    || !actor.tenant().equals(document.tenant)
                    || !actor.name().equals(document.owner)
                    || documentId != document.id) {
                throw new SecurityException("Denied");
            }
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("Invalid title");
            }
            document.title = title;
        }

        String title() {
            return document.title;
        }
    }

    static void call(String channel, Runnable operation) {
        try {
            operation.run();
            System.out.println(channel + ": allowed");
        } catch (SecurityException exception) {
            System.out.println(channel + ": denied");
        }
    }

    public static void main(String[] args) {
        DocumentService service = new DocumentService();
        Actor owner = new Actor(
                "an", "north", Set.of("document:write"));
        Actor outsider = new Actor(
                "binh", "north", Set.of("document:write"));

        call("http", () -> service.rename(owner, 7, "Reviewed"));
        call("message", () -> service.rename(
                outsider, 7, "Overwritten"));
        call("internal", () -> service.rename(
                null, 7, "Bypassed"));
        System.out.println("title: " + service.title());
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac ServiceBoundaryDemo.java
java ServiceBoundaryDemo
~~~

Kết quả chính xác:

~~~text
http: allowed
message: denied
internal: denied
title: Reviewed
~~~

Điều cần học từ demo: một adapter mới không thể bỏ kiểm tra khi **mọi lối vào chỉ có một operation có guard**. Ở ứng dụng thật, `Actor` không được coi là chứng cứ nếu adapter bất kỳ có thể tự tạo với name/tenant/authority giả; nó phải được **xác minh hoặc dựng từ nguồn tin cậy**. Đối với Spring AOP, vẫn phải bảo đảm caller đi qua bean proxy; guard Java được gọi trực tiếp như demo sẽ không có rủi ro self-invocation của annotation.

## 13. Thiết kế test để chứng minh “mọi điểm vào đều được bảo vệ”

### 13.1. Ma trận đường vào × quyền

Lập ma trận cho từng use case nhạy cảm:

| Đường gọi | Có danh tính/authority hợp lệ, đúng resource | Thiếu authority | Đúng authority nhưng sai tenant/ACL | Không có identity |
|---|---|---|---|---|
| HTTP controller | Thành công | Bị từ chối | Bị từ chối | Bị từ chối / yêu cầu login |
| Service gọi service | Thành công qua proxy | Bị từ chối | Bị từ chối | Bị từ chối |
| Message từ nguồn tin cậy | Thành công khi actor/purpose hợp lệ | Bị từ chối | Bị từ chối | Bị từ chối hoặc lỗi xác minh |
| Scheduled system operation | Thành công với workload identity có scope | Bị từ chối | Bị từ chối | Bị từ chối |
| Batch import | Thành công khi tất cả item hợp lệ hoặc theo contract partial | Item trái quyền không được ghi | Không ghi xuyên tenant | Bị từ chối |

Mỗi ô phải kiểm tra **kết quả cuối cùng trong database**, không chỉ HTTP status hoặc exception type. Một request bị 403 nhưng dữ liệu đã commit trước khi hậu kiểm vẫn là lỗi nghiêm trọng.

### 13.2. Kiểm thử qua bean Spring thực tế

Tạo integration test với `@SpringBootTest` hoặc slice test phù hợp, inject service từ application context. Với HTTP dùng `MockMvc` hoặc test client tương ứng; với method security có thể dùng `@WithMockUser`/custom security context khi quyền phụ thuộc principal custom hoặc claim tenant.

Các phép thử cần có:

1. Người không có `document:write` gọi trực tiếp bean `DocumentCommandService.rename(...)`: bị từ chối và không cập nhật document.
2. Người có authority nhưng sai tenant/owner: bị từ chối, kể cả đoán đúng ID.
3. Batch service gọi bean con qua dependency injection: từng phần tử vẫn được kiểm tra.
4. Một biến thể dùng `this.rename(...)` ở cùng bean minh họa bypass proxy; xác nhận production không có đường gọi tương tự ở các điểm nhạy cảm.
5. Message event tự khai `userId/tenantId` giả: không làm đổi tài liệu ngoài quyền.
6. Job thiếu workload identity hoặc sai job purpose: không thực thi.
7. Nếu một batch có item bị từ chối, xác nhận rollback toàn bộ hoặc partial-success **đúng với contract đã công bố**, không commit ngẫu nhiên.
8. Với async và retry, xác nhận security context/actor scope không bị rò giữa task và không bị dùng lại sau khi quyền bị thu hồi.
9. Nếu có `@PostAuthorize` trên lệnh ghi, kiểm tra side effect/commit khi bị deny để chứng minh không có rủi ro; thông thường nên chuyển kiểm tra vào trước mutation.
10. Với tên method overload, proxy JDK/class-based hoặc final method, xác nhận annotation thực sự kích hoạt trên method đang được gọi.

### 13.3. Kiểm thử kiến trúc và quan sát vận hành

Một số lỗi không thể bắt bằng unit test của từng service:

- Dùng ArchUnit hoặc rule module để cấm adapter/controller/listener truy cập trực tiếp repository ghi, trừ các module được phê duyệt rõ.
- Rà soát mọi public method thao tác dữ liệu có side effect: method nào là entrypoint, method nào là helper, policy đặt ở đâu.
- Bảo đảm audit ghi actor thực, trust source, action, resource ID, tenant, result và correlation ID; không ghi token hoặc thông tin nhạy cảm.
- Giám sát số `AccessDeniedException`, lỗi policy service, request thiếu scope, transaction rollback, truy cập sai tenant và message retry bất thường.
- Chạy test với cấu hình proxy/transaction giống production, tránh chỉ unit test object được tạo bằng `new` rồi kết luận annotation đã hoạt động.

Mục tiêu của test là chứng minh tính **không thể đi vòng** trong những đường gọi được hỗ trợ và những đường gọi mà codebase có thể tạo ra, không phải chỉ chứng minh một controller có annotation.

## 14. Checklist thiết kế khi thêm một điểm vào mới

Trước khi thêm controller, message listener, cron job hoặc service method:

1. Xác định use case và resource, ghi rõ authority và điều kiện owner/tenant/ACL.
2. Xác minh caller identity theo đúng transport; thiếu identity không được gán quyền ngầm.
3. Chọn một public application-service boundary hoặc một use case hệ thống chuyên biệt đã bảo vệ.
4. Bảo đảm method security đã được bật và lời gọi đi qua **Spring-managed proxy**.
5. Không tin annotation trên private/final method hoặc lời gọi nội bộ `this.method()` trong proxy mode.
6. Phân biệt quyền thao tác tại service với quyền trên tài nguyên tại query/domain policy.
7. Đặt kiểm tra quyền trước side effect và trong transaction phù hợp với yêu cầu nhất quán.
8. Kiểm tra rollback, checked/runtime exceptions, `@PostAuthorize`, retry và giao dịch lồng nhau nếu có.
9. Với async/message/job, xác minh identity propagation, replay/idempotency và không mặc định quyền admin.
10. Không cho adapter bypass use case để gọi repository ghi trực tiếp.
11. Test ít nhất một đường HTTP, một đường non-HTTP, một đường gọi service nội bộ và các trường hợp sai authority/sai tenant/thiếu authentication.
12. Quan sát/audit kết quả, nhưng không log token hoặc thông tin nhạy cảm.

**Tư duy vận hành:** Mỗi lần thêm “đường đi vào” nên làm tăng số adapter được kiểm thử, **không** làm tăng số bản sao của logic authorization. Quyền phải được diễn đạt ở ranh giới service và chính sách tài nguyên chung, với các ngoại lệ hệ thống được định nghĩa và bảo vệ tường minh.

## Tài liệu tham khảo

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và cách Spring AOP proxy gọi authorization interceptor.
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy, self-invocation, JDK proxy/CGLIB và giới hạn interception.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction advice, proxy mode, self-invocation, order và rollback defaults.
- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `SecurityContext` trên thread khác và các wrapper truyền context được quản lý.
