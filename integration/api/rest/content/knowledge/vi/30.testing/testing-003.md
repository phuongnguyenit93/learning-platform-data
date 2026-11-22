# REST Assured để kiểm thử giao diện HTTP

## 1. Vì sao cần kiểm thử từ phía HTTP?

Trong module **INTEGRATION_API_REST**, thiết kế REST API không chỉ là trả đúng JSON. Một endpoint phải tuân thủ **resource/URI, phương thức HTTP, mã trạng thái, header, hợp đồng dữ liệu, xác thực, phân quyền, cache, idempotency, phân trang và lỗi**. Kiểm thử chỉ gọi service method không thể chứng minh các thuộc tính này được thực thi đúng ở ranh giới HTTP.

**REST Assured** là thư viện Java giúp gửi HTTP request và kiểm tra response theo cú pháp gần với lời mô tả hành vi:

~~~java
given()
    .accept(ContentType.JSON)
.when()
    .get("/api/v1/products/{id}", productId)
.then()
    .statusCode(200)
    .contentType(ContentType.JSON)
    .body("id", equalTo(productId));
~~~

Một bài kiểm thử tốt sẽ trả lời: **Với đúng request, identity và trạng thái dữ liệu ban đầu, API phải phát HTTP response nào, đồng thời tạo hoặc không tạo side effect nào?**

**Mục tiêu bài học:**

1. Cài REST Assured với **JUnit 5** và Spring Boot test server chạy HTTP thật.
2. Viết test theo **Given–When–Then**, tái sử dụng request/response specifications mà không làm rò state giữa tests.
3. Kiểm **status, Content-Type, Location, ETag, Cache-Control, JSON body, schema, pagination và Problem Details**.
4. Kiểm xác thực/phân quyền thực tế, bao gồm **BOLA/IDOR**, multi-tenant và mass assignment.
5. Kiểm HTTP semantics của **POST, PATCH/If-Match, idempotency, 304, 429** và lỗi request.
6. Thiết kế fixtures, cách ly DB, chạy ở local/CI và phân biệt unit, integration, contract, end-to-end tests.
7. Tự xây một bộ kiểm thử REST có cả positive, negative, security và concurrency cases.

**Phạm vi:** ví dụ Java 17+, Spring Boot 3, Spring Security, JUnit Jupiter, REST Assured 5.x. Các class ứng dụng trong ví dụ (repository, Product DTO, token fixture) là hợp đồng giả định để người học triển khai, không phải code dự án có sẵn. Không tuyên bố phiên bản dependency minh họa là bản mới nhất.

## 2. REST Assured nằm ở đâu trong chiến lược kiểm thử?

| Mức kiểm thử | Ranh giới | Thế mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Unit test** | Method/service trong JVM | Logic nhanh, dễ cô lập | Không kiểm HTTP serialization/filter |
| **MockMvc** | Spring MVC với mock servlet request | Kiểm route, validation, filter, handler | Không mở TCP socket thật; không kiểm ingress/proxy |
| **REST Assured + RANDOM_PORT** | HTTP tới embedded Spring server | Kiểm HTTP stack, status, header, JSON và security filter | Chưa tự kiểm gateway/load balancer production |
| **REST Assured tới môi trường triển khai** | HTTP qua gateway/ingress | Kiểm rewrite, CORS, TLS, auth và headers tại đường public | Chậm hơn, phụ thuộc hạ tầng và dữ liệu |
| **Consumer-driven contract / OpenAPI validation** | So contract giữa client/provider | Phát hiện thay đổi schema/semantics | Không thay test quyền trên dữ liệu thật |

**REST Assured là HTTP client trong test**, không phải framework thay Spring Security hay DB. Nó gửi request giống client ngoài ứng dụng và assert kết quả. Nếu cấu hình test sử dụng **mock service trả sẵn response**, REST Assured vẫn chỉ chứng minh phần HTTP trước mock, không chứng minh service/DB thật.

Ví dụ bộ test có thể dùng **SpringBootTest(webEnvironment = RANDOM_PORT)** với DB thử nghiệm, token ký bởi issuer test, rồi sau đó chạy vài smoke tests REST Assured qua gateway staging. Cùng một request spec có thể tái sử dụng ý tưởng, nhưng phải quản lý host, dữ liệu và credentials riêng.

## 3. Hợp đồng API dùng xuyên suốt bài

Giả sử Catalog API đa tenant có các endpoints:

| Operation | Hợp đồng điển hình |
| --- | --- |
| **GET /api/v1/products/{id}** | 200 JSON + ETag; 404 khi không tồn tại/không được công bố |
| **GET /api/v1/products?limit=20&cursor=...** | 200, items + nextCursor, limit có giới hạn |
| **POST /api/v1/products** | 201 Created + Location, không nhận tenantId/client-owned fields |
| **PATCH /api/v1/products/{id}** | Yêu cầu If-Match, thành công 200/204 theo contract; stale 412 |
| **GET với If-None-Match** | 304 nếu representation hiện tại match validator |
| **Request thiếu token** | 401 + WWW-Authenticate phù hợp |
| **Token không đủ scope** | 403 hoặc 404 theo chính sách không tiết lộ |
| **Validation lỗi** | 400 hoặc 422 theo API contract, Problem Details |
| **Quá quota** | 429, có thể có Retry-After |

Ví dụ JSON thành công:

~~~http
GET /api/v1/products/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-v7"
Cache-Control: private, no-store

{
  "id": "11111111-1111-4111-8111-111111111111",
  "sku": "KB-001",
  "name": "Bàn phím cơ",
  "priceMinor": 2590000,
  "currency": "VND"
}
~~~

**Product ID, ETag, tenant và giá** là dữ liệu của fixture; không so cứng một ID ngẫu nhiên do DB tạo nếu test không kiểm soát dữ liệu đó. Cần xác định trước API dùng **404 để che cross-tenant resource**, hay **403** khi caller đã được phép biết resource tồn tại.

## 4. Cài dependency và cấu trúc project

Ví dụ Maven với Spring Boot 3 quản lý phiên bản dependency qua BOM/parent, JUnit 5 từ **spring-boot-starter-test**, REST Assured và JSON schema validator trong **test scope**:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>io.rest-assured</groupId>
    <artifactId>rest-assured</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>io.rest-assured</groupId>
    <artifactId>json-schema-validator</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Nếu BOM/parent của project không quản lý version một artifact**, phải khai báo phiên bản **tương thích** một cách tường minh hoặc thêm dependency management, không copy XML rồi giả định Maven luôn resolve được. Giữ các REST Assured modules đồng bộ version, kiểm API Java/JUnit compatibility theo runtime dự án. Đặc biệt nên kiểm dependency tree khi test classpath có các phiên bản Groovy/JSONPath khác nhau.

REST Assured chủ yếu sử dụng các thành phần:

- **io.restassured.RestAssured**: điểm vào **given/when/then**.
- **io.restassured.builder.RequestSpecBuilder**: chuẩn hóa base URI, port, headers và filters.
- **io.restassured.builder.ResponseSpecBuilder**: assert chung cho nhiều responses.
- **org.hamcrest.Matchers**: **equalTo, hasSize, notNullValue, greaterThan**.
- **io.restassured.path.json.JsonPath**: trích xuất JSON bằng biểu thức phù hợp.
- **io.restassured.module.jsv.JsonSchemaValidator**: kiểm JSON Schema theo capability/version của module.

**Tổ chức test:** tách **test fixtures**, **HTTP specifications**, **positive tests**, **security-negative tests**, **contract/schema tests** và **performance/load tests**. REST Assured không phải công cụ load test chuyên dụng; kiểm throughput lớn dùng công cụ khác nhưng vẫn có thể tái sử dụng test expectations.

## 5. Test đầu tiên chạy qua embedded HTTP server

Không cần deploy WAR riêng: **@SpringBootTest(webEnvironment = RANDOM_PORT)** khởi động ứng dụng với port HTTP ngẫu nhiên. Test dùng **@LocalServerPort** để tạo request tới đúng port.

~~~java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static io.restassured.RestAssured.given;
import static io.restassured.http.ContentType.JSON;
import static org.hamcrest.Matchers.equalTo;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class ProductHttpIT {

    @LocalServerPort
    int port;

    @Autowired
    TestTokenFactory tokens;

    private RequestSpecification api() {
        return new RequestSpecBuilder()
            .setBaseUri("http://localhost")
            .setPort(port)
            .setBasePath("/api/v1")
            .setAccept(JSON)
            .build();
    }

    @Test
    void getProductReturnsExpectedJson() {
        String productId =
            "11111111-1111-4111-8111-111111111111";
        String token = tokens.forTenantReader("tenant-a");

        given()
            .spec(api())
            .auth().oauth2(token)
        .when()
            .get("/products/{id}", productId)
        .then()
            .statusCode(200)
            .contentType(JSON)
            .body("id", equalTo(productId))
            .body("sku", equalTo("KB-001"))
            .body("currency", equalTo("VND"));
    }
}
~~~

**TestTokenFactory** là fixture giả định tạo token test **được Spring Security Resource Server của ứng dụng test xác minh đúng** (issuer, audience, signature, expiry, scopes và tenant claim). Không tự gắn token bất kỳ rồi tắt authentication filter để test pass. Fixture product cần được seed với ID trên hoặc tạo qua API setup có quyền.

**Vì sao dùng RequestSpecBuilder thay cho RestAssured.port static?** REST Assured có trạng thái global như baseURI/port, có thể gây nhiễu khi chạy nhiều class hoặc test song song. Spec per-test/context hạn chế rò cấu hình, dễ chạy trên port ngẫu nhiên. Với môi trường CI, baseURI phải đến từ **test config đáng tin**, không nhận full URL do untrusted test data cung cấp.

### 5.1. Given–When–Then có ý nghĩa gì?

- **given()**: thiết lập request, ví dụ method path, token, content type, query, body, headers.
- **when()**: thực hiện một HTTP call.
- **then()**: kiểm response status, headers, content type, body.
- **extract()**: lấy ID, ETag hoặc response body để dùng ở bước tiếp theo.

Không đặt side effects ẩn trong một reusable spec mà test khác không biết, ví dụ token của user A hoặc Idempotency-Key cố định dùng chung. HTTP calls có thể có side effects: test POST/PATCH phải làm dữ liệu được cách ly, không dựa test chạy đúng thứ tự.

## 6. Đọc status, header, JSON body và trích xuất dữ liệu

REST Assured hỗ trợ Hamcrest assertions ở JSON paths:

~~~java
given().spec(api()).auth().oauth2(readerToken)
.when()
    .get("/products/{id}", productId)
.then()
    .statusCode(200)
    .header("ETag", notNullValue())
    .header("Cache-Control", containsString("no-store"))
    .contentType(JSON)
    .body("name", not(isEmptyOrNullString()))
    .body("priceMinor", greaterThanOrEqualTo(0))
    .body("currency", equalTo("VND"));
~~~

Nếu API thực sự công bố **priceMinor** là số nguyên lớn, JSON number có thể được REST Assured deserialize thành **Integer, Long hoặc kiểu số khác tùy kích thước/config**. Không assert sai kiểu Java khi điều cần kiểm là giá trị. Đối với tiền, giá trị lấy từ fixture nên so sánh chính xác với policy decimal/minor units, không dùng float gần đúng.

**Trích xuất response có kiểm soát:**

~~~java
Response response =
    given().spec(api()).auth().oauth2(readerToken)
    .when()
        .get("/products/{id}", productId)
    .then()
        .statusCode(200)
        .extract().response();

String etag = response.getHeader("ETag");
String sku = response.jsonPath().getString("sku");

assertNotNull(etag);
assertEquals("KB-001", sku);
~~~

Các import bổ sung: **io.restassured.response.Response**, **org.junit.jupiter.api.Assertions** và các **org.hamcrest.Matchers** tương ứng.

### 6.1. Test JSONPath nên kiểm cấu trúc, không chỉ một field

~~~java
given().spec(api()).auth().oauth2(readerToken)
.when()
    .get("/products?limit=2")
.then()
    .statusCode(200)
    .body("items", hasSize(lessThanOrEqualTo(2)))
    .body("items.id", everyItem(notNullValue()));
~~~

JSONPath trong REST Assured dựa trên **Groovy GPath-style expressions**. Kiểm cách truy cập field nếu response là array, object lồng nhau hoặc có key chứa dấu đặc biệt. Tránh assert chính xác **thứ tự JSON object fields**: JSON object không bảo đảm thứ tự key; thay vì so raw string nên kiểm semantic values.

## 7. RequestSpecification và ResponseSpecification để giảm lặp

Tách spec theo **HTTP invariants**, không cố nhét mọi kỳ vọng vào một spec toàn cục:

~~~java
RequestSpecification readerSpec(int port, String token) {
    return new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(port)
        .setBasePath("/api/v1")
        .setAccept(ContentType.JSON)
        .addHeader("Authorization", "Bearer " + token)
        .build();
}

ResponseSpecification okJson() {
    return new ResponseSpecBuilder()
        .expectStatusCode(200)
        .expectContentType(ContentType.JSON)
        .build();
}
~~~

~~~java
given()
    .spec(readerSpec(port, readerToken))
.when()
    .get("/products/{id}", productId)
.then()
    .spec(okJson())
    .body("id", equalTo(productId));
~~~

**Cẩn trọng với response specs:** response **201**, **204**, **304**, **401 Problem Details** không thỏa một spec 200 JSON chung. Định nghĩa spec đúng từng contract. Request spec có token **per test**; không dùng token hardcode ở shared static spec, không leak qua debug logs. Nếu test chạy parallel, ưu tiên immutable specs và tài nguyên fixture độc lập.

## 8. Test POST 201 Created, Location và thực thể vừa tạo

~~~java
@Test
void createProductReturns201AndResolvableLocation() {
    String adminToken = tokens.forTenantAdmin("tenant-a");
    String payload = """
        {
          "sku":"KB-NEW-001",
          "name":"Bàn phím thử nghiệm",
          "priceMinor":2590000,
          "currency":"VND"
        }
        """;

    Response created =
        given().spec(api())
            .auth().oauth2(adminToken)
            .contentType(ContentType.JSON)
            .body(payload)
        .when()
            .post("/products")
        .then()
            .statusCode(201)
            .header("Location", not(isEmptyOrNullString()))
            .extract().response();

    String id = created.jsonPath().getString("id");
    assertNotNull(id);

    String location = created.header("Location");
    assertTrue(location.endsWith("/products/" + id));

    given().spec(api())
        .auth().oauth2(adminToken)
    .when()
        .get("/products/{id}", id)
    .then()
        .statusCode(200)
        .body("sku", equalTo("KB-NEW-001"));
}
~~~

**Location có thể là URI tương đối hoặc tuyệt đối** theo thiết kế API. Test nên kiểm nó trỏ tới resource vừa tạo và có đường public đúng khi chạy qua proxy; không hardcode Host/port sai deployment. Nếu server trả 201 kèm body, kiểm ID đồng nhất giữa Location và representation. Nếu creation bị async, **202 Accepted** + status resource mới là hợp đồng đúng; không ép API trả 201 khi chưa tạo thực thể.

**Dữ liệu test phải dọn sạch hoặc được cách ly**. Không tạo một SKU cố định trong DB dùng chung giữa tests mà không reset trạng thái trước/sau; nếu chạy lại có thể bị 409 do unique constraint.

## 9. Xác thực và phân quyền: kiểm đường đi HTTP thực

Authentication và authorization dễ bị che bởi test gọi trực tiếp service hoặc mock controller. REST Assured gửi request qua **Spring Security filter chain**, nên có thể kiểm cả **401, WWW-Authenticate, 403/404, scope và tenant/object ACL**.

### 9.1. Không có token, token hết hạn, thiếu scope

~~~java
@Test
void missingBearerTokenReturns401() {
    given().spec(api())
    .when()
        .get("/products/{id}", seededProductId)
    .then()
        .statusCode(401)
        .header("WWW-Authenticate",
            containsString("Bearer"));
}

@Test
void validTokenWithoutWritePermissionReturns403() {
    String reader = tokens.forTenantReader("tenant-a");

    given().spec(api())
        .auth().oauth2(reader)
        .contentType(ContentType.JSON)
        .body(validCreateProductJson())
    .when()
        .post("/products")
    .then()
        .statusCode(403);
}
~~~

Test với **token hết hạn** cần token **đã ký hợp lệ nhưng exp ở quá khứ**; token ngẫu nhiên hoặc sai signature chỉ chứng minh nhánh invalid token, không chứng minh expiry validation. Nếu dùng OIDC/JWT, còn cần kiểm sai **issuer, audience, nbf, scope** và key rotation theo security policy.

Không dùng **@WithMockUser** như bằng chứng bearer HTTP được xác minh: annotation thường tạo SecurityContext cho test thread, còn REST Assured gửi request qua socket và request thread khác. Nên dùng signed token fixture, issuer thử nghiệm hoặc phương án test auth integration có chủ đích. Đừng tắt SecurityFilterChain để lấy trạng thái 200 trong bài kiểm thử xác thực.

### 9.2. BOLA/IDOR và multi-tenant

Giả sử product B thuộc tenant B và không được công bố cho tenant A. Một test chỉ thử token hợp lệ là chưa đủ; cần thử **cùng ID với hai danh tính khác nhau**:

~~~java
@Test
void foreignTenantProductIsNotVisible() {
    String tenantAReader = tokens.forTenantReader("tenant-a");

    given().spec(api())
        .auth().oauth2(tenantAReader)
    .when()
        .get("/products/{id}", productOwnedByTenantB)
    .then()
        .statusCode(404);
}
~~~

**404** ở đây là lựa chọn policy nhằm che sự tồn tại của tài nguyên tenant khác. Một hệ thống chọn **403** cũng có thể hợp lệ khi đã được phép biết object tồn tại; test phải bám contract. Quan trọng nhất: **response không chứa tên, tenantId, ownerId hoặc dữ liệu của product B**, và không có side effect.

Thêm ca: token tenant A có products:read nhưng không có quyền sửa object; tenantId do client truyền trong query/body không được quyền ghi đè trusted tenant từ principal; API không được đổi quyền chỉ vì request gửi **Origin** hoặc role tùy ý.

### 9.3. Mass assignment và thuộc tính không được ghi

Nếu request tạo product chỉ cho phép **sku, name, priceMinor, currency** theo role, client không được tự đặt **tenantId, ownerId, approved, createdBy**:

~~~java
String maliciousPayload = """
    {
      "sku":"KB-UNTRUSTED",
      "name":"Injected product",
      "priceMinor":10,
      "currency":"VND",
      "tenantId":"tenant-b",
      "approved":true
    }
    """;

given().spec(api())
    .auth().oauth2(adminTenantAToken)
    .contentType(ContentType.JSON)
    .body(maliciousPayload)
.when()
    .post("/products")
.then()
    .statusCode(400);
~~~

**Status 400 chỉ là ví dụ nếu contract cấu hình reject unknown/forbidden fields.** Một API dùng DTO allowlist có thể bỏ qua unknown fields theo chính sách; khi đó test phải kiểm **DB vẫn ghi đúng trusted tenant và không ghi approved=true**. Không nhận response 201 rồi suy rằng server không bị mass assignment nếu chưa kiểm dữ liệu đã lưu.

## 10. Kiểm lỗi request và Problem Details

REST contract cần kiểm cả trường hợp không thành công. Đối với **application/problem+json** theo RFC 9457:

~~~java
@Test
void invalidPriceReturnsSafeProblemDetails() {
    String payload = """
        {"sku":"KB-X","name":"Invalid",
         "priceMinor":-1,"currency":"VND"}
        """;

    given().spec(api())
        .auth().oauth2(adminToken)
        .contentType(ContentType.JSON)
        .body(payload)
    .when()
        .post("/products")
    .then()
        .statusCode(400)
        .contentType("application/problem+json")
        .body("type", notNullValue())
        .body("title", not(isEmptyOrNullString()))
        .body("status", equalTo(400))
        .body("code", equalTo("INVALID_PRODUCT"));
}
~~~

**INVALID_PRODUCT** là mã domain minh họa; tên code và 400/422 phải khớp contract dự án. Đừng dựa vào nội dung tiếng Anh/Vietnamese của **detail** nếu thông điệp có localization hoặc thay đổi không ảnh hưởng hợp đồng; nên assert **code/type/status/invalidParams** ổn định.

Ma trận cơ bản:

| Request | Response theo contract | Điều không được xảy ra |
| --- | --- | --- |
| JSON syntax sai | **400** | Java stack trace |
| Field bắt buộc thiếu | **400/422** | Bỏ qua validation rồi commit |
| JSON body khi endpoint chỉ nhận XML | **415** | Handler chạy với dữ liệu sai |
| Accept không tương thích @Produces | **406** | Response sai media type |
| HTTP method không được hỗ trợ | **405**, có thể có **Allow** | POST bị xử lý như GET |
| Resource không thấy | **404** | Lộ tenant/owner của tài nguyên bị che |
| Request không auth | **401** + challenge phù hợp | Bỏ JWT filter |
| Request không đủ quyền | **403/404** | Side effect vẫn commit |
| Rate limit đạt ngưỡng | **429**, Retry-After nếu được quy định | Counter/quota bị bypass |

**Content-Type** mô tả representation của request/response; **Accept** là sở thích của client đối với response. Đừng viết test chỉ assert body mà quên test media type. Với 204/304, không nên yêu cầu JSON body.

## 11. JSON Schema validation và contract tests

Assert một số JSONPath cần thiết nhưng chưa đủ để phát hiện **mất required field, sai kiểu, thêm trường nhạy cảm hoặc đổi shape collection**. REST Assured có module **json-schema-validator**; schema có thể được lưu trong test resources để đồng bộ với hợp đồng provider.

Ví dụ tạo resource ở **src/test/resources/schemas/product.json** trong dự án minh họa (chỉ là mô tả cấu trúc test, không phải tệp cần tạo trong nhiệm vụ STEP_4 này):

~~~json
{
  "type": "object",
  "required": ["id", "sku", "name", "priceMinor", "currency"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string" },
    "sku": { "type": "string", "minLength": 1 },
    "name": { "type": "string", "minLength": 1 },
    "priceMinor": { "type": "integer", "minimum": 0 },
    "currency": { "type": "string" }
  }
}
~~~

Kiểm schema:

~~~java
import static io.restassured.module.jsv.JsonSchemaValidator
    .matchesJsonSchemaInClasspath;

given().spec(api()).auth().oauth2(readerToken)
.when()
    .get("/products/{id}", seededProductId)
.then()
    .statusCode(200)
    .body(matchesJsonSchemaInClasspath(
        "schemas/product.json"));
~~~

**Chú ý:** JSON Schema validator của phiên bản REST Assured đang dùng có thể không hỗ trợ đầy đủ mọi keyword của **OpenAPI 3.1 / JSON Schema 2020-12**. Không ngầm coi việc test JSON Schema thành công là đã kiểm OpenAPI path/method/status/security. Chọn draft được module hỗ trợ, kiểm version và dùng công cụ OpenAPI validator chuyên biệt khi cần.

**additionalProperties: false** chỉ phù hợp nếu response contract cấm thêm field. Với API chủ trương additive evolution, client có thể phải chấp nhận unknown response fields; khi đó cần schema và compatibility policy tương ứng. Nhưng với request DTO security-critical, vẫn nên từ chối hoặc bỏ qua fields không được phép và kiểm DB để chống mass assignment.

### 11.1. Schema không kiểm được tất cả bất biến

Schema có thể nói **priceMinor là integer**, nhưng không chứng minh giá lấy từ nguồn tin cậy hoặc product thuộc đúng tenant. Test cần kết hợp:

- **HTTP structure:** required fields, Content-Type, schema.
- **Nghiệp vụ:** tiền, tồn kho, state transition, idempotency.
- **Security:** tenant/owner/field authorization và dữ liệu bị che.
- **Consistency:** revision/ETag, transaction side effects.
- **Compatibility:** các trường bắt buộc và status/header không thay đổi trái contract.

## 12. Phân trang, lọc, sắp xếp và giới hạn truy vấn

Một list endpoint dễ trả đúng 200 nhưng sai **limit, cursor, sort, ACL hoặc count**. Test phải seed dữ liệu đủ vượt quá một trang và phân biệt dữ liệu trong nhiều tenant.

~~~java
@Test
void paginationDoesNotDuplicateItemsAcrossPages() {
    String cursor = null;
    Set<String> ids = new HashSet<>();
    boolean finished = false;

    for (int pageIndex = 0; pageIndex < 20; pageIndex++) {
        RequestSpecification request = given()
            .spec(api())
            .auth().oauth2(readerToken)
            .queryParam("limit", 5);

        if (cursor != null) {
            request.queryParam("cursor", cursor);
        }

        Response page = request.when()
            .get("/products")
            .then()
            .statusCode(200)
            .extract().response();

        List<String> pageIds =
            page.jsonPath().getList("items.id", String.class);
        assertTrue(pageIds.size() <= 5);
        for (String id : pageIds) {
            assertTrue(ids.add(id), "Duplicate item: " + id);
        }

        cursor = page.jsonPath().getString("nextCursor");
        if (cursor == null) {
            finished = true;
            break;
        }
    }

    assertTrue(finished, "Pagination did not terminate");
}
~~~

**Giới hạn 20 pages** là guard chống vòng lặp vô hạn trong test; fixture phải có số bản ghi phù hợp. Ngoài không trùng lặp, cần kiểm **không bỏ sót item** dựa trên fixture ổn định, sort deterministic (ví dụ **createdAt DESC, id DESC**), cursor thuộc đúng query/tenant, và không có item tenant khác.

Các test quan trọng khác:

- **limit=0, limit âm, limit quá max** → 400 hoặc clamp theo contract; không truy vấn không giới hạn.
- **Sort field tùy ý, filter injection** → chỉ allowlist, không SQL injection.
- **Cursor bị chỉnh sửa/đến từ tenant khác** → reject hoặc xử lý an toàn theo API.
- **Total count/facets** → chỉ tính tập đã authorize; không rò dữ liệu ẩn.
- **Có record mới trong lúc phân trang** → contract cần chọn snapshot/keyset semantics; không thể mong kết quả cố định trong mọi tình huống concurrent writes.

## 13. Conditional requests, ETag và optimistic concurrency

REST Assured phù hợp để test **header-driven state transitions**, thay vì chỉ assert dữ liệu sau PATCH.

### 13.1. If-None-Match và 304 cho GET

~~~java
@Test
void matchingETagReturns304WithoutBody() {
    Response first =
        given().spec(api()).auth().oauth2(readerToken)
        .when()
            .get("/products/{id}", seededProductId)
        .then()
            .statusCode(200)
            .extract().response();

    String etag = first.header("ETag");
    assertNotNull(etag);

    Response second =
        given().spec(api())
            .auth().oauth2(readerToken)
            .header("If-None-Match", etag)
        .when()
            .get("/products/{id}", seededProductId)
        .then()
            .statusCode(304)
            .extract().response();

    assertEquals("", second.asString());
}
~~~

**ETag** phải là validator thực của selected representation, không phải chuỗi tùy ý test tự tạo. Trường hợp response **304 không có message body** theo HTTP semantics; không yêu cầu Content-Type JSON và body mới như 200. Cần kiểm thêm Cache-Control/Vary/authorization trên route có cache cá nhân hóa; một 304 không được bypass object ACL hoặc trả dữ liệu qua shared cache sai scope.

### 13.2. If-Match ngăn lost update

Nếu API yêu cầu **If-Match** cho PATCH, test ba bước: lấy ETag hiện tại, update thành công, dùng ETag cũ để cập nhật lần nữa.

~~~java
@Test
void staleIfMatchFailsWith412() {
    String etag = given().spec(api())
        .auth().oauth2(editorToken)
        .get("/products/{id}", seededProductId)
        .then().statusCode(200)
        .extract().header("ETag");

    given().spec(api())
        .auth().oauth2(editorToken)
        .header("If-Match", etag)
        .contentType("application/merge-patch+json")
        .body("{\"name\":\"Bàn phím cập nhật\"}")
    .when()
        .patch("/products/{id}", seededProductId)
    .then()
        .statusCode(204);

    given().spec(api())
        .auth().oauth2(editorToken)
        .header("If-Match", etag)
        .contentType("application/merge-patch+json")
        .body("{\"name\":\"Ghi đè sai\"}")
    .when()
        .patch("/products/{id}", seededProductId)
    .then()
        .statusCode(412);

    given().spec(api()).auth().oauth2(editorToken)
        .get("/products/{id}", seededProductId)
    .then()
        .statusCode(200)
        .body("name", equalTo("Bàn phím cập nhật"));
}
~~~

**Hợp đồng minh họa:** PATCH hỗ trợ JSON Merge Patch, thành công trả 204, không kèm body. API khác có thể trả 200 với representation; test phải bám hợp đồng đã công bố. Thiếu If-Match có thể trả **428 Precondition Required** nếu server bắt buộc precondition. Với dữ liệu nhạy cảm, **authorization phải được kiểm trước khi tiết lộ version hoặc thay đổi**, và DB update phải có CAS/@Version để tránh TOCTOU.

## 14. Idempotency-Key và retry sau response bị mất

POST có thể thành công ở server nhưng client mất response; thử lại không được tạo **hai sản phẩm hoặc hai đơn hàng** khi contract có idempotency.

~~~java
@Test
void sameIdempotencyKeyDoesNotCreateSecondProduct() {
    String key = UUID.randomUUID().toString();
    String payload = validCreateProductJson();

    Response first = given().spec(api())
        .auth().oauth2(adminToken)
        .header("Idempotency-Key", key)
        .contentType(ContentType.JSON)
        .body(payload)
    .when()
        .post("/products");

    Response retry = given().spec(api())
        .auth().oauth2(adminToken)
        .header("Idempotency-Key", key)
        .contentType(ContentType.JSON)
        .body(payload)
    .when()
        .post("/products");

    assertEquals(201, first.statusCode());
    assertEquals(201, retry.statusCode());
    assertEquals(first.path("id"), retry.path("id"));
}
~~~

**Hai lần 201** là chính sách replay **minh họa**, không phải yêu cầu chung của HTTP; một API có thể chọn status replay khác nếu contract công bố. Test đúng phải kiểm **cùng business result, không có duplicate DB rows, key scoped theo tenant/actor/operation và request fingerprint**. Gửi **cùng key nhưng payload khác** phải bị xử lý conflict theo policy (thường 409), không lặng lẽ áp dữ liệu mới. Đồng thời thử **hai POST concurrent cùng key** để phát hiện race dedup.

Nếu API không hỗ trợ Idempotency-Key, **không mặc định retry POST** chỉ vì client gặp timeout. Test mạng mất response có thể dùng fault proxy và kiểm DB outcome, không chỉ gửi POST hai lần bình thường.

## 15. CORS, content negotiation và giới hạn tốc độ

REST Assured **không phải trình duyệt**: nó không tự thực thi chính sách CORS và không chặn JavaScript đọc response. Nhưng nó có thể kiểm **header/status** của preflight và actual response ở Spring Security/gateway.

### 15.1. Preflight OPTIONS không cần Bearer token

~~~java
@Test
void corsPreflightWorksWithoutAccessToken() {
    given().spec(api())
        .header("Origin", "https://app.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
                "authorization,content-type")
    .when()
        .options("/products")
    .then()
        .statusCode(anyOf(is(200), is(204)))
        .header("Access-Control-Allow-Origin",
                equalTo("https://app.example.test"))
        .header("Access-Control-Allow-Methods",
                containsString("POST"));
}
~~~

**Preflight không mang token trong ví dụ**; CORS processor phải xử lý trước yêu cầu bearer của request thực. Sau đó test actual request **không có token** vẫn phải nhận **401**, kể cả khi Origin được cho phép. Một origin lạ không được nhận allow-origin phù hợp.

**Chỉ curl/REST Assured test headers chưa đủ chứng minh behavior của browser.** Với SPA thực, dùng Playwright hoặc browser integration test để kiểm browser có gửi request thực hay chặn sau preflight, kiểm cookie/SameSite, **credentials: include**, CSRF token và JavaScript đọc được ETag/Location khi **Access-Control-Expose-Headers** được cấu hình.

### 15.2. Accept, Content-Type, method và các body rỗng

Các case nên bổ sung:

~~~java
given().spec(api())
    .auth().oauth2(readerToken)
    .accept("application/xml")
.when()
    .get("/products/{id}", seededProductId)
.then()
    .statusCode(406);
~~~

Ví dụ trên chỉ đúng khi endpoint **không hỗ trợ application/xml** và contract yêu cầu 406. Với POST sai Content-Type có thể nhận 415. Với DELETE thành công **204 No Content**, assert body thực sự rỗng; với 304 cũng vậy. Khi endpoint trả binary file hoặc multipart, assert content type, kích thước/checksum và header **Content-Disposition**, không cố parse tất cả response thành JSON.

### 15.3. Rate limiting 429

~~~java
given().spec(api())
    .auth().oauth2(readerToken)
.when()
    .get("/products/{id}", seededProductId)
.then()
    .statusCode(429)
    .header("Retry-After", notNullValue());
~~~

Đây là **assertion cho tình huống đã chủ động kích hoạt quota**, không phải test GET bình thường; test phải cấu hình **rate limiter fake/test profile**, seed số lần gọi và bảo đảm một identity đã chạm ngưỡng. Không cho tests chạy song song chia sẻ bucket làm kết quả ngẫu nhiên. **Retry-After** không bắt buộc trong mọi 429, chỉ assert nếu hợp đồng có quy định.

## 16. Fixtures, giao dịch, DB và kiểm thử bất đồng bộ

Một HTTP integration test đáng tin phải kiểm soát **trạng thái ban đầu** và **side effects**. Với ví dụ GET/POST/PATCH, các fixtures cần:

- Tenant A và B có product IDs phân biệt; vài product được chia sẻ, vài product private.
- Principal A có read, principal B không có read; admin/editor và token expired.
- Product revision/ETag ban đầu ổn định; inventory/price dữ liệu hợp lệ.
- Dữ liệu đủ tạo ít nhất **hai trang** và kiểm boundary limit/cursor.
- Idempotency store sạch, rate limit store độc lập, cache có thể reset theo test.
- Đồng hồ điều khiển được khi test TTL, expiration, Retry-After hoặc cache revalidation.

**Bẫy thường gặp:** đánh dấu JUnit test **@Transactional** rồi nghĩ các thay đổi do HTTP request sẽ rollback theo test thread. Với **RANDOM_PORT**, request chạy ở server thread/transaction khác, nên rollback trong test method **không tự rollback DB transaction của endpoint**.

Các phương án cô lập:

1. Seed dữ liệu trước test và cleanup sau test bằng cơ chế **có transaction riêng**; tránh xóa nhầm dữ liệu của class đang chạy song song.
2. Dùng database/container riêng cho suite hoặc test class, ví dụ **Testcontainers** với PostgreSQL thật nếu production dùng các tính năng locking/RLS/index/JSONB đặc thù.
3. Tạo **tenant namespace/UUID riêng mỗi test** và dùng unique SKU/key; dữ liệu được dọn theo định danh đã biết.
4. Với async job, dọn cả **queue messages, output objects, scheduled workers**; đợi trạng thái terminal bằng bounded polling.
5. Không phụ thuộc vào **thứ tự chạy test** để có dữ liệu từ test trước; mỗi test phải tự dựng preconditions.

### 16.1. Kiểm thử song song và race conditions

Đối với **If-Match** hoặc **Idempotency-Key**, gửi hai requests concurrent có thể giúp chứng minh DB CAS/dedup là atomic. Đồng bộ điểm xuất phát bằng barrier thay vì sleep tùy ý. Sau đó assert:

- Hai update cùng ETag ban đầu: theo contract **tối đa một** mutation commit, request còn lại trả 412 hoặc kết quả conflict thích hợp.
- Hai POST cùng Idempotency-Key: **một business object** được tạo, các responses có cùng outcome theo policy.
- Không có trường hợp record thuộc tenant khác bị thay đổi.
- Không suy kết quả chỉ qua response: kiểm DB/business audit và trạng thái cuối.

Các ca concurrent có thể phụ thuộc isolation level, reverse proxy hoặc DB khóa; chạy trên hạ tầng đủ gần production để tránh test pass giả.

### 16.2. Job bất đồng bộ và eventual consistency

Khi POST trả **202 Accepted + Location**, REST Assured có thể theo dõi status resource:

~~~java
Response accepted =
    given().spec(api())
        .auth().oauth2(adminToken)
        .contentType(ContentType.JSON)
        .body(validExportRequest())
    .when()
        .post("/exports")
    .then()
        .statusCode(202)
        .header("Location", notNullValue())
        .extract().response();

String statusUrl = accepted.header("Location");
// Poll statusUrl với giới hạn tổng thời gian, số lần và interval.
// Khẳng định state COMPLETE/FAILED/CANCELLED theo policy,
// kiểm tenant/owner quyền đọc job và file output.
~~~

**Không poll vô hạn hoặc Thread.sleep một khoảng cố định rồi assert ngay**; dùng polling có deadline (ví dụ Awaitility trong test environment) và cleanup sau test. Status URL có thể là relative hoặc absolute; kiểm origin khi truy cập URL tuyệt đối để không gửi token test đến host không tin cậy. Với export CSV, validate bytes/encoding và scope dữ liệu, không chỉ job state.

## 17. Logging, TLS và cấu hình CI an toàn

REST Assured có **request/response logging** để giúp chẩn đoán assertion failure, nhưng full logs có thể chứa bearer tokens, cookies, PII, signed URLs và raw request bodies.

**Quy tắc:**

- Chỉ ghi phương thức, route template, status, request ID, một số header không bí mật và sanitized response fragments.
- Blacklist/redact **Authorization, Cookie, Set-Cookie, Proxy-Authorization, signed URL query** trước khi xuất CI logs.
- Không bật **log().all()** cho test môi trường chia sẻ nếu chưa có redaction đáng tin.
- Khi response validation fail, lưu **expected vs actual** và correlation ID; không cần dump nguyên DB/customer JSON.
- Dùng structured assertion message để chỉ rõ contract nào sai: 201 không có Location, 401 thiếu challenge, 304 có body, v.v.

**TLS:** Khi test qua public gateway staging, xác minh certificate chain/hostname như client thật. Không dùng **relaxedHTTPSValidation()** chỉ để test xanh: nó che lỗi cấu hình TLS có thể xuất hiện ở production. Nếu môi trường test dùng CA nội bộ, cấp truststore phù hợp thay vì bỏ hostname verification.

**Môi trường CI:** chọn cấu hình khác nhau cho local test **RANDOM_PORT** và deployed tests **HTTPS base URI**. Không hardcode credential thật. Truyền test secrets qua secret manager/CI variables, cấp scope tối thiểu, luôn có cleanup và chặn tests ghi phá dữ liệu production.

### 17.1. Đừng để build báo xanh khi integration tests chưa chạy

**JUnit test discovery** phụ thuộc Maven Surefire/Failsafe hoặc cấu hình Gradle test task:

- Test class tên **ProductHttpTest** thường được Surefire chạy khi thực thi unit/test phase theo cấu hình mặc định.
- Test class tên **ProductHttpIT** trong ví dụ phần 5 thường được chạy bởi **Maven Failsafe** với executions **integration-test/verify** đã cấu hình.
- Nếu chưa cấu hình Failsafe, một **mvn test** có thể **bỏ qua các lớp có hậu tố IT** mà không báo lỗi. Kiểm báo cáo **số lượng test executed/skipped** trước khi kết luận PASS.
- Đối với kiểm thử qua deployed environment, tách suite read-only/safe write và cài cơ chế tạo/dọn dữ liệu thử nghiệm.

Một pipeline khả thi: **compile + unit → Spring HTTP integration → OpenAPI/contract validation → container/gateway smoke → security-negative → staging canary**. CI có thể chạy test schema/HTTP mỗi PR; các ca fault injection hoặc load test nặng chạy theo cadence phù hợp.

## 18. Những anti-pattern khi viết REST Assured tests

| Anti-pattern | Tác hại | Cách sửa |
| --- | --- | --- |
| Assert chỉ **statusCode(200)** | Không thấy sai header, schema, quyền hoặc nội dung | Assert status + content type + body + side effects |
| Hardcode test order | Suite flaky khi chạy riêng/parallel | Mỗi test tự seed fixture |
| Shared RestAssured.port static bị thay đổi | Test khác class gọi nhầm server | RequestSpecification theo port/context |
| Test authentication với filters bị tắt | 401/403 pass giả | Signed token fixture, full Spring Security chain |
| Chỉ mock service và gọi REST Assured | Không kiểm DB/ACL thực | Integration tests kiểm tenant/DB và negative paths |
| POST retry không kiểm DB | Trùng đơn/transaction nhưng HTTP vẫn xanh | Assert business outcome/idempotency store |
| So raw JSON string | Hỏng vì whitespace/key order | JSONPath/schema/semantic comparison |
| Chỉ kiểm happy path | Bỏ qua 400/401/403/404/409/412/429/5xx | Test matrix theo HTTP contract |
| Test async bằng sleep | Flaky theo CPU/network CI | Poll có deadline |
| Dùng production token, tắt TLS | Lộ secrets, test bảo mật sai | Test identities, proper truststore |
| Log mọi request/response | Lộ Authorization, PII, signed URL | Redaction/logging có chủ đích |

**Phân biệt bug của API với bug của test:** giá trị test kỳ vọng có thể lỗi do fixture, auth token hết hạn, timezone, cache, race hoặc gateway rewrite. Khi một assertion fail, kiểm request đã đến đúng server nào, state DB ban đầu và request ID trước khi sửa contract hay vô hiệu security.

## 19. Bài thực hành: xây bộ REST Assured tests cho Catalog API

**Bối cảnh:** Spring Boot 3 + Spring Security có Catalog API đa tenant. Product có **id, sku, name, priceMinor, currency, revision**. API hỗ trợ GET/POST/PATCH, list cursor, ETag/If-Match và Idempotency-Key. Cần một bộ test chạy bằng JUnit 5 và REST Assured qua port HTTP thật.

**Nhiệm vụ (100 điểm):**

1. **Cấu hình và happy path – 20:** tạo RequestSpecification theo RANDOM_PORT, token fixture; GET 200 kiểm JSON/schema; POST 201 kiểm Location và GET lại product mới.
2. **HTTP semantics – 25:** kiểm Content-Type/Accept, 400/404/405/415, GET If-None-Match→304, PATCH If-Match→204 và stale→412.
3. **Security và dữ liệu – 25:** thiếu token→401, thiếu scope→403, ID tenant khác→404 theo policy; không mass assignment, không rò field/tenant qua error/cache.
4. **Resilience và consistency – 20:** cursor pagination, Idempotency-Key retry không trùng, 429 theo rate limit test profile, một ca concurrent write.
5. **Vận hành test – 10:** fixtures độc lập, DB cleanup, không log token, CI thực sự chạy mọi test và báo cáo test count.

**Gợi ý triển khai:**

- Bắt đầu một **ProductHttpTest** và giữ mỗi test độc lập; dùng test DB hoặc container.
- Khi GET, assert **200 + application/json + id/sku/priceMinor**; lấy ETag từ response thực cho conditional requests.
- Khi POST, tạo SKU ngẫu nhiên, xác minh Location và DB, không dùng test trước để seed.
- Khi test BOLA, dùng product tenant B đã seed và token tenant A; kiểm cả HTTP lẫn dữ liệu không bị rò.
- Khi thử idempotency, gửi lại **đúng key + payload**, rồi xác minh chỉ một product; test key trùng/payload khác.
- Khi chạy CI, quan sát test report và tắt logging nhạy cảm. Các test deployed qua gateway chỉ chạy trên môi trường được cấp quyền và dữ liệu thử nghiệm.

**Tiêu chí đạt:** chạy test độc lập, chạy toàn suite và chạy lại nhiều lần đều nhất quán; mỗi failure có assertion rõ; một thay đổi làm mất kiểm soát scope/ETag/Location/idempotency phải làm ít nhất một test **đỏ**.

## 20. Checklist và tài liệu tham khảo

- [ ] Test gọi qua HTTP thật khi cần xác minh full MVC/Security stack.
- [ ] Given thiết lập đúng identity/fixtures; When gửi method/path; Then assert status, headers, body.
- [ ] Request specs không mang mutable global state và không rò token giữa test.
- [ ] Schema đúng phiên bản validator; không coi schema là thay thế BOLA/business logic.
- [ ] GET/POST/PATCH kiểm URI, Content-Type, Location, ETag, If-Match, 304/412.
- [ ] Kiểm lỗi 400/401/403/404/405/415/429 và Problem Details.
- [ ] Phân trang có limit, sort ổn định, cursor đúng scope và không lộ record tenant khác.
- [ ] Idempotency test kiểm DB outcome, không chỉ hai HTTP responses.
- [ ] Có negative security tests với JWT và Spring Security filter thật.
- [ ] DB/test container, queue, cache và async job được seed/cleanup có chủ đích.
- [ ] Logging redacted; không disable TLS validation để test xanh.
- [ ] CI xác nhận số lượng test thực sự được chạy, không bỏ sót hậu tố IT.

**Ghi nhớ:** REST Assured giúp biến hợp đồng REST thành assertions tại **ranh giới HTTP**, nhưng test chỉ có giá trị khi **request, token, dữ liệu nền và môi trường** được kiểm soát. Để chứng minh API đúng, phải kiểm **cả kết quả HTTP lẫn trạng thái nghiệp vụ và quyền truy cập sau request**.

### Nguồn tham khảo

- **REST Assured Usage Guide và Javadocs**: Given–When–Then, request/response specifications, authentication, JSONPath và schema validation.
- **JUnit Jupiter User Guide**: lifecycle, parameterized/concurrent tests và assertions.
- **Spring Boot Test / Spring Security Test**: RANDOM_PORT, integration test và security filter chain.
- **RFC 9110 – HTTP Semantics**, **RFC 9457 – Problem Details**, **OpenAPI Specification 3.1**.
- **Testcontainers, WireMock/MockWebServer, Maven Surefire/Failsafe**: test fixtures, HTTP fault injection và CI.
