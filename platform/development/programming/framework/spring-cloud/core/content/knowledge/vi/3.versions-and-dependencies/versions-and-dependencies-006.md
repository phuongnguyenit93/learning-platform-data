# Nhận diện `spring-cloud-commons`, `spring-cloud-context` và `spring-cloud-starter`

Trong dự án Spring Boot dùng Spring Cloud, ba tên **`spring-cloud-commons`**, **`spring-cloud-context`** và **`spring-cloud-starter`** thường xuất hiện cùng lúc trong cây phụ thuộc. Chúng **không phải ba cách gọi của cùng một thư viện**. Hai artifact đầu là các thư viện nền tảng; artifact thứ ba là **starter** dùng để tập hợp những phụ thuộc chung. Nhận diện đúng vai trò giúp quyết định thêm dependency nào, hiểu tính năng nào thực sự có mặt trong ứng dụng và tìm nguyên nhân khi tích hợp thất bại.

Bài học nằm trong chương **Phiên bản và phụ thuộc** của module **SPRING_CLOUD_CORE**. Phạm vi là các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán: Spring Cloud Commons, Context, cấu hình bên ngoài, tương thích với Spring Boot, refresh scope, discovery, service registry, giao tiếp dịch vụ và cách xác minh những abstraction đã được kích hoạt.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhìn vào tọa độ Maven/Gradle để phân biệt **thư viện**, **starter**, **BOM** và **implementation**.
2. Giải thích chức năng của `spring-cloud-commons` và `spring-cloud-context`, đồng thời nêu những tính năng chúng **chưa tự cung cấp**.
3. Nhận diện `spring-cloud-starter` khác gì các starter tính năng như `spring-cloud-starter-config` và `spring-cloud-starter-loadbalancer`.
4. Đọc dependency tree để biết một artifact đi vào classpath trực tiếp hay gián tiếp, và xác định phiên bản thực tế được chọn.
5. Phối hợp **Spring Boot version** với **Spring Cloud release train** và kiểm chứng bằng Maven/Gradle cùng các phép thử hành vi.

## 2. Tên artifact nói lên điều gì?

Một dependency Maven thường được xác định bởi **groupId**, **artifactId** và **version**. Trong Spring Cloud, cả ba artifact của bài đều thường thuộc group **`org.springframework.cloud`**, nhưng `artifactId` khác nhau:

| Artifact | Dạng | Vai trò chính | Khi nào cần quan tâm? |
| --- | --- | --- | --- |
| `org.springframework.cloud:spring-cloud-commons` | Thư viện JAR | Các abstraction chung cho service discovery, service registry, service instance, client-side load balancing và một số tích hợp dùng chung | Khi viết mã dựa vào API chung hoặc tìm hiểu vì sao `DiscoveryClient` có trên classpath |
| `org.springframework.cloud:spring-cloud-context` | Thư viện JAR | Dịch vụ liên quan `ApplicationContext`, nguồn cấu hình, sự kiện thay đổi môi trường và refresh scope | Khi dùng `@RefreshScope`, làm mới cấu hình hoặc phân tích vòng đời context |
| `org.springframework.cloud:spring-cloud-starter` | Starter JAR | Gom các dependency nền tảng Spring Cloud, thường kéo theo Commons và Context cùng Spring Boot starter | Khi thiết lập nền tảng Cloud chung hoặc xem một starter tính năng đưa thư viện nào vào ứng dụng |
| `org.springframework.cloud:spring-cloud-dependencies` | BOM (POM) | Quản lý các phiên bản tương thích trong một Spring Cloud release train | Khi kiểm soát phiên bản dependency; **không phải thư viện runtime** |

> **Quy tắc nhận diện:** `commons` nói về **hợp đồng API dùng chung**; `context` nói về **ngữ cảnh ứng dụng và cấu hình**; `starter` nói về **tập hợp phụ thuộc để khởi tạo một khả năng**. Tên artifact giúp định hướng, nhưng hành vi thực tế còn phụ thuộc vào phiên bản, classpath, auto-configuration và cấu hình của ứng dụng.

Đừng nhầm:

- **`spring-boot-starter`** là starter nền tảng của **Spring Boot**; **`spring-cloud-starter`** là starter nền tảng của **Spring Cloud**.
- **`spring-cloud-dependencies`** quản lý phiên bản; nó không cung cấp `DiscoveryClient`, `@RefreshScope` hay HTTP client lúc chạy.
- **`spring-cloud-starter`** là tên **một artifact cụ thể**; mẫu tên **`spring-cloud-starter-*`** còn đại diện cho nhiều starter theo chức năng, chẳng hạn Config Client hoặc LoadBalancer.
- **`spring-cloud-commons`** và **`spring-cloud-context`** là những module thuộc hệ sinh thái/dự án mã nguồn Spring Cloud Commons, nhưng tên repository và tên Maven artifact là hai khái niệm khác nhau.

## 3. `spring-cloud-commons`: abstraction dùng chung

Một hệ thống phân tán có thể dùng Eureka, Consul, Kubernetes hoặc danh sách instance tĩnh để tìm dịch vụ. Nếu mã nghiệp vụ phụ thuộc trực tiếp vào API riêng của một nhà cung cấp, việc thay đổi hạ tầng discovery sẽ khó khăn hơn. Spring Cloud Commons đặt các **giao diện chung** giữa ứng dụng và implementation cụ thể.

### 3.1. Những khái niệm tiêu biểu

| Abstraction | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `DiscoveryClient` | Tra cứu service và các `ServiceInstance` bằng tên logic | Chỉ là hợp đồng tra cứu; chưa có nghĩa ứng dụng đã kết nối tới Eureka/Consul |
| `ReactiveDiscoveryClient` | Biến thể phản ứng cho việc tra cứu instance | Phù hợp với đường xử lý reactive khi có implementation tương ứng |
| `ServiceInstance` | Mô tả một đích có thể gọi (service ID, host, port, URI, metadata...) | Một instance có trong danh sách không bảo đảm còn sống |
| `ServiceRegistry` | Hợp đồng đăng ký/hủy đăng ký dịch vụ | Cần implementation registry và `Registration` phù hợp |
| `LoadBalancerClient` / các API liên quan | Hợp đồng hỗ trợ lựa chọn instance và gọi theo tên service | Thuật toán và bộ triển khai cụ thể cần thư viện/bean thích hợp |

Ví dụ Java minh họa cách ứng dụng phụ thuộc vào **hợp đồng chung**, không dùng SDK riêng của registry:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDirectory {
    private final DiscoveryClient discoveryClient;

    public InventoryDirectory(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> availableInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Trong đoạn trên, phương thức `getInstances("inventory-service")` chỉ yêu cầu danh sách instance. Nó **không tự gọi HTTP API của Inventory Service**, không tạo circuit breaker và cũng không bảo đảm instance trả về sẽ kết nối được.

Spring Cloud Commons có thể cấu hình một **`SimpleDiscoveryClient`** dựa trên danh sách instance khai báo trong properties khi không có discovery client dựa trên registry. Vì vậy, **thấy bean `DiscoveryClient` chưa đủ để kết luận Eureka, Consul hoặc registry bên ngoài đang hoạt động**.

### 3.2. Ví dụ: discovery tĩnh để tìm hiểu API

Khi dùng phiên bản Spring Cloud hỗ trợ `SimpleDiscoveryClient`, có thể khai báo instance bằng cấu hình:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Ứng dụng có thể tra cứu `inventory-service` qua `DiscoveryClient`. Đây là minh họa cho **nguồn danh sách instance tĩnh**. Nó không tạo service registry, không đăng ký tiến trình vào máy chủ discovery và không thay thế giải pháp discovery động cho môi trường có nhiều instance thay đổi liên tục.

### 3.3. Commons không tự triển khai toàn bộ hệ thống phân tán

Cần tách các khái niệm:

- **Hợp đồng discovery** (`DiscoveryClient`) khác với **provider discovery** (ví dụ Eureka client hoặc Consul discovery).
- **Hợp đồng registry** (`ServiceRegistry`) khác với **registry server** và implementation dùng để đăng ký.
- **Chọn instance** khác với **gửi HTTP request**. Spring Cloud LoadBalancer hỗ trợ chọn instance, nhưng ứng dụng vẫn cần HTTP client được tích hợp tương ứng.
- **Thấy dependency trên classpath** khác với **auto-configuration đã kích hoạt và bean mong muốn đã được tạo**.

Từ đây có thể giải thích một lỗi quen thuộc: thêm `spring-cloud-commons` rồi truy cập `http://inventory-service/...` nhưng tên không phân giải được. Nguyên nhân là project chưa có đúng nguồn `ServiceInstance`/load balancer/HTTP client integration; JAR Commons đơn lẻ không phải một service mesh hay DNS server.

## 4. `spring-cloud-context`: ngữ cảnh và cập nhật cấu hình

Spring Boot tạo và quản lý `ApplicationContext`. Spring Cloud Context bổ sung những cơ chế giúp ứng dụng Cloud xử lý **nguồn cấu hình** và **thay đổi cấu hình trong vòng đời ứng dụng**.

Các thành phần tiêu biểu gồm:

- `@RefreshScope`: một scope cho bean cần được khởi tạo lại sau khi refresh.
- `RefreshScope`: dịch vụ quản lý cache target của các bean thuộc refresh scope; có thể làm mới một bean hoặc toàn bộ scope.
- Các sự kiện/cơ chế liên quan đến thay đổi `Environment` và rebind cấu hình, tùy phiên bản.
- Tích hợp bootstrap/configuration context, tùy cách cấu hình và phiên bản Spring Boot/Spring Cloud.

### 4.1. `@RefreshScope` dùng để làm gì?

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogMessage {
    @Value("${catalog.banner:Chao mung}")
    private String banner;

    public String text() {
        return banner;
    }
}
~~~

Nếu ứng dụng nhận được giá trị `catalog.banner` mới trong `Environment` **và** có một hoạt động refresh thích hợp, target của bean trong refresh scope có thể được tạo lại để sử dụng giá trị mới ở lần truy cập sau.

Cần phân biệt bốn thời điểm:

1. Nguồn cấu hình ở bên ngoài được sửa.
2. Ứng dụng **nhận được hoặc nạp lại** giá trị cấu hình.
3. Cơ chế **refresh** được kích hoạt.
4. Bean đang dùng cấu hình được **rebind hoặc khởi tạo lại**, tùy loại bean/scope.

**Chỉ thêm `spring-cloud-context` hoặc gắn `@RefreshScope` không làm bốn bước trên tự xảy ra.** Nếu sử dụng Spring Cloud Config Server, cần thêm Config Client và thiết kế cách cập nhật/refresh phù hợp. Nếu muốn gọi endpoint quản trị refresh, cần cân nhắc Spring Boot Actuator, việc expose endpoint và kiểm soát truy cập. Hành vi cụ thể thay đổi theo release train.

### 4.2. `@ConfigurationProperties` không đồng nghĩa với `@RefreshScope`

`@ConfigurationProperties` của Spring Boot hỗ trợ binding các thuộc tính vào một bean kiểu dữ liệu. Một số cơ chế Spring Cloud có thể **rebind** cấu hình khi môi trường thay đổi, nhưng việc rebind và việc **tạo lại target bean** là hai hành vi khác nhau.

Ví dụ, một HTTP client đã được tạo với timeout lấy từ cấu hình lúc khởi tạo có thể giữ timeout cũ dù object cấu hình được cập nhật. Muốn thay đổi timeout có hiệu lực, cần thiết kế lại vòng đời client, bean phụ thuộc và refresh phù hợp. `@RefreshScope` trên một lớp `@Configuration` cũng không tự động khiến mọi bean do lớp đó tạo ra thuộc refresh scope.

Các hạn chế cần kiểm tra theo phiên bản: tính refresh được của từng bean, dữ liệu chỉ đọc/constructor binding, yêu cầu runtime native/AOT, và hành vi của những request đang chạy khi refresh. Không nên giả định mọi thay đổi đều tức thì hoặc nguyên tử.

### 4.3. `spring-cloud-context` không phải Config Server

**Spring Cloud Context** cung cấp cơ chế liên quan đến context và refresh. **Spring Cloud Config** là một thành phần riêng, gồm các module/starter theo vai trò client hoặc server. Việc đọc cấu hình qua HTTP từ một Config Server không đến từ `spring-cloud-context` đơn lẻ.

Ví dụ dưới đây là cấu hình minh họa cho **Config Client** theo cơ chế Config Data ở các phiên bản Spring Boot/Spring Cloud hỗ trợ, **chỉ có ý nghĩa khi đã thêm starter Config Client phù hợp**:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Ở đây `optional:` thể hiện chính sách cho phép ứng dụng tiếp tục trong một số trường hợp không lấy được cấu hình từ server; mức độ phù hợp phải do yêu cầu vận hành quyết định. Cơ chế lấy cấu hình lúc khởi động và cơ chế refresh **không phải cùng một thao tác**.

## 5. `spring-cloud-starter`: tập hợp dependency nền tảng

Starter giải quyết một vấn đề thực tế: nếu mỗi ứng dụng phải tự liệt kê nhiều JAR để sử dụng một chức năng, nguy cơ thiếu dependency hoặc kết hợp sai phiên bản sẽ tăng. Starter là một **điểm khai báo thuận tiện** đưa các phụ thuộc liên quan vào classpath.

### 5.1. Starter nền tảng khác starter tính năng

| Artifact | Nhóm | Chức năng chính |
| --- | --- | --- |
| `spring-cloud-starter` | Starter nền tảng | Kéo vào các thư viện Spring Cloud cơ bản, điển hình gồm Commons và Context |
| `spring-cloud-starter-loadbalancer` | Starter tính năng | Cung cấp tích hợp Spring Cloud LoadBalancer để chọn service instance |
| `spring-cloud-starter-config` | Starter tính năng | Cài đặt phía **client** để ứng dụng lấy cấu hình từ Spring Cloud Config |
| `spring-cloud-starter-netflix-eureka-client` | Starter tính năng | Thêm integration client cho dịch vụ khám phá Eureka |
| `spring-cloud-starter-circuitbreaker-resilience4j` | Starter tính năng | Tích hợp API Spring Cloud CircuitBreaker với Resilience4j cho cách xử lý lỗi phù hợp |

**Sơ đồ khái niệm** sau cho thấy quan hệ giữa ứng dụng, starter và thư viện nền tảng. Quan hệ phụ thuộc chính xác phải xem theo phiên bản thực tế.

~~~mermaid
flowchart TD
    A[Ứng dụng Spring Boot] --> S[spring-cloud-starter]
    S --> C[spring-cloud-commons]
    S --> X[spring-cloud-context]
    A -. khi cần chọn instance .-> L[spring-cloud-starter-loadbalancer]
    A -. khi cần cấu hình từ Config Server .-> F[spring-cloud-starter-config]
    A -. khi cần Eureka .-> E[spring-cloud-starter-netflix-eureka-client]
    L --> C
    F --> X
    E --> C
    B[spring-cloud-dependencies BOM] -. quản lý version .-> S
    B -. quản lý version .-> L
    B -. quản lý version .-> F
    B -. quản lý version .-> E
~~~

Sơ đồ không mô tả đầy đủ mọi cạnh transitve; nó dùng để nhận diện **vai trò**. Starter tính năng có thể tự kéo theo thư viện nền tảng, vì vậy thường **không cần khai báo thêm** `spring-cloud-starter` riêng nếu đã có starter tính năng chứa những thư viện cần dùng. Hãy kiểm tra cây phụ thuộc thay vì khai báo trùng theo thói quen.

### 5.2. Thêm starter có tự bật tính năng không?

**Chưa chắc.** Có ba mức cần kiểm tra:

1. **Dependency present:** artifact nằm trong runtime classpath.
2. **Bean/configuration present:** điều kiện auto-configuration thỏa mãn, bean cần thiết đã được tạo.
3. **Behavior works:** registry khả dụng, danh sách instance đúng, cấu hình hợp lệ và request thực tế hoạt động.

Ví dụ, thêm Eureka Client starter làm cho integration client có mặt, nhưng service registry server vẫn phải sẵn sàng và các thông số URL, registration, network phải đúng. Thêm LoadBalancer starter cũng không cung cấp bản thân các địa chỉ instance nếu không có discovery implementation hoặc một `ServiceInstanceListSupplier` thích hợp.

### 5.3. Nhận diện dependency trực tiếp và gián tiếp

Nếu khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter</artifactId>
</dependency>
~~~

Maven có thể phân giải các JAR nền tảng từ **transitive dependencies** của starter. Tương tự, chỉ khai báo `spring-cloud-starter-config` có thể dẫn đến `spring-cloud-context` xuất hiện dù không được khai báo trực tiếp trong `pom.xml`.

Vì nội dung POM của từng starter có thể thay đổi theo release train, **cây phụ thuộc thực tế** mới là căn cứ để kết luận artifact nào có mặt và phiên bản nào đã được chọn.

## 6. BOM và tương thích Spring Boot – Spring Cloud

Từng module có phiên bản như `4.x`, `5.x`... nhưng ứng dụng thường lựa chọn Spring Cloud bằng **release train**. Release train tập hợp các phiên bản tương thích của nhiều thành phần Cloud; BOM `spring-cloud-dependencies` quy định phiên bản phù hợp cho chúng.

Khái niệm này khác nhau ở ba nơi:

| Nơi xuất hiện phiên bản | Ví dụ | Vai trò |
| --- | --- | --- |
| Spring Boot | `3.5.x` hoặc `4.0.x` | Phiên bản nền Spring Boot |
| Spring Cloud release train | `2025.0.x` hoặc `2025.1.x` | Bộ phiên bản Cloud được phối hợp để dùng cùng nhau |
| Spring Cloud module | Ví dụ Commons/Context phiên bản thuộc release train | Phiên bản JAR được dependency management lựa chọn |

Theo ma trận chính thức tại thời điểm biên soạn (18/11/2026), **Spring Cloud 2025.0.x** dành cho **Spring Boot 3.5.x**; **Spring Cloud 2025.1.x** dành cho **Spring Boot 4.0.x**, và hỗ trợ **Spring Boot 4.1.x từ bản 2025.1.2**. Đây là dữ liệu theo release train/patch, không phải quy tắc suy ra từ số phiên bản. Trước khi tạo hoặc nâng cấp dự án, cần kiểm tra lại [ma trận Spring Cloud – Spring Boot chính thức](https://spring.io/projects/spring-cloud/).

BOM của Spring Cloud **không thay thế** cơ chế quản lý phiên bản Spring Boot. Với Maven dùng `spring-boot-starter-parent`, parent tiếp tục quản lý phiên bản Boot và những phụ thuộc Boot liên quan; BOM Cloud quản lý các artifact thuộc Cloud. Với Gradle cần thiết lập dependency management tương ứng với build đang dùng.

### 6.1. Maven: ví dụ khai báo nền tảng

Ví dụ này giả định project đã có **Spring Boot parent phù hợp với Spring Cloud 2025.0.x**; thông tin Boot parent và phần build khác không được trình bày để tập trung vào dependency Cloud.

~~~xml
<properties>
    <!-- Ví dụ release train; chọn bản vá phù hợp khi triển khai -->
    <spring-cloud.version>2025.0.0</spring-cloud.version>
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
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter</artifactId>
    </dependency>
</dependencies>
~~~

Điểm quan trọng:

- Trong `dependencyManagement`, `type=pom` và `scope=import` cho phép Maven nhập **bảng quản lý phiên bản**.
- Dependency `spring-cloud-starter` nằm trong `<dependencies>` để được đưa vào classpath.
- Không cần tự đặt `<version>` cho mỗi Spring Cloud starter khi đã dùng BOM đúng.
- `2025.0.0` là **ví dụ minh họa bản phát hành có thật**, không phải khuyến nghị luôn dùng bản đó; chọn bản vá phù hợp và còn được duy trì trong release train tương ứng.
- Nếu dự án **đã có** starter tính năng kéo vào các thư viện mong muốn, không bắt buộc khai báo thêm starter nền tảng chỉ để gọi lại cùng các JAR.

Nếu cần Config Client, thay hoặc bổ sung dependency đúng nhu cầu:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Không dùng `spring-cloud-starter` để thay `spring-cloud-starter-config`: hai artifact giải quyết những yêu cầu khác nhau.

### 6.2. Gradle: ví dụ quản lý phiên bản bằng platform BOM

Đây là phần `dependencies` minh họa cho một **Gradle build của Spring Boot đã được cấu hình hợp lệ**:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:2025.0.0"
    )
    implementation "org.springframework.cloud:spring-cloud-starter"
}
~~~

Đoạn trên sử dụng cơ chế `platform` của Gradle. Có thể dùng Spring dependency-management plugin theo quy ước của dự án; không cần áp dụng cả hai cách một cách máy móc. Các dependency của Spring Boot vẫn phải được quản lý theo thiết lập Boot phù hợp. Với Gradle Kotlin DSL, cú pháp tương đương là `implementation(platform("..."))`.

### 6.3. Vì sao không nên tự ghép ba module bằng version rời rạc?

Giả sử project tự đặt `spring-cloud-commons` từ một release train, `spring-cloud-context` từ một release train khác, rồi thêm starter từ train thứ ba. Maven/Gradle vẫn có thể chọn ra một cây phụ thuộc phân giải được, nhưng các API và auto-configuration có thể không khớp nhau. Hậu quả thường gặp là `NoSuchMethodError`, `ClassNotFoundException`, lỗi nạp bean hoặc hành vi cấu hình không như mong muốn.

**Nguyên tắc:** chọn Spring Boot trước, tra train Cloud tương thích, để BOM quản lý phiên bản Cloud, sau đó xem dependency tree để kiểm chứng phiên bản thực tế. Chỉ override phiên bản module khi có lý do rõ ràng và kiểm thử tương thích đầy đủ.

## 7. Đọc dependency tree để tìm nguyên nhân

### 7.1. Maven

Các lệnh sau là gợi ý chạy ở **project đích** khi thực hành, không phải thao tác phải thực hiện với bài học này:

~~~bash
# Xem những dependency Cloud và đường đi trong cây phụ thuộc
mvn dependency:tree -Dincludes=org.springframework.cloud

# Xem POM đã được kết hợp sau parent và dependencyManagement
mvn help:effective-pom
~~~

Cách đọc kết quả:

~~~text
com.example:orders-service:jar:1.0.0
\- org.springframework.cloud:spring-cloud-starter:jar:<resolved-version>:compile
   +- org.springframework.cloud:spring-cloud-context:jar:<resolved-version>:compile
   \- org.springframework.cloud:spring-cloud-commons:jar:<resolved-version>:compile
~~~

Đây là **cây minh họa đã lược bớt**, không phải output nguyên văn của một release train nhất định. Nó cho thấy:

- `spring-cloud-starter` được khai báo trực tiếp.
- `spring-cloud-context` và `spring-cloud-commons` có thể được đưa vào gián tiếp.
- `<resolved-version>` phải được thay bằng phiên bản mà Maven thực sự phân giải.
- Một artifact có thể bị loại khỏi cây hoặc bị chọn phiên bản khác do quy tắc dependency management, exclusion hay dependency conflict.

Nếu `spring-cloud-context` hiện ra trong cây, hãy xem đường đi để biết nó đến từ starter nào trước khi thêm dependency trực tiếp.

### 7.2. Gradle

~~~bash
# Cây runtime dependencies
./gradlew dependencies --configuration runtimeClasspath

# Tại sao artifact này xuất hiện và version nào được chọn
./gradlew dependencyInsight --dependency spring-cloud-context \
  --configuration runtimeClasspath

./gradlew dependencyInsight --dependency spring-cloud-commons \
  --configuration runtimeClasspath
~~~

Trong PowerShell/Windows, hãy viết lệnh `dependencyInsight` trên **một dòng** và dùng `gradlew.bat` nếu thích hợp; dấu `\` xuống dòng phía trên chỉ minh họa cho shell Unix.

`dependencyInsight` đặc biệt hữu ích khi một version được chọn bởi BOM, bị ràng buộc bởi constraint hoặc bị nâng lên vì dependency khác. Mục tiêu là truy ra **vì sao version đó có mặt**, không chỉ kiểm tra có/không có JAR.

### 7.3. Classpath có JAR nhưng tính năng không hoạt động?

Sử dụng trình tự kiểm tra:

1. **Có đúng artifact?** Xem dependency tree ở `runtimeClasspath`, không chỉ `testRuntimeClasspath`.
2. **Có đúng implementation?** Ví dụ Commons có interface `DiscoveryClient`, nhưng dùng Eureka cần starter/client phù hợp.
3. **Auto-configuration có match?** Đọc condition evaluation report của Spring Boot (có thể bật logging debug hoặc dùng Actuator với bảo vệ truy cập thích hợp).
4. **Bean cần thiết đã được tạo?** Kiểm tra `ApplicationContext` trong integration test hoặc kiểm tra Actuator beans khi được bật và bảo vệ.
5. **Có hoạt động thật?** Gọi thử, kiểm tra danh sách instance, refresh, load balancing hoặc dữ liệu cấu hình theo yêu cầu.

Một ứng dụng có thể **compile được** vì API tồn tại, nhưng **runtime vẫn lỗi** vì thiếu provider, sai URL registry, sai property hoặc không đủ quyền.

## 8. Ví dụ phân loại yêu cầu trước khi chọn dependency

Một nhóm xây ứng dụng `orders-service`. Các yêu cầu thay đổi dần:

| Yêu cầu thực tế | Thành phần cần xem xét | Lý do |
| --- | --- | --- |
| Chỉ cần API chung để làm việc với `DiscoveryClient` | `spring-cloud-commons` (trực tiếp hoặc được kéo vào qua starter) | Cung cấp hợp đồng; có thể cần `SimpleDiscoveryClient` cho dữ liệu tĩnh |
| Cần bean có thể tạo lại sau một lần refresh có kiểm soát | `spring-cloud-context` | Cung cấp `@RefreshScope` và cơ chế context/refresh |
| Cần nền tảng Cloud chung trong một project Boot | `spring-cloud-starter` | Gom thư viện nền tảng; chưa cung cấp mọi tính năng Cloud |
| Muốn nạp cấu hình tập trung từ Config Server | `spring-cloud-starter-config` và cấu hình Config Data phù hợp | Cần implementation Config Client |
| Muốn đăng ký/tra cứu instance qua Eureka | `spring-cloud-starter-netflix-eureka-client` | Cần discovery/registry provider tương ứng |
| Muốn gọi `http://inventory-service` với client-side load balancing | `spring-cloud-starter-loadbalancer`, nguồn instance và HTTP client tích hợp | Phải có cách tra cứu instance và bộ chọn instance |
| Muốn kiểm soát lỗi bằng Resilience4j | Starter CircuitBreaker phù hợp và cấu hình chính sách | Commons/Context không tự triển khai đầy đủ circuit breaker |

Không nên thêm toàn bộ các starter “để phòng khi cần”. Mỗi dependency làm thay đổi classpath, auto-configuration, bề mặt cấu hình và việc nâng cấp. Chọn các starter theo **hành vi cần dùng**.

## 9. Kiểm thử để xác nhận đã nhận diện đúng

Nhận diện bằng tên JAR là bước đầu; kiểm thử cần xác nhận lớp abstraction và implementation khớp với nhau.

### 9.1. Kiểm tra discovery

Một integration test có thể inject `DiscoveryClient` và yêu cầu instance của một service:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest
class DiscoveryWiringTest {
    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void findsConfiguredInventoryService() {
        assertThat(discoveryClient.getInstances("inventory-service"))
                .isNotEmpty();
    }
}
~~~

Để test có giá trị, môi trường kiểm thử phải khai báo danh sách instance tĩnh hoặc một discovery server/test fixture phù hợp. Test này chứng minh **có thể tra cứu instance theo cấu hình thử nghiệm**, không chứng minh registry bên ngoài hoạt động trong production. Nếu muốn thử Eureka/Consul thật, cần một phép kiểm thử tích hợp khác.

### 9.2. Kiểm tra refresh

Với một bean `@RefreshScope`, một phép thử có thể thay đổi nguồn cấu hình trong môi trường kiểm thử, kích hoạt refresh bằng cơ chế tương thích và xác nhận lần truy cập sau nhận giá trị mới. Đồng thời, cần xác định bean bị tạo lại hoặc rebind theo đúng thiết kế.

Không nên kiểm thử bằng cách chỉ sửa file cấu hình rồi giả định Spring tự đọc lại. Cần điều khiển được **sự kiện thay đổi cấu hình** và **điểm refresh**. Khi dùng Config Client, kiểm tra thêm hành vi khi Config Server chậm, không sẵn sàng hoặc trả cấu hình thiếu.

### 9.3. Kiểm tra load balancing và tính năng vận hành

- Chuẩn bị hai instance `inventory-service` với phản hồi phân biệt được.
- Dùng client đã tích hợp LoadBalancer để gửi nhiều request.
- Xác nhận instance được chọn dựa trên danh sách được cung cấp và chính sách đang cấu hình; đừng mặc định cứ hai instance thì request luân phiên tuyệt đối trong mọi tình huống.
- Kiểm tra timeout, lỗi kết nối và hành vi khi danh sách instance rỗng.
- Đo metrics/tracing và kiểm tra điều kiện auto-configuration của ứng dụng theo từng environment.

## 10. Lỗi nhầm lẫn thường gặp

| Triệu chứng | Hiểu nhầm thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `DiscoveryClient` inject được nhưng không tìm thấy instance | “Commons tự có registry” | Kiểm tra discovery provider hoặc `SimpleDiscoveryClient` cùng nguồn instance |
| Có `@RefreshScope` nhưng cập nhật cấu hình không có hiệu lực | “Context tự phát hiện mọi đổi cấu hình” | Kiểm tra nạp lại `Environment`, kích hoạt refresh, scope của bean và vòng đời đối tượng phụ thuộc |
| Đã thêm `spring-cloud-starter` nhưng không gọi được Config Server | “Starter nền tảng bao gồm Config Client” | Thêm `spring-cloud-starter-config` và kiểm tra `spring.config.import` phù hợp |
| Có Cloud BOM mà runtime thiếu class | “BOM tự tải mọi JAR” | Xem `<dependencies>` hoặc `implementation`; BOM chỉ quản lý version |
| Dự án báo lỗi tương thích khi startup | “Mọi bản Spring Cloud đều hỗ trợ mọi Spring Boot” | Tra release train/Boot matrix, loại bỏ override lệch hoặc dependency cũ |
| Dependency tree có cùng artifact đi qua nhiều starter | “Phải xóa mọi dependency trùng đường dẫn” | Kiểm tra version được chọn và conflict thực tế; Maven/Gradle có cơ chế hòa giải |
| Starter đã thêm nhưng auto-configuration không chạy | “Có JAR là luôn có bean” | Kiểm tra conditions, required properties, classpath, các bean tùy chỉnh |
| `ServiceInstance` được trả về nhưng request lỗi | “Discovery bảo đảm instance khỏe” | Kiểm tra endpoint, health, kết nối, timeouts và cách danh sách instance được cập nhật |

### 10.1. Khi nào cần khai báo thư viện trực tiếp?

Có thể khai báo `spring-cloud-commons` hoặc `spring-cloud-context` trực tiếp trong một module thư viện đang **công khai sử dụng API của chúng**, nhất là khi muốn mô tả rõ compile dependency. Trong ứng dụng Spring Boot chạy thực tế, starter tính năng thường tiện hơn vì kéo theo những phần cần thiết để tích hợp. Cách chọn phụ thuộc vào mô hình module, tính năng cần dùng và chính sách quản lý transitive dependency của nhóm.

Tránh dùng cách “thấy compile lỗi thì thêm trực tiếp version mới nhất của Commons” mà không kiểm tra BOM; cách đó dễ phá vỡ sự tương thích của cả release train.

## 11. Bài tập thực hành

**Bài tập 1 — Phân loại artifact.** Cho bốn tọa độ:

~~~text
org.springframework.cloud:spring-cloud-context
org.springframework.cloud:spring-cloud-starter
org.springframework.cloud:spring-cloud-commons
org.springframework.cloud:spring-cloud-dependencies
~~~

Hãy đánh dấu: thư viện cung cấp abstraction, thư viện quản lý context/refresh, starter nền tảng và BOM. Với mỗi artifact, nêu một khả năng **không** được bảo đảm chỉ bằng việc khai báo nó.

**Bài tập 2 — Sửa sai về dependency.** Một project đã import BOM Cloud và chỉ khai báo `spring-cloud-starter`. Nhóm muốn truy cập Config Server nhưng ứng dụng không đọc được cấu hình từ đó. Hãy đề xuất dependency và property cần bổ sung, giải thích vì sao `spring-cloud-context` sẵn có không giải quyết hết yêu cầu.

**Bài tập 3 — Truy vết transitive dependency.** `dependencyInsight` cho thấy `spring-cloud-context` do một starter tính năng kéo vào. Hãy tìm artifact đầu vào, phiên bản được chọn và constraint/BOM nào tác động. Nêu vì sao không cần thêm một dependency `spring-cloud-context` trực tiếp chỉ để “đảm bảo nó có mặt”.

**Bài tập 4 — Kiểm tra runtime.** Một service inject được `DiscoveryClient`, nhưng `getInstances("inventory-service")` trả danh sách rỗng. Lập trình tự kiểm tra từ classpath, bean, provider, cấu hình instance cho đến kết nối thực tế. Chỉ rõ bằng chứng nào mới chứng minh registry bên ngoài hoạt động.

## 12. Ghi nhớ và nguồn tra cứu

Ba artifact cần được nhớ theo **trách nhiệm**:

- **`spring-cloud-commons`**: *hợp đồng và abstraction chung* cho các mô hình phân tán như discovery, service registry và client-side load balancing.
- **`spring-cloud-context`**: *cơ chế context, environment và refresh* của ứng dụng.
- **`spring-cloud-starter`**: *điểm gom dependency nền tảng*. Muốn có tính năng cụ thể như Config Client, Eureka hoặc LoadBalancer, cần thêm integration tương ứng, không suy luận chỉ từ tên starter chung.

Khi triển khai, hãy kiểm tra **artifact → dependency tree → auto-configuration → bean → hành vi thực tế**, đồng thời giữ một cặp **Spring Boot – Spring Cloud release train** tương thích.

Nguồn chính thức để đối chiếu theo phiên bản đang sử dụng:

1. [Spring Cloud – tổng quan và ma trận tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
2. [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
3. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
4. [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
5. [Maven Central – `org.springframework.cloud:spring-cloud-starter`](https://central.sonatype.com/artifact/org.springframework.cloud/spring-cloud-starter)
