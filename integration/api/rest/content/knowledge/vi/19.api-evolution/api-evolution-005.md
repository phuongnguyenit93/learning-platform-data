# Quản lý đồng thời nhiều phiên bản bằng hợp đồng riêng

## 1. Mục tiêu và tình huống thực tế

Trong module **INTEGRATION_API_REST**, một API đúng về resource, URI, phương thức, status HTTP và hợp đồng dữ liệu vẫn cần **ổn định đối với ứng dụng đã tích hợp**. Khi sản phẩm thay đổi một điều mà client cũ không thể hiểu, cần duy trì **v1 và v2 đồng thời**, mỗi phiên bản có hợp đồng công khai riêng, thay vì sửa response v1 rồi hy vọng mọi client cập nhật kịp.

**Tình huống:** ứng dụng mobile cũ gọi **GET /api/v1/orders/{id}**, nhận trường **totalAmountVnd** kiểu integer và trạng thái **NEW**. Phiên bản mới muốn trả tiền bằng object **total: {amountMinor, currency}** và dùng trạng thái **PENDING**. Thay đổi trực tiếp trong v1 sẽ làm SDK cũ parse lỗi hoặc tính tiền sai.

Sau bài này bạn có thể:

- Phân biệt version API, version tài liệu, version triển khai và ETag của resource.
- Quản lý **hai OpenAPI contract riêng**, gồm schema, lỗi, security và hành vi HTTP.
- Chọn định tuyến theo URI/header/media type, hiểu ảnh hưởng của cache và redirect.
- Thiết kế controller/DTO/mapper v1-v2 ở Spring nhưng dùng chung domain service.
- Đảm bảo quyền tenant, idempotency, optimistic locking, dữ liệu và quota xuyên phiên bản.
- Thực hiện migration, deprecation/sunset, contract tests và kiểm thử client cũ.

**Mục tiêu không phải fork hai codebase mãi mãi**, mà là tách ranh giới hợp đồng khi cần, đo mức sử dụng và loại bỏ version cũ theo một lộ trình có chủ sở hữu.

## 2. Có nhiều loại “version”: đừng nhầm

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Public API major version** | /api/**v1**/orders | Hợp đồng công khai mà client chọn |
| **OpenAPI document version** | info.version: **1.8.2** | Lần chỉnh sửa tài liệu của v1 |
| **Server build/release** | build **2026.11.18** | Phần mềm đang triển khai |
| **Resource version/ETag** | ETag: **"order-17-r9"** | Validator cho conditional GET và If-Match |
| **Database schema version** | migration **V42** | Cấu trúc lưu trữ |
| **Event schema version** | OrderCreated.v2 | Hợp đồng message/event riêng |

Một lần triển khai có thể phục vụ **cả v1 và v2**; một DB migration không tự buộc API tăng public version. Cũng không được dùng ETag thay cho định danh API v2: **ETag nói về trạng thái biểu diễn**, không nói client nên dùng schema request/response nào.

**Khi nào thực sự cần version mới?** Khi một thay đổi về field, enum, default, error, auth, pagination, URI/method hay thời điểm hoàn thành request không thể được client hiện hữu tiếp nhận an toàn. Một thay đổi additive có thể giữ trong v1 nếu đã chứng minh tương thích, không cần tạo v2 cho mọi sửa nhỏ.

## 3. “Hợp đồng riêng” phải độc lập ở những đâu?

Mỗi version cần được mô tả và kiểm chứng như một sản phẩm giao tiếp:

- **URI, method, requestBody, response, status và headers** của chính version đó.
- **Object/array/enum/required/null/default**, pagination và error contract.
- **Authorization scopes, tenant policy, rate limit**, cache và idempotency behavior.
- **Ví dụ request/response**, SDK hỗ trợ, changelog và test suite độc lập.
- **Thời gian hỗ trợ**, hướng dẫn migration và điều kiện sunset.

Một bố cục **minh họa** cho tài liệu/CI:

~~~text
contracts/
  orders-v1/openapi.yaml
  orders-v1/contract-tests/
  orders-v2/openapi.yaml
  orders-v2/contract-tests/
~~~

Hợp đồng v1 có thể nhận một bản vá lỗi hoặc field optional mới nếu không phá client. Nhưng thay đổi **shared schema** phải được review theo cả hai contract: một đổi tên trong DTO chung không được âm thầm biến output v1 thành v2.

**Chống mẫu:** một class OrderResponse được tái sử dụng cho tất cả controller; khi nhóm v2 đổi trường tiền và enum, /api/v1 cũng trả kiểu mới. Giải pháp là **DTO/mapper riêng ở HTTP boundary**; domain/DB vẫn có thể dùng chung.

## 4. Cùng một Order nhưng hai representation

Đơn hàng có ID **11111111-1111-4111-8111-111111111111**, tổng **150.000 VND**, đang chờ xử lý.

### 4.1. Hợp đồng v1

~~~http
GET /api/v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "NEW",
  "totalAmountVnd": 150000
}
~~~

V1 chỉ biết trạng thái **NEW/PAID/CANCELLED** và tổng tiền integer theo đơn vị **VND**.

### 4.2. Hợp đồng v2

~~~http
GET /api/v2/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "PENDING",
  "total": {
    "amountMinor": 150000,
    "currency": "VND"
  }
}
~~~

Hai response có thể xuất phát từ **cùng một Order aggregate trong CSDL**, không phải hai bản sao độc lập vì URL có tiền tố khác nhau.

**Ranh giới tương thích:** nếu sau này v2 cho phép USD nhưng v1 chỉ biết VND, không được xuất USD dưới tên totalAmountVnd hoặc tự đổi nghĩa status. Phải có **capability gate/compatibility policy** khi v1 còn được hỗ trợ, hoặc hoàn tất migration trước khi phát hành dữ liệu mà v1 không thể biểu diễn trung thực.

### 4.3. Với operation ghi

Ví dụ v2 yêu cầu **shippingMethod** khi POST tạo đơn, còn v1 chưa có trường đó. Nếu vẫn hỗ trợ v1, domain cần giữ ngữ nghĩa v1 (ví dụ default **STANDARD** nếu nghiệp vụ cho phép), **không được dùng v2 DTO để bắt request v1 gửi field mới**. Mỗi operation ghi cũng phải có schema và validation độc lập.

## 5. Hai OpenAPI 3.1 tách biệt

### 5.1. Hợp đồng GET v1

~~~yaml
openapi: 3.1.0
info:
  title: Orders API v1
  version: 1.8.2
paths:
  /api/v1/orders/{orderId}:
    get:
      operationId: getOrderV1
      summary: Đọc order theo hợp đồng v1
      security:
        - bearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Biểu diễn v1 được phân quyền
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderV1'
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '404':
          description: Không có order trong phạm vi được phép
components:
  schemas:
    OrderV1:
      type: object
      required: [id, status, totalAmountVnd]
      additionalProperties: false
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [NEW, PAID, CANCELLED]
        totalAmountVnd:
          type: integer
          minimum: 0
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

### 5.2. Hợp đồng GET v2

~~~yaml
openapi: 3.1.0
info:
  title: Orders API v2
  version: 2.1.0
paths:
  /api/v2/orders/{orderId}:
    get:
      operationId: getOrderV2
      summary: Đọc order theo hợp đồng v2
      security:
        - bearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Biểu diễn v2 được phân quyền
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderV2'
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '404':
          description: Không có order trong phạm vi được phép
components:
  schemas:
    Money:
      type: object
      required: [amountMinor, currency]
      additionalProperties: false
      properties:
        amountMinor:
          type: integer
          minimum: 0
        currency:
          type: string
          enum: [VND]
    OrderV2:
      type: object
      required: [id, status, total]
      additionalProperties: false
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [PENDING, PAID, CANCELLED]
        total:
          $ref: '#/components/schemas/Money'
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

**Đọc đúng:** **openapi: 3.1.0** là phiên bản tiêu chuẩn; **info.version: 1.8.2/2.1.0** là version tài liệu/sản phẩm; **/api/v1** và **/api/v2** là major version trong public URI.

Hai OpenAPI ở đây chỉ minh họa operation GET; hệ thống thật phải khai báo POST/PUT/PATCH/DELETE, error schema theo **RFC 9457**, headers, scope, cache, pagination và ví dụ cho mỗi contract. Nếu v1 bắt đầu bị deprecate, đặt **deprecated: true** tại operation tương ứng; cờ đó không tự ngừng route.

## 6. Ma trận thay đổi tương thích

| Thay đổi | Có nguy cơ breaking? | Khuyến nghị |
| --- | --- | --- |
| Thêm optional field vào request, default cũ giữ | Thường thấp | Có thể giữ v1 sau khi test |
| Thêm required request field | Cao | Contract mới hoặc migration rõ |
| Đổi tên/kiểu field response | Cao | Tách v2 |
| Thêm response field | Thường thấp, nhưng client strict có thể lỗi | Test SDK thực |
| Thêm giá trị enum response | Có, SDK enum đóng dễ lỗi | Contract review/feature gate |
| Optional → required | Cao | Không áp âm thầm vào v1 |
| Response non-null → nullable | Cao | Đánh giá client/SDK |
| Tiền số nguyên → Money object | Cao | Tách DTO và hợp đồng |
| Page/size → cursor | Cao với client cũ | Tách endpoint/version |
| 200 đồng bộ → 202 async | Có, đổi thời điểm hoàn tất | Hợp đồng mới |
| Đổi status hoặc error type | Có, client retry/error handling có thể sai | Contract tests |
| Bổ sung scope auth bắt buộc | Có, có thể khiến client bị 403 | Migration credential/quyền |

**Breaking phụ thuộc hành vi consumer**, không chỉ việc JSON “có thêm trường”. Nếu một client cũ deserializer enum đóng, việc thêm trạng thái mới có thể gây lỗi dù validator schema mới chấp nhận.

**Bản vá bảo mật vẫn phải đến v1** trong thời gian v1 còn được hỗ trợ. Tính ổn định không có nghĩa giữ nguyên một lỗ hổng IDOR/rate-limit chỉ vì nó là “hành vi cũ”.

## 7. Routing phiên bản: URL, header hay media type?

| Phương án | Ví dụ | Ưu điểm | Cần quản lý |
| --- | --- | --- | --- |
| **URI path** | /api/**v2**/orders | Dễ debug, cache/log phân biệt rõ | Client/link phải đổi URI |
| **Custom header** | X-Api-Version: 2 | URI không đổi | Cache key, gateway, SDK |
| **Media type** | Accept: application/vnd.example.orders.v2+json | Gắn version với representation | Vary: Accept, 406/415, tooling |
| **Hostname** | v2.api.example.test | Tách hạ tầng/cert/policy | DNS, TLS, client config |

Ví dụ bài chọn **URI path** vì dễ kiểm thử và tài liệu hóa. Với version nằm trong **Accept**, response phải được cache/route theo **Accept** (chẳng hạn **Vary: Accept**); với custom header, cache key phải gồm chiều lựa chọn tương ứng. Không sử dụng chung cached body v1/v2 hoặc lộ dữ liệu cá nhân khi đổi version.

**Không fallback âm thầm** request /api/v3 sang v2: client phải biết mình nhận hợp đồng nào. Cũng không dùng 307/308 để **tự động chuyển POST/PUT** v1 sang v2 khi schema payload đã khác nhau: redirect có thể giữ method/body nhưng **không chuyển đổi ngữ nghĩa JSON**. Với content negotiation, **406 Not Acceptable** và **415 Unsupported Media Type** chỉ dùng khi ngữ nghĩa media type tương ứng đúng, không phải status chung cho mọi lỗi version.

## 8. Kiến trúc: adapter theo contract, domain dùng chung

~~~mermaid
flowchart TD
    C1[Client v1] --> V1[Controller/DTO v1]
    C2[Client v2] --> V2[Controller/DTO v2]
    V1 --> S[Shared domain service]
    V2 --> S
    S --> AUTH[Authorization + business rules]
    AUTH --> DB[(Canonical Order DB)]
~~~

**Nên tách:** request/response DTO, schema validation, enum mapping, default khác nhau và error representation ở biên HTTP.

**Có thể dùng chung:** domain model, business invariants, transaction, quyền dữ liệu thực chất, lưu trữ, audit và outbox. Nếu mỗi version cần lifecycle độc lập, gateway có thể route tới hai deployment khác nhau; nhưng hai server vẫn phải giữ transaction và contract dữ liệu nhất quán.

**Không đồng nhất** “hợp đồng riêng” với “database riêng”. Nếu v1/v2 cùng quản lý một Order, tạo hai bản ghi nguồn sự thật độc lập gây khó reconciliation và double-processing.

## 9. Java/Spring Boot: DTO và controller versioned

Ví dụ Java 17+, Spring Boot 3. Các thành phần **OrderAggregate** và **OrderQueryService** là abstraction của ứng dụng, còn imports/security/exception handlers được lược bỏ. Hai controller có thể ở **hai file Java riêng**.

### 9.1. DTO và mapper

~~~java
public enum OrderStatus { PENDING, PAID, CANCELLED }

public record OrderV1Dto(
        UUID id, String status, long totalAmountVnd) {}

public record MoneyV2Dto(long amountMinor, String currency) {}

public record OrderV2Dto(
        UUID id, String status, MoneyV2Dto total) {}

public final class OrderContractMappers {
    private OrderContractMappers() {}

    public static OrderV1Dto toV1(OrderAggregate order) {
        // V1 chỉ diễn tả VND. Đây là invariant do domain bảo đảm.
        if (!"VND".equals(order.currency())) {
            throw new IllegalStateException(
                "Cannot represent order with v1 contract");
        }
        String oldStatus = switch (order.status()) {
            case PENDING -> "NEW";
            case PAID -> "PAID";
            case CANCELLED -> "CANCELLED";
        };
        return new OrderV1Dto(
                order.id(), oldStatus, order.totalAmountMinor());
    }

    public static OrderV2Dto toV2(OrderAggregate order) {
        return new OrderV2Dto(
                order.id(), order.status().name(),
                new MoneyV2Dto(
                    order.totalAmountMinor(), order.currency()));
    }
}
~~~

**Không dùng IllegalStateException như policy production:** mã trên chỉ làm lộ giả định. Khi v1 còn phục vụ, hãy **gate** dữ liệu không tương thích hoặc cung cấp quy tắc xử lý đã thiết kế, không lặng lẽ gán USD vào totalAmountVnd.

### 9.2. Hai controller cùng gọi domain service

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderV1Controller {
    private final OrderQueryService orders;

    public OrderV1Controller(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderV1Dto> get(
            @PathVariable UUID id, Authentication principal) {

        OrderAggregate domain = orders.requireReadable(id, principal);
        return ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
            .body(OrderContractMappers.toV1(domain));
    }
}

@RestController
@RequestMapping("/api/v2/orders")
public class OrderV2Controller {
    private final OrderQueryService orders;

    public OrderV2Controller(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderV2Dto> get(
            @PathVariable UUID id, Authentication principal) {

        OrderAggregate domain = orders.requireReadable(id, principal);
        return ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
            .body(OrderContractMappers.toV2(domain));
    }
}
~~~

**requireReadable** phải kiểm tra principal, tenant, membership và quyền trên Order trước khi trả dữ liệu. Cả v1/v2 phải dùng chung quy tắc phân quyền thực chất; khác representation **không** có nghĩa cho phép bỏ kiểm tra ở v1.

Nếu v1 dùng mã lỗi riêng **ORDER_NOT_FOUND** còn v2 dùng **RFC 9457 Problem Details**, hai HTTP error mapper có thể nhận cùng một domain exception. Tuy nhiên, status 401, 403, 404, 409, 412 cần giữ đúng ngữ nghĩa.

## 10. Khi cả hai phiên bản đều ghi

Tách contract chỉ bảo vệ hình dạng JSON. Nếu cùng sửa CSDL, còn phải bảo vệ **ý định nghiệp vụ và tính nguyên tử**.

### 10.1. Default không làm hỏng client cũ

V2 POST yêu cầu **shippingMethod**; v1 không có. Nếu hợp đồng v1 tương đương **STANDARD**, adapter v1 có thể truyền default đó vào domain service. Không đổi v1 thành 400 “thiếu shippingMethod” chỉ vì reuse v2 DTO.

### 10.2. Idempotency-Key xuyên version

POST không mặc định idempotent. Client có thể timeout rồi gửi lại qua SDK khác:

- Scope key theo **tenant/account, operation, version contract, fingerprint, key và TTL**; không trả raw cached JSON v2 cho v1 vì trùng key.
- Nếu cùng một ý định được retry **qua hai version**, dùng **business operation ID/unique constraint** chung để chống tạo hai đơn hoặc hai khoản thanh toán.
- Khi outcome không rõ sau timeout, cho phép tra cứu resource/operation thay vì tạo lại vô điều kiện.

### 10.3. Concurrency và event

Nếu v1 và v2 cùng PUT/PATCH một Order, ETag có thể khác theo representation nhưng **If-Match phải ánh xạ an toàn vào revision chung**. Tầng dữ liệu cần optimistic lock/version trong transaction để không lost update. Một mutation nên tạo **một outbox event**, không phải hai event do có hai HTTP adapter. Version schema của event là hợp đồng riêng.

## 11. Bảo mật, quota và caching xuyên phiên bản

| Rủi ro | Kiểm soát |
| --- | --- |
| V1 bypass authentication | Security filter/gateway rule bao phủ cả v1 và v2 |
| BOLA/IDOR | Domain query kiểm tra tenant/owner/role, không tin tenantId client gửi |
| Scope lỏng ở v1 | Cập nhật security policy trong mọi version còn hỗ trợ |
| Mass assignment | DTO request riêng, không bind thẳng entity hoặc trường server-managed |
| Quota bypass | Giới hạn tổng operations theo tenant/account, không chỉ mỗi prefix |
| Cache lẫn representation | Cache key chứa URI/version/variant và phân quyền khi được phép lưu |
| Dữ liệu nhạy cảm | Chính sách private/no-store phù hợp, không phát token/PII vào logs |
| CORS/WAF/CSRF | Không bảo vệ v2 mà bỏ quên route legacy |
| Đổi quyền giữa requests | Kiểm tra quyền hiện tại thay vì tin ETag hoặc cache cũ |

Với example đơn hàng riêng, chọn **Cache-Control: private, no-store** ở cả hai controller. Nếu version nằm trong **Accept** hay header tự định nghĩa, cache key/Vary phải phân biệt biến thể tương ứng; shared cache không được lộ response v1/v2 của người khác.

**V1 còn được phục vụ thì v1 vẫn phải được vá lỗ hổng.** Sunset sắp tới không phải lý do bỏ qua IDOR, SQL injection hay rate limiting.

## 12. Data migration: expand–migrate–contract

Khi đổi từ **total_amount_vnd** sang **amount_minor + currency** ở DB, đừng xóa cột cũ ngay trong lần phát hành v2 nếu v1/background job vẫn phụ thuộc.

1. **Expand:** thêm schema mới theo cách cho đường đọc/ghi cũ còn hoạt động.
2. **Backfill:** chuyển dữ liệu, kiểm tra precision, số lượng record và trường hợp bất thường.
3. **Adapt:** domain chuyển sang canonical model; mapper v1/v2 đọc cùng nguồn đã thống nhất. Nếu cần dual-write, phải bảo vệ consistency và thứ tự update.
4. **Cutover:** bật đọc/ghi mới qua canary, theo dõi sai lệch và thử rollback.
5. **Contract:** xóa cấu trúc cũ khi đã chắc chắn không còn consumer hoặc job dùng nó.

~~~mermaid
flowchart LR
    V1[Adapter v1] --> D[Domain service]
    V2[Adapter v2] --> D
    D --> DB[(Expanded DB schema)]
    DB --> B[Backfill + verification]
~~~

**Rollback code v2 không tự rollback dữ liệu v2.** Nếu v2 đã tạo order bằng tiền tệ/trạng thái mà v1 không diễn tả, cần capability gate trong giai đoạn chuyển tiếp hoặc một chiến lược forward-only an toàn. Không biến một currency mới thành VND bằng cách đổi nhãn.

## 13. Phát hành, Deprecation và Sunset

| Giai đoạn | Hoạt động | Điều kiện qua cổng |
| --- | --- | --- |
| **Review** | Chốt OpenAPI v1/v2, compatibility diff, migration guide | Consumer/provider review đạt |
| **Dual-run** | Chạy v1/v2 song song | Regression v1 + contract v2 đều đạt |
| **Pilot** | Client/tenant chủ động chọn v2 | Latency, lỗi và dữ liệu đúng |
| **Rollout** | Mở rộng opt-in v2 | Có metrics, rollback và capability gates |
| **Deprecation** | Công bố lịch, hỗ trợ SDK và migration | Biết consumer nào còn dùng v1 |
| **Sunset** | Ngừng hỗ trợ theo quyết định công khai | Consumer thiết yếu đã chuyển/được xử lý |

Có thể **shadow GET** để so dữ liệu trong môi trường cách ly, nhưng phải kiểm soát dữ liệu cá nhân và quota. **Không shadow POST/PUT/PATCH/DELETE như lệnh thật**: có thể tạo giao dịch trùng. Canary không được tự đổi URL/method của client nếu client chưa chấp nhận contract v2.

### 13.1. Các HTTP headers thông báo lifecycle

Ví dụ response v1 với thời điểm **minh họa**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1798761600
Sunset: Fri, 31 Dec 2027 23:59:59 GMT
Link: <https://docs.example.test/migrate/orders-v2>; rel="deprecation"
Cache-Control: private, no-store

{"id":"11111111-1111-4111-8111-111111111111","status":"NEW","totalAmountVnd":150000}
~~~

- **RFC 9745** định nghĩa HTTP response field **Deprecation** (Structured Fields date).
- **RFC 8594** định nghĩa HTTP **Sunset**.
- **Link rel=deprecation** dẫn tới hướng dẫn migration khi được hỗ trợ.
- Header không tự tắt route. **deprecated: true** trong OpenAPI cũng chỉ là metadata.
- Sau sunset, có thể trả **410 Gone** nếu ngữ nghĩa phù hợp, không bắt buộc mọi URL phải dùng 410. **426 Upgrade Required** không phải status mặc định để ép client JSON API sang v2.

Hãy công bố changelog, field/enum mapping, ngày ngừng hỗ trợ được phê duyệt, tài liệu nâng SDK và kênh hỗ trợ. Quyết định sunset dựa vào **traffic theo version và nhóm consumer**, không chỉ số request trung bình; công việc chạy hàng tháng cũng có thể còn phụ thuộc v1.

## 14. Ma trận kiểm thử v1/v2

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| V01 | GET cùng order qua cả hai version | Cùng domain record, hai schema đúng |
| V02 | SDK v1 đọc response trên server mới | Không lỗi enum/deserializer |
| V03 | Domain PENDING | V1 NEW, v2 PENDING |
| V04 | V1 có trường total v2 | Contract test phát hiện |
| V05 | V2 thiếu currency | Contract test phát hiện |
| V06 | Client gọi /api/v3 | Không fallback âm thầm |
| V07 | V2 POST thêm required field | V1 POST cũ vẫn hợp lệ theo semantics cũ |
| V08 | Tenant A đọc order B ở v1 và v2 | Đều 403/404, không lộ dữ liệu |
| V09 | Token không hợp lệ qua v1 | 401, legacy route không bypass auth |
| V10 | Xen kẽ v1/v2 để vượt quota | Bị chặn bởi quota tổng |
| V11 | Cache có cả v1/v2 | Không trộn body hoặc principal |
| V12 | Retry POST cùng business operation | Không tạo side effect trùng |
| V13 | Hai client PUT qua hai version | Cùng optimistic locking, không lost update |
| V14 | V2 thêm currency khác | Gate bảo vệ khả năng biểu diễn v1 |
| V15 | OpenAPI lint & JSON schema validation | Hai spec hợp lệ, $ref không hỏng |
| V16 | Backfill tiền | Không mất precision/record |
| V17 | Canary v2 rollback | Không gây dữ liệu v1 không đọc được |
| V18 | Deprecation/Sunset | Header/link, lifecycle policy đúng |

**Provider contract tests** so response thật với OpenAPI **từng phiên bản**. **Consumer-driven tests** chạy với SDK/client quan trọng; một test v2 thành công không chứng minh v1 tương thích. V1 regression suite phải chạy ở **mọi release vẫn phục vụ v1**.

### 14.1. Mẫu Spring MockMvc

~~~java
@Test
void contractsStayIndependent() throws Exception {
    UUID id = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");

    mvc.perform(get("/api/v1/orders/{id}", id)
            .header("Authorization", "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("NEW"))
        .andExpect(jsonPath("$.totalAmountVnd").value(150000))
        .andExpect(jsonPath("$.total").doesNotExist());

    mvc.perform(get("/api/v2/orders/{id}", id)
            .header("Authorization", "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("PENDING"))
        .andExpect(jsonPath("$.total.currency").value("VND"))
        .andExpect(jsonPath("$.total.amountMinor").value(150000));
}
~~~

Đây là ví dụ cần fixture và security test setup. Cần thêm test DB thực cho transaction/authorization, không coi mock service là bằng chứng chống lost update hoặc IDOR.

## 15. Bài thực hành: Task API v1 → v2

**Bối cảnh:** v1 có GET/POST **/api/v1/tasks**, trả **dueDate** (YYYY-MM-DD), enum **TODO/DONE** và **assigneeId** tùy chọn. V2 đổi thành **dueAt** ISO 8601 date-time có timezone, enum **OPEN/IN_PROGRESS/COMPLETED** và **assignees** array. Mobile v1 chưa nâng cấp ngay.

### 15.1. Nhiệm vụ (100 điểm)

1. **Contract – 30 điểm:** thiết kế OpenAPI 3.1 v1 và v2 riêng, ghi breaking differences, null/required, enum, HTTP errors.
2. **Spring – 25 điểm:** thiết kế DTO/mapper/controller riêng, domain service chung và chính sách với task nhiều assignee/timezone mà v1 không hiểu.
3. **Bảo mật/rollout – 20 điểm:** bảo vệ tenant, quota, cache, idempotency và concurrency xuyên phiên bản; lập lịch canary/deprecation.
4. **Kiểm thử – 25 điểm:** ít nhất tám test gồm v1 regression, v2 schema, enum/timezone, multi-assignee, cross-tenant, concurrent update, SDK cũ và rollback.

### 15.2. Hướng giải tham khảo

V1 giữ dueDate/TODO/DONE/assigneeId. V2 dùng dueAt, trạng thái mới và assignees list. Domain có thể dùng instant kèm timezone và danh sách assignee; nhưng v1 mapper chỉ được chuyển đổi khi **không làm mất nghĩa**. Nếu v1 chỉ có một assignee, phải hạn chế capability tương ứng trong thời gian hỗ trợ hoặc có migration đã duyệt, **không âm thầm bỏ những người còn lại**. Cả hai controller phải dùng chung quyền tenant và optimistic locking đúng nghĩa, và mọi build phải chạy regression cả hai spec.

Một lời giải đạt yêu cầu phải chỉ rõ **field nào không thể chuyển đổi an toàn**, không chỉ đổi prefix URI.

## 16. Checklist tổng kết

- [ ] Phân biệt API version, OpenAPI doc version, server release và ETag.
- [ ] Mỗi version có schema, error, security và kiểm thử riêng.
- [ ] Routing rõ; không fallback/redirect gây gửi sai payload.
- [ ] DTO/mapper ở HTTP boundary; domain logic chung có kiểm soát.
- [ ] Bảo vệ semantic compatibility cho tiền tệ, enum, timezone, required fields.
- [ ] Authn/authz/tenant, quota, cache, idempotency và concurrency xuyên version.
- [ ] DB có lộ trình expand–migrate–contract và rollback/capability gates.
- [ ] Có canary, observability, migration guide, lịch deprecation/sunset xác thực.
- [ ] Không ngừng v1 khi còn consumer quan trọng chưa chuyển đổi.

**Ghi nhớ:** nhiều phiên bản API **không đồng nghĩa nhiều nguồn sự thật dữ liệu**. Hãy duy trì **hợp đồng public độc lập**, dùng domain/policies chung khi đúng, và quản lý mỗi version như một sản phẩm có kiểm thử, bảo mật và vòng đời rõ ràng.

### Tài liệu tham khảo

- **OpenAPI Specification 3.1:** paths, schema, security, deprecated.
- **JSON Schema Draft 2020-12:** type, object, enum, null và required.
- **RFC 9110 – HTTP Semantics:** content negotiation, status, validators và redirects.
- **RFC 9111 – HTTP Caching:** Vary, Authorization và cache keys.
- **RFC 9457 – Problem Details for HTTP APIs:** lỗi HTTP có cấu trúc.
- **RFC 9745 – Deprecation HTTP Response Header Field** và **RFC 8594 – Sunset HTTP Header Field**.
- **Spring Framework / Spring Boot:** versioned controllers, security và testing.
