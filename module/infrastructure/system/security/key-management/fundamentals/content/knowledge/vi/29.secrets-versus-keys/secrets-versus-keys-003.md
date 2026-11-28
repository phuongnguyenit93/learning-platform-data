# API credential

API credential là thông tin xác thực mà một ứng dụng, dịch vụ hoặc workload gửi khi gọi API để chứng minh danh tính hoặc quyền truy cập được cấp. Credential có thể là API key, client secret, access token, khóa dùng để ký request hoặc cặp chứng thư và khóa riêng cho mutual TLS. Mỗi loại có cách phát hành, lưu trữ, kiểm tra và thu hồi khác nhau.

Trong quản lý khóa mật mã, cần phân biệt credential với khóa mật mã. Một API key thường là bí mật có entropy cao, được dùng như mật khẩu của một client. Nó không tự động là khóa AES, khóa RSA hay khóa ký số. Khóa mật mã là đầu vào có cấu trúc cho một thuật toán mật mã và thường có mục đích sử dụng, thuật toán, độ dài, quyền truy cập cùng vòng đời được kiểm soát riêng. Phân biệt đúng hai khái niệm giúp tránh dùng sai vật liệu bí mật và chọn đúng cơ chế bảo vệ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích API credential dùng để xác thực client và liên hệ giữa xác thực với phân quyền.
- Phân biệt API key, client secret, access token, khóa ký HMAC và khóa riêng của chứng thư.
- Chọn cách cấp phát credential theo loại client, thời gian sống và mức độ nhạy cảm.
- Thiết kế nơi lưu trữ, truyền tải, kiểm tra, xoay vòng và thu hồi credential.
- Nhận diện rủi ro khi đưa credential vào mã nguồn, log, URL, ứng dụng phía người dùng hoặc môi trường dùng chung.
- Kết nối việc quản lý API credential với KMS, secret manager, HSM, kiểm soát truy cập và kiểm toán.

## 2. API credential là gì?

API credential là bằng chứng mà bên gọi API trình ra để hệ thống nhận biết client hoặc xác minh rằng client đang nắm giữ một quyền truy cập. Credential thường gắn với một bản ghi quản lý ở phía máy chủ, trong đó có thông tin như chủ sở hữu, ứng dụng, môi trường, phạm vi quyền, thời điểm hết hạn và trạng thái.

Ví dụ, một dịch vụ thanh toán gọi API của nhà cung cấp:

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{"amount": 250000, "currency": "VND"}
~~~

Access token trong header là credential. Máy chủ nhận token, kiểm tra chữ ký hoặc tra cứu trạng thái token, sau đó đánh giá quyền của token đối với thao tác tạo thanh toán. Việc token hợp lệ chỉ cho biết request có bằng chứng xác thực phù hợp; hệ thống vẫn phải kiểm tra token có quyền tạo thanh toán cho đúng tài khoản, tenant và môi trường hay không.

Một credential có thể đại diện cho:

- Một ứng dụng hoặc project gọi API.
- Một workload chạy trong môi trường máy chủ.
- Một client OAuth đã đăng ký.
- Một phiên truy cập có thời hạn và các scope cụ thể.
- Một chủ thể nắm giữ khóa riêng có thể ký request hoặc hoàn tất bắt tay TLS.

Credential không nhất thiết nhận diện một con người. API key của một backend thường nhận diện ứng dụng hoặc workload. Nếu cần xác định người dùng cuối, hệ thống phải có cơ chế danh tính người dùng riêng và liên kết hành động của người dùng với request của dịch vụ.

## 3. Phân biệt secret, API credential và khóa mật mã

Các thuật ngữ này có liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ | Cách quản lý tiêu biểu |
|---|---|---|---|
| Secret | Dữ liệu cần giữ kín vì người có được nó có thể tạo ra quyền truy cập hoặc làm lộ thông tin | Mật khẩu, token, client secret, chuỗi kết nối | Secret manager, mã hóa khi lưu, giới hạn người được đọc, xoay vòng |
| API credential | Bằng chứng được API chấp nhận để nhận diện hoặc xác minh client | API key, access token, client secret | Gắn với client, scope, hạn dùng, trạng thái và chính sách thu hồi |
| Khóa mật mã | Vật liệu đầu vào cho thuật toán mật mã, có mục đích sử dụng xác định | AES key, HMAC key, private key của RSA hoặc EC | KMS/HSM, kiểm soát thao tác mật mã, phiên bản, chu kỳ xoay vòng và hủy |
| Public identifier | Giá trị dùng để tìm bản ghi hoặc nhận diện credential, không cần giữ bí mật | Key ID, client ID, token prefix | Có thể lưu và hiển thị, nhưng không được xem nó là bằng chứng xác thực |

API key thường là một chuỗi ngẫu nhiên bí mật. Trong trường hợp đó, nó là một loại secret và có thể đóng vai trò credential kiểu bearer: ai nắm giữ chuỗi hợp lệ có thể sử dụng quyền được gắn với nó. Tuy nhiên, chuỗi này không trở thành khóa mã hóa chỉ vì tên gọi có từ “key”.

Một khóa HMAC có thể được dùng làm credential khi client chứng minh quyền sở hữu bằng cách ký request. Khi ấy khóa vừa là vật liệu mật mã vừa tham gia cơ chế xác thực. Khóa AES dùng để mã hóa dữ liệu không nên được gửi cho API như một API key. Mỗi khóa cần được giới hạn đúng mục đích sử dụng.

Client ID thường là mã định danh công khai của ứng dụng; client secret là phần bí mật dùng để xác thực client. Hai giá trị thường đi cùng nhau trong OAuth nhưng có vai trò khác nhau. Tương tự, access token thường được xem là bearer credential, trong khi refresh token có khả năng tạo access token mới và do đó cần được bảo vệ với mức độ rất cao.

## 4. Các loại API credential thường gặp

### 4.1. API key tĩnh

API key tĩnh là chuỗi được cấp cho ứng dụng và gửi trong mỗi request. Nhà cung cấp có thể dùng nó để nhận diện project, áp dụng quota, giới hạn API hoặc cấp quyền ở mức dịch vụ.

Ưu điểm của API key là dễ triển khai và dễ kiểm tra. Nhược điểm là credential thường sống lâu, dễ bị sao chép và khó ràng buộc với một phiên hoặc một người dùng. Nếu key bị lộ, người khác có thể sử dụng nó cho đến khi key bị thu hồi hoặc hết hạn.

API key tĩnh phù hợp với tích hợp đơn giản khi nhà cung cấp không hỗ trợ cơ chế danh tính workload tốt hơn. Nên cấp một key riêng cho từng ứng dụng, môi trường và mục đích; giới hạn quyền, quota và nguồn sử dụng nếu nền tảng hỗ trợ.

### 4.2. Client ID và client secret

Trong OAuth 2.0, client ID nhận diện ứng dụng đã đăng ký. Client secret là bí mật mà confidential client dùng để chứng minh danh tính với authorization server. Client secret không phải access token và không nên được gửi đến API tài nguyên thay cho access token.

Với luồng Client Credentials, dịch vụ máy chủ xác thực client bằng phương thức được cấu hình, sau đó nhận access token có thời hạn và scope cụ thể. API tài nguyên kiểm tra access token. Cách này tách credential dài hạn của client khỏi token ngắn hạn được dùng trong request.

Ứng dụng chạy hoàn toàn trong trình duyệt hoặc ứng dụng di động phân phối cho người dùng thường không thể giữ client secret an toàn. Mã và cấu hình của ứng dụng có thể bị người dùng trích xuất. Không nhúng client secret dùng chung vào các ứng dụng public client; hãy dùng luồng OAuth phù hợp với public client, chẳng hạn Authorization Code với PKCE khi phù hợp.

### 4.3. Access token và refresh token

Access token là credential được gửi đến API tài nguyên. Token có thể là chuỗi opaque cần tra cứu tại máy chủ hoặc token có cấu trúc như JWT được xác minh bằng chữ ký và các claim.

Refresh token dùng để xin access token mới mà không yêu cầu người dùng hoặc client thực hiện lại toàn bộ quy trình cấp quyền. Vì refresh token có vòng đời và khả năng tạo quyền truy cập tiếp theo, cần lưu trữ chặt chẽ, giới hạn nơi sử dụng, hỗ trợ thu hồi và cân nhắc refresh token rotation.

Không giả định mọi JWT đều an toàn chỉ vì có chữ ký. Resource server vẫn phải kiểm tra thuật toán được phép, chữ ký, issuer, audience, thời hạn, thời điểm bắt đầu hiệu lực, scope và các điều kiện thu hồi hoặc phiên bản chính sách. Không chấp nhận thuật toán do token tự chọn ngoài danh sách được cấu hình.

### 4.4. Credential ký request bằng HMAC

Một số API yêu cầu client ký nội dung request bằng khóa bí mật dùng chung. Máy chủ tính lại chữ ký và so sánh với chữ ký nhận được. Khóa HMAC trong mô hình này là khóa mật mã đối xứng và đồng thời là thành phần xác thực client.

Chữ ký nên bao phủ các thành phần có ý nghĩa bảo mật như HTTP method, đường dẫn chuẩn hóa, hash của body, timestamp và nonce. Máy chủ kiểm tra timestamp trong cửa sổ cho phép và lưu hoặc phát hiện nonce đã dùng để giảm nguy cơ phát lại request. Hai bên phải thống nhất chính xác cách chuẩn hóa request; khác biệt về encoding, thứ tự tham số hoặc khoảng trắng có thể làm chữ ký không khớp.

### 4.5. Chứng thư client và mutual TLS

Với mutual TLS (mTLS), client trình chứng thư trong quá trình bắt tay TLS và chứng minh quyền sở hữu khóa riêng tương ứng. Máy chủ xác minh chuỗi chứng thư, thời hạn, mục đích sử dụng, danh tính trong chứng thư và chính sách tin cậy.

Khóa riêng cần được bảo vệ trong keystore phù hợp, KMS hoặc HSM tùy mức độ rủi ro. Chứng thư công khai có thể được phân phối để xác minh; khóa riêng không được gửi cho máy chủ. Việc gia hạn hoặc thay chứng thư phải đi cùng kế hoạch triển khai và thu hồi chứng thư cũ.

### 4.6. Public key dành cho ứng dụng phía người dùng

Một số nhà cung cấp gọi một giá trị là publishable key hoặc public API key vì nó được phép xuất hiện trong mã phía trình duyệt. Giá trị này chỉ an toàn để công khai khi nhà cung cấp thiết kế nó như một định danh công khai và giới hạn quyền phù hợp. Nó không được phép cấp quyền truy cập dữ liệu riêng tư hoặc thao tác nhạy cảm chỉ dựa trên việc người gọi biết giá trị đó.

Các giới hạn như domain allowlist, bundle identifier, quota và API allowlist giúp giảm lạm dụng nhưng không biến một bí mật bị nhúng trong ứng dụng thành bí mật an toàn. Mọi thao tác nhạy cảm cần được kiểm soát ở backend.

| Loại credential | Thời gian sống thường gặp | Rủi ro chính | Kiểm soát nên có |
|---|---|---|---|
| API key tĩnh | Dài hạn hoặc đến khi thu hồi | Bị sao chép và dùng lại | Key riêng cho từng client, scope hẹp, quota, hạn dùng, rotation |
| Client secret | Dài hạn hơn access token | Lộ danh tính client | Secret manager, xác thực client phù hợp, rotation |
| Access token | Ngắn hạn | Bị đánh cắp trong thời gian hiệu lực | TLS, scope, audience, expiry, kiểm tra issuer và chữ ký |
| Refresh token | Trung hoặc dài hạn | Có thể tạo access token mới | Lưu trữ bảo vệ, rotation, phát hiện tái sử dụng, thu hồi |
| HMAC signing key | Theo phiên bản khóa | Lộ khóa cho phép giả mạo chữ ký | KMS/HSM, key ID, chống replay, rotation |
| Khóa riêng mTLS | Theo vòng đời chứng thư | Giả mạo client nếu khóa bị lộ | Keystore/HSM, cấp chứng thư, thu hồi và kiểm toán |

Tên gọi và hành vi thực tế phụ thuộc nhà cung cấp. Luôn đọc hợp đồng API và tài liệu xác thực của dịch vụ thay vì suy luận từ tên “API key”, “secret” hoặc “token”.

## 5. Mối đe dọa và lỗi thiết kế phổ biến

Credential là mục tiêu hấp dẫn vì nó có thể biến quyền truy cập của một ứng dụng thành quyền truy cập của kẻ tấn công. Các tình huống thường gặp gồm:

- Commit API key hoặc client secret vào Git, kể cả trong repository riêng. Lịch sử commit, fork, cache và bản sao CI có thể giữ lại giá trị sau khi xóa file.
- Đưa token vào URL query string. URL có thể xuất hiện trong access log, proxy log, browser history, analytics, referer hoặc hệ thống giám sát.
- Ghi toàn bộ Authorization header, cookie hoặc payload nhạy cảm vào log, trace, exception hay ticket hỗ trợ.
- Dùng chung một credential cho nhiều dịch vụ, tenant, môi trường hoặc nhân viên. Khi có sự cố sẽ khó xác định phạm vi và thu hồi mà không làm gián đoạn các bên khác.
- Cấp quyền quản trị cho key chỉ cần đọc một tập dữ liệu. Credential bị lộ sẽ gây thiệt hại lớn hơn mức cần thiết.
- Nhúng secret vào JavaScript, ứng dụng di động, image container hoặc file cấu hình được đóng gói. Người nhận artifact có thể trích xuất giá trị.
- Không đặt hạn dùng, không ghi nhận chủ sở hữu và không biết key nào đang được sử dụng. Credential cũ dễ tồn tại lâu hơn nhu cầu thực tế.
- Chỉ mã hóa database nhưng cho phép quá nhiều dịch vụ giải mã secret. Mã hóa khi lưu không thay thế kiểm soát quyền đọc và sử dụng.
- Xoay vòng key nhưng không kiểm tra các consumer, job nền, bản sao triển khai hoặc cache còn dùng key cũ.
- Coi API key là danh tính người dùng cuối. Một key của backend có thể đại diện cho cả hệ thống, nên không đủ để chứng minh người dùng cụ thể đã thực hiện thao tác.

Mô hình đe dọa cần xem xét cả nơi credential được tạo, truyền, lưu, sử dụng, sao lưu và thu hồi. Kẻ tấn công có thể lấy credential từ máy phát triển, pipeline, artifact, máy chủ, log, trình duyệt hoặc nhà cung cấp bên thứ ba.

## 6. Cấp phát credential an toàn

Credential bí mật nên được tạo bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG). Không dùng timestamp, tên dịch vụ, số thứ tự, UUID tự chế hoặc dữ liệu có thể dự đoán làm secret. Với bearer token do hệ thống tự phát hành, có thể dùng ít nhất 128 bit entropy và thường chọn 256 bit để có biên an toàn rộng. Độ dài thực tế cần phù hợp định dạng và giới hạn của giao thức.

Một định dạng dễ vận hành có thể gồm phần nhận diện công khai và phần bí mật:

~~~text
ak_live_<key-id>.<random-secret>
~~~

Phần prefix giúp xác định môi trường hoặc loại credential; key ID giúp tra cứu bản ghi. Chúng không được dùng làm bằng chứng xác thực. Phần secret phải được sinh ngẫu nhiên, đủ dài và chỉ hiển thị cho người tạo tại thời điểm cấp phát nếu hệ thống không có nhu cầu hiển thị lại.

Mỗi credential nên có metadata tối thiểu:

| Trường | Mục đích |
|---|---|
| Credential ID | Định danh bản ghi, không chứa secret |
| Owner và service | Xác định nhóm chịu trách nhiệm |
| Consumer hoặc client | Xác định ứng dụng được phép sử dụng |
| Environment | Tách development, staging và production |
| Scopes và resource | Giới hạn hành động, dữ liệu và tenant |
| Created at, expires at | Theo dõi vòng đời |
| Status | Active, suspended, revoked hoặc expired |
| Version hoặc key ID | Hỗ trợ nhiều phiên bản trong quá trình rotation |
| Last used at | Phát hiện credential không còn cần thiết |
| Created by và approved by | Truy vết quyết định cấp quyền |

Không đưa giá trị secret vào metadata, tên file, tag, URL hoặc nội dung audit. Chỉ lưu fingerprint hoặc định danh không thể dùng để xác thực khi cần đối chiếu.

Quy trình cấp phát nên xác định chủ sở hữu, mục đích, scope, môi trường, thời hạn và người phê duyệt trước khi phát hành. Credential cho production cần có kiểm soát chặt hơn credential thử nghiệm. Cấp một credential riêng cho từng consumer để có thể giới hạn sự cố và thu hồi độc lập.

## 7. Truyền credential qua mạng

Luôn dùng TLS đã được cấu hình đúng khi truyền credential. TLS bảo vệ dữ liệu trên đường truyền và xác thực máy chủ theo cấu hình chứng thư; nó không bảo vệ credential khỏi log, malware trên endpoint, extension trình duyệt hoặc quyền truy cập trái phép ở đầu cuối.

Đặt credential trong header theo giao thức của nhà cung cấp, ví dụ:

~~~http
Authorization: Bearer <access-token>
~~~

Hoặc một header riêng theo hợp đồng API:

~~~http
X-API-Key: <api-key>
~~~

Không gửi credential trong query string, path, tên host hoặc thông báo lỗi. Không gửi cùng một secret qua nhiều kênh khi không cần thiết. Nếu API hỗ trợ, ưu tiên token ngắn hạn, ràng buộc audience và scope cụ thể.

Ở phía server, proxy và API gateway cần có chính sách che hoặc loại bỏ các header nhạy cảm trước khi ghi log. Cần kiểm tra cả log ứng dụng, access log, distributed trace, APM, crash report và hệ thống analytics; che header ở một tầng không đảm bảo các tầng còn lại đã an toàn.

## 8. Lưu trữ và bảo vệ credential

Cách lưu trữ phụ thuộc việc hệ thống có cần lấy lại secret gốc hay chỉ cần xác minh secret do client gửi.

### 8.1. Credential do hệ thống phát hành và chỉ cần xác minh

Nếu máy chủ chỉ cần so sánh API token do client gửi với token đã cấp, không cần lưu plaintext. Với token ngẫu nhiên có entropy cao, có thể lưu hash mật mã của token. Khi nhận request, máy chủ tính hash của token được gửi và so sánh với giá trị lưu. Có thể dùng HMAC với một khóa pepper được giữ riêng trong KMS để tăng khả năng chống lại việc sử dụng trực tiếp bản sao database.

Một cách tổ chức là lưu key ID, trạng thái, scope và hash/HMAC; khi request đến, dùng key ID để tìm bản ghi, tính giá trị kiểm tra từ secret nhận được rồi so sánh bằng phép so sánh thời gian ổn định. Không ghi token gốc vào database hoặc log.

Với token có entropy thấp hoặc do người dùng tự chọn, hash nhanh như SHA-256 không đủ để chống dò đoán ngoại tuyến. Khi đó cần cơ chế băm mật khẩu phù hợp hoặc thay thế bằng credential ngẫu nhiên có entropy cao. Password hashing chậm không cần thiết cho token ngẫu nhiên đủ mạnh, nhưng phù hợp hơn với bí mật do con người chọn.

### 8.2. Secret bên thứ ba mà hệ thống cần gửi lại

Một dịch vụ tích hợp có thể cần giữ API key của nhà cung cấp để gửi request về sau. Vì hệ thống phải khôi phục secret gốc, hash một chiều không đáp ứng được. Hãy lưu secret trong secret manager hoặc mã hóa bằng envelope encryption với khóa mã hóa được quản lý bởi KMS/HSM.

Envelope encryption thường dùng một data encryption key (DEK) để mã hóa secret, sau đó bảo vệ DEK bằng key encryption key (KEK) do KMS quản lý. Ứng dụng chỉ được phép yêu cầu giải mã khi danh tính workload và chính sách truy cập cho phép. Không đưa KEK hoặc plaintext secret vào repository hay file cấu hình đóng gói.

### 8.3. Biến môi trường và file cấu hình

Biến môi trường có thể là phương thức truyền secret từ nền tảng triển khai đến tiến trình, nhưng bản thân biến môi trường không phải một vault. Giá trị có thể bị lộ qua dump tiến trình, cấu hình chẩn đoán, quyền truy cập máy chủ, script khởi chạy hoặc log nếu vận hành sai.

Ưu tiên workload identity hoặc tích hợp secret manager để workload lấy secret khi chạy. Nếu buộc phải dùng biến môi trường, giới hạn quyền đọc tiến trình và cấu hình triển khai, không in môi trường ra log, không lưu secret vào image và kiểm soát quyền truy cập hệ thống orchestration.

### 8.4. Phân quyền đọc và sử dụng

Tách quyền quản trị metadata khỏi quyền đọc secret. Dịch vụ chỉ cần gọi một API nên được cấp quyền lấy đúng credential đó, trong đúng môi trường và trong thời gian cần thiết. Người phát triển không mặc nhiên cần quyền đọc secret production. Quyền giải mã hoặc sử dụng khóa nên được giới hạn theo danh tính workload, thao tác và resource.

HSM phù hợp khi cần bảo vệ khóa riêng hoặc khóa mật mã có yêu cầu cao và thực hiện thao tác mật mã trong ranh giới phần cứng được kiểm soát. Không phải mọi API key đều cần đưa vào HSM; secret manager kết hợp KMS và IAM có thể phù hợp hơn cho nhiều loại credential ứng dụng.

## 9. Xác minh credential ở phía API

Một quy trình xác minh nên thực hiện các bước sau:

1. Nhận credential từ vị trí được giao thức cho phép và từ chối request thiếu credential khi endpoint yêu cầu xác thực.
2. Phân tích định dạng, lấy key ID hoặc client ID nếu có. Không tin các trường do client gửi nếu chưa được xác minh.
3. Tìm bản ghi credential theo định danh công khai.
4. Xác minh secret, chữ ký hoặc chứng thư bằng cơ chế tương ứng. Với giá trị bí mật, dùng phép so sánh phù hợp để tránh rò rỉ thông tin qua thời gian xử lý.
5. Kiểm tra trạng thái active, thời hạn, issuer, audience, thời điểm bắt đầu hiệu lực và phiên bản chính sách khi áp dụng.
6. Kiểm tra scope, tenant, resource, hành động và các điều kiện ràng buộc khác.
7. Áp dụng rate limit, quota và phát hiện hành vi bất thường.
8. Ghi audit event không chứa credential gốc.

Ví dụ logic kiểm tra API token:

~~~text
record = lookupByKeyId(keyId)
if record does not exist:
    reject

if record.status is not ACTIVE or record.expiresAt <= now:
    reject

candidate = HMAC(serverPepper, presentedSecret)
if not constantTimeEqual(candidate, record.secretMac):
    reject

if requestedAction is not allowed by record.scopes:
    reject

allow request and attach authenticated client identity
~~~

Đoạn mã chỉ mô tả luồng xử lý. Trong triển khai thực tế, cần xử lý an toàn lỗi tra cứu, giới hạn thời gian, cache trạng thái, đồng bộ thu hồi và quản lý phiên bản pepper. Không trả về thông báo cho biết key ID có tồn tại hay secret sai nếu việc phân biệt đó giúp kẻ tấn công dò credential.

Nếu dùng JWT, kiểm tra chữ ký bằng khóa tin cậy và thuật toán nằm trong allowlist của hệ thống. Kiểm tra tối thiểu issuer, audience, expiration và các claim quyền cần thiết. Nếu dùng token opaque, tra cứu trạng thái và quyền tại authorization server hoặc kho dữ liệu được tin cậy. Không mặc định token hợp lệ về cú pháp là token hợp lệ về quyền.

## 10. Tách xác thực và phân quyền

Xác thực trả lời câu hỏi “request đến từ client nào hoặc chủ thể nào?”. Phân quyền trả lời “chủ thể đó được phép làm gì trên resource nào?”. Hai bước phải được thực hiện riêng.

Một API key hợp lệ có thể xác thực project A nhưng project A chỉ được đọc dữ liệu của tenant A. Nếu request yêu cầu xóa dữ liệu, hệ thống phải kiểm tra scope và chính sách cho thao tác xóa. Không suy ra quyền quản trị chỉ từ việc credential được xác thực thành công.

Áp dụng nguyên tắc quyền tối thiểu:

- Chỉ cấp scope cần thiết cho công việc của client.
- Tách quyền đọc, ghi, quản trị và thao tác nhạy cảm.
- Ràng buộc credential với tenant, project, audience hoặc resource phù hợp.
- Tách credential theo môi trường và không dùng credential production trong thử nghiệm.
- Đặt quota và rate limit theo client để hạn chế lạm dụng.
- Ưu tiên danh tính workload và token ngắn hạn thay cho secret tĩnh dài hạn khi nền tảng hỗ trợ.

Nếu một API key dùng chung cho nhiều người dùng cuối, backend cần xác thực người dùng và kiểm tra quyền của người dùng trước khi thực hiện thao tác. Audit log nên ghi nhận cả danh tính người dùng đã xác thực và danh tính workload đã gọi dịch vụ, nếu cả hai có liên quan.

## 11. Xoay vòng credential

Rotation thay thế credential đang sử dụng bằng credential mới theo lịch hoặc theo sự kiện. Mục tiêu là giảm thời gian một secret bị lộ có thể được sử dụng và hỗ trợ thay khóa khi có thay đổi nhân sự, nhà cung cấp hoặc chính sách.

Một quy trình rotation ít gián đoạn thường gồm:

1. Xác định owner, consumer, scope, môi trường và tất cả nơi đang sử dụng credential cũ.
2. Tạo credential mới với quyền tương đương hoặc hẹp hơn, thời hạn và metadata rõ ràng.
3. Lưu credential mới vào secret manager và cấp quyền đọc cho đúng workload.
4. Triển khai consumer để đọc phiên bản mới. Nếu API hỗ trợ hai credential đồng thời, giữ credential cũ hoạt động trong một khoảng chuyển tiếp có giới hạn.
5. Xác minh request mới dùng credential mới qua metric hoặc audit event đã che secret.
6. Thu hồi credential cũ sau khi xác nhận consumer đã chuyển đổi.
7. Kiểm tra job nền, worker, bản triển khai cũ, cache và tác vụ khôi phục có còn tham chiếu credential cũ hay không.
8. Ghi lại thời điểm, người thực hiện, phiên bản mới và kết quả kiểm tra.

Không nên để khoảng chuyển tiếp kéo dài vô thời hạn. Nếu nhà cung cấp chỉ cho phép một key hoạt động, cần phối hợp lịch triển khai và thời điểm thay key để tránh gián đoạn. Với HMAC key hoặc khóa ký, dùng key ID để máy chủ có thể xác minh chữ ký bằng phiên bản hiện hành và phiên bản chuyển tiếp trong một khoảng thời gian đã định.

Tần suất rotation phụ thuộc loại credential, thời hạn, mức độ rủi ro, khả năng tự động hóa và yêu cầu của nhà cung cấp. Rotation thường xuyên nhưng triển khai lỗi có thể gây sự cố; cần có quan sát, kế hoạch rollback và quy trình thu hồi rõ ràng.

## 12. Thu hồi và xử lý khi credential bị lộ

Thu hồi vô hiệu hóa credential trước thời hạn dự kiến. Các lý do thường gặp gồm nhân viên hoặc nhà cung cấp kết thúc quyền truy cập, ứng dụng ngừng hoạt động, credential không còn owner, nghi ngờ bị lộ hoặc phát hiện hành vi bất thường.

Khi nghi ngờ credential bị lộ:

1. Xác định credential, owner, consumer, scope và tài nguyên có thể bị truy cập.
2. Thu hồi hoặc tạm khóa credential theo mức độ khẩn cấp. Không chờ hoàn tất điều tra nếu nguy cơ đang diễn ra.
3. Cấp credential thay thế qua kênh được kiểm soát và cập nhật consumer hợp lệ.
4. Kiểm tra log, audit event, quota, địa chỉ nguồn và hành động được thực hiện trong khoảng thời gian có nguy cơ.
5. Xác định nguồn rò rỉ: repository, pipeline, log, máy trạm, artifact, secret manager hoặc bên thứ ba.
6. Xóa hoặc hạn chế bản sao bị lộ ở những nơi có thể kiểm soát; nhớ rằng xóa file không xóa lịch sử Git hoặc bản sao đã tải xuống.
7. Đánh giá dữ liệu và tài nguyên bị truy cập, thực hiện biện pháp khắc phục và thông báo theo quy trình sự cố của tổ chức.
8. Ghi nhận nguyên nhân, thời gian phát hiện, thời gian thu hồi và bằng chứng xử lý.

Thu hồi cần có hiệu lực trên các lớp cache và replica. Với JWT tự chứa, resource server có thể tiếp tục chấp nhận token cho đến khi token hết hạn nếu không có cơ chế kiểm tra thu hồi hoặc denylist. Có thể giảm rủi ro bằng access token ngắn hạn, kiểm tra phiên bản hoặc trạng thái khi cần, và giới hạn audience. Với token opaque, trạng thái thu hồi thường được kiểm tra tại máy chủ hoặc introspection endpoint.

Không đưa secret bị lộ vào báo cáo sự cố, ticket hoặc kênh trao đổi để minh họa. Dùng credential ID, fingerprint đã được kiểm soát hoặc giá trị đã che.

## 13. Log, giám sát và kiểm toán

Audit log cần cho biết ai đã cấp, phê duyệt, đọc, sử dụng, xoay vòng, vô hiệu hóa hoặc thu hồi credential; hành động diễn ra khi nào, từ workload nào và theo yêu cầu nào. Log phải hỗ trợ điều tra mà không làm lộ chính credential.

Các trường hữu ích có thể gồm:

- Credential ID hoặc key ID không bí mật.
- Client, owner, service và environment.
- Hành động được thực hiện và kết quả.
- Thời điểm, request ID và nguồn gọi ở mức phù hợp.
- Scope hoặc policy version có liên quan.
- Người hoặc workload thực hiện thay đổi.

Không ghi plaintext token, client secret, private key, Authorization header hoặc request body nhạy cảm. Nếu cần liên kết sự kiện theo credential, dùng ID ổn định hoặc fingerprint được thiết kế để không thể dùng làm credential.

Theo dõi các tín hiệu như key không dùng trong thời gian dài, request tăng đột biến, lỗi xác thực bất thường, sử dụng từ môi trường hoặc vùng không mong đợi, hành động ngoài scope và việc sử dụng credential sau thời điểm dự kiến thu hồi. Cảnh báo cần gắn với owner để có thể xử lý.

Kiểm toán định kỳ danh sách credential để tìm secret không có owner, credential không có hạn dùng, scope quá rộng, key trùng giữa môi trường, key cũ không còn sử dụng và tài khoản có quyền đọc secret vượt nhu cầu.

## 14. Tích hợp với KMS, secret manager và HSM

Các hệ thống này giải quyết những phần khác nhau của bài toán:

| Thành phần | Vai trò trong quản lý API credential |
|---|---|
| Secret manager | Lưu, phân phối, kiểm soát quyền đọc và theo dõi vòng đời của API key, client secret hoặc token cần khôi phục |
| KMS | Quản lý khóa dùng để mã hóa secret, tạo HMAC, ký hoặc giải mã theo chính sách |
| HSM | Bảo vệ khóa mật mã nhạy cảm và thực hiện thao tác mật mã trong ranh giới phần cứng được kiểm soát |
| IAM/workload identity | Xác định workload nào được phép lấy secret hoặc gọi thao tác KMS |
| API gateway | Xác thực request, áp dụng quota, rate limit, policy và che dữ liệu nhạy cảm trong log |
| Audit platform | Thu thập sự kiện quản trị và sử dụng để điều tra, cảnh báo và kiểm toán |

Không phải mọi credential cần được mã hóa trực tiếp bằng KMS hoặc lưu trong HSM. Một API token ngẫu nhiên chỉ cần xác minh thường có thể lưu hash/HMAC; secret bên thứ ba cần gửi lại thường cần secret manager hoặc mã hóa có quản lý khóa. Khóa HMAC, khóa ký và khóa riêng có yêu cầu mật mã cần được quản lý theo chính sách khóa tương ứng.

Một mô hình tham khảo:

~~~mermaid
flowchart TD
    A[Client hoặc workload] -->|Credential qua TLS| B[API Gateway]
    B --> C[Xác minh credential]
    C --> D[Kiểm tra trạng thái và scope]
    D --> E[API service]
    C --> F[Credential metadata]
    C --> G[KMS hoặc secret manager]
    F --> H[Audit và monitoring]
    G --> H
    E --> H
~~~

Trong mô hình này, gateway hoặc service xác minh credential dựa trên metadata và cơ chế mật mã phù hợp. Secret manager cung cấp secret cho workload đã được cấp quyền; KMS thực hiện thao tác mã hóa hoặc HMAC khi được yêu cầu. Audit ghi nhận sự kiện mà không thu thập giá trị secret.

## 15. Ví dụ thiết kế API token cho một dịch vụ nội bộ

Giả sử dịch vụ Inventory cung cấp API cho dịch vụ Order. Hai dịch vụ chạy trong cùng tổ chức nhưng có vòng đời triển khai độc lập.

Một thiết kế hợp lý có thể thực hiện như sau:

1. Đăng ký Order như một workload client riêng trong môi trường production.
2. Cấp token ngẫu nhiên có entropy cao, gắn với client ID, owner, scope chỉ đọc và cập nhật tồn kho cần thiết, cùng thời hạn cụ thể.
3. Chỉ hiển thị token một lần khi cấp. Ghi key ID và metadata vào kho quản lý; lưu HMAC của secret để xác minh.
4. Đưa token vào secret manager và cấp quyền đọc cho workload Order thông qua workload identity.
5. Order gửi token trong Authorization header qua TLS khi gọi Inventory.
6. Inventory tìm bản ghi theo key ID, xác minh secret, trạng thái và thời hạn, sau đó kiểm tra scope và tenant của request.
7. Gateway giới hạn tốc độ và ghi audit event với client ID, credential ID, request ID và kết quả, không ghi token.
8. Theo dõi lần sử dụng cuối và cảnh báo khi token được dùng ngoài hành vi dự kiến.
9. Khi rotation, cấp token mới, cập nhật Order, xác nhận request đã chuyển sang token mới rồi thu hồi token cũ.

Nếu nền tảng hỗ trợ workload identity và cấp token ngắn hạn tự động, nên cân nhắc phương án đó để giảm số lượng secret tĩnh. Nếu cần dùng token tĩnh, việc tách credential theo client và môi trường giúp giới hạn phạm vi khi một token bị lộ.

## 16. Những quyết định cần ghi rõ trong thiết kế

Trước khi đưa API credential vào production, thiết kế cần trả lời được:

- Credential xác thực ứng dụng, workload hay người dùng cuối?
- Loại credential nào phù hợp với giao thức và khả năng của nhà cung cấp?
- Credential có phải secret hay chỉ là public identifier?
- Secret được sinh ở đâu, có bao nhiêu entropy và được hiển thị cho ai?
- Hệ thống có cần khôi phục secret gốc hay chỉ cần xác minh?
- Secret được truyền qua TLS và header nào? Những tầng nào phải che log?
- Workload nào được đọc hoặc sử dụng credential? Quyền được giới hạn theo môi trường, scope và resource ra sao?
- Credential hết hạn khi nào, rotation theo lịch hay theo sự kiện, và có thể duy trì hai phiên bản trong lúc chuyển đổi không?
- Thu hồi có hiệu lực nhanh đến đâu trên cache, replica, gateway và resource server?
- Ai chịu trách nhiệm xử lý credential không còn owner hoặc có dấu hiệu bị lộ?
- Audit log có đủ thông tin điều tra mà không chứa secret hay không?

## 17. Checklist vận hành

- [ ] Mỗi credential có owner, consumer, mục đích và môi trường rõ ràng.
- [ ] Secret được tạo bằng CSPRNG và có entropy phù hợp.
- [ ] Mỗi client và môi trường có credential riêng.
- [ ] Scope, quota, audience và resource được giới hạn theo nhu cầu.
- [ ] Credential không xuất hiện trong source code, Git history, image, URL hoặc log.
- [ ] Secret được lưu trong secret manager hoặc được mã hóa bằng khóa do KMS quản lý.
- [ ] Quyền đọc secret và quyền sử dụng khóa được cấp cho workload cần thiết.
- [ ] API xác minh trạng thái, thời hạn, chữ ký hoặc secret và quyền của request.
- [ ] Có quy trình rotation với thời gian chuyển tiếp hữu hạn.
- [ ] Có thể thu hồi credential và kiểm tra hiệu lực thu hồi trên các lớp cache.
- [ ] Có audit event cho cấp phát, truy cập, rotation và thu hồi.
- [ ] Có quy trình phản ứng khi credential bị lộ và kiểm tra credential không còn sử dụng.

## Kết luận

API credential là một phần của cơ chế nhận diện và kiểm soát truy cập API. API key, client secret, access token, khóa HMAC và khóa riêng mTLS có thể cùng xuất hiện trong một hệ thống nhưng có vai trò và yêu cầu bảo vệ khác nhau. Thiết kế an toàn cần chọn đúng loại credential, tạo giá trị khó đoán, giới hạn quyền, truyền qua TLS, lưu trữ theo nhu cầu xác minh hoặc khôi phục, đồng thời hỗ trợ rotation, thu hồi và kiểm toán. Khi credential dựa trên khóa mật mã, cần quản lý khóa bằng KMS hoặc HSM theo đúng mục đích sử dụng; khi credential là secret ứng dụng, cần kiểm soát nó qua secret manager và danh tính workload.
