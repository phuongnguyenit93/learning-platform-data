# Lộ trình chuyển đổi, hỗ trợ và xác nhận kết thúc phiên bản

## 1. Vì sao phát hành API v2 chưa có nghĩa đã chuyển đổi xong?

Sau khi phát hành **/v2/orders**, đối tác vẫn gọi **/v1/orders** mỗi đêm, mobile cũ có thể offline nhiều tuần và cron job chỉ chạy cuối quý. Xóa v1 khi traffic gần 0 sẽ làm hỏng client hiếm hoạt động. Ngược lại, duy trì mã cũ mãi mãi tăng chi phí và rủi ro bảo mật. **Tiến hóa API cần lộ trình và bằng chứng hoàn tất**, không chỉ đổi version.

Bài thuộc chương **Tiến hóa API**, module **INTEGRATION_API_REST**, kết nối resource/URI, phương thức và status HTTP, hợp đồng dữ liệu, pagination, cache, idempotency, OpenAPI, bảo mật và Java/Spring. Trọng tâm là **lộ trình chuyển đổi, hỗ trợ, ngừng phiên bản và xác nhận EOL**.

Sau bài học, bạn có thể:

- Phân biệt **deprecated**, **supported**, **security-only**, **sunset**, **retired** và **archived**.
- Lập kế hoạch có **mốc, người chịu trách nhiệm, điều kiện tiến/lùi và kênh truyền thông**.
- Áp dụng đúng các HTTP header **Deprecation**, **Sunset** và **Link** để thông báo.
- Thiết kế adapter v1/v2, chuyển đổi dữ liệu, bảo vệ quyền và rollback có giới hạn.
- Dùng telemetry, consumer confirmation, contract tests và runbook để ra quyết định tắt v1.
- Xác nhận kết thúc bằng **bằng chứng kỹ thuật + chấp thuận nghiệp vụ**, không chỉ dựa trên “không thấy traffic”.

## 2. Từ ngữ phải thống nhất trước khi thông báo

| Trạng thái / mốc | Ý nghĩa thực hành | Hệ quả cho consumer |
| --- | --- | --- |
| **Active / GA** | Phiên bản phát hành chính thức, có hỗ trợ và phát triển theo cam kết. | Có thể triển khai mới theo chính sách. |
| **Deprecated** | Nhà cung cấp khuyến cáo **không dùng cho tích hợp mới**, đã công bố đường chuyển đổi. | Client hiện tại nên lên kế hoạch di chuyển; chưa mặc nhiên ngừng chạy. |
| **Feature freeze** | Không nhận thêm tính năng ở bản cũ, có thể vẫn sửa lỗi/bảo mật. | Không kỳ vọng bổ sung chức năng mới trên v1. |
| **Security-only support** | Chỉ xử lý lỗi bảo mật hoặc lỗi nghiêm trọng theo phạm vi đã công bố. | Cần có ngày kết thúc và kênh xử lý khẩn cấp. |
| **Sunset date** | Thời điểm dự kiến phiên bản/tài nguyên **không còn đáp ứng theo dịch vụ cũ**. | Cần hoàn thành chuyển đổi trước mốc, có kế hoạch dự phòng. |
| **Retired / disabled** | Định tuyến hoặc triển khai v1 đã bị ngừng; hành vi sau ngừng được xác định. | Request v1 không còn phục vụ nghiệp vụ. |
| **End of support (EoS)** | Kết thúc nghĩa vụ hỗ trợ theo chính sách/hợp đồng. | Không kỳ vọng nhà cung cấp xử lý sự cố trên bản cũ. |
| **Archived** | Giữ lại tài liệu, test/evidence hoặc dữ liệu theo thời hạn được phép. | Không đồng nghĩa endpoint còn hoạt động. |

**Deprecated không phải retired**: endpoint vẫn có thể trả 200/201 đúng hợp đồng. **Sunset** báo dự kiến, **EoS** là kết thúc hỗ trợ và có thể khác ngày ngừng kỹ thuật. Thông báo phải có **phạm vi, ngày UTC, bản thay thế, guide, kênh hỗ trợ, hành vi sau mốc**.

## 3. Chốt phạm vi chuyển đổi và đường cơ sở

Trước timeline, xác định:

1. **Scope:** chỉ /v1/orders, toàn /v1 hay một media type?
2. **Thay đổi:** methods, schema, errors, OAuth scopes, pagination, idempotency, cache, webhook?
3. **Consumers:** B2B, mobile, batch/cron, tích hợp vô danh?
4. **V2 readiness:** nghiệp vụ, security, SLO, data, quota, docs/SDK, recovery?
5. **Ràng buộc:** hợp đồng, đối soát, retention, khả năng phục hồi và pháp lý?

Breaking change còn có thể là đổi mặc định phân trang, 404 thành 200 rỗng, thay semantics idempotency, scope, Location hoặc timeout, dù JSON hầu như không đổi.

### 3.1. Hồ sơ phiên bản tối thiểu

~~~text
Version: Orders API v1
Scope: /v1/orders/** (không bao gồm /v1/payments/**)
Replacement: Orders API v2 (/v2/orders/**)
Owner: API Platform + Orders Domain
Customer success: Partner Integrations
Compatibility: v1 được duy trì tới mốc sunset theo chính sách
Security: vá lỗi nghiêm trọng cho tới khi ngừng v1
Support: ticket, incident channel, escalation và SLA đã thống nhất
Migration guide: https://docs.example.com/migration/orders-v1-v2
Rollback authority: Release lead + Security + Domain owner
~~~

Tài liệu EOL phải chỉ rõ **ai quyết định, ai thông báo, ai duyệt rủi ro** và kênh hỗ trợ.

## 4. Kiểm kê consumer dựa trên chứng cứ, không chỉ hỏi miệng

Danh sách consumer dễ bỏ sót script, credential dùng chung và job ít chạy; cần kết hợp nhiều nguồn:

| Nguồn | Thu được | Giới hạn |
| --- | --- | --- |
| **API gateway/access logs** | Version, route template, client credential/app ID, status, volume, last seen. | Có thể mất mẫu hoặc bị ẩn bởi NAT/proxy; user-agent không đáng tin. |
| **OAuth client registry / API key registry** | Chủ sở hữu ứng dụng, scope, đối tác liên hệ. | Key dùng chung không chỉ ra từng chương trình. |
| **Distributed tracing/metrics** | Độ trễ, lỗi, đường gọi v1 còn sống, job nền. | Sampling có thể bỏ qua traffic rất hiếm. |
| **Hệ thống hợp đồng/CSM/support** | Cam kết hỗ trợ và ngày nâng cấp của đối tác. | Có thể lỗi thời, cần xác nhận lại. |
| **Kho mã/CI và mobile release matrix** | Client/library dùng v1, lịch release. | Không nhìn thấy mọi binary đã phát hành. |
| **Consumer sign-off** | Ai đã test/migrate, bằng chứng thành công. | Phải đối chiếu với telemetry thực tế. |

Lưu **owner, mức quan trọng, auth, chu kỳ dùng, version, deadline, test v2 và sign-off** cho mỗi consumer.

Ví dụ record quản lý:

~~~yaml
consumer: partner-shipping-app
owner: partner-integrations
criticality: high
currentVersion: v1
targetVersion: v2
lastObservedV1: 2027-06-30T00:20:00Z
migrationTest: passed
productionCutover: scheduled
signoff: pending
~~~

**Một tuần không có request không chứng minh đã hết consumer**: batch quý, mobile offline và retry có thể xuất hiện sau đó. Cửa sổ quan sát cần theo **chu kỳ nghiệp vụ** và sign-off của client ít hoạt động.

### 4.1. Telemetry hữu ích mà không lộ dữ liệu cá nhân

Theo dõi các metric như:

- **api_requests_total{version, route_template, method, status_family, client_class}**.
- Số consumer còn active trên v1 theo **app/client ID được cấp**, không chỉ IP.
- Tỷ lệ lỗi 4xx/5xx, p95 latency và request success trên cả v1 lẫn v2.
- Các endpoint nguy hiểm: POST thanh toán, hủy đơn, webhook, export, command có tác dụng phụ.
- Request thất bại do schema mới, auth scope, idempotency, timeout và retry.

Không đưa token, key, body hay order ID vào nhãn metric; audit chi tiết phải được phân quyền và redaction.

## 5. Một lộ trình mẫu có mốc và tiêu chí ra quyết định

Các ngày dưới đây là **ví dụ lập kế hoạch UTC trong năm 2027**, không phải lịch áp dụng cho một API thật.

| Ngày UTC | Mốc | Deliverable / tiêu chí hoàn thành |
| --- | --- | --- |
| **15/01/2027** | **v2 GA** | Contract, docs, SDK, mock, migration guide; SLO và security tests v2 đạt. |
| **15/02/2027** | **Thông báo deprecation v1** | Email/portal/changelog, header Deprecation; danh sách consumer và owner. |
| **15/04/2027** | **Đóng đăng ký tích hợp v1 mới** | New integrations dùng v2; ngoại lệ có người duyệt. |
| **15/07/2027** | **v1 security-only support** | Không thêm tính năng; có on-call xử lý lỗ hổng, sự cố nghiêm trọng. |
| **15/09/2027** | **Go/no-go review** | Consumer xác nhận, kiểm tra traffic hiếm, test EOL, rollback và pháp lý. |
| **15/10/2027** | **Sunset/retirement v1** | Ngừng phục vụ nghiệp vụ v1 theo runbook; giám sát và hỗ trợ sau cutover. |
| **15/11/2027** | **Xác nhận kết thúc** | Ký biên bản kỹ thuật/nghiệp vụ, đóng ngoại lệ, lưu evidence đúng chính sách. |

Từ **15/07 đến 15/10**, v1 vẫn cần có cách xử lý lỗi bảo mật nghiêm trọng trong phạm vi support đã hứa; không nên tạo khoảng trống “không vá nhưng vẫn phục vụ dữ liệu nhạy cảm”. Nếu điều khoản hỗ trợ khác lịch này, phải cập nhật timeline và thông báo.

### 5.1. Giai đoạn 1 — Chuẩn bị

Chốt baseline v1, consumers, owner, khác biệt schema, thử SDK v2; định nghĩa **SLO và rollback threshold**.

### 5.2. Giai đoạn 2 — Chạy song song và di chuyển

Giữ v1 đúng contract, cung cấp v2/adapter và guide; từng consumer test staging, xác minh quyền/dữ liệu rồi chuyển production có giám sát.

### 5.3. Giai đoạn 3 — Giảm hỗ trợ có kiểm soát

Đóng đăng ký v1 mới; duy trì vá lỗi nghiêm trọng, theo dõi **consumer còn hoạt động** và escalation khi chưa sign-off.

### 5.4. Giai đoạn 4 — Quyết định và cutover

Thực hiện **go/no-go**. Gia hạn cần ngày mới, lý do, scope và owner; nếu bắt buộc tắt vì bảo mật/pháp lý, phải thông báo phương án thay thế.

### 5.5. Giai đoạn 5 — Xác nhận kết thúc

Sau tắt, quan sát traffic/lỗi, v2, ticket và dữ liệu; chỉ ký **EOL completed** khi đủ bằng chứng.

## 6. Tín hiệu HTTP: Deprecation, Sunset và Link

Đối với resource đã công bố lịch ngừng, có thể bổ sung metadata ngay trong response v1 để consumer và công cụ quan sát phát hiện. Hai trường chuẩn quan trọng:

- **Deprecation** theo **RFC 9745**: ngày resource được/đã đưa vào trạng thái deprecated, dùng kiểu **Structured Fields Date**, ví dụ **@1802649600** là ngày **15/02/2027 00:00:00 UTC**.
- **Sunset** theo **RFC 8594**: thời điểm dự kiến resource không còn đáp ứng, dùng định dạng **HTTP-date**, ví dụ **Fri, 15 Oct 2027 00:00:00 GMT**.

~~~http
GET /v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1802649600
Sunset: Fri, 15 Oct 2027 00:00:00 GMT
Link: <https://docs.example.com/migration/orders-v1-v2>; rel="deprecation"; type="text/html"
Link: <https://docs.example.com/policies/orders-v1-sunset>; rel="sunset"; type="text/html"

{"id":"11111111-1111-4111-8111-111111111111","status":"CREATED"}
~~~

**Lưu ý thiết kế:**

1. **Deprecation** và **Sunset** có **định dạng ngày khác nhau**; không dùng chuỗi HTTP-date cho Deprecation hoặc epoch @... cho Sunset. Sunset không được đặt **trước** ngày Deprecation.
2. Header áp dụng cho **resource có trong response**. Nếu tuyên bố một phạm vi rộng hơn (cả /v1/orders/** hoặc toàn API v1), phải ghi phạm vi ấy rõ trong tài liệu. Đừng suy rằng header ở một endpoint mặc nhiên bao trùm mọi endpoint.
3. **Link rel="deprecation"** dẫn tới thông tin/migration guide; **rel="sunset"** dẫn tới chính sách retirement. Link không phải lệnh chuyển hướng và không tự cấp quyền.
4. **Sunset là tín hiệu dự kiến**, không phải cam kết client sẽ chắc chắn nhận 200 trước mốc hoặc 410 sau mốc. Kế hoạch chính thức phải được thông báo ngoài giao thức và cập nhật nếu thay đổi.
5. Trong giai đoạn deprecated, **HTTP 200/201 hiện tại vẫn phải đúng hợp đồng v1**; không đổi mã trạng thái thành 299 hay tự chèn lỗi vào body chỉ để nhắc nâng cấp.
6. Nếu frontend JavaScript cần đọc header cross-origin, cấu hình CORS **Access-Control-Expose-Headers: Deprecation, Sunset, Link** theo chính sách origin; không làm rộng quyền truy cập dữ liệu.

Để tham khảo semantics chính xác: [RFC 9745 – Deprecation](https://www.rfc-editor.org/rfc/rfc9745.html), [RFC 8594 – Sunset](https://www.rfc-editor.org/rfc/rfc8594.html), [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).

### 6.1. 410 Gone có thể dùng sau khi retire không?

Có thể. Khi nhà cung cấp biết tài nguyên/endpoint cũ **không còn khả dụng lâu dài**, response **410 Gone** thể hiện khác biệt với **404 Not Found**, vốn có thể không chỉ rõ tính lâu dài. Nhưng việc dùng **410 hay 404** còn phụ thuộc thông tin server có và chính sách không tiết lộ resource. **410 không phải một phần bắt buộc của RFC Sunset**.

~~~http
GET /v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: no-store
Link: <https://docs.example.com/migration/orders-v1-v2>; rel="deprecation"

{
  "type": "https://api.example.com/problems/api-version-retired",
  "title": "API version retired",
  "status": 410,
  "detail": "Orders API v1 đã kết thúc; hãy chuyển sang v2.",
  "code": "API_VERSION_RETIRED"
}
~~~

**Cache-Control: no-store** ở đây là chính sách minh họa để tránh cache giữ response 410 nếu phải rollback; 410 có đặc tính cache riêng theo HTTP nên không được giả định mọi cache sẽ tự bỏ qua. Với caller chưa xác thực hoặc bị cấm, gateway/security có thể trả **401/403/404** trước, tránh lộ dữ liệu hoặc metadata ngoài quyền.

**Không tự động dùng 301/308 để redirect tất cả request v1 sang v2 khi hợp đồng phá vỡ tương thích.** POST/PATCH có body hoặc idempotency khác có thể gây tác dụng phụ ngoài ý muốn nếu chuyển đích mù quáng; ngay cả GET cũng có thể đổi nghĩa query/response. Cần adapter hoặc consumer migration có kiểm chứng, không chỉ đổi URL.

## 7. Bản đồ chuyển đổi: từ hợp đồng v1 sang v2

Giả sử phiên bản mới chuẩn hóa giá trị tiền và trạng thái đơn hàng:

| Khía cạnh | v1 | v2 | Quy tắc chuyển đổi |
| --- | --- | --- | --- |
| URL | **/v1/orders/{id}** | **/v2/orders/{id}** | Client cập nhật route và SDK. |
| Tiền | **totalAmount** dạng số thập phân | **totalMinorUnit** dạng integer | Cần currency, scale và làm tròn **có kiểm soát**, không cast từ float. |
| Trạng thái | **state: NEW** | **status: CREATED** | Định nghĩa bảng mapping có kiểm thử; không đoán bằng tên. |
| ID | UUID dạng chuỗi | UUID dạng chuỗi | Không đổi định danh chỉ vì đổi version. |
| Lỗi validation | Body legacy | **application/problem+json** | Client sửa parser/status handling. |
| Phân trang | offset/page | cursor/nextCursor | Không dịch máy móc page=5 thành cursor nếu API không cung cấp cơ chế. |
| Bảo mật | Legacy scope | Scope mới có tách quyền | Migrate token/consent và xác minh object-level authorization. |

Ví dụ GET v1:

~~~http
GET /v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1802649600
Sunset: Fri, 15 Oct 2027 00:00:00 GMT

{
  "id":"11111111-1111-4111-8111-111111111111",
  "state":"NEW",
  "currency":"USD",
  "totalAmount":1250.00
}
~~~

GET v2 tương ứng:

~~~http
GET /v2/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id":"11111111-1111-4111-8111-111111111111",
  "status":"CREATED",
  "currency":"USD",
  "totalMinorUnit":125000
}
~~~

**1250.00 USD = 125000 cents** với USD có 2 chữ số phần lẻ theo chính sách ví dụ. Không áp dụng cố định nhân 100 cho mọi đơn vị tiền; có loại tiền dùng 0 hoặc 3 chữ số phần lẻ và sản phẩm có thể có quy tắc tiền tệ riêng. Với tài chính, phải kiểm tra overflow, rounding, ngữ nghĩa trường và kết quả đối soát trước khi đổi kiểu.

### 7.1. Định nghĩa mapping như một hợp đồng có thể kiểm thử

~~~text
V1 state NEW        <-> V2 status CREATED
V1 state PAID       <-> V2 status PAID
V1 state CANCELLED  <-> V2 status CANCELLED
V1 totalAmount USD  -> V2 totalMinorUnit = exact(amount * 100)
~~~

Nếu v2 có trạng thái **PARTIALLY_REFUNDED** mà v1 không diễn tả được, phải quyết định rõ: bổ sung mapping được chấp thuận, giới hạn sử dụng v1, hay thông báo tính năng chỉ có ở v2. **Không tự ép trạng thái mới thành PAID** để làm vừa enum cũ khi có thể gây sai nghiệp vụ.

### 7.2. Tương thích schema không đủ

Một SDK v2 deserialize thành công vẫn có thể gặp lỗi khi backend đổi cách hiểu thời gian, giá trị null, tổng tiền, ETag, retry hoặc điều kiện bảo mật. **Bộ mapping phải có ca semantic parity**, so kết quả nghiệp vụ của cùng đơn giữa hai phiên bản trên dữ liệu được cấp quyền, không chỉ đối chiếu tên trường.

Khi chuyển idempotency keys, phải quyết định phạm vi key theo consumer, operation và version. Nếu v1 và v2 cùng tác động một lệnh tạo đơn, việc hai route dùng key khác nhau có thể **tạo hai đơn** nếu server không quản lý deduplication ở tầng nghiệp vụ.

## 8. Chiến lược triển khai song song và chuyển traffic

### 8.1. Ưu tiên một lõi nghiệp vụ, hai lớp hợp đồng

~~~mermaid
flowchart LR
    C1["Client v1"] --> A1["Adapter /v1"]
    C2["Client v2"] --> A2["Controller /v2"]
    A1 --> S["Service nghiệp vụ chung"]
    A2 --> S
    S --> DB[("Dữ liệu chuẩn")]
~~~

Mô hình này thường an toàn hơn việc chạy **hai business logic khác nhau và dual-write hai database** chỉ để duy trì hai phiên bản HTTP. Adapter v1 giữ JSON/status/headers theo hợp đồng cũ nhưng gọi cùng service có transaction, authorization, audit và quy tắc dữ liệu. Không vì muốn giữ v1 mà tạo một đường truy cập bỏ qua kiểm tra quyền mới.

### 8.2. Các lựa chọn triển khai

| Cách | Khi phù hợp | Cảnh báo |
| --- | --- | --- |
| **Expand–migrate–contract** | Có thể mở rộng schema/handler trước, rồi chuyển client và cuối cùng bỏ legacy. | Chỉ contract sau khi có bằng chứng consumer đã rời v1. |
| **Adapter/anti-corruption layer** | v1 khác format, v2 dùng model mới. | Mapping phải chính xác, gồm lỗi, trạng thái và authorization. |
| **Canary theo client ID** | Di chuyển nhóm người dùng/đối tác từng đợt. | Session, quota, token, idempotency và sticky behavior phải được xét. |
| **Shadow read / response comparison** | So kết quả GET v1/v2 mà không đổi hành vi với client. | Không shadow các lệnh ghi có tác dụng phụ hoặc làm lộ dữ liệu. |
| **Gateway route cutover** | V1/v2 cùng gateway, cần tắt đường legacy có kiểm soát. | Gateway không tự chuyển JSON/logic giữa hai hợp đồng khác nhau. |

Khi shadow read, kết quả phụ có thể truy cập dữ liệu nhạy cảm hoặc kích hoạt rate limit; cần phân quyền môi trường, redaction và sampling có kiểm soát. Với POST thanh toán hoặc hủy đơn, **không gửi song song hai lệnh thật để “so sánh”**.

### 8.3. Kế hoạch quay lui phải có ranh giới

Rollback an toàn thường gồm:

- Dừng rollout một nhóm consumer v2, chuyển lại client/SDK nếu dữ liệu chưa bị thay đổi bất tương thích.
- Giữ adapter v1 trong thời gian chuyển tiếp, không xóa code/config trước go/no-go.
- Có feature flag/route config có kiểm soát, rehearsal và owner được quyền bật/tắt.
- Kiểm tra **schema expand** có cho phép v1 đọc dữ liệu v2 mới ghi không; nếu không, quay lui route không cứu được tính đúng.
- Định nghĩa rõ điều kiện **không rollback**: lỗ hổng bảo mật nghiêm trọng, compliance hoặc dữ liệu đã không thể diễn dịch trên v1.

Rollback **không** đồng nghĩa luôn có thể đảo ngược dữ liệu. Một migration có xóa trường, gộp trạng thái hoặc thay đổi side effect cần backup/restore, dual-read có kiểm soát hoặc phương án phục hồi khác được thử trước.

## 9. Java/Spring: phục vụ v1 trong thời gian chuyển đổi

Ví dụ dùng **Spring Boot 3 / Spring MVC**. Mục tiêu là giữ **v1 contract** khi backend đã dùng model v2, và phát cảnh báo retirement đúng giao thức. Các lớp dưới đây minh họa, không phải dự án chạy nguyên trạng có đủ security/database.

### 9.1. Adapter v1 đọc dữ liệu chuẩn

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record CanonicalOrder(
        UUID id, long totalMinorUnit, String currency, String status) {}
record LegacyOrder(
        String id, String state, String currency, BigDecimal totalAmount) {}

interface OrderQueryService {
    CanonicalOrder findAuthorized(UUID id);
}

@RestController
@RequestMapping("/v1/orders")
class LegacyOrdersController {
    private final OrderQueryService orders;

    LegacyOrdersController(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    ResponseEntity<LegacyOrder> get(@PathVariable UUID id) {
        // findAuthorized kiểm tra danh tính và tenant ở server.
        CanonicalOrder order = orders.findAuthorized(id);
        int digits = Currency.getInstance(order.currency())
                .getDefaultFractionDigits();
        if (digits < 0) {
            throw new IllegalStateException(
                    "Currency needs explicit minor-unit policy");
        }
        BigDecimal amount =
                BigDecimal.valueOf(order.totalMinorUnit(), digits);
        String state = switch (order.status()) {
            case "CREATED" -> "NEW";
            case "PAID" -> "PAID";
            case "CANCELLED" -> "CANCELLED";
            default -> throw new IllegalStateException(
                    "V1 cannot represent this order state");
        };
        return ResponseEntity.ok(
                new LegacyOrder(
                        order.id().toString(),
                        state, order.currency(), amount));
    }
}
~~~

**Giới hạn:** đây chỉ là GET và mapping minh họa. Bản v1 thật phải bảo toàn status, cache, pagination, error body và mọi contract đã hứa. Currency minor units dùng ví dụ USD; có thể cần bảng quy tắc riêng theo nghiệp vụ. **Không dùng Double để đổi tiền**, và không bật trạng thái v2 mới khi v1 chưa có cách biểu diễn an toàn.

### 9.2. Gắn Deprecation/Sunset trên response v1

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
class LegacyLifecycleFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String path = request.getRequestURI();
        String prefix = request.getContextPath() + "/v1/orders";
        if (path.equals(prefix) || path.startsWith(prefix + "/")) {
            response.setHeader("Deprecation", "@1802649600");
            response.setHeader(
                    "Sunset", "Fri, 15 Oct 2027 00:00:00 GMT");
            response.addHeader(
                    "Link",
                    "<https://docs.example.com/migration/orders-v1-v2>"
                    + "; rel=\"deprecation\"; type=\"text/html\"");
        }
        chain.doFilter(request, response);
    }
}
~~~

Filter chỉ minh họa cách phát header theo route. Production nên đưa ngày/URL vào **config được quản lý và review**, không hard-code mãi trong controller. Thứ tự Spring Security/gateway có thể khiến một số response được xử lý trước filter; **test thực tế trên gateway và cả 401/403/404**, thay vì giả định header sẽ có trên mọi lỗi. Mọi request vẫn phải kiểm tra quyền trước khi trả dữ liệu; lifecycle metadata không cấp phép truy cập.

**Điểm cần tránh:** filter trên chỉ chọn **/v1/orders**; không được coi đó là thông báo tự động cho toàn bộ /v1 nếu chính sách thực tế chỉ áp dụng một nhóm route. Bản v2 không nên có các header thông báo v1 sắp ngừng.

### 9.3. Sau retirement: không tiếp tục gọi business service

Tại mốc cutover, gateway/controller v1 có thể dùng một **retirement handler** trả **410 + Problem Details + Link đến guide**, thay vì route request v1 vào service ghi. Security vẫn phải áp dụng theo chính sách. Với **POST/PATCH/DELETE**, không được gọi nghiệp vụ rồi mới quyết định trả 410; test cần xác minh **không có side effect**.

Một cấu hình an toàn là **giữ route tombstone ở gateway hoặc controller** có thời hạn, quan sát số client còn cố gọi v1 và đưa migration guide. Nếu loại bỏ route hoàn toàn, 404 là kết quả có thể xuất hiện nhưng mất khả năng hướng dẫn. Quyết định này phải nằm trong runbook và không để response 410 của endpoint đã retire bị hiểu là “đơn hàng cụ thể đã bị xóa”.

## 10. Bảo mật và nghĩa vụ hỗ trợ suốt vòng đời

Một bản v1 bị deprecate nhưng vẫn nhận dữ liệu thật là **một bề mặt tấn công còn sống**. Chính sách chuyển đổi cần xét:

- **Authentication/authorization parity:** JWT validation, OAuth scopes, tenant isolation và object-level authorization của v1 không được yếu hơn v2 chỉ vì giữ adapter.
- **Thư viện và lỗ hổng:** bản v1 còn chạy phải có kế hoạch vá security. Nếu không thể vá, nâng mức rủi ro, rút mốc sunset có truyền thông và phương án cho consumer.
- **Chống replay/tạo trùng:** client có thể retry giữa v1/v2; bảo vệ idempotency theo **thao tác nghiệp vụ**, không chỉ route.
- **Logs/metrics:** không lưu access token, body nhạy cảm hay client secret; dashboard consumer đã được hạn chế quyền truy cập.
- **Data migration:** backfill và đối soát theo tenant; không xóa dữ liệu/audit trail chỉ vì endpoint cũ ngừng.
- **Docs/mocks/SDK:** đánh dấu rõ bản cũ, ngăn sinh tích hợp mới, không cung cấp khóa thử nghiệm thực trong ví dụ.
- **Quyền truy cập sau EOL:** thu hồi credential/scope chỉ chuyên dùng v1 theo quy trình, tránh vô tình làm v2 ngừng hoạt động nếu hai bản dùng chung client credential.

Nếu security-only support cho v1 tới 15/10/2027, cần có **owner, kênh báo cáo lỗ hổng, SLA khẩn cấp và bản vá triển khai được** cho toàn bộ thời gian ấy. Không được tuyên bố “unsupported” trong khi vẫn xử lý dữ liệu nhạy cảm mà không có quyết định chấp thuận rủi ro rõ ràng.

## 11. Kiểm thử chuyển đổi trước và sau khi tắt v1

| Test | Điều cần chứng minh |
| --- | --- |
| **Hợp đồng v1** | Trong thời gian hỗ trợ, status, schema, header và lỗi cũ vẫn đúng. |
| **Hợp đồng v2** | Client/SDK mới hoạt động với các request hợp lệ và lỗi. |
| **Mapping dữ liệu** | Giá trị tiền, status, ID, null và thời gian giữ đúng ngữ nghĩa. |
| **Security** | Không vượt quyền tenant; cả v1/v2 đều bảo vệ mọi thao tác. |
| **Side effects** | Retry và chuyển route không tạo đơn/thanh toán trùng. |
| **Metadata vòng đời** | Deprecation/Sunset/Link đúng route, ngày và URL hướng dẫn. |
| **Retirement** | v1 trả 410/404 theo chính sách; không còn thao tác ghi. |
| **Rollback** | Có thể khôi phục route được phép mà không làm sai dữ liệu. |

Ví dụ **Spring MockMvc** kiểm tra metadata trong giai đoạn chuyển tiếp:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/v1/orders/{id}", orderId))
    .andExpect(status().isOk())
    .andExpect(header().string("Deprecation", "@1802649600"))
    .andExpect(header().string(
        "Sunset", "Fri, 15 Oct 2027 00:00:00 GMT"))
    .andExpect(jsonPath("$.state").value("NEW"));
~~~

Test cần mock principal/service hoặc security context phù hợp. Ở môi trường tích hợp, cần chạy **client v1 cũ** và **SDK v2** trên cùng dữ liệu test, gọi qua gateway, xác minh quyền và mapping; so request/response cùng ID nhưng không shadow các lệnh ghi gây tác dụng phụ.

## 12. Go/no-go và hồ sơ xác nhận kết thúc

**Không có traffic trong dashboard không đủ để tuyên bố EOL.** Trước ngày sunset, owner cần một bảng quyết định:

| Cổng quyết định | Bằng chứng đạt |
| --- | --- |
| Consumer coverage | Mọi consumer quan trọng đã migrate, hoặc ngoại lệ/rủi ro có người duyệt. |
| Telemetry | V1 traffic được phân tích đủ chu kỳ daily/monthly/quarterly; unknown clients được điều tra. |
| V2 readiness | Contract/security/performance tests đạt; SLO và on-call sẵn sàng. |
| Cutover | Runbook, rollback boundary, kênh sự cố và thông báo đã diễn tập. |
| Compliance | Hợp đồng, retention và quyền dữ liệu đã được kiểm tra. |

Sau khi triển khai retirement, thu thập **bằng chứng hoạt động**, không chỉ checklist: route/config đã thay, request v1 thử nghiệm trả mã dự kiến, lệnh ghi không còn tác dụng, số request v1 còn lại và ticket đã xử lý, v2 đạt ngưỡng chất lượng. Kiểm tra tại **D+0, D+7 và D+30**; các mốc này là lịch vận hành gợi ý.

Biên bản kết thúc ghi: **version/scope, ngày thực tế, người phê duyệt, kết quả test, consumer sign-off, số ngoại lệ, vấn đề tồn đọng, nơi lưu log/tài liệu và chính sách xóa**. Chỉ sau đó mới dọn đường route, credential chỉ dành cho v1 và code legacy theo quy trình kiểm soát thay đổi.

Nếu consumer quan trọng vẫn chưa chuyển và không có ràng buộc buộc phải tắt, quyết định **no-go** cần một ngày mới, owner, biện pháp giảm rủi ro và thông báo lại. Không gia hạn âm thầm để mỗi nơi hiểu một lịch khác nhau.

## 13. Bài tập: kết thúc Orders API v1

Một đối tác dùng **POST /v1/orders** mỗi đêm; mobile cũ có thể offline 60 ngày; báo cáo tài chính chạy một lần/quý. Nhóm vận hành dự định tắt v1 sau khi dashboard thấy request giảm 99%. V2 đổi **totalAmount** thành **totalMinorUnit**, bảo vệ bằng scope OAuth2 khác và dùng cursor thay offset.

**Yêu cầu:** (1) Liệt kê consumer còn rủi ro và dữ liệu cần thu. (2) Đề xuất các mốc thông báo/hỗ trợ/sunset. (3) Viết header HTTP trên GET v1 trong giai đoạn deprecation. (4) Nêu ba phép kiểm thử chứng minh v2 giữ đúng nghiệp vụ và quyền. (5) Chọn bằng chứng cần có trước khi ký EOL.

**Gợi ý:** 99% giảm traffic chưa đủ, vì batch quý/mobile offline vẫn có thể dùng v1. Kết hợp registry, logs, sign-off và chu kỳ quan sát dài hơn. Dùng **Deprecation @date, Sunset HTTP-date và Link** tới guide; duy trì v1 đúng contract cho tới sunset. Test chuyển tiền chính xác, scope/tenant và idempotency; chỉ ký EOL sau khi kiểm tra route cũ không còn xử lý nghiệp vụ, consumer quan trọng đã xác nhận và có giám sát hậu cutover.

## 14. Checklist và kết luận

- [ ] Xác định đúng **phạm vi phiên bản**, owner, deadline và hợp đồng hỗ trợ.
- [ ] Có danh sách consumer với last-seen, chu kỳ sử dụng, rủi ro và sign-off.
- [ ] V2 đủ chức năng/quyền; migration guide, docs, SDK, mock và test sẵn sàng.
- [ ] Header Deprecation/Sunset đúng chuẩn, scope, ngày và Link hướng dẫn.
- [ ] Chạy song song không làm thay đổi dữ liệu hay tạo tác dụng phụ trùng.
- [ ] Có go/no-go, rollback rehearsal và kịch bản giao tiếp sự cố.
- [ ] Sau sunset, v1 không còn thực hiện nghiệp vụ; 410/404 đúng chính sách.
- [ ] Thu đủ evidence, theo dõi D+0/D+7/D+30 và lưu biên bản EOL.

**Kết luận:** Tiến hóa API là **chương trình chuyển đổi có quản trị**, không chỉ phát hành v2. **Deprecation** thông báo cần di chuyển, **Sunset** chỉ mốc dự kiến, còn **kết thúc thực tế** phải được chứng minh bằng consumer readiness, kiểm thử, telemetry, an toàn bảo mật và xác nhận chính thức sau cutover.
