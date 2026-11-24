# Lấy cổng hoặc URL stub được cấp phát động

Một bài kiểm thử consumer dùng **Spring Cloud Contract Stub Runner** thường cần gọi tới HTTP stub của producer. Nếu mỗi developer, mỗi CI job hoặc mỗi bộ test đều cố định `http://localhost:8089`, những lần chạy song song có thể tranh cổng, test gọi nhầm phiên bản stub hoặc gặp lỗi kết nối dù hợp đồng hoàn toàn đúng. **Cấp phát cổng động** giúp Stub Runner chọn cổng còn trống; nhiệm vụ của consumer test là **tra URL hoặc port thực sự được cấp**, rồi truyền địa chỉ đó vào mã HTTP client đang kiểm.

Bài thuộc chương **Stub Runner** của mô-đun **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract dùng Groovy/YAML DSL định nghĩa hành vi HTTP hoặc thông điệp, sinh kiểm thử producer, đóng gói và phát hành stub, rồi cho consumer chạy test qua Stub Runner trong CI. Trọng tâm ở đây là kỹ thuật **không hardcode cổng của HTTP stub**, sử dụng các API như `StubFinder` hoặc `@StubRunnerPort`, xử lý đúng vòng đời khởi tạo và phân biệt **tải artifact từ repository** với **địa chỉ server stub để gửi request**.

## 1. Tại sao Stub Runner nên dùng cổng động?

Giả sử **Order Service** (producer) phát hành artifact stub cho **Billing Service** (consumer). Một bản test cũ đặt cố định:

~~~yaml
orders:
  base-url: http://localhost:8089
~~~

và chạy HTTP client trỏ tới địa chỉ này. Nó chỉ hoạt động nếu **đúng stub cần kiểm** đã khởi động trên **đúng cổng 8089**. Các tình huống thường làm giả định này sai:

| Tình huống | Khi hardcode port | Khi lấy địa chỉ động từ Stub Runner |
| --- | --- | --- |
| Hai job CI trên cùng host | Có thể tranh cổng, báo `Address already in use`. | Mỗi lần chạy có thể được cấp cổng riêng. |
| Hai producer stubs trong một test | Nhầm địa chỉ Order Service và Customer Service. | Tra riêng URL theo tọa độ từng stub. |
| Chạy nhiều test song song | Các test có thể kết nối nhầm stub instance. | Mỗi test/context dùng địa chỉ instance tương ứng. |
| Đổi dải cổng cho CI | Phải sửa cấu hình client hardcode. | Test đọc port thực, không phụ thuộc một số cố định. |
| Local và CI khác môi trường | `localhost:8089` có thể không khả dụng. | Tra URL và xử lý hostname trong đúng môi trường chạy. |
| Stub chưa khởi động | HTTP client báo connection refused khó chẩn đoán. | API tra cứu và log Stub Runner giúp phân biệt lỗi startup với mismatch. |

**Một cổng động không làm HTTP contract thay đổi.** Hợp đồng vẫn là `GET /api/orders/42` với response đã thống nhất. Địa chỉ `http://localhost:NNNN` chỉ là **đường đi thử nghiệm** tới instance WireMock của stub.

## 2. Phân biệt artifact, stub instance, port và URL

Cần phân biệt bốn khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Artifact stub** | `com.acme:order-service:1.0.0:stubs` | Tọa độ Maven chỉ bộ hợp đồng/stub đã được producer đóng gói. |
| **Stub instance** | WireMock chạy từ artifact đó trong một test context | Process/server mô phỏng producer HTTP. |
| **Port đang lắng nghe** | `12543` | Số cổng thực tế Stub Runner chọn ở thời điểm khởi động. |
| **Base URL** | `http://localhost:12543` | Scheme + host + port để HTTP client gửi request. |

Một artifact **không mang theo một cổng HTTP cố định**. Cùng một `order-service-1.0.0-stubs.jar` có thể chạy ở cổng khác nhau giữa hai lần test. Vì thế, đừng ghi số cổng của lần chạy trước vào mã nguồn hoặc coi nó là một phần hợp đồng.

Nếu API client chỉ cần **port**, ta có thể tra port. Nếu client cần **địa chỉ đầy đủ**, ưu tiên lấy **base URL** bởi vì nó diễn đạt cả scheme và hostname, không buộc mọi môi trường đều là `localhost`.

~~~mermaid
flowchart TD
    A["Producer verification đạt"] --> B["Phát hành order-service:1.0.0:stubs"]
    B --> C["Consumer test yêu cầu Stub Runner nạp artifact"]
    C --> D["Stub Runner khởi động HTTP stub ở cổng khả dụng"]
    D --> E["StubFinder / @StubRunnerPort tra địa chỉ thật"]
    E --> F["Cấu hình OrderClient của consumer"]
    F --> G["Gửi HTTP request qua mã client thật"]
    G --> H["Stub trả response theo contract"]
    H --> I["Consumer test assert kết quả xử lý"]
~~~

**Trật tự quan trọng:** chỉ tra địa chỉ **sau khi** Stub Runner đã tạo stub instance cho test context. Nếu tạo và cấu hình HTTP client quá sớm với một URL giả, việc Stub Runner có khởi động sau đó cũng không tự thay base URL đã được client giữ.

## 3. Hợp đồng HTTP mẫu cần có trước khi chạy Stub Runner

Ta dùng một hợp đồng Order Service đơn giản, lưu tại `src/test/resources/contracts/orders/get_paid_order.groovy` trong producer:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service trả đơn hàng đã thanh toán'

    request {
        method 'GET'
        url '/api/orders/42'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'PAID')
    }
}
~~~

Hợp đồng này mô tả **hành vi HTTP**, không có cổng `8089` hay `12543`. Plugin Contract Verifier sinh producer test, kiểm Order Service thật, rồi đưa mapping vào artifact `stubs`.

Nếu dự án chọn YAML DSL, cùng hành vi có thể được biểu diễn:

~~~yaml
description: Order Service trả đơn hàng đã thanh toán
request:
  method: GET
  url: /api/orders/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Chỉ giữ **một phiên bản contract có hiệu lực** cho tình huống này trong build; đừng nạp cả Groovy và YAML tương đương rồi tạo test/mapping trùng nhau.

Ở producer Maven đã được cấu hình Contract Verifier, quy trình tham khảo:

~~~shell
mvn clean verify
mvn install
~~~

Lệnh thứ nhất phải thật sự chạy **generated producer tests**; lệnh thứ hai cài bản artifact `stubs` vào Maven local cho bài consumer test ở chế độ `LOCAL`. Trong pipeline thực, có thể cấu hình khác để tránh chạy trùng các bước lifecycle. Chỉ publish bản stub đáng tin sau khi producer verification đạt.

## 4. Cho Stub Runner tự chọn port

Trong dự án Billing Service, thêm dependency test `spring-cloud-starter-contract-stub-runner` với version tương thích Spring Boot/Spring Cloud đang dùng. Với JUnit 5 và Spring Boot Test, cấu hình:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {
    // Nội dung test sẽ bổ sung ở các mục sau.
}
~~~

Chuỗi `ids` gồm các phần:

~~~text
groupId:artifactId:version:classifier[:port]
com.acme:order-service:1.0.0:stubs
~~~

Trong cách khai báo này **không yêu cầu một port cụ thể** ở cuối tọa độ; Stub Runner có thể cấp một cổng khả dụng theo cấu hình. Ngược lại, ví dụ:

~~~java
ids = "com.acme:order-service:1.0.0:stubs:8089"
~~~

có nghĩa **cố định cổng 8089** cho instance đó. Cách ghi một port tĩnh hữu ích trong tình huống đơn giản, nhưng thường không phù hợp khi muốn tránh xung đột giữa nhiều test process.

**Cảnh báo phiên bản:** cú pháp tọa độ và quy tắc chọn cổng thuộc API/cấu hình Spring Cloud Contract đang dùng. Hãy kiểm log startup, địa chỉ stub thực và khả năng resolver của phiên bản dự án; không mặc định rằng **bỏ port** luôn tương đương việc **dùng port 0** trong mọi API của mọi framework.

## 5. Cách nên ưu tiên: tra base URL bằng StubFinder

Spring Cloud Contract Stub Runner cung cấp **`StubFinder`** để tìm stub đã khởi động. Thay vì đặt `http://localhost:8089` trong mã test, tra URL theo **groupId và artifactId**.

Ví dụ phần test:

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
class DynamicStubAddressTest {

    @Autowired
    private StubFinder stubFinder;

    @Test
    void resolvesRunningStubAddress() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        assertThat(url.getProtocol()).isEqualTo("http");
        assertThat(url.getPort()).isPositive();
        assertThat(url.toExternalForm()).startsWith("http://");
    }
}
~~~

**Điều quan trọng nhất là lời gọi `findStubUrl("com.acme", "order-service")`**. Kết quả là URL của **stub instance đã được Stub Runner khởi chạy**, không phải URL Maven repository chứa JAR. Nếu resolver không tìm thấy stub phù hợp, đừng tự động fallback sang `localhost:8089`: điều đó có thể che lỗi artifact chưa được nạp.

API tra cứu và kiểu trả về cần được đối chiếu với **phiên bản thư viện đã cài**. Những phiên bản Stub Runner phổ biến cung cấp `findStubUrl` nhận group/artifact và biến thể nhận Ivy notation; trong project thực, hãy dùng chữ ký có thật ở classpath. Ở ví dụ này, dùng hai tham số làm rõ danh tính producer, đặc biệt khi một test có nhiều artifact.

### 5.1. Khi nào dùng URL, khi nào dùng port?

Nếu HTTP client nhận một **base URL**, gọi:

~~~java
String baseUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
).toExternalForm();
~~~

Nếu chỉ cần số cổng, có thể lấy từ URL:

~~~java
int port = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
).getPort();
~~~

Nhưng `port` không đủ nếu stub chạy ở **host khác**, qua **HTTPS** hoặc qua một **proxy**. URL là thông tin phù hợp hơn cho ứng dụng được cấu hình qua thuộc tính `orders.base-url`. Hạn chế tự ghép `"http://localhost:" + port` khi có thể dùng URL do resolver cung cấp.

## 6. Thực hành kiểm mã client thật với URL động

Chỉ lấy được URL chưa phải một **consumer contract test** hoàn chỉnh. Ta cần **gửi request bằng chính mã OrderClient của Billing**, để phát hiện lỗi tạo path, parse JSON, mapping DTO hoặc xử lý status.

Một client Spring Framework 6.1+ dùng `RestClient`:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(RestClient.Builder builder, String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

Trong ứng dụng Billing thực, constructor này có thể được gọi qua `@Bean` hoặc một component factory, truyền base URL từ cấu hình môi trường. Trong test, **cùng class client** được khởi tạo bằng **URL Stub Runner vừa cấp**:

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
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    private StubFinder stubFinder;

    @Autowired
    private RestClient.Builder restClientBuilder;

    @Test
    void readsPaidOrderUsingAllocatedStubUrl() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub is unavailable"
        );

        OrderClient client = new OrderClient(
            restClientBuilder, stubUrl.toExternalForm()
        );

        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
    }
}
~~~

**Vì sao ví dụ này có ích?** Test dùng **chính lớp OrderClient** của ứng dụng, không chỉ gọi WireMock bằng một HTTP client được viết riêng rồi bỏ qua logic của Billing. Địa chỉ được truyền vào **sau khi** Stub Runner khởi động, nên không cần đoán số cổng.

Đây là **ví dụ có điều kiện**: cần Spring Boot Test, Spring Cloud Contract Stub Runner, AssertJ, RestClient và một `RestClient.Builder` được Spring Boot cung cấp. Trước khi test, producer phải cài hoặc publish JAR stub tương ứng. Nếu ứng dụng dùng `WebClient` hoặc `RestTemplate`, nguyên tắc vẫn giống nhau: tạo hoặc cấu hình **client thật** với base URL tra được.

## 7. Dùng @StubRunnerPort khi chỉ cần số cổng

Trong nhiều phiên bản Spring Cloud Contract, annotation **`@StubRunnerPort`** hỗ trợ inject cổng của một stub cụ thể vào test. Ý tưởng sử dụng:

~~~java
import org.springframework.cloud.contract.stubrunner.StubRunnerPort;

@StubRunnerPort("com.acme:order-service")
int orderServicePort;
~~~

Sau đó có thể cấu hình client:

~~~java
String localBaseUrl = "http://localhost:" + orderServicePort;
~~~

**Chọn khóa tra cứu phù hợp với phiên bản được cài.** Một số hình thức định danh sử dụng group/artifact, một số API hỗ trợ dạng khác; cách dùng annotation/package và khả năng inject của Spring Test cần được xác nhận bằng generated metadata hoặc API có trên classpath. Nếu `@StubRunnerPort` không phù hợp với cấu hình, **`StubFinder.findStubUrl(...)` là cách rõ ràng hơn** để vừa nhận diện artifact vừa lấy được URL.

**Giới hạn của port-only:** ghép `localhost` từ port chỉ đúng khi HTTP stub thực sự nghe trên **loopback của cùng môi trường thực thi**. Trong môi trường container, `localhost` bên trong container consumer **không phải** host CI hoặc container khác. Khi đó cần một URL có hostname mà client có thể truy cập.

## 8. Vòng đời Spring Test: tránh cấu hình base URL quá sớm

Đây là bẫy quan trọng hơn việc chọn API. Nếu OrderClient được khởi tạo cùng Spring application context bằng:

~~~java
@Value("${orders.base-url}")
String baseUrl;
~~~

thì thuộc tính `orders.base-url` phải đúng **trước khi bean được tạo**. Nhưng địa chỉ Stub Runner động thường chỉ biết **sau khi stub đã khởi động trong test context**. Không thể tùy tiện đặt `@DynamicPropertySource` rồi truy cập một instance `@Autowired StubFinder` chưa sẵn sàng từ một static method; cách này không có thứ tự khởi tạo bảo đảm.

Các lựa chọn hợp lý:

1. **Inject StubFinder vào test**, rồi khởi tạo **mã client thật** bằng URL thu được như mục 6. Đây là cách đơn giản và dễ kiểm nhất khi constructor của client nhận base URL.
2. Nếu consumer cần một **bean OrderClient quản lý bởi Spring**, thiết kế bean/factory trong test context **phụ thuộc vào StubFinder** và tạo client ở thời điểm resolver đã có URL; kiểm tra thứ tự initialization trong phiên bản framework đang dùng.
3. Với framework có cơ chế service discovery hoặc property integration chính thức của Stub Runner, có thể dùng **property do Stub Runner xuất ra** để inject địa chỉ; cần xác minh tên property và giai đoạn nó có mặt, không bịa một khóa rồi coi nó luôn tồn tại.
4. Với test chạy trên stub server **ngoài process**, cung cấp base URL từ CI/test configuration sau khi server đã sẵn sàng, thay vì giả định có một bean StubFinder local.

**Không làm:** khởi tạo OrderClient với `http://localhost:8089` trước rồi mong thay đổi field `baseUrl` của test sẽ cập nhật các request đã được client cấu hình. Phần lớn HTTP clients giữ cấu hình base URL ở thời điểm tạo; cần tái tạo client hoặc dùng abstraction cho phép đọc endpoint động có chủ đích.

### 8.1. Tránh RestAssured.baseURI/port toàn cục khi chạy song song

Một số bài test dùng:

~~~java
RestAssured.baseURI = "http://localhost";
RestAssured.port = orderServicePort;
~~~

Đây là **cấu hình static dùng chung**, dễ gây đụng nhau khi nhiều lớp test thay đổi `RestAssured.port` đồng thời. Nếu dùng Rest Assured, ưu tiên base URI ở **request specification riêng cho từng test**, hoặc cách tạo client độc lập để mỗi test gắn với đúng instance.

Tương tự, đừng ghi base URL vào một biến tĩnh dùng chung giữa các context nếu test có thể chạy trên nhiều worker/port khác nhau.

## 9. Khi có nhiều stub producer trong cùng bài test

Billing có thể vừa gọi **Order Service** vừa gọi **Customer Service**. Cấu hình Stub Runner với hai artifact:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.0.0:stubs",
        "com.acme:customer-service:2.3.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Tra địa chỉ theo **từng artifact**:

~~~java
URL ordersUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
);
URL customersUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "customer-service")
);

OrderClient orders = new OrderClient(
    restClientBuilder, ordersUrl.toExternalForm()
);
CustomerClient customers = new CustomerClient(
    restClientBuilder, customersUrl.toExternalForm()
);
~~~

`CustomerClient` ở đây là client giả định được dự án định nghĩa, có constructor nhận `RestClient.Builder` và base URL tương ứng. Mục tiêu là **đừng lấy một port rồi dùng chung cho hai producer**. Mỗi artifact có thể được Stub Runner khởi chạy ở một cổng khác.

Nếu hai producer trùng `artifactId` nhưng khác `groupId`, tra theo **cặp group/artifact** để tránh mơ hồ. Nếu một test nạp đồng thời hai **version khác nhau của cùng group/artifact**, hãy kiểm khả năng phân giải nhiều version và định danh chính xác theo API/version thư viện; đừng mặc nhiên tin hàm tra chỉ bằng group/artifact sẽ phân biệt được cả hai.

## 10. LOCAL, REMOTE và địa chỉ stub: hai loại “remote” khác nhau

Trong `@AutoConfigureStubRunner`, cấu hình:

~~~java
stubsMode = StubRunnerProperties.StubsMode.LOCAL
~~~

thường có nghĩa **tìm artifact stub trong Maven local**. Còn:

~~~java
stubsMode = StubRunnerProperties.StubsMode.REMOTE
~~~

thường có nghĩa **tải artifact stub từ Maven repository** đã cấu hình. Sau khi tải xong, Stub Runner có thể vẫn **khởi động HTTP WireMock trên máy chạy test**, và bạn vẫn phải **tra cổng động** theo cách tương tự.

| Câu hỏi | `LOCAL` | `REMOTE` |
| --- | --- | --- |
| Artifact `stubs` được tìm từ đâu? | Repository Maven local. | Repository Maven từ xa. |
| Có phải HTTP request đi tới Maven repository? | **Không.** | **Không.** |
| Stub server HTTP có thể chạy tại local test process? | Có. | Có. |
| Port của HTTP stub có thể động? | Có. | Có. |
| Consumer dùng gì để tìm URL? | `StubFinder` hoặc API tương ứng. | `StubFinder` hoặc API tương ứng sau khi nạp stub. |

Ví dụ cấu hình repository trong test:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/maven-releases"
)
~~~

Địa chỉ repository trên là **minh họa**, không phải URL thật. Tên repository, credentials và version do CI quản lý. **Đừng sử dụng `repositoryRoot` làm HTTP base URL của OrderClient**: repository trả artifact Maven, không phải giao diện `GET /api/orders/42`.

### 10.1. Stub Runner Server ở máy khác là câu chuyện riêng

Spring Cloud Contract còn có thể vận hành **Stub Runner Server** hoặc cấu hình stub được khởi động ngoài process của consumer test. Khi đó địa chỉ stub có thể là `http://stub-host:PORT` thay vì `localhost`. Không suy ra hostname từ một **số port**; lấy địa chỉ được service cung cấp hoặc cấu hình đúng host/port trong CI. Trong container, kiểm cả **địa chỉ lắng nghe** và **địa chỉ client truy cập được** vì chúng có thể khác nhau qua NAT/port mapping.

## 11. Port động và container/CI song song

Các môi trường thường gặp:

| Môi trường | Điểm cần lưu ý |
| --- | --- |
| Laptop developer | Có thể có ứng dụng khác chiếm 8089; dùng port động tránh tranh cổng. |
| CI runner chạy nhiều module | Mỗi job nạp artifact khác nhau; không chia sẻ cổng cố định hoặc biến static. |
| CI nhiều process trên cùng máy | Dùng port được Stub Runner cấp trong từng process; không truyền số cổng của process A cho B. |
| Consumer chạy trong Docker container | `localhost` là loopback **của container consumer**, không nhất thiết tới Stub Runner ở host. |
| Stub Runner chạy trong container riêng | Cần dùng DNS container/service name và port được publish/định tuyến đúng. |
| Kubernetes test namespace | Có thể dùng Service DNS/URL thay vì port localhost; cần chờ readiness và kiểm network policy. |

**Cổng động không giải quyết mọi lỗi mạng.** Nếu HTTP client không cùng network namespace với Stub Runner, URL `http://localhost:12543` có thể không đi tới stub dù server đã sẵn sàng trên host. Khi đó phải có **địa chỉ có thể route được** trong môi trường đang chạy; tránh thay số cổng một cách ngẫu nhiên để “thử may”.

### 11.1. Có cần sleep để đợi Stub Runner?

Trong tích hợp Spring Test đúng, việc tạo stub thuộc lifecycle của `@AutoConfigureStubRunner`. Test nên tra URL và gửi request khi context đã được cấu hình; nếu stub không lên, phải xem lỗi startup. Dùng `Thread.sleep(3000)` không chứng minh server sẵn sàng, còn khiến CI chậm và chập chờn.

Nếu ứng dụng chạy stub server ngoài Spring test lifecycle, nên có **readiness check có timeout hữu hạn** và chỉ thử endpoint phù hợp sau khi server báo sẵn sàng. Không dùng một sleep cố định thay thế kiểm readiness.

## 12. Khác biệt giữa “không tìm thấy stub” và HTTP 404 của stub

Ba loại lỗi thường bị nhầm:

| Triệu chứng | Ý nghĩa khả dĩ | Hành động |
| --- | --- | --- |
| `StubFinder` không tìm được URL | Artifact chưa nạp, tọa độ sai, Stub Runner không khởi động instance. | Kiểm `ids`, classifier/version, local/remote repo và log startup. |
| `Connection refused` khi gọi base URL | Không có server nghe tại host/port hoặc client ở sai network namespace. | Kiểm URL thực, readiness, firewall/container mapping. |
| HTTP `404` từ một WireMock server đang chạy | Request không khớp mapping **hoặc** mapping cố ý trả 404 nghiệp vụ. | So method/path/headers/body với generated mappings; nếu test lỗi nghiệp vụ, assert error body/code. |

Ví dụ client gọi:

~~~http
GET /api/orders/43
~~~

nhưng contract chỉ có `GET /api/orders/42`. Stub có thể trả 404 vì **không có mapping**, không có nghĩa Order Service thật đã kiểm database và kết luận đơn 43 không tồn tại. Nếu muốn test xử lý `ORDER_NOT_FOUND`, phải có contract lỗi tương ứng và assertion phân biệt no-match.

**Không giải quyết 404 mapping mismatch bằng cách đổi port** khi `StubFinder` đã trả URL đúng và HTTP server đã phản hồi. Lúc đó hãy kiểm request thực tế và mappings được sinh trong artifact.

## 13. Kiểm tra artifact và log khi URL resolver thất bại

Một quy trình điều tra có hệ thống:

1. **Producer verification:** hợp đồng Groovy/YAML đã được plugin nạp và generated producer tests đã thực thi?
2. **Artifact stub:** producer có tạo JAR mang classifier `stubs` cho đúng `groupId:artifactId:version`?
3. **Nơi lưu:** với `LOCAL` đã `mvn install` vào đúng Maven local của môi trường test? Với `REMOTE` đã publish vào repository và có quyền đọc?
4. **Stub Runner startup:** log cho biết artifact nào được tìm thấy, mapping nào được nạp, WireMock instance nào được khởi chạy?
5. **Tra URL:** `StubFinder.findStubUrl(groupId, artifactId)` trả đúng URL cho artifact mong muốn?
6. **HTTP reachability:** HTTP client chạy cùng network namespace hay cần hostname khác?
7. **Matching:** gửi method/path/body đúng hợp đồng và assert cả status lẫn dữ liệu nghiệp vụ.

Tránh đoán JAR ở vị trí `target`/`build` cụ thể của mọi dự án; đường dẫn artifact phụ thuộc Maven/Gradle và cấu hình. Thông tin bất biến cần đối chiếu là **tọa độ Maven, classifier `stubs` và version**.

### 13.1. Không tự sửa mapping được sinh để “chữa” URL

Địa chỉ HTTP server mà Stub Runner cấp **không nằm trong request matcher của hợp đồng**. Khi một client không gọi được vì port thay đổi, **sửa cấu hình client**, không sửa DSL `url '/api/orders/42'` thành `url 'http://localhost:12543/api/orders/42'`. DSL dùng path/request semantics, còn host/port thuộc môi trường test.

Nếu mapping không khớp request, hãy sửa contract hoặc mã client ở nguồn đúng chỗ và sinh lại artifact sau producer verification. Sửa tay file mapping trong JAR rồi publish lại dễ làm producer test và stub không còn cùng một nguồn hợp đồng.

## 14. Khi nào vẫn nên cố định port?

Cấp phát động thường tốt cho developer và CI song song, nhưng một cổng cố định có thể hợp lý khi:

- Bạn chạy một **Stub Runner Server phục vụ thủ công** trên máy, biết rõ port và tự quản lý việc chiếm cổng.
- Một hệ thống test bên ngoài **không hỗ trợ khám phá địa chỉ động**, trong khi môi trường bảo đảm cổng được dành riêng.
- Công cụ debug hoặc reverse proxy đã được cấu hình cố định trỏ tới stub server độc lập.

Khi chọn port cố định, hãy ghi rõ **ai sở hữu cổng, phạm vi tồn tại, cơ chế chống xung đột và cách kiểm readiness**. Đừng đem cách này làm mặc định cho mọi consumer test chỉ vì dễ viết `localhost:8089`.

Với một test Spring Boot thuần, để Stub Runner chọn port rồi tra URL bằng `StubFinder` thường ít phụ thuộc môi trường và dễ mở rộng hơn.

## 15. Đưa URL động vào CI để bảo vệ tương thích

Một pipeline đáng tin có thể chia thành hai nhánh được nối bằng artifact version:

~~~mermaid
flowchart TD
    A["Producer sửa API/contract"] --> B["Contract Verifier sinh producer tests"]
    B --> C{"Producer verification đạt?"}
    C -->|Không| D["Chặn publish"]
    C -->|Có| E["Build và publish order-service:version:stubs"]
    E --> F["Consumer CI tải artifact phiên bản xác định"]
    F --> G["Stub Runner khởi động WireMock ở port khả dụng"]
    G --> H["StubFinder trả base URL của instance"]
    H --> I["OrderClient dùng URL động"]
    I --> J["Test status/body/error theo contract"]
~~~

Checklist CI:

1. **Ghim version artifact** của producer stub; không dựa vào một “latest” thay đổi ngầm.
2. **Không dùng cổng cố định** nếu nhiều job có thể cùng chạy trong một network namespace.
3. **Không hardcode `localhost`** nếu consumer và stub chạy trong hai container khác network.
4. **Tra địa chỉ sau startup** và cấu hình client bằng URL đó, không bằng giá trị từ lần chạy trước.
5. **Giữ các test thật sự kiểm mã client**; không thay bằng một bài GET trực tiếp tới stub chỉ để xác nhận WireMock chạy.
6. **Kiểm cả negative path** (ví dụ 404 nghiệp vụ) bằng mapping và error payload riêng, tránh kết quả đạt giả.
7. **Chặn publish stub khi producer verification thất bại**; kết quả consumer test xanh với một stub chưa được xác minh không có giá trị bảo đảm producer thực.

Nếu đồng thời kiểm messaging contracts, nhớ rằng **Stub Runner có thể phát message mà không cần HTTP WireMock port cho kịch bản đó**. Cổng động trong bài này chủ yếu áp dụng **HTTP stub**; messaging cần cấu hình binder/adapter/destination và có thể dùng `StubTrigger` thay vì URL HTTP.

## 16. Bài thực hành: bỏ cổng cố định trong Billing Service

Trên một producer Order Service đã phát hành artifact `com.acme:order-service:1.0.0:stubs` và một consumer Billing Service:

1. **Tạo hợp đồng HTTP** `GET /api/orders/42` → `200` với `{"id":42,"status":"PAID"}` bằng Groovy hoặc YAML DSL.
2. **Chạy generated producer tests** để chứng minh Order Service thật đáp ứng contract, sau đó cài hoặc publish artifact `stubs`.
3. **Tạo `OrderClient` thật** với constructor nhận base URL thay vì hardcode `http://localhost:8089`.
4. **Cấu hình `@AutoConfigureStubRunner`** ở consumer dùng `ids` **không có port ở cuối**; chọn `LOCAL` khi artifact đã được cài vào Maven local.
5. **Inject `StubFinder`**, tra `findStubUrl("com.acme", "order-service")` sau khi test context đã khởi tạo.
6. **Gọi OrderClient với URL đã tra**, assert `id=42` và `status=PAID`. Không chỉ assert rằng URL có một port dương.
7. **Chạy hai bộ test đồng thời** trong điều kiện máy/CI hỗ trợ; xác nhận mỗi instance không tranh `8089` và client gọi đúng stub của mình.
8. **Thêm Customer Service stub**, tra hai URL theo group/artifact riêng và kiểm không dùng nhầm port của Order Service.
9. **Chuyển sang `REMOTE`** sau khi producer publish artifact vào repository, giữ nguyên logic tra URL, kiểm rõ rằng repository URL **khác** HTTP stub URL.
10. **Gây lỗi có chủ đích**: đổi `artifactId` trong `ids` hoặc gọi path ngoài contract; phân biệt lỗi StubFinder, connection refused và no-match 404, rồi khôi phục.
11. **Thử trên container/CI**, ghi rõ client và stub có cùng network namespace không; nếu không, cấu hình hostname/dịch vụ có thể truy cập được.

**Tiêu chí đạt:** cùng một bài consumer test có thể chạy khi WireMock được cấp **nhiều số cổng khác nhau** mà không sửa mã nguồn, vẫn gọi **mã HTTP client thật**, nhận đúng response contract và phân biệt lỗi **không tải được artifact**, **không kết nối được** với **request không khớp mapping**.

## 17. Câu hỏi tự kiểm tra

1. Cổng HTTP của một stub có nằm trong artifact `order-service-1.0.0-stubs.jar` hoặc hợp đồng `GET /api/orders/42` không?
2. Khi bỏ `:8089` khỏi `ids`, tại sao HTTP client không nên tiếp tục gọi `localhost:8089`?
3. `StubFinder.findStubUrl(...)` trả địa chỉ của **artifact repository** hay địa chỉ **stub server đang chạy**?
4. Vì sao lấy URL đầy đủ thường tốt hơn chỉ lấy số port?
5. `@StubRunnerPort` phù hợp trong trường hợp nào, và giới hạn của việc tự ghép `localhost` là gì?
6. Vì sao một phương thức static `@DynamicPropertySource` không thể tùy ý truy cập bean `@Autowired StubFinder` chưa được tạo?
7. Nếu có hai producer stubs cùng chạy, vì sao phải tra URL theo danh tính producer?
8. `StubsMode.REMOTE` có mặc định nghĩa là mọi request HTTP đều gửi tới Maven repository hoặc một stub host từ xa không?
9. Khi nào WireMock trả 404 vì request không khớp mapping, và điều đó khác gì lỗi 404 nghiệp vụ?
10. Cách nào giúp kiểm tra cổng động đã được sử dụng đúng mà vẫn bảo vệ logic của OrderClient?
11. Vì sao `localhost` trong một container consumer có thể không truy cập tới stub trên CI host?
12. Vì sao consumer test xanh với stub không đủ để bỏ qua generated producer verification trước khi publish?

**Ghi nhớ:** **Port của HTTP stub là chi tiết môi trường chạy, không phải thành phần của hợp đồng producer–consumer**. Hãy để Stub Runner cấp phát địa chỉ theo cấu hình, dùng **`StubFinder`** hoặc cơ chế tương ứng để lấy **URL/port sau startup**, rồi truyền địa chỉ đó vào **mã client thật**. Phân biệt rõ Maven repository `LOCAL/REMOTE` với HTTP server đang chạy, tránh hardcode port trong CI song song và kiểm request matching cùng response nghiệp vụ. Nhờ đó, consumer contract tests vẫn tái lập và phát hiện thay đổi API không tương thích mà không phụ thuộc một cổng số cố định.
