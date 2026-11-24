# Mô phỏng mất mạng, resume bị từ chối và máy chủ khởi động lại

RSocket Connection Resumption giúp tiếp tục một connection sau khi transport bị gián đoạn trong một khoảng thời gian. Tính năng này hữu ích khi TCP hoặc WebSocket mất kết nối tạm thời, nhưng không phải cơ chế phục hồi luôn thành công. Client và server phải cùng hỗ trợ resume, đồng thời giữ đủ session state và các frame cần truyền lại.

Ba tình huống cần kiểm thử riêng:

1. Mất mạng ngắn hạn, server vẫn sống và còn giữ session: client có thể resume thành công.
2. Server không còn session/token hoặc frame buffer cần thiết: server từ chối resume.
3. Server process khởi động lại: state resume trong bộ nhớ của process cũ thường đã mất, nên client không thể tiếp tục session cũ bằng cơ chế mặc định.

Điểm quan trọng khi thiết kế bài kiểm thử là phân biệt khôi phục transport/session với khôi phục nghiệp vụ. RSocket resume có thể tiếp tục các interaction đang hoạt động nếu state giao thức còn nguyên; nó không tự khôi phục transaction database, job nền hoặc cursor nghiệp vụ đã mất.

## 1. Phân biệt ba loại sự cố

| Tình huống | Điều xảy ra | Kỳ vọng |
| --- | --- | --- |
| Network interruption | Đường truyền bị cắt, nhưng client và server vẫn chạy, session và frame buffer vẫn còn. | Client mở transport mới, gửi RESUME; server có thể trả RESUME_OK. |
| Resume rejected | Token không được nhận diện, session hết hạn hoặc một phía không còn frame cần phát lại. | Server trả ERROR[REJECTED_RESUME]; client dừng thử resume session đó. |
| Server restart | Process server cũ dừng, session manager và frame store trong RAM bị mất. | Với state lưu trong bộ nhớ, instance mới không nhận ra session cũ và từ chối RESUME. Client phải tạo connection mới và phục hồi nghiệp vụ ở tầng ứng dụng. |

Một lần mất mạng không đồng nghĩa server restart. Trong network partition, server có thể vẫn giữ nguyên session và tiếp tục stream sau khi client kết nối lại. Khi process server bị thay thế, trạng thái trong bộ nhớ của instance cũ không tự xuất hiện ở instance mới.

## 2. Connection Resumption hoạt động như thế nào?

RSocket resumption là capability tùy chọn. Client bật khả năng resume trong SETUP và gửi resume identification token. Khi transport bị gián đoạn, client tạo một transport connection mới và gửi frame RESUME thay cho SETUP. Server dùng token để tìm session cũ và kiểm tra các vị trí frame mà hai bên đã gửi, nhận và còn lưu.

Nếu đủ state, server trả RESUME_OK. Hai bên tiếp tục từ vị trí giao thức đã thống nhất và có thể truyền lại các frame chưa được xác nhận. Các stream đang hoạt động có thể tiếp tục mà ứng dụng không cần tạo request mới.

~~~text
Client                                  Server
  |                                       |
  |----------- SETUP (resume token) ----->|
  |<---------- connection ready ----------|
  |                                       |
  |----------- REQUEST_STREAM ----------->|
  |<-------------- PAYLOAD ---------------|
  |<-------------- PAYLOAD ---------------|
  |                                       |
  X  TCP/WebSocket bị gián đoạn           |
  |                                       |
  |  tạo transport connection mới         |
  |----------- RESUME (token, positions)->|
  |<---------- RESUME_OK -----------------|
  |                                       |
  |<-------------- PAYLOAD ---------------|
  |<-------------- PAYLOAD ---------------|
  |                                       |
  |     interaction tiếp tục              |
~~~

Hai frame quan trọng:

| Frame | Stream ID | Ý nghĩa |
| --- | --- | --- |
| RESUME (0x0D) | 0 | Client yêu cầu khôi phục connection cũ, mang token và các vị trí frame. |
| RESUME_OK (0x0E) | 0 | Server chấp nhận và cho biết vị trí cuối cùng đã nhận từ client. |

RESUME và RESUME_OK là frame connection-level, không phải request-response nghiệp vụ. Nếu server không thể tiếp tục session, nó trả ERROR với mã REJECTED_RESUME.

## 3. Những state cần còn nguyên để resume thành công

Resume không chỉ cần biết token. Hai đầu phải giữ state cần thiết để xác định phần frame nào cần truyền lại:

- Resume identification token của connection ban đầu.
- Vị trí frame đã gửi và đã nhận ở cả hai chiều.
- Các frame chưa được peer xác nhận, còn nằm trong retransmission buffer.
- Session và trạng thái của các stream đang hoạt động.
- Cấu hình giao thức và MIME type tương thích với connection ban đầu.
- Thời gian session còn nằm trong giới hạn cho phép resume.

Protocol dùng implied position: hai bên suy ra vị trí từ chuỗi frame đã trao đổi. Client gửi vị trí cuối cùng nhận từ server và vị trí đầu tiên mà client còn giữ. Server kiểm tra liệu frame cần phát lại có còn tồn tại ở cả hai phía hay không.

Resume chỉ được thiết kế cho trường hợp mất kết nối mà state của hai đầu vẫn được duy trì. Protocol không giả định rằng một bên đã mất toàn bộ state rồi có thể tự tái tạo nó từ token.

Resume token là định danh opaque của một connection. Token nên duy nhất cho từng connection, khó đoán và chỉ hợp lệ trong vòng đời session tương ứng. Không ghi token thô vào log hoặc dùng lại token của session cũ khi tạo một SETUP mới.

## 4. Cấu hình resume cho RSocket Java

Trong RSocket Java, RSocketConnector bật resume ở client và RSocketServer bật resume ở server. Hai phía đều cần cấu hình capability. Ví dụ sau minh họa API của RSocket Java 1.1.x; hãy dùng phiên bản được BOM của dự án quản lý và kiểm tra API tương ứng với phiên bản đó.

Client:

~~~java
Resume clientResume = new Resume()
    .sessionDuration(Duration.ofSeconds(30))
    .retry(Retry.fixedDelay(
        20,
        Duration.ofMillis(500)
    ));

RSocketConnector connector = RSocketConnector.create()
    .keepAlive(
        Duration.ofSeconds(1),
        Duration.ofSeconds(5)
    )
    .resume(clientResume);

Mono<RSocket> connection =
    connector.connect(TcpClientTransport.create("localhost", 7000));
~~~

sessionDuration xác định khoảng thời gian session được giữ để có thể resume. retry ở client xác định chính sách thử kết nối lại trong giai đoạn phục hồi. Keepalive giúp phát hiện peer không còn phản hồi; giá trị 1 giây/5 giây ở ví dụ chỉ phù hợp test nhanh, không phải mặc định production.

Server:

~~~java
Resume serverResume = new Resume()
    .sessionDuration(Duration.ofSeconds(30));

CloseableChannel server = RSocketServer
    .create(socketAcceptor)
    .resume(serverResume)
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

Server cũng phải giữ session và frame store trong thời gian cho phép resume. Không cấu hình resume chỉ ở client rồi kỳ vọng server tự động hỗ trợ.

### Dùng Spring RSocketRequester

Spring RSocketRequester.Builder cho phép cấu hình trực tiếp RSocketConnector thông qua rsocketConnector(...):

~~~java
Resume clientResume = new Resume()
    .sessionDuration(Duration.ofSeconds(30))
    .retry(Retry.fixedDelay(
        20,
        Duration.ofMillis(500)
    ));

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector
        .keepAlive(
            Duration.ofSeconds(1),
            Duration.ofSeconds(5)
        )
        .resume(clientResume)
    )
    .tcp("localhost", 7000);
~~~

Kết nối của requester được thiết lập khi có interaction đầu tiên. Nếu dùng Spring Boot server auto-configuration, có thể tùy chỉnh RSocketServer bằng RSocketServerCustomizer:

~~~java
@Bean
RSocketServerCustomizer resumeServerCustomizer() {
    return server -> server.resume(
        new Resume().sessionDuration(Duration.ofSeconds(30))
    );
}
~~~

Nếu dự án không dùng Boot auto-configuration, cấu hình RSocketServer trực tiếp như ví dụ phía trên. Việc bật resume phải được xác minh ở cả client lẫn server bằng log hoặc quan sát protocol frame.

## 5. Thiết kế môi trường test có thể điều khiển mạng

Không nên phụ thuộc vào việc rút cáp mạng hoặc tắt Wi-Fi thủ công để kiểm thử. Hãy đặt một TCP proxy giữa client và server, sau đó chủ động tạo latency, packet interruption hoặc đóng kết nối.

Testcontainers có module Toxiproxy:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-toxiproxy</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án chưa import Testcontainers BOM, hãy khai báo version của module theo version Testcontainers đang dùng trong dự án.

Ví dụ kiến trúc test:

~~~text
JUnit / Testcontainers
       |
       v
RSocket Client
       |
       v
Toxiproxy
       |
       v
RSocket Server Container
~~~

Client phải kết nối qua host/port của proxy. Nếu client kết nối trực tiếp tới server, các toxic trên proxy sẽ không ảnh hưởng đến connection đang được kiểm thử.

Toxiproxy có thể:

- Thêm latency và jitter để mô phỏng mạng chậm.
- Giới hạn bandwidth.
- Chặn dữ liệu theo một hoặc cả hai chiều.
- Tạo timeout hoặc đóng TCP connection.
- Khôi phục luồng dữ liệu bằng cách gỡ toxic.

Với test resume, cần phân biệt network blackhole với TCP reset. Blackhole chặn traffic và buộc keepalive phát hiện timeout; reset đóng socket rõ ràng. Cả hai đều hữu ích nhưng kiểm tra các đường phục hồi khác nhau.

## 6. Mô phỏng network interruption hai chiều

Với Testcontainers Toxiproxy, có thể chặn cả downstream và upstream bằng bandwidth bằng 0:

~~~java
proxy.toxics().bandwidth(
    "cut-downstream",
    ToxicDirection.DOWNSTREAM,
    0
);

proxy.toxics().bandwidth(
    "cut-upstream",
    ToxicDirection.UPSTREAM,
    0
);
~~~

Trong test, giữ stream đang hoạt động và chờ client phát hiện mất kết nối theo keepalive timeout. Sau đó gỡ hai toxic:

~~~java
proxy.toxics().get("cut-downstream").remove();
proxy.toxics().get("cut-upstream").remove();
~~~

Khi dùng bandwidth bằng 0, Toxiproxy chặn dữ liệu nhưng không nhất thiết đóng socket TCP ngay. Đây là mô phỏng blackhole. Nếu cần đóng connection sau một khoảng thời gian, có thể dùng timeout toxic với thời hạn lớn hơn 0 hoặc tắt proxy theo API của Toxiproxy.

Không đặt thời gian chờ test ngắn hơn keepalive max lifetime. Nếu client cần tối đa 5 giây để nhận ra peer không còn phản hồi, test phải dành thêm thời gian cho retry và resume.

## 7. Kịch bản A — Mất mạng ngắn hạn, resume thành công

Mục tiêu: xác nhận stream đang chạy tiếp tục sau khi đường truyền được phục hồi, trong khi server process và session state vẫn còn.

Thiết lập:

1. Bật resume ở client và server.
2. Đặt session duration đủ dài, ví dụ 30 giây.
3. Cho client kết nối qua Toxiproxy.
4. Mở một Request-Stream có sequence tăng dần.
5. Chặn traffic hai chiều trong thời gian ngắn.
6. Chờ client phát hiện disconnect và thực hiện RESUME.
7. Gỡ toxic trước khi session hết hạn.
8. Xác nhận stream tiếp tục và không tạo một SETUP session mới.

Responder mẫu:

~~~java
public record Event(long sequence, Instant createdAt) {}

@Controller
public class ResumeTestController {

    @MessageMapping("events.live")
    Flux<Event> liveEvents() {
        return Flux.interval(Duration.ofMillis(100))
            .map(sequence -> new Event(
                sequence,
                Instant.now()
            ));
    }
}
~~~

Test có thể dùng StepVerifier để nhận một số event trước khi cắt mạng, chờ phục hồi rồi xác nhận tiếp tục nhận event:

~~~java
StepVerifier.create(
        requester.route("events.live")
            .retrieveFlux(Event.class)
    )
    .expectNextCount(3)
    .then(() -> cutNetwork(proxy))
    .thenAwait(Duration.ofSeconds(7))
    .then(() -> restoreNetwork(proxy))
    .expectNextCount(5)
    .thenCancel()
    .verify(Duration.ofSeconds(20));
~~~

cutNetwork và restoreNetwork là helper của test dùng Toxiproxy. Thời gian trong ví dụ phải được điều chỉnh theo keepalive, retry và session duration đã cấu hình.

Các assertion cần có:

- Server process không restart trong test.
- Client quan sát được một lần mất transport.
- Client gửi RESUME sau khi mở transport mới.
- Server chấp nhận và trả RESUME_OK.
- Interaction đang chạy tiếp tục.
- Client không tạo SETUP mới cho cùng interaction.
- Sequence event không bị thiếu trong phạm vi frame mà resume bảo đảm truyền lại.

Đừng chỉ kiểm tra rằng một request mới thành công sau khi gỡ toxic. Điều đó có thể là reconnect bằng SETUP mới chứ không phải resume session cũ. Hãy quan sát frame, session ID hoặc log/interceptor để phân biệt.

## 8. Kịch bản B — Resume bị từ chối

Server có thể từ chối RESUME khi:

- Không nhận diện được resume token.
- Session đã hết thời gian lưu giữ.
- Server không còn frame cần phát lại.
- Vị trí frame client yêu cầu không hợp lệ.
- Server không hỗ trợ resumption.
- Có điều kiện khác khiến server không thể tiếp tục session.

Một cách test có thể lặp lại là tạo session rồi chờ vượt quá sessionDuration trước khi client resume. Cách khác là dùng test server mới có resume enabled nhưng không có session state của token cũ.

~~~text
Client                                  Server
  |                                       |
  |----------- SETUP (token T-1) -------->|
  |<---------- connection ready ----------|
  |                                       |
  X transport disconnected               |
  |                                       |
  |----------- RESUME (token T-1) ------->|
  |                                       | token/session không còn
  |<---------- ERROR[REJECTED_RESUME] ----|
  |                                       |
  |  dừng resume session T-1              |
  |                                       |
  |----------- SETUP mới (token T-2) ---->|
  |<---------- connection ready ----------|
~~~

Theo protocol, sau khi nhận ERROR[REJECTED_RESUME], client MUST NOT tiếp tục thử resume session đó. Client cần kết thúc đường resume cũ. Nếu ứng dụng muốn tiếp tục làm việc, nó phải tạo một connection mới bằng SETUP và thực hiện khôi phục ở tầng ứng dụng.

Không nhầm hai lỗi:

| Lỗi | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| REJECTED_SETUP | Lúc tạo connection ban đầu bằng SETUP có yêu cầu resume nhưng server không chấp nhận cấu hình. | Server không chấp nhận setup có resume. |
| REJECTED_RESUME | Client đã có session trước đó và gửi RESUME sau khi transport đứt. | Server không thể tiếp tục session cũ. |

## 9. Kịch bản C — Server khởi động lại

Đây là kịch bản thường làm test resume thất bại nếu chỉ dùng cấu hình mặc định:

1. Client và server tạo connection có resume enabled.
2. Server giữ session manager và frame store trong bộ nhớ process.
3. Client mở một stream đang hoạt động.
4. Server process bị dừng hoặc container bị restart.
5. Client phát hiện transport lỗi và thử kết nối lại.
6. Instance server mới nhận RESUME nhưng không có session/token/frame state của process cũ.
7. Server trả ERROR[REJECTED_RESUME].

RSocket Java có InMemoryResumableFramesStore và các lớp session manager trong package io.rsocket.resume. State trong RAM không tồn tại sau khi JVM/process bị dừng. Bật .resume(...) không đồng nghĩa session được ghi ra database hoặc tự động chuyển sang replica khác.

Sơ đồ:

~~~text
Client                  Server instance A
  |                            |
  |------ SETUP token T ------>|
  |<----- session active ------|
  |------ REQUEST_STREAM ----->|
  |<--------- PAYLOAD ----------|
  |                            |
  |                    process crash
  |                            X
  |                            |
  |                 Server instance B
  |                            |
  |------ RESUME token T ----->|
  |                            | token T không tồn tại
  |<-- ERROR[REJECTED_RESUME] -|
  |                            |
  |------ new SETUP ---------->|
  |<----- new session ---------|
~~~

### Cách dựng test server restart

Đặt server phía sau Toxiproxy và giữ nguyên địa chỉ upstream/port. Test cần có khả năng:

- Dừng container hoặc process server A.
- Khởi động process server B trên cùng endpoint.
- Giữ client process và trạng thái resume phía client đang chạy.
- Chờ client gửi RESUME tới server B.
- Xác nhận server B từ chối token của session A.

Nếu test khởi động một server mới với một Resume object mới, session store trong bộ nhớ cũng mới. Đây là điều kiện mong muốn để chứng minh state của instance cũ không tự được chuyển sang instance mới.

### Điều gì xảy ra sau khi bị từ chối?

Client không được gửi lại RESUME với token cũ. Ứng dụng nên:

1. Ghi nhận session cũ đã mất.
2. Tạo một RSocket connection mới bằng SETUP.
3. Xác thực lại và thiết lập metadata cần thiết.
4. Tạo lại request stream hoặc channel.
5. Dùng cursor/sequence nghiệp vụ để tiếp tục từ vị trí đã xử lý bền vững.
6. Dùng idempotency key cho command có side effect để tránh thực hiện trùng.

Ví dụ query có cursor:

~~~java
public record SubscribeEvents(
    UUID aggregateId,
    long afterSequence
) {}

Flux<Event> resumeAtApplicationLevel(
        RSocketRequester requester,
        UUID aggregateId,
        long lastProcessedSequence) {

    return requester
        .route("events.from-sequence")
        .data(new SubscribeEvents(
            aggregateId,
            lastProcessedSequence
        ))
        .retrieveFlux(Event.class);
}
~~~

Đây là application-level replay. Nó mở interaction mới và đọc lại event từ cursor nghiệp vụ, không phải RSocket RESUME protocol.

## 10. Vì sao server restart khác network interruption?

RSocket resume được thiết kế cho transport failure trong khi state của cả hai đầu vẫn còn. Server restart có thể xóa:

- Resume token và mapping token tới session.
- Frame retransmission buffer.
- Implied positions.
- Các stream đang hoạt động và subscription tới nguồn dữ liệu.
- Context của connection và các resource gắn với session.

Ngay cả khi lưu frame buffer bền vững, ứng dụng còn phải khôi phục được state xử lý của stream và responder. Một Flux.interval đang chạy trong JVM cũ không thể tự tiếp tục trong JVM mới chỉ nhờ replay frame.

Muốn resume xuyên process restart cần một thiết kế nâng cao: session state, token mapping, frame store, positions và khả năng tái tạo các responder/stream phải được lưu hoặc dựng lại nhất quán. Đây không phải điều mặc định mà RSocket Java hoặc Spring Boot tự cung cấp.

Với nhiều replica, sticky routing có thể giúp một client quay lại đúng instance sau network interruption. Tuy nhiên, sticky routing không cứu được khi instance đó bị restart hoặc bị xóa. Nếu client được route sang replica khác, replica đó cũng phải có state resume tương ứng thì mới có thể chấp nhận token.

## 11. Phân biệt resume với reconnect

RSocket Java có hai cơ chế khác nhau:

| Cơ chế | Hành vi | Có tiếp tục interaction đang chạy? |
| --- | --- | --- |
| Resume | Khôi phục session cũ bằng token và frame positions. | Có thể, nếu state hai phía còn nguyên và server chấp nhận. |
| Reconnect | Tạo connection mới sau khi connection cũ mất. | Không tự khôi phục stream cũ; ứng dụng phải gửi lại request cần thiết. |

RSocketConnector.resume(Resume) và reconnect(Retry) là hai tùy chọn loại trừ lẫn nhau trong RSocket Java. Khi dùng resume, connector lưu state frame để có thể phát lại; reconnect đơn giản hơn và không phải lưu retransmission buffer cho session cũ.

Không coi retry một request sau khi reconnect là resume. Nếu request trước có side effect, retry có thể chạy nghiệp vụ lần thứ hai. Hãy dùng idempotency key hoặc query trạng thái trước khi gửi lại.

## 12. Resume không bảo đảm exactly-once cho nghiệp vụ

Resume bảo đảm tính liên tục của giao thức theo frame positions trong phạm vi state còn tồn tại. Nó không cam kết một thao tác nghiệp vụ chỉ được thực hiện đúng một lần.

Ví dụ:

1. Client gửi command thanh toán.
2. Server nhận frame và gọi payment service.
3. Payment service đã commit giao dịch.
4. Connection đứt trước khi client nhận response.
5. Frame được truyền lại sau resume hoặc client retry command qua connection mới.

Nếu handler không idempotent, giao dịch có thể bị thực hiện hai lần. Vì vậy:

- Mỗi command có side effect nên mang idempotency key ổn định.
- Consumer lưu key đã xử lý trong cùng transaction với business update.
- Response nên trả kết quả của lần xử lý trước nếu key đã tồn tại.
- Với stream sự kiện, dùng event ID/sequence để deduplicate.
- Với job dài hạn, lưu trạng thái job và cursor trong database.

RSocket resume và idempotency giải quyết hai vấn đề khác nhau: một bên duy trì continuity của protocol, bên kia bảo vệ semantics nghiệp vụ khi có retry hoặc replay.

## 13. Kiểm thử session expiry và frame buffer

Ngoài server restart, hãy chủ động làm session không thể resume:

| Cách tạo điều kiện | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Session hết hạn | Chờ lâu hơn sessionDuration trước khi reconnect. | Server không còn giữ session và từ chối RESUME. |
| Token không tồn tại | Gửi RESUME với token không được session manager nhận diện trong test protocol/custom harness. | ERROR[REJECTED_RESUME]. |
| Frame buffer không còn liên tục | Giảm giới hạn retention hoặc tạo tình huống vị trí cần phát lại đã bị loại khỏi store. | Server từ chối vì không thể phát lại đủ frame. |
| Server không hỗ trợ resume | Dùng test server nhận RESUME nhưng không có capability. | ERROR[REJECTED_RESUME]. |
| Client restart | Dừng JVM client và tạo client process mới không còn token/frame state. | Client tạo SETUP mới; không thể resume session cũ chỉ bằng application config. |

Không chỉnh sửa protocol frame bằng tay trong test nghiệp vụ thông thường. Với token hoặc implied position sai, chỉ nên dùng low-level protocol test nếu cần xác minh parser và error code. Phần lớn integration test có thể kiểm tra session expiry hoặc khởi động server instance mới để tạo tình huống từ chối có thật.

## 14. Test matrix

Một bộ kiểm thử tốt nên xác minh cả frame-level outcome và application-level behavior:

| Test case | Network/server action | Protocol expectation | Application expectation |
| --- | --- | --- | --- |
| Resume thành công | Cắt mạng ngắn, server còn sống | RESUME → RESUME_OK | Stream cũ tiếp tục. |
| Mạng chậm | Thêm latency/jitter | Connection vẫn hoạt động hoặc timeout theo ngưỡng | Không tạo request trùng chỉ vì response chậm. |
| Session hết hạn | Chờ quá session duration | REJECTED_RESUME | Tạo connection mới và resubscribe bằng cursor. |
| Server restart | Dừng A, bật B với state mới | REJECTED_RESUME | Không giả định stream cũ tự tiếp tục. |
| Client restart | Dừng rồi tạo client process mới | SETUP mới | Khôi phục theo application cursor. |
| Frame buffer thiếu | Làm mất khả năng phát lại frame | REJECTED_RESUME | Có fallback nghiệp vụ. |
| Resume retry hết giới hạn | Giữ mạng lỗi lâu hơn retry policy | Resume flow kết thúc lỗi | Báo trạng thái unavailable, không loop vô hạn. |
| Side effect và response mất | Cho server commit rồi cắt response | Có thể replay frame/request theo session | Idempotency ngăn xử lý nghiệp vụ hai lần. |
| Nhiều stream đồng thời | Mở nhiều interaction trước khi cắt mạng | Các stream được phục hồi theo session | Không trộn event giữa các stream. |

## 15. Ghi nhận protocol frame và log

Khi kiểm thử, cần quan sát được:

- Thời điểm phát hiện transport disconnect.
- Thời điểm bắt đầu reconnect/resume.
- RESUME được gửi hay client chuyển sang connection mới.
- Server trả RESUME_OK hay ERROR[REJECTED_RESUME].
- Resume token nên được log dưới dạng hash hoặc ID rút gọn, không ghi token thô.
- Session duration và thời gian từ disconnect tới lần resume.
- Số frame đang chờ trong retransmission buffer.
- Số interaction được phục hồi hoặc phải tạo lại.
- Số lần application-level replay/resubscribe.

Không ghi payload hoặc resume token nhạy cảm vào log. Với test, có thể dùng protocol interceptor hoặc wire logging của RSocket Java ở mức phù hợp. Wire log cần được tắt hoặc che dữ liệu trước khi chạy production.

Metric gợi ý:

| Metric | Ý nghĩa |
| --- | --- |
| rsocket_resume_attempts_total | Tổng số lần client thử resume. |
| rsocket_resume_success_total | Số lần server chấp nhận resume. |
| rsocket_resume_rejected_total | Số lần nhận REJECTED_RESUME. |
| rsocket_resume_duration | Thời gian từ disconnect đến khi interaction tiếp tục. |
| rsocket_resume_buffer_bytes | Dung lượng frame đang giữ để phát lại. |
| rsocket_transport_disconnects_total | Số lần transport bị ngắt. |
| rsocket_application_resubscribe_total | Số lần phải tạo lại stream ở tầng ứng dụng. |

Giữ metric label có cardinality thấp. Không dùng resume token, session ID hoặc user ID làm label.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Client không gửi RESUME | Chưa bật .resume(...) hoặc connector không được cấu hình đúng. | Kiểm tra rsocketConnector và log connector. |
| Server trả REJECTED_SETUP ngay khi kết nối | Client yêu cầu resume nhưng server không bật capability. | Bật resume ở server hoặc không yêu cầu resume trong SETUP. |
| Server trả REJECTED_RESUME sau restart | Instance mới không có session/token/frame state cũ. | Dùng SETUP mới và application-level resubscribe. |
| Resume thất bại sau khi chờ lâu | Session duration đã hết. | Điều chỉnh session duration và retry window theo SLA. |
| Resume bị từ chối khi tải cao | Frame buffer không giữ được khoảng frame cần phát lại hoặc giới hạn bộ nhớ quá thấp. | Đo buffer, retention và tốc độ producer/consumer. |
| Client retry RESUME vô hạn sau REJECTED_RESUME | Không phân biệt rejection với lỗi transport tạm thời. | Dừng resume session cũ; tạo connection mới theo chính sách. |
| Stream tiếp tục nhưng nghiệp vụ bị lặp | Retry/replay side effect không idempotent. | Thêm idempotency key, inbox hoặc event sequence. |
| Client kết nối replica khác và bị từ chối | Session state chỉ nằm ở replica ban đầu. | Dùng sticky routing trong thời gian session hoặc thiết kế shared/durable session state. |
| Test không thấy disconnect | Client kết nối thẳng tới server, bỏ qua proxy hoặc thời gian chờ quá ngắn. | Bảo đảm client đi qua Toxiproxy và đợi keepalive timeout. |

## 17. Checklist triển khai và kiểm thử

- [ ] Bật resume ở cả client và server.
- [ ] Đặt session duration dài hơn khoảng gián đoạn mạng dự kiến.
- [ ] Cấu hình keepalive để phát hiện mất kết nối theo SLA.
- [ ] Giới hạn retry và thời gian phục hồi ở client.
- [ ] Đo frame buffer và dung lượng bộ nhớ khi nhiều stream hoạt động.
- [ ] Dùng Toxiproxy/Testcontainers để mô phỏng latency, blackhole và TCP close.
- [ ] Kiểm thử RESUME_OK khi server vẫn giữ session.
- [ ] Kiểm thử REJECTED_RESUME khi token/session/frame buffer không còn.
- [ ] Restart server process để xác minh state trong RAM bị mất.
- [ ] Restart client để xác minh token/frame state phía client không tự được khôi phục.
- [ ] Sau REJECTED_RESUME, không thử lại session cũ; tạo SETUP mới.
- [ ] Dùng cursor, event ID và idempotency key để khôi phục nghiệp vụ.
- [ ] Ghi nhận protocol outcome, thời gian phục hồi và số lần resubscribe.

## 18. Ghi nhớ

- RSocket resume là capability tùy chọn và có tính optimistic; nó không bảo đảm mọi lần mất mạng đều khôi phục được.
- Client gửi RESUME bằng token của SETUP ban đầu; server trả RESUME_OK nếu state và frame positions còn đủ.
- Resume yêu cầu cả client và server giữ session state cùng frame buffer trong thời gian gián đoạn.
- Sau ERROR[REJECTED_RESUME], client không được thử resume session đó lần nữa.
- REJECTED_SETUP xảy ra khi setup ban đầu có yêu cầu resume nhưng server không chấp nhận; REJECTED_RESUME xảy ra khi khôi phục session cũ thất bại.
- Network interruption ngắn có thể resume thành công nếu server process và session state còn nguyên.
- Server restart thường làm mất in-memory session manager và frame store; instance mới không tự biết token cũ.
- RSocket Java có RSocketConnector.resume(...) ở client và RSocketServer.resume(...) ở server; Spring cho phép cấu hình connector qua RSocketRequester.Builder.
- reconnect tạo connection mới, còn resume cố tiếp tục session và interaction cũ.
- Resume không tạo exactly-once cho nghiệp vụ; command có side effect vẫn cần idempotency.
- Sau khi resume bị từ chối, dùng SETUP mới và khôi phục stream từ cursor/sequence ở tầng ứng dụng.

## Tài liệu tham khảo

- [RSocket Protocol — Resuming Operation, RESUME và RESUME_OK](https://rsocket.io/about/protocol/)
- [RSocket Java — RSocketConnector API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java — RSocketServer API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java — Resume State and Frame Store](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/resume/package-summary.html)
- [Spring Framework — RSocketRequester Advanced Configuration](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Testcontainers — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/)
