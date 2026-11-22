# RSocket Resume: khôi phục phiên sau khi mất kết nối

Resume là phần mở rộng tùy chọn của giao thức RSocket, cho phép hai đầu tiếp tục một phiên RSocket đang tồn tại sau khi kết nối transport bị gián đoạn. Client mở một transport connection mới và đề nghị server nối lại phiên cũ. Nếu cả hai bên còn giữ đủ trạng thái và các frame cần phát lại, những stream đang chạy có thể tiếp tục mà không phải tạo lại toàn bộ phiên.

Resume giải quyết gián đoạn mạng tạm thời như Wi-Fi chuyển mạng, TCP connection bị reset hoặc đường truyền mất trong một khoảng ngắn. Khả năng này phụ thuộc vào việc client và server cùng hỗ trợ, cùng giữ trạng thái phiên và còn lưu được các frame cần thiết. Resume không phải cơ chế lưu trữ thông điệp bền vững và không bảo đảm phiên luôn khôi phục được.

## 1. Phân biệt Resume, reconnect và tạo phiên mới

Ba hành vi này thường bị nhầm lẫn:

| Hành vi | Điều xảy ra sau khi mất kết nối | Trạng thái stream cũ |
|---|---|---|
| Resume | Client kết nối transport mới rồi gửi yêu cầu tiếp tục phiên cũ | Được khôi phục nếu server chấp nhận và hai bên còn đủ trạng thái/frame |
| Reconnect thông thường | Client tạo một RSocket connection mới | Không tự khôi phục stream đang chạy; ứng dụng phải quyết định request hoặc subscribe lại |
| Tạo phiên mới | Client gửi SETUP như một kết nối ban đầu | Là phiên mới, có thể cần xác thực, setup và khôi phục trạng thái nghiệp vụ từ ứng dụng |

Resume là một tính năng ở tầng giao thức/connector. Ứng dụng vẫn dùng các interaction model quen thuộc như request-response, request-stream, fire-and-forget và request-channel. Các handler Spring dùng @MessageMapping không phải tự triển khai việc lưu hay phát lại frame.

## 2. Trạng thái phiên cần được giữ

Một phiên RSocket không chỉ là socket TCP. Nó còn chứa trạng thái giao thức để hai bên hiểu những stream nào đang hoạt động và frame nào đã được nhận.

Những dữ liệu quan trọng cho Resume gồm:

- **Resume Identification Token:** token mờ (opaque) dùng để server tìm đúng phiên cũ. Client dùng lại token đã gửi trong SETUP ban đầu khi gửi RESUME. Server không nên suy diễn cấu trúc token.
- **Vị trí frame theo từng chiều:** mỗi bên theo dõi vị trí ngầm định (implied position) của các frame được gửi và nhận. Vị trí được tính theo thứ tự frame, không phải một trường số thứ tự lặp lại trong mọi frame.
- **Frame cần phát lại:** mỗi bên giữ các frame đã gửi nhưng chưa thể xác nhận là phía kia đã nhận. Frame store phải còn đủ dữ liệu để phát lại từ vị trí mà peer báo.
- **Trạng thái stream và giao thức:** các stream ID, trạng thái requester/responder, tiến trình tương tác và thông tin cần thiết để tiếp tục phiên.
- **Thời hạn và vòng đời phiên:** server phải giữ phiên đủ lâu để client có cơ hội kết nối lại. Khi phiên hết hạn hoặc bị loại khỏi bộ nhớ, token không còn giúp khôi phục phiên.

Theo giao thức, các frame REQUEST, CANCEL, ERROR và PAYLOAD có vị trí ngầm định. Các frame khác không tham gia chuỗi vị trí này. KEEPALIVE có thể mang vị trí đã nhận để peer cập nhật trạng thái và loại bỏ phần frame store không còn cần thiết.

Không được nhầm Resume Identification Token với thông tin xác thực người dùng. Token có mục đích nhận diện phiên; ứng dụng vẫn phải thực hiện xác thực và phân quyền theo thiết kế bảo mật của mình. Token nên khó đoán, duy nhất cho từng phiên và chỉ có hiệu lực trong vòng đời phiên đó.

## 3. Luồng RESUME và RESUME_OK

### 3.1. Thiết lập phiên ban đầu

Khi bắt đầu kết nối, client gửi SETUP. Nếu client muốn dùng Resume, SETUP bật cờ Resume và mang Resume Identification Token. Server phải hỗ trợ Resume thì mới có thể chấp nhận khả năng này.

Sau khi phiên được thiết lập, client và server bắt đầu theo dõi vị trí frame theo từng chiều và lưu các frame cần thiết cho việc phát lại.

### 3.2. Mất transport connection

Khi transport connection bị đứt, phiên logic có thể vẫn được giữ lại. Hai bên giữ trạng thái và frame store trong khoảng thời gian cho phép Resume. Việc transport bị đóng không đồng nghĩa ngay lập tức với việc phiên đã bị hủy; điều này phụ thuộc vào chính sách vòng đời phiên của implementation.

### 3.3. Client mở kết nối mới và gửi RESUME

Client tạo một transport connection mới tới endpoint có thể tìm được trạng thái phiên cũ, sau đó gửi RESUME với:

1. Phiên bản giao thức.
2. Resume Identification Token giống token trong SETUP ban đầu.
3. Last Received Server Position: vị trí cuối cùng mà client đã nhận thành công từ server.
4. First Available Client Position: vị trí sớm nhất của frame phía client vẫn còn giữ để có thể phát lại.

Trong lúc chờ kết quả Resume, client không được gửi các loại frame thông thường khác. RESUME là bước đầu tiên trên transport connection mới.

### 3.4. Server kiểm tra và phản hồi

Server dùng token để tìm phiên, sau đó kiểm tra xem trạng thái phiên và frame store có đáp ứng được các vị trí mà client cung cấp hay không.

- Nếu có thể tiếp tục, server gửi RESUME_OK. Frame này mang Last Received Client Position, tức vị trí cuối cùng server đã nhận từ client.
- Nếu server không hỗ trợ Resume, không nhận diện được token hoặc không còn đủ frame/trạng thái, server có thể từ chối bằng ERROR[REJECTED_RESUME].
- Các lỗi kết nối tạm thời có thể được xử lý theo retry policy của implementation. Khi nhận ERROR[REJECTED_RESUME], client không được tiếp tục thử Resume cho cùng yêu cầu đó.

### 3.5. Phát lại frame và tiếp tục stream

Sau RESUME_OK, hai bên dùng các vị trí đã trao đổi để xác định phần frame còn thiếu:

- Client phát lại các frame bắt đầu từ Last Received Client Position do server trả về.
- Server phát lại các frame bắt đầu sau Last Received Server Position mà client đã báo trong RESUME.

Các frame được phát lại theo đúng thứ tự giao thức. Khi phần dữ liệu còn thiếu đã được xử lý, các stream tiếp tục trên transport connection mới. Ứng dụng không cần tự tạo một request mới cho từng frame đã được Resume khôi phục.

## 4. Điều kiện hỗ trợ ở cả client và server

Resume chỉ hoạt động khi các điều kiện sau được đáp ứng đồng thời.

### Client

- Implementation của client có hỗ trợ Resume và bật tính năng này khi gửi SETUP.
- Client giữ nguyên token của phiên ban đầu.
- Client còn giữ các frame outbound cần phát lại; vị trí First Available Client Position phải cho phép đáp ứng yêu cầu của server.
- Client có retry policy để tạo transport connection mới trong khoảng thời gian phiên còn hiệu lực.
- Client tiếp tục dùng cấu hình giao thức tương thích với phiên ban đầu, bao gồm cách mã hóa data và metadata.

### Server

- Server implementation có hỗ trợ Resume và được cấu hình bật tính năng này.
- Server còn giữ phiên tương ứng với token.
- Server còn giữ đủ các frame outbound kể từ vị trí cuối cùng client xác nhận đã nhận.
- Session manager chưa hết hạn hoặc loại bỏ phiên.
- Transport connection mới được định tuyến đến server có thể truy cập đúng trạng thái phiên.

### Cả hai phía

- Cả hai bên phải duy trì trạng thái trong suốt thời gian mất kết nối. Chỉ bật Resume ở client là chưa đủ.
- Phiên bản giao thức và các thiết lập kết nối phải tương thích. Resume giả định các thông số như định dạng data/metadata không bị thay đổi giữa phiên cũ và lần nối lại.
- Frame store phải đủ dung lượng cho lưu lượng phát sinh trong khoảng thời gian mất kết nối. Nếu cần phát lại một frame nhưng frame đó đã bị loại khỏi store, Resume không thể hoàn tất.
- Thời gian giữ phiên phải phù hợp với khoảng gián đoạn mạng mà hệ thống muốn hỗ trợ.
- Với hệ thống nhiều node, load balancer phải đưa yêu cầu Resume đến node có phiên, hoặc các node phải dùng cơ chế lưu trữ/đồng bộ trạng thái phiên tương thích. Chỉ dùng sticky session không giúp khôi phục phiên nếu node đã mất trạng thái.

## 5. Cấu hình trong Spring Framework và RSocket Java

Spring cung cấp RSocketRequester để gửi request ở mức ứng dụng. Builder có callback rsocketConnector để tùy chỉnh io.rsocket.core.RSocketConnector, bao gồm cấu hình Resume. Vì vậy, Resume được bật ở tầng connector, không phải bằng cách thêm logic khôi phục vào từng phương thức @MessageMapping.

### 5.1. Cấu hình phía client

Đây là đoạn cấu hình minh họa cho Spring Framework kết hợp RSocket Java. Các import cần thiết gồm RSocketRequester, Resume, Retry và Duration. Ví dụ giả định transport TCP ở localhost:7000.

~~~java
Resume resume = new Resume()
        .sessionDuration(Duration.ofMinutes(5))
        .retry(Retry.fixedDelay(6, Duration.ofSeconds(1)));

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.resume(resume))
        .tcp("localhost", 7000);
~~~

Đây là fragment cấu hình, không phải chương trình độc lập: ứng dụng vẫn cần dependency RSocket phù hợp, cấu hình transport, xử lý lỗi và các request thực tế. sessionDuration xác định khoảng thời gian implementation giữ phiên để có thể nối lại. retry xác định chính sách thử kết nối lại; cần chọn số lần thử và khoảng chờ theo mục tiêu vận hành.

### 5.2. Cấu hình phía server

Server cũng phải bật Resume. Với RSocket Java, có thể cấu hình trên RSocketServer trước khi bind transport:

~~~java
Resume resume = new Resume()
        .sessionDuration(Duration.ofMinutes(5));

RSocketServer.create(acceptor)
        .resume(resume)
        .bind(serverTransport);
~~~

Đây cũng là fragment: acceptor và serverTransport do ứng dụng cung cấp. Nếu Spring Boot tự tạo RSocket server, hãy áp dụng cấu hình vào RSocketServer thông qua hook tùy chỉnh mà phiên bản Spring Boot đang dùng hỗ trợ. Cấu hình client và server phải được triển khai độc lập; việc client bật Resume không tự động bật Resume trên server.

### 5.3. Vai trò của các thành phần Spring

- **RSocketRequester:** API cấp cao để gửi request và chuyển đổi payload thành object. Nó dùng RSocketConnector bên dưới.
- **RSocketConnector:** thiết lập kết nối phía client và cấu hình Resume qua resume(...).
- **RSocketServer:** thiết lập phía server và phải được cấu hình Resume tương ứng.
- **@MessageMapping:** xử lý message theo route ở tầng ứng dụng. Handler không thay thế session manager hoặc frame store.
- **RSocketStrategies:** cấu hình encoder/decoder và cách chuyển đổi data, metadata. Khi nối lại, cách mã hóa phải tương thích với phiên ban đầu.

Tên API và điểm mở rộng cấu hình server có thể thay đổi theo phiên bản Spring Framework, Spring Boot và RSocket Java. Hãy đối chiếu Javadoc của đúng phiên bản dependency trong dự án trước khi áp dụng cấu hình.

## 6. Thời hạn phiên, retry và dung lượng frame store

### sessionDuration

sessionDuration là khoảng thời gian implementation giữ phiên sau khi transport bị ngắt để chờ Resume. Giá trị quá ngắn làm client hết cơ hội khôi phục khi mạng gián đoạn lâu. Giá trị quá dài làm tăng thời gian giữ session object và frame store, tiêu thụ bộ nhớ và tài nguyên.

Chọn thời hạn dựa trên thời gian gián đoạn cần chịu đựng, tốc độ phát sinh frame và giới hạn tài nguyên. Cần có cơ chế dọn phiên hết hạn để tránh giữ trạng thái vô hạn.

### Retry policy

Retry policy quyết định client thử thiết lập lại transport như thế nào. Nên dùng khoảng chờ có kiểm soát, giới hạn số lần thử phù hợp và ghi log có ngữ cảnh. Retry quá dày có thể tạo tải lớn khi server đang phục hồi. Retry kéo dài hơn thời hạn phiên cũng không giúp ích vì server có thể đã loại bỏ trạng thái.

Retry kết nối không đồng nghĩa với việc mọi lỗi đều có thể Resume. Khi server trả REJECTED_RESUME, client phải coi phiên cũ không thể tiếp tục và chuyển sang quy trình tạo phiên mới.

### Frame store

Dung lượng frame store phụ thuộc vào lưu lượng và thời gian mất kết nối. Có thể ước lượng sơ bộ lượng dữ liệu cần giữ bằng:

~~~text
Dung lượng dữ liệu tối thiểu ≈ tốc độ frame outbound × thời gian mất kết nối
~~~

Đây chỉ là ước lượng phần payload/frame cơ bản; triển khai thực tế còn có overhead, metadata, nhiều phiên đồng thời và biên an toàn. Theo dõi số phiên đang giữ, số frame chờ phát lại, dung lượng store, số lần Resume thành công/thất bại và số lần bị từ chối do thiếu trạng thái.

KEEPALIVE và vị trí đã nhận giúp implementation xác định phần frame nào peer đã nhận để dọn store. Tuy nhiên, việc dọn frame phải dựa trên thông tin vị trí hợp lệ; dọn quá sớm có thể khiến lần Resume sau không còn đủ dữ liệu.

## 7. Các trường hợp Resume thất bại

| Nguyên nhân | Vì sao không thể tiếp tục | Hướng xử lý |
|---|---|---|
| Server không hỗ trợ Resume | Server từ chối loại kết nối này | Bật Resume ở server hoặc dùng reconnect và xử lý retry ở tầng ứng dụng |
| Token không được nhận diện | Server không tìm thấy phiên cũ | Kiểm tra token, định tuyến và vòng đời session manager |
| Phiên đã hết hạn | Trạng thái phiên đã được dọn | Điều chỉnh sessionDuration nếu phù hợp; tạo phiên mới khi đã hết hạn |
| Frame store thiếu dữ liệu | Một hoặc nhiều frame cần phát lại không còn được giữ | Điều chỉnh dung lượng/lifetime của store và tốc độ phát sinh frame |
| Client hoặc server khởi động lại | Trạng thái trong bộ nhớ tiến trình có thể đã mất | Cần cơ chế lưu trữ và khôi phục trạng thái phiên bền vững nếu muốn hỗ trợ restart |
| Load balancer chuyển sang node khác | Node mới không có trạng thái của phiên | Dùng session affinity hoặc cơ chế chia sẻ/khôi phục trạng thái phù hợp |
| Cấu hình giao thức thay đổi | Thiết lập phiên mới không tương thích với phiên ban đầu | Giữ cấu hình tương thích trong thời gian phiên có thể được Resume |
| Client hết thời gian retry | Transport không được nối lại trong thời hạn phiên | Điều chỉnh retry và sessionDuration theo SLO thực tế |

Khi Resume bị từ chối, ứng dụng có thể tạo một phiên mới bằng SETUP. Nếu cần tiếp tục một luồng dữ liệu nghiệp vụ, ứng dụng nên gửi cursor, offset hoặc mã phiên nghiệp vụ để server phát tiếp từ điểm đã lưu. Không được giả định rằng một phiên RSocket mới tự biết vị trí nghiệp vụ mà phiên cũ đã xử lý.

## 8. Resume bảo đảm điều gì và không bảo đảm điều gì?

Resume khôi phục trạng thái giao thức và hỗ trợ phát lại frame trong phạm vi mà cả hai bên còn giữ đủ dữ liệu. Nó giúp các stream đang hoạt động tiếp tục sau một số lỗi transport mà không cần khởi tạo lại toàn bộ tương tác.

Resume tự nó không phải message broker hoặc kho lưu trữ bền vững. Nếu tiến trình server bị dừng và session/frame store chỉ nằm trong RAM, trạng thái có thể mất. Khả năng Resume qua restart hoặc failover cần implementation lưu và khôi phục session state, frame store, token mapping và định tuyến tương ứng. Không nên mặc định rằng bật Resume là đủ để đạt khả năng chịu lỗi khi triển khai nhiều node.

Resume cũng không định nghĩa tính nguyên tử, transaction hoặc exactly-once cho các tác động nghiệp vụ. Ứng dụng vẫn cần thiết kế idempotency key, transaction boundary, cursor/offset và lưu trạng thái nghiệp vụ khi thao tác có thể được gửi lại hoặc khi phải tạo phiên mới. Với dữ liệu sự kiện quan trọng, hãy lưu checkpoint nghiệp vụ ở nơi bền vững thay vì chỉ dựa vào vị trí frame của RSocket.

Lease cũng không mặc nhiên tiếp tục từ kết nối trước. Theo giao thức, ngữ nghĩa Lease phải được khởi động lại trên kết nối mới bằng LEASE frame từ server nếu tính năng Lease đang được sử dụng.

## 9. Checklist triển khai và vận hành

- [ ] Client bật Resume trong SETUP và lưu token của phiên.
- [ ] Server bật Resume và có thể tra cứu token về đúng session.
- [ ] Cả hai phía giữ frame store và trạng thái stream đủ lâu.
- [ ] Retry policy phù hợp với sessionDuration và thời gian phục hồi dự kiến.
- [ ] Load balancer đưa RESUME về đúng node hoặc trạng thái phiên được chia sẻ/khôi phục.
- [ ] Data MIME type, metadata MIME type và thiết lập giao thức tương thích với phiên ban đầu.
- [ ] Có giới hạn bộ nhớ, dọn session hết hạn và theo dõi frame store.
- [ ] Có fallback tạo phiên mới cùng cơ chế khôi phục cursor/offset nghiệp vụ.
- [ ] Các thao tác nghiệp vụ có thể được gửi lại được bảo vệ bằng idempotency hoặc transaction phù hợp.
- [ ] Có log và metric phân biệt lỗi transport, lỗi retry, RESUME_OK và REJECTED_RESUME.

## 10. Cách chẩn đoán nhanh

**Client liên tục kết nối lại nhưng stream không tiếp tục:** kiểm tra xem client có thực sự cấu hình resume(...) hay chỉ dùng reconnect(...), server đã bật Resume chưa, và transport mới có đến đúng node giữ phiên không.

**Resume hoạt động khi mất mạng ngắn nhưng thất bại sau thời gian dài:** kiểm tra sessionDuration, retry policy và thời điểm session manager dọn phiên. Kiểm tra thêm frame store có bị đầy hoặc loại frame cần phát lại hay không.

**Resume thất bại sau khi deploy/restart:** nếu trạng thái chỉ nằm trong RAM, server mới không có session cũ. Cần shared/persistent session state hoặc chấp nhận tạo phiên mới và khôi phục từ cursor nghiệp vụ.

**Ứng dụng xử lý trùng tác động nghiệp vụ:** kiểm tra ranh giới transaction và idempotency của handler. Vị trí frame của RSocket không thay thế khóa idempotency hoặc checkpoint nghiệp vụ.

**Lease không còn hiệu lực sau khi Resume:** khởi động lại Lease theo giao thức trên kết nối mới và kiểm tra cấu hình cấp lease ở server.

## Tài liệu tham khảo

- RSocket Protocol — phần Resuming Operation, RESUME và RESUME_OK: https://github.com/rsocket/rsocket/blob/master/Protocol.md#resuming-operation
- Spring Framework Reference — RSocket Support và cấu hình RSocketRequester: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework Javadoc — RSocketRequester.Builder.rsocketConnector(...): https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- RSocket Java — RSocketConnector và resume(Resume): https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java
