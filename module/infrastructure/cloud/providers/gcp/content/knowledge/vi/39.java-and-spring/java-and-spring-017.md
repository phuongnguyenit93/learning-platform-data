# Thực hành chuẩn hóa cấu hình Java qua nhiều môi trường GCP

Một dịch vụ Java/Spring Boot thường chạy qua nhiều môi trường: máy phát triển, development, staging và production. Mỗi môi trường có project Google Cloud, endpoint, Pub/Sub topic, cơ sở dữ liệu, mức giới hạn tài nguyên và chính sách bảo mật riêng. Nếu lập trình viên sửa trực tiếp Java code hoặc tạo một JAR khác cho từng môi trường, nhóm sẽ khó chứng minh production đang chạy đúng phiên bản đã kiểm thử, đồng thời tăng nguy cơ đưa nhầm tài nguyên hoặc bí mật vào bản phát hành.

**Chuẩn hóa cấu hình** nghĩa là giữ một bộ mã nguồn và một artifact, nhưng cung cấp các giá trị cấu hình phù hợp khi triển khai. Spring Boot hỗ trợ externalized configuration thông qua YAML/properties, environment variables, command-line arguments và các nguồn khác. Trên Google Cloud, có thể phối hợp với Cloud Run, Google Kubernetes Engine (GKE), Secret Manager, IAM, Artifact Registry và quy trình CI/CD để quản lý cấu hình có kiểm soát.

Bài thực hành xây dựng một dịch vụ checkout đơn giản, triển khai qua nhiều môi trường GCP theo hướng **build once, deploy many**, tách dữ liệu nhạy cảm khỏi cấu hình thường và kiểm tra tính đúng đắn ngay khi ứng dụng khởi động.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân loại cấu hình theo mức độ nhạy cảm và phạm vi môi trường.
- Thiết kế một bộ application.yml, profile-specific YAML và environment variables thống nhất.
- Dùng @ConfigurationProperties để bind cấu hình vào kiểu dữ liệu Java có validation.
- Áp dụng Application Default Credentials (ADC), IAM và Secret Manager để tránh lưu khóa tĩnh.
- Cấu hình Cloud Run hoặc GKE bằng các giá trị dành riêng cho dev/staging/prod.
- Build một container image và promote cùng digest qua nhiều môi trường.
- Kiểm tra cấu hình mà không làm lộ secret trong log.
- Lập quy trình review, rollback, phát hiện drift và vận hành cấu hình an toàn.

## 1. Vấn đề của cấu hình không thống nhất

Một số mẫu lỗi thường gặp:

- Mã nguồn dùng hằng số PROJECT_ID hoặc topic name của môi trường phát triển.
- Kết nối database production được ghi trong application-prod.yml và commit vào Git.
- Các môi trường dùng các phiên bản JAR khác nhau dù cùng một commit.
- Staging không có giới hạn concurrency giống production, khiến kiểm thử tải không đại diện.
- Thay đổi timeout trên Console mà không cập nhật repository hoặc pipeline triển khai.
- Môi trường dùng profile prod nhưng lại tham chiếu tài nguyên dev.
- Khi rollback ứng dụng, không ai biết configuration đã thay đổi vào thời điểm nào.

Một hệ thống cấu hình tốt cần bảo đảm:

1. Giá trị có tên và ý nghĩa rõ ràng.
2. Giá trị được kiểm soát trong phạm vi môi trường cụ thể.
3. Thông tin bí mật được bảo vệ bằng cơ chế riêng.
4. Ứng dụng báo lỗi sớm nếu thiếu cấu hình bắt buộc.
5. Có thể xác định phiên bản artifact và cấu hình đang chạy.
6. Cùng một artifact có thể triển khai ở nhiều môi trường mà không sửa mã nguồn.

## 2. Phân loại cấu hình trước khi viết code

Không phải mọi giá trị đều nên đặt trong cùng một YAML.

| Nhóm cấu hình | Ví dụ | Nơi quản lý nên dùng |
|---|---|---|
| Giá trị chung, không nhạy cảm | Tên service, timeout mặc định, feature behavior | application.yml hoặc code config |
| Giá trị theo môi trường | Project ID, topic ID, endpoint, concurrency | Environment variables hoặc deployment configuration |
| Bí mật | API key, password, certificate, token | Secret Manager và quyền IAM |
| Hạ tầng | CPU, memory, min/max instances, service account | IaC và cấu hình Cloud Run/GKE |
| Quyền truy cập | Pub/Sub Publisher, Secret Manager Accessor | IAM policy theo service account |
| Feature rollout | Bật tính năng cho nhóm nhỏ, canary | Feature flag service hoặc configuration có kiểm soát |

Cần phân biệt **configuration** với **secrets**. Một project ID thường không bí mật; password hoặc API token là bí mật. Không nên đưa secret vào Git, Dockerfile, build argument, môi trường CI dùng chung hoặc log chẩn đoán.

### Cấu hình là một phần của hợp đồng vận hành

Với mỗi trường, hãy mô tả:

- Tên và kiểu dữ liệu.
- Giá trị mặc định, nếu có.
- Có bắt buộc ở production hay không.
- Phạm vi môi trường.
- Ai được phép thay đổi.
- Rủi ro nếu đặt sai.
- Khi thay đổi có cần restart/redeploy hay không.

Ví dụ, CHECKOUT_TIMEOUT=2s là thời hạn gọi dependency, trong khi CHECKOUT_PROJECT_ID xác định project chứa Pub/Sub topic. Nếu đặt sai project, ứng dụng có thể gửi dữ liệu tới tài nguyên của môi trường khác. Trường này cần được kiểm tra nghiêm ngặt, dù bản thân giá trị không phải bí mật.

## 3. Kiến trúc cấu hình nhiều môi trường

Một cách tổ chức có thể là:

~~~text
Git repository
  |
  +-- src/main/resources/application.yml
  +-- src/main/resources/application-local.yml
  +-- src/main/resources/application-staging.yml
  +-- src/main/resources/application-prod.yml
  |
  +-- Source code Spring Boot
  |
  v
CI/CD: build + test + image digest
  |
  +--------> Dev Cloud Run / GKE
  |             + env dev + service account dev + secrets dev
  |
  +--------> Staging Cloud Run / GKE
  |             + env staging + service account staging + secrets staging
  |
  +--------> Production Cloud Run / GKE
                + env prod + service account prod + secrets prod
~~~

Trong mô hình này, image digest giữ nguyên giữa các môi trường. Những thay đổi thuộc về deployment: profile, environment variables, secret references, IAM và cấu hình hạ tầng.

**Không xem profile name là ranh giới bảo mật.** Bảo mật thực sự đến từ IAM, project isolation, network policy và quyền của service account. Profile chỉ là cách Spring chọn nhóm giá trị cấu hình.

## 4. Cấu trúc Spring Boot configuration

Ví dụ dự án checkout dùng Java 21 và Spring Boot 3.x. Một cấu trúc đơn giản:

~~~text
checkout-service/
  src/main/java/com/example/checkout/
    CheckoutApplication.java
    config/CheckoutProperties.java
    service/CheckoutService.java
  src/main/resources/
    application.yml
    application-local.yml
    application-staging.yml
    application-prod.yml
  pom.xml
  Dockerfile
~~~

### application.yml: cấu hình chung

~~~yaml
spring:
  application:
    name: checkout-service

checkout:
  project-id: "${CHECKOUT_PROJECT_ID}"
  topic-id: "${CHECKOUT_TOPIC_ID}"
  payment-api-base-url: "${PAYMENT_API_BASE_URL}"
  request-timeout: "${CHECKOUT_TIMEOUT:2s}"
  max-in-flight: "${CHECKOUT_MAX_IN_FLIGHT:16}"

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Các biến không có mặc định thể hiện cấu hình bắt buộc. Nếu chưa cung cấp CHECKOUT_PROJECT_ID, CHECKOUT_TOPIC_ID hoặc PAYMENT_API_BASE_URL, ứng dụng cần thất bại lúc khởi động thay vì vô tình dùng project hoặc endpoint sai.

Giá trị mặc định cho timeout và concurrency chỉ là điểm khởi đầu; môi trường production nên khai báo rõ các giá trị đã được kiểm tra.

### application-local.yml: chạy trên máy phát triển

~~~yaml
checkout:
  project-id: local-project
  topic-id: orders-local
  payment-api-base-url: http://localhost:8089
  request-timeout: 3s
  max-in-flight: 4

logging:
  level:
    com.example.checkout: DEBUG
~~~

Profile local có thể dùng stub hoặc emulator cho dependency phù hợp. Không trỏ local mặc định vào production. Nếu sử dụng Pub/Sub emulator, cần cấu hình endpoint và credentials của emulator theo client/framework đang dùng; không giả định chỉ đổi tên topic là đủ.

### application-staging.yml: môi trường tiền production

~~~yaml
checkout:
  request-timeout: 2s
  max-in-flight: 16

logging:
  level:
    root: INFO
~~~

Staging nên gần production về loại dependency và chính sách quan trọng. Các giá trị project ID, topic ID và endpoint tiếp tục được inject từ cấu hình triển khai.

### application-prod.yml: cấu hình production

~~~yaml
checkout:
  request-timeout: 1500ms
  max-in-flight: 32

logging:
  level:
    root: WARN
~~~

Production không nên có fallback ngầm sang dữ liệu dev. Tránh commit endpoint chứa credential hoặc private IP không phù hợp với quy định bảo mật của tổ chức.

### Kích hoạt profile

Trên máy phát triển:

~~~bash
export SPRING_PROFILES_ACTIVE=local
./mvnw spring-boot:run
~~~

Trên Cloud Run/GKE, set SPRING_PROFILES_ACTIVE thành staging hoặc prod ở cấu hình triển khai. Nếu không có profile phù hợp, Spring dùng cấu hình không gắn profile và default profile của framework; vì vậy các trường bắt buộc vẫn phải được validation.

## 5. Hiểu thứ tự ưu tiên của nguồn cấu hình

Spring Boot có nhiều nguồn property với thứ tự ưu tiên được xác định. Về nguyên tắc, giá trị được cung cấp ở nguồn ưu tiên cao hơn sẽ ghi đè giá trị thấp hơn.

Các nguồn thường gặp:

- application.yml được đóng gói cùng JAR.
- application-{profile}.yml theo profile đang active.
- File configuration đặt ngoài JAR.
- Environment variables.
- Java system properties.
- Command-line arguments.

Thứ tự đầy đủ còn phụ thuộc loại nguồn, vị trí file và cách khởi động. Khi có nghi vấn về override, hãy đối chiếu tài liệu externalized configuration của Spring Boot phiên bản đang dùng.

Ví dụ:

~~~yaml
# application.yml
checkout:
  max-in-flight: 16
~~~

Nếu deployment cung cấp environment variable CHECKOUT_MAX_IN_FLIGHT=40, Spring Boot relaxed binding có thể ánh xạ biến môi trường đó vào property checkout.max-in-flight.

Hãy dùng một quy ước nhất quán: property trong Java/YAML dùng kebab-case; tên biến môi trường dùng uppercase và underscore. Tránh tạo nhiều alias cho cùng một ý nghĩa.

### Tại sao không nên lạm dụng @Value?

@Value thích hợp với một vài giá trị nhỏ, nhưng khi service có hàng chục property, code dễ có nhiều chuỗi tên rải rác và thiếu validation tập trung.

@ConfigurationProperties giúp nhóm các property theo miền nghiệp vụ, có kiểu dữ liệu rõ ràng và kiểm tra ngay khi ứng dụng khởi động.

## 6. Bind cấu hình vào Java với @ConfigurationProperties

Ví dụ dùng Java record và Jakarta Bean Validation:

~~~java
package com.example.checkout.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @NotBlank String projectId,
        @NotBlank String topicId,
        @NotNull URI paymentApiBaseUrl,
        @NotNull Duration requestTimeout,
        @Min(1) int maxInFlight
) {}
~~~

Spring Boot hỗ trợ bind Duration từ các giá trị như 2s hoặc 1500ms. Để chạy validation, dự án cần dependency Spring Boot validation tương ứng (ví dụ spring-boot-starter-validation).

Kích hoạt quét configuration properties:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Sử dụng trong service:

~~~java
package com.example.checkout.service;

import com.example.checkout.config.CheckoutProperties;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final CheckoutProperties properties;

    public CheckoutService(CheckoutProperties properties) {
        this.properties = properties;
    }

    public String topicPath() {
        return "projects/" + properties.projectId()
                + "/topics/" + properties.topicId();
    }
}
~~~

Đối tượng properties là immutable record, phù hợp để inject và đọc từ nhiều thành phần. Nếu cần thay đổi runtime mà không restart, phải thiết kế cơ chế cập nhật cấu hình riêng; một record được bind lúc startup không tự refresh khi environment variable hoặc secret thay đổi.

### Validation chuyên biệt theo môi trường

Bean Validation kiểm tra được null, blank hoặc khoảng giá trị. Nhưng một project ID hợp lệ về cú pháp vẫn có thể là project sai.

Có thể thêm kiểm tra ở startup hoặc admission/deploy pipeline:

- Profile prod không được dùng topic kết thúc bằng -dev.
- Project production phải nằm trong danh sách cho phép.
- Endpoint thanh toán production phải dùng HTTPS.
- max-in-flight phải nằm dưới concurrency budget đã phê duyệt.
- Request timeout không được vượt HTTP request timeout của hệ thống.

Các quy tắc này nên có test và được kiểm tra trước khi nhận traffic. Không ghi toàn bộ giá trị cấu hình khi validation thất bại nếu chúng có thể chứa thông tin nhạy cảm.

## 7. Project, identity và credentials theo môi trường

Mỗi môi trường nên có service account hoặc workload identity riêng. Cùng một image Java có thể chạy trong project dev và prod, nhưng danh tính khi gọi GCP API được cấp theo runtime.

### Application Default Credentials

Google Cloud Java client libraries thường hỗ trợ ADC. Trên Cloud Run, service account được cấu hình cho dịch vụ; trên GKE, có thể dùng Workload Identity Federation for GKE. Trên máy phát triển, người dùng có thể cấu hình ADC theo quy trình đăng nhập được tổ chức cho phép.

Trong code:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;

try (SecretManagerServiceClient client =
         SecretManagerServiceClient.create()) {
    // Client sử dụng credential mặc định của môi trường.
}
~~~

Đây là ví dụ cho chương trình ngắn. Trong Spring Boot service dài hạn, hãy quản lý client như singleton bean và đóng khi application context dừng.

Không đưa service account JSON key vào image, source hoặc application-prod.yml. Nếu service cần truy cập nhiều project, hãy cấp IAM có phạm vi đúng cho runtime service account, không dùng một key toàn quyền cho mọi môi trường.

### Ma trận môi trường

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| Project ID | checkout-dev | checkout-staging | checkout-prod |
| Spring profile | dev | staging | prod |
| Runtime identity | checkout-dev SA | checkout-staging SA | checkout-prod SA |
| Pub/Sub topic | orders-dev | orders-staging | orders-prod |
| Secret Manager | Secret dev | Secret staging | Secret prod |
| Database | Instance dev | Instance staging | Instance prod |
| Logging | DEBUG có kiểm soát | INFO | INFO/WARN |
| Quyền IAM | Theo nhu cầu dev | Gần production | Least privilege nghiêm ngặt |

Các tên trong bảng chỉ là ví dụ. Project ID thực tế phải lấy từ tổ chức, không tự suy diễn từ profile string.

## 8. Secret Manager: quản lý dữ liệu bí mật

Secret Manager phù hợp để lưu API key, token, password hoặc certificate. Ứng dụng chỉ nên nhận quyền truy cập secret cần thiết.

Trên Cloud Run, secret có thể được đưa vào container theo hai cách:

- **Environment variable:** giá trị được resolve khi instance khởi động. Phù hợp với ứng dụng đọc cấu hình một lần; nên pin version cụ thể để việc triển khai dễ tái lập.
- **Mounted volume:** secret xuất hiện dưới dạng file. Khi đọc nội dung, Cloud Run lấy giá trị từ Secret Manager, hỗ trợ cơ chế cập nhật khi rotate theo cách cấu hình.

Ví dụ gắn version cố định vào environment variable khi deploy:

~~~bash
gcloud run deploy checkout \
  --image IMAGE_DIGEST \
  --project CHECKOUT_PROD_PROJECT \
  --region asia-southeast1 \
  --service-account checkout-runtime@CHECKOUT_PROD_PROJECT.iam.gserviceaccount.com \
  --update-secrets PAYMENT_API_KEY=payment-api-key:5
~~~

Trong ví dụ, IMAGE_DIGEST là tham chiếu image đầy đủ theo dạng registry/repository/image@sha256:digest. Secret payment-api-key đã được tạo trong project và runtime service account cần quyền Secret Manager Secret Accessor phù hợp.

### Không lưu secret trong environment file

File production.env.yaml nên chỉ chứa thông tin không nhạy cảm. Secret được khai báo riêng bằng secret reference hoặc cơ chế mount phù hợp. Tránh đưa secret vào output của terraform plan, CI logs, debug endpoint hoặc snapshot container.

Không mặc định bật actuator env/configprops cho người dùng bên ngoài. Nếu cần endpoint vận hành, phải có xác thực, quyền truy cập phù hợp và cơ chế masking dữ liệu nhạy cảm.

### Secret rotation

Khi dùng environment variable secret, instance đang chạy không tự thay giá trị chỉ vì secret có version mới. Cần kiểm soát rollout để instance mới nhận version đã chọn. Với volume, hành vi đọc phiên bản có thể linh hoạt hơn; ứng dụng phải quyết định khi nào reload nội dung.

Không coi việc dùng latest là chính sách rotation hoàn chỉnh. Cần thử nghiệm, version pinning khi thích hợp, phân phối rollout, rollback và thu hồi quyền/version cũ theo quy trình an toàn.

## 9. Thực hành triển khai Cloud Run qua nhiều môi trường

Mục tiêu là build một container image đã được kiểm thử rồi dùng cùng digest cho dev, staging và production.

### Bước 1: build image một lần

Ví dụ xây dựng image bằng Cloud Build:

~~~bash
gcloud builds submit \
  --tag asia-southeast1-docker.pkg.dev/BUILD_PROJECT/java-services/checkout:COMMIT_SHA \
  --project BUILD_PROJECT
~~~

Sau khi push, lấy digest chính xác từ Artifact Registry. Ghi nhận commit, build ID, digest và kết quả test/scan trước khi promotion.

### Bước 2: file environment variables của staging

Nội dung file staging.env.yaml ở deployment repository:

~~~yaml
SPRING_PROFILES_ACTIVE: staging
CHECKOUT_PROJECT_ID: checkout-staging
CHECKOUT_TOPIC_ID: orders-staging
PAYMENT_API_BASE_URL: https://payments-staging.example.com
CHECKOUT_TIMEOUT: 2s
CHECKOUT_MAX_IN_FLIGHT: "16"
~~~

File chứa cấu hình không bí mật nên có thể review trong Git. Endpoint minh họa phải được thay bằng endpoint thật. Không commit token hoặc password vào file này.

### Bước 3: triển khai staging

~~~bash
gcloud run deploy checkout \
  --image IMAGE_DIGEST \
  --project CHECKOUT_STAGING_PROJECT \
  --region asia-southeast1 \
  --service-account checkout-runtime@CHECKOUT_STAGING_PROJECT.iam.gserviceaccount.com \
  --env-vars-file staging.env.yaml \
  --update-secrets PAYMENT_API_KEY=payment-api-key:3
~~~

Yêu cầu runtime service account có IAM phù hợp với Pub/Sub, Secret Manager và dependency khác. Khi image nằm ở build project khác với project triển khai, identity dùng để pull image cần được cấp quyền Artifact Registry Reader phù hợp; điều này khác với quyền mà runtime service account dùng để gọi API.

### Bước 4: file environment variables của production

~~~yaml
SPRING_PROFILES_ACTIVE: prod
CHECKOUT_PROJECT_ID: checkout-prod
CHECKOUT_TOPIC_ID: orders-prod
PAYMENT_API_BASE_URL: https://payments.example.com
CHECKOUT_TIMEOUT: 1500ms
CHECKOUT_MAX_IN_FLIGHT: "32"
~~~

Production có biến cấu hình và secret riêng, nhưng dùng cùng image digest đã chạy qua staging.

### Bước 5: triển khai production có kiểm soát

~~~bash
gcloud run deploy checkout \
  --image IMAGE_DIGEST \
  --project CHECKOUT_PROD_PROJECT \
  --region asia-southeast1 \
  --service-account checkout-runtime@CHECKOUT_PROD_PROJECT.iam.gserviceaccount.com \
  --env-vars-file prod.env.yaml \
  --update-secrets PAYMENT_API_KEY=payment-api-key:5
~~~

Đây là ví dụ cú pháp; lệnh thật phải được review, thay placeholder, xác nhận dự án và tuân theo approval/canary policy của tổ chức. Cập nhật environment variables hoặc secret reference trên Cloud Run tạo revision mới. Hãy ghi nhận revision và so sánh cấu hình trước/sau để bảo đảm không làm mất biến cần thiết.

**Lưu ý:** gcloud --set-env-vars thay toàn bộ danh sách environment variables thuộc nhóm đó, trong khi --update-env-vars cập nhật các biến được chỉ định. Với --env-vars-file, cần review đầy đủ tập giá trị mà deployment sẽ áp dụng. Nên dùng manifest có version trong Git hoặc IaC làm nguồn sự thật.

## 10. Triển khai trên GKE bằng ConfigMap và workload identity

Trên GKE, các giá trị không nhạy cảm có thể được quản lý bằng ConfigMap; secret có thể được lấy qua Secret Manager theo cơ chế tích hợp phù hợp. Runtime identity nên dùng Workload Identity Federation for GKE thay vì đặt static key vào pod.

### ConfigMap ví dụ

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-config
  namespace: production
data:
  SPRING_PROFILES_ACTIVE: "prod"
  CHECKOUT_PROJECT_ID: "checkout-prod"
  CHECKOUT_TOPIC_ID: "orders-prod"
  PAYMENT_API_BASE_URL: "https://payments.example.com"
  CHECKOUT_TIMEOUT: "1500ms"
  CHECKOUT_MAX_IN_FLIGHT: "32"
~~~

### Deployment sử dụng ConfigMap

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: production
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      serviceAccountName: checkout
      containers:
        - name: checkout
          image: asia-southeast1-docker.pkg.dev/BUILD_PROJECT/java-services/checkout@sha256:IMAGE_DIGEST
          envFrom:
            - configMapRef:
                name: checkout-config
          ports:
            - containerPort: 8080
~~~

Ví dụ chưa bao gồm probes, resource requests/limits, secret mount hoặc cơ chế Workload Identity đã cấu hình. Trong production, cần bổ sung các thành phần này và xác định Kubernetes ServiceAccount có quyền GCP tối thiểu cần thiết.

Nếu ConfigMap được inject thành environment variables, pod đang chạy thường không tự nhận giá trị mới khi ConfigMap thay đổi. Cần rollout/restart pod để dùng cấu hình mới. Nếu ConfigMap được mount thành volume, file có thể được cập nhật theo cơ chế Kubernetes, nhưng Spring Boot không tự reload @ConfigurationProperties chỉ vì file đổi.

### Lưu ý khi dùng nhiều môi trường GKE

- Có namespace, cluster hoặc project isolation theo yêu cầu bảo mật.
- Giới hạn quyền RBAC của Kubernetes và IAM của GCP.
- Không chia sẻ một Kubernetes Secret chung cho dev và prod.
- Dùng GitOps/IaC để quản lý manifest, ConfigMap và rollout.
- Chỉ promote image digest đã kiểm thử.
- Bảo đảm liveness/readiness/startup probes phù hợp với thời gian khởi động và dependency.

## 11. Một artifact, nhiều cấu hình: quản lý phiên bản và rollback

Nguyên tắc build once, deploy many làm giảm sai khác giữa staging và production. Nhưng chỉ dùng cùng image chưa đủ; phải ghi nhận **cấu hình đã triển khai**.

Một deployment record nên có:

| Trường | Ví dụ |
|---|---|
| Source commit | 8f3a2c1 |
| Image digest | sha256:... |
| Environment | production |
| Spring profile | prod |
| Config revision | commit hoặc version của deployment repo |
| Secret references | payment-api-key version 5 |
| Runtime service account | checkout-runtime của project production |
| Deployment timestamp | Thời điểm phát hành |
| Approver | Người/nhóm phê duyệt theo quy trình |

Rollback có thể cần khôi phục cả image lẫn configuration. Nếu vừa đổi endpoint, secret version và timeout, chỉ rollback image mà giữ config mới có thể vẫn gây lỗi.

### Promotion pipeline

~~~text
Commit code
   |
   v
Build -> Unit tests -> Integration tests -> Scan
   |
   v
Artifact Registry image digest D
   |
   v
Deploy dev with config C-dev
   |
   v
Deploy staging with config C-staging
   |
   v
Verify SLI / smoke tests / business checks
   |
   v
Deploy production with config C-prod
   |
   v
Canary / monitor / rollback if needed
~~~

Cả ba môi trường dùng digest D. Configuration C-dev, C-staging và C-prod có thể khác nhau nhưng phải được version hóa và review.

## 12. Kiểm tra cấu hình trước khi nhận traffic

Một dịch vụ không nên đến bước xử lý request mới phát hiện thiếu project ID hoặc endpoint.

### Fail fast

- Dùng @Validated và @ConfigurationProperties cho cấu hình bắt buộc.
- Kiểm tra URI, timeout và concurrency trước khi tạo client hoặc bắt đầu nhận traffic.
- Không để production mặc định dùng giá trị local.
- Kiểm tra resource mapping (project, topic, secret reference) trong deployment pipeline.
- Trả startup failure rõ ràng nhưng không log plaintext secret.

### Health checks

Spring Boot Actuator cung cấp health endpoints khi được cấu hình. Liveness kiểm tra tiến trình có còn hoạt động; readiness xác định ứng dụng có sẵn sàng nhận traffic hay không.

Không cấu hình liveness probe gọi liên tục một dependency bên ngoài rồi restart ứng dụng mỗi khi dependency chậm. Readiness có thể phản ánh điều kiện cần để phục vụ traffic; cần tránh biến sự cố dependency thành vòng lặp restart toàn bộ pod.

Trên Cloud Run/GKE, thời gian startup và probes cần phù hợp với thời gian JVM khởi động, warm-up, kết nối database và initialization của clients.

### Không để log tiết lộ secret

Log có thể ghi:

~~~text
Service=checkout
Environment=production
ConfigVersion=cfg-2026-11-19
Project=checkout-prod
Topic=orders-prod
Timeout=1500ms
SecretReference=payment-api-key:5
~~~

Không log giá trị của PAYMENT_API_KEY, mật khẩu, access token hoặc nội dung certificate private key. Ngay cả tên resource và secret reference cũng chỉ nên hiển thị trong log có quyền phù hợp.

## 13. Kiểm thử cấu hình nhiều môi trường

Một chiến lược thực tế cần kiểm tra ở nhiều tầng.

### Unit test cho property binding

Kiểm tra:

- Default value được áp dụng đúng.
- Thiếu project/topic/endpoint làm startup thất bại.
- Duration được parse đúng.
- max-in-flight bằng 0 hoặc âm bị từ chối.
- Môi trường production không nhận endpoint dev.

### Test với profile

Ví dụ chạy test bằng Spring profile:

~~~bash
./mvnw -B -ntp test -Dspring.profiles.active=local
~~~

Có thể dùng @ActiveProfiles trong Spring test để xác định profile. Dùng stub/mock hoặc emulator cho dependency phù hợp; không để unit test vô tình gọi Secret Manager hay Pub/Sub production.

### Integration test trên staging

- Runtime service account truy cập đúng secret/topic.
- Cấu hình endpoint dẫn tới đúng dependency.
- Pub/Sub publish hoặc database query hoạt động.
- Timeout/retry phù hợp với SLO.
- Readiness/liveness và request path hoạt động.
- Không có secret lộ trong logs hoặc error responses.

### Test triển khai và rollback

Triển khai cùng image digest với staging config rồi production config; xác minh chỉ runtime configuration thay đổi. Mô phỏng rollback secret reference hoặc env var bị lỗi trong môi trường thử nghiệm để xác nhận quy trình khôi phục.

## 14. Phát hiện configuration drift

Configuration drift xảy ra khi môi trường thực tế khác với nguồn sự thật: một người đổi environment variables trên Console, thay service account, sửa secret reference hoặc thay namespace ConfigMap mà không cập nhật Git.

Để phát hiện:

1. Lưu deployment manifest/IaC trong repository được review.
2. Định kỳ so sánh trạng thái resource với configuration đã khai báo.
3. Dùng audit logs để xác định thay đổi và principal thực hiện.
4. Cảnh báo khi có thay đổi ngoài pipeline được phép.
5. Quyết định chấp nhận, hoàn nguyên hoặc đưa thay đổi vào IaC theo quy trình.

Trên Cloud Run, mỗi thay đổi cấu hình tạo revision, giúp điều tra và rollback theo revision. Trên GKE, GitOps controller có thể phát hiện và đồng bộ sự khác biệt giữa manifest Git và resource trong cluster. Cần tránh việc controller tự động ghi đè một thay đổi khẩn cấp trước khi nhóm incident thống nhất biện pháp xử lý.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Hardcode project ID trong Java | Deploy nhầm môi trường | Externalize và validate project ID |
| Commit secret vào application-prod.yml | Rò rỉ credential qua Git/artifact | Secret Manager và IAM |
| Dùng một service account cho mọi môi trường | Blast radius lớn | Tách identity và quyền theo môi trường |
| Build JAR riêng cho prod | Artifact khác staging, khó truy vết | Build một lần, promote cùng digest |
| Dùng profile prod nhưng topic dev | Dữ liệu qua sai môi trường | Kiểm tra mapping và policy ở startup/pipeline |
| Không version hóa env variables | Khó rollback, drift | Deployment config trong Git/IaC |
| Dùng latest secret env var không kiểm soát | Instance nhận version khác nhau qua thời gian | Pin version và rollout có kiểm chứng |
| Mong ConfigMap env tự refresh | Pod dùng giá trị cũ | Rollout/restart khi thay đổi |
| In tất cả configuration ra log | Có thể lộ secret | Masking và logging theo allowlist |
| Để default local hoạt động trên production | Lỗi cấu hình bị che giấu | Fail fast với property bắt buộc |
| Không test image digest qua môi trường | Không chứng minh artifact đã kiểm thử | Promote một artifact có digest |
| Chỉ rollback image | Config mới vẫn có thể gây lỗi | Rollback cả cấu hình liên quan |

## 16. Bài thực hành tổng hợp

Bạn cần triển khai checkout-service từ một image Java duy nhất vào staging và production trên Cloud Run.

### Yêu cầu

- Cùng một image digest cho hai môi trường.
- Spring profile staging hoặc prod tương ứng.
- Mỗi môi trường có project, Pub/Sub topic và endpoint riêng.
- Secret payment-api-key lấy từ Secret Manager.
- Runtime service account có quyền tối thiểu.
- Cấu hình timeout và max-in-flight phải được validation.
- Có khả năng xem deployment revision và rollback cấu hình.

### Các bước

1. Định nghĩa CheckoutProperties và validation.
2. Tạo application.yml chứa các property dùng chung và placeholder bắt buộc.
3. Tạo profile-specific YAML chỉ cho các khác biệt hợp lý về hành vi.
4. Tạo staging.env.yaml và prod.env.yaml không có secret.
5. Build image một lần và ghi nhận digest.
6. Triển khai staging bằng image digest và config staging.
7. Chạy smoke test, kiểm tra logs và quyền IAM.
8. Triển khai production bằng cùng image digest và config prod.
9. Kiểm tra project/topic/secret reference thực tế.
10. Thử thay đổi timeout trên staging qua pipeline; xác nhận revision mới và khả năng rollback.

### Tiêu chí hoàn thành

| Tiêu chí | Kết quả mong muốn |
|---|---|
| Image | Cùng digest giữa staging và production |
| Config | Profile và environment variables đúng môi trường |
| Secret | Không có plaintext trong Git/image/log |
| IAM | Service account chỉ có quyền cần thiết |
| Validation | Sai/thiếu property làm startup fail có thông báo an toàn |
| Traceability | Có record image, config revision, secret version |
| Rollback | Có thể quay lại cấu hình/revision ổn định |
| Observability | Dashboard/log phân biệt service, environment và revision |

## 17. Checklist chuẩn hóa cấu hình production

- [ ] Cấu hình được phân loại thành non-sensitive, sensitive và infrastructure.
- [ ] application.yml chứa mặc định an toàn và placeholder rõ ràng.
- [ ] application-{profile}.yml không chứa credential.
- [ ] @ConfigurationProperties có kiểu dữ liệu và validation.
- [ ] Không có fallback âm thầm từ production sang local/dev.
- [ ] Project ID, topic, endpoint và secret reference đúng môi trường.
- [ ] ADC/Workload Identity và runtime service account được cấu hình đúng.
- [ ] IAM cấp tối thiểu theo service/môi trường.
- [ ] Secret Manager version và phương pháp env/volume được chọn có chủ đích.
- [ ] Build một lần, deploy nhiều môi trường bằng cùng image digest.
- [ ] Deployment configuration được review và version hóa trong Git/IaC.
- [ ] Có smoke tests, health probes và startup validation.
- [ ] Không có plaintext secret trong source, image, log, Actuator hoặc CI output.
- [ ] Có kế hoạch rotation và rollback config/secret.
- [ ] Có cơ chế phát hiện thay đổi ngoài pipeline.
- [ ] Có bằng chứng cấu hình đang chạy khớp deployment record.

## Kết luận

Chuẩn hóa cấu hình Java qua nhiều môi trường GCP giúp đội ngũ phát hành cùng một artifact đã kiểm thử mà vẫn cô lập project, identity, endpoint, quota và secret của từng môi trường. Spring Boot externalized configuration và @ConfigurationProperties tạo lớp cấu hình có kiểu dữ liệu, validation và dễ kiểm thử. Cloud Run/GKE cung cấp cách inject environment variables và runtime identity; Secret Manager giữ dữ liệu bí mật ngoài mã nguồn. Khi version hóa deployment configuration, triển khai theo digest, kiểm tra lúc startup và quản lý rollback cùng audit, tổ chức có thể giảm sai sót cấu hình và tăng độ tin cậy cho quy trình CI/CD.

## Tài liệu tham khảo

- [Spring Boot: Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot: Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot: Type-safe configuration properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Google Cloud: Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Run: Environment variables](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables)
- [Cloud Run: Configure secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Run: Service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [Secret Manager: Best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices)
- [GKE: Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Kubernetes: ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes: Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Artifact Registry documentation](https://docs.cloud.google.com/artifact-registry/docs)
- [Cloud Run: Traffic splitting and revisions](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)

