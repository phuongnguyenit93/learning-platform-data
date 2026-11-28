# Cấu hình cổng, context path và tiền tố đường dẫn máy chủ

Spring Cloud Config Server cung cấp cấu hình qua HTTP. Để Config Client truy cập được máy chủ, nhóm phải thống nhất địa chỉ mạng, cổng lắng nghe và đường dẫn API. Ba phần này thường bị nhầm lẫn: cổng xác định kết nối đến tiến trình, context path xác định gốc của ứng dụng web, còn tiền tố Config Server thay đổi vị trí các endpoint cấu hình.

Ví dụ, Config Server có thể lắng nghe tại cổng `8888`, phục vụ API dưới tiền tố `/config`, và được truy cập qua địa chỉ `https://config.example.com/config`. Nếu client gọi thiếu tiền tố hoặc proxy chuyển tiếp sai đường dẫn, ứng dụng có thể gặp `404 Not Found` dù tiến trình Config Server vẫn đang chạy bình thường.

## 1. Phân biệt cổng, context path và tiền tố Config Server

| Thành phần | Thuộc tính | Tác dụng | Ví dụ |
|---|---|---|---|
| Cổng HTTP | `server.port` | Cổng mà web server của Spring Boot lắng nghe | `8888` |
| Context path của servlet | `server.servlet.context-path` | Tiền tố gốc áp dụng cho các endpoint trong ứng dụng servlet | `/platform` |
| Tiền tố API Config Server | `spring.cloud.config.server.prefix` | Tiền tố được thêm vào các endpoint cấu hình của Config Server | `/config` |
| Tiền tố công khai của proxy | Cấu hình ở reverse proxy/API gateway | Đường dẫn mà client nhìn thấy từ bên ngoài | `/central-config` |

Các giá trị trên có thể phối hợp, nhưng mỗi lớp có phạm vi khác nhau. `server.port` không thêm đoạn nào vào URL. `server.servlet.context-path` áp dụng cho ứng dụng web servlet, bao gồm các endpoint web khác cùng chạy trong ứng dụng. `spring.cloud.config.server.prefix` chỉ thay đổi các request mapping của Config Server và nằm bên dưới servlet path/context path của Spring Boot. Tiền tố do proxy quản lý phụ thuộc proxy giữ nguyên hay loại bỏ đoạn đường dẫn trước khi chuyển tiếp request.

Với Config Server chạy độc lập theo mô hình servlet thông thường, hãy bắt đầu bằng cách xác định ba thông tin: cổng nội bộ, đường dẫn API mà ứng dụng cần gọi và đường dẫn công khai nếu có reverse proxy.

## 2. Cấu hình cổng lắng nghe bằng `server.port`

Config Server là một ứng dụng Spring Boot. Nếu không cấu hình cổng riêng, Spring Boot dùng cổng mặc định `8080`. Nhiều ví dụ triển khai Config Server chọn `8888` để dễ nhận diện, nhưng đây là lựa chọn cấu hình chứ không phải yêu cầu bắt buộc của Config Server.

Có thể khai báo cổng trong `application.yml`:

```yaml
server:
  port: 8888
```

Trong môi trường triển khai, nên cho phép ghi đè bằng biến môi trường:

```yaml
server:
  port: ${CONFIG_SERVER_PORT:8888}
```

Nếu biến `CONFIG_SERVER_PORT` được cấp, Spring Boot dùng giá trị đó; nếu không, ứng dụng dùng `8888`. Cách này giúp một artifact có thể chạy ở các môi trường có quy ước cổng khác nhau mà không cần sửa mã nguồn.

Ví dụ khởi chạy trên một cổng khác:

```bash
java -jar config-server.jar --server.port=9090
```

Tham số dòng lệnh là một nguồn cấu hình của Spring Boot và có thể ghi đè giá trị trong file cấu hình. Khi điều tra cổng thực tế, hãy kiểm tra cả file, biến môi trường, tham số JVM và tham số dòng lệnh được dùng khi tiến trình khởi động.

### Cổng trong container và Kubernetes

Trong container, `server.port` là cổng bên trong container mà ứng dụng thực sự bind. Docker publish port ánh xạ cổng trên máy host vào cổng container. Ví dụ:

```bash
docker run --rm -p 8888:8888 \
  -e CONFIG_SERVER_PORT=8888 \
  config-server:1.0.0
```

Trong ví dụ này, `8888` bên trái là cổng host, `8888` bên phải là cổng container. Hai số có thể khác nhau nếu ánh xạ phù hợp, nhưng cổng bên phải phải khớp với cổng ứng dụng đang lắng nghe.

Với Kubernetes, Service thường nhận traffic ở `port` và chuyển đến `targetPort` của Pod:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: config-server
spec:
  selector:
    app: config-server
  ports:
    - name: http
      port: 8888
      targetPort: 8888
```

`targetPort` phải trỏ đến cổng mà tiến trình trong container sử dụng. Nếu ứng dụng chạy ở `9090` nhưng Service vẫn chuyển đến `8888`, kết nối sẽ thất bại dù Service đã có địa chỉ. Cần đồng bộ `server.port`, cổng container, `targetPort`, health probe và cấu hình firewall/network policy.

## 3. Đặt context path cho toàn bộ ứng dụng servlet

`server.servlet.context-path` thay đổi đường dẫn gốc của ứng dụng web servlet. Ví dụ:

```yaml
server:
  port: 8888
  servlet:
    context-path: /platform
```

Khi đó, endpoint cấu hình của Config Server nằm bên dưới `/platform`. Nếu tiền tố riêng của Config Server chưa được đặt, request lấy cấu hình sẽ có dạng:

```text
http://localhost:8888/platform/order-service/prod/main
```

Context path áp dụng cho các endpoint servlet trong ứng dụng. Ví dụ, nếu Actuator dùng base path mặc định `/actuator` và chạy cùng web server, đường dẫn health thường cũng nằm dưới context path:

```text
http://localhost:8888/platform/actuator/health
```

Đây là khác biệt quan trọng so với tiền tố riêng của Config Server. Khi chỉ thay đổi tiền tố API Config Server, không nên giả định endpoint Actuator cũng tự động chuyển sang tiền tố đó.

Context path thường hữu ích khi ứng dụng được triển khai dưới một nhánh URL chung cùng các ứng dụng web khác. Nếu chỉ cần đặt Config Server API dưới `/config`, tiền tố riêng của Config Server thường thể hiện ý định rõ hơn và không làm thay đổi đường dẫn của các endpoint web khác.

## 4. Đặt tiền tố API bằng `spring.cloud.config.server.prefix`

Spring Cloud Config hỗ trợ thuộc tính `spring.cloud.config.server.prefix` để phục vụ các endpoint cấu hình dưới một tiền tố. Tiền tố phải bắt đầu bằng dấu `/` và không kết thúc bằng dấu `/`.

Ví dụ:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        prefix: /config
        git:
          uri: https://git.example.com/platform/config-repository.git
          default-label: main
```

Với cấu hình này, endpoint lấy cấu hình cho `order-service`, profile `prod`, label `main` là:

```text
http://localhost:8888/config/order-service/prod/main
```

Nếu không khai báo `spring.cloud.config.server.prefix`, Config Server dùng đường dẫn endpoint mặc định:

```text
http://localhost:8888/order-service/prod/main
```

Tiền tố này được áp dụng vào các request mapping của Config Server bên dưới servlet path và context path của Spring Boot. Vì vậy, nếu đồng thời đặt:

```yaml
server:
  servlet:
    context-path: /platform

spring:
  cloud:
    config:
      server:
        prefix: /config
```

đường dẫn API sẽ chứa cả hai phần:

```text
http://localhost:8888/platform/config/order-service/prod/main
```

Chỉ kết hợp hai thuộc tính khi thật sự cần hai lớp đường dẫn riêng. Nếu chỉ cần một tiền tố cho API cấu hình, dùng `spring.cloud.config.server.prefix` thường đơn giản hơn. Nếu cần toàn bộ ứng dụng servlet nằm dưới một context path, dùng `server.servlet.context-path`.

## 5. Cập nhật địa chỉ ở Config Client

Config Client phải gọi đúng base URL, bao gồm scheme, host, cổng và mọi context path hoặc tiền tố API đã cấu hình ở server.

Ví dụ Config Server dùng cổng `8888` và tiền tố `/config`:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888/config"
```

Trong ví dụ này, `config-server` là hostname có thể phân giải từ mạng của client, chẳng hạn tên Kubernetes Service. Config Client dùng base URL kết thúc ở `/config`; client tự xây dựng request theo tên ứng dụng, profile và label. Không thêm lặp lại `/order-service/prod/main` vào giá trị `spring.config.import`.

Nếu server dùng context path `/platform` và tiền tố Config Server `/config`, base URL của client phải bao gồm cả hai:

```yaml
spring:
  config:
    import: "configserver:http://config-server:8888/platform/config"
```

Nếu không có context path và không có tiền tố API riêng, base URL chỉ cần là origin của server:

```yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
```

Với ứng dụng dùng cơ chế bootstrap cũ, `spring.cloud.config.uri` cũng cần trỏ đến đúng base URL có context path/prefix. Không nên cấu hình hai cơ chế bootstrap khác nhau cùng lúc nếu chưa xác định rõ thứ tự và hành vi mong muốn. Với Spring Boot hiện đại, `spring.config.import` là cách khai báo Config Data được khuyến nghị.

## 6. Kết hợp reverse proxy hoặc API gateway

Trong production, Config Server thường được đặt sau reverse proxy, ingress hoặc API gateway. Proxy có thể cung cấp TLS, xác thực, giới hạn truy cập, ghi log và tên miền ổn định. Khi có tiền tố URL công khai, cần thống nhất proxy giữ nguyên hay loại bỏ tiền tố trước khi gửi request đến ứng dụng.

Có hai cách tổ chức phổ biến:

| Cách tổ chức | Đường dẫn client gọi | Đường dẫn proxy gửi đến Config Server |
|---|---|---|
| Proxy loại bỏ tiền tố `/central-config` | `/central-config/order-service/prod/main` | `/order-service/prod/main` |
| Proxy giữ nguyên tiền tố và Config Server khai báo prefix `/central-config` | `/central-config/order-service/prod/main` | `/central-config/order-service/prod/main` |

Ở cách thứ nhất, Config Server không cần biết tiền tố công khai. Proxy nhận `/central-config/...`, loại bỏ `/central-config` và chuyển tiếp phần còn lại đến server chạy ở root path. Ở cách thứ hai, proxy giữ nguyên đường dẫn và Config Server phải khai báo `spring.cloud.config.server.prefix: /central-config`.

Nếu dùng `server.servlet.context-path` thay cho tiền tố Config Server, proxy phải chuyển tiếp đường dẫn phù hợp với context path đó. Ví dụ context path `/platform` yêu cầu upstream nhận request bắt đầu bằng `/platform/...`. Kiểm tra cấu hình rewrite của proxy để tránh trường hợp proxy vừa giữ nguyên prefix vừa thêm prefix lần nữa.

### Minh họa hai luồng request

```text
Cách A: Proxy loại bỏ tiền tố

Config Client
  GET https://config.example.com/central-config/order-service/prod/main
       |
       v
Reverse Proxy (strip /central-config)
       |
       v
Config Server :8888
  GET /order-service/prod/main


Cách B: Config Server xử lý tiền tố

Config Client
  GET https://config.example.com/central-config/order-service/prod/main
       |
       v
Reverse Proxy (preserve path)
       |
       v
Config Server :8888, prefix=/central-config
  GET /central-config/order-service/prod/main
```

Không nhất thiết phải dùng cùng một tiền tố ở URL nội bộ và URL công khai. Điều cần bảo đảm là đường dẫn sau khi proxy xử lý khớp với request mapping mà Config Server thực sự cung cấp.

## 7. Kiểm tra endpoint và đường dẫn thực tế

Sau khi khởi động Config Server, hãy kiểm tra theo từng lớp thay vì chỉ dựa vào việc tiến trình đã chạy:

1. Kiểm tra log khởi động để xác nhận cổng bind thành công và không có lỗi cấu hình.
2. Kiểm tra health endpoint nếu Actuator đã được bật và bảo vệ phù hợp.
3. Gọi API cấu hình bằng đúng application, profile và label.
4. Gọi lại qua hostname, cổng và proxy mà Config Client sẽ dùng.
5. Khởi động một Config Client thử nghiệm để xác nhận `spring.config.import` nhận được cấu hình.

Ví dụ kiểm tra API Config Server dùng prefix `/config`:

```bash
curl -i http://localhost:8888/config/order-service/prod/main
```

Endpoint môi trường thường trả về biểu diễn JSON gồm tên ứng dụng, profile, label và các property source. Có thể kiểm tra endpoint YAML dành cho client hoặc công cụ cần định dạng YAML:

```bash
curl -i http://localhost:8888/config/order-service-prod.yml
```

Các request trên chỉ là ví dụ cho server không có context path bổ sung. Nếu có context path `/platform`, thêm `/platform` vào đầu đường dẫn; nếu proxy có prefix được giữ nguyên, dùng URL và đường dẫn upstream tương ứng với cấu hình proxy.

### Đọc mã lỗi để khoanh vùng

| Kết quả | Nguyên nhân có thể | Nơi cần kiểm tra |
|---|---|---|
| Connection refused hoặc timeout | Sai host/cổng, tiến trình chưa lắng nghe, Service không chuyển đúng targetPort, firewall hoặc network policy | `server.port`, container port, Service, ingress và mạng |
| `404 Not Found` | Thiếu hoặc lặp prefix, sai context path, sai application/profile/label hoặc file không tồn tại | URL đầy đủ, `server.servlet.context-path`, `spring.cloud.config.server.prefix`, proxy rewrite và tên file |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực HTTP | Security filter, credential ở Config Client và proxy |
| `403 Forbidden` | Danh tính đã được nhận diện nhưng không được phép truy cập | Quy tắc phân quyền Config Server/gateway |
| `5xx` | Lỗi nội bộ server hoặc backend repository | Log Config Server, Git URI, credential, kết nối mạng và trạng thái repository |
| Client khởi động nhưng không nhận giá trị mong đợi | Client gọi nhầm base URL, sai tên/profile/label hoặc property source có ưu tiên khác | `spring.config.import`, request thực tế và môi trường thuộc tính của client |

`404` không phải lúc nào cũng có nghĩa file cấu hình không tồn tại. Một prefix sai hoặc context path bị thiếu cũng tạo ra `404`. Hãy gọi trực tiếp server từ cùng mạng với client và so sánh request trước/sau proxy để tìm nơi đường dẫn thay đổi.

## 8. Actuator và các endpoint quản trị

Config Server thường cần endpoint health để load balancer hoặc nền tảng điều phối biết server có sẵn sàng nhận request hay không. Nếu dùng Spring Boot Actuator, có thể cấu hình base path:

```yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info
```

Chỉ expose các endpoint thật sự cần thiết. Endpoint quản trị có thể tiết lộ thông tin môi trường, tên property source hoặc dữ liệu nhạy cảm; cần dùng Spring Security, network policy hoặc cổng quản trị riêng để giới hạn truy cập. Nếu Actuator chạy cùng cổng với ứng dụng, context path servlet sẽ ảnh hưởng đến URL của Actuator. Tiền tố riêng `spring.cloud.config.server.prefix` chỉ dành cho các endpoint Config Server và không tự đổi base path Actuator.

Khi tách cổng quản trị bằng `management.server.port`, cần cập nhật health probe và quy tắc mạng cho cổng đó. Không mở cổng quản trị ra Internet chỉ để phục vụ health check nội bộ.

## 9. Quy ước triển khai để tránh sai đường dẫn

Nên ghi lại một địa chỉ chuẩn cho từng môi trường và dùng cùng giá trị đó trong cấu hình client, proxy, health check và tài liệu vận hành. Một bảng triển khai có thể gồm:

| Môi trường | Hostname client dùng | Cổng nội bộ | Context path | Config Server prefix | Base URL client |
|---|---|---:|---|---|---|
| Local | `localhost` | `8888` | *(rỗng)* | `/config` | `http://localhost:8888/config` |
| Docker network | `config-server` | `8888` | *(rỗng)* | `/config` | `http://config-server:8888/config` |
| Kubernetes nội bộ | `config-server` | `8888` | *(rỗng)* | `/config` | `http://config-server:8888/config` |
| Production qua proxy | `config.example.com` | `8888` upstream | *(rỗng)* | `/central-config` hoặc proxy strip prefix | `https://config.example.com/central-config` |

Các giá trị trong bảng là ví dụ. Cổng upstream và cổng công khai có thể khác nhau; hostname phải phân giải được từ mạng của Config Client. Nếu proxy loại bỏ prefix, cột Config Server prefix có thể để rỗng và proxy chịu trách nhiệm rewrite. Hãy ghi rõ lựa chọn này để người vận hành không thêm prefix lần thứ hai.

Trước khi đưa thay đổi đường dẫn vào production:

- Thay đổi cấu hình server và client trong cùng một kế hoạch triển khai.
- Kiểm tra đường dẫn từ mạng của client, không chỉ từ máy chạy Config Server.
- Kiểm tra tất cả instance sau khi rollout để tránh các replica dùng cấu hình path khác nhau.
- Cập nhật ingress, load balancer, health probe, service discovery và tài liệu hỗ trợ.
- Bảo đảm TLS và xác thực được áp dụng cho cả đường dẫn client và endpoint quản trị.
- Có kế hoạch rollback nếu client không thể lấy cấu hình sau khi đổi port hoặc prefix.

## 10. Nguyên tắc cần ghi nhớ

- `server.port` quyết định cổng web server Spring Boot lắng nghe; Config Server không bắt buộc phải dùng `8888`.
- `server.servlet.context-path` đặt gốc URL cho toàn bộ ứng dụng servlet.
- `spring.cloud.config.server.prefix` đặt tiền tố riêng cho các endpoint Config Server; tiền tố bắt đầu bằng `/` và không kết thúc bằng `/`.
- Client phải dùng base URL chứa đúng context path và prefix đang có hiệu lực.
- Reverse proxy cần có quy tắc rõ ràng về việc giữ nguyên hoặc loại bỏ tiền tố đường dẫn.
- Phân biệt cổng host, cổng container, `port` và `targetPort` khi triển khai Docker/Kubernetes.
- Kiểm tra endpoint cấu hình và health từ đúng mạng của client; phân tích `404`, `401`, `403` và `5xx` theo từng lớp.
- Giới hạn endpoint Actuator và bảo vệ Config Server bằng TLS, xác thực và phân quyền phù hợp.

Cổng, context path và tiền tố API là các lớp độc lập trong địa chỉ Config Server. Khi cấu hình đúng từng lớp và đồng bộ với URL của Config Client, reverse proxy và cổng triển khai, các ứng dụng có thể truy cập cấu hình ổn định qua một địa chỉ nhất quán.

## Tài liệu tham khảo

- [Spring Cloud Config Server — tài liệu chính thức](https://docs.spring.io/spring-cloud-config/reference/server.html)
- [Embedding the Config Server — tiền tố `spring.cloud.config.server.prefix`](https://docs.spring.io/spring-cloud-config/reference/5.0/server/embedding.html)
- [Spring Cloud Config Client — cách khai báo Config Data import và định vị tài nguyên](https://docs.spring.io/spring-cloud-config/reference/client.html)
