# Tệp `application.properties` và `application.yml`

Spring Boot cho phép tách cấu hình khỏi mã nguồn để cùng một ứng dụng có thể chạy ở môi trường phát triển, kiểm thử và production với những giá trị khác nhau. Hai định dạng phổ biến nhất là **`application.properties`** và **`application.yml`** (hoặc phần mở rộng chuẩn YAML là **`application.yaml`**). Spring Boot nạp các tệp này vào `Environment`, sau đó các bean có thể đọc giá trị qua `@Value`, `Environment` hoặc binding có kiểu bằng `@ConfigurationProperties`.

Trong module **SPRING_CLOUD_CORE**, cấu hình bên ngoài là nền tảng để các ứng dụng phân tán khai báo tên dịch vụ, địa chỉ registry, timeout, endpoint phụ thuộc và những tùy chọn Spring Cloud. Hiểu đúng hai định dạng tệp này giúp tránh lỗi cấu hình bị ghi đè, profile không được kích hoạt, YAML sai thụt lề hoặc ứng dụng vẫn dùng giá trị mặc định ngoài dự kiến.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Viết cùng một cấu hình bằng `application.properties` và `application.yml`.
2. Giải thích cách Spring Boot tìm, nạp và hợp nhất cấu hình trong classpath và bên ngoài ứng dụng.
3. Tạo file theo profile như `application-dev.yml` và hiểu thứ tự ghi đè.
4. Dùng placeholder, biến môi trường, danh sách và cấu trúc lồng nhau đúng cách.
5. Chọn `spring.config.location`, `spring.config.additional-location`, `spring.config.name` và `spring.config.import` phù hợp.
6. Kiểm tra giá trị thực tế trong `Environment` và xử lý những lỗi thường gặp khi nạp cấu hình.
7. Giải thích mối liên hệ giữa file cấu hình Spring Boot, Config Client và cơ chế refresh của Spring Cloud.

## 2. Hai định dạng, cùng một Environment

### 2.1. `application.properties`: dạng key-value

Mỗi dòng biểu diễn một thuộc tính. Cấu trúc phân cấp được viết bằng dấu chấm trong tên key:

~~~properties
spring.application.name=orders-service
server.port=8080

clients.inventory.base-url=http://inventory-service
clients.inventory.connect-timeout=250ms
clients.inventory.read-timeout=700ms

management.endpoints.web.exposure.include=health,info
~~~

Ưu điểm của `.properties` là đơn giản, dễ tìm kiếm, phù hợp với một số cấu hình phẳng hoặc khi cần khai báo từng key rõ ràng. Nhược điểm là các nhóm thuộc tính lồng nhau, danh sách object và map phức tạp có thể khó đọc khi file lớn.

### 2.2. `application.yml`: dạng phân cấp

YAML biểu diễn cấu trúc bằng thụt lề. Cùng cấu hình trên có thể viết:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

clients:
  inventory:
    base-url: http://inventory-service
    connect-timeout: 250ms
    read-timeout: 700ms

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Các key lồng nhau trong YAML được chuyển thành key phẳng khi đưa vào Spring `Environment`. Ví dụ `clients.inventory.read-timeout` là tên thuộc tính có thể đọc từ cả hai định dạng.

| Tiêu chí | `.properties` | `.yml` / `.yaml` |
| --- | --- | --- |
| Cách biểu diễn | `key=value` hoặc `key:value` | Cấu trúc lồng nhau bằng thụt lề |
| Nhóm thuộc tính | Dùng tiền tố phân tách bằng dấu chấm | Dùng các cấp YAML |
| Danh sách | Có thể dùng chỉ số `[0]`, `[1]` hoặc dạng phù hợp với binder | Dùng dấu `-` |
| Đọc cấu hình nhiều cấp | Có thể dài khi nhiều key chung tiền tố | Thường dễ nhìn hơn |
| Chia nhiều tài liệu | Dùng separator đặc biệt `#---` | Dùng separator YAML `---` |
| Công cụ nạp | Spring Boot Config Data | Spring Boot Config Data và SnakeYAML |

Hai định dạng đều có thể cung cấp cùng một giá trị cho `Environment`; việc chọn định dạng là lựa chọn biểu diễn. Một dự án nên thống nhất một định dạng chính để giảm nhầm lẫn.

### 2.3. Không nên khai báo cả hai định dạng cùng tên trong một vị trí

Nếu cùng một vị trí có `application.properties` và `application.yml`/`application.yaml`, Spring Boot ưu tiên **`.properties`**. Điều này dễ gây nhầm khi người phát triển sửa YAML nhưng ứng dụng vẫn lấy giá trị từ file properties cùng vị trí.

Ví dụ:

~~~text
src/main/resources/
  application.properties
  application.yml
~~~

Nếu hai file cùng khai báo `server.port`, giá trị trong `application.properties` sẽ được ưu tiên tại cùng vị trí cấu hình. Hãy chọn một định dạng chính hoặc xóa cấu hình trùng để hành vi rõ ràng. Tài liệu Spring Boot khuyến nghị sử dụng một định dạng thống nhất cho toàn ứng dụng.

## 3. Cách Spring Boot tìm file cấu hình

### 3.1. Các vị trí mặc định

Spring Boot tự động tìm các tệp `application.properties`, `application.yaml` và các biến thể YAML tương ứng tại các vị trí mặc định. Với ứng dụng chạy theo cách thông thường, các nhóm vị trí gồm:

1. Gốc classpath, ví dụ `src/main/resources/application.yml` sau khi đóng gói.
2. `classpath:/config/`.
3. Thư mục làm việc hiện tại, thường là thư mục nơi lệnh chạy ứng dụng được thực thi.
4. Thư mục `./config/` bên dưới thư mục làm việc.
5. Các thư mục con trực tiếp bên dưới `./config/`.

Các vị trí được xét theo thứ tự; những giá trị ở vị trí có độ ưu tiên cao hơn có thể ghi đè giá trị đã nạp trước đó. Cấu hình nằm ngoài JAR thường được dùng để điều chỉnh ứng dụng theo môi trường triển khai mà không cần build lại artifact.

Ví dụ cấu trúc:

~~~text
orders-service/
  config/
    application.yml
    application-prod.yml
  orders-service.jar
~~~

Khi chạy từ thư mục `orders-service`, Spring Boot có thể tìm cấu hình trong thư mục `config/` bên ngoài JAR. File `application-prod.yml` được xét khi profile `prod` đang hoạt động.

**Lưu ý:** vị trí tương đối phụ thuộc *working directory*. Chạy cùng một JAR từ hai thư mục khác nhau có thể làm Spring Boot tìm thấy các file bên ngoài khác nhau.

### 3.2. Cấu hình classpath và cấu hình bên ngoài

Một cách tổ chức thường dùng:

- `src/main/resources/application.yml`: giá trị mặc định dùng chung, đóng gói cùng JAR.
- `./config/application.yml`: cấu hình của môi trường triển khai, nằm ngoài JAR.
- `./config/application-prod.yml`: giá trị chỉ áp dụng cho profile `prod`.

Ví dụ file trong classpath:

~~~yaml
spring:
  application:
    name: orders-service

clients:
  inventory:
    connect-timeout: 200ms
    read-timeout: 500ms
~~~

File ngoài JAR:

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    read-timeout: 900ms
~~~

Các giá trị không được ghi đè vẫn lấy từ nguồn cấu hình có độ ưu tiên thấp hơn, còn `read-timeout` được thay bằng giá trị của file ngoài. Cấu hình có thể được đưa vào container hoặc máy chủ qua volume mount, thư mục triển khai hay công cụ quản lý cấu hình.

### 3.3. Đổi tên hoặc vị trí tìm file

Ba thuộc tính cần phân biệt:

| Thuộc tính | Tác dụng |
| --- | --- |
| `spring.config.name` | Đổi tên cơ sở mà Spring Boot dùng khi tìm file; ví dụ `myservice` để tìm `myservice.properties` hoặc `myservice.yaml` |
| `spring.config.location` | Chỉ định các vị trí cần tìm và **thay thế** các vị trí mặc định |
| `spring.config.additional-location` | Bổ sung vị trí mới bên cạnh các vị trí mặc định |

Có thể truyền chúng từ command line:

~~~bash
java -jar orders-service.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=optional:file:./deploy-config/
~~~

Hoặc dùng biến môi trường:

~~~bash
SPRING_CONFIG_NAME=orders
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:./deploy-config/
~~~

Các thuộc tính điều khiển việc tìm file được đọc rất sớm. Nên cung cấp chúng qua environment variable, JVM system property hoặc command-line argument trước khi Config Data được nạp. Đặt `spring.config.location` bên trong chính file mà nó cần quyết định tìm kiếm thường là quá muộn.

Nếu location là thư mục, đường dẫn cần kết thúc bằng `/`. Nếu là file cụ thể, Spring Boot nạp file được chỉ định. Các location có thể phân tách bằng dấu phẩy; thứ tự khai báo ảnh hưởng thứ tự ghi đè.

**Khác biệt quan trọng:**

- Dùng `spring.config.location` khi muốn tự xác định tập vị trí cấu hình.
- Dùng `spring.config.additional-location` khi muốn giữ vị trí mặc định và thêm cấu hình triển khai ở bên ngoài.

### 3.4. Vị trí tùy chọn và lỗi thiếu file

Nếu một Config Data location được chỉ định nhưng không tồn tại, mặc định ứng dụng có thể thất bại khi khởi động. Thêm tiền tố `optional:` khi file hoặc location thực sự không bắt buộc:

~~~bash
java -jar orders-service.jar \
  --spring.config.additional-location=optional:file:./local-overrides/
~~~

Không nên đánh dấu mọi cấu hình là optional. Nếu ứng dụng cần một endpoint hoặc thông tin bảo mật để phục vụ nghiệp vụ, tiếp tục khởi động với giá trị mặc định không phù hợp có thể gây lỗi muộn hơn và khó chẩn đoán hơn.

## 4. Cấu hình theo profile

Profile cho phép dùng chung mã nguồn nhưng thay đổi giá trị theo môi trường hoặc mục đích chạy.

### 4.1. File theo profile

Tên file theo quy ước:

~~~text
application.yml
application-dev.yml
application-test.yml
application-staging.yml
application-prod.yml
~~~

File `application.yml` chứa mặc định chung:

~~~yaml
spring:
  application:
    name: orders-service

clients:
  inventory:
    connect-timeout: 200ms
    read-timeout: 500ms
    base-url: http://localhost:8081
~~~

File `application-prod.yml` chỉ khai báo phần cần thay đổi:

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    read-timeout: 900ms
~~~

Khi profile `prod` hoạt động, các giá trị trong `application-prod.yml` ghi đè giá trị tương ứng trong file không theo profile. Những key không được khai báo trong file profile tiếp tục lấy từ cấu hình chung hoặc các nguồn khác.

### 4.2. Kích hoạt profile

Có thể kích hoạt bằng command line:

~~~bash
java -jar orders-service.jar --spring.profiles.active=prod
~~~

Hoặc bằng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Trong môi trường phát triển, có thể đặt mặc định trong `application.yml`:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Không nên đóng cứng `prod` trong file cấu hình đóng gói của ứng dụng. Môi trường triển khai nên chủ động chọn profile qua cấu hình chạy để tránh vô tình khởi động nhầm chế độ.

Nếu không có active profile, Spring `Environment` sử dụng default profile (thông thường tên là `default`). Khi nhiều profile được kích hoạt, profile được xét sau có thể ghi đè giá trị của profile trước theo quy tắc last-wins.

### 4.3. Thứ tự ghi đè cần nhớ

Có hai cấp độ cần phân biệt:

- **Thứ tự nguồn cấu hình tổng thể:** command-line arguments, environment variables, system properties và các nguồn khác có độ ưu tiên riêng so với Config Data.
- **Thứ tự bên trong Config Data:** file đóng gói, file theo profile, file bên ngoài và file bên ngoài theo profile được xét theo thứ tự quy định.

Ví dụ rút gọn:

| Nguồn | `clients.inventory.read-timeout` |
| --- | ---: |
| `classpath:/application.yml` | `500ms` |
| `classpath:/application-prod.yml` | `700ms` |
| `./config/application.yml` | `800ms` |
| `./config/application-prod.yml` | `900ms` |
| Environment variable `CLIENTS_INVENTORY_READTIMEOUT` | `1s` |
| Command line `--clients.inventory.read-timeout=1200ms` | `1200ms` |

Với các nguồn phổ biến trên, giá trị cuối cùng là `1200ms`. Nếu bỏ command line, biến môi trường có thể ghi đè Config Data. Bảng này là ví dụ minh họa, không phải danh sách đầy đủ mọi `PropertySource` hoặc mọi quy tắc kiểm thử.

**Một điểm dễ nhầm:** thứ tự vị trí trong `spring.config.location` và khái niệm *location group* có thể ảnh hưởng thứ tự profile-specific file. Với cấu hình nhiều thư mục, dấu phẩy và dấu chấm phẩy không luôn tương đương. Khi cần phối hợp nhiều location, xem phần Profile Specific Files trong tài liệu Spring Boot đúng phiên bản.

## 5. Cú pháp của `application.properties`

### 5.1. Key, value và dấu phân cách

Một thuộc tính có thể được viết theo dạng:

~~~properties
spring.application.name=orders-service
server.port=8080
clients.inventory.base-url=http://localhost:8081
clients.inventory.read-timeout=700ms
~~~

Dấu `=` là cách viết phổ biến; file properties cũng hỗ trợ dấu `:` trong cú pháp key-value. Dùng key theo dạng chữ thường, phân tách từ bằng dấu gạch ngang (`kebab-case`) để nhất quán với quy ước Spring Boot.

Comment thường bắt đầu bằng `#` hoặc `!`:

~~~properties
# Timeout cho Inventory Service
clients.inventory.connect-timeout=250ms
! Đây là comment theo cú pháp properties
~~~

Nếu giá trị có ký tự cần escape hoặc khoảng trắng đặc biệt, hãy dùng quy tắc escape của Java properties. Với giá trị phức tạp, cần kiểm tra kết quả thực tế trong `Environment` thay vì dựa vào cách nhìn trên file.

### 5.2. Danh sách và key có chỉ số

Có thể khai báo danh sách bằng các chỉ số:

~~~properties
clients.inventory.zones[0]=north
clients.inventory.zones[1]=south
clients.inventory.zones[2]=central
~~~

Một số trường hợp đơn giản có thể dùng dạng phân tách bằng dấu phẩy:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics
~~~

Khi bind vào `List`, cách biểu diễn theo chỉ số giúp xác định rõ từng phần tử, đặc biệt với danh sách object lồng nhau.

### 5.3. Placeholder và giá trị mặc định

Spring Boot hỗ trợ placeholder `${...}` trong giá trị thuộc tính:

~~~properties
clients.inventory.base-url=${INVENTORY_URL:http://localhost:8081}
clients.inventory.read-timeout=${INVENTORY_READ_TIMEOUT:700ms}
spring.application.name=${SERVICE_NAME:orders-service}
~~~

Cú pháp `${TEN_KEY:gia_tri_mac_dinh}` cho phép dùng giá trị mặc định nếu key được tham chiếu không tồn tại. Có thể tham chiếu thuộc tính khác:

~~~properties
app.region=ap-southeast-1
app.instance-label=${spring.application.name}-${app.region}
~~~

Placeholder giúp tránh lặp lại giá trị, nhưng cần tránh tạo chuỗi tham chiếu vòng. Với thông tin bí mật như mật khẩu và token, nên lấy từ secret store hoặc nguồn cấu hình bảo mật phù hợp; không commit secret thật vào repository.

## 6. Cú pháp của `application.yml`

### 6.1. Thụt lề và cấu trúc lồng nhau

YAML dùng khoảng trắng để biểu diễn cấp cấu trúc. Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080
~~~

Quy tắc thực hành:

- Dùng dấu cách, không dùng tab để thụt lề.
- Giữ mức thụt lề nhất quán trong cùng một cấu trúc.
- Sau dấu `:` của key phải có khoảng trắng khi khai báo scalar theo cú pháp thông thường.
- Mỗi cấp lồng nhau phải thụt vào đúng số khoảng trắng.
- Đặt dấu nháy cho chuỗi có ký tự đặc biệt hoặc dễ bị parser hiểu thành kiểu dữ liệu khác.

Một lỗi thường gặp là thụt lề sai khiến `read-timeout` trở thành thuộc tính của một nhóm khác hoặc file không parse được. Nếu nghi ngờ YAML, hãy dùng IDE có YAML validation và kiểm tra log lỗi lúc khởi động.

### 6.2. Chuỗi, boolean, số và thời lượng

YAML hỗ trợ các kiểu scalar. Ví dụ:

~~~yaml
clients:
  inventory:
    enabled: true
    port: 8081
    connect-timeout: 250ms
    read-timeout: 700ms
    base-url: "https://inventory.internal.example/api"
    description: "Inventory service for orders"
~~~

Một số giá trị có thể được parse thành boolean, số hoặc kiểu scalar theo quy tắc YAML. Nếu muốn giữ nguyên một giá trị như chuỗi, hãy đặt trong dấu nháy:

~~~yaml
feature:
  release-code: "0012"
  display-value: "on"
  label: "2026-11"
~~~

Với URL, biểu thức, password hoặc chuỗi có `#`, dấu hai chấm và ký tự đặc biệt, dùng dấu nháy giúp ý định rõ hơn. Không đưa secret thực vào file cấu hình được commit.

### 6.3. Danh sách

YAML biểu diễn danh sách bằng dấu gạch ngang:

~~~yaml
clients:
  inventory:
    zones:
      - north
      - south
      - central
~~~

Cấu trúc này tương ứng với các property key có chỉ số:

~~~properties
clients.inventory.zones[0]=north
clients.inventory.zones[1]=south
clients.inventory.zones[2]=central
~~~

Danh sách object cũng có thể biểu diễn trực quan:

~~~yaml
clients:
  downstream:
    - name: inventory
      base-url: http://inventory-service
      read-timeout: 700ms
    - name: pricing
      base-url: http://pricing-service
      read-timeout: 500ms
~~~

Khi bind vào Java object, kiểu đích cần tương ứng với cấu trúc danh sách. Không nên trộn các phần tử khác kiểu trong cùng một list nếu muốn binding ổn định.

### 6.4. Map và key đặc biệt

Map có thể được viết theo dạng:

~~~yaml
routing:
  service-urls:
    inventory: http://inventory-service
    pricing: http://pricing-service
~~~

Khi key map có ký tự đặc biệt cần giữ nguyên, dùng cú pháp ngoặc vuông và đặt trong dấu nháy:

~~~yaml
routing:
  metadata:
    "[/v1/inventory]": inventory
    "[/v1/pricing]": pricing
~~~

Nếu không dùng bracket notation trong những trường hợp cần thiết, một số ký tự trong key có thể bị loại bỏ khi binding. Hãy xem quy tắc map binding của Spring Boot nếu map key chứa dấu `/`, dấu chấm hoặc ký tự ngoài nhóm chữ/số.

### 6.5. Placeholder trong YAML

Cùng cú pháp placeholder như `.properties`:

~~~yaml
spring:
  application:
    name: "${SERVICE_NAME:orders-service}"

clients:
  inventory:
    base-url: "${INVENTORY_URL:http://localhost:8081}"
    read-timeout: "${INVENTORY_READ_TIMEOUT:700ms}"
~~~

Giá trị sau khi phân giải được đưa vào `Environment` và có thể bind vào bean. Với cấu hình phức tạp, nên kiểm tra kiểu cuối cùng sau binding, nhất là `Duration`, `DataSize`, danh sách và map.

## 7. Dùng `@ConfigurationProperties` để tiêu thụ cấu hình

File cấu hình chỉ là nguồn dữ liệu. Ứng dụng cần một cách đọc các giá trị đó. Với một nhóm thuộc tính có cấu trúc, `@ConfigurationProperties` thường phù hợp hơn việc đặt nhiều `@Value` rời rạc.

### 7.1. Định nghĩa lớp cấu hình có kiểu

Giả sử `application.yml` có:

~~~yaml
clients:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 250ms
    read-timeout: 700ms
    zones:
      - north
      - south
~~~

Có thể bind vào Java record:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "clients.inventory")
public record InventoryClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        List<String> zones
) {}
~~~

Để đăng ký record, có thể bật `@ConfigurationPropertiesScan` ở lớp ứng dụng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Hoặc đăng ký rõ lớp cấu hình bằng `@EnableConfigurationProperties(InventoryClientProperties.class)` trong một cấu hình phù hợp.

### 7.2. Vì sao nên dùng kiểu dữ liệu?

- Tập hợp các key cùng một nhóm vào một object.
- Chuyển đổi `250ms` thành `Duration` và URL thành `URI`.
- Hỗ trợ binding cấu trúc lồng nhau, list và map.
- Dễ kiểm thử và tài liệu hóa cấu hình.
- Có thể bổ sung validation để phát hiện cấu hình không hợp lệ khi khởi động.

Ví dụ, một giá trị timeout âm hoặc URL không hợp lệ nên được phát hiện sớm thay vì gây lỗi trong request đầu tiên. Khi dùng Jakarta Bean Validation, cần dependency validation phù hợp và annotation tương ứng; không giả định validation tự có chỉ vì khai báo `@ConfigurationProperties`.

### 7.3. Canonical property name

Nên dùng tên thuộc tính ở dạng **kebab-case chữ thường** trong file và placeholder, ví dụ:

~~~properties
clients.inventory.read-timeout=700ms
~~~

Spring Boot hỗ trợ relaxed binding nên có thể nhận một số cách viết tương đương như camelCase hoặc underscore tùy property source. Tuy vậy, chọn một dạng canonical giúp cấu hình, placeholder và biến môi trường nhất quán.

## 8. Biến môi trường và cấu hình khi triển khai

Trong môi trường container hoặc cloud, biến môi trường thường được dùng để truyền giá trị thay đổi giữa các lần triển khai mà không sửa file trong JAR.

Spring Boot chuyển tên thuộc tính canonical sang tên biến môi trường theo các quy tắc chính:

1. Đổi dấu chấm `.` thành dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-`.
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ:

| Property name | Environment variable |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `clients.inventory.read-timeout` | `CLIENTS_INVENTORY_READTIMEOUT` |
| `server.port` | `SERVER_PORT` |
| `spring.config.additional-location` | `SPRING_CONFIG_ADDITIONALLOCATION` |

Với phần tử list, chỉ số được đặt giữa hai dấu gạch dưới, ví dụ `my.service[0].other` tương ứng với `MY_SERVICE_0_OTHER`.

Trên Windows PowerShell, có thể đặt biến môi trường cho tiến trình hiện tại:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:SERVER_PORT = "9090"
java -jar .\orders-service.jar
~~~

Trên Linux/macOS shell:

~~~bash
SPRING_PROFILES_ACTIVE=prod SERVER_PORT=9090 java -jar orders-service.jar
~~~

Biến môi trường là nguồn cấu hình bên ngoài, nhưng không tự động biến file thành secret store. Tránh ghi password vào lịch sử shell, log CI hoặc manifest công khai. Với nền tảng như Kubernetes, có thể dùng Secret/ConfigMap mount hoặc giải pháp quản lý secret thích hợp.

## 9. Nhiều tài liệu trong một file

Spring Boot hỗ trợ chia một file vật lý thành nhiều logical document. Các document được xử lý theo thứ tự từ trên xuống; document phía sau có thể ghi đè thuộc tính của document phía trước.

### 9.1. Multi-document YAML

Dùng ba dấu gạch ngang `---` để bắt đầu document mới:

~~~yaml
spring:
  application:
    name: orders-service

clients:
  inventory:
    read-timeout: 500ms
---
spring:
  config:
    activate:
      on-profile: prod

clients:
  inventory:
    read-timeout: 900ms
~~~

Document thứ hai chỉ được kích hoạt khi profile `prod` phù hợp với biểu thức `on-profile`. Khi chạy ở profile khác, giá trị chung `500ms` tiếp tục được sử dụng.

### 9.2. Multi-document properties

Với `.properties`, dùng separator đặc biệt `#---`:

~~~properties
spring.application.name=orders-service
clients.inventory.read-timeout=500ms
#---
spring.config.activate.on-profile=prod
clients.inventory.read-timeout=900ms
~~~

Separator phải bắt đầu ở đầu dòng, không có khoảng trắng đứng trước và phải có chính xác ba dấu gạch ngang sau ký hiệu comment. Quy tắc separator đặc biệt này thuộc cơ chế multi-document của Spring Boot, không phải cú pháp chung của Java properties.

### 9.3. Điều kiện kích hoạt document

Một document có thể dùng:

- `spring.config.activate.on-profile`: chỉ kích hoạt khi profile expression phù hợp.
- `spring.config.activate.on-cloud-platform`: chỉ kích hoạt khi Spring Boot nhận diện cloud platform tương ứng.

Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
---
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes

clients:
  inventory:
    base-url: http://inventory.default.svc.cluster.local
~~~

Document trên cần thỏa điều kiện profile và cloud platform như cấu hình. Multi-document hữu ích khi muốn giữ các biến thể nhỏ trong cùng file, nhưng nếu nhiều môi trường có nhiều cấu hình khác biệt, file riêng theo profile thường dễ bảo trì hơn.

## 10. `spring.config.import` và tệp cấu hình bên ngoài

Ngoài những file mặc định, Config Data cho phép nhập thêm một nguồn cấu hình bằng `spring.config.import`.

Ví dụ nhập một file properties riêng:

~~~yaml
spring:
  config:
    import: optional:file:./deploy-config/inventory.properties
~~~

Nội dung file được nhập:

~~~properties
clients.inventory.base-url=https://inventory.internal.example
clients.inventory.read-timeout=900ms
~~~

Tiền tố `optional:` cho phép ứng dụng tiếp tục nếu location không tồn tại. Bỏ tiền tố này khi file là bắt buộc và ứng dụng không được phép chạy nếu thiếu nó.

### 10.1. Phân biệt `location`, `additional-location` và `import`

| Cơ chế | Câu hỏi nó trả lời |
| --- | --- |
| `spring.config.location` | Spring Boot cần tìm cấu hình ở những vị trí nào thay cho vị trí mặc định? |
| `spring.config.additional-location` | Cần thêm thư mục/file nào bên cạnh vị trí mặc định? |
| `spring.config.import` | File hoặc nguồn Config Data nào cần được nhập từ một document cấu hình? |

Không dùng ba thuộc tính thay thế cho nhau. Chọn sai có thể khiến file classpath mặc định không còn được nạp hoặc nguồn import không được xử lý như dự định.

### 10.2. Liên hệ với Spring Cloud Config

Khi cần cấu hình tập trung, ứng dụng có thể dùng Config Client để import Config Server trong các phiên bản hỗ trợ Config Data:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Cần thêm starter Config Client tương thích với Spring Boot/Spring Cloud release train đang dùng. Tên ứng dụng, profile và label có thể tham gia xác định bộ cấu hình server trả về.

Cần phân biệt:

- File `application.yml` và `application.properties` là các nguồn Config Data cục bộ.
- Config Server là nguồn cấu hình từ xa được đưa vào qua integration tương ứng.
- Nạp cấu hình lúc khởi động không đồng nghĩa với tự động nhận mọi thay đổi về sau.
- `@RefreshScope` của Spring Cloud Context chỉ tham gia khi cơ chế refresh phù hợp được kích hoạt; file thay đổi trên đĩa không tự động làm mọi bean được tạo lại.

Nếu cấu hình remote là bắt buộc cho nghiệp vụ, hãy cân nhắc bỏ `optional:` và cấu hình retry/fail-fast theo phiên bản để ứng dụng không khởi động với bộ giá trị thiếu.

## 11. Kiểm tra cấu hình đã được nạp

### 11.1. Đọc giá trị qua Environment

Có thể kiểm tra nhanh một key trong ứng dụng:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationProbe {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    public void printSelectedValues() {
        System.out.println("application="
                + environment.getProperty("spring.application.name"));
        System.out.println("inventory timeout="
                + environment.getProperty("clients.inventory.read-timeout"));
    }
}
~~~

`Environment.getProperty` trả về giá trị cuối cùng sau khi các nguồn được kết hợp theo độ ưu tiên. Nó không nhất thiết cho biết file cụ thể nào đã cung cấp giá trị đó.

### 11.2. Kiểm tra nguồn qua Actuator

Nếu ứng dụng đã có Spring Boot Actuator và expose endpoint phù hợp, `env` và `configprops` có thể hỗ trợ tìm nguồn của giá trị và kiểm tra kết quả binding.

Ví dụ cấu hình expose trong môi trường local:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
~~~

Không expose các endpoint cấu hình ra môi trường công khai. Chúng có thể tiết lộ tên property, thông tin triển khai hoặc dữ liệu nhạy cảm nếu việc che giá trị và bảo vệ truy cập không được cấu hình đúng. Chỉ expose tối thiểu endpoint cần dùng, kèm xác thực và giới hạn mạng.

### 11.3. Bật debug Config Data

Khi file không được nạp như dự kiến, bật debug logging cho quá trình khởi động và xem log liên quan đến Config Data. Tìm các thông tin:

- Tên file/location đã được xét.
- File nào thực sự được nạp.
- Profile nào đang active.
- Document nào được kích hoạt hoặc bỏ qua.
- Có lỗi parse YAML, thiếu location hoặc import thất bại không.

Không nên kết luận file không được nạp chỉ từ việc bean nhận giá trị mặc định; có thể file đã được nạp nhưng bị một property source có ưu tiên cao hơn ghi đè.

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Sửa `application.yml` nhưng giá trị không đổi | Có `application.properties` cùng vị trí hoặc nguồn ưu tiên cao hơn | Kiểm tra file trùng và `Environment`/Actuator `env` |
| Profile file không có hiệu lực | Profile chưa active, sai tên file hoặc sai location | Kiểm tra `SPRING_PROFILES_ACTIVE`, log Config Data và tên `application-{profile}` |
| Ứng dụng không tìm thấy file ngoài JAR | Working directory khác dự kiến, location sai hoặc thiếu quyền đọc | Kiểm tra đường dẫn tuyệt đối, working directory và log startup |
| YAML parse error | Thụt lề sai, dùng tab, dấu nháy hoặc cấu trúc list sai | Kiểm tra dòng lỗi, validate YAML và đối chiếu cấp lồng nhau |
| Placeholder không resolve | Key tham chiếu chưa tồn tại hoặc sai tên | Kiểm tra chính tả, property source và giá trị mặc định sau dấu `:` |
| `Duration` binding không đúng | Định dạng giá trị hoặc kiểu dữ liệu không phù hợp | Dùng dạng rõ ràng như `250ms`, `2s`, `1m`; kiểm tra bean đã bind |
| Danh sách ở profile bị mất phần tử | List ở nguồn ưu tiên cao thay thế toàn bộ list thấp hơn | Kiểm tra quy tắc merge của `@ConfigurationProperties`; không giả định list tự nối |
| File import bị thiếu làm ứng dụng dừng | Location không có `optional:` và file không tồn tại | Xác nhận file là bắt buộc hay tùy chọn |
| Cấu hình đã sửa nhưng bean vẫn dùng giá trị cũ | Bean đã khởi tạo và giữ giá trị trong instance | Kiểm tra lifecycle, refresh mechanism và cách bean lấy cấu hình |

### 12.1. Danh sách không luôn được nối thêm

Khi binding một list từ nhiều nguồn, Spring Boot áp dụng quy tắc ghi đè cho list; giá trị ở nguồn ưu tiên cao hơn có thể thay thế toàn bộ list đã bind từ nguồn thấp hơn. Không nên giả định chỉ phần tử cùng chỉ số bị thay đổi hoặc hai list tự động được nối.

Ví dụ file chung:

~~~yaml
clients:
  inventory:
    zones:
      - north
      - south
      - central
~~~

File theo profile:

~~~yaml
clients:
  inventory:
    zones:
      - production-a
~~~

Kết quả binding ở profile có thể chỉ còn `production-a`. Nếu muốn hợp nhất danh sách theo nghiệp vụ, cần thiết kế cấu trúc cấu hình và xử lý hợp nhất rõ ràng.

### 12.2. Cấu hình file không phải cơ chế hot reload

Spring Boot nạp Config Data trong quá trình khởi động. Sửa file trên đĩa sau khi ứng dụng đã chạy không có nghĩa mọi bean sẽ tự đọc lại. Một số công cụ phát triển có thể restart ứng dụng khi phát hiện thay đổi, nhưng đó là hành vi của công cụ phát triển, không phải bảo đảm chung cho production.

Trong Spring Cloud, refresh cần một cơ chế cập nhật Environment và kích hoạt refresh phù hợp. Nếu client hoặc bean đã giữ giá trị trong constructor, cần thiết kế lại vòng đời để giá trị mới có hiệu lực. Luôn kiểm tra từng instance sau khi refresh trong hệ thống nhiều replica.

## 13. Quy ước quản lý cấu hình cho hệ thống Spring Cloud

Với một dịch vụ như `orders-service`, có thể áp dụng các nguyên tắc:

1. Đặt giá trị mặc định không nhạy cảm trong `src/main/resources/application.yml`.
2. Đưa URL, timeout và profile-specific value của môi trường triển khai ra ngoài JAR hoặc qua biến môi trường.
3. Chọn một định dạng chính (`.properties` hoặc YAML) cho mỗi ứng dụng.
4. Dùng prefix theo chức năng, ví dụ `clients.inventory`, `clients.pricing`, để tránh trùng key.
5. Dùng `@ConfigurationProperties` cho nhóm cấu hình có cấu trúc và validation cho giá trị bắt buộc.
6. Không commit password, token, private key hoặc secret thật.
7. Dùng profile cho khác biệt có chủ đích, không tạo quá nhiều profile trùng lặp.
8. Ghi rõ cấu hình nào là bắt buộc; chỉ dùng `optional:` cho nguồn thực sự có thể thiếu.
9. Kiểm tra dependency version và cách import Config Server theo release train tương thích.
10. Quan sát giá trị sau cùng trong runtime và kiểm thử cấu hình quan trọng khi build/deploy.

## 14. Bài tập vận dụng

**Bài tập 1 — Chuyển đổi định dạng.** Viết nhóm thuộc tính sau bằng cả `.properties` và YAML: application name, server port, Inventory URL, connect timeout, read timeout và danh sách ba availability zone. Chứng minh hai định dạng tạo ra cùng các key trong `Environment`.

**Bài tập 2 — Tìm giá trị thắng.** File trong JAR đặt `server.port=8080`, file ngoài JAR đặt `server.port=8085`, biến môi trường đặt `SERVER_PORT=8090` và command line truyền `--server.port=9090`. Hãy xác định giá trị cuối cùng và mô tả cách xác minh bằng `Environment`.

**Bài tập 3 — Profile.** Tạo `application.yml` có timeout mặc định `500ms` và `application-prod.yml` có timeout `900ms`. Chạy lần lượt với và không có profile `prod`, ghi nhận kết quả.

**Bài tập 4 — Lỗi YAML.** Cố ý tạo lỗi thụt lề trong một nhóm `clients.inventory`. Quan sát thông báo parser và sửa file. Giải thích vì sao một key bị thụt sai có thể trở thành thuộc tính ở cấp khác.

**Bài tập 5 — Import.** Tạo một file `inventory.properties` nằm ngoài JAR và import bằng `spring.config.import`. Thử với và không có `optional:` khi file không tồn tại, so sánh hành vi startup.

**Bài tập 6 — Hệ thống phân tán.** Khai báo `spring.application.name`, discovery endpoint và timeout của downstream service. Tách giá trị mặc định khỏi giá trị production; xác định giá trị nào nên đưa qua environment variable hoặc Config Server và giải thích lý do.

## 15. Ghi nhớ và nguồn tra cứu

- `application.properties` và `application.yml` là hai cách biểu diễn Config Data; cả hai cùng đưa giá trị vào Spring `Environment`.
- File theo profile ghi đè giá trị chung khi profile tương ứng hoạt động.
- File bên ngoài có thể ghi đè file đóng gói trong JAR; environment variable và command line có thể ghi đè Config Data.
- `spring.config.location` thay thế vị trí mặc định; `spring.config.additional-location` bổ sung; `spring.config.import` nhập nguồn khác.
- YAML dễ đọc với cấu trúc lồng nhau nhưng nhạy với thụt lề và kiểu scalar.
- Thay đổi file khi ứng dụng đang chạy không tự động đồng nghĩa với refresh bean.
- Khi có nhiều nguồn cấu hình, luôn kiểm tra giá trị cuối cùng và nguồn cung cấp nó.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot Reference – Working with YAML and Multi-document Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files)
3. [Spring Boot Reference – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
4. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
5. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
