# Đường dẫn /eureka/, context path và địa chỉ mà client truy cập

Eureka Server cung cấp REST API để Eureka Client đăng ký instance, gửi heartbeat và lấy danh sách service. Với cấu hình mặc định, server thường lắng nghe ở port `8761` và API có base path `/eureka/`. Vì vậy, địa chỉ client thường dùng là `http://localhost:8761/eureka/`.

Khi triển khai sau reverse proxy, đổi port hoặc đặt Spring Boot vào một context path riêng, URL client phải phản ánh đúng địa chỉ mà client thực sự truy cập được. Nhầm lẫn giữa context path của ứng dụng và base path `/eureka/` là nguyên nhân phổ biến gây lỗi `404`, lỗi kết nối hoặc client không đăng ký được. Bài học này phân tích từng phần của URL và cách cấu hình server, client, proxy để chúng khớp nhau.

## 1. Cấu trúc địa chỉ Eureka

Một URL Eureka Client sử dụng thường có dạng:

```text
http(s)://<host>:<port>/<context-path>/eureka/
```

Trong đó:

- `http` hoặc `https` là scheme mà client dùng để kết nối.
- `<host>` là hostname hoặc IP có thể phân giải và truy cập từ môi trường chạy client.
- `<port>` là port mà Eureka Server hoặc reverse proxy công bố.
- `<context-path>` là prefix của ứng dụng Spring Boot nếu server được triển khai dưới một context path riêng; nếu không có thì bỏ phần này.
- `/eureka/` là base path REST API mặc định của Eureka Server.

Ví dụ:

| Cách triển khai | URL client truy cập |
| --- | --- |
| Eureka chạy local, không có context path | `http://localhost:8761/eureka/` |
| Context path là `/discovery` | `http://eureka.internal:8761/discovery/eureka/` |
| HTTPS qua domain công khai | `https://eureka.example.com/eureka/` |
| Reverse proxy công bố prefix `/registry` | `https://gateway.example.com/registry/eureka/` |

Hãy phân biệt hai phần cuối URL: context path là prefix của web application; `/eureka/` là đường dẫn REST API của Eureka. Nếu context path là `/discovery`, đường dẫn đầy đủ là `/discovery/eureka/`.

## 2. Cấu hình Eureka Server mặc định

Một Eureka Server đơn giản cần dependency server và annotation `@EnableEurekaServer`.

Ví dụ class khởi động:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
```

Ví dụ `application.yml` cho server chạy local:

```yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: ${EUREKA_HOST:localhost}
  client:
    register-with-eureka: false
    fetch-registry: false
```

`register-with-eureka: false` và `fetch-registry: false` phù hợp với một Eureka Server độc lập không đăng ký vào chính nó và không lấy registry từ peer. Trong cụm Eureka nhiều node, cấu hình peer cần được thiết lập riêng; các server thường đăng ký và lấy registry từ các peer để đồng bộ. Không sao chép hai giá trị `false` này cho mọi node trong một cụm peer-aware mà không xem xét topology.

Với cấu hình mặc định, Eureka Server nhận REST request tại `/eureka/`. Client sẽ dùng URL có port `8761` và base path đó.

## 3. Context path của Spring Boot

`server.servlet.context-path` đặt prefix chung cho các servlet endpoint của ứng dụng Spring Boot. Nếu khai báo:

```yaml
server:
  port: 8761
  servlet:
    context-path: /discovery
```

Các endpoint của ứng dụng được đặt dưới prefix `/discovery`. Vì Eureka API vốn có base path `/eureka/`, URL đầy đủ mà client cần gọi sẽ là:

```text
http://localhost:8761/discovery/eureka/
```

Một số ví dụ đối chiếu:

| `server.servlet.context-path` | Eureka API URL |
| --- | --- |
| Không khai báo hoặc context root | `http://localhost:8761/eureka/` |
| `/discovery` | `http://localhost:8761/discovery/eureka/` |
| `/platform/registry` | `http://localhost:8761/platform/registry/eureka/` |

Context path phải bắt đầu bằng dấu `/`. Tránh thêm dấu `/` ở cuối nếu không cần thiết; giữ một cách viết nhất quán trong cấu hình và reverse proxy.

### 3.1. Context path không phải server port

Hai thuộc tính này giải quyết hai phần khác nhau:

- `server.port` quyết định tiến trình lắng nghe ở cổng nào, ví dụ `8761`.
- `server.servlet.context-path` quyết định prefix URL của web application, ví dụ `/discovery`.

Đổi port không tự đổi path; đổi context path không tự đổi port. Khi URL không truy cập được, hãy kiểm tra cả hai.

### 3.2. Management port không phải Eureka API port

Nếu cấu hình `management.server.port` để Actuator chạy trên một port riêng, điều đó không tự chuyển Eureka REST API sang port quản trị. Eureka Client vẫn phải trỏ tới port ứng dụng đang phục vụ Eureka API.

Ví dụ:

```yaml
server:
  port: 8761

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,info
```

Trong cấu hình này, Eureka API vẫn ở port `8761`; Actuator được phục vụ trên port `9001` theo cấu hình management. Không cấu hình `defaultZone` thành `http://localhost:9001/eureka/` trừ khi bạn đã chủ động thiết kế một routing riêng cho Eureka API trên port đó.

## 4. Cấu hình địa chỉ trong Eureka Client

Eureka Client chỉ cần biết URL mà Eureka Server có thể truy cập từ môi trường của client. Ví dụ server dùng port mặc định và không có context path:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
  instance:
    prefer-ip-address: true
```

Điểm cần chú ý:

- `eureka.client.service-url.defaultZone` là URL gốc của Eureka Server mà client sử dụng.
- `defaultZone` là tên key của map service URL; giữ đúng chữ hoa/thường `Z` như ví dụ trong tài liệu Eureka/Spring Cloud Netflix.
- `register-with-eureka` bật đăng ký instance của ứng dụng client.
- `fetch-registry` bật lấy registry để tìm các service khác.
- `prefer-ip-address` điều khiển việc công bố IP thay cho hostname trong thông tin instance; nó không thay đổi URL server mà client kết nối.

Nếu server có context path `/discovery`, cập nhật URL:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/discovery/eureka/}
```

Khi triển khai production, thường cấp URL qua biến môi trường:

```text
EUREKA_SERVER_URL=https://eureka.internal.example.com/discovery/eureka/
```

Như vậy cùng một artifact client có thể chạy ở local, Docker hoặc production mà không phải sửa mã nguồn.

## 5. Địa chỉ client phải truy cập được từ đâu?

Một lỗi thường gặp là URL đúng khi kiểm tra từ máy host nhưng sai khi client chạy trong container hoặc một máy khác.

### 5.1. Chạy cả server và client trên máy local

Nếu cả hai tiến trình chạy trực tiếp trên cùng máy, client có thể dùng:

```text
http://localhost:8761/eureka/
```

Nếu Eureka Server dùng context path `/discovery`:

```text
http://localhost:8761/discovery/eureka/
```

### 5.2. Client chạy trong Docker

Trong container client, `localhost` trỏ về chính container client. Nếu Eureka Server chạy trong một container khác trên cùng Docker network, hãy dùng tên service hoặc DNS alias của server:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
```

Tên `eureka-server` phải khớp với service name hoặc network alias trong Docker Compose. Nếu Eureka Server chạy trên máy host, dùng hostname/IP mà container có thể truy cập theo cấu hình Docker của hệ điều hành; không mặc định rằng `localhost` bên trong container là host.

### 5.3. Client chạy trên máy khác

Dùng DNS hoặc IP của máy Eureka Server có thể truy cập qua mạng:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://10.0.0.15:8761/eureka/
```

Đảm bảo firewall, security group và network policy cho phép client kết nối tới port server. Nếu Eureka công bố hostname/IP của instance cho consumer, các địa chỉ instance đó cũng phải có thể truy cập từ consumer; kết nối được tới server registry chưa đảm bảo consumer gọi được service instance.

## 6. Triển khai sau reverse proxy hoặc ingress

Trong production, Eureka Server có thể nằm sau reverse proxy, ingress hoặc load balancer. Client khi đó thường truy cập URL bên ngoài thay vì địa chỉ nội bộ của process.

Ví dụ public URL:

```text
https://gateway.example.com/registry/eureka/
```

Có hai cách tổ chức path thường gặp:

1. **Ứng dụng tự có context path `/registry`:** Eureka Server nhận request nội bộ ở `/registry/eureka/`; proxy chuyển tiếp nguyên path đó.
2. **Proxy thêm prefix và rewrite path:** Client gọi `/registry/eureka/`, proxy bỏ prefix `/registry` rồi chuyển request tới upstream `/eureka/`.

Hai cách đều có thể hoạt động nếu quy tắc proxy và URL client khớp nhau. Tránh tình huống proxy vừa giữ prefix vừa thêm lại context path, khiến request thành `/registry/registry/eureka/` hoặc một đường dẫn không tồn tại.

Với HTTPS termination tại proxy, client dùng scheme `https` và hostname công khai. Proxy phải chuyển tiếp đúng các REST method và path mà Eureka cần; cấu hình xác thực, TLS và network access cần được giới hạn phù hợp. Nếu Eureka server chạy theo mô hình peer, các server cũng cần URL peer nội bộ có thể truy cập ổn định; không nhất thiết dùng cùng URL public dành cho client bên ngoài.

Khi ứng dụng tự tạo redirect hoặc công bố URL dựa trên request, hãy cấu hình forwarded headers và proxy đúng cách theo phiên bản Spring Boot. Không dùng forwarded header từ nguồn không tin cậy.

## 7. Kiểm tra URL Eureka bằng HTTP

Sau khi khởi động server, kiểm tra REST API từ cùng môi trường mạng với client.

Với server mặc định:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8761/eureka/apps
```

Với context path `/discovery`:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8761/discovery/eureka/apps
```

Nếu endpoint được bảo vệ bằng authentication, cần gửi thông tin xác thực phù hợp khi kiểm tra. Một response thành công cho thấy request đã tới đúng REST endpoint; danh sách application rỗng vẫn có thể xảy ra nếu chưa có client nào đăng ký.

Có thể kiểm tra theo từng lớp:

1. Kiểm tra process Eureka Server đã khởi động và lắng nghe đúng port.
2. Xác định context path thực tế từ cấu hình đang active.
3. Ghép context path với `/eureka/` để có base URL.
4. Gọi endpoint `/apps` từ máy hoặc container chạy Eureka Client.
5. Đặt cùng base URL vào `eureka.client.service-url.defaultZone`.
6. Kiểm tra log client để xác nhận request đăng ký và fetch registry thành công.

Không chỉ kiểm tra URL bằng trình duyệt trên host nếu client chạy ở một network namespace khác. Hãy chạy `curl` từ container hoặc máy client để xác nhận DNS, route và firewall.

## 8. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client báo connection refused | Server chưa chạy, sai port, bind address hoặc firewall chặn | Xác nhận process, port `8761` (hoặc port thực tế) và đường mạng từ client. |
| Client nhận `404 Not Found` | Sai context path hoặc thiếu `/eureka/` trong URL | Đối chiếu `server.servlet.context-path` và base path REST API; thử `/eureka/apps` hoặc `<context-path>/eureka/apps`. |
| Client gọi được từ host nhưng không gọi được từ Docker | Dùng `localhost` trong container hoặc DNS service không đúng | Dùng hostname service trong Docker network hoặc địa chỉ host có thể truy cập từ container. |
| Client đăng ký được nhưng không lấy được registry | `fetch-registry` bị tắt, URL/credential không đúng hoặc response bị proxy chặn | Kiểm tra `fetch-registry`, log client, authentication và proxy route. |
| Eureka Dashboard mở được nhưng client không đăng ký | Dashboard path đúng nhưng URL REST API hoặc client property sai; server security chặn REST request | Kiểm tra `/eureka/apps`, `defaultZone` và quyền truy cập của client. |
| Proxy trả `502` hoặc `504` | Upstream sai host/port, timeout hoặc proxy không truy cập được server | Kiểm tra upstream health, DNS, route và timeout của proxy. |
| Client tiếp tục dùng URL cũ sau khi đổi context path | Profile hoặc biến môi trường ghi đè file cấu hình | Kiểm tra property source, `EUREKA_SERVER_URL` và profile active. |

Một số dấu hiệu HTTP thường giúp khoanh vùng:

- `404`: server có phản hồi nhưng path không khớp hoặc endpoint không được map.
- `401`/`403`: request tới được server/proxy nhưng thiếu quyền hoặc bị policy chặn.
- `502`/`504`: reverse proxy không nhận được response hợp lệ từ upstream hoặc hết thời gian chờ.
- `Connection refused`/timeout: kiểm tra process, port, DNS, route và firewall trước khi xem xét path.

## 9. Ví dụ cấu hình hoàn chỉnh

### 9.1. Eureka Server có context path `/discovery`

```yaml
spring:
  application:
    name: eureka-server

server:
  port: 8761
  servlet:
    context-path: /discovery

eureka:
  instance:
    hostname: ${EUREKA_HOST:localhost}
  client:
    register-with-eureka: false
    fetch-registry: false
```

Base URL của Eureka API là:

```text
http://localhost:8761/discovery/eureka/
```

### 9.2. Eureka Client kết nối server trên

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/discovery/eureka/}
  instance:
    prefer-ip-address: true
```

Nếu client chạy trong Docker, thay giá trị mặc định `localhost` bằng hostname của Eureka Server trên Docker network, ví dụ `http://eureka-server:8761/discovery/eureka/`.

## 10. Ghi nhớ

- Eureka REST API mặc định có base path `/eureka/`; URL local mặc định thường là `http://localhost:8761/eureka/`.
- `server.servlet.context-path` thêm prefix chung phía trước base path, ví dụ `/discovery/eureka/`.
- `server.port` và context path là hai cấu hình độc lập; `management.server.port` không tự chuyển Eureka API.
- Client cấu hình URL server qua `eureka.client.service-url.defaultZone`; giữ đúng key `defaultZone`.
- Địa chỉ phải truy cập được từ chính môi trường chạy client; `localhost` trong container là container đó.
- Reverse proxy phải chuyển tiếp đúng scheme, host, port và path; kiểm tra rewrite để không thiếu hoặc lặp prefix.
- Dùng `/eureka/apps` hoặc `<context-path>/eureka/apps` để xác minh REST endpoint từ network của client.

Khi context path, base path `/eureka/` và địa chỉ mạng được cấu hình nhất quán, Eureka Client có thể đăng ký, gửi heartbeat và lấy registry ổn định trong cả môi trường local lẫn production.
