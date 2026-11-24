# Cấu hình thư mục hợp đồng và đầu ra được sinh

## Mục tiêu bài học

**Spring Cloud Contract Verifier** biến các hợp đồng **Groovy DSL** hoặc **YAML DSL** thành những kiểm thử có thể thực thi phía **producer**. Cùng nguồn hợp đồng có thể dùng để tạo **stub** nhằm cho **consumer** kiểm thử thông qua **Stub Runner**. Trong CI, chuỗi này giúp phát hiện những thay đổi HTTP hoặc thông điệp không còn phù hợp với hành vi đã thống nhất.

Tuy nhiên, Verifier không thể kiểm tra một hợp đồng mà nó **không tìm thấy**; producer cũng không được xác minh nếu generated test **không được biên dịch và chạy**. Vì thế, cấu hình thư mục nguồn và thư mục đầu ra là một phần quan trọng của quy trình kiểm thử, không chỉ là lựa chọn sắp xếp tệp.

Sau bài học, bạn có thể:

- Phân biệt **thư mục chứa hợp đồng**, **thư mục kiểm thử sinh ra**, **tài nguyên sinh ra** và **stub artifact**.
- Thiết lập hoặc nhận diện thư mục Groovy/YAML DSL trong dự án Maven và Gradle.
- Giải thích cách **base test class**, cấu trúc thư mục tương đối và cấu hình sinh test liên hệ với nhau.
- Kiểm tra generated tests, mapping và stub được tạo từ đúng tập hợp hợp đồng.
- Xử lý các trường hợp dùng repository hợp đồng độc lập hoặc di chuyển nguồn hợp đồng.
- Thiết kế bước kiểm tra CI ngăn tình huống build xanh vì **không có hợp đồng nào được kiểm chứng**.

## 1. Bốn nhóm đường dẫn không được nhầm lẫn

Hãy nhìn quy trình tổng thể:

~~~mermaid
flowchart TD
    A["Nguồn hợp đồng Groovy/YAML<br/>contracts root"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer tests<br/>generated test sources"]
    B --> D["Generated resources<br/>nếu generator cần"]
    B --> E["Stub/mapping<br/>generated stubs"]
    C --> F["Biên dịch và chạy test trên producer"]
    D --> F
    E --> G["Đóng gói stub artifact có version"]
    F --> H{"Producer test PASS?"}
    H -->|Không| X["Dừng: không đủ bằng chứng"]
    H -->|Có| I["Release gate"]
    G --> I
    I --> J["Consumer tải stub qua Stub Runner"]
    J --> K["Consumer integration tests"]
~~~

Một dự án thường có các đường dẫn sau:

| Nhóm | Mục đích | Ví dụ thường gặp |
| --- | --- | --- |
| **Contracts source** | Chứa tệp `.groovy`, `.yml` hoặc `.yaml` mà công cụ đọc | `src/test/resources/contracts` |
| **Generated test sources** | Chứa mã nguồn kiểm thử phía producer do Verifier tạo | `target/generated-test-sources/contracts` hoặc `build/generated-test-sources/contracts` |
| **Generated test resources** | Tài nguyên phụ trợ được generator hoặc test dùng nếu có | Một thư mục dưới `target` / `build` |
| **Generated stubs/artifact** | Mapping/response được đóng gói để consumer dùng | Các file trong vùng build và artifact classifier `stubs` |

Các tên ở bảng là **ví dụ bố cục phổ biến**, không phải cam kết rằng mọi phiên bản Maven/Gradle plugin đều sinh ra chính xác cùng tên thư mục. Đường dẫn hiệu lực do **phiên bản plugin, cấu hình build và hệ thống build** quyết định. Hãy đối chiếu log và đầu ra của dự án đang sử dụng.

Đặc biệt, đường dẫn tệp `contracts/orders/get_order.yml` **không phải** HTTP endpoint. Endpoint nằm **trong nội dung hợp đồng**, chẳng hạn `GET /api/orders/ORD-1001`.

## 2. Bố cục dự án producer dễ hiểu

Với một dự án Order Service có các hợp đồng HTTP và thông điệp, cách tổ chức tham khảo:

~~~text
order-service/
├── pom.xml                     # Hoặc build.gradle
├── src/
│   ├── main/
│   │   └── java/
│   └── test/
│       ├── java/
│       │   └── com/example/orders/contract/
│       │       ├── OrderHttpContractBase.java
│       │       └── OrderMessageContractBase.java
│       └── resources/
│           └── contracts/
│               └── orders/
│                   ├── http/
│                   │   ├── get_paid_order.yml
│                   │   └── get_missing_order.groovy
│                   └── messaging/
│                       └── order_paid.groovy
└── target/ hoặc build/         # Sinh ra khi chạy build
~~~

Ở đây:

1. `src/test/resources/contracts` là **root nguồn hợp đồng** thường dùng.
2. `orders/http` và `orders/messaging` là **cách tổ chức của dự án**, không phải tên hai thư mục bắt buộc do Verifier quy định.
3. Các file DSL mô tả hành vi công khai; lớp nền ở `src/test/java` chuẩn bị HTTP client, fixture hoặc điều kiện kích hoạt message.
4. Tệp dưới `target` hoặc `build` là **đầu ra sinh**, thường không được sửa tay hoặc commit như mã nguồn chính.

Nên đặt tên thư mục, file và kịch bản ổn định, dễ đọc và tránh ký tự khiến tên package/class sinh ra khó xử lý. Cấu trúc tương đối còn có thể tham gia vào **quy tắc chọn base test class** hoặc cách đặt tên generated test tùy cấu hình.

## 3. Một hợp đồng YAML làm ví dụ xuyên suốt

File `src/test/resources/contracts/orders/http/get_paid_order.yml`:

~~~yaml
description: "Lấy trạng thái đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Hợp đồng mô tả:

- **Input:** GET trên path đã thống nhất và header `Accept`.
- **Output:** status 200, nội dung JSON có `id` và `status`.
- **Tình huống:** trong môi trường test, producer phải có hoặc giả lập một đơn `ORD-1001` ở trạng thái `PAID`.

Spring Cloud Contract có thể dùng hợp đồng này để tạo một **producer test** gọi endpoint rồi đối chiếu response. Công cụ cũng có thể sinh một **stub** phục vụ consumer thử gọi GET với dữ liệu mẫu.

Việc file YAML tồn tại và đúng cú pháp **chưa chứng minh**:

- Plugin đã đọc file đó;
- Generated test đã được sinh và được test runner nhận diện;
- Test producer chạy PASS với đúng build;
- Artifact stub mới có chứa mapping tương ứng;
- Consumer đã kiểm thử với đúng phiên bản stub.

Tất cả các bước này cần được xác minh bằng đầu ra build và kết quả CI.

## 4. Cấu hình thư mục hợp đồng với Maven

Với Maven, Spring Cloud Contract thường được cấu hình qua `spring-cloud-contract-maven-plugin`. Một đoạn `pom.xml` minh họa:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>VERSION_PHU_HOP</version>
            <extensions>true</extensions>
            <configuration>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
                <baseClassForTests>
                    com.example.orders.contract.OrderHttpContractBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn cấu hình minh họa**, không phải một file POM hoàn chỉnh. `VERSION_PHU_HOP` phải được thay bằng phiên bản tương thích với Spring Boot, Spring Cloud BOM và build của dự án. Trong ứng dụng thật còn cần dependency, test engine và cấu hình test phù hợp.

Ý nghĩa của các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `spring-cloud-contract-maven-plugin` | Thực hiện các bước sinh test/stub theo cấu hình Maven |
| `contractsDirectory` | Chọn thư mục chứa DSL cục bộ |
| `baseClassForTests` | Chỉ định lớp nền mà generated producer tests có thể kế thừa |
| `extensions` | Cho phép Maven tích hợp các extension/lifecycle của plugin theo cấu hình đang dùng |

Thư mục `src/test/resources/contracts` được viết rõ ở đây để người đọc biết nguồn đầu vào. Khi chuyển root sang nơi khác, phải đổi cấu hình tương ứng, không chỉ di chuyển file.

### Đường dẫn đầu ra trong Maven

Các phiên bản plugin hỗ trợ tùy chỉnh thư mục sinh test/tài nguyên qua các tùy chọn tương ứng, chẳng hạn `generatedTestSourcesDir` và `generatedTestResourcesDir`. Một dạng cấu hình **minh họa**:

~~~xml
<configuration>
    <contractsDirectory>src/test/resources/contracts</contractsDirectory>
    <generatedTestSourcesDir>
        target/generated-test-sources/contracts
    </generatedTestSourcesDir>
    <generatedTestResourcesDir>
        target/generated-test-resources/contracts
    </generatedTestResourcesDir>
</configuration>
~~~

Cần xác minh **đúng tên tùy chọn và đường dẫn được plugin phiên bản hiện tại hỗ trợ**. Đừng mặc định mọi dự án cần khai báo đường dẫn đầu ra: sử dụng mặc định của plugin thường đơn giản và ít rủi ro hơn.

**Không nên** đặt đầu ra được sinh vào `src/main/java` hoặc một thư mục source thủ công đang được quản lý bởi lập trình viên. Generated tests nên tách khỏi production code, có thể xóa và sinh lại hoàn toàn từ contract.

## 5. Cấu hình thư mục hợp đồng với Gradle

Với Gradle, plugin Spring Cloud Contract thường có phần cấu hình `contracts`. Đoạn Groovy DSL cho Gradle dưới đây minh họa cách chỉ định nguồn và lớp nền:

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version 'VERSION_PHU_HOP'
}

contracts {
    contractsDslDir = file('src/test/resources/contracts')
    baseClassForTests = 'com.example.orders.contract.OrderHttpContractBase'
}
~~~

Đây là ví dụ **build.gradle dạng Groovy DSL**, không phải cú pháp có thể dán nguyên xi vào `build.gradle.kts` (Kotlin DSL). Phiên bản plugin, cách tích hợp plugin management, dependencies và test runtime cần phù hợp cấu hình thật.

Trong những phiên bản hỗ trợ, có thể cấu hình thư mục đầu ra bằng các thuộc tính như:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
    generatedTestSourcesDir = file('build/generated-test-sources/contracts')
    generatedTestResourcesDir = file('build/generated-test-resources/contracts')
}
~~~

Điểm cần hiểu là **đầu vào của verifier** và **đầu ra của generator** là những đường dẫn khác nhau. Thay đổi `contractsDslDir` không đồng nghĩa phải thay `generatedTestSourcesDir`. Ngược lại, đổi vị trí generated tests mà không cấu hình cho chúng được biên dịch/chạy có thể khiến test không tham gia kết quả build.

Với Maven hoặc Gradle, các tùy chọn/thư mục chính xác có thể thay đổi theo phiên bản Spring Cloud Contract. Khi áp dụng, nên kiểm tra documentation đi kèm plugin và **nhìn generated output thực tế**, thay vì sao chép cấu hình của một dự án khác không cùng phiên bản.

## 6. Những gì Verifier sinh ra và không sinh ra

Từ hợp đồng ở mục 3, quá trình build có thể tạo các loại đầu ra sau:

| Đầu ra | Người dùng chính | Phải kiểm tra điều gì? |
| --- | --- | --- |
| **Producer test source** | Test runner của producer | Test có chứa request/response cần kiểm tra, được biên dịch và chạy |
| **Test resource hỗ trợ** | Generated test hoặc test runner | Tài nguyên được tìm đúng classpath khi chạy test |
| **Stub/mapping** | Stub Runner / cơ chế stub server | Matcher request và response phản ánh đúng hợp đồng |
| **Stub artifact** | Consumer CI | Artifact có tọa độ và phiên bản ổn định, được tải đúng bản |
| **Build/test report** | CI và người duyệt release | Có bằng chứng test chạy PASS trên đúng producer build |

### Ví dụ hình dung producer test được sinh

Đoạn **giả mã Java** dưới đây nhằm mô tả chức năng, không phải mã đầu ra nguyên văn của bất kỳ phiên bản generator nào:

~~~java
// Giả mã: Verifier thực tế có thể dùng client/test framework khác.
class GeneratedGetPaidOrderTest extends OrderHttpContractBase {

    void shouldGetPaidOrder() {
        // GET /api/orders/ORD-1001
        // Accept: application/json
        // Assert HTTP 200
        // Assert JSON id == "ORD-1001"
        // Assert JSON status == "PAID"
    }
}
~~~

Tên package, tên lớp, tên method, thư viện assertion và cú pháp HTTP client **không phải cố định**. Có thể bị chi phối bởi tên contract, cấu trúc thư mục, framework test, chế độ kiểm thử và phiên bản generator. Điều cần xác minh là **hành vi của generated test**, không phải dự đoán tên file từ trước.

### Ví dụ hình dung stub được sinh

Một stub HTTP có thể match request `GET /api/orders/ORD-1001` và trả status `200`, JSON như contract. Bản thân stub mapping có thể là JSON và có cấu trúc/thư mục gắn với cơ chế WireMock hoặc công cụ tích hợp tương ứng.

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/ORD-1001"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "body": "{\"id\":\"ORD-1001\",\"status\":\"PAID\"}"
  }
}
~~~

**Đây là dạng mapping rút gọn để minh họa**, không phải bản chụp artifact đã được Spring Cloud Contract sinh ra. Ví dụ chưa thể hiện matcher cho header `Accept`. Trong build thật, hãy xem các mapping thực sự được tạo và kiểm tra cả những điều kiện request như header, query parameter và body nếu contract khai báo.

## 7. Lớp nền kiểm thử: cấu hình đúng nơi để generated test chạy được

Generated producer tests cần môi trường thực thi. Với HTTP, đó có thể là Spring application context, controller, HTTP client và dữ liệu mẫu; với messaging, có thể là phương thức kích hoạt event và message verifier.

Một ví dụ **lớp nền HTTP** trong dự án sử dụng Spring Boot, MockMvc và Rest Assured Mock MVC:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class OrderHttpContractBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
        // Chuẩn bị ORD-1001 là đơn PAID trong test fixture,
        // theo cách phù hợp với ứng dụng đang kiểm thử.
    }
}
~~~

Đoạn mã này **phụ thuộc** vào test mode, generated test framework và dependencies. Nó không phải một cấu hình chạy được trong mọi dự án. Chẳng hạn nếu dùng WebTestClient, JAX-RS hoặc một chiến lược chạy HTTP test khác, lớp nền cần thay đổi theo.

Hai điểm mấu chốt:

1. `baseClassForTests` hoặc cấu hình ánh xạ tương đương phải trỏ đến **lớp nền có thật** và phù hợp với generated tests.
2. Producer test phải kiểm tra **hành vi producer** trong môi trường được cấu hình, không chỉ gọi một stub giả lập để tự khẳng định kỳ vọng.

Nếu nhiều nhóm contract cần setup khác nhau, có thể dùng khả năng ánh xạ lớp nền theo package/đường dẫn hoặc quy ước naming được plugin hỗ trợ. Ví dụ, `orders/http` cần lớp nền HTTP, còn `orders/messaging` cần lớp nền có phương thức kích hoạt message. Cách match và property tương ứng (như `baseClassMappings`) phải kiểm chứng theo phiên bản plugin.

## 8. Đường dẫn tương đối có thể ảnh hưởng đến generated test

Xét hai tệp:

~~~text
src/test/resources/contracts/
├── orders/http/get_paid_order.yml
└── payments/http/get_payment.yml
~~~

Đường dẫn tương đối thường được dùng để **tổ chức contract**, và tùy cấu hình còn có thể tham gia việc tạo package/class hoặc chọn base test class. Nếu di chuyển:

~~~text
orders/http/get_paid_order.yml
~~~

sang:

~~~text
checkout/http/get_paid_order.yml
~~~

thì:

- Nội dung `request.url` trong file **không tự động đổi**.
- Bộ quét phải còn tìm được hợp đồng tại vị trí mới.
- Quy tắc chọn lớp nền có thể không còn khớp.
- Package/tên generated tests có thể thay đổi theo cơ chế generator.
- Bộ lọc test theo package/tên cũ trong CI có thể làm generated tests **không được chạy**.
- Stub mới cần được kiểm tra lại; consumer không nên tiếp tục chỉ dùng stub cũ.

Đây là lý do việc di chuyển file nguồn có thể làm mất bằng chứng kiểm thử **dù API thực tế không thay đổi**.

## 9. Nguồn hợp đồng ngoài dự án producer

Không phải dự án nào cũng giữ DSL trong `src/test/resources/contracts`. Một số nhóm sử dụng repository hợp đồng độc lập hoặc artifact chứa hợp đồng cho nhiều producer/consumer.

~~~text
contracts-repository/
├── order-service/
│   └── orders/http/get_paid_order.yml
└── payment-service/
    └── payments/http/get_payment.yml
~~~

Trong trường hợp này, cấu hình phải trả lời:

1. **Nguồn ở đâu?** Repository, artifact hoặc dependency nào cung cấp contract?
2. **Phiên bản nào?** Revision/commit hoặc artifact version nào được sử dụng cho build?
3. **Lấy thư mục con nào?** Producer Order Service không nên vô tình sinh test từ contract của Payment Service.
4. **Đưa vào thư mục làm việc nào?** Plugin phải đọc được DSL ở đường dẫn đúng sau khi tải hoặc giải nén nguồn.
5. **Đóng gói stub từ tập hợp nào?** Consumer phải lấy stub tương ứng với đúng hợp đồng đã kiểm tra producer.

Trong Spring Cloud Contract có các cách cấu hình nguồn hợp đồng bên ngoài, chẳng hạn dependency chứa contract, đường dẫn tương đối bên trong nguồn và chế độ lấy contract. Tên property cụ thể và ý nghĩa của nó phụ thuộc **Maven/Gradle plugin và phiên bản**; không tự động coi `contractsDirectory` của nguồn cục bộ tương đương với đường dẫn nội bộ của một artifact.

**Tránh phụ thuộc phiên bản động khi xác minh release.** Nếu producer test dùng revision A nhưng stub consumer tải được tạo từ revision B, kết quả PASS không chứng minh cả hai phía đồng ý với cùng một hợp đồng.

## 10. Stub artifact không đồng nghĩa với thư mục generated tests

Sau khi producer tests được sinh và chạy đạt, stub có thể được **đóng gói thành artifact riêng**. Một quy ước thường gặp của hệ sinh thái Spring Cloud Contract là artifact có classifier `stubs`:

~~~text
groupId:    com.example
artifactId: order-service
version:    2.4.0
classifier: stubs
~~~

Đây là **tọa độ artifact minh họa**. Tên package/tệp bên trong JAR có thể do plugin và cách đóng gói quyết định. Không nên giả định client có thể truy cập một đường dẫn trên filesystem build của producer.

Phân biệt:

| Đối tượng | Có thể nằm ở đâu? | Consumer cần biết gì? |
| --- | --- | --- |
| Generated producer tests | Thư mục `target`/`build` của producer | Consumer thường không dùng trực tiếp |
| Stub mapping chưa đóng gói | Thư mục generated stub trong build producer | Chưa hẳn đã publish |
| Stub JAR/artifact đã publish | Artifact repository | Tọa độ, version và nguồn gốc rõ ràng |
| Stub Runner instance | Test runtime phía consumer | Dùng artifact nào, nhận request trên endpoint nào |

**Stub Runner** có thể giúp consumer tải và chạy stub, nhưng nó không tự chứng minh producer thật khớp stub. **Producer generated tests** mới là một mắt xích của bằng chứng này; thêm vào đó cần consumer tests có assertion về hành vi ứng dụng.

## 11. Những đầu ra cần đưa vào phạm vi quản lý mã nguồn

Một quy tắc thực tế:

- **Commit** các file DSL nguồn, cấu hình build, base test class và fixture do nhóm chủ động duy trì.
- **Không sửa tay** generated producer tests hoặc stub mapping với ý định biến chúng thành nguồn sự thật.
- **Không commit** thư mục build `target` / `build` khi chúng chứa generated outputs có thể tái tạo, trừ trường hợp đặc biệt có chính sách rõ ràng.
- **Lưu kết quả kiểm thử** và artifact đóng gói trong CI/artifact repository để truy vết build, thay vì sao chép generated source vào source control.

Nếu generated Java test hiện hành sai, hãy sửa **hợp đồng**, cấu hình sinh test hoặc lớp nền. Sửa generated file trực tiếp chỉ có tác dụng tạm thời, dễ biến mất ở lần sinh kế tiếp.

Với các bản build dùng thư mục đầu ra tùy chỉnh, phải tránh ghi đè code do lập trình viên quản lý hoặc tạo file vào vị trí dùng chung với build khác. Workspace riêng cho từng pipeline giúp giảm nguy cơ lẫn generated outputs giữa hai commit.

## 12. Một thay đổi đường dẫn phải được xác minh thế nào?

Giả sử dự án ban đầu đọc hợp đồng từ:

~~~text
src/test/resources/contracts/orders/
~~~

Sau refactor, nhóm chuyển chúng sang:

~~~text
src/contract-spec/orders/
~~~

Nếu không sửa cấu hình, Verifier có thể **không phát hiện DSL**. Build có thể vẫn xanh vì các test khác chạy thành công, trong khi test hợp đồng mới hoàn toàn không được sinh.

Quy trình kiểm tra đúng:

1. **Cập nhật nguồn:** cấu hình `contractsDirectory` hoặc `contractsDslDir` phù hợp với vị trí mới.
2. **Dọn kết quả cũ:** trong môi trường phát triển/CI, dùng cơ chế clean của build để tránh nhầm file sinh từ commit trước.
3. **Kiểm tra hợp đồng được đọc:** đối chiếu danh sách hợp đồng mong đợi với danh sách/kịch bản generator xử lý.
4. **Kiểm tra generated tests:** xác nhận test mới tồn tại, classpath và lớp nền đúng.
5. **Chạy producer tests:** xác nhận generated tests thực sự được biên dịch, thực thi và PASS; không bị skip do test filter.
6. **Kiểm tra stub:** artifact mới chứa mapping của hợp đồng đã chuyển.
7. **Chạy consumer tests:** lấy stub đúng version qua Stub Runner và xác minh logic consumer.

Để dễ truy vết, hãy lưu thông tin:

~~~yaml
# Mẫu biên bản build do nhóm tự thiết kế,
# không phải định dạng mặc định của Spring Cloud Contract.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
contracts_root: "src/contract-spec/orders"
expected_contracts:
  - "http/get_paid_order.yml"
  - "http/get_missing_order.groovy"
generated_test_sources_verified: true
generated_producer_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_stub_tests: PASS
~~~

Nếu danh sách hợp đồng mong đợi giảm sau một lần di chuyển file, không tự động cập nhật nó xuống 0 để làm CI xanh. Cần xem việc bỏ hợp đồng có được phê duyệt như một thay đổi giao diện thật hay là sai cấu hình.

## 13. CI nên xác nhận những điều gì về thư mục và đầu ra?

Một pipeline kiểm thử hợp đồng có thể dùng cổng kiểm soát:

~~~mermaid
flowchart TD
    A["Checkout đúng producer + contract revision"] --> B["Xác định contracts root"]
    B --> C{"Các hợp đồng mong đợi có được phát hiện?"}
    C -->|Không| X["BLOCK: thiếu hoặc sai đường dẫn"]
    C -->|Có| D["Sinh generated tests + stubs"]
    D --> E{"Generated tests đúng và biên dịch?"}
    E -->|Không| X
    E -->|Có| F["Chạy producer contract tests"]
    F --> G{"PASS, không bị skip ngoài chủ đích?"}
    G -->|Không| X
    G -->|Có| H["Kiểm tra và phát hành stub version cố định"]
    H --> I["Consumer CI dùng chính stub version đó"]
    I --> J{"Consumer tests PASS?"}
    J -->|Không| X
    J -->|Có| K["Lưu bằng chứng / release gate"]
~~~

### Những kiểm tra không nên bỏ qua

| Điều kiện | Vì sao cần? |
| --- | --- |
| Contracts root tồn tại và chứa DSL mong đợi | Tránh build không có contract mà vẫn PASS |
| Không có file vô tình bị lọc | Tránh bỏ sót kịch bản vì tên file hoặc thư mục sai |
| Generated tests nằm trong source set/test compilation | Tránh tạo ra code nhưng test runner không chạy |
| Generated tests thực sự được thực thi | Một báo cáo build xanh không đủ chứng minh Verifier chạy |
| Base class phù hợp với loại hợp đồng | Tránh HTTP test dùng setup message hoặc ngược lại |
| Stub mapping được sinh từ cùng contract revision | Tránh stub khác hành vi producer test |
| Stub artifact có version bất biến và truy vết được | Đảm bảo consumer test có thể tái lập |
| Consumer CI chạy với đúng stub artifact | Tránh PASS với stub đã cũ |

Trong dự án Maven, thao tác build như `./mvnw verify` có thể chạy các bước gắn với lifecycle nếu plugin được cấu hình đúng. Trong Gradle, thường phải bảo đảm task sinh test, biên dịch test và task kiểm thử được nối vào vòng đời build; lệnh như `./gradlew check` chỉ có ý nghĩa khi cấu hình đó thực sự tồn tại.

Không chỉ nhìn kết quả của lệnh: **phải kiểm tra trong log/report rằng generated contract tests đã được thực thi**. Tùy hệ thống, nên có một bước fail khi số contract xử lý bất ngờ bằng 0 hoặc thiếu các kịch bản bắt buộc.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy generated tests | DSL nằm ngoài root hoặc plugin chưa được kích hoạt | Kiểm tra contracts root, cấu hình plugin và log sinh test |
| Chỉ sinh một phần hợp đồng | Sai cấu trúc/đường dẫn, bộ lọc hoặc file không hợp lệ | So sánh danh sách hợp đồng mong đợi với đầu vào được phát hiện |
| Generated test không biên dịch | Base test class sai package, sai framework hoặc thiếu dependency | Xem source sinh, thông báo compiler và lớp nền |
| Generated test biên dịch nhưng không chạy | Test task/source set hoặc bộ lọc không nhận test | Kiểm tra test report và classpath |
| Producer test thất bại dù stub trông đúng | Producer không đáp ứng contract hoặc fixture không phù hợp | Kiểm tra request/response thực và setup của base class |
| Stub artifact không chứa mapping mới | Đóng gói từ bộ contract cũ hoặc job khác | Kiểm tra nguồn sinh, version và nội dung artifact |
| Consumer Stub Runner không tải được stub | Sai tọa độ, repository hoặc version | Kiểm tra cấu hình repository và artifact tồn tại |
| CI xanh sau khi di chuyển thư mục contract | Test bị bỏ qua hoặc dùng file generated cũ | Clean build, kiểm tra lại discovery và test thực thi |
| Generated test sai lớp nền sau đổi tên folder | Quy tắc ánh xạ dựa vào package/đường dẫn | Điều chỉnh cấu hình mapping, xác minh test sinh ra |
| Kết quả local và CI khác nhau | Khác môi trường, case-sensitive path hoặc cấu hình plugin | Chuẩn hóa tên tệp, phiên bản và đường dẫn |

**Không sửa generated tests bằng tay như một giải pháp lâu dài.** Nếu lỗi là do sai nguồn, sửa hợp đồng hoặc cấu hình; nếu lỗi là do dữ liệu, sửa fixture test; nếu lỗi là do API không tương thích, sửa producer hoặc thương lượng thay đổi hợp đồng với consumer.

## 15. Thực hành theo tình huống

### Bài tập A — Root nguồn sai

Đội đang cấu hình `src/test/resources/contracts` nhưng một người thêm tệp tại:

~~~text
src/test/resources/contract/orders/get_paid_order.yml
~~~

Build vẫn xanh, không có generated test mới.

**Yêu cầu:** xác định lỗi, cách xác minh generator thực sự tìm thấy hợp đồng và vì sao build xanh chưa phải là bằng chứng tương thích.

**Gợi ý:** `contract` và `contracts` là hai thư mục khác nhau. Di chuyển đúng nguồn hoặc cập nhật cấu hình có chủ đích; sau đó xác minh generated test được tạo **và chạy**.

### Bài tập B — Generated tests không thuộc test task

Plugin sinh Java test vào một thư mục tùy chỉnh, nhưng quá trình test compilation không đưa thư mục đó vào source set.

**Yêu cầu:** phân biệt bước sinh mã với bước thực thi test và liệt kê những đầu ra cần kiểm tra để bảo đảm Verifier có tác dụng trong CI.

**Gợi ý:** xem thư mục generated source, test compile log, danh sách test được thực thi và report. Không dùng sự tồn tại của file Java làm bằng chứng test PASS.

### Bài tập C — Chuyển thư mục làm đổi base class

Hợp đồng HTTP nằm ở `orders/http` được chuyển sang `orders/messaging`, trong khi cấu hình chọn base class theo nhóm thư mục.

**Yêu cầu:** dự đoán tác động có thể xảy ra và đề xuất bước xác minh.

**Gợi ý:** generated test có thể kế thừa lớp nền message không phù hợp. Xem source test thực, quy tắc ánh xạ, fixture và kết quả chạy producer test; không sửa endpoint để né lỗi cấu hình.

### Bài tập D — Dùng stub cũ để kết luận tương thích

Producer P2 chạy generated tests PASS. Consumer Checkout C1 cũng PASS với Stub Runner, nhưng CI đang lấy artifact `order-service:2.3.0:stubs` trong khi P2 dự kiến phát hành `2.4.0`.

**Yêu cầu:** giải thích vì sao bằng chứng chưa đủ và mô tả các bước cần làm để kiểm tra đúng cặp phiên bản.

**Gợi ý:** sinh và phát hành stub 2.4.0 từ đúng hợp đồng/build P2 đã kiểm chứng, khóa artifact, chạy lại consumer tests, lưu revision và kết quả.

### Bài tập E — Thiết kế cổng kiểm soát CI

Hãy đề xuất một release gate ngăn trường hợp **số hợp đồng được phát hiện bằng 0** và ngăn trường hợp **generated tests bị skip**.

**Gợi ý:** đối chiếu danh sách hợp đồng bắt buộc, kiểm tra số test sinh/thực thi và fail khi điều kiện tối thiểu không đạt. Kết hợp kiểm tra stub artifact và consumer tests với version cố định.

## 16. Checklist cấu hình thư mục và đầu ra

- [ ] Nguồn Groovy/YAML contract được xác định rõ và được plugin tìm thấy.
- [ ] Đường dẫn cục bộ hoặc nguồn contract ngoài dự án được khóa revision/version.
- [ ] Tên thư mục/file thống nhất, không phụ thuộc case-sensitive path ngoài ý muốn.
- [ ] Cấu hình Maven `contractsDirectory` hoặc Gradle `contractsDslDir` phù hợp với vị trí DSL thực.
- [ ] Đầu ra generated tests/tài nguyên/stubs nằm ở vùng build được quản lý rõ.
- [ ] Generated Java tests được biên dịch, phát hiện và thực thi bởi test runner.
- [ ] Base class phù hợp với HTTP hoặc messaging và có fixture kiểm soát được.
- [ ] Số lượng và danh sách hợp đồng đã xử lý được đối chiếu với kỳ vọng.
- [ ] Không dùng generated tests cũ để xác minh một revision mới.
- [ ] Stub artifact được sinh từ đúng hợp đồng và producer build đã chạy PASS.
- [ ] Consumer dùng Stub Runner với đúng artifact/version, không phụ thuộc bản cũ.
- [ ] CI fail khi thiếu hợp đồng, thiếu generated tests bắt buộc hoặc test bị skip ngoài chủ đích.
- [ ] Build/test report và metadata đủ để truy vết nguồn hợp đồng, phiên bản producer và stub.
- [ ] Thay đổi đường dẫn được review như một thay đổi **hạ tầng kiểm thử**, kể cả khi HTTP API chưa đổi.

**Ghi nhớ:** Spring Cloud Contract Verifier chỉ mang lại bằng chứng tương thích khi hợp đồng **được phát hiện**, kiểm thử **được sinh và chạy**, stub **được tạo từ cùng nguồn** và consumer **kiểm thử đúng artifact**. Cấu hình thư mục hợp đồng và các đầu ra được sinh phải được xem như một phần của thiết kế CI, không chỉ là vấn đề đặt tên hoặc sắp xếp tệp.
