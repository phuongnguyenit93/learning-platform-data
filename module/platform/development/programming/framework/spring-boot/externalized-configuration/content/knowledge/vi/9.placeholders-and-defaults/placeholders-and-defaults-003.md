# Tham chiếu lồng nhau và xây giá trị từ nhiều thuộc tính

## 1. Từ một giá trị cấu hình đến một giá trị được ghép

Trong Spring Boot, cấu hình ngoài không nhất thiết chỉ chứa những chuỗi độc lập. Một địa chỉ dịch vụ thường được tạo từ tên máy, cổng, đường dẫn và môi trường triển khai. Nếu chép nguyên URL đó vào nhiều tệp, mỗi lần đổi tên máy hoặc cổng phải sửa ở nhiều nơi; rất dễ bỏ sót hoặc tạo các giá trị không nhất quán.

Ví dụ dịch vụ đặt hàng có các thành phần:

```text
Host          = localhost
Port          = 8081
API prefix    = /api/v1
Order path    = /orders

URL cuối cùng = http://localhost:8081/api/v1/orders
```

Spring cho phép biểu diễn sự phụ thuộc này bằng **placeholder** dạng `${ten.thuoc.tinh}`. Khi một giá trị được đọc qua cơ chế giải quyết placeholder, Spring tìm thuộc tính được tham chiếu rồi thay phần `${...}` bằng giá trị tương ứng. Có thể kết hợp phần văn bản cố định, nhiều placeholder và cả placeholder lồng nhau.

```text
application.yml
   |
   +-- client.host = localhost
   +-- client.port = 8081
   +-- client.api-prefix = /api/v1
   +-- client.orders-url =
           "http://${client.host}:${client.port}${client.api-prefix}/orders"
   |
   v
Environment và cơ chế resolve placeholder
   |
   v
"http://localhost:8081/api/v1/orders"
   |
   v
@Value, @ConfigurationProperties hoặc mã sử dụng cấu hình
```

Bài này giải thích cách tham chiếu đơn, xây giá trị từ nhiều thuộc tính, khóa tham chiếu động, giá trị mặc định và những lỗi thường gặp. Điều quan trọng là phân biệt **chuỗi khai báo**, **giá trị sau khi giải quyết placeholder** và **giá trị cuối cùng được liên kết vào bean**.

## 2. Placeholder cơ bản: ${property.name}

Ví dụ trong `src/main/resources/application.yml`:

```yaml
client:
  host: localhost
  port: 8081
  api-prefix: /api/v1
  orders-url: "http://${client.host}:${client.port}${client.api-prefix}/orders"
```

Khi Spring giải quyết `client.orders-url`, kết quả mong đợi:

```text
http://localhost:8081/api/v1/orders
```

Một chuỗi có thể chứa nhiều placeholder ở bất kỳ vị trí nào:

```properties
app.name=checkout
app.region=ap-southeast-1
app.instance-id=${app.name}-${app.region}
```

Kết quả của `app.instance-id` là `checkout-ap-southeast-1`.

Phần `${client.host}` có nghĩa **tra cứu thuộc tính với khóa `client.host`**. Nó không phải một lời gọi tới phương thức Java và cũng không phải biến của YAML. Spring Boot nạp các nguồn cấu hình thành những `PropertySource`, rồi cơ chế giải quyết thuộc tính/placeholder sử dụng các nguồn có hiệu lực.

### 2.1. Đọc kết quả bằng Environment

Tạo một ứng dụng quan sát đơn giản:

```java
package com.example.placeholderlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class PlaceholderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showValues(Environment environment) {
        return args -> {
            System.out.println("orders-url = "
                + environment.getProperty("client.orders-url"));
        };
    }
}
```

Với các nguồn tiêu chuẩn của Spring Boot, `Environment.getProperty("client.orders-url")` có thể trả về chuỗi đã giải quyết các placeholder, miễn là mọi tham chiếu cần thiết có giá trị hoặc có mặc định hợp lệ.

Những giá trị thô vẫn có thể tồn tại ở `PropertySource` dưới dạng văn bản chứa `${...}`. Không nên suy ra rằng ngay khi YAML được nạp, Spring Boot đã sửa nội dung của file hoặc thay mọi placeholder trực tiếp trong nguồn dữ liệu. **Giải quyết placeholder là một bước của quá trình truy cập/đưa giá trị vào ứng dụng.**

### 2.2. Đưa vào bean bằng @Value

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class OrdersClientSettings {

    private final String ordersUrl;

    public OrdersClientSettings(
            @Value("${client.orders-url}") String ordersUrl) {
        this.ordersUrl = ordersUrl;
    }

    public String ordersUrl() {
        return ordersUrl;
    }
}
```

Spring xử lý placeholder khi tạo bean và cấp giá trị qua constructor. Bean chỉ dùng `ordersUrl` mà không cần biết nó đến từ một chuỗi ghép của bốn thành phần trong YAML.

Cũng có thể ghép trực tiếp trong annotation:

```java
@Value("http://${client.host}:${client.port}/health")
private String healthUrl;
```

Tuy nhiên, khi cùng một địa chỉ được dùng ở nhiều bean, nên đặt công thức ở cấu hình hoặc một đối tượng cấu hình chung để tránh lặp các chuỗi khóa ở nhiều lớp Java.

## 3. Phân biệt placeholder với giá trị mặc định

Cú pháp mặc định thường dùng:

```text
${property.name:default-value}
```

Nếu không tìm thấy `property.name`, resolver dùng phần sau dấu hai chấm.

Ví dụ:

```yaml
client:
  host: "${CLIENT_HOST:localhost}"
  port: "${CLIENT_PORT:8081}"
  orders-url: "http://${client.host}:${client.port}/api/v1/orders"
```

Khi không có biến môi trường `CLIENT_HOST` và `CLIENT_PORT`, kết quả là `http://localhost:8081/api/v1/orders`. Nếu có hai biến môi trường đó, các giá trị tương ứng sẽ được dùng.

Lưu ý: tên `CLIENT_HOST` ở đây được dùng trực tiếp trong placeholder như một khóa; với các thuộc tính ứng dụng thông thường, nên ưu tiên tên **canonical kebab-case** trong tham chiếu, ví dụ `${client.host}`, để Spring Boot có thể áp dụng relaxed binding nhất quán với các nguồn như biến môi trường. Cách tổ chức sạch hơn là đặt `client.host=localhost` làm mặc định và để `CLIENT_HOST` hoặc biến môi trường theo quy ước `CLIENT_HOST` ghi đè `client.host` từ nguồn khác.

Ví dụ khuyến nghị:

```yaml
client:
  host: localhost
  port: 8081
  orders-url: "http://${client.host}:${client.port}/api/v1/orders"
```

Khi triển khai:

```bash
CLIENT_HOST=orders.internal CLIENT_PORT=9090 java -jar app.jar
```

Spring Boot có thể ánh xạ các biến môi trường này tới `client.host` và `client.port`. URL sau khi tra cứu sẽ thành `http://orders.internal:9090/api/v1/orders` theo ví dụ, không cần sửa giá trị `client.orders-url` trong file.

### 3.1. Mặc định cho một thành phần và mặc định cho toàn bộ chuỗi

Hai cách sau có ý nghĩa khác nhau.

**Mặc định từng thành phần:**

```properties
client.host=localhost
client.url=http://${client.host}:${client.port:8081}/api
```

Nếu `client.port` vắng mặt, dùng `8081`, còn host vẫn lấy từ `client.host`.

**Mặc định cả địa chỉ:**

```properties
client.resolved-url=${client.explicit-url:http://localhost:8081/api}
```

Ở đây, khi thiếu `client.explicit-url`, toàn bộ chuỗi mặc định được sử dụng. Phần `http://` có dấu hai chấm nhưng vẫn là phần của **giá trị mặc định** sau dấu phân cách đầu tiên.

Không hiểu `:` trong placeholder là cú pháp YAML hoặc dấu phân cách port. Với `${client.port:8081}`, dấu hai chấm thuộc cú pháp fallback; với `http://${client.host}:${client.port}`, dấu hai chấm ngoài placeholder là văn bản của URL.

### 3.2. Giá trị thiếu, rỗng và mặc định

Khi giá trị **không có** trong các nguồn cấu hình, placeholder có mặc định có thể lấy giá trị sau dấu `:`. Nhưng thuộc tính được khai báo thành chuỗi rỗng không luôn tương đương với thuộc tính vắng mặt:

```properties
client.host=
client.url=http://${client.host:localhost}:8081/api
```

Trong một tình huống resolver nhận được giá trị chuỗi rỗng, `client.host` được coi là **có giá trị**, nên `localhost` có thể không được chọn; URL tạo ra trở thành `http://:8081/api`. Vì vậy, mặc định không có nghĩa là kiểm tra chuỗi rỗng, URL hợp lệ hoặc tính hợp lệ nghiệp vụ.

Với dữ liệu bắt buộc, cần kết hợp validation của `@ConfigurationProperties` hoặc cơ chế kiểm tra phù hợp.

## 4. Xây một giá trị từ nhiều thuộc tính

Giả sử một ứng dụng cần địa chỉ API, địa chỉ health check và địa chỉ tài liệu cho cùng dịch vụ. Ta có thể khai báo những thành phần dùng chung:

```yaml
catalog:
  scheme: https
  host: catalog.example.invalid
  port: 8443
  base-path: /v1

  base-url: "${catalog.scheme}://${catalog.host}:${catalog.port}${catalog.base-path}"
  products-url: "${catalog.base-url}/products"
  health-url: "${catalog.scheme}://${catalog.host}:${catalog.port}/health"
```

Các giá trị sau khi giải quyết:

```text
catalog.base-url
  = https://catalog.example.invalid:8443/v1

catalog.products-url
  = https://catalog.example.invalid:8443/v1/products

catalog.health-url
  = https://catalog.example.invalid:8443/health
```

`catalog.products-url` tham chiếu `catalog.base-url`, mà `catalog.base-url` lại chứa bốn placeholder khác. Đây là **chuỗi phụ thuộc nhiều tầng**. Resolver có thể tiếp tục giải quyết các placeholder của giá trị tham chiếu để trả về URL cuối cùng.

```text
catalog.products-url
     |
     +-- catalog.base-url
               |
               +-- catalog.scheme
               +-- catalog.host
               +-- catalog.port
               +-- catalog.base-path
     |
     +-- chuỗi "/products"
     |
     v
https://catalog.example.invalid:8443/v1/products
```

Nên giữ sơ đồ phụ thuộc ngắn và tên khóa rõ nghĩa. Nếu một giá trị phải đi qua quá nhiều tầng, người vận hành sẽ khó xác định nguồn tạo ra URL cuối cùng.

### 4.1. Vì sao ghép giá trị trong cấu hình?

Điều này hữu ích khi các phần có vòng đời khác nhau. Ví dụ `catalog.host` thay đổi theo máy, trong khi `catalog.base-path` là quy ước ổn định của dịch vụ. Khi một nguồn có ưu tiên cao hơn ghi đè `catalog.host`, các URL tham chiếu giá trị đó cũng có thể nhận host mới lúc được giải quyết.

Không nên chép địa chỉ đầy đủ vào nhiều file:

```properties
catalog.products-url=https://catalog.example.invalid:8443/v1/products
catalog.categories-url=https://catalog.example.invalid:8443/v1/categories
catalog.inventory-url=https://catalog.example.invalid:8443/v1/inventory
```

Nếu chỉ đổi host, phải sửa cả ba dòng. Với cách tham chiếu một `catalog.base-url`, ý định rõ hơn và ít có nguy cơ lệch cấu hình.

Tuy nhiên, nếu các URL thực sự khác nhau về cơ chế xây dựng, ví dụ có proxy, ký URL, đường dẫn do logic nghiệp vụ tính toán hoặc quy tắc mã hóa tham số, nên dùng mã Java phù hợp thay vì cố biến cấu hình thành ngôn ngữ lập trình.

## 5. Hai kiểu “lồng nhau” cần phân biệt

Chữ *lồng nhau* thường bị hiểu lẫn giữa **tham chiếu nối tầng** và **placeholder nằm trong tên của placeholder khác**.

### 5.1. Tham chiếu nối tầng: giá trị A dẫn đến B dẫn đến C

```properties
service.host=localhost
service.base-url=http://${service.host}:8080
service.orders-url=${service.base-url}/orders
```

Ở đây:

```text
service.orders-url
  -> service.base-url
      -> service.host
```

Các placeholder không nhất thiết nằm trong cùng một cặp dấu ngoặc, nhưng việc giải quyết một giá trị kéo theo giải quyết giá trị nó tham chiếu.

### 5.2. Placeholder lồng trong tên khóa: chọn khóa động

Giả sử ứng dụng khai báo endpoint của ba vùng:

```properties
payments.targets.dev=http://localhost:9000
payments.targets.staging=https://staging-payments.example.invalid
payments.targets.prod=https://payments.example.invalid
payments.selected=staging
payments.endpoint=${payments.targets.${payments.selected}}
```

Biểu thức:

```text
${payments.targets.${payments.selected}}
```

được hiểu theo hai bước:

1. Giải quyết placeholder **bên trong**: `${payments.selected}` → `staging`.
2. Tạo tên khóa **bên ngoài**: `payments.targets.staging`, sau đó tra cứu khóa đó → `https://staging-payments.example.invalid`.

Kết quả của `payments.endpoint`:

```text
https://staging-payments.example.invalid
```

Đây là **tham chiếu khóa động**. Nếu thay `payments.selected` thành `prod` và khởi động lại ứng dụng, biểu thức ngoài hướng tới `payments.targets.prod`. Cần phân biệt điều này với việc nối chuỗi `${payments.host}/api`: trong khóa động, giá trị của placeholder bên trong trở thành **một phần tên thuộc tính cần tra cứu**.

Ví dụ YAML tương đương:

```yaml
payments:
  selected: staging
  targets:
    dev: http://localhost:9000
    staging: https://staging-payments.example.invalid
    prod: https://payments.example.invalid

  endpoint: "${payments.targets.${payments.selected}}"
```

Chuỗi có hai dấu mở `${` và hai dấu đóng `}`. Đừng bỏ dấu đóng ở cuối hoặc viết nhầm thành `${payments.targets}.${payments.selected}`: biểu thức sau chỉ **ghép hai giá trị**, không chọn một khóa trong nhánh `payments.targets.*`.

## 6. Kết hợp khóa động với giá trị mặc định

Khi khóa được chọn có thể thiếu, cần thiết kế fallback rõ ràng.

Ví dụ:

```properties
payments.selected=preview
payments.targets.dev=http://localhost:9000
payments.targets.prod=https://payments.example.invalid
payments.endpoint=${payments.targets.${payments.selected}:http://localhost:9099}
```

Giải quyết:

1. `payments.selected` → `preview`.
2. Tên khóa ngoài trở thành `payments.targets.preview`.
3. Khóa đó không có trong các nguồn của ví dụ.
4. Giá trị mặc định của placeholder ngoài là `http://localhost:9099`.

Kết quả là:

```text
http://localhost:9099
```

Ta cũng có thể đặt mặc định cho **tên được chọn**:

```properties
payments.targets.dev=http://localhost:9000
payments.selected-endpoint=${payments.targets.${payments.selected:dev}}
```

Nếu không có `payments.selected`, placeholder bên trong dùng `dev`, rồi bên ngoài tra cứu `payments.targets.dev`. Nhưng nếu `payments.selected=preview` trong khi `payments.targets.preview` vắng mặt, mặc định `dev` của placeholder **bên trong** không cứu được trường hợp khóa ngoài bị thiếu.

Hai loại thiếu giá trị khác nhau:

| Thiếu gì? | Placeholder có mặc định | Mặc định được áp dụng? |
| --- | --- | --- |
| `payments.selected` | `${payments.selected:dev}` | Có, chọn `dev` |
| `payments.targets.preview` | `${payments.targets.${payments.selected}:http://localhost:9099}` | Có, dùng URL fallback |
| `payments.targets.preview` nhưng chỉ có mặc định ở `selected` | `${payments.targets.${payments.selected:dev}}` | Không có fallback cho khóa ngoài |

Nếu dùng cả hai mức mặc định, biểu thức sẽ khó đọc hơn. Thường nên tách một thuộc tính chọn môi trường có mặc định an toàn, đồng thời chỉ cho phép các giá trị `selected` thuộc tập đã được kiểm chứng. Với lựa chọn ảnh hưởng đến giao dịch, cần cân nhắc **báo lỗi khi thiếu cấu hình** thay vì âm thầm gọi một endpoint dự phòng.

## 7. Nguồn cấu hình nào được dùng khi một thành phần bị ghi đè?

Spring Boot cho phép cùng một khóa được khai báo ở nhiều nguồn. Khi giải quyết `${catalog.host}`, resolver sử dụng giá trị có hiệu lực của khóa đó theo hệ thống `Environment`.

Giả sử trong JAR có:

```yaml
catalog:
  scheme: http
  host: localhost
  port: 8080
  base-url: "${catalog.scheme}://${catalog.host}:${catalog.port}"
```

Khi chạy:

```bash
java -jar app.jar --catalog.host=catalog.internal --catalog.port=9090
```

nếu không có nguồn khác có ưu tiên cao hơn, kết quả:

```text
catalog.base-url = http://catalog.internal:9090
```

`catalog.base-url` vẫn được khai báo trong YAML. Nhưng các placeholder bên trong lấy giá trị có hiệu lực của `catalog.host` và `catalog.port` từ tham số dòng lệnh. Đây là lý do một **công thức cấu hình** có thể dùng trên nhiều môi trường: các thành phần của nó nhận giá trị từ những nguồn khác nhau.

Cũng có thể ghi đè **toàn bộ khóa đích**:

```bash
java -jar app.jar --catalog.base-url=https://gateway.example.invalid/catalog
```

Trong trường hợp này, ứng dụng có thể đọc URL hoàn chỉnh từ tham số dòng lệnh mà không cần sử dụng công thức YAML cho khóa đó. Vì vậy, khi giá trị cuối cùng khác mong đợi, hãy kiểm tra cả **khóa đích** và các **khóa thành phần**, không chỉ một file cấu hình.

### Ví dụ kết hợp profile

```yaml
# application.yml
catalog:
  host: localhost
  port: 8080
  base-url: "http://${catalog.host}:${catalog.port}"
```

```yaml
# application-prod.yml
catalog:
  host: catalog.internal
  port: 9090
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Trong điều kiện cấu hình chuẩn và không có override khác, `catalog.base-url` nhận `http://catalog.internal:9090`. Profile chọn những nguồn cấu hình được nạp; placeholder dùng giá trị có hiệu lực từ các nguồn đó. **Profile không thay đổi cú pháp `${...}`**.

## 8. Một ví dụ hoàn chỉnh bằng @ConfigurationProperties

Với nhiều thuộc tính liên quan, nên liên kết chúng vào một lớp có kiểu, sau đó đưa lớp đó vào service qua dependency injection.

Tệp `application.yml`:

```yaml
shipping:
  scheme: https
  host: shipping.example.invalid
  port: 8443
  root-path: /api
  rates-url: "${shipping.scheme}://${shipping.host}:${shipping.port}${shipping.root-path}/rates"
  labels-url: "${shipping.scheme}://${shipping.host}:${shipping.port}${shipping.root-path}/labels"
```

Record Java:

```java
package com.example.placeholderlab;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        String scheme,
        String host,
        int port,
        String rootPath,
        URI ratesUrl,
        URI labelsUrl
) {}
```

Đăng ký tại lớp ứng dụng:

```java
package com.example.placeholderlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ShippingProperties.class)
public class PlaceholderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderLabApplication.class, args);
    }
}
```

Bean sử dụng đối tượng cấu hình:

```java
package com.example.placeholderlab;

import org.springframework.stereotype.Service;

@Service
public class ShippingClientSettings {
    private final ShippingProperties properties;

    public ShippingClientSettings(ShippingProperties properties) {
        this.properties = properties;
    }

    public String ratesUrl() {
        return properties.ratesUrl().toString();
    }

    public String labelsUrl() {
        return properties.labelsUrl().toString();
    }
}
```

Spring Boot `Binder` xử lý nhóm `shipping.*`, chuyển chuỗi URI sau khi placeholder đã được giải quyết sang `java.net.URI` và cấp đối tượng cấu hình cho bean. Trong ví dụ, service không cần biết `shipping.rates-url` được ghép từ những khóa nào; nó chỉ nhận một URI đã được liên kết.

Tuy nhiên, với những URL cần mã hóa tham số, xử lý đường dẫn động hoặc ghép query string phức tạp, hãy ưu tiên API như `URI`, `UriComponentsBuilder` hoặc client HTTP phù hợp khi chạy ứng dụng. Placeholder thuận tiện cho **giá trị cấu hình tĩnh**, không thay thế hoàn toàn việc xây URL đúng quy tắc.

## 9. Thực nghiệm khóa động: thay selector và quan sát kết quả

Dựng một bài thực hành nhỏ với file:

```yaml
lookup:
  selected: dev

  endpoints:
    dev: http://localhost:8085
    staging: https://staging.example.invalid
    prod: https://prod.example.invalid

  base-url: "${lookup.endpoints.${lookup.selected}}"
  health-url: "${lookup.base-url}/health"
```

Trong một `ApplicationRunner` có thể in:

```java
@Bean
ApplicationRunner report(Environment environment) {
    return args -> {
        System.out.println(
            "selected = " + environment.getProperty("lookup.selected")
        );
        System.out.println(
            "base-url = " + environment.getProperty("lookup.base-url")
        );
        System.out.println(
            "health-url = " + environment.getProperty("lookup.health-url")
        );
    };
}
```

Đặt phương thức `@Bean` trong một lớp `@Configuration` hoặc `@SpringBootApplication`, và bảo đảm đã import `ApplicationRunner`, `Bean`, `Environment`.

### Lần chạy A: mặc định dev

```bash
java -jar app.jar
```

Kỳ vọng:

```text
selected = dev
base-url = http://localhost:8085
health-url = http://localhost:8085/health
```

Ở đây, `lookup.selected` → `dev`; tên khóa bên ngoài thành `lookup.endpoints.dev`; URL health tiếp tục tham chiếu `lookup.base-url`.

### Lần chạy B: chọn staging trên dòng lệnh

```bash
java -jar app.jar --lookup.selected=staging
```

Kỳ vọng:

```text
selected = staging
base-url = https://staging.example.invalid
health-url = https://staging.example.invalid/health
```

Không đổi bất kỳ dòng nào trong YAML. Chỉ một khóa `lookup.selected` được ghi đè, nhưng hai giá trị dẫn xuất thay đổi theo vì chúng phụ thuộc vào khóa được chọn.

### Lần chạy C: chọn prod và ghi đè endpoint prod

```bash
java -jar app.jar \
  --lookup.selected=prod \
  --lookup.endpoints.prod=https://private-gateway.example.invalid
```

Kỳ vọng:

```text
selected = prod
base-url = https://private-gateway.example.invalid
health-url = https://private-gateway.example.invalid/health
```

Đây là thí nghiệm có **hai mức động**: selector xác định khóa nào được đọc, còn nguồn có độ ưu tiên cao quyết định giá trị của khóa đó.

### Lần chạy D: chọn giá trị không có trong bảng

```bash
java -jar app.jar --lookup.selected=unknown
```

Lúc này placeholder ngoài cố tra cứu `lookup.endpoints.unknown`. Vì YAML mẫu không có khóa đó và không đặt fallback, quá trình giải quyết có thể gặp lỗi placeholder không xác định khi giá trị được truy cập hoặc binding. Tùy nơi và thời điểm sử dụng thuộc tính, lỗi có thể xuất hiện trong khởi động bean hay khi một mã truy cập thuộc tính.

Trong ứng dụng thật, nên **kiểm tra selector đầu vào** hoặc thiết kế fallback rõ ràng. Không tự suy diễn rằng Spring sẽ chọn `dev` chỉ vì `dev` đứng đầu danh sách.

## 10. Kiểm tra cả ba tầng: nguồn, placeholder và bean

Khi một bean nhận URL không đúng, hãy đặt ba câu hỏi theo thứ tự:

```text
Nguồn cấu hình
  - "lookup.selected" có giá trị gì?
  - "lookup.endpoints.prod" đến từ đâu?
             |
             v
Giải quyết placeholder
  - Khóa động sau khi thay "selected" là gì?
  - Giá trị đích có chứa placeholder nối tầng khác không?
             |
             v
Bean
  - Bean đang dùng khóa nào?
  - Kiểu Java đích là gì?
  - Giá trị được khởi tạo vào thời điểm nào?
```

Ví dụ nếu `lookup.base-url` lại lấy từ dòng lệnh:

```bash
java -jar app.jar --lookup.base-url=https://override.example.invalid
```

thì dù `lookup.selected=dev`, URL nhận được vẫn có thể là `https://override.example.invalid`. Lý do là **khóa đích `lookup.base-url` đã bị ghi đè trực tiếp**, khiến công thức trong YAML không phải giá trị có hiệu lực.

Nếu một trường `@ConfigurationProperties` được khởi tạo khi context bắt đầu chạy, việc đổi file YAML lúc tiến trình đã chạy **không tự bảo đảm** bean được cập nhật. Bài thực nghiệm nên khởi động lại tiến trình mỗi lần thay cấu hình để quan sát một trạng thái ổn định.

## 11. Placeholder khác với Spring Expression Language (SpEL)

Hai loại cú pháp thường thấy trong Spring:

```text
${server.port:8080}         -> placeholder: tra cứu thuộc tính
#{2 * 3}                    -> SpEL: đánh giá biểu thức
```

Placeholder tìm và thay giá trị từ cấu hình. SpEL là một ngôn ngữ biểu thức có khả năng tính toán hoặc truy cập thành phần trong ngữ cảnh cho phép. **Không đánh đồng hai cú pháp**.

Ví dụ `@Value("${client.port:8080}")` dùng property placeholder để lấy một cổng cấu hình. Ví dụ `@Value("#{2 * 3}")` yêu cầu Spring đánh giá biểu thức thành `6`. Cả hai có thể gặp trong `@Value`, nhưng việc Spring Boot binding `@ConfigurationProperties` có cơ chế và giới hạn riêng; không nên coi mỗi giá trị cấu hình trong YAML đều được thực thi như SpEL.

Nếu cần phép tính hoặc quyết định phức tạp, rõ ràng và có thể kiểm thử hơn khi xử lý trong mã Java, thay vì cố xây một cây biểu thức dài trong file cấu hình.

## 12. Khác biệt giữa Spring placeholder và nội suy của shell

Ký hiệu `${...}` cũng xuất hiện trong một số shell, công cụ CI/CD hoặc hệ thống template. Nhưng khi có mặt **trong file YAML hoặc properties của Spring Boot**, placeholder ở đây được Spring giải quyết lúc truy cập cấu hình.

Khi truyền qua shell, ký tự `$` có thể được shell xử lý trước. Ví dụ trên Bash, chuỗi:

```text
java -jar app.jar --client.url=${client.host}
```

có thể bị shell hiểu theo cú pháp riêng hoặc mở rộng ngoài ý muốn. Nếu muốn truyền **nguyên văn** placeholder để Spring xử lý, hãy trích dẫn đúng theo shell, chẳng hạn:

```bash
java -jar app.jar '--client.url=http://${client.host}:8080'
```

Với PowerShell, dấu nháy đơn cũng giúp tránh mở rộng biến trong chuỗi:

```powershell
java -jar app.jar '--client.url=http://${client.host}:8080'
```

Thường dễ hơn khi đặt công thức placeholder trong `application.yml` và chỉ truyền những thành phần muốn ghi đè trên dòng lệnh.

Cũng cần phân biệt placeholder trong Spring Boot với tính năng thay biến ở giai đoạn build của Maven/Gradle hoặc triển khai của Helm/Kubernetes. Nếu một công cụ đã thay văn bản trước khi ứng dụng bắt đầu chạy, Spring không nhất thiết còn nhìn thấy cú pháp placeholder gốc. Nên xác định **công cụ nào sở hữu việc nội suy** để tránh giải quyết cùng một biến ở hai giai đoạn khác nhau.

## 13. Điều kiện khi tham chiếu có thể không được giải quyết

### 13.1. Khóa tham chiếu vắng mặt

```properties
client.url=http://${client.host}:8080
```

Nếu thiếu `client.host` và không có fallback, việc giải quyết có thể thất bại khi bean được tạo hoặc khi thuộc tính được truy cập. Lỗi thường có thông tin về placeholder không tìm được. Khắc phục bằng cách khai báo nguồn hợp lệ hoặc thiết kế mặc định phù hợp.

### 13.2. Khóa tham chiếu bị sai tên

Ví dụ file khai báo `client.hostname` nhưng công thức dùng `${client.host}`. Spring sẽ không tự suy luận hai tên khóa là một. Cần thống nhất tên và ưu tiên dạng canonical phù hợp với cơ chế relaxed binding của Spring Boot.

### 13.3. Chu trình tham chiếu

Không tạo vòng như:

```properties
a.value=${b.value}
b.value=${a.value}
```

Hoặc tự tham chiếu:

```properties
a.value=${a.value}
```

Resolver không thể thu được giá trị cuối cùng xác định từ vòng vô tận. Spring thường báo lỗi khi gặp chu trình lúc giải quyết. Không nên xem fallback là một cách hợp lệ để thiết kế phụ thuộc vòng. Hãy tổ chức các khóa theo hướng **giá trị nền tảng → giá trị dẫn xuất**, không dẫn quay trở lại giá trị nền tảng.

### 13.4. Tham chiếu nhiều tầng quá sâu

```text
url.current
  -> url.alias
      -> url.region
          -> url.host-by-region
              -> url.host
```

Chuỗi phụ thuộc càng dài, việc đọc và gỡ lỗi càng khó. Nếu cần kết hợp nhiều điều kiện, có thể chuyển sang một lớp cấu hình có kiểu và tính giá trị dẫn xuất trong Java.

### 13.5. Cấu hình trống nhưng fallback không chạy

```properties
service.path=
service.url=http://localhost:8080${service.path:/api}
```

Nếu `service.path` thực sự tồn tại với giá trị rỗng, kết quả không nhất thiết có `/api`. Fallback của placeholder thông thường xử lý **khóa thiếu**, không phải mọi giá trị không đạt yêu cầu. Hãy kiểm tra dữ liệu đầu vào thay vì dựa vào fallback để làm validation.

### 13.6. Ghép URI tạo dấu slash dư hoặc thiếu

```properties
service.root=https://example.invalid/api/
service.url=${service.root}/orders
```

Kết quả có thể là `https://example.invalid/api//orders`. Placeholder chỉ thay văn bản, không tự chuẩn hóa slash. Tương tự, nếu `service.root` thiếu slash cuối và phần sau cũng không có slash đầu, URL bị dính vào nhau.

Để giảm lỗi, hãy quy định rõ: phần `base-url` **không** có slash cuối; các đường dẫn con **có** slash đầu. Khi URL chứa tham số hoặc cần xử lý mã hóa, nên tạo URI bằng API tương ứng.

## 14. Tham chiếu lồng nhau không phải phép nối dữ liệu tùy ý

Một placeholder lấy một giá trị cấu hình theo tên. Nó **không** tự có khả năng:

- Chạy một truy vấn cơ sở dữ liệu để tạo URL theo người dùng hiện tại.
- Đọc cấu hình thay đổi theo từng HTTP request mà không có cơ chế cập nhật riêng.
- Bảo đảm endpoint có thể kết nối hoặc URI có cấu trúc hợp lệ.
- Bảo đảm selector động chỉ chọn những đích đã được phép.
- Tự mã hóa URL hoặc giữ bí mật nếu kết quả bị in ra log.

Ví dụ khóa động `${payments.targets.${payments.selected}}` rất tiện khi selector có tập giá trị được kiểm soát tại lúc khởi động. Nhưng nếu biến `payments.selected` có thể nhận đầu vào không tin cậy, cần validation để tránh lựa chọn sai đích.

Đối với token hoặc password, có thể lấy giá trị từ nguồn quản lý bí mật phù hợp, nhưng không nên nối chúng thành URL rồi ghi URL ra log. Giá trị nhạy cảm vẫn là nhạy cảm sau khi placeholder được giải quyết.

## 15. Quy trình gỡ lỗi khi URL cuối cùng sai

Giả sử bạn kỳ vọng:

```text
https://catalog.example.invalid:8443/v1/products
```

nhưng bean nhận một giá trị khác. Hãy kiểm tra theo quy trình:

1. **Đọc khóa đích**: bean dùng `catalog.products-url` hay một khóa khác? Có `@Value`/`@ConfigurationProperties` nào định nghĩa fallback riêng không?
2. **Kiểm tra nguồn ưu tiên**: `catalog.products-url` có bị ghi đè hoàn toàn từ tham số dòng lệnh, biến môi trường, file profile hoặc Config Data khác không?
3. **Lần từng tham chiếu**: `products-url` → `base-url` → `scheme`, `host`, `port`, `base-path`. Với khóa động, kiểm tra selector trước rồi mới xác định tên khóa ngoài.
4. **Kiểm tra khóa thiếu**: một thuộc tính không tồn tại khác với một thuộc tính có chuỗi rỗng; kiểm tra fallback tại đúng cấp.
5. **Kiểm tra cấu trúc**: thiếu/dư dấu slash, scheme `http`/`https`, cổng, mã hóa thành phần URL.
6. **Kiểm tra thời điểm**: vừa thay file sau khi ứng dụng khởi động hay không; bean có đang giữ giá trị liên kết từ lần khởi động trước?
7. **Kiểm tra lỗi chu trình**: có hai khóa dẫn ngược về nhau không?

Với dữ liệu thử nghiệm vô hại, có thể dùng một `ApplicationRunner` để in đúng các khóa liên quan qua `Environment.getProperty(...)`. Nếu ứng dụng có Spring Boot Actuator và endpoint `env` được cấu hình an toàn, có thể tra cứu thông tin nguồn. Tránh bật endpoint công khai hoặc in toàn bộ cấu hình khi có mật khẩu/token.

Một kỹ thuật đơn giản là tạm rút gọn công thức theo tầng:

```text
Bước 1: catalog.host
Bước 2: catalog.port
Bước 3: catalog.base-url
Bước 4: catalog.products-url
```

Nếu bước 1 và 2 đúng nhưng bước 3 sai, tập trung vào chuỗi công thức hoặc cách ghi đè `base-url`. Nếu bước 3 đúng nhưng bước 4 sai, kiểm tra suffix `/products` hoặc khả năng khóa `products-url` bị override.

## 16. Bài thực hành: một thay đổi kéo theo nhiều giá trị

Khởi tạo:

```yaml
app:
  env: dev

  hosts:
    dev: localhost
    stage: stage.example.invalid
    prod: prod.example.invalid

  scheme: https
  port: 8443
  api-root: /api/v1

  selected-host: "${app.hosts.${app.env}}"
  base-url: "${app.scheme}://${app.selected-host}:${app.port}${app.api-root}"
  customers-url: "${app.base-url}/customers"
  orders-url: "${app.base-url}/orders"
```

Hãy dự đoán các giá trị:

| Lần chạy | Override | `app.selected-host` | `app.orders-url` |
| --- | --- | --- | --- |
| A | Không | `localhost` | `https://localhost:8443/api/v1/orders` |
| B | `--app.env=stage` | `stage.example.invalid` | `https://stage.example.invalid:8443/api/v1/orders` |
| C | `--app.env=prod --app.port=9443` | `prod.example.invalid` | `https://prod.example.invalid:9443/api/v1/orders` |
| D | `--app.env=prod --app.base-url=https://proxy.example.invalid/v2` | `prod.example.invalid` | `https://proxy.example.invalid/v2/orders` |

Trong D, `app.selected-host` vẫn có thể đúng bằng `prod.example.invalid`, nhưng `app.base-url` đã được ghi đè trực tiếp, nên `app.orders-url` không còn buộc phải dùng công thức `scheme://selected-host:port/api-root` từ YAML.

Thử thêm một tình huống E:

```bash
java -jar app.jar --app.env=unknown
```

Ở đây, `app.selected-host` sẽ tìm `app.hosts.unknown`. Vì không có khóa đó, bạn cần quyết định nghiệp vụ muốn **báo lỗi sớm**, **từ chối selector** hay **dùng endpoint fallback được khai báo rõ ràng**. Không có quy tắc rằng Spring tự tìm một tên gần giống `unknown`.

### Bài tập suy luận

1. Nếu `app.port` được ghi đè bằng `9443`, những khóa dẫn xuất nào thay đổi?
2. Nếu `app.base-url` bị ghi đè thành một URL tuyệt đối, việc thay `app.scheme` có còn tác động lên `app.orders-url` không?
3. Nếu `app.env` vắng mặt, nên đặt mặc định ở `app.env` hay ở placeholder bên trong `app.selected-host`? Mỗi cách tạo điều kiện lỗi nào?
4. Nếu `app.hosts.prod` chứa chuỗi rỗng, fallback ở placeholder ngoài có chắc được chọn không?
5. Với hai khóa `one=${two}` và `two=${one}`, điều gì khiến chúng không thể được giải quyết thành một giá trị hữu hạn?

Bài tập nhấn mạnh quan hệ giữa **giá trị được chọn theo ưu tiên**, **tên khóa động** và **cây phụ thuộc của các giá trị dẫn xuất**.

## 17. Cách tổ chức để cấu hình dễ bảo trì

Tách ba loại thuộc tính:

| Loại | Vai trò | Ví dụ |
| --- | --- | --- |
| Giá trị nền tảng | Thay đổi theo môi trường | `app.host`, `app.port`, `app.env` |
| Giá trị dẫn xuất | Ghép từ giá trị nền tảng | `app.base-url`, `app.orders-url` |
| Giá trị lựa chọn | Xác định nhánh cấu hình | `app.selected`, `payments.region` |

Một số quy ước hữu ích:

- **Đặt tên đầy đủ**: `payments.selected-region` dễ hiểu hơn `payments.sel`.
- **Ưu tiên khóa chuẩn**: dùng chữ thường, dấu chấm cho nhóm và dấu gạch ngang cho từ ghép trong các tham chiếu `${...}`.
- **Đặt fallback có chủ đích**: chỉ đưa vào giá trị mặc định nếu giá trị đó an toàn và có ý nghĩa khi thiếu nguồn.
- **Giới hạn chuỗi tham chiếu**: tránh các cây quá sâu; nếu công thức khó đọc, cân nhắc tạo một đối tượng cấu hình rồi tính toán có kiểm tra trong Java.
- **Không tạo chu trình**: giá trị dẫn xuất phụ thuộc vào giá trị nền tảng, không ngược lại.
- **Kiểm tra URI và dữ liệu bắt buộc**: placeholder không thay thế validation.
- **Đừng log bí mật**: URL có token/password vẫn là dữ liệu nhạy cảm ngay cả khi đã ghép xong.
- **Ghi rõ nguồn có thể override**: nếu `base-url` được phép ghi đè độc lập, hãy công bố điều đó cho người triển khai để họ hiểu vì sao công thức không được dùng.

## 18. Ghi nhớ

Các placeholder trong Spring Boot giúp một thuộc tính được **xây dựng từ những thuộc tính khác** mà không phải lặp giá trị trong nhiều tệp.

```text
${app.host}                         -> tham chiếu đơn

http://${app.host}:${app.port}      -> ghép nhiều thuộc tính

${app.base-url}/orders             -> tham chiếu nối tầng

${app.hosts.${app.env}}            -> placeholder lồng trong tên khóa

${app.host:localhost}              -> giá trị mặc định cho khóa thiếu
```

Luồng xử lý luôn cần xét theo thứ tự:

```text
Nguồn cấu hình có hiệu lực
        |
        v
Giải quyết từng tham chiếu ${...}
        |
        v
Thay placeholder lồng nhau, nếu có
        |
        v
Tạo chuỗi kết quả và chuyển kiểu khi cần
        |
        v
Bean nhận và sử dụng giá trị
```

Với các hệ thống có nhiều môi trường, khả năng tham chiếu giúp tái sử dụng cấu hình, còn khả năng **ghi đè từng khóa** cho phép một bản JAR hoạt động với host, port hoặc endpoint khác nhau. Khi một URL không như mong đợi, hãy lần ngược từ khóa đích qua từng placeholder đến nguồn cấp giá trị, rồi kiểm tra fallback, chu trình và thứ tự ưu tiên.

Tài liệu để đọc thêm: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) và [Spring Framework — Property Resolution](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html).