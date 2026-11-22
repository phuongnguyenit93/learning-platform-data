# Cấu hình HTTPS cho cổng quản trị và quan hệ với HTTPS của ứng dụng

## 1. Xác định nơi kết thúc TLS

HTTPS là HTTP truyền qua kết nối được bảo vệ bằng TLS. Trước khi chọn thuộc tính, hãy xác định kết nối TLS được xử lý ngay tại ứng dụng Spring Boot hay tại một máy chủ trung gian (proxy).

Nếu JVM trực tiếp phục vụ HTTPS, điểm lắng nghe phải có cấu hình TLS và vật liệu mật mã phù hợp. Chỉ đổi cổng từ 8080 sang 8443 hoặc 9443 không tự biến HTTP thành HTTPS.

Trong bài này, **Spring Boot 3.3.x**, đối chiếu 3.3.13, có hai nhóm cấu hình:

| Nhóm | Phạm vi |
| --- | --- |
| `server.ssl.*` | TLS cho máy chủ ứng dụng chính |
| `management.server.ssl.*` | TLS riêng cho máy chủ quản trị khi quản trị dùng cổng khác cổng ứng dụng |

Spring Boot cho phép hai cổng có cấu hình SSL khác nhau, kể cả trường hợp ứng dụng dùng HTTPS còn quản trị dùng HTTP. [Cấu hình SSL riêng cho máy chủ quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.configuring-management-specific-ssl).

Tên thuộc tính vẫn dùng chữ `ssl`, nhưng mục đích là cấu hình HTTPS/TLS của máy chủ. Không lấy tên thuộc tính làm lý do bật các phiên bản giao thức SSL cũ.

## 2. Dùng chung cổng khác với dùng cổng quản trị riêng

### 2.1. Khi dùng chung cổng

Nếu không đặt `management.server.port`, Actuator dùng chung máy chủ/cổng của ứng dụng. Khi đó TLS được quyết định bởi `server.ssl.*`.

Ví dụ với kho khóa thử sẽ được tạo ở mục 4:

```yaml
server:
  port: 8443
  address: 127.0.0.1
  ssl:
    enabled: true
    key-store: file:./tls/app-local.p12
    key-store-type: PKCS12
    key-store-password: ${APP_TLS_STORE_PASSWORD}
    key-alias: app-local

management:
  endpoints:
    web:
      exposure:
        include: health
```

Trong cấu hình độc lập này, địa chỉ health là:

```text
https://localhost:8443/actuator/health
```

Endpoint quản trị và HTTP nghiệp vụ đi qua cùng máy chủ TLS. Không dùng `management.server.ssl.*` để yêu cầu một chứng thư riêng theo đường dẫn `/actuator` trên cùng listener. TLS được thiết lập trước khi máy chủ đọc đường dẫn HTTP để chọn endpoint.

Các thuộc tính SSL riêng của quản trị đòi hỏi cổng quản trị riêng. [Phạm vi thuộc tính management server](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

### 2.2. Khi quản trị dùng cổng khác

Với `server.port=8443` và `management.server.port=9443`, có thể chọn TLS quản trị độc lập.

Trong cơ chế máy chủ nhúng mặc định của 3.3.13, máy chủ quản trị được tùy chỉnh theo cấu hình phía ứng dụng trước; nếu có đối tượng SSL quản trị riêng thì đối tượng đó được đặt thay vào máy chủ quản trị. Điều này dẫn tới hai cách đọc:

- **Không khai báo khối SSL quản trị riêng:** trong cơ chế mặc định này, máy chủ quản trị giữ cấu hình SSL đã nhận từ phía ứng dụng.
- **Có khai báo SSL quản trị riêng:** cung cấp cấu hình phù hợp cho nó, không giả định các trường thiếu sẽ được ghép từng trường với `server.ssl.*`.

Đây là suy luận từ [`ManagementWebServerFactoryCustomizer` của 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementWebServerFactoryCustomizer.java). Nếu dự án có tùy chỉnh máy chủ bằng mã, cần kiểm tra thêm tùy chỉnh đó.

Ví dụ, đặt riêng `management.server.ssl.enabled=true` không phải cách rõ ràng để chọn “chứng thư của ứng dụng cộng vài thay đổi nhỏ”. Khi cần quản trị riêng, hãy khai báo đủ nguồn khóa/chứng thư hoặc chọn một SSL bundle đã có đầy đủ vật liệu.

## 3. Cần những gì để máy chủ phục vụ HTTPS?

| Thành phần | Công dụng |
| --- | --- |
| Khóa riêng (private key) | Chứng minh máy chủ sở hữu khóa tương ứng với chứng thư |
| Chứng thư máy chủ (certificate), kèm chuỗi cần thiết | Giới thiệu danh tính của máy chủ để khách kiểm tra |
| Kho khóa (keystore) | Chứa khóa riêng và chứng thư, ví dụ định dạng PKCS12 |
| Tên mục khóa (alias) | Chọn đúng mục khóa riêng trong kho |
| Nguồn tin cậy phía khách | Cho phép công cụ gọi xác minh chứng thư máy chủ |
| Tên miền/IP trong SAN | Cho phép đối chiếu danh tính chứng thư với URL được gọi |

Không nhầm **keystore phục vụ phía máy chủ** với **truststore dùng để kiểm tra bên kia**. Trong HTTPS một chiều của bài thử, máy chủ cần khóa riêng và chứng thư; công cụ curl cần tin chứng thư máy chủ.

Nếu sau này dùng xác thực TLS hai chiều (mTLS), máy chủ còn kiểm tra chứng thư khách và cần cấu hình tin cậy phù hợp. Bật HTTPS thông thường chưa có nghĩa mọi khách phải trình chứng thư. [Vai trò keystore và truststore trong Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html).

Các thuộc tính thường dùng khi chọn PKCS12:

| Thuộc tính tương đối dưới nhóm SSL | Giá trị trong ví dụ |
| --- | --- |
| `enabled` | `true` |
| `key-store` | `file:./tls/management-local.p12` |
| `key-store-type` | `PKCS12` |
| `key-store-password` | Giá trị lấy từ biến môi trường |
| `key-alias` | `management-local` |

`file:./tls/management-local.p12` là đường dẫn tương đối theo thư mục làm việc của tiến trình Java. Nó không tự tính từ vị trí của `application.yml`. Nếu dùng `classpath:`, tài nguyên lại được tìm trên classpath; đây là hai cách định vị khác nhau.

## 4. Tạo vật liệu TLS cho bài thử cục bộ

Phần này là bài thực hành cho một **dự án thử riêng** đã có lớp khởi động Spring Boot 3.3.x, `spring-boot-starter-web` và `spring-boot-starter-actuator`. Dùng JDK 21; các lệnh chạy trong PowerShell tại thư mục gốc của dự án thử.

Chứng thư tự ký trong bài chỉ phục vụ thử nghiệm cục bộ, có SAN cho `localhost` và `127.0.0.1`. Không dùng nó như chứng thư cho một tên miền triển khai khác.

### 4.1. Tạo thư mục mới và mật khẩu phiên thực hành

Giả định dự án thử chưa có thư mục `tls`:

```powershell
New-Item -ItemType Directory -Path ./tls -ErrorAction Stop | Out-Null
$env:APP_TLS_STORE_PASSWORD = [Guid]::NewGuid().ToString("N")
$env:MGMT_TLS_STORE_PASSWORD = [Guid]::NewGuid().ToString("N")
```

Hai biến nhận giá trị khác nhau, được giữ trong phiên PowerShell. Không in hoặc chép chúng vào bài học. Chạy phần tạo kho khóa và khởi động ứng dụng từ phiên giữ các biến này; nếu chạy bằng IDE hoặc công cụ khác, cần cấp cùng giá trị cho tiến trình Java.

Không chạy lại hai dòng tạo mật khẩu rồi dùng kho khóa đã tạo bằng mật khẩu cũ. Khi mở phiên mới, phải cấp lại đúng mật khẩu của kho hiện có hoặc tạo bộ vật liệu thử mới một cách có chủ đích.

### 4.2. Tạo hai kho khóa độc lập

Mỗi dòng sau là một lệnh đầy đủ:

```powershell
keytool -genkeypair -alias app-local -keyalg RSA -keysize 2048 -validity 30 -dname "CN=localhost,O=LocalLab,C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -storetype PKCS12 -keystore ./tls/app-local.p12 -storepass:env APP_TLS_STORE_PASSWORD -keypass:env APP_TLS_STORE_PASSWORD
keytool -genkeypair -alias management-local -keyalg RSA -keysize 2048 -validity 30 -dname "CN=localhost,O=LocalLab,C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -storetype PKCS12 -keystore ./tls/management-local.p12 -storepass:env MGMT_TLS_STORE_PASSWORD -keypass:env MGMT_TLS_STORE_PASSWORD
```

`-storepass:env` và `-keypass:env` yêu cầu keytool lấy giá trị từ biến môi trường mang tên được chỉ định. Trong mỗi kho PKCS12 của bài thử, mật khẩu mục khóa được đặt bằng mật khẩu kho.

SAN chứa tên/IP mà khách sẽ dùng. Chỉ đặt `CN=localhost` rồi bỏ qua SAN không phải cách kiểm tra tên máy chủ đáng tin cậy cho các công cụ hiện đại. [Lệnh keytool, tùy chọn mật khẩu và phần mở rộng chứng thư trong JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html).

### 4.3. Xuất chứng thư công khai cho curl

```powershell
keytool -exportcert -rfc -alias app-local -keystore ./tls/app-local.p12 -storepass:env APP_TLS_STORE_PASSWORD -file ./tls/app-local.crt
keytool -exportcert -rfc -alias management-local -keystore ./tls/management-local.p12 -storepass:env MGMT_TLS_STORE_PASSWORD -file ./tls/management-local.crt
```

Kết quả cần có:

| Tệp | Vai trò |
| --- | --- |
| `tls/app-local.p12` | Khóa riêng và chứng thư cho ứng dụng |
| `tls/management-local.p12` | Khóa riêng và chứng thư cho quản trị |
| `tls/app-local.crt` | Chứng thư công khai dạng PEM để khách tin máy chủ ứng dụng trong bài thử |
| `tls/management-local.crt` | Chứng thư công khai dạng PEM để khách tin máy chủ quản trị trong bài thử |

Tệp `.p12` chứa khóa riêng; không đưa các kho thử và mật khẩu vào Git. Tệp `.crt` xuất theo lệnh này không chứa khóa riêng. Trong triển khai thật, quản lý khóa, chứng thư, chuỗi tin cậy và việc gia hạn theo hạ tầng đã chọn.

## 5. Hai cổng HTTPS với hai kho khóa

Dùng cấu hình sau trong `src/main/resources/application.yml` của dự án thử:

```yaml
server:
  port: 8443
  address: 127.0.0.1
  ssl:
    enabled: true
    key-store: file:./tls/app-local.p12
    key-store-type: PKCS12
    key-store-password: ${APP_TLS_STORE_PASSWORD}
    key-alias: app-local

management:
  server:
    port: 9443
    address: 127.0.0.1
    ssl:
      enabled: true
      key-store: file:./tls/management-local.p12
      key-store-type: PKCS12
      key-store-password: ${MGMT_TLS_STORE_PASSWORD}
      key-alias: management-local
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

Đọc cấu hình thành hai bộ riêng:

| Nội dung | Ứng dụng chính | Quản trị |
| --- | --- | --- |
| Cổng | `8443` | `9443` |
| Giao thức | HTTPS | HTTPS |
| Địa chỉ lắng nghe | `127.0.0.1` | `127.0.0.1` |
| Kho khóa | `app-local.p12` | `management-local.p12` |
| Alias | `app-local` | `management-local` |
| Nguồn mật khẩu | `APP_TLS_STORE_PASSWORD` | `MGMT_TLS_STORE_PASSWORD` |

Ứng dụng và quản trị có thể cùng dùng một kho khi thiết kế yêu cầu như vậy; hai kho trong bài nhằm làm rõ sự độc lập của cấu hình.

### Kiểm tra bằng curl có xác minh chứng thư

Khởi động dự án thử từ thư mục gốc và phiên có đúng biến môi trường. Giả định:

- Không có Spring Security, proxy, đường dẫn tùy chỉnh hoặc controller trùng đường dẫn đang thử.
- Không có nguồn cấu hình khác ghi đè, không thêm đường phụ health vào cổng ứng dụng.
- Chứng thư còn hạn; curl hỗ trợ `--cacert` và môi trường khách có thể kiểm tra chứng thư thử.
- Trạng thái health là `UP`.

Trong PowerShell:

```powershell
curl.exe --cacert ./tls/management-local.crt --silent --show-error --max-time 5 --output NUL --write-out "%{http_code}\n" "https://localhost:9443/actuator/health"
curl.exe --cacert ./tls/app-local.crt --silent --show-error --max-time 5 --output NUL --write-out "%{http_code}\n" "https://localhost:8443/actuator/health"
```

Stdout dự kiến của hai lệnh theo thứ tự:

```text
200
404
```

Lệnh thứ nhất kiểm tra health tại máy chủ quản trị. Lệnh thứ hai dùng đúng chứng thư ứng dụng để thiết lập TLS nhưng không có health ở cổng chính trong cấu hình bài thử. HTTP 404 ở đây khác với lỗi bắt tay TLS.

Muốn xem nội dung health:

```powershell
curl.exe --cacert ./tls/management-local.crt --silent --show-error --max-time 5 "https://localhost:9443/actuator/health"
```

Với các điều kiện đã nêu, JSON thường thấy:

```json
{"status":"UP"}
```

`--cacert` cấp nguồn tin cậy tường minh cho lần gọi. Curl vẫn kiểm tra chứng thư và tên máy chủ; không dùng `-k`/`--insecure` làm tiêu chí chứng minh cấu hình tin cậy đúng. [Cách curl xác minh chứng thư máy chủ](https://curl.se/docs/sslcerts.html).

Các phản hồi trên là kết quả dự kiến có điều kiện. Địa chỉ, thời hạn và nội dung chứng thư sinh ra mỗi lần không cố định, nên không ghi một fingerprint hoặc ngày hết hạn giả vào tài liệu.

## 6. Các tổ hợp giữa HTTPS ứng dụng và HTTPS quản trị

Sau khi hiểu cấu hình đầy đủ ở mục 5, có thể thay đổi ý định ở từng máy chủ:

| Ứng dụng | Quản trị | Cách cấu hình |
| --- | --- | --- |
| HTTPS, chung cổng với Actuator | Cùng HTTPS | Dùng `server.ssl.*`; không tạo SSL quản trị riêng |
| HTTPS 8443 | HTTPS 9443 với kho riêng | Cấu hình đủ hai nhóm SSL như mục 5 |
| HTTPS 8443 | HTTP 9091 | Giữ TLS ứng dụng, đặt cổng quản trị riêng và `management.server.ssl.enabled=false` |
| HTTP 8080 | HTTPS 9443 | Tắt TLS phía ứng dụng, giữ đầy đủ TLS quản trị riêng |
| HTTPS 8443 | Cổng quản trị riêng, chưa đặt SSL riêng | Giữ SSL ứng dụng trong cơ chế mặc định; kiểm tra thêm nếu có tùy chỉnh bằng mã |

### 6.1. Ứng dụng HTTPS, quản trị HTTP

Để biến đổi bài thử mục 5:

- Giữ nguyên toàn bộ `server` của ứng dụng.
- Đổi cổng quản trị sang `9091`.
- Thay khối `management.server.ssl` bằng khối tắt TLS; giữ địa chỉ quản trị cục bộ.

Đoạn `management.server` thay thế là:

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
    ssl:
      enabled: false
```

Đây là phần cấu hình cần thay trong cây hiện có; giữ các cấu hình bật/công bố health ở cùng mục `management`, không tạo hai khóa YAML `management:` trùng nhau.

URL quản trị lúc này:

```text
http://localhost:9091/actuator/health
```

Chứng thư của ứng dụng chính không mã hóa kết nối HTTP này. Nếu sau đó đưa cổng quản trị lên một mạng khác, phải đánh giá đúng chặng truyền không có TLS. Tài liệu Spring Boot có nêu rõ khả năng HTTPS ứng dụng kết hợp HTTP quản trị; việc framework hỗ trợ không thay thế quyết định triển khai. [Ví dụ SSL quản trị độc lập](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.configuring-management-specific-ssl).

### 6.2. Ứng dụng HTTP, quản trị HTTPS

Từ bài thử mục 5, đổi `server.port` thành `8080` và thay khối `server.ssl` bằng `enabled: false`. Giữ nguyên cổng 9443 và toàn bộ kho khóa/chứng thư quản trị.

Khi đó:

```text
Máy chủ nghiệp vụ: HTTP trên cổng 8080
Health quản trị:   https://localhost:9443/actuator/health
```

Dòng nghiệp vụ mô tả giao thức/cổng; các đường dẫn cụ thể do ứng dụng thực tế cung cấp. HTTPS quản trị không tự mã hóa kết nối tới cổng nghiệp vụ 8080.

Đổi các thuộc tính theo từng trường hợp độc lập rồi khởi động lại; không dán chồng mọi ví dụ trong bài thành một cấu hình.

### 6.3. Không có chuyển hướng HTTP tự động chỉ vì bật SSL

Khi đổi máy chủ chính sang HTTPS bằng cấu hình SSL, Spring Boot không tự duy trì thêm một cổng HTTP 8080 hay tự tạo chuyển hướng sang HTTPS. Muốn hai điểm tiếp nhận hoặc chuyển hướng, cần thiết kế riêng ở máy chủ/proxy. [Hướng dẫn cấu hình SSL cho máy chủ nhúng](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-ssl).

Tương tự, không gọi `http://localhost:9443` để thử một listener đã cấu hình HTTPS. Gửi HTTP thuần đến cổng TLS có thể bị từ chối hoặc sinh phản hồi khác tùy máy chủ; không gán một mã HTTP cố định cho mọi trường hợp sai giao thức.

## 7. Khi dùng SSL bundle hoặc máy chủ trung gian

### SSL bundle là cách đặt tên cho vật liệu TLS

Spring Boot 3.3 hỗ trợ các bộ vật liệu SSL có tên, cấu hình dưới `spring.ssl.bundle`, dùng định dạng kho khóa hoặc PEM. Khi dự án đã quản lý chúng, `server.ssl.bundle` và `management.server.ssl.bundle` cho phép chọn bộ dùng cho mỗi máy chủ.

Bài thực hành chọn thuộc tính PKCS12 trực tiếp để dễ theo dõi từng tệp. Với cùng một nhóm SSL, chọn cách cấu hình vật liệu nhất quán; không trộn bundle với các thuộc tính nguồn keystore/PEM trực tiếp như thể chúng tự hợp nhất. [Cấu hình SSL bundle](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html), [ràng buộc cấu hình SSL máy chủ](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-ssl).

### Phân biệt HTTPS phía ngoài với HTTPS tới JVM

Một hệ thống có thể có luồng:

```text
Công cụ quản trị --HTTPS--> proxy --HTTP hoặc HTTPS--> Spring Boot
```

HTTPS phía công cụ chỉ chứng minh chặng tới proxy được bảo vệ. Chặng proxy tới quản trị là HTTP hay HTTPS phụ thuộc cấu hình kết nối phía sau và listener Spring Boot.

Nếu proxy kết nối tới JVM bằng HTTPS, proxy cũng phải tin chứng thư của listener quản trị và dùng tên máy chủ phù hợp. Nếu proxy nối bằng HTTP, cấu hình chứng thư ở proxy không biến chặng sau thành HTTPS. [Lưu ý Spring Boot khi chạy sau proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server).

## 8. Tìm lỗi theo lớp

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Ứng dụng không khởi động khi đọc kho khóa | Tệp tồn tại, đường dẫn theo thư mục làm việc, loại kho, mật khẩu và alias |
| Báo không lấy được khóa riêng | Alias có mục khóa riêng không; mật khẩu mục khóa có đúng không |
| Không kết nối được tới cổng | Tiến trình đã chạy, địa chỉ lắng nghe, cổng và đường mạng |
| Bắt tay TLS thất bại | Đúng HTTPS chưa; máy chủ có cấu hình TLS/khóa phù hợp không |
| Khách không tin chứng thư | Chuỗi chứng thư và nguồn tin cậy phía khách |
| Lỗi tên máy chủ | URL có tên/IP được chứng thư SAN bao phủ không |
| TLS thành công nhưng HTTP 401/403 | Xác thực và phân quyền HTTP hoặc bộ lọc bảo vệ |
| TLS thành công nhưng HTTP 404 | Cổng, đường dẫn và quyết định bật/công bố endpoint |
| Health trả trạng thái không khỏe | Kiểm tra tình trạng thành phần, không chỉ cấu hình TLS |

Đừng sửa lỗi chứng thư bằng cách thêm endpoint vào danh sách công bố. Ngược lại, chứng thư hợp lệ không tạo ra một endpoint đang bị tắt hoặc chưa được công bố.

HTTPS bảo vệ kết nối và giúp khách xác minh danh tính máy chủ; phân quyền vào các thao tác quản trị là một yêu cầu riêng. Nếu cần mTLS, còn phải cấu hình yêu cầu chứng thư khách và nguồn tin cậy phía máy chủ, rồi kiểm tra cả hai chiều.

## 9. Tự kiểm tra quan hệ giữa hai máy chủ

**Câu 1.** Chỉ đặt `management.server.port=9443`, số cổng có chứng minh endpoint là HTTPS không?

**Đáp án:** Không. Phải xác định cấu hình SSL hiệu lực và nơi kết thúc TLS.

**Câu 2.** Ứng dụng và Actuator dùng chung cổng 8443. Có thể dùng `management.server.ssl.*` để đổi riêng chứng thư của đường dẫn `/actuator/health` không?

**Đáp án:** Không theo cơ chế SSL quản trị riêng này. TLS thuộc listener dùng chung; muốn cấu hình quản trị độc lập, dùng cổng quản trị khác.

**Câu 3.** Cả hai cổng dùng hai chứng thư tự ký khác nhau. Curl gọi cổng 9443 cần tin chứng thư nào?

**Đáp án:** Chứng thư quản trị `management-local.crt` trong bài thử, đồng thời tên/IP URL phải phù hợp SAN. Việc tin chứng thư ứng dụng không tự tạo quan hệ tin cậy với chứng thư tự ký khác.

**Câu 4.** HTTPS quản trị đã hoạt động nhưng khách nhận HTTP 403 khi gọi một thao tác.

**Đáp án:** Kết nối đã đi qua TLS để có phản hồi HTTP; cần xét quyền truy cập và các bộ lọc liên quan thay vì chỉ đổi kho khóa.

**Câu 5.** Truy cập được qua `--insecure` có đủ chứng minh cấu hình tin cậy và tên chứng thư đúng không?

**Đáp án:** Chưa. Bài kiểm tra đạt mục tiêu phải xác minh chứng thư, chẳng hạn dùng đúng `--cacert` trong môi trường thử đã mô tả.
