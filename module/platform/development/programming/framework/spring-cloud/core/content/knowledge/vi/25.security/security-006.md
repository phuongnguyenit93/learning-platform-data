# Giới hạn thuộc tính được sửa động theo khả năng phiên bản

Spring Cloud cho phép ứng dụng cập nhật Environment trong lúc đang chạy và áp dụng cấu hình mới cho một số bean. Khả năng này hữu ích khi vận hành feature flag, giới hạn tải hoặc cấu hình tích hợp mà không cần khởi động lại service. Tuy nhiên, một endpoint có quyền ghi Environment cũng có thể thay đổi những thuộc tính nhạy cảm nếu không giới hạn key được phép sửa.

Vấn đề này đã được ghi nhận trong **CVE-2026-59284 – Spring Cloud Commons no allow list for writable env actuator endpoint**, công bố ngày 20/08/2026 với mức độ HIGH. Các phiên bản bị ảnh hưởng cho phép POST tới Actuator Environment endpoint mà không có allowlist property key. Bản vá bổ sung thuộc tính giới hạn key được phép cập nhật: **management.endpoint.env.post.valid-keys-regex**.

Bài học thuộc chương **Bảo mật** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào ranh giới giữa cập nhật Environment và refresh bean, khả năng của từng nhánh Spring Cloud Commons, cách cấu hình allowlist bằng regular expression, cách bảo vệ endpoint, và cách kiểm thử để xác nhận thuộc tính ngoài danh sách không thể bị sửa.

## 1. Rủi ro khi cho phép ghi Environment

Spring Boot Actuator cung cấp endpoint quản trị để quan sát và điều khiển ứng dụng. Spring Cloud Context bổ sung khả năng ghi giá trị mới vào Environment qua POST /actuator/env, sau đó phát hiện thay đổi và cập nhật một số bean.

Nếu endpoint ghi này nhận mọi property key, người có quyền gọi có thể thử thay đổi những cấu hình vượt quá phạm vi vận hành dự kiến, chẳng hạn:

- URL hoặc thông tin kết nối database.
- Cấu hình xác thực, authorization hoặc session.
- Địa chỉ, port và đường dẫn quản trị.
- Cấu hình Spring Security hoặc management endpoint.
- Cấu hình cloud client, broker hoặc service discovery.
- Log level của package nhạy cảm.
- Các feature flag hoặc giới hạn nghiệp vụ vốn không được phép thay đổi bởi operator đó.

Một property thay đổi trong Environment không nhất thiết lập tức làm mọi bean đổi hành vi. Kết quả phụ thuộc bean có được rebind hay refresh hay không. Tuy vậy, khả năng ghi key tùy ý vẫn tạo ra bề mặt tấn công lớn vì nó cho phép thay đổi nguồn cấu hình runtime của ứng dụng.

### 1.1. CVE-2026-59284

Thông báo bảo mật chính thức mô tả lỗi là thiếu allowlist cho property key khi bật writable /actuator/env của Spring Cloud Commons.

| Nội dung | Thông tin |
| --- | --- |
| CVE | CVE-2026-59284 |
| Công bố | 20/08/2026 |
| Mức độ | HIGH |
| Thành phần | Spring Cloud Commons |
| Điểm rủi ro | POST /actuator/env có thể ghi key ngoài phạm vi cho phép |
| Biện pháp chính | Nâng cấp bản đã vá và cấu hình valid-keys-regex |
| Nguồn | Spring Security Advisories |

Không nên xem việc thêm một property regex vào file cấu hình của phiên bản cũ là đã khắc phục CVE. Bản thân code của Spring Cloud Commons phải có khả năng kiểm tra regex trước khi chấp nhận thao tác ghi.

Khác biệt về khả năng theo phiên bản thể hiện ngay trong tài liệu: tài liệu Spring Cloud 2023.0.x chỉ hướng dẫn bật thao tác POST bằng management.endpoint.env.post.enabled; tài liệu Spring Cloud Commons hiện hành bổ sung yêu cầu regex valid-keys-regex để giới hạn key được ghi. Vì vậy phải kiểm tra implementation Commons thực tế, không chỉ kiểm tra tên property có nằm trong file cấu hình hay không.

## 2. Khả năng theo phiên bản Spring Cloud Commons

Spring Security Advisory công bố các dải phiên bản bị ảnh hưởng và phiên bản sửa lỗi tương ứng:

| Spring Cloud Commons | Trạng thái | Phiên bản sửa lỗi | Phạm vi phát hành bản sửa |
| --- | --- | --- | --- |
| 5.0.0 đến 5.0.2 | Bị ảnh hưởng | 5.0.3 | OSS |
| 4.3.0 đến 4.3.3 | Bị ảnh hưởng | 4.3.4 | Enterprise Support Only |
| 4.0.0 đến 4.2.6 | Bị ảnh hưởng | 4.2.7 | Enterprise Support Only |
| 3.1.10 và cũ hơn | Bị ảnh hưởng | 3.1.11 | Enterprise Support Only |

Tại thời điểm biên soạn, Spring Cloud Commons 5.0.4 là phiên bản ổn định mới hơn trong nhánh 5.0.x. Spring Cloud 2025.1.3 đã đưa bản sửa CVE vào release train; Spring Cloud 2025.1.4 hiện dùng Commons 5.0.4.

Điểm cần chú ý:

- Với Commons 5.0.0 đến 5.0.2, cần nâng tối thiểu lên 5.0.3 hoặc bản mới hơn trong cùng nhánh.
- Với Commons 4.3.0 đến 4.3.3, bản sửa 4.3.4 được advisory ghi là chỉ có trong Enterprise Support.
- Với Commons 4.0.0 đến 4.2.6, bản sửa 4.2.7 được advisory ghi là chỉ có trong Enterprise Support.
- Với Commons 3.1.10 và cũ hơn, bản sửa 3.1.11 được advisory ghi là chỉ có trong Enterprise Support.
- Các nhánh cũ không có bản sửa OSS được liệt kê cần được nâng cấp sang release train còn phù hợp hoặc xử lý theo kênh hỗ trợ chính thức.

Nếu ứng dụng chưa thể nâng cấp, hãy tắt khả năng POST /actuator/env và không expose endpoint ghi này. Không dựa vào regex chưa được implementation hỗ trợ để bảo vệ một phiên bản đang bị ảnh hưởng.

### 2.1. Phải giữ tương thích Spring Boot và Spring Cloud

Không nâng riêng Spring Cloud Commons lên một version tùy ý mà không kiểm tra release train. Spring Cloud phát hành BOM để quản lý các module cùng một dòng tương thích.

| Spring Cloud release train | Spring Boot generation | Ghi chú |
| --- | --- | --- |
| 2025.1.x – Oakwood | 4.0.x; từ 2025.1.2 hỗ trợ 4.1.x | Commons 5.0.x; 2025.1.3 có bản sửa CVE |
| 2025.0.x – Northfields | 3.5.x | Commons 4.3.x; advisory ghi bản sửa 4.3.4 là Enterprise Support Only |
| 2024.0.x – Moorgate | 3.4.x | Commons 4.2.x; advisory ghi bản sửa 4.2.7 là Enterprise Support Only |
| 2023.0.x – Leyton | 3.2.x và 3.3.x từ 2023.0.2 | Kiểm tra chính xác Commons version và trạng thái hỗ trợ trước khi nâng |
| 2022.0.x – Kilburn | 3.0.x và 3.1.x từ 2022.0.3 | Nhánh cũ; cần kiểm tra trạng thái hỗ trợ và bản sửa có sẵn |

Ví dụ hiện hành của Spring Cloud 2025.1.4 được xây dựng trên Spring Boot 4.0.9 và hỗ trợ Spring Boot 4.1.2. Nếu ứng dụng còn ở Spring Boot 3.x, không ép Spring Cloud 5.0.x vào classpath chỉ để lấy bản vá. Hãy lập kế hoạch nâng Boot và Cloud đồng bộ, hoặc dùng bản sửa Enterprise tương ứng nếu tổ chức có quyền hỗ trợ đó.

### 2.2. Dùng BOM thay vì pin từng module

Ví dụ Maven cho release train 2025.1.4:

~~~xml
<properties>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

BOM giúp các module Spring Cloud dùng những version được release train kiểm thử cùng nhau. Khi xử lý CVE, hãy kiểm tra dependency tree để xác nhận version Spring Cloud Commons thực tế được nạp, kể cả khi ứng dụng không khai báo trực tiếp dependency đó.

Không kết luận đã nâng cấp chỉ từ version trong một file build. Dependency bắc cầu, dependency constraint hoặc platform khác có thể ghi đè version dự kiến.

## 3. POST /actuator/env làm gì?

Spring Cloud Context mở rộng Environment endpoint của Spring Boot Actuator. Khi thao tác POST được bật và endpoint được expose, client có thể gửi một property name cùng value mới.

Ví dụ payload:

~~~json
{
  "name": "app.runtime.catalog-enabled",
  "value": "false"
}
~~~

Spring Cloud cập nhật Environment và phát hiện các key thay đổi. Một số hành vi tiêu chuẩn gồm:

- Rebind các bean được quản lý bằng @ConfigurationProperties.
- Cập nhật log level cho các key thuộc logging.level.*.
- Cho phép listener ứng dụng nhận EnvironmentChangeEvent để thực hiện hành động bổ sung.

Thay đổi này nằm trong Environment của process đang chạy. Nó không tự sửa file application.yml, repository Git của Config Server hoặc manifest triển khai.

### 3.1. Cập nhật Environment không đồng nghĩa mọi bean đều thay đổi

Một bean chỉ nhận giá trị mới nếu cơ chế quản lý cấu hình của bean đó hỗ trợ cập nhật.

Ví dụ, một bean @ConfigurationProperties có setter có thể được rebind. Một bean đã giữ giá trị trong field thông thường nhưng không được rebind hoặc refresh sẽ tiếp tục dùng giá trị cũ.

Do đó, cần phân biệt:

| Cơ chế | Vai trò |
| --- | --- |
| POST /actuator/env | Thay đổi giá trị trong Environment |
| EnvironmentChangeEvent | Thông báo các property key đã thay đổi |
| @ConfigurationProperties rebinding | Gán lại giá trị cho bean cấu hình |
| @RefreshScope | Hủy target đang cache để tạo lại bean khi được sử dụng |
| Spring Cloud Bus | Phân phối sự kiện thay đổi/refresh tới nhiều instance |

Allowlist của CVE bảo vệ thao tác ghi property key qua writable Environment endpoint. Nó không phải bộ lọc chung cho mọi nguồn cấu hình hoặc mọi cơ chế refresh.

## 4. Bật allowlist theo khả năng của phiên bản đã vá

Trên phiên bản Spring Cloud Commons đã vá, có thể giới hạn property key được phép ghi bằng:

**management.endpoint.env.post.valid-keys-regex**

Ví dụ chỉ cho phép ba thuộc tính do ứng dụng quản lý:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env"
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(catalog-enabled|recommendations-enabled|max-items))$'
~~~

Regex trên chỉ khớp các key:

~~~text
app.runtime.catalog-enabled
app.runtime.recommendations-enabled
app.runtime.max-items
~~~

Các key như spring.datasource.url, spring.security.user.password, management.endpoints.web.exposure.include hoặc server.port không khớp và không nằm trong danh sách được phép ghi.

Đây là cấu hình minh họa cho phiên bản đã có bản vá. Trên version bị ảnh hưởng, không được giả định thuộc tính valid-keys-regex sẽ được thực thi.

### 4.1. Cách đọc regex

| Thành phần | Ý nghĩa |
| --- | --- |
| ^ | Bắt đầu chuỗi |
| app\.runtime\. | Prefix property được phép |
| (catalog-enabled\|recommendations-enabled\|max-items) | Một trong ba tên key được liệt kê |
| $ | Kết thúc chuỗi |

Dấu chấm trong tên property được escape thành \. để chỉ khớp dấu chấm thật. Hai anchor ^ và $ giúp giới hạn toàn bộ key, tránh trường hợp một chuỗi dài hơn chỉ cần chứa đoạn prefix hợp lệ là được chấp nhận.

YAML dùng nháy đơn quanh regex để giữ nguyên dấu gạch chéo ngược. Nếu dùng nháy kép, cần chú ý quy tắc escape của YAML.

### 4.2. Không dùng regex quá rộng

Không nên cấu hình:

~~~yaml
management:
  endpoint:
    env:
      post:
        valid-keys-regex: '.*'
~~~

Regex trên cho phép mọi property key và làm mất mục đích của allowlist.

Các pattern rộng khác cũng có rủi ro:

~~~text
^app\..*$
^spring\..*$
.*password.*
.*url.*
~~~

Một prefix ứng dụng rộng có thể chứa cả cấu hình bảo mật, credential hoặc endpoint nội bộ trong tương lai. Hãy liệt kê chính xác những key cần thay đổi thay vì cho phép cả namespace nếu không có lý do rõ ràng.

### 4.3. Chỉ giới hạn key, không giới hạn value

Regex kiểm tra tên property. Nó không kiểm tra giá trị có phù hợp với nghiệp vụ hay không.

Ví dụ key app.runtime.max-items có thể được phép ghi, nhưng giá trị 1000000 có thể gây quá tải nếu ứng dụng không có validation.

Hãy kiểm tra giá trị bằng cơ chế binding và validation:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.runtime")
public class RuntimeOptions {

    @Min(1)
    @Max(100)
    private int maxItems = 20;

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
~~~

Đăng ký RuntimeOptions bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties. Validation cần được kích hoạt với dependency validation phù hợp.

Allowlist trả lời câu hỏi “key nào được ghi?”. Validation trả lời câu hỏi “value nào hợp lệ?”. Phân quyền trả lời câu hỏi “ai được phép thực hiện thao tác?”. Ba lớp cần được thiết kế cùng nhau.

## 5. Bảo vệ endpoint bằng quyền truy cập và network boundary

Regex không xác thực người gọi. Một người không có quyền vẫn không được gọi endpoint, kể cả khi họ biết một key nằm trong allowlist.

Một cấu hình production nên có các lớp bảo vệ:

- Chỉ expose endpoint env khi có nhu cầu vận hành đã được phê duyệt.
- Đặt management interface trên mạng nội bộ hoặc management port riêng.
- Dùng Spring Security để yêu cầu identity và role chuyên biệt cho thao tác thay đổi cấu hình.
- Giới hạn quyền operator theo môi trường và service.
- Dùng TLS hoặc mTLS trên đường quản trị.
- Ghi audit cho người gọi, key, thời điểm, kết quả và change request.
- Giám sát các request POST tới /actuator/env.
- Không dùng credential quản trị chung trong source code hoặc application.yml.
- Không expose toàn bộ Actuator bằng include="*".

Nếu ứng dụng khai báo SecurityFilterChain tùy chỉnh, Spring Boot có thể lùi cấu hình bảo mật Actuator tự động. Khi đó ứng dụng phải tự định nghĩa quy tắc cho các endpoint quản trị và cả các route còn lại.

### 5.1. Chỉ expose endpoint cần thiết

Ví dụ chỉ expose health và env trên management interface:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
~~~

Exposure chỉ làm endpoint có thể được truy cập qua HTTP. Nó không thay thế authentication, authorization hoặc firewall.

Nếu ứng dụng không cần cập nhật Environment qua HTTP, hãy để POST env bị tắt và không expose env endpoint. Không bật endpoint chỉ để thử nghiệm rồi quên thu hồi trước khi triển khai production.

### 5.2. Quyền ghi nên tách khỏi quyền đọc

Một mô hình quyền đơn giản:

| Nhóm | Quyền |
| --- | --- |
| Health probe | Chỉ đọc health status |
| Monitoring | Đọc metrics và thông tin vận hành cần thiết |
| Configuration operator | Ghi các key nằm trong allowlist |
| Application administrator | Quản trị endpoint theo chính sách riêng |
| Service identity | Nhận cấu hình từ Config Server hoặc Bus theo quyền được cấp |

Không cấp role quản trị Actuator cho mọi người dùng ứng dụng. Tài khoản có quyền ghi Environment là tài khoản vận hành có khả năng thay đổi hành vi process.

### 5.3. Tránh lộ giá trị cấu hình

GET /actuator/env và /actuator/configprops có thể cung cấp thông tin về cấu hình đang chạy. Dù Spring Boot có cơ chế sanitization, không nên mở các endpoint này công khai.

- Giữ giá trị nhạy cảm ở chế độ ẩn.
- Không đưa password, token hoặc private key vào log.
- Không trả toàn bộ Environment cho frontend hoặc API nghiệp vụ.
- Hạn chế quyền đọc cấu hình theo vai trò.
- Bảo vệ log và audit vì chúng có thể chứa property key hoặc thông tin thay đổi.

## 6. Kiểm thử allowlist

Không chỉ kiểm tra một request hợp lệ. Cần có cả trường hợp được phép, bị từ chối và không có quyền.

### 6.1. Request hợp lệ

Ví dụ:

~~~bash
curl -X POST http://localhost:8080/actuator/env \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CONFIG_OPERATOR_TOKEN" \
  -d '{"name":"app.runtime.catalog-enabled","value":"false"}'
~~~

Sau khi thao tác thành công, kiểm tra Environment và bean cấu hình đã nhận giá trị mới theo cơ chế rebinding tương ứng.

Không coi response thành công là bằng chứng mọi bean trong ApplicationContext đã được tái tạo. Nếu bean cần @RefreshScope, phải thực hiện refresh theo đúng quy trình của bean đó.

### 6.2. Request không hợp lệ

Thử ghi một property nhạy cảm nằm ngoài allowlist:

~~~bash
curl -X POST http://localhost:8080/actuator/env \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CONFIG_OPERATOR_TOKEN" \
  -d '{"name":"spring.datasource.url","value":"jdbc:example"}'
~~~

Trên bản đã vá và regex giới hạn đúng, thao tác phải bị từ chối. Kiểm tra thêm Environment vẫn giữ giá trị cũ và không có bean cấu hình nào bị thay đổi.

Không chạy thử ghi key nhạy cảm trên production. Dùng test context hoặc môi trường staging với dữ liệu giả.

### 6.3. Test matrix tối thiểu

| Test | Kết quả mong đợi |
| --- | --- |
| Key hợp lệ, người gọi có role | Ghi thành công |
| Key ngoài regex, người gọi có role | Bị từ chối |
| Key hợp lệ, người gọi không có role | 401 hoặc 403 tùy security configuration |
| POST env chưa được bật | Không có thao tác ghi thành công |
| Env không được expose qua HTTP | Không truy cập được endpoint qua web |
| Regex thiếu hoặc cấu hình sai | Không cho phép vận hành ghi động; kiểm tra behavior của bản vá cụ thể |
| Value vượt validation | Binding/validation thất bại hoặc ứng dụng giữ trạng thái an toàn theo cấu hình |
| Key hợp lệ được cập nhật | Environment và bean hỗ trợ rebinding phản ánh giá trị mới |

### 6.4. Ví dụ kiểm thử với MockMvc

Ví dụ cấu trúc test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,env",
        "management.endpoint.env.post.enabled=true",
        "management.endpoint.env.post.valid-keys-regex=^(app\\.runtime\\.(catalog-enabled|recommendations-enabled|max-items))$"
})
@AutoConfigureMockMvc
class WritableEnvironmentAllowlistTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsAnAllowlistedProperty() throws Exception {
        mockMvc.perform(post("/actuator/env")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "name": "app.runtime.catalog-enabled",
                          "value": "false"
                        }
                        """))
                .andExpect(status().is2xxSuccessful());
    }

    @Test
    void rejectsAPropertyOutsideTheAllowlist() throws Exception {
        mockMvc.perform(post("/actuator/env")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "name": "spring.datasource.url",
                          "value": "jdbc:example"
                        }
                        """))
                .andExpect(status().is4xxClientError());
    }
}
~~~

Test cần chạy với Spring Cloud Commons đã vá và Actuator endpoint được bật. Đoạn test tập trung vào regex; nếu context có Spring Security, thêm user/role giả lập cho request hợp lệ và test riêng trường hợp thiếu quyền. Có thể bổ sung assertion trên Environment hoặc bean RuntimeOptions để chứng minh key bị từ chối không làm thay đổi giá trị.

Nếu endpoint bị bảo vệ bởi Spring Security, test cho phép phải đăng nhập bằng user/role đúng; test không có quyền cần xác nhận 401/403 trước khi kết luận về regex.

## 7. Phân biệt POST env với POST refresh

Hai endpoint có mục đích khác nhau:

| Endpoint | Vai trò | Có allowlist key của CVE không? |
| --- | --- | --- |
| POST /actuator/env | Ghi property vào Environment và kích hoạt rebinding liên quan | Có, trên Commons đã vá |
| POST /actuator/refresh | Làm mới property sources theo cơ chế Spring Cloud và refresh các bean trong @RefreshScope | Không phải endpoint ghi key theo cơ chế allowlist đó |
| Config Server refresh | Tải cấu hình ngoài từ Config Server | Quản lý quyền ở Config Server/repository và cơ chế refresh |
| Spring Cloud Bus refresh | Phát sự kiện refresh tới nhiều instance | Quản lý quyền ở Bus, broker và endpoint nhận sự kiện |

Regex valid-keys-regex không phải bộ lọc toàn cục cho mọi thay đổi cấu hình. Nó bảo vệ thao tác ghi key qua writable Environment endpoint được Spring Cloud Commons bổ sung.

Nếu cấu hình được thay đổi từ Config Server, Spring Cloud Bus, custom EnvironmentPostProcessor hoặc code gọi Environment API, cần kiểm soát nguồn và quyền của chính cơ chế đó.

## 8. Rebinding @ConfigurationProperties

Khi EnvironmentChangeEvent được xử lý, Spring Cloud có thể rebind các bean @ConfigurationProperties.

Ví dụ dưới đây minh họa một lớp mutable riêng để giải thích rebinding. Trong ứng dụng thật, không đăng ký nhiều bean cấu hình cùng prefix chỉ để sao chép các ví dụ; hãy giữ một lớp cấu hình có contract rõ ràng.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.runtime")
public class RuntimeOptionsRebindingExample {

    private boolean catalogEnabled = true;
    private int maxItems = 20;

    public boolean isCatalogEnabled() {
        return catalogEnabled;
    }

    public void setCatalogEnabled(boolean catalogEnabled) {
        this.catalogEnabled = catalogEnabled;
    }

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
~~~

Khi các key app.runtime.catalog-enabled hoặc app.runtime.max-items thay đổi và bean được rebind, bean nhận giá trị mới theo binding rules.

### 8.1. Rebinding thay đổi instance hiện có

Rebinding cập nhật các field của bean hiện tại. Quá trình này không tạo một instance mới rồi thay thế nguyên tử trong mọi trường hợp.

Spring Cloud tuần tự hóa các lần rebind đồng thời của cùng một bean. Tuy nhiên, một thread khác vẫn có thể đọc bean trong lúc field đang được cập nhật và thấy trạng thái trung gian.

Nếu ứng dụng cần một snapshot nhất quán trong khi refresh, cân nhắc dùng @RefreshScope cho bean phù hợp. Không dùng mutable configuration bean như một cấu trúc dữ liệu chia sẻ mà không có kế hoạch đồng bộ.

### 8.2. Constructor binding và Java Record

Các object @ConfigurationProperties dùng constructor binding, bao gồm Java Record, không thể được refresh theo cơ chế hiện hành được mô tả trong Spring Cloud Context.

Nếu một nhóm cấu hình cần thay đổi trong runtime, hãy lựa chọn kiểu binding tương thích và kiểm thử thực tế theo version. Không giả định mọi class @ConfigurationProperties đều tự động cập nhật chỉ vì Environment đã thay đổi.

### 8.3. Giá trị bị xóa khỏi Environment

Tài liệu Spring Cloud lưu ý rằng xóa một configuration value rồi refresh không nhất thiết làm sự hiện diện của giá trị đó biến mất như mong đợi. Nếu logic ứng dụng dựa vào việc property không tồn tại, hãy kiểm thử riêng semantics khi xóa key; có thể thiết kế theo một giá trị trạng thái tường minh thay vì dựa vào sự vắng mặt.

## 9. @RefreshScope và giới hạn bean có thể refresh

@RefreshScope tạo proxy lazy cho bean. Khi refresh scope bị invalidated, target được cache bị xóa và target mới được khởi tạo ở lần gọi tiếp theo.

Ví dụ:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class RemoteCatalogClient {

    private final String endpoint;

    public RemoteCatalogClient(CatalogClientProperties properties) {
        this.endpoint = properties.getEndpoint();
    }

    public String endpoint() {
        return endpoint;
    }
}
~~~

Khi cấu hình thay đổi và scope được refresh, lần gọi tiếp theo có thể tạo target mới với giá trị endpoint mới.

### 9.1. @RefreshScope không tự áp dụng cho mọi bean trong configuration class

Đánh dấu một @Configuration class bằng @RefreshScope không có nghĩa tất cả bean được khai báo trong class đó đều tự trở thành refresh-scoped.

Bean phụ thuộc vào các bean được tạo từ configuration class cũng không tự động nhận target mới. Nếu một dependency cần được tạo lại, hãy đặt scope phù hợp trên chính bean đó hoặc thiết kế dependency graph để việc inject lại được thực hiện đúng.

### 9.2. Bean không thể refresh và HikariDataSource

Spring Cloud Context có danh sách bean mặc định không được refresh. HikariDataSource là ví dụ quan trọng được tài liệu nêu trong spring.cloud.refresh.never-refreshable.

Nếu ứng dụng dùng HikariDataSource, không nên giả định refresh sẽ tạo lại pool chỉ vì URL database trong Environment đổi. Hãy chọn chiến lược cấu hình và thay thế pool phù hợp với lifecycle của datasource.

Các thuộc tính:

| Property | Mục đích |
| --- | --- |
| spring.cloud.refresh.extra-refreshable | Thêm bean name hoặc class name cần được xử lý như refreshable |
| spring.cloud.refresh.never-refreshable | Liệt kê bean name hoặc class name không được refresh/rebind |
| spring.cloud.refresh.never-reset-nested-types | Loại các nested library type khỏi quá trình reset đệ quy khi rebind |
| spring.cloud.refresh.enabled | Bật/tắt auto-configuration của refresh scope và các tính năng liên quan |

Các thuộc tính này điều khiển vòng đời bean hoặc cách rebind. Chúng **không phải allowlist property key** cho POST /actuator/env và không khắc phục CVE-2026-59284.

### 9.3. AOT và native image

Context refresh không được hỗ trợ cho Spring AOT transformations và native images theo tài liệu Spring Cloud Context hiện hành. Với ứng dụng AOT/native, đặt spring.cloud.refresh.enabled=false và quản lý cấu hình theo mô hình phù hợp với quá trình build/deploy.

Không bật refresh scope chỉ vì muốn có một API thay đổi cấu hình. Cần xác định bean nào thực sự hỗ trợ lifecycle đó.

## 10. Config Server và thứ tự ưu tiên property source

Spring Cloud Config có thể đưa remote property source vào Environment. Mặc định, remote property source có thể không cho local property override.

Các thuộc tính liên quan:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.config.allow-override | Cho phép remote property source chấp nhận quy tắc override |
| spring.cloud.config.override-none | Khi allow-override được cấp, cho local property source override từ mọi nguồn |
| spring.cloud.config.override-system-properties | Điều khiển system properties, command line và environment variables có được override remote property hay không |

Các thuộc tính này điều khiển **thứ tự ưu tiên của property source**, không phải quyền xác thực người gọi và cũng không phải allowlist property key.

Một local property có thể có độ ưu tiên cao hơn remote property không có nghĩa mọi người dùng đều được phép sửa property đó. Quyền ghi Config Server cần được kiểm soát tại repository, branch, credential, API và pipeline triển khai.

### 10.1. Spring Cloud Config Client không mặc định polling

Spring Cloud Config Client không mặc định liên tục polling Config Server để tìm thay đổi. Nếu hệ thống nhiều replica, có thể dùng Spring Cloud Bus để phát sự kiện refresh tới các instance.

Khi dùng Bus:
- Bảo vệ broker bằng credential và network policy.
- Giới hạn publisher có quyền phát sự kiện.
- Bảo vệ endpoint busrefresh hoặc cơ chế tương ứng.
- Theo dõi instance nào đã nhận và xử lý refresh.
- Không xem regex của /actuator/env là bảo vệ cho Bus event.

Một nguồn cấu hình có quyền thay đổi nhiều property cần có quy trình review, audit và rollback riêng.

## 11. Quy trình nâng cấp và xử lý hệ thống đang bị ảnh hưởng

Khi phát hiện ứng dụng dùng Spring Cloud Commons trong dải bị ảnh hưởng:

1. Xác định version Commons thực tế trong runtime dependency tree.
2. Kiểm tra POST /actuator/env có được bật không.
3. Kiểm tra endpoint env có được expose qua HTTP/JMX hoặc management interface nào không.
4. Nếu không cần ghi Environment, tắt thao tác POST và thu hồi exposure.
5. Giới hạn management network và quyền truy cập trong thời gian chuẩn bị nâng cấp.
6. Chọn bản vá phù hợp với Spring Cloud release train và Spring Boot version.
7. Nếu dùng OSS, xem xét nâng lên Spring Cloud 2025.1.3 trở lên cùng Spring Boot 4.0.x phù hợp; tại thời điểm biên soạn, 2025.1.4 dùng Commons 5.0.4.
8. Nếu chưa thể nâng major version, kiểm tra bản sửa Enterprise Support tương ứng hoặc giữ POST env bị tắt.
9. Sau khi nâng, cấu hình valid-keys-regex theo danh sách key tối thiểu.
10. Chạy test allowlist, authentication, authorization và rebinding.
11. Kiểm tra log truy cập, audit và thay đổi cấu hình trong thời gian phiên bản dễ bị ảnh hưởng đang chạy.
12. Ghi lại version BOM, quyền operator, danh sách key được phép và quy trình rollback.

Không chỉ sửa một file application.yml rồi coi sự cố đã được khắc phục. Cần xác minh code phiên bản mới thực sự thực thi allowlist.

### 11.1. Nếu nghi ngờ đã có thao tác trái phép

Nếu access log ghi nhận POST /actuator/env không được phê duyệt:

- Xác định thời gian, source IP, identity và property key đã gửi.
- So sánh Environment/runtime config với nguồn cấu hình chuẩn.
- Kiểm tra thay đổi log level, database endpoint, security settings và management exposure.
- Xác minh các bean cấu hình có được rebind hoặc refresh sau thao tác hay không.
- Khôi phục cấu hình từ nguồn tin cậy và restart instance nếu cần để loại bỏ trạng thái runtime không xác định.
- Thu hồi hoặc xoay credential nếu có bằng chứng giá trị nhạy cảm đã bị thay đổi hoặc lộ.
- Lưu log và audit để phục vụ điều tra.

Không tự động kết luận mọi ứng dụng trong dải affected đã bị khai thác. Phân biệt rõ version bị ảnh hưởng với bằng chứng một request trái phép thực sự đã xảy ra.

## 12. Những hiểu nhầm thường gặp

| Nhận định | Thực tế |
| --- | --- |
| Chỉ bật env.post.enabled là đủ an toàn | Cần bản Commons đã vá, regex allowlist và kiểm soát quyền |
| Thêm valid-keys-regex vào version cũ là đã vá CVE | Version cũ có thể không thực thi thuộc tính đó |
| Regex kiểm tra cả value | Regex chỉ giới hạn property key |
| Regex thay thế Spring Security | Regex không xác thực hoặc phân quyền người gọi |
| /actuator/refresh dùng cùng allowlist | Refresh không phải thao tác ghi key của writable env endpoint |
| @RefreshScope làm mọi bean tự cập nhật | Chỉ bean nằm trong scope và dependency được thiết kế phù hợp được tái tạo |
| never-refreshable là danh sách property cấm sửa | Đây là danh sách bean không được refresh/rebind |
| allow-override là quyền ghi cấu hình | Đây là quy tắc ưu tiên property source |
| Config Server/Bus được bảo vệ bởi valid-keys-regex | Cần kiểm soát riêng repository, API, broker và publisher |
| HTTP 200 của env POST chứng minh toàn bộ bean đã đổi | Chỉ xác nhận thao tác endpoint thành công; cần kiểm tra bean và consumer thực tế |

## 13. Checklist review bảo mật

- [ ] Đã xác định đúng version Spring Cloud Commons đang chạy.
- [ ] Version nằm ngoài dải bị ảnh hưởng của CVE-2026-59284.
- [ ] Nếu cần writable /actuator/env, đã dùng bản Commons có hỗ trợ valid-keys-regex.
- [ ] Regex có anchor đầu/cuối và chỉ liệt kê property key cần thiết.
- [ ] Không dùng regex .* hoặc prefix rộng không có lý do.
- [ ] Value được kiểm tra bằng validation nghiệp vụ.
- [ ] POST env chỉ bật khi có nhu cầu vận hành.
- [ ] Endpoint chỉ expose trên management network.
- [ ] Spring Security giới hạn người gọi bằng role chuyên biệt.
- [ ] Có audit cho request thay đổi cấu hình.
- [ ] GET env/configprops không làm lộ giá trị nhạy cảm.
- [ ] Config Server, Git repository và Bus có quyền truy cập riêng.
- [ ] Đã phân biệt rebinding với @RefreshScope.
- [ ] Đã kiểm tra constructor-bound properties và bean never-refreshable.
- [ ] Test chứng minh key hợp lệ được ghi và key ngoài allowlist bị từ chối.
- [ ] Test chứng minh người không có quyền không thể gọi endpoint.
- [ ] Có quy trình rollback và điều tra khi runtime config bị thay đổi ngoài ý muốn.

## Ghi nhớ

Giới hạn cập nhật cấu hình động cần được thực hiện ở đúng lớp và đúng version. CVE-2026-59284 cho thấy writable POST /actuator/env không an toàn nếu không giới hạn property key. Hãy nâng Spring Cloud Commons lên bản đã vá, cấu hình management.endpoint.env.post.valid-keys-regex với danh sách key hẹp, bảo vệ endpoint bằng authentication/authorization và management network, đồng thời validate value riêng. Đừng nhầm allowlist của env POST với @RefreshScope, never-refreshable, thứ tự ưu tiên Config Server hoặc Spring Cloud Bus: mỗi cơ chế có phạm vi và quyền hạn khác nhau.

## Tài liệu tham khảo

- Spring Security Advisory – CVE-2026-59284: https://spring.io/security/cve-2026-59284/
- Spring Cloud Commons – Application Context Services: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Cloud 2025.1.3 Release Notes – CVE-2026-59284 fix: https://spring.io/blog/2026/08/20/spring-cloud-2025-1-3-has-been-released/
- Spring Cloud 2025.1.4 Release Notes: https://spring.io/blog/2026/10/23/spring-cloud-2025-1-4-has-been-released/
- Spring Cloud – Spring Boot Compatibility Matrix: https://spring.io/projects/spring-cloud/
- Spring Boot Actuator – Endpoints and Security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Cloud Bus – Bus Refresh and Bus Env: https://docs.spring.io/spring-cloud/docs/current/reference/htmlsingle/spring-cloud.html

