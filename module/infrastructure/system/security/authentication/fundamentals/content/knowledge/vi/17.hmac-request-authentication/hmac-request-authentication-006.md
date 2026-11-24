# Replay prevention — Ngăn phát lại yêu cầu đã ký bằng HMAC

> **Chương:** HMAC request authentication  
> **Chủ đề:** Replay prevention  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào chống phát lại trong xác thực HTTP request bằng HMAC, ranh giới tin cậy giữa client và verifier, timestamp, nonce, canonical request, cache trạng thái và xử lý retry an toàn.

## 1. Replay attack là gì?

**Replay attack (tấn công phát lại)** xảy ra khi kẻ tấn công thu thập một thông điệp hoặc yêu cầu hợp lệ rồi gửi lại thông điệp đó để lặp lại hành động, sử dụng lại quyền truy cập hoặc làm hệ thống hiểu nhầm đó là một yêu cầu mới. Kẻ tấn công không nhất thiết phải biết bí mật dùng để tạo thông điệp; chỉ cần sao chép được một thông điệp đã được chấp nhận và gửi lại trong điều kiện verifier vẫn chấp nhận nó.

Ví dụ, một dịch vụ nội bộ dùng HMAC để xác thực request. Client gửi yêu cầu chuyển 500.000 đồng, kèm chữ ký HMAC hợp lệ. Attacker quan sát được request trên một máy bị xâm nhập hoặc log bị lộ, rồi gửi lại nguyên request. Nếu server chỉ kiểm tra chữ ký mà không kiểm tra thời gian, nonce hoặc trạng thái đã sử dụng, request thứ hai có thể thực hiện giao dịch lần nữa.

**HMAC chứng minh tính toàn vẹn và quyền kiểm soát khóa bí mật dùng chung**, nhưng bản thân chữ ký HMAC không nói rằng thông điệp chỉ được sử dụng một lần. Cùng một thông điệp, cùng một khóa và cùng một nội dung luôn tạo ra cùng một MAC. Vì vậy, verifier cần thêm dữ liệu chống replay và trạng thái để phân biệt request mới với request đã được chấp nhận.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao chữ ký HMAC hợp lệ vẫn có thể bị phát lại.
2. Phân biệt timestamp, nonce, request ID và idempotency key.
3. Thiết kế canonical request để chữ ký ràng buộc đúng method, authority, path, query, body và ngữ cảnh.
4. Xác minh HMAC, kiểm tra timestamp và tiêu thụ nonce theo thứ tự an toàn.
5. Xây dựng replay cache có thao tác nguyên tử và nhất quán trên nhiều instance/region.
6. Phân biệt chống replay với xử lý retry hợp lệ và chống thực hiện giao dịch trùng lặp.
7. Đánh giá key rotation, clock skew, proxy, tenant scope và các tình huống lỗi vận hành.

## 2. HMAC xác thực điều gì và không xác thực điều gì?

**HMAC (Keyed-Hash Message Authentication Code)** là cơ chế tạo mã xác thực thông điệp dựa trên hàm băm mật mã và khóa bí mật dùng chung. Với HMAC-SHA-256, client và server dùng cùng một secret để tính và kiểm tra MAC.

~~~text
Client:
  canonicalRequest = canonicalize(request, timestamp, nonce)
  mac = HMAC-SHA-256(sharedSecret, canonicalRequest)

Server:
  expectedMac = HMAC-SHA-256(sharedSecret, canonicalRequest)
  accept only if expectedMac matches supplied MAC
~~~

HMAC có thể giúp verifier kiểm tra:

- Request được tạo bởi bên có quyền kiểm soát khóa bí mật tương ứng, theo giả định khóa chưa bị lộ.
- Các thành phần request đã được ký không bị thay đổi sau khi ký.
- Một request có thể được ràng buộc với một client/key ID và một dịch vụ nhận cụ thể.

HMAC **không tự cung cấp**:

- **Chống replay:** cùng request đã ký có thể được gửi lại.
- **Mã hóa:** nội dung request vẫn có thể đọc nếu không có TLS hoặc cơ chế bảo mật khác.
- **Non-repudiation:** cả client và server đều biết secret nên cả hai có thể tạo MAC; bên thứ ba không thể chỉ dựa vào MAC để chứng minh ai đã tạo.
- **Xác thực người dùng cuối:** một key của service thường xác thực workload/client, không chứng minh người đang ngồi trước trình duyệt là ai.
- **Authorization:** key hợp lệ không có nghĩa client được phép thực hiện mọi hành động.
- **Bảo vệ khi secret bị lộ:** attacker có secret có thể ký request mới với timestamp và nonce mới.

Do đó, HMAC request authentication thường phù hợp cho một số tích hợp server-to-server, thiết bị hoặc workload có thể bảo vệ secret. Không nên nhúng một shared secret dùng chung vào mã JavaScript tải về trình duyệt hoặc ứng dụng mobile phân phối rộng rồi coi nó là bí mật; người dùng hoặc malware có thể trích xuất secret. Với xác thực người dùng cuối, cân nhắc OIDC/OAuth, passkey/WebAuthn hoặc giao thức phù hợp.

## 3. Replay có thể xảy ra ngay cả khi TLS và HMAC đều hợp lệ

TLS bảo vệ kết nối và HMAC xác thực request theo khóa; hai cơ chế giải quyết các vấn đề khác nhau.

- TLS giúp bảo vệ dữ liệu trên đường truyền, xác thực server và có thể xác thực client tùy cấu hình.
- HMAC cho phép ứng dụng xác minh nội dung request theo khóa và policy riêng.
- Replay prevention ngăn một request hợp lệ đã được chấp nhận bị sử dụng lại như một giao dịch mới.

Replay có thể xảy ra khi:

- Endpoint nhận cùng một request hai lần do retry hoặc attacker gửi lại.
- Log, tracing, proxy, thiết bị đầu cuối hoặc hệ thống giám sát làm lộ một request đã ký.
- Request được chuyển tiếp qua một dịch vụ trung gian có quyền gửi lại.
- Một API chấp nhận cùng chữ ký trong một khoảng thời gian dài.
- Nhiều server độc lập không chia sẻ trạng thái nonce, khiến mỗi server coi cùng request là lần đầu.
- Một request ký cho dịch vụ/tenant này lại được gửi tới dịch vụ/tenant khác do canonical request không ràng buộc đích.

**Ví dụ:** chữ ký HMAC của request tạo hóa đơn không bị sửa. Attacker gửi lại request y hệt sau 3 giây. Nếu verifier chỉ kiểm tra HMAC và timestamp nằm trong cửa sổ 5 phút, request thứ hai vẫn có chữ ký đúng và timestamp vẫn hợp lệ. Timestamp đơn lẻ giới hạn thời gian replay nhưng không ngăn replay bên trong cửa sổ đó.

## 4. Ba thành phần thường dùng: timestamp, nonce và chữ ký

Một thiết kế phổ biến kết hợp:

- **Timestamp:** thời điểm client tạo request, thường là Unix time theo giây hoặc mili giây. Server chỉ chấp nhận request trong một cửa sổ thời gian cho phép.
- **Nonce (number used once):** giá trị ngẫu nhiên mới cho mỗi request được ký. Server ghi nhận nonce đã dùng để từ chối request lặp.
- **HMAC:** chữ ký bao phủ timestamp, nonce và nội dung/ngữ cảnh request, để attacker không thể thay các trường chống replay mà vẫn giữ chữ ký hợp lệ.

Ví dụ header:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.internal.example
X-Key-Id: workload-42-key-3
X-Signature-Version: 1
X-Timestamp: 1795320000
X-Nonce: 7G4fJp9zW1rQm2xK8vN6aA
X-Content-SHA256: <base64url-body-digest>
Authorization: HMAC-SHA256 <base64url-mac>
Content-Type: application/json
~~~

Các tên header ở đây là **quy ước minh họa**, không phải chuẩn HTTP bắt buộc. Điều quan trọng là cả client và server phải thống nhất format, canonicalization, đơn vị thời gian, encoding và phạm vi dữ liệu được ký.

### Vai trò của từng thành phần

| Thành phần | Mục đích | Nếu thiếu |
| --- | --- | --- |
| HMAC | Xác minh tính toàn vẹn và bên sở hữu secret | Attacker có thể sửa timestamp/nonce/body nếu chỉ có metadata. |
| Timestamp | Giới hạn thời gian request có thể được chấp nhận | Nonce bị lộ có thể bị thử lại sau thời gian dài nếu cache bị xóa hoặc thiếu TTL hợp lý. |
| Nonce | Phân biệt từng lần tạo request và ngăn dùng lại trong cửa sổ | Request y hệt có thể được replay nhiều lần khi timestamp vẫn còn hợp lệ. |
| Body digest | Ràng buộc nội dung body với chữ ký | Body có thể bị thay nếu không được ký trực tiếp hoặc gián tiếp. |
| Method/authority/path/query | Ràng buộc đích và hành động HTTP | Chữ ký có thể bị chuyển sang endpoint hoặc dịch vụ khác. |
| Replay store | Ghi nhận nonce đã được chấp nhận | Nhiều request đồng thời hoặc nhiều instance có thể cùng chấp nhận một nonce. |

Timestamp và nonce không phải bí mật. Chúng chỉ hữu ích khi được ký bằng HMAC và được verifier kiểm tra theo đúng trạng thái.

## 5. Timestamp: giới hạn cửa sổ chấp nhận

Server thường chấp nhận request khi timestamp đủ gần thời gian hiện tại:

~~~text
abs(serverNow - requestTimestamp) <= allowedClockSkew
~~~

Ví dụ, policy cho phép lệch tối đa 300 giây (5 phút). Đây là giá trị minh họa; hệ thống cần chọn cửa sổ theo độ chính xác đồng hồ, độ trễ mạng, khả năng retry và mức rủi ro. Cửa sổ càng rộng, thời gian attacker có thể thử phát lại càng dài nếu thiếu nonce cache.

### Vì sao timestamp không đủ?

Giả sử request được tạo lúc 10:00:00, server chấp nhận timestamp trong ±5 phút. Request hợp lệ đầu tiên tới lúc 10:00:02. Attacker gửi lại nguyên request lúc 10:00:20. Timestamp vẫn nằm trong cửa sổ, HMAC vẫn đúng. Nếu server không nhớ nonce đã được dùng, replay thành công.

### Đồng bộ đồng hồ

Timestamp-based protocol phụ thuộc đồng hồ client và server:

- Server cần đồng bộ đồng hồ bằng nguồn thời gian đáng tin cậy và giám sát clock drift.
- Client phải xử lý clock skew; không nên tự sửa timestamp do server trả về mà không có quy tắc.
- Chọn đơn vị rõ ràng (seconds hay milliseconds), định dạng số nguyên và từ chối chuỗi mơ hồ.
- Giới hạn giá trị tương lai/quá khứ, tránh overflow hoặc parse không chặt.
- Ghi nhận chênh lệch thời gian để phát hiện lỗi cấu hình hoặc client bất thường.

Nếu timestamp quá cũ hoặc nằm quá xa trong tương lai, từ chối trước khi thực hiện nghiệp vụ. Không tự động mở rộng cửa sổ chỉ để làm request cũ chạy lại.

## 6. Nonce: giá trị dùng một lần

**Nonce** là giá trị được tạo mới cho mỗi request được ký. Một nonce tốt cần:

- Được sinh bằng CSPRNG (cryptographically secure pseudorandom number generator).
- Có entropy đủ cao; 128 bit ngẫu nhiên là một mức thường dùng cho ví dụ triển khai.
- Không được tái sử dụng trong phạm vi key/client mà server dùng để kiểm tra trùng.
- Có encoding rõ ràng, chẳng hạn Base64URL không padding hoặc hex.
- Được đưa vào canonical request để HMAC bảo vệ.
- Được server ghi nhận nguyên tử sau khi xác minh chữ ký.

Ví dụ client:

~~~java
byte[] nonceBytes = new byte[16]; // 128 bit
secureRandom.nextBytes(nonceBytes);

String nonce = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(nonceBytes);
~~~

Nonce không cần bí mật sau khi request được gửi; mục đích là tạo tính duy nhất và liên kết chữ ký với một lần gửi. Không dùng timestamp làm nonce vì nhiều request có thể được tạo trong cùng một giây. Không dùng request counter đơn giản nếu nhiều process/client có thể đồng thời tạo request hoặc trạng thái counter có thể bị rollback.

### Nonce scope

Nonce phải được kiểm tra trong phạm vi khóa/client thích hợp. Nếu key ID xác định duy nhất một client credential, replay cache key có thể là:

~~~text
replay:v1:<key-id>:<nonce>
~~~

Nếu key ID chỉ duy nhất trong một tenant hoặc một issuer, thêm scope tương ứng để tránh collision. Tránh dùng nonce toàn cục mà không có namespace nếu các client độc lập có thể tình cờ tạo cùng giá trị. Một nonce trùng do ngẫu nhiên là cực kỳ hiếm khi entropy đủ lớn, nhưng namespace vẫn cần rõ ràng.

## 7. Canonical request: chữ ký phải bao phủ đúng request

Replay prevention chỉ có ý nghĩa khi HMAC xác thực **đúng request sẽ được xử lý**. Nếu client ký một chuỗi nhưng server xử lý request khác do canonicalization không nhất quán, attacker có thể lợi dụng khác biệt parser hoặc chuyển chữ ký sang một ngữ cảnh khác.

Một canonical request có thể bao gồm:

~~~text
HMAC-REQUEST-V1
POST
api.internal.example
/v1/transfers
currency=VND
content-type:application/json
x-key-id:workload-42-key-3
x-timestamp:1795320000
x-nonce:7G4fJp9zW1rQm2xK8vN6aA
x-content-sha256:<body-digest>

<optional-idempotency-key>
~~~

Đây là format minh họa. Một giao thức thực tế cần đặc tả chính xác từng dòng, delimiter, encoding, newline cuối, cách xử lý query và header lặp. Client và server phải tạo ra **cùng một byte sequence**, không chỉ hai chuỗi nhìn có vẻ giống nhau.

### Các thành phần nên cân nhắc ký

| Thành phần | Vì sao cần ký |
| --- | --- |
| Protocol/version | Ngăn diễn giải request theo format hoặc policy khác. |
| HTTP method | Không cho chữ ký GET được dùng như POST. |
| Authority/host | Ngăn chuyển request sang service/host khác. |
| Path và query | Ràng buộc endpoint, tài nguyên và tham số. |
| Timestamp | Bảo vệ thời gian tạo request. |
| Nonce | Bảo vệ định danh duy nhất của lần gửi. |
| Body digest | Ràng buộc body byte-for-byte với chữ ký. |
| Content-Type hoặc header bảo mật liên quan | Tránh diễn giải cùng body theo kiểu dữ liệu khác. |
| Key ID/client ID hoặc audience | Ràng buộc credential và dịch vụ nhận. |
| Tenant/action context nếu có | Ngăn đổi tenant hoặc mục đích mà chữ ký vẫn hợp lệ. |
| Idempotency key nếu dùng | Ràng buộc khóa xử lý retry với request đã ký. |

Không nhất thiết phải ký mọi header. Chỉ ký các header đã được định nghĩa rõ và có ảnh hưởng tới cách server xử lý. Nếu header có thể lặp, cần quy tắc từ chối hoặc chuẩn hóa chính xác; không để proxy và ứng dụng hiểu khác nhau.

### Canonicalization cần tránh mơ hồ

- Method được chuẩn hóa theo quy tắc cụ thể, thường là uppercase.
- Authority phải chuẩn hóa hostname, port và IDN theo một policy thống nhất.
- Path phải xử lý percent-encoding nhất quán; không ký một dạng rồi router giải mã thành dạng khác.
- Query parameter phải có quy tắc về thứ tự, duplicate key, dấu +, percent-encoding và giá trị rỗng. Không tự sort nếu protocol không quy định.
- Header name không phân biệt hoa/thường theo HTTP, nhưng value whitespace, duplicate header và folding phải có quy tắc.
- Body digest phải được tính trên đúng byte sequence mà server xác minh; không parse JSON rồi serialize lại theo cách có thể đổi whitespace, key order hoặc number format.
- Reverse proxy không được âm thầm đổi method, path, host hoặc body sau khi signature đã được kiểm tra, trừ khi ranh giới ký được định nghĩa rõ.

Nếu client ký request target trước proxy nhưng server kiểm tra sau khi proxy rewrite URL, hai bên có thể tạo canonical request khác nhau. Hãy chọn một điểm xác minh tin cậy (ví dụ API gateway) và đặc tả request representation ở điểm đó.

## 8. HMAC signature: ký timestamp và nonce, không chỉ ký body

Ví dụ cách tính MAC:

~~~java
byte[] mac(byte[] secret, byte[] canonicalRequest) throws Exception {
    Mac hmac = Mac.getInstance("HmacSHA256");
    SecretKeySpec key = new SecretKeySpec(secret, "HmacSHA256");
    hmac.init(key);
    return hmac.doFinal(canonicalRequest);
}
~~~

Client mã hóa MAC bằng Base64URL hoặc encoding đã quy định rồi gửi trong header. Server phải dùng cùng algorithm, key, canonicalization và encoding. Không cho client tự chọn thuật toán tùy ý; server nên cấu hình một bộ thuật toán cho protocol version, ví dụ HMAC-SHA-256, và từ chối downgrade hoặc thuật toán không được phép.

### Kiểm tra chữ ký constant-time

So sánh MAC cần dùng hàm so sánh constant-time của nền tảng/thư viện phù hợp, tránh so sánh byte-array theo kiểu dừng ngay ở byte đầu tiên khác nhau. Điều này giảm kênh timing có thể rò rỉ thông tin về chữ ký. Vẫn cần giới hạn độ dài input và kiểm tra encoding trước khi so sánh.

### Key ID không phải bí mật

Header key ID giúp server tìm secret tương ứng, nhưng bản thân key ID có thể công khai. Server phải ánh xạ key ID tới client principal, trạng thái key, audience, scope và policy. Không tin tenant hoặc account do client khai báo chỉ vì key ID hợp lệ.

## 9. Trình tự xác minh phía server

Một verifier cần kiểm tra theo thứ tự rõ ràng để vừa chống replay vừa tránh tạo bề mặt từ chối dịch vụ.

1. **Parse chặt request:** giới hạn kích thước header/body, từ chối header trùng hoặc format mơ hồ, parse timestamp/nonce đúng định dạng.
2. **Tra key:** dùng key ID để tìm credential; kiểm tra key còn active, đúng client, đúng audience/service và thuật toán được cấu hình.
3. **Kiểm tra timestamp sơ bộ:** từ chối timestamp quá cũ hoặc quá xa trong tương lai trước khi thực hiện xử lý tốn kém.
4. **Tính body digest và canonical request:** dùng byte sequence và các thành phần đúng theo protocol.
5. **Xác minh HMAC:** tính expected MAC và so sánh constant-time. Nếu sai, từ chối và không ghi nonce vào replay cache.
6. **Đăng ký nonce nguyên tử:** chỉ sau khi MAC hợp lệ, cố gắng tạo replay record với điều kiện chưa tồn tại. Nếu nonce đã có, từ chối replay.
7. **Kiểm tra trạng thái principal và policy:** client/service còn active, tenant context hợp lệ, scope phù hợp.
8. **Authorization:** kiểm tra hành động và tài nguyên cụ thể.
9. **Thực hiện nghiệp vụ:** áp dụng idempotency cho tác vụ có side effect và ghi audit phù hợp.

~~~mermaid
flowchart TD
    A["Nhận HTTP request"] --> B["Parse header và giới hạn input"]
    B --> C["Tra key ID, kiểm tra trạng thái/audience"]
    C --> D["Kiểm tra timestamp window"]
    D --> E["Tạo canonical request + body digest"]
    E --> F{"HMAC hợp lệ?"}
    F -- "Không" --> X["Từ chối; không ghi nonce"]
    F -- "Có" --> G["Atomic reserve nonce"]
    G --> H{"Nonce đã tồn tại?"}
    H -- "Có" --> Y["Từ chối replay"]
    H -- "Không" --> I["Kiểm tra principal, tenant, scope"]
    I --> J["Authorization theo resource/action"]
    J --> K["Idempotency và xử lý nghiệp vụ"]
    K --> L["Ghi audit / trả response"]
~~~

Vì sao không lưu nonce trước khi xác minh HMAC? Nếu attacker gửi hàng loạt request giả với nonce tùy ý, họ có thể làm đầy replay cache hoặc chiếm trước nonce của request hợp lệ. Xác minh chữ ký trước giúp chỉ request có MAC hợp lệ mới được phép tiêu thụ không gian replay store. Vẫn cần rate limit cho request không hợp lệ để bảo vệ CPU và key lookup.

## 10. Atomic replay cache: ngăn hai request đồng thời cùng thành công

Kiểm tra nonce theo kiểu đọc rồi ghi riêng rẽ không đủ:

~~~text
Request A: GET nonce -> chưa tồn tại
Request B: GET nonce -> chưa tồn tại
Request A: INSERT nonce
Request B: INSERT nonce
Request A: thực hiện chuyển tiền
Request B: thực hiện chuyển tiền lần nữa
~~~

Cần một thao tác **check-and-set nguyên tử**. Hai lựa chọn phổ biến:

### 10.1. Redis SET NX với TTL

~~~text
SET replay:v1:workload-42-key-3:7G4fJp9zW1rQm2xK8vN6aA 1 NX EX 600
~~~

- NX chỉ tạo key nếu chưa tồn tại.
- EX đặt TTL để tự dọn trạng thái sau thời gian cần chống replay.
- Chỉ request nhận kết quả thành công từ thao tác reserve mới được tiếp tục.
- Redis key phải được namespace theo môi trường, protocol version và key/client scope.

Đây là lệnh minh họa; cần kiểm tra cách client Redis xử lý timeout và kết quả không xác định. Nếu server timeout sau khi Redis đã ghi nonce, request có thể bị xem như đã dùng dù client không biết. Hành vi đó an toàn hơn việc tự động bỏ qua nonce, nhưng cần retry/idempotency để xử lý trải nghiệm.

### 10.2. Unique constraint trong database

~~~sql
CREATE TABLE used_request_nonces (
    key_id       TEXT NOT NULL,
    nonce        TEXT NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    accepted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (key_id, nonce)
);
~~~

Server INSERT nonce; nếu vi phạm primary key thì nonce đã được dùng. Có thể dọn bản ghi hết hạn bằng job. Việc insert phải diễn ra trong transaction và nằm đúng ranh giới consistency của hệ thống.

### TTL nên tính như thế nào?

Giả sử server chấp nhận timestamp trong khoảng ±W giây. Một request có timestamp ở phía tương lai của cửa sổ có thể vẫn được chấp nhận cho đến khi timestamp đó cộng W giây. TTL nonce phải đủ dài để request không thể quay lại trong bất kỳ thời điểm nào mà timestamp vẫn được chấp nhận.

Một quy tắc khái niệm là giữ nonce đến ít nhất:

~~~text
nonceExpiresAt = requestTimestamp + allowedClockSkew + safetyMargin
~~~

Nếu server có quy tắc khác cho timestamp tương lai/quá khứ, TTL cần được suy ra từ đúng acceptance window đó. Không đặt TTL ngắn tùy tiện hơn cửa sổ timestamp. Nếu nonce record hết hạn trong khi request cũ vẫn được timestamp policy chấp nhận, attacker có thể replay lại.

## 11. Nhiều instance và nhiều region: replay cache phải nhất quán

Một hệ thống có nhiều API instance cần đảm bảo mọi verifier nhìn thấy cùng trạng thái nonce trong phạm vi key. Nếu request đầu tới instance A và replay tới instance B, hai cache local độc lập có thể cùng chấp nhận.

Các lựa chọn:

- **Shared replay store:** Redis/database dùng chung với atomic insert. Cần thiết kế HA, replication, failover và consistency.
- **Partition theo key/client:** tất cả request của một key được route về một partition/region có trạng thái duy nhất. Phải bảo đảm routing không thay đổi tùy tiện và failover không làm mất nonce state.
- **Strongly consistent datastore:** dùng unique constraint/transaction ở nơi đảm bảo tính duy nhất trong toàn phạm vi.
- **Region-local cache:** chỉ phù hợp nếu protocol/routing bảo đảm request của cùng key không thể được replay sang region khác trong cửa sổ; nếu không, không đủ chống replay toàn hệ thống.

Eventual consistency có thể làm hai region cùng thấy nonce chưa tồn tại trong một khoảng thời gian. Với thao tác nhạy cảm, không dùng replay store eventually consistent như thể nó cung cấp atomic global uniqueness.

### Khi replay store không khả dụng?

Đối với request có side effect hoặc quyền cao, **fail closed** thường an toàn hơn: không thể kiểm tra nonce thì không thực hiện request. Soft-fail có thể biến outage của replay store thành cửa sổ cho phép phát lại. Nếu tổ chức chọn phương án dự phòng, cần phạm vi, thời gian, quyền và audit được phê duyệt rõ ràng; không tự động bỏ kiểm tra trên toàn hệ thống.

Giám sát replay store: latency, error/timeout, memory, eviction, replication lag, failover và số lần reserve thất bại. Nếu Redis eviction xóa nonce trước TTL, hệ thống có thể mất khả năng nhận biết replay; cấu hình memory/persistence/eviction phải phù hợp với vai trò bảo mật của cache.

## 12. Idempotency khác replay prevention như thế nào?

Hai cơ chế liên quan nhưng giải quyết hai vấn đề khác nhau:

- **Replay prevention:** cùng một request đã ký (cùng nonce) không được chấp nhận lần thứ hai.
- **Idempotency:** nhiều lần thử hợp lệ của cùng một thao tác logic không tạo ra side effect lặp lại.

Ví dụ client gửi lệnh tạo thanh toán. Server đã thực hiện thanh toán nhưng response bị mất trên đường về. Client không biết kết quả và muốn retry.

Nếu client gửi lại cùng nonce, replay guard sẽ từ chối. Nếu client tạo nonce mới nhưng giữ cùng idempotency key, server có thể nhận request mới đã ký, nhận ra thao tác logic đã được xử lý và trả lại kết quả cũ thay vì tạo thanh toán lần nữa.

~~~text
Request attempt 1:
  nonce = N1
  idempotency-key = payment-2026-00042
  HMAC = signature-1
  -> payment committed, response lost

Request attempt 2:
  nonce = N2 (mới)
  idempotency-key = payment-2026-00042 (giữ nguyên)
  HMAC = signature-2
  -> xác minh request mới, trả kết quả đã lưu, không tạo payment mới
~~~

Idempotency key nên được ký cùng request và gắn với client/tenant/action/body fingerprint. Nếu cùng idempotency key nhưng body hoặc tài nguyên khác, server phải từ chối conflict thay vì trả kết quả của thao tác khác.

Không dùng idempotency key thay nonce. Idempotency có thể có thời gian lưu lâu và mục đích nghiệp vụ; nonce là trạng thái chống replay trong acceptance window của giao thức.

## 13. Timestamp, nonce và request ID: không dùng lẫn nhau

| Giá trị | Ai tạo? | Tính chất | Mục đích |
| --- | --- | --- | --- |
| Timestamp | Client ký request | Thời gian, có thể lặp giữa nhiều request | Giới hạn tuổi request. |
| Nonce | Client ký request | Ngẫu nhiên, mới cho từng lần gửi | Ngăn chấp nhận lại cùng request. |
| Request ID | Client hoặc server theo protocol | Định danh phục vụ trace | Tương quan log/trace; chỉ chống replay nếu được ràng buộc và lưu như nonce. |
| Idempotency key | Client hoặc ứng dụng tạo theo thao tác logic | Giữ nguyên qua retry cùng một thao tác | Ngăn side effect nghiệp vụ trùng lặp. |
| Key ID | Nhà cung cấp credential | Định danh credential, không cần bí mật | Tra khóa HMAC và policy. |
| Signature/MAC | Client có secret | Giá trị xác thực có thể tính lại | Xác minh tính toàn vẹn và quyền kiểm soát key. |

Một request ID tăng dần không nhất thiết là nonce an toàn; nhiều client có thể trùng, counter có thể rollback và giá trị có thể đoán. Một idempotency key cũng không tự chống replay nếu server không kiểm tra trạng thái đã xử lý.

## 14. Replay ở các ranh giới khác nhau

### 14.1. Replay giữa endpoint

Nếu canonical request không ký method và path, attacker có thể thử dùng chữ ký tạo cho endpoint ít nhạy cảm ở endpoint khác. Hãy ràng buộc method, authority, path, query và audience/service.

### 14.2. Replay giữa tenant

Trong multi-tenant API, request ký cho tenant Alpha không được sử dụng cho Beta. Tenant context cần được xác định từ server hoặc đưa vào canonical request nếu client được phép chọn tenant. Dù tenant ID được ký, server vẫn phải kiểm tra key có quyền trong tenant đó.

### 14.3. Replay giữa môi trường

Không dùng cùng secret cho development, staging và production. Authority/audience và key namespace cần tách biệt để request staging không thể được chấp nhận ở production.

### 14.4. Replay giữa key rotation

Replay cache nên namespace theo key ID/credential version. Khi key cũ và mới cùng hoạt động trong giai đoạn overlap, request được ký bằng key cũ vẫn cần nonce protection trong scope key cũ. Khi key cũ bị revoke, từ chối request dùng key đó ngay cả khi timestamp/nonce hợp lệ.

### 14.5. Replay ở tầng ứng dụng sau TLS

Nếu TLS connection được terminate tại load balancer, API phía sau có thể nhận request đã được proxy chuyển tiếp. HMAC verifier phải chạy ở ranh giới được tin cậy và mọi hop nội bộ phải giữ nguyên hoặc chuyển tiếp thông tin đã xác minh theo cơ chế không thể bị client giả mạo. Không để một service downstream bỏ qua kiểm tra vì tưởng gateway đã làm, nếu không có hợp đồng trust và kênh nội bộ phù hợp.

## 15. Key provisioning, rotation và compromise

Replay prevention phụ thuộc vào bí mật HMAC:

- Tạo secret ngẫu nhiên bằng CSPRNG, entropy cao; không dùng password người dùng hoặc chuỗi dễ đoán.
- Mỗi client/workload nên có key riêng, hạn chế chia sẻ một secret cho nhiều dịch vụ hoặc nhiều tenant.
- Lưu secret trong secret manager/HSM hoặc kho được bảo vệ; phân quyền tối thiểu, audit truy cập và tránh ghi vào log/config public.
- Dùng key ID để chọn credential, không gửi secret trong request.
- Có trạng thái active, retiring, revoked và thời hạn; rotation có giai đoạn overlap được kiểm soát.
- Khi secret nghi bị lộ, revoke key cũ, cấp key mới, điều tra request đã ký trong thời gian ảnh hưởng và thu hồi session/token nếu cần.

Nếu attacker có secret, họ có thể tạo timestamp mới, nonce mới và HMAC hợp lệ. Replay cache chỉ ngăn dùng lại nonce, **không ngăn một bên đã chiếm secret tạo request giả mới**. Đây là lý do key protection, rotation, least privilege và monitoring vẫn thiết yếu.

### Rotation minh họa

~~~text
T0: key-7 active
T1: provision key-8 cho client
T2: client bắt đầu ký bằng key-8
T3: server chấp nhận key-7 và key-8 trong overlap ngắn
T4: xác nhận client đã chuyển hoàn toàn sang key-8
T5: revoke key-7, xóa/disable secret cũ theo policy
~~~

Không kéo dài overlap vô thời hạn. Nếu key cũ bị compromise, không chờ hết overlap thông thường; revoke khẩn cấp và xử lý ảnh hưởng.

## 16. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Chỉ kiểm tra HMAC, không timestamp/nonce | Request hợp lệ có thể được replay | Kết hợp timestamp, nonce và replay store. |
| Chỉ có timestamp | Replay được trong cửa sổ chấp nhận | Dùng nonce và atomic reserve. |
| Chỉ có nonce nhưng không expiry | Replay cache phình lớn; request cũ có thể được thử vô hạn nếu record bị dọn sai | Gắn timestamp và TTL suy ra từ acceptance window. |
| Không ký nonce/timestamp | Attacker thay metadata chống replay | Bao gồm chúng trong canonical request. |
| Không ký method/path/authority | Chữ ký bị chuyển sang endpoint/host khác | Ràng buộc toàn bộ request target cần thiết. |
| Canonicalization khác client/server | Bypass, signature mismatch hoặc request smuggling | Đặc tả byte-level canonicalization và kiểm thử proxy/parser. |
| Lưu nonce trước khi xác minh MAC | Request giả có thể làm đầy cache/chiếm nonce | Xác minh HMAC trước rồi atomic reserve. |
| SELECT rồi INSERT không nguyên tử | Hai request đồng thời cùng được chấp nhận | SET NX/unique constraint/transaction. |
| Replay cache local từng instance | Replay tới server khác được chấp nhận | Shared consistent store hoặc routing có bảo đảm. |
| TTL ngắn hơn acceptance window | Nonce bị xóa khi timestamp vẫn còn hợp lệ | Tính TTL từ timestamp policy và clock skew. |
| Soft-fail khi replay store lỗi | Outage biến thành bypass | Fail closed cho hành động nhạy cảm; có fallback được phê duyệt. |
| Dùng key chung cho mọi client | Một client bị lộ secret ảnh hưởng toàn hệ thống | Key riêng, scope hẹp, rotation. |
| Không dùng constant-time compare | Có thể tạo kênh timing | Dùng primitive so sánh constant-time. |
| Nhầm nonce với idempotency key | Retry hợp lệ bị chặn hoặc side effect bị lặp | Dùng nonce mới cho mỗi attempt và idempotency key cho thao tác logic. |
| Tin tenant/account trong body | Key hợp lệ có thể bị dùng vượt scope | Ánh xạ key tới principal, kiểm tra membership/authorization. |

## 17. Ví dụ thiết kế request và verifier

Ví dụ request ký:

~~~http
POST /v1/orders?region=ap-southeast HTTP/1.1
Host: api.internal.example
X-Key-Id: workload-orders-12
X-Signature-Version: 1
X-Timestamp: 1795320000
X-Nonce: Yx9c4pQm0A8v3Tn7Lk2sRg
X-Content-SHA256: <digest>
Idempotency-Key: order-2026-00091
Authorization: HMAC-SHA256 <mac>
Content-Type: application/json

{"productId":"P-100","quantity":2}
~~~

Canonical request minh họa:

~~~text
HMAC-REQUEST-V1
POST
api.internal.example
/v1/orders
region=ap-southeast
content-type:application/json
idempotency-key:order-2026-00091
x-key-id:workload-orders-12
x-timestamp:1795320000
x-nonce:Yx9c4pQm0A8v3Tn7Lk2sRg
x-content-sha256:<digest>
~~~

Verifier pseudocode:

~~~java
Response handleSignedRequest(HttpRequest request) {
    ParsedSignature parsed = parser.parseStrictly(request);

    ClientKey key = keyStore.requireActive(parsed.keyId());
    policy.requireAudience(key, request.authority());

    Instant timestamp = parseTimestampStrictly(parsed.timestamp());
    clockPolicy.requireWithinWindow(timestamp, clock.instant());

    byte[] bodyBytes = request.rawBodyBytes();
    String bodyDigest = sha256Base64Url(bodyBytes);

    CanonicalRequest canonical = canonicalizer.build(
        request.method(),
        request.authority(),
        request.rawPathAndQuery(),
        parsed.timestamp(),
        parsed.nonce(),
        bodyDigest,
        parsed.idempotencyKey(),
        parsed.keyId());

    byte[] expectedMac = hmacSha256(key.secret(), canonical.bytes());
    byte[] suppliedMac = decodeBase64UrlStrictly(parsed.signature());

    if (!constantTimeEquals(expectedMac, suppliedMac)) {
        throw genericAuthenticationFailure();
    }

    // Atomic operation: only one request with this key+nonce wins.
    boolean firstUse = replayStore.reserveOnce(
        parsed.keyId(),
        parsed.nonce(),
        expiryFor(timestamp, clockPolicy));

    if (!firstUse) {
        throw replayDetected();
    }

    Principal principal = principalResolver.fromKey(key);
    authorization.requireAllowed(principal, request);

    return idempotency.executeOnce(
        principal,
        parsed.idempotencyKey(),
        bodyDigest,
        () -> applicationService.execute(request, principal));
}
~~~

Đây là **giả mã minh họa**, không phải thư viện HMAC/HTTP production. Trong triển khai thật, cần xác minh parser, body byte representation, canonicalization, key lifecycle, replay store consistency, transaction boundaries, authorization và error handling. Không log secret, raw MAC nếu policy coi đó là dữ liệu nhạy cảm, hoặc toàn bộ request chứa thông tin cá nhân.

### Thứ tự và lỗi nghiệp vụ

Nếu nonce đã được reserve nhưng database nghiệp vụ lỗi, request retry với nonce cũ sẽ bị từ chối. Client cần tạo nonce mới và giữ idempotency key của cùng thao tác logic. Server dùng idempotency record để trả kết quả cũ hoặc tiếp tục xử lý an toàn. Không giải quyết lỗi bằng cách xóa nonce tùy tiện sau khi có side effect chưa rõ trạng thái.

## 18. Kiểm thử chống replay

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Request có HMAC hợp lệ, timestamp mới, nonce mới | Chấp nhận nếu key/policy/authorization hợp lệ. |
| Gửi lại nguyên request sau lần đầu | Từ chối do nonce đã dùng. |
| Cùng nonce nhưng sửa body | HMAC không hợp lệ; không consume nonce. |
| Sửa timestamp nhưng giữ MAC cũ | HMAC không hợp lệ. |
| Timestamp quá cũ | Từ chối trước khi thực hiện nghiệp vụ. |
| Timestamp quá xa trong tương lai | Từ chối. |
| Nonce thiếu hoặc sai encoding | Từ chối theo parser policy. |
| Nonce ngẫu nhiên trùng trong cùng key scope | Chỉ một request được reserve; request còn lại bị từ chối. |
| Hai request giống nhau tới hai instance đồng thời | Chỉ một request được chấp nhận. |
| Replay sang endpoint khác | Từ chối do method/path/authority không khớp canonical request. |
| Replay sang tenant khác | Từ chối do tenant/action scope và authorization không hợp lệ. |
| Replay sang staging/production khác nhau | Từ chối do key/audience/authority khác. |
| HMAC sai nhưng nonce mới | Không ghi nonce vào replay cache. |
| Replay store timeout | Hành động nhạy cảm không được tự động fail open. |
| Replay cache record hết TTL trước acceptance window | Test phải phát hiện cấu hình sai; không được chấp nhận replay. |
| Client retry với nonce mới và cùng idempotency key | Trả kết quả cũ hoặc xử lý một lần, không tạo side effect thứ hai. |
| Cùng idempotency key nhưng body khác | Từ chối conflict. |
| Key bị revoke nhưng HMAC cũ vẫn đúng | Từ chối do key status. |
| Key rotation overlap | Chỉ key trong trạng thái được phép mới được chấp nhận; nonce scope tách theo key ID. |
| Secret bị thay đổi ở client mà server chưa cập nhật | Từ chối chữ ký; không hạ thuật toán. |
| Proxy thay path/body sau điểm ký | Signature mismatch hoặc protocol xử lý rõ ràng, không chấp nhận ngầm. |
| Duplicate security header | Từ chối hoặc xử lý theo quy tắc canonicalization thống nhất. |
| Clock drift của client tăng | Request ngoài cửa sổ bị từ chối và được ghi nhận để điều tra. |

### Kiểm thử concurrency

Chạy nhiều request đồng thời có cùng key ID, nonce và MAC tới các verifier khác nhau. Kết quả cần có **tối đa một lần reserve thành công**. Không chỉ kiểm tra status HTTP; xác minh database chỉ có một side effect (một payment/order/job) và audit cho thấy các lần còn lại bị nhận diện là replay.

## 19. Vận hành và quan sát

Các chỉ số hữu ích:

- Số request bị từ chối do timestamp cũ/tương lai.
- Số nonce trùng và tỷ lệ replay theo key/client/service.
- Tỷ lệ HMAC mismatch, key unknown, key revoked và canonicalization error.
- Replay store latency, timeout, failover, eviction và replication lag.
- Phân bố clock skew giữa client/server.
- Tỷ lệ idempotency hit, conflict và request retry.
- Thời gian từ key compromise tới revoke và từ revoke tới mọi verifier thực thi.
- Tỷ lệ request fail closed do replay store outage.

Log cần đủ để điều tra nhưng không biến thành kho lưu request có thể phát lại. Có thể ghi key ID, request ID, nonce fingerprint/hash, timestamp, route, reason code và correlation ID theo policy. Không log shared secret, Authorization header, raw token hoặc nội dung nhạy cảm không cần thiết. Nếu lưu nonce để audit, cần bảo vệ và giới hạn retention.

## 20. Bài tập tình huống

Một dịch vụ thanh toán nội bộ nhận request ký bằng HMAC. Hệ thống hiện chỉ kiểm tra HMAC và timestamp trong cửa sổ ±5 phút. Hai API instance chạy ở hai region, mỗi region dùng một replay cache local. Client có thể retry khi timeout và hiện tại retry bằng cách gửi lại nguyên request. Một ngày, một request tạo lệnh thanh toán bị phát lại ở region thứ hai.

**Yêu cầu phân tích:**

1. Vì sao timestamp không ngăn được replay trong cửa sổ 5 phút?
2. Vì sao cache local từng region không bảo vệ request giữa hai region?
3. Thiết kế canonical request phải ký những thành phần nào?
4. Làm sao bảo đảm nonce chỉ được chấp nhận một lần trên toàn phạm vi?
5. Client nên retry thế nào nếu server đã xử lý nhưng response bị mất?
6. Replay cache không khả dụng thì policy nên làm gì với lệnh thanh toán?
7. Nếu shared secret bị lộ, timestamp và nonce còn bảo vệ được điều gì?

**Hướng phân tích:** Bổ sung nonce ngẫu nhiên mới cho mỗi attempt và ký nonce cùng timestamp, method, authority, path/query, body digest, key ID/audience và idempotency key. Dùng replay store có atomic uniqueness nhất quán giữa hai region hoặc route mọi request của key về một partition có bảo đảm. Retry dùng nonce mới nhưng giữ idempotency key; server trả kết quả cũ thay vì thanh toán lần hai. Với thanh toán, không thể kiểm tra replay thì nên fail closed. Nếu secret bị lộ, attacker có thể tạo request mới với nonce/timestamp mới; phải revoke key, cấp key mới, điều tra và thu hồi session/token liên quan.

## 21. Checklist review

- [ ] HMAC được hiểu đúng là message authentication/integrity bằng secret dùng chung, không phải encryption hoặc non-repudiation.
- [ ] Key ID ánh xạ tới principal, audience, scope và trạng thái key ở server.
- [ ] Timestamp có đơn vị, parser và acceptance window rõ ràng.
- [ ] Nonce được sinh bằng CSPRNG, đủ entropy và không tái sử dụng trong key scope.
- [ ] HMAC bao phủ timestamp, nonce, method, authority, path/query, body digest và các header/ngữ cảnh quan trọng.
- [ ] Canonicalization được đặc tả theo byte, xử lý duplicate header, encoding, proxy và body representation nhất quán.
- [ ] HMAC được so sánh constant-time; thuật toán/version do server policy kiểm soát.
- [ ] Chỉ sau khi MAC hợp lệ mới atomic reserve nonce.
- [ ] Replay cache có TTL ít nhất bằng acceptance window thực tế và không bị eviction sớm.
- [ ] Replay store nhất quán trên mọi instance/region có thể nhận cùng request.
- [ ] Replay store outage có hard-fail policy phù hợp với mức rủi ro.
- [ ] Retry dùng nonce mới và idempotency key giữ nguyên cho cùng thao tác logic.
- [ ] Idempotency key được ký, scope theo client/tenant/action và kiểm tra body conflict.
- [ ] Key riêng cho client, secret được bảo vệ, rotation và revoke có quy trình.
- [ ] Authentication, tenant resolution và authorization vẫn được kiểm tra độc lập.
- [ ] Có test replay đồng thời, cross-endpoint, cross-tenant, cross-region và side effect trùng.

## 22. Ghi nhớ

**HMAC xác minh request được tạo bởi bên có secret và nội dung đã ký không bị sửa; nó không tự ngăn một request hợp lệ bị gửi lại.** Một thiết kế chống replay cần timestamp để giới hạn tuổi request, nonce mới cho từng lần gửi, canonical request ràng buộc đúng đích và nội dung, cùng replay store có thao tác atomic và nhất quán. Retry hợp lệ cần nonce mới nhưng có thể dùng idempotency key để tránh lặp side effect.

Khi review giao thức, hãy hỏi: **Request ký chính xác những byte và ngữ cảnh nào? Timestamp còn được chấp nhận bao lâu? Nonce được lưu ở đâu và có nguyên tử trên mọi instance không? Điều gì xảy ra khi cache lỗi? Client retry ra sao sau timeout? Nếu secret bị lộ hoặc key bị revoke, mọi verifier có ngừng tin nó kịp thời không?**
