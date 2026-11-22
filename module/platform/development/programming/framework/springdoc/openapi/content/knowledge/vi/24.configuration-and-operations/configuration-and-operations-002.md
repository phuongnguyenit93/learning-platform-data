# Ghi đè cấu hình theo profile và biến môi trường

Một ứng dụng Spring Boot thường chạy ở nhiều môi trường như local, test, staging và production. Mỗi môi trường có thể dùng cổng, URL dịch vụ, mức log và chính sách công bố tài liệu API khác nhau. Spring Boot hỗ trợ tách cấu hình theo profile và ghi đè thuộc tính bằng biến môi trường hoặc tham số khởi động.

Với `springdoc-openapi`, cách này giúp bật Swagger UI khi phát triển, đổi đường dẫn tài liệu ở staging hoặc tắt endpoint tài liệu trong production. Cấu hình môi trường cần được thiết kế có chủ đích: cùng một thuộc tính có thể được khai báo ở nhiều nơi, nhưng giá trị cuối cùng phụ thuộc thứ tự ưu tiên của các nguồn cấu hình.

## 1. Cấu hình chung trong `application.yml`

Đặt những giá trị dùng chung cho mọi môi trường trong `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
    disable-swagger-default-url: true

logging:
  level:
    org.springdoc: INFO
```

Trong ví dụ, OpenAPI JSON được công bố tại `/v3/api-docs`, Swagger UI vào từ `/swagger-ui.html`, và URL mặc định Petstore của Swagger UI bị tắt. Đây là cấu hình nền; profile hoặc biến môi trường có thể ghi đè từng thuộc tính mà không cần sửa file này.

Nên đặt ở cấu hình chung những giá trị thực sự giống nhau giữa các môi trường. Các URL nội bộ, credential, thông tin database và chính sách bảo mật phụ thuộc môi trường nên được đưa vào nguồn cấu hình riêng.

## 2. Tạo file cấu hình theo profile

Spring Boot tự nạp file profile-specific có dạng `application-{profile}.yml`. Ví dụ:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
```

File `application-local.yml` có thể bật đầy đủ tài liệu để phát triển:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true

logging:
  level:
    org.springdoc: DEBUG
```

File `application-prod.yml` có thể tắt Swagger UI và endpoint OpenAPI nếu production không cần công bố tài liệu:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false

logging:
  level:
    org.springdoc: WARN
```

Nếu production cần tài liệu JSON cho một hệ thống nội bộ, có thể giữ `springdoc.api-docs.enabled: true`, tắt riêng `springdoc.swagger-ui.enabled: false`, rồi bảo vệ endpoint JSON/YAML bằng Spring Security hoặc gateway. Tắt giao diện không đồng nghĩa endpoint OpenAPI đã bị tắt; hai thuộc tính có mục đích riêng.

## 3. Kích hoạt profile

Có thể chọn profile bằng biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Hoặc truyền tham số khi chạy JAR:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Khi profile `prod` hoạt động, Spring Boot nạp cấu hình chung rồi áp dụng các giá trị trong `application-prod.yml` theo thứ tự ưu tiên của Config Data. Nếu nhiều profile được kích hoạt, các file tương ứng đều có thể được nạp; khi cùng khai báo một thuộc tính, thứ tự profile và thứ tự nguồn cấu hình ảnh hưởng giá trị cuối cùng. Tránh kích hoạt đồng thời các profile có chính sách mâu thuẫn mà không kiểm tra kết quả.

`spring.profiles.active` là thuộc tính chọn profile, không phải thuộc tính nghiệp vụ. Không đặt nó trong một file `application-{profile}.yml` để kích hoạt chính profile đó. Hãy chọn profile từ cấu hình không gắn profile, biến môi trường, system property hoặc command line.

## 4. Dùng `spring.config.activate.on-profile` trong một file YAML

Nếu muốn gom cấu hình nhiều môi trường trong một file, Spring Boot hỗ trợ multi-document YAML bằng dấu phân cách `---`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false

logging:
  level:
    org.springdoc: WARN
```

Document đầu tiên không gắn profile nên được áp dụng chung. Document thứ hai chỉ được kích hoạt khi profile `prod` hoạt động. Cách này phù hợp với ứng dụng nhỏ, nhưng khi cấu hình từng môi trường lớn dần, file `application-{profile}.yml` riêng thường dễ đọc và review hơn.

Không khai báo `spring.profiles.active`, `spring.profiles.include` hoặc `spring.profiles.group` bên trong document đã kích hoạt bằng `spring.config.activate.on-profile`. Các thuộc tính lựa chọn profile phải nằm trong document không gắn profile.

## 5. Profile group cho một môi trường gồm nhiều cấu hình

Một môi trường production có thể cần nhiều nhóm cấu hình nhỏ, chẳng hạn database production, quan sát hệ thống và chính sách tài liệu. Có thể gom chúng thành profile group:

```yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-observability
        - prod-docs
```

Khi kích hoạt `production`, Spring Boot cũng kích hoạt các profile thành viên. Các file tương ứng có thể giữ trách nhiệm riêng:

```text
application-prod-database.yml
application-prod-observability.yml
application-prod-docs.yml
```

Ví dụ `application-prod-docs.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
```

Profile group giúp chọn một môi trường bằng một tên duy nhất trong pipeline, đồng thời tách cấu hình theo mối quan tâm. Khai báo group trong cấu hình không gắn profile, không đặt group bên trong file thành viên profile-specific.

## 6. Thứ tự ưu tiên của các nguồn cấu hình

Spring Boot có nhiều nguồn cung cấp cùng một property. Khi một thuộc tính xuất hiện ở nhiều nơi, nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị hiệu lực. Một cách ghi nhớ phổ biến, từ thấp lên cao, là:

1. Giá trị mặc định được khai báo trong ứng dụng.
2. File cấu hình đóng gói trong JAR như `application.yml`.
3. File cấu hình profile-specific như `application-prod.yml`.
4. File cấu hình bên ngoài ứng dụng được Spring Boot nạp.
5. Biến môi trường của hệ điều hành.
6. Java system properties, ví dụ `-Dspringdoc.api-docs.enabled=false`.
7. `SPRING_APPLICATION_JSON`.
8. Tham số command line, ví dụ `--springdoc.api-docs.enabled=false`.

Đây là sơ đồ rút gọn để hiểu các nguồn thường gặp; thứ tự đầy đủ còn có test properties, Devtools, JNDI và các nguồn cấu hình khác. Với Config Data, vị trí file, profile đang hoạt động và thứ tự import cũng ảnh hưởng kết quả. Khi cần kết luận chính xác, kiểm tra tài liệu Spring Boot đúng phiên bản và giá trị runtime trong môi trường triển khai.

Ví dụ `application-prod.yml` bật API docs:

```yaml
springdoc:
  api-docs:
    enabled: true
```

Nhưng môi trường production đặt biến:

```bash
SPRINGDOC_API_DOCS_ENABLED=false
```

Giá trị cuối cùng là `false` vì biến môi trường có độ ưu tiên cao hơn file Config Data. Đây là hành vi ghi đè có chủ đích, không phải Spring Boot bỏ qua profile.

## 7. Ánh xạ property sang tên biến môi trường

Spring Boot relaxed binding cho phép chuyển tên property sang dạng biến môi trường theo quy tắc:

- Chuyển tên thành chữ hoa.
- Thay dấu chấm (`.`) bằng dấu gạch dưới (`_`).
- Bỏ dấu gạch ngang (`-`).
- Giữ dấu gạch dưới làm ký tự phân cách.

Ví dụ:

| Property | Environment variable |
| --- | --- |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `springdoc.api-docs.enabled` | `SPRINGDOC_API_DOCS_ENABLED` |
| `springdoc.api-docs.path` | `SPRINGDOC_API_DOCS_PATH` |
| `springdoc.swagger-ui.enabled` | `SPRINGDOC_SWAGGER_UI_ENABLED` |
| `springdoc.swagger-ui.path` | `SPRINGDOC_SWAGGER_UI_PATH` |
| `springdoc.swagger-ui.disable-swagger-default-url` | `SPRINGDOC_SWAGGER_UI_DISABLE_SWAGGER_DEFAULT_URL` |

Ví dụ triển khai container chỉ cần thay biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8081
SPRINGDOC_API_DOCS_ENABLED=true
SPRINGDOC_API_DOCS_PATH=/internal/openapi
SPRINGDOC_SWAGGER_UI_ENABLED=false
```

Ứng dụng dùng profile `prod`, chạy cổng `8081`, công bố OpenAPI JSON ở path nội bộ `/internal/openapi` và tắt Swagger UI. Endpoint tài liệu vẫn cần cơ chế kiểm soát truy cập nếu chỉ dành cho hệ thống nội bộ.

Với property dạng list hoặc map, cách đặt tên biến môi trường có quy tắc chỉ số riêng; không nên tự đoán tên biến cho cấu trúc phức tạp. Nếu cần cấu hình nhiều `springdoc.group-configs`, file YAML hoặc file cấu hình ngoài thường dễ kiểm soát và review hơn.

## 8. Ghi đè bằng command line và `SPRING_APPLICATION_JSON`

Tham số command line hữu ích khi chạy thủ công hoặc trong một job triển khai:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --springdoc.api-docs.enabled=true \
  --springdoc.swagger-ui.enabled=false \
  --springdoc.api-docs.path=/internal/openapi
```

Nếu cần truyền một nhóm property dưới dạng JSON, có thể dùng `SPRING_APPLICATION_JSON`:

```bash
SPRING_APPLICATION_JSON='{"springdoc":{"api-docs":{"enabled":true,"path":"/internal/openapi"},"swagger-ui":{"enabled":false}}}' \
SPRING_PROFILES_ACTIVE=prod \
java -jar app.jar
```

JSON phải là JSON hợp lệ và tên property phải khớp cấu trúc Spring Boot. Tránh đặt bí mật hoặc token vào command line hay JSON nếu chúng có thể xuất hiện trong process list, log hoặc thông tin chẩn đoán của nền tảng triển khai.

Không nên dùng quá nhiều cơ chế ghi đè cùng lúc cho một property. Nếu file YAML, biến môi trường, JSON và command line đều đặt cùng một giá trị, việc tìm nguồn gây ra cấu hình cuối cùng sẽ khó hơn. Hãy chọn một nguồn cấu hình có chủ đích cho mỗi môi trường.

## 9. Nạp cấu hình ngoài JAR

Có thể đặt cấu hình riêng bên ngoài artifact để thay đổi mà không build lại ứng dụng. Ví dụ thư mục triển khai:

```text
/opt/store-service/
  app.jar
  config/
    application.yml
    application-prod.yml
```

Spring Boot tự tìm một số vị trí cấu hình chuẩn bên ngoài. Có thể bổ sung vị trí bằng `spring.config.additional-location`:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/store-service/ \
SPRING_PROFILES_ACTIVE=prod \
java -jar /opt/store-service/app.jar
```

`spring.config.additional-location` thêm vị trí tìm kiếm bên cạnh các vị trí mặc định. Nếu dùng `spring.config.location`, các vị trí mặc định bị thay thế; cần khai báo đủ những nơi ứng dụng vẫn cần đọc. Khi chỉ muốn bổ sung file triển khai bên ngoài, `additional-location` thường ít gây bất ngờ hơn.

Tiền tố `optional:` cho phép ứng dụng khởi động nếu vị trí không tồn tại. Chỉ dùng khi cấu hình đó thực sự không bắt buộc; với file chứa thiết lập kết nối hoặc chính sách quan trọng, thiếu file nên làm triển khai thất bại rõ ràng thay vì âm thầm dùng giá trị mặc định.

## 10. Quản lý secret tách khỏi cấu hình thông thường

Profile và biến môi trường phù hợp để thay đổi property theo môi trường, nhưng không nên commit mật khẩu, private key, client secret hoặc access token vào Git. Dùng secret manager, Kubernetes Secret, Docker secret hoặc cơ chế cấp phát bí mật của nền tảng.

Ví dụ biến môi trường có thể tham chiếu credential do hệ thống triển khai cấp:

```bash
SPRING_DATASOURCE_USERNAME=store_app
SPRING_DATASOURCE_PASSWORD=<value-provided-by-secret-manager>
```

Trong cấu hình ứng dụng, chỉ tham chiếu property:

```yaml
spring:
  datasource:
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
```

Không ghi giá trị secret thật vào ví dụ, file profile hoặc tài liệu OpenAPI. Biến môi trường cũng có thể bị lộ qua quyền đọc process, log hoặc công cụ chẩn đoán; với môi trường có yêu cầu bảo mật cao, ưu tiên cơ chế mount secret hoặc secret manager tích hợp.

## 11. Cấu hình theo profile cho springdoc

Một ma trận đơn giản có thể như sau:

| Môi trường | API docs JSON/YAML | Swagger UI | Mục đích |
| --- | --- | --- | --- |
| `local` | Bật | Bật | Phát triển và thử API. |
| `test` | Bật khi test hợp đồng cần dùng | Tùy nhu cầu | Kiểm tra tài liệu và tích hợp. |
| `staging` | Bật | Bật có kiểm soát | QA và review API trước phát hành. |
| `prod` | Tắt hoặc bật có bảo vệ | Thường tắt hoặc giới hạn truy cập | Giảm bề mặt công bố tài liệu. |

Ví dụ `application-staging.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /docs
```

Ví dụ `application-prod.yml` cho trường hợp pipeline nội bộ vẫn cần lấy JSON:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /internal/openapi
  swagger-ui:
    enabled: false
```

Trong trường hợp production giữ API docs, hãy bảo vệ `/internal/openapi` và các biến thể JSON/YAML tương ứng bằng Spring Security hoặc gateway. Đổi path không phải biện pháp xác thực; một URL khó đoán vẫn có thể bị phát hiện hoặc gọi trực tiếp.

## 12. Xác minh cấu hình hiệu lực

Khi ứng dụng chạy sai môi trường hoặc springdoc không dùng giá trị mong muốn, kiểm tra theo thứ tự:

1. Xác nhận profile đang hoạt động từ log khởi động hoặc cấu hình triển khai (`SPRING_PROFILES_ACTIVE`, command line).
2. Xác nhận file `application-{profile}.yml` được đóng gói hoặc mount đúng vị trí.
3. Kiểm tra tên biến môi trường theo quy tắc relaxed binding, đặc biệt dấu gạch ngang và dấu chấm.
4. Kiểm tra command line, Java system properties và `SPRING_APPLICATION_JSON` có ghi đè property hay không.
5. Gọi endpoint OpenAPI thực tế để xác nhận path và trạng thái bật/tắt.
6. Kiểm tra Swagger UI riêng; UI có thể bị tắt trong khi JSON vẫn được bật.
7. Nếu có Spring Boot Actuator, dùng `env` hoặc `configprops` trong môi trường được bảo vệ để xem nguồn cấu hình và giá trị đã bind. Không công khai các endpoint này vì chúng có thể tiết lộ thông tin cấu hình.
8. Kiểm tra log khi khởi động để phát hiện YAML sai cú pháp, profile không tồn tại hoặc config location không được nạp.

Không chỉ dựa vào việc file YAML có chứa giá trị mong muốn. Điều cần xác nhận là property hiệu lực sau khi tất cả nguồn cấu hình được hợp nhất.

## 13. Kiểm thử profile và biến môi trường

Có thể dùng `@ActiveProfiles` để kiểm tra cấu hình profile trong Spring Boot test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionDocsConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void disablesSwaggerUiInProductionProfile() {
        assertThat(environment.getProperty(
            "springdoc.swagger-ui.enabled", Boolean.class
        )).isFalse();
    }
}
```

Test này giả định `application-prod.yml` đặt `springdoc.swagger-ui.enabled: false`. Nó xác nhận giá trị được nạp trong test context, nhưng không thay thế smoke test trên artifact/container thực tế.

Với môi trường triển khai, nên có smoke test sau khi khởi động:

- Profile đúng được kích hoạt.
- Cổng và context path đúng.
- Endpoint `/v3/api-docs` hoặc path tùy chỉnh có trạng thái mong đợi.
- Swagger UI được bật/tắt theo chính sách.
- Nếu tài liệu được giữ trong production, truy cập không có quyền bị từ chối và người có quyền tải được.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Luôn dùng cấu hình local khi deploy | `SPRING_PROFILES_ACTIVE` chưa được đặt hoặc sai tên | Kiểm tra biến môi trường và log profile đang hoạt động. |
| Profile được kích hoạt nhưng property không đổi | File profile-specific không được nạp hoặc đặt sai tên | Dùng đúng `application-prod.yml` và vị trí Config Data. |
| YAML có giá trị nhưng runtime vẫn dùng giá trị khác | Biến môi trường, system property hoặc command line ghi đè | Kiểm tra nguồn có độ ưu tiên cao hơn. |
| `SPRINGDOC_API_DOCS_ENABLED` không có tác dụng | Tên biến sai, app dùng property khác hoặc dependency không hỗ trợ thuộc tính | Kiểm tra relaxed binding và phiên bản springdoc. |
| Swagger UI tắt nhưng `/v3/api-docs` vẫn truy cập được | Chỉ tắt `springdoc.swagger-ui.enabled` | Tắt riêng `springdoc.api-docs.enabled` hoặc bảo vệ endpoint nếu cần. |
| API docs tắt nhưng Swagger UI vẫn còn tài nguyên tĩnh | Chỉ tắt API docs, chưa tắt UI | Đặt cả `springdoc.swagger-ui.enabled: false` nếu muốn tắt giao diện. |
| `spring.config.location` làm mất cấu hình mặc định | Thuộc tính này thay thế các vị trí mặc định | Dùng `spring.config.additional-location` khi muốn bổ sung. |
| Ứng dụng khởi động dù thiếu file cấu hình quan trọng | Dùng `optional:` cho vị trí bắt buộc | Bỏ `optional:` để fail fast khi thiếu cấu hình. |
| Test profile cho kết quả khác container | Test không dùng cùng biến môi trường hoặc config mount như production | Thêm smoke test với artifact và cấu hình triển khai thực tế. |
| Secret xuất hiện trong Git hoặc log | Đặt bí mật trực tiếp trong YAML/command line | Chuyển sang secret manager và kiểm soát quyền đọc cấu hình. |

## 15. Nguyên tắc áp dụng

- Đặt giá trị dùng chung trong `application.yml`, giá trị riêng trong `application-{profile}.yml`.
- Kích hoạt profile từ biến môi trường, system property hoặc command line.
- Dùng `spring.config.activate.on-profile` cho multi-document YAML; không đặt thuộc tính chọn profile trong document profile-specific.
- Dùng profile group khi một môi trường cần kích hoạt nhiều nhóm cấu hình.
- Hiểu thứ tự ưu tiên trước khi điều tra property bị ghi đè.
- Ánh xạ biến môi trường theo relaxed binding; không tự đoán tên biến cho list/map phức tạp.
- Dùng `spring.config.additional-location` để bổ sung cấu hình ngoài JAR; chỉ dùng `spring.config.location` khi muốn thay thế vị trí mặc định.
- Không commit secret; lấy credential từ secret manager hoặc nền tảng triển khai.
- Tách `springdoc.api-docs.enabled` khỏi `springdoc.swagger-ui.enabled` và bảo vệ endpoint nếu vẫn công bố tài liệu.
- Kiểm tra property hiệu lực, endpoint thực tế và chính sách truy cập sau khi deploy.

Profile giúp chọn tập cấu hình theo môi trường; biến môi trường và command line giúp nền tảng triển khai ghi đè giá trị mà không sửa artifact. Khi hiểu thứ tự ưu tiên, cách relaxed binding và ranh giới giữa API docs với Swagger UI, đội vận hành có thể bật tài liệu ở local/staging, kiểm soát tài liệu production và tránh cấu hình sai hoặc lộ bí mật.

## Tài liệu tham khảo

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot – Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Springdoc OpenAPI – Properties and Configuration](https://springdoc.org/)
