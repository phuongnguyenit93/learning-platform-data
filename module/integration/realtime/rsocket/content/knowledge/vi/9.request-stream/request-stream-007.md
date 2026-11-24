# Phân biệt đăng ký mới với tiếp tục một luồng đang tồn tại

## Bối cảnh: kết nối lại không đồng nghĩa tiếp tục đúng luồng cũ

RSocket hỗ trợ request-stream để client gửi một request và nhận nhiều payload theo thời gian. Ví dụ, dashboard theo dõi nhiệt độ thiết bị, ứng dụng nhận cập nhật giá hoặc dịch vụ giám sát nhận sự kiện trạng thái. Một luồng có thể chạy trong vài giây, vài giờ hoặc lâu hơn tùy nghiệp vụ.

Trong thực tế, client có thể mất kết nối, ứng dụng có thể chuyển mạng, người dùng rời màn hình rồi quay lại, hoặc một subscription bị hủy do timeout. Khi kết nối hoạt động trở lại, client cần quyết định nên mở một luồng mới, tiếp tục một phiên RSocket đã được phục hồi, hay đăng ký lại từ vị trí dữ liệu đã xử lý.

Ba hành động này có ngữ nghĩa khác nhau:

- **Đăng ký mới:** tạo một request-stream interaction mới. Server xử lý request mở đầu và tạo một stream mới với stream ID mới.
- **Resume phiên RSocket:** khôi phục một kết nối/session RSocket đã bị gián đoạn, nếu cả hai peer hỗ trợ và còn giữ trạng thái cần thiết. Các interaction đang hoạt động có thể tiếp tục trên session được phục hồi.
- **Tiếp tục ở tầng ứng dụng:** mở một request-stream mới nhưng gửi cursor hoặc sequence đã xử lý để server phát lại dữ liệu từ vị trí phù hợp.

Một request-stream không tự có khả năng phát lại chỉ vì client kết nối lại hoặc subscribe lại Flux. Muốn tiếp tục đúng dữ liệu, hệ thống phải có resume ở cấp giao thức hoặc một cơ chế cursor/replay được thiết kế ở tầng ứng dụng.

## 1. Request-stream là một interaction có danh tính riêng

Khi client khởi tạo request-stream, nó gửi một frame REQUEST_STREAM chứa request payload và nhu cầu ban đầu (initialN). Phía khởi tạo cấp stream ID để nhận diện interaction đó. Server xử lý request và phát các PAYLOAD theo nhu cầu của client.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: REQUEST_STREAM (streamId=1, initialN=4)
    S-->>C: PAYLOAD event 101
    S-->>C: PAYLOAD event 102
    S-->>C: PAYLOAD event 103
    S-->>C: PAYLOAD event 104
    C->>S: REQUEST_N (streamId=1, N=4)
    S-->>C: PAYLOAD event 105
    S-->>C: PAYLOAD event 106
~~~

Stream ID nhận diện interaction trong một session RSocket. Nó không phải ID của thiết bị, ID của subscription nghiệp vụ hoặc vị trí cuối cùng client đã đọc.

Một request-stream có vòng đời riêng:

- Bắt đầu khi requester mở interaction.
- Nhận payload theo nhu cầu được cấp.
- Có thể tiếp tục bằng các frame REQUEST_N.
- Kết thúc bình thường, kết thúc do lỗi hoặc bị hủy.
- Không thể tiếp tục sau khi đã kết thúc như thể interaction vẫn còn hoạt động.

Khi client gửi lại cùng route và cùng request payload, đó vẫn là một lần mở interaction mới. RSocket không suy luận rằng request mới là phần tiếp theo của stream trước đó chỉ vì dữ liệu request giống nhau.

## 2. Đăng ký mới tạo stream mới

Giả sử client đăng ký route sensor.readings để nhận telemetry của sensor-01. Lần đầu request có thể chứa sensor ID và một bộ lọc:

~~~java
record SensorQuery(
    String sensorId,
    double minimumTemperature
) {}

Flux<Reading> readings = requester
    .route("sensor.readings")
    .data(new SensorQuery("sensor-01", 20.0))
    .retrieveFlux(Reading.class);
~~~

Khi publisher được subscribe, RSocketRequester khởi tạo request-stream interaction. Server nhận request, tạo publisher cho route và bắt đầu phát dữ liệu theo demand.

Nếu client subscribe lại publisher theo cách tạo một interaction mới, server nhận một request-stream mới. Stream mới có stream ID riêng và có vòng đời, demand, cancellation riêng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: REQUEST_STREAM (streamId=1, sensor-01)
    S-->>C: PAYLOAD Reading A
    S-->>C: PAYLOAD Reading B
    Note over C: Kết nối bị đóng, stream cũ không còn được duy trì
    C->>S: REQUEST_STREAM (streamId=3, sensor-01)
    S-->>C: PAYLOAD Reading A
    S-->>C: PAYLOAD Reading B
    S-->>C: PAYLOAD Reading C
~~~

Ví dụ này minh họa việc đăng ký lại từ đầu. Nếu nguồn dữ liệu phát lại lịch sử hoặc query không có cursor, client có thể nhận lại các bản ghi đã đọc. Nếu nguồn chỉ phát dữ liệu mới, client có thể bỏ lỡ sự kiện xảy ra trong thời gian mất kết nối.

### Cùng request không có nghĩa cùng subscription

Hai request có cùng sensor ID và bộ lọc vẫn có thể đại diện cho hai subscription khác nhau. Một request có thể đến từ dashboard của người dùng thứ nhất; request còn lại đến từ dashboard của người dùng thứ hai. Mỗi interaction có thể có quyền truy cập, demand và vòng đời riêng.

Không dùng payload giống nhau hoặc stream ID cũ để suy ra rằng server phải gắn request mới vào subscription cũ. Nếu cần định danh một phiên theo dõi ở tầng nghiệp vụ, hãy định nghĩa subscription ID hoặc cursor riêng.

### Cold Flux và hot Flux khi subscribe lại

Reactor có hai dạng publisher thường gặp:

- **Cold publisher:** tạo hoặc thực hiện nguồn dữ liệu riêng khi mỗi subscriber đăng ký. Subscribe lại thường chạy lại nguồn từ đầu.
- **Hot publisher:** phát dữ liệu độc lập với một subscriber cụ thể. Subscriber tham gia muộn có thể chỉ nhận các phần tử phát ra từ thời điểm tham gia.

RSocket stream được tạo ở ranh giới network khi publisher tương ứng được subscribe. Nếu client tạo lại request bằng RSocketRequester, mỗi subscription mới mở một interaction mới, bất kể publisher upstream của ứng dụng là cold hay hot.

share(), replay() hoặc cache() của Reactor có thể thay đổi cách các subscriber cùng chia sẻ dữ liệu ở một process. Chúng không tự cung cấp một session RSocket bền vững qua reconnect, cũng không tự khôi phục các frame đã mất sau khi process hoặc kết nối bị mất.

## 3. Resume phiên RSocket là cơ chế ở cấp kết nối/session

RSocket định nghĩa một extension có tên **Resume** để khôi phục một session khi kết nối transport bị gián đoạn tạm thời. Client và server phải hỗ trợ, bật tính năng này và giữ đủ trạng thái session trong khoảng thời gian cho phép.

Với Resume, mục tiêu là tiếp tục session RSocket đã tồn tại. Nó khác với việc client gọi lại route để tạo một request-stream mới.

Ở mức khái quát, quá trình gồm:

1. Hai peer thiết lập session RSocket có hỗ trợ resume và trao đổi thông tin nhận diện session.
2. Trong khi session hoạt động, mỗi phía lưu trạng thái cần thiết để xác định dữ liệu giao thức đã gửi và đã nhận.
3. Nếu TCP hoặc WebSocket bị ngắt tạm thời, session có thể được giữ trong bộ nhớ hoặc kho trạng thái theo cấu hình.
4. Client kết nối lại và gửi thông tin resume token cùng vị trí giao thức đã nhận.
5. Server xác nhận session có thể tiếp tục và hai phía trao đổi lại những frame cần thiết.
6. Các interaction đang hoạt động tiếp tục theo trạng thái session được phục hồi.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    C->>S: SETUP (resume enabled)
    S-->>C: Session established
    C->>S: REQUEST_STREAM (streamId=1)
    S-->>C: PAYLOAD event 101
    S-->>C: PAYLOAD event 102
    Note over C,S: Transport connection bị ngắt
    C->>S: Kết nối lại + RESUME (token, positions)
    S-->>C: RESUME_OK
    S-->>C: Replay frame chưa được xác nhận
    S-->>C: PAYLOAD event 103
    Note over C,S: Stream cũ tiếp tục trên session được phục hồi
~~~

Các chi tiết trao đổi resume phụ thuộc giao thức và implementation. Điểm cốt lõi là peer khôi phục session đã có, thay vì nhận một REQUEST_STREAM mới cho cùng route.

### Resume token và vị trí giao thức

Resume token giúp peer nhận diện session cần phục hồi. Vị trí trong quá trình resume dùng để xác định frame nào đã được trao đổi hoặc cần phát lại trong trạng thái giao thức.

Đây là vị trí của dữ liệu giao thức trong cơ chế resume, không phải sequence number nghiệp vụ như event 1042 hoặc offset của một partition trong event log. Không dùng resume token hay vị trí frame làm cursor để truy vấn lịch sử nghiệp vụ.

### Resume có giới hạn thời gian và trạng thái

Resume chỉ thành công khi session còn khả năng phục hồi. Ví dụ, nếu server đã loại bỏ session state, resume buffer đã hết dữ liệu cần phát lại, token không còn hợp lệ hoặc thời gian lưu session đã hết, peer không thể tiếp tục session cũ.

Một kết nối mới thành công không tự chứng minh session cũ đã được resume. Client cần phân biệt kết quả resume thành công với việc phải tạo một session mới rồi đăng ký lại các stream cần thiết.

Resume cũng không phải cơ chế lưu trữ lịch sử vô thời hạn. Nó nhằm phục hồi gián đoạn transport trong phạm vi session và chính sách lưu trạng thái được cấu hình.

### Resume không phải replay nghiệp vụ

Resume có thể phát lại các frame giao thức chưa được xác nhận để khôi phục luồng trao đổi. Nó không thay thế event store, database hoặc message log của ứng dụng.

Nếu server đã phát một event trước khi mất kết nối, nhưng ứng dụng cần truy vấn lại event đó sau khi session resume không còn khả dụng, hệ thống vẫn cần dữ liệu nghiệp vụ có thể replay. Tương tự, nếu client đã nhận frame nhưng chưa commit xử lý nghiệp vụ, ứng dụng cần cơ chế deduplication khi sự kiện được phát lại hoặc đăng ký lại.

## 4. Đăng ký lại từ cursor ở tầng ứng dụng

Nếu không dùng được RSocket Resume hoặc session đã hết hạn, ứng dụng có thể mở request-stream mới và yêu cầu server phát dữ liệu từ vị trí cuối cùng đã xử lý.

Cách này thường gọi là **application-level resume**, cursor-based replay hoặc continuation bằng sequence. Đây là quy ước của ứng dụng, không phải hành vi tự động của RSocket.

Ví dụ, mỗi sự kiện cảm biến có sequence tăng dần theo thiết bị:

~~~json
{
  "sensorId": "sensor-01",
  "sequence": 1042,
  "temperatureC": 28.4,
  "occurredAt": "2026-11-22T10:15:30Z"
}
~~~

Client đã xử lý và lưu bền vững đến sequence 1042. Khi cần mở lại luồng, client gửi query với afterSequence = 1042. Server tạo request-stream mới và phát những sự kiện có sequence lớn hơn 1042.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant L as Event Log
    C->>S: REQUEST_STREAM (afterSequence=1042)
    S->>L: Đọc sự kiện có sequence > 1042
    L-->>S: 1043, 1044, 1045
    S-->>C: PAYLOAD 1043
    S-->>C: PAYLOAD 1044
    S-->>C: PAYLOAD 1045
    Note over C,S: Interaction mới, tiếp tục dữ liệu theo cursor nghiệp vụ
~~~

Ví dụ DTO và route Spring:

~~~java
public record ReadingQuery(
    String sensorId,
    long afterSequence
) {}

public record ReadingEvent(
    String eventId,
    String sensorId,
    long sequence,
    double temperatureC,
    Instant occurredAt
) {}

@Controller
class SensorStreamController {

    private final ReadingEventService eventService;

    SensorStreamController(ReadingEventService eventService) {
        this.eventService = eventService;
    }

    @MessageMapping("sensor.readings")
    Flux<ReadingEvent> readings(ReadingQuery query) {
        return eventService.readAfter(
            query.sensorId(),
            query.afterSequence()
        );
    }
}
~~~

Mỗi lần gọi route vẫn tạo một request-stream interaction mới. Điểm khác biệt là request mang cursor để server xác định phần dữ liệu cần phát tiếp.

### Cursor nên biểu diễn điều gì?

Một cursor tốt cần có ý nghĩa rõ ràng đối với nguồn dữ liệu:

- Sequence tăng đơn điệu trong phạm vi một sensor hoặc một partition.
- Event ID có thể sắp thứ tự và truy vấn tiếp theo.
- Offset của một partition trong event log.
- Một token opaque do server cấp, chứa vị trí đọc và thông tin phiên bản.

Timestamp đơn thuần thường không đủ an toàn làm cursor. Nhiều sự kiện có thể cùng timestamp; đồng hồ giữa producer có thể lệch; độ chính xác timestamp có thể không đủ để phân biệt thứ tự. Nếu dùng thời gian, cần thêm tie-breaker ổn định như event ID hoặc sequence.

Nếu dữ liệu được phân vùng theo thiết bị hoặc tenant, cursor cần xác định rõ phạm vi. Sequence 1042 của sensor-01 không nhất thiết liên quan đến sequence 1042 của sensor-02.

### Quy ước inclusive và exclusive

Hợp đồng cursor phải nói rõ server sẽ phát từ vị trí nào:

- afterSequence = 1042 có nghĩa phát các sự kiện có sequence lớn hơn 1042.
- fromSequence = 1042 có nghĩa phát cả sự kiện 1042 trở đi.

Hai cách có thể dùng được, nhưng producer và consumer phải thống nhất. Nếu client lưu sequence cuối đã commit là 1042, cách phổ biến là truy vấn theo điều kiện sequence > 1042.

### Lưu cursor sau khi xử lý bền vững

Client chỉ nên tiến cursor sau khi sự kiện đã được xử lý theo yêu cầu nghiệp vụ và kết quả cần thiết đã commit. Nếu client lưu cursor trước rồi crash trước khi xử lý event, lần đăng ký tiếp theo sẽ bỏ qua event đó.

Một trình tự an toàn:

1. Nhận event có sequence 1043.
2. Kiểm tra event đã được xử lý hay chưa.
3. Thực hiện cập nhật nghiệp vụ.
4. Commit kết quả và sequence đã xử lý trong cùng transaction nếu chúng cùng database.
5. Sau commit, mới yêu cầu hoặc xác nhận phần dữ liệu tiếp theo theo chính sách consumer.

Nếu việc xử lý và lưu cursor không thể nằm trong cùng transaction, cần dùng event ID để deduplicate và có quy trình đối soát.

## 5. Phát lại có thể tạo dữ liệu trùng

Khi client mất kết nối, có thể xảy ra tình huống server đã gửi event 1043 nhưng client chưa kịp lưu trạng thái xử lý. Client đăng ký lại từ cursor 1042 và nhận event 1043 lần nữa.

Đây là hành vi có thể chấp nhận được nếu consumer xử lý theo kiểu at-least-once và có deduplication. Không nên giả định một cursor hoặc reconnect tự tạo ra exactly-once processing.

Một cách triển khai là lưu event ID hoặc sequence đã xử lý:

~~~java
@Transactional
public void handle(ReadingEvent event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    readingRepository.updateLatestReading(
        event.sensorId(),
        event.temperatureC()
    );

    processedEventRepository.save(event.eventId());
    cursorRepository.advance(
        event.sensorId(),
        event.sequence()
    );
}
~~~

Ví dụ giả định các thao tác lưu dữ liệu, đánh dấu event và cập nhật cursor cùng nằm trong một database transaction. Nếu event được gửi lại, consumer nhận ra event ID đã xử lý và không lặp tác dụng phụ.

Nếu một event có thể gây tác dụng phụ ở hệ thống bên ngoài, cần idempotency ở hệ thống đích hoặc outbox/inbox và đối soát. Transaction local không bảo đảm exactly-once xuyên qua network.

### Không tiến cursor vượt qua sự kiện chưa commit

Giả sử client nhận event 1043 và 1044. Nếu xử lý 1044 hoàn tất trước 1043 do xử lý song song, client không thể đơn giản lưu cursor 1044 rồi bỏ qua 1043. Cursor phải đại diện cho vị trí liên tục đã xử lý an toàn, hoặc consumer cần lưu tập hợp các sequence đã hoàn tất và chỉ tiến high-water mark khi không còn khoảng trống.

Với luồng cần giữ thứ tự, xử lý tuần tự là lựa chọn đơn giản hơn. Nếu xử lý song song để tăng throughput, cần thiết kế cơ chế commit offset theo thứ tự hoặc theo từng partition.

## 6. Snapshot kết hợp stream để bắt kịp trạng thái hiện tại

Không phải ứng dụng nào cũng cần replay toàn bộ lịch sử. Dashboard có thể chỉ cần trạng thái mới nhất rồi tiếp tục nhận cập nhật. Trong trường hợp đó, một mô hình phổ biến là lấy snapshot và cursor nhất quán, sau đó mở stream từ cursor đó.

Ví dụ:

1. Server trả snapshot thiết bị và high-watermark sequence H trong cùng một góc nhìn nhất quán.
2. Client hiển thị snapshot.
3. Client mở request-stream với afterSequence = H.
4. Server phát các event mới hơn H.
5. Client cập nhật trạng thái theo thứ tự.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant DB as State + Event Log
    C->>S: Request snapshot
    S->>DB: Đọc state và high-watermark H
    DB-->>S: Snapshot, H=1042
    S-->>C: Snapshot + cursor 1042
    C->>S: REQUEST_STREAM(afterSequence=1042)
    S->>DB: Đọc event > 1042 và theo dõi event mới
    DB-->>S: Event 1043...
    S-->>C: PAYLOAD 1043...
~~~

Điểm quan trọng là snapshot và high-watermark phải nhất quán. Nếu server đọc snapshot trước rồi mới lấy H trong một thời điểm khác, có thể bỏ sót event xảy ra giữa hai thao tác. Cần dùng transaction snapshot, log offset hoặc cơ chế tương đương để xác định ranh giới chính xác.

### Khi cursor đã quá cũ

Event log có thể chỉ giữ dữ liệu trong một khoảng thời gian. Nếu client quay lại sau khi cursor đã nằm ngoài retention, server không thể phát đầy đủ phần bị thiếu.

Server nên trả lỗi hoặc trạng thái nghiệp vụ rõ ràng như CURSOR_EXPIRED/RESYNC_REQUIRED theo hợp đồng. Client khi đó cần lấy snapshot mới và đăng ký lại từ high-watermark mới. Không âm thầm bỏ qua khoảng dữ liệu bị thiếu nếu nghiệp vụ yêu cầu đầy đủ sự kiện.

## 7. Chọn cách phục hồi theo tình huống

Không có một cơ chế duy nhất phù hợp với mọi loại gián đoạn.

| Tình huống | Hành động phù hợp | Điều kiện |
|---|---|---|
| Client muốn mở dashboard lần đầu | Đăng ký request-stream mới | Chưa có cursor hoặc không cần lịch sử |
| Client hủy stream vì không còn cần dữ liệu | Kết thúc stream; khi cần lại thì đăng ký mới | Stream cũ đã bị hủy |
| Transport mất tạm thời, session RSocket còn hợp lệ | Thử Resume phiên | Resume được hỗ trợ và session state còn hiệu lực |
| Session resume thất bại hoặc hết hạn | Mở request-stream mới từ cursor ứng dụng | Server có replay/query theo cursor |
| Client cần trạng thái hiện tại, không cần toàn bộ lịch sử | Lấy snapshot rồi stream từ high-watermark | Snapshot và cursor nhất quán |
| Event log đã xóa cursor cũ | Yêu cầu resync bằng snapshot hoặc quy trình phục hồi khác | Có chính sách retention rõ ràng |
| Client chỉ cần nhận dữ liệu mới từ thời điểm đăng ký | Mở stream live mới | Nghiệp vụ cho phép bỏ qua lịch sử trước đó |

### Quyết định theo loại dữ liệu

- **Telemetry chỉ cần giá trị mới nhất:** snapshot cộng stream live hoặc đăng ký mới với chính sách latest có thể đủ.
- **Sự kiện đơn hàng cần đầy đủ:** cursor bền vững và replay từ event log thường cần thiết.
- **Giá thị trường:** có thể lấy snapshot order book rồi nhận các cập nhật mới từ sequence nhất quán.
- **Lệnh điều khiển thiết bị:** dùng command ID/idempotency và truy vấn trạng thái trước khi gửi lại lệnh chưa rõ kết quả.
- **Thông báo người dùng:** lưu notification ID hoặc offset đã đọc để tránh bỏ sót và xử lý trùng.

## 8. Bảo mật và quyền sở hữu cursor

Cursor có thể tiết lộ vị trí đọc hoặc cho phép truy vấn lại dữ liệu. Server không nên tin cursor do client gửi mà không kiểm tra.

Một số nguyên tắc:

- Xác thực và phân quyền caller trên mỗi lần đăng ký mới.
- Ràng buộc cursor với tenant, user, thiết bị hoặc phạm vi dữ liệu được phép truy cập.
- Kiểm tra cursor có thuộc đúng route và đúng loại stream hay không.
- Dùng token opaque hoặc ký cursor nếu không muốn client tự thay đổi sequence.
- Đặt thời hạn cho cursor và quy định rõ khi cursor hết hạn.
- Không nhúng secret hoặc dữ liệu nhạy cảm trực tiếp vào cursor nếu nó có thể xuất hiện trong log hoặc telemetry.
- Giới hạn tốc độ replay để một client không yêu cầu đọc lại lượng lịch sử quá lớn.

Resume token ở cấp giao thức cũng cần được bảo vệ theo chính sách session. Không xem token đó là thông tin định danh nghiệp vụ hoặc thay thế xác thực/authorization của ứng dụng.

## 9. Kiểm thử đăng ký mới, resume và application replay

Kiểm thử cần xác nhận mỗi hành động có đúng ngữ nghĩa và không bỏ sót hoặc nhân đôi dữ liệu ngoài chính sách.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Subscribe route lần đầu | Tạo interaction mới và nhận dữ liệu theo initialN |
| Subscribe lại sau khi stream đã complete | Tạo interaction mới |
| Subscribe lại sau khi client đã cancel | Tạo interaction mới, stream cũ không được hồi sinh |
| Mở lại cùng route không cursor | Hành vi theo chính sách nguồn: live-only hoặc phát lại từ đầu |
| Mở lại với afterSequence = H | Chỉ phát dữ liệu sau H theo quy ước exclusive |
| Cùng cursor được gửi nhiều lần | Có thể nhận trùng, consumer deduplicate theo event ID/sequence |
| RSocket Resume thành công | Session và interaction đang hoạt động tiếp tục theo trạng thái đã lưu |
| Resume token hết hạn hoặc session state mất | Resume thất bại; ứng dụng chuyển sang đăng ký mới bằng cursor nếu hỗ trợ |
| Cursor nằm ngoài retention | Server yêu cầu resync thay vì âm thầm bỏ dữ liệu |
| Snapshot và high-watermark | Không có khoảng trống giữa snapshot và stream tiếp theo |

### Kiểm thử service đọc từ cursor

Ví dụ dùng StepVerifier để xác nhận quy ước afterSequence là exclusive:

~~~java
@Test
void resumesAfterLastCommittedSequence() {
    Flux<ReadingEvent> result =
        eventService.readAfter("sensor-01", 1042);

    StepVerifier.create(result)
        .expectNextMatches(event -> event.sequence() == 1043)
        .expectNextMatches(event -> event.sequence() == 1044)
        .verifyComplete();
}
~~~

Đây là unit test cho logic đọc cursor. Cần bổ sung integration test với event store thật để kiểm tra thứ tự, retention, cursor hết hạn và sự kiện phát sinh đồng thời với lúc client đăng ký.

### Kiểm thử RSocket integration

Với RSocket, hãy kiểm tra thêm:

- Mỗi lần mở route mới có một interaction và stream ID mới.
- CANCEL kết thúc stream cũ và giải phóng subscription nguồn.
- Khi bật Resume, thử ngắt transport rồi phục hồi trong thời gian session còn hiệu lực.
- Khi Resume không thành công, client không giả định stream cũ vẫn hoạt động.
- Application replay mở stream mới và gửi cursor đúng.
- Event phát lại không tạo tác dụng phụ trùng ở consumer.
- Quyền truy cập vẫn được kiểm tra khi client resume hoặc đăng ký lại.

Không phải mọi RSocket client/server hoặc cấu hình Spring đều bật Resume mặc định. Hãy kiểm tra khả năng hỗ trợ và cấu hình của implementation, rồi kiểm thử trên đúng transport và phiên bản thư viện đang triển khai.

## 10. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi lại cùng route và nghĩ đó là stream cũ | Server tạo interaction mới | Dùng Resume hoặc cursor nghiệp vụ |
| Dùng stream ID cũ làm cursor | ID giao thức không biểu diễn vị trí dữ liệu | Dùng sequence/event ID/offset |
| Nghĩ reconnect luôn resume được | Session có thể đã hết hạn hoặc không hỗ trợ Resume | Kiểm tra kết quả resume và có fallback |
| Dùng resume token làm event cursor | Nhầm trạng thái giao thức với vị trí nghiệp vụ | Quản lý hai loại token riêng |
| Chỉ dùng timestamp để tiếp tục | Có thể trùng hoặc bỏ sự kiện cùng thời điểm | Dùng sequence hoặc timestamp kèm tie-breaker |
| Lưu cursor trước khi xử lý event | Crash có thể làm mất sự kiện | Commit xử lý rồi mới tiến cursor |
| Xử lý song song rồi lưu sequence lớn nhất | Có thể bỏ qua event chưa hoàn tất ở giữa | Commit high-watermark liên tục hoặc xử lý tuần tự |
| Replay không deduplicate | Tác dụng phụ có thể lặp | Dùng event ID và xử lý idempotent |
| Không kiểm tra retention | Client yêu cầu cursor không còn dữ liệu | Trả trạng thái cần resync |
| Snapshot và cursor không nhất quán | Có thể tạo khoảng trống dữ liệu | Lấy snapshot và high-watermark cùng một ranh giới |
| Chia sẻ Flux rồi xem đó là durable subscription | Mất dữ liệu khi process hoặc session bị mất | Dùng event store và cursor bền vững |
| Tin cursor từ client | Có thể truy vấn dữ liệu ngoài phạm vi quyền | Xác thực, ký hoặc ràng buộc cursor với caller |

## Kết luận

Đăng ký mới, resume phiên RSocket và tiếp tục từ cursor nghiệp vụ là ba thao tác khác nhau. Đăng ký mới tạo request-stream interaction mới với stream ID và vòng đời mới. Resume khôi phục một session RSocket còn trạng thái, nếu hai peer hỗ trợ và session chưa hết hạn. Application replay mở stream mới nhưng yêu cầu server phát dữ liệu từ cursor đã lưu.

Với dữ liệu chỉ cần trạng thái hiện tại, snapshot cộng stream mới có thể đủ. Với sự kiện cần đầy đủ, hãy dùng sequence hoặc cursor bền vững, event log có retention, deduplication và quy tắc resync. Luôn lưu cursor sau khi xử lý bền vững, bảo vệ cursor theo danh tính caller và kiểm thử cả trường hợp resume thành công lẫn thất bại.

RSocket cung cấp cơ chế stream và có extension resume ở cấp session. Việc khôi phục chính xác tiến trình nghiệp vụ và dữ liệu đã xử lý vẫn cần được thiết kế ở tầng ứng dụng.
