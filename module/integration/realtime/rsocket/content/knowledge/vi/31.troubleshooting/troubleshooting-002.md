# SETUP bị từ chối do MIME type, phiên bản hoặc chính sách truy cập

Khi client RSocket mở kết nối, nó gửi frame `SETUP` để khai báo phiên bản giao thức, cấu hình keepalive, MIME type của data và metadata, cùng dữ liệu/metadata khởi tạo nếu có. Server có thể chấp nhận hoặc từ chối SETUP trước khi client được phép gửi các tương tác nghiệp vụ. Vì vậy, lỗi xuất hiện ngay lúc `connectTcp(...)` hoặc `connectWebSocket(...)` thường cần được chẩn đoán ở ranh giới thiết lập phiên, không nên xử lý như lỗi của một route `@MessageMapping`.

Trong module `INTEGRATION_REALTIME_RSOCKET`, Spring Boot và `RSocketRequester` giúp tạo client/server reactive qua TCP hoặc WebSocket. Bài viết này tập trung vào ba nhóm nguyên nhân thường gặp khiến SETUP bị từ chối: MIME type không được hỗ trợ hoặc khai báo sai, protocol version không tương thích và chính sách truy cập/authentication không chấp nhận thông tin khởi tạo. Cũng cần phân biệt lỗi SETUP thật với lỗi codec hoặc authorization chỉ xuất hiện sau khi phiên đã được thiết lập.

## 1. SETUP làm gì trước khi có request nghiệp vụ?

SETUP là frame đầu tiên dùng để khởi tạo một logical RSocket connection. Nó cung cấp các thông tin nền tảng để hai phía hiểu cách trao đổi payload trong phiên:

- **Protocol version:** major/minor version của RSocket protocol mà client sử dụng.
- **Keepalive settings:** khoảng gửi KEEPALIVE và thời gian sống tối đa mà peer được kỳ vọng phản hồi.
- **Data MIME type:** định dạng mặc định của payload data, ví dụ JSON, CBOR hoặc Protobuf.
- **Metadata MIME type:** định dạng metadata mặc định, ví dụ composite metadata hoặc một kiểu metadata cụ thể.
- **Setup data:** dữ liệu khởi tạo tùy chọn của ứng dụng.
- **Setup metadata:** metadata khởi tạo tùy chọn, có thể chứa thông tin authentication hoặc context phiên theo hợp đồng hai phía.

Trình tự tổng quát:

```text
RSocket client                         RSocket server
     |                                       |
     |------ SETUP ------------------------->|
     |       protocol version                |
     |       data/metadata MIME type         |
     |       keepalive                       |
     |       setup data/metadata             |
     |                                       |
     |                         kiểm tra version, MIME,
     |                         metadata và access policy
     |                                       |
     |<----- SETUP success / rejection ------|
     |                                       |
     |------ request frames sau setup ------>|
```

Nếu SETUP bị từ chối, các route như `devices.status.get` chưa được xử lý. Nếu SETUP thành công nhưng request đầu tiên lỗi decode hoặc authorization, đó là giai đoạn xử lý payload/request và cần một nhánh chẩn đoán khác.

## 2. Phân biệt lỗi transport, SETUP và request

Trước khi thay đổi MIME type hoặc token, hãy xác định lỗi xảy ra ở giai đoạn nào.

| Giai đoạn | Dấu hiệu thường thấy | Nhóm cần kiểm tra |
|---|---|---|
| TCP connect | Connection refused, DNS failure, connect timeout | Host/port, firewall, service discovery, server listener. |
| WebSocket handshake | HTTP 404/400/401/403/426, TLS error, không nhận `101 Switching Protocols` | URL/path, WSS certificate, proxy Upgrade, Origin, cookie/handshake policy. |
| RSocket SETUP | Server gửi lỗi setup/rejection hoặc đóng phiên ngay sau SETUP | Protocol version, MIME type, setup metadata/data, authentication và access policy. |
| Request đầu tiên | SETUP đã thành công; request lỗi decode, route hoặc authorization | Codec, payload MIME, route metadata, request-level security. |
| Stream đang chạy | Một số phần tử đã được nhận rồi stream lỗi/đóng | Application error, timeout, cancellation, connection loss hoặc backpressure. |

Không kết luận mọi lỗi `connect...()` đều do SETUP. Ví dụ `connectWebSocket(...)` có thể thất bại trước khi RSocket frame được gửi vì proxy không hỗ trợ Upgrade hoặc TLS certificate không hợp lệ.

## 3. Đọc đúng mã lỗi SETUP

RSocket protocol phân biệt các lỗi ở cấp kết nối với lỗi của một stream. Một số mã lỗi connection-level liên quan tới thiết lập phiên:

| Mã lỗi protocol | Tên | Ý nghĩa tổng quát |
|---|---|---|
| `0x00000001` | `INVALID_SETUP` | SETUP không hợp lệ theo cấu trúc hoặc ràng buộc giao thức. |
| `0x00000002` | `UNSUPPORTED_SETUP` | Server không hỗ trợ một phần cấu hình SETUP được yêu cầu. |
| `0x00000003` | `REJECTED_SETUP` | Server chủ động từ chối thiết lập phiên. |
| `0x00000004` | `REJECTED_RESUME` | Server không chấp nhận yêu cầu Resume; đây không phải lỗi SETUP mới thông thường. |

Mã cụ thể và cách thư viện ánh xạ thành exception có thể khác nhau theo implementation/version. Khi chẩn đoán, ghi lại error code, error type và giai đoạn phát sinh. Không chỉ dựa vào chuỗi message của exception.

Một số lỗi như application authorization có thể được biểu diễn thành application error trên một request sau khi SETUP thành công, thay vì `REJECTED_SETUP`. Nếu client nhận được lỗi từ route sau khi kết nối đã hoạt động, hãy kiểm tra request-level authentication/authorization trước khi thay protocol version.

## 4. MIME type: phân biệt data và metadata

Một trong các lỗi cấu hình phổ biến là client và server không thống nhất MIME type hoặc không có codec tương ứng. Cần phân biệt hai trường trong SETUP:

| Trường | Vai trò | Ví dụ |
|---|---|---|
| Data MIME type | Cách encode/decode payload data | `application/json`, `application/cbor`, `application/x-protobuf` |
| Metadata MIME type | Cách diễn giải vùng metadata | `message/x.rsocket.composite-metadata.v0` hoặc MIME type metadata phù hợp |

Data MIME type không phải MIME type của routing metadata. Nếu dùng composite metadata, container composite có thể chứa nhiều entry có MIME type riêng, ví dụ routing metadata hoặc authentication metadata. Đừng đổi data MIME type thành routing MIME type chỉ vì request cần route.

### 4.1. Dấu hiệu MIME type không tương thích

- Server từ chối ngay SETUP vì MIME type khai báo không nằm trong danh sách được hỗ trợ.
- SETUP thành công nhưng request đầu tiên lỗi decode vì server không có decoder cho data MIME type.
- Route hoặc authentication metadata không được đọc vì metadata MIME type/container sai.
- Server nhận metadata như một blob opaque trong khi ứng dụng kỳ vọng composite metadata.
- Client gửi Protobuf nhưng server cố decode JSON, hoặc ngược lại.
- MIME string có typo, sai chữ hoa/thường theo quy ước implementation hoặc khác với MIME type mà codec đăng ký.

Điểm quan trọng: không phải mọi codec mismatch đều dẫn tới SETUP rejection. SETUP có thể chỉ công bố MIME type; tùy server/acceptor và policy, việc kiểm tra hỗ trợ có thể xảy ra lúc thiết lập hoặc chỉ khi decode request đầu tiên. Hãy dùng thời điểm lỗi và server log để xác định chính xác.

### 4.2. Ví dụ cấu hình JSON thống nhất

Client Spring có thể khai báo data MIME type rõ ràng:

```java
RSocketRequester.Builder builder = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON);

Mono<RSocketRequester> requesterMono = builder
    .connectTcp("rsocket-service", 7000);
```

Server phải có JSON encoder/decoder tương ứng trong `RSocketStrategies`. Với Spring Boot, codec mặc định có thể được cấu hình theo classpath và auto-configuration; nếu tùy chỉnh strategies, cần bảo đảm Jackson JSON encoder/decoder được đăng ký ở cả hai phía.

Ví dụ cấu hình strategies minh họa:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
    .build();
```

Tên package/class và cấu hình mặc định cần khớp phiên bản Spring Framework trong dự án. Không thêm codec trùng lặp một cách tùy tiện nếu Spring Boot đã đăng ký codec đó.

### 4.3. Ví dụ CBOR hoặc Protobuf

Nếu client dùng CBOR, hai phía cần thống nhất `application/cbor` và có CBOR encoder/decoder. Nếu dùng Protobuf, hai phía cần thống nhất MIME type Protobuf và generated message tương thích schema.

```java
MimeType cborMime = MimeTypeUtils.parseMimeType("application/cbor");

RSocketRequester.Builder cborBuilder = RSocketRequester.builder()
    .dataMimeType(cborMime);
```

```java
MimeType protobufMime =
    MimeTypeUtils.parseMimeType("application/x-protobuf");

RSocketRequester.Builder protobufBuilder = RSocketRequester.builder()
    .dataMimeType(protobufMime);
```

Hai đoạn trên chỉ cấu hình MIME type. Chúng không tự đăng ký codec. Cần thêm encoder/decoder tương ứng vào `RSocketStrategies` ở client và server, rồi kiểm tra generated class/schema hoặc object model được sử dụng.

### 4.4. Composite metadata và routing

Nếu ứng dụng dùng routing metadata cùng authentication metadata trong một payload, hai phía phải thống nhất metadata container. Một cấu hình thường gặp là composite metadata MIME type:

```java
MimeType compositeMetadata = MimeTypeUtils.parseMimeType(
    "message/x.rsocket.composite-metadata.v0");

RSocketRequester.Builder builder = RSocketRequester.builder()
    .metadataMimeType(compositeMetadata);
```

Routing metadata là một entry bên trong composite metadata, không phải data MIME type. Nếu client gửi raw routing metadata nhưng server đang chờ composite metadata, server có thể không đọc được route hoặc metadata entry. Cần xác nhận cách encode/decode của thư viện client/server đang dùng.

## 5. Protocol version không phải application schema version

SETUP mang protocol version của RSocket. Cần phân biệt ít nhất ba loại version:

| Version | Ví dụ | Ảnh hưởng |
|---|---|---|
| RSocket protocol version | Major/minor trong SETUP | Quyết định hai implementation có hiểu framing/semantics kết nối hay không. |
| Library version | Phiên bản `rsocket-core`, Spring Framework, RSocket JS | Quyết định API và khả năng triển khai protocol/features. |
| Application schema/API version | `telemetry.v1`, Protobuf schema hoặc DTO version | Quyết định cách hiểu payload nghiệp vụ sau khi kết nối. |

Không thể sửa protocol version mismatch bằng cách đổi tên route hoặc tăng version DTO. Ngược lại, nếu SETUP thành công nhưng Protobuf decode lỗi do field/schema không tương thích, đó không nhất thiết là protocol version mismatch.

### 5.1. Khi major/minor protocol version không tương thích

Nếu client và server không có protocol version tương thích theo implementation, server có thể từ chối SETUP hoặc đóng kết nối. Cần kiểm tra:

- Phiên bản RSocket client và server đang chạy thực tế, không chỉ phiên bản khai báo trong source.
- Các dependency `rsocket-core`, transport và Spring integration có được căn chỉnh tương thích không.
- Client JS có dùng protocol version/feature set mà server hỗ trợ không.
- Server đã nâng cấp hoặc rollback gần thời điểm lỗi chưa.
- Có proxy/gateway đang terminate hoặc chuyển đổi protocol ở giữa không.

Không tự ép protocol version bằng cách sửa frame hoặc hạ version tùy tiện. Nâng/hạ các thư viện theo bộ phiên bản tương thích, rồi chạy kiểm thử client-server trước khi triển khai.

### 5.2. Library mismatch và dependency conflict

Một ứng dụng có thể biên dịch thành công nhưng runtime classpath chứa nhiều phiên bản RSocket/Reactor không tương thích do dependency transitive. Dấu hiệu có thể là lỗi khởi tạo, `NoSuchMethodError`, `ClassNotFoundException`, lỗi codec hoặc hành vi handshake khác giữa môi trường local và production.

Kiểm tra dependency tree bằng công cụ build của dự án ở bước chẩn đoán riêng; xác nhận Spring Framework, Spring Boot, RSocket Java, Reactor và transport module thuộc một tập phiên bản được hỗ trợ. Không ghép tùy ý một `rsocket-core` mới với transport hoặc Spring integration cũ.

## 6. SETUP bị từ chối bởi authentication hoặc access policy

Server có thể yêu cầu client xác thực ngay khi mở logical connection. Khi đó, thông tin xác thực có thể được gửi trong SETUP metadata theo hợp đồng bảo mật của ứng dụng. Một số nguyên nhân thường gặp:

- Thiếu authentication metadata trong SETUP.
- Metadata MIME type của authentication không đúng hoặc không được server decoder hỗ trợ.
- Token hết hạn, sai issuer/audience, chữ ký không hợp lệ hoặc không đúng tenant.
- Server yêu cầu một authentication scheme nhưng client gửi scheme khác.
- Principal hợp lệ nhưng không được phép mở loại session/transport này.
- Policy từ chối client theo tenant, network, Origin hoặc trạng thái tài khoản.
- Đồng hồ client/server lệch khiến token chưa có hiệu lực hoặc đã hết hạn theo kiểm tra thời gian.

### 6.1. Authentication ở SETUP và authentication ở từng request

Hai cách triển khai có thời điểm kiểm tra khác nhau:

| Cách xác thực | Thời điểm | Lỗi thường thấy |
|---|---|---|
| Connection-level authentication | Trong SETUP hoặc ngay khi tạo session | Kết nối bị từ chối trước request nghiệp vụ. |
| Request-level authentication | Metadata của từng request sau SETUP | Kết nối mở thành công; request cụ thể bị từ chối. |

Nếu server yêu cầu connection-level auth, client phải gửi credential đúng vị trí và MIME type ngay trong SETUP. Nếu auth được thiết kế cho từng request, không nên mặc định SETUP rejection là do token của request đầu tiên.

Ví dụ khái niệm với Spring requester:

```java
MimeType authenticationMime = MimeTypeUtils.parseMimeType(
    "message/x.rsocket.authentication.v0");

RSocketRequester.Builder builder = RSocketRequester.builder()
    .setupMetadata(authenticationMetadata, authenticationMime);
```

`authenticationMetadata` là object được encoder tương ứng hỗ trợ, ví dụ bearer-token metadata theo contract của hệ thống. Đoạn code không chứa token thật. Server cần đăng ký decoder/converter và authentication handler tương ứng. Nếu dùng composite metadata, authentication entry phải được encode đúng trong composite container.

Không gửi password/token trong setup data dạng text hoặc trong route. Dùng authentication metadata đã được định dạng theo cơ chế bảo mật của hai phía và chỉ truyền qua transport được bảo vệ bằng TLS.

### 6.2. Access policy không nhất thiết là lỗi SETUP

Một số chính sách được áp dụng ở connection-level, một số chỉ áp dụng khi client gọi route. Ví dụ:

- Chặn client theo danh tính hoặc tenant ngay lúc SETUP: có thể dẫn tới setup rejection.
- Cho phép kết nối nhưng chặn `admin.device.shutdown`: SETUP thành công, request tới route bị access denied.
- WebSocket Origin không hợp lệ: proxy/server có thể từ chối HTTP handshake trước khi RSocket SETUP được gửi.
- Token trong SETUP hợp lệ nhưng hết hạn trong phiên: request sau đó có thể bị từ chối nếu server kiểm tra lại token/credential theo policy.

Hãy xác định lớp policy đang từ chối: HTTP handshake, RSocket SETUP, authentication của request hay authorization của route. Sửa sai lớp sẽ không giải quyết được lỗi và có thể vô tình nới lỏng bảo mật.

## 7. Quy trình chẩn đoán theo thứ tự

Thực hiện các bước sau để khoanh vùng lỗi mà không thay đổi nhiều cấu hình cùng lúc.

### Bước 1: Xác nhận transport đã kết nối

- Với TCP, kiểm tra DNS, host, port, firewall và server listener.
- Với WebSocket, kiểm tra URL/path, TLS certificate, proxy Upgrade và HTTP status.
- Xác nhận client thực sự gửi RSocket SETUP sau khi transport được mở.

Nếu chưa có transport connection, chưa cần điều tra codec hoặc route.

### Bước 2: Ghi nhận SETUP error code và thời điểm

- Thu thập loại exception, error code và thời điểm client nhận lỗi.
- Đối chiếu server log cùng correlation/connection ID.
- Phân biệt `INVALID_SETUP`, `UNSUPPORTED_SETUP`, `REJECTED_SETUP` với application error trên request.
- Không log raw SETUP metadata hoặc token để tìm nguyên nhân.

### Bước 3: So sánh protocol version và thư viện

- Xác định protocol version mà client/server thực sự sử dụng.
- Kiểm tra bộ dependency runtime và transport module.
- Xác nhận hai đầu hỗ trợ cùng protocol/features cần dùng.
- Nếu vừa deploy, kiểm tra node nào đang chạy phiên bản cũ/mới.

### Bước 4: So sánh data MIME type

- Ghi MIME type client khai báo trong SETUP.
- Kiểm tra server có encoder/decoder tương ứng không.
- Xác nhận JSON/CBOR/Protobuf được cấu hình giống nhau.
- Kiểm tra lỗi xảy ra ngay lúc SETUP hay chỉ khi decode payload đầu tiên.

### Bước 5: So sánh metadata MIME type và entry

- Xác định client gửi composite metadata hay metadata đơn.
- Xác nhận server hỗ trợ đúng container và MIME type của từng entry.
- Kiểm tra routing/authentication entry được encode đúng.
- Không nhầm route metadata với data MIME type.

### Bước 6: Kiểm tra authentication/access policy

- Xác nhận credential có được gửi trong đúng vị trí không.
- Kiểm tra authentication scheme, issuer, audience, expiry và clock skew.
- Kiểm tra tenant/principal và policy mở connection.
- Nếu WebSocket, kiểm tra Origin ở HTTP handshake riêng.
- Phân biệt authentication tại SETUP với authorization trên từng route.

### Bước 7: Kiểm thử tối giản

Tạo một client test dùng transport và MIME type đã biết, không gửi custom metadata nếu server cho phép anonymous setup. Nếu client tối giản kết nối được, thêm từng cấu hình một: data MIME, metadata MIME, authentication metadata, rồi setup data. Bước nào làm lỗi xuất hiện sẽ khoanh vùng được nguyên nhân.

Không vô hiệu hóa authentication trên production chỉ để thử. Dùng môi trường test hoặc một endpoint test có policy được kiểm soát.

## 8. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xác minh | Hướng xử lý |
|---|---|---|---|
| SETUP bị `UNSUPPORTED_SETUP` | Protocol/MIME/feature không được hỗ trợ | Đọc error code và cấu hình SETUP hai phía | Chọn protocol/MIME được hỗ trợ; căn chỉnh thư viện. |
| SETUP bị `INVALID_SETUP` | Frame/cấu hình SETUP sai hoặc metadata không hợp lệ | Kiểm tra version, field và metadata encoding | Sửa cấu trúc/encoding theo protocol và implementation. |
| SETUP bị `REJECTED_SETUP` | Server policy hoặc authentication từ chối | Kiểm tra server-side rejection reason đã làm sạch | Gửi đúng auth metadata hoặc điều chỉnh policy theo yêu cầu bảo mật. |
| SETUP thành công, request đầu tiên lỗi decode | Codec hoặc data MIME không khớp | Xem decoder exception và MIME type thực tế | Đăng ký codec đúng ở cả client/server. |
| Route không được tìm thấy | Routing metadata sai hoặc handler mapping không khớp | Kiểm tra route entry và `@MessageMapping` | Sửa composite/routing metadata hoặc route. |
| WebSocket nhận 401/403 trước SETUP | Cookie, Origin hoặc HTTP auth policy | Kiểm tra access log đã lọc secret và proxy policy | Sửa handshake auth/Origin theo contract. |
| WebSocket không nhận 101 | Proxy Upgrade/path/TLS | Kiểm tra response handshake | Sửa reverse proxy, path hoặc certificate. |
| Chỉ một số node từ chối SETUP | Node chạy version/config khác nhau | So sánh deployment/config theo node | Đồng bộ version, MIME codec và access policy. |
| Token hợp lệ nhưng SETUP bị từ chối | Sai auth MIME/decoder, issuer/audience hoặc clock | Kiểm tra auth failure code an toàn và clock | Sửa metadata encoding hoặc validation config. |
| Kết nối mở được nhưng route bị 403 | Authorization ở request-level | Kiểm tra principal, authority và route policy | Cấp quyền đúng hoặc sửa mapping security. |

## 9. Log và quan sát an toàn

Chẩn đoán SETUP cần log đủ để phân biệt lỗi nhưng không làm lộ credential. Có thể ghi:

- Transport: `tcp` hoặc `websocket`.
- Endpoint đã loại bỏ query string nhạy cảm.
- Protocol version đã chuẩn hóa.
- Data MIME type và metadata MIME type.
- SETUP error code và exception class.
- Authentication scheme hoặc mã lý do đã chuẩn hóa, không ghi token.
- Client/app version và server node.
- Correlation ID/connection ID không chứa bí mật.

Không ghi:

- Bearer token, password, API key, cookie hoặc refresh token.
- Raw SETUP metadata/composite metadata.
- Raw setup data nếu có thể chứa thông tin cá nhân hoặc bí mật.
- Toàn bộ exception message/cause chain chưa được kiểm tra.

Nếu cần bật DEBUG/wiretap để xem frame, chỉ dùng môi trường test với credential giả. Tắt logging payload-level sau khi điều tra. Với production, ưu tiên error code, metadata đã allowlist và log phía server đã được làm sạch.

## 10. Ví dụ phân tích một lỗi cụ thể

Giả sử client kết nối TCP thành công nhưng nhận `REJECTED_SETUP`. Cả hai phía khai báo JSON cho data. Server log mã `AUTHENTICATION_FAILED` đã chuẩn hóa.

Quy trình điều tra:

1. TCP connect thành công, vậy host/port và listener hoạt động.
2. SETUP đã được server đọc, vậy đây không phải lỗi transport.
3. Data MIME type giống nhau; chưa có bằng chứng codec gây rejection.
4. Server rejection code cho biết policy authentication từ chối.
5. Kiểm tra client có gửi authentication metadata trong SETUP hay không.
6. Xác nhận metadata MIME type là authentication entry mà server decoder hỗ trợ; nếu composite metadata được yêu cầu, kiểm tra entry nằm trong composite container.
7. Kiểm tra issuer, audience, expiry, chữ ký và clock skew bằng mã lỗi an toàn; không in token ra log.
8. Chạy lại trong môi trường test với token giả lập hợp lệ và không hợp lệ để xác nhận kết quả.

Nếu thay token nhưng vẫn lỗi, cần kiểm tra encoder/decoder và MIME type của authentication metadata. Nếu server thực tế chỉ yêu cầu authentication ở từng request, không nên ép credential vào SETUP; hãy kiểm tra request-level security contract.

## 11. Checklist trước khi phát hành client/server

- Client/server dùng protocol version và thư viện tương thích.
- Data MIME type được khai báo thống nhất và codec tương ứng có ở cả hai phía.
- Metadata MIME type đúng với loại metadata đơn hoặc composite được sử dụng.
- Routing/authentication entry có MIME type riêng đúng contract.
- SETUP data/metadata không chứa field sai định dạng hoặc vượt giới hạn.
- Authentication ở SETUP và authentication ở từng request được phân biệt rõ.
- Origin/HTTP handshake policy được kiểm tra riêng với RSocket SETUP khi dùng WebSocket.
- Error code và server log đủ phân biệt `INVALID_SETUP`, `UNSUPPORTED_SETUP`, `REJECTED_SETUP`.
- Không log raw token, cookie, metadata hoặc payload nhạy cảm.
- Có integration test cho MIME mismatch, protocol mismatch, missing/invalid auth metadata và route-level denial.
- Deployment nhiều node dùng cấu hình và dependency đồng nhất.

## 12. Kết luận

SETUP là bước khởi tạo logical RSocket connection, nơi client công bố protocol version, keepalive và MIME type mặc định cho data/metadata. Khi bị từ chối, hãy xác định trước transport đã kết nối chưa, sau đó đọc error code và đối chiếu cấu hình hai phía. MIME mismatch có thể bị từ chối ngay lúc SETUP hoặc chỉ lộ ra khi decode request đầu tiên; protocol version khác với library version và application schema version. Authentication có thể được kiểm tra ở SETUP hoặc từng request, còn Origin thường được kiểm tra ở WebSocket handshake. Phân loại đúng lớp lỗi, dùng MIME/codec tương thích, đồng bộ dependency và kiểm tra access policy sẽ giúp khắc phục sự cố mà không phải nới lỏng bảo mật hoặc thay đổi cấu hình một cách mò mẫm.
