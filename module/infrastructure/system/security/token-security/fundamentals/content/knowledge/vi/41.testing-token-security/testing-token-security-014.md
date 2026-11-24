# Test multi-tenant isolation

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ranh giới tenant và vì sao xác thực người dùng thành công chưa có nghĩa là người dùng được truy cập dữ liệu của mọi tenant.
- Thiết kế test xác minh tenant context được lấy từ danh tính đã xác thực và được truyền xuyên suốt request.
- Kiểm thử các tình huống truy cập chéo tenant ở API, database, cache, object storage, search và xử lý bất đồng bộ.
- Phát hiện lỗi Broken Object Level Authorization (BOLA/IDOR), rò rỉ dữ liệu qua truy vấn danh sách, batch, export và cache.
- Xây dựng test fixture nhiều tenant có dữ liệu dễ phân biệt, kiểm tra cả đường đọc, ghi và các trường hợp từ chối.

## 1. Multi-tenant isolation là gì?

Một ứng dụng multi-tenant phục vụ nhiều tổ chức hoặc khách hàng trên cùng một hệ thống. Mỗi tenant có một không gian dữ liệu và quyền truy cập riêng. Ví dụ, Tenant A và Tenant B cùng dùng một dịch vụ quản lý đơn hàng; người dùng của A chỉ được xem và thao tác trên đơn hàng thuộc A, dù họ biết ID của đơn hàng thuộc B.

**Tenant isolation** là tập hợp các kiểm soát bảo đảm một tenant không thể đọc, sửa, xóa, suy luận hoặc làm ảnh hưởng trái phép đến tài nguyên của tenant khác. Ranh giới này phải được duy trì ở mọi lớp xử lý, không chỉ tại màn hình đăng nhập hay API gateway.

Hãy phân biệt ba câu hỏi:

1. **Authentication:** Request do ai gửi? Ví dụ user-17 đã được xác thực.
2. **Tenant membership/context:** Người đó đang hoạt động trong tenant nào? Ví dụ user-17 có membership ở Tenant A.
3. **Authorization:** Người đó có quyền thực hiện hành động nào trên tài nguyên cụ thể thuộc tenant đó? Ví dụ được đọc invoice-100 của A nhưng không được xóa invoice-100.

Một access token hợp lệ chứng minh một số thông tin về issuer, subject, audience và quyền theo profile của token. Nó không tự động chứng minh người dùng được truy cập mọi tenant hoặc mọi object có ID mà họ gửi lên.

## 2. Xây dựng mô hình tin cậy cho tenant

### 2.1 Tenant ID là dữ liệu định tuyến bảo mật

Một hệ thống có thể biểu diễn tenant trong claim riêng, chẳng hạn `tenant_id`, hoặc lấy tenant context từ một membership đã được xác minh ở phía máy chủ. `tenant_id` **không phải claim chuẩn bắt buộc của JWT hay OAuth 2.0**; đây là quy ước ứng dụng cần được định nghĩa trong profile token.

Ví dụ access token minh họa:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-17",
  "aud": "orders-api",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
~~~

Resource server chỉ được sử dụng `tenant_id` sau khi xác minh chữ ký, thuật toán được phép, issuer, audience, expiration và các điều kiện khác của token. Không được giải mã payload rồi tin ngay claim vì payload JWT có thể đọc được nhưng chưa chắc đã được xác thực.

Nếu một người dùng thuộc nhiều tenant, hệ thống cần xác định rõ cách chọn tenant đang hoạt động. Một số thiết kế phát hành token riêng cho từng tenant context; thiết kế khác giữ membership và kiểm tra tenant được chọn ở phía server. Trong cả hai trường hợp, client gửi `X-Tenant-Id` hoặc tenant trong URL chỉ là **yêu cầu chọn context**, không phải bằng chứng được phép truy cập tenant đó.

### 2.2 Phân biệt các định danh

| Giá trị | Mục đích | Cách sử dụng an toàn |
| --- | --- | --- |
| `sub` | Định danh subject trong issuer | Xác định người dùng/workload sau khi xác minh issuer |
| `tenant_id` | Tenant context theo profile ứng dụng | Kiểm tra claim đã xác thực hoặc membership hiện hành |
| `aud` | Resource server mà token hướng tới | Từ chối token không dành cho API hiện tại |
| `scope` / quyền | Phạm vi hành động được cấp | Kết hợp với tenant và quyền trên object |
| Resource ID | Định danh invoice, order, document... | Truy vấn kèm tenant predicate và kiểm tra quyền |
| `X-Tenant-Id` | Tenant client muốn chọn | Đối chiếu với context/membership đã tin cậy; không dùng độc lập |

Tenant ID không thay thế object-level authorization. Người dùng có thể thuộc Tenant A nhưng vẫn không được đọc mọi tài liệu trong A. Ngược lại, một object ID hợp lệ cũng không cho phép bỏ qua tenant boundary.

### 2.3 Quy tắc quyết định truy cập

Với mỗi thao tác, quyết định cần gắn với ít nhất bốn thành phần:

~~~text
subject + activeTenant + action + resource
~~~

Ví dụ: user-17, tenant-a, action=read, resource=invoice-100. Hệ thống phải xác minh:

- Danh tính user-17 được xác thực.
- Tenant A là context hợp lệ của request.
- Invoice-100 thuộc Tenant A.
- User-17 có quyền đọc loại tài nguyên đó.

Chỉ kiểm tra role như `USER` hoặc `ADMIN` mà không ràng buộc tenant là chưa đủ. Vai trò admin trong Tenant A không mặc nhiên là admin của Tenant B. Nếu có platform administrator toàn hệ thống, đó phải là quyền riêng, được cấp rõ ràng, giám sát và kiểm thử riêng.

## 3. Thiết kế bộ dữ liệu test có thể phát hiện rò rỉ

Tạo ít nhất hai tenant độc lập và dữ liệu có nội dung dễ nhận biết:

| Thuộc tính | Tenant A | Tenant B |
| --- | --- | --- |
| Tenant ID | `tenant-a` | `tenant-b` |
| User | `user-a1` | `user-b1` |
| Role | `TENANT_ADMIN` | `TENANT_ADMIN` |
| Document ID | `doc-100` | `doc-200` |
| Marker dữ liệu | `A-SECRET-ALPHA` | `B-SECRET-BETA` |

Nên có thêm trường hợp hai tenant dùng cùng một ID cục bộ nếu kiến trúc cho phép, ví dụ mỗi tenant có `document_id=42` trong schema hoặc partition riêng. Trường hợp này phát hiện lỗi truy vấn chỉ lọc theo object ID mà quên tenant ID.

Fixture cần tạo user, membership, token và dữ liệu thông qua cơ chế test rõ ràng. Không tái sử dụng token thật từ môi trường production. Khi test xong, dọn dữ liệu và cache của cả hai tenant để kết quả không phụ thuộc thứ tự chạy test.

**Nguyên tắc kiểm thử:** kiểm tra bằng dữ liệu của cả A và B trong cùng một test scenario. Nếu chỉ tạo dữ liệu Tenant A, một truy vấn thiếu tenant predicate vẫn có thể vượt qua test mà không ai phát hiện.

## 4. Ma trận kiểm thử cách ly tenant

### 4.1 Đọc dữ liệu

| Người gọi | Tài nguyên | Kỳ vọng |
| --- | --- | --- |
| User A | Document A | Cho phép nếu đủ quyền |
| User A | Document B | Từ chối hoặc trả 404 theo contract |
| User B | Document B | Cho phép nếu đủ quyền |
| User B | Document A | Từ chối hoặc trả 404 theo contract |
| User A | ID không tồn tại | Trả kết quả không tồn tại theo contract |

Kiểm tra cả endpoint đọc một object, endpoint danh sách, tìm kiếm, thống kê, export và endpoint batch. Một API chi tiết có thể lọc đúng tenant trong khi endpoint danh sách lại trả toàn bộ dữ liệu vì thiếu điều kiện lọc.

### 4.2 Ghi, sửa và xóa

Với user A, thử sửa hoặc xóa document B bằng cách thay ID trong URL/body. Hệ thống phải từ chối và dữ liệu Tenant B phải giữ nguyên. Kiểm tra thêm các field tenant do client gửi:

- Client A gửi body có `tenantId=tenant-b`.
- Client A gửi path Tenant B nhưng token/context thuộc A.
- Client A đổi tenant header sau khi đã xác thực.
- Client A tạo object với tenant ID của B.

Server phải lấy tenant từ context tin cậy, kiểm tra membership và áp policy. Không cho client ghi đè tenant ownership bằng field trong request. Với thao tác tạo, tenant ID được gán từ context đã xác minh; với thao tác cập nhật, tenant ownership hiện tại của object phải được giữ nguyên trừ khi có một quy trình chuyển tenant riêng được ủy quyền.

### 4.3 Các đường truy cập phụ

| Thành phần | Lỗi thường gặp | Bài test |
| --- | --- | --- |
| Database query | Quên điều kiện tenant | Cùng object ID ở hai tenant; xác minh chỉ lấy đúng tenant |
| Cache | Key không có tenant | Đọc cùng resource ID từ A rồi B, xác minh không dùng chung entry |
| Search index | Query không filter tenant | Tìm marker B bằng principal A, không được trả kết quả |
| Object storage | URL/key đoán được | User A không tải được file B dù biết object key |
| Export/report | Job chạy theo ID mà không ràng tenant | Export của A chỉ chứa dòng A |
| Message queue | Consumer tin tenant từ payload không xác thực | Event sai tenant hoặc không khớp resource bị từ chối |
| Background job | Tenant context bị mất hoặc rò giữa worker | Hai job chạy xen kẽ vẫn truy cập đúng partition |
| Audit/log | Log hoặc dashboard gộp nhầm tenant | Người dùng tenant không xem dữ liệu vận hành của tenant khác |

## 5. Kiểm tra tenant tại API và service layer

Tenant context nên được tạo từ principal đã xác thực và truyền tường minh qua các lớp. Tránh nhận tenant tùy ý từ request rồi lưu vào biến toàn cục hoặc `ThreadLocal` mà không có cơ chế đặt, khôi phục và xóa an toàn.

Ví dụ Java đơn giản:

~~~java
record AuthenticatedPrincipal(
        String subject,
        String tenantId,
        java.util.Set<String> authorities) {}

record Document(
        String id,
        String tenantId,
        String content) {}

interface DocumentRepository {
    java.util.Optional<Document> findByIdAndTenantId(
            String documentId, String tenantId);
}

final class DocumentService {
    private final DocumentRepository repository;

    DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    Document getDocument(
            AuthenticatedPrincipal principal, String documentId) {
        if (principal == null || principal.tenantId() == null) {
            throw new SecurityException("missing_tenant_context");
        }

        return repository.findByIdAndTenantId(
                        documentId, principal.tenantId())
                .orElseThrow(() ->
                        new DocumentNotFoundException(documentId));
    }
}
~~~

Repository cần thực hiện truy vấn có tenant predicate, ví dụ:

~~~sql
SELECT id, tenant_id, content
FROM documents
WHERE id = :documentId
  AND tenant_id = :trustedTenantId;
~~~

`trustedTenantId` trong truy vấn phải đến từ principal/context đã xác minh. Không lấy nó từ body hoặc query parameter mà không kiểm tra membership. Nếu dùng ORM, kiểm tra SQL thực tế được sinh ra hoặc kiểm thử repository để bảo đảm tenant filter thực sự nằm trong truy vấn.

Ví dụ unit test cho service:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Test;

class DocumentServiceTest {
    @Test
    void tenantAReadsOnlyItsOwnDocument() {
        DocumentRepository repository =
                mock(DocumentRepository.class);
        var service = new DocumentService(repository);
        var tenantA = new AuthenticatedPrincipal(
                "user-a1", "tenant-a", Set.of("DOCUMENT_READ"));
        var documentA = new Document(
                "doc-100", "tenant-a", "A-SECRET-ALPHA");

        when(repository.findByIdAndTenantId(
                "doc-100", "tenant-a"))
                .thenReturn(Optional.of(documentA));

        Document result = service.getDocument(tenantA, "doc-100");

        assertEquals("tenant-a", result.tenantId());
        assertEquals("A-SECRET-ALPHA", result.content());
        verify(repository).findByIdAndTenantId(
                "doc-100", "tenant-a");
        verifyNoMoreInteractions(repository);
    }

    @Test
    void tenantACannotReadDocumentOwnedByTenantB() {
        DocumentRepository repository =
                mock(DocumentRepository.class);
        var service = new DocumentService(repository);
        var tenantA = new AuthenticatedPrincipal(
                "user-a1", "tenant-a", Set.of("DOCUMENT_READ"));

        when(repository.findByIdAndTenantId(
                "doc-200", "tenant-a"))
                .thenReturn(Optional.empty());

        assertThrows(DocumentNotFoundException.class,
                () -> service.getDocument(tenantA, "doc-200"));
        verify(repository).findByIdAndTenantId(
                "doc-200", "tenant-a");
    }
}
~~~

Test service giúp xác minh tenant được truyền đúng. Tuy nhiên, mock repository không chứng minh SQL/database đã lọc tenant. Cần có integration test với database thật hoặc container test để kiểm tra query, constraint và row-level security nếu kiến trúc sử dụng chúng.

## 6. Kiểm thử JWT và tenant context

Với token-based authentication, cần kiểm tra ít nhất các trường hợp:

1. Token đã xác minh có `tenant_id=tenant-a`; request tới resource của A được xử lý theo quyền.
2. Token của A yêu cầu resource thuộc B; từ chối dù caller biết chính xác ID.
3. Token thiếu tenant context trong khi API yêu cầu tenant; từ chối an toàn.
4. Token có tenant claim sai chữ ký hoặc payload bị sửa; từ chối do xác minh token thất bại.
5. Token có issuer hoặc audience không hợp lệ; từ chối trước khi thực hiện nghiệp vụ.
6. Client gửi tenant B trong header/body nhưng token/context đã xác minh là A; không được tự chuyển sang B.
7. User thuộc nhiều tenant chọn B; server kiểm tra membership B và quyền hiện hành trước khi tạo context B.
8. Membership bị thu hồi sau khi token được phát hành; hành vi phải phù hợp chính sách freshness/revocation của hệ thống.

### Trường hợp người dùng thuộc nhiều tenant

Giả sử user-17 có membership ở A và B. Việc người đó thuộc cả hai tenant không có nghĩa một request có thể trộn dữ liệu A và B. Mỗi request cần một tenant context rõ ràng; mọi truy vấn, cache key, event và audit record phải gắn với context đó.

Nếu token mang một tenant duy nhất, việc chuyển tenant thường cần quy trình phát hành hoặc đổi context có kiểm tra membership. Nếu token mang danh sách tenant, danh sách đó vẫn cần được xác minh và request phải chọn đúng một context theo policy. Không dùng danh sách tenant trong token làm quyền truy cập mọi object mà không kiểm tra role và quyền cụ thể.

Nếu membership có thể bị thu hồi trong thời gian token còn hiệu lực, hãy xác định rõ hệ thống dùng token TTL ngắn, introspection, revocation event hay kiểm tra membership trực tuyến. Test phải chứng minh hành vi sau khi membership bị thu hồi, không giả định claim cũ tự cập nhật.

## 7. Kiểm thử database isolation

### 7.1 Shared database, shared schema

Mô hình thường có cột `tenant_id` trên mọi bảng thuộc tenant. Kiểm thử:

- Mọi SELECT, UPDATE, DELETE và JOIN đều giới hạn theo tenant.
- Foreign key hoặc quan hệ giữa bảng không cho liên kết object của tenant A với object của B ngoài policy.
- Unique constraint có xét tenant khi định danh chỉ cần duy nhất trong tenant, ví dụ `(tenant_id, external_code)`.
- Pagination/count/aggregate chỉ tính dữ liệu tenant hiện tại.
- Bulk update/delete không bỏ qua tenant predicate.

Một lỗi phổ biến là truy vấn danh sách đã lọc tenant nhưng truy vấn lấy object theo ID lại dùng `findById(id)` đơn thuần. Hãy test cả hai đường truy cập.

### 7.2 Schema-per-tenant hoặc database-per-tenant

Nếu mỗi tenant có schema/database riêng, test phải xác minh connection routing đúng tenant, transaction không bị tái sử dụng nhầm và pool không giữ session/schema state từ request trước. Tạo hai tenant với marker khác nhau, chạy request xen kẽ trên cùng pool kết nối và xác minh không có dữ liệu chéo.

### 7.3 Row-level security

Nếu database hỗ trợ Row-Level Security (RLS), hãy kiểm tra:

- Policy được bật cho đúng bảng và đúng role ứng dụng.
- Tenant context được đặt trong transaction trước câu query.
- Connection pool reset session variable sau transaction.
- Role ứng dụng không có quyền bypass RLS ngoài chủ đích.
- Các đường truy cập bằng batch, stored procedure và migration không vô tình bỏ qua policy.

RLS là lớp bảo vệ bổ sung, không thay thế authorization ở ứng dụng. Kiểm thử cần chứng minh cả policy database lẫn kiểm soát quyền nghiệp vụ.

## 8. Cache, search, file và xử lý bất đồng bộ

### Cache

Cache key phải phân biệt tenant khi dữ liệu phụ thuộc tenant. Ví dụ:

~~~text
document:tenant-a:doc-100
document:tenant-b:doc-100
~~~

Test cùng một resource key trong hai tenant. Gửi request A trước, sau đó request B; xác minh B không nhận entry A. Lặp lại theo thứ tự B rồi A để phát hiện cache poisoning hoặc lỗi key. Kiểm tra cả cache object, cache query result, permission decision và CDN/gateway cache nếu có.

### Search và analytics

Search query phải áp filter tenant ở server-side. Không dựa vào filter do browser gửi. Kiểm thử:

- Từ khóa chỉ có trong dữ liệu B không xuất hiện với user A.
- Facet, count, autocomplete và suggestion không tiết lộ tên hoặc số lượng tài liệu của B.
- Dashboard và báo cáo tổng hợp chỉ tính dữ liệu được phép.
- Export lớn không bỏ mất tenant filter ở các trang tiếp theo.

### Object storage

Đường dẫn file nên gắn với tenant hoặc có mapping server-side. Biết object key không đủ để tải file. Với signed URL, test người dùng A không thể yêu cầu URL cho file B; URL được cấp phải có thời hạn và quyền phù hợp. Không ghi signed URL hoặc credential vào log.

### Message queue và background job

Event cần mang tenant context được tạo từ nguồn tin cậy và liên kết với resource tương ứng. Consumer phải xác minh event, quyền xử lý và tenant ownership trước khi thao tác. Không tin một field `tenantId` trong message chỉ vì message có cấu trúc JSON hợp lệ.

Chạy hai job A và B xen kẽ trên cùng worker pool. Kiểm tra context được truyền tường minh, không rò qua thread reuse, coroutine, callback hoặc retry. Nếu job A thất bại, cleanup phải xóa context trước khi worker xử lý job B.

## 9. Phản hồi lỗi và chống dò tìm tài nguyên

Khi user A yêu cầu object của B, API có thể trả `403 Forbidden` hoặc `404 Not Found` tùy contract và yêu cầu tránh tiết lộ sự tồn tại của object. Dù chọn cách nào, cần nhất quán giữa endpoint đọc, sửa, xóa, export và batch. Không trả body chứa tenant owner, tên khách hàng, metadata hoặc thông tin xác nhận object có tồn tại trong tenant khác.

Phân biệt:

- `401 Unauthorized`: chưa có thông tin xác thực hợp lệ hoặc token không hợp lệ.
- `403 Forbidden`: đã xác thực nhưng không được phép thực hiện hành động theo contract.
- `404 Not Found`: tài nguyên không tồn tại hoặc được cố ý che giấu để tránh tiết lộ.

Test không nên chỉ assert status code. Hãy xác minh body, header, thời gian phản hồi nếu có nguy cơ enumeration, audit event và việc không phát sinh side effect. Cần bảo đảm phản hồi lỗi không làm lộ ID nội bộ hay dữ liệu tenant khác.

## 10. Các lỗi thường gặp khi kiểm thử

| Lỗi | Vì sao test đơn giản bỏ sót | Cách phát hiện |
| --- | --- | --- |
| Chỉ kiểm tra role | Cả A và B đều có role ADMIN | Dùng cùng role ở hai tenant và thử truy cập chéo |
| Tin tenant từ request | Test luôn gửi tenant đúng | Thử sửa header, path, query và body sang tenant khác |
| Truy vấn theo ID đơn thuần | ID test không trùng giữa tenant | Tạo cùng local ID ở A/B hoặc kiểm tra SQL predicate |
| Chỉ test API detail | Endpoint danh sách/search/export khác code path | Test mọi kiểu truy vấn và tổng hợp |
| Cache key thiếu tenant | Test chạy một tenant hoặc cache rỗng | Chạy A/B liên tiếp theo cả hai thứ tự |
| Context bị rò giữa thread | Test chạy tuần tự trên một thread | Chạy song song và tái sử dụng worker/thread pool |
| Job tin tenant trong payload | Test event luôn do producer hợp lệ tạo | Gửi event giả mạo hoặc tenant-resource mismatch |
| Chỉ test đọc | Write path có query khác | Thử create/update/delete/bulk operation chéo tenant |
| Membership cũ trong token | Không test thu hồi membership | Thu hồi membership rồi gọi API theo policy freshness |
| Platform admin bị lẫn tenant admin | Cùng một role name | Tách quyền toàn hệ thống và quyền trong tenant |

## 11. Kế hoạch kiểm thử hồi quy

Một bộ hồi quy có thể tổ chức theo các lớp:

1. **Unit test:** policy chọn tenant, kiểm tra membership, object authorization và tenant-aware cache key.
2. **Repository integration test:** truy vấn thực tế với ít nhất hai tenant, gồm đọc, ghi, join, count và bulk operation.
3. **API integration test:** token của A gọi endpoint với resource của B; xác minh từ chối và không có side effect.
4. **Infrastructure test:** cache, search, object storage, queue và worker pool không trộn tenant context.
5. **Concurrency test:** request A/B chạy song song, dùng chung connection pool/cache/worker nhưng không rò dữ liệu.
6. **Regression test:** mỗi lỗi cross-tenant từng phát hiện phải có fixture và test tái hiện.

Với các hệ thống có nhiều endpoint, có thể xây dựng một test contract chung: tạo principal tenant A, tạo resource tenant B, gọi endpoint bằng ID B, rồi xác minh response và trạng thái dữ liệu. Contract này cần hỗ trợ từng kiểu thao tác và ngoại lệ nghiệp vụ được cho phép.

## 12. Checklist trước khi phát hành

- [ ] Tenant context đến từ token đã xác minh hoặc membership được kiểm tra ở server.
- [ ] Tenant do client gửi không thể tự thay thế context tin cậy.
- [ ] Mọi thao tác object kiểm tra cả tenant ownership và quyền hành động.
- [ ] Có fixture tối thiểu hai tenant với dữ liệu marker khác nhau.
- [ ] Đã test đọc, danh sách, search, count, export, create, update, delete và batch.
- [ ] Repository query, JOIN, bulk operation và pagination đều có tenant predicate.
- [ ] Cache key, search filter, object storage và signed URL được ràng buộc tenant.
- [ ] Queue event và background job xác minh tenant-resource mapping.
- [ ] Đã test membership thu hồi và người dùng thuộc nhiều tenant.
- [ ] Đã test request song song và connection/thread reuse.
- [ ] Phản hồi lỗi không làm lộ dữ liệu hoặc sự tồn tại của tài nguyên tenant khác.
- [ ] Platform-wide administrator được tách biệt và kiểm thử theo policy riêng.

## Ghi nhớ

**Xác thực đúng người dùng chưa đủ để bảo đảm cách ly tenant.** Mỗi lần truy cập phải gắn danh tính đã xác thực với tenant context tin cậy, hành động và tài nguyên cụ thể. Bộ test mạnh cần dùng ít nhất hai tenant, thử truy cập chéo trên mọi đường dữ liệu và kiểm tra cả trạng thái sau thao tác. Tenant filter phải tồn tại xuyên suốt API, service, database, cache, search, file storage và background processing.

### Tài liệu tham khảo

- OWASP API Security Top 10 — API1: Broken Object Level Authorization (BOLA): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet — kiểm tra quyền ở mọi request và nguyên tắc deny by default: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- IETF RFC 7519 — JSON Web Token (JWT), registered claims và xác minh token: https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
