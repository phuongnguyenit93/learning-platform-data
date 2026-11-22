# Tổ chức thuộc tính springdoc trong application.yml hoặc properties

springdoc-openapi dùng cơ chế cấu hình chuẩn của Spring Boot. Các thuộc tính của springdoc được đặt trong application.yml, application.yaml hoặc application.properties, có thể ghi đè theo profile, biến môi trường, system property hay tham số dòng lệnh. Nhờ vậy, cùng một artifact có thể chạy ở local, test, staging và production với cấu hình tài liệu API phù hợp từng môi trường.

Điều quan trọng là tổ chức cấu hình theo hai nhóm:

- **Cấu hình tài liệu OpenAPI:** bật/tắt endpoint JSON, đường dẫn tài liệu, package và path cần quét, nhóm API.
- **Cấu hình giao diện Swagger UI:** bật/tắt giao diện, đường dẫn trang, URL của OpenAPI definition và cách hiển thị.

Không cần tạo một cơ chế cấu hình riêng cho springdoc. Hãy dùng quy tắc property source và profile của Spring Boot, giữ giá trị mặc định trong cấu hình chung, rồi ghi đè đúng những giá trị khác nhau ở từng môi trường.

## 1. Springdoc đọc cấu hình từ Spring Environment

Springdoc sử dụng Spring configuration properties. Các giá trị có thể đến từ YAML, properties, biến môi trường, system properties, tham số dòng lệnh hoặc nguồn cấu hình ngoài được Spring Boot nạp.

Ví dụ một số thuộc tính thường dùng:

| Thuộc tính | Mục đích |
| --- | --- |
| **springdoc.api-docs.enabled** | Bật hoặc tắt endpoint OpenAPI |
| **springdoc.api-docs.path** | Đổi đường dẫn endpoint OpenAPI |
| **springdoc.packages-to-scan** | Giới hạn package được springdoc quét |
| **springdoc.paths-to-match** | Chỉ đưa các path khớp pattern vào tài liệu |
| **springdoc.paths-to-exclude** | Loại path khỏi tài liệu |
| **springdoc.group-configs** | Khai báo nhiều tài liệu theo nhóm |
| **springdoc.swagger-ui.enabled** | Bật hoặc tắt Swagger UI |
| **springdoc.swagger-ui.path** | Đổi đường dẫn trang Swagger UI |
| **springdoc.swagger-ui.displayRequestDuration** | Hiển thị thời gian request trong Try it out |

Các thuộc tính có thể thay đổi theo phiên bản springdoc. Hãy kiểm tra reference đúng phiên bản dependency đang dùng trước khi thêm property mới vào cấu hình.

## 2. Chọn YAML hoặc properties

YAML biểu diễn cấu trúc lồng nhau rõ ràng, phù hợp khi có nhiều thuộc tính springdoc:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  packages-to-scan:
    - com.example.shop.api
  paths-to-match:
    - /api/**
  swagger-ui:
    enabled: true
    path: /docs
    displayRequestDuration: true
~~~

Cùng cấu hình đó trong application.properties:

~~~properties
springdoc.api-docs.enabled=true
springdoc.api-docs.path=/v3/api-docs
springdoc.packages-to-scan=com.example.shop.api
springdoc.paths-to-match=/api/**
springdoc.swagger-ui.enabled=true
springdoc.swagger-ui.path=/docs
springdoc.swagger-ui.displayRequestDuration=true
~~~

Hai định dạng có cùng ý nghĩa khi được Spring Boot nạp. Chọn một định dạng làm chuẩn cho toàn ứng dụng. Nếu cùng một thư mục chứa cả application.properties và application.yml (hoặc application.yaml), file .properties được ưu tiên. Trộn hai định dạng cho cùng nhóm thuộc tính dễ khiến người vận hành đọc nhầm giá trị đang có hiệu lực.

Với YAML, chú ý thụt lề và kiểu dữ liệu. Boolean nên ghi true hoặc false, danh sách nên dùng cú pháp list, không đặt toàn bộ cấu hình thành một chuỗi nếu muốn Spring Boot bind thành cấu trúc.

## 3. Tổ chức cấu hình chung theo nhóm

Một cấu trúc dễ bảo trì là đặt các giá trị dùng chung trong application.yml, sau đó phân nhóm theo springdoc.api-docs, springdoc.swagger-ui và springdoc.group-configs.

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
    version: openapi_3_1
  packages-to-scan:
    - com.example.shop.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
  swagger-ui:
    enabled: true
    path: /docs
    displayRequestDuration: true
    deepLinking: true
~~~

Trong ví dụ:

- api-docs điều khiển endpoint sinh OpenAPI JSON.
- packages-to-scan và paths-to-match xác định phạm vi API được đưa vào tài liệu.
- paths-to-exclude loại các endpoint không nên xuất hiện.
- swagger-ui điều khiển trang giao diện và hành vi hiển thị.

Không đưa mọi thuộc tính vào một danh sách dài không phân nhóm. Khi một property thay đổi, người bảo trì cần nhận ra ngay nó tác động đến tài liệu sinh ra hay đến giao diện người dùng.

## 4. Tách cấu hình theo profile

Spring Boot hỗ trợ file cấu hình theo profile với quy ước application-{profile}.yml hoặc application-{profile}.properties.

Một cách tổ chức phổ biến:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

application.yml chứa giá trị chung:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  packages-to-scan:
    - com.example.shop.api
  paths-to-match:
    - /api/**
  swagger-ui:
    path: /docs
~~~

application-dev.yml bật tài liệu và giao diện cho phát triển:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
    displayRequestDuration: true
~~~

application-test.yml có thể giữ OpenAPI endpoint để kiểm thử hợp đồng, nhưng tắt giao diện không cần thiết:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

application-prod.yml phụ thuộc chính sách công bố tài liệu:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Không có quy tắc bắt buộc production phải tắt OpenAPI. Nếu tài liệu là một phần của cổng developer portal hoặc cần cho đối tác tích hợp, có thể giữ endpoint bật nhưng đặt sau xác thực, phân quyền, gateway hoặc mạng nội bộ. Quyết định phải dựa trên chính sách công bố API.

Kích hoạt profile bằng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=dev
~~~

Hoặc tham số dòng lệnh:

~~~bash
java -jar shop-api.jar --spring.profiles.active=prod
~~~

Nếu bật nhiều profile, profile được liệt kê sau có thể ghi đè giá trị của profile đứng trước. Ví dụ SPRING_PROFILES_ACTIVE=prod,region-eu cho phép application-region-eu.yml ghi đè thuộc tính tương ứng của application-prod.yml.

Không đặt spring.profiles.active trong file cấu hình chỉ được kích hoạt bởi một profile khác. Hãy chọn profile từ môi trường chạy, tham số dòng lệnh hoặc nguồn cấu hình cấp cao hơn.

## 5. Dùng nhiều document trong một YAML

Nếu muốn giữ một file nhưng vẫn phân tách cấu hình theo môi trường, YAML hỗ trợ nhiều document bằng dấu --- và điều kiện spring.config.activate.on-profile.

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: test
springdoc:
  swagger-ui:
    enabled: false

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
~~~

Document đầu tiên luôn được nạp. Document sau chỉ được áp dụng khi profile expression khớp. Cách này phù hợp với cấu hình ngắn; nếu mỗi môi trường có nhiều khác biệt, các file application-{profile}.yml thường dễ đọc và quản lý hơn.

## 6. Hiểu thứ tự ưu tiên khi ghi đè thuộc tính

Spring Boot nạp nhiều PropertySource. Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị từ nguồn thấp hơn. Trong vận hành thông thường, có thể ghi nhớ:

| Nguồn | Ví dụ | Tác động |
| --- | --- | --- |
| Cấu hình đóng gói trong JAR | application.yml | Giá trị mặc định của ứng dụng |
| File theo profile trong JAR | application-prod.yml | Ghi đè cấu hình chung theo profile |
| File cấu hình bên ngoài JAR | ./config/application.yml | Ghi đè cấu hình đóng gói |
| File profile bên ngoài JAR | ./config/application-prod.yml | Ghi đè thêm theo profile |
| Biến môi trường | SPRINGDOC_APIDOCS_ENABLED | Ghi đè cấu hình file |
| Java system property | -Dspringdoc.api-docs.enabled=false | Ghi đè biến môi trường |
| SPRING_APPLICATION_JSON | JSON truyền lúc khởi động | Ghi đè các nguồn thấp hơn |
| Tham số dòng lệnh | --springdoc.api-docs.enabled=false | Thường có ưu tiên cao hơn khi chạy ứng dụng |

Đây là thứ tự rút gọn để giải thích các nguồn thường gặp, không phải toàn bộ danh sách PropertySource. Spring Boot còn có default properties, @PropertySource, JNDI, servlet init parameters và các nguồn dành riêng cho kiểm thử. Khi cần chẩn đoán chính xác, hãy đối chiếu danh sách đầy đủ của phiên bản Spring Boot đang chạy.

Ví dụ file đặt:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Nhưng biến môi trường đặt:

~~~bash
SPRINGDOC_APIDOCS_ENABLED=false
~~~

Thì giá trị hiệu lực là false. Không nên nhìn riêng application.yml rồi kết luận endpoint chắc chắn được bật.

## 7. Quy tắc đổi tên property thành biến môi trường

Spring Boot dùng relaxed binding. Để chuyển tên property dạng chuẩn sang tên biến môi trường:

1. Thay dấu chấm . bằng dấu gạch dưới _.
2. Bỏ dấu gạch ngang -.
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ:

| Property | Environment variable |
| --- | --- |
| springdoc.api-docs.enabled | SPRINGDOC_APIDOCS_ENABLED |
| springdoc.swagger-ui.enabled | SPRINGDOC_SWAGGERUI_ENABLED |
| springdoc.api-docs.path | SPRINGDOC_APIDOCS_PATH |
| springdoc.swagger-ui.path | SPRINGDOC_SWAGGERUI_PATH |

Lưu ý dấu gạch ngang bị loại bỏ, không biến thành dấu gạch dưới. Vì vậy springdoc.api-docs.enabled chuyển thành SPRINGDOC_APIDOCS_ENABLED, không phải SPRINGDOC_API_DOCS_ENABLED.

Có thể đặt biến trong Linux/macOS:

~~~bash
export SPRINGDOC_APIDOCS_ENABLED=true
export SPRINGDOC_SWAGGERUI_ENABLED=false
java -jar shop-api.jar
~~~

Trong PowerShell:

~~~powershell
$env:SPRINGDOC_APIDOCS_ENABLED = "true"
$env:SPRINGDOC_SWAGGERUI_ENABLED = "false"
java -jar shop-api.jar
~~~

Đặt biến trong container hoặc Kubernetes bằng manifest/deployment configuration theo môi trường. Không ghi giá trị nhạy cảm vào Dockerfile hoặc manifest được commit nếu có thể cấp qua secret store.

## 8. Đưa cấu hình ra ngoài JAR

Không cần build lại ứng dụng chỉ để thay đường dẫn tài liệu hoặc bật/tắt Swagger UI. Spring Boot tự tìm file cấu hình ở classpath và một số vị trí bên ngoài thư mục chạy, ví dụ:

- Thư mục hiện tại.
- Thư mục ./config/.
- Các thư mục con trực tiếp của ./config/.

Ví dụ triển khai:

~~~text
deployment/
  shop-api.jar
  config/
    application.yml
    application-prod.yml
~~~

File ngoài JAR có thể ghi đè cấu hình đóng gói. Điều này giúp image/JAR giữ nguyên giữa các môi trường, còn cấu hình được cung cấp tại runtime.

Nếu muốn thêm một thư mục cấu hình mà vẫn giữ các vị trí mặc định, dùng spring.config.additional-location. Nếu dùng spring.config.location, danh sách location được chỉ định sẽ thay thế vị trí mặc định. Hai thuộc tính này được xử lý rất sớm khi khởi động, nên phải truyền qua environment, system property hoặc command line.

Ví dụ:

~~~bash
java -jar shop-api.jar \
  --spring.config.additional-location=optional:file:./runtime-config/
~~~

Prefix optional: cho phép ứng dụng tiếp tục khởi động nếu location đó không tồn tại. Chỉ dùng khi việc thiếu file thực sự có thể chấp nhận; với cấu hình bắt buộc, nên để ứng dụng fail fast.

## 9. Dùng placeholder để tái sử dụng giá trị

YAML và properties hỗ trợ placeholder để lấy giá trị từ Spring Environment. Có thể khai báo giá trị mặc định bằng dấu hai chấm sau tên property.

Ví dụ:

~~~yaml
springdoc:
  api-docs:
    path: ${DOCS_API_PATH:/v3/api-docs}
  swagger-ui:
    path: ${DOCS_UI_PATH:/docs}
~~~

Khi có DOCS_API_PATH hoặc DOCS_UI_PATH, Spring Boot dùng giá trị được cung cấp. Nếu không có, giá trị mặc định sau dấu hai chấm được sử dụng.

Trong placeholder, nên viết property name theo dạng canonical kebab-case chữ thường. Ví dụ ${springdoc.api-docs.path:/v3/api-docs} giúp relaxed binding hoạt động nhất quán với các nguồn cấu hình.

Không dùng placeholder để che giấu việc cấu hình thiếu một giá trị bắt buộc bằng default tùy tiện. Nếu thiếu URL, issuer hoặc thông tin vận hành khiến ứng dụng không thể hoạt động đúng, hãy để startup báo lỗi rõ ràng.

## 10. Cấu hình nhóm tài liệu trong YAML

Khi ứng dụng có nhiều API domain, có thể định nghĩa group để tạo nhiều OpenAPI document. Cấu hình group nằm dưới springdoc.group-configs.

~~~yaml
springdoc:
  group-configs:
    - group: orders
      display-name: Orders API
      packages-to-scan:
        - com.example.shop.orders
      paths-to-match:
        - /api/orders/**
    - group: catalog
      display-name: Catalog API
      packages-to-scan:
        - com.example.shop.catalog
      paths-to-match:
        - /api/products/**
~~~

Mỗi group có tên, package và path riêng. Springdoc tạo endpoint tài liệu tương ứng cho từng group, thường có dạng /v3/api-docs/{group} nếu không đổi base path. Swagger UI có thể hiển thị các tài liệu này trong danh sách chọn API khi cấu hình URL/group phù hợp.

Đừng tạo group chỉ để phân biệt môi trường. Group mô tả ranh giới tài liệu theo domain hoặc nhóm người dùng; profile mô tả cấu hình triển khai. Hai khái niệm có mục đích khác nhau.

## 11. Cấu hình group trong properties

Trong application.properties, các phần tử của list dùng chỉ số:

~~~properties
springdoc.group-configs[0].group=orders
springdoc.group-configs[0].display-name=Orders API
springdoc.group-configs[0].packages-to-scan=com.example.shop.orders
springdoc.group-configs[0].paths-to-match=/api/orders/**

springdoc.group-configs[1].group=catalog
springdoc.group-configs[1].display-name=Catalog API
springdoc.group-configs[1].packages-to-scan=com.example.shop.catalog
springdoc.group-configs[1].paths-to-match=/api/products/**
~~~

Chỉ số [0], [1] xác định phần tử trong list. Khi ghi đè list từ nguồn cấu hình khác, Spring Boot dùng toàn bộ list từ nguồn ưu tiên cao nhất; các phần tử không được khai báo lại sẽ không tự động được ghép từ list thấp hơn.

Ví dụ application.yml có hai group, nhưng application-prod.yml chỉ khai báo group orders, thì ở profile prod list group có thể chỉ còn orders. Nếu muốn giữ cả hai, phải khai báo đầy đủ cả hai group trong nguồn ghi đè. Quy tắc này cũng áp dụng cho các thuộc tính list như packages-to-scan và paths-to-match.

## 12. Giữ cấu hình Swagger UI tách biệt với OpenAPI

Swagger UI và OpenAPI endpoint có thể được bật/tắt độc lập:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Cấu hình trên vẫn cho phép client tải OpenAPI JSON, nhưng không phục vụ giao diện Swagger UI. Ngược lại, nếu api-docs.enabled=false, Swagger UI không thể tải tài liệu từ endpoint mặc định trừ khi được cấu hình dùng một OpenAPI definition ở URL khác.

Một số cấu hình UI thường dùng:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
    displayRequestDuration: true
    deepLinking: true
    docExpansion: none
    filter: true
~~~

Các property như displayRequestDuration, deepLinking, docExpansion và filter tương ứng với tùy chọn Swagger UI. Kiểm tra tên property và kiểu dữ liệu theo phiên bản springdoc vì các tùy chọn UI có thể theo phiên bản Swagger UI đi kèm.

Nếu muốn thay giao diện nhưng vẫn dùng cùng OpenAPI JSON, chỉ điều chỉnh nhóm springdoc.swagger-ui. Nếu muốn thay nội dung hợp đồng được sinh ra, hãy điều chỉnh nhóm core như packages-to-scan, paths-to-match, api-docs.path hoặc annotation của API.

## 13. Quản lý secret và thông tin xác thực

application.yml thường được commit cùng mã nguồn, vì vậy không đặt mật khẩu, token, private key hoặc client secret thật vào file này.

Với một giá trị bí mật cần được Spring Boot đọc, hãy lấy từ secret manager, biến môi trường được cấp bởi nền tảng hoặc configuration tree. Ví dụ Docker/Kubernetes mount secret thành file:

~~~text
/run/secrets/
  docs.auth.username
  docs.auth.password
~~~

Có thể nạp các file đó bằng:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Các tên file và nội dung sẽ trở thành property tương ứng trong Spring Environment, ví dụ docs.auth.password.

Tuy nhiên, không đưa secret vào cấu hình Swagger UI OAuth nếu trang được tải xuống browser. Client secret được nhúng trong cấu hình JavaScript hoặc được gửi cho trình duyệt không còn bí mật. Với Swagger UI chạy như public client, dùng client ID và Authorization Code với PKCE; việc bảo vệ endpoint tài liệu nên được thực hiện ở Spring Security, reverse proxy hoặc API gateway.

Không bật Actuator env hoặc configprops công khai để tiện debug. Các endpoint này có thể tiết lộ tên và giá trị cấu hình; nếu cần dùng để chẩn đoán, phải giới hạn quyền truy cập và masking theo chính sách.

## 14. Không nhầm cấu hình springdoc với cấu hình Spring Boot

Các thuộc tính server.port, management.server.port, spring.profiles.active, spring.config.* là cấu hình nền tảng Spring Boot. Các thuộc tính springdoc.* điều khiển việc sinh tài liệu và giao diện.

Ví dụ:

~~~yaml
server:
  port: 8080

spring:
  profiles:
    active: dev

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
~~~

Không đặt server.port bên dưới springdoc. YAML có thể hợp lệ về cú pháp nhưng property name sai vị trí sẽ không được bind vào cấu hình mong muốn.

Tương tự, springdoc.swagger-ui.path là đường dẫn giao diện, còn springdoc.api-docs.path là đường dẫn OpenAPI definition. Đổi một giá trị không tự động đổi giá trị còn lại.

## 15. Kiểm tra cấu hình đang có hiệu lực

Khi ứng dụng chạy không giống cấu hình dự kiến, hãy kiểm tra giá trị thực trong Spring Environment thay vì chỉ mở file YAML.

Các bước gợi ý:

1. Xác nhận profile đang hoạt động, ví dụ dev, test hoặc prod.
2. Xác nhận file cấu hình bên ngoài có được nạp và đúng vị trí không.
3. Kiểm tra biến môi trường có đúng tên sau khi chuyển đổi relaxed binding không.
4. Kiểm tra tham số command line hoặc system property có đang ghi đè file không.
5. Kiểm tra endpoint /v3/api-docs và đường dẫn Swagger UI thực tế.
6. Nếu cần, dùng Actuator env hoặc configprops trong môi trường đã được bảo vệ để xem nguồn và giá trị property.

Ví dụ chẩn đoán nhanh:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=dev \
  --springdoc.api-docs.enabled=true
~~~

Tham số dòng lệnh có thể ghi đè giá trị từ file. Vì vậy, sau khi debug xong, hãy xóa tham số tạm khỏi script deploy nếu không muốn nó trở thành cấu hình mặc định của lần chạy tiếp theo.

## 16. Kiểm thử cấu hình OpenAPI trong môi trường

Một kiểm thử tích hợp có thể xác nhận endpoint tài liệu được bật và sinh đúng thông tin:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "springdoc.api-docs.enabled=true",
    "springdoc.api-docs.path=/v3/api-docs"
})
@AutoConfigureMockMvc
class OpenApiConfigurationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiEndpointUsesConfiguredPathAndContainsInfo() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title").exists());
    }
}
~~~

Test này giả định tài liệu OpenAPI được phép truy cập trong test security context. Nếu Spring Security bảo vệ endpoint, cấu hình test authentication hoặc quyền truy cập phù hợp.

Ngoài endpoint JSON, nên có smoke test cho Swagger UI nếu giao diện được bật trong môi trường đó. Có thể xác nhận đường dẫn UI trả về redirect hoặc trang HTML theo cấu hình của phiên bản springdoc.

Với nhiều profile, chạy test hoặc smoke test bằng từng profile cần hỗ trợ. Đặc biệt kiểm tra:

- Local/dev: tài liệu và giao diện có bật đúng không.
- Test: endpoint cần cho contract test có hoạt động không.
- Staging: URL, group và security có giống production không.
- Production: tài liệu có được công bố đúng chính sách không.

## 17. Những lỗi cấu hình thường gặp

**Đã đổi application.yml nhưng giá trị không đổi.** Có thể file ngoài JAR, profile, biến môi trường hoặc command line đang ghi đè. Kiểm tra PropertySource và profile đang hoạt động.

**Biến môi trường không ghi đè được property.** Kiểm tra quy tắc chuyển tên: dấu chấm thành _, bỏ dấu gạch ngang và viết hoa. Ví dụ springdoc.api-docs.enabled là SPRINGDOC_APIDOCS_ENABLED.

**Swagger UI không tải được OpenAPI JSON.** Kiểm tra springdoc.api-docs.enabled, springdoc.api-docs.path, URL cấu hình trong Swagger UI, context path và security rule.

**OpenAPI JSON vẫn bật dù Swagger UI đã tắt.** springdoc.swagger-ui.enabled và springdoc.api-docs.enabled độc lập; đặt cả hai theo chính sách mong muốn.

**Group biến mất sau khi bật profile.** List trong nguồn ưu tiên cao hơn thay thế toàn bộ list thấp hơn. Khai báo đầy đủ group cần giữ ở profile đó.

**Thuộc tính có trong file nhưng không có hiệu lực.** Kiểm tra chính tả, prefix springdoc, kiểu dữ liệu và phiên bản springdoc có hỗ trợ property đó không.

**Có cả YAML và properties nhưng giá trị bất ngờ.** Trong cùng vị trí, .properties được ưu tiên. Chuẩn hóa về một định dạng.

**Tài liệu dev xuất hiện trong production.** Kiểm tra SPRING_PROFILES_ACTIVE, profile file, external config và biến môi trường trong deployment.

**Lộ client secret qua Swagger UI.** Xóa secret khỏi cấu hình được gửi đến browser. Dùng public client với PKCE hoặc bảo vệ tài liệu bằng cơ chế server-side.

**Không biết property nào ghi đè property nào.** Kiểm tra thứ tự PropertySource; trong môi trường được bảo vệ, dùng Actuator env/configprops để truy vết.

## 18. Checklist tổ chức cấu hình

- [ ] Chọn YAML hoặc properties làm định dạng chính.
- [ ] Nhóm property dưới springdoc.api-docs, springdoc.swagger-ui và springdoc.group-configs.
- [ ] Đặt giá trị dùng chung trong application.yml.
- [ ] Chỉ ghi đè phần khác biệt trong application-{profile}.yml.
- [ ] Chọn profile từ môi trường chạy hoặc command line.
- [ ] Dùng đúng tên environment variable theo relaxed binding.
- [ ] Hiểu nguồn cấu hình bên ngoài và thứ tự ưu tiên.
- [ ] Không giả định list được merge giữa các profile.
- [ ] Đưa file cấu hình triển khai ra ngoài JAR khi cần.
- [ ] Lấy secret từ secret manager, environment hoặc configtree.
- [ ] Không gửi client secret đến Swagger UI chạy trong browser.
- [ ] Bảo vệ Actuator env/configprops nếu dùng để debug.
- [ ] Kiểm tra OpenAPI JSON và Swagger UI bằng smoke/integration test.
- [ ] Xác nhận cấu hình production đúng chính sách công bố tài liệu.

## 19. Kết luận

Tổ chức thuộc tính springdoc theo nhóm giúp cấu hình tài liệu OpenAPI và Swagger UI dễ đọc, còn Spring Boot profiles và externalized configuration giúp cùng một ứng dụng chạy đúng ở nhiều môi trường. Hãy giữ giá trị chung trong application.yml hoặc application.properties, chỉ ghi đè khác biệt trong profile, dùng biến môi trường hoặc file ngoài JAR cho cấu hình triển khai, và quản lý secret qua nguồn riêng. Khi có lỗi, kiểm tra profile cùng thứ tự PropertySource và xác nhận endpoint thực tế. Đừng quên list cấu hình bị thay thế toàn bộ khi ghi đè và Swagger UI không phải nơi lưu bí mật.

## 20. Nguồn tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, application files, profiles, environment variables, placeholders, config locations và config trees.
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html): cấu hình file, profile và cách chẩn đoán nguồn thuộc tính.
- [springdoc-openapi — Configuration Properties](https://springdoc.org/properties.html): core properties, group configs và Swagger UI properties.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): sử dụng endpoint quản trị để quan sát và chẩn đoán ứng dụng.
