# Đóng gói JAR rồi chạy bằng cấu hình ngoài ở hai môi trường

Một ứng dụng Spring Boot thường chạy ở nhiều môi trường như development và production. Hai môi trường có thể dùng cùng business logic và cùng phiên bản ứng dụng, nhưng khác database, endpoint dịch vụ ngoài, port, logging level, feature flags và secret.

Một cách triển khai dễ kiểm soát là **build executable JAR một lần, sau đó chạy chính artifact đó với cấu hình bên ngoài khác nhau ở từng môi trường**. JAR chứa code và dependency của ứng dụng; file cấu hình và secret được cung cấp lúc chạy. Nhờ vậy, không cần tạo một JAR riêng cho dev và một JAR khác cho production.

Bài thực hành đi qua toàn bộ luồng: tạo executable JAR bằng Maven hoặc Gradle, bố trí thư mục triển khai, nạp external configuration, chọn profile, cấp environment variables, kiểm tra property precedence và xác nhận hai môi trường đang chạy đúng cấu hình. Các ví dụ dùng một dịch vụ Spring Boot có database và partner API; tên ứng dụng, đường dẫn và endpoint là dữ liệu minh họa.

## 1. Mục tiêu và nguyên tắc triển khai

Giả sử có ứng dụng `orders-service`. Nó cần cùng một phiên bản code ở dev và production, database riêng, partner API endpoint riêng, timeout/logging/feature flags có thể cấu hình, secret được cấp an toàn và khả năng xác định chính xác JAR nào đang chạy.

~~~text
                 Source code
                     |
                     v
             Maven / Gradle build
                     |
                     v
          orders-service.jar (một lần)
                     |
             +-------+-------+
             |               |
             v               v
         DEV host        PROD host
             |               |
       external config  external config
       DEV profile      PROD profile
       DEV secrets      PROD secrets
             |               |
             v               v
       Spring Boot      Spring Boot
       application      application
             |               |
             v               v
       DEV database     PROD database
       DEV partner      PROD partner
~~~

Nguyên tắc quan trọng:

1. **Build artifact một lần:** JAR được tạo từ một commit/build cụ thể.
2. **Cấu hình được cấp lúc runtime:** không đóng cứng URL database, password hay endpoint production vào JAR.
3. **Cùng artifact, khác environment:** khác biệt nằm ở external config, environment variables và runtime options.
4. **Mỗi môi trường có secret riêng:** dev không dùng credential production và ngược lại.
5. **Có thể truy vết:** ghi nhận version, commit SHA và checksum của JAR được phát hành.

Một JAR khác nhau cho từng môi trường làm tăng nguy cơ build drift: hai artifact có thể chứa code hoặc dependency khác nhau dù cùng được gọi là một release. Mô hình build once, deploy many giảm rủi ro đó.

## 2. Tách artifact khỏi cấu hình

Executable JAR của Spring Boot thường chứa:

~~~text
orders-service.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/orders/...
    │   └── application.yml
    └── lib/
        ├── spring-boot-...
        ├── spring-context-...
        └── ...
~~~

File `application.yml` bên trong JAR có thể chứa cấu hình mặc định dùng chung hoặc giá trị an toàn cho local development. Khi chạy, Spring Boot có thể đọc thêm file bên ngoài JAR. External configuration có precedence cao hơn packaged defaults theo quy tắc Config Data/property sources.

Một layout dễ vận hành:

~~~text
deploy/
├── dev/
│   ├── orders-service.jar
│   └── config/
│       ├── application.yml
│       └── application-dev.yml
└── prod/
    ├── orders-service.jar
    └── config/
        ├── application.yml
        └── application-prod.yml
~~~

Hai thư mục có bản sao của **cùng một JAR**. Nội dung config khác nhau theo môi trường. Nếu dùng artifact registry, mỗi host có thể tải cùng artifact theo version hoặc digest đã phát hành.

Không đóng gói database password, API token, private key, broker credential, cloud access key hoặc signing secret vào JAR. Cấp chúng qua secret manager, environment variables, mounted secret files hoặc cơ chế bảo mật của nền tảng triển khai.

## 3. Tạo executable JAR bằng Maven

Với Maven và Spring Boot Maven Plugin, cấu hình plugin thường nằm trong POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu dùng `spring-boot-starter-parent`, plugin version thường được quản lý cùng Spring Boot release. Nếu dự án chỉ import Boot BOM mà không dùng parent, có thể cần khai báo plugin version và cấu hình riêng.

Build:

~~~bash
mvn clean package
~~~

Với project được cấu hình để repackage executable JAR, artifact thường nằm trong `target/orders-service-1.0.0.jar`. Tên thực tế phụ thuộc `artifactId`, `version` và cấu hình build.

Chạy thử:

~~~bash
java -jar target/orders-service-1.0.0.jar
~~~

Lệnh này chạy JAR bằng JVM hiện tại và dùng cấu hình mặc định có sẵn. Không cần build riêng một JAR tên `orders-service-dev.jar` hoặc `orders-service-prod.jar`.

Có thể xem nội dung JAR:

~~~bash
jar tf target/orders-service-1.0.0.jar
~~~

Executable JAR của Spring Boot có launcher phù hợp trong manifest. Nếu `java -jar` báo không có main manifest attribute hoặc không tìm thấy main class, có thể bạn đang chạy plain JAR thay vì Boot executable JAR, hoặc plugin repackage chưa chạy đúng.

## 4. Tạo executable JAR bằng Gradle

Với Gradle và Spring Boot plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}
~~~

Build executable JAR:

~~~bash
./gradlew clean bootJar
~~~

Artifact thường nằm trong `build/libs/`. Ví dụ:

~~~bash
java -jar build/libs/orders-service-1.0.0.jar
~~~

Tên và version plugin trong ví dụ là placeholder. Chọn phiên bản phù hợp với Java, Gradle wrapper và Spring Boot release đang dùng.

Nếu dự án tạo cả plain JAR và Boot executable JAR, hãy xác định đúng task/output cần phát hành. Không copy một file bất kỳ trong `build/libs` sang deployment directory.

| Công việc | Maven | Gradle |
|---|---|---|
| Build executable JAR | `mvn clean package` với Boot plugin | `./gradlew bootJar` |
| Output thường gặp | `target/` | `build/libs/` |
| Chạy | `java -jar path/app.jar` | `java -jar path/app.jar` |
| Dependency inspection | `mvn dependency:tree` | `./gradlew dependencies` |

Sau khi artifact đã được tạo, cách cung cấp external configuration khi chạy là như nhau. Cơ chế runtime configuration không phụ thuộc bạn đã dùng Maven hay Gradle để build.

## 5. Cấu hình mặc định trong JAR

Một file `src/main/resources/application.yml` có thể chứa thiết lập chung, không nhạy cảm:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

app:
  partner:
    timeout: 3s
  checkout:
    allow-test-cards: false

logging:
  level:
    root: INFO
~~~

File này được đóng gói vào classpath của JAR và đóng vai trò **default configuration**. Không đặt thông tin đặc thù production vào đây nếu muốn artifact dùng được ở nhiều môi trường. Không hard-code database URL production, hostname nội bộ production hoặc password.

### Bind cấu hình bằng @ConfigurationProperties

~~~java
@ConfigurationProperties(prefix = "app.partner")
@Validated
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout
) {
    public PartnerProperties {
        if (timeout != null && timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.partner.timeout must not be negative"
            );
        }
    }
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` trên application class hoặc `@EnableConfigurationProperties(PartnerProperties.class)` trong configuration phù hợp.

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Typed properties giúp tập trung cấu hình, conversion và validation. Với production, endpoint bắt buộc nên fail fast nếu thiếu hoặc sai định dạng thay vì tự dùng một URL mặc định không phù hợp.

## 6. Spring Boot tìm external configuration ở đâu?

Khi chạy executable JAR, Spring Boot dùng Config Data mechanism để tìm file cấu hình theo những vị trí mặc định. Những vị trí thường gặp gồm:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
~~~

Các phiên bản hiện đại còn hỗ trợ tìm trong những thư mục con cấu hình theo quy tắc location được tài liệu hóa. Hãy đối chiếu đúng phiên bản Boot của ứng dụng nếu cần dựa vào behavior chi tiết.

Điều cần nhớ:

- `classpath:/application.yml` là file được đóng gói trong JAR.
- `file:./application.yml` là file ở working directory của process.
- `file:./config/application.yml` là file trong thư mục `config` bên dưới working directory.
- External locations có độ ưu tiên cao hơn packaged defaults theo thứ tự location của Config Data.

### Working directory ảnh hưởng đường dẫn tương đối

Giả sử JAR nằm tại `/opt/orders/orders-service.jar`. Nếu chạy:

~~~bash
cd /opt/orders
java -jar orders-service.jar
~~~

thì `file:./config/application.yml` trỏ tới `/opt/orders/config/application.yml`.

Nếu chạy JAR từ working directory khác, `./config` được tính từ working directory mới, không tự động tính từ nơi chứa JAR. Đây là nguyên nhân phổ biến khiến ứng dụng “không đọc thấy file config” dù file vẫn tồn tại.

## 7. Tổ chức hai môi trường bằng profile

Spring Profiles cho phép chọn tập cấu hình theo môi trường.

File cấu hình trong JAR:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

app:
  partner:
    timeout: 3s
  checkout:
    allow-test-cards: false
~~~

File ngoài JAR cho dev:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: https://partner-dev.example.test
  checkout:
    allow-test-cards: true

logging:
  level:
    root: DEBUG
    com.example.orders: DEBUG
~~~

File ngoài JAR cho production:

~~~yaml
spring:
  datasource:
    url: `DOLLAR`{DB_URL}
    username: `DOLLAR`{DB_USERNAME}
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
  checkout:
    allow-test-cards: false

logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

Đặt các file theo profile:

~~~text
config/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

`application.yml` chứa cấu hình chung; `application-dev.yml` chỉ được nạp khi profile `dev` active; `application-prod.yml` chỉ được nạp khi profile `prod` active.

Có thể đặt cấu hình chung trong JAR và chỉ đưa các override ra ngoài. Khi đó file external profile chỉ cần chứa những property thực sự khác.

Đặt `spring.profiles.active` ở nguồn cấu hình không gắn profile, ví dụ command line, environment variable hoặc application.yml chung. Không đặt nó bên trong `application-prod.yml` với ý định tự kích hoạt chính profile đó. Spring cần biết profile trước khi quyết định nạp profile-specific documents.

## 8. Chạy JAR ở môi trường dev

Giả sử deployment directory:

~~~text
deploy/dev/
├── orders-service.jar
└── config/
    ├── application.yml
    └── application-dev.yml
~~~

Chạy từ thư mục `deploy/dev`:

~~~bash
cd deploy/dev
java -jar orders-service.jar --spring.profiles.active=dev
~~~

Spring Boot đọc cấu hình mặc định trong JAR, external configuration tại working directory/config, rồi nạp thêm profile-specific configuration cho `dev`. Nếu `config/application-dev.yml` chứa `spring.datasource.url`, nó cung cấp URL cho database dev.

Cấp secret cho dev bằng Linux/macOS shell:

~~~bash
export DB_PASSWORD='dev-password-from-local-secret-store'
java -jar orders-service.jar --spring.profiles.active=dev
~~~

PowerShell:

~~~powershell
$env:DB_PASSWORD = 'dev-password-from-local-secret-store'
java -jar .\orders-service.jar --spring.profiles.active=dev
~~~

Password ở trên chỉ minh họa cú pháp. Không commit password thật vào repository hoặc lưu trong script triển khai dùng chung.

## 9. Chạy cùng JAR ở môi trường production

Deployment directory:

~~~text
deploy/prod/
├── orders-service.jar
└── config/
    ├── application.yml
    └── application-prod.yml
~~~

Linux/macOS shell:

~~~bash
cd deploy/prod
export DB_URL='jdbc:postgresql://db.prod.internal:5432/orders'
export DB_USERNAME='orders_app'
export DB_PASSWORD='injected-by-secret-manager'
export PARTNER_BASE_URL='https://partner.example.com'

java -jar orders-service.jar --spring.profiles.active=prod
~~~

PowerShell:

~~~powershell
Set-Location .\deploy\prod
$env:DB_URL = 'jdbc:postgresql://db.prod.internal:5432/orders'
$env:DB_USERNAME = 'orders_app'
$env:DB_PASSWORD = 'injected-by-secret-manager'
$env:PARTNER_BASE_URL = 'https://partner.example.com'

java -jar .\orders-service.jar --spring.profiles.active=prod
~~~

Trong production thật, secret manager hoặc orchestration platform nên cấp những environment variables này. Không ghi credential vào shell history, file batch dùng chung hoặc CI log.

| Thuộc tính | Dev | Production |
|---|---|---|
| Artifact | Cùng version JAR | Cùng version JAR |
| Active profile | `dev` | `prod` |
| Database | Database dev | Database production |
| Partner API | Sandbox/dev endpoint | Production endpoint |
| Logging | Có thể DEBUG cho package ứng dụng | Thường INFO hoặc policy vận hành |
| Test-only feature | Có thể bật có kiểm soát | Tắt |
| Secrets | Dev credentials | Production secrets |
| Deploy config | External dev config | External prod config |

Profile không phải cơ chế bảo mật. Nếu một feature nguy hiểm phải tuyệt đối không bật trong production, cần validation/policy bổ sung và test cấu hình production; không chỉ dựa vào tên profile.

## 10. Thay đổi external config mà không build lại JAR

Giả sử JAR có default:

~~~yaml
server:
  port: 8080
~~~

External config có thể override:

~~~yaml
server:
  port: 8090
~~~

Khi khởi động, server dùng giá trị có precedence cao hơn theo Config Data/property source ordering.

External config có thể thay database URL, partner API endpoint, connection pool size, logging level, feature flags, timeout/retry values và management endpoint configuration.

Sau khi thay đổi external config, thông thường phải restart process để Spring đọc lại cấu hình lúc startup. Spring Boot không tự động reload mọi property trong mọi loại file chỉ vì file đã được sửa. Nếu ứng dụng dùng cơ chế refresh/config server riêng, đó là thiết kế khác cần cấu hình và kiểm soát rõ.

Không sửa file bên trong JAR để đổi môi trường. Việc giải nén, sửa rồi đóng gói lại làm artifact khác đi và mất tính reproducible. External configuration được thiết kế để tách biến môi trường khỏi artifact.

## 11. Property precedence: giá trị nào thắng?

Spring Boot có nhiều property sources. Quy tắc chính cần nhớ là **nguồn có precedence cao hơn có thể override nguồn thấp hơn**.

Trong các nguồn thông dụng, thứ tự khái quát từ thấp lên cao:

~~~text
Packaged application.yml
          |
          v
External application.yml / profile config
          |
          v
OS environment variables
          |
          v
Java system properties (-D...)
          |
          v
Spring command-line arguments (--key=value)
~~~

Thứ tự đầy đủ có thêm các nguồn như default properties, `@PropertySource`, random values, JNDI/servlet sources và test property sources. Với một trường hợp cần xác định chính xác, hãy dùng bảng property source precedence của đúng phiên bản Spring Boot.

Ví dụ cùng một key:

Packaged:

~~~yaml
server:
  port: 8080
~~~

External:

~~~yaml
server:
  port: 8081
~~~

Environment:

~~~text
SERVER_PORT=8082
~~~

Command line:

~~~bash
java -jar orders-service.jar --server.port=8083
~~~

Kết quả hiệu lực có thể là `8083` vì command-line properties có precedence cao hơn các nguồn trên trong cấu hình thông thường.

Trong nhóm Config Data, location và profile-specific file có quy tắc thứ tự riêng. Sau khi Config Data được nạp, OS environment, system properties và command line còn có precedence riêng. Khi nhiều nguồn cùng định nghĩa một key, cần xét cả hai tầng.

## 12. Thêm external location bằng spring.config.additional-location

Các thư mục mặc định thường đủ khi deployment có layout `./config/`. Nếu config nằm ở vị trí khác, có thể thêm location:

~~~bash
java -jar orders-service.jar \
  --spring.config.additional-location=file:./external-config/
~~~

Ví dụ layout:

~~~text
deploy/prod/
├── orders-service.jar
└── external-config/
    ├── application.yml
    └── application-prod.yml
~~~

Chạy:

~~~bash
cd deploy/prod
java -jar orders-service.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:./external-config/
~~~

`spring.config.additional-location` **bổ sung** location vào các location mặc định. Các property trong location được thêm có thể override giá trị từ những location trước theo thứ tự Config Data.

Nếu thư mục bắt buộc phải tồn tại, dùng location không có `optional:` để startup báo lỗi khi thiếu. Nếu nó thật sự tùy chọn, có thể viết:

~~~bash
--spring.config.additional-location=optional:file:./external-config/
~~~

Dùng `optional:` có chủ đích. Nếu production bắt buộc phải có external config nhưng lại đánh dấu optional, ứng dụng có thể khởi động với default values sai môi trường.

Khi trỏ đến directory, dấu slash cuối giúp Spring hiểu đây là thư mục location và tìm các config names bên trong. Spring Boot tự xử lý Config Data, profile-specific files và property sources; không cần tự đọc YAML rồi merge map vào Environment nếu use case được Config Data hỗ trợ.

## 13. spring.config.location khác spring.config.additional-location

Hai property này dễ bị nhầm:

| Property | Ý nghĩa |
|---|---|
| `spring.config.location` | Chỉ định locations để nạp cấu hình; có thể thay thế các default locations |
| `spring.config.additional-location` | Thêm locations vào default search locations |

Ví dụ:

~~~bash
java -jar orders-service.jar \
  --spring.config.location=file:./only-this-config/
~~~

Lệnh này có thể làm các default locations không còn được tìm theo cách thông thường. Nếu JAR đang dựa vào `classpath:/application.yml`, việc thay toàn bộ locations có thể khiến default config không được nạp như bạn nghĩ.

Khi chỉ muốn thêm config bên ngoài và vẫn giữ cấu hình mặc định trong JAR, thường dùng `spring.config.additional-location`. Dùng `spring.config.location` khi bạn muốn kiểm soát toàn bộ nơi cấu hình được đọc và chủ động cung cấp mọi location cần thiết.

## 14. spring.config.name và spring.config.import

Mặc định Spring Boot tìm basename như `application`. Nếu muốn dùng tên khác:

~~~bash
java -jar orders-service.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=file:./config/
~~~

Khi đó Spring tìm các file tương ứng như `orders.properties`, `orders.yml`, `orders-dev.yml` và `orders-prod.yml` theo Config Data rules. Đổi basename chỉ khi tổ chức có convention rõ ràng.

Trong Config Data mechanism, một file có thể import file khác:

~~~yaml
spring:
  config:
    import: "optional:file:./secrets/application-secrets.yml"
~~~

`spring.config.import` được xử lý trong giai đoạn Config Data loading. Các import có quy tắc precedence và profile activation riêng; không nên coi nó như một lệnh include YAML đơn giản.

Đặt secret trong file riêng không tự làm nó an toàn. Nếu file nằm trong repository hoặc được đóng gói vào JAR, nó vẫn có thể bị lộ. Phải kiểm soát nơi file được lưu, quyền đọc, backup và cách cấp cho process.

### Config tree và mounted secrets

Một số môi trường mount secret thành file và Spring Boot hỗ trợ config tree imports:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Các file trong thư mục có thể được ánh xạ thành property theo tên tương ứng. Cần xác nhận cú pháp, mount path và behavior của Boot version đang dùng. Không dùng `optional:` nếu secret đó bắt buộc để ứng dụng hoạt động an toàn.

## 15. Environment variables và relaxed binding

Spring Boot hỗ trợ map property names sang environment variable theo quy tắc relaxed binding. Ví dụ thường gặp:

| Property | Environment variable |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `app.partner.base-url` | `APP_PARTNER_BASEURL` |
| `app.partner.timeout` | `APP_PARTNER_TIMEOUT` |

Với environment variables, dấu chấm được chuyển thành dấu gạch dưới và tên thường được viết hoa; dấu gạch nối trong tên property được bỏ theo quy tắc mapping của Boot. Với property phức tạp hoặc collection/map, hãy kiểm tra relaxed binding documentation.

Ví dụ chạy production:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
export SERVER_PORT=8080
export SPRING_DATASOURCE_URL='jdbc:postgresql://db.prod.internal:5432/orders'
export SPRING_DATASOURCE_USERNAME='orders_app'
export SPRING_DATASOURCE_PASSWORD='injected-secret'
export APP_PARTNER_BASEURL='https://partner.example.com'

java -jar orders-service.jar
~~~

Environment variables là cách phổ biến và được nhiều platform hỗ trợ. Tuy nhiên, chúng có thể hiển thị trong process inspection, diagnostic dumps hoặc cấu hình vận hành tùy host. Nếu nền tảng có secret file/config tree hoặc secret manager integration, hãy cân nhắc chính sách bảo mật thực tế. Không log toàn bộ Environment hoặc in password khi debug.

## 16. Dùng command-line arguments cho runtime override

Spring Boot cho phép truyền property theo dạng:

~~~bash
java -jar orders-service.jar --server.port=8090
~~~

Có thể truyền nhiều property:

~~~bash
java -jar orders-service.jar \
  --spring.profiles.active=prod \
  --server.port=8080 \
  --logging.level.com.example.orders=INFO
~~~

Command-line properties có precedence cao trong những nguồn thông dụng. Đây là cách hữu ích cho những override có chủ đích, nhưng không nên đưa một danh sách dài cấu hình production vào script command line nếu có thể quản lý qua external config/environment.

Các option Spring Boot dạng `--name=value` được truyền sau JAR:

~~~bash
java -jar orders-service.jar --spring.profiles.active=dev
~~~

JVM options như `-Xms`, `-Xmx`, `-Dname=value` phải được đặt trước `-jar`:

~~~bash
java -Xms256m -Xmx768m \
  -Duser.timezone=UTC \
  -jar orders-service.jar \
  --spring.profiles.active=prod
~~~

Đặt nhầm vị trí có thể khiến Java coi option là đối số của application hoặc không áp dụng như mong đợi.

## 17. Chọn profile bằng environment variable và YAML documents

Có thể không cần truyền profile qua command line.

Linux/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=dev
java -jar orders-service.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar .\orders-service.jar
~~~

Production platform có thể khai báo `SPRING_PROFILES_ACTIVE=prod`. Profile chỉ chọn tập cấu hình. Nó không tự tạo credential, không mã hóa password và không ngăn một file prod bị đọc bởi người không có quyền.

Có thể đặt cấu hình theo từng file:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

Hoặc dùng YAML multi-document với profile activation:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

---
spring:
  config:
    activate:
      on-profile: dev

logging:
  level:
    root: DEBUG

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
~~~

Phân biệt:

- `spring.profiles.active` chọn profile đang chạy.
- `spring.config.activate.on-profile` quy định document/file được áp dụng khi profile tương ứng active.

Một document không tự kích hoạt profile chỉ vì nó có `on-profile`.

## 18. Cấu hình chung và override phần khác nhau

Không cần copy toàn bộ application.yml vào từng môi trường.

Packaged `application.yml`:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

app:
  partner:
    timeout: 3s
  checkout:
    allow-test-cards: false

logging:
  level:
    root: INFO
~~~

External `application-dev.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: https://partner-dev.example.test
  checkout:
    allow-test-cards: true

logging:
  level:
    com.example.orders: DEBUG
~~~

External `application-prod.yml`:

~~~yaml
spring:
  datasource:
    url: `DOLLAR`{DB_URL}
    username: `DOLLAR`{DB_USERNAME}
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
  checkout:
    allow-test-cards: false
~~~

Các key ở external profile config override giá trị thấp hơn; các key không xuất hiện vẫn giữ default.

Với list, map và một số cấu trúc phức tạp, profile-specific config có thể thay thế toàn bộ list từ document thấp hơn thay vì append như developer kỳ vọng. Nếu cấu hình có list như CORS origins, allowed hosts hoặc custom routes, hãy kiểm tra behavior binding thực tế và viết test cho kết quả cuối.

## 19. Validation để phát hiện cấu hình sai ngay khi startup

Một ứng dụng không nên khởi động với database URL rỗng hoặc partner endpoint sai định dạng nếu đó là dependency bắt buộc.

~~~java
@ConfigurationProperties(prefix = "app.partner")
@Validated
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout
) {
    public PartnerProperties {
        if (timeout != null && timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.partner.timeout must not be negative"
            );
        }
    }
}
~~~

Có thể dùng Jakarta Bean Validation annotations khi có validation provider phù hợp. Một số constraint như `@NotNull` cần dependency validation tương ứng.

Trong production config:

~~~yaml
app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
    timeout: 2s
~~~

Nếu `PARTNER_BASE_URL` không được cấp, placeholder có thể không resolve và startup thất bại. Đây là tín hiệu hữu ích hơn việc dùng URL rỗng hoặc URL localhost trong production.

Default phù hợp có thể là timeout an toàn, logging level mặc định, feature không nguy hiểm mặc định tắt hoặc port mặc định cho local run. Không nên đặt default cho production password, production database endpoint, private key hoặc tenant ID nhạy cảm.

## 20. Không để dev config lọt vào production

Một lỗi thường gặp là file `application-dev.yml` được đặt trong JAR, rồi production vô tình chạy với profile `dev`. Hậu quả có thể gồm kết nối database local/sandbox, DEBUG logging quá chi tiết, bật test-only feature, tắt security hoặc dùng mock implementation.

Kiểm soát profile tại deployment boundary:

- Deployment dev khai báo profile `dev`.
- Deployment prod khai báo profile `prod`.
- Production startup script/manifest đặt profile tường minh.
- Production config dùng endpoint/secret bắt buộc.
- Startup validation kiểm tra invariant quan trọng.
- CI có test xác nhận production configuration không bật test-only features.

Không dựa vào default profile mơ hồ nếu ứng dụng có behavior khác biệt quan trọng giữa môi trường. Việc ẩn file profile trong JAR cũng không thay thế kiểm tra cấu hình runtime.

## 21. Dùng config file ngoài JAR trên Linux và Windows

Linux layout:

~~~text
/opt/orders/
├── current/
│   └── orders-service.jar
├── config/
│   ├── application.yml
│   └── application-prod.yml
└── logs/
~~~

Chạy:

~~~bash
cd /opt/orders
java -jar current/orders-service.jar \
  --spring.profiles.active=prod
~~~

Spring tìm `./config/` theo working directory `/opt/orders`. File JAR ở `/opt/orders/current` không quyết định relative config location.

Dùng absolute location khi service manager có working directory riêng:

~~~bash
java -jar /opt/orders/current/orders-service.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/opt/orders/config/
~~~

Windows layout:

~~~text
C:\apps\orders\
├── orders-service.jar
└── config\
    ├── application.yml
    └── application-prod.yml
~~~

PowerShell:

~~~powershell
Set-Location C:\apps\orders
$env:SPRING_PROFILES_ACTIVE = 'prod'
java -jar .\orders-service.jar
~~~

Nếu muốn trỏ tới thư mục khác, có thể dùng `--spring.config.additional-location=file:./external-config/`. Đảm bảo process có quyền đọc config directory và secret mount. Với URI trên Windows, cần chú ý cú pháp file URI và dấu slash; kiểm tra path trên hệ điều hành mục tiêu.

`$env:NAME = 'value'` đặt environment variable cho session PowerShell và các process con được khởi chạy từ session đó. Nó không tự ghi cấu hình vĩnh viễn cho mọi lần khởi động máy. Với Windows Service, cần cấu hình environment trong service manager hoặc wrapper tương ứng.

## 22. Script khởi động và systemd

Một script giúp chuẩn hóa lệnh, nhưng không nên chứa secret tĩnh.

Ví dụ Linux `start-dev.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/orders-dev"
JAR="$APP_DIR/orders-service.jar"

cd "$APP_DIR"

if [ -z "$DB_PASSWORD" ]; then
  echo "DB_PASSWORD is required" >&2
  exit 1
fi

exec java -jar "$JAR" \
  --spring.profiles.active=dev
~~~

Production script có thể kiểm tra các biến bắt buộc tương tự:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/orders-prod"
JAR="$APP_DIR/orders-service.jar"

cd "$APP_DIR"

if [ -z "$DB_URL" ] || [ -z "$DB_USERNAME" ] ||
   [ -z "$DB_PASSWORD" ] || [ -z "$PARTNER_BASE_URL" ]; then
  echo "Required production configuration is missing" >&2
  exit 1
fi

exec java -jar "$JAR" \
  --spring.profiles.active=prod
~~~

Production thường dùng systemd, container orchestrator hoặc service manager để restart theo policy, đặt working directory, cấp environment/secrets, giới hạn CPU/memory, thu thập stdout/stderr và quản lý shutdown timeout.

Một unit file systemd minh họa:

~~~ini
[Unit]
Description=Orders Service
After=network.target

[Service]
User=orders
Group=orders
WorkingDirectory=/opt/orders
Environment=SPRING_PROFILES_ACTIVE=prod
EnvironmentFile=/etc/orders/orders.env
ExecStart=/usr/bin/java -jar /opt/orders/current/orders-service.jar
Restart=on-failure
RestartSec=5
SuccessExitStatus=143
TimeoutStopSec=40

[Install]
WantedBy=multi-user.target
~~~

File `/etc/orders/orders.env` có thể chứa environment variables được cấp và bảo vệ theo chính sách máy chủ. Không đưa file đó vào source control hoặc cho user không phù hợp quyền đọc.

Vì đường dẫn tương đối phụ thuộc working directory, khai báo `WorkingDirectory` rõ ràng giúp Spring tìm đúng `./config`. Nếu không, service manager có thể chạy process từ thư mục khác và ứng dụng dùng nhầm hoặc thiếu cấu hình.

## 23. Cấp secret bằng file thay vì environment variables

Một số nền tảng mount secret thành file:

~~~text
/run/secrets/
├── db-password
└── partner-api-token
~~~

Có thể dùng Config Tree support của Spring Boot:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Các file trong thư mục có thể được ánh xạ thành property theo tên tương ứng. Cần xác nhận cú pháp, mount path và behavior của Boot version đang dùng.

Chỉ user chạy ứng dụng nên được đọc secret cần thiết. Không đặt quyền world-readable, không copy secret vào thư mục release/artifact, không in nội dung file trong log và có quy trình rotate secret. Việc secret file thay đổi không có nghĩa mọi bean đang giữ credential sẽ tự cập nhật; cần hiểu lifecycle/refresh behavior của ứng dụng.

## 24. Cấu hình database, partner API và logging

Ví dụ dev database:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: `DOLLAR`{DB_PASSWORD}
    hikari:
      maximum-pool-size: 5
~~~

Production database:

~~~yaml
spring:
  datasource:
    url: `DOLLAR`{DB_URL}
    username: `DOLLAR`{DB_USERNAME}
    password: `DOLLAR`{DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
~~~

Các giá trị pool size là minh họa. Production phải tính theo giới hạn connection của database, số instance và concurrency của ứng dụng. Khi chuyển môi trường, còn cần kiểm tra JDBC driver, TLS/SSL, database permissions, schema/migration version, network/firewall/DNS, transaction isolation và timezone.

Partner endpoint:

~~~yaml
app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
    timeout: 2s
~~~

Timeout cần được lựa chọn dựa trên SLA và behavior của client. Nếu dùng retry, tổng deadline gồm số lần retry, backoff và timeout từng request không được vượt quá request budget mà hệ thống cho phép.

Logging dev:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
~~~

Logging production:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

DEBUG log có thể tăng volume, lộ dữ liệu request hoặc thông tin nội bộ. Chỉ bật tạm thời theo quy trình vận hành và đảm bảo dữ liệu nhạy cảm đã được redacted. Khi chạy trong container hoặc service manager, stdout/stderr thường được thu thập bởi nền tảng. Nếu log vào file, cần quản lý rotation, permissions, disk usage và retention.

## 25. Đổi port và management endpoint

External config có thể đặt port:

~~~yaml
server:
  port: 8081
~~~

Hoặc environment variable `SERVER_PORT=8081`.

Nếu dùng Actuator, cấu hình management port/path cần được xem xét riêng:

~~~yaml
management:
  server:
    port: 8082
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Management port khác server port khi được cấu hình riêng. Không expose mọi actuator endpoint ra public network chỉ để tiện kiểm tra. Nếu readiness/liveness probes được dùng, xác nhận chúng gọi đúng endpoint/port và có authorization/network policy phù hợp.

## 26. Kiểm tra cấu hình hiệu lực mà không làm lộ secret

Khi hai môi trường chạy sai behavior, cần biết property nào đang được áp dụng. Không nên dump toàn bộ Environment vì có thể lộ credential.

Có thể log một số giá trị không nhạy cảm:

~~~java
@Component
public class RuntimeConfigurationLogger {

    private static final Logger log =
            LoggerFactory.getLogger(RuntimeConfigurationLogger.class);

    public RuntimeConfigurationLogger(
            Environment environment,
            PartnerProperties properties
    ) {
        log.info(
                "Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles())
        );
        log.info(
                "Partner timeout: {}",
                properties.timeout()
        );
    }
}
~~~

Không log database password, authorization token, private key, full secret-bearing URI hoặc toàn bộ property source.

Actuator có endpoint `env` để inspect environment/property sources khi được cấu hình và expose. Đây là endpoint nhạy cảm, cần kiểm soát access và sanitization. Không expose công khai chỉ để debug cấu hình. Trong nhiều trường hợp, log một vài property an toàn hoặc dùng debugger là đủ.

## 27. Kiểm tra JAR và checksum

Có thể liệt kê resource trong JAR:

~~~bash
jar tf orders-service.jar
~~~

Tìm:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-dev.yml
BOOT-INF/classes/application-prod.yml
~~~

Nếu dự án cố ý đóng gói profile config, kiểm tra chúng không chứa secret và production không vô tình chọn dev profile. Một lựa chọn khác là chỉ đóng gói default config và giữ environment-specific files hoàn toàn bên ngoài JAR.

Sau khi build, tính checksum:

Linux/macOS:

~~~bash
sha256sum target/orders-service-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\orders-service-1.0.0.jar -Algorithm SHA256
~~~

Ghi lại checksum trong build artifact metadata hoặc release record. Sau khi copy/tải xuống server, tính lại checksum và so sánh. Nếu checksum khác, file trên server không phải byte-for-byte artifact đã build.

Một version label như `1.0.0` giúp con người nhận biết release, còn checksum/digest giúp xác nhận chính xác nội dung. Trong artifact repository, nên dùng version immutable hoặc digest theo chính sách release.

## 28. Kiểm tra hai môi trường có thực sự chạy cùng code

Một quy trình release có thể:

1. CI build JAR từ commit SHA.
2. CI chạy tests.
3. CI tính checksum và publish artifact.
4. Dev deployment tải artifact theo version/digest.
5. Smoke test dev.
6. Production deployment promote đúng artifact đã test.
7. Ghi nhận checksum và runtime configuration version.

Không rebuild ở bước production nếu mục tiêu là promote cùng artifact. Chỉ thay config/secret và deployment parameters.

JAR được promote nguyên vẹn, nhưng external config có thể khác theo môi trường và có version/review process riêng. Cần lưu dấu cấu hình nào đã được dùng cho mỗi release để có thể điều tra và rollback.

## 29. Kiểm thử cấu hình dev và production

Nên có test cho những invariant quan trọng của từng profile.

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class DevConfigurationTests {

    @Autowired
    PartnerProperties properties;

    @Test
    void usesDevPartnerEndpoint() {
        assertThat(properties.baseUrl().getHost())
                .isEqualTo("partner-dev.example.test");
    }
}
~~~

Test này giả định dev profile được nạp trong test classpath. Nó không tự chứng minh external config ở deployment host được tìm thấy.

Có thể tạo test configuration validation để xác nhận production endpoint, database URL, test-only flags, timeout/pool settings và logging level. Không dùng production password thật trong test; dùng placeholder/synthetic value và kiểm tra format/required constraints.

Một số test framework cho phép cấp system properties hoặc dynamic properties trong test. Đặt giá trị test tường minh thay vì phụ thuộc environment của máy developer để test reproducible trên CI.

## 30. Smoke test JAR với external config

Sau khi deploy vào một thư mục test:

~~~bash
cd deploy/dev
java -jar orders-service.jar \
  --spring.profiles.active=dev
~~~

Kiểm tra process có khởi động thành công, profile đúng, database connection, partner endpoint, server port, health endpoint, logging và graceful shutdown.

Nếu ứng dụng có endpoint health và Actuator được cấu hình:

~~~bash
curl http://localhost:8080/actuator/health
~~~

Không phải ứng dụng nào cũng expose endpoint này. Cần bật dependency và exposure phù hợp trước khi dùng.

Một request health thành công chỉ xác nhận một phần trạng thái. Nó không chứng minh toàn bộ nghiệp vụ, database migration, authorization, performance hoặc resilience đều đúng.

### Graceful shutdown

Khi chạy bằng terminal hoặc service manager, process Java nhận tín hiệu dừng từ môi trường. Spring Boot có thể đóng ApplicationContext và thực hiện lifecycle callbacks.

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Thời gian chờ cần phù hợp với process manager/orchestrator timeout. Dùng `exec java -jar ...` khi chạy qua shell script để process Java thay thế shell process và signal được chuyển tiếp theo cách đơn giản hơn.

## 31. Troubleshooting: Spring không đọc file external

Triệu chứng: sửa `config/application.yml` nhưng ứng dụng vẫn dùng giá trị trong JAR.

Kiểm tra theo thứ tự:

1. Working directory của process là gì?
2. File có nằm đúng `./config/application.yml` so với working directory không?
3. File có đúng tên và extension được hỗ trợ không?
4. YAML có syntax/indentation hợp lệ không?
5. User chạy ứng dụng có quyền đọc file không?
6. Có dùng `spring.config.location` thay thế default locations không?
7. Có profile-specific file nhưng profile chưa active không?
8. Một nguồn precedence cao hơn có đang override property không?
9. Config import/location có bị đánh dấu optional và bỏ qua không?
10. Log startup có chỉ ra Config Data loading failure không?

Có thể thử location tường minh:

~~~bash
java -jar orders-service.jar \
  --spring.config.additional-location=file:./config/
~~~

Nếu vẫn không đọc, dùng absolute file URI theo OS và kiểm tra lại working directory.

## 32. Troubleshooting: sai profile hoặc placeholder

Nếu ứng dụng chạy bằng config dev khi triển khai production, kiểm tra `SPRING_PROFILES_ACTIVE`, command line `--spring.profiles.active`, system property, deployment manifest/service unit, default profile và tên file `application-prod.yml`.

Command line có thể override environment variable. Một script local có thể truyền `--spring.profiles.active=dev` dù production service đã đặt `SPRING_PROFILES_ACTIVE=prod`. Kiểm tra **lệnh thực tế** mà process manager chạy.

Nếu gặp:

~~~text
Could not resolve placeholder 'DB_PASSWORD'
~~~

nguyên nhân thường gặp là environment variable chưa được cấp cho process, tên biến sai, service manager không inherit shell environment, secret file chưa mount hoặc config import bị thiếu.

Có thể kiểm tra sự tồn tại mà không in giá trị secret:

PowerShell:

~~~powershell
[bool]$env:DB_PASSWORD
~~~

Linux/macOS:

~~~bash
test -n "$DB_PASSWORD" && echo "DB_PASSWORD is set"
~~~

Không paste password vào ticket hoặc log.

## 33. Troubleshooting: property bị override hoặc JAR chạy khác IDE

Nếu external config đặt port 8081 nhưng app chạy port 8083, có thể một nguồn cao hơn đặt `SERVER_PORT` hoặc `--server.port=8083`. Kiểm tra command line, environment variables, JVM system properties, service unit, profile-specific config và external config import/location.

IDE có thể dùng working directory, environment variables, active profile, classpath/resource path, JDK hoặc VM options khác. Khi chạy JAR, kiểm tra đúng JDK/runtime, executable Boot JAR, external config location, environment variables, runtime dependencies, filesystem permissions, port và network access.

Đừng kết luận Spring Boot chạy sai khi đóng gói trước khi so sánh hai môi trường thực thi.

## 34. Troubleshooting: build thành công nhưng test không chạy

Đây là vấn đề build/test tooling chứ không phải external config. Khi build JAR để phát hành, vẫn phải kiểm tra test đã được discover và thực thi:

~~~bash
mvn clean verify
~~~

hoặc:

~~~bash
./gradlew clean test bootJar
~~~

Không dùng `-DskipTests` hoặc `-x test` trong release build trừ khi pipeline có một bước test được thực hiện riêng và có bằng chứng tương ứng.

So sánh test reports và số lượng tests. Build success với zero tests không chứng minh ứng dụng đã được kiểm thử.

## 35. Checklist thực hành hoàn chỉnh

### Trước khi build

- [ ] Chọn version Spring Boot và Java phù hợp.
- [ ] Kiểm tra Maven/Gradle wrapper.
- [ ] Đảm bảo Boot plugin tạo executable JAR.
- [ ] Xác định default config nào được đóng gói.
- [ ] Xác định property nào phải đến từ external config.
- [ ] Xác định secret nào phải đến từ secret manager/environment.
- [ ] Có test cho configuration properties và validation.

### Khi build artifact

- [ ] Chạy clean build và tests.
- [ ] Tạo đúng executable JAR.
- [ ] Kiểm tra artifact path/name.
- [ ] Kiểm tra JAR contents nếu cần.
- [ ] Tính checksum/digest.
- [ ] Publish artifact theo version immutable.

### Khi triển khai dev

- [ ] Copy/tải đúng JAR digest.
- [ ] Đặt external config vào location dự kiến.
- [ ] Cấp DB_PASSWORD và những dev secrets cần thiết.
- [ ] Chọn profile `dev` tường minh.
- [ ] Kiểm tra working directory.
- [ ] Khởi động và xác nhận health/log/database/partner.

### Khi triển khai production

- [ ] Promote đúng artifact đã kiểm thử.
- [ ] Không rebuild JAR theo production profile.
- [ ] Đặt external config production.
- [ ] Cấp secrets qua cơ chế được bảo vệ.
- [ ] Chọn profile `prod` tường minh.
- [ ] Kiểm tra endpoint không trỏ dev/sandbox.
- [ ] Kiểm tra pool size, timeout và resource limits.
- [ ] Xác nhận health/readiness và graceful shutdown.
- [ ] Ghi lại artifact digest và config release/version.

### Sau triển khai

- [ ] Xác nhận process chạy đúng version.
- [ ] Kiểm tra log không chứa secret.
- [ ] Kiểm tra database/partner connections.
- [ ] Kiểm tra health và các use cases quan trọng.
- [ ] Theo dõi lỗi startup, latency và resource usage.
- [ ] Giữ artifact/config version trước đó để rollback có kiểm soát.

## 36. Bài tập thực hành

### Bài 1: Tạo một executable JAR

Tạo ứng dụng Spring Boot đơn giản có endpoint:

~~~java
@RestController
public class EnvironmentController {

    private final Environment environment;

    public EnvironmentController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/environment")
    public Map<String, Object> environment() {
        return Map.of(
                "application", environment.getProperty(
                        "spring.application.name"
                ),
                "activeProfiles", Arrays.asList(
                        environment.getActiveProfiles()
                )
        );
    }
}
~~~

Build bằng Maven hoặc Gradle và chạy bằng `java -jar`.

### Bài 2: Thêm cấu hình mặc định

Trong `application.yml`, đặt tên ứng dụng và port mặc định. Xác nhận endpoint trả đúng tên.

### Bài 3: Tạo external dev config

Tạo `config/application-dev.yml` và đặt một property như `app.environment-name: development`. Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Xác nhận property được bind đúng.

### Bài 4: Tạo external prod config

Tạo `config/application-prod.yml` với `app.environment-name: production`. Chạy cùng JAR nhưng chọn profile `prod`.

### Bài 5: Override bằng environment variable

Đặt `APP_ENVIRONMENT_NAME=staging`. Xác nhận giá trị từ environment variable có precedence cao hơn file config trong setup thông thường.

### Bài 6: Override bằng command line

~~~bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --app.environment-name=command-line
~~~

Xác nhận giá trị command line thắng các nguồn thấp hơn.

### Bài 7: Kiểm tra additional-location

Đặt config ở `./external-config/` và chạy với:

~~~bash
--spring.config.additional-location=file:./external-config/
~~~

Xác nhận Spring nạp được file external.

### Bài 8: Cố ý làm thiếu một biến bắt buộc

Xóa `DB_PASSWORD` khỏi environment và khởi động. Quan sát lỗi placeholder/binding. Cấp lại secret test rồi xác nhận context khởi động.

### Bài 9: Chứng minh cùng artifact

Tính SHA-256 của JAR trong thư mục dev và prod. Hai checksum phải giống nhau nếu đó là cùng một artifact byte-for-byte.

### Bài 10: Kiểm tra rollback

Giữ release JAR trước đó và external config version tương ứng. Thử khôi phục artifact/config trong môi trường test, xác nhận ứng dụng khởi động lại được.

## Kết luận

Đóng gói executable JAR rồi chạy bằng cấu hình ngoài ở hai môi trường là một cách triển khai Spring Boot rõ ràng và dễ kiểm soát. Maven hoặc Gradle tạo một JAR; Spring Boot đọc default configuration trong classpath rồi kết hợp external Config Data, profile-specific files, environment variables, system properties và command-line arguments theo precedence của chúng.

Với dev và production, có thể đặt cùng JAR vào hai deployment directories, mỗi nơi có external `config/` và profile tương ứng. Chạy `--spring.profiles.active=dev` hoặc `prod` để chọn cấu hình, cấp secret qua cơ chế bảo mật của môi trường và xác nhận process đang đọc đúng working directory. Nếu config nằm ngoài default search path, dùng `spring.config.additional-location` để bổ sung location; chỉ dùng `spring.config.location` khi chủ động muốn thay thế tập location mặc định.

Điểm cần giữ xuyên suốt là **artifact và runtime configuration có vòng đời riêng**: build/test JAR một lần, promote đúng artifact qua các môi trường, quản lý config/secret theo môi trường, rồi smoke test behavior thực tế. Cách làm này giúp tránh build drift, dễ truy vết release và cho phép thay đổi endpoint, database, logging hoặc timeout mà không phải biên dịch lại ứng dụng.
