# Thay đổi dependency, starter và tên thuộc tính cấu hình giữa các dòng Boot

Khi nâng cấp Spring Boot, cấu hình Spring Session có thể thay đổi ở ba lớp riêng: dependency dùng để đưa repository vào classpath, starter giúp Spring Boot tự cấu hình repository, và tên property dùng để kết nối Redis hoặc tùy chỉnh session. Một ứng dụng nâng từ Boot 2.7 lên 3.x rồi 4.x có thể vẫn biên dịch được nhưng không còn kết nối đúng Redis nếu giữ nguyên prefix cũ; hoặc có thể khởi động với repository khác dự kiến nếu nhiều module session cùng có trên classpath.

Spring Session quản lý `HttpSession`/`WebSession` qua repository như Redis hoặc JDBC. Spring Boot cung cấp dependency management và auto-configuration để đăng ký repository, filter hoặc WebSession integration. Vì thế, khi nâng cấp phải đồng bộ phiên bản Boot, Spring Framework, Spring Session, Spring Data và các starter liên quan; đồng thời xác minh cấu hình thực tế sau khi ứng dụng khởi động.

## 1. Bốn lớp cần phân biệt khi nâng cấp

### 1.1. Spring Boot version

Spring Boot BOM quản lý một tập hợp phiên bản tương thích của Spring Framework, Spring Data, Spring Security, Spring Session và thư viện hạ tầng. Nâng Boot thường kéo theo nhiều phiên bản transitive thay đổi, kể cả khi `pom.xml` hoặc `build.gradle` không khai báo trực tiếp chúng.

Không nên nâng riêng `spring-session-data-redis` lên một major mới trong khi giữ Spring Boot cũ chỉ để sửa một lỗi. Nếu cần override phiên bản, phải xác minh ma trận tương thích và lý do cụ thể.

### 1.2. Spring Session module

Các module phổ biến gồm:

| Module | Vai trò |
|---|---|
| `spring-session-core` | API và abstraction session cốt lõi |
| `spring-session-data-redis` | Repository session dựa trên Redis, gồm hỗ trợ Servlet và reactive theo cấu hình |
| `spring-session-jdbc` | Repository session dựa trên JDBC cho ứng dụng Servlet |
| `spring-session-hazelcast` | Repository session dựa trên Hazelcast |

Tên artifact module `spring-session-data-redis` vẫn được dùng trong cấu hình dependency trực tiếp. Spring Boot 4 bổ sung starter ở namespace `org.springframework.boot` để gom module và auto-configuration cho từng store.

### 1.3. Spring Boot starter

Starter là dependency tổng hợp do Spring Boot cung cấp. Nó giúp kéo đúng module và kích hoạt auto-configuration. Starter không phải tên khác của repository và cũng không phải phiên bản của Spring Session.

Các dòng Boot cũ thường dùng module Spring Session trực tiếp, kết hợp starter Redis/JDBC của Boot nếu ứng dụng chưa có hạ tầng đó. Boot 4 có starter riêng cho Spring Session Redis và JDBC.

### 1.4. Configuration properties

Property của Spring Session và property kết nối Redis thuộc hai nhóm khác nhau:

- `spring.session...`: cấu hình repository, namespace, timeout, flush/save mode và schema session.
- `spring.redis...` hoặc `spring.data.redis...`: cấu hình kết nối Redis như host, port, password, TLS và timeout.

Khi một prefix thay đổi, không được suy ra prefix còn lại cũng thay đổi theo cùng quy tắc. Cần kiểm tra từng nhóm riêng.

## 2. Bản đồ thay đổi giữa Boot 2.x, 3.x và 4.x

### 2.1. Bảng tổng hợp

| Dòng Spring Boot | Dependency/starter Redis thường gặp | Redis connection properties | Spring Session Redis properties | Nền tảng chính |
|---|---|---|---|---|
| Boot 2.x (ví dụ 2.7) | `org.springframework.session:spring-session-data-redis`; thường đi cùng `spring-boot-starter-data-redis` nếu cần auto-config Redis client | `spring.redis.*` | `spring.session.redis.*` | Spring Framework 5.x, Servlet `javax.*` |
| Boot 3.x (ví dụ 3.5) | `org.springframework.session:spring-session-data-redis`; dùng Redis starter của Boot khi cần hạ tầng connection factory | `spring.data.redis.*` | `spring.session.redis.*` | Spring Framework 6.x, Servlet `jakarta.*` |
| Boot 4.x | `org.springframework.boot:spring-boot-starter-session-data-redis` | `spring.data.redis.*` | `spring.session.data.redis.*` | Spring Framework 7.x, Jakarta EE 11, Servlet 6.1 |

Với JDBC, Boot 2.x/3.x thường dùng `org.springframework.session:spring-session-jdbc` cùng `spring-boot-starter-jdbc` hoặc starter JPA đã có sẵn. Boot 4 có `org.springframework.boot:spring-boot-starter-session-jdbc`.

Đây là bản đồ cho các dòng phổ biến, không thay thế metadata của minor/patch release cụ thể. Trước khi sửa dependency, kiểm tra tài liệu đúng phiên bản Boot và Spring Session đang dùng.

### 2.2. Ba thay đổi quan trọng cần nhớ

1. **Boot 3.0:** Redis connection properties chuyển từ `spring.redis.*` sang `spring.data.redis.*`.
2. **Boot 4.0:** Spring Session Redis properties chuyển từ `spring.session.redis.*` sang `spring.session.data.redis.*`.
3. **Boot 4:** Có starter chuyên biệt `spring-boot-starter-session-data-redis` và `spring-boot-starter-session-jdbc`; auto-configuration từ starter thay cho việc phải tự thêm `@Enable*HttpSession` trong cấu hình thông thường.

Không gộp hai lần đổi prefix thành một thay đổi duy nhất. Khi chuyển Boot 2.7 lên Boot 3.5, Redis connection prefix đổi nhưng Spring Session Redis prefix vẫn là `spring.session.redis`. Khi chuyển Boot 3.5 lên Boot 4, cả prefix Spring Session Redis đổi tiếp.

## 3. Dependency trên Boot 2.x và 3.x

### 3.1. Redis với module Spring Session trực tiếp

Trong các dòng Boot trước Boot 4, dependency module Spring Session thường được khai báo trực tiếp:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
```

Nếu ứng dụng đã có Redis starter do một thành phần khác cung cấp, không thêm dependency trùng lặp. Spring Session module cung cấp repository; Redis starter của Boot cung cấp cấu hình client và `RedisConnectionFactory` theo auto-configuration. Kiểm tra dependency tree để xác nhận cả hai lớp cần thiết đã có.

Trong một số guide Boot/Spring Session cũ, ví dụ chỉ khai báo `spring-session-data-redis` vì ứng dụng mẫu đã có Redis infrastructure. Hãy đọc toàn bộ dependency hiện hữu trước khi thêm starter.

### 3.2. JDBC với module Spring Session trực tiếp

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
</dependencies>
```

Nếu ứng dụng đã dùng `spring-boot-starter-data-jpa`, nó thường đã mang theo hạ tầng JDBC cần thiết. Không thêm starter JDBC chỉ vì thấy ví dụ có nó; xác minh `DataSource`, transaction manager và schema session đang được cấu hình.

### 3.3. Không tự đặt version module Spring Session khi dùng Boot BOM

Khi dự án dùng `spring-boot-starter-parent` hoặc import `spring-boot-dependencies`, thường để Boot quản lý version của `spring-session-data-redis` và `spring-session-jdbc`:

```xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
```

Không gắn version riêng nếu không có quyết định override có kiểm soát. Version Spring Session không tương thích với Spring Framework/Spring Data mà Boot quản lý có thể gây lỗi khởi động, `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi serialization chỉ xuất hiện khi có request.

### 3.4. Gradle và dependency constraints

Với Gradle, khai báo module tương tự:

```kotlin
dependencies {
    implementation("org.springframework.session:spring-session-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

Nếu dùng Spring Boot Gradle plugin và dependency management, không cần khai báo version cho các dependency do BOM quản lý. Nếu dự án dùng version catalog hoặc platform riêng, kiểm tra catalog không ghi đè version Spring Session/Redis khác với Boot BOM.

## 4. Starter mới trên Spring Boot 4

### 4.1. Redis starter

Boot 4 cung cấp starter riêng cho Spring Session Redis:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
```

Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-session-data-redis")
}
```

Starter giúp Boot tự cấu hình Spring Session Redis và Redis infrastructure theo convention. Với Servlet application, auto-configuration đăng ký repository/filter. Với reactive application, starter hỗ trợ Redis-backed `WebSession` theo cấu hình reactive tương ứng.

### 4.2. JDBC starter

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-jdbc</artifactId>
</dependency>
```

Starter JDBC gom phần tích hợp Spring Session JDBC với auto-configuration. Ứng dụng vẫn cần cấu hình database connection, schema/migration và quyền database phù hợp.

### 4.3. Không trộn starter mới và module cũ một cách tùy tiện

Khi chuyển Boot 4, nếu đã dùng `spring-boot-starter-session-data-redis`, không giữ thêm một khai báo `spring-session-data-redis` độc lập cùng version override nếu không có lý do. Starter mới đã chọn module phù hợp; khai báo lặp có thể làm dependency graph khó kiểm soát.

Không thêm cả Redis và JDBC starter nếu ứng dụng chỉ cần một repository. Nếu có nhiều implementation trên classpath, auto-configuration có thể chọn store theo thứ tự ưu tiên của phiên bản Boot. Hãy làm rõ store chủ đích và kiểm tra bean repository thực tế.

### 4.4. Khi cần cấu hình thủ công

Boot 4 cho phép dùng module Spring Session trực tiếp thay vì starter và tự điều khiển cấu hình bằng annotation như `@EnableRedisHttpSession` hoặc `@EnableJdbcHttpSession` cho Servlet. Khi khai báo annotation, auto-configuration tương ứng sẽ back off.

Chọn một cách cấu hình nhất quán:

- Starter Boot + auto-configuration + properties.
- Module Spring Session trực tiếp + annotation/bean cấu hình thủ công.

Không vừa bật starter auto-config vừa tạo cấu hình annotation/repository thủ công trùng chức năng mà không hiểu điều kiện back-off.

## 5. Thay đổi prefix Redis connection

### 5.1. Boot 2.x

Ví dụ cấu hình Redis connection trên Boot 2.7:

```yaml
spring:
  redis:
    host: redis.internal
    port: 6379
    password: ${REDIS_PASSWORD}
```

### 5.2. Boot 3.x và Boot 4.x

Từ Boot 3.0, prefix Redis connection chuyển sang `spring.data.redis`:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      password: ${REDIS_PASSWORD}
```

Các thuộc tính như database index, username, SSL, Sentinel, Cluster, timeout và URL cũng nằm dưới `spring.data.redis.*` theo metadata của phiên bản.

### 5.3. Kiểm tra biến môi trường

Spring Boot relaxed binding ánh xạ property sang biến môi trường. Vì vậy, khi nâng Boot 2 lên Boot 3/4, đổi tên biến tương ứng:

| Property | Biến môi trường |
|---|---|
| `spring.redis.host` | `SPRING_REDIS_HOST` |
| `spring.data.redis.host` | `SPRING_DATA_REDIS_HOST` |
| `spring.session.redis.namespace` | `SPRING_SESSION_REDIS_NAMESPACE` |
| `spring.session.data.redis.namespace` | `SPRING_SESSION_DATA_REDIS_NAMESPACE` |

Nếu manifest Kubernetes, Helm chart, Docker Compose, secret store hoặc pipeline CI vẫn đặt biến cũ, file YAML mới có thể đúng nhưng ứng dụng vẫn kết nối sai host hoặc dùng giá trị mặc định. Tìm cả tên property và tên biến môi trường trong cấu hình triển khai.

## 6. Thay đổi prefix Spring Session Redis ở Boot 4

### 6.1. Boot 2.x và 3.x

Ví dụ namespace và flush mode:

```yaml
spring:
  session:
    redis:
      namespace: "portal:session"
      flush-mode: on-save
      save-mode: on-set-attribute
```

Các property Redis session phổ biến của Boot 3.5 vẫn có prefix `spring.session.redis`, gồm namespace, repository type, flush mode, save mode và configure action.

### 6.2. Boot 4.x

Trong Boot 4, nhóm property này được đổi để phản ánh việc Spring Session sử dụng Spring Data Redis:

```yaml
spring:
  session:
    data:
      redis:
        namespace: "portal:session"
        flush-mode: on-save
        save-mode: on-set-attribute
```

Đổi prefix `spring.session.redis` thành `spring.session.data.redis`. Không thay đổi tên các leaf property nếu metadata Boot 4 vẫn giữ nguyên; kiểm tra tài liệu property của minor release mục tiêu.

### 6.3. Các property không đổi prefix theo cùng cách

`spring.session.timeout` vẫn là property cấp chung. Các property JDBC như `spring.session.jdbc.table-name`, `spring.session.jdbc.initialize-schema` và `spring.session.jdbc.cleanup-cron` tiếp tục nằm dưới `spring.session.jdbc` trong Boot 4. Không tự chuyển chúng thành `spring.session.data.jdbc`.

### 6.4. Bảng mapping chi tiết

| Ý nghĩa | Boot 2.x/3.x | Boot 4.x |
|---|---|---|
| Redis host | `spring.redis.host` (Boot 2) hoặc `spring.data.redis.host` (Boot 3) | `spring.data.redis.host` |
| Redis port | `spring.redis.port` (Boot 2) hoặc `spring.data.redis.port` (Boot 3) | `spring.data.redis.port` |
| Session Redis namespace | `spring.session.redis.namespace` | `spring.session.data.redis.namespace` |
| Session Redis flush mode | `spring.session.redis.flush-mode` | `spring.session.data.redis.flush-mode` |
| Session Redis save mode | `spring.session.redis.save-mode` | `spring.session.data.redis.save-mode` |
| Redis repository type | `spring.session.redis.repository-type` | `spring.session.data.redis.repository-type` |
| Session timeout | `spring.session.timeout` | `spring.session.timeout` |
| JDBC table | `spring.session.jdbc.table-name` | `spring.session.jdbc.table-name` |

## 7. Auto-configuration và lựa chọn repository

### 7.1. Boot 2.x

Boot 2 cung cấp auto-configuration Spring Session và property `spring.session.store-type` để chọn store. Trong các ứng dụng có nhiều module session trên classpath, khai báo store type rõ ràng giúp tránh chọn nhầm. Ví dụ:

```yaml
spring:
  session:
    store-type: redis
```

Với Redis, auto-configuration tạo `springSessionRepositoryFilter`, thay thế cách lưu `HttpSession` cục bộ của Servlet container bằng repository Spring Session.

### 7.2. Boot 3.x

Boot 3 tiếp tục hỗ trợ auto-configuration Servlet và reactive. Các tài liệu Boot 3.x mới mô tả việc chọn repository dựa trên module có trên classpath; khi nhiều store cùng hiện diện, thứ tự ưu tiên phụ thuộc phiên bản Boot. Ví dụ tài liệu Boot 3.5 nêu Redis trước JDBC, sau đó Hazelcast và MongoDB.

Do hành vi và property có thể khác giữa các minor release, hãy kiểm tra tài liệu đúng phiên bản thay vì giả định cấu hình `spring.session.store-type` của ứng dụng cũ vẫn là lựa chọn tốt nhất. Cách đơn giản nhất là chỉ đưa module của store thực sự dùng vào classpath.

### 7.3. Boot 4.x

Boot 4 có starter riêng cho từng store được hỗ trợ. Với Servlet, Redis và JDBC có starter tương ứng; auto-configuration thay cho `@Enable*HttpSession` trong cấu hình thông thường. Reactive có Redis-backed WebSession qua Redis session starter.

Nếu cần kiểm soát chi tiết, dùng module Spring Session trực tiếp và annotation cấu hình; khi đó Boot auto-configuration tương ứng sẽ back off.

### 7.4. Kiểm tra repository thực tế

Sau khi nâng cấp, xác minh:

- Có đúng một `SessionRepository`/`ReactiveSessionRepository` được chọn cho ứng dụng.
- Filter `springSessionRepositoryFilter` có được đăng ký cho Servlet request không.
- Redis namespace hoặc JDBC table/schema đúng môi trường.
- Cookie session name/domain/path giữ nguyên nếu đó là yêu cầu tương thích.
- Không có cấu hình annotation tạo repository thứ hai.
- Session có thể được tạo, đọc lại, cập nhật, invalidate và hết hạn.

Không kết luận repository đã hoạt động chỉ vì Spring ApplicationContext khởi động thành công. Một số lỗi kết nối hoặc serialization chỉ xuất hiện khi request đầu tiên truy cập session.

## 8. Chuyển đổi Servlet `javax` sang `jakarta`

### 8.1. Ranh giới Boot 2 và Boot 3

Boot 3 chuyển sang Jakarta EE 10, Spring Framework 6 và Servlet 6.0. Các API Java EE cũ đổi package từ `javax.*` sang `jakarta.*`. Vì vậy, mã tùy chỉnh tích hợp Servlet/Spring Session cần cập nhật import.

Ví dụ:

```java
// Boot 2.x
import javax.servlet.Filter;
import javax.servlet.http.HttpSession;
```

```java
// Boot 3.x và 4.x
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpSession;
```

Không giữ đồng thời cả `javax.servlet-api` và `jakarta.servlet-api` như một cách sửa nhanh. Hai kiểu này không tương thích nhị phân. Dependency cũ có thể kéo `javax.servlet` vào classpath và gây lỗi khi khởi động hoặc deploy.

### 8.2. Boot 4 tiếp tục nâng baseline

Boot 4 yêu cầu Spring Framework 7 và Jakarta EE 11 với Servlet 6.1 baseline. Ngoài package `jakarta`, cần kiểm tra tương thích của servlet container, filter, security integration, thư viện kiểm thử và customizer.

### 8.3. Tìm dependency còn dùng `javax`

Sau khi nâng, rà soát:

- Import `javax.servlet.*` trong source.
- Dependency `javax.servlet:javax.servlet-api`.
- Filter/listener tự viết.
- Thư viện bên thứ ba tích hợp Servlet.
- Test fixture và mock request/response.

Không thay hàng loạt mọi `javax.*` thành `jakarta.*`: một số package Java SE như `javax.crypto`, `javax.net` hoặc `javax.sql` không thuộc Jakarta EE và không được đổi.

## 9. Quy trình nâng cấp theo từng chặng

### 9.1. Nâng Boot 2.7 lên Boot 3.x

Nên chia thành các bước nhỏ:

1. Nâng ứng dụng lên bản patch mới nhất của Boot 2.7 trước khi bắt đầu.
2. Xác nhận Spring Session module được Boot BOM quản lý, không có version override ngoài ý muốn.
3. Nâng Boot lên 3.x và Java tối thiểu 17.
4. Chuyển các dependency Servlet từ `javax` sang `jakarta`.
5. Đổi Redis connection prefix từ `spring.redis` sang `spring.data.redis`.
6. Giữ Spring Session Redis prefix theo dòng Boot 3, thường là `spring.session.redis`.
7. Rà soát Spring Security 6 và các filter/session strategy tùy chỉnh.
8. Kiểm tra schema JDBC, Redis serialization và cookie/session ID.
9. Chạy integration test với Redis/JDBC thật.

### 9.2. Nâng Boot 3.x lên Boot 4.x

1. Nâng ứng dụng lên minor/patch mới nhất của dòng Boot 3 được chọn làm điểm xuất phát.
2. Đọc Boot 4 migration guide và review dependency management diff.
3. Xác nhận Java, Spring Framework 7, Jakarta EE 11 và Servlet container đáp ứng baseline.
4. Thay module Spring Session trực tiếp bằng Boot 4 session starter nếu chọn auto-configuration.
5. Đổi Redis session prefix từ `spring.session.redis` sang `spring.session.data.redis`.
6. Giữ Redis connection prefix `spring.data.redis`.
7. Kiểm tra `spring.session.jdbc.*` và `spring.session.timeout` theo metadata mới.
8. Bỏ annotation cấu hình session thủ công nếu chuyển sang starter auto-configuration; hoặc giữ module trực tiếp và quản lý annotation nhất quán.
9. Kiểm tra serializer, schema, session cookie và khả năng đọc session cũ trong giai đoạn rollout.
10. Chạy test startup, integration, security, timeout, logout và nhiều instance.

### 9.3. Không nâng nhiều major cùng lúc nếu chưa có điểm kiểm soát

Nếu vừa nâng Boot, Spring Session, Spring Security, Redis major, database driver và serializer trong một thay đổi, khi lỗi xảy ra rất khó xác định nguyên nhân. Chia thay đổi thành các mốc có thể build/test độc lập, lưu dependency tree trước và sau, và giữ khả năng rollback.

## 10. Dùng Properties Migrator đúng cách

### 10.1. Mục đích

Spring Boot cung cấp `spring-boot-properties-migrator` để phát hiện property đã đổi tên hoặc bị loại bỏ. Migrator có thể in cảnh báo và tạm thời ánh xạ một số property trong runtime để hỗ trợ chuyển đổi.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Gradle:

```kotlin
runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
```

### 10.2. Không giữ migrator lâu dài

Migrator là công cụ chuyển tiếp, không phải lớp tương thích cấu hình lâu dài. Sau khi đã đổi property, xóa dependency migrator và chạy lại toàn bộ test. Nếu giữ nó, cấu hình sai có thể tiếp tục hoạt động tạm thời và bị bỏ sót khi triển khai ở môi trường khác.

### 10.3. Migrator không thay thế migration dependency

Properties Migrator không tự sửa:

- Dependency artifact sai.
- Spring Session/Spring Framework version không tương thích.
- Import `javax` còn sót.
- Schema JDBC chưa được nâng.
- Redis serializer không đọc được session cũ.
- Custom `@Configuration` tạo repository trùng lặp.

Hãy xem log migrator như danh sách cần xử lý, không phải xác nhận ứng dụng đã nâng cấp xong.

## 11. Ví dụ cấu hình qua ba dòng Boot

### 11.1. Boot 2.7 với Redis

```yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: "portal:session"
      flush-mode: on-save
  redis:
    host: redis.internal
    port: 6379
```

### 11.2. Boot 3.5 với Redis

```yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: "portal:session"
      flush-mode: on-save
  data:
    redis:
      host: redis.internal
      port: 6379
```

Trong Boot 3.x, xác minh cách chọn store nếu nhiều module repository có mặt trên classpath. Tài liệu Boot 3.5 mô tả lựa chọn auto-configuration theo thứ tự ưu tiên; tránh thêm các module không dùng.

### 11.3. Boot 4.2 với Redis starter

Dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
```

Configuration:

```yaml
spring:
  session:
    timeout: 30m
    data:
      redis:
        namespace: "portal:session"
        flush-mode: on-save
  data:
    redis:
      host: redis.internal
      port: 6379
```

Các ví dụ minh họa khác biệt prefix. Với từng minor release, kiểm tra property metadata và lựa chọn `flush-mode`, `save-mode`, repository type theo nhu cầu. Không copy cấu hình Boot 2 vào Boot 4 rồi chỉ đổi một prefix.

## 12. Những điểm cần kiểm tra khi chuyển JDBC

### 12.1. Dependency

Boot 2.x/3.x thường dùng `spring-session-jdbc` trực tiếp cùng `spring-boot-starter-jdbc` hoặc JPA. Boot 4 cung cấp `spring-boot-starter-session-jdbc`.

### 12.2. Schema và migration

Kiểm tra schema `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`, index, kiểu cột timestamp, độ dài session ID và quyền DDL/DML. Không để auto schema initialization ghi đè dữ liệu production. Với production, dùng Flyway/Liquibase hoặc migration đã review.

### 12.3. Property JDBC

Các property như:

```yaml
spring:
  session:
    jdbc:
      table-name: SPRING_SESSION
      initialize-schema: never
      cleanup-cron: "0 * * * * *"
```

vẫn thuộc `spring.session.jdbc` trong các dòng Boot hiện hành. Giá trị `initialize-schema` cần theo môi trường và phiên bản; ví dụ `never` phù hợp khi schema được quản lý bằng migration riêng. Kiểm tra metadata Boot mục tiêu trước khi dùng.

### 12.4. Kiểm tra transaction và connection pool

Sau nâng cấp, đo query latency, cleanup job, connection pool và transaction. Driver/database version có thể thay đổi theo Boot BOM; không kết luận vấn đề là Spring Session nếu dependency driver hoặc SQL dialect đã đổi.

## 13. Kiểm tra dependency graph

### 13.1. Maven

Xem dependency tree trước và sau nâng cấp:

```bash
mvn dependency:tree -Dincludes=org.springframework.session,org.springframework.data,org.springframework.boot,javax.servlet,jakarta.servlet
```

Kiểm tra effective POM:

```bash
mvn help:effective-pom
```

Tìm:

- Nhiều version `spring-session-core` hoặc `spring-session-data-redis`.
- Spring Data Redis không cùng dòng với Boot BOM.
- `javax.servlet-api` còn xuất hiện trong Boot 3/4.
- Cả starter session mới và module cũ cùng bị pin version khác nhau.
- Dependency Redis client trùng hoặc xung đột giữa Lettuce/Jedis.

### 13.2. Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-session-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-session-data-redis --configuration runtimeClasspath
```

Kiểm tra version được chọn cuối cùng, không chỉ dependency khai báo trực tiếp. Version conflict resolution có thể chọn một bản ngoài ý muốn do plugin, platform hoặc dependency transitive.

### 13.3. Kiểm tra dependency quản lý bởi Boot

Nếu dự án import nhiều BOM, thứ tự platform có thể ảnh hưởng version. Spring Cloud release train cũng phải tương thích với dòng Boot. Không import Spring Session BOM hoặc Spring Data BOM riêng nếu Boot BOM đã quản lý và không có quyết định override rõ ràng.

## 14. Kiểm thử sau khi đổi dependency và property

### 14.1. Kiểm tra startup và auto-configuration

Khởi động application context trong profile tương ứng và xác minh repository/filter được tạo. Khi cần, bật condition evaluation report (`--debug`) để hiểu auto-configuration nào match hoặc back off. Không dựa vào việc ứng dụng không ném exception để kết luận đúng store đã được chọn.

### 14.2. Kiểm thử vòng đời session

Với Redis hoặc JDBC test store riêng:

1. Tạo session qua HTTP.
2. Lấy cookie `SESSION`.
3. Gửi request tiếp theo với cookie đó và xác minh attribute được khôi phục.
4. Cập nhật attribute và xác minh thay đổi được lưu.
5. Logout/invalidate và xác minh session cũ không còn được nạp.
6. Chờ idle timeout và xác minh session hết hạn.

### 14.3. Kiểm thử nhiều instance

Chạy hai node cùng repository/namespace/schema. Tạo session ở node A rồi gửi cookie sang node B. Xác minh B đọc được session. Đây là cách phát hiện cấu hình namespace, serializer hoặc repository bị lệch giữa các node sau rollout.

### 14.4. Kiểm thử cookie và Security

Xác minh cookie name, domain, path, Secure, HttpOnly và SameSite không đổi ngoài chủ ý. Kiểm tra Spring Security session fixation strategy, concurrent session control, logout handler và CSRF. Nâng Boot có thể kéo theo Spring Security major mới, vì vậy test session không nên chỉ dừng ở repository.

### 14.5. Kiểm thử tương thích dữ liệu cũ

Nếu rollout rolling deployment, node phiên bản mới có thể phải đọc session do node cũ ghi và ngược lại. Kiểm tra serializer, class name, DTO/attribute version và SecurityContext. Nếu không bảo đảm tương thích, cần kế hoạch buộc đăng nhập lại hoặc migrate session có kiểm soát.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Boot 3 không kết nối Redis | Vẫn dùng `spring.redis.*` | Chuyển Redis connection config sang `spring.data.redis.*` |
| Boot 4 dùng namespace mặc định thay vì namespace cũ | Vẫn dùng `spring.session.redis.namespace` | Đổi sang `spring.session.data.redis.namespace` |
| Boot 4 không tự cấu hình session | Dependency cũ không đúng starter hoặc auto-config bị exclude | Dùng session starter phù hợp hoặc cấu hình module/annotation thủ công |
| JDBC được chọn dù muốn Redis | Nhiều store module cùng có trên classpath hoặc starter không rõ | Loại dependency không dùng và xác minh auto-configuration selection |
| Hai `SessionRepositoryFilter` hoặc bean session trùng | Vừa dùng starter vừa bật `@Enable*HttpSession`/cấu hình tay | Chọn một cơ chế cấu hình và kiểm tra back-off |
| `ClassNotFoundException: javax.servlet...` | Dependency Servlet cũ còn trong Boot 3/4 | Cập nhật thư viện sang Jakarta-compatible và loại API cũ |
| `NoSuchMethodError` trong Spring Session/Data | Tự pin version không khớp Boot BOM | Bỏ override hoặc chọn ma trận version tương thích |
| Session mất sau deploy | Namespace/cookie/serializer khác nhau giữa các node | Đồng bộ cấu hình hoặc có kế hoạch migration/reauthentication |
| Property migrator báo property cũ | Cấu hình chưa chuyển hết | Sửa file YAML, env var, Helm/CI rồi gỡ migrator |
| Test pass nhưng production dùng Redis khác | Profile/env var override host/namespace | Kiểm tra effective configuration trong môi trường triển khai |
| Redis client conflict | Trộn Lettuce/Jedis hoặc nhiều version | Kiểm tra dependency tree và chỉ chọn client dự kiến |
| Schema JDBC lỗi sau nâng cấp | Driver/schema/index không tương thích | Chạy migration được review và integration test với DB mục tiêu |

## 16. Checklist nâng cấp

- [ ] Ghi lại Boot, Spring Framework, Spring Session, Spring Security và Spring Data version hiện tại.
- [ ] Xác nhận Boot BOM quản lý dependency; loại bỏ version override không cần thiết.
- [ ] Chọn đúng dependency module/starter cho Redis hoặc JDBC theo dòng Boot.
- [ ] Kiểm tra Redis client starter và `RedisConnectionFactory` có mặt đúng cách.
- [ ] Đổi `spring.redis.*` thành `spring.data.redis.*` khi chuyển từ Boot 2 sang Boot 3+.
- [ ] Đổi `spring.session.redis.*` thành `spring.session.data.redis.*` khi chuyển từ Boot 3 sang Boot 4.
- [ ] Giữ `spring.session.jdbc.*` và `spring.session.timeout` theo metadata phiên bản.
- [ ] Cập nhật biến môi trường, Helm, Kubernetes, Docker Compose và pipeline CI.
- [ ] Chuyển `javax.servlet` sang `jakarta.servlet` khi nâng Boot 3+.
- [ ] Kiểm tra Jakarta EE/Servlet baseline và container khi nâng Boot 4.
- [ ] Không kết hợp starter auto-config với annotation/repository thủ công trùng chức năng.
- [ ] Kiểm tra repository thực tế, filter, namespace, schema và cookie.
- [ ] Chạy integration test Redis/JDBC, security, timeout, logout và multi-node.
- [ ] Kiểm tra session serialization và rolling deployment compatibility.
- [ ] Dùng Properties Migrator tạm thời nếu cần rồi gỡ bỏ.

Khi nâng Spring Session theo các dòng Boot, hãy thay dependency, starter và property như ba phần của cùng một thay đổi có kiểm soát. Boot 2 dùng `spring.redis.*` và `spring.session.redis.*`; Boot 3 chuyển Redis connection sang `spring.data.redis.*` nhưng Spring Session Redis vẫn dùng `spring.session.redis.*`; Boot 4 chuyển tiếp Spring Session Redis sang `spring.session.data.redis.*` và cung cấp starter session chuyên biệt. Sau mỗi bước, kiểm tra dependency graph, auto-configuration, repository thực tế và khả năng đọc lại session qua HTTP trên Redis/JDBC dùng chung.

## Tài liệu tham khảo

- [Spring Boot 2.7 — Spring Session Guide](https://docs.spring.io/spring-session/docs/2.7/guides/boot-redis.html)
- [Spring Boot 3.0 Migration Guide — Redis Properties](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.5 — Spring Session](https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html)
- [Spring Boot 4.0 Migration Guide — Spring Session Properties](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot 4.2 — Spring Session Starters](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Spring Session 3.5 — Redis Configuration](https://docs.spring.io/spring-session/reference/3.5/configuration/redis.html)
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
