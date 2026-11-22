# Thay đổi package, module và dependency khi nâng dòng Spring Boot

## 1. Nâng dòng Spring Boot là một thay đổi của cả nền tảng

Một lần nâng Spring Boot không chỉ là đổi số phiên bản trong `pom.xml` hoặc `build.gradle`. Mỗi dòng Spring Boot được kiểm thử với một bộ phiên bản Java, Spring Framework, Spring Data, Spring Security, thư viện bên thứ ba và build plugin nhất định. Khi nâng dòng, những phần này cần tiếp tục tương thích với nhau.

Có bốn nhóm thay đổi cần rà soát:

1. **Java và Jakarta EE:** phiên bản JDK tối thiểu, Servlet/JPA/Validation API và namespace package.
2. **Package và API:** class được di chuyển, đổi tên, thay thế hoặc loại bỏ; các chuỗi class name trong metadata cũng có thể cần sửa.
3. **Module và starter:** artifact được tách nhỏ, đổi tên hoặc có thêm test starter riêng.
4. **Dependency management:** BOM, tọa độ Maven, phiên bản thư viện và plugin build cần đồng bộ với dòng Boot đích.

Một dự án có thể biên dịch sau khi đổi version nhưng vẫn gặp lỗi runtime do dependency cũ còn trong classpath, auto-configuration không được phát hiện hoặc container không đáp ứng Servlet baseline mới. Vì vậy, phải xem nâng cấp là một thay đổi có kiểm chứng từ compile, test, package đến khởi động ứng dụng.

## 2. Xác định dòng nguồn và dòng đích trước khi sửa build

Spring Boot khuyến nghị nâng ứng dụng lên maintenance release mới nhất của dòng hiện tại trước khi chuyển sang dòng mới. Ví dụ:

- Từ Boot 2.x sang Boot 3.x: trước tiên nâng lên bản 2.7.x mới nhất, xử lý các cảnh báo deprecation và kiểm tra dependency.
- Từ Boot 3.x sang Boot 4.x: trước tiên nâng lên bản 3.5.x mới nhất, xử lý API/property đã deprecated và kiểm tra dependency.

Nếu bỏ qua nhiều feature release, đọc release notes của tất cả các dòng đã đi qua. Các thay đổi nhỏ về property, auto-configuration hoặc dependency có thể cộng dồn thành lỗi khó truy vết ở lần nâng cấp cuối cùng.

### 2.1. So sánh các mốc nền tảng quan trọng

| Dòng Spring Boot | Java tối thiểu | Spring Framework nền tảng | Jakarta/Servlet |
|---|---:|---|---|
| Boot 2.7 | Java 8 | Spring Framework 5.3 | Java EE / `javax.*` APIs |
| Boot 3.0 | Java 17 | Spring Framework 6.0 | Jakarta EE 10; Servlet 6.0 |
| Boot 4.0 | Java 17 | Spring Framework 7.x | Jakarta EE 11; Servlet 6.1 |

Bảng này nêu các mốc major quan trọng, không thay thế System Requirements của đúng maintenance release. Phiên bản build tool, container, Kotlin, GraalVM và các thư viện hỗ trợ có thể có yêu cầu riêng. Kiểm tra tài liệu dòng đích trước khi thay đổi toolchain.

Ví dụ, Boot 4.0 yêu cầu Java 17 trở lên và Spring Framework 7.x. Tài liệu System Requirements của Boot 4.0 cũng công bố Maven 3.6.3 trở lên và Gradle 8.14 trở lên trong nhánh 8.x hoặc Gradle 9.x. Hãy kiểm tra lại yêu cầu của đúng bản Boot sẽ triển khai.

### 2.2. Lập danh sách dependency trước khi đổi version

Ghi lại các thành phần sau:

- JDK đang dùng để build và JDK ở production.
- Spring Boot plugin, parent POM hoặc BOM.
- Spring Framework, Spring Data, Spring Security và Spring Cloud.
- Starter đang dùng và dependency được khai báo trực tiếp.
- Driver database, HTTP client, logging, JSON, metrics và messaging.
- Build plugin, annotation processor, test engine và container triển khai.
- Các thư viện tự viết có import class nội bộ hoặc package của Spring Boot.

Phân biệt dependency được BOM quản lý với dependency có version tự khai báo. Một thư viện ngoài BOM, chẳng hạn Spring Cloud hoặc SDK của nhà cung cấp, phải được kiểm tra compatibility matrix riêng. Không suy luận rằng nó tương thích chỉ vì ứng dụng đã dùng Spring Boot mới.

## 3. Boot 2 sang Boot 3: chuyển từ Java EE sang Jakarta EE

Thay đổi package dễ nhận thấy nhất khi nâng từ Boot 2 lên Boot 3 là các API thuộc Jakarta EE chuyển từ namespace `javax` sang `jakarta`. Boot 3 dùng Spring Framework 6 và các phiên bản Jakarta EE mới hơn.

Ví dụ các import thường phải đổi:

| Trước (Boot 2 / Java EE) | Sau (Boot 3 / Jakarta EE) |
|---|---|
| `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` |
| `javax.validation.Valid` | `jakarta.validation.Valid` |
| `javax.transaction.Transactional` | `jakarta.transaction.Transactional` |
| `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` |

Ví dụ Servlet API:

~~~java
// Trước: Boot 2.x
import javax.servlet.Filter;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;

// Sau: Boot 3.x
import jakarta.servlet.Filter;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
~~~

Không thay thế hàng loạt mọi chuỗi bắt đầu bằng `javax.`. Một số package thuộc Java SE vẫn giữ nguyên, chẳng hạn:

- `javax.sql.DataSource`
- `javax.crypto.*`
- `javax.net.*`
- `javax.xml.*`
- `javax.annotation.processing.*`

Hãy xác định package thuộc Jakarta EE hay Java SE trước khi sửa import. Nếu thay nhầm `javax.sql.DataSource` thành `jakarta.sql.DataSource`, code sẽ không biên dịch vì package đó không tồn tại.

### 3.1. Đồng bộ dependency Jakarta

Nếu dùng Spring Boot starters và BOM, nhiều dependency Jakarta sẽ được quản lý theo dòng Boot. Nếu tự khai báo API, kiểm tra cả tọa độ Maven và version.

Ví dụ Servlet API:

~~~xml
<!-- Jakarta Servlet API cho ứng dụng Boot 3 -->
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Không giữ đồng thời API cũ `javax.servlet:javax.servlet-api` và API mới `jakarta.servlet:jakarta.servlet-api` trong cùng runtime chỉ để che lỗi biên dịch. Hai namespace có kiểu khác nhau và không thể thay thế nhau.

Các thư viện tích hợp cũng phải hỗ trợ Jakarta. Nếu một SDK, filter, validation provider hoặc thư viện persistence chỉ cung cấp class `javax.*`, cần nâng lên phiên bản Jakarta-compatible hoặc thay thế thư viện đó.


## 4. Boot 3: rà soát auto-configuration, package và dependency cũ

### 4.1. Đăng ký auto-configuration bằng imports file

Spring Boot 2.7 đã giới thiệu file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Từ Spring Boot 3.0, việc đăng ký auto-configuration bằng khóa `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories` đã bị loại bỏ. Hãy chuyển danh sách auto-configuration sang `AutoConfiguration.imports`.

Ví dụ nội dung file:

~~~text
com.example.audit.autoconfigure.AuditAutoConfiguration
com.example.audit.autoconfigure.AuditMetricsAutoConfiguration
~~~

Mỗi dòng là tên đầy đủ của một class. Các mục `spring.factories` khác, chẳng hạn extension point không phải `EnableAutoConfiguration`, không bị xóa chỉ vì thay đổi này. Đọc đúng key và hướng dẫn của extension point tương ứng trước khi chuyển.

Nếu thư viện cần hỗ trợ cả Boot 2.7 và Boot 3 trong giai đoạn chuyển tiếp, Boot 2.7 hiểu cả hai cơ chế và có thể loại trùng class được khai báo ở cả hai nơi. Với thư viện mới chỉ hỗ trợ Boot 3 trở lên, dùng imports file làm cơ chế đăng ký chính.

### 4.2. Theo dõi class đổi tên hoặc chuyển package

Không chỉ sửa import trong source code. Tên class còn có thể xuất hiện trong:

- `AutoConfiguration.imports` và các file metadata.
- `spring.factories`.
- `@AutoConfiguration(before = ...)` hoặc `after = ...`.
- `exclude` / `excludeName` của `@EnableAutoConfiguration`.
- `@Import`, reflection, tên class trong cấu hình và test.
- `META-INF/spring/...AutoConfiguration.replacements` nếu thư viện duy trì tương thích tên auto-configuration.

Ví dụ từ Boot 3 migration guide: `ReactiveElasticsearchRestClientAutoConfiguration` được đổi tên thành `ReactiveElasticsearchClientAutoConfiguration` và chuyển package từ `org.springframework.boot.autoconfigure.data.elasticsearch` sang `org.springframework.boot.autoconfigure.elasticsearch`. Khi ứng dụng exclude hoặc sắp xếp cấu hình bằng class cũ, phải cập nhật cả import lẫn tham chiếu metadata tương ứng.

### 4.3. Kiểm tra tọa độ dependency đã thay đổi

Một số dependency có thể đổi groupId hoặc artifactId khi nâng dòng. Ví dụ trong quá trình chuyển sang Boot 3:

| Trước | Sau |
|---|---|
| `mysql:mysql-connector-java` | `com.mysql:mysql-connector-j` |
| `org.apache.httpcomponents:httpclient` | `org.apache.httpcomponents.client5:httpclient5` |

Đây là các ví dụ tiêu biểu, không phải danh sách đầy đủ. Đừng giữ tọa độ cũ chỉ vì một dependency bắc cầu vẫn kéo nó vào classpath. Kiểm tra dependency tree và tài liệu của nhà cung cấp để xác định dependency trực tiếp mà ứng dụng nên khai báo.

### 4.4. Xử lý property đã đổi tên hoặc bị loại bỏ

Property có thể đổi prefix, đổi tên hoặc bị loại bỏ giữa các feature release. Ví dụ trong Boot 3, một số cấu hình Redis chuyển từ `spring.redis.*` sang `spring.data.redis.*`; một số cấu hình Cassandra chuyển từ `spring.data.cassandra.*` sang `spring.cassandra.*`.

Spring Boot cung cấp module `spring-boot-properties-migrator` để phân tích môi trường, in cảnh báo và tạm thời migrate một số property khi chạy ứng dụng.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Gradle:

~~~groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
~~~

Chạy ứng dụng trong môi trường test hoặc staging, đọc cảnh báo, cập nhật file cấu hình thật rồi gỡ migrator khỏi dependency. Migrator là công cụ chuyển tiếp, không phải lớp tương thích cần giữ lâu dài. Một số property được thêm muộn vào Environment, chẳng hạn thông qua `@PropertySource`, có thể không được migrator xử lý đầy đủ.

## 5. Boot 4: module nhỏ hơn và package theo module

Spring Boot 4.0 có thiết kế module hóa rõ hơn. Thay vì một số JAR lớn chứa nhiều phần tích hợp, Boot phát hành nhiều module nhỏ theo công nghệ. Mỗi module có package gốc riêng theo quy ước:

- Module: `spring-boot-<technology>`.
- Package gốc: `org.springframework.boot.<technology>`.
- Starter: `spring-boot-starter-<technology>`.

Ví dụ, phần hỗ trợ GraphQL nằm trong module `spring-boot-graphql`, package gốc `org.springframework.boot.graphql`, và starter là `spring-boot-starter-graphql`.

Điều này ảnh hưởng đến cả dependency lẫn Java import. Nếu ứng dụng chỉ dùng starter chính thức, phần lớn dependency thường được chuyển theo starter. Nếu ứng dụng khai báo trực tiếp các module Boot hoặc import class Boot cụ thể, cần rà soát và chuyển từng module/package.

### 5.1. Các starter được đổi tên

Một số starter cũ vẫn còn trong Boot 4 nhưng đã deprecated để người dùng chuyển sang tên mới:

| Starter cũ | Starter mới |
|---|---|
| `spring-boot-starter-web` | `spring-boot-starter-webmvc` |
| `spring-boot-starter-web-services` | `spring-boot-starter-webservices` |
| `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` |
| `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` |
| `spring-boot-starter-oauth2-authorization-server` | `spring-boot-starter-security-oauth2-authorization-server` |

Không dựa vào việc starter cũ vẫn resolve được để kết luận nó còn là lựa chọn tốt. Cập nhật theo tên thay thế trong migration guide và theo dõi các starter deprecated sẽ bị gỡ ở release sau.

### 5.2. Tách dependency runtime và test

Boot 4 chuẩn hóa starter theo công nghệ và cung cấp nhiều test starter đi kèm. Ví dụ:

| Mục đích | Dependency |
|---|---|
| Spring MVC runtime | `spring-boot-starter-webmvc` |
| Spring MVC test support | `spring-boot-starter-webmvc-test` |
| JDBC runtime | `spring-boot-starter-jdbc` |
| JDBC test support | `spring-boot-starter-jdbc-test` |
| Spring Security runtime | `spring-boot-starter-security` |
| Spring Security test support | `spring-boot-starter-security-test` |

Kiểm tra `testImplementation` / Maven `test` scope riêng. Khi test infrastructure được module hóa, một dependency test cũ có thể không còn kéo theo mọi lớp test utility mà ứng dụng từng dùng gián tiếp.

### 5.3. Các package chuyển vị trí trong Boot 4

Một số ví dụ quan trọng trong migration guide:

| API | Package cũ | Package mới |
|---|---|---|
| `BootstrapRegistry` | `org.springframework.boot` | `org.springframework.boot.bootstrap` |
| `EnvironmentPostProcessor` | `org.springframework.boot.env` | `org.springframework.boot` |
| `EntityScan` | package auto-config cũ | `org.springframework.boot.persistence.autoconfigure.EntityScan` |
| `TestRestTemplate` | package test cũ | `org.springframework.boot.resttestclient.TestRestTemplate` |

Nếu dùng `EnvironmentPostProcessor` hoặc `BootstrapRegistry`, cập nhật cả source code và tên class được đăng ký trong `spring.factories`. Với `TestRestTemplate`, migration guide chỉ rõ dependency test mới là `spring-boot-resttestclient`.

Ví dụ import sau khi nâng Boot 4:

~~~java
import org.springframework.boot.bootstrap.BootstrapRegistry;
import org.springframework.boot.EnvironmentPostProcessor;
import org.springframework.boot.persistence.autoconfigure.EntityScan;
import org.springframework.boot.resttestclient.TestRestTemplate;
~~~

Không sao chép nguyên bảng package từ một bài blog cũ. Mỗi class cần được đối chiếu với API docs hoặc migration guide của đúng dòng Boot đích vì package có thể thay đổi theo module và release.

### 5.4. Thay đổi Jackson 2 sang Jackson 3

Boot 4 dùng Jackson 3 làm thư viện JSON mặc định. Jackson 3 chuyển phần lớn groupId/package từ `com.fasterxml.jackson` sang `tools.jackson`; riêng `jackson-annotations` tiếp tục dùng groupId `com.fasterxml.jackson.core` và package `com.fasterxml.jackson.annotation`.

Một số thay đổi API:

| Jackson 2 / Boot 3 | Jackson 3 / Boot 4 |
|---|---|
| `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.ObjectMapper` |
| `Jackson2ObjectMapperBuilderCustomizer` | `JsonMapperBuilderCustomizer` |
| `@JsonComponent` | `@JacksonComponent` |
| `@JsonMixin` | `@JacksonMixin` |

Một số property JSON cũng chuyển từ `spring.jackson.read.*` / `spring.jackson.write.*` sang `spring.jackson.json.read.*` / `spring.jackson.json.write.*`.

Nếu chưa thể chuyển ngay, Boot 4 có module tương thích `spring-boot-jackson2`, nhưng module này được đánh dấu deprecated và chỉ nên dùng như giải pháp chuyển tiếp. Không đưa cả Jackson 2 và Jackson 3 vào cấu hình mặc định mà không hiểu rõ mapper nào được dùng ở từng integration.


## 6. Đồng bộ BOM, Spring Framework và build plugin

Spring Boot phát hành BOM `spring-boot-dependencies` chứa các phiên bản dependency mà dòng Boot đó đã tích hợp và kiểm thử cùng nhau. Dùng BOM để các module Spring, Spring Data và thư viện bên thứ ba được quản lý đồng bộ.

Nguyên tắc khi nâng:

- Cập nhật Spring Boot parent, plugin và BOM về cùng một dòng.
- Bỏ version tự khai báo cho dependency đã được BOM quản lý.
- Không ép Spring Framework, Spring Data, Jackson, Hibernate hoặc logging sang version tùy ý nếu chưa có kiểm thử tương thích.
- Nếu cần override một dependency, ghi rõ lý do, kiểm tra compatibility matrix và thêm test tương ứng.
- Spring Cloud và các portfolio release train khác phải dùng phiên bản tương thích với dòng Boot đích.

### 6.1. Maven: dùng parent hoặc import BOM

Nếu dự án có thể kế thừa parent của Spring Boot:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.0</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`4.0.0` là version minh họa cho cú pháp. Khi thực hiện migration thật, dùng maintenance release được tổ chức phê duyệt và cùng version đó cho Spring Boot Maven plugin.

Nếu công ty có parent POM riêng, import BOM trong `dependencyManagement`:

~~~xml
<properties>
    <spring-boot.version>4.0.0</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo dependency mà không lặp version nếu BOM đã quản lý. Đồng thời cập nhật `spring-boot-maven-plugin` về cùng dòng version. Nếu plugin cũ vẫn chạy trong khi BOM mới đã được import, build có thể tạo artifact bằng loader hoặc packaging behavior không đồng nhất.

### 6.2. Gradle: đồng bộ plugin và BOM

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.0'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.0.0')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là cấu hình minh họa cho Boot 4.0. Trong dự án thực tế, kiểm tra phiên bản Gradle Wrapper mà dòng Boot đích hỗ trợ và dùng cùng version cho plugin với BOM. Nếu project dùng Kotlin DSL hoặc convention plugin nội bộ, cập nhật version catalog và plugin convention thay vì chỉ sửa một module con.

### 6.3. Không giữ nhiều version của cùng một nền tảng

Sau khi đổi BOM, chạy dependency insight để tìm version conflict. Ví dụ, một dependency trực tiếp khai báo Spring Framework 6 trong khi Boot 4 quản lý Spring Framework 7 có thể làm classpath chứa các module Spring không cùng baseline.

Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Kiểm tra cả compile classpath, runtime classpath và test runtime classpath. Một dependency cũ chỉ xuất hiện trong test có thể làm test compile lỗi dù ứng dụng production đã chạy.

## 7. Xây dựng thư viện/starter riêng cho nhiều dòng Boot

Nếu nhóm phát triển một thư viện auto-configuration hoặc starter, package và module của Spring Boot là một phần compile-time API mà thư viện phụ thuộc. Một artifact được build với Boot 3 không tự nhiên tương thích với Boot 4 chỉ vì người dùng đổi version dependency.

Migration guide Boot 4 khuyến cáo mạnh việc không hỗ trợ Boot 3 và Boot 4 trong cùng một artifact do thay đổi module hóa và package.

Một cách tổ chức dễ kiểm soát là phát hành artifact riêng cho từng dòng:

~~~text
northstar-spring-boot-3-autoconfigure
northstar-spring-boot-3-starter
northstar-spring-boot-4-autoconfigure
northstar-spring-boot-4-starter
~~~

Tên ở trên là ví dụ của một nhà cung cấp giả định. Giữ namespace của nhà cung cấp đứng trước; không đặt tên artifact bên thứ ba bắt đầu bằng `spring-boot`.

Có thể dùng một repository đa module hoặc các nhánh release riêng, nhưng mỗi artifact cần:

- Compile với đúng Spring Boot BOM và API của dòng được hỗ trợ.
- Có dependency graph riêng, không kéo class Boot 3 vào artifact Boot 4.
- Có bộ test chạy trên phiên bản Boot tương ứng.
- Đóng gói đúng auto-configuration imports và metadata.
- Công bố rõ version compatibility, Java baseline và migration path.
- Có thể phát hành bản vá bảo mật độc lập theo từng dòng nếu tổ chức cần hỗ trợ song song.

Nếu cần dùng chung phần nghiệp vụ, tách code không phụ thuộc Spring Boot vào module core. Hai adapter Boot 3 và Boot 4 có thể dùng chung core API, nhưng mỗi adapter biên dịch với đúng package, module và auto-configuration API của dòng tương ứng.

### 7.1. Kiểm tra metadata của starter sau khi chuyển

Sau khi build JAR, kiểm tra:

- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` chứa đúng tên class của dòng Boot đích.
- Các file `spring.factories` chỉ còn key và class name hợp lệ.
- Tên class trong ordering, exclusion, replacement và reflection không còn package cũ.
- Configuration metadata được sinh từ class `@ConfigurationProperties` đúng.
- Không có duplicate class hoặc dependency bắc cầu kéo Boot 3 và Boot 4 vào cùng runtime.

Một test dùng `ApplicationContextRunner` có thể đăng ký auto-configuration class trực tiếp, vì vậy nó chưa đủ chứng minh resource trong JAR được đóng gói đúng. Thêm consumer smoke test chỉ phụ thuộc starter đã publish hoặc install vào repository local để xác minh discovery qua artifact.


## 8. Quy trình nâng cấp theo từng bước

Một quy trình có thể lặp lại giúp phát hiện lỗi ở đúng lớp thay đổi.

### Bước 1: Chốt baseline hiện tại

- Nâng lên maintenance release mới nhất của dòng Boot đang dùng.
- Chạy toàn bộ test và lưu kết quả làm baseline.
- Ghi lại dependency tree, version JDK, Maven/Gradle Wrapper và container production.
- Bật compiler warning hoặc kiểm tra deprecation để tìm API đã bị đánh dấu loại bỏ.

Không bắt đầu bằng việc đổi hàng loạt import khi ứng dụng hiện tại vẫn chưa build xanh. Nếu có lỗi từ trước, phân loại chúng trước để không nhầm lỗi cũ với lỗi do migration.

### Bước 2: Làm sạch deprecation trước khi chuyển major

Thay các class, method và property đã deprecated trong dòng hiện tại. Boot 3 loại bỏ nhiều API đã deprecated trong Boot 2; Boot 4 tiếp tục loại các API đã deprecated trong Boot 3.

Đọc migration guide và release notes theo từng dòng. Một method còn tồn tại trong bản cuối của dòng cũ không có nghĩa nó vẫn tồn tại ở major kế tiếp.

### Bước 3: Nâng JDK và build tool

Cập nhật JDK/toolchain trước hoặc cùng một thay đổi build có kiểm soát. Kiểm tra:

- JDK local, CI, Docker base image và production runtime.
- Maven Wrapper hoặc Gradle Wrapper.
- Compiler release/source compatibility.
- Annotation processor, Kotlin plugin và plugin tạo executable JAR.
- Container Servlet hoặc application server nếu deploy WAR.

Ví dụ cấu hình Java toolchain trong Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Java 17 là baseline cho Boot 3 và Boot 4. Tuy nhiên, dependency bên thứ ba hoặc công cụ build có thể yêu cầu Java cao hơn.

### Bước 4: Đổi Spring Boot parent/plugin/BOM cùng một lượt

Cập nhật một nơi quản lý version duy nhất nếu có thể. Kiểm tra mọi module con đều kế thừa BOM mới, kể cả module test, integration test, build logic và code generation.

Đảm bảo plugin Boot, BOM, dependency management plugin và các plugin liên quan không còn trộn version của hai dòng.

### Bước 5: Sửa package và metadata

- Với Boot 2 sang 3, chuyển các API Jakarta từ `javax` sang `jakarta` và rà soát dependency tương ứng.
- Với Boot 3 sang 4, sửa các package đã được chia theo module, ví dụ `BootstrapRegistry`, `EnvironmentPostProcessor`, `EntityScan` và `TestRestTemplate`.
- Cập nhật `spring.factories` nếu tên class extension point đã đổi.
- Cập nhật `AutoConfiguration.imports`, exclusions, ordering và reflection strings.
- Kiểm tra test source, generated source, annotation processor và file cấu hình.

Không sửa tên package trong source code mà quên class name được lưu dưới dạng chuỗi trong file metadata.

### Bước 6: Chuyển starter và dependency test

Đối chiếu dependency với bảng starter/module của dòng Boot đích. Thay starter deprecated bằng starter mới; bổ sung test starter tương ứng khi test đang dùng các class test support đã được tách.

Nếu đang nâng lên Boot 4 và cần một bước trung gian để ứng dụng lớn khởi động lại nhanh, có thể dùng `spring-boot-starter-classic` và `spring-boot-starter-test-classic`. Các classic starter cung cấp tập module rộng gần với thế hệ trước, giúp chuyển package và dependency dần dần. Đây chỉ là cầu nối; sau khi migration hoàn tất, quay lại starter/module cụ thể để classpath nhỏ và rõ hơn.

### Bước 7: Chuyển property và hành vi cấu hình

Dùng properties migrator khi có đổi tên property, sau đó sửa file cấu hình gốc. So sánh các file:

- `application.properties` và `application.yml`.
- Cấu hình theo profile.
- Environment variables và command-line arguments.
- Config server, Kubernetes ConfigMap/Secret và secret manager.
- Các giá trị được nạp qua `@PropertySource` hoặc custom EnvironmentPostProcessor.

Kiểm tra giá trị thực sau khi bind, không chỉ kiểm tra tên property trong source. Property có thể giữ tên nhưng thay đổi default hoặc cách hiểu.

### Bước 8: Chạy kiểm thử và xác minh artifact

Chạy theo thứ tự:

1. Compile main source và test source.
2. Unit tests và slice tests.
3. Integration tests với database, broker, cache và external service giả lập.
4. Package JAR/WAR và kiểm tra nội dung.
5. Khởi động ứng dụng bằng artifact vừa đóng gói.
6. Smoke test endpoint, health, metrics, security, database migration và graceful shutdown.
7. Kiểm tra image/container trong môi trường gần production.

Với thư viện starter, thêm consumer sample chỉ phụ thuộc artifact starter đã publish/install. Test này xác nhận dependency transitives, package và auto-configuration discovery hoạt động như người dùng thực tế.

## 9. Công cụ hỗ trợ tìm và sửa thay đổi

### 9.1. Tìm import cũ và tọa độ dependency

Có thể dùng ripgrep để rà soát source và build file:

~~~bash
rg -n "javax\\.(servlet|persistence|validation|transaction|annotation)" src
rg -n "spring-boot-starter-web|spring-boot-starter-oauth2" pom.xml build.gradle settings.gradle
rg -n "spring\\.redis|spring\\.data\\.cassandra|spring\\.data\\.mongodb" src/main/resources
~~~

Kết quả tìm kiếm là danh sách cần xem xét, không phải danh sách thay thế tự động. Đặc biệt, không thay tất cả `javax.*` vì nhiều package Java SE vẫn thuộc JDK.

### 9.2. Dùng OpenRewrite hoặc IDE migration

OpenRewrite có recipe hỗ trợ một số chuyển đổi Spring Boot và Jakarta. IDE cũng có thể hỗ trợ đổi package và sửa import. Các công cụ này giúp giảm thao tác lặp, nhưng kết quả vẫn cần review:

- Recipe có thể không biết dependency nội bộ của tổ chức.
- Một số thay đổi cần sửa tọa độ Maven/Gradle cùng với source code.
- Reflection, class name dạng chuỗi và resource file có thể không được tự động cập nhật.
- Một API thay đổi ngữ nghĩa có thể cần thiết kế lại, không chỉ rename.

Chạy recipe trên branch riêng, review diff, sau đó compile và test. Không coi việc recipe chạy xong là bằng chứng migration đã hoàn tất.

### 9.3. Kiểm tra dependency và JAR

Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dverbose
mvn clean verify
jar tf target/application.jar
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew clean check bootJar
~~~

Kiểm tra:

- Không còn dependency cũ không tương thích.
- Không có hai version của Spring Framework hoặc thư viện nền tảng quan trọng.
- Dependency test không bị kéo vào runtime.
- Các resource auto-configuration và metadata có trong JAR.
- Các class được tham chiếu trong imports file thực sự tồn tại trong artifact.

## 10. Các lỗi thường gặp

1. **Chỉ đổi version Spring Boot.** Parent/plugin/BOM, Java, package, dependency và test support phải cùng được rà soát.
2. **Thay mọi `javax` thành `jakarta`.** Chỉ các API Jakarta EE đổi namespace; package Java SE như `javax.sql` vẫn giữ nguyên.
3. **Giữ dependency Java EE cũ cùng Jakarta API.** Hai namespace không tương thích về kiểu và có thể gây lỗi classpath hoặc runtime.
4. **Quên `AutoConfiguration.imports` khi nâng Boot 3.** Khóa `EnableAutoConfiguration` trong `spring.factories` không còn là cách đăng ký auto-configuration.
5. **Sửa import nhưng quên metadata.** Ordering, exclusion, reflection và file `spring.factories` vẫn có thể tham chiếu tên class cũ.
6. **Giữ starter deprecated trong Boot 4.** Chuyển sang starter mới như `spring-boot-starter-webmvc` và các starter có tiền tố `security`.
7. **Không tách test dependency.** Một test có thể thiếu MockMvc, RestTestClient, JDBC test support hoặc class test khác dù runtime dependency đã đúng.
8. **Tự ghim version Spring Framework bên cạnh BOM Boot.** Điều này có thể tạo một tập module không tương thích.
9. **Nâng Spring Cloud hoặc SDK ngoài BOM mà không kiểm tra matrix.** Dependency ngoài BOM có chu kỳ tương thích riêng.
10. **Để properties migrator trong production lâu dài.** Dùng nó để tìm và sửa property, rồi gỡ khỏi build.
11. **Dùng classic starter như giải pháp cuối.** Đây là bước chuyển tiếp; sau đó cần thay bằng starter/module cụ thể.
12. **Chỉ kiểm tra compile.** Lỗi runtime có thể xuất hiện ở servlet container, security filter, JSON mapper, database driver hoặc auto-configuration.
13. **Một artifact tự viết cố hỗ trợ cả Boot 3 và Boot 4.** Package và module API khác nhau; tách artifact theo dòng giúp kiểm soát tương thích.
14. **Không đọc release notes của dòng trung gian.** Các thay đổi property và dependency nhỏ có thể bị bỏ sót khi nhảy nhiều release.

## 11. Checklist trước khi đánh dấu migration hoàn tất

| Hạng mục | Tiêu chí đạt |
|---|---|
| Baseline | Đã nâng source line lên maintenance release mới nhất và xử lý deprecation |
| Java | JDK build, CI và runtime đáp ứng baseline của dòng đích |
| Build tools | Maven/Gradle Wrapper và plugin được hỗ trợ |
| BOM | Boot parent/plugin/BOM đồng bộ; không override framework tùy tiện |
| Jakarta | Import và dependency Jakarta đúng; không mass-replace Java SE `javax.*` |
| Packages | Import, reflection, metadata và class name được cập nhật |
| Auto-configuration | Imports file, `spring.factories`, ordering và exclusions hợp lệ |
| Starters | Starter runtime và test starter đúng với dòng đích |
| Dependencies | Dependency tree không còn version conflict hoặc artifact cũ |
| Properties | Property đã đổi tên/default được cập nhật; migrator đã gỡ |
| Tests | Unit, slice, integration và consumer smoke test đều đạt |
| Packaging | JAR/WAR chứa đúng class, resource và metadata |
| Runtime | Ứng dụng khởi động và smoke test trên môi trường gần production |
| Documentation | Version matrix, Java baseline và migration note được cập nhật |

## 12. Ghi nhớ

- Boot 2 sang Boot 3 là bước chuyển lớn sang Java 17, Spring Framework 6 và Jakarta EE; các API Jakarta chuyển từ `javax.*` sang `jakarta.*`.
- Boot 3 loại bỏ đăng ký auto-configuration qua key `EnableAutoConfiguration` trong `spring.factories`; dùng `AutoConfiguration.imports`.
- Boot 4 tiếp tục yêu cầu Java 17, chuyển sang Spring Framework 7/Jakarta EE 11 và module hóa package, module, starter.
- Boot 4 đổi tên một số starter, tách test starter và chuyển package của nhiều API; phải cập nhật source code lẫn metadata.
- Dùng BOM của dòng Boot đích để đồng bộ dependency; kiểm tra riêng Spring Cloud và thư viện ngoài BOM.
- Properties migrator và classic starter là công cụ chuyển tiếp; gỡ chúng sau khi migration hoàn tất.
- Với thư viện starter, duy trì artifact riêng cho Boot 3 và Boot 4 là hướng an toàn hơn việc nhồi hai API vào một artifact.
- Chỉ kết luận hoàn tất sau khi build, test, đóng gói và khởi động artifact thực tế đều đạt.

### Tài liệu chính thức

- Spring Boot 3.0 Migration Guide — Java 17, Spring Framework 6, Jakarta EE, imports file và dependency changes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Spring Boot 4.0 Migration Guide — module/package changes, starter/test starter, Jackson 3 và package migration: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Boot 4.0 System Requirements — Java, Spring Framework và build tools: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Upgrading Spring Boot — hướng dẫn nâng cấp theo từng dòng: https://docs.spring.io/spring-boot/3.4/upgrading.html
- Spring Boot Build Systems — dependency management và BOM: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
