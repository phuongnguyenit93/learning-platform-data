# Nhóm frame thiết lập và quản lý kết nối

RSocket dùng một nhóm frame ở cấp kết nối để khởi tạo phiên giao tiếp, duy trì khả năng phát hiện kết nối mất, giới hạn quyền gửi request và khôi phục phiên sau khi transport bị gián đoạn. Các frame này tạo nền tảng cho những luồng request-response, fire-and-forget, request-stream và request-channel chạy bên trên.

Nhóm frame cần nhận biết gồm **SETUP**, **KEEPALIVE**, **LEASE**, **RESUME** và **RESUME_OK**. Ngoài ra, **ERROR** với stream ID bằng 0 có thể báo lỗi khiến toàn bộ kết nối RSocket không thể tiếp tục. Hiểu đúng vai trò của từng frame giúp ta phân biệt lỗi transport, lỗi phiên RSocket và lỗi của một stream ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả trình tự thiết lập một phiên RSocket sau khi TCP hoặc WebSocket đã kết nối.
- Nhận biết thông tin được trao đổi trong frame SETUP và ý nghĩa của các tham số kết nối.
- Giải thích cách KEEPALIVE phát hiện peer không còn hoạt động.
- Phân biệt LEASE với backpressure của một request-stream.
- Mô tả điều kiện và quy trình khôi phục phiên bằng RESUME và RESUME_OK.
- Đọc stream ID để phân biệt frame điều khiển kết nối với frame thuộc một stream ứng dụng.

## 1. Frame điều khiển kết nối nằm ở đâu?

RSocket có thể chạy trên TCP hoặc WebSocket. Transport tạo đường truyền giữa hai tiến trình; sau khi đường truyền sẵn sàng, RSocket mới trao đổi frame để thiết lập và quản lý phiên giao tiếp. Vì vậy, kết nối TCP thành công chưa có nghĩa là phiên RSocket đã được thiết lập thành công.

Một frame RSocket có phần header chứa stream ID, loại frame và các flag. Stream ID bằng **0** dành cho các frame điều khiển ở cấp kết nối. Các frame ứng dụng như REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL, REQUEST_FNF và PAYLOAD thường gắn với stream ID khác 0.

Trên transport TCP, frame còn được phân định bằng phần length prefix của transport. Phần phân định này không phải là stream ID và cũng không phải loại frame. Khi đọc log hoặc bắt gói tin, cần tách ba khái niệm: ranh giới frame, header RSocket và payload của frame.

| Thành phần | Vai trò |
|---|---|
| Transport connection | Đường truyền TCP hoặc WebSocket giữa hai peer |
| RSocket session | Trạng thái giao thức được thiết lập bằng SETUP và được quản lý trong suốt vòng đời kết nối |
| Connection-level frame | Điều khiển phiên; dùng stream ID bằng 0 |
| Application stream | Một tương tác RSocket cụ thể, được định danh bằng stream ID khác 0 |

Các frame điều khiển không phải là request nghiệp vụ. Ví dụ, KEEPALIVE không yêu cầu server trả về dữ liệu giá; nó kiểm tra khả năng giao tiếp của peer. LEASE không điều tiết số phần tử trong một Flux; nó giới hạn khả năng khởi tạo request theo một khoảng thời gian.

## 2. SETUP: thiết lập phiên RSocket

### 2.1. Khi nào SETUP được gửi?

Sau khi client và server đã có transport connection, bên khởi tạo RSocket gửi frame **SETUP** để bắt đầu một phiên giao thức. SETUP là frame đầu tiên cần thiết để khởi tạo phiên RSocket mới. Frame này dùng stream ID bằng 0.

SETUP cho hai bên biết cách diễn giải dữ liệu và các giới hạn thời gian cơ bản. Những thông tin chính gồm:

- **Protocol version**: phiên bản major và minor của RSocket protocol mà bên khởi tạo sử dụng.
- **Keepalive interval**: khoảng thời gian dự kiến giữa các lần gửi keepalive.
- **Maximum lifetime**: giới hạn thời gian peer có thể không thể hiện hoạt động hợp lệ trước khi kết nối bị coi là không còn sống.
- **Data MIME type**: kiểu nội dung của phần data trong payload.
- **Metadata MIME type**: kiểu nội dung của metadata nếu có.
- **Flags**: các khả năng hoặc chế độ được yêu cầu, chẳng hạn resume và lease.
- **Setup payload**: metadata và data ban đầu tùy nhu cầu của ứng dụng.
- **Resume token**: thông tin nhận diện phiên dùng cho resume nếu chế độ này được bật.

Tên trường và cách mã hóa của chúng được quy định trong protocol. Các con số thời gian trong SETUP được truyền theo đơn vị mà protocol định nghĩa; ở tầng ứng dụng, nên cấu hình bằng kiểu Duration để tránh nhầm đơn vị.

### 2.2. MIME type và setup payload

Data MIME type cho biết cách giải mã phần data, ví dụ JSON hoặc một định dạng nhị phân. Metadata MIME type cho biết cách giải mã metadata, chẳng hạn metadata dạng composite hoặc một định dạng văn bản cụ thể. Hai bên cần thống nhất MIME type để tránh việc một bên gửi dữ liệu mà bên kia giải mã sai.

Setup payload là dữ liệu đi kèm lúc mở phiên. Ứng dụng có thể dùng metadata ban đầu để gửi thông tin cần thiết cho việc khởi tạo, ví dụ một thông tin xác thực hoặc ngữ cảnh client. Setup payload không phải là một request-response riêng và không tạo application stream.

Thông tin xác thực trong setup metadata vẫn cần được kiểm tra ở phía server. Việc gửi một token trong SETUP không tự động cấp quyền cho mọi route; server cần xác thực token, kiểm tra phạm vi truy cập và tiếp tục áp dụng authorization cho các request phù hợp.

### 2.3. Các flag quan trọng

Một số flag trong SETUP làm thay đổi cách hai bên quản lý phiên:

| Flag | Ý nghĩa |
|---|---|
| RESUME | Bên khởi tạo yêu cầu sử dụng khả năng khôi phục phiên; SETUP mang resume token tương ứng |
| LEASE | Bật cơ chế cấp quyền gửi request theo lease |
| METADATA | Cho biết setup payload có metadata |

Khả năng có mặt của flag không có nghĩa là tính năng đã được triển khai đầy đủ ở cả hai phía. Resume còn cần trạng thái phiên và dữ liệu để phát lại được lưu giữ; lease cần bên cấp lease gửi quyền hợp lệ và bên gửi request tuân thủ giới hạn.

### 2.4. Server xử lý SETUP

Server kiểm tra phiên bản protocol, MIME type, flag và dữ liệu khởi tạo. Nếu chấp nhận, server tiếp tục xử lý các frame của phiên. Protocol không dùng một frame SETUP_OK riêng để xác nhận thành công. Nếu setup bị từ chối, server có thể gửi frame ERROR ở cấp kết nối, tức stream ID bằng 0, rồi đóng hoặc kết thúc phiên.

Một số nguyên nhân khiến setup thất bại:

- Phiên bản protocol không được hỗ trợ.
- MIME type hoặc tổ hợp flag không được hỗ trợ.
- Setup payload không hợp lệ.
- Xác thực thất bại hoặc chính sách server từ chối kết nối.
- Tham số keepalive không được chấp nhận theo chính sách triển khai.

Không nên nhầm SETUP với TLS handshake. TLS có thể xác thực server, mã hóa và bảo vệ đường truyền trước khi RSocket SETUP được gửi. SETUP thương lượng thông tin của RSocket session ở tầng ứng dụng.

## 3. KEEPALIVE: theo dõi peer còn hoạt động

### 3.1. Mục đích

Một transport connection có thể tồn tại trong khi peer đã dừng xử lý, tiến trình bị treo hoặc đường truyền bị đứt mà hệ điều hành chưa phát hiện. **KEEPALIVE** giúp hai phía nhận biết peer còn có thể giao tiếp.

Các tham số keepalive được trao đổi trong SETUP:

- Keepalive interval xác định nhịp gửi keepalive dự kiến.
- Maximum lifetime đặt giới hạn thời gian chờ hoạt động của peer.

Hai phía dựa vào các tham số này để phát hiện kết nối không còn đáp ứng. Khi quá thời gian cho phép mà không nhận được hoạt động phù hợp, implementation có thể kết thúc phiên và báo lỗi cho các stream đang chạy.

### 3.2. Respond flag

KEEPALIVE có flag **Respond**. Khi một peer gửi KEEPALIVE với Respond được bật, peer còn lại phải phản hồi bằng KEEPALIVE không yêu cầu phản hồi tiếp. Cơ chế này giúp bên gửi xác nhận rằng peer vẫn nhận và xử lý được frame.

KEEPALIVE còn mang thông tin vị trí đã nhận trong luồng frame của phiên. Thông tin vị trí này đặc biệt hữu ích khi resume được bật, vì hai bên cần biết dữ liệu nào đã được peer nhận để xác định phần cần phát lại.

### 3.3. KEEPALIVE không thay thế timeout nghiệp vụ

KEEPALIVE trả lời câu hỏi: peer còn có thể giao tiếp ở cấp kết nối hay không? Nó không chứng minh rằng một truy vấn cụ thể sẽ hoàn tất đúng hạn hoặc dữ liệu nghiệp vụ còn mới.

Ví dụ, client vẫn nhận KEEPALIVE đều đặn nhưng một request tìm kiếm có thể bị kẹt do cơ sở dữ liệu chậm. Ứng dụng vẫn cần timeout cho request, giới hạn thời gian xử lý và theo dõi độ trễ của từng route.

Không nên đặt keepalive interval quá ngắn. Tần suất quá cao làm tăng lưu lượng điều khiển và có thể tạo cảnh báo mất kết nối giả khi mạng có jitter. Hãy chọn interval và maximum lifetime dựa trên độ trễ mạng, chính sách idle timeout của hạ tầng và mục tiêu phát hiện lỗi.

## 4. LEASE: giới hạn quyền khởi tạo request

### 4.1. LEASE giải quyết vấn đề gì?

Trong một hệ thống có nhiều client, server có thể cần giới hạn số request mới mà một client được phép gửi trong một khoảng thời gian. **LEASE** cung cấp cơ chế cấp quyền gửi request có thời hạn và số lượng giới hạn.

Trong mô hình phổ biến, server gửi LEASE cho client. Frame chứa:

- **Time-to-live (TTL)**: thời gian lease còn hiệu lực.
- **Number of requests**: số request tối đa được phép khởi tạo trong thời gian lease.
- Metadata tùy chọn nếu ứng dụng cần truyền thêm ngữ cảnh về lease.

Client chỉ nên khởi tạo request trong giới hạn số lượng và thời gian được cấp. Khi hết TTL hoặc đã dùng hết số request, client phải chờ lease tiếp theo trước khi gửi request mới.

LEASE chỉ được sử dụng khi chế độ lease đã được bật trong quá trình thiết lập. Nếu không thương lượng lease, không được tự suy luận rằng server đang áp dụng giới hạn request bằng frame này.

### 4.2. LEASE khác backpressure như thế nào?

Hai cơ chế kiểm soát hai loại tài nguyên khác nhau:

| Cơ chế | Kiểm soát | Ví dụ |
|---|---|---|
| LEASE | Số request mới được khởi tạo trong thời hạn | Client được phép bắt đầu tối đa 50 request trong 10 giây |
| Reactive Streams demand / REQUEST_N | Số phần tử mà subscriber sẵn sàng nhận trong một stream | Subscriber yêu cầu thêm 20 phần tử |
| Timeout | Thời gian chờ một thao tác hoàn tất | Request phải hoàn tất trong 2 giây |

LEASE không giới hạn trực tiếp số phần tử mà một request-stream phát ra. Ngược lại, REQUEST_N không phải cơ chế cấp quota cho số request mới. Một hệ thống có thể cần cả lease, backpressure và timeout để bảo vệ các lớp tài nguyên khác nhau.

### 4.3. Ví dụ luồng sử dụng lease

Giả sử server cấp lease với TTL 10 giây và số request tối đa là 50. Client có thể bắt đầu tối đa 50 request trong cửa sổ hiệu lực đó. Sau request thứ 50, client phải đợi lease tiếp theo hoặc áp dụng chính sách chờ phù hợp. Nếu lease hết hạn trước khi client dùng hết quota, phần quota còn lại không tự kéo dài sang lease kế tiếp.

Ứng dụng nên xử lý trạng thái hết lease một cách tường minh: xếp hàng có giới hạn, từ chối sớm ở tầng nghiệp vụ hoặc thử lại sau khi nhận lease mới. Không nên retry liên tục trong khi chưa có quyền gửi request, vì điều đó tạo thêm tải và làm sai ý nghĩa của lease.

## 5. RESUME và RESUME_OK: khôi phục phiên sau gián đoạn

### 5.1. Vì sao cần resume?

Một kết nối TCP hoặc WebSocket có thể bị gián đoạn do chuyển mạng, mất Wi-Fi, proxy đóng kết nối hoặc tiến trình tạm thời mất khả năng giao tiếp. Nếu tạo một RSocket session mới, những stream đang chạy trong session cũ không tự động tiếp tục.

Resume cho phép hai peer cố gắng tiếp tục một phiên RSocket đã tồn tại trên một transport connection mới. Điều này hữu ích cho stream dài hạn, nhưng chỉ hoạt động khi cả hai phía hỗ trợ resume và còn giữ đủ trạng thái cần thiết.

### 5.2. Điều kiện để resume thành công

Một phiên có thể được resume khi các điều kiện chính sau được đáp ứng:

1. Khả năng resume đã được bật trong SETUP và hai phía triển khai cơ chế tương ứng.
2. Client có resume token của phiên trước.
3. Server vẫn giữ trạng thái phiên và dữ liệu cần thiết để phát lại.
4. Các vị trí frame mà hai bên báo cáo còn nằm trong phạm vi dữ liệu có thể khôi phục.
5. Token và thông tin phiên vượt qua kiểm tra hợp lệ của server.

Resume token là định danh opaque đối với ứng dụng. Không nên tự phân tích token hoặc dùng nó làm business identifier. Token cần được bảo vệ như thông tin phiên, vì người có token có thể thử yêu cầu tiếp tục phiên tương ứng.

### 5.3. Trình tự RESUME

Khi phát hiện transport cũ bị mất, client tạo một transport connection mới đến server và gửi **RESUME** thay vì SETUP để yêu cầu tiếp tục session cũ. RESUME mang protocol version, resume token và thông tin vị trí nhận của hai hướng truyền.

Server tra cứu phiên theo token, kiểm tra khả năng phát lại và đối chiếu vị trí. Nếu chấp nhận, server gửi **RESUME_OK** để xác nhận phiên có thể tiếp tục. Hai bên sử dụng thông tin vị trí để xác định frame nào đã được nhận và frame nào cần phát lại. Sau đó các stream đang hoạt động có thể tiếp tục theo trạng thái được khôi phục.

Nếu token không hợp lệ, trạng thái phiên đã hết hạn hoặc dữ liệu cần phát lại không còn, server từ chối resume bằng ERROR ở cấp kết nối. Client khi đó cần xử lý như một phiên mới: thiết lập lại bằng SETUP và để ứng dụng quyết định có cần tạo lại các request hay không.

### 5.4. Resume không phải lưu trữ bền vững

Resume dựa vào trạng thái phiên và bộ đệm phát lại còn tồn tại. Nếu server khởi động lại và mất trạng thái đó, hoặc thời gian gián đoạn vượt quá thời gian giữ dữ liệu, resume có thể thất bại.

Resume cũng không thay thế idempotency ở tầng nghiệp vụ. Khi ứng dụng thực hiện một thao tác có side effect, chẳng hạn tạo đơn hàng hoặc trừ tiền, cần có mã định danh nghiệp vụ và cơ chế chống thực hiện trùng. Việc khôi phục luồng frame không tự chứng minh rằng một side effect đã được commit đúng một lần ở hệ thống phía sau.

Vì vậy, hãy xem resume là khả năng khôi phục phiên trong một giới hạn được cấu hình, không phải cam kết dữ liệu tồn tại vô thời hạn hoặc bảo đảm exactly-once cho nghiệp vụ.

## 6. ERROR ở cấp kết nối

Frame ERROR có thể báo lỗi cho một stream hoặc cho toàn bộ kết nối. Stream ID giúp xác định phạm vi:

- Stream ID bằng 0: lỗi ở cấp kết nối RSocket. Phiên không thể tiếp tục bình thường; ví dụ setup bị từ chối hoặc resume thất bại.
- Stream ID khác 0: lỗi thuộc một application stream cụ thể. Những stream khác có thể vẫn hoạt động tùy loại lỗi và trạng thái kết nối.

Khi nhận ERROR ở cấp kết nối, ứng dụng nên dừng việc tạo request trên phiên đó, giải phóng tài nguyên liên quan và thực hiện chính sách reconnect phù hợp. Nếu lỗi ở một stream riêng, không nên mặc định đóng toàn bộ kết nối.

Log cần ghi lại phạm vi lỗi, loại frame, stream ID, mã lỗi và nguyên nhân có thể xác định. Tránh ghi resume token, access token hoặc metadata nhạy cảm vào log.

## 7. Sơ đồ vòng đời kết nối

Sơ đồ dưới đây mô tả một phiên có bật lease và resume. Lease là tùy chọn; các frame KEEPALIVE tiếp tục xuất hiện trong khi phiên đang hoạt động.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: Transport connect (TCP hoặc WebSocket)
    C->>S: SETUP (version, MIME types, keepalive, flags)
    alt Server chấp nhận
        Note over C,S: Phiên RSocket được thiết lập
        loop Khi phiên còn hoạt động
            C->>S: KEEPALIVE
            S-->>C: KEEPALIVE response nếu được yêu cầu
            S-->>C: LEASE (nếu lease được bật)
        end
        Note over C,S: Transport bị gián đoạn
        C->>S: Transport connect mới
        C->>S: RESUME (token và vị trí)
        alt Phiên còn khôi phục được
            S-->>C: RESUME_OK
            Note over C,S: Phát lại frame còn thiếu và tiếp tục stream
        else Không thể khôi phục
            S-->>C: ERROR (stream ID = 0)
            Note over C,S: Client cân nhắc tạo phiên mới bằng SETUP
        end
    else Server từ chối
        S-->>C: ERROR (stream ID = 0)
        Note over C,S: Không có phiên RSocket hoạt động
    end
~~~

## 8. Cấu hình và quan sát trong ứng dụng Java

### 8.1. Cấu hình keepalive với Spring RSocketRequester

Spring cho phép cấu hình RSocketConnector thông qua builder của RSocketRequester. Ví dụ sau đặt chu kỳ keepalive là 20 giây và maximum lifetime là 90 giây:

~~~java
import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90)))
        .tcp("localhost", 7000);
~~~

Đây là ví dụ cấu hình client dùng TCP. Nếu dùng WebSocket, phần tạo transport thay đổi theo endpoint và cấu hình ứng dụng; ý nghĩa của các tham số keepalive ở cấp RSocket vẫn cần được hiểu riêng với timeout của WebSocket, proxy hoặc load balancer.

API cụ thể cho lease và resume phụ thuộc phiên bản thư viện RSocket và cách ứng dụng quản lý session. Hãy kiểm tra tài liệu của phiên bản đang dùng trước khi bật các tính năng này. Cấu hình một cờ resume mà không có nơi lưu trạng thái và buffer phát lại không tạo ra khả năng khôi phục đáng tin cậy.

### 8.2. Những tín hiệu nên theo dõi

Trong môi trường vận hành, nên quan sát ít nhất:

- Số lần thiết lập kết nối thành công và thất bại.
- Số lần keepalive timeout và thời gian phát hiện kết nối mất.
- Số lần resume thành công, resume bị từ chối và nguyên nhân.
- Dung lượng, tuổi dữ liệu và số lần tràn của buffer phát lại.
- Số lease được cấp, số request được phép, số request bị trì hoãn hoặc từ chối do hết lease.
- Số ERROR ở cấp kết nối và ở cấp stream.
- Số stream đang hoạt động, thời gian sống của stream và số lần reconnect.

Không dùng riêng trạng thái TCP connected để kết luận RSocket session đang khỏe. Một phiên có thể bị lỗi ở tầng giao thức hoặc một stream có thể gặp vấn đề trong khi transport vẫn còn mở.

## 9. Các lỗi thiết kế thường gặp

### Coi TCP connect là RSocket setup thành công

Transport chỉ tạo đường truyền. Client vẫn phải gửi SETUP và server phải chấp nhận phiên. Hãy phân biệt log kết nối transport với log khởi tạo RSocket session.

### Cấu hình keepalive quá ngắn

Interval quá thấp có thể làm tăng lưu lượng điều khiển và gây timeout giả khi mạng có jitter. Chọn interval và maximum lifetime theo điều kiện mạng thực tế.

### Dùng LEASE như backpressure

LEASE giới hạn số request mới trong một thời hạn. Backpressure điều tiết số phần tử trong một stream. Cần áp dụng đúng cơ chế cho đúng loại tải.

### Bật resume nhưng không giữ trạng thái

Resume cần token, trạng thái phiên và dữ liệu phát lại. Nếu các dữ liệu này bị xóa quá sớm, client sẽ không thể khôi phục session.

### Giả định resume luôn thành công

Resume có thể bị từ chối khi token hết hiệu lực, server không còn trạng thái hoặc vị trí đã vượt quá buffer. Ứng dụng cần có đường xử lý tạo session mới và khởi tạo lại các request cần thiết.

### Xem resume là bảo đảm exactly-once

Resume hỗ trợ tiếp tục trao đổi frame trong giới hạn trạng thái được giữ. Nó không thay thế idempotency, transaction hoặc cơ chế chống xử lý trùng ở tầng nghiệp vụ.

### Đóng toàn bộ kết nối khi một stream lỗi

ERROR có thể giới hạn ở một stream. Hãy đọc stream ID và phạm vi lỗi trước khi quyết định đóng session.

## 10. Checklist kiểm thử

Khi kiểm thử nhóm frame thiết lập và quản lý kết nối, hãy thử các tình huống sau:

1. Client gửi SETUP với phiên bản và MIME type được hỗ trợ; xác nhận request nghiệp vụ có thể bắt đầu sau khi phiên được chấp nhận.
2. Gửi SETUP với thông tin không hợp lệ; xác nhận server từ chối bằng lỗi cấp kết nối và client không tiếp tục gửi request trên phiên đó.
3. Giữ kết nối hoạt động đủ lâu; xác nhận KEEPALIVE được trao đổi và timeout được phát hiện khi peer ngừng phản hồi.
4. Bật lease; xác nhận client tuân thủ số request và TTL, sau đó tiếp tục khi lease mới được cấp.
5. Bật resume, ngắt transport tạm thời trong giới hạn buffer; xác nhận client có thể gửi RESUME và nhận RESUME_OK.
6. Làm resume token không hợp lệ hoặc để trạng thái phiên hết hạn; xác nhận server từ chối và client có thể tạo session mới.
7. Gây lỗi cho một stream; xác nhận những stream độc lập khác không bị đóng ngoài dự kiến.
8. Kiểm tra log và metric không làm lộ token hoặc metadata xác thực.

Các bài kiểm thử nên kiểm tra cả kết quả ở client lẫn trạng thái tài nguyên ở server: số session, số stream, buffer phát lại và subscription còn tồn tại sau reconnect.

## 11. Tóm tắt

SETUP khởi tạo RSocket session sau khi transport đã kết nối và thương lượng phiên bản, MIME type, keepalive cùng các khả năng tùy chọn. KEEPALIVE theo dõi khả năng giao tiếp của peer. LEASE giới hạn số request mới được khởi tạo trong một thời hạn. RESUME và RESUME_OK hỗ trợ tiếp tục một phiên cũ trên transport mới nếu token, trạng thái và dữ liệu phát lại vẫn còn hợp lệ. ERROR với stream ID bằng 0 báo lỗi cấp kết nối. Khi thiết kế ứng dụng Java và Spring Boot, cần kết hợp các frame này với timeout nghiệp vụ, backpressure, idempotency, bảo mật và quan sát vận hành.
