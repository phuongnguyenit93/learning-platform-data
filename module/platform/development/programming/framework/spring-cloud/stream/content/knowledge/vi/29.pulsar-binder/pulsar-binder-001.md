# Chọn artifact và phiên bản Pulsar Binder tương thích

Để dùng Apache Pulsar trong ứng dụng Spring Cloud Stream, cần chọn đúng binder artifact và căn chỉnh nó với Spring Boot, Spring Cloud release train, Spring Cloud Stream, Pulsar client và Pulsar broker. Các thành phần này có version riêng; không thể lấy số version của một thành phần rồi gán cho tất cả.

Việc chọn artifact còn phụ thuộc thế hệ tích hợp. Spring Cloud Stream 5.0.x dùng dòng binder do Spring for Apache Pulsar phát hành. Từ tháng 11/2026, Spring for Apache Pulsar đã chuyển sang dự án Apache Pulsar với tên Apache Pulsar support for Spring. Phiên bản Spring Pulsar 2.0.8 là bản cuối do Spring phát hành; dự án Apache đã phát hành dòng 3.0.0-M1 với Maven coordinates và Java packages mới. Spring Cloud 2026.0.0 cũng đã phát hành cùng Spring Boot 4.2.0 và Spring Cloud Stream 5.1.0. Vì vậy, khi chọn dependency cần xác định rõ đang duy trì ứng dụng trên dòng Spring cũ, dùng binder trong Spring Cloud Stream 5.1.0, hay chuyển sang dòng Apache Pulsar mới.

Bài học này hướng dẫn đọc compatibility matrix, chọn Maven/Gradle coordinates, sử dụng BOM, kiểm soát Pulsar client và Netty, kiểm tra dependency tree, xử lý xung đột classpath và lập kế hoạch nâng cấp mà không làm thay đổi broker ngoài ý muốn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt artifact binder với Spring Boot starter, Pulsar client và BOM.
- Xác định Spring Boot version tương thích với Spring Cloud release train.
- Chọn binder theo thế hệ Spring Cloud Stream và nơi dự án được duy trì.
- Nhận biết Maven coordinates cũ và mới của Pulsar integration.
- Dùng Spring Cloud BOM hoặc Pulsar Spring BOM đúng phạm vi.
- Căn chỉnh Pulsar client version và Netty version.
- Hiểu vì sao không nên thêm đồng thời binder cũ và binder mới.
- Kiểm tra dependency tree và effective POM để tìm version conflict.
- Xác minh build, classpath và kết nối với Pulsar broker trước khi triển khai.

## 1. Các thành phần có version riêng

Một ứng dụng Spring Cloud Stream kết nối Pulsar có thể có các lớp dependency sau:

| Thành phần | Vai trò | Ví dụ tên artifact |
|---|---|---|
| Spring Boot | Nền tảng ứng dụng, auto-configuration và dependency management | `spring-boot-starter` |
| Spring Cloud release train | Căn chỉnh các dự án Spring Cloud | `spring-cloud-dependencies` |
| Spring Cloud Stream | Programming model, binding abstraction và binder SPI | `spring-cloud-stream` |
| Pulsar binder | Nối binding với Pulsar topic, producer và consumer | `pulsar-spring-cloud-stream-binder` |
| Spring Pulsar integration | Template, listener, auto-configuration và tiện ích Spring cho Pulsar | `pulsar-spring` |
| Pulsar Java client | Giao tiếp protocol với Pulsar broker | `pulsar-client` hoặc các artifact client tương ứng |
| Pulsar broker | Hệ thống messaging chạy ở server | Apache Pulsar cluster |
| BOM | Quản lý tập version tương thích | `spring-cloud-dependencies`, `pulsar-spring-bom` |

Không nhầm các version sau:

- Spring Boot version là version nền tảng ứng dụng.
- Spring Cloud release train version là version BOM của hệ sinh thái Spring Cloud.
- Spring Cloud Stream version là version của programming model và binder SPI.
- Pulsar binder version là version của adapter nối Spring Cloud Stream với Pulsar.
- Spring Pulsar integration version là version của các thư viện Spring cho Pulsar.
- Pulsar client version là version thư viện client chạy trong ứng dụng.
- Pulsar broker version là version cluster server.

Một ứng dụng có thể chạy Spring Boot 4.2.0, Spring Cloud 2026.0.0, Spring Cloud Stream 5.1.0, binder Apache Pulsar 3.0.0-M1 và Pulsar client 5.0.x. Các số version khác nhau là bình thường; điều quan trọng là các tổ hợp đó được tài liệu hoặc BOM hỗ trợ.

## 2. Đọc compatibility matrix trước khi thêm binder

Spring Cloud release train được phát hành theo từng dòng Spring Boot. Chọn release train trước, rồi mới chọn các dependency thuộc train đó.

Tại thời điểm 24/11/2026, các mốc chính thức liên quan gồm:

| Spring Cloud release train | Spring Boot tương thích | Spring Cloud Stream trong train | Ghi chú |
|---|---|---|---|
| 2026.0.0 (Paddington) | 4.2.0 | 5.1.0 | Phát hành ngày 20/11/2026 |
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x từ 2025.1.2 | 5.0.x | Chọn service release mới nhất trong train |
| 2025.0.x (Northfields) | 3.5.x | 4.3.x | Dòng cũ hơn |

Bảng này là các mốc của release train, không phải bảng tương thích trực tiếp giữa mọi Pulsar broker và Pulsar client. Khi chọn binder, tiếp tục kiểm tra tài liệu binder và dependency management của đúng release train.

### 2.1. Ví dụ: ứng dụng Spring Boot 4.2.0

Nếu ứng dụng dùng Spring Boot 4.2.0, Spring Cloud 2026.0.0 là release train tương ứng. Release train này chứa Spring Cloud Stream 5.1.0.

Maven BOM:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
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
~~~

Spring Cloud BOM quản lý version các artifact thuộc release train. Khi dependency được BOM quản lý, không tự đặt một version khác chỉ để làm cho số version trông giống Spring Boot.

### 2.2. Không ghép release train theo cảm tính

Ví dụ không nên:

~~~text
Spring Boot 4.2.x
Spring Cloud 2025.0.x
Spring Cloud Stream 5.1.x
Pulsar binder 4.3.x
~~~

Các dòng trên thuộc những thế hệ khác nhau. Một dependency có thể vẫn resolve được từ Maven Central nhưng compile thành công không chứng minh tổ hợp được hỗ trợ. Hãy dùng compatibility matrix, BOM và tài liệu của đúng release.

## 3. Chọn binder theo thế hệ phát hành

Pulsar integration cho Spring Cloud Stream đã thay đổi nơi phát triển và Maven coordinates. Cần nhận biết ba trường hợp thường gặp.

### 3.1. Dòng Spring Pulsar trước khi chuyển dự án

Tài liệu Spring Cloud Stream 5.0.x hướng dẫn sử dụng binder artifact:

~~~xml
<dependency>
    <groupId>org.springframework.pulsar</groupId>
    <artifactId>spring-pulsar-spring-cloud-stream-binder</artifactId>
</dependency>
~~~

Đây là coordinate trong tài liệu binder của thế hệ Spring for Apache Pulsar 2.x. Spring Pulsar 2.0.8 là bản cuối được Spring duy trì. Ứng dụng đang chạy ổn định trên dòng này có thể tiếp tục dùng trong lúc chuẩn bị migration, nhưng không nên kỳ vọng các bản vá mới từ dự án Spring sau khi dự án chuyển giao.

Một số thế hệ binder Spring Cloud Stream cũng được phát hành dưới coordinate:

~~~text
org.springframework.cloud:spring-cloud-stream-binder-pulsar
~~~

Migration guide của dự án Apache ghi nhận coordinate này trong danh sách artifact cũ được thay thế. Khi bảo trì ứng dụng hiện hữu, hãy đọc pom.xml, Gradle dependency declaration và dependency tree để xác định chính xác artifact đang được sử dụng; không thêm cả hai coordinate Spring-side chỉ vì tìm thấy chúng trong các tài liệu của những thế hệ khác nhau.

### 3.2. Dòng Spring Cloud Stream 5.1.0

Spring Cloud 2026.0.0 phát hành Spring Cloud Stream 5.1.0. Thông báo chuyển dự án cho biết các ứng dụng có thể tiếp tục dùng Spring Pulsar 2.0.8 và binder 5.1.0 trong giai đoạn chuyển tiếp.

Nếu ứng dụng chủ đích sử dụng binder được quản lý trong Spring Cloud release train 2026.0.0, hãy dùng artifact thuộc train đó và để Spring Cloud BOM quản lý version. Coordinate của binder trong dòng Spring Cloud là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-pulsar</artifactId>
</dependency>
~~~

Không ghi version thủ công khi BOM 2026.0.0 đã quản lý artifact. Cách này giúp binder cùng dòng với Spring Cloud Stream 5.1.0. Đây là đường nâng cấp tương thích cho ứng dụng Spring Cloud; dự án tích hợp Pulsar mới đã chuyển sang Apache Pulsar để nhận bảo trì và phát triển tiếp.

### 3.3. Dòng Apache Pulsar support for Spring

Từ ngày 10/11/2026, Spring for Apache Pulsar chuyển sang dự án con của Apache Pulsar với tên Apache Pulsar support for Spring. Bản phát hành đầu tiên là `3.0.0-M1`, được công bố trên Maven Central.

Binder artifact mới:

~~~xml
<dependency>
    <groupId>org.apache.pulsar</groupId>
    <artifactId>pulsar-spring-cloud-stream-binder</artifactId>
    <version>3.0.0-M1</version>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("org.apache.pulsar:pulsar-spring-cloud-stream-binder:3.0.0-M1")
}
~~~

Đây là coordinate thuộc dự án Apache Pulsar support for Spring, không phải artifact do Spring Cloud BOM quản lý. `3.0.0-M1` là milestone release; cần đánh giá trạng thái phát hành và chính sách hỗ trợ trước khi chọn cho production. Khi có bản GA mới hơn, dùng version được công bố trong tài liệu chính thức của Apache Pulsar support for Spring.

### 3.4. Bảng quyết định

| Tình huống | Artifact cần xem xét | Cách quản lý version |
|---|---|---|
| Ứng dụng cũ theo tài liệu Spring Cloud Stream 5.0.x | `org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder` | Theo BOM/tài liệu của dòng Spring Pulsar tương ứng |
| Ứng dụng dùng binder của Spring Cloud Stream 5.1.0 | `org.springframework.cloud:spring-cloud-stream-binder-pulsar` | Spring Cloud 2026.0.0 BOM |
| Ứng dụng chuyển sang dự án Apache Pulsar support for Spring | `org.apache.pulsar:pulsar-spring-cloud-stream-binder` | Khai báo version hoặc import `pulsar-spring-bom` |

Chọn một đường dependency cho mỗi ứng dụng. Không để binder Spring-side cũ và binder Apache-side mới cùng xuất hiện trên classpath.

## 4. Phân biệt artifact, starter và BOM

### 4.1. Binder artifact

Binder là implementation của Spring Cloud Stream Binder SPI. Nó kết nối các binding như `orders-in-0` và `orders-out-0` với Pulsar topic, producer và consumer. Đây là dependency cần có để ứng dụng Spring Cloud Stream sử dụng Pulsar làm middleware.

### 4.2. Spring Boot starter

Starter gom dependency và auto-configuration để xây dựng ứng dụng Spring Boot dùng Pulsar API trực tiếp. Ví dụ starter của dự án Apache:

~~~xml
<dependency>
    <groupId>org.apache.pulsar</groupId>
    <artifactId>pulsar-spring-boot-starter</artifactId>
    <version>3.0.0-M1</version>
</dependency>
~~~

Nếu mục tiêu là dùng Spring Cloud Stream binder, hãy bắt đầu từ binder artifact. Chỉ thêm starter riêng khi ứng dụng cần các API Spring Pulsar khác ngoài những gì binder đã cung cấp và dependency graph cho thấy không bị trùng auto-configuration.

Không thêm starter chỉ vì nghĩ mọi Spring Boot ứng dụng đều phải khai báo starter Pulsar riêng. Binder đã tích hợp các thành phần cần thiết theo dependency của nó.

### 4.3. BOM

BOM là POM quản lý version. Nó không phải thư viện runtime và không thay thế binder artifact.

Hai BOM có phạm vi khác nhau:

- `spring-cloud-dependencies`: quản lý các dự án thuộc Spring Cloud release train.
- `pulsar-spring-bom`: quản lý các artifact thuộc Apache Pulsar support for Spring.

Khi chuyển sang Apache artifact, Spring Cloud BOM không tự quản lý version `org.apache.pulsar:pulsar-spring-cloud-stream-binder`. Hãy khai báo version trực tiếp hoặc import BOM của dự án Apache.

## 5. Quản lý version của dòng Apache mới

Apache Pulsar support for Spring 3.0.0-M1 yêu cầu Pulsar 5.0.x client. Dự án này không được Spring Boot quản lý version như trước. Vì vậy, Spring Boot application cần đặt `pulsar.version`; dự án cũng khuyến nghị đặt `netty.version` theo bản 4.2.x phù hợp.

Ví dụ Maven khai báo version trực tiếp:

~~~xml
<properties>
    <pulsar-spring.version>3.0.0-M1</pulsar-spring.version>
    <pulsar.version>5.0.1</pulsar.version>
    <netty.version>4.2.20.Final</netty.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.pulsar</groupId>
        <artifactId>pulsar-spring-cloud-stream-binder</artifactId>
        <version>${pulsar-spring.version}</version>
    </dependency>
</dependencies>
~~~

Các version trong ví dụ minh họa cấu hình được công bố cùng bản 3.0.0-M1; trước khi dùng, hãy kiểm tra release notes và yêu cầu client/Netty của bản Apache support for Spring mà dự án chọn.

### 5.1. Dùng Pulsar Spring BOM

Nếu có nhiều artifact của Apache Pulsar support for Spring, import BOM để tránh khai báo các version Spring integration lệch nhau:

~~~xml
<properties>
    <pulsar-spring.version>3.0.0-M1</pulsar-spring.version>
    <pulsar.version>5.0.1</pulsar.version>
    <netty.version>4.2.20.Final</netty.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.pulsar</groupId>
            <artifactId>pulsar-spring-bom</artifactId>
            <version>${pulsar-spring.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.apache.pulsar</groupId>
        <artifactId>pulsar-spring-cloud-stream-binder</artifactId>
    </dependency>
</dependencies>
~~~

BOM quản lý version của các artifact thuộc Apache Pulsar support for Spring. `pulsar.version` vẫn cần được đặt vì Spring Boot có thể quản lý một Pulsar client version cũ hơn. `netty.version` là thuộc tính khuyến nghị để căn chỉnh Netty với client mới.

Gradle:

~~~kotlin
extra["pulsar.version"] = "5.0.1"
extra["netty.version"] = "4.2.20.Final"

dependencies {
    implementation(platform("org.apache.pulsar:pulsar-spring-bom:3.0.0-M1"))
    implementation("org.apache.pulsar:pulsar-spring-cloud-stream-binder")
}
~~~

### 5.2. Không dùng BOM để che giấu version conflict

Khi import nhiều BOM, thứ tự và precedence của dependency management có thể ảnh hưởng version cuối cùng. Không nên thêm một BOM chỉ để ép một thư viện về version mới mà chưa hiểu dependency graph.

Sau khi import BOM:

- Xem effective POM hoặc Gradle dependency insight.
- Xác minh version Pulsar client thực tế.
- Kiểm tra Netty và Jackson không bị kéo về các version xung đột.
- Xác minh không có hai binder implementation cùng được nạp.
- Chạy build và integration test với broker.

## 6. Pulsar client version khác broker version

Pulsar client là thư viện chạy trong JVM của ứng dụng. Pulsar broker là server trong cluster. Hai version này không nhất thiết phải giống nhau.

Apache Pulsar support for Spring 3.0.0-M1 yêu cầu Pulsar 5.0.x client. Tài liệu migration cho biết client 5.0.x tương thích với các broker cũ hơn, vì vậy việc nâng client không đồng nghĩa phải nâng broker ngay lập tức.

Tuy nhiên, cần phân biệt:

- Protocol compatibility giữa client và broker.
- Feature support của client khi nói chuyện với broker cũ.
- Feature support mới của broker mà client cũ không biết.
- Schema, transaction và authentication features được bật ở cluster.

Một client mới có thể kết nối broker cũ nhưng không có nghĩa mọi tính năng mới của client đều khả dụng trên broker đó. Kiểm tra bảng tương thích Pulsar client/broker và release notes trước khi rollout.

### 6.1. Unshaded client dependencies

Dòng Apache support for Spring mới chuyển khỏi `pulsar-client-all` sang các artifact client không shade, như `pulsar-client-original` và `pulsar-client-admin-original`. Điều này làm Netty, Jackson và một số thư viện khác trở thành dependency thông thường trên classpath.

Hệ quả:

- Có thể xuất hiện conflict với Netty/Jackson do framework hoặc thư viện khác kéo vào.
- Các class trong package `org.apache.pulsar.shade` không còn khả dụng.
- Không nên viết code phụ thuộc vào implementation đã được relocate bên trong `pulsar-client-all`.
- Cần kiểm tra dependency tree sau migration.

Nếu một dependency khác vẫn kéo `pulsar-client-all` vào, xem xét exclude theo hướng dẫn chính thức và kiểm tra kỹ các class cần thiết còn có mặt.

## 7. Thay đổi package khi chuyển sang Apache Pulsar support for Spring

Migration không chỉ thay Maven coordinates. Java package cũng thay đổi:

| Package cũ | Package mới |
|---|---|
| `org.springframework.pulsar` | `org.apache.pulsar.spring` |
| `org.springframework.boot.pulsar` | `org.apache.pulsar.spring.boot` |
| `org.springframework.cloud.stream.binder.pulsar` | `org.apache.pulsar.spring.cloud.stream.binder` |

Ví dụ import:

~~~java
// Trước khi chuyển
import org.springframework.pulsar.core.PulsarTemplate;

// Sau khi chuyển
import org.apache.pulsar.spring.core.PulsarTemplate;
~~~

Tên package thực tế cần tra trong migration guide/Javadoc của version đang dùng; ví dụ trên minh họa quy tắc đổi namespace.

Các property prefix `spring.pulsar.*` và `spring.cloud.stream.pulsar.*` được công bố là không thay đổi trong migration. Điều đó giúp giảm số thay đổi cấu hình, nhưng không có nghĩa dependency và Java import có thể giữ nguyên.

### 7.1. Thay thế, không thêm song song

Khi chuyển từ Spring-side binder sang Apache-side binder:

1. Xóa dependency binder cũ.
2. Thêm `org.apache.pulsar:pulsar-spring-cloud-stream-binder`.
3. Chuyển các import Java liên quan.
4. Căn chỉnh `pulsar.version` và `netty.version`.
5. Kiểm tra không còn auto-configuration hoặc binder cũ trên classpath.
6. Build và chạy integration test.

Không giữ cả binder cũ và binder mới chỉ để thử nghiệm trong cùng một runtime. Hai bộ auto-configuration và SPI metadata có thể tạo binding trùng hoặc bean xung đột.

## 8. Ví dụ cấu hình ứng dụng dùng Pulsar binder

Sau khi chọn artifact phù hợp, cấu hình Spring Cloud Stream vẫn dùng function và binding như các binder khác.

Java:

~~~java
@SpringBootApplication
public class PulsarEventsApplication {

    @Bean
    public Supplier<OrderCreated> orderSupplier() {
        return () -> new OrderCreated(
                UUID.randomUUID().toString(),
                Instant.now());
    }

    @Bean
    public Function<OrderCreated, OrderAccepted> acceptOrder() {
        return order -> new OrderAccepted(
                order.orderId(),
                "ACCEPTED",
                order.createdAt());
    }

    @Bean
    public Consumer<OrderAccepted> logAcceptedOrder() {
        return order -> log.info("Accepted order {}", order.orderId());
    }

    record OrderCreated(String orderId, Instant createdAt) {}

    record OrderAccepted(
            String orderId,
            String status,
            Instant createdAt) {}
}
~~~

YAML:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSupplier;acceptOrder;logAcceptedOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
        acceptOrder-out-0:
          destination: orders.accepted
        logAcceptedOrder-in-0:
          destination: orders.accepted
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    admin:
      service-url: http://localhost:8080
~~~

Đây là ví dụ cấu trúc ứng dụng, không phải cấu hình triển khai production hoàn chỉnh. Với nhiều function, `spring.cloud.function.definition` chọn các bean cần kích hoạt. Supplier có output binding, Function có input/output binding và Consumer có input binding.

### 8.1. Property precedence

Pulsar binder sử dụng Spring Pulsar auto-configuration. Có thể cấu hình ở ba cấp:

| Cấp | Prefix | Phạm vi |
|---|---|---|
| Spring Boot/Pulsar | `spring.pulsar.*` | Cấu hình client chung |
| Binder | `spring.cloud.stream.pulsar.binder.*` | Cấu hình chung cho binder |
| Extended binding | `spring.cloud.stream.pulsar.bindings.<binding-name>.*` | Cấu hình riêng cho binding |

Precedence của binder từ cao xuống thấp:

1. Extended binding properties.
2. Binder properties.
3. Spring Boot properties.

Nếu hai binding cần authentication, schema hoặc consumer settings khác nhau, dùng extended binding properties thay vì đặt một giá trị chung cho toàn ứng dụng.

## 9. Kiểm tra dependency tree

Một build thành công chưa đủ để chứng minh ứng dụng dùng đúng binder và Pulsar client. Hãy kiểm tra dependency graph thực tế.

### 9.1. Maven

Hiển thị dependency liên quan:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.pulsar,org.springframework.pulsar,org.springframework.cloud,org.springframework.boot
~~~

Xem effective POM:

~~~bash
./mvnw help:effective-pom
~~~

Kiểm tra:

- Binder artifact đúng groupId/artifactId.
- Chỉ có một thế hệ Pulsar binder được nạp.
- Version `pulsar-client` là version mong muốn.
- Không còn dependency cũ ngoài ý muốn.
- Version Netty không bị kéo lệch.
- Spring Cloud Stream cùng dòng với Spring Cloud BOM.

### 9.2. Gradle

Xem runtime dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem lý do một dependency được chọn:

~~~bash
./gradlew dependencyInsight --dependency pulsar --configuration runtimeClasspath
./gradlew dependencyInsight --dependency netty --configuration runtimeClasspath
~~~

Gradle có thể chọn một version do conflict resolution. Hãy đọc lý do version đó được chọn thay vì chỉ nhìn dòng dependency khai báo trong build.gradle.

### 9.3. Kiểm tra classpath lúc chạy

Nếu ứng dụng khởi động nhưng không tìm thấy binder, kiểm tra:

- Dependency có nằm trong runtimeClasspath hay chỉ compile/test scope?
- Binder có metadata SPI và auto-configuration được đóng gói không?
- Có exclusion loại bỏ binder hoặc Pulsar client không?
- Có hai version của cùng thư viện trong fat JAR hoặc container image không?
- Dependency cache có đang dùng artifact cũ không?

Không giải quyết lỗi classpath bằng cách copy JAR thủ công vào thư mục ứng dụng. Hãy sửa build declaration để dependency graph có thể tái tạo.

## 10. Những lỗi chọn version thường gặp

1. **Dùng nhầm artifact ID**: Pulsar binder không có cùng coordinate với Kafka hoặc Rabbit binder. Hãy dùng coordinate trong tài liệu của đúng thế hệ.
2. **Chỉ thay groupId mà giữ artifactId cũ**: migration sang Apache đổi cả groupId, artifactId và package. Hãy thay theo migration guide.
3. **Dùng Spring Cloud BOM để quản lý Apache artifact mới**: BOM Spring Cloud không tự quản lý version `org.apache.pulsar`. Hãy đặt version hoặc import `pulsar-spring-bom`.
4. **Không đặt `pulsar.version`**: Spring Boot có thể quản lý Pulsar client cũ. Hãy đặt property theo yêu cầu của Apache support for Spring.
5. **Bỏ qua Netty**: client unshaded đưa Netty thành dependency thông thường. Hãy kiểm tra và căn chỉnh `netty.version`.
6. **Trộn Spring Boot và Spring Cloud không tương thích**: dependency vẫn có thể resolve nhưng runtime có thể lỗi. Hãy bắt đầu từ compatibility matrix.
7. **Thêm binder cũ và mới cùng lúc**: có thể tạo duplicate auto-configuration hoặc binder registration. Hãy thay thế dependency cũ.
8. **Nhầm client version với broker version**: client và broker có thể khác version trong phạm vi tương thích. Hãy xem bảng client/broker compatibility.
9. **Dùng milestone như bản GA**: `3.0.0-M1` là milestone. Hãy kiểm tra trạng thái phát hành và chính sách hỗ trợ trước production.
10. **Dùng package cũ sau khi đổi artifact**: code không compile hoặc runtime không tìm thấy class. Hãy chuyển import theo migration guide.
11. **Giữ `pulsar-client-all` cùng client unshaded**: có thể gây duplicate hoặc conflict class. Hãy kiểm tra dependency tree và loại bỏ artifact không cần thiết.
12. **Tự đặt version từng module Spring khác nhau**: các module có thể lệch API. Hãy dùng BOM để quản lý tập version nhất quán.
13. **Chỉ kiểm tra compile**: compile không chứng minh topic provisioner, authentication hoặc broker compatibility hoạt động. Hãy chạy integration test với Pulsar.

## 11. Quy trình chọn artifact và version

Khi bắt đầu một ứng dụng hoặc nâng cấp binder:

1. Xác định Spring Boot version của ứng dụng.
2. Tra Spring Cloud compatibility matrix và chọn release train tương ứng.
3. Xác định Spring Cloud Stream version mà release train cung cấp.
4. Chọn thế hệ Pulsar binder: Spring-side transitional hay Apache-owned.
5. Tra Maven coordinates trong tài liệu chính thức đúng thế hệ.
6. Import Spring Cloud BOM cho các artifact Spring Cloud.
7. Với Apache Pulsar support for Spring, đặt binder version hoặc import `pulsar-spring-bom`.
8. Đặt `pulsar.version` theo yêu cầu client của binder.
9. Căn chỉnh `netty.version` nếu dùng dòng client unshaded.
10. Không để binder cũ và binder mới cùng trên classpath.
11. Kiểm tra dependency tree và effective POM.
12. Build ứng dụng, chạy test và kết nối với Pulsar broker tương thích.
13. Triển khai thử, theo dõi startup, topic provisioning, producer/consumer và schema.
14. Ghi lại artifact coordinates và version trong tài liệu vận hành để lần nâng cấp sau có thể tái lập.

## Kết luận

Chọn Pulsar binder tương thích bắt đầu từ Spring Boot và Spring Cloud release train, sau đó mới chọn Spring Cloud Stream và binder artifact. Spring Cloud 2026.0.0 tương thích Spring Boot 4.2.0 và cung cấp Spring Cloud Stream 5.1.0. Dòng Spring Pulsar 2.0.8 là bản cuối do Spring duy trì; dự án Apache Pulsar support for Spring đã phát hành binder mới `org.apache.pulsar:pulsar-spring-cloud-stream-binder` với version 3.0.0-M1.

Khi dùng artifact Apache mới, hãy khai báo version hoặc import `pulsar-spring-bom`, đặt `pulsar.version` và kiểm tra `netty.version`. Migration còn đổi Java package và chuyển client sang artifact unshaded. Không thêm song song binder cũ và mới; hãy kiểm tra dependency tree, build và integration test với Pulsar broker trước khi triển khai.

## Tài liệu tham khảo

- [Spring Cloud — Release Train and Spring Boot Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 Release Notes](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Stream — Pulsar Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar — New Home Announcement](https://spring.io/blog/2026/11/10/spring-pulsar-new-home-asf/)
- [Apache Pulsar Support for Spring — Migration Guide](https://pulsar.apache.org/pulsar-spring/reference/migration.html)
- [Apache Pulsar Support for Spring — Spring Cloud Stream Binder](https://pulsar.apache.org/pulsar-spring/reference/cloud-stream-binder.html)
