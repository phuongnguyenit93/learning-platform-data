# Xác định dòng Spring Boot, Spring Framework và JDK làm mốc cho thư viện

## 1. Mục tiêu: công bố một hợp đồng tương thích có thể kiểm chứng

Khi phát triển thư viện trong hệ sinh thái Spring, câu hỏi “thư viện hỗ trợ Spring Boot phiên bản nào?” không thể trả lời chỉ bằng cách nhìn version dependency trong `pom.xml`. Có ít nhất ba trục độc lập cần chốt:

1. **JDK tối thiểu:** bytecode và API Java thấp nhất mà thư viện yêu cầu.
2. **Spring Framework tối thiểu:** dòng API Spring mà mã nguồn thư viện sử dụng.
3. **Spring Boot tối thiểu và các dòng được hỗ trợ:** phiên bản Boot cung cấp dependency management, auto-configuration API và môi trường tích hợp mà thư viện được kiểm thử.

Một thư viện có thể biên dịch bằng JDK 21 nhưng vẫn tạo bytecode Java 17; có thể dùng Spring Framework 6.2 API; và có thể được kiểm thử với nhiều dòng Boot khác nhau. Ba con số đó không bắt buộc giống nhau.

Bài học hướng dẫn cách chọn baseline, đọc đúng quan hệ giữa Boot/Framework/JDK, thiết kế module để hỗ trợ nhiều dòng, cấu hình Maven/Gradle, xây dựng ma trận CI và công bố phạm vi tương thích. Ví dụ dùng **Java 17+** và các dòng Spring Boot hiện hành trong tài liệu chính thức tại thời điểm biên soạn.

## 2. Ba trục version và ý nghĩa của từng trục

### 2.1. JDK baseline

JDK baseline trả lời: ứng dụng tiêu thụ có thể chạy thư viện trên Java tối thiểu nào?

Cần phân biệt ba giá trị:

- **JDK dùng để build:** JDK cài trên máy developer hoặc CI.
- **Java release/bytecode target:** phiên bản class file và tập API Java mà compiler được phép sử dụng.
- **JDK runtime tối thiểu:** JVM thấp nhất có thể nạp và chạy artifact.

Ví dụ build bằng JDK 21 nhưng cấu hình `--release 17` sẽ giới hạn bytecode và API Java ở mức Java 17. Nếu chỉ khai báo source/target mà không dùng release phù hợp, compiler có thể vẫn cho phép tham chiếu API chỉ có từ JDK mới hơn; ứng dụng sau đó có thể lỗi khi chạy trên JDK tối thiểu.

Với thư viện mới hướng tới Spring Boot 3.x và 4.x, baseline Java thực tế thường là **Java 17** vì các dòng Boot này yêu cầu Java 17 trở lên. Nếu thư viện cần API Java 21, baseline của thư viện phải nâng lên Java 21 dù Boot vẫn hỗ trợ Java 17.

### 2.2. Spring Framework baseline

Spring Framework baseline trả lời: thư viện cần API Spring tối thiểu nào để compile và chạy?

Ví dụ:

- Module chỉ dùng `org.springframework.core` hoặc `spring-context` có thể có phạm vi phụ thuộc hẹp hơn module auto-configuration.
- Module dùng API của `spring-webmvc`, `spring-security` hoặc `spring-data` phải xét thêm version của project tương ứng.
- Module dùng `@AutoConfiguration`, `@ConditionalOnClass`, `@ConditionalOnMissingBean` hoặc `AutoConfiguration.imports` còn phụ thuộc Spring Boot, không chỉ Spring Framework.

Một thư viện compile thành công với Spring Framework 7.0 không tự động chứng minh nó chạy được với Spring Framework 6.2. Nếu mã nguồn tham chiếu method hoặc class mới chỉ xuất hiện trong 7.0, runtime 6.2 có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.

### 2.3. Spring Boot baseline

Spring Boot baseline trả lời: thư viện hỗ trợ các dòng Boot nào và được kiểm thử với BOM nào?

Đối với thư viện chỉ cung cấp Java API, có thể không cần phụ thuộc Spring Boot. Đối với thư viện tích hợp Spring, Boot có thể chỉ là một môi trường kiểm thử. Nhưng với module auto-configuration hoặc starter, Boot là dependency trực tiếp vì module đó sử dụng Boot API.

Hãy phân biệt:

- **Compile baseline:** version thấp nhất mà mã nguồn được biên dịch.
- **Runtime compatibility:** các dòng version mà artifact thực sự chạy được.
- **Tested support:** các dòng version đã chạy qua bộ test trong CI.
- **Recommended version:** dòng mà tài liệu khuyên người dùng chọn cho dự án mới.

Chỉ công bố một dòng Boot là được hỗ trợ khi có bằng chứng kiểm thử phù hợp. Không suy luận hỗ trợ chỉ vì Maven có thể resolve dependency.

## 3. Quan hệ giữa các dòng Spring Boot, Spring Framework và JDK

Spring Boot quản lý một tập dependency đã được kiểm thử cùng nhau. Mỗi dòng Boot gắn với một dòng Spring Framework và một baseline Java nhất định. Bảng dưới đây dùng các patch release ổn định trong tài liệu chính thức làm ví dụ; version patch tối thiểu của Framework có thể thay đổi theo patch release của Boot.

| Dòng Spring Boot | Java tối thiểu | Dòng Spring Framework tương ứng | Ghi chú |
|---|---:|---|---|
| 2.7.x | 8 | 5.3.x | Dòng Java EE cũ, dùng namespace `javax` ở các API Jakarta/Servlet liên quan |
| 3.0.x–3.1.x | 17 | 6.0.x | Chuyển sang Jakarta EE, package `jakarta.*` |
| 3.2.x–3.3.x | 17 | 6.1.x | Dòng Framework 6.1 |
| 3.4.x–3.5.x | 17 | 6.2.x | Dòng Framework 6.2 |
| 4.0.x–4.1.x | 17 | 7.0.x | Dòng Framework 7.0, cần kiểm thử tương thích riêng |

Một số mốc patch trong tài liệu hệ thống chính thức:

| Bản Boot được tài liệu hóa | Java tối thiểu | Spring Framework tối thiểu |
|---|---:|---|
| Boot 2.7.18 | 8 | 5.3.31 |
| Boot 3.0.13 | 17 | 6.0.14 |
| Boot 3.1.12 | 17 | 6.0.21 |
| Boot 3.2.12 | 17 | 6.1.x |
| Boot 3.3.13 | 17 | 6.1.21 |
| Boot 3.4.13 | 17 | 6.2.15 |
| Boot 3.5.16 | 17 | 6.2.19 |
| Boot 4.0.9 | 17 | 7.0.10 |
| Boot 4.1.2 | 17 | 7.0.10 |

Đây là yêu cầu của từng bản Boot được dẫn, không phải cam kết rằng mọi bản patch cũ của một dòng đều hỗ trợ mọi JDK mới. Hãy mở trang System Requirements của đúng patch trước khi chốt CI matrix hoặc tuyên bố runtime support.

Tại thời điểm biên soạn, tài liệu chính thức liệt kê các dòng ổn định 3.3, 3.4, 3.5, 4.0 và 4.1. Điều đó không có nghĩa thư viện phải hỗ trợ tất cả. Chủ thư viện cần chọn phạm vi dựa trên người dùng mục tiêu, thời gian bảo trì và chi phí kiểm thử.

## 4. Các bước chọn baseline cho thư viện

### Bước 1: xác định loại artifact

Trước tiên, xác định thư viện thuộc trường hợp nào:

| Loại module | Phụ thuộc chính | Baseline cần công bố |
|---|---|---|
| Core Java library | JDK và các thư viện Java độc lập | JDK tối thiểu; không cần Boot nếu không dùng Boot |
| Spring integration | Spring Framework | JDK + Spring Framework |
| Boot auto-configuration | Spring Boot auto-config API và Spring Framework | JDK + dòng Boot/Framework |
| Starter aggregator | Các module tích hợp và dependency mà starter kéo vào | Dòng Boot mà starter được kiểm thử |
| Adapter cho project bên ngoài | API của Spring Security, Data, Kafka, v.v. | Boot/Framework và version project tích hợp |

Nếu một repository có cả core API và auto-configuration, không nhất thiết buộc mọi module dùng cùng một dependency graph. Có thể tách core để giữ API ổn định và module Boot để tích hợp với từng dòng Boot.

### Bước 2: thu thập yêu cầu từ người dùng

Lấy dữ liệu từ các ứng dụng tiêu thụ thực tế:

- Họ đang chạy Boot 3.3, 3.5 hay 4.1?
- Có còn ứng dụng bắt buộc dùng Boot 2.7 không?
- JDK runtime thấp nhất là 17, 21 hay cao hơn?
- Họ dùng Servlet stack, WebFlux hay không dùng web?
- Họ cần native image, AOT processing hoặc GraalVM không?
- Có project Spring Cloud/Spring Data/Security cần phối hợp version không?

Không nên hỗ trợ một dòng cũ chỉ vì có thể biên dịch. Mỗi dòng được công bố hỗ trợ sẽ làm tăng số tổ hợp phải kiểm thử, tài liệu và thời gian xử lý issue.

### Bước 3: chọn JDK tối thiểu theo API Java thực sự dùng

Nếu mục tiêu là Boot 3.5 và Boot 4.1, Java 17 là baseline chung thấp nhất theo yêu cầu của hai dòng Boot này. Dùng `release 17` giúp compiler ngăn việc vô tình sử dụng API Java mới hơn.

Nếu core library cần hỗ trợ Java 8 để dùng cùng Boot 2.7, có thể tách module:

- `acme-core`: Java 8 hoặc baseline thấp nhất mà core có thể duy trì.
- `acme-spring-boot3-autoconfigure`: Java 17.
- `acme-spring-boot4-autoconfigure`: Java 17, nếu cần adapter riêng.

Đừng đặt Java 8 làm baseline cho toàn bộ thư viện chỉ vì một module core có thể chạy trên Java 8; module tích hợp Boot 3/4 vẫn phải đáp ứng Java 17.

### Bước 4: chọn dòng Boot/Framework thấp nhất mà bạn cam kết hỗ trợ

Nếu cần hỗ trợ Boot 3.x rộng rãi, một baseline có thể là Boot 3.3.x / Framework 6.1.x và kiểm thử thêm trên 3.5.x / Framework 6.2.x. Nếu chỉ hướng tới dòng 3.x mới nhất, có thể lấy Boot 3.5.x / Framework 6.2.x làm baseline.

Nếu muốn hỗ trợ Boot 4.x, thêm một test lane riêng với Boot 4.1.x / Framework 7.0.x. Không tuyên bố Boot 4 tương thích chỉ dựa vào việc cùng yêu cầu Java 17; major release có thể thay đổi API, dependency graph, module và tích hợp.

### Bước 5: compile với baseline thấp nhất, test trên mọi dòng đã công bố

Nếu thư viện công bố hỗ trợ Boot 3.3, 3.5 và 4.1:

- Compile source trên API thấp nhất mà bạn muốn hỗ trợ.
- Dùng BOM tương ứng để resolve dependency khi chạy test từng dòng.
- Chạy integration test trên từng dòng.
- Nếu một dòng cần source set hoặc adapter riêng, tách module thay vì thêm nhiều điều kiện version khó bảo trì.

Compile với Framework 7.0 rồi chỉ test trên Boot 4.1 không chứng minh hỗ trợ Boot 3.5. Ngược lại, compile với Framework 6.2 không chứng minh tự động rằng mọi API và extension point của Boot 4.1 vẫn tương thích.

## 5. Chọn một baseline hay nhiều dòng hỗ trợ?

### 5.1. Một baseline duy nhất

Phù hợp khi thư viện mới, người dùng mục tiêu đã chuyển sang một dòng Boot rõ ràng, nhóm nhỏ và muốn giữ chi phí bảo trì thấp.

Ví dụ hợp đồng:

~~~text
Library version: 2.x
Java: 17+
Spring Boot: 3.5.x
Spring Framework: 6.2.x (theo BOM của Boot)
Tested with: Boot 3.5.16
~~~

Ưu điểm là dễ hiểu, dễ kiểm thử và dễ hỗ trợ. Nhược điểm là ứng dụng đang ở Boot 3.3 hoặc Boot 4.1 có thể không dùng được nếu thư viện không công bố/test các dòng đó.

### 5.2. Một artifact hỗ trợ nhiều dòng Boot

Phù hợp khi thư viện chủ yếu dùng API ổn định, các dòng Boot mục tiêu dùng cùng baseline Java, source không phụ thuộc API mới chỉ có ở dòng cao hơn và CI có thể chạy đủ ma trận.

Ví dụ hợp đồng:

~~~text
Library version: 2.x
Java: 17+
Spring Boot: 3.3.x, 3.5.x, 4.1.x
Spring Framework: theo BOM của từng dòng Boot
Tested patch versions: ghi rõ trong release notes
~~~

Khi dùng một artifact, compile dependency version trong POM và dependency management của ứng dụng tiêu thụ phải được phối hợp. Hãy kiểm tra runtime dependency tree để chắc chắn consumer đang chạy version Spring mà BOM của họ chọn.

### 5.3. Tách module hoặc artifact theo major line

Nên tách khi có khác biệt thực sự về API, namespace, dependency graph hoặc code cần biên dịch riêng.

~~~text
acme-library/
├── acme-core/
├── acme-spring/
├── acme-boot3-autoconfigure/
├── acme-boot3-starter/
├── acme-boot4-autoconfigure/
└── acme-boot4-starter/
~~~

`acme-core` chứa logic độc lập. Module Boot 3 phụ thuộc Spring Boot 3 và Spring Framework 6; module Boot 4 phụ thuộc Spring Boot 4 và Spring Framework 7. Hai adapter có thể cùng gọi vào core API.

Không tách module chỉ để phản ánh mọi patch version. Thường chỉ cần tách khi có major compatibility boundary hoặc khi source code thật sự khác nhau.

### 5.4. Trường hợp phải hỗ trợ Boot 2.7 và Boot 3+

Boot 2.7 dùng Java 8 và Spring Framework 5.3; Boot 3+ yêu cầu Java 17 và chuyển các API Jakarta sang namespace `jakarta.*`. Các integration dùng Servlet, Validation, Persistence hoặc API Jakarta thường cần source/module riêng.

Nếu phải hỗ trợ cả hai:

- Giữ core module ở Java baseline thấp nhất có thể.
- Tách module Boot 2/Jakarta cũ và module Boot 3+.
- Không để type `javax.*` rò vào public API của module Boot 3.
- Kiểm tra dependency tree để loại dependency Java EE cũ khỏi module Boot 3.
- Dùng đúng metadata auto-configuration cho các dòng mục tiêu.

Spring Boot 2.7 hỗ trợ cả file `AutoConfiguration.imports` và cơ chế `spring.factories` cho auto-configuration. Spring Boot 3 đã bỏ đăng ký auto-configuration qua key `EnableAutoConfiguration` trong `spring.factories`; nếu cần một artifact tương thích 2.7 và 3.x, hãy thiết kế metadata và test theo hướng dẫn migration chính thức.

## 6. Spring Boot BOM: để Boot quản lý Spring Framework

Spring Boot phát hành `spring-boot-dependencies` BOM chứa các version dependency đã được chọn và kiểm thử cùng nhau. Khi nâng Boot, BOM cập nhật đồng bộ Spring Framework và nhiều thư viện liên quan.

Đối với thư viện, nguyên tắc quan trọng:

- Không tự đặt version `spring-core`, `spring-context`, `spring-beans`, `spring-web` hoặc các Spring module nếu BOM đã quản lý.
- Không nâng riêng Spring Framework lên dòng mới hơn chỉ để lấy một API, rồi vẫn tuyên bố hỗ trợ dòng Boot cũ.
- Nếu thật sự cần override, ghi rõ lý do, kiểm tra compatibility và test đầy đủ.
- Ứng dụng tiêu thụ nên dùng BOM của dòng Boot mà ứng dụng đang chạy.

Ví dụ: Boot 3.5 quản lý Spring Framework 6.2; Boot 4.1 quản lý Spring Framework 7.0. Một POM thư viện không nên ép mọi consumer dùng Framework 7.0 nếu vẫn muốn hỗ trợ Boot 3.5.

### 6.1. Ví dụ Maven cho module auto-configuration

Ví dụ dưới đây lấy Boot 3.5.16 làm baseline build/test. Đây là cấu hình mẫu cho một module dùng Boot auto-configuration API, không phải tuyên bố rằng mọi consumer phải chạy đúng patch này.

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-boot-autoconfigure</artifactId>
    <version>2.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>${spring-boot.version}</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Thay `${spring-boot.version}` bằng version property đã chọn hoặc quản lý qua profile CI. Nếu dùng Maven parent `spring-boot-starter-parent`, có thể nhận sẵn dependency management và compiler defaults; với library nhiều module, import BOM trực tiếp thường giúp kiểm soát parent của tổ chức.

Lưu ý: dependency management của thư viện giúp build module nhất quán. Ứng dụng tiêu thụ vẫn nên quản lý dependency graph bằng BOM của chính dòng Boot mà nó chạy. Hãy kiểm tra POM đã publish và dependency tree thực tế, không giả định BOM của một thư viện tự động thay thế platform của ứng dụng.

### 6.2. Ví dụ Gradle

Với Gradle và Java Library plugin:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:3.5.16"
    ))

    implementation(
        "org.springframework.boot:spring-boot-autoconfigure"
    )

    testImplementation(
        "org.springframework.boot:spring-boot-starter-test"
    )
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`toolchain` chọn JDK dùng để biên dịch. `options.release` giới hạn bytecode và API Java được sử dụng. Nếu thư viện công bố Java 17+, cần giữ cả hai cài đặt ở mức 17, kể cả khi CI chạy trên JDK 21 hoặc 25.

Nếu muốn test trên nhiều Boot line, quản lý version BOM bằng Gradle property hoặc version catalog và chạy từng job CI với một giá trị cụ thể. Không dùng dynamic version như `latest.release` trong build phát hành vì kết quả có thể thay đổi mà không có source change.

## 7. Dependency scope và public API

Chọn scope theo cách consumer cần dùng thư viện:

| Dependency | Khi nào dùng | Lưu ý |
|---|---|---|
| `api` (Gradle) | Type dependency xuất hiện trong public method/signature của library và consumer cần compile với type đó | Làm dependency trở thành compile API của consumer |
| `implementation` | Dependency là chi tiết nội bộ nhưng vẫn cần ở runtime | Thường phù hợp cho implementation và auto-configuration runtime |
| `compileOnly` | Container hoặc ứng dụng tiêu thụ chắc chắn cung cấp dependency; artifact không nên kéo dependency runtime | Chỉ dùng khi hợp đồng library yêu cầu consumer tự cung cấp |
| Maven `optional` | Muốn dependency không tự truyền sang consumer | Consumer cần khai báo dependency nếu muốn dùng tính năng tương ứng |
| `test` / `testImplementation` | Chỉ dùng khi chạy test | Không xuất hiện trong runtime của consumer |

Không dùng `optional` theo thói quen. Nếu auto-configuration class cần một type của Boot để được nạp, hoặc starter cần thư viện tích hợp để tạo bean, hãy thiết kế dependency runtime rõ ràng. Với optional integration, tách module hoặc dùng condition/classloader an toàn để ứng dụng không có dependency đó vẫn khởi động được.

Public API cũng ảnh hưởng baseline. Nếu một method công khai trả về type chỉ có ở Spring Framework 7, consumer dùng module đó sẽ bị ràng buộc theo Framework 7 ngay cả khi phần lớn logic của thư viện tương thích Framework 6.

## 8. Thiết kế module để giảm ràng buộc version

Một thư viện dễ bảo trì thường tách phần nghiệp vụ khỏi phần tích hợp:

~~~text
acme/
├── acme-core/
│   └── API và logic Java thuần
├── acme-spring-support/
│   └── Spring Framework integration
├── acme-boot3-autoconfigure/
│   └── Boot 3 conditions và bean definitions
├── acme-boot3-starter/
│   └── Dependency aggregator cho Boot 3
├── acme-boot4-autoconfigure/
│   └── Boot 4 adapter nếu cần
└── acme-boot4-starter/
    └── Dependency aggregator cho Boot 4
~~~

Lợi ích:

- Core ít phụ thuộc vào Spring Boot nên dễ giữ API ổn định.
- Có thể test logic nghiệp vụ mà không phải khởi tạo ApplicationContext.
- Mỗi adapter compile với BOM tương ứng.
- Khi Boot major thay đổi, chỉ module adapter cần sửa nếu core API không bị ảnh hưởng.
- Starter có thể khai báo đúng dependency cho dòng Boot mục tiêu.

Không nên tạo module trống chỉ để tăng số artifact. Chỉ tách khi có ranh giới dependency hoặc compatibility thực tế.

## 9. Auto-configuration và metadata theo từng dòng Boot

Module auto-configuration cần được kiểm tra với đúng cơ chế đăng ký và API của dòng Boot được công bố.

Ví dụ lớp cấu hình:

~~~java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
~~~

Đăng ký trong file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Nếu cùng một module cần hỗ trợ Boot 2.7 và Boot 3.x, cần xem xét metadata registration của cả hai dòng. Boot 2.7 có hỗ trợ imports file và `spring.factories`; Boot 3 bỏ key `EnableAutoConfiguration` trong `spring.factories`. Không nhầm SPI khác vẫn dùng `spring.factories` với cơ chế đăng ký auto-configuration.

Khi hỗ trợ Boot 4, build và test module với Boot 4 BOM; không chỉ đổi version trong POM rồi giả định mọi API, starter dependency và extension point giữ nguyên.

## 10. Xây dựng ma trận kiểm thử tương thích

Một thư viện chỉ được công bố hỗ trợ những tổ hợp đã được kiểm tra. Ma trận không nhất thiết bao gồm mọi JDK và mọi patch version, nhưng phải bao phủ các boundary quan trọng.

### 10.1. Ma trận khuyến nghị cho thư viện mới

Nếu thư viện dự định hỗ trợ cả dòng Boot 3 mới và Boot 4:

| Test lane | Spring Boot | Spring Framework theo BOM | JDK test |
|---|---|---|---|
| Boot 3 baseline | 3.5.16 | 6.2.x | 17, 21, 25 |
| Boot 4 baseline | 4.1.2 | 7.0.x | 17, 21, 27 |

Đây là ma trận ví dụ theo giới hạn JDK được tài liệu hóa cho các patch release trên. Nếu CI của dự án không có JDK mới nhất, chọn tập con đại diện và ghi rõ phạm vi thực tế. Nếu thư viện tuyên bố hỗ trợ Boot 3.3, phải thêm test lane Boot 3.3; không suy ra từ test Boot 3.5.

Nếu còn hỗ trợ Boot 2.7, thêm lane riêng với JDK 8/11/17 phù hợp. Khi module đó dùng `javax.*`, không gộp nó với adapter `jakarta.*` chỉ để giảm số job.

### 10.2. Kiểm thử những gì ở mỗi lane?

Ở mỗi dòng Boot nên chạy ít nhất:

1. Compile toàn bộ module.
2. Unit test cho logic core.
3. Test auto-configuration với `ApplicationContextRunner`.
4. Integration test bằng ứng dụng consumer thực sự phụ thuộc starter.
5. Test khi optional dependency có và không có trên classpath.
6. Test user bean khiến default auto-configuration back off.
7. Test property condition và binding.
8. Test đóng gói JAR để xác nhận imports resource có mặt.
9. Test runtime trên JDK tối thiểu đã công bố.
10. Kiểm tra dependency tree để phát hiện Spring Framework version bị override.

### 10.3. Ví dụ test auto-configuration

~~~java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultClientWhenUserHasNoClient() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
        });
    }
}
~~~

Test này kiểm tra điều kiện và bean registration của auto-configuration trong test context. Với một bài kiểm tra discovery thực tế, bổ sung consumer application chỉ khai báo dependency starter, không `@Import` class auto-configuration và không component-scan package của thư viện. Consumer test xác nhận JAR metadata được đọc qua đường khởi động ứng dụng.

### 10.4. CI matrix minh họa

Có thể dùng cùng một Maven property cho BOM version rồi chạy nhiều job:

~~~bash
./mvnw -Dspring-boot.version=3.5.16 clean verify
./mvnw -Dspring-boot.version=4.1.2 clean verify
~~~

Nếu BOM version được khai báo cố định trong POM, hãy chuyển nó thành property/profile hoặc dùng hai build fixture riêng. Không sửa file POM thủ công giữa các job vì có thể khiến kết quả CI không tái lập.

Mỗi job nên ghi rõ:

- JDK thực tế (`java -version`).
- Maven/Gradle version.
- Boot BOM version.
- Spring Framework version resolve được.
- Test result và artifact commit.
- Test lane có bị bỏ qua hay không.

## 11. Kiểm tra dependency graph thực tế

Build thành công chưa đủ. Một dependency khác có thể kéo Spring Framework version không cùng BOM hoặc một SDK có thể kéo API `javax.*` cũ vào module Boot 3.

Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.boot
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Đọc kết quả để trả lời:

- `spring-core`, `spring-context`, `spring-beans` có cùng dòng không?
- `spring-boot`, `spring-boot-autoconfigure` có cùng dòng Boot không?
- Có dependency cũ kéo `javax.servlet` hoặc `javax.validation` vào module Jakarta không?
- Có version override ngoài BOM không?
- Một integration optional có vô tình trở thành runtime dependency bắt buộc không?

Khi phát hành thư viện, xem cả effective POM của module và dependency tree trong một ứng dụng consumer. Dependency tree của riêng module thư viện không luôn phản ánh chính xác graph cuối cùng của ứng dụng sử dụng.

## 12. Quy tắc nâng version

### 12.1. Nâng patch trong cùng dòng

Patch release thường tập trung vào sửa lỗi và cập nhật dependency tương thích trong cùng release line. Dù vậy, hãy chạy CI trên patch Boot mới nhất mà dự án chọn hỗ trợ và kiểm tra changelog của Spring Boot, Framework cùng thư viện tích hợp.

Không khóa consumer vào patch cũ nếu không có lý do. Trong ứng dụng tiêu thụ, BOM của Boot thường là nơi chọn patch dependency graph.

### 12.2. Nâng minor/feature release của Boot

Khi chuyển từ Boot 3.3 sang 3.5, Spring Framework cũng chuyển từ dòng 6.1 sang 6.2. Kiểm tra deprecation, behavior change, dependency upgrade và condition processing. Nếu thư viện công bố cả hai dòng, test cả hai thay vì chỉ build với version mới nhất.

### 12.3. Nâng major release

Boot 2 → 3 là một ranh giới đáng kể: Java 17 trở thành baseline, Spring Framework 6 được dùng và Jakarta namespace thay thế Java EE namespace trong các API liên quan.

Boot 3 → 4 cũng cần một compatibility lane riêng vì Boot chuyển sang Spring Framework 7 và có thể cập nhật nhiều dependency, module và integration. Đọc migration guide cho mỗi bước nhảy; nếu cách nhiều release, đọc release notes của các dòng trung gian.

### 12.4. Không dùng version range thay cho compatibility policy

Một khai báo Maven version range rộng không chứng minh thư viện tương thích với mọi version trong range. Resolver có thể chọn version khác với version đã test, hoặc version mới có API/behavior thay đổi.

Hãy công bố bảng hỗ trợ rõ ràng và test từng dòng. Nếu muốn dùng version range, cần lý do cụ thể, hiểu quy tắc resolver và vẫn giữ CI matrix để xác nhận.

## 13. Công bố baseline trong tài liệu và artifact

README hoặc release page nên có một mục Compatibility ngắn, có thể theo mẫu:

~~~markdown
## Compatibility

| Library line | Java | Spring Boot | Spring Framework |
|---|---|---|---|
| 2.x | 17+ | 3.5.x | Managed by Boot BOM |
| 2.x | 17+ | 4.1.x | Managed by Boot BOM |

Tested with:
- Spring Boot 3.5.16 on JDK 17, 21, and 25
- Spring Boot 4.1.2 on JDK 17, 21, and 27

The Spring Framework version is selected by the Spring Boot BOM.
Do not override Spring Framework modules independently unless required.
~~~

Không ghi “Spring Boot 3+” nếu chỉ test một patch của Boot 3.5 và chưa test 3.0/3.1/3.2/3.3. Cũng không ghi “Java 17+” nếu bytecode được build bằng release 21.

Nên ghi rõ:

- Dòng Boot thấp nhất được hỗ trợ.
- Các dòng Boot đã kiểm thử.
- JDK tối thiểu và JDK đã chạy test.
- Framework được quản lý bởi BOM nào.
- Các module/artifact riêng cho Boot major khác nhau.
- Dòng đã ngừng hỗ trợ và version cuối cùng được duy trì.

## 14. Những lỗi thường gặp khi chọn baseline

- **Chỉ chọn version mới nhất:** bỏ qua người dùng đang ở dòng Boot cũ và không đánh giá chi phí bảo trì.
- **Dùng JDK build làm JDK runtime tối thiểu:** build bằng JDK 21 không có nghĩa artifact chạy được trên Java 17 nếu không dùng `--release`.
- **Compile với Framework mới rồi công bố hỗ trợ Framework cũ:** có thể tạo lỗi linkage khi chạy trên API cũ.
- **Ghi version Framework riêng trong starter:** có thể phá dependency alignment của BOM Boot.
- **Nhầm Boot baseline với Framework baseline:** auto-configuration API thuộc Boot; `ApplicationContext` và nhiều extension API thuộc Framework.
- **Dùng một artifact cho cả `javax` và `jakarta` mà không có ranh giới:** type signature, dependency và runtime API có thể không tương thích.
- **Dùng version range để tuyên bố hỗ trợ:** resolver chọn version không đồng nghĩa test đã chứng minh tương thích.
- **Chỉ compile mà không chạy integration test:** không phát hiện bean condition, metadata, classpath hoặc runtime linkage failure.
- **Chỉ test Boot mới nhất:** không chứng minh baseline thấp nhất còn hoạt động.
- **Không test JDK tối thiểu:** bytecode có thể nạp được nhưng API Java mới hơn vẫn gây lỗi runtime.
- **Đưa SDK tùy chọn thành dependency bắt buộc:** consumer không dùng integration vẫn có thể bị lỗi classpath.
- **Gộp Boot 2.7 và Boot 3+ trong một adapter mà không xét namespace:** `javax` và `jakarta` là hai API khác nhau.
- **Không kiểm tra dependency tree consumer:** module build sạch nhưng ứng dụng cuối có thể resolve Framework version khác.
- **Không ghi rõ patch version đã test:** người dùng không biết mức bằng chứng của tuyên bố tương thích.
- **Giữ một dòng cũ mà không có owner bảo trì:** số lượng matrix tăng nhưng không có năng lực xử lý lỗi và cập nhật bảo mật.

## 15. Quy trình quyết định nhanh

1. Liệt kê ứng dụng tiêu thụ và các dòng Boot thực tế đang dùng.
2. Xác định module nào là Java thuần, Spring integration và Boot auto-configuration.
3. Chọn JDK tối thiểu theo API Java cần dùng và JDK runtime của người dùng.
4. Chọn dòng Spring Framework thấp nhất mà source thực sự cần.
5. Chọn Boot BOM tương ứng; không tự nâng riêng Spring Framework.
6. Quyết định hỗ trợ một Boot line, nhiều line hoặc tách adapter theo major.
7. Nếu hỗ trợ Boot 2.7 cùng Boot 3+, tách module khi có `javax`/`jakarta` khác nhau.
8. Cấu hình compiler bằng `release`, không chỉ source/target.
9. Tạo CI matrix cho Boot baseline, Boot mới nhất được hỗ trợ và JDK tối thiểu.
10. Chạy integration test trong consumer app và kiểm tra dependency tree runtime.
11. Công bố tested matrix, patch version và dòng không hỗ trợ.
12. Khi nâng Boot/Framework major, cập nhật compatibility policy và migration notes trước khi phát hành.

### Khuyến nghị mẫu cho thư viện mới

Nếu thư viện mới cần phục vụ cả ứng dụng Boot 3 và Boot 4 trong môi trường hiện nay, một chính sách thực tế là:

- Dùng **Java 17** làm bytecode baseline chung.
- Duy trì test lane **Boot 3.5.x / Framework 6.2.x**.
- Duy trì test lane riêng **Boot 4.1.x / Framework 7.0.x**.
- Chỉ dùng một artifact nếu cùng source và dependency graph đã vượt qua cả hai lane; nếu không, tách adapter theo major.
- Chỉ thêm Boot 2.7 khi có nhu cầu người dùng cụ thể và có khả năng duy trì module Java 8/Framework 5.3 riêng.

Nếu thư viện chỉ nhắm tới Boot 4, có thể lấy Boot 4.1.x / Framework 7.0.x / Java 17+ làm baseline chính. Nếu thư viện chỉ nhắm tới Boot 3, chọn patch Boot 3.x mới nhất trong phạm vi hỗ trợ và để BOM quản lý Framework 6.x tương ứng.

Đây là chính sách gợi ý, không thay thế việc kiểm tra yêu cầu runtime của SDK, database driver, Servlet container hoặc thư viện tích hợp mà sản phẩm thực sự sử dụng.

## 16. Câu hỏi tự kiểm tra

1. Ba trục version phải công bố là gì? **JDK tối thiểu, Spring Framework baseline và các dòng Spring Boot được hỗ trợ/kiểm thử.**
2. Build bằng JDK 21 có chứng minh thư viện chạy được trên Java 17 không? **Không.** Cần compile với `--release 17` và test runtime trên JDK 17.
3. Boot 3.5.x đi cùng dòng Framework nào? **Framework 6.2.x theo BOM của Boot 3.5.**
4. Boot 4.1.x đi cùng dòng Framework nào? **Framework 7.0.x theo BOM của Boot 4.1.**
5. Có nên tự pin `spring-context` version trong starter không? **Thông thường không.** Để BOM của Boot quản lý các Spring module.
6. Nếu cần hỗ trợ Boot 2.7 và Boot 3+, ranh giới lớn nào cần xem xét? **Java 8 so với Java 17 và namespace `javax.*` so với `jakarta.*`.**
7. Một module core Java thuần có cần phụ thuộc Boot không? **Không**, nếu nó không sử dụng Boot API.
8. Khi nào nên tách Boot 3 và Boot 4 adapter? **Khi API, dependency graph hoặc source integration không tương thích trong một artifact chung.**
9. Test với Boot 3.5 có chứng minh hỗ trợ Boot 3.3 không? **Không.** Cần chạy test trên Boot 3.3 nếu công bố hỗ trợ dòng đó.
10. `spring-boot-dependencies` BOM dùng để làm gì? **Chọn một tập dependency version tương thích đã được Boot quản lý.**
11. Vì sao không nên dùng version range thay cho ma trận test? **Resolver có thể chọn version chưa được kiểm chứng; range không phải bằng chứng compatibility.**
12. Những bằng chứng tối thiểu để công bố hỗ trợ một dòng Boot là gì? **Compile, unit/integration test, consumer test, JDK runtime test và dependency tree của dòng đó.**

## 17. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): yêu cầu JDK và Spring Framework của Boot 3.5.
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): yêu cầu JDK và Spring Framework của Boot 4.1.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): yêu cầu JDK và Spring Framework của Boot 4.0.
- [Spring Boot 3.4 — System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html): yêu cầu của dòng Boot 3.4.
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): yêu cầu của dòng Boot 3.3.
- [Spring Boot 3.2 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/getting-started.html): yêu cầu của dòng Boot 3.2.
- [Spring Boot 3.1 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/3.1.x/reference/htmlsingle/): yêu cầu của dòng Boot 3.1.
- [Spring Boot 3.0 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/3.0.13/reference/html/getting-started.html): yêu cầu của dòng Boot 3.0.
- [Spring Boot 2.7 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/2.7.18/reference/htmlsingle/): yêu cầu của dòng Boot 2.7.
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): BOM, dependency management và khuyến nghị không tự chỉ định Spring Framework version.
- [Spring Boot 3.3 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html): import BOM trong Gradle và quản lý dependency version.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6, Jakarta namespace và auto-configuration metadata migration.
- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/upgrading.html): cách tiếp cận migration và release notes khi nâng dòng Boot.
