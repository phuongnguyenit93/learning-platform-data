# Kiểm tra cấu hình hiệu lực qua env và configprops

> **Chương:** Quan sát  
> **Module:** SPRING_CLOUD_CORE

Khi một ứng dụng Spring Cloud chạy ở nhiều môi trường, cùng một thuộc tính có thể được khai báo trong file YAML, biến môi trường, JVM argument, command-line argument hoặc nguồn cấu hình từ xa. Vì vậy, đọc riêng `application.yml` không đủ để biết ứng dụng cuối cùng đang sử dụng giá trị nào. Ta cần quan sát `Environment` sau khi Spring Boot đã hợp nhất các nguồn cấu hình và kiểm tra giá trị đã được bind vào bean cấu hình.

Spring Boot Actuator cung cấp hai endpoint bổ trợ cho việc này: **`/actuator/env`** cho biết các property source trong `Environment`, nguồn của một thuộc tính và giá trị được phân giải; **`/actuator/configprops`** cho biết các bean `@ConfigurationProperties` cùng giá trị đã bind và thông tin đầu vào của quá trình binding. Kết hợp hai endpoint giúp tìm ra thuộc tính nào đang thắng, nó đến từ đâu và bean cấu hình có nhận đúng giá trị hay không.

Bài này dùng ví dụ cấu hình client và discovery trong **SPRING_CLOUD_CORE** để hướng dẫn đọc endpoint, truy tìm property precedence, hiểu relaxed binding, xử lý giá trị bị che, bảo vệ Actuator và kiểm thử cấu hình hiệu lực.

## 1. Vì sao cần kiểm tra cấu hình hiệu lực?

Giả sử ứng dụng khai báo:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true

catalog:
  client:
    base-url: https://catalog.internal
    connect-timeout: 2s
~~~

Khi triển khai, môi trường production đặt biến:

~~~text
SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED=false
CATALOG_CLIENT_CONNECT_TIMEOUT=750ms
~~~

Ứng dụng có thể nhận các giá trị từ biến môi trường thay cho giá trị trong YAML. Nếu người vận hành chỉ mở file cấu hình trong JAR, họ có thể kết luận sai rằng registration đang bật và timeout là hai giây.

Một số nguyên nhân thường làm giá trị runtime khác với file cấu hình:

- Profile khác nhau được kích hoạt.
- File cấu hình bên ngoài ghi đè file đóng gói trong JAR.
- Biến môi trường hoặc JVM system property có độ ưu tiên cao hơn.
- Command-line argument ghi đè giá trị đã khai báo.
- Config Server hoặc nguồn cấu hình được import cung cấp giá trị khác.
- Tên biến môi trường không được ánh xạ như dự kiến.
- Giá trị có trong Environment nhưng không được bind vào bean do sai prefix, sai tên field hoặc bean không được đăng ký.
- Giá trị đã bind được chuyển kiểu, áp dụng default hoặc validation trước khi ứng dụng sử dụng.

`env` và `configprops` giải quyết hai câu hỏi khác nhau: “Spring đang phân giải thuộc tính này từ đâu?” và “bean cấu hình đã nhận giá trị nào?”.

## 2. Hai endpoint có vai trò khác nhau

| Endpoint | Nguồn dữ liệu | Câu hỏi chính |
| --- | --- | --- |
| `/actuator/env` | Spring `Environment` và các `PropertySource` | Thuộc tính có trong nguồn nào, nguồn nào cung cấp giá trị được chọn? |
| `/actuator/configprops` | Bean được bind bằng `@ConfigurationProperties` | Bean cấu hình nào tồn tại, prefix là gì và các field đã bind ra sao? |

### 2.1. env: quan sát Environment

Endpoint `env` trình bày:

- `activeProfiles` và `defaultProfiles`.
- Danh sách `propertySources` và tên từng nguồn.
- Các thuộc tính có trong mỗi nguồn.
- Giá trị và origin của property khi metadata nguồn cung cấp.
- Thông tin nguồn cung cấp giá trị hiệu lực khi truy vấn một property cụ thể.

Endpoint này hữu ích cho cả thuộc tính được đọc bằng `Environment`, `@Value` và thuộc tính dùng cho binding, miễn là chúng được đưa vào Environment.

### 2.2. configprops: quan sát ConfigurationProperties binding

Endpoint `configprops` tổng hợp các bean được cấu hình bằng `@ConfigurationProperties`. Mỗi bean thường có các thông tin:

- Tên bean và prefix.
- `properties`: cấu trúc giá trị đã bind vào bean.
- `inputs`: thông tin đầu vào của từng thuộc tính, bao gồm value và origin nếu có.
- Context chứa bean đó, hữu ích khi ứng dụng có nhiều ApplicationContext.

Endpoint này phù hợp khi muốn xác nhận một cấu hình có cấu trúc đã được bind đúng. Nó không phải danh sách đầy đủ mọi property trong Environment. Một giá trị chỉ được đọc bằng `@Value` mà không thuộc bean `@ConfigurationProperties` có thể xuất hiện ở `env` nhưng không có bean tương ứng trong `configprops`.

## 3. Cấu hình Actuator để expose hai endpoint

Ứng dụng cần Spring Boot Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Để truy cập qua HTTP, expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
~~~

Spring Boot mặc định chỉ expose endpoint `health` qua HTTP và JMX. Có dependency Actuator không đồng nghĩa `env` và `configprops` tự động được mở qua HTTP.

Địa chỉ mặc định:

~~~text
GET /actuator/env
GET /actuator/configprops
~~~

Có thể thay đổi base path hoặc cổng management:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
  server:
    port: 9091
~~~

Với cấu hình này, các endpoint sẽ nằm dưới base path `/manage` trên cổng management `9091`. Hãy kiểm tra cấu hình thực tế khi endpoint trả 404; nguyên nhân có thể là base path, port, exposure hoặc access policy.

Không dùng `management.endpoints.web.exposure.include=*` trong production nếu không có nhu cầu rõ ràng và biện pháp bảo vệ đầy đủ. Hai endpoint này có thể tiết lộ tên property, profile, tên bean, class và topology nội bộ.

## 4. Đọc toàn bộ Environment qua /actuator/env

Có thể xem các property source bằng curl:

~~~bash
curl -u ops:password http://localhost:8080/actuator/env
~~~

Ví dụ rút gọn:

~~~json
{
  "activeProfiles": ["production"],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "systemEnvironment",
      "properties": {
        "CATALOG_CLIENT_CONNECT_TIMEOUT": {
          "value": "750ms"
        }
      }
    },
    {
      "name": "Config resource 'class path resource [application.yml]'",
      "properties": {
        "catalog.client.connect-timeout": {
          "value": "2s",
          "origin": "class path resource [application.yml] - 8:23"
        }
      }
    }
  ]
}
~~~

Đây là JSON minh họa cấu trúc, không phải response cố định của mọi phiên bản. Tên property source và cách hiển thị tên biến có thể khác theo môi trường.

`propertySources` được trả theo thứ tự precedence mà Spring Environment cung cấp. Khi cùng một property có ở nhiều nguồn, nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị hiệu lực. Dùng truy vấn một property cụ thể để xem trực tiếp nguồn thắng, thay vì suy đoán chỉ từ file YAML.

### 4.1. Xem một thuộc tính cụ thể

Endpoint hỗ trợ truy vấn theo tên property:

~~~bash
curl -u ops:password   http://localhost:8080/actuator/env/spring.cloud.service-registry.auto-registration.enabled
~~~

Response của một property có thể chứa:

- `property.source`: nguồn cung cấp giá trị được chọn.
- `property.value`: giá trị hiệu lực, nếu được phép hiển thị.
- `propertySources`: các nguồn và occurrence liên quan.
- `origin`: vị trí hoặc nguồn gốc của property nếu có metadata.

Ví dụ:

~~~json
{
  "activeProfiles": ["production"],
  "property": {
    "source": "systemEnvironment",
    "value": "false"
  },
  "propertySources": [
    {
      "name": "systemEnvironment",
      "property": {
        "value": "false",
        "origin": "System Environment Property"
      }
    },
    {
      "name": "Config resource 'class path resource [application.yml]'",
      "property": {
        "value": "true",
        "origin": "application.yml - 4:18"
      }
    }
  ]
}
~~~

Trong ví dụ, biến môi trường cung cấp giá trị `false` và ghi đè giá trị `true` trong file YAML. Nếu giá trị bị sanitization, trường value có thể được thay bằng `******`; khi đó vẫn có thể xem tên nguồn và origin nếu endpoint trả các metadata này.

### 4.2. Hiểu property precedence

Spring Boot có nhiều nguồn cấu hình, ví dụ:

- Default properties.
- `@PropertySource`.
- Config Data như `application.yml` và file profile-specific.
- OS environment variables.
- JVM system properties.
- JNDI và servlet init parameters trong môi trường phù hợp.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Các test property source khi chạy test.

Đây là danh sách minh họa các nguồn thường gặp; thứ tự chính xác và nguồn bổ sung phụ thuộc phiên bản, Config Data import và môi trường chạy. Quy tắc cần nhớ là property source có độ ưu tiên cao hơn có thể ghi đè giá trị từ nguồn thấp hơn.

Với file Config Data, profile-specific file và file bên ngoài JAR cũng có quy tắc ưu tiên riêng. Không kết luận chỉ dựa trên thứ tự file được liệt kê trong repository. Hãy truy vấn property hiệu lực qua `env` để biết ứng dụng đang dùng nguồn nào.

## 5. Ánh xạ tên biến môi trường sang property

Trên nhiều hệ điều hành, tên biến môi trường không tiện dùng dấu chấm hoặc dấu gạch nối. Spring Boot hỗ trợ relaxed binding để ánh xạ dạng biến môi trường sang tên property canonical.

Ví dụ:

| Property | Environment variable |
| --- | --- |
| `spring.cloud.service-registry.auto-registration.enabled` | `SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED` |
| `catalog.client.connect-timeout` | `CATALOG_CLIENT_CONNECT_TIMEOUT` |
| `catalog.client.base-url` | `CATALOG_CLIENT_BASEURL` |

Quy tắc thông dụng cho tên biến môi trường là chuyển chữ thành uppercase, dấu chấm thành dấu gạch dưới và bỏ dấu gạch nối. Với map key, list index và các tên phức tạp, cần kiểm tra quy tắc binding cụ thể thay vì tự suy luận từ một ví dụ đơn giản.

Ví dụ triển khai:

~~~bash
export SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED=false
export CATALOG_CLIENT_CONNECT_TIMEOUT=750ms
~~~

Nếu `env` không hiển thị property như mong đợi:

1. Kiểm tra tên biến có thực sự được truyền vào process/container.
2. Kiểm tra chính tả và quy tắc relaxed binding.
3. Kiểm tra property canonical bằng endpoint `/actuator/env/{property.name}`.
4. Kiểm tra profile và property source đang thắng.
5. Kiểm tra bean `@ConfigurationProperties` có prefix và field tương ứng hay không.

Không phải mọi tên property có dấu chấm đều có thể chuyển máy móc thành tên biến môi trường mà không xét map key, list index hoặc ký tự đặc biệt.

## 6. Đọc /actuator/configprops

Để xem toàn bộ bean cấu hình:

~~~bash
curl -u ops:password http://localhost:8080/actuator/configprops
~~~

Để lọc theo prefix:

~~~bash
curl -u ops:password   http://localhost:8080/actuator/configprops/catalog.client
~~~

Response có cấu trúc theo context và bean. Một phần tử rút gọn:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "catalogClientProperties": {
          "prefix": "catalog.client",
          "properties": {
            "baseUrl": "https://catalog.internal",
            "connectTimeout": "PT0.75S"
          },
          "inputs": {
            "baseUrl": {
              "value": "https://catalog.internal",
              "origin": "class path resource [application.yml] - 7:15"
            },
            "connectTimeout": {
              "value": "750ms",
              "origin": "System Environment Property"
            }
          }
        }
      }
    }
  }
}
~~~

Đây là response minh họa đã rút gọn. Bean name, context ID, cách biểu diễn Duration và cấu trúc lồng nhau phụ thuộc class cấu hình cùng phiên bản Spring Boot.

### 6.1. Phân biệt properties và inputs

Hai nhánh trong response giúp trả lời hai câu hỏi:

- `properties`: giá trị của object cấu hình sau binding và chuyển đổi kiểu.
- `inputs`: thông tin đầu vào được dùng để bind, thường có value và origin.

Ví dụ `connectTimeout` trong `properties` có thể được biểu diễn thành duration chuẩn hóa, trong khi `inputs.connectTimeout.value` vẫn hiển thị chuỗi nguồn như `750ms`. Đây là lý do hai trường có thể không giống nhau về cách biểu diễn mà vẫn tương đương về ý nghĩa.

Origin giúp truy ra nguồn cấu hình, chẳng hạn file YAML và số dòng, biến môi trường hoặc nguồn cấu hình khác. Không phải mọi PropertySource đều cung cấp metadata origin chi tiết.

### 6.2. Endpoint chỉ hiển thị bean ConfigurationProperties

`configprops` không phải bản sao của toàn bộ `env`. Nó tập trung vào các bean được bind bằng `@ConfigurationProperties`.

Nếu một property có trong `env` nhưng không tìm thấy trong `configprops`, hãy kiểm tra:

- Ứng dụng có bean `@ConfigurationProperties` tương ứng không?
- Prefix của bean có đúng không?
- Bean có được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` không?
- Field/property có được binder nhận diện không?
- Property chỉ được đọc qua `@Value` hoặc `Environment` hay không?

Không kết luận property bị bỏ qua chỉ vì nó không xuất hiện trong `configprops`.

## 7. Tạo bean cấu hình để quan sát binding

Ví dụ một client cấu hình bằng prefix riêng:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private String baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Đăng ký bean cấu hình bằng scan:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
}
~~~

Hoặc đăng ký tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogPropertiesConfiguration {
}
~~~

File YAML:

~~~yaml
catalog:
  client:
    base-url: https://catalog.internal
    connect-timeout: 2s
~~~

Biến môi trường có thể ghi đè timeout:

~~~text
CATALOG_CLIENT_CONNECT_TIMEOUT=750ms
~~~

Sau khi ứng dụng khởi động, `env` cho biết property source thắng; `configprops` cho biết bean `CatalogClientProperties` đã bind `connectTimeout` ra sao. Cách quan sát kép này giúp tách lỗi nạp cấu hình khỏi lỗi binding.

## 8. Quy trình chẩn đoán khi giá trị không đúng

Giả sử client đang timeout sau hai giây dù deployment khai báo `CATALOG_CLIENT_CONNECT_TIMEOUT=750ms`. Có thể điều tra theo thứ tự:

1. Gọi `/actuator/env/catalog.client.connect-timeout` để xem property có trong Environment không.
2. Xem `property.source` để xác định nguồn đang thắng.
3. Nếu nguồn thắng không phải system environment, kiểm tra tên biến và thứ tự precedence.
4. Gọi `/actuator/configprops/catalog.client` để xem bean nào được bind với prefix này.
5. So sánh `inputs.connectTimeout` với `properties.connectTimeout`.
6. Kiểm tra bean cấu hình có được đăng ký và component sử dụng có inject đúng bean hay không.
7. Nếu cấu hình được cập nhật sau startup, xác định bean có cơ chế refresh/rebind hay cần khởi động lại.
8. Kiểm tra code có ghi đè giá trị sau binding hoặc dùng một client được tạo từ giá trị cũ hay không.

### 8.1. Một số triệu chứng thường gặp

| Triệu chứng | Nơi kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Property không xuất hiện trong env | Process environment, profile, Config Data, tên property | Kiểm tra nguồn cấu hình và tên canonical |
| env có nhiều giá trị khác nhau | propertySources và property.source | Xác định source có precedence cao nhất |
| env đúng nhưng configprops không có bean | configprops theo prefix | Kiểm tra scan, EnableConfigurationProperties và prefix |
| configprops có bean nhưng field không như mong đợi | inputs và properties | Kiểm tra tên field, kiểu dữ liệu, converter và default |
| Giá trị bị ****** | show-values và sanitization | Kiểm tra role/authorization; không mở giá trị rộng rãi |
| Origin không rõ | inputs/propertySources | Kiểm tra nguồn có hỗ trợ origin metadata không |
| Giá trị đúng sau restart nhưng sai trước restart | refresh/rebinding và vòng đời bean | Xác định bean có hỗ trợ refresh hay cần restart |

### 8.2. Khi property đã đổi nhưng bean vẫn dùng giá trị cũ

`env` phản ánh Environment hiện tại; `configprops` giúp kiểm tra bean cấu hình đã bind. Tuy nhiên, việc một nguồn cấu hình thay đổi không bảo đảm mọi object đang chạy tự động được cập nhật.

Với bean cấu hình thông thường, hãy xác định lifecycle binding của phiên bản Spring Boot và Spring Cloud đang dùng. Nếu ứng dụng sử dụng Spring Cloud Context, có thể cần cơ chế refresh/rebind phù hợp hoặc thay thế bean theo quy trình được hỗ trợ. Các HTTP client, connection pool hoặc object đã được tạo từ giá trị cũ cũng có thể cần tái tạo.

Không dùng việc thấy property mới trong `env` làm bằng chứng duy nhất rằng toàn bộ ứng dụng đã áp dụng giá trị đó.

## 9. Bảo vệ giá trị nhạy cảm và quyền truy cập

Hai endpoint có thể chứa thông tin nhạy cảm như URL nội bộ, username, token, mật khẩu, thông tin database hoặc cấu hình tích hợp. Spring Boot mặc định sanitizes các giá trị được trả về từ `env` và `configprops`; response có thể thay giá trị bằng `******`.

Có thể điều khiển việc hiển thị giá trị bằng `show-values`:

| Giá trị | Hành vi |
| --- | --- |
| `never` | Luôn che giá trị |
| `always` | Hiển thị giá trị cho mọi người có quyền truy cập endpoint |
| `when-authorized` | Chỉ hiển thị giá trị cho người đã xác thực và có role được endpoint yêu cầu |

Ví dụ chỉ cho role `ops` xem giá trị chưa che:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ops
    configprops:
      show-values: when-authorized
      roles:
        - ops
~~~

Với HTTP endpoint, người dùng cần xác thực và đáp ứng role cấu hình. Nếu không đặt role riêng, quy tắc mặc định của phiên bản có thể cho phép mọi người dùng đã xác thực xem giá trị; hãy khai báo role rõ ràng khi dùng `when-authorized`.

Một bean `SanitizingFunction` tùy chỉnh vẫn có thể che giá trị ngay cả khi `show-values` được đặt thành `always` hoặc `when-authorized`. Vì vậy, không được giả định đổi show-values sẽ luôn làm lộ mọi giá trị.

### 9.1. Cấu hình an toàn cho production

Khuyến nghị:

- Chỉ expose `env` và `configprops` trên management network hoặc qua gateway nội bộ.
- Bật Spring Security hoặc cơ chế xác thực tương đương.
- Phân quyền riêng cho người vận hành cần đọc cấu hình.
- Giữ `show-values: never` nếu không có yêu cầu xem giá trị rõ ràng.
- Nếu cần xem giá trị, ưu tiên `when-authorized` và role hẹp như `ops`.
- Không dùng `always` cho endpoint có thể truy cập từ mạng rộng.
- Không expose tất cả Actuator endpoint chỉ để debug một property.
- Không chia sẻ nguyên response có chứa URL nội bộ hoặc thông tin nhạy cảm vào ticket/chat công khai.
- Dùng secret manager cho secret; không dựa vào sanitization để biến endpoint thành nơi lưu secret an toàn.

## 10. Kiểm thử endpoint và binding

Có thể kiểm thử cấu hình bean riêng bằng ApplicationContext test, sau đó kiểm thử Actuator HTTP endpoint trong Spring Boot test. Ví dụ dưới đây giả định ứng dụng đã đăng ký `CatalogClientProperties` và dùng Spring MVC test support.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "catalog.client.base-url=https://catalog.test",
        "catalog.client.connect-timeout=750ms",
        "management.endpoints.web.exposure.include=env,configprops"
})
@AutoConfigureMockMvc
class ConfigurationActuatorEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesEnvironmentPropertyOrigin() throws Exception {
        mockMvc.perform(get(
                "/actuator/env/catalog.client.connect-timeout"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.property.source").exists());
    }

    @Test
    void exposesCatalogConfigurationPropertiesBean() throws Exception {
        mockMvc.perform(get("/actuator/configprops/catalog.client"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.contexts.*.beans.*.prefix",
                        hasItem("catalog.client")));
    }
}
~~~

Response thực tế có thể khác theo phiên bản Spring Boot, context ID và bean name. Test nên kiểm tra cấu trúc và hành vi cần thiết, tránh phụ thuộc vào tên bean tự sinh nếu ứng dụng không cố định tên đó.

### 10.1. Kiểm thử sanitization

Không nên viết test yêu cầu secret hiển thị trong response. Thay vào đó, kiểm tra mặc định giá trị nhạy cảm được che hoặc kiểm tra role authorization khi dùng `when-authorized`.

Với test bảo mật, cần xác nhận:

- Người chưa xác thực không truy cập được endpoint theo security policy.
- Người đã xác thực nhưng thiếu role không thấy giá trị chưa che.
- Người có role được phép chỉ thấy các giá trị theo policy đã cấu hình.
- Custom `SanitizingFunction` vẫn được áp dụng.

### 10.2. Kiểm thử nguồn cấu hình ghi đè

Có thể đặt cùng một property ở YAML test và environment/property source có precedence cao hơn, rồi kiểm tra `env` báo đúng nguồn thắng. Với test tự động, nên ưu tiên xác nhận giá trị đã bind vào bean bằng assertion trực tiếp; endpoint test xác nhận khả năng quan sát và cấu trúc response.

Không nên kiểm thử toàn bộ precedence của Spring Boot bằng một test duy nhất. Tạo test nhỏ cho từng nguồn quan trọng mà deployment thực sự sử dụng.

## 11. Lỗi thường gặp và cách tránh

1. **Đọc application.yml rồi cho rằng đó là giá trị runtime:** kiểm tra `env` để tìm nguồn thắng.
2. **Nhầm env với configprops:** env hiển thị Environment; configprops hiển thị bean đã bind bằng ConfigurationProperties.
3. **Không thấy property trong configprops nên nghĩ property không tồn tại:** property có thể chỉ được đọc bằng Value hoặc Environment.
4. **Thấy env có giá trị nhưng bean không nhận:** kiểm tra prefix, tên field, binding, condition và bean registration.
5. **Cho rằng thứ tự YAML quyết định precedence:** xem PropertySource và property.source.
6. **Nhầm tên biến môi trường:** áp dụng relaxed binding và xác nhận trong endpoint.
7. **Không hiểu giá trị Duration sau binding:** so sánh inputs với properties; chúng có thể có cách biểu diễn khác nhau.
8. **Giá trị bị che nên kết luận property rỗng:** kiểm tra show-values và sanitization policy.
9. **Bật show-values always trên production:** giới hạn bằng when-authorized, role và management network.
10. **Expose toàn bộ Actuator để debug:** chỉ mở endpoint cần thiết.
11. **Thấy env đã đổi rồi cho rằng bean đã refresh:** xác minh configprops và lifecycle/rebinding của bean.
12. **Không kiểm tra origin:** dùng origin để tìm file, dòng hoặc nguồn cung cấp khi metadata có sẵn.

## 12. Quy trình vận hành khi cần truy tìm cấu hình

Khi một hành vi Spring Cloud khác với cấu hình mong đợi:

1. Xác định canonical property name và giá trị mong muốn.
2. Kiểm tra active profile và các nguồn cấu hình của deployment.
3. Truy vấn `/actuator/env/{property.name}` để tìm giá trị hiệu lực và nguồn thắng.
4. Đối chiếu các occurrence trong propertySources để hiểu giá trị bị ghi đè.
5. Truy vấn `/actuator/configprops/{prefix}` nếu property thuộc một bean ConfigurationProperties.
6. So sánh inputs với properties để phân biệt giá trị nguồn và giá trị đã bind.
7. Kiểm tra prefix, field, type conversion, default và validation.
8. Xác định bean hoặc client đã áp dụng giá trị tại runtime hay chưa.
9. Kiểm tra refresh/rebind/restart nếu nguồn cấu hình thay đổi sau startup.
10. Lưu lại kết luận gồm property, source, origin và bean bị ảnh hưởng; che mọi giá trị nhạy cảm trước khi chia sẻ.

**Điểm ghi nhớ:** `env` trả lời thuộc tính nào đang có trong Environment và nguồn nào cung cấp giá trị hiệu lực; `configprops` trả lời bean `@ConfigurationProperties` nào đã nhận giá trị sau binding. Khi điều tra một cấu hình Spring Cloud, hãy tìm nguồn thắng bằng env, xác nhận giá trị đã bind bằng configprops và kiểm tra bean thực sự sử dụng giá trị đó. Luôn giữ endpoint trong management network, áp dụng xác thực/phân quyền và che secret theo chính sách phù hợp của **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Actuator — Endpoints and Sanitization](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator REST API — Environment](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot Actuator REST API — Configuration Properties](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Boot — Customizing Sanitization](https://docs.spring.io/spring-boot/how-to/actuator.html)
