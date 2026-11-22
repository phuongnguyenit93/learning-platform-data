# Quản lý phiên bản phụ thuộc bằng Spring Cloud BOM

Một ứng dụng Spring Cloud thường dùng nhiều module cùng lúc: Spring Cloud LoadBalancer để chọn instance phía client, một discovery provider để tìm instance, và có thể thêm OpenFeign hoặc các thành phần khác để gọi dịch vụ. Những module này được phát hành theo các release train có quan hệ tương thích với Spring Boot. Nếu tự chọn phiên bản cho từng dependency, dự án dễ gặp tình trạng các thư viện Spring Cloud không cùng thế hệ hoặc không tương thích với nền tảng Spring Boot đang dùng.

Spring Cloud BOM giải quyết việc quản lý phiên bản tập trung. BOM khai báo tập hợp phiên bản đã được quản lý cho các dependency thuộc một release train. Khi import BOM vào Maven hoặc Gradle, dự án có thể khai báo các starter Spring Cloud mà không cần lặp lại phiên bản ở từng dependency.

Trong module cân bằng tải phía client, BOM giúp giữ nhất quán phiên bản giữa Spring Cloud Commons, Spring Cloud LoadBalancer, discovery integration và các thư viện tích hợp như OpenFeign. BOM quản lý phiên bản thư viện; việc cấu hình discovery, chọn instance, health check, retry hay timeout vẫn cần được thực hiện ở các phần cấu hình tương ứng.

## 1. BOM là gì và giải quyết vấn đề nào?

BOM là viết tắt của *Bill of Materials*. Trong hệ sinh thái Java, BOM thường là một Maven POM có packaging là `pom`, chứa các quy tắc quản lý phiên bản dependency trong phần `dependencyManagement`.

Thay vì khai báo phiên bản ở từng dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    <version>...</version>
</dependency>
```

dự án import một BOM ở cấp quản lý dependency, sau đó khai báo dependency mà không ghi phiên bản:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Maven tra phiên bản được quản lý trong BOM khi giải quyết dependency. Cách này có ba lợi ích chính:

- **Nhất quán:** các module Spring Cloud được chọn theo cùng một release train.
- **Dễ nâng cấp:** thường chỉ cần cập nhật một thuộc tính phiên bản BOM thay vì sửa nhiều dependency.
- **Dễ rà soát:** reviewer có thể nhìn vào một vị trí để biết dự án đang sử dụng release train Spring Cloud nào.

BOM chỉ cung cấp quy tắc phiên bản. Import BOM không tự thêm thư viện vào classpath và cũng không khởi tạo service discovery hoặc load balancer. Muốn sử dụng một tính năng, dự án vẫn phải khai báo starter tương ứng.

## 2. Quan hệ phiên bản giữa Spring Boot và Spring Cloud

Spring Boot và Spring Cloud có chu kỳ phát hành riêng. Spring Cloud tổ chức các module theo release train; mỗi release train được kiểm thử và công bố tương thích với một hoặc một số dòng Spring Boot nhất định.

Vì vậy, khi thiết lập dự án cần chọn theo thứ tự:

1. Xác định phiên bản Spring Boot mà ứng dụng sử dụng.
2. Tra bảng tương thích chính thức của Spring Cloud để chọn release train phù hợp.
3. Lấy phiên bản của artifact BOM `org.springframework.cloud:spring-cloud-dependencies` thuộc release train đó.
4. Import BOM và khai báo các starter Spring Cloud cần thiết.

Không nên lấy số phiên bản Spring Boot rồi gán cho Spring Cloud BOM. Hai hệ thống phiên bản này có quy ước riêng. Tên release train cũng không phải là phiên bản của từng module con; BOM sẽ quản lý các phiên bản module tương ứng.

Ví dụ, dự án có thể lưu phiên bản Spring Boot và Spring Cloud trong hai thuộc tính riêng:

```text
spring-boot.version  = <boot-version>
spring-cloud.version = <compatible-cloud-release-train>
```

Các giá trị trong dấu ngoặc là chỗ cần thay bằng phiên bản thực tế đã được xác nhận trong bảng tương thích của dự án. Không sao chép một cặp phiên bản từ dự án khác nếu chưa kiểm tra dòng Spring Boot và release train đang dùng.

### 2.1. Vì sao không nên trộn nhiều release train?

Giả sử một dự án import BOM của release train A nhưng lại tự đặt phiên bản một module Spring Cloud thuộc release train B. Khi đó, module được ghi đè có thể sử dụng API hoặc hành vi khác với các module còn lại.

Một số lỗi có thể xuất hiện:

- `NoSuchMethodError` khi một module gọi phương thức không tồn tại trong phiên bản module còn lại.
- `ClassNotFoundException` hoặc lỗi khởi tạo bean do các lớp và cấu hình không còn đồng bộ.
- Lỗi auto-configuration hoặc lỗi runtime chỉ xuất hiện khi một luồng tích hợp cụ thể được thực thi.
- Hành vi khác nhau giữa môi trường local, CI và production vì dependency tree không giống nhau.

Giữ một release train thống nhất giúp giảm rủi ro này. Nếu cần ghi đè phiên bản của một module, phải có lý do kỹ thuật rõ ràng, kiểm tra tương thích và ghi lại quyết định đó.

## 3. Import Spring Cloud BOM bằng Maven

Trong Maven, Spring Cloud BOM được import trong phần `dependencyManagement` với `type` là `pom` và `scope` là `import`.

Ví dụ sau minh họa cấu trúc `pom.xml`. Các giá trị phiên bản là placeholder; hãy thay chúng bằng phiên bản tương thích với dự án:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_COMPATIBLE_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>REPLACE_WITH_SUPPORTED_JAVA_VERSION</java.version>
        <spring-cloud.version>REPLACE_WITH_COMPATIBLE_CLOUD_RELEASE_TRAIN</spring-cloud.version>
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
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>

        <!-- Chỉ thêm nếu ứng dụng dùng Eureka làm discovery provider. -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
        </dependency>

        <!-- Chỉ thêm nếu ứng dụng khai báo client bằng OpenFeign. -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-openfeign</artifactId>
        </dependency>
    </dependencies>
</project>
```

Trong ví dụ trên:

- Parent `spring-boot-starter-parent` quản lý nhiều dependency và plugin thuộc hệ sinh thái Spring Boot.
- `spring-cloud-dependencies` quản lý phiên bản các dependency thuộc Spring Cloud release train.
- `spring-cloud-starter-loadbalancer` đưa tích hợp LoadBalancer vào classpath.
- Discovery starter là thành phần riêng, cần chọn theo nền tảng discovery của hệ thống.
- OpenFeign starter chỉ cần khi ứng dụng sử dụng Feign client.

Không bắt buộc phải dùng `spring-boot-starter-parent`. Nếu dự án dùng parent POM nội bộ hoặc không thể kế thừa parent này, có thể import thêm Spring Boot dependencies BOM trong `dependencyManagement` và quản lý plugin theo cấu hình riêng. Điều quan trọng là giữ rõ nguồn quản lý phiên bản cho từng nhóm dependency.

### 3.1. dependencyManagement không tự thêm dependency

Một điểm dễ nhầm trong Maven là `dependencyManagement` chỉ quản lý thông tin dependency, chẳng hạn phiên bản và scope mặc định. Nó không tự đưa dependency vào classpath của module.

Ví dụ, chỉ import Spring Cloud BOM không có nghĩa ứng dụng đã có Spring Cloud LoadBalancer. Muốn dùng LoadBalancer, vẫn cần khai báo:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Khi một dependency được khai báo trong `<dependencies>`, Maven tìm phiên bản phù hợp từ phần quản lý dependency đã import.

### 3.2. Nếu dependency có khai báo version riêng

Nếu một dependency trực tiếp ghi `<version>`, giá trị đó có thể ghi đè phiên bản được quản lý trong BOM cho dependency đó. Điều này hữu ích trong trường hợp ngoại lệ đã được kiểm chứng, nhưng cũng là nguồn gây lệch phiên bản phổ biến.

Trong cấu hình thông thường, hãy bỏ version khỏi các dependency Spring Cloud được BOM quản lý. Nếu phải override, cần ghi chú lý do và xác minh các module liên quan cùng hoạt động với phiên bản được chọn.

## 4. Import Spring Cloud BOM bằng Gradle

Gradle hỗ trợ import Maven BOM thông qua dependency platform. Với Groovy DSL, có thể khai báo như sau:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_COMPATIBLE_BOOT_VERSION'
}

ext {
    set('springCloudVersion', 'REPLACE_WITH_COMPATIBLE_CLOUD_RELEASE_TRAIN')
}

dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    // Chọn provider theo hạ tầng discovery thực tế.
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'

    // Chỉ thêm khi ứng dụng dùng OpenFeign.
    implementation 'org.springframework.cloud:spring-cloud-starter-openfeign'
}
```

Hàm `platform(...)` đưa các constraint phiên bản từ BOM vào cấu hình dependency của Gradle. Các dependency Spring Cloud được khai báo sau đó có thể dùng phiên bản do BOM quản lý mà không cần ghi version riêng.

Nếu dự án dùng Kotlin DSL (`build.gradle.kts`), cú pháp tương đương là:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "REPLACE_WITH_COMPATIBLE_BOOT_VERSION"
}

extra["springCloudVersion"] = "REPLACE_WITH_COMPATIBLE_CLOUD_RELEASE_TRAIN"

dependencies {
    implementation(
        platform(
            "org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}"
        )
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
```

Một lựa chọn khác là dùng plugin `io.spring.dependency-management` và khối `dependencyManagement { imports { mavenBom(...) } }`. Hãy chọn một cách quản lý BOM nhất quán trong dự án và làm theo convention hiện có của build.

### 4.1. platform và enforcedPlatform

Gradle cung cấp hai cách import platform thường được nhắc đến:

- `platform(...)` đưa các constraint từ BOM vào quá trình giải quyết dependency và cho phép Gradle xử lý xung đột theo quy tắc dependency resolution.
- `enforcedPlatform(...)` áp đặt các phiên bản từ platform mạnh hơn, kể cả khi dependency khác yêu cầu phiên bản khác.

Thông thường, `platform(...)` là lựa chọn phù hợp để bắt đầu. Chỉ dùng `enforcedPlatform(...)` khi đã hiểu ảnh hưởng của việc ép phiên bản lên toàn bộ dependency graph, đặc biệt nếu module được chia sẻ hoặc xuất bản cho ứng dụng khác sử dụng.

## 5. Chọn dependency cho ứng dụng cân bằng tải phía client

BOM quản lý phiên bản; starter được chọn theo chức năng ứng dụng cần. Một service gọi service khác có thể cần một số nhóm dependency sau:

| Nhu cầu | Dependency thường dùng | Vai trò |
|---|---|---|
| Gọi HTTP đồng bộ | `spring-boot-starter-web` | Cung cấp nền tảng web và các thành phần HTTP đồng bộ của Spring Boot. |
| Gọi HTTP reactive | `spring-boot-starter-webflux` | Cung cấp WebFlux và WebClient. |
| Cân bằng tải phía client | `spring-cloud-starter-loadbalancer` | Tích hợp cơ chế chọn ServiceInstance của Spring Cloud LoadBalancer. |
| Discovery với Eureka | `spring-cloud-starter-netflix-eureka-client` | Kết nối ứng dụng với Eureka discovery. |
| Khai báo client bằng OpenFeign | `spring-cloud-starter-openfeign` | Cung cấp tích hợp OpenFeign cho Spring Cloud. |
| Gọi service bằng tên logic | LoadBalancer cùng nguồn instance phù hợp | Phân giải service ID thành instance có thể kết nối. |

Tên dependency cần được kiểm tra theo release train và tài liệu của module đang dùng. Không nên thêm tất cả starter vào mọi service. Chẳng hạn, một service chỉ cung cấp API có thể không cần OpenFeign; một service dùng WebClient không nhất thiết phải thêm WebFlux server nếu dự án chỉ cần client và đã quản lý đúng dependency theo kiến trúc.

### 5.1. LoadBalancer không thay thế discovery provider

LoadBalancer cần danh sách instance để lựa chọn. Danh sách đó có thể đến từ discovery provider hoặc một `ServiceInstanceListSupplier` được cấu hình theo cách khác.

Vì vậy, thêm `spring-cloud-starter-loadbalancer` không đồng nghĩa ứng dụng đã có Eureka, Consul hoặc Kubernetes discovery. Nếu hệ thống sử dụng Eureka, cần thêm và cấu hình Eureka client. Nếu dùng nền tảng discovery khác, chọn integration phù hợp với nền tảng đó.

Đối với OpenFeign, hãy kiểm tra dependency tree để bảo đảm client load-balanced có thành phần LoadBalancer cần thiết. Việc khai báo `@FeignClient(name = "inventory-service")` chỉ mô tả tên client; nó không tự cung cấp một registry hay danh sách instance.

### 5.2. Không thêm dependency trùng vai trò

Trước khi thêm starter, hãy xác định ứng dụng cần:

- API server để nhận request.
- HTTP client để gọi service khác.
- Discovery client để tìm instance.
- LoadBalancer để chọn instance.
- Declarative client như OpenFeign nếu muốn khai báo interface.

Một ứng dụng có thể cần nhiều vai trò, nhưng không nên thêm starter chỉ vì thấy chúng xuất hiện trong ví dụ khác. Dependency thừa làm tăng kích thước classpath, số auto-configuration cần khởi tạo và bề mặt phải kiểm tra khi nâng cấp.

## 6. Quy trình thiết lập phiên bản cho một dự án mới

Có thể áp dụng quy trình sau khi khởi tạo service mới:

1. **Chọn nền tảng:** xác định dòng Spring Boot, Java và build tool mà dự án sẽ dùng.
2. **Xác nhận tương thích:** tra release train Spring Cloud tương thích với Spring Boot đã chọn.
3. **Khai báo BOM:** import `spring-cloud-dependencies` một lần tại nơi quản lý dependency chung.
4. **Chọn starter:** thêm LoadBalancer, discovery provider và HTTP client theo đúng vai trò của service.
5. **Đồng bộ các module:** nếu repository có nhiều module Maven hoặc Gradle, đặt BOM ở cấp phù hợp để các module dùng cùng quy tắc phiên bản.
6. **Kiểm tra dependency graph:** xác nhận phiên bản thực tế được giải quyết đúng và không có override ngoài dự kiến.
7. **Xác minh runtime:** chạy ứng dụng và kiểm tra discovery, danh sách instance cùng khả năng gọi service bằng service ID.

Với repository multi-module, cần xác định nơi đặt BOM theo cấu trúc build. Nếu mỗi module tự khai báo một BOM khác nhau, dự án có thể tạo ra dependency graph không đồng nhất. Nên quản lý release train tập trung ở parent POM hoặc convention/plugin chung của Gradle khi phù hợp.

## 7. Kiểm tra dependency sau khi import BOM

Sau khi sửa build file, hãy kiểm tra dependency mà Maven hoặc Gradle thực sự giải quyết. Không nên chỉ nhìn vào file cấu hình vì dependency bắc cầu có thể đưa thêm phiên bản hoặc module ngoài dự kiến.

### 7.1. Maven

Xem cây dependency Spring Cloud:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

Xem effective POM để kiểm tra cấu hình sau khi Maven hợp nhất parent POM, properties và BOM:

```bash
mvn help:effective-pom
```

Khi cần tìm nguồn của một phiên bản hoặc xung đột, có thể xem dependency tree ở chế độ verbose:

```bash
mvn dependency:tree -Dverbose
```

Trong output, kiểm tra các artifact Spring Cloud như Commons, LoadBalancer, discovery client và OpenFeign có thuộc cùng bộ phiên bản do release train quản lý hay không. Nếu một artifact có phiên bản khác thường, tìm dependency trực tiếp hoặc dependency bắc cầu đã đưa phiên bản đó vào.

### 7.2. Gradle

Liệt kê dependency runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Truy vấn lý do Gradle chọn một dependency cụ thể:

```bash
./gradlew dependencyInsight \
    --dependency spring-cloud-loadbalancer \
    --configuration runtimeClasspath
```

Trên Windows, có thể dùng `gradlew.bat` thay cho `./gradlew`. Khi đọc kết quả, chú ý phiên bản được chọn, constraint từ platform và dependency nào yêu cầu phiên bản khác.

### 7.3. Kiểm tra ở cấp ứng dụng

Dependency tree đúng là điều kiện cần, nhưng chưa đủ để xác nhận giao tiếp service hoạt động. Sau khi build thành công, cần kiểm tra các bước ở runtime:

- Ứng dụng khởi động được và các bean HTTP client được tạo thành công.
- Discovery client kết nối được với provider nếu dùng registry.
- Service ID trả về danh sách instance hợp lệ.
- HTTP client đã được tích hợp với LoadBalancer.
- Request có thể chọn instance và nhận response.
- Log và metrics cho phép phân biệt lỗi discovery, lỗi chọn instance và lỗi kết nối.

BOM không cấu hình những hành vi này. Nó chỉ bảo đảm dependency được chọn theo tập phiên bản đã quản lý.

## 8. Các lỗi thường gặp khi quản lý phiên bản

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Maven không resolve được BOM | Sai group/artifact/version, repository không truy cập được hoặc phiên bản không tồn tại. | Kiểm tra tọa độ `spring-cloud-dependencies`, repository và giá trị property. |
| Dependency Spring Cloud có phiên bản lệch nhau | Ghi version trực tiếp, import nhiều BOM hoặc dependency bắc cầu đưa phiên bản khác vào. | Kiểm tra effective POM và dependency tree; bỏ override không cần thiết. |
| `NoSuchMethodError` hoặc lỗi class khi khởi động | Module Spring Boot/Spring Cloud không tương thích hoặc các module Cloud bị trộn phiên bản. | Chọn lại release train theo bảng tương thích và kiểm tra dependency graph. |
| Có LoadBalancer nhưng không tìm thấy instance | Chưa cấu hình discovery provider hoặc chưa có nguồn instance. | Cấu hình discovery integration hoặc supplier cung cấp instance. |
| OpenFeign gọi service ID nhưng không được load balance | Thiếu thành phần tích hợp LoadBalancer hoặc cấu hình client chưa đúng. | Kiểm tra starter, dependency tree và cấu hình Feign/LoadBalancer. |
| Local chạy nhưng CI hoặc production lỗi | Cache dependency, profile hoặc build file giữa môi trường không giống nhau. | So sánh effective POM/dependency report và dùng cùng lock/configuration trong pipeline. |

Khi nâng cấp, nên thay đổi phiên bản Spring Boot và Spring Cloud theo cặp tương thích, sau đó chạy lại kiểm tra dependency graph và kiểm thử tích hợp. Tránh cập nhật riêng một JAR Spring Cloud để xử lý lỗi runtime nếu chưa xác định nguyên nhân.

## 9. Nguyên tắc duy trì BOM lâu dài

Để dependency graph ổn định khi dự án phát triển, nên áp dụng một số nguyên tắc:

- Quản lý phiên bản Spring Boot và Spring Cloud ở vị trí trung tâm, dễ tìm và review.
- Mỗi ứng dụng hoặc nhóm module liên quan dùng một release train Spring Cloud nhất quán.
- Không ghi version riêng cho dependency Spring Cloud đã được BOM quản lý, trừ khi có ngoại lệ được kiểm chứng.
- Chỉ thêm starter tương ứng với vai trò thực tế của service.
- Kiểm tra dependency tree khi thêm thư viện, thay đổi BOM hoặc nâng cấp framework.
- Ghi lại lý do khi override dependency hoặc dùng `enforcedPlatform`.
- Cập nhật theo bảng tương thích và ghi chú phát hành chính thức, sau đó chạy build và kiểm thử tích hợp.

Trong môi trường doanh nghiệp, có thể chuẩn hóa BOM tại parent POM hoặc convention plugin dùng chung để các service không tự chọn release train khác nhau. Tuy nhiên, việc dùng chung cấu hình cần tính đến vòng đời nâng cấp của từng ứng dụng và khả năng chúng đang ở các dòng Spring Boot khác nhau.

## 10. Kết luận

Spring Cloud BOM là điểm quản lý phiên bản tập trung cho các module Spring Cloud. Import `org.springframework.cloud:spring-cloud-dependencies` giúp các starter như LoadBalancer, discovery integration và OpenFeign dùng phiên bản thuộc cùng release train, đồng thời giảm việc khai báo version lặp lại trong build file.

Khi thiết lập dự án, hãy chọn release train theo bảng tương thích Spring Boot, import BOM bằng `dependencyManagement` của Maven hoặc `platform(...)` của Gradle, rồi chỉ khai báo các starter mà service thực sự cần. Cuối cùng, kiểm tra dependency graph và xác minh luồng discovery đến HTTP request ở runtime. Cách làm này tạo nền tảng phiên bản nhất quán để phát triển và vận hành giao tiếp giữa các dịch vụ.

