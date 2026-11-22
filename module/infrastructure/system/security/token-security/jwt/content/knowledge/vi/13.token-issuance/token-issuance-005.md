# Sinh jti bằng nguồn ngẫu nhiên phù hợp khi cần định danh token

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Nội dung áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hay framework.

## 1. jti là gì và khi nào cần dùng?

`jti` (JWT ID) là registered claim dùng để cung cấp **định danh duy nhất cho một JWT**. Theo RFC 7519, giá trị `jti` là chuỗi phân biệt chữ hoa/chữ thường; issuer cần bảo đảm giá trị được tạo ra không vô tình trùng với một JWT khác trong phạm vi mà hệ thống yêu cầu. Bên nhận có thể sử dụng định danh này để chống phát lại (replay), thu hồi token, theo dõi sự kiện hoặc liên kết token với bản ghi quản lý phía máy chủ.

Ví dụ:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "iat": 1900000000,
  "exp": 1900000900,
  "jti": "n9Wq7XrQv0d5aYh3c2Lk8A"
}
~~~

`jti` là mã nhận diện token trong ví dụ. Nó không phải danh tính người dùng, không phải quyền truy cập và cũng không phải một bằng chứng xác thực độc lập.

**Không phải mọi JWT đều bắt buộc có `jti`.** Chỉ thêm claim này khi profile token hoặc nghiệp vụ cần định danh từng token. Nếu hệ thống cần thu hồi riêng từng token, phát hiện sử dụng lại, xử lý token dùng một lần hoặc truy vết phát hành, `jti` thường hữu ích. Với một token tự chứa đơn giản, không có nhu cầu định danh riêng và không có trạng thái liên quan ở phía máy chủ, việc thêm `jti` có thể không đem lại lợi ích đáng kể.

Trước khi quyết định, hãy trả lời ba câu hỏi:

1. Hệ thống cần nhận diện **từng token cụ thể** hay chỉ cần nhận diện subject/session/grant?
2. Định danh sẽ được dùng cho mục đích nào: audit, denylist, replay detection, one-time use hay correlation?
3. Có thành phần nào lưu và kiểm tra trạng thái của `jti` không? Nếu không, claim này chỉ là một nhãn định danh được ký cùng token.

## 2. Phân biệt jti với các giá trị thường bị nhầm lẫn

| Giá trị | Vai trò | Khác biệt với `jti` |
| --- | --- | --- |
| `sub` | Định danh chủ thể mà token đại diện | Nhiều token của cùng chủ thể có thể có cùng `sub` |
| `sid` hoặc session ID | Định danh phiên đăng nhập theo profile/thiết kế | Một phiên có thể phát hành nhiều JWT với các `jti` khác nhau |
| `jti` | Định danh một token cụ thể | Thay đổi mỗi lần phát hành một JWT mới |
| Nonce | Giá trị dùng một lần hoặc giá trị thách thức để liên kết/chống phát lại trong một giao thức | Ngữ nghĩa và vòng đời phụ thuộc giao thức; không mặc định tương đương `jti` |
| CSRF state | Liên kết yêu cầu khởi tạo và callback trong một luồng | Dùng cho giao dịch/luồng cụ thể, không phải ID chung của JWT |
| Idempotency key | Định danh một yêu cầu nghiệp vụ để xử lý retry an toàn | Không tự động là ID của token hoặc bằng chứng chống replay |
| `kid` | Gợi ý chọn khóa ký trong JOSE header | Định danh khóa, không định danh token |

Mỗi JWT được phát hành mới nên có một `jti` mới nếu hệ thống sử dụng claim này. Không tái sử dụng `jti` chỉ vì token mới có cùng subject, audience hoặc scope. Một token được refresh, reissue hoặc trao đổi thành token khác là một lần phát hành mới và cần định danh riêng.

## 3. Tính duy nhất và tính khó đoán là hai thuộc tính khác nhau

Khi thiết kế `jti`, cần phân biệt:

- **Uniqueness (tính duy nhất):** hai token khác nhau không nhận cùng định danh trong phạm vi cần quản lý.
- **Unpredictability (tính khó đoán):** người ngoài không dễ dự đoán giá trị của một định danh chưa được phát hành.

Hai thuộc tính này có mục đích khác nhau. Một bộ đếm tăng dần có thể tạo giá trị duy nhất nếu được quản lý tập trung, nhưng giá trị dễ đoán và có thể làm lộ số lượng token đã phát hành. Một giá trị ngẫu nhiên mạnh vừa có xác suất va chạm rất thấp, vừa khó dự đoán.

`jti` không phải bí mật theo định nghĩa: claim thường hiển thị trong payload JWT đã mã hóa Base64URL và người có token có thể đọc nó. Tuy vậy, **định danh khó đoán** có ích khi token ID được dùng trong các luồng quản lý trạng thái, tham chiếu bản ghi hoặc chống đoán định danh. Không được xem tính khó đoán của `jti` là biện pháp bảo vệ bearer token.

Khuyến nghị thực tế cho đa số hệ thống là dùng một giá trị ngẫu nhiên có đủ entropy từ **nguồn sinh số ngẫu nhiên mật mã (CSPRNG)**. Nếu nghiệp vụ chỉ cần tính duy nhất và dùng bộ cấp phát ID có bảo đảm, vẫn phải đánh giá việc lộ quy mô, khả năng đoán và phạm vi duy nhất trước khi chọn.

## 4. Chọn nguồn ngẫu nhiên phù hợp

### 4.1. CSPRNG và nguồn ngẫu nhiên của hệ điều hành

CSPRNG (Cryptographically Secure Pseudorandom Number Generator) là bộ sinh số giả ngẫu nhiên được thiết kế cho mục đích bảo mật. Nó sử dụng trạng thái được khởi tạo và quản lý bằng nguồn entropy phù hợp; người quan sát không thể dễ dàng dự đoán đầu ra tiếp theo chỉ từ những đầu ra trước đó.

Nên dùng:

- API sinh byte ngẫu nhiên mật mã được hệ điều hành hoặc nền tảng cung cấp;
- thư viện mật mã đã được kiểm chứng, sử dụng CSPRNG chuẩn của môi trường;
- cơ chế DRBG được triển khai theo tiêu chuẩn phù hợp, với quy trình khởi tạo, reseed và quản lý trạng thái đúng cách.

Ứng dụng nên gọi API cấp cao đã được nền tảng cung cấp. Không tự viết bộ sinh số ngẫu nhiên cho mục đích bảo mật.

### 4.2. Những nguồn không phù hợp

Không dùng các nguồn sau để tạo `jti` trong bối cảnh bảo mật:

- hàm random thông thường không cam kết an toàn mật mã;
- thời gian hiện tại, timestamp hoặc số mili giây;
- bộ đếm đơn giản, số thứ tự bản ghi hoặc ID tăng dần nếu cần tính khó đoán;
- PID, hostname, địa chỉ IP, MAC address hoặc thông tin môi trường;
- hash của username, email, subject hoặc tổ hợp dữ liệu công khai;
- giá trị lấy từ request, header hoặc client tự gửi;
- chuỗi ngẫu nhiên tự chế bằng cách ghép các ký tự hoặc chọn từ danh sách nhỏ.

Các giá trị này có thể trùng, dự đoán được, rò rỉ thông tin hoặc bị điều khiển từ bên ngoài. Ghép timestamp với một số ngẫu nhiên yếu cũng không tự động tạo thành ID an toàn.

### 4.3. Không fallback sang nguồn yếu khi CSPRNG lỗi

Nếu API ngẫu nhiên mật mã không khả dụng hoặc báo lỗi, không được chuyển sang timestamp, counter hay random thông thường để tiếp tục phát hành token. Hành vi phù hợp là:

1. Dừng việc tạo token cần `jti`.
2. Ghi nhận lỗi vận hành mà không để lộ dữ liệu nhạy cảm.
3. Báo lỗi an toàn và thử lại theo cơ chế được thiết kế.
4. Điều tra tình trạng entropy, nguồn ngẫu nhiên hoặc thư viện mật mã.

**Một lần phát hành token thất bại an toàn tốt hơn một token có định danh dễ đoán hoặc trùng lặp.**

## 5. Chọn độ dài và entropy

Entropy đo mức độ khó đoán của một giá trị. Với một ID ngẫu nhiên đồng đều gồm `b` bit, có `2^b` khả năng khác nhau.

Một lựa chọn phổ biến là lấy **16 byte ngẫu nhiên (128 bit)** cho mỗi `jti`. Có thể mã hóa thành Base64URL không padding, thường dài 22 ký tự, hoặc biểu diễn bằng hex (32 ký tự). Việc mã hóa chỉ thay đổi cách biểu diễn; entropy vẫn là 128 bit nếu 16 byte ban đầu được sinh ngẫu nhiên đồng đều.

Ví dụ:

~~~text
16 random bytes
       |
       v
CSPRNG (128 bits of random output)
       |
       v
Base64URL without padding
       |
       v
n9Wq7XrQv0d5aYh3c2Lk8A
~~~

Một lựa chọn khác là UUID phiên bản 4 được tạo bằng API chuẩn: UUIDv4 có 122 bit ngẫu nhiên do một số bit được dành cho version và variant. Cần dùng bộ tạo UUIDv4 dựa trên nguồn ngẫu nhiên mật mã của nền tảng, không tự lắp byte theo cách tùy ý.

Độ dài cần được chọn theo số lượng token dự kiến, vòng đời hệ thống, phạm vi duy nhất và mức rủi ro. 128 bit ngẫu nhiên thường là điểm khởi đầu thực tế tốt; hệ thống có quy mô hoặc yêu cầu đặc biệt có thể chọn mức cao hơn theo đánh giá kỹ thuật. Không nên rút ngắn ID chỉ để tiết kiệm vài byte nếu điều đó làm tăng đáng kể nguy cơ va chạm hoặc đoán được.

### 5.1. Xác suất va chạm

Với `n` giá trị được sinh độc lập, đồng đều từ không gian `2^b`, xác suất có ít nhất một cặp trùng gần đúng theo birthday bound:

\[
P(\text{collision}) \approx \frac{n(n-1)}{2^{b+1}}
\]

Khi xác suất còn nhỏ, công thức gần đúng này hữu ích để đánh giá quy mô. Ví dụ với `b = 128` và `n = 10^{12}` token được tạo trong cùng phạm vi duy nhất, xác suất va chạm xấp xỉ `1.47 \times 10^{-15}`. Con số này rất nhỏ nhưng không bằng không.

Điều cần nhớ:

- Tính toán dựa trên giả định đầu ra CSPRNG độc lập và phân bố đồng đều.
- Nếu bộ sinh ngẫu nhiên bị lỗi, entropy thấp hoặc trạng thái bị nhân bản, công thức birthday bound không còn phản ánh rủi ro thực.
- Phạm vi `n` phải là phạm vi mà hệ thống yêu cầu duy nhất, không phải chỉ số token trên một máy nếu issuer chạy nhiều node.
- Với hệ thống yêu cầu duy nhất tuyệt đối, có thể thêm unique constraint trong kho trạng thái để phát hiện va chạm; không chỉ dựa vào xác suất.

## 6. Phạm vi duy nhất trong hệ thống phân tán

Một hệ thống có thể có nhiều instance, vùng triển khai hoặc issuer cùng phát hành token. Thiết kế `jti` phải xác định rõ miền duy nhất:

- **Theo issuer:** `jti` duy nhất trong tập token do một issuer phát hành.
- **Toàn hệ thống:** mọi issuer dùng chung namespace và phải bảo đảm không trùng giữa các issuer.
- **Theo loại token hoặc giao dịch:** chỉ áp dụng khi nghiệp vụ định nghĩa rõ khóa nhận diện gồm những thành phần nào.

Trong nhiều hệ thống, khóa lưu trạng thái phù hợp là cặp `(iss, jti)`. Khi đó, hai issuer khác nhau có thể có cùng chuỗi `jti` mà không gây xung đột vì issuer là một phần của namespace. Nếu kho dữ liệu dùng `jti` làm khóa toàn cục, phải bảo đảm tính duy nhất trên toàn bộ các issuer và node.

Các cách triển khai:

1. **Random ID đủ entropy:** mỗi node dùng CSPRNG độc lập đã được khởi tạo đúng cách; không cần đồng bộ counter giữa node.
2. **ID allocator tập trung:** cấp ID duy nhất từ một dịch vụ có kiểm soát; cần đánh giá tính sẵn sàng, khả năng lộ thứ tự và việc phân vùng.
3. **Namespace kết hợp:** định danh issuer hoặc vùng được kết hợp với thành phần ngẫu nhiên; cần quy tắc chuẩn hóa và so sánh thống nhất.

Không nhân bản trạng thái PRNG đã khởi tạo giữa các tiến trình hoặc máy ảo theo cách khiến chúng phát ra cùng chuỗi giá trị. Khi môi trường được snapshot/restore, clone hoặc fork, cần dùng cơ chế ngẫu nhiên của nền tảng để tránh tái sử dụng trạng thái sinh số.

## 7. Tạo và gắn jti vào JWT

`jti` phải được tạo ở phía issuer trong quy trình phát hành. Client có thể yêu cầu một luồng hoặc resource, nhưng không được tự quyết định định danh của JWT mà issuer sẽ ký.

Quy trình cơ bản:

1. Xác định loại token/profile có yêu cầu hoặc có lợi khi dùng `jti`.
2. Lấy byte ngẫu nhiên từ CSPRNG.
3. Mã hóa thành chuỗi ổn định, không padding nếu định dạng đã chọn yêu cầu.
4. Kiểm tra giới hạn chiều dài và tập ký tự theo hợp đồng dữ liệu.
5. Tạo payload, gắn `jti` cùng các claim được máy chủ kiểm soát.
6. Nếu có kho trạng thái chống replay/thu hồi, đăng ký định danh theo thao tác nguyên tử và quy tắc nghiệp vụ.
7. Ký JWT bằng khóa và thuật toán đã cấu hình.
8. Ghi sự kiện audit cần thiết mà không ghi toàn bộ token.

Mã giả độc lập công nghệ:

~~~text
function createJti():
    randomBytes = secureRandomBytes(16)
    require randomBytes.length == 16

    identifier = base64UrlEncodeWithoutPadding(randomBytes)
    require identifier.length == 22
    require identifier contains only allowedBase64UrlCharacters

    return identifier

function issueJwt(context):
    require context.isAuthenticatedOrGrantVerified
    policy = tokenPolicy.resolve(context.tokenType, context.audience)

    claims = buildClaimsFromTrustedSources(context)
    claims.iss = policy.configuredIssuer
    claims.sub = context.verifiedSubject
    claims.aud = policy.allowedAudience

    if policy.requiresJti:
        claims.jti = createJti()

    policy.validateClaims(claims)
    return configuredJwtSigner.sign(claims)
~~~

Mã giả minh họa 16 byte đầu ra CSPRNG, sau đó mã hóa Base64URL không padding. Việc kiểm tra chiều dài chỉ là kiểm tra định dạng, không chứng minh chất lượng entropy; chất lượng đến từ nguồn ngẫu nhiên và cách triển khai API.

## 8. jti không tự động ngăn replay

Đây là điểm dễ hiểu sai nhất: **có `jti` không đồng nghĩa token không thể bị phát lại**.

Một bearer JWT hợp lệ có thể được gửi nhiều lần trong thời hạn hiệu lực. `jti` chỉ cung cấp định danh để hệ thống có thể phát hiện các lần sử dụng hoặc đánh dấu token đã bị thu hồi. Nếu resource server chỉ xác minh chữ ký, `iss`, `aud` và `exp` mà không lưu hoặc kiểm tra trạng thái `jti`, cùng một token vẫn có thể được sử dụng nhiều lần.

Các cách sử dụng `jti`:

### 8.1. Denylist để thu hồi token

Khi cần thu hồi một JWT cụ thể trước `exp`:

- Lưu cặp `(iss, jti)` vào denylist.
- Resource server kiểm tra định danh token sau khi xác minh token.
- Bản ghi denylist chỉ cần tồn tại đến khi token hết hạn (có thể cộng biên thời gian xử lý theo chính sách).
- Khi token hết hạn, bản ghi có thể được dọn tự động.

Cách này cho phép thu hồi token riêng lẻ nhưng thêm một bước truy cập trạng thái. Nếu cache hoặc replica không đồng bộ, token bị thu hồi có thể vẫn được chấp nhận ở một node. Phải thiết kế mức nhất quán phù hợp với rủi ro.

### 8.2. Chống phát lại với token dùng một lần

Với token xác nhận một hành động hoặc assertion chỉ được dùng một lần, resource server có thể đánh dấu `jti` đã sử dụng:

~~~text
function consumeOnce(verifiedClaims):
    key = (verifiedClaims.iss, verifiedClaims.jti)

    inserted = replayStore.insertIfAbsentAtomically(
        key,
        expiresAt = verifiedClaims.exp
    )

    if not inserted:
        reject("token_already_used")

    continueProtectedOperation()
~~~

Thao tác `insertIfAbsentAtomically` phải nguyên tử trên toàn bộ các node. Nếu hai request đồng thời cùng dùng một token, chỉ một request được phép chuyển trạng thái từ chưa sử dụng sang đã sử dụng.

Đối với giao dịch nghiệp vụ, cần phối hợp việc đánh dấu đã dùng và thực hiện giao dịch trong một mô hình nhất quán. Nếu đánh dấu thành công nhưng xử lý giao dịch thất bại, client retry có thể bị từ chối dù giao dịch chưa hoàn thành. Có thể cần idempotency key hoặc state machine nghiệp vụ riêng; không nên dùng `jti` để giải quyết mọi vấn đề retry.

### 8.3. Phát hiện replay cho assertion hoặc proof

Một số giao thức dùng JWT làm assertion hoặc proof cho một yêu cầu cụ thể. Trong trường hợp này, `jti` có thể là khóa tra cứu để từ chối proof đã thấy trước đó trong khoảng thời gian hiệu lực. Bên xác minh phải tuân thủ chính xác profile, phạm vi audience, thời hạn và quy tắc replay của giao thức.

### 8.4. Kết hợp với sender-constrained token

Với bearer token, ai sở hữu token có thể trình token. Sender-constrained token (ví dụ ràng buộc với khóa của client hoặc bằng chứng sở hữu) yêu cầu thêm bằng chứng rằng bên gửi có quyền kiểm soát khóa tương ứng. `jti` vẫn có thể được dùng trong cơ chế replay detection của proof, nhưng không thay thế việc xác minh bằng chứng sở hữu.

## 9. Lưu trữ và tra cứu jti an toàn

Nếu `jti` được dùng cho denylist, replay detection hoặc one-time use, cần thiết kế kho trạng thái:

| Thuộc tính | Yêu cầu |
| --- | --- |
| Khóa | Thường dùng `(iss, jti)`; bổ sung loại token/audience nếu chính sách cần namespace riêng |
| Tính nguyên tử | Insert-if-absent hoặc chuyển trạng thái phải nguyên tử để tránh hai node cùng chấp nhận |
| Thời hạn bản ghi | Không ngắn hơn khoảng thời gian token/proof có thể còn hợp lệ |
| Tính nhất quán | Phù hợp với yêu cầu chống replay/thu hồi; eventual consistency có thể tạo cửa sổ chấp nhận lại |
| Phân vùng | Có thể phân vùng theo issuer hoặc hash của định danh để mở rộng quy mô |
| Quyền truy cập | Chỉ thành phần cần thiết được đọc/ghi trạng thái; bảo vệ dữ liệu khi truyền và lưu |
| Giám sát | Theo dõi lỗi ghi, timeout, duplicate, tăng trưởng dung lượng và độ trễ đồng bộ |

Khi lưu `jti`, có thể cân nhắc lưu hash của định danh thay vì giá trị nguyên bản để giảm khả năng lộ trực tiếp ID trong bản sao dữ liệu. Việc này không biến `jti` thành bí mật và không thay thế kiểm soát truy cập kho dữ liệu. Nếu hash được dùng làm khóa, phải chuẩn hóa chuỗi nhất quán và dùng hàm băm phù hợp; không được cắt ngắn hash tùy tiện đến mức làm tăng va chạm.

Không ghi toàn bộ JWT vào log để tiện tra cứu. Audit thường chỉ cần issuer, jti, subject ở dạng được phép, audience, thời điểm, kết quả và mã tương quan. Cần cân nhắc quyền riêng tư, thời gian lưu và quyền truy cập log.

## 10. Xử lý va chạm, lỗi và retry

Xác suất va chạm với ID ngẫu nhiên đủ dài rất thấp, nhưng hệ thống vẫn nên có hành vi xác định:

1. Nếu kho dữ liệu có unique constraint và phát hiện khóa `(iss, jti)` đã tồn tại, không ghi đè bản ghi cũ.
2. Sinh một `jti` mới bằng cùng CSPRNG và thử lại với giới hạn số lần nhỏ.
3. Ghi metric/cảnh báo nếu có va chạm; nhiều va chạm có thể chỉ ra lỗi nguồn ngẫu nhiên, lỗi mã hóa hoặc trạng thái PRNG bị lặp.
4. Nếu vẫn thất bại, dừng phát hành token và báo lỗi vận hành an toàn.
5. Không trả lại token có `jti` trùng với token đã tồn tại.

Không nên retry vô hạn vì có thể che giấu lỗi nghiêm trọng hoặc làm cạn tài nguyên. Việc retry cũng phải được thiết kế sao cho không phát hành token trước khi việc đăng ký trạng thái bắt buộc hoàn tất.

Nếu hệ thống không lưu `jti` và chỉ dựa trên xác suất va chạm, có thể không cần truy vấn kho dữ liệu cho mỗi lần phát hành. Tuy nhiên, nếu nghiệp vụ yêu cầu duy nhất tuyệt đối, phải có cơ chế phát hiện va chạm hoặc allocator có bảo đảm.

## 11. Ví dụ: thu hồi và chống sử dụng lại token

Một API thanh toán nhận access token cho phép thực hiện thao tác nhạy cảm. Token có:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "service-billing",
  "aud": "https://api.example.net/payments",
  "iat": 1900000000,
  "exp": 1900000300,
  "jti": "n9Wq7XrQv0d5aYh3c2Lk8A",
  "scope": "payments:charge"
}
~~~

**Tình huống A — Thu hồi token:** phát hiện credential của workload bị lộ. Hệ thống ghi `(iss, jti)` vào denylist. Payments API xác minh chữ ký và claim, sau đó tra denylist; token bị từ chối dù `exp` chưa đến.

**Tình huống B — Token dùng một lần:** một proof JWT được phát hành cho giao dịch cụ thể. Lần đầu `jti` được chấp nhận và đánh dấu đã dùng nguyên tử. Lần thứ hai cùng proof được gửi lại, kho replay trả về trạng thái đã tồn tại và yêu cầu bị từ chối.

**Tình huống C — Token bearer thông thường:** nếu API không tra denylist, không ghi nhận replay và không yêu cầu proof ràng buộc người gửi, token có thể được dùng nhiều lần đến khi hết hạn. Chỉ thêm `jti` vào payload không thay đổi hành vi này.

## 12. Kiểm thử và vận hành

Các kiểm thử quan trọng:

- **Nguồn ngẫu nhiên:** xác minh đường gọi sử dụng API CSPRNG; lỗi nguồn ngẫu nhiên phải làm phát hành thất bại an toàn.
- **Định dạng:** `jti` có đúng kiểu chuỗi, chiều dài, encoding và không chứa ký tự không được hợp đồng cho phép.
- **Không tái sử dụng:** mỗi lần phát hành mới tạo định danh mới; refresh/reissue không sao chép `jti` cũ.
- **Phân tán:** nhiều node phát hành đồng thời không tạo va chạm quan sát được; không dùng chung trạng thái PRNG đã clone.
- **Va chạm mô phỏng:** ép kho dữ liệu trả duplicate để kiểm tra regenerate, giới hạn retry và fail-safe.
- **Denylist:** token đã thu hồi bị từ chối trên tất cả node trong thời gian đồng bộ được yêu cầu.
- **One-time use:** hai request đồng thời cùng `jti` chỉ có một request thắng thao tác consume.
- **Replay:** gửi lại token/proof theo giao thức và xác minh hệ thống chỉ chặn khi cơ chế replay state được bật.
- **Logging:** log không chứa JWT nguyên vẹn, credential hoặc dữ liệu nhạy cảm không cần thiết; jti chỉ được ghi theo chính sách audit.

Nên có metric về số lượng ID được tạo, lỗi CSPRNG, duplicate, số lần retry, số lần replay bị chặn, độ trễ truy cập kho trạng thái và số lượng bản ghi denylist. Không log đầu ra ngẫu nhiên ở mức debug trong các hệ thống nhạy cảm nếu không có lý do vận hành rõ ràng.

## 13. Những sai lầm cần tránh

- Dùng timestamp hoặc counter làm `jti` trong khi cần ID khó đoán.
- Dùng random thông thường hoặc tự viết thuật toán sinh số.
- Tạo `jti` từ subject, email, username, IP hoặc dữ liệu client.
- Tái sử dụng `jti` giữa access token, refresh token hoặc token mới được phát hành.
- Cho rằng `jti` là bí mật hoặc là một cơ chế xác thực.
- Cho rằng chỉ cần thêm `jti` thì bearer token không thể replay.
- Dùng `jti` làm idempotency key cho giao dịch mà không phân biệt vòng đời token với vòng đời yêu cầu nghiệp vụ.
- Không xác định phạm vi duy nhất khi có nhiều issuer hoặc nhiều node.
- Ghi đè bản ghi khi phát hiện va chạm.
- Dùng kho replay eventual consistency cho thao tác cần chống replay nghiêm ngặt.
- Fallback sang nguồn ngẫu nhiên yếu khi CSPRNG lỗi.
- Lưu JWT nguyên vẹn vào log hoặc cơ sở dữ liệu chỉ để tra cứu `jti`.

## 14. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa registered claim `jti` và yêu cầu định danh duy nhất trong phạm vi issuer.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các thực hành bảo mật khi sử dụng và xác minh JWT.
- [RFC 4086 — Randomness Requirements for Security](https://www.rfc-editor.org/rfc/rfc4086): yêu cầu về nguồn ngẫu nhiên trong các ứng dụng bảo mật.
- [NIST SP 800-90A Rev. 1 — Recommendation for Random Number Generation Using Deterministic Random Bit Generators](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final): khuyến nghị về DRBG.
- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): sử dụng `jti` trong assertion và kiểm soát phát lại.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): định danh proof và yêu cầu phát hiện phát lại trong cơ chế DPoP.

**Ghi nhớ:** `jti` giúp định danh một JWT cụ thể. Khi cần, hãy sinh nó bằng CSPRNG với entropy đủ lớn, xác định namespace duy nhất và quản lý trạng thái nguyên tử nếu dùng để thu hồi hoặc chống replay. `jti` tự nó không làm bearer token hết khả năng bị phát lại; hiệu quả bảo vệ chỉ xuất hiện khi issuer và bên nhận thực thi đúng cơ chế dựa trên định danh đó.

