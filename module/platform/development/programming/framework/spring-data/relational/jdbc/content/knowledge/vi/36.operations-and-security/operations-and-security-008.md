# Giới hạn auditing, log và sự kiện đối với yêu cầu truy vết nghiệp vụ

Trong một hệ thống dùng **Spring Data Relational JDBC**, việc truy vết nghiệp vụ không thể chỉ dựa vào các cột created_at/updated_at hoặc log SQL. Những cơ chế này trả lời các câu hỏi khác nhau:

- **Auditing metadata** cho biết ai tạo hoặc sửa một entity và thời điểm nào.
- **Persistence callbacks và lifecycle events** cho biết một thao tác lưu/xóa/tải đang đi qua persistence infrastructure.
- **Application logs và distributed tracing** giúp vận hành tìm request, lỗi, latency và luồng xử lý qua nhiều service.
- **Business audit history và domain events** ghi lại hành động nghiệp vụ có ý nghĩa, ví dụ ai duyệt đơn, thay đổi hạn mức hay hủy hợp đồng.
- **Transactional outbox** giúp lưu sự kiện cần phát ra ngoài cùng transaction với thay đổi dữ liệu.

Các cơ chế này không thay thế lẫn nhau. Auditing annotation không tạo lịch sử đầy đủ mọi lần thay đổi; lifecycle callback không quan sát mọi câu SQL; log có thể bị mất hoặc bị xoay vòng; event trong bộ nhớ không phải hàng đợi bền vững. Khi yêu cầu truy vết nghiệp vụ có tính kiểm toán, cần thiết kế rõ nguồn dữ liệu, transaction boundary, quyền truy cập, retention và cách xử lý các đường ghi ngoài Spring Data JDBC.

## 1. Phân biệt năm loại thông tin truy vết

| Cơ chế | Câu hỏi trả lời | Ví dụ | Giới hạn chính |
|---|---|---|---|
| Spring Data JDBC auditing | Ai tạo/sửa entity và lúc nào? | createdBy, createdDate, lastModifiedBy, lastModifiedDate | Chỉ chạy trên persistence path có auditing callback |
| Entity callbacks/lifecycle events | Persistence operation đang ở giai đoạn nào? | BeforeSave, AfterSave, BeforeDelete | Không phải lịch sử nghiệp vụ bền vững; direct SQL có thể bỏ qua |
| Application logs/tracing | Request nào chạy, lỗi ở đâu, mất bao lâu? | traceId, correlationId, operation, duration | Log có thể bị mất, rotate hoặc bị sửa; không phải audit ledger |
| Business audit record/domain event | Hành động nghiệp vụ nào đã xảy ra? | ORDER_APPROVED, CREDIT_LIMIT_CHANGED | Cần thiết kế schema, actor, payload, retention và transaction |
| Transactional outbox | Sự kiện nào cần được phát ra ngoài một cách đáng tin cậy? | OrderApprovedEvent chờ publish | Cần relay, retry, deduplication và monitoring |

Ví dụ: một nhân viên duyệt đơn hàng.

- created/lastModified metadata cho biết người tạo hoặc sửa aggregate gần nhất.
- Business audit record ghi rõ người đó đã duyệt đơn nào, từ trạng thái nào sang trạng thái nào, lý do gì.
- Log ghi request/trace, kết quả, thời gian xử lý và lỗi nếu có.
- Outbox lưu sự kiện OrderApproved để worker phát đến message broker sau khi transaction commit.

Nếu chỉ có hai cột auditing, hệ thống không thể trả lời đầy đủ ai đã duyệt, duyệt theo quyền nào, lý do gì, trước đó trạng thái là gì và sự kiện đã được gửi sang hệ thống khác chưa.

## 2. Spring Data JDBC auditing ghi nhận điều gì?

Spring Data Relational cung cấp các annotation auditing phổ biến:

- **@CreatedBy:** actor tạo entity.
- **@CreatedDate:** thời điểm tạo.
- **@LastModifiedBy:** actor sửa gần nhất.
- **@LastModifiedDate:** thời điểm sửa gần nhất.

Auditing được bật bằng **@EnableJdbcAuditing**. Framework sử dụng auditing infrastructure và entity callback để điền metadata khi entity đi qua persistence path tương ứng.

Ví dụ:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;
}
~~~

Các cột SQL tương ứng có thể là:

~~~sql
ALTER TABLE purchase_order
    ADD COLUMN created_by VARCHAR(120),
    ADD COLUMN created_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN last_modified_by VARCHAR(120),
    ADD COLUMN last_modified_at TIMESTAMP WITH TIME ZONE;
~~~

Đây là DDL minh họa cho PostgreSQL. Với database khác, chọn timestamp type phù hợp. Nếu bảng đã có cột audit, map tên cột hiện hữu bằng **@Column**; không thêm cột trùng chỉ vì tên Java khác.

Auditing metadata thường biểu diễn trạng thái hiện tại của entity. Sau nhiều lần cập nhật, lastModifiedBy và lastModifiedDate chỉ giữ thông tin lần sửa gần nhất; chúng không lưu toàn bộ lịch sử các thay đổi trước đó.

## 3. Cấu hình AuditorAware và thời gian

CreatedBy và LastModifiedBy cần nguồn cung cấp actor. Spring Data dùng **AuditorAware<T>** để lấy người dùng hiện tại. Trong ứng dụng web, actor thường lấy từ Spring Security; trong batch hoặc scheduler, actor có thể là một service account.

~~~java
@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "auditDateTimeProvider"
)
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }
}
~~~

Đoạn code minh họa dùng Spring Security và Clock của Java. Cần có dependency/configuration Security tương ứng. Nếu ứng dụng không dùng Spring Security, triển khai AuditorAware từ context xác thực riêng.

### Vì sao nên dùng Clock?

Inject Clock giúp:

- Dùng UTC nhất quán.
- Test thời gian bằng clock cố định.
- Tránh gọi Instant.now() rải rác trong domain/service.
- Kiểm soát clock source giữa các môi trường.

Ví dụ test có thể cung cấp Clock.fixed(...) để timestamp xác định. Nếu database cũng tự tạo timestamp bằng default/trigger, phải quyết định rõ timestamp nào là nguồn sự thật. Trộn app clock và DB clock mà không có quy tắc có thể tạo chênh lệch.

### Actor có thể không tồn tại

AuditorAware trả Optional.empty() khi không có actor. Điều này thường xảy ra với:

- Scheduled job.
- Batch import.
- Message consumer.
- System-to-system request.
- Test không thiết lập security context.
- Async task chạy trên thread khác.

Nếu audit columns bắt buộc NOT NULL, cần quy ước actor hệ thống rõ ràng như system:billing-reconciliation hoặc truyền actor context vào use case. Không gán một username giả cho mọi trường hợp vì sẽ làm mất nguồn gốc thực tế.

Không giả định SecurityContext tự truyền qua mọi executor/thread. Với async/message processing, truyền actor/correlation metadata trong message hoặc dùng cơ chế context propagation đã cấu hình.

## 4. Auditing callback hoạt động trên persistence path nào?

Spring Data JDBC sử dụng entity callback để áp dụng auditing metadata trước khi ghi. Auditing infrastructure đăng ký callback tương ứng và cập nhật entity theo mapping.

Những thao tác thường đi qua Spring Data JDBC repository hoặc JdbcAggregateTemplate có thể kích hoạt lifecycle/callback infrastructure:

- Insert aggregate.
- Update aggregate.
- Đọc aggregate.
- Delete aggregate, tùy thao tác và callback tương ứng.

Tuy nhiên, cần phân biệt rõ các đường ghi:

| Đường ghi | Auditing callback của Spring Data JDBC |
|---|---|
| repository.save(aggregate) | Có, theo auditing configuration và entity mapping |
| JdbcAggregateTemplate.insert/update | Đi qua Spring Data JDBC aggregate infrastructure |
| JdbcTemplate.update(...) | Không tự chạy entity auditing callback |
| NamedParameterJdbcTemplate.update(...) | Không tự chạy entity auditing callback |
| MyBatis mapper DML | Không tự chạy Spring Data JDBC callback |
| SQL chạy từ service khác | Không tự chạy callback của ứng dụng này |
| Stored procedure/ETL trực tiếp | Không tự chạy callback Spring Data JDBC |

Đây là giới hạn quan trọng nhất khi có nhiều writer. Nếu một bảng được cập nhật bởi repository, MyBatis, batch job và SQL thủ công, bốn cột auditing do Spring Data JDBC điền không bảo đảm phản ánh mọi thay đổi.

Nếu yêu cầu auditing phải bao phủ tất cả writer, hãy chọn một trong các thiết kế:

1. Chuẩn hóa mọi đường ghi qua application service/repository có auditing.
2. Dùng database trigger để ghi audit ở tầng database, với actor/session context được truyền an toàn.
3. Dùng audit service/API trung tâm và bắt buộc mọi writer tích hợp với nó.
4. Kết hợp database audit cho thay đổi dữ liệu với business audit event cho hành động nghiệp vụ.

Không bật @EnableJdbcAuditing rồi tuyên bố mọi thay đổi trong database đều được audit.

## 5. Auditing aggregate root và owned entities

Spring Data JDBC lưu aggregate như một đơn vị, nhưng audit requirement có thể khác nhau giữa root và child.

~~~text
PurchaseOrder
  id
  status
  last_modified_by
  last_modified_at
  lines
    ├── OrderLine
    │     id
    │     quantity
    │     last_modified_by
    │     last_modified_at
    └── OrderLine
~~~

Nếu cần metadata ở cả root và child, hãy xác định:

- Child có entity metadata riêng và cột audit riêng không?
- Callback có được gọi trên đúng object cần audit trong persistence path cụ thể không?
- Save root có rewrite/delete-insert child rows theo chiến lược mapping hiện tại không?
- Giá trị createdAt của child có được giữ khi child được lưu lại không?
- Direct SQL cập nhật child có tuân thủ cùng quy tắc không?

Không suy luận rằng annotation trên root tự động điền audit columns ở mọi child row hoặc mọi row trong aggregate. Hãy kiểm tra behavior với phiên bản Spring Data JDBC đang dùng bằng integration test và SQL log.

Nếu audit theo từng child operation là yêu cầu quan trọng, một bảng business audit append-only có thể phù hợp hơn việc cố đặt đầy đủ lịch sử lên từng entity row.

## 6. Lifecycle callbacks và lifecycle events khác business events

Spring Data Relational có các callback/event gắn với vòng đời persistence. Những tên thường gặp gồm:

- BeforeConvertCallback
- BeforeSaveCallback
- AfterSaveCallback
- AfterLoadCallback
- BeforeDeleteCallback
- AfterDeleteCallback

Lifecycle events có thể được phát quanh các giai đoạn như trước khi convert/save, sau save, sau load hoặc sau delete.

Callbacks và events giúp mở rộng persistence infrastructure, ví dụ chuẩn hóa metadata, tạo giá trị kỹ thuật hoặc quan sát thao tác persistence. Chúng không tự biểu diễn ý nghĩa nghiệp vụ.

Ví dụ:

- AfterSaveCallback có nghĩa aggregate vừa được lưu qua persistence path.
- ORDER_APPROVED có nghĩa một hành động nghiệp vụ đã được chấp nhận theo rule của domain.
- Hai việc này không tương đương: aggregate có thể được save vì đổi địa chỉ, sửa ghi chú hoặc cập nhật kỹ thuật mà không có nghiệp vụ approve.

### Callback phù hợp với việc gì?

- Điền/chuẩn hóa metadata trước khi convert.
- Kiểm tra hoặc điều chỉnh dữ liệu persistence theo quy tắc kỹ thuật.
- Gắn giá trị cần thiết trước khi lưu.
- Thực hiện logic phụ thuộc entity lifecycle và phải có thứ tự xác định.

### Event phù hợp với việc gì?

- Thông báo cho listener trong application context rằng một persistence lifecycle event đã xảy ra.
- Quan sát, ghi metric hoặc thực hiện phản ứng nội bộ.
- Kết nối một số xử lý phụ thuộc giai đoạn lifecycle.

### Không dùng callback/event thay domain rule

Không đặt quyết định duyệt đơn, tính hạn mức, cấp quyền hoặc xác nhận thanh toán vào một callback chỉ vì callback chạy trước khi lưu. Domain rule nên nằm trong aggregate/domain service/application service để có thể gọi, kiểm thử và hiểu rõ theo use case.

Callbacks không phải nơi phù hợp để gửi email, gọi HTTP hoặc publish message ra ngoài trước khi transaction commit. Nếu thao tác ngoài database thành công rồi transaction rollback, hệ thống bên ngoài đã nhận thông tin không còn đúng.

## 7. EntityCallback và ApplicationEvent: chọn đúng cơ chế

EntityCallback được gọi trực tiếp bởi persistence infrastructure và trả về entity có thể được điều chỉnh. Callback có thể triển khai đồng bộ hoặc reactive tùy API; Spring Data JDBC là imperative JDBC nên dùng callback phù hợp với imperative flow.

Ví dụ callback trước khi convert:

~~~java
@Component
public class OrderNormalizationCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(
            PurchaseOrder aggregate) {

        aggregate.normalizeStatus();
        return aggregate;
    }
}
~~~

Ví dụ là minh họa; với immutable aggregate, callback phải trả về instance mới thay vì mutate object.

Lifecycle event thường được publish qua Spring ApplicationEvent infrastructure và listener có thể dùng @EventListener. Nếu listener cần chạy sau transaction commit, dùng @TransactionalEventListener với phase phù hợp thay vì giả định AfterSaveEvent đồng nghĩa dữ liệu đã commit.

Không phụ thuộc vào thứ tự giữa nhiều callback/event listener nếu chưa cấu hình order rõ ràng. Nếu logic cần thứ tự nghiêm ngặt, đặt nó trong một application service hoặc callback chain có thứ tự xác định.

## 8. Business audit history phải là dữ liệu riêng

Nếu yêu cầu cần trả lời:

- Ai đã thực hiện hành động?
- Hành động gì đã xảy ra?
- Aggregate nào bị tác động?
- Giá trị trước và sau là gì?
- Lý do nghiệp vụ là gì?
- Request/approval nào dẫn đến thay đổi?
- Hành động xảy ra lúc nào?
- Có thành công và commit hay không?

thì nên có business audit table hoặc event store phù hợp, thay vì chỉ dùng created/modified columns.

Ví dụ schema append-only:

~~~sql
CREATE TABLE business_audit (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    action VARCHAR(120) NOT NULL,
    actor_id VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    correlation_id VARCHAR(160),
    causation_id VARCHAR(160),
    reason VARCHAR(1000),
    payload JSONB,
    schema_version INTEGER NOT NULL
);

CREATE INDEX idx_business_audit_aggregate_time
    ON business_audit(aggregate_type, aggregate_id, occurred_at DESC);

CREATE INDEX idx_business_audit_actor_time
    ON business_audit(actor_id, occurred_at DESC);
~~~

DDL trên dùng UUID/JSONB của PostgreSQL. Với database khác, chọn kiểu tương đương và kiểm tra indexing strategy.

### Nội dung audit record

| Trường | Ý nghĩa |
|---|---|
| event_id | ID duy nhất để deduplicate |
| aggregate_type | Loại aggregate |
| aggregate_id | ID của aggregate bị tác động |
| action | Hành động nghiệp vụ |
| actor_id | Người dùng/service account thực hiện |
| occurred_at | Thời điểm nghiệp vụ xảy ra |
| correlation_id | Nhóm các thao tác thuộc một request/workflow |
| causation_id | Sự kiện/command gây ra thay đổi hiện tại |
| reason | Lý do hoặc ghi chú được phép lưu |
| payload | Các giá trị nghiệp vụ cần truy vết |
| schema_version | Phiên bản cấu trúc payload |

Không ghi toàn bộ entity graph hoặc toàn bộ request body một cách mặc định. Chỉ lưu những field cần cho yêu cầu kiểm toán, và xác định cách xử lý dữ liệu cá nhân, bí mật thương mại và dữ liệu nhạy cảm.

### Audit record không nên bị update tùy tiện

Business audit history thường cần append-only semantics. Quyền database nên giới hạn tài khoản runtime ở INSERT/SELECT cần thiết; quyền UPDATE/DELETE chỉ cấp cho quy trình retention/administration được kiểm soát.

Tuy vậy, append-only trong ứng dụng không tự tạo ra tamper-proof storage. Người có quyền database cao vẫn có thể sửa/xóa. Nếu yêu cầu chống sửa đổi mạnh, cần thêm separation of duties, database audit, immutable/WORM storage, signing/hash chain hoặc hệ thống lưu trữ chuyên dụng và kiểm thử quy trình truy cập.

## 9. Ghi business audit trong cùng transaction với thay đổi aggregate

Nếu audit record là bằng chứng rằng một thay đổi đã commit, insert audit row trong cùng transaction với aggregate:

~~~java
@Service
public class ApproveOrderService {

    private final PurchaseOrderRepository orders;
    private final BusinessAuditRepository audit;

    public ApproveOrderService(
            PurchaseOrderRepository orders,
            BusinessAuditRepository audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public void approve(
            Long orderId,
            String actorId,
            String reason,
            String correlationId) {

        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow();

        String previousStatus = order.getStatus();
        order.approve();

        PurchaseOrder saved = orders.save(order);

        audit.insert(new BusinessAuditEntry(
                UUID.randomUUID(),
                "PurchaseOrder",
                saved.getId().toString(),
                "ORDER_APPROVED",
                actorId,
                Instant.now(),
                correlationId,
                null,
                reason,
                previousStatus,
                saved.getStatus()
        ));
    }
}
~~~

Đây là ví dụ minh họa; BusinessAuditRepository có thể là Spring Data JDBC repository hoặc custom JDBC repository. Cần dùng Clock được inject thay cho Instant.now() trực tiếp trong production code nếu cần test thời gian xác định.

Nếu audit insert thất bại và exception thoát khỏi transaction, thay đổi aggregate cũng rollback. Nếu aggregate update thất bại, audit row không được commit. Điều này tạo atomicity cho business state và audit history trong cùng database.

Không insert audit trong một transaction độc lập REQUIRES_NEW nếu ý nghĩa của record là “hành động đã commit”. Nếu transaction ngoài rollback nhưng audit transaction đã commit, lịch sử có thể ghi một hành động chưa bao giờ xảy ra. Có thể có nhu cầu lưu attempt/failure riêng, nhưng hãy đặt tên và semantics rõ, ví dụ ORDER_APPROVAL_ATTEMPTED hoặc ORDER_APPROVAL_FAILED.

## 10. Domain events và sự kiện nghiệp vụ

Domain event biểu diễn một điều có ý nghĩa trong domain, ví dụ:

- OrderApproved.
- PaymentCaptured.
- CreditLimitChanged.
- CustomerAddressChanged.
- InventoryReserved.

Event nên được tạo bởi aggregate/domain logic khi invariant được thỏa mãn, hoặc bởi application service khi điều phối use case. Nó không nên được suy ra chỉ từ việc một row vừa được update.

Một aggregate có thể giữ các domain events chưa phát:

~~~java
public class PurchaseOrder {

    private final List<Object> domainEvents = new ArrayList<>();

    public void approve(String actorId) {
        if (!canApprove()) {
            throw new IllegalStateException("Order cannot be approved");
        }

        String previousStatus = status;
        status = "APPROVED";

        domainEvents.add(new OrderApproved(id, actorId, previousStatus));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(domainEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        domainEvents.clear();
    }
}
~~~

Spring Data repository infrastructure hỗ trợ cơ chế publish domain events từ aggregate root qua các annotation như @DomainEvents và @AfterDomainEventPublication khi repository method tương ứng được gọi. Cần kiểm tra method và lifecycle cụ thể của phiên bản Spring Data đang dùng.

Điều cần nhớ:

- Domain event có semantics nghiệp vụ; lifecycle event có semantics persistence.
- Việc event được publish trong process không đồng nghĩa broker đã nhận.
- @AfterDomainEventPublication không phải bằng chứng event đã được xử lý thành công ở hệ thống ngoài.
- Không dùng danh sách event trong object như một event store bền vững.
- Nếu cần đảm bảo event được phát sau commit và không mất khi process crash, dùng outbox.

## 11. Transactional event listener và giới hạn sau commit

Spring cung cấp @TransactionalEventListener để listener gắn với transaction phase, ví dụ:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderApproved(OrderApproved event) {
        // Gửi thông báo hoặc kích hoạt công việc sau commit.
    }
}
~~~

Các phase thường dùng gồm BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION. Listener mặc định gắn với transaction; nếu không có transaction, event có thể không được xử lý trừ khi cấu hình fallbackExecution.

AFTER_COMMIT giúp tránh gửi thông báo cho một thay đổi đã rollback. Tuy nhiên, nó không đảm bảo delivery bền vững:

1. Database commit thành công.
2. Process crash trước khi listener chạy hoặc trước khi message được gửi.
3. Event không có bản ghi bền vững để retry.

Listener cũng chạy trong process của ứng dụng; exception sau commit không thể rollback dữ liệu đã commit. Nếu listener cần ghi database sau commit, phải thiết kế transaction mới rõ ràng và không giả định transaction cũ vẫn đang hoạt động.

Dùng AFTER_COMMIT cho side effect best-effort hoặc tín hiệu nội bộ khi có thể chấp nhận retry/mất sự kiện. Với thông điệp quan trọng về tài chính, đơn hàng hoặc đồng bộ hệ thống, dùng transactional outbox.

## 12. Transactional outbox cho delivery đáng tin cậy

Outbox lưu business event trong cùng database transaction với aggregate. Một worker/relay đọc các hàng chưa publish và gửi đến message broker hoặc hệ thống đích.

~~~mermaid
flowchart TD
    A["Application service"] --> B["Một transaction"]
    B --> C["Update aggregate"]
    B --> D["Insert outbox event"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Outbox relay"]
    F --> G["Message broker / downstream"]
    G --> H["Consumer deduplicate bằng event_id"]
~~~

Ví dụ bảng:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(status, next_attempt_at, occurred_at);
~~~

Service ghi aggregate và outbox:

~~~java
@Transactional
public void approve(Long orderId, String actorId) {
    PurchaseOrder order = repository.findById(orderId).orElseThrow();
    order.approve(actorId);

    PurchaseOrder saved = repository.save(order);

    outboxRepository.insert(
            OutboxEvent.orderApproved(saved, actorId, clock.instant())
    );
}
~~~

Nếu một trong hai thao tác thất bại, transaction rollback cả hai. Relay chỉ thấy event sau khi commit.

### At-least-once và idempotency

Outbox relay thường cung cấp at-least-once delivery. Một tình huống có thể xảy ra:

1. Relay publish message thành công.
2. Process crash trước khi đánh dấu outbox row là published.
3. Worker khác publish lại cùng event.

Vì vậy, consumer cần deduplicate bằng event_id hoặc idempotency key. Không giả định exactly-once end-to-end chỉ vì dùng outbox.

Relay cần có:

- Retry/backoff và giới hạn attempt.
- Lease/claim hoặc cơ chế tránh nhiều worker xử lý cùng row.
- Dead-letter/manual replay path.
- Metrics cho pending count và oldest event age.
- Cơ chế lưu published_at/status.
- Quy trình xử lý event lỗi vĩnh viễn.
- Retention/cleanup có kiểm soát.

Không giữ database row lock trong khi gọi network broker lâu. Có thể claim theo batch bằng lease hoặc status/locked_until, commit claim, publish ngoài transaction rồi cập nhật kết quả. SQL locking như SKIP LOCKED phụ thuộc database vendor.

## 13. Structured logs cho truy vết request

Log vận hành nên có cấu trúc để tìm kiếm và tương quan. Các field hữu ích:

| Field | Ý nghĩa |
|---|---|
| timestamp | Thời điểm log |
| level | INFO/WARN/ERROR |
| service/environment | Dịch vụ và môi trường |
| trace_id/span_id | Liên kết distributed trace |
| correlation_id | Nhóm các thao tác thuộc một workflow |
| actor_id | Principal đã được xác thực, nếu cần |
| operation | Tên use case |
| aggregate_type/id | Đối tượng nghiệp vụ liên quan |
| outcome | success/failure/rejected |
| duration_ms | Thời gian xử lý |
| error_code | Mã lỗi ổn định |
| retry_count | Số lần thử lại |

Ví dụ log structured:

~~~java
log.info(
        "order approval completed: orderId={}, actorId={}, correlationId={}, outcome={}",
        orderId,
        actorId,
        correlationId,
        "SUCCESS"
);
~~~

Với JSON logging, các field được ghi thành key/value để hệ thống log có thể filter/aggregate. Tránh chỉ ghi một câu tự do dài mà không có field ổn định.

### Correlation ID và Trace ID

Correlation ID liên kết các bước của một business workflow; trace ID/span ID liên kết các span trong distributed tracing. Có thể dùng cả hai vì chúng trả lời các câu hỏi khác nhau.

- HTTP gateway có thể tạo hoặc nhận correlation ID đã được xác thực/kiểm soát.
- Service truyền correlation metadata qua HTTP/message headers.
- Consumer khôi phục context khi xử lý message.
- Async executor cần context propagation phù hợp; MDC của thread hiện tại không tự truyền sang mọi thread.
- Luôn xóa MDC/context sau request/task để tránh rò rỉ dữ liệu giữa các request trong thread pool.

Không tin correlation ID từ client như một danh tính hoặc quyền truy cập. Nó chỉ là khóa tương quan, không phải authentication token.

## 14. Log SQL không phải business audit

SQL log hữu ích để điều tra:

- Query nào chạy?
- Query mất bao lâu?
- Có N+1 không?
- Bind type/parameter nào gây lỗi?
- Transaction đã rollback ở đâu?

Nhưng SQL log không phải lịch sử nghiệp vụ vì:

- Có thể bị tắt, sampling hoặc rotate.
- Có thể thiếu actor/business reason.
- Một câu UPDATE không cho biết hành động nghiệp vụ là gì.
- Parameter có thể bị mask hoặc không được log.
- Log có thể chứa dữ liệu nhạy cảm.
- Không có guarantee lưu trữ lâu dài hoặc tamper resistance.
- Một transaction rollback vẫn có SQL log như thể statement đã được thực thi.

Nếu log ghi UPDATE status='APPROVED', điều đó chưa chứng minh transaction commit. Audit record/outbox trong cùng transaction mới có thể biểu diễn một business change đã commit. Nếu cần ghi cả attempt thất bại, lưu loại event riêng để phân biệt attempted và committed action.

## 15. Những đường ghi bỏ qua auditing và event callback

Một hệ thống có thể có nhiều persistence path:

~~~text
Spring Data JDBC repository
  └── Entity callbacks + auditing + repository events

JdbcTemplate / NamedParameterJdbcTemplate
  └── SQL trực tiếp

MyBatis mapper
  └── SQL qua MyBatis-Spring

Batch/ETL/Stored procedure
  └── Database-side write

External application
  └── Writer khác
~~~

Các đường direct SQL không tự đi qua Spring Data JDBC entity callbacks. Điều này có nghĩa:

- last_modified_by có thể không được cập nhật.
- last_modified_at có thể giữ giá trị cũ.
- EntityCallback/lifecycle event không được phát.
- Domain event không tự được tạo.
- Cache application có thể stale.
- Version column có thể không tăng nếu SQL không tự xử lý.
- Business audit row có thể không được insert.

### Thiết kế đường ghi có kiểm soát

Chọn một quy tắc cho từng aggregate/table:

1. Mọi write đi qua một application service có thể kiểm tra quyền, invariant và audit.
2. Direct SQL chỉ dùng cho các bảng/read model đã xác định, có cơ chế audit/version riêng.
3. Nếu external writer là bắt buộc, dùng database trigger/audit mechanism hoặc contract tích hợp để mọi writer ghi metadata.
4. Có test xác nhận mỗi đường ghi cập nhật đúng audit fields và history.
5. Theo dõi các row không có actor/timestamp bất thường.

Database trigger có thể bao phủ nhiều writer hơn application callback, nhưng trigger không tự biết actor nghiệp vụ nếu ứng dụng không truyền session context an toàn. Không lấy database user chung của connection pool làm actor người dùng cuối.

## 16. Bảo vệ log và audit data

Audit data và logs có thể chứa thông tin nhạy cảm. Hãy thiết kế data minimization và access control ngay từ đầu.

### Không ghi dữ liệu nhạy cảm vào log

Tránh ghi:

- Password, access token, refresh token, API key.
- Session cookie, authorization header.
- Payment card/security code.
- Full request/response body nếu có PII.
- Thông tin sức khỏe hoặc định danh cá nhân không cần thiết.
- SQL bind values chứa dữ liệu bí mật.

Nếu cần trace một record, ưu tiên aggregate ID hoặc opaque correlation ID thay vì log toàn bộ entity.

### Phân quyền và retention

- Runtime app chỉ có quyền INSERT/SELECT audit cần thiết; hạn chế UPDATE/DELETE.
- Admin audit storage có role riêng và được ghi nhận khi truy cập.
- Tách log vận hành khỏi business audit history.
- Định nghĩa retention theo luật/chính sách và mục đích xử lý.
- Có quy trình archive/delete/anonymize dữ liệu hết hạn.
- Bảo vệ backup, export và log sink giống dữ liệu gốc.
- Đồng bộ thời gian hệ thống và dùng timestamp UTC.
- Nếu cần tamper evidence, thiết kế immutable storage/hash/signature và quy trình key management.

Không mặc định giữ audit payload vô thời hạn. Lưu quá nhiều dữ liệu cá nhân có thể tạo rủi ro lớn hơn giá trị truy vết.

## 17. Kiểm thử auditing và actor context

Auditing cần test với thời gian và actor xác định. Không để test phụ thuộc vào đồng hồ hệ thống hoặc SecurityContext đang tồn tại từ test khác.

Ví dụ test configuration với Clock cố định:

~~~java
@TestConfiguration
@EnableJdbcAuditing(
        auditorAwareRef = "testAuditorAware",
        dateTimeProviderRef = "testDateTimeProvider"
)
class TestAuditingConfiguration {

    @Bean
    AuditorAware<String> testAuditorAware() {
        return () -> Optional.of("test-user");
    }

    @Bean
    DateTimeProvider testDateTimeProvider() {
        Instant fixed = Instant.parse("2026-01-10T09:00:00Z");
        return () -> Optional.of(fixed);
    }
}
~~~

Test repository:

~~~java
@DataJdbcTest
@Import(TestAuditingConfiguration.class)
class PurchaseOrderAuditingTest {

    @Autowired PurchaseOrderRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void fillsCreatedAndModifiedMetadataOnInsert() {
        PurchaseOrder saved = repository.save(new PurchaseOrder("DRAFT"));

        Map<String, Object> row = jdbcTemplate.queryForMap("""
                SELECT created_by, created_at,
                       last_modified_by, last_modified_at
                FROM purchase_order
                WHERE id = ?
                """, saved.getId());

        assertThat(row.get("created_by")).isEqualTo("test-user");
        assertThat(row.get("last_modified_by")).isEqualTo("test-user");
    }
}
~~~

Ví dụ cần điều chỉnh constructor, repository và schema. Với test insert/update, kiểm tra cả lần tạo lẫn lần sửa, và xác nhận created fields không bị thay đổi ngoài ý muốn trong khi modified fields được cập nhật theo quy tắc.

### Kiểm thử các trường hợp không có actor

- Không có Authentication.
- Anonymous authentication.
- System/batch actor.
- Message consumer.
- Async thread không có SecurityContext.
- AuditorAware trả Optional.empty.

Nếu cột NOT NULL, test phải xác nhận fallback system actor hoặc lỗi validation có chủ đích. Không để production vô tình ghi null mà không có alert.

## 18. Kiểm thử lifecycle, direct SQL và rollback

Một test suite nên phân biệt:

| Kịch bản | Kỳ vọng |
|---|---|
| Repository insert/update | Auditing metadata được điền |
| Repository save với callback | Callback chạy đúng giai đoạn |
| JdbcTemplate UPDATE | Callback Spring Data JDBC không tự chạy |
| MyBatis UPDATE | Callback Spring Data JDBC không tự chạy |
| Transaction rollback | Aggregate và business audit/outbox cùng rollback |
| AFTER_COMMIT listener | Chỉ chạy khi transaction commit |
| Transaction rollback | AFTER_COMMIT listener không chạy |
| Outbox relay publish hai lần | Consumer deduplicate bằng event ID |
| Aggregate child update | Child audit behavior được xác minh riêng |
| External writer | Database-level audit hoặc integration contract ghi nhận actor/source |

Có thể dùng @RecordApplicationEvents trong Spring test để quan sát application events nếu cần. Với callback, test trực tiếp callback hoặc kiểm tra side effect trên entity/database. Với transaction phase, test commit và rollback qua Spring proxy thay vì gọi listener method trực tiếp.

## 19. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| createdBy/lastModifiedBy luôn null | Chưa cấu hình AuditorAware hoặc không có actor context | Kiểm tra @EnableJdbcAuditing và actor source |
| Timestamp khác kỳ vọng | App clock/timezone và DB clock khác nhau | Dùng Clock/UTC thống nhất và test type |
| Audit columns không đổi khi MyBatis update | Direct SQL bỏ qua entity callback | Cập nhật metadata trong mapper/service hoặc dùng DB audit |
| Audit chỉ có trạng thái cuối | Chỉ dùng LastModified fields | Thêm business audit append-only |
| AfterSave listener gửi message rồi transaction rollback | Listener chạy trước commit | Dùng AFTER_COMMIT hoặc transactional outbox |
| Event mất sau khi DB commit | Process crash trước khi publish | Lưu outbox trong cùng transaction |
| Event bị publish hai lần | Relay crash sau publish trước khi đánh dấu | Consumer idempotency/deduplication |
| Callback không chạy với custom DML | DML không đi qua aggregate persistence | Thiết kế audit cho direct SQL riêng |
| Audit actor là service user chung | Không truyền end-user actor context | Propagate actor metadata có xác thực |
| Log có token/PII | Ghi request/SQL bind quá chi tiết | Redaction, allowlist field và retention |
| Không tìm được request qua nhiều service | Thiếu correlation/trace context propagation | Propagate trace/correlation headers |
| Audit history bị sửa | Dùng table nhưng quyền UPDATE/DELETE rộng | Append-only permission, separation of duties, tamper evidence |
| Callback chứa domain rule | Persistence lifecycle bị dùng làm business workflow | Chuyển rule vào aggregate/application service |

## 20. Quy trình thiết kế truy vết nghiệp vụ

1. **Xác định câu hỏi audit cần trả lời:** actor, action, aggregate, before/after, reason, time và correlation.
2. **Chọn loại dữ liệu:** auditing columns, business audit table, domain event, log hay outbox.
3. **Xác định tất cả writer:** repository, JdbcTemplate, MyBatis, batch, trigger và external service.
4. **Cấu hình actor/time:** AuditorAware, Clock/DateTimeProvider, system actor và UTC.
5. **Bật auditing:** @EnableJdbcAuditing và audit annotations trên các entity cần theo dõi.
6. **Định nghĩa lifecycle hooks:** dùng callback/event cho logic kỹ thuật phù hợp, không thay domain rule.
7. **Ghi business history:** insert append-only audit record trong cùng transaction với aggregate.
8. **Phát event đáng tin cậy:** ghi outbox cùng transaction; relay và consumer idempotent.
9. **Structured logging/tracing:** correlationId, traceId, actor, aggregate ID, outcome và duration.
10. **Bảo vệ dữ liệu:** mask secrets/PII, quyền truy cập, retention, backup và tamper controls.
11. **Kiểm thử từng đường ghi:** repository, direct SQL, MyBatis, batch và external writer.
12. **Theo dõi vận hành:** missing actor, audit failure, outbox lag, duplicate delivery và log ingestion.

### Bảng quyết định nhanh

| Yêu cầu | Cơ chế phù hợp |
|---|---|
| Biết ai tạo/sửa entity lần gần nhất | @CreatedBy/@CreatedDate/@LastModifiedBy/@LastModifiedDate |
| Chuẩn hóa object trước persistence | EntityCallback |
| Quan sát lifecycle persistence trong application | Lifecycle event/ApplicationEvent |
| Ghi hành động nghiệp vụ và lý do | Business audit append-only |
| Liên kết request qua nhiều service | Correlation ID và distributed trace |
| Điều tra SQL/lỗi/latency | Structured application logs và SQL instrumentation |
| Gửi message sau khi commit, chấp nhận best-effort | @TransactionalEventListener(AFTER_COMMIT) |
| Không muốn mất event quan trọng sau commit | Transactional outbox |
| Bao phủ thay đổi từ nhiều writer | Database audit/trigger hoặc write contract chung |
| Chống sửa đổi audit | Quyền append-only, separation of duties, immutable storage/tamper evidence |

**Điểm cốt lõi:** auditing columns ghi người tạo/sửa gần nhất; callback và lifecycle event phản ánh persistence path; log/tracing phục vụ vận hành; business audit history ghi hành động có ý nghĩa; outbox bảo đảm event được lưu cùng transaction để có thể retry. Hãy chọn đúng cơ chế cho từng câu hỏi, bao phủ mọi đường ghi, và kiểm thử cả commit, rollback, actor context, direct SQL và duplicate delivery.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): @EnableJdbcAuditing, AuditorAware và audit metadata.
- [Spring Data Relational — Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): callback và lifecycle event trong Spring Data Relational.
- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): @DomainEvents và @AfterDomainEventPublication.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): @TransactionalEventListener và transaction phases.
- [Spring Framework — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): ApplicationEventPublisher và listener infrastructure.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình logger, levels và logging system.
- [Spring Security — SecurityContext](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): Authentication và SecurityContextHolder.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context qua process và service boundaries.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): lưu message trong cùng database transaction và relay theo cơ chế retry.

