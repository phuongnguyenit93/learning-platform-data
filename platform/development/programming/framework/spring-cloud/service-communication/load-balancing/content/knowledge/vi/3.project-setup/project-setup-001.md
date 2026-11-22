# Chọn phiên bản Spring Boot và Spring Cloud Release Train tương thích

## Mục tiêu

Spring Cloud được phát triển trên nền Spring Boot và có các thư viện riêng cho discovery, load balancing, OpenFeign, gateway, circuit breaker cùng nhiều chức năng phân tán khác. Các thư viện này cần tương thích với thế hệ Spring Boot và Spring Framework mà ứng dụng đang sử dụng. Nếu chọn sai cặp phiên bản, dự án có thể không phân giải được dependency, không khởi động được hoặc gặp lỗi tương thích khi chạy.

Trong bài này, bạn sẽ học cách:

- Đọc bảng tương thích giữa Spring Boot và Spring Cloud Release Train.
- Phân biệt phiên bản Spring Boot, phiên bản Spring Cloud Release Train và phiên bản từng module Spring Cloud.
- Chọn cặp phiên bản ổn định theo yêu cầu dự án.
- Khai báo Spring Cloud BOM trong Maven hoặc Gradle để đồng bộ dependency.
- Kiểm tra phiên bản Java, build tool và dependency thực tế trước khi bắt đầu cấu hình Spring Cloud LoadBalancer.

## 1. Vì sao phải chọn đúng cặp phiên bản?

Spring Boot quản lý nền tảng ứng dụng như Spring Framework, auto-configuration, logging, embedded server và nhiều thư viện nền tảng. Spring Cloud bổ sung các năng lực dành cho hệ thống phân tán, trong đó có service discovery và client-side load balancing.

Một phiên bản Spring Cloud được xây dựng và kiểm thử với một số thế hệ Spring Boot nhất định. Khi kết hợp hai thế hệ không tương thích, các vấn đề có thể xuất hiện ở nhiều mức:

- **Dependency resolution**: một module yêu cầu phiên bản thư viện không tồn tại hoặc xung đột với phiên bản do Boot quản lý.
- **Compile time**: API hoặc kiểu dữ liệu đã thay đổi khiến mã nguồn không biên dịch.
- **Application startup**: auto-configuration không tìm thấy lớp, method hoặc bean mà module mong đợi.
- **Runtime**: ứng dụng khởi động được nhưng lỗi khi thực hiện discovery, chọn `ServiceInstance` hoặc gọi dịch vụ.

Vì vậy, việc chọn phiên bản phải bắt đầu từ bảng tương thích chính thức. Không nên suy ra rằng Spring Boot `4.0.x` sẽ luôn dùng Spring Cloud `4.0.x`: Spring Cloud sử dụng một quy tắc đánh số phiên bản khác.

## 2. Hiểu cách đánh số phiên bản

### 2.1. Spring Boot

Spring Boot dùng phiên bản dạng `MAJOR.MINOR.PATCH`, ví dụ `4.0.9` hoặc `4.1.2`.

- `MAJOR`: thế hệ lớn, có thể chứa thay đổi cần xem xét khi nâng cấp.
- `MINOR`: nhánh phát hành tính năng.
- `PATCH`: bản sửa lỗi và cập nhật tương thích trong cùng nhánh.

Khi tài liệu nói Spring Boot `4.0.x`, ký tự `x` đại diện cho các bản vá trong nhánh `4.0`, chẳng hạn `4.0.7`, `4.0.8` hoặc `4.0.9`. Dự án vẫn nên dùng bản vá ổn định mới nhất được hỗ trợ trong nhánh đã chọn.

### 2.2. Spring Cloud Release Train

Spring Cloud sử dụng Calendar Versioning (CalVer) theo dạng `YYYY.MINOR.MICRO`, ví dụ `2025.1.4`.

- `YYYY`: năm của thế hệ Release Train.
- `MINOR`: nhánh Release Train trong năm đó.
- `MICRO`: bản phát hành dịch vụ trong cùng Release Train, chứa các bản sửa lỗi và cải tiến tương thích.

Hai phần đầu xác định thế hệ Release Train. Ví dụ, `2025.1.0`, `2025.1.2` và `2025.1.4` đều thuộc thế hệ `2025.1`. Không được hiểu `2025.1` là Spring Boot `2025.1` hoặc suy luận phiên bản Spring Cloud từ số phiên bản Spring Boot.

Một Release Train gom nhiều dự án Spring Cloud. Mỗi module có số phiên bản riêng. Ví dụ, Release Train `2025.1.4` quản lý các module như Spring Cloud Commons và Spring Cloud OpenFeign ở nhánh `5.0.x`. Bạn nên dùng BOM của Release Train để chọn các phiên bản module đồng bộ.

## 3. Đọc bảng tương thích Spring Boot và Spring Cloud

Tại ngày **17/11/2026**, các cặp phiên bản chính cần nhận biết như sau:

| Spring Boot | Spring Cloud Release Train | Trạng thái và cách sử dụng |
|---|---|---|
| `4.0.x` | `2025.1.x` | Cặp tương thích thuộc thế hệ Spring Cloud ổn định hiện hành. |
| `4.1.x` | `2025.1.x` | Được hỗ trợ từ Spring Cloud `2025.1.2`; `2025.1.4` hỗ trợ Boot `4.1.2`. |
| `3.5.x` | `2025.0.x` | Cặp tương thích cho ứng dụng Boot 3.5; `2025.0.3` là bản OSS cuối cùng và hỗ trợ OSS đã kết thúc ngày 30/06/2026. |
| `4.2.0-RC2` | `2026.0.0-RC2` | Bản xem trước (Release Candidate), phù hợp thử nghiệm tính năng mới, chưa phải lựa chọn ổn định cho production. |

Spring Cloud `2025.1.4` là bản GA mới nhất tại thời điểm viết bài. Bản này được xây dựng trên Spring Boot `4.0.9` và công bố hỗ trợ Spring Boot `4.1.2`. Nếu bắt đầu một dự án mới, cặp `Spring Boot 4.0.9 + Spring Cloud 2025.1.4` là lựa chọn cụ thể, ổn định để thực hành trong bài học này. Nếu dự án đã chuẩn hóa trên Boot `4.1.2`, có thể dùng cùng Release Train `2025.1.4`.

Spring Cloud `2025.0.3` vẫn là một bản phát hành đã được công bố cho Spring Boot `3.5.x`, nhưng đây là bản OSS cuối cùng của nhánh `2025.0.x`; hỗ trợ OSS kết thúc ngày 30/06/2026. Khi bảo trì ứng dụng Boot 3.5 hiện có, cần đánh giá chính sách hỗ trợ và lập kế hoạch nâng cấp. Không nên chọn nhánh đã hết hỗ trợ cho một dự án mới cần cập nhật bảo mật lâu dài.

Spring Cloud `2026.0.0-RC2` tương ứng với Spring Boot `4.2.0-RC2`. Hậu tố `RC` có nghĩa là Release Candidate, tức bản tiền phát hành. Chỉ dùng cặp này trong môi trường thử nghiệm có chủ đích; không trộn một bản RC với các dependency GA rồi coi đó là cấu hình production đã được hỗ trợ.

> Bảng tương thích là điểm bắt đầu. Với từng bản vá cụ thể, hãy đọc release notes của Release Train để biết phiên bản Boot nào được hỗ trợ từ bản phát hành nào. Ví dụ, hỗ trợ dòng Boot `4.1.x` bắt đầu từ Spring Cloud `2025.1.2`, không phải mọi bản `2025.1.x` đầu tiên đều mặc nhiên hỗ trợ dòng này.

## 4. Quy trình chọn phiên bản cho một dự án

Hãy thực hiện theo thứ tự sau:

1. **Xác định trạng thái dự án.** Nếu dự án đã tồn tại, đọc phiên bản Spring Boot hiện tại từ `pom.xml`, `build.gradle` hoặc `build.gradle.kts`. Nếu là dự án mới, xác định yêu cầu về Java, thư viện và nền tảng triển khai trước khi chọn Boot.
2. **Xác định nhánh Boot cần dùng.** Chọn một nhánh Boot đang được hỗ trợ và phù hợp với môi trường chạy. Đừng nâng major version chỉ vì có bản mới nếu dự án còn phụ thuộc vào thư viện chưa tương thích.
3. **Tra bảng Release Train.** Tìm Release Train tương ứng với nhánh Boot đã chọn trên trang Spring Cloud chính thức.
4. **Chọn bản GA mới nhất trong Release Train đó.** Các bản service release thường mang theo sửa lỗi và cập nhật tương thích. Không lấy bản `M`, `RC` hoặc `SNAPSHOT` nếu mục tiêu là một dự án ổn định.
5. **Kiểm tra release notes.** Xác nhận chính xác bản Boot đang dùng có nằm trong phạm vi hỗ trợ của bản Cloud đó; xem thêm các thay đổi ảnh hưởng đến module dự định sử dụng như LoadBalancer, Netflix Eureka hoặc OpenFeign.
6. **Kiểm tra Java và build tool.** Phiên bản JDK, Maven hoặc Gradle phải đáp ứng yêu cầu của Spring Boot đã chọn.
7. **Khai báo BOM và build thử.** Để BOM quản lý các module Spring Cloud, sau đó kiểm tra dependency đã phân giải và chạy build trước khi thêm cấu hình discovery hoặc load balancing.

Nếu cần tạo dự án mới nhanh, có thể dùng [Spring Initializr](https://start.spring.io/), chọn phiên bản Spring Boot và các dependency cần thiết. Initializr sẽ thêm Spring Cloud BOM tương ứng vào cấu hình Maven hoặc Gradle. Sau khi sinh dự án, vẫn cần kiểm tra lại các phiên bản được tạo và trạng thái hỗ trợ trước khi đưa vào sử dụng.

## 5. Chọn Java và build tool phù hợp

Spring Boot `4.0.9` yêu cầu tối thiểu Java 17. Tài liệu phiên bản này công bố hỗ trợ Maven từ `3.6.3` trở lên và Gradle `8.14` trở lên trong nhánh 8.x hoặc nhánh 9.x.

| Thành phần | Yêu cầu với ví dụ Spring Boot 4.0.9 |
|---|---|
| JDK | Java 17 trở lên |
| Maven | 3.6.3 trở lên |
| Gradle | 8.14 trở lên trong nhánh 8.x, hoặc 9.x |
| Spring Cloud | Release Train tương thích, ví dụ `2025.1.4` |

Hãy kiểm tra JDK thực tế mà terminal và IDE đang sử dụng:

```bash
java -version
javac -version
```

Với Maven:

```bash
mvn -version
```

Với Gradle:

```bash
gradle --version
```

Trong dự án nhóm, nên commit Maven Wrapper (`mvnw`, `mvnw.cmd`) hoặc Gradle Wrapper (`gradlew`, `gradlew.bat`). Wrapper giúp mọi thành viên và CI sử dụng cùng phiên bản build tool đã khai báo trong repository, giảm khác biệt do máy cá nhân cài các bản Maven hoặc Gradle khác nhau.

## 6. Khai báo phiên bản bằng Spring Cloud BOM

### 6.1. BOM làm nhiệm vụ gì?

BOM (Bill of Materials) là một POM chuyên quản lý phiên bản dependency. Spring Cloud cung cấp BOM `spring-cloud-dependencies` cho từng Release Train. Khi import BOM, Maven hoặc Gradle có thể chọn phiên bản tương ứng cho các starter và module Spring Cloud mà không cần khai báo version riêng trên từng dependency.

Trong một dự án Spring Boot:

- Spring Boot parent hoặc Spring Boot BOM quản lý các dependency thuộc hệ sinh thái Boot.
- Spring Cloud BOM quản lý các dependency thuộc hệ sinh thái Cloud.
- Phiên bản Spring Boot plugin là phiên bản plugin build ứng dụng, không phải phiên bản Spring Cloud.

Không nên tự gán một phiên bản Spring Cloud khác nhau cho từng starter. Việc đó có thể tạo ra classpath chứa các module Cloud thuộc nhiều Release Train, gây xung đột API hoặc hành vi khó dự đoán.

### 6.2. Cấu hình Maven

Ví dụ dưới đây sử dụng Spring Boot `4.0.9`, Java 17 và Spring Cloud `2025.1.4`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>load-balancing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>
</project>
```

Khi thêm một discovery provider, ví dụ Eureka, khai báo starter tương ứng mà không thêm version nếu dependency được BOM quản lý:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Nếu dự án không kế thừa `spring-boot-starter-parent`, có thể import `spring-boot-dependencies` BOM theo cấu trúc phù hợp, rồi import `spring-cloud-dependencies` BOM. Cần đảm bảo thứ tự và quy tắc quản lý dependency rõ ràng, tránh khai báo nhiều BOM ghi đè cùng một dependency ngoài ý muốn.

### 6.3. Cấu hình Gradle

Ví dụ sử dụng Gradle Groovy DSL và `platform` để import Spring Cloud BOM:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.9'
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

ext {
    springCloudVersion = '2025.1.4'
}

dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:4.0.9")
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
```

Nếu dự án sử dụng Kotlin DSL (`build.gradle.kts`), cách làm tương tự: khai báo Boot plugin ở phiên bản đã chọn, import BOM bằng `implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))`, sau đó khai báo starter mà không chỉ định version riêng.

## 7. Kiểm tra dependency sau khi cấu hình

Việc khai báo đúng version trong file build chưa đủ. Cần kiểm tra phiên bản thực tế sau khi Maven hoặc Gradle giải quyết dependency, vì dependency bắc cầu (transitive dependency), BOM khác hoặc constraint trong dự án có thể ảnh hưởng kết quả.

### 7.1. Kiểm tra với Maven

Chạy bằng Maven Wrapper:

```bash
./mvnw -version
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud
./mvnw clean verify
```

Trong PowerShell trên Windows, dùng `.\mvnw.cmd` thay cho `./mvnw` nếu môi trường không chạy được script Unix. Kết quả dependency tree cần cho thấy Spring Boot thuộc nhánh đã chọn và các module Spring Cloud được BOM quản lý cùng Release Train.

### 7.2. Kiểm tra với Gradle

Chạy bằng Gradle Wrapper:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew clean build
```

`dependencies` hiển thị cây dependency của runtime classpath. `dependencyInsight` giúp truy nguyên lý do một phiên bản cụ thể được chọn, hữu ích khi có nhiều dependency cùng yêu cầu một module.

### 7.3. Bật kiểm tra tương thích của Spring Cloud

Spring Cloud Commons có cơ chế Compatibility Verification để kiểm tra phiên bản Spring Boot trên classpath. Với Spring Cloud Commons `5.0.4`, thuộc tính `spring.cloud.compatibility-verifier.enabled` mặc định là `false`. Có thể bật kiểm tra này trong môi trường phát triển hoặc CI:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Khi phát hiện cặp phiên bản không phù hợp, cơ chế này có thể đưa ra báo cáo giải thích phiên bản Boot không được hỗ trợ. Hãy sửa cặp phiên bản theo bảng tương thích và release notes. Không nên tắt kiểm tra chỉ để che một xung đột chưa được giải quyết.

## 8. Lỗi thường gặp khi chọn phiên bản

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Maven báo không tìm thấy artifact hoặc version | Gõ sai artifact, dùng bản chưa phát hành hoặc repository không có artifact đó | Kiểm tra tọa độ dependency, trạng thái GA/RC và repository. |
| Ứng dụng báo Boot không tương thích với Cloud | Chọn Release Train không hỗ trợ nhánh Boot hiện tại | Tra bảng tương thích và chọn đúng Release Train. |
| Có `NoSuchMethodError` hoặc `ClassNotFoundException` | Các module Spring hoặc Spring Cloud bị trộn phiên bản | Xem dependency tree, bỏ version thủ công và để BOM quản lý. |
| Build thành công nhưng lỗi khi khởi động | Auto-configuration hoặc API của các module không tương thích | Kiểm tra stack trace, release notes và phiên bản thực tế trên runtime classpath. |
| IDE biên dịch được nhưng CI thất bại | JDK hoặc build tool trên hai môi trường khác nhau | Dùng Wrapper, thống nhất JDK/toolchain và kiểm tra `java -version`. |
| Starter discovery không hoạt động | Chỉ thêm LoadBalancer nhưng chưa có discovery provider hoặc danh sách instance | Thêm discovery implementation phù hợp hoặc cấu hình nguồn instance tĩnh cho môi trường thử nghiệm. |

Một lỗi như `NoSuchMethodError` thường cho biết classpath lúc chạy khác với API mà mã nguồn hoặc module đã được biên dịch dựa vào. Hãy truy nguyên dependency trước khi thêm một thư viện khác để thử sửa lỗi.

## 9. Nâng cấp Spring Boot hoặc Spring Cloud an toàn

Nâng cấp Spring Boot và Spring Cloud là thay đổi có thể ảnh hưởng đến API, auto-configuration và dependency bắc cầu. Nên thực hiện theo các bước:

1. Ghi nhận phiên bản Boot, Cloud BOM, JDK, Maven/Gradle và các starter hiện tại.
2. Tra Release Train hỗ trợ phiên bản Boot đích.
3. Đọc release notes của Spring Boot và Spring Cloud cho các nhánh liên quan; lưu ý thay đổi breaking change, deprecated API và thay đổi cấu hình.
4. Cập nhật Boot và Cloud BOM theo một cặp đã được công bố tương thích.
5. Xóa các version thủ công của module Spring Cloud nếu chúng đang xung đột với BOM.
6. Chạy dependency tree để kiểm tra classpath sau nâng cấp.
7. Chạy unit test, integration test và smoke test cho các luồng discovery, chọn instance và gọi dịch vụ.
8. Kiểm tra log khởi động, health endpoint, metrics và trace trước khi triển khai.

Với ứng dụng đang dùng Spring Boot 3.5.x, không nên chỉ thay Boot thành 4.0.x rồi giữ nguyên Spring Cloud `2025.0.x`. Hãy nâng cấp đồng bộ Spring Boot lên `4.0.x` hoặc `4.1.x` và Spring Cloud lên Release Train `2025.1.x`, sau đó thực hiện migration theo tài liệu Spring Boot 4 cùng các release notes Spring Cloud. Đồng thời kiểm tra các thư viện ngoài Spring vì chúng có thể chưa hỗ trợ thế hệ Spring mới.

## 10. Checklist trước khi bắt đầu cấu hình LoadBalancer

- [ ] Đã xác định nhánh Spring Boot và kiểm tra trạng thái hỗ trợ.
- [ ] Đã tra đúng Spring Cloud Release Train trong bảng tương thích chính thức.
- [ ] Đã chọn bản GA mới nhất trong Release Train phù hợp.
- [ ] Đã kiểm tra release notes cho bản Boot patch và Cloud service release cụ thể.
- [ ] JDK đáp ứng yêu cầu của Spring Boot.
- [ ] Maven hoặc Gradle đáp ứng yêu cầu và dự án sử dụng Wrapper.
- [ ] Spring Cloud BOM đã được import đúng.
- [ ] Starter Spring Cloud không bị gán version thủ công ngoài BOM.
- [ ] Dependency tree cho thấy các module Boot và Cloud được phân giải nhất quán.
- [ ] Build và test cơ bản chạy thành công.

## Kết luận

Phiên bản Spring Cloud phải được chọn theo thế hệ Spring Boot mà Release Train hỗ trợ. Tại ngày 17/11/2026, cặp `Spring Boot 4.0.9 + Spring Cloud 2025.1.4` là cấu hình GA cụ thể phù hợp để bắt đầu bài thực hành; Spring Cloud `2025.1.4` cũng hỗ trợ Boot `4.1.2`. Dùng Spring Cloud BOM để đồng bộ các module, kiểm tra JDK và build tool, rồi xác minh dependency tree trước khi tích hợp discovery và load balancing.

## Tài liệu tham khảo

- [Spring Cloud — Getting Started và bảng tương thích Release Train](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.4 — thông báo phát hành và cặp Spring Boot tương thích](https://spring.io/blog/2026/10/23/spring-cloud-2025-1-4-has-been-released/)
- [Spring Cloud 2025.0.3 — bản OSS cuối cùng và thời điểm kết thúc hỗ trợ](https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/)
- [Spring Cloud Release — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Cloud Commons — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
