# Giảm chức năng có kiểm soát và điều kiện trả dữ liệu rút gọn

## 1. Bối cảnh: không phải mọi dependency đều quan trọng như nhau

Trong module **INTEGRATION_API_REST**, API cần có URI, phương thức HTTP, mã trạng thái, hợp đồng dữ liệu, cache, xác thực và phân quyền rõ ràng. Tuy nhiên, một endpoint có thể tổng hợp dữ liệu từ nhiều dịch vụ: khi **một nguồn phụ bị lỗi**, có nhất thiết phải làm hỏng toàn bộ response?

Ví dụ **GET /api/v1/products/{id}/overview** trên hệ thống thương mại điện tử:

- **Product Core**: ID, tên, giá đang có hiệu lực, tiền tệ, khả năng hiển thị trong tenant.
- **Ratings Service**: điểm đánh giá trung bình và số lượt đánh giá.
- **Recommendation Service**: các sản phẩm gợi ý dựa trên hành vi.
- **Inventory Service**: tồn kho dùng để xác nhận đặt hàng, không phải nguồn dữ liệu có thể giả định tùy ý.

Nếu Ratings hoặc Recommendation quá tải, UI vẫn có thể hiển thị **tên và giá được xác thực** nhưng ẩn điểm đánh giá/gợi ý. Đó là **giảm chức năng có kiểm soát** (*graceful degradation*). Ngược lại, nếu không thể xác định giá chính xác hoặc quyền xem sản phẩm, trả một giá đoán, giá cũ không được phép hoặc bỏ qua kiểm quyền là **sai ngữ nghĩa và nguy hiểm**.

**Kết quả học tập:**

1. Phân loại **dữ liệu bắt buộc, dữ liệu tùy chọn, dữ liệu được phép stale và dữ liệu không được fallback** theo từng operation.
2. Thiết kế điều kiện trả bản **FULL**, **REDUCED**, **STALE** hoặc **UNAVAILABLE** mà không nhập nhằng lỗi với kết quả rỗng hợp lệ.
3. Chọn HTTP status, JSON metadata, header, cache policy và OpenAPI 3.1 đúng hợp đồng.
4. Đặt timeout, circuit breaker, bulkhead, retry budget và feature flag tại đúng dependency.
5. Viết ví dụ Java/Spring giữ authentication/authorization và core data nhất quán khi dependency tùy chọn bị lỗi.
6. Kiểm thử hành vi degraded, dữ liệu cũ, race, mất quyền, cache isolation và hiệu ứng lên UI/client.

**Luận điểm chính:** chỉ trả response rút gọn nếu **các bất biến bắt buộc vẫn đúng**, các phần bị thiếu đã được đánh dấu theo hợp đồng, và client được thiết kế để dùng phiên bản rút gọn an toàn.

## 2. Phân biệt graceful degradation, fallback và fail-closed

| Khái niệm | Nghĩa trong REST API | Ví dụ |
| --- | --- | --- |
| **FULL** | Mọi phần bắt buộc và tùy chọn trong hợp đồng đã có dữ liệu/hành vi hoàn chỉnh | Product + ratings + recommendations |
| **REDUCED** | Giữ dữ liệu bắt buộc, bỏ một số khả năng tùy chọn có thông báo | Product + giá đúng, không có recommendations |
| **STALE** | Dùng bản đã lưu trước đó theo chính sách độ cũ cho phép, có dấu thời gian nguồn | Ratings cache 2 phút trước, trong giới hạn 5 phút |
| **FALLBACK** | Cơ chế thay thế một nguồn lỗi bằng dữ liệu/hành vi dự phòng được định nghĩa | Ratings từ cache thay vì service hiện tại |
| **FAIL CLOSED** | Khi không xác định được điều kiện an toàn/bắt buộc thì **từ chối** thay vì giả định được phép | Không xác định quyền truy cập → không trả product |
| **UNAVAILABLE** | Không thể đáp ứng mức tối thiểu hợp đồng; trả lỗi phù hợp | Product Core không sẵn sàng → 503 |
| **PARTIAL SUCCESS** | Một nhóm thao tác độc lập có kết quả khác nhau | Batch cập nhật từng item; không đồng nghĩa với REDUCED representation |

**Điểm tinh tế:** có thể có response vừa **REDUCED** (thiếu recommendations) vừa có ratings **STALE**. Nên mô hình hóa **completeness** và **freshness** độc lập; không nhét mọi tình huống vào một boolean duy nhất.

Đối với dữ liệu tùy chọn, **mảng trống hợp lệ** khác **không tải được mảng**:

~~~json
{"recommendations":[]}
~~~

Có thể có nghĩa hệ thống đã tính toán và tìm thấy **0** gợi ý. Nếu dependency đang down, trả cùng một mảng trống **không có dấu hiệu** sẽ khiến client hiểu sai rằng phép tính đã hoàn tất. Cần ghi rõ omitted/unavailable trong payload hoặc trạng thái riêng của section.

## 3. Quyết định cái gì được suy giảm theo ngữ nghĩa nghiệp vụ

Không thể gắn nhãn một dependency là "optional" chung cho mọi endpoint. **Cùng một dữ liệu có thể là tùy chọn ở trang chi tiết, nhưng bắt buộc trong thao tác khác.**

| Thao tác | Bắt buộc | Có thể rút gọn? | Khi thiếu phần bắt buộc |
| --- | --- | --- | --- |
| **GET /products/{id}/overview** | ID, tên, giá/currency được phép công bố, quyền xem | Ratings, recommendations | 503 hoặc lỗi xác thực/quyền/tồn tại đúng nguyên nhân |
| **GET /products/{id}/recommendations** | Kết quả recommendation là nội dung chính | Không giả mảng rỗng vì service down | 503 hoặc status được contract quy định |
| **POST /orders** | Giá/thuế/tồn kho xác nhận, idempotency, quyền đặt, payment rules | Có thể bỏ theo dõi/phân tích không thiết yếu | Không tạo order bằng giá/tồn kho giả |
| **GET /orders/{id}** | Owner/tenant ACL và trạng thái đơn hàng đúng | Hình minh họa/gợi ý kèm theo nếu có contract | 401/403/404 hoặc 503; không bypass ACL |
| **GET /dashboard** | Scope/tenant và metrics cốt lõi được định nghĩa | Charts phụ nếu ghi rõ thiếu | 200 reduced hoặc lỗi theo yêu cầu mức đầy đủ |
| **POST /refunds** | Quyền hoàn tiền, số tiền, trạng thái giao dịch | Telemetry/marketing events không ảnh hưởng commit | Fail-closed, không giả lập thành công |

**Nguyên tắc phân loại:**

1. **Cốt lõi** là dữ liệu thiếu sẽ làm response sai lời hứa nghiệp vụ, sai pháp lý, sai tài chính hoặc gây quyết định nguy hiểm.
2. **Tùy chọn** chỉ khi omission không làm client hiểu sai trạng thái tài nguyên và đã được document.
3. **Stale** chỉ khi có ngưỡng độ cũ, xuất xứ, kiểm quyền đọc hiện tại và cơ chế invalidate phù hợp.
4. **Security-critical** (JWT, tenant scope, ACL, consent, policy rules, kiểm soát giá/thanh toán) **không được thay bằng "allow" khi lỗi**.
5. **Write side effects** cần xem tính nhất quán và idempotency riêng; degraded read không tự cho phép degraded write.

### 3.1. Ma trận quyết định trước khi bật fallback

| Câu hỏi | Nếu "không" |
| --- | --- |
| Mọi dữ liệu **bắt buộc** đã được lấy và validate? | Không trả representation rút gọn; lỗi |
| Authentication, tenant và object-level authorization còn hợp lệ? | Trả 401/403/404, không fallback |
| Phần bị thiếu thực sự nằm trong **allowlist optional** của operation? | Không được bỏ phần đó |
| Client/hợp đồng có định nghĩa cách hiển thị/tiêu thụ khi thiếu? | Không trả REDUCED âm thầm |
| Nếu dùng cache, dữ liệu cũ trong giới hạn **staleness + scope**? | Không dùng cache đó |
| Đã giới hạn timeout, tải chờ và fallback cascade? | Fail fast hoặc bảo vệ tài nguyên trước khi mở |
| Có metric, alert, kill switch và test khả năng trở lại FULL? | Chưa nên bật trong production |

**Degrade là chính sách sản phẩm có điều kiện**, không phải một đoạn catch Exception nhằm giấu lỗi lập trình.

## 4. Thiết kế contract FULL và REDUCED rõ ràng

Tài nguyên minh họa có core bắt buộc:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "name": "Bàn phím cơ",
  "priceMinor": 2590000,
  "currency": "VND"
}
~~~

Khi đủ các nguồn, response:

~~~http
GET /api/v1/products/11111111-1111-4111-8111-111111111111/overview HTTP/1.1
Accept: application/json
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "product": {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "Bàn phím cơ",
    "priceMinor": 2590000,
    "currency": "VND"
  },
  "ratings": {
    "average": 4.6,
    "count": 123,
    "asOf": "2026-11-18T08:00:00Z"
  },
  "recommendations": [{"id": "SKU-123"}],
  "quality": {
    "completeness": "FULL",
    "omittedSections": [],
    "staleSections": []
  }
}
~~~

Nếu recommendation service timeout nhưng core/ratings hợp lệ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "product": {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "Bàn phím cơ",
    "priceMinor": 2590000,
    "currency": "VND"
  },
  "ratings": {
    "average": 4.6,
    "count": 123,
    "asOf": "2026-11-18T08:00:00Z"
  },
  "recommendations": null,
  "quality": {
    "completeness": "REDUCED",
    "omittedSections": ["recommendations"],
    "staleSections": [],
    "reasonCodes": ["OPTIONAL_DEPENDENCY_UNAVAILABLE"]
  }
}
~~~

**Ý nghĩa:**

- **200 OK** hợp lý vì representation đáp ứng **mức tối thiểu** của endpoint và contract cho phép omission tùy chọn.
- **recommendations: null + omittedSections** diễn tả không có kết quả vì nguồn tùy chọn không khả dụng, khác **[]** khi đã tính toán nhưng không có gợi ý.
- **reasonCodes** là mã ổn định, không tiết lộ hostname, stack trace, topology, quyền/tenant khác.
- **ratings.asOf** nói thời điểm nguồn đánh giá, không phải thời điểm response được tạo; nếu ratings cũ hơn ngưỡng theo policy thì hoặc đánh dấu STALE hợp lệ, hoặc omit.
- Client phải được lập trình để hiển thị "Tạm ẩn gợi ý" hoặc bỏ widget, **không** biến null thành "không có đề xuất" như dữ kiện nghiệp vụ.

**Không loại bỏ dữ liệu bắt buộc khỏi JSON và vẫn khai báo FULL.** Nếu product price không lấy được, cần trả error, không để priceMinor = 0 hoặc currency = null để khách hàng hiểu nhầm miễn phí.

### 4.1. Chế độ tiêu thụ linh hoạt và yêu cầu đầy đủ

Một API có thể định nghĩa:

~~~http
GET /api/v1/products/{id}/overview?completeness=flexible
GET /api/v1/products/{id}/overview?completeness=full
~~~

- **flexible**: cho phép thiếu sections nằm trong allowlist; server trả FULL hoặc REDUCED và chỉ rõ tình trạng.
- **full**: client cần toàn bộ sections theo contract; nếu không đáp ứng thì **không trả 200 reduced**, mà trả 503/504 hoặc status được quy định, kèm Problem Details.
- **Giá trị không hợp lệ**: 400 với mã lỗi phù hợp.
- Query parameter làm các variant có URI khác nhau; nếu dùng header cho chế độ, phải khai báo **Vary** đúng khi response cacheable.

Có thể dùng **Prefer: return=minimal** của RFC 7240 nếu mục tiêu là yêu cầu representation ngắn gọn, và **Preference-Applied: return=minimal** khi chấp nhận. Tuy nhiên **return=minimal không có nghĩa chuẩn rằng server được phép bỏ dữ liệu tùy chọn vì dependency lỗi**. Hai khái niệm tối ưu payload và suy giảm do lỗi cần được ghi rõ trong contract riêng; không suy diễn preference thay nghĩa FULL/REDUCED.

## 5. HTTP status: không dùng 206 cho JSON thiếu một số section

| Tình huống | HTTP status | Lý do |
| --- | --- | --- |
| Core chính xác, optional thiếu được phép | **200 OK** | Representation hợp lệ nhưng metadata thông báo REDUCED |
| Core chính xác, optional từ cache trong policy | **200 OK** | Có thể là FULL + staleSections hoặc REDUCED tùy section thiếu |
| Core không khả dụng, không có fallback được duyệt | **503 Service Unavailable** | Không đáp ứng mức tối thiểu |
| Request qua gateway chờ upstream quá hạn | **504 Gateway Timeout** | Phù hợp khi gateway thực sự timeout |
| Client yêu cầu completeness=full nhưng optional lỗi | **503** theo contract | Không âm thầm trả REDUCED cho client yêu cầu FULL |
| Không có tài nguyên trong scope | **404 Not Found** | Không biến mất quyền/tồn tại thành degraded |
| Thiếu JWT/permission | **401/403** (hoặc 404 che tồn tại) | Fail-closed |
| Dữ liệu input không hợp lệ | **400/422** theo contract | Không dùng fallback để che input sai |
| Job async được tiếp nhận | **202 Accepted** | Chưa có representation cuối |
| Batch item có kết quả riêng | **200** với per-item outcomes | Không dùng mã response tùy tiện cho aggregation |

**HTTP 206 Partial Content dành cho một phần representation được truyền theo semantics HTTP Range**, cùng các quy tắc như **Content-Range** hoặc multipart/byteranges; **không dành cho JSON bị thiếu trường recommendation hoặc ratings**. Gắn 206 vào response rút gọn có thể phá range/cache/client semantics.

**207 Multi-Status** đến từ WebDAV và không phải mã chuẩn chung cho việc trả JSON overview thiếu tính năng. **202 Accepted** chỉ phù hợp khi request đã nhận để xử lý bất đồng bộ, không thay 200 REDUCED.

Nếu API trả lỗi vì không thể cung cấp core:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store
Retry-After: 5

{
  "type": "https://api.example.test/problems/representation-unavailable",
  "title": "Required product data unavailable",
  "status": 503,
  "code": "CORE_DATA_UNAVAILABLE"
}
~~~

**Retry-After** chỉ nên xuất hiện khi có chỉ dẫn retry có cơ sở, không hứa thời gian phục hồi chính xác. 503 không phải lúc nào cũng cần Retry-After. Bên cạnh đó, **lỗi authn/authz phải được kiểm trước khi gọi optional dependencies**, tránh chuyển 403 thành 200 kèm dữ liệu rút gọn.

## 6. Freshness: khi nào được dùng dữ liệu cũ?

Fallback thường gặp là **stale-while-error ở tầng application**. Không đồng nghĩa với **stale-if-error** của HTTP cache (RFC 5861) hay cơ chế CDN: mỗi tầng có điều kiện, cache key và phạm vi xác thực khác nhau.

Ví dụ một chính sách **minh họa**, cần được chủ sản phẩm xác nhận:

| Data | Stale tối đa | Quy tắc |
| --- | ---: | --- |
| Tên/hình ảnh catalog công khai | 5 phút tùy use case | Chỉ nếu đúng tenant/visibility và không bị gỡ |
| Điểm đánh giá | 10 phút | asOf rõ; không giả rating 0 |
| Recommendations cá nhân | 2 phút | Chỉ cùng user/tenant/consent/policy version; cân nhắc bỏ hẳn |
| Giá hiện hành | **Không stale** trong operation yêu cầu giá tức thời | Lỗi nếu không có nguồn được ủy quyền |
| Tồn kho để đặt hàng | **Không stale** | Không xác nhận giữ hàng dựa trên snapshot cũ |
| Quyền truy cập/consent/tenant scope | **Không stale theo kiểu allow-all** | Kiểm quyền hiện tại, fail-closed |

Khi dùng cache:

1. Key theo **tenant, resource, user/permission/consent context, projection/version** và các tham số ảnh hưởng; không dùng chỉ productId khi có dữ liệu riêng tư.
2. Chỉ đọc cached value **sau khi xác thực và phân quyền hiện tại**, không dựa vào quyền lúc cache được tạo.
3. Xác nhận **age** không vượt mức cho phép, có timestamp từ nguồn đáng tin; nếu timestamp mất thì không được tự coi fresh.
4. Phân biệt dữ liệu **stale nhưng được phép dùng** với **missing, corrupted, revoked hoặc invalid**.
5. Trả **asOf**/staleSections, không giả giá trị mới.
6. Kiểm invalidate khi xóa sản phẩm, rút consent, thay ACL, đổi giá hoặc chuyển tenant.

Khi cache data đã được ủy quyền hết hạn, **hệ thống phải bỏ section hoặc trả lỗi**, không kéo dài TTL vô hạn chỉ để tăng availability. Các response riêng tư có thể dùng **Cache-Control: private, no-store** và vẫn dùng application-side cache có kiểm soát; HTTP cache directive không tự mô tả policy Redis nội bộ.

## 7. Thứ tự quyết định degrade: xác thực trước, fallback sau

~~~mermaid
flowchart TD
    R[Request GET overview] --> V[Validate input + authenticate]
    V --> A{Authorize tenant + product?}
    A -- Không --> E[401 / 403 / 404]
    A -- Có --> C[Load required core within deadline]
    C --> D{Core valid, current and complete?}
    D -- Không --> U[503 or permitted error]
    D -- Có --> O[Fetch optional sources with budgets]
    O --> F{Every optional source successful?}
    F -- Có --> FULL[200 FULL]
    F -- Không --> P{Optional failure and fallback policy allowed?}
    P -- Có --> S[Use bounded stale or omit optional]
    S --> RED[200 REDUCED / freshness metadata]
    P -- Không --> ERR[503 when full required, or policy error]
~~~

**Không catch tất cả exception rồi trả 200**. Các lỗi có thể giảm cấp phải nằm trong **allowlist** (ví dụ timeout/503 tạm thời của recommendation service). Các lỗi **401/403**, dữ liệu vi phạm contract/schema, dữ liệu tenant khác, lỗi kiểm tính toàn vẹn và exception lập trình **không phải** tín hiệu hợp lệ để thay bằng fallback.

### 7.1. Định nghĩa minimum viable representation

Trước khi triển khai, ghi một **minimum data contract** cho từng operation:

- Danh sách **required fields và invariants** (giá, tiền tệ, visibility, identifier).
- Các **optional sections** được phép vắng và cách thể hiện omission/empty/stale.
- **Max age**, ownership/consent và tính nhất quán với dữ liệu chính.
- Chính sách HTTP khi client yêu cầu **full**.
- Mốc thời gian tối đa cho core, optional, tổng operation và retry budget.
- Quyền lưu/cache/trace data và cách rollback chính sách bằng feature flag.

Một endpoint không có minimum data contract rõ ràng **không nên tự degrade** chỉ vì dependency đang down.

## 8. Java/Spring: compose core chính xác và optional có giới hạn

Ví dụ skeleton dùng **Spring Boot 3 / Java 17+**. Mục tiêu là làm rõ boundary và policy; repository/gateway/exception là interface/domain class cần cài đặt trong dự án thực.

### 8.1. DTO phân biệt dữ liệu thật, rút gọn và stale

~~~java
public record ProductCore(
        UUID id, String name, long priceMinor, String currency) {}

public record Ratings(
        Double average, int count, Instant asOf) {}

public record Recommendation(
        UUID id, String label) {}

public record RepresentationQuality(
        String completeness,
        List<String> omittedSections,
        List<String> staleSections,
        List<String> reasonCodes) {}

public record ProductOverview(
        ProductCore product,
        Ratings ratings,
        List<Recommendation> recommendations,
        RepresentationQuality quality) {}
~~~

Quy tắc DTO: **product** luôn có mặt; **ratings/recommendations** có thể là null **chỉ khi** mục tương ứng có trong omittedSections. Danh sách recommendation rỗng **[]** là kết quả tính toán hợp lệ, không có nghĩa dependency lỗi. **Ratings.average = null** với count 0 có thể biểu diễn chưa có đánh giá thật, khác ratings toàn phần bị bỏ.

Cần thêm **JSON Schema/Bean Validation** và integration tests để đảm bảo các bất biến này không bị phá khi nâng phiên bản serialization.

### 8.2. Service phân loại lỗi trước khi fallback

~~~java
@Service
public class ProductOverviewService {
    private final AuthorizedProductReader productReader;
    private final RatingsGateway ratingsGateway;
    private final RecommendationGateway recommendationGateway;

    public ProductOverviewService(
            AuthorizedProductReader productReader,
            RatingsGateway ratingsGateway,
            RecommendationGateway recommendationGateway) {
        this.productReader = productReader;
        this.ratingsGateway = ratingsGateway;
        this.recommendationGateway = recommendationGateway;
    }

    public ProductOverview load(
            Caller caller, UUID productId, boolean requireFull) {

        // Đây là bước BẮT BUỘC: kiểm quyền và đọc core đã scope.
        // Bất kỳ lỗi auth/core nào đều thoát ra, KHÔNG fallback.
        ProductCore core =
            productReader.requireCurrentVisible(caller, productId);

        List<String> omitted = new ArrayList<>();
        List<String> reasons = new ArrayList<>();
        Ratings ratings = null;
        List<Recommendation> recommendations = null;

        try {
            ratings = ratingsGateway.fetch(caller, productId);
        } catch (OptionalDependencyUnavailableException ex) {
            omitted.add("ratings");
            reasons.add("OPTIONAL_DEPENDENCY_UNAVAILABLE");
        }

        try {
            recommendations = recommendationGateway.fetch(
                caller, productId);
        } catch (OptionalDependencyUnavailableException ex) {
            omitted.add("recommendations");
            if (!reasons.contains("OPTIONAL_DEPENDENCY_UNAVAILABLE")) {
                reasons.add("OPTIONAL_DEPENDENCY_UNAVAILABLE");
            }
        }

        if (requireFull && !omitted.isEmpty()) {
            throw new RequiredRepresentationUnavailableException();
        }

        return new ProductOverview(
            core, ratings, recommendations,
            new RepresentationQuality(
                omitted.isEmpty() ? "FULL" : "REDUCED",
                List.copyOf(omitted),
                List.of(),
                List.copyOf(reasons)));
    }
}
~~~

**Hợp đồng cần cài đặt:**

- **AuthorizedProductReader.requireCurrentVisible** phải lấy core **sau xác thực/kiểm tenant/ACL** với nguồn hiện hành, trả 401/403/404 theo privacy policy. Không lấy core từ một cache không scope, không tự bỏ qua 404.
- **RatingsGateway/RecommendationGateway** phải tự giới hạn timeout, connection pool và fallback budget; đối với dữ liệu riêng tư, gửi delegated context được xác minh hoặc gọi service theo policy, không tin userId ở body.
- Chỉ catch **OptionalDependencyUnavailableException** do gateway **phân loại chính xác** từ timeout, circuit open hoặc 503/429 transient được chính sách cho phép. **Không catch Exception** rồi trả 200: JSON schema lỗi, authn/authz 401/403, dữ liệu sai tenant, lỗi lập trình và vi phạm integrity phải được quan sát và xử lý riêng.
- Nếu policy cho phép cached ratings, gateway có thể trả **Ratings** cùng metadata freshness. Service cần đánh dấu **staleSections** (không phải luôn trả List.of() như skeleton không-cache này).
- Dạng code tuần tự dễ hiểu nhưng tăng latency khi cả hai optional services chậm; có thể chạy song song có **deadline chung**, cancellation và cap concurrency khi đã có tests.
- Giá, tiền tệ và quyền xem phải đi theo **cùng một consistency contract**. Nếu Product Core trả dữ liệu không thể xác minh, không giả priceMinor = 0.

### 8.3. Controller và HTTP response

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductOverviewController {
    private final ProductOverviewService service;
    private final CallerResolver callerResolver;

    @GetMapping("/{id}/overview")
    public ResponseEntity<ProductOverview> getOverview(
            @PathVariable UUID id,
            @RequestParam(defaultValue = "flexible")
                String completeness,
            Authentication authentication) {

        boolean requireFull;
        if ("full".equals(completeness)) {
            requireFull = true;
        } else if ("flexible".equals(completeness)) {
            requireFull = false;
        } else {
            throw new InvalidCompletenessModeException();
        }

        Caller caller = callerResolver.require(authentication);
        ProductOverview result =
            service.load(caller, id, requireFull);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
    }
}
~~~

**Lớp Caller, CallerResolver và các custom exceptions được định nghĩa ở ứng dụng thật**. SecurityFilterChain cần xác thực Bearer JWT trước khi controller; method/object permission còn được kiểm ở productReader. Nếu request thiếu token, không lấy optional data hoặc trả cached product để biến lỗi thành 200.

Để client phân biệt lỗi, triển khai **@RestControllerAdvice** ánh xạ RequiredRepresentationUnavailableException thành **503 Problem Details**; do request full yêu cầu đầy đủ, không trả response REDUCED cùng status 200. Không dùng một catch chung khiến cả **AccessDeniedException** biến thành 503.

## 9. Timeout, circuit breaker, bulkhead và retry đặt ở đâu?

Một fallback chỉ có ích nếu failure được **phát hiện có giới hạn thời gian và tài nguyên**. Ví dụ tổng endpoint có budget **700 ms**, trong đó core cần hoàn tất trong khoảng 350 ms, optional ratings và recommendations cùng chạy trong **cửa sổ tối đa 200–300 ms** nếu song song. Đây là giả định để load test, không phải preset production.

| Cơ chế | Tác dụng | Không tự làm được |
| --- | --- | --- |
| **Timeout/deadline** | Không chờ upstream tùy chọn vô hạn | Không rollback transaction đã commit ở upstream |
| **Circuit breaker** | Ngừng gọi tạm thời nguồn đang fail theo ngưỡng | Không chứng minh dữ liệu cache hợp lệ hoặc caller có quyền |
| **Bulkhead** | Chặn optional dependency dùng hết thread/connection | Không giải quyết consistency của core |
| **Bounded queue/pool acquisition timeout** | Giảm overload và thời gian xếp hàng | Không tự thay retry budget |
| **Retry + jitter** | Có thể phục hồi lỗi ngắn hạn | Có nguy cơ nhân tải khi upstream down |
| **Feature flag/kill switch** | Vô hiệu một widget/adapter không thiết yếu | Không được bỏ các security checks |
| **Fallback cache** | Cung cấp dữ liệu cũ theo policy | Không bảo đảm dữ liệu vẫn đúng quyền/giá |

**Thứ tự tư duy:** validate/auth → core bắt buộc → kiểm deadline còn lại → gọi optional qua bulkhead/timeout/circuit → nếu optional failure được phân loại, dùng fallback đã duyệt → compose representation/metadata → áp cache/HTTP contract. Chi tiết thứ tự thực thi trong framework thay đổi theo decorator, nhưng các bất biến trên không được thay.

### 9.1. Gọi WebClient cho recommendation với timeout mục tiêu

~~~java
public Mono<List<Recommendation>> getRecommendations(UUID productId) {
    return webClient.get()
        .uri("/internal/products/{id}/recommendations", productId)
        .retrieve()
        .bodyToFlux(Recommendation.class)
        .collectList()
        .timeout(Duration.ofMillis(250));
}
~~~

Ví dụ reactive này **chỉ giới thiệu timeout**, chưa bao gồm authentication service-to-service, bulkhead, mapping exception hay limit body. Khi timeout, Mono phát lỗi, **không đồng nghĩa server đã hủy nghiệp vụ**. Nếu dùng Spring MVC và muốn block, phải thực hiện ở boundary có thread budget được đo; đừng block event loop. Khi dùng Resilience4j, đặt cấu hình **instance riêng cho từng optional dependency**, không để recommendation lỗi kéo theo circuit breaker dùng chung cho Product Core.

**Không được viết onErrorResume(error -> Mono.just(Collections.emptyList())) vô điều kiện**, vì nó biến timeout, 401, 403, 500, lỗi JSON và thiếu permission thành cùng kết quả rỗng. Thay vào đó, chuyển những lỗi **transient** được chấp nhận thành một kiểu **OptionalDependencyUnavailableException**, rồi để service đánh dấu omitted.

### 9.2. Chọn retry bảo vệ upstream

- GET tới optional read service thường có thể retry **tối đa một lần** nếu lỗi transient, còn deadline và bulkhead có capacity. Dùng backoff/jitter, xét **Retry-After** cho 429/503 khi phù hợp.
- Không retry 400/401/403 hoặc dữ liệu sai schema như thể kết nối tạm thời; đây là điều cần điều tra và không nên bị che.
- Có nhiều tầng retry (gateway, service client, SDK) dễ tạo **retry storm**. Giảm số attempts khi circuit open; đặt retry budget tính cả **queue wait + timeouts + backoff**.
- Đối với POST tạo order, tuyệt đối không dùng fallback "trả 201 từ queue" nếu chưa có hợp đồng async/idempotency đúng; 202 Accepted chỉ được sử dụng khi công việc đã thật sự được nhận để xử lý sau.

### 9.3. Fallback không nên kéo theo một dependency lớn hơn

Nếu Recommendation lỗi mà fallback lập tức gọi Search rồi gọi Analytics rồi gọi User Profile, degradation lại có thể tạo **cascade dependency** và failure amplification. Fallback nên **rẻ hơn, có giới hạn, không phát sinh side effect**, ví dụ omit widget hoặc trả bản cache đã kiểm scope và TTL. Khi fallback cũng lỗi, bỏ section theo policy, không tạo vòng lặp.

## 10. Chế độ rút gọn được quyết định bởi trạng thái hay yêu cầu client?

Có hai tác nhân:

**Degrade chủ động (load shedding):** hệ thống đo upstream p95, queue depth, saturation/circuit state và quyết định **bỏ optional work** trước khi nó làm nghẽn core. Không cần chờ một timeout thực tế cho từng request. Phải có ngưỡng, hysteresis/cooldown và cơ chế phục hồi có kiểm soát, tránh trạng thái FULL ↔ REDUCED dao động từng giây.

**Degrade phản ứng:** một optional call đã gặp timeout, 503 hoặc circuit open và service bỏ section hoặc dùng cache đúng policy. Tất cả failures phải có metric riêng, không biến thành thành công giả không quan sát được.

**Yêu cầu client** có thể giới hạn mức cho phép:
- Chế độ flexible: server được phép trả reduced khi thiếu optional.
- Chế độ full: nếu optional thiếu thì **503** theo contract, không trả 200 dù core đúng.
- Client có thể chủ động chỉ muốn ít section để tiết kiệm dữ liệu (**projection/minimal**) ngay cả khi hệ thống khỏe. Đừng nhầm **client không yêu cầu** với **server không thể cung cấp**.
- Nếu client chưa hỗ trợ reduced, migration an toàn có thể dùng **API version, media type profile hoặc opt-in**; đừng đột ngột làm required fields thành optional.

### 10.1. Đánh dấu metadata không làm rò topology

Một số thông tin hữu ích cho frontend/telemetry:

| Trường | Ví dụ | Quy tắc |
| --- | --- | --- |
| quality.completeness | FULL / REDUCED | Mô tả representation hiện tại |
| quality.omittedSections | ["recommendations"] | Enum/allowlist đã công bố |
| quality.staleSections | ["ratings"] | Chỉ khi dữ liệu cũ còn được policy chấp nhận |
| ratings.asOf | timestamp ISO-8601 | Thời điểm dữ liệu nguồn |
| quality.reasonCodes | OPTIONAL_DEPENDENCY_UNAVAILABLE | Mã ổn định, không lộ nội bộ |
| X-Request-Id | Request ID dùng audit/trace | Không phải secret hay authorization |
| Retry-After | Khi trả 503/429 nếu có cơ sở | Không tạo kỳ vọng phục hồi chắc chắn |

Không trả **tên cluster, IP backend, chi tiết circuit breaker, userId của tài khoản khác hoặc path S3 nội bộ**. Frontend cần biết phần nào thiếu, không cần cấu trúc hạ tầng.

## 11. Bảo mật trong chế độ degraded

Lỗ hổng nguy hiểm nhất là **fail-open khi security dependency down**. Ví dụ:

~~~java
// SAI: lỗi authorization service không có nghĩa cho phép.
try {
    policy.requireCanRead(caller, productId);
} catch (Exception ignored) {
    return cachedProduct; // Có thể rò dữ liệu tenant khác.
}
~~~

Bất biến an ninh:

1. **JWT/session được xác minh**, token không được phép bỏ qua vì gateway/AuthZ quá tải.
2. **Tenant + BOLA/BOPLA** được áp trên core và mọi optional source; cache không được trả dữ liệu của caller/tenant khác.
3. Nếu consent cá nhân hóa bị thu hồi, **recommendations cache không được tiếp tục phục vụ** chỉ vì gateway lỗi.
4. **Schema rút gọn không thêm quyền**: data classification vẫn áp dụng cho FULL và REDUCED.
5. **Feature flag giảm tải** chỉ tắt widget/tác vụ tùy chọn, không tắt validation, audit bảo mật, rate limit hay fraud checks bắt buộc.
6. Một fallback dùng **public recommendations** không được làm lộ dữ liệu cá nhân; phải kiểm nguồn/publicness và policy.
7. API dùng **cookie** vẫn cần CSRF protections đối với unsafe methods; CORS không tạo authorization.
8. Error/telemetry không echo access token, hồ sơ người dùng khác, số tiền nhạy cảm hoặc raw request.

### 11.1. Không dùng HTTP cache để truyền representation sai quyền

- Dữ liệu riêng tư và multi-tenant: **Cache-Control: private, no-store** khi dữ liệu nhạy cảm.
- Nếu cache được dùng cho data public, cache key phải phân biệt **projection, mode (full/flexible), locale, authorization scope nếu có, freshness version**.
- Không để CDN cache một REDUCED response theo URL rồi tiếp tục trả bản thiếu phần cho mọi user sau khi upstream phục hồi, nếu không có TTL/invalidation phù hợp.
- **ETag** cần mô tả đúng variant representation và thời điểm xuất bản. Một ETag của FULL không được tái dùng cho REDUCED có body khác.
- **304 Not Modified** chỉ được dùng khi validator cho representation được chọn thực sự match và vẫn đáp ứng authorization/cache semantics. Không dùng 304 để che không đủ quyền.
- Không trả **206 Partial Content** cho JSON thiếu sections vì có thể làm hỏng range caches.

## 12. Observability, SLO và các ngưỡng kích hoạt

Trả 200 REDUCED có thể giúp tổng tỷ lệ HTTP 2xx tăng, nhưng người dùng vẫn mất chức năng. Phải đo **availability của core** và **availability của experience FULL** riêng.

| Metric | Ý nghĩa |
| --- | --- |
| **response.full.count / reduced.count / error.count** | Tỷ lệ từng chất lượng representation |
| **degradation.reason** | Timeout, circuit open, bulkhead reject, stale fallback |
| **omittedSections per endpoint** | Tính năng nào đang mất |
| **optional dependency latency/error/timeout** | Nguồn lỗi và xu hướng |
| **core latency / total latency p95/p99** | Có bảo vệ core thực sự không |
| **stale value age p95/max** | Có vượt staleness policy không |
| **bulkhead active/queue/rejected** | Hàng chờ có được giới hạn không |
| **circuit state transitions** | Có flapping hay outage kéo dài không |
| **client mode full/flexible** | Đáp ứng hợp đồng từng nhóm caller |
| **auth denial rate và cache isolation failures** | Bảo mật không bị suy giảm |

Metric labels theo **route template, optional section, reason code, environment**, không theo productId, userId, token hoặc raw URL có high cardinality/PII.

**Ví dụ trigger vận hành minh họa:**

- Nếu Recommendation p95 tăng mạnh hoặc error rate vượt ngưỡng trong một khoảng đủ dài, bật **disableRecommendations** cho nhóm traffic cụ thể.
- Tiếp tục phục vụ core, quan sát tỷ lệ FULL/REDUCED và ghi sự kiện bật flag có người chịu trách nhiệm.
- Khi upstream ổn định trong nhiều cửa sổ liên tiếp, phục hồi từng phần qua canary; có hysteresis để không bật/tắt liên tục.
- Nếu **core error/latency** tăng hoặc reduced rate vượt ngưỡng product/SLO, alert và cân nhắc hạn chế traffic, không cố trả 200 bằng mọi giá.

**Không cộng response REDUCED vào chỉ số "toàn bộ tính năng hoạt động"**. Báo cáo tách **reliability của tính năng cốt lõi**, **full-fidelity rate** và **degraded experience rate** để tránh che outage.

## 13. OpenAPI 3.1 cho FULL và REDUCED

Contract phải thể hiện **core luôn có**, các section tùy chọn có thể **null khi bị omit**, và **quality metadata bắt buộc**. Việc đổi field đã từng required thành nullable có thể làm hỏng client cũ; cần version hoặc opt-in khi thay đổi hợp đồng.

~~~yaml
openapi: 3.1.0
info:
  title: Product Overview API
  version: 1.0.0
paths:
  /api/v1/products/{id}/overview:
    get:
      operationId: getProductOverview
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
        - in: query
          name: completeness
          schema: { type: string, enum: [flexible, full], default: flexible }
      responses:
        '200':
          description: FULL hoặc REDUCED theo quality.completeness
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Overview' }
        '400': { description: Input không hợp lệ }
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '404': { description: Product không được công bố }
        '503':
          description: Core lỗi hoặc không đáp ứng chế độ full
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    Core:
      type: object
      required: [id, name, priceMinor, currency]
      properties:
        id: { type: string, format: uuid }
        name: { type: string, minLength: 1 }
        priceMinor: { type: integer, format: int64, minimum: 0 }
        currency: { type: string, minLength: 3, maxLength: 3 }
    Ratings:
      type: object
      required: [count, asOf]
      properties:
        average: { type: [number, 'null'], minimum: 0, maximum: 5 }
        count: { type: integer, minimum: 0 }
        asOf: { type: string, format: date-time }
    Quality:
      type: object
      required: [completeness, omittedSections, staleSections]
      properties:
        completeness: { type: string, enum: [FULL, REDUCED] }
        omittedSections:
          type: array
          uniqueItems: true
          items: { type: string, enum: [ratings, recommendations] }
        staleSections:
          type: array
          uniqueItems: true
          items: { type: string, enum: [ratings, recommendations] }
        reasonCodes:
          type: array
          items: { type: string }
    Overview:
      type: object
      required: [product, ratings, recommendations, quality]
      properties:
        product: { $ref: '#/components/schemas/Core' }
        ratings:
          anyOf:
            - $ref: '#/components/schemas/Ratings'
            - type: 'null'
        recommendations:
          anyOf:
            - type: array
              items:
                type: object
                required: [id]
                properties:
                  id: { type: string, format: uuid }
            - type: 'null'
        quality: { $ref: '#/components/schemas/Quality' }
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string }
        title: { type: string }
        status: { type: integer }
        code: { type: string }
~~~

**Lưu ý:** Schema này kiểm kiểu dữ liệu nhưng chưa tự enforce bất biến **section null phải xuất hiện trong omittedSections**; cần thêm validation/contract tests. **recommendations=[]** là kết quả đã tính hợp lệ, không phải failure. API không có **206** vì không dùng HTTP Range. Trong production, mô tả thêm Cache-Control/ETag, JSON examples và security scopes thực.

## 14. Kiểm thử degraded mode và khả năng phục hồi

Không chỉ mock một dependency trả null. Cần kiểm **timeout thật, circuit open, stale cache, authorization, optimistic consistency** và HTTP response của gateway/controller.

### 14.1. Unit test chính sách với JUnit/Mockito

~~~java
@Test
void recommendationTimeoutKeepsCoreAndMarksReduced() {
    UUID id = UUID.randomUUID();
    Caller caller = validCaller();
    ProductCore core = new ProductCore(id, "Bàn phím", 2590000, "VND");

    when(productReader.requireCurrentVisible(caller, id))
        .thenReturn(core);
    when(ratingsGateway.fetch(caller, id))
        .thenReturn(new Ratings(4.6, 123, Instant.now()));
    when(recommendationGateway.fetch(caller, id))
        .thenThrow(new OptionalDependencyUnavailableException());

    ProductOverview result = service.load(caller, id, false);

    assertEquals(core, result.product());
    assertEquals("REDUCED", result.quality().completeness());
    assertNull(result.recommendations());
    assertTrue(result.quality().omittedSections()
        .contains("recommendations"));
}
~~~

Đây là **test skeleton**: cần khai báo fixtures, imports và constructors. Dùng WireMock/MockWebServer để delay response 1 giây khi optional budget 250 ms; kiểm service **không chờ toàn bộ 1 giây**. Dùng fault proxy cho connect stalls và bulkhead saturation; MockMvc với SecurityFilterChain thật để test authn/authz và status.

### 14.2. Ma trận kiểm thử tối thiểu

| ID | Kịch bản | Kết quả |
| --- | --- | --- |
| R01 | Tất cả dependencies khỏe | **200 FULL** |
| R02 | Recommendation tính ra danh sách rỗng | FULL, recommendations **[]**, không omitted |
| R03 | Recommendation timeout | **200 REDUCED**, null, omittedSections đúng |
| R04 | Ratings lỗi, cache trong TTL và đúng scope | asOf/staleSections đúng |
| R05 | Cache vượt TTL, tenant/consent đã đổi | Không dùng cache trái quyền |
| R06 | Product Core không sẵn sàng | **503**, không giả giá 0 |
| R07 | completeness=full, optional timeout | 503, không trả 200 REDUCED |
| R08 | JWT thiếu/sai hoặc tenant khác | **401/403/404**, không phục vụ fallback |
| R09 | Optional trả 401/403 hoặc schema corrupted | Không nuốt thành empty success |
| R10 | Ratings không có đánh giá thật | count=0, không nhầm omitted |
| R11 | Client/cache nhận FULL và REDUCED liên tiếp | ETag/cache semantics đúng variant |
| R12 | Server trả 206 cho JSON thiếu sections | Test phải phát hiện lỗi contract |
| R13 | Circuit open, bulkhead queue đầy | Fail fast, core p95 vẫn trong budget |
| R14 | Circuit đóng sau recovery | Quay lại FULL có cooldown, không flap |
| R15 | Retry 429/503 từ optional service | Attempts và deadline có giới hạn |
| R16 | Product/ACL thay đổi sau cache | Không trả data cũ trái quyền |
| R17 | Checkout thiếu stock/giá hiện hành | Fail-closed, không tạo giao dịch |
| R18 | Error response/metrics | Không lộ token/hostname/PII |

**Kiểm thử nhiều người dùng, nhiều tenant, consent revoke, concurrent policy change và tải cao** mới đủ chứng minh response rút gọn an toàn. Tỷ lệ 2xx cao không chứng minh không rò dữ liệu và không chứng minh mọi chức năng đã hoạt động.

## 15. Bài tập: Product Overview chịu lỗi trong 700 ms

Một API tổng hợp **Product Core, Ratings và Recommendations**. Core chứa giá hiện hành; Ratings có cache tối đa **10 phút**; Recommendations được phép bỏ. Client gọi **completeness=full|flexible**. **POST /orders** cần tồn kho và giá đúng, không được rút gọn hai phần đó.

**Yêu cầu (100 điểm):** (1) **Policy – 25:** xác định minimum contract, optional sections, TTL và bốn điều kiện bắt buộc fail-closed. (2) **HTTP/OpenAPI – 25:** viết response FULL, REDUCED, 503; giải thích null khác [] và vì sao không dùng 206. (3) **Java/Spring – 30:** thiết kế controller/service/gateway với JWT/tenant, optional timeout/circuit/bulkhead, không catch Exception rộng, full mode. (4) **Security/testing – 20:** ít nhất mười test về lỗi core, timeout, cache stale/revoked, cross-tenant, recovery, checkout.

**Hướng giải:** luôn xác thực và đọc core hiện hành trước. Optional có budget riêng; recommendation lỗi thì omit và đánh dấu; ratings cache chỉ dùng khi đúng **scope, asOf và TTL**, đánh dấu stale. Full mode không chấp nhận omission; checkout thất bại nếu price/stock không được xác nhận. Đo **core latency, full-fidelity rate, reduced rate và error rate** tách biệt.

## 16. Checklist và nguồn tham khảo

- [ ] Endpoint có **minimum data contract** và allowlist section được phép thiếu.
- [ ] Không biến lỗi core, security, consent hoặc dữ liệu sai thành 200.
- [ ] FULL/REDUCED/STALE phân biệt; empty thật không bị coi là dependency outage.
- [ ] 200 rút gọn có metadata; full mode và 503 rõ; **không dùng 206** cho JSON thiếu field.
- [ ] Cache TTL, asOf, tenant/permission scope và invalidation được kiểm.
- [ ] Optional dependencies có timeout, retry budget, bulkhead, circuit riêng.
- [ ] Feature flag có guardrail, rollback và cách phục hồi có kiểm soát.
- [ ] Response/error/metrics không rò thông tin nội bộ.
- [ ] Có fault injection, contract tests, security tests và load test.

**Ghi nhớ:** graceful degradation không phải **trả 200 bằng mọi giá**. Chỉ bỏ phần **thực sự tùy chọn**, bảo toàn các bất biến nghiệp vụ/bảo mật và **nói rõ phần dữ liệu đã mất hoặc cũ** cho client.

**Nguồn:** RFC 9110 (HTTP Semantics, 206/Range), RFC 9111 (HTTP Caching), RFC 5861 (stale cache extensions), RFC 7240 (Prefer), RFC 9457 (Problem Details); OpenAPI 3.1; Spring Framework/Boot; Resilience4j và OWASP API Security Top 10.
