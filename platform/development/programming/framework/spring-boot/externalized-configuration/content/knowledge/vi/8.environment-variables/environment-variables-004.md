# Khóa Map qua biến môi trường và giới hạn bảo toàn chữ hoa trong Spring Boot

Spring Boot cho phép cấu hình một `Map<String, String>` qua biến môi trường hệ điều hành. Cách này rất hữu ích khi triển khai ứng dụng trên máy chủ, Docker hoặc Kubernetes vì mỗi môi trường có thể cung cấp những cặp khóa–giá trị khác nhau mà không cần sửa mã nguồn. Tuy nhiên, cơ chế *relaxed binding* có một giới hạn quan trọng:

> **Khi Spring Boot bind các biến môi trường vào một Map qua `@ConfigurationProperties`, khóa trong Map được chuyển thành chữ thường. Giá trị của biến môi trường vẫn giữ nguyên chữ hoa và chữ thường.**

Ví dụ, biến môi trường `MY_PROPS_VALUES_KEY=VALUE` tạo phần tử `{"key": "VALUE"}` trong Map phù hợp. Tên khóa `KEY` trở thành `key`, trong khi giá trị `VALUE` vẫn là `VALUE`.

Bài học tập trung vào Spring Boot 3.3.x và Java 21; phân biệt tên biến môi trường, đường dẫn thuộc tính và khóa thật sự trong Map, sau đó hướng dẫn cách xử lý khi hệ thống bên ngoài đòi hỏi tên khóa có phân biệt hoa–thường.

## 1. Vì sao Map được dùng trong cấu hình?

Một số cấu hình có danh sách khóa động, không cố định trước lúc biên dịch. Ví dụ, ứng dụng có thể lưu các nhãn tích hợp, tên đối tác hoặc quy tắc định tuyến:

~~~yaml
my:
  props:
    values:
      region: vietnam
      team: platform
      mode: production
~~~

Ta muốn bind `my.props.values` thành đối tượng Java:

~~~java
Map<String, String> values
~~~

Kết quả tương ứng:

~~~text
values["region"] = "vietnam"
values["team"]   = "platform"
values["mode"]   = "production"
~~~

Khi ứng dụng chạy tại nhiều môi trường, người vận hành có thể muốn khai báo các giá trị đó qua biến môi trường thay vì tạo một file YAML riêng. Đó là lúc cần hiểu quy tắc chuyển tên biến môi trường sang đường dẫn cấu hình và cách Binder xử lý **khóa động của Map**.

## 2. Nhắc lại relaxed binding từ biến môi trường

Spring Boot hỗ trợ nhiều cách viết tên thuộc tính, ví dụ:

~~~text
my.service.client-id
my.service.clientId
MY_SERVICE_CLIENTID
~~~

Đối với biến môi trường, tài liệu Spring Boot khuyến nghị chuyển tên thuộc tính dạng chuẩn (*canonical kebab-case*) như sau:

1. Thay dấu chấm `.` phân tách cấp thuộc tính thành dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-` trong tên thuộc tính.
3. Chuyển thành chữ hoa.

Ví dụ:

| Tên thuộc tính chuẩn | Biến môi trường tương ứng |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `my.props.values` | `MY_PROPS_VALUES` |
| `app.client.connect-timeout` | `APP_CLIENT_CONNECTTIMEOUT` |

Quy tắc này cho phép nhập cấu hình bằng những tên biến tương thích với hệ điều hành và công cụ triển khai. Với một trường cố định như `connectTimeout` trong Java, relaxed binding giúp nhận giá trị từ `APP_CLIENT_CONNECTTIMEOUT`.

Tuy nhiên, với **Map**, đoạn cuối tên thuộc tính không nhất thiết là tên một trường Java cố định. Đoạn đó có thể là **một khóa dữ liệu do người vận hành đặt**. Vì vậy, việc chuẩn hóa chữ hoa/chữ thường có thể làm mất thông tin mà một hệ thống khác yêu cầu giữ nguyên.

### Biến môi trường và giá trị là hai phần khác nhau

~~~text
MY_PROPS_VALUES_CLIENT=SomeValue
|____________________| |_______|
      tên biến          giá trị
~~~

Trong ví dụ, tên biến chứa tiền tố đường dẫn `MY_PROPS_VALUES` và khóa động `CLIENT`. Chỉ **tên** biến được dùng để xác định đường dẫn và khóa của Map trong quá trình bind. Phần `SomeValue` là dữ liệu giá trị, không bị chuyển tự động thành `somevalue`.

## 3. Ví dụ chính thức về Map binding

Tạo lớp cấu hình:

~~~java
package com.example.configdemo;

import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "my.props")
public class MyMapsProperties {

    private final Map<String, String> values = new HashMap<>();

    public Map<String, String> getValues() {
        return values;
    }
}
~~~

Lớp này có tiền tố `my.props` và trường `values`, vì vậy các thuộc tính con của `my.props.values` có thể được bind thành các entry trong Map.

Đăng ký cấu hình trong ứng dụng Spring Boot:

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` cho phép Spring Boot phát hiện lớp có `@ConfigurationProperties` trong package quét. Nếu dự án đã đăng ký cấu hình bằng `@EnableConfigurationProperties(MyMapsProperties.class)`, có thể dùng cơ chế đó thay thế.

Trên Linux/macOS, đặt biến môi trường:

~~~bash
export MY_PROPS_VALUES_KEY=VALUE
java -jar config-demo.jar
~~~

Sau khi bind, Map chứa:

~~~text
key   → VALUE
~~~

Tức là:

~~~java
properties.getValues().get("key");   // "VALUE"
properties.getValues().get("KEY");   // thường là null nếu không có key riêng "KEY"
~~~

Đây là ví dụ cốt lõi được mô tả trong tài liệu Spring Boot 3.3 phần *Binding Maps From Environment Variables*.

## 4. Tên khóa luôn lowercase, giá trị giữ nguyên

Xét các biến môi trường:

~~~bash
export MY_PROPS_VALUES_REGION="APAC"
export MY_PROPS_VALUES_TEAM="PlatformOps"
export MY_PROPS_VALUES_TOKENLABEL="xYz123"
~~~

Với lớp `MyMapsProperties` ở trên, Map nhận các entry:

~~~text
{
  "region":     "APAC",
  "team":       "PlatformOps",
  "tokenlabel": "xYz123"
}
~~~

Hai phép biến đổi khác nhau xảy ra:

| Phần | Dữ liệu đầu vào | Kết quả |
| --- | --- | --- |
| Tên khóa Map | `REGION` | `region` |
| Giá trị Map | `APAC` | `APAC` |
| Tên khóa Map | `TEAM` | `team` |
| Giá trị Map | `PlatformOps` | `PlatformOps` |
| Tên khóa Map | `TOKENLABEL` | `tokenlabel` |
| Giá trị Map | `xYz123` | `xYz123` |

Điều cần tránh là suy luận rằng vì tên biến môi trường thường viết hoa, Map sẽ giữ nguyên tên khóa viết hoa. **Không có cơ chế như vậy trong relaxed binding thông thường của Spring Boot từ environment variables vào Map.**

Ngược lại, không được suy luận rằng mọi dữ liệu đi qua Binder sẽ bị chuyển thành chữ thường: **chỉ tên biến được chuẩn hóa để xác định tên thuộc tính/khóa Map; giá trị không bị lowercasing**.

Đây là sự phân biệt quan trọng khi giá trị chứa mã định danh, chuỗi phân biệt hoa–thường, URL, tên tệp hoặc nội dung nghiệp vụ.

## 5. Đọc Map trong ứng dụng Java

Tạo một `ApplicationRunner` để quan sát dữ liệu sau khi ứng dụng khởi động:

~~~java
package com.example.configdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ConfigPrinter {

    @Bean
    ApplicationRunner printMap(MyMapsProperties properties) {
        return args -> {
            properties.getValues()
                    .forEach((key, value) ->
                            System.out.println(key + " = " + value));

            System.out.println(
                    "Get lowercase key: "
                            + properties.getValues().get("region"));

            System.out.println(
                    "Get uppercase key: "
                            + properties.getValues().get("REGION"));
        };
    }
}
~~~

Với biến môi trường `MY_PROPS_VALUES_REGION=APAC`, kết quả phần tra cứu như sau:

~~~text
region = APAC
Get lowercase key: APAC
Get uppercase key: null
~~~

Thứ tự các dòng trong `forEach` có thể không cố định vì lớp cấu hình dùng `HashMap`. Trong bài tập cần kết quả nhất quán, có thể sắp xếp entry khi in hoặc kiểm tra bằng từng khóa cụ thể.

Đối với `Map<String, String>`, `get("region")` và `get("REGION")` là hai truy vấn khác nhau. `HashMap` mặc định phân biệt chữ hoa/chữ thường của khóa String; Binder đã tạo khóa lowercase nên truy vấn với uppercase không tìm thấy entry đó.

**Điểm quan trọng:** đây là hành vi của Map **sau khi bind**. Bản thân Java `Map` không tự ý đổi tên khóa thành chữ thường; Spring Boot Binder và nguồn biến môi trường mới là nơi thực hiện việc chuẩn hóa.

## 6. Vì sao Spring Boot chuẩn hóa khóa Map từ environment variables?

Nhiều hệ điều hành và công cụ triển khai giới hạn những ký tự có thể dùng trong tên biến môi trường. Thông thường tên biến có dạng:

~~~text
LETTERS_DIGITS_AND_UNDERSCORES
~~~

Vì vậy, Spring Boot đưa ra relaxed binding để liên kết các tên như:

~~~text
MY_PROPS_VALUES_KEY
~~~

với cấu trúc property:

~~~text
my.props.values.key
~~~

Khi bind từ property source `systemEnvironment`, Spring Boot xử lý tên biến môi trường theo dạng chữ thường. Đối với field Java thông thường, việc này ít gây ảnh hưởng vì `firstName`, `first-name` hoặc `FIRSTNAME` đều có thể được liên kết đến cùng một field theo relaxed binding.

Nhưng nếu phần cuối của tên đại diện cho **dữ liệu khóa**, không phải tên field có sẵn, thì sự khác biệt trở nên rõ ràng:

~~~text
Input:     MY_PROPS_VALUES_ACCOUNTID=ABC
Map key:   accountid
Map value: ABC
~~~

Không thể suy ra chữ hoa ban đầu của từ `AccountID`, `ACCOUNTID` hay `accountId` chỉ từ khóa `accountid` đã bind. Nhiều kiểu viết có thể cùng được chuẩn hóa về một dạng.

### Phạm vi của kết luận

Kết luận “khóa Map được chuyển lowercase” áp dụng cho **binding từ biến môi trường theo cơ chế Spring Boot Binder**, đặc biệt khi dùng `@ConfigurationProperties`. Không có nghĩa mọi tên khóa trong mọi `Map` của Java hoặc mọi nguồn cấu hình đều bị chuyển lowercase.

Ví dụ `Map.of("ClientID", "ABC")` do lập trình viên tạo trực tiếp vẫn có key `ClientID`. Một YAML được viết với cú pháp bảo toàn key có thể cung cấp key khác; các trường hợp đó phải được xem xét theo nguồn và cú pháp bind tương ứng.

## 7. Không nhầm với `Environment.getProperty` và `System.getenv`

Có ba thao tác khác nhau:

1. Đọc nguyên biến môi trường của hệ điều hành.
2. Đọc giá trị một thuộc tính từ Spring `Environment`.
3. Bind nhóm thuộc tính thành một `Map` bằng `@ConfigurationProperties`.

### 7.1. `System.getenv(...)` đọc biến gốc

~~~java
String raw = System.getenv("MY_PROPS_VALUES_KEY");
~~~

Lệnh này đọc giá trị của biến có tên được cung cấp theo cơ chế hệ điều hành/JVM. Nếu biến chứa `VALUE` thì kết quả là `VALUE`. Nó **không tạo một Map với khóa `KEY`**; chuỗi `"MY_PROPS_VALUES_KEY"` là đối số do lập trình viên dùng để tìm biến.

Có thể liệt kê map biến môi trường do JVM nhìn thấy qua `System.getenv()`, nhưng cách hệ điều hành xử lý chữ hoa/chữ thường trong **tên biến** có thể khác nhau. Chẳng hạn Windows thường xử lý tên biến môi trường không phân biệt chữ hoa/chữ thường, trong khi trên hệ thống Unix chúng thường phân biệt.

### 7.2. `Environment.getProperty(...)` đọc một thuộc tính

~~~java
String value = environment.getProperty("my.props.values.key");
~~~

API này hỏi Spring `Environment` về giá trị cuối cùng của một đường dẫn thuộc tính. Nó không yêu cầu tạo bean `MyMapsProperties` và không có nghĩa toàn bộ quy tắc Map binding được áp dụng tại lời gọi đó.

### 7.3. `@ConfigurationProperties` bind nhóm khóa

~~~java
MyMapsProperties props = ...;
Map<String, String> values = props.getValues();
~~~

Đối tượng Map này phản ánh kết quả Binder đã phân tích và chuyển đổi từng tên property thành key tương ứng.

| Thao tác | Đầu vào | Kết quả chính |
| --- | --- | --- |
| `System.getenv("MY_PROPS_VALUES_KEY")` | Tên biến gốc | Chuỗi giá trị biến môi trường |
| `Environment.getProperty("my.props.values.key")` | Tên property | Chuỗi giá trị cuối cùng nếu tìm được |
| `MyMapsProperties.getValues()` | Cấu hình đã được Binder xử lý | Map với khóa được Binder tạo |

Vì vậy, thấy `System.getenv(...)` trả `"VALUE"` không chứng minh rằng Map sẽ có key viết hoa `"KEY"`. Đây là hai tầng xử lý khác nhau.

## 8. Giới hạn khi cần tên khóa có phân biệt chữ hoa/chữ thường

Giả sử một hệ thống bên ngoài yêu cầu các tên định danh chính xác:

~~~text
ClientID
clientId
CLIENTID
~~~

Trong một số giao thức hoặc API, đây có thể là ba khóa dữ liệu khác nhau. Nếu cố đưa chúng thành các đoạn tên biến môi trường rồi dựa vào relaxed binding để tạo Map, Spring Boot không có đủ thông tin để tái tạo đúng từng kiểu viết ban đầu.

Ví dụ mong đợi:

~~~java
Map<String, String> externalNames = Map.of(
        "ClientID", "A",
        "clientId", "B",
        "CLIENTID", "C"
);
~~~

Một Map Java như trên hợp lệ vì ba chuỗi key khác nhau. Nhưng nếu dùng tên environment variables để biểu diễn chúng, quy tắc chuẩn hóa tên sẽ khiến ta không thể bảo đảm giữ được cả ba tên chính xác và phân biệt chúng sau binding.

**Không nên dựa vào chữ hoa của biến môi trường để mã hóa chữ hoa của Map key**. Đổi tên biến thành `MY_PROPS_VALUES_ClientID`, `MY_PROPS_VALUES_CLIENTID` hoặc một kiểu viết hỗn hợp khác không tạo ra một cơ chế bảo toàn case được Spring Boot cam kết.

### 8.1. Ví dụ lỗi tích hợp API

Giả sử chương trình cần xây dựng payload:

~~~json
{
  "ClientID": "partner-123",
  "Mode": "Fast"
}
~~~

Nếu lấy key từ Map bind bằng biến môi trường, kết quả có thể là:

~~~json
{
  "clientid": "partner-123",
  "mode": "Fast"
}
~~~

Với API phân biệt hoa–thường của tên field, payload thứ hai có thể không được chấp nhận. Chuỗi giá trị `Fast` vẫn đúng; **tên field** mới là phần bị biến đổi.

Ví dụ này cho thấy giới hạn không chỉ ảnh hưởng đến truy vấn `map.get("ClientID")` mà còn có thể ảnh hưởng tới việc tạo JSON, tham số hệ thống ngoài hoặc các bảng ánh xạ nghiệp vụ cần đúng chính tả.

## 9. Dùng YAML với bracket notation khi cần giữ nguyên key

Đối với các nguồn cấu hình file, Spring Boot hỗ trợ **bracket notation** để bảo toàn tên khóa Map có ký tự đặc biệt. Có thể dùng nó khi tên khóa cần được biểu diễn chính xác.

Ví dụ:

~~~yaml
my:
  props:
    values:
      "[ClientID]": "partner-123"
      "[Mode]": "Fast"
      "[X-API-Key]": "demo-value"
      "[/external/key]": "enabled"
~~~

Ở YAML, các tên key có dấu ngoặc vuông `[ ... ]` nên được đặt trong dấu nháy để parser đọc chúng là chuỗi key YAML phù hợp.

Khi bind các property từ tài liệu này vào Map, bracket notation giúp Spring Boot hiểu phần nằm trong ngoặc là **key nguyên vẹn** cần giữ, thay vì tùy tiện phân tích hoặc loại bỏ ký tự theo quy tắc tên thuộc tính.

Ví dụ tra cứu dự kiến:

~~~java
values.get("ClientID");       // "partner-123"
values.get("Mode");           // "Fast"
values.get("X-API-Key");      // "demo-value"
values.get("/external/key");  // "enabled"
~~~

### Vì sao bracket notation không tự giải quyết giới hạn environment variable?

Biến môi trường hệ điều hành thông thường sử dụng chữ, số và dấu gạch dưới trong tên; tên chứa `[` hoặc `]` không phải một cách triển khai phổ quát. Quan trọng hơn, Spring Boot đã quy định **tên biến môi trường được lowercased trước khi bind Map**.

Do đó, đừng giả định có thể đặt một tên biến như `MY_PROPS_VALUES_[ClientID]` rồi Binder sẽ giữ nguyên `ClientID`. Bracket notation được tài liệu mô tả cho **khóa trong file cấu hình**; cơ chế environment variable có quy tắc riêng và vẫn có giới hạn chữ hoa.

### 9.1. Tệp `application.properties`

Cũng có thể viết với key bracket:

~~~properties
my.props.values.[ClientID]=partner-123
my.props.values.[Mode]=Fast
my.props.values.[X-API-Key]=demo-value
~~~

Ở đây dấu `[ ... ]` thể hiện cách Binder phân biệt đoạn key nguyên vẹn. Cú pháp file phù hợp hơn cho các khóa cần chữ hoa hoặc ký tự đặc biệt.

### 9.2. Key chứa dấu chấm hoặc gạch chéo

Với `Map<String, String>`, theo tài liệu Spring Boot, key chứa dấu chấm có thể được giữ trong một số trường hợp ngay cả khi không dùng ngoặc. Nhưng với `Map<String, Object>` hoặc cấu trúc Map lồng nhau, dấu chấm có thể bị xem là dấu phân tách cấp.

Ví dụ:

~~~yaml
my:
  props:
    values:
      "[api.v1]": "v1"
      "[/health]": "healthy"
~~~

Brackets làm ý định rõ ràng: `api.v1` và `/health` là hai **key dữ liệu** của Map, không phải đường dẫn thuộc tính cần tách tiếp.

Khi tên khóa cần được giữ chính xác, chọn cách viết có bracket trong file cấu hình là giải pháp rõ ý nghĩa và dễ kiểm tra hơn.

## 10. Nếu vẫn muốn cung cấp dữ liệu qua biến môi trường thì làm gì?

Khi việc bảo toàn case quan trọng, nên **tách cấu hình kỹ thuật** khỏi **tên khóa nghiệp vụ** thay vì cố lấy tên khóa nghiệp vụ từ tên biến môi trường.

### 10.1. Giải pháp A: cố định key trong mã, lấy value từ biến môi trường

Giả sử API bên ngoài yêu cầu đúng hai tên field `ClientID` và `Mode`. Ta có thể đặt cấu hình giá trị theo thuộc tính thông thường:

~~~bash
export APP_PARTNER_CLIENTID="partner-123"
export APP_PARTNER_MODE="Fast"
~~~

Bind vào các field Java:

~~~java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(String clientId, String mode) {
}
~~~

Khi cần tạo Map phục vụ API bên ngoài:

~~~java
Map<String, String> payload = Map.of(
        "ClientID", partnerProperties.clientId(),
        "Mode", partnerProperties.mode()
);
~~~

Như vậy:

- `clientId` và `mode` là field cấu hình cố định, phù hợp với relaxed binding.
- `ClientID` và `Mode` là chuỗi key cố định trong mã để đáp ứng hợp đồng của API bên ngoài.
- Người vận hành thay **giá trị** qua biến môi trường, không thay **chính tả key**.

Đây thường là cách đơn giản nhất khi tập khóa nghiệp vụ đã biết trước.

### 10.2. Giải pháp B: đưa mapping nhạy cảm case vào file cấu hình

Ví dụ file triển khai `/etc/my-service/external-keys.yml`:

~~~yaml
my:
  props:
    values:
      "[ClientID]": "partner-123"
      "[Mode]": "Fast"
~~~

Sau đó tích hợp file vào quá trình nạp Config Data bằng `spring.config.import` hoặc một location phù hợp, ví dụ trong một `application.yml` đã được nạp:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/my-service/external-keys.yml"
~~~

Dùng location bắt buộc thay vì `optional:` nếu thiếu file phải làm ứng dụng dừng khởi động. Phương án này phù hợp khi tập khóa thay đổi theo môi trường, đồng thời cần giữ nguyên chính tả khóa.

Tập khóa đã bind có thể chịu tác động của **nhiều PropertySource**. Nếu cùng key được khai báo thêm qua biến môi trường, phải kiểm tra giá trị hiệu lực và dạng key cuối cùng thay vì giả định dữ liệu file luôn thắng.

### 10.3. Giải pháp C: mang cả map dưới dạng một biến môi trường chứa JSON

Nếu hệ thống triển khai chỉ thuận tiện cấp biến môi trường và mapping có các key động phân biệt chữ hoa–chữ thường, có thể đưa **toàn bộ JSON vào giá trị của một biến duy nhất**:

~~~bash
export APP_EXTERNAL_MAP_JSON='{"ClientID":"partner-123","Mode":"Fast"}'
~~~

Trong trường hợp này, `APP_EXTERNAL_MAP_JSON` chỉ là tên một thuộc tính cố định; các chuỗi `ClientID` và `Mode` nằm **bên trong giá trị JSON** nên không phải key rút ra từ tên biến môi trường.

Ví dụ parse JSON bằng Jackson, nếu dự án có thư viện Jackson Databind:

~~~java
package com.example.configdemo;

import java.util.Map;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ExternalMapParser {

    public static Map<String, String> fromJson(String json) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        return mapper.readValue(
                json,
                new TypeReference<Map<String, String>>() {});
    }
}
~~~

Lấy giá trị bằng `Environment`:

~~~java
String json = environment.getRequiredProperty("app.external.map-json");
Map<String, String> externalMap = ExternalMapParser.fromJson(json);

System.out.println(externalMap.get("ClientID")); // partner-123
System.out.println(externalMap.get("Mode"));     // Fast
~~~

Ở đây việc bảo toàn tên key do **JSON parser và dữ liệu JSON** quyết định. Đoạn ví dụ chủ động parse giá trị JSON; không giả định Spring Boot Binder tự chuyển chuỗi JSON tùy ý thành `Map<String,String>`.

Nếu JSON không hợp lệ, parser sẽ báo lỗi. Với cấu hình triển khai có tính quan trọng, nên kiểm tra schema, trường bắt buộc và kiểu dữ liệu trước khi sử dụng.

## 11. Các giới hạn khác khi dùng tên Map key qua environment variables

Ngoài lowercasing, cách biểu diễn Map bằng environment variable còn có một số điểm cần nhớ.

### 11.1. Dấu gạch dưới đóng vai trò phân tách đường dẫn

Ví dụ:

~~~text
MY_PROPS_VALUES_REGION=APAC
~~~

Dấu `_` phân tách các phần của đường dẫn property. Đừng mặc nhiên xem một dấu gạch dưới trong tên biến là ký tự `_` nguyên vẹn của Map key. Nếu tên nghiệp vụ bắt buộc có dấu gạch dưới, nên cân nhắc YAML bracket notation hoặc truyền một giá trị dữ liệu có cấu trúc.

### 11.2. Dấu gạch ngang trong tên thuộc tính được bỏ khi đổi thành env var

Tên property chuẩn:

~~~text
app.client.retry-count
~~~

trở thành:

~~~text
APP_CLIENT_RETRYCOUNT
~~~

Do đó, tên biến môi trường không thể tự mô tả mọi dấu phân cách nguyên thủy của tên khóa nghiệp vụ. Đối với những key cố định đã định nghĩa qua field Java, relaxed binding xử lý việc chuẩn hóa này tốt. Với key động cần bảo toàn từng ký tự, cơ chế đó có thể không phù hợp.

### 11.3. Tên có dấu chấm, dấu gạch chéo hoặc ký tự đặc biệt

Map key như `a.b`, `/health` hay `X-API-Key` có thể chứa ký tự mà tên env var không biểu diễn trực tiếp hoặc có thể bị phân tích thành nhiều cấp property. File cấu hình với bracket notation là cách rõ ràng để chỉ định đây là **một key duy nhất**.

### 11.4. Khả năng trùng tên sau chuẩn hóa

Giả sử tên key ngoài hệ thống phân biệt:

~~~text
ClientID
clientId
clientid
~~~

Sau bước chuẩn hóa trong luồng bind environment variables, nhiều cách viết có thể không còn phân biệt được. Không nên thiết kế cấu hình dựa trên việc các tên biến chỉ khác chữ hoa/thường sẽ tạo ra những Map entry độc lập.

Nếu cần hai key nghiệp vụ khác nhau theo case, hãy sử dụng một định dạng truyền dữ liệu lưu được tên key nguyên bản.

## 12. Phân biệt `Map<String, String>` với `Map<String, Object>`

Cơ chế bind Map còn phụ thuộc **kiểu của value**. Ví dụ:

~~~properties
my.map.a.b=c
~~~

Với `Map<String, String>`, tài liệu Spring Boot mô tả trường hợp dấu chấm có thể được giữ trong một key scalar, tương ứng key `a.b`.

Nhưng với `Map<String, Object>`, dấu chấm có thể dẫn đến cấu trúc Map lồng nhau:

~~~text
a
└── b = c
~~~

Cách viết bracket notation có chủ đích:

~~~properties
my.map.[a.b]=c
~~~

giúp thể hiện key `a.b` là một phần tử duy nhất thay vì hai cấp.

Cần phân biệt hai câu hỏi:

1. **Key có bị tách hoặc mất ký tự không?** Điều này phụ thuộc bracket notation, kiểu Map và cách phân tích property path.
2. **Key có giữ nguyên chữ hoa khi đến từ biến môi trường không?** Trong binding Map từ environment variables theo tài liệu Spring Boot 3.3, key vẫn lowercase.

Brackets hỗ trợ bảo toàn key của những nguồn có thể mô tả cú pháp này; chúng **không đảo ngược** việc lowercasing tên biến môi trường.

## 13. Thực hành trên Linux/macOS và Windows

### 13.1. Linux/macOS

Ở thư mục có JAR ứng dụng:

~~~bash
export MY_PROPS_VALUES_KEY="VALUE"
export MY_PROPS_VALUES_REGION="APAC"
java -jar config-demo.jar
~~~

Kiểm tra Map bằng bean `MyMapsProperties`. Các key dự kiến là `key` và `region`.

Khi chạy nhiều lần trong cùng shell, biến đã export vẫn có thể tồn tại. Có thể dọn biến khi hoàn thành:

~~~bash
unset MY_PROPS_VALUES_KEY MY_PROPS_VALUES_REGION
~~~

### 13.2. Windows PowerShell

~~~powershell
$env:MY_PROPS_VALUES_KEY = "VALUE"
$env:MY_PROPS_VALUES_REGION = "APAC"
java -jar config-demo.jar
~~~

Xóa các biến của phiên PowerShell sau khi thực hành:

~~~powershell
Remove-Item Env:MY_PROPS_VALUES_KEY
Remove-Item Env:MY_PROPS_VALUES_REGION
~~~

Ví dụ được mô tả dưới góc nhìn quá trình Spring Boot lấy các biến môi trường đã được tiến trình Java nhận được. Quy tắc đặt tên và xử lý hoa/thường của chính hệ điều hành có thể khác nhau; nội dung bài tập tập trung vào kết quả Binder.

### 13.3. Docker Compose

Ví dụ cấu hình biến môi trường cho ứng dụng:

~~~yaml
services:
  app:
    image: example/config-demo:latest
    environment:
      MY_PROPS_VALUES_KEY: "VALUE"
      MY_PROPS_VALUES_REGION: "APAC"
~~~

Cả hai biến được truyền vào container như các cặp tên–giá trị. Khi Spring Boot bind vào `MyMapsProperties`, các entry vẫn có key lowercase. Dù file Compose dùng chữ hoa trong tên biến, tên key trong Map không vì vậy được bảo toàn uppercase.

Nếu muốn truyền JSON trong một biến:

~~~yaml
services:
  app:
    image: example/config-demo:latest
    environment:
      APP_EXTERNAL_MAP_JSON: '{"ClientID":"partner-123","Mode":"Fast"}'
~~~

Những key bên trong JSON là nội dung giá trị biến; có thể parse bằng Jackson như hướng dẫn phía trên.

## 14. Quan sát và chẩn đoán khi Map không có key mong đợi

Một lỗi phổ biến:

~~~java
String clientId = properties.getValues().get("ClientID");
~~~

trả về `null`, dù đã khai báo:

~~~bash
export MY_PROPS_VALUES_CLIENTID="partner-123"
~~~

Trong trường hợp này, nên kiểm tra:

1. Biến môi trường đã thực sự được cấp cho **tiến trình Java** chưa?
2. Tên tiền tố `my.props.values` có khớp `@ConfigurationProperties(prefix="my.props")` và field `values` không?
3. Có phải chương trình đang tìm key viết hoa `ClientID` trong khi Binder tạo key `clientid`?
4. Có nguồn cấu hình khác cung cấp cùng property, cùng key hoặc ghi đè value không?
5. Có ký tự `_`, `-`, `.` hoặc dấu `/` trong tên key mà cách biểu diễn biến môi trường không bảo toàn được không?

Để quan sát tập key sau bind mà tránh lộ value nhạy cảm:

~~~java
@Bean
ApplicationRunner showBoundKeys(MyMapsProperties properties) {
    return args -> {
        System.out.println("Bound keys:");
        properties.getValues().keySet().stream()
                .sorted()
                .forEach(System.out::println);
    };
}
~~~

Đặt bean trong một lớp `@Configuration` hoặc `@SpringBootApplication`, với import `ApplicationRunner` và `Bean` cần thiết.

Khi chẩn đoán, **in tên khóa** có thể đủ để tìm vấn đề casing. Không nên in toàn bộ giá trị của Map nếu Map chứa token, mật khẩu hoặc dữ liệu nhạy cảm.

### Truy vấn với key lowercase

Nếu ứng dụng xác định Map key được chuẩn hóa từ environment variables, có thể chủ động truy vấn tên lowercase:

~~~java
String value = properties.getValues().get("clientid");
~~~

Cách này giải quyết tình huống tra cứu trong phạm vi Map đã có. Tuy nhiên, nếu key phải được gửi sang hệ thống ngoài dưới tên `ClientID` thì vẫn cần ánh xạ trở lại tên chính xác theo hợp đồng của hệ thống ngoài; không nên chuyển cả payload sang lowercase.

## 15. Những hiểu nhầm thường gặp

### “Biến môi trường tên uppercase nên Map key cũng uppercase”

Sai đối với binding Map từ environment variables qua Spring Boot Binder. Trong ví dụ `MY_PROPS_VALUES_KEY=VALUE`, key là `key`.

### “Spring Boot lowercase cả giá trị”

Không đúng. Giá trị `VALUE` vẫn là `VALUE`; chuỗi `Prod-US-West` vẫn giữ nguyên chữ hoa/chữ thường khi được bind như String, trừ khi ứng dụng có chuyển đổi dữ liệu riêng.

### “Dùng bracket notation trong tên biến môi trường sẽ giữ được key uppercase”

Không nên dựa vào giả định đó. Bracket notation được hỗ trợ để bảo toàn key trong các nguồn cấu hình như YAML/properties; environment variable binding có giới hạn riêng và tên biến được lowercased trước khi tạo key Map.

### “Đọc `System.getenv` giống với `@ConfigurationProperties`”

Hai cách này khác nhau. `System.getenv` trả giá trị một biến có tên xác định; Binder phân tích nhiều thuộc tính và xây dựng Map với các key đã chuẩn hóa.

### “Đổi Map thành `TreeMap` sẽ tự giữ key uppercase”

Kiểu triển khai Map không phục hồi thông tin chữ hoa đã mất ở bước bind. `TreeMap` còn có quy tắc sắp xếp/comparator riêng, nhưng không tự suy ra key gốc từ env var đã chuẩn hóa.

### “Chỉ cần ép uppercase tất cả key khi đọc”

Đổi `clientid` thành `CLIENTID` có thể hữu ích nếu hợp đồng của ứng dụng chỉ dùng tên uppercase chuẩn. Nhưng nó **không phục hồi được** tên chính xác ban đầu như `ClientID` hay `clientId`. Nếu hệ thống cần nhiều tên phân biệt case, phải giữ metadata hoặc khai báo ánh xạ tên chính xác từ nguồn khác.

## 16. Câu hỏi thực hành

### Bài 1: Dự đoán nội dung Map

Với `MyMapsProperties`:

~~~bash
export MY_PROPS_VALUES_ENV="PROD"
export MY_PROPS_VALUES_REGION="AsiaPacific"
~~~

Hãy xác định kết quả của:

~~~java
values.get("env");
values.get("ENV");
values.get("region");
values.get("REGION");
~~~

**Đáp án:** `"PROD"`, `null`, `"AsiaPacific"`, `null`, giả định không có nguồn cấu hình khác tạo thêm các key tương ứng.

### Bài 2: Bảo toàn giá trị, không bảo toàn tên key

Cho:

~~~bash
export MY_PROPS_VALUES_CLIENTID="AbC-987"
~~~

Khi bind qua `@ConfigurationProperties`, hãy xác định key và value.

**Đáp án:** key `clientid`, value `AbC-987`.

### Bài 3: Sử dụng bracket notation

Viết YAML để `Map<String, String>` chứa đúng hai key:

~~~text
ClientID
X-API-Key
~~~

**Gợi ý lời giải:**

~~~yaml
my:
  props:
    values:
      "[ClientID]": "partner-123"
      "[X-API-Key]": "demo-value"
~~~

### Bài 4: Tạo payload bên ngoài

Một REST API yêu cầu JSON field `ClientID`. Cấu hình từ biến môi trường là `APP_PARTNER_CLIENTID=partner-123`. Hãy bind giá trị vào `PartnerProperties.clientId` rồi tạo payload bằng key literal `"ClientID"`. Giải thích vì sao cách này bảo toàn tên field của API.

### Bài 5: Trường hợp nhiều key chỉ khác chữ hoa

Hệ thống yêu cầu đồng thời `ClientID` và `clientId`. Có nên tạo hai biến môi trường chỉ khác kiểu viết hoa để tự bind vào một Map không?

**Đáp án:** Không nên. Hãy dùng YAML/properties với key được mô tả rõ, một giá trị JSON có cấu trúc và parse riêng, hoặc ánh xạ các field cố định sang tên bên ngoài.

## 17. Ghi nhớ

- Với Spring Boot 3.3, khi bind **Map từ environment variables** qua `@ConfigurationProperties`, **tên key của Map là lowercase**.
- **Giá trị** của biến môi trường được giữ nguyên chữ hoa/chữ thường; `KEY=VALUE` tạo key `key` với value `VALUE` trong ví dụ tương ứng.
- Relaxed binding phù hợp để ánh xạ tên thuộc tính Spring Boot sang biến môi trường, nhưng không bảo đảm bảo toàn tên khóa nghiệp vụ động có phân biệt hoa/thường.
- `System.getenv`, `Environment.getProperty` và `@ConfigurationProperties` là ba tầng API khác nhau; đọc giá trị từ biến gốc không đồng nghĩa với key của Map sau bind.
- Khi cần key giữ nguyên như `ClientID`, `X-API-Key` hoặc `/health`, cân nhắc YAML/properties với bracket notation hoặc lưu tên key bên trong một định dạng dữ liệu như JSON.
- Nếu bên ngoài cần một tập tên field cố định, hãy bind **giá trị** qua cấu hình và dùng **tên key chính xác** khi xây dựng payload.
- Khi chẩn đoán, kiểm tra cả **key sau bind** và **value hiệu lực**, đồng thời phân biệt ảnh hưởng của những nguồn cấu hình khác.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration, Binding Maps From Environment Variables](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables)
- [Spring Boot 3.3 — Externalized Configuration, Binding Maps](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
