# Khai báo spring-boot-starter-data-mongodb-reactive

## 1. Vì sao cần starter dành riêng cho MongoDB reactive?

Một dịch vụ đặt hàng nhận nhiều yêu cầu đọc trạng thái, truy vấn lịch sử và cập nhật đơn cùng lúc. Nếu mỗi truy vấn sử dụng MongoDB Java driver đồng bộ, thread gọi có thể phải chờ I/O. Với hệ thống được thiết kế end-to-end theo Reactive Streams, Spring Data MongoDB cung cấp đường truy cập dữ liệu bất đồng bộ, biểu diễn kết quả bằng `Mono<T>` hoặc `Flux<T>`, sử dụng **MongoDB Reactive Streams driver** thay vì driver truy cập đồng bộ.

Dependency cần khai báo là:

```text
org.springframework.boot:spring-boot-starter-data-mongodb-reactive
```

Starter này là **điểm bắt đầu** cho reactive persistence trên Spring Boot. Nó hỗ trợ cấu hình tự động MongoDB reactive client, mapping và repository/template khi những điều kiện tương ứng được đáp ứng. Nó **không** tự làm mọi đoạn code trong ứng dụng thành non-blocking, không tự tạo REST API và không thay thế việc thiết kế truy vấn/index đúng.

Bài thuộc chương **Truy cập reactive** của module **SPRING_DATA_MONGODB**. Module hướng dẫn dùng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; đồng thời thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài này, bạn sẽ:

1. Thêm đúng `spring-boot-starter-data-mongodb-reactive` cho **Maven**, **Gradle Groovy DSL** và **Gradle Kotlin DSL**.
2. Hiểu quan hệ giữa starter, Spring Data MongoDB, Reactive Streams driver và Reactor.
3. Phân biệt property URI giữa **Spring Boot 3.x** và **Spring Boot 4.x**.
4. Tạo entity, `ReactiveMongoRepository`, `ReactiveMongoOperations` và một service sử dụng `Mono`/`Flux`.
5. Biết khi nào cần `spring-boot-starter-webflux` và vì sao không trộn driver đồng bộ vào đường reactive.
6. Cấu hình kết nối an toàn, kiểm tra dependency tree, auto-configuration và lỗi khởi động.
7. Kiểm thử thật với MongoDB, hiểu phiên bản, transaction, index và giới hạn backpressure.

> Các ví dụ dùng Java 17+ và cú pháp Spring Boot 3.x/4.x. API có thể thay đổi theo phiên bản cụ thể, nhất là property names, test starters và auto-configuration. Chọn **một** dòng phiên bản Spring Boot được dự án quản lý, không trộn các đoạn cấu hình 3.x và 4.x trong cùng ứng dụng.

## 2. Hình dung kiến trúc sau khi khai báo starter

```mermaid
flowchart LR
    A["HTTP Controller WebFlux (tùy chọn)"] --> B["Application Service"]
    B --> C["ReactiveMongoRepository"]
    B --> D["ReactiveMongoOperations"]
    C --> E["Spring Data Mapping + Converter"]
    D --> E
    E --> F["MongoDB Reactive Streams Driver"]
    F --> G["MongoDB Server / Replica Set"]
    G --> F
    F --> H["Reactive Streams Publisher"]
    H --> C
    H --> D
```

Vai trò từng thành phần:

| Thành phần | Công dụng | Có cần tự khai báo không? |
| --- | --- | --- |
| `spring-boot-starter-data-mongodb-reactive` | Tập hợp dependency và kích hoạt đường auto-configuration phù hợp | **Có**, trong build file |
| Spring Data MongoDB | Mapping document, query DSL, repository infrastructure | Thường được starter quản lý |
| MongoDB Reactive Streams driver | I/O MongoDB theo Reactive Streams | Thường được starter kéo vào |
| Project Reactor | `Mono`/`Flux` để biểu diễn và kết hợp publishers | Thường có qua dependency liên quan |
| `ReactiveMongoTemplate` | Reactive operations dạng template | Boot có thể tự cấu hình khi đủ điều kiện |
| `ReactiveMongoRepository` | Repository interface có implementation động | Người học tự định nghĩa interface |
| `spring-boot-starter-webflux` | HTTP reactive endpoints và runtime web | **Chỉ thêm khi cần WebFlux HTTP** |
| MongoDB Server | Lưu document và thực thi query | **Phải có** server/test instance thực |

**Lưu ý:** Spring Boot starter là thư viện dependency, không phải MongoDB server. Thêm dependency và chạy app không tự cài một database production. Trong quá trình phát triển có thể dùng MongoDB local, Docker hoặc môi trường dev được cấp quyền.

## 3. Chọn một Spring Boot version làm nguồn quản lý dependency

### 3.1. Quy tắc sử dụng BOM hoặc parent

Spring Boot quản lý một tập phiên bản tương thích cho Spring Data, MongoDB driver và thư viện liên quan qua dependency management.

Khi project đã dùng Spring Boot parent/BOM hoặc Gradle dependency management tương ứng, **không ghi số phiên bản riêng cho reactive MongoDB starter**:

```text
Spring Boot version đã chọn
       ↓
Spring Boot dependency management
       ↓
spring-boot-starter-data-mongodb-reactive
       ↓
Spring Data MongoDB + reactive driver + dependencies tương thích
```

Nếu tự gắn version mới nhất cho một driver độc lập trong project cũ, có nguy cơ `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi codec do tổ hợp chưa được kiểm thử.

### 3.2. Spring Boot 3.x và 4.x

Cùng artifact starter này được tài liệu chính thức liệt kê cho **Spring Boot 3.x và 4.x**, nhưng có thay đổi cấu hình quan trọng:

| Nội dung | Spring Boot 3.x | Spring Boot 4.x |
| --- | --- | --- |
| Starter chính | `spring-boot-starter-data-mongodb-reactive` | **Cùng artifact** |
| MongoDB connection URI property | `spring.data.mongodb.uri` | `spring.mongodb.uri` |
| Auto index creation | `spring.data.mongodb.auto-index-creation` | Vẫn thuộc nhóm `spring.data.mongodb.*` |
| Reactive repository type | `ReactiveMongoRepository` | `ReactiveMongoRepository` |
| Bean abstraction | `ReactiveMongoOperations` | `ReactiveMongoOperations` |
| Test dependencies | `spring-boot-starter-test`, `reactor-test` và tool test phù hợp | Có thêm starter chuyên biệt `spring-boot-starter-data-mongodb-reactive-test` |

Không dùng bảng này để suy ra **mọi API và mọi package auto-configuration đều giữ nguyên**. Trước khi nâng cấp từ Boot 3 lên Boot 4, đọc migration guide và kiểm tra ứng dụng trên dependency tree thực.

## 4. Khai báo trong Maven

### 4.1. Dự án đã sử dụng Spring Boot parent

Đoạn thiết yếu trong `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
    </dependency>
</dependencies>
```

Khi Spring Boot parent quản lý version, không cần tự thêm:

```xml
<!-- Không cần pin version Mongo reactive starter
     khi version đã được Spring Boot quản lý. -->
```

Một khung Maven tối giản với Boot 3.x (phần version là **ví dụ chọn từ dòng Boot 3**, không phải khuyến nghị dùng mọi môi trường):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-orders</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
        </dependency>

        <!-- Chỉ cần nếu ứng dụng cung cấp HTTP Reactive API. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Quan trọng:** `3.5.0` minh họa một phiên bản thuộc dòng Boot 3; dự án thực tế phải chọn phiên bản được tổ chức hỗ trợ, cập nhật bản vá bảo mật và tương thích với Java/MongoDB server. Không lấy ví dụ này làm phiên bản «mới nhất» vào mọi thời điểm.

### 4.2. Khi dùng Spring Boot 4.x

Giữ nguyên dependency chính:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Nhưng sử dụng **Spring Boot 4 parent/BOM**, kiểm tra Java runtime tương thích và tên properties mới. Nếu sử dụng starter test chuyên biệt theo Boot 4:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive-test</artifactId>
    <scope>test</scope>
</dependency>
```

Không copy nguyên dependency list 3.x rồi cho rằng mọi class trong Boot 4 đã được chia module/test starter giống hệt.

### 4.3. Khi project không kế thừa parent

Sử dụng Spring Boot BOM trong `dependencyManagement` thay vì hardcode version riêng cho starter:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây chỉ là phần dependency management; Maven project vẫn phải có Java compiler/plugin và build configuration thích hợp. Chọn **một** cơ chế quản lý version nhất quán.

## 5. Khai báo với Gradle Groovy DSL

### 5.1. build.gradle

Một Gradle project sử dụng Spring Boot plugin phù hợp:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'

    // Chỉ nếu cần HTTP reactive.
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu Gradle project đã có `plugins` và dependency management, chỉ thêm **dòng implementation cho MongoDB reactive** thay vì copy một file build mới và ghi đè cấu hình của dự án.

### 5.2. Gradle không dùng dependency-management plugin

Một số dự án dùng Gradle native platform/BOM:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
}
```

Chọn một chiến lược plugin/platform được dự án quản lý. Không cần áp đồng thời nhiều BOM cạnh tranh với các version override không rõ nguồn.

## 6. Khai báo với Gradle Kotlin DSL

### 6.1. build.gradle.kts

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(
        "org.springframework.boot:spring-boot-starter-data-mongodb-reactive"
    )
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Đối với dự án Kotlin dùng `kotlin("jvm")`, `kotlin("plugin.spring")` và Kotlin data classes, cần thêm các Kotlin plugins/dependencies tương ứng do dự án quyết định. Ví dụ trên là **Gradle Kotlin DSL cho code Java**, không phải hướng dẫn hoàn chỉnh cho toàn bộ dự án ngôn ngữ Kotlin.

### 6.2. Tránh pin driver version riêng

Không vội thêm:

```groovy
// Tránh ép phiên bản không theo Boot BOM khi chưa có lý do kỹ thuật.
// implementation 'org.mongodb:mongodb-driver-reactivestreams:<version-tu-chon>'
```

Starter đã bao gồm reactive driver theo dependency management. Chỉ override khi có lý do tương thích/bảo mật được kiểm thử, và cần xem toàn bộ dependency graph thay vì sửa một artifact tùy ý.

## 7. Xác minh dependency đã được kéo vào

### 7.1. Maven dependency tree

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-data-mongodb-reactive
./mvnw dependency:tree -Dincludes=org.mongodb
```

Trên Windows, có thể dùng `mvnw.cmd`; trên Linux/macOS, dùng `./mvnw`. Trong bài này, những lệnh trên là **hướng dẫn chạy trong project phù hợp**, không phải lệnh đã được chạy trên workspace hiện tại.

### 7.2. Gradle dependency graph

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-reactivestreams --configuration runtimeClasspath
```

Đọc kết quả để biết:

- Starter reactive thật sự có trên classpath.
- MongoDB Reactive Streams driver có được resolve không.
- Spring Data MongoDB được quản lý bởi dòng Spring Boot nào.
- Có hai phiên bản driver hoặc nhiều BOM override không mong muốn không.
- Có cả driver blocking do một starter khác vô tình mang vào không.

### 7.3. Những lớp cần có về mặt khái niệm

| Lớp/abstraction | Package hoặc artifact liên quan |
| --- | --- |
| `ReactiveMongoRepository` | `org.springframework.data.mongodb.repository` |
| `ReactiveMongoOperations` | `org.springframework.data.mongodb.core` |
| `ReactiveMongoTemplate` | `org.springframework.data.mongodb.core` |
| `Mono` và `Flux` | `reactor.core.publisher` |
| Reactive driver `MongoClient` | `com.mongodb.reactivestreams.client` |
| Blocking driver `MongoClient` | `com.mongodb.client` |

**Hai MongoClient trên không phải cùng một type.** Nếu code tự cấu hình client, import nhầm có thể khiến auto-configuration reactive không nhận bean mong muốn hoặc khiến một phần code chạy đồng bộ.

## 8. Cấu hình kết nối MongoDB cho Spring Boot 3.x

### 8.1. application.yml (Boot 3.x)

```yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI:mongodb://localhost:27017/reactive_orders}"
```

Nếu environment variable `MONGODB_URI` có giá trị, Spring dùng nó; nếu không, URI local trong ví dụ được sử dụng. **Không dùng fallback local trên production nếu việc kết nối nhầm database là rủi ro**. Thường nên yêu cầu environment variable bắt buộc với profile production.

### 8.2. application.properties (Boot 3.x)

```properties
spring.data.mongodb.uri=${MONGODB_URI:mongodb://localhost:27017/reactive_orders}
```

Chọn YAML hoặc properties theo quy ước dự án, không khai báo hai URI khác nhau rồi phụ thuộc thứ tự override.

### 8.3. Test URI có authentication database

Một URI có thể mang thông tin replica set, user, database, authSource và TLS:

```text
mongodb://app-user:<password>@mongo-1:27017,mongo-2:27017/reactive_orders?replicaSet=rs0&authSource=admin&tls=true
```

Chuỗi trên là **mẫu cấu trúc**, không có thông tin đăng nhập thật. Nếu mật khẩu chứa ký tự đặc biệt trong URI, cần percent-encode đúng cách. Dùng secret manager/environment injection, không commit credentials vào Git.

## 9. Cấu hình kết nối MongoDB cho Spring Boot 4.x

Từ Spring Boot 4, nhiều connection properties của MongoDB đã đổi tiền tố từ `spring.data.mongodb.*` sang **`spring.mongodb.*`**. Không copy cấu hình Boot 3 mà không kiểm tra migration guide.

### 9.1. application.yml (Boot 4.x)

```yaml
spring:
  mongodb:
    uri: "${MONGODB_URI:mongodb://localhost:27017/reactive_orders}"
```

### 9.2. application.properties (Boot 4.x)

```properties
spring.mongodb.uri=${MONGODB_URI:mongodb://localhost:27017/reactive_orders}
```

### 9.3. Một số property vẫn ở spring.data.mongodb

Không phải **mọi** property MongoDB đều đã chuyển tiền tố:

```properties
# Ví dụ mapping/index policy vẫn thuộc Spring Data:
spring.data.mongodb.auto-index-creation=false
```

Với production, index creation thường cần một quy trình migration/index management có kiểm soát. Đừng bật auto-index-creation chỉ vì dependency starter được thêm vào; tạo index trên collection lớn có chi phí vận hành.

### 9.4. Kiểm tra đúng Boot version thay vì đoán

Nếu URI property không được áp dụng, ứng dụng có thể cố kết nối default local. Cần:

1. Xác nhận phiên bản Spring Boot thực được resolve.
2. Xem configuration binding/condition report trong môi trường development.
3. Kiểm tra effective URI nhưng **che username/password** trong logs.
4. Đối chiếu tên property với reference documentation của Boot version.
5. Không tự thêm cả hai property để «chắc chắn» khi chưa hiểu precedence.

## 10. Security: credential, TLS, network và timeout

### 10.1. Đừng đưa secret vào repository

Tránh:

```java
// Anti-pattern:
// MongoClients.create("mongodb://admin:password@db-host:27017/prod");
```

Config phải đến từ nguồn có quản lý quyền và rotation. CI/CD không nên in connection URI nguyên vẹn. Tài khoản ứng dụng chỉ cần quyền theo collection và workload của mình.

### 10.2. MongoDB Atlas / mongodb+srv

Một URI dạng:

```text
mongodb+srv://<user>:<password>@cluster.example.mongodb.net/reactive_orders?retryWrites=true&w=majority
```

cần DNS SRV hoạt động, network access được cấp quyền và TLS/CA phù hợp. Với deployment managed, đọc hướng dẫn của provider về certificate và driver compatibility; không tắt TLS verification để vượt lỗi kết nối.

### 10.3. Timeout và retry cần có chủ đích

Connection/server selection timeout khác với write concern timeout và HTTP request timeout. Một lỗi timeout **không mặc định** chứng minh update chưa được áp dụng; với các write có side effect, cần CAS/idempotency và cơ chế reconcile.

Không cấu hình retry vô hạn trên `Flux`/`Mono` ghi dữ liệu chỉ để «tăng tính sẵn sàng».

### 10.4. Reactive TLS và event loop

Theo Spring Boot 4 reference, reactive MongoDB driver cần **Netty** cho đường TLS tương ứng; auto-configuration hỗ trợ khi Netty có trên classpath và factory chưa bị custom sai. Khi tự xây MongoClient/settings, phải kiểm tra SSL/TLS provider cùng driver/version thực tế thay vì sao chép thiết lập của blocking driver.

## 11. Spring Boot có tự tạo những bean nào?

Với starter và cấu hình phù hợp, Spring Boot có thể tạo:

- Reactive MongoDB client/connection infrastructure.
- Reactive database factory.
- MongoDB converter/mapping context.
- `ReactiveMongoTemplate` để inject thông qua `ReactiveMongoOperations`.
- Reactive repository factory và implementation cho các interface được phát hiện.

Các bean này **có điều kiện**: nếu người dùng tự định nghĩa MongoClient/Factory/Template, auto-configuration có thể back off hoặc thay đổi đường tạo. Chính sách và class auto-configuration có thể đổi package giữa Boot 3/4.

### 11.1. Bean nhận bằng constructor injection

```java
package com.example.orders.persistence;

import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Component
public final class ReactiveMongoProbe {
    private final ReactiveMongoOperations mongo;

    public ReactiveMongoProbe(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }
}
```

Nếu Spring không inject được `ReactiveMongoOperations`, trước tiên kiểm tra starter, version, URI, classpath và auto-configuration conditions — không tạo tạm một blocking `MongoTemplate` để «chạy được».

### 11.2. Không cần tự viết @EnableReactiveMongoRepositories trong trường hợp mặc định

Khi repository interfaces nằm dưới package được Boot scan và auto-config conditions thỏa, Boot có thể kích hoạt reactive repositories.

Chỉ bổ sung:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories;

@Configuration
@EnableReactiveMongoRepositories(
    basePackages = "com.example.orders.persistence"
)
class ReactiveRepositoryConfig {}
```

nếu cần xác định phạm vi repository rõ ràng hoặc khi không dùng auto-configuration mặc định. Khi khai báo thủ công, phải kiểm tra không quét trùng/nhầm các blocking repositories.

## 12. Tạo application package và cấu trúc mã nguồn

Một bố cục tham khảo:

```text
src/main/java/com/example/orders/
├── ReactiveOrdersApplication.java
├── persistence/
│   ├── OrderDocument.java
│   ├── ReactiveOrderRepository.java
│   └── OrderMongoGateway.java
├── service/
│   └── OrderQueryService.java
└── api/
    └── OrderController.java
```

Các class ở những mục sau là **các file Java riêng**, không ghép tất cả public class/interface vào một file.

### 12.1. Main application

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveOrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveOrdersApplication.class, args
        );
    }
}
```

Đặt main class tại package gốc `com.example.orders` giúp Boot scan các component/repository trong package con trong cấu trúc minh họa. Trong monorepo/modularized codebase, cấu hình component/repository scanning cần đối chiếu cấu trúc thực tế.

## 13. Khai báo domain document cho reactive MongoDB

### 13.1. OrderDocument.java

```java
package com.example.orders.persistence;

import java.time.Instant;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String status,
    @Field("amount_vnd") long amountVnd,
    Instant createdAt,
    @Version Long version
) {}
```

Entity vẫn dùng mapping annotations của **Spring Data MongoDB**. Không có annotation `@ReactiveDocument` riêng. Reactive nằm ở **driver/operations/publisher** và repository infrastructure, không phải vì document tự «reactive».

### 13.2. Field mapping

| Java property | MongoDB BSON field |
| --- | --- |
| `id` | `_id` |
| `tenantId` | `tenantId` |
| `status` | `status` |
| `amountVnd` | `amount_vnd` |
| `createdAt` | `createdAt` |
| `version` | `version` |

`@MongoId(FieldType.STRING)` giúp sử dụng String ID như fixture; nếu collection dùng BSON ObjectId, thiết kế lại ID mapping và converters. `@Version` có thể hỗ trợ optimistic locking với những write paths Spring Data phù hợp, nhưng **không tự bảo vệ mọi raw update**.

### 13.3. Fixture BSON

```javascript
db.orders.insertMany([
  {
    _id: "ord-101",
    tenantId: "tenant-a",
    status: "PAID",
    amount_vnd: NumberLong("150000"),
    createdAt: ISODate("2026-11-18T08:00:00Z"),
    version: NumberLong("1")
  },
  {
    _id: "ord-102",
    tenantId: "tenant-a",
    status: "PAID",
    amount_vnd: NumberLong("250000"),
    createdAt: ISODate("2026-11-19T08:00:00Z"),
    version: NumberLong("1")
  },
  {
    _id: "ord-103",
    tenantId: "tenant-a",
    status: "NEW",
    amount_vnd: NumberLong("99000"),
    createdAt: ISODate("2026-11-20T08:00:00Z"),
    version: NumberLong("1")
  },
  {
    _id: "ord-201",
    tenantId: "tenant-b",
    status: "PAID",
    amount_vnd: NumberLong("900000"),
    createdAt: ISODate("2026-11-20T09:00:00Z"),
    version: NumberLong("1")
  }
]);
```

Chỉ chạy fixture trong **database thực hành có thể reset**, không chạy nguyên trạng trên production. Có đơn của tenant khác để xác minh repository không vô ý trả dữ liệu chéo tenant.

## 14. Khai báo ReactiveMongoRepository

### 14.1. Interface

```java
package com.example.orders.persistence;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Mono<OrderDocument> findByTenantIdAndId(
        String tenantId, String id
    );

    Flux<OrderDocument> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId, String status
    );

    Mono<Long> countByTenantIdAndStatus(
        String tenantId, String status
    );
}
```

Spring Data tạo implementation dựa trên method names, domain mapping và repository infrastructure. Không cần tự viết class `ReactiveOrderRepositoryImpl` cho những method derived query đơn giản này.

### 14.2. Mono và Flux biểu diễn cardinality

| Method | Return type | Ý nghĩa |
| --- | --- | --- |
| `findByTenantIdAndId` | `Mono<OrderDocument>` | 0 hoặc 1 document |
| `findByTenantIdAndStatus...` | `Flux<OrderDocument>` | 0 đến nhiều document |
| `countByTenantIdAndStatus` | `Mono<Long>` | Một giá trị đếm nếu thành công |
| `save(entity)` | `Mono<OrderDocument>` | Kết quả của write khi subscribed |
| `deleteById(id)` | `Mono<Void>` | Completion/error |

`Mono<T>` có thể hoàn thành **rỗng** thay vì phát giá trị null. `Flux<T>` có thể không phát phần tử nào. Cả hai còn có thể phát **error signal**, không nên biến mọi lỗi kết nối thành empty result.

### 14.3. Đừng nhầm reactive repository và imperative repository

```java
// Imperative:
// interface Orders extends MongoRepository<OrderDocument, String>
// List<OrderDocument> findByStatus(String status);

// Reactive:
// interface Orders extends ReactiveMongoRepository<OrderDocument, String>
// Flux<OrderDocument> findByStatus(String status);
```

Trả về `Flux` từ một imperative repository không tự biến việc gọi blocking driver thành reactive I/O. Ngược lại, reactive repository cần driver Reactive Streams và một reactive MongoDB connection infrastructure đúng.

## 15. Service tạo và kết hợp Publisher thay vì tự subscribe

### 15.1. OrderQueryService.java

```java
package com.example.orders.service;

import com.example.orders.persistence.OrderDocument;
import com.example.orders.persistence.ReactiveOrderRepository;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public final class OrderQueryService {
    private final ReactiveOrderRepository repository;

    public OrderQueryService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<OrderDocument> findOne(
        String authenticatedTenantId, String orderId
    ) {
        return repository.findByTenantIdAndId(
            authenticatedTenantId, orderId
        );
    }

    public Flux<OrderDocument> paidOrders(
        String authenticatedTenantId
    ) {
        return repository
            .findByTenantIdAndStatusOrderByCreatedAtDesc(
                authenticatedTenantId, "PAID"
            );
    }
}
```

Service **trả publisher** cho caller thay vì tự gọi `subscribe()`. Trong WebFlux, framework subscribe khi xử lý response; trong batch job, caller/runner phải chủ động quản lý lifecycle.

### 15.2. Vì sao không subscribe trong service?

```java
// Anti-pattern: tách execution khỏi request lifecycle.
// public void create(OrderDocument order) {
//     repository.save(order).subscribe();
// }
```

Khi gọi `subscribe()` nội bộ:

- Controller có thể trả thành công trước khi DB write hoàn tất.
- Exception có thể không được caller nhận/ánh xạ đúng.
- Cancellation, transaction context, tracing và authentication context có thể bị tách.
- Test khó xác nhận write completion.

Thay bằng:

```java
public Mono<OrderDocument> create(OrderDocument order) {
    return repository.save(order);
}
```

Giả định đoạn method này nằm trong service có field `repository`. Caller nhận `Mono<OrderDocument>` và compose tiếp, không tách side effect bằng `subscribe()`.

## 16. Khi nào cần thêm spring-boot-starter-webflux?

**MongoDB reactive starter** cung cấp một đường truy cập database. Nó **không tự biến ứng dụng thành HTTP server**. Nếu muốn xây REST endpoint trên stack WebFlux, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Hoặc Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Nếu ứng dụng chỉ là background worker/consumer chạy reactive MongoDB, **không nhất thiết** cần WebFlux. `Mono`/`Flux` và reactive driver có thể dùng mà không cần HTTP server.

### 16.1. Một controller WebFlux đơn giản

```java
package com.example.orders.api;

import com.example.orders.persistence.OrderDocument;
import com.example.orders.service.OrderQueryService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public final class OrderController {
    private final OrderQueryService service;

    public OrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<OrderDocument> findById(
        @PathVariable String id
    ) {
        // Trong ứng dụng thật, lấy tenant từ principal/authorization,
        // không dùng giá trị do client tự nhận là mình được sở hữu.
        String authenticatedTenantId = "tenant-a"; // test only

        return service.findOne(authenticatedTenantId, id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found"
                )
            ));
    }

    @GetMapping
    public Flux<OrderDocument> paidOrders() {
        String authenticatedTenantId = "tenant-a"; // test only
        return service.paidOrders(authenticatedTenantId);
    }
}
```

**Cảnh báo:** `"tenant-a"` là giá trị hardcode để minh họa, **không phải cơ chế authentication**. Trong production phải dùng security context và kiểm tra tenant/owner trong các truy vấn. Trả toàn bộ `OrderDocument` ra API cũng không luôn đúng; thường nên map thành response DTO đã whitelist fields.

### 16.2. Không trộn spring-boot-starter-web với WebFlux chỉ để có Mono

`spring-boot-starter-web` phục vụ Spring MVC/Servlet. Khi có cả Web và WebFlux starters, Spring Boot có quy tắc lựa chọn web application type; việc có `Mono` không tự đảm bảo chạy reactive web server.

Nếu mục tiêu là end-to-end WebFlux, cấu hình web stack rõ ràng và tránh phụ thuộc blocking MVC/JDBC/JPA trên đường request hot-path. Nếu ứng dụng MVC nhưng muốn gọi MongoDB reactive, cần thiết kế bridging và execution model cụ thể; không tự cho rằng toàn bộ request xử lý non-blocking chỉ vì repository trả `Mono`.

## 17. ReactiveMongoOperations và ReactiveMongoTemplate

Repository methods tiện cho CRUD và derived queries; khi cần `Criteria`, sort, projection, aggregation hoặc bulk-like operations phức tạp, dùng `ReactiveMongoOperations`.

### 17.1. Ví dụ find với Query/Criteria

```java
package com.example.orders.persistence;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public final class OrderMongoGateway {
    private final ReactiveMongoOperations mongo;

    public OrderMongoGateway(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Flux<OrderDocument> latestPaid(
        String authenticatedTenantId, int pageSize
    ) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || pageSize < 1 || pageSize > 100) {
            return Flux.error(
                new IllegalArgumentException("Invalid query")
            );
        }

        Query query = Query.query(
            Criteria.where("tenantId").is(authenticatedTenantId)
                .and("status").is("PAID")
        )
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(pageSize);

        return mongo.find(query, OrderDocument.class);
    }
}
```

`ReactiveMongoOperations` hỗ trợ mapping từ Java property `id` sang BSON `_id` trong context entity phù hợp. Nhưng trong mongosh/driver dùng tên BSON vật lý. Với `@Field("amount_vnd")`, nhớ kiểm tra aliases khi viết raw JSON pipelines.

### 17.2. Update cần kết quả acknowledgment

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<Boolean> markShipped(
    String tenantId, String id, long expectedVersion
) {
    Query query = Query.query(
        Criteria.where("id").is(id)
            .and("tenantId").is(tenantId)
            .and("status").is("READY_TO_SHIP")
            .and("version").is(expectedVersion)
    );
    Update update = new Update()
        .set("status", "SHIPPED")
        .inc("version", 1);

    return mongo.updateFirst(
        query, update, OrderDocument.class
    ).map(result -> {
        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Write has no reliable acknowledgment"
            );
        }
        return result.getMatchedCount() == 1;
    });
}
```

Đặt method này trong một component đã có `ReactiveMongoOperations mongo` và imports `Criteria`, `Query`. Với `@Version`, cần integration test để xác nhận version tăng **đúng một lần**, không dựa vào suy đoán về cơ chế version augmentation của phiên bản Spring Data hiện tại.

## 18. Mono/Flux: hiểu đúng cold publisher và subscription

### 18.1. Publisher biểu diễn một công việc, không phải kết quả đã có

```java
Mono<OrderDocument> pending =
    repository.findByTenantIdAndId(
        "tenant-a", "ord-101"
    );

// Khi mới khai báo pending, chưa có gì khẳng định truy vấn đã chạy.
```

Các repository publisher thường là **cold**: công việc I/O được kích hoạt khi có subscriber. Mỗi subscription độc lập có thể kích hoạt một truy vấn mới:

```java
Mono<OrderDocument> pending =
    repository.findByTenantIdAndId("tenant-a", "ord-101");

// Hai subscription có thể thực hiện hai lần I/O:
pending.subscribe();
pending.subscribe();
```

Ví dụ này chỉ giải thích behavior; **không** khuyến khích gọi `subscribe()` trực tiếp từ service.

### 18.2. Dùng operators thay vì lấy giá trị đồng bộ

```java
Mono<String> statusText = repository
    .findByTenantIdAndId("tenant-a", "ord-101")
    .map(order -> "status=" + order.status())
    .defaultIfEmpty("not found");
```

`map` xử lý đồng bộ ngắn trên một phần tử; `flatMap` dùng khi hàm trả một publisher khác:

```java
Mono<Long> countAfterLookup = repository
    .findByTenantIdAndId("tenant-a", "ord-101")
    .flatMap(order ->
        repository.countByTenantIdAndStatus(
            order.tenantId(), order.status()
        )
    );
```

Không dùng `map(order -> repository.save(order))` nếu mục tiêu là đợi save chạy: kết quả sẽ là `Mono<Mono<OrderDocument>>` theo nghĩa logic, không phải pipeline chờ side effect. Dùng `flatMap`.

### 18.3. Empty khác error

```java
Mono<OrderDocument> result = repository
    .findByTenantIdAndId("tenant-a", "missing-id");
```

Không tìm thấy có thể tạo **completion không có giá trị**. Lỗi mạng, authorization hoặc decode tạo **error signal**. Không dùng `onErrorResume(e -> Mono.empty())` cho mọi lỗi, vì nó có thể biến sự cố database thành «không tìm thấy».

### 18.4. Không dùng block() trong reactive request thread

```java
// Không làm trong controller/service reactive:
// OrderDocument order = repository.findById(id).block();
```

`block()` chờ kết quả và có thể chặn event-loop, giảm khả năng phục vụ concurrent I/O. Nếu integration với một thư viện blocking là bắt buộc, cần cô lập nó theo thread scheduler và giới hạn concurrency có chủ đích; tốt nhất ưu tiên API non-blocking.

## 19. Backpressure, phân trang và kiểm soát bộ nhớ

### 19.1. Reactive không cho phép tải vô hạn

`Flux<OrderDocument>` không có nghĩa MongoDB query miễn phí. Driver vẫn phải đọc batches, decode BSON, thực thi sort/filter và giữ trạng thái cursor.

Đoạn sau nguy hiểm với collection lớn:

```java
// Đọc toàn collection và gom vào một list trong RAM:
// Mono<List<OrderDocument>> all = repository.findAll().collectList();
```

Nếu danh sách hàng triệu document, `collectList()` có thể làm heap tăng mạnh. Khi caller cần một trang, áp **giới hạn tại MongoDB** trước khi stream, ví dụ `Query.limit(50)` hoặc repository query có `Pageable` ở API được hỗ trợ.

### 19.2. Backpressure giúp điều phối demand, không thay index

Trong Reactive Streams, downstream có thể yêu cầu số lượng phần tử theo demand. Driver/batching tương tác với request này. Nhưng:

- Một `$sort` không có index vẫn có thể là blocking stage **bên trong MongoDB server**.
- `$group` trên tập lớn vẫn tiêu tốn CPU/RAM server.
- Một `flatMap` với concurrency cao có thể phát nhiều queries đồng thời.
- Backpressure **không** sửa một filter tenant sai hoặc schema thiếu index.

### 19.3. Giới hạn concurrency

Ví dụ cần đọc trạng thái cho một số ID:

```java
Flux<OrderDocument> loaded = Flux
    .fromIterable(orderIds)
    .flatMap(id ->
        repository.findByTenantIdAndId(
            authenticatedTenantId, id
        ),
        8
    );
```

`orderIds` và `authenticatedTenantId` là input đã validate từ caller. `8` là **giới hạn concurrency ví dụ**, không phải mức tối ưu chung. Nếu cần giữ thứ tự đầu vào, cân nhắc `concatMap` hoặc một API/batch query thích hợp.

### 19.4. Offset sâu và keyset

Với một danh sách cuộn dài, offset pagination có thể tốn chi phí khi `skip` lớn. Có thể cân nhắc keyset theo `createdAt` và `_id` với sort ổn định và index compound. Reactive repository không tự biến `skip(100000)` thành keyset; thiết kế query phải đáp ứng semantics thật.

## 20. Index và hiệu năng của reactive MongoDB

### 20.1. Index cho query mẫu

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "ix_orders_tenant_status_recent" }
);
```

Index này là ứng viên cho query:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Kiểm tra plan thật, `IXSCAN`/`COLLSCAN`, docs/keys examined và blocking sort. Việc đổi từ blocking driver sang reactive driver **không** khiến server tự chọn index tốt hơn hoặc giảm chi phí aggregation.

### 20.2. Tạo index thuộc lifecycle quản trị

Không chạy `createIndex` trên mỗi HTTP request. Có thể dùng Spring Data `IndexOperations`/reactive index API tùy version, hoặc migration tool theo source of truth. Kiểm tra `spring.data.mongodb.auto-index-creation` theo chính sách dự án: production thường cần phê duyệt tác động tới disk/CPU và thời gian build.

### 20.3. Quan sát toàn đường đi

| Nơi đo | Metric |
| --- | --- |
| HTTP/WebFlux | p50/p95/p99, error rate, active requests |
| Reactor chain | Subscription, cancellation, timeout, retries, queueing |
| MongoDB driver | Connection pool/command latency, timeouts |
| MongoDB server | Query plan, docs examined, CPU/I/O, replication lag |
| Heap/GC | Allocation và memory pressure khi collect/buffer |

Không coi «thread ít hơn» đồng nghĩa query nhanh hơn. Reactive giúp sử dụng thread hiệu quả khi phải chờ I/O nhưng không bảo đảm throughput cao nếu database là nút thắt.

## 21. Reactive write, @Version và transaction

### 21.1. Reactive repository save

```java
Mono<OrderDocument> saved =
    repository.save(new OrderDocument(
        "ord-301",
        "tenant-a",
        "NEW",
        150000L,
        java.time.Instant.now(),
        null
    ));
```

Đây là một publisher. Ghi thật khi được subscribe, và returned entity có thể mang ID/version do persistence mapping quản lý. Không giả định entity wrapper version khởi tạo luôn bằng một giá trị cố định; kiểm thử đúng phiên bản Spring Data.

### 21.2. Acknowledged write cần để phát hiện xung đột

Khi dùng `@Version`, Spring Data có thể phát hiện stale write trên các đường save hỗ trợ, nhưng cần write concern đủ để **nhận acknowledgment**. Nếu write result không được acknowledged, nhiều lỗi không thể được quan sát đáng tin. Với command quan trọng, cấu hình write concern theo SLA/durability và test conflict.

### 21.3. Transaction reactive cần transaction manager reactive

Một ví dụ cấu hình:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory
    ) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
```

Multi-document transactions cần MongoDB topology hỗ trợ session/transaction (thường replica set hoặc sharded cluster với điều kiện phù hợp). Không chạy transaction demo trên standalone rồi cho rằng session/commit semantics giống production.

### 21.4. TransactionalOperator

```java
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public final class AtomicWorkflow {
    private final ReactiveOrderRepository orders;
    private final TransactionalOperator tx;

    public AtomicWorkflow(
        ReactiveOrderRepository orders,
        ReactiveTransactionManager txManager
    ) {
        this.orders = orders;
        this.tx = TransactionalOperator.create(txManager);
    }

    public Mono<OrderDocument> saveWithinTransaction(
        OrderDocument order
    ) {
        return orders.save(order).as(tx::transactional);
    }
}
```

Chỉ một `save` đơn document thường **không cần** mở transaction. Ví dụ dùng `TransactionalOperator` để minh họa operator, chứ không phải khuyến nghị thêm transaction cho mọi write. Trong workflow thực có nhiều thao tác, phải bảo đảm toàn bộ publishers nằm **bên trong transaction chain**, không gọi `subscribe()` tách rời.

## 22. Reactive starter và imperative starter có thể cùng tồn tại?

Có thể có ứng dụng vừa sử dụng:

```text
spring-boot-starter-data-mongodb
spring-boot-starter-data-mongodb-reactive
```

Tuy nhiên, đây là **hai đường driver và connection infrastructure khác nhau**, không phải cùng một connection pool với hai API bọc ngoài. Một bên dùng `com.mongodb.client.MongoClient`, bên kia dùng `com.mongodb.reactivestreams.client.MongoClient`.

### 22.1. Rủi ro thực tế

- Repository scanning dễ mơ hồ nếu cả imperative/reactive interfaces cùng package.
- Ứng dụng có hai client/pool và metrics riêng, tốn thêm tài nguyên.
- Bean injection nhầm `MongoOperations` với `ReactiveMongoOperations`.
- Một service reactive gọi template blocking và làm nghẽn event loop.
- Cấu hình connection/auth/TLS có thể không được đồng bộ như dự tính.

### 22.2. Khi nào trộn có thể hợp lý?

Trong giai đoạn migration, một batch blocking legacy và một API reactive mới có thể cùng tồn tại nếu:

1. Cả hai cần thiết, đã phân định ownership rõ.
2. Package/repository scanning không chồng lấn.
3. Có cấu hình/metrics riêng cho hai driver.
4. Không gọi blocking database API trong reactive request path.
5. Có kế hoạch dọn dẹp dependency sau migration.

Nếu chỉ cần reactive access, ưu tiên **một reactive starter** và tránh kéo thêm imperative starter do thói quen.

### 22.3. @EnableMongoRepositories khác @EnableReactiveMongoRepositories

`@EnableMongoRepositories` dùng cho imperative repositories; `@EnableReactiveMongoRepositories` dùng cho reactive repositories. Dùng đúng annotation khi cần tự điều khiển scanning, và kiểm tra Boot auto-configuration trước khi thêm cấu hình thủ công.

## 23. Kiểm thử Reactor bằng StepVerifier

### 23.1. Thêm reactor-test

Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle:

```groovy
testImplementation 'io.projectreactor:reactor-test'
```

`StepVerifier` giúp subscribe vào publisher và xác nhận signals, completion và error.

### 23.2. Test một Mono không cần MongoDB

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class MonoContractTest {
    @Test
    void monoEmitsOneValueThenCompletes() {
        Mono<Integer> answer = Mono.just(21).map(x -> x * 2);

        StepVerifier.create(answer)
            .expectNext(42)
            .verifyComplete();
    }

    @Test
    void emptyMonoDoesNotEmitNull() {
        StepVerifier.create(Mono.<String>empty())
            .verifyComplete();
    }
}
```

Test trên chỉ xác minh **Reactor operator contract**, không chứng minh MongoDB reactive connection đã hoạt động.

### 23.3. Test error semantics

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> failure = Mono.error(
    new IllegalStateException("Simulated failure")
);

StepVerifier.create(failure)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && ex.getMessage().contains("Simulated")
    )
    .verify();
```

Không chuyển mọi error thành empty để test «pass»; error cần được giữ hoặc mapping phù hợp, đặc biệt khi thiếu quyền truy cập hoặc database unavailable.

## 24. Integration test với MongoDB thật

### 24.1. Vì sao mock chưa đủ?

Mock `ReactiveOrderRepository` có thể kiểm tra service mapping/operator, nhưng không chứng minh:

- Connection URI/TLS/auth đúng.
- Spring Boot tạo `ReactiveMongoTemplate` và repository proxy.
- `@MongoId`, `@Field`, `@Version` mapping đúng BSON.
- Derived query theo tenant/status thực sự được MongoDB thực thi.
- Sort/index/count/transaction hoạt động đúng.

Cần integration test sử dụng MongoDB thật hoặc Testcontainers MongoDB với version/topology đại diện.

### 24.2. Khung Testcontainers

Một lựa chọn test trên Java/Boot 3.x (dependencies Testcontainers version do Boot BOM/test strategy quản lý):

```java
package com.example.orders;

import com.example.orders.persistence.OrderDocument;
import com.example.orders.persistence.ReactiveOrderRepository;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import reactor.test.StepVerifier;

@Testcontainers
@SpringBootTest
class ReactiveMongoIntegrationTest {

    @Container
    static MongoDBContainer mongodb =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        // Spring Boot 3.x:
        registry.add(
            "spring.data.mongodb.uri",
            mongodb::getReplicaSetUrl
        );
        // Với Spring Boot 4.x: dùng "spring.mongodb.uri".
    }

    @Autowired ReactiveOrderRepository repository;

    @Test
    void savesAndFindsByTenant() {
        OrderDocument sample = new OrderDocument(
            "test-reactive-001", "tenant-a", "PAID",
            120000L, Instant.parse("2026-11-20T00:00:00Z"),
            null
        );

        StepVerifier.create(
            repository.save(sample)
                .flatMap(saved ->
                    repository.findByTenantIdAndId(
                        "tenant-a", saved.id()
                    )
                )
        )
        .expectNextMatches(found ->
            found.id().equals("test-reactive-001")
                && found.amountVnd() == 120000L
        )
        .verifyComplete();
    }
}
```

Đây là **khung ví dụ**, chưa chứa đủ build/test dependencies và cleanup. Phải thêm Testcontainers MongoDB/JUnit integration phù hợp với phiên bản được quản lý. Nếu class test chạy nhiều lần trên cùng collection và dùng ID cố định, cần xóa dữ liệu test hoặc dùng ID duy nhất. Với Boot 4, kiểm tra starter test chuyên biệt, JUnit/Testcontainers APIs và property đổi tên.

### 24.3. Dependencies Testcontainers cho Maven

```xml
<!-- Ví dụ cho dòng Testcontainers có các artifact này;
     để Boot BOM quản lý version khi phù hợp. -->
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mongodb</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Testcontainers 2.x có thay đổi module/artifact trong một số tích hợp; nếu dùng phiên bản mới hơn, đối chiếu nhóm dependency và class API của phiên bản được quản lý thay vì sao chép nguyên mẫu trên.

### 24.4. Kiểm thử tenant isolation

Test gồm document tenant-a và tenant-b có cùng status; truy vấn:

```java
Flux<OrderDocument> paidA =
    repository.findByTenantIdAndStatusOrderByCreatedAtDesc(
        "tenant-a", "PAID"
    );

StepVerifier.create(paidA)
    .thenConsumeWhile(order ->
        order.tenantId().equals("tenant-a")
    )
    .verifyComplete();
```

Đoạn test này kiểm tra không có kết quả khác tenant trong những phần tử được phát; tốt hơn cần seed expected IDs và assert **đúng số lượng/IDs** để phát hiện trường hợp repository trả rỗng sai. Trong thực tế, sắp xếp nên thêm tie-breaker khi timestamps có thể trùng.

### 24.5. Reactive transaction test

Nếu cần kiểm thử `ReactiveMongoTransactionManager`, sử dụng MongoDB topology hỗ trợ transactions và đảm bảo test dùng reactive transaction operator. Một test trên standalone hoặc mock không chứng minh rollback/commit nhiều document.

## 25. Boot startup: kiểm tra ứng dụng thực sự đang dùng reactive

### 25.1. Starter tồn tại không có nghĩa kết nối thành công

Spring Boot auto-config có thể tạo client/template khi startup nhưng không nhất thiết thực hiện một query đầy đủ ngay lúc đó. Một ứng dụng khởi động thành công không chứng minh auth, DNS SRV, TLS, connection pool hay quyền collection đều hợp lệ.

Để xác minh:

1. Kiểm tra dependency graph đúng starter/driver.
2. Xác nhận environment properties được binding đúng.
3. Khởi động với một MongoDB dev/test đang phục vụ.
4. Inject `ReactiveMongoOperations` hoặc repository.
5. Chạy một smoke query **có subscription và timeout**.
6. Kiểm tra kết quả/exception, không coi `Mono<?>` vừa được tạo là thành công.

### 25.2. Smoke query bằng ReactiveMongoOperations

```java
package com.example.orders.diagnostics;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class MongoSmokeProbe {
    private final ReactiveMongoOperations mongo;

    public MongoSmokeProbe(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<Boolean> canReadOrders() {
        // Bỏ qua số lượng thật; chỉ dùng cho ví dụ.
        return mongo.collectionExists("orders")
            .timeout(java.time.Duration.ofSeconds(3));
    }
}
```

`collectionExists("orders")` là thao tác metadata và có thể cần quyền phù hợp; `false` cũng có thể chỉ do collection chưa tạo, không phải lỗi kết nối. Trong ứng dụng thực, dùng readiness/health indicator phù hợp và một smoke query theo quyền của account.

### 25.3. Health check và metrics

Thêm Spring Boot Actuator nếu cần health/metrics:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Điều kiện kích hoạt MongoDB health contributor và tên management properties có thể khác giữa Boot 3/4. Không mở actuator endpoints nhạy cảm ra Internet; cấu hình readiness/liveness và authentication theo policy.

### 25.4. Debug auto-configuration

Trong môi trường dev có thể bật condition evaluation report (ví dụ chạy app với `--debug`). Tìm vì sao bean reactive MongoDB auto-config có hoặc không được tạo. Không xuất toàn bộ environment secrets/connection URI nguyên vẹn vào logs hoặc chia sẻ công khai.

## 26. Những lỗi thường gặp khi thêm starter

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `ReactiveMongoRepository` không compile | Starter chưa được resolve hoặc dependency conflict | Xem Maven/Gradle dependency graph |
| Bean `ReactiveMongoOperations` không tồn tại | Auto-configuration condition không thỏa, custom config sai | Condition report, reactive driver imports |
| Boot 4 tìm MongoDB ở localhost | Vẫn dùng `spring.data.mongodb.uri` kiểu Boot 3 | Dùng `spring.mongodb.uri` |
| Boot 3 không nhận URI | Dùng `spring.mongodb.uri` của Boot 4 | Dùng `spring.data.mongodb.uri` |
| `ClassNotFoundException`/`NoSuchMethodError` | Override driver/Spring Data lệch BOM | Bỏ pin thủ công, đồng bộ version |
| `MongoClient` import sai | Dùng `com.mongodb.client` thay cho reactive driver | Kiểm tra `com.mongodb.reactivestreams.client` |
| Repository bean không được tìm thấy | Sai package scanning, interface chưa được quét | Đặt dưới package root, kiểm tra enable repositories |
| Hai repository factories xung đột | Trộn blocking và reactive starters không tách scope | Rà soát dependency/scanning |
| Controller trả `Mono` nhưng block | Gọi `.block()` hoặc JDBC/HTTP blocking trong chain | Dùng non-blocking API, cô lập blocking nếu cần |
| API trả trước khi save xong | `subscribe()` bên trong service rồi trả `void` | Trả `Mono`/compose tới controller |
| Test không ghi gì | Tạo publisher nhưng không subscribe | Dùng `StepVerifier` |
| `Mono.empty()` bị hiểu thành DB error | Không phân biệt completion rỗng với error | `switchIfEmpty` cho not-found, error mapping riêng |
| Query trả chéo tenant | Quên tenant filter | Authorization context và tenant-scoped query |
| `collectList()` gây OOM | Load collection lớn vào heap | Giới hạn query, stream, paginate |
| Flux xử lý chậm dù có reactive | Index thiếu, blocking sort hoặc DB nghẽn | Explain/index, đo DB metrics |
| Không có HTTP endpoint | Chỉ thêm MongoDB starter mà không có WebFlux starter | Thêm WebFlux nếu cần HTTP |
| TLS handshake thất bại | Trust/CA/hostname/proxy/Netty config | Kiểm tra TLS và provider/driver |
| Authentication failed | authSource/username/password sai | Kiểm tra URI/secret injection và quyền |
| Timeout rồi retry ghi hai lần | Không có idempotency | CAS/operation ID và reconcile |
| Transaction not supported | Standalone/topology hoặc transaction manager sai | Replica set và reactive transaction setup |
| `@Version` không báo conflict | Write concern unacknowledged hoặc dùng raw update không filter | Acknowledged + test đường ghi |
| Lỗi bộ nhớ khi dùng `flatMap` | Fan-out concurrency quá lớn | Limit concurrency và batch |

### 26.1. Quy trình chẩn đoán từng bước

```text
1. Xác nhận Boot version và starter reactive.
                         ↓
2. Kiểm tra dependency tree, không ép driver version lệch BOM.
                         ↓
3. Kiểm tra URI property Boot 3 hay Boot 4 đúng.
                         ↓
4. Kiểm tra DNS/auth/TLS/network tới MongoDB.
                         ↓
5. Kiểm tra ReactiveMongoOperations + repository bean.
                         ↓
6. Dùng StepVerifier để thực thi một query thật.
                         ↓
7. Kiểm tra tenant filter, BSON mapping, result/error.
                         ↓
8. Đọc explain/index và metrics latency/connection pool.
                         ↓
9. Kiểm tra không block/subscribe tách lifecycle.
```

## 27. Bài thực hành có lời giải

### Bài 1 — Dependency Maven tối thiểu

**Đề bài:** Thêm Spring Data MongoDB reactive vào project Maven dùng Spring Boot parent.

**Lời giải:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Không cần điền version riêng khi parent/BOM quản lý dependency.

### Bài 2 — Gradle Groovy và Kotlin DSL

**Đề bài:** Viết dòng dependency trong hai DSL.

**Lời giải:**

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
```

```kotlin
implementation("org.springframework.boot:spring-boot-starter-data-mongodb-reactive")
```

### Bài 3 — Chọn property đúng cho Boot 3

**Đề bài:** Spring Boot 3.4 dùng MongoDB dev ở port 27017, database `training`.

**Lời giải:**

```properties
spring.data.mongodb.uri=mongodb://localhost:27017/training
```

Không dùng property mới `spring.mongodb.uri` của Boot 4 cho Boot 3.x.

### Bài 4 — Chọn property đúng cho Boot 4

**Đề bài:** Nâng ứng dụng lên Spring Boot 4 nhưng giữ `spring.data.mongodb.uri`. Cần sửa gì?

**Lời giải:**

```properties
spring.mongodb.uri=mongodb://localhost:27017/training
```

Kiểm tra thêm các property MongoDB được di chuyển theo migration guide, trong khi một số Spring Data mapping/index options vẫn thuộc `spring.data.mongodb.*`.

### Bài 5 — Có phải thêm WebFlux không?

**Đề bài:** Một batch job chỉ đọc MongoDB và xử lý Flux, không có HTTP endpoint. Có cần `spring-boot-starter-webflux`?

**Lời giải:** Không nhất thiết. MongoDB reactive starter đủ cho reactive data access khi auto-config hoạt động. Chỉ thêm WebFlux khi cần HTTP reactive endpoints hoặc những thành phần web-specific.

### Bài 6 — Reactive repository hay blocking repository?

**Đề bài:** Service muốn method `findByTenantIdAndId` trả `Mono<OrderDocument>` và không chặn thread.

**Lời giải:**

```java
public interface Orders
    extends ReactiveMongoRepository<OrderDocument, String> {

    Mono<OrderDocument> findByTenantIdAndId(
        String tenantId, String id
    );
}
```

Phải dùng reactive starter/driver. Chỉ đổi return type của `MongoRepository` imperative là không đủ.

### Bài 7 — Vì sao service không gọi subscribe?

**Đề bài:** Developer viết `repository.save(order).subscribe(); return Mono.empty();`. Điều gì sai?

**Lời giải:** DB write được chạy tách khỏi request completion/error/cancellation và có thể trả thành công trước khi ghi xong. Trả thẳng `repository.save(order)` hoặc compose bằng operators để caller/framework quản lý subscription.

### Bài 8 — StepVerifier cho query rỗng

**Đề bài:** Không tìm được ID theo tenant. Đâu là tín hiệu đúng?

**Lời giải:** `Mono.empty()`/completion rỗng trong trường hợp không có document, không phải `Mono.just(null)`. Test:

```java
StepVerifier.create(Mono.<OrderDocument>empty())
    .verifyComplete();
```

Lỗi network/authorization nên là error signal, không chuyển thành not-found.

### Bài 9 — Query chậm dù dùng Flux

**Đề bài:** Lấy 50 đơn mới nhất bằng reactive repository vẫn chậm. Chuyển sang `Flux` đã tối ưu database chưa?

**Lời giải:** Chưa. Kiểm tra filter/index và sort: index `{tenantId:1,status:1,createdAt:-1,_id:-1}` là ứng viên. Dùng `explain("executionStats")`, tránh blocking sort/scan, giới hạn page size và so sánh latency.

### Bài 10 — Không có ReactiveMongoOperations bean

**Đề bài:** Project có `spring-boot-starter-data-mongodb` nhưng không có reactive starter; injection `ReactiveMongoOperations` thất bại.

**Lời giải:** Thêm `spring-boot-starter-data-mongodb-reactive`, xác minh reactive driver, auto-configuration và cấu hình URI/connection. Không thay thế bằng injection `MongoTemplate` trong service reactive.

### Bài 11 — Auto index creation trong production

**Đề bài:** Developer bật `spring.data.mongodb.auto-index-creation=true` để tạo mọi index lúc startup. Có nên làm mặc định?

**Lời giải:** Không. Cần quy trình quản lý index phù hợp với dữ liệu lớn, thời gian build, quyền và rollout. Trong production thường quản lý qua migration/DBA policy; xác nhận annotations không tạo lại index đã chủ động loại bỏ.

### Bài 12 — Xây một test tích hợp đầy đủ

**Đề bài:** Làm sao chứng minh starter reactive thực sự hoạt động, không chỉ compile?

**Lời giải:** Dựng MongoDB test container; cấu hình URI theo Boot version; boot Spring context có `ReactiveOrderRepository`; dùng `StepVerifier` subscribe vào `save(...).flatMap(findByTenantIdAndId(...))`; assert ID/tenant/field mapping; làm cleanup; test error path/transaction/optimistic lock nếu module dùng. Một `Mono` chưa subscribe hoặc một mock repository không đủ chứng minh kết nối thật.

## 28. Checklist hoàn thành trước khi triển khai

| Hạng mục | Tiêu chí |
| --- | --- |
| Starter artifact | Đúng `spring-boot-starter-data-mongodb-reactive` |
| Dependency management | Dùng Boot parent/BOM, không pin Mongo driver tùy ý |
| Build DSL | Maven/Groovy/Kotlin có cú pháp hợp lệ |
| Boot version | Đã xác nhận 3.x hay 4.x |
| MongoDB URI | Boot 3 `spring.data.mongodb.uri`; Boot 4 `spring.mongodb.uri` |
| Secrets | URI/credential ngoài source, logs được redaction |
| TLS/CA | Được kiểm tra theo driver và deployment |
| Reactive driver | Có `com.mongodb.reactivestreams.client` |
| Repository | `ReactiveMongoRepository` trong package được scan |
| Template | Inject `ReactiveMongoOperations`, không nhầm blocking template |
| HTTP stack | Chỉ thêm WebFlux khi cần, không trộn vô ý với MVC |
| Mapping | `@Document`, ID, `@Field`, converter/BSON type đúng |
| Tenant isolation | Tenant lấy từ auth và có trong filter |
| Execution | Service trả Publisher, không fire-and-forget subscribe |
| Blocking | Không `block()` trên event loop |
| Backpressure | Không `collectList()` toàn collection không giới hạn |
| Concurrency | `flatMap` fan-out có giới hạn phù hợp |
| Query performance | Index, explain, sort, pagination được đánh giá |
| Index lifecycle | Auto-index/migration có policy rõ |
| Write concern/version | Acknowledgment và CAS được kiểm thử |
| Transaction | Reactive transaction manager/topology phù hợp |
| Retry | Không retry side effect vô điều kiện |
| Unit test | `reactor-test` và StepVerifier |
| Integration test | MongoDB thật/Testcontainers, test URI theo Boot version |
| Operations | Health/metrics/readiness/latency có quan sát |
| QA | Chạy vòng kiểm tra chuyên môn theo quy trình sau bước viết |

## 29. Tóm tắt và tài liệu tham khảo

### 29.1. Tóm tắt

1. Khai báo **`org.springframework.boot:spring-boot-starter-data-mongodb-reactive`** trong Maven/Gradle là bước cốt lõi để có reactive MongoDB integration qua Spring Boot.
2. Starter **không tự tạo web server**; thêm `spring-boot-starter-webflux` khi cần HTTP reactive endpoints.
3. **Boot 3.x** dùng `spring.data.mongodb.uri`; **Boot 4.x** dùng `spring.mongodb.uri`. Một số Spring Data properties như auto-index-creation vẫn giữ tiền tố cũ.
4. Reactive driver và blocking driver là **hai kiểu client khác nhau**; `ReactiveMongoRepository`/`ReactiveMongoOperations` dùng đường reactive.
5. `Mono` và `Flux` biểu diễn publishers, không đồng nghĩa I/O đã chạy; **phải có subscription**, thường do framework/caller quản lý.
6. **Không `block()` hoặc `subscribe()` tách lifecycle trong reactive service**, không tải không giới hạn bằng `collectList()` và không retry writes bừa bãi.
7. Dependency đúng **chưa đủ**: cần BSON mapping, tenant filter, index, write concern, transaction policy, monitoring và integration test với MongoDB thực.

### 29.2. Tài liệu chính thức để đối chiếu phiên bản

- Spring Boot 3.x — [NoSQL / MongoDB](https://docs.spring.io/spring-boot/3.4/reference/data/nosql.html).
- Spring Boot 4.x — [NoSQL / MongoDB](https://docs.spring.io/spring-boot/4.0/reference/data/nosql.html).
- Spring Boot 4.x — [Build systems và starter list](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html).
- Spring Boot — [Migration guide 4.0](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
- Spring Data MongoDB — [Reactive MongoDB support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/reactive-mongodb.html).
- Spring Data MongoDB — [Reactive repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).
- Spring Data MongoDB — [Sessions and transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).
- Project Reactor — [Reference guide](https://projectreactor.io/docs/core/release/reference/).
- Testcontainers — [MongoDB module](https://java.testcontainers.org/modules/databases/mongodb/).

**Kết luận:** Khai báo starter reactive là một thay đổi nhỏ trong build file nhưng mở ra một đường persistence có execution model khác. Để triển khai Spring Data MongoDB reactive hiệu quả, cần quản lý đúng phiên bản Spring Boot, dùng đúng Reactive Streams driver, viết service theo publisher lifecycle và kiểm tra toàn bộ hệ thống qua test/metrics trước khi kết luận rằng ứng dụng đã thực sự non-blocking.

