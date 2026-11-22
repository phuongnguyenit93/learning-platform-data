# Properties và YAML cho gRPC trong Spring Boot

## 1. Vai trò của properties trong tích hợp gRPC

Một ứng dụng **SPRING_GRPC** có thể vừa mở gRPC server vừa gọi nhiều remote gRPC service. Những thông tin thay đổi theo môi trường như port, target, TLS certificate, trust store và các tuỳ chọn transport cần được đưa ra cấu hình thay vì gắn cứng trong Java code.

Spring Boot đọc cấu hình từ YAML/properties, hợp nhất nhiều nguồn và bind chúng vào các đối tượng cấu hình. gRPC starter tận dụng cơ chế đó để thiết lập server và client. Vì vậy, người phát triển cần hiểu ba lớp:

1. **Cú pháp YAML:** cấu trúc phân cấp, kiểu dữ liệu, indentation và placeholder.
2. **Tên property:** namespace server/client và tên client logic mà starter công bố.
3. **Binding và nguồn giá trị:** cách Spring chuyển cấu hình thành giá trị runtime, cùng thứ tự ưu tiên giữa file, profile, environment và command line.

Bài này tập trung vào **Properties và YAML cho gRPC**. Ví dụ sử dụng **`net.devh:grpc-server-spring-boot-starter`** và **`net.devh:grpc-client-spring-boot-starter`**, với prefix `grpc.server.*` và `grpc.client.<name>.*`. Spring gRPC chính thức có hệ property và cấu hình riêng; luôn đối chiếu reference của đúng starter/version đang dùng. Không trộn tên property giữa hai hệ.

## 2. YAML là cấu trúc dữ liệu

YAML biểu diễn object bằng indentation. Với Spring Boot, các key phân cấp thường ánh xạ thành property dạng dấu chấm.

Ví dụ:

```yaml
grpc:
  server:
    port: 9090
  client:
    inventory:
      address: "static://inventory.internal:9090"
      negotiationType: TLS
```

Có thể hiểu tương đương với các property:

- `grpc.server.port = 9090`
- `grpc.client.inventory.address = static://inventory.internal:9090`
- `grpc.client.inventory.negotiationType = TLS`

Các dòng có cùng cấp indentation là các thành viên cùng object. YAML dùng khoảng trắng, không dùng tab để thụt lề. Một cấp lồng sâu hơn phải thụt thêm số spaces nhất quán; sai indentation có thể khiến YAML parse lỗi hoặc cấu trúc bị bind khác dự kiến.

### 2.1. Kiểu dữ liệu

| Giá trị YAML | Kiểu thường được parse | Cách dùng |
| --- | --- | --- |
| `9090` | Số nguyên | Port, số lượng |
| `true` / `false` | Boolean | Bật/tắt tính năng |
| `"static://host:9090"` | Chuỗi | Address, URI, enum-like value |
| `null` hoặc `~` | Null | Không nên dùng thay cho giá trị bắt buộc |
| `[a, b]` | Danh sách | Các giá trị có thứ tự nếu property hỗ trợ |
| Khối lồng nhau | Map/object | Nhóm server, client theo tên |

Các trường dạng URI, hostname, enum hoặc giá trị có ký tự đặc biệt nên đặt trong dấu nháy để thể hiện rõ ý định là chuỗi. Không đặt port trong dấu nháy nếu property mong đợi số nguyên, trừ khi tài liệu starter yêu cầu chuỗi.

Ví dụ:

```yaml
grpc:
  server:
    port: 9090
  client:
    inventory:
      address: "dns:///inventory.internal:9090"
      negotiationType: "TLS"
```

Tránh các dạng dễ gây nhầm kiểu:

- `port: "9090"` khi property yêu cầu integer.
- `enabled: "true"` khi property yêu cầu boolean.
- `address:` để trống trong khi client bắt buộc phải có target.
- Dùng tab để thụt lề hoặc đặt key trùng nhau ở cùng cấp.

## 3. Hai namespace chính: server và client

Với starter net.devh, cấu hình server và client được tách thành hai nhánh:

```text
grpc
├── server
│   ├── port
│   ├── address / security / các thuộc tính server được hỗ trợ
│   └── ...
└── client
    ├── inventory
    │   ├── address
    │   ├── negotiationType
    │   └── security / các thuộc tính client được hỗ trợ
    └── payment
        ├── address
        └── ...
```

**`grpc.server.*`** áp dụng cho gRPC server do server starter quản lý. **`grpc.client.<name>.*`** áp dụng cho một client/channel có tên logic. Chúng không thay thế `server.port` của Spring Web và cũng không thay thế `management.server.port` của Actuator.

### 3.1. Server properties

Một cấu hình server cơ bản:

```yaml
grpc:
  server:
    port: 9090
```

Có thể thêm TLS khi triển khai:

```yaml
grpc:
  server:
    port: 9090
    security:
      enabled: true
      certificateChain: "file:/run/secrets/grpc/server.crt"
      privateKey: "file:/run/secrets/grpc/server.key"
```

Tên property minh họa theo net.devh; định dạng resource và các trường bảo mật cần xác minh trong reference của version đang dùng. Đường dẫn phải tồn tại và tiến trình phải đọc được. Không lưu private key thật trong repository.

Nếu ứng dụng có cả HTTP và gRPC server, khai báo hai port riêng:

```yaml
server:
  port: 8080

grpc:
  server:
    port: 9090
```

Ở đây `server.port` là HTTP listener nếu ứng dụng có web stack; `grpc.server.port` là gRPC listener của starter. Chỉ đổi một giá trị không tự đổi giá trị còn lại.

### 3.2. Client properties theo tên

Mỗi remote client nằm dưới một key tên riêng:

```yaml
grpc:
  client:
    inventory:
      address: "dns:///inventory.internal:9090"
      negotiationType: TLS
    payment:
      address: "dns:///payment.internal:9090"
      negotiationType: TLS
```

Tên `inventory` và `payment` là **client name** dùng để liên kết cấu hình với injection point tương ứng, ví dụ `@GrpcClient("inventory")`. Tên này không bắt buộc phải trùng package Protobuf, tên class Java hoặc DNS hostname.

Nếu hai backend có target hoặc security policy khác nhau, nên có hai client name. Không gom chúng vào một cấu hình chung rồi dùng chung channel nếu chính sách kết nối khác nhau.

## 4. Định dạng address và negotiation type

### 4.1. Address là target logic

Ví dụ thường gặp:

| Address | Mục đích |
| --- | --- |
| `static://localhost:9090` | Endpoint cố định cho local |
| `static://inventory.internal:9090` | Endpoint cố định theo hostname |
| `dns:///inventory.internal:9090` | Dùng DNS resolver của gRPC Java nếu runtime hỗ trợ |
| `in-process:inventory-test` | In-process transport khi starter/version hỗ trợ |

Không phải scheme nào cũng được mọi starter hỗ trợ. Scheme cần có resolver tương ứng trên runtime classpath. Nếu client khởi tạo được nhưng không phân giải target, kiểm tra scheme và name resolver trước khi sửa RPC method.

Tránh ghi cứng IP của pod hoặc container ngắn hạn. Trong môi trường orchestration, thường nên dùng DNS/service name ổn định hoặc resolver tích hợp discovery.

### 4.2. Negotiation type

Với net.devh, các cấu hình thường gặp là `PLAINTEXT` và `TLS`:

```yaml
grpc:
  client:
    inventory:
      address: "static://localhost:9090"
      negotiationType: PLAINTEXT
```

`PLAINTEXT` phù hợp cho local loopback hoặc môi trường test được cô lập. Khi gọi qua mạng không tin cậy, dùng TLS và cấu hình trust certificate phù hợp:

```yaml
grpc:
  client:
    inventory:
      address: "dns:///inventory.internal:9090"
      negotiationType: TLS
      security:
        trustCertCollection: "file:/run/secrets/grpc/inventory-ca.crt"
```

Client phải xác minh certificate chain và hostname/SAN của server. Không tắt xác minh hoặc dùng trust-all để làm cho kết nối thành công. Nếu dùng mTLS, cần thêm certificate/key phía client và trust policy phía server theo đúng API starter.

## 5. Placeholder và biến môi trường

Không nên tạo một file YAML khác nhau bằng cách sửa endpoint thủ công trước mỗi lần deploy. Spring Boot hỗ trợ placeholder để lấy giá trị từ Environment:

```yaml
grpc:
  server:
    port: ${GRPC_SERVER_PORT:9090}
  client:
    inventory:
      address: "${INVENTORY_GRPC_ADDRESS:static://localhost:9091}"
      negotiationType: ${INVENTORY_GRPC_NEGOTIATION:PLAINTEXT}
```

Cú pháp:

- `${GRPC_SERVER_PORT:9090}`: dùng biến `GRPC_SERVER_PORT`; nếu không có thì dùng `9090`.
- `${INVENTORY_GRPC_ADDRESS:...}`: lấy target từ environment, fallback sang target local.
- `${INVENTORY_GRPC_NEGOTIATION:PLAINTEXT}`: lấy negotiation mode từ environment hoặc dùng mặc định.

Fallback chỉ nên tồn tại khi giá trị mặc định thực sự an toàn. Ví dụ, fallback plaintext hoặc localhost có thể tiện cho local nhưng nguy hiểm nếu production quên cấp biến môi trường. Với giá trị bắt buộc ở production, có thể bỏ default để ứng dụng fail-fast khi thiếu.

### 5.1. Tên biến môi trường

Spring Boot hỗ trợ relaxed binding. Dạng property:

`grpc.client.inventory.address`

thường được biểu diễn trong environment bằng:

`GRPC_CLIENT_INVENTORY_ADDRESS`

Tương tự:

| Property | Environment variable thường dùng |
| --- | --- |
| `grpc.server.port` | `GRPC_SERVER_PORT` |
| `grpc.client.inventory.address` | `GRPC_CLIENT_INVENTORY_ADDRESS` |
| `grpc.client.inventory.negotiationType` | `GRPC_CLIENT_INVENTORY_NEGOTIATIONTYPE` |

Quy tắc chuyển đổi tên của Spring Boot bao gồm đổi dấu chấm thành underscore, bỏ dấu gạch nối và viết hoa. Với map key và tên client, cần kiểm tra binding thực tế theo version; giữ tên client đơn giản như `inventory`, `payment` giúp tránh vấn đề chuyển đổi không cần thiết.

Không đặt giá trị bí mật trực tiếp vào command line nếu process list hoặc logging của môi trường có thể để lộ tham số. Dùng secret store hoặc file secret mount phù hợp.

## 6. Cấu hình nhiều môi trường mà không lặp YAML

Có thể giữ cấu trúc ổn định trong `application.yml`, rồi ghi đè các giá trị thay đổi trong file profile.

Cấu hình chung:

```yaml
spring:
  application:
    name: order-service

grpc:
  server:
    port: ${GRPC_SERVER_PORT:9090}
```

Cấu hình local:

```yaml
grpc:
  client:
    inventory:
      address: "static://localhost:9091"
      negotiationType: PLAINTEXT
```

Cấu hình production:

```yaml
grpc:
  client:
    inventory:
      address: ${INVENTORY_GRPC_ADDRESS}
      negotiationType: TLS
      security:
        trustCertCollection: "file:${INVENTORY_GRPC_CA_PATH}"
```

Profile chọn tập giá trị phù hợp; Environment variables và command-line arguments vẫn có thể ghi đè file profile theo thứ tự ưu tiên của Spring Boot. Không giả định file `application-prod.yml` luôn thắng mọi nguồn cấu hình khác.

Chỉ lặp những property thực sự khác nhau. Nếu cùng một `grpc.client.inventory.negotiationType` được khai báo trong base, local và prod, hãy bảo đảm mỗi lần ghi đè là có chủ đích. Tránh cấu hình mặc định chung làm production vô tình kết nối plaintext.

## 7. Các property bổ sung: chỉ cấu hình khi cần

gRPC starter có thể cung cấp các nhóm tuỳ chọn cho TLS, message size, keepalive, interceptor, executor hoặc shutdown. Tên và kiểu của chúng thay đổi theo version. Trước khi thêm property:

1. Kiểm tra đúng artifact/version đang chạy.
2. Đối chiếu tên property trong reference configuration hoặc metadata của starter.
3. Xác định kiểu mong đợi: integer, boolean, enum, duration hay resource path.
4. Kiểm tra giá trị mặc định và tác động đến server/client.
5. Thay đổi từng nhóm và đo kết quả.

Một số ví dụ về **kiểu dữ liệu** trong cấu hình Spring Boot nói chung:

```yaml
app:
  rpc:
    request-timeout: 800ms
    shutdown-grace-period: 20s
    max-payload-size: 4MB
    tracing-enabled: true
```

Đây là các property ứng dụng tự định nghĩa để minh họa `Duration`, `DataSize` và boolean; **không phải** khẳng định net.devh tự nhận các key `app.rpc.*`. Nếu dùng `@ConfigurationProperties`, khai báo kiểu Java tương ứng và validation cho các giá trị bắt buộc. Không sao chép tên ví dụ này vào `grpc.*` rồi kỳ vọng starter hiểu chúng.

Keepalive không thay thế deadline của RPC; tăng message size không thay thế kiểm soát bộ nhớ; bật tracing không tự động bảo đảm trace context được truyền nếu thiếu instrumentation/interceptor.

## 8. Kiểm tra cấu hình đã bind

Khi YAML hợp lệ nhưng server/client chạy sai, hãy kiểm tra giá trị **được bind thực tế**:

- Active profiles: ứng dụng đang dùng `local`, `test` hay `prod`?
- `grpc.server.port`: listener gRPC đang nhận cấu hình nào?
- `grpc.client.inventory.address`: target cuối cùng là gì?
- `grpc.client.inventory.negotiationType`: plaintext hay TLS?
- Các đường dẫn certificate/CA có tồn tại và đọc được không?

Có thể kiểm tra từ code bằng `Environment` trong môi trường test:

```java
@Autowired
Environment environment;

@Test
void usesTestInventoryTarget() {
    assertEquals(
        "in-process:inventory-test",
        environment.getProperty("grpc.client.inventory.address")
    );
}
```

Ví dụ assertion này chỉ phù hợp nếu test thật sự khai báo target đó. Có thể dùng `@ConfigurationProperties`/`@ConfigurationPropertiesScan` cho cấu hình do ứng dụng sở hữu; với property của starter, nên kiểm tra bean/configuration do starter cung cấp hoặc đọc `Environment` để tránh tự tạo một object không liên kết với cấu hình thật.

Spring Boot Actuator có endpoint `env` và `configprops` nếu được bật, giúp truy nguồn property và xem giá trị đã bind. Các endpoint này có thể tiết lộ cấu hình nhạy cảm; chỉ mở trong môi trường quản trị được bảo vệ, và không công khai secret.

## 9. Những lỗi YAML và binding thường gặp

| Triệu chứng | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| YAML không parse | Indentation sai, tab hoặc dấu nháy không đóng | Kiểm tra cấu trúc YAML và line báo lỗi |
| Port không đổi | Sai namespace, profile chưa bật hoặc nguồn khác ghi đè | Xem effective `grpc.server.port` |
| Client không nhận target | Sai tên client hoặc sai cấp lồng `grpc.client` | Đối chiếu `@GrpcClient("name")` với key YAML |
| Address bị parse sai | Thiếu quote hoặc placeholder không được resolve | Xem kiểu và giá trị cuối trong Environment |
| `UNAVAILABLE` | Target, DNS, port hoặc transport không đúng | Kiểm tra target thực tế và network |
| TLS handshake thất bại | CA/SAN/hostname hoặc negotiation không khớp | Kiểm tra certificate và trust chain |
| Property không có tác dụng | Starter/version không hỗ trợ key đó | Tra reference configuration đúng version |
| Production dùng plaintext ngoài ý muốn | Kế thừa fallback local hoặc profile chồng chéo | Bỏ fallback nguy hiểm và kiểm tra active profiles |
| Giá trị duration không hợp lệ | Property mong integer hoặc duration nhưng format sai | Đối chiếu kiểu Java và cú pháp được hỗ trợ |

Lỗi cú pháp YAML thường làm ứng dụng thất bại ngay khi khởi tạo Environment. Lỗi binding có thể xuất hiện khi starter tạo bean. Còn target sai hoặc TLS mismatch thường chỉ bộc lộ khi channel kết nối hoặc RPC được gọi. Phân biệt các giai đoạn này giúp điều tra đúng tầng.

## 10. Quy trình viết và rà soát YAML gRPC

1. Xác định starter và version, dùng đúng namespace property.
2. Tách server properties khỏi client properties; đặt mỗi remote dưới client name riêng.
3. Chọn kiểu YAML phù hợp: số cho port, boolean cho cờ, chuỗi có quote cho URI/enum.
4. Dùng placeholder cho endpoint/secret thay đổi theo môi trường.
5. Không để plaintext hoặc localhost làm fallback production.
6. Chọn profile và kiểm tra property precedence.
7. Xác minh các key thực sự được starter bind; không đoán tên property từ tên Java field.
8. Khởi động server, thực hiện RPC client thật và kiểm tra TLS/status.
9. Kiểm tra log/metrics nhưng không ghi token, private key hoặc payload nhạy cảm.

Khi cấu hình đúng, YAML thể hiện rõ **server nghe ở đâu, mỗi client gọi target nào, transport được bảo vệ ra sao và giá trị đến từ môi trường nào**. Điều này giúp nhóm phát triển thay đổi endpoint và chính sách kết nối mà không sửa business code, đồng thời làm lỗi cấu hình dễ phát hiện trước khi ứng dụng nhận traffic.
