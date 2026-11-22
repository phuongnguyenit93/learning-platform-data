# Cấu hình management.server.port và địa chỉ mạng lắng nghe

## 1. Hạ tầng quản trị gồm những quyết định nào?

Một dịch vụ có thể nhận yêu cầu nghiệp vụ từ mạng bên ngoài nhưng chỉ cho phép công cụ vận hành cùng máy đọc Actuator. Để thể hiện ý định đó, cần phân biệt **cổng nhận kết nối** và **địa chỉ mạng mà máy chủ lắng nghe**.

- **Cổng (port)** xác định điểm nhận kết nối trên một địa chỉ IP, ví dụ `8080` hoặc `9091`.
- **Địa chỉ lắng nghe (bind address)** chọn giao diện mạng cục bộ được dùng để nhận kết nối. Điểm lắng nghe (listener) được xác định bởi địa chỉ và cổng.
- **Đường dẫn HTTP** như `/actuator/health` được xử lý sau khi kết nối đến máy chủ phù hợp.
- **Bật/công bố endpoint và phân quyền** quyết định endpoint nào có thể sử dụng, ai được phép gọi.

Trong Spring Boot **3.3.x**, mặc định Actuator dùng chung cổng HTTP của ứng dụng. Muốn tách điểm tiếp nhận quản trị, cấu hình `management.server.port`; muốn quản trị chỉ lắng nghe trên một địa chỉ riêng, dùng `management.server.address` cùng cổng quản trị khác cổng chính. [Cấu hình HTTP quản trị của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Tách cổng quản trị vẫn nằm trong cùng ứng dụng/JVM. Nó không tạo một dịch vụ được triển khai độc lập, cũng không tự tách tài nguyên CPU hoặc bộ nhớ khỏi ứng dụng.

## 2. Bốn thuộc tính cần đọc cùng nhau

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `server.port` | Cổng HTTP của máy chủ ứng dụng chính |
| `server.address` | Địa chỉ máy chủ ứng dụng chính gắn vào để nhận kết nối |
| `management.server.port` | Chọn cổng HTTP cho vùng quản trị |
| `management.server.address` | Địa chỉ lắng nghe riêng của vùng quản trị khi dùng cổng riêng |

Ví dụ về hai điểm tiếp nhận:

```text
Ứng dụng chính: địa chỉ lắng nghe 0.0.0.0, cổng 8080
Quản trị:       địa chỉ lắng nghe 127.0.0.1, cổng 9091
```

Đây là mô tả phía máy chủ. Việc gắn socket vào địa chỉ/cổng cục bộ khác với việc khách chọn địa chỉ đích để kết nối. [Cơ chế gắn socket vào địa chỉ của hệ thống](https://learn.microsoft.com/en-us/windows/win32/winsock/binding-a-socket). Người gọi không dùng `0.0.0.0` làm địa chỉ dịch vụ được quảng bá; họ dùng địa chỉ thực có thể truy cập của máy chủ, tên miền tương ứng, hoặc `127.0.0.1` khi gọi cục bộ.

`management.server.address` yêu cầu cổng quản trị riêng. Không thể chỉ đặt thuộc tính này để tách địa chỉ lắng nghe của Actuator trong khi vẫn dùng chung máy chủ/cổng ứng dụng. [Danh mục thuộc tính server và management server](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### Trường hợp dùng chung cổng

Ví dụ độc lập:

```yaml
server:
  port: 8080
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health
```

Không đặt `management.server.port`, nên endpoint HTTP quản trị dùng chung điểm tiếp nhận của ứng dụng. Với đường dẫn mặc định và endpoint đủ điều kiện, có thể gọi:

```text
http://127.0.0.1:8080/actuator/health
```

Khi cấu hình `server.address=127.0.0.1` trong trường hợp dùng chung này, phạm vi lắng nghe cục bộ tác động cả HTTP nghiệp vụ lẫn quản trị, không chỉ Actuator.

## 3. Ví dụ tách cổng và chỉ cho quản trị lắng nghe cục bộ

Đặt trong `src/main/resources/application.yml` của một ứng dụng web đã có Actuator:

```yaml
server:
  port: 8080
  address: 0.0.0.0

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

Cấu hình thể hiện hai ý định riêng:

1. HTTP nghiệp vụ có điểm tiếp nhận trên các địa chỉ IPv4 cục bộ ở cổng `8080`.
2. HTTP quản trị dùng cổng `9091`, gắn với địa chỉ quay về máy (loopback) IPv4 `127.0.0.1`.

Trong ví dụ này chỉ chủ động bật và công bố `health`. Không cần chọn tất cả endpoint chỉ để thử cổng quản trị.

Cấu hình tương đương bằng properties:

```properties
server.port=8080
server.address=0.0.0.0
management.server.port=9091
management.server.address=127.0.0.1
management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoints.web.exposure.include=health
```

Địa chỉ gọi trực tiếp từ cùng môi trường mạng của tiến trình:

```text
http://127.0.0.1:9091/actuator/health
```

Việc mở cổng 9091 không tự bật mọi endpoint. Quyết định bật/công bố vẫn cần được thỏa trước khi có endpoint tương ứng. [Điều kiện có sẵn của endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Nếu cần máy giám sát khác truy cập, phải chọn địa chỉ lắng nghe phù hợp và có đường mạng tới nó. Chỉ đổi URL trên máy giám sát không làm listener loopback tự nhận kết nối từ xa.

## 4. Chọn địa chỉ lắng nghe theo nơi người gọi thực sự chạy

### 4.1. Loopback và địa chỉ mạng cụ thể

| Giá trị minh họa | Ý nghĩa khi gắn listener IPv4 | Nơi dùng phù hợp |
| --- | --- | --- |
| `127.0.0.1` | Nhận kết nối loopback trong môi trường mạng cục bộ | Công cụ vận hành chạy cùng máy hoặc cùng không gian mạng |
| `0.0.0.0` | Địa chỉ đại diện để nhận trên các giao diện IPv4 cục bộ | Cần nhận qua nhiều giao diện và đã thiết kế phạm vi truy cập |
| `192.168.10.20` | Gắn vào địa chỉ cụ thể đã được gán cho máy | Máy có giao diện quản trị riêng mang địa chỉ đó |

`192.168.10.20` chỉ là ví dụ: phải thay bằng IP thực sự thuộc môi trường đang chạy. Không điền IP của **máy giám sát** vào bind address của **máy ứng dụng**. Bind address chọn địa chỉ cục bộ của phía nhận, không phải danh sách IP khách được phép.

Loopback IPv4 thuộc dải địa chỉ dùng cho việc quay về chính máy, không đại diện cho một máy ở xa. [Quy định địa chỉ loopback IPv4 trong RFC 1122](https://www.rfc-editor.org/rfc/rfc1122.html#section-3.2.1.3).

Các ví dụ dùng IPv4 một cách tường minh. IPv6 có địa chỉ và quy tắc lắng nghe riêng; không suy từ `0.0.0.0` rằng mọi giao diện IPv6 cũng được mở. Khi dùng tên `localhost`, còn cần xét nó phân giải thành địa chỉ IPv4 hay IPv6.

### 4.2. Lắng nghe không đồng nghĩa với truy cập được từ mọi nơi

Giả sử quản trị lắng nghe trên một IP nội bộ. Một yêu cầu từ máy khác còn phải đi qua định tuyến, tường lửa, quy tắc mạng của nền tảng, máy chủ trung gian (proxy) nếu có, rồi mới tới máy chủ HTTP.

Do đó:

- IP thuộc mạng riêng không tự tạo cơ chế xác thực người dùng.
- `0.0.0.0` không tự tạo địa chỉ IP công cộng hay mở luật tường lửa.
- Một tên miền công cộng không làm thay đổi địa chỉ mà JVM đã gắn listener.
- Tách cổng giúp chọn phạm vi mạng độc lập, nhưng vẫn cần chính sách công bố và bảo vệ endpoint phù hợp.

Trước khi chọn địa chỉ, hãy mô tả rõ người gọi: một tiến trình trên máy ứng dụng, một container khác, máy giám sát trong LAN, hay một hệ thống qua proxy. Câu trả lời quyết định vị trí cần lắng nghe.

## 5. Kiểm tra listener trước, kiểm tra endpoint sau

### Điều kiện thực hành

Dùng Spring Boot 3.3.x, Java 17 trở lên; Java 21 phù hợp. Ứng dụng đã có lớp khởi động, `spring-boot-starter-web` và `spring-boot-starter-actuator`.

Dùng cấu hình ở mục 3; chạy trực tiếp trên Windows, chưa qua container hoặc proxy. Giả định:

- Hai cổng 8080 và 9091 chưa bị tiến trình khác sử dụng.
- Không có Spring Security hoặc bộ lọc tùy chỉnh thay đổi phản hồi.
- Không có context path, base path tùy chỉnh, controller trùng đường dẫn hoặc đường phụ cho health trên cổng chính.
- Trạng thái sức khỏe là `UP`, không có nguồn cấu hình khác ghi đè.

Khởi động lại ứng dụng sau khi đổi cấu hình. Những kết quả dưới đây là kết quả dự kiến theo các điều kiện này.

### 5.1. Quan sát cổng và địa chỉ đang lắng nghe

Trong PowerShell:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080,9091 |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Đối chiếu cổng 9091 có listener gắn với `127.0.0.1`, rồi kiểm tra mã tiến trình (PID) qua `OwningProcess`. Không dùng một PID cố định trong tài liệu để so khớp; PID và thứ tự dòng thay đổi giữa các lần chạy. Lệnh này đọc trạng thái TCP của hệ điều hành, chưa chứng minh endpoint trả được dữ liệu. [Tài liệu `Get-NetTCPConnection`](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection?view=windowsserver2025-ps).

Nếu cổng xuất hiện nhưng thuộc một PID khác, cần xác định đúng tiến trình trước khi kết luận cấu hình ứng dụng có hiệu lực.

### 5.2. Gọi health trên cổng quản trị

```powershell
curl.exe --silent --show-error --max-time 3 --output NUL --write-out "%{http_code}\n" "http://127.0.0.1:9091/actuator/health"
```

Stdout dự kiến là:

```text
200
```

Lệnh in một mã HTTP kèm xuống dòng và bỏ phần thân. Muốn đọc nội dung:

```powershell
curl.exe --silent --show-error --max-time 3 "http://127.0.0.1:9091/actuator/health"
```

Phản hồi thường thấy khi khỏe và không hiển thị chi tiết:

```json
{"status":"UP"}
```

### 5.3. Kiểm tra cổng ứng dụng không tự giữ lại cùng endpoint

```powershell
curl.exe --silent --show-error --max-time 3 --output NUL --write-out "%{http_code}\n" "http://127.0.0.1:8080/actuator/health"
```

Với các giả định trên, stdout dự kiến:

```text
404
```

Điểm cần hiểu: cổng 8080 vẫn có máy chủ HTTP, nhưng yêu cầu này không được phục vụ như health endpoint ở đó. Đây là **phản hồi HTTP**, khác với không thể kết nối đến cổng.

Nếu bạn chủ động cấu hình đường phụ cho health hoặc có controller/proxy cung cấp đường dẫn tương tự, kết quả có thể khác; phải kiểm tra cấu hình đó riêng.

### 5.4. Phân biệt lỗi mạng với lỗi endpoint

| Quan sát | Hướng kiểm tra |
| --- | --- |
| Không kết nối được hoặc hết thời gian chờ | Listener, địa chỉ đích, cổng, định tuyến, tường lửa |
| Có HTTP 404 | Đúng cổng và đường dẫn chưa; endpoint có được bật/công bố không |
| Có HTTP 401 hoặc 403 | Xác thực, phân quyền và các bộ lọc bảo vệ |
| Có phản hồi health với trạng thái không khỏe | Đã đến được API; cần kiểm tra các thành phần sức khỏe |

Khi curl không nhận được phản hồi HTTP và phần `--write-out` in `000`, đừng coi đó là mã HTTP do Actuator trả. Hãy đọc luồng lỗi (stderr) và mã thoát của curl. curl giữ mã phản hồi ở giá trị 0 khi chưa nhận mã phản hồi từ máy chủ. [Ý nghĩa mã phản hồi của curl](https://curl.se/libcurl/c/CURLINFO_RESPONSE_CODE.html). Tránh sửa `include` liên tục để xử lý một listener chưa thể kết nối.

## 6. Đọc đúng địa chỉ trong container và sau proxy

### Container có không gian mạng riêng

Trong mô hình container dùng mạng bridge riêng, `127.0.0.1` bên trong container trỏ về chính môi trường mạng của container. Listener quản trị chỉ gắn loopback trong container không tự trở thành listener trên loopback của máy host.

Cần tách hai lớp cấu hình:

1. Địa chỉ/cổng mà tiến trình Java lắng nghe **bên trong container**.
2. Địa chỉ/cổng được nền tảng công bố **trên host hoặc qua mạng triển khai**.

Ví dụ, thông số công bố cổng Docker `127.0.0.1:19091:9091` diễn đạt cổng host 19091 trên loopback chuyển đến cổng container 9091. Nó không sửa cấu hình listener của JVM. Trong mô hình bridge thông thường, tiến trình trong container còn phải lắng nghe trên giao diện có thể nhận lưu lượng chuyển tiếp; gắn riêng vào loopback của container không đáp ứng điều đó.

Đây là ví dụ phân tích các lớp, không phải lệnh triển khai đầy đủ. Các chế độ mạng khác như dùng chung không gian mạng cần được xét theo cấu hình thực tế. [Cách Docker công bố và ánh xạ cổng](https://docs.docker.com/engine/network/port-publishing/).

### Proxy hoặc cổng công bố khác cổng nội bộ

Một địa chỉ bên ngoài như `https://monitor.example.com/actuator/health` có thể đi qua proxy tới listener HTTP nội bộ 9091. Cổng và giao thức mà người dùng thấy không nhất thiết trùng trực tiếp với listener JVM.

Vì vậy khi tìm lỗi, ghi rõ cả hai chặng: **người gọi → proxy/cổng công bố** và **proxy → ứng dụng**. Nếu proxy nằm ở máy khác, cấu hình quản trị chỉ gắn loopback trên máy ứng dụng không tự cho proxy đó kết nối trực tiếp.

## 7. Các giá trị đặc biệt và giới hạn của việc tách cổng

### Dùng chung, dùng cổng riêng, chọn cổng động hoặc tắt HTTP quản trị

Với cổng ứng dụng cố định 8080 trong ví dụ:

| Giá trị `management.server.port` | Ý nghĩa |
| --- | --- |
| Không đặt | Dùng cổng ứng dụng |
| `8080` | Vẫn dùng cùng cổng, không tạo sự tách biệt chỉ vì có khai báo |
| `9091` | Dùng cổng quản trị khác cổng ứng dụng |
| `0` | Yêu cầu chọn cổng khả dụng động; cần đọc cổng thực tế sau khi khởi động |
| `-1` | Tắt việc cung cấp endpoint quản trị qua HTTP |

API cấu hình của Spring Boot ghi rõ ý nghĩa `0` và `-1`; giá trị chưa đặt cho phép dùng cổng server chính. [API `ManagementServerProperties`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html).

Không gọi URL với `:0` như thể 0 là cổng thực tế đã được cấp. Với cổng động, quan sát log hoặc thông tin máy chủ sau khi khởi động. Cách phát hiện cổng thực tế được mô tả trong [hướng dẫn máy chủ web nhúng](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html).

Cấu hình tắt HTTP quản trị:

```properties
management.server.port=-1
```

Điều này không phải lệnh dừng JVM hoặc tắt toàn bộ HTTP nghiệp vụ. Nó cũng không tự quyết định việc công bố JMX; JMX có cấu hình bật và danh sách công bố riêng. [Quản trị qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### Cổng khác không tự đồng nghĩa với HTTPS

Các ví dụ trong bài dùng HTTP không cấu hình TLS. Chọn số cổng 8443 hay 9443 không tự tạo HTTPS. Khi cần TLS cho vùng quản trị riêng, phải cấu hình SSL tương ứng; lựa chọn chứng thư và phạm vi kết nối là quyết định riêng.

### Listener quản trị khỏe chưa chứng minh listener nghiệp vụ khỏe

Khi quản trị có máy chủ/cổng riêng, một phép kiểm tra trên cổng quản trị có thể thành công dù hạ tầng web chính đang gặp vấn đề nhận kết nối. Vì vậy cần thiết kế phép kiểm tra phù hợp với mục đích vận hành; không dùng một kết quả health trên cổng riêng làm bằng chứng duy nhất rằng mọi đường phục vụ nghiệp vụ đều hoạt động. [Lưu ý của Spring Boot về health và cổng quản trị riêng](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 8. Lỗi cấu hình thường gặp

| Sai sót | Cách suy nghĩ để sửa |
| --- | --- |
| Đặt địa chỉ quản trị riêng nhưng giữ chung cổng | Chọn cổng quản trị khác trước khi cần listener độc lập |
| Gán IP của máy giám sát vào `management.server.address` | Chọn IP cục bộ của máy chạy ứng dụng; lọc khách ở lớp chính sách phù hợp |
| Gán IP không tồn tại trên máy | Kiểm tra địa chỉ đã được cấp cho giao diện mạng thực tế |
| Gọi `localhost` từ một máy khác | `localhost` là máy người gọi; dùng địa chỉ máy chạy ứng dụng khi cần truy cập từ xa |
| Nhầm loopback trong container với loopback của host | Xác định không gian mạng ở từng chặng |
| Đổi cổng trong file nhưng ứng dụng vẫn nghe cổng cũ | Kiểm tra profile, biến môi trường, tham số khởi động và lần khởi động gần nhất |
| Cổng đã được tiến trình khác dùng | Xác định tiến trình chiếm cổng hoặc chọn cổng phù hợp, không chỉ thử lại URL |

Spring Boot có thứ tự ưu tiên giữa các nguồn cấu hình. Ví dụ tham số `--management.server.port=9191` có thể ghi đè giá trị 9091 trong file. Khi đó cần kiểm tra giá trị đang có hiệu lực, thay vì chỉ nhìn một file YAML. [Thứ tự nguồn cấu hình](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Cách điều tra gọn: xác nhận **tiến trình → listener/IP/cổng → đường mạng → giao thức/đường dẫn → bật/công bố → quyền truy cập → dữ liệu health**. Kiểm tra theo chặng giúp tránh sửa cấu hình endpoint cho một lỗi xảy ra trước khi HTTP tới được ứng dụng.

## 9. Tự kiểm tra trước khi chọn cấu hình

**Tình huống 1:** Ứng dụng chạy trực tiếp trên một máy, công cụ quản trị chạy cùng máy, còn HTTP nghiệp vụ cần nhận kết nối qua LAN.

Có thể chọn `server.address=0.0.0.0`, `server.port=8080`, và listener quản trị riêng `127.0.0.1:9091`; sau đó chọn endpoint được phép công bố.

**Tình huống 2:** Máy giám sát là máy khác trong mạng nội bộ. Quản trị đang gắn `127.0.0.1:9091`.

Thay URL của máy giám sát sẽ chưa đủ. Cần thiết kế đường kết nối và listener quản trị có thể nhận trên giao diện thích hợp, cùng chính sách mạng và quyền truy cập tương ứng.

**Tình huống 3:** File đặt 9091 nhưng log cho biết vùng quản trị chạy ở 9191.

Kiểm tra nguồn cấu hình có ưu tiên cao hơn, profile và tham số khởi động; xác nhận listener và PID trước khi sửa URL.

**Tình huống 4:** Cổng quản trị trả health thành công nhưng người dùng không vào được dịch vụ trên cổng ứng dụng.

Kiểm tra riêng listener và hạ tầng phục vụ nghiệp vụ. Kết nối thành công đến vùng quản trị riêng chỉ chứng minh được chặng quản trị vừa kiểm tra.
