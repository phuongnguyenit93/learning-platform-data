# Chạy test được sinh bằng công cụ kiểm thử phù hợp

## 1. Vấn đề: sinh được test nhưng chưa chắc đã kiểm chứng được producer

Trong **Spring Cloud Contract (SCC)**, producer và consumer thỏa thuận hành vi HTTP hoặc thông điệp qua **Groovy DSL/YAML DSL**. **Contract Verifier** sinh test phía cung cấp (producer); từ cùng contract, công cụ còn có thể tạo stub để phía tiêu thụ (consumer) chạy với **Stub Runner**. Kết hợp hai luồng này trong CI giúp phát hiện thay đổi API không tương thích trước khi phát hành.

Ở dự án dùng **Maven**, không ít nhóm đã tích hợp thành công `spring-cloud-contract-maven-plugin`, nhìn thấy file generated Java dưới `target/` và kết luận “đã có contract testing”. Tuy nhiên, test vẫn có thể không được chạy, chạy bởi framework sai, kết nối vào controller giả hoặc không tương thích với kiểu ứng dụng đang kiểm chứng:

- Plugin sinh **JUnit 5 test**, nhưng Maven Surefire quá cũ hoặc không nhận diện test.
- Generated test cần **RestAssuredMockMvc**, nhưng base test chỉ thiết lập WebTestClient.
- Producer là **WebFlux**, nhưng lại dùng test mode chỉ phù hợp với MVC.
- Test được đặt tên `*IT`, trong khi pipeline chỉ chạy **Surefire** và chưa chạy **Failsafe**.
- Maven build có `-DskipTests` hoặc `-Dmaven.test.skip=true` mà CI không kiểm soát.
- Generated test trỏ tới **fake controller** trả đúng response mẫu nên vẫn xanh khi code production sai.
- Build thành công nhưng **không có contract nào được phát hiện** và số contract tests đã thực thi là 0.

Bài này thuộc chương **Tích hợp Maven**, tập trung vào **chạy test được sinh bằng công cụ kiểm thử phù hợp**: lựa chọn test framework, test mode, Maven test plugin, base test, lifecycle, cách xác minh thực thi, đóng gói stubs và nối vào CI.

### Sau bài học, bạn có thể

1. Giải thích khác biệt giữa **contract source**, **generated tests**, **test runner** và **stub artifact**.
2. Dùng Maven Contract Verifier plugin để cấu hình generated producer tests.
3. Chọn **JUnit Jupiter/JUnit 5**, Surefire hoặc Failsafe theo loại test và vòng đời phù hợp.
4. Nối generated tests với **Spring MVC/MockMvc**, **Spring WebFlux/WebTestClient** hoặc HTTP server chạy thật.
5. Thiết lập test base để generated tests gọi **producer code thực**, không phải response giả.
6. Chạy đúng Maven phase và xác minh **số generated tests đã thực thi**, không chỉ thấy `BUILD SUCCESS`.
7. Xử lý hợp đồng message dùng trigger và message verifier/test binder.
8. Đưa kết quả producer verification và stub ứng viên vào consumer CI qua Stub Runner.
9. Chẩn đoán những trường hợp zero-test, wrong mode, wrong runner, test skip và build xanh giả.

## 2. Hiểu chính xác những tài sản của Contract Verifier

Một luồng đơn giản:

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["Maven Spring Cloud Contract plugin"]
    B --> C["Generated Java producer tests"]
    B --> D["Generated WireMock mappings / stubs"]
    C --> E["Maven compiler và test runner"]
    E --> F["Spring test base + code producer thật"]
    F --> G{"Response/message có khớp contract?"}
    G -- "Không" --> X["FAIL producer verification"]
    G -- "Có" --> H["Đóng gói/publish candidate stubs"]
    D --> H
    H --> I["Stub Runner trong consumer tests"]
    I --> J["HTTP client / message handler consumer thật"]
    J --> K{"Consumer còn tương thích?"}
    K -- "Không" --> Y["FAIL compatibility gate"]
    K -- "Có" --> L["Tiếp tục release"]
~~~

Cần phân biệt:

| Thành phần | Vai trò | Không thể thay thế cho |
|---|---|---|
| **Contract source** | Mô tả hành vi HTTP/message được cam kết | Test đã chạy |
| **SCC Maven plugin** | Đọc contract, sinh test và stub artifacts | JUnit/Surefire chạy assertions |
| **Generated Java test** | Mã test được tạo tự động | Bằng chứng test đã thực thi |
| **JUnit/TestNG hoặc framework tương ứng** | Cung cấp annotations, assertions, lifecycle của test | Cấu hình Spring context đúng |
| **Maven Surefire/Failsafe** | Phát hiện, khởi chạy và báo cáo test theo Maven lifecycle | Việc chọn test mode và base class |
| **Test base** | Khởi tạo môi trường kiểm tra producer thật | Contract DSL |
| **WireMock stub** | Trả mẫu response cho consumer test | Producer code và producer verification |
| **Stub Runner** | Resolve, khởi động stub cho consumer | Tính đúng đắn của implementation producer |

**Nguyên tắc:** phải kiểm tra hai câu hỏi độc lập: (1) **Test được sinh đúng không?** và (2) **Test được runner chạy trên producer thật không?**. Chỉ có câu trả lời “có” cho cả hai mới tạo ra một bằng chứng verification có giá trị.

## 3. Maven lifecycle ảnh hưởng thế nào đến generated tests?

Maven có các phase liên quan trực tiếp:

~~~text
generate-test-sources
       ↓
test-compile
       ↓
test
       ↓
package
       ↓
integration-test
       ↓
verify
       ↓
install
       ↓
deploy
~~~

Bảng trách nhiệm:

| Phase | Kỳ vọng trong quy trình contract testing |
|---|---|
| `generate-test-sources` | Plugin sinh Java producer tests và đăng ký source directory thích hợp |
| `test-compile` | Compiler compile generated tests và test base |
| `test` | **Surefire** thực thi những test phù hợp naming/provider |
| `package` | Đóng gói artifact producer; SCC có thể gắn stub packaging theo cấu hình |
| `integration-test` | **Failsafe** chạy integration tests khi có cấu hình executions |
| `verify` | Chạy các bước xác minh; **Failsafe verify** báo lỗi integration test khi cấu hình đúng |
| `install` | Ghi artifacts vào local Maven repository |
| `deploy` | Publish artifacts tới repository từ xa đã cấu hình |

Tên goal và phase binding của **SCC plugin** phụ thuộc phiên bản và `<extensions>true</extensions>`. Không mặc định mọi Maven build đã gắn đầy đủ generation/packaging. Cần xem **effective POM**, log build và thư mục output.

### Vì sao `mvn test` và `mvn verify` khác nhau?

`./mvnw test` chạy đến phase `test`, phù hợp để kiểm tra generated tests do **Surefire** quản lý. `./mvnw verify` đi xa hơn, bao gồm các phase sau `test` và các plugin executions được liên kết, chẳng hạn **Failsafe**. Tuy nhiên, nếu `failsafe-maven-plugin` không được cấu hình để chạy, chỉ gọi `verify` không tự làm xuất hiện một bài integration test.

**Không nhầm Maven `verify` phase với tên sản phẩm “Contract Verifier”.** Đây là hai khái niệm khác nhau: một bên là phase của Maven lifecycle, một bên là bộ công cụ sinh và kiểm chứng hợp đồng.

## 4. Ví dụ xuyên suốt: Inventory Service là producer

Giả sử Checkout Service là consumer, Inventory Service là producer. Checkout gọi:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Producer cam kết:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Trong bài này, ta dùng một ứng dụng Spring Boot + Spring MVC để minh họa `MockMvc` mode; về sau so sánh với WebFlux và HTTP test chạy server thật.

Contract source trong producer:

~~~text
inventory-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/java/com/example/inventory/
    │   ├── InventoryApplication.java
    │   ├── InventoryController.java
    │   └── InventoryService.java
    └── test/
        ├── java/com/example/inventory/
        │   └── ContractTestBase.java
        └── resources/contracts/inventory/
            └── get-stock.groovy
~~~

Nếu dự án tổ chức contract ở thư mục khác, Maven plugin cần nhận đúng đường dẫn và generated test source directory.

## 5. Một hợp đồng Groovy DSL cụ thể

Tệp `src/test/resources/contracts/inventory/get-stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout có thể tra tồn kho SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
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
            available: true,
            quantity: 12
        )
    }
}
~~~

Trong một bản YAML DSL tương đương:

~~~yaml
description: Checkout có thể tra tồn kho SKU-123
name: inventory_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Hai snippet **thay thế nhau**; không cần chứa cả hai trong cùng project khi chỉ mô tả một scenario, vì có thể tạo test/mapping lặp.

Contract nói producer phải trả dữ liệu gì, nhưng **không quyết định test runner nào sẽ chạy file Java được sinh**. Cần cấu hình Maven và base test ở các phần sau.

## 6. Cấu hình Maven Contract Verifier plugin

Một phần POM minh họa:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>CONTRACT_PLUGIN_VERSION</version>
            <extensions>true</extensions>
            <configuration>
                <testFramework>JUNIT5</testFramework>
                <testMode>MOCKMVC</testMode>
                <baseClassForTests>
                    com.example.inventory.ContractTestBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### Ý nghĩa

- `spring-cloud-contract-maven-plugin` cung cấp cơ chế xử lý hợp đồng, sinh generated tests và stubs.
- `CONTRACT_PLUGIN_VERSION` là placeholder; **phải thay bằng version thật** phù hợp với Spring Boot/Cloud của dự án.
- `extensions=true` cho phép cơ chế lifecycle integration của plugin theo dòng SCC hỗ trợ.
- `testFramework=JUNIT5` là lựa chọn minh họa để sinh tests dùng JUnit Jupiter.
- `testMode=MOCKMVC` thể hiện hướng generated tests cho ứng dụng Spring MVC.
- `baseClassForTests` nối generated tests tới test base, nơi thiết lập Spring context và REST Assured MockMvc adapter.

**Lưu ý phiên bản:** tên giá trị enum/cú pháp `testFramework` và `testMode` có thể thay đổi giữa dòng SCC. Đối chiếu reference của đúng phiên bản và kiểm tra generated Java imports, không chỉ tin rằng tên nhìn hợp lý.

Khi dự án có nhiều nhóm contract với các base classes khác nhau, có thể cần cấu hình mapping các nhóm theo package/đường dẫn thay vì một `baseClassForTests` duy nhất. Đừng dùng một base class giả lập toàn bộ endpoints để tránh lỗi setup.

## 7. Dependency management: nhất quán Spring Boot, Cloud và plugin

Phía producer thường có `spring-cloud-starter-contract-verifier` trong test scope:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dự án Spring Boot có thể import Spring Cloud BOM (ví dụ):

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>CLOUD_TRAIN_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong một POM thực, khối `dependencyManagement` còn có thể chứa các BOM của doanh nghiệp hoặc dependency khác. Version placeholder **không chạy được** nếu chưa thay.

### Ba version nên kiểm tra riêng

1. **Spring Boot version:** quyết định Spring Framework, test infrastructure và nhiều dependency nền.
2. **Spring Cloud Release Train:** đưa nhóm Spring Cloud dependencies vào các phiên bản tương thích với Boot.
3. **Spring Cloud Contract Maven plugin version:** version của build plugin, không nhất thiết được BOM quản lý như test dependency.

Cũng phải kiểm tra **Maven Surefire/Failsafe plugin version**: một dòng JUnit 5 không được runner hỗ trợ đúng có thể khiến test không được thực thi. Nên chọn phiên bản test plugin đã được dự án kiểm chứng thay vì dựa vào bản mặc định cũ của Maven parent.

## 8. JUnit 5 hay JUnit 4: framework phải khớp với generated code

Một generated test JUnit Jupiter có thể có các import:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
~~~

Trong khi JUnit 4 dùng:

~~~java
import org.junit.Test;
import org.junit.Before;
~~~

Hai loại annotation **không tương đương** với nhau. Nếu plugin sinh JUnit 5 nhưng test base lại chỉ đặt lifecycle setup ở `@Before` của JUnit 4, phần khởi tạo adapter có thể không chạy đúng theo runner. Ngược lại, cấu hình JUnit Vintage/Jupiter lẫn lộn có thể làm test discovery khó chẩn đoán.

Trong bài dùng **JUnit 5/Jupiter** thống nhất:

- Plugin được cấu hình sinh JUnit 5 theo khả năng version;
- `spring-boot-starter-test` và `spring-cloud-starter-contract-verifier` cấp các dependency test phù hợp;
- Test base dùng `@BeforeEach`;
- Maven Surefire plugin hỗ trợ JUnit Platform;
- Generated source thực tế có `org.junit.jupiter.api.Test`;
- Surefire report có **số test đã chạy > 0**.

**Đừng trộn framework vì giữ code base test của một ví dụ cũ.** Khi nâng Spring Boot/Contract version, cần kiểm tra lại generated code và test report.

## 9. Maven Surefire: ai thực sự chạy generated tests?

`maven-surefire-plugin` thường gắn với phase `test`. Nó phát hiện và chạy test dựa trên provider, test framework và pattern tên class.

Ví dụ POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>SUREFIRE_VERSION</version>
            <configuration>
                <failIfNoTests>true</failIfNoTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`SUREFIRE_VERSION` là placeholder; chọn bản có hỗ trợ JUnit 5 và tương thích với Maven/JDK của dự án. `failIfNoTests` giúp chặn một số tình huống test task không tìm được bất kỳ test nào, nhưng **không thay thế** kiểm tra **có generated contract tests**. Nếu dự án còn nhiều unit tests, Surefire vẫn có thể chạy chúng và thành công dù contract generation bị bỏ qua.

### Quy tắc đặt tên

Mặc định, Surefire thường nhận diện các tên như:

~~~text
TestSomething
SomethingTest
SomethingTests
SomethingTestCase
~~~

Còn các test đặt tên `SomethingIT` thường thuộc cách đặt tên của **Failsafe**. Nếu SCC sinh class với tên không khớp quy tắc runner, phải điều chỉnh **test naming configuration hoặc plugin includes** theo version, và kiểm chứng không tạo double-run.

Ví dụ khi muốn include cả các tên đặc thù, có thể cấu hình:

~~~xml
<configuration>
    <includes>
        <include>**/*Test.java</include>
        <include>**/*Tests.java</include>
    </includes>
</configuration>
~~~

Đây là minh họa cấu hình patterns, không khuyến nghị sao chép để **ghi đè includes đang hoạt động** nếu dự án dùng tên test khác. Nên kiểm tra generated source names rồi bổ sung pattern tối thiểu.

## 10. Maven Failsafe: dành cho integration tests theo lifecycle

`maven-failsafe-plugin` thường dùng cho test cần khởi động web server thật, container, database hoặc các thành phần integration. Nó không tự chạy chỉ vì ta gọi `mvn verify`; cần cấu hình executions.

Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>FAILSAFE_VERSION</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Với naming convention phổ biến, Failsafe chạy `*IT`/`IT*` hoặc pattern được cấu hình. Nếu generated contract tests của SCC có tên `*Test`, chúng **không tự chuyển sang Failsafe** chỉ vì plugin này tồn tại.

| Cấu hình | Lệnh nên quan sát | Điều cần xác nhận |
|---|---|---|
| Generated `*Test`, Surefire | `./mvnw test` | Surefire chạy contract tests |
| Generated `*IT`, Failsafe đã cấu hình | `./mvnw verify` | Failsafe integration-test và verify chạy |
| Generated `*IT`, chỉ `./mvnw test` | Chưa đủ | Failsafe chưa tới phase thực thi |
| Generated `*Test`, chỉ kỳ vọng Failsafe | Chưa đủ | Naming/includes phải khớp runner |
| Surefire + Failsafe cùng match một lớp | Rủi ro | Có thể chạy test hai lần với setup không độc lập |

**Không sửa tên generated Java bằng tay trong `target/` để “cho test chạy”.** Hãy chỉnh cấu hình naming, plugin test runner hoặc SCC generator theo cách được version hỗ trợ. Output dưới `target/` có thể bị `clean` xóa và sinh lại.

## 11. Cấu hình Base Test đúng cho Spring MVC + MockMvc

Giả sử ứng dụng dùng Spring MVC và cần kiểm chứng `InventoryController` thật. Base class JUnit 5:

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Điều này có ý nghĩa:

1. `@SpringBootTest` khởi tạo Spring ApplicationContext của **producer**.
2. `@AutoConfigureMockMvc` cung cấp MockMvc được nối với Spring MVC context.
3. `@Autowired MockMvc` lấy adapter thật từ context.
4. `RestAssuredMockMvc.mockMvc(mockMvc)` nối adapter cho generated tests dùng RestAssuredMockMvc.
5. Generated tests gửi request tới **controller của producer**, không phải stub HTTP.
6. Response thực được sinh bởi controller/service và được assert theo hợp đồng.

**MockMvc không mở cổng TCP**, nhưng đi qua Spring MVC handler mapping, conversion và controller trong test context. Nếu contract cần xác nhận chi tiết network/container (TLS, reverse proxy, server-specific behavior), dùng integration test HTTP khác để bổ sung.

## 12. Base test nào tạo ra kết quả xanh giả?

Phản ví dụ:

~~~java
// SAI nếu mục tiêu là kiểm chứng implementation producer:
@BeforeEach
void setup() {
    RestAssuredMockMvc.standaloneSetup(
        new FakeInventoryController()
    );
}
~~~

Trong đó `FakeInventoryController` luôn trả:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Generated contract test có thể xanh vì fake trả đúng body mẫu — dù `InventoryController` production đã mất mapping hoặc `InventoryService` trả `available:false`.

Một phản ví dụ tinh vi hơn: dùng Spring context thật nhưng thay **toàn bộ service nghiệp vụ** bằng mock trả sẵn `StockResponse` đúng contract. Test này còn có thể kiểm tra route/serialization của controller, nhưng **không kiểm tra logic business của service**.

**Câu hỏi kiểm chứng:** nếu cố tình sửa sai code producer mà contract cần bảo vệ, generated test có chuyển **đỏ** không? Nếu không, có thể test đang dùng fake/mocks quá cao, hoặc chưa thực sự chạy.

Có thể mock dependency bên ngoài (gateway thanh toán, email sender) hoặc dùng test database/fake repository cung cấp dữ liệu thô, miễn là **đường thực thi nghiệp vụ quan trọng** vẫn là code production.

## 13. Một producer implementation để làm mutation test

Một ứng dụng minh họa:

~~~java
package com.example.inventory;

public record StockResponse(
        String sku, boolean available, int quantity) {
}
~~~

Service thật:

~~~java
package com.example.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    public StockResponse lookup(String sku) {
        int quantity = "SKU-123".equals(sku) ? 12 : 0;
        return new StockResponse(sku, quantity > 0, quantity);
    }
}
~~~

Controller thật:

~~~java
package com.example.inventory;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public StockResponse getStock(@PathVariable String sku) {
        return service.lookup(sku);
    }
}
~~~

Trong nhánh thử, đổi:

~~~java
return new StockResponse(sku, quantity > 0, quantity);
~~~

thành:

~~~java
// Cố ý sai: chỉ sử dụng trong phép thử.
return new StockResponse(sku, quantity == 0, quantity);
~~~

Với SKU-123 có quantity 12, contract yêu cầu `available:true` phải **thất bại** nếu generated test chạy qua service thật.

Sau khi quan sát thất bại, phải **khôi phục logic đúng** và kiểm tra test xanh trở lại. Phép thử này chứng minh bộ test có khả năng phát hiện lỗi trong phạm vi đã cam kết.

## 14. Chọn MockMvc, WebTestClient hay HTTP thật?

SCC có thể sinh các kiểu producer tests khác nhau tùy `testMode` và plugin version. Lựa chọn phải dựa trên **stack thực tế và phạm vi kiểm chứng**.

| Stack/cách chạy | Hướng thực thi | Base test cần có | Điều phải cảnh giác |
|---|---|---|---|
| Spring MVC | **MockMvc** | Spring MVC context + RestAssuredMockMvc setup | Không thay controller bằng fake |
| Spring WebFlux | **WebTestClient** nếu version SCC hỗ trợ | Reactive context và WebTestClient đúng kiểu generated test dùng | Không dùng MockMvc vô thức cho reactive stack |
| HTTP server thật | **Explicit/HTTP mode** phù hợp | Khởi động server và cung cấp URL/port cho test | Test phải gọi producer thật, không gọi WireMock |
| REST producer ngoài Spring MVC/WebFlux | HTTP client mode plugin hỗ trợ | Server/test harness phù hợp | Không dùng base class Spring MVC không liên quan |
| Message producer | Messaging verifier infrastructure | Trigger production và observer/message verifier | Đừng tự publish payload mẫu từ base |

Tên `testMode` và generated API **phụ thuộc phiên bản**. Không nên đoán enum hoặc copy đúng một `<testMode>...` vào mọi stack. Sau khi sinh test, xem generated Java để biết class cần `RestAssuredMockMvc`, `WebTestClient`, `RestAssured` hay messaging support nào.

**Chạy đúng công cụ** không có nghĩa chỉ chọn framework compile được; nó phải thực thi đúng **đường production code** mà contract bảo vệ.

## 15. WebFlux: khi nào chọn WebTestClient?

Với Spring WebFlux, controller có thể trả `Mono<StockResponse>` hoặc `Flux<StockResponse>`. Một base test cần khởi tạo WebFlux app context và đúng cách WebTestClient được generated test sử dụng.

Ví dụ phần setup minh họa:

~~~java
package com.example.inventory;

import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
public abstract class ReactiveContractTestBase {
    // Bổ sung WebTestClient injection/binding theo generated test
    // và theo phiên bản SCC testMode=WEBTESTCLIENT tương ứng.
}
~~~

Một bài WebTestClient test tự viết có thể kiểm tra endpoint:

~~~java
@Autowired
WebTestClient client;

@Test
void readsStock() {
    client.get()
        .uri("/api/inventory/SKU-123")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.available").isEqualTo(true);
}
~~~

Đoạn này chỉ minh họa **tool kiểm thử HTTP WebFlux**. **Nó không phải generated test của SCC**; test thực được plugin sinh phải được kiểm tra trực tiếp, rồi base class cung cấp những field/method mà generated test cần.

Vì ứng dụng reactive có các thao tác bất đồng bộ, cần đảm bảo request/response được subscribe và test timeout có hạn. Đối với `Mono/Flux` logic dài hạn, bổ sung `StepVerifier`/virtual time khi phù hợp; chỉ một HTTP contract test không chứng minh retry/backpressure/cancellation đã đúng.

## 16. HTTP thật: khi MockMvc không đủ phạm vi

Một số contract phụ thuộc behavior của HTTP server chạy thật (response compression, networking, filter/container config hoặc middleware). Khi đó có thể dùng mode HTTP/client mà phiên bản SCC hỗ trợ, cùng base test khởi động web server trong test.

Ví dụ **ý tưởng** cho RestAssured HTTP test:

~~~java
package com.example.inventory;

import io.restassured.RestAssured;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.server.LocalServerPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
public abstract class HttpContractTestBase {

    @LocalServerPort
    int port;

    @BeforeEach
    void setup() {
        RestAssured.port = port;
    }
}
~~~

**Lưu ý phiên bản:** package của `@LocalServerPort` thay đổi giữa các dòng Spring Boot. Ví dụ trên minh họa cách một phiên bản cũ đặt import; với các dòng Boot mới hơn, annotation nằm trong package test của `org.springframework.boot.test.web.server`. Hãy dùng import của phiên bản dự án và xác minh generated code có thực sự gọi RestAssured HTTP client và chọn đúng host/port.

Đối với các bài test chạy song song, **RestAssured.port là cấu hình global** có thể gây nhiễu. Nên kiểm soát song song hoặc dùng client config per-test theo API/plugin version hỗ trợ.

**Không dùng Stub Runner trong producer HTTP verification** để trả response mẫu. Làm vậy chỉ chứng minh test gọi stub từ contract, không chứng minh producer implementation thực đáp ứng hợp đồng.

## 17. Messaging contract: công cụ chạy khác HTTP

Spring Cloud Contract còn hỗ trợ hợp đồng thông điệp. Ví dụ Inventory Service phát event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stockChanged'

    input {
        triggeredBy('triggerStockChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

Phần generated messaging test cần:

- **Test framework đúng** (JUnit 5/Jupiter trong ví dụ).
- Một phương thức `triggerStockChanged()` mà generated test có thể gọi.
- Một **message verifier / test binder** hoặc messaging test infrastructure để quan sát output.
- Cấu hình timeout hữu hạn nếu output phát bất đồng bộ.
- Fixture và cleanup để không nhận nhầm message từ test khác.

Base test nên gọi application service **production**:

~~~java
@Autowired
InventoryApplicationService inventoryApplicationService;

public void triggerStockChanged() {
    inventoryApplicationService.changeStock("SKU-123", 12);
}
~~~

`InventoryApplicationService` ở đây là bean application giả định; trong dự án thực, nó phải **thực sự tạo và phát event**. Không tự làm:

~~~java
// Sai mục đích producer verification:
public void triggerStockChanged() {
    testSink.send(
        "inventory.events",
        "{\"eventType\":\"StockChanged\",\"sku\":\"SKU-123\",\"available\":true}"
    );
}
~~~

Cách sai có thể khiến generated test xanh dù code producer production không phát đúng message.

**Với message test, chọn Surefire/Failsafe vẫn chỉ là phần test runner; HTTP MockMvc không tự cung cấp message verifier.** Phải thiết lập đúng messaging adapter/binder theo stack Spring Cloud Stream/Kafka/Rabbit và phiên bản SCC.

## 18. Khi nào cần helper assertion hay setup trong base class?

Contract có thể có matcher phức tạp, ví dụ body field phải hợp lệ theo quy tắc:

~~~groovy
response {
    status OK()
    body(
        sku: 'SKU-123',
        quantity: 12
    )
    bodyMatchers {
        jsonPath('$.quantity',
            byCommand('assertNonNegativeQuantity($it)'))
    }
}
~~~

Generated test có thể cần gọi phương thức helper từ base class:

~~~java
public void assertNonNegativeQuantity(Object value) {
    if (!(value instanceof Number)) {
        throw new AssertionError("quantity phải là số");
    }

    double quantity = ((Number) value).doubleValue();

    if (quantity < 0) {
        throw new AssertionError("quantity không được âm");
    }
}
~~~

Đoạn này minh họa nguyên tắc “custom command phải có method ứng với generated test”. Đối với tiền tệ hoặc precision nghiêm ngặt, không nên dùng `double` mà phải kiểm tra kiểu cụ thể như `BigDecimal`/`Long` theo hợp đồng.

Nếu generated Java compile lỗi vì không tìm thấy `assertNonNegativeQuantity`, không nên xóa matcher để làm build xanh. Hãy kiểm tra `baseClassForTests`, visibility và chữ ký method theo **generated source thật**.

## 19. Maven plugin sinh test: tìm file ở đâu?

Trong nhiều phiên bản SCC Maven plugin, generated Java tests nằm dưới một thư mục bên trong `target/generated-test-sources`, chẳng hạn:

~~~text
target/generated-test-sources/contracts/...
~~~

Vị trí cụ thể do plugin/config quyết định. `target/` là **output build**, không phải nơi sửa hợp đồng hoặc generated Java thủ công.

Khi kiểm tra, nên nhìn ba lớp:

~~~text
src/test/resources/contracts/
  -> Hợp đồng đầu vào được commit

target/generated-test-sources/...
  -> Test source do Contract Verifier sinh

target/surefire-reports/ hoặc target/failsafe-reports/
  -> Bằng chứng test đã thực sự chạy
~~~

Trong một dự án, tên class có thể được sinh từ tên contract, package và các quy tắc SCC. Đừng dựa vào một tên cố định `GetStockTest` nếu generator tạo tên khác; hãy lấy tên **từ output thực tế**.

**Một test source tồn tại nhưng không được Maven test runner phát hiện vẫn là một lỗ hổng.**

## 20. Lệnh Maven nên dùng trong phát triển

Dùng **Maven Wrapper** của dự án để giữ version Maven nhất quán:

~~~bash
# Đọc plugin/phase theo lifecycle, sinh và chạy tests khi được cấu hình.
./mvnw clean test

# Đi qua phase verify, bao gồm các plugin executions có liên kết.
./mvnw clean verify

# Xem effective POM để kiểm tra cấu hình thừa kế/ghi đè.
./mvnw help:effective-pom

# Xem log chi tiết khi cần chẩn đoán.
./mvnw -X test
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd clean verify
.\mvnw.cmd help:effective-pom
~~~

Các lệnh này là **hướng dẫn thực hành**, chưa được chạy trong bước biên soạn. Phải chạy trong module producer hoặc từ parent với đúng selector nếu đây là multi-module build.

### Lệnh nào không đủ chứng minh tương thích?

- `./mvnw compile`: chưa tới `test`, không chứng minh generated tests đã chạy.
- `./mvnw test-compile`: chỉ compile tests, chưa thực thi.
- `./mvnw package -DskipTests`: có thể tạo artifact nhưng bỏ qua verification.
- `./mvnw verify -Dmaven.test.skip=true`: có thể bỏ cả compile và execution tests.
- `./mvnw -Dtest=InventoryUnitTest test`: có thể chỉ chạy một unit test và **không chạy generated contract tests**.
- `./mvnw integration-test`: có thể chạy Failsafe tests nhưng chưa thực thi **failsafe verify goal** để báo kết quả đầy đủ theo cấu hình.

Với pipeline phát hành stub, nên sử dụng một target Maven lifecycle thực thi **đúng producer verification**, sau đó mới đưa artifact ứng viên cho consumer test.

## 21. Đọc Surefire/Failsafe reports thay vì đoán từ exit code

Sau khi chạy Maven test, kiểm tra báo cáo runner:

~~~text
target/surefire-reports/
  TEST-com.example.inventory.GetStockTest.xml
  com.example.inventory.GetStockTest.txt

target/failsafe-reports/
  TEST-com.example.inventory.SomeIntegrationIT.xml
  ...
~~~

Đây là **tên file minh họa**, không phải output được xác nhận của dự án. Mục tiêu là đọc:

- Số tests đã chạy, số failures/errors/skipped;
- Tên lớp generated test;
- Test mode/base class đã sử dụng;
- Lỗi assertion nào không khớp status/header/body/message;
- Có test bị skip qua annotations, profile hoặc build flags không;
- Test report có thuộc **build mới** sau `clean` không.

### Guard về số lượng contract tests

Ngay cả khi Surefire đã chạy 100 unit tests, **số generated contract tests vẫn có thể bằng 0**. Do đó CI nên xác nhận **contract discovery > 0** và **generated contract tests executed > 0** đối với module phải có contract. Có thể dùng plugin hoặc script report check phù hợp với CI của dự án, nhưng bản thân bài này chỉ mô tả yêu cầu kiểm chứng, không thêm script/file bên ngoài.

## 22. Đặt tên test để Surefire hoặc Failsafe không bỏ sót

Một ma trận kiểm tra:

| Generated class | Runner dự kiến | Điều cần xác minh |
|---|---|---|
| `GetStockTest` | Surefire | Pattern `*Test` match |
| `GetStockTests` | Surefire | Pattern `*Tests` match |
| `InventoryContractIT` | Failsafe nếu cấu hình | Pattern `*IT` match và goal verify chạy |
| `InventoryContractSpec` | Không mặc định với tất cả runner | Cấu hình includes cụ thể |
| `AbstractContractTestBase` | Không nên là test độc lập | Class abstract không bị nhận như test thực |
| Helper class không có `@Test` | Không nên tính vào số tests | Đếm executed test methods, không đếm class files |

Nếu project áp dụng naming extension của SCC hoặc custom suffix cho generated tests, phải đồng bộ includes/excludes của runner.

**Đừng cấu hình cả Surefire và Failsafe nhận cùng generated class** mà không chủ đích: test có thể chạy hai lần, gây side effects hoặc làm thời gian CI tăng bất thường. Nếu cần phân tách unit tests và producer integration tests, nên định nghĩa strategy nhất quán theo naming/source sets và lifecycle.

## 23. Test resources, dữ liệu cố định và Spring context

Generated test thường gọi endpoint production, nên dữ liệu phải xác định. Ví dụ contract GET SKU-123 yêu cầu quantity 12.

Nếu producer đọc database, có thể dùng:

- Database test riêng hoặc Testcontainers khi persistence behavior thuộc phạm vi cần kiểm tra.
- `@Sql`/fixture loader để tạo dữ liệu trước test.
- Test profile tách repository/endpoint production.
- Mock gateway bên thứ ba nhưng giữ controller/service nghiệp vụ thật.
- Fixed clock/seed nếu response có timestamp/ID do ứng dụng sinh.

Ví dụ với test fixture SQL:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@org.springframework.test.context.jdbc.Sql(
    scripts = "/sql/inventory-contract-fixture.sql"
)
public abstract class ContractTestBase {
    // Thiết lập RestAssuredMockMvc với Spring MockMvc như phần 11.
}
~~~

Đoạn này chỉ minh họa annotation; file SQL phải tồn tại trong một project thực nếu dùng. Bước viết bài không tạo thêm file.

**Tách dữ liệu test khỏi logic nghiệp vụ:** fake repository có thể trả entity dữ liệu thô, nhưng nếu mock luôn `return new StockResponse("SKU-123", true, 12)` từ service thì generated test sẽ không phát hiện sai logic service nữa.

## 24. Không dùng Thread.sleep để chờ producer reactive/message

Với HTTP reactive hoặc messaging, test có thể phụ thuộc tín hiệu bất đồng bộ. Chờ bằng `Thread.sleep(5000)` dễ gây CI flakiness vì thời gian scheduling và tải host không cố định.

Cần có **deadline rõ ràng** cho từng tầng:

| Tầng | Ví dụ | Vai trò |
|---|---|---|
| Service timeout | `Mono.timeout(Duration.ofSeconds(1))` | Quy tắc nghiệp vụ/ứng dụng |
| HTTP test client timeout | WebTestClient/RestAssured timeout | Giới hạn chờ response |
| StepVerifier deadline | `verify(Duration.ofSeconds(3))` | Test Reactor không treo |
| Message receive timeout | Messaging test infrastructure | Chờ message output có giới hạn |
| Runner timeout | Surefire/Failsafe forked JVM timeout, test annotation | Tránh suite mắc kẹt |
| CI job timeout | Job-level deadline | Cổng an toàn cuối cùng |

Các giá trị chỉ là ví dụ, phải dựa trên SLO và môi trường thực. Timeout **test client** không tự khiến producer trả HTTP 504; test timeout báo test không nhận response, còn HTTP 504 phải được producer chuyển từ lỗi ứng dụng thành response công khai theo contract.

Với logic `Mono/Flux`, dùng `StepVerifier`/virtual time để thử toán tử thời gian khi có thể; với network/broker thật, vẫn cần integration tests có timeout hữu hạn.

## 25. Kiểm thử response lỗi, không chỉ happy path

Một producer thường có nhiều hợp đồng:

~~~text
GET /api/inventory/SKU-123 -> 200, available=true
GET /api/inventory/SKU-456 -> 200, available=false
GET /api/inventory/SKU-404 -> 404, SKU_NOT_FOUND
GET /api/inventory/SKU-503 -> 503, INVENTORY_UNAVAILABLE
~~~

Một YAML contract 404:

~~~yaml
description: SKU không tồn tại

request:
  method: GET
  url: /api/inventory/SKU-404

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
~~~

Generated producer test phải gửi request tới code producer thật và kiểm tra **status + body lỗi**, chứ không chỉ chấp nhận “bất kỳ response 404”. Trong consumer test với Stub Runner, phải phân biệt **business 404** được mapping chủ động trả và **WireMock unmatched 404** khi client gửi sai URL/header.

Nếu chỉ có một happy-path contract, build xanh chưa chứng minh error mapping, validation, retry hoặc tương thích khi producer bổ sung field/enum mới.

## 26. Sinh stub sau producer verification

SCC có thể sinh WireMock mappings và đóng gói stubs JAR chứa các contract resources. Ví dụ tọa độ:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.3.0-rc1
classifier:  stubs
type:        jar
~~~

Tên JAR minh họa:

~~~text
inventory-service-1.3.0-rc1-stubs.jar
~~~

Maven lifecycle có thể tạo/attach stubs artifact khi plugin được cấu hình đúng, nhưng phải **kiểm tra output thực**, không suy ra từ tên goal.

Để xem cấu trúc JAR sau build (tên file cần đổi theo output thật):

~~~bash
jar tf target/inventory-service-1.3.0-rc1-stubs.jar
~~~

Kiểm tra có những mapping và response body files cần thiết. Một JAR rỗng hoặc chứa artifact cũ không phục vụ việc kiểm chứng consumer.

**Quan trọng:** Stub Runner ở phía consumer không phải công cụ chạy generated producer tests. Hai nhiệm vụ được nối bằng **candidate artifact từ cùng contract revision/commit**, nhưng phải có **producer verification** trước khi công bố stub.

## 27. Consumer test với Stub Runner: vai trò riêng

Trong Checkout Service:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @Test
    void checkoutHandlesInventoryResponse() {
        // Gọi Inventory HTTP client thật của Checkout,
        // deserialize JSON và kiểm tra business handling.
    }
}
~~~

`LOCAL` giả định stub đã có tại repository local môi trường test. Với CI tách project, có thể dùng `REMOTE` + repository cấu hình thích hợp.

Consumer test nên gọi **HTTP client thật** của Checkout. Nếu mock chính client và trả DTO mẫu, test không phát hiện sai method, URL, headers, serialization, deserialization hoặc error mapping.

### Thay đổi API không tương thích

Nếu producer đổi body từ:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

thành:

~~~json
{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

thì producer test mới có thể đạt nếu contract cũng đổi. Nhưng Checkout cũ vẫn đọc `available`. Vì vậy phải cho Checkout cũ thử với **stubs artifact ứng viên của producer mới**, không dùng một version stable đã cache từ trước.

## 28. CI: một pipeline thật sự kiểm chứng hợp đồng

~~~mermaid
flowchart TD
    A["PR producer: code + contract + POM"] --> B["Maven generate tests"]
    B --> C["Compile generated Java"]
    C --> D["Surefire/Failsafe chạy test thật"]
    D --> E{"Có executed contract tests và tất cả đạt?"}
    E -- "Không" --> X["BLOCK"]
    E -- "Có" --> F["Sinh/publish candidate stubs JAR"]
    F --> G["Consumer test qua Stub Runner"]
    G --> H{"Client consumer tương thích?"}
    H -- "Không" --> X
    H -- "Có" --> I["Tiếp tục release gates"]
~~~

**Một CI gate tối thiểu cần xác nhận:**

1. Plugin đọc đúng contract directory; không phải zero-contract run.
2. Generated test files được tạo ra.
3. Test source compile thành công.
4. Surefire/Failsafe chạy đúng framework và có **executed contract tests > 0**.
5. Các assertions thực sự chạy với **producer implementation thật**.
6. `-DskipTests` và `-Dmaven.test.skip=true` không được bật trong verification stage.
7. Stubs JAR có mappings phù hợp, đúng group/artifact/version/classifier.
8. Candidate artifact liên kết được với đúng Git commit.
9. Consumer test tải **exact candidate version**, không dùng `latest` hoặc cache nhập nhằng.
10. Consumer chạy client/handler thực với Stub Runner, bao gồm error cases quan trọng.
11. Pipeline lưu test reports, Maven/JDK/Boot/Cloud/Contract versions và logs.
12. Khi contract thay đổi theo hướng breaking, consumer hiện hành trong phạm vi hỗ trợ phải được kiểm chứng trước release.

Đây là **khung thiết kế CI**; bài này không tạo thêm Jenkinsfile/GitHub Actions file vì phạm vi được giao chỉ là một tệp Markdown và status của YAML.

## 29. Maven multi-module: test nào chạy ở module nào?

Một repository có thể có:

~~~text
commerce-platform/
  pom.xml
  inventory-service/
    pom.xml
    src/test/resources/contracts/...
  pricing-service/
    pom.xml
    src/test/resources/contracts/...
  checkout-service/
    pom.xml
    src/test/java/...consumer tests...
~~~

Cấu hình SCC Maven plugin chỉ nên được **kích hoạt ở producer module cần generate contract tests**. Một parent POM có thể quản lý plugin version, nhưng không có nghĩa nên tự động áp dụng plugin cho tất cả modules.

Ví dụ chạy riêng Inventory (tùy reactor/module names):

~~~bash
./mvnw -pl inventory-service -am clean verify
~~~

`-pl` chọn module, `-am` build thêm dependencies trong reactor khi cần. Phải kiểm tra test reports và artifact của **inventory-service** cụ thể. Chạy `verify` ở parent mà chỉ có unit tests của Checkout đạt không chứng minh Inventory contract tests đã chạy.

Nếu hai producer có các base classes và contracts khác nhau, mỗi module cần source directory, test mode và dependencies phù hợp.

## 30. Trường hợp test bị skip: Maven có nhiều cách bỏ qua

Một bảng cảnh báo:

| Cấu hình/lệnh | Ảnh hưởng phổ biến | Rủi ro |
|---|---|---|
| `-DskipTests` | Bỏ thực thi tests theo Surefire/Failsafe | Build xanh mà không verification |
| `-Dmaven.test.skip=true` | Có thể bỏ cả test compilation và execution | Generated Java có thể không được kiểm tra |
| `-Dtest=SomeUnitTest` | Chỉ chọn subset tests | Generated contracts không được chạy |
| `-DskipITs` | Bỏ Failsafe integration tests | Test tên `*IT` bị bỏ qua |
| `<skipTests>true</skipTests>` trong plugin | Có thể bỏ qua toàn bộ test execution | CI không thấy mismatch |
| Profile Maven không kích hoạt SCC execution | Không sinh test/stub đúng mong đợi | Zero-contract/zero-test |
| Surefire includes không match generated class | Test không được discover | Xanh giả nếu không có guard |
| Test `@Disabled` hoặc JUnit condition | Test bị skip | Report có skipped > 0 |

Không phải tất cả property có cùng semantics trong mọi version/plugin; **cần kiểm tra effective POM và log**. Nếu `skipTests` được dùng ở stage chỉ đóng gói artifact đã được verification ở stage trước, phải có bằng chứng rõ ràng và bảo đảm **không thay đổi code/contract giữa hai stage**.

**Đối với verification stage chính, khuyến nghị fail closed:** nếu không có contract hoặc không có generated test executed, job phải báo lỗi thay vì được xem là pass.

## 31. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra tiếp |
|---|---|---|
| Không có generated Java | Plugin không chạy, sai contract path, YAML/Groovy không được phát hiện | POM/plugin logs, contract directory |
| File generated có nhưng không compile | Sai import, JUnit version, base class hoặc helper | Compiler error, generated source |
| Generated test compile nhưng không chạy | Surefire/Failsafe includes, naming hoặc runner cũ | Reports, runner logs và test count |
| JUnit 5 test chạy mà `@BeforeEach` không gọi | Framework/lifecycle không khớp hoặc setup nằm sai class | Generated import và base test annotations |
| MockMvc không có context | Thiếu `@SpringBootTest`/`@AutoConfigureMockMvc` | Test base Spring setup |
| WebFlux test dùng MVC adapter | `testMode` sai | Plugin config và generated code |
| HTTP mode gọi sai cổng | Server chưa start, port/base URL sai | Random port/setup, actual request |
| Message test không nhận event | Trigger/binder/verifier sai | Production trigger, destination, timeout |
| Stub tests xanh nhưng producer code sai | Chỉ chạy Stub Runner, bỏ generated producer tests | Producer test report và mutation |
| Test xanh khi sửa sai service | Fake controller/mock service quá cao | Test base, Spring bean overrides |
| Build xanh nhưng zero-contract | Sai đường dẫn/plugin skip | Contract discovery guard |
| Surefire báo no tests | Test naming/provider không match | Generated class names, plugin version |
| Failsafe tests chỉ chạy khi verify | Chưa cấu hình/bật integration-test+verify | Failsafe executions |
| Test fail trên CI nhưng local pass | JDK/Maven/profile/clock/fixture khác | Wrapper, effective POM, reports |
| Stubs JAR không có mappings | Generation/packaging sai, input rỗng | Kiểm tra JAR entries |
| Consumer nhận API schema cũ | Stub version/cache sai | Exact candidate coordinate/commit |

### Một trình tự debug hữu ích

~~~text
1. Kiểm tra contract nguồn (Groovy/YAML)
2. Kiểm tra SCC Maven plugin version + configuration
3. Kiểm tra log goal sinh test/stub
4. Mở generated Java: framework + test mode + base class
5. Kiểm tra test compilation
6. Xem Surefire/Failsafe report và executed tests count
7. Kiểm tra producer response/message thực
8. Mở stubs JAR, kiểm tra mappings/fixtures
9. Kiểm tra consumer Stub Runner exact artifact
10. Đối chiếu behavior cũ/mới và breaking changes
~~~

Không sửa bước 8 khi lỗi đang ở bước 4 (JUnit imports), và không thay contract cho khớp code sai khi test đang phát hiện một regression thật.

## 32. Thực hành A — JUnit 5 + Surefire + MockMvc

**Mục tiêu:** sinh và chạy một producer contract test thật bằng Maven.

1. Tạo Inventory Service Spring MVC với controller và service ở phần 13.
2. Chọn bộ version JDK/Maven/Boot/Cloud/Contract tương thích.
3. Thêm SCC Maven plugin và `spring-cloud-starter-contract-verifier`.
4. Cấu hình `<testFramework>JUNIT5</testFramework>`, `<testMode>MOCKMVC</testMode>` và `baseClassForTests` theo phiên bản.
5. Tạo base test `@SpringBootTest + @AutoConfigureMockMvc` với `RestAssuredMockMvc.mockMvc(...)`.
6. Viết contract GET ở phần 5.
7. Dùng `./mvnw clean test` trong môi trường dự án.
8. Kiểm tra generated class và `target/surefire-reports`; ghi số test thực sự chạy.
9. Cố tình đổi logic `quantity > 0` thành `quantity == 0` và xác nhận test **đỏ**.
10. Khôi phục code, chạy lại test.

**Bằng chứng nộp:** POM, contract, test base, generated Java/test report, log mutation fail/pass.

## 33. Thực hành B — Chọn đúng runner cho integration tests

**Mục tiêu:** phân biệt test chạy trong `test` với test chạy ở `integration-test/verify`.

1. Xác định tên generated tests hiện tại (ví dụ `*Test`).
2. Kiểm tra chúng được Surefire phát hiện và chạy.
3. Nếu dự án có lớp integration test tên `*IT`, cấu hình Failsafe executions.
4. Chạy `./mvnw test`, kiểm tra Surefire reports.
5. Chạy `./mvnw verify`, kiểm tra Failsafe reports.
6. Xác nhận generated contract tests **không bị bỏ qua hoặc chạy hai lần**.
7. Tạm dùng `-DskipITs` trong nhánh thử để hiểu gate nào bị vô hiệu hóa.
8. Khôi phục flags và chốt lifecycle CI.

**Bằng chứng nộp:** ma trận tên test → runner → Maven phase → executed count.

## 34. Thực hành C — So sánh MockMvc, WebTestClient và HTTP thực

**Mục tiêu:** chọn test mode đúng stack và phạm vi, không copy cấu hình máy móc.

1. Với Spring MVC, dùng MockMvc + context thật; xác minh generated test đã chạy.
2. Xem một mẫu WebFlux/Mono controller riêng và test bằng WebTestClient.
3. Đối chiếu SCC plugin version có `WEBTESTCLIENT` mode hay cấu hình tương đương không.
4. Kiểm tra generated code yêu cầu những field/method setup nào của base test.
5. Nếu cần HTTP server thật, thử HTTP mode với random port và REST Assured khi phiên bản hỗ trợ.
6. Không dùng WireMock thay producer trong bất kỳ producer verification nào.
7. Tạo một lỗi controller/service có chủ đích cho từng mode; test phải phát hiện.
8. Ghi lại phạm vi mà từng test **chưa bảo vệ** (network, security, broker, downstream).

**Bằng chứng nộp:** bảng mode ↔ runner ↔ base setup ↔ lỗi phát hiện được.

## 35. Thực hành D — Producer verification tới Stub Runner consumer

**Mục tiêu:** bảo đảm consumer thử chính artifact của producer đang thay đổi.

1. Chạy generated producer tests đạt.
2. Sinh và đóng gói stubs JAR, kiểm tra mapping/content.
3. Install/publish stub candidate với version không nhập nhằng.
4. Cho Checkout dùng Stub Runner tải exact candidate version.
5. Gọi Inventory HTTP client thực của Checkout và assert `available`/`quantity`.
6. Tạo phiên bản producer ứng viên đổi field `available` thành `inStock`.
7. Chạy Checkout cũ với **stub mới** để phát hiện breaking change.
8. Đề xuất migration/versioning nếu consumer chưa hỗ trợ.
9. Đưa các cổng vào pipeline theo phần 28.

**Bằng chứng nộp:** producer reports, stubs artifact metadata, consumer test report, thay đổi contract và kế hoạch tương thích.

## 36. Checklist trước khi hợp nhất POM/contract

- [ ] `spring-cloud-contract-maven-plugin` được áp dụng đúng producer module.
- [ ] Spring Boot, Cloud Release Train, Contract plugin, Maven/JDK và Surefire/Failsafe versions phù hợp.
- [ ] Contract source đúng thư mục, Groovy/YAML schema hợp lệ.
- [ ] `testFramework` khớp JUnit/Jupiter hoặc runner đã chọn.
- [ ] `testMode` khớp MVC/WebFlux/HTTP/message testing infrastructure.
- [ ] `baseClassForTests` trỏ đúng class, package và lifecycle annotations.
- [ ] Generated tests gọi **producer code thật**, không fake controller/service đáp sẵn body.
- [ ] Generated Java được sinh và compile trong Maven lifecycle.
- [ ] Surefire/Failsafe includes phát hiện đúng tên generated classes.
- [ ] Verification stage không bật skip flags hoặc test filter vô tình.
- [ ] **Executed contract tests > 0** và failures/errors/skipped được đánh giá.
- [ ] Dữ liệu fixture ổn định, không dùng production database/credentials.
- [ ] Những timeout async/message có deadline hữu hạn; không dùng sleep cố định làm đồng bộ chính.
- [ ] Có mutation test thử sai hành vi quan trọng để chứng minh test chuyển đỏ.
- [ ] HTTP success và error contracts quan trọng được bao phủ.
- [ ] Message contract trigger gọi application production và verifier quan sát output thật.
- [ ] Stubs JAR có mappings/body files, đúng version và classifier.
- [ ] Consumer Stub Runner dùng **exact candidate artifact** của producer.
- [ ] Consumer test dùng HTTP client/message handler thật, bao gồm deserialization/error mapping.
- [ ] Multi-module CI chạy đúng module/phase, không coi unit tests của module khác là producer verification.
- [ ] Logs và reports đủ chứng cứ để truy nguyên lỗi theo contract/framework/runner.
- [ ] Không hardcode token hay dữ liệu khách hàng thật vào contract/test fixture.
- [ ] Thay đổi breaking được xác nhận với các consumer đang trong phạm vi hỗ trợ.

## 37. Câu hỏi tự kiểm tra

**1. Vì sao file generated Java xuất hiện chưa đủ chứng minh contract được kiểm chứng?**

Vì test có thể không được compile, không được Surefire/Failsafe phát hiện hoặc bị skip. Cần test report chứng minh đã thực thi và assertions chạy trên producer thật.

**2. Spring Cloud Contract Maven plugin và Maven Surefire có cùng nhiệm vụ không?**

Không. SCC plugin xử lý contract và sinh test/stub; Surefire là runner thực thi test trong Maven phase `test`.

**3. Khi nào dùng Failsafe thay vì Surefire?**

Khi dự án chủ đích tổ chức tests dạng integration test ở lifecycle `integration-test/verify`, thường theo pattern `*IT`. Cần cấu hình Failsafe execution và tránh double-run.

**4. Vì sao JUnit 5 generated tests cần tương thích với test base?**

Vì annotations và lifecycle của Jupiter khác JUnit 4. Nếu generated tests dùng `org.junit.jupiter.api.Test`, setup `@BeforeEach` và runner cần phù hợp.

**5. Tại sao không dùng MockMvc cho mọi producer?**

Vì MockMvc hướng tới Spring MVC stack. WebFlux hoặc server HTTP thực có adapter/mode phù hợp hơn; phải đối chiếu SCC version và generated code.

**6. Nếu test base dựng fake controller trả body đúng contract thì có an toàn không?**

Không nếu mục tiêu là kiểm chứng producer implementation. Test có thể xanh khi code thật sai. Cần gọi controller/service production trong phạm vi hợp đồng.

**7. Vì sao `./mvnw verify` có thể vẫn không chạy integration tests?**

Vì Failsafe chưa được cấu hình để chạy `integration-test` và `verify` goals, hoặc test naming/includes không match. Maven phase không tự cấu hình tất cả plugin.

**8. `-DskipTests` và `-Dmaven.test.skip=true` khác nhau thế nào?**

Thông thường `skipTests` bỏ **thực thi** tests; `maven.test.skip` có thể bỏ cả **compile và thực thi** test. Cả hai đều nguy hiểm nếu xuất hiện ở compatibility verification stage.

**9. Vì sao producer và contract cùng đổi field rồi producer test xanh chưa đủ?**

Vì consumer cũ vẫn có thể đọc field cũ. Phải thử consumer với **stub được sinh từ chính contract/version ứng viên**, không từ stable cache.

**10. CI cần tối thiểu những bằng chứng nào?**

Contract được nhận diện, generated test compile, **test executed > 0**, assertions đạt trên producer thật, stubs JAR hợp lệ, artifact version/commit rõ và consumer test với Stub Runner dùng đúng candidate.

## 38. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, Groovy/YAML DSL, producer tests và Stub Runner.
- [Spring Cloud Contract — Maven Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): plugin, lifecycle, generated tests và stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): HTTP/message contract syntax.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): consumer compatibility testing.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases `test`, `integration-test`, `verify`, `package` và `deploy`.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): test discovery, includes/excludes, reports và JUnit Platform.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration tests và verify goal.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter lifecycle, test annotations và discovery.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): kiểm thử MVC mà không cần server TCP.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP WebFlux.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): xác định request nào khớp stub.

**Lưu ý phiên bản:** Các giá trị `testFramework/testMode`, generated source path, goal binding, JUnit/Jupiter provider, package `@LocalServerPort`, Surefire/Failsafe behavior và stub packaging có thể khác theo dòng Maven/SCC/Spring Boot. Luôn đối chiếu tài liệu **cùng phiên bản** với build thực tế. Những version viết bằng placeholder cần thay bằng version được hỗ trợ; các lệnh và ví dụ chỉ minh họa quy trình, **không phải kết quả đã chạy trên repository trong bước biên soạn này**.

---

**Điểm cần nhớ:** Để “chạy test được sinh bằng công cụ kiểm thử phù hợp”, phải nối **Spring Cloud Contract generator → JUnit/test framework → Maven Surefire/Failsafe → base test đúng mode → producer implementation thật**. Chỉ khi generated tests thực sự chạy, có báo cáo và có thể chuyển đỏ khi producer vi phạm contract, chúng mới mang giá trị kiểm chứng. Sau đó mới đóng gói stubs JAR của **đúng commit ứng viên** và cho consumer dùng **Stub Runner** trong CI để phát hiện thay đổi API không tương thích.
