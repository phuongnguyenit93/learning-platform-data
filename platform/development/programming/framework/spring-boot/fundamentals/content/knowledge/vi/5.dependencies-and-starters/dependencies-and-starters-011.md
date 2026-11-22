# Khác biệt cách chia starter, module giữa các dòng Spring Boot

Khi thêm một tính năng vào dự án Spring Boot, lập trình viên thường bắt đầu bằng một dependency như `spring-boot-starter-web` hay `spring-boot-starter-data-jpa`. Tuy nhiên, **tên starter, những thư viện nó kéo theo và vị trí mã auto-configuration không bất biến giữa các dòng Spring Boot**. Đặc biệt, Spring Boot 4 tổ chức lại nhiều thành phần thành các module nhỏ theo công nghệ và cung cấp starter kiểm thử tương ứng.

Bài này giải thích cách đọc cấu trúc dependency từ các thế hệ Spring Boot 1.x, 2.x, 3.x đến 4.x, tập trung vào **starter**, **module Spring Boot**, **module của Spring Framework**, **dependency management** và các hệ quả khi tạo mới hoặc nâng cấp ứng dụng.

> **Phạm vi phiên bản:** Các ví dụ tên artifact được đối chiếu theo quy ước của từng dòng chính, nhất là hướng dẫn chuyển đổi **Spring Boot 3 → 4.0**. Khi làm việc với một phiên bản con cụ thể, hãy kiểm tra tài liệu của chính phiên bản đó. Một starter đã đổi tên có thể còn tồn tại tạm thời dưới tên cũ để tương thích, không có nghĩa đó là tên nên dùng cho dự án mới.

## 1. Đừng nhầm starter, module và framework

Ba lớp tên thường gặp đều xuất hiện trong Gradle/Maven, nhưng chúng có trách nhiệm khác nhau.

| Loại artifact | Ví dụ | Trách nhiệm |
|---|---|---|
| **Starter** | `spring-boot-starter-web` (Boot 3), `spring-boot-starter-webmvc` (Boot 4) | Gom các dependency thường cần cho một loại ứng dụng; người dùng khai báo để chọn khả năng mong muốn. |
| **Module triển khai/hỗ trợ của Spring Boot** | `spring-boot-autoconfigure` (phổ biến ở Boot 2/3), `spring-boot-webmvc` (Boot 4) | Chứa mã do Spring Boot cung cấp, chẳng hạn auto-configuration, tích hợp framework và các API hỗ trợ. |
| **Module của Spring Framework** | `org.springframework:spring-webmvc`, `spring-context`, `spring-core` | Chứa khả năng nền tảng của Spring Framework: DI container, MVC, web abstraction, transaction... |
| **Thư viện bên thứ ba** | Hibernate, Jackson, Tomcat, Flyway | Triển khai công nghệ cụ thể; không phải module của Spring Boot chỉ vì Boot quản lý phiên bản của nó. |
| **BOM / dependency management** | `spring-boot-dependencies` | Quản lý tập phiên bản tương thích; bản thân BOM không tự kích hoạt web server hay tạo bean. |

**Starter không đồng nghĩa với module mã nguồn.** Nhiều starter chủ yếu là các khai báo phụ thuộc, còn hành vi runtime nằm ở module Spring Boot, Spring Framework hoặc thư viện khác. Ví dụ, thêm starter web đưa các thành phần liên quan vào classpath; lớp `DispatcherServlet` thuộc Spring MVC, còn Spring Boot giúp tự cấu hình ứng dụng khi đáp ứng các điều kiện.

Một starter cũng **không phải module Gradle/Maven do chính bạn tạo**. Nếu repository có các subproject `:api`, `:service` và `:data`, đó là cấu trúc nhiều module của ứng dụng; nó độc lập với cách Spring Boot chia các JAR nội bộ.

## 2. Vì sao Spring Boot cung cấp starter?

Nếu không có starter, ứng dụng web truyền thống phải tự khai báo nhiều thư viện và lựa chọn phiên bản tương thích:

- Spring Framework cho DI, HTTP và MVC.
- Servlet container hoặc web server phù hợp.
- Thư viện xử lý JSON khi trả/nhận JSON.
- Thư viện logging và những thành phần liên quan.
- Các phiên bản có thể hoạt động cùng nhau.

Starter làm việc như một **gói lựa chọn theo mục đích**. Nhà phát triển khai báo một tên có ý nghĩa, còn build tool resolve dependency graph tương ứng.

Một chuỗi khái niệm:

```text
Khai báo starter theo nhu cầu
        │
        ▼
Gradle/Maven resolve các dependency
        │
        ├── module hỗ trợ của Spring Boot
        ├── module Spring Framework
        ├── thư viện bên thứ ba
        └── dependency trung gian khác
        │
        ▼
Classpath lúc chạy
        │
        ▼
Spring Boot xét điều kiện auto-configuration
        │
        ▼
Các bean/tính năng thực sự được cấu hình
```

Sơ đồ là **mô hình trách nhiệm**, không phải cây dependency đầy đủ của một artifact cụ thể. Các cạnh transitive và tập module thực tế có thể thay đổi theo dòng Boot, dependency khác và cơ chế loại trừ.

Hai ý cần phân biệt:

1. **Có dependency** nghĩa là thư viện có mặt trên classpath theo cấu hình build.
2. **Tính năng hoạt động** còn phụ thuộc vào annotation, bean, cấu hình, loại ứng dụng và điều kiện auto-configuration.

Ví dụ, thêm starter JPA không tự tạo entity hoặc database đang hoạt động. Cần có datasource, driver, metadata entity và cấu hình tương ứng.

## 3. Lược đồ tiến hóa từ Spring Boot 1.x đến 4.x

| Dòng Spring Boot | Cách tổ chức nổi bật | Cách nhìn khi đọc `dependencies` |
|---|---|---|
| **1.x** | Phát triển mô hình starter theo tính năng, bootstrapping và auto-configuration; trọng tâm web servlet, data, security, actuator. | Tìm các starter lớn theo nhu cầu, rồi xem module/framework phía dưới. |
| **2.x** | Duy trì hệ starter; mở rộng các lựa chọn hiện đại như **WebFlux** và các starter công nghệ cụ thể. | Phân biệt rõ web servlet và reactive; không coi mọi ứng dụng web đều cùng một stack. |
| **3.x** | Dựa trên Spring Framework 6 và Jakarta EE; giữ nhiều tên starter quen thuộc của 2.x nhưng thay đổi baseline và nhiều dependency bên dưới. | Tên starter có thể giống 2.x, song code dùng `javax.*`/`jakarta.*` và phiên bản thư viện có thể khác đáng kể. |
| **4.x** | Tách nhiều mã hỗ trợ thành **module theo công nghệ**; chuẩn hóa thêm starter chính, starter test và tên package; một số starter đổi tên. | Xác định đúng starter mới, module chuyên biệt, test starter và import auto-configuration tương ứng. |

Bảng cho thấy **không thể đánh giá mức độ tương thích chỉ bằng cách nhìn tên starter**. Hai dự án đều ghi `spring-boot-starter-data-jpa` nhưng chạy trên Boot 2 và Boot 3 vẫn có thể khác JPA API, Spring Data, Hibernate và Java baseline.

### Spring Boot 1.x: starter là lối vào đơn giản

Thế hệ đầu làm nổi bật cách nghĩ theo loại ứng dụng: muốn web thì dùng starter web, muốn JDBC/JPA thì dùng starter data, muốn bảo mật thì dùng starter security. Lập trình viên ít phải lắp từng JAR bằng tay.

Thư viện Java và các module của Spring Framework vẫn tồn tại phía dưới. Spring Boot không thay thế Spring Framework; nó tạo trải nghiệm cấu hình và đóng gói thuận tiện hơn.

### Spring Boot 2.x: mở rộng theo mô hình lập trình

Dòng 2.x bổ sung lựa chọn reactive như `spring-boot-starter-webflux` (từ Boot 2.0), trong khi `spring-boot-starter-web` tiếp tục là lựa chọn quen thuộc cho Spring MVC trên servlet stack.

Một khác biệt quan trọng trong chính dòng 2.x: từ **2.3**, Bean Validation không còn được kéo vào theo cách trước đó bởi starter web. Với project cần validation, việc khai báo rõ `spring-boot-starter-validation` trở nên cần thiết. Đây là ví dụ cho thấy **chỉ cần nâng minor version cũng có thể thay đổi dependency transitively có sẵn**.

### Spring Boot 3.x: nhiều tên cũ, hệ sinh thái bên dưới thay đổi

Boot 3 chuyển sang Spring Framework 6, Java 17 trở lên và API Jakarta. Trong code dùng Servlet, Validation, JPA..., nhiều import `javax.*` thuộc Java EE cũ phải chuyển thành `jakarta.*` theo thư viện tương ứng.

Ví dụ:

```java
// Kiểu import thuộc Java EE cũ, thường gặp ở dự án Boot 2:
import javax.persistence.Entity;

// Kiểu import phù hợp với Jakarta Persistence trên Boot 3:
import jakarta.persistence.Entity;
```

Tên `spring-boot-starter-data-jpa` có thể giữ nguyên, nhưng không có nghĩa mã biên dịch trên Boot 2 tự động tương thích với Boot 3. Khi nâng cấp cần xem **cả API và dependency graph**, không chỉ tìm tên artifact nào bị đổi.

### Spring Boot 4.x: chia nhỏ module và gắn starter với công nghệ

Boot 4.0 tổ chức lại các module chính theo khả năng chuyên biệt. Thay vì giả định phần lớn auto-configuration đều tập trung trong một JAR lớn, bạn sẽ gặp các tên như:

- `spring-boot-webmvc` cho phần hỗ trợ Boot đối với Spring MVC.
- `spring-boot-webflux` cho phần hỗ trợ Boot đối với WebFlux.
- `spring-boot-data-jpa` cho phần hỗ trợ Boot đối với Spring Data JPA.
- `spring-boot-jackson` cho phần hỗ trợ Jackson.
- `spring-boot-flyway` cho phần hỗ trợ Flyway.
- `spring-boot-webmvc-test`, `spring-boot-data-jpa-test` cho hạ tầng kiểm thử chuyên biệt.

Quy ước đặt tên được tài liệu Boot 4.0 mô tả như sau:

```text
spring-boot-<technology>                   # Module hỗ trợ chính
org.springframework.boot.<technology>       # Package gốc tương ứng
spring-boot-starter-<technology>           # Starter chính
spring-boot-<technology>-test              # Module hỗ trợ test, khi có
spring-boot-starter-<technology>-test      # Starter test, khi có
```

Không phải mọi công nghệ đều có đủ từng loại artifact. Ví dụ một số starter web server không có một starter test tương ứng riêng. Hãy tra danh mục chính thức của phiên bản đang dùng thay vì tự ghép tên và giả định artifact tồn tại.

## 4. Bảng đối chiếu tên starter giữa Boot 3 và Boot 4

Bảng dưới đây tập trung vào những tên thường khiến dự án bị nhầm khi nâng từ 3.x lên 4.x.

| Nhu cầu | Tên thường dùng ở Spring Boot 3.x | Tên phù hợp theo Boot 4.x | Lưu ý |
|---|---|---|---|
| Spring MVC + HTTP server | `spring-boot-starter-web` | `spring-boot-starter-webmvc` | Tên `starter-web` được giữ nhưng **deprecated** ở Boot 4.0. |
| WebFlux | `spring-boot-starter-webflux` | `spring-boot-starter-webflux` | Tên chính giữ nguyên; thành phần Boot bên dưới được tổ chức lại. |
| Spring Data JPA | `spring-boot-starter-data-jpa` | `spring-boot-starter-data-jpa` | Tên chính giữ nguyên, nhưng integration/test modules khác. |
| JDBC | `spring-boot-starter-jdbc` | `spring-boot-starter-jdbc` | Starter công nghệ vẫn hiện diện qua các dòng. |
| Bean Validation | `spring-boot-starter-validation` | `spring-boot-starter-validation` | Cần khai báo khi dùng validation, không suy ra mọi web starter đều đủ. |
| Spring Security cơ bản | `spring-boot-starter-security` | `spring-boot-starter-security` | Kiểm thử Security có starter riêng ở Boot 4. |
| OAuth2 Client | `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` | Tên cũ được đánh dấu deprecated ở Boot 4. |
| OAuth2 Resource Server | `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` | Tên mới nhấn mạnh nhóm Security. |
| Spring Web Services | `spring-boot-starter-web-services` | `spring-boot-starter-webservices` | Tên cũ deprecated ở Boot 4. |
| Spring GraphQL | `spring-boot-starter-graphql` | `spring-boot-starter-graphql` | Có module Boot theo công nghệ và test companion rõ ràng. |
| Flyway migration | Thường khai báo `org.flywaydb:flyway-core` trực tiếp | `spring-boot-starter-flyway` | Boot 4 yêu cầu chú ý starter riêng để có tích hợp Boot thích hợp. |
| Liquibase migration | Thường khai báo `org.liquibase:liquibase-core` trực tiếp | `spring-boot-starter-liquibase` | Cần rà soát starter theo dòng Boot. |

**Deprecated không có nghĩa là bị xóa ngay.** Tài liệu Boot 4.0 xác nhận một số tên starter cũ còn được cung cấp để chuyển đổi dần, nhưng nên sử dụng tên thay thế khi chỉnh build của dự án Boot 4. Không nên suy ra rằng mọi starter cũ đều được giữ dưới dạng alias.

### Ví dụ: chỉ nhìn tên Web starter đã thấy khác biệt

Trong ứng dụng Spring MVC Boot 3, khai báo Gradle phổ biến là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Với dự án Boot 4 dùng Spring MVC:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
}
```

Điều được thay đổi là **tên lựa chọn và tổ chức dependency tương ứng**. Controller dùng `@RestController`, `@GetMapping` vẫn thuộc mô hình Spring MVC; đổi starter không đồng nghĩa phải viết lại mọi controller.

Nhưng việc nâng major version **có thể đòi hỏi** sửa API, package, cấu hình hoặc thư viện khác. Không nên dùng ví dụ đổi một dòng dependency như một cam kết toàn bộ ứng dụng sẽ tương thích sau khi nâng cấp.

## 5. Từ module hỗ trợ rộng sang module theo công nghệ

Ở Boot 2 và Boot 3, hai artifact hay gặp là:

- `org.springframework.boot:spring-boot`: những lớp lõi và API chính của Boot.
- `org.springframework.boot:spring-boot-autoconfigure`: tập hợp rộng các auto-configuration.

Ở Boot 4, nhiều phần hỗ trợ công nghệ được chuyển vào các module có tên rõ ràng. Cách nhìn này đặc biệt hữu ích khi đọc một stack trace hoặc tìm class đã di chuyển:

| Vấn đề bạn đang tìm | Ví dụ module chuyên biệt ở Boot 4 | Vai trò |
|---|---|---|
| Tích hợp Spring MVC | `spring-boot-webmvc` | Phần hỗ trợ và cấu hình Boot cho Spring MVC. |
| WebFlux | `spring-boot-webflux` | Phần hỗ trợ Boot cho reactive web stack. |
| Spring Data JPA | `spring-boot-data-jpa` | Tích hợp Boot với Spring Data JPA. |
| HTTP client không reactive | `spring-boot-restclient` | Tích hợp Boot cho `RestClient`/`RestTemplate`. |
| Reactive WebClient | `spring-boot-webclient` | Tích hợp Boot cho `WebClient`. |
| Caching | `spring-boot-cache` | Hỗ trợ auto-configuration liên quan caching. |
| Security | `spring-boot-security` | Hỗ trợ Boot cho Spring Security. |
| Jackson | `spring-boot-jackson` | Tích hợp Jackson theo phiên bản Boot 4. |

Ví dụ `spring-boot-webmvc` **không phải** là tên thay thế của thư viện Spring MVC gốc `org.springframework:spring-webmvc`. Hai artifact thuộc **hai dự án và hai trách nhiệm**: Spring Framework cung cấp khả năng MVC; Spring Boot cung cấp việc tích hợp và auto-configuration theo quy ước.

Trong tài liệu và lỗi build, nên xác định cả **group ID**:

```text
org.springframework.boot:spring-boot-webmvc      # Module của Spring Boot 4
org.springframework:spring-webmvc                # Module của Spring Framework
org.springframework.boot:spring-boot-starter-webmvc  # Starter của Spring Boot 4
```

Hai thành phần có chữ `webmvc` trong tên không nhất thiết hoán đổi trực tiếp được.

## 6. Tách riêng Web MVC, WebFlux và HTTP client

Một điểm dễ nhầm là nghĩ mọi thứ liên quan HTTP đều phải đi cùng một starter web. Thực tế có ít nhất ba nhu cầu:

1. **Server Spring MVC**: phục vụ request theo Spring MVC servlet stack.
2. **Server WebFlux**: ứng dụng reactive theo Spring WebFlux.
3. **HTTP client**: một ứng dụng gọi API bên ngoài, không nhất thiết tự mở web server.

Ở Boot 3, ứng dụng cần `WebClient` thường thêm `spring-boot-starter-webflux`, kể cả khi chỉ muốn dùng client. Boot 4 có các starter riêng cho HTTP client nhằm diễn đạt rõ nhu cầu:

| Nhu cầu | Starter Boot 4 |
|---|---|
| Server Spring MVC | `spring-boot-starter-webmvc` |
| Server WebFlux | `spring-boot-starter-webflux` |
| HTTP client kiểu imperative (ví dụ `RestClient`) | `spring-boot-starter-restclient` |
| HTTP client reactive (`WebClient`) | `spring-boot-starter-webclient` |

Điều này giúp tránh suy luận rằng **dùng client HTTP là phải xây một web server**. Một job chạy theo lịch, một consumer message hoặc CLI application vẫn có thể gọi HTTP API nhưng không mở cổng phục vụ request.

Nếu code vẫn dùng các API `RestTemplate`, `RestClient` hay `WebClient`, cần chọn starter tương thích với **API và dòng Boot**, thay vì chỉ tìm tên phụ thuộc có từ “web”.

## 7. Starter kiểm thử cũng thay đổi cách chia

Ở Boot 2/3, `spring-boot-starter-test` là dependency thường gặp cho JUnit, AssertJ, Spring Test, MockMvc-related testing utilities tùy phiên bản và dependency graph. Một số công nghệ chuyên biệt vẫn phải bổ sung dependency test riêng, ví dụ `spring-security-test`.

Boot 4 tiếp tục có starter test cơ bản nhưng bổ sung **test starter theo công nghệ**, chẳng hạn:

| Công nghệ cần kiểm thử | Starter test Boot 4 |
|---|---|
| Spring MVC | `spring-boot-starter-webmvc-test` |
| Spring WebFlux | `spring-boot-starter-webflux-test` |
| Spring Data JPA | `spring-boot-starter-data-jpa-test` |
| Spring Security | `spring-boot-starter-security-test` |
| Spring GraphQL | `spring-boot-starter-graphql-test` |
| Spring JDBC | `spring-boot-starter-jdbc-test` |

Các test starter chuyên biệt của Boot 4 thường kéo `spring-boot-starter-test` theo dependency bắc cầu. Vì vậy, nếu đã chọn đúng test starter theo công nghệ, không nhất thiết phải khai báo thêm `spring-boot-starter-test` trực tiếp.

Đây là **khác biệt thiết kế đáng nhớ**, không chỉ là một tên khác. Trong Boot 4, việc thêm trực tiếp một thư viện test như `spring-security-test` mà thiếu starter tích hợp tương ứng có thể không mang đủ auto-configuration/hạ tầng test mà bạn mong đợi.

### Ví dụ phụ thuộc kiểm thử theo thế hệ

Một dự án **Boot 3** dùng Spring MVC, JPA và Security thường có các khai báo kiểu:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Dự án **Boot 4** tương ứng có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-jpa-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-test'
}
```

Các đoạn trên chỉ minh họa **thành phần dependency**, giả định project đã được cấu hình Spring Boot plugin và dependency management/BOM tương thích với phiên bản tương ứng. Driver database, cấu hình datasource, bộ test và các thư viện khác phải được bổ sung theo ứng dụng thật.

Trong cả hai phiên bản, annotation `@SpringBootTest` không tự biến thành bộ kiểm thử đầy đủ. Cần chọn các kiểu test phù hợp như unit test, `@WebMvcTest` hoặc `@DataJpaTest` khi có công cụ/hạ tầng hỗ trợ.

## 8. Với database migration, phụ thuộc bên thứ ba có thể chưa đủ

Flyway và Liquibase là ví dụ quan trọng khi chuyển từ Boot 3 lên Boot 4.

Với **Boot 3**, ứng dụng thường khai báo thư viện bên thứ ba trực tiếp:

```groovy
dependencies {
    implementation 'org.flywaydb:flyway-core'
    // Hoặc:
    // implementation 'org.liquibase:liquibase-core'
}
```

Spring Boot 3 có thể tự cấu hình hỗ trợ theo dependency và cấu hình hiện diện. Khi sang **Boot 4**, cấu trúc module tách riêng khiến hướng dẫn migration yêu cầu chú ý **starter của Spring Boot**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-flyway'
    // Hoặc:
    // implementation 'org.springframework.boot:spring-boot-starter-liquibase'
}
```

Không nên chỉ copy nguyên `flyway-core` từ build cũ rồi giả định mọi auto-configuration của Boot 4 sẽ sẵn sàng như trước. Ngoài starter, Flyway có thể cần các module riêng cho loại database đang sử dụng; cần kiểm tra thêm theo phiên bản và DBMS.

Tương tự, việc Boot quản lý phiên bản của một thư viện **không có nghĩa cứ thêm thư viện đó là mọi tích hợp Boot đều xuất hiện**. BOM và starter có mục tiêu khác nhau.

## 9. Sự thay đổi về JSON: chú ý Jackson 2 và Jackson 3

Trong Boot 3, Jackson 2 là lựa chọn JSON phổ biến của hệ sinh thái web; các package thường dùng có tiền tố `com.fasterxml.jackson`. Boot 4 ưu tiên **Jackson 3**, với nhiều module và package chuyển sang `tools.jackson`.

Ví dụ ý tưởng về tên import:

```java
// Jackson 2, phổ biến trong các ứng dụng Boot 3:
import com.fasterxml.jackson.databind.ObjectMapper;

// Với Jackson 3, các API tương ứng được tổ chức lại
// trong namespace tools.jackson; cần theo đúng API mới,
// không thay mọi chuỗi package một cách máy móc.
```

Boot 4 có `spring-boot-jackson` và `spring-boot-starter-jackson` cho hỗ trợ Jackson. Nhưng việc có starter liên quan JSON **không đồng nghĩa** mọi code tự viết cho Jackson 2 đều tương thích nhị phân hoặc tương thích nguồn với Jackson 3.

Khi dự án dùng Jackson trực tiếp (custom serializer, deserializer, module, ObjectMapper, configuration), cần đọc hướng dẫn nâng cấp Jackson 3. Một ứng dụng chỉ dùng controller nhận/trả DTO JSON thường ít tiếp xúc với chi tiết này hơn ứng dụng cấu hình sâu Jackson, nhưng vẫn nên chạy test serialize/deserialize.

## 10. Boot 4 có “classic starter” để chuyển đổi từng bước

Sau khi tách module, ứng dụng lớn sử dụng các class Boot ở mức thấp có thể gặp import không còn nằm trên classpath giống trước. Boot 4.0 cung cấp một bước trung gian:

- `spring-boot-starter-classic`
- `spring-boot-starter-test-classic`

Các classic starter giúp đưa vào classpath một bộ module gần với cách tổ chức của thế hệ trước, hỗ trợ sửa ứng dụng và kiểm chứng việc chạy. **Chúng được khuyến nghị là cầu nối migration**, không phải cấu hình cuối cùng lý tưởng cho mọi dự án Boot 4.

Một tiến trình chuyển đổi có kiểm soát:

1. Xác định phiên bản Java và Spring Boot của dự án; chốt baseline test/build hiện có.
2. Đọc migration guide và cập nhật build plugin, dependency management, starter tên cũ.
3. Nếu cần, tạm dùng classic starter để xử lý các class/import đã di chuyển và chạy lại chương trình.
4. Chuyển dần sang starter theo công nghệ, quan sát dependency graph.
5. Loại classic starter khi đã xác minh các dependency cần thiết được khai báo rõ.
6. Kiểm tra test, HTTP endpoint, security, database migration và behavior runtime.

Tránh lạm dụng classic starter để che giấu một dependency thiếu: nó có thể làm ứng dụng chạy tạm nhưng khiến người bảo trì khó biết công nghệ nào thực sự cần thiết.

## 11. Dependency management: một artifact giống nhau vẫn có thể mang phiên bản khác

Spring Boot công bố BOM `org.springframework.boot:spring-boot-dependencies` quản lý nhiều phiên bản thư viện tương thích. Starter diễn tả **công nghệ cần dùng**; BOM quyết định **phiên bản được quản lý** cho các dependency thuộc phạm vi của nó.

Ví dụ dự án Gradle đã import BOM và dùng plugin phù hợp có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

Ở đây không ghi version của starter vì cơ chế dependency management đã cung cấp version. Một cách dùng BOM thuần Gradle là:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.0.0')
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

Đoạn này minh họa **phần quản lý dependency**, không phải build file hoàn chỉnh. Dự án dùng plugin Spring Boot cũng cần cấu hình plugin, Java và các task tương ứng. Không nên import đồng thời hai BOM thuộc hai dòng Boot khác nhau hoặc tự ép một số thư viện nền về thế hệ không tương thích.

Nếu sử dụng Maven, phiên bản thường được quản lý qua `spring-boot-starter-parent` hoặc import BOM trong `dependencyManagement`. Gradle có thể dùng `io.spring.dependency-management` hoặc `platform(...)` theo cấu hình build. Các lựa chọn này không làm thay đổi sự khác nhau giữa **starter và module**.

### Vì sao phải xem dependency graph thay vì chỉ file build?

File build chỉ hiển thị dependency **khai báo trực tiếp**; bản đồ runtime còn có các dependency **transitive**.

```text
Bạn khai báo:
spring-boot-starter-webmvc
         │
         ▼
Một tập thư viện web, Spring, Boot integration,
server, serialization... được resolve theo phiên bản
         │
         ▼
Thực tế classpath phụ thuộc:
BOM + dependency conflict resolution + exclusions
+ profile/configuration + phiên bản Boot
```

Vì vậy, hai build có cùng một dòng starter vẫn có thể khác hành vi khi BOM, exclusion hoặc dependency bổ sung khác nhau.

## 12. Cách xem dependency thực tế của dự án

### Với Gradle

Ở thư mục chứa wrapper của project:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để biết **vì sao** một module cụ thể xuất hiện (ví dụ với Boot 4):

```bash
./gradlew dependencyInsight \
  --dependency spring-boot-webmvc \
  --configuration runtimeClasspath
```

Trong Windows PowerShell, bạn có thể viết thành một dòng:

```powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-webmvc --configuration runtimeClasspath
```

Các lệnh đọc dependency graph **đúng project/configuration**. Nếu repository nhiều module, cần chỉ định subproject tương ứng, ví dụ `:app:dependencies`. Tên artifact `spring-boot-webmvc` chỉ mang tính minh họa cho dự án Boot 4 có webmvc; không nên chạy truy vấn đó để kết luận ở một project Boot 2/3.

Để xem dependency lúc compile hoặc test:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Một thư viện có mặt ở `testRuntimeClasspath` không đảm bảo nó tồn tại trên runtime classpath của ứng dụng sau khi đóng gói.

### Với Maven

```bash
./mvnw dependency:tree
```

Hoặc giới hạn nhóm Spring Boot:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot
```

Kết quả giúp kiểm tra đâu là dependency trực tiếp, đâu là transitive và version nào được chọn. Khi dự án chuyển Boot 3 → 4, nên so sánh ít nhất **runtime** và **test** dependency graph trước/sau.

### Đọc artifact bằng tọa độ đầy đủ

Đừng chỉ so sánh `spring-webmvc` với `spring-boot-webmvc` bằng vài chữ trong tên; luôn nhìn đủ:

```text
groupId:artifactId:version

org.springframework:spring-webmvc:<spring-framework-version>
org.springframework.boot:spring-boot-webmvc:<spring-boot-version>
org.springframework.boot:spring-boot-starter-webmvc:<spring-boot-version>
```

Các dấu `<...>` ở đây là chỗ giữ chỗ cho version thực tế, không phải văn bản nhập nguyên vào lệnh build.

## 13. Auto-configuration phụ thuộc classpath nhưng không tương đương starter

Spring Boot kích hoạt nhiều auto-configuration theo **điều kiện**: class có hiện diện, bean có tồn tại, ứng dụng có loại web phù hợp, property bật/tắt tính năng hay không...

Ví dụ một auto-configuration có thể chỉ được áp dụng khi có thư viện JDBC và datasource phù hợp. Nếu thiếu class cần thiết, điều kiện sẽ không thỏa; nếu đã có bean do ứng dụng tự cung cấp, auto-configuration có thể lùi lại.

Một starter giúp đưa **những class cần thiết** vào môi trường, nhưng không thể thay cho mọi cấu hình runtime. Khi một bean dự kiến không xuất hiện, cần xem:

- Dependency chính và các dependency transitive có đúng phiên bản?
- Class/module hỗ trợ Boot có nằm trên runtime classpath?
- Auto-configuration nào được áp dụng, bị loại hoặc chưa đủ điều kiện?
- Có bean tự định nghĩa khiến Boot không tạo bean mặc định?
- Property, profile, application type hoặc điều kiện môi trường có ảnh hưởng không?

Có thể khởi chạy ứng dụng trong môi trường phát triển với tùy chọn `--debug` để xem **conditions evaluation report**. Báo cáo này giúp hiểu auto-configuration, nhưng không tự chứng minh toàn bộ cấu hình ứng dụng đúng.

Khi nâng cấp Boot 4, một class từng có trong package auto-configuration rộng ở Boot 3 có thể được chuyển sang package module cụ thể. Nếu ứng dụng import trực tiếp class nội bộ của Boot, hãy tra API và migration guide; đừng mặc định thiếu starter là lỗi duy nhất.

## 14. Những lỗi thường gặp khi nâng dòng Spring Boot

| Hiện tượng | Điều cần điều tra | Cách xử lý phù hợp |
|---|---|---|
| Code dùng Boot 3, sau nâng Boot 4 không tìm thấy một class Boot | Module/package đã đổi, dependency chưa được khai báo rõ | Xem migration guide, tìm module và package mới, thêm starter đúng công nghệ nếu cần. |
| Boot 4 vẫn khai báo `spring-boot-starter-web` | Dùng starter cũ đã deprecated | Chuyển sang `spring-boot-starter-webmvc` khi ứng dụng dùng Spring MVC. |
| Sau nâng cấp, test Security dùng `@WithMockUser` lỗi | Hạ tầng Security test chưa được tích hợp đủ | Kiểm tra `spring-boot-starter-security-test` ở Boot 4. |
| Sau nâng Boot 4, Flyway không chạy như dự kiến | Chỉ giữ dependency Flyway cũ; thiếu module tích hợp Boot | Xem `spring-boot-starter-flyway` và driver/module DB tương ứng. |
| Dự án có cả starter MVC và WebFlux, không rõ mô hình web | Hai công nghệ khác nhau cùng trên classpath | Xác định server stack mong muốn; kiểm tra loại ứng dụng và cấu hình. |
| Nâng 2.x lên 3.x gây lỗi `javax.persistence` hoặc `javax.servlet` | Chuyển sang Jakarta EE | Đổi API/import và dependency tương thích, cập nhật thư viện liên quan. |
| `NoClassDefFoundError` khi runtime | Classpath thực tế thiếu hoặc version không tương thích | Dùng dependency tree, kiểm tra exclusion và runtime configuration. |
| Dependency version bị thay đổi ngoài dự kiến | BOM xung đột, override thủ công hoặc giải quyết version của build tool | Kiểm tra dependency insight/tree và quy tắc quản lý phiên bản. |
| Dùng module Boot trực tiếp nhưng auto-config không có đủ | Không dùng starter mà thiếu dependency tích hợp liên quan | Xem starter chính thức hoặc tự khai báo đầy đủ module có chủ đích. |

### Một ví dụ migration nhỏ nhưng có nhiều lớp

Giả sử một service Boot 3 có endpoint MVC, đăng nhập OAuth2 và Flyway:

```groovy
// Dependencies trong ứng dụng Boot 3
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.flywaydb:flyway-core'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Khi chuyển sang Boot 4, các lựa chọn theo tên mới sẽ là:

```groovy
// Dependencies minh họa cho ứng dụng đã chuyển sang Boot 4
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-flyway'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client-test'
}
```

Đây là **bản đồ các dependency cần xem xét**, không phải công thức nâng cấp hoàn chỉnh. Bạn vẫn phải xét Java target, Spring Framework version, security configuration, kết nối database, driver, migration script và các thư viện khác.

## 15. Bài tập đọc starter/module thực tế

### Bài tập 1: Phân biệt starter với module

Trong file `build.gradle` hoặc `pom.xml`, tìm một starter đang được khai báo. Với dependency tree, ghi ra ba lớp:

1. Starter được khai báo trực tiếp.
2. Một module tích hợp Spring Boot có mặt transitively.
3. Một module của Spring Framework hoặc thư viện bên thứ ba mà starter sử dụng.

Giải thích tại sao ba lớp không thể được xem là cùng một artifact.

### Bài tập 2: So sánh Spring MVC trên Boot 3 và Boot 4

Tạo hai project thử nghiệm riêng bằng phiên bản Spring Boot tương ứng, một dự án Boot 3 dùng `spring-boot-starter-web` và một dự án Boot 4 dùng `spring-boot-starter-webmvc`. Mỗi project có một `@RestController` trả về chuỗi cho `GET /hello`.

So sánh:

- Tên starter khai báo trong build file.
- Danh sách module `org.springframework.boot` trong runtime dependency tree.
- Thư viện `spring-webmvc` của Spring Framework.
- Cách endpoint hoạt động sau khi chạy đúng Java/runtime theo phiên bản.

Mục tiêu là thấy **trách nhiệm MVC giữ cùng khái niệm** trong khi cách tổ chức artifact của Boot thay đổi.

### Bài tập 3: Quan sát test starter của Boot 4

Với project Boot 4 có Spring MVC, thêm `spring-boot-starter-webmvc-test` và quan sát `testRuntimeClasspath`. Xác định `spring-boot-starter-test` có được kéo vào qua dependency bắc cầu hay không. Sau đó thử viết một test HTTP cho controller của bạn.

### Bài tập 4: Kiểm tra auto-configuration

Tạo ứng dụng với dependency JDBC/JPA thích hợp. Chạy với `--debug` và xem conditions evaluation report. Xác định những auto-configuration liên quan datasource có điều kiện gì. Nếu ứng dụng thiếu database hoặc driver, ghi nhận lỗi/thông báo tương ứng và phân biệt **lỗi cấu hình kết nối** với **thiếu starter/module**.

### Bài tập 5: Lập bảng khi nâng cấp

Chọn một dự án Boot 3 có ít nhất ba starter. Trước khi đổi phiên bản, tạo bảng:

| Dependency hiện tại | Nhóm tính năng | Tên theo Boot 4 | Có thay test starter? | Cần kiểm tra thêm |
|---|---|---|---|---|
| `spring-boot-starter-web` | MVC | `spring-boot-starter-webmvc` | `webmvc-test` | Controller, serialization, server |
| `spring-boot-starter-data-jpa` | Persistence | Giữ tên chính | `data-jpa-test` | Jakarta, JPA, Hibernate, driver |
| `spring-boot-starter-security` | Security | Giữ tên chính | `security-test` | Authentication, filter chain |

Dùng dependency tree và migration guide của phiên bản đích để bổ sung những hàng chưa rõ. Không tự thay toàn bộ tên theo một quy tắc chuỗi khi chưa kiểm tra artifact thực có tồn tại.

## 16. Các nguyên tắc cần nhớ

1. **Starter là lựa chọn tính năng**, còn module là nơi chứa mã thực thi/tích hợp. BOM là nguồn quản lý phiên bản; ba đối tượng giải quyết ba vấn đề khác nhau.
2. **Boot 1/2 đặt nền cho mô hình starter**; Boot 2 có nhiều lựa chọn như WebFlux; Boot 3 thay đổi baseline Spring Framework/Jakarta dù nhiều tên starter không đổi.
3. **Boot 4.0 chia Spring Boot thành nhiều module công nghệ**, chuẩn hóa tên starter và bổ sung test starter chuyên biệt; một số tên Boot 3 vẫn còn nhưng deprecated.
4. **Không suy luận dependency chỉ từ tên**: phải nhìn tọa độ `group:artifact:version`, runtime/test classpath và các dependency transitively được resolve.
5. **Migration qua major version là công việc của toàn dependency graph và API**, bao gồm Java, Spring Framework, Jakarta/Jackson, auto-configuration, test và thư viện khác.
6. **Chọn starter đúng dòng Boot** trước khi viết code giúp tránh lỗi classpath, auto-configuration và cấu hình mơ hồ về sau.

### Tài liệu chính thức để tra cứu

- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) — danh sách module, starter, test starter, tên deprecated và hướng dẫn chuyển từ Boot 3.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide) — các thay đổi lớn từ Boot 2 sang Boot 3, trong đó có Jakarta EE.
- [Spring Boot Reference — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — danh sách starter được tài liệu chính thức công bố theo phiên bản đang truy cập.
- [Spring Initializr](https://start.spring.io/) — chọn dòng Boot và dependency để tạo một project đối chiếu thực tế.

Khi đọc hoặc nâng cấp một dự án, hãy bắt đầu từ câu hỏi **“Ứng dụng cần công nghệ nào, trên dòng Spring Boot nào?”**, chọn starter đúng dòng đó, rồi xác nhận những module và thư viện thực tế bằng dependency graph. Cách tiếp cận này hữu ích hơn việc ghi nhớ cứng một danh sách tên starter qua mọi phiên bản.
