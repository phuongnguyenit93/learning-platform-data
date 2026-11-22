# Test BOLA và broken property authorization

## 1. Mục tiêu của bài kiểm thử

Một API có thể xác thực đúng người gọi nhưng vẫn trả dữ liệu của người khác hoặc cho phép sửa những thuộc tính mà caller không được quyền thay đổi. Hai nhóm lỗi cần đánh giá riêng là:

- **Broken Object Level Authorization (BOLA):** server không kiểm tra đầy đủ quan hệ giữa principal hiện tại và object được tham chiếu trong request. Caller dùng một object ID hợp lệ nhưng không thuộc phạm vi quyền của mình để đọc, sửa, xóa hoặc thực hiện hành động trên object đó.
- **Broken Object Property Level Authorization (BOPLA):** server không giới hạn đúng các thuộc tính mà caller được đọc hoặc ghi. Lỗi đọc thường biểu hiện thành excessive data exposure; lỗi ghi thường biểu hiện thành mass assignment hoặc thay đổi field server-owned.

Bài này tập trung vào cách đánh giá thực tế hai loại lỗi trên trong một API: xác định phạm vi, chuẩn bị tài khoản và dữ liệu thử nghiệm, tìm mọi vị trí nhận object/property, thực hiện test có kiểm soát, xác minh tác động và ghi nhận bằng chứng để sửa lỗi.

Không kết luận API an toàn chỉ vì endpoint yêu cầu bearer token, object ID là UUID khó đoán hoặc response trả `403`. Cần chứng minh server kiểm tra đúng object relationship và property policy trên mọi đường đọc/ghi, đồng thời request bị từ chối không tạo side effect.

## 2. Phân biệt BOLA, IDOR và BOPLA

Các thuật ngữ liên quan nhưng không hoàn toàn đồng nghĩa:

| Khái niệm | Điều cần đánh giá | Ví dụ |
|---|---|---|
| BOLA | Quyền truy cập object cụ thể. | Alice đọc `/orders/ord-bob` dù đơn hàng thuộc Bob. |
| IDOR | Một dạng tham chiếu object trực tiếp có thể bị khai thác khi thiếu kiểm tra quyền. | Thay `fileId` hoặc `invoiceId` trong URL để truy cập record khác. |
| Excessive data exposure | Response trả nhiều field hơn quyền hoặc nhu cầu của caller. | Customer đọc được `internalRiskScore` hoặc `fraudReviewNotes`. |
| Mass assignment | Input client được bind vào field mà caller không được phép sửa. | Customer gửi `ownerId`, `tenantId` hoặc `paymentStatus` trong PATCH. |
| BOPLA | Lỗi authorization ở cấp thuộc tính, bao gồm cả đọc và ghi. | User không có quyền xem salary nhưng response vẫn trả; hoặc sửa field `approvedBy`. |

BOLA và BOPLA có thể cùng xuất hiện trong một endpoint. Ví dụ Alice đọc được object invoice của Bob (BOLA), và response invoice của Alice còn tiết lộ field ngân hàng nội bộ (BOPLA). Khi đánh giá, ghi nhận riêng object boundary và property boundary để remediation không bỏ sót một nửa vấn đề.

## 3. Chuẩn bị phạm vi và môi trường kiểm thử

Authorization assessment có thể tạo ra thay đổi dữ liệu, gửi thông báo hoặc kích hoạt giao dịch. Trước khi chạy test, cần có phạm vi được phê duyệt và môi trường phù hợp.

1. Xác nhận base URL, API version, tenant, endpoint, method và luồng nghiệp vụ nằm trong scope.
2. Ưu tiên staging hoặc môi trường test có cấu hình authorization tương đương production.
3. Dùng test accounts, test tokens và dữ liệu giả do đội sở hữu hệ thống chuẩn bị.
4. Xác định thao tác có side effect như refund, cancel, delete, invite, export hoặc gửi webhook; dùng sandbox/mock downstream hoặc object có thể khôi phục.
5. Chốt giới hạn request, thời gian, concurrency và cách dừng test nếu phát hiện dữ liệu thật hoặc tác động ngoài dự kiến.
6. Ghi lại expected policy với owner nghiệp vụ/security trước khi đánh giá kết quả.

Không dò ID ngẫu nhiên trên dữ liệu production, không thử thay đổi object của khách hàng thật và không chạy bulk/delete/refund test nếu chưa có dữ liệu thử nghiệm cùng phương án rollback. Mục tiêu là xác minh policy bằng các principal và object đã được cấp cho assessment.

## 4. Xây dựng bộ principal và object có thể phân biệt

Một bộ fixture tốt cần có cả hai trường hợp: hai user khác nhau trong cùng tenant và user thuộc tenant khác. Nếu chỉ tạo một user trên mỗi tenant, test có thể bỏ sót lỗi ownership bên trong cùng tenant.

Ví dụ test data:

| Principal | Role | Tenant | Object được sở hữu/phân công |
|---|---|---|---|
| `alice` | Customer | `tenant-red` | `order-A1`, `profile-A` |
| `bob` | Customer | `tenant-red` | `order-A2`, `profile-B` |
| `carol` | Customer | `tenant-blue` | `order-B1`, `profile-C` |
| `support-red` | Support | `tenant-red` | Case `case-R1` được phân công |
| `admin-red` | Tenant admin | `tenant-red` | Thành viên và cấu hình tenant-red |
| `service-fulfillment` | Service identity | `tenant-red` | Shipment được giao cho service |
| `anonymous` | Không có identity | Không có | Không có |

Tạo dữ liệu nhạy cảm giả để kiểm tra property policy, chẳng hạn:

```json
{
  "id": "profile-A",
  "displayName": "Alice Example",
  "email": "alice-test@example.invalid",
  "tenantId": "tenant-red",
  "role": "CUSTOMER",
  "internalRiskScore": 17,
  "fraudReviewNotes": "TEST ONLY",
  "approvedBy": "reviewer-test"
}
```

Định nghĩa trước field nào customer được đọc, field nào chỉ support/admin được đọc và field nào chỉ server cập nhật. Không dùng dữ liệu production để làm fixture. Các giá trị giả giúp xác định chính xác field nào bị lộ trong response hoặc bị thay đổi sau request.

## 5. Lập bản đồ object reference và property

Trước khi gửi request, rà soát contract, route list, OpenAPI hoặc code flow trong phạm vi được giao để xác định object ID và field đi vào đâu. Một object có thể được tham chiếu ở nhiều vị trí:

| Vị trí | Ví dụ | Câu hỏi kiểm thử |
|---|---|---|
| Path parameter | `/orders/{orderId}` | Đổi ID sang object của user khác có bị chặn không? |
| Query parameter | `?invoiceId=...` | Filter hoặc export có giữ tenant/owner scope không? |
| Request body | `{ "accountId": "..." }` | Server có xác minh quan hệ giữa account và principal không? |
| Nested object | `{ "items": [{ "documentId": "..." }] }` | Từng object con có được authorize không? |
| Header | `X-Tenant-ID`, `X-Account-ID` | Header có bị caller tự giả mạo không? |
| Bulk array | `{ "orderIds": ["...", "..."] }` | Một ID ngoài scope có làm lộ hoặc thay đổi dữ liệu không? |
| GraphQL/RPC input | `node(id: ...)`, `updateRecord(input: ...)` | Resolver có áp policy như REST endpoint không? |
| File/download reference | `fileId`, export ID, signed URL | Quyền được kiểm tra lúc tạo và lúc sử dụng capability ra sao? |
| Async job/event | `jobId`, `resourceId`, `tenantId` | Worker có tái xác minh scope khi xử lý không? |

Đối với property, phân loại ít nhất:

- Field public/được phép đọc.
- Field chỉ một số role hoặc purpose được đọc.
- Field được caller cập nhật.
- Field chỉ server hoặc workflow đặc quyền được cập nhật.
- Field nhạy cảm không được xuất hiện trong response của caller thông thường.

Tập trung vào các field có thể thay đổi quyền hoặc trạng thái: `ownerId`, `tenantId`, `role`, `permissions`, `isAdmin`, `approvedBy`, `paymentStatus`, `balance`, `price`, `discount`, `riskScore`, `visibility` và các field tương đương trong domain thực tế.

## 6. Quy trình đánh giá có hệ thống

Một assessment có thể thực hiện theo chuỗi sau:

1. **Baseline:** gọi endpoint bằng principal có quyền hợp lệ trên object của chính mình; lưu status, response schema và trạng thái dữ liệu trước/sau.
2. **Object substitution:** giữ nguyên principal và thay một object reference bằng ID của user khác cùng tenant.
3. **Tenant substitution:** thay reference bằng object của tenant khác.
4. **Role/function variation:** chạy cùng request với role thấp hơn, role khác hoặc service identity không có chức năng đó.
5. **Method/action variation:** lặp lại trên read, update, delete, approve, download, export và các action phụ.
6. **Property read assessment:** so sánh field thực tế trả về với field mà role được phép đọc.
7. **Property write assessment:** gửi field được phép cùng field nhạy cảm/server-owned, sau đó đọc lại trạng thái lưu trữ.
8. **Alternate path assessment:** kiểm tra list, search, bulk, nested resource, GraphQL, cache, file và background job.
9. **Side-effect verification:** xác minh request bị deny không cập nhật database, phát event, gọi downstream hoặc gửi thông báo.
10. **Evidence and retest:** lưu request/response đã redacted, object ownership, expected policy, actual result và xác nhận sau khi sửa.

Thay một biến tại một thời điểm giúp biết chính xác policy nào bị thiếu. Khi cần test kết hợp nhiều yếu tố, ghi rõ tổ hợp principal, role, tenant, object state và property để người khác có thể tái hiện.

## 7. Kiểm thử BOLA trên thao tác đọc

Bắt đầu với request hợp lệ của Alice trên `order-A1`, sau đó giữ nguyên token Alice và đổi object ID sang `order-A2` của Bob trong cùng tenant.

```http
GET /api/orders/order-A1 HTTP/1.1
Host: api.test.example
Authorization: Bearer <alice-test-token>
Accept: application/json
```

Baseline dự kiến trả dữ liệu đơn hàng A1. Sau đó thay ID:

```http
GET /api/orders/order-A2 HTTP/1.1
Host: api.test.example
Authorization: Bearer <alice-test-token>
Accept: application/json
```

Request thứ hai phải bị từ chối theo contract, hoặc trả response không tiết lộ object tồn tại. Nếu server trả dữ liệu của Bob, đã có bằng chứng BOLA. Tiếp tục thử object `order-B1` thuộc tenant-blue để xác định cả ownership lẫn tenant boundary.

Khi đọc response, không chỉ nhìn status code. Kiểm tra:

- Object ID, owner, tenant và field thực tế được trả.
- Header hoặc metadata có tiết lộ existence, count, location hay download URL không.
- Response body có khác biệt cho phép suy ra object tồn tại dù nội dung bị che không.
- Cache có trả dữ liệu đã được lưu bởi principal khác không.

`403` và `404` đều có thể là hành vi hợp lệ tùy API contract. `404` có thể được dùng để che giấu sự tồn tại của object. Tuy nhiên, `404` không chứng minh BOLA đã được ngăn nếu response khác hoặc side channel vẫn tiết lộ dữ liệu.

## 8. Kiểm thử BOLA trên thao tác ghi và hành động

BOLA không chỉ là lỗi đọc. Một caller có thể sửa, xóa, phê duyệt, hoàn tiền hoặc thực hiện action trên object không thuộc quyền của mình.

Các thao tác cần xem xét:

| Operation | Thử nghiệm có kiểm soát | Điều phải xác minh |
|---|---|---|
| Update | Alice gửi PATCH tới order của Bob trong fixture. | Không field nào của Bob thay đổi. |
| Delete/archive | Dùng object test có thể khôi phục thuộc principal khác. | Object vẫn tồn tại/không đổi khi deny. |
| Approve/reject | Dùng account không có quyền hoặc object ngoài scope. | Approval state và workflow không đổi. |
| Cancel/close | Gọi action trên resource của user khác. | Không tạo transition hoặc notification. |
| Refund/payment | Chỉ dùng sandbox payment và test transaction. | Không tạo refund/charge ngoài policy. |
| Download/export | Yêu cầu file/report của principal khác. | Không trả bytes, signed URL hoặc metadata nhạy cảm. |
| Bulk action | Trộn object được phép và không được phép. | Hành vi atomic/partial đúng contract, không có tác động ngoài ý muốn. |

Ví dụ request cập nhật chỉ dùng object test:

```http
PATCH /api/orders/order-A2/address HTTP/1.1
Host: api.test.example
Authorization: Bearer <alice-test-token>
Content-Type: application/json

{
  "shippingAddress": "TEST ADDRESS - DO NOT SHIP"
}
```

Sau request, đọc lại order-A2 bằng account Bob hoặc qua test database. Nếu địa chỉ thay đổi dù Alice không có quyền, đây là lỗi integrity. Nếu request trả `403` nhưng message/event đã được phát hoặc downstream đã được gọi, vẫn là lỗi nghiêm trọng cần điều tra transaction boundary.

Không chạy action có tác dụng tài chính hoặc gửi hàng trên hệ thống thật trong assessment thông thường. Dùng sandbox, mock provider hoặc test object được đánh dấu rõ để tránh tác động không thể đảo ngược.

## 9. Kiểm thử BOLA ở nested resource và relationship

Một endpoint có thể kiểm tra quyền trên parent nhưng bỏ sót object con. Ví dụ Alice có quyền đọc order của mình nhưng request chứa `documentId` của Bob; hoặc tenant admin có thể đọc member list nhưng không được truy cập billing profile của tenant khác.

Kiểm tra các trường hợp:

- Parent thuộc caller nhưng child reference thuộc người khác.
- Child thuộc đúng tenant nhưng không liên kết với parent được gửi.
- Thay `accountId`, `projectId`, `workspaceId` hoặc `organizationId` trong nested route.
- Gửi ID object con trong array hoặc relation update.
- Dùng relationship đã bị thu hồi, object đã chuyển owner hoặc user đã rời tenant.
- Dùng parent ID hợp lệ nhưng child endpoint có policy khác.

Ví dụ:

```http
POST /api/orders/order-A1/attachments HTTP/1.1
Authorization: Bearer <alice-test-token>
Content-Type: application/json

{
  "fileId": "file-owned-by-bob"
}
```

Việc Alice được quyền thêm attachment cho order-A1 không có nghĩa Alice được quyền gắn bất kỳ file ID nào. Server cần xác minh file thuộc Alice/tenant phù hợp và trạng thái file cho phép liên kết. Test cả object parent lẫn object con và quan hệ giữa chúng.

## 10. Kiểm thử excessive data exposure

Với BOPLA ở chiều đọc, đánh giá response theo role, purpose và resource. Không giả định mọi field trong database hoặc entity đều được phép serialize ra API.

Ví dụ response thực tế của customer có thể vô tình chứa:

```json
{
  "id": "profile-A",
  "displayName": "Alice Example",
  "email": "alice-test@example.invalid",
  "role": "CUSTOMER",
  "tenantId": "tenant-red",
  "internalRiskScore": 17,
  "fraudReviewNotes": "TEST ONLY",
  "supportOnlyFlags": ["manual-review"]
}
```

Nếu customer chỉ được xem `displayName` và email đã xác minh, các field risk/fraud/support nội bộ không được xuất hiện. Kiểm tra response ở:

- Detail endpoint và list endpoint.
- Search result, autocomplete, count, aggregate và report.
- Nested object, embedded relation và error response.
- Download metadata, export CSV/PDF và file preview.
- GraphQL selection/resolver và endpoint version cũ.
- Cache hit và response được phục vụ từ CDN/API gateway.

So sánh response theo role nhưng dựa trên contract đã duyệt. Không yêu cầu mọi role phải có response khác nhau; chỉ những field có policy khác mới cần kiểm tra. Dùng schema allowlist/DTO cụ thể để xác định field được phép trả thay vì serialize trực tiếp entity chứa toàn bộ cột database.

## 11. Kiểm thử mass assignment và field update

Với BOPLA ở chiều ghi, xác định field nào caller được cập nhật rồi gửi thêm field ngoài allowlist. Test phải đọc lại object từ database để xác minh server không thay đổi field cấm.

Ví dụ customer chỉ được sửa `displayName`:

```http
PATCH /api/profile/profile-A HTTP/1.1
Authorization: Bearer <alice-test-token>
Content-Type: application/json

{
  "displayName": "Alice Updated",
  "role": "ADMIN",
  "tenantId": "tenant-blue",
  "isAdmin": true,
  "approvedBy": "alice",
  "internalRiskScore": 0
}
```

Kết quả hợp lệ có thể là từ chối toàn bộ request hoặc chỉ cập nhật field được phép, tùy contract. Dù chọn cách nào, `role`, `tenantId`, `isAdmin`, `approvedBy` và `internalRiskScore` không được thay đổi. Nếu API bỏ qua field lạ, hành vi đó cần được định nghĩa và test rõ; không được âm thầm bind vào entity.

Kiểm tra các dạng input:

- `POST`, `PUT`, `PATCH` và nested update.
- Field bị bỏ qua, `null`, empty string, giá trị mặc định và kiểu dữ liệu khác.
- Case variation hoặc alias của field nếu serializer hỗ trợ.
- Array/map động, JSON merge patch và form/multipart fields.
- Field được gửi trong cả path/header lẫn body với giá trị mâu thuẫn.
- Field server-owned được gửi trong request tạo mới lẫn request cập nhật.

Đặc biệt, kiểm tra cập nhật một phần có atomic không. Nếu server thay đổi `displayName` rồi lỗi khi xử lý `tenantId`, dữ liệu có thể đã bị cập nhật một phần. Assertion phải xem toàn bộ object state và audit/outbox records.

## 12. Kiểm tra field authorization trong API list, bulk và search

Một endpoint detail có thể trả DTO an toàn trong khi list endpoint dùng projection rộng hoặc search index chứa field nội bộ. Kiểm thử cùng object qua nhiều đường truy cập:

| API path | Rủi ro cần kiểm tra |
|---|---|
| `GET /resources/{id}` | Field nhạy cảm trong detail response. |
| `GET /resources` | Field thừa trong list item hoặc metadata. |
| `GET /search?q=...` | Snippet/highlight chứa field không được phép. |
| `GET /resources/{id}/history` | Snapshot cũ chứa field trước khi policy thay đổi. |
| `POST /resources/export` | CSV/PDF export có thể dùng serializer khác. |
| `POST /resources/bulk-update` | Một số item được cập nhật dù caller không có quyền. |
| `GET /resources?include=...` | Caller yêu cầu relation hoặc field expansion ngoài quyền. |

Kiểm tra count, facet, sort và filter. Dù response không trả object, API có thể tiết lộ giá trị field nhạy cảm qua số lượng record hoặc khả năng lọc theo một thuộc tính bí mật. Không cho phép query tùy ý trên field restricted chỉ vì field không xuất hiện trong JSON response.

## 13. GraphQL, RPC và các giao thức khác

Authorization phải nhất quán ở mọi giao thức truy cập cùng dữ liệu. REST endpoint có thể kiểm tra owner trong service nhưng GraphQL resolver hoặc gRPC method lại truy vấn repository trực tiếp.

Với GraphQL, kiểm tra:

- Node/object lookup theo global ID có áp object authorization không?
- Nested resolver có tái kiểm tra quyền trên child object không?
- Field resolver có ẩn field restricted theo principal không?
- Mutation có kiểm tra object và property trước khi ghi không?
- Batch/DataLoader có vô tình trộn dữ liệu giữa tenant hoặc principal không?

Với RPC/message API, kiểm tra resource ID, tenant context, caller service identity và authorization khi consumer xử lý. Không tin tenant/owner trong message payload nếu producer không được xác thực và mapping chưa được xác minh. Test cả retry và replay của message vì job có thể chạy trong context khác request gốc.

## 14. File, export, cache và signed URL

File API và export thường có object ID riêng, storage key và URL tạm. Đánh giá cả thời điểm cấp capability lẫn thời điểm sử dụng.

- User A không thể yêu cầu metadata/download của file B bằng cách thay `fileId`.
- Export job ID của tenant khác không thể được tải xuống.
- Signed URL chỉ trỏ đúng object, method và thời hạn đã cấp; không được tạo trước khi authorization thành công.
- Nếu business policy yêu cầu quyền phải được kiểm tra ở mỗi lần tải, không dùng URL có thời hạn quá dài hoặc capability vượt scope.
- Cache key phải tách theo principal/tenant hoặc response riêng tư không được shared-cache.
- File preview/thumbnail và derivative object phải có policy tương đương file gốc.

Khi test signed URL, dùng object giả và URL được tạo trong môi trường test. Không ghi URL có query credential vào evidence hoặc ticket; lưu file ID, thời điểm cấp, scope và trạng thái đã redacted.

## 15. Kiểm tra HTTP response và side channel

Status code không đủ để kết luận. Một endpoint có thể trả `404` nhưng vẫn tiết lộ object qua `Content-Length`, `ETag`, timing, count hoặc response header. Ngược lại, `403` có thể là kết quả đúng nhưng vẫn cần xác minh không có side effect.

Kiểm tra:

- Response body, field, header, content type và redirect.
- Error message có tiết lộ object existence, owner, tenant hoặc dữ liệu không?
- `Location`, download URL, pagination cursor hoặc export reference có thể dùng để lấy object khác không?
- `ETag`, cache status, content length và response timing có khác biệt quá rõ giữa object tồn tại và không tồn tại không?
- Request bị deny có tạo database write, event, notification, audit action nghiệp vụ hoặc downstream call không?
- Error handler có vô tình serialize entity trước khi chuyển thành lỗi không?

Không phải mọi khác biệt timing nhỏ đều là vulnerability. Ghi nhận khi có tín hiệu có thể lặp lại, gắn với dữ liệu nhạy cảm và có cách khai thác thực tế. Ưu tiên xác minh bằng response/data evidence thay vì suy luận từ một lần đo thời gian.

## 16. Tự động hóa bằng test case và differential comparison

Có thể tổ chức test data theo một bảng principal-object-property-action để chạy lặp trên nhiều endpoint. Ví dụ:

```yaml
principals:
  alice:
    role: CUSTOMER
    tenant: tenant-red
  bob:
    role: CUSTOMER
    tenant: tenant-red
  carol:
    role: CUSTOMER
    tenant: tenant-blue
objects:
  order-A1:
    owner: alice
    tenant: tenant-red
  order-A2:
    owner: bob
    tenant: tenant-red
  order-B1:
    owner: carol
    tenant: tenant-blue
checks:
  - principal: alice
    action: order.read
    object: order-A1
    expected: allow
  - principal: alice
    action: order.read
    object: order-A2
    expected: deny
  - principal: alice
    action: order.read
    object: order-B1
    expected: deny
```

Đây là fixture minh họa; dữ liệu thực tế cần được tạo bởi test harness và token issuer của môi trường test. Không đưa token thật vào YAML/CI artifact.

Differential testing có thể so sánh:

1. Response của owner với response của non-owner trên cùng object.
2. Response của customer với support/admin trên cùng object.
3. Response detail với list/search/export của cùng principal.
4. Object state trước và sau request bị deny.
5. Output schema với allowlist field theo role.

Tự động hóa nên dựa trên expected policy, không chỉ tìm chuỗi như `password` hoặc so sánh response byte-for-byte. Dynamic field như timestamp, pagination cursor và trace ID cần được chuẩn hóa trước khi diff. Mọi khác biệt bất thường cần review để phân biệt lỗi thật với behavior được contract cho phép.

## 17. Ví dụ kiểm thử với Spring MockMvc

Ví dụ dưới đây minh họa kiểm tra một customer không thể đọc order của customer khác và không thể mass-assign field đặc quyền. Test fixture, JWT converter và repository phải khớp cấu hình thật của ứng dụng.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationAssessmentTest {
    @Autowired MockMvc mvc;
    @Autowired OrderRepository orders;
    @Autowired ProfileRepository profileRepository;

    @Test
    void customerCannotReadAnotherCustomersOrder() throws Exception {
        TestOrders data = createAliceAndBobOrders();

        mvc.perform(get("/api/orders/{id}", data.bobOrderId())
                .with(jwt().jwt(jwt -> jwt
                    .subject(data.aliceId().toString())
                    .claim("tenant_id", data.tenantRed().toString())
                    .claim("roles", List.of("CUSTOMER")))))
            .andExpect(status().isForbidden());

        assertThat(orders.findById(data.bobOrderId()))
            .isPresent();
    }

    @Test
    void customerCannotChangeServerOwnedProperties() throws Exception {
        TestProfile data = createAliceProfile();

        mvc.perform(patch("/api/profiles/{id}", data.profileId())
                .with(jwt().jwt(jwt -> jwt
                    .subject(data.aliceId().toString())
                    .claim("tenant_id", data.tenantRed().toString())
                    .claim("roles", List.of("CUSTOMER"))))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "Alice Updated",
                      "role": "ADMIN",
                      "tenantId": "tenant-blue",
                      "isAdmin": true
                    }
                    """))
            .andExpect(status().isBadRequest());

        Profile saved = profileRepository.findById(data.profileId())
            .orElseThrow();
        assertThat(saved.getDisplayName()).isEqualTo("Alice");
        assertThat(saved.getRole()).isEqualTo("CUSTOMER");
        assertThat(saved.getTenantId()).isEqualTo(data.tenantRed());
        assertThat(saved.isAdmin()).isFalse();
    }
}
```

Đây là ví dụ cấu trúc, cần bổ sung import, fixture helpers và repository phù hợp. API có thể chọn bỏ qua field không được phép thay vì trả `400`; khi đó assertion phải theo contract, nhưng các field server-owned vẫn phải giữ nguyên. Trong test BOLA, status có thể là `404` nếu API che giấu object. Assertion quan trọng là dữ liệu Bob không bị trả cho Alice và không có side effect.

## 18. Thu thập bằng chứng và viết finding

Một finding tốt cho phép developer tái hiện lỗi mà không cần token hoặc dữ liệu nhạy cảm của người kiểm thử. Ghi các thành phần:

| Thành phần | Nội dung |
|---|---|
| Finding title | Ví dụ: `BOLA: customer đọc được order của user khác`. |
| Affected endpoint | Method, route template, API version và environment. |
| Principal | Test account/role/tenant; không lưu raw token. |
| Object relationship | Owner/tenant dự kiến và object được tham chiếu. |
| Expected policy | Vì sao principal phải bị deny hoặc chỉ được đọc một số field. |
| Reproduction | Request đã redacted, các bước tối thiểu và test data IDs. |
| Actual result | Status, field/side effect quan sát được và correlation ID. |
| Impact | Confidentiality, integrity, tenant scope, số object/role bị ảnh hưởng. |
| Evidence | Response đã redacted, state diff, audit/event record và thời điểm. |
| Remediation | Kiểm tra object relationship/property allowlist ở server. |
| Retest | Test case chứng minh lỗi đã được sửa và regression được thêm vào CI. |

Không đính kèm access token, cookie, API key, dữ liệu cá nhân thật hoặc toàn bộ production response vào ticket. Nếu cần chứng minh field nhạy cảm, dùng test value giả hoặc che nội dung nhưng giữ tên field và bằng chứng policy. Lưu evidence trong nơi có access control và retention phù hợp.

## 19. Đánh giá mức độ ảnh hưởng

Severity phụ thuộc vào dữ liệu, hành động và phạm vi có thể truy cập, không chỉ loại lỗi hoặc HTTP status.

- **Confidentiality:** có thể đọc PII, tài chính, secret, dữ liệu nội bộ hoặc file của người khác không?
- **Integrity:** có thể đổi owner, tenant, role, payment state, approval hoặc nội dung object không?
- **Privilege:** principal thường có thể thực hiện chức năng admin/support/service không?
- **Scope:** ảnh hưởng một object, một user, một tenant hay nhiều tenant?
- **Scale:** có thể khai thác qua list, bulk, export, pagination hoặc automation không?
- **Exploitability:** cần token hợp lệ, role đặc biệt, object ID đã biết hay chỉ cần user thường?
- **Business impact:** có thể gây mất tiền, thay đổi quyền, gián đoạn nghiệp vụ hoặc vi phạm nghĩa vụ dữ liệu không?

Một BOLA đọc invoice của tenant khác có thể có mức độ nghiêm trọng cao vì rò dữ liệu chéo khách hàng. Một BOPLA cho phép user đổi `isAdmin` có thể dẫn đến privilege escalation và thường nghiêm trọng hơn việc một field không nhạy cảm bị trả dư. Ghi rõ điều kiện khai thác và giới hạn đã xác minh; không suy rộng impact vượt quá evidence.

## 20. Remediation và retest

Các biện pháp sửa lỗi cần được áp dụng ở server-side boundary:

- Lấy principal/tenant từ authentication context đã xác minh, không tin ID/role/tenant do client gửi.
- Truy vấn object theo tenant/scope phù hợp và kiểm tra ownership/relationship cho từng action.
- Dùng policy service hoặc authorization check tập trung nhưng bảo đảm mọi route, resolver, job và download đều gọi đúng policy.
- Dùng request DTO với allowlist field; không bind trực tiếp request vào entity/domain object.
- Dùng response DTO/projection chỉ chứa field được phép đọc.
- Kiểm tra nested object và từng item trong bulk request.
- Đặt authorization trước side effect; dùng transaction để request bị deny không ghi một phần dữ liệu.
- Tách cache theo principal/tenant hoặc không cache response nhạy cảm trong shared cache.
- Kiểm tra quyền trước khi tạo signed URL và giới hạn object/method/TTL.
- Thêm regression tests cho cùng tenant, cross-tenant, role, property và side effect.

Retest phải chạy lại đúng reproduction steps, sau đó mở rộng sang các endpoint có cùng code path/DTO/repository method. Không chỉ kiểm tra status đã đổi từ `200` sang `403`; xác minh response không còn field/object ngoài quyền, database không đổi, event/downstream không chạy và các luồng list/export/file cũng được bảo vệ.

## 21. Những sai lầm khi đánh giá BOLA/BOPLA

| Sai lầm | Vì sao không đủ | Cách làm đúng |
|---|---|---|
| Chỉ thay ID ở một GET | Bỏ sót update, delete, action, nested resource và bulk. | Lập bản đồ mọi operation dùng object reference. |
| Chỉ thử user khác tenant | Bỏ sót user khác trong cùng tenant. | Có same-tenant non-owner và cross-tenant principal. |
| Dùng UUID khó đoán làm kết luận | ID có thể lộ từ URL, log, event hoặc relation. | Kiểm tra authorization bất kể ID format. |
| Chỉ xem status code | Có thể lộ field qua response hoặc đã tạo side effect. | Kiểm tra body, headers, DB, events và downstream. |
| Chỉ thử field `role` | Bỏ sót tenant, owner, approval, payment và nested fields. | Dựa trên property inventory và server-owned field list. |
| Chỉ xem detail response | List/export/search có thể dùng serializer khác. | Differential test trên mọi response path. |
| Test bằng mock hoàn toàn | Không xác minh query tenant và persistence thật. | Bổ sung integration test với database và filter chain. |
| Thử trên production data tùy tiện | Có thể lộ dữ liệu hoặc tạo tác động không thể đảo ngược. | Dùng test identities, fixture và sandbox có scope. |
| Chấp nhận 404 là đủ | Metadata, timing hoặc side effect vẫn có thể rò. | Kiểm tra mọi observable output và state. |
| Sửa một controller nhưng bỏ qua worker | Background path có thể vẫn thiếu authorization. | Theo dõi object policy xuyên suốt lifecycle. |

## 22. Checklist assessment BOLA và broken property authorization

- [ ] Scope, environment, test identities và dữ liệu thử nghiệm được phê duyệt?
- [ ] Có ít nhất hai user cùng tenant và principal ở tenant khác?
- [ ] Đã lập bản đồ object reference ở path, query, body, header, nested, bulk, GraphQL và job?
- [ ] Đã xác định owner, tenant, relationship và action policy cho từng object?
- [ ] Đã thử object substitution trên read, update, delete, approve, download và export?
- [ ] Đã thử same-tenant non-owner và cross-tenant access?
- [ ] Đã kiểm tra nested object/child reference và quan hệ parent-child?
- [ ] Đã lập danh sách field public, restricted, writable và server-owned?
- [ ] Đã kiểm tra excessive data exposure trên detail, list, search, history và export?
- [ ] Đã thử mass assignment với role, tenant, owner, approval và business state fields?
- [ ] Đã đọc lại database để xác minh field cấm không thay đổi?
- [ ] Đã xác minh denied request không tạo event, notification hoặc downstream side effect?
- [ ] Đã kiểm tra cache, pagination, bulk, file, signed URL và background worker?
- [ ] Evidence đã redacted, có expected policy, actual result và correlation ID?
- [ ] Finding có impact được giới hạn theo evidence và remediation cụ thể?
- [ ] Retest bao gồm regression trên các endpoint dùng chung code path?

Đánh giá BOLA và BOPLA cần kiểm tra đồng thời quyền trên object và quyền trên từng thuộc tính. Dùng principal/object fixture có quan hệ rõ, thay object reference có kiểm soát, so sánh response theo role, thử field ngoài allowlist và xác minh trạng thái lưu trữ cùng side effect. Khi evidence cho thấy caller đọc hoặc thay đổi dữ liệu ngoài quyền, ghi finding có thể tái hiện, sửa authorization ở server-side boundary và retest mọi đường truy cập liên quan. Một endpoint chỉ được xem là đạt khi cả object scope lẫn property scope đều được thực thi nhất quán.
