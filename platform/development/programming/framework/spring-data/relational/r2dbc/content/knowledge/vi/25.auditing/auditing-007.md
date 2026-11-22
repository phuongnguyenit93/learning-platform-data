# Phân biệt trường auditing với nhật ký thay đổi nghiệp vụ

Trong một ứng dụng Spring Data R2DBC, entity thường có các trường như `createdAt`, `createdBy`, `lastModifiedAt` và `lastModifiedBy`. Những trường này cho biết bản ghi được tạo khi nào, bởi ai và lần cập nhật gần nhất diễn ra lúc nào. Spring Data Auditing có thể tự động điền các metadata đó trong vòng đời lưu entity.

Tuy nhiên, các trường auditing trên entity không phải là nhật ký lịch sử thay đổi đầy đủ. Khi một bản ghi được cập nhật nhiều lần, `lastModifiedAt` và `lastModifiedBy` chỉ giữ thông tin của lần cập nhật gần nhất. Giá trị cũ bị ghi đè; chúng không cho biết từng thay đổi là gì, lý do thay đổi ra sao hoặc trạng thái trước và sau mỗi lần cập nhật.

Nếu nghiệp vụ cần trả lời các câu hỏi như “Ai đã đổi hạn mức?”, “Giá trị trước và sau là bao nhiêu?”, “Thay đổi được thực hiện vì yêu cầu nào?” hoặc “Trạng thái của đơn hàng đã đi qua những bước nào?”, ứng dụng cần một nhật ký thay đổi nghiệp vụ riêng. Nhật ký này thường được lưu thành các bản ghi append-only, có thể truy vấn theo đối tượng, người thực hiện, thời điểm hoặc mã yêu cầu.

## 1. Trường auditing trên entity là gì?

Spring Data Auditing cung cấp các annotation để lưu metadata tạo và cập nhật của một entity:

| Annotation | Ý nghĩa | Giá trị thường gặp |
|---|---|---|
| `@CreatedDate` | Thời điểm entity được tạo | `Instant`, `LocalDateTime` hoặc kiểu thời gian được hỗ trợ |
| `@CreatedBy` | Người hoặc principal tạo entity | ID người dùng, service account hoặc tên actor |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất | Kiểu thời gian |
| `@LastModifiedBy` | Người hoặc principal sửa entity gần nhất | ID người dùng hoặc service account |

Ví dụ entity:

```java
@Table("customer_account")
public class CustomerAccount {

    @Id
    private UUID id;

    private String displayName;

    private BigDecimal creditLimit;

    @CreatedDate
    private Instant createdAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @LastModifiedBy
    private String lastModifiedBy;
}
```

Các trường này là metadata gắn với trạng thái hiện tại của hàng `customer_account`. Sau lần tạo đầu tiên, `createdAt` và `createdBy` mô tả nguồn gốc của bản ghi. Mỗi lần cập nhật tiếp theo, `lastModifiedAt` và `lastModifiedBy` được cập nhật để phản ánh lần sửa mới nhất.

Ví dụ sau ba lần cập nhật:

| Thời điểm | Actor | Hành động |
|---|---|---|
| 09:00 | `user-17` | Tạo tài khoản, hạn mức 10 triệu |
| 10:15 | `user-42` | Đổi hạn mức thành 15 triệu |
| 14:30 | `admin-3` | Đổi hạn mức thành 20 triệu |

Trạng thái cuối của entity chỉ có thể giữ thông tin như `createdBy = user-17`, `createdAt = 09:00`, `lastModifiedBy = admin-3`, `lastModifiedAt = 14:30`. Hai lần sửa ở 10:15 và 14:30 cùng nội dung thay đổi trước/sau không còn được biểu diễn bằng bốn trường metadata này.

## 2. Bật auditing cho Spring Data R2DBC

Trong cấu hình Java, bật auditing bằng `@EnableR2dbcAuditing`:

```java
@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorAware")
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
```

`ReactiveAuditorAware<T>` cung cấp actor hiện tại dưới dạng publisher. Ví dụ trên lấy tên principal từ reactive security context. Trong ứng dụng thực tế, có thể trả về user ID ổn định thay vì username hiển thị, tùy mô hình định danh của hệ thống.

Nếu ứng dụng không dùng Spring Security, có thể triển khai `ReactiveAuditorAware` theo context quản lý actor của ứng dụng. Với tác vụ nền, import hoặc scheduler, actor có thể là service account như `batch-import` thay vì một người dùng tương tác.

Một số lưu ý khi cấu hình:

- Dependency và phiên bản Spring Data R2DBC phải hỗ trợ auditing tương ứng.
- Bean được tham chiếu trong `auditorAwareRef` phải có tên khớp với cấu hình.
- Trong ứng dụng reactive, lấy actor từ Reactor/Security Context; không dựa vào `ThreadLocal` thông thường vì các bước có thể chạy trên thread khác.
- Không tin một trường `createdBy` hoặc `modifiedBy` do client gửi lên. Actor phải được xác định ở phía server từ danh tính đã xác thực hoặc từ danh tính service.
- Nếu không có actor, hãy quyết định rõ có cho phép giá trị null hay dùng một principal hệ thống; không gán một người dùng giả chỉ để tránh null.

Với Spring Boot, cấu hình auditing vẫn cần được bật rõ ràng nếu auto-configuration của ứng dụng không tự bật tính năng đó. Không nên giả định chỉ thêm các annotation vào entity là đủ.

## 3. Spring Data Auditing được thực hiện ở thời điểm nào?

Spring Data sử dụng cơ chế entity callback để điền metadata vào entity trong quy trình persistence. Các trường tạo/cập nhật được xử lý trước khi dữ liệu được ghi xuống database. Vì vậy, chúng phản ánh metadata của lần lưu đang thực hiện.

Ví dụ, khi gọi:

```java
accountRepository.save(account);
```

Spring Data có thể điền `createdAt`/`createdBy` cho entity mới hoặc `lastModifiedAt`/`lastModifiedBy` cho entity đã tồn tại, tùy trạng thái và cấu hình auditing. Các giá trị này được đưa vào mapping để ghi cùng hàng entity.

Auditing hoạt động trong các đường persistence entity của Spring Data như repository hoặc `R2dbcEntityTemplate` khi được cấu hình đúng. Nếu ứng dụng chạy SQL trực tiếp bằng `DatabaseClient` hoặc R2DBC SPI, không nên giả định entity auditing callback sẽ tự động được gọi. Với câu lệnh SQL tường minh, ứng dụng cần tự cập nhật các cột metadata trong câu lệnh hoặc chuyển thao tác qua abstraction entity phù hợp.

Ví dụ SQL trực tiếp cần chủ động đặt metadata:

```java
databaseClient.sql("""
        UPDATE customer_account
        SET credit_limit = :limit,
            last_modified_at = :modifiedAt,
            last_modified_by = :modifiedBy
        WHERE id = :id
        """)
    .bind("limit", newLimit)
    .bind("modifiedAt", clock.instant())
    .bind("modifiedBy", actorId)
    .bind("id", accountId)
    .fetch()
    .rowsUpdated();
```

Ở đây code tự cung cấp thời gian và actor vì nó đang thực thi SQL trực tiếp. Nên dùng `Clock` được inject để có thể kiểm soát thời gian trong test, thay vì gọi `Instant.now()` rải rác trong code.

## 4. Giới hạn của bốn trường auditing

Các trường `created*` và `lastModified*` hữu ích cho việc hiển thị và vận hành, nhưng không cung cấp một lịch sử thay đổi hoàn chỉnh.

| Câu hỏi cần trả lời | Trường auditing có đủ không? |
|---|---|
| Ai tạo bản ghi? | Có, nếu `@CreatedBy` được cấu hình và dữ liệu được lưu đúng. |
| Bản ghi được tạo khi nào? | Có, nếu `@CreatedDate` được cấu hình. |
| Ai sửa bản ghi gần nhất? | Có, qua `@LastModifiedBy`. |
| Lần sửa gần nhất diễn ra khi nào? | Có, qua `@LastModifiedDate`. |
| Những lần sửa trước đó diễn ra khi nào? | Không. |
| Mỗi lần sửa đã đổi trường nào? | Không. |
| Giá trị trước và sau mỗi lần sửa? | Không. |
| Vì sao người dùng thực hiện thay đổi? | Không, trừ khi ứng dụng lưu lý do riêng. |
| Thay đổi thuộc request, ticket hoặc workflow nào? | Không, trừ khi ứng dụng lưu correlation/reference riêng. |
| Có thể khôi phục trạng thái ở một thời điểm cũ không? | Không thể chỉ dựa vào các trường metadata này. |

Vì vậy, không nên dùng `lastModifiedBy` làm bằng chứng duy nhất cho mọi thao tác đã xảy ra. Trường này chỉ cho biết actor của lần sửa gần nhất được ghi nhận trên entity.

## 5. Nhật ký thay đổi nghiệp vụ là gì?

Nhật ký thay đổi nghiệp vụ (business change log hoặc business audit trail) lưu lại các hành động có ý nghĩa đối với nghiệp vụ. Mỗi lần thay đổi được ghi thành một bản ghi riêng, thay vì ghi đè thông tin của lần trước.

Một bản ghi nhật ký thường chứa:

- **Đối tượng:** loại aggregate/entity và định danh của đối tượng bị thay đổi.
- **Hành động:** ví dụ `CREDIT_LIMIT_CHANGED`, `ORDER_APPROVED`, `ACCOUNT_SUSPENDED`.
- **Actor:** người dùng, service hoặc hệ thống thực hiện hành động.
- **Thời điểm:** thời điểm nghiệp vụ được ghi nhận.
- **Trước và sau:** giá trị cũ/mới hoặc snapshot cần thiết để giải thích thay đổi.
- **Lý do:** lý do nghiệp vụ, ghi chú phê duyệt hoặc mã yêu cầu.
- **Correlation/reference:** request ID, ticket ID, workflow ID hoặc command ID để liên kết các bước.

Không phải mọi thao tác SQL đều cần một business audit entry. Nhật ký nên mô tả hành động có ý nghĩa nghiệp vụ, ví dụ “hạn mức tín dụng được tăng từ 10 triệu lên 15 triệu theo yêu cầu đã duyệt”, thay vì chỉ ghi “UPDATE row 123”.

## 6. So sánh trường auditing, nhật ký nghiệp vụ và log kỹ thuật

Ba loại dữ liệu thường cùng xuất hiện trong một hệ thống nhưng có mục đích khác nhau:

| Tiêu chí | Trường Spring Data Auditing | Nhật ký thay đổi nghiệp vụ | Log kỹ thuật/application log |
|---|---|---|---|
| Mục tiêu | Metadata tạo và sửa gần nhất của entity | Lịch sử hành động nghiệp vụ | Chẩn đoán, giám sát và điều tra lỗi hệ thống |
| Dạng lưu | Cột trên hàng entity | Bản ghi riêng, thường append-only | File log hoặc hệ thống log tập trung |
| Số bản ghi | Một bộ metadata hiện tại cho mỗi entity | Có thể có nhiều bản ghi cho một entity | Nhiều dòng theo request, component hoặc process |
| Nội dung | Ai tạo/sửa và khi nào | Ai làm gì, đối tượng nào, trước/sau, lý do | Mức log, message, stack trace, latency, correlation ID |
| Khi entity cập nhật | Ghi đè metadata sửa gần nhất | Thêm entry mới cho hành động cần lưu vết | Ghi sự kiện kỹ thuật nếu cấu hình yêu cầu |
| Dùng để khôi phục lịch sử | Không | Có thể hỗ trợ, nếu lưu đủ dữ liệu và quy tắc replay rõ ràng | Không nên dùng làm nguồn dữ liệu khôi phục nghiệp vụ |
| Quyền truy cập | Theo quyền đọc entity | Thường cần quyền audit riêng, hạn chế sửa/xóa | Theo chính sách vận hành và bảo mật log |

Log kỹ thuật không thay thế business audit trail. Một dòng log như `Updated customer 123` có thể thiếu actor đáng tin cậy, giá trị trước/sau, lý do và bảo đảm lưu bền vững. Ngược lại, không nên đưa stack trace, SQL nhạy cảm hoặc mọi thông tin debug vào nhật ký nghiệp vụ.

## 7. Thiết kế bảng nhật ký thay đổi

Một bảng đơn giản có thể lưu các thay đổi của nhiều loại aggregate:

```sql
CREATE TABLE business_change_log (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    action VARCHAR(120) NOT NULL,
    actor_id VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT,
    correlation_id VARCHAR(160),
    before_state TEXT,
    after_state TEXT
);

CREATE INDEX ix_change_log_aggregate_time
    ON business_change_log (aggregate_type, aggregate_id, occurred_at);

CREATE INDEX ix_change_log_actor_time
    ON business_change_log (actor_id, occurred_at);
```

Ví dụ dùng `TEXT` cho `before_state` và `after_state` để minh họa payload đã serialize. Nếu database hỗ trợ JSON/JSONB và ứng dụng cần truy vấn từng thuộc tính, có thể chọn kiểu JSON tương ứng cùng codec/converter phù hợp. Kiểu timestamp, UUID và index cần điều chỉnh theo database thực tế.

Một số quyết định thiết kế cần làm rõ:

- `aggregate_type` phải là tên loại nghiệp vụ ổn định, không nhất thiết là tên class Java có thể thay đổi khi refactor.
- `aggregate_id` có thể là chuỗi để hỗ trợ nhiều kiểu khóa, nhưng cần định dạng thống nhất.
- `action` nên là mã hành động ổn định, có thể dùng enum/mã domain thay vì lưu câu mô tả tự do làm khóa phân loại.
- `actor_id` nên là định danh ổn định; nếu cần hiển thị tên, có thể lưu thêm snapshot tên tại thời điểm hành động.
- `occurred_at` nên có quy ước múi giờ rõ ràng, thường lưu instant UTC.
- `reason` nên có giới hạn độ dài và quy tắc lọc dữ liệu nhạy cảm.
- `correlation_id` giúp nối log nghiệp vụ với request và trace kỹ thuật, nhưng không thay thế nội dung audit.
- Snapshot trước/sau chỉ nên chứa trường cần thiết; tránh sao chép toàn bộ entity nếu có thông tin bí mật hoặc dữ liệu cá nhân không cần lưu.

## 8. Ví dụ ghi nhật ký khi thay đổi hạn mức

Giả sử nghiệp vụ cho phép nhân viên có quyền thay đổi hạn mức tín dụng. Entity hiện tại có `creditLimit`, còn nhật ký cần lưu giá trị trước và sau, actor và lý do.

Một model nhật ký có thể như sau:

```java
@Table("business_change_log")
public class BusinessChangeLog {

    @Id
    private UUID id;

    private String aggregateType;
    private String aggregateId;
    private String action;
    private String actorId;
    private Instant occurredAt;
    private String reason;
    private String correlationId;
    private String beforeState;
    private String afterState;

    public static BusinessChangeLog creditLimitChanged(
            UUID accountId,
            String actorId,
            Instant occurredAt,
            String reason,
            String correlationId,
            BigDecimal oldLimit,
            BigDecimal newLimit) {

        return new BusinessChangeLog(
            UUID.randomUUID(),
            "CustomerAccount",
            accountId.toString(),
            "CREDIT_LIMIT_CHANGED",
            actorId,
            occurredAt,
            reason,
            correlationId,
            oldLimit.toPlainString(),
            newLimit.toPlainString()
        );
    }
}
```

Constructor và getter/setter đã được lược bỏ để tập trung vào cấu trúc dữ liệu. Trong dự án, có thể dùng record/immutable object hoặc builder.

Service ghi entity và change log trong cùng transaction R2DBC:

```java
@Service
public class CreditLimitService {

    private final CustomerAccountRepository accountRepository;
    private final BusinessChangeLogRepository changeLogRepository;
    private final Clock clock;

    @Transactional
    public Mono<CustomerAccount> changeLimit(
            UUID accountId,
            BigDecimal newLimit,
            String reason,
            String actorId,
            String correlationId) {

        return accountRepository.findById(accountId)
            .switchIfEmpty(Mono.error(
                new AccountNotFoundException(accountId)))
            .flatMap(current -> {
                BigDecimal oldLimit = current.getCreditLimit();
                current.setCreditLimit(newLimit);

                return accountRepository.save(current)
                    .flatMap(saved -> {
                        BusinessChangeLog entry =
                            BusinessChangeLog.creditLimitChanged(
                                accountId,
                                actorId,
                                clock.instant(),
                                reason,
                                correlationId,
                                oldLimit,
                                saved.getCreditLimit()
                            );

                        return changeLogRepository.save(entry)
                            .thenReturn(saved);
                    });
            });
    }
}
```

Ví dụ giả định cả hai repository dùng cùng `ConnectionFactory` và transaction manager. Khi đó, thay đổi hạn mức và bản ghi lịch sử có thể commit hoặc rollback cùng nhau. Nếu lưu entity thành công nhưng ghi change log thất bại, lỗi trong reactive chain làm transaction rollback; không để entity đổi mà thiếu nhật ký tương ứng.

`actorId` và `correlationId` trong ví dụ được truyền vào service để làm rõ dữ liệu cần có. Trong ứng dụng thực tế, actor phải được lấy từ security context hoặc context tin cậy ở server, không lấy trực tiếp từ request body. Lý do thay đổi cũng cần được validate theo quy tắc nghiệp vụ.

## 9. Ghi nhật ký thay đổi theo hành động nghiệp vụ, không chỉ theo từng cột

Có hai cách phổ biến để mô tả thay đổi:

**Field-level diff:** lưu tên trường cùng giá trị cũ và mới, ví dụ:

```json
{
  "changes": [
    {
      "field": "creditLimit",
      "before": "10000000.00",
      "after": "15000000.00"
    }
  ]
}
```

**Business event:** lưu hành động có ý nghĩa, ví dụ `CREDIT_LIMIT_CHANGED`, cùng payload mô tả hạn mức trước/sau và lý do phê duyệt.

Field-level diff phù hợp khi cần hiển thị lịch sử chỉnh sửa chi tiết cho nhiều thuộc tính. Business event phù hợp khi hệ thống cần phân loại hành động theo ngôn ngữ nghiệp vụ và có thể dùng lại trong báo cáo hoặc workflow.

Không phải mọi thay đổi kỹ thuật đều cần tạo một event nghiệp vụ. Ví dụ cập nhật `lastAccessedAt`, đồng bộ cache hoặc sửa metadata nội bộ có thể không phải một hành động cần hiển thị trong lịch sử nghiệp vụ. Xác định rõ danh sách hành động cần lưu sẽ tránh log quá nhiều và làm mờ những thay đổi quan trọng.

## 10. Nhật ký nghiệp vụ không đồng nghĩa Event Sourcing

Business audit trail và Event Sourcing có điểm chung là lưu các sự kiện theo thời gian, nhưng vai trò khác nhau.

| Đặc điểm | Business audit trail | Event Sourcing |
|---|---|---|
| Mục đích chính | Giải thích ai đã thực hiện hành động gì và dữ liệu thay đổi ra sao | Lưu sự kiện làm nguồn sự thật để dựng trạng thái aggregate |
| Nguồn trạng thái hiện tại | Thường vẫn là bảng entity/state hiện tại | Được tính bằng cách áp dụng chuỗi event |
| Nội dung event | Có thể là diff, actor, reason, before/after | Là sự kiện domain đủ để tái tạo trạng thái theo quy tắc domain |
| Thay đổi schema/event | Có thể phục vụ tra cứu lịch sử | Cần versioning/upcasting và tương thích replay lâu dài |
| Đọc dữ liệu hiện tại | Đọc trực tiếp bảng state | Có thể dựng từ event hoặc dùng projection/snapshot |

Một hệ thống có thể lưu audit log bên cạnh mô hình CRUD mà không phải áp dụng Event Sourcing. Nếu muốn dùng event làm nguồn sự thật, cần thiết kế toàn bộ aggregate, event schema, replay, snapshot, projection và xử lý event versioning. Chỉ thêm một bảng `business_change_log` không biến hệ thống thành Event Sourcing.

## 11. Bảo đảm tính nhất quán giữa entity và nhật ký

Nếu yêu cầu là “mỗi thay đổi nghiệp vụ thành công phải có một bản ghi audit tương ứng”, hai thao tác ghi phải nằm trong cùng local transaction database:

1. Đọc trạng thái hiện tại và xác định thay đổi hợp lệ.
2. Cập nhật entity.
3. Tạo change log với actor, action, thời điểm, lý do và dữ liệu trước/sau.
4. Ghi change log.
5. Commit transaction khi cả hai thao tác thành công.

Nếu change log nằm trong một database khác, `R2dbcTransactionManager` của database entity không tự bảo đảm cả hai database commit cùng nhau. Khi đó cần outbox, distributed transaction tương thích hoặc quy trình đồng bộ/compensation riêng.

Nếu nhật ký được dùng để phát message ra broker, có thể ghi business change log hoặc outbox event trong transaction database, rồi publisher gửi sau commit. Không gửi message trực tiếp trong callback `AfterSaveCallback` với giả định callback chỉ chạy sau commit.

## 12. Tính append-only và bảo vệ nhật ký

Nhật ký thay đổi thường cần được bảo vệ chặt hơn bảng entity thông thường. Một số nguyên tắc:

- Chỉ thêm bản ghi mới; ứng dụng nghiệp vụ không nên cập nhật hoặc xóa entry lịch sử đã ghi.
- Dùng database role riêng với quyền `INSERT` và `SELECT` phù hợp; hạn chế `UPDATE`/`DELETE` trên bảng audit.
- Có thể dùng trigger hoặc cơ chế kiểm soát ở database để ngăn sửa/xóa ngoài ý muốn.
- Lưu actor và timestamp từ nguồn tin cậy ở server.
- Có index theo aggregate ID và thời gian để tra cứu lịch sử hiệu quả.
- Thiết kế partition/archival khi dữ liệu lớn và có chính sách retention rõ ràng.
- Hạn chế quyền đọc nhật ký vì before/after có thể chứa dữ liệu nhạy cảm.
- Ghi nhận truy cập hoặc export audit log nếu yêu cầu kiểm soát truy cập cần thiết.

Append-only ở tầng ứng dụng không tự bảo đảm chống giả mạo tuyệt đối. Người có quyền quản trị database vẫn có thể can thiệp dữ liệu nếu không có kiểm soát bổ sung. Với yêu cầu bằng chứng cao, có thể cần lưu trữ bất biến, hash chaining, chữ ký hoặc bản sao audit ở hệ thống có quyền quản trị tách biệt. Các biện pháp này cần được thiết kế và vận hành đúng; chỉ thêm một cột hash không tự tạo ra tính chống sửa đổi.

## 13. Dữ liệu nhạy cảm và chính sách lưu giữ

Không nên sao chép toàn bộ entity vào `before_state` và `after_state` một cách mặc định. Snapshot có thể chứa mật khẩu, token, thông tin thanh toán, dữ liệu cá nhân hoặc trường không cần cho mục đích audit.

Nên áp dụng:

- Allowlist các trường nghiệp vụ cần lưu lịch sử.
- Mask hoặc loại bỏ thông tin bí mật, credential, token và dữ liệu xác thực.
- Không lưu giá trị thẻ thanh toán hoặc bí mật theo cách không được phép.
- Giới hạn độ dài `reason` và loại nội dung được chấp nhận.
- Xác định thời hạn lưu, quy trình archive và xóa theo chính sách pháp lý/nội bộ.
- Phân quyền truy vấn lịch sử theo tenant, vai trò và mục đích sử dụng.
- Tránh đưa snapshot nhạy cảm vào application log hoặc trace.

Nhật ký phục vụ điều tra không có nghĩa phải lưu mọi dữ liệu mãi mãi. Chính sách retention cần cân bằng yêu cầu kiểm toán, quyền riêng tư, chi phí lưu trữ và nghĩa vụ xóa dữ liệu.

## 14. Xử lý cập nhật bằng SQL trực tiếp

Các thao tác `DatabaseClient` hoặc SQL tùy chỉnh có thể bỏ qua entity callback và auditing infrastructure. Nếu một use case dùng SQL trực tiếp để cập nhật bảng entity, cần cập nhật cột `last_modified_*` và tạo business audit entry một cách tường minh.

Ví dụ:

```java
@Transactional
public Mono<Void> updateStatus(
        UUID orderId,
        OrderStatus newStatus,
        String actorId,
        String reason) {

    Instant now = clock.instant();

    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(oldOrder -> {
            OrderStatus oldStatus = oldOrder.getStatus();

            return databaseClient.sql("""
                    UPDATE purchase_order
                    SET status = :status,
                        last_modified_at = :modifiedAt,
                        last_modified_by = :modifiedBy
                    WHERE id = :id
                    """)
                .bind("status", newStatus.name())
                .bind("modifiedAt", now)
                .bind("modifiedBy", actorId)
                .bind("id", orderId)
                .fetch()
                .rowsUpdated()
                .flatMap(count -> {
                    if (count != 1) {
                        return Mono.error(
                            new UnexpectedUpdateCountException(count));
                    }

                    return changeLogRepository.save(
                        OrderStatusChange.of(
                            orderId, oldStatus, newStatus,
                            actorId, now, reason))
                        .then();
                });
        });
}
```

Ví dụ đọc trạng thái cũ rồi cập nhật bằng SQL để minh họa việc ghi audit tường minh. Nếu có nhiều cập nhật đồng thời, cần thêm optimistic version predicate hoặc khóa phù hợp để `oldStatus` phản ánh đúng trạng thái được chuyển đổi. Nếu không, hai transaction có thể cùng đọc một trạng thái cũ và tạo hai bản ghi lịch sử không đúng với thứ tự nghiệp vụ mong muốn.

Với thao tác cập nhật có điều kiện, hãy kiểm tra `rowsUpdated()` và chỉ ghi audit khi database thực sự thay đổi hàng. Nếu update count bằng 0, có thể hàng không tồn tại, version không khớp hoặc predicate không còn đúng; cần diễn giải theo hợp đồng use case.

## 15. Tránh ghi nhật ký trùng hoặc thiếu

Một số tình huống có thể tạo log không chính xác:

- Ghi change log trước khi update, nhưng update thất bại và log vẫn commit ở transaction khác.
- Ghi entity xong rồi ghi log ở transaction riêng; log thất bại khiến trạng thái thay đổi không có lịch sử.
- Retry một command sau timeout nhưng lần đầu đã commit, tạo hai change log cho cùng một hành động.
- Callback sau save và service cùng ghi audit cho một thay đổi, tạo bản ghi trùng.
- Ghi log cho một lệnh update có `rowsUpdated = 0`, dù dữ liệu không thay đổi.

Các biện pháp kiểm soát:

1. Ghi entity và audit entry trong cùng transaction nếu cùng database.
2. Tạo `commandId` hoặc `idempotencyKey` ổn định cho hành động có thể retry.
3. Đặt unique constraint trên event/command ID nếu mỗi command chỉ được ghi nhận một lần.
4. Chỉ tạo change log sau khi đã xác định thay đổi hợp lệ và có số hàng bị ảnh hưởng như mong đợi.
5. Chọn một tầng chịu trách nhiệm ghi business audit; không ghi cùng hành động ở callback và service nếu không có quy tắc chống trùng.
6. Với side effect broker, dùng outbox và consumer idempotency.

## 16. Truy vấn lịch sử thay đổi

Khi lưu mỗi thay đổi thành một hàng riêng, có thể lấy lịch sử theo aggregate:

```java
public interface BusinessChangeLogRepository
        extends ReactiveCrudRepository<BusinessChangeLog, UUID> {

    Flux<BusinessChangeLog>
    findByAggregateTypeAndAggregateIdOrderByOccurredAtDesc(
        String aggregateType, String aggregateId);
}
```

Với lịch sử lớn, nên phân trang hoặc giới hạn theo thời gian thay vì tải toàn bộ. Cần có tie-breaker ổn định như `id` nếu nhiều event cùng timestamp:

```sql
SELECT *
FROM business_change_log
WHERE aggregate_type = :type
  AND aggregate_id = :aggregateId
ORDER BY occurred_at DESC, id DESC
LIMIT :pageSize;
```

Có thể truy vấn theo actor, action hoặc correlation ID để phục vụ điều tra. Index phải phù hợp với các mẫu truy vấn thực tế; không tạo quá nhiều index vì mỗi lần insert audit cũng phải cập nhật index.

## 17. Trường auditing và nhật ký nghiệp vụ có thể dùng cùng nhau

Hai cơ chế không loại trừ nhau. Một entity có thể lưu metadata hiện tại để đọc nhanh, đồng thời có bảng lịch sử để giải thích từng thay đổi.

Ví dụ:

| Nhu cầu | Nguồn dữ liệu |
|---|---|
| Hiển thị “Tạo bởi An lúc 09:00” trên trang chi tiết | `createdBy`, `createdAt` |
| Hiển thị “Cập nhật gần nhất bởi Bình lúc 14:30” | `lastModifiedBy`, `lastModifiedAt` |
| Xem tất cả lần đổi hạn mức trong 6 tháng | `business_change_log` |
| Xem giá trị trước/sau và lý do phê duyệt | Business change log với before/after và reason |
| Điều tra request gây ra thay đổi | `correlation_id` trong audit entry kết hợp trace/log kỹ thuật |
| Chẩn đoán vì sao câu SQL timeout | Log kỹ thuật, metric và trace |

Các trường auditing giúp truy vấn trạng thái hiện tại nhanh và đơn giản. Nhật ký nghiệp vụ bổ sung chiều lịch sử, còn log kỹ thuật phục vụ vận hành. Thiết kế rõ ba mục đích sẽ tránh biến một bảng entity thành nơi chứa toàn bộ lịch sử và tránh dùng log kỹ thuật làm nguồn bằng chứng nghiệp vụ.

## 18. Checklist thiết kế cho một use case cần lưu lịch sử

Trước khi triển khai, hãy xác định:

1. Những hành động nào thực sự cần lưu vết theo nghiệp vụ?
2. Actor lấy từ security context/service identity nào và có ổn định không?
3. Cần lưu before/after ở cấp trường hay snapshot đã chọn lọc?
4. Lý do, ticket ID, command ID và correlation ID nào cần được lưu?
5. Entity và audit log có thể ghi trong cùng `ConnectionFactory`/transaction không?
6. SQL trực tiếp có cập nhật các cột `lastModified*` và ghi audit tường minh không?
7. Retry có thể tạo audit trùng không; có cần idempotency key/unique constraint không?
8. Ai được phép đọc lịch sử và dữ liệu nhạy cảm nào phải được mask hoặc loại bỏ?
9. Chính sách retention, archive và bảo vệ append-only là gì?
10. Có integration test xác nhận entity và change log cùng commit/rollback không?

## 19. Kiểm thử tính nhất quán của audit

Nên kiểm tra cả trường hợp thành công và lỗi:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Tạo entity qua repository | `createdAt` và `createdBy` được điền theo cấu hình. |
| Cập nhật entity qua repository | `lastModifiedAt` và `lastModifiedBy` phản ánh lần sửa mới. |
| Cập nhật entity nhiều lần | Metadata entity chỉ giữ lần sửa gần nhất; change log có đủ từng entry được yêu cầu. |
| Lưu entity thành công, ghi audit thất bại trong cùng transaction | Cả entity và audit entry rollback. |
| Transaction rollback sau khi tạo audit entry | Không còn entity change hoặc audit entry chưa commit. |
| Retry cùng command | Không tạo change log trùng nếu command được thiết kế idempotent. |
| SQL trực tiếp | Cột metadata và business audit được cập nhật rõ ràng. |
| Truy cập lịch sử khác tenant | Không đọc được audit entry ngoài phạm vi quyền. |

Unit test có thể kiểm tra logic tạo event và nội dung before/after. Integration test trên database thực tế cần xác nhận transaction, constraint, mapping và quyền truy cập. Với yêu cầu chống sửa đổi cao, cần kiểm thử cả quyền database và quy trình archive/retention.

Trường auditing của Spring Data R2DBC mô tả ai tạo entity và ai sửa entity gần nhất. Nhật ký thay đổi nghiệp vụ lưu từng hành động có ý nghĩa, cùng actor, thời điểm, lý do và dữ liệu trước/sau khi cần. Hai cơ chế nên được dùng bổ sung: metadata trên entity phục vụ trạng thái hiện tại; business audit trail phục vụ lịch sử và khả năng giải thích; log kỹ thuật phục vụ chẩn đoán hệ thống. Khi cần bảo đảm thay đổi và lịch sử luôn nhất quán, hãy ghi chúng trong cùng transaction database, thiết kế idempotency cho retry và bảo vệ nhật ký theo chính sách truy cập, dữ liệu nhạy cảm và retention của tổ chức.
