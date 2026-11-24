# Custom assertion bằng phương thức trong base test

## 1. Khi matcher có sẵn chưa đủ

**Spring Cloud Contract (SCC)** dùng hợp đồng viết bằng **Groovy DSL** hoặc **YAML DSL** để kiểm chứng hành vi giao tiếp giữa **producer** và **consumer**. Từ contract, hệ thống có thể sinh test phía producer, tạo stub cho consumer chạy bằng **Stub Runner**, rồi đưa các bước đó vào CI nhằm phát hiện API thay đổi không tương thích.

Matcher thông dụng như `byEquality`, `byRegex`, `byType`, matcher ngày giờ giải quyết nhiều tình huống. Nhưng có những quy tắc đòi hỏi mã Java, chẳng hạn:

- Tỷ lệ khuyến mãi phải nằm trong đoạn **0–50**, bao gồm hai đầu.
- Mảng phân bổ tồn kho không được rỗng và không được có mã kho trùng nhau.
- Một giá trị tiền phải thỏa quy tắc làm tròn hoặc chia hết theo đơn vị thanh toán.
- ID có cấu trúc đặc thù, không thể diễn tả dễ đọc chỉ bằng regex.

**Custom assertion** là một phương thức kiểm tra do đội phát triển định nghĩa, được **generated producer test** gọi theo chỉ dẫn của contract. Trong Groovy DSL, dạng thường dùng là `byCommand('assertRule($it)')`; trong YAML DSL là `type: by_command` cùng `value` chứa lời gọi.

Bài học này tập trung vào **cách viết custom assertion bằng phương thức trong base test** và nối nó với contract, generated tests, Stub Runner và CI.

Sau bài học, bạn sẽ có thể giải thích quy trình sinh test, viết matcher `byCommand`/`by_command`, triển khai Java assertion, cấu hình `baseClassForTests`, kiểm tra test thật sự gọi method và nhận diện những chỗ custom assertion không thay thế được kiểm tra consumer.

## 2. Vị trí của custom assertion trong luồng producer–consumer

~~~mermaid
flowchart TD
    A["Contract Groovy hoặc YAML"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    C --> D["Gọi producer thật"]
    D --> E["Trích giá trị theo JSONPath"]
    E --> F["Gọi assertion method trong base test"]
    F --> G{"Assertion đạt?"}
    G -- "Không" --> H["Test đỏ, chặn thay đổi"]
    G -- "Có" --> I["Producer verification đạt"]
    B --> J["Stub artifact"]
    J --> K["Consumer test với Stub Runner"]
~~~

**Phân biệt hai phía:** custom assertion ở **response matcher** kiểm tra response mà **producer thật** trả về khi generated test chạy. Stub Runner thường trả **response mẫu** lấy từ contract; nó không tự tải và thực thi phương thức Java trong base test của producer.

| Thành phần | Chức năng |
|---|---|
| `response.bodyMatchers` (Groovy) / `response.matchers.body` (YAML) | Xác định trường và quy tắc cần kiểm tra |
| `$it` | Placeholder cho giá trị JSONPath được trích trong generated test |
| `byCommand` / `by_command` | Yêu cầu generated test gọi một phương thức tùy biến |
| `ContractTestBase` | Cấu hình môi trường test và cung cấp phương thức assertion |
| Generated producer test | Kiểm chứng code producer so với contract |
| Stub artifact + Stub Runner | Kiểm tra code consumer sử dụng hành vi mẫu đúng cách |
| CI | Tích hợp, truy vết và chặn các thay đổi không tương thích |

## 3. Bài toán xuyên suốt: tỷ lệ khuyến mãi

Giả sử **Promotion Service** cung cấp:

~~~http
GET /api/promotions/SKU-123 HTTP/1.1
Accept: application/json
~~~

Response mẫu:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "discountPercent": 15,
  "currency": "VND"
}
~~~

**Checkout Service** đọc `discountPercent` để hiển thị và tính giá. Hai đội thống nhất:

1. `discountPercent` là **số JSON**, không phải chuỗi.
2. Giá trị nằm trong đoạn **[0, 50]**.
3. Có thể thay đổi theo chiến dịch, vì vậy **không buộc luôn bằng 15**.
4. `sku` vẫn là `SKU-123` và `currency` là `VND` ở tình huống này.

Nếu dùng equality cho `discountPercent: 15`, producer trả 25 sẽ bị coi là sai dù hợp lệ. Nếu chỉ dùng type matcher, producer trả 75 vẫn có thể qua. Một Java assertion kiểm tra **kiểu và khoảng giá trị** diễn đạt yêu cầu rõ hơn.

| Response `discountPercent` | Kỳ vọng | Vì sao |
|---|---|---|
| `0` | PASS | Bằng min |
| `15` | PASS | Trong khoảng |
| `50` | PASS | Bằng max |
| `50.01` | FAIL | Vượt max |
| `-1` | FAIL | Nhỏ hơn min |
| `75` | FAIL | Vượt max |
| `"15"` | FAIL | String khác Number |
| `null` | FAIL | Không phải Number |
| Thiếu field | FAIL hoặc lỗi lúc trích JSONPath, phải kiểm chứng test thực | Không đáp ứng schema |

## 4. Viết contract bằng Groovy DSL

Ví dụ file `src/test/resources/contracts/promotions/discount-percent.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout cần phần trăm giảm giá hợp lệ'

    request {
        method GET()
        url '/api/promotions/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-123',
            discountPercent: 15,
            currency: 'VND'
        )

        bodyMatchers {
            jsonPath(
                '$.discountPercent',
                byCommand('assertValidDiscountPercent($it)')
            )
        }
    }
}
~~~

Ý nghĩa:

- Phần `request` khai báo method, URL và header gửi tới producer.
- Phần `response` khai báo HTTP status, content type và body mẫu.
- `jsonPath('$.discountPercent', ...)` chọn đúng field cần kiểm chứng.
- `byCommand('assertValidDiscountPercent($it)')` chỉ thị **generated test** gọi method cùng tên với giá trị được trích.
- `$it` là placeholder của SCC; không phải biến trong controller.

Đặt matcher ở **response** vì cần kiểm tra dữ liệu producer trả về. Các trường cố định như `sku` và `currency` vẫn có thể được kiểm tra bằng equality mặc định hoặc matcher tương ứng. Custom assertion nên tập trung vào quy tắc thực sự cần Java.

## 5. YAML DSL tương đương

Nếu dùng YAML, có thể mô tả cùng hành vi:

~~~yaml
description: Checkout cần phần trăm giảm giá hợp lệ
name: valid_discount_percent

request:
  method: GET
  url: /api/promotions/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    discountPercent: 15
    currency: VND
  matchers:
    body:
      - path: $.discountPercent
        type: by_command
        value: 'assertValidDiscountPercent($it)'
~~~

| Groovy | YAML | Vai trò |
|---|---|---|
| `bodyMatchers` | `matchers.body` | Nơi khai báo body matcher |
| `jsonPath('$.discountPercent', ...)` | `path: $.discountPercent` | Chọn trường JSON |
| `byCommand(...)` | `type: by_command` | Dùng custom command |
| `'assertValidDiscountPercent($it)'` | `value: 'assertValidDiscountPercent($it)'` | Lời gọi assertion |

YAML và Groovy ở đây là **hai cách viết thay thế**, không cần cùng xuất hiện dưới thư mục contract nếu chúng chỉ mô tả một tình huống giống hệt nhau. Khi chuyển đổi DSL, hãy kiểm tra generated tests/stubs để bảo đảm semantics vẫn tương đương.

## 6. Cấu trúc project và lớp base test

Ví dụ tổ chức producer:

~~~text
promotion-service/
├── pom.xml
└── src/
    └── test/
        ├── java/
        │   └── com/example/promotion/
        │       └── ContractTestBase.java
        └── resources/
            └── contracts/
                └── promotions/
                    └── discount-percent.groovy
~~~

`ContractTestBase` có **hai trách nhiệm**:

- Thiết lập môi trường để generated test gọi producer, ví dụ MockMvc, WebTestClient hoặc HTTP thật.
- Cung cấp phương thức `assertValidDiscountPercent` để generated test kế thừa và gọi.

Không có quy tắc rằng mọi dự án đều dùng một base class giống nhau. Cấu hình phụ thuộc **test mode**, JUnit, Spring Boot và phiên bản Spring Cloud Contract. Ví dụ tiếp theo minh họa với **MockMvc qua RestAssuredMockMvc**.

## 7. Viết method custom assertion trong base test

~~~java
package com.example.promotion;

import java.math.BigDecimal;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    WebApplicationContext applicationContext;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.webAppContextSetup(applicationContext);
    }

    public void assertValidDiscountPercent(Object actual) {
        assertThat(actual)
                .as("discountPercent phải là JSON number")
                .isInstanceOf(Number.class);

        BigDecimal percent = new BigDecimal(actual.toString());

        assertThat(percent)
                .as("discountPercent phải nằm trong [0, 50]")
                .isBetween(BigDecimal.ZERO, new BigDecimal("50"));
    }
}
~~~

Giải thích từng quyết định:

1. `public void` bảo đảm generated test có thể gọi được phương thức thừa kế.
2. `Object actual` chấp nhận đầu vào JSONPath, sau đó method **tự kiểm tra kiểu**. Dữ liệu runtime có thể là `Integer`, `Long`, `BigDecimal` hoặc kiểu Number khác.
3. `isInstanceOf(Number.class)` chặn `"15"` là string ngay cả khi parse được thành số.
4. `BigDecimal` cho phép kiểm tra khoảng thập phân một cách rõ ràng.
5. `isBetween` của AssertJ kiểm tra cả **hai đầu** 0 và 50.
6. Assertion **ném lỗi** khi điều kiện không đạt; test runner đánh dấu test thất bại.

Nếu yêu cầu phần trăm phải là **số nguyên**, cần thêm assertion về phần thập phân/kiểu JSON; mã ở trên **cho phép 12.5** vì vẫn nằm trong đoạn hợp lệ. Đây là quyết định minh họa có chủ đích.

Phương thức assertion nằm ở **test sources**, không phải code production. Trong ví dụ này phương thức cần nhìn thấy giá trị được truyền vào, không nên truy vấn database, gọi HTTP ngoài hoặc phụ thuộc thời gian hiện tại.

## 8. Cấu hình Maven và Gradle liên kết base test

Với Maven, `spring-cloud-contract-maven-plugin` có cấu hình `baseClassForTests`. Đoạn minh họa phần plugin (chọn phiên bản plugin thật tương thích với BOM):

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>4.x.y</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>com.example.promotion.ContractTestBase</baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`4.x.y` chỉ là **ký hiệu phiên bản minh họa**, phải thay bằng một phiên bản thật phù hợp với Spring Boot và Spring Cloud Release Train của dự án. Không thể chạy nguyên đoạn này với `4.x.y`.

Dependency verifier thường nằm ở test scope, không tự ghim version nếu đã được Spring Cloud BOM quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle đã áp dụng Spring Cloud Contract plugin:

~~~groovy
contracts {
    baseClassForTests = 'com.example.promotion.ContractTestBase'
}
~~~

Điều cần xác nhận trong dự án:

- Package/class trong `baseClassForTests` phải khớp với test source.
- Test framework và thư viện `RestAssuredMockMvc`, AssertJ nằm trên **test classpath**.
- Test mode được cấu hình phù hợp với cách base class khởi tạo môi trường.
- Plugin có chạy sinh test và test runner có thực thi chúng.
- Phiên bản Contract plugin nhất quán với các dependency Contract được BOM resolve.

`dependencyManagement` của Maven không tự định version cho **build plugin**. Khi nâng Spring Cloud Release Train, cần kiểm tra cả phiên bản plugin.

## 9. Generated test thực thi gì?

Khi xử lý contract, SCC có thể sinh một lớp test kế thừa base class và gọi phương thức assertion. Sơ đồ mã sau chỉ mô tả **ý tưởng**; đây **không phải generated source chính xác**:

~~~java
// Mã giả: cấu trúc, method name và API test thật tùy SCC version.
class GeneratedDiscountTest extends ContractTestBase {

    @Test
    void verifyPromotionResponse() {
        // Gửi GET /api/promotions/SKU-123 tới producer.
        // Kiểm tra response status và headers.
        // Trích trường $.discountPercent từ response JSON.
        Object actual = /* giá trị JSONPath */;
        assertValidDiscountPercent(actual);
    }
}
~~~

Sau bước sinh test, hãy kiểm tra generated source:

1. Request đúng method, URL, header.
2. Test thật sự trích `$.discountPercent`.
3. Có lời gọi `assertValidDiscountPercent(...)` với giá trị vừa trích.
4. Lớp test **extends** đúng base class hoặc có khả năng truy cập method.
5. Status/headers/các matcher khác vẫn được assert.
6. Test được compile và **thực thi**, không chỉ được tạo ra.

Có contract chứa `byCommand` chưa đủ chứng minh assertion đã chạy. Bằng chứng nằm ở generated source và test report.

## 10. Cách xác nhận custom assertion thật sự bắt lỗi

Một phép thử hữu ích là thay giá trị response producer trong môi trường test rồi chạy lại **cùng generated test**:

| Response producer trả | Kỳ vọng |
|---|---|
| `15` | PASS |
| `0` | PASS |
| `50` | PASS |
| `50.01` | FAIL |
| `75` | FAIL |
| `-2` | FAIL |
| `"15"` | FAIL (sai kiểu) |
| `null` | FAIL |

Thực hành:

1. Chạy test với `15`, ghi nhận PASS.
2. Cho producer trả `75`, test phải đỏ, có thông báo về đoạn `[0, 50]`.
3. Cho producer trả `"15"`, test phải đỏ do sai kiểu.
4. Kiểm tra `0` và `50` để xác nhận biên được bao gồm.
5. Khôi phục implementation hợp lệ.

Nếu `75` vẫn làm test xanh, cần kiểm tra: contract đã được phát hiện chưa, matcher có ở response không, test có gọi assertion không, helper có thật sự ném lỗi không và build có chạy đúng generated test không.

## 11. So sánh custom assertion với matcher có sẵn

| Quy tắc | Cách phù hợp | Vì sao |
|---|---|---|
| `status` phải bằng `ACTIVE` | Equality | Chỉ so một giá trị |
| ID theo mẫu `SKU-[0-9]+` | Regex | Có thể mô tả gọn |
| `quantity` là số | Type matcher | Kiểm tra kiểu |
| Timestamp đúng định dạng | Date/time matcher | Có quy tắc tích hợp |
| `discountPercent` trong `[0,50]` | Custom method | Có logic số học |
| Mã kho trong mảng không trùng | Custom method | Phải duyệt các phần tử |
| Response total bằng tích của nhiều trường | Assertion tích hợp có đủ ngữ cảnh | `$it` thường chỉ là một giá trị trích theo JSONPath |
| Kiểm tra tốc độ, bảo mật, database | Integration/E2E tests riêng | Không phải việc của matcher này |

Custom assertion làm contract **phụ thuộc mã kiểm thử**. Chỉ nên dùng khi quy tắc thật sự khó biểu diễn bằng matcher chuẩn. Nếu mỗi field đều gọi Java helper dù chỉ cần equality, contract sẽ mất tính khai báo và khó review.

## 12. Ví dụ nâng cao: kiểm tra mảng phân bổ tồn kho

Một producer khác trả:

~~~json
{
  "sku": "SKU-123",
  "allocations": [
    {"warehouseCode": "HCM-01", "quantity": 2},
    {"warehouseCode": "HN-02", "quantity": 3}
  ]
}
~~~

Quy tắc: `allocations` phải là mảng không rỗng; từng phần tử có mã kho không blank; các mã kho không trùng; quantity dương.

Groovy matcher:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        sku: 'SKU-123',
        allocations: [
            [warehouseCode: 'HCM-01', quantity: 2],
            [warehouseCode: 'HN-02', quantity: 3]
        ]
    )
    bodyMatchers {
        jsonPath('$.allocations', byCommand('assertValidAllocations($it)'))
    }
}
~~~

Phương thức Java sau cần đặt **bên trong base test hoặc helper được base test gọi**:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

public void assertValidAllocations(Object actual) {
    assertThat(actual)
            .as("allocations phải là JSON array")
            .isInstanceOf(List.class);

    List<?> allocations = (List<?>) actual;
    assertThat(allocations).isNotEmpty();

    Set<String> seen = new HashSet<>();

    for (Object element : allocations) {
        assertThat(element).isInstanceOf(Map.class);
        Map<?, ?> item = (Map<?, ?>) element;

        Object codeValue = item.get("warehouseCode");
        assertThat(codeValue).isInstanceOf(String.class);

        String code = (String) codeValue;
        assertThat(code).isNotBlank();
        assertThat(seen.add(code))
                .as("Trùng warehouseCode: " + code)
                .isTrue();

        Object quantity = item.get("quantity");
        assertThat(quantity).isInstanceOf(Number.class);
        assertThat(((Number) quantity).doubleValue())
                .isGreaterThan(0.0);
    }
}
~~~

**Lưu ý:** `$it` của một JSONPath trả mảng có thể có kiểu runtime cụ thể khác nhau theo thư viện JSONPath/Contract. Mẫu trên giả định giá trị là `List` chứa `Map`; phải kiểm tra generated source và kiểu dữ liệu thực tế trước khi áp dụng. Nếu `quantity` phải là số nguyên, bổ sung assertion phù hợp vì phép kiểm hiện tại chỉ bảo đảm nó là **số dương**.

### Khi cần kiểm tra quan hệ nhiều field

`$it` thường đại diện một giá trị tại JSONPath đã chọn; ví dụ matcher của `$.totalVnd` chỉ nhận total, không tự có `quantity` và `unitPriceVnd`. Với ràng buộc `totalVnd = quantity × unitPriceVnd`, hãy chọn matcher lấy đủ dữ liệu nếu DSL hỗ trợ và verify kiểu runtime, hoặc viết **integration test riêng** nhận toàn bộ response. Đừng cho helper gọi dịch vụ ngoài để suy ra các field thiếu.

## 13. Phải ném assertion failure khi dữ liệu sai

Một helper chỉ trả boolean có thể bị generated test bỏ qua:

~~~java
// Không nên: kết quả false có thể không được caller kiểm tra.
public boolean isValidPercent(Object raw) {
    if (!(raw instanceof Number)) {
        return false;
    }
    double percent = ((Number) raw).doubleValue();
    return percent >= 0 && percent <= 50;
}
~~~

Cách an toàn hơn là method dùng assert hoặc `throw new AssertionError(...)`:

~~~java
public void assertPercentWithinRange(Object raw) {
    if (!(raw instanceof Number)) {
        throw new AssertionError(
            "discountPercent phải là Number: " + raw
        );
    }

    double percent = ((Number) raw).doubleValue();
    if (!Double.isFinite(percent) || percent < 0 || percent > 50) {
        throw new AssertionError(
            "discountPercent ngoài [0,50]: " + percent
        );
    }
}
~~~

Với các giá trị cần độ chính xác cao như tiền, dùng `BigDecimal` thay vì tính toán `double`. Thông báo assertion nên nêu **field nào sai**, **giá trị thực** và **quy tắc bị vi phạm**.

## 14. Những lỗi thường gặp khi nối command và base test

| Dấu hiệu | Nguyên nhân có thể | Cách chẩn đoán |
|---|---|---|
| Generated test không thấy `assertValidDiscountPercent` | Sai `baseClassForTests`, package, tên method hoặc visibility | Kiểm tra generated class và base class |
| Compile lỗi type khi gọi method | Method nhận kiểu quá cụ thể, JSONPath trả kiểu khác | Xem lời gọi đã sinh; dùng `Object` và xác nhận kiểu bên trong |
| Test xanh dù producer trả 75 | Matcher không được sinh/chạy hoặc helper không ném lỗi | Xem generated source, thử mutation |
| Null gây `NullPointerException` khó hiểu | Helper thao tác trước khi kiểm tra null/type | Assert type trước, thêm thông điệp |
| Stub Runner không gọi helper | Stub chỉ mô phỏng response; helper ở producer test | Viết assertion ở consumer test nếu cần |
| Test chạy local nhưng lỗi CI | Khác JDK, plugin, test dependency hoặc context | Đồng bộ toolchain, kiểm tra dependency tree |
| Test bị ảnh hưởng bởi mạng hoặc thời gian | Helper không thuần, phụ thuộc dữ liệu ngoài | Tách I/O; dùng input xác định |
| Không có generated test dù build xanh | Plugin không tìm contract hoặc task chưa chạy | Xem log generation và test report |
| Contract đổi nhưng CI vẫn chạy helper cũ | Test source/build cache không được làm mới | Chạy clean, kiểm tra source và artifact mới |
| Nới giới hạn mà không phát hiện consumer lỗi | Đổi Java helper thành quy tắc quá rộng | Review helper như phần của contract, chạy consumer compatibility test |

Hướng điều tra nên đi theo **contract → generated test → base class → giá trị JSONPath → assertion → stub/consumer**.

## 15. Tổ chức base test khi có nhiều quy tắc

Khi số lượng custom assertion tăng, có thể giữ base test là điểm kết nối và chuyển các quy tắc vào lớp trợ giúp:

~~~text
src/test/java/com/example/promotion/
├── ContractTestBase.java
└── assertions/
    ├── PromotionAssertions.java
    ├── MoneyAssertions.java
    └── AllocationAssertions.java
~~~

Ví dụ phương thức trong base gọi helper chuyên biệt:

~~~java
private final PromotionAssertions checks = new PromotionAssertions();

public void assertValidDiscountPercent(Object actual) {
    checks.assertValidDiscountPercent(actual);
}
~~~

Base test vẫn phải giữ phần thiết lập môi trường producer test đã trình bày ở phần 7. Với nhiều nhóm contract, có thể sử dụng các cơ chế mapping base class của SCC theo cấu hình dự án; cần kiểm tra generated tests chọn đúng base, không chỉ suy đoán từ tên thư mục.

Chú ý quy tắc:

- Tên method phải phản ánh **nghĩa nghiệp vụ** và ổn định khi refactor.
- Không chứa I/O hoặc side effect không cần thiết.
- Helper dùng chung nên có phạm vi rõ và dễ kiểm tra biên.
- Đổi tên/chữ ký method phải sửa mọi contract gọi nó.
- Một thay đổi nới giới hạn trong helper có thể là **thay đổi cam kết API** dù file DSL không đổi.

## 16. Producer xanh chưa đồng nghĩa consumer an toàn

Giả sử ban đầu giới hạn chiết khấu là `50`. Nhóm muốn nâng tối đa lên `80` và sửa `assertValidDiscountPercent` thành cho phép `0..80`. Producer test có thể xanh. Nhưng Checkout Service cũ có thể giới hạn UI tại 50 hoặc giả định dữ liệu luôn ≤50.

Do đó:

- **Producer verification:** generated test xác nhận response của producer đáp ứng rule hiện tại trong Java helper.
- **Consumer verification:** code consumer thực tế phải xử lý được stub mới và các giá trị biên liên quan.
- **Stub artifact:** cần được sinh từ **contract/commit ứng viên** và gắn version rõ ràng để CI không vô tình dùng bản cũ.
- **Migration:** khi nới hoặc thay đổi quy tắc có tác động, cần cập nhật consumer hoặc hỗ trợ chuyển đổi phù hợp.

Một stub với response mẫu `15` chưa đủ chứng minh consumer xử lý đúng tất cả giá trị từ 0 đến 50; có thể bổ sung những case contract/stub hoặc consumer tests với response biên.

## 17. Đưa quy trình vào CI/CD

~~~mermaid
flowchart LR
    A["Thay code, contract hoặc Java helper"] --> B["Sinh producer contract tests"]
    B --> C["Compile generated tests + base class"]
    C --> D{"Producer tests đạt?"}
    D -- "Không" --> X["Chặn merge hoặc release"]
    D -- "Có" --> E["Đóng gói stub ứng viên"]
    E --> F["Consumer tests với Stub Runner"]
    F --> G{"Consumer tests đạt?"}
    G -- "Không" --> X
    G -- "Có" --> H["Tiếp tục các release gate khác"]
~~~

Trong dự án đã cấu hình SCC, lệnh Maven tham khảo:

~~~bash
./mvnw clean verify
~~~

Với Gradle:

~~~bash
./gradlew clean test
~~~

Trên Windows dùng wrapper tương ứng `mvnw.cmd` hoặc `gradlew.bat`. Tùy plugin, generated test location và task có thể khác; cần đọc log thực tế. Không nên suy ra matcher đã chạy chỉ từ exit code 0 nếu build không tìm thấy contract.

Trong CI cần lưu dấu vết: tên contract, phiên bản Boot/Cloud/Contract, generated test report, status assertion, tọa độ stub `group:artifact:version:stubs` và commit tương ứng, kết quả consumer tests. Các kiểm tra phải dùng **đúng stub ứng viên**, không được dùng lại bản trước trong cache.

## 18. Bài thực hành

**Bối cảnh:** Promotion Service có `GET /api/promotions/SKU-123`, Checkout Service dùng tỷ lệ giảm giá.

**Vòng 1 — Tạo assertion:**

1. Viết contract Groovy hoặc YAML với `discountPercent: 15`.
2. Gắn matcher `byCommand('assertValidDiscountPercent($it)')` hoặc `by_command`.
3. Tạo base class Java với method kiểm tra Number trong `[0,50]`.
4. Cấu hình plugin và chạy generated producer test.
5. Mở source test đã sinh, xác nhận method được gọi.

**Vòng 2 — Kiểm tra biên và sai kiểu:**

1. Cho producer trả 0, 50; xác nhận xanh.
2. Cho trả 51, -1 và 75; xác nhận đỏ.
3. Cho trả `"15"`; xác nhận lỗi sai kiểu.
4. Khôi phục implementation.

**Vòng 3 — Thêm mảng:**

1. Thêm `allocations` cho hai kho.
2. Viết `assertValidAllocations` để kiểm tra mã kho duy nhất và quantity dương.
3. Cố tình lặp `warehouseCode` và đưa quantity bằng 0; test phải phát hiện.
4. Kiểm tra kiểu JSONPath thực tế để bảo đảm method không có giả định sai.

**Vòng 4 — Consumer và CI:**

1. Đóng gói stub ứng viên từ contract đã kiểm chứng.
2. Consumer dùng Stub Runner với đúng artifact ứng viên.
3. Gọi client thật, assert dữ liệu và các trường hợp cần hỗ trợ.
4. Đưa kết quả producer và consumer vào release gate.

**Đầu ra nộp bài:** contract, code base/helper, generated test có lời gọi assertion, báo cáo PASS/FAIL cho mutation, stub version ứng viên và kết quả consumer test.

## 19. Checklist trước khi merge

- [ ] Custom assertion phục vụ một quy tắc mà matcher chuẩn không diễn tả rõ.
- [ ] Matcher nằm trong **response** nếu mục đích là xác minh response producer.
- [ ] JSONPath trỏ đúng trường của body mẫu.
- [ ] Tên method và biểu thức `$it` khớp Groovy/YAML DSL đang dùng.
- [ ] Generated test kế thừa đúng base class và truy cập được method.
- [ ] Method xác minh null/type/range và ném assertion failure khi sai.
- [ ] Có test sai chủ đích chứng minh assertion không bị vô hiệu.
- [ ] Generated test được sinh, compile và chạy với producer thật.
- [ ] Method tránh network, thời gian hiện tại, database hoặc side effects.
- [ ] Những thay đổi rule trong helper được review như thay đổi contract.
- [ ] Stub Runner được dùng đúng mục đích; consumer có assertion riêng.
- [ ] CI dùng artifact ứng viên chính xác, lưu thông tin version/commit.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao matcher `by_type` không đủ kiểm tra chiết khấu 0..50?**

Vì 75 vẫn là Number. Custom assertion mới kiểm tra được rule **giá trị thuộc đoạn**.

**2. `$it` trong `assertValidDiscountPercent($it)` là gì?**

Là placeholder đại diện giá trị được trích theo JSONPath khi SCC sinh producer test, không phải biến của controller.

**3. Method trả `false` nhưng không throw có nguy cơ gì?**

Nếu generated test chỉ gọi method và bỏ qua giá trị trả về, test có thể vẫn đạt. Hãy dùng assertion hoặc ném `AssertionError`.

**4. Tại sao base class cần được cấu hình trong plugin?**

Để generated test có thể kế thừa hoặc truy cập method assertion cùng môi trường thiết lập gọi producer.

**5. Stub Runner có thực thi Java method của producer không?**

Không. Custom assertion ở response matcher là kiểm chứng producer. Consumer test phải tự xác nhận việc xử lý response mẫu.

**6. Nếu nới helper từ giới hạn 50 lên 80 thì có phải thay đổi hợp đồng không?**

Có thể có. Dù DSL không đổi, giới hạn response được producer verification chấp nhận đã thay đổi. Cần đánh giá consumer và chạy test với stub ứng viên.

## 21. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, generated tests và Stub Runner.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): các matcher, custom command và `$it`.
- [Spring Cloud Contract – YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): cấu trúc `by_command` trong YAML.
- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): mô tả request/response.
- [AssertJ](https://assertj.github.io/doc/): viết assertion rõ ràng, thông báo lỗi và các phép so sánh.

**Lưu ý phiên bản:** Tên DSL, cách generated test gọi method và cấu hình test mode có thể phụ thuộc phiên bản Spring Cloud Contract. Đối chiếu tài liệu của phiên bản plugin dự án đã chọn và kiểm tra generated source thực tế.

---

**Điểm cần nhớ:** Contract chỉ rõ **JSONPath + byCommand**, base test cung cấp **Java assertion ném lỗi**, generated producer test thực thi quy tắc trên **response thật**. Để đánh giá tương thích của consumer, phải tiếp tục đóng gói **stub ứng viên** và chạy consumer tests qua Stub Runner trong CI.
