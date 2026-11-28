# Dựng broker tối thiểu và gọi thử GET /v2/catalog

## Mục tiêu và phạm vi

Trong module Spring Cloud Service Broker, service broker là ứng dụng đứng giữa nền tảng triển khai và hệ thống cung cấp dịch vụ. Broker công bố những dịch vụ có thể được cấp phát, mô tả các plan và tiếp nhận những yêu cầu vòng đời theo Open Service Broker API (OSB API).

Bài này dựng một broker tối thiểu bằng Spring Boot và Spring Cloud Open Service Broker, khai báo một catalog tĩnh, khởi động ứng dụng và gọi thử endpoint GET /v2/catalog. Đây là bước khởi tạo để xác nhận ba thành phần đã kết nối đúng:

1. Ứng dụng Spring Boot khởi động được.
2. Spring Cloud Open Service Broker nhận diện implementation của CatalogService và cung cấp endpoint OSB API.
3. Nền tảng hoặc công cụ HTTP có thể xác thực và đọc catalog ở đường dẫn /v2/catalog.

Phạm vi này chỉ kiểm tra khả năng công bố catalog. Broker chưa cấp phát database, chưa tạo binding và chưa thu hồi tài nguyên. Các thao tác đó cần service implementation, lưu trạng thái và backend adapter ở những bước tiếp theo.

Sau bài học, bạn có thể giải thích cấu trúc tối thiểu của một broker, khai báo service definition và service plan, chạy ứng dụng ở môi trường local, kiểm tra response HTTP và nhận biết các lỗi thường gặp khi endpoint catalog không hoạt động.

## 1. Các thành phần cần có

Một broker khởi tạo cần các thành phần sau:

| Thành phần | Vai trò |
|---|---|
| Spring Boot application | Khởi động ứng dụng, quản lý cấu hình và dependency injection |
| Spring Cloud Open Service Broker | Cung cấp tích hợp HTTP và các abstraction theo OSB API |
| CatalogService | Trả về danh sách service definition và plan |
| Spring Security | Xác thực nền tảng khi gọi broker |
| HTTP client | Gửi request kiểm tra GET /v2/catalog |

Luồng xử lý ở mức tối thiểu:

~~~mermaid
flowchart LR
    CLIENT[Nền tảng / curl] -->|HTTPS hoặc HTTP local| SECURITY[Spring Security]
    SECURITY --> API[OSB API Endpoint]
    API --> CATALOG[CatalogService]
    CATALOG --> MODEL[Catalog]
    MODEL --> RESPONSE[JSON Response]
    RESPONSE --> CLIENT
~~~

Spring Cloud Open Service Broker tích hợp các endpoint OSB API vào ứng dụng Spring. Vì vậy, implementation của broker tập trung vào các abstraction nghiệp vụ mà thư viện yêu cầu. Với bài này, ta chỉ cần cung cấp CatalogService để endpoint catalog có dữ liệu trả về.

Không cần tự tạo một REST controller có mapping trùng với /v2/catalog. Nếu tự xây endpoint riêng, ứng dụng có thể vô tình bỏ qua các quy tắc request, response, phiên bản giao thức hoặc xử lý lỗi mà thư viện đã cung cấp.

## 2. Chuẩn bị project Spring Boot

### 2.1. Yêu cầu môi trường

Chuẩn bị:

- JDK tương thích với phiên bản Spring Boot của project.
- Maven hoặc Gradle theo cách quản lý build hiện tại.
- Một IDE hoặc terminal để chạy ứng dụng.
- Công cụ gọi HTTP như curl, curl.exe trên Windows, Postman hoặc HTTP client trong IDE.

Chọn phiên bản Spring Boot và Spring Cloud Open Service Broker tương thích với nhau. Không lấy ngẫu nhiên phiên bản mới nhất của từng thư viện vì Spring Cloud phát hành theo các release train có ma trận tương thích riêng. Nếu project đã có Spring Cloud BOM, ưu tiên dùng dependency management của project. Nếu chưa có, hãy chọn release train tương thích với Spring Boot đang sử dụng và tham khảo hướng dẫn phiên bản của thư viện trước khi khóa version.

### 2.2. Thêm dependency

Với Maven, dependency chính của broker có dạng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-open-service-broker</artifactId>
</dependency>
~~~

Để bảo vệ endpoint bằng HTTP Basic trong môi trường thử nghiệm, thêm Spring Security:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Nếu project quản lý phiên bản Spring Cloud bằng BOM, phần dependency management có dạng khái quát:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>SPRING_CLOUD_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

SPRING_CLOUD_VERSION là chỗ giữ phiên bản release train tương thích với Spring Boot trong project. Không sao chép một version minh họa vào project mà chưa kiểm tra ma trận tương thích.

Với Gradle, dependency chính có dạng:

~~~groovy
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-open-service-broker")
    implementation("org.springframework.boot:spring-boot-starter-security")
}
~~~

Cách khai báo version hoặc BOM trong Gradle phụ thuộc vào plugin quản lý dependency mà project đang sử dụng. Giữ nhất quán với cấu hình build hiện tại.

## 3. Tạo ứng dụng Spring Boot

Một lớp main tối thiểu:

~~~java
package com.example.broker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServiceBrokerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceBrokerApplication.class, args);
    }
}
~~~

Spring Boot quét component trong package hiện tại và các package con. Vì vậy, nên đặt CatalogService implementation trong package com.example.broker hoặc một package con để component scan tìm thấy bean.

Cấu trúc mã nguồn minh họa:

~~~text
src/main/java/
└── com/example/broker/
    ├── ServiceBrokerApplication.java
    └── catalog/
        └── DemoCatalogService.java

src/main/resources/
└── application.yml
~~~

Đây là cấu trúc nhỏ để bắt đầu. Khi broker phát triển, có thể tách catalog, service instance, binding, domain, persistence và backend adapter thành các package riêng.

## 4. Khai báo catalog đầu tiên

### 4.1. Catalog gồm những gì?

Catalog là danh sách dịch vụ broker công bố cho nền tảng. Một catalog gồm một hoặc nhiều service definition. Mỗi service definition mô tả một loại dịch vụ và chứa các service plan có thể lựa chọn.

Các khái niệm:

- **Service definition:** định nghĩa sản phẩm, ví dụ dịch vụ PostgreSQL được quản lý.
- **Service ID:** định danh ổn định của service definition. Nền tảng dùng ID này trong các request vòng đời.
- **Service plan:** một cấu hình hoặc cấp dịch vụ, ví dụ development hoặc production.
- **Plan ID:** định danh ổn định của plan.
- **Bindable:** cho biết service có hỗ trợ tạo service binding hay không.

Trong ví dụ này, broker công bố một dịch vụ PostgreSQL với một plan development. Ta đặt bindable=false vì bài này chưa triển khai service binding. Catalog phải mô tả đúng khả năng hiện có của broker, không bật capability chỉ để làm ví dụ trông đầy đủ.

### 4.2. Cài đặt CatalogService

Tạo lớp DemoCatalogService:

~~~java
package com.example.broker.catalog;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;
import org.springframework.cloud.servicebroker.service.CatalogService;

import reactor.core.publisher.Mono;

@Service
public class DemoCatalogService implements CatalogService {

    private final Catalog catalog;

    public DemoCatalogService() {
        Plan developmentPlan = Plan.builder()
                .id("2b10d3a0-40a0-4b19-a0f4-12a9b8000001")
                .name("development")
                .description("PostgreSQL plan cho moi truong phat trien")
                .build();

        ServiceDefinition postgresql = ServiceDefinition.builder()
                .id("8b5d3d7a-1f10-4b2c-9e70-7f4e8d0a1001")
                .name("managed-postgresql")
                .description("PostgreSQL database duoc quan ly boi broker")
                .bindable(false)
                .plans(List.of(developmentPlan))
                .build();

        this.catalog = Catalog.builder()
                .serviceDefinitions(List.of(postgresql))
                .build();
    }

    @Override
    public Mono<Catalog> getCatalog() {
        return Mono.just(catalog);
    }
}
~~~

Implementation tạo catalog khi Spring khởi tạo bean và trả về catalog dưới dạng Mono. Đây là kiểu trả về reactive của Spring Cloud Open Service Broker. Với catalog tĩnh, Mono.just phù hợp vì dữ liệu đã có sẵn trong bộ nhớ.

Những điểm cần chú ý:

- Service ID và plan ID phải ổn định giữa các lần khởi động.
- Mỗi plan phải thuộc một service definition cụ thể.
- Tên và mô tả nên giúp người dùng hiểu mục đích của dịch vụ.
- bindable=false phản ánh việc chưa có luồng binding.
- Không tạo ID ngẫu nhiên trong mỗi lần gọi getCatalog; platform có thể lưu các ID để tham chiếu ở những request sau.

Nếu phiên bản thư viện trong project có thay đổi package hoặc chữ ký builder, đối chiếu API của đúng phiên bản dependency đang dùng. Không trộn class từ các phiên bản khác nhau.

### 4.3. Đăng ký CatalogService với Spring

Annotation @Service khiến Spring tạo bean cho DemoCatalogService. Spring Cloud Open Service Broker sử dụng bean CatalogService để lấy catalog khi nhận request GET /v2/catalog.

Một lỗi phổ biến là viết class đúng nhưng đặt ngoài vùng component scan hoặc quên annotation đăng ký bean. Khi đó endpoint có thể được tạo nhưng ứng dụng không tìm thấy implementation phù hợp để trả catalog.

Có thể dùng cấu hình @Bean thay cho @Service nếu muốn quản lý catalog ở một lớp cấu hình. Chỉ nên có một implementation CatalogService chính cho catalog mà broker cần công bố, trừ khi phiên bản thư viện và kiến trúc ứng dụng có chủ đích hỗ trợ cách phân tách khác.

## 5. Cấu hình cổng và xác thực local

Tạo file application.yml:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: service-broker
  security:
    user:
      name: broker-local
      password: local-dev-only
~~~

Với dependency Spring Security và cấu hình người dùng trên, Spring Boot có thể bảo vệ các endpoint HTTP bằng HTTP Basic theo auto-configuration mặc định. Khi gọi endpoint cần gửi đúng username và password.

Giá trị local-dev-only chỉ dùng để thử nghiệm trên máy cá nhân. Khi chạy ở môi trường dùng chung hoặc production, cấp secret qua biến môi trường hoặc secret manager, sử dụng TLS và cấu hình xác thực theo yêu cầu bảo mật của nền tảng.

Một số lưu ý:

- Không commit password thật vào repository.
- Không dùng tài khoản local chung cho nhiều nền tảng production.
- Giới hạn quyền của tài khoản broker ở đúng phạm vi cần thiết.
- Không tắt xác thực chỉ để làm request catalog chạy được.
- Khi triển khai sau reverse proxy, kiểm tra cấu hình TLS và chuyển tiếp header một cách an toàn.

Trong môi trường production, có thể cần một SecurityFilterChain riêng để chỉ định rõ cơ chế xác thực, quyền truy cập và chính sách CSRF cho các endpoint API. Cấu hình đó phải tương thích với phiên bản Spring Security đang dùng và cơ chế xác thực mà platform hỗ trợ.

## 6. Khởi động broker

Với Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với Maven trên Linux hoặc macOS:

~~~bash
./mvnw spring-boot:run
~~~

Nếu project dùng Gradle Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

~~~bash
./gradlew bootRun
~~~

Chọn lệnh tương ứng với build system thực tế của project. Khi ứng dụng khởi động thành công, log Spring Boot sẽ cho biết ứng dụng đã chạy và cổng HTTP đang lắng nghe. Nếu cổng 8080 đã được sử dụng, đổi server.port trong application.yml hoặc truyền cấu hình tương ứng khi chạy.

Khi ứng dụng không khởi động:

1. Kiểm tra phiên bản JDK và phiên bản Spring Boot.
2. Kiểm tra dependency Spring Cloud Open Service Broker đã được resolve.
3. Kiểm tra dependency management có xung đột phiên bản hay không.
4. Kiểm tra lỗi compile trong DemoCatalogService.
5. Kiểm tra bean CatalogService đã được component scan phát hiện.
6. Kiểm tra cổng server.port có bị tiến trình khác chiếm dụng hay không.

Không nên bắt đầu kiểm tra HTTP khi ứng dụng còn chưa khởi động hoàn tất.

## 7. Gọi thử GET /v2/catalog

### 7.1. Request bằng curl

Mở terminal khác với terminal đang chạy broker và gửi request:

~~~bash
curl -i -u broker-local:local-dev-only -H "Accept: application/json" -H "X-Broker-API-Version: 2.16" http://localhost:8080/v2/catalog
~~~

Header X-Broker-API-Version minh họa phiên bản OSB API mà client yêu cầu. Hãy thay giá trị này bằng phiên bản được hỗ trợ bởi phiên bản thư viện broker và platform đang tích hợp. Với môi trường local, HTTP được dùng để kiểm tra trên máy. Khi triển khai thực tế, endpoint broker cần được bảo vệ bằng HTTPS.

Trên Windows PowerShell, gọi curl.exe để sử dụng chương trình curl thay vì alias Invoke-WebRequest:

~~~powershell
curl.exe -i -u broker-local:local-dev-only -H "Accept: application/json" -H "X-Broker-API-Version: 2.16" http://localhost:8080/v2/catalog
~~~

Không đưa password thật vào lịch sử shell hoặc tài liệu chia sẻ. Có thể cấu hình biến môi trường riêng cho local và dùng cơ chế nhập secret an toàn của công cụ HTTP.

### 7.2. Response mong đợi

Nếu xác thực thành công và CatalogService đã được đăng ký, server trả HTTP 200 OK cùng JSON catalog. Cấu trúc response có dạng:

~~~json
{
  "services": [
    {
      "id": "8b5d3d7a-1f10-4b2c-9e70-7f4e8d0a1001",
      "name": "managed-postgresql",
      "description": "PostgreSQL database duoc quan ly boi broker",
      "bindable": false,
      "plans": [
        {
          "id": "2b10d3a0-40a0-4b19-a0f4-12a9b8000001",
          "name": "development",
          "description": "PostgreSQL plan cho moi truong phat trien"
        }
      ]
    }
  ]
}
~~~

Response thực tế có thể chứa thêm trường metadata hoặc capability tùy cấu hình và phiên bản thư viện. Điều cần xác nhận trong smoke test là:

- HTTP status là 200.
- JSON có mảng services.
- Service ID và tên service đúng như đã khai báo.
- Service có ít nhất một plan với plan ID ổn định.
- bindable là false vì chưa triển khai binding.
- Response không chứa password hoặc secret.

### 7.3. Kiểm tra bằng HTTP client

Trong Postman hoặc HTTP client của IDE, tạo request:

| Thuộc tính | Giá trị |
|---|---|
| Method | GET |
| URL | http://localhost:8080/v2/catalog |
| Authorization | Basic Auth |
| Username | broker-local |
| Password | Giá trị local password đã cấu hình |
| Accept | application/json |
| X-Broker-API-Version | Phiên bản OSB API được broker hỗ trợ |

Gửi request và đối chiếu response với catalog đã khai báo trong DemoCatalogService. Nếu sử dụng môi trường local, có thể giữ request trong collection để chạy lại sau khi thay đổi catalog.

## 8. Hiểu kết quả của smoke test

GET /v2/catalog là bước kiểm tra đầu tiên của broker vì nó xác nhận ứng dụng có thể công bố danh mục dịch vụ theo giao thức OSB API.

| Kết quả | Ý nghĩa có thể xảy ra | Hướng kiểm tra |
|---|---|---|
| 200 OK | Request được xử lý và catalog được trả về | Kiểm tra service ID, plan ID và capability |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực | Kiểm tra Basic Auth và secret local |
| 403 Forbidden | Đã xác thực nhưng không được phép truy cập | Kiểm tra cấu hình authorization |
| 404 Not Found | Đường dẫn không được ánh xạ | Kiểm tra starter, auto-configuration và path |
| 406 Not Acceptable | Server không đáp ứng media type được yêu cầu | Kiểm tra Accept header |
| 5xx | Lỗi trong ứng dụng hoặc xử lý catalog | Đọc log server và kiểm tra bean CatalogService |

Một số nguyên nhân cụ thể:

**401 Unauthorized:** request không có Authorization header hoặc username/password không khớp cấu hình. Nếu ứng dụng dùng Spring Security, kiểm tra cấu hình người dùng và xem có cấu hình bảo mật tùy chỉnh ghi đè auto-configuration hay không.

**404 Not Found:** dependency Open Service Broker có thể chưa được thêm đúng, auto-configuration không được kích hoạt hoặc URL bị thêm context path. Kiểm tra endpoint thực tế và log khởi động.

**500 Internal Server Error:** CatalogService có thể ném exception khi tạo catalog hoặc một giá trị bắt buộc bị thiếu. Xem stack trace phía server; không đưa stack trace vào response gửi cho platform.

**Catalog rỗng:** kiểm tra danh sách serviceDefinitions được truyền vào Catalog.builder. Catalog rỗng có thể là response hợp lệ về mặt cấu trúc nhưng không hữu ích cho người dùng nền tảng.

**Không thấy service vừa khai báo:** xác minh bean được Spring tạo, implementation getCatalog trả đúng object và ứng dụng đang chạy đúng profile/cấu hình.

## 9. Vì sao catalog phải ổn định?

Platform không chỉ hiển thị catalog một lần. Nó có thể đọc catalog khi đăng ký broker, khi làm mới danh sách service hoặc trong quá trình vận hành. Sau đó, platform gửi service ID và plan ID trong các request provision, update hoặc deprovision.

Nếu broker sinh ID mới mỗi lần khởi động, platform có thể không còn tham chiếu đúng các service instance đã tạo trước đó. Vì vậy:

- Dùng ID ổn định cho service definition và plan.
- Không tạo UUID ngẫu nhiên trong getCatalog.
- Không đổi ID chỉ vì đổi tên hiển thị.
- Nếu thay đổi ý nghĩa của plan, cân nhắc công bố plan mới.
- Chỉ công bố capability mà broker thực sự triển khai.

Tên service và plan có thể được cải thiện để dễ đọc, nhưng ID là định danh giao thức và cần được quản lý như dữ liệu tương thích lâu dài.

## 10. Từ broker tối thiểu đến broker có vòng đời

Sau khi GET /v2/catalog hoạt động, có thể mở rộng broker theo từng nhóm chức năng:

~~~mermaid
flowchart TD
    A[Spring Boot khởi động] --> B[CatalogService]
    B --> C[GET /v2/catalog hoạt động]
    C --> D[ServiceInstanceService]
    D --> E[Provision / Retrieve / Update / Deprovision]
    E --> F[Persistence và Operation State]
    F --> G[Async Worker, Retry, Reconciliation]
    G --> H[Binding Service]
    H --> I[Credentials và Unbind]
    I --> J[Backend Adapters]
    J --> K[Cloud Foundry / Kubernetes / Resource APIs]
~~~

Các bước mở rộng có thể được tổ chức như sau:

1. **Service instance:** triển khai service xử lý provision và deprovision; xác định service ID, plan ID, instance ID và parameters.
2. **Persistence:** lưu instance, tenant, plan, backend reference và trạng thái trong database.
3. **Async operation:** thêm operation record và worker khi backend mất nhiều thời gian.
4. **Idempotency:** xử lý request lặp bằng định danh ổn định, unique constraint và kiểm tra trạng thái backend.
5. **Binding:** tạo credentials riêng cho consumer và thu hồi credentials khi unbind.
6. **Backend adapter:** kết nối PostgreSQL, Redis, queue, object storage hoặc Kubernetes.
7. **Security và observability:** hoàn thiện xác thực, phân quyền tenant, secret management, audit, metrics và tracing.
8. **Platform integration:** đăng ký broker với Cloud Foundry hoặc xây dựng controller/adapter để tích hợp Kubernetes.

Mỗi giai đoạn nên có kiểm tra độc lập. Ví dụ, trước khi thử provision qua platform, kiểm tra catalog trả đúng service ID và plan ID; trước khi thử bind, xác nhận instance đã READY và backend có khả năng tạo credential riêng.

## 11. Giới hạn của broker trong bài thực hành

Broker trong bài mới chỉ công bố catalog. Việc GET /v2/catalog trả HTTP 200 không chứng minh toàn bộ vòng đời dịch vụ đã hoạt động.

Ở trạng thái này:

- Platform có thể đọc service definition và plan.
- Broker chưa có logic tạo service instance.
- Broker chưa lưu trạng thái instance hoặc operation.
- Broker chưa xử lý update và deprovision.
- Broker chưa tạo binding hoặc trả credentials.
- Chưa có adapter kết nối hệ thống tài nguyên phía sau.

Do đó, không nên đăng ký broker này như một dịch vụ production có khả năng provision thực tế. Khi platform gửi request vòng đời mà broker chưa triển khai, request có thể nhận lỗi hoặc chưa có service handler phù hợp.

Catalog tối thiểu là nền móng để xác nhận tích hợp giao thức và phát triển tiếp. Nó cũng giúp nhóm thống nhất tên dịch vụ, service ID, plan ID và capability trước khi triển khai backend.

## Kết luận

Một broker Spring Cloud tối thiểu cần ứng dụng Spring Boot, dependency Spring Cloud Open Service Broker, một implementation CatalogService và cấu hình xác thực cho request từ platform. Khi ứng dụng khởi động, thư viện cung cấp endpoint GET /v2/catalog và gọi CatalogService để tạo response JSON.

Smoke test thành công khi request được xác thực, endpoint trả HTTP 200 và response chứa đúng service definition cùng service plan đã khai báo. Đây là mốc khởi tạo quan trọng để tiếp tục xây dựng service instance lifecycle, operation bền vững, xử lý bất đồng bộ, idempotency, binding và backend adapter cho Cloud Foundry hoặc Kubernetes.
