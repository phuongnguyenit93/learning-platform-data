# Thiết lập pipeline với artifact có thể truy vết

Trong hệ thống microservices, **producer** và **consumer** thường được build, kiểm thử và triển khai ở các pipeline khác nhau. Producer có thể đã chạy generated contract tests thành công, nhưng consumer vẫn tải nhầm stub cũ; container image được deploy có thể được build từ commit khác; hoặc khi xảy ra lỗi production, nhóm không biết JAR `stubs` nào đã được dùng để xác minh release. Một pipeline hoàn chỉnh phải nối được **contract source → producer verification → stub artifact → consumer verification → producer image → deployment record**.

Bài thực hành này xây dựng một luồng CI/CD có thể truy vết cho hai dịch vụ:

- **Order Service** là producer, cung cấp HTTP API `GET /api/orders/{id}` và phát hành artifact chứa WireMock stubs.
- **Billing Service** là consumer, gọi API Order bằng HTTP client thật và kiểm thử bằng **Spring Cloud Contract Stub Runner**.

Ta sẽ định nghĩa hợp đồng bằng **Groovy DSL**, sinh và chạy producer tests, đóng gói JAR classifier `stubs`, ghi checksum và provenance, cho Billing tải đúng artifact, rồi đặt các cổng CI trước khi promote release. Cuối bài, một incident giả lập sẽ được lần ngược từ deployment revision về Git commit, contract, test report và stub artifact.

Bài thuộc chương **Thực hành tổng hợp** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun học kiểm thử hợp đồng giữa producer và consumer qua HTTP hoặc message, sử dụng Groovy/YAML DSL, sinh producer tests, phát hành stub, dùng Stub Runner và tích hợp CI để phát hiện API không tương thích. Mục tiêu workshop là tạo được **bằng chứng có thể kiểm tra lại**, chứ không chỉ có một dòng `BUILD SUCCESS`.

Các ví dụ dùng **Maven, JUnit 5, Spring Boot và Spring Cloud Contract**. Hãy chọn Spring Boot, Spring Cloud release train, Spring Cloud Contract plugin/starter và JDK tương thích với nhau theo BOM của dự án. Các version `1.4.2`, `3.8.0` trong bài là version ví dụ của ứng dụng, **không phải phiên bản mới nhất của thư viện**. Những phần CI YAML mang tính mẫu trung lập nhà cung cấp; cần ánh xạ sang GitHub Actions, GitLab CI, Jenkins hoặc hệ thống hiện có.

## 1. Kết quả cuối cùng của workshop

Sau khi hoàn thành, nhóm phải có thể trả lời các câu hỏi sau chỉ bằng release record và artifacts:

1. Contract nào được producer build nạp?
2. Producer Git SHA nào đã chạy generated verification tests?
3. Test nào đã chạy, test count bao nhiêu và report ở đâu?
4. JAR `stubs` nào được tạo, tọa độ Maven và SHA-256 là gì?
5. Billing đã test với **đúng bytes** của stub artifact nào?
6. Producer image digest nào được build từ source đã xác minh?
7. Image digest nào thực sự được deploy vào environment/region?
8. Khi lỗi xảy ra, có thể truy từ trace/request đến deployment revision, build run, contract và consumer test không?

**Deliverables của bài thực hành**

- Producer Maven build có Spring Cloud Contract Plugin và generated tests.
- Artifact `order-service:1.4.2:stubs` được đóng gói và publish vào repository staging.
- Consumer Stub Runner test dùng artifact version cụ thể và client thật.
- Release manifest nối Git SHA, CI run, report, stub checksum và image digest.
- CI gates cho producer, consumer, publish, deploy và post-deploy.
- Incident note chứng minh đường truy vết hoạt động.

## 2. Kiến trúc và luồng artifact

~~~mermaid
flowchart TD
    A["Order Service Git commit"] --> B["Groovy/YAML contracts"]
    B --> C["Spring Cloud Contract Maven Plugin"]
    C --> D["Generated producer tests"]
    D --> E{"Tests pass?"}
    E -->|No| X["Block publish"]
    E -->|Yes| F["Package producer + classifier stubs"]
    F --> G["Stub JAR + SHA-256 + build provenance"]
    G --> H["Staging Maven repository"]
    H --> I["Billing CI / Stub Runner"]
    I --> J["Real Billing HTTP client"]
    J --> K{"Consumer tests pass?"}
    K -->|No| Y["Block release promotion"]
    K -->|Yes| L["Promote verified artifacts"]
    L --> M["Deploy verified producer image digest"]
    M --> N["Deployment revision + runtime evidence"]
~~~

**Artifact stub và container image là hai đầu ra khác nhau**. JAR `stubs` giúp consumer kiểm tương tác được công bố; image chứa producer runtime. Chúng phải cùng trỏ về một **producer source/build identity**. Nếu image được build lại từ một commit khác sau khi consumer đã test stub, chuỗi bằng chứng bị đứt.

## 3. Phân biệt các danh tính trong release

| Danh tính | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| Contract identity | `GET /api/orders/42`, `shouldReturnPaidOrder` | Hành vi nào được cam kết? |
| Producer source identity | Full Git SHA `a1b2c3...` | Source/contract nào được review và build? |
| Consumer source identity | Full Git SHA `b2c3d4...` | Client nào đã được kiểm? |
| Producer application version | `com.acme:order-service:1.4.2` | Bản ứng dụng nào được đóng gói? |
| Stub artifact coordinates | `com.acme:order-service:1.4.2:stubs` | Consumer đã nạp bộ stubs nào? |
| Stub artifact checksum | SHA-256 của JAR | Bytes nào đã được dùng? |
| Container image digest | `sha256:...` | Image bytes nào được deploy? |
| CI run ID | `order-producer-483` | Lần build/test nào tạo bằng chứng? |
| Deployment revision | `orders-prod-r134` | Lần rollout nào đã chạy ở môi trường? |

**Không thay thế một loại ID bằng loại khác.** Version `1.4.2` không chứng minh JAR có nội dung gì nếu repository cho phép overwrite. Git SHA không chứng minh image đã được deploy. Image tag không chắc bất biến; dùng digest để định danh nội dung.

## 4. Chuẩn bị hai repository

Trong workshop, giả định có hai repository:

~~~text
order-service/
├── pom.xml
├── src/
│   ├── main/java/com/acme/orders/
│   │   ├── OrderController.java
│   │   ├── OrderService.java
│   │   └── OrderRepository.java
│   └── test/
│       ├── java/com/acme/orders/contract/
│       │   └── BaseContractTest.java
│       └── resources/contracts/orders/
│           ├── get_paid_order.groovy
│           └── order_not_found.groovy
└── ...

billing-service/
├── pom.xml
├── src/
│   ├── main/java/com/acme/billing/
│   │   ├── OrderClient.java
│   │   └── BillingService.java
│   └── test/java/com/acme/billing/
│       └── OrderClientContractTest.java
└── ...
~~~

**Mỗi repository có Git SHA riêng**. Producer pipeline chịu trách nhiệm sinh tests và phát hành stubs; consumer pipeline ghim stub version để xác minh client. Có thể tổ chức mono-repo, nhưng vẫn cần ghi riêng commit/source identity cho các module nếu build/release độc lập.

### 4.1. Công cụ và quyền truy cập

Chuẩn bị:

- JDK và Maven Wrapper theo phiên bản project.
- Maven repository manager có **staging/release repository** hoặc cơ chế artifact promotion tương đương.
- CI identity có quyền publish vào staging và quyền read cho consumer job.
- Container registry nếu bài triển khai image.
- Một môi trường test/staging để chạy producer và consumer checks.

**Không dùng production credentials trong bài thực hành**. Stub fixtures chỉ chứa dữ liệu giả; repository credentials được cấp qua CI secret store và không được commit vào POM, contract hoặc logs.

## 5. Khóa bộ phiên bản build

Ví dụ phần properties trong producer/consumer POM:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2023.0.4</spring-cloud.version>
    <spring-cloud-contract.version>4.1.5</spring-cloud-contract.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Các giá trị trên chỉ minh họa một cấu hình project. **Không sao chép version độc lập mà không kiểm tương thích** với Spring Boot parent/BOM và Java runtime đang dùng. Cả producer plugin và consumer starter phải nằm trong cùng dòng Spring Cloud Contract tương thích.

Import Spring Cloud BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**BOM quản lý các dependency thuộc release train**, nhưng không tự khóa mọi Maven plugin, JDK, CI image, CI actions hoặc Docker base image. Pin các thành phần đó riêng và ghi version/digest trong run manifest.

## 6. Khai báo Spring Cloud Contract ở producer

Trong `order-service/pom.xml`, thêm Contract Verifier vào test scope:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Khai báo Maven Plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>
                    com.acme.orders.contract.BaseContractTest
                </baseClassForTests>
                <testFramework>JUNIT5</testFramework>
                <testMode>MockMvc</testMode>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Plugin được cấu hình như **lifecycle extension** để tham gia quá trình generate/verify/package theo cách Maven Plugin hỗ trợ. Các tên property/giá trị enum có thể thay đổi theo phiên bản; khi cấu hình project thật, đối chiếu documentation và plugin descriptor của version đã pin.

**Đừng thêm dependency Verifier vào scope runtime** của producer. Đây là công cụ sinh/chạy tests, không phải thành phần bắt buộc của application runtime.

## 7. Viết contract HTTP cho Order Service

Tạo `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Trả đơn hàng đã thanh toán theo ID'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Contract bảo vệ method `GET`, path `/api/orders/42`, request header `Accept`, response status `200`, JSON media type và các field/kiểu/giá trị nghiệp vụ của fixture.

Thêm contract lỗi `order_not_found.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderNotFound'
    description 'Trả lỗi có cấu trúc khi không tìm thấy đơn'

    request {
        method 'GET'
        url '/api/orders/999'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order does not exist'
        )
    }
}
~~~

Đây là hai tình huống **có chủ đích khác nhau**. Consumer có thể cần phân biệt dữ liệu thành công với lỗi nghiệp vụ. Nếu message lỗi thay đổi theo ngôn ngữ/locale, giữ `code` là cam kết ổn định và dùng matcher phù hợp cho `message`.

## 8. Tạo base class cho generated producer tests

Tạo `BaseContractTest.java`:

~~~java
package com.acme.orders.contract;

import com.acme.orders.Order;
import com.acme.orders.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class BaseContractTest {

    @Autowired
    OrderRepository orders;

    @BeforeEach
    void prepareContractData() {
        orders.deleteAll();
        orders.save(new Order(
            42L, "PAID", 125000L, "VND"
        ));
    }
}
~~~

`Order` và `OrderRepository` là ví dụ domain/repository; hãy thay bằng implementation của project. Base class tạo **fixture xác định** để generated tests chạy lại cho kết quả ổn định.

Các nguyên tắc:

1. Mỗi test có fixture độc lập; không phụ thuộc dữ liệu từ lần chạy trước.
2. Không dùng database development hoặc production.
3. Không gọi service ngoài không cần thiết trong generated tests.
4. Nếu API phụ thuộc thời gian, inject clock/test time cố định.
5. Nếu dùng test container/database, pin image/version và reset state.

**Generated test phải đi qua application/controller thật của producer trong test context**. Không viết base class trả response mẫu trực tiếp để test tự pass; điều đó chỉ xác minh fixture của base class, không xác minh implementation.

## 9. Chạy producer verification lần đầu

Trong repository Order Service:

~~~bash
./mvnw -B -ntp clean verify
~~~

Lệnh này là ví dụ cho Linux CI runner có Maven Wrapper. Trên Windows PowerShell có thể dùng `.\mvnw.cmd -B -ntp clean verify`.

Sau build, kiểm tra:

- Plugin đã phát hiện đúng contract files.
- Generated tests xuất hiện trong generated test source directory của build.
- Test runner thực sự thực thi generated tests.
- Test count không bằng 0 ngoài ý muốn.
- Report có test names tương ứng `shouldReturnPaidOrder` và `shouldReturnOrderNotFound`.
- Không có `skipTests` hoặc cấu hình skip Contract Verifier ngoài dự kiến.

**`BUILD SUCCESS` một mình không đủ**. Nếu plugin không tìm thấy contracts hoặc generated tests bị skip, pipeline vẫn có thể xanh mà không kiểm hợp đồng.

### 9.1. Thử chứng minh cổng test bắt lỗi

Trong nhánh thử nghiệm, thay implementation để trả:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": "125000",
  "currency": "VND"
}
~~~

Contract đang yêu cầu `amountMinor` là JSON number. Generated producer test phải FAIL. Hoàn nguyên implementation sau khi xác minh.

Tiếp theo, đổi `status` từ `PAID` thành `CANCELLED`. Test fixture này cũng phải FAIL. Nếu vẫn PASS, kiểm matcher/body assertion đã sinh; không nới contract chỉ để che sai khác nghiệp vụ.

## 10. Đóng gói producer và JAR stubs

Khi producer verification đạt, plugin tạo các output theo cấu hình project, bao gồm artifact stubs có **classifier `stubs`**. Tọa độ ví dụ:

~~~text
com.acme:order-service:1.4.2:stubs
~~~

Tách tọa độ:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.4.2
classifier = stubs
extension  = jar
~~~

JAR stubs chứa thông tin hợp đồng và mappings mà consumer runner cần. Cấu trúc nội bộ phụ thuộc plugin/version. Có thể kiểm file bằng:

~~~bash
jar tf target/order-service-1.4.2-stubs.jar
~~~

Đường dẫn trên là ví dụ theo cách đặt tên thường gặp; hãy tìm **đúng artifact được build** trong output và log. Kiểm rằng mappings cho cả success/error scenarios có mặt.

**Không sửa nội dung JAR sau khi đã tính checksum hoặc publish**. Nếu contract thay đổi, tạo build/version mới để consumer có thể pin chính xác.

## 11. Publish vào staging repository

Trong workshop, dùng một Maven staging repository hoặc cơ chế tương đương:

~~~text
Repository: contract-staging
Producer coordinates: com.acme:order-service:1.4.2
Stub coordinates: com.acme:order-service:1.4.2:stubs
Policy: immutable within a staging/release build
~~~

Maven Plugin có thể attach classifier stubs vào project artifact để lifecycle publish cả application và stubs. Một pipeline Maven có thể chạy:

~~~bash
./mvnw -B -ntp clean deploy
~~~

`deploy` chạy các phase trước đó, bao gồm verification theo lifecycle đã cấu hình, rồi deploy artifact. Cấu hình repository và quyền truy cập phải được đặt trong Maven settings/CI secret store; **không commit username/password vào POM**.

Nếu tổ chức dùng repository manager có staging lifecycle:

1. Publish vào **staging repository**.
2. Chạy consumer compatibility tests trên chính artifact trong staging.
3. Nếu mọi gate đạt, **close/promote** staging repository sang release.
4. Nếu fail, drop staging và sửa producer/consumer/contract.

Tên thao tác close/promote phụ thuộc repository manager. Không phát hành một release immutable trước khi compatibility gates đạt nếu policy yêu cầu tất cả consumer được kiểm trước.

## 12. Tính checksum của JAR stubs

Sau khi artifact đã được tạo, tính SHA-256 trên **bytes thật**:

~~~bash
sha256sum target/order-service-1.4.2-stubs.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\target\order-service-1.4.2-stubs.jar -Algorithm SHA256
~~~

Ghi kết quả vào run record:

~~~text
stubCoordinate = com.acme:order-service:1.4.2:stubs
stubSha256     = <sha256-of-actual-jar>
producerCommit = <full-git-sha>
producerRunId  = <ci-run-id>
~~~

Placeholder `<...>` không phải giá trị thật. **Checksum phải được tính từ JAR được upload/download**, không được tự nhập dựa trên tên file.

Sau khi publish staging, tải lại JAR từ repository và tính checksum lần nữa. Nếu checksum khác file local đã verify, dừng pipeline và điều tra:

- Artifact có bị transform/overwrite không?
- Có nhầm version/classifier không?
- Job publish có lấy nhầm output từ build khác không?
- Repository có trả artifact cache/mirror khác không?

## 13. Consumer: thêm Stub Runner dependency

Trong `billing-service/pom.xml`, thêm:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Consumer không cần Contract Verifier plugin chỉ để tải và dùng producer stubs. Nó cần Stub Runner ở test scope và một test sử dụng **client/listener thật**.

## 14. Viết HTTP client của Billing

Ví dụ client:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(String baseUrl) {
        this.http = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .accept(org.springframework.http.MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(
        long id,
        String status,
        long amountMinor,
        String currency
    ) {}
}
~~~

Đây là ví dụ dùng Spring Framework có `RestClient`. Nếu project sử dụng Feign, WebClient hoặc một client wrapper nội bộ, bài test nên gọi **đúng client production** và dùng cùng converter/interceptors/error handler; chỉ thay base URL để trỏ đến stub.

## 15. Viết consumer test với Stub Runner

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/contract-staging"
)
class OrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void billingClientReadsPaidOrder() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderClient client = new OrderClient(stubUrl.toExternalForm());
        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.amountMinor()).isEqualTo(125000L);
        assertThat(order.currency()).isEqualTo("VND");
    }
}
~~~

Điểm cần lưu ý:

- `ids` pin đúng producer stub version `1.4.2`.
- `REMOTE` tải artifact từ Maven repository; repository URL là ví dụ và phải được thay bằng staging URL thực.
- `StubFinder` trả URL HTTP của WireMock instance đã khởi động; port có thể động.
- Test gọi **OrderClient**, không chỉ gọi một endpoint mock tự tạo.
- Assertions kiểm DTO/business data, không dừng ở HTTP 200.

Nếu dùng `LOCAL`, JAR phải có trong Maven local repository của runner. `REMOTE` cần read credentials/proxy/TLS phù hợp. **Stub Runner tải JAR từ Maven repository; nó không biến Maven repository thành HTTP server của API.**

### 15.1. Test error behavior

Consumer cũng nên kiểm lỗi:

~~~java
@Test
void mapsMissingOrderToDomainError() {
    assertThatThrownBy(() -> client.getOrder(999L))
        .isInstanceOf(OrderNotFoundException.class);
}
~~~

Ví dụ này giả định `OrderClient` có error mapping thành `OrderNotFoundException`. Trong implementation thật, kiểm error body/code theo contract; không chỉ assert “có exception bất kỳ”. Nếu consumer chưa có mapping, bài thực hành cần triển khai nó như behavior của client.

## 16. Tạo compatibility matrix cho consumer

Một producer release có thể ảnh hưởng nhiều consumer:

| Consumer | Phiên bản consumer | Stub producer | Kết quả CI | Quyết định |
| --- | --- | --- | --- | --- |
| Billing | 3.7.0 | Order 1.4.1 | PASS | Baseline. |
| Billing | 3.7.0 | Order 1.4.2 | PASS/FAIL thực tế | Kiểm backward compatibility. |
| Billing | 3.8.0 | Order 1.4.2 | PASS/FAIL thực tế | Kiểm client mới. |
| Analytics batch | 2.2.0 | Order 1.4.2 | NOT TESTED | Chưa đủ bằng chứng. |

Đây là **ma trận minh họa**, không có kết quả CI thực. Pipeline chỉ được đánh dấu tương thích cho những consumer versions đã kiểm hoặc có quyết định ngoại lệ rõ ràng.

Ưu tiên:

- Consumer đang chạy production/còn support.
- Consumer deploy chậm như batch, mobile hoặc partner.
- Consumer dùng field/enum/header/error semantics đang thay đổi.
- Consumer còn phụ thuộc API v1 trong migration v2.

Không nhất thiết chạy mọi tổ hợp phiên bản lịch sử, nhưng không được coi `NOT TESTED` là `PASS`.

## 17. Tạo release manifest

Manifest là hồ sơ nối **source, build, test, artifact và deployment**. Ví dụ JSON:

~~~json
{
  "service": "order-service",
  "source": {
    "repository": "order-service",
    "commit": "a1b2c3d4e5f678901234567890abcdef12345678",
    "contractPaths": [
      "src/test/resources/contracts/orders/get_paid_order.groovy",
      "src/test/resources/contracts/orders/order_not_found.groovy"
    ]
  },
  "build": {
    "runId": "order-producer-483",
    "jdk": "17",
    "mavenWrapper": "3.9.x",
    "springCloudContract": "4.1.5",
    "producerVerification": "PASSED",
    "testReportRef": "order-producer-483/test-report"
  },
  "stubArtifact": {
    "coordinates": "com.acme:order-service:1.4.2:stubs",
    "sha256": "<actual-stubs-jar-sha256>",
    "repository": "contract-staging"
  },
  "producerImage": {
    "reference": "registry.example.org/orders/order-service",
    "digest": "sha256:<actual-image-digest>"
  },
  "consumerChecks": [
    {
      "consumer": "billing-service",
      "consumerCommit": "b2c3d4e5f678901234567890abcdef1234567890",
      "stubCoordinates": "com.acme:order-service:1.4.2:stubs",
      "stubSha256": "<actual-stubs-jar-sha256>",
      "ciRunId": "billing-contract-991",
      "result": "PASSED"
    }
  ],
  "deployment": {
    "environment": "production",
    "region": "region-a",
    "rolloutId": "orders-prod-r134",
    "imageDigest": "sha256:<actual-image-digest>",
    "status": "COMPLETED"
  }
}
~~~

Đây là **schema nội bộ minh họa**, không phải định dạng bắt buộc của Spring Cloud Contract. Các giá trị `<actual-...>` là placeholder. Pipeline phải tạo manifest từ dữ liệu thật do Git/CI/repository/registry/deployment system cung cấp; không cho developer tự điền `PASSED` bằng tay.

### 17.1. Những gì không được đưa vào manifest

- Maven/Gradle repository passwords hoặc access tokens.
- Docker registry credentials.
- Broker/database credentials.
- JWT, private key, certificate private material.
- Raw customer payload hoặc PII.

Chỉ lưu **secret reference/identity** nếu cần truy vết cấu hình; giá trị bí mật được quản lý trong secret manager. CI logs và reports cần redaction trước khi lưu.

## 18. Thu thập provenance từ CI

Một số lệnh Linux runner minh họa:

~~~bash
git rev-parse HEAD
./mvnw -version
sha256sum target/order-service-1.4.2-stubs.jar
sha256sum target/order-service-1.4.2.jar
~~~

Các đầu ra cần ghi:

| Lệnh/nguồn | Dữ liệu |
| --- | --- |
| Git checkout | Full source SHA và ref/PR context. |
| Maven Wrapper | Maven version, Java runtime. |
| Test report | Số generated tests, pass/fail/skip. |
| Stub JAR | Coordinates và SHA-256. |
| Application JAR | Checksum nếu cần kiểm đúng package. |
| Container build/push | Image digest trả từ registry/build tool. |
| Deployment system | Environment, region, rollout revision, image digest thực chạy. |

**Đừng lấy Git SHA của một job khác rồi gắn vào artifact đã được build từ workspace hiện tại**. Manifest phải được tạo trong cùng run context với outputs, hoặc nhận metadata từ artifact provenance đã ký/xác minh.

### 18.1. Image digest

Container tag như `order-service:1.4.2` có thể mutable tùy registry policy. Khi build/push image, lấy **digest thực tế** từ tool/registry và lưu trong manifest. Job deploy phải dùng reference theo digest:

~~~text
registry.example.org/orders/order-service@sha256:<actual-digest>
~~~

Không tự tạo digest từ tag và không giả định image tag luôn trỏ cùng bytes. Khi canary có nhiều image, record cần thể hiện digest theo rollout/replica/region.

## 19. CI pipeline: các stage và điều kiện

~~~mermaid
flowchart TD
    A["Checkout immutable producer SHA"] --> B["Resolve pinned JDK/Maven/dependencies"]
    B --> C["Generate + run producer contract tests"]
    C --> D{"All required tests pass?"}
    D -->|No| X["Stop; do not publish"]
    D -->|Yes| E["Package producer JAR + stubs JAR"]
    E --> F["Calculate checksums and create provenance"]
    F --> G["Publish to staging Maven repository"]
    G --> H["Consumer CI resolves exact stub version"]
    H --> I["Run Stub Runner client tests"]
    I --> J{"Supported consumer matrix passes?"}
    J -->|No| Y["Stop promotion; investigate"]
    J -->|Yes| K["Promote immutable stubs"]
    K --> L["Build/promote verified image digest"]
    L --> M["Deploy canary and smoke test"]
    M --> N["Record deployment revision and monitor"]
~~~

**Không bắt buộc tất cả stage chạy trong một job**. Nếu tách job, phải chuyển đúng JAR/image đã được xác minh qua artifact handoff; không checkout branch đang di chuyển rồi build lại mà không có verification tương ứng.

### 19.1. Pipeline YAML trung lập nhà cung cấp

~~~yaml
# Pseudocode: ánh xạ sang CI provider thực tế của tổ chức.
producer:
  checkout:
    ref: immutable-commit-sha
  toolchain:
    jdk: pinned-version
    maven: repository-wrapper
  verify:
    command: ./mvnw -B -ntp clean verify
    require_generated_contract_tests: true
    fail_if_required_test_count_is_zero: true
  package:
    include_application_jar: true
    include_classifier_stubs_jar: true
  provenance:
    capture_git_sha: true
    capture_test_reports: true
    calculate_sha256: true
    create_release_manifest: true
  publish:
    target: staging-maven-repository
    immutable_coordinates: true

consumer:
  checkout:
    ref: immutable-consumer-commit
  resolve:
    stub: com.acme:order-service:1.4.2:stubs
    checksum: expected-stub-sha256
  test:
    command: ./mvnw -B -ntp clean verify
    use_stub_runner: true
    require_real_client_tests: true
  record:
    consumer_commit: true
    stub_coordinates_and_checksum: true
    test_report: true

release:
  require_producer_gate: true
  require_supported_consumer_matrix: true
  promote_staging_artifacts: true
  deploy_by_image_digest: true
  record_rollout_and_smoke_result: true
~~~

Đây là **pseudocode**, không chạy trực tiếp trên GitHub Actions/GitLab/Jenkins. Những key như `require_generated_contract_tests` chỉ có ý nghĩa khi được hiện thực thành script/assertion thực. CI provider phải thực sự chặn job tiếp theo nếu gate thất bại.

## 20. Thứ tự build, test và publish

Một release pipeline cần quyết định khi nào artifact được publish.

**Phương án A — staging trước, promote sau**

1. Producer build/verify và publish vào staging repository.
2. Consumer jobs tải artifact staging theo version cố định.
3. Compatibility matrix chạy.
4. Repository manager promote cùng staging repository nếu mọi gate đạt.

Ưu điểm: consumer test tải JAR qua đúng cơ chế Maven resolver sẽ dùng; release chưa được public trước khi gates hoàn tất.

**Phương án B — artifact handoff**

1. Producer build/verify và upload JAR `stubs` vào CI artifact store.
2. Consumer job tải đúng file, kiểm SHA-256 và cài vào Maven local hoặc staging repository tạm.
3. Consumer test chạy.
4. Sau khi pass, publish/promote đúng bytes đã handoff.

Ưu điểm: không cần publish sớm vào Maven repository. Nhược điểm: cần kiểm soát cách Stub Runner resolver tìm artifact và cách chuyển artifact giữa jobs.

**Không nên** build producer một lần cho test, sau đó build lại một lần khác chỉ để publish cùng tọa độ mà không đối chiếu source, toolchain, test reports và checksum. Đó là cách dễ tạo ra hai bộ bytes khác nhau dưới cùng tên release.

## 21. Consumer matrix và chính sách breaking change

Trước khi promote producer release, phân loại contract diff:

| Thay đổi | Phân loại sơ bộ | Bằng chứng cần |
| --- | --- | --- |
| Thêm optional response field | Có thể additive | Consumer cũ có bỏ qua unknown field? |
| Xóa required field | Thường breaking | Consumer versions còn dùng field? |
| Đổi JSON number thành string | Breaking với client strict/type-safe | DTO/schema/parser compatibility. |
| Đổi enum `PAID` thành `SETTLED` | Có thể breaking | Enum/switch behavior của consumer. |
| Đổi 200 thành 202 | Có thể breaking về workflow | Consumer xử lý async/pending thế nào? |
| Đổi error body/code | Có thể breaking | Error decoder mapping. |
| Đổi destination/schemaVersion của event | Có thể breaking | Listener/topic/schema support. |

Nếu thay đổi breaking, thiết kế **expand–migrate–contract**:

1. Expand: thêm API/event version mới, giữ bản cũ.
2. Migrate: cập nhật và deploy consumer.
3. Verify: chạy Stub Runner tests cho consumer versions được hỗ trợ và quan sát usage.
4. Contract: bỏ bản cũ sau khi policy EOL đạt.

Không đánh dấu consumer chưa kiểm là PASS. Ghi `NOT TESTED` và owner/quyết định ngoại lệ.

## 22. Deploy producer bằng image đã được xác minh

Sau khi producer và consumer gates đạt:

1. Promote artifact JAR `stubs` bất biến.
2. Promote image digest được build từ cùng producer source/build đã verification.
3. Tạo deployment revision chứa environment, region, digest, config version và thời điểm.
4. Chạy canary/smoke tests.
5. Theo dõi error rate, response schema, latency và consumer failures.
6. Hoàn tất rollout hoặc rollback về digest đã biết.

Ví dụ deployment manifest rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  annotations:
    example.org/source-commit: "a1b2c3d4e5f678901234567890abcdef12345678"
    example.org/build-run-id: "order-producer-483"
    example.org/release-version: "1.4.2"
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: registry.example.org/orders/order-service@sha256:<actual-digest>
          ports:
            - containerPort: 8080
~~~

Các annotation `example.org/*` là convention nội bộ minh họa, không được Spring Cloud Contract tự thêm. Manifest mô tả **ý định deploy**; để chứng minh runtime, còn cần rollout status và image ID/digest của pods đang chạy.

## 23. Theo dõi runtime để khép kín đường truy vết

Log có cấu trúc có thể ghi:

~~~json
{
  "timestamp": "2026-11-24T10:00:00Z",
  "service": "order-service",
  "environment": "production",
  "releaseVersion": "1.4.2",
  "gitCommit": "a1b2c3d4...",
  "buildRunId": "order-producer-483",
  "deploymentRevision": "orders-prod-r134",
  "traceId": "trace-abc123",
  "httpMethod": "GET",
  "httpRoute": "/api/orders/{id}",
  "httpStatus": 200
}
~~~

`traceId` nhận diện trace/request; `gitCommit`/`releaseVersion` nhận diện bản code; `deploymentRevision` nhận diện lần rollout. **Không dùng một ID cho cả ba mục đích**.

Để bảo vệ dữ liệu:

- Không log Authorization, cookies, JWT hoặc broker tokens.
- Không ghi raw customer payload/PII nếu không cần thiết.
- Dùng route template thay cho raw path có ID người dùng nếu phù hợp.
- Giữ retention/audit policy cho CI reports và deployment records.
- Đồng bộ timestamp giữa CI, registry và deploy system.

## 24. Incident drill: lần từ Billing error về producer contract

Giả sử sau rollout, Billing báo `amountMinor` deserialize lỗi.

Thực hiện:

1. Lấy **trace ID**, thời điểm, environment/region và Billing release.
2. Xác định Order Service deployment revision/image digest đã nhận request.
3. Tra release manifest từ digest → producer CI run → full Git SHA.
4. Xem contract diff của `get_paid_order.groovy`.
5. Kiểm generated producer test report: assertion cho `amountMinor` có kiểm JSON number không?
6. Xác định stub coordinates/checksum mà Billing CI đã dùng.
7. So checksum với artifact trong staging/release repository.
8. Kiểm consumer report: Billing commit nào đã test artifact đó?
9. Thu response thực ở staging hoặc sample đã redacted; xác nhận number/string.
10. Phân loại nguyên nhân: contract thiếu assertion, producer regression, artifact drift, image drift hay consumer DTO mismatch.
11. Chọn fix forward/rollback theo consumer support policy.
12. Cập nhật contract, tests và release manifest để lần sau truy lại được.

~~~mermaid
flowchart TD
    A["Billing parse failure + traceId"] --> B["Billing release / consumer commit"]
    A --> C["Order deployment revision / image digest"]
    C --> D["Release manifest"]
    D --> E["Producer Git SHA + contract diff"]
    D --> F["Stub coordinates + SHA-256"]
    E --> G["Generated producer test report"]
    F --> H["Billing Stub Runner report"]
    G --> I["Root cause and repair"]
    H --> I
~~~

Nếu không thể nối **producer image digest với stub checksum và source SHA**, đó là một khoảng trống của pipeline cần sửa, không phải lý do để đoán phiên bản.

## 25. Failure drills: cố tình làm pipeline thất bại

Thực hành các lỗi sau trên branch/fixture thử nghiệm:

| Drill | Cách tạo lỗi | Kết quả mong đợi |
| --- | --- | --- |
| Contract regression | Producer trả `amountMinor` dạng string | Generated producer test FAIL. |
| Contract coverage gap | Xóa contract cho 404 rồi đổi error behavior | Review/coverage gate nhận ra scenario thiếu; consumer error test FAIL nếu behavior thay đổi. |
| Consumer incompatibility | Billing DTO yêu cầu field không còn trong stub | Stub Runner consumer test FAIL. |
| Wrong stub version | Billing pin `1.4.1` thay vì `1.4.2` | Test/report ghi rõ version được dùng; behavior có thể khác. |
| Artifact overwrite | Thử ghi đè cùng release coordinates trong repository test | Repository policy từ chối hoặc checksum drift được phát hiện. |
| Stale local cache | Cài JAR cũ vào local repo | Checksum đối chiếu phát hiện không khớp expected. |
| Test bị skip | Bật skip flag trong nhánh thử | Gate test count/report chặn publish. |
| Image drift | Build image từ commit khác stub build | Manifest source identity không khớp, deploy gate chặn. |
| Wrong deployment | Deploy tag trỏ digest khác | Runtime/deployment record phát hiện digest khác expected. |
| Unchecked consumer | Bỏ một consumer khỏi matrix | Trạng thái NOT TESTED, không tự động PASS. |

Sau mỗi drill, khôi phục trạng thái đúng và ghi **lớp nào phát hiện lỗi**. Mục tiêu không phải làm mọi job đỏ, mà chứng minh lỗi bị chặn ở đúng gate với bằng chứng đủ rõ.

## 26. Bài tập mở rộng: thêm message contract

Sau khi HTTP pipeline hoạt động, mở rộng Order Service để phát event `OrderCreated`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    input {
        triggeredBy('publishOrderCreated()')
    }
    outputMessage {
        sentTo('orders.created')
        headers {
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
            header('contentType', 'application/json')
        }
        body(
            eventId: 'evt-42',
            orderId: 'ORD-42',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Các bước mở rộng:

1. Cấu hình messaging verifier/integration phù hợp transport đang dùng.
2. Base test trigger **publisher application thật**.
3. Receiver kiểm destination, headers và payload.
4. Generated producer message test phải chạy trước publish.
5. Consumer Stub Runner trigger label `orderCreatedV1`.
6. Billing listener test assert side effect nghiệp vụ.
7. Nếu dùng broker/serializer thật, thêm integration test cho bytes, schema registry, routing, ack/retry.
8. Ghi event contract version và adapter/broker test mode vào provenance.

**Không coi fake/in-memory message test là bằng chứng broker production đã được kiểm**. Ghi rõ mức test trong manifest.

## 27. Release checklist

| Nhóm | Điều kiện để tiếp tục |
| --- | --- |
| Contract source | Groovy/YAML được review, có owner và consumer impact. |
| Producer source | Full Git SHA xác định, workspace sạch/đã kiểm soát. |
| Toolchain | JDK, Maven Wrapper, plugin/BOM versions được pin hoặc ghi exact. |
| Generated tests | Được sinh, compile và chạy; test count hợp lệ. |
| Producer verification | Tất cả scenario bắt buộc PASS; mutation quan trọng FAIL đúng. |
| Stub packaging | JAR classifier `stubs` có mappings/contract mong đợi. |
| Artifact identity | Coordinates, checksum, producer CI run và source SHA nối được. |
| Repository | Staging/release policy bất biến; consumer read credentials hoạt động. |
| Consumer tests | Stub Runner dùng đúng version/checksum; client/listener thật được kiểm. |
| Compatibility matrix | Các consumer versions được hỗ trợ có kết quả hoặc exemption rõ. |
| Image identity | Image digest được build từ source/build đã xác minh. |
| Deployment | Deploy theo digest, có rollout revision và region. |
| Runtime | Smoke tests, logs/metrics/traces có release identity và redaction. |
| Rollback | Có digest bản tốt trước đó và quyết định rollback/migration. |
| Retention | Test reports, stub artifacts và release manifests được giữ theo policy. |

## 28. Tiêu chí nghiệm thu workshop

Workshop chỉ được coi là hoàn thành khi:

1. Order Service có ít nhất một success contract và một error contract.
2. Maven Plugin sinh generated producer tests; test runner thực sự chạy chúng.
3. Một mutation phá schema/semantics làm producer verification FAIL.
4. Build tạo JAR classifier `stubs` và artifact có version xác định.
5. SHA-256 được tính từ JAR thật và có thể đối chiếu sau khi tải từ staging.
6. Billing Stub Runner tải đúng stub artifact, gọi HTTP client thật và kiểm DTO/business fields.
7. Consumer CI report ghi consumer Git SHA, stub coordinates/checksum và test result.
8. Release manifest nối producer source/build/test/stub/image.
9. Deploy dùng image digest đã xác minh và tạo deployment revision.
10. Incident drill có thể lần từ trace/request đến contract source và test reports.
11. Không có credentials/PII trong contract, stub, manifest hoặc CI logs.
12. Consumer chưa kiểm được đánh dấu NOT TESTED/EXEMPTED thay vì PASS.

## 29. Câu hỏi tự kiểm tra

1. Producer generated test PASS chứng minh điều gì và không chứng minh điều gì?
2. Vì sao cần cả producer verification và consumer Stub Runner tests?
3. Maven artifact coordinates `com.acme:order-service:1.4.2:stubs` gồm những phần nào?
4. Vì sao checksum JAR cần được tính từ bytes thực thay vì chỉ lưu version?
5. `StubsMode.LOCAL` và `REMOTE` khác nhau ở cách tìm artifact như thế nào?
6. Vì sao consumer test phải dùng HTTP client/listener thật?
7. Làm sao chứng minh generated tests không bị skip hoặc không có test nào?
8. Tại sao producer stub JAR và producer image cần cùng source/build provenance?
9. Tại sao image digest đáng tin hơn image tag mutable?
10. Release manifest nên chứa những identity nào?
11. Vì sao không được ghi repository password hoặc JWT vào manifest?
12. Staging repository giúp đặt consumer gates trước release promotion như thế nào?
13. Khi consumer test trả 404, cần kiểm những dữ liệu request nào?
14. Vì sao ma trận consumer cần bao gồm phiên bản cũ còn được hỗ trợ?
15. Khi nào cần giữ API v1 trong quá trình phát hành v2?
16. Một producer image được deploy có thể khác build đã tạo stub trong trường hợp nào?
17. Correlation/trace ID khác Git SHA và deployment revision như thế nào?
18. Với messaging, vì sao producer test qua fake adapter chưa chứng minh broker serialization thật?
19. Khi nào một consumer được ghi NOT TESTED thay vì PASS?
20. Nếu incident không nối được image digest với stub checksum, pipeline đang thiếu loại bằng chứng nào?

**Ghi nhớ:** **Pipeline có thể truy vết phải chứng minh producer source nào đã được kiểm, generated tests nào đã chạy, JAR `stubs` bytes nào được consumer dùng, image digest nào được deploy và deployment revision nào phục vụ traffic.** Dùng Groovy/YAML DSL để định nghĩa hành vi; Contract Verifier để kiểm producer; Maven classifier `stubs` để phát hành mappings; Stub Runner để kiểm client/listener thật; checksum và release manifest để nối artifacts; compatibility matrix để bảo vệ các consumer versions; deployment evidence để khép kín đường truy vết. Khi tất cả các gate dùng cùng một artifact identity và cùng nguồn provenance, nhóm có thể phát hành độc lập, phát hiện API không tương thích trước rollout và điều tra incident bằng bằng chứng thay vì suy đoán.
