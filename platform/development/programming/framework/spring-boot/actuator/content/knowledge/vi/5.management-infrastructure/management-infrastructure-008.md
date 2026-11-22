# Xử lý URL, cổng và thông tin proxy trong môi trường container

## 1. Một yêu cầu có thể đi qua nhiều địa chỉ khác nhau

Giả sử người dùng gọi:

```text
https://ops.example.com/ops/actuator/health
```

Máy chủ trung gian (reverse proxy) có thể kết thúc TLS, bỏ tiền tố `/ops`, rồi chuyển yêu cầu qua HTTP tới container ứng dụng:

```text
Người gọi
  -> https://ops.example.com:443/ops/actuator/health
  -> proxy
  -> http://app:9091/actuator/health
```

Đây là mô hình phân tích, chưa phải cấu hình triển khai HTTPS đầy đủ. Các thành phần của hai URL khác nhau vì chúng thuộc hai chặng:

| Thành phần | Người gọi nhìn thấy | Ứng dụng nhận ở chặng nội bộ |
| --- | --- | --- |
| Giao thức | HTTPS | HTTP |
| Tên máy chủ | `ops.example.com` | `app`, tên dịch vụ nội bộ |
| Cổng | 443 | 9091 |
| Đường dẫn | `/ops/actuator/health` | `/actuator/health` |

Bài này dùng **Spring Boot 3.3.x**, đối chiếu 3.3.13. Cần giải quyết hai việc: đưa yêu cầu tới đúng endpoint, và giúp ứng dụng hiểu địa chỉ phía người gọi để sinh liên kết hoặc chuyển hướng phù hợp. Spring Boot có cơ chế xử lý thông tin proxy cho nhu cầu thứ hai. [Chạy Spring Boot sau máy chủ trung gian](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server).

## 2. Phân biệt cổng container, cổng host và cổng công khai

### Cổng ứng dụng bên trong container

Nếu ứng dụng lắng nghe cổng nghiệp vụ 8080 và quản trị 9091, proxy nằm trong cùng mạng Compose sẽ gọi `app:9091` cho Actuator.

Không đổi `management.server.port` sang 443 chỉ vì URL bên ngoài dùng HTTPS cổng 443. Thuộc tính này chọn cổng mà máy chủ quản trị thực sự lắng nghe trong môi trường của tiến trình Java.

### Cổng được công bố trên host

Ví dụ một ánh xạ Docker:

```text
127.0.0.1:19091:9091
```

Ý nghĩa: cổng 19091 trên loopback của host được chuyển tới cổng 9091 trong container. Cấu hình đó không đổi listener bên trong JVM thành 19091.

Trong mạng Compose, container khác vẫn dùng **tên dịch vụ và cổng container**. Máy host dùng cổng được công bố. Không dùng cổng host như thể đó là cổng nội bộ của dịch vụ. [Mạng Compose và khác biệt HOST_PORT/CONTAINER_PORT](https://docs.docker.com/compose/how-tos/networking/).

### Địa chỉ lắng nghe và localhost

Trong mô hình container mạng bridge riêng:

- `localhost` bên trong container proxy là chính container proxy.
- `localhost` trên máy host là máy host.
- Tên dịch vụ `app` được Compose cung cấp cho các container cùng mạng; nó không tự trở thành tên miền của máy người dùng.
- Nếu quản trị chỉ gắn vào `127.0.0.1` bên trong container ứng dụng, proxy ở container khác không kết nối tới listener đó qua giao diện mạng container được.

Bài thực hành sẽ để máy chủ quản trị gắn `0.0.0.0:9091` **bên trong container**, nhưng chỉ công bố cổng proxy trên loopback host. Vẫn cần kiểm soát những thành phần được tham gia mạng nội bộ; việc không công bố một cổng lên host không đồng nghĩa mọi container khác đều bị chặn.

`EXPOSE` trong Dockerfile chỉ mô tả cổng dự kiến của ảnh. Nó không tự khởi động listener, công bố cổng lên host hoặc tạo cơ chế phân quyền. [Ý nghĩa Dockerfile EXPOSE](https://docs.docker.com/reference/dockerfile/#expose).

## 3. Thông tin proxy giúp khôi phục điều gì?

Khi có thay đổi giao thức, tên máy chủ, cổng hoặc tiền tố đường dẫn, proxy có thể gửi thông tin gốc qua các HTTP header.

| Header | Thông tin thường được diễn đạt |
| --- | --- |
| `Forwarded` | Chuẩn chứa các tham số như `for`, `proto`, `host` |
| `X-Forwarded-Proto` | Giao thức phía người gọi, ví dụ `https` |
| `X-Forwarded-Host` | Tên máy chủ công khai |
| `X-Forwarded-Port` | Cổng phía người gọi |
| `X-Forwarded-Prefix` | Tiền tố phía ngoài đã bị proxy bỏ hoặc cần phản ánh khi sinh URL |
| `X-Forwarded-For` | Thông tin địa chỉ khách theo chính sách chuỗi proxy |

Các header `X-Forwarded-*` là quy ước phổ biến, không phải mọi phần đều thuộc chuẩn `Forwarded`. Với Servlet, `ForwardedHeaderFilter` có thể điều chỉnh cách ứng dụng nhìn giao thức, tên máy chủ, cổng và các yêu cầu chuyển hướng. [API ForwardedHeaderFilter trong Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html).

### Không nhầm khôi phục thông tin với viết lại đường dẫn

Trong ví dụ đầu bài:

```text
Proxy nhận:             /ops/actuator/health
Proxy gửi tới ứng dụng: /actuator/health
Tiền tố cần phản ánh:   /ops
```

Proxy phải thực sự thực hiện quy tắc chuyển đường dẫn. `X-Forwarded-Prefix: /ops` không tự thay thế mọi quy tắc định tuyến của proxy.

Ở phía Spring, việc xử lý tiền tố giúp URL nhìn từ người gọi có thể là `/ops/actuator/health` dù URI nội bộ đã bỏ `/ops`. Cơ chế Servlet xử lý tiền tố được thể hiện trong [mã ForwardedHeaderFilter 6.1.21](https://github.com/spring-projects/spring-framework/blob/v6.1.21/spring-web/src/main/java/org/springframework/web/filter/ForwardedHeaderFilter.java).

Đừng đồng thời đưa `/ops` vào mọi lớp một cách máy móc. Nếu proxy đã giữ nguyên tiền tố, ứng dụng lại có context path tương ứng và header tiếp tục khai báo một tiền tố khác, URL có thể bị thiếu hoặc lặp đoạn. Trước hết phải ghi rõ URI đi vào từng chặng.

## 4. Chọn cách Spring Boot xử lý forwarded headers

Thuộc tính chính:

```properties
server.forward-headers-strategy=framework
```

| Giá trị | Cách xử lý do Boot lựa chọn |
| --- | --- |
| `NONE` | Không tự áp dụng cơ chế forwarded headers này |
| `NATIVE` | Dựa vào hỗ trợ của máy chủ web nhúng |
| `FRAMEWORK` | Dùng hỗ trợ của Spring Framework |

Với `FRAMEWORK`, Servlet dùng cơ chế `ForwardedHeaderFilter`; Reactive dùng `ForwardedHeaderTransformer`. Khả năng và cấu hình của `NATIVE` phụ thuộc máy chủ, không mặc định rằng mọi header tiền tố đều được xử lý giống `FRAMEWORK`.

Bài thực hành chọn `framework` để minh họa tiền tố đường dẫn. Không đăng ký thêm một filter tự viết chỉ để lặp lại đúng chức năng Boot đã cấu hình. Tài liệu 3.3 cũng nêu mặc định có thể là `NATIVE` trên nền tảng cloud được hỗ trợ và `NONE` ở trường hợp khác; chỉ chạy trong container không đủ để kết luận ứng dụng đã xử lý forwarded headers. [Các chiến lược forwarded headers của Boot 3.3](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server).

### Ranh giới tin cậy là một phần của cấu hình

Ứng dụng không tự biết một header đến từ proxy thật hay do người gọi tự gửi. Ở ranh giới đi vào hệ thống:

1. Proxy bỏ các forwarded header không đáng tin từ phía ngoài.
2. Proxy tạo lại giá trị từ thông tin mà nó được phép tin.
3. Đường nội bộ tới ứng dụng được giới hạn theo kiến trúc mạng đã chọn.

Với một proxy biên duy nhất, không nối chuỗi `X-Forwarded-For` do người gọi tự cung cấp một cách mù quáng. Với nhiều proxy, cần xác định rõ chặng nào được tin và ai chịu trách nhiệm chuẩn hóa chuỗi. Quy tắc tin proxy của Tomcat native cũng không tự trở thành bộ lọc IP cho chiến lược Framework. [Lưu ý tin cậy của ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html).

## 5. Bài thử cục bộ: proxy và ứng dụng trong hai container

Mục tiêu là kiểm tra **đường dẫn và liên kết Actuator**, nên bài thử dùng HTTP cục bộ. Phần HTTPS phía ngoài sẽ được phân tích riêng ở mục 7.

Chuẩn bị một thư mục lab mới với một JAR Spring Boot 3.3.x chạy được, đặt tên `app.jar`. JAR cần có lớp khởi động, `spring-boot-starter-web` và `spring-boot-starter-actuator`; bài thử giả định không có Spring Security, filter tùy chỉnh hoặc cấu hình tự viết làm thay đổi ví dụ. Dùng Docker Engine/Desktop hỗ trợ Linux containers và Compose.

Các tệp cần có:

```text
proxy-lab/
  app.jar
  Dockerfile
  application.yml
  compose.yml
  nginx.conf
```

Đây là tài liệu để người học tạo lab riêng; cấu hình không đòi hỏi sửa mã controller nghiệp vụ.

### 5.1. application.yml

```yaml
server:
  port: 9091
  address: 0.0.0.0
  forward-headers-strategy: framework
  ssl:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      base-path: /actuator
      discovery:
        enabled: true
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

Trong lab, ứng dụng và Actuator dùng chung listener 9091; không đặt `management.server.port`. Cấu hình chọn cổng và đường dẫn nội bộ, không lấy cổng host 8088 hoặc tiền tố ngoài `/ops` làm cấu hình listener/base path.

Cấu hình `framework` tham gia cơ chế đăng ký filter của Boot trên máy chủ Servlet dùng trong lab. Nếu dự án thực tách cổng quản trị hoặc thay thế filter/cấu hình máy chủ, hãy kiểm tra liên kết tại chính cổng quản trị; không lấy kết quả trên cổng nghiệp vụ làm bằng chứng cho cổng khác. [Đăng ký filter forwarded của Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/web/servlet/ServletWebServerFactoryAutoConfiguration.java).

### 5.2. Dockerfile

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar
COPY application.yml /app/application.yml
EXPOSE 9091
ENTRYPOINT ["java", "-jar", "/app/app.jar", "--spring.config.location=file:/app/application.yml"]
```

JRE 21 chạy JAR đã được build trước đó; Dockerfile này không biên dịch mã nguồn. Dùng ảnh Java được cung cấp trong [Eclipse Temurin Official Image](https://hub.docker.com/_/eclipse-temurin).

### 5.3. compose.yml

```yaml
services:
  app:
    build: .

  proxy:
    image: nginx:stable-alpine
    depends_on:
      - app
    ports:
      - "127.0.0.1:8088:80"
    volumes:
      - "./nginx.conf:/etc/nginx/conf.d/default.conf:ro"
```

Proxy và app cùng mạng Compose mặc định; proxy gọi `app:9091`. Ứng dụng không có `ports` công bố trực tiếp 9091 lên host trong lab này. Cổng 8088 của host ánh xạ vào cổng 80 của container proxy.

Thẻ ảnh Nginx trong lab lấy từ [Nginx Official Image](https://hub.docker.com/_/nginx). Với môi trường cần tái lập chính xác, quản lý phiên bản/digest theo quy trình của dự án.

### 5.4. nginx.conf

```nginx
server {
    listen 80;
    server_name localhost;

    location /ops/ {
        proxy_pass http://app:9091/;

        proxy_set_header Host localhost:8088;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host localhost;
        proxy_set_header X-Forwarded-Port 8088;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Forwarded-Prefix /ops;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Ssl "";
    }

    location / {
        return 404;
    }
}
```

Các giá trị `localhost`, 8088 và `http` là địa chỉ công khai **của lab cục bộ**, được đặt tường minh. Không sao chép chúng nguyên vẹn sang một miền HTTPS thực tế.

Đọc hai phần độc lập:

- `location /ops/` kết hợp `proxy_pass http://app:9091/;` thay phần `/ops/` bằng `/` trước khi chuyển tiếp. Vì vậy `/ops/actuator/health` đi vào app thành `/actuator/health`.
- Các header tạo lại thông tin phía ngoài. `Forwarded` và `X-Forwarded-Ssl` đầu vào được bỏ; những header được dùng còn lại được ghi lại theo chính sách một proxy của lab.

Dấu `/` sau cổng trong `proxy_pass` có vai trò trong quy tắc thay URI. Không bỏ/thêm nó mà không tính lại đường dẫn. Nginx cũng quy định header có giá trị rỗng sẽ không được chuyển tiếp. [Quy tắc proxy_pass và proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

Cổng được khai báo trong header là **8088**, không phải 80 mà Nginx đang lắng nghe trong container. Đây chính là khác biệt giữa cổng phía người gọi và cổng của một chặng nội bộ.

## 6. Kiểm tra cả dữ liệu và liên kết sinh ra

### Khởi động lab

Trong PowerShell, tại thư mục lab:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs app
docker compose exec proxy nginx -t
```

Chờ ứng dụng đã khởi động thành công rồi gọi HTTP. `depends_on` ở dạng danh sách chỉ tổ chức thứ tự khởi động, không bảo đảm Spring Boot đã sẵn sàng nhận kết nối khi proxy vừa chạy. [Thứ tự khởi động và trạng thái sẵn sàng trong Compose](https://docs.docker.com/compose/how-tos/startup-order/).

### 6.1. Kiểm tra health qua proxy

```powershell
curl.exe --silent --show-error --max-time 5 --output NUL --write-out "%{http_code}\n" "http://localhost:8088/ops/actuator/health"
```

Khi ứng dụng khỏe và các giả định của lab được thỏa, stdout dự kiến:

```text
200
```

Mã này cho thấy yêu cầu tới được endpoint. Nó chưa chứng minh mọi URL mà ứng dụng sinh ra đều đúng.

### 6.2. Đọc liên kết từ trang khám phá

```powershell
$document = curl.exe --silent --show-error --max-time 5 "http://localhost:8088/ops/actuator" | ConvertFrom-Json
$document._links.health.href
```

Kết quả dự kiến là một dòng:

```text
http://localhost:8088/ops/actuator/health
```

Kiểm tra đủ bốn thành phần: `http`, `localhost`, `8088`, `/ops/actuator/health`. Không chấp nhận chỉ vì URL kết thúc bằng chữ `health`.

Actuator tạo liên kết từ URL yêu cầu của trang khám phá, nên xử lý đúng thông tin yêu cầu giúp tránh trả liên kết chứa tên container, cổng nội bộ hoặc thiếu tiền tố. Đây là suy luận áp dụng từ [mã EndpointLinksResolver của Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java).

Nếu đổi `server.forward-headers-strategy` sang `none` trong ứng dụng không có cơ chế khác xử lý forwarded headers, health vẫn có thể trả 200 do proxy đã định tuyến đúng, nhưng liên kết có thể thiếu `/ops`. Thử lại sau khi build/khởi động lại cấu hình để thấy hai nhiệm vụ độc lập.

### 6.3. Kiểm tra proxy không giữ header giả từ phía ngoài

Gửi các giá trị thử qua **cổng proxy của chính lab**:

```powershell
$document = curl.exe --silent --show-error --max-time 5 -H "Forwarded: proto=https;host=untrusted.invalid" -H "X-Forwarded-Host: untrusted.invalid" "http://localhost:8088/ops/actuator" | ConvertFrom-Json
$document._links.health.href
```

Liên kết dự kiến vẫn là:

```text
http://localhost:8088/ops/actuator/health
```

Kết quả này kiểm tra hai header đã gửi trong tình huống lab, không thay thế việc kiểm tra toàn bộ ranh giới tin cậy, chuỗi proxy hoặc các đường kết nối có thể đi vòng proxy.

Các kết quả trong mục 6 là dự kiến có điều kiện, không phải tuyên bố đã chạy trên mọi cấu hình Docker/Spring Boot. Khi kết thúc lab riêng:

```powershell
docker compose down
```

## 7. Đưa mô hình sang HTTPS hoặc hạ tầng nhiều lớp

Giả sử proxy thật trực tiếp kết thúc TLS tại `https://ops.example.com` cổng 443, còn app nhận HTTP cổng 9091. Thông tin đáng tin được chuyển tới app cần phản ánh phía ngoài:

| Thông tin | Giá trị trong mô hình HTTPS |
| --- | --- |
| Giao thức gốc | `https` |
| Máy chủ gốc | `ops.example.com` |
| Cổng gốc | `443` |
| Tiền tố ngoài | `/ops` |
| URI chuyển tới app | `/actuator/health` |
| URL health phía ngoài | `https://ops.example.com/ops/actuator/health` |

Không đặt `X-Forwarded-Proto=https` chỉ để liên kết “trông có vẻ an toàn” khi người gọi thực tế dùng HTTP. Header mô tả một chặng đã diễn ra; nó không mã hóa kết nối proxy → app.

Nếu Nginx lại nằm sau một bộ cân bằng tải đã kết thúc TLS, `$scheme` tại Nginx có thể chỉ là `http`. Cần xác định proxy nào sở hữu thông tin gốc đáng tin, kiểm soát nguồn kết nối và chuẩn hóa header tại đúng ranh giới. Không lấy nguyên header do khách tự gửi để suy ra trạng thái an toàn.

Với cổng quản trị riêng, cũng xác định rõ `management.server.base-path`, `management.endpoints.web.base-path` và các ánh xạ endpoint thực tế. Các thuộc tính đó chọn đường dẫn ứng dụng phục vụ; forwarded prefix mô tả tiền tố phía ngoài, không phải một giá trị thay thế chung cho mọi loại đường dẫn. [Quan hệ đường dẫn và cổng quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 8. Tìm lỗi theo chặng thay vì sửa URL ngẫu nhiên

| Hiện tượng | Chặng cần kiểm tra |
| --- | --- |
| Không kết nối được tới `localhost:8088` | Cổng host, container proxy và việc công bố cổng |
| Proxy trả 502 | Tên dịch vụ, cổng nội bộ, địa chỉ app lắng nghe, app đã sẵn sàng chưa |
| Proxy tới được app nhưng nhận 404 | Quy tắc bỏ/giữ tiền tố và đường dẫn endpoint nội bộ |
| Health 200 nhưng liên kết chứa `app:9091` | Host/cổng gốc và cơ chế xử lý forwarded headers |
| Liên kết thiếu `/ops` | Header tiền tố, chiến lược xử lý và quy tắc rewrite có khớp không |
| Liên kết lặp tiền tố | Có lớp nào cộng tiền tố hai lần không |
| URL sinh ra dùng HTTP trong khi phía ngoài thật là HTTPS | Nơi kết thúc TLS và nguồn thông tin giao thức gốc |
| URL bị đổi theo header giả của khách | Ranh giới tin cậy và các đường gọi trực tiếp tới app |
| Có 401/403 | Xác thực, phân quyền hoặc bộ lọc; không chỉ cổng/rewrite |

Khi ghi chẩn đoán, lập bảng cho từng chặng gồm **giao thức, host, cổng, URI, header đã chuẩn hóa**. Kiểm tra cả `Location` khi có chuyển hướng và các liên kết JSON mà Actuator thực sự trả.

Nếu container app bị tạo lại, tên dịch vụ vẫn là mục tiêu cấu hình nhưng địa chỉ IP có thể đổi. Proxy hoặc kết nối lâu dài cần cơ chế phân giải/kết nối lại phù hợp với cách triển khai; trong lab, có thể cần khởi động lại proxy sau khi tái tạo app. Không ghi cứng IP container để che vấn đề đó. [Cập nhật container trong mạng Compose](https://docs.docker.com/compose/how-tos/networking/).

## 9. Tự kiểm tra mô hình

**Tình huống 1:** Host công bố `19091:9091`. Proxy cùng mạng Compose phải gọi `app:19091` hay `app:9091`?

Dùng `app:9091`: kết nối giữa các dịch vụ sử dụng cổng container.

**Tình huống 2:** `GET /ops/actuator/health` trả 200, nhưng liên kết trong trang khám phá thiếu `/ops`. Có thể kết luận proxy đã sai hoàn toàn không?

Chưa. Việc chuyển yêu cầu có thể đúng, còn thông tin dùng sinh URL chưa được khôi phục đúng.

**Tình huống 3:** Chỉ thêm `X-Forwarded-Prefix: /ops` nhưng proxy vẫn gửi URI mà ứng dụng không phục vụ.

Cần sửa quy tắc định tuyến/viết lại URI theo hợp đồng từng chặng. Header không tự tạo endpoint hoặc thay mọi quy tắc của proxy.

**Tình huống 4:** Ứng dụng bật `FRAMEWORK`, nhưng bất kỳ khách nào cũng gọi trực tiếp tới cổng app và tự gửi forwarded headers.

Cần kiểm soát đường kết nối và ranh giới chuẩn hóa header. Chọn chiến lược xử lý không tự xác thực danh tính proxy.

**Tình huống 5:** URL ngoài là HTTPS 443, app nội bộ là HTTP 9091. Có cần đổi `management.server.port` thành 443 không?

Không. Giữ cổng listener nội bộ theo thiết kế; chuyển đúng lưu lượng và thông tin phía ngoài qua proxy đáng tin.
