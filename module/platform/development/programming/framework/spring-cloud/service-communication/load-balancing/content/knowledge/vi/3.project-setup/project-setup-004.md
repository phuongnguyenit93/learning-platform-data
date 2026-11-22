# Phân biệt phụ thuộc bắt buộc, tùy chọn và phụ thuộc bắc cầu

Khi thiết lập một ứng dụng dùng Spring Cloud LoadBalancer, việc chọn đúng dependency giúp ứng dụng có đủ thành phần để phân giải service ID và chọn `ServiceInstance`, đồng thời tránh kéo vào những thư viện mà dự án không sử dụng. Cần phân biệt ba nhóm: dependency mà chức năng đang dùng cần trực tiếp, dependency chỉ cần cho một tính năng bổ sung, và dependency được công cụ build tự động đưa vào thông qua một dependency khác.

Trong module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`, ứng dụng có thể tích hợp LoadBalancer với `RestClient`, `WebClient` hoặc OpenFeign; lấy danh sách instance từ discovery; sau đó áp dụng cache, health check, retry, timeout và quan sát lỗi. Mỗi lựa chọn làm thay đổi tập dependency cần có. Không có một danh sách duy nhất phù hợp với mọi ứng dụng.

## 1. Ba khái niệm cần phân biệt

### Dependency bắt buộc

Dependency bắt buộc là thư viện ứng dụng cần để biên dịch hoặc chạy chức năng mà nó đã chọn. Nếu ứng dụng muốn dùng Spring Cloud LoadBalancer để chuyển một URL chứa service ID như `http://catalog-service/products/42` thành địa chỉ của một instance, ứng dụng cần đưa tích hợp LoadBalancer vào classpath.

Với ứng dụng Spring Cloud thông thường, dependency khởi đầu là:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Starter này cung cấp cấu hình tích hợp và các thành phần LoadBalancer cần thiết. Ứng dụng nên khai báo starter trực tiếp vì chính ứng dụng đang chủ động sử dụng chức năng cân bằng tải.

### Dependency tùy chọn

Dependency tùy chọn chỉ cần khi ứng dụng bật một khả năng bổ sung. Ví dụ, Caffeine có thể được thêm để dùng cache dựa trên Caffeine; Actuator có thể được thêm để cung cấp endpoint health/metrics và hỗ trợ quan sát ứng dụng; thư viện kiểm thử chỉ cần trong quá trình test.

Nếu ứng dụng không sử dụng tính năng đó, không cần thêm dependency tương ứng. Việc thêm một thư viện tùy chọn cũng không tự động cấu hình tính năng: ứng dụng vẫn cần cấu hình bean, property hoặc cơ chế tích hợp phù hợp.

### Dependency bắc cầu

Dependency bắc cầu (*transitive dependency*) là thư viện được công cụ build phân giải tự động vì một dependency khác khai báo nó. Chẳng hạn, starter LoadBalancer phụ thuộc vào các module Spring Cloud cung cấp abstraction discovery và triển khai LoadBalancer. Khi khai báo starter, Maven hoặc Gradle sẽ lấy những module cần thiết theo metadata của starter.

Sơ đồ dưới đây minh họa quan hệ khái niệm; cây dependency chính xác phụ thuộc phiên bản Spring Cloud và Spring Boot mà dự án đang dùng:

```text
Ứng dụng
└── spring-cloud-starter-loadbalancer       (khai báo trực tiếp)
    ├── spring-cloud-loadbalancer           (được kéo vào bắc cầu)
    ├── spring-cloud-commons                (được kéo vào bắc cầu)
    └── các thư viện Spring nền tảng khác   (được phân giải theo POM)
```

Không cần khai báo lại mọi module con chỉ vì nhìn thấy chúng trong dependency tree. Tuy nhiên, nếu mã nguồn của ứng dụng trực tiếp sử dụng API của một thư viện, hoặc công khai kiểu của thư viện đó trong API của chính ứng dụng, hãy cân nhắc khai báo dependency trực tiếp để thể hiện rõ hợp đồng và tránh phụ thuộc tình cờ vào cây bắc cầu.

## 2. Chọn dependency theo HTTP client

LoadBalancer không thay thế HTTP client. Nó quyết định instance đích; HTTP client thực hiện kết nối và gửi request. Vì thế, ngoài starter LoadBalancer, ứng dụng cần dependency của client mà nó chọn.

| Cách gọi dịch vụ | Dependency phía client | Dependency LoadBalancer |
|---|---|---|
| `RestClient` | `spring-boot-starter-web` trên phiên bản Spring Framework có `RestClient` | `spring-cloud-starter-loadbalancer` |
| `WebClient` | `spring-boot-starter-webflux` hoặc dependency WebFlux phù hợp với cách tổ chức ứng dụng | `spring-cloud-starter-loadbalancer` |
| OpenFeign | `spring-cloud-starter-openfeign` | Thêm `spring-cloud-starter-loadbalancer` để bật tích hợp cân bằng tải cho Feign |

Chỉ thêm client mà ứng dụng thực sự sử dụng. Một ứng dụng có thể dùng nhiều client, nhưng cần có lý do kiến trúc rõ ràng và tránh kéo hai web stack chỉ vì một ví dụ cấu hình.

### Trường hợp dùng RestClient

`RestClient` là API gọi HTTP đồng bộ của Spring Framework. Với Spring Boot 3.2 trở lên, `spring-boot-starter-web` cung cấp nền tảng Spring MVC và các thư viện Spring Web tương ứng để sử dụng `RestClient`.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Sau đó, ứng dụng có thể khai báo bean `RestClient.Builder` được đánh dấu `@LoadBalanced` và gửi request đến URL chứa service ID. Nếu dùng phiên bản Spring Framework chưa có `RestClient`, hãy chọn API HTTP client tương thích với phiên bản nền tảng thay vì thêm riêng một dependency để giả lập API chưa được hỗ trợ.

### Trường hợp dùng WebClient

`WebClient` phù hợp với ứng dụng reactive hoặc trường hợp cần API HTTP non-blocking. Starter WebFlux cung cấp `WebClient` cùng các thành phần reactive cần thiết:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Ứng dụng tạo `WebClient.Builder` với `@LoadBalanced`, sau đó gọi URI có service ID. Nếu ứng dụng hiện tại chạy Spring MVC nhưng chỉ muốn dùng `WebClient` như HTTP client, hãy cân nhắc chỉ thêm các module WebFlux cần thiết thay vì vô tình chuyển kiến trúc máy chủ sang reactive.

### Trường hợp dùng OpenFeign

OpenFeign tạo client từ interface khai báo bằng `@FeignClient`. Để sử dụng OpenFeign và chọn instance qua Spring Cloud LoadBalancer, ứng dụng cần cả starter OpenFeign lẫn starter LoadBalancer:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Khi tích hợp LoadBalancer được phát hiện và bật theo phiên bản đang sử dụng, Feign có thể dùng service name trong `@FeignClient(name = "catalog-service")` để tìm instance. Nếu chỉ có OpenFeign mà thiếu tích hợp LoadBalancer, không nên mặc định rằng tên service sẽ được tự động phân giải thành một bản sao.

## 3. Chọn dependency cho Service Discovery

LoadBalancer cần danh sách `ServiceInstance` để lựa chọn. Nguồn danh sách đó phụ thuộc cách triển khai hệ thống:

| Nguồn instance | Dependency bổ sung | Khi sử dụng |
|---|---|---|
| `SimpleDiscoveryClient` | Thường không cần thêm registry starter riêng | Khai báo instance tĩnh, thử nghiệm hoặc môi trường đơn giản |
| Eureka | Starter Eureka Client tương ứng, thường là `spring-cloud-starter-netflix-eureka-client` | Hệ thống đăng ký và tra cứu dịch vụ qua Eureka |
| Consul | Starter Consul Discovery tương ứng, thường là `spring-cloud-starter-consul-discovery` | Hệ thống dùng Consul làm registry |
| Kubernetes | Module discovery tương thích với Spring Cloud Kubernetes và nền tảng đang triển khai | Muốn tích hợp discovery với Kubernetes |

Chỉ chọn provider mà môi trường thực tế sử dụng. Không cần đưa Eureka, Consul và Kubernetes discovery vào cùng một ứng dụng nếu kiến trúc không yêu cầu nhiều nguồn discovery.

Với `SimpleDiscoveryClient`, có thể khai báo các instance trong cấu hình:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Ví dụ này dùng hai địa chỉ tĩnh cho service ID `catalog-service`. Khi chuyển sang Eureka hoặc Consul, registry cung cấp danh sách instance động; ứng dụng cần cấu hình địa chỉ registry và thông tin đăng ký phù hợp với môi trường.

Lưu ý rằng discovery và LoadBalancer là hai trách nhiệm khác nhau. Discovery tìm các instance được đăng ký; LoadBalancer chọn một instance trong danh sách mà supplier cung cấp. Chỉ thêm dependency registry không tự tạo ra cấu hình client-side load balancing nếu HTTP client chưa được tích hợp với LoadBalancer.

## 4. Những dependency tùy chọn thường gặp

### Caffeine cho cache

Spring Cloud LoadBalancer có cơ chế cache danh sách instance. Khi muốn dùng cache dựa trên Caffeine, có thể thêm thư viện Caffeine:

```xml
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
```

Đây là dependency tùy chọn cho lựa chọn cache. Không nên thêm chỉ vì thấy chữ “cache” trong tài liệu; hãy xác định cache mặc định của phiên bản đang dùng đã đáp ứng yêu cầu hay chưa, sau đó mới cân nhắc Caffeine và cấu hình thời gian sống phù hợp. Cache quá lâu có thể giữ danh sách instance cũ sau khi registry thay đổi.

### Actuator và quan sát hệ thống

Nếu cần endpoint quản trị, health hoặc metrics của ứng dụng, có thể thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Actuator hỗ trợ quan sát trạng thái ứng dụng và cung cấp các endpoint được cấu hình. Nó không phải dependency cốt lõi để LoadBalancer chọn instance. Việc bật endpoint, quyền truy cập và mức độ công khai phải phù hợp với môi trường triển khai.

### Dependency kiểm thử

Trong Maven, `spring-boot-starter-test` thường được khai báo với scope `test`; trong Gradle, dùng `testImplementation`. Các dependency này phục vụ kiểm thử cấu hình, client và hành vi khi registry không có instance. Chúng không cần được đóng gói như dependency runtime của ứng dụng.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

## 5. Quản lý phiên bản bằng Spring Cloud BOM

Spring Boot và Spring Cloud có ma trận tương thích phiên bản. Không nên chọn phiên bản starter một cách độc lập hoặc trộn các module Spring Cloud từ nhiều release train. Hãy chọn release train tương thích với phiên bản Spring Boot của dự án và dùng BOM để quản lý phiên bản đồng bộ.

Ví dụ Maven:

```xml
<properties>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN</spring-cloud.version>
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
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
```

Giá trị `YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN` là chỗ giữ chỗ: thay bằng release train được Spring công bố tương thích với phiên bản Spring Boot đang dùng. Khi BOM đã quản lý phiên bản, thông thường không ghi `<version>` riêng cho từng starter Spring Cloud.

Với Gradle, có thể import BOM qua `platform`:

```groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )
    implementation "org.springframework.cloud:spring-cloud-starter-loadbalancer"
}
```

BOM chỉ quản lý phiên bản dependency; nó không tự thêm mọi module Spring Cloud vào ứng dụng. Muốn sử dụng LoadBalancer, vẫn phải khai báo starter trong `dependencies`.

## 6. Scope và ý nghĩa của từ optional trong Maven, Gradle

Các khái niệm bắt buộc, tùy chọn và bắc cầu mô tả vai trò của dependency trong ứng dụng. Maven và Gradle còn có cơ chế scope/configuration để quyết định dependency có mặt ở giai đoạn nào và có được truyền tiếp hay không.

### Maven

| Scope | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| `compile` | Có trong compile classpath và runtime classpath; đây là scope mặc định | Starter mà mã ứng dụng và runtime đều cần |
| `runtime` | Cần khi chạy nhưng không cần để biên dịch mã nguồn | Một driver hoặc implementation chỉ nạp lúc chạy |
| `test` | Chỉ dùng cho biên dịch và chạy test | `spring-boot-starter-test` |
| `provided` | Môi trường chạy dự kiến cung cấp dependency | API do container hoặc nền tảng cung cấp |

Trong Maven, `<optional>true</optional>` có ý nghĩa về truyền dependency: module khai báo dependency đó không tự động truyền nó cho các module tiêu thụ ở downstream. Nó không đơn giản có nghĩa “dependency này sẽ không được nạp lúc runtime trong project hiện tại”. Nếu ứng dụng hiện tại cần tính năng do dependency optional cung cấp, ứng dụng cần khai báo dependency phù hợp trực tiếp.

### Gradle

| Configuration | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| `implementation` | Dependency nội bộ cần khi biên dịch và chạy module | Starter LoadBalancer trong ứng dụng |
| `api` | Dependency được phơi ra trên API của thư viện và truyền đến consumer | Kiểu của dependency xuất hiện trong public API |
| `runtimeOnly` | Chỉ cần ở runtime, không dùng API khi biên dịch | Driver hoặc implementation được nạp động |
| `compileOnly` | Cần để biên dịch nhưng không được đóng gói như runtime dependency | API do môi trường khác cung cấp |
| `testImplementation` | Chỉ dùng khi biên dịch và chạy test | Thư viện test |

Không nên thay `implementation` bằng `compileOnly` cho starter LoadBalancer trong ứng dụng thông thường: cấu hình tích hợp phải có mặt khi ứng dụng khởi chạy. Cũng không nên dùng `api` chỉ để “cho chắc”; chỉ dùng khi dependency thực sự là một phần API công khai mà module muốn consumer nhìn thấy.

## 7. Kiểm tra dependency tree thay vì đoán

Dependency tree cho biết dependency nào được khai báo trực tiếp, dependency nào được kéo vào bắc cầu và phiên bản nào được chọn sau khi giải quyết xung đột.

Với Maven:

```bash
mvn dependency:tree
```

Để tập trung vào các module Spring Cloud:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để truy tìm lý do một module có mặt hoặc vì sao một phiên bản được chọn:

```bash
./gradlew dependencyInsight --dependency spring-cloud-loadbalancer --configuration runtimeClasspath
```

Khi đọc kết quả, hãy kiểm tra:

1. Starter LoadBalancer có nằm trong runtime classpath không?
2. HTTP client mà ứng dụng sử dụng có mặt và tương thích không?
3. Nếu dùng registry, discovery provider tương ứng có được khai báo không?
4. Có nhiều phiên bản Spring Cloud hoặc Spring Framework cạnh tranh không?
5. Dependency chỉ phục vụ test có bị đưa nhầm vào runtime không?
6. Một thư viện được thêm trực tiếp có thực sự cần thiết, hay chỉ được thêm trùng với dependency bắc cầu?

Nếu một dependency xuất hiện nhiều lần trong cây, điều đó không nhất thiết có nghĩa nhiều bản JAR sẽ được đóng gói. Maven và Gradle áp dụng quy tắc giải quyết phiên bản; hãy xem phiên bản cuối cùng và đường dẫn đưa dependency vào thay vì chỉ đếm số dòng.

## 8. Ví dụ chọn dependency theo tình huống

| Tình huống | Nên khai báo trực tiếp | Chỉ thêm khi cần |
|---|---|---|
| REST đồng bộ với RestClient và instance tĩnh | `spring-boot-starter-web`, `spring-cloud-starter-loadbalancer` | Caffeine, Actuator, test starter |
| Gọi reactive với WebClient và Eureka | `spring-boot-starter-webflux`, `spring-cloud-starter-loadbalancer`, Eureka Client starter | Caffeine, Actuator, test starter |
| Gọi bằng OpenFeign và Consul | `spring-cloud-starter-openfeign`, `spring-cloud-starter-loadbalancer`, Consul Discovery starter | Caffeine, Actuator, test starter |
| Chỉ thử nghiệm hai instance local | HTTP client đang dùng và `spring-cloud-starter-loadbalancer` | Registry ngoài, Caffeine, Actuator nếu không phục vụ mục tiêu thử nghiệm |

Các bảng trên là cách phân loại theo vai trò, không phải POM đầy đủ cho mọi dự án. Hãy đối chiếu với phiên bản Spring Boot/Spring Cloud, cách đóng gói và hạ tầng discovery cụ thể trước khi chốt dependency.

## 9. Những lỗi thường gặp khi khai báo dependency

**Chỉ thêm OpenFeign nhưng mong Feign tự cân bằng tải.** OpenFeign cung cấp cơ chế tạo HTTP client từ interface. Để phân giải tên service thành instance bằng Spring Cloud LoadBalancer, cần có tích hợp LoadBalancer trên classpath và cấu hình phù hợp.

**Thêm dependency registry nhưng thiếu LoadBalancer.** Registry có thể cung cấp thông tin instance, nhưng HTTP client vẫn cần tích hợp bộ chọn để chuyển URL logic thành địa chỉ cụ thể.

**Khai báo phiên bản riêng cho từng module Spring Cloud.** Cách này dễ tạo tổ hợp không tương thích. Dùng BOM phù hợp để quản lý phiên bản theo release train.

**Thêm trực tiếp tất cả module đang thấy trong dependency tree.** Việc này làm POM hoặc Gradle build khó bảo trì và có thể khóa chặt ứng dụng vào chi tiết triển khai nội bộ. Chỉ khai báo module con khi ứng dụng thật sự sử dụng API hoặc tính năng của nó một cách trực tiếp.

**Coi dependency optional là dependency không cần thiết trong mọi trường hợp.** Optional chỉ nói rằng tính năng bổ sung không phải lúc nào cũng cần và trong Maven còn có ý nghĩa truyền dependency. Nếu bật cache Caffeine hoặc một tích hợp cụ thể, ứng dụng vẫn phải cung cấp thư viện mà tính năng đó yêu cầu.

**Thêm cả Web MVC và WebFlux mà không hiểu tác động.** Hai starter có thể cùng xuất hiện trong một ứng dụng, nhưng Spring Boot sẽ chọn loại ứng dụng web dựa trên classpath và cấu hình. Hãy xác định rõ server stack và client API mà ứng dụng cần.

## 10. Quy trình chốt dependency cho dự án

Trước khi thêm thư viện, hãy trả lời lần lượt:

1. Ứng dụng sẽ gọi dịch vụ bằng `RestClient`, `WebClient` hay OpenFeign?
2. Ứng dụng có cần client-side load balancing hay chỉ gọi một địa chỉ cố định?
3. Instance đến từ `SimpleDiscoveryClient`, Eureka, Consul hay Kubernetes?
4. Có yêu cầu cache riêng, health/metrics endpoint hoặc quan sát nâng cao không?
5. Spring Boot đang dùng phiên bản nào và release train Spring Cloud nào tương thích?
6. Dependency tree sau khi build có đúng runtime classpath và không có phiên bản xung đột không?

Sau khi chọn xong, khai báo starter cần thiết trực tiếp, để BOM quản lý phiên bản, chỉ thêm provider discovery và thư viện tùy chọn theo tính năng thực tế, rồi kiểm tra dependency tree. Cách làm này giữ cho cấu hình dự án phản ánh đúng kiến trúc: HTTP client gửi request, discovery cung cấp danh sách instance, còn Spring Cloud LoadBalancer chọn bản sao phù hợp cho service ID.
