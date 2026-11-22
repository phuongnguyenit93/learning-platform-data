# Search scope authorization — Cấp quyền cho phạm vi tìm kiếm

## 1. Tìm kiếm không phải một đường đọc được miễn phân quyền

Một hệ thống có thể kiểm tra quyền rất kỹ khi đọc hồ sơ theo ID nhưng lại tìm trên toàn bộ bảng hoặc chỉ mục rồi trả tên, đoạn trích và số lượng kết quả. Khi đó người dùng vẫn có thể biết dữ liệu ngoài phạm vi qua tìm kiếm, dù endpoint chi tiết không cho mở hồ sơ.

**Search scope authorization** là việc xác định tập tài nguyên và những thông tin liên quan mà một chủ thể được phép tìm, lọc, thống kê hoặc nhìn thấy trong một ngữ cảnh cụ thể, rồi giữ giới hạn đó trên toàn bộ quá trình truy vấn và trả kết quả.

Một số lỗi điển hình:

- Người của tenant A tìm được tiêu đề hồ sơ tenant B.
- Người chỉ có quyền đơn vị A1 đổi filter sang A2 để xem thêm dữ liệu.
- Danh sách hit đã được lọc nhưng `totalCount` vẫn đếm toàn hệ thống.
- Gợi ý hoặc đoạn highlight lộ nội dung của tài liệu ngoài quyền.
- Chỉ mục còn ACL cũ và tiếp tục trả dữ liệu sau thu hồi.
- Một nhánh `OR` trong tìm kiếm vô tình bỏ điều kiện tenant hoặc quyền.

Bài học dùng danh sách đề nghị thanh toán nhiều tenant để thiết kế phạm vi tìm kiếm, truy vấn, đầu ra và kiểm thử các đường rò dữ liệu đó.

## 2. Phạm vi có thẩm quyền và filter người dùng là hai thứ khác nhau

Một mô hình tổng quát:

```text
Kết quả =
    tài_nguyên_được_phép_đọc(actor, action, context)
    giao với tài_nguyên_khớp_từ_khóa
    giao với các_filter_nghiệp_vụ_hợp_lệ
```

Sau đó chỉ trả các trường và metadata mà caller được phép biết.

| Thành phần | Nguồn có thẩm quyền | Ví dụ |
| --- | --- | --- |
| Tenant đang truy cập | Danh tính, lựa chọn tenant đã được server kiểm tra | Tenant A |
| Phạm vi đọc | Role, quan hệ, ownership, delegation và policy hiện tại | Đơn vị A1 cùng một số hồ sơ được chia sẻ |
| Filter nghiệp vụ | Đề nghị của client, được validate | Trạng thái đang chờ duyệt |
| Từ khóa | Input tìm kiếm trong hợp đồng | Mã đề nghị hoặc tên nhà cung cấp |
| Projection và thống kê | Policy về loại thông tin được công bố | Summary, count trạng thái, không có thông tin tài khoản |

Filter chỉ được chọn trong hoặc thu hẹp tập mà chính sách cho phép. Nó không phải một assignment cấp quyền.

### 2.1. Thiếu filter không được làm mất phạm vi bảo vệ

Nếu client không gửi `unitIds`, API có thể tìm trong toàn bộ tập caller được phép. Điều đó khác với tìm toàn tenant hoặc toàn hệ thống.

Nếu client gửi một tập rỗng, cần định nghĩa nó là không chọn đơn vị nào hay một giá trị không hợp lệ. Không để một nhánh xử lý tiện lợi biến tập rỗng thành bỏ điều kiện quyền.

### 2.2. Yêu cầu ngoài scope có thể bị giao hoặc bị từ chối

Một API có thể lấy giao của đơn vị được yêu cầu với scope được phép; API khác có thể từ chối yêu cầu scope không được chấp nhận. Cả hai cần hợp đồng rõ ràng và không tiết lộ không cần thiết về đơn vị ngoài quyền.

Trong mọi trường hợp, không lấy `unitIds` do client gửi làm danh sách đơn vị đã được cấp quyền.

## 3. Quyền dùng chức năng search khác với quyền đọc từng đối tượng

Một role có thể được mở màn hình tìm kiếm nhưng chỉ đọc hồ sơ do mình xử lý. Quyền `PAYMENT_SEARCH` không tự là quyền đọc mọi payment request.

Một action đọc dùng để xác định scope có thể là:

```text
PAYMENT_READ_SUMMARY
```

Tập được phép có thể đến từ nhiều nguồn:

- Sở hữu hồ sơ theo chính sách.
- Quyền đọc trong một đơn vị hoặc tập đơn vị.
- Phân công đang có hiệu lực.
- Grant chia sẻ trên những đối tượng cụ thể.
- Một nhiệm vụ kiểm toán có phạm vi và thời hạn riêng.

Các nguồn phải giữ đúng tenant, action, thời hạn và điều kiện. Quyền được chia sẻ một hồ sơ không tự mở quyền tìm mọi hồ sơ của cùng chủ sở hữu hoặc cùng đơn vị.

### 3.1. Có nhiều nguồn không có nghĩa mọi nguồn đều rộng

Ví dụ actor có quyền đọc toàn A1 và được chia sẻ riêng hồ sơ X ở A2. Kết quả hợp lệ có thể gồm A1 và X, không phải toàn A1 cộng toàn A2.

Một danh sách đơn vị được phép rỗng cũng không nhất thiết nghĩa actor không có dữ liệu nào: họ có thể còn quyền ownership hoặc grant riêng. Mỗi nguồn rỗng đóng góp một nhánh không khớp, không làm mở toàn bộ truy vấn.

### 3.2. Scope phải thuộc đúng actor và ngữ cảnh

Một người thuộc nhiều tenant chỉ được dùng quyền của tenant đang được kiểm tra. Cache, query plan hoặc cursor của một ngữ cảnh không được tự áp dụng sang ngữ cảnh khác.

Nếu có tìm kiếm xuyên tenant cho vận hành nền tảng, cần một action và miền thẩm quyền riêng. Không biến tenant bị bỏ trống thành chế độ toàn cục của endpoint thông thường.

## 4. Hợp đồng input tìm kiếm phải phân biệt quyền và sở thích

Ví dụ:

```http
POST /payment-requests/search
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "text": "nhà cung cấp",
  "filters": {
    "unitIds": ["unit-a1"],
    "states": ["PENDING_APPROVAL", "APPROVED"]
  },
  "sort": "CREATED_DESC",
  "pageSize": 25,
  "cursor": null
}
```

Server cần kiểm tra schema, giới hạn và những toán tử được hỗ trợ. Tenant, actor chuẩn hóa, danh sách quyền hiệu lực và trạng thái quản trị không được lấy từ body như một nguồn tin cậy.

Các field như sau không được tự mở scope:

```text
includeAllTenants
ignoreAcl
effectiveRole
asAdmin
allowedUnitIds
skipAuthorization
```

Nếu một lựa chọn như `includeArchived` được hỗ trợ, nó vẫn cần quyền đọc dữ liệu lưu trữ tương ứng. Một checkbox không được bỏ những điều kiện bảo vệ khác.

### 4.1. Query rỗng hoặc wildcard không tự là vượt quyền

API có thể cho từ khóa rỗng nghĩa là liệt kê toàn bộ dữ liệu trong scope. Đây là lựa chọn nghiệp vụ, cần giới hạn tài nguyên phù hợp.

Vấn đề bảo mật xuất hiện khi query rộng làm mất predicate quyền, hoặc một toán tử đặc biệt có thể thay root query bằng một phạm vi khác.

### 4.2. Không nhận một scope đã được client dựng sẵn

Tên kiểu dữ liệu như `AuthorizedScope` không tạo bảo đảm nếu nó được deserialize trực tiếp từ request. Scope cần được tạo bởi đường kiểm tra quyền có thẩm quyền và ràng buộc với actor, tenant, action cùng revision cần thiết.

## 5. Ghép predicate bằng đúng ngữ nghĩa logic

Một điều kiện tenant có thể bị vô hiệu hóa dù mọi giá trị đều được bind an toàn:

```sql
-- Không an toàn về scope nếu nhánh OR không được nhóm đúng.
WHERE p.tenant_id = :verifiedTenantId
  AND p.org_unit_id = ANY(:authorizedUnitIds)
  AND p.display_reference ILIKE :pattern
   OR p.supplier_display_name ILIKE :pattern
```

Nhánh tên nhà cung cấp có thể khớp mà không chịu toàn bộ điều kiện đứng trước. Đây là lỗi logic phân quyền, không nhất thiết là SQL injection.

Phải giữ nhóm bảo vệ bắt buộc ngoài các nhánh tìm kiếm:

```text
tenant_predicate
AND authorization_predicate
AND business_filter_predicate
AND (text_match_1 OR text_match_2 OR text_match_3)
```

OWASP nhấn mạnh việc kết hợp hạn chế quyền với predicate tenant và ứng dụng bằng phép AND, đồng thời không được bỏ một biểu thức không dịch được sang query. [OWASP: Authorization Decisions and Output Handling](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Decisions_And_Output_Handling_Cheat_Sheet.html#security-considerations)

### 5.1. OR vẫn có chỗ hợp lệ trong predicate quyền

Một policy có thể cho đọc nếu actor là owner, thuộc đơn vị được phép hoặc có grant trực tiếp. Đây là nhóm OR được server định nghĩa, đặt bên trong các giới hạn bắt buộc như tenant.

Không trộn OR từ query của client với OR của các nguồn cấp quyền rồi làm mất ranh giới hai nhóm.

### 5.2. Giá trị không phải cú pháp

Bind từ khóa và giá trị filter. Những lựa chọn cấu trúc như tên field, sort hoặc toán tử phải đến từ tập được hỗ trợ và được kiểm tra quyền sử dụng.

Không nối một chuỗi debug của policy engine hoặc raw query DSL vào SQL. Có chữ ký hoặc đến từ một service được tin cậy không tự làm chuỗi đó trở thành một ngôn ngữ truy vấn an toàn để thực thi tùy ý.

## 6. SQL minh họa phạm vi tìm kiếm có nhiều nguồn quyền

Giả sử policy đơn giản cho phép đọc summary của hồ sơ chưa lưu trữ khi actor là owner, có quyền trên đơn vị hoặc có một grant đối tượng dùng được.

```sql
SELECT p.id,
       p.created_at,
       p.display_reference,
       p.supplier_display_name,
       p.state,
       p.amount_minor,
       p.currency
FROM payment_request p
WHERE p.tenant_id = :verifiedTenantId
  AND p.archived_at IS NULL
  AND (
        p.owner_subject_id = :verifiedSubjectId
        OR p.org_unit_id = ANY(:authorizedUnitIds)
        OR p.id = ANY(:authorizedDelegatedRequestIds)
      )
  AND (
        p.display_reference ILIKE :validatedPattern
        OR p.supplier_display_name ILIKE :validatedPattern
      )
  AND p.state = ANY(:validatedRequestedStates)
ORDER BY p.created_at DESC, p.id DESC
LIMIT :fetchCount;
```

Đây là SQL minh họa cho PostgreSQL với tham số được bind đúng kiểu, gồm các mảng ID nếu sử dụng. Biến thể có cursor cần thêm predicate vị trí tương thích mà vẫn giữ các nhóm quyền bắt buộc.

Các danh sách `authorized...` do server tính từ nguồn quyền hiện tại theo hợp đồng, không phải giá trị đổi tên từ request. Grant đối tượng phải đúng action và còn dùng được, không chỉ có bản ghi tồn tại.

Policy thực tế có thể còn điều kiện phân loại, ownership, delegation hoặc thời gian phức tạp hơn. Ví dụ này không phải công thức quyền phổ quát cho mọi hồ sơ thanh toán.

### 6.1. Danh sách ID quá lớn cần một cơ chế phù hợp

Có thể thay danh sách bằng quan hệ, EXISTS hoặc query plan có ngữ nghĩa tương đương. Không cắt bớt danh sách quyền rồi coi kết quả là toàn bộ tập được phép, cũng không bỏ restriction khi vượt giới hạn.

Nếu nguồn chỉ trả được một tập con đã xác nhận, API phải phân biệt kết quả giới hạn với một kết luận tìm kiếm đầy đủ.

### 6.2. Join phải giữ quan hệ và tenant

Nếu tìm qua bảng nhà cung cấp, cần join hoặc EXISTS theo đúng quan hệ, gồm tenant khi model yêu cầu. Quyền đọc payment không tự cho phép một join sai lấy dữ liệu nhà cung cấp ở tenant khác.

Nếu dùng tên nhà cung cấp được sao chép vào read model như ví dụ, cần quản lý nguồn và mức công bố của trường đó; dữ liệu denormalize không mất tính nhạy cảm chỉ vì nằm trong bảng tìm kiếm.

## 7. Field nào được tìm cũng là một câu hỏi phân quyền

Một caller có thể được đọc summary nhưng không được biết tài khoản nhận tiền. Nếu API cho filter chính xác theo số tài khoản rồi trả count, caller vẫn có thể kiểm tra một giá trị bí mật có khớp hay không.

Cần phân loại khả năng theo field:

| Khả năng | Ví dụ |
| --- | --- |
| Trả về | Hiển thị mã hồ sơ, trạng thái |
| Tìm từ khóa | Tìm trên mã hoặc tên nhà cung cấp được công bố |
| Filter | Chọn trạng thái hoặc khoảng ngày được hỗ trợ |
| Sort | Sắp xếp theo thời điểm tạo hoặc trường được phép |
| Facet hoặc aggregate | Đếm theo trạng thái trong scope |
| Highlight hoặc snippet | Trích đoạn từ những field được phép xem |

Không mặc định field bị ẩn trong response vẫn được dùng để tìm, sort hoặc thống kê. Nếu sản phẩm chủ ý cung cấp khả năng dò khớp mà không trả giá trị gốc, đó là một quyền và rủi ro thông tin cần được thiết kế riêng.

### 7.1. Search-all-fields có thể vượt hợp đồng

Một engine có thể index nhiều field hơn UI hiển thị. Không để từ khóa mặc định tìm trên mọi field nội bộ, tài liệu đính kèm hoặc metadata nếu caller không có quyền với những nội dung đó.

Cần giới hạn field được tìm trong plan và kiểm tra các cấu trúc lồng nhau. Một field mới được thêm vào index không nên tự trở thành một kênh tìm kiếm công khai.

### 7.2. Projection không phải chỉ xóa một field ở frontend

Server phải trả đúng biểu diễn được cấp. Không tải cả dữ liệu nhạy cảm về trình duyệt rồi chỉ ẩn bằng giao diện.

Với policy có nhiều mức nhìn trên từng hồ sơ, mapper hoặc query projection cần dùng đúng quyền theo dòng, không chỉ một role chung cho cả response.

## 8. Count, facet, suggestion và snippet đều thuộc đầu ra cần bảo vệ

### 8.1. Count và facet

Hit list được lọc đúng nhưng count toàn hệ thống vẫn có thể lộ sự tồn tại hoặc phân bố dữ liệu. Facet theo nhà cung cấp, đơn vị hoặc trạng thái cũng cần cùng phạm vi được phép và quyền thống kê tương ứng.

Count của toàn bộ tập khớp không phải count của trang hiện tại. Cần định nghĩa rõ, nhưng cả hai đều không được đếm dữ liệu ngoài policy.

Một số API trả estimate; chữ “ước lượng” không cho phép tính cả dữ liệu ngoài quyền.

### 8.2. Gợi ý và autocomplete

Một gợi ý từ tên tài liệu riêng tư hoặc lịch sử tìm của người khác có thể tiết lộ dữ liệu ngay cả khi không có hit nào được trả.

Nguồn suggestion cần có scope và điều kiện field phù hợp. Không dùng một từ điển chung toàn hệ thống rồi giả định danh sách kết quả chính đã xử lý mọi rò rỉ.

### 8.3. Highlight và snippet

Đoạn trích phải được tạo từ field và phiên bản nội dung mà caller được phép xem. Không lấy snippet từ toàn tài liệu rồi chỉ bỏ một số field trong object JSON.

Nội dung người dùng nhập có thể chứa ký tự hiển thị đặc biệt. Renderer cần xử lý an toàn; quyền đọc snippet không bao gồm quyền làm nội dung của một tài liệu thực thi trong công cụ người duyệt.

### 8.4. Score, explain và metadata nội bộ

Rà soát những điểm số, lý do xếp hạng hoặc thông tin chẩn đoán mà API công bố. Chúng có thể phụ thuộc dữ liệu hoặc cấu trúc ngoài phạm vi mà UI cần biết.

Không tự khẳng định mọi engine đều rò cùng một loại metadata; cần kiểm tra cấu hình và hợp đồng cụ thể. Nếu không cần công bố debug output, không mở nó chỉ để tiện phát triển.

## 9. Authorization filter cần có kết quả rõ ràng

Khi policy engine trả filter hoặc query plan, cần hiểu chính xác ngữ nghĩa mà adapter hỗ trợ.

Một mô hình ứng dụng có thể phân biệt:

| Kết quả | Hành vi |
| --- | --- |
| Cho phép trong miền được yêu cầu | Vẫn giữ tenant và các giới hạn ứng dụng bắt buộc |
| Từ chối toàn bộ | Không trả protected data hoặc metadata của nó |
| Có điều kiện | Biên dịch đầy đủ predicate được hỗ trợ |
| Không xác định hoặc output không dùng được | Không coi là không có restriction |

Không dùng `null`, danh sách rỗng hoặc lỗi parse filter để biểu diễn mơ hồ cả “không có dữ liệu được phép” lẫn “không cần kiểm tra”.

### 9.1. Giữ ngữ nghĩa khi dịch policy

Null, thuộc tính thiếu, quan hệ thành viên, join và phủ định có thể được hai hệ thống hiểu khác nhau. Adapter cần kiểm tra đầy đủ; một biểu thức không hỗ trợ phải bị xử lý rõ ràng, không bị bỏ qua để phần query còn lại chạy rộng hơn.

Một debug string không phải query plan có thể thực thi an toàn. Dùng biểu diễn có cấu trúc và adapter phù hợp, không chạy một chuỗi tùy ý như SQL.

### 9.2. Quyết định tìm được không cấp quyền cập nhật

Danh sách ID được phép đọc không tự là danh sách được phép duyệt, hủy hoặc xóa. Action tiếp theo vẫn phải kiểm tra riêng trên đối tượng tại gate của nó.

Nếu một nút “chọn tất cả kết quả” tạo batch action, batch phải ràng buộc đúng query hoặc manifest và kiểm tra quyền action tương ứng, không dùng quyền search thay quyền thực thi.

## 10. Ví dụ Java: tạo plan từ scope server và filter client

Đoạn mã minh họa tổ chức service tìm kiếm trên dữ liệu có thể áp dụng predicate quyền tại query. Các repository, policy, kiểu dữ liệu và helper cần được triển khai; constructor injection được lược bỏ.

```java
@Service
public class PaymentRequestSearchService {
    private final PaymentSearchAuthorization authorization;
    private final PaymentSearchInputPolicy inputPolicy;
    private final AuthorizedSearchPlanner planner;
    private final SearchCursorService cursors;
    private final PaymentSearchRepository repository;
    private final PaymentSearchViewMapper views;

    @Transactional(readOnly = true)
    public PaymentSearchPage search(
            VerifiedActor actor,
            PaymentSearchInput input) {

        actor.requireAuthenticated();

        CanonicalSearchSpec requested =
                inputPolicy.validateAndCanonicalize(input);

        SearchAccessDecision decision = authorization.resolve(
                actor, SearchAction.PAYMENT_READ_SUMMARY);

        if (decision.isIndeterminate()) {
            throw new SearchAuthorizationUnavailableException();
        }
        if (decision.isDenied()) {
            return PaymentSearchPage.emptyWithoutProtectedMetadata();
        }

        CurrentSearchScope scope = decision.requireUsableScope();
        scope.requireBoundTo(
                actor.tenantId(), actor.canonicalSubjectId());

        AuthorizedSearchPlan plan = planner.combineByIntersection(
                scope, requested);
        plan.requireSupportedFieldOperations();

        SearchPosition position = cursors.verifyForRequest(
                input.cursor(), actor, plan);

        int pageSize = requested.effectivePageSize();
        int fetchCount = Math.addExact(pageSize, 1);

        List<AuthorizedPaymentRow> rows = repository.searchAuthorized(
                plan, position, fetchCount);

        AuthorizedPageWindow window = AuthorizedPageWindow.from(
                rows, pageSize);

        List<PaymentSummary> results = views.toAllowedSummaries(
                window.visibleRows(), scope.outputPolicy());

        SearchAggregates aggregates = repository.aggregateAuthorized(
                plan.withoutPageBoundary());

        String nextCursor = window.hasNext()
                ? cursors.issueFromLastVisibleRow(actor, plan, window)
                : null;

        return new PaymentSearchPage(results, aggregates, nextCursor);
    }
}
```

Các dependency `final` cần constructor thực tế. Transaction read-only không tự tạo policy hoặc đồng bộ quyền từ một IAM ngoài; cần thiết kế nguồn và mức nhất quán phù hợp cho scope và query.

Trong mẫu, từ chối scope được biểu diễn thành trang rỗng không có metadata được bảo vệ. API có thể chọn trả lỗi quyền thay vì trang rỗng; lựa chọn cần nhất quán và không dùng aggregate toàn hệ thống cho nhánh từ chối.

`combineByIntersection()` phải giữ các giới hạn tenant, action và policy bất biến; nó không được nhận một raw predicate từ client rồi thay scope. `AuthorizedSearchPlan` phải do đường tin cậy tạo, không là một DTO được deserialize nguyên từ request.

### 10.1. Những hợp đồng repository cần được chứng minh

`searchAuthorized()` áp dụng scope trước LIMIT và chỉ trả các cột cần cho projection được phép. `aggregateAuthorized()` giữ cùng predicate quyền và filter nghiệp vụ, nhưng bỏ position phân trang nếu count được định nghĩa cho toàn bộ tập khớp.

Nếu data query và aggregate query cần phản ánh chính xác cùng một snapshot dữ liệu, phải dùng cơ chế nhất quán phù hợp. Một annotation không tự bảo đảm mọi statement hoặc nguồn ngoài nhìn cùng trạng thái.

Trong ví dụ, các aggregate được yêu cầu đã được planner giới hạn theo quyền. Không để một caller chỉ được xem summary tự thêm một phép tổng hợp trên field bị bảo vệ.

## 11. Chỉ mục tìm kiếm và vấn đề ACL cũ

Một chỉ mục thường là bản sao phục vụ đọc. Khi dữ liệu hoặc quyền thay đổi, cập nhật chỉ mục có thể đến muộn.

Tình huống nguy hiểm:

```text
T1: B có quyền đọc hồ sơ X, chỉ mục lưu ACL đó.
T2: Quyền B bị thu hồi ở nguồn có thẩm quyền.
T3: Chỉ mục chưa cập nhật, search tiếp tục trả X cho B.
```

Cần xác định độ trễ thu hồi được chấp nhận và cơ chế đáp ứng nó. Chỉ đặt tenant trong mỗi document chưa đủ nếu quyền còn khác nhau giữa những đối tượng cùng tenant.

### 11.1. Ba hướng thiết kế cần đánh giá theo khả năng thực tế

| Hướng | Điều cần bảo đảm |
| --- | --- |
| Search ở nguồn có thẩm quyền với predicate quyền | Query, policy và đầu ra giữ đúng mức nhất quán cần thiết |
| Engine áp dụng cơ chế quyền đủ mới | ACL, revision hoặc giao thức đồng bộ đáp ứng thời hạn thu hồi và mọi đầu ra liên quan |
| Engine chỉ tìm candidate, nguồn chính kiểm tra lại | Candidate chưa được công bố, dữ liệu và metadata cuối chỉ dùng phần được xác nhận |

Không có lựa chọn nào tự đúng chỉ vì dùng một nhãn sản phẩm hoặc một loại access control. Cần kiểm tra những bảo đảm thật sự của hệ thống.

### 11.2. Recheck hit không sửa được mọi metadata cũ

Nếu loại các hit bị từ chối ở nguồn chính nhưng vẫn trả count, facet hoặc snippet của chỉ mục cũ, thông tin vẫn có thể lộ.

Với mô hình candidate, chỉ công bố nội dung đã được xác nhận và có thể phải bỏ hoặc tính lại metadata. Kết quả ước lượng cũng không được có nguồn ngoài quyền chỉ vì nó không chính xác tuyệt đối.

### 11.3. Candidate scan có giới hạn phải diễn đạt đúng

Sau hậu kiểm, một lô candidate có thể không đủ N dòng được phép. Nếu tiếp tục quét, cần giới hạn chi phí và không công bố các ID bị từ chối qua token hoặc thông tin tiến độ.

Nếu chưa thể kết luận còn kết quả được phép hay không, không tự báo hết tập hoặc `hasNext=true` chỉ vì index còn hit thô. Có thể cần trạng thái tìm chưa hoàn tất hoặc cơ chế tiếp tục riêng phù hợp chính sách metadata.

Những tín hiệu về độ dài quét hoặc thời gian cũng cần được đánh giá theo mức bảo mật yêu cầu. Nếu không thể cung cấp hợp đồng đúng với kiến trúc hiện tại, cần đổi cách tìm hoặc thu hẹp chức năng, không giả rằng lọc hit cuối cùng đã giải quyết mọi vấn đề.

## 12. Pagination và cursor phải giữ nguyên scope

Trang đầu đúng quyền không bảo đảm các trang sau đúng. Mỗi request tiếp theo cần kiểm tra actor, tenant, quyền hiện tại và ràng buộc cursor với query theo hợp đồng.

Cursor có thể cần bảo vệ:

```text
resource/action
tenant và chủ thể hoặc scope
query digest
sort và chiều duyệt
vị trí hoặc read view
revision và thời hạn phù hợp
```

Cursor không phải credential. Một token hợp lệ về tính toàn vẹn không cho dùng quyền cũ sau thu hồi hoặc truy cập một tenant khác.

### 12.1. Không lấy position từ dòng ngoài quyền để công bố tùy ý

Với query đã lọc quyền trước LIMIT, cursor có thể tạo từ dòng cuối được trả theo thuật toán đã chọn. Với candidate scan, position nội bộ có thể liên quan dữ liệu chưa được phép công bố nên cần thiết kế bảo vệ riêng.

HMAC không che nội dung payload. Nếu cursor chứa ID hoặc thông tin candidate bị từ chối, không thể coi nó bí mật chỉ vì client không được sửa.

### 12.2. Live search không phải snapshot vĩnh viễn

Dữ liệu và quyền có thể thay đổi giữa các trang. Cần định nghĩa LIVE hoặc snapshot mode và cách xử lý bắt đầu lại khi scope thay đổi.

Một snapshot dữ liệu không tự cấp quyền đọc mãi. Export hoặc read view cần policy về thời hạn, thu hồi và những đầu ra được công bố.

## 13. Archive, quan hệ liên quan và các đường tìm phụ

### 13.1. Dữ liệu lưu trữ không chỉ là một filter giao diện

Nếu archive cần quyền khác, `includeArchived=true` phải được kết hợp với quyền tương ứng theo scope và từng nguồn. Không lấy một quyền archive ở A1 để mở dữ liệu được chia sẻ ở A2 nếu nguồn đó không cho phép.

Các trạng thái xóa hoặc ẩn vì policy cũng cần quy tắc riêng. Đổi một tham số hiển thị không được bỏ ranh giới bảo vệ bắt buộc.

### 13.2. Quan hệ cha không tự bao phủ mọi dữ liệu con

Tìm thấy order không tự được đọc mọi payment, chứng từ hay dữ liệu nhà cung cấp liên quan. Những field hoặc quan hệ được đưa vào hit cần có chính sách công bố phù hợp.

Khi filter qua bảng con, bảo đảm join đúng quan hệ. Một ID con đúng kiểu nhưng thuộc đối tượng khác không được làm lộ dữ liệu hoặc làm query vượt scope.

### 13.3. Export, report và tìm kiếm quản trị

Export không được dùng một query không có authorization vì “người dùng đã lọc trên màn hình”. Worker export cần scope hoặc command có ràng buộc và hợp đồng đánh giá lại phù hợp.

Report, dashboard, API hỗ trợ và endpoint autocomplete cũng là những đường đọc. Không chỉ kiểm tra endpoint search chính rồi để những đường này trả dữ liệu rộng hơn.

## 14. Cache, thời điểm quyền và lớp bảo vệ dữ liệu

### 14.1. Cache không chỉ theo từ khóa

Một cache theo `text + filters` có thể trả kết quả của người có scope rộng cho người khác. Khóa và giới hạn sử dụng cần bao gồm tenant, action, chủ thể hoặc scope, projection và những revision liên quan.

TTL ngắn không tự đáp ứng thu hồi tức thời. Nếu quyền thay đổi, hệ thống cần cơ chế đúng với thời hạn đã cam kết cho action đọc đó.

### 14.2. Phải chọn mốc quyết định có ý nghĩa

“Quyền hiện tại” cần được hiểu theo gate, read context và độ mới nguồn đã xác định. Không lấy scope từ đầu phiên dài rồi coi nó đúng cho mọi tìm kiếm về sau.

Nếu quyền đến từ nguồn ngoài, mô tả giới hạn đồng bộ. Khi nguồn bắt buộc không dùng được, không tự bỏ restriction để có kết quả trả nhanh.

### 14.3. Row-level security là lớp bổ sung có giả định

PostgreSQL có chính sách theo hàng, nhưng một số chủ thể đặc quyền hoặc owner có thể bypass theo cấu hình. Do đó phải kiểm tra đúng tài khoản thực thi và chính sách, không suy từ việc đã bật tính năng rằng mọi query đều chịu cùng ranh giới. [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

Với connection pool, ngữ cảnh tenant hoặc chủ thể của kết nối cần được thiết lập và quản lý theo giao thức phù hợp. Không để một request sau dùng lại scope còn sót từ request trước.

Lớp dữ liệu không thay thế quyền field, đầu ra của search engine khác hoặc các đường không đi qua cùng cơ chế.

## 15. Lỗi phản hồi và quan sát vận hành

Một lỗi phạm vi không cần xác nhận đơn vị hay hồ sơ tenant khác có tồn tại. Input query sai, không có quyền và nguồn authorization lỗi là những trường hợp cần phân biệt trong xử lý nội bộ và hướng phục hồi.

Không tự trả một tập dữ liệu rộng hơn khi filter không parse được. Một plan không hỗ trợ không được thay bằng match-all.

Audit hoặc log chẩn đoán có thể giữ actor, tenant, action, query fingerprint, scope revision, loại output và kết quả áp dụng quyền. Tránh ghi toàn bộ từ khóa hoặc dữ liệu nhạy cảm nếu không có nhu cầu và quyền truy cập phù hợp.

| Tín hiệu | Điều cần xem xét |
| --- | --- |
| Search trả count nhưng không có hit được phép | Có thể metadata dùng scope khác hoặc có hậu kiểm không đầy đủ |
| Query OR hoặc wildcard làm tăng kết quả khác thường | Kiểm tra nhóm predicate và toán tử được hỗ trợ |
| Sau thu hồi vẫn có hit hoặc suggestion cũ | Index, cache hoặc nguồn quyền có thể không đáp ứng độ mới cần thiết |
| Một user dùng lại cursor hay cache của scope khác | Có thể thiếu binding theo tenant hoặc chủ thể |
| Filter không hỗ trợ nhưng request vẫn thành công rộng hơn | Adapter có thể bỏ biểu thức bắt buộc |
| Export khác kết quả tìm kiếm về phạm vi | Có thể có đường đọc bỏ authorization |
| Predicate hoặc scope rỗng làm query thành toàn cục | Đang nhầm không được phép với không có restriction |

Một search không có kết quả có thể do dữ liệu, filter hoặc scope; không cần mở thêm quyền để phân biệt những trường hợp mà caller không được biết.

## 16. Kiểm thử scope bằng dataset có đối chứng

### 16.1. Fixture cần có dữ liệu ngoài quyền

Ví dụ chuẩn bị:

```text
Tenant A:
  A1 có hồ sơ actor được phép đọc.
  A2 có hồ sơ actor không được đọc.
  Một hồ sơ X tại A2 được chia sẻ riêng cho actor.

Tenant B:
  Hồ sơ có từ khóa giống các hồ sơ ở A.

Trong mỗi nhóm có field, trạng thái và thời điểm trùng nhau đủ để query khớp.
```

Nếu từ khóa chỉ khớp dữ liệu được phép, test có thể không phát hiện predicate quyền bị bỏ. Cần dữ liệu cấm khớp cùng các nhánh tìm kiếm.

### 16.2. Ma trận quyền và query

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Không gửi unit filter | Chỉ trong scope hiện tại, không tự toàn tenant |
| Gửi A2 thay A1 | Không mở A2 ngoài grant cụ thể |
| Từ khóa khớp tenant B ở nhánh OR thứ hai | Tenant B vẫn bị loại |
| Quyền đơn vị rỗng nhưng còn ownership | Chỉ nguồn ownership hợp lệ tiếp tục áp dụng |
| Mọi nguồn quyền đều không cho phép | Không có protected hit hoặc metadata |
| Một hồ sơ được chia sẻ tại A2 | Chỉ hồ sơ đó, không toàn A2 |
| Unit filter rỗng hoặc null | Đúng hợp đồng, không bỏ predicate bảo vệ |
| Plan luôn từ chối hoặc lỗi nguồn quyền | Không fallback thành query không hạn chế |
| Filter toán tử chưa hỗ trợ | Bị xử lý rõ ràng, không bỏ phần không dịch được |

### 16.3. Kiểm thử field và metadata

1. Từ khóa chỉ xuất hiện trong field caller không được tìm.
2. Count và facet có các dòng cấm khớp cùng query.
3. Suggestion có thể lấy tên riêng tư từ nguồn chung.
4. Snippet của phiên bản cũ chứa nội dung đã không còn được công bố.
5. Sort hoặc aggregate theo field ẩn tạo ra kênh suy đoán.
6. Export dùng cùng query nhưng đi một repository khác.
7. Raw debug output hoặc explain trả cấu trúc dữ liệu ngoài phạm vi.

Kiểm tra mọi đầu ra đã công bố, không chỉ mảng `items`. Một response không có ID cấm vẫn có thể chưa đạt yêu cầu nếu metadata tiết lộ chúng.

### 16.4. So sánh filter với quyết định theo đối tượng

Trên fixture nhỏ có thể liệt kê, tính tập kỳ vọng bằng các quyết định đọc theo đối tượng có thẩm quyền rồi so với tập search trả sau khi áp cùng điều kiện nghiệp vụ.

Không dùng chính biểu thức query đang cần kiểm tra làm cả implementation lẫn expected result. Chọn các case về owner, đơn vị, delegation, null, join và scope rỗng để phát hiện dịch sai ngữ nghĩa.

Với dataset cố định, duyệt hết các trang để kiểm tra không có dòng cấm, không mất dòng được phép trái hợp đồng và thứ tự hoặc cursor hoạt động đúng.

## 17. Kiểm thử thay đổi quyền và những lỗi thiết kế cần tránh

### 17.1. Thay đổi có điều khiển giữa các request

Dùng điểm đồng bộ hoặc những bước rõ ràng:

```text
Đọc trang đầu hoặc thực hiện search khi còn quyền.
Thu hồi membership, grant hoặc thay quan hệ đối tượng.
Giữ index hoặc cache ở trạng thái cũ theo fixture kiểm thử.
Gửi search, count, suggestion và trang tiếp theo.
```

Kết quả phải đáp ứng gate và giới hạn thu hồi mà hệ thống cam kết. Không dùng một khoảng sleep tùy ý rồi coi mọi nguồn chắc chắn đã đồng bộ.

Với yêu cầu output chỉ phụ thuộc tập được phép, thêm các dòng ngoài quyền không nên làm lộ chúng qua những field và metadata đã được cam kết. Nếu ranking dùng thống kê rộng hơn, cần đánh giá ảnh hưởng đó theo policy thay vì mặc định chỉ lọc ID là đủ.

### 17.2. Kiểm tra mọi kênh thực thi

Test API trực tiếp, UI, export worker và công cụ hỗ trợ theo đúng phạm vi chúng có thể gọi. Mock policy trả allow cho mọi case hoặc mock repository trả sẵn danh sách sạch không chứng minh query đã giữ scope.

Các bảo đảm về query, transaction, connection context và adapter cần integration test ở tầng phù hợp. Tính đúng của một hàm `canRead()` riêng lẻ không tự chứng minh mọi đầu ra search đã dùng nó.

| Cách làm | Vì sao sai | Hướng thay thế |
| --- | --- | --- |
| Filter đơn vị là quyền đơn vị | Client tự chọn phạm vi rộng hơn | Scope server kết hợp giao với filter |
| Tenant predicate đứng trước một OR không nhóm | Nhánh sau có thể đi vòng | Nhóm bắt buộc và nhóm tìm kiếm tách rõ |
| Có search permission là đọc mọi object | Bỏ quyền theo đối tượng | Policy đọc đúng action và scope |
| Field ẩn vẫn tìm được mặc định | Có thể dò giá trị không được công bố | Quyền searchable, filterable và aggregate rõ ràng |
| Lọc hit nhưng giữ count toàn cục | Metadata vẫn tiết lộ dữ liệu | Cùng phạm vi cho mọi đầu ra |
| ACL trong index được coi luôn mới | Thu hồi có thể chưa tới bản sao | Giao thức độ mới hoặc kiểm tra nguồn chính |
| Recheck N hit rồi coi phân trang đã đúng | Có thể thiếu trang, sai hasNext hoặc lộ candidate | Thiết kế quét, metadata và giới hạn đầy đủ |
| Scope rỗng hoặc lỗi thì bỏ filter | Biến không đủ quyền thành toàn quyền | Phân biệt deny, conditional và indeterminate |
| Cursor có chữ ký thay authorization | Có thể dùng scope cũ hoặc khác caller | Kiểm tra quyền trên mỗi request |
| Export nội bộ không cần scope | Tạo đường đọc rộng hơn API chính | Ràng buộc scope và action tại worker |
| Có row security nên không test tài khoản thực | Tài khoản hoặc nguồn khác có thể bypass | Kiểm thử đúng principal và đường dữ liệu |

## 18. Bài tập thiết kế

Thiết kế tìm kiếm đề nghị thanh toán cho hệ thống nhiều tenant. Actor có quyền toàn đơn vị A1, được chia sẻ một hồ sơ X ở A2, chỉ được đọc summary và có thể dùng filter trạng thái, count, facet cùng autocomplete.

Hãy mô tả:

1. Scope có thẩm quyền được tạo từ những nguồn nào và khác filter của client ra sao?
2. Predicate tenant, các nguồn quyền và các nhánh từ khóa được nhóm thế nào?
3. Vì sao quyền riêng trên X không mở toàn A2?
4. Field nào được trả, tìm, lọc, sort, facet hoặc tạo snippet?
5. Count, suggestion, export và cursor tiếp theo giữ cùng phạm vi như thế nào?
6. Khi index chưa cập nhật ACL hoặc quyền bị thu hồi giữa hai trang, hệ thống bảo đảm điều gì và bằng cơ chế nào?
7. Scope rỗng, nguồn quyền lỗi hoặc filter không dịch được có kết quả gì?
8. Những fixture và assertion nào chứng minh không có dữ liệu ngoài quyền xuất hiện qua cả hit lẫn metadata?

Một thiết kế đạt yêu cầu phải giữ quyền trên toàn bộ bề mặt tìm kiếm: từ việc chọn tập ứng viên, ghép điều kiện, phân trang đến từng trường và metadata được công bố, kể cả khi dữ liệu hoặc quyền thay đổi giữa các lần đọc.
