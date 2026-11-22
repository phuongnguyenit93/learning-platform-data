# Kiểm thử tạo, sửa, xóa, tìm kiếm và xuất dữ liệu chéo phạm vi

## 1. Mục tiêu và bối cảnh

Trong ứng dụng nhiều tenant, tổ chức, workspace hoặc dự án, người dùng có thể có quyền thực hiện một **loại thao tác** nhưng không mặc nhiên có quyền thao tác trên **mọi bản ghi**. Bài này tập trung vào việc kiểm thử chính sách phân quyền ở ranh giới dữ liệu (data scope) cho năm nhóm thao tác: **tạo (create), sửa (update), xóa (delete), tìm kiếm (search) và xuất dữ liệu (export)**. Đây là nhóm kiểm thử phát hiện lỗi **Broken Object Level Authorization (BOLA/IDOR)**, lộ dữ liệu chéo tenant và bỏ sót bộ lọc phạm vi tại các đường truy cập khác nhau.

Ví dụ xuyên suốt: hệ thống lưu tài liệu theo tenant. Alice thuộc tenant A, Bob thuộc tenant B; cả hai đều có quyền thao tác tài liệu trong tenant của mình. Tài liệu A-101 thuộc A, tài liệu B-202 thuộc B. Chính sách cần bảo đảm Alice không thể tạo dữ liệu sang B, sửa hoặc xóa B-202, nhìn thấy B-202 trong kết quả tìm kiếm, hay nhận B-202 qua tệp xuất, dù Alice đoán đúng ID và cố tình sửa URL, query, JSON body hoặc header.

**Phạm vi kiểm thử:** quyền nghiệp vụ (permission), quan hệ chủ thể–đối tượng (actor–resource), tenant cha, liên kết giữa các bản ghi và kết quả/side effect. Bài dùng ví dụ Spring Security ở tầng servlet; cùng tư duy áp dụng cho WebFlux, GraphQL, batch API, job nền và truy cập service-to-service, nhưng cần bộ công cụ test tương ứng.

### Quy ước và bất biến bảo mật

- **Authentication** xác thực ai đang gọi. **Functional authorization** xác định người đó có quyền `document:create`, `document:edit`, `document:delete`, `document:search` hoặc `document:export`. **Data-scope authorization** xác định họ được thao tác trên tài liệu/tenant nào. Cả ba phải đúng.
- **Phạm vi hiệu lực** phải được suy ra hoặc xác minh từ danh tính đã xác thực và membership/chính sách phía server. ID tenant do client gửi chỉ là tham số cần kiểm chứng; không phải nguồn cấp quyền.
- **Bất biến đọc:** mọi bản ghi trả về, mỗi trang kết quả, số đếm và tệp xuất đều thuộc tập bản ghi được phép xem tại thời điểm chính sách có hiệu lực.
- **Bất biến ghi:** thao tác bị từ chối không tạo, đổi, xóa, di chuyển hoặc liên kết bản ghi ngoài phạm vi. Kiểm tra **trạng thái lưu trữ sau request**, không chỉ HTTP status.
- **Fail closed:** thiếu thông tin scope, membership hết hiệu lực, scope không hợp lệ hoặc policy service lỗi phải từ chối; không tự rơi về truy vấn không lọc.
- **Ẩn sự tồn tại:** một tài nguyên ngoài phạm vi có thể trả `404` để tránh tiết lộ ID; `403` cũng hợp lệ nếu hợp đồng API dùng chính sách đó. Test khẳng định chính sách đã công bố, nhất quán, không tùy tiện chấp nhận mọi mã 4xx.

Một actor có thể thuộc nhiều tenant. Khi đó server phải xác minh tenant đang hoạt động và quyền của actor đối với *tenant cụ thể*, thay vì chỉ so tên tenant với một claim hoặc tin vào header `X-Tenant-Id`.

## 2. Dữ liệu kiểm thử tối thiểu và ma trận quyền

Chuẩn bị fixture có ít nhất: tenant A và B; Alice thuộc A, Bob thuộc B; một người không đăng nhập; một người đăng nhập nhưng thiếu quyền thao tác; tài liệu A-101 và B-202; một tài liệu A liên kết tới đối tượng của A; một đối tượng liên kết của B; bộ dữ liệu có từ khóa trùng nhau ở cả A và B để phát hiện lọc tìm kiếm sai. Nếu ứng dụng cho phép actor thuộc nhiều tenant, thêm tình huống actor có quyền đọc A nhưng chỉ quyền ghi B. Dữ liệu phải có ID và title phân biệt rõ để truy vết.

| Thao tác | Ca hợp lệ | Ca chéo phạm vi bắt buộc | Điều cần xác nhận |
| --- | --- | --- | --- |
| Tạo | Alice tạo trong A | Gửi tenant B trong path/body; gắn parent/project ID của B | Không có bản ghi mới tại B; chủ sở hữu không bị client áp đặt |
| Sửa | Alice sửa A-101 | Alice sửa B-202 hoặc dùng path A nhưng ID thuộc B | Nội dung, version, quan hệ của B-202 giữ nguyên |
| Xóa | Alice xóa tài liệu A | Alice xóa B-202, kể cả soft delete/bulk delete | B-202 vẫn tồn tại, không có tombstone/job xóa ngoài quyền |
| Tìm kiếm | Alice thấy đúng tập A | Filter/query/keyword chứa B; phân trang, tổng số, facet, autocomplete | Không có hàng, metadata hay gợi ý tiết lộ B |
| Xuất | Alice tải đúng dữ liệu A | Export all, filter B, chọn ID B, chạy job và tải lại bằng actor khác | File/stream/job chỉ chứa dữ liệu được phép |

Với mỗi hàng, còn cần hai kiểm thử độc lập: **chưa đăng nhập** (`401` với bearer API thông thường) và **đã đăng nhập nhưng thiếu permission** (`403` thông thường); mã thực tế phụ thuộc hợp đồng authentication entry point và error handling. Ca chéo scope phải được thử cả khi actor *có đầy đủ quyền chức năng* để chắc rằng bước kiểm tra object-level không bị bỏ quên.

### Thiết kế một ca test có sức chứng minh

1. **Arrange:** tạo A-101 và B-202, ghi lại nội dung/version/số bản ghi trước test; thiết lập token của Alice với đúng authority nhưng chỉ membership A.
2. **Act:** gửi request cố truy cập B-202 hoặc phạm vi B qua endpoint đang kiểm tra.
3. **Assert response:** nhận mã bị từ chối theo hợp đồng; phản hồi không chứa dữ liệu nhạy cảm như title, owner, tenant, ID nội bộ hoặc stack trace.
4. **Assert persistence:** truy vấn trực tiếp dưới quyền test/administrator để xác nhận B-202 không đổi; kiểm tra cả bảng liên kết, attachment, soft-delete flag, event/outbox và job nếu thao tác có thể kích hoạt chúng. Audit sự kiện *từ chối* được phép tồn tại, khác với tác dụng phụ nghiệp vụ.
5. **Control:** request tương đương trên A-101 thành công và chỉ đổi dữ liệu A. Nếu chỉ có negative test, một endpoint hỏng luôn trả 403 cũng có thể qua test.

Không coi `403` ở tầng route là bằng chứng đủ cho phân quyền tài nguyên: request có thể bị chặn vì thiếu CSRF, thiếu token hoặc thiếu functional permission trước khi policy scope được chạy. Dùng đúng phương thức auth và authority để kích hoạt đường xử lý cần kiểm tra.

## 3. Kiểm thử CREATE: không nhận tenant hoặc owner từ client làm quyền

Ví dụ endpoint: `POST /api/tenants/{tenantId}/documents`. Thử tạo trong A (thành công); thay path sang B; giữ path A nhưng gửi JSON chứa `tenantId=B` hoặc `ownerId=Bob`; dùng `parentId`/`projectId` thuộc B; gửi nhiều phần tử gồm một phần tử thuộc B.

Các khẳng định quan trọng:

- Server phải kiểm membership và quyền `create` đối với tenant nhận bản ghi; ID/owner nhạy cảm phải do server gán hoặc xác minh, không mass-assign từ DTO.
- Đối tượng cha, thư mục, dự án, danh mục hoặc tài nguyên được tham chiếu cũng phải nằm trong phạm vi mà actor được phép liên kết. Chỉ kiểm tra tenant của bản ghi mới là chưa đủ.
- Request bị từ chối không sinh record, attachment, quan hệ, outbox message hoặc queue job bất hợp lệ. Kiểm tra số bản ghi trước–sau ở **cả hai** tenant.
- Nếu API cho phép bulk create, tài liệu hóa rõ chính sách **atomic all-or-nothing** hay **partial success**; test đúng hợp đồng và bảo đảm phần tử B không được chèn ngay cả khi phần tử A hợp lệ.

Phản ví dụ nguy hiểm: service gọi `repository.save(dto.toEntity())`, vô tình chép `tenantId`/`ownerId` từ JSON body mà không đối chiếu membership. Một actor có authority `document:create` sẽ ghi chéo tenant mặc dù middleware đã xác thực thành công.

## 4. Kiểm thử UPDATE/PATCH: ID thuộc tenant khác và đổi quan hệ

Ví dụ: `PUT /api/tenants/A/documents/B-202` hoặc `PATCH /api/documents/B-202`. Kiểm tra cả việc đoán ID B, path tenant A + body tenant B, sửa trường `ownerId`/`tenantId`, đổi `projectId` sang project B, và thao tác batch update nhiều ID.

Bắt buộc xác nhận:

- Đọc/khóa bản ghi bằng **điều kiện ID và scope**, hoặc thực thi policy trên entity đã nạp trước khi sửa. Không gọi `findById(id)` rồi save mà bỏ qua tenant. Với multi-tenant database, truy vấn có thể kết hợp RLS nhưng test vẫn phải chứng minh tính đúng đắn của truy cập.
- Kiểm tra quyền **trên giá trị cũ** trước khi thay đổi, và kiểm tra quyền đối với **giá trị đích** nếu cho phép chuyển ownership/parent. Trường bất biến phải bị loại khỏi DTO hoặc từ chối sửa.
- `PATCH`, JSON Merge Patch, JSON Patch và PUT phải đi qua cùng policy. Thử path dạng `/tenantId` và body chứa trường trái phép, cả việc bỏ qua/đổi tên trường.
- Với optimistic locking, ETag/version phải được kiểm đúng; đừng để lỗi stale update che lỗi scope. Request bị từ chối không tăng version hoặc ghi event thành công.

Ví dụ truy vấn cập nhật có guard tại database:

~~~sql
UPDATE documents
SET title = :newTitle, version = version + 1
WHERE id = :documentId
  AND tenant_id = :authorizedTenant
  AND version = :expectedVersion;
~~~

Số dòng bị tác động bằng 0 có thể là không thấy tài nguyên, ngoài phạm vi hoặc conflict version; cách ánh xạ mã lỗi phải theo hợp đồng API và không làm lộ sự tồn tại của tài liệu ngoài scope. `authorizedTenant` phải xuất phát từ policy phía server, không lấy mù quáng từ path/body.

## 5. Kiểm thử DELETE: xóa thật, xóa mềm và hậu quả bất đồng bộ

Thử `DELETE /api/documents/B-202` với token Alice có quyền `delete` trong A. Bên cạnh việc chờ phản hồi từ chối, truy vấn lại bản ghi B-202 để xác nhận: còn tồn tại; `deleted_at`/`is_deleted` chưa đổi; quan hệ, file, index, cache và outbox không bị cập nhật theo yêu cầu xóa trái phép.

Tách các dạng xóa để không bỏ sót policy: xóa đơn, xóa nhiều ID, xóa theo bộ lọc, xóa cascade các quan hệ con, restore/undelete, purge vĩnh viễn và endpoint admin. Nếu request chứa cả A-101 và B-202, test chính sách atomic/partial success đã công bố; tuyệt đối không được xóa B-202. Tùy thiết kế, có thể trả 404 cho ID ngoài phạm vi nhằm tránh enumeration.

Với tác vụ nền, hãy xác nhận job **không được enqueue** khi request không được phép; đồng thời test worker kiểm scope lại khi job thực thi nếu quyền/membership có thể bị thu hồi giữa hai thời điểm. Không tin rằng bước kiểm tra trên HTTP request đủ để cho phép job chạy về sau.

## 6. Kiểm thử SEARCH: lọc cả kết quả và metadata

Ví dụ: `GET /api/documents?tenantId=B&q=invoice&page=0&size=20` với Alice của A. Bộ lọc scope phải được áp dụng ở truy vấn gốc, trước phân trang/aggregate, trên tất cả nhánh join, subquery, đề xuất tìm kiếm và các kết quả tổng hợp.

Một mẫu truy vấn đọc giới hạn scope (ký hiệu `:authorizedTenant` là kết quả xác minh phía server):

~~~sql
SELECT d.id, d.title
FROM documents AS d
WHERE d.tenant_id = :authorizedTenant
  AND LOWER(d.title) LIKE :escapedSearchPattern
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
~~~

Truy vấn `COUNT(*)`, facet, grouped statistics, autocomplete, pagination cursor và kết quả từ search engine phải dùng **cùng tập điều kiện quyền**. Nếu chỉ lọc list sau `LIMIT/OFFSET`, trang có thể thiếu dữ liệu, `totalElements` sai, hoặc sự tồn tại tenant khác lộ qua số đếm. Nếu join sang đối tượng liên kết, ràng buộc quyền cho chính dữ liệu được đưa vào response, không chỉ bản ghi gốc.

Kiểm thử tối thiểu:

- Cùng một keyword xuất hiện ở A và B; Alice chỉ nhận bản ghi A; Bob chỉ nhận B.
- Filter `tenantId=B` phải bị từ chối hoặc bị ép về tập được phép theo hợp đồng; không trả bản ghi B. Thử filter rỗng, nhiều tenant, filter lồng nhau, khoảng thời gian, sort, page size lớn, page cuối.
- Kiểm tra `totalElements`, `totalPages`, count, group by, facets, suggestions và cursor; mọi giá trị chỉ phản ánh dữ liệu khả kiến.
- Kiểm tra kết quả sau khi thu hồi membership, sau khi chuyển tenant, ở cache hit và cache miss, và với bộ chỉ mục/search backend cập nhật chậm. Cache key phải gắn ngữ cảnh scope/quyền phù hợp.
- Khi policy yêu cầu quyền đọc một số record trong cùng tenant, test lọc theo ownership/ACL/attribute của record thay vì giả định toàn tenant được đọc.

## 7. Kiểm thử EXPORT: file tải xuống, job và liên kết chia sẻ

Export có thể là CSV/XLSX/ZIP/JSON, endpoint đồng bộ trả stream hoặc job bất đồng bộ trả file sau. Chính sách phải được áp dụng **cho từng dòng và cột nhạy cảm**, cùng phạm vi như chức năng search, đồng thời kiểm quyền `export` riêng nếu chính sách có quy định.

Các đường tấn công cần test: `export all` không kèm filter; chọn ID B qua `ids[]=...`; khai báo tenant B trong query; xuất theo report saved-filter do người khác tạo; gửi trang lớn; tự đổi job ID/download URL; tải file được tạo trước khi bị thu hồi quyền; dùng URL có chữ ký đã hết hạn hoặc bị chia sẻ cho actor khác.

Trình tự E2E cho export bất đồng bộ:

1. Alice yêu cầu export A. Server xác minh permission + scope, tạo job mang danh tính và thông tin policy cần thiết.
2. Bob hoặc Alice đã mất quyền thử đọc job/file của Alice. Xác nhận bị từ chối theo hợp đồng.
3. Thay đổi membership trước khi worker chạy, kiểm kết quả theo chính sách đã thiết kế: kiểm lại lúc thực thi, hoặc snapshot quyền có thời hạn và được kiểm soát chặt. Không âm thầm dùng quyền server/admin để xuất toàn bảng.
4. Mở/parsing tệp hoàn tất, kiểm tra **danh sách ID và nội dung thực tế**, tổng số dòng, header, cột nhạy cảm, nhiều trang, thứ tự, dòng đầu/cuối; khẳng định không có marker của B. Chỉ kiểm filename, status 200 hay kích thước file là chưa đủ.
5. Thử lỗi khi ghi stream giữa chừng và retry job; bảo đảm không tái xuất dữ liệu ngoài phạm vi hoặc để lại file có thể tải trái phép.

Với CSV, dữ liệu từ người dùng bắt đầu bằng ký tự công thức có thể gây **CSV formula injection** khi mở bằng bảng tính. Đây là yêu cầu kiểm thử an toàn đầu ra bổ sung, tách biệt với kiểm tra phạm vi: escape phù hợp theo hợp đồng và ứng dụng khách, không giả định chỉ đặt dấu nháy CSV là vô hiệu hóa công thức.

## 8. Đặt chốt kiểm tra ở đúng lớp trong Spring Security

Cấu hình request authorization giới hạn truy cập endpoint và functional permission. **Object-level authorization** cần chạy tại service/policy/domain query để bảo vệ cả đường gọi HTTP, async job hoặc service nội bộ. Ví dụ phần sau là **mảnh mã minh họa**, cần ghép repository và resolver thực của ứng dụng; không phải chương trình Java độc lập:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}

@Service
class DocumentService {
    private final DocumentRepository repository;
    private final TenantAccess tenantAccess;

    DocumentService(DocumentRepository repository, TenantAccess tenantAccess) {
        this.repository = repository;
        this.tenantAccess = tenantAccess;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:edit')")
    public void rename(long documentId, String newTitle,
                       Authentication authentication) {
        // requireActiveTenant xác minh membership/chính sách từ server.
        String tenantId = tenantAccess.requireActiveTenant(authentication);

        Document doc = repository.findByIdAndTenantId(documentId, tenantId)
            .orElseThrow(DocumentNotFoundException::new);
        doc.setTitle(newTitle); // Entity đã được ràng buộc scope.
    }
}
~~~

`@EnableMethodSecurity` kích hoạt kiểm tra `@PreAuthorize` trên phương thức Spring-managed. Đây là guard *quyền chức năng*; `findByIdAndTenantId` và `TenantAccess` thực hiện guard *phạm vi*. Code ví dụ giả định JPA dirty checking trong transaction, entity có setter hợp lệ và cấu hình exception mapping theo API. Với các trường hợp cập nhật hàng loạt hoặc concurrency, truy vấn ghi có điều kiện scope trực tiếp tại database và kiểm số dòng tác động giúp tránh khoảng hở giữa kiểm tra và ghi. Tránh self-invocation làm bỏ qua AOP proxy của method security; service phải được gọi qua bean được quản lý.

Nếu hệ thống dùng JWT, claim `tenant_id` không tự chứng minh membership còn hiệu lực. Cần xác minh issuer, audience, signature/expiry khi xác thực thật, và cơ chế policy/membership phù hợp; test bằng `jwt()` của Spring Security test là giả lập ngữ cảnh bảo mật cho kiểm thử authorization, **không** xác nhận toàn bộ quá trình xác minh chữ ký/token thật.

## 9. Chương trình Java 17 độc lập để kiểm bất biến năm thao tác

Ví dụ dưới đây dùng kho dữ liệu trong bộ nhớ nhằm minh họa *hợp đồng hành vi* có thể kiểm tự động; nó **không thay thế Spring Security/JPA/integration test**. Tạo file `CrossScopeContract.java` rồi chạy `javac CrossScopeContract.java` và `java CrossScopeContract` trên Java 17+. Actor A và B đều có đủ năm quyền chức năng; các ca bị từ chối vì khác phạm vi, không vì thiếu authority.

~~~java
import java.util.*;
import java.util.stream.Collectors;

public class CrossScopeContract {
    record Actor(String tenant, Set<String> permissions) {}
    record Doc(long id, String tenant, String title) {}
    static class Forbidden extends RuntimeException {}
    static class NotFound extends RuntimeException {}

    static class Store {
        private final Map<Long, Doc> data = new LinkedHashMap<>();
        private long nextId = 0;

        void allow(Actor actor, String requestedTenant, String operation) {
            if (!actor.tenant().equals(requestedTenant)
                    || !actor.permissions().contains(operation)) {
                throw new Forbidden();
            }
        }

        Doc create(Actor actor, String tenant, String title) {
            allow(actor, tenant, "create");
            Doc doc = new Doc(++nextId, actor.tenant(), title);
            data.put(doc.id(), doc);
            return doc;
        }

        private Doc visible(Actor actor, long id) {
            Doc doc = data.get(id);
            if (doc == null || !doc.tenant().equals(actor.tenant())) {
                throw new NotFound();
            }
            return doc;
        }

        void update(Actor actor, long id, String title) {
            allow(actor, actor.tenant(), "update");
            Doc original = visible(actor, id);
            data.put(id, new Doc(id, original.tenant(), title));
        }

        void delete(Actor actor, long id) {
            allow(actor, actor.tenant(), "delete");
            visible(actor, id);
            data.remove(id);
        }

        List<Doc> search(Actor actor, String requestedTenant, String text) {
            allow(actor, requestedTenant, "search");
            return data.values().stream()
                .filter(d -> d.tenant().equals(actor.tenant()))
                .filter(d -> d.title().contains(text))
                .toList();
        }

        String exportCsv(Actor actor, String requestedTenant) {
            allow(actor, requestedTenant, "export");
            return data.values().stream()
                .filter(d -> d.tenant().equals(actor.tenant()))
                .map(d -> d.id() + "," + d.title())
                .collect(Collectors.joining("\n"));
        }
    }

    static void expectRejected(Runnable action) {
        try {
            action.run();
        } catch (Forbidden | NotFound expected) {
            return;
        }
        throw new AssertionError("Expected cross-scope rejection");
    }

    static void check(boolean condition) {
        if (!condition) throw new AssertionError("Contract failed");
    }

    public static void main(String[] args) {
        Set<String> grants = Set.of("create", "update", "delete",
                                     "search", "export");
        Actor alice = new Actor("A", grants);
        Actor bob = new Actor("B", grants);
        Store store = new Store();
        Doc a = store.create(alice, "A", "ALICE_PRIVATE");
        Doc b = store.create(bob, "B", "BOB_SECRET");

        expectRejected(() -> store.create(alice, "B", "SPOOF"));
        check(store.data.size() == 2);
        System.out.println("PASS create");

        expectRejected(() -> store.update(alice, b.id(), "OVERWRITTEN"));
        check(store.data.get(b.id()).title().equals("BOB_SECRET"));
        store.update(alice, a.id(), "ALICE_EDITED");
        System.out.println("PASS update");

        expectRejected(() -> store.delete(alice, b.id()));
        check(store.data.containsKey(b.id()));
        Doc temporary = store.create(alice, "A", "TEMP");
        store.delete(alice, temporary.id());
        check(!store.data.containsKey(temporary.id()));
        System.out.println("PASS delete");

        expectRejected(() -> store.search(alice, "B", ""));
        List<Doc> visible = store.search(alice, "A", "");
        check(visible.size() == 1 && visible.get(0).id() == a.id());
        System.out.println("PASS search");

        expectRejected(() -> store.exportCsv(alice, "B"));
        String csv = store.exportCsv(alice, "A");
        check(csv.contains("ALICE_EDITED") && !csv.contains("BOB_SECRET"));
        System.out.println("PASS export");
    }
}
~~~

Kết quả chuẩn:

~~~text
PASS create
PASS update
PASS delete
PASS search
PASS export
~~~

Chương trình có cả positive control và negative control cho từng nhóm. Kho thực tế cần thêm transaction, dữ liệu quan hệ, validation, authn, isolation và kiểm soát đọc file. Lớp `Store` chỉ là mô hình nhỏ để thấy rõ bất biến; không triển khai production bằng map trong bộ nhớ.

## 10. Test Spring MVC và các lớp kiểm thử cần có

Dùng `spring-security-test` và Spring MVC Test/MockMvc cho servlet app. Với resource server JWT, có thể tạo principal giả qua `jwt()` và chỉ định authorities để tập trung kiểm tra policy; ví dụ thích nghi sau giả định ứng dụng có route, dữ liệu fixture và cơ chế nhận diện tenant từ principal. **Đoạn test là khung tích hợp, không biên dịch độc lập khi chưa có Controller/Repository/fixture của dự án.**

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Sql("/fixtures/two-tenants.sql")
class CrossTenantDocumentTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentRepository repository;

    @Test
    void aliceCannotEditBobsDocument() throws Exception {
        String originalTitle = repository.findById(202L)
            .orElseThrow().getTitle();

        mvc.perform(patch("/api/documents/{id}", 202L)
                .with(jwt().jwt(j -> j.subject("alice")
                    .claim("tenant_id", "A"))
                    .authorities(new SimpleGrantedAuthority("document:edit")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"ATTACK\"}"))
            .andExpect(status().isNotFound()); // Hợp đồng API dùng 404.

        assertThat(repository.findById(202L)
            .orElseThrow().getTitle()).isEqualTo(originalTitle);
    }
}
~~~

Các import/thiết lập test cần dùng theo ngữ cảnh: JUnit 5 `@Test`; Spring Boot Test `@SpringBootTest`, `@AutoConfigureMockMvc`; Spring Test `@Sql`; `MockMvc` và các static request/status matcher; `jwt()` từ `SecurityMockMvcRequestPostProcessors`; AssertJ `assertThat`; `spring-security-test` làm dependency test. Với API dùng CSRF cho state-changing requests, thêm CSRF token hợp lệ để test thực sự đi qua policy scope. Nếu API công bố `403` thay vì `404` cho outside scope, đổi assertion theo hợp đồng nhất quán.

Ba cấp test bổ sung lẫn nhau:

1. **Unit/policy test:** đưa actor, resource, tenant, role, membership, policy version vào hàm quyết định; test bảng allow/deny, quyền khi membership bị thu hồi, thiếu/invalid scope, ownership liên kết. Nhanh nhưng không bảo đảm mọi entrypoint đã gọi policy.
2. **Integration/service + database test:** chạy repository và transaction thật hoặc môi trường gần production; test predicate scope của SELECT/COUNT/UPDATE/DELETE, join, bulk write, soft delete, RLS (nếu có), outbox, transaction rollback, optimistic locking. Không mock phần logic mà bạn muốn chứng minh.
3. **HTTP/E2E + async test:** gọi mọi route thực sự bằng actor A/B (MockMvc và ít nhất một luồng bearer token xác thực thật khi cần); kiểm status, payload và trạng thái sau request. Với export, đọc file/binary/ZIP bằng parser tương ứng, chờ job đến trạng thái kết thúc có kiểm soát, rồi kiểm nội dung bằng ID và marker. Cần kiểm tra download URL và job permissions riêng.

Tạo hàm hỗ trợ fixture và assert tái sử dụng, nhưng **không** tái sử dụng cùng một ID mong đợi hoặc cùng một expected status cho mọi trường hợp khi policy khác nhau. Mỗi test cần mô tả actor, operation, resource scope và bất biến cụ thể.

## 11. Góc khuất thường bị bỏ sót

| Tình huống | Nguy cơ | Kiểm thử gợi ý |
| --- | --- | --- |
| Chỉ kiểm authority ở controller | Có quyền sửa chung nên sửa mọi ID | Actor có `edit` trong A vẫn bị từ chối trên B |
| Client gửi `tenantId` hoặc `ownerId` | Mass assignment/chọn scope giả | Cố mạo danh B qua path, header, body và nested object |
| Fetch theo ID rồi filter sau | IDOR hoặc rò metadata khi entity đã tải | So khớp entity, scope, response và DB trước–sau |
| Search filter sau paging | Count, total pages, facets và cursor bị lộ | So sánh toàn bộ metadata giữa A và B |
| Cache/search index dùng chung | Cache poisoning hoặc lộ dữ liệu cũ | Test cache hit/miss, index lag, policy revoke |
| Soft delete/cascade/batch | Xóa nhầm tài nguyên con ngoài tenant | Kiểm record con, relation, tombstone, outbox, file |
| Export chạy bằng service admin | Bỏ qua scope của người tạo job | Kiểm rows/file/job dưới identity của requester |
| URL file download dự đoán được | Download chéo actor | Thử đổi job/file ID và truy cập sau revoke |
| Policy chỉ kiểm tại request | Quyền thay đổi trước commit/job chạy | Test transaction race, permission revoke, retry |
| Quan hệ tài nguyên chéo tenant | Có quyền tạo A nhưng gắn foreign key B | Thử parentId, projectId, ownerId, attachment ID thuộc B |

Tùy hệ thống, thêm kiểm thử cho tổ chức phân cấp, nhóm chia sẻ tài liệu, role đa tenant, super-admin đúng thẩm quyền, dữ liệu đã anonymize, phân vùng DB và row-level security. Các quyền đặc biệt phải có test **cấp quyền đúng** và **giới hạn đặc quyền**, không thêm đường bypass mặc định.

## 12. Checklist QA trước khi kết luận chính sách an toàn

- [ ] Có ít nhất hai phạm vi độc lập, dữ liệu cùng keyword, và actor có đủ authority nhưng khác scope.
- [ ] Mỗi thao tác tạo/sửa/xóa/tìm kiếm/xuất có positive control, cross-scope negative, unauthenticated và thiếu functional permission.
- [ ] Bắt được scope trong path/query/body/header, quan hệ tham chiếu, bulk ID và batch endpoint.
- [ ] Mọi denial được kiểm **sau request**: database, version, soft-delete, links, files, job, outbox, side effect.
- [ ] Search kiểm cả rows, total/count, pagination, facets, suggestions, cache và lớp index.
- [ ] Export kiểm nội dung file thực, job, download URL, retry và thu hồi quyền.
- [ ] Điều kiện scope nằm trong service/query hoặc chính sách tương đương; thiếu scope thì fail closed.
- [ ] Cùng chính sách được áp dụng cho HTTP, job, service nội bộ và các route ít dùng.
- [ ] Error code phù hợp hợp đồng và không tiết lộ tài liệu ngoài scope.
- [ ] Test fixture độc lập, chạy được lặp lại, kiểm dữ liệu thật và không chỉ dựa vào mocks.

**Tiêu chí hoàn thành:** mọi request hợp lệ chỉ tác động dữ liệu trong phạm vi được phép; mọi request chéo phạm vi bị từ chối hoặc chỉ truy xuất tập được phép theo hợp đồng, không có rò rỉ qua payload, metadata, file hay side effect. Một bài test chỉ kiểm status HTTP chưa chứng minh bất biến này.

### Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): kích hoạt và kiểm thử `@PreAuthorize`.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): bảo vệ đường vào HTTP và phân biệt request authorization với chính sách dữ liệu.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()` request post-processor cho MockMvc.
