# Thực nghiệm một thuộc tính xuất hiện trong nhiều nguồn

Trong ứng dụng Spring Boot, cùng một thuộc tính có thể được khai báo ở nhiều nơi: file application.yml, file theo profile, file cấu hình đặt ngoài JAR, biến môi trường của máy/container, Java system property, tham số dòng lệnh hoặc Config Server. Khi các giá trị khác nhau, ứng dụng sẽ dùng giá trị nào?

Spring Boot đưa các nguồn cấu hình vào Environment theo một thứ tự ưu tiên xác định. Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị từ nguồn thấp hơn. Hiểu thứ tự này giúp nhóm phát triển giải thích vì sao ứng dụng đang chạy với một giá trị khác với giá trị nhìn thấy trong repository.

Bài học thuộc chương **Nạp cấu hình** của module **SPRING_CLOUD_CORE**. Ta sẽ dùng một thuộc tính không nhạy cảm là `app.banner`, gán giá trị khác nhau ở từng nguồn, khởi động ứng dụng nhiều lần và quan sát giá trị thắng cuộc. Sau thí nghiệm, bài học mở rộng sang profile, `spring.config.import`, Spring Cloud Config Client và refresh runtime.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích khái niệm `PropertySource`, `Environment` và quy tắc nguồn có ưu tiên cao hơn ghi đè nguồn thấp hơn.
- Phân biệt thứ tự ưu tiên giữa các nhóm nguồn cấu hình với thứ tự tìm kiếm các file trong Config Data.
- Thực nghiệm một key xuất hiện trong file classpath, file profile, file ngoài JAR, environment variable, system property và command-line argument.
- Đọc giá trị qua `Environment` hoặc `@ConfigurationProperties` và kiểm tra nguồn cung cấp giá trị.
- Dùng `spring.config.import`, `spring.config.additional-location` và profile đúng mục đích.
- Phân biệt việc chọn giá trị lúc khởi động với việc refresh cấu hình khi ứng dụng đang chạy.
- Nhận diện các nguyên nhân phổ biến khiến một cấu hình bị ghi đè ngoài dự kiến.

## 2. Các khái niệm cần nắm

### 2.1. Property và PropertySource

Một **property** là một cặp tên và giá trị, ví dụ:

~~~properties
app.banner=Hello from application
~~~

Một **PropertySource** là nguồn cung cấp các property cho Spring `Environment`. File YAML, file `.properties`, biến môi trường, Java system properties và command-line arguments có thể được biểu diễn thành các nguồn khác nhau.

`Environment` tổng hợp các nguồn này. Khi gọi `environment.getProperty("app.banner")`, Spring tìm property theo thứ tự ưu tiên và trả về giá trị đầu tiên tìm thấy. Nếu cùng một key xuất hiện ở nhiều nguồn, giá trị của nguồn ưu tiên cao hơn sẽ được dùng.

~~~mermaid
flowchart TD
    A[application.yml] --> E[Spring Environment]
    B[application-lab.yml] --> E
    C[External config files] --> E
    D[OS environment variables] --> E
    F[Java system properties] --> E
    G[Command-line arguments] --> E
    E --> R[Resolve app.banner]
    R --> V[Effective value]
    V --> BIND[@ConfigurationProperties / @Value]
~~~

Sơ đồ thể hiện các nguồn cùng đóng góp vào `Environment`. Khi một key bị trùng, thứ tự ưu tiên quyết định giá trị hiệu lực.

### 2.2. Giá trị mặc định, giá trị ghi đè và giá trị hiệu lực

- **Giá trị mặc định** là giá trị được đặt để ứng dụng có thể chạy khi môi trường chưa cung cấp cấu hình riêng.
- **Giá trị ghi đè** là giá trị từ một nguồn ưu tiên cao hơn, dùng thay giá trị của nguồn thấp hơn.
- **Giá trị hiệu lực** (*effective value*) là kết quả mà ứng dụng thực sự đọc được từ `Environment` tại thời điểm truy vấn.

Ví dụ:

| Nguồn | Giá trị `app.banner` |
| --- | --- |
| `application.yml` trong JAR | `classpath-default` |
| `application-lab.yml` trong JAR | `profile-lab` |
| `./config/application.yml` | `external-default` |
| `./config/application-lab.yml` | `external-profile` |
| Biến môi trường `APP_BANNER` | `from-env` |
| Java system property `-Dapp.banner` | `from-system` |
| Argument `--app.banner` | `from-cli` |

Không phải tất cả các nguồn đều cùng một tầng. Trước tiên Spring Boot sắp xếp các file thuộc Config Data; sau đó Config Data được đặt trong thứ tự ưu tiên chung cùng các nguồn khác.

## 3. Thứ tự ưu tiên PropertySource

Tài liệu Spring Boot hiện hành mô tả thứ tự từ ưu tiên thấp đến cao. Nguồn xuất hiện sau trong danh sách có thể ghi đè nguồn xuất hiện trước. Bảng dưới đây theo tài liệu Spring Boot **3.5.x và 4.1.x**; nếu dự án dùng dòng Boot khác, hãy tra đúng phiên bản trước khi kết luận về một thứ tự chi tiết.

| Thứ tự thấp → cao | Nguồn | Ví dụ |
| ---: | --- | --- |
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` trên lớp `@Configuration` | File được khai báo qua annotation |
| 3 | Config Data | `application.yml`, file profile, file ngoài JAR, file import |
| 4 | `RandomValuePropertySource` | Các key thuộc `random.*` |
| 5 | OS environment variables | `APP_BANNER=from-env` |
| 6 | Java System properties | `-Dapp.banner=from-system` |
| 7 | JNDI attributes | `java:comp/env/...` |
| 8 | `ServletContext` init parameters | Tham số khởi tạo servlet context |
| 9 | `ServletConfig` init parameters | Tham số khởi tạo servlet |
| 10 | `SPRING_APPLICATION_JSON` | JSON inline trong environment hoặc system property |
| 11 | Command-line arguments | `--app.banner=from-cli` |
| 12 | `properties` trên `@SpringBootTest` hoặc test slice | `@SpringBootTest(properties = "...")` |
| 13 | `@DynamicPropertySource` | Dynamic properties trong test |
| 14 | `@TestPropertySource` | Property source khai báo trên test |
| 15 | Devtools global settings | Cấu hình Devtools trong thư mục người dùng khi Devtools hoạt động |

Các nguồn như JNDI và Servlet init parameters chỉ liên quan đến kiểu triển khai tương ứng. Trong một ứng dụng Spring Boot chạy độc lập, thí nghiệm thường tập trung vào Config Data, environment variables, system properties và command line.

### 3.1. Hai điểm dễ nhầm

**Environment variable và Java system property là hai nguồn khác nhau.** Theo thứ tự trong tài liệu Spring Boot 3.5.x/4.1.x nêu trên, Java system properties có ưu tiên cao hơn OS environment variables. Vì vậy, nếu cùng có `APP_BANNER=from-env` và `-Dapp.banner=from-system`, giá trị hiệu lực là `from-system`.

**Command-line arguments có ưu tiên cao hơn các nguồn cấu hình thông thường.** Khi chạy:

~~~bash
java -jar app.jar --app.banner=from-cli
~~~

giá trị `from-cli` ghi đè giá trị của file cấu hình, environment variable và system property cho cùng key. Có thể tắt việc thêm command-line properties vào `Environment` bằng `SpringApplication.setAddCommandLineProperties(false)`, nhưng ứng dụng thông thường giữ mặc định này.

### 3.2. Thứ tự trong Config Data là một lớp riêng

Với file cấu hình, Spring Boot xét các nhóm theo thứ tự sau, từ thấp đến cao:

1. `application.properties` hoặc YAML được đóng gói trong JAR.
2. File profile-specific được đóng gói trong JAR, ví dụ `application-lab.yml`.
3. `application.properties` hoặc YAML ở bên ngoài JAR.
4. File profile-specific ở bên ngoài JAR.

Do đó, file `./config/application-lab.yml` có thể ghi đè file `application.yml` trong JAR. Sau khi Config Data được resolve, các nguồn ưu tiên cao hơn như environment variables, system properties và command line vẫn có thể ghi đè giá trị từ file.

Trong cùng một thư mục, nếu đồng thời có `application.properties` và `application.yml`, Spring Boot ưu tiên `.properties`. Để tránh khó hiểu, nên thống nhất một định dạng cấu hình trong cùng vị trí.

## 4. Chuẩn bị thí nghiệm app.banner

Thí nghiệm sử dụng một Spring Boot application có `ApplicationRunner` để in giá trị hiệu lực. Không cần Config Server thật ở bước đầu; mục tiêu là quan sát cách Spring Boot resolve nhiều nguồn cục bộ và nguồn runtime.

### 4.1. Cấu trúc file

Tạo các file sau:

~~~text
config-precedence-demo/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/configdemo/
│       │       ├── ConfigDemoApplication.java
│       │       ├── AppProperties.java
│       │       └── ConfigReportRunner.java
│       └── resources/
│           ├── application.yml
│           └── application-lab.yml
├── config/
│   ├── application.yml
│   └── application-lab.yml
└── pom.xml
~~~

Thư mục `config/` nằm cạnh nơi chạy ứng dụng. Khi dùng Maven `spring-boot:run`, chạy lệnh từ thư mục gốc dự án để `./config/` được tìm thấy. Khi chạy JAR, đặt `config/` cạnh JAR và đặt working directory tại thư mục đó.

### 4.2. Khai báo giá trị trong file classpath

`src/main/resources/application.yml`:

~~~yaml
app:
  banner: "classpath-default"
~~~

`src/main/resources/application-lab.yml`:

~~~yaml
app:
  banner: "classpath-profile-lab"
~~~

File thứ hai chỉ được nạp khi profile `lab` đang active.

### 4.3. Khai báo giá trị trong file ngoài JAR

`config/application.yml`:

~~~yaml
app:
  banner: "external-default"
~~~

`config/application-lab.yml`:

~~~yaml
app:
  banner: "external-profile-lab"
~~~

Đây là các file ở vị trí cấu hình ngoài mặc định. Chúng không cần được đóng gói vào JAR. Khi chạy từ thư mục chứa `config/`, Spring Boot tự tìm thấy chúng theo quy tắc external application properties.

## 5. Đọc giá trị hiệu lực trong ứng dụng

Có thể truy cập cùng một property theo nhiều cách. Trong bài thực nghiệm, ta dùng `@ConfigurationProperties` để bind cấu hình có cấu trúc và `Environment` để quan sát giá trị được resolve.

### 5.1. Lớp nhận cấu hình

`AppProperties.java`:

~~~java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String banner = "code-default";

    public String getBanner() {
        return banner;
    }

    public void setBanner(String banner) {
        this.banner = banner;
    }
}
~~~

Giá trị `code-default` là giá trị khởi tạo trong Java. Nếu property `app.banner` được tìm thấy trong `Environment`, binder sẽ dùng giá trị cấu hình để bind vào bean.

### 5.2. Lớp ứng dụng

`ConfigDemoApplication.java`:

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` tìm các lớp có `@ConfigurationProperties` trong package ứng dụng và các package con.

### 5.3. In giá trị và nguồn đang chứa key

`ConfigReportRunner.java`:

~~~java
package com.example.configdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class ConfigReportRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ConfigReportRunner.class);

    private final ConfigurableEnvironment environment;
    private final AppProperties appProperties;

    public ConfigReportRunner(
            ConfigurableEnvironment environment,
            AppProperties appProperties) {
        this.environment = environment;
        this.appProperties = appProperties;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Effective app.banner from Environment: {}",
                environment.getProperty("app.banner"));
        log.info("Bound app.banner from AppProperties: {}",
                appProperties.getBanner());
        log.info("Active profiles: {}",
                String.join(",", environment.getActiveProfiles()));

        log.info("Property sources containing app.banner (high priority first):");
        for (PropertySource<?> source : environment.getPropertySources()) {
            Object candidate = source.getProperty("app.banner");
            if (candidate != null) {
                log.info("  {} -> {}", source.getName(), candidate);
            }
        }
    }
}
~~~

Vòng lặp giúp nhìn thấy nhiều nguồn cùng có key. `Environment.getProperty()` trả về giá trị theo thứ tự ưu tiên; danh sách `PropertySource` được duyệt theo thứ tự ưu tiên của `Environment`, nên nguồn chứa key xuất hiện đầu tiên là nguồn thắng trong phép resolve thông thường.

Đây là mã chẩn đoán cho property minh họa, không phải mẫu để in toàn bộ cấu hình production. Không log mật khẩu, token, connection string hoặc tất cả property source trong môi trường thật.

## 6. Chạy thí nghiệm theo từng bước

### 6.1. Bước 1 — Chỉ dùng cấu hình mặc định

Chạy ứng dụng từ thư mục gốc dự án:

Để quan sát riêng hai file classpath ở bước 1 và 2, tạm đổi tên hoặc di chuyển thư mục `config/` bên ngoài JAR. Khôi phục thư mục này trước bước 3 để quan sát độ ưu tiên của file ngoài.

~~~bash
./mvnw spring-boot:run
~~~

Chưa kích hoạt profile `lab` và chưa có nguồn ghi đè từ environment/system/command line. Nếu không có file ngoài JAR, kết quả là `classpath-default`.

Nếu file ngoài JAR `config/application.yml` đã tồn tại như cấu trúc ở trên, kết quả sẽ là `external-default`, vì file ngoài JAR có ưu tiên cao hơn file classpath.

### 6.2. Bước 2 — Kích hoạt profile lab

Chạy:

~~~bash
./mvnw -Dspring-boot.run.arguments="--spring.profiles.active=lab" spring-boot:run
~~~

Hoặc chạy JAR:

~~~bash
java -jar target/config-precedence-demo.jar --spring.profiles.active=lab
~~~

Kết quả là `external-profile-lab` nếu cả bốn file trong ví dụ đều tồn tại. File profile-specific ngoài JAR có ưu tiên cao hơn file profile-specific trong JAR và các file không profile.

### 6.3. Bước 3 — Thêm environment variable

Trên Windows PowerShell:

~~~powershell
$env:APP_BANNER = "from-env"
java -jar target/config-precedence-demo.jar --spring.profiles.active=lab
Remove-Item Env:APP_BANNER
~~~

Trên Linux/macOS:

~~~bash
APP_BANNER=from-env java -jar target/config-precedence-demo.jar --spring.profiles.active=lab
~~~

Kết quả là `from-env`. Spring Boot hỗ trợ relaxed binding cho tên biến môi trường. Với property `app.banner`, dạng environment variable tương ứng là `APP_BANNER`: chuyển thành chữ hoa và thay dấu chấm bằng dấu gạch dưới.

### 6.4. Bước 4 — Thêm Java system property

Chạy:

~~~bash
APP_BANNER=from-env java -Dapp.banner=from-system -jar target/config-precedence-demo.jar --spring.profiles.active=lab
~~~

Trên PowerShell, đặt biến trước rồi chạy lệnh:

~~~powershell
$env:APP_BANNER = "from-env"
java -Dapp.banner=from-system -jar target/config-precedence-demo.jar --spring.profiles.active=lab
Remove-Item Env:APP_BANNER
~~~

Kết quả là `from-system` theo thứ tự PropertySource của Spring Boot 3.5.x/4.1.x: Java system properties có ưu tiên cao hơn OS environment variables. Lưu ý `-Dapp.banner=...` phải đặt trước `-jar` trong lệnh Java để JVM nhận đó là system property.

### 6.5. Bước 5 — Thêm command-line argument

Chạy:

~~~bash
APP_BANNER=from-env java -Dapp.banner=from-system -jar target/config-precedence-demo.jar --spring.profiles.active=lab --app.banner=from-cli
~~~

Kết quả cuối cùng là `from-cli`, vì command-line arguments có ưu tiên cao hơn environment variables, Java system properties và Config Data.

### 6.6. Bảng kết quả dự kiến

| Lần chạy | Nguồn cao nhất đang có `app.banner` | Giá trị hiệu lực |
| --- | --- | --- |
| 1. Không profile, không override, không file ngoài | Classpath `application.yml` | `classpath-default` |
| 2. Profile `lab`, không file ngoài | Classpath `application-lab.yml` | `classpath-profile-lab` |
| 3. Có file ngoài, profile `lab` | `./config/application-lab.yml` | `external-profile-lab` |
| 4. Có `APP_BANNER` | OS environment variable | `from-env` |
| 5. Có thêm `-Dapp.banner` | Java system property | `from-system` |
| 6. Có thêm `--app.banner` | Command-line argument | `from-cli` |

Nếu kết quả khác bảng, đừng đổi ngẫu nhiên nhiều file. Hãy kiểm tra profile đang active, working directory, đường dẫn file cấu hình và danh sách `PropertySource` mà runner đã in.

## 7. Thay đổi vị trí nạp file cấu hình

Spring Boot tự tìm `application.properties` hoặc `application.yaml` ở các vị trí mặc định:

- Root của classpath.
- Thư mục `config/` trên classpath.
- Thư mục làm việc hiện tại.
- Thư mục `config/` trong thư mục làm việc.
- Các thư mục con trực tiếp của `config/` trong thư mục làm việc.

Các vị trí này được xét theo thứ tự; các vị trí có độ ưu tiên cao hơn có thể ghi đè vị trí được xét trước.

### 7.1. spring.config.additional-location

Dùng `additional-location` khi muốn **bổ sung** vị trí ngoài các vị trí mặc định:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./tenant-config/
~~~

Thư mục bổ sung được xét sau các vị trí mặc định nên có thể ghi đè giá trị từ các file mặc định.

### 7.2. spring.config.location

Dùng `location` khi muốn **thay thế** danh sách vị trí mặc định:

~~~bash
java -jar app.jar --spring.config.location=optional:file:./config-base/,optional:file:./config-prod/
~~~

Nếu đặt `spring.config.location`, các vị trí mặc định không còn tự động được tìm như trước. Điều này dễ làm mất cấu hình classpath hoặc cấu hình ngoài mà ứng dụng vẫn đang phụ thuộc. Nếu chỉ muốn bổ sung file cấu hình theo môi trường, thường nên cân nhắc `spring.config.additional-location`.

Các thuộc tính `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được dùng rất sớm để xác định nơi tìm file. Vì vậy, phải cung cấp chúng từ environment variable, system property hoặc command line; không đặt chúng trong file mà chính chúng cần điều khiển.

## 8. Profile và nhiều file cấu hình

Profile cho phép cùng một ứng dụng dùng cấu hình khác nhau theo môi trường:

~~~yaml
# application.yml
app:
  banner: "default"
~~~

~~~yaml
# application-dev.yml
app:
  banner: "development"
~~~

~~~yaml
# application-prod.yml
app:
  banner: "production"
~~~

Kích hoạt profile bằng:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Nếu nhiều profile cùng active, quy tắc last-wins áp dụng trong cùng nhóm vị trí: profile được xét sau có thể ghi đè giá trị trùng từ profile được xét trước, tùy vị trí và location group.

Không khai báo `spring.profiles.active` hoặc `spring.profiles.default` trong một tài liệu cấu hình chỉ được kích hoạt theo profile. Các thuộc tính dùng để chọn profile phải nằm trong nguồn không phụ thuộc profile hoặc được truyền từ môi trường khởi động.

### 8.1. Nhiều location và location group

Khi có nhiều `spring.config.location`, dấu phẩy và dấu chấm phẩy có ý nghĩa khác nhau:

- Dấu phẩy tách các location group, được xử lý theo thứ tự nhóm.
- Dấu chấm phẩy đặt nhiều location vào cùng một group để quy tắc profile được áp dụng ở cùng cấp.

Ví dụ `classpath:/cfg/,classpath:/ext/` không có cùng ý nghĩa với `classpath:/cfg/;classpath:/ext/` khi nhiều profile-specific file tồn tại. Chỉ dùng location group khi đã hiểu thứ tự cần đạt được; nếu không, cấu hình đơn giản sẽ dễ dự đoán hơn.

## 9. Nạp thêm nguồn bằng spring.config.import

`spring.config.import` cho phép một file cấu hình nhập thêm dữ liệu từ file khác hoặc một nguồn cấu hình được hỗ trợ. Giá trị trong file được import có thể ghi đè giá trị ở tài liệu khai báo import.

Ví dụ, `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./shared-config.yml"

app:
  banner: "from-application"
~~~

File `shared-config.yml`:

~~~yaml
app:
  banner: "from-import"
~~~

Khi file import tồn tại, giá trị hiệu lực trong Config Data là `from-import`. Từ `optional:` cho phép ứng dụng tiếp tục khởi động nếu file không tồn tại. Nếu bỏ `optional:`, ứng dụng sẽ báo lỗi khi location bắt buộc không được tìm thấy.

Nếu có nhiều location trong một khai báo import, các location được xử lý theo thứ tự đã khai báo; import sau có ưu tiên cao hơn import trước. Một location được import chỉ một lần dù được khai báo ở nhiều nơi.

### 9.1. Phân biệt import và additional-location

| Cơ chế | Được khai báo ở đâu? | Tác dụng |
| --- | --- | --- |
| `spring.config.import` | Trong tài liệu Config Data | Nhập thêm file/nguồn, import được đặt ngay dưới tài liệu khai báo và có thể ghi đè tài liệu đó |
| `spring.config.additional-location` | Environment, system property hoặc command line | Thêm các vị trí tìm kiếm vào nhóm vị trí cấu hình mặc định |
| `spring.config.location` | Environment, system property hoặc command line | Thay thế các vị trí tìm kiếm mặc định |

Không dùng ba cơ chế này như các tên gọi khác nhau của cùng một chức năng. Chúng tác động vào quá trình nạp Config Data ở các bước khác nhau.

## 10. Liên hệ với Spring Cloud Config Client

Spring Cloud Config Client đưa cấu hình từ Config Server vào ứng dụng Spring Boot. Với cách Config Data hiện đại, client dùng `spring.config.import`; không cần `bootstrap.yml` cho cách import này.

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Phiên bản dependency được quản lý bởi Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án.

Trong `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

Với `optional:`, ứng dụng có thể tiếp tục khởi động khi Config Server không truy cập được. Nếu bỏ tiền tố này, Config Client yêu cầu lấy được cấu hình từ server; ứng dụng sẽ dừng khởi động nếu không tải được cấu hình bắt buộc.

### 10.1. Thứ tự property sources trả về từ Config Server

Config Server có thể cung cấp cấu hình dùng chung và cấu hình theo từng ứng dụng/profile. Ví dụ, khi client có tên `order-service`, profile `prod` và cấu hình thêm tên `shared-db`, Config Server có thể trả các property source theo thứ tự:

1. `application.properties`
2. `application-prod.properties`
3. `order-service.properties`
4. `order-service-prod.properties`
5. `shared-db.properties`
6. `shared-db-prod.properties`

Các property source ở phía sau có thể ghi đè key trùng ở phía trước. Thứ tự cụ thể còn phụ thuộc `spring.cloud.config.name`, profile và label mà client yêu cầu.

### 10.2. Không áp dụng máy móc quy tắc legacy bootstrap

Tài liệu Spring Cloud Config có các thuộc tính điều khiển việc ghi đè remote property source như:

- `spring.cloud.config.allow-override`
- `spring.cloud.config.override-none`
- `spring.cloud.config.override-system-properties`

Các quy tắc này gắn với cơ chế bootstrap cũ và cách Config Client đặt remote property source. Đặc biệt, quyền cho phép override phải được cấp từ cấu hình phía server/repository; đặt `allow-override` tùy ý trong cấu hình local không có nghĩa client sẽ tự có quyền ghi đè remote source. Không sao chép các cờ này vào ứng dụng dùng `spring.config.import` mà không đọc tài liệu của đúng phiên bản Spring Cloud Config và đúng chế độ bootstrap.

Khi dùng Config Data import, hãy quan sát các property source thực tế bằng `Environment` hoặc công cụ chẩn đoán. Đừng gộp thứ tự của file classpath, file ngoài JAR, remote Config Server và legacy bootstrap thành một bảng duy nhất áp dụng cho mọi cấu hình.

## 11. Xác định nguồn nào đã cung cấp giá trị

### 11.1. Dùng Environment

Trong code, có thể đọc giá trị:

~~~java
String banner = environment.getProperty("app.banner");
~~~

Nếu cần biết nguồn nào đang có key, duyệt `environment.getPropertySources()` như ví dụ `ConfigReportRunner`. Tên nguồn giúp nhận diện file, system properties, environment hoặc command line. Cách này rất hữu ích khi debug trong môi trường local.

### 11.2. Dùng Actuator env và configprops

Actuator có endpoint `env` và `configprops` hỗ trợ chẩn đoán property source và binding. Chúng có thể cho biết property đến từ nguồn nào và giá trị nào đã được bind.

Nếu cần expose endpoint `env` trong môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
  endpoint:
    env:
      show-values: "never"
~~~

Chỉ bật tạm thời trong môi trường local hoặc mạng quản trị đã bảo vệ. Nếu cần xem giá trị, dùng cơ chế `show-values` có kiểm soát và xác thực phù hợp với phiên bản Boot. Không expose `env` hoặc `configprops` công khai vì chúng có thể tiết lộ cấu trúc cấu hình và thông tin nhạy cảm.

### 11.3. Bật log quá trình nạp Config Data

Khi không hiểu vì sao một file không được nạp, có thể tăng log của bộ xử lý config:

~~~yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
~~~

Log TRACE giúp xác định các location được kiểm tra và file được nạp. Không duy trì mức log TRACE cho bộ xử lý cấu hình trong production nếu không có nhu cầu chẩn đoán cụ thể.

## 12. Giá trị lúc khởi động và refresh runtime là hai việc khác nhau

Thí nghiệm `app.banner` ở các phần trước chạy lại ứng dụng mỗi khi đổi environment variable, system property hoặc command-line argument. Những nguồn này thường được đọc trong quá trình tạo `Environment` và khởi động context.

Thay file cấu hình trên đĩa hoặc cập nhật giá trị trong Config Server **không tự động có nghĩa mọi bean đang chạy đều nhận giá trị mới ngay lập tức**. Cần phân biệt:

- **Nạp cấu hình lúc khởi động:** Spring Boot tạo `Environment`, resolve property source và bind giá trị cho bean.
- **Refresh cấu hình:** một cơ chế runtime cập nhật `Environment`/phát sự kiện, sau đó các bean hoặc scope được hỗ trợ mới có thể phản ánh giá trị mới.
- **Restart/rollout:** tạo process hoặc instance mới để nạp lại cấu hình từ đầu.

Trong Spring Cloud, `@RefreshScope` có thể làm mới bean được quản lý trong refresh scope sau khi quy trình refresh được kích hoạt. Tuy nhiên, không phải mọi bean đều refresh được và không nên giả định việc thay đổi một file tự gửi refresh event đến tất cả instance.

Với cấu hình có ảnh hưởng đến kết nối database, bảo mật, pool, thread hoặc bean khởi tạo một lần, cần đánh giá liệu refresh có an toàn hay phải restart/rollout. Với cấu hình nhạy cảm hoặc thay đổi ảnh hưởng hành vi nghiệp vụ, cần có kiểm soát phiên bản, audit và phương án rollback.

## 13. Những lỗi thường gặp khi thí nghiệm

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Sửa `application.yml` nhưng giá trị không đổi | File ngoài JAR hoặc nguồn khác đang ghi đè | In danh sách `PropertySource`; kiểm tra `./config/` |
| `application-lab.yml` không được nạp | Profile `lab` chưa active hoặc file đặt sai tên/vị trí | In `Environment.getActiveProfiles()` và bật TRACE cho config loader |
| Biến môi trường không ghi đè | Sai tên biến, sai process/container hoặc có system property/CLI ưu tiên cao hơn | Kiểm tra `APP_BANNER`, command line và `-Dapp.banner` |
| `-Dapp.banner` không có tác dụng | Đặt `-D` sau `-jar` hoặc truyền nhầm vào application arguments | Đưa `-D...` trước `-jar` |
| Tham số `--app.banner` không có tác dụng | Chạy wrapper/build tool nhưng chưa truyền argument vào JVM/application đúng cách | Kiểm tra lệnh thực tế và `ApplicationArguments` |
| File `application.properties` và `application.yml` cho kết quả bất ngờ | Cả hai cùng tồn tại ở một vị trí; `.properties` được ưu tiên | Chỉ giữ một định dạng hoặc kiểm tra property source |
| `spring.config.location` làm mất cấu hình cũ | Thuộc tính này thay thế vị trí mặc định | Chuyển sang `spring.config.additional-location` nếu mục tiêu là bổ sung |
| `spring.config.import` không tìm thấy file | Location bắt buộc không tồn tại hoặc sai relative path | Kiểm tra working directory; dùng `optional:` chỉ khi nguồn thật sự tùy chọn |
| Config Server ghi đè local ngoài dự kiến | Chế độ Config Data/bootstrap hoặc cờ override khác nhau | Kiểm tra property source, phiên bản và cấu hình remote repository |
| Thay file nhưng bean vẫn giữ giá trị cũ | Bean đã bind lúc startup và chưa có refresh/restart | Kiểm tra refresh scope/event hoặc thực hiện rollout |

## 14. Bài tập thực hành

### Bài 1 — Dự đoán trước khi chạy

Giả sử cùng có các giá trị:

~~~text
application.yml                       = file
./config/application.yml              = external
APP_BANNER                            = env
-Dapp.banner                          = system
--app.banner                          = cli
~~~

Hãy dự đoán giá trị `Environment.getProperty("app.banner")` sẽ trả về. Sau đó chạy ứng dụng và đối chiếu với kết quả.

### Bài 2 — Đổi thứ tự nguồn

1. Xóa argument `--app.banner`.
2. Giữ `APP_BANNER=env` và `-Dapp.banner=system`.
3. Dự đoán giá trị trước khi chạy.
4. Xóa `-Dapp.banner` rồi chạy lại.
5. Ghi lại nguồn thắng ở từng lần.

### Bài 3 — So sánh profile

Tạo thêm `application-region-a.yml` và `application-region-b.yml`, mỗi file có một giá trị khác nhau. Chạy với:

~~~bash
java -jar app.jar --spring.profiles.active=region-a,region-b
~~~

Sau đó đảo thứ tự profile. Quan sát chiến lược last-wins và giải thích tại sao file ngoài JAR vẫn có thể ghi đè file trong JAR.

### Bài 4 — Import cấu hình dùng chung

Tạo `shared-config.yml`, khai báo nó trong `spring.config.import`, đặt cùng key `app.banner` ở cả hai file. Chạy ứng dụng khi file import tồn tại và khi file bị đổi tên. Thử cả hai trường hợp có và không có tiền tố `optional:`.

### Bài 5 — Liên hệ Config Server

Đọc tài liệu Spring Cloud Config Client và mô tả:

- Config Server lấy `application`, `profile`, `label` từ đâu.
- Vì sao Config Data import có thể gọi Config Server nhiều lần khi profile được kích hoạt trong quá trình nạp cấu hình.
- Khi nào ứng dụng nên fail startup nếu Config Server không sẵn sàng.
- Vì sao không thể áp dụng các cờ legacy bootstrap override một cách tùy tiện cho mọi cấu hình hiện đại.

**Tiêu chí hoàn thành:** bạn có thể giải thích một giá trị hiệu lực bằng cách chỉ ra đúng property source thắng cuộc, tái hiện được kết quả bằng lệnh chạy và nhận diện được khi nào phải restart hoặc refresh bean.

## 15. Tổng kết

Spring Boot không chọn ngẫu nhiên một giá trị khi cùng property xuất hiện ở nhiều nơi. `Environment` tổng hợp các `PropertySource` theo thứ tự xác định; nguồn có ưu tiên cao hơn cung cấp giá trị hiệu lực. Trong một ứng dụng thông thường, file profile-specific và file ngoài JAR có thể ghi đè cấu hình mặc định, còn environment variable, Java system property và command line có các mức ưu tiên riêng.

Để xử lý một cấu hình bị ghi đè, hãy kiểm tra theo thứ tự: profile đang active, location và file Config Data được nạp, các import, environment variable, system property, command line và cuối cùng là property source trong `Environment`. Khi dùng Spring Cloud Config, cần tính đến thứ tự property source từ server và phân biệt Config Data import với legacy bootstrap. Khi ứng dụng đã chạy, thay đổi nguồn cấu hình còn cần quy trình refresh hoặc restart phù hợp.

## Tài liệu tham khảo

- [Spring Boot 4.1 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự `PropertySource`, Config Data, profile, import và biến môi trường.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): đối chiếu thứ tự property source trên dòng Boot 3.5.
- [Spring Boot — Properties and Configuration How-to](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html): vị trí file, `spring.config.location` và `spring.config.additional-location`.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, profile, property sources từ Config Server và hành vi khi server không sẵn sàng.
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html): cơ chế override ở phía Config Server.

Thứ tự chi tiết và hành vi của các thuộc tính cấu hình có thể thay đổi theo phiên bản. Khi làm việc với dự án thực tế, hãy đối chiếu tài liệu của đúng release train Spring Boot/Spring Cloud đang triển khai.
