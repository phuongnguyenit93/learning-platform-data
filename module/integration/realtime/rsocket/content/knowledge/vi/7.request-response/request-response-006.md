# Thử lại khi mất phản hồi và nguy cơ thực thi lặp

## Bối cảnh: timeout không cho biết server đã làm gì

Request-response của RSocket phù hợp với thao tác cần gửi một request và nhận một response, chẳng hạn tra cứu trạng thái, tạo đơn hàng, xác nhận thanh toán hoặc cập nhật cấu hình thiết bị. Trong mạng thực tế, kết nối có thể bị ngắt hoặc response có thể đến muộn. Client thường đặt timeout và thử gửi lại request khi không nhận được phản hồi đúng hạn.

Vấn đề là **mất phản hồi không đồng nghĩa thao tác chưa được thực hiện**. Server có thể đã nhận request, cập nhật cơ sở dữ liệu thành công, nhưng response bị mất trên đường về client. Nếu client gửi lại một request mới, server có thể thực hiện cùng nghiệp vụ lần thứ hai.

Ví dụ, client gửi lệnh chuyển 500.000 đồng. Server ghi nợ tài khoản nguồn và ghi có tài khoản đích thành công. Ngay sau khi commit, kết nối bị ngắt trước khi client nhận response. Client chỉ nhìn thấy timeout. Nếu client tạo một request mới và server xử lý như một giao dịch mới, tài khoản có thể bị trừ tiền hai lần.

Bài học này giải thích cách nhận diện tình huống kết quả chưa rõ, phân biệt retry an toàn với retry nguy hiểm, và thiết kế idempotency để nhiều lần gửi cùng một yêu cầu chỉ tạo ra một kết quả nghiệp vụ.

## 1. Vòng đời của một request-response khi response bị mất

Một request-response thường có luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    participant DB as Database
    C->>S: REQUEST_RESPONSE: Transfer 500000
    S->>DB: Ghi nhận giao dịch
    DB-->>S: Commit thành công
    S-->>C: RESPONSE: Transfer completed
~~~

Nếu response bị mất sau khi database commit, client không thể phân biệt việc server chưa xử lý với việc server đã xử lý nhưng không gửi được kết quả.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    participant DB as Database
    C->>S: REQUEST_RESPONSE: Transfer 500000
    S->>DB: Ghi nhận giao dịch
    DB-->>S: Commit thành công
    S--xC: RESPONSE bị mất
    Note over C: Timeout, không biết giao dịch đã hoàn tất
    C->>S: REQUEST_RESPONSE: Transfer 500000 (retry)
    S->>DB: Ghi nhận giao dịch lần nữa?
    DB-->>S: Có thể tạo giao dịch thứ hai
    S-->>C: RESPONSE
~~~

Trong tình huống này, client biết rằng nó chưa nhận được response. Nó không biết chắc server đã nhận request chưa, đang xử lý, đã commit hay đã hoàn tất nhưng mất phản hồi.

Có thể chia kết quả quan sát thành bốn trường hợp:

| Trạng thái thực tế | Điều client nhìn thấy | Retry có thể gây ra điều gì? |
|---|---|---|
| Request chưa tới server | Timeout hoặc lỗi kết nối | Thử lại có thể giúp thao tác được thực hiện |
| Server nhận nhưng chưa xử lý | Timeout hoặc lỗi kết nối | Lần gửi lại có thể cạnh tranh với lần đầu |
| Server đang xử lý | Timeout | Hai lần xử lý có thể chạy đồng thời |
| Server đã commit, response bị mất | Timeout | Có nguy cơ thực hiện tác dụng phụ lần thứ hai |

Điểm khó nằm ở chỗ client thường không có bằng chứng đủ chắc để xác định nó đang ở hàng nào. Vì vậy, mọi chiến lược retry cho thao tác có tác dụng phụ phải tính đến khả năng request cũ đã được thực hiện.

## 2. Retry tạo ra request mới, không tự khôi phục kết quả cũ

Trong RSocket, mỗi tương tác request-response được gắn với một stream ID. Khi client thử lại, nó khởi tạo một lần tương tác mới. Giao thức RSocket cung cấp cách truyền request và response; bản thân nó không tự biết hai request có cùng ý nghĩa nghiệp vụ hay không.

Ví dụ, hai request sau có payload giống nhau:

~~~json
{
  "fromAccount": "A-100",
  "toAccount": "B-200",
  "amount": 500000
}
~~~

Server không thể kết luận chúng là hai lần gửi của cùng một thao tác hay hai yêu cầu chuyển tiền độc lập chỉ dựa trên nội dung. Hai giao dịch có thể hợp lệ nếu người dùng chủ động chuyển cùng số tiền hai lần.

Client cần gửi một định danh ổn định cho từng thao tác nghiệp vụ, thường gọi là **idempotency key**. Server dùng key đó để nhận ra các lần retry thuộc cùng một thao tác.

Cần phân biệt:

- **Stream ID:** nhận diện một tương tác ở cấp giao thức RSocket.
- **Request ID hoặc trace ID:** giúp theo dõi một lần gửi hoặc một trace qua các thành phần.
- **Operation ID:** nhận diện một công việc nghiệp vụ xuyên suốt vòng đời.
- **Idempotency key:** nhận diện cùng một ý định nghiệp vụ qua nhiều lần gửi, kể cả khi mỗi lần gửi dùng stream ID khác nhau.

Stream ID có thể thay đổi giữa các lần retry. Trace ID cũng có thể được tạo mới cho mỗi attempt hoặc liên kết các attempt vào cùng một trace. Idempotency key phải giữ nguyên cho tất cả lần gửi lại của cùng một thao tác.

## 3. Phân biệt at-most-once, at-least-once và effectively-once

Retry ảnh hưởng đến số lần một thao tác có thể được gửi và thực hiện.

| Cách tiếp cận | Đặc điểm | Rủi ro |
|---|---|---|
| Một lần gửi từ client (at-most-once attempt) | Client không retry sau lần gửi đầu | Có thể không biết kết quả hoặc thao tác không xảy ra nếu request chưa tới server |
| Gửi lại khi cần (at-least-once attempts) | Client tạo thêm attempt khi chưa nhận được response | Server có thể nhận và thực hiện nhiều lần |
| Effectively-once business effect | Có thể có nhiều lần gửi nhưng server khử trùng lặp theo key | Cần lưu trạng thái idempotency và phối hợp với transaction |

Không retry không tạo ra bảo đảm rằng thao tác chắc chắn được thực hiện một lần. Nó chỉ giới hạn số lần client chủ động gửi. Nếu kết nối hỏng trước khi server nhận request, thao tác có thể không xảy ra.

Retry cho khả năng phục hồi tốt hơn trước lỗi tạm thời, nhưng làm tăng khả năng request đến server nhiều lần. Đây là đặc tính thường thấy của hệ thống phân tán: việc gửi lại có thể cần thiết, nhưng không thể suy ra rằng lần gửi trước chắc chắn chưa có tác dụng.

Trong ứng dụng nghiệp vụ, mục tiêu thực tế thường là **effectively-once**: cho phép nhiều lần gửi cùng một ý định nhưng chỉ tạo một tác dụng phụ nghiệp vụ. Điều này đạt được bằng idempotency, transaction và khử trùng lặp ở phía xử lý. Nó không có nghĩa mạng chỉ truyền đúng một lần.

## 4. Xác định thao tác nào an toàn để retry

Trước khi thêm retry, hãy phân loại nghiệp vụ theo tác dụng của nó.

### Thao tác đọc

Một truy vấn chỉ đọc thường có thể retry khi gặp lỗi kết nối hoặc timeout, miễn là việc đọc không tạo tác dụng phụ và dữ liệu có thể thay đổi theo thời gian được chấp nhận.

Ví dụ:

- Đọc trạng thái thiết bị.
- Tra cứu thông tin đơn hàng.
- Lấy cấu hình hiện tại.

Kết quả của lần retry có thể khác lần đầu nếu dữ liệu thay đổi trong lúc chờ. Nếu cần đọc nhất quán tại một thời điểm, phải có cơ chế snapshot hoặc version dữ liệu phù hợp.

### Thao tác đặt trạng thái

Một lệnh đặt trạng thái thường có tính idempotent nếu lặp lại cùng giá trị không tạo thêm tác dụng phụ.

Ví dụ:

- Đặt nhiệt độ mục tiêu thành 22°C.
- Đặt trạng thái thiết bị thành OFF.
- Cập nhật địa chỉ giao hàng thành một giá trị xác định.

Gửi lại lệnh đặt cùng một giá trị thường cho kết quả trạng thái cuối giống nhau. Tuy nhiên, nếu mỗi lần cập nhật còn gửi thông báo, tính phí hoặc ghi nhận một sự kiện mới, các tác dụng phụ đó vẫn có thể bị lặp. Cần đánh giá toàn bộ nghiệp vụ, không chỉ phép gán dữ liệu.

### Thao tác tăng, tạo mới hoặc trừ tiền

Các thao tác này thường không idempotent nếu không có cơ chế bảo vệ:

- Tăng số dư hoặc tăng bộ đếm.
- Tạo một đơn hàng mới.
- Chuyển tiền hoặc trừ tồn kho.
- Gửi một lệnh kích hoạt thiết bị có tác dụng một lần.
- Phát hành một vé hoặc mã sử dụng một lần.

Nếu gửi lại cùng request, mỗi lần có thể tạo thêm một kết quả. Các thao tác này cần idempotency key hoặc một quy tắc nghiệp vụ tương đương.

### Cùng request có thể cần xử lý khác nhau theo ngữ cảnh

Một lệnh đặt nhiệt độ có thể được retry an toàn ở tầng cập nhật trạng thái. Nhưng nếu mỗi lần nhận lệnh đều gửi một email xác nhận, email có thể bị gửi nhiều lần. Tính idempotent phải được đánh giá từ đầu đến cuối, bao gồm database, message broker, dịch vụ bên ngoài và các thông báo.

## 5. Idempotency key: nhận diện cùng một ý định nghiệp vụ

Idempotency key là một mã do client tạo trước lần gửi đầu tiên và gắn với một thao tác nghiệp vụ. Khi timeout và cần retry, client gửi lại đúng key đó.

Ví dụ:

~~~json
{
  "idempotencyKey": "6bce1f3e-0c73-4e6e-a420-3e6dff6a9d8a",
  "fromAccount": "A-100",
  "toAccount": "B-200",
  "amount": 500000
}
~~~

Nếu client gửi lại cùng thao tác, payload tiếp tục dùng key này:

~~~json
{
  "idempotencyKey": "6bce1f3e-0c73-4e6e-a420-3e6dff6a9d8a",
  "fromAccount": "A-100",
  "toAccount": "B-200",
  "amount": 500000
}
~~~

Server có thể nhận ra đây là lần gửi lại của cùng một ý định và trả về kết quả đã ghi nhận thay vì tạo giao dịch mới.

### Quy tắc thiết kế key

Một idempotency key nên đáp ứng các yêu cầu:

- Được tạo một lần cho mỗi thao tác nghiệp vụ, trước lần gửi đầu tiên.
- Được giữ nguyên qua timeout, reconnect và mọi lần retry của thao tác đó.
- Đủ duy nhất trong phạm vi người dùng, tenant hoặc hệ thống phát sinh.
- Được gắn với đúng loại operation hoặc route.
- Không được dùng lại cho payload có nội dung khác.
- Được lưu đủ lâu để bao phủ khoảng thời gian retry và khả năng client gửi lại sau khi khởi động lại.

Key không nên được tạo mới trong mỗi lần retry. Nếu client tạo UUID bên trong một publisher factory được chạy lại khi retry, mỗi attempt sẽ có key khác và server không thể khử trùng lặp.

### Idempotency key khác trace ID

Trace ID phục vụ quan sát kỹ thuật. Một trace có thể bao gồm nhiều span và nhiều lần gọi. Idempotency key phục vụ bảo vệ tác dụng phụ nghiệp vụ. Không dùng trace ID làm idempotency key nếu hệ thống không bảo đảm nó ổn định qua mọi lần gửi lại của cùng một operation.

Nên lưu thêm request fingerprint, tức dấu vân tay của nội dung nghiệp vụ đã chuẩn hóa. Fingerprint giúp server phát hiện trường hợp client vô tình dùng lại key cho một request khác.

Ví dụ, cùng key nhưng lần đầu chuyển 500.000 đồng, lần sau chuyển 5.000.000 đồng. Server phải từ chối vì key đã được gắn với nội dung khác, thay vì trả về kết quả cũ hoặc thực hiện giao dịch mới.

## 6. Lưu trạng thái idempotency ở server

Server cần lưu dấu vết của operation để các instance khác nhau vẫn nhận diện được retry. Chỉ lưu key trong bộ nhớ của một process không đủ tin cậy: request retry có thể tới instance khác hoặc server có thể khởi động lại.

Một bảng idempotency có thể gồm:

| Cột | Mục đích |
|---|---|
| client_id hoặc tenant_id | Phạm vi chủ thể sở hữu key |
| operation | Tên nghiệp vụ hoặc route |
| idempotency_key | Key do client tạo |
| request_hash | Fingerprint của payload đã chuẩn hóa |
| status | IN_PROGRESS, SUCCEEDED hoặc trạng thái lỗi cuối |
| response_payload | Kết quả đã tạo để trả lại khi retry |
| created_at | Thời điểm bắt đầu |
| expires_at | Thời điểm hết thời hạn lưu key |

Tạo unique constraint trên tổ hợp client/tenant, operation và idempotency key. Unique constraint là lớp bảo vệ quan trọng khi hai request giống nhau đến đồng thời trên các instance khác nhau.

### Quy trình xử lý ở server

~~~mermaid
flowchart TD
    A["Nhận request và xác thực caller"] --> B["Tính request fingerprint"]
    B --> C["Tra cứu hoặc đăng ký idempotency key"]
    C --> D{"Key đã tồn tại?"}
    D -->|Chưa| E["Đăng ký IN_PROGRESS"]
    E --> F["Thực hiện nghiệp vụ và lưu kết quả"]
    F --> G["Commit trạng thái SUCCEEDED"]
    G --> H["Trả response"]
    D -->|Rồi| I{"Fingerprint có khớp?"}
    I -->|Không| J["Từ chối: key dùng cho request khác"]
    I -->|Có, đã thành công| K["Trả lại response đã lưu"]
    I -->|Có, đang xử lý| L["Chờ, hoặc trả trạng thái đang xử lý"]
    I -->|Có, lỗi cuối| M["Trả lại kết quả lỗi đã lưu theo chính sách"]
~~~

Một trình tự xử lý thực tế nên thực hiện các bước sau:

1. Xác thực caller và xác định phạm vi tenant/client từ danh tính đã xác thực.
2. Chuẩn hóa request và tính fingerprint.
3. Đăng ký key với unique constraint hoặc khóa giao dịch phù hợp.
4. Nếu key đã hoàn tất và fingerprint trùng, trả lại response đã lưu.
5. Nếu key đang xử lý, áp dụng chính sách chờ, trả trạng thái đang xử lý hoặc cho client truy vấn operation status.
6. Nếu key đã tồn tại nhưng fingerprint khác, trả lỗi conflict.
7. Nếu đây là request mới, thực hiện nghiệp vụ và lưu response cùng trạng thái hoàn tất.
8. Commit thay đổi theo một ranh giới transaction phù hợp.

### Phải lưu kết quả cùng tác dụng phụ một cách nhất quán

Với nghiệp vụ chỉ cập nhật cùng một database, cách an toàn thường là lưu bản ghi idempotency, thay đổi nghiệp vụ và response trong cùng transaction. Khi transaction commit, cả tác dụng phụ và kết quả idempotency cùng tồn tại. Nếu transaction rollback, server không để lại trạng thái thành công giả.

Ví dụ chuyển tiền cần bảo đảm việc ghi sổ giao dịch và đánh dấu key đã hoàn tất nằm trong một ranh giới nhất quán. Nếu ghi trạng thái SUCCEEDED trước khi cập nhật số dư, server có thể trả response thành công dù tác dụng phụ chưa xảy ra. Nếu cập nhật số dư trước nhưng không lưu key, retry có thể trừ tiền lần nữa.

### Xử lý hai request cùng key đến đồng thời

Hai request retry có thể tới hai instance gần như cùng lúc. Nếu chỉ kiểm tra key rồi mới insert mà không có unique constraint hoặc khóa phù hợp, cả hai instance có thể cùng thấy key chưa tồn tại và cùng thực hiện nghiệp vụ.

Unique constraint, transaction isolation và cơ chế khóa giúp chỉ một request giành quyền thực hiện. Request còn lại cần đọc trạng thái đã được tạo và xử lý theo trạng thái đó.

Nếu trạng thái là IN_PROGRESS, không nên tự động coi đây là lỗi cuối. Tùy thời gian xử lý, server có thể đợi kết quả, trả một response nghiệp vụ như PROCESSING kèm operation ID, hoặc yêu cầu client truy vấn lại sau. Cần có timeout và quy tắc phục hồi nếu process đang xử lý bị dừng giữa chừng.

### Không giữ IN_PROGRESS vĩnh viễn

Nếu hệ thống commit trạng thái IN_PROGRESS ở một transaction riêng để các request khác nhìn thấy operation đang chạy, server crash có thể để lại bản ghi IN_PROGRESS. Với thiết kế gộp bản ghi idempotency, tác dụng phụ và trạng thái SUCCEEDED trong cùng một transaction, transaction chưa commit thường sẽ rollback cùng nhau và bản ghi chưa hoàn tất không còn tồn tại. Hệ thống cần chọn rõ một trong hai cách và xác định cách phục hồi:

- Kiểm tra transaction đã commit hay chưa.
- Dùng lease hoặc thời hạn cho quyền xử lý.
- Cho phép worker phục hồi operation bị bỏ dở khi có thể xác định an toàn.
- Không tự động chạy lại tác dụng phụ nếu chưa biết lần trước đã đi tới đâu.

Trạng thái IN_PROGRESS cần có thời điểm bắt đầu, thông tin worker hoặc lease và quy tắc hết hạn. Chỉ xóa bản ghi cũ theo TTL mà không xét trạng thái có thể mở lại khả năng thực thi lặp.

Chỉ lưu lỗi cuối cùng khi hợp đồng quy định lỗi đó là kết quả ổn định, chẳng hạn request không hợp lệ. Với lỗi tạm thời xảy ra trước tác dụng phụ, có thể giải phóng quyền xử lý để cùng key được thử lại. Nếu không biết tác dụng phụ đã xảy ra hay chưa, phải đối soát hoặc truy vấn hệ thống phụ thuộc trước khi cho phép thực hiện lại.

## 7. Phối hợp idempotency với hệ thống bên ngoài

Một transaction database không thể tự động bao trùm một API thanh toán, email provider hoặc thiết bị IoT bên ngoài. Ví dụ server ghi nhận yêu cầu chuyển tiền trong database rồi gọi cổng thanh toán. Nếu cổng thanh toán đã thu tiền nhưng response bị mất, rollback database không thể thu hồi giao dịch ở hệ thống bên ngoài.

Với tác dụng phụ bên ngoài, cần phối hợp các mẫu thiết kế:

- **Outbox:** ghi sự kiện cần gửi vào outbox trong cùng transaction với thay đổi nghiệp vụ.
- **Idempotent consumer/inbox:** phía nhận lưu message ID hoặc idempotency key và khử trùng lặp.
- **Downstream idempotency key:** truyền cùng operation key tới nhà cung cấp nếu API bên ngoài hỗ trợ.
- **Reconciliation:** đối soát trạng thái khi kết quả bên ngoài chưa rõ.
- **Compensation:** tạo thao tác bù trừ nếu nghiệp vụ hỗ trợ và tác dụng phụ đã xảy ra.

Outbox giúp không mất ý định gửi khi transaction nội bộ commit, nhưng worker có thể gửi lại message nếu không nhận được xác nhận. Consumer vẫn cần khử trùng lặp. Với hệ thống vật lý, ví dụ thiết bị đã mở khóa cửa nhưng phản hồi mất, cần có command ID và trạng thái thiết bị để truy vấn trước khi quyết định gửi lại.

Không thể tạo bảo đảm exactly-once tổng quát chỉ bằng cách thêm một bảng idempotency ở một service. Mọi ranh giới có tác dụng phụ cần có cơ chế nhận diện operation hoặc đối soát phù hợp.

## 8. Retry có kiểm soát với Reactor và RSocketRequester

Trong ứng dụng Spring, RSocketRequester có thể trả về Mono cho request-response. Reactor cung cấp retryWhen để đăng ký lại publisher khi gặp lỗi phù hợp.

Ví dụ client gửi lệnh chuyển tiền:

~~~java
record TransferCommand(
    String idempotencyKey,
    String fromAccount,
    String toAccount,
    BigDecimal amount
) {}

Mono<TransferResult> transfer(TransferCommand command) {
    return requester
        .route("payments.transfer")
        .data(command)
        .retrieveMono(TransferResult.class)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isTransientFailure)
        )
        .timeout(Duration.ofSeconds(8));
}
~~~

Ví dụ minh họa ba lớp bảo vệ:

- Timeout 2 giây giới hạn thời gian chờ của từng attempt.
- Retry backoff thử lại tối đa ba lần, tăng khoảng chờ và thêm jitter để nhiều client không đồng loạt retry.
- Timeout 8 giây ở cuối pipeline giới hạn tổng thời gian caller chờ toàn bộ chuỗi attempt.

Đối tượng command được tạo trước khi gọi transfer và giữ nguyên idempotency key trong mọi lần retry. Server phải thực hiện khử trùng lặp theo key này. Nếu tạo key mới cho mỗi lần subscribe, cơ chế bảo vệ sẽ mất tác dụng.

Trong ứng dụng thực tế, cần bổ sung import, cấu hình RSocketRequester, DTO và hàm phân loại lỗi. Tên lớp exception cụ thể phụ thuộc phiên bản Spring/RSocket và cách ứng dụng chuyển lỗi giao thức thành lỗi miền nghiệp vụ.

### Chỉ retry lỗi có khả năng tạm thời

Hàm isTransientFailure cần được xây dựng theo loại lỗi mà hệ thống thực sự phát ra. Có thể cân nhắc retry cho:

- Timeout hoặc mất kết nối tạm thời.
- Lỗi transport có thể phục hồi sau reconnect.
- Tình trạng server quá tải nếu server xác định rõ đây là lỗi tạm thời.
- Một số lỗi dịch vụ phụ thuộc có thể thử lại an toàn.

Không nên retry tự động cho:

- Dữ liệu request không hợp lệ.
- Lỗi xác thực hoặc phân quyền.
- Không tìm thấy tài nguyên theo ngữ nghĩa nghiệp vụ.
- Conflict do idempotency key được dùng với payload khác.
- Lỗi deserialize hoặc MIME type không tương thích.
- Lỗi nghiệp vụ không thể khắc phục bằng cách gửi lại cùng request.

Đừng coi mọi RSocket error là lỗi tạm thời. Nếu retry lỗi validation hoặc authorization, client chỉ tạo thêm tải và làm chậm việc hiển thị lỗi thực sự.

### Backoff, jitter và giới hạn retry

Nếu nhiều client cùng timeout do một sự cố server, tất cả có thể retry ngay lập tức. Điều này tạo retry storm: tải tăng đúng lúc hệ thống đang yếu nhất.

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại. Jitter thêm độ ngẫu nhiên để các client không đồng bộ thời điểm retry. Giới hạn số lần retry và tổng deadline giúp request không chiếm tài nguyên vô hạn.

Ngoài ra, hệ thống nên có:

- Retry budget theo client hoặc service.
- Circuit breaker để tạm ngừng gọi dependency đang lỗi kéo dài.
- Giới hạn concurrency và rate limit.
- Metrics về số attempt, lỗi, timeout và retry exhaustion.
- Quy tắc không retry ở nhiều tầng cùng lúc nếu tổng số lần gửi sẽ bị nhân lên ngoài dự kiến.

Nếu client retry ba lần, gateway retry ba lần và service phụ thuộc retry ba lần, một thao tác có thể tạo nhiều request hơn con số mà mỗi nhóm tưởng mình đang cho phép. Cần xác định rõ một tầng sở hữu chính sách retry hoặc đặt ngân sách chung.

## 9. Xử lý timeout, CANCEL và kết quả chưa rõ

Khi client đặt timeout cho một Mono, Reactor có thể hủy subscription upstream. Với tương tác RSocket còn đang hoạt động, runtime có thể truyền tín hiệu hủy tới peer. Tuy nhiên, tín hiệu hủy không phải rollback.

Server có thể đã commit nghiệp vụ trước khi nhận CANCEL, hoặc công việc phía server có thể không dừng tức thì nếu nguồn upstream không hỗ trợ cancellation. Vì vậy:

- Timeout chỉ nói rằng client không nhận được kết quả trong thời gian quy định.
- Cancellation yêu cầu dừng tương tác và công việc có thể dừng.
- Không tín hiệu nào tự hoàn tác tác dụng phụ đã commit.
- Client cần dùng idempotency key hoặc truy vấn trạng thái operation để xác định kết quả.

Với thao tác có giá trị cao hoặc thời gian xử lý dài, một response request-response có thể trả về operation ID sau khi server chấp nhận công việc. Client dùng operation ID để truy vấn trạng thái bằng request-response khác hoặc đăng ký stream cập nhật. Cách này tách việc chấp nhận công việc khỏi thời gian hoàn tất nghiệp vụ.

Ví dụ response chấp nhận:

~~~json
{
  "operationId": "op-2026-000184",
  "status": "ACCEPTED"
}
~~~

Client có thể gọi route payments.operation-status với operationId. Nếu lần đầu mất response, client vẫn truy vấn lại bằng idempotency key hoặc operation ID đã biết, thay vì tạo một thao tác mới.

## 10. Ví dụ xử lý idempotency ở Spring RSocket

Controller có thể chuyển request tới một service chịu trách nhiệm kiểm soát idempotency:

~~~java
@Controller
class PaymentController {

    private final IdempotentPaymentService paymentService;

    PaymentController(IdempotentPaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @MessageMapping("payments.transfer")
    Mono<TransferResult> transfer(TransferCommand command) {
        return paymentService.execute(
            authenticatedClientId(),
            "payments.transfer",
            command.idempotencyKey(),
            fingerprint(command),
            () -> performTransfer(command)
        );
    }
}
~~~

Đây là phác thảo kiến trúc. IdempotentPaymentService phải thực hiện việc đăng ký key, kiểm tra fingerprint, xử lý request đồng thời và lưu response trong ranh giới transaction phù hợp. authenticatedClientId phải lấy từ danh tính đã xác thực của kết nối hoặc security context, không tin client tự khai báo clientId trong payload.

Một API service có thể áp dụng quy tắc:

| Trạng thái key | Fingerprint | Hành vi server |
|---|---|---|
| Chưa tồn tại | Bất kỳ | Đăng ký và xử lý nghiệp vụ |
| SUCCEEDED | Trùng | Trả lại response đã lưu |
| IN_PROGRESS | Trùng | Chờ hoặc trả operation đang xử lý |
| FAILED_FINAL | Trùng | Trả lại kết quả lỗi cuối theo hợp đồng |
| Đã tồn tại | Khác | Từ chối bằng lỗi conflict |

Nếu server lưu response đã hoàn tất, retry có thể nhận lại cùng kết quả nghiệp vụ ngay cả khi dữ liệu hiện tại trong hệ thống đã thay đổi. Điều này giúp client hiểu kết quả của operation ban đầu thay vì vô tình nhận kết quả của một thao tác mới.

## 11. Thời hạn lưu key và bảo vệ dữ liệu

Idempotency key cần được lưu lâu hơn khoảng thời gian mà client hoặc hệ thống trung gian có thể retry. Nếu key bị xóa quá sớm, một request cũ được gửi lại sau đó có thể được coi là operation mới.

Khi xác định TTL, cần xem xét:

- Timeout và số lần retry ở client.
- Thời gian client có thể offline trước khi gửi lại.
- Thời gian reconnect hoặc hàng đợi retry ở gateway.
- Thời gian xử lý và đối soát với hệ thống bên ngoài.
- Yêu cầu lưu vết của nghiệp vụ và quy định dữ liệu.

Key nên được giới hạn theo caller đã xác thực và operation. Không để một tenant sử dụng key của tenant khác để đọc lại response. Nếu response chứa dữ liệu nhạy cảm, phải áp dụng cùng chính sách authorization khi trả lại response đã lưu.

Không ghi toàn bộ payload nhạy cảm vào log chỉ để phục vụ deduplication. Có thể lưu fingerprint đã chuẩn hóa, trạng thái, operation ID và response cần thiết theo chính sách bảo vệ dữ liệu. Cần cân nhắc mã hóa, phân quyền truy cập và thời hạn lưu.

## 12. Kiểm thử retry và thực thi lặp

Unit test cho hàm retry chỉ xác nhận publisher được đăng ký lại. Nó không chứng minh server khử trùng lặp đúng trong tình huống response mất sau commit. Cần kiểm thử cả client, server và kho lưu idempotency.

Các tình huống quan trọng:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Request chưa tới server rồi client retry | Operation được thực hiện một lần |
| Server commit nhưng response bị làm mất | Retry trả lại kết quả cũ, không tạo tác dụng phụ lần hai |
| Hai request cùng key đến đồng thời | Chỉ một request thực hiện nghiệp vụ |
| Cùng key nhưng payload khác | Server trả conflict |
| Server restart sau khi commit | Retry vẫn tìm thấy kết quả đã lưu |
| Key đang IN_PROGRESS | Client nhận trạng thái đang xử lý hoặc chờ theo chính sách |
| Lỗi validation | Không retry tự động |
| Timeout tổng thể hết hạn | Caller nhận lỗi timeout, operation vẫn có thể cần truy vấn trạng thái |
| Key hết TTL rồi request cũ được gửi lại | Hành vi tuân theo chính sách hết hạn đã công bố |

### Kiểm thử retry bằng StepVerifier

Ví dụ publisher thất bại hai lần do lỗi tạm thời rồi thành công:

~~~java
@Test
void retriesTransientFailure() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        int current = attempts.incrementAndGet();

        if (current < 3) {
            return Mono.error(new TemporaryServiceException());
        }

        return Mono.just("completed");
    });

    StepVerifier.withVirtualTime(() ->
        source.retryWhen(
            Retry.backoff(2, Duration.ofSeconds(1))
                .jitter(0)
        )
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("completed")
    .verifyComplete();

    assertEquals(3, attempts.get());
}
~~~

Test này kiểm tra publisher được thử lại theo chính sách. Đối với idempotency, cần integration test sử dụng database thật hoặc test container, gửi cùng key nhiều lần và xác nhận chỉ có một bản ghi nghiệp vụ.

### Kiểm thử điểm mất response sau commit

Một bài kiểm thử quan trọng nên mô phỏng:

1. Server nhận request và thực hiện transaction.
2. Database commit thành công.
3. Test làm mất response trước khi client nhận.
4. Client gửi lại cùng idempotency key.
5. Server trả response đã lưu.
6. Database chỉ có một tác dụng phụ nghiệp vụ.

Đây là tình huống chứng minh cơ chế idempotency hoạt động ở đúng ranh giới cần bảo vệ.

## 13. Những lỗi thường gặp khi triển khai retry

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Retry mọi lỗi | Tăng tải và lặp lỗi không thể khắc phục | Phân loại lỗi trước khi retry |
| Tạo idempotency key mới ở mỗi attempt | Server coi retry là operation mới | Tạo key một lần và giữ nguyên |
| Dùng stream ID làm idempotency key | Mỗi lần retry có stream ID mới | Dùng key nghiệp vụ ổn định |
| Chỉ lưu key trong memory | Mất dedup khi restart hoặc đổi instance | Lưu trạng thái dùng chung và bền vững |
| Kiểm tra key rồi insert mà không khóa | Hai request đồng thời cùng thực hiện | Unique constraint và transaction |
| Chỉ lưu key, không lưu fingerprint | Cùng key nhưng payload khác có thể bị chấp nhận | So sánh request fingerprint |
| Lưu SUCCEEDED tách khỏi transaction nghiệp vụ | Trạng thái key và tác dụng phụ không nhất quán | Gắn chúng vào cùng ranh giới commit |
| Coi timeout là thất bại nghiệp vụ | Client tạo operation mới trong khi operation cũ đã hoàn tất | Truy vấn trạng thái hoặc retry cùng key |
| Coi CANCEL là rollback | Tác dụng phụ đã commit không được hoàn tác | Dùng idempotency và compensation nếu cần |
| Retry vô hạn | Giữ tài nguyên và gây retry storm | Backoff, jitter, retry budget và deadline |
| Xóa key quá sớm | Request cũ có thể được thực hiện lại | TTL dựa trên thời gian retry và đối soát |
| Bỏ qua tác dụng phụ bên ngoài | Database dedup nhưng email/thanh toán vẫn lặp | Outbox, inbox và idempotency ở downstream |

## Kết luận

Khi client RSocket timeout, điều chắc chắn duy nhất là nó chưa nhận được response đúng hạn. Server có thể chưa nhận request, đang xử lý hoặc đã commit nghiệp vụ nhưng mất phản hồi. Vì vậy, retry một request có tác dụng phụ luôn cần xem xét nguy cơ thực thi lặp.

Hãy phân loại lỗi, đặt timeout và retry budget hợp lý, dùng backoff cùng jitter, và giữ một idempotency key ổn định cho mỗi ý định nghiệp vụ. Server cần lưu key, fingerprint, trạng thái và response một cách bền vững; dùng transaction và unique constraint để xử lý cả các lần retry đồng thời. Với tác dụng phụ bên ngoài, hãy bổ sung outbox, inbox, idempotency ở downstream và đối soát.

RSocket cung cấp request-response và cơ chế truyền dữ liệu. Bảo đảm một tác dụng phụ nghiệp vụ chỉ xảy ra một lần cần được thiết kế ở tầng ứng dụng và các hệ thống phụ thuộc.
