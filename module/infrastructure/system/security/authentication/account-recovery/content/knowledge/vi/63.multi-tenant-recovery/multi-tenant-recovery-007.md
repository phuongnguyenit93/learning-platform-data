# Tenant recovery audit: kiểm toán khôi phục tài khoản trong hệ thống đa tenant

## 1. Audit recovery phải giữ đúng ranh giới tenant

Trong hệ thống đa tenant, một người dùng có thể tham gia nhiều tổ chức, còn nhân viên hỗ trợ có thể được giao xử lý một số tenant cụ thể. Một sự kiện “MFA reset approved” sẽ thiếu ý nghĩa nếu không biết phê duyệt thuộc tổ chức nào, ai có quyền ở phạm vi đó và thao tác đã ảnh hưởng tới credential nào.

**Tenant recovery audit** là việc ghi nhận, bảo vệ, tra cứu và đối chiếu các sự kiện recovery theo phạm vi tenant được xác định có thẩm quyền. Nó phải vừa phục vụ truy trách nhiệm, vừa ngăn dữ liệu kiểm toán trở thành một đường truy cập chéo tổ chức.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, các sự kiện có thể liên quan mất mật khẩu, MFA, passkey hoặc thiết bị xác thực; đánh giá rủi ro, token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát phiên. Mỗi bước cần giữ được liên hệ với đúng chủ thể, tài khoản và ranh giới quản trị.

Hai yêu cầu phải được đáp ứng đồng thời:

- Tenant có thể xem những bằng chứng recovery thuộc phạm vi họ được phép quản lý.
- Tenant không được biết hồ sơ, bằng chứng, membership hoặc hoạt động của tổ chức khác chỉ vì cùng một người dùng xuất hiện ở cả hai nơi.

Một event có trường `tenantId` chưa đủ. Cần bảo đảm trường đó được xác định đúng, không thể bị tráo ở đường ghi và luôn được thực thi tại đường đọc, tìm kiếm, export và lưu trữ.

## 2. Làm rõ tài khoản thuộc tenant hay danh tính dùng chung

Trước khi thiết kế audit, cần hiểu mô hình danh tính của sản phẩm.

| Mô hình | Ví dụ | Hệ quả với recovery audit |
| --- | --- | --- |
| Tài khoản độc lập theo tenant | Mỗi tổ chức có account và credential riêng | Recovery có thể gắn trực tiếp với một tenant account |
| Principal toàn nền tảng, membership theo tenant | Một danh tính đăng nhập vào nhiều workspace | Thay credential có thể ảnh hưởng nhiều membership; cần phân biệt phạm vi identity và tenant |
| Danh tính liên kết qua provider của tenant | Tổ chức quản lý đăng nhập bằng IdP riêng | Cần ghi provider scope và quyền quản trị tương ứng |
| Tài khoản hỗ trợ có quyền ủy nhiệm | Nhân viên nền tảng xử lý theo access grant | Cần ghi cả actor nền tảng và tenant được phép hỗ trợ |

Một tenant admin có quyền quản lý membership không mặc nhiên được reset credential toàn nền tảng của một người dùng thuộc nhiều tenant. Nếu hệ thống cho phép loại thao tác đó, quyền phải được xác định riêng và tác động phải được kiểm soát rõ ràng.

Audit cần biểu diễn **phạm vi credential bị thay đổi** chứ không chỉ tenant đang được chọn trên giao diện. Có thể phân biệt `TENANT_ACCOUNT`, `TENANT_IDENTITY_LINK` và `GLOBAL_PRINCIPAL` theo mô hình của hệ thống.

Với recovery của danh tính dùng chung, có thể lưu một sự kiện gốc tại miền identity của nền tảng và tạo projection tối thiểu cho từng tenant được phép nhận thông tin. Projection không sao chép danh sách các tenant khác, bằng chứng danh tính hoặc thông tin mà tổ chức nhận không có quyền xem.

## 3. Tenant context phải đến từ nguồn có thẩm quyền

Header, query parameter, subdomain hoặc một trường trong request có thể giúp định tuyến, nhưng không tự chứng minh người gọi có quyền với tenant được nêu.

Đối với một thao tác recovery, máy chủ cần đối chiếu:

1. Actor đã được xác thực là ai?
2. Actor có quyền hoặc access grant hiện hành cho tenant nào?
3. Case, tài khoản đích và credential thuộc phạm vi nào trong nguồn dữ liệu chuẩn?
4. Hành động cụ thể có được phép trong phạm vi đó không?

Tenant của sự kiện được lấy từ kết quả phân giải và kiểm tra tài nguyên, không chỉ chép `X-Tenant-Id` từ request. Nếu client gửi tenant A nhưng case thuộc tenant B, hành động cần bị từ chối hoặc xử lý theo cổng quyền phù hợp; không sửa event thành tenant A để làm nó trông hợp lệ.

Các đường không có phiên người dùng cũng cần tenant context có thẩm quyền: worker, scheduler, webhook và dịch vụ gửi thông báo. Một queue message cần tham chiếu tới case và scope đã được máy chủ xác minh, còn consumer phải kiểm tra ràng buộc nguồn và đối tượng trước khi tạo tác động.

Nếu không xác định được tenant, không mặc định gán vào tenant hiện tại, tenant đầu tiên hoặc một tenant dùng chung có thể đọc rộng. Sự kiện lỗi cần vào luồng bảo vệ dành cho nền tảng hoặc vùng cách ly để điều tra, với phạm vi truy cập rõ ràng.

## 4. Những sự kiện recovery cần có phạm vi tenant

Không chỉ kết quả thành công mới cần audit. Các lần thử sai phạm vi và các quyết định bị chặn giúp phát hiện lạm dụng.

| Nhóm sự kiện | Nội dung cần giải thích |
| --- | --- |
| Khởi tạo recovery | Yêu cầu thuộc tài khoản và tenant scope nào, qua kênh nào |
| Xác minh danh tính | Phương thức, kết quả và tham chiếu bằng chứng phù hợp |
| Đánh giá rủi ro | Quyết định cho tiếp tục, chặn hoặc yêu cầu kiểm tra thêm |
| Phê duyệt | Actor, quyền, phạm vi đã duyệt, case version và thời hạn |
| Cấp hoặc dùng capability | Mục đích, tham chiếu token, scope và kết quả tiêu thụ |
| Thay factor hoặc credential | Loại thay đổi, đối tượng và phạm vi tác động |
| Kiểm soát phiên | Credential hoặc phiên nào thuộc diện thu hồi, kết quả áp dụng |
| Hoàn tất, hủy, hết hạn | Trạng thái cuối và hạn chế còn hiệu lực |
| Truy cập audit | Ai đã tìm kiếm, xem hoặc xuất sự kiện của tenant nào |
| Vi phạm phạm vi | Hành động bị từ chối vì tenant, tài nguyên hoặc quyền không khớp |

Không ghi token thật, secret TOTP, recovery code hoặc mật khẩu. Một token reference opaque và trạng thái tiêu thụ đủ để nối sự kiện mà không biến audit thành nơi chứa khả năng đăng nhập.

Tùy mô hình, sự kiện từ chối có thể chứa thông tin chỉ nền tảng được đọc. Giao diện tenant không nên tiết lộ tên tenant hoặc tài khoản đích ngoài phạm vi chỉ để giải thích rằng một request đã bị từ chối.

## 5. Schema sự kiện và các phạm vi actor khác nhau

Actor thuộc tenant nào, đang được ủy quyền cho tenant nào và đang tác động đến tenant nào là những khái niệm có thể khác nhau.

Một event khái niệm:

```json
{
  "schemaVersion": 1,
  "eventId": "event_example_63",
  "eventType": "RECOVERY_FACTOR_REPLACEMENT_APPROVED",
  "occurredAt": "2030-04-01T08:00:00Z",
  "tenantId": "tenant_example",
  "scopeKind": "TENANT_ACCOUNT",
  "tenantAccountReference": "account_reference",
  "recoveryCaseId": "case_reference",
  "caseVersion": 5,
  "actorReference": "actor_reference",
  "executorReference": "support_service_reference",
  "delegationGrantReference": "delegation_reference",
  "approvalReference": "approval_reference",
  "policyVersion": "tenant_recovery_policy_reference",
  "evidenceReference": "protected_evidence_reference",
  "outcome": "SUCCEEDED",
  "reasonCode": "INDEPENDENT_APPROVAL_ACCEPTED",
  "sourceId": "recovery_service_example",
  "sourceSequence": 927
}
```

Các giá trị chỉ minh họa. Event được tạo từ trạng thái có thẩm quyền và quyết định thực tế, không phải từ nội dung client tự khai là đã được phê duyệt.

Các trường có thể cần bổ sung theo hệ thống:

- Actor khởi xướng khác actor thực thi, nếu có automation hoặc ủy quyền.
- Phạm vi access grant và thời điểm hết hiệu lực của quyền hỗ trợ.
- Credential scope, provider configuration reference hoặc principal reference có quyền đọc riêng.
- Correlation, parent event và tham chiếu thay đổi phiên.
- Phân loại dữ liệu và projection mà một tenant được phép xem.

Không cần đưa tất cả các trường nội bộ vào projection của tenant. Principal ID toàn nền tảng có thể tạo khả năng liên kết một người giữa các tổ chức; có thể dùng tenant-scoped reference cho người xem tenant, còn ánh xạ toàn cục nằm trong miền truy cập điều tra riêng.

## 6. Bảo vệ đường ghi: không để producer tự nhận tenant bất kỳ

Một broker xác thực được service account chỉ chứng minh danh tính producer, chưa chắc chứng minh producer được phát sự kiện cho mọi tenant.

Audit ingestion cần kiểm tra nguồn được phép ghi phạm vi nào, schema nào và loại sự kiện nào. Producer của một tích hợp tenant A không được tự khai `tenantId=B` rồi khiến kho audit chấp nhận như sự kiện có thẩm quyền của B.

Các lớp kiểm soát có thể gồm:

- Access grant hoặc namespace được ràng buộc với producer.
- Kiểm tra case và account reference khi nguồn được thiết kế có quyền tra cứu đó.
- Metadata được bảo vệ về tenant scope trong command hoặc outbox.
- Xác thực nguồn, toàn vẹn thông điệp và chống sửa trường scope.
- Từ chối hoặc cách ly sự kiện thiếu thông tin bắt buộc thay vì tự điền tenant.

Chữ ký hợp lệ không tự giải quyết quyền phạm vi. Nếu một service có thể ký bất kỳ tenant ID nào nhưng chính sách chỉ cho nó phục vụ A, ingestion vẫn phải kiểm tra điều kiện đó.

Đối với quyết định nằm trong một database, thay đổi recovery và audit journal hoặc outbox có thể được ghi trong cùng transaction. Tenant context của outbox phải lấy từ chính đối tượng đã kiểm tra, không từ một biến request có thể bị thay đổi sau đó.

Nếu sự kiện bị phát lại, khóa deduplication cần gồm namespace phù hợp, chẳng hạn tenant, source và event ID. Cùng khóa nhưng payload khác là dấu hiệu sai lệch cần xử lý, không phải lý do âm thầm ghi đè event cũ.

## 7. Bảo vệ đường đọc: tenant filter là điều kiện bắt buộc

Tenant admin cần quyền xem audit ở phạm vi tenant của họ. Có role `AUDIT_VIEWER` không mặc nhiên cho phép tra mọi event trong nền tảng.

Một truy vấn sự kiện cụ thể nên thể hiện scope:

```sql
SELECT event_id,
       tenant_id,
       event_type,
       occurred_at,
       public_reason_code,
       outcome
FROM tenant_recovery_audit_projection
WHERE tenant_id = :authorized_tenant_id
  AND event_id = :event_id;
```

`:authorized_tenant_id` được lấy từ quyết định quyền hiện hành của máy chủ. Không chỉ dùng tenant ID client gửi vì tên biến nghe có vẻ an toàn.

Các điểm cần kiểm soát:

- Endpoint xem chi tiết, danh sách và tìm kiếm đều áp dụng tenant scope.
- Truy vấn theo `caseId`, `accountId` hoặc actor không bỏ mất tenant predicate.
- Bộ lọc nâng cao không cho người dùng mở rộng phạm vi ngoài quyền.
- Search index, cache và materialized view giữ tenant context tương ứng.
- Dữ liệu trả về chỉ gồm projection được phép đọc, không serialize nguyên entity nội bộ.

Row-level security hoặc tách database có thể tăng lớp bảo vệ, nhưng cấu hình connection pool, quyền service account và các đường quản trị vẫn cần đúng. Không giả định có partition theo tenant thì mọi API đã tự an toàn.

Phản hồi khi không có quyền không nên tiết lộ một event hoặc case của tenant khác có tồn tại hay không. Audit nội bộ vẫn giữ thông tin cần thiết cho điều tra theo phạm vi quyền phù hợp.

## 8. Ví dụ Java: API đọc audit chỉ làm việc trong phạm vi đã duyệt

Ví dụ dưới minh họa service đọc projection của một tenant. Nó không xác thực session hoặc truy cập database thật. `AccessDecision` phải được máy chủ tạo từ actor đã xác thực và quyền hiện hành, không được nhận nguyên từ body request.

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class TenantRecoveryAuditReader {
    public record AccessDecision(
            UUID actorId,
            UUID authorizedTenantId,
            boolean allowed) {}

    public record AuditProjection(
            UUID eventId,
            UUID tenantId,
            String eventType,
            Instant occurredAt,
            String outcome,
            String publicReasonCode) {}

    public interface Repository {
        List<AuditProjection> findLatestByTenant(
                UUID tenantId, int limit);
    }

    private final Repository repository;

    public TenantRecoveryAuditReader(Repository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public List<AuditProjection> listLatest(
            UUID authenticatedActorId,
            UUID requestedTenantId,
            AccessDecision access,
            int limit) {
        Objects.requireNonNull(authenticatedActorId);
        Objects.requireNonNull(requestedTenantId);
        Objects.requireNonNull(access);

        if (!access.allowed()
                || !authenticatedActorId.equals(access.actorId())
                || !requestedTenantId.equals(access.authorizedTenantId())) {
            throw new SecurityException("Audit scope is not authorized");
        }
        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("Invalid page size");
        }

        UUID tenantId = access.authorizedTenantId();
        List<AuditProjection> events = repository.findLatestByTenant(
                tenantId, limit);

        boolean scopeMismatch = events.stream()
                .anyMatch(event -> !tenantId.equals(event.tenantId()));
        if (scopeMismatch) {
            throw new IllegalStateException("Audit repository scope violation");
        }
        return List.copyOf(events);
    }
}
```

Giới hạn 200 là ví dụ, không phải giá trị bắt buộc. Repository thật phải áp dụng predicate tenant trong truy vấn; kiểm tra sau khi đọc chỉ là phòng thủ bổ sung, không cho phép nạp toàn bộ dữ liệu mọi tenant rồi lọc trong bộ nhớ.

Service gọi phải ghi nhận hành động đọc hoặc xuất audit theo chính sách. Khi phát hiện repository trả sai tenant, không trả các dòng còn lại như thể mọi thứ bình thường; cần chặn phản hồi và tạo tín hiệu điều tra tại nguồn audit bảo vệ phù hợp.

Ví dụ dùng quyền hiện hành của một request. Một access decision cũ không được tái sử dụng vô thời hạn sau khi người xem bị gỡ quyền. Pagination dài và export bất đồng bộ cần chính sách kiểm tra lại riêng.

## 9. Pagination, tìm kiếm, cache và export cũng là đường truy cập dữ liệu

Nhiều lỗi cách ly tenant nằm ngoài endpoint xem chi tiết.

### Pagination

Cursor cần ràng buộc với tenant, bộ lọc, thứ tự và phạm vi truy vấn tương ứng. Không cho một cursor tạo ở tenant A được dùng để tiếp tục trang ở tenant B. Nếu cursor chứa thông tin nhạy cảm hoặc có thể bị sửa, cần cơ chế bảo vệ phù hợp và kiểm tra ở máy chủ.

### Tìm kiếm và cache

Cache key cần bao phủ tenant cùng các yếu tố quyền và truy vấn có liên quan. Một cache chỉ theo `caseId` có thể trả kết quả của tenant khác. Search query cũng phải giữ scope dù tìm theo email, actor hoặc một đoạn reason code.

Không đưa dữ liệu bằng chứng hoặc token vào search index chung. Tìm kiếm audit nên dùng projection tối thiểu và thông tin đã phân loại.

### Export bất đồng bộ

Job export cần ghi tenant scope và quyền đã cho phép. Trước khi thực hiện hoặc bàn giao file, hệ thống phải xử lý trường hợp quyền bị thu hồi theo chính sách hiện hành. Một job được mở trước khi actor mất quyền không mặc nhiên được phép gửi dữ liệu sau đó.

File kết quả cần có kiểm soát truy cập theo tenant và người nhận hoặc quyền được cấp. Đường dẫn object chứa tenant ID không tự bảo đảm cách ly. URL được ký có thể là bearer capability; cần giới hạn phạm vi, thời hạn và tránh xuất hiện trong log hoặc kênh không phù hợp.

Nếu audit thay đổi hoặc có event đến muộn trong khi export, báo cáo cần nói rõ cutoff và phạm vi dữ liệu. Không mô tả một bản export theo checkpoint là toàn bộ lịch sử hiện hành nếu điều kiện đó chưa được chứng minh.

## 10. Danh tính dùng chung cần projection có chọn lọc

Giả sử principal P là thành viên tenant A và B. P trải qua recovery credential toàn nền tảng. Một event gốc có thể cần biết tác động tới phiên và credential của P, nhưng A không vì thế được biết P có membership tại B.

Một cách tổ chức:

```text
Sự kiện identity gốc — quyền truy cập nền tảng chuyên biệt
  ├── Projection tenant A: tác động được phép biết trong A
  └── Projection tenant B: tác động được phép biết trong B
```

Projection có thể thông báo credential đã trải qua recovery và các phiên thuộc tenant cần xác thực lại, nếu chính sách cho phép. Nó không chứa danh sách tổ chức, bằng chứng identity hoặc reason chi tiết làm lộ dữ liệu của bên khác.

Việc tạo projection cần dựa trên quan hệ đã xác minh và chính sách công bố. Không phát event tới mọi tenant trong một danh sách client gửi. Cũng không dùng chính projection của A làm bằng chứng rằng admin A được phép thực thi recovery toàn nền tảng.

Liên kết toàn cục phục vụ điều tra có thể cần tồn tại, nhưng chỉ một nhóm có quyền chuyên biệt mới được tra cứu. Tenant-scoped reference giúp giảm khả năng liên kết chéo, không tự thay thế authorization khi người xem có thể truy cập nguồn ánh xạ.

## 11. Tính toàn vẹn, sequence và audit bền vững theo tenant

Audit cần phát hiện sửa, mất hoặc phát lại sự kiện mà không tạo cảnh báo sai do lọc tenant.

Nếu một nguồn dùng sequence toàn cục cho A, B và C, người xem A sẽ thấy các số bị khuyết hợp lệ. Không được kết luận mỗi khoảng khuyết là thiếu event của A. Có thể dùng sequence theo tenant và nguồn, checkpoint được bảo vệ hoặc cơ chế chứng minh phạm vi phù hợp với thiết kế.

Thời gian xảy ra và thời gian nhận có thể khác nhau. Timestamp một mình không chứng minh một phê duyệt đã có trước lúc cấp token. Cần liên kết case version, quyết định và trạng thái thực thi bằng các tham chiếu có ý nghĩa.

Các cơ chế như append-only, hash chain, chữ ký hoặc MAC có thể giúp bảo vệ toàn vẹn theo mô hình đe dọa. Nhưng nếu actor có thể sửa cả lịch sử lẫn checkpoint, hoặc nguồn ký được phép giả mọi tenant, một lớp mật mã đơn thuần không giải quyết được quyền phạm vi.

Audit cần chiến lược bền vững và phục hồi phù hợp. Restore snapshot cũ không được làm mất duy nhất các sự kiện thu hồi hoặc quyết định tenant sau checkpoint. Khi có khoảng lịch sử chưa xác định, phải ghi rõ và áp dụng hạn chế hoặc đối soát thay vì coi không có event là không có hành động.

Retention và quyền xóa cần được thực thi đúng phạm vi. Một thao tác quản lý audit của tenant A không được xóa partition, khóa hoặc manifest đang bảo vệ tenant B. Nếu dùng hạ tầng chung, quy trình vận hành phải nhận diện được tài nguyên dùng chung trước khi thay đổi.

## 12. Truy cập audit cần được audit

Thông tin recovery có thể tiết lộ người dùng bị mất thiết bị, thời điểm hỗ trợ, loại factor và các hoạt động an ninh. Đọc audit vì vậy cũng là một hành động cần kiểm soát, không chỉ là tính năng báo cáo.

Một access event có thể ghi:

- Actor đã xác thực và access grant được sử dụng.
- Tenant được phép đọc, loại projection và phạm vi thời gian.
- Hành động xem chi tiết, tìm kiếm, export hoặc tải file.
- Số lượng kết quả hoặc tham chiếu job, không sao chép toàn bộ kết quả vào log.
- Kết quả cho phép hoặc từ chối cùng mã lý do an toàn.

Không ghi query thô nếu nó chứa email, số điện thoại hoặc dữ liệu nhạy cảm không cần thiết. Có thể dùng loại bộ lọc hoặc fingerprint theo chính sách, nhưng fingerprint không mặc nhiên làm dữ liệu vô danh nếu giá trị đầu vào dễ đoán.

Không thiết kế vòng lặp vô hạn “đọc audit tạo event, đọc event đó lại tạo event tiếp”. Các sự kiện truy cập có thể được ghi tại journal chuyên biệt và hiển thị theo quy tắc rõ ràng. Việc ghi không được vô tình phát lộ tenant khác cho người đang tra cứu.

Nhân viên hỗ trợ cần quyền đọc tạm thời theo hồ sơ, lý do và thời hạn khi chính sách yêu cầu. Quyền nền tảng không nên đồng nghĩa với quyền xem mọi bằng chứng mọi tenant mà không có mục đích.

## 13. Giám sát xâm phạm ranh giới và giới hạn tài nguyên

Các tín hiệu đáng điều tra có thể gồm:

- Actor đổi tenant ID nhiều lần trong cùng chuỗi request bị từ chối.
- Producer phát event cho tenant ngoài access grant.
- Case reference, account reference và tenant context không khớp.
- Cố dùng cursor hoặc URL export của tenant khác.
- Một tài khoản hỗ trợ truy cập nhiều tenant ngoài phạm vi công việc.
- Event thiếu tenant context hoặc payload khác nhau với cùng khóa deduplication.
- Độ trễ audit hoặc số sự kiện bị cách ly tăng bất thường.

Cảnh báo cần gửi tới nhóm có quyền xử lý đúng phạm vi. Tenant A không nên nhận thông báo chứa chi tiết tài nguyên của B chỉ vì request sai phạm vi xuất phát từ một actor của A. Có thể cần một cảnh báo tenant đã rút gọn và một cảnh báo điều tra nền tảng được bảo vệ riêng.

Tenant nhiều lưu lượng không được làm mất audit quan trọng của tenant khác. Có thể dùng quota, phân vùng xử lý, backpressure và dung lượng dự phòng theo kiến trúc. Tuy nhiên, không lấy mẫu mất các quyết định recovery quan trọng chỉ để giữ biểu đồ đẹp.

Nếu không ghi bền vững được audit cho một hành động nhạy cảm, hành vi phải theo chính sách của hành động đó. Đường cấp hoặc sử dụng capability có thể cần bị chặn; các thao tác chỉ đọc phục vụ chẩn đoán có thể có quy tắc riêng. Không dùng một chế độ bỏ audit chung cho toàn bộ hệ thống khi một tenant gây quá tải.

## 14. Ví dụ xuyên suốt: admin tenant A xem recovery của người dùng nhiều tổ chức

Linh là thành viên tenant A và B, dùng một principal toàn nền tảng. Linh mất thiết bị xác thực và hoàn tất recovery qua miền identity của nền tảng. Sự kiện gốc chứa tham chiếu bằng chứng và kết quả xử lý phiên, chỉ nhóm có quyền chuyên biệt mới được xem đầy đủ.

Tenant A nhận projection được phép biết: tài khoản thành viên của Linh trong A chịu tác động xác thực lại theo chính sách. Projection không liệt kê B và không chứa giấy tờ dùng để xác minh Linh.

Hà là audit viewer của A. Khi Hà xem sự kiện, API xác thực actor, kiểm tra quyền hiện hành với A và truy vấn projection theo đúng tenant. Một event ID của B được gửi vào cùng endpoint không trả dữ liệu B hoặc tiết lộ chi tiết rằng B có hồ sơ tương ứng.

Hà tạo export, rồi quyền audit của Hà bị thu hồi trước lúc file được bàn giao. Hệ thống xử lý quyền tại thời điểm bàn giao theo chính sách, không gửi file chỉ vì job từng được chấp thuận. Quyết định và kết quả được ghi vào access audit.

Trong cùng thời gian, một producer tích hợp của A gửi event tự khai thuộc B. Ingestion phát hiện scope không khớp, giữ dấu vết ở luồng điều tra bảo vệ và không đưa sự kiện đó vào audit chính thức của B như một hành động đã được B cho phép.

Ví dụ cho thấy tenant scope phải giữ xuyên suốt từ nguồn sự kiện tới projection, API, export và điều tra. Chỉ lọc ở một màn hình giao diện không tạo ra cách ly tenant.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng thiết kế |
| --- | --- | --- |
| Chép tenant ID từ request vào audit | Có thể giả phạm vi hoặc che thao tác chéo tenant | Phân giải tài nguyên và quyền từ nguồn có thẩm quyền |
| Truy vấn chỉ theo event ID | Lộ sự kiện ngoài tenant | Tenant predicate bắt buộc và kiểm tra quyền trên tài nguyên |
| Role audit viewer có phạm vi toàn nền tảng mặc định | Tenant admin xem dữ liệu tổ chức khác | Grant theo tenant, projection và loại dữ liệu |
| Gửi nguyên event global cho mọi membership | Lộ liên kết tổ chức và bằng chứng identity | Event gốc bảo vệ riêng, projection có chọn lọc |
| Producer đã xác thực được coi là được ghi mọi tenant | Service có thể giả sự kiện tenant khác | Kiểm tra thẩm quyền nguồn theo scope và event type |
| Cache hoặc cursor không ràng buộc tenant | Kết quả hoặc trang tiếp theo bị trộn | Scope trong cache key, cursor và kiểm tra phía máy chủ |
| Export bỏ kiểm tra quyền sau khi job được tạo | Người mất quyền vẫn nhận dữ liệu | Kiểm tra quyền theo các cổng thực thi và bàn giao đã định |
| Log token hoặc bằng chứng nguyên vẹn | Audit trở thành kho bí mật | Reason code và tham chiếu có kiểm soát |
| Coi sequence toàn cục bị khuyết sau lọc là mất event | Cảnh báo sai hoặc hiểu nhầm tính đầy đủ | Dùng checkpoint và ngữ nghĩa sequence đúng phạm vi |
| Quyền tenant admin bao gồm reset global credential ngầm định | Tác động tới tài khoản ngoài thẩm quyền tenant | Tách credential scope và quyền recovery tương ứng |

Tenant recovery audit có giá trị khi mỗi sự kiện giữ được phạm vi đáng tin, mọi đường truy cập thực thi đúng quyền và các bằng chứng nhạy cảm không lan qua ranh giới tổ chức. Khả năng điều tra toàn nền tảng cần một miền quyền riêng, trong khi tenant chỉ nhận những thông tin thực sự thuộc thẩm quyền của họ.
