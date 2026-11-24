# Kiểm thử JSON, validation và cấu hình với cùng dữ liệu ở JVM và native

## 1. Mục tiêu: so sánh cùng một hợp đồng trên hai runtime

Khi chuyển ứng dụng Spring Boot sang GraalVM Native Image, một yêu cầu HTTP có thể được xử lý qua nhiều lớp: nhận JSON, deserialize thành DTO, bind cấu hình, validate dữ liệu, chạy nghiệp vụ và serialize response. Trên JVM, reflection và metadata có thể được khám phá linh hoạt khi chạy. Với Native Image, Spring AOT và reachability analysis chuẩn bị trước một phần cấu trúc và metadata cần thiết.

Vì vậy, một endpoint trả kết quả đúng trên JVM chưa đủ chứng minh nó hoạt động giống nhau trong native executable. Những khác biệt có thể xuất hiện ở constructor binding, Jackson creator/property discovery, polymorphic JSON, custom serializer, validation provider, message interpolation hoặc cấu hình được nạp từ environment.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài này xây dựng phương pháp kiểm thử để chạy **cùng một tập dữ liệu và cùng một contract** trên hai bản:

- Bản JVM: executable Spring Boot JAR chạy bằng `java -jar`.
- Bản native: executable được tạo qua Spring AOT và GraalVM Native Image.

Mục tiêu là so sánh chức năng và dữ liệu một cách có thể tái lập. Chỉ số startup/RSS có thể được đo bổ sung, nhưng trước hết hai bản phải xử lý cùng input và cho kết quả tương đương theo contract đã xác định.

## 2. Những gì cần giữ giống nhau trong phép thử

Để kết quả có ý nghĩa, cố định các yếu tố sau:

| Yếu tố | Yêu cầu giữa JVM và native |
|---|---|
| Source code | Cùng Git commit hoặc revision được ghi nhận |
| Spring Boot/dependencies | Cùng version và dependency graph |
| Test fixtures | Cùng file JSON hợp lệ, không hợp lệ và file cấu hình |
| Spring profiles | Cùng profile logic; ghi rõ profile structural dùng khi AOT |
| Runtime properties | Cùng giá trị endpoint, timeout, limits và feature flags |
| External files | Cùng nội dung file, mount path tương đương |
| Locale/timezone | Cùng cấu hình nếu ảnh hưởng JSON/date/message |
| Database/fixtures | Cùng schema và dữ liệu test nếu endpoint có persistence |
| HTTP contract | Cùng method, URL, headers, body và expected status |
| Resource limits | Cùng CPU/RAM/container constraints khi đo hiệu năng |

Không nhất thiết phải dùng cùng process startup command, vì một bên chạy JVM và một bên chạy executable. Điều cần giữ giống là **đầu vào và điều kiện quan sát**. Ghi lại mọi khác biệt bắt buộc như JVM flags, native build args và runtime image.

## 3. Xác định contract JSON trước khi viết test

Giả sử endpoint tạo đơn hàng nhận request:

```json
{
  "customerId": "C-1001",
  "quantity": 2,
  "unitPrice": 125000,
  "delivery": {
    "city": "Da Nang",
    "express": true
  }
}
```

Response contract:

```json
{
  "orderId": "ORD-1001",
  "total": 250000,
  "status": "ACCEPTED"
}
```

Contract cần mô tả rõ:

- Field bắt buộc và field tùy chọn.
- Kiểu dữ liệu, giới hạn số và quy tắc null/blank.
- Cách xử lý field không biết (unknown properties).
- Enum, ngày giờ, số thập phân và timezone.
- Status code và cấu trúc error response.
- Field response có ổn định hay chứa giá trị sinh ngẫu nhiên.

Không chỉ so sánh JSON text nguyên văn nếu thứ tự field không thuộc contract. Nên parse JSON và so sánh cấu trúc/giá trị. Nếu field là timestamp hoặc ID sinh tự động, dùng clock/ID provider có thể kiểm soát hoặc so sánh theo quy tắc đã định.

## 4. Tạo DTO và validation thống nhất

Ví dụ DTO dùng record và Jakarta Bean Validation:

```java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @Min(1) @Max(100) int quantity,
        @Positive BigDecimal unitPrice,
        @Valid @NotNull Delivery delivery) {

    public record Delivery(
            @NotBlank String city,
            boolean express) {
    }
}
```

Controller:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        BigDecimal total = request.unitPrice()
                .multiply(BigDecimal.valueOf(request.quantity()));

        return ResponseEntity.ok(
                new OrderResponse("ORD-1001", total, "ACCEPTED"));
    }
}
```

Ví dụ cần import annotation từ `jakarta.validation.constraints`, `jakarta.validation.Valid`, `BigDecimal` và Spring Web APIs. Dự án phải có validation implementation, thường qua `spring-boot-starter-validation`. Nếu thiếu provider, annotation có thể không được thực thi như mong đợi.

`@Valid` trên nested property làm validation tiếp tục vào `Delivery`. `@NotNull` đảm bảo object con không null; `@NotBlank` kiểm tra chuỗi không null, không rỗng và không chỉ chứa khoảng trắng.

Định nghĩa response:

```java
public record OrderResponse(
        String orderId,
        BigDecimal total,
        String status) {
}
```

Khi kiểm thử hai runtime, dùng cùng DTO, converter, validation provider và cấu hình Jackson. Nếu ứng dụng sử dụng custom ObjectMapper hoặc module riêng, cần bảo đảm cấu hình đó được áp dụng cho cả hai.

## 5. Thiết kế bộ dữ liệu kiểm thử dùng chung

Tập fixture nên được lưu trong repository, ví dụ:

```text
src/test/resources/contract/orders/
├── valid-order.json
├── invalid-blank-customer.json
├── invalid-zero-quantity.json
├── invalid-null-delivery.json
├── invalid-negative-price.json
├── unknown-field.json
└── malformed-json.json
```

Mỗi file là input độc lập, được cả JVM test và native test sử dụng. Không tạo hai bản fixture gần giống nhau cho từng runtime vì chúng có thể lệch theo thời gian.

Ví dụ `valid-order.json`:

```json
{
  "customerId": "C-1001",
  "quantity": 2,
  "unitPrice": 125000.00,
  "delivery": {
    "city": "Da Nang",
    "express": true
  }
}
```

Ví dụ `invalid-zero-quantity.json`:

```json
{
  "customerId": "C-1001",
  "quantity": 0,
  "unitPrice": 125000,
  "delivery": {
    "city": "Da Nang",
    "express": false
  }
}
```

Bên cạnh fixture, lưu expected outcome: HTTP status, JSON response hoặc error category. Có thể dùng JSON snapshot hoặc test assertions; tránh phụ thuộc vào stack trace hay message nội bộ không thuộc public contract.

## 6. Kiểm thử JSON binding trong JVM test

Với Spring MVC, `MockMvc` kiểm tra request mapping, JSON conversion và validation trong ApplicationContext test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "C-1001",
                      "quantity": 2,
                      "unitPrice": 125000,
                      "delivery": {
                        "city": "Da Nang",
                        "express": true
                      }
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value("ORD-1001"))
            .andExpect(jsonPath("$.total").value(250000))
            .andExpect(jsonPath("$.status").value("ACCEPTED"));
    }
}
```

Ví dụ cần các static imports của MockMvc request/result matchers và Spring test APIs. Nếu dùng Java version chưa hỗ trợ text blocks, thay bằng string literal phù hợp.

MockMvc chạy pipeline MVC trong test context nhưng không mở HTTP server thật. Nó rất hữu ích để kiểm tra binding/validation; để xác minh executable được đóng gói và chạy đúng, cần thêm black-box HTTP test với process JVM/native thực tế.

## 7. Kiểm thử validation và error contract

Không chỉ kiểm tra request hợp lệ. Cần test từng nhóm lỗi:

| Fixture | Điều cần kiểm tra |
|---|---|
| Customer ID rỗng | `@NotBlank` được áp dụng |
| Quantity bằng 0 | `@Min(1)` được áp dụng |
| Quantity vượt 100 | `@Max(100)` được áp dụng |
| Delivery null | `@NotNull` được áp dụng |
| City chỉ có khoảng trắng | Nested validation qua `@Valid` hoạt động |
| JSON sai cú pháp | HTTP 400 theo error contract |
| Kiểu dữ liệu sai | Deserialization thất bại theo contract |
| Field không xác định | Kết quả theo cấu hình unknown-property |

Ví dụ kiểm tra status:

```java
@Test
void rejectsZeroQuantity() throws Exception {
    mvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "C-1001",
                  "quantity": 0,
                  "unitPrice": 1000,
                  "delivery": {
                    "city": "Da Nang",
                    "express": false
                  }
                }
                """))
        .andExpect(status().isBadRequest());
}
```

Định dạng body lỗi có thể khác theo Spring Boot version, Problem Details configuration và exception handler. Nếu body là public API, chuẩn hóa bằng `@ControllerAdvice` hoặc Problem Details rồi assert schema/field quan trọng. Tránh so sánh nguyên văn message validation nếu message phụ thuộc locale hoặc provider.

## 8. Kiểm tra cấu hình bằng cùng property sources

JSON binding có thể đúng nhưng ứng dụng vẫn xử lý khác do cấu hình khác nhau. Ví dụ:

```yaml
orders:
  max-items: 100
  default-currency: VND
  client:
    timeout: 2s
```

Properties class:

```java
@ConfigurationProperties(prefix = "orders")
@Validated
public record OrdersProperties(
        @Min(1) int maxItems,
        @NotBlank String defaultCurrency,
        @Valid Client client) {

    public record Client(
            @NotNull Duration timeout) {
    }
}
```

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Cả JVM và native cần cùng giá trị cấu hình. Có thể đặt fixture config dùng chung trong test resources hoặc truyền environment variables giống nhau khi chạy process.

Phân biệt structural properties với runtime values. Nếu `orders.max-items` chỉ được service đọc khi xử lý request, có thể đổi lúc chạy. Nếu property được dùng trong `@ConditionalOnProperty` để quyết định bean, giá trị AOT dùng khi build có thể đã xác định cấu trúc context. Không thể chỉ đổi environment container rồi kỳ vọng bean bị loại lúc build xuất hiện.

## 9. Test cấu hình runtime bằng environment và file

Có thể chạy process với cùng tập environment:

```bash
ORDERS_MAX_ITEMS=100 \
ORDERS_DEFAULT_CURRENCY=VND \
ORDERS_CLIENT_TIMEOUT=2s \
java -jar target/orders-service.jar
```

Và native:

```bash
ORDERS_MAX_ITEMS=100 \
ORDERS_DEFAULT_CURRENCY=VND \
ORDERS_CLIENT_TIMEOUT=2s \
./orders-service
```

Hai lệnh phải chạy trong môi trường có cùng property source và dependency ngoài. Nếu dùng file cấu hình, mount cùng nội dung tại cùng path hoặc cung cấp qua `SPRING_CONFIG_ADDITIONAL_LOCATION` cho cả hai process.

Để tránh sai lệch do shell, dùng một script khởi chạy chung hoặc file environment được kiểm soát. Không ghi credentials thật vào test fixture. Dùng secret test giả và giữ nguyên quy trình cung cấp secret ở cả hai runtime.

## 10. Kiểm tra serialization và deserialization đặc biệt

Các trường hợp JSON nâng cao dễ bộc lộ khác biệt native:

- Record và constructor-based DTO.
- Immutable object có creator tùy chỉnh.
- Polymorphic type qua `@JsonTypeInfo`.
- Enum và custom enum deserializer.
- `LocalDate`, `Instant`, `OffsetDateTime` và timezone.
- BigDecimal, precision/scale và giá trị số rất lớn.
- Optional, collection lồng nhau và generic wrapper.
- Custom serializer/deserializer, mix-in và naming strategy.
- Field private được mapper truy cập qua reflection.

Ví dụ polymorphic DTO:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPayment.class,
                name = "card"),
        @JsonSubTypes.Type(
                value = BankTransfer.class,
                name = "bank")
})
public sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}
```

Trong native image, các subtype và member cần thiết phải được framework/metadata nhận diện. Spring AOT và Jackson integration có thể xử lý nhiều trường hợp phổ biến, nhưng custom polymorphic type hoặc reflection tùy biến cần được kiểm thử cụ thể. Không tự thêm hints rộng trước khi xác định chính xác đường đi thiếu.

## 11. So sánh JSON theo cấu trúc, không theo chuỗi tùy tiện

JSON object không quy định ý nghĩa dựa trên thứ tự key. Vì vậy, response:

```json
{"orderId":"ORD-1001","status":"ACCEPTED","total":250000}
```

và:

```json
{"total":250000,"orderId":"ORD-1001","status":"ACCEPTED"}
```

có cùng cấu trúc dữ liệu. So sánh chuỗi nguyên văn có thể tạo false failure do thứ tự field, khoảng trắng hoặc format số.

Nên dùng:

- JSONPath assertions cho field quan trọng.
- Parse JSON thành tree và so sánh cấu trúc.
- JSON schema validation nếu contract được mô tả bằng schema.
- So sánh numeric values theo semantics cần thiết, chú ý `250000` và `250000.00` có thể được biểu diễn khác nhau.
- Chuẩn hóa timestamp/ID bằng clock hoặc generator có thể kiểm soát trong test.

Nếu thứ tự array có ý nghĩa, giữ nguyên thứ tự và so sánh chính xác. Nếu array là tập không thứ tự theo contract, normalize trước khi so sánh.

## 12. Chạy cùng fixture trên JVM và native bằng HTTP contract test

MockMvc không thay thế kiểm thử process thật. Một cách tiếp cận là tạo test runner gửi cùng fixture đến một base URL. Ví dụ shell:

```bash
curl -sS -i \
  -H "Content-Type: application/json" \
  --data-binary @src/test/resources/contract/orders/valid-order.json \
  http://localhost:8080/api/orders
```

Chạy JVM process trước, gửi fixture, lưu response; dừng process rồi chạy native executable với cùng cấu hình và gửi lại fixture. Dùng script test chung để tránh copy/paste request khác nhau.

Trong CI có thể:

1. Build executable JAR và khởi chạy process JVM.
2. Chờ readiness endpoint hoặc endpoint test trả lời.
3. Chạy toàn bộ HTTP contract fixtures.
4. Dừng JVM process.
5. Build và khởi chạy native executable.
6. Chờ readiness bằng cùng chính sách timeout.
7. Chạy lại đúng fixtures và so sánh status/JSON contract.
8. Dừng process và lưu logs/artifacts khi có lỗi.

Nếu sử dụng Actuator readiness endpoint, phải thêm dependency và expose endpoint tương ứng. Nếu không, dùng endpoint health/test riêng. Không dùng một khoảng sleep cố định làm bằng chứng process đã sẵn sàng.

## 13. Test native trong Maven/Gradle và giới hạn của từng lớp test

Tùy plugin/version, dự án có thể hỗ trợ native test task hoặc native integration test workflow. Ví dụ task có thể là `nativeTest` trong cấu hình GraalVM Native Build Tools Gradle, nhưng cần xác minh task tồn tại trong project.

Các lớp kiểm thử bổ sung cho nhau:

| Lớp test | Điều xác minh | Giới hạn |
|---|---|---|
| Unit test DTO/mapper | Logic mapping, conversion riêng | Không khởi tạo toàn Spring context |
| Spring Boot integration test trên JVM | Binding, MVC, validation, bean wiring | Chạy trên JVM |
| RuntimeHints test | Registrar khai báo metadata mong muốn | Không chứng minh binary cuối chạy được |
| Native test task | Test chạy trong native mode theo plugin hỗ trợ | Phạm vi phụ thuộc task/configuration |
| Black-box HTTP test trên executable | Process native, HTTP stack và contract | Cần môi trường chạy binary |
| Container integration test | Runtime image, config mount, user, libraries | Chậm hơn và cần image build |

Không thay thế black-box test bằng việc build thành công. Một executable có thể biên dịch được nhưng lỗi khi deserialize một subtype hiếm gặp hoặc khi đọc resource/configuration trong runtime container.

## 14. Đảm bảo cùng dữ liệu thực sự được sử dụng

Một lỗi phổ biến là JVM test dùng fixture từ `src/test/resources`, còn native test vô tình dùng payload hard-code khác. Để tránh:

- Lưu fixture ở một vị trí chuẩn trong repository.
- Đọc fixture bằng cùng helper hoặc script.
- Không tạo payload riêng trong nhánh `if (native)`.
- Ghi checksum fixture trong báo cáo nếu cần truy vết.
- Ghi rõ file config, profile và environment variables.
- Dùng deterministic clock/ID/seed khi response có giá trị sinh động.
- Reset database/test state giữa hai lần chạy.

Nếu ứng dụng có side effect như tạo đơn hàng, gửi message hoặc gọi dịch vụ ngoài, dùng test double hoặc sandbox có dữ liệu reset được. Đảm bảo thứ tự test không làm kết quả của lần chạy sau phụ thuộc lần chạy trước.

## 15. Ma trận kiểm thử đề xuất

| Nhóm | Dữ liệu | Kỳ vọng |
|---|---|---|
| JSON hợp lệ | Request đầy đủ | HTTP 2xx, response schema đúng |
| Field optional | Bỏ field tùy chọn | Default theo contract |
| Field bắt buộc | Bỏ customerId | HTTP 400 |
| Null nested object | delivery = null | HTTP 400 |
| Nested validation | city rỗng | HTTP 400 |
| Numeric boundary | quantity = 1 và 100 | Được chấp nhận |
| Numeric out of range | quantity = 0 và 101 | HTTP 400 |
| JSON syntax | Dấu phẩy/quote sai | HTTP 400 |
| Type mismatch | quantity là string không chuyển được | HTTP 400 |
| Unknown field | Thêm field không khai báo | Theo cấu hình Jackson |
| Polymorphic JSON | Mỗi subtype hợp lệ | Deserialize đúng subtype |
| Date/time | Timestamp có offset | Cùng semantics/timezone |
| Configuration | Timeout, currency, max-items | Cùng giá trị được bind |
| External config | Cùng file mount | Cùng behavior |
| Validation messages | Cùng locale | Cùng error contract đã chuẩn hóa |

Chạy ma trận trên cả JVM và native. Với các trường hợp cần nhiều profile structural khác nhau, xác định artifact native tương ứng cho từng profile trước khi chạy.

## 16. Phân tích sai khác giữa JVM và native

Khi một test chỉ fail trên native, điều tra theo thứ tự:

1. **So sánh request thực tế:** xác nhận body, header, content type và property giống nhau.
2. **So sánh cấu hình:** active profile, property source, locale, timezone, file mount và environment.
3. **Xác định tầng thất bại:** JSON parse, object construction, validation, service logic hay response serialization.
4. **Đọc exception gốc:** phân biệt Jackson mapping error, validation error, missing reflection metadata, resource missing và lỗi cấu hình.
5. **Kiểm tra AOT/native metadata:** subtype, constructor, method, field hoặc resource có được nhận diện không.
6. **Tái hiện tối thiểu:** giữ một fixture và một đường đi làm lỗi, sau đó thêm metadata/điều chỉnh cấu hình.
7. **Chạy lại cùng toàn bộ fixtures:** bảo đảm sửa một trường hợp không làm hỏng trường hợp khác.

Không kết luận mọi lỗi JSON native đều do reflection. Có thể do property khác, locale, dependency version, serializer custom, date/time format hoặc dữ liệu test không tương đương.

## 17. Báo cáo kết quả và đo hiệu năng sau khi contract pass

Khi chức năng đã tương đương, có thể đo startup/readiness và bộ nhớ. Không trộn lỗi chức năng với chỉ số hiệu năng.

Bảng báo cáo mẫu:

| Chỉ số | JVM | Native |
|---|---|---|
| Commit và dependency versions | Ghi | Cùng revision |
| Test fixtures pass/total | Ghi | Ghi |
| JSON response contract | PASS/FAIL | PASS/FAIL |
| Validation outcomes | PASS/FAIL | PASS/FAIL |
| Configuration values | Ghi | Ghi |
| Startup tới readiness | Đo nhiều lần | Đo nhiều lần |
| RSS khi idle | Đo | Đo |
| RSS khi tải | Đo | Đo |
| Throughput/latency | Đo nếu cần | Đo nếu cần |

Đo trên cùng CPU/RAM limit, dataset, concurrency, request rate và cách đo. Với JVM, ghi heap flags và thời gian warm-up; native không có cùng JIT warm-up behavior. Báo cáo số lần chạy, trung vị/phân phối và thời điểm đo để người khác có thể tái lập.

Một native image dùng ít RAM hơn vì bỏ sót subtype hoặc không tải một resource cần thiết là kết quả sai chức năng, không phải tối ưu hợp lệ.

## 18. Bài thực hành: một bộ contract cho cả hai runtime

**Bối cảnh:** dịch vụ Order API nhận JSON, validate nested Delivery, bind cấu hình giới hạn đơn hàng và trả JSON response.

**Bước 1 — Chuẩn hóa DTO.** Tạo request/response records và nested validation annotations.

**Bước 2 — Chuẩn hóa cấu hình.** Tạo `OrdersProperties` với `@ConfigurationProperties`, constructor binding và validation; đăng ký trong ApplicationContext.

**Bước 3 — Tạo fixtures.** Lưu JSON hợp lệ, invalid, malformed, unknown field và boundary cases trong một thư mục test chung.

**Bước 4 — Viết JVM integration tests.** Dùng MockMvc để xác nhận JSON binding, validation và response contract.

**Bước 5 — Chạy process JVM.** Gửi cùng fixture qua HTTP tới executable JAR; lưu status và JSON response.

**Bước 6 — Build native.** Chạy Spring AOT và Native Image; chạy registrar/hints tests nếu ứng dụng có custom JSON/reflection behavior.

**Bước 7 — Chạy process native.** Gửi chính xác cùng fixture và runtime properties; so sánh status, JSON tree và error contract.

**Bước 8 — Chạy trong container.** Mount cùng external config, thiết lập locale/timezone và user tương đương; lặp lại contract test.

**Bước 9 — Ghi kết quả.** Ghi revision, toolchain, fixture checksum, test pass/fail, startup/readiness và RSS.

Tiêu chí hoàn thành: cùng bộ fixture được chạy trên cả hai runtime; JSON binding, validation, nested data và configuration có kết quả tương đương theo contract; mọi sai khác đều có nguyên nhân được xác định; native executable được kiểm tra trong runtime container đích.

## 19. Kết luận

Kiểm thử Spring Boot Native Image cần dùng **cùng dữ liệu, cùng contract và cấu hình tương đương** trên JVM và native. Bộ test phải bao phủ JSON serialization/deserialization, nested DTO, constructor binding, validation, cấu hình runtime, external files và những trường hợp dữ liệu biên. MockMvc và unit tests hữu ích để kiểm tra logic; black-box HTTP tests trên executable và container xác minh hành vi triển khai thực tế.

Khi phát hiện sai khác, xác định tầng lỗi trước khi thêm RuntimeHints hoặc thay cấu hình. Chỉ sau khi hai bản đáp ứng cùng contract mới nên so sánh startup, RSS và throughput. Cách làm này giúp đánh giá Native Image dựa trên hành vi tương đương, thay vì chỉ dựa vào việc build thành công hoặc một vài request smoke test.
