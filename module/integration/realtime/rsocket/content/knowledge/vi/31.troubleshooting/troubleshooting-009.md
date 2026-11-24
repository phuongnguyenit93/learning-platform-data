# Resume thất bại do mất trạng thái hoặc bộ đệm không còn đủ

## Bối cảnh: reconnect được nhưng session cũ không thể tiếp tục

RSocket Resume cho phép hai peer khôi phục một session sau khi transport bị gián đoạn. Khi Resume thành công, các interaction đang chạy có thể tiếp tục và những frame còn thiếu được truyền lại theo vị trí giao thức. Cơ chế này hữu ích cho stream dài hạn, kết nối di động và các ứng dụng realtime cần chịu được gián đoạn mạng ngắn.

Resume là một cơ chế có điều kiện. Cả client và server phải hỗ trợ, bật Resume và giữ đủ trạng thái của session cũ. Nếu một phía mất session, token không còn được nhận diện, frame buffer bị xóa hoặc dải frame còn lại không liên tục, server có thể từ chối bằng **ERROR[REJECTED_RESUME]**.

Đây là tình huống khác với việc TCP/WebSocket không kết nối được. Transport mới có thể đã mở thành công nhưng giao thức không thể tiếp tục session cũ. Khi đó, client phải ngừng thử Resume với session đó, tạo session mới và để ứng dụng khôi phục nghiệp vụ bằng cursor/checkpoint nếu nguồn dữ liệu hỗ trợ.

Bài học này cung cấp quy trình chẩn đoán từ log và frame position, cách tìm nguyên nhân mất session state hoặc thiếu frame, cách ước lượng buffer, kiểm tra Resume store và thiết kế fallback an toàn.

## 1. Nhận diện đúng loại lỗi

Trước khi thay đổi timeout hoặc tăng buffer, hãy xác định lỗi xuất hiện ở giai đoạn nào.

| Dấu hiệu | Ý nghĩa có thể có | Hướng kiểm tra đầu tiên |
|---|---|---|
| DNS, connect refused, connect timeout | Transport mới chưa kết nối được tới server | DNS, service discovery, firewall, load balancer và port |
| TCP/WebSocket kết nối được nhưng nhận REJECTED_RESUME | Server nhận RESUME nhưng không thể tiếp tục session cũ | Token, session lookup, session expiry và frame retention |
| RejectedResumeException ở RSocket Java | Server từ chối Resume theo protocol | Đọc lý do server, kiểm tra state và vị trí frame |
| ConnectionErrorException hoặc lỗi connection-level | Kết nối bị kết thúc trong quá trình thiết lập hoặc Resume | Frame protocol, version, server log và transport |
| Resume thành công nhưng payload lặp | Frame được phát lại hoặc ứng dụng xử lý lại side effect | Event ID, idempotency và application checkpoint |
| Resume thành công nhưng stream không phát tiếp | Session được nối lại nhưng nguồn/interaction phía ứng dụng không còn hoạt động như mong đợi | Lifecycle handler, broker subscription và trạng thái nghiệp vụ |
| Reconnect tạo session mới nhưng dữ liệu bị thiếu | Ứng dụng bắt đầu lại sai cursor hoặc nguồn không hỗ trợ replay | Checkpoint, event log và snapshot/resync |

REJECTED_RESUME là lỗi ở cấp connection, không phải lỗi của một route riêng. Protocol quy định client không được tiếp tục thử Resume với cùng session sau khi nhận ERROR[REJECTED_RESUME]. Retry liên tục cùng token chỉ tạo thêm tải và log nhiễu; hãy chuyển sang quy trình tạo session mới.

### Phân biệt Resume với reconnect thông thường

Trong RSocket Java, RSocketConnector.resume(Resume) bật khả năng Resume ở client; server cũng phải bật Resume. RSocketConnector.reconnect(Retry) là cơ chế kết nối lại bằng một connection mới. Hai tùy chọn này loại trừ nhau trong API được mô tả ở RSocket Java 1.1.5; khi cấu hình cả hai, Resume được ưu tiên.

Reconnect thông thường không tự khôi phục các stream và frame đang dở của session cũ. Ứng dụng phải tạo interaction mới và khôi phục dữ liệu theo hợp đồng riêng. Đừng coi việc gọi connect thành công là bằng chứng Resume đã thành công.

## 2. Resume cần giữ trạng thái ở cả hai phía

Resume không phải một bản sao của transport connection. Nó cần trạng thái giao thức được tích lũy trước và trong lúc connection bị ngắt.

Trong một session, mỗi phía theo dõi vị trí frame đã gửi và đã nhận. Những frame có vị trí liên quan đến Resume được giữ trong store để có thể truyền lại khi cần. Khi reconnect, client gửi RESUME với token của SETUP ban đầu cùng các vị trí frame mà nó còn biết.

Vị trí này là implied position của giao thức, không phải số thứ tự stream hoặc offset nghiệp vụ. Theo protocol, REQUEST, CANCEL, ERROR và PAYLOAD tham gia chuỗi vị trí; các loại frame khác không làm tăng implied position. Vì vậy, không lấy event sequence hoặc số lượng payload trong database để thay thế frame position khi điều tra Resume.

Server cần xác định:

1. Token có nhận diện được session cũ hay không.
2. Server có giữ mọi frame cần phát lại sau vị trí cuối cùng client đã nhận hay không.
3. Client có còn giữ các frame cần phát lại sau vị trí cuối cùng server đã nhận hay không.
4. Các vị trí có hợp lệ và liên tục theo session cũ hay không.

Nếu hai phía còn đủ state, server có thể gửi RESUME_OK. Nếu không thể tiếp tục, server có thể gửi ERROR[REJECTED_RESUME].

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    participant CS as Client Resume Store
    participant SS as Server Resume Store

    C->>CS: Giữ frame đã gửi/chưa được xác nhận
    S->>SS: Giữ frame đã gửi/chưa được xác nhận
    Note over C,S: Transport bị gián đoạn
    C->>S: Mở transport mới + RESUME(token, positions)
    S->>SS: Tìm session và frame còn lưu
    S->>C: Kiểm tra vị trí client còn giữ
    alt Hai phía còn đủ dải frame
        S-->>C: RESUME_OK(server position)
        S-->>C: Phát lại frame còn thiếu
        C-->>S: Tiếp tục session
    else Thiếu session hoặc frame
        S-->>C: ERROR[REJECTED_RESUME]
        Note over C,S: Kết thúc lần Resume của session cũ
    end
~~~

Protocol Resume giả định trạng thái của hai peer được giữ qua thời gian mất kết nối. Nó không giả định rằng một peer có thể mất toàn bộ state rồi dựng lại session chỉ từ resume token. Đây là lý do restart process với store chỉ nằm trong heap thường làm Resume thất bại.

## 3. Hiểu các vị trí frame trong RESUME

RESUME mang token nhận diện session và các vị trí frame theo hai hướng. Hai trường quan trọng trong RESUME là:

- **Last Received Server Position:** vị trí cuối cùng client đã nhận từ server.
- **First Available Client Position:** vị trí sớm nhất của frame phía client mà client còn giữ để có thể phát lại.

Server cũng giữ vị trí frame của mình và vị trí gần nhất đã nhận từ client. RESUME_OK trả về vị trí cuối cùng server đã nhận từ client.

Ví dụ minh họa:

| Thông tin | Giá trị giả định | Ý nghĩa |
|---|---:|---|
| Client đã nhận từ server | 900 | Client đã nhận liên tục tới frame 900 của server |
| Client còn giữ frame gửi từ | 420 | Frame client sớm nhất còn có thể phát lại |
| Server đã nhận từ client | 418 | Server đã nhận liên tục tới frame 418 của client |
| Server còn giữ frame gửi từ | 880 | Frame server sớm nhất còn có thể phát lại |

Trong ví dụ này, server cần có frame từ 901 trở đi nếu đã phát những frame đó trước khi mất kết nối. Client cần còn frame từ 419 trở đi nếu server chưa nhận chúng. Các vị trí chỉ minh họa quan hệ; số cụ thể và cách hiển thị phụ thuộc implementation.

### Vì sao một khoảng trống nhỏ cũng có thể làm Resume thất bại?

Vị trí frame là vị trí ngầm định theo thứ tự frame, không phải offset nghiệp vụ tùy ý. Nếu store mất một frame ở giữa dải cần phát lại, peer không thể giả vờ rằng các frame sau vẫn tạo thành chuỗi liên tục.

Một store có thể còn frame mới nhất nhưng thiếu một frame cũ hơn. Điều đó vẫn không đủ để Resume. Độ mới của dữ liệu không thay thế được tính liên tục của dải frame.

Trong RSocket Java 1.1.5, ResumableFramesStore.resumeStream() trả về các frame trong store theo thứ tự; contract yêu cầu publisher kết thúc bằng lỗi nếu các frame không liên tục. Đây là dấu hiệu quan trọng khi kiểm tra custom store hoặc log của implementation.

## 4. Nhóm nguyên nhân A: server không còn nhận diện session

### 4.1 Server process đã restart

Nếu Resume state chỉ nằm trong memory, restart server sẽ xóa:

- Mapping từ resume token tới session.
- Frame buffer chưa được xác nhận.
- Vị trí frame gửi/nhận.
- Trạng thái interaction cần thiết để tiếp tục session.

Client vẫn có token cũ và có thể mở transport mới, nhưng server mới không còn dữ liệu để tìm session đó. Token hợp lệ về hình thức không có nghĩa session state còn tồn tại.

**Cách kiểm tra:**

1. So sánh thời điểm server restart với thời điểm client mất kết nối.
2. Xác định node nhận RESUME có phải node đã nhận SETUP ban đầu không.
3. Xác minh Resume store là in-memory hay có persistence/shared storage.
4. Kiểm tra session có bị cleanup trong quá trình shutdown hay không.
5. Đối chiếu log session-created, session-expired, session-disposed và resume-rejected.

Nếu yêu cầu nghiệp vụ là sống sót qua restart process, một in-memory store không đáp ứng được yêu cầu đó. Cần implementation có khả năng phục hồi session state hoặc application recovery từ durable source.

### 4.2 Client reconnect tới node khác

Trong cluster, load balancer có thể chuyển transport mới tới node khác. Nếu session chỉ tồn tại ở memory của node ban đầu, node mới không thể tiếp tục session.

| Tình huống | Kết quả có thể xảy ra |
|---|---|
| Reconnect về đúng node, session còn hạn | Có thể Resume |
| Reconnect sang node khác, không có shared state | Không tìm thấy session |
| Reconnect sang node khác, shared store có đủ state | Có thể Resume nếu implementation hỗ trợ và state nhất quán |
| Node cũ đã chết, shared store chỉ lưu token | Không đủ để khôi phục frame/session |
| Node cũ còn sống nhưng session đã hết hạn | Resume bị từ chối |

Sticky session chỉ tăng khả năng reconnect về đúng node khi node đó còn hoạt động. Nó không phục hồi state khi node owner đã chết. Nếu cần Resume xuyên node, phải có giải pháp chia sẻ/khôi phục state phù hợp với implementation.

### 4.3 Session đã hết thời hạn

Resume session có thời gian sống riêng. Server không nhất thiết giữ session vô thời hạn sau khi transport mất kết nối.

Nếu client retry sau khi session đã bị cleanup, token có thể không còn được nhận diện. Hãy đối chiếu:

- Session duration ở server.
- Thời gian client bắt đầu reconnect.
- Retry backoff, số lần retry và max elapsed time.
- TTL của session directory hoặc shared store.
- Chính sách cleanup khi keepalive hoặc transport đóng.

Cửa sổ retry của client phải nằm trong thời gian server còn giữ session, đồng thời đủ rộng cho độ trễ reconnect thực tế. Tăng retry duration phía client mà không tăng retention phía server không làm Resume thành công hơn.

### 4.4 Token không khớp hoặc bị thay đổi

Resume token phải là token của SETUP ban đầu. Các lỗi thường gặp:

- Client tạo token mới cho mỗi lần retry.
- Client dùng token của một connection khác.
- Session directory ghi đè token do collision.
- Token bị cắt, encode sai hoặc thay đổi khi lưu/đọc.
- Token hết hiệu lực theo chính sách bảo mật.
- Nhiều connection dùng chung token ngoài dự kiến.

Token nên được xem là dữ liệu opaque. Không tự phân tích hoặc biến đổi nội dung token nếu implementation không quy định. Khi log, chỉ ghi fingerprint/hash đủ để đối chiếu giữa client và server; không ghi token thô vì token có thể cho phép chiếm lại session.

### 4.5 Hai peer không còn cùng cấu hình session

Resume giả định cấu hình giao thức của session không bị thay đổi giữa SETUP và RESUME. Các khác biệt có thể làm việc tiếp tục không hợp lệ:

- Protocol version không tương thích.
- Data MIME type thay đổi.
- Metadata MIME type thay đổi.
- Cách encode/decode payload thay đổi giữa hai phiên bản ứng dụng.
- Cấu hình Resume ở client/server không đồng nhất.
- Session được phục hồi bằng code mới nhưng state cũ không tương thích.

Trong rolling deployment, hãy giữ tương thích cấu hình và định dạng trong toàn bộ cửa sổ Resume. Nếu không thể bảo đảm tương thích, từ chối Resume có kiểm soát rồi mở session mới bằng protocol/application version mới.

## 5. Nhóm nguyên nhân B: bộ đệm không còn đủ frame

### 5.1 Buffer quá nhỏ so với tốc độ phát dữ liệu

Giả sử server phát dữ liệu liên tục với tốc độ cao. Khi transport mất kết nối, peer chưa thể nhận frame mới; server phải giữ frame đã phát để có thể gửi lại. Nếu buffer chỉ đủ cho vài giây dữ liệu nhưng client offline lâu hơn, các frame cũ có thể không còn trong store.

Một ước lượng sơ bộ cho dung lượng cần giữ:

\[
B \approx R \times T \times F
\]

Trong đó:

- \(B\): dung lượng buffer ước lượng cho một hướng.
- \(R\): tốc độ byte frame được giữ mỗi giây.
- \(T\): thời gian gián đoạn tối đa cần chịu đựng.
- \(F\): hệ số dự phòng cho burst, metadata và overhead.

Ví dụ, một hướng phát trung bình 2 MB/s, cần chịu gián đoạn 20 giây và dùng hệ số dự phòng 1,5:

\[
B \approx 2 \times 20 \times 1.5 = 60\ \text{MB}
\]

Đây là ước lượng cho một session và một hướng. Hãy tính riêng chiều client-to-server và server-to-client, rồi nhân với số session đồng thời. Trong thực tế, keepalive và vị trí peer đã nhận có thể cho phép giải phóng frame trước khi hết thời gian gián đoạn; nhưng khi chưa nhận được thông tin xác nhận, hãy tính theo tình huống bảo thủ.

Không dùng một con số buffer cho mọi workload. Payload lớn, metadata dài, burst traffic và số connection đồng thời đều ảnh hưởng đến bộ nhớ cần thiết.

### 5.2 Buffer bị eviction hoặc overflow

Khi store đạt giới hạn, implementation có thể không giữ được đầy đủ frame cần thiết. Cách xử lý cụ thể phụ thuộc implementation: từ chối lưu frame, kết thúc session, làm Resume không còn khả thi hoặc phát lỗi ở bước replay.

Không giả định buffer tự tăng vô hạn hoặc tự xóa frame cũ mà vẫn Resume được. Nếu frame cũ nhất trong dải cần phát lại đã bị loại bỏ, Resume không thể khôi phục chuỗi liên tục.

**Cách kiểm tra:**

- Dung lượng store theo session và tổng dung lượng.
- Số byte frame được ghi, số byte được giải phóng.
- Số lần store chạm giới hạn.
- Frame position cũ nhất và mới nhất còn lưu.
- Số session bị cleanup hoặc eviction.
- Thời gian client offline so với tốc độ frame thực tế.

### 5.3 Store ghi frame không đầy đủ hoặc sai thứ tự

Custom Resume store cần tuân thủ contract của implementation. Các lỗi thường gặp:

- Ghi frame bất đồng bộ nhưng báo hoàn tất trước khi dữ liệu thực sự bền vững.
- Ghi frame từ nhiều thread mà không bảo toàn thứ tự.
- Bỏ qua một frame khi queue đầy.
- Cập nhật frame position trước khi frame được lưu.
- Giải phóng frame theo vị trí peer đã nhận sai.
- Khôi phục store từ snapshot không nhất quán.
- Không phân biệt session hoặc chiều truyền khi lưu frame.

Một store còn đủ số byte nhưng sai thứ tự vẫn có thể không Resume được. Resume cần cả nội dung frame và vị trí chính xác của từng frame.

### 5.4 KEEPALIVE position và giải phóng frame

KEEPALIVE có thể mang vị trí frame peer đã nhận. Implementation có thể dùng thông tin này để giải phóng frame đã được peer xác nhận khỏi retransmit buffer.

Nếu KEEPALIVE không tới được, bị chặn hoặc khoảng thời gian quá dài, store có thể giữ frame lâu hơn dự kiến và tiêu thụ thêm bộ nhớ. Ngược lại, nếu store giải phóng frame sớm hơn vị trí peer thực sự đã nhận, Resume sẽ thiếu frame.

Hãy kiểm tra đồng thời:

- KEEPALIVE interval và max lifetime.
- Proxy/load balancer idle timeout.
- Log keepalive timeout hoặc connection close.
- Frame position nhận được từ peer.
- Chính sách releaseFrames của store.

KEEPALIVE position là thông tin giao thức để quản lý frame retransmission. Nó không phải application ACK và không chứng minh database nghiệp vụ đã commit.

## 6. Nhóm nguyên nhân C: hai phía còn state nhưng vị trí không liên tục

Đây là nhóm khó phát hiện nhất vì token vẫn tồn tại và store vẫn có dữ liệu.

Một số dấu hiệu:

- Resume store tìm thấy session nhưng replay stream phát lỗi.
- Frame position cũ nhất lớn hơn vị trí mà peer cần phát lại.
- Frame position mới nhất không khớp implied position dự kiến.
- Client store còn frame nhưng có gap.
- Server store phục hồi từ snapshot có frame thiếu.
- Một node ghi frame nhưng node khác đọc bản sao chưa đồng bộ.

### Kiểm tra dải frame trong store

Với mỗi session và mỗi hướng, cần đối chiếu:

| Giá trị | Câu hỏi chẩn đoán |
|---|---|
| Last received position | Peer đã nhận liên tục tới vị trí nào? |
| First available position | Store còn phát lại được từ vị trí nào? |
| Current frame position | Vị trí frame mới nhất đã ghi là bao nhiêu? |
| Implied position | Vị trí logic hiện tại của stream frame là bao nhiêu? |
| Oldest retained frame | Frame cũ nhất chưa được giải phóng là frame nào? |
| Newest retained frame | Frame mới nhất trong buffer là frame nào? |

Nếu custom store hỗ trợ, kiểm tra framePosition(), frameImpliedPosition() và resumeStream(). Đọc replay stream trong test hoặc công cụ chẩn đoán có kiểm soát để xác nhận frame liên tục; không dump payload nhạy cảm vào log production.

### Không tự sửa vị trí để ép Resume thành công

Không tăng hoặc giảm position để làm cho hai phía có vẻ khớp nhau. Position là một phần của trạng thái giao thức. Nếu bỏ qua gap, peer có thể diễn giải frame mới thành frame cũ hoặc ngược lại, dẫn tới stream hỏng và side effect lặp/mất.

Khi phát hiện gap, hãy đánh dấu session không thể Resume, giữ log/metrics phục vụ điều tra, rồi chuyển ứng dụng sang recovery từ checkpoint. Không sửa state đang chạy trực tiếp trong shared store trừ khi có quy trình phục hồi được thiết kế và kiểm thử riêng.

## 7. Quy trình chẩn đoán theo thứ tự

Dùng quy trình sau để khoanh vùng lỗi mà không thay đổi nhiều tham số cùng lúc.

~~~mermaid
flowchart TD
    A["Client mất transport"] --> B["Có mở được transport mới?"]
    B -->|Không| C["Kiểm tra DNS, route, proxy, TLS và port"]
    B -->|Có| D["Client gửi RESUME với token cũ"]
    D --> E["Server có nhận diện session?"]
    E -->|Không| F["Kiểm tra token, node owner, restart và TTL"]
    E -->|Có| G["Hai phía còn đủ frame liên tục?"]
    G -->|Không| H["Kiểm tra buffer limit, eviction, store gap và vị trí"]
    G -->|Có| I["Kiểm tra protocol/config compatibility và ownership race"]
    F --> J["REJECTED_RESUME: dừng retry session cũ"]
    H --> J
    I --> J
    J --> K["Tạo session mới"]
    K --> L["Resubscribe từ application checkpoint/cursor"]
    L --> M["Deduplicate và tiếp tục ACK nghiệp vụ"]
~~~

### Bước 1: ghi nhận thời điểm và node

Thu thập:

- Client ID hoặc subscription ID đã được che/ẩn danh.
- Session fingerprint, không ghi raw resume token.
- Node nhận SETUP ban đầu.
- Node nhận RESUME.
- Thời điểm transport mất kết nối và thời điểm reconnect.
- Phiên bản ứng dụng, RSocket Java và protocol configuration.
- Transport TCP hay WebSocket.

Nếu node nhận RESUME khác node ban đầu, kiểm tra affinity hoặc shared store trước.

### Bước 2: kiểm tra token và session lookup

Xác nhận token gửi trong RESUME chính là token từ SETUP ban đầu. Kiểm tra session directory, TTL, cleanup log và mapping token-to-owner.

Nếu server không tìm thấy token, nguyên nhân có thể là token sai, session đã hết hạn, process restart hoặc node đích không có state. Đừng tăng frame buffer khi server còn chưa tìm thấy session.

### Bước 3: kiểm tra thời hạn

So sánh thời gian reconnect với session duration ở server. Tính tổng thời gian retry gồm backoff, jitter, DNS, TLS handshake và thời gian chờ load balancer.

Nếu session đã hết hạn, tăng session retention chỉ có ích khi yêu cầu nghiệp vụ thật sự cần Resume lâu hơn và cluster có đủ dung lượng giữ state.

### Bước 4: kiểm tra frame store ở cả hai phía

Thu thập frame position, implied position, oldest/newest retained frame và store occupancy. Xác minh store không bị dispose, cleanup hoặc eviction trước thời điểm RESUME.

Nếu có custom store, chạy kiểm tra liên tục của resumeStream() và kiểm tra các thao tác ghi/giải phóng frame theo thứ tự.

### Bước 5: kiểm tra cấu hình tương thích

So sánh client và server về:

- Resume có được bật ở cả hai phía không.
- Protocol version.
- Data MIME type và metadata MIME type.
- Cách serialize payload.
- Session duration và giới hạn buffer.
- Node/cluster identity và session ownership.
- Các chính sách cleanup, retry và keepalive.

### Bước 6: quyết định Resume hay application recovery

Nếu state đủ và lỗi chỉ do transport tạm thời, client có thể tiếp tục theo retry policy của implementation. Nếu đã nhận REJECTED_RESUME, session state bị mất hoặc frame gap không thể sửa an toàn, hãy chuyển sang session mới và khôi phục nghiệp vụ từ durable cursor/checkpoint.

## 8. Chẩn đoán Resume store trong RSocket Java

RSocket Java 1.1.5 đặt các kiểu hỗ trợ Resume trong package io.rsocket.resume. Các kiểu quan trọng gồm:

- ResumableFramesStore: contract lưu frame cần cho Resume.
- InMemoryResumableFramesStore: implementation lưu frame trong bộ nhớ.
- ClientRSocketSession và ServerRSocketSession: quản lý session ở hai phía.
- ResumableDuplexConnection: lớp kết nối hỗ trợ Resume.

RSocketConnector.resume(Resume) bật Resume phía client. RSocketServer.resume(Resume) bật Resume phía server. Cả hai mặc định không bật Resume nếu không cấu hình.

### Các thao tác cần quan sát

ResumableFramesStore có những thao tác chính:

| API | Mục đích chẩn đoán |
|---|---|
| saveFrames(Flux<ByteBuf>) | Ghi frame gửi đi để có thể phát lại |
| resumableFrameReceived(ByteBuf) | Ghi nhận frame nhận được và tiến implied position |
| releaseFrames(long) | Giải phóng frame đã được peer xác nhận |
| resumeStream() | Đọc lại frame từ store theo thứ tự |
| framePosition() | Vị trí frame cục bộ |
| frameImpliedPosition() | Vị trí ngầm định của frame |

resumeStream() phải báo lỗi nếu frame không liên tục. Đây là một kiểm tra quan trọng đối với custom store.

### Vì sao in-memory store không chịu được process restart?

InMemoryResumableFramesStore lưu dữ liệu trong memory của process. Nếu process bị dừng, dữ liệu và mapping liên quan biến mất. Cấu hình Resume ở client không thể tự tái tạo frame buffer của server sau restart.

Nếu yêu cầu chịu được node restart, cần storage/session manager có khả năng phục hồi đủ state theo contract của đúng phiên bản RSocket Java. Việc chỉ lưu resume token trong Redis hoặc database không đủ: implementation còn cần frame, vị trí, ownership và lifecycle session.

### Cẩn thận với ByteBuf

RSocket Java dùng Netty ByteBuf cho frame. Custom store phải tuân thủ quy tắc reference counting:

- Retain/copy frame đúng cách khi lưu vượt qua lifecycle của callback.
- Release frame đúng số lần khi không còn sử dụng.
- Không phát một buffer đã bị release.
- Không sửa nội dung buffer đang được peer hoặc pipeline khác dùng.
- Đảm bảo frame replay có byte content và thứ tự giống dữ liệu đã lưu.

Sai sót reference counting có thể tạo lỗi use-after-release, leak memory hoặc frame hỏng. Khi nghi ngờ, dùng leak detection của Netty trong môi trường test và kiểm thử store độc lập trước khi đưa vào cluster.

### Không dùng API nội bộ để vá state

Các lớp trong package io.rsocket.internal là chi tiết implementation. Không dựa vào chúng để tự thay position hoặc dựng lại session. Hãy sử dụng API công khai và SPI mà đúng phiên bản cung cấp; nếu cần custom store, kiểm tra contract của ResumableFramesStore và test tương thích theo phiên bản.

## 9. Ước lượng và điều chỉnh buffer

Tăng buffer có thể giải quyết tình huống frame bị loại bỏ vì dung lượng quá nhỏ, nhưng không giải quyết session bị mất sau restart hoặc token không được nhận diện.

### Quy trình tính dung lượng

1. Đo tốc độ byte frame thực tế theo từng hướng.
2. Xác định thời gian gián đoạn tối đa mà hệ thống cần Resume.
3. Tính lượng dữ liệu phát trong cửa sổ đó.
4. Thêm hệ số dự phòng cho burst, metadata và overhead.
5. Nhân với số session đồng thời.
6. Kiểm tra giới hạn memory hoặc storage của từng node và toàn cluster.

Ví dụ một session có tốc độ 500 KB/s trong một hướng, cần chịu gián đoạn 60 giây và dùng hệ số 2:

\[
B \approx 500\ \text{KB/s} \times 60\ \text{s} \times 2
= 60\ \text{MB}
\]

Nếu có 300 session đồng thời ở mức tương tự, dung lượng lý thuyết đã khoảng 18 GB cho hướng đó. Đây là ước lượng bảo thủ khi frame chưa được giải phóng theo vị trí peer; cần đo phân phối thực tế và xác định bao nhiêu session cùng đạt peak.

### Tăng buffer có đánh đổi

| Điều chỉnh | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Tăng cache size theo session | Giữ được nhiều frame hơn khi mất kết nối lâu | Tăng memory/storage |
| Tăng session duration | Cho client thêm thời gian reconnect | Giữ state lâu hơn, tăng session tồn đọng |
| Tăng keepalive frequency | Phát hiện trạng thái peer và cập nhật position thường xuyên hơn | Tăng frame/control traffic |
| Tăng max lifetime | Chịu được nhiều keepalive bị trễ hơn | Phát hiện connection chết chậm hơn |
| Dùng durable/shared store | Có thể phục hồi qua process hoặc node tùy thiết kế | Latency, I/O, consistency và vận hành phức tạp hơn |

Không điều chỉnh keepalive interval chỉ để thay thế session retention. Keepalive phát hiện trạng thái kết nối và có thể mang vị trí frame; session duration quyết định state được giữ trong bao lâu. Hai cấu hình giải quyết hai vấn đề khác nhau.

### Đặt giới hạn tổng dung lượng

Tính tổng bộ nhớ theo số session và phân phối tải, không chỉ nhìn cache size của một session. Cần có giới hạn:

- Tổng số session Resume đang được giữ.
- Dung lượng store tối đa trên mỗi node.
- Dung lượng theo tenant hoặc nhóm client.
- Thời gian session không hoạt động.
- Ngưỡng cảnh báo trước khi store đầy.
- Chính sách cleanup khi client không quay lại.

Nếu hệ thống phải chọn session nào bị loại khi quá tải, hãy có chính sách ưu tiên và ghi nhận rõ session nào không còn Resume được. Không để eviction âm thầm khiến vận hành tưởng rằng Resume luôn sẵn sàng.

## 10. Phục hồi an toàn sau REJECTED_RESUME

Khi server trả ERROR[REJECTED_RESUME], client không được tiếp tục Resume session đó. Hãy chuyển sang application recovery.

Quy trình tổng quát:

1. Ghi nhận Resume rejection và session fingerprint.
2. Kết thúc/giải phóng connection cũ theo lifecycle của client.
3. Tạo một RSocket session mới bằng SETUP.
4. Xác thực lại và thiết lập metadata cần thiết.
5. Đăng ký lại request-stream hoặc request-channel.
6. Gửi cursor/checkpoint nghiệp vụ cuối cùng đã commit.
7. Nhận lại các event sau cursor đó.
8. Deduplicate event đã xử lý nhưng ACK trước đó bị mất.
9. Tiếp tục ghi checkpoint sau khi transaction nghiệp vụ commit.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant L as Durable Event Log
    participant DB as Client Database

    C->>S: RESUME(token cũ)
    S-->>C: ERROR[REJECTED_RESUME]
    Note over C,S: Không retry RESUME với session cũ
    C->>S: SETUP mới
    S-->>C: SETUP thành công
    C->>S: REQUEST_STREAM(cursor đã commit)
    S->>L: Đọc event sau cursor
    L-->>S: Event 501...
    S-->>C: Event 501
    C->>DB: Kiểm tra event ID, xử lý và commit
    DB-->>C: Commit thành công
    C->>S: Application ACK/checkpoint 501
~~~

### Dùng cursor nghiệp vụ, không dùng frame position

Frame position thuộc về session RSocket cũ. Khi tạo SETUP mới, không gửi frame position cũ như cursor của stream mới.

Application cursor phải là dữ liệu nghiệp vụ có nghĩa với nguồn: event offset, sequence theo partition, change token hoặc snapshot version. Nếu nguồn không có cursor bền vững, cần thiết kế durable log hoặc snapshot/resync; không thể tự khôi phục dữ liệu đã mất chỉ bằng cách tạo connection mới.

### Tránh lặp side effect

Một event có thể đã được xử lý ở client nhưng ACK nghiệp vụ chưa đến server trước khi transport đứt. Khi resubscribe, event có thể được phát lại.

Dùng event ID ổn định và idempotency record. Commit thay đổi nghiệp vụ và processed marker trong cùng transaction; chỉ gửi application ACK sau commit. Với thao tác gọi hệ thống ngoài, truyền idempotency key tới downstream hoặc dùng outbox/inbox phù hợp.

Đối với command request-response có kết quả chưa rõ sau khi mất connection, đừng tự động gửi lại command có side effect mà không kiểm tra trạng thái. Hãy dùng command ID/idempotency key để truy vấn hoặc thực hiện lại an toàn.

## 11. Những điều không nên làm khi Resume thất bại

| Cách xử lý sai | Vì sao nguy hiểm | Cách làm phù hợp |
|---|---|---|
| Retry vô hạn cùng resume token sau REJECTED_RESUME | Trái với protocol và tạo tải không cần thiết | Chuyển sang session mới |
| Tăng buffer dù token không được tìm thấy | Không sửa được session lookup | Kiểm tra node owner, TTL và token |
| Chỉ lưu token mà không lưu frame state | Không thể phát lại dữ liệu cần thiết | Lưu đầy đủ state theo implementation |
| Dùng in-memory store nhưng kỳ vọng sống qua restart | Restart xóa toàn bộ state trong process | Durable/shared store hoặc application recovery |
| Đưa mọi reconnect về node ngẫu nhiên | Node đích có thể không có session | Affinity hoặc shared state |
| Bỏ qua frame gap và ép position khớp | Có thể làm sai thứ tự hoặc mất/nhân frame | Từ chối Resume và resubscribe |
| Tăng session TTL vô hạn | Giữ state và buffer không giới hạn | TTL theo retry window và ngân sách tài nguyên |
| Giảm keepalive interval quá thấp | Tăng control traffic và CPU | Chọn theo network/proxy timeout và tải |
| Xem RESUME_OK là ACK nghiệp vụ | Không chứng minh transaction đã commit | Application ACK/checkpoint riêng |
| Retry command mù quáng sau lỗi connection | Side effect có thể đã xảy ra | Idempotency key và kiểm tra trạng thái |
| Log raw resume token hoặc payload nhạy cảm | Có thể lộ khả năng chiếm session/dữ liệu | Log fingerprint và metadata đã che |

## 12. Thiết kế log và metrics để tìm nguyên nhân nhanh

Nếu chỉ log Resume failed, rất khó phân biệt mất session với thiếu frame. Mỗi lần Resume nên có một bản ghi có cấu trúc.

Các trường log nên cân nhắc:

| Trường | Mục đích |
|---|---|
| timestamp | Thời điểm attempt |
| session fingerprint | Đối chiếu session mà không lộ token |
| client/application version | Phát hiện thay đổi tương thích |
| initial node / current node | Phát hiện reconnect sang node khác |
| transport | TCP hoặc WebSocket |
| session age | Kiểm tra TTL |
| last received server position | Vị trí client đã nhận |
| first available client position | Frame client còn giữ sớm nhất |
| server received client position | Vị trí server đã nhận |
| oldest/newest retained frame | Kiểm tra frame range |
| store occupancy / limit | Phát hiện buffer pressure |
| resume outcome | RESUME_OK, REJECTED_RESUME, connection error |
| rejection category | Token missing, session expired, frame gap, store unavailable |

Không ghi resume token thô. Không log payload data hoặc authentication metadata trong log chẩn đoán thông thường.

Metrics nên bao gồm:

- Resume attempts, successes và rejections.
- Rejection theo nguyên nhân.
- Session đang giữ và session hết hạn.
- Frame store bytes và occupancy ratio.
- Frame bị release, drop, eviction hoặc write failure.
- Resume replay bytes và replay duration.
- Session lookup latency.
- Reconnect duration và retry count.
- Số session theo node và số lần client đổi node.

Đặt cảnh báo khi tỷ lệ Resume rejection tăng đột ngột, store gần đầy, session cleanup tăng bất thường hoặc reconnect latency vượt retry window.

## 13. Kiểm thử tái hiện lỗi Resume

Không chỉ kiểm tra happy path. Hãy cố ý tạo các điều kiện làm mất state để xác nhận hệ thống có thể chẩn đoán và fallback.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Ngắt mạng ngắn, hai store còn state | Resume thành công |
| Client mất store nhưng server còn state | Resume bị từ chối nếu thiếu frame client cần phát lại |
| Server restart với in-memory store | Session cũ không còn để Resume |
| Reconnect tới node không có session | Session lookup thất bại hoặc Resume bị từ chối |
| Session vượt quá retention | Resume bị từ chối |
| Frame buffer vượt giới hạn và thiếu frame cần thiết | Resume không tiếp tục được |
| Custom store có frame gap | resumeStream() phát lỗi; không giả vờ replay thành công |
| Token sai hoặc token của session khác | Server không nhận diện session |
| Data/metadata MIME type thay đổi | Không tiếp tục session cũ bằng cấu hình không tương thích |
| Nhận REJECTED_RESUME | Client không retry Resume với token đó |
| Application recovery từ checkpoint | Session mới đọc tiếp từ cursor và không mất event đã lưu |
| ACK nghiệp vụ bị mất | Event có thể lặp nhưng side effect được deduplicate |

### Fault injection có kiểm soát

Một integration test có thể:

1. Khởi động client và server với Resume enabled.
2. Mở request-stream và nhận một số payload.
3. Ngắt transport nhưng giữ process và Resume store.
4. Reconnect và xác nhận RESUME_OK.
5. Lặp lại với việc xóa store phía server.
6. Xác nhận REJECTED_RESUME.
7. Tạo session mới và resubscribe từ application checkpoint.
8. Xác nhận event được phát lại nhưng không tạo side effect trùng.

Một test khác có thể giới hạn buffer nhỏ để buộc xảy ra tình huống thiếu frame. Cần kiểm tra log/metrics ghi nhận đúng nguyên nhân, không chỉ kiểm tra rằng client nhận một exception.

Đối với custom store, test riêng thứ tự ghi, release, khôi phục và replay liên tục. Chạy test với nhiều frame, nhiều lần ngắt kết nối và tải đồng thời để tìm race condition.

## 14. Checklist xử lý sự cố tại production

Khi nhận báo cáo Resume thất bại, thực hiện theo thứ tự:

- [ ] Xác định lỗi transport hay REJECTED_RESUME.
- [ ] Ghi lại node nhận SETUP ban đầu và node nhận RESUME.
- [ ] Đối chiếu session fingerprint, không ghi token thô.
- [ ] Xác nhận Resume được bật ở cả client và server.
- [ ] Kiểm tra session còn trong retention window không.
- [ ] Kiểm tra process/node có restart hoặc deploy không.
- [ ] Xác nhận token gửi trong RESUME là token từ SETUP ban đầu.
- [ ] Đối chiếu protocol version và MIME type.
- [ ] Kiểm tra frame store còn đủ dữ liệu ở cả hai hướng.
- [ ] Kiểm tra frame position và tính liên tục của replay stream.
- [ ] Kiểm tra store occupancy, overflow, eviction và write failure.
- [ ] Kiểm tra KEEPALIVE và proxy timeout.
- [ ] Nếu đã REJECTED_RESUME, dừng retry session cũ.
- [ ] Tạo session mới và phục hồi từ application cursor/checkpoint.
- [ ] Xác nhận duplicate được xử lý idempotent.
- [ ] Lưu lại metrics và log để xác định nguyên nhân gốc.

## Kết luận

Resume thất bại thường xuất phát từ hai điều kiện: server không còn nhận diện hoặc khôi phục được session cũ, hoặc một trong hai phía không còn đủ frame liên tục để tiếp tục. Token chỉ định danh session; nó không thay thế session state, frame buffer và vị trí giao thức.

Hãy chẩn đoán theo thứ tự: transport, token/session lookup, node owner, session retention, frame positions, buffer capacity và tính liên tục của store. Phân biệt session duration với keepalive timeout; tăng buffer chỉ khi có bằng chứng frame bị loại do thiếu dung lượng. Với custom store, kiểm tra thứ tự ghi, release, ByteBuf lifecycle và contract replay liên tục.

Khi nhận REJECTED_RESUME, ngừng thử lại session cũ. Tạo SETUP mới và phục hồi nghiệp vụ từ durable cursor/checkpoint, dùng event ID và idempotency để chịu được dữ liệu phát lại. RSocket Resume giúp phục hồi session giao thức; ứng dụng vẫn phải chịu trách nhiệm bảo toàn tiến trình nghiệp vụ.

## Tài liệu tham khảo

- [RSocket Protocol — Resuming Operation](https://rsocket.io/about/protocol/#resuming-operation)
- [RSocket Java 1.1.5 — RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 — RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 — ResumableFramesStore](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/resume/ResumableFramesStore.html)
- [RSocket Java 1.1.5 — InMemoryResumableFramesStore](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/resume/InMemoryResumableFramesStore.html)
- [RSocket Java 1.1.5 — RejectedResumeException](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/RejectedResumeException.html)
