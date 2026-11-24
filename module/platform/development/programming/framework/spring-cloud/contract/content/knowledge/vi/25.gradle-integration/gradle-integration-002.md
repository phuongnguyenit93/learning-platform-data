# Cấu hình contracts DSL trong build Gradle

## 1. Vì sao cần cấu hình Spring Cloud Contract ngay trong Gradle?

**Spring Cloud Contract (SCC)** giúp các nhóm producer và consumer thỏa thuận hành vi HTTP hoặc thông điệp thông qua hợp đồng **Groovy DSL/YAML DSL**. Phía producer dùng **Contract Verifier** để sinh test và xác minh code thực tế. Từ cùng hợp đồng, hệ thống có thể tạo các HTTP stub hoặc message stub cho consumer dùng với **Stub Runner**. Khi đưa vào CI, hai phía có thể phát hiện thay đổi API không tương thích sớm hơn.

Với một dự án dùng **Gradle**, việc đặt tệp contract vào repository chỉ là bước đầu. Gradle cần biết:

- Plugin nào đọc và xử lý hợp đồng;
- Thư mục nào chứa contract;
- Sinh test theo **MockMvc**, **WebTestClient** hay phương thức phù hợp với stack producer;
- Generated tests kế thừa **base test class** nào;
- Test source/generated source có được compile và thực thi không;
- Stub mappings và **stubs JAR** được tạo, kiểm tra và phát hành như thế nào.

Đó là vai trò của **khối cấu hình `contracts { ... }`** do Spring Cloud Contract Gradle plugin cung cấp.

Bài này thuộc chương **Tích hợp Gradle** và tập trung vào **cấu hình contracts DSL trong build Gradle**. Nội dung được trình bày theo hướng có thể tự học và áp dụng trong Spring Boot service, từ một ví dụ HTTP đơn giản tới nhiều nhóm contract, build đa module, Stub Runner và CI.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Gradle contracts extension** với **Groovy/YAML contract files**.
2. Áp dụng Spring Cloud Contract plugin và khai báo dependencies theo bộ phiên bản tương thích.
3. Cấu hình các thuộc tính thường dùng như `contractsDslDir`, `testMode` và `baseClassForTests`.
4. Hiểu trường hợp cần chọn nhiều base classes và tổ chức contract theo nhóm nghiệp vụ.
5. Viết một contract HTTP, sinh producer tests và kiểm tra test đã chạy thật.
6. Tạo stub mappings, stubs JAR và kết nối consumer với Stub Runner.
7. Nhận diện sự khác nhau giữa cấu hình Gradle Groovy DSL và Kotlin DSL.
8. Chẩn đoán build xanh giả do thiếu contract, sai thư mục, sai test mode hoặc bỏ qua task.
9. Đưa Gradle producer verification và consumer compatibility vào CI.

## 2. Hai chữ “DSL” khác nhau trong cùng dự án

Khi làm việc với SCC, có hai ngữ cảnh đều thường được gọi là DSL:

| Loại DSL | Nằm ở đâu? | Làm nhiệm vụ gì? |
|---|---|---|
| **Gradle Groovy DSL** | `build.gradle` | Cấu hình plugin, dependencies, tasks, `contracts { ... }` |
| **Gradle Kotlin DSL** | `build.gradle.kts` | Cùng mục đích cấu hình build nhưng dùng cú pháp Kotlin |
| **Spring Cloud Contract Groovy DSL** | File `*.groovy` trong thư mục contracts | Mô tả request/response hoặc input/output message |
| **Spring Cloud Contract YAML DSL** | File `*.yml`/`*.yaml` trong thư mục contracts | Mô tả cùng hành vi bằng YAML |

Ví dụ khối trong `build.gradle`:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

Nó **không phải** hợp đồng HTTP. Nó chỉ cấu hình **cách plugin tìm, sinh và thực thi các test/stub**.

Ví dụ một tệp hợp đồng:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url '/api/inventory/SKU-123'
    }
    response {
        status OK()
        body(sku: 'SKU-123', available: true, quantity: 12)
    }
}
~~~

Tệp thứ hai mô tả **hành vi giao tiếp**. Gradle plugin đọc nó dựa trên cấu hình ở tệp thứ nhất.

**Điểm cần nhớ:** `contracts { ... }` là **build configuration**; `Contract.make { ... }` là **specification về hành vi producer–consumer**. Đặt nhầm nội dung của hai DSL vào nhau sẽ không tạo ra một pipeline kiểm thử hợp đồng hợp lệ.

## 3. Luồng xử lý từ build.gradle tới consumer

~~~mermaid
flowchart TD
    A["build.gradle: plugin và contracts extension"] --> B["Tìm Groovy/YAML contract files"]
    B --> C{"Contract parse được?"}
    C -- "Không" --> X["FAIL: sửa DSL/đường dẫn"]
    C -- "Có" --> D["Sinh generated producer tests"]
    C --> E["Sinh HTTP/message stub artifacts"]
    D --> F["Compile + chạy với producer thật"]
    F --> G{"Test đạt?"}
    G -- "Không" --> Y["FAIL: implementation hoặc fixture lệch contract"]
    G -- "Có" --> H["Đóng gói stubs JAR ứng viên"]
    E --> H
    H --> I["Install / publish artifact"]
    I --> J["Consumer dùng Stub Runner"]
    J --> K["Consumer client/handler thật"]
    K --> L{"Consumer tương thích?"}
    L -- "Không" --> Z["FAIL: breaking change hoặc client sai"]
    L -- "Có" --> M["Qua compatibility gate"]
~~~

Các khâu là **mục tiêu logic** của quy trình. Không nên suy ra plugin tự động chạy mọi khâu trong mọi dự án: mức độ gắn task, cấu hình publication và tên task cụ thể phụ thuộc **phiên bản Gradle, SCC và cách build được viết**.

Cấu hình Gradle tốt phải bảo đảm mỗi nhánh có **bằng chứng đầu ra**: contract đã được nhận diện, test được sinh, test thật sự chạy, stub mappings có mặt và artifact ứng viên được consumer sử dụng.

## 4. Điều kiện trước khi thêm plugin

Giả sử producer là **Inventory Service**, một ứng dụng Spring Boot dùng Spring MVC. API cần bảo vệ:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Trước khi cấu hình, cần thống nhất:

- **JDK** mà Spring Boot và Spring Cloud Contract phiên bản đã chọn hỗ trợ.
- **Gradle** bản tương thích với Spring Boot Gradle plugin.
- **Spring Boot version** và **Spring Cloud Release Train** tương thích.
- **Spring Cloud Contract plugin version** phù hợp với các dependency Contract trong project.
- Producer là **Spring MVC** hay **Spring WebFlux**, hoặc không dùng Spring HTTP stack.
- Test runner dùng **JUnit Jupiter** hay cấu hình khác.
- Nơi lưu contracts và test base.

Không lấy một phiên bản cụ thể từ hướng dẫn cũ rồi dùng với Spring Boot bất kỳ. **Spring Cloud BOM quản lý phiên bản dependency không đồng nghĩa tự quản lý version của Gradle plugin**. Plugin ID/version phải được kiểm tra riêng trong plugin resolution.

Bài dùng các placeholder như `BOOT_VERSION`, `CLOUD_TRAIN_VERSION`, `CONTRACT_PLUGIN_VERSION`. Chúng cần được thay bằng **phiên bản thật**; không phải ký hiệu có thể chạy nguyên văn.

## 5. Cấu trúc thư mục của một producer Gradle

Một cách tổ chức dễ hiểu:

~~~text
inventory-service/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
└── src/
    ├── main/
    │   └── java/com/example/inventory/
    │       ├── InventoryApplication.java
    │       ├── InventoryController.java
    │       └── InventoryService.java
    └── test/
        ├── java/com/example/inventory/
        │   └── ContractTestBase.java
        └── resources/
            └── contracts/
                └── inventory/
                    └── get-stock.groovy
~~~

Tệp `src/test/resources/contracts/inventory/get-stock.groovy` sẽ được plugin xử lý. `ContractTestBase` cung cấp cách generated tests khởi tạo đúng ứng dụng producer thật.

Đường dẫn `src/test/resources/contracts` là convention thường gặp của Spring Cloud Contract producer project. Nếu dự án muốn dùng đường dẫn khác, phải chỉ định chính xác bằng `contractsDslDir` và kiểm tra task có đọc thư mục đó không.

**Không được** đặt toàn bộ contract dưới `src/main/resources` rồi kỳ vọng plugin tự nhận, nếu cấu hình đang chỉ tới `src/test/resources/contracts`.

## 6. Cấu hình build.gradle bằng Gradle Groovy DSL

Ví dụ build script minh họa cho producer Spring MVC:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_VERSION'
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

group = 'com.example'
version = '1.3.0-rc1'

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', 'CLOUD_TRAIN_VERSION')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    contractsDslDir = file('src/test/resources/contracts')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Đây là template để giải thích các khối cấu hình**, chưa phải `build.gradle` có thể chạy ngay. Thay tất cả placeholder bằng version thực đã được kiểm tra tương thích. Tùy Gradle/Boot/Cloud, dự án có thể dùng `platform(...)` hoặc `enforcedPlatform(...)` thay vì plugin `io.spring.dependency-management`; không cần dùng cả hai cách quản lý BOM một cách mâu thuẫn.

### Tác dụng của từng khối

| Cấu hình | Tác dụng |
|---|---|
| `id 'org.springframework.cloud.contract'` | Áp dụng Gradle plugin của Contract Verifier |
| `group/version` | Định danh artifact producer và stubs ứng viên |
| `repositories` | Nguồn resolve dependencies |
| Spring Cloud BOM | Đồng bộ phiên bản các dependency Spring Cloud/Contract |
| `spring-cloud-starter-contract-verifier` | Hỗ trợ kiểm thử hợp đồng ở test scope |
| `contractsDslDir` | Xác định nguồn contracts |
| `testMode` | Chọn chế độ generated producer tests |
| `baseClassForTests` | Chọn base test class cho generated tests |
| `useJUnitPlatform()` | Cho Gradle test task thực thi JUnit Jupiter nếu dự án dùng JUnit 5 |

**Quan trọng:** chỉ thêm plugin/dependency chưa bảo đảm có test; phải có **hợp đồng đầu vào**, base class/test infrastructure thích hợp và task/lifecycle thực sự thực thi generated tests.

## 7. contractsDslDir: plugin sẽ đọc contract ở đâu?

Đây là cấu hình đầu tiên cần xác nhận:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
}
~~~

Thông thường đường dẫn được resolve tương đối so với **project/module đang áp dụng plugin**. Trong Gradle multi-project build, `file('src/test/resources/contracts')` của `:inventory-service` trỏ tới thư mục bên trong **subproject đó**, không mặc nhiên trỏ root repository.

Nếu project dùng thư mục khác:

~~~groovy
contracts {
    contractsDslDir = file('contract-specifications')
}
~~~

thì contract phải nằm dưới `contract-specifications` của module tương ứng, và generated tasks phải được kiểm tra thực tế.

### Những lỗi thường gặp

- Đưa file vào `src/test/contracts` nhưng `contractsDslDir` vẫn trỏ `src/test/resources/contracts`.
- Viết đúng tên thư mục nhưng áp plugin ở **root project** thay vì module producer.
- Đưa contract vào thư mục khác bởi custom source set nhưng không cập nhật configuration.
- Tệp là YAML nhưng đặt đuôi `.txt`, hoặc tệp Groovy bị đặt ở vị trí không được scan.
- Bật profile/condition Gradle khiến task không đọc thư mục hoặc không chạy.
- Chuyển code qua subproject khác mà để path tính theo root cũ.

**Giá trị kiểm chứng:** không chỉ đếm file trên disk; xác nhận **plugin đã parse chúng thành generated tests/stubs**.

## 8. Viết HTTP contract Groovy đầu tiên

Tạo file:

~~~text
src/test/resources/contracts/inventory/get-stock.groovy
~~~

Nội dung:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout có thể đọc tồn kho SKU-123'

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

Giải thích:

1. `request.method`, `url` và `headers` chỉ rõ HTTP request producer phải xử lý và stub phải match.
2. `response.status` xác định HTTP status cam kết.
3. `response.headers` xác định media type của response.
4. `response.body` mô tả JSON mẫu với `available` là boolean và `quantity` là number.
5. SCC sinh **generated producer tests** để gọi endpoint thật với các assertions tương ứng.
6. SCC cũng có thể sinh **WireMock mapping** phục vụ consumer stubs.

Đây là contract **cho một tình huống cụ thể**. Muốn kiểm tra `404 SKU_NOT_FOUND` hoặc tồn kho bằng 0, nên có contract/fixture bổ sung với request/response tương ứng.

## 9. Nếu chọn YAML contract thay Groovy

Cùng hành vi có thể viết thành:

~~~yaml
description: Checkout có thể đọc tồn kho SKU-123
name: get_stock_sku123

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

SCC Gradle plugin có thể xử lý Groovy hoặc YAML DSL theo khả năng của phiên bản đã dùng. Khối `contracts { ... }` **không biến một YAML file thành Gradle DSL**; plugin đọc nó như một **nguồn hợp đồng giao tiếp riêng**.

Lưu ý:

- `available: true` là JSON boolean; `available: 'true'` là string.
- `quantity: 12` là số; `quantity: '12'` là chuỗi.
- YAML đúng syntax chưa chắc đúng **schema SCC**; các key `request/response` phải nằm đúng cấp.
- Không thêm cùng một tình huống bằng cả YAML và Groovy vào cùng nơi nếu chỉ tạo **hai mappings/test trùng lặp**.
- Sử dụng schema/matcher tương ứng phiên bản SCC trong dự án; **phải mở generated test** để kiểm tra semantics.

## 10. testMode: chọn cách generated test gọi producer

Cấu hình:

~~~groovy
contracts {
    testMode = 'MockMvc'
}
~~~

`testMode` quyết định **chế độ sinh producer HTTP test**. Với Spring MVC, chế độ `MockMvc` thường được dùng để gọi controller thông qua Spring MVC test infrastructure. Với Spring WebFlux, một số phiên bản SCC hỗ trợ mode tương ứng **WebTestClient**. Với producer không dùng các mode trên, có thể cần mode HTTP thực hoặc cấu hình riêng.

| Producer stack | Hướng kiểm thử phổ biến | Điều cần xác minh |
|---|---|---|
| Spring MVC | `MockMvc` | Generated request dùng MockMvc/RestAssuredMockMvc và gọi controller thật |
| Spring WebFlux | `WebTestClient` nếu plugin version hỗ trợ | Generated test subscribe/gọi reactive handler thật |
| Server HTTP chạy trên port | Chế độ HTTP phù hợp | URL/port được inject đúng, không gọi mock ngoài |
| Message producer | Messaging verifier/test infrastructure | Generated test quan sát message do production code phát |

Tên giá trị `testMode` và cú pháp của nó **phụ thuộc dòng plugin**. Ví dụ `MockMvc` thể hiện cách cấu hình thường thấy trong Gradle Groovy DSL, nhưng khi dùng WebFlux/HTTP mode khác hãy đối chiếu tài liệu phiên bản chính xác thay vì tự suy ra giá trị enum từ tên framework.

Một lỗi cấu hình phổ biến: chọn `MockMvc` nhưng base class khởi tạo `WebTestClient`, hoặc chọn WebFlux test mode nhưng generated test không được nối đến WebFlux application context. Trong trường hợp đó, **contract có thể hợp lệ nhưng generated tests không compile/chạy**.

## 11. baseClassForTests: cầu nối tới ứng dụng producer thật

Với contract HTTP, generated test cần biết **cách gọi controller thật**. Khối Gradle:

~~~groovy
contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

Lớp `ContractTestBase` được đặt trong `src/test/java` của module producer.

Ví dụ cho Spring MVC:

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    WebApplicationContext context;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.webAppContextSetup(context);
    }
}
~~~

Trong cấu hình này, test base khởi tạo **Spring context của producer**; generated test sử dụng adapter tương ứng để gọi **controller production**, không phải fake controller do test tạo ra.

Điều phải tránh:

~~~java
// Phản ví dụ: base test tự trả chính response của contract.
@BeforeEach
void wrongSetup() {
    RestAssuredMockMvc.standaloneSetup(
        new FakeInventoryController()
    );
}
~~~

Nếu fake controller luôn trả `{"available":true,"quantity":12}`, generated test có thể **xanh giả** dù implementation Inventory thật đã bị sửa sai.

**Quy tắc thực hành:** chỉ mock/fake những dependency **ngoài phạm vi hành vi cần kiểm chứng**. Nếu hợp đồng bảo vệ logic tồn kho từ quantity tới available, không nên mock chính `InventoryService` để trả toàn bộ response DTO mẫu.

## 12. generated tests sẽ có dạng gì?

Sau khi đọc contract, SCC có thể sinh lớp test kế thừa base class và thực thi các assertions. Mã bên dưới là **mã giả minh họa ý tưởng**, không phải generated Java exact của mọi phiên bản:

~~~java
// MÃ GIẢ: tên lớp, API và assertions do SCC tạo tùy version.
class GetStockGeneratedTest extends ContractTestBase {

    @Test
    void verifyGetStock() {
        // Gửi GET /api/inventory/SKU-123 tới controller thật.
        // Kiểm tra HTTP 200 và Content-Type application/json.
        // Đọc JSON body của response.
        // Assert $.sku == "SKU-123".
        // Assert $.available == true.
        // Assert $.quantity == 12.
    }
}
~~~

Sau khi chạy bước sinh test, **xem generated source** để trả lời:

1. Đã sinh test cho `get-stock.groovy` chưa?
2. Generated class dùng base class đúng không?
3. Test dùng đúng test mode không?
4. Request method/URL/header có khớp?
5. Status, headers và JSON fields nào được assert?
6. Test source có được compile không?
7. JUnit test runner có **thực sự chạy test đó** không?

Một build thành công khi không có generated test **không phải bằng chứng** rằng producer đã tuân thủ contract.

## 13. Nhiều nhóm contract và base class mapping

Một producer lớn có thể có hai nhóm endpoint:

~~~text
contracts/
  inventory/
    get-stock.groovy
  reservations/
    create-reservation.groovy
~~~

Nhóm inventory có fixture riêng; nhóm reservations cần dữ liệu hoặc security setup khác. Nếu một `ContractTestBase` không phù hợp cho cả hai, một số phiên bản SCC Gradle plugin hỗ trợ cơ chế **mapping contract/generated package tới các base classes**.

Ví dụ ý tưởng cấu hình Gradle Groovy DSL thường thấy:

~~~groovy
contracts {
    baseClassMappings {
        baseClassMapping('.*inventory.*',
            'com.example.inventory.InventoryContractBase')
        baseClassMapping('.*reservations.*',
            'com.example.inventory.ReservationContractBase')
    }
}
~~~

**Cảnh báo:** ví dụ này mô tả cách phân nhóm **theo pattern**. Cú pháp `baseClassMappings/baseClassMapping` và đối tượng mà regex được so sánh (đường dẫn/package generated) cần được xác nhận theo **phiên bản plugin**. Nếu pattern không match, plugin có thể chọn base khác hoặc sinh test không compile.

Một số dòng plugin còn có tùy chọn `packageWithBaseClasses` để dùng convention dựa trên package chứa base classes:

~~~groovy
contracts {
    packageWithBaseClasses = 'com.example.inventory.contract'
}
~~~

Không cần bật đồng thời mọi phương án. Khi chỉ có một base class, `baseClassForTests` thường rõ ràng và dễ bảo trì hơn.

**Kiểm chứng bắt buộc:** xem generated test của **từng nhóm** để xác nhận lớp kế thừa đúng, không chỉ nhìn vào `build.gradle`.

## 14. Phân biệt settings.gradle và build.gradle trong multi-project

Một Gradle repository có thể chứa:

~~~text
platform/
  settings.gradle
  build.gradle
  inventory-service/
    build.gradle
    src/test/resources/contracts/...
  pricing-service/
    build.gradle
    src/test/resources/contracts/...
  checkout-service/
    build.gradle
    src/test/java/...
~~~

Trong `settings.gradle` có thể include:

~~~groovy
rootProject.name = 'commerce-platform'

include 'inventory-service'
include 'pricing-service'
include 'checkout-service'
~~~

`settings.gradle` khai báo **project topology**, không phải nơi thông thường để định nghĩa contract HTTP. Cấu hình `contracts { ... }` nên được áp dụng ở **module producer thực sự sở hữu contract và code**:

~~~groovy
// Trong inventory-service/build.gradle
plugins {
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

contracts {
    contractsDslDir = file('src/test/resources/contracts')
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

Đoạn trên là **trích cấu hình**, chưa phải build script hoàn chỉnh. Nếu plugin version được khai báo tập trung ở root bằng `apply false` hoặc version catalog, cú pháp apply tại subproject có thể khác.

Với multi-project Gradle:

- `project.file(...)` lấy đường dẫn tương đối từ subproject;
- generated test output cũng thuộc subproject;
- stubs JAR của Inventory mang group/artifact/version **của Inventory**;
- Checkout là **consumer**, thường không cần producer contract generation plugin chỉ để dùng Stub Runner;
- tránh áp plugin cho mọi module bằng `allprojects` nếu chỉ một vài module có contract.

## 15. Source sets và vị trí generated output

Trong một build bình thường, Spring Cloud Contract plugin sinh **Java test sources** và stubs vào những thư mục dưới `build/`. Đường dẫn chính xác tùy phiên bản và cấu hình plugin.

Một số phiên bản có option điều chỉnh nơi generated test sources được xuất ra, ví dụ ý tưởng:

~~~groovy
contracts {
    generatedTestSourcesDir = file('build/generated-contract-tests')
}
~~~

**Không tự thêm đoạn này vào production build trước khi xác nhận** extension của version đang dùng có đúng property, và task compile/test đã nhận thư mục đó làm generated test source. Vị trí mặc định thường an toàn hơn nếu dự án chưa có yêu cầu đặc biệt.

Quy tắc:

1. **Contract source** thuộc source control, thường ở `src/test/resources/contracts`.
2. **Generated test Java** là output của build, **không cần commit** vào source tree trong workflow thông thường.
3. **Stub mappings** cũng là generated output, được đóng gói vào artifact theo task/pipeline.
4. Không dùng `build/generated...` làm nơi viết contract nguồn, vì `clean` có thể xóa toàn bộ.
5. Không cấu hình generated sources trùng với `src/test/java` mà không có chủ ý, dễ gây file stale hoặc conflict.

Một lỗi hay gặp: Gradle task sinh test tạo source thành công, nhưng `test` task không compile/run chúng do source set wiring bị thay đổi bởi customization khác. **Generated file có mặt chưa đủ; test runner phải thực thi.**

## 16. Gradle tasks: tìm đúng task thay vì đoán

Sau khi plugin được áp dụng, có thể kiểm tra các tasks bằng:

~~~bash
# Dùng Gradle Wrapper của dự án.
./gradlew tasks --all

# Xem dependency của task mà không thực thi.
./gradlew test --dry-run

# Chạy test task đã cấu hình.
./gradlew clean test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat tasks --all
.\gradlew.bat test --dry-run
.\gradlew.bat clean test
~~~

Một số dòng Spring Cloud Contract Gradle plugin có tasks liên quan tới:

- `generateContractTests` — sinh producer tests;
- `generateClientStubs` — sinh client/HTTP stubs;
- `verifierStubsJar` — đóng gói stubs artifact;
- `test` hoặc test task được cấu hình — thực thi generated tests.

**Tên task và quan hệ giữa các task phải được kiểm tra ở dự án/version thực**. Không áp dụng một tên task từ bài viết cũ nếu `tasks --all` không có nó. Tương tự, `--dry-run` cho biết task graph dự kiến, **không chứng minh** test thực thi thành công.

Khi chạy `./gradlew clean test`, hãy kiểm tra:

1. Log generation đã đọc các contract;
2. Generated source được compile;
3. Test runner đã chạy số test mong đợi;
4. Assertions thực sự kiểm tra producer thật;
5. Build không bị filter/skip generated contract tests.

## 17. Base test và testMode phải phù hợp nhau

Một số tổ hợp cấu hình có vẻ hợp lý nhưng thực tế không dùng được:

| Test mode | Base test | Kết quả |
|---|---|---|
| `MockMvc` | `RestAssuredMockMvc.webAppContextSetup(...)` với MVC context thật | Thường là hướng phù hợp cho Spring MVC |
| `MockMvc` | Chỉ thiết lập `WebTestClient` | Có thể compile/test fail do adapter không khớp |
| `WebTestClient` | WebFlux test infrastructure thích hợp | Phù hợp nếu SCC version hỗ trợ và được nối đúng |
| HTTP server mode | Base test không khởi động server/không cung cấp port | Generated tests có thể không kết nối được |
| Messaging contract | Base test chỉ cấu hình MockMvc, không có message verifier/trigger | Message test không quan sát được output |

Đừng dùng một class `ContractTestBase` rỗng rồi cho rằng plugin tự biết cách chạy tất cả producer stacks. Base test phải cung cấp **đúng điểm kết nối** mà generated source cần.

Đối với WebFlux hoặc cấu hình HTTP đặc biệt, cách chắc chắn nhất là:

- chọn test mode theo tài liệu version;
- sinh thử generated source;
- xem imports, method calls và class extends;
- chuẩn bị base class đúng;
- chạy test và xác nhận response của **producer thật**.

## 18. Custom assertions trong contract và base test

Contract có thể cần kiểm tra quy tắc mà equality/regex thông thường không mô tả tốt, ví dụ `quantity` phải nằm trong đoạn từ 0 tới 1000.

Groovy DSL có thể dùng custom command:

~~~groovy
response {
    status OK()

    body(
        sku: 'SKU-123',
        quantity: 12
    )

    bodyMatchers {
        jsonPath('$.quantity',
            byCommand('assertValidQuantity($it)'))
    }
}
~~~

Lúc này base test cần cung cấp method:

~~~java
public void assertValidQuantity(Object actual) {
    if (!(actual instanceof Number)) {
        throw new AssertionError(
            "quantity phải là JSON number");
    }

    int quantity = ((Number) actual).intValue();

    if (quantity < 0 || quantity > 1000) {
        throw new AssertionError(
            "quantity ngoài [0, 1000]: " + quantity);
    }
}
~~~

Đoạn này là minh họa cách gắn **Groovy contract DSL** với **baseClassForTests**. Nếu type JSON có decimal không nguyên, chuyển sang `intValue()` có thể làm mất thông tin; khi đó nên dùng `BigDecimal` và kiểm tra kiểu/số nguyên theo yêu cầu.

Trong Gradle, phần quan trọng vẫn là generated tests **kế thừa đúng base**. Nếu `baseClassForTests` trỏ sai package hoặc method không visible, test có thể lỗi compile. Đừng bỏ matcher chỉ để làm build xanh; sửa base class hoặc matcher theo cam kết được thống nhất.

## 19. Hợp đồng HTTP POST: kiểm tra request body khi sinh stub

Một API tạo reservation có request JSON:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":2}
~~~

Groovy contract minh họa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url '/api/reservations'

        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-123',
            quantity: 2
        )
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
        }

        body(
            reservationId: 'R-1001',
            status: 'RESERVED'
        )
    }
}
~~~

Trong **generated producer test**, request body mẫu được gửi tới implementation. Trong **generated WireMock stub**, phần request của contract tạo các **điều kiện matching**; phần response trở thành body/status/header trả về cho consumer.

Một mapping gần tương đương về ý tưởng:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {"contains": "application/json"}
    },
    "bodyPatterns": [
      {"equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"}
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

Đây là **mapping minh họa**, không phải output chính xác của mọi SCC version. Sau build, phải mở **mapping thực tế** để xem generator chọn `equalToJson`, `matchesJsonPath`, `body` hay `jsonBody`. Không suy ra tất cả field đều được kiểm tra chặt chỉ từ việc file contract có body.

## 20. Message contracts trong cùng cấu hình Gradle

Dù bài tập trung vào khối `contracts`, module Spring Cloud Contract còn hỗ trợ **hợp đồng thông điệp**. Một contract messaging có thể mô tả:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

Với contract này:

- Plugin vẫn cần tìm file theo `contractsDslDir`.
- Generated test cần **triggerInventoryChanged()** trong test base hoặc test support phù hợp.
- Test phải quan sát event được **producer production code** phát ra, qua messaging test infrastructure thích hợp.
- `sentTo` là destination được verifier quan sát; không tự chứng minh Kafka partition key, Rabbit routing key hoặc broker production đã nhận event.
- Consumer dùng Stub Runner/message test infrastructure khi phiên bản hỗ trợ, không coi message contract là một HTTP WireMock mapping.

**Phản ví dụ:** base test tự gửi JSON mẫu vào test binder trong `triggerInventoryChanged()` rồi generated test xanh, trong khi application service thật không phát gì. Đây là test xanh giả. Base test nên gọi **production use case** để output message được sinh bởi code thực.

## 21. Sinh HTTP stubs và stubs JAR trong Gradle

Mục tiêu của nhánh stubs:

~~~text
contracts/*.groovy hoặc *.yml
    -> SCC generator
    -> HTTP WireMock mappings + response body files
    -> JAR classifier "stubs"
    -> artifact repository
    -> Stub Runner của consumer
~~~

Ví dụ tọa độ artifact:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.3.0-rc1
classifier:  stubs
type:        jar
~~~

Một tên file minh họa:

~~~text
inventory-service-1.3.0-rc1-stubs.jar
~~~

Với Gradle, plugin có thể cung cấp task như `verifierStubsJar` để đóng gói artifacts. Tuy nhiên, **tạo task/JAR không tự động đồng nghĩa đã publish artifact** vào Maven local hoặc repository dùng chung.

Cần kiểm tra:

1. `generateClientStubs` hoặc task tương ứng đã đọc đúng contracts;
2. Có mapping cho mỗi scenario quan trọng;
3. Body files (nếu dùng) đã được đóng gói;
4. JAR có classifier `stubs` và group/artifact/version mong muốn;
5. Publication (nếu dùng `maven-publish`) đã đính kèm đúng stub artifact;
6. Consumer tải **đúng version ứng viên**, không lấy artifact cũ từ cache.

### Kiểm tra JAR

Sau khi build thực tế sinh artifact:

~~~bash
# Thay tên file bằng output thật trong build/libs.
jar tf build/libs/inventory-service-1.3.0-rc1-stubs.jar
~~~

Vị trí file và tên artifact có thể thay đổi. `jar tf` chỉ kiểm tra **entries trong JAR**, không xác nhận generated producer tests đã chạy. Cần giữ cả test report và danh sách mappings.

## 22. Publishing bằng maven-publish: phân biệt phần Gradle với SCC

Gradle `maven-publish` chịu trách nhiệm đưa artifact lên repository, trong khi `contracts { ... }` chịu trách nhiệm cấu hình nguồn/generation của SCC.

Ví dụ hướng tổ chức:

~~~groovy
plugins {
    id 'maven-publish'
}

// Ý tưởng: publication của producer cần bao gồm
// application artifact và stubs JAR từ task SCC tương ứng.
// Tên task, cách attach artifact và publication syntax
// phải xác minh với Gradle/SCC plugin version thực tế.
~~~

Không nên đưa một cấu hình publish **đoán tên task** vào pipeline mà chưa kiểm tra `tasks --all` và publish metadata. Hãy thiết kế publication theo các bước:

1. Khai báo repository và credentials bằng secret manager/CI variables;
2. Xác định chính xác task `stubsJar`/`verifierStubsJar` đang tồn tại;
3. Gắn output task đó vào publication như **classifier stubs**;
4. Dùng candidate version không bị ghi đè giữa các PR/commit;
5. Tạo stage publish chỉ khi producer verification đạt;
6. Kiểm tra từ consumer job rằng artifact được resolve đúng tọa độ.

**Không chứa token thực trong `build.gradle` hoặc commit credentials lên Git.** Stub JAR chỉ nên có fixture tổng hợp, không có dữ liệu khách hàng hay bí mật production.

## 23. Consumer dùng Stub Runner với artifact sinh từ Gradle

Một Checkout Service có thể kiểm tra client thật bằng stub của Inventory:

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
    void consumerUsesInventoryStub() {
        // Gọi HTTP client thực của Checkout tới http://localhost:18081
        // rồi kiểm tra deserialize và business handling.
    }
}
~~~

`LOCAL` giả định stub đã được cài vào nguồn local mà Stub Runner hỗ trợ. Trong CI nhiều repository, thường dùng repository REMOTE có tọa độ và credentials tương ứng.

Đừng chỉ chạy WireMock rồi assert raw HTTP response bằng một test helper nếu mục đích là xác nhận **Checkout client production**. Client thật cần được kiểm chứng về method, URL, headers, serialization, deserialization và error mapping.

Một bài consumer test xanh khi dùng **stub của commit trước** không chứng minh tương thích với API của **commit ứng viên**.

## 24. Contracts được giữ ngoài repository producer

Một số tổ chức để contracts trong repository hoặc artifact riêng. Trong trường hợp đó, cấu hình không còn đơn giản là đọc `src/test/resources/contracts`.

Các khái niệm cần phân biệt:

- **Local contracts:** mã nguồn contract nằm trong module producer.
- **External contracts:** contract được lấy từ repository/nguồn khác theo configuration/contract dependency.
- **Contract coordinates/path:** xác định nguồn, version và vùng contract của producer.
- **Contracts mode:** cách công cụ tìm contracts trong nguồn local, artifact hoặc remote repository tùy phiên bản.

SCC có những cơ chế cấu hình nâng cao cho external contracts, nhưng **tên extension/property của chúng phụ thuộc phiên bản**. Không tự đoán cú pháp `contractDependency`, `contractsMode` hoặc `contractsRepositoryUrl` rồi dùng vào một `build.gradle` thật nếu chưa đối chiếu reference/version.

Điều cần giữ nguyên về mặt kiểm chứng:

1. Producer build tải đúng **contract revision** được phép.
2. Generated test bám vào contract đó.
3. Stub artifact được tạo từ **cùng revision**.
4. Consumer dùng chính artifact/revision ứng viên.
5. CI lưu nguồn và commit contract nếu tách repository.

Với bài thực hành đầu tiên, nên bắt đầu bằng **local contractsDslDir** để giảm số biến gây lỗi.

## 25. Kotlin DSL build.gradle.kts có gì khác?

Nếu dự án dùng `build.gradle.kts`, cần phân biệt:

| Gradle Groovy DSL | Gradle Kotlin DSL |
|---|---|
| `id 'org.springframework.cloud.contract' version '...'` | `id("org.springframework.cloud.contract") version "..."` |
| `file('src/test/resources/contracts')` | `file("src/test/resources/contracts")` |
| Gán property với cú pháp Groovy | Gán property theo Kotlin/property API mà plugin version expose |
| Groovy closure `contracts { ... }` | Kotlin lambda/type-safe accessor hoặc `configure<...>` nếu extension chưa có accessor |

Minh họa phần khai báo plugin (các version là placeholder):

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "BOOT_VERSION"
    id("org.springframework.cloud.contract") version "CONTRACT_PLUGIN_VERSION"
}
~~~

Đối với khối `contracts` trong Kotlin DSL, **không nên máy móc đổi mọi dấu nháy Groovy thành nháy kép**. Gradle extension có thể expose setter dạng property, phương thức Java hoặc cần `configure<ContractVerifierExtension>`, tùy phiên bản plugin và khả năng type-safe accessors.

Cách làm an toàn:

1. Kiểm tra Spring Cloud Contract Gradle plugin documentation **đúng phiên bản** có ví dụ Kotlin DSL hay không.
2. Kiểm tra Gradle Kotlin DSL accessors/IDE autocomplete cho `contracts` extension.
3. Dùng đúng property types thay vì đoán `.set(...)` cho mọi thuộc tính.
4. Thực thi generation ở dự án thử rồi xem generated test/stub.
5. Không trộn code của `build.gradle` vào `build.gradle.kts` nguyên văn.

Nếu khóa học/dự án đã chọn **Groovy Gradle DSL**, ví dụ chính của bài ở phần 6 là đủ để hiểu cách cấu hình extension.

## 26. Kiểm tra version resolution và plugin classpath

Một lỗi phổ biến là dependency version đã được BOM điều phối nhưng **Gradle không resolve được plugin**:

~~~text
Plugin [id: 'org.springframework.cloud.contract',
        version: '...'] was not found
~~~

Đây là lỗi **plugin resolution**, không phải lỗi syntax contract.

Một số nguồn gây lỗi:

- Version plugin không tồn tại hoặc không tương thích;
- `pluginManagement.repositories` trong `settings.gradle` bị giới hạn;
- Build đang offline nhưng plugin chưa có cache;
- Corporate proxy/private repository chặn truy cập;
- Gradle/Java toolchain quá cũ hoặc quá mới so với plugin.

Cách chẩn đoán:

~~~bash
./gradlew --version
./gradlew help --stacktrace
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Lệnh thứ ba giúp quan sát **test dependencies**, nhưng không thay thế việc kiểm tra **plugin classpath/plugin resolution**. Cần nhìn lỗi Gradle ở đúng phase: plugin lookup, dependency resolution, compile test, execution hay packaging.

Đừng cố sửa `contractsDslDir` khi Gradle chưa áp dụng được plugin, và đừng sửa version plugin bằng cách xóa contract tests khỏi build.

## 27. Khi Gradle build xanh nhưng không có contract tests

Một trong những tình huống nguy hiểm nhất:

~~~text
./gradlew clean test
BUILD SUCCESSFUL

... nhưng không có generated contract test nào đã chạy.
~~~

Nguyên nhân có thể là:

- `contractsDslDir` trỏ tới thư mục rỗng/sai module;
- contract chưa được commit hoặc có extension không được nhận diện;
- plugin không được áp dụng ở module producer;
- Gradle test task đã được tùy chỉnh bỏ bước generation;
- generated source set không nối vào compile/test task;
- `test` đang bị disable, exclude hoặc filter;
- pipeline chạy `:some-other-module:test` thay vì `:inventory-service:test`;
- repo có contract nhưng chúng không parse thành generated test như mong đợi.

**Không kết luận SCC mặc định luôn fail khi không có contract.** Hành vi tùy version/configuration. Với producer bắt buộc có contracts, CI nên xác nhận **số contract được parse > 0** và **số generated tests được thực thi > 0**.

Một guard sơ bộ có thể đếm file dưới source directory, nhưng số file **không chứng minh** plugin đã đọc thành công. Bằng chứng mạnh hơn là generated source/test report và stub mapping count.

## 28. Trường hợp hợp đồng sai hoặc base class sai

| Hiện tượng | Tầng lỗi | Cách khắc phục |
|---|---|---|
| Groovy contract thiếu `}` | Parsing | Sửa DSL và đọc lỗi dòng/cột |
| YAML đặt `status` sai indentation | Parsing/schema | Sửa cấu trúc YAML |
| DSL tham chiếu body file không tồn tại | Resource resolution | Sửa đường dẫn fixture |
| JSONPath matcher trỏ field không có | Generation/test semantics | Sửa body/matcher theo contract thật |
| Generated test không tìm thấy `ContractTestBase` | Compilation | Sửa `baseClassForTests`, package/test source |
| Test base dùng adapter khác `testMode` | Compilation/execution | Đồng bộ test mode và base initialization |
| Test chạy nhưng trả 404 | Producer verification | Kiểm tra endpoint, context và request |
| Test xanh dù producer đổi field | Test base fake response hoặc test không chạy | Kiểm tra generated source và mutation |
| Có mappings nhưng stubs JAR trống | Packaging | Xem task graph và artifact inputs |
| Consumer dùng stub cũ | Resolution/cache | Ghim exact candidate version/commit |

**Định vị lỗi theo tầng** giúp tránh những “cách sửa” sai, ví dụ xóa contract hoặc bỏ generated tests khi chỉ bị lỗi `baseClassForTests`.

## 29. Test âm tính để xác nhận cấu hình Gradle có hiệu lực

Một cấu hình build đáng tin phải **bị lỗi khi producer vi phạm hợp đồng**. Trong nhánh thử nghiệm:

1. Bắt đầu với contract GET inventory đúng và producer test xanh.
2. Thay code controller/service để trả `available: false` khi contract yêu cầu `true`.
3. Chạy generated producer tests.
4. **Kỳ vọng:** test đỏ ở body assertion.
5. Khôi phục code production.
6. Tạm di chuyển contract ra khỏi thư mục `contractsDslDir`.
7. Chạy build/CI gate, xác nhận module producer bắt buộc có contract **bị chặn vì không có contract**.
8. Khôi phục contract và chạy lại tests.

Nếu **thay đổi producer không làm test đỏ**, kiểm tra hai khả năng:

- Test không được sinh hoặc không được chạy;
- Test base có **fake controller/mock service** trả chính dữ liệu mẫu của contract.

Nếu **xóa contract mà pipeline vẫn xanh**, cần guard về số contract/test; không được xem đây là bằng chứng API đã được bảo vệ.

## 30. Bước kiểm tra stub artifact sau Gradle build

Có contract source và producer test chạy tốt **chưa đủ** để consumer tải được stub. Cần xác nhận:

1. Task generation đã tạo WireMock mappings cho HTTP contracts.
2. Các file body tham chiếu (nếu có) đã được copy/đóng gói đúng.
3. Stubs JAR thực sự tồn tại ở output của module producer.
4. JAR mang classifier `stubs` và version ứng viên chính xác.
5. Artifact đã được install/publish vào repository mà Stub Runner đọc.
6. Consumer test dùng tọa độ artifact chính xác, không dùng `latest`/`+` mà không kiểm soát.
7. Consumer sử dụng **HTTP client/handler thật** và assert kết quả.
8. Test còn có lỗi nghiệp vụ quan trọng, không chỉ happy path.

Nhớ phân biệt **business 404** được contract mô tả với **WireMock unmatched request 404** do client gửi sai URL/header/body. Một consumer test chỉ assert status 404 có thể che lỗi request serialization.

## 31. CI/CD: nối Gradle producer test với consumer Stub Runner

~~~mermaid
flowchart TD
    A["Producer PR: code + contract + build.gradle"] --> B["Gradle resolve plugin/dependencies"]
    B --> C["Generate + compile contract tests"]
    C --> D{"Tests được thực thi và đạt?"}
    D -- "Không" --> X["BLOCK"]
    D -- "Có" --> E["Generate mappings + package stubs JAR"]
    E --> F["Publish candidate artifact có version duy nhất"]
    F --> G["Consumer tests dùng Stub Runner và client thật"]
    G --> H{"Consumer tương thích?"}
    H -- "Không" --> X
    H -- "Có" --> I["Tiếp tục release gates"]
~~~

Trong producer Gradle:

~~~bash
./gradlew clean test
~~~

Đây là lệnh tham khảo **chỉ chạy những task đã được cấu hình vào graph**. Stage packaging/publish có thể cần task riêng. Với multi-project:

~~~bash
./gradlew :inventory-service:clean :inventory-service:test
~~~

Tên subproject chỉ là ví dụ; dùng tên thật từ `settings.gradle`.

**Các cổng cần có:**

| Cổng | Bằng chứng |
|---|---|
| Contract discovery | Những contract mong đợi được nhận diện |
| Generated tests | Test source tồn tại và compile |
| Producer verification | Test report có **executed tests > 0** và assertions đạt |
| Stub packaging | Mappings/JAR có nội dung, đúng classifier |
| Candidate provenance | Version + commit SHA không nhập nhằng |
| Consumer verification | Stub Runner dùng artifact ứng viên, client consumer thật chạy |
| Breaking-change detection | Consumer tests thất bại khi response schema mới không tương thích |

CI nên ghi lại **Gradle Wrapper version, JDK, Spring Boot/Cloud/Contract versions, test mode, số test chạy, artifact coordinates và commit**. Không dùng `--offline` trên CI nếu artifact ứng viên có thể chưa có trong cache, trừ khi cơ chế phân phối đã được kiểm soát.

## 32. Bài thực hành A — Thiết lập Gradle contracts extension

**Mục tiêu:** producer Gradle nhận hợp đồng và sinh test chạy được.

1. Chuẩn bị một ứng dụng Inventory Spring MVC với endpoint GET.
2. Chọn bộ version JDK/Gradle/Boot/Cloud/Contract tương thích.
3. Áp dụng `org.springframework.cloud.contract` plugin.
4. Khai báo `spring-cloud-starter-contract-verifier` test dependency.
5. Thêm:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

6. Tạo `ContractTestBase` kết nối tới Spring MVC application context thật.
7. Viết `inventory/get-stock.groovy` ở phần 8.
8. Dùng `./gradlew tasks --all` và `./gradlew clean test` trong môi trường dự án.
9. Kiểm tra generated source, test report, status/body assertions.

**Đầu ra:** `build.gradle`, contract, base test và bằng chứng generated test thực thi.

## 33. Bài thực hành B — Đổi nguồn contract và phát hiện cấu hình sai

1. Di chuyển contract từ `src/test/resources/contracts` sang `contract-specifications` trong nhánh thử.
2. Giữ `contractsDslDir` cũ, quan sát plugin không đọc được contract theo mong đợi.
3. Đổi cấu hình thành:

~~~groovy
contracts {
    contractsDslDir = file('contract-specifications')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

4. Chạy lại generation và xác nhận generated test xuất hiện.
5. Cố tình đặt `baseClassForTests` sai package: compile test phải báo lỗi nếu generated test thực sự dùng base.
6. Khôi phục base class đúng.
7. Đổi response production `available` từ true sang false và kiểm tra test đỏ.
8. Khôi phục code và chạy lại test xanh.

**Đầu ra:** bảng mô tả lỗi discovery, compilation và verification cùng phương án sửa đúng tầng.

## 34. Bài thực hành C — Sinh stub và kiểm tra consumer

1. Sinh HTTP stub mappings từ contract Inventory.
2. Đóng gói stubs JAR bằng task plugin tương ứng.
3. Kiểm tra nội dung JAR và candidate version.
4. Install/publish đúng repository.
5. Tạo Checkout consumer test dùng Stub Runner tải Inventory candidate artifact.
6. Cho client thật gọi `GET /api/inventory/SKU-123` và assert DTO.
7. Thêm contract/error case `404 SKU_NOT_FOUND` và test client phân biệt business 404 với unmatched WireMock 404.
8. Trong nhánh thử, đổi field `available` thành `inStock` ở producer và contract, tạo stub ứng viên mới.
9. Chạy consumer cũ với **artifact mới** để phát hiện breaking change.
10. Lưu kết quả producer/consumer cùng tọa độ stub và commit.

**Đầu ra:** generated mapping, JAR, Stub Runner logs, consumer test report và kế hoạch migration nếu có breaking change.

## 35. Checklist review cấu hình Gradle

- [ ] Dùng Gradle Wrapper và JDK tương thích với Spring Boot/Cloud/Contract.
- [ ] Plugin `org.springframework.cloud.contract` đã được áp dụng ở **đúng producer module**.
- [ ] Version plugin phù hợp với BOM/dependency version đã chọn.
- [ ] `contractsDslDir` trỏ đúng nơi chứa Groovy/YAML contracts.
- [ ] Contract files có cấu trúc DSL hợp lệ, không bị bỏ sót do extension/đường dẫn.
- [ ] `testMode` phù hợp với Spring MVC/WebFlux/HTTP stack.
- [ ] `baseClassForTests` chỉ đúng package và class tồn tại trong test sources.
- [ ] Base test kết nối tới **producer code thật**, không tự trả response contract bằng fake.
- [ ] Nếu có nhiều nhóm, base class mapping được kiểm chứng bằng generated source.
- [ ] Generated Java sources thực sự được compile và chạy trong Gradle test task.
- [ ] **Số contract test executed > 0** với module producer bắt buộc có hợp đồng.
- [ ] Không có `test.enabled = false`, exclude/filter hoặc profile làm bỏ qua generated tests.
- [ ] Mappings/body files được sinh và có trong stubs JAR.
- [ ] Candidate stubs JAR có group/artifact/version/classifier chính xác.
- [ ] Publication/repository có thể phục vụ consumer Stub Runner.
- [ ] Consumer tests dùng **stub ứng viên và client thật**.
- [ ] CI chặn khi producer test fail, không có contract hoặc stubs artifact rỗng.
- [ ] Thay đổi breaking ở API/message đã được thử với consumer cũ.
- [ ] Không commit credentials, secret hoặc dữ liệu khách hàng thật vào contract fixture.
- [ ] Build logs/test reports đủ để truy vết version, commit, task và lỗi theo từng tầng.

## 36. Câu hỏi tự kiểm tra

**1. `contracts { ... }` trong `build.gradle` có phải một HTTP contract không?**

Không. Nó cấu hình **Gradle plugin** cách tìm/sinh test/stub. Hợp đồng HTTP nằm trong các tệp Groovy/YAML mô tả request/response.

**2. `contractsDslDir` dùng làm gì?**

Chỉ thư mục contract source mà plugin sẽ đọc. Nếu trỏ sai, dự án có thể không sinh được contract tests dù trên disk vẫn có file ở nơi khác.

**3. `baseClassForTests` có vai trò gì?**

Giúp generated tests truy cập môi trường test và setup để gọi producer thật, hoặc helper/assertion mà contract cần. Base class sai tên/package/test mode sẽ làm generated tests compile/run lỗi.

**4. Vì sao chọn `testMode` sai nguy hiểm?**

Vì generated tests có thể dùng HTTP adapter khác base class. Contract parse được nhưng không kiểm chứng được implementation producer, hoặc sinh test không chạy.

**5. `./gradlew clean test` thành công có đủ để tuyên bố contract được kiểm chứng không?**

Chưa. Phải xem **contract discovery, generated source và executed test count**. Build có thể xanh khi không có contract hoặc generated tests bị skip tùy cấu hình.

**6. Tại sao cần xem stubs JAR sau khi producer test xanh?**

Vì mappings/fixture có thể chưa được đóng gói hoặc artifact chưa publish. Consumer Stub Runner chỉ tải được artifact có nội dung ở đúng repository/version.

**7. Có thể dùng cả Groovy contract và YAML contract trong cùng dự án không?**

Có thể khi plugin hỗ trợ và chúng mô tả **những tình huống khác nhau**. Không nên tạo hai contract giống hệt chỉ vì hai cú pháp, vì có thể sinh test/mapping trùng.

**8. Nếu producer và contract cùng đổi `available` sang `inStock` rồi generated test xanh, liệu consumer đã an toàn?**

Không. Consumer cũ có thể vẫn đọc `available`. Cần sinh **candidate stubs JAR của commit mới** và chạy consumer tests để đánh giá tương thích.

**9. Vì sao không nên áp plugin cho mọi subproject nếu chỉ một service là producer?**

Vì có thể tạo task/generation không cần thiết, dẫn đến nhầm **zero contract** hoặc source path, và làm khó xác định module nào thực sự cần verification.

## 37. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): quy trình Contract Verifier, Groovy/YAML DSL, producer test và Stub Runner.
- [Spring Cloud Contract — Gradle Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): plugin, `contracts` extension, task generation và stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML HTTP/message contracts và matchers.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): request/response structure.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): consumer tests với artifact stubs.
- [Gradle — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts.html): Gradle Groovy/Kotlin DSL và extension.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): source project, subproject và task targeting.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publication và repository.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): xác minh mappings sinh từ HTTP contracts.

**Lưu ý phiên bản:** Các thuộc tính mở rộng của `contracts`, tên và quan hệ task Gradle, test mode, generated source directories, cách lựa chọn base classes và publication artifacts có thể đổi theo **Spring Cloud Contract plugin version**. Các khối Gradle dùng placeholder version trong bài **không thể chạy nguyên văn**; phải thay bằng phiên bản tương thích thực tế. Nội dung minh họa đường đi kỹ thuật và điểm kiểm tra, **không phải báo cáo rằng các lệnh build đã được chạy**.

---

**Điểm cần nhớ:** Khối `contracts { ... }` trong Gradle quyết định **SCC đọc contract ở đâu và sinh producer tests bằng cách nào**. `contractsDslDir` chọn nguồn Groovy/YAML, `testMode` chọn adapter kiểm thử, `baseClassForTests` nối generated tests với **producer implementation thật**. Sau khi producer tests đạt, cần kiểm tra mappings/stubs JAR và dùng **Stub Runner với artifact ứng viên đúng commit** để xác nhận consumer. Một pipeline đáng tin phải chứng minh từng khâu thực sự chạy, không chỉ thấy Gradle báo `BUILD SUCCESSFUL`.
