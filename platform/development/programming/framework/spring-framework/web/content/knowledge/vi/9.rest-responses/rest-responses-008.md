# Giữ hợp đồng API ổn định khi thay đổi cấu trúc dữ liệu trong Spring MVC

## 1. Hợp đồng API là lời cam kết với client

Một REST API vẫn có thể chạy thành công trong backend sau khi thay đổi DTO, entity hoặc cấu trúc database nhưng **client cũ lại ngừng hoạt động**. Điều này xảy ra khi cấu trúc hoặc ý nghĩa dữ liệu trên HTTP thay đổi ngoài những gì client đã được cam kết.

Ví dụ hợp đồng JSON ban đầu:

```http
GET /api/v1/products/7 HTTP/1.1
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"Notebook","price":129000}
```

Client có thể đang dựa vào các giả định sau:

- URL và HTTP method vẫn là `GET /api/v1/products/{id}`.
- Khi thành công, status là `200` và body là JSON object.
- Field `id` là số định danh ổn định.
- Field `name` luôn có nội dung tên sản phẩm.
- Field `price` là một con số có nghĩa là **đồng Việt Nam (VND)**, không bất ngờ trở thành chuỗi hoặc cent.
- Khi không tồn tại sản phẩm, endpoint trả `404` theo một cách đã được tài liệu hóa.
- Client không bắt buộc phải parse field mới, và server không tùy ý xóa field đã công bố.

Giả sử backend đổi tên Java property từ `name` sang `displayName`, đổi tiền từ `BigDecimal` sang `Money` và chuyển database sang bảng mới. Các thay đổi nội bộ này **không nhất thiết buộc JSON cũ phải đổi**. API contract là lớp biểu diễn công khai, độc lập với domain model và persistence schema.

Nếu server lặng lẽ thay JSON cũ bằng:

```json
{
  "id": 7,
  "displayName": "Notebook",
  "pricing": {"amount": 129000, "currency": "VND"}
}
```

thì client tìm `response.name` và `response.price` sẽ bị hỏng. Đây là thay đổi **breaking** cho các client phụ thuộc vào field cũ, dù dữ liệu vẫn nói về cùng một sản phẩm.

**Trọng tâm của bài:** quản lý sự tiến hóa của cấu trúc request/response trong **Spring Web MVC** sao cho hệ thống phát triển được mà không làm gián đoạn consumer đang sử dụng hợp đồng được hỗ trợ. Cơ chế áp dụng gồm request/response DTO, JSON serialization bằng Jackson, phân phiên bản, adapter mapping, tài liệu OpenAPI và các bài kiểm thử hợp đồng.

## 2. “Hợp đồng” bao gồm những gì ngoài JSON field?

Một API contract không chỉ là tên class hoặc DTO. Cần mô tả các yếu tố client quan sát được:

| Mặt hợp đồng | Ví dụ | Điều cần giữ ổn định |
| --- | --- | --- |
| Endpoint | `GET /api/v1/products/7` | URL, path params, HTTP method |
| Request headers | `Content-Type`, `Accept`, auth headers | Header bắt buộc, media types hỗ trợ |
| Request body | `{"name":"Notebook"}` | Field names, types, required/optional, constraints |
| Response status | `200`, `201`, `400`, `404` | Ngữ nghĩa thành công/thất bại |
| Response body | `{"id":7,"name":"Notebook"}` | JSON shape, kiểu, nullability và ý nghĩa |
| Error shape | `{"code":"PRODUCT_NOT_FOUND",...}` | Trường ổn định mà client đọc được |
| Pagination | `items`, `nextCursor` | Shape, ordering, cursor/offset semantics |
| Time, money, ID | ISO-8601, VND, opaque ID | Đơn vị, timezone, độ chính xác, định dạng |
| Headers response | `ETag`, `Location`, cache headers | Client caching, redirect/creation semantics |
| Behavioral rules | Giá, tồn kho, sort | Quy tắc nghiệp vụ có ảnh hưởng đến client |

Ví dụ, giữ nguyên JSON key `price` nhưng đổi ý nghĩa từ **VND** sang **cent** vẫn là breaking change. Giữ nguyên tên enum `ACTIVE` nhưng diễn giải trạng thái khác trước cũng có thể phá client. Thay response code từ `404` sang `200` với body lỗi có thể khiến consumer coi lỗi thành thành công.

**Phân biệt hai hướng tương thích:**

- **Backward compatibility của server mới:** request từ client cũ vẫn được chấp nhận và response mà client cũ hiểu vẫn giữ đúng contract.
- **Forward compatibility của client:** client được thiết kế để có thể bỏ qua những field mới, xử lý enum value chưa biết, và không phụ thuộc thứ tự key JSON, nếu contract cho phép.

Một server muốn thêm response field vào cùng phiên bản cần biết **chính sách extensibility** đã công bố và kiểm chứng client có thể chịu được. Đối với client deserialize strict hoặc SDK code-generated đóng schema, “chỉ thêm field mới” vẫn có thể gây lỗi. Vì vậy, khả năng tương thích là **tính chất của cả producer và consumer**, không chỉ của JSON nhìn bằng mắt.

## 3. Phân loại thay đổi cấu trúc dữ liệu

| Thay đổi | Thường an toàn không? | Điều kiện/khuyến nghị |
| --- | --- | --- |
| Đổi tên Java field nội bộ, JSON key giữ nguyên | Thường có | Dùng DTO và mapping/`@JsonProperty`; test wire format |
| Thêm field optional vào response | Có điều kiện | Client bỏ qua unknown fields và contract cho phép mở rộng |
| Thêm field optional vào request | Có điều kiện | Server phải dùng default hợp lý khi client cũ không gửi |
| Thêm endpoint mới | Thường có | Endpoint cũ vẫn hoạt động |
| Đổi thứ tự các key trong JSON object | Thường có | JSON object không đảm bảo thứ tự ngữ nghĩa |
| Xóa/đổi tên response field đã công bố | Breaking | Giữ v1 hoặc tạo v2 |
| Đổi kiểu `price: number` thành `price: string` | Breaking | Consumer parser và logic có thể hỏng |
| Đổi flat field thành nested object | Breaking | Ví dụ `price` thành `pricing.amount` |
| Đổi nghĩa/đơn vị giá trị giữ nguyên key | Breaking | Phải version và mô tả rõ |
| Thêm required request field | Breaking | Client cũ thiếu field; chuyển thành optional/default hoặc v2 |
| Chuyển optional field thành required | Breaking | Request cũ từng hợp lệ có thể bị từ chối |
| Chuyển non-null thành nullable / ngược lại | Có thể breaking | Consumer dereference hoặc validation phụ thuộc |
| Thêm enum response value | Có điều kiện | Client có xử lý unknown enum value không? |
| Thay status/error code hoặc error schema | Có thể breaking | Giữ semantics và công bố migration |
| Áp dụng pagination bắt buộc cho endpoint trả toàn bộ list | Có thể breaking | Client cũ có thể không tải đủ dữ liệu |
| Thay ordering của mảng kết quả | Có thể breaking | Nếu contract từng hứa sort theo tiêu chí cụ thể |
| Siết validation, giảm size limit hoặc rate limit | Có thể breaking | Request hợp lệ trước đây có thể thất bại |

Bảng là **đánh giá theo tác động**, không phải quy tắc tự động cho mọi client. Microsoft và các hệ sinh thái API lớn khác nhấn mạnh rằng định nghĩa breaking change phải rõ ràng: có nơi xem thêm JSON field là tương thích, có nơi xem đó là thay đổi hợp đồng. Hãy chọn một chính sách, ghi vào tài liệu và áp dụng nhất quán.

### Tính ổn định của “shape” và của “meaning”

Xem hai phản hồi:

```json
{"amount": 15.75, "currency": "USD"}
```

```json
{"amount": 1575, "currency": "USD"}
```

Cùng tên field, cùng JSON number, nhưng một API dùng **đô la**, API kia dùng **cent**. Nếu chuyển đổi mà không đổi contract thì client có thể tính tiền sai 100 lần. Vì vậy tài liệu phải mô tả **đơn vị, rounding, range và ý nghĩa**, ngoài JSON type.

Tương tự, `null`, vắng field, chuỗi rỗng `""`, số `0` và mảng rỗng `[]` không phải luôn tương đương. Client có thể phân biệt “không có”, “chưa biết” và “có giá trị rỗng”; thay một loại bằng loại khác cần đánh giá như thay đổi contract.

## 4. Không dùng JPA entity/domain object trực tiếp làm public API

Một nguyên nhân phổ biến của breaking changes là để JSON response phản chiếu toàn bộ object nội bộ:

```java
@GetMapping("/users/{id}")
public UserEntity getUser(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
```

Đây là **ví dụ phản diện**, chỉ minh họa nguyên tắc, không phải chương trình độc lập. Nếu `UserEntity` thay column/property, thêm relationship hoặc chứa `passwordHash`, cấu trúc JSON có thể vô tình thay đổi hoặc lộ dữ liệu. Lazy loading/circular references cũng có thể gây lỗi serialize.

Thiết kế ổn định hơn:

```text
Database schema / JPA entities
           |
           v
Domain model + business services
           |
           v
API mapper cho từng contract
           |
     +-----+-----+
     |           |
     v           v
ProductV1Dto   ProductV2Dto
     |           |
     v           v
JSON v1       JSON v2
```

**Input DTO** cũng tách riêng với **response DTO**. Input chỉ có những field mà client được phép cung cấp; response chỉ lộ những trường đã cam kết. `record` của Java 17 thuận tiện để mô tả cấu trúc bất biến, nhưng việc dùng record **không tự chứng minh API không đổi**: tên component, kiểu, annotations Jackson và cấu hình mapper đều ảnh hưởng wire format.

Đừng dùng reflection copy tự động toàn bộ entity sang DTO nếu việc bổ sung property có thể lặng lẽ làm đổi JSON. Mapper tường minh tuy nhiều dòng hơn nhưng dễ review và test.

## 5. Cơ chế giữ tên JSON khi đổi tên biến Java

Spring MVC dùng `HttpMessageConverter` để đọc/ghi body, thường là Jackson JSON converter trong ứng dụng Spring Boot Web. Nếu refactor Java property `name` thành `displayName` nhưng muốn client vẫn nhìn thấy JSON `"name"`, có thể khai báo:

```java
public record ProductV1(
        long id,
        @JsonProperty("name") String displayName,
        BigDecimal price) {}
```

Đây là snippet cần imports `com.fasterxml.jackson.annotation.JsonProperty` và `java.math.BigDecimal`. Object `new ProductV1(7L, "Notebook", new BigDecimal("129000"))` được Jackson serialize thành JSON có **key `name`**, không thành `displayName`. Annotation cố định tên bên ngoài; Java code có thể dùng `displayName()`.

Một trường hợp khác là **chấp nhận một tên thay thế ở request input** trong giai đoạn chuyển tiếp:

```java
public record PreviewRequest(
        @JsonAlias("displayName") String name,
        BigDecimal price) {}
```

Với Jackson 2, `@JsonAlias` cho phép deserialize từ `"displayName"` hoặc tên chính `"name"`, nhưng **không đổi tên được ghi khi serialize**: tên chính vẫn là `name`. Điều này hữu ích khi chỉ thay đổi cách client gửi một trường và muốn server hỗ trợ cả hai. Tuy nhiên:

- Không coi `@JsonAlias` là một chiến lược versioning đầy đủ: nó không xử lý nested structure, kiểu mới, đơn vị đo hay business semantics khác.
- Nếu cả `name` và `displayName` xuất hiện trong một JSON, thứ tự input có thể làm giá trị sau ghi đè giá trị trước. Hãy xác định chính sách từ chối payload mơ hồ nếu hệ thống yêu cầu, thay vì mặc định chấp nhận cả hai.
- Đừng dùng alias để vô tình mở thêm những field client không được phép điều khiển.
- Giữ annotation, mapper settings và contract tests cùng version API.

Một cách khác để giữ cấu trúc cũ là xây DTO riêng và map tường minh. Đó thường là giải pháp dễ kiểm soát hơn khi thay đổi lớn.

## 6. Ví dụ chạy được: duy trì v1 và mở rộng v2 trong Spring MVC

Mục tiêu minh họa:

- `GET /api/v1/products/{id}` giữ JSON cũ có `id`, `name`, `price`, ngay cả khi Java DTO dùng component `displayName`.
- `GET /api/v2/products/{id}` công bố representation mới có `displayName` và `pricing: {amount, currency}`, kèm `sku`.
- `POST /api/v1/products/preview` chấp nhận request field `name` hoặc alias `displayName` nhưng vẫn trả JSON field `name`.
- Kiểm thử `MockMvc` chặn regression khiến `v1` bị đổi shape ngoài ý muốn.

Dữ liệu lưu trữ chỉ được giả lập bằng object trong bộ nhớ; ví dụ không có database, authentication, distributed cache hay nghiệp vụ thương mại thật.

### 6.1. Cấu trúc Maven

```text
api-contract-demo/
├── pom.xml
└── src/
    ├── main/java/example/contract/
    │   ├── ApiContractApplication.java
    │   └── ProductController.java
    └── test/java/example/contract/
        └── ProductContractTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>api-contract-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/contract/ApiContractApplication.java`**

```java
package example.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiContractApplication.class, args);
    }
}
```

### 6.2. Hai DTO response với một dữ liệu nghiệp vụ

**`src/main/java/example/contract/ProductController.java`**

```java
package example.contract;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;

@RestController
public class ProductController {

    // Mô hình nội bộ; không trả thẳng ra HTTP.
    private record Product(
            long id, String name, BigDecimal price, String sku) {}

    // Contract JSON v1: id, name, price.
    // Java component đã đổi thành displayName, JSON vẫn giữ "name".
    public record ProductV1(
            long id,
            @JsonProperty("name") String displayName,
            BigDecimal price) {}

    // Contract JSON v2: id, displayName, pricing, sku.
    public record Money(BigDecimal amount, String currency) {}

    public record ProductV2(
            long id, String displayName, Money pricing, String sku) {}

    // Hỗ trợ alias phía request trong quá trình chuyển tiếp.
    public record PreviewRequest(
            @NotBlank @JsonAlias("displayName") String name,
            @NotNull @DecimalMin("0.01") BigDecimal price) {}

    // Output v1 tiếp tục giữ tên cũ.
    public record PreviewResponse(String name, BigDecimal price) {}

    @GetMapping(path = "/api/v1/products/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductV1 getV1(@PathVariable("id") long id) {
        Product product = load(id);
        return new ProductV1(
                product.id(), product.name(), product.price());
    }

    @GetMapping(path = "/api/v2/products/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductV2 getV2(@PathVariable("id") long id) {
        Product product = load(id);
        return new ProductV2(
                product.id(),
                product.name(),
                new Money(product.price(), "VND"),
                product.sku());
    }

    @PostMapping(
            path = "/api/v1/products/preview",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public PreviewResponse preview(
            @Valid @RequestBody PreviewRequest input) {
        return new PreviewResponse(input.name(), input.price());
    }

    private Product load(long id) {
        if (id != 7L) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found");
        }
        return new Product(
                7L, "Notebook", new BigDecimal("129000"), "NB-007");
    }
}
```

**Những quyết định làm nên tính ổn định:**

1. `Product` là mô hình nội bộ. Nó không tự xuất hiện ở HTTP response.
2. `ProductV1` dùng component Java `displayName` nhưng `@JsonProperty("name")` giữ JSON key `name`. Vì client v1 còn đọc tên cũ, chỉ refactor Java không gây breaking change.
3. `ProductV2` là response contract **mới**: nested `pricing` và `currency`, không giả vờ rằng client v1 hiểu representation này.
4. Cả v1 và v2 dùng cùng một hàm `load` để tránh tạo hai nguồn dữ liệu thật; phần khác nhau chỉ là **API mapping**.
5. `PreviewRequest` chỉ chứa các trường client được phép gửi. `@Valid` + Jakarta Validation kiểm tra text không trống, giá có mặt và giá ít nhất `0.01`. Không cho client chỉnh `sku`, `id` hay quyền truy cập qua DTO này.
6. `@JsonAlias` chỉ làm mềm **đầu vào**. Response preview vẫn dùng `PreviewResponse.name`, vì vậy client cũ không bị đổi response field.
7. Ví dụ giả lập sản phẩm duy nhất ID `7`. ID khác nhận `404` từ `ResponseStatusException`. Trong ứng dụng thật cần service, persistence và authorization đúng tài nguyên.

### 6.3. Gửi request và so sánh response

Chạy project từ thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh được thực hiện tuần tự. `mvn test` cần hoàn thành với status thành công trước khi chạy ứng dụng. Khi Spring Boot khởi động thành công ở cổng mặc định `8080`:

**API v1 giữ nguyên JSON:**

```bash
curl -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/v1/products/7
```

Response status và body (bỏ các HTTP headers không liên quan):

```http
HTTP/1.1 200
Content-Type: application/json

{"id":7,"name":"Notebook","price":129000}
```

Tên `name` xuất hiện nhờ `@JsonProperty` dù Java record component có tên `displayName`. Đừng dựa vào thứ tự các JSON object keys khi xây client.

**API v2 có cấu trúc mới:**

```bash
curl -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/v2/products/7
```

Body chính:

```json
{
  "id": 7,
  "displayName": "Notebook",
  "pricing": {"amount": 129000, "currency": "VND"},
  "sku": "NB-007"
}
```

Khoảng trắng/xuống dòng trong JSON ở trên được trình bày cho dễ đọc; server có thể trả một dòng. Đây là hai **contract song song**, không phải client v1 tự động đọc được v2.

**Request từ client cũ vẫn hoạt động:**

```bash
curl -i -X POST http://localhost:8080/api/v1/products/preview \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Notebook","price":129000}'
```

Body:

```json
{"name":"Notebook","price":129000}
```

**Request dùng alias mới vẫn được chấp nhận:**

```bash
curl -i -X POST http://localhost:8080/api/v1/products/preview \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Notebook","price":129000}'
```

Body vẫn là:

```json
{"name":"Notebook","price":129000}
```

Đó là ví dụ về **tolerant input** có kiểm soát, không phải chính sách chấp nhận tùy ý mọi field unknown. Nếu request chứa cả `name` và `displayName`, cần định nghĩa một quy tắc rõ ràng (ví dụ trả `400` khi hai giá trị trùng property) trong một phiên bản thực; ví dụ chỉ minh họa client gửi **một** trong hai tên.

**ID không tồn tại:**

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/v1/products/999
```

Status thường là `404 Not Found`. JSON lỗi chi tiết do exception handler, Spring Boot error configuration hoặc Spring MVC `ProblemDetail` tùy môi trường. **Không phụ thuộc vào một error body ngẫu nhiên chưa được tài liệu hóa**; nếu error response là hợp đồng, hãy xây và kiểm thử schema lỗi riêng.

## 7. Contract tests bằng MockMvc: kiểm tra shape thật trên HTTP

Chỉ unit-test Java DTO hoặc mapper là chưa đủ. Jackson config, controller annotation, converter, media type và response status cũng tham gia tạo HTTP contract. Một test gửi request qua `MockMvc` sẽ bắt được nhiều regression tại đường HTTP mà không cần bật một cổng server thực.

**`src/test/java/example/contract/ProductContractTest.java`**

```java
package example.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void v1KeepsPublishedNamesAndShape() throws Exception {
        mvc.perform(get("/api/v1/products/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.price").value(129000))
            .andExpect(jsonPath("$.displayName").doesNotExist())
            .andExpect(jsonPath("$.pricing").doesNotExist());
    }

    @Test
    void v2PublishesNewStructure() throws Exception {
        mvc.perform(get("/api/v2/products/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Notebook"))
            .andExpect(jsonPath("$.pricing.amount").value(129000))
            .andExpect(jsonPath("$.pricing.currency").value("VND"))
            .andExpect(jsonPath("$.sku").value("NB-007"))
            .andExpect(jsonPath("$.name").doesNotExist())
            .andExpect(jsonPath("$.price").doesNotExist());
    }

    @Test
    void requestOldNameStillWorks() throws Exception {
        mvc.perform(post("/api/v1/products/preview")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\",\"price\":129000}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.displayName").doesNotExist());
    }

    @Test
    void requestAliasDoesNotRenameV1Response() throws Exception {
        mvc.perform(post("/api/v1/products/preview")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Notebook\",\"price\":129000}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.displayName").doesNotExist());
    }

    @Test
    void invalidRequestIsRejected() throws Exception {
        mvc.perform(post("/api/v1/products/preview")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\",\"price\":0}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingProductHasNotFoundStatus() throws Exception {
        mvc.perform(get("/api/v1/products/999"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
mvn test
```

Kết quả thành công có ý nghĩa: tất cả các trường hợp test trên pass và Maven kết thúc với exit code `0`. Thông báo tổng kết thường có dạng `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`; số thời gian chạy, các log và thứ tự test tùy môi trường.

**Phạm vi của test:** những test này giữ **ví dụ** v1, v2 và các đường lỗi nêu trên. Trong dự án thật, bổ sung tests về request thiếu field, null, unknown fields, enum, BigDecimal precision, thời gian, pagination, authorization và response lỗi. Cần giữ contract fixtures từ một bản API đã được duyệt để phát hiện thay đổi vô ý; test được tạo mới từ code hiện hành mà không so với contract cũ có thể “đúng đồng thời với một thay đổi gây hỏng”.

## 8. Cách tiến hóa mà vẫn phục vụ client cũ

Một quy trình hiệu quả là **expand → migrate → contract**:

1. **Kiểm kê consumer và hợp đồng hiện hữu.** Liệt kê endpoint, field, kiểu, required/nullable, unit, error codes, phân trang, các SDK và ứng dụng mobile không thể cập nhật tức thời. Xác định client nào cần giữ.
2. **Xác định thay đổi có thể ảnh hưởng client.** Đừng đánh giá chỉ từ diff Java class; hãy so sánh JSON/HTTP schema cũ và mới, đồng thời so sánh ngữ nghĩa. Với thay đổi lớn, đánh dấu breaking.
3. **Expand khả năng server mà không xóa v1.** Thêm v2 hoặc một tính năng tương thích; ánh xạ cả hai DTO từ cùng domain model. Khi đổi request field nhỏ, có thể tạm chấp nhận alias cũ/mới với quy tắc mơ hồ được xử lý rõ.
4. **Phát hành tài liệu, SDK và ví dụ mới.** Công bố JSON mẫu, OpenAPI schema, unit/timezone, API error contract và đường nâng cấp từ v1 lên v2. Với đối tác ngoài tổ chức, kế hoạch hỗ trợ version cũ phải có thời hạn.
5. **Migrate các client theo đợt.** Dùng traffic analytics, metrics hoặc version headers để đánh giá còn consumer v1; đừng giả định “backend đã deploy” đồng nghĩa client đã nâng cấp.
6. **Theo dõi lỗi contract thực tế.** Quan sát tỉ lệ `400`/`404`/`406`, lỗi deserialize phía client, việc dùng alias cũ; tránh log payload nhạy cảm. Hỗ trợ rollback trong khoảng chuyển đổi.
7. **Chỉ retire hợp đồng cũ theo chính sách deprecation đã công bố.** Thực hiện khi đã xác nhận client còn lại và mốc hỗ trợ. Việc loại bỏ endpoint v1 là thay đổi mang tác động bên ngoài, cần phối hợp release.

Khi triển khai rolling deployment nhiều instance, server cũ và mới có thể cùng tồn tại. Một migration chỉ thành công nếu dữ liệu chung/database/message events chịu được cả hai phiên bản trong giai đoạn chuyển tiếp. Đây là lý do nên giữ tương thích **cả luồng đọc và ghi** khi cập nhật schema chung, thay vì nâng database rồi ngay lập tức xóa field cũ.

### Tình huống đổi field name mà chưa cần v2

Nếu chỉ đổi Java class cho dễ hiểu, sử dụng `@JsonProperty("oldName")` hoặc API mapper để giữ nguyên JSON. Không tự động tạo version mới cho **mọi** refactor nội bộ.

### Tình huống cần v2

Nếu biến `price: 129000` thành `pricing: {amount:129000,currency:"VND"}`, client cũ không thể suy ra đường dẫn mới. Một v2 song song là lựa chọn dễ giải thích. Đừng xóa `price` khỏi v1 chỉ vì v2 đã có.

### Tình huống thêm optional field

Nếu hợp đồng nói client phải bỏ qua unknown response fields, thêm `description` (optional) thường được chấp nhận:

```json
{"id":7,"name":"Notebook","price":129000,"description":"A5"}
```

Tuy nhiên, client generated từ schema đóng có thể fail khi gặp field lạ. Vì vậy CI nên kiểm tra behavior consumer, và tổ chức phải công bố chính sách mở rộng schema thay vì coi additive luôn tuyệt đối an toàn.

## 9. Chọn cách version API

| Cách | Ví dụ | Điểm mạnh | Điểm cần quản lý |
| --- | --- | --- | --- |
| Version trong URL | `/api/v1/products`, `/api/v2/products` | Dễ nhìn và test, routing rõ | URL song song, nhiều mappings |
| Version qua header | `X-Api-Version: 2` | URI ổn định | Client/proxy/cache phải xử lý header |
| Version qua media type | `Accept: application/vnd.example.product-v2+json` | Gắn version với representation | Nội dung Content Negotiation phức tạp hơn |
| Version qua query | `?version=2` | Dễ thử nghiệm | Policy cache, documentation và routing cần nhất quán |

Trong Spring MVC 6.1, version qua URL dễ trình bày với các `@GetMapping` riêng. Không dựa vào annotation versioning chuyên biệt của các Spring major versions ra đời sau để làm ví dụ Boot 3.3.5 chạy được.

Hãy định nghĩa **version scope** rõ: version của toàn API, resource representation, hay một endpoint contract? Nếu chỉ thay một field trong một loại product, có thể dùng resource-specific versioning theo chính sách dự án; nhưng tránh một hỗn hợp khó dự đoán giữa URL, header và query. Không lấy nhãn `v2` làm bằng chứng rằng mọi breaking change trong tương lai của v2 đều được phép.

### Deprecation không đồng nghĩa với xóa ngay

Khi có v2, v1 có thể được đánh dấu deprecated trong tài liệu/API catalog, gửi tín hiệu qua headers tiêu chuẩn phù hợp nếu tổ chức sử dụng, và có kế hoạch sunset. Tránh công bố một thời hạn mà đội vận hành không cam kết thực hiện được. Mọi client cần có hướng di chuyển, ví dụ mapping:

| v1 | v2 |
| --- | --- |
| `name` | `displayName` |
| `price` (VND) | `pricing.amount` (VND) |
| Không có currency field | `pricing.currency = "VND"` |
| Không có SKU trong v1 output | `sku` được bổ sung ở v2 |

Bảng chỉ minh họa dữ liệu của ví dụ; hợp đồng thực tế còn phải mô tả nullability, units, error semantics và các endpoint khác.

## 10. Các vùng dễ gây breaking change âm thầm

### 10.1. Required, optional, null và absent

Đầu vào JSON:

```json
{}
```

```json
{"description":null}
```

```json
{"description":""}
```

Ba dữ liệu trên có thể có ý nghĩa khác nhau: không yêu cầu thay đổi, xóa mô tả, đặt mô tả thành chuỗi rỗng. Khi thiết kế PATCH cần biểu diễn rõ trạng thái **absent** và **present null**; DTO thông thường chỉ có `String description` có thể gộp cả hai thành Java `null`. Cân nhắc JSON Merge Patch, JSON Patch hoặc command DTO chứa thông tin field presence nếu nhu cầu thật sự cần.

Đừng thêm `@NotNull` vào trường mà client cũ có thể không gửi rồi coi đó là thay đổi tương thích. Để thêm field mới cho request v1, thường phải để optional và quy định default không thay đổi hành vi trước đây.

### 10.2. Kiểu số và độ chính xác

`Integer`, `Long`, `BigDecimal` và floating-point có behavior khác nhau. JavaScript clients có vùng số nguyên an toàn giới hạn; IDs lớn có thể cần **chuỗi định danh opaque** nếu contract ngay từ đầu đã quy định vậy. Không tự đổi từ JSON number sang string trong endpoint đang phục vụ.

Với tiền, ưu tiên mô tả chính xác `amount`, `currency`, đơn vị và quy tắc rounding. `BigDecimal` tránh nhiều lỗi nhị phân của `double` nhưng không tự giải quyết hợp đồng tiền. Nếu đổi đơn vị từ VND sang đơn vị nhỏ nhất hoặc USD, đó là thay đổi ngữ nghĩa.

### 10.3. Date/time và timezone

`"2026-10-21"` (local date), `"2026-10-21T04:00:00Z"` (instant) và một chuỗi timestamp không timezone không thể thay thế nhau tùy ý. Hợp đồng nên chọn kiểu và mô tả timezone (ví dụ UTC), độ chính xác fractional seconds và định dạng ISO-8601 cụ thể. Nâng cấu hình Jackson cho Java Time types có thể làm JSON đổi biểu diễn; hãy có test serialized fixtures khi nâng thư viện.

### 10.4. Enum mở rộng

Giả sử client có:

```java
switch (status) {
    case ACTIVE -> showActive();
    case INACTIVE -> showInactive();
}
```

Đây là **snippet minh họa**, yêu cầu `status` là enum và các hàm được định nghĩa trong code client. Thêm `SUSPENDED` trong response có thể làm client không xử lý được, đặc biệt khi enum parser nghiêm ngặt. Với enum được phép phát triển, thiết kế unknown fallback ngay từ đầu và mô tả chính sách forward compatibility. Với loại enum đóng, thêm value có thể xem là breaking.

### 10.5. Pagination và mảng

Một API từng trả toàn bộ:

```json
[{"id":1},{"id":2},{"id":3}]
```

nếu chuyển sang:

```json
{"items":[{"id":1},{"id":2}],"nextCursor":"abc"}
```

sẽ đổi kiểu top-level từ array sang object và thiếu các phần tử mà client cũ chờ đợi. Đây là breaking change, kể cả khi lý do là tăng hiệu năng. Nếu cần pagination mới, dùng v2 hoặc một endpoint mới; xác định page size, stable ordering, cursor semantics và điều gì xảy ra khi tài nguyên thay đổi trong lúc phân trang.

### 10.6. Schema lỗi và status

Client thường xử lý lỗi theo `status` và machine-readable `code`, không chỉ thông điệp người dùng. Đổi `404` thành `200` với `{"success":false}` hoặc đổi `error.code` thành `reason` có thể khiến retry logic và UI sai. Thiết kế error response ổn định, có mã lỗi hữu ích, và không lộ internal stack trace. Nếu dùng `ProblemDetail` theo RFC 9457, hãy xác định rõ contract của các extension fields và cách consumer đọc `type`/`status`/`detail`; không trộn nhiều schema lỗi tùy ý.

### 10.7. Configuration Jackson và response advice

Một lần thay `ObjectMapper` hoặc global `@JsonInclude`, naming strategy, timezone, property visibility, polymorphic typing hay `ResponseBodyAdvice` có thể đổi JSON **của mọi endpoint**. Trước khi áp dụng, hãy kiểm thử representative endpoints ở từng version.

`@JsonAlias` chỉ hỗ trợ deserialize aliases; `@JsonProperty` kiểm soát property name; `@JsonIgnore` có thể làm field biến mất; `@JsonInclude(Include.NON_NULL)` có thể chuyển field explicit null thành field absent. Không gọi những annotation này là “nội bộ” khi chúng ảnh hưởng wire contract.

## 11. Ghi hợp đồng bằng OpenAPI và kiểm thử ở CI

OpenAPI mô tả endpoints, operations, parameters, request/response media types, status codes và JSON schemas. Một đoạn schema v1 minh họa:

```yaml
openapi: 3.0.3
info:
  title: Products API
  version: 1.0.0
paths:
  /api/v1/products/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: integer
            format: int64
      responses:
        "200":
          description: Product v1
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductV1"
        "404":
          description: Product not found
components:
  schemas:
    ProductV1:
      type: object
      required: [id, name, price]
      properties:
        id: {type: integer, format: int64}
        name: {type: string}
        price:
          type: number
          description: Amount in VND
```

Đây là **đoạn OpenAPI minh họa contract cho một endpoint**; nó không mô tả toàn bộ project ở mục 6 hoặc hoàn chỉnh error schema. Trong code thật, cân nhắc validation constraints, nullable, examples, response headers, auth và mọi error status.

Một pipeline kiểm soát thay đổi có thể:

1. Lưu schema đã phát hành làm baseline, không tự cập nhật baseline chỉ để test pass.
2. Generate/OpenAPI từ bản mới hoặc xây schema contract versioned.
3. Chạy **schema diff/compatibility check** để phát hiện field bị xóa/đổi tên/đổi kiểu, required biến động, endpoint bị mất, status đổi.
4. Chạy `MockMvc` integration tests với request/response fixtures cũ.
5. Chạy **consumer-driven contract tests** với những giả định thật của các client quan trọng.
6. Chặn merge/deploy hoặc yêu cầu version bump khi gặp breaking changes chưa được phê duyệt.
7. Khi release, cập nhật docs, changelog, SDK và hướng migration.

Chỉ so sánh OpenAPI schema chưa đủ: đổi đơn vị từ VND sang USD, thay sort order hay cách tính tổng vẫn có thể giữ cùng schema JSON. Phải có tests ngữ nghĩa nghiệp vụ và consumer tests.

### Snapshot test có nên so sánh nguyên chuỗi JSON?

Chụp nguyên body và so sánh string từng ký tự có thể bắt field thay đổi, nhưng sẽ thất bại vô ích khi thứ tự JSON object keys hoặc whitespace đổi. Thường nên parse JSON và so sánh **cây JSON/JSONPath theo hợp đồng**. Với những field contract có order cố định (như mảng đã sort), hãy kiểm tra đúng thứ tự mảng. Với currency/number/time, assert cả ý nghĩa và giá trị chuẩn.

### Producer tests và consumer tests khác nhau

Producer tests hỏi: “Server còn trả đúng những thứ đã hứa?” Consumer tests hỏi: “Client thực tế còn chạy được với response/request của server mới?” Nếu chỉ test server mới theo DTO mới, một rename làm hỏng client cũ có thể bị bỏ sót. Khi nhiều team sở hữu nhiều client, cần phối hợp contract fixtures/chạy test trên cả hai phía.

## 12. Quy trình review một thay đổi DTO/JSON

Ví dụ developer đề xuất PR: “Chuyển `Product.price` sang `Product.pricing.amount` vì backend đổi Money model.”

Hãy kiểm tra theo chuỗi:

- **Public contract hiện nay:** API nào đang trả `price`? v1/v2, mobile, SDK, partner?
- **Diff wire format:** JSON thực tế trước/sau khác key/type/meaning gì? Cả thành công lẫn lỗi?
- **Tương thích phía consumer:** nếu client cũ deserialize response mới, điểm nào có thể fail?
- **Phương án không breaking:** giữ v1 DTO mapper trả `price`, thêm v2 cho `pricing`.
- **Request compatibility:** client cũ gửi field nào? Trường nào vừa được đánh dấu required?
- **Status và metadata:** `Content-Type`, status, pagination, error codes có đổi không?
- **Security:** entity mới có fields nhạy cảm bị JSON serializer lộ vô tình không?
- **Tests:** v1 fixtures vẫn pass, v2 fixtures mới pass, validation/error cases phù hợp?
- **Release:** docs và thời gian hỗ trợ v1 có rõ không? Telemetry theo dõi client cũ?

Ví dụ diff phù hợp:

```diff
- // V1 controller trả thẳng domain Product.
- return productService.find(id);
+ // V1 controller giữ hợp đồng JSON cũ qua mapping.
+ Product product = productService.find(id);
+ return new ProductV1(
+         product.getId(),
+         product.getDisplayName(),
+         product.getMoney().getAmount());
```

Đây là **diff giải thích kiến trúc**, phụ thuộc các class service/domain giả định và không phải đoạn có thể paste vào project chạy ở mục 6. Nó cho thấy điểm cần bảo vệ là representation ở ranh giới HTTP, không phải tên method nội bộ.

## 13. Một số quy tắc thực hành

1. **Version hợp đồng công khai, không version theo database schema.** Một schema mới có thể phục vụ cả v1/v2 thông qua mapper.
2. **Giữ tách biệt input DTO và output DTO.** Vừa tránh over-posting vừa kiểm soát response fields.
3. **Định nghĩa “tương thích” bằng consumer thực.** Cho phép unknown fields/enum fallback khi đã công bố; đừng giả định SDK nào cũng tolerant.
4. **Không đổi tên, kiểu, đơn vị hoặc semantic của field v1 tùy tiện.** Nếu phải đổi, tạo v2 có migration.
5. **Tạo field mới là optional khi cần tương thích với request cũ**, với default giữ logic cũ; đừng thêm required request fields âm thầm.
6. **Giữ quy tắc null/absent/empty nhất quán.** Đặc biệt quan trọng với PATCH và các DTO có primitive defaults.
7. **Hạn chế global Jackson settings và response wrappers.** Mỗi thay đổi toàn cục đều cần contract regression tests.
8. **Công bố mốc deprecated/sunset có thể thực thi được.** Đo usage của version cũ trước khi loại bỏ.
9. **Test status, headers, content type, body và error contract.** Không chỉ assert controller trả đúng class Java.
10. **Giữ tính bảo mật ở tầng service.** DTO hẹp, validation và authorization là các nhiệm vụ độc lập; không dựa vào Jackson annotation để thực hiện phân quyền.

## 14. Bài tập tự kiểm tra

1. Backend đổi Java field `displayName` nhưng client vẫn cần JSON `name`. Bạn có thể dùng `@JsonProperty` ra sao, và khi nào mapper DTO rõ ràng hơn?
2. Vì sao thêm field response thường an toàn hơn xóa field, nhưng không bảo đảm an toàn với mọi client?
3. Client cũ gửi request không có `currency`. Làm thế nào thêm currency mà không biến request cũ thành `400`?
4. Giữ `price` là JSON number nhưng đổi đơn vị tiền sang cents. Hợp đồng có giữ nguyên không? Vì sao?
5. `@JsonAlias("displayName")` có khiến response tự xuất `displayName` thay cho `name` không?
6. Vì sao thay array response bằng object `{"items":[...]}` có thể là breaking change?
7. Có cần thay URL từ `/v1` sang `/v2` khi chỉ đổi tên biến nội bộ không?
8. Contract test của một controller nên so sánh những yếu tố nào bên ngoài class Java?
9. Khi hai phiên bản server cùng chạy trong rolling deploy, những thay đổi database/message schema nào có thể làm instance cũ bị hỏng?
10. Nếu `null` và vắng field từng mang hai ý nghĩa, một DTO Java `String` đơn giản có luôn giữ được sự khác biệt này không?

**Gợi ý đáp án:** (1) Cố định JSON key hoặc map DTO; (2) strict clients và closed SDK có thể từ chối unknown fields; (3) optional/default giữ behavior cũ hoặc version mới; (4) không, semantic thay đổi; (5) không, alias dùng khi đọc; (6) top-level type và phân trang thay đổi; (7) không cần nếu wire contract vẫn y nguyên; (8) URL/method/status/headers/media type/shape/meaning/error; (9) schema chỉ hỗ trợ instance mới có thể phá bản cũ; (10) không, cần presence-aware representation khi quan trọng.

## 15. Tài liệu tham khảo

- [Spring MVC: ResponseBody và HttpMessageConverter](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework: Jackson JSON](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/jackson.html)
- [Spring Boot 3.3: Testing Spring Boot Applications và MockMvc](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Jackson 2: JsonAlias Javadoc](https://fasterxml.github.io/jackson-annotations/javadoc/2.12/com/fasterxml/jackson/annotation/JsonAlias.html)
- [Microsoft: Web API Design Best Practices](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design)
- [Microsoft: API Design and Versioning](https://learn.microsoft.com/en-us/azure/architecture/microservices/design/api-design)
- [OpenAPI Specification 3.0.3](https://spec.openapis.org/oas/v3.0.3)
- [GitHub REST API: Breaking Changes](https://docs.github.com/en/rest/about-the-rest-api/breaking-changes)

Bài học giới hạn trong **ổn định hợp đồng REST API khi thay đổi cấu trúc dữ liệu** và những kỹ thuật Spring MVC có giá trị trực tiếp cho nhiệm vụ đó. Chương trình minh họa dùng Java 17 và Spring Boot 3.3.5; các chiến lược compatibility/versioning là quy tắc thiết kế cần được quyết định theo hợp đồng và consumer thực tế.
