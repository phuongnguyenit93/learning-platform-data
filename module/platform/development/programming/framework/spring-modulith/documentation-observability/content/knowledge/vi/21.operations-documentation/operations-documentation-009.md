# Giữ tài liệu khớp cấu hình production

## 1. Mục tiêu

Tài liệu vận hành phải phản ánh cấu hình mà ứng dụng Spring Boot thực sự sử dụng ở production, gồm property source, profile, secret reference, Actuator và revision triển khai.

~~~yaml
spring:
  profiles:
    active: prod
~~~

Không kết luận file này là nguồn cấu hình cuối cùng: environment variables, JVM properties và command-line arguments có thể ghi đè giá trị trong file.

## 2. Ba lớp cấu hình cần được ghi nhận

| Lớp | Nội dung | Nguồn thường gặp | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| **Declared configuration** | Default và cấu trúc property mà ứng dụng hỗ trợ | application.yaml, @ConfigurationProperties, metadata | Ứng dụng hiểu những property nào? |
| **Deployed configuration** | Giá trị/nguồn được gắn vào workload của môi trường | Helm values, Deployment, ConfigMap, Secret reference | Release này định cung cấp cấu hình nào? |
| **Effective configuration** | Giá trị Spring Environment và bean đã bind thực sự sử dụng | /actuator/env, /actuator/configprops, startup diagnostics | Instance đang chạy với giá trị nào và đến từ đâu? |

Tài liệu vận hành phải nối được cả ba lớp. Chỉ sao chép application.yaml vào wiki không đủ để mô tả production nếu deployment có override.

Mỗi trang vận hành nên ghi service name, Spring Boot/Spring Modulith version, Java runtime, image digest, Git commit, Helm chart/deployment revision, profile active, thời điểm xác minh và team sở hữu cấu hình. Không dùng từ “latest” làm phiên bản duy nhất; người vận hành cần biết tài liệu đang mô tả binary và cấu hình của release nào.

## 3. Hiểu thứ tự ưu tiên property của Spring Boot

Spring Boot xây dựng Environment từ nhiều PropertySource. Nếu cùng một key có ở nhiều nguồn, nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị cuối.

Ở mức khái quát, các nguồn thường gặp được sắp theo thứ tự ưu tiên tăng dần:

1. Default properties đặt qua SpringApplication.
2. @PropertySource trên configuration class.
3. Config data như application.yaml, file profile và file được import.
4. RandomValuePropertySource.
5. OS environment variables.
6. Java system properties (-D...).
7. JNDI và servlet context/config parameters nếu ứng dụng chạy trong môi trường đó.
8. SPRING_APPLICATION_JSON.
9. Command-line arguments (--property=value).
10. Test property sources trong test context.

Đây là bản rút gọn để định hướng điều tra; danh sách chính xác và chi tiết từng nhóm cần đối chiếu Spring Boot reference guide của phiên bản đang triển khai. Test property sources chỉ áp dụng cho test, không phải cấu hình production.

### 3.1. Thứ tự bên trong Config Data

Các file config data thường được xử lý theo nhóm:

- File application đóng gói trong JAR.
- File profile-specific đóng gói trong JAR.
- File application ở ngoài JAR.
- File profile-specific ở ngoài JAR.

Các location group, spring.config.import, spring.config.location và spring.config.additional-location có thể thay đổi cách nhóm và ghi đè. Profile-specific files thường ghi đè file không gắn profile trong cùng quy tắc location; nếu nhiều profile active, quy tắc last-wins được áp dụng.

Ví dụ các nguồn có thể cùng định nghĩa datasource URL:

~~~text
application.yaml
application-prod.yaml
/etc/shop/application.yaml
/etc/shop/application-prod.yaml
SPRING_DATASOURCE_URL
--spring.datasource.url=...
~~~

Không kết luận giá trị trong application-prod.yaml chắc chắn là giá trị cuối cùng. Environment variable hoặc command-line argument có thể ghi đè nó.

### 3.2. Profile là điều kiện kích hoạt, không phải bằng chứng của cấu hình hiệu lực

~~~yaml
# application-prod.yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Profile có thể được bật từ deployment:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
~~~

spring.profiles.active tuân theo quy tắc ưu tiên property như các property khác. Không đặt nó trong profile-specific document hoặc document được kích hoạt bằng spring.config.activate.on-profile; hãy cấu hình profile active từ nguồn không phụ thuộc profile.

Tài liệu production cần ghi cả profile active và nguồn kích hoạt profile.

## 4. Relaxed binding và tên biến môi trường

Với environment variable, quy tắc chuyển tên canonical property thường là:

1. Thay dấu chấm bằng dấu gạch dưới.
2. Bỏ dấu gạch ngang.
3. Chuyển thành chữ hoa.

| Property canonical | Environment variable |
| --- | --- |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| management.endpoints.web.exposure.include | MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE |
| management.tracing.sampling.probability | MANAGEMENT_TRACING_SAMPLING_PROBABILITY |
| spring.task.execution.pool.max-size | SPRING_TASK_EXECUTION_POOL_MAXSIZE |

Giữ property canonical trong tài liệu và ghi tên biến môi trường ở cột riêng. Với collection, map và property có index, hãy kiểm tra binding thực tế thay vì tự đoán tên biến. Ví dụ list index thường được bao bằng dấu gạch dưới:

~~~text
my.service[0].other
MY_SERVICE_0_OTHER
~~~

## 5. Tạo danh mục cấu hình production

Một configuration inventory nên có:

| Cột | Nội dung cần ghi |
| --- | --- |
| Property key | Tên canonical theo Spring Boot |
| Mục đích | Tác động tới hành vi nào |
| Kiểu/đơn vị | Boolean, integer, URI, duration, bytes, enum... |
| Default | Giá trị mặc định của ứng dụng/framework |
| Production source | ConfigMap, Secret reference, environment variable, config tree, JVM argument... |
| Effective value | Giá trị đã xác minh; secret chỉ ghi trạng thái hoặc reference |
| Scope | Service, module, instance hay environment |
| Restart/reload | Restart, rolling restart hay refresh mechanism cụ thể |
| Validation | Ràng buộc hợp lệ và giới hạn vận hành |
| Owner | Team chịu trách nhiệm |
| Verification | Endpoint, command hoặc test dùng để xác minh |
| Last reviewed | Revision và thời điểm đối chiếu gần nhất |

Ví dụ danh mục rút gọn:

| Property | Mục đích | Production source | Xác minh |
| --- | --- | --- | --- |
| spring.application.name | Service identity | Deployment env | /actuator/env |
| spring.profiles.active | Bật profile production | Deployment env | Startup log và /actuator/env |
| spring.datasource.url | JDBC endpoint | ConfigMap/secret reference | /actuator/env, không lộ credential |
| spring.datasource.hikari.maximum-pool-size | Giới hạn connection pool | Helm values/ConfigMap | /actuator/configprops |
| management.endpoints.web.exposure.include | Endpoint Actuator được expose | App config + deployment override | /actuator/env và route thực tế |
| management.tracing.sampling.probability | Tỷ lệ trace được sample | Profile/ConfigMap | /actuator/env và trace backend |
| Property exporter OTLP theo Boot version | Địa chỉ trace collector | ConfigMap | /actuator/env, không ghi credential |

Tên property của exporter có thể thay đổi giữa các dòng Spring Boot. Ghi key đúng với version của service; đừng dùng một bảng cấu hình chung cho mọi version.

## 6. Quản lý default, override và secret riêng biệt

Một cách tổ chức thường dùng:

~~~text
application.yaml
  └── default an toàn, dùng được ở local

application-prod.yaml
  └── khác biệt không nhạy cảm của production

Deployment / Helm values
  └── profile, resource limits, non-secret environment variables

ConfigMap
  └── endpoint và cấu hình môi trường không bí mật

Secret manager / Kubernetes Secret
  └── credential, token, certificate material
~~~

Không ghi secret thật trong Markdown, README, ví dụ lệnh, issue hoặc ảnh chụp Actuator. Tài liệu chỉ nên ghi tên secret/secret-manager path, key cần có, namespace/environment, team quản lý, quy trình rotate và cách xác minh binding mà không in giá trị.

| Property | Secret reference | Ghi chú |
| --- | --- | --- |
| spring.datasource.username | shop-db-credentials / username | Secret do platform team cấp |
| spring.datasource.password | shop-db-credentials / password | Không ghi giá trị vào tài liệu |
| payment.provider.api-key | payment-provider / api-key | Rotate theo quy trình provider |

### 6.1. Dùng configuration tree cho secret được mount thành file

Spring Boot hỗ trợ configtree: để chuyển tên file trong thư mục mount thành property:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Nếu thư mục có các file spring.datasource.username, spring.datasource.password và payment.provider.api-key, nội dung từng file được bind thành property tương ứng. Với secret bắt buộc ở production, không dùng optional: chỉ để ứng dụng khởi động khi secret bị thiếu; hãy để validation/startup fail rõ ràng.

Config tree có thể dùng với Kubernetes Secret hoặc Docker secret được mount thành volume. Tài liệu phải ghi chính xác mount path và key names, không sao chép nội dung file secret.

## 7. Dùng @ConfigurationProperties làm hợp đồng cấu hình

Với cấu hình riêng của ứng dụng, nên gom các property liên quan vào một type thay vì rải nhiều @Value trong code. Type-safe configuration hỗ trợ relaxed binding, metadata và validation.

~~~java
package com.example.shop.payments;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties("shop.payment")
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts) {
}
~~~

Đăng ký property type bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
}
~~~

Cần có Bean Validation implementation trên classpath để các constraint như @NotNull và @Min được thực thi. Với nested property cần cascade validation, đánh dấu field/record component tương ứng bằng @Valid.

~~~yaml
shop:
  payment:
    base-url: "https://payments.example.internal"
    timeout: 3s
    max-attempts: 2
~~~

Khi cấu hình thiếu hoặc không hợp lệ, ứng dụng nên fail ngay lúc startup thay vì đợi request đầu tiên mới phát hiện.

### 7.1. Sinh configuration metadata

Khai báo spring-boot-configuration-processor ở annotation processor path để IDE và tooling có thể gợi ý các key được hỗ trợ. Ví dụ với Gradle:

~~~groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Với Maven, khai báo artifact trong annotationProcessorPaths của maven-compiler-plugin theo hướng dẫn Spring Boot. Metadata giúp phát hiện property do ứng dụng tự định nghĩa, mô tả field và giá trị mặc định có thể suy ra. Nó không thay thế tài liệu production: metadata không biết giá trị override ở Kubernetes, Secret Manager hoặc runtime.

## 8. Xác minh cấu hình hiệu lực bằng Actuator

| Endpoint | Nội dung |
| --- | --- |
| /actuator/env | Property sources trong Spring Environment, property và nguồn đóng góp |
| /actuator/configprops | Các bean @ConfigurationProperties đã bind và các property có thể bind |
| /actuator/conditions | Điều kiện auto-configuration và lý do cấu hình có hoặc không được áp dụng |

Ví dụ truy vấn:

~~~bash
curl -s http://localhost:8080/actuator/env/spring.profiles.active
curl -s http://localhost:8080/actuator/env/management.tracing.sampling.probability
curl -s http://localhost:8080/actuator/configprops
~~~

Endpoint env giúp xác định property đến từ nguồn nào; configprops giúp xem bean đã bind; conditions giúp điều tra auto-configuration. Kết hợp ba nguồn này để tìm nguyên nhân thay vì chỉ đọc một file YAML.

### 8.1. Giữ endpoint nhạy cảm ở trạng thái an toàn

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus,modulith"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Trong production, không expose env và configprops rộng rãi chỉ để tiện debug. Nếu cần dùng, giới hạn mạng và quyền truy cập, đồng thời giữ show-values: never trừ khi có quy trình quản trị đặc biệt được phê duyệt. Các endpoint này vẫn có thể tiết lộ tên property, cấu trúc ứng dụng và nguồn cấu hình dù giá trị đã được sanitize.

Nếu tổ chức cần cho admin xem giá trị không nhạy cảm, có thể dùng when-authorized với role được cấu hình rõ ràng; không dùng always trên production. Secret vẫn cần được sanitize bằng chính sách phù hợp.

Không đưa response nguyên vẹn của /actuator/env hoặc /actuator/configprops vào ticket công khai hay tài liệu version control. Khi lưu bằng chứng, loại bỏ credential, token, host nội bộ nhạy cảm và thông tin định danh cần bảo vệ.

## 9. Tài liệu hóa cấu hình observability của Spring Modulith

Với service này, cấu hình production cần mô tả cả module architecture lẫn pipeline quan sát:

| Hạng mục | Nội dung tài liệu phải ghi |
| --- | --- |
| Modulith Insight | Dependency/starter và version được quản lý bởi BOM |
| Module detection | Package/module arrangement và custom detection convention |
| Module actuator | Endpoint /actuator/modulith, access policy và management port |
| Module observations | Có instrument module entry hay không; metric/span handler được đăng ký ra sao |
| Event metrics | Counter publication nào được bật, customizer có thêm tag nào |
| Tracing | Bridge/exporter, endpoint collector, sampling và resource/service name |
| Context propagation | Executor nào có task decorator; Reactor mode nếu ứng dụng reactive |
| Prometheus | Scrape path, interval, histogram và relabel policy |
| Logs | Correlation IDs, structured format và retention |

Spring Modulith Insight starter cung cấp Actuator và observability support; để gửi telemetry tới monitoring backend vẫn cần dependency/registry/exporter phù hợp. Tài liệu phải ghi rõ cả hai phần, không suy luận rằng chỉ thêm Insight starter là đã có đầy đủ remote trace export.

Nếu ứng dụng tùy biến cách phát hiện application modules, các tùy biến đó phải nằm trong production sources để actuator/observability runtime nhìn thấy cùng cấu trúc module như kiến trúc mà đội phát triển kiểm thử.

### 9.1. Ghi property theo version

| Khái niệm | Property hoặc nguồn | Cần ghi |
| --- | --- | --- |
| Active profile | spring.profiles.active | Giá trị profile và nguồn cấp |
| Actuator exposure | management.endpoints.web.exposure.include | Danh sách endpoint thực tế |
| Sampling | management.tracing.sampling.probability | Giá trị, policy và môi trường |
| OTLP endpoint | Property exporter theo Boot version | Protocol, host/path, TLS/auth reference |
| Prometheus histogram | management.metrics.distribution.percentiles-histogram.* | Meter name, bucket và cardinality impact |
| Module graph | /actuator/modulith | Module list, dependency types và version |

Tên property của tracing exporter và các module integration có thể đổi theo Spring Boot/Micrometer version. Ghi tên key được binder nhận trong chính version production; nếu nâng version, cập nhật bảng và kiểm tra lại bằng Actuator.

## 10. Giữ cấu hình và tài liệu trong cùng quy trình thay đổi

~~~mermaid
flowchart TD
    Change["Đề xuất thay đổi property"] --> Impact["Xác định module/service/environment"]
    Impact --> Update["Cập nhật config source và documentation"]
    Update --> Validate["CI: parse, bind, validate, policy checks"]
    Validate --> Review["Review owner + operations"]
    Review --> Deploy["Deploy immutable release/config revision"]
    Deploy --> Verify["Verify effective config và runtime behavior"]
    Verify --> Record["Ghi revision, thời điểm và kết quả"]
    Record --> Docs["Tài liệu production khớp runtime"]
~~~

Trong pull request, mô tả property được thêm/đổi/xóa; default và production override; environment chịu tác động; restart/refresh behavior; thay đổi secret reference; rủi ro, dashboard/alert và điều kiện rollback; trang vận hành được cập nhật ở đâu.

Không merge một thay đổi property production mà không biết ai sở hữu key đó và cách xác minh sau deploy.

## 11. Kiểm tra configuration drift trong CI

CI không thể biết mọi giá trị runtime nếu chưa kết nối deployment system, nhưng có thể kiểm tra hợp đồng cấu hình và những khác biệt được quản lý trong Git.

Các kiểm tra hữu ích:

1. Parse YAML/Helm values và xác nhận schema.
2. Build application để kiểm tra @ConfigurationProperties binding.
3. Chạy test context với profile/environment fixture đại diện.
4. Xác nhận property bắt buộc có mặt và nằm trong range hợp lệ.
5. Kiểm tra key cũ đã deprecated hoặc bị xóa trong version hiện tại.
6. So sánh property inventory với generated configuration metadata.
7. Kiểm tra documentation chứa đúng property keys và source references.
8. Phát hiện secret literal hoặc token pattern trong tài liệu và config được commit.
9. Kiểm tra Helm render output hoặc Kubernetes manifest đã render trước khi deploy.
10. Lưu image digest, chart version và config revision vào release record.

### 11.1. Test binding và validation

Một test context có thể xác minh cấu hình hợp lệ:

~~~java
class PaymentPropertiesTest {

    @Test
    void bindsProductionLikeConfiguration() {
        new ApplicationContextRunner()
            .withUserConfiguration(PaymentConfiguration.class)
            .withPropertyValues(
                "shop.payment.base-url=https://payments.example.internal",
                "shop.payment.timeout=3s",
                "shop.payment.max-attempts=2"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                PaymentProperties properties =
                    context.getBean(PaymentProperties.class);
                assertThat(properties.maxAttempts()).isEqualTo(2);
            });
    }
}
~~~

Đây là ví dụ test binding; cần khai báo ApplicationContextRunner, AssertJ và configuration class phù hợp với dự án. Test không chứng minh production đã dùng đúng ConfigMap/Secret; nó chứng minh ứng dụng hiểu và validate cấu hình theo hợp đồng.

### 11.2. Kiểm tra drift sau deployment

| Revision | Lấy từ đâu? | Mục đích |
| --- | --- | --- |
| Git commit | Release artifact metadata | Code/default config |
| Deployment/config revision | Helm release, GitOps commit hoặc manifest revision | Desired configuration |
| Runtime identity | /actuator/info, deployment labels hoặc release metadata | Instance thực sự đang chạy |

Nếu deployment revision không khớp GitOps source of truth, coi đó là drift cần điều tra. Không tự động ghi đè thay đổi thủ công trước khi xác định ai/automation nào đã thay đổi và vì sao.

## 12. Kubernetes, ConfigMap và Secret: xác minh mà không lộ giá trị

Một runbook có thể dùng các lệnh sau để kiểm tra nguồn cấu hình:

~~~bash
kubectl get deployment shop-service -n production -o yaml
kubectl describe deployment shop-service -n production
kubectl get configmap shop-service-config -n production -o yaml
kubectl get secret shop-service-credentials -n production -o jsonpath='{.metadata.name}{"\n"}'
kubectl rollout history deployment/shop-service -n production
~~~

Các lệnh trên là ví dụ; thay namespace và resource name theo môi trường. Không chạy kubectl get secret -o yaml để sao chép secret value vào log/ticket. Chỉ kiểm tra metadata, key names, reference và quyền truy cập; giá trị secret phải được bảo vệ.

Khi cần xác nhận env variable của container, đọc tên biến và nguồn configMapKeyRef/secretKeyRef trong Pod spec. Tránh in giá trị secret từ process environment.

### 12.1. ConfigMap thay đổi không có nghĩa ứng dụng đã nhận cấu hình mới

- Environment variables được gán lúc container tạo; sửa ConfigMap không tự thay đổi environment của process đang chạy.
- Volume mount từ ConfigMap/Secret có thể được cập nhật bởi Kubernetes theo cơ chế của volume, nhưng Spring Boot không tự động rebind mọi bean/property chỉ vì file thay đổi.
- Nếu ứng dụng không có cơ chế refresh được thiết kế rõ, hãy dùng rollout/restart để process khởi động với cấu hình mới.
- Nếu dùng Spring Cloud refresh hoặc config client, tài liệu phải ghi trigger, phạm vi bean được refresh và giới hạn của cơ chế đó.

Đừng ghi “cấu hình tự reload” nếu ứng dụng chỉ đọc Config Data ở startup.

## 13. Quy trình rollout và rollback cấu hình

### 13.1. Trước rollout

1. Xác nhận property key có trong version Spring Boot đang chạy.
2. Kiểm tra default, override và property precedence.
3. Xác nhận secret reference tồn tại và quyền mount đúng.
4. Chạy validation/binding test và render manifest.
5. Ghi lại cấu hình hiện tại và revision để rollback.
6. Xác định dashboard/alert cần theo dõi.
7. Thống nhất restart strategy và maintenance window nếu cần.

### 13.2. Sau rollout

1. Kiểm tra deployment rollout thành công và pod chạy image/config revision mong đợi.
2. Kiểm tra startup log, active profile và application identity.
3. Dùng /actuator/env hoặc /actuator/configprops trong phạm vi truy cập được phép để xác nhận property hiệu lực.
4. Kiểm tra /actuator/health, /actuator/metrics, /actuator/prometheus và /actuator/modulith theo endpoint đã expose.
5. Xác minh trace exporter, log correlation và module metrics vẫn hoạt động.
6. Theo dõi latency, error ratio, connection pool, queue và các alert liên quan.
7. Cập nhật release record với kết quả và thời điểm xác minh.

### 13.3. Khi rollback

- Rollback đồng bộ application image và configuration revision tương thích.
- Không chỉ rollback ConfigMap nếu code mới yêu cầu property mới hoặc đã bỏ property cũ.
- Nếu secret đã rotate, xác định ứng dụng phiên bản cũ có còn đọc được secret mới hay cần khôi phục version secret phù hợp.
- Sau rollback, xác minh effective config và health/runtime behavior như một deployment mới.
- Ghi lại nguyên nhân và cập nhật runbook nếu bước rollback thực tế khác tài liệu.

## 14. Cấu trúc trang tài liệu vận hành đề xuất

| Phần | Nội dung |
| --- | --- |
| Service identity | Service name, owner, repository, version, environment |
| Module architecture | Module list, dependency graph, public entry points |
| Runtime topology | Replica, ports, dependencies, network paths |
| Configuration inventory | Property, source, default, override, validation, owner |
| Secrets | Secret references, rotation owner, mount path; không ghi value |
| Actuator and access | Endpoint được expose, management port, authorization |
| Observability | Module metrics, traces, sampling, log correlation, exporter |
| SLO and alerts | Availability, latency, error ratio, cardinality, event backlog |
| Deployment | Image/chart version, rollout strategy, config revision |
| Runbooks | Startup failure, config drift, database, collector, event listener |
| Recovery | Rollback, restore, secret recovery, incident escalation |
| Change history | PR, deployment revision, reviewer, ngày xác minh |

### 14.1. Mẫu configuration inventory

~~~markdown
| Property | Purpose | Default | Production source | Effective value/reference | Reload | Owner | Verification |
|---|---|---|---|---|---|---|---|
| shop.payment.timeout | Provider timeout | 3s | ConfigMap | 3s | Restart | Payments | /actuator/configprops |
| shop.payment.api-key | Provider credential | none | Secret payment-provider/api-key | Secret reference only | Restart | Platform | Startup/health check |
~~~

Không đưa secret value vào cột Effective value; ghi secret reference và kết quả kiểm tra binding thay thế.

## 15. Những dấu hiệu tài liệu đã lệch production

| Dấu hiệu | Rủi ro | Việc cần làm |
| --- | --- | --- |
| Tài liệu ghi profile prod, runtime chạy production | Profile-specific file không được kích hoạt như dự kiến | Xác minh spring.profiles.active và profile groups |
| Property trong file khác /actuator/env | Có override từ nguồn ưu tiên cao hơn | Kiểm tra property source/origin |
| /actuator/configprops không có bean mong đợi | ConfigurationProperties chưa được scan/register hoặc condition không match | Kiểm tra binding và /actuator/conditions |
| Deployment env var không còn trong inventory | Tài liệu thiếu nguồn override | Cập nhật inventory từ manifest/source of truth |
| ConfigMap revision thay đổi nhưng pod chưa restart | Process vẫn dùng cấu hình cũ | Rollout restart theo quy trình |
| Tài liệu ghi endpoint Modulith nhưng /actuator không quảng bá link | Dependency/exposure/management context sai | Kiểm tra Insight/Actuator và security |
| Tài liệu ghi OTLP endpoint cũ | Trace export có thể thất bại hoặc gửi sai collector | Kiểm tra effective property và exporter logs |
| Property cũ còn trong tài liệu sau nâng version | Operator áp dụng key không còn tác dụng | Kiểm tra deprecation/migration guide và xóa hướng dẫn cũ |
| Tài liệu chứa secret value | Có nguy cơ lộ credential lâu dài | Rotate secret, xử lý lịch sử lưu trữ và sửa tài liệu |
| Runbook không ghi restart behavior | Thay đổi có thể không có hiệu lực | Ghi rõ startup-bound hay dynamic refresh |

## 16. Runbook: điều tra configuration drift

Khi hành vi production khác tài liệu, đi theo trình tự:

1. **Chốt instance:** ghi service name, pod, image digest, application version và deployment revision.
2. **Chốt profile:** xác định profile active từ startup log và nguồn property.
3. **Xác định key:** chọn một property cụ thể liên quan đến hành vi sai.
4. **Kiểm tra Environment:** xem /actuator/env/{property} trong phạm vi được cấp quyền; ghi property source/origin, không sao chép secret.
5. **Kiểm tra binding:** xem /actuator/configprops để xác nhận bean nhận property.
6. **Kiểm tra condition:** nếu bean/feature không có, xem /actuator/conditions.
7. **Đối chiếu desired config:** so với Helm/ConfigMap/Secret reference và GitOps revision.
8. **Tìm override ngoài dự kiến:** environment variable, JVM argument, command line hoặc SPRING_APPLICATION_JSON.
9. **Xác định thời điểm nạp:** startup-only, file mount update hay refresh mechanism.
10. **Khắc phục source of truth:** đưa thay đổi đúng về Git/Config management, không để hotfix thủ công thành trạng thái không quản lý.
11. **Rollout và xác minh:** restart/refresh theo thiết kế, kiểm tra effective config và metrics/log/traces.
12. **Cập nhật tài liệu:** ghi revision, owner, kết quả và bước rollback.

Không kết luận “Spring Boot bỏ qua property” trước khi kiểm tra property source order, canonical key, profile activation và binding target.

## 17. Bài thực hành: đồng bộ tài liệu với production-like environment

**Bối cảnh:** ứng dụng Spring Modulith có các module orders, payments và inventory. Local dùng default config; staging dùng profile riêng; production nhận một số giá trị từ environment variables, ConfigMap và mounted Secret.

Thực hiện:

1. Tạo configuration inventory cho spring.application.name, active profile, datasource pool, tracing sampling, OTLP endpoint, Actuator exposure và module observability.
2. Đưa cấu hình nghiệp vụ riêng vào @ConfigurationProperties type có validation.
3. Bật configuration metadata processor để IDE và reviewer nhận biết property hợp lệ.
4. Tạo application.yaml cho default và application-prod.yaml cho khác biệt không nhạy cảm.
5. Tạo manifest minh họa cung cấp SPRING_PROFILES_ACTIVE, SPRING_DATASOURCE_URL và Secret reference; không ghi credential thật.
6. Nếu dùng mounted secret files, cấu hình spring.config.import với configtree: và xác minh property binding.
7. Expose /actuator/env và /actuator/configprops chỉ trong môi trường thử nghiệm có bảo vệ; xác nhận values được sanitize.
8. Cố ý đặt một property khác nhau ở file và environment variable; xác minh nguồn nào thắng bằng /actuator/env/{property}.
9. Thay đổi ConfigMap trong môi trường thử nghiệm và quan sát process có nhận giá trị mới hay cần restart.
10. Tạo CI check xác nhận property keys, validation, manifest render và documentation inventory cùng thay đổi.
11. Thử một key sai hoặc thiếu và xác nhận ứng dụng fail startup với thông báo có thể hành động.
12. Thực hiện rollout/rollback thử nghiệm, ghi image/config revision và kết quả xác minh.
13. Đối chiếu /actuator/modulith, module metrics và trace exporter để chắc chắn tài liệu observability khớp cấu hình đang chạy.

Mẫu bảng nghiệm thu:

| Kiểm tra | Kết quả cần đạt |
| --- | --- |
| Configuration inventory | Có property, nguồn, owner, scope và reload behavior |
| Property precedence | Xác định được nguồn thắng khi có override |
| Profile | Profile active khớp deployment |
| Validation | Key thiếu/sai làm startup fail rõ ràng |
| Secret handling | Chỉ ghi reference, không lưu secret value |
| Actuator | env/configprops được bảo vệ và sanitize |
| Drift check | Phát hiện khác biệt giữa Git, manifest và runtime |
| Rollout | Xác minh effective config sau deploy |
| Rollback | Application/config revision được khôi phục đồng bộ |
| Modulith observability | Module endpoint, metrics và traces đúng cấu hình production |

**Tiêu chí hoàn thành:** có thể giải thích nguồn tạo ra giá trị production, xác minh được giá trị đã bind, phát hiện drift, xử lý secret đúng cách và cập nhật tài liệu cùng release revision.

## 18. Ghi nhớ

~~~text
DECLARED CONFIG
  application.yaml + @ConfigurationProperties
        ↓
DEPLOYED CONFIG
  profile + environment + ConfigMap + Secret reference
        ↓
EFFECTIVE CONFIG
  Spring Environment + bound configuration beans
        ↓
RUNTIME VERIFICATION
  Actuator + metrics + logs + traces
        ↓
DOCUMENTATION UPDATE
  owner + revision + verification date + rollback
~~~

Tài liệu vận hành phải cho biết **property nào được dùng, lấy từ nguồn nào, giá trị hiệu lực được xác minh ra sao, ai sở hữu và thay đổi có cần restart hay không**. Không ghi secret value, không giả định file cấu hình là nguồn cuối cùng và không để hotfix production nằm ngoài source of truth.

Với Spring Modulith, cần ghi thêm cấu trúc module, Insight/Actuator support, module observations, event metrics và tracing exporter theo đúng version. Khi cấu hình production đổi, cập nhật tài liệu trong cùng change/release và xác minh runtime sau deployment.

### Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — property source precedence, profile files, environment variables, configuration trees và type-safe binding.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) — active/default profiles và profile-specific configuration.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — endpoint exposure, access control và sanitization.
- [Spring Boot — Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/index.html) — Actuator operations và runtime inspection.
- [Spring Boot — Configuration Metadata Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html) — sinh metadata cho @ConfigurationProperties.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Insight starter, Modulith Actuator và observability.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/) — quản lý cấu hình không nhạy cảm.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) — cung cấp dữ liệu nhạy cảm cho workload.

> **Lưu ý phiên bản:** property precedence, endpoint Actuator, cấu hình validation và tracing exporter có thể thay đổi theo Spring Boot/Spring Modulith version. Đối chiếu reference guide của đúng version production trước khi sửa runbook. Bài được soạn trong STEP 4; Content QA chuyên môn thuộc bước riêng.

> **Lưu ý phiên bản:** property precedence, tên endpoint, show-values, starter và tracing exporter có thể thay đổi theo Spring Boot/Spring Modulith version. Đối chiếu reference guide của đúng version production; không sao chép property từ tài liệu version khác. Bài được soạn trong STEP 4; Content QA chuyên môn thuộc bước riêng.
