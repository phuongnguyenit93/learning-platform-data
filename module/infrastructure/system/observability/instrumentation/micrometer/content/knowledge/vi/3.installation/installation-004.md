# Khai báo phụ thuộc bằng Gradle hoặc Maven

Để sử dụng Micrometer trong ứng dụng Java, cần chọn đúng các thư viện theo cách ứng dụng được xây dựng và nơi metrics sẽ được gửi đến. Với ứng dụng Spring Boot, dependency thường gồm Spring Boot Actuator và một registry tương ứng với backend giám sát. Với ứng dụng Java độc lập, có thể khai báo Micrometer Core cùng registry cần dùng.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, các dependency này là nền tảng để ghi nhận counter, gauge, timer, distribution summary và xuất metrics. Việc chọn dependency nên bám theo hai quyết định: ứng dụng có dùng Spring Boot hay không, và hệ thống giám sát đang sử dụng registry nào.

## 1. Phân biệt các thành phần cần khai báo

Micrometer được chia thành API chung và các adapter registry. Mỗi thành phần có một vai trò riêng:

| Thành phần | Artifact tiêu biểu | Vai trò |
| --- | --- | --- |
| Micrometer Core | `io.micrometer:micrometer-core` | Cung cấp `MeterRegistry`, counter, gauge, timer, distribution summary và các API meter |
| Spring Boot Actuator | `org.springframework.boot:spring-boot-starter-actuator` | Tích hợp observability với Spring Boot, auto-configuration registry và các management endpoint |
| Registry adapter | `io.micrometer:micrometer-registry-prometheus` | Chuyển meter sang định dạng và cơ chế export của backend cụ thể |
| Micrometer BOM | `io.micrometer:micrometer-bom` | Quản lý một bộ phiên bản Micrometer tương thích khi không có BOM của Spring Boot |

Micrometer Core không tự gửi dữ liệu đến một hệ thống giám sát. Ứng dụng cần một registry phù hợp với backend. Ví dụ, Prometheus cần Prometheus registry; một backend khác cần adapter tương ứng. Không cần thêm tất cả registry vào classpath.

Với Spring Boot, Actuator cung cấp phần tích hợp và quản lý. Khi registry adapter được khai báo, Spring Boot có thể phát hiện adapter trên classpath và cấu hình registry tương ứng. Mã nghiệp vụ nhận `MeterRegistry` thông qua dependency injection mà không cần tự khởi tạo một registry cụ thể.

## 2. Spring Boot với Gradle

Ví dụ sau sử dụng Gradle Groovy DSL. Phiên bản Spring Boot được khai báo ở plugin hoặc được quản lý theo quy ước của dự án; không ghi phiên bản riêng cho hai dependency Actuator và Prometheus registry khi đã dùng dependency management của Spring Boot.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Nếu dự án dùng Gradle Kotlin DSL, phần khai báo tương đương là:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-plugin-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

`implementation` đưa Actuator vào compile và runtime classpath. `runtimeOnly` đưa Prometheus registry vào runtime classpath để Spring Boot phát hiện và cấu hình adapter. Nếu mã nguồn của ứng dụng trực tiếp tham chiếu các lớp riêng của Prometheus registry, hãy dùng `implementation` thay cho `runtimeOnly`.

Spring Boot dependency management quản lý phiên bản Micrometer tương thích với phiên bản Spring Boot đang dùng. Vì vậy, không tự thêm một phiên bản Micrometer khác vào registry adapter nếu không có lý do tương thích đã được xác minh. Dự án có thể dùng plugin dependency management như ví dụ, hoặc cơ chế quản lý BOM native của Gradle theo chuẩn đã chọn trong repository.

## 3. Spring Boot với Maven

Khi dự án sử dụng `spring-boot-starter-parent`, parent POM quản lý phiên bản của các dependency thuộc Spring Boot và Micrometer. Chỉ cần khai báo artifact:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>&lt;spring-boot-version&gt;</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Nếu công ty hoặc dự án đã có parent POM riêng, không thể kế thừa `spring-boot-starter-parent`, có thể import `spring-boot-dependencies` BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>&lt;spring-boot-version&gt;</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó khai báo hai dependency Actuator và registry như ví dụ trước, không cần đặt `<version>` riêng cho chúng. Cách này giúp các module Spring Boot và Micrometer đi cùng một bộ phiên bản do BOM quản lý.

## 4. Java độc lập với Spring Boot

Nếu ứng dụng không dùng Spring Boot, hãy khai báo trực tiếp Micrometer Core và registry adapter cần thiết. Ví dụ với Gradle Groovy DSL:

```groovy
dependencies {
    implementation platform('io.micrometer:micrometer-bom:<micrometer-version>')
    implementation 'io.micrometer:micrometer-core'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Với Maven, import Micrometer BOM để quản lý đồng bộ phiên bản Core và registry:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-bom</artifactId>
            <version>&lt;micrometer-version&gt;</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-core</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Trong ví dụ standalone, BOM phải được chọn theo phiên bản Micrometer mà dự án muốn sử dụng. Không phối hợp tùy ý các phiên bản Core và registry; các module cùng dòng phát hành nên được quản lý như một bộ. Nếu ứng dụng dùng một registry khác, thay artifact Prometheus bằng artifact registry tương ứng và giữ Core ở cùng bộ phiên bản.

Khi không dùng Spring Boot, ứng dụng cũng phải tự chịu trách nhiệm tạo và quản lý vòng đời registry, cấu hình adapter và kết nối nó với luồng thu thập hoặc export. Chỉ thêm dependency vào build file không tự tạo endpoint Actuator hay cấu hình Prometheus scrape.

## 5. Cấu hình endpoint Prometheus trong Spring Boot

Sau khi khai báo Actuator và Prometheus registry, có thể expose endpoint Prometheus qua cấu hình ứng dụng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Với cấu hình mặc định của Actuator, endpoint thường có đường dẫn `/actuator/prometheus`. Prometheus có thể scrape endpoint này theo cấu hình scrape target của nó. Nếu ứng dụng thay đổi management base path, port hoặc endpoint path, cấu hình scrape phải khớp với địa chỉ thực tế.

Chỉ expose endpoint cần thiết và bảo vệ endpoint quản trị theo mạng, authentication và chính sách bảo mật của môi trường. Việc thêm dependency không đồng nghĩa endpoint sẽ tự được expose qua HTTP; cần kiểm tra cấu hình exposure của Actuator.

## 6. Chọn registry theo backend

Registry adapter là dependency gắn với hệ thống nhận metrics. Một số lựa chọn phổ biến:

| Nhu cầu | Artifact |
| --- | --- |
| Prometheus scrape metrics | `micrometer-registry-prometheus` |
| Gửi metrics qua OTLP | `micrometer-registry-otlp` |
| Gửi metrics đến Datadog | `micrometer-registry-datadog` |
| Gửi metrics qua StatsD | `micrometer-registry-statsd` |
| Xuất metrics qua JMX | `micrometer-registry-jmx` |

Tên artifact chỉ là điểm bắt đầu để chọn adapter. Trước khi thêm dependency, hãy xác định backend, giao thức export, phiên bản Spring Boot/Micrometer và chính sách kết nối trong môi trường triển khai. Không thêm nhiều registry chỉ vì muốn thử nghiệm; mỗi registry có thể tạo thêm đường export, cấu hình và tải vận hành.

Trong ứng dụng Spring Boot, thông thường chỉ cần thêm registry adapter tương ứng. Spring Boot auto-configuration phát hiện registry trên classpath và cung cấp registry bean phù hợp. Nếu có nhiều registry cùng lúc, hành vi composite và cách export phụ thuộc cấu hình cũng như các registry có mặt; chỉ khai báo những backend ứng dụng thực sự sử dụng.

## 7. Kiểm tra dependency sau khi khai báo

Sau khi chỉnh sửa build file, hãy kiểm tra dependency tree để xác nhận thư viện được resolve và phiên bản đang dùng là phiên bản mong đợi.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Có thể truy vấn riêng một dependency để xem phiên bản được chọn và lý do chọn:

```bash
./gradlew dependencyInsight \
  --dependency micrometer-registry-prometheus \
  --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree
```

Hoặc lọc dependency Micrometer:

```bash
./mvnw dependency:tree -Dincludes=io.micrometer
```

Kiểm tra các điểm sau:

- Có `micrometer-core` thông qua Actuator hoặc khai báo trực tiếp khi chạy standalone.
- Có đúng registry adapter mà backend cần.
- Các module Micrometer được quản lý bằng một BOM tương thích, không bị kéo về nhiều phiên bản ngoài dự kiến.
- Registry xuất hiện trong runtime classpath của ứng dụng Spring Boot.
- Không có registry không sử dụng hoặc dependency trùng lặp do khai báo ở nhiều module.

Nếu dependency tree cho thấy nhiều phiên bản Micrometer, hãy tìm dependency bắc cầu đã đưa phiên bản khác vào và điều chỉnh BOM hoặc dependency constraint ở cấp quản lý. Không giải quyết bằng cách thêm phiên bản tùy ý vào từng dependency, vì cách đó có thể tạo ra một tập thư viện không tương thích.

## 8. Kiểm tra tích hợp ở thời gian chạy

Dependency được resolve thành công mới xác nhận build tool tải được thư viện. Cần khởi động ứng dụng để xác minh Spring Boot thực sự tạo registry và endpoint mong muốn.

Với Spring Boot và Prometheus registry, quy trình kiểm tra cơ bản là:

1. Khởi động ứng dụng trong profile có bật Actuator và cấu hình endpoint.
2. Gọi `/actuator/health` để xác nhận Actuator đang hoạt động.
3. Gọi `/actuator/prometheus` và xác nhận phản hồi có định dạng metrics Prometheus.
4. Tạo một vài thao tác nghiệp vụ có instrumentation để xác nhận meter tương ứng xuất hiện hoặc thay đổi.
5. Kiểm tra Prometheus scrape target và xác nhận target ở trạng thái hoạt động.

Nếu endpoint trả về 404, kiểm tra dependency registry, cấu hình exposure, management port và base path. Nếu endpoint có nhưng không thấy meter tùy chỉnh, kiểm tra mã instrumentation đã được Spring quản lý, meter đã được đăng ký vào registry và luồng nghiệp vụ tạo ra phép đo. Nếu build thành công nhưng ứng dụng báo thiếu registry hoặc không tạo endpoint, kiểm tra runtime classpath và tính tương thích phiên bản.

## 9. Dependency cho kiểm thử

Khi dùng Spring Boot Actuator hoặc khai báo `micrometer-core`, API `SimpleMeterRegistry` có sẵn để kiểm thử instrumentation trong bộ nhớ. Nếu module test không nhận được Core thông qua dependency hiện có, khai báo nó trong test scope phù hợp với build tool. Ví dụ Maven:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-core</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ Gradle:

```groovy
testImplementation 'io.micrometer:micrometer-core'
```

Nếu dependency management đã quản lý Micrometer, không thêm version riêng vào dependency test. Dùng `SimpleMeterRegistry` để kiểm tra counter, timer, tag và các phép đo mà không cần kết nối backend. Kiểm tra endpoint và registry adapter ở integration test riêng, nơi ứng dụng Spring Boot được khởi động với cấu hình tương ứng.

## 10. Lỗi thường gặp khi khai báo thư viện

| Lỗi | Biểu hiện | Cách khắc phục |
| --- | --- | --- |
| Chỉ thêm `micrometer-core` nhưng không có registry adapter | Ứng dụng ghi nhận meter nhưng không xuất đến backend mong muốn | Thêm registry tương ứng với backend |
| Thêm registry nhưng thiếu Actuator trong Spring Boot | Không có tích hợp Actuator hoặc endpoint Prometheus như mong đợi | Thêm `spring-boot-starter-actuator` và cấu hình exposure |
| Không quản lý phiên bản bằng BOM | Core và registry có thể lệch phiên bản | Dùng Spring Boot BOM hoặc Micrometer BOM |
| Đặt registry ở scope không có trong runtime | Spring Boot không phát hiện adapter khi chạy | Đảm bảo registry có mặt trong runtime classpath |
| Thêm tất cả registry vào một ứng dụng | Có nhiều đường export và cấu hình không cần thiết | Chỉ thêm adapter của backend được sử dụng |
| Nhầm dependency với cấu hình endpoint | Dependency đã có nhưng endpoint HTTP vẫn không truy cập được | Kiểm tra Actuator exposure, port và base path |

## 11. Trình tự khai báo đề xuất

Khi bắt đầu một dự án hoặc bổ sung Micrometer vào ứng dụng hiện có, hãy thực hiện theo thứ tự:

1. Xác định dự án dùng Spring Boot hay Java độc lập.
2. Xác định backend giám sát và registry adapter cần dùng.
3. Với Spring Boot, thêm `spring-boot-starter-actuator` và registry adapter; để Spring Boot BOM quản lý phiên bản.
4. Với Java độc lập, thêm `micrometer-core`, registry adapter và import Micrometer BOM.
5. Xác nhận dependency nằm trong compile/runtime classpath phù hợp.
6. Với Spring Boot, cấu hình Actuator exposure và thông tin kết nối cần thiết cho backend.
7. Kiểm tra dependency tree, khởi động ứng dụng và xác minh metrics được xuất.

Khai báo dependency đúng giúp ứng dụng có API ghi nhận và adapter xuất dữ liệu tương thích. Sau bước cài đặt, mã instrumentation có thể sử dụng `MeterRegistry` để ghi nhận các phép đo có ý nghĩa; cấu hình Spring Boot hoặc cấu hình registry của ứng dụng độc lập sẽ quyết định metrics được quản lý và chuyển đến hệ thống giám sát như thế nào.
