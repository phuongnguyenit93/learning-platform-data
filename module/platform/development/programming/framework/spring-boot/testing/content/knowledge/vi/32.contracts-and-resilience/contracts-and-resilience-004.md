# Kiểm tra thay đổi tương thích và thay đổi làm hỏng client trong Spring Boot

## 1. Mục tiêu

Một API có thể khởi động bình thường, trả `200 OK`, không gây lỗi unit test và vẫn **làm hỏng client đang chạy ở production**. Điều này xảy ra khi thay đổi hình dạng JSON, HTTP status, headers, validation, quyền truy cập, đơn vị đo, enum, thứ tự sự kiện hoặc timing mà người dùng API đã dựa vào.

**Kiểm thử tương thích ngược (backward compatibility testing)** trả lời một câu hỏi cụ thể: **Phiên bản provider mới có còn đáp ứng hợp đồng mà các consumer hiện có đã tích hợp hay không?** Khi thay đổi khiến một consumer cũ không thể gửi request hợp lệ, đọc response, diễn giải giá trị hoặc duy trì workflow cũ, đó có thể là **breaking change** ngay cả khi schema compiler coi thay đổi là hợp lệ.

Bài này thuộc phần **Hợp đồng và khả năng phục hồi** của module **Spring Boot – testing**, đúng chủ đề **Kiểm tra thay đổi tương thích và thay đổi làm hỏng client**.

Sau bài, bạn có thể:

1. Phân biệt tương thích **request**, **response**, **semantic**, **behavioral**, **security**, **timing** và **event**.
2. Đánh giá một thay đổi “thêm trường” có thực sự backward-compatible cho consumer cụ thể hay không.
3. Xây bảng phân loại breaking/non-breaking theo đường giao tiếp provider–consumer.
4. Thiết kế **provider contract tests** bằng Spring MVC `MockMvc`, kiểm method/path/status/content type/JSON shape.
5. Thiết kế **consumer compatibility tests** dùng một client cũ thật với `RestClient` và `MockRestServiceServer`.
6. Dùng **golden fixtures** lưu contract cũ và candidate mới; kiểm JSON bằng Jackson mà không tự tạo expected từ chính output của SUT.
7. Phát hiện các thay đổi “schema vẫn đúng nhưng nghĩa sai”: cents thành dollars, enum mới, null, list order, idempotency, timezone.
8. Chọn các công cụ bổ sung như Spring Cloud Contract, Pact, OpenAPI diff và schema registries đúng tình huống.
9. Tổ chức CI compatibility gate, supported-consumer matrix, versioning và rollout/rollback không gây downtime.
10. Tách **contract tests**, **component tests**, **real-HTTP integration tests** và **production observability**.
11. Viết project **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit Jupiter** chạy offline, không cần broker/DB/Docker.
12. Biết giới hạn của mô hình thử nghiệm một provider và một legacy client; mở rộng sang GraphQL, gRPC, Avro/Kafka, SOAP và database migrations khi phù hợp.

**Nguyên tắc:** “Build xanh” không có nghĩa “client cũ vẫn sống”. Với một API được sử dụng bởi các client triển khai độc lập, **hợp đồng công khai** và **hành vi của consumer thật** phải trở thành điều kiện trước khi phát hành.

## 2. Provider, consumer và contract

Hình dung một ứng dụng Spring Boot tên **Catalog Service**:

~~~text
                  Deploy độc lập
                       |
                       v
Legacy Mobile App --------\
Partner Integrator --------> GET /api/v1/products/{sku}
Internal Checkout --------/          |
                                    v
                          Spring Boot Catalog API
                                    |
                                    v
                            JSON ProductResponse
~~~

Các consumer có thể dùng công nghệ khác nhau:

- Mobile app có thể offline nhiều tuần trước khi cập nhật.
- Một đối tác dùng Jackson với `FAIL_ON_UNKNOWN_PROPERTIES=true`.
- Một Java client dùng `@JsonIgnoreProperties(ignoreUnknown=true)`.
- Một consumer parse `priceCents` thành `long`.
- Một consumer đọc enum bằng `Enum.valueOf`, có thể throw khi gặp giá trị chưa biết.
- Một tác vụ batch kỳ vọng `404` cho SKU không có và không biết cách xử lý `200 + null`.
- Một webhook consumer đã triển khai retry/idempotency theo status code và event ID.

**Hợp đồng** không chỉ là schema JSON. Nó có thể bao gồm:

| Thành phần | Ví dụ contract | Điều cần bảo vệ |
| --- | --- | --- |
| HTTP method | `GET /api/v1/products/{sku}` | Không bất ngờ đổi GET thành POST |
| URL/path | `/api/v1/products/BOOK-1` | Không xóa/đổi path mà client cũ đang gọi |
| Query parameters | `?locale=vi` optional | Không biến tham số tùy chọn thành bắt buộc |
| Request headers | `Authorization`, `Idempotency-Key` | Không bắt client cũ gửi header mới nếu chưa triển khai |
| Request body | `sku`, `quantity` | Không biến trường cũ thành required khác |
| Response status | 200 khi tìm được, 404 khi không có | Không chuyển thành status khác khi consumer phân nhánh theo status |
| Response headers | `Content-Type: application/json` | Không chuyển thành XML/plain text |
| Response JSON fields | `sku`, `name`, `priceCents` | Không xóa/rename/change type |
| Field semantics | Giá tính bằng **cents** | Không đổi sang dollars nhưng giữ tên cũ |
| Nullability | `priceCents` luôn non-null | Không bất ngờ trả null |
| Enum domain | `PENDING`, `COMPLETED` | Giá trị mới có thể làm client cũ crash |
| Pagination | Stable cursor, next link | Không đổi thứ tự/cursor semantics ngầm |
| Timing | Retry-After, timeout, eventual consistency | Không thay đồng bộ thành bất đồng bộ mà client không biết |
| Security | OAuth scope/permission/cookie behavior | Không ngầm yêu cầu scope mới khi client cũ không có |
| Error format | `{"code":"PRODUCT_NOT_FOUND"}` | Không thay JSON error bằng HTML/stack trace |
| Event delivery | OrderCreated có event ID | Không bỏ field hoặc đổi partition/order guarantee |

Đánh giá compatibility phải dựa trên **người nhận** và **hợp đồng đã được công bố/sử dụng**, không chỉ dựa vào việc type system compile.

## 3. Tương thích ngược, tương thích xuôi và song phương

### 3.1. Backward compatibility

Phiên bản provider **mới** vẫn phục vụ đúng **consumer cũ**:

~~~text
Consumer v1  ---- request v1 ----> Provider v2
Consumer v1  <--- response OK ---- Provider v2
~~~

Nếu trước đây client gửi `{"sku":"BOOK-1","quantity":2}`, provider v2 vẫn phải nhận nếu contract cũ còn được hỗ trợ.

### 3.2. Forward compatibility

Consumer **mới** có thể xử lý response **cũ** từ provider chưa nâng cấp:

~~~text
Consumer v2  ---- request --------> Provider v1
Consumer v2  <--- response v1 ---- Provider v1
~~~

Điều này quan trọng khi client và server deploy không đồng thời. Ví dụ consumer v2 có field `availability` optional và fallback khi provider v1 chưa trả field đó.

### 3.3. Full/transitive compatibility

Một số ecosystems, đặc biệt schema registries cho message formats, dùng các chính sách **BACKWARD**, **FORWARD**, **FULL** và variants **TRANSITIVE**. Khái niệm “tương thích” phụ thuộc encoding/schema resolution rules (Avro, Protobuf, JSON Schema) và phiên bản so sánh. **Đừng áp dụng kết luận của Avro schema compatibility thẳng sang REST/JSON với semantics riêng.**

### 3.4. Một deploy thường có nhiều versions cùng tồn tại

Với mobile apps, consumer v1/v2/v3 có thể cùng truy cập provider v4. Một PR làm API v4 chỉ tương thích v3 nhưng phá v1 vẫn là breaking nếu v1 còn nằm trong **support window**. Vì vậy phải có **supported consumer versions** và ngày ngừng hỗ trợ rõ ràng; không chọn mỗi “main branch consumer hiện tại” làm baseline.

## 4. Phân loại thay đổi: tương thích hay làm hỏng client?

| Thay đổi | Thông thường | Điều kiện và ngoại lệ |
| --- | --- | --- |
| Thêm field response optional | Có thể tương thích | Consumer phải bỏ qua unknown fields; schema validator strict có thể từ chối |
| Thêm endpoint mới | Thường tương thích | Không chiếm path/matcher cũ hoặc làm thay đổi routing |
| Thêm query parameter optional | Thường tương thích | Giá trị mặc định phải giữ behavior cũ |
| Thêm field request optional | Thường tương thích | Provider phải chấp nhận request cũ không có field |
| Thêm required request field | **Breaking** | Client cũ không gửi được |
| Rename response field | **Breaking** | Trừ khi giữ alias/old field trong thời kỳ chuyển tiếp |
| Xóa response field | **Breaking** | Nếu consumer cũ sử dụng |
| Đổi JSON number → string | **Breaking** | Có thể phá parser/type validation |
| Number int → decimal | Có thể breaking | Client parse integer có thể coerce/truncate/throw |
| String enum thêm một giá trị | Có thể breaking | Client dùng exhaustive switch/Enum.valueOf |
| Biến non-null thành nullable | **Breaking** | Client cũ có thể NPE |
| Biến optional thành required ở request | **Breaking** | Request cũ bị 400 |
| Trả 202 thay vì 201/200 | **Behavioral breaking** | Client kỳ vọng kết quả cuối ngay |
| Thay 404 bằng 200 + null | **Behavioral breaking** | Client phân nhánh theo HTTP status |
| Thêm permission/scope bắt buộc | **Potential breaking** | Client cũ có thể bị 401/403 |
| Đổi unit cents → dollars | **Semantic breaking** | JSON schema có thể không phát hiện |
| Thay `priceCents` 1999 bằng 19.99 | **Breaking** | Cả schema và semantics đều thay đổi |
| Đổi timezone hoặc rounding | **Semantic breaking** | Financial reports/schedules lệch |
| Đổi pagination order/cursor | Có thể breaking | UI/batch paging bỏ sót/trùng record |
| Thêm caching | Có thể breaking | Staleness/ETag/Cache-Control thay đổi |
| Thêm retry tự động | Có thể breaking | Side effects có thể xảy ra nhiều lần |
| Tối ưu performance không đổi output | Thường tương thích | Phải giữ timing/SLA và ordering nếu đã công bố |

**Không dùng quy tắc máy móc “thêm = tốt, xóa = xấu”.** Hệ thống có consumers strict và semantics phức tạp. Hãy kiểm **contract theo client đang hỗ trợ**.

## 5. Contract test không đồng nghĩa unit test

Một unit test chỉ gọi service:

~~~java
Product product = catalog.find("BOOK-1");
assertEquals(1999, product.priceCents());
~~~

chưa chứng minh:

- Đường dẫn HTTP đúng.
- Controller trả 200 và `Content-Type: application/json`.
- Jackson serialize tên field `priceCents`, không phải `priceInCents`.
- Request v1 không có một field mới vẫn được bind.
- 404 có mã lỗi và status ổn định.
- Client cũ deserialize được provider v2 response.

Ngược lại, một MockMvc provider test kiểm JSON shape nhưng **không chứng minh** một consumer thực với configuration khác vẫn đọc được. Hai phía cần bổ sung nhau.

### Pyramid phù hợp

~~~text
                 Real HTTP smoke
                     /  \
        Provider MockMvc  Consumer RestClient
                  \       /
           Golden fixtures + schema checks
                     |
             Unit business invariants
~~~

- **Provider contract tests:** bảo vệ API exposed qua controller/serialization/validation.
- **Consumer contract tests:** chạy **code client cũ**, dùng stubs thuộc contract với requests/responses rõ ràng.
- **Schema/API diff:** cảnh báo thay đổi cấu trúc trên OpenAPI/AsyncAPI/Avro.
- **Real HTTP smoke:** xác minh servlet container/network stack/port và client thực, nhưng chưa phải full production.
- **Observability/canary:** phát hiện consumer versions chưa có trong CI, failures ngoài dự kiến.

Không cần ép mọi thay đổi vào một E2E test chậm; chia test theo boundary để tìm root cause nhanh.

## 6. Consumer-driven contracts (CDC)

Với **consumer-driven contract**, consumer mô tả **những interaction mà nó thực sự cần**: request nào, response status/header/body fields nào. Provider phải kiểm rằng version mới đáp ứng các hợp đồng này.

Quy trình tiêu biểu:

~~~text
Consumer v1
  |
  | Ghi contract: GET /api/v1/products/BOOK-1
  | Expect 200 application/json; sku/name/priceCents
  v
Contract artifact/stub registry
  |
  +-- Consumer tests chạy với stub
  |
  +-- Provider CI tải contract và verify implementation
  |
  v
Provider v2 release gate
  |
  +-- PASS: cho phép release phù hợp support policy
  +-- FAIL: sửa provider hoặc version endpoint/plan migration
~~~

Điểm quan trọng:

- Contract nên thể hiện **kỳ vọng mà consumer thực sự dùng**, không copy toàn bộ provider DTO.
- Provider test phải chạy trên **provider implementation**, không chỉ một stub do provider tự viết rồi xác nhận.
- Contract phải có **version/consumer identity** và trạng thái deploy/support; không dùng một fixture không ai sở hữu.
- Consumer test cần bắt thay đổi deserialize, retry/error handling, status expectations; provider cần bắt schema/validation behavior.
- Nếu test chỉ so JSON được tạo bởi cùng `ObjectMapper` và DTO mới, cả expected và actual có thể đổi cùng nhau -> **false confidence**.
- Không phải mọi compatibility problem là schema problem: unit, currency, enum semantics, ordering và idempotency vẫn cần business assertions.

### Công cụ phổ biến

**Spring Cloud Contract** có thể sinh provider verification tests và consumer stubs từ Groovy/YAML contracts. Khi dùng với Spring Boot 3.3.x, chọn dòng Spring Cloud Contract và Spring Cloud BOM tương thích thay vì copy dependency mới nhất vào build cũ.

**Pact** phù hợp quản lý hợp đồng theo consumer/provider, có broker, provider verification và deployment checks. “Pact verified” có nghĩa các interactions được khai báo đã được kiểm theo cấu hình đó, **không phải** mọi behavior đã được chứng minh an toàn.

**OpenAPI diff** giúp so base/target specs theo rules, phát hiện xóa endpoint, đổi required fields/status/schema. Nhưng docs spec có thể sai thực thi, và semantic changes đôi khi không xuất hiện trong schema. Kết hợp **spec diff + runtime contract tests**.

Trong lab dưới đây, dùng chính JUnit/Spring Test/Jackson để không cần thêm tooling phức tạp. Sau đó có hướng nâng cấp sang CDC chuyên dụng.

## 7. Golden fixtures: baseline không được thay theo provider mới

Một **golden fixture** là request/response được lưu độc lập làm chuẩn. Ví dụ consumer v1 từng nhận:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999
}
~~~

Provider v2 thêm `availability`:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999,
  "availability": "IN_STOCK"
}
~~~

Nếu **consumer v1 bỏ qua unknown fields**, nó vẫn có thể deserialize và dùng ba field cũ. Nhưng một consumer strict có thể fail vì field mới. Kết luận “backward compatible” phải gắn với **consumer behavior đã kiểm**.

Ví dụ breaking rename:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceInCents": 1999,
  "availability": "IN_STOCK"
}
~~~

Consumer cũ đọc `priceCents` nhận missing value, có thể throw hoặc mặc định 0. Cả hai đều nguy hiểm.

Ví dụ semantic break mà JSON parser vẫn nhận:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 20,
  "availability": "IN_STOCK"
}
~~~

Nếu giá thực vẫn 19,99 USD nhưng field đổi ngầm từ cents sang dollars/rounding, type JSON vẫn là integer. **Schema-only diff không thấy**. Bảo vệ bằng business invariant và fixture expected giá/currency.

### Quy tắc quản lý fixtures

1. Baseline v1 được **đóng băng** theo phiên bản consumer còn hỗ trợ.
2. Mỗi field có semantics/requiredness rõ ràng.
3. Khi provider đổi, **không tự regenerate tất cả expected JSON** rồi coi test pass.
4. Candidate fixture dùng cho **positive và negative compatibility cases**.
5. Không đưa PII/credentials thật vào fixtures.
6. Có review khi hợp đồng thay đổi và deprecation plan.
7. Khi consumer versions khác nhau, lưu fixtures theo consumer/version/interaction.
8. Không biến snapshot toàn bộ JSON thành rule “không được thêm field nào”, nếu contract cho phép additive extension.

## 8. Project runnable: Spring Boot 3.3.5 / Java 17

Ta xây **Catalog API v2** vẫn trả route **`/api/v1/products/{sku}`**, vì URI version `v1` ở đây là **phiên bản hợp đồng còn được hỗ trợ**, không phải version binary của Spring Boot app. Provider v2 có thể bổ sung trường `availability` mà không buộc tạo endpoint v2 ngay.

Consumer cũ `LegacyCatalogClient` chỉ biết `sku`, `name`, `priceCents` và dùng Spring Framework `RestClient`. Bộ test dùng:

- `@SpringBootTest` + `@AutoConfigureMockMvc` kiểm provider thực.
- `MockRestServiceServer.bindTo(RestClient.Builder)` kiểm client cũ với fixtures.
- `ObjectMapper` kiểm baseline/candidate shape độc lập.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` kiểm client cũ qua socket thật.
- Một POST `/api/v1/reservations` để chứng minh **request cũ không có optional field mới vẫn được chấp nhận**.

Không dùng Docker, DB, HTTP external server hoặc mã giả. Dữ liệu demo cố định để assertions tái lập.

### 8.1. Cấu trúc thư mục

~~~text
api-compatibility-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/contracts/
    │   ├── ContractLabApplication.java
    │   ├── api/
    │   │   ├── CatalogController.java
    │   │   └── CatalogErrorHandler.java
    │   └── consumer/
    │       ├── LegacyProduct.java
    │       └── LegacyCatalogClient.java
    └── test/
        ├── resources/contracts/
        │   ├── product-v1.json
        │   ├── product-v2-additive.json
        │   ├── product-breaking-rename.json
        │   ├── product-breaking-units.json
        │   ├── reservation-v1-request.json
        │   └── reservation-v2-request.json
        └── java/com/example/contracts/
            ├── CatalogProviderContractTest.java
            ├── LegacyCatalogClientContractTest.java
            ├── JsonCompatibilityGateTest.java
            └── LiveHttpCompatibilityTest.java
~~~

Gradle Wrapper scripts/JAR phải được sinh từ Gradle hoặc lấy từ repository; `gradle-wrapper.jar` là binary không thể chép từ Markdown. Tất cả source/fixture khác được liệt kê bên dưới.

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'api-compatibility-lab'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Spring Boot 3.3.x sử dụng Spring Framework 6.1.x, có `RestClient` và `MockRestServiceServer.bindTo(RestClient.Builder)` từ Spring Framework 6.1. `spring-boot-starter-web` mang Jackson, Spring MVC, servlet container và `RestClient` API; `spring-boot-starter-validation` cấp Jakarta Validation. `spring-boot-starter-test` đem JUnit Jupiter, AssertJ, MockMvc và mock REST client support.

**Không thêm Spring Cloud Contract plugin vào build này**: demo thực thi bằng JUnit thuần. Phần CDC nâng cao hướng dẫn triển khai với dependency BOM phù hợp, tránh trộn một plugin không được cấu hình vào project runnable.

### 8.4. ContractLabApplication.java

~~~java
package com.example.contracts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractLabApplication.class, args);
    }
}
~~~

Root package bao phủ `api` và `consumer`. Consumer là plain Java class **không gắn @Component**, vì trong demo nó chỉ đại diện một legacy client được test trực tiếp; không cần external base URL/RestClient bean trong Spring context.

## 9. Provider implementation: giữ field cũ và thêm optional field

**src/main/java/com/example/contracts/api/CatalogController.java**

~~~java
package com.example.contracts.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class CatalogController {

    @GetMapping(
        value = "/products/{sku}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductResponse getProduct(
            @PathVariable String sku) {

        if (!"BOOK-1".equals(sku)) {
            throw new ProductMissingException();
        }

        // Các field cũ giữ nguyên cả tên, type và nghĩa.
        // Field availability là bổ sung của provider v2.
        return new ProductResponse(
            "BOOK-1", "Java Basics",
            1999L, "IN_STOCK");
    }

    @PostMapping(
        value = "/reservations",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public ReservationResponse reserve(
            @Valid @RequestBody ReservationRequest request) {

        // note là optional: request cũ vẫn hợp lệ.
        return new ReservationResponse(
            "RSV-1", request.sku(),
            request.quantity(), "PENDING");
    }

    public record ProductResponse(
            String sku,
            String name,
            long priceCents,
            String availability) {
    }

    public record ReservationRequest(
            @NotBlank String sku,
            @NotNull @Min(1) Integer quantity,
            String note) {
    }

    public record ReservationResponse(
            String reservationId,
            String sku,
            int quantity,
            String status) {
    }

    public static class ProductMissingException
            extends RuntimeException {
    }
}
~~~

### Điều gì được bảo vệ?

**GET v1 shape** tiếp tục có `sku`, `name`, `priceCents` đúng units, đồng thời provider có thể thêm `availability`. Endpoint path và HTTP method không đổi.

**POST request** thêm `note` dưới dạng nullable optional field: JSON cũ chỉ có `sku`/`quantity` vẫn được bind vào `ReservationRequest` record, `note` là null, validation không từ chối. Nếu developer thêm `@NotBlank` cho `note`, request cũ sẽ bị 400 — **breaking change** và provider test phải phát hiện.

**Status** được giữ: GET 200, POST 201, missing product 404. Một số client phân nhánh logic theo status và không biết xử lý việc biến POST success từ 201 thành 202 async.

**Record** dùng Java 17 và Jackson được Spring Boot cấu hình qua auto-configuration. Các giá trị cố định phục vụ test, không phải data layer production.

## 10. Error contract: 404 và lỗi validation 400 ổn định

**src/main/java/com/example/contracts/api/CatalogErrorHandler.java**

~~~java
package com.example.contracts.api;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CatalogErrorHandler {

    @ExceptionHandler(
        CatalogController.ProductMissingException.class)
    public ResponseEntity<ApiError> productMissing() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidReservation() {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_INPUT"));
    }

    public record ApiError(String code) {
    }
}
~~~

Một contract lỗi phải kiểm cả **status**, **Content-Type** và **body code** khi consumer thật sự dựa vào các yếu tố đó.

Tại sao không trả exception message? Public JSON error không nên lộ internal class names, SQL, credentials hoặc stack traces. Ví dụ chỉ giữ `code` ổn định. Nếu app thực dùng `ProblemDetail` theo RFC 9457, test schema `type/title/status/code` tương ứng. Không tự thay error format chỉ vì upgrade Spring Boot; cần migration plan.

**Giới hạn:** 415 Unsupported Media Type, 405 Method Not Allowed và các lỗi ở filter/container có thể dùng body khác. Demo chỉ quy định JSON code ổn định cho **404 SKU không tồn tại** và **400 bean validation**.

## 11. Legacy consumer: mã Java thật từ góc nhìn client cũ

**src/main/java/com/example/contracts/consumer/LegacyProduct.java**

~~~java
package com.example.contracts.consumer;

import java.util.Objects;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LegacyProduct(
        String sku,
        String name,
        Long priceCents) {

    public LegacyProduct {
        if (sku == null || sku.isBlank()
                || name == null || name.isBlank()
                || priceCents == null
                || priceCents < 0) {
            throw new IllegalArgumentException(
                    "Invalid product contract");
        }
    }
}
~~~

Dùng `Long` thay primitive `long` và validate non-null để tránh lỗi nguy hiểm: JSON bị xóa `priceCents` mà Java/Jackson âm thầm gán mặc định 0. Một price 0 có thể bị coi là hàng miễn phí; **silent corruption còn nguy hiểm hơn fail-fast**.

`@JsonIgnoreProperties(ignoreUnknown=true)` cho client này bỏ qua `availability` từ provider v2. **Không suy ra mọi consumer đều dùng cùng policy**: code-gen/JSON schema validators hoặc các ngôn ngữ khác có thể strict. Tương thích phải kiểm trên consumer đang hỗ trợ.

**src/main/java/com/example/contracts/consumer/LegacyCatalogClient.java**

~~~java
package com.example.contracts.consumer;

import java.util.Objects;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class LegacyCatalogClient {

    private final RestClient http;

    public LegacyCatalogClient(RestClient http) {
        this.http = Objects.requireNonNull(http);
    }

    public LegacyProduct getProduct(String sku) {
        LegacyProduct value = http.get()
            .uri("/api/v1/products/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(LegacyProduct.class);

        if (value == null) {
            throw new IllegalStateException(
                    "Empty catalog response");
        }

        if (!sku.equals(value.sku())) {
            throw new IllegalStateException(
                    "Mismatched product SKU");
        }

        return value;
    }
}
~~~

Nếu provider trả HTTP 404/500, `RestClient.retrieve()` mặc định tạo error exception phù hợp trước khi deserialize body như Product. Consumer production có thể map lỗi vào domain-specific exceptions, nhưng điều đó **phải được test theo contract**, không dùng `catch(Exception) -> return empty product` khiến dữ liệu sai bị che.

`RestClient` là synchronous client, không phải reactive `WebClient`. Dùng nó giúp lab dễ chạy với `spring-boot-starter-web`; khi production dùng WebClient, cần kiểm WebClient codecs/status handling tương ứng.

## 12. Frozen JSON fixtures

Tạo các file trong `src/test/resources/contracts/`. Chúng được lưu cố định, không sinh từ provider DTO ở runtime.

### 12.1. product-v1.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999
}
~~~

Đây là **baseline contract của consumer v1**. Nó không có `availability`.

### 12.2. product-v2-additive.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999,
  "availability": "IN_STOCK",
  "displayHint": "new field ignored by v1"
}
~~~

Một client cũ tolerant có thể bỏ qua hai trường mới; các field cũ vẫn giữ nguyên.

### 12.3. product-breaking-rename.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceInCents": 1999,
  "availability": "IN_STOCK"
}
~~~

Đây là thay đổi breaking giả lập: field `priceCents` biến mất; test mong legacy client từ chối thay vì tạo price=0.

### 12.4. product-breaking-units.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 20,
  "availability": "IN_STOCK"
}
~~~

JSON shape vẫn hợp lệ, nhưng value vi phạm business oracle “giá BOOK-1 là 1.999 cents”. Consumer deserialize được; schema diff **không đủ** để phát hiện. Provider contract test phải giữ assertion semantic.

### 12.5. reservation-v1-request.json

~~~json
{
  "sku": "BOOK-1",
  "quantity": 2
}
~~~

Client v1 **không có `note`**. Provider v2 phải tiếp tục trả 201.

### 12.6. reservation-v2-request.json

~~~json
{
  "sku": "BOOK-1",
  "quantity": 2,
  "note": "Gift wrap requested"
}
~~~

Provider v2 nhận field mới nhưng **không biến nó thành required**. Test old request và new request phải tách riêng để chứng minh back-compat.

## 13. Provider contract tests bằng Spring MVC MockMvc

**src/test/java/com/example/contracts/CatalogProviderContractTest.java**

~~~java
package com.example.contracts;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.core.io.ClassPathResource;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = ContractLabApplication.class)
@AutoConfigureMockMvc
class CatalogProviderContractTest {

    @Autowired
    private MockMvc mvc;

    private static String fixture(String name)
            throws IOException {
        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {

            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
        }
    }

    @Test
    void providerKeepsLegacyResponseFieldsAndUnits()
            throws Exception {
        mvc.perform(get("/api/v1/products/BOOK-1")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.sku")
                .value("BOOK-1"))
            .andExpect(jsonPath("$.name")
                .value("Java Basics"))
            .andExpect(jsonPath("$.priceCents")
                .isNumber())
            .andExpect(jsonPath("$.priceCents")
                .value(1999));
    }

    @Test
    void additiveAvailabilityFieldDoesNotReplaceOldFields()
            throws Exception {
        mvc.perform(get("/api/v1/products/BOOK-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku")
                .value("BOOK-1"))
            .andExpect(jsonPath("$.priceCents")
                .value(1999))
            .andExpect(jsonPath("$.availability")
                .value("IN_STOCK"));
    }

    @Test
    void missingProductStillReturns404AndCode()
            throws Exception {
        mvc.perform(get("/api/v1/products/UNKNOWN")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                .value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void oldReservationRequestStillWorksWithoutNote()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(fixture(
                    "reservation-v1-request.json")))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.reservationId")
                .value("RSV-1"))
            .andExpect(jsonPath("$.sku")
                .value("BOOK-1"))
            .andExpect(jsonPath("$.quantity")
                .value(2))
            .andExpect(jsonPath("$.status")
                .value("PENDING"));
    }

    @Test
    void newOptionalNoteIsAcceptedToo()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .content(fixture(
                    "reservation-v2-request.json")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.reservationId")
                .value("RSV-1"));
    }

    @Test
    void missingQuantityIsStillValidationError()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"BOOK-1\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_INPUT"));
    }

    @Test
    void invalidQuantityStillReturns400()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"BOOK-1\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_INPUT"));
    }

    @Test
    void wrongContentTypeIsNotSilentlyTreatedAsJson()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.TEXT_PLAIN)
                .content(
                    "{\"sku\":\"BOOK-1\",\"quantity\":2}"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

### Test nào bảo vệ thay đổi nào?

- `providerKeepsLegacyResponseFieldsAndUnits`: path, status, content type và các **field cũ/giá**.
- `additiveAvailabilityFieldDoesNotReplaceOldFields`: field mới có thể xuất hiện cùng field cũ, không rename.
- `missingProductStillReturns404AndCode`: status/error code không bị đổi thành “200 + null”.
- `oldReservationRequestStillWorksWithoutNote`: client cũ không biết `note` vẫn tạo reservation được.
- `newOptionalNoteIsAcceptedToo`: provider hỗ trợ dữ liệu bổ sung.
- `missingQuantityIsStillValidationError`: không vô tình thay requiredness của quantity.
- `invalidQuantityStillReturns400`: `@Min(1)` còn hiệu lực.
- `wrongContentTypeIsNotSilentlyTreatedAsJson`: media-type contract không vô tình mở tùy ý.

**Không dùng exact JSON string equality để chặn field mới**, vì đó là backward-compatible policy quá chặt nếu consumer tolerant. Kiểm fields/semantics cần giữ; phần mở rộng được đánh giá riêng.

### Nếu provider đổi `priceCents` thành `priceInCents`?

`jsonPath("$.priceCents")` sẽ fail. Nếu đổi giá 1999 thành 20 nhưng vẫn trả number, assertion `value(1999)` sẽ fail. Đây là lý do cần cả **shape** và **business oracle**.

### Nếu provider sửa một test cho khớp code mới?

Đó là rủi ro **tự đồng thuận**. Một người sửa API và đổi luôn expected mà không review consumer contracts có thể biến breaking change thành “test xanh”. Baseline nên được quản lý có ownership, review bởi consumer hoặc gate tự động theo supported versions.

## 14. Consumer contract tests bằng RestClient và MockRestServiceServer

**src/test/java/com/example/contracts/LegacyCatalogClientContractTest.java**

~~~java
package com.example.contracts;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import com.example.contracts.consumer.LegacyCatalogClient;
import com.example.contracts.consumer.LegacyProduct;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class LegacyCatalogClientContractTest {

    private static final String BASE =
            "https://catalog.example.test";

    private MockRestServiceServer server;
    private LegacyCatalogClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);

        server = MockRestServiceServer
                .bindTo(builder)
                .build();

        client = new LegacyCatalogClient(
                builder.build());
    }

    private static String fixture(String name)
            throws IOException {
        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {
            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
        }
    }

    private void expectProductJson(String fileName)
            throws IOException {
        server.expect(requestTo(
                BASE + "/api/v1/products/BOOK-1"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                fixture(fileName),
                MediaType.APPLICATION_JSON));
    }

    @Test
    void legacyClientReadsOriginalV1Contract()
            throws Exception {
        expectProductJson("product-v1.json");

        LegacyProduct product =
                client.getProduct("BOOK-1");

        assertEquals("BOOK-1", product.sku());
        assertEquals("Java Basics", product.name());
        assertEquals(
                1999L, product.priceCents().longValue());

        server.verify();
    }

    @Test
    void tolerantLegacyClientIgnoresAdditiveFields()
            throws Exception {
        expectProductJson(
                "product-v2-additive.json");

        LegacyProduct product =
                client.getProduct("BOOK-1");

        assertEquals("BOOK-1", product.sku());
        assertEquals("Java Basics", product.name());
        assertEquals(
                1999L, product.priceCents().longValue());

        server.verify();
    }

    @Test
    void renamingRequiredFieldBreaksLegacyClient()
            throws Exception {
        expectProductJson(
                "product-breaking-rename.json");

        assertThrows(
            RestClientException.class,
            () -> client.getProduct("BOOK-1"));

        server.verify();
    }

    @Test
    void semanticUnitChangeMayDeserializeWithoutError()
            throws Exception {
        expectProductJson(
                "product-breaking-units.json");

        LegacyProduct product =
                client.getProduct("BOOK-1");

        // Deserializer KHÔNG phát hiện lỗi unit.
        assertEquals(
                20L, product.priceCents().longValue());
        assertNotEquals(
                1999L, product.priceCents().longValue());

        server.verify();
    }

    @Test
    void oldClientStillDistinguishes404()
            throws Exception {
        server.expect(requestTo(
                BASE + "/api/v1/products/UNKNOWN"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(
                withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(
                        "{\"code\":\"PRODUCT_NOT_FOUND\"}"));

        HttpClientErrorException error = assertThrows(
            HttpClientErrorException.class,
            () -> client.getProduct("UNKNOWN"));

        assertEquals(
                404, error.getStatusCode().value());
        assertTrue(error.getResponseBodyAsString()
                .contains("PRODUCT_NOT_FOUND"));

        server.verify();
    }

    @Test
    void changingResponseMediaTypeCanBreakReader()
            throws Exception {
        server.expect(requestTo(
                BASE + "/api/v1/products/BOOK-1"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                "<product/>", MediaType.APPLICATION_XML));

        assertThrows(
            RestClientException.class,
            () -> client.getProduct("BOOK-1"));

        server.verify();
    }
}
~~~

### Vì sao `MockRestServiceServer.bindTo(RestClient.Builder)`?

Spring Framework 6.1 cho phép một mock server gắn vào **RestClient.Builder** để bắt HTTP requests của chính client dưới test, xác minh method/URL và trả fixture response. Không mở socket thật; đây là **client boundary test** chứ không phải kiểm full network transport.

**Chú ý thứ tự:** bind mock server vào `builder` **trước khi gọi `builder.build()`**. Nếu tạo RestClient trước rồi bind builder khác, mock server có thể không nhận request và client cố kết nối Internet.

### Những giới hạn của client test

- Consumer v1 có `ignoreUnknown=true`, nên thêm field pass **cho client này**; một consumer strict khác vẫn có thể fail.
- Rename `priceCents` bị phát hiện do `LegacyProduct` validate non-null trong constructor; nếu dùng primitive `long` không validate, Jackson có thể trả 0 và gây silent corruption.
- Semantic unit change **vẫn deserialize thành công**. Test này cố ý chứng minh lỗ hổng schema/type checking; **business oracle ở provider test** mới phát hiện giá 20 không đúng 1999.
- HTTP 404 được kiểm bằng exception/status; nếu client mới đổi cách map errors, cần thêm contract riêng cho business caller.
- Mock server không mô phỏng DNS/TLS/proxy/socket timeouts thực tế; test network issues ở layer khác.

Không hiểu “test semanticUnitChangeMayDeserializeWithoutError pass” là provider compatible: đây là một **negative illustration** của sự bất lực của deserializer trước lỗi nghĩa.

## 15. JSON compatibility gate với Jackson

Không phải khi nào cũng có sẵn consumer code để chạy. Có thể xây một **structural compatibility gate** so sánh baseline và candidate, nhưng phải coi nó là lớp **bổ sung**, không phải bằng chứng duy nhất.

**src/test/java/com/example/contracts/JsonCompatibilityGateTest.java**

~~~java
package com.example.contracts;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

class JsonCompatibilityGateTest {

    private final ObjectMapper mapper =
            new ObjectMapper();

    private JsonNode fixture(String name)
            throws IOException {
        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {
            return mapper.readTree(input);
        }
    }

    private static void assertLegacyFieldsRemain(
            JsonNode baseline, JsonNode candidate) {

        for (String field : List.of(
                "sku", "name", "priceCents")) {

            assertTrue(
                baseline.hasNonNull(field),
                "Baseline missing: " + field);

            assertTrue(
                candidate.hasNonNull(field),
                "Candidate removed: " + field);

            assertEquals(
                baseline.get(field).getNodeType(),
                candidate.get(field).getNodeType(),
                "Type changed: " + field);
        }
    }

    @Test
    void additiveCandidatePassesShapeGate()
            throws Exception {
        JsonNode old = fixture("product-v1.json");
        JsonNode next = fixture(
                "product-v2-additive.json");

        assertDoesNotThrow(
            () -> assertLegacyFieldsRemain(old, next));

        assertTrue(next.has("availability"));
    }

    @Test
    void missingLegacyFieldFailsShapeGate()
            throws Exception {
        JsonNode old = fixture("product-v1.json");
        JsonNode broken = fixture(
                "product-breaking-rename.json");

        assertThrows(
            AssertionError.class,
            () -> assertLegacyFieldsRemain(old, broken));
    }

    @Test
    void shapeOnlyCannotDetectChangedPriceUnits()
            throws Exception {
        JsonNode old = fixture("product-v1.json");
        JsonNode changed = fixture(
                "product-breaking-units.json");

        // Structural shape vẫn pass.
        assertDoesNotThrow(
            () -> assertLegacyFieldsRemain(old, changed));

        // Nhưng expected business value đã bị phá.
        assertNotEquals(
                old.get("priceCents").longValue(),
                changed.get("priceCents").longValue());
    }
}
~~~

### Phạm vi của gate này

Helper `assertLegacyFieldsRemain` **không phải** một JSON Schema compatibility checker toàn diện. Nó chỉ kiểm **ba field** và Jackson node types, không kiểm arrays, nested objects, enums, minimum/maximum, required request fields, regex constraints, nullability của mọi field hoặc semantics.

Trong production:

- Bảo vệ toàn bộ schema theo OpenAPI/JSON Schema có version.
- Thêm contract interactions từ consumers.
- Khi field mang đơn vị tiền, đặt schema description/x-property và business invariants.
- Phân biệt response additive rules với request widening/narrowing rules.
- Không coi một snapshot diff được chấp nhận thủ công là bằng chứng client không gãy.

### Vì sao không assert equality nguyên JSON?

Nếu `candidate` thêm trường `availability` hợp lệ, deep-equality v1/v2 sẽ fail dù legacy client tolerant vẫn hoạt động. Ngược lại, một schema gate quá lỏng có thể không phát hiện `priceCents` đổi nghĩa. Lựa chọn assertions phải phản ánh **compatibility policy được team đồng ý**.

## 16. Real HTTP smoke: dùng chính legacy client với provider v2

MockMvc provider test và MockRestServiceServer consumer test là hai phía độc lập. Để khép khoảng trống “stub pass nhưng app thật khác”, ta chạy một integration smoke với HTTP server trên port ngẫu nhiên.

**src/test/java/com/example/contracts/LiveHttpCompatibilityTest.java**

~~~java
package com.example.contracts;

import com.example.contracts.consumer.LegacyCatalogClient;
import com.example.contracts.consumer.LegacyProduct;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ContractLabApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpCompatibilityTest {

    @LocalServerPort
    int port;

    private RestClient restClient() {
        return RestClient.create(
            "http://localhost:" + port);
    }

    @Test
    void legacyReaderWorksAgainstActualProviderV2() {
        LegacyCatalogClient legacy =
            new LegacyCatalogClient(restClient());

        LegacyProduct value = legacy.getProduct("BOOK-1");

        assertEquals("BOOK-1", value.sku());
        assertEquals("Java Basics", value.name());
        assertEquals(
            1999L, value.priceCents().longValue());
    }

    @Test
    void legacyPostBodyStillGets201AcrossSocket() {
        ResponseEntity<String> response =
            restClient()
                .post()
                .uri("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .body(
                    "{\"sku\":\"BOOK-1\","
                    + "\"quantity\":2}")
                .retrieve()
                .toEntity(String.class);

        assertEquals(
            HttpStatus.CREATED,
            response.getStatusCode());

        assertNotNull(response.getBody());
        assertTrue(
            response.getBody().contains("\"RSV-1\""));
        assertTrue(
            response.getBody().contains("\"PENDING\""));
    }

    @Test
    void missingSkuStillReports404OverHttp() {
        LegacyCatalogClient legacy =
            new LegacyCatalogClient(restClient());

        HttpClientErrorException error =
            assertThrows(
                HttpClientErrorException.class,
                () -> legacy.getProduct("UNKNOWN"));

        assertEquals(
            404, error.getStatusCode().value());
        assertTrue(error.getResponseBodyAsString()
                .contains("PRODUCT_NOT_FOUND"));
    }
}
~~~

### Điều gì được xác nhận?

- Server thật khởi chạy trên một **random local port**.
- Consumer cũ và provider mới dùng cùng Jackson/HTTP semantics như production code của demo.
- JSON response thêm field vẫn đọc được.
- POST request cũ thiếu `note` vẫn nhận HTTP 201.
- SKU không có vẫn trả 404/error code.

Điều này chưa kiểm TLS proxy, gateway auth, rate limiting, CDN, multi-instance load balancing hoặc data migrations. Những boundary thực tế đó cần môi trường staging/canary riêng.

**Không gắn `@Transactional` rồi suy luận rollback** với real-server tests: HTTP client/server chạy ở thread/transaction contexts khác nhau. Lab không có DB/side effects, nên có thể tái lập đơn giản.

## 17. Tổng số test và lệnh chạy

| Lớp test | Số phương thức `@Test` | Vai trò |
| --- | ---: | --- |
| `CatalogProviderContractTest` | 8 | Provider HTTP routes/status/JSON/request |
| `LegacyCatalogClientContractTest` | 6 | Consumer deserialization/error handling |
| `JsonCompatibilityGateTest` | 3 | Structural gate và giới hạn semantic |
| `LiveHttpCompatibilityTest` | 3 | Legacy client gọi HTTP provider v2 thật |
| **Tổng** | **20** | Compatibility nhiều tầng |

### Lệnh chạy

JDK 17, Gradle Wrapper và quyền tải Maven Central lần đầu:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng test classes:

~~~bash
./gradlew test --tests 'com.example.contracts.CatalogProviderContractTest'
./gradlew test --tests 'com.example.contracts.LegacyCatalogClientContractTest'
./gradlew test --tests 'com.example.contracts.JsonCompatibilityGateTest'
./gradlew test --tests 'com.example.contracts.LiveHttpCompatibilityTest'
~~~

Tạo Gradle Wrapper nếu project chưa có và Gradle tương thích đã được cài:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Nếu muốn buộc test task chạy lại thay vì dùng Gradle cache:

~~~bash
./gradlew test --rerun-tasks
~~~

Expected: **20 JUnit test methods thành công** với source/fixtures/dependencies đầy đủ; đây là kết quả dự kiến, **không phải báo cáo đã thực thi Gradle/JUnit** tại đây. Lab không có Docker/DB, không ghi file ra ngoài Gradle build/test runtime. Nếu test fail trên máy thật, đọc `build/reports/tests/test/index.html` và JUnit XML để xác định thuộc provider, consumer, schema hay real HTTP integration.

### Khi chạy, cái gì được cố tình xem là failure?

Các test `renamingRequiredFieldBreaksLegacyClient` và `missingLegacyFieldFailsShapeGate` dùng `assertThrows` vì chúng **chủ động đưa fixture breaking vào** để chứng minh cơ chế phát hiện. Chúng pass khi validator/consumer **bắt được sự phá vỡ**.

Trong pipeline kiểm **provider candidate thật**, một breaking response không được chuyển thành “test xanh vì ta mong lỗi”. Provider test và real HTTP smoke **phải fail** khi candidate vi phạm contract.

## 18. Điều kiện tương thích không chỉ là JSON shape

### 18.1. Nullability

Nếu một field cũ đã cam kết non-null, đổi thành null là breaking với client dùng primitive/unboxing. Nếu data model Java dùng `Long`, có thể deserialize null rồi lỗi khi tính toán; dùng validation hoặc business layer contract tests.

### 18.2. Enum evolution

Giả sử trước đây `status` chỉ là:

~~~json
{"status":"PENDING"}
~~~

V2 thêm:

~~~json
{"status":"ON_HOLD"}
~~~

Một Java consumer dùng `enum Status { PENDING, COMPLETED }` có thể throw khi Jackson parse unknown enum. Client tolerant có thể cấu hình unknown enum fallback (ví dụ `@JsonEnumDefaultValue` với Jackson feature phù hợp), nhưng phải có test thật. **Thêm enum value không mặc định an toàn**.

### 18.3. Numeric precision and units

Cents trong integer vs dollars trong decimal; number vs string; decimal precision; overflow khi lượng tiền lớn; rounding từ `BigDecimal` sang `double` có thể khiến báo cáo sai mà schema vẫn “number”. Test nên so exact domain units, limits và edge values, đặc biệt payments/tax.

### 18.4. Dates and timezones

`2026-11-08T08:00:00Z` khác `2026-11-08T08:00:00+07:00` về instant. Đổi từ UTC sang local time không kèm timezone có thể breaking dù JSON vẫn string. Kiểm ISO-8601 format, zone/offset và semantics (“event time” vs “processing time”).

### 18.5. List ordering

Một API từng trả danh sách theo `createdAt DESC`, v2 đổi sang `updatedAt DESC` nhưng giữ schema. Một consumer phân trang theo cursor có thể bỏ sót/nhận trùng items. Test sorting, cursors, stable tie-breaker, pagination boundary và concurrent writes.

### 18.6. Error handling và retries

Nếu provider đổi một lỗi retryable `503` thành `400`, consumer cũ có thể ngừng retry. Nếu đổi `404` thành `200 + empty`, client cũ không nhận ra không có dữ liệu. Nếu tăng `429` nhưng bỏ `Retry-After`, backoff policy có thể thay. Contract errors cần được bảo vệ như happy path.

### 18.7. Idempotency

Một client cũ có thể retry POST sau timeout với `Idempotency-Key`. Nếu provider mới bỏ deduplication, same request bị tính tiền/tạo order hai lần. Contract test phải kiểm **stateful behavior và key reuse**, không chỉ status JSON một lần.

### 18.8. Authentication và authorization

Bắt buộc một OAuth scope mới có thể khiến client cũ 403 dù request/response schema không đổi. Rotating JWT issuer/audience hoặc thay cookie SameSite có thể ảnh hưởng clients. Test có identity/permission matrix, không dùng CORS như authorization substitute.

### 18.9. Eventual consistency

Nếu trước đây POST trả 201 khi DB commit, nay trả 202 và xử lý async, consumer có thể đọc state ngay rồi fail. Cần xem đây là **behavioral contract change**, có job status endpoint/retry semantics và migration plan.

### 18.10. Content negotiation và headers

`Accept: application/json` cũ, nhưng provider mới chỉ hỗ trợ `application/problem+json` cho lỗi hoặc đổi `Content-Type` sang XML/CSV, có thể làm reader fail. Còn `ETag`, `Location`, `Cache-Control`, `Vary`, CORS, pagination headers cũng có thể là contract.

## 19. JSON response vs JSON request: chiều tương thích khác nhau

**Response:** Provider thường có thể **bổ sung** một field optional nếu consumer bỏ qua unknown fields. Nhưng một client strict hoặc chữ ký JSON canonical có thể không chịu được.

**Request:** Provider mới cần chấp nhận request cũ; thêm field request optional thường tương thích vì client cũ **không gửi field đó**. Nếu bật `@NotNull`/`@NotBlank` cho field mới, request cũ có thể fail 400; đó là breaking.

**Request coercion:** Việc provider đổi Jackson property binding/unknown fields strictness có thể gây lỗi cho client vốn gửi các trường bổ sung trước đây. Nên test request corpus của từng consumer, không chỉ DTO happy path.

**Validation tightening:** Đổi `quantity` min từ 1 sang 10 có thể phá các client cũ gửi 2, dù JSON schema vẫn int. Đây là behavioral/schema constraint change.

**Response field removal:** Nếu muốn đổi tên, trong migration window có thể trả **cả field cũ và mới**, đánh dấu deprecated field cũ và theo dõi usage; chỉ xóa sau khi support window kết thúc. Cần kiểm sự nhất quán giữa alias fields.

**Response new required field:** Khái niệm “required field” trong **response schema** khác required field trong **request**. Thêm response required có thể giúp client mới, nhưng không có nghĩa client cũ sẽ chấp nhận field lạ; phải kiểm strictness.

## 20. Versioning không tự giải quyết compatibility

Một số lựa chọn:

- URI version: `/api/v1/...`, `/api/v2/...`.
- Header version: `API-Version: 2`.
- Media type versioning: `Accept: application/vnd.example.v2+json`.
- Schema registry version (event).
- Giao thức gRPC/Protobuf với field numbering rules.

### Đường migration hợp lý

Nếu muốn đổi `priceCents` thành `priceMinorUnits`:

1. Giữ `priceCents` ở `/api/v1` hoặc trong cùng response trong thời kỳ chuyển tiếp.
2. Thêm field mới và mô tả semantic/units.
3. Viết tests cho consumer v1 và v2.
4. Cho consumer v2 sử dụng field mới, giữ backward fallback nếu cần.
5. Đo usage của field/endpoint cũ và thông báo deprecation.
6. Đặt sunset date dựa trên support policy thực.
7. Khi không còn consumer được hỗ trợ cần field cũ, release breaking v2 endpoint/schema.
8. Sau migration, **mới** xóa contract v1 khỏi CI theo quyết định có ghi nhận.

Chỉ đặt tên path `v2` không làm một thay đổi thiếu migration trở nên an toàn. Ngược lại, có thể triển khai provider binary v5 mà vẫn giữ `/api/v1` ổn định cho các clients cũ.

### Expand–migrate–contract

Đây là chiến lược phổ biến cho dữ liệu và API:

~~~text
EXPAND: thêm field/endpoint/DB column mới, vẫn giữ cũ
   |
   v
MIGRATE: consumer mới chuyển sang contract mới
   |
   v
MONITOR: xác nhận consumer cũ đã rời support window
   |
   v
CONTRACT: loại bỏ field/endpoint cũ theo release được công bố
~~~

Không dùng `contract` (bước xóa) trước khi clients cũ đã chuyển xong.

## 21. Tương thích message contracts: Kafka, RabbitMQ và Avro

Một consumer event có thể bị hỏng khi:

- Bỏ field `eventId` hoặc `aggregateId`.
- Đổi tên event type `OrderPaid` thành `PaymentSettled`.
- Thêm enum value mà handler có exhaustive switch.
- Đổi field timestamp millis thành seconds.
- Đổi partition key/ordering, làm workflow reorder.
- Đổi schema subject/registry compatibility mode.
- Thay at-least-once delivery/retry/DLQ policy mà consumer dựa vào.
- Quên giữ schema evolution rules của Avro/Protobuf.

**Avro:** reader/writer schema resolution có quy tắc riêng về defaults, unions và compatibility. Một change hợp lệ với BACKWARD trong schema registry chưa tự chứng minh business semantics (ví dụ cents->dollars).

**Protobuf:** không tùy tiện reuse field numbers; đổi wire type có thể phá compatibility. Không chỉ đổi tên Java class và coi schema binary tương thích. Tránh reuse reserved tags.

**RabbitMQ JSON:** tương tự HTTP JSON, nhưng metadata còn gồm routing key, exchange, content type, message headers, retry and DLQ behavior.

**Consumer-driven messaging contract tests** có thể kiểm payload và headers mà consumer cần; integration tests broker thật kiểm listener/serialization/ack. Đừng dùng đơn thuần “broker nhận message” làm proof consumer xử lý business đúng.

## 22. GraphQL, SOAP và gRPC

### GraphQL

- **Thêm field** vào schema thường không làm existing queries thất bại.
- **Xóa/rename field** làm query cũ lỗi validation.
- **Thay nullable thành non-null hoặc ngược lại** cần xét cả schema clients và runtime null propagation; đổi từ nullable sang non-null có thể làm response error bubbling khác.
- **Thêm enum value** có thể phá generated clients exhaustive mapping.
- **Đổi argument thành required** làm query cũ không hợp lệ.
- **Thay resolver semantics/performance** có thể phá client dù SDL không đổi.

Test nên thực hiện **queries cũ thật** qua `GraphQlTester` với schema/resolvers mới, ngoài schema diff.

### SOAP/WSDL

- Đổi namespace/operation/request/response XSD elements có thể phá generated clients.
- Element mới nếu schema strict có thể fail validation.
- Đổi fault code/details là behavioral contract change.
- Test bằng XML/WSDL/XSD fixtures và SOAP client thật khi cần.

### gRPC/Protobuf

- Protobuf field numbers và wire types quan trọng hơn tên Java.
- Thêm field thường có schema evolution support, nhưng không hứa business semantics.
- Streaming behavior, deadlines, metadata headers và status codes cũng là contract.
- Kiểm cả generated clients cũ với server implementation mới; tránh chỉ compile generated v2 client.

## 23. Database schema evolution và clients gián tiếp

Khi hai services cùng truy cập một schema DB (điều thường nên tránh), DB migration có thể là breaking change dù HTTP API không đổi.

Các ví dụ:

- Rename/drop column khi consumer cũ vẫn query.
- Thêm NOT NULL column không có default làm INSERT từ phiên bản cũ fail.
- Đổi enum/check constraint làm dữ liệu cũ không hợp lệ.
- Đổi index/collation ảnh hưởng query semantics/order.
- Thay timezone/precision trong timestamp/decimal.
- Thay transaction isolation hoặc consistency behavior.

**Expand–contract migrations**:

1. Add nullable column/alias view trước.
2. App mới đọc cả cũ/mới hoặc dual-write có kiểm soát.
3. Backfill dữ liệu, validate totals.
4. Switch reads sang schema mới.
5. Giữ rollback compatibility trong deployment overlap window.
6. Drop old column sau support window.

Test database migrations nên có integration harness (Testcontainers PostgreSQL/MySQL phù hợp production), không dùng H2 thay toàn bộ PostgreSQL-specific semantics rồi tuyên bố migration compatibility.

## 24. CI release gate cho compatibility

Một pipeline thực tế có thể có:

~~~text
Pull Request mở
  |
  v
Unit tests
  |
  v
Generate OpenAPI/AsyncAPI/schema artifact
  |
  +-- Diff với released baseline
  |      +-- Breaking? -> review và chặn
  |
  v
Provider contract verification
  |      +-- Consumer v1, v2, v3 supported
  |
  v
Consumer stub tests
  |      +-- HTTP, deserialization, errors
  |
  v
Real HTTP/component smoke
  |
  v
Staging/canary traffic và observability
  |
  v
Release / rollback theo policy
~~~

### Một compatibility gate tốt

- Lấy baseline từ **last released version** hoặc approved contract registry, không chỉ từ branch trước commit.
- Biết consumer versions đang deployed và **support window**.
- Kiểm method/path/status/headers/body/validation, không chỉ Java DTO.
- Có semantic invariants cho money, units, timezone, enum và pagination.
- Dùng server-side generated tests từ consumer contracts khi thích hợp.
- Có real HTTP smoke với packaged artifact hoặc server tương đương.
- Nếu breaking, phải **fail pipeline** hoặc yêu cầu documented exception/migration plan.
- Không auto-rewrite golden fixtures mỗi lần CI chạy.
- Có contract artifact version/owner và traceability đến consumer.
- Không ghi sensitive payloads/tokens vào artifacts hoặc CI logs.

### Khi kết quả FAIL

Một báo cáo có ích:

~~~text
Contract: catalog-v1 / consumer mobile-2.9
Provider candidate: build 9f4...
Interaction: GET /api/v1/products/BOOK-1
Expected: HTTP 200, application/json
Expected fields: sku:string, name:string,
                 priceCents:integer cents
Actual: HTTP 200, application/json
Missing: priceCents
Unexpected: priceInCents
Impact: LegacyCatalogClient cannot deserialize
Decision: BLOCK release until alias restored or v2 migration
~~~

Đây là **mẫu report minh họa**, không phải stdout thực từ project. Không đưa token/credentials/PII vào diagnostic. Báo cáo phải nói **client nào bị ảnh hưởng**, không chỉ “JSON diff”.

## 25. Mutation tests: chứng minh tests sẽ đỏ khi contract bị phá

Trên branch sandbox, thử từng biến đổi và hoàn nguyên ngay:

| Mutation | Test dự kiến đỏ |
| --- | --- |
| Rename `priceCents` → `priceInCents` | Provider JSONPath + live client |
| Đổi giá 1999 → 20 trong provider | Business invariant provider/live tests |
| Xóa `sku` | Provider JSONPath + legacy constructor |
| Xóa `name` | Provider JSONPath + legacy constructor |
| Đổi ProductResponse thành XML | Provider Content-Type + client conversion |
| Đổi GET product từ 200 sang 202 | Provider status test |
| Đổi missing SKU từ 404 sang 200+null | Provider 404 + live HTTP error |
| Thêm `@NotBlank` cho request `note` | Old reservation POST test |
| Đổi `@Min(1)` thành `@Min(10)` | Old POST quantity=2 test |
| Đổi POST success 201 thành 200 | Provider POST + live POST tests |
| Đổi error code PRODUCT_NOT_FOUND | Provider + consumer 404 tests |
| Đổi path `/api/v1` thành `/api/v2` | All provider/live path tests |
| Đổi unknown-field reader sang strict | Consumer additive fixture test |
| Bỏ validation non-null price | Rename fixture may silently parse -> client test đỏ |
| Bật caching làm dữ liệu cũ | Cần thêm stateful cache contract tests |
| Bỏ idempotency key | Cần thêm retry/stateful tests |
| Đổi enum status mới | Cần thêm enum consumer fixture tests |
| Đổi date timezone | Cần thêm semantic/time tests |

**Chỉ assert “test suite pass” là chưa đủ.** Một test hữu ích phải thất bại khi behavior cụ thể mà nó bảo vệ bị thay đổi. Khi mutation không bị phát hiện, bổ sung test đúng boundary; không vội tăng timeout hoặc bỏ qua assertion.

## 26. Lỗi phổ biến khi kiểm compatibility

### 26.1. Provider tự viết cả expected và actual

Nếu test serialize cùng một DTO mới rồi so với chính JSON đó, rename field có thể khiến hai bên cùng thay, test vẫn xanh. Khắc phục bằng **frozen consumer contract fixture** và contract owned bởi consumer.

### 26.2. Chỉ dùng OpenAPI diff

Spec có thể quên cập nhật, không phản ánh serializer thực tế hoặc bỏ qua semantic changes. Dùng diff là early warning, **không phải bằng chứng runtime pass**.

### 26.3. Chỉ dùng happy path

Status/errors/validation/auth/pagination/retries có thể làm hỏng client dù GET 200 đúng. Thêm error interactions và negative tests.

### 26.4. Thấy additive field nên kết luận an toàn

Một consumer strict/coercion/codegen có thể reject unknown response field. Kiểm consumer thực sự hoặc công bố tolerant reader contract.

### 26.5. Dùng primitive cho mandatory JSON field

Missing `long priceCents` có thể deserialize thành 0 trong một số Jackson settings, khiến client tiếp tục xử lý sai. Dùng wrapper + explicit validation nếu contract không chấp nhận missing/null.

### 26.6. Chỉ chạy consumer mới nhất

Mobile/partner clients còn giữ versions cũ. Gắn contract status với deployed/supported consumer list. Hết support window mới ngừng gate cho version đó.

### 26.7. Cập nhật fixture khi test đỏ mà không review

Điều này “sửa” test bằng cách đổi hợp đồng đã phát hành. Contract version migration phải được review, không tự regenerated để xanh.

### 26.8. Coi schema diff phát hiện tiền tệ

Cùng JSON number nhưng đổi cents/dollars, rounding hoặc currency sẽ không hiện qua type diff. Dùng semantic tests và domain constraints.

### 26.9. Dùng retries để che breaking

Nếu provider trả 400 mới do validation thay đổi, retry 3 lần không giúp. Retry phải dành cho lỗi transient/được phép và có idempotency; không bao giờ dùng retry để che contract mismatch.

### 26.10. Full HTTP integration quá ít cases

Một random-port smoke chỉ kiểm vài flows. Provider MockMvc và consumer stubs giúp phủ nhiều branches nhanh hơn. Kết hợp thay vì thay thế tất cả bằng E2E chậm.

## 27. Contract review trước khi triển khai

Khi xem một PR thay đổi API, hỏi:

1. Nó đổi **public contract** hay chỉ internal implementation?
2. Những clients/versions nào đang sử dụng path này?
3. Có consumer nào strict về unknown fields/enums/nulls?
4. Nếu thêm field request, request cũ không có field ấy còn hợp lệ?
5. Nếu thay status, error body, Content-Type hoặc permission, client cũ xử lý ra sao?
6. Có thay đơn vị, timezone, rounding, sorting, pagination hay idempotency?
7. Có thể giữ alias/default cho một migration window?
8. Có test interaction thực và fixture cũ đã đóng băng?
9. Nếu có schema diff warning, ai phê duyệt waiver và theo tiêu chí nào?
10. Có thể rollback provider mà không phá consumer đã chuyển sang contract mới?
11. Có log/metric theo client version và error code để quan sát rollout?
12. Ngày deprecation/sunset đã công bố và đủ thời gian cập nhật?
13. Có khả năng consumer deploy trước provider, provider deploy trước consumer?
14. Với messaging, có schema registry compatibility mode và consumer lag policy đúng?
15. Với DB, migration có backward-compatible khi mixed-version deployments đang chạy?

## 28. Bài tập thực hành

**Bài A — response rename:** Đổi `priceCents` thành `priceInCents` trong provider, không sửa consumer. Xác định test nào đỏ, vì sao decoder sẽ thiếu required field.

**Bài B — semantic units:** Giữ field name và type nhưng trả `20` thay `1999`. Ghi nhận JSON shape gate pass mà business invariant fail.

**Bài C — additive:** Thêm field `warehouse` vào response. Chạy old client tolerant; kiểm nó vẫn đọc 3 fields cũ và không phụ thuộc warehouse.

**Bài D — strict reader:** Tạo một legacy client không có `@JsonIgnoreProperties(ignoreUnknown=true)` và bật unknown-property failure. Kiểm additive field có thể làm vỡ client.

**Bài E — request optional:** Cho `note` thêm vào `ReservationRequest` mà không `@NotBlank`; old POST phải 201.

**Bài F — required request:** Thêm `@NotBlank` cho `note` để tạo breaking case; old POST phải đỏ. Hoàn nguyên.

**Bài G — status semantics:** Đổi POST success 201 thành 202. Phân tích migration sang async job contract và client cũ nhận gì.

**Bài H — error mapping:** Đổi missing SKU từ 404 thành 200 với empty JSON. Kiểm provider/live HTTP tests.

**Bài I — enum:** Thêm trạng thái `ON_HOLD` vào response và tạo legacy enum parser không hỗ trợ. Thiết kế fallback hoặc versioning.

**Bài J — null:** Cho provider trả `priceCents=null` trên một SKU. Legacy record constructor cần fail-fast.

**Bài K — pagination:** Tạo GET list theo `createdAt DESC` và cursor. Đổi sort tie-breaker rồi viết test chống duplicate/missing items.

**Bài L — idempotency:** Tạo POST với `Idempotency-Key`, gửi hai requests cùng key; assert một business effect.

**Bài M — version gate:** Dùng một baseline OpenAPI đã release, chạy diff với candidate và review breaking warnings.

**Bài N — Spring Cloud Contract:** Viết DSL contract mô tả GET product, sinh provider verification tests/stubs với Spring Cloud Contract version tương thích Boot 3.3.

**Bài O — Pact:** Khai báo consumer interaction và verify provider against Pact broker; nghiên cứu cách giữ contracts theo deployed consumer versions.

**Bài P — multi-version:** Thêm consumer v2 và giữ v1 trong CI. Đặt support window rõ, không xóa v1 chỉ vì v2 đã deploy.

**Bài Q — network:** Dùng `@SpringBootTest(RANDOM_PORT)` gọi live endpoint với client cũ, kiểm status/errors. So khác biệt với MockMvc-only.

**Bài R — security:** Thay một required OAuth scope trên endpoint, tạo client principal v1 trong test và verify không mất quyền ngoài policy.

**Bài S — messaging:** Tạo Avro/Kafka schema v1/v2 và kiểm compatibility mode; thêm semantic test cho timestamp units.

**Bài T — expand–contract:** Viết migration plan giữ `priceCents` trong thời gian chuyển sang `priceMinorUnits`, theo dõi consumer uptake và cutover.

## 29. Checklist trước khi merge breaking-sensitive changes

- [ ] Đã xác định contract đang public hay internal?
- [ ] Biết consumers đang deployed và versions còn hỗ trợ?
- [ ] Baseline lấy từ last released/stable contract, không tự sinh từ SUT?
- [ ] Provider tests kiểm HTTP method/path/status/content type/headers theo hợp đồng?
- [ ] JSON shape test kiểm required fields/type/nullability?
- [ ] Request compatibility tests giữ body cũ và optional/required behavior?
- [ ] Consumer code cũ thực sự chạy với response candidate hoặc stub phù hợp?
- [ ] Có test error responses (400/401/403/404/429/5xx) theo usage?
- [ ] Có semantic assertions về cents/currency/timezone/sort/enum?
- [ ] Có positive/additive test và negative/breaking test?
- [ ] Thêm response field đã kiểm consumer strict/tolerant?
- [ ] Có API/schema diff nhưng không coi đó là lớp test duy nhất?
- [ ] Có xử lý thay đổi status, retries, idempotency và timeouts?
- [ ] Có real HTTP smoke khi packaging/serialization/wiring quan trọng?
- [ ] Khi messaging, có schema evolution và broker/event integration?
- [ ] Khi DB migrations, có mixed-version compatibility?
- [ ] CI chặn breaking change hoặc yêu cầu migration/waiver rõ?
- [ ] Fixture cũ không bị tự regenerate khi candidate thay đổi?
- [ ] Có deprecation/sunset/communication plan?
- [ ] Rollout có canary, telemetry per client version và rollback path?
- [ ] Không lấy một “test PASS” của negative illustration làm proof provider compatible?
- [ ] Đã phân biệt backward, forward và full compatibility?
- [ ] Đã kiểm đồng thời provider mới/client cũ và client mới/provider cũ nếu deploy lệch?
- [ ] Tất cả test reports xác nhận methods thực thi, không chỉ Gradle cache?
- [ ] Không tiết lộ PII/secrets trong golden fixtures và CI artifacts?

## 30. Tài liệu tham khảo

Tài liệu chính thức, phù hợp để đi tiếp từ lab **Spring Boot 3.3.5 / Java 17**:

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, MockMvc, RANDOM_PORT, `@RestClientTest`.
- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer` và RestClient/RestTemplate test boundaries.
- [Spring Framework 6.1 — MockRestServiceServer API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): `bindTo(RestClient.Builder)`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient request/response and error handling.
- [Spring Cloud Contract 4.1 Reference](https://docs.spring.io/spring-cloud-contract/reference/4.1/): consumer-driven/provider-driven contracts và stubs.
- [Spring Cloud 2023.0.x Reference](https://docs.spring.io/spring-cloud/docs/2023.0.x/reference/htmlsingle/): release train tương thích Boot 3.3.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): schema, request/response, status codes và API descriptions.
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step): types, required, nullability và object evolution.
- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): methods, status semantics, HTTP fields.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): reader/writer schemas và resolution.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): field number/wire compatibility.
- [Pact Documentation](https://docs.pact.io/): consumer-driven contracts, provider verification and deployment checks.
- [Jackson JsonIgnoreProperties](https://fasterxml.github.io/jackson-annotations/javadoc/2.16/com/fasterxml/jackson/annotation/JsonIgnoreProperties.html): tolerant reading behavior.

**Ghi nhớ:** Một thay đổi API chỉ được coi là backward-compatible sau khi chứng minh **consumer cũ vẫn gửi request, đọc response và giữ đúng business behavior**. Dùng frozen contracts, provider MockMvc, legacy consumer tests, JSON/schema diff, real HTTP smoke và semantic assertions kết hợp. Nếu phải thay đổi phá vỡ, chọn **versioning + expand–migrate–contract + hỗ trợ song song**, không âm thầm cập nhật fixture cho test xanh rồi phát hành.
