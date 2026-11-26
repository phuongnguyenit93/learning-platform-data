# Tách cấu hình khỏi image và tránh nhúng Secret

## Mục tiêu bài học

Trong chương **Đóng gói ứng dụng** của **SPRING_CLOUD_KUBERNETES**, một bản phát hành cần trả lời được hai câu hỏi: image chứa những gì, và Pod nhận cấu hình ở đâu khi chạy?

Sau bài học, bạn có thể:

- Giữ cùng một image khi chuyển ứng dụng Spring từ môi trường thử nghiệm sang production.
- Phân loại cấu hình thông thường, thông tin nhạy cảm và dữ liệu chỉ cần trong quá trình build.
- Nạp ConfigMap và Secret bằng volume, biến môi trường hoặc tính năng cấu hình của Spring Cloud Kubernetes.
- Tránh đưa mật khẩu vào JAR, Dockerfile, layer image, build context và đầu ra chẩn đoán.
- Chọn cách cập nhật cấu hình có kiểm soát, với quyền RBAC tương ứng cơ chế thực sự sử dụng.

Bài thực hành dùng `catalog-service`, một dịch vụ Spring Boot đọc URL của dịch vụ đối tác và token truy cập. Các tên image, namespace và token minh họa đều cần được thay bằng giá trị của môi trường thực hành. Không có Secret thật trong tài liệu.

## 1. Image là sản phẩm phần mềm; cấu hình là đầu vào lúc chạy

Giả sử nhóm tạo ba image:

```text
catalog-service:1.8.0-dev
catalog-service:1.8.0-staging
catalog-service:1.8.0-prod
```

Nếu mỗi lần build chép một `application-prod.yml` khác nhau vào JAR, image production không còn đúng sản phẩm đã được kiểm thử ở staging. Việc thay URL cũng đòi hỏi chạy lại chuỗi build. Nếu tệp đó có token, người được quyền tải image có thể nhận luôn thông tin truy cập hệ thống đối tác.

Thiết kế mong muốn:

```text
                         + ConfigMap dev     + Secret dev
                         |
Cùng một image digest ---+ ConfigMap staging + Secret staging
                         |
                         + ConfigMap prod    + Secret prod
```

Một lần triển khai nên được nhận diện bằng bộ thông tin:

```text
image digest + phiên bản cấu hình + tham chiếu phiên bản Secret
```

Image digest mô tả chính xác nội dung image. Tên phiên bản cấu hình và Secret cho biết Pod nhận bộ đầu vào nào. Chỉ ghi lại tag `1.8.0` là chưa đủ nếu tag có thể bị trỏ sang image khác hoặc Secret cùng tên đã được cập nhật.

Không phải mọi cấu hình đều phải đưa ra ngoài. Giá trị mặc định an toàn như cổng HTTP, tên ứng dụng, giới hạn phân trang và lựa chọn log cơ bản có thể nằm trong JAR. Token, private key và mật khẩu production không được xem là giá trị mặc định.

## 2. Đặt đúng dữ liệu vào đúng nơi

| Loại dữ liệu | Ví dụ | Nơi phù hợp | Điều cần tránh |
| --- | --- | --- | --- |
| Mã và thư viện | Controller, dependency, migration không chứa mật khẩu | JAR và image | Build riêng chỉ để đổi môi trường |
| Mặc định an toàn | Cổng 8080, timeout cơ sở | `application.yml` trong JAR | Mặc định cho phép bỏ qua xác thực |
| Cấu hình theo môi trường | URL đối tác, mức log, timeout | ConfigMap hoặc biến môi trường | Ghi mật khẩu trong URL |
| Thông tin nhạy cảm lúc chạy | API token, mật khẩu DB, private key | Secret hoặc hệ thống quản lý bí mật | Đưa giá trị thật vào Git, JAR, image |
| Thông tin nhạy cảm khi build | Token tải thư viện từ kho riêng | Secret của CI, BuildKit secret mount | Truyền qua Docker `ARG` hoặc `ENV` |
| Tham chiếu không nhạy cảm | Tên ConfigMap, tên Secret, đường dẫn mount | Deployment và cấu hình triển khai | Nhầm tên Secret với giá trị Secret |

ConfigMap dành cho dữ liệu không bí mật. Đối với dữ liệu nhạy cảm, dùng Secret và thiết lập kiểm soát truy cập thích hợp; đổi tên khóa thành `password` trong ConfigMap không tạo thêm lớp bảo vệ. Xem [khái niệm ConfigMap của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/).

Secret có thể biểu diễn dữ liệu bằng Base64; Base64 không phải mã hóa bảo mật. Bảo vệ dữ liệu lưu trữ, quyền truy cập và bản sao lưu vẫn là trách nhiệm của nền tảng. Xem [cơ chế Secret của Kubernetes](https://kubernetes.io/docs/concepts/configuration/secret/).

## 3. Chọn cơ chế đưa cấu hình vào ứng dụng

| Cơ chế | Phù hợp khi | Ứng dụng cần gọi Kubernetes API? | Cách tiếp nhận thay đổi trong bài này |
| --- | --- | --- | --- |
| `configMapKeyRef`, `secretKeyRef` | Ít khóa, ánh xạ rõ ràng | Không | Tạo Pod mới |
| ConfigMap volume chứa YAML | Nhiều cấu hình có cấu trúc | Không | Tạo Pod mới để Spring đọc lại |
| Secret volume và `configtree:` | Muốn cung cấp từng khóa bằng tệp | Không | Tạo Pod mới hoặc thiết kế nạp lại riêng |
| Spring Cloud Kubernetes Config/Secrets qua API | Cần nguồn cấu hình Kubernetes trong Spring | Có, với đường đọc qua API | Phụ thuộc cơ chế refresh đã cấu hình |
| Configuration Watcher | Có yêu cầu cập nhật mà không khởi động lại | Watcher cần quyền API | Phải thiết kế cả thông báo và hành vi refresh |

Trong thực hành bên dưới, chọn **ConfigMap volume + Secret volume + Spring Boot Config Data**. Cách này giúp quan sát ranh giới image/cấu hình mà không phải cấp thêm quyền API cho tiến trình ứng dụng.

Spring Cloud Kubernetes còn cung cấp DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher. Những tính năng đó giải quyết các nhu cầu khác nhau; việc chạy trên Kubernetes hoặc dùng một ConfigMap không tự tạo ra nhu cầu bật tất cả chúng.

## 4. Chuẩn bị ứng dụng Spring Boot

### 4.1. Giả định của ví dụ

Ứng dụng có:

- Java 21 và phiên bản Spring Boot tương thích; hỗ trợ Config Data và `configtree:`, có từ Spring Boot 2.4.
- Web starter, Actuator và validation starter.
- Lớp `@SpringBootApplication` trong package `com.example.catalog` hoặc package cha của các lớp bên dưới.
- Một executable JAR sau đóng gói tại `target/catalog-service.jar`.

Ví dụ không cần starter đọc cấu hình Kubernetes qua API. Nếu ứng dụng hiện có các starter Spring Cloud Kubernetes, rà soát và tắt hoặc loại bỏ những tích hợp API không dùng theo đúng phiên bản đang chạy. Không giả định rằng bỏ một RoleBinding sẽ tự vô hiệu hóa auto-configuration.

Trong `application.yml` đóng gói cùng ứng dụng chỉ giữ mặc định an toàn:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8080

partner:
  timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Không khai báo token mặc định và không thêm token giả vào profile production để ứng dụng “khởi động cho qua”.

### 4.2. Ràng buộc và kiểm tra cấu hình bắt buộc

Tạo lớp thuộc package mà ứng dụng quét được:

```java
package com.example.catalog;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "partner")
@Validated
public class PartnerProperties {

    @NotNull
    private URI baseUrl;

    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    @NotBlank
    private String apiToken;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public String getApiToken() {
        return apiToken;
    }

    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }
}
```

Đăng ký bằng một lớp cấu hình:

```java
package com.example.catalog;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerProperties.class)
public class PartnerConfiguration {
}
```

Thiếu `partner.api-token` hoặc có giá trị rỗng khiến validation không thành công. Đây là lỗi cấu hình cần sửa trước khi nhận traffic.

Ví dụ dùng lớp thường và không sinh `toString()` chứa toàn bộ thuộc tính. Không log đối tượng này hoặc giá trị token. Với thông tin nhạy cảm, cũng cần rà soát thông báo lỗi binding/validation để tránh đưa giá trị bị từ chối vào log; thông báo lỗi chỉ nên nêu tên thuộc tính và nguyên nhân.

### 4.3. Import tệp YAML và configuration tree

Deployment sẽ truyền:

```text
SPRING_CONFIG_IMPORT=file:/etc/catalog/config/application.yml,configtree:/etc/catalog/secrets/
```

Hai nguồn có cấu trúc khác nhau:

```text
/etc/catalog/config/application.yml
    -> một tài liệu YAML

/etc/catalog/secrets/partner.api-token
    -> nội dung tệp trở thành giá trị partner.api-token
```

Spring Boot hỗ trợ import tệp và `configtree:`; tên tệp có dấu chấm ánh xạ thành tên thuộc tính. Giữ dấu `/` cuối đường dẫn configuration tree. Ví dụ cố ý không dùng `optional:` vì cấu hình cần thiết phải tồn tại. Xem [Externalized Configuration của Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree).

Lưu ý thứ tự ghi đè: biến môi trường và đối số dòng lệnh có thể ghi đè config data. Nếu tồn tại `PARTNER_APITOKEN` hoặc `--partner.api-token=...`, giá trị mà bean nhận có thể không đến từ Secret volume. Với quy tắc bind biến môi trường của Spring Boot, dấu gạch ngang bị loại bỏ: `partner.api-token` tương ứng `PARTNER_APITOKEN`.

## 5. Đóng image mà không mang theo cấu hình môi trường

### 5.1. Dockerfile chỉ chép artifact cần thiết

Một Dockerfile minh họa:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --chown=10001:10001 target/catalog-service.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Tag base image được dùng cho dễ đọc; quy trình phát hành nên ghim digest của base image đã được nhóm kiểm tra. Image của ứng dụng cũng cần được triển khai bằng digest thực tế.

Dockerfile không có mật khẩu, `SPRING_PROFILES_ACTIVE=prod`, bản sao `.env` hay lệnh chép thư mục cấu hình production. UID chạy ứng dụng khác root; thư mục `/app` chỉ cần đọc JAR, không cần quyền ghi.

Một `.dockerignore` theo danh sách cho phép cho ví dụ này:

```dockerignore
**
!Dockerfile
!.dockerignore
!target/
target/**
!target/catalog-service.jar
```

Chỉ JAR được phép đi vào ngữ cảnh build để thực hiện `COPY`. Khi cần tệp khác, bổ sung có chủ đích. Cơ chế `.dockerignore` được giải thích trong [tài liệu build context của Docker](https://docs.docker.com/build/concepts/context/#dockerignore-files).

**Giới hạn quan trọng:** nếu JAR đã chứa `BOOT-INF/classes/application-prod.yml` với mật khẩu, `.dockerignore` không loại bỏ được mật khẩu nằm bên trong JAR. Cần kiểm tra tài nguyên ứng dụng trước đóng gói và quét artifact sau đóng gói.

### 5.2. Vì sao “chép rồi xóa” vẫn nguy hiểm?

Đây là mẫu không được sử dụng:

```dockerfile
# Sai: nội dung nhạy cảm đã đi vào một layer.
COPY production.env /app/production.env
RUN rm /app/production.env
```

Xóa tệp ở layer sau không xóa nội dung đã có trong layer trước. Tương tự, dùng multi-stage build không làm mọi dữ liệu ở builder tự động an toàn: cache, log, output build hoặc artifact được chép sang stage cuối vẫn có thể mang dữ liệu nhạy cảm.

Phải ngăn Secret đi vào đầu vào không cần thiết ngay từ đầu. Nếu một thông tin truy cập thật đã xuất hiện trong image hoặc Git, xóa tệp ở commit mới là chưa đủ; cần thu hồi hoặc xoay thông tin đó và xử lý các bản lưu theo quy trình của nhóm.

### 5.3. Phân biệt Secret khi build với Secret lúc chạy

Token tải dependency từ kho Maven riêng chỉ phục vụ build. Token gọi dịch vụ đối tác chỉ phục vụ ứng dụng lúc chạy. Không dùng chung chúng và không đưa token runtime vào pipeline đóng image.

Khi bắt buộc xác thực trong Docker build, dùng BuildKit secret mount. Đoạn sau là phần riêng của một builder stage Maven, không phải bổ sung vào Dockerfile runtime ở trên:

```dockerfile
# syntax=docker/dockerfile:1
# Giả định builder stage đã có Maven, pom.xml và mã nguồn.
RUN --mount=type=secret,id=maven_settings,required=true \
    mvn -s /run/secrets/maven_settings -B -DskipTests package
```

Lệnh cung cấp tệp từ kho bí mật của CI:

```bash
docker build --secret id=maven_settings,src=/secure/ci/maven-settings.xml .
```

Đường dẫn trên là ví dụ; không commit tệp đó vào repository. Secret mount chỉ cấp dữ liệu cho bước build cần dùng, nhưng lệnh build vẫn có thể làm lộ nếu tự in hoặc chép nội dung ra artifact. Docker khuyến nghị secret mount thay cho `ARG`/`ENV` chứa thông tin nhạy cảm trong [Build secrets](https://docs.docker.com/build/building/secrets/).

## 6. Triển khai ConfigMap và Secret bên ngoài image

### 6.1. Tạo namespace và ConfigMap

Lưu manifest sau thành `catalog-config.yml` trong môi trường thực hành:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: catalog-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config-v1
  namespace: catalog-lab
immutable: true
data:
  application.yml: |
    partner:
      base-url: https://partner.sandbox.example
      timeout: 3s
```

Miền `example` là địa chỉ minh họa, không phải dịch vụ để gửi yêu cầu thật. Nếu triển khai thêm luồng gọi đối tác, thay bằng endpoint thử nghiệm do bạn kiểm soát.

`immutable: true` được chọn để cấu hình v1 không thay đổi ngoài ý muốn. Khi cần timeout mới, tạo `catalog-config-v2` rồi đổi tham chiếu trong Deployment.

Áp dụng:

```bash
kubectl apply -f catalog-config.yml
```

### 6.2. Cấp Secret mà không đưa giá trị thật vào manifest Git

Trong môi trường thật, hệ thống quản lý bí mật hoặc pipeline được cấp quyền nên tạo Secret. Trong lab, ví dụ giả định tệp `/secure/lab/partner-token` đã được cấp bên ngoài thư mục mã nguồn, có quyền đọc phù hợp và không nằm trong build context.

Nội dung tệp là token duy nhất, không có dòng xuống hàng thừa. Không truyền token thật qua `--from-literal=...` trong shell có lưu lịch sử hoặc log CI.

```bash
kubectl -n catalog-lab create secret generic catalog-partner-v1 \
  --from-file=partner.api-token=/secure/lab/partner-token
```

Lệnh tạo Secret mới; nếu tên đã tồn tại, dùng tên phiên bản mới theo quy trình triển khai. Không dùng `-o yaml` để xuất giá trị Secret vào log.

Việc dùng `--from-file` giảm khả năng đặt token trong câu lệnh, nhưng không thay thế kiểm soát tệp nguồn, quyền của người tạo Secret và bảo vệ máy chạy lệnh. Tệp ví dụ phải được quản lý và dọn theo quy trình lưu trữ bí mật của môi trường.

### 6.3. Mount vào Deployment

Lưu manifest sau thành `catalog-deployment.yml`. Trước khi áp dụng, thay `registry.example.com/catalog-service@sha256:REPLACE_WITH_REAL_DIGEST` bằng image đã build và push; đây là placeholder, không phải image có thể chạy.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-runtime
  namespace: catalog-lab
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  namespace: catalog-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
      annotations:
        example.com/config-version: "v1"
        example.com/secret-version: "v1"
    spec:
      serviceAccountName: catalog-runtime
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/catalog-service@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "file:/etc/catalog/config/application.yml,configtree:/etc/catalog/secrets/"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: app-config
              mountPath: /etc/catalog/config
              readOnly: true
            - name: partner-secret
              mountPath: /etc/catalog/secrets
              readOnly: true
            - name: app-tmp
              mountPath: /tmp
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
      volumes:
        - name: app-config
          configMap:
            name: catalog-config-v1
            items:
              - key: application.yml
                path: application.yml
        - name: partner-secret
          secret:
            secretName: catalog-partner-v1
            defaultMode: 0440
            items:
              - key: partner.api-token
                path: partner.api-token
        - name: app-tmp
          emptyDir:
            sizeLimit: 128Mi
```

Hai volume dữ liệu đều chỉ đọc. `/tmp` có volume riêng để ứng dụng vẫn có chỗ ghi tạm khi root filesystem chỉ đọc. `fsGroup` giúp UID không phải root đọc Secret theo nhóm; cần xác minh chính sách quyền file với môi trường triển khai.

Mount cả thư mục, không dùng `subPath`. Kubernetes có thể cập nhật nội dung volume theo thời gian nếu dùng tài nguyên cho phép sửa, nhưng mount bằng `subPath` không nhận cập nhật tự động của Secret. Xem [Secret dưới dạng tệp trong Pod](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod).

Probe dùng các endpoint sức khỏe của Actuator. Nếu có Spring Security, cấu hình quyền để kubelet truy cập được đúng các endpoint probe; không mở toàn bộ Actuator. Xem [các endpoint Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

```bash
kubectl apply -f catalog-deployment.yml
kubectl -n catalog-lab rollout status deployment/catalog-service --timeout=180s
kubectl -n catalog-lab get pods -l app=catalog-service
```

Nếu image nằm trong registry riêng, cấu hình `imagePullSecrets` phù hợp. Secret dùng để kubelet kéo image là một nhu cầu khác với token runtime của ứng dụng.

## 7. Quyền đọc Secret: phân biệt tiến trình ứng dụng và nền tảng

Deployment trên không tạo Role hoặc RoleBinding cho `catalog-runtime`. Tiến trình Spring chỉ đọc các tệp được mount và không nhận ServiceAccount token. Việc kubelet chuẩn bị volume không đòi hỏi cấp quyền `get secrets` cho ServiceAccount của ứng dụng.

Điều đó không có nghĩa Secret không còn rủi ro. Người có quyền tạo Pod trong namespace có thể có khả năng tạo Pod mount Secret ở namespace đó. Vì vậy, quyền tạo workload, quyền thực thi lệnh trong container và quyền đọc Secret phải được đánh giá cùng nhau. Xem [thực hành bảo vệ Secret của Kubernetes](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

Khi chọn **Spring Cloud Kubernetes đọc qua API**, thiết kế thay đổi:

1. Xác định ứng dụng hoặc controller nào thực hiện lời gọi.
2. Chọn đúng namespace và tên tài nguyên cần đọc.
3. Cấp quyền phù hợp thao tác thực tế, kiểm tra xem client dùng `get`, `list` hay `watch`.
4. Chỉ cấp quyền Secret nếu thật sự cần tính năng này.
5. Không dùng `cluster-admin` để giải quyết lỗi cấu hình.

Spring Cloud Kubernetes có `ConfigMap PropertySource` và `Secrets PropertySource`. Đường đọc Secret qua API cần chủ động bật; tài liệu cũng khuyến nghị dùng volume và giới hạn quyền khi cần API. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html) và [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

Đối với đường API, hãy dùng tài liệu đúng phiên bản Spring Boot, Spring Cloud release train và Spring Cloud Kubernetes đã chọn. Không chép cấu hình bootstrap hoặc reload của một phiên bản bất kỳ rồi giả định hành vi giống nhau.

Có thể nhờ tài khoản vận hành được phép impersonate kiểm tra quyền của ServiceAccount:

```bash
kubectl auth can-i get secrets \
  --as=system:serviceaccount:catalog-lab:catalog-runtime \
  -n catalog-lab
```

Với thiết kế lab, kết quả mong muốn là `no`. Lỗi bị từ chối impersonation phản ánh quyền của người chạy lệnh, không chứng minh ServiceAccount có hay không có quyền đọc Secret.

## 8. Thay cấu hình hoặc xoay Secret mà không build lại image

### 8.1. Dữ liệu thay đổi không đồng nghĩa bean thay đổi

Phân biệt bốn thời điểm:

```text
Tài nguyên Kubernetes thay đổi
        |
        v
Tệp trong Pod được cập nhật
        |
        v
Spring nạp lại giá trị vào Environment/bean
        |
        v
Client đang chạy thực sự sử dụng giá trị mới
```

Biến môi trường đã cấp cho một container không tự đổi khi nguồn ConfigMap/Secret đổi. Volume có thể nhận thay đổi sau độ trễ; Spring Boot vẫn không tự refresh bean chỉ vì một tệp đã đổi.

Ngay cả khi đã refresh thuộc tính, một HTTP client đã sao chép token vào interceptor hoặc một connection pool đã mở cũng có thể tiếp tục giữ trạng thái cũ. Vì vậy, cần kiểm chứng hành vi của tài nguyên sử dụng cấu hình, không chỉ kiểm tra tệp.

### 8.2. Chiến lược chính của bài: phiên bản mới và rollout

Ví dụ đổi timeout từ `3s` sang `5s`:

1. Tạo `catalog-config-v2` chứa YAML mới; có thể tiếp tục dùng `immutable: true`.
2. Đổi `volumes[].configMap.name` trong Deployment thành `catalog-config-v2`.
3. Đổi annotation `example.com/config-version` thành `"v2"`.
4. Áp dụng Deployment và chờ rollout; giữ nguyên image digest.
5. Xác nhận Pod mới khỏe và hành vi sử dụng timeout mới.

Thay đổi Pod template tạo rollout. Annotation chỉ ghi dấu phiên bản; Kubernetes không tự tính checksum cho nội dung ConfigMap. Nếu pipeline dùng annotation checksum, pipeline hoặc công cụ template phải tự tính và cập nhật nó.

Xoay token theo cùng nguyên tắc: tạo `catalog-partner-v2`, đổi tham chiếu Secret và annotation, rollout, xác nhận kết nối dùng token mới, rồi mới thu hồi token cũ. Nếu hệ thống đối tác hỗ trợ hai token cùng có hiệu lực, dùng khoảng chuyển tiếp để Pod cũ và mới cùng hoạt động trong rolling update.

Rollback phải chọn lại **cả bộ tham chiếu** tương thích. Đưa Deployment về Secret cũ không có tác dụng nếu token cũ đã bị thu hồi; khi đó cần khôi phục khả năng truy cập bằng thông tin còn hợp lệ. Giữ lại ConfigMap/Secret phiên bản cũ trong cửa sổ rollback theo chính sách, thay vì xóa ngay sau rollout.

Nếu buộc sửa tài nguyên cùng tên, cần chủ động tạo Pod mới, chẳng hạn `kubectl rollout restart`. Với `catalog-config-v1` bất biến trong lab, phải tạo tài nguyên tên mới; không thể sửa trực tiếp phần `data`.

### 8.3. Khi nào dùng Configuration Watcher?

Configuration Watcher có thể hỗ trợ gửi tín hiệu refresh cho ứng dụng Spring Cloud. Nó không biến mọi bean hoặc client thành đối tượng tự cập nhật; vẫn phải thiết kế quyền, cách gọi refresh hoặc Bus và kiểm tra hành vi sau refresh. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Cân nhắc Watcher khi thời gian thay đổi cấu hình là yêu cầu vận hành cụ thể, rollout gây chi phí đáng kể và nhóm đã kiểm thử refresh cho từng loại thuộc tính. Bảo vệ đường refresh như một thao tác quản trị. Mô hình một controller theo dõi tài nguyên cũng cần RBAC riêng cho controller; không sao chép quyền đó sang mọi ứng dụng.

Đối với token hoặc cấu hình khởi tạo client, phiên bản hóa và rollout thường dễ quan sát hơn. Quyết định cuối cùng dựa trên yêu cầu cập nhật và hành vi ứng dụng, không dựa vào việc thư viện đã có sẵn tính năng reload.

## 9. Xác minh mà không in Secret

### 9.1. Kiểm tra image và trạng thái triển khai

Các lệnh sau chỉ đọc thông tin cần thiết:

```bash
kubectl -n catalog-lab get deployment catalog-service \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

kubectl -n catalog-lab get deployment catalog-service \
  -o jsonpath='{.spec.template.spec.volumes[?(@.name=="partner-secret")].secret.secretName}'

kubectl -n catalog-lab get secret catalog-partner-v1 \
  -o custom-columns=NAME:.metadata.name,TYPE:.type

kubectl -n catalog-lab rollout status deployment/catalog-service --timeout=180s
```

So sánh image digest trước và sau thay cấu hình: digest phải giữ nguyên nếu chỉ đổi ConfigMap hoặc Secret. Đối chiếu tên tài nguyên với phiên bản đã duyệt, rồi kiểm tra hành vi không nhạy cảm như timeout hoặc kết quả xác thực qua một yêu cầu thử được phép.

Để xem probe trong lab:

```bash
kubectl -n catalog-lab port-forward deployment/catalog-service 8080:8080
```

Trong terminal khác:

```bash
curl -fsS http://localhost:8080/actuator/health/readiness
```

Kết quả sức khỏe thành công chứng minh ứng dụng đáp ứng probe, không chứng minh token có hiệu lực tại dịch vụ đối tác. Chỉ một phép thử tương tác phù hợp mới kiểm chứng được điều đó.

### 9.2. Kiểm tra artifact và đường rò rỉ

Trong quy trình đóng gói, kiểm tra:

- Danh sách tài nguyên trong JAR, nhất là `application-*.yml`, `.env`, keystore và private key không được phép phát hành.
- Secret scanning trên nguồn, artifact và các layer image bằng công cụ đã được nhóm chọn.
- Log build và log khởi động để tránh nội dung cấu hình, header `Authorization` hoặc phản hồi chứa token.
- Build context, cache và artifact trung gian theo chính sách lưu giữ.

`docker history` và `docker inspect` có thể giúp phát hiện lệnh build hoặc biến môi trường bất thường, nhưng không chứng minh image sạch Secret. Khi đang điều tra image nghi rò rỉ, đầu ra của chúng cũng có thể chứa dữ liệu nhạy cảm; không đưa nguyên văn lên hệ thống log chung.

Không dùng `printenv`, `cat /etc/catalog/secrets/partner.api-token`, `kubectl get secret -o yaml` hoặc mở `/actuator/env` để chứng minh ứng dụng “đã nhận token”. Nếu cần log chẩn đoán, chỉ ghi mã phiên bản Secret do pipeline gán, tên thuộc tính bị thiếu hoặc kết quả xác thực đã được làm sạch.

## 10. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Pod không khởi tạo được container vì volume | Secret/ConfigMap sai tên, khác namespace hoặc thiếu khóa trong `items` | Đối chiếu tham chiếu và tên khóa; xem event trong phạm vi được phép |
| Ứng dụng báo thiếu `partner.api-token` | Import sai, thiếu tệp hoặc nội dung rỗng | Kiểm tra đường mount, tên tệp và nguồn cấp Secret; không in nội dung |
| Tệp tồn tại nhưng Java không đọc được | UID/GID và mode không phù hợp | Đối chiếu `runAsUser`, `fsGroup`, mode và chính sách volume |
| Cấu hình ngoài không có hiệu lực | Thuộc tính bị environment/command line ghi đè | Tìm nguồn khai báo trùng; thống nhất một nguồn sở hữu mỗi khóa |
| Tệp đổi nhưng ứng dụng dùng giá trị cũ | Chưa nạp lại Spring hoặc client giữ bản sao | Rollout hoặc thiết kế refresh đã được kiểm chứng |
| Ứng dụng báo 403 khi đọc Kubernetes API | Starter/API loader đang hoạt động nhưng thiếu quyền | Xác định có cần API không, rồi tắt tích hợp thừa hoặc cấp quyền hẹp |
| Rollout xong nhưng gọi đối tác thất bại | Token sai, hết hạn, sai endpoint hoặc mạng không tới | Kiểm tra phiên bản đầu vào và phép thử kết nối có kiểm soát |
| Readiness tốt dù token đã hết hạn | Probe mặc định không kiểm tra xác thực đối tác | Phân biệt sức khỏe tiến trình với sức khỏe tích hợp; bổ sung quan sát phù hợp |
| Token bị phát hiện trong image cũ | Đã đưa vào JAR, layer hoặc metadata | Thu hồi token, build lại từ đầu vào sạch và xử lý bản image/cache liên quan |

Không đưa tình trạng dịch vụ đối tác vào liveness một cách máy móc: lỗi bên ngoài có thể làm toàn bộ Pod bị khởi động lại mà không giải quyết được nguyên nhân. Hãy chọn tín hiệu readiness và cảnh báo theo yêu cầu phục vụ thực tế.

## 11. Bài thực hành củng cố

Thực hiện trong namespace lab và chỉ dùng thông tin thử nghiệm:

1. Build một image không có token; ghi lại digest.
2. Cấp `catalog-config-v1` và `catalog-partner-v1` ngoài image; triển khai bằng digest đó.
3. Xác nhận rollout và probe, rồi kiểm tra ứng dụng gọi được endpoint thử nghiệm nếu đã cài luồng tích hợp.
4. Tạo ConfigMap v2 với timeout khác, đổi Deployment và chứng minh image digest không thay đổi.
5. Tạo Secret v2 và thử quy trình chuyển token có khoảng chồng lấp trước khi thu hồi v1.
6. Thử tham chiếu một Secret không tồn tại; xác định lỗi ở khâu chuẩn bị volume thay vì sửa Dockerfile.
7. Thử Secret tồn tại nhưng token rỗng; quan sát lỗi validation khi Spring khởi động, không in giá trị.
8. Ghi lại bộ phiên bản dùng cho rollback và giải thích điều gì xảy ra nếu token cũ đã bị thu hồi.

Bài làm đạt yêu cầu khi bạn chứng minh được cấu hình thay đổi độc lập với image, ứng dụng dừng khi thiếu thông tin bắt buộc, và đường cấp Secret không đi qua artifact đóng gói hoặc log chẩn đoán.
