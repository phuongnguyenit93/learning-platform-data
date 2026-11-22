# SDK, mã client sinh tự động và trách nhiệm bảo trì

> **Module:** `INTEGRATION_API_REST` — chương **Tài liệu và trải nghiệm**. Bài học giúp thiết kế REST API dựa trên resource, URI, phương thức và mã trạng thái HTTP có **SDK sử dụng được, an toàn và bảo trì được**. Trọng tâm: sinh client từ OpenAPI, ranh giới giữa mã sinh và mã viết tay, Java/Spring, authentication, phân trang, cache/ETag, idempotency, lỗi, kiểm thử tương thích và trách nhiệm vòng đời của đội cung cấp API.

## 1. Có client sinh tự động chưa có nghĩa đã có SDK tốt

Một API Orders công bố:

~~~http
GET /v1/orders/ord_42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Client sinh từ OpenAPI có thể cung cấp method `getOrder("ord_42")` và class `OrderResponse`. Nhưng SDK còn phải trả lời:

- Token lấy từ đâu, refresh thế nào, có bị gửi sang host khác khi redirect không?
- `404` được biểu diễn ra sao? `412 Precondition Failed` có giúp caller đối soát ETag không?
- Khi POST timeout sau commit, SDK có tự gửi lại gây **đơn hàng trùng** không?
- `GET /v1/orders?cursor=...` có phân trang, SDK có cung cấp iterator mà không tải vô hạn không?
- Server thêm một trường JSON mới có làm client cũ mất khả năng deserialize không?
- Khi OpenAPI thay đổi, **ai chịu trách nhiệm** regeneration, review, test, publish, release notes, xử lý bug và migration?

Một lớp generated DTO có thể đúng cú pháp mà vẫn phá hệ thống ở production vì tự retry POST, làm rò Bearer token hoặc biến các response lỗi thành exception không có thông tin hữu ích. **Sinh code là bước tạo ra một phần hiện vật; SDK là sản phẩm có hợp đồng hỗ trợ.**

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **OpenAPI contract, generated client, HTTP transport và SDK façade**.
2. Chọn sinh code hoặc viết tay có chủ đích, khóa version generator và quy trình reproducible builds.
3. Thiết kế xử lý HTTP status, auth, timeout, redirect, retry, idempotency, ETag và phân trang trong Java client.
4. Thiết lập kiểm thử contract, compatibility, security và CI cho mã được sinh.
5. Định nghĩa trách nhiệm giữa API team, SDK maintainers và các nhóm tiêu thụ SDK; lập chính sách release, deprecation và support.

## 2. SDK gồm những tầng nào?

~~~mermaid
flowchart TB
    A["API contract: OpenAPI + examples + policy"] --> B["Pinned generator + config"]
    B --> C["Generated: DTO, endpoints, serialization"]
    C --> D["Transport: TLS, auth, timeouts, errors"]
    D --> E["Handwritten façade: safe workflows"]
    E --> F["App Java/Spring hoặc client khác"]
    G["Contract / integration / compatibility tests"] --> A
    G --> C
    G --> D
    G --> E
    H["API + SDK maintainers: version, release, support"] --> G
~~~

| Tầng | Công việc chính | Ranh giới trách nhiệm |
|---|---|---|
| **OpenAPI & HTTP contract** | Paths, schemas, operationId, status, headers, security, error model | **API owner** sở hữu sự thật trên wire |
| **Generated models/API stubs** | Type mapping, JSON codecs, method signatures, request builders | **Generator output** có thể tái tạo; không vá trực tiếp |
| **Transport/runtime** | TLS, token provider, connection pool, timeouts, redirect, retry, logging | SDK maintainer cần kiểm thử và kiểm soát |
| **SDK façade** | Iterator phân trang, thao tác có điều kiện, mapping lỗi, cancellation | API developer experience và ergonomics |
| **Release artifacts** | Version, binary/source package, docs, SBOM, checksum | SDK owner và CI/release pipeline |
| **Consumers** | Cấu hình credentials, xử lý business conflict, nâng version | App team sử dụng đúng contract |

Không phải mọi dự án cần năm lớp tách thành năm thư viện. SDK nhỏ có thể gói chung transport và façade; điều bắt buộc là **trách nhiệm rõ** và **mã sinh không trở thành nơi sửa tay không kiểm soát**.

### 2.1. Client sinh tự động khác thư viện ứng dụng

- **Generated client:** phương thức HTTP và các kiểu dữ liệu từ OpenAPI; thường đưa operationId, path/query/body/response thành code.
- **SDK:** generated client **cộng** defaults an toàn, error handling, pagination, auth integration, docs, tests, versioning và support policy.
- **Ứng dụng gọi SDK:** sở hữu business workflow, loại data cần lấy, user consent, quy tắc retry phía nghiệp vụ và tenant context của chính mình.

Không để SDK tự quyết định “khách hàng có được phép đọc đơn hàng này không”. **Server luôn thực thi authentication/authorization theo principal, tenant và object.** SDK có thể giúp truyền token/scope đúng, nhưng không phải một biện pháp bảo mật thay server.

## 3. Khi nào nên generate, khi nào nên viết tay?

| Tình huống | Generate có lợi | Phần vẫn cần thiết kế |
|---|---|---|
| API có hàng chục resource và JSON schema rõ | Giảm boilerplate, kiểu nhất quán | operationId, lỗi, optional/null semantics |
| Nhiều ngôn ngữ (Java, TypeScript, Python) | Dùng chung OpenAPI làm source of truth | Mỗi runtime có idiom/transport khác nhau |
| CRUD cơ bản, pagination có contract ổn định | Path/query/body mapping nhanh | Iterator an toàn, page limit, cancellation |
| Streaming/file upload/download lớn | Có thể sinh signature/headers | Streaming/rewind/resume, file limits, không buffer vô hạn |
| OAuth2/OIDC, rotating keys, mTLS | Khai báo security schemes | Token provider, TLS/redirect/rotation thực tế |
| Retry, ETag và idempotent commands | Sinh header parameters | **Chính sách** replay, delay, deadline, conflict |
| Legacy API có schema mơ hồ | Sinh code có thể ít giá trị | Bổ sung contract tests/tài liệu hoặc adapter viết tay |

**Nguyên tắc:** generate cho phần **có thể mô tả đầy đủ và lặp lại bằng schema**; viết tay cho phần **policy và trải nghiệm có ngữ cảnh**. Không viết tay lại toàn bộ DTO chỉ vì generator thiếu một tiện ích nhỏ; cũng không nhét logic security phức tạp vào template generator chưa được quản trị.

### 3.1. Không để SDK che mất ngữ nghĩa HTTP

Hãy giữ khả năng đọc tối thiểu `status`, `headers` (nhất là `ETag`, `Location`, `Retry-After`, `Link`) và response errors. Một method `createOrder()` chỉ trả `OrderResponse` nhưng xóa `Location`, `ETag` sẽ hạn chế client xử lý resource mới, optimistic concurrency hoặc polling.

API sinh có thể cung cấp method dạng `...WithHttpInfo(...)`, `ApiResponse<T>` hoặc response wrapper tùy generator/runtime; **đừng giả định tên method giống nhau giữa các generator**. Trước khi chốt SDK public API, kiểm thử những dữ liệu nào còn khả dụng sau khi generated transport deserialize body.

## 4. OpenAPI là hợp đồng đầu vào, không phải hình minh họa

Ví dụ phần cốt lõi của một API Orders dùng OpenAPI 3.1. Các đường dẫn, media types, headers và HTTP statuses đều cần khớp với server đang chạy:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.4.0
servers:
  - url: https://api.example.test
paths:
  /v1/orders:
    get:
      operationId: listOrders
      security: [{bearerAuth: []}]
      parameters:
        - name: limit
          in: query
          schema: {type: integer, minimum: 1, maximum: 100, default: 20}
        - name: cursor
          in: query
          schema: {type: string}
      responses:
        '200':
          description: Trang đơn hàng
          content:
            application/json:
              schema: {$ref: '#/components/schemas/OrderPage'}
    post:
      operationId: createOrder
      security: [{bearerAuth: []}]
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string, minLength: 1, maxLength: 128}
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/CreateOrderRequest'}
      responses:
        '201':
          description: Đã tạo đơn
          headers:
            Location:
              required: true
              schema: {type: string, format: uri-reference}
            ETag:
              schema: {type: string}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '400': {$ref: '#/components/responses/Problem'}
        '409': {$ref: '#/components/responses/Problem'}
  /v1/orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        schema: {type: string}
    get:
      operationId: getOrder
      security: [{bearerAuth: []}]
      parameters:
        - name: If-None-Match
          in: header
          required: false
          schema: {type: string}
      responses:
        '200':
          description: Chi tiết đơn
          headers:
            ETag:
              schema: {type: string}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '304':
          description: Không đổi; không có response body
          headers:
            ETag:
              schema: {type: string}
        '404': {$ref: '#/components/responses/Problem'}
    patch:
      operationId: updateOrderNote
      security: [{bearerAuth: []}]
      parameters:
        - name: If-Match
          in: header
          required: true
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema: {$ref: '#/components/schemas/PatchOrderNote'}
      responses:
        '200':
          description: Đã cập nhật
          headers:
            ETag:
              schema: {type: string}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '412': {$ref: '#/components/responses/Problem'}
        '428': {$ref: '#/components/responses/Problem'}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    CreateOrderRequest:
      type: object
      additionalProperties: false
      required: [productId, quantity]
      properties:
        productId: {type: string, minLength: 1}
        quantity: {type: integer, minimum: 1}
    PatchOrderNote:
      type: object
      additionalProperties: false
      required: [deliveryNote]
      properties:
        deliveryNote: {type: [string, 'null'], maxLength: 500}
    Order:
      type: object
      required: [id, status]
      properties:
        id: {type: string, readOnly: true}
        status: {type: string, readOnly: true}
        deliveryNote: {type: [string, 'null']}
    OrderPage:
      type: object
      required: [items]
      properties:
        items:
          type: array
          items: {$ref: '#/components/schemas/Order'}
        nextCursor: {type: [string, 'null']}
  responses:
    Problem:
      description: Lỗi theo RFC 9457
      content:
        application/problem+json:
          schema:
            type: object
            required: [type, title, status]
            properties:
              type: {type: string, format: uri-reference}
              title: {type: string}
              status: {type: integer}
              code: {type: string}
~~~

Đây là **hợp đồng mẫu, không phải toàn bộ API thực thi**. Nếu server còn trả `401/403/429/500`, thêm chúng vào spec; security schemes và status phải khớp server. `readOnly` của OpenAPI không thay field-level authorization; server phải bác request thay đổi field server-owned. `additionalProperties: false` nên khớp cách server xử lý unknown input thay vì để client sinh code tự quyết policy.

## 5. Thiết kế spec để client sinh ra có thể dùng được

**Spec hợp lệ về cú pháp chưa đủ.** Tên, kiểu và quy tắc tương thích trên wire sẽ quyết định mức độ ổn định của các SDK.

### 5.1. `operationId`, tags và tên model là API bề mặt của SDK

Một generator có thể biến:

~~~yaml
get:
  operationId: getOrder
  tags: [Orders]
~~~

thành lời gọi gần giống `OrdersApi.getOrder(...)`. Nếu đổi `operationId` thành `getSingleOrder` dù HTTP path vẫn y nguyên, **source code người dùng có thể không biên dịch** sau khi regenerate SDK. Vì thế:

- Mỗi operation có **operationId duy nhất, ổn định**, theo quy ước động từ + resource (`listOrders`, `getOrder`, `createOrder`, `updateOrderNote`).
- Tags/namespace, model names, trường bắt buộc và phân cấp package cần được review như **public API**.
- Không đặt model tên `Object`, `ApiResponse`, `Request` quá chung chung gây đụng tên trong Java/TypeScript.
- Chọn một phong cách URI/resource và versioning nhất quán; không để generator tự quyết REST design.

### 5.2. Required, optional, nullable và missing không giống nhau

Với JSON:

~~~json
{"deliveryNote": null}
~~~

khác với:

~~~json
{}
~~~

Nhất là với PATCH, **vắng mặt** có thể nghĩa là “giữ nguyên” còn `null` nghĩa là “xóa ghi chú”. Trong OpenAPI 3.1/JSON Schema, `required` quyết định property phải xuất hiện, còn `type: [string, 'null']` quyết định giá trị null có hợp lệ. Một số generator biểu diễn:

- Java `String` và `null` cho cả “không có field” lẫn “field=null” → **mất thông tin** nếu không có wrapper/flag/JsonNullable.
- Kotlin nullable type, TypeScript optional property và JSON `null` với ngữ nghĩa khác nhau.
- `Optional<T>` có thể vẫn không phân biệt ba trạng thái nếu không thiết kế serializer phù hợp.

Đối với PATCH cần giữ ranh giới **absent / null / value**, hãy test serialization thật của generated model chứ không chỉ nhìn signature. Nếu generator không biểu diễn được, tạo DTO/patch builder riêng trong façade với một loại tri-state hoặc JSON patch document đã kiểm soát; đừng âm thầm gửi `null` cho field vắng mặt.

### 5.3. Date, decimal, enum và binary

| Trường | Sai lầm dễ gặp | Quyết định cần ghi trong contract |
|---|---|---|
| Timestamp | Serialize bằng timezone local; mất offset | `date-time` theo RFC 3339/ISO 8601, UTC/offset rõ |
| Tiền | Dùng `double`, sai số khi cộng/trừ | Decimal dưới dạng string + scale hoặc integer minor units, có currency |
| Enum | Client cũ crash khi server thêm giá trị | Chiến lược unknown value/fallback được test |
| ID | Dùng số quá lớn trong JavaScript, mất precision | String cho opaque identifiers |
| Binary/file | Buffer toàn file trong RAM | Streaming API, size limits, MIME và checksum |
| `oneOf`/discriminator | Generator chọn sai subtype | Schema đủ rõ, test từng subtype |
| URL/`Location` | SDK tự ghép URI và forward Bearer | URI reference hợp lệ và origin policy |

**Không đổi kiểu trên wire chỉ vì type mapping của một generator “trông đẹp hơn”.** Nếu SDK Java cần `BigDecimal` nhưng contract hiện trả numeric JSON có precision semantics chưa rõ, phải xử lý ở hợp đồng/API owner, không chỉ vá type ở SDK.

### 5.4. Response headers và vấn đề empty-body

Kiểm tra generator phân biệt `204 No Content`, `304 Not Modified` và `200` có body. Java client không được deserialize `304` thành `Order` từ body rỗng. `201 Location` và `202 Accepted` + operation monitor cần truy cập raw response headers; `429 Retry-After` có thể ở response lỗi và phải được giữ lại trong error type.

Nếu frontend chạy trên browser, `Access-Control-Expose-Headers` còn quyết định JavaScript có đọc `ETag/Location` được không; sinh SDK TypeScript không thể vượt qua cơ chế Fetch/CORS của browser.

## 6. Sinh mã theo cách tái lập được và kiểm soát dependency

Luồng đúng:

~~~text
Thay đổi OpenAPI
    ↓ lint + validate + diff tương thích
Pin generator version + templates + config + runtime dependencies
    ↓ generate vào thư mục riêng
Review generated diff + smoke build/test
    ↓ test server contract, integration, security
Publish signed/reproducible artifact + changelog + docs
    ↓ hỗ trợ versions và thông báo migration
~~~

Không để mỗi lập trình viên dùng generator mới nhất trên máy cá nhân khiến cùng một spec tạo ra code khác nhau. **Khóa phiên bản generator, template tùy biến, ngôn ngữ/library flavor, serialization settings và dependency lockfiles**. Nếu chạy generator qua container, cân nhắc pin immutable digest, không chỉ `latest`.

### 6.1. Cấu hình Maven minh họa

Ví dụ build Java client qua OpenAPI Generator Maven Plugin. Dự án thực cần thay `X.Y.Z` bằng **phiên bản đã kiểm chứng và khóa cố định**; không để biến version tự cập nhật:

~~~xml
<properties>
  <openapi.generator.version>X.Y.Z</openapi.generator.version>
</properties>
<build>
  <plugins>
    <plugin>
      <groupId>org.openapitools</groupId>
      <artifactId>openapi-generator-maven-plugin</artifactId>
      <version>${openapi.generator.version}</version>
      <executions>
        <execution>
          <id>generate-orders-client</id>
          <goals><goal>generate</goal></goals>
          <configuration>
            <inputSpec>${project.basedir}/src/main/openapi/orders.yaml</inputSpec>
            <generatorName>java</generatorName>
            <output>${project.build.directory}/generated-orders</output>
            <apiPackage>example.sdk.generated.api</apiPackage>
            <modelPackage>example.sdk.generated.model</modelPackage>
            <configOptions>
              <dateLibrary>java8</dateLibrary>
            </configOptions>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Các đường dẫn/tên package là ví dụ, **không yêu cầu bạn tạo thêm tệp trong nhiệm vụ này**. Các option được hỗ trợ và thư viện HTTP mặc định phụ thuộc version/generator; chọn, document và khóa chúng sau khi thử compile/test. Có thể generate dưới `target/` hoặc một thư mục riêng để dễ phân biệt mã sinh và mã tay. Với Gradle dùng plugin tương đương và dependency locking.

### 6.2. Có commit generated code vào Git không?

Hai lựa chọn hợp lý:

| Cách | Lợi ích | Rủi ro và kiểm soát |
|---|---|---|
| Commit code sinh vào repository SDK | Reviewer thấy diff, consumers không cần generator | Git diff lớn, không sửa tay, CI regenerate kiểm diff sạch |
| Generate trong CI/build | Tránh lưu hàng nghìn dòng generated | Toolchain phải pin, build offline/reproducible, artifact có provenance |

Không có lựa chọn đúng cho mọi dự án. Bất kể cách nào, **cùng OpenAPI + cùng generator/config phải tạo cùng public SDK behavior**. Một CI job có thể regenerate trong thư mục sạch và so sánh checksum/diff, thất bại nếu đầu ra không khớp artifact đã review. Cẩn thận timestamp, line ending, encoding và file ordering không ổn định.

### 6.3. Supply chain và giấy phép

Mã sinh thường mang các runtime libraries/HTTP client/JSON libraries; cần theo dõi CVE, licenses, transitive dependencies, SBOM và nguồn generator/templates. Không download templates từ URL không kiểm soát trong CI, không chạy plugin `latest` không pin, không publish package từ laptop với credentials cá nhân.

Thư viện SDK Java nên công bố version Java tối thiểu, Jakarta/Javax compatibility, Spring/HTTP library requirements, Maven coordinates, quy tắc shading nếu có, và việc dùng dependency nào là transitive. Tránh kéo nhiều HTTP client stack cồng kềnh chỉ vì generator chọn flavor mặc định.

## 7. Java SDK façade: giữ generated code có thể thay thế

Ví dụ một lớp application-facing `OrderSdk` cần đọc `ETag` và PATCH có điều kiện. Ta định nghĩa **port ổn định do đội SDK sở hữu**; adapter phía sau port gọi **generated client thật**. Mẫu này giúp test lỗi/headers mà không khóa người dùng vào tên class/phương thức cụ thể của generator.

### 7.1. Contract của adapter

~~~java
import java.util.*;

public record OrderDto(String id, String status, String deliveryNote) {}
record NotePatch(String deliveryNote) {}
public record VersionedOrder(OrderDto order, String etag) {}

record SdkHttpResponse<T>(
    int status, Map<String, List<String>> headers, T body
) {
    Optional<String> header(String name) {
        return headers.entrySet().stream()
            .filter(e -> e.getKey().equalsIgnoreCase(name))
            .flatMap(e -> e.getValue().stream())
            .findFirst();
    }
}

interface OrdersPort {
    SdkHttpResponse<OrderDto> getOrder(String orderId);
    SdkHttpResponse<OrderDto> patchNote(
        String orderId, String ifMatch, NotePatch patch);
}
~~~

`OrdersPort` và `SdkHttpResponse` là **interface/record tự thiết kế**, **không phải tên class mặc định của OpenAPI Generator**. Adapter hiện thực chúng bằng generated `OrdersApi` và method nhận raw status/headers của **generator/library đã chọn**. Như vậy một lần nâng generator không buộc mọi application import một bộ method mới. Khi chuyển đoạn minh họa thành mã thật, đặt **mỗi `public record` vào tệp `.java` riêng** theo quy tắc Java; các type nội bộ như `NotePatch`/`OrdersPort` có thể giữ package-private nếu không cần công bố.

### 7.2. Façade không làm mất ETag và status

~~~java
import java.util.Objects;

public final class OrderSdk {
    private final OrdersPort port;

    public OrderSdk(OrdersPort port) {
        this.port = Objects.requireNonNull(port);
    }

    public VersionedOrder get(String id) {
        SdkHttpResponse<OrderDto> r =
            port.getOrder(Objects.requireNonNull(id));
        if (r.status() == 200 && r.body() != null) {
            return new VersionedOrder(
                r.body(), requireStrongEtag(r));
        }
        throw toSdkError(r.status());
    }

    public VersionedOrder updateNote(
            VersionedOrder current, String note) {
        Objects.requireNonNull(current);
        String tag = current.etag();
        if (!isStrongTag(tag)) {
            throw new IllegalArgumentException(
                "A strong ETag is required");
        }

        SdkHttpResponse<OrderDto> r = port.patchNote(
            current.order().id(), tag, new NotePatch(note));
        if (r.status() == 200 && r.body() != null) {
            return new VersionedOrder(
                r.body(), requireStrongEtag(r));
        }
        if (r.status() == 412) {
            throw new StaleOrderException(
                "Reload and reconcile the order");
        }
        throw toSdkError(r.status());
    }

    private static String requireStrongEtag(
            SdkHttpResponse<?> r) {
        String tag = r.header("ETag").orElseThrow(() ->
            new SdkProtocolException("ETag missing"));
        if (!isStrongTag(tag)) {
            throw new SdkProtocolException(
                "Expected a strong ETag");
        }
        return tag;
    }

    private static boolean isStrongTag(String tag) {
        return tag != null && tag.length() >= 2
            && tag.startsWith("\"") && tag.endsWith("\"");
    }

    private static RuntimeException toSdkError(int status) {
        if (status == 401 || status == 403) {
            return new SdkAuthorizationException(status);
        }
        if (status == 404) {
            return new SdkNotFoundException();
        }
        return new SdkHttpException(status);
    }
}

class StaleOrderException extends RuntimeException {
    StaleOrderException(String message) { super(message); }
}
class SdkProtocolException extends RuntimeException {
    SdkProtocolException(String message) { super(message); }
}
class SdkHttpException extends RuntimeException {
    private final int status;
    SdkHttpException(int status) {
        super("HTTP " + status);
        this.status = status;
    }
    int status() { return status; }
}
class SdkAuthorizationException extends SdkHttpException {
    SdkAuthorizationException(int status) { super(status); }
}
class SdkNotFoundException extends SdkHttpException {
    SdkNotFoundException() { super(404); }
}
~~~

Đây là **lát cắt minh họa Java 17**, giả định port trả `SdkHttpResponse` cả với 4xx. Generated clients thường **ném exception** cho non-2xx, nên adapter phải chuyển generated exception về `status/headers/body` mà không nuốt `Retry-After` hoặc `application/problem+json`. `isStrongTag` chỉ minh họa kiểm cú pháp bao ngoài; parser HTTP hoàn chỉnh phải dùng khi hỗ trợ danh sách ETags/`*`/escaping theo RFC 9110.

Đối với PATCH thật, cần contract xử lý `null` và omitted fields, validate note length, tenant/owner trên server và test request body. Nếu caller nắm `VersionedOrder` cũ, façade **giữ If-Match** thay vì tự tải tag mới rồi ghi đè trái ý người dùng. Sau 412, caller phải reload, so sánh thay đổi và quyết định cập nhật lại.

### 7.3. Chọn cách tích hợp vào Spring

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersSdkConfiguration {
    @Bean
    OrderSdk orderSdk(OrdersPort generatedOrdersAdapter) {
        return new OrderSdk(generatedOrdersAdapter);
    }
}
~~~

`generatedOrdersAdapter` là bean được đội SDK hiện thực bằng generated transport đã chọn; ví dụ không giả định generated class có constructor hoặc method cố định. Trong ứng dụng Spring, có thể tiêm `TokenProvider` theo **mỗi service audience**, HTTP client pool và base URL cấu hình; đừng dùng global static token hoặc global mutable base URL cho nhiều tenant.

**Luồng trách nhiệm:** API team duy trì `/v1/orders` và response headers; SDK maintainer duy trì `OrdersPort` adapter, façade/errors/tests; application gọi `OrderSdk` và xử lý conflict theo nghiệp vụ. Chỉ bên server biết quyền cập nhật object cuối cùng, không phải façade.

## 8. Transport và bảo mật: hợp đồng không thể “sinh hộ”

SDK mặc định có ảnh hưởng trực tiếp tới bảo mật production. Trước khi publish, chốt các policy có thể kiểm thử:

| Chủ đề | Mặc định an toàn | Lỗi phổ biến |
|---|---|---|
| Base URL | HTTPS, allowlist/config tin cậy, chặn HTTP ngoài test | Cho endpoint URL tùy ý rồi gửi token |
| TLS | Verify certificate và hostname, trust store chuẩn | `trust-all`/`HostnameVerifier` luôn đúng |
| Bearer token | Provider đúng audience/scope; token ngắn hạn | Hardcode token, log Authorization |
| OAuth2 refresh | Retry auth flow có giới hạn, single-flight khi cần | 401 loop/refresh storm |
| Redirect | Không chuyển credentials qua origin khác; policy rõ 301/302/303/307/308 | Auto-follow 307 đến host không tin cậy cùng body và Bearer |
| Cookie | `HttpOnly/Secure/SameSite` khi dùng browser session | Coi `Set-Cookie` là header JS có thể đọc |
| Logging | Redact token, cookies, signed URL, request body PII | Log nguyên request/response khi debug |
| Proxy/mTLS | Cấu hình riêng, không nhập proxy auth với API auth | Gửi `Proxy-Authorization` sai đích |

Ví dụ tạo HTTP client nền cho một adapter **không tự follow redirect**:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient transport = HttpClient.newBuilder()
    .followRedirects(HttpClient.Redirect.NEVER)
    .connectTimeout(Duration.ofSeconds(3))
    .build();
~~~

Điều này chưa phải một SDK hoàn chỉnh: còn request deadline, cancellation, pool sizing, TLS policy và token provider. Với Java 17 `HttpClient`, setting timeout của `HttpRequest` kiểm từng request; tổng deadline qua nhiều attempts/redirects là trách nhiệm khác. Với Spring `RestClient` (đồng bộ) hoặc `WebClient` (reactive), cách đặt connector, refresh/token-scoping và timeout phụ thuộc HTTP client dưới lớp Spring; không giả định default phù hợp.

### 8.1. Browser SDK và Java server SDK khác nhau

Một SDK TypeScript chạy trong browser chịu **CORS**: `Access-Control-Allow-Origin`, preflight `Allow-Headers` khi gửi `Authorization/If-Match`, `Expose-Headers` khi đọc `ETag/Location`; `Set-Cookie` không đọc được qua `Response.headers`. Java backend client **không chịu browser CORS**, nhưng vẫn phải kiểm TLS, permission, redirects và secrets. Không dùng cùng lời khuyên “bật CORS” để chữa lỗi Java HttpClient.

Nếu app là native mobile/server-side và SDK mở rộng các redirect hợp lệ sang CDN tải file, hãy dùng **một HTTP client context khác** không mang Bearer của API cho signed URL. Signed URL là bearer capability: không log query signature, không forward URL qua analytics và giới hạn TTL/host theo contract.

## 9. HTTP semantics trong SDK: giữ hành vi đúng thay vì “tiện”

| Tình huống | SDK nên làm | Điều không được tự làm |
|---|---|---|
| `201 Created` + `Location` | Trả resource và link mới | Coi Location là redirect bắt buộc |
| `202 Accepted` | Trả operation ID/monitor URI, trạng thái đang xử lý | Báo công việc hoàn tất ngay |
| `204 No Content` | Trả kết quả không body đúng kiểu | Deserialize JSON rỗng gây lỗi |
| `304 Not Modified` | Dùng cached representation *nếu có* và đúng policy | Coi 304 là 200 JSON mới |
| `400` / `422` | Chuyển thành validation error có field/code đã lọc | Retry vô hạn vì HTTP không phải 2xx |
| `401/403` | Dừng hoặc auth refresh hợp lệ **tối đa có giới hạn** | Thay token audience ngẫu nhiên, retry 403 |
| `404` | Trả not-found theo policy | Tự tìm resource ở tenant khác |
| `409` | Expose business conflict | Tự vượt conflict bằng replay |
| `412` / `428` | Bảo toàn precondition, báo stale/missing ETag | Bỏ `If-Match` để request “thành công” |
| `429` / `503` + `Retry-After` | Tôn trọng retry policy và deadline | Retry ngay gây retry storm |
| `500/502/504` | Phân loại transient vs permanent, ghi trace ID | Che lỗi thành response rỗng |

### 9.1. Error model có ích cho người dùng SDK

Nếu server trả:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Retry-After: 5
X-Request-Id: req_42

{
  "type": "https://api.example.test/problems/order-state",
  "title": "Order cannot be changed",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

SDK nên giữ **status, code, request ID, retry-after nếu có và thông tin body được phép đọc**, nhưng không phản chiếu private fields/token vào exception message/log. `409` là business conflict nên **không mặc định retry chỉ vì có Retry-After**; retryability còn phụ thuộc operation contract. Header `Retry-After` có cả dạng delay-seconds lẫn HTTP-date; parser phải hỗ trợ cả hai khi tuyên bố tuân chuẩn.

### 9.2. Contract HTTP là nguồn quyết định

Không suy ra idempotency chỉ bằng “method này thường là POST/PUT”. `GET` là safe theo HTTP, `PUT`/`DELETE` có ngữ nghĩa idempotent, nhưng SDK phải biết request body có replay được không, server có `Idempotency-Key`/dedup với POST không, và redirect có thay đổi method/body không. Một attempt **bị timeout sau commit** có kết quả mơ hồ; không có retry policy nào biến việc commit đã xảy ra thành rollback.

## 10. Retry, idempotency, deadline và kết quả không chắc chắn

SDK thường được kỳ vọng “tự ổn định mạng”, nhưng **retry không phải một vòng lặp catch Exception**. Một policy thực tế cần phối hợp **loại thao tác, trạng thái HTTP, khả năng replay body, deadline, server hint và idempotency contract**.

| Operation | Retry khi timeout/503? | Điều kiện tiên quyết |
|---|---|---|
| `GET /v1/orders/{id}` | Thường có thể, trong budget | Đọc an toàn; auth, deadline và backoff |
| `GET` phân trang | Có thể, nhưng giữ nguyên cursor và query | Không tự nhảy trang, không dùng cursor tenant khác |
| `POST /v1/orders` | Chỉ nếu contract hỗ trợ replay | Cùng `Idempotency-Key`, **cùng payload**/fingerprint |
| `PATCH` với `If-Match` | Cẩn trọng | Nếu timeout có thể đã commit; readback/reconcile khi 412 |
| Upload stream không rewind | Không tự replay | Resumable upload/checkpoint hoặc body replayable |
| `401` token hết hạn | Có thể refresh **một lần** theo OAuth flow | Đúng audience, single-flight, không refresh 403 |
| `429/503` | Có thể theo contract | Honor `Retry-After`, giới hạn attempts và deadline |

**Retry decision matrix** nên nêu rõ: lỗi connect trước khi gửi request, reset giữa lúc gửi body và timeout sau khi server xử lý **không có mức chắc chắn như nhau**. SDK có thể biết request chưa rời client trong một số lỗi, nhưng không suy từ mọi `IOException` rằng server chưa commit.

### 10.1. `Idempotency-Key` là ranh giới server–client

Ví dụ một attempt tạo đơn:

~~~http
POST /v1/orders HTTP/1.1
Idempotency-Key: 12a31ee2-5ff7-431b-a0ca-6d18bd433a65
Content-Type: application/json
Authorization: Bearer <access-token>

{"productId":"p_17","quantity":2}
~~~

Nếu response mất, SDK retry cùng `Idempotency-Key` và **body y hệt theo contract canonicalization**, không tạo UUID mới cho attempt kế tiếp. Server cần lưu fingerprint và kết quả cùng ranh giới commit, phân biệt **cùng key + cùng payload** với **cùng key + payload khác**. Phải công bố TTL, status khi key đang `IN_PROGRESS`, behavior khi hết hạn và scoping theo tenant/client/operation.

Một SDK Java có thể cung cấp hai API rõ ràng:

~~~java
interface OrderCreation {
    // SDK tự sinh key cho một LẦN gọi logical operation,
    // và giữ nguyên key qua các transport attempts.
    CreatedOrder create(CreateOrderRequest request);

    // Caller truyền key để có thể retry qua process restart.
    CreatedOrder createWithKey(
        CreateOrderRequest request, String idempotencyKey);
}
~~~

`CreatedOrder` và `CreateOrderRequest` là types công khai do SDK định nghĩa/chọn từ generated models. **Nếu SDK chỉ tạo key trong memory**, sau process crash caller không thể biết key cũ; phương thức `createWithKey` hoặc một operation monitor giúp workflow bền vững. Tuyệt đối không log key nếu môi trường coi key là dữ liệu nhạy cảm; ít nhất không để key trở thành metric label.

### 10.2. Backoff và tổng ngân sách

Cho `maxAttempts=3`, per-attempt timeout 3 giây, toàn operation deadline 7 giây: dù còn attempts trên giấy, SDK không được tiếp tục khi deadline hết. Exponential backoff có jitter giảm retry storm:

~~~text
attempt 1: ngay lập tức
attempt 2: random trong [0, 200 ms] theo backoff policy
attempt 3: random trong [0, 400 ms], nếu còn deadline
~~~

Đây là thông số **minh họa**, không mặc định cho mọi API. Nếu server trả `Retry-After: 5`, không thử lại sớm hơn khoảng thời gian được chỉ dẫn; nếu vượt overall deadline thì trả lỗi có thể xử lý, không chờ vô hạn. `Retry-After` cũng có thể là HTTP-date. Không retry mọi `404/409/412` chỉ vì chúng là non-2xx.

### 10.3. Cancellation và concurrency

SDK cần giới hạn in-flight requests, queue length, connection pool, body size; hỗ trợ cancellation qua `CompletableFuture`/reactive subscription khi runtime cho phép. Trong WebFlux, không `Thread.sleep` hoặc `block()` trên event-loop khi chờ retry; dùng operator phi chặn. Client hủy sau khi server nhận POST **không đảm bảo rollback**, vì thế idempotency/operation status vẫn cần thiết.

Telemetry của SDK nên có attempts, failures, backoff duration, pool saturation và logical operation ID theo log có kiểm soát; **không** thêm user ID, JWT, raw URL/query, request ID vào metrics labels. HTTP request counts và logical success counts là hai metric khác nhau.

## 11. Phân trang, batch, file: vì sao “method được sinh” chưa đủ

### 11.1. Iterator phân trang phải có giới hạn và phát hiện vòng lặp

Server trả `GET /v1/orders?limit=20&cursor=...` với:

~~~json
{
  "items": [{"id":"ord_42","status":"DRAFT"}],
  "nextCursor": "next_abc"
}
~~~

SDK có thể cung cấp hàm tiện ích đọc các trang, nhưng **không mặc định đọc toàn bộ vô hạn**:

~~~java
import java.util.*;

record OrderPage(List<OrderDto> items, String nextCursor) {}

interface OrderPagesPort {
    OrderPage listOrders(int limit, String cursor);
}

final class OrderPaginator {
    private final OrderPagesPort port;

    OrderPaginator(OrderPagesPort port) {
        this.port = port;
    }

    List<OrderDto> loadAtMost(int pageSize, int maxPages) {
        if (pageSize < 1 || pageSize > 100 || maxPages < 1) {
            throw new IllegalArgumentException("Invalid limits");
        }
        List<OrderDto> items = new ArrayList<>();
        Set<String> cursors = new HashSet<>();
        String cursor = null;
        for (int page = 0; page < maxPages; page++) {
            OrderPage result = port.listOrders(pageSize, cursor);
            items.addAll(result.items());
            String next = result.nextCursor();
            if (next == null) break;
            if (!cursors.add(next)) {
                throw new SdkProtocolException("Repeated cursor");
            }
            cursor = next;
        }
        return List.copyOf(items);
    }
}
~~~

Đây là **bounded helper**, không phải streaming iterator thực sự; với dataset lớn, nên cung cấp `Iterator`/`Stream` hoặc reactive `Flux` tải trang theo nhu cầu, giới hạn buffer và cho phép hủy. Không đoán next cursor từ last ID nếu contract server không nói thế. Khi server dùng `Link: ...; rel="next"` thay vì `nextCursor` trong JSON, parser phải xử lý cú pháp Link đúng, và không forward credential sang origin ngoài allowlist.

### 11.2. File download/upload phải có API riêng

Generated method trả `byte[]` cho file nhiều GB có thể gây `OutOfMemoryError`. SDK nên cung cấp streaming download/upload có:

- Bounded buffers, max bytes, read-idle timeout, checksums, cancellation.
- `Content-Type` và `Content-Disposition` được validate; không dùng tên file từ server làm filesystem path chưa sanitize.
- Range/resume hoặc multipart/upload session chỉ khi API hỗ trợ, gắn idempotency cho từng part.
- Khi dùng signed download URL, **không gửi API Bearer token** sang storage origin; kiểm TLS, redirect và expiry.
- HTTP `413 Payload Too Large`, `416 Range Not Satisfiable` hoặc checksum mismatch thành errors rõ ràng.

### 11.3. Batch và partial success cần API có contract riêng

Một `POST /v1/batches` có thể **atomic all-or-nothing** hoặc **best-effort**. SDK không được coi mọi status 2xx nghĩa là mọi item thành công. Nếu API trả `202`, trả operation handle có thể poll/cancel theo quyền; nếu API trả kết quả từng item, hãy biểu diễn typed per-item outcomes và idempotency. Không tự replay toàn batch sau timeout nếu từng item đã được xử lý một phần mà không có dedup contract.

## 12. Kiểm thử SDK: generator pass chưa phải quality gate

Một lần generate và compile thành công chỉ chứng minh một phần **syntactic compatibility**. Trước khi công bố bản SDK mới, cần kiểm **wire contract, serialization, hành vi chính sách, lỗi và khả năng nâng cấp**.

### 12.1. Kim tự tháp kiểm thử

| Tầng | Điều cần chứng minh | Ví dụ |
|---|---|---|
| OpenAPI lint/validate | Spec parse được, operationId duy nhất, schemas/response hợp lệ | CI parser + rule set |
| Generation reproducibility | Cùng spec/tool/config sinh diff ổn định | Regenerate trong clean workspace, so output |
| Build/package | Generated code compile, test, Java version được hỗ trợ | Maven/Gradle với dependency lock |
| Serialization | Missing/null, enum unknown, time/decimal, polymorphism | Golden JSON snapshots, round-trip |
| HTTP adapter | Status, headers, Problem Details, CORS nếu browser | Fake HTTP server/WireMock/MockWebServer |
| SDK policy | Token/redirect/retry/idempotency/timeout/pagination | Unit test với fake clock/transport |
| Consumer contract | New SDK với server cũ/mới; SDK cũ với server mới | Compatibility matrix |
| End-to-end | TLS, auth, rate limit, DB, concurrent PATCH, operation monitor | Integration environment sandbox |

Một HTTP mock trả response theo OpenAPI **không đủ** để chứng minh server production thực sự tuân spec; phải có test với server thực (hoặc provider contract tests). Ngược lại, end-to-end pass một đường happy path cũng không chứng minh SDK xử lý tri-state JSON, TLS redirect hay timeout đúng.

### 12.2. JUnit test façade: ETag cũ không bị bỏ qua

Ví dụ kiểm tra `OrderSdk` ở mục 7 với fake port, không phụ thuộc method names của generated library:

~~~java
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderSdkTest {
    @Test
    void staleIfMatchIsPreservedAndSurfaced() {
        AtomicReference<String> sentIfMatch =
            new AtomicReference<>();
        OrdersPort fake = new OrdersPort() {
            @Override
            public SdkHttpResponse<OrderDto> getOrder(String id) {
                return new SdkHttpResponse<>(
                    200, Map.of("ETag", List.of("\"ord-v7\"")),
                    new OrderDto(id, "DRAFT", "Old"));
            }

            @Override
            public SdkHttpResponse<OrderDto> patchNote(
                    String id, String ifMatch, NotePatch patch) {
                sentIfMatch.set(ifMatch);
                return new SdkHttpResponse<>(
                    412, Map.of(), null);
            }
        };

        OrderSdk sdk = new OrderSdk(fake);
        VersionedOrder current = sdk.get("ord_42");

        assertThrows(StaleOrderException.class,
            () -> sdk.updateNote(current, "New"));
        assertEquals("\"ord-v7\"", sentIfMatch.get());
    }
}
~~~

Test này **không chứng minh database optimistic locking đúng** — đó là trách nhiệm integration test phía server. Nó chứng minh SDK không quên `If-Match` hoặc tự đổi nó để PATCH vượt qua conflict. Thêm test `304` không deserialize body, `201` giữ Location, `429 Retry-After`, `401` refresh có giới hạn, `403` không refresh và `POST` timeout retry giữ **cùng key + body**.

### 12.3. Test transport với HTTP server giả

Với WireMock/MockWebServer hoặc test HTTP server tương đương, dựng phản hồi:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 2
X-Request-Id: req_test_1

{"type":"about:blank","title":"Unavailable","status":503}
~~~

Kiểm SDK:

1. Đọc được `status=503`, `Retry-After`, request ID, body lỗi an toàn.
2. Không retry trước 2 giây khi policy yêu cầu tôn trọng header; nếu deadline còn 1 giây thì **không retry**.
3. Có tối đa số attempts được cấu hình; cancellation kết thúc retry.
4. Nếu phản hồi `307 Location: https://untrusted.test/...`, **không gửi Bearer token** sang origin khác.
5. Không log `Authorization`, cookie, signed URL, raw request body nhạy cảm.

Fake clock/scheduler giúp test backoff không chờ thời gian thật; test mTLS/certificate/hostname nên chạy với môi trường TLS kiểm soát. Không tắt TLS verification để test “dễ hơn” rồi vô tình đưa cấu hình đó vào production.

### 12.4. Tương thích chéo và server contract

Một matrix tối thiểu khi phát hành:

| SDK | API v1 hiện hành | API v1 phiên bản mới | Ghi chú |
|---|---|---|---|
| SDK v1.3 (đang hỗ trợ) | PASS | **Phải PASS** với thay đổi backward-compatible | Server-first rollout |
| SDK v1.4 (sắp phát hành) | PASS nếu tính năng có mặt | PASS | Không bắt buộc endpoint chưa deploy |
| SDK v2.x (breaking) | Theo compatibility policy đã công bố | PASS | Hướng dẫn migration |

Đừng nhầm **API version ở URL** (`/v1`) với **SDK package version**: SDK có thể lên major do đổi public Java APIs trong khi HTTP API vẫn ở `/v1`. Ngược lại server có thể nâng minor/release mà không đòi SDK mới nếu wire contract vẫn tương thích.

### 12.5. CI pipeline đề xuất

~~~text
Change OpenAPI
  → validate + lint + check backward compatibility
  → generate bằng pinned toolchain
  → deterministic diff / build / dependency scan
  → serialization golden tests + unit policy tests
  → mock HTTP + provider contract + supported server matrix
  → SDK public API/binary compatibility check
  → version/release notes + samples + publish staging
  → consumer smoke test
  → publish release + SBOM/provenance + support monitoring
~~~

Mỗi mũi tên là **quality gate có owner**, không chỉ danh sách lệnh. CI phải thất bại nếu generated output thay đổi ngoài dự kiến hoặc method được rename trái quy ước. Có thể dùng OpenAPI diff tooling, nhưng tool tự động **không thay review ngữ nghĩa**: một schema “additive” vẫn có thể phá consumer do enum mới, default mới, thay authorization hay rate limiting.

## 13. Compatibility, SemVer và vòng đời deprecation

### 13.1. Kiểm tương thích ở ba lớp

| Lớp | Có thể bị phá dù các lớp khác ổn? | Ví dụ |
|---|---|---|
| **Wire/HTTP API** | Có | Xóa field, đổi status/Content-Type, yêu cầu scope mới |
| **Generated/public SDK source & binary** | Có | Rename method/model, đổi Java package, constructor, dependency ABI |
| **Behavioral** | Có | Retry POST nhiều lần, thay default timeout, redirect policy, xử lý unknown enum |

Ví dụ server thêm property response tùy chọn là **thường** backward-compatible ở JSON wire, nhưng SDK cũ cấu hình strict unknown fields có thể crash. Thêm enum value mới thường an toàn cho open-world clients nhưng có thể phá switch exhaustive ở Java/Kotlin. Đổi `operationId` có thể thay method name trong generated client dù HTTP URI/status không đổi.

### 13.2. SemVer là lời hứa của **SDK package**

Đội SDK có thể công bố:

- **PATCH**: bug fix, security patch, không đổi public source/binary API ngoài chính sách.
- **MINOR**: thêm tính năng/method backward-compatible, giữ method và behavior cũ.
- **MAJOR**: breaking changes có chủ đích, migration guide, deprecation window.

Đây là ví dụ áp dụng Semantic Versioning; mức tăng thực phải theo **chính sách package đã công bố**. Một thay đổi dependency major có thể gây lỗi ABI/runtime dù generated Java source không đổi; phải test với ứng dụng dùng dependency combinations được hỗ trợ.

Không hứa support “mọi JDK, mọi Spring version” nếu CI chỉ chạy Java 17. Công bố version matrix cụ thể (ví dụ Java 17+, server API v1, hỗ trợ đến ngày nào). Khi nâng generator, giữ binary compatibility của façade nếu có thể và chỉ nâng public major khi có phá vỡ hợp đồng.

### 13.3. Quy trình bỏ API/field an toàn

Giả sử `GET /v1/orders/{id}` sắp thay bằng API mới. Quy trình:

1. Đưa endpoint/field mới vào spec, hỗ trợ song song, phát hành SDK dùng cả hai.
2. Đánh dấu operation cũ `deprecated: true` trong OpenAPI, bổ sung docs và release notes.
3. Nếu dùng HTTP deprecation/sunset signaling, gửi header theo tiêu chuẩn và lịch cụ thể; không coi một header là thay thông báo cho consumers.
4. Có migration guide, examples (trước/sau), thời gian hỗ trợ và cách theo dõi adoption **không lộ user/tenant ID**.
5. Duy trì compatibility tests cho old SDK trong giai đoạn chuyển đổi; chỉ bỏ hành vi cũ theo lịch/policy.

Ví dụ migration không chỉ nói “đổi tên method”, mà phải hướng dẫn ETag/If-Match, auth scopes, pagination cursor, thay đổi schema và error types nếu chúng cũng đổi. Một endpoint mới trả `202` thay cho `201` tạo **thay đổi workflow** dù JSON body có vẻ tương tự.

## 14. Trách nhiệm bảo trì: ai thực sự sở hữu SDK?

Không nên viết trên trang tài liệu “SDK sinh tự động, không cần bảo trì” nếu khách hàng phụ thuộc binary đó. Một sự cố có thể do **spec sai**, **generator bug**, **HTTP adapter**, **server behavior**, hoặc **consumer sử dụng sai**; cần xác định chủ sở hữu và người phối hợp điều tra.

### 14.1. Ma trận trách nhiệm tối thiểu

| Việc | API owner | SDK maintainer | Platform/security | Consumer team |
|---|---|---|---|---|
| URI/method/status/schema/OpenAPI chính xác | **Chịu trách nhiệm chính** | Review developer experience | Review auth/privacy | Báo use case cần hỗ trợ |
| Pin generator/templates, regenerate | Cung cấp spec version | **Chịu trách nhiệm chính** | Scan supply-chain | Không tự sửa generated code |
| Generated adapter + façade Java | Thống nhất HTTP semantics | **Chịu trách nhiệm chính** | Review token/redirect/TLS | Dùng public API |
| Backward-compatible server rollout | **Chịu trách nhiệm chính** | Chạy SDK compatibility tests | Monitor auth/data leaks | Test ứng dụng trên staging |
| Maven package, docs, changelog, release | Cung cấp API release notes | **Chịu trách nhiệm chính** | CI signing/SBOM/secrets | Nâng version theo policy |
| Sự cố dữ liệu sai/quyền | **Điều tra server** | Tìm SDK reproduction | **Ứng cứu bảo mật** | Cung cấp dấu vết đã lọc |
| Deprecated operation và migration | Quyết định API timeline | Hướng dẫn SDK thay thế | Kiểm policy/retention | Lập kế hoạch chuyển đổi |

**Một bên phải có quyền quyết định cuối cùng** cho mỗi loại thay đổi. Tại tổ chức nhỏ, API owner và SDK maintainer có thể cùng một đội, nhưng trách nhiệm vẫn phải được ghi nhận trong repo/ownership rules và lịch trực xử lý bug.

### 14.2. Quy trình nhận bug không đổ lỗi cho người dùng

Một báo cáo “Java SDK timeout, curl vẫn chạy” cần được phân loại:

1. Xác minh SDK version, JDK, HTTP transport flavor, dependency graph, base URL và reproducible request **không chứa token thật**.
2. Ghi HTTP method/route template/status/trace ID/timing, không ghi raw Authorization hoặc nội dung nhạy cảm.
3. So sánh **generated call** và raw HTTP contract; kiểm method, headers, proxy, redirect, JSON serializer, timeout.
4. Tạo regression test trong lớp đúng: spec/server, adapter, façade hay consumer misuse.
5. Phát hành patch/version, changelog, hướng dẫn workaround nếu an toàn, và theo dõi adoption.

Không bắt consumer sửa mã generated thủ công hoặc “tắt TLS verification” để đi tiếp. Nếu lỗi thuộc server (ví dụ ghi sai `ETag`), sửa server và **giữ SDK test** để lỗi không tái diễn.

### 14.3. Security response và dependency maintenance

SDK là thư viện nằm trong ứng dụng bên thứ ba; một CVE ở HTTP/JSON dependency có thể ảnh hưởng hàng trăm consumers. Cần quy trình:

- Theo dõi CVE, runtime dependencies, giấy phép, SBOM/provenance, build integrity.
- Phát hành security fix theo thời hạn hỗ trợ đã cam kết, có advisory/migration guidance khi cần.
- Revocation/rotation publishing credentials; package registry permissions theo least privilege.
- Chính sách support window cho từng **major SDK**, JDK versions và server versions.
- Thu hồi/đánh dấu deprecated artifacts nguy hiểm theo quy định registry, nhưng không tự xóa package đang được consumers sử dụng nếu chưa có phương án chuyển đổi.

**Không thu thập telemetry SDK vượt mong đợi:** nhiều SDK chạy trong môi trường nhạy cảm; usage tracking phải opt-in/được công bố khi phù hợp, không âm thầm gửi URL, tenant ID, token hoặc body dữ liệu về nhà cung cấp SDK.

## 15. Tài liệu dùng SDK phải thực thi được và nói rõ giới hạn

Một trang README chỉ có:

~~~java
new OrdersApi().getOrder("ord_42");
~~~

chưa chỉ cách thiết lập token, handle 401/412, cấu hình timeout, phân trang hoặc nâng version. Ví dụ public nên đi theo **luồng người dùng thực**:

~~~java
// OrdersPort được binding vào generated client với token provider,
// base URL HTTPS và policy timeout/redirect đã cấu hình.
OrderSdk orders = new OrderSdk(ordersPort);

VersionedOrder first = orders.get("ord_42");
System.out.println(first.order().status());

try {
    VersionedOrder updated =
        orders.updateNote(first, "Giao cổng phụ");
    System.out.println(updated.etag());
} catch (StaleOrderException conflict) {
    // Reload, hiển thị diff/merge; KHÔNG bỏ If-Match.
    VersionedOrder latest = orders.get("ord_42");
    System.out.println(latest.order().deliveryNote());
}
~~~

Ví dụ này dùng các lớp minh họa ở mục 7, **không phải code generated tự sinh sẵn**; `ordersPort` phải được adapter hiện thực và cấu hình trong ứng dụng. Để README thật **copy/paste chạy được**, cung cấp một sample project riêng có pinned SDK dependency, test environment, token test và secret management; đừng đặt API key thật vào README.

### 15.1. Một gói tài liệu tối thiểu

1. **Quickstart:** yêu cầu Java/JDK, tọa độ Maven/Gradle, cách tạo `OrderSdk`, môi trường sandbox và request GET đầu tiên.
2. **Authentication:** OAuth2 client credentials vs user tokens, audience/scopes, refresh, mTLS nếu có; không hardcode secrets.
3. **Common workflows:** tạo đơn với idempotency, đọc ETag và PATCH có điều kiện, phân trang/cursor, upload/download, theo dõi `202` job.
4. **Error handling:** typed errors, Problem Details, status mapping, retryable vs business conflict.
5. **Configuration:** base URL, proxy/TLS, deadlines, backoff, concurrency, thread-safety, logs và observability.
6. **Compatibility:** SDK/API/JDK version matrix, changelog, migration guide, deprecated behavior, supported generator/runtime.
7. **Troubleshooting:** trace/correlation ID, cách tái hiện lỗi với token đã che, nơi báo security issue.

Một số cấu hình **không nên mặc định**: tự retry mọi POST, tự follow redirect qua origin khác, deserialize body vô hạn, in raw request/response khi debug, hoặc tự động bật thông tin telemetry không được công bố.

### 15.2. Definition of Done cho một release SDK

| Câu hỏi | Bằng chứng trước khi publish |
|---|---|
| Spec và server đồng bộ? | OpenAPI lint + provider contract tests |
| Generated output tái tạo được? | Pin tool/config và regenerate diff sạch |
| Public API giữ tương thích? | Java source/binary compatibility check và matrix |
| HTTP semantics đúng? | Tests 201/202/204/304/401/409/412/429/503 |
| Retry an toàn? | Same key/body, deadline, Retry-After, no replay unsafe |
| Bảo mật? | Token scoping, TLS, cross-origin redirect, redaction tests |
| Tài liệu đủ để dùng? | Quickstart chạy trên sandbox, examples đúng SDK version |
| Dependency an toàn? | Scan, SBOM/provenance, artifact signing theo policy |
| Người hỗ trợ được xác định? | Owners, support channel, release notes, deprecation plan |
| Dữ liệu riêng tư không rò? | No secrets in logs/metrics/examples, object ACL tests phía server |

Không đánh dấu release là **ready** nếu chỉ “generator command exit 0”. CI có thể automate nhiều hàng trong bảng, nhưng vẫn cần người review behavior, contract breaking changes và migration story.

## 16. Bài thực hành: phát hành Java SDK cho Orders API

**Bối cảnh:** đội cung cấp `INTEGRATION_API_REST` có API `/v1/orders`. Đang sinh Java client từ OpenAPI, nhưng consumer phàn nàn `getOrder()` không đọc được ETag, POST timeout gây duplicate, và SDK mới đổi tên method sau khi generator upgrade.

**Yêu cầu triển khai:**

1. Viết hoặc hoàn thiện OpenAPI 3.1 cho `listOrders/getOrder/createOrder/updateOrderNote`: operationId ổn định, request/response schemas, `Location`, `ETag`, `If-Match`, `Idempotency-Key`, `Retry-After` và `application/problem+json`.
2. Chọn generator Java và HTTP library flavor, **pin chính xác version/config/templates**; sinh code vào một thư mục tách khỏi mã viết tay.
3. Tạo `OrdersPort` adapter và `OrderSdk` façade trả `VersionedOrder`, hỗ trợ update note có If-Match; chứng minh consumer không phụ thuộc generated class names.
4. Tạo `TokenProvider` lấy token đúng audience, TLS/redirect policy không gửi Bearer sang host khác; có request deadline và retry budget.
5. Viết `createWithKey(...)` để retry cùng logical POST bằng **cùng key và body**. Dùng fake server mô phỏng response mất sau commit và xác minh không tạo hai orders.
6. Viết iterator phân trang có giới hạn; test cursor lặp, cursor hết hạn, 401/403 và cancellation.
7. Viết unit tests cho missing/null/value JSON, enum unknown và `OrderSdk` stale ETag; integration tests cho 201/204/304/412/429 và `Retry-After`.
8. Chạy compatibility matrix: SDK cũ trên server mới; SDK mới trên server hiện hành. Giải thích một thay đổi OpenAPI additive nhưng có thể làm generated client cũ crash.
9. Thử nâng generator major; đo source/binary API diff, lập migration guide nếu public method/model đổi.
10. Lập bảng trách nhiệm API owner/SDK maintainer/security/consumer, pipeline CI, cách phát hành Maven artifact và support policy ít nhất một major trước đó.

**Bài kiểm tra nâng cao:** server chuyển tạo đơn sang `202 Accepted` với operation monitor nhưng SDK vẫn trả `CreatedOrder` ngay. Đây là **behavioral breaking change**; hãy thiết kế một API façade trả `OperationHandle`, tài liệu hóa trạng thái `PENDING/COMPLETED/FAILED`, giữ error/security policy và lập migration plan.

**Tiêu chí đạt:** generated code có thể tái tạo; façade không làm mất HTTP status/headers; token không rò khi redirect; POST retry không tạo side effect trùng; PATCH không bỏ If-Match; phân trang bounded; có bằng chứng contract/compatibility/security tests và owner support rõ ràng.

## 17. Ghi nhớ

**OpenAPI là hợp đồng, generator là công cụ, SDK là sản phẩm được bảo trì.** Mã sinh giúp giảm boilerplate nhưng không quyết định thay bạn cách xử lý token, redirect, retry, deadline, idempotency, ETag, phân trang, error model hay deprecation. Hãy giữ generated code tách biệt, khóa generator/config, cung cấp façade có chủ đích, và dùng kiểm thử để bảo vệ hành vi HTTP.

Điều khó nhất không phải sinh `OrdersApi.java` lần đầu, mà là **duy trì tương thích và an toàn qua nhiều phiên bản API, generator, JDK và consumers**. SDK tốt có nhóm sở hữu, lịch support, release notes, regression tests và lộ trình migration rõ ràng — thay vì một thư mục source được generate rồi bỏ mặc.
