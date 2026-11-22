# Đọc tài liệu đúng dòng Spring Boot và phiên bản Spring Framework

Trong quá trình học và phát triển ứng dụng Spring Boot, một lỗi rất dễ gặp là **làm theo hướng dẫn viết cho phiên bản khác với phiên bản mà dự án đang chạy**. Ví dụ, bạn đọc một bài viết dùng `javax.servlet.*` nhưng mã nguồn của dự án chỉ chấp nhận `jakarta.servlet.*`; hoặc bạn thấy ví dụ cấu hình bảo mật bằng `WebSecurityConfigurerAdapter` trong khi lớp đó không còn tồn tại ở dòng Spring Security mà dự án sử dụng. Đôi khi đoạn mã sao chép vẫn biên dịch nhưng hành vi mặc định hoặc cách cấu hình đã thay đổi.

Để đọc tài liệu chính xác, cần trả lời ba câu hỏi theo thứ tự:

1. **Ứng dụng đang sử dụng dòng và bản vá Spring Boot nào?**
2. **Phiên bản Spring Framework và các thư viện Spring liên quan thực sự được giải quyết là gì?**
3. **Trang tài liệu, ví dụ API và hướng dẫn chuyển đổi đang nói về đúng dòng phiên bản đó không?**

Bài học này trình bày cách xác định phiên bản, chọn đúng tài liệu chính thức, đối chiếu dependency thực tế, nhận diện hướng dẫn cũ và hình thành quy trình tra cứu có thể áp dụng cho cả dự án Gradle lẫn Maven.

## 1. Trước hết, phân biệt Spring Boot và Spring Framework

**Spring Framework** cung cấp nền tảng cốt lõi của hệ sinh thái Spring: IoC container, Dependency Injection, bean lifecycle, transaction, Spring MVC, Spring WebFlux và nhiều API khác. **Spring Boot** xây trên Spring Framework, cung cấp cách khởi động ứng dụng, starter dependencies, auto-configuration, dependency management và công cụ vận hành.

Chúng có **số phiên bản độc lập**. Phiên bản Spring Boot `3.3.5` không có nghĩa ứng dụng đang chạy Spring Framework `3.3.5`. Chẳng hạn, **dòng Spring Boot 3.3.x** được xây trên **dòng Spring Framework 6.1.x**; bản vá Framework cụ thể phụ thuộc vào phiên bản Boot/BOM và cách giải quyết dependency trong dự án.

~~~text
Ứng dụng
  │
  ├── Spring Boot 3.3.x            ← dòng Boot dùng để chọn tài liệu Boot
  │     ├── spring-boot-autoconfigure
  │     ├── spring-boot-starter-*
  │     └── Spring Boot dependency management
  │
  ├── Spring Framework 6.1.x       ← dòng Framework dùng để chọn tài liệu API
  │     ├── spring-core / spring-context
  │     ├── spring-web / spring-webmvc
  │     └── spring-tx / ...
  │
  ├── Spring Data ...              ← dòng phát hành riêng, thường do Boot quản lý
  └── Spring Security ...          ← dòng phát hành riêng, thường do Boot quản lý
~~~

Sơ đồ là **ví dụ về quan hệ phiên bản**, không phải bảng tra chính xác các bản vá. Spring Boot còn quản lý nhiều thư viện bên ngoài Spring như Jackson, Hibernate, Logback và driver. Không thể suy ra phiên bản tất cả các thành phần chỉ từ cách đặt tên của Boot.

### 1.1. Dòng phiên bản là gì?

Với số phiên bản dạng `MAJOR.MINOR.PATCH`:

| Phần | Ví dụ ở `3.3.5` | Ý nghĩa khi tra tài liệu |
|---|---|---|
| Major | `3` | Có thể gắn với thay đổi nền tảng, yêu cầu Java và API không tương thích ngược. |
| Minor | `3` thứ hai | Xác định dòng tính năng, cấu hình và phiên bản framework đi kèm. |
| Patch | `5` | Chủ yếu là sửa lỗi/cải thiện tương thích; vẫn có thể chứa thay đổi hành vi cần đọc release notes. |

Trong thực tế, hãy xác định **cả bản đầy đủ** đang dùng (`3.3.5`) và **dòng tài liệu** tương ứng (`3.3.x`). Nếu cần tìm một API hoặc bug fix xuất hiện trong bản vá cụ thể, phải xem thêm tài liệu/changelog của đúng bản vá, thay vì chỉ đọc trang chung của dòng 3.3.

Các nhãn `SNAPSHOT`, `M1`, `RC1` hay bản phát hành cuối cùng cũng có ý nghĩa: tài liệu dành cho snapshot/milestone/release candidate có thể mô tả API chưa ổn định. Không áp dụng hướng dẫn từ bản thử nghiệm cho một bản ổn định mà không đối chiếu lại.

### 1.2. Boot quản lý phiên bản, nhưng không bảo đảm mọi dự án đều giống nhau

Spring Boot công bố **`spring-boot-dependencies` BOM** (Bill of Materials) để chỉ định bộ phiên bản thư viện đã được phối hợp cho một bản Boot. Dự án thường sử dụng BOM trực tiếp hoặc gián tiếp qua plugin/parent.

Tuy nhiên, phiên bản hiệu lực có thể khác BOM mặc định nếu:

- Dự án khai báo phiên bản riêng của một dependency.
- Một BOM hoặc dependency platform khác tham gia vào quy trình giải quyết phiên bản.
- Gradle/Maven áp dụng quy tắc phiên bản, constraint, force, resolution strategy hoặc override của tổ chức.
- Module trong dự án nhiều module có cấu hình dependency riêng.

Vì vậy, phải phân biệt **phiên bản mong đợi từ Spring Boot BOM** với **phiên bản thực sự có trên dependency graph**. Cái thứ hai mới quyết định API mà compiler và runtime sử dụng.

## 2. Phân loại đúng loại tài liệu cần đọc

Một câu hỏi về Spring có thể cần nhiều nguồn tài liệu khác nhau:

| Bạn đang cần biết | Nguồn ưu tiên | Điều cần khớp |
|---|---|---|
| Boot tự tạo bean nào, thuộc tính cấu hình nào, starter hoạt động ra sao? | **Spring Boot Reference Documentation** | Dòng Spring Boot của ứng dụng |
| Cách dùng `ApplicationContext`, `@Transactional`, Spring MVC hoặc WebFlux? | **Spring Framework Reference Documentation** | Dòng Spring Framework được giải quyết |
| Chữ ký, overload, annotation, trạng thái deprecated của một class/method? | **Javadoc API** của artifact đó | Phiên bản API cụ thể, tốt nhất cùng bản vá |
| Repository Spring Data JPA/JDBC/R2DBC hoạt động như thế nào? | **Spring Data module reference** | Module và release train/phiên bản thực tế |
| `SecurityFilterChain`, OAuth2, request authorization hay reactive security? | **Spring Security reference** | Dòng Spring Security thực tế |
| Có breaking changes, cấu hình mới hoặc hành vi thay đổi sau nâng cấp? | **Release Notes / Migration Guide / Upgrade Notes** | Cặp phiên bản nguồn → đích |
| Phiên bản transitive nào được kéo vào dự án? | **Dependency report / effective build configuration** | Artifact và configuration đang chạy |
| Một lỗi đã sửa ở bản nào? | **Issue, changelog, release notes** có liên kết bản phát hành | Phiên bản có sửa lỗi và điều kiện tái hiện |

Một số điểm truy cập chính thức có thể bắt đầu từ:

- Spring Boot: https://docs.spring.io/spring-boot/reference/
- Spring Framework: https://docs.spring.io/spring-framework/reference/
- Spring Security: https://docs.spring.io/spring-security/reference/
- Spring Data: https://spring.io/projects/spring-data
- Danh mục dự án và các nhánh tài liệu: https://spring.io/projects

**Chú ý:** Đường dẫn gốc `/reference/` thường hướng tới tài liệu đang được công bố mặc định tại thời điểm truy cập. Nếu dự án dùng một dòng cũ, hãy dùng bộ chọn **Versions** trên trang tài liệu hoặc liên kết theo nhánh phiên bản. Không kết luận rằng nội dung mới nhất là nội dung đúng cho ứng dụng hiện tại chỉ vì trang đó xuất hiện đầu tiên trên công cụ tìm kiếm.

Tài liệu chính thức đôi khi đặt tại những cấu trúc URL khác nhau qua các đời phát hành. Cần kiểm tra **tiêu đề phiên bản hiển thị trên chính trang** thay vì đoán phiên bản bằng một URL tự ghép. Đặc biệt, link Javadoc và đường dẫn archive có thể khác trang reference.

## 3. Xác định Spring Boot đang dùng trong dự án

### 3.1. Dự án Gradle: xem phiên bản plugin và cấu hình dependency

Ví dụ một ứng dụng Spring Boot **3.3.5** dùng Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ở ví dụ này, `3.3.5` là **phiên bản plugin Spring Boot**; khi kết hợp plugin dependency management như trên, BOM tương ứng được áp dụng cho các dependency được quản lý. Phiên bản `1.1.6` thuộc plugin `io.spring.dependency-management`, **không phải phiên bản Spring Framework**.

Trong dự án thực tế, phiên bản plugin có thể nằm ở nơi khác, chẳng hạn:

- `settings.gradle` / `settings.gradle.kts` qua `pluginManagement`;
- `gradle/libs.versions.toml` qua version catalog và plugin alias;
- `gradle.properties` hoặc build convention plugin riêng;
- BOM nhập bằng `platform(...)` hoặc `enforcedPlatform(...)`, không nhất thiết qua plugin dependency-management.

Vì thế, nếu `build.gradle` chỉ ghi `alias(libs.plugins.spring.boot)`, cần tra alias để biết version được khai báo. Nếu một module khai báo dependencies nhưng không áp dụng Boot plugin, phải xem thiết lập BOM/dependency management thực tế của module đó.

### 3.2. Dự án Maven: xem parent hoặc BOM nhập vào

Một ứng dụng Maven thường kế thừa parent của Boot:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Khi không dùng `spring-boot-starter-parent`, dự án có thể import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Hai cấu hình trên minh họa **hai cách tổ chức dự án khác nhau**, không phải hai khối bắt buộc đặt đồng thời trong cùng một POM. Parent còn cung cấp một số mặc định build/plugin bên cạnh dependency management; import BOM chỉ đưa vào phần quản lý dependency của BOM.

### 3.3. Phân biệt bản khai báo với bản hiệu lực

Đọc `pom.xml` hoặc `build.gradle` cho biết **dự án chủ định dùng gì**. Nhưng chính **resolved dependency graph** cho biết **trình biên dịch và runtime nhận phiên bản nào**. Điều này đặc biệt quan trọng nếu gặp những trường hợp như:

~~~text
Ứng dụng khai báo:
  Spring Boot plugin: 3.3.5

Một dependency khác hoặc quy tắc quản lý phiên bản:
  yêu cầu spring-core theo phiên bản riêng

Kết quả cần kiểm tra:
  spring-core, spring-context, spring-webmvc...
  thực sự được resolve về những phiên bản nào?
~~~

Không nên chỉ lấy số plugin và suy đoán một patch number Framework. Spring Boot BOM và resolved dependencies là nguồn xác minh cụ thể hơn.

## 4. Đối chiếu Spring Framework bằng dependency graph

Trong một dự án Gradle, có thể dùng các lệnh sau **tại môi trường phát triển dự án** để xem dependency thực tế. Đây là các lệnh để người học tham khảo; chúng không phải bước cần chạy khi chỉ đọc bài học:

~~~bash
# Xem dependency tổng thể ở runtime của module hiện tại.
./gradlew dependencies --configuration runtimeClasspath

# Truy nguồn phiên bản spring-core được chọn.
./gradlew dependencyInsight \
  --dependency org.springframework:spring-core \
  --configuration runtimeClasspath

# Kiểm tra một thành phần MVC cụ thể nếu ứng dụng có MVC.
./gradlew dependencyInsight \
  --dependency org.springframework:spring-webmvc \
  --configuration runtimeClasspath
~~~

Với một module trong multi-project build, chỉ rõ task path của module, ví dụ `./gradlew :catalog-api:dependencyInsight --dependency spring-core --configuration runtimeClasspath`. Trên Windows, dùng `gradlew.bat` hoặc cách gọi wrapper phù hợp với terminal. Một số module có cấu hình dependency khác `runtimeClasspath`; cần chọn configuration khớp với ứng dụng muốn quan sát.

Nếu dùng Maven, có thể kiểm tra:

~~~bash
# Xem cấu hình POM sau khi kế thừa parent/profile và nội suy.
./mvnw help:effective-pom

# In các dependency thuộc Spring Framework.
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Không chỉ tìm `spring-core`. Để hiểu một tính năng, kiểm tra artifact trực tiếp liên quan:

| Chức năng | Artifact cần chú ý |
|---|---|
| Container và bean | `spring-core`, `spring-beans`, `spring-context` |
| Spring MVC | `spring-web`, `spring-webmvc` |
| Spring WebFlux | `spring-web`, `spring-webflux` |
| Transaction | `spring-tx` |
| Spring Data JPA | `spring-data-jpa` cùng JPA provider liên quan |
| Spring Security | `spring-security-web`, `spring-security-config`, `spring-security-core` |

Phần lớn artifact của Spring Framework thường được quản lý nhất quán trong một dòng phiên bản. Nếu dependency graph cho thấy bị kéo lệch các module cốt lõi, hãy điều tra cấu hình quản lý phiên bản trước khi dựa vào tài liệu hoặc thử vá bằng cách bổ sung ngẫu nhiên một phiên bản riêng.

Trong IDE, bạn cũng có thể mở **External Libraries / Maven Dependencies / Gradle Dependencies** để xem version của JAR đã được resolve. Cách này hữu ích khi cần xác nhận class thực tế đến từ JAR nào. Nếu IDE và command line cho kết quả khác nhau, kiểm tra import/sync build, profile, cấu hình Gradle, cache và classpath đang chạy.

## 5. Chọn đúng trang tài liệu sau khi đã biết phiên bản

Giả sử bạn đã xác minh:

~~~text
Spring Boot           3.3.5
Spring Framework      6.1.x (xác định patch qua dependency graph)
Spring Data           phiên bản do BOM/resolution chọn
Spring Security       phiên bản do BOM/resolution chọn
~~~

Khi đó, thao tác tra cứu nên diễn ra như sau:

**Bước 1 — Chọn tài liệu Boot cùng dòng 3.3.** Nếu cần biết `spring.mvc.*`, cách chạy embedded server, actuator hoặc auto-configuration, ưu tiên Spring Boot Reference của **3.3**. Không mặc định tra phiên bản Boot đang được đánh dấu “current” ở thời điểm hiện tại.

**Bước 2 — Chọn tài liệu Framework cùng dòng 6.1.** Nếu tìm hiểu `@Bean`, transaction, validation tích hợp, HTTP request mapping hay WebFlux, tra Spring Framework Reference/Javadoc **6.1**. Với chữ ký API cụ thể, ưu tiên Javadoc của bản Framework đã được resolve.

**Bước 3 — Chọn tài liệu dự án con theo phiên bản riêng.** Nếu vấn đề nằm ở `SecurityFilterChain`, repository query hoặc reactive database, chuyển sang Spring Security/Spring Data và đối chiếu version tương ứng trong graph. Đừng áp dụng số version `3.3` của Boot lên các dự án con.

**Bước 4 — Xem release notes khi có khác biệt.** Nếu hướng dẫn trên mạng có API mà Javadoc của bạn không có, so sánh release notes hoặc migration guide của dòng nguồn và dòng đích. Cũng cần để ý chú thích `Since`, `Deprecated` và mục `Removed APIs` trong tài liệu.

**Bước 5 — Kiểm chứng với source và classpath.** Chữ ký method, annotation, dependency và import phải tồn tại trong phiên bản thực tế. Có thể mở `Go to Declaration` trong IDE để xác nhận API thuộc artifact nào.

### Một thứ tự tra cứu hữu ích

~~~text
Câu hỏi về ứng dụng
   │
   ├─ Spring Boot cấu hình gì?
   │      → Boot Reference của đúng dòng Boot
   │
   ├─ Spring Framework API xử lý thế nào?
   │      → Framework Reference của đúng dòng
   │      → Javadoc của artifact đã resolve
   │
   ├─ Security / Data / thư viện khác?
   │      → Reference của đúng project và version
   │
   └─ Tại sao ví dụ cũ không chạy hoặc nâng cấp bị lỗi?
          → Migration Guide / Release Notes
          → dependency graph và source thực tế
~~~

## 6. Nhận diện hướng dẫn cũ bằng những ví dụ phổ biến

### 6.1. `javax.*` so với `jakarta.*`

Spring Boot 3.x được xây trên Spring Framework 6.x và hệ sinh thái Jakarta EE mới, trong đó nhiều API thuộc Jakarta EE đổi namespace từ `javax.*` sang `jakarta.*`. Ví dụ:

~~~java
// Ví dụ từ hệ cũ, không dùng nguyên xi trong Boot 3.x:
import javax.servlet.http.HttpServletRequest;
import javax.persistence.Entity;
import javax.validation.constraints.NotNull;

// Với API tương ứng trong môi trường Boot 3.x:
import jakarta.servlet.http.HttpServletRequest;
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotNull;
~~~

Không được hiểu rằng **mọi** package `javax.*` đều phải đổi thành `jakarta.*`. Các package thuộc Java SE như `javax.crypto` hoặc `javax.net.ssl` vẫn có tên `javax.*`. Cần xem API đó thuộc **Jakarta EE** hay **Java SE**, và xác định dependency tương ứng. Thay import chỉ là một phần của việc di chuyển; server, persistence provider, validation provider và những thư viện tích hợp cũng phải hỗ trợ phiên bản mới.

### 6.2. Cấu hình Spring Security theo API của đúng dòng

Nhiều bài viết cũ còn kế thừa `WebSecurityConfigurerAdapter`. Lớp này đã bị loại khỏi Spring Security 6; ví dụ kiểu đó không thể áp dụng nguyên xi cho một dự án Boot 3.x sử dụng Spring Security 6.

Với dòng API mới hơn, cấu hình Servlet Security thường sử dụng bean `SecurityFilterChain`:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là ví dụ minh họa cho **Servlet Security**; cách xử lý CSRF, session, OAuth2/JWT, thông tin người dùng và đường dẫn cần phù hợp ứng dụng thực tế. Nếu dùng WebFlux, phải tra tài liệu **reactive security**, với `SecurityWebFilterChain` và `ServerHttpSecurity`, thay vì sao chép chain Servlet. Đọc đúng phiên bản thôi chưa đủ: còn phải đọc **đúng web stack**.

### 6.3. Lấy một annotation từ tài liệu nhưng dự án thiếu starter

Nếu tài liệu dùng `@Entity`, `JpaRepository` hoặc `@Valid` mà dự án báo lỗi không nhận diện được, nguyên nhân không nhất thiết là do sai phiên bản Boot. Có thể thiếu dependency dành cho JPA/Validation hoặc môi trường chưa import project đúng cách.

Ví dụ `spring-boot-starter-web` không đồng nghĩa ứng dụng đã có đầy đủ **Spring Data JPA**, database driver và Bean Validation provider. Trước khi tìm cách “sửa import” theo hướng dẫn trên mạng, xác định starter đang dùng và artifact chứa class tương ứng. Dùng Spring Initializr hoặc trang starter dependencies của đúng dòng Boot để tra dependency cần thiết.

### 6.4. Một thuộc tính cấu hình được đổi tên hoặc bị loại

Ví dụ lấy từ blog cũ có thể dùng thuộc tính `server.*`, `management.*` hoặc `spring.*` đã đổi tên, đổi mặc định hay không còn được hỗ trợ. Lúc này:

1. Đọc **Common Application Properties** của đúng dòng Boot.
2. Xem **configuration metadata**/gợi ý IDE nếu có.
3. Kiểm tra release notes/migration guide giữa hai dòng.
4. Xác nhận auto-configuration đang có mặt và điều kiện kích hoạt của nó.

Một thuộc tính “không có tác dụng” đôi khi là vì ứng dụng không nạp module/autoconfiguration tương ứng, chứ không chỉ vì property bị đổi tên.

## 7. Không nhầm giữa các loại “đúng phiên bản”

Cụm từ **đúng phiên bản** có nhiều lớp:

| Lớp | Ví dụ câu hỏi | Cách xác minh |
|---|---|---|
| **Phiên bản Boot khai báo** | Build dùng Spring Boot plugin/parent nào? | Build script, version catalog, POM |
| **Phiên bản BOM quản lý** | Boot dự định chọn phiên bản thư viện nào? | `spring-boot-dependencies` BOM tương ứng |
| **Phiên bản resolved** | Runtime thực sự nạp `spring-webmvc` phiên bản nào? | Dependency graph, IDE classpath |
| **Phiên bản JDK/Build Tool** | JDK, Gradle, Maven hiện tại có đáp ứng yêu cầu của dòng Boot? | Release notes/system requirements, `java -version` và wrapper |
| **Phiên bản tài liệu** | Reference/Javadoc đang hiển thị bản nào? | Nhãn version trên trang docs |
| **Phiên bản mã nguồn ví dụ** | Ví dụ được viết cho stack và release nào? | Metadata repo, commit/tag, imports, dependency declarations |
| **Phiên bản môi trường chạy** | Artifact đang deploy thật sự là build nào? | Build metadata, deployment/image tag và thông tin khởi động |

Thứ tự quan trọng là: **khai báo → quản lý → giải quyết dependency → mã chạy thực tế**. Ở mỗi tầng có thể tồn tại sai khác nếu build bị override, môi trường chạy dùng artifact cũ, hoặc một module khác được đóng gói.

### 7.1. Java và công cụ build cũng phải tương thích

Tài liệu Spring Boot có mục **System Requirements** cho từng dòng phát hành. Khi nâng cấp hoặc làm theo hướng dẫn, hãy xem:

- **Java tối thiểu và các bản Java được hỗ trợ** của dòng Boot;
- **Gradle/Maven phiên bản hỗ trợ** và version của wrapper trong project;
- yêu cầu **Servlet/Jakarta**, ứng dụng chạy bằng Tomcat/Jetty hay một runtime khác;
- những thay đổi cơ bản của Spring Framework và các thư viện tích hợp.

Chẳng hạn, Spring Boot 3.x yêu cầu **Java 17 trở lên** làm mức cơ sở; các dòng khác có thể có điều kiện hệ thống khác. Vì vậy, không dùng kết luận về JDK của một nhánh Boot cho tất cả các nhánh Boot. Nếu dự án có cả toolchain và JVM chạy Gradle, cần phân biệt Java được dùng để **biên dịch** với Java dùng để **chạy Gradle** và **chạy ứng dụng**.

### 7.2. Đúng reference vẫn có thể sai vì khác cấu hình

Một ví dụ trong Spring Boot Reference có thể giả định bạn dùng:

- Servlet MVC, trong khi ứng dụng của bạn chạy WebFlux;
- JPA, trong khi dự án dùng JDBC, R2DBC hoặc MongoDB;
- embedded web server, trong khi dự án đóng gói WAR;
- auto-configuration mặc định, trong khi ứng dụng đã tự khai báo bean;
- một ứng dụng độc lập, trong khi bạn đang làm việc trong multi-module build.

Hãy đọc **điều kiện áp dụng** ngay quanh ví dụ: các annotation, dependency cần có, web stack, bean được tạo và thuộc tính bật/tắt. Không chỉ tìm đoạn code trùng tên class.

## 8. Cách đọc Javadoc mà không suy diễn quá khả năng của API

Khi tìm thấy một class trong Spring Framework, hãy kiểm tra:

1. **Package và artifact**: class đang ở `org.springframework.web.servlet.*`, `org.springframework.web.reactive.*` hay package khác?
2. **Chữ ký thực tế**: constructor, tham số, kiểu trả về, generic và checked exceptions.
3. **`Since`**: method/class xuất hiện từ dòng nào?
4. **`Deprecated`**: từ khi nào và tài liệu gợi ý API thay thế nào?
5. **Hợp đồng hành vi**: precondition, nullability, callback, lifecycle, thread-safety, thời điểm thực thi.
6. **Liên kết nguồn**: interface/superclass, implementation và trang hướng dẫn tương ứng.

Ví dụ, nếu Javadoc hiện tại ghi method được thêm **Since 6.2** nhưng dependency graph của bạn là Spring Framework **6.1.x**, method đó chưa có trong classpath dù tên class vẫn trùng. Cần tìm API tồn tại ở 6.1 hoặc lên kế hoạch nâng cấp theo bộ phiên bản tương thích.

Tương tự, nếu API đã **deprecated**, không đồng nghĩa lập tức bị xóa ở phiên bản hiện tại. Javadoc của đúng bản sẽ giúp phân biệt “vẫn tồn tại nhưng khuyên chuyển đổi” với “đã bị loại”.

## 9. Khi nâng cấp: đọc tài liệu của cả phiên bản cũ và mới

Giả sử ứng dụng chuyển từ một dòng Spring Boot cũ sang dòng mới. Không nên chỉ mở reference của phiên bản đích và sửa theo những thông báo lỗi đầu tiên. Quy trình tốt hơn:

1. **Ghi lại hiện trạng**: Boot version, Framework version, Spring Security/Data, JDK, Gradle/Maven, web stack và các dependency override.
2. **Đọc mục Upgrading/Release Notes/Migration Guide** của Boot cho đoạn chuyển đổi đó; nếu đi qua nhiều dòng minor/major, đọc các bước trung gian.
3. **Kiểm tra thay đổi của Framework và các dự án con** tương ứng, nhất là security, persistence và Spring Cloud nếu ứng dụng sử dụng.
4. **Nâng bộ phiên bản đồng bộ** qua BOM/parent/plugin phù hợp trước khi tự ghim từng thư viện Spring.
5. **Tìm breaking changes**: package `javax`/`jakarta`, removed/deprecated APIs, thay đổi property, auto-configuration conditions, defaults, servlet/reactive behavior.
6. **Đối chiếu dependency graph sau nâng cấp** để đảm bảo không còn bản cũ bị kéo vào ngoài chủ đích.
7. **Kiểm tra hành vi chạy ứng dụng**: bean creation, HTTP mapping, security, transaction, persistence, serialization, startup và integration tests.

Đặc biệt, **không nâng riêng Spring Framework lên major khác chỉ vì muốn dùng một API mới**, trong khi toàn bộ hệ thống vẫn do BOM Boot cũ quản lý, trừ khi có hướng dẫn tương thích rõ ràng và đã đánh giá đầy đủ. Mặc định, để Boot điều phối những thư viện mà nó quản lý sẽ ít rủi ro hơn.

### Một tình huống tự kiểm tra

Bạn có một dự án ghi:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Bạn mở kết quả tìm kiếm nói rằng “Spring Framework 6.2 có API X” và định thêm một lệnh gọi API X.

Hãy xác minh tuần tự:

1. **Boot 3.3.5 đang quản lý phiên bản Framework thuộc dòng nào?** Không suy từ chữ “Spring” trong tên framework.
2. **`spring-webmvc`/`spring-core` được resolve thành bản nào?** Xem dependency graph.
3. **Javadoc của bản resolved có API X không?** Nếu không, nguồn tìm kiếm đang nói về phiên bản khác.
4. **Nhu cầu có thể giải quyết bằng API đang hỗ trợ không?** Nếu không, cân nhắc nâng Boot theo hướng dẫn migration, thay vì ép một mình artifact Framework.

Thao tác này tiết kiệm nhiều thời gian hơn so với việc thử sửa liên tục import hoặc ép dependency version cho tới khi compiler hết báo lỗi.

## 10. Thực hành tra cứu cho một lỗi thường gặp

**Tình huống:** Sau khi xem một hướng dẫn trên mạng, bạn viết:

~~~java
import javax.servlet.http.HttpServletRequest;

@RestController
class TraceController {
    @GetMapping("/trace")
    String trace(HttpServletRequest request) {
        return request.getRequestURI();
    }
}
~~~

IDE báo không tìm thấy `javax.servlet.http.HttpServletRequest` trong dự án Spring Boot 3.x.

**Cách điều tra theo phiên bản:**

1. Mở build file, xác định Boot 3.x và `spring-boot-starter-web` có được đưa vào không.
2. Kiểm tra Spring Framework/Servlet dependencies thực tế và xác nhận ứng dụng dùng Servlet MVC.
3. Tìm tài liệu Servlet/Jakarta phù hợp với dòng Boot và Framework, thay vì sao chép thêm một JAR `javax.servlet` cũ để làm cho import tồn tại.
4. Đổi import cho đúng namespace Jakarta:

~~~java
import jakarta.servlet.http.HttpServletRequest;

@RestController
class TraceController {
    @GetMapping("/trace")
    String trace(HttpServletRequest request) {
        return request.getRequestURI();
    }
}
~~~

5. Nếu lỗi vẫn còn, kiểm tra classpath và web stack thực tế: một ứng dụng WebFlux dùng kiểu request reactive khác, nên việc thay `javax` bằng `jakarta` không tự biến thiết kế reactive thành MVC.

Bài học rút ra là **lỗi import có thể là dấu hiệu của khác biệt phiên bản hoặc khác biệt web stack**, không nhất thiết là thiếu một dependency đơn lẻ.

## 11. Mẫu ghi chú phiên bản khi đọc tài liệu

Trước khi áp dụng một ví dụ, có thể ghi nhanh thông tin sau vào ghi chú học tập hoặc mô tả issue:

~~~text
Chủ đề đang tra: @Transactional + Spring Data JPA
Spring Boot: 3.3.5
Spring Framework: <bản spring-tx/spring-core resolved>
Spring Data JPA: <bản spring-data-jpa resolved>
JDK: <bản Java build/run>
Build tool: Gradle hoặc Maven <phiên bản>
Web stack: Spring MVC / WebFlux / không có web
Tài liệu: <URL + nhãn phiên bản hiển thị>
API liên quan: <package.class#method>
Thay đổi cần lưu ý: <release note/migration link nếu có>
~~~

Ghi chú phiên bản ngắn như vậy giúp bạn phân biệt rõ: câu trả lời đến từ tài liệu của **dòng nào**, đang được áp dụng cho **artifact nào**, và có cần kiểm tra migration hay không. Khi báo lỗi hoặc đặt câu hỏi cho người khác, đính kèm **dependency graph phần liên quan** thường hữu ích hơn chỉ nói “em dùng Spring Boot”.

## 12. Các quy tắc cần nhớ

- **Spring Boot version và Spring Framework version là hai số khác nhau.** Spring Boot BOM quyết định bộ phiên bản thư viện mặc định; dependency graph xác nhận bản thực sự được chọn.
- **Trang “latest/current” có thể không đúng với dự án.** Luôn kiểm tra nhãn version trên reference, Javadoc và ví dụ.
- **Đọc tài liệu theo đúng vấn đề.** Boot cho auto-configuration/starter; Framework cho core/MVC/WebFlux/transaction; Data và Security theo phiên bản từng dự án con.
- **Release notes và migration guides rất quan trọng khi nâng cấp.** Một ví dụ hoạt động ở dòng mới có thể chứa API chưa được hỗ trợ ở dòng cũ.
- **Đúng phiên bản phải đi cùng đúng stack.** Ví dụ MVC/Servlet không thể áp dụng nguyên xi cho WebFlux; ví dụ JPA blocking khác R2DBC reactive.
- **Không sửa lỗi thiếu API bằng cách ép ngẫu nhiên phiên bản thư viện.** Xác định nguyên nhân từ build, BOM, dependency graph và compatibility trước.

Khi đọc một hướng dẫn Spring, hãy hình thành phản xạ: **“Bài viết này thuộc dòng Boot nào, dựa trên Framework nào, và các API được dùng có thực sự nằm trong classpath của ứng dụng mình không?”** Trả lời được ba câu hỏi đó là nền tảng để tiếp cận tài liệu Spring Boot chính xác, học hiệu quả và nâng cấp ứng dụng an toàn.
