# jti kết hợp kho trạng thái dùng một lần

## 1. jti không tự ngăn được replay

JWT có registered claim jti (JWT ID) để cung cấp định danh cho từng token. Issuer tạo giá trị sao cho xác suất hai token khác nhau nhận cùng một ID là không đáng kể. Claim này hữu ích cho việc nhận diện token, ghi log sự kiện, thu hồi hoặc phát hiện một token đã được sử dụng.

Tuy nhiên, jti chỉ là một giá trị nằm trong JWT. Nếu verifier chỉ xác minh chữ ký, issuer, audience và thời hạn rồi chấp nhận token, cùng một JWT vẫn có thể được gửi lại nhiều lần trong thời gian còn hiệu lực. Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành; nó không ghi nhớ token đã được sử dụng.

Muốn dùng jti để chống phát lại trong một luồng token dùng một lần, hệ thống cần một kho trạng thái dùng chung để ghi nhận việc tiêu thụ token. Việc kiểm tra và ghi nhận phải là một thao tác nguyên tử:

- Lần sử dụng hợp lệ đầu tiên: ghi nhận jti thành công và tiếp tục xử lý.
- Những lần gửi lại cùng token: phát hiện jti đã tồn tại và từ chối.
- Nhiều yêu cầu đồng thời: chỉ một yêu cầu được quyền tiêu thụ jti.

**jti cung cấp định danh; kho trạng thái và thao tác tiêu thụ nguyên tử mới tạo ra cơ chế phát hiện replay.**

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. jti biểu diễn điều gì?

RFC 7519 định nghĩa jti là một định danh duy nhất của JWT. Giá trị này phân biệt token với những token khác được issuer tạo ra; khi có nhiều issuer, bên nhận cần tránh xung đột giữa các namespace định danh.

Ví dụ Claims Set:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "account-42",
  "aud": "https://api.example.org/account-actions",
  "iat": 1893456000,
  "exp": 1893456300,
  "jti": "reset-7f31b8d9e2"
}
~~~

Đây là payload minh họa, chưa phải JWT đã ký. Trong ví dụ, jti nhận diện một token đặt lại thông tin tài khoản. Nếu token được thiết kế để dùng một lần, lần tiêu thụ thành công đầu tiên sẽ đánh dấu định danh này là đã dùng.

### 2.1. Yêu cầu đối với giá trị jti

Một jti phù hợp nên:

- Được tạo bằng nguồn ngẫu nhiên mật mã hoặc cơ chế định danh có tính duy nhất tương đương.
- Có không gian giá trị đủ lớn để xác suất trùng lặp không đáng kể.
- Không chứa thông tin cá nhân, mật khẩu hoặc dữ liệu bí mật.
- Không dễ đoán theo số thứ tự, timestamp hoặc ID tài khoản.
- Được issuer tạo mới cho mỗi token cần định danh riêng.

Không dùng cùng một jti cho nhiều token độc lập. Nếu issuer vô tình tái sử dụng jti, kho trạng thái có thể từ chối nhầm một token hợp lệ hoặc làm sai lệch việc nhận diện token.

### 2.2. jti không phải nonce cho mọi giao thức

jti là định danh token. Nonce thường là một giá trị thách thức hoặc giá trị dùng một lần gắn với một giao dịch cụ thể. Một hệ thống có thể dùng cả hai:

- jti nhận diện JWT.
- Nonce ràng buộc token hoặc bằng chứng với một giao dịch, yêu cầu hay phiên cụ thể.

Không nên mặc định jti tự ràng buộc token với HTTP method, URL, body hoặc giao dịch nghiệp vụ. Nếu cần ràng buộc như vậy, phải có claims hoặc proof riêng được xác minh theo một profile rõ ràng.

## 3. Khi nào nên dùng kho trạng thái một lần?

Cơ chế này phù hợp khi credential được thiết kế để chỉ được chấp nhận một lần hoặc một giao dịch chỉ được thực hiện một lần.

Ví dụ:

| Trường hợp | Ý nghĩa của việc dùng một lần |
| --- | --- |
| Link đặt lại mật khẩu | Chỉ lần sử dụng hợp lệ đầu tiên được đặt lại mật khẩu |
| Link xác minh email | Không thể dùng lại cùng token để lặp lại hành động xác minh |
| Lời mời tham gia tổ chức | Một lời mời chỉ được chấp nhận một lần |
| Magic link đăng nhập | Một link không thể tạo nhiều phiên đăng nhập độc lập |
| JWT assertion dùng để đổi token | Một assertion đã được chấp nhận không được dùng lại trong cửa sổ hiệu lực |
| Xác nhận giao dịch nhạy cảm | Một challenge/token xác nhận chỉ được tiêu thụ cho một giao dịch |
| DPoP proof | Một proof JWT không được chấp nhận lại trong thời gian chống replay |

Điểm chung là hệ thống có thể xác định rõ **đơn vị nào chỉ được tiêu thụ một lần**: token, assertion, proof hoặc challenge.

### 3.1. Không biến access token thông thường thành token một lần

Access token OAuth thường được dùng cho nhiều request trong thời hạn của nó. Ví dụ một ứng dụng có thể gọi GET /profile, GET /orders và GET /notifications bằng cùng access token. Nếu resource server đánh dấu jti của access token là đã dùng sau request đầu tiên, các request hợp lệ tiếp theo sẽ bị từ chối.

Vì vậy:

- Không áp dụng consume-once cho jti của access token thông thường trừ khi hợp đồng token nói rõ token chỉ được dùng một lần.
- jti của access token có thể được dùng làm định danh để ghi log, denylist hoặc thu hồi.
- Chống phát lại một bearer access token thường cần sender constraint, proof-of-possession hoặc cơ chế phù hợp với giao thức, thay vì đơn giản tiêu thụ access token ở request đầu tiên.
- Với DPoP, jti của **proof JWT** có thể được lưu để phát hiện cùng một proof bị gửi lại; đây là đơn vị khác với access token.

## 4. Kiến trúc jti + kho trạng thái dùng một lần

Một hệ thống thường có các thành phần:

1. **Issuer:** tạo JWT có jti riêng và thời hạn phù hợp.
2. **Verifier/API:** xác minh JWT và xác định token có thuộc luồng dùng một lần không.
3. **Replay store:** lưu các jti đã được tiêu thụ.
4. **Business handler:** thực hiện hành động sau khi tiêu thụ thành công.

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Xác minh chữ ký, issuer, audience, thời gian, loại token"]
    B --> C["Kiểm tra jti bắt buộc và hợp lệ"]
    C --> D["Tạo khóa replay theo issuer + purpose + jti"]
    D --> E{"Ghi nhận nguyên tử: chưa tồn tại?"}
    E -->|"Có, lần đầu"| F["Đánh dấu đã tiêu thụ"]
    E -->|"Không, đã tồn tại"| G["Từ chối replay"]
    F --> H["Thực hiện hành động nghiệp vụ"]
    H --> I["Trả kết quả"]
~~~

Điểm quan trọng là phải xác minh token trước khi tin iss, jti hoặc các claims khác. Nếu ghi dữ liệu vào kho replay dựa trên một JWT chưa được xác minh, attacker có thể gửi các token giả với jti tùy ý để làm bẩn kho trạng thái hoặc gây từ chối dịch vụ.

## 5. Khóa định danh trong replay store

Không nên chỉ dùng jti trần làm khóa toàn cục nếu hệ thống nhận token từ nhiều issuer hoặc nhiều mục đích.

Một khóa logic có thể được tạo từ:

~~~text
replay-key = namespace(issuer, token-purpose, audience, jti)
~~~

Ví dụ biểu diễn:

~~~text
replay:v1:identity.example.org:password-reset:account-api:reset-7f31b8d9e2
~~~

Các thành phần có ý nghĩa:

| Thành phần | Vì sao cần |
| --- | --- |
| Namespace/version | Tránh xung đột giữa các loại record hoặc phiên bản schema |
| Issuer | Tách namespace jti của các issuer khác nhau |
| Purpose/token type | Tránh nhầm token đặt lại mật khẩu với assertion hoặc proof ở luồng khác |
| Audience/resource | Có thể tách phạm vi tiêu thụ nếu hợp đồng cho phép một jti được dùng ở các resource khác nhau |
| jti | Định danh token cần kiểm soát replay |

Việc chọn các thành phần phải nhất quán với hợp đồng token. Nếu một jti được định nghĩa là duy nhất toàn cục trong phạm vi issuer và chỉ dùng cho một purpose, khóa có thể ngắn hơn. Không đưa claims chưa được xác minh vào khóa có thể gây tác động trạng thái.

Không ghi nguyên token vào replay store chỉ để phát hiện trùng lặp. Thông thường chỉ cần lưu khóa định danh đã xác minh và metadata tối thiểu. Nếu jti không đủ khó đoán hoặc kho có nguy cơ bị đọc, có thể dùng một dạng hash/HMAC của định danh để tạo storage key; điều này không thay thế việc tạo jti đủ mạnh.

## 6. Thao tác tiêu thụ phải nguyên tử

### 6.1. Vấn đề check-then-set

Một cách triển khai sai là:

1. Đọc kho trạng thái để kiểm tra jti chưa tồn tại.
2. Nếu chưa tồn tại, thực hiện một lệnh ghi riêng.

Hai request đồng thời có thể cùng đọc kết quả “chưa tồn tại” trước khi một request kịp ghi. Cả hai đều tiếp tục, dẫn đến cùng một token được chấp nhận hai lần.

~~~mermaid
sequenceDiagram
    participant R1 as Request A
    participant R2 as Request B
    participant S as Replay Store
    R1->>S: GET key → không tồn tại
    R2->>S: GET key → không tồn tại
    R1->>S: SET key
    R2->>S: SET key
    Note over R1,R2: Cả hai request có thể cùng nghĩ mình là lần đầu
~~~

Kiểm tra và ghi nhận phải là một thao tác nguyên tử do kho dữ liệu bảo đảm.

### 6.2. Các cơ chế nguyên tử thường dùng

| Kho trạng thái | Cơ chế |
| --- | --- |
| Redis-compatible store | SET key value NX EX/PX ttl hoặc lệnh/script nguyên tử tương đương |
| SQL database | INSERT vào bảng có unique constraint trên replay key; chỉ một transaction insert thành công |
| Key-value store | Conditional put / put-if-absent |
| Distributed database | Conditional write hoặc compare-and-set có bảo đảm nhất quán phù hợp |

Ví dụ thao tác Redis ở mức khái niệm:

~~~text
SET replay:v1:<issuer>:<purpose>:<jti> consumed NX EX <ttl-seconds>
~~~

- NX: chỉ ghi nếu khóa chưa tồn tại.
- EX: đặt TTL tính bằng giây.
- Nếu lệnh tạo khóa thành công: request thắng quyền tiêu thụ.
- Nếu khóa đã tồn tại: token đã được tiêu thụ, request bị từ chối.

Ví dụ với SQL, có thể dùng một bảng có cột replay key được unique:

~~~sql
CREATE TABLE consumed_jwt (
    replay_key VARCHAR(512) PRIMARY KEY,
    consumed_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);
~~~

Request thực hiện INSERT và dựa vào kết quả unique constraint để quyết định. Không cần đọc trước rồi mới insert. Nếu insert bị duplicate-key, jti đã được tiêu thụ.

### 6.3. Kho trạng thái phải dùng chung giữa các instance

Nếu API chạy trên nhiều instance, mọi instance phải kiểm tra cùng một replay store hoặc một cơ chế đồng bộ có bảo đảm tương đương. Nếu mỗi instance giữ cache cục bộ:

- Request đầu tiên đến instance A được ghi nhận tại A.
- Replay tiếp theo đến instance B không thấy record của A.
- Cùng token có thể được chấp nhận lại.

Không dùng eventual consistency cho thao tác quyết định tiêu thụ một lần nếu độ trễ đồng bộ có thể cho phép hai instance cùng chấp nhận. Cần chọn kho có atomic conditional write và mức nhất quán phù hợp.

## 7. TTL và thời gian lưu record

Replay record chỉ cần tồn tại trong khoảng thời gian token còn có thể được chấp nhận, cộng thêm khoảng clock skew hoặc cửa sổ xử lý được chính sách cho phép.

Ví dụ:

~~~text
token exp       = 12:10:00 UTC
allowed leeway  = 30 seconds
replay record   = giữ ít nhất đến 12:10:30 UTC
~~~

Nếu xóa record trước khi token hết hiệu lực, cùng token có thể được gửi lại sau khi record biến mất. Vì vậy TTL không được ngắn hơn khoảng thời gian verifier có thể chấp nhận token.

### 7.1. Tính TTL

Với token có exp, cách tính khái niệm:

~~~text
record_expiry = exp + allowed_clock_skew
ttl = max(0, record_expiry - current_time)
~~~

Chỉ tạo replay record nếu token còn hợp lệ và TTL dương. Không gia hạn TTL dựa trên thời điểm replay; làm vậy có thể tạo cơ hội giữ record vô thời hạn khi attacker liên tục gửi lại.

Với token có thời hạn riêng theo nghiệp vụ, chẳng hạn link xác minh có hạn 10 phút, record cần được giữ đến hết thời hạn mà verifier có thể chấp nhận link đó. Nếu có nhiều verifier với leeway khác nhau, dùng cửa sổ bảo thủ phù hợp với chính sách chung.

### 7.2. Dọn dẹp record

Kho trạng thái có thể tự hết hạn record bằng TTL hoặc chạy tác vụ dọn dẹp theo expires_at. Việc dọn dẹp chỉ là tối ưu lưu trữ; an toàn phụ thuộc record không bị loại bỏ quá sớm.

Không dùng eviction policy có thể xóa record còn hiệu lực để nhường chỗ cho dữ liệu khác nếu điều đó làm replay được chấp nhận lại. Với dữ liệu chống replay, cần dung lượng, retention và chính sách eviction có chủ đích.

## 8. Xác minh token trước hay tiêu thụ jti trước?

Thứ tự đúng về mặt tin cậy:

1. Parse token với giới hạn kích thước và định dạng.
2. Xác minh thuật toán, chữ ký và khóa tin cậy.
3. Kiểm tra issuer, audience, loại token và các claims thời gian.
4. Kiểm tra jti có mặt, đúng kiểu và phù hợp hợp đồng.
5. Kiểm tra claims ràng buộc giao dịch/purpose nếu có.
6. Thực hiện thao tác consume nguyên tử.
7. Thực hiện hành động nghiệp vụ theo mô hình transaction đã thiết kế.

Không tiêu thụ jti của token chưa xác minh. Ngược lại, cũng không thực hiện side effect nghiệp vụ trước khi consume thành công, nếu mục tiêu là bảo đảm token chỉ được chấp nhận một lần.

### 8.1. Kiểm tra quyền trước hay consume trước?

Thứ tự cụ thể giữa kiểm tra quyền nghiệp vụ và consume phụ thuộc threat model. Có thể thực hiện các kiểm tra không gây side effect trước khi consume, ví dụ xác định tài nguyên, xác minh quyền và kiểm tra trạng thái hiện tại. Chỉ consume khi request đã đủ điều kiện để thực hiện hành động.

Nếu consume trước rồi mới phát hiện request không đủ quyền, token có thể bị mất hiệu lực dù không có hành động nào xảy ra. Nếu thực hiện hành động trước rồi mới consume, hai request đồng thời có thể cùng gây side effect. Cần xác định rõ điểm commit.

## 9. Race condition và hành động nghiệp vụ

Thao tác consume nguyên tử bảo đảm chỉ một request thắng ở bước ghi nhận jti. Nhưng nó chưa tự bảo đảm hành động nghiệp vụ và replay record được commit như một đơn vị.

### 9.1. Rủi ro crash giữa consume và business action

Giả sử:

1. API ghi jti vào replay store thành công.
2. Process bị dừng trước khi cập nhật mật khẩu hoặc xác nhận giao dịch.
3. Client retry cùng token.
4. API thấy jti đã tồn tại và từ chối.

Token đã bị tiêu thụ nhưng hành động nghiệp vụ chưa hoàn thành. Đây có thể là hành vi fail-safe, nhưng gây trải nghiệm lỗi và cần quy trình phục hồi.

### 9.2. Gộp consume và thay đổi nghiệp vụ trong một transaction

Nếu replay record và dữ liệu nghiệp vụ cùng nằm trong một transactional database, có thể thực hiện trong một transaction:

1. Insert replay key với unique constraint.
2. Thực hiện thay đổi nghiệp vụ.
3. Commit cả hai cùng lúc.

Nếu bất kỳ bước nào thất bại và transaction rollback, cả replay record lẫn thay đổi nghiệp vụ đều rollback. Request khác có thể thử lại nếu token vẫn còn hiệu lực.

### 9.3. Khi replay store và business store khác nhau

Nếu replay store và dữ liệu nghiệp vụ nằm ở hai hệ thống không có distributed transaction, không thể giả định hai thao tác commit nguyên tử cùng nhau. Có thể thiết kế state machine bền vững:

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Đã giành quyền xử lý jti, đang thực hiện nghiệp vụ |
| COMPLETED | Nghiệp vụ đã hoàn tất |
| FAILED_RETRYABLE | Thất bại có thể thử lại theo chính sách |
| FAILED_FINAL | Thất bại cuối cùng; token không được dùng lại |

Việc chuyển trạng thái phải có compare-and-set hoặc transaction phù hợp. Với side effect bên ngoài, có thể dùng transactional outbox, durable job hoặc saga để phối hợp. Không xóa record PENDING một cách mù quáng sau timeout vì nghiệp vụ có thể đã hoàn tất nhưng phản hồi bị mất.

## 10. Replay prevention và idempotency không giống nhau

Hai cơ chế thường được dùng cùng nhau nhưng có mục tiêu khác:

| Tiêu chí | Replay prevention | Idempotency |
| --- | --- | --- |
| Mục tiêu | Từ chối việc dùng lại một token/proof đã tiêu thụ | Cho phép retry an toàn mà không lặp side effect |
| Cùng request gửi lại | Thường bị từ chối như replay | Có thể trả lại kết quả đã lưu |
| Định danh | jti, nonce hoặc proof identifier | Idempotency key gắn với thao tác |
| Trạng thái | Đã tiêu thụ hay chưa | Đang xử lý, hoàn tất và kết quả |
| Trường hợp dùng | Link một lần, assertion, proof chống replay | Thanh toán, tạo đơn hàng, retry do timeout |

Ví dụ: client gửi yêu cầu xác nhận thanh toán với one-time JWT. Server tiêu thụ jti và tạo giao dịch. Phản hồi bị mất trên mạng; client gửi lại request.

- Nếu chỉ dùng replay prevention, request thứ hai bị từ chối. Client có thể không biết giao dịch đầu tiên đã hoàn tất hay chưa.
- Nếu kết hợp idempotency key, server có thể nhận ra đây là retry của cùng một thao tác và trả lại kết quả đã lưu mà không thực hiện thanh toán lần thứ hai.

Không nên nới lỏng replay prevention bằng cách chấp nhận lại mọi token trùng jti. Nếu cần retry, hãy thiết kế idempotency và lưu kết quả theo một khóa nghiệp vụ riêng.

## 11. Dùng jti trong DPoP và JWT assertion

### 11.1. DPoP proof

DPoP (RFC 9449) dùng một JWT proof được client tạo cho request. Proof chứa các thông tin như:

- jti: định danh duy nhất của proof.
- htm: HTTP method.
- htu: HTTP URI.
- iat: thời điểm tạo proof.
- ath: hash của access token trong những trường hợp yêu cầu.
- nonce: server-provided nonce nếu resource server/authorization server yêu cầu.

Resource server có thể lưu dấu jti của proof trong cửa sổ hiệu lực để từ chối cùng proof bị gửi lại. Khóa replay nên được ràng buộc với thumbprint của public key (ví dụ jkt) và jti, cùng namespace phù hợp. Không dùng jti của access token làm khóa thay cho jti của từng DPoP proof.

Mỗi request cần proof mới theo quy tắc DPoP. Việc chỉ kiểm tra chữ ký proof mà không lưu/kiểm tra replay identifier sẽ không phát hiện được cùng proof bị phát lại trong cửa sổ chấp nhận.

### 11.2. JWT bearer assertion

RFC 7523 cho phép JWT được sử dụng làm client assertion hoặc authorization grant trong OAuth 2.0. Assertion thường có thời hạn ngắn và audience ràng buộc với token endpoint/authorization server.

Nếu chính sách của AS yêu cầu chống replay assertion, AS có thể yêu cầu jti và lưu các assertion ID đã chấp nhận trong khoảng thời gian assertion còn hiệu lực. Khi nhận lại cùng assertion, AS từ chối. Việc yêu cầu và xử lý jti cần được ghi rõ trong profile/chính sách; không nên giả định mọi JWT assertion đều tự có cơ chế replay prevention.

## 12. Xử lý lỗi và hành vi khi kho trạng thái không sẵn sàng

| Tình huống | Hành vi nên có |
| --- | --- |
| Thiếu jti trong luồng bắt buộc one-time | Từ chối token vì không đáp ứng hợp đồng |
| jti đã có trong replay store | Từ chối như replay |
| Hai request đồng thời cùng jti | Chỉ một request consume thành công |
| Token hết hạn | Từ chối trước khi consume |
| Chữ ký hoặc issuer sai | Từ chối trước khi ghi replay state |
| Replay store timeout/không truy cập được | Không giả định token chưa dùng; fail closed đối với thao tác yêu cầu chống replay |
| Replay store mất record còn hiệu lực | Có nguy cơ replay được chấp nhận; cần retention/backup/consistency phù hợp |
| Business action lỗi sau consume | Phục hồi theo transaction/state machine; không tự xóa record tùy tiện |

Nếu hệ thống không thể truy cập replay store, việc tiếp tục cho phép token có thể làm mất bảo đảm một lần. Với thao tác nhạy cảm, mặc định an toàn là từ chối hoặc tạm hoãn, ghi nhận lỗi vận hành và cho phép retry theo quy trình idempotent khi dịch vụ phục hồi.

## 13. Những giới hạn cần hiểu rõ

### 13.1. jti không ngăn kẻ trộm sử dụng token trước chủ sở hữu

One-time store bảo đảm chỉ lần sử dụng đầu tiên thắng. Nếu attacker đánh cắp token và gửi trước người dùng hợp lệ, attacker có thể trở thành bên tiêu thụ đầu tiên. Vì vậy vẫn cần:

- HTTPS/TLS và bảo vệ token khi lưu/truyền.
- Thời hạn ngắn và audience/purpose hẹp.
- Ràng buộc token với giao dịch hoặc subject cụ thể.
- Sender constraint/proof-of-possession khi phù hợp.
- Cơ chế phát hiện bất thường và quy trình thu hồi.

### 13.2. jti không ràng buộc nội dung request

Một token có jti hợp lệ có thể được trình cùng một request khác nếu profile không ràng buộc token với nội dung request. Với thao tác nhạy cảm, cần ràng buộc thêm dữ liệu như transaction ID, amount, resource ID, HTTP method/URI hoặc hash nội dung theo một giao thức được thiết kế rõ ràng.

### 13.3. Kho trạng thái trở thành một thành phần bảo mật trọng yếu

Replay store phải có:

- Tính nhất quán và thao tác ghi có điều kiện nguyên tử.
- Retention/TTL đúng với cửa sổ chấp nhận token.
- Quyền truy cập hạn chế và giám sát.
- Dung lượng đủ để tránh eviction record còn hiệu lực.
- Khả năng sẵn sàng phù hợp với mức độ quan trọng của giao dịch.
- Cách phục hồi sau lỗi mà không làm mất dấu các token đã tiêu thụ còn hiệu lực.

Nếu store bị xóa sạch hoặc khôi phục từ backup cũ, hệ thống có thể quên các lần tiêu thụ trước đó và chấp nhận replay. Kế hoạch khôi phục phải tính đến tính toàn vẹn của replay state.

## 14. Ví dụ: link đặt lại mật khẩu dùng một lần

Giả sử issuer tạo JWT đặt lại mật khẩu với:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "account-42",
  "aud": "https://api.example.org/password-reset",
  "iat": 1893456000,
  "exp": 1893456600,
  "jti": "pwd-reset-2c9f7a31"
}
~~~

Khi người dùng mở link và gửi mật khẩu mới:

1. API xác minh chữ ký, issuer, audience, thời hạn và loại token.
2. API kiểm tra subject và các điều kiện đặt lại mật khẩu.
3. API tạo replay key từ issuer, purpose và jti.
4. API thực hiện insert-if-absent/conditional write nguyên tử.
5. Nếu đã tồn tại, API từ chối vì link đã được dùng.
6. Nếu insert thành công, API cập nhật mật khẩu và đánh dấu token đã tiêu thụ trong cùng transaction nếu có thể.
7. API kết thúc các phiên/credential liên quan theo chính sách và trả kết quả.

### 14.1. Lần đầu sử dụng

~~~text
JWT valid
replay key absent
atomic consume succeeds
password update commits
result: success
~~~

### 14.2. Gửi lại cùng link

~~~text
JWT signature/time still valid
replay key already exists
atomic consume fails
result: reject as already used
~~~

### 14.3. Hai request đồng thời

Hai request cùng gửi link gần như đồng thời. Kho trạng thái chỉ cho một conditional insert thành công. Request thắng tiếp tục; request còn lại bị từ chối. Nếu cập nhật mật khẩu và replay record cùng transaction, chỉ một lần thay đổi được commit.

## 15. Checklist thiết kế jti + replay store

### Issuer và token contract

- [ ] Token thuộc luồng có ngữ nghĩa dùng một lần rõ ràng.
- [ ] jti được tạo mới cho mỗi token và có entropy/độ duy nhất phù hợp.
- [ ] Token có issuer, audience, purpose/type và thời hạn rõ ràng.
- [ ] jti là claim bắt buộc trong profile nội bộ nếu cơ chế replay phụ thuộc vào nó.
- [ ] Claims ràng buộc giao dịch được định nghĩa nếu token phải gắn với một hành động cụ thể.

### Verifier và replay store

- [ ] Xác minh chữ ký và claims trước khi tin jti.
- [ ] Namespace replay key theo issuer/purpose và phạm vi cần thiết.
- [ ] Consume bằng atomic insert-if-absent/conditional write.
- [ ] Mọi instance dùng cùng replay store nhất quán.
- [ ] TTL ít nhất bằng thời gian token còn được chấp nhận cộng clock skew.
- [ ] Không eviction record còn hiệu lực.
- [ ] Fail closed nếu không thể kiểm tra/ghi replay state cho thao tác nhạy cảm.
- [ ] Không lưu token nguyên văn hoặc ghi token vào log.

### Business action và vận hành

- [ ] Xác định điểm commit giữa consume và business side effect.
- [ ] Dùng transaction khi replay record và nghiệp vụ cùng kho dữ liệu.
- [ ] Nếu khác hệ thống, có state machine/outbox/saga và quy tắc phục hồi.
- [ ] Phân biệt replay rejection với idempotent retry.
- [ ] Có xử lý race condition và nhiều request đồng thời.
- [ ] Có giám sát duplicate jti, lỗi store, TTL và dung lượng.
- [ ] Có kế hoạch phục hồi store mà không quên các token đã tiêu thụ còn hiệu lực.

## 16. Kết luận

jti là định danh của JWT, không phải cơ chế chống phát lại độc lập. Đối với token hoặc proof được thiết kế dùng một lần, verifier cần xác minh token trước, sau đó ghi nhận jti trong kho trạng thái bằng một thao tác nguyên tử như insert-if-absent hoặc conditional write. Record phải được giữ đến khi token chắc chắn không còn được chấp nhận.

Thiết kế còn phải xử lý đồng thời, nhiều instance, lỗi kho dữ liệu, crash giữa consume và business action, cũng như retry hợp lệ. Replay prevention từ chối việc dùng lại credential; idempotency quản lý retry để không lặp side effect. Hai cơ chế có thể phối hợp nhưng không thay thế nhau.

Đặc biệt, không nên đánh dấu jti của access token bearer thông thường là đã dùng sau request đầu tiên nếu token được phép gọi nhiều API. Với access token, jti thường phục vụ nhận diện/thu hồi; với DPoP, jti của từng proof mới là định danh phù hợp để phát hiện proof bị phát lại.

## Tài liệu chuẩn để đọc tiếp

- [RFC 7519 — JSON Web Token (JWT), Section 4.1.7](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.7): registered claim jti.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo ngữ cảnh và giảm nhầm lẫn token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof JWT, jti, nonce và phát hiện replay.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT assertion trong OAuth 2.0.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token và authorization grant.
