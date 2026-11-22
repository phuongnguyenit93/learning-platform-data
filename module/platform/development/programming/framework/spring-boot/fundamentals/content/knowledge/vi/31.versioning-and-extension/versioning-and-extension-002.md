# Đọc tài liệu theo phiên bản đang chạy và kiểm tra API mới

Một trong những nguyên nhân gây lỗi khi phát triển Spring Boot là làm theo ví dụ trên Internet nhưng ví dụ đó thuộc phiên bản framework khác với project hiện tại. Một method có thể xuất hiện trong tài liệu mới nhưng chưa có trong thư viện mà ứng dụng đang dùng; một property có thể đã đổi tên; một starter có thể được tách hoặc thay thế; và một đoạn code có thể yêu cầu Java baseline mới hơn môi trường build.

Trước khi áp dụng một API mới, cần trả lời hai câu hỏi:

1. **Ứng dụng thực tế đang chạy phiên bản nào?**
2. **API hoặc tính năng muốn dùng có được hỗ trợ trong đúng tập dependency đó không?**

Trong chương **Phiên bản và mở rộng** của *Spring Boot Fundamentals*, bài học này hướng dẫn cách đọc tài liệu theo version, xác định phiên bản Spring Boot/Spring Framework và dependency runtime, tra cứu API reference, release notes, migration guide và kiểm chứng API mới bằng build/test thực tế.

Mục tiêu là hình thành một quy trình có thể lặp lại: **xác định runtime → chọn đúng bộ tài liệu → tìm version/API requirement → xác nhận dependency → thử compile và chạy → kiểm tra khả năng tương thích trước khi đưa vào ứng dụng**.

## 1. Vì sao phải đọc tài liệu theo phiên bản đang chạy?

Tài liệu framework thường được cập nhật liên tục. Trang tài liệu mặc định có thể hiển thị phiên bản mới nhất, trong khi project của bạn vẫn dùng một release cũ hơn.

Ví dụ:

```text
Project đang chạy:
  Spring Boot 3.1.x
  Spring Framework 6.0.x
  Java 17

Ví dụ tìm thấy trên Internet:
  Spring Boot release mới hơn
  Spring Framework release mới hơn
  Java baseline có thể khác

Kết quả:
  Code mẫu có thể gọi API chưa tồn tại trong classpath hiện tại.
```

Đây là sơ đồ minh họa, không phải bảng tương thích chính thức cho một project cụ thể. Version thực tế phải được lấy từ dependency management và runtime artifact của ứng dụng.

### 1.1. Một ví dụ rất thường gặp

Bạn tìm được đoạn code:

```java
var client = RestClient.create();
```

IDE báo không tìm thấy `RestClient` hoặc build thất bại. Có thể đoạn code thuộc Spring Framework release mới hơn release mà Spring Boot BOM của project đang quản lý.

Lúc này, có ba khả năng khác nhau:

- Project dùng Spring Framework quá cũ để có class/API đó.
- Dependency chứa API không nằm trên compile classpath.
- Project có nhiều version hoặc classpath bị lệch, khiến compiler/runtime nhìn thấy version khác nhau.

Chỉ nhìn code snippet không thể phân biệt ba khả năng này. Cần kiểm tra version và dependency graph.

### 1.2. Tài liệu mới không tự động áp dụng cho ứng dụng cũ

Một API xuất hiện trong tài liệu mới có thể:

- Chưa tồn tại ở release cũ.
- Chỉ có trong một module/starter riêng.
- Được thêm ở một minor release.
- Được đánh dấu experimental hoặc incubating.
- Đã deprecated hoặc thay thế trong release mới hơn.
- Có signature hoặc semantics khác giữa các release.

Vì vậy, khi tra cứu hãy chọn **tài liệu trùng version với project** trước, sau đó mới đọc release notes của những phiên bản mới hơn nếu đang cân nhắc nâng cấp.

## 2. Phân biệt các phiên bản trong một ứng dụng Spring Boot

Nói “project đang dùng Spring Boot 3” chưa đủ để xác định mọi API có sẵn. Một ứng dụng có nhiều lớp version:

| Thành phần | Ví dụ | Vì sao cần biết |
| --- | --- | --- |
| Spring Boot | 3.x.y | Release train, auto-configuration, starters, Boot APIs |
| Spring Framework | 6.x.y | Core container, MVC, WebFlux, transaction, validation integration |
| Java/JDK | 17, 21 | Language features, bytecode level, JVM APIs và toolchain |
| Spring Security | Version do BOM/constraints quản lý | Security DSL, filters và integration |
| Spring Data | Release tương ứng | Repository APIs và persistence integration |
| Hibernate | Version được quản lý hoặc override | JPA provider behavior và APIs |
| Jackson | Version được quản lý hoặc override | JSON serialization/deserialization APIs |
| Micrometer | Version được quản lý | Metrics/observations/tracing integration |
| Servlet container | Tomcat/Jetty/Undertow version | Servlet API và web runtime behavior |
| Third-party SDK | Version riêng của vendor | API và compatibility matrix của SDK |

### 2.1. Spring Boot version không phải Spring Framework version

Spring Boot sử dụng Spring Framework và quản lý một version tương thích thông qua dependency management. Ví dụ, một ứng dụng có thể dùng Spring Boot 3.x nhưng Spring Framework version cụ thể được BOM của Boot lựa chọn.

Nếu một API thuộc package `org.springframework.web.client`, cần kiểm tra version của Spring Framework artifact chứa API đó, chứ không chỉ nhìn version của starter web.

### 2.2. Starter không phải thư viện chứa toàn bộ API

`spring-boot-starter-web` là một starter giúp kéo các thành phần cần thiết cho web application. API bạn đang tìm có thể thuộc:

- Spring Framework module như `spring-web` hoặc `spring-webmvc`.
- Một thư viện bên thứ ba được starter kéo vào.
- Một starter riêng như validation, security hoặc data access.
- Một dependency mà project chưa khai báo.

Do đó, câu hỏi đúng không chỉ là “Boot version nào?” mà còn là **class/method nằm trong artifact nào và artifact version nào đang có trên classpath?**

### 2.3. Java version là một trục độc lập

Một API có thể tồn tại trong thư viện nhưng bytecode của thư viện yêu cầu Java runtime mới hơn. Khi đó lỗi có thể là `UnsupportedClassVersionError` hoặc build tool từ chối compile do toolchain.

Ngược lại, project dùng Java mới không tự làm xuất hiện API Spring mới nếu dependency vẫn cũ.

Hãy tách:

- **Java language/API level:** compiler và JDK mà source code được phép sử dụng.
- **Library API level:** class/method có trong dependency version nào.
- **Runtime JDK:** JVM thực tế dùng để chạy ứng dụng.

## 3. Xác định Spring Boot version của project

Nguồn đầu tiên nên xem là build configuration, sau đó xác nhận runtime nếu cần.

### 3.1. Maven: kiểm tra parent hoặc property

Một project dùng Spring Boot parent có thể khai báo:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>
```

Trong ví dụ, `3.x.y` chỉ là placeholder. Hãy đọc version thật trong `pom.xml` hoặc property được tham chiếu.

Một project không dùng Boot parent có thể import BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Không nên chỉ tìm `<version>` đầu tiên trong POM rồi kết luận. Project có thể có parent khác, nhiều module, properties hoặc import BOM ở cấp khác.

### 3.2. Maven: xem effective POM

Chạy:

```bash
./mvnw help:effective-pom
```

Trên Windows:

```powershell
.\mvnw.cmd help:effective-pom
```

Effective POM thể hiện cấu hình sau khi Maven áp dụng inheritance, properties và dependency management. Nó hữu ích khi version được định nghĩa trong parent hoặc một BOM mà file POM hiện tại không thể hiện trực tiếp.

### 3.3. Gradle: kiểm tra plugin và version catalog

Một project có thể khai báo Spring Boot Gradle plugin:

```groovy
plugins {
    id 'org.springframework.boot' version '3.x.y'
}
```

Hoặc lấy version từ Gradle version catalog:

```toml
[versions]
spring-boot = "3.x.y"

[plugins]
spring-boot = {
    id = "org.springframework.boot",
    version.ref = "spring-boot"
}
```

Nếu version được khai báo trong `settings.gradle`, convention plugin hoặc catalog, cần xem nguồn đó. Đừng suy ra Boot version từ một starter dependency riêng lẻ nếu project có plugin/BOM quản lý.

### 3.4. Kiểm tra phiên bản tại runtime

Có thể in version Spring Boot từ code:

```java
import org.springframework.boot.SpringBootVersion;

public class VersionReport {

    public static void printBootVersion() {
        System.out.println(
                "Spring Boot: " + SpringBootVersion.getVersion()
        );
    }
}
```

Và version Spring Framework:

```java
import org.springframework.core.SpringVersion;

public class FrameworkVersionReport {

    public static void printFrameworkVersion() {
        System.out.println(
                "Spring Framework: " + SpringVersion.getVersion()
        );
    }
}
```

Những phương thức này giúp quan sát phiên bản framework đang có trong runtime. Kết quả có thể phụ thuộc cách đóng gói và metadata của artifact; nếu trả về `null` hoặc không rõ, hãy kiểm tra package metadata, dependency graph và artifact.

### 3.5. Ghi nhận build version trong ứng dụng

Trong ứng dụng thực tế, nên đưa thông tin build vào artifact một cách có chủ đích. Với Maven Spring Boot plugin, có thể tạo build information; với Gradle, plugin cũng có cơ chế tương ứng theo version.

Khi build metadata được tạo và contributor phù hợp được bật, Actuator `info` có thể cung cấp một phần thông tin release/build. Ví dụ:

```properties
management.endpoints.web.exposure.include=health,info
```

Không nên công bố mọi metadata build ra public Internet. Chỉ đưa thông tin không nhạy cảm và giới hạn quyền truy cập phù hợp.

### 3.6. Version trong file build chưa chắc là artifact đang chạy

Một deployment có thể đang chạy:

- Image cũ vì pipeline chưa cập nhật tag.
- JAR cũ được copy vào container.
- Artifact từ một module khác.
- Một process khác đang giữ port.
- Profile/configuration khác với local.

Khi điều tra production, xác nhận **artifact/image digest hoặc build ID đang chạy**, không chỉ đọc `pom.xml` trong repository mới nhất.

## 4. Chọn đúng bộ tài liệu Spring Boot

Trang tài liệu chính thức của Spring Boot có các phần khác nhau:

- Reference Documentation: hướng dẫn cấu hình và sử dụng framework.
- API Documentation/Javadoc: class, interface, method, annotation và contract chi tiết.
- Release Notes: thay đổi giữa các release.
- Migration Guide: lưu ý khi nâng cấp giữa các dòng version.
- Dependency Versions: version thư viện được Spring Boot quản lý.

Điểm bắt đầu:

- <Link url="https://docs.spring.io/spring-boot/" title="Spring Boot documentation"/>.
- <Link url="https://docs.spring.io/spring-framework/reference/" title="Spring Framework reference"/>.
- <Link url="https://docs.spring.io/spring-boot/api/java/" title="Spring Boot API documentation"/>.

Các trang chính thức có thể thay đổi cách điều hướng theo release. Hãy dùng bộ chọn version hoặc đường dẫn version-specific trên trang tài liệu, thay vì giả định URL hiện tại luôn trỏ đến đúng release của project.

### 4.1. Tìm version selector

Khi mở Reference Documentation:

1. Xác định version đang được hiển thị trên trang.
2. Chọn đúng version của ứng dụng.
3. Mở nội dung tương ứng trong Reference Guide.
4. Mở API Javadoc cùng release nếu cần xem class/method.
5. Kiểm tra release notes/migration guide khi API chưa có hoặc đã thay đổi.

Nếu trang mặc định là “current” hoặc “latest”, điều đó không có nghĩa project của bạn cũng đang dùng release đó.

### 4.2. Không trộn Reference Guide và Javadoc của hai version

Reference Guide có thể mô tả cách cấu hình ở mức khái niệm. Javadoc mới hơn có thể liệt kê một method chưa tồn tại ở version cũ.

Khi một hướng dẫn nói “gọi method X”, hãy kiểm tra method X trong Javadoc **cùng version với dependency thực tế**. Nếu Javadoc chỉ có method ở bản mới, cần nâng cấp hoặc chọn cách làm tương thích.

### 4.3. Spring Boot docs và Spring Framework docs

Không phải API nào trong ứng dụng Spring Boot cũng thuộc Spring Boot.

Ví dụ:

- `@SpringBootApplication`: Spring Boot.
- `SpringApplication`: Spring Boot.
- `ApplicationContext`: Spring Framework.
- `@Transactional`: Spring Framework abstraction.
- `RestClient`: Spring Framework web client API.
- `@PreAuthorize`: Spring Security.
- `JpaRepository`: Spring Data.

Tra cứu đúng dự án tài liệu giúp tránh xem nhầm API version. Nếu API thuộc Spring Security, cần đọc tài liệu Spring Security và version được Boot quản lý.

## 5. Tìm thông tin API trong Javadoc

Khi muốn dùng một class hoặc method mới, API documentation là nơi xác nhận chính xác nhất.

### 5.1. Tìm class và package

Trước hết xác định:

- Tên đầy đủ của class/interface.
- Package.
- Artifact/module chứa nó.
- API có public hay chỉ là internal implementation.

Ví dụ:

```java
import org.springframework.web.client.RestClient;
```

Package cho biết API thuộc Spring Framework Web module. Từ đó, có thể kiểm tra version của artifact chứa class thay vì chỉ kiểm tra starter tổng.

### 5.2. Xem method signature

Javadoc cung cấp:

- Tên và visibility của method.
- Parameter types.
- Return type.
- Generic bounds.
- Checked exceptions nếu được khai báo.
- Overloads.
- Contract và side effects được mô tả.

Hai method cùng tên có thể có signature khác nhau. Đừng chỉ tìm tên method rồi kết luận API đã tồn tại.

### 5.3. Tìm @since

Javadoc thường có thông tin `Since` hoặc `@since` cho biết API được thêm từ release nào.

Ví dụ minh họa:

```java
/**
 * Creates a client with default settings.
 *
 * @since 6.1
 */
public static RestClient create() {
    // ...
}
```

Đây chỉ là minh họa cách Javadoc biểu diễn version, không phải trích nguyên văn tài liệu một API cụ thể.

Nếu API được đánh dấu từ Spring Framework 6.1, hãy xác nhận ứng dụng thực tế có Spring Framework version tương thích hay không. Không suy ra rằng mọi Spring Boot 3.x đều có API đó; các minor Boot releases có thể quản lý Framework versions khác nhau.

### 5.4. Kiểm tra deprecated và forRemoval

Javadoc/annotation có thể cho biết API đã deprecated:

```java
@Deprecated(since = "x.y", forRemoval = true)
public void oldOperation() {
    // ...
}
```

Các thuộc tính `since` và `forRemoval` giúp đánh giá hướng di chuyển:

- `since`: API bị deprecated từ version nào.
- `forRemoval`: dự kiến loại bỏ trong một release tương lai theo contract của API.
- `@deprecated` Javadoc: thường có hướng dẫn API thay thế.

Không nên bắt đầu một implementation mới dựa trên API đã deprecated nếu có lựa chọn được khuyến nghị.

### 5.5. Kiểm tra API public hay internal

Không phải class nào có thể import cũng là API được hỗ trợ lâu dài. Một số package có thể chứa implementation detail, internal helper hoặc class phục vụ auto-configuration.

Trước khi phụ thuộc trực tiếp:

1. Xem package và module.
2. Đọc Javadoc/class description.
3. Xem API có được tài liệu hướng dẫn chính thức sử dụng không.
4. Kiểm tra annotation/versioning policy nếu thư viện công bố.
5. Ưu tiên public abstraction được thiết kế cho application code.

Một class internal có thể đổi hoặc bị xóa mà không theo cùng compatibility promise với public API.

## 6. Release notes và migration guide trả lời câu hỏi gì?

Javadoc cho biết một API cụ thể. Release notes cho biết **điều gì đã thay đổi giữa các phiên bản**.

Khi muốn dùng API mới, hãy tìm:

- API được thêm từ release nào?
- Có module/dependency nào mới cần thêm không?
- API thay thế một API cũ hay bổ sung chức năng?
- Có behavior change hoặc breaking change không?
- Có yêu cầu JDK tối thiểu mới không?
- Có thay đổi default configuration không?
- Có migration action bắt buộc không?

### 6.1. Release notes

Release notes hữu ích khi:

- Nâng minor/patch version.
- Thêm một feature mới.
- Tìm API đã được giới thiệu ở đâu.
- Điều tra behavior khác giữa hai bản.
- Tìm bug fix hoặc known issue.

Hãy đọc release notes của **đúng dòng thư viện**. Một thay đổi trong Spring Framework có thể được phát hành độc lập về mặt version với Spring Boot.

### 6.2. Migration guide

Migration guide thường tổng hợp những thay đổi cần xử lý khi chuyển giữa các dòng release:

- Java baseline.
- Package namespace.
- Removed/deprecated APIs.
- Configuration properties đổi tên.
- Default behavior thay đổi.
- Auto-configuration changes.
- Dependency/module changes.

Khi nâng cấp Spring Boot major version, đừng chỉ xem release notes của một patch release. Đọc migration guidance cho toàn bộ bước chuyển giữa các major line mà project phải đi qua.

### 6.3. Dependency versions appendix

Spring Boot documentation có phần liệt kê dependency versions được quản lý. Đây là nơi hữu ích để biết Boot release đang quản lý phiên bản nào của Spring Framework, Jackson, Hibernate, Micrometer và các thư viện khác.

Tuy nhiên, project có thể override BOM. Vì vậy, bảng version của Boot chỉ là **mốc quản lý mặc định**, còn dependency tree/runtime artifact mới cho biết project đang thực sự dùng gì.

### 6.4. Compatibility matrix của hệ sinh thái liên quan

Nếu project dùng Spring Cloud, Spring Security, Spring Data hoặc SDK bên thứ ba, hãy xem compatibility information của chính thành phần đó.

Ví dụ:

- Spring Cloud release train tương thích với Spring Boot line nào?
- Spring Security DSL nào có trong version đang dùng?
- Spring Data module yêu cầu Spring Framework/JDK nào?
- SDK của vendor hỗ trợ Boot/Jakarta/JDK nào?

Không nên chỉ dùng Boot BOM rồi cho rằng mọi thư viện ngoài hệ sinh thái đã được kiểm chứng tương thích.

## 7. Phân biệt stable, snapshot, milestone và release candidate

Trang tài liệu có thể dẫn tới nhiều loại phiên bản:

| Loại | Ý nghĩa chung | Cách sử dụng |
| --- | --- | --- |
| Stable release | Bản phát hành ổn định | Phù hợp với ứng dụng thông thường theo policy của project |
| Snapshot | Bản phát triển thay đổi theo thời gian | Dùng thử có kiểm soát, không xem là API ổn định |
| Milestone (M) | Bản thử nghiệm theo mốc phát triển | Đánh giá sớm tính năng, có thể thay đổi |
| Release Candidate (RC) | Bản ứng viên trước release chính thức | Kiểm thử/feedback trước phát hành |
| GA | General Availability, bản phát hành chính thức | Có thể dùng theo compatibility/support policy |

Ví dụ version suffix có thể chứa `-SNAPSHOT`, `-M1`, `-RC1`. Đừng nhầm những bản này với stable release chỉ vì số version chính giống nhau.

### 7.1. Vì sao snapshot docs nguy hiểm khi làm theo?

Một snapshot có thể:

- Có method chưa được đưa vào GA.
- Đổi signature trước release.
- Có property/configuration tạm thời.
- Chưa có migration guidance cuối cùng.

Nếu project đang dùng stable release, đừng dựa vào snapshot Javadoc để quyết định API có sẵn.

### 7.2. API mới có thể chưa được support như API ổn định

Một số tính năng được đánh dấu incubating/experimental hoặc có contract hạn chế. Hãy đọc trạng thái API và compatibility policy trước khi đưa vào một thư viện dùng lâu dài.

## 8. Kiểm tra API mới theo một quy trình có thể lặp lại

Khi tìm thấy API mới, thực hiện theo thứ tự:

### Bước 1 — Ghi rõ API cần dùng

Không ghi chung chung “muốn dùng tính năng mới”. Hãy xác định:

```text
Class / annotation / method / property / endpoint:
Fully qualified name:
Expected module/artifact:
Documentation version:
First available version (if documented):
Replacement/deprecation status:
```

### Bước 2 — Xác định version runtime hiện tại

Đọc build file, BOM, dependency graph và xác nhận artifact đang chạy. Nếu cần, in `SpringBootVersion.getVersion()` và `SpringVersion.getVersion()` trong môi trường tái hiện.

### Bước 3 — Xác định API thuộc artifact nào

Tìm package/class trong API docs và dependency metadata. Nếu API nằm trong `spring-web`, việc project có `spring-boot-starter-web` chưa đủ để chứng minh version của `spring-web` có method đó.

### Bước 4 — Đối chiếu @since và release notes

Xác nhận version đầu tiên có API và xem release notes/migration guide cho những thay đổi liên quan.

### Bước 5 — Kiểm tra dependency graph thực tế

Dùng Maven dependency tree hoặc Gradle dependency insight để xác nhận version được chọn trên compile/runtime classpath.

### Bước 6 — Kiểm tra signature bằng Javadoc hoặc javap

Nếu Javadoc không rõ, kiểm tra JAR thực tế. Xác nhận class/method/signature đúng trong artifact được resolve.

### Bước 7 — Viết một compile probe nhỏ

Tạo một class/test tối giản chỉ sử dụng API cần thử. Build với đúng project dependencies. Nếu compile fail, kiểm tra module/version trước khi sửa code.

### Bước 8 — Chạy test trên runtime artifact

Compile pass chưa đủ. Chạy unit/integration test và nếu cần chạy executable JAR hoặc container image giống cách triển khai.

### Bước 9 — Đánh giá migration và compatibility

Nếu cần nâng dependency, kiểm tra các thư viện liên quan, Java baseline, release train và behavior changes.

### Bước 10 — Ghi nhận lựa chọn version

Giữ dependency management tập trung, cập nhật lockfile/CI nếu project dùng và ghi rõ lý do override khi có.

## 9. Kiểm tra API bằng dependency graph Maven

Maven dependency tree giúp xác định artifact và version mà project resolve.

### 9.1. Xem dependency tổng thể

```bash
./mvnw dependency:tree
```

### 9.2. Lọc module chứa API

Ví dụ nếu API thuộc Spring Web:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-web
```

Nếu API thuộc Spring Core:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-core
```

Tên artifact ở đây là ví dụ; cần xác định module thực sự chứa class đang tra cứu.

### 9.3. Xem effective POM

```bash
./mvnw help:effective-pom
```

Kiểm tra:

- Boot parent/BOM version.
- Dependency management override.
- Explicit dependency version.
- Exclusions.
- Scope.
- Profile thay đổi dependency.

### 9.4. Xác nhận compile/runtime scope

Nếu API compile được nhưng runtime lỗi, tạo hoặc xem classpath runtime:

```bash
./mvnw dependency:build-classpath -Dmdep.outputFile=runtime-classpath.txt
```

Nếu API thuộc dependency chỉ có trong test hoặc provided scope, nó có thể không có trong artifact runtime. Xem scope và cách đóng gói trước khi kết luận API không được hỗ trợ.

### 9.5. Không override version chỉ để compiler hết đỏ

Nếu một API chưa có trong Boot-managed Framework version, có thể nâng Spring Boot release phù hợp hoặc chọn cách triển khai tương thích với version hiện tại.

Pin riêng `spring-web` lên một version mới hơn có thể làm lệch `spring-core`, `spring-context` và các module khác. Chỉ override một module khi có compatibility evidence và test đầy đủ.

## 10. Kiểm tra API bằng dependency insight của Gradle

Gradle có thể cho biết vì sao một version được chọn.

### 10.1. Xem runtime graph

```bash
./gradlew dependencies --configuration runtimeClasspath
```

### 10.2. Xem lý do chọn module

```bash
./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath
```

Output giúp thấy:

- Version được chọn.
- Version được yêu cầu từ các dependency khác.
- Constraint/platform tham gia.
- Lý do chọn version.

### 10.3. So sánh compile và runtime

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Nếu API có trên compile classpath nhưng không có trên runtime, cần kiểm tra configuration và dependency declaration.

### 10.4. Kiểm tra test runtime

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Một test có thể pass vì dependency chỉ có trong test runtime. Điều đó không chứng minh application runtime có thể dùng API.

### 10.5. Dependency locking

Nếu project bật dependency locking, lockfile ghi nhận version đã resolve. Khi thêm API mới, cần cập nhật lock state theo workflow của project và review thay đổi.

Locking giúp build tái lập, nhưng không tự chứng minh API tương thích. Vẫn phải đối chiếu docs và kiểm thử.

## 11. Dùng javap để xác minh class và method

Javadoc là nguồn tham khảo API tốt, nhưng khi cần biết **JAR đang có thật sự chứa method nào**, công cụ `javap` rất hữu ích.

### 11.1. Xác định JAR chứa class

Trước tiên tìm artifact trong dependency tree. Sau đó dùng đường dẫn JAR trong Maven/Gradle cache hoặc extracted artifact.

Ví dụ:

```bash
jar tf spring-web.jar | grep 'RestClient.class'
```

Trên PowerShell:

```powershell
jar tf spring-web.jar |
    Select-String 'RestClient.class'
```

### 11.2. Xem public methods

```bash
javap -classpath spring-web.jar org.springframework.web.client.RestClient
```

Để xem thêm member và descriptor:

```bash
javap -classpath spring-web.jar -p -s org.springframework.web.client.RestClient
```

`javap` giúp kiểm tra bytecode/API trong JAR cụ thể. Nó không thay thế Javadoc về semantics, lifecycle hoặc cách sử dụng được khuyến nghị.

### 11.3. So sánh hai version

Nếu muốn biết method được thêm ở release nào, tải/resolve hai version trong một môi trường thử nghiệm rồi chạy `javap` trên từng JAR.

```bash
javap -classpath spring-web-old.jar -p org.springframework.web.client.RestClient
javap -classpath spring-web-new.jar -p org.springframework.web.client.RestClient
```

Không nên chỉ nhìn method name; so sánh parameter types, return type, visibility và inheritance.

### 11.4. JAR đúng phải là JAR runtime sử dụng

Nếu máy có nhiều version trong local repository, kiểm tra nhầm JAR có thể dẫn đến kết luận sai. Lấy version từ dependency report và class origin thực tế trước khi chạy `javap`.

## 12. Viết compile probe để thử một API mới

Một compile probe là một ví dụ nhỏ chỉ tập trung vào API đang muốn sử dụng. Nó giúp tách vấn đề version/API khỏi business code phức tạp.

Ví dụ một class thử:

```java
package com.example.apiprobe;

import org.springframework.web.client.RestClient;

public class RestClientProbe {

    public RestClient createClient() {
        return RestClient.create();
    }
}
```

Nếu project hiện tại chưa có class/method này, compiler sẽ chỉ rõ symbol không tồn tại.

### 12.1. Compile probe với Maven

Đặt class trong source của một module thử nghiệm dùng đúng parent/BOM và dependencies của ứng dụng, rồi chạy:

```bash
./mvnw -pl catalog-service -am test
```

Hoặc build module chứa probe theo cấu trúc project. Không tạo một project tạm dùng version mới nhất rồi dùng kết quả đó để kết luận ứng dụng chính cũng hỗ trợ API.

### 12.2. Compile probe với Gradle

```bash
./gradlew :catalog-service:compileJava
```

Dùng đúng subproject và dependency configuration. Nếu API chỉ nằm trong test source, dùng task compile test tương ứng.

### 12.3. Probe cần đúng dependency set

Nếu compile probe thêm trực tiếp một version mới của `spring-web`, nó có thể compile thành công nhưng không phản ánh ứng dụng đang chạy với BOM hiện tại.

Một probe có giá trị khi nó dùng **chính dependency management của module ứng dụng**.

### 12.4. Compile thành công chưa đủ

Nếu compile với version mới nhưng runtime artifact lại nạp version cũ, có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.

Sau compile probe, xác nhận runtime graph và chạy test/runtime artifact tương ứng.

## 13. Kiểm tra API dạng configuration property

Không phải API mới nào cũng là Java method. Spring Boot có nhiều configuration properties được bind từ file YAML/properties.

Ví dụ:

```yaml
spring:
  application:
    name: catalog-service
```

Khi muốn dùng một property mới, hãy xác định:

- Property thuộc Boot, Framework hay thư viện khác?
- Nó được thêm từ version nào?
- Có deprecated alias hoặc tên cũ không?
- Property có điều kiện theo classpath/feature không?
- Type và default value là gì?
- Có cần bật một endpoint/feature khác để property có tác dụng không?

### 13.1. Configuration metadata

Spring Boot configuration metadata thường được đóng gói trong resource:

```text
META-INF/spring-configuration-metadata.json
```

Metadata có thể mô tả:

- Property name.
- Type.
- Description.
- Default value.
- Deprecation information.
- Hints cho IDE.

IDE autocomplete dựa vào metadata có thể giúp khám phá property, nhưng **autocomplete không thay thế tài liệu của đúng version**. Một property có thể tồn tại trong cache IDE nhưng không có trong dependency runtime hiện tại.

### 13.2. Xác nhận property được bind

Với property do ứng dụng tự định nghĩa:

```java
@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        int pageSize,
        Duration timeout
) {
}
```

Có thể test binding bằng Spring Boot configuration properties test support hoặc một context nhỏ với property values:

```java
new ApplicationContextRunner()
        .withUserConfiguration(CatalogPropertiesConfiguration.class)
        .withPropertyValues(
                "app.catalog.page-size=50",
                "app.catalog.timeout=2s"
        )
        .run(context -> {
            assertThat(context).hasNotFailed();
            CatalogProperties properties =
                    context.getBean(CatalogProperties.class);
            assertThat(properties.pageSize()).isEqualTo(50);
        });
```

Đây là ví dụ test cho property của ứng dụng. Khi kiểm tra property framework mới, cần bảo đảm đúng configuration class/auto-configuration đang đọc nó.

### 13.3. Property sai tên có thể bị bỏ qua

Một property không được bind không phải lúc nào cũng làm startup thất bại. Nếu property không có consumer, ứng dụng có thể khởi động nhưng feature không hoạt động như mong đợi.

Hãy kiểm tra metadata/Javadoc, binding object, condition evaluation và behavior thực tế. Không dựa vào việc ứng dụng “không báo lỗi” để kết luận property được hỗ trợ.

## 14. Kiểm tra annotation hoặc feature mới

Một annotation có thể tồn tại trong package nhưng chỉ hoạt động khi một processor, registrar hoặc auto-configuration tương ứng được kích hoạt.

Ví dụ một annotation:

```java
@SomeNewFeature
public class FeatureConfiguration {
}
```

Chỉ compile thành công chưa chứng minh feature đã được bật. Hãy kiểm tra:

1. Annotation thuộc artifact nào.
2. Annotation được xử lý bởi framework/processor nào.
3. Cần import configuration hay starter nào.
4. Feature có điều kiện theo property/classpath/profile không.
5. Có test context chứng minh bean/behavior mong đợi xuất hiện không.

### 14.1. API annotation có thể là marker hoặc có semantics

Một số annotation chỉ đánh dấu metadata; annotation khác được đọc bởi component scanner, AOP, bean factory, validation engine hoặc compiler processor.

Đọc Javadoc và reference section để hiểu **ai xử lý annotation**. Đừng giả định cứ đặt annotation lên class là framework tự thực hiện chức năng.

### 14.2. Kiểm tra auto-configuration

Nếu feature dựa trên Boot auto-configuration, xem:

- Điều kiện `@ConditionalOnClass`.
- Điều kiện `@ConditionalOnProperty`.
- Điều kiện `@ConditionalOnBean`/`@ConditionalOnMissingBean`.
- Những dependency cần có.
- Condition evaluation report khi ứng dụng khởi động.

Một API có mặt nhưng auto-configuration không match thì feature vẫn có thể không hoạt động.

## 15. Kiểm tra endpoint hoặc Actuator feature mới

Một endpoint có thể cần nhiều điều kiện:

- Actuator dependency.
- Endpoint implementation có trong version.
- Endpoint được enable.
- Endpoint được expose qua HTTP/JMX.
- Security cho phép truy cập.

Ví dụ một request 404 có thể do endpoint chưa được expose hoặc base path khác; không nhất thiết là endpoint không tồn tại trong version.

### 15.1. Tách ba câu hỏi

| Câu hỏi | Cách xác minh |
| --- | --- |
| Endpoint có trong version không? | Reference docs/Javadoc/release notes |
| Endpoint có được enable/expose không? | `management.*` configuration và mappings |
| Người gọi có quyền truy cập không? | Security configuration và HTTP response |

### 15.2. Kiểm tra cấu hình theo version

Một property management có thể thay đổi giữa các release. Dùng property appendix hoặc configuration metadata cùng version. Không copy nguyên cấu hình từ blog cũ nếu không biết release nào được dùng.

## 16. Ví dụ cụ thể: đánh giá RestClient API

Giả sử team muốn dùng `RestClient` thay vì một HTTP client abstraction cũ.

### 16.1. Xác định API owner

`RestClient` là API của Spring Framework, thuộc module web/client tương ứng. Vì vậy cần kiểm tra version của Spring Framework artifact chứa class.

### 16.2. Đối chiếu release

Tài liệu/Javadoc của Spring Framework cho biết API này được giới thiệu từ dòng 6.1. Hãy kiểm tra Boot BOM của project đang quản lý Spring Framework 6.1 hay không; không suy luận từ nhãn “Spring Boot 3” chung chung.

### 16.3. Kiểm tra dependency

Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-web
```

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-web --configuration compileClasspath
```

Xác nhận version được chọn có chứa API.

### 16.4. Compile probe

```java
import org.springframework.web.client.RestClient;

class RestClientProbe {
    RestClient client() {
        return RestClient.create();
    }
}
```

Compile probe bằng đúng project build. Nếu compile thành công, tiếp tục kiểm tra runtime classpath và test.

### 16.5. Quyết định

Nếu version hiện tại chưa có API:

- Nâng Spring Boot lên release quản lý Spring Framework phù hợp, sau khi kiểm tra migration/compatibility.
- Hoặc tiếp tục dùng API client hiện tại cho đến khi có kế hoạch nâng cấp.
- Tránh pin riêng `spring-web` nếu chưa đánh giá các module Spring Framework còn lại.

Điểm quan trọng không phải ghi nhớ một con số version cụ thể, mà là xác minh API owner, release requirement và dependency thực tế.

## 17. Ví dụ: tìm API mới trong Spring Security

Giả sử một ví dụ hướng dẫn sử dụng DSL mới trong `HttpSecurity`.

Không nên:

1. Copy code.
2. Thấy IDE đỏ.
3. Thêm version Spring Security mới nhất trực tiếp.
4. Coi compile pass là đã hoàn tất.

Thay vào đó:

1. Xác định class/method trong Spring Security.
2. Mở Spring Security reference/API docs cùng version.
3. Xem method `@since`, deprecation và migration notes.
4. Kiểm tra version Spring Security được Boot BOM quản lý.
5. Xem dependency tree để biết có override hay không.
6. Viết security configuration test với MockMvc hoặc context phù hợp.
7. Xác nhận request được authorize/deny đúng behavior.

### 17.1. API DSL có thể thay đổi semantics

Hai đoạn code có thể compile nhưng không nhất thiết tương đương về authorization behavior. Khi thay API security, cần test:

- Request anonymous.
- User đã xác thực.
- Role/authority đúng.
- Role/authority thiếu.
- CSRF nếu áp dụng.
- Filter ordering và exception handling.

Compile probe chỉ xác nhận API tồn tại, không xác nhận security policy đúng.

## 18. Đọc tài liệu khi API bị deprecated

Một API đã deprecated vẫn có thể compile và chạy, nhưng không nên bỏ qua cảnh báo.

Quy trình:

1. Mở Javadoc của API.
2. Đọc `@Deprecated` và `@deprecated` description.
3. Xác định version bắt đầu deprecated.
4. Tìm API thay thế.
5. Đọc migration guide/release notes.
6. Kiểm tra API thay thế có trong version hiện tại hay cần nâng cấp.
7. Thay đổi và viết test xác nhận behavior tương đương.

### 18.1. Deprecated không đồng nghĩa đã bị xóa

API deprecated thường vẫn tồn tại trong một hoặc nhiều release. Tuy nhiên, code mới nên ưu tiên replacement được khuyến nghị.

### 18.2. forRemoval cần được chú ý

Nếu API được đánh dấu `forRemoval = true`, cần lên kế hoạch loại bỏ khỏi code trước khi nâng cấp tới release có thể xóa API.

### 18.3. Replacement có thể có semantics khác

Không phải lúc nào thay method cũ bằng method mới cùng tên gần giống cũng giữ nguyên behavior. Hãy đọc Javadoc và test các case thực tế, đặc biệt với:

- Null handling.
- Default values.
- Exception behavior.
- Ordering.
- Thread-safety.
- Resource lifecycle.
- Transaction boundaries.
- Security semantics.

## 19. Đọc tài liệu property theo version

Configuration properties là nguồn lỗi tương thích phổ biến vì property có thể được thêm, đổi tên hoặc thay default.

### 19.1. Tìm property trong reference guide

Tra cứu đúng section của feature, ví dụ web, data, logging, Actuator, security integration. Kiểm tra property name và ví dụ cấu hình cùng version.

### 19.2. Tìm trong configuration metadata

Trong dependency JAR, metadata có thể ở:

```text
META-INF/spring-configuration-metadata.json
```

Có thể liệt kê nội dung JAR và đọc file metadata. Khi một property không có trong metadata, nó chưa chắc không tồn tại (một số property được tạo theo cách khác), nhưng đó là dấu hiệu cần tra cứu thêm.

### 19.3. Kiểm tra default value

Default behavior có thể thay đổi giữa releases. Một ứng dụng không khai báo property có thể hoạt động khác sau nâng cấp dù source code không đổi.

Đọc migration guide/release notes để tìm default changes, sau đó quyết định có cần khai báo tường minh property hay không.

### 19.4. Không copy cấu hình từ blog mà bỏ qua prefix

Một property có thể đã được chuyển từ prefix cũ sang prefix mới hoặc được thay bằng cấu hình khác. Kiểm tra property deprecation metadata và migration notes.

## 20. Đọc tài liệu theo phiên bản trong môi trường nhiều module

Một hệ thống có thể có:

```text
root/
  catalog-service
  order-service
  notification-service
  shared-library
```

Không mặc định tất cả module dùng cùng dependency graph:

- Mỗi executable service có thể có Boot plugin/BOM riêng.
- Shared library có thể không dùng Spring Boot.
- Test module có thể có test dependencies khác.
- Một service có thể nâng version trước service khác.

### 20.1. Xác định đúng module đang chạy

Khi đọc tài liệu cho `catalog-service`, xem POM/Gradle configuration của module đó. Không chỉ nhìn root build file nếu module override dependency.

### 20.2. Shared library cần compatibility range rõ

Nếu `shared-library` dùng API Spring Framework mới, những service tiêu thụ library phải có version tương thích. Một library compile thành công trong repository của nó không đảm bảo mọi consumer có thể chạy nó.

Hãy xác định:

- Java baseline.
- Spring Framework/Spring Boot baseline nếu library phụ thuộc trực tiếp.
- API public mà library expose.
- Dependency scope và optional dependencies.
- Consumer compatibility tests.

### 20.3. Tránh để library kéo framework version không kiểm soát

Một shared library thường nên tránh ép version Spring Framework/Spring Boot cho ứng dụng tiêu thụ nếu không có lý do. Có thể dùng dependency management phù hợp, khai báo dependency scopes và để application platform quản lý release train.

Thiết kế chính xác tùy loại library (Spring Boot starter, auto-configuration module hay plain Java library).

## 21. API compatibility và versioning

Khi sử dụng một API, cần biết mức độ ổn định và loại thay đổi mà nhà phát triển thư viện cam kết.

### 21.1. Source compatibility

Source compatibility nghĩa là source code cũ vẫn compile được với version mới (trong phạm vi contract được xét).

### 21.2. Binary compatibility

Binary compatibility nghĩa là bytecode đã compile trước đó vẫn có thể liên kết và chạy với version mới theo contract.

Một API thay đổi có thể giữ source gần giống nhưng vẫn ảnh hưởng binary descriptor, hoặc ngược lại.

### 21.3. Behavioral compatibility

API vẫn compile và link nhưng behavior có thể thay đổi:

- Default timeout.
- Null handling.
- Exception type.
- Ordering.
- Retry behavior.
- Serialization output.
- Security defaults.

Do đó, kiểm tra API không dừng ở việc class/method tồn tại.

### 21.4. Semantic compatibility

Một method vẫn nhận cùng tham số nhưng ý nghĩa có thể đổi. Ví dụ một property trước đây là timeout cho từng request, sau đó được diễn giải là timeout tổng của operation. Javadoc/release notes và integration tests mới giúp phát hiện.

## 22. Kiểm tra API mới trong CI

Nếu một project thường xuyên cập nhật framework, nên đưa kiểm tra version/API vào workflow:

1. Build với dependency management đã review.
2. Compile main/test source.
3. Unit tests.
4. Context startup tests.
5. Integration tests cho các API mới.
6. Package executable JAR.
7. Chạy smoke test trên artifact đã đóng gói.
8. Kiểm tra dependency graph và vulnerability/compatibility policy.

### 22.1. Vì sao test context quan trọng?

Một API có thể compile nhưng auto-configuration không được kích hoạt vì thiếu condition/dependency. Context test giúp xác nhận bean/configuration thực tế được tạo.

### 22.2. Vì sao test artifact quan trọng?

Test chạy trên test classpath. Executable JAR chạy trên runtime classpath đã đóng gói. Smoke test artifact giúp phát hiện dependency bị thiếu hoặc version mismatch.

### 22.3. API mới nên có regression test

Nếu team nâng cấp để dùng một method/property mới, hãy thêm test thể hiện behavior mà team cần. Điều đó bảo vệ ứng dụng khi framework hoặc dependency tiếp tục được nâng cấp.

## 23. Các công cụ hỗ trợ tra cứu

| Công cụ | Câu hỏi nó trả lời |
| --- | --- |
| Spring Boot Reference Guide | Feature/configuration được dùng thế nào trong release cụ thể? |
| Spring Framework Reference Guide | API/framework behavior thuộc Framework ra sao? |
| Javadoc | Class/method/annotation có signature và contract gì? |
| Release notes | Release thêm, đổi hoặc sửa gì? |
| Migration guide | Cần thay đổi gì khi nâng cấp? |
| Dependency versions appendix | Boot BOM quản lý version nào? |
| Maven `dependency:tree` | Dependency nào kéo artifact/version vào? |
| Maven `help:effective-pom` | Parent/BOM/properties tạo cấu hình cuối ra sao? |
| Gradle `dependencyInsight` | Vì sao Gradle chọn version này? |
| `javap` | JAR cụ thể có class/method descriptor nào? |
| IDE autocomplete | Gợi ý API/property theo classpath hiện tại của IDE |
| Compile probe | Source có compile với dependency set hiện tại không? |
| Context/integration test | API/feature có hoạt động trong Spring context/runtime không? |

Không công cụ nào thay thế hoàn toàn các công cụ còn lại. Chúng cung cấp bằng chứng ở những lớp khác nhau.

## 24. Nguồn tài liệu nên ưu tiên

Khi xác định API hoặc behavior, ưu tiên theo thứ tự:

1. **Tài liệu chính thức cùng version** của project thư viện.
2. **Javadoc cùng version** cho signature và API contract.
3. **Release notes/migration guide chính thức** cho lịch sử thay đổi.
4. **Dependency metadata và source JAR** tương ứng với artifact đã resolve.
5. Ví dụ chính thức và sample repository cùng release.
6. Blog, Q&A hoặc video như nguồn giải thích bổ sung.

Các nguồn cộng đồng có thể rất hữu ích, nhưng cần xác minh version của snippet. Một câu trả lời đúng với Spring Boot 2 có thể không còn phù hợp với Boot 3 hoặc release mới hơn.

### 24.1. Khi đọc blog hoặc Stack Overflow

Ghi nhận:

- Ngày đăng và lần cập nhật.
- Spring Boot version được tác giả dùng.
- Spring Framework version.
- Java version.
- Dependency versions.
- API được hỏi có còn deprecated/removed không.

Nếu thiếu những thông tin này, hãy coi code snippet là gợi ý cần kiểm chứng.

### 24.2. Khi đọc GitHub source

Nếu cần hiểu implementation:

- Chọn đúng tag/release, không chỉ branch `main`.
- Xem source của artifact version đang dùng.
- Phân biệt public API với implementation detail.
- Kiểm tra commit/release note liên quan.

Branch phát triển có thể đã chứa code chưa phát hành.

## 25. Những lỗi thường gặp khi đọc tài liệu sai version

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| IDE không tìm thấy class | API chưa có hoặc thiếu module | Javadoc, dependency graph, JAR contents |
| IDE có class nhưng build CI không có | IDE cache/classpath khác build | Chạy Maven/Gradle compile trong CI-like environment |
| Compile pass nhưng runtime `NoSuchMethodError` | Runtime nạp version cũ/khác | Runtime graph, class origin, `javap` |
| Property không có tác dụng | Property chưa tồn tại, sai prefix hoặc condition không match | Reference docs, metadata, binding/conditions |
| Endpoint trả 404 | Endpoint không tồn tại, disabled, không expose hoặc sai base path | Docs, `management.*`, mappings |
| Bean không được auto-configure | Thiếu dependency/property hoặc condition không match | Conditions report và dependency graph |
| API deprecated warning | Code đang dùng API cũ | Javadoc và migration guide |
| `UnsupportedClassVersionError` | Runtime JDK không hỗ trợ bytecode | Java toolchain và runtime version |
| Behavior khác sau upgrade | Default/semantic change | Release notes, migration guide, integration tests |
| Chỉ lỗi trong executable JAR | Runtime packaging khác IDE/test | Inspect nested JARs và chạy đúng artifact |

## 26. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Trang docs mặc định là version của project.” | Trang có thể hiển thị release mới nhất; phải chọn version đúng |
| “Spring Boot version chính là Spring Framework version.” | Boot quản lý một version Framework tương thích; hai version khác nhau |
| “Có starter web là mọi API web mới đều có.” | API phụ thuộc module và version cụ thể |
| “Java 21 thì dùng được mọi API Spring mới.” | Java level và library API level là hai trục độc lập |
| “Javadoc mới nhất mô tả runtime hiện tại.” | Cần Javadoc của artifact version đang resolve |
| “Có `@since` là chắc chắn classpath đã có API.” | `@since` chỉ cho biết release giới thiệu; project vẫn phải có đúng module/version |
| “IDE autocomplete có nghĩa runtime có API.” | IDE có thể dùng classpath/cache khác với artifact |
| “Compile probe pass là ứng dụng chạy được.” | Cần kiểm tra runtime linkage, auto-configuration và behavior |
| “Dependency tree resolved nghĩa API tương thích.” | Resolution không chứng minh binary/behavioral compatibility |
| “Boot BOM quản lý mọi dependency bên thứ ba.” | BOM chỉ quản lý các artifact trong phạm vi của nó |
| “Deprecated nghĩa API đã bị xóa.” | Deprecated thường vẫn tồn tại nhưng cần migration plan |
| “Release notes chỉ dành cho người viết framework.” | Release notes giúp ứng dụng biết API/default/compatibility changes |
| “Một blog cũ vẫn đúng vì code Java compile.” | Code có thể phụ thuộc API/configuration của version khác |

## 27. Bài tập thực hành

### Bài tập 1 — Xác định version thật

Mở một Spring Boot project:

1. Tìm Boot version trong Maven parent/BOM hoặc Gradle plugin/catalog.
2. In `SpringBootVersion.getVersion()` khi chạy.
3. In `SpringVersion.getVersion()`.
4. Kiểm tra Java build và runtime version.
5. Ghi lại các version thành một bảng.

Giải thích vì sao Boot version và Framework version không nhất thiết giống nhau.

### Bài tập 2 — Đọc đúng Reference Guide

Chọn một feature đang dùng trong project, ví dụ validation, Actuator hoặc Spring MVC.

1. Mở docs chính thức.
2. Chọn version tương ứng với project.
3. Mở cùng section trong version mới hơn.
4. Ghi lại những điểm khác nhau.

Không thay dependency trong project ở bài tập này.

### Bài tập 3 — Tra API mới

Chọn một class/method mới trong Spring Framework hoặc Spring Boot.

1. Tìm fully qualified name.
2. Xác định artifact/module.
3. Đọc `@since`.
4. Xác nhận version dependency của project.
5. Viết compile probe.

Giải thích vì sao chỉ nhìn version “Spring Boot 3” là chưa đủ.

### Bài tập 4 — Maven dependency tree

Chạy:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-web
```

Xác định version `spring-web` được chọn, dependency path và nguồn quản lý version.

### Bài tập 5 — Gradle dependencyInsight

Chạy:

```bash
./gradlew dependencyInsight --dependency spring-web --configuration runtimeClasspath
```

Ghi lại version requested, selected và selection reason. So sánh với `compileClasspath`.

### Bài tập 6 — Kiểm tra method bằng javap

Tìm một class trong JAR đã resolve. Chạy:

```bash
javap -classpath path/to/library.jar -p -s fully.qualified.ClassName
```

Tìm method muốn dùng và xác nhận parameter/return descriptor.

### Bài tập 7 — Đọc deprecation

Tìm một API deprecated trong project. Ghi lại:

- Deprecated since.
- For removal hay không.
- Replacement được đề xuất.
- Replacement có trong version hiện tại không.

Viết một test chứng minh behavior sau khi thay thế.

### Bài tập 8 — Configuration property mới

Chọn một property trong tài liệu Boot mới hơn. Kiểm tra nó có trong metadata của dependency hiện tại không, tìm `@since`/release note nếu có, rồi thử trong một context test.

Giải thích vì sao property sai tên có thể không làm startup fail.

### Bài tập 9 — Kiểm tra endpoint

Chọn một Actuator endpoint. Xác định:

- Endpoint có trong version không?
- Dependency nào cần có?
- Có cần enable không?
- Có cần expose không?
- Security policy là gì?

Thử các response khác nhau trong môi trường local được bảo vệ.

### Bài tập 10 — So sánh docs với artifact

Đọc Javadoc của một version mới và so sánh với JAR đang có trong Maven/Gradle cache bằng `javap`.

Tìm một API chỉ có trong version mới. Giải thích vì sao source code không thể gọi nó khi project đang dùng version cũ.

### Bài tập 11 — Kiểm tra executable JAR

Build project và kiểm tra `BOOT-INF/lib`. Xác nhận artifact chứa version thư viện đúng với dependency report. Chạy `java -jar` và gọi một code path sử dụng API vừa thêm.

### Bài tập 12 — Lập kế hoạch nâng cấp

Giả sử team muốn sử dụng một API mới nhưng version hiện tại chưa hỗ trợ. Viết kế hoạch:

1. Boot target version.
2. Java baseline.
3. Framework/dependency version changes.
4. Migration guide cần đọc.
5. Dependency overrides cần bỏ hoặc cập nhật.
6. Tests phải chạy.
7. Artifact cần xác minh.

## 28. Mẫu ghi chú khi đánh giá một API mới

Trước khi đưa API vào code production, có thể ghi một bản đánh giá ngắn:

```text
Feature/API:
Fully qualified name:
Owning project/module:
Artifact:
Current Spring Boot version:
Current Spring Framework version:
Current Java runtime:
API first available version:
Javadoc/reference version checked:
Release note / migration note:
Deprecated/experimental status:
Compile classpath version:
Runtime classpath version:
Required additional dependency:
Compatibility concerns:
Compile probe result:
Context/integration test result:
Executable artifact result:
Decision:
```

Mẫu này đặc biệt hữu ích khi review pull request nâng dependency hoặc thêm một API chưa được dùng trong codebase.

## 29. Quy trình nâng cấp khi API chưa có trong version hiện tại

Nếu đã xác nhận API không có trong dependency hiện tại, có ba hướng chính:

### 29.1. Giữ version hiện tại và dùng API thay thế

Phù hợp khi:

- Chức năng mới chưa thật sự bắt buộc.
- Nâng cấp kéo theo nhiều breaking changes.
- Thư viện liên quan chưa tương thích.
- Project đang trong giai đoạn ổn định release.

Ưu điểm là giữ dependency graph hiện tại ổn định. Nhược điểm là chưa tận dụng API mới.

### 29.2. Nâng Spring Boot theo release train

Phù hợp khi:

- API mới có trong một Boot release đã phát hành.
- Java baseline đáp ứng.
- Các dependency chính có compatibility.
- Team có thời gian chạy migration/integration tests.

Quy trình:

1. Chọn Boot target version.
2. Đọc release notes và migration guide.
3. Kiểm tra Java/JDK baseline.
4. Kiểm tra Spring Cloud và vendor compatibility.
5. Cập nhật Boot parent/plugin/BOM.
6. Xóa các version override không còn cần.
7. Chạy dependency reports.
8. Build/test/package.
9. Chạy executable artifact.

### 29.3. Override một dependency riêng lẻ

Đây là lựa chọn có rủi ro cao hơn, chỉ nên cân nhắc khi:

- Biết chính xác module chứa API.
- Có compatibility guidance cho tổ hợp version.
- Các module liên quan có thể giữ tương thích.
- Có integration tests bao phủ code path.
- Có lý do rõ ràng chưa thể nâng toàn Boot release train.

Không nên override một module Spring Framework chỉ vì IDE báo thiếu method rồi hy vọng các module còn lại vẫn tương thích.

## 30. Cách đọc tài liệu khi nâng major version

Nâng major version cần đánh giá rộng hơn việc tìm một method mới.

### 30.1. Kiểm tra baseline

Xác định Java minimum, build tool version, container/servlet API, framework line và dependency release train.

### 30.2. Tìm breaking changes

Đọc migration guide và release notes qua từng bước nâng cấp. Ghi lại API removed, package rename, behavior changes và default changes.

### 30.3. Kiểm tra source compatibility

Compile source sau khi cập nhật dependency. Sửa deprecation/removal và API signature changes.

### 30.4. Kiểm tra runtime compatibility

Chạy test, kiểm tra dependency graph và chạy executable artifact. Những lỗi linkage có thể chỉ xuất hiện khi một code path cụ thể được gọi.

### 30.5. Kiểm tra behavior

Test configuration defaults, serialization, security, transactions, database access, scheduling và web request behavior.

### 30.6. Không bỏ qua thư viện bên thứ ba

Một ứng dụng có thể nâng Spring Boot thành công nhưng SDK cũ chưa hỗ trợ Jakarta hoặc Java baseline mới. Hãy xác minh compatibility matrix của từng integration quan trọng.

## 31. Những giới hạn của việc tra cứu API

### 31.1. Tài liệu có thể không liệt kê mọi chi tiết runtime

Một số behavior phụ thuộc classpath, auto-configuration conditions, profile, environment và infrastructure. Javadoc một class không mô tả toàn bộ runtime composition.

### 31.2. API có mặt không đồng nghĩa feature được bật

Class có thể compile nhưng feature cần một starter, property, bean hoặc auto-configuration khác.

### 31.3. Version report có thể thiếu chính xác nếu artifact bị đóng gói đặc biệt

Package implementation version có thể null hoặc không phản ánh tất cả module. Dependency graph và artifact inspection vẫn cần thiết.

### 31.4. Docs current không phải compatibility guarantee

Trang current mô tả release hiện hành theo tài liệu, không phải cam kết API tồn tại trong mọi release cũ.

### 31.5. Compile success không bảo đảm binary compatibility

Compile probe xác nhận source code có thể biên dịch với compile classpath. Runtime vẫn có thể nạp version khác hoặc thiếu dependency.

## 32. Tổng kết

**Đọc tài liệu theo phiên bản đang chạy là bước bắt buộc trước khi áp dụng API mới vào ứng dụng Spring Boot.** Một API có thể được giới thiệu trong Spring Framework, Spring Security, Spring Data hoặc thư viện khác; nó không tự động có mặt chỉ vì project dùng một version Spring Boot có cùng major number.

Hãy ghi nhớ:

1. Xác định **Spring Boot, Spring Framework, Java và các dependency quan trọng** đang thực sự chạy.
2. Phân biệt version trong build file với version được resolve và version có trong artifact đang deploy.
3. Chọn đúng Reference Guide và Javadoc theo release; tránh vô tình dùng tài liệu `current` cho project cũ.
4. Đọc `@since`, deprecation, release notes, migration guide và compatibility matrix.
5. Xác định **API owner và artifact/module** chứa class hoặc method.
6. Dùng Maven dependency tree hoặc Gradle dependency insight để kiểm tra version được chọn.
7. Dùng `javap` khi cần xác nhận class/method descriptor trong JAR thực tế.
8. Viết compile probe bằng đúng dependency management của ứng dụng.
9. Kiểm tra runtime, auto-configuration và behavior bằng integration tests/artifact smoke tests.
10. Khi cần API mới, ưu tiên nâng Boot theo release train tương thích; chỉ override module riêng khi có bằng chứng và kiểm thử đầy đủ.

Một quy tắc làm việc hữu ích là: **không áp dụng một snippet chỉ vì nó xuất hiện trong tài liệu mới nhất; hãy xác nhận nó thuộc đúng thư viện, đúng version và đúng runtime classpath của ứng dụng.** Thói quen đó giúp tránh lỗi compile, linkage, configuration và những thay đổi behavior khó phát hiện khi nâng cấp Spring Boot.
