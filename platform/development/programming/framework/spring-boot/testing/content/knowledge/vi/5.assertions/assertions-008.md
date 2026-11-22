# JSON assertions, JSONPath và so sánh cấu trúc trong kiểm thử Spring Boot

## Mục tiêu

Một endpoint REST có thể trả HTTP 200 nhưng vẫn sai dữ liệu: thiếu trường, sai kiểu số, sai số lượng phần tử, sai thứ tự giao dịch hoặc để lộ thuộc tính không nên công khai. Vì vậy, test API cần **kiểm tra nội dung JSON** theo hợp đồng, bên cạnh HTTP status.

Sau bài này, bạn có thể:

- Phân biệt kiểm tra **một giá trị** bằng JSONPath với kiểm tra **toàn bộ cấu trúc** JSON.
- Viết assertion cho object lồng nhau, array, phần tử theo chỉ số, điều kiện, `null` và field không tồn tại.
- Sử dụng `MockMvc` cùng `jsonPath(...)` và `content().json(...)` ở lớp controller Spring Boot.
- Hiểu so sánh JSON **strict** và **lenient**, khi nào chọn mỗi cách; so sánh cây JSON bằng Jackson `JsonNode`.
- Thiết kế test tránh lệ thuộc thứ tự field, khoảng trắng và thứ tự mảng ngoài ý muốn; phân biệt hợp đồng HTTP với chi tiết nội bộ Java.
- Chạy ví dụ Spring Boot/Java 17 với Gradle và đọc kết quả từ JUnit.

Bài viết tập trung vào **assertion JSON khi kiểm thử API Spring Boot**. JSONPath là cú pháp truy vấn; assertion là phép kiểm mong đợi; so sánh cấu trúc đối chiếu object/array. Ba khái niệm liên quan nhưng giải quyết những câu hỏi khác nhau.

## 1. JSON trả về và những thứ cần xác minh

Giả sử một API `GET /api/orders/42` trả:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "customer": {
    "code": "C01",
    "name": "Lan"
  },
  "items": [
    { "sku": "BOOK", "quantity": 2, "unitPrice": 120 },
    { "sku": "PEN", "quantity": 1, "unitPrice": 10 }
  ],
  "total": 250,
  "paid": true
}
~~~

Để có một test chất lượng, hãy biến hợp đồng thành các phép kiểm có thể phát hiện lỗi:

| Quy tắc/hợp đồng | Cần khẳng định | Lựa chọn |
| --- | --- | --- |
| API trả đơn hàng hợp lệ | HTTP 200 và media type JSON | `status().isOk()`, `contentTypeCompatibleWith` |
| ID và trạng thái chính xác | `id=42`, `status=CONFIRMED` | `jsonPath("$.id")`, `jsonPath("$.status")` |
| Khách hàng đúng | `customer.code=C01` | JSONPath lồng nhau |
| Có đúng hai mặt hàng | `items` có 2 phần tử | JSONPath + Hamcrest `hasSize(2)` |
| Thứ tự mặt hàng là hợp đồng | SKU là `BOOK` rồi `PEN` | JSONPath array + `contains` |
| Response không được thêm field nội bộ | Chỉ có những trường đã công bố | So sánh cấu trúc **strict** |
| Chỉ bắt buộc một phần dữ liệu | Một số field chính xác, cho phép field mới | So sánh **lenient** hoặc JSONPath có chọn lọc |

**HTTP status không chứng minh JSON đúng.** Ngược lại, một assertion JSON có thể fail vì response là HTML lỗi hoặc JSON không hợp lệ, nên trong test controller hãy kiểm status và content type trước để lỗi dễ đọc.

### Ba cách kiểm tra thường dùng

1. **JSONPath:** lấy một giá trị hay tập giá trị bằng đường dẫn, sau đó so với expected. Phù hợp khi hợp đồng quan tâm đến một vài field.
2. **So sánh JSON cấu trúc:** đối chiếu một JSON expected với response như cây object/array, bỏ qua định dạng chữ và thứ tự key của object; strict/lenient quyết định thêm field và thứ tự array có được phép hay không.
3. **Jackson `JsonNode`:** parse expected/actual thành cây dữ liệu rồi dùng assertion của JUnit. Phù hợp khi cần kiểm toàn bộ response, duyệt từng node hay tính toán kiểm tra phức tạp.

Không dùng so sánh chuỗi thô giữa hai văn bản JSON nếu yêu cầu thực sự là **giống nhau về ngữ nghĩa**. Hai chuỗi có khác khoảng trắng hoặc thứ tự field nhưng vẫn là JSON object tương đương.

## 2. JSONPath là gì?

JSONPath biểu diễn một đường đi qua JSON. Ký hiệu phổ biến:

| Biểu thức | Ý nghĩa trên JSON ví dụ |
| --- | --- |
| `$` | Toàn bộ document JSON |
| `$.status` | Chuỗi `"CONFIRMED"` |
| `$.customer.code` | Chuỗi `"C01"` |
| `$['customer']['name']` | Một cách viết khác để lấy `"Lan"` |
| `$.items` | Mảng mặt hàng |
| `$.items[0].sku` | SKU của mặt hàng đầu tiên: `"BOOK"` |
| `$.items[*].sku` | Danh sách SKU: `["BOOK","PEN"]` |
| `$.items[?(@.sku == 'BOOK')].quantity` | Danh sách quantity của mặt hàng khớp điều kiện, ở đây `[2]` |

`$` là gốc. `.` chọn field; `[0]` chọn chỉ số mảng bắt đầu từ 0; `[*]` chọn mọi phần tử; `[?()]` lọc phần tử theo điều kiện. `@` trong biểu thức lọc tham chiếu phần tử đang xét. Chú ý **đường dẫn lọc thường cho ra một danh sách**, kể cả khi chỉ có một phần tử.

**JSONPath không phải một chuẩn ngữ nghĩa duy nhất ở mọi thư viện.** Trong Spring MVC Test, `jsonPath` dùng trình đánh giá JSONPath tương ứng với thư viện có trong Spring Test/Jayway. Một số phép toán và định dạng lỗi khác nhau giữa thư viện; hãy kiểm thử biểu thức theo bộ phiên bản dự án.

### JSONPath trong `MockMvc`

Ví dụ cách viết assertion (đoạn minh họa, cần đối tượng `mockMvc` và controller đã cấu hình):

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("CONFIRMED"))
        .andExpect(jsonPath("$.items[0].sku").value("BOOK"))
        .andExpect(jsonPath("$.items[*].sku")
                .value(contains("BOOK", "PEN")));
~~~

`jsonPath(...).value(...)` lấy giá trị và so sánh. Hamcrest `contains(...)` kiểm **đúng các phần tử theo thứ tự**; nếu mảng không có yêu cầu thứ tự, có thể chọn matcher tương ứng như `containsInAnyOrder(...)` kết hợp kiểm số phần tử phù hợp.

Sử dụng JSONPath cho các giá trị **được công bố ra ngoài**, không kiểm chi tiết triển khai như số lần controller gọi service trừ khi chính tương tác đó là yêu cầu kiểm thử.

## 3. Assertion cho giá trị, kiểu, mảng và field vắng mặt

Một số matcher `MockMvcResultMatchers.jsonPath` hữu ích:

| Assertion | Ý nghĩa |
| --- | --- |
| `jsonPath("$.id").value(42)` | Giá trị số phải bằng 42 |
| `jsonPath("$.status").value("CONFIRMED")` | Giá trị chuỗi phải bằng expected |
| `jsonPath("$.paid").value(true)` | Giá trị boolean phải đúng |
| `jsonPath("$.items").isArray()` | Node là mảng |
| `jsonPath("$.customer").isMap()` | Node là object được biểu diễn dạng map |
| `jsonPath("$.items").value(hasSize(2))` | Mảng có đúng hai phần tử |
| `jsonPath("$.items[*].sku").value(contains("BOOK","PEN"))` | Dãy SKU có đúng nội dung/thứ tự |
| `jsonPath("$.status").isString()` | Giá trị là chuỗi |
| `jsonPath("$.total").isNumber()` | Giá trị là số |
| `jsonPath("$.internalFlag").doesNotHaveJsonPath()` | Không tồn tại field ở đường dẫn đó |

`hasSize`, `contains`, `containsInAnyOrder`, `hasItem` là matcher của Hamcrest, có thể dùng trong `value(Matcher)`. Với các JSONPath trả collection, cần chọn matcher cho **collection** thay vì so từng phần tử đơn lẻ.

### Phân biệt field vắng mặt, `null` và chuỗi rỗng

Ba JSON này có hợp đồng khác nhau:

~~~json
{"customer": {}}
~~~

~~~json
{"customer": {"nickname": null}}
~~~

~~~json
{"customer": {"nickname": ""}}
~~~

- **Vắng mặt:** không có property `nickname`. Khi yêu cầu property phải hoàn toàn không xuất hiện, dùng `jsonPath("$.customer.nickname").doesNotHaveJsonPath()`.
- **Có mặt nhưng `null`:** property xuất hiện với giá trị `null`. Dùng `jsonPath("$.customer.nickname").hasJsonPath()` để xác nhận **đường dẫn tồn tại kể cả khi giá trị null**; có thể kết hợp kiểm null bằng cách đọc `JsonNode` và `isNull()`.
- **Chuỗi rỗng:** property có giá trị `""`, là chuỗi hợp lệ nhưng độ dài 0; `jsonPath("$.customer.nickname").value("")` mới kiểm đúng nghĩa này.

Cặp phương thức rất dễ lẫn: `exists()` đòi giá trị **không null**, còn `hasJsonPath()` chấp nhận cả `null` khi đường dẫn tồn tại. Tương tự, `doesNotExist()` phủ định sự tồn tại của giá trị không null, còn `doesNotHaveJsonPath()` yêu cầu đường dẫn **không tồn tại**, kể cả không cho phép `null`. Việc chọn sai có thể khiến test bỏ sót field thừa.

Khi dùng Jackson, `node.path("nickname")` trả `MissingNode` nếu không có field, còn `node.get("nickname")` trả Java `null` khi field thiếu; với JSON null, `get` trả một `NullNode`. Vì vậy đừng viết `node.get(...) == null` để đồng nhất thiếu field với JSON null.

### Số trong JSON và vấn đề kiểu

JSON có kiểu **number** chung, nhưng bộ giải mã Java có thể biểu diễn các giá trị `42`, `42.0`, `0.1` bằng các loại `Integer`, `Long`, `Double`, `BigDecimal` khác nhau tùy cấu hình. So sánh kiểu quá chặt có thể khiến test fail dù giá trị nghiệp vụ tương đương; so sánh quá lỏng cũng có thể bỏ sót sai hợp đồng.

- Nếu API yêu cầu số nguyên, khẳng định `isNumber()` và giá trị nguyên mong đợi, hoặc xác nhận kiểu node `isIntegralNumber()` khi dùng Jackson.
- Nếu là tiền tệ, xác định rõ cách biểu diễn (**number hay string, đơn vị tiền, scale/rounding**); tránh so số `double` bằng phép so tuyệt đối khi không cần.
- Nếu API bắt buộc `"250"` là string, test phải kiểm string thay vì chấp nhận number `250`.
- Đừng giả định `1` và `1.0` sẽ được tất cả thư viện so sánh JSON xử lý giống nhau; hành vi so sánh số phụ thuộc comparator/kiểu node.

## 4. Hai kiểu so sánh cấu trúc: strict và lenient

Spring MVC Test có:

~~~java
.andExpect(content().json(expectedJson, true))   // strict
.andExpect(content().json(expectedJson, false))  // lenient
~~~

Đây là **các đoạn biểu thức để gắn vào chain MockMvc**, không phải Java program độc lập. `expectedJson` là chuỗi JSON hợp lệ, và `content().json` dùng bộ so sánh JSON (thường từ JSONassert trong Spring Test) thay vì so raw string.

### So sánh strict

Strict có ý nghĩa khi hợp đồng xác định **đầy đủ cấu trúc**:

- Object trong actual không được thiếu field bắt buộc hoặc có field không được expected liệt kê.
- Các giá trị phải khớp.
- Các phần tử array phải có **nội dung và thứ tự** tương ứng.
- Thứ tự các **key trong JSON object** không phải tiêu chí; JSON object là tập thuộc tính, không phải dãy phần tử.

Ví dụ expected:

~~~json
{
  "id": 42,
  "items": [
    {"sku": "BOOK"},
    {"sku": "PEN"}
  ]
}
~~~

Nếu actual có thêm `"status"` ở object gốc hoặc `"quantity"` trong từng item, strict sẽ báo khác cấu trúc. Nếu actual đổi thứ tự hai item, strict cũng fail. Vì vậy muốn dùng strict với một response thực tế, expected phải nêu **đủ các field thuộc hợp đồng**.

### So sánh lenient

Lenient thường có ý nghĩa khi expected chỉ là **tập điều kiện tối thiểu**:

~~~json
{
  "id": 42,
  "status": "CONFIRMED"
}
~~~

Actual có thể chứa `customer`, `items`, `total`, `paid` bổ sung mà phép so sánh trên vẫn pass nếu hai giá trị đã nêu đúng. Chế độ lenient thông thường cũng **không buộc array theo đúng thứ tự** như strict, nhưng vẫn kiểm các phần tử được mong đợi chứ không thể bỏ qua mọi khác biệt array. Đừng sử dụng lenient để chứng minh không có field nhạy cảm bị lộ.

| Tiêu chí | Strict (`true`) | Lenient (`false`) |
| --- | --- | --- |
| Field bắt buộc trong expected | Phải có | Phải có |
| Actual thêm field ngoài expected | Thường fail | Được chấp nhận |
| Thứ tự field của object | Không quan trọng | Không quan trọng |
| Thứ tự phần tử array | Quan trọng | Không buộc thứ tự như strict |
| Đối chiếu giá trị field hiện diện trong expected | Có | Có |
| Phù hợp | API/schema cố định, cần chống field thừa | Chỉ xác nhận phần hợp đồng trọng tâm, response được phép mở rộng |

Với JSON array có phần tử lặp hoặc object phức tạp, hành vi so sánh lenient có thể khó diễn giải; assertion JSONPath cho đúng property cần thiết hoặc so sánh object theo khóa nghiệp vụ thường dễ hiểu hơn.

### Khi nào strict dễ tạo test giòn?

Nếu response có các field thay đổi mỗi lần như `generatedAt`, `traceId`, ID ngẫu nhiên, hoặc các phần tử không đảm bảo thứ tự, so sánh strict toàn response dễ fail do chi tiết **không thuộc hợp đồng**. Có thể kiểm những field động theo kiểu/định dạng và so phần ổn định bằng JSONPath; hoặc chuẩn hóa dữ liệu trước khi so cấu trúc nếu quy tắc cho phép.

Ngược lại, ở endpoint dữ liệu nhạy cảm, một response được phép trả **chỉ một bộ field cố định** thì strict giúp phát hiện việc vô tình thêm field không nên công bố.

## 5. So sánh cây JSON bằng Jackson `JsonNode`

Jackson `ObjectMapper.readTree(String)` parse JSON thành cây node, ví dụ `ObjectNode` cho object, `ArrayNode` cho array, `TextNode`, `NumericNode`, `NullNode` cho giá trị. Một khi parse, thứ tự field và cách xuống dòng của văn bản không quan trọng với equality của object; **thứ tự array và kiểu/giá trị các node** vẫn quan trọng.

~~~java
JsonNode expectedTree = objectMapper.readTree(expectedJson);
JsonNode actualTree = objectMapper.readTree(actualJson);

assertEquals(expectedTree, actualTree);
~~~

Đây là snippet minh họa có `objectMapper`, `expectedJson`, `actualJson` và import đã được thiết lập. Nếu một field thừa xuất hiện, một node sai giá trị hoặc một phần tử array khác vị trí, phép so sánh tree sẽ fail. Khác `content().json(..., false)`, `JsonNode.equals` không có chế độ tự cho phép field thừa trong object.

### Chọn `get` hay `path` khi inspect

~~~java
JsonNode customer = actualTree.path("customer");
String code = customer.path("code").asText();

assertEquals("C01", code);
assertEquals(2, actualTree.path("items").size());
~~~

Tuy tiện, `path(...).asText()` trên node thiếu có thể cho chuỗi rỗng, dễ tạo kết luận sai nếu expected cũng là rỗng. Khi contract quy định node phải có thật, hãy kiểm `has(...)`, `isMissingNode()`, `isNull()` hoặc kiểu node trước rồi mới đọc giá trị:

~~~java
assertEquals(true, actualTree.has("customer"));
assertEquals(true, actualTree.path("customer").isObject());
assertEquals("C01",
        actualTree.path("customer").path("code").asText());
~~~

Nếu cần so chính xác `null`/missing, dùng `has("field")` kết hợp `isNull()` và `hasNonNull("field")` đúng ngữ nghĩa. `has` trả true kể cả field có giá trị JSON null; `hasNonNull` chỉ true khi field có giá trị không null.

### Jackson tree và so sánh kiểu số

`JsonNode.equals` không chỉ so chuỗi JSON; nó so node theo kiểu và giá trị. Ví dụ các node số nguyên và số thực có thể khác dù hiển thị giá trị gần như nhau, còn `BigDecimal` có quy tắc tương đương liên quan kiểu/scale theo node. Nếu contract chú trọng giá trị số học hơn representation, hãy chuẩn hóa về kiểu phù hợp hoặc kiểm qua API `decimalValue()`/`compareTo` theo đặc tả, thay vì mặc định coi mọi number là đồng nhất.

**Không tự parse JSON bằng cách tách chuỗi tại dấu phẩy hoặc dùng regex.** JSON hỗ trợ chuỗi chứa dấu phẩy, ký tự escape, object/array lồng nhau; thư viện parser xử lý các trường hợp đó đúng đắn.

## 6. Ví dụ Spring Boot/Java 17 chạy được

Ví dụ tạo một Spring Boot MVC controller đơn giản và **năm** kiểm thử với `MockMvc`. `@WebMvcTest` khởi động một Spring MVC slice và không cần lắng nghe port HTTP thực. Mục tiêu là quan sát JSON client nhận được sau serialization qua Jackson và MVC. Mã không dùng cơ sở dữ liệu, service bên ngoài hoặc thời gian ngẫu nhiên, nên kết quả xác định.

### 6.1. Cấu trúc tệp

~~~text
json-assertions-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/testing/DemoApplication.java
    ├── main/java/com/example/testing/OrderController.java
    └── test/java/com/example/testing/OrderControllerTest.java
~~~

Cần có Gradle Wrapper trong dự án. Có thể sử dụng script Wrapper đã được repository tạo, hoặc tạo từ Gradle tương thích đã cài; không tự viết `gradle-wrapper.jar`.

**`settings.gradle`**

~~~groovy
rootProject.name = 'json-assertions-demo'
~~~

**`build.gradle`** — dùng một phiên bản Spring Boot 3.3.x cụ thể cho ví dụ có thể tái lập, không có ý yêu cầu dự án hiện tại đổi phiên bản:

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` đem theo Spring MVC Test, JUnit Jupiter, Jackson support qua ứng dụng và các assertion/matcher thường dùng. `content().json(...)` cần JSON comparison library có sẵn qua bộ test dependency đã khai báo. Ở ứng dụng khác có custom exclusions, phải kiểm tra test runtime classpath thực tế. Java toolchain cần JDK 17 phù hợp.

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Class `@SpringBootApplication` ở cùng package gốc giúp Spring Boot Test tìm được cấu hình ứng dụng. Main method không cần chạy thủ công khi thực thi `@WebMvcTest`.

**`src/main/java/com/example/testing/OrderController.java`**

~~~java
package com.example.testing;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public ResponseEntity<OrderResponse> find(@PathVariable long id) {
        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }

        OrderResponse order = new OrderResponse(
                42L,
                "CONFIRMED",
                new Customer("C01", "Lan"),
                List.of(
                        new Line("BOOK", 2, 120),
                        new Line("PEN", 1, 10)
                ),
                250,
                true
        );
        return ResponseEntity.ok(order);
    }

    public record OrderResponse(
            long id,
            String status,
            Customer customer,
            List<Line> items,
            int total,
            boolean paid
    ) {}

    public record Customer(String code, String name) {}

    public record Line(String sku, int quantity, int unitPrice) {}
}
~~~

Response chỉ là DTO record được Jackson serialize theo tên các thành phần. Giá trị `total=250` khớp ví dụ: `2 × 120 + 1 × 10 = 250`. Với ID khác 42, controller trả HTTP 404 không có body.

### 6.2. Viết test JSONPath, structural comparison và JsonNode

**`src/test/java/com/example/testing/OrderControllerTest.java`**

~~~java
package com.example.testing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private static String expectedFullJson() {
        return """
                {
                  "id": 42,
                  "status": "CONFIRMED",
                  "customer": {
                    "code": "C01",
                    "name": "Lan"
                  },
                  "items": [
                    {"sku": "BOOK", "quantity": 2, "unitPrice": 120},
                    {"sku": "PEN", "quantity": 1, "unitPrice": 10}
                  ],
                  "total": 250,
                  "paid": true
                }
                """;
    }

    @Test
    void jsonPathChecksImportantFields() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.customer.code").value("C01"))
                .andExpect(jsonPath("$.customer.name").value("Lan"))
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.items").value(hasSize(2)))
                .andExpect(jsonPath("$.items[*].sku")
                        .value(contains("BOOK", "PEN")))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.total").value(250))
                .andExpect(jsonPath("$.paid").value(true))
                .andExpect(jsonPath("$.discountCode")
                        .doesNotHaveJsonPath());
    }

    @Test
    void lenientJsonAllowsAdditionalFields() throws Exception {
        String requiredFields = """
                {
                  "id": 42,
                  "status": "CONFIRMED",
                  "customer": {"code": "C01"}
                }
                """;

        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(content().json(requiredFields, false));
    }

    @Test
    void strictJsonMatchesEntireResponse() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(content().json(expectedFullJson(), true));
    }

    @Test
    void jacksonJsonTreeMatchesEntireResponse() throws Exception {
        String actualJson = mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode actual = objectMapper.readTree(actualJson);
        JsonNode expected = objectMapper.readTree(expectedFullJson());

        assertEquals(expected, actual);
    }

    @Test
    void missingOrderReturns404WithoutBody() throws Exception {
        mockMvc.perform(get("/api/orders/999"))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));
    }
}
~~~

Đoạn code chứa đủ import, controller, cấu hình Spring Boot và test cho project demo. Để chạy, cần tạo/đưa các file vào **đúng đường dẫn** của cấu trúc trên và có Gradle Wrapper hợp lệ. Với dependency nêu ở `build.gradle`, không phải thêm service/mock cho controller vì controller không có dependency ngoài Spring MVC/Jackson.

### 6.3. Chạy kiểm thử

Trên Linux/macOS, tại root dự án:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu máy chưa có Wrapper, cách bootstrap thông dụng từ Gradle đã cài là chạy `gradle wrapper --gradle-version 8.5` ở project demo; Gradle 8.5 là một ví dụ phù hợp cho cấu hình này và Java 17. Với repository thực, luôn ưu tiên wrapper và version đã được dự án chọn.

Sau khi chạy thành công, bộ test ví dụ có **5 test method `@Test`**, mỗi method thực thi một lần; mong đợi **5 test pass**. Method `expectedFullJson` là helper, không phải test. Không có `System.out.println`, nên **không có stdout nghiệp vụ**. Gradle có thể hiện `BUILD SUCCESSFUL` và trạng thái `UP-TO-DATE` nếu kết quả cũ được tái sử dụng; số test thực tế đọc ở `build/reports/tests/test/index.html` hoặc `build/test-results/test/`. Nếu cần buộc chạy lại, dùng `./gradlew test --rerun-tasks`.

### 6.4. Đọc từng test để hiểu vì sao đúng

**`jsonPathChecksImportantFields`:** kiểm HTTP status, content type và những field quyết định hành vi. `contains` bắt buộc array SKU giữ thứ tự; `doesNotHaveJsonPath` bảo vệ yêu cầu không trả `discountCode`. Nó không cấm mọi field mới ngoài những field đã nêu. Nếu response thêm `internalNote` ngoài `discountCode`, test này không tự phát hiện.

**`lenientJsonAllowsAdditionalFields`:** so đúng một tập hợp yêu cầu nhỏ. Response đầy đủ có thêm `items`/`total`/`paid` vẫn hợp lệ. Test phù hợp nếu API cho phép mở rộng response mà không cần cập nhật test.

**`strictJsonMatchesEntireResponse`:** kiểm toàn bộ object và array. Nếu controller vô tình thêm `passwordHash`, đổi `status`, đổi thứ tự hai item hoặc bỏ một field, test sẽ phát hiện sai khác cấu trúc. Test phụ thuộc rõ vào hợp đồng response đã cố định.

**`jacksonJsonTreeMatchesEntireResponse`:** parse JSON response và expected thành tree rồi dùng `assertEquals`. Việc đổi xuống dòng hoặc vị trí khai báo key object không làm fail vì đây là phép so cây, nhưng đổi thứ tự array làm fail. Cách này hữu ích khi sau đó cần thao tác `JsonNode` theo điều kiện riêng.

**`missingOrderReturns404WithoutBody`:** xác nhận trường hợp không tìm thấy. Không nên luôn gọi `jsonPath` trên response không có JSON body; cần phân biệt lỗi HTTP và JSON contract. Nếu ứng dụng thật định nghĩa JSON error body, đổi test theo đúng error contract thay vì mặc định body rỗng.

## 7. JSONPath nâng cao: lọc mảng và thứ tự không ổn định

Với `items`, câu hỏi có thể là “Trong danh sách có một SKU `BOOK` với `quantity=2` hay không?” chứ không quan tâm vị trí của nó. JSONPath filter tạo kết quả dạng collection:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
                "$.items[?(@.sku == 'BOOK')].quantity")
                .value(hasItem(2)));
~~~

Đây là **snippet minh họa**; nếu thêm vào class test, import `org.hamcrest.Matchers.hasItem`. Khi truy vấn match nhiều item, `hasItem(2)` chỉ yêu cầu có ít nhất một phần tử bằng 2. Nếu cần bảo đảm **đúng một** item BOOK, hãy kiểm kích thước của tập kết quả nữa hoặc biến kết quả thành danh sách rồi assert số phần tử. Nếu thứ tự mảng là yêu cầu nghiệp vụ, dùng matcher bảo toàn thứ tự thay vì filter.

Khi JSONPath đi qua các field tùy chọn có thể thiếu, hãy thiết kế assertion phù hợp thay vì mặc định `[0]` sẽ tồn tại. Ví dụ mảng rỗng thì `$.items[0].sku` không có giá trị; điều này có thể là hợp lệ ở một tình huống “đơn hàng rỗng” nhưng phải được viết thành test riêng.

### Tránh so “contains” quá yếu

Nếu yêu cầu là “chỉ có BOOK và PEN, không có SKU nào khác”, assertion sau có thể quá yếu:

~~~java
// Có ít nhất một SKU là BOOK, nhưng chưa bảo đảm chỉ có hai SKU.
jsonPath("$.items[*].sku").value(hasItem("BOOK"));
~~~

Thay bằng `contains("BOOK", "PEN")` nếu **thứ tự cố định** hoặc kết hợp `hasSize(2)` với `containsInAnyOrder("BOOK","PEN")` nếu **không quan tâm thứ tự**. Những snippet này dùng Hamcrest matcher tương ứng và cần import; bản thân chúng không là Java program độc lập.

## 8. Sai khác quan trọng khi so JSON

| Sai khác actual so với expected | JSONPath một field | Lenient structural | Strict structural | Jackson tree |
| --- | --- | --- | --- | --- |
| Đổi khoảng trắng/xuống dòng trong văn bản JSON | Không ảnh hưởng | Không ảnh hưởng | Không ảnh hưởng | Không ảnh hưởng |
| Đổi thứ tự key trong object | Không ảnh hưởng | Không ảnh hưởng | Không ảnh hưởng | Không ảnh hưởng |
| Thêm field `extra` không nằm trong expected | Chỉ phát hiện nếu có assertion cấm field đó | Thường chấp nhận | Fail | Fail |
| Bỏ field đã khẳng định | Fail | Fail | Fail | Fail |
| Đổi thứ tự phần tử array | Phụ thuộc biểu thức/matcher | Thường chấp nhận | Fail | Fail |
| Đổi giá trị expected | Fail nếu field được kiểm | Fail | Fail | Fail |
| `null` thay vì field vắng mặt | Tùy `exists/hasJsonPath` đã chọn | Tùy expected/comparator | Phân biệt theo cấu trúc | Phân biệt node null/missing |
| Thay số nguyên bằng chuỗi | Fail khi expected kiểu number | Không phù hợp expected number | Không phù hợp expected number | Node type khác |

Bảng này mô tả **hướng kiểm tra điển hình**, không thay thế việc xác nhận hành vi của comparator/cấu hình thư viện cụ thể, nhất là với số thực, `null` và nested arrays.

### Chọn assertion theo hợp đồng

- **Hợp đồng chỉ cần vài trường:** JSONPath; kiểm đúng kiểu và expected, không bám thêm field không quan trọng.
- **Hợp đồng cấm field ngoài danh sách:** structural strict hoặc JSON tree equality; thêm test bảo vệ các field nhạy cảm nếu cần.
- **Hợp đồng cho mở rộng:** structural lenient hoặc JSONPath có chọn lọc, song vẫn kiểm những field bắt buộc.
- **Hợp đồng cho phép array đổi thứ tự:** chọn matcher không quan tâm thứ tự; không dùng JsonNode tree equality toàn response nếu array order không được bảo đảm.
- **Response có timestamp/ID động:** assert định dạng, kiểu hoặc quan hệ (ví dụ thời gian trong khoảng hợp lệ), đồng thời so phần ổn định; tránh hardcode giá trị không xác định.

Một bộ test có thể kết hợp nhiều công cụ: JSONPath để kiểm giá trị nghiệp vụ, strict comparison cho response cực kỳ ổn định, và Jackson để kiểm logic cấu trúc phức tạp. Không cần dùng cả ba cho mọi endpoint.

## 9. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Test status 200 vẫn pass dù body sai | Chỉ assert status | Thêm JSONPath/structure assertion theo hợp đồng |
| `No value at JSON path` | Sai tên field, viết sai path, path thiếu phần tử hoặc response không phải JSON | In/đọc body thực tế, kiểm path và điều kiện đầu vào |
| Hamcrest matcher fail vì `Integer` và `Long` | Kiểu numeric đã parse khác expected | Chọn đúng matcher/value type, rõ hợp đồng số |
| `hasItem` pass nhưng response có item thừa | Matcher chỉ yêu cầu tồn tại một phần tử | Kiểm kích thước và nội dung đầy đủ nếu cần |
| Structural strict fail khi API thêm field hợp lệ | Expected đang cố định toàn bộ cấu trúc | Chuyển sang lenient hoặc JSONPath nếu contract cho mở rộng |
| Lenient pass dù API lộ field không mong muốn | Comparator cho phép field thừa | Dùng strict hoặc assertion cấm field cụ thể |
| Test fail vì thứ tự array thay đổi | Dùng matcher/strict/tree có yêu cầu thứ tự | Xác định liệu thứ tự là hợp đồng; dùng matcher không quan tâm thứ tự nếu phù hợp |
| Test fail vì key order/whitespace | So raw body bằng chuỗi | Parse JSON hay dùng `content().json` |
| Field `null` vẫn bị xem như không tồn tại | Dùng `exists()/doesNotExist()` sai ý nghĩa | Dùng `hasJsonPath()/doesNotHaveJsonPath()` hoặc Jackson node check |
| `@WebMvcTest` không khởi tạo context | Thiếu SpringBootConfiguration, security filter, dependency controller/mapper | Xem nguyên nhân context, đặt bootstrap class đúng package, mock/import dependency phù hợp |
| Assertion `MockMvc` fail vì unauthorized/redirect | Spring Security filter đang tham gia test | Dùng mock user/cấu hình security test theo hợp đồng, không vô hiệu bảo mật tùy tiện |
| Status đúng nhưng Content-Type khác | Controller trả text/HTML hoặc converter không phù hợp | Kiểm API serialization và cấu hình Jackson/MVC |
| Test ghi expected JSON theo serialization hiện có | Test “sao chép” sai sót từ SUT | Viết expected độc lập từ hợp đồng và case nghiệp vụ |

**Cách chẩn đoán thực tế:** Khi một JSONPath fail, đọc response body ở log/test hoặc tạm dùng `andDo(print())` trong MockMvc test để xem response. Không để log thông tin bí mật trong CI. Khi structural comparison fail, đọc đường dẫn field của diff và xác định thay đổi đó là vi phạm hợp đồng hay thay đổi hợp lệ.

## 10. Luyện tập

**Bài A – field và kiểu:** Bổ sung assertions cho `$.customer.name`, `$.items[1].unitPrice` và `$.total`. Dùng matcher kiểm `items` là array, `paid` là boolean; kết quả của response mẫu lần lượt là `"Lan"`, `10`, `250`, `true`.

**Bài B – thiếu so với null:** Thêm field tùy chọn `note` vào DTO; thử trả `null`, chuỗi rỗng và bỏ hẳn field (có thể cần cấu hình Jackson omit-null riêng). Viết test phân biệt ba dạng bằng `hasJsonPath()/doesNotHaveJsonPath()` và `JsonNode.has/isNull`. Không coi ba dạng là tương đương nếu API contract phân biệt chúng.

**Bài C – strict và lenient:** Với expected chỉ có `id` và `status`, quan sát lenient pass còn strict fail khi response có các field khác. Sau đó dùng `expectedFullJson()` để strict pass. Đảo thứ tự hai item trong response và quan sát test strict và tree fail nếu thứ tự là hợp đồng.

**Bài D – phát hiện field thừa:** Tạm thêm `privateToken` vào DTO response. JSONPath chỉ kiểm các field quan trọng có thể vẫn pass; structural strict và Jackson tree cần fail. Hoàn nguyên thay đổi thử nghiệm và chạy lại để chắc test bảo vệ được cấu trúc.

**Bài E – API dữ liệu động:** Giả lập endpoint trả `createdAt` mới mỗi lần. Đề xuất assertion cho định dạng ISO-8601 hoặc parser thời gian và so các field ổn định bằng JSONPath; tránh viết expected timestamp cố định khiến test chập chờn.

## 11. Checklist khi viết JSON assertions

1. **Xác định contract:** field nào bắt buộc, kiểu gì, có thể `null` không, field nào không được lộ, array có giữ thứ tự không?
2. **Chọn cấp độ kiểm tra:** JSONPath cho field; strict/lenient structural cho object; JsonNode khi cần duyệt/đối chiếu cả cây.
3. **Tạo request có tiền điều kiện rõ:** dữ liệu, path, query, authentication và profile test phải xác định được.
4. **Assert status và media type**, rồi tới JSON body; test lỗi HTTP khác test response JSON thành công.
5. **Chọn expected độc lập với SUT**, nhất là expected JSON “chuẩn” và số tiền/tổng; không tự serialize lại chính object actual làm expected.
6. **Kiểm array rõ ý định:** số lượng, tập phần tử, và có hay không yêu cầu thứ tự.
7. **Phân biệt thiếu field, null, empty string**, số nguyên/số thực/string; không để converter quyết định hợp đồng thay bạn.
8. **Chạy test bằng Wrapper và đọc báo cáo**; thử gây một sai lệch nhỏ để xác nhận assertion liên quan fail, rồi hoàn nguyên.

**Ghi nhớ:** JSONPath trả lời “trường nào có giá trị gì?”, structural comparison trả lời “toàn bộ hình dạng response có đúng không?”, còn Jackson `JsonNode` cho phép biểu diễn và kiểm tra cây JSON bằng code Java. Chọn phép assert theo **hợp đồng bên ngoài của API**, để test thất bại khi hành vi sai và vẫn ổn định khi chi tiết triển khai không quan trọng thay đổi.
