# Chuyển đổi URI, URL, InetAddress và Resource trong Spring Boot Externalized Configuration

## 1. Mục tiêu bài học

Một cấu hình ứng dụng thường chứa địa chỉ HTTP, hostname, địa chỉ IP, đường dẫn đến chứng chỉ hoặc tệp dữ liệu. Trong `application.properties` hoặc `application.yml`, những giá trị này ban đầu được biểu diễn bằng chuỗi. Spring Boot có thể **chuyển đổi kiểu khi binding** để code Java nhận một đối tượng có ngữ nghĩa cụ thể thay vì luôn nhận `String`.

Các kiểu thường gặp là:

- `java.net.URI`: biểu diễn định danh tài nguyên theo cú pháp URI, có thể là tương đối hoặc tuyệt đối.
- `java.net.URL`: biểu diễn locator với một protocol mà Java hỗ trợ; phù hợp khi một API cũ hoặc thư viện yêu cầu `URL`.
- `java.net.InetAddress`: biểu diễn địa chỉ mạng IP, có thể được tạo từ địa chỉ số hoặc tên máy cần phân giải.
- `org.springframework.core.io.Resource`: abstraction của Spring cho nội dung tài nguyên, ví dụ file trong classpath, file trên hệ thống tệp hoặc một nguồn được `ResourceLoader` hỗ trợ.

Ví dụ một nhóm properties:

~~~properties
service.api.base-uri=https://api.example.test/v1
service.api.legacy-url=https://legacy.example.test/api
service.network.bind-address=127.0.0.1
service.tls.certificate=classpath:certs/service.pem
~~~

Object Java có thể khai báo các trường cùng ý nghĩa:

~~~java
import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import org.springframework.core.io.Resource;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        Api api,
        Network network,
        Tls tls
) {
    public record Api(URI baseUri, URL legacyUrl) {}
    public record Network(InetAddress bindAddress) {}
    public record Tls(Resource certificate) {}
}
~~~

Khi cấu hình được bind thành công, code có thể gọi `baseUri().getHost()`, `bindAddress().getHostAddress()` hay `certificate().getInputStream()`. Nhưng **binding thành công không chứng minh endpoint truy cập được, DNS còn đúng, hoặc file đọc được**. Những bước kiểm tra đó có ý nghĩa riêng.

Bài này tập trung vào việc chọn kiểu đúng, các ví dụ từ properties/YAML/biến môi trường, quá trình chuyển đổi, các lỗi thường gặp và cách kiểm tra an toàn ở thời điểm khởi động.

## 2. Bức tranh tổng thể của quá trình chuyển đổi

Spring Boot xây dựng một `Environment` từ các nguồn externalized configuration. `@ConfigurationProperties` sử dụng Binder để liên kết giá trị đã được ưu tiên và chuyển đổi sang kiểu khai báo.

~~~text
application.properties / application.yml
             |
     Config Data locations
    profiles / import / override
             |
             v
          Environment
       + PropertySources
             |
             v
       Spring Boot Binder
      (ConversionService)
             |
      +------+------+------+------+
      |      |      |      |      |
     URI    URL  InetAddress Resource
             |
             v
      Configuration bean
             |
             v
          Service
~~~

Ví dụ:

~~~properties
remote.endpoint=https://orders.example.test/api
remote.connect-address=192.0.2.10
remote.public-key=file:/etc/orders/public.pem
~~~

Target:

~~~java
import java.net.InetAddress;
import java.net.URI;
import org.springframework.core.io.Resource;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "remote")
public record RemoteProperties(
        URI endpoint,
        InetAddress connectAddress,
        Resource publicKey
) {}
~~~

Spring Boot có thể chuyển từng giá trị riêng biệt. Nếu một giá trị không thể chuyển sang kiểu đích, quá trình tạo configuration properties bean có thể thất bại với lỗi binding chứa đường dẫn property liên quan.

### 2.1. Ba bước không nên gộp làm một

1. **Parsing source**: đọc YAML hoặc properties và tạo các key/value.
2. **Type conversion**: chuyển giá trị của key thành `URI`, `URL`, `InetAddress` hay `Resource` khi bind.
3. **Sử dụng tài nguyên**: gửi request HTTP, mở file, đọc stream hoặc kết nối tới hostname.

Một URI hợp lệ ở bước 2 vẫn có thể trỏ đến host không tồn tại ở bước 3. Một `Resource` được tạo ở bước 2 có thể không có file tương ứng khi gọi `getInputStream()`. Nhận thức được ranh giới này là nền tảng để chẩn đoán lỗi.

## 3. `URI`: định danh tài nguyên với cú pháp rõ ràng

`java.net.URI` đại diện một định danh tài nguyên theo quy tắc cú pháp của URI. Nó có thể chứa:

- `scheme`, ví dụ `https`, `file` hoặc `mailto`.
- `authority`, thường bao gồm hostname và cổng đối với URL mạng.
- `path`, ví dụ `/v1/orders`.
- `query`, ví dụ `?limit=20`.
- `fragment`, ví dụ `#overview`.

Ví dụ URI tuyệt đối:

~~~text
https://api.example.test:8443/v1/orders?limit=20
~~~

Ví dụ URI tương đối:

~~~text
/v1/orders
~~~

**Cả hai có thể là URI hợp lệ.** Nếu ứng dụng yêu cầu một endpoint HTTP tuyệt đối, khai báo field `URI` không tự đảm bảo có scheme/host phù hợp; cần validation bổ sung.

### 3.1. Binding URI từ properties

~~~properties
app.catalog.endpoint=https://catalog.example.test/v1/items
~~~

Java record:

~~~java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(URI endpoint) {
}
~~~

Khi binding thành công, có thể truy cập:

~~~java
URI uri = properties.endpoint();

String scheme = uri.getScheme();   // https
String host = uri.getHost();       // catalog.example.test
String path = uri.getPath();       // /v1/items
~~~

Để dùng với một Java HTTP client:

~~~java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        properties.endpoint()
).GET().build();
~~~

Đoạn trên mới xây request; chưa gửi mạng vì chưa gọi `send` hoặc `sendAsync`.

### 3.2. Binding URI từ YAML

~~~yaml
app:
  catalog:
    endpoint: "https://catalog.example.test:8443/v1/items?limit=10"
~~~

Quote giúp giá trị rõ là scalar string, nhất là khi có nhiều ký tự phân tách. YAML parser không trực tiếp tạo `URI`; Binder chuyển chuỗi sang `URI`.

### 3.3. URI tương đối và URI tuyệt đối

~~~properties
app.catalog.endpoint=/v1/items
~~~

Giá trị này có thể bind thành một `URI` tương đối. Nếu code cần gọi tới một host HTTP cụ thể, nó không đáp ứng yêu cầu dù parse hợp lệ.

Có thể kiểm tra:

~~~java
URI uri = properties.endpoint();

if (!uri.isAbsolute() || uri.getHost() == null) {
    throw new IllegalArgumentException(
        "app.catalog.endpoint must be an absolute network URI");
}
~~~

Kiểm tra này mới chỉ là bước khởi đầu; cần xem scheme, host, port hoặc whitelist tùy nhu cầu. `URI.isAbsolute()` chỉ kiểm tra có scheme, vì vậy `mailto:user@example.test` là URI tuyệt đối nhưng không phải endpoint HTTP.

### 3.4. URI và encoding

Trong URI, dấu cách trực tiếp và nhiều ký tự đặc biệt cần được mã hóa đúng. Ví dụ:

~~~text
https://example.test/search?q=hello%20world
~~~

khác với một giá trị sai cú pháp chứa dấu cách thô ở vị trí không được phép. Chuyển đổi `String -> URI` không tự sửa mọi chuỗi URL chưa được encode.

Nếu ứng dụng phải xây URI từ những phần dữ liệu động như path segment hoặc query parameter, sử dụng builder phù hợp, ví dụ `UriComponentsBuilder`, thay vì nối chuỗi thủ công mà không encode.

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder
        .fromUri(properties.endpoint())
        .pathSegment("details")
        .queryParam("page", 1)
        .build()
        .toUri();
~~~

Ví dụ này cần module Spring Web chứa `UriComponentsBuilder`. Đối với ứng dụng không sử dụng Spring Web, có thể dùng API URI hoặc thư viện URL builder tương ứng.

### 3.5. Vì sao URI thường là lựa chọn mặc định cho endpoint?

`URI` có tính chất biểu diễn định danh; tạo đối tượng không yêu cầu DNS lookup hay kết nối. API Java HTTP hiện đại như `HttpRequest.newBuilder(URI)` cũng sử dụng `URI`. Vì thế, với một cấu hình endpoint cần được chuyển qua nhiều tầng service, `URI` thường rõ ràng và thuận tiện hơn `URL`.

## 4. `URL`: locator dành cho API có protocol

`java.net.URL` là kiểu có lịch sử lâu đời trong Java, thường được sử dụng bởi những API cần một locator dạng network. Ví dụ:

~~~properties
legacy.partner.url=https://legacy.example.test/api
~~~

~~~java
import java.net.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "legacy.partner")
public record LegacyPartnerProperties(URL url) {
}
~~~

Khi binder hỗ trợ conversion tương ứng, property `url` có thể trở thành một `URL`.

### 4.1. Khác biệt giữa URI và URL

| Tiêu chí | `URI` | `URL` |
| --- | --- | --- |
| Ý nghĩa chính | Định danh tài nguyên | Locator tài nguyên theo protocol |
| Có thể là tương đối | Có | Đường dẫn URL tương đối cần context/base URL phù hợp |
| Kiểm tra cú pháp | Theo quy tắc URI | Theo protocol/handler mà Java biết |
| Tạo đối tượng tự gửi request? | Không | Không |
| Dùng với Java HTTP Client hiện đại | Phù hợp trực tiếp | Thường cần chuyển sang URI |
| Khi nên dùng trong config | Endpoint, định danh và URI nói chung | Khi API thư viện yêu cầu `URL` |

**Không nhầm “URL object đã được tạo” với “URL có thể truy cập”.** Kết nối HTTP, chứng chỉ TLS, DNS, proxy hoặc thời gian phản hồi chỉ được kiểm tra khi phần mềm thực sự thực hiện truy cập mạng.

### 4.2. Ví dụ sử dụng URL

~~~java
import java.net.URL;

URL url = properties.url();

String protocol = url.getProtocol();
String host = url.getHost();
int port = url.getPort();
~~~

Một API Java có thể yêu cầu `URL` làm input. Với API mới chấp nhận `URI`, nên cân nhắc giữ field cấu hình ở kiểu `URI` và chỉ chuyển đổi khi cần.

~~~java
URI endpoint = properties.endpoint();

URL url = endpoint.toURL();
~~~

`toURL()` có thể báo lỗi cho URI không hợp lệ để chuyển thành URL. Nếu một API cần `URL`, khai báo `URL` trực tiếp trong configuration properties cũng là lựa chọn hợp lệ khi khả năng conversion của phiên bản Spring Boot đang dùng hỗ trợ.

### 4.3. URL không phải nơi lưu mọi loại đường dẫn

Đường dẫn như:

~~~text
./certs/service.pem
~~~

không phải một URL network có scheme. Nếu đó là file ứng dụng muốn đọc, hãy xem `Resource` hoặc `Path` phù hợp hơn thay vì khai báo `URL` rồi cố tạo URL từ relative file path.

Với file URL cần dùng chuẩn hợp lệ:

~~~text
file:/etc/myapp/service.pem
~~~

trên một hệ thống tệp tương ứng. Trong ứng dụng đóng gói JAR, file nằm trên classpath thường dễ truy cập hơn qua `Resource`, không nên ép mọi classpath asset thành `URL` rồi giả định nó có file vật lý riêng trên ổ đĩa.

### 4.4. An toàn khi dùng URL để truy cập mạng

Một URL cấu hình có thể trỏ đến hệ thống bên ngoài hoặc địa chỉ mạng nội bộ. Nếu người dùng hoặc nguồn dữ liệu không tin cậy có thể thay đổi URL được ứng dụng tải, có thể phát sinh rủi ro SSRF hoặc lộ dữ liệu.

Khi cần mở URL:

- Chỉ cho phép scheme được chấp nhận, thông thường `https` cho external API.
- Hạn chế host/destination theo chính sách vận hành.
- Đặt connect/read timeout và kiểm soát redirect.
- Không đưa credential hoặc token trực tiếp vào URL query rồi in log.
- Tách việc **parse URL** khỏi việc **thực sự truy cập URL**.

## 5. `InetAddress`: địa chỉ mạng, không phải URL

`java.net.InetAddress` biểu diễn địa chỉ IP của host. Nó thích hợp khi một API Java cần địa chỉ IP đã được phân giải, ví dụ cấu hình bind address cho một socket hoặc giao tiếp ở mức mạng.

~~~properties
app.network.bind-address=127.0.0.1
~~~

~~~java
import java.net.InetAddress;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.network")
public record NetworkProperties(InetAddress bindAddress) {
}
~~~

Khi binder chuyển chuỗi sang `InetAddress`, có thể truy cập:

~~~java
InetAddress address = properties.bindAddress();

String numeric = address.getHostAddress(); // 127.0.0.1
~~~

### 5.1. Địa chỉ IP literal và hostname

Hai cấu hình có ý nghĩa khác:

~~~properties
app.network.bind-address=192.0.2.10
~~~

và:

~~~properties
app.network.bind-address=host.example.test
~~~

Địa chỉ dạng số thường có thể tạo `InetAddress` mà không phải hỏi DNS của hostname. Với tên máy, việc tạo `InetAddress` có thể liên quan đến **name resolution** theo cơ chế của JVM/hệ điều hành. Nếu tên máy không phân giải được, binding có thể thất bại tại startup hoặc trở nên phụ thuộc tình trạng DNS.

Điều này đặc biệt quan trọng khi:

- container khởi động trước khi DNS nội bộ sẵn sàng;
- hostname chỉ phân giải được trong một VPN cụ thể;
- cấu hình chạy local và production dùng DNS khác nhau;
- ứng dụng chỉ cần giữ nguyên tên máy chứ chưa cần địa chỉ IP lúc khởi động.

Nếu yêu cầu của ứng dụng chỉ là xây URL hoặc mở socket tới một hostname sau này, lưu `String hostname` hoặc `URI endpoint` có thể tốt hơn `InetAddress` vì tránh phân giải DNS sớm không cần thiết.

### 5.2. `InetAddress` không chứa port

Ví dụ:

~~~text
192.0.2.10:8080
~~~

là cặp **host + port**, không phải một địa chỉ IP riêng. Không nên đưa nguyên chuỗi đó vào field `InetAddress`.

Thay vào đó:

~~~properties
app.network.host=192.0.2.10
app.network.port=8080
~~~

~~~java
import java.net.InetAddress;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.network")
public record NetworkProperties(
        InetAddress host,
        int port
) {}
~~~

Nếu ứng dụng cần một đối tượng socket endpoint, có thể xây từ các thành phần này theo API phù hợp, ví dụ:

~~~java
import java.net.InetSocketAddress;

InetSocketAddress socketAddress =
        new InetSocketAddress(properties.host(), properties.port());
~~~

Validation vẫn cần kiểm tra `port` thuộc phạm vi hợp lệ của ứng dụng.

### 5.3. IPv4 và IPv6

IPv4 literal:

~~~properties
app.network.bind-address=127.0.0.1
~~~

IPv6 literal:

~~~properties
app.network.bind-address=::1
~~~

Trong YAML nên quote IPv6 để làm rõ scalar:

~~~yaml
app:
  network:
    bind-address: "::1"
~~~

Trong **URI với IPv6 host**, biểu diễn authority thường dùng dấu ngoặc vuông:

~~~properties
app.api.endpoint=http://[::1]:8080/api
~~~

Đừng nhầm cú pháp `InetAddress` là `::1` với cú pháp host của URI `[::1]`. Khi xây endpoint HTTP, nên dùng `URI`; khi cần địa chỉ IP trong API mạng, dùng `InetAddress`.

### 5.4. Kiểu cụ thể `Inet4Address` và `Inet6Address`

`InetAddress` là kiểu cha cho địa chỉ IPv4 và IPv6. Nếu ứng dụng chỉ cho phép một họ địa chỉ, có thể kiểm tra type:

~~~java
import java.net.Inet4Address;

if (!(properties.bindAddress() instanceof Inet4Address)) {
    throw new IllegalArgumentException(
        "app.network.bind-address must be IPv4");
}
~~~

Chỉ khai báo `InetAddress` không bảo đảm giá trị là IPv4 hay IPv6. Một hostname có thể được phân giải thành địa chỉ khác theo DNS và chính sách ưu tiên của JVM/hệ điều hành.

### 5.5. “Phân giải thành IP” không đồng nghĩa “kết nối được”

Kể cả khi `InetAddress` đã được tạo, IP có thể không reachable hoặc không có process đang lắng nghe ở port. Binder không ping host và không mở TCP connection chỉ vì field có kiểu `InetAddress`.

Nếu ứng dụng cần kiểm tra health của endpoint, dùng health check ở lớp vận hành hoặc probe có timeout phù hợp, không coi thành công của type conversion là bằng chứng dịch vụ hoạt động.

## 6. `Resource`: abstraction để đọc tài nguyên

`org.springframework.core.io.Resource` là một interface của Spring Framework. Nó trừu tượng hóa một nguồn dữ liệu, cho phép code đọc nội dung mà không phải biết ngay nguồn nằm trong JAR, trên file system hay ở nơi khác.

Những location thường gặp:

| Chuỗi cấu hình | Ý nghĩa thường dùng |
| --- | --- |
| `classpath:certs/public.pem` | Tài nguyên trong classpath |
| `classpath:/certs/public.pem` | Tài nguyên bắt đầu từ gốc classpath |
| `file:/etc/myapp/keys/public.pem` | File trên filesystem |
| `file:./config/public.pem` | File tương đối theo working directory |
| `https://example.test/assets/schema.json` | URL resource nếu bộ resolver/handler hỗ trợ |
| `config/public.pem` | Location không có prefix; cách diễn giải phụ thuộc ResourceLoader/context |

Khi cấu hình hướng tới file hoặc nội dung cần mở bằng stream, `Resource` thường mang lại API phù hợp hơn `URI` và `URL`.

Ví dụ:

~~~properties
app.security.public-key=classpath:certs/public.pem
~~~

~~~java
import org.springframework.core.io.Resource;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(Resource publicKey) {
}
~~~

Khi nguồn và binder hỗ trợ conversion tương ứng, `publicKey` là một `Resource` trỏ tới location đã khai báo.

### 6.1. Đọc stream từ Resource

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public byte[] loadBytes(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return input.readAllBytes();
    }
}
~~~

Lệnh mở stream mới là lúc code cố truy cập nội dung. Nó có thể ném `IOException` nếu file thiếu, quyền truy cập không đủ hoặc nguồn không khả dụng.

Nếu file có thể rất lớn, tránh `readAllBytes()` trong production; hãy stream hoặc giới hạn kích thước theo yêu cầu. Ví dụ này chỉ nhằm minh họa cách sử dụng.

### 6.2. `Resource` không nhất thiết là `File`

Một lỗi thường gặp là:

~~~java
File file = properties.publicKey().getFile();
~~~

và giả định thao tác luôn hoạt động. Với resource trong một executable JAR, entry nằm **bên trong archive**, không nhất thiết có đường dẫn vật lý riêng có thể truy cập như `java.io.File`.

Cách an toàn hơn để đọc nội dung từ classpath:

~~~java
try (InputStream in = properties.publicKey().getInputStream()) {
    // Xử lý dữ liệu.
}
~~~

Chỉ dùng `getFile()` khi thực sự biết resource nằm trên filesystem và cần một `File` thật.

### 6.3. `exists()` và `isReadable()`

`Resource` cung cấp các phương thức như `exists()`, `isReadable()` và `getInputStream()`. Có thể kiểm tra trước khi đọc:

~~~java
Resource resource = properties.publicKey();

if (!resource.exists()) {
    throw new IllegalStateException(
        "Configured public key resource does not exist");
}
~~~

Dù vậy, vẫn có race condition: một file tồn tại tại thời điểm kiểm tra có thể bị xóa trước khi mở stream. Bởi vậy, cần xử lý `IOException` tại chính điểm đọc.

Không nên coi `Resource.exists()` là một kiểm tra bảo mật. Nó chỉ trả lời về sự tồn tại theo cơ chế của resource implementation.

### 6.4. Relative resource location

~~~properties
app.security.public-key=file:./config/public.pem
~~~

Đường dẫn `./` thường được hiểu dựa trên **working directory của tiến trình Java**, không phải thư mục chứa JAR. Chạy cùng JAR từ hai working directory khác nhau có thể dẫn tới hai file khác nhau hoặc lỗi không tìm thấy.

Trong container, nên kiểm tra `WORKDIR`, `workingDir` và mount path. Với file external ổn định, đường dẫn tuyệt đối như `file:/etc/myapp/public.pem` thường ít gây bất ngờ hơn.

### 6.5. Không nhầm `classpath:` với `file:`

~~~properties
app.security.public-key=classpath:certs/public.pem
~~~

nghĩa là tìm trong classpath, phù hợp với resource nằm trong `src/main/resources/certs/public.pem` rồi được đóng gói vào artifact.

~~~properties
app.security.public-key=file:/etc/myapp/public.pem
~~~

nghĩa là một file external cần tồn tại trên filesystem của môi trường chạy.

Dùng `classpath:` cho file cần thay đổi độc lập với JAR không thuận tiện, vì file thường gắn với bản build. Dùng `file:` cho một resource đóng gói trong JAR cũng không đúng nếu không thực sự có file external.

## 7. Ví dụ tổng hợp với cả bốn kiểu

Giả sử ứng dụng cần cấu hình cho một dịch vụ remote và một file trust material:

~~~yaml
app:
  remote:
    base-uri: "https://api.example.test:8443/v1"
    legacy-url: "https://legacy.example.test/v2"
    bind-address: "127.0.0.1"
    trust-bundle: "classpath:tls/trust.pem"
~~~

Record:

~~~java
package com.example.client.config;

import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        URI baseUri,
        URL legacyUrl,
        InetAddress bindAddress,
        Resource trustBundle
) {}
~~~

Đăng ký:

~~~java
package com.example.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` tìm các class có annotation trong package phù hợp. Với record constructor binding trong Spring Boot 3.x, cách đăng ký này phù hợp hơn việc đặt `@Component` và hy vọng Spring tự bind các tham số constructor bằng property.

Service sử dụng:

~~~java
package com.example.client.service;

import com.example.client.config.RemoteProperties;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.stereotype.Service;

@Service
public class RemoteClientSettingsReader {

    private final RemoteProperties properties;

    public RemoteClientSettingsReader(RemoteProperties properties) {
        this.properties = properties;
    }

    public String host() {
        return properties.baseUri().getHost();
    }

    public String localBindIp() {
        return properties.bindAddress().getHostAddress();
    }

    public byte[] readTrustBundle() throws IOException {
        try (InputStream input =
                     properties.trustBundle().getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

Ví dụ trên minh họa việc tiêu thụ cấu hình có kiểu. Nó **không** tự tạo HTTP client an toàn, cấu hình TLS, xác minh chứng chỉ hay kết nối mạng. Những thao tác đó cần thư viện và kiến trúc riêng.

## 8. Khai báo tương đương trong `application.properties`

Bốn thuộc tính YAML ở phần trước có thể viết:

~~~properties
app.remote.base-uri=https://api.example.test:8443/v1
app.remote.legacy-url=https://legacy.example.test/v2
app.remote.bind-address=127.0.0.1
app.remote.trust-bundle=classpath:tls/trust.pem
~~~

Spring Boot Binder sử dụng relaxed binding: `base-uri` tương ứng với Java `baseUri`, `bind-address` với `bindAddress`, `trust-bundle` với `trustBundle`.

Nếu dùng JavaBean mutable:

~~~java
import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.remote")
public class RemotePropertiesBean {

    private URI baseUri;
    private URL legacyUrl;
    private InetAddress bindAddress;
    private Resource trustBundle;

    public URI getBaseUri() { return baseUri; }
    public void setBaseUri(URI value) { baseUri = value; }

    public URL getLegacyUrl() { return legacyUrl; }
    public void setLegacyUrl(URL value) { legacyUrl = value; }

    public InetAddress getBindAddress() { return bindAddress; }
    public void setBindAddress(InetAddress value) { bindAddress = value; }

    public Resource getTrustBundle() { return trustBundle; }
    public void setTrustBundle(Resource value) { trustBundle = value; }
}
~~~

`@Component` yêu cầu class nằm trong phạm vi component scanning. JavaBean có setter là mô hình phù hợp khi đăng ký bằng component scanning thông thường. Với record bất biến, dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 9. Nguồn externalized configuration và thứ tự ưu tiên

Spring Boot có thể đọc các khóa trên từ nhiều nguồn. Ví dụ, trong JAR:

~~~properties
# application.properties
app.remote.base-uri=https://api.default.example/v1
app.remote.bind-address=127.0.0.1
app.remote.trust-bundle=classpath:tls/default.pem
~~~

Bên ngoài JAR:

~~~properties
# file:./config/application.properties
app.remote.base-uri=https://api.production.example/v1
app.remote.trust-bundle=file:/etc/app/tls/trust.pem
~~~

Trong tình huống tìm kiếm Config Data mặc định thông thường, file external có độ ưu tiên cao hơn file trong JAR. Khi binding, Boot chọn giá trị hiệu lực cho từng key rồi chuyển sang kiểu Java phù hợp.

Giá trị của `app.remote.bind-address` có thể vẫn lấy từ file cơ sở trong JAR, còn `base-uri` và `trust-bundle` đến từ file external. Một `@ConfigurationProperties` object có thể kết hợp các field được cung cấp từ **nhiều property sources**; không cần tất cả field ở cùng một file.

### 9.1. Ghi đè bằng command-line argument

~~~bash
java -jar app.jar \
  --app.remote.base-uri=https://canary.example.test/v1 \
  --app.remote.bind-address=0.0.0.0
~~~

Trong cấu hình Spring Boot thông dụng, command-line properties có ưu tiên cao so với Config Data. Binder nhận chuỗi mới rồi convert sang `URI` và `InetAddress`.

`0.0.0.0` thường được dùng làm địa chỉ bind trên mọi IPv4 interface khi API socket cho phép, không phải một hostname đích để gửi request ra Internet. Không coi nó như endpoint HTTP có thể gọi tới.

### 9.2. Biến môi trường

Dạng tên môi trường thường dùng với relaxed binding:

~~~text
APP_REMOTE_BASEURI
APP_REMOTE_LEGACYURL
APP_REMOTE_BINDADDRESS
APP_REMOTE_TRUSTBUNDLE
~~~

Ví dụ trong shell:

~~~bash
export APP_REMOTE_BASEURI="https://api.production.example/v1"
export APP_REMOTE_BINDADDRESS="127.0.0.1"
export APP_REMOTE_TRUSTBUNDLE="file:/etc/app/tls/trust.pem"

java -jar app.jar
~~~

Quy tắc chuyển tên canonical sang env var thường là: dấu chấm thành underscore, loại dấu gạch nối rồi chuyển chữ sang uppercase. Vì vậy `base-uri` thường trở thành `BASEURI`, không nên mặc nhiên dùng `BASE_URI` và kỳ vọng mọi cơ chế đều xử lý giống nhau.

Với tên property đơn giản như `server.address`, tên biến môi trường là `SERVER_ADDRESS`. Khi tên có dấu gạch nối và collection indices, cần đặc biệt cẩn thận.

### 9.3. Profile-specific configuration

~~~properties
# application-dev.properties
app.remote.base-uri=http://localhost:8081/v1
app.remote.bind-address=127.0.0.1
app.remote.trust-bundle=classpath:tls/dev.pem
~~~

~~~properties
# application-prod.properties
app.remote.base-uri=https://api.example.test/v1
app.remote.bind-address=10.0.0.5
app.remote.trust-bundle=file:/etc/app/tls/prod.pem
~~~

Việc nạp profile quyết định giá trị chuỗi nào hiện diện và có ưu tiên; kiểu Java khai báo vẫn giữ nguyên. Một `Resource` chỉ thay đổi location, còn code sử dụng `getInputStream()` có thể giữ nguyên.

Không nên lưu secret thật trong profile-specific file được commit. Profile là cách chọn cấu hình, không phải cơ chế bảo vệ dữ liệu.

## 10. Placeholder trước và trong quá trình binding

Các giá trị chuyển đổi cũng có thể chứa placeholder `${...}`:

~~~properties
app.api.scheme=https
app.api.host=api.example.test
app.api.port=8443

app.remote.base-uri=${app.api.scheme}://${app.api.host}:${app.api.port}/v1
app.remote.trust-bundle=${APP_TRUST_RESOURCE:classpath:tls/default.pem}
~~~

Khi Spring Boot phân giải các property theo cơ chế cấu hình tương ứng, các placeholder có thể được thay bằng giá trị được tra cứu từ `Environment` trước khi chuyển thành `URI` hay `Resource`.

Ví dụ, khi `APP_TRUST_RESOURCE` được cung cấp là `file:/etc/app/trust.pem`, `trustBundle` có thể trỏ tới file external. Nếu thiếu, giá trị mặc định của placeholder là `classpath:tls/default.pem`.

### 10.1. Default không bảo đảm tài nguyên tồn tại

~~~properties
app.remote.trust-bundle=${APP_TRUST_RESOURCE:classpath:tls/default.pem}
~~~

Nếu file `tls/default.pem` không thực sự nằm trong classpath của artifact, việc tạo `Resource` vẫn có thể thành công nhưng mở stream có thể thất bại. Cú pháp placeholder chỉ cung cấp location mặc định, không kiểm chứng nội dung nguồn.

### 10.2. Cẩn thận với shell expansion

Nếu truyền literal `${APP_TRUST_RESOURCE:...}` từ lệnh Bash, shell có thể diễn giải chuỗi `${...}` trước khi Java chạy. Đặt đối số trong single quotes của POSIX shell nếu muốn Spring nhận nguyên placeholder:

~~~bash
java -jar app.jar \
  '--app.remote.trust-bundle=${APP_TRUST_RESOURCE:classpath:tls/default.pem}'
~~~

Trong file `application.properties` và YAML do Spring Boot trực tiếp nạp, shell không tự xử lý chuỗi như trên.

## 11. Resource location và cách resolver chọn implementation

`Resource` là interface; implementation cụ thể phụ thuộc vào location và `ResourceLoader`/conversion mechanism.

Một số ví dụ:

| Location | Resource implementation điển hình | Đặc điểm |
| --- | --- | --- |
| `classpath:config/default.json` | `ClassPathResource` | Có thể hoạt động khi asset ở trong JAR |
| `file:/etc/app/config.json` | `FileSystemResource` hoặc tương đương | File hệ thống tệp |
| `https://example.test/config.json` | `UrlResource` hoặc tương đương | Có thể cần request qua mạng khi mở |
| Location tương đối không prefix | Phụ thuộc context và loader | Tránh dùng nếu cần hành vi portable |

Không nên phụ thuộc vào tên class implementation ở business code trừ khi có yêu cầu đặc biệt. Tốt hơn là lập trình theo interface `Resource` và dùng `getInputStream()` khi cần.

### 11.1. Classpath resource trong executable JAR

~~~text
src/main/resources/
└── tls/
    └── trust.pem
~~~

Cấu hình:

~~~properties
app.remote.trust-bundle=classpath:tls/trust.pem
~~~

Sau build, resource có thể nằm bên trong JAR. Đây là lý do code đọc `InputStream` phù hợp hơn code đòi hỏi `File`.

Nếu tài nguyên phải được thay đổi bởi bộ phận vận hành mà không rebuild, có thể chọn `file:/etc/app/tls/trust.pem` và mount file ở môi trường triển khai.

### 11.2. Resource path có thể được dùng bởi loader khác

Không phải mọi thư viện nhận chuỗi `classpath:...` đều biết cú pháp này. Nó là quy ước location phổ biến của Spring ResourceLoader. Nếu thư viện yêu cầu một filesystem path thuần, có thể phải cung cấp `Path` hoặc stream thay vì đưa nguyên chuỗi `classpath:...`.

Ngược lại, nếu method nhận Spring `Resource`, đưa resource object trực tiếp thường làm giảm phụ thuộc vào chi tiết nguồn.

### 11.3. Không nhầm `Resource` với nhiều resource

Một field `Resource` đại diện cho **một tài nguyên**. Các mẫu wildcard như `classpath*:/**/*.xml` thuộc cơ chế tìm **nhiều tài nguyên** của `ResourcePatternResolver`, không tự có cùng ý nghĩa khi gán vào một field `Resource`.

Ví dụ nếu cần nhiều file schema trong classpath:

~~~java
import java.io.IOException;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

PathMatchingResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] schemas =
        resolver.getResources("classpath*:schemas/*.xsd");
~~~

Đây là lookup theo pattern, không phải conversion đơn giản của một chuỗi thành một `Resource`. Nếu muốn cấu hình danh sách các vị trí file cụ thể, có thể dùng `List<Resource>` trong một configuration properties class nếu Binder/converter phù hợp.

## 12. Mảng và List của các kiểu chuyển đổi

Spring Boot Binder có thể xử lý collections gồm các giá trị có converter tương ứng.

Ví dụ:

~~~yaml
app:
  peers:
    endpoints:
      - "https://peer-a.example.test/api"
      - "https://peer-b.example.test/api"
    addresses:
      - "192.0.2.10"
      - "192.0.2.11"
    certificates:
      - "classpath:certs/a.pem"
      - "file:/etc/app/certs/b.pem"
~~~

Java:

~~~java
import java.net.InetAddress;
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties(prefix = "app.peers")
public record PeerProperties(
        List<URI> endpoints,
        List<InetAddress> addresses,
        List<Resource> certificates
) {}
~~~

Mỗi phần tử được chuyển sang kiểu phù hợp. Nếu một phần tử sai cú pháp, lỗi có thể chỉ ra key indexed như `app.peers.endpoints[1]`.

### 12.1. Indexed properties

~~~properties
app.peers.endpoints[0]=https://peer-a.example.test/api
app.peers.endpoints[1]=https://peer-b.example.test/api

app.peers.addresses[0]=192.0.2.10
app.peers.addresses[1]=192.0.2.11

app.peers.certificates[0]=classpath:certs/a.pem
app.peers.certificates[1]=file:/etc/app/certs/b.pem
~~~

Indexed properties phù hợp khi mỗi phần tử có dấu phẩy hoặc khi cần phân biệt rõ ranh giới phần tử.

### 12.2. Không tự ghép list ở nhiều PropertySource

Khi list được khai báo từ file cơ sở và file profile-specific với độ ưu tiên cao hơn, Binder thường sử dụng **list của nguồn ưu tiên cao hơn** chứ không cộng các phần tử của mọi source.

Nếu có:

~~~yaml
# application.yml
app:
  peers:
    endpoints:
      - https://dev-a.example.test
      - https://dev-b.example.test
~~~

và:

~~~yaml
# application-prod.yml
app:
  peers:
    endpoints:
      - https://prod.example.test
~~~

với profile `prod`, trong tình huống đơn giản, `endpoints` hiệu lực là list một URI production. Nó không tự biến thành ba endpoint. Quy tắc này quan trọng khi danh sách chứa URI/Resource mà người vận hành mong append theo môi trường.

## 13. Validation: đúng kiểu chưa chắc đúng nghĩa

Binding giúp loại bỏ một lớp lỗi cú pháp và conversion. Nhưng nó không thay thế các quy tắc ứng dụng.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.api")
public record ApiProperties(
        @NotNull URI endpoint
) {}
~~~

`@NotNull` bảo đảm object không null, **không bảo đảm URI dùng scheme https, có host hoặc thuộc allowlist**.

### 13.1. Kiểm tra URI HTTP(S) tuyệt đối

~~~java
import java.net.URI;

public static void requireHttpEndpoint(URI endpoint) {
    if (endpoint == null) {
        throw new IllegalArgumentException("Endpoint is required");
    }

    String scheme = endpoint.getScheme();
    boolean http = "http".equalsIgnoreCase(scheme);
    boolean https = "https".equalsIgnoreCase(scheme);

    if ((!http && !https) || endpoint.getHost() == null) {
        throw new IllegalArgumentException(
            "Endpoint must be an absolute HTTP(S) URI with a host");
    }
}
~~~

Nếu môi trường chỉ cho phép HTTPS, loại bỏ nhánh HTTP hoặc kiểm tra bằng một validation rule rõ. Với endpoint chứa port, có thể yêu cầu port nằm trong phạm vi cho phép.

### 13.2. Kiểm tra URL phù hợp nghiệp vụ

Một `URL` được tạo thành công có thể sử dụng protocol mà ứng dụng không muốn hỗ trợ. Kiểm tra `getProtocol()` và host theo chính sách.

Không gọi `openStream()` chỉ để “validation” mọi URL từ nguồn không tin cậy; thao tác đó gây I/O và có thể truy cập mạng ngoài ý định.

### 13.3. Kiểm tra InetAddress theo mục đích

Nếu cần địa chỉ bind local, ứng dụng có thể yêu cầu:

- IPv4 hoặc IPv6 theo khả năng server.
- Địa chỉ loopback trong môi trường development.
- Một địa chỉ được cấu hình trên network interface của container.
- Không cho phép wildcard address trong một số chế độ an toàn.

Bản thân `InetAddress` không xác minh địa chỉ có thực sự được assign cho network interface hiện tại. Đó là một kiểm tra khác, đôi khi cần làm khi khởi động socket server.

### 13.4. Kiểm tra Resource theo loại file

Nếu một chứng chỉ bắt buộc:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public static void requireReadable(Resource resource) {
    if (resource == null || !resource.exists() || !resource.isReadable()) {
        throw new IllegalStateException("Required resource is unavailable");
    }

    try (InputStream ignored = resource.getInputStream()) {
        // Đã mở được stream; parse nội dung ở lớp cần thiết.
    } catch (IOException e) {
        throw new IllegalStateException("Cannot read required resource", e);
    }
}
~~~

Đây là kiểm tra tính sẵn có, chưa phải xác minh rằng nội dung thực sự là certificate/key hợp lệ. Với TLS material, cần parser phù hợp và kiểm soát lỗi, quyền đọc, bảo mật.

Nếu resource là URL trên mạng, `exists()`/`isReadable()` có thể cần I/O; không nên sử dụng như một bước validation đồng bộ tùy tiện trên luồng startup nếu nguồn không được tin cậy hoặc không kiểm soát timeout.

## 14. Jakarta Validation và cấu hình bắt buộc

Khi dùng `@Validated` cùng Bean Validation provider phù hợp (thường qua `spring-boot-starter-validation`), Boot có thể kiểm tra cấu hình sớm.

~~~java
import jakarta.validation.constraints.NotNull;
import java.net.InetAddress;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        @NotNull URI endpoint,
        @NotNull InetAddress bindAddress,
        @NotNull Resource certificate
) {}
~~~

Các annotation trên kiểm tra **sự hiện diện của đối tượng**. Nếu yêu cầu URL tuyệt đối, certificate phải tồn tại hoặc IP phải thuộc một miền cho phép, cần thêm custom validation hoặc logic startup thích hợp.

### 14.1. Vì sao không dùng `@NotBlank` trên URI/Resource?

`@NotBlank` được thiết kế cho `CharSequence`. Nếu gắn lên `URI`, `InetAddress` hoặc `Resource`, Bean Validation có thể không có validator phù hợp và báo lỗi.

Với object này, có thể dùng `@NotNull`, custom constraint hoặc phương thức kiểm tra cụ thể. Không sử dụng annotation chỉ vì tên nghe đúng với ý định.

### 14.2. Kiểm tra trong constructor record

Nếu muốn hợp đồng bất biến của object luôn đúng, có thể kiểm tra một phần ngay tại constructor:

~~~java
@ConfigurationProperties(prefix = "app.api")
public record ApiProperties(URI endpoint) {
    public ApiProperties {
        if (endpoint == null || endpoint.getHost() == null) {
            throw new IllegalArgumentException(
                "app.api.endpoint must contain a host");
        }
    }
}
~~~

Trường hợp này vẫn cần kiểm tra scheme và các yêu cầu khác nếu ứng dụng đòi hỏi. Exception có thể được Spring Boot bọc bởi lỗi binding hoặc khởi tạo configuration properties; đó là hành vi hợp lý khi cấu hình không hợp lệ.

## 15. Custom converter khi giá trị không khớp quy ước chuẩn

Bốn kiểu cơ bản thường đã có đường chuyển đổi phù hợp trong Spring Boot/Spring Framework. Nhưng ứng dụng đôi khi nhận cấu hình theo định dạng đặc biệt, chẳng hạn một chuỗi định danh nội bộ cần chuyển thành object domain.

Không nên thêm converter tùy ý chỉ để chữa một URL sai cú pháp hoặc hostname không tồn tại. Trước tiên, bảo đảm dữ liệu nguồn đúng.

Ví dụ một kiểu domain:

~~~java
public record EndpointId(String region, String service) {
}
~~~

Cấu hình:

~~~properties
app.endpoint-id=ap-southeast-1/catalog
~~~

Converter:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class EndpointIdConverter implements Converter<String, EndpointId> {

    @Override
    public EndpointId convert(String value) {
        String[] parts = value.split("/", 2);

        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            throw new IllegalArgumentException(
                "Expected '<region>/<service>'");
        }

        return new EndpointId(parts[0], parts[1]);
    }
}
~~~

`@ConfigurationPropertiesBinding` đánh dấu converter được sử dụng cho configuration properties. Trong các phiên bản Boot hiện đại, cần bảo đảm converter được đăng ký đúng giai đoạn để Binder có thể sử dụng; với những converter tạo sớm, tránh inject các bean phụ thuộc vào application context chưa hoàn chỉnh.

Mục đích của ví dụ là làm rõ extension point. Không nhất thiết thay các converter sẵn có cho `URI`, `URL`, `InetAddress` hay `Resource` nếu định dạng chuẩn đã đáp ứng yêu cầu.

### 15.1. Converter không nên có side effect

Một converter chuyển hostname thành một object domain không nên tự tạo tài khoản, gửi HTTP request hoặc sửa file. Những side effect đó khiến binding cấu hình trở thành quy trình không kiểm soát được.

Với `InetAddress`, bản thân conversion có thể kéo theo DNS lookup; đây là một lý do để chọn `String` nếu không muốn hạ tầng DNS ảnh hưởng tới startup.

## 16. Ví dụ cấu hình an toàn cho production

Một service cần API endpoint, địa chỉ bind và file trust store:

~~~yaml
app:
  integration:
    endpoint: "https://integration.example.test/v2"
    bind-address: "0.0.0.0"
    trust-resource: "file:/etc/app/tls/trust.pem"
~~~

Java:

~~~java
import java.net.InetAddress;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        URI endpoint,
        InetAddress bindAddress,
        Resource trustResource
) {}
~~~

Nếu môi trường deployment cung cấp file `/etc/app/tls/trust.pem`, code có thể đọc qua `Resource.getInputStream()`. Nhưng cần tự cấu hình thư viện HTTP/TLS sử dụng nội dung đó, đồng thời kiểm soát permission.

Một deployment container có thể mount ConfigMap/Secret hoặc persistent volume tại đường dẫn đã định. Spring Boot không tự mount file chỉ vì `Resource` trỏ tới location đó.

### 16.1. Những điều cần kiểm tra trước khi triển khai

- Scheme của `endpoint` là HTTPS đúng chính sách.
- Host không phải địa chỉ không tin cậy nếu endpoint có thể bị tác động bởi user input.
- DNS và route mạng đến endpoint hoạt động tại thời điểm gửi request.
- Bind address phù hợp network interface của container.
- File trust resource được mount đúng, có quyền đọc và nội dung hợp lệ.
- Quy trình restart khi cấu hình hoặc secret thay đổi được thiết kế rõ.
- Không log credential, private key hoặc nội dung resource nhạy cảm.

## 17. Xử lý file trong JAR và file external

### 17.1. Asset đóng gói trong JAR

~~~text
src/main/resources/
└── policies/
    └── access-rules.json
~~~

Cấu hình:

~~~properties
app.policy.resource=classpath:policies/access-rules.json
~~~

Java:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public String readPolicy(Resource resource) throws IOException {
    try (var stream = resource.getInputStream()) {
        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Kể cả khi chạy executable JAR, đọc qua `getInputStream()` thường vẫn có ý nghĩa nếu resource thực sự nằm trên classpath.

### 17.2. File được mount ngoài ứng dụng

~~~properties
app.policy.resource=file:/etc/app/policies/access-rules.json
~~~

Cùng code đọc stream ở trên có thể hoạt động mà không cần thay đổi Java class. Đây là lợi ích của `Resource`: thay location bằng externalized configuration.

### 17.3. Không mặc định live reload

Nếu một file mounted được sửa sau khi ứng dụng đã khởi động, object `Resource` có thể vẫn trỏ tới location cũ và những lần mở stream mới có thể thấy nội dung mới, tùy nguồn. Nhưng **nếu service đã đọc file một lần và cache nội dung trong bộ nhớ**, sửa file không tự khiến dữ liệu đã parse được làm mới.

Tương tự, việc đổi property `app.policy.resource` trên disk sau startup không tự bind lại field trong bean. Hệ thống cần cơ chế reload/restart rõ ràng, nhất là với chính sách bảo mật.

## 18. Unit test và integration test cho type conversion

Đối với cấu hình có kiểu, nên kiểm thử đường conversion trong môi trường Spring Boot thật thay vì chỉ tự gọi constructor Java.

Giả sử:

~~~java
import java.net.InetAddress;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.test")
public record TestProperties(
        URI endpoint,
        InetAddress address
) {}
~~~

Một test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    classes = ConversionBindingTest.TestConfig.class,
    properties = {
        "app.test.endpoint=https://test.example.test/v1",
        "app.test.address=127.0.0.1"
    }
)
class ConversionBindingTest {

    @org.springframework.boot.SpringBootConfiguration
    @EnableConfigurationProperties(TestProperties.class)
    static class TestConfig {}

    @Autowired
    TestProperties properties;

    @Test
    void bindsUriAndIpAddress() {
        assertEquals("https", properties.endpoint().getScheme());
        assertEquals("test.example.test",
                     properties.endpoint().getHost());
        assertEquals("127.0.0.1",
                     properties.address().getHostAddress());
    }
}
~~~

Test tránh hostname phải lookup DNS để kết quả ít phụ thuộc môi trường. `example.test` trong URI được dùng để kiểm tra parsing, không thực hiện network call.

### 18.1. Test với Resource

Có thể đặt một file test:

~~~text
src/test/resources/
└── samples/
    └── test-config.txt
~~~

Thuộc tính test:

~~~properties
app.test.resource=classpath:samples/test-config.txt
~~~

Assertion:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

assertTrue(properties.resource().exists());
~~~

Để kiểm tra nội dung, mở `getInputStream()` trong test có xử lý `IOException`. Một `Resource` từ classpath không bắt buộc có `File` tương ứng, vì vậy test cũng không nên dựa vào `getFile()`.

### 18.2. Test trường hợp lỗi

Những tình huống nên bao gồm:

- URI thiếu scheme khi endpoint HTTP tuyệt đối là bắt buộc.
- URI chứa ký tự không hợp lệ.
- URL có protocol không được ứng dụng cho phép.
- `InetAddress` nhận một hostname không phân giải được trong môi trường test, nếu đây là trường hợp cần được kiểm tra có kiểm soát.
- `Resource` trỏ tới file không tồn tại nhưng được yêu cầu bắt buộc.
- Một property được nguồn ưu tiên cao hơn ghi đè thành location sai.
- Cấu hình IPv6 với định dạng đúng cho `InetAddress` và URI.
- Bài test không thực hiện request tới hệ thống bên ngoài chỉ để chứng minh binding.

Nếu cố ý test lỗi DNS, cần bảo đảm timeout và môi trường kiểm thử phù hợp; nhiều test trên CI không nên phụ thuộc vào DNS thật.

## 19. Chẩn đoán lỗi thường gặp

### 19.1. `Failed to bind properties`

Lỗi như:

~~~text
Failed to bind properties under 'app.remote.base-uri'
~~~

có thể bắt nguồn từ conversion, thiếu kiểu phù hợp hoặc cấu hình nguồn. Thường cần xem nguyên nhân bên trong, chẳng hạn `IllegalArgumentException`, `URISyntaxException` hoặc lỗi network resolution.

Các bước:

1. Kiểm tra tên prefix trong `@ConfigurationProperties`.
2. Kiểm tra field Java có đúng kiểu và tên relaxed binding không.
3. Xác định property source nào đang cung cấp giá trị cuối.
4. Kiểm tra cú pháp YAML/properties.
5. Xem trường hợp converter không xử lý được giá trị.
6. Phân biệt conversion fail và lỗi khi code thực sự sử dụng object.

Không chữa lỗi binding bằng cách đổi mọi field thành `String` mà bỏ qua validation. Chuyển sang `String` chỉ hợp lý nếu ứng dụng thật sự cần giữ nguyên input dạng text hoặc muốn chủ động defer conversion.

### 19.2. URI chứa khoảng trắng

~~~properties
app.remote.base-uri=https://api.example.test/my path
~~~

Chuỗi có khoảng trắng thô trong URI có thể không hợp lệ. Hãy encode đúng hoặc sử dụng builder khi xây từ phần động:

~~~properties
app.remote.base-uri=https://api.example.test/my%20path
~~~

Không cho rằng Binder sẽ tự encode mọi ký tự không hợp lệ.

### 19.3. URL thiếu protocol

~~~properties
app.remote.legacy-url=api.example.test/v1
~~~

Một `URL` thường yêu cầu protocol phù hợp. Nếu mục đích là một đường dẫn tương đối, có thể chọn `URI` tương đối hoặc `Resource`/`Path` tùy ngữ nghĩa thay vì ép thành URL.

### 19.4. InetAddress chứa cả cổng

~~~properties
app.network.bind-address=127.0.0.1:8080
~~~

Chuỗi này không biểu diễn một IP literal thuần. Tách host và port thành hai property:

~~~properties
app.network.bind-address=127.0.0.1
app.network.bind-port=8080
~~~

### 19.5. InetAddress phụ thuộc DNS

~~~properties
app.network.bind-address=internal-host
~~~

Nếu môi trường không phân giải `internal-host`, binding có thể thất bại. Nếu ứng dụng không thật sự cần IP resolved tại startup, chọn `String hostname` và phân giải muộn hơn trong lớp kết nối.

### 19.6. Resource không tồn tại

~~~properties
app.security.public-key=classpath:certs/missing.pem
~~~

Bản thân `Resource` được bind có thể tồn tại như một handle, nhưng `getInputStream()` sẽ thất bại khi file thực tế thiếu. Kiểm tra packaging của JAR, đúng đường dẫn và chữ hoa/chữ thường; trong Linux filesystem, phân biệt chữ hoa và chữ thường có thể làm khác kết quả so với máy phát triển.

### 19.7. `getFile()` trên classpath resource trong JAR

Code:

~~~java
properties.publicKey().getFile();
~~~

có thể lỗi nếu file nằm trong archive. Sử dụng `getInputStream()` hoặc trích xuất ra file tạm một cách có chủ đích nếu một thư viện bắt buộc nhận `File`. Khi trích xuất, cần kiểm soát quyền truy cập, cleanup và dữ liệu nhạy cảm.

### 19.8. URL/Resource load từ nguồn không tin cậy

Nếu property được thiết lập bằng đầu vào tùy ý, ứng dụng có thể bị dẫn tới file local hoặc endpoint nội bộ. Không sử dụng `Resource` làm cơ chế đọc file tùy ý được cấp từ request của user. Ràng buộc allowed scheme, path root và host theo chính sách.

### 19.9. YAML parse lỗi trước khi bind

~~~yaml
app:
  remote:
    bind-address: ::1
~~~

Cú pháp YAML có thể diễn giải ký tự đặc biệt theo ngữ cảnh. Với IPv6, nên quote:

~~~yaml
app:
  remote:
    bind-address: "::1"
~~~

### 19.10. Cấu hình đã đổi nhưng ứng dụng chưa nhận

`@ConfigurationProperties` thường bind tại startup. Sửa `application.yml` hoặc biến môi trường của shell khác không tự khiến bean đang chạy được tạo lại. Restart hoặc cơ chế refresh được thiết kế riêng mới áp dụng thay đổi một cách có kiểm soát.

## 20. So sánh với `String` và `Path`

Không phải lúc nào dùng kiểu phức tạp cũng tốt. Chọn kiểu theo **mục đích sử dụng**.

| Nhu cầu | Kiểu nên cân nhắc | Vì sao |
| --- | --- | --- |
| HTTP endpoint đã biết scheme và host | `URI` | Biểu diễn định danh URL mạng với cấu trúc rõ |
| Tích hợp thư viện yêu cầu `URL` | `URL` | Tránh chuyển đổi tại nhiều vị trí sử dụng |
| Cần địa chỉ IP để bind socket | `InetAddress` | API mạng thao tác trực tiếp với IP |
| Muốn giữ hostname, để DNS resolve lúc connect | `String` | Không ép phân giải DNS trong lúc binding |
| Cần đọc file trong JAR hoặc ngoài filesystem | `Resource` | Một API stream thống nhất cho nhiều nguồn |
| Cần path filesystem thuần để thao tác NIO | `Path` | Phù hợp `Files`, `Path.resolve` và quyền file |
| Cần URL đã được build từ các phần động | `URI` và builder | Tránh nối chuỗi/encode sai |
| Cần danh sách các endpoint | `List<URI>` | Binder chuyển đổi từng phần tử |

**Không dùng `InetAddress` thay cho `URI`** chỉ vì URL có host. `InetAddress` không chứa scheme, port, path hoặc query. **Không dùng `Resource` thay cho URL endpoint** nếu ứng dụng thực sự cần gửi HTTP request theo protocol riêng và xử lý response/status/authentication.

### 20.1. Khi nào giữ String?

Một URL có placeholder hoặc hostname chỉ có ý nghĩa trong một subsystem đặc thù, và subsystem đó tự parse theo quy tắc khác Java URI. Khi ấy, giữ `String` có thể phù hợp. Nhưng cần bổ sung validation tại đúng boundary. Không nên giữ mọi thứ ở `String` rồi ngầm để từng service parse lại theo cách khác nhau.

### 20.2. Khi nào chọn Path?

`java.nio.file.Path` hướng tới vị trí file trên filesystem. Nó hữu ích nếu chương trình phải thao tác bằng `Files.readString`, `Files.newInputStream` hoặc `Files.move`. Nhưng `Path` không tự biết cú pháp Spring `classpath:`; đừng chuyển đường dẫn classpath trong JAR thành `Path` rồi mong nó có filesystem entry.

`Resource` là lựa chọn tự nhiên hơn khi nguồn có thể nằm cả trong classpath và external filesystem.

## 21. Lưu ý về thời điểm conversion và phụ thuộc hạ tầng

Các kiểu không có chi phí khởi tạo giống nhau:

- Tạo `URI` thường chỉ xử lý cú pháp chuỗi, không bắt buộc network.
- Tạo `URL` thường kiểm tra protocol/handler, không tự gửi HTTP request.
- Tạo `InetAddress` từ hostname có thể cần DNS resolution và chịu ảnh hưởng môi trường.
- Tạo `Resource` thường tạo handle tới location; kiểm tra existence hay mở stream có thể thực hiện I/O tùy implementation.

Nếu muốn startup ít phụ thuộc dịch vụ bên ngoài, tránh những chuyển đổi hoặc bước validation khiến ứng dụng phải gọi DNS/HTTP không cần thiết. Ngược lại, nếu tài nguyên như chứng chỉ hoặc file policy là **bắt buộc**, kiểm tra sớm ở startup có thể hữu ích để phát hiện sai deployment.

Một thiết kế tốt tách:

1. **Phân giải cấu hình có kiểu** để biết giá trị hợp lệ về mặt cấu trúc.
2. **Kiểm tra hợp đồng ứng dụng** để bảo đảm các yêu cầu nghiệp vụ/kỹ thuật.
3. **Kiểm tra kết nối hoặc tài nguyên thực tế** ở thời điểm phù hợp, với timeout và cơ chế xử lý lỗi.

## 22. Tình huống vận hành: cấu hình cùng JAR cho local và Kubernetes

Giả sử một ứng dụng dùng certificate đóng gói để chạy local nhưng đọc certificate được mount ở production.

Cấu hình cơ sở:

~~~yaml
app:
  remote:
    base-uri: "http://localhost:8081/api"
    bind-address: "127.0.0.1"
    trust-bundle: "classpath:tls/dev-trust.pem"
~~~

Document được kích hoạt bởi profile production:

~~~yaml
---
spring:
  config:
    activate:
      on-profile: prod

app:
  remote:
    base-uri: "https://api.production.example/v1"
    bind-address: "0.0.0.0"
    trust-bundle: "file:/etc/app/tls/production-trust.pem"
~~~

Chạy local:

~~~bash
java -jar app.jar
~~~

Chạy production:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Khi Boot nạp các document theo điều kiện và priority tương ứng, những field cùng tên được bind sang `URI`, `InetAddress` và `Resource` từ giá trị hiệu lực.

Điều quan trọng: `file:/etc/app/tls/production-trust.pem` không tự sinh ra file. Hạ tầng phải mount đúng location và cấp quyền đọc. Việc ứng dụng dùng profile `prod` không thay thế kiểm soát bảo mật hạ tầng.

### 22.1. Địa chỉ bind khác địa chỉ truy cập

Trong container, `bind-address=0.0.0.0` có thể làm server lắng nghe trên mọi IPv4 interface phù hợp. Nhưng client không thể dùng `0.0.0.0` như một service endpoint có ý nghĩa định tuyến bình thường. Cấu hình lắng nghe và cấu hình endpoint để gọi service khác phải được tách rõ.

### 22.2. File certificate có thể đến từ Secret

Một mounted Secret có thể được ánh xạ thành file, sau đó `Resource` trỏ tới path tương ứng. Tuy nhiên, việc bảo vệ secret vẫn phụ thuộc permission, RBAC, lifecycle, volume và policies. Không in nội dung certificate/private key ra log khi debug.

## 23. Bảng lỗi và cách khắc phục nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| URI bind lỗi | Ký tự sai cú pháp hoặc encoding | Kiểm tra scheme, path, percent encoding |
| URI bind thành công nhưng không gửi được HTTP | URI tương đối hoặc scheme không hỗ trợ | Kiểm tra absolute HTTP(S), host và client |
| URL bind lỗi | Thiếu protocol hoặc protocol không được hỗ trợ | Dùng URL đầy đủ hoặc chuyển sang URI/Resource phù hợp |
| URL có giá trị nhưng request lỗi | DNS, TLS, proxy, timeout | Phân biệt parsing với network access |
| InetAddress gây lỗi startup | Hostname không resolve | Kiểm tra DNS/hosts hoặc dùng String để resolve muộn |
| InetAddress không chứa port | Đã nhập host:port vào một field | Tách host và port |
| IPv6 không hoạt động trong URI | Thiếu dấu `[ ]` quanh host | Dùng `http://[::1]:8080` |
| Resource đọc lỗi | File không tồn tại, đường dẫn sai, thiếu quyền | Kiểm tra classpath/file mount, gọi stream an toàn |
| Resource.getFile() lỗi trong JAR | Asset nằm trong archive | Dùng getInputStream() |
| Giá trị khác file đang đọc | Bị nguồn có ưu tiên cao hơn ghi đè | Xem profile, env vars, command line |
| Cấu hình thay đổi nhưng bean giữ giá trị cũ | Binding đã diễn ra lúc startup | Restart hoặc cơ chế refresh riêng |
| @NotBlank trên URI báo lỗi validation | Constraint dùng sai kiểu | Dùng @NotNull/custom validator |

## 24. Checklist áp dụng trong dự án

- Xác định ngữ nghĩa property trước khi chọn `URI`, `URL`, `InetAddress`, `Resource` hay `String`.
- Khai báo các type trong `@ConfigurationProperties` và đăng ký bean đúng cách.
- Viết tên key canonical kebab-case, ví dụ `base-uri`, `bind-address` và `trust-bundle`.
- Với endpoint HTTP, ưu tiên `URI` và kiểm tra scheme/host/absolute theo yêu cầu.
- Chỉ chọn `URL` khi API hoặc thiết kế thực sự cần kiểu này; không đồng nhất URL parse với network readiness.
- Với `InetAddress`, cân nhắc DNS lookup trong lúc binding; dùng `String` nếu cần giữ hostname chưa phân giải.
- Không đưa host và port vào cùng field `InetAddress`.
- Với IPv6, phân biệt literal IP và cú pháp IPv6 host trong URI.
- Với tài nguyên trong JAR, dùng `classpath:` và đọc qua `Resource.getInputStream()`.
- Với file mount ngoài JAR, dùng `file:` và bảo đảm working directory hoặc absolute path phù hợp.
- Không giả định Resource được bind nghĩa là tệp tồn tại hoặc đọc được.
- Không dùng `Resource.getFile()` cho mọi classpath resource.
- Tách parsing, validation, file/network access thành các bước có trách nhiệm rõ ràng.
- Kiểm tra Config Data precedence nếu giá trị hiệu lực khác cấu hình gốc.
- Tránh log secret hoặc tải URL tùy ý từ nguồn không tin cậy.
- Test conversion với URI và IP literal ổn định, test Resource qua classpath sample hoặc file test.
- Thiết kế restart/reload cho các thay đổi Config Data sau startup.

## 25. Kết luận

Spring Boot có thể chuyển các chuỗi trong **externalized configuration** thành kiểu Java có ý nghĩa, giúp giảm parsing thủ công và phát hiện nhiều lỗi sớm. Bốn kiểu ở bài này giải quyết các mục đích khác nhau:

- `URI` biểu diễn một định danh tài nguyên, thường là lựa chọn thuận tiện cho endpoint HTTP.
- `URL` phục vụ những API cần locator với protocol tương ứng.
- `InetAddress` biểu diễn địa chỉ IP và có thể kéo theo DNS lookup khi nhập hostname.
- `Resource` là abstraction của Spring để truy cập nội dung từ classpath, filesystem hoặc nguồn được hỗ trợ.

Dù Binder tạo thành công object, ứng dụng vẫn cần **validation theo nghiệp vụ**, xử lý lỗi I/O/network, phân quyền và các quy tắc vận hành phù hợp. Đặc biệt, không nhầm parsing URI/URL với kết nối mạng, không nhầm `Resource` với một `File` vật lý, và không nhầm địa chỉ IP với một endpoint đầy đủ có scheme/port/path.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration và Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Framework API — Resource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html)
- [Java API — URI](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html)
- [Java API — URL](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URL.html)
- [Java API — InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html)
