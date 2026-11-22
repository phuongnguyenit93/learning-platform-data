# Round-trip serialization và giới hạn của việc chỉ kiểm tra hai chiều trong Spring Boot

## 1. Vấn đề: object trở về như cũ chưa chắc JSON đúng hợp đồng

Trong Spring Boot, một REST API thường phải chuyển **đối tượng Java thành JSON** để gửi cho client (`serialization`) và **JSON thành đối tượng Java** khi nhận dữ liệu (`deserialization`). Một bài kiểm thử rất tự nhiên là:

```text
       serialize                  deserialize
Java DTO ----------> JSON ----------------------> Java DTO'
   |                                                 |
   +------------------ assert DTO' == DTO -----------+
```

Nếu kết quả sau khi đọc lại bằng đối tượng ban đầu thì gọi là **round-trip test**. Nó có giá trị: phát hiện một số trường bị mất, kiểu dữ liệu bị đổi, custom serializer/deserializer không đối xứng, lỗi với dữ liệu Unicode hoặc cách bind field vào constructor.

Tuy nhiên, bài test này có **giới hạn lớn**: cả hai hướng thường sử dụng **cùng một cấu hình mapper, cùng annotation và cùng một giả định về schema**. Vì thế, hai phía có thể **cùng sai một cách nhất quán**. Ví dụ Java DTO có thuộc tính `paymentId`; đối tác yêu cầu JSON key `payment_id`, nhưng serializer xuất `paymant_id` và deserializer lại đọc `paymant_id`. Kết quả round-trip vẫn bằng nhau dù client bên ngoài không đọc được.

Đây là lý do không nên viết duy nhất:

```java
assertEquals(original, mapper.readValue(
        mapper.writeValueAsString(original), PaymentResponse.class));
```

rồi kết luận JSON API đã đúng. Cần kiểm tra **ít nhất ba quan hệ khác nhau**:

1. **Java → JSON chuẩn đã định nghĩa từ bên ngoài**: tên field, kiểu JSON, field bắt buộc, null/absence, format ngày/tiền, nested structure và dữ liệu nhạy cảm không bị lộ.
2. **JSON mẫu từ client/đối tác → Java**: parse đúng input, tương thích với các trường hợp có/không có field và phản ứng với dữ liệu lỗi theo hợp đồng.
3. **Java → JSON → Java**: giữ các thuộc tính cần giữ theo hợp đồng và bảo toàn ngữ nghĩa sau hai chiều.

Ba phép thử **bổ sung cho nhau, không thay thế cho nhau**.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Câu hỏi kiểm tra | Ví dụ |
|---|---|---|
| Serialization | DTO được phát ra dưới hình dạng JSON nào? | `paymentId` thành `"payment_id"` |
| Deserialization | JSON hợp lệ có được hiểu thành DTO đúng không? | `"amount": 19.90` thành `BigDecimal("19.90")` |
| Round-trip object | Đọc lại JSON do chính mapper viết có bảo toàn object không? | `read(write(x)) == x` |
| Round-trip JSON | Viết lại JSON nhận được có giữ nội dung JSON không? | `write(read(j))` so với `j` |
| Wire contract | Đối tác/client độc lập nhìn thấy gì trên đường truyền? | key `"payment_id"`, status, content type |
| Equality | Quy tắc nào xác định hai object tương đương? | `record.equals`, `BigDecimal.equals`, domain comparison |
| Canonicalization | Có chuẩn hóa định dạng sau khi đọc/viết lại không? | bỏ whitespace, thứ tự key, format số/ngày |
| Validation | Dữ liệu có đáp ứng quy tắc nghiệp vụ không? | amount phải dương, ID không rỗng |

Một đối tượng bằng nhau sau round-trip **không chứng minh** validation đã chạy, JSON tương thích với client cũ, việc truyền HTTP có content type đúng hoặc Jackson đang dùng cấu hình production.

### 2.1. Diễn đạt bằng hàm

Gọi `S` là hàm serialize từ DTO `D` sang JSON `J`; `P` là hàm deserialize từ JSON về DTO.

- Round-trip hướng object kiểm tra `P(S(d)) ≈ d`.
- Round-trip hướng JSON kiểm tra `S(P(j)) ≈ j`.
- Hợp đồng độc lập kiểm tra `S(d) ≈ j_expected` và `P(j_external) ≈ d_expected`.

Ký hiệu `≈` phải được định nghĩa: với DTO, có thể là equality theo giá trị nghiệp vụ; với JSON, có thể là **equality cấu trúc** (không quan tâm thứ tự field) chứ không phải equality nguyên chuỗi. Nếu tài liệu giao tiếp buộc giữ dạng số, timezone hoặc thứ tự phần tử trong array, assertion phải thể hiện đúng yêu cầu đó.

**Không được suy ra từ `P(S(d)) = d` rằng `S` và `P` đều đúng đối với mọi client độc lập**: một phép ghép hai hàm có thể đúng với những dữ liệu được chọn, trong khi từng hàm vi phạm contract bên ngoài.

## 3. Khi nào round-trip thật sự có ích?

Round-trip giúp phát hiện:

- Một trường có giá trị khác `null` bị `@JsonIgnore` hoặc custom serializer bỏ đi và không được khôi phục.
- Enum/record/nested DTO không đọc lại được vì thiếu constructor/creator hoặc cấu hình type mapping.
- Custom date/time serializer làm mất timezone offset hoặc precision nếu equality trong DTO nhận ra điều đó.
- Collection mất thứ tự hoặc phần tử trùng khi bị đổi kiểu.
- Chuỗi Unicode hoặc ký tự escape được decode sai.
- Polymorphic DTO bị mất subtype nếu hình dạng dữ liệu bắt buộc phải giữ subtype.
- Cấu hình Jackson module thay đổi làm hai hướng không còn tương thích, ví dụ thời gian hay sealed type.

Nhưng mức độ bảo vệ còn phụ thuộc **dữ liệu được chọn**. Nếu chỉ test một DTO có mọi trường là `null`, logic bỏ field có thể vẫn làm bài test pass. Nếu chỉ test amount nguyên, lỗi làm tròn với `19.90` có thể không xuất hiện. Nếu test list rỗng, lỗi về thứ tự/duplicates không bị phát hiện.

Do đó nên có bộ fixture đại diện: giá trị điển hình, biên, `null`, rỗng, Unicode, nested, số chính xác, ngày giờ/offset khi liên quan, dữ liệu trong collection với phần tử trùng, và nhánh exception.

## 4. Vì sao kiểm tra hai chiều có thể tạo false confidence?

### 4.1. Sai cùng một tên field ở cả hai chiều

Đối tác yêu cầu:

```json
{"payment_id":"p-42","amount":19.90}
```

Nhưng DTO bị gắn annotation sai chính tả:

```java
record BrokenPayment(
        @JsonProperty("paymant_id") String paymentId,
        BigDecimal amount) {}
```

Đoạn trên là mã minh họa trong tệp có import Jackson và `BigDecimal`. Mapper có thể xuất `"paymant_id"` rồi đọc đúng `"paymant_id"` về `paymentId`. **Object round-trip pass; contract với client fail**. Một assertion độc lập như `assertThat(tree.has("payment_id")).isTrue()` sẽ phát hiện vấn đề.

Đây là **lỗi đối xứng (symmetric defect)**: cùng mapping sai được dùng trong cả `S` và `P`, nên phép thử hai chiều không nhìn thấy.

### 4.2. Bỏ qua cả trường đã bị mất

Giả sử dữ liệu `internalNote` không được serialize do `@JsonIgnore`. Nếu test tạo object có `internalNote == null`, kết quả đọc lại thường vẫn `null`, vì thế pass. Nếu nghiệp vụ cần trường đó trong wire contract, test đã bỏ sót. Ngược lại, có những trường nội bộ **phải cố tình bị loại khỏi JSON** (mật khẩu, token nội bộ); khi đó round-trip đầy đủ toàn bộ object không phải expectation đúng — cần tách DTO công khai khỏi entity nội bộ.

### 4.3. Cấu hình mapper sai nhưng tự tương thích

Hai hướng cùng bật naming strategy `SNAKE_CASE` sai đối với API đang công bố `camelCase`; round-trip object vẫn có thể thành công. Tương tự custom serializer và deserializer cho enum có thể cùng sử dụng tên sai. Assertion cần đối chiếu **golden JSON từ đặc tả API** thay vì chỉ dựa trên JSON do mapper hiện tại tự sinh.

### 4.4. JSON hợp lệ không nhất thiết là JSON được client chấp nhận

Một object có thể serialize thành JSON hợp lệ về cú pháp nhưng sai semantic contract:
- Field bắt buộc bị bỏ (`"name"` không có).
- Field `"balance"` từ JSON number bị viết thành JSON string `"100.00"`.
- ID dạng chuỗi UUID bị đổi sang đối tượng nested.
- Enum từ `"PAID"` bị đổi thành `"paid"`.
- Response có thêm `"secret"` dù client không yêu cầu; nguy hiểm hơn là lộ dữ liệu.
- Timestamp được chuẩn hóa sang offset/timezone mà downstream không chấp nhận.

Round-trip không nhất thiết bắt những sai lệch này nếu cả hai hướng cùng chấp nhận hoặc âm thầm chuyển đổi.

## 5. Chọn đúng môi trường test và mapper

Đối với Spring Boot 3.5 và Jackson 2, có thể dùng `@JsonTest` để kiểm tra JSON mapping mà không nạp toàn bộ web server/database. `@JsonTest` hỗ trợ cấu hình Jackson hiện diện trong phạm vi JSON slice và các helper như `JacksonTester<T>`. Đây là công cụ phù hợp cho unit/integration hẹp của serialization.

Ba mức kiểm tra khác nhau:

| Mức kiểm thử | Công cụ | Điều có thể chứng minh |
|---|---|---|
| Pure Jackson test | `new ObjectMapper()` + JUnit | Hành vi của **mapper vừa tự tạo** với modules/features đã khai báo |
| Boot JSON slice | `@JsonTest`, inject `JacksonTester<T>`/`ObjectMapper` | DTO với mapper và JSON-related auto-config thực sự được slice nạp |
| Web integration | `@WebMvcTest` + `MockMvc`, `@WebFluxTest` + `WebTestClient`, hoặc `@SpringBootTest` | HTTP codecs, content type, controller advice, headers/status trên đường web đã kiểm tra |

**Chú ý:** `new ObjectMapper()` có thể không có `JavaTimeModule`, naming strategy, custom serializers, inclusion rules hoặc modules mà Spring Boot production sử dụng. Nếu mục tiêu là hợp đồng JSON HTTP của ứng dụng, nên dùng **mapper của Spring context phù hợp**, hoặc test qua web pipeline thật. Nếu ứng dụng tùy chỉnh `ObjectMapper` trong một `@Configuration` ngoài slice, `@JsonTest` không mặc nhiên nạp mọi cấu hình đó; phải import/configure rõ và xác minh JSON thực tế.

Trong các phần code chạy được bên dưới, ta dùng **Spring Boot 3.5.x / Jackson 2 / Java 17+**, vì import `com.fasterxml.jackson.databind.ObjectMapper`, `org.springframework.boot.test.autoconfigure.json.JsonTest` và `JacksonTester` được đặt theo dòng đó. **Không lấy nguyên import của ví dụ này cho Spring Boot 4 / Jackson 3**; phần migration riêng ở mục 13.

## 6. Ví dụ Java 17+ với @JsonTest: round-trip và hợp đồng độc lập

### 6.1. Hợp đồng thanh toán công khai

Ứng dụng công bố JSON payment:

```json
{
  "payment_id": "pay-7",
  "amount": 19.90,
  "note": "quà tặng"
}
```

Quy định tối thiểu:
- JSON key **`payment_id`**, không phải `paymentId` hoặc `paymant_id`.
- `amount` là JSON number, không phải string; trong Java dùng `BigDecimal`.
- `note` là tùy chọn; trong **ví dụ này**, khi `null` thì **bỏ field** chứ không phát `"note":null`.
- Khi nhận dữ liệu từ một JSON fixture độc lập, mapper phải tạo đúng `PaymentResponse`.
- Không có field nội bộ hoặc thông tin nhạy cảm được phép tự động xuất hiện trong JSON.

Ta cố tình tách **giá trị object** khỏi **đặc tả JSON**, để một thay đổi mapping sai có thể bị phát hiện ở test độc lập.

### 6.2. Tổ chức source và dependencies

Giả định dự án đã sử dụng Spring Boot **3.5.x**, JDK 17+ và Gradle/Maven có dependency management theo Boot. Ví dụ fragment `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-json'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây **không phải toàn bộ build.gradle**: phải có Spring Boot plugin, Java plugin/toolchain và repository Maven Central từ build của dự án. Nếu dự án đã dùng `spring-boot-starter-web`, Jackson JSON thường được cung cấp theo starter web nên không cần thêm starter-json chỉ cho ví dụ.

Cấu trúc:

```text
src/main/java/com/example/jsoncontract/
    JsonContractApplication.java
    PaymentResponse.java

src/test/java/com/example/jsoncontract/
    PaymentResponseJsonTest.java
```

Tệp `src/main/java/com/example/jsoncontract/JsonContractApplication.java`:

```java
package com.example.jsoncontract;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {
}
```

Lớp `@SpringBootApplication` giúp Boot test bootstrap tìm cấu hình ứng dụng; bài `@JsonTest` vẫn nạp **JSON slice**, không khởi động HTTP listener, datasource hay toàn bộ application context.

### 6.3. DTO dùng Jackson annotations

Tệp `src/main/java/com/example/jsoncontract/PaymentResponse.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PaymentResponse(
        @JsonProperty("payment_id") String paymentId,
        @JsonProperty("amount") BigDecimal amount,
        String note) {
}
```

Những chú ý về DTO:
- `@JsonProperty("payment_id")` khai báo wire key độc lập với tên component Java `paymentId`.
- `@JsonInclude(NON_NULL)` bỏ những thuộc tính `null` **khi serialize**; nó không tự xác nhận một field đầu vào có mặt hay không.
- `BigDecimal` phù hợp với số thập phân cần giữ độ chính xác hơn `double`, nhưng **`BigDecimal.equals` nhạy với scale**: `19.90` và `19.9` cùng giá trị số nhưng `equals` có thể là `false`.
- `record` tự tạo `equals`, `hashCode`, accessor và constructor, thuận tiện so sánh DTO sau round-trip.
- Đây là response DTO minh họa, không nên dùng một JPA entity có lazy associations làm public JSON payload trực tiếp chỉ để test round-trip.

### 6.4. Bài test đầy đủ: hai chiều + fixture độc lập + case xấu

Tệp `src/test/java/com/example/jsoncontract/PaymentResponseJsonTest.java`:

```java
package com.example.jsoncontract;

import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import com.fasterxml.jackson.databind.JsonNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@JsonTest
class PaymentResponseJsonTest {

    @Autowired
    JacksonTester<PaymentResponse> json;

    @Autowired
    ObjectMapper mapper;

    private static PaymentResponse sample() {
        return new PaymentResponse(
                "pay-7",
                new BigDecimal("19.90"),
                "quà tặng");
    }

    @Test
    void objectRoundTripPreservesValues() throws IOException {
        PaymentResponse original = sample();

        String outgoing = json.write(original).getJson();
        PaymentResponse decoded = json.parseObject(outgoing);

        assertThat(decoded).isEqualTo(original);
    }

    @Test
    void outgoingJsonMatchesExternalContract() throws IOException {
        PaymentResponse original = sample();

        assertThat(json.write(original))
                .isStrictlyEqualToJson("""
                        {
                          "payment_id": "pay-7",
                          "amount": 19.90,
                          "note": "quà tặng"
                        }
                        """);

        JsonNode tree = mapper.readTree(json.write(original).getJson());
        assertThat(tree.get("payment_id").asText())
                .isEqualTo("pay-7");
        assertThat(tree.get("amount").isNumber()).isTrue();
        assertThat(tree.has("paymentId")).isFalse();
        assertThat(tree.has("paymant_id")).isFalse();
        assertThat(tree.size()).isEqualTo(3);
    }

    @Test
    void externalFixtureDeserializesCorrectly() throws IOException {
        String fromClient = """
                {
                  "payment_id": "client-8",
                  "amount": 12.50,
                  "note": "Nội dung"
                }
                """;

        PaymentResponse decoded = json.parseObject(fromClient);

        assertThat(decoded).isEqualTo(
                new PaymentResponse(
                        "client-8",
                        new BigDecimal("12.50"),
                        "Nội dung"));
    }

    @Test
    void nullNoteIsAbsentByPublicContract() throws IOException {
        PaymentResponse value = new PaymentResponse(
                "pay-9",
                new BigDecimal("0.01"),
                null);

        JsonNode tree = mapper.readTree(json.write(value).getJson());

        assertThat(tree.has("payment_id")).isTrue();
        assertThat(tree.has("amount")).isTrue();
        assertThat(tree.has("note")).isFalse();
    }

    @Test
    void malformedAmountDoesNotSilentlyBecomeValid() {
        String invalid = """
                {
                  "payment_id": "pay-10",
                  "amount": "not-a-number",
                  "note": "gift"
                }
                """;

        assertThrows(IOException.class, () -> json.parseObject(invalid));
    }

    @Test
    void unknownFieldCanBeRejectedWhenPolicyIsStrict() {
        ObjectMapper strictMapper = mapper.copy()
                .configure(
                        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                        true);

        String fromClient = """
                {
                  "payment_id": "pay-11",
                  "amount": 4.00,
                  "debug_role": "admin"
                }
                """;

        assertThrows(
                UnrecognizedPropertyException.class,
                () -> strictMapper.readValue(
                        fromClient, PaymentResponse.class));
    }

    // Bản mapping CỐ Ý SAI: external contract cần "payment_id".
    private record BrokenPayment(
            @JsonProperty("paymant_id") String paymentId,
            BigDecimal amount) {
    }

    @Test
    void roundTripCanPassDespiteWrongExternalFieldName()
            throws IOException {

        BrokenPayment input = new BrokenPayment(
                "pay-12", new BigDecimal("10.00"));

        String outgoing = mapper.writeValueAsString(input);
        BrokenPayment decoded =
                mapper.readValue(outgoing, BrokenPayment.class);

        // Dù sai tên trường wire, hai hướng vẫn tự khớp.
        assertThat(decoded).isEqualTo(input);

        JsonNode tree = mapper.readTree(outgoing);
        assertThat(tree.has("paymant_id")).isTrue();
        assertThat(tree.has("payment_id")).isFalse();
    }
}
```

**Ghi chú quan trọng:** Test `roundTripCanPassDespiteWrongExternalFieldName` **cố ý đưa ra một ví dụ DTO sai hợp đồng**, nhưng assertions vẫn đúng: nó chứng minh round-trip có thể pass trong khi key wire mong đợi không xuất hiện. Không đưa `BrokenPayment` vào production làm DTO thật.

Trong test `outgoingJsonMatchesExternalContract`, `isStrictlyEqualToJson` kiểm tra cấu trúc JSON với các field cần thiết, không phải so sánh chuỗi byte theo thứ tự key/whitespace. Ta bổ sung `JsonNode` để assert **kiểu JSON number**, số field và absence của những tên bị sai. Nếu wire protocol yêu cầu **lexical representation** chính xác (chẳng hạn dạng timestamp, chữ hoa enum, chính sách biểu diễn tiền), cần assertion chuỗi/format cụ thể nữa.

Bài test `unknownFieldCanBeRejectedWhenPolicyIsStrict` làm rõ một **chính sách do test thiết lập**. Không suy ra Boot mặc định luôn từ chối unknown JSON properties; điều đó phụ thuộc cấu hình ObjectMapper/Jackson. Nếu sản phẩm cần strict mode, phải bật chính sách đó trên **mapper thật của HTTP endpoint**, không chỉ trên bản `mapper.copy()` của test.

### 6.5. Đọc đúng kết luận từ từng test

| Test method | Bằng chứng | Không đủ để kết luận |
|---|---|---|
| `objectRoundTripPreservesValues` | DTO có thể được mapper này viết rồi đọc lại, giữ `equals` | JSON đúng schema công khai |
| `outgoingJsonMatchesExternalContract` | Key, JSON types và field set của response mẫu đúng | Tất cả biến thể dữ liệu/HTTP pipeline đúng |
| `externalFixtureDeserializesCorrectly` | JSON độc lập được hiểu thành DTO mong đợi | Input không hợp lệ luôn bị chặn ở tất cả tầng |
| `nullNoteIsAbsentByPublicContract` | `null` được omit khi serialize | Server biết phân biệt missing/null khi deserialize |
| `malformedAmountDoesNotSilentlyBecomeValid` | Giá trị amount không chuyển được thành số gây lỗi parse | Mọi số âm hoặc số quá lớn sẽ bị từ chối theo domain |
| `unknownFieldCanBeRejectedWhenPolicyIsStrict` | Mapper **cấu hình strict trong test** từ chối field lạ | Production mapper đang bật policy tương tự |
| `roundTripCanPassDespiteWrongExternalFieldName` | Ví dụ mapping sai có thể vẫn đạt round-trip | Tên key mà client mong đợi thực sự có mặt |

Cả bảy ca trên được **thiết kế để có assertion cụ thể**; bài Knowledge không giả vờ chúng đã chạy trên dự án của bạn. Nếu phụ thuộc hoặc cấu hình Boot/Jackson khác, phải chạy test và kiểm tra report để xác nhận. Kết quả mong đợi về nguyên tắc là các assertions đạt trên **dòng phiên bản và cấu hình đã nêu**.

## 7. Chạy các ví dụ và xem báo cáo thật

Dùng Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.jsoncontract.PaymentResponseJsonTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jsoncontract.PaymentResponseJsonTest"
```

Với Maven wrapper trên Linux/macOS:

```bash
./mvnw -Dtest=PaymentResponseJsonTest test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=PaymentResponseJsonTest test
```

Điều kiện: dự án có wrapper, Java 17+, Spring Boot 3.5.x, Jackson 2/JacksonTester và JUnit Jupiter. Gradle thường cần `useJUnitPlatform()`. Nếu source set của bạn có Boot 4/Jackson 3 thay vì Boot 3.5, phải chuyển imports/configuration tương ứng, không cưỡng ép đồng thời hai major version của Spring.

Xem Gradle report `build/reports/tests/test/index.html` (ở module có task `test`) hoặc Maven Surefire `target/surefire-reports/`. Đảm bảo test class được **discover và execute**, không chỉ báo build `UP-TO-DATE` hoặc test bị skip. Đoạn test không có `System.out.println`; không tồn tại một stdout cố định của nghiệp vụ để ghi lại.

## 8. Round-trip JSON → Java → JSON còn có nhiều bẫy hơn

Đôi khi team viết test **nhận JSON rồi serialize lại** và so sánh hai chuỗi:

```java
String outgoing =
        mapper.writeValueAsString(
                mapper.readValue(incoming, PaymentResponse.class));
assertEquals(incoming, outgoing);
```

Đoạn trên là **minh họa** với mapper và biến `incoming` có sẵn. So sánh raw string kiểu này dễ tạo **false negative** vì JSON object thường không quy định thứ tự key, whitespace hay cách escape tương đương. Ví dụ:

```json
{"a":1,"b":2}
```

và:

```json
{
  "b": 2,
  "a": 1
}
```

có cùng nội dung cấu trúc JSON object, dù chuỗi khác hoàn toàn. Nếu hợp đồng không yêu cầu thứ tự key, hãy parse cả hai thành `JsonNode` rồi so sánh **tree** hoặc dùng JSON assertions cấu trúc với mức strict/lenient được chọn có chủ đích.

Tuy nhiên, ngay cả **tree equality** cũng không tự chứng minh round-trip bảo toàn mọi ngữ nghĩa:
- `1`, `1.0` và `1.00` có thể biểu diễn cùng giá trị toán học nhưng mang lexical precision khác nhau; `JsonNode.equals` có cách so sánh kiểu node riêng.
- `"2026-03-01T10:00:00Z"` và `"2026-03-01T17:00:00+07:00"` biểu diễn cùng instant nhưng **khác chuỗi/offset**.
- `null` và **missing field** khác nhau về JSON structure dù DTO mapping có thể gom về cùng một `null`.
- Array có **thứ tự** và **số phần tử**, không được phép bỏ qua duplicate chỉ vì order không quan trọng với một business set.
- Object có **duplicate keys** như `{"id":1,"id":2}` không nên được chấp nhận hay chuẩn hóa một cách vô thức; nhiều parser có thể lấy giá trị cuối, và stricter duplicate-detection là một chính sách riêng.

**Quy tắc so sánh phù hợp phải xuất phát từ hợp đồng**, không phải từ việc thư viện hỗ trợ `assertEquals` nào tiện nhất.

## 9. Các góc dữ liệu cần kiểm tra độc lập

### 9.1. Missing field và explicit null

Ba JSON sau không đồng nhất:

```json
{}
```

```json
{"note":null}
```

```json
{"note":""}
```

Jackson có thể ánh xạ cả missing và explicit `null` thành Java `null` cho một record component reference type, trong khi empty string thành `""`. Nếu contract dùng JSON Merge Patch hoặc semantics “không gửi field = giữ nguyên” khác “gửi null = xóa dữ liệu”, **DTO đơn giản không đủ lưu thông tin presence**. Cần kiểu biểu diễn presence, JsonNode hoặc request schema phù hợp.

Một round-trip bắt đầu với `note == null` không phân biệt được `{}` với `{"note":null}` nếu DTO và inclusion rule làm mất thông tin; kiểm tra wire contract trực tiếp.

### 9.2. Số nguyên, số thập phân và làm tròn

Với tiền:
- Sử dụng `BigDecimal` hoặc đại lượng nguyên ở đơn vị nhỏ nhất theo domain contract khi phù hợp.
- Đừng mặc định `double` bảo toàn mọi giá trị thập phân chính xác.
- `BigDecimal("19.90").equals(BigDecimal("19.9"))` thường `false` vì scale khác, còn `compareTo(...) == 0` xét giá trị toán học. Xác định contract cần giữ **scale** hay chỉ cần cùng giá trị.
- Nếu API quy định JSON number, một JSON string `"19.90"` có thể bị Jackson **coerce** thành BigDecimal nếu cấu hình cho phép; round-trip object có thể vẫn pass dù input vi phạm kiểu JSON.
- Dữ liệu rất lớn vượt miền `long`/ `int` có thể gây overflow hoặc parse error; test boundary và cách trả 400.
- Chuỗi `NaN`, `Infinity` hoặc numeric precision ngoài phạm vi JSON chuẩn cần policy riêng; không cho qua bằng mapper permissive mà không hiểu client.

### 9.3. Thời gian, timezone và precision

Các loại `Instant`, `OffsetDateTime`, `ZonedDateTime`, `LocalDateTime` mang ngữ nghĩa khác nhau:
- `Instant`: một thời điểm tuyệt đối, thường được biểu diễn với `Z`/UTC hoặc timestamp theo cấu hình.
- `OffsetDateTime`: có offset, nhưng serializer/deserializer có thể normalize hoặc bỏ offset nếu setting khác.
- `ZonedDateTime`: zone ID có ý nghĩa hơn offset ở nhiều quy tắc giờ mùa.
- `LocalDateTime`: **không có timezone/offset**, không thể tự suy ra instant toàn cầu.

Ví dụ `2026-03-01T10:00:00Z` và `2026-03-01T17:00:00+07:00` biểu diễn cùng instant; test `Instant.equals` có thể pass sau khi chuyển đổi, trong khi client cần **giữ chuỗi với offset gốc**. Nếu contract yêu cầu ISO-8601 và độ chính xác nano/milli, phải kiểm tra JSON string chính xác hoặc quy tắc normalize được công bố.

Với Jackson 2, support `java.time` thường cần `JavaTimeModule` hoặc module được Boot tự cấu hình theo dependency. Một `new ObjectMapper()` thuần khác Boot mapper có thể fail hoặc xuất timestamp khác. Không thay đổi `WRITE_DATES_AS_TIMESTAMPS` hay timezone chỉ để làm test pass nếu HTTP contract production không cho phép.

### 9.4. Enum và thay đổi phiên bản

Nếu hệ thống phát:

```json
{"status":"AUTHORIZED"}
```

mà client cũ chỉ hiểu `"APPROVED"`, round-trip với enum Java mới vẫn có thể pass vì serialization và deserialization đều biết giá trị mới. Cần test hợp đồng consumer hoặc fixture của **version cũ**, quy tắc fallback cho enum unknown, `@JsonCreator`/`@JsonValue` khi được phép và migration strategy.

Tương tự, đổi `"user_id"` thành `"userId"` có thể làm round-trip xanh nhưng phá backward compatibility. Golden files và contract tests có khả năng phát hiện thay đổi wire schema nhanh hơn.

### 9.5. Collection, Map và kiểu generic

Nếu DTO chứa `List<T>`, test phải bảo vệ order và số phần tử khi contract yêu cầu. Nếu chứa `Set<T>`, duplicate từ JSON có thể bị loại — round-trip object trên một set **không thể chứng minh duplicate trong JSON gốc được bảo toàn**.

Khi deserialize trực tiếp `List<PaymentResponse>` bằng Jackson, không dùng `List.class` rồi ép cast như thể generic type được giữ:

```java
List<PaymentResponse> values = mapper.readValue(
        inputJson,
        new TypeReference<List<PaymentResponse>>() {});
```

Đây là đoạn minh họa, cần `import com.fasterxml.jackson.core.type.TypeReference`, `List`, và mapper Boot 3/Jackson 2 cùng `inputJson` được khai báo. Nếu chỉ đọc `List.class`, các phần tử có thể thành `LinkedHashMap` thay vì `PaymentResponse`; một test không truy cập phần tử có thể không phát hiện.

Map với key không phải String hoặc polymorphic values cần thêm custom mapping; JSON object keys về bản chất là chuỗi. Không kỳ vọng cấu trúc `Map<SomeComplexKey, Value>` tự round-trip đúng mọi trường hợp nếu chưa thiết kế serializer/deserializer.

### 9.6. Polymorphism và subtype

Một DTO có kiểu base/interface có thể serialize ra JSON đủ để nhìn bằng mắt nhưng không deserialize về subtype đúng vì thiếu type discriminator. Hoặc bật default typing quá rộng có thể mở bề mặt rủi ro với input không tin cậy.

Đừng bật Jackson default typing một cách tùy tiện chỉ để round-trip có thể deserialize mọi subtype. Hãy dùng **schema/discriminator công khai có giới hạn subtype**, cơ chế polymorphic mapping an toàn và test JSON từ đối tác thực. Nếu một API không cam kết dynamic polymorphism, có thể chọn DTO cụ thể thay vì cho phép arbitrary Java class names xuất hiện trong JSON.

## 10. Security và privacy: round-trip không bảo vệ khỏi rò field

Một entity có thể chứa `passwordHash`, `apiKey`, `internalRiskScore`, `tenantId` hoặc dữ liệu nhạy cảm. Một round-trip kiểm tra object equality có thể **rất vui vẻ xác nhận** các field này được serialize rồi deserialize thành công, trong khi chính việc đưa chúng ra JSON là lỗi bảo mật.

**Giải pháp thực hành:**
- Dùng **response DTO tách biệt** khỏi JPA entity hoặc model chứa nội bộ.
- Kiểm tra **allowlist field công khai** bằng JSON structural assertions, không chỉ blacklist một field bí mật.
- Nếu dữ liệu phụ thuộc quyền, test các user/tenant khác nhau qua HTTP/security chain, không chỉ test ObjectMapper đơn lẻ.
- Kiểm tra các custom serializers/`@JsonView` thật sự được áp dụng trong endpoint, không chỉ ở object mapper khác.
- Đảm bảo log test thất bại không đổ secret ra output khi dùng snapshot JSON.

Ví dụ: `assertThat(tree.size()).isEqualTo(3)` cùng kiểm tra từng key của response mẫu ở mục 6 bảo vệ basic allowlist; trong production nên có test riêng khi response object phức tạp, hoặc OpenAPI/schema contract test có cơ chế kiểm tra field được phép.

## 11. Validation không đồng nghĩa deserialization

JSON syntactically valid, được Jackson đọc thành object, **chưa chắc hợp lệ về nghiệp vụ**. Với một request DTO:

```java
public record NewPaymentRequest(
        @NotBlank String paymentId,
        @Positive BigDecimal amount) {}
```

Đây là đoạn minh họa, cần `jakarta.validation.constraints.NotBlank`, `Positive`, dependency validator và môi trường test. Annotation constraint là metadata của Bean Validation; **gọi `ObjectMapper.readValue` trực tiếp không tự đảm bảo Bean Validation được chạy**.

Trong Spring MVC, controller thường dùng `@Valid @RequestBody` cùng validation provider thích hợp; trong WebFlux, cơ chế argument validation tương ứng hoạt động khi được cấu hình. Nếu thiếu `@Valid`, một object với amount âm có thể deserialize thành công rồi đi qua controller.

Để bảo vệ request contract, cần ít nhất:
1. Test JSON parse/binding field đúng.
2. Test validation constraints bằng `Validator` hoặc web test thích hợp.
3. Test HTTP 400 + error schema khi request không hợp lệ.
4. Test service không bị gọi nếu input đã bị chặn ở web layer (khi đó là hợp đồng).

Round-trip của `NewPaymentRequest(-1)` có thể thành công dù amount âm là dữ liệu cấm. **Không coi round-trip là validation test**.

## 12. Test JSON trực tiếp và test HTTP response nên kết hợp thế nào?

### 12.1. @JsonTest: nhanh, tập trung vào mapper

Ưu tiên khi thay đổi:
- DTO record/POJO, `@JsonProperty`, `@JsonInclude`, `@JsonFormat`.
- Jackson modules, naming strategy, custom serializer/deserializer.
- Cấu trúc JSON nested, enum, dates, exact fields.
- Fixture của client từ hợp đồng đã được thống nhất.

Thực hiện cả 3 nhánh **outgoing**, **incoming**, **round-trip**, không chỉ một nhánh để lấy code coverage.

### 12.2. @WebMvcTest / @WebFluxTest: kiểm tra HTTP contract

Một JSON mapper có thể đúng nhưng endpoint lại:
- Không có mapping URI/HTTP method.
- Trả nhầm status 200 thay vì 201/404.
- Bỏ `Content-Type: application/json` hoặc ghi body với converter khác.
- Dùng DTO khác với DTO được @JsonTest.
- Bị `@ControllerAdvice`/filter/security thay đổi JSON hoặc HTTP status.
- Trả output theo Jackson view/property filter của endpoint khác với mapper test.

`@WebMvcTest` + `MockMvc` kiểm tra mapping MVC, Jackson response, content type, advice trong slice. `@WebFluxTest` + `WebTestClient` kiểm tra analogous WebFlux pipeline trong slice. Nếu muốn request qua HTTP socket thật và tích hợp nhiều tầng, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` với HTTP test client được cấu hình phù hợp.

**Không dùng một test Web slice đã mock service để chứng minh repository, transaction hoặc SQL production.** Một HTTP JSON contract test có thể rất tốt mà vẫn là test của controller với stubbed data.

### 12.3. Snapshot/golden JSON: giữ độc lập với serializer đang kiểm tra

Golden JSON nên đến từ **API contract hoặc fixture đối tác đã được duyệt**, không được tạo lại tự động bằng chính `ObjectMapper.writeValueAsString` mỗi lần chạy test. Nếu snapshot được tự cập nhật sau mỗi thay đổi code, test có thể chỉ “duyệt lại” bug.

Nên review mỗi thay đổi schema có thể phá client:
- Field thêm/bớt/đổi tên, mandatory/optional.
- Enum values, union discriminators.
- Null/absence semantics.
- Format date, timezone và precision.
- Kiểu số hoặc string và quy tắc làm tròn.
- Nested object/array order và duplicates.
- Error response JSON, versioning và backward compatibility.
- Có xuất hiện field sensitive/internal không.

Bản snapshot chuẩn cấu trúc nên dùng parser/JSON assertion strict thay vì raw text nếu key order không phải hợp đồng; raw snapshot thích hợp khi cần bytes/lexical format chính xác.

## 13. Lưu ý phiên bản: Spring Boot 3.5/Jackson 2 và Boot 4/Jackson 3

**Phần mã chạy được của bài này nhắm Boot 3.5/Jackson 2.** Khi nâng lên Spring Boot 4.x, không nên giả định toàn bộ imports và default features của mapper giữ nguyên.

Những điểm migration chính:
- Spring Boot 4 ưu tiên **Jackson 3**; nhiều class di chuyển từ `com.fasterxml.jackson.databind` sang namespace `tools.jackson`. **Ngoại lệ quan trọng:** các Jackson annotations như `@JsonProperty` vẫn thuộc package `com.fasterxml.jackson.annotation`.
- Boot 4 cung cấp `JsonMapper` của Jackson 3 và cơ chế auto-config mới; không thể coi `new ObjectMapper()` kiểu Jackson 2 là tương đương mapper của Boot 4.
- `@JsonTest` vẫn tồn tại nhưng có thể auto-configure JSON mapper theo các thư viện/phiên bản trên classpath. Test nên inject và sử dụng **mapper mà ứng dụng thực sự dùng**.
- `@JsonComponent` của Boot/Jackson 2 có chuyển đổi tương ứng sang `@JacksonComponent` cho Jackson 3; cần xem migration guide và custom module registration.
- Boot 4 thay đổi mặc định module detection và một số JSON property settings; một fixture external JSON có thể phát hiện thay đổi schema mà object round-trip bỏ sót.
- Không ép dependency `jackson-databind` 2.x và 3.x lẫn lộn rồi kỳ vọng mapping giống nhau; chọn chiến lược migration được BOM/Boot hỗ trợ.

Để kiểm tra compatibility sau nâng version, **giữ nguyên external fixtures/golden JSON từ Boot 3.5** và chạy chúng bằng mapper của Boot 4, bên cạnh round-trip nội bộ. Đây là cách phát hiện thay đổi tên field, null inclusion, date format, coercion hoặc module registration mà hai hàm serialize/deserialize mới có thể cùng chấp nhận.

Không có một mệnh đề “Jackson 3 luôn serialize khác Jackson 2” đúng với mọi DTO; khác biệt phụ thuộc class, annotations, defaults và modules. Cần **assert JSON thực tế** trong project đang dùng.

## 14. Những lỗi kiểm thử phổ biến và cách sửa

| Anti-pattern | Vì sao không đáng tin | Cách kiểm chứng tốt hơn |
|---|---|---|
| Chỉ `assertEquals(dto, read(write(dto)))` | Hai hướng cùng sai schema vẫn pass | Thêm external JSON fixture và exact field contract |
| Golden JSON được sinh tự động từ mapper mỗi lần test | Test không còn oracle độc lập | Lưu fixture được review và cố định |
| DTO mẫu có tất cả field rỗng/null | Không phát hiện field bị omit/lost | Thêm non-null, nested, boundary và Unicode |
| Assert object equality nhưng `equals` bỏ field quan trọng | Equality có thể quá yếu | Assert field cụ thể và wire structure |
| Chỉ so raw JSON string | Whitespace/key order tạo false negative | JSON structural assertion khi ordering không thuộc contract |
| Luôn dùng JSON assertion lenient | Có thể bỏ qua field extra, loại/kiểu sai | Strict structural assertion, type và field-count checks |
| `BigDecimal.equals` bị coi như numeric compare | Scale khác khiến test fail dù số cùng giá trị | Chọn `equals` hoặc `compareTo` đúng domain |
| Test amount bằng `double` rồi kết luận chính xác tiền | Floating-point có rounding error | Dùng BigDecimal hoặc integer minor units |
| Bỏ qua missing vs `null` | API PATCH/optional fields có thể sai semantic | Test cả missing/null/empty string |
| ObjectMapper tự tạo khác mapper Boot | Modules/naming/date/format config lệch | Inject mapper của JSON slice/HTTP path |
| Serialize trực tiếp JPA entity | Có thể lazy load/recursive graph/secret leak | Tách response DTO, test allowlist fields |
| Dùng `List.class` để parse generic list | Phần tử có thể thành map | Dùng `TypeReference<List<T>>` |
| Deserialize xong coi dữ liệu đã validate | Jackson không tự chạy Bean Validation | Test @Valid/Validator và HTTP 400 |
| Giấu unknown JSON fields vô điều kiện | Có thể che lỗi client hoặc phá version policy | Chọn FAIL/IGNORE đúng contract và test rõ |
| Bật default typing cho mọi subtype | Không an toàn cho input không tin cậy | Giới hạn polymorphic types bằng schema/discriminator |
| Chỉ test `@JsonTest` rồi kết luận HTTP API đúng | Bỏ qua status, headers, filters, selected DTO | Bổ sung MockMvc/WebTestClient/HTTP integration |
| Cùng JSON fixture cho cả expected lẫn actual được tạo từ code | Không có oracle độc lập | Dùng fixture ngoài do client/schema quyết định |
| Migrate Boot/Jackson nhưng chỉ chạy round-trip | Mapper mới có thể tự tương thích với schema mới sai | Chạy golden JSON và request samples xuyên phiên bản |

## 15. Checklist để round-trip có giá trị thực sự

- [ ] Đã định nghĩa **wire contract độc lập** (OpenAPI/JSON Schema/fixture đối tác): field names, types, presence, null, format.
- [ ] Đã kiểm tra DTO → JSON expected bằng **strict structural assertions** và các kiểu JSON quan trọng.
- [ ] Đã kiểm tra JSON external → DTO expected, không tái sử dụng JSON do serializer tạo ra.
- [ ] Round-trip object có fixture đại diện: non-null, rỗng, `null`, Unicode, nested, boundary, precision.
- [ ] Đã định nghĩa **equality**: record.equals, BigDecimal scale, date offset/instant, order/duplicates.
- [ ] Đã kiểm tra unknown fields, missing required fields, type coercion, malformed JSON theo chính sách cụ thể.
- [ ] Đã kiểm tra enum, timezone/date format, generic collections và polymorphic DTO nếu contract sử dụng.
- [ ] Không serialize field internal/secret; có allowlist hoặc schema assertion phù hợp.
- [ ] Nếu dùng Boot, test sử dụng mapper/configuration phản ánh ứng dụng thật; không dựa riêng vào `new ObjectMapper()` mặc định.
- [ ] Nếu cần validation, đã kiểm tra `@Valid`/Validator và HTTP 400 riêng.
- [ ] Nếu cần bảo vệ HTTP contract, có web test kiểm tra status, content type, headers, body/error schema.
- [ ] Khi nâng Spring Boot/Jackson, dùng external fixtures xuyên phiên bản để phát hiện behavioral drift.
- [ ] Đã chạy đúng test task, xác minh số test thực thi và xem test reports trước khi kết luận PASS.

## 16. Tài liệu chính thức để tiếp tục

- [Spring Boot 3.5 – Auto-configured JSON Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JsonTest`, `JacksonTester`, so sánh JSON theo helper.
- [Spring Boot 4 – JSON Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): phạm vi test JSON và các mapper được hỗ trợ.
- [Spring Boot 4.0 Migration Guide – Upgrading Jackson](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): namespace Jackson 3, module và default changes.
- [Spring Boot 3.5 – JacksonTester API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/JacksonTester.html): `write`, `parse`, `parseObject`.
- [Jackson 2 Annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations): `@JsonProperty`, `@JsonIgnore`, `@JsonInclude`, `@JsonCreator` và liên quan.

**Kết luận:** Round-trip serialization là một phép thử có ích nhưng **không đủ để chứng minh hợp đồng JSON**. Hai hướng sử dụng cùng mapper có thể cùng mắc lỗi và tự khôi phục object ban đầu; dữ liệu `null`, naming, số, ngày giờ, unknown fields, security hoặc validation có thể bị bỏ sót. Một bộ test đáng tin cậy phải kết hợp **round-trip theo ngữ nghĩa**, **golden JSON độc lập cho serialization**, **input JSON độc lập cho deserialization**, và **HTTP contract tests** khi JSON xuất hiện trên API thực.