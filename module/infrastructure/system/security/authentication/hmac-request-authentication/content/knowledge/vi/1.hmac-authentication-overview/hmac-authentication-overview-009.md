# Giới hạn mô hình HMAC

HMAC (Hash-based Message Authentication Code) là cơ chế tạo mã xác thực thông điệp từ **khóa bí mật dùng chung** và dữ liệu đầu vào. Trong xác thực HTTP request, client và server thống nhất một hợp đồng ký: chọn phương thức HTTP, URI, các header quan trọng và/hoặc body; biến chúng thành một chuỗi byte chuẩn (canonical request); sau đó tính và kiểm tra HMAC. Cơ chế này hữu ích cho giao tiếp giữa những hệ thống được cấp khóa, nhưng chỉ an toàn khi hiểu rõ **nó xác thực điều gì, không xác thực điều gì và phụ thuộc vào những thành phần nào bên ngoài HMAC**.

Bài này đặt HMAC request authentication trong phạm vi thiết kế bảo mật hệ thống: chữ ký, canonicalization, chống replay bằng timestamp/nonce, quản lý khóa và key rotation, hành vi của proxy/gateway, cũng như ranh giới giữa **xác thực** và **phân quyền**.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Diễn giải chính xác tính toàn vẹn và bằng chứng sở hữu shared secret mà một HMAC hợp lệ cung cấp.
2. Chỉ ra giới hạn về bí mật dữ liệu, định danh cá nhân, chống replay, chống chối bỏ và độ sẵn sàng.
3. Nhận diện tình huống một request “ký đúng” nhưng vẫn nguy hiểm vì thiếu trường trong canonical request, sai ranh giới proxy hoặc thiếu kiểm tra quyền.
4. Thiết kế cơ chế timestamp/nonce, phân phối khóa và rotation phù hợp với hệ thống nhiều instance.
5. Lập bộ kiểm thử cho signed request đi qua load balancer, reverse proxy, API gateway và HTTP client khác nhau.
6. Lựa chọn HMAC, mTLS, chữ ký bất đối xứng hoặc cơ chế ủy quyền phù hợp với mô hình đe dọa thực tế.

## 2. Phạm vi bảo đảm của HMAC

Ở mức đơn giản, hai bên cùng biết một secret K, một thông điệp byte M và hàm HMAC:

~~~text
signature = Base64UrlWithoutPadding(HMAC-SHA256(K, M))
M         = UTF-8(canonicalRequest)
~~~

Server tự tính lại chữ ký trên **cùng chuỗi byte** rồi so sánh với chữ ký nhận được. Nếu khóa vẫn bí mật và giao thức không mắc lỗi, chữ ký hợp lệ tạo ra những bảo đảm có điều kiện sau:

| Thuộc tính | HMAC đem lại | Ranh giới cần hiểu |
| --- | --- | --- |
| Toàn vẹn dữ liệu đã ký | Phát hiện thay đổi các byte có trong canonical request | Trường không được đưa vào hợp đồng ký có thể bị sửa mà chữ ký vẫn đúng |
| Xác thực bên sở hữu khóa | Bên tạo chữ ký có quyền truy cập shared secret tương ứng | Không chứng minh chính xác người dùng hay máy nào đã sử dụng khóa |
| Tính mới của request | **Không tự cung cấp** | Cần kiểm tra timestamp, nonce và lưu trạng thái chống replay |
| Bí mật nội dung | **Không cung cấp** | Dữ liệu vẫn đọc được nếu truyền qua kênh không mã hóa; cần TLS |
| Phân quyền | **Không cung cấp** | Server vẫn phải kiểm tra hành động, tài nguyên, tenant và chính sách quyền |
| Chống chối bỏ | **Không cung cấp** | Hai bên đều biết secret nên đều có thể tự tạo một chữ ký hợp lệ |
| Khả dụng, chống DoS | **Không bảo đảm** | Xác minh chữ ký, đọc body và lưu nonce vẫn tiêu tốn tài nguyên |

**Điều kiện cốt lõi:** HMAC bảo vệ tính toàn vẹn của *thông điệp đã được định nghĩa và ký*, không tự bảo vệ toàn bộ ý nghĩa nghiệp vụ của HTTP request.

### 2.1. Ví dụ: chữ ký đúng nhưng nghiệp vụ sai

Một đối tác được cấp khóa để gọi `POST /v1/orders`. Chữ ký hợp lệ có thể xác nhận rằng request dùng khóa của đối tác và các trường trong hợp đồng ký không bị thay đổi. Tuy vậy, nó không trả lời được:

- Đối tác có quyền đặt hàng thay cho `customerId` được gửi trong body hay không?
- Đơn hàng có thuộc đúng tenant gắn với `keyId` hay không?
- Sản phẩm, số tiền, trạng thái giao dịch có hợp lệ theo chính sách hay không?
- Request có bị gửi lại hay đã thực thi trước đó hay không?

Bởi vậy, hệ thống phải kiểm tra chữ ký **trước khi thực hiện tác vụ bảo vệ**, rồi tiếp tục kiểm tra quyền và ràng buộc nghiệp vụ. Không nên suy ra “HMAC hợp lệ” đồng nghĩa “được phép thực hiện mọi hành động”.

## 3. Giới hạn của shared secret: ai thực sự đã ký?

Vì client và server cùng sở hữu secret, mỗi bên đều có khả năng tạo ra chữ ký hợp lệ cho một thông điệp tùy ý.

**Hệ quả quan trọng:**

- Server biết request khớp với **khóa nào**, nhưng không có bằng chứng mật mã để phân biệt một client hợp lệ với người đã đánh cắp khóa.
- Nếu nhiều client dùng chung một khóa, một chữ ký không đủ để xác định client cụ thể. Việc ghi log theo `keyId` chỉ quy trách nhiệm cho *nhóm cùng sở hữu khóa*.
- Nếu hệ thống trung gian được cấp secret, hệ thống đó cũng có thể tạo hoặc ký lại request. Phải tính nó vào ranh giới tin cậy.
- Khác với chữ ký số bằng khóa bất đối xứng, HMAC không tạo ra bằng chứng chống chối bỏ đối với chính phía server, vì server cũng biết secret.

**Ví dụ:** Cả service A và service B cùng dùng `shared-secret-1` để truy cập API thanh toán. Khi xuất hiện một yêu cầu hoàn tiền có HMAC đúng, chỉ từ chữ ký không thể kết luận A hay B là nguồn phát. Nên cấp khóa khác nhau theo từng consumer, môi trường và phạm vi sử dụng; gắn `keyId` với định danh principal được quản lý ở server.

Phân tách khóa giúp truy vết, giới hạn sự cố và thu hồi chọn lọc, nhưng vẫn không ngăn một consumer có khóa hợp lệ tự gửi các yêu cầu có hại nằm trong quyền của mình. Phân quyền, giới hạn tốc độ và kiểm toán vẫn cần thiết.

## 4. Giới hạn lớn nhất thường nằm ở canonical request

HMAC chạy trên byte, còn HTTP được các lớp mạng và framework diễn giải thành phương thức, đường dẫn, query, header và body. Hai bên có thể nhìn thấy **cùng một request ở mức nghiệp vụ** nhưng tạo **chuỗi byte khác nhau**; hoặc nguy hiểm hơn, tạo **cùng canonical string từ hai request có ý nghĩa khác nhau**.

### 4.1. Hợp đồng ký phải tường minh

Hãy coi canonicalization là một phần của protocol và version nó như API. Một hợp đồng minh họa có thể quy định:

| Thành phần | Quy tắc phải quy định rõ |
| --- | --- |
| Phiên bản/khu vực sử dụng | Prefix cố định, ví dụ `HMAC-REQUEST-V1`; có thể ràng buộc thêm tên service hoặc audience |
| HTTP method | Cách viết hoa và cách lấy method khi có proxy |
| Path | Lấy từ request-target nào; có chuẩn hóa `%2F`, dấu `/` cuối, dấu chấm hay không |
| Query | Thứ tự sort theo byte nào; percent-encoding; query trùng tên; query rỗng; dấu `+` và khoảng trắng |
| Header | Danh sách được ký; lowercase tên; xử lý khoảng trắng; header nhiều giá trị/trùng tên; header vắng mặt |
| Body | Hash đúng byte nào; xử lý body rỗng, multipart, nén và streaming; có cho phép gateway biến đổi nội dung không |
| Thời gian/nonce | Đơn vị timestamp; định dạng nonce; phạm vi duy nhất; xử lý header bị lặp |
| Thuật toán và chữ ký | HMAC-SHA256; mã hóa Base64URL, padding, cách so sánh; định dạng tên/giá trị `keyId` |

Cần xử lý những trường hợp như `/a%2Fb` khác `/a/b`, `?role=user&role=admin`, ký tự Unicode hoặc header lặp theo một quy tắc không mơ hồ. Mỗi bên phải dùng cùng quy tắc, **không tùy ý decode rồi encode lại theo cách riêng**.

### 4.2. Ví dụ hợp đồng ký phiên bản 1

Giả sử contract chọn phương thức, path, query đã chuẩn hóa, một số header, timestamp, nonce và SHA-256 của *byte body được server xác minh*. Request minh họa:

~~~http
POST /v1/orders?item=a%2Bb&currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: merchant-17:k2
X-Timestamp: 1710000000
X-Nonce: 52eaa3b04198ed2f72a5cffd76c81928
X-Signature: <Base64URL_HMAC_SHA256>

{"sku":"A+B","qty":1}
~~~

Canonical request, theo *quy tắc minh họa* rằng query được sort theo tên đã percent-encode và body hash bằng SHA-256 chữ thường, là:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders
currency=VND&item=a%2Bb
content-type:application/json
x-key-id:merchant-17:k2
x-timestamp:1710000000
x-nonce:52eaa3b04198ed2f72a5cffd76c81928
body-sha256:<64-hex-chars>
~~~

Dòng cuối phải thay bằng digest thật của dãy byte UTF-8 trong body; `<64-hex-chars>` chỉ là ký hiệu trong ví dụ. Mỗi dấu xuống dòng của canonical string phải được quy định chính xác, chẳng hạn LF (`\n`) và **không thêm LF ở cuối**. Cả hai phía phải thống nhất cách viết query, tên header, thứ tự các dòng và bộ ký tự UTF-8.

**Điều gì không được bảo vệ trong ví dụ?** Header `Host` chưa được ký. Nếu host/authority ảnh hưởng đến tenant hoặc đích định tuyến, hợp đồng phải ràng buộc một audience/authority tin cậy; có thể ký một giá trị service ID ổn định thay cho host bên ngoài vốn bị proxy đổi. Các header như `X-User-Id`, `X-Tenant-Id` hoặc `Idempotency-Key`, nếu server dùng chúng để ra quyết định quan trọng, cũng cần được ràng buộc bằng chữ ký hoặc tái xác định từ principal phía server.

### 4.3. Khi một ký tự làm thay đổi kết quả

Với body JSON:

~~~json
{"sku":"A+B","qty":1}
~~~

Các biểu diễn sau có thể tương đương về mặt dữ liệu JSON nhưng **khác byte**:

~~~json
{"qty":1,"sku":"A+B"}
~~~

Do đó, nếu ký hash của body thô, middleware không được tự đổi thứ tự khóa, loại khoảng trắng hoặc chuyển mã trước khi server tính lại hash. Nếu bài toán bắt buộc ký một JSON được chuẩn hóa, phải chọn một chuẩn canonical JSON được định nghĩa độc lập và triển khai nhất quán; không dùng kết quả `toString()` hoặc serializer mặc định như một “chuẩn” ngầm định.

Trường hợp GET không có body cũng phải có biểu diễn duy nhất: SHA-256 của chuỗi byte rỗng là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

**Nguyên tắc thực hành:** Cái gì ảnh hưởng đến định tuyến, quyền hoặc dữ liệu thực thi thì phải được ràng buộc với principal tin cậy và hợp đồng ký. Khi không thể định nghĩa canonicalization không nhập nhằng giữa tất cả thành phần, nên đơn giản hóa giao thức thay vì thêm các phép “sửa chuỗi” tùy tiện.

## 5. HMAC không tự chống replay

Giả sử một attacker lấy được một signed request hợp lệ. Họ không cần biết secret để **gửi lại nguyên vẹn** request đã bắt được. Chữ ký vẫn hợp lệ vì thông điệp không thay đổi.

Nếu request là `POST /v1/transfers`, gửi lại có thể gây trùng giao dịch. Chỉ dùng HMAC không ngăn được tình huống này.

### 5.1. Timestamp giới hạn khoảng thời gian, không ngăn gửi lặp

Server có thể yêu cầu `X-Timestamp` là Unix time tính bằng giây và áp dụng cửa sổ, ví dụ:

~~~text
abs(serverTimeSeconds - requestTimestampSeconds) <= 300
~~~

Bên ngoài cửa sổ 5 phút, request bị từ chối. Nhưng **nhiều bản sao trong cửa sổ 5 phút vẫn có chữ ký đúng**. Nếu triển khai đa vùng, cần thống nhất đồng hồ, độ trễ mạng và đồng bộ NTP. Timestamp phải là một phần của canonical request, nếu không attacker có thể sửa timestamp mà không làm sai chữ ký.

### 5.2. Nonce cần bộ nhớ và tính nguyên tử

Client tạo `nonce` ngẫu nhiên đủ mạnh, chẳng hạn 128 bit từ bộ sinh số ngẫu nhiên an toàn; mỗi request mới có nonce khác. Server dùng kho nonce dùng chung, hỗ trợ thao tác “đặt nếu chưa tồn tại” **nguyên tử**, khóa theo namespace thích hợp, ví dụ:

~~~text
hmac:v1:<keyId>:<nonce>
~~~

Luồng xử lý khuyến nghị:

1. Kiểm tra hình thức method, đường dẫn, kích thước body, định dạng timestamp/nonce/header; loại request không hợp lệ.
2. Tra cứu `keyId` trong kho khóa đang hiệu lực, kiểm tra trạng thái và phạm vi được phép sử dụng.
3. Kiểm tra timestamp nằm trong cửa sổ được chấp nhận.
4. Tạo lại canonical request từ dữ liệu tại ranh giới xác minh đã chọn.
5. Tính HMAC bằng secret tương ứng và so sánh chữ ký theo cách không phụ thuộc nội dung bí mật.
6. **Chỉ sau khi chữ ký đúng**, thực hiện thao tác ghi nonce nếu chưa tồn tại. Nếu nonce đã có thì từ chối replay.
7. Tạo principal gắn với khóa, kiểm tra phân quyền và chính sách nghiệp vụ trước khi xử lý request.

Đối với cửa sổ ±5 phút, TTL của một nonce phải đủ che phủ **toàn bộ khoảng thời gian timestamp đó còn có thể được chấp nhận**, kể cả trường hợp request được nhận sớm. Có thể chọn ít nhất `2 × 5 phút + biên dự phòng` tính từ lần được chấp nhận đầu tiên, hoặc lưu đến mốc hết hạn được tính từ timestamp. TTL chỉ 5 phút tính từ lần nhận đầu tiên có thể cho phép nonce hết hạn khi timestamp vẫn còn hợp lệ.

**Cẩn thận với tính phân tán:** Bộ nhớ local trên từng instance, cache có eventual consistency hoặc thao tác “check rồi insert” tách rời sẽ khiến hai bản sao đồng thời cùng vượt qua. Nếu store chống replay bị mất hoặc không sẵn sàng, hệ thống cần chính sách **fail closed** cho các thao tác nhạy cảm; không âm thầm chuyển sang chế độ chấp nhận mọi nonce.

### 5.3. Replay khác retry và idempotency

Một HTTP client hoặc gateway có thể tự retry khi timeout. Nếu retry dùng nguyên signed request thì nonce bị trùng và phải bị từ chối; nếu tạo timestamp/nonce/chữ ký mới thì request qua được lớp chống replay nhưng **vẫn có thể lặp thao tác nghiệp vụ**.

Với tạo đơn hàng hoặc thanh toán, nên bổ sung `Idempotency-Key` được ký hoặc ràng buộc với request, cùng kho idempotency kiểm soát kết quả nghiệp vụ. Nonce ngăn **dùng lại đúng thông điệp đã ký**; idempotency ngăn **thực hiện lặp cùng thao tác nghiệp vụ**. Đây là hai yêu cầu khác nhau.

### 5.4. Những trường hợp nonce không giải quyết được

- Client sở hữu secret có thể cố ý tạo *nhiều request mới* với nonce mới và chữ ký hợp lệ.
- Người đánh cắp được secret có thể ký request mới tùy ý.
- Nonce không thể chứng minh dữ liệu nghiệp vụ là hợp lệ hay client có quyền.
- Nếu các service dùng chung secret, cùng tên audience và kho nonce tách rời, request có thể bị phát lại sang service khác nếu canonical request không ràng buộc đúng đích đến.

## 6. HMAC không mã hóa dữ liệu và không thay thế TLS

HMAC bảo đảm phát hiện sửa dữ liệu đã ký; nó **không che nội dung** khỏi người có thể quan sát kết nối. Header chứa mã khách hàng, body chứa thông tin nhạy cảm và chính chữ ký đều có thể bị thu thập trên đường truyền không mã hóa.

Vì vậy, signed HTTP API vẫn cần HTTPS/TLS cho cả chặng truyền và kết nối nội bộ tương ứng. TLS bảo vệ nội dung trên đường truyền và hỗ trợ xác thực endpoint, còn HMAC ràng buộc dữ liệu với một secret và hợp đồng ứng dụng. Chúng giải quyết hai lớp vấn đề khác nhau.

Ngay cả khi dùng TLS, secret và request có thể bị lộ qua debug log, crash dump, tracing, bộ nhớ máy chủ, một proxy terminate TLS hoặc cấu hình secret manager sai. Cần hạn chế log header nhạy cảm, bảo vệ kho secret, phân quyền đọc và chính sách lưu trữ dữ liệu.

## 7. Reverse proxy và API gateway có thể đổi dữ liệu mà server đang xác minh

Trong thực tế, request đi qua load balancer, WAF, API gateway, service mesh hoặc framework trước khi đến code kiểm tra chữ ký.

~~~mermaid
flowchart LR
    A[HTTP client] --> B[Load balancer / TLS termination]
    B --> C[API gateway / WAF]
    C --> D[HMAC verifier]
    D --> E[Authorization]
    E --> F[Business handler]
~~~

Các thành phần trung gian có thể:

- Chuẩn hóa path; decode `%2F` hoặc `%2e`; bỏ dấu `/` cuối; rewrite prefix `/api`.
- Sắp xếp lại query, xử lý tham số trùng, đổi `+` thành khoảng trắng.
- Gộp, bỏ hoặc thêm header; đổi `Host`; thêm `Forwarded` hoặc `X-Forwarded-*`.
- Giải nén request, thay đổi cách truyền bằng `Transfer-Encoding`, hoặc đọc và ghi lại body.
- Retry request hoặc chuyển request sang một region/backend khác.

Nếu client ký request **trước proxy** nhưng server kiểm tra dữ liệu **sau khi proxy đã biến đổi**, chữ ký có thể sai dù client hợp lệ. Ngược lại, nếu server ký/kiểm tra trên một biểu diễn nhưng router hoặc business handler dùng biểu diễn khác, có thể hình thành lỗi **parser differential**: cùng chữ ký nhưng việc định tuyến hoặc xử lý diễn giải khác nhau.

### 7.1. Chọn và cố định ranh giới xác minh

Có hai mô hình phổ biến:

| Vị trí verifier | Cần bảo đảm |
| --- | --- |
| Tại gateway | Gateway xác minh trên request nguyên bản và truyền principal đã xác minh tới backend qua kênh tin cậy; backend không được tin header principal do client tự gửi |
| Tại backend | Hợp đồng ký được thiết kế cho biểu diễn request mà backend thật sự nhận; mọi rewrite trước verifier được xác định và kiểm thử |

Ở cả hai mô hình, không được tùy tiện tin giá trị `X-Forwarded-*` từ Internet. Gateway cần xóa các header định danh do client tự cung cấp trước khi gắn thông tin tin cậy, và kết nối gateway–backend cần được bảo vệ. Nếu ký `authority`, cần xác định rõ authority bên ngoài, hostname nội bộ và service audience.

**Ví dụ lỗi:** Client ký `/payments/%2Frefund` nhưng gateway decode thành `/payments//refund`; backend router gộp hai slash thành một đường dẫn khác. Nếu verifier và router không cùng quan niệm về path, kết quả có thể là từ chối request hợp lệ hoặc xác minh một đường dẫn nhưng thực thi handler khác.

### 7.2. Kiểm thử ở cả hai đầu ranh giới

Không chỉ unit test hàm `Mac`. Cần kiểm thử tích hợp từ HTTP client thật, đi qua đúng gateway/proxy được sử dụng trong môi trường chạy, rồi quan sát canonical request tại điểm verifier và hành động handler cuối cùng. Kiểm thử cả HTTP/1.1, HTTP/2 (khi có sử dụng), path được percent-encode, query trùng, Unicode, header lặp, body nén và các đường đi có retry.

## 8. Key rotation và thu hồi khóa không diễn ra tự động

Chữ ký mạnh không giúp gì nếu secret bị lộ hoặc tồn tại vô thời hạn mà không có cơ chế thu hồi. HMAC phụ thuộc trực tiếp vào vòng đời shared secret.

### 8.1. Phân tách khóa và chọn khóa theo key ID

Mỗi consumer hoặc workload cần có secret đủ ngẫu nhiên, ví dụ 256 bit do CSPRNG sinh ra; tách ít nhất theo môi trường và phạm vi truy cập. Header `X-Key-Id` là **định danh công khai** để server lấy secret tương ứng, không phải secret. Server không nên nhận secret từ request, tự dựng key theo nội dung do client chỉ định, hoặc cho phép client yêu cầu một thuật toán yếu hơn.

Cần lưu secret trong secret manager/KMS thích hợp, cấp quyền đọc tối thiểu, tránh commit vào Git, đóng gói trong source hoặc in ra log. Nếu dùng chung một khóa trên nhiều dịch vụ, sự cố tại một dịch vụ mở rộng khả năng giả mạo sang các dịch vụ còn lại.

### 8.2. Quy trình rotation hai khóa minh họa

1. Tạo secret mới với `keyId = merchant-17:k3`, đồng thời vẫn giữ `merchant-17:k2` hoạt động trong thời gian chuyển tiếp được kiểm soát.
2. Phân phối k3 an toàn cho client; kiểm thử ký/xác minh bằng k3 và kiểm tra mọi instance/region đã nhận cấu hình.
3. Chuyển client sang ký bằng k3. Server xác minh từng request bằng **đúng secret tương ứng với keyId được gửi**, không thử toàn bộ khóa một cách mù quáng.
4. Theo dõi lưu lượng k2, lỗi xác minh và đồng bộ giữa các node. Sau khoảng chuyển tiếp, chuyển k2 sang trạng thái hết hiệu lực rồi thu hồi.
5. Kiểm tra nonce, audit log và cấu hình cache trong quá trình rollout; cập nhật tài liệu/hướng dẫn của consumer.

Khoảng overlap phục vụ chuyển tiếp bình thường, **không dùng để trì hoãn thu hồi khi nghi ngờ khóa cũ bị lộ**. Khi khóa bị xâm phạm, phải thu hồi nhanh, thay khóa và đánh giá các yêu cầu đã được chấp nhận. Với cache khóa, thời gian cache có thể khiến một instance tiếp tục chấp nhận khóa đã thu hồi; cần cơ chế invalidation hoặc TTL kiểm soát được.

### 8.3. Key ID không phải là quyền

Server phải ánh xạ `keyId` tới principal đáng tin cậy và quyền được cấu hình **ở phía server**. Client không được tự chọn tenant hoặc scope bằng cách sửa header ngoài chữ ký. Khi rotation, cả khóa cũ lẫn khóa mới phải ánh xạ tới cùng principal/phạm vi dự kiến, trừ khi có thay đổi quyền được phê duyệt riêng.

## 9. Những giới hạn trong triển khai mật mã

Ngay cả khi chọn HMAC-SHA256, lỗi triển khai vẫn có thể làm hỏng giao thức.

**Phải làm rõ:**

- **Không tự chế MAC:** không thay `HMAC(secret, message)` bằng `SHA256(secret + message)`. Cách nối trực tiếp không có tính chất bảo mật tương đương HMAC và có thể chịu các kiểu tấn công khác.
- **Dùng khóa ngẫu nhiên đủ mạnh:** một mật khẩu dễ đoán không phải secret tốt cho API production. Chuẩn hóa độ dài và phân phối khóa bằng cơ chế an toàn.
- **Khóa thuật toán và phiên bản:** không cho request tự chọn `alg=none`, SHA-1 hay thuật toán tùy ý. Phía server chọn phiên bản giao thức được hỗ trợ.
- **Định dạng chữ ký duy nhất:** xác định Base64URL có padding hay không, độ dài digest và quy tắc xử lý chữ ký lỗi; tránh nhiều biểu diễn cho cùng một chữ ký.
- **So sánh chữ ký an toàn:** sau khi decode và kiểm tra độ dài, so sánh byte kỳ vọng với byte nhận bằng API so sánh thích hợp, chẳng hạn `MessageDigest.isEqual` trong Java, thay vì `String.equals` với các chữ ký bí mật.
- **Không phơi bày lý do chi tiết:** trả phản hồi xác thực thất bại nhất quán ra bên ngoài; ghi metric nội bộ có giới hạn để phát hiện lỗi đồng hồ, key rotation hoặc canonicalization.
- **Giới hạn tài nguyên:** hạn chế kích thước body, số header, thời gian đọc, số nonce đang lưu; hash body theo stream khi cần. Request lớn hoặc cố tình gửi chậm có thể làm kiệt tài nguyên trước khi HMAC được xác minh.

### 9.1. Ví dụ Java: kiểm tra HMAC của canonical bytes

Đoạn mã dưới đây chỉ thực hiện **kiểm tra chữ ký**. Biến `canonicalBytes` phải được xây dựng trước đó theo đúng hợp đồng ký; đoạn mã không tự thực hiện canonicalization, timestamp/nonce, tra cứu khóa hay phân quyền.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSignatureCheck {
    private HmacSignatureCheck() {}

    public static boolean matches(
            byte[] secret,
            byte[] canonicalBytes,
            String signatureBase64Url) throws GeneralSecurityException {

        if (signatureBase64Url == null || signatureBase64Url.isEmpty()) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signatureBase64Url);
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }

        // HMAC-SHA256 có kết quả 32 byte. Chỉ chấp nhận một dạng Base64URL.
        if (supplied.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(signatureBase64Url)) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(canonicalBytes);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Để có digest của body trong Java 17 trở lên:

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

byte[] bodySha256 = MessageDigest.getInstance("SHA-256").digest(rawBody);
String bodyHashHex = HexFormat.of().formatHex(bodySha256);
~~~

`rawBody` phải chứa **đúng dãy byte mà hợp đồng ký định nghĩa**. Nếu servlet filter hoặc middleware đã tiêu thụ body và parser đọc phiên bản khác, cần thiết kế cách buffering/streaming rõ ràng. Đừng tạo canonical bytes từ body đã parse rồi serialize lại nếu hợp đồng đang yêu cầu ký raw bytes.

### 9.2. HMAC verifier còn cần những lớp nào?

~~~text
HTTP request
  -> kiểm tra giới hạn và hình thức/không mơ hồ
  -> đọc keyId; tìm khóa đang hiệu lực và scope
  -> kiểm tra timestamp trong cửa sổ cho phép
  -> canonicalize đúng contract
  -> tính và so sánh HMAC
  -> ghi nonce atomically vào shared store (reject nếu đã tồn tại)
  -> tạo principal đã xác thực
  -> authorize action/resource/tenant
  -> enforce idempotency và ràng buộc nghiệp vụ
  -> thực thi handler
~~~

Thứ tự chính xác có thể điều chỉnh theo kiến trúc, nhưng phải giữ các bất biến: **không tạo principal đáng tin khi chữ ký chưa hợp lệ, không đánh dấu nonce theo request chưa được xác minh, không để replay lọt qua cuộc đua đồng thời, và không thực thi nghiệp vụ trước khi phân quyền**.

## 10. Xác thực khác phân quyền

HMAC request authentication trả lời câu hỏi gần đúng: “Request này có chữ ký khớp với secret được quản lý cho `keyId` không?”. Phân quyền trả lời: “Principal tương ứng với khóa này có được thực hiện **hành động này trên tài nguyên này** vào thời điểm này không?”.

Ví dụ:

~~~http
DELETE /v1/tenants/tenant-B/users/user-9 HTTP/1.1
X-Key-Id: tenant-A-client:k4
X-Timestamp: ...
X-Nonce: ...
X-Signature: ...
~~~

Chữ ký có thể hoàn toàn hợp lệ với khóa của `tenant-A-client:k4`. Nếu server chỉ xác minh chữ ký rồi xóa `user-9` thuộc tenant B, đây là lỗi **broken object-level authorization**, không phải lỗi HMAC.

Cách xử lý là gắn `keyId` với principal và tenant ở server, đối chiếu tenant/resource trong path/body với quyền thực tế, rồi áp dụng kiểm tra quyền ở từng thao tác. Header tự khai `X-Tenant-Id` không phải nguồn sự thật nếu client có thể điều khiển nó. Đôi khi tốt hơn là suy ra tenant từ principal thay vì cho request tự chọn.

Tương tự, HMAC không thay thế chính sách về scope, quota, rate limit, hợp lệ hóa dữ liệu, kiểm tra chống gian lận, giao dịch nguyên tử hay audit trail.

## 11. Rủi ro về vận hành, hiệu năng và tính sẵn sàng

Bảo mật request không chỉ là việc chọn thuật toán.

| Rủi ro vận hành | Hậu quả có thể xảy ra | Biện pháp phù hợp |
| --- | --- | --- |
| Clock drift giữa client/server | Request hợp lệ bị từ chối hoặc cửa sổ replay bị mở rộng | NTP, đồng hồ ổn định, timestamp cùng đơn vị, giám sát sai lệch |
| Nonce store chậm hoặc mất kết nối | Độ trễ, lỗi xác thực; nếu bypass có thể nhận replay | Store có thao tác nguyên tử, TTL, timeout, fail closed cho tác vụ nhạy cảm |
| Body rất lớn hoặc gửi chậm | Chiếm RAM/CPU/kết nối trước lúc xác minh | Giới hạn body/timeouts, hashing theo stream và kiểm soát buffering |
| Khóa bị lộ qua log, CI hoặc client | Attacker tạo request mới hợp lệ | Secret manager, kiểm soát truy cập, audit, rotation và thu hồi |
| Proxy rewrite không đồng nhất | Request hợp lệ lỗi chữ ký hoặc parser differential | Contract canonical rõ ràng, test end-to-end qua gateway |
| Dùng lại khóa ở nhiều tenant/service | Một sự cố lan sang các phạm vi khác | Per-consumer, per-environment, per-audience key |
| Client có khóa hợp lệ nhưng bị lạm dụng | Request độc hại vẫn có chữ ký hợp lệ | Authorization, quota, rate limit, anomaly detection |
| Thay đổi contract không có phiên bản | Client và server ký hai thông điệp khác nhau | Phiên bản hóa protocol và kiểm thử tương thích |

Nên đo riêng các lý do thất bại nội bộ: `unknown_key_id`, `expired_timestamp`, `bad_signature`, `replayed_nonce`, `unauthorized_resource` và lỗi hạ tầng. Tránh gửi chi tiết giúp kẻ tấn công dò khóa hoặc thăm dò canonicalization trong HTTP response.

## 12. Khi nào HMAC không phải lựa chọn phù hợp?

| Bối cảnh | Đánh giá |
| --- | --- |
| Gọi API server-to-server với secret được bảo vệ tốt | HMAC có thể phù hợp nếu canonicalization, replay protection, rotation và authorization đầy đủ |
| Web browser hoặc ứng dụng mobile phân phối cho người dùng cuối | Không thể coi shared secret được nhúng trong client là bí mật dài hạn; nên xem xét cơ chế token/ủy quyền phù hợp |
| Muốn bên thứ ba độc lập xác minh người ký mà không biết private key | HMAC không phù hợp vì verifier cũng biết secret; cân nhắc chữ ký bất đối xứng |
| Muốn xác thực danh tính workload ở tầng kết nối | mTLS có thể phù hợp; vẫn cần kiểm tra quyền ở tầng ứng dụng |
| Muốn chứng minh người dùng đồng ý một giao dịch cụ thể | HMAC giữa hai server không thay thế xác thực người dùng, xác nhận giao dịch hoặc chứng cứ chữ ký số |
| Muốn chống lặp thanh toán, đơn hàng hoặc chuyển tiền | HMAC + nonce vẫn chưa đủ; cần thêm idempotency và nguyên tắc giao dịch nghiệp vụ |

Không có lựa chọn nào mặc nhiên thay thế tất cả các lớp khác. Ví dụ, mTLS xác thực peer của kết nối, nhưng không tự xác minh quyền truy cập từng object. Chữ ký bất đối xứng giải quyết bài toán phân phối private/public key khác HMAC, nhưng cũng không tự cấp quyền hay chống replay nếu protocol không thiết kế.

## 13. Bộ kiểm thử giới hạn nên có

Một bộ kiểm thử đáng tin cậy phải bao gồm cả **trường hợp chấp nhận** và **trường hợp từ chối**, chạy tại đường đi HTTP thật của hệ thống.

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Request chuẩn | Đúng key, timestamp, nonce mới, canonical request hợp lệ | Xác thực thành công; tiếp tục kiểm tra quyền |
| Đổi body sau khi ký | Sửa 1 byte trong JSON body | Từ chối chữ ký |
| Đổi path/query được ký | Thay `/orders/1` thành `/orders/2` hoặc đổi query | Từ chối chữ ký |
| Đổi header không được ký | Thử thay header có ảnh hưởng đến nghiệp vụ | Phát hiện lỗ hổng hợp đồng ký nếu handler bị ảnh hưởng mà chữ ký vẫn đúng |
| Timestamp quá cũ/quá xa tương lai | Dùng thời gian ngoài cửa sổ | Từ chối |
| Replay nguyên request | Gửi hai lần một request đã ký | Lần đầu chấp nhận (nếu đủ quyền), lần sau từ chối |
| Replay đồng thời | Gửi nhiều bản sao vào nhiều node/region | Tối đa một lần vượt qua nonce gate |
| Nonce store lỗi | Ngắt kho nonce tại thời điểm xác minh | Từ chối với chính sách an toàn, không bỏ qua replay protection |
| Sai key ID | Gửi signature của k2 nhưng tự khai k3 | Từ chối |
| Key đã thu hồi | Gửi chữ ký hợp lệ với secret cũ | Từ chối sau thời điểm thu hồi có hiệu lực |
| Case/whitespace/header lặp | Kiểm tra các biến thể theo contract | Cho kết quả duy nhất; từ chối đầu vào mơ hồ |
| Query trùng hoặc percent-encoding | `a=1&a=2`, `%2F`, `+`, Unicode | Client/verifier/router diễn giải thống nhất hoặc từ chối |
| Gateway rewrite, HTTP/2 | Đi qua proxy thật, kiểm tra path/body/header | Hợp đồng ký giữ đúng; handler xử lý request đã xác minh |
| Đúng HMAC nhưng vượt quyền | Key của tenant A truy cập tài nguyên tenant B | Xác thực có thể thành công, **phân quyền phải từ chối** |
| Retry nghiệp vụ | Gửi request mới, nonce mới nhưng cùng `Idempotency-Key` | Không thực thi lặp nghiệp vụ |

Khi có test thất bại, cần xác định lỗi nằm ở tầng nào: canonicalization, crypto, freshness, store đồng bộ, gateway, authorization hay idempotency. Không “chữa” lỗi sai chữ ký bằng cách nới lỏng bỏ kiểm tra một trường nhạy cảm.

## 14. Tình huống phân tích: webhook thanh toán có HMAC

Một nhà cung cấp gửi webhook thông báo thanh toán, mỗi request có `X-Key-Id`, `X-Timestamp`, `X-Nonce` và `X-Signature`. Hệ thống nhận webhook qua API gateway rồi cập nhật trạng thái đơn hàng.

**Thiết kế ban đầu:** Backend chỉ tính HMAC trên body JSON sau khi framework parse, bỏ qua timestamp/nonce; callback có `orderId` và `status` trong body. Người lập trình cho rằng “đã có HMAC thì không cần kiểm tra thêm”.

**Vấn đề có thể xảy ra:**

1. Một webhook hợp lệ bị gửi lại nhiều lần, khiến callback trùng tác động đến nghiệp vụ hoặc ghi nhận doanh thu sai.
2. Gateway deserialize/serialize body, làm thay đổi byte và khiến một client hợp lệ bị từ chối.
3. Nếu `orderId` không được đối chiếu với merchant/tenant gắn `keyId`, một partner có thể tác động tới đơn hàng không thuộc phạm vi của họ.
4. Một shared secret được dùng chung cho nhiều merchant khiến khó khoanh vùng khi khóa bị lộ.

**Thiết kế cải thiện:** Quy định rõ byte body được ký và xác minh tại ranh giới ổn định; ký cả phiên bản, đích service, key ID, timestamp, nonce và body digest; áp dụng cửa sổ thời gian cùng nonce store nguyên tử; tách secret theo merchant; ánh xạ key ID tới merchant server-side; kiểm tra order thuộc merchant; dùng event ID/idempotency để xử lý đúng một lần về mặt nghiệp vụ; test qua gateway và kiểm tra rotation.

Trong tình huống này, HMAC vẫn hữu ích, nhưng nó chỉ là **một mắt xích** trong chuỗi bảo vệ webhook.

## 15. Câu hỏi tự kiểm tra

1. Nếu attacker lấy được một signed request hợp lệ nhưng không biết secret, họ có thể làm gì? **Gợi ý:** Phát lại request nguyên vẹn nếu không có freshness/nonce; không thể tùy ý thay nội dung đã ký mà giữ chữ ký hợp lệ.
2. Vì sao ký body JSON theo chuỗi do serializer sinh ra có thể gây lỗi? **Gợi ý:** Hai biểu diễn tương đương về dữ liệu vẫn khác byte; verifier và client phải có cùng quy tắc chuẩn hóa.
3. Timestamp ±5 phút có đủ chống replay không? **Gợi ý:** Không; các bản sao trong cửa sổ vẫn hợp lệ, cần nonce store nguyên tử và TTL phù hợp.
4. Một key của tenant A tạo chữ ký đúng cho thao tác trên tenant B. Lớp nào phải chặn? **Gợi ý:** Authorization dựa vào principal và quyền được quản lý ở server.
5. Tại sao rotation cần `keyId` và khoảng chuyển tiếp? **Gợi ý:** Để xác định chính xác secret đang dùng, triển khai khóa mới trên nhiều instance và thu hồi khóa cũ có kiểm soát.
6. Khi request đi qua reverse proxy, cần so sánh những gì? **Gợi ý:** Method, path, query, header, byte body, audience, canonical string và handler cuối cùng trước/sau proxy.
7. Có thể dùng secret HMAC nhúng trong JavaScript frontend để xác minh một người dùng duy nhất không? **Gợi ý:** Không thể coi secret công khai tới trình duyệt là bí mật; cần mô hình xác thực/ủy quyền người dùng khác.

## 16. Checklist khi áp dụng vào hệ thống thật

- [ ] Có threat model: attacker có thể quan sát, sửa, phát lại request, chiếm client hoặc chiếm key ở đâu?
- [ ] Hợp đồng ký được version, quy định byte canonical tường minh, gồm các trường có ảnh hưởng đến quyền và thao tác.
- [ ] Dùng HMAC-SHA256, khóa mạnh cấp riêng, quản lý trong secret manager; signature được decode và so sánh an toàn.
- [ ] Timestamp có giới hạn thời gian, nonce ngẫu nhiên đủ mạnh và kho dùng chung với thao tác nguyên tử, TTL đúng.
- [ ] Xử lý retry/idempotency của nghiệp vụ tách khỏi nonce replay protection.
- [ ] Có key ID, principal mapping, rotation, cơ chế thu hồi và quan sát lỗi phù hợp.
- [ ] Đã kiểm thử qua đúng reverse proxy/gateway, cả các biến thể encoding, header và body.
- [ ] Backend kiểm tra authorization theo action/resource/tenant, dù HMAC hợp lệ.
- [ ] TLS, rate limit, giới hạn kích thước, timeout và ghi log an toàn được triển khai.
- [ ] Có kịch bản lỗi nonce store, lỗi đồng hồ và secret compromise, xác định chính sách fail closed.

**Kết luận:** HMAC là công cụ xác minh tính toàn vẹn và bằng chứng sở hữu shared secret cho *các byte được ký*. Độ an toàn của HTTP request authentication phụ thuộc vào định nghĩa canonical request không nhập nhằng, bảo vệ khóa, kiểm soát replay, ranh giới proxy và phân quyền sau xác thực. Một chữ ký hợp lệ không tự chứng minh request còn mới, nội dung bí mật, người dùng cụ thể, quyền truy cập hay tính đúng đắn của giao dịch.
