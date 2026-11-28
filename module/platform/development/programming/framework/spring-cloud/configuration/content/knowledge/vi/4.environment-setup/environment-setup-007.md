# Kiểm tra dependency, tự cấu hình và điều kiện tái lập thí nghiệm

Một ứng dụng Spring Cloud Config có thể chạy trên máy của lập trình viên nhưng lỗi khi triển khai vì dependency không tương thích, auto-configuration không được kích hoạt hoặc môi trường thử nghiệm khác với môi trường đã kiểm tra. Trước khi đánh giá hành vi của Config Server và Config Client, cần xác nhận ba điều: ứng dụng nạp đúng thư viện, Spring tạo đúng các bean cần thiết và mọi đầu vào ảnh hưởng đến kết quả đều có thể ghi nhận để tái lập.

## 1. Kiểm tra phiên bản Spring Boot và Spring Cloud

Spring Boot và Spring Cloud được phát hành theo các dòng phiên bản có ma trận tương thích. Một dự án cần chọn Spring Cloud release train phù hợp với phiên bản Spring Boot đang dùng. Không nên chọn hai phiên bản mới nhất một cách độc lập hoặc khai báo phiên bản riêng cho từng thư viện Spring Cloud, vì các module có thể yêu cầu những phiên bản Spring Framework và Spring Boot khác nhau.

Với Maven, quản lý phiên bản Spring Cloud qua BOM `spring-cloud-dependencies` trong `dependencyManagement`:

```xml
<properties>
    <java.version>21</java.version>
    <spring-cloud.version>${compatible-cloud-release}</spring-cloud.version>
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
```

`compatible-cloud-release` là placeholder cần thay bằng release train tương thích theo ma trận chính thức của Spring Cloud cho phiên bản Spring Boot đã chọn. Dùng Spring Boot parent hoặc BOM tương ứng để quản lý các dependency Spring Boot. Khi nâng cấp, hãy cập nhật theo một cặp phiên bản tương thích và chạy lại kiểm tra tích hợp.

Với Gradle, có thể import cùng BOM bằng dependency platform:

```kotlin
dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))
    implementation("org.springframework.cloud:spring-cloud-starter-config")
}
```

Khai báo phiên bản của release train tại một nơi dùng chung trong build, chẳng hạn `gradle.properties` hoặc version catalog. Không trộn nhiều BOM có cùng trách nhiệm quản lý phiên bản nếu chưa hiểu rõ thứ tự và quy tắc ghi đè của chúng.

## 2. Chọn dependency đúng vai trò

Config Server và Config Client là hai ứng dụng có vai trò khác nhau. Server cung cấp REST API để đọc cấu hình từ backend như Git; client gọi server và nạp kết quả vào Spring `Environment`.

| Thành phần | Dependency chính | Vai trò |
| --- | --- | --- |
| Config Server | `org.springframework.cloud:spring-cloud-config-server` | Bật dịch vụ cung cấp cấu hình |
| Config Client | `org.springframework.cloud:spring-cloud-starter-config` | Nạp cấu hình từ Config Server |
| Actuator (tùy chọn) | `org.springframework.boot:spring-boot-starter-actuator` | Hỗ trợ health check và chẩn đoán |

Ví dụ khai báo trong Maven cho một Config Server:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Ứng dụng server cần bật chức năng Config Server:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigurationServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigurationServerApplication.class, args);
    }
}
```

Ví dụ khai báo trong Maven cho một Config Client:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
```

Client dùng Config Data import để khai báo địa chỉ server:

```yaml
spring:
  application:
    name: billing-api
  config:
    import: "optional:configserver:http://localhost:8888"
```

Nếu cấu hình từ xa là điều kiện bắt buộc để ứng dụng hoạt động, bỏ `optional:` để lỗi kết nối hoặc lỗi nạp cấu hình làm ứng dụng khởi động thất bại. `spring.config.import` là cách tích hợp Config Client theo cơ chế Config Data hiện đại. Dự án cũ có thể dùng bootstrap context với dependency bootstrap tương ứng; không nên thêm cơ chế bootstrap cũ vào dự án mới nếu không có yêu cầu tương thích cụ thể.

Chỉ thêm dependency cho vai trò mà ứng dụng thực sự đảm nhiệm. Một ứng dụng client không cần dependency Config Server chỉ để gọi server; một ứng dụng server không cần tự thêm Config Client trừ khi nó cũng phải lấy cấu hình từ một Config Server khác.

## 3. Đọc dependency tree để tìm lỗi

Khai báo trực tiếp trong file build chưa cho biết toàn bộ thư viện được nạp. Một starter có thể kéo theo nhiều dependency bắc cầu; xung đột phiên bản thường xuất hiện ở những thư viện đó.

Với Maven, các lệnh sau giúp kiểm tra dependency:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud
./mvnw help:effective-pom
```

Trên Windows có thể chạy `mvnw.cmd` thay cho `./mvnw`. `dependency:tree` cho thấy đường dẫn dependency và phiên bản được chọn; `effective-pom` cho thấy các cấu hình được kế thừa và hợp nhất từ parent, profile cùng BOM.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-config --configuration runtimeClasspath
```

`dependencies` hiển thị cây dependency của cấu hình đã chọn. `dependencyInsight` giải thích vì sao một phiên bản cụ thể được chọn, ví dụ do BOM, constraint hoặc một dependency bắc cầu yêu cầu. Tên cấu hình có thể khác với dự án đa module hoặc Android; hãy chọn cấu hình runtime thực tế của ứng dụng.

Khi đọc kết quả, tập trung vào các dấu hiệu sau:

- Có nhiều phiên bản khác nhau của Spring Boot, Spring Framework hoặc Spring Cloud trong runtime classpath.
- Một thư viện bị ép phiên bản thủ công và không còn khớp với BOM.
- Starter cần thiết cho Config Server hoặc Config Client không xuất hiện trong runtime classpath.
- Dependency chỉ nằm trong `test` hoặc `provided` trong khi ứng dụng cần nó khi chạy.
- Có nhiều thư viện cùng cung cấp một chức năng hoặc một implementation ngoài dự kiến.

Không nên sửa xung đột bằng cách loại trừ dependency bắc cầu ngay khi thấy hai phiên bản. Trước hết xác định thư viện nào yêu cầu phiên bản đó, BOM nào đang quản lý và liệu có release train tương thích hơn hay không. Chỉ dùng exclusion hoặc version constraint khi đã hiểu ảnh hưởng và có kiểm thử bảo vệ.

## 4. Spring Boot auto-configuration hoạt động như thế nào?

`@SpringBootApplication` bao gồm cấu hình auto-configuration của Spring Boot. Auto-configuration quan sát classpath, các bean đã đăng ký, thuộc tính cấu hình và loại ứng dụng để quyết định cấu hình nào phù hợp. Các lớp cấu hình thường dùng những điều kiện như:

| Điều kiện | Ý nghĩa |
| --- | --- |
| `@ConditionalOnClass` | Kích hoạt khi lớp hoặc thư viện cần thiết có trên classpath |
| `@ConditionalOnMissingBean` | Cung cấp bean mặc định khi ứng dụng chưa tự khai báo bean tương ứng |
| `@ConditionalOnProperty` | Kích hoạt theo giá trị một thuộc tính |
| `@ConditionalOnBean` | Kích hoạt khi một bean phụ thuộc đã tồn tại |
| `@ConditionalOnWebApplication` | Kích hoạt khi ứng dụng có loại môi trường web phù hợp |

Nhờ các điều kiện này, chỉ thêm dependency không có nghĩa mọi tính năng liên quan đều tự động được bật. Ví dụ, Config Server cần dependency server và annotation `@EnableConfigServer` để công bố các endpoint server. Config Client cần starter client và cấu hình import để yêu cầu, nạp cấu hình từ xa. Hai vai trò không thể thay thế cho nhau.

Auto-configuration thường cung cấp bean mặc định nếu ứng dụng chưa tự khai báo bean. Khi người phát triển định nghĩa bean cùng loại, điều kiện `@ConditionalOnMissingBean` có thể khiến cấu hình mặc định lùi lại. Đây là cơ chế mở rộng có chủ đích, nhưng một bean tùy chỉnh sai qualifier, tên hoặc lifecycle cũng có thể làm ứng dụng không hoạt động như dự kiến.

## 5. Xem báo cáo điều kiện auto-configuration

Khi một bean hoặc tính năng không xuất hiện, bật báo cáo điều kiện để xem cấu hình nào khớp và cấu hình nào bị loại:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc khi chạy JAR:

```bash
java -jar app.jar --debug
```

`--debug` yêu cầu Spring Boot in condition evaluation report trong log khởi động. Hãy tìm tên auto-configuration liên quan và lý do điều kiện không thỏa mãn, chẳng hạn thiếu class, thiếu property hoặc đã có bean khác.

Nếu dự án đã bật Actuator, endpoint `conditions` cũng có thể cung cấp báo cáo điều kiện:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Sau khi được phơi bày, endpoint thường truy cập qua `/actuator/conditions`. Chỉ bật endpoint chẩn đoán trên môi trường phù hợp và bảo vệ bằng xác thực, phân quyền, giới hạn mạng. Endpoint `env` và `configprops` cũng hữu ích khi kiểm tra giá trị cấu hình và bean đã bind, nhưng có thể tiết lộ thông tin nhạy cảm; không công khai chúng tùy tiện.

Nếu một auto-configuration cần bị loại trừ, có thể dùng `exclude` trên `@SpringBootApplication` hoặc thuộc tính `spring.autoconfigure.exclude`. Chỉ loại trừ sau khi báo cáo điều kiện xác nhận cấu hình đó là nguyên nhân và đã xác định bean hoặc chức năng nào thay thế nó. Loại trừ một cấu hình có thể làm mất nhiều bean phụ thuộc, không chỉ một bean nhìn thấy đầu tiên.

## 6. Phân biệt lỗi dependency, auto-configuration và nạp cấu hình

Ba nhóm lỗi thường có biểu hiện gần giống nhau nhưng cách xử lý khác nhau:

| Triệu chứng | Nhóm nguyên nhân nên kiểm tra trước |
| --- | --- |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu dependency, scope sai hoặc dependency tree có phiên bản không tương thích |
| Không tìm thấy bean mong đợi | Auto-configuration không khớp điều kiện, chưa bật annotation cần thiết hoặc bean tùy chỉnh thay thế cấu hình mặc định |
| Client không tải được property source | Thiếu Config Client, sai `spring.config.import`, sai URL, profile, label hoặc lỗi kết nối/xác thực |
| Ứng dụng khởi động nhưng giá trị vẫn là mặc định | Property source không được nạp, tên ứng dụng/profile không đúng hoặc nguồn có độ ưu tiên cao hơn ghi đè |
| Lỗi chỉ xuất hiện ở môi trường triển khai | Khác JDK, biến môi trường, quyền Git, mạng, secret hoặc revision cấu hình |

Nên kiểm tra theo thứ tự: xác nhận dependency runtime; xem log và condition report; kiểm tra Config Client đã nạp đúng endpoint và metadata; sau đó xác định property source thắng và giá trị cuối cùng đã bind. Cách này giúp tránh thay đổi dependency để xử lý một lỗi thực chất do profile hoặc label.

## 7. Ghi nhận điều kiện để tái lập thí nghiệm

Một thí nghiệm cấu hình chỉ có thể tái lập khi các đầu vào ảnh hưởng đến kết quả được ghi nhận. Với Spring Cloud Config, không chỉ mã nguồn ứng dụng mà cả revision cấu hình từ xa cũng là một phần của thí nghiệm.

| Nhóm thông tin | Cần ghi nhận |
| --- | --- |
| Mã nguồn | Git commit của ứng dụng, nhánh làm việc và trạng thái thay đổi |
| JDK và build | Phiên bản Java, Maven/Gradle wrapper, toolchain và lệnh build |
| Framework | Phiên bản Spring Boot, Spring Cloud release train và dependency lock hoặc dependency tree |
| Config Client | `spring.application.name`, profile đang hoạt động, Config Server URI và label |
| Config Server | Git revision thực tế, backend, trạng thái truy cập và phiên bản server |
| Runtime | Biến môi trường cần thiết, hệ điều hành hoặc image container, timezone và locale nếu chúng ảnh hưởng kết quả |
| Kết quả | Lệnh chạy, log liên quan, kết quả kiểm thử và thời điểm thực hiện |

Không ghi giá trị bí mật vào tài liệu thí nghiệm. Ghi tên biến, nguồn cấp và phiên bản tham chiếu của secret nếu cần; không lưu token, mật khẩu, private key hay nội dung nhạy cảm trong log hoặc báo cáo.

Các lệnh cơ bản để thu thập thông tin build và môi trường:

```bash
java -version
./mvnw -version
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud
git rev-parse HEAD
git status --short
```

Với Gradle, dùng `./gradlew --version` và `./gradlew dependencies --configuration runtimeClasspath`. Trên Windows, dùng các wrapper `.cmd` hoặc `.bat` tương ứng. Wrapper giúp dự án sử dụng đúng phiên bản Maven hoặc Gradle đã khai báo; JDK vẫn cần được kiểm soát riêng bằng toolchain hoặc môi trường build chuẩn.

## 8. Cố định dependency và cấu hình để có thể tái lập

Để hai lần chạy có kết quả tương đương, hãy cố định những đầu vào có thể thay đổi:

1. Commit Maven Wrapper hoặc Gradle Wrapper và khai báo JDK toolchain rõ ràng.
2. Quản lý Spring Cloud bằng BOM tương thích, tránh version override rải rác.
3. Bật dependency locking hoặc lưu dependency verification phù hợp nếu dự án cần kiểm soát chặt phiên bản và artifact được tải.
4. Ghi nhận commit của ứng dụng và revision cấu hình Git. Với thí nghiệm quan trọng, chọn tag bất biến hoặc commit cụ thể làm Config Server label thay vì phụ thuộc nhánh có thể tiếp tục thay đổi.
5. Khai báo rõ profile, Config Server URI và các biến môi trường bắt buộc trong cấu hình triển khai hoặc hướng dẫn chạy.
6. Dùng container image theo digest khi cần cố định cả hệ điều hành và runtime, đồng thời giữ secret bên ngoài image.
7. Chạy cùng bộ lệnh kiểm thử và lưu log, kết quả cùng metadata của lần chạy.

Dependency locking giúp ngăn việc phân giải dependency thay đổi ngoài ý muốn, nhưng không thay thế việc cập nhật bảo mật định kỳ. Sau khi nâng phiên bản, cần cập nhật lockfile có chủ đích và chạy lại kiểm thử. Tương tự, cố định Config Server label giúp tái lập dữ liệu cấu hình nhưng không đảm bảo mọi dịch vụ phụ thuộc bên ngoài cũng có cùng trạng thái; cần ghi nhận những phụ thuộc đó nếu chúng ảnh hưởng kết quả.

## 9. Quy trình kiểm tra trước khi chạy

Có thể áp dụng quy trình ngắn sau cho mỗi thí nghiệm hoặc lần triển khai:

1. Kiểm tra JDK và build wrapper đúng phiên bản.
2. Đọc BOM và dependency tree để xác nhận các module Spring Boot/Spring Cloud tương thích, starter server/client đúng vai trò.
3. Chạy ứng dụng với `--debug` nếu cần và xác nhận auto-configuration mong đợi đã khớp.
4. Kiểm tra Config Client dùng đúng application, profile, label và Config Server URI.
5. Xác nhận Config Server trả về đúng Git revision và property source cần thiết.
6. Kiểm tra giá trị đã bind, biến môi trường và secret được cung cấp đúng cách.
7. Ghi lại commit ứng dụng, revision cấu hình, lệnh chạy và kết quả kiểm thử.

Khi dependency, auto-configuration và môi trường được kiểm tra có hệ thống, lỗi cấu hình sẽ dễ khoanh vùng hơn. Việc lưu lại phiên bản ứng dụng cùng revision cấu hình cũng giúp nhóm có thể giải thích, so sánh và tái lập một kết quả vận hành trong những lần thử nghiệm sau.
