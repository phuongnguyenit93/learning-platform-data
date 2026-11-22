# Đảm bảo test chạy ổn định giữa các môi trường

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao documentation test có thể chạy tốt trên máy cá nhân nhưng thất bại hoặc sinh snippet khác trong CI.
- Thiết kế fixture và dữ liệu kiểm thử có kết quả xác định.
- Kiểm soát clock, timezone, locale, random ID, thứ tự collection và dữ liệu database.
- Cô lập dependency ngoài như HTTP service, message broker, filesystem và cloud storage.
- Giữ cấu hình MockMvc, WebTestClient và REST Assured nhất quán giữa local và CI.
- Tránh test phụ thuộc thứ tự chạy, trạng thái dùng chung hoặc chạy song song không an toàn.
- Chuẩn hóa snippet ở mức cần thiết để diff phản ánh thay đổi API contract thay vì nhiễu môi trường.
- Thu thập log và chẩn đoán lỗi flaky test có hệ thống.

## 1. Vì sao documentation test cần ổn định?

Spring REST Docs tạo tài liệu từ HTTP exchange thực sự được test. Khi test chạy, request, response và descriptor được ghi thành snippet; Asciidoctor sau đó include các file này vào tài liệu.

Điều đó có nghĩa là mọi biến động không có chủ đích trong test đều có thể xuất hiện trong tài liệu:

- Timestamp thay đổi theo thời điểm chạy.
- ID sinh ngẫu nhiên làm response body khác nhau.
- Dữ liệu database còn sót từ lần chạy trước.
- Thứ tự phần tử trong collection không được quy định.
- Host, port hoặc context path khác giữa máy cá nhân và CI.
- Locale hoặc timezone của agent CI khác môi trường developer.
- Dependency ngoài chập chờn hoặc trả dữ liệu thay đổi.
- Test chạy song song và ghi đè cùng snippet output.

Một test có thể pass nhưng snippet thay đổi liên tục. Khi đó pull request xuất hiện diff không liên quan đến API contract, reviewer khó nhận ra thay đổi thật và build có thể thất bại ngẫu nhiên.

Mục tiêu không phải làm mọi response giống nhau bằng cách che hết dữ liệu. Mục tiêu là kiểm soát các yếu tố không thuộc contract, đồng thời giữ nguyên những giá trị mà consumer cần hiểu.

## 2. Nguyên tắc thiết kế test xác định

Một documentation test ổn định thường có các đặc điểm:

1. Input được khai báo rõ và không phụ thuộc dữ liệu còn lại từ môi trường.
2. Clock, timezone và locale được kiểm soát khi ảnh hưởng kết quả.
3. Database được reset hoặc dùng transaction/test container có vòng đời rõ.
4. ID và thứ tự dữ liệu có thể dự đoán.
5. Dependency ngoài được thay bằng fake/mock hoặc môi trường test ổn định.
6. Cấu hình server, port, context path và serialization nhất quán.
7. Mỗi test có document identifier riêng, không ghi đè snippet của test khác.
8. Chạy lặp lại nhiều lần vẫn tạo kết quả tương đương.

Ví dụ fixture:

```java
Order order = new Order(
    42L,
    "ORD-2026-0001",
    OrderStatus.PENDING,
    Instant.parse("2026-01-15T08:30:00Z")
);
```

Fixture này có ID, mã đơn hàng, trạng thái và timestamp cố định. Test không phụ thuộc dữ liệu được tạo ngẫu nhiên hoặc thời gian hiện tại.

## 3. Kiểm soát thời gian, timezone và locale

Thời gian là nguồn gây khác biệt phổ biến. Một response có createdAt lấy từ Instant.now() sẽ thay đổi mỗi lần chạy:

```java
order.setCreatedAt(Instant.now());
```

Nếu timestamp là một phần response được tài liệu hóa, snippet có thể khác giữa các lần build. Nên inject Clock để test cố định thời điểm.

### 3.1. Inject Clock

Trong ứng dụng:

```java
@Configuration
class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Service dùng clock:

```java
class OrderService {

    private final Clock clock;

    OrderService(Clock clock) {
        this.clock = clock;
    }

    Instant currentTime() {
        return Instant.now(clock);
    }
}
```

Trong test, cung cấp clock cố định:

```java
@TestConfiguration
class FixedClockConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T08:30:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Nếu ứng dụng có nhiều Clock bean, đặt qualifier rõ ràng để tránh inject nhầm. Không thay clock toàn cục bằng static mutable state vì test chạy song song có thể ảnh hưởng lẫn nhau.

### 3.2. Chuẩn hóa timezone

Ưu tiên lưu và xử lý thời gian bằng Instant hoặc OffsetDateTime khi API contract cần biểu diễn offset. Nếu response dùng local date/time, phải xác định timezone rõ ràng.

Trong test có thể đặt JVM timezone:

```bash
./gradlew test -Duser.timezone=UTC
```

Hoặc cấu hình test task:

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'user.timezone', 'UTC'
}
```

Đây là một lớp bảo vệ. Cách tốt hơn vẫn là dùng kiểu thời gian có semantics rõ và inject Clock vào code cần thời điểm hiện tại.

### 3.3. Locale và định dạng số/ngày

Không dựa vào Locale.getDefault() nếu output API cần định dạng cố định. Một agent CI có thể dùng locale khác, làm số thập phân, tên tháng hoặc thông báo validation thay đổi.

Ví dụ format có locale rõ ràng:

```java
DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.US);
```

Nếu API trả JSON date theo ISO-8601, hãy cấu hình serializer nhất quán và test giá trị thực tế. Không nên biến locale hiển thị của máy thành một phần ngầm định của contract.

## 4. Dữ liệu fixture và ID xác định

Tránh sinh ID ngẫu nhiên trong response được ghi vào snippet nếu ID không phải nội dung cần minh họa:

```java
UUID.randomUUID()
```

Thay bằng fixture có chủ đích:

```java
UUID.fromString("123e4567-e89b-12d3-a456-426614174000")
```

Hoặc inject ID generator:

```java
interface IdGenerator {
    UUID nextId();
}
```

Trong test:

```java
given(idGenerator.nextId())
    .willReturn(UUID.fromString(
        "123e4567-e89b-12d3-a456-426614174000"
    ));
```

Nếu ID được sinh bởi database sequence, có thể seed/reset sequence trong test setup hoặc dùng repository test fixture để kiểm soát giá trị. Không phụ thuộc sequence tiếp tục từ lần test trước.

### 4.1. Dữ liệu giả nhưng có ý nghĩa

Dữ liệu tài liệu nên:

- Dễ đọc và diễn giải.
- Không chứa dữ liệu cá nhân hoặc production.
- Có giá trị ổn định giữa các lần chạy.
- Thể hiện các trường hợp tiêu biểu của API.
- Không phụ thuộc thứ tự tạo fixture ngẫu nhiên.

Ví dụ:

```json
{
  "id": 42,
  "orderNumber": "ORD-2026-0001",
  "status": "PENDING",
  "createdAt": "2026-01-15T08:30:00Z"
}
```

Không nên dùng fixture toàn giá trị "foo", "bar", 1, 2 nếu điều đó làm consumer khó hiểu ý nghĩa domain. Nhưng cũng không cần dùng dữ liệu production để tạo ví dụ thực tế.

## 5. Kiểm soát thứ tự collection

Một số collection không cam kết thứ tự. Nếu response trả danh sách từ HashMap, HashSet hoặc query database không có ORDER BY, thứ tự có thể khác giữa các lần chạy hoặc giữa database engine.

Ví dụ query thiếu sort:

```sql
SELECT id, order_number, status
FROM orders;
```

Nếu API contract yêu cầu thứ tự, thêm ORDER BY rõ ràng:

```sql
SELECT id, order_number, status
FROM orders
ORDER BY created_at DESC, id ASC;
```

Nếu thứ tự không thuộc contract, documentation test nên kiểm tra tập phần tử thay vì dựa vào vị trí cố định. Tuy nhiên, snippet vẫn có thể phản ánh một thứ tự ngẫu nhiên. Có thể dùng fixture collection có thứ tự xác định trong documentation test để output ổn định.

Trong Java:

```java
List<Order> orders = List.of(
    orderFixture(42L, "ORD-001"),
    orderFixture(43L, "ORD-002")
);
```

Không dựa vào iteration order của HashMap/HashSet để tạo response mẫu. Nếu JSON object field order không phải contract, đừng viết assertion phụ thuộc thứ tự key; nếu snippet cần ổn định để review, cấu hình serializer/fixture phù hợp nhưng không biến thứ tự key thành cam kết API nếu contract không quy định.

## 6. Database isolation và dữ liệu còn sót

Documentation test có thể dùng database thật hoặc test database. Nếu dữ liệu không được cô lập, test có thể:

- Thất bại khi chạy lần hai do duplicate key.
- Trả thêm record được test khác tạo ra.
- Phụ thuộc thứ tự test.
- Sinh snippet khác theo trạng thái database.
- Chạy tốt local nhưng thất bại trên CI database sạch.

Các cách xử lý:

### 6.1. Transaction rollback

Với test phù hợp, có thể dùng transaction và rollback sau test:

```java
@Transactional
@Test
void documentsOrder() throws Exception {
    // Arrange, perform request, assert and document.
}
```

Rollback chỉ có tác dụng nếu request và thao tác database tham gia cùng transaction test. Với server chạy ở thread khác hoặc transaction boundary khác, transaction của test có thể không bao phủ request. Hãy kiểm tra cách MockMvc/WebTestClient được cấu hình.

### 6.2. Dọn dữ liệu trước mỗi test

Có thể dùng repository cleanup hoặc SQL script để đưa database về trạng thái đã biết:

```java
@BeforeEach
void resetData() {
    orderRepository.deleteAll();
    customerRepository.deleteAll();
    seedDocumentationFixtures();
}
```

Thứ tự cleanup phải tôn trọng foreign key. Với dữ liệu lớn, chỉ xóa record thuộc namespace/test fixture thay vì xóa toàn bộ bảng dùng chung.

### 6.3. Testcontainers

Testcontainers cung cấp dependency service có vòng đời được kiểm soát, ví dụ PostgreSQL hoặc Redis. Cần pin image version và cấu hình khởi tạo schema/data nhất quán.

Không dùng tag image trôi nổi như latest trong CI nếu thay đổi version có thể làm test khác kết quả. Khóa image version/digest theo chính sách dự án.

## 7. Cô lập dependency ngoài

Documentation test nên kiểm tra contract HTTP của ứng dụng. Không nên để một dịch vụ thanh toán, email hoặc API bên thứ ba quyết định test có pass hay snippet chứa dữ liệu nào.

Các dependency thường cần thay thế:

| Dependency | Cách cô lập |
| --- | --- |
| Payment gateway | Stub HTTP server hoặc mock adapter |
| Email provider | Fake mail sender, kiểm tra message đã tạo |
| Object storage | Local emulator hoặc fake storage client |
| Message broker | Test container hoặc embedded broker có version cố định |
| External catalog API | Stub response fixture |
| Clock | Fixed Clock |
| Random ID | Deterministic generator |

Nếu mục tiêu của test là xác minh tích hợp với dịch vụ ngoài, tạo integration test riêng với môi trường test có kiểm soát. Không để documentation test chính phụ thuộc internet công cộng hoặc sandbox không ổn định.

### 7.1. Stub HTTP service

Ví dụ dùng WireMock theo ý tưởng:

```java
stubFor(get(urlEqualTo("/catalog/items/42"))
    .willReturn(okJson("""
        {"id":42,"name":"Keyboard"}
        """)));
```

Pin WireMock version và fixture response. Reset stub/mapping trước mỗi test để request của test trước không ảnh hưởng test sau.

## 8. Cấu hình MockMvc, WebTestClient và REST Assured

Mỗi test client có cách tạo request và kết nối khác nhau, nhưng nguyên tắc ổn định vẫn giống nhau: dùng cùng cấu hình application, serialization, security và fixture.

### 8.1. MockMvc

MockMvc thường chạy request qua Spring MVC infrastructure mà không cần mở TCP port thật. Điều này giúp test nhanh và ít phụ thuộc môi trường:

```java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
```

Đảm bảo test dùng đúng filter chain, controller advice, message converter và configuration mà API runtime sử dụng. Standalone MockMvc có thể thiếu một phần cấu hình nếu dự án chỉ dựng controller thủ công.

### 8.2. WebTestClient

WebTestClient có thể bind với application context hoặc gọi server chạy thật. Chọn cách phù hợp với mục tiêu:

```java
webTestClient.get()
    .uri("/api/orders/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-get"));
```

Nếu dùng random port, không đưa port runtime vào phần prose hoặc file được so sánh nếu nó không phải nội dung contract. Spring REST Docs thường chuẩn hóa một số phần request, nhưng vẫn cần kiểm tra snippet thực tế.

### 8.3. REST Assured

REST Assured thường phù hợp với integration test gọi ứng dụng qua HTTP:

```java
given()
    .accept(ContentType.JSON)
    .pathParam("id", 42)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/{id}")
    .then()
    .statusCode(200);
```

Đảm bảo base URI, port, context path và filter configuration được thiết lập từ test environment, không hard-code hostname local.

## 9. Chuẩn hóa môi trường local và CI

Một số giá trị cần đồng nhất:

| Yếu tố | Cấu hình nên kiểm soát |
| --- | --- |
| Java | Toolchain/version được pin |
| Gradle/Maven | Wrapper và plugin version được commit |
| Timezone | UTC hoặc timezone được quy định |
| Locale | Locale rõ ràng cho dữ liệu phụ thuộc locale |
| Encoding | UTF-8 cho source, process và output |
| Database | Engine/version/schema/seed xác định |
| Port | Random port chỉ dùng cho transport, không đưa vào contract |
| Context path | Cùng giá trị giữa test và tài liệu |
| Environment variables | Có default test rõ, không phụ thuộc máy developer |
| Dependency image | Pin version hoặc digest |

Ví dụ Gradle:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    systemProperty 'user.timezone', 'UTC'
    systemProperty 'file.encoding', 'UTF-8'
    systemProperty 'user.language', 'en'
    systemProperty 'user.country', 'US'
}
```

Chỉ đặt locale en-US nếu đó là môi trường test có chủ đích. Nếu API cần trả tiếng Việt, hãy test locale vi-VN rõ ràng thay vì phụ thuộc locale mặc định của máy.

## 10. Tránh phụ thuộc thứ tự và chạy song song không an toàn

Test không nên dựa vào việc một test khác đã tạo dữ liệu hoặc khởi tạo static state. Mỗi test phải chuẩn bị fixture của chính nó hoặc dùng một fixture immutable được chia sẻ an toàn.

Các lỗi phổ biến khi chạy song song:

- Hai test cùng ghi vào một document identifier.
- Hai test cùng xóa/seed một database schema.
- Shared mock server bị reset trong lúc test khác đang dùng.
- Mutable singleton/cache dùng chung.
- Test cùng ghi một file output.

Giải pháp:

1. Dùng document identifier duy nhất cho mỗi exchange/kịch bản.
2. Cô lập database/schema hoặc serialize nhóm test cần state dùng chung.
3. Không dùng mutable static fixture.
4. Khởi tạo/reset stub theo lifecycle của test.
5. Chỉ bật parallel execution khi resource và snippet output an toàn.

Ví dụ identifier:

| Kịch bản | Document identifier |
| --- | --- |
| GET order thành công | orders-get |
| GET order không tồn tại | orders-get-not-found |
| POST order thành công | orders-create |
| POST order validation lỗi | orders-create-invalid |

Không dùng cùng identifier cho nhiều test có request/response khác nhau nếu chúng có thể ghi đè hoặc tạo output không xác định.

## 11. Ổn định snippet mà không che mất contract

Spring REST Docs ghi lại request/response đã được preprocess. Có thể dùng preprocessor để chuẩn hóa dữ liệu biến động không thuộc contract:

- Thay request ID ngẫu nhiên bằng placeholder.
- Che token, cookie hoặc thông tin nhạy cảm.
- Chuẩn hóa host/port nếu chúng thay đổi theo môi trường.
- Xóa header không có ý nghĩa với consumer và phụ thuộc hạ tầng.

Ví dụ:

```java
preprocessRequest(
    removeHeaders("X-Internal-Trace")
)
```

Không xóa mọi header hoặc field chỉ để snippet ngắn. Hãy giữ những thông tin mà consumer cần gửi hoặc cần hiểu.

### 11.1. Thay timestamp có kiểm soát

Nếu timestamp là một field trong response contract, nên cố định Clock để giá trị trong test có nghĩa. Có thể thay bằng placeholder khi thời điểm cụ thể không quan trọng với ví dụ, nhưng phải giữ format/type:

```json
{
  "createdAt": "<timestamp>"
}
```

Không dùng placeholder để che một bug timezone hoặc format. Test cần assert giá trị/format thực tế trước khi preprocess snippet.

### 11.2. Chuẩn hóa host và port

Một số test chạy server ở random port. Nếu port xuất hiện trong snippet, có thể preprocess phần URI hoặc dùng cấu hình REST Docs operation/request preprocessing phù hợp. Trước khi thay, kiểm tra host/port có phải nội dung consumer cần biết hay chỉ là chi tiết môi trường test.

Không hard-code một port production giả vào tài liệu. Nếu tài liệu cần base URL, mô tả bằng placeholder rõ ràng như https://api.example.test.

## 12. Kiểm tra tính ổn định bằng cách chạy lặp lại

Một lần chạy xanh chưa đủ chứng minh test ổn định. Nên chạy documentation test nhiều lần từ trạng thái sạch:

```bash
./gradlew clean test
./gradlew clean test
```

So sánh snippet giữa hai lần chạy. Diff cần tập trung vào nội dung contract; timestamp, UUID, port hoặc thứ tự không xác định là tín hiệu cần điều tra.

Có thể dùng Git diff để xem thay đổi:

```bash
git diff -- build/generated-snippets
```

Nếu generated-snippets không được track trong Git, lưu hai output vào thư mục tạm và so sánh bằng diff tool của CI. Không commit output chỉ để che một test không ổn định.

## 13. Chẩn đoán flaky documentation test

Khi test chỉ thất bại đôi lúc, thu thập bằng chứng trước khi tăng retry:

1. Ghi tên test và document identifier thất bại.
2. Lưu request/response thực tế và assertion mismatch.
3. Ghi Java version, timezone, locale và environment variables.
4. Kiểm tra trạng thái database và seed data.
5. Kiểm tra dependency ngoài, timeout và log server.
6. Chạy riêng test thất bại nhiều lần.
7. Chạy toàn bộ suite để phát hiện phụ thuộc thứ tự.
8. So sánh snippet giữa các lần chạy.

Retry có thể giúp pipeline tạm thời xanh nhưng không sửa nguyên nhân. Chỉ dùng retry cho lỗi hạ tầng đã được nhận diện, có giới hạn và có telemetry; không dùng retry để che race condition hoặc fixture thiếu xác định.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Timestamp snippet thay đổi mỗi build | Dùng system clock trực tiếp | Inject Clock và cố định thời điểm test |
| ID response khác nhau | UUID/sequence ngẫu nhiên | Seed sequence hoặc mock ID generator |
| Danh sách response đổi thứ tự | Query không ORDER BY hoặc collection unordered | Quy định sort hoặc fixture có thứ tự |
| Test pass riêng nhưng fail cả suite | Shared state hoặc phụ thuộc thứ tự | Cô lập fixture/database và bỏ static mutable state |
| Local pass, CI fail | Java/locale/timezone/config khác | Pin toolchain và chuẩn hóa environment |
| Test timeout ngẫu nhiên | Dependency ngoài hoặc timeout quá ngắn | Stub dependency, đặt timeout hợp lý và ghi log |
| Snippet bị ghi đè | Nhiều test dùng chung identifier | Dùng identifier duy nhất theo kịch bản |
| Chạy song song sinh output lỗi | Shared DB, stub hoặc file output | Cô lập resource hoặc serialize nhóm test |
| Retry làm CI xanh nhưng lỗi còn | Flaky root cause chưa được sửa | Điều tra và loại bỏ nondeterminism |

## 15. Checklist đảm bảo test ổn định

- [ ] Fixture có giá trị xác định và không dùng dữ liệu production.
- [ ] Clock/timezone/locale được kiểm soát khi ảnh hưởng output.
- [ ] ID generator và database sequence không tạo giá trị bất định.
- [ ] Query có ORDER BY khi thứ tự là một phần contract.
- [ ] Database được reset hoặc cô lập giữa test.
- [ ] Dependency ngoài được stub/fake hoặc chạy trong test environment cố định.
- [ ] Java, build tool, encoding và environment variables được pin.
- [ ] MockMvc/WebTestClient/REST Assured dùng cấu hình phù hợp runtime.
- [ ] Document identifier không trùng giữa các scenario.
- [ ] Parallel execution không chia sẻ mutable state hoặc output.
- [ ] Preprocessor chỉ chuẩn hóa chi tiết môi trường, không che contract.
- [ ] Documentation tests chạy lặp lại tạo snippet ổn định.
- [ ] CI lưu log và output cần thiết để chẩn đoán lỗi.

## 16. Bài tập thực hành

Một endpoint GET /api/orders trả danh sách đơn hàng với các field id, orderNumber, status và createdAt. Test hiện tại đôi lúc tạo snippet khác nhau vì timestamp, ID và thứ tự danh sách.

Hãy thực hiện:

1. Tạo fixture ba đơn hàng có ID, mã và timestamp cố định.
2. Inject Clock và cấu hình fixed clock trong test.
3. Đảm bảo repository query có sort rõ ràng hoặc fixture list có thứ tự.
4. Reset database trước test và xác minh test không phụ thuộc dữ liệu cũ.
5. Stub payment/catalog service nếu endpoint gọi dependency ngoài.
6. Đặt document identifier riêng cho success và error scenario.
7. Chuẩn hóa timezone, locale và encoding trong Gradle test task.
8. Chạy documentation tests hai lần từ clean state và so sánh generated snippets.
9. Bật parallel test có kiểm soát, quan sát xem có race condition hoặc output bị ghi đè.
10. Ghi lại nguyên nhân và cách sửa nếu phát hiện bất kỳ diff không xác định nào.

**Câu hỏi tự kiểm tra:** Nếu response timestamp thay đổi mỗi lần chạy, có nên xóa field createdAt khỏi snippet bằng preprocessor không? Chỉ khi field đó không cần thiết để hiểu contract và đã có test riêng xác minh format/semantics. Thông thường, nên inject Clock cố định để snippet vẫn thể hiện một timestamp hợp lệ, có ý nghĩa và ổn định.

## Kết luận

Documentation test chỉ tạo tài liệu đáng tin cậy khi kết quả có thể lặp lại giữa local và CI. Hãy kiểm soát fixture, clock, timezone, locale, ID, thứ tự collection, database state và dependency ngoài; dùng cùng cấu hình application và serialization với runtime. Tránh shared mutable state, document identifier trùng và chạy song song trên resource dùng chung. Preprocessor chỉ nên chuẩn hóa chi tiết môi trường hoặc che dữ liệu nhạy cảm, không được xóa thông tin thuộc API contract. Chạy lặp lại từ clean state và so sánh snippet để phát hiện nondeterminism sớm. Khi các yếu tố này được kiểm soát, diff tài liệu sẽ phản ánh thay đổi API thực sự và build CI ổn định hơn.
