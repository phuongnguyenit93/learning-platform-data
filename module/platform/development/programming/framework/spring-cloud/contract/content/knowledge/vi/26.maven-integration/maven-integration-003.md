# Gắn sinh kiểm thử với lifecycle Maven

Khi dùng **Spring Cloud Contract**, việc đặt một file hợp đồng Groovy hoặc YAML vào dự án **producer** mới chỉ là bước mô tả giao tiếp. Để hợp đồng thật sự bảo vệ API, **Maven phải sinh mã kiểm thử từ hợp đồng trước khi biên dịch test**, chạy mã đó trên implementation của producer, rồi chỉ đóng gói/phát hành stub khi các kiểm tra bắt buộc đạt. Nếu goal sinh test chạy quá muộn hoặc không được gắn vào lifecycle, Maven có thể báo `BUILD SUCCESS` dù **không có một generated contract test nào được thực thi**.

Bài thuộc chương **Tích hợp Maven** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun hướng dẫn kiểm thử hợp đồng giữa producer và consumer bằng Groovy/YAML DSL cho HTTP hoặc thông điệp, sinh producer tests, phát hành stub, sử dụng Stub Runner và tích hợp CI để phát hiện thay đổi API không tương thích. Trọng tâm bài này là **cơ chế gắn plugin goals vào Maven lifecycle**, kiểm đường đi từ `generate-test-sources` đến `test`/`package`, và thiết kế cổng chặn phát hành đáng tin cậy.

Các ví dụ sử dụng **Spring Boot + Spring MVC + JUnit 5** với `spring-cloud-contract-maven-plugin` để minh họa. Tên goal và mặc định phase nên được kiểm theo **phiên bản plugin mà dự án cài**, vì cấu hình plugin và cách sinh/đóng gói artifact có thể thay đổi giữa các dòng Spring Cloud Contract.

## 1. Phân biệt hợp đồng, goal, phase và lifecycle

Maven dùng một **lifecycle** gồm các **phase** có thứ tự. Một **plugin goal** có thể được gắn vào một phase. Khi chạy Maven tới phase đó, các phase trước nó trong cùng lifecycle sẽ được thực hiện theo thứ tự.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Hợp đồng** | `src/test/resources/contracts/orders/get_order.groovy` | Dữ liệu nguồn mô tả request/response hoặc thông điệp. |
| **Plugin** | `spring-cloud-contract-maven-plugin` | Mã build hỗ trợ chuyển hợp đồng thành generated tests/stubs. |
| **Goal** | `generateTests` | Một công việc cụ thể do plugin thực hiện. |
| **Phase** | `generate-test-sources` | Một vị trí trong thứ tự Maven lifecycle. |
| **Lifecycle** | `default` | Chuỗi phase từ đầu tới `package`, `verify`, `install`, `deploy`. |
| **Test runner** | Maven Surefire | Biên dịch/chạy test ở phase thích hợp thông qua các goal tương ứng. |

**Không nhầm `generateTests` với phase `test`.** `generateTests` tạo **source code kiểm thử**; phase `test` mới là nơi Surefire thông thường **chạy test đã biên dịch**. Nếu đã sinh mã nhưng không chạy, producer chưa được xác minh.

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["generate-test-sources: generateTests"]
    B --> C["process-test-resources: convert"]
    C --> D["test-compile: biên dịch generated tests"]
    D --> E["test: Surefire chạy tests"]
    E --> F{"Producer verification đạt?"}
    F -->|Không| G["Dừng build; không phát hành"]
    F -->|Có| H["package: generateStubs tạo JAR stubs"]
    H --> I["verify: thêm các kiểm tra tích hợp nếu có"]
    I --> J["install / deploy"]
    J --> K["Consumer tải stubs bằng Stub Runner"]
~~~

Sơ đồ thể hiện **đường đi dự kiến của producer** khi plugin và test runner được cấu hình đúng. Maven chỉ tự chặn publish nếu pipeline thực thi đúng lifecycle, không bỏ qua test và không tách bước publish khỏi điều kiện verification.

## 2. Các phase Maven quan trọng đối với Contract Verifier

Trong `default` lifecycle của một dự án đóng gói `jar`, những phase sau liên quan trực tiếp đến producer contract tests:

| Thứ tự tương đối | Maven phase | Công việc cần quan sát |
| --- | --- | --- |
| 1 | `validate` | Kiểm project/POM cơ bản; có thể gắn quy tắc build riêng. |
| 2 | `generate-sources`, `compile` | Chuẩn bị và biên dịch source chính của producer. |
| 3 | **`generate-test-sources`** | Spring Cloud Contract **sinh Java/Groovy producer test** từ hợp đồng. |
| 4 | `generate-test-resources`, **`process-test-resources`** | Chuẩn bị test resources; plugin có thể **chuyển contract thành stub mapping**. |
| 5 | **`test-compile`** | Biên dịch các test đã được sinh và test do nhóm viết. |
| 6 | **`test`** | Surefire chạy unit tests và generated producer tests được nhận diện. |
| 7 | **`package`** | Tạo artifact ứng dụng và artifact `stubs` nếu cấu hình đúng. |
| 8 | **`verify`** | Chạy các bước kiểm tra sau package; có thể bao gồm Failsafe integration-test verification. |
| 9 | **`install`** | Cài các artifact vào Maven local repository. |
| 10 | **`deploy`** | Phát hành artifact vào repository từ xa đã cấu hình. |

**`mvn test` chưa chạy `package`**, nên không mặc định có JAR `stubs` mới. **`mvn verify` đi qua cả `test` và `package`**, thích hợp để chạy toàn bộ kiểm tra trước khi phát hành. **`mvn install`** và **`mvn deploy`** cũng đi qua những phase trước, trừ khi build bị skip hoặc profile thay đổi cấu hình.

Đặc biệt, Maven còn có các phase trung gian không được liệt kê hết trong bảng. Bài này chỉ chọn những điểm giúp giải thích **đúng thứ tự: sinh → biên dịch → chạy test → đóng gói → phát hành**.

## 3. Ba goal Spring Cloud Contract thường dùng và phase mặc định

Ở các phiên bản Maven Plugin có goal tương ứng, tài liệu Spring Cloud Contract mô tả:

| Plugin goal | Phase mặc định | Kết quả chính | Quan hệ phụ thuộc |
| --- | --- | --- | --- |
| **`generateTests`** | **`generate-test-sources`** | Tạo source của **producer verification tests**. | Cần contract và base test phù hợp để biên dịch/chạy được. |
| **`convert`** | **`process-test-resources`** | Chuyển hợp đồng thành **stub mappings/resources**. | Cần contract được tìm thấy và định dạng được hỗ trợ. |
| **`generateStubs`** | **`package`** | Đóng gói JAR stub từ resources đã chuyển đổi. | **`convert` phải chạy trước**. |

Những tên goal ở trên dùng chính xác chữ hoa/thường theo ví dụ của Maven Plugin. **Không có nghĩa mọi phiên bản plugin đều có goal tên `packageStubs`**; với tổ hợp goal đang mô tả, công việc tạo JAR là **`generateStubs`**.

Các goal khác như `run`, `help` hoặc hỗ trợ đẩy stub lên SCM có mục đích riêng. `run` dùng để chạy stubs, không thay cho `generateTests` hoặc việc chạy producer tests trong build.

**Một chi tiết dễ bỏ sót:** gắn goal vào phase **không đủ** nếu Surefire không nhận generated class, generated test bị skip hoặc plugin không tìm thấy hợp đồng. Phải kiểm **test report** chứ không chỉ kiểm Maven đã thực thi goal.

### 3.1. Vì sao `convert` phải đi trước `generateStubs`?

Hợp đồng có thể được viết bằng Groovy/YAML DSL, trong khi HTTP Stub Runner thường sử dụng **WireMock mappings** để trả response. `convert` tạo tài nguyên stub cần thiết; `generateStubs` sau đó **đóng gói tài nguyên đã chuyển đổi**. Nếu chỉ gọi `generateStubs` trên một thư mục chưa từng được `convert` chuẩn bị, bạn có thể nhận lỗi hoặc một artifact không có nội dung mong đợi.

Với **messaging-only contracts**, thông tin được đóng gói có thể khác HTTP mappings: label, destination, headers và payload có thể được Stub Runner xử lý qua messaging adapter. Đừng chỉ tìm `mappings/*.json` rồi kết luận không có stub.

## 4. POM producer tối thiểu: dependency và plugin

Ví dụ dự án `com.acme:order-service:1.0.0`, dùng Spring Boot 3.3.x và Spring Cloud 2023.0.x minh họa. Phần sau là **một POM tham khảo** có đủ vị trí cho BOM, dependencies và plugin:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2023.0.4</spring-cloud.version>
        <spring-cloud-contract.version>4.1.5</spring-cloud-contract.version>
    </properties>

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

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-contract-verifier</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-contract-maven-plugin</artifactId>
                <version>${spring-cloud-contract.version}</version>
                <extensions>true</extensions>
                <configuration>
                    <testFramework>JUNIT5</testFramework>
                    <testMode>MOCKMVC</testMode>
                    <baseClassForTests>
                        com.acme.orders.ContractTestBase
                    </baseClassForTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Cảnh báo về phiên bản:** ba số phiên bản trên là ví dụ của một hệ Spring Boot/Spring Cloud Contract gần nhau, **không phải khẳng định mọi patch trong các dòng đó tương thích hoặc là phiên bản mới nhất**. Trước khi áp dụng, hãy đối chiếu release train và ma trận tương thích của dự án; không tùy tiện nâng riêng plugin trong khi giữ starter/BOM quá cũ.

### 4.1. Phân biệt dependency và Maven Plugin

| Thành phần POM | Vai trò |
| --- | --- |
| `spring-boot-starter-web` | Chạy Spring MVC producer thật. |
| `spring-boot-starter-test`, scope `test` | Spring Test, JUnit Jupiter, MockMvc và các test utilities phù hợp. |
| `spring-cloud-starter-contract-verifier`, scope `test` | Các thành phần cần để biên dịch/chạy generated producer tests. |
| `spring-cloud-contract-maven-plugin` trong `build/plugins` | Thực hiện các goal **sinh test, convert và đóng gói stub**. |
| `spring-cloud-dependencies` BOM | Quản lý versions của nhóm Spring Cloud dependencies. |
| `spring-cloud-contract.version` | Chọn version của **build plugin**, vốn không tự được BOM thay thế trong phần `<version>` của plugin. |

Chỉ khai báo Verifier starter mà **không có Maven Plugin** có thể khiến không có generated test nào được sinh. Ngược lại, có Maven Plugin nhưng thiếu test dependencies hoặc base test có thể gây lỗi compile/runtime. Cả hai phần đều cần được cấu hình có chủ đích.

## 5. Dùng `<extensions>true</extensions>` để tích hợp lifecycle

Trong hướng dẫn Spring Cloud Contract Maven, cách phổ biến là khai báo plugin có:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>
            com.acme.orders.ContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

Với cấu hình plugin/lifecycle tương ứng, Maven có thể sinh tests và stubs khi chạy những phase thông thường, ví dụ `mvn clean verify`. **Không cần tự gọi `generateTests` trước từng lần chạy Maven** nếu plugin đã được tích hợp đúng vào lifecycle.

Đừng xem `<extensions>true</extensions>` là công tắc “tự động bảo đảm test đúng”: nó chỉ tham gia **cách Maven nạp plugin và tích hợp lifecycle**. Test runner vẫn cần biên dịch/thực thi generated tests. Hãy xác nhận qua log Maven/`effective-pom` rằng các goal đã thực sự được gắn.

### 5.1. Không khai báo thêm executions trùng một cách vô ý

Nếu đã có cấu hình extension tự gắn goals vào lifecycle, thêm một bộ `<executions>` giống hệt có thể khiến **goal chạy hai lần**, generated source bị ghi lại hoặc stubs được tạo lặp. Ngược lại, ở dự án có cấu hình lifecycle đặc thù, bạn có thể cần **executions tường minh**.

**Quy tắc:** chọn một chiến lược rõ ràng, rồi dùng Maven debug log/`effective-pom` và test report để xác minh. Không dán tất cả ví dụ plugin trên mạng vào cùng một POM.

## 6. Cách thay thế: ràng buộc các goal bằng `<executions>`

Nếu đội phát triển muốn **hiển thị rõ goal–phase trong POM** và không dựa vào binding tự động, một cấu hình thay thế có thể đặt các executions sau trong `spring-cloud-contract-maven-plugin`:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>
            com.acme.orders.ContractTestBase
        </baseClassForTests>
    </configuration>
    <executions>
        <execution>
            <id>generate-contract-tests</id>
            <phase>generate-test-sources</phase>
            <goals>
                <goal>generateTests</goal>
            </goals>
        </execution>
        <execution>
            <id>convert-contracts-to-stubs</id>
            <phase>process-test-resources</phase>
            <goals>
                <goal>convert</goal>
            </goals>
        </execution>
        <execution>
            <id>build-contract-stubs-jar</id>
            <phase>package</phase>
            <goals>
                <goal>generateStubs</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **phương án thay thế cho phần plugin ở mục 5**, **không phải một đoạn phải thêm dưới cấu hình đã tự gắn goals**. Trước khi dùng, kiểm rằng plugin phiên bản dự án hỗ trợ ba goal và chúng đang được thực thi **một lần** ở những phase mong đợi.

Vì sao chọn những phase đó?

- `generateTests` ở **`generate-test-sources`**: mã kiểm thử tồn tại **trước `test-compile`**.
- `convert` ở **`process-test-resources`**: mapping được chuẩn bị **trước khi đóng gói stub**.
- `generateStubs` ở **`package`**: tạo JAR classifier `stubs` từ resources mà `convert` đã tạo.

**Không gắn `generateTests` vào `verify`** nếu bạn kỳ vọng test được sinh sẽ được Maven `test` chạy trong cùng lượt build; `verify` diễn ra **sau `test`**, nên mã test mới tạo lúc đó đã quá muộn cho test phase hiện tại.

### 6.1. Khi nào nên dùng executions tường minh?

Nó có ích nếu project có parent POM tổ chức khác thông lệ, cần review chính xác phase–goal hoặc muốn kiểm soát bước convert/package. Tuy nhiên, explicit bindings **không thay thế** các yêu cầu khác: phải có contract, dependency, base test, compiler và Surefire.

Nếu phần plugin đã có trong **parent POM** và child POM khai báo thêm execution mới, Maven có thể **hợp nhất cấu hình**. Hãy kiểm `effective-pom` để tránh các execution được kế thừa và khai báo trùng.

## 7. Phân biệt `<pluginManagement>` và `<plugins>`

Đây là lỗi phổ biến trong multi-module Maven. Ví dụ parent POM chỉ:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-contract-maven-plugin</artifactId>
                <version>${spring-cloud-contract.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đoạn trên **quản lý phiên bản/cấu hình mặc định**, không nhất thiết có nghĩa goal sẽ được áp dụng vào mọi module. Module producer thường phải **kích hoạt plugin** trong `<build><plugins>`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Khi parent quản lý đầy đủ executions/configuration, child có thể kế thừa chúng theo Maven merge rules. **Không copy cấu hình plugin xuống mọi module** chỉ để “chắc ăn”; một module consumer-only không cần sinh producer tests nếu nó không sở hữu hợp đồng đầu ra.

## 8. Hợp đồng HTTP mẫu được Maven nạp

Tạo `src/test/resources/contracts/orders/get_paid_order.groovy` ở producer:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Đọc đơn hàng đã thanh toán'

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
            status: 'PAID'
        )
    }
}
~~~

Contract mô tả **HTTP observable behavior**: request là `GET /api/orders/42`; phản hồi là `200` và JSON `{"id":42,"status":"PAID"}`. Nó không chứa tên Maven goal, đường dẫn target hoặc port WireMock.

Nếu nhóm chọn **YAML DSL**, cùng hành vi có thể được mô tả trong tệp YAML riêng:

~~~yaml
description: Đọc đơn hàng đã thanh toán
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Trong build thực tế, **chọn một phiên bản hợp đồng có hiệu lực cho cùng tình huống**, không để cả Groovy và YAML tương đương bị plugin nạp rồi tạo generated tests/stubs trùng.

### 8.1. Đường dẫn contract và cách nhóm test

Plugin thường quét thư mục:

~~~text
src/test/resources/contracts/
└── orders/
    └── get_paid_order.groovy
~~~

Cấu trúc thư mục có thể được dùng để **nhóm generated test classes/packages**. Không đổi lung tung đường dẫn giữa CI và IDE: nếu plugin quét nhầm thư mục, Maven vẫn có thể thực hiện các phase khác và bạn phải nhìn log/`failOnNoContracts` để biết chưa có contract nào được nạp.

Khi hợp đồng nằm trong repository hoặc module khác, plugin có các cách cấu hình tải contract. Tuy nhiên, trong bài này ta tập trung vào **contracts nằm cùng producer** để nhìn rõ lifecycle; cách dùng external contracts cần cấu hình repository/version tương ứng và không tự suy rằng một dependency khai báo bất kỳ sẽ được plugin đọc làm contract source.

## 9. Producer thật và lớp base test để generated tests chạy được

Tạo ứng dụng Spring Boot có `@SpringBootApplication`, ví dụ `com.acme.orders.OrderApplication`. Một controller phục vụ contract:

~~~java
package com.acme.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderView getOrder(@PathVariable long id) {
        if (id != 42L) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new OrderView(42L, "PAID");
    }

    public record OrderView(long id, String status) {}
}
~~~

Controller này dùng ID 42 cố định **chỉ để minh họa cơ chế build**; ứng dụng thật cần service, repository, dữ liệu và auth theo yêu cầu.

Tạo `src/test/java/com/acme/orders/ContractTestBase.java`:

~~~java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void configureMockMvc() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Khi `testFramework=JUNIT5` và `testMode=MOCKMVC`, generated tests phải có cách truy cập Spring MVC test context. `ContractTestBase` chuẩn bị `MockMvc` và kết nối `RestAssuredMockMvc`. Nếu producer cần dữ liệu `Order 42` trong database hoặc token xác thực, base test còn phải chuẩn bị fixture và security phù hợp **trước request**.

**Maven Plugin không tự sinh toàn bộ môi trường nghiệp vụ.** Nếu `GET /api/orders/42` trả 404 do database chưa được seed, đó có thể là lỗi fixture; nếu controller đổi JSON field `status` thành `state`, đó có thể là lỗi producer vi phạm hợp đồng. Phải phân biệt để sửa đúng nguồn.

## 10. `mvn test`, `mvn package`, `mvn verify`, `mvn install` khác nhau

| Lệnh | Phần lifecycle chạy tới | Dùng khi | Điều không nên suy ra |
| --- | --- | --- | --- |
| `./mvnw clean test` | Đến `test` | Sinh, biên dịch và chạy generated producer tests. | Chưa nhất thiết tạo JAR `stubs` vì chưa tới `package`. |
| `./mvnw clean package` | Đến `package` | Chạy test rồi đóng gói app và stubs. | Chưa chạy những integration verification ở các phase sau `package`. |
| **`./mvnw clean verify`** | Đến `verify` | Kiểm đầy đủ những goal/test được gắn tới `verify`, trước publish. | Không tự publish artifact lên repository. |
| `./mvnw install` | Đến `install` | Cài artifact vào **Maven local** để consumer test `LOCAL` dùng. | Không gửi artifact tới repository dùng chung của CI runner khác. |
| `./mvnw deploy` | Đến `deploy` | Phát hành artifact theo `distributionManagement`/Maven deploy config. | Không bảo đảm pipeline tốt nếu bỏ qua tests hoặc bản artifact chưa được xác minh. |

`./mvnw` là **Maven Wrapper** của dự án. Trên Windows có thể dùng `mvnw.cmd`; nếu không có wrapper thì dùng lệnh `mvn` tương ứng phiên bản Maven đã kiểm.

Một phiên chạy minh họa:

~~~shell
./mvnw clean verify
~~~

Không nên chạy `generateTests` trực tiếp rồi nghĩ Maven đã hoàn tất test; chỉ sinh source chưa đủ. Nếu dự án đã gắn goal vào lifecycle, lệnh `verify` là một cách thực hiện **nguyên chuỗi công việc**.

### 10.1. Gọi trực tiếp plugin goal khác việc chạy phase

Ví dụ:

~~~shell
./mvnw spring-cloud-contract:generateTests
~~~

đề nghị plugin **sinh test**. Nó không có nghĩa Maven sẽ tự chạy toàn bộ các phase `test-compile`, `test`, `package` và `verify`. Tương tự:

~~~shell
./mvnw spring-cloud-contract:convert
./mvnw spring-cloud-contract:generateStubs
~~~

đề nghị chuyển đổi và đóng gói tài nguyên stub theo goal, nhưng không phải quy trình kiểm producer đầy đủ. `generateStubs` cần dữ liệu mà `convert` tạo trước đó; các lệnh gọi trực tiếp cần cấu hình và thứ tự phù hợp.

Để plugin prefix `spring-cloud-contract:...` được Maven nhận diện, môi trường có thể cần cấu hình `pluginGroups` hoặc khai báo plugin phù hợp trong project. Nếu prefix không phân giải được, hãy gọi **fully qualified goal** như:

~~~shell
./mvnw org.springframework.cloud:spring-cloud-contract-maven-plugin:generateTests
~~~

**Không coi kết quả của lệnh gọi goal riêng lẻ là thay thế cho `./mvnw verify`.** Trong CI, cần chạy cả test runner và kiểm report trước publish.

## 11. Generated test có được Maven Surefire chạy không?

Đường đi bình thường:

~~~text
Contract source (.groovy/.yml)
    -> generateTests ở generate-test-sources
    -> Java/Groovy generated test sources
    -> test-compile
    -> Surefire chạy trong test phase
    -> target/surefire-reports/
~~~

Những việc cần kiểm:

1. Plugin **tìm thấy hợp đồng** và sinh ra ít nhất một generated test.
2. Generated sources được **đưa vào Maven test source roots** để compiler nhìn thấy.
3. Test **compile thành công** với dependencies JUnit/Rest Assured/Spring Test tương thích.
4. Surefire **nhận diện test** đúng engine/framework.
5. Báo cáo có **số test đã chạy > 0**, không toàn `skipped`.
6. Khi chủ động làm sai response ở producer, ít nhất một test **FAIL**.

Một cấu hình Surefire khi dự án cần quản lý phiên bản trực tiếp:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <!-- Chọn phiên bản Surefire hỗ trợ JUnit Platform,
         phù hợp Spring Boot parent và Maven đang dùng. -->
</plugin>
~~~

Nếu dùng Spring Boot parent, nhiều plugin versions đã được quản lý; không cần override Surefire chỉ vì muốn dùng JUnit 5. Chỉ chỉnh version khi có lý do và sau khi kiểm tương thích. Các file báo cáo thường nằm dưới `target/surefire-reports`.

### 11.1. Tình huống sinh test rồi nhưng không được biên dịch

Trong một số IDE hoặc custom Maven build, thư mục generated test sources có thể **không được nhận diện** như test source root. Cách điều tra là xem **đường dẫn được plugin sinh trong `target/`**, rồi kiểm Maven compiler có đọc nó không. Có dự án sử dụng `build-helper-maven-plugin` để thêm test source root, nhưng **không nên thêm mù quáng** khi plugin đã tự đăng ký thư mục đúng.

Nếu thật sự cần build-helper, hãy gắn goal `add-test-source` vào `generate-test-sources` với **đường dẫn generated sources đúng của phiên bản plugin**:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>add-generated-contract-tests</id>
            <phase>generate-test-sources</phase>
            <goals>
                <goal>add-test-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>
                        ${project.build.directory}/generated-test-sources/contracts
                    </source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Điều kiện:** chỉ áp dụng đoạn này sau khi kiểm thư mục generated test thực tế **đúng đường dẫn đã ghi** và compiler chưa được plugin cấu hình. Tránh khai báo hai test source roots trùng nhau hoặc bám một đường dẫn mặc định của phiên bản khác.

## 12. Cách chứng minh lifecycle đã được gắn đúng

Đừng chỉ đọc POM bằng mắt. Hãy kiểm cấu hình Maven sau khi kế thừa parent/profile và thứ tự goal trong log:

~~~shell
./mvnw help:effective-pom
./mvnw clean verify
~~~

Nếu có thể lọc log hoặc dùng debug Maven, tìm:

~~~text
spring-cloud-contract:...:generateTests
spring-cloud-contract:...:convert
maven-compiler-plugin:...:testCompile
maven-surefire-plugin:...:test
spring-cloud-contract:...:generateStubs
~~~

**Đây là danh sách khái niệm để dò log**, không phải lời bảo đảm thứ tự dòng hoặc định dạng output của mọi Maven/Plugin version. Điểm cần xác nhận là generated sources tồn tại **trước test compilation**, tests được chạy **trước packaging** và `generateStubs` đóng gói **sau khi convert**.

Để tra mô tả goal của phiên bản đang dùng, plugin cung cấp lệnh help tương ứng:

~~~shell
./mvnw org.springframework.cloud:spring-cloud-contract-maven-plugin:help \
    -Ddetail=true -Dgoal=generateTests
~~~

Với shell Windows, có thể viết một dòng thay vì dùng dấu `\` xuống dòng của POSIX shell. Khi nâng plugin, chạy help tương ứng cho `convert` và `generateStubs` để xem **default phase, parameters và goal names** thực tế.

## 13. Artifact `stubs` được đóng gói như thế nào?

Sau khi lifecycle tới `package` và plugin packaging đúng, producer có thể có:

~~~text
target/
├── order-service-1.0.0.jar
├── order-service-1.0.0-stubs.jar
├── generated-test-sources/
├── stubs/
└── surefire-reports/
~~~

Đây là **sơ đồ minh họa**. Đường dẫn chi tiết phụ thuộc version, packaging và cấu hình Maven. Điều quan trọng là **JAR ứng dụng** và **JAR mang classifier `stubs`** là hai artifact khác mục đích.

Tọa độ Maven của stub:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.0.0
classifier = stubs
~~~

Viết gọn:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

Trong nhiều cấu hình plugin, goal `generateStubs` tạo/đính kèm artifact `stubs` ở phase `package`. Để xác nhận, cần **kiểm file JAR và Maven metadata**, không chỉ nhìn file `target/stubs`. Một lần build có thể sinh mappings nhưng chưa có classifier JAR nếu lifecycle dừng trước package hoặc packaging bị skip.

### 13.1. Kiểm nội dung JAR thay vì chỉ nhìn tên

Với JDK `jar` tool:

~~~shell
jar tf target/order-service-1.0.0-stubs.jar
~~~

HTTP stubs có thể chứa WireMock mappings và hợp đồng gốc theo cấu trúc `META-INF/...`. Consumer Stub Runner thường cần **các tài nguyên và đường dẫn phù hợp** với group/artifact/version. Không suy từ một JAR tên đúng rằng nó chứa **đúng phiên bản contract**: hãy xem nội dung và đối chiếu generated producer tests.

Với messaging contracts, stub JAR có thể chứa tài nguyên messaging contract thay vì mappings HTTP cho những sự kiện đó. **Không đếm `mappings` = 0 rồi kết luận packaging hỏng** nếu dự án chỉ có message contracts.

## 14. Vì sao `install` hoặc `deploy` phải chờ verification?

Về Maven lifecycle, `install` và `deploy` đến **sau `test`/`package`/`verify`**. Khi chạy một lệnh lifecycle bình thường mà **không skip**, test thất bại khiến build dừng trước install/deploy.

Nhưng các tình huống sau vẫn có thể tạo bản stub **chưa được kiểm đúng**:

- Người dùng chạy goal packaging trực tiếp nhưng **không chạy test**.
- CI tách publish thành job riêng và **không kiểm kết quả producer test job**.
- Build dùng `-DskipTests` hoặc `-Dmaven.test.skip=true`.
- Generated contract tests không được Surefire nhận diện.
- Contract không được plugin nạp, nhưng build vẫn được phép pass.
- Plugin/test run nằm trong profile không được bật ở CI.

Một cách vận hành an toàn là:

~~~text
validate POM & toolchain
  -> contract generation + producer tests
  -> inspect test reports / required test count
  -> package and verify
  -> attach stubs artifact
  -> install/publish/deploy
  -> consumer Stub Runner tests
~~~

**Không xem `mvn deploy` thành công là bằng chứng chất lượng nếu các bước kiểm ở trước đã bị vô hiệu hóa**. Cổng CI phải kiểm rõ ràng rằng producer verification được thực thi và đạt.

### 14.1. Phân biệt `-DskipTests` và `-Dmaven.test.skip=true`

Trong nhiều cấu hình Maven:

| Cấu hình | Tác động thường gặp | Rủi ro |
| --- | --- | --- |
| `-DskipTests` | Bỏ qua **thực thi** test, nhưng có thể vẫn biên dịch test. | Generated tests tồn tại nhưng không chạy. |
| `-Dmaven.test.skip=true` | Có thể bỏ cả **biên dịch và chạy test**. | Producer verification hoàn toàn bị bỏ qua. |
| Cờ skip của Contract Verifier plugin | Có thể bỏ sinh/convert/đóng gói theo tham số plugin. | Không có contract verification hoặc stub mong đợi. |

Đừng lấy một cờ skip dùng để tăng tốc local làm mặc định của job phát hành. Nếu cần build nhanh để xem lỗi compile, ghi rõ rằng artifact đó **chưa được producer verification chứng thực** và không đưa vào kênh publish chính thức.

## 15. Surefire và Failsafe: test thường hay integration test?

Maven có **Surefire** để chạy các unit/component tests tại `test` và **Failsafe** thường dùng cho integration tests thông qua các phase `integration-test`/`verify` khi được cấu hình.

| Thành phần | Phase thường gặp | Vai trò |
| --- | --- | --- |
| `maven-surefire-plugin` | `test` | Chạy test classes được nhận diện; thường gồm generated contract tests. |
| `maven-failsafe-plugin:integration-test` | `integration-test` | Chạy integration tests, có thể cần server/test containers. |
| `maven-failsafe-plugin:verify` | `verify` | Tổng hợp kết quả integration tests, đánh dấu build thất bại khi cần. |

Ví dụ Failsafe cho các bài integration test **được viết riêng**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
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

Đừng nhầm `generateTests` với `Failsafe integration-test`. **Generated contract tests được sinh từ DSL không tự được đổi thành Failsafe tests**. Nếu dự án muốn chạy chúng như integration tests, phải cấu hình tên class/runner/lifecycle thích hợp; nếu không, hãy để Surefire chạy chúng ở `test` như luồng phổ biến.

**Vì sao dùng `verify` thay vì gọi trực tiếp phase `integration-test`?** Với Failsafe, giai đoạn `verify` thực hiện kiểm kết quả để Maven trả trạng thái build thất bại đúng cách. Ngoài ra, các bước cleanup ở `post-integration-test` có thể cần chạy đúng vòng đời. Bám nguyên lifecycle thay vì chỉ gọi một goal lẻ giúp test environment được khởi động và dọn dẹp đúng.

## 16. Consumer Maven: Stub Runner là dependency test, không phải goal của producer

Sau khi Order Service đã publish `com.acme:order-service:1.0.0:stubs`, consumer Billing Service cần **Spring Cloud Contract Stub Runner** ở test scope:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **phần dependency của POM consumer**, cần Spring Boot parent/BOM, Spring Cloud BOM tương thích và các dependencies ứng dụng riêng. Consumer thường **không cần** `spring-cloud-contract-maven-plugin` chỉ để dùng stub đã được producer phát hành. Nếu Billing cũng là producer cho dịch vụ khác, nó có thể cần cả Verifier và Stub Runner với vai trò riêng.

Một client thật:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public class OrderClient {
    private final RestClient restClient;

    public OrderClient(String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return restClient.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

Consumer test bằng Stub Runner:

~~~java
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
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void readsPaidOrder() {
        URL baseUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        OrderClient client = new OrderClient(
            baseUrl.toExternalForm()
        );

        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42);
        assertThat(order.status()).isEqualTo("PAID");
    }
}
~~~

`StubsMode.LOCAL` phù hợp khi producer đã cài stub artifact vào **cùng Maven local repository** với consumer test; trong CI khác máy, dùng `REMOTE` và repository/credentials đã cấu hình. `StubFinder` trả URL của **stub server đã khởi động**, không phải URL Maven repository.

Điều test consumer chứng minh: **mã HTTP client của Billing** gửi và xử lý tương tác đúng với stub contract. Điều nó không chứng minh: implementation Order Service đã đáp ứng contract. Vì vậy, producer generated tests vẫn là cổng kiểm tra bắt buộc trước phát hành.

## 17. Multi-module Maven và reactor build

Trong một repository có nhiều module:

~~~text
commerce-platform/
├── pom.xml
├── order-service/
│   └── pom.xml
├── inventory-service/
│   └── pom.xml
└── checkout-service/
    └── pom.xml
~~~

Mỗi module có vai trò:

| Maven module | Vai trò | Maven cấu hình |
| --- | --- | --- |
| `order-service` | Producer của Order API | Contract Verifier plugin + contract files + base test. |
| `inventory-service` | Producer của Inventory API | Contract Verifier plugin riêng và bộ contract riêng. |
| `checkout-service` | Consumer của hai API | Stub Runner test dependency và tọa độ hai stub artifacts. |

Parent POM có thể tập trung quản lý plugin versions/BOM, nhưng **plugin execution nên có hiệu lực ở đúng producer modules**. Không áp dụng goal `generateTests` lên mọi module nếu module không có contract, vì plugin có thể báo không tìm thấy contract hoặc tạo bước build vô ích.

Khi dùng Maven reactor, có thể chạy:

~~~shell
./mvnw -pl order-service -am clean verify
~~~

`-pl` chọn project/module; `-am` có thể xây dựng các module **phụ thuộc cần thiết** trong reactor. **Không suy rằng `-am` tự chạy producer khác chỉ vì consumer sẽ tải stub của producer đó từ Maven repository**: quan hệ reactor dựa vào Maven dependencies và project graph. Một artifact có classifier `stubs` cần được **đóng gói và có thể phân giải** ở thời điểm consumer test yêu cầu.

**Rủi ro khi chạy reactor song song:** các goal Spring Cloud Contract Maven Plugin như `generateTests`/`convert`/`generateStubs` có phiên bản không được đánh dấu thread-safe. Khi bật `mvn -T`, phải kiểm tính an toàn của cấu hình, thư mục sinh file và build agent; không mặc nhiên cho rằng mọi goal sẽ an toàn khi chạy song song.

## 18. Messaging contracts cũng cần gắn vào lifecycle đúng

Một producer có thể phát `OrderCreated` thay vì chỉ cung cấp HTTP REST:

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
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-1042'
        )
    }
}
~~~

Goal `generateTests` vẫn cần chạy **trước test compilation**. Nhưng base test phải có `publishOrderCreated()` và hệ **MessageVerifier/test binder/messaging adapter** để generated test có thể quan sát sự kiện thực. `testMode=MOCKMVC` không thay thế cho messaging test infrastructure.

Ở phase `package`, stub artifact có thể chứa **messaging contracts** để Stub Runner phát message mẫu qua `StubTrigger`/adapter khi consumer test yêu cầu. Kịch bản messaging không tự trở thành WireMock HTTP endpoint. Trong CI, nên có thêm serialization/broker integration tests nếu consumer phụ thuộc bytes, headers, topic hoặc schema trên transport thực.

## 19. CI: buộc Maven sinh, chạy và kiểm trước khi publish

Một pipeline producer và consumer đáng tin:

~~~mermaid
flowchart TD
    A["Producer PR sửa code/contract"] --> B["Maven Wrapper + resolve POM/BOM/plugin"]
    B --> C["generateTests + convert"]
    C --> D["test-compile + Surefire"]
    D --> E{"Generated tests thật sự chạy và PASS?"}
    E -->|Không| F["Chặn publish"]
    E -->|Có| G["generateStubs ở package"]
    G --> H["verify + integration checks"]
    H --> I["Kiểm JAR stubs/classifier/version"]
    I --> J["install hoặc deploy theo CI"]
    J --> K["Consumer tải artifact bằng Stub Runner"]
    K --> L["Consumer test chạy mã client thật"]
~~~

Checklist CI nên có:

1. **Ghim phiên bản** Maven Wrapper/JDK, Spring Boot, Spring Cloud BOM và Spring Cloud Contract Plugin.
2. **Không skip producer tests** trong job phát hành; kiểm xem `-DskipTests`/`maven.test.skip`/plugin skip có được truyền ngầm không.
3. **Kiểm hợp đồng đã được phát hiện**, không chỉ có thư mục `contracts` rỗng trong source tree.
4. **Kiểm generated tests được biên dịch và thực thi**, báo cáo Surefire có số lượng thực tế.
5. **Dừng publish khi producer verification thất bại**; artifact tạo ra trước phase `verify` không tự động là artifact đã được xác minh.
6. **Đóng gói classifier `stubs` đúng tọa độ** và kiểm chứa tài nguyên tương ứng.
7. **Gắn artifact với commit/version xác định** để consumer có thể tái lập kiểm thử.
8. **Consumer CI dùng `LOCAL` hoặc `REMOTE` phù hợp**, không giả định hai runner chia sẻ cùng Maven local repository.
9. **Đánh giá tương thích ngược** khi thay body/headers/status/error/destination, không chỉ kiểm contract mới nhất.

Không cần chạy ba lệnh `mvn test`, `mvn package`, `mvn verify` tuần tự ở mọi job: gọi `verify` sẽ đi qua các phase trước đó. Tách job chỉ khi có mục tiêu như cache, báo cáo hoặc kiểm soát phát hành, và lúc đó phải quản lý artifact/điều kiện phụ thuộc rõ ràng.

### 19.1. Nếu CI có job publish riêng

Ví dụ tổ chức:

~~~text
job producer-verify:
    ./mvnw clean verify
    kiểm Surefire/Failsafe reports
    lưu artifact stubs đã xây dựng

job publish-stubs:
    chỉ chạy nếu producer-verify PASS
    kiểm hash/metadata của artifact được chuyển giao
    publish artifact đã được xác minh

job consumer-contract-test:
    tải stubs theo version chính xác
    chạy ./mvnw test
~~~

**Đừng build lại source khác hoặc skip test trong job publish mà vẫn gắn nhãn bản đã được xác minh**, trừ khi cơ chế phát hành chứng minh artifact được dùng là cùng nội dung từ bước verification. Một hash/commit/version có thể giúp truy nguyên nhưng **không thay thế kiểm thử**.

## 20. Các lỗi lifecycle thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `BUILD SUCCESS` nhưng không có contract test. | Plugin không gắn lifecycle, contract nằm sai thư mục hoặc test bị skip. | Xem `effective-pom`, goal log, `target/generated-test-sources` và Surefire report. |
| Test được sinh sau khi `test` đã chạy. | `generateTests` bị gắn nhầm phase quá muộn. | Dùng `generate-test-sources` trước `test-compile`. |
| Goal `generateTests` chạy hai lần. | `<extensions>true</extensions>` và `<executions>` chồng lấn, parent/child POM thừa hưởng trùng. | Kiểm `effective-pom` và execution IDs; chọn một chiến lược binding. |
| Test compile lỗi không thấy `ContractTestBase`. | Sai package/base class hoặc test sources chưa được nhận diện. | So `baseClassForTests` với file test và source roots. |
| Generated JUnit 5 tests không chạy. | Surefire/JUnit Platform engine/configuration hoặc naming không khớp. | Kiểm runner version, test count và reports. |
| `mvn test` PASS nhưng không có `stubs.jar`. | `generateStubs` thuộc `package`, `test` chưa chạy đến đó. | Chạy `mvn package/verify` và xem plugin execution. |
| `generateStubs` báo thiếu mappings. | Chưa chạy `convert` hoặc thư mục stubs bị đổi. | Kiểm goal `convert`, phase `process-test-resources`, stubs directory. |
| JAR `stubs` có tên đúng nhưng không có hợp đồng. | Contract không nạp, content bị loại hoặc packaging configuration sai. | Mở JAR và kiểm tài nguyên, plugin logs. |
| `mvn install` thành công nhưng consumer CI không tải được. | Consumer ở máy khác, repository chưa publish hoặc tọa độ classifier sai. | Dùng `deploy` và repository cấu hình phù hợp, kiểm `ids`. |
| Chạy `mvn -DskipTests deploy` publish stub chưa xác minh. | Test runner đã bị skip dù lifecycle đi qua. | Bỏ skip và đặt cổng CI kiểm test report. |
| Producer test fail sau khi thêm một contract mới. | Fixture, auth, base test hoặc implementation không đáp ứng. | Tách lỗi setup và vi phạm contract; không sửa contract chỉ để xanh. |
| WireMock trả 404 ở consumer test. | Request không match mapping, stub version khác hoặc 404 nghiệp vụ. | Kiểm request journal và mapping; assert error body khi 404 nghiệp vụ. |
| Multi-module chỉ chạy contract ở root. | Plugin áp dụng ở parent nhưng child producer không kích hoạt. | Kiểm plugin trong effective POM của đúng module. |
| Maven build song song có test chập chờn. | Plugin goal không thread-safe, chia sẻ target/cache/broker/port. | Cô lập state hoặc giới hạn parallel cho module liên quan. |

**Đường chẩn đoán:** POM thật sau kế thừa → plugin/goal binding → contract được tìm → generated source → test compilation → test execution/report → `convert` mappings → `generateStubs` JAR → repository/install/deploy → consumer Stub Runner.

## 21. Bài thực hành: từ POM đến JAR stub được kiểm

Hãy thực hành trên hai project `order-service` và `billing-service`:

1. **Tạo producer Maven project** dùng Maven Wrapper và bộ Spring Boot/Spring Cloud/Contract tương thích; đặt `groupId=com.acme`, `artifactId=order-service`, `version=1.0.0`.
2. **Khai báo BOM và dependencies**: Spring MVC, Spring Boot Test, `spring-cloud-starter-contract-verifier` ở test scope.
3. **Áp dụng Spring Cloud Contract Maven Plugin** trong `build/plugins`; chọn một trong hai kiểu cấu hình: extension tự gắn lifecycle hoặc executions tường minh. Không dùng cả hai mà chưa kiểm trùng goals.
4. **Viết hợp đồng Groovy** cho `GET /api/orders/42` → 200 JSON `PAID`; có thể so YAML tương đương nhưng chỉ nạp một nguồn.
5. **Tạo `OrderController` và `ContractTestBase`** khởi tạo MockMvc trong `@BeforeEach`; thiết lập fixture nếu implementation cần.
6. **Chạy `./mvnw clean test`**; kiểm rằng `generateTests` chạy trước `test-compile` và Surefire thật sự chạy test được sinh.
7. **Cố ý phá producer**: đổi `PAID` thành `PENDING` nhưng giữ hợp đồng; kiểm build FAIL rồi hoàn nguyên.
8. **Chạy `./mvnw clean verify`**; kiểm `convert` tạo mappings và `generateStubs` tạo JAR classifier `stubs` ở phase `package`.
9. **Kiểm `target/surefire-reports` và JAR content**; không coi file JAR tồn tại là đủ nếu test 0 hoặc bị skip.
10. **Chạy `./mvnw install`** trong producer đã xác minh để cài artifact local. Ở consumer, thêm `spring-cloud-starter-contract-stub-runner` vào test scope.
11. **Viết OrderClient thật và JUnit test**, dùng Stub Runner `LOCAL` và `StubFinder` lấy URL động, assert JSON `id=42`, `status=PAID`.
12. **Thử `REMOTE`** sau khi publish artifact lên Maven repository, chứng minh consumer chạy ở môi trường khác không cần producer process.
13. **Thử lỗi cấu hình có chủ đích**: gắn `generateTests` vào `verify` hoặc bật `-DskipTests` trong một nhánh thử nghiệm, quan sát test không bảo vệ producer như mong đợi rồi phục hồi.
14. **Đặt cổng CI**: producer `verify` PASS + generated test count > 0 → publish stubs versioned → consumer Stub Runner tests.

**Tiêu chí đạt:** Maven thực thi **đúng thứ tự sinh → biên dịch → chạy tests → convert/đóng gói → kiểm → phát hành**, producer contract test phát hiện thay đổi response không tương thích, và consumer tải đúng artifact `stubs` để kiểm mã client mà không khởi động Order Service.

## 22. Câu hỏi tự kiểm tra

1. Plugin goal và Maven phase khác nhau ra sao? Vì sao `generateTests` không đồng nghĩa phase `test`?
2. Ba goal `generateTests`, `convert` và `generateStubs` có công việc và phase mặc định nào?
3. Vì sao `generateTests` phải thực hiện trước `test-compile`?
4. Nếu gắn `generateTests` vào `verify`, producer generated tests có được Surefire chạy trong cùng lượt `mvn verify` không?
5. `<extensions>true</extensions>` có vai trò gì? Khi nào việc thêm `<executions>` có thể gây trùng?
6. Vì sao chỉ đặt plugin vào `<pluginManagement>` ở parent POM chưa chắc đã kích hoạt goal của module producer?
7. `mvn test` và `mvn package` khác nhau gì về việc tạo classifier JAR `stubs`?
8. Vì sao `mvn clean verify` là một đường chạy phù hợp trước khi phát hành?
9. Có thể kết luận producer tuân thủ hợp đồng chỉ từ dòng `BUILD SUCCESS` khi Surefire báo 0 generated tests không?
10. `spring-cloud-starter-contract-verifier` và `spring-cloud-contract-maven-plugin` có trách nhiệm khác nhau như thế nào?
11. Khi generated test không tìm được base class, bạn cần kiểm những gì ngoài hợp đồng Groovy?
12. Vì sao `generateStubs` cần tài nguyên từ `convert`?
13. `mvn install` khác `mvn deploy` như thế nào về nơi consumer có thể tải stub?
14. Vì sao `-DskipTests` làm yếu cổng kiểm thử dù Maven vẫn chạy tới phase `package` hoặc `deploy`?
15. `maven-failsafe-plugin` bổ sung điều gì so với Surefire và tại sao cần phase `verify`?
16. Trong reactor multi-module, vì sao plugin không nên được áp dụng bừa bãi lên consumer-only modules?
17. Khi consumer Stub Runner test xanh, tại sao vẫn cần producer verification để khẳng định contract đáng tin?

## 23. Nguồn tham khảo và giới hạn phiên bản

Tài liệu chính thức giúp đối chiếu **goal names, default phases và cấu hình plugin đúng theo phiên bản**:

- Spring Cloud Contract — **Maven Project**: https://docs.spring.io/spring-cloud-contract/reference/maven-project.html
- Spring Cloud Contract Maven Plugin — **Goals**: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/plugin-info.html
- Plugin goal `generateTests`: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/generateTests-mojo.html
- Plugin goal `convert`: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/convert-mojo.html
- Plugin goal `generateStubs`: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/generateStubs-mojo.html

Khi xem các trang `/docs/current/` được lưu theo một dòng plugin cụ thể, hãy **so số phiên bản trong phần “Full name” với phiên bản project của bạn**. Nếu khác, dùng Maven Plugin help của bản đang cài, tránh suy rằng tất cả tham số/phase vẫn giống nhau.

**Ghi nhớ:** **Sinh kiểm thử từ hợp đồng phải nằm trước biên dịch và chạy test trong Maven lifecycle; đóng gói stub chỉ đáng tin khi producer tests thật sự được thực thi và đạt**. Với Spring Cloud Contract, `generateTests` thường gắn `generate-test-sources`, `convert` gắn `process-test-resources` và `generateStubs` gắn `package`. Hãy dùng cấu hình plugin/lifecycle nhất quán, kiểm `effective-pom` và Surefire reports, không để skip tests hoặc duplicate executions che mất bước xác minh. Cuối cùng, chỉ cài/phát hành artifact `stubs` đã được kiểm để consumer sử dụng qua Stub Runner và CI phát hiện thay đổi API không tương thích.
