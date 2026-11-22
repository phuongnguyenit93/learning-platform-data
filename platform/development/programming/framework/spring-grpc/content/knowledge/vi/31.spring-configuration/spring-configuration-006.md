# Cấu hình keepalive và message size

Trong **SPRING_GRPC**, keepalive và giới hạn kích thước message ảnh hưởng trực tiếp đến độ ổn định của kết nối HTTP/2, khả năng truyền payload lớn và mức tiêu thụ tài nguyên. Keepalive giúp phát hiện kết nối đã mất hoặc duy trì kết nối qua proxy/load balancer có chính sách idle timeout. Message size giới hạn lượng dữ liệu một RPC message được phép nhận.

Spring Boot cung cấp properties riêng cho gRPC client và server. Cần cấu hình hai phía có phối hợp: server kiểm soát message nhận từ client và chính sách ping mà client được phép gửi; client kiểm soát message nhận từ server và nhịp keepalive của channel. Bài này trình bày cách chọn giá trị, áp dụng trong YAML và kiểm thử giới hạn thực tế.

## 1. Phân biệt keepalive với health check và deadline

gRPC keepalive dùng HTTP/2 PING frame để kiểm tra transport connection. Một đầu gửi PING sau một khoảng không có hoạt động đọc; đầu kia trả ACK. Nếu không nhận được phản hồi trong timeout, transport đóng kết nối.

Keepalive giải quyết vấn đề ở tầng kết nối:

- Phát hiện connection không còn phản hồi.
- Giữ kết nối hoạt động khi proxy hoặc load balancer đóng connection quá lâu không có traffic.
- Hỗ trợ các RPC streaming hoặc channel sống lâu.

Nó không xác nhận service còn xử lý nghiệp vụ được. Cần phân biệt:

| Cơ chế | Kiểm tra điều gì? | Phạm vi |
| --- | --- | --- |
| gRPC keepalive | HTTP/2 connection có phản hồi PING/ACK không | Transport connection |
| gRPC Health | Service có đang ở trạng thái `SERVING` không | Service/application |
| RPC deadline | Một lời gọi được phép chạy tối đa bao lâu | Từng RPC |
| TCP keepalive | Socket TCP có còn phản hồi theo cơ chế hệ điều hành không | TCP connection |

Không dùng PING để thay health check hoặc deadline. Một connection có thể phản hồi PING trong khi database đã ngừng hoạt động; ngược lại, một connection idle không có RPC vẫn có thể khỏe mạnh dù không cần gửi PING thường xuyên.

## 2. Keepalive có hai phía và hai chiều hoạt động

Client và server đều có thể gửi PING. Các tham số chính:

| Tham số | Ý nghĩa |
| --- | --- |
| `keepalive.time` | Khoảng thời gian không có hoạt động đọc trước khi đầu gửi phát PING |
| `keepalive.timeout` | Thời gian chờ phản hồi sau khi gửi PING; quá hạn thì đóng connection |
| `keepalive.without-calls` | Ở client, có cho phép gửi PING khi không có RPC đang hoạt động không |
| `keepalive.permit.time` | Ở server, khoảng tối thiểu giữa các PING client được phép gửi khi không có data/header activity |
| `keepalive.permit.without-calls` | Ở server, có cho phép client gửi PING khi không có RPC đang hoạt động không |

Các giá trị mặc định phổ biến trong gRPC là:

- Client keepalive time mặc định tắt; timeout thường là `20s`; không gửi PING khi không có RPC.
- Server keepalive time mặc định `2h`; timeout `20s`.
- Server permit time mặc định `5m`; mặc định không cho client PING khi không có RPC.

Spring Boot 4.1 cung cấp properties để điều chỉnh các giá trị này. Giá trị thực tế còn phụ thuộc transport, phiên bản và cấu hình của proxy/load balancer.

**Không cấu hình client gửi PING quá thường xuyên.** Nếu client gửi PING nhanh hơn chính sách server cho phép hoặc gửi khi server không cho phép PING lúc không có RPC, server có thể gửi HTTP/2 `GOAWAY` với debug data `too_many_pings` và đóng connection. Hướng dẫn gRPC khuyến nghị tránh bật PING khi không có RPC và tránh chu kỳ client quá ngắn; hãy phối hợp với chủ sở hữu server trước khi thay đổi.

## 3. Cấu hình keepalive cho gRPC client

Mỗi channel có thể có chính sách riêng. Ví dụ client `inventory` gọi server qua mạng nội bộ:

```yaml
spring:
  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          keepalive:
            time: 5m
            timeout: 20s
            without-calls: false
```

Ý nghĩa:

- `time: 5m`: khi connection không có hoạt động đọc trong khoảng thời gian này, client có thể gửi PING.
- `timeout: 20s`: client chờ PING ACK tối đa 20 giây.
- `without-calls: false`: client không chủ động gửi PING khi không có RPC đang hoạt động.

Đây là ví dụ cho trường hợp cần duy trì connection lâu dài. Nếu server giữ permit time mặc định `5m`, client không nên đặt `time` nhỏ hơn giá trị đó. Nếu server đặt permit time khác, client cần tuân theo chính sách thực tế của server.

Cấu hình trong `application.properties`:

```properties
spring.grpc.client.channel.inventory.target=static://inventory.internal:9090
spring.grpc.client.channel.inventory.keepalive.time=5m
spring.grpc.client.channel.inventory.keepalive.timeout=20s
spring.grpc.client.channel.inventory.keepalive.without-calls=false
```

Nếu ứng dụng có nhiều channel, không nhất thiết áp dụng cùng một chu kỳ. Channel dùng streaming dài hạn qua load balancer có thể cần keepalive; channel chỉ gọi unary ngắn và thường xuyên có traffic có thể không cần cấu hình thêm.

## 4. Cấu hình keepalive policy trên server

Server quyết định nhịp PING do chính server gửi và giới hạn PING từ client:

```yaml
spring:
  grpc:
    server:
      keepalive:
        time: 2h
        timeout: 20s
        permit:
          time: 5m
          without-calls: false
```

Trong ví dụ:

- `time: 2h`: server gửi PING khi không có hoạt động đọc trong khoảng hai giờ.
- `timeout: 20s`: server chờ phản hồi tối đa 20 giây.
- `permit.time: 5m`: server không chấp nhận client gửi PING dày hơn chính sách tối thiểu năm phút khi không có data/header activity.
- `permit.without-calls: false`: server không cho client gửi PING khi connection không có RPC đang hoạt động.

`permit.time` không phải thời gian timeout của một RPC. Nó là chính sách bảo vệ server khỏi PING quá thường xuyên. Nếu cần đổi giá trị này, phải phối hợp với cấu hình client và hạ tầng mạng.

### 4.1. Quản lý tuổi thọ connection

Server còn có thể đặt giới hạn tuổi và thời gian idle của connection:

```yaml
spring:
  grpc:
    server:
      keepalive:
        connection:
          max-age: 30m
          max-idle-time: 10m
          grace-period: 30s
```

- `connection.max-age`: tuổi tối đa của một connection trước khi server yêu cầu kết thúc có kiểm soát.
- `connection.max-idle-time`: thời gian connection không có RPC đang hoạt động trước khi bị kết thúc có kiểm soát.
- `connection.grace-period`: khoảng thời gian tối đa dành cho quá trình graceful termination.

Đây là chính sách vòng đời connection, khác với PING/ACK. Khi đặt `max-age`, các channel dài hạn và stream đang chạy cần có chiến lược reconnect/resume phù hợp. Không chọn thời gian quá ngắn nếu ứng dụng có stream kéo dài hoặc client không thể khôi phục vị trí xử lý.

## 5. Giới hạn message size là giới hạn inbound

gRPC áp dụng giới hạn message ở phía **nhận**. Mỗi đầu kiểm soát kích thước message mà nó chấp nhận:

- Server inbound limit kiểm soát request message do client gửi lên.
- Client inbound limit kiểm soát response message do server gửi xuống.

Vì vậy, tăng giới hạn ở server không tự động tăng giới hạn nhận response ở client. Nếu request và response đều lớn, phải cấu hình đúng phía nhận ở cả hai chiều.

gRPC Java thường có mặc định khoảng `4 MiB` cho inbound message. Spring Boot 4.1 cung cấp `inbound.message.max-size` để thay đổi giá trị này.

## 6. Cấu hình message size cho server và client

Ví dụ cho phép nhận message tối đa `8MB` ở cả hai phía:

```yaml
spring:
  grpc:
    server:
      inbound:
        message:
          max-size: 8MB

    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          inbound:
            message:
              max-size: 8MB
```

Các property tương ứng:

| Phía nhận | Property |
| --- | --- |
| Server nhận request | `spring.grpc.server.inbound.message.max-size` |
| Client nhận response trên channel `inventory` | `spring.grpc.client.channel.inventory.inbound.message.max-size` |

Có thể khai báo trong `application.properties`:

```properties
spring.grpc.server.inbound.message.max-size=8MB
spring.grpc.client.channel.inventory.inbound.message.max-size=8MB
```

Property nhận `DataSize`, vì vậy có thể dùng hậu tố như `KB`, `MB` hoặc `B`. Nếu bỏ hậu tố, giá trị được hiểu là byte. Hãy ghi đơn vị rõ ràng để tránh nhầm giữa byte và megabyte.

Giới hạn này áp dụng cho từng message, không phải tổng dung lượng của toàn bộ stream. Một server-streaming RPC có thể gửi nhiều message; mỗi message phải nằm trong giới hạn inbound của client. Tương tự, client-streaming có nhiều request và mỗi request phải nằm trong giới hạn inbound của server.

## 7. Message size, metadata size và compression

Không nhầm message size với metadata size:

- Message chứa payload protobuf như field, bytes hoặc nested message.
- Metadata chứa thông tin điều khiển như authorization token, trace context và custom headers.

Spring Boot có property riêng cho inbound metadata, thường có giới hạn mặc định nhỏ hơn nhiều so với message. Tăng message limit không làm metadata limit tăng theo. Nếu lỗi do header/metadata quá lớn, hãy kiểm tra metadata property và giảm lượng dữ liệu đặt trong metadata.

Message size cũng không phải giới hạn tổng bộ nhớ của request. Một message lớn có thể cần bộ nhớ cho buffer mạng, object protobuf đã parse và bản sao trong logic ứng dụng. Compression có thể giảm bytes truyền qua mạng, nhưng phía nhận vẫn phải giải nén và xử lý payload. Vì vậy, cần chọn giới hạn dựa trên kích thước dữ liệu thực tế sau giải nén và khả năng bộ nhớ của workload.

## 8. Chọn message size an toàn

Không đặt giới hạn rất lớn hoặc không giới hạn chỉ để tránh lỗi `RESOURCE_EXHAUSTED`. Hãy xác định kích thước payload lớn nhất hợp lệ theo nghiệp vụ và cộng một khoảng dự phòng có kiểm soát.

Một số nguyên tắc:

- Giữ mặc định nếu payload thông thường nhỏ hơn nhiều so với `4 MiB`.
- Chỉ tăng lên `8MB`, `16MB` hoặc mức khác khi có use case và số liệu đo đạc.
- Đặt cùng một contract giữa sender và receiver; kiểm tra request và response độc lập.
- Xem xét đồng thời metadata size, memory limit, concurrency và số lượng stream đang mở.
- Với file hoặc dữ liệu rất lớn, ưu tiên streaming theo chunk thay vì gửi một message chứa toàn bộ nội dung.
- Dùng flow control và backpressure để producer không đẩy dữ liệu nhanh hơn khả năng consumer xử lý.

Ví dụ schema truyền file theo chunk:

```proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
```

Mỗi `UploadChunk` có kích thước giới hạn; tổng file có thể lớn hơn nhiều lần giới hạn đó. Ứng dụng cần xác minh sequence, xử lý retry/resume và giới hạn số chunk đang giữ trong bộ nhớ.

## 9. Cấu hình kết hợp cho một service thực tế

Ví dụ dưới đây đặt chính sách cho server tồn kho và channel client tương ứng:

```yaml
spring:
  grpc:
    server:
      port: 9090
      keepalive:
        time: 2h
        timeout: 20s
        permit:
          time: 5m
          without-calls: false
      inbound:
        message:
          max-size: 8MB

    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          keepalive:
            time: 5m
            timeout: 20s
            without-calls: false
          inbound:
            message:
              max-size: 8MB
```

Cấu hình này minh họa client ping theo chu kỳ phù hợp với server permit policy và cho phép mỗi bên nhận message tối đa `8MB`. Giá trị cần điều chỉnh theo traffic, proxy idle timeout và kích thước payload thực tế; không phải cấu hình mặc định phù hợp cho mọi hệ thống.

## 10. Khi nào cần ServerBuilderCustomizer?

Các properties chuẩn phù hợp với keepalive và inbound message size phổ biến. Nếu cần một tùy chọn transport-specific chưa được Spring Boot expose, có thể dùng bean `ServerBuilderCustomizer` để tùy chỉnh server builder trước khi server được tạo. Kiểu builder cụ thể và các tùy chọn khả dụng phụ thuộc transport cùng phiên bản grpc-java.

Không đặt cùng một giá trị ở cả properties và customizer mà không xác định rõ thứ tự/nguồn cấu hình. Với servlet transport, servlet container quản lý network layer và một số tùy chọn của native builder có thể không khả dụng. Hãy xác nhận transport trước khi dùng customizer.

## 11. Kiểm thử keepalive và message size

### 11.1. Kiểm tra message size

Tạo test server và client với giới hạn nhỏ, ví dụ `1MB`, rồi kiểm tra:

1. Request nhỏ hơn giới hạn được xử lý.
2. Request lớn hơn server inbound limit bị từ chối.
3. Response lớn hơn client inbound limit bị client từ chối.
4. Tăng giới hạn ở đúng phía nhận thì test tương ứng chuyển sang thành công.
5. Streaming nhiều chunk nhỏ vẫn hoạt động khi tổng dữ liệu vượt `1MB`.

Lỗi vượt giới hạn thường được thể hiện bằng gRPC status `RESOURCE_EXHAUSTED` hoặc lỗi transport tương ứng. Hãy xác định phía nào từ chối message qua log và exception cause, thay vì tăng giới hạn ở cả hai đầu một cách mù quáng.

### 11.2. Kiểm tra keepalive

Keepalive cần được kiểm tra trên transport mạng thật vì in-process transport không mô phỏng đầy đủ HTTP/2 PING:

- Mở channel và thực hiện một RPC.
- Để connection idle hoặc duy trì một stream dài hạn theo kịch bản.
- Kiểm tra client/server vẫn giữ connection trong khoảng thời gian dự kiến.
- Tắt server hoặc chặn đường truyền trong môi trường test để xác nhận ping timeout phát hiện connection mất.
- Thử cấu hình client ping ngắn hơn server permit policy trong môi trường cô lập để nhận diện lỗi policy; không chạy phép thử này trên production.
- Kiểm tra reconnect và khả năng phục hồi stream khi connection bị đóng do max age hoặc network interruption.

Không dùng một RPC unary nhanh để kết luận keepalive hoạt động; RPC có thể hoàn tất trước khi timer PING được kích hoạt.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Connection bị server đóng với `too_many_pings` | Client ping quá thường xuyên hoặc ping khi không có RPC trong khi server không cho phép |
| Channel mất kết nối sau idle | Proxy/load balancer idle timeout, keepalive chưa bật hoặc timeout không phù hợp |
| PING timeout | Network path mất phản hồi, server quá tải hoặc connection đã hỏng |
| Request bị từ chối vì message quá lớn | Server inbound message limit thấp hơn request |
| Client nhận `RESOURCE_EXHAUSTED` khi đọc response | Client inbound message limit thấp hơn response |
| Message nhỏ vẫn bị từ chối | Có thể lỗi metadata size, không phải message size |
| Stream bị ngắt sau một khoảng thời gian | Server connection max-age, idle policy, proxy timeout hoặc network interruption |
| Tăng limit nhưng lỗi không đổi | Đã chỉnh nhầm phía nhận, channel khác hoặc cấu hình chưa được bind vào server/client đang chạy |

Khi điều tra, ghi lại kích thước payload, channel target, transport, property source hiệu lực và status/exception đầy đủ. Không log nội dung nhạy cảm chỉ để đo kích thước; có thể ghi số byte và RPC method.

## 13. Bài tập thực hành

1. Giữ cấu hình mặc định và ghi nhận kích thước request/response lớn nhất của một RPC.
2. Cấu hình server inbound message size thành `8MB`; gửi request `6MB` và xác nhận thành công.
3. Giữ client inbound limit ở `4MB`; trả response `6MB` và xác nhận client từ chối.
4. Tăng client inbound limit thành `8MB`; chạy lại response test.
5. Cấu hình client keepalive `time: 5m`, `timeout: 20s`, `without-calls: false`.
6. Cấu hình server permit time và permit-without-calls; xác nhận client tuân theo policy.
7. Quan sát kết nối qua proxy có idle timeout; so sánh khi bật/tắt keepalive.
8. Đặt `connection.max-age` trong test và kiểm tra client reconnect sau khi server kết thúc connection có kiểm soát.
9. Chuyển payload lớn thành stream chunk và đo bộ nhớ khi nhiều upload chạy đồng thời.
10. Ghi lại property nào thuộc client, property nào thuộc server và chiều message mà từng giới hạn kiểm soát.

### Ghi nhớ

**Keepalive điều khiển sức khỏe của transport connection; message size giới hạn từng message mà một đầu nhận chấp nhận.** Cấu hình client ping phải phù hợp với permit policy của server và hạ tầng mạng. Giới hạn request phải đặt ở server, giới hạn response phải đặt ở client; cả hai cần được kiểm thử riêng. Với payload lớn, chọn giới hạn vừa đủ hoặc chia thành stream chunk có flow control thay vì mở giới hạn vô hạn.

## Tài liệu tham khảo

- [Spring Boot — gRPC Channel Properties](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot API — GrpcClientProperties.Channel.Keepalive](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/grpc/client/autoconfigure/GrpcClientProperties.Channel.Keepalive.html)
- [Spring gRPC — Server and ServerBuilderCustomizer](https://docs.spring.io/spring-grpc/reference/server.html)
- [gRPC — Keepalive](https://grpc.io/docs/guides/keepalive/)
- [gRPC Java — ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html)
