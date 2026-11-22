# Ghi nhận cấu hình hiệu lực và đối chiếu đặc tả sau khởi động

Một file `application.yml` chứa giá trị mong muốn chưa chứng minh ứng dụng đang chạy với giá trị đó. Spring Boot có thể nhận cấu hình từ file đóng gói, file bên ngoài, profile, biến môi trường, system property, `SPRING_APPLICATION_JSON` và tham số command line. Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị trong file mà người phát triển đang xem.

Với `springdoc-openapi`, sai lệch cấu hình có thể làm endpoint tài liệu bị tắt, đổi URL, thiếu operation hoặc sinh đặc tả khác dự kiến. Cần kiểm tra cấu hình hiệu lực sau khi ứng dụng khởi động, xác định nguồn cung cấp giá trị, rồi đối chiếu với OpenAPI JSON/YAML và Swagger UI thực tế.

## 1. Phân biệt cấu hình được khai báo và cấu hình hiệu lực

Giả sử `application-prod.yml` khai báo:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: false
```

Nhưng container production có biến môi trường:

```bash
SPRINGDOC_API_DOCS_ENABLED=false
SPRINGDOC_API_DOCS_PATH=/internal/openapi
```

Ứng dụng có thể chạy với `springdoc.api-docs.enabled=false` và path `/internal/openapi`, dù file YAML vẫn ghi `true` và `/v3/api-docs`. Khi endpoint không xuất hiện, việc chỉ đọc file YAML sẽ không chỉ ra nguồn ghi đè.

Phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| Giá trị được khai báo | Giá trị có trong một file hoặc nguồn cấu hình cụ thể | Đọc file, biến môi trường hoặc tham số khởi động. |
| Giá trị hiệu lực | Giá trị Spring `Environment` phân giải sau khi hợp nhất các nguồn | Actuator `env` hoặc `Environment` trong ứng dụng. |
| Giá trị đã bind | Giá trị được gắn vào bean `@ConfigurationProperties` | Actuator `configprops`. |

Giá trị hiệu lực và giá trị đã bind thường giống nhau, nhưng hai góc nhìn giúp phát hiện các vấn đề khác nhau. `env` giúp tìm property source và origin; `configprops` giúp xem cấu hình có được bind vào đối tượng cấu hình hay không.

## 2. Bổ sung Spring Boot Actuator

Các endpoint `env`, `configprops` và `conditions` thuộc Spring Boot Actuator. Thêm dependency tương ứng nếu ứng dụng chưa có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Mặc định, chỉ endpoint `health` được expose qua HTTP. Muốn dùng các endpoint chẩn đoán cấu hình, cần expose chúng rõ ràng. Ví dụ cấu hình dành cho môi trường kiểm thử nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops,conditions"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Các endpoint thường có URL:

| Endpoint | Thông tin chính | Dùng để trả lời |
| --- | --- | --- |
| `/actuator/env` | Các property source trong Spring `Environment` | Property đến từ nguồn nào? |
| `/actuator/env/{property}` | Thông tin của một property cụ thể | Giá trị hiệu lực và origin của property này là gì? |
| `/actuator/configprops` | Các bean `@ConfigurationProperties` đã bind | Cấu hình đã được bind vào bean chưa, giá trị nào đang có? |
| `/actuator/conditions` | Kết quả điều kiện auto-configuration | Vì sao một cấu hình tự động được bật hoặc không được bật? |
| `/actuator/mappings` | Các request mapping đã đăng ký | Endpoint tài liệu có mapping trong ứng dụng không? |

Endpoint `mappings` hữu ích khi cần xác nhận đường dẫn thực tế, nhưng không phải endpoint chuyên kiểm tra nội dung OpenAPI. Chỉ expose khi có nhu cầu chẩn đoán cụ thể.

## 3. Expose endpoint không đồng nghĩa cho phép truy cập công khai

Actuator phân biệt việc endpoint được tạo, được expose và được phép truy cập. Một endpoint chỉ dùng được khi nó được bật, được expose qua HTTP/JMX tương ứng và request vượt qua chính sách bảo mật.

Trong ví dụ trên, `include` chỉ chọn các endpoint được công bố. Nếu ứng dụng có Spring Security, hãy bảo vệ các endpoint chẩn đoán bằng quyền vận hành hoặc chỉ cho phép truy cập từ mạng quản trị. Không mở `env` và `configprops` trên Internet chỉ để tiện kiểm tra.

Các response `env` và `configprops` có thể tiết lộ tên property, cấu trúc cấu hình, đường dẫn file, host dịch vụ hoặc thông tin nhạy cảm. Spring Boot hiện hành mặc định che giá trị nhạy cảm của các endpoint này. Tuy vậy, không nên dựa vào sanitization như lớp bảo vệ duy nhất; hãy giới hạn exposure và xác thực người truy cập.

Nếu cần cho phép người có quyền xem giá trị đã được lọc, có thể cấu hình theo role ở các phiên bản Spring Boot hỗ trợ `show-values`:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: OPS
    configprops:
      show-values: when-authorized
      roles: OPS
```

`when-authorized` chỉ hiển thị giá trị chưa bị sanitization cho người đã xác thực và có role được chỉ định. Một `SanitizingFunction` tùy chỉnh vẫn có thể tiếp tục che giá trị. Với môi trường không cần xem giá trị, giữ `show-values: never`. Hãy kiểm tra tài liệu đúng phiên bản Spring Boot vì khả năng và tên thuộc tính Actuator có thể thay đổi theo phiên bản.

## 4. Dùng `/actuator/env` để tìm nguồn ghi đè

Khi một property không có giá trị như mong đợi, truy vấn riêng property đó thay vì đọc toàn bộ `env`:

```bash
curl -u ops https://service.example.com/actuator/env/springdoc.api-docs.enabled
curl -u ops https://service.example.com/actuator/env/springdoc.api-docs.path
curl -u ops https://service.example.com/actuator/env/springdoc.swagger-ui.enabled
```

`curl -u ops` sẽ yêu cầu nhập mật khẩu tương tác trong terminal nếu chưa cung cấp. Dùng cơ chế xác thực được tổ chức cho phép; không ghi mật khẩu hoặc token thật vào lệnh lưu trong shell history hay tài liệu.

Response của `env` thường cho biết:

- Property được phân giải thành giá trị nào, nếu quyền hiển thị cho phép.
- Các property source có chứa property đó.
- Tên nguồn, ví dụ `systemEnvironment`, `systemProperties`, `commandLineArgs` hoặc nguồn Config Data.
- Origin hoặc vị trí khai báo, ví dụ tên file và dòng cấu hình khi có metadata.

Cấu trúc JSON chi tiết có thể thay đổi theo phiên bản Spring Boot. Hãy tìm property name, `propertySources` và origin thay vì phụ thuộc vào thứ tự hoặc tên field phụ của một response mẫu.

Ví dụ, nếu `springdoc.api-docs.enabled` có origin từ `systemEnvironment`, hãy kiểm tra biến `SPRINGDOC_API_DOCS_ENABLED` trong deployment. Nếu origin đến từ `commandLineArgs`, kiểm tra tham số `--springdoc.api-docs.enabled=...` ở lệnh chạy hoặc cấu hình container.

`/actuator/env` cho biết Spring đang nhìn thấy gì. Nó không tự giải thích vì sao một bean cụ thể được tạo hoặc không được tạo; dùng `configprops` và `conditions` cho hai câu hỏi đó.

## 5. Dùng `/actuator/configprops` để kiểm tra binding

`configprops` hiển thị các bean được đánh dấu `@ConfigurationProperties` và thông tin binding. Khi điều tra cấu hình springdoc, tìm prefix `springdoc` hoặc nhóm property tương ứng trong response:

```bash
curl -u ops https://service.example.com/actuator/configprops
```

Kiểm tra:

- Bean cấu hình có xuất hiện không.
- Prefix có đúng không.
- Thuộc tính đã bind có giá trị phù hợp không.
- Metadata `inputs` hoặc origin (nếu phiên bản cung cấp) cho biết nguồn đầu vào nào được dùng.
- Có thuộc tính bị bỏ qua do tên sai, kiểu không chuyển đổi được hoặc cấu hình không được nạp không.

Không phải mọi property đều nhất thiết xuất hiện trong `configprops`: endpoint này tập trung vào bean `@ConfigurationProperties`, còn `env` phản ánh property source trong `Environment`. Nếu một property có trong `env` nhưng không thấy ở `configprops`, kiểm tra xem nó có thuộc prefix/bean cấu hình được bind hay không và phiên bản thư viện có hỗ trợ property đó không.

Đối với springdoc, đối chiếu các thuộc tính quan trọng:

| Property | Tác động cần xác nhận |
| --- | --- |
| `springdoc.api-docs.enabled` | Endpoint OpenAPI có được bật hay không. |
| `springdoc.api-docs.path` | Base path của OpenAPI JSON. |
| `springdoc.api-docs.version` | Phiên bản OpenAPI được ghi trong trường `openapi` của document. |
| `springdoc.packages-to-scan` | Package controller được đưa vào tài liệu. |
| `springdoc.paths-to-match` | Path được chọn để mô tả. |
| `springdoc.paths-to-exclude` | Path bị loại khỏi tài liệu. |
| `springdoc.swagger-ui.enabled` | Giao diện Swagger UI có được bật hay không. |
| `springdoc.swagger-ui.path` | Đường dẫn vào giao diện. |

Danh sách property phụ thuộc phiên bản springdoc. Đối chiếu với tài liệu property của đúng nhánh đang dùng; không giả định property mới nhất luôn có trong một ứng dụng cũ.

## 6. Dùng `/actuator/conditions` để hiểu auto-configuration

`conditions` cho biết các điều kiện của cấu hình tự động nào đã match hoặc không match. Đây là nơi hữu ích khi:

- Starter springdoc có trong dependency nhưng auto-configuration không được kích hoạt.
- Ứng dụng dùng WebFlux nhưng lại nạp starter WebMVC, hoặc ngược lại.
- Một bean tùy chỉnh khiến auto-configuration mặc định lùi lại.
- Điều kiện classpath, property hoặc bean hiện có không thỏa yêu cầu.

Gọi endpoint:

```bash
curl -u ops https://service.example.com/actuator/conditions
```

Tìm các mục có liên quan đến springdoc hoặc OpenAPI trong positive matches và negative matches. Tên lớp auto-configuration và cấu trúc report phụ thuộc phiên bản. Đọc phần condition message để biết điều kiện nào đã được thỏa mãn hoặc còn thiếu.

`conditions` không phải danh sách mọi property hiệu lực và cũng không chứng minh tài liệu cuối cùng đúng. Ví dụ, auto-configuration có thể match nhưng `paths-to-match` lọc hết controller. Khi đó cần kiểm tra `env`, `configprops` và OpenAPI document.

## 7. Kiểm tra cấu hình hiệu lực ngay trong ứng dụng

Trong code hoặc một chẩn đoán tạm thời, có thể đọc `Environment` để xem giá trị mà Spring phân giải:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class OpenApiConfigurationProbe implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(
        OpenApiConfigurationProbe.class
    );

    private final Environment environment;

    OpenApiConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        Boolean apiDocsEnabled = environment.getProperty(
            "springdoc.api-docs.enabled", Boolean.class, true
        );
        String apiDocsPath = environment.getProperty(
            "springdoc.api-docs.path", "/v3/api-docs"
        );
        Boolean swaggerUiEnabled = environment.getProperty(
            "springdoc.swagger-ui.enabled", Boolean.class, true
        );

        log.info("OpenAPI enabled: {}", apiDocsEnabled);
        log.info("OpenAPI path: {}", apiDocsPath);
        log.info("Swagger UI enabled: {}", swaggerUiEnabled);
    }
}
```

Ví dụ này chỉ log các flag và path không chứa bí mật. Không dump toàn bộ `Environment`, `System.getenv()` hoặc `configprops` vào log: chúng có thể chứa credential, token, URL nội bộ và thông tin hạ tầng. Sau khi chẩn đoán, bỏ probe tạm hoặc giới hạn nó ở profile chẩn đoán.

Giá trị mặc định trong `getProperty(..., defaultValue)` chỉ là fallback của đoạn code probe. Nó không thay thế cấu hình mặc định thật của springdoc và không chứng minh property đã được bind vào bean. Hãy đối chiếu với Actuator và document runtime.

## 8. Đối chiếu endpoint OpenAPI sau khi ứng dụng khởi động

Sau khi biết cấu hình hiệu lực, gọi endpoint thực tế. Ví dụ:

```bash
curl -i https://service.example.com/v3/api-docs
curl -i https://service.example.com/v3/api-docs.yaml
curl -i https://service.example.com/v3/api-docs/swagger-config
```

Nếu `springdoc.api-docs.path` đã đổi, thay URL bằng path hiệu lực. Nếu ứng dụng có context path, management port hoặc reverse proxy prefix, dùng URL mà client thực sự truy cập.

Đối chiếu response:

| Cấu hình hiệu lực | Kết quả cần kiểm tra |
| --- | --- |
| `springdoc.api-docs.enabled=true` | Endpoint OpenAPI được đăng ký và có thể trả document nếu không bị security/proxy chặn. |
| `springdoc.api-docs.enabled=false` | Endpoint OpenAPI không được cung cấp theo cấu hình springdoc; kiểm tra status và mapping thực tế. |
| `springdoc.api-docs.path=/internal/openapi` | JSON document ở base path đã cấu hình; các URL YAML và Swagger UI config phải theo đúng base path/phiên bản. |
| `springdoc.api-docs.version` | Trường `openapi` trong JSON phản ánh phiên bản đặc tả được cấu hình và hỗ trợ. |
| `springdoc.packages-to-scan` | Operation chỉ đến từ package được chọn. |
| `springdoc.paths-to-match` / `paths-to-exclude` | Các path xuất hiện/biến mất đúng theo filter. |
| `springdoc.swagger-ui.enabled=false` | Swagger UI bị tắt, nhưng OpenAPI JSON có thể vẫn hoạt động. |

Không kết luận endpoint bị tắt chỉ từ một response `401`, `403` hoặc `404`. `401`/`403` thường cho biết request bị bảo vệ; `404` có thể do sai path, proxy rewrite hoặc endpoint không được đăng ký. Kết hợp `env`, `conditions`, `mappings` và log khởi động để xác định nguyên nhân.

## 9. Đối chiếu nội dung OpenAPI document

Khi document trả `200`, tiếp tục kiểm tra nội dung thay vì dừng ở HTTP status. Một checklist cơ bản:

1. `openapi`: phiên bản OpenAPI đúng với `springdoc.api-docs.version` và phiên bản thư viện.
2. `info`: title, version và description đúng môi trường hoặc group.
3. `servers`: scheme, host, port và prefix công khai đúng với request mà client sẽ gọi.
4. `paths`: các operation cần công bố có mặt; operation nội bộ hoặc bị loại trừ không xuất hiện ngoài ý muốn.
5. `components.schemas`: DTO, enum, format và validation metadata đúng.
6. `components.securitySchemes` và `security`: scheme cùng yêu cầu bảo mật đúng với hợp đồng.
7. `requestBody`, `parameters`, `responses`: media type, required, status code, header và schema đúng.
8. `$ref`: mọi tham chiếu đều trỏ đến component tồn tại.

Ví dụ rút gọn:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Store API",
    "version": "1.0.0"
  },
  "servers": [
    { "url": "https://api.example.com/store" }
  ],
  "paths": {
    "/api/orders": {
      "get": {
        "operationId": "listOrders",
        "responses": {
          "200": { "description": "OK" }
        }
      }
    }
  }
}
```

Đây là ví dụ cấu trúc để đối chiếu, không phải document cố định của mọi ứng dụng. Giá trị `openapi` và cách sinh schema phụ thuộc cấu hình cùng phiên bản springdoc. Hãy kiểm tra response thực tế của service.

## 10. Phân biệt lỗi cấu hình, lỗi auto-configuration và lỗi tài liệu

Một số triệu chứng trông giống nhau nhưng cần kiểm tra ở các nơi khác nhau:

| Triệu chứng | Nơi kiểm tra đầu tiên | Nguyên nhân có thể |
| --- | --- | --- |
| Property trong YAML đúng nhưng endpoint vẫn tắt | `/actuator/env/{property}` | Environment variable, system property hoặc command line ghi đè. |
| Property có trong `env` nhưng bean không nhận | `/actuator/configprops` | Binding sai, prefix khác hoặc property không thuộc bean cấu hình đó. |
| Springdoc auto-configuration không xuất hiện | `/actuator/conditions` | Thiếu starter, sai web stack, điều kiện classpath/bean không thỏa. |
| `/v3/api-docs` trả `404` nhưng `api-docs.enabled=true` | `/actuator/env`, `/actuator/mappings`, proxy | Path tùy chỉnh, context path, security hoặc rewrite sai. |
| `/v3/api-docs` trả `200` nhưng thiếu controller | `paths`, `packages-to-scan`, `paths-to-match` | Filter loại endpoint hoặc controller không được phát hiện. |
| JSON có operation nhưng Swagger UI không mở | `swagger-config`, UI path, Network tab | UI tắt, config URL sai, asset lỗi hoặc security chặn. |
| Document vẫn giống phiên bản trước sau khi đổi code | Log khởi động, process/instance, cache | Đang gọi nhầm instance, artifact cũ hoặc cache OpenAPI. |
| `servers` có host nội bộ hoặc sai prefix | `servers`, forwarded headers, proxy config | Ứng dụng chưa nhận metadata URL công khai. |
| Security scheme đúng nhưng request bị từ chối | Spring Security runtime | Token, role, issuer, audience hoặc rule runtime không đúng. |

## 11. Lưu ý về cache và thay đổi sau khởi động

Springdoc có thể cache OpenAPI document đã tính toán để giảm chi phí tạo đặc tả. Nếu cùng một process vẫn trả document cũ sau khi thay đổi mapping, annotation hoặc dữ liệu cấu hình, kiểm tra:

- Request đang đến đúng instance và đúng artifact vừa triển khai hay không.
- Profile và property source của instance có thực sự thay đổi hay không.
- Có cache ở springdoc, reverse proxy, gateway hoặc CDN hay không.
- Ứng dụng có cần restart để nạp lại cấu hình startup-time hay không.

Property `springdoc.cache.disabled` có thể tắt cache tài liệu trong các phiên bản hỗ trợ, nhưng không nên dùng nó như cơ chế refresh cấu hình production. Thay đổi `application.yml`, biến môi trường hoặc hầu hết cấu hình khởi động không tự cập nhật mọi bean đang chạy. Nếu hệ thống dùng Spring Cloud Config/refresh hoặc cơ chế reload riêng, hãy xác minh property đó có được refresh và bean tiêu thụ nó có hỗ trợ refresh hay không.

Sau khi thay đổi cấu hình startup-time, cách xác minh đáng tin cậy thường là triển khai/restart instance với cấu hình mới, chờ readiness, rồi gọi lại endpoint tài liệu từ đúng địa chỉ public.

## 12. Quy trình kiểm tra sau khởi động

Thực hiện theo trình tự để thu thập bằng chứng từ cấu hình đến document:

1. **Xác nhận instance:** kiểm tra version/build info, pod/container hoặc hostname để chắc chắn đang gọi đúng instance.
2. **Xác nhận profile:** xem log khởi động hoặc `SPRING_PROFILES_ACTIVE` trong cấu hình triển khai.
3. **Kiểm tra Environment:** gọi `/actuator/env/{property}` cho các property springdoc quan trọng và ghi lại property source/origin, không lưu secret.
4. **Kiểm tra binding:** gọi `/actuator/configprops` và xác nhận bean cấu hình nhận đúng giá trị.
5. **Kiểm tra điều kiện:** dùng `/actuator/conditions` nếu nghi ngờ springdoc auto-configuration không được kích hoạt.
6. **Kiểm tra mapping:** dùng `/actuator/mappings` hoặc log startup để xác nhận URL OpenAPI và Swagger UI đã đăng ký.
7. **Tải document:** gọi JSON/YAML theo path hiệu lực và xác nhận HTTP status cùng content type.
8. **Đối chiếu nội dung:** kiểm tra `openapi`, `servers`, `paths`, schema, security và responses.
9. **Kiểm tra giao diện:** gọi `swagger-config`, mở Swagger UI và xác nhận nó tải đúng document.
10. **Lưu bằng chứng:** ghi lại profile, build version, property source không nhạy cảm, endpoint đã kiểm tra và kết quả so sánh.

Không cần expose toàn bộ Actuator cho quy trình này. Chỉ bật endpoint cần thiết trong môi trường chẩn đoán, bảo vệ chúng và tắt/giới hạn exposure sau khi hoàn tất nếu chính sách vận hành yêu cầu.

## 13. Kiểm tra tự động trong CI hoặc smoke test

Có thể kiểm tra OpenAPI document bằng MockMvc trong test context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiStartupContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesExpectedOrdersOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$['paths']['/api/orders']['get']").exists());
    }
}
```

Test trên xác nhận document trong Spring test context. Nó chưa xác nhận biến môi trường của container production, proxy, security hoặc URL public. Vì vậy, sau khi deploy vẫn cần smoke test HTTP từ môi trường gần với client thực tế.

Ví dụ smoke test có thể kiểm tra status và các field quan trọng:

```bash
curl -fsS https://service.example.com/v3/api-docs -o openapi.json
```

Sau đó dùng JSON parser hoặc OpenAPI validator trong pipeline để kiểm tra `openapi`, path bắt buộc, response schema và `$ref`. Tránh chỉ so sánh toàn bộ JSON dạng chuỗi vì thứ tự field hoặc tên component có thể thay đổi giữa phiên bản thư viện.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không truy cập được `/actuator/env` | Chưa thêm Actuator, endpoint chưa expose hoặc security chặn | Kiểm tra dependency, `management.endpoints.web.exposure.include` và quyền truy cập. |
| `/actuator/env` trả giá trị `******` | Sanitization đang che giá trị nhạy cảm | Kiểm tra property source/origin; chỉ cho phép hiển thị giá trị cho role vận hành nếu thực sự cần. |
| Không thấy property trong `configprops` | Property không thuộc bean `@ConfigurationProperties` hoặc chưa bind | Dùng `env` để xác nhận property source và kiểm tra prefix/binding. |
| `/actuator/conditions` không có thông tin mong đợi | Đang đọc nhầm instance, endpoint chưa expose hoặc cấu trúc report khác phiên bản | Xác nhận instance, exposure và tên auto-configuration theo version. |
| OpenAPI path không như file cấu hình | Nguồn có ưu tiên cao hơn ghi đè path | Truy vấn `/actuator/env/springdoc.api-docs.path` và kiểm tra origin. |
| Endpoint docs bị `404` dù enabled là true | Sai path, proxy rewrite, context path hoặc auto-configuration không tạo mapping | Kiểm tra `configprops`, `conditions`, `mappings` và URL public. |
| OpenAPI thiếu operation | Package/path filters hoặc controller chưa được đăng ký | Đối chiếu `packages-to-scan`, `paths-to-match`, `paths-to-exclude` và mappings. |
| Swagger UI tắt nhưng JSON vẫn hoạt động | Hai thuộc tính enable độc lập | Kiểm tra riêng `springdoc.swagger-ui.enabled` và `springdoc.api-docs.enabled`. |
| Document cũ sau triển khai | Nhầm instance, artifact cũ hoặc cache | Kiểm tra build/version, restart và cache ở springdoc/proxy. |
| Actuator lộ thông tin cấu hình | Expose quá rộng hoặc security chưa đúng | Thu hẹp exposure, bảo vệ endpoint và giữ sanitization. |

## 15. Nguyên tắc áp dụng

- Phân biệt giá trị trong file, giá trị hiệu lực trong `Environment` và giá trị đã bind vào bean.
- Dùng `/actuator/env/{property}` để tìm nguồn và origin của property quan trọng.
- Dùng `/actuator/configprops` để xác nhận binding của cấu hình có kiểu.
- Dùng `/actuator/conditions` để chẩn đoán auto-configuration, không dùng nó thay cho kiểm tra property hoặc document.
- Chỉ expose Actuator endpoint cần thiết; bảo vệ bằng mạng quản trị và Spring Security.
- Giữ `show-values: never` nếu không cần xem giá trị; không ghi secret vào log.
- Đối chiếu property springdoc với URL JSON/YAML, Swagger UI và nội dung OpenAPI sau khởi động.
- Kiểm tra `servers`, `paths`, schema, security, response và `$ref`, không chỉ kiểm tra HTTP `200`.
- Xác nhận đúng instance/artifact và xem xét cache trước khi kết luận document không được cập nhật.
- Dùng test context trong CI và smoke test sau triển khai vì hai môi trường không có cùng nguồn cấu hình.

Ghi nhận cấu hình hiệu lực giúp giải thích vì sao ứng dụng đang chạy khác với file cấu hình được commit. `env` chỉ ra nguồn và origin, `configprops` xác nhận binding, còn `conditions` giải thích quyết định auto-configuration. Sau đó, việc tải OpenAPI JSON/YAML và đối chiếu `servers`, `paths`, schema, security cùng Swagger UI xác nhận cấu hình đã tạo ra hợp đồng đúng như mong muốn. Kết hợp kiểm tra Actuator có kiểm soát với smoke test sau khởi động giúp phát hiện sớm sai lệch giữa cấu hình triển khai và tài liệu API thực tế.

## Tài liệu tham khảo

- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Springdoc OpenAPI – Core Configuration Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI – Configuration Properties](https://springdoc.org/properties.html)
