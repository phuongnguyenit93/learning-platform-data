# Ứng dụng không khởi động do Boot và Cloud không tương thích

## 1. Nhận diện lỗi tương thích ngay từ startup

Spring Boot và Spring Cloud phát hành theo hai nhịp version khác nhau. Spring Boot dùng version dạng `4.1.2`, còn Spring Cloud dùng release train dạng `2025.1.4`. Hai version này không cần giống nhau; chúng phải thuộc cặp đã được Spring công bố là tương thích.

Khi chọn sai release train, ứng dụng có thể dừng ngay lúc khởi động với thông báo tương tự:

```text
APPLICATION FAILED TO START

Your project setup is incompatible with our requirements
due to the following reasons:

- Spring Boot [4.x.y] is not compatible with this Spring Cloud release train

Action:
- Change Spring Boot version to one of the compatible versions
  listed by the Spring Cloud release train.
```

Thông báo này thường đến từ **Spring Cloud Compatibility Verifier**. Verifier kiểm tra version Spring Boot đang có trên classpath với các version mà release train chấp nhận. Nó giúp phát hiện cặp version không được hỗ trợ trước khi ứng dụng đi sâu vào quá trình khởi tạo.

Tuy nhiên, không phải mọi lỗi khởi động đều là lỗi release train. `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, `UnsupportedClassVersionError` hoặc lỗi tạo bean có thể bắt nguồn từ dependency bị ghi đè, JDK quá cũ, starter thiếu hoặc cấu hình không đúng. Bài học này hướng dẫn phân biệt các nhóm lỗi trước khi sửa version.

## 2. Hiểu hai hệ thống version độc lập

Spring Boot và Spring Cloud có trách nhiệm quản lý những phần khác nhau:

- Spring Boot cung cấp nền tảng ứng dụng, auto-configuration, embedded server, dependency management và plugin build.
- Spring Cloud bổ sung các abstraction và integration cho hệ thống phân tán như Config, Discovery, LoadBalancer, Gateway, Circuit Breaker, Bus và OpenFeign.
- Spring Boot BOM quản lý Spring Framework, logging, JSON, server và nhiều dependency bên thứ ba theo một tập hợp đã được kiểm thử.
- Spring Cloud release train BOM quản lý version các module Spring Cloud để chúng hoạt động đồng bộ với một thế hệ Spring Boot cụ thể.

Một ứng dụng có thể dùng Spring Boot `4.1.2` cùng Spring Cloud `2025.1.4`. Đây là cặp version hợp lệ theo ma trận tương thích hiện hành. Không cần và không nên cố tìm một version Spring Cloud có số `4.1.2`.

## 3. Tra cứu ma trận tương thích trước khi thay đổi dependency

Tại thời điểm biên soạn (18-11-2026), trang Spring Cloud công bố Spring Cloud `2025.1.4` là release train GA mới nhất. Bảng tương thích chính thức ghi:

| Spring Cloud release train | Spring Boot tương thích | Ghi chú |
| --- | --- | --- |
| `2025.1.x` Oakwood | `4.0.x`; `4.1.x` từ `2025.1.2` | Release train GA hiện hành |
| `2025.0.x` Northfields | `3.5.x` | Tương thích theo ma trận; trang dự án đánh dấu EOL bằng dấu `*` |
| `2024.0.x` Moorgate | `3.4.x` | Đã hết OSS support |
| `2023.0.x` Leyton | `3.2.x`, `3.3.x` từ `2023.0.2` | Đã hết OSS support |
| `2022.0.x` Kilburn | `3.0.x`, `3.1.x` từ `2022.0.3` | Đã hết OSS support |
| `2021.0.x` Jubilee | `2.6.x`, `2.7.x` từ `2021.0.3` | Đã hết OSS support |

Các release train cũ hơn cũng có bảng mapping riêng nhưng không còn nằm trong chính sách hỗ trợ OSS. Nếu đang bảo trì hệ thống cũ, hãy kiểm tra support status và kế hoạch nâng cấp trước khi tiếp tục dùng chúng.

Spring Cloud `2026.0.0-RC2` hiện là bản preview và công bố hỗ trợ Spring Boot `4.2.0-RC2`. Đây không phải GA release. Không dùng cặp RC này cho production chỉ để giải quyết verifier error trên một ứng dụng đang dùng Boot GA.

Quy tắc đọc bảng:

1. Chọn dòng theo version Spring Boot của ứng dụng.
2. Chọn release train Spring Cloud tương ứng.
3. Nếu bảng có ghi điều kiện như “Starting with 2025.1.2”, phải dùng service release từ mốc đó trở lên.
4. Trong cùng release train, ưu tiên service release GA mới nhất còn được hỗ trợ.
5. Kiểm tra support lifecycle của từng module Cloud nếu ứng dụng dùng module có lịch hỗ trợ riêng.

Không chọn release train chỉ dựa vào tên codename hoặc version số lớn hơn. Một release train mới có thể yêu cầu thế hệ Spring Boot mới hơn.

## 4. Spring Cloud Compatibility Verifier hoạt động ra sao?

Compatibility Verifier thuộc Spring Cloud Commons. Nó phát hiện version Spring Boot trên classpath và so sánh với danh sách version được release train chấp nhận. Khi không tương thích, verifier tạo báo cáo giải thích version hiện tại và các version được chấp nhận.

Property chính:

| Property | Tác dụng |
| --- | --- |
| `spring.cloud.compatibility-verifier.enabled` | Bật hoặc tắt bước xác minh tương thích |
| `spring.cloud.compatibility-verifier.compatible-boot-versions` | Ghi đè danh sách version Boot được verifier chấp nhận |

Để chủ động bật kiểm tra trong dự án:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Hành vi mặc định và metadata của property có thể khác giữa các phiên bản Spring Cloud. Khi cần verifier chạy chắc chắn trong CI hoặc môi trường phát triển, khai báo rõ `true` thay vì dựa vào giả định từ một bài viết cũ.

Nếu dùng release train chuẩn, hãy để danh sách tương thích do release train cung cấp. Không tự thêm version Boot vào `compatible-boot-versions` chỉ để làm mất thông báo lỗi. Việc đó chỉ thay đổi điều kiện mà verifier chấp nhận; nó không chứng minh các API, auto-configuration hoặc dependency thực sự tương thích.

Ví dụ ghi đè danh sách chỉ phù hợp khi tổ chức đang duy trì một bản Spring Cloud fork hoặc một tổ hợp đã được kiểm thử và có trách nhiệm hỗ trợ riêng:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
      compatible-boot-versions: "4.0.x,4.1.x"
```

Không dùng cấu hình trên như cách sửa nhanh cho một ứng dụng thông thường. Nếu phải ghi đè, cần có tài liệu giải thích vì sao tổ hợp đó hợp lệ, test tích hợp bao phủ các module liên quan và người chịu trách nhiệm bảo trì.

## 5. Xác định version thực tế đang chạy

Không chỉ đọc version khai báo trong `pom.xml` hoặc `build.gradle`. Dependency có thể bị parent POM, BOM khác, Gradle constraint, version catalog hoặc dependency bắc cầu ghi đè.

Hãy xác định ít nhất bốn nhóm version:

- Spring Boot plugin/parent version.
- Spring Boot runtime artifacts thực tế, ví dụ `spring-boot`, `spring-boot-autoconfigure`.
- Spring Cloud release train BOM.
- Spring Cloud module thực tế, ví dụ `spring-cloud-commons`, `spring-cloud-config`, `spring-cloud-netflix`.

Nếu log có `SpringBootVersion` trong manifest, hãy đối chiếu với version trong dependency graph. Version trên file build và version runtime cần khớp với nhau.

Một dự án có thể khai báo Boot `4.1.2` nhưng do dependency management hoặc module khác kéo `spring-boot-autoconfigure` version khác. Khi đó, chỉ nhìn property version ở đầu file sẽ không phát hiện được vấn đề.

## 6. Sửa version bằng Maven

Maven nên dùng Spring Boot parent hoặc import Spring Boot BOM, sau đó import đúng một Spring Cloud release train BOM. Ví dụ sau dùng Boot `4.1.2` với Cloud `2025.1.4`:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
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
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Đây là ví dụ cấu trúc dependency management. Hãy kiểm tra Java baseline theo đúng bản Spring Boot và toolchain của dự án trước khi chọn `java.version`.

Các điểm cần lưu ý:

- `spring-cloud-dependencies` là BOM quản lý version; nó không tự đưa tất cả Spring Cloud module vào classpath.
- Mỗi starter mà ứng dụng thực sự dùng vẫn phải khai báo trong `<dependencies>`.
- Không ghi version riêng cho từng Spring Cloud starter nếu BOM đã quản lý.
- Không import đồng thời nhiều release train Cloud khác nhau.
- Không dùng parent POM của một release train Cloud cũ cùng BOM của release train mới nếu không có lý do cụ thể và kiểm thử đầy đủ.

Nếu dự án không dùng Spring Boot parent, có thể import `spring-boot-dependencies` BOM và `spring-cloud-dependencies` BOM trong `dependencyManagement`. Đảm bảo thứ tự và các override được xem xét rõ ràng.

## 7. Sửa version bằng Gradle

Với Gradle Kotlin DSL, có thể dùng native BOM support để quản lý cả Boot và Cloud:

```kotlin
plugins {
    id("org.springframework.boot") version "4.1.2"
    java
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:4.1.2")
    )
    implementation(
        platform("org.springframework.cloud:spring-cloud-dependencies:2025.1.4")
    )

    implementation("org.springframework.cloud:spring-cloud-starter-config")
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
}
```

Gradle cũng có thể dùng plugin `io.spring.dependency-management`. Nếu chọn cách đó, cấu hình Spring Boot plugin và Cloud BOM theo tài liệu Spring Boot Gradle Plugin. Không trộn hai cách quản lý dependency mà không hiểu thứ tự ưu tiên và constraint được áp dụng.

### 7.1. Kiểm tra version catalog và dependency constraints

Nếu dự án dùng `gradle/libs.versions.toml`, kiểm tra các alias Spring Boot và Spring Cloud có đang khai báo version riêng hay không. Một version catalog có thể giữ version cũ dù BOM mới đã được cập nhật ở nơi khác.

Tìm cả các khai báo:

- `version`
- `strictly`
- `prefer`
- `force`
- `resolutionStrategy`
- `enforcedPlatform`
- `constraints`

Một constraint hoặc `force` ở root project có thể thắng version mà BOM dự định quản lý. Đừng xóa tất cả constraint một cách máy móc; xác định dependency nào cần override và vì sao.

## 8. Những lỗi thường gặp khi trộn BOM

| Cấu hình sai | Hậu quả có thể gặp | Cách xử lý |
| --- | --- | --- |
| Boot 4.1.x nhưng dùng Cloud 2025.1.0 | Release train chưa hỗ trợ Boot 4.1.x | Dùng Cloud 2025.1.2 trở lên |
| Boot 3.5.x nhưng dùng Cloud 2025.1.x | Khác thế hệ Boot được release train hỗ trợ | Dùng Cloud 2025.0.x |
| Import Cloud 2025.0 và 2025.1 cùng lúc | Module Cloud có thể bị resolve về các version không đồng bộ | Chỉ import một release train |
| Khai báo version riêng cho `spring-cloud-commons` | Commons có thể lệch với Config, Consul, Netflix hoặc Gateway | Bỏ version riêng và để Cloud BOM quản lý |
| Ghi đè `spring-core` hoặc `spring-context` bằng version tùy ý | Spring Framework API có thể không còn đồng bộ với Boot | Trả về version do Boot BOM quản lý |
| Dùng starter cũ qua dependency bắc cầu | Classpath có thể chứa module cũ không mong muốn | Dùng dependency tree tìm đường kéo vào và cập nhật/exclude có chủ đích |
| Chỉ nâng Boot plugin nhưng không nâng runtime BOM | Build plugin và dependency runtime lệch thế hệ | Cập nhật đồng bộ Boot parent/BOM và Cloud BOM |

Spring Boot BOM và Spring Cloud BOM có phạm vi quản lý khác nhau. Boot BOM quản lý các Spring Framework module và nhiều thư viện nền tảng; Cloud BOM quản lý các module Spring Cloud. Không nên tự ép tất cả dependency về cùng một số version.

## 9. Đọc lỗi trong stack trace để tìm đúng nguyên nhân

Thông báo đầu tiên thường chỉ cho biết ứng dụng không khởi động. Nguyên nhân cụ thể thường nằm ở phần `Caused by` sâu hơn.

| Dấu hiệu | Ý nghĩa thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| `Spring Boot [...] is not compatible with this Spring Cloud release train` | Compatibility Verifier từ chối cặp Boot/Cloud | Ma trận release train và BOM |
| `NoSuchMethodError` | Code được biên dịch với API khác version runtime đang nạp | Spring Framework, Boot và Cloud artifacts bị trộn |
| `NoSuchFieldError` | Runtime class không có field mà caller mong đợi | Dependency version override |
| `NoClassDefFoundError` | Class có lúc compile nhưng thiếu ở runtime, hoặc static initialization thất bại | Runtime classpath, optional dependency và nguyên nhân khởi tạo |
| `ClassNotFoundException` | Class loader không tìm thấy class theo tên | Dependency thiếu, class name sai hoặc classloader boundary |
| `AbstractMethodError` | Implementation runtime không đáp ứng method contract mà caller mong đợi | Module API và implementation lệch version |
| `UnsupportedClassVersionError` | JDK runtime quá cũ để đọc bytecode | Java runtime, toolchain và target bytecode |
| `NoSuchBeanDefinitionException` | Bean không được tạo hoặc không có trong context | Starter, auto-configuration condition, profile và component scan |
| `BeanDefinitionOverrideException` | Có bean trùng tên hoặc behavior override thay đổi | Cấu hình ứng dụng và thay đổi auto-configuration |
| Gradle `No matching variant` | Variant không phù hợp với attributes như JVM version, usage hoặc platform | JDK, Gradle metadata và dependency attributes |
| Maven `Could not resolve artifact` | Không tải được artifact hoặc version/repository không tồn tại | Coordinates, repository, proxy và dependency version |

Không kết luận `NoSuchBeanDefinitionException` luôn do Boot/Cloud incompatibility. Nó cũng có thể do ứng dụng thiếu starter, chưa kích hoạt cấu hình, profile sai hoặc condition không thỏa mãn.

## 10. Phân biệt lỗi Boot/Cloud với lỗi JDK và build tool

Ma trận Spring Boot/Spring Cloud không thay thế yêu cầu Java runtime và build tool.

Ví dụ:

- `UnsupportedClassVersionError` chỉ ra bytecode cần Java mới hơn runtime hiện tại.
- Gradle wrapper quá cũ có thể không chạy được plugin hoặc JDK mới.
- Maven Compiler Plugin có thể đặt `release` thấp hơn hoặc cao hơn JDK thực tế.
- Native library hoặc thư viện bên thứ ba có thể có yêu cầu OS/architecture riêng.
- Một Spring Cloud module có thể tương thích release train nhưng dependency bên thứ ba của ứng dụng vẫn đã hết hỗ trợ.

Khi gặp lỗi, ghi lại kết quả:

```bash
java -version
./mvnw -version
./gradlew --version
```

Chạy lệnh tương ứng với build tool của dự án. Nếu CI và máy local dùng JDK khác nhau, so sánh cả `JAVA_HOME`, toolchain và Gradle/Maven wrapper version.

## 11. Kiểm tra dependency tree bằng Maven

Lệnh sau cho biết dependency graph đã resolve:

```bash
./mvnw dependency:tree
```

Thu hẹp kết quả vào các group liên quan:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:*,org.springframework:*,org.springframework.cloud:*
```

Dùng verbose để xem cả các dependency bị loại do conflict:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework.boot:*,org.springframework:*,org.springframework.cloud:*
```

Xuất effective POM để kiểm tra parent, BOM và version được quản lý:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Khi đọc kết quả, tìm:

- Nhiều version của `spring-boot`, `spring-boot-autoconfigure`.
- Nhiều version Spring Framework như `spring-core`, `spring-context`, `spring-beans`.
- Cloud module nằm ở release train khác.
- Version do dependency bắc cầu mang vào.
- Dependency bị `omitted for conflict` hoặc version bị quản lý bởi một BOM không mong muốn.

Không sửa bằng cách thêm exclusion cho đến khi biết dependency nào kéo version sai. Exclusion có thể làm mất class mà module khác đang cần.

## 12. Kiểm tra dependency graph bằng Gradle

Liệt kê dependency runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Kiểm tra riêng một dependency để biết version được chọn và lý do:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Nếu lỗi chỉ xảy ra trong test, kiểm tra `testRuntimeClasspath`. Nếu lỗi chỉ xảy ra lúc compile, kiểm tra `compileClasspath`. Một dependency có thể được resolve khác nhau giữa các configuration.

Với multi-module project, chạy lệnh ở đúng module hoặc chỉ định project path, ví dụ:

```bash
./gradlew :inventory-service:dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
```

Không chỉ kiểm tra root project: mỗi module có thể import BOM hoặc áp dụng constraint riêng.

## 13. Quy trình sửa lỗi theo thứ tự an toàn

Thực hiện theo thứ tự sau để tránh thay đổi quá nhiều version cùng lúc:

1. **Lưu toàn bộ lỗi startup**: giữ thông báo `APPLICATION FAILED TO START`, các dòng đầu và chuỗi `Caused by`.
2. **Xác định Boot thực tế**: kiểm tra parent/plugin và version trong dependency graph.
3. **Xác định Cloud release train**: tìm BOM đang import và version Cloud module được resolve.
4. **Tra ma trận chính thức**: xác định cặp Boot/Cloud được hỗ trợ và support status.
5. **Chọn một release train**: dùng đúng BOM của train tương ứng, ưu tiên service release GA mới nhất.
6. **Gỡ version pin thừa**: bỏ version riêng của Spring Cloud module nếu BOM quản lý.
7. **Kiểm tra dependency bắc cầu**: dùng dependency tree/insight để tìm artifact cũ hoặc version bị force.
8. **Kiểm tra JDK và wrapper**: đảm bảo toolchain phù hợp với Spring Boot.
9. **Build lại từ đầu**: chạy clean build sau khi đã sửa cấu hình dependency.
10. **Chạy test và startup smoke test**: kiểm tra auto-configuration, web context và các integration Cloud đang dùng.
11. **Kiểm tra log verifier**: giữ kiểm tra tương thích trong CI để phát hiện regression sớm.

Chỉ thay một nhóm version tại một thời điểm. Nếu vừa nâng Boot, Cloud, JDK, Gradle, Netty và HTTP client cùng lúc, sẽ khó xác định thay đổi nào đã giải quyết hoặc tạo ra lỗi.

## 14. Ví dụ chọn release train theo Spring Boot

### 14.1. Ứng dụng dùng Spring Boot 4.1.x

Chọn Spring Cloud `2025.1.2` trở lên. Ví dụ cấu hình GA hiện hành:

```xml
<properties>
    <spring-boot.version>4.1.2</spring-boot.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>
```

Nếu dùng Spring Boot parent, version Boot được khai báo trong `<parent>`; property trên chỉ để minh họa mối liên hệ giữa hai version.

### 14.2. Ứng dụng dùng Spring Boot 3.5.x

Spring Cloud `2025.0.x` là release train được ghép với Boot `3.5.x`, nhưng trang dự án hiện đánh dấu train này EOL bằng dấu `*`. Nếu phải duy trì ứng dụng cũ, dùng patch cuối đã phát hành và xác nhận chính sách hỗ trợ của tổ chức; lập kế hoạch nâng Boot/Cloud lên một cặp GA còn được hỗ trợ. Không ghép Cloud 2025.1 với Boot 3.5 chỉ vì đây là release train mới hơn.

### 14.3. Ứng dụng dùng Spring Boot 3.4.x hoặc cũ hơn

Spring Cloud `2024.0.x` từng được ghép với Boot `3.4.x`, nhưng release train này đã hết OSS support theo bảng hiện hành. Các train 2023.0.x và cũ hơn cũng có tình trạng EOL được công bố.

Nếu cần tiếp tục duy trì hệ thống cũ, kiểm tra hỗ trợ thương mại hoặc lập kế hoạch nâng Boot và Cloud theo một lộ trình có test. Không nâng riêng Boot lên major mới trong khi giữ nguyên Cloud train cũ.

## 15. Khi nào có thể tắt Compatibility Verifier?

Trong dự án thông thường, không nên tắt verifier để che lỗi tương thích.

Tắt verifier bằng:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: false
```

chỉ nên được cân nhắc tạm thời khi:

- Đang xác minh một tổ hợp tùy biến có bản vá riêng.
- Đã có test integration chứng minh các module cần dùng hoạt động.
- Đã xác định rõ verifier đang từ chối vì danh sách version mặc định chưa bao gồm version Boot đã được kiểm thử.
- Có kế hoạch loại bỏ override hoặc duy trì fork một cách có trách nhiệm.

Tắt verifier không sửa `NoSuchMethodError`, không bổ sung class bị thiếu và không làm API tương thích trở lại. Nếu chưa có bằng chứng, hãy giữ verifier bật và sửa cặp version trước.

## 16. Những nguyên nhân không nằm ở release train

Ngay cả khi Boot/Cloud BOM đúng, ứng dụng vẫn có thể lỗi vì:

- Một thư viện bên thứ ba kéo Spring Framework hoặc Reactor version khác.
- Một starter đã bị thay thế bằng module không tương thích.
- Profile production kích hoạt auto-configuration khác profile local.
- Cấu hình conditional bean không còn thỏa mãn sau khi nâng version.
- Java runtime, Gradle wrapper hoặc Maven plugin không đáp ứng yêu cầu của Boot.
- Classpath có hai implementation của cùng một API.
- Ứng dụng dùng API đã deprecated rồi bị loại bỏ trong major release.

Do đó, sau khi xác nhận release train đúng, hãy đọc root cause và dependency graph thay vì tiếp tục đổi version ngẫu nhiên.

## 17. Kiểm thử sau khi căn chỉnh version

Một build thành công chỉ chứng minh compile/package hoàn tất. Cần chạy thêm các kiểm tra sau:

| Kiểm tra | Điều cần xác nhận |
| --- | --- |
| Unit tests | Logic nghiệp vụ và cấu hình không bị ảnh hưởng |
| Application context test | ApplicationContext khởi tạo với bean graph đúng |
| Auto-configuration test | Starter và conditional configuration được kích hoạt đúng |
| Config Client integration | Ứng dụng đọc được cấu hình theo profile/application |
| Discovery integration | Đăng ký và lookup service hoạt động |
| LoadBalancer/Feign/Gateway | Request tới service được resolve đúng |
| Actuator health | Health contributor không bị thiếu hoặc báo trạng thái sai |
| Runtime smoke test | Ứng dụng khởi động trên JDK và môi trường gần production |
| CI dependency report | Không xuất hiện version Spring Boot/Framework/Cloud ngoài dự kiến |

Nếu dùng nhiều profile hoặc nhiều module Cloud, test tối thiểu một context cho từng cấu hình quan trọng. Một ứng dụng chỉ có Config Client có thể khởi động được dù Eureka/Gateway module khác vẫn bị lệch version.

## 18. Ghi nhận version để ngăn lỗi quay lại

Sau khi sửa, ghi lại:

- Spring Boot version.
- Spring Cloud release train và service release.
- JDK vendor/version.
- Maven/Gradle wrapper version.
- Các module Spring Cloud được dùng.
- Các dependency override có lý do rõ ràng.
- Kết quả dependency tree hoặc Gradle dependency insight.

Dùng dependency locking hoặc dependency verification nếu quy trình build yêu cầu tái lập. Trong CI, có thể lưu dependency report như build artifact để so sánh khi nâng version.

Khi nâng cấp, đọc release notes của cả Spring Boot và Spring Cloud. Một cặp version nằm trong cùng ma trận không có nghĩa mọi behavior trong ứng dụng sẽ không thay đổi; major release vẫn có thể loại bỏ API cũ hoặc đổi auto-configuration.

## 19. Bảng chẩn đoán nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng sửa |
| --- | --- | --- |
| Verifier báo Boot không tương thích | Boot version và Cloud release train | Chọn đúng Cloud BOM theo ma trận |
| Boot 4.1.x nhưng Cloud 2025.1.0 | Mốc hỗ trợ 4.1.x | Nâng Cloud lên 2025.1.2+ |
| Boot 3.5.x nhưng Cloud 2025.1.x | Release train đang dùng | Dùng Cloud 2025.0.x |
| `NoSuchMethodError` trong `org.springframework.*` | Version Framework thực tế | Gỡ override và dùng Boot BOM |
| `NoSuchMethodError` trong `org.springframework.cloud.*` | Các Cloud module đã resolve | Đồng bộ theo một Cloud BOM |
| `NoClassDefFoundError` chỉ ở runtime | `runtimeClasspath`/Maven runtime tree | Bổ sung dependency đúng scope hoặc bỏ exclusion sai |
| `UnsupportedClassVersionError` | `java -version` và class file version | Nâng JDK runtime hoặc build target phù hợp |
| Gradle `No matching variant` | Gradle attributes và Java toolchain | Đồng bộ Gradle wrapper, JDK và plugin |
| Maven không resolve BOM | Effective POM, repository, version | Sửa coordinates/repository hoặc dùng release đã phát hành |
| Verifier không báo lỗi nhưng app vẫn fail | Root cause và dependency graph | Chẩn đoán API/classpath/auto-configuration cụ thể |

## 20. Checklist trước khi kết luận đã sửa xong

- [ ] Đã đọc toàn bộ chuỗi `Caused by`, không chỉ dòng `APPLICATION FAILED TO START`.
- [ ] Đã xác định Spring Boot version thực tế trên runtime classpath.
- [ ] Đã xác định duy nhất Spring Cloud release train BOM.
- [ ] Đã đối chiếu cặp version với bảng tương thích chính thức.
- [ ] Đã kiểm tra service release và trạng thái hỗ trợ.
- [ ] Đã loại bỏ version pin Spring Cloud module không cần thiết.
- [ ] Đã kiểm tra Spring Framework/Boot dependency bị ghi đè.
- [ ] Đã xác minh JDK và Maven/Gradle wrapper.
- [ ] Đã chạy dependency tree hoặc dependency insight.
- [ ] Đã chạy test context và smoke test trên môi trường gần production.
- [ ] Không tắt verifier chỉ để che lỗi.
- [ ] Đã ghi nhận version matrix trong tài liệu nâng cấp của dự án.

## 21. Câu hỏi tự kiểm tra

1. Vì sao Spring Boot `4.1.2` không cần Spring Cloud `4.1.2`?
2. Spring Cloud release train BOM quản lý những module nào?
3. Spring Cloud `2025.1.x` hỗ trợ Boot `4.1.x` bắt đầu từ service release nào?
4. Boot `3.5.x` nên ghép với release train nào?
5. Compatibility Verifier kiểm tra điều gì và giới hạn của nó là gì?
6. Vì sao tắt verifier không sửa được `NoSuchMethodError`?
7. Làm thế nào để phát hiện Spring Cloud module bị kéo về version cũ?
8. `dependencyManagement` và BOM import có vai trò gì trong Maven?
9. Gradle `dependencyInsight` giúp tìm nguyên nhân chọn version như thế nào?
10. `UnsupportedClassVersionError` khác lỗi release train ở điểm nào?
11. Vì sao không nên import nhiều Spring Cloud release train trong cùng ứng dụng?
12. Cần kiểm thử những gì sau khi căn chỉnh version Boot/Cloud?

## 22. Tài liệu tham khảo chính thức

- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/) — bảng mapping Spring Boot và Spring Cloud, service release và hướng dẫn import BOM.
- [Spring Cloud — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions) — support policy, release train còn được hỗ trợ và lịch sử EOL.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html) — Spring Cloud Compatibility Verification và báo cáo lỗi khi Boot không tương thích.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) — `spring.cloud.compatibility-verifier.enabled` và `compatible-boot-versions`.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html) — quản lý dependency bằng Boot BOM và Gradle.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — dependency management và `spring-boot-dependencies`.
- [Gradle — Importing a Platform (BOM)](https://docs.gradle.org/current/userguide/platforms.html) — native BOM support, `platform` và dependency constraints.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — BOM import và `dependencyManagement`.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html) — xem dependency graph đã resolve.

*Tài liệu giúp tìm và sửa lỗi khởi động do cặp version Spring Boot/Spring Cloud không tương thích. Hãy căn chỉnh theo release train được hỗ trợ, kiểm tra dependency thực tế và xác nhận lại bằng test trên đúng JDK/runtime của ứng dụng.*
