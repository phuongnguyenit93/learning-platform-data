# Đọc bí mật và cấu hình Spring từ Secret Manager

Một ứng dụng Spring Boot thường cần kết nối cơ sở dữ liệu, gọi API bên thứ ba hoặc xác thực với hệ thống khác. Địa chỉ dịch vụ, port và timeout có thể đặt trong cấu hình thông thường; nhưng mật khẩu, API token, OAuth client secret và private key cần được bảo vệ. Nếu một giá trị bí mật xuất hiện trong application.yml, Dockerfile, source Java hoặc lịch sử Git, những người có quyền đọc repository hay artifact có thể lấy được nó.

Google Cloud **Secret Manager** cung cấp nơi lưu trữ phiên bản bí mật với quyền truy cập được kiểm soát bằng IAM. **Spring Framework on Google Cloud** (trước đây thường được gọi là Spring Cloud GCP) cung cấp tích hợp để ứng dụng Spring Boot tham chiếu secret như một thuộc tính cấu hình. Ngoài ra, ứng dụng có thể sử dụng Java client library hoặc tích hợp secret của nền tảng chạy. Bài học này giải thích cách chọn phương án, cấu hình đúng phiên bản thư viện và xoay vòng secret mà không đưa payload vào source code.

Bài học thuộc module **CLOUD_PROVIDERS_GCP**, trong chương **Java và Spring trên GCP**. Module khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; thông qua các tình huống triển khai, người học lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở đây, chúng ta áp dụng các nguyên tắc đó vào Spring Boot và Secret Manager.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân loại cấu hình thông thường và dữ liệu bí mật trong ứng dụng Spring.
- Giải thích mối quan hệ giữa Secret Manager, IAM, Application Default Credentials (ADC) và Spring Environment.
- Tạo secret, thêm version và cấp quyền đọc ở cấp secret cho runtime service account.
- Cấu hình starter Spring Cloud GCP Secret Manager và đọc secret bằng cú pháp phù hợp với phiên bản.
- Liên kết secret với Spring datasource, @Value và @ConfigurationProperties.
- Phân biệt đọc secret khi khởi động, đọc chủ động bằng Java SDK và tích hợp secret của Cloud Run/GKE.
- Xử lý lỗi, xoay vòng secret, kiểm thử và tránh lộ secret qua log hoặc Actuator.

## 1. Phân biệt cấu hình và bí mật

Spring Boot có thể đọc cấu hình từ application.properties, application.yml, biến môi trường, command-line arguments và các nguồn khác. Các nguồn này rất hữu ích nhưng không phải mọi nguồn đều có cơ chế bảo vệ phù hợp với thông tin xác thực.

| Thuộc tính | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| Tên ứng dụng | orders-api | Spring config |
| Region hoặc project ID | asia-southeast1, example-project | Spring config hoặc biến môi trường |
| Timeout, concurrency | 3 giây, 50 request | Spring config |
| Địa chỉ JDBC không có mật khẩu | jdbc:postgresql://db.internal:5432/orders | Spring config |
| Database username | orders_app | Spring config hoặc secret tùy chính sách |
| Database password | Giá trị dùng để đăng nhập | Secret Manager |
| API token hoặc client secret | Thông tin xác thực với đối tác | Secret Manager |
| Private key | Khóa riêng để ký hoặc xác thực | Dịch vụ quản lý khóa hoặc secret phù hợp |
| Khóa mã hóa dài hạn cần thao tác mật mã | Khóa bảo vệ dữ liệu | Cloud KMS |

Secret Manager thích hợp cho dữ liệu ứng dụng **phải lấy lại ở dạng rõ** để kết nối hoặc gọi dịch vụ. Cloud KMS chủ yếu quản lý khóa mật mã và thực hiện thao tác mật mã; không nên coi Cloud KMS là một kho mật khẩu thay thế Secret Manager.

### Cấu hình không an toàn

Ví dụ dưới đây minh họa lỗi thường gặp:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: super-secret-value-in-git
payments:
  api-token: static-token-in-source-control
~~~

Đổi tên file thành application-prod.yml hoặc thêm nó vào .gitignore sau khi commit không loại bỏ các bản sao đã lưu trong lịch sử Git. Mã hóa Base64 cũng không bảo vệ được secret. Nếu một credential thực tế đã bị commit, cần xoay vòng hoặc thu hồi nó tại hệ thống đích.

## 2. Luồng Spring Boot đọc secret trên Google Cloud

Khi dùng Spring Cloud GCP Secret Manager starter, Spring khởi tạo property source, nhận diện các tham chiếu secret và dùng ADC để gọi Secret Manager API. Cloud IAM quyết định runtime identity có quyền đọc phiên bản secret hay không.

~~~mermaid
flowchart LR
    A["Spring Boot config<br/>application.yml"]
    B["Spring Cloud GCP<br/>Secret Manager integration"]
    C["Application Default<br/>Credentials"]
    D["IAM: secretAccessor<br/>trên secret cần đọc"]
    E["Secret Manager API"]
    F["Phiên bản secret"]
    G["Spring Environment<br/>DataSource / Bean"]
    A --> B
    B --> C
    C --> D
    B --> E
    D --> E
    E --> F
    F --> G
~~~

Các thành phần có trách nhiệm khác nhau:

1. **Tên secret và version** là tham chiếu cấu hình. Chúng không phải payload bí mật.
2. **Danh tính workload** là service account hoặc danh tính liên kết được cung cấp cho ứng dụng khi chạy.
3. **IAM** xác thực quyền đọc payload. Quyền nên được cấp trên đúng secret, không mở rộng tùy tiện ra toàn project.
4. **Secret Manager** lưu payload theo các phiên bản có thể được bật, vô hiệu hóa hoặc hủy.
5. **Spring Environment** cung cấp giá trị đã giải quyết cho thuộc tính như spring.datasource.password hoặc payments.api-token.

Ứng dụng chỉ cần quyền đọc secret. Tạo version, thay đổi policy hoặc xóa secret là hoạt động quản trị riêng, không thuộc trách nhiệm runtime của hầu hết ứng dụng.

## 3. Chuẩn bị project và Secret Manager

Ví dụ dùng một ứng dụng Spring Boot tên orders-api có kết nối PostgreSQL. Thay project ID, địa chỉ và service account bằng giá trị được cấp trong môi trường thử nghiệm.

### Bước 1: Chọn project và bật API

~~~bash
export PROJECT_ID="example-project"
export SECRET_ID="orders-db-password"
export RUNTIME_SA="orders-runtime@example-project.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable secretmanager.googleapis.com \
  --project="$PROJECT_ID"
~~~

Quyền để bật API, tạo secret hoặc thay đổi IAM thường thuộc nhóm quản trị project; không cấp các quyền quản trị đó cho ứng dụng chỉ cần đọc secret.

### Bước 2: Tạo secret

~~~bash
gcloud secrets create "$SECRET_ID" \
  --replication-policy=automatic \
  --project="$PROJECT_ID"
~~~

Chế độ automatic replication là một lựa chọn phổ biến. Nếu tổ chức yêu cầu ràng buộc vị trí lưu dữ liệu, hãy thiết kế replication/location theo chính sách và khả năng hỗ trợ của Secret Manager trước khi tạo tài nguyên. Ví dụ sau sử dụng secret kiểu toàn cục để tập trung vào tích hợp Spring.

### Bước 3: Thêm phiên bản

~~~bash
gcloud secrets versions add "$SECRET_ID" \
  --data-file="/secure/path/orders-db-password.txt" \
  --project="$PROJECT_ID"
~~~

Tệp đầu vào chứa mật khẩu thử nghiệm, được tạo qua quy trình bảo mật của nhóm. Tránh đưa secret trực tiếp vào command line, lưu trong thư mục repository hoặc in ra log. Đảm bảo quyền đọc của tệp và xóa bản sao tạm theo chính sách sau khi hoàn tất.

Secret Manager không tự tạo hoặc thay đổi mật khẩu tại database. Mật khẩu trong secret phải khớp thông tin xác thực thực tế của tài khoản database. Khi xoay vòng, cần điều phối cả hai phía.

### Bước 4: Cấp quyền đọc tối thiểu

~~~bash
gcloud secrets add-iam-policy-binding "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
~~~

Vai trò roles/secretmanager.secretAccessor cho phép đọc secret payload. Cấp ở cấp secret hạn chế phạm vi hơn so với cấp ở cấp project. Nếu ứng dụng dùng ba secret, có thể cấp quyền trên đúng ba secret, thay vì cho ứng dụng đọc tất cả secret trong project.

Khi chạy trên Cloud Run, gắn service account này làm runtime service account của service. Khi chạy trên GKE, dùng Workload Identity Federation for GKE và cấu hình quyền truy cập cho principal phù hợp. Khi chạy trên Compute Engine, gắn service account của workload vào VM và kiểm tra các cơ chế kiểm soát truy cập liên quan.

## 4. Phiên bản Spring Cloud GCP quyết định cú pháp

**Điểm quan trọng:** cú pháp Secret Manager property source đã thay đổi theo dòng phiên bản Spring Framework on Google Cloud. Các hướng dẫn cũ trên mạng thường dùng sm://, còn tài liệu cho dòng mới khuyến nghị sm@.

| Dòng tích hợp | Cách bật Config Data | Tham chiếu secret | Ghi chú |
|---|---|---|---|
| Spring Cloud GCP 4.x hoặc 5.x | spring.config.import=sm:// | ${sm://orders-db-password} | Cú pháp được tài liệu của các dòng này hướng dẫn |
| Spring Framework on Google Cloud 6.x trở lên | spring.config.import=sm@ | ${sm@orders-db-password} | Cú pháp mới được giới thiệu từ 6.0.0; dòng 7.x khuyến nghị |
| Spring Cloud Config Server với Secret Manager backend | Cơ chế cấu hình riêng | Theo backend của Config Server | Không đồng nhất với Secret Manager starter tích hợp trực tiếp |

Các ví dụ chính dưới đây dùng **sm@** theo tài liệu Spring Framework on Google Cloud 7.x. Nếu dự án dùng dòng cũ, hãy đổi phần import và placeholder theo tài liệu đúng phiên bản. Không trộn cú pháp hai dòng trong cùng ví dụ. Trước khi nâng Spring Boot hoặc Spring Cloud, kiểm tra ma trận tương thích và release notes, đặc biệt khi chuyển major version.

### Các cách chỉ định secret ở cú pháp mới

| Cú pháp | Ý nghĩa |
|---|---|
| sm@orders-db-password | Secret trong project mặc định, version mới nhất |
| sm@orders-db-password/5 | Secret trong project mặc định, version 5 |
| sm@example-project/orders-db-password/5 | Chỉ định project, secret và version |
| sm@projects/example-project/secrets/orders-db-password/versions/5 | Tên tài nguyên đầy đủ |
| sm@projects/example-project/secrets/orders-db-password | Tên tài nguyên không chỉ định version, dùng phiên bản mới nhất |

Spring Framework on Google Cloud phiên bản mới cũng hỗ trợ tham chiếu **regional secrets** bằng đường dẫn có locations/LOCATION_ID. Với dòng thư viện cũ, kiểm tra khả năng hỗ trợ regional secret trước khi áp dụng. Nếu cần khóa chặt phiên bản, dùng version cụ thể thay vì latest; latest phù hợp cho luồng xoay vòng có cơ chế làm mới cấu hình đã được thiết kế.

## 5. Thêm starter vào ứng dụng Maven

Dự án Spring Boot phải chọn phiên bản Spring Framework on Google Cloud tương thích với phiên bản Spring Boot đang sử dụng. Với Maven, nên nhập BOM của Spring Framework on Google Cloud trong dependencyManagement rồi khai báo starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
</dependency>
~~~

Đoạn dependency trên giả định dự án đã nhập BOM tương ứng, vì vậy không lặp phiên bản ở từng starter. Nếu chưa có BOM, thêm spring-cloud-gcp-dependencies với phiên bản đã chọn và kiểm tra compatibility matrix của Spring Boot/Spring Cloud. Tránh sao chép một version từ hướng dẫn cũ rồi dùng chung với Spring Boot mới.

Nếu ứng dụng dùng JDBC và PostgreSQL, cần có những dependency phù hợp khác như Spring Boot JDBC starter và PostgreSQL JDBC driver. Secret Manager starter chỉ cung cấp nguồn cấu hình; nó không tự tạo database, không cấp network access và không thay thế JDBC driver.

## 6. Đưa mật khẩu datasource vào Spring config

Trong application.yml, khai báo tên secret thay vì giá trị password:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "sm@"
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${sm@orders-db-password}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
~~~

Ở dòng mới, import sm@ bật Spring Boot Config Data API cho Secret Manager. Khi Spring giải quyết thuộc tính spring.datasource.password, starter gọi Secret Manager để lấy payload của secret orders-db-password theo project mặc định và version mới nhất. Spring Boot JDBC auto-configuration có thể dùng password này để khởi tạo DataSource.

Các biến DB_JDBC_URL và DB_USERNAME được cung cấp từ môi trường hoặc nguồn cấu hình khác. Nếu username là thông tin nhạy cảm theo chính sách tổ chức, cũng có thể lưu nó trong Secret Manager.

Để tham chiếu một phiên bản cụ thể:

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@orders-db-password/5}"
~~~

Nếu muốn truy cập secret ở project khác, dùng tên tài nguyên đầy đủ:

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@projects/central-secrets/secrets/orders-db-password/versions/5}"
~~~

Runtime service account vẫn phải có quyền đọc secret trong project đích. Việc truyền project ID trong chuỗi tham chiếu không tự cấp quyền.

### application.properties tương đương

~~~properties
spring.application.name=orders-api
spring.config.import=sm@
spring.datasource.url=${DB_JDBC_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${sm@orders-db-password}
~~~

Không đặt payload bí mật trong YAML, properties hoặc placeholder mặc định như secret-value. Với secret bắt buộc, hãy để ứng dụng thất bại khi secret không tồn tại hoặc bị từ chối, thay vì âm thầm dùng mật khẩu hard-code.

## 7. Inject secret qua @Value và @ConfigurationProperties

Spring có thể truy cập một secret trực tiếp bằng @Value hoặc ánh xạ secret vào một thuộc tính cấu hình có tên rõ ràng.

### Dùng @Value cho cấu hình đơn lẻ

Ví dụ tham chiếu API token của đối tác:

~~~yaml
spring:
  config:
    import: "sm@"
payments:
  endpoint: "https://payments.example.invalid/api"
  api-token: "${sm@payments-api-token}"
~~~

Trong Java:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PaymentCredentialProvider {
    private final String apiToken;

    public PaymentCredentialProvider(
            @Value("${payments.api-token}") String apiToken) {
        this.apiToken = apiToken;
    }

    public String tokenForOutboundRequest() {
        return apiToken;
    }
}
~~~

Lớp này chỉ là ví dụ về injection. Trong production, dùng token bên trong HTTP client khi tạo Authorization header, và không log giá trị trả về hoặc đưa nó vào response API. Không tạo endpoint công khai để hiển thị secret.

Có thể tham chiếu trực tiếp:

~~~java
@Value("${sm@payments-api-token}")
private String paymentApiToken;
~~~

Tuy nhiên, ánh xạ qua thuộc tính nghiệp vụ payments.api-token thường dễ review hơn, vì phần lớn code không cần biết secret lưu trong dịch vụ nào.

### Dùng @ConfigurationProperties cho cấu hình có cấu trúc

Khi một client cần nhiều thuộc tính, @ConfigurationProperties thường rõ ràng hơn việc dùng nhiều @Value rời rạc.

~~~yaml
spring:
  config:
    import: "sm@"
payments:
  endpoint: "https://payments.example.invalid/api"
  timeout: 3s
  api-token: "${sm@payments-api-token}"
~~~

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentSettings(
        URI endpoint,
        Duration timeout,
        String apiToken) {
}
~~~

Đăng ký bean cấu hình:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(PaymentSettings.class)
public class PaymentSettingsConfiguration {
}
~~~

Khi Spring bind thuộc tính payments.api-token, placeholder được giải quyết từ Secret Manager. Bean nhận token dưới dạng String giống những thuộc tính Spring khác.

**Chú ý:** record trong Java tự sinh toString() có chứa các field. Không log toàn bộ PaymentSettings, không đưa bean này vào thông báo lỗi hoặc response, và cấu hình Actuator để không hiển thị giá trị nhạy cảm. Nếu cần bảo vệ trước việc vô tình gọi toString(), có thể dùng class tùy chỉnh và phương thức toString() chỉ in các thuộc tính không nhạy cảm.

## 8. Profiles và cấu hình theo môi trường

Ứng dụng thường chạy trên local, staging và production. Một thiết kế đơn giản là lưu cấu hình chung trong application.yml, còn tham chiếu Secret Manager của từng môi trường trong file profile tương ứng.

**application.yml** chỉ chứa phần chung:

~~~yaml
spring:
  application:
    name: orders-api
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
~~~

**application-staging.yml:**

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@orders-db-password-staging}"
~~~

**application-prod.yml:**

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@projects/prod-secrets/secrets/orders-db-password/versions/7}"
~~~

**application-local.yml** có thể dùng một biến môi trường riêng khi chạy thử:

~~~yaml
spring:
  datasource:
    password: "${LOCAL_DB_PASSWORD}"
~~~

Khi profile prod được bật, file application-prod.yml được tải và Spring gọi Secret Manager. Khi chạy kiểm thử unit với profile test hoặc local không có import sm@, bạn có thể dùng credential thử nghiệm riêng mà không cần gọi Google Cloud API.

Không để test profile vô tình tải import sm@ từ cấu hình chung nếu mục tiêu là test offline. Chỉ bật nguồn Secret Manager ở profile và môi trường thực sự cần nó; cùng một artifact có thể dùng nhiều profile mà không đóng gói secret bên trong.

### Project mặc định

Starter có thể xác định project từ cấu hình chung hoặc ADC. Nếu muốn chỉ định project cho Secret Manager, dùng thuộc tính:

~~~properties
spring.cloud.gcp.secretmanager.project-id=example-project
~~~

Khi cần truy cập project khác, tên tài nguyên đầy đủ giúp nhìn rõ đích. Hãy kiểm tra project lúc khởi động để tránh trường hợp ứng dụng chạy được nhưng lấy nhầm secret từ môi trường khác.

## 9. Xác thực bằng Application Default Credentials

**Application Default Credentials (ADC)** là cơ chế để thư viện Google Cloud tìm thông tin xác thực từ môi trường mà ứng dụng đang chạy. Ứng dụng không cần viết riêng logic chọn tài khoản khi chuyển từ laptop lên Cloud Run hoặc GKE.

Trong môi trường local, có thể tạo ADC cho tài khoản phát triển:

~~~bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT_ID"
~~~

Lệnh thứ hai đặt quota project cho ADC nếu cần và tài khoản có quyền tương ứng. **gcloud auth login** phục vụ Google Cloud CLI; nó không đồng nghĩa với việc đã có ADC cho Java client libraries. Vì vậy, hãy dùng đúng lệnh application-default khi thử nghiệm trực tiếp từ máy phát triển.

Chạy ứng dụng với profile phù hợp:

~~~bash
export DB_JDBC_URL="jdbc:postgresql://127.0.0.1:5432/orders"
export DB_USERNAME="orders_app"

./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=staging
~~~

Ví dụ yêu cầu database hoặc tunnel kết nối đã được thiết lập, tài khoản ADC có quyền đọc secret của staging, và cấu hình project chính xác. Nếu không có kết nối database, Spring vẫn có thể đọc secret nhưng bước khởi tạo DataSource hoặc health check có thể thất bại vì lỗi mạng; cần phân biệt hai nguyên nhân này khi điều tra.

Không tải khóa JSON của service account về laptop chỉ để chạy thử. Khóa JSON là credential dài hạn có thể bị sao chép hoặc commit. Với môi trường tự động hóa chạy ngoài Google Cloud, cân nhắc Workload Identity Federation thay vì khóa tĩnh.

### Phân biệt danh tính ở các môi trường

| Môi trường | ADC thường đến từ đâu? | Điều cần kiểm soát |
|---|---|---|
| Máy phát triển | gcloud auth application-default login | Quyền người dùng đối với secret phát triển |
| Cloud Run | Runtime service account của service | IAM ở đúng secret |
| Compute Engine | Service account gắn vào VM | IAM và cấu hình VM/Google API access liên quan |
| GKE | Workload Identity Federation for GKE | Danh tính Kubernetes workload, IAM, namespace và network |
| CI/CD bên ngoài | Workload Identity Federation | Trust giữa external identity provider và Google Cloud |

Một ứng dụng có thể chạy ở nhiều nơi với cùng mã Java, nhưng project và secret tham chiếu phải được chọn rõ ràng theo môi trường. Không giả định danh tính mặc định luôn có quyền đọc tất cả secret.

## 10. Triển khai Spring Boot trên Cloud Run

Cloud Run cung cấp runtime identity cho container và có thể cho ứng dụng gọi Secret Manager API. Nếu ứng dụng đã dùng starter với import sm@, chỉ cần service account đúng quyền, project đúng và network có thể truy cập API.

### Gắn runtime service account

Ví dụ cập nhật danh tính service:

~~~bash
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project="$PROJECT_ID" \
  --service-account="$RUNTIME_SA"
~~~

Lệnh này thay đổi cấu hình Cloud Run service; ví dụ chỉ để minh họa quy trình, không phải bước bắt buộc khi service đã dùng đúng danh tính. Người thực hiện deploy cần quyền cập nhật service và quyền sử dụng service account được chỉ định. Runtime identity sau khi gắn chỉ cần quyền đọc secret của ứng dụng.

### Hai cách đưa secret vào Spring trên Cloud Run

**Cách A — Spring starter đọc trực tiếp từ Secret Manager.** Giữ cấu hình:

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@orders-db-password/7}"
~~~

Cloud Run chỉ cần cấp danh tính và các biến cấu hình không nhạy cảm. Starter gọi Secret Manager khi giải quyết placeholder.

**Cách B — Cloud Run cung cấp secret qua biến môi trường.** Cloud Run tích hợp Secret Manager và có thể ánh xạ một secret version sang biến môi trường, ví dụ SPRING_DATASOURCE_PASSWORD:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/example-project/app-images/orders-api:release-7" \
  --region=asia-southeast1 \
  --project="$PROJECT_ID" \
  --service-account="$RUNTIME_SA" \
  --set-secrets="SPRING_DATASOURCE_PASSWORD=orders-db-password:7"
~~~

Spring Boot có thể đọc SPRING_DATASOURCE_PASSWORD như thuộc tính spring.datasource.password qua quy tắc relaxed binding. Với cách này, ứng dụng không nhất thiết cần starter Secret Manager, vì nền tảng đã cung cấp giá trị cho tiến trình. Không cần đặt thêm placeholder sm@ cho cùng thuộc tính.

Hai cách đều cần runtime identity có quyền đọc secret. Cách A thống nhất truy cập qua Spring property source và dễ tái sử dụng trên nhiều môi trường; cách B đơn giản cho một ứng dụng chỉ chạy trên Cloud Run. Chọn theo kiến trúc và khả năng vận hành, rồi dùng nhất quán để tránh khó xác định nguồn cấu hình thực sự.

Cloud Run cũng hỗ trợ cung cấp secret qua mounted volume. Cách dùng file và cách dùng biến môi trường có hành vi cập nhật khác nhau. Secret truyền qua biến môi trường được lấy tại lúc instance khởi động; instance đang chạy không tự cập nhật giá trị chỉ vì có secret version mới. Hãy thiết kế việc triển khai revision/khởi động lại để bảo đảm mọi instance dùng đúng credential sau xoay vòng.

### Kiểm tra sau deploy

Sau khi cập nhật service:

1. Xác nhận revision mới có trạng thái Ready.
2. Kiểm tra endpoint health và một thao tác database bằng tài khoản thử nghiệm.
3. Theo dõi error rate, latency, instance restart và log khởi tạo.
4. Xác minh rằng log không chứa password hoặc token.
5. Xác minh runtime service account không thể đọc secret nằm ngoài phạm vi được cấp.

Không tạo endpoint debug trả về Environment, DataSource configuration hoặc một bean chứa secret. Bất cứ cách phát hiện lỗi nào cũng phải tránh in payload thật.

## 11. Spring Boot trên GKE và Workload Identity

Trên GKE, một Pod chạy ứng dụng Spring Boot và thường dùng Kubernetes ServiceAccount (KSA). Nếu ứng dụng gọi Secret Manager API trực tiếp, Workload Identity Federation for GKE là lựa chọn ưu tiên để workload có danh tính Google Cloud được kiểm soát mà không cần chứa tệp khóa JSON.

Ví dụ manifest cho Kubernetes ServiceAccount:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: production
~~~

Pod cần tham chiếu service account tương ứng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/example-project/app-images/orders-api:release-7
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
~~~

Manifest minh họa việc gắn KSA cho Pod, chưa phải quy trình Workload Identity hoàn chỉnh. Cần cấu hình workload identity pool/principal và IAM binding đúng theo chế độ GKE Standard hoặc Autopilot đang dùng, bảo đảm principal đại diện cho namespace và KSA có quyền roles/secretmanager.secretAccessor trên secret cần thiết. Với một số mô hình, có thể liên kết KSA với một IAM service account; chọn cách được hỗ trợ theo hướng dẫn hiện hành.

Khi workload có quyền và đường mạng đến Secret Manager API, starter sử dụng ADC trong Pod để truy cập secret. Nếu tổ chức dùng Secret Manager add-on hoặc CSI driver để mount secret thành file, ứng dụng có thể đọc từ file/configtree theo cách tương ứng. Đó là một kiến trúc khác với việc starter gọi API trực tiếp; cần xem xét quyền, cách đồng bộ phiên bản và lịch refresh riêng.

Đối với GKE private cluster, ngoài IAM còn phải kiểm tra egress hoặc cơ chế kết nối đến các Google APIs. Một Pod có quyền IAM đúng nhưng không thể kết nối đến endpoint Secret Manager vẫn không đọc được secret.

## 12. Khi cần đọc secret bằng Java SDK

Spring starter phù hợp với secret được giải quyết như cấu hình trong quá trình khởi tạo ứng dụng. Có trường hợp ứng dụng cần chủ động đọc một phiên bản ở một thời điểm nhất định, ví dụ sau một sự kiện xoay vòng hoặc một tác vụ nền. Khi đó có thể dùng Google Cloud Secret Manager Java client library.

Thêm dependency thông qua hệ thống quản lý phiên bản tương thích với các thư viện Google Cloud:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-secretmanager</artifactId>
</dependency>
~~~

Đăng ký client do Spring quản lý:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SecretManagerClientConfig {

    @Bean(destroyMethod = "close")
    SecretManagerServiceClient secretManagerClient()
            throws IOException {
        // Sử dụng Application Default Credentials.
        return SecretManagerServiceClient.create();
    }
}
~~~

Tạo service đọc một phiên bản cụ thể:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;
import org.springframework.stereotype.Service;

@Service
public class RuntimeSecretService {
    private final SecretManagerServiceClient client;

    public RuntimeSecretService(
            SecretManagerServiceClient client) {
        this.client = client;
    }

    public String read(
            String projectId,
            String secretId,
            String versionId) {
        SecretVersionName name = SecretVersionName.of(
                projectId, secretId, versionId);

        return client.accessSecretVersion(name)
                .getPayload()
                .getData()
                .toStringUtf8();
    }
}
~~~

Ví dụ chỉ minh họa việc đọc payload. Service gọi API phải được thiết kế để không log giá trị trả về, không truyền secret vào exception message, không đưa secret vào response và xử lý lỗi theo yêu cầu nghiệp vụ. Một giá trị được trả về dưới dạng String nằm trong bộ nhớ JVM; không thể bảo đảm xóa tức thì tất cả bản sao khỏi bộ nhớ.

Nên tái sử dụng client và chỉ đọc khi cần. Không gọi Secret Manager cho mọi request HTTP hoặc mỗi lần lấy connection database. Đọc quá thường xuyên tăng độ trễ, số lần gọi API và có thể chạm quota; dùng cache hoặc một quy trình refresh có kiểm soát nếu kiến trúc yêu cầu.

### So sánh ba cách tích hợp

| Cách | Phù hợp khi | Hạn chế cần lưu ý |
|---|---|---|
| Spring Cloud GCP property source | Secret là thuộc tính cấu hình lúc ứng dụng khởi động | Thay đổi secret không đồng nghĩa bean đang chạy tự nhận giá trị mới |
| Java Secret Manager SDK | Cần đọc version chủ động hoặc theo sự kiện | Phải quản lý client, cache, retry và truyền giá trị vào component |
| Secret integration của runtime | Chạy trên Cloud Run/GKE và muốn platform cung cấp secret | Hành vi env/file và cơ chế refresh phụ thuộc nền tảng |

Không phải ứng dụng nào cũng cần cài cả starter và SDK trực tiếp. Chọn cách ít phức tạp nhất đáp ứng nhu cầu phiên bản, refresh, độ trễ và quyền truy cập.

## 13. Xoay vòng phiên bản secret

Secret Manager quản lý nhiều version của cùng một secret. Tuy nhiên, thay đổi secret ở Secret Manager **không tự thay đổi credential trong database hoặc dịch vụ bên thứ ba**, và không bảo đảm các đối tượng Spring đã được tạo sẽ tự nhận giá trị mới.

### latest và version cụ thể

- **latest:** thuận tiện khi muốn instance mới đọc phiên bản mới nhất đang được bật. Những instance đã khởi động và lưu giá trị trong bean hoặc connection pool thường tiếp tục dùng giá trị đã đọc.
- **Version cụ thể:** giúp một bản phát hành có cấu hình tái lập. Nhóm có thể chủ động nâng từ version 7 sang 8 và triển khai revision mới để mọi instance dùng cùng phiên bản.

Với PostgreSQL password, nếu đổi password tại database trước khi các instance chuyển sang secret mới, các instance cũ có thể mất quyền kết nối khi pool tạo connection mới. Nếu database không hỗ trợ hai credential đồng thời cho cùng tài khoản, có thể tạo credential hoặc database user mới trong giai đoạn chuyển đổi, hoặc thiết kế một khoảng dừng phù hợp.

### Quy trình xoay vòng đề xuất

1. Tạo credential mới tại hệ thống đích theo cách cho phép chạy song song với credential cũ nếu có thể.
2. Thêm version mới trong Secret Manager mà không sửa source code.
3. Thử đọc version mới bằng danh tính được cấp quyền trong môi trường kiểm thử.
4. Cập nhật tham chiếu version hoặc triển khai revision mới để ứng dụng khởi động với credential mới.
5. Xác nhận kết nối, health checks và luồng nghiệp vụ thực tế hoạt động.
6. Chuyển hết traffic sang phiên bản ứng dụng mới hoặc restart các instance còn giữ credential cũ.
7. Thu hồi credential cũ tại hệ thống đích và vô hiệu hóa hoặc hủy secret version cũ theo chính sách.
8. Theo dõi log, metric và audit events để phát hiện workload nào còn sử dụng credential cũ.

Không xóa version cũ trước khi đã xác minh rollout và khả năng phục hồi. Rollback ứng dụng có thể cần version cũ trong một khoảng thời gian, nhưng việc giữ credential cũ quá lâu cũng tăng rủi ro. Hãy xác định rõ thời hạn và điều kiện thu hồi.

### Có tự động refresh được không?

Một số dòng Spring Cloud GCP hỗ trợ cơ chế refresh kết hợp Spring Cloud Context và @RefreshScope. Tuy nhiên, việc gọi refresh chỉ có tác dụng với bean và kiểu cấu hình được hỗ trợ; nó không mặc nhiên tái tạo DataSource, connection pool hoặc các connection đã mở. Không xây quy trình xoay vòng dựa trên giả định mọi bean sẽ cập nhật tức thì.

Phương án dễ kiểm soát với Cloud Run hoặc GKE là phát hành revision/rollout mới với version chỉ định, chạy smoke test và chuyển traffic sau khi xác minh. Với hệ thống bắt buộc cập nhật nóng, hãy thiết kế rõ cơ chế tải lại secret, thay client/pool, đóng kết nối cũ và kiểm thử trong môi trường gần production.

## 14. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy secret | Sai project, secret ID hoặc version | Xác nhận tên tài nguyên, project và version tồn tại |
| PERMISSION_DENIED | Runtime identity thiếu quyền đọc secret | Kiểm tra service account và IAM binding ở đúng secret |
| NOT_FOUND | Secret/version không tồn tại hoặc đã bị xóa | Kiểm tra resource path và vòng đời version |
| FAILED_PRECONDITION | Version bị vô hiệu hóa hoặc trạng thái không cho phép truy cập | Kiểm tra trạng thái secret version |
| UNAVAILABLE hoặc timeout | Vấn đề kết nối, Google API hoặc sự cố tạm thời | Kiểm tra network, DNS, egress và retry có giới hạn |
| RESOURCE_EXHAUSTED | Quota bị vượt hoặc quá nhiều request | Giảm tần suất đọc, dùng cache và kiểm tra quota |
| Placeholder vẫn còn nguyên | Sai syntax cho dòng thư viện hoặc import chưa được bật | Kiểm tra BOM, starter và spring.config.import |
| Ứng dụng chạy local nhưng lỗi trên Cloud Run | Runtime service account hoặc project khác local | So sánh ADC local và service identity trên Cloud Run |
| Ứng dụng chạy nhưng database trả 401/28P01 | Secret không khớp credential tại database | Kiểm tra quy trình xoay vòng và đúng database user |
| Thêm version nhưng app vẫn dùng giá trị cũ | Bean hoặc pool chỉ tải secret khi khởi động | Thiết kế rollout/restart hoặc refresh có kiểm soát |

Không xử lý lỗi bằng cách in toàn bộ Spring Environment hoặc giá trị mật khẩu để so sánh. Hãy log mã lỗi, tên secret, project, version và correlation ID khi phù hợp; tránh đưa payload vào log, trace, metric label và exception message.

### Kiểm tra chính xác phiên bản thư viện

Nếu import sm@ không được nhận diện, trước hết hãy kiểm tra phiên bản Spring Framework on Google Cloud. Dòng 4.x/5.x sử dụng sm://; cú pháp sm@ được giới thiệu ở 6.0.0. Ngoài ra, hãy xác nhận starter có mặt trong dependency tree và tương thích với Spring Boot đang dùng. Không sao chép một thuộc tính từ hướng dẫn dành cho major version khác rồi kết luận Secret Manager API bị lỗi.

Nếu dùng Config Server backend của Spring Cloud Config, quy trình cấu hình và mapping ứng dụng/profile khác với starter đọc trực tiếp qua Config Data API. Hãy phân biệt hai kiến trúc trước khi chọn cấu hình.

## 15. Bảo mật dữ liệu trong Spring và pipeline

Secret Manager giảm rủi ro lộ secret trong Git, nhưng ứng dụng vẫn nhận payload dưới dạng rõ khi cần dùng. Vì vậy, bảo mật còn phụ thuộc cách dữ liệu di chuyển trong bộ nhớ, log, network và công cụ chẩn đoán.

Các nguyên tắc quan trọng:

- Không viết token, password hoặc private key trong Java source, Dockerfile, application.yml hoặc build substitutions.
- Không đưa secret vào URL/query string, exception message, metrics, traces hoặc structured log.
- Không truyền secret vào system property/command-line argument nếu nó có thể bị ghi lại trong log hoặc danh sách tiến trình.
- Dùng IAM tối thiểu và service account riêng theo workload/môi trường.
- Không chia sẻ secret production cho pull request build hoặc môi trường thử nghiệm.
- Tránh dùng credential JSON dài hạn; ưu tiên ADC và Workload Identity Federation.
- Bảo vệ Spring Actuator, đặc biệt các endpoint env, configprops, heapdump hoặc những endpoint có thể tiết lộ dữ liệu cấu hình.
- Không log toàn bộ bean @ConfigurationProperties chứa token; record toString() có thể chứa trường nhạy cảm.
- Kiểm tra audit logs và cấu hình logging phù hợp để có thể điều tra truy cập bất thường.
- Xoay vòng ngay credential đã bị lộ, kể cả khi commit chứa credential đã được xóa.

Với Spring Boot Actuator, nên hạn chế endpoint được expose và giữ chính sách không hiển thị giá trị nhạy cảm:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Đây là ví dụ giảm bề mặt lộ cấu hình. Quyền truy cập endpoint vẫn cần được bảo vệ bằng network và Spring Security hoặc phương án tương đương; không xem việc ẩn giá trị là thay thế cho authentication.

Trong pipeline CI/CD, build service account thường chỉ cần tạo artifact và deploy. Nó không nên được cấp quyền đọc secret runtime nếu build không có nhu cầu đó. Runtime service account cần quyền đọc secret nhưng không cần quyền chỉnh sửa pipeline hoặc push image.

## 16. Kiểm thử khi ứng dụng phụ thuộc Secret Manager

Chia kiểm thử thành nhiều mức:

| Mức kiểm thử | Cách làm | Mục tiêu |
|---|---|---|
| Unit test | Mock client hoặc cung cấp thuộc tính test | Kiểm tra logic nghiệp vụ không cần mạng |
| Spring context test | Bật profile test không import Secret Manager | Kiểm tra binding cấu hình và khởi tạo bean |
| Integration test | Dùng secret riêng của môi trường test, principal có quyền tối thiểu | Kiểm tra API và đường kết nối thực |
| Deployment smoke test | Chạy với runtime service account thực tế | Xác nhận revision/Pod đọc được secret được cấp |
| Rotation test | Thêm version thử nghiệm và rollout lại | Xác minh quy trình chuyển credential an toàn |
| Failure test | Thu hồi quyền ở môi trường thử nghiệm hoặc chỉ định version sai | Xác minh ứng dụng fail rõ ràng, không fallback secret tĩnh |

Ví dụ application-test.yml không nhập Secret Manager:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders_test
    username: sa
    password: ""
~~~

Ví dụ này giả định dự án đã thêm H2 dependency cho test hoặc dùng một datasource giả phù hợp. Không để test profile import sm@ ở tệp cấu hình chung nếu mục đích là test offline. Nếu dự án bắt buộc kiểm tra cấu hình production, hãy có integration test tách biệt với quyền và secret dành riêng cho thử nghiệm.

### Kiểm tra thiếu quyền

Trong môi trường thử nghiệm, có thể thu hồi quyền secretAccessor của principal test hoặc thử truy cập một secret không thuộc phạm vi được cấp. Xác nhận ứng dụng không thể đọc secret và lỗi thể hiện đúng nhóm nguyên nhân mà không tiết lộ payload.

Không thực hiện thao tác thu hồi quyền trực tiếp trên secret production đang được dùng bởi workload thật để “thử nhanh” mà không có kế hoạch và phạm vi kiểm thử phù hợp.

## 17. Quan sát và tối ưu chi phí

Truy cập Secret Manager tạo request đến API. Nếu ứng dụng đọc secret liên tục trong mỗi HTTP request, hệ thống có thể tăng độ trễ, quota usage và chi phí. Phần lớn mật khẩu và token được nạp khi khởi động hoặc khi làm mới theo sự kiện là đủ.

Nên theo dõi:

- Tỷ lệ lỗi khởi động ứng dụng do không đọc được secret.
- Số lần đọc secret bất thường sau deploy hoặc rotation.
- Latency của thao tác đọc secret khi được instrumentation.
- Thay đổi IAM và hoạt động truy cập secret theo Cloud Audit Logs được cấu hình.
- Trạng thái version và mốc thu hồi credential cũ.
- Mức sử dụng Secret Manager so với quota, ngân sách và chính sách lưu giữ.

Đừng đặt secret payload hoặc ID người dùng có cardinality cao vào metric labels. Dùng resource name hoặc mã lỗi không nhạy cảm để điều tra. Với ứng dụng có nhiều replica, thay version thường nên kết hợp rollout theo đợt và theo dõi lỗi kết nối thay vì để tất cả replica làm mới cùng lúc không kiểm soát.

## 18. Bài tập thực hành: Spring Boot đọc password và API token

Giả sử service **orders-api** kết nối PostgreSQL và gọi một đối tác thanh toán. Trước đây application-prod.yml chứa database password và API token. Bạn cần chuyển hai secret vào Secret Manager và xác nhận ứng dụng đọc chúng bằng runtime identity.

Thực hiện trong project Google Cloud thử nghiệm:

1. Tạo hai secret orders-db-password và payments-api-token, thêm version chứa credential **thử nghiệm**.
2. Tạo runtime service account cho orders-api và cấp roles/secretmanager.secretAccessor trên đúng hai secret.
3. Kiểm tra major version Spring Framework on Google Cloud được dùng, chọn sm@ hoặc sm:// phù hợp.
4. Thêm spring-cloud-gcp-starter-secretmanager và BOM tương thích vào pom.xml.
5. Trong application-staging.yml, khai báo spring.config.import và tham chiếu password bằng placeholder Secret Manager.
6. Định nghĩa payments.api-token và inject vào PaymentCredentialProvider hoặc PaymentSettings.
7. Dùng ADC với principal test để chạy ứng dụng ở local hoặc staging. Xác minh database connection và HTTP client hoạt động.
8. Triển khai Cloud Run với runtime service account đã cấp quyền. Kiểm tra revision Ready và smoke test.
9. Thử thay version của payments-api-token, xác minh việc khởi động lại revision đọc đúng version mới.
10. Kiểm tra log, Actuator exposure và build artifact để xác nhận không chứa payload.
11. Thu hồi quyền đọc một secret trong môi trường test và xác nhận ứng dụng báo lỗi rõ ràng, không fallback sang giá trị hard-code.
12. Khôi phục quyền test, hoàn tất kế hoạch xoay vòng và kiểm tra credential cũ đã được thu hồi đúng thời điểm.

### Tiêu chí hoàn thành

- Source code và các tệp cấu hình được commit không chứa password/token.
- Spring Boot đọc secret bằng đúng cú pháp tương ứng với phiên bản thư viện.
- Runtime service account có quyền đọc đúng secret cần thiết.
- Test không đòi hỏi dùng secret production.
- Ứng dụng không trả payload qua API, log hoặc Actuator.
- Quy trình đổi version có bước kiểm tra và thu hồi credential cũ.

## 19. Checklist trước khi đưa vào production

- [ ] Đã phân loại secret và cấu hình thông thường.
- [ ] Tên secret, project và version được xác định rõ theo môi trường.
- [ ] Secret Manager API và replication được cấu hình đúng chính sách.
- [ ] Từng runtime identity chỉ có quyền secretAccessor cần thiết.
- [ ] Không lưu service account JSON key trong repository hoặc image.
- [ ] Starter và Spring Boot tương thích; sm@ hoặc sm:// đúng major version.
- [ ] Spring config chỉ chứa tham chiếu secret, không chứa payload.
- [ ] Lớp cấu hình hoặc bean chứa secret không được log hoặc serialize ra ngoài.
- [ ] Spring Actuator không lộ env/configprops/heapdump cho người không được phép.
- [ ] Mạng runtime truy cập được Secret Manager API khi dùng tích hợp trực tiếp.
- [ ] Cache hoặc cách làm mới được thiết kế, tránh đọc secret theo từng request.
- [ ] Lỗi thiếu quyền, sai version và API không sẵn sàng được xử lý rõ ràng.
- [ ] Có kế hoạch rotation bao gồm cả hệ thống đích và rollout ứng dụng.
- [ ] Có test cho startup, smoke test và trường hợp thiếu quyền.
- [ ] Có cách truy vết version đang dùng mà không in payload.
- [ ] Log, metrics, build và artifact đã được kiểm tra để tránh lộ secret.

## Câu hỏi tự kiểm tra

**1. Vì sao không nên lưu database password trong application.yml?**

Vì tệp cấu hình có thể được commit, sao chép vào image hoặc lưu trong artifact và log. Secret Manager cho phép lưu payload bên ngoài repository và kiểm soát quyền đọc bằng IAM.

**2. Spring Cloud GCP 4.x/5.x và dòng mới khác nhau ở cú pháp nào?**

Các dòng cũ dùng sm://; từ 6.0.0 xuất hiện cú pháp sm@, được dòng mới khuyến nghị. Cần xem phiên bản thư viện thực tế trước khi chọn import và placeholder.

**3. ADC cung cấp điều gì cho ứng dụng Spring Boot?**

ADC giúp client library tìm danh tính từ môi trường chạy. IAM của danh tính đó quyết định secret nào có thể truy cập, nên ứng dụng không cần nhúng khóa JSON vào mã nguồn.

**4. Cập nhật secret version có làm một DataSource đang chạy tự đổi password không?**

Không mặc định. DataSource hoặc connection pool có thể giữ giá trị đã tải khi khởi động. Cần cơ chế refresh có kiểm soát hoặc rollout/restart, đồng thời điều phối việc đổi credential ở database.

**5. Khi nào nên dùng Secret Manager Java SDK trực tiếp?**

Khi cần đọc secret chủ động theo một sự kiện hoặc version cụ thể, thay vì chỉ inject secret như một thuộc tính cấu hình lúc ứng dụng khởi động.

**6. Vì sao một Pod GKE có IAM đúng vẫn có thể không đọc được secret?**

Workload có thể chưa được cấu hình đúng Workload Identity Federation for GKE, hoặc không có đường mạng đến API. Cần kiểm tra identity, binding và kết nối.

**7. Nếu một password từng xuất hiện trong Git, chỉ xóa khỏi commit có đủ không?**

Không. Các bản clone, nhánh, artifact hoặc log vẫn có thể chứa giá trị cũ. Cần thu hồi hoặc xoay vòng password tại hệ thống đích.

## Tài liệu tham khảo

- [Spring Framework on Google Cloud 7.x – Secret Manager Config Data](https://googlecloudplatform.github.io/spring-cloud-gcp/7.0.0/reference/html/index.html)
- [Spring Framework on Google Cloud 5.x – Secret Manager](https://googlecloudplatform.github.io/spring-cloud-gcp/5.13.2/reference/html/index.html)
- [Google Codelab: Retrieving Credentials/Secrets from Secret Manager with Spring Boot](https://codelabs.developers.google.com/codelabs/cloud-spring-cloud-gcp-secret-manager)
- [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Google Cloud: Secret Manager overview](https://docs.cloud.google.com/secret-manager/docs/overview)
- [Google Cloud: Access control for Secret Manager](https://docs.cloud.google.com/secret-manager/docs/access-control)
- [Google Cloud: Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Google Cloud: Cloud Run configure secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Google Cloud: Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Google Cloud: Secret Manager audit logging](https://docs.cloud.google.com/secret-manager/docs/audit-logging)

## Kết luận

Đọc bí mật trong Spring Boot từ Secret Manager là một bài toán kết hợp cấu hình, danh tính và vòng đời credential. Secret Manager giữ payload và version; IAM giới hạn quyền đọc; ADC cung cấp danh tính phù hợp với môi trường; Spring Cloud GCP hoặc Java SDK đưa giá trị đến đúng thành phần ứng dụng. Cần chọn cú pháp sm@ hoặc sm:// theo major version của thư viện, tránh đóng gói secret trong source code và xây dựng quy trình rotation có kiểm tra trên cả ứng dụng lẫn hệ thống đích. Khi quản lý rõ project, version, quyền runtime, logging và cơ chế refresh, ứng dụng Java trên Google Cloud có thể giữ cấu hình linh hoạt mà vẫn bảo vệ thông tin xác thực.
