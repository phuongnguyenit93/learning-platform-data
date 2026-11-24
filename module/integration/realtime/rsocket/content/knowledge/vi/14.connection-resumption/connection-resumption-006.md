# Điều kiện resume thành công và trường hợp REJECTED_RESUME

RSocket có thể duy trì một session logic khi kết nối mạng bị gián đoạn tạm thời. Khi transport được thiết lập lại, requester có thể yêu cầu tiếp tục session trước đó bằng cơ chế **connection resumption**. Nếu hai phía còn giữ đúng trạng thái session và dữ liệu cần phát lại, các interaction đang hoạt động có thể tiếp tục mà không phải khởi tạo lại toàn bộ RSocket session.

Resume không đơn giản là mở một TCP connection mới rồi gửi lại request. Hai phía phải nhận diện đúng session, đối chiếu vị trí dữ liệu đã nhận và còn giữ đủ các frame cần phát lại. Nếu token không hợp lệ, session đã bị loại bỏ hoặc replay buffer không còn phần dữ liệu cần thiết, responder có thể trả về **REJECTED_RESUME**. Khi đó client cần chuyển sang một session mới và xử lý các thao tác chưa rõ kết quả theo chính sách nghiệp vụ.

Bài học này tập trung vào điều kiện resume thành công, vai trò của token và position, vòng đời replay buffer, nguyên nhân REJECTED_RESUME và cách thiết kế fallback an toàn trong Java/Spring RSocket.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt reconnect transport với resume một RSocket session.
- Giải thích vai trò của resume token, position và replay buffer.
- Mô tả handshake RESUME và RESUME_OK ở hai chiều truyền dữ liệu.
- Xác định điều kiện để server chấp nhận resume.
- Nhận biết các nguyên nhân dẫn đến REJECTED_RESUME.
- Thiết kế thời gian lưu session, dung lượng replay buffer và định tuyến reconnect.
- Xử lý fallback sang session mới mà không giả định request nghiệp vụ được thực thi đúng một lần.

## 1. Reconnect và resume là hai việc khác nhau

Khi TCP hoặc WebSocket bị ngắt, transport connection cũ không còn dùng được. Ứng dụng có thể mở một transport connection mới, nhưng điều đó chưa có nghĩa RSocket session cũ đã được khôi phục.

Có hai hướng:

| Hướng | Điều gì xảy ra? | Trạng thái interaction cũ |
|---|---|---|
| Reconnect thông thường | Thiết lập một RSocket session mới bằng SETUP | Session cũ và stream cũ không tự được khôi phục |
| Resume | Thiết lập transport mới rồi yêu cầu peer tiếp tục session đã lưu | Có thể tiếp tục các interaction và replay frame còn thiếu nếu trạng thái vẫn tồn tại |

Resume hữu ích cho kết nối realtime dài hạn, chẳng hạn dashboard, telemetry, notification hoặc channel hai chiều. Nó giảm nhu cầu khởi tạo lại session sau một lần mất mạng ngắn. Tuy nhiên, resume chỉ thành công khi các điều kiện protocol và trạng thái ở cả hai phía còn đáp ứng.

### 1.1. Resume phải được bật từ session ban đầu

Requester và responder cần hỗ trợ extension resumption. Trong quá trình SETUP ban đầu, requester thông báo khả năng resume và cung cấp resume token. Peer lưu trạng thái cần thiết để có thể xác nhận session này nếu transport bị mất.

Nếu session ban đầu không được thiết lập ở chế độ resume, một reconnect thông thường không thể tự biến nó thành resumable session. Muốn có resume, phải cấu hình và thương lượng khả năng này ngay từ đầu.

### 1.2. Resume giữ session protocol, không tự khôi phục mọi thứ trong ứng dụng

Resume khôi phục trạng thái RSocket protocol và tiếp tục việc trao đổi frame còn thiếu. Nó không tự khôi phục:

- Transaction database đã rollback hoặc commit.
- State nằm trong bộ nhớ của một service khác mà không được quản lý theo session.
- Công việc nền đã bị process kill.
- Dữ liệu đã hết hạn trong cache hoặc message broker.
- Quy tắc idempotency của lệnh nghiệp vụ.

Ứng dụng vẫn phải quản lý vòng đời nghiệp vụ, tính bền vững của dữ liệu và tính idempotent của các thao tác có side effect.

## 2. Những thành phần cần thiết cho resume

Một resumable session cần giữ nhiều loại trạng thái:

| Thành phần | Vai trò |
|---|---|
| Resume token | Nhận diện session cần tiếp tục |
| Resume position | Xác định ranh giới dữ liệu đã nhận trong mỗi chiều |
| Replay buffer | Lưu frame đã gửi nhưng peer có thể chưa nhận |
| Receive position | Theo dõi dữ liệu đã nhận từ peer |
| Session state | Giữ các interaction và state protocol đang hoạt động |
| Retention policy | Quyết định session và replay data được giữ bao lâu |

Resume chỉ có thể thành công nếu peer tìm được session tương ứng và có đủ dữ liệu để đồng bộ lại hai chiều.

### 2.1. Resume token

Resume token là giá trị nhận diện session. Khi reconnect, requester gửi lại token để peer tìm session đã lưu.

Token phải được tạo và quản lý bởi cơ chế resumption của implementation. Không tự dùng user ID, connection ID dễ đoán hoặc một chuỗi cố định làm resume token. Token không thay thế credential xác thực; server vẫn cần áp dụng bảo mật và authorization phù hợp cho kết nối mới.

Token nên được coi là dữ liệu nhạy cảm:

- Không ghi nguyên token vào log.
- Không gửi token qua kênh không được bảo vệ.
- Không tái sử dụng token cho session không liên quan.
- Xóa state và token khi session hết hạn hoặc bị đóng theo chính sách.

### 2.2. Position và replay buffer

Resume protocol theo dõi vị trí dữ liệu trong luồng frame của mỗi chiều truyền. Position biểu diễn offset tích lũy theo byte của dữ liệu frame trong session, không phải số lượng request hay số lượng payload.

Ví dụ, một peer đã phát các frame có tổng chiều dài 4.000 byte. Peer còn giữ replay buffer bắt đầu từ position 2.500. Nếu bên kia đã xác nhận nhận đến position 3.000, peer có thể phát lại phần dữ liệu sau vị trí đã nhận vì buffer vẫn bao phủ phần còn thiếu.

Replay buffer cần giữ frame đã gửi nhưng chưa được peer xác nhận. Khi peer nhận resume position, implementation xác định frame nào cần replay và frame nào đã được nhận. Dữ liệu đã được xác nhận có thể được loại khỏi buffer theo chính sách của implementation.

Điều quan trọng là resume position không phải sequence number của sự kiện nghiệp vụ. Nó là vị trí trong luồng frame của RSocket session. Nếu ứng dụng cần phát hiện thiếu hoặc trùng bản ghi nghiệp vụ, vẫn nên có event ID hoặc sequence number riêng ở tầng domain.

## 3. Handshake RESUME và RESUME_OK

Khi transport mới được mở, requester gửi frame RESUME thay vì bắt đầu một session mới bằng SETUP thông thường. Frame này mang thông tin phiên bản, resume token và vị trí dữ liệu cần đồng bộ.

Ở mức khái niệm, RESUME mang:

- Protocol version.
- Resume token để nhận diện session.
- Last received server position: vị trí cuối cùng requester đã nhận từ server.
- First available client position: vị trí sớm nhất của dữ liệu phía client còn có thể phát lại cho server.

Nếu responder xác nhận session và dữ liệu còn đủ, nó trả về RESUME_OK kèm vị trí cuối cùng đã nhận từ client. Hai phía sau đó phát lại các frame còn thiếu và tiếp tục trao đổi trên transport mới.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    Note over C,S: Transport cũ bị ngắt, session state vẫn được giữ
    C->>S: Mở transport mới
    C->>S: RESUME (token, last server position, first client position)
    S->>S: Tìm session và kiểm tra replay range
    S-->>C: RESUME_OK (last received client position)
    S-->>C: Replay frame server còn thiếu
    C->>S: Replay frame client còn thiếu
    Note over C,S: Tiếp tục các interaction trên session cũ
~~~

Sơ đồ mô tả trình tự logic. Thứ tự truyền frame replay thực tế do RSocket implementation quản lý; ứng dụng không tự tạo RESUME hoặc RESUME_OK bằng payload nghiệp vụ.

### 3.1. Vì sao cần position ở cả hai chiều?

RSocket là giao thức hai chiều. Trong khi kết nối bị gián đoạn, cả requester lẫn responder đều có thể đã gửi frame mà peer chưa nhận được.

- Requester cần cho responder biết mình đã nhận đến đâu trong luồng server gửi.
- Requester cũng phải cho biết frame sớm nhất phía mình còn giữ để responder có thể yêu cầu phát lại phần dữ liệu client gửi.
- Responder phản hồi vị trí cuối cùng nó đã nhận từ requester.

Nhờ đó, hai phía có thể xác định khoảng dữ liệu cần replay theo từng chiều. Nếu một phía đã loại bỏ frame mà peer vẫn chưa nhận, khoảng dữ liệu đó không thể được phục hồi từ replay buffer và resume có thể bị từ chối.

### 3.2. Resume không phải gửi lại toàn bộ request

Requester không tạo lại từng request nghiệp vụ bằng cách gọi lại API client. RSocket resumption làm việc ở tầng frame/session: các frame chưa được peer nhận được replay theo position.

Điều này khác với retry ở tầng ứng dụng. Retry tạo một thao tác mới và có thể gây side effect lặp nếu request trước đã đến server nhưng response chưa đến client. Resume tiếp tục session cũ nếu trạng thái còn tồn tại.

## 4. Điều kiện để resume thành công

Resume thành công cần đồng thời thỏa mãn các điều kiện chính:

1. Session ban đầu đã bật và thương lượng resumption.
2. Requester còn resume token tương ứng với session cũ.
3. Responder nhận diện được token và session chưa bị loại bỏ.
4. Protocol version và extension cần thiết tương thích.
5. Replay buffer của mỗi phía còn bao phủ các frame mà peer chưa nhận.
6. Các position được gửi trong RESUME nhất quán với trạng thái đã lưu.
7. Transport mới được thiết lập thành công đến đúng peer có state session, hoặc đến một node có thể truy cập state đó.
8. Session chưa vượt retention duration mà implementation cho phép.

Chỉ mở lại TCP/WebSocket thành công là chưa đủ. Nếu transport mới kết nối đến một node khác không có session state, peer đó có thể không nhận diện token và từ chối resume.

### 4.1. Cùng session token và đúng peer

Requester phải gửi token của session đang cần khôi phục. Nếu token bị thay đổi, bị cắt cụt hoặc thuộc session khác, responder không thể tìm đúng state.

Trong môi trường nhiều node, cần một trong các cách:

- Sticky routing để reconnect về đúng node đang giữ session.
- Một cơ chế lưu/chia sẻ resumable session state mà implementation hỗ trợ.
- Một tầng điều phối đảm bảo session được phục hồi trên node có đầy đủ replay state.

Chỉ chia sẻ resume token giữa các node không đủ. Node đích còn cần replay buffer, position và state của các interaction đang hoạt động.

### 4.2. Replay buffer còn đủ dữ liệu

Giả sử requester báo rằng nó đã nhận server đến position 8.000. Responder phải còn giữ các frame cần thiết sau position này. Nếu replay buffer đã bị trim và chỉ còn dữ liệu từ position 9.500, responder không thể gửi lại phần 8.000 đến 9.500.

Tương tự, responder có thể cần requester phát lại dữ liệu client đã gửi. Nếu requester không còn giữ các frame từ vị trí mà responder cần, session cũng không thể đồng bộ đầy đủ.

Vì thế, resume thành công phụ thuộc vào khả năng lưu trữ của cả hai phía. Tăng retention time nhưng không tăng replay buffer có thể không giúp resume nếu lưu lượng phát sinh làm buffer tràn trước khi hết thời gian.

### 4.3. Resume trong thời gian session còn được giữ

Khi transport bị ngắt, implementation giữ session state trong một khoảng thời gian cấu hình. Nếu requester reconnect trong khoảng này và các điều kiện khác còn đúng, resume có thể thành công.

Nếu mất mạng lâu hơn retention duration, server có thể đã giải phóng session và replay buffer. Requester khi đó không thể tiếp tục session cũ.

Retention duration nên được chọn theo thời gian gián đoạn mạng mà hệ thống muốn hỗ trợ, dung lượng bộ nhớ và lưu lượng frame trung bình. Không đặt thời gian giữ quá dài nếu không có ngân sách bộ nhớ và chính sách cleanup.

## 5. REJECTED_RESUME là gì?

**REJECTED_RESUME** là mã lỗi RSocket cho biết peer từ chối yêu cầu resume. Đây là lỗi ở phạm vi connection/session, không phải lỗi nghiệp vụ của một stream riêng lẻ.

Peer có thể từ chối resume khi không thể tiếp tục session một cách an toàn. Các nguyên nhân thường gặp:

| Nguyên nhân | Vì sao resume không thể tiếp tục? |
|---|---|
| Resume token không được nhận diện | Không tìm thấy session tương ứng |
| Session đã hết retention | State và replay buffer đã bị giải phóng |
| Replay buffer thiếu frame | Không thể phát lại đầy đủ dữ liệu peer chưa nhận |
| Position không còn nằm trong replay range | Peer yêu cầu dữ liệu cũ hơn phần còn lưu |
| Reconnect đến node không giữ session | Node mới không có state để khôi phục |
| Resume extension không được bật hoặc không tương thích | Hai phía không thể thực hiện đúng handshake |
| Session đã bị đóng hoặc invalidated | State không còn hợp lệ để tiếp tục |

Khi nhận REJECTED_RESUME, requester phải coi session cũ không thể tiếp tục qua lần resume đó. Mở transport mới bằng SETUP có thể tạo session mới, nhưng không khôi phục các interaction và frame state đã mất của session cũ.

### 5.1. REJECTED_RESUME khác lỗi transport

Không phải mọi lần resume thất bại đều trả REJECTED_RESUME:

- DNS, TCP connect hoặc TLS handshake thất bại: transport mới chưa được thiết lập.
- Timeout trong lúc gửi RESUME hoặc chờ phản hồi: chưa biết peer đã nhận hoặc xử lý frame đến đâu.
- REJECTED_RESUME: peer đã xử lý yêu cầu resume và chủ động từ chối session cũ.
- Lỗi application trên một stream: interaction cụ thể gặp lỗi, nhưng không nhất thiết session connection bị từ chối resume.

Phân loại đúng lỗi giúp client quyết định nên thử lại transport, thử resume lần nữa trong retention window hay chuyển sang session mới.

### 5.2. Không retry resume vô hạn

Nếu token đã bị từ chối hoặc replay range đã mất, gửi lại cùng một RESUME với cùng state thường không giải quyết được nguyên nhân. Client nên:

1. Ghi nhận session cũ không còn resumable.
2. Dừng vòng retry resume cho session đó.
3. Thực hiện quy trình tạo session mới nếu nghiệp vụ cho phép.
4. Đồng bộ lại trạng thái ứng dụng từ nguồn dữ liệu có thẩm quyền.
5. Xử lý các thao tác chưa rõ kết quả bằng idempotency hoặc truy vấn trạng thái.

Nếu nguyên nhân là lỗi transport tạm thời và session vẫn còn, retry resume với backoff có thể phù hợp. Phải phân biệt timeout transport với REJECTED_RESUME rõ ràng.

## 6. Ví dụ vòng đời session

Giả sử một dashboard mở request-stream để nhận trạng thái thiết bị. Kết nối bị ngắt trong lúc server đang gửi dữ liệu:

~~~text
T0  Client mở RSocket session có resume.
T1  Server gửi event A, B, C.
T2  Client xác nhận đã nhận đến position chứa A và B.
T3  Mạng bị ngắt trước khi C được xác nhận.
T4  Hai phía giữ session state và replay buffer.
T5  Client mở transport mới và gửi RESUME.
T6  Server kiểm tra token, position và replay range.
T7  Nếu hợp lệ: RESUME_OK, replay C rồi tiếp tục stream.
~~~

Nếu client quay lại sau khi server đã giải phóng session hoặc frame C không còn trong replay buffer, server có thể trả REJECTED_RESUME. Client cần tạo session mới và lấy lại trạng thái từ API/query hoặc event store có khả năng đồng bộ.

### 6.1. Resume thành công

~~~mermaid
flowchart TD
    A["Transport bị ngắt"] --> B["Giữ session và replay buffer"]
    B --> C["Requester reconnect trong retention"]
    C --> D["Gửi RESUME với token và positions"]
    D --> E{"Token và replay range hợp lệ?"}
    E -- Có --> F["RESUME_OK"]
    F --> G["Replay frame còn thiếu"]
    G --> H["Tiếp tục session cũ"]
    E -- Không --> I["REJECTED_RESUME"]
~~~

### 6.2. Resume bị từ chối

Khi resume bị từ chối, không nên tự giả định các event trước đó đã được xử lý đầy đủ hoặc chưa được xử lý. Client có thể không biết server đã nhận frame cuối cùng trước khi transport đứt hay chưa.

Đối với stream đọc dữ liệu, client có thể tạo session mới rồi truy vấn từ một checkpoint nghiệp vụ đã lưu. Đối với command có side effect, cần gửi idempotency key hoặc truy vấn trạng thái command trước khi quyết định gửi lại.

## 7. Cấu hình retention và replay buffer

Resume là sự đánh đổi giữa khả năng phục hồi và tài nguyên lưu trữ. Session càng được giữ lâu và lưu lượng frame càng lớn thì replay buffer có thể chiếm càng nhiều bộ nhớ.

### 7.1. Retention duration

Retention duration quyết định session state được giữ sau khi transport mất kết nối trong bao lâu. Khi chọn giá trị, cần cân nhắc:

- Thời gian gián đoạn mạng phổ biến và thời gian outage mục tiêu.
- Số lượng session đồng thời.
- Tốc độ phát frame trung bình và đỉnh.
- Dung lượng bộ nhớ dành cho session.
- Chính sách cleanup khi server quá tải hoặc restart.

Retention quá ngắn làm resume thất bại với outage dài. Retention quá dài có thể giữ state của các client không bao giờ quay lại và làm tăng memory pressure.

### 7.2. Replay buffer capacity

Replay buffer phải đủ để giữ các frame chưa được xác nhận trong khoảng gián đoạn mà hệ thống muốn hỗ trợ. Ước lượng sơ bộ:

<math block value="B \\approx R \\times T"/>

Trong đó:

- B là dung lượng byte cần giữ cho một chiều của session.
- R là tốc độ phát dữ liệu tính bằng byte/giây.
- T là thời gian gián đoạn mục tiêu tính bằng giây.

Ví dụ, nếu một chiều phát trung bình 200 KB/s và muốn chịu gián đoạn 15 giây:

<math block value="B \\approx 200\\ \\text{KB/s} \\times 15\\ \\text{s} = 3\\ \\text{MB}"/>

Đây là ước lượng đơn giản cho một chiều và chưa tính overhead, burst, metadata hay hệ số an toàn. Hai chiều có thể cần buffer riêng. Cần đo p95/p99 throughput và burst thực tế thay vì chỉ dựa vào mức trung bình.

### 7.3. Buffer overflow và retention

Nếu buffer đầy trước khi session hết retention, implementation có thể không còn đủ frame để resume. Tăng retention duration mà không xử lý buffer capacity không loại bỏ nguy cơ này.

Các cách giảm rủi ro:

- Giới hạn tốc độ phát hoặc kích thước payload.
- Cấp buffer theo mức dịch vụ hoặc loại session.
- Giảm số interaction và stream không cần thiết.
- Theo dõi số byte replay buffer đang dùng.
- Dọn session đã hết hạn đúng thời điểm.
- Chọn chiến lược fallback nếu session không thể resume.

Không dùng một buffer không giới hạn cho mọi session. Một số lượng lớn connection bị mất đồng thời có thể làm bộ nhớ tăng nhanh nếu state được giữ mà không có quota.

## 8. Ví dụ Java và Spring RSocket

Resumption được triển khai ở tầng RSocket connection, không phải trong từng method @MessageMapping. Handler vẫn trả về Mono hoặc Flux bình thường; connector và server transport quản lý resume token, position và replay buffer.

### 8.1. Cấu hình theo vai trò

Ở phía client, cần cấu hình RSocket connector để:

- Bật resumption.
- Chọn thời gian giữ session và giới hạn replay state theo API implementation.
- Thiết lập retry/backoff cho lần thiết lập transport mới.
- Giữ connector/session context cần thiết qua lần transport reconnect.

Ở phía server, cần:

- Bật khả năng resume trong RSocket server.
- Giữ session state và replay buffer theo từng connection.
- Áp dụng giới hạn bộ nhớ và retention.
- Đảm bảo reconnect được định tuyến đến node có state hoặc cơ chế state sharing tương thích.

Tên builder method và overload cụ thể thay đổi theo phiên bản rsocket-java và Spring RSocket. Vì vậy, cần kiểm tra API của dependency thực tế thay vì sao chép cấu hình từ phiên bản khác. Không nên viết một vòng reconnect TCP riêng rồi coi đó là resumption.

### 8.2. Handler không cần tự phát lại frame

Ví dụ handler stream:

~~~java
@Controller
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("devices.state")
    public Flux<DeviceState> states(
            @Payload DeviceQuery query,
            Principal principal) {

        return deviceService.watchAuthorized(
                principal.getName(),
                query.deviceId());
    }
}
~~~

Handler trả về một publisher theo cách thông thường. Khi session được resume thành công, RSocket protocol layer xử lý replay frame cần thiết. Ứng dụng không tự gửi lại toàn bộ state bằng cách gọi lại method handler trên cùng session.

### 8.3. Fallback sau REJECTED_RESUME

Khi peer trả REJECTED_RESUME, client có thể đóng trạng thái session cũ và thiết lập session mới. Ứng dụng cần quyết định cách đồng bộ lại:

~~~java
public Flux<DeviceEvent> resyncDevice(
        String deviceId,
        long lastProcessedSequence) {

    return deviceService.eventsAfter(
            deviceId,
            lastProcessedSequence);
}
~~~

Đây là ví dụ minh họa đồng bộ theo sequence nghiệp vụ. lastProcessedSequence và sequence của event store thuộc domain; chúng không phải resume position của RSocket. Nếu checkpoint đã cũ hơn thời gian lưu event, ứng dụng có thể tải snapshot mới rồi tiếp tục nhận event từ sequence của snapshot để tránh bỏ sót thay đổi trong khoảng mất kết nối.

## 9. Resume và tính đúng đắn nghiệp vụ

Resume giúp tiếp tục trao đổi frame trong một session còn đủ state. Tuy nhiên, ứng dụng không nên suy ra rằng mọi command được thực thi đúng một lần chỉ nhờ resume.

Có những tình huống client không biết kết quả:

- Request đã đến server, server đã thực hiện side effect, nhưng response chưa tới client.
- Transport bị ngắt trước khi client nhận được acknowledgement.
- Session không thể resume và client phải tạo session mới.
- Client retry command trong session mới trong khi command cũ đã được xử lý.

### 9.1. Idempotency key

Với thao tác có side effect, gắn một idempotency key duy nhất cho ý định nghiệp vụ. Server lưu key cùng trạng thái và kết quả xử lý trong phạm vi user/tenant phù hợp. Khi client retry sau REJECTED_RESUME, server có thể trả lại kết quả cũ thay vì thực hiện side effect lần nữa.

Idempotency key cần được lưu bền vững đủ lâu so với cửa sổ retry. Không chỉ lưu trong bộ nhớ của connection vì connection mới có thể được tạo trên node khác.

### 9.2. Sequence nghiệp vụ cho stream dữ liệu

Đối với event stream, mỗi event có thể mang sequence tăng dần theo nguồn:

~~~java
public record DeviceEvent(
        String deviceId,
        long sequence,
        DeviceState state,
        Instant occurredAt) {
}
~~~

Khi resume thành công, RSocket phục hồi frame theo position protocol. Khi phải tạo session mới, client dùng sequence nghiệp vụ để yêu cầu các event sau checkpoint cuối cùng đã xử lý. Hai loại position giải quyết hai lớp khác nhau:

| Position | Phạm vi | Dùng để |
|---|---|---|
| RSocket resume position | Luồng frame của một session | Replay frame chưa được peer nhận |
| Business sequence/event ID | Dòng sự kiện nghiệp vụ | Đồng bộ dữ liệu sau khi session cũ không thể phục hồi |

Không dùng resume position làm event cursor vì nó không mang ý nghĩa thứ tự nghiệp vụ.

## 10. Bảo mật và vận hành

Resume token và session state có thể cho phép tiếp tục các interaction đã được xác thực trước đó. Vì vậy, việc resume cần gắn với chính sách bảo mật của connection:

- Bảo vệ transport bằng TLS.
- Xác minh danh tính khi tạo connection và áp dụng quy tắc xác thực phù hợp khi resume.
- Không log token hoặc dữ liệu nhạy cảm trong RESUME frame.
- Giới hạn số session resumable và tổng byte replay buffer.
- Xóa state khi logout, revoke hoặc đóng session theo chính sách.
- Không để token trở thành cách vượt qua authorization hoặc tenant boundary.

Trong môi trường nhiều node, cần bảo vệ cả state chia sẻ lẫn kênh định tuyến session. Một node không có đủ state không được giả vờ resume thành công.

### 10.1. Metric nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| Resume attempts | Số lần client yêu cầu resume |
| Resume accepted | Số lần server trả RESUME_OK |
| Resume rejected | Số lần nhận REJECTED_RESUME |
| Rejection reason | Token missing, expired session, replay gap, node mismatch... nếu implementation cung cấp |
| Resume latency | Thời gian từ reconnect đến khi session hoạt động lại |
| Session retention age | Tuổi session khi được resume hoặc cleanup |
| Replay buffer bytes | Dung lượng buffer đang sử dụng |
| Replay bytes | Số byte được phát lại |
| Buffer eviction/overflow | Số lần frame cần thiết không còn được giữ |
| New-session fallback | Số lần client phải tạo session mới |

Theo dõi tỷ lệ resume thành công cùng thời gian outage và replay bytes. Tỷ lệ thất bại tăng có thể chỉ ra retention quá ngắn, buffer quá nhỏ, reconnect định tuyến sai node hoặc token lifecycle chưa phù hợp.

### 10.2. Log và trace

Log nên có một session correlation ID nội bộ, node xử lý, thời điểm mất kết nối, thời điểm resume và kết quả. Không ghi resume token nguyên văn. Nếu cần đối chiếu token, dùng fingerprint không thể đảo ngược và được tạo bằng cơ chế an toàn.

Trace của request nghiệp vụ nên tiếp tục qua session mới bằng context tracing phù hợp. RSocket resume position không thay thế trace ID hoặc correlation ID.

## 11. Các lỗi thường gặp

### Chỉ reconnect transport rồi kỳ vọng session cũ tự quay lại

Reconnect thông thường tạo một session mới. Muốn resume, session ban đầu phải bật resumption và client phải gửi RESUME với token/position phù hợp.

### Resume đến node không giữ session state

Token có thể hợp lệ ở node cũ nhưng node mới không có replay buffer. Dùng sticky routing hoặc cơ chế chia sẻ state được implementation hỗ trợ.

### Retention dài nhưng replay buffer quá nhỏ

Session còn tồn tại nhưng frame cần phát lại đã bị loại khỏi buffer. Ước lượng buffer theo throughput, thời gian outage và burst.

### Nghĩ REJECTED_RESUME là lỗi stream có thể retry tại chỗ

REJECTED_RESUME từ chối session cũ ở phạm vi connection. Dừng retry cùng session state và chuyển sang fallback session mới nếu phù hợp.

### Dùng RSocket position làm sequence nghiệp vụ

Resume position đếm offset frame. Dùng event ID hoặc sequence domain để đồng bộ dữ liệu sau khi tạo session mới.

### Retry command mà không có idempotency

Khi response bị mất, client có thể không biết command cũ đã chạy hay chưa. Kiểm tra trạng thái hoặc dùng idempotency key trước khi gửi lại.

### Giữ session không giới hạn

Session và replay buffer tiêu tốn bộ nhớ. Cần retention, quota, eviction policy và metric rõ ràng.

## 12. Kịch bản kiểm thử

Nên kiểm thử resume với các trường hợp:

1. Resume thành công khi transport ngắt ngắn và session state còn nguyên.
2. Resume token sai hoặc không tìm thấy session.
3. Resume sau khi retention duration đã hết.
4. Replay buffer không còn bao phủ position peer yêu cầu.
5. Client reconnect đến node khác không có session state.
6. Reconnect transport thất bại trước khi gửi RESUME.
7. Resume handshake timeout hoặc mất kết nối giữa RESUME và RESUME_OK.
8. Stream dài hạn tiếp tục sau RESUME_OK và frame còn thiếu được replay.
9. Client phải tạo session mới sau REJECTED_RESUME và đồng bộ theo business sequence.
10. Command có side effect được retry với idempotency key mà không tạo kết quả trùng.
11. Nhiều session mất kết nối đồng thời để kiểm tra replay buffer quota và cleanup.
12. Logout hoặc revoke credential trong khi session đang ở trạng thái resumable.

Khi kiểm thử, ghi lại cả protocol outcome và kết quả nghiệp vụ. Một lần RESUME_OK chứng minh protocol session được tiếp tục, không tự chứng minh dữ liệu ứng dụng đã được lưu bền vững đúng như mong muốn.

## 13. Checklist triển khai

Trước khi bật resumption trong production, hãy xác nhận:

1. Resumption được bật trong SETUP ban đầu ở cả hai phía.
2. Resume token được tạo, lưu và bảo vệ đúng vòng đời.
3. Resume positions được quản lý theo protocol và cả hai chiều.
4. Replay buffer đủ lớn cho thời gian outage mục tiêu và throughput thực tế.
5. Retention duration có giới hạn và cleanup rõ ràng.
6. Reconnect được định tuyến đến node có session state hoặc state sharing tương thích.
7. REJECTED_RESUME được phân biệt với lỗi transport và lỗi stream.
8. Client dừng retry resume khi session đã bị từ chối.
9. Fallback session mới có quy trình snapshot/replay theo business sequence.
10. Command có side effect được bảo vệ bằng idempotency hoặc kiểm tra trạng thái.
11. Token không bị ghi vào log và session state tuân thủ authorization.
12. Có metric cho resume success/rejection, replay bytes, buffer usage và fallback.

## 14. Tổng kết

Resume thành công khi session ban đầu đã bật resumption, token nhận diện đúng session, peer còn giữ session state, replay buffer bao phủ các frame chưa được nhận và requester reconnect trong thời gian lưu giữ cho phép. RESUME và RESUME_OK giúp hai phía đối chiếu vị trí đã nhận và phát lại frame còn thiếu theo từng chiều.

REJECTED_RESUME cho biết peer không thể tiếp tục session cũ, thường do token không hợp lệ, session hết hạn, replay buffer thiếu dữ liệu hoặc reconnect đến node không có state. Khi đó client cần tạo session mới và đồng bộ lại dữ liệu nghiệp vụ bằng snapshot, sequence hoặc idempotency. Thiết kế đúng retention, replay capacity, routing và fallback sẽ giúp RSocket phục hồi kết nối mà vẫn bảo toàn tính đúng đắn của ứng dụng.
