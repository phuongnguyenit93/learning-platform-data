# Giới hạn kích thước và phân tích cú pháp an toàn

## 1. Vì sao đây là bước bảo mật, không chỉ là xử lý chuỗi?

Trong hệ thống sử dụng **JSON Web Token (JWT)**, token đi từ trình duyệt, ứng dụng khách hoặc một dịch vụ khác vào vùng xử lý đáng tin cậy. Trước khi chữ ký được xác minh hoặc nội dung mã hóa được kiểm tra, toàn bộ chuỗi JWT là **dữ liệu do bên ngoài cung cấp**. Kẻ tấn công có thể điều khiển độ dài, số thành phần, nội dung Base64URL, JSON, JOSE header và những giá trị được dùng để tìm khóa.

Hai nhóm rủi ro xuất hiện ngay tại bước tiếp nhận:

1. **Cạn tài nguyên (denial of service):** token quá dài, JSON quá sâu, mảng quá lớn, giải nén dữ liệu phình to, chuỗi JWT lồng nhiều lớp hoặc các yêu cầu tra khóa lặp lại làm tiêu tốn CPU, bộ nhớ, mạng và thời gian xử lý.
2. **Phân tích mơ hồ:** decoder quá dễ dãi, tên thuộc tính JSON trùng nhau, kiểu dữ liệu sai, chuẩn hóa chuỗi không nhất quán hoặc cách hiểu JOSE header khác nhau có thể khiến thành phần A chấp nhận dữ liệu mà thành phần B hiểu theo nghĩa khác.

Mục tiêu của bài thuộc chương **Xác minh token** là thiết kế một lớp đầu vào JWT có **giới hạn tài nguyên rõ ràng**, **cú pháp được xử lý nghiêm ngặt**, **kết quả có thể dự đoán** và **khả năng từ chối an toàn**. Nội dung áp dụng cho JWT nói chung, độc lập với ngôn ngữ lập trình, framework hay sản phẩm xác thực.

> **Nguyên tắc xuyên suốt:** Parse thành công chỉ chứng minh dữ liệu có thể được đọc theo một định dạng; nó **không** chứng minh chữ ký đúng, issuer đáng tin cậy, token còn hiệu lực hoặc người gọi có quyền truy cập.

## 2. Hiểu chính xác cấu trúc cần tiếp nhận

JWT dựa trên bộ chuẩn JOSE. Hai dạng Compact Serialization thường gặp:

| Dạng | Cấu trúc | Điều cần chú ý |
| --- | --- | --- |
| **JWS Compact** – nội dung được ký | `protected-header.payload.signature` | Thông thường có **3 thành phần** phân tách bằng dấu chấm; header và payload của JWT được mã hóa Base64URL |
| **JWE Compact** – nội dung được mã hóa | `protected-header.encrypted-key.iv.ciphertext.tag` | Có **5 thành phần**; phải giải mã và xác thực bảo vệ mã hóa trước khi đọc plaintext |

Trong đó:

- **Protected header** là JSON được bảo vệ bởi cơ chế mật mã tương ứng, nhưng vẫn phải được **đọc sơ bộ như dữ liệu chưa tin cậy** để chọn cách xác minh.
- **Payload** của JWS chứa JWT Claims Set, hoặc là nội dung lồng bên trong theo hợp đồng đã chọn.
- **Chữ ký (signature)** hay **authentication tag** là bằng chứng mật mã cần kiểm tra; việc chuỗi có đủ ba hoặc năm phần không nói lên tính đúng đắn của bằng chứng này.
- **Nested JWT** có thể chứa một đối tượng JOSE khác ở bên trong; mỗi lớp phát sinh thêm chi phí và phải chịu giới hạn độc lập lẫn tổng thể.

Việc phân loại theo số phần chỉ là một bước **kiểm tra cú pháp rẻ và sớm**. Không dùng một bộ phân tích JWS ba phần để xử lý JWE năm phần; cũng không cố sửa token sai định dạng rồi tiếp tục.

Với JWT tuân thủ RFC 7519, không cho phép biến thể JWS **unencoded payload** sử dụng `b64=false`: RFC 7797 cấm dùng tùy chọn đó với JWT. Đối với môi trường chỉ chấp nhận JWT Compact, các dạng JOSE JSON Serialization ngoài hợp đồng phải bị từ chối ngay.

## 3. Xác định ranh giới tin cậy và luồng kiểm tra

~~~mermaid
flowchart TD
    A["Nhận dữ liệu từ request"] --> B{"Nguồn token hợp lệ, không mơ hồ?"}
    B -- "Không" --> X["Từ chối an toàn"]
    B -- "Có" --> C{"Độ dài chuỗi và số phần nằm trong giới hạn?"}
    C -- "Không" --> X
    C -- "Có" --> D["Giải mã Base64URL có hạn mức"]
    D --> E{"JOSE header là JSON hợp lệ, không mơ hồ?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Header và loại token được chính sách cho phép?"}
    F -- "Không" --> X
    F -- "Có" --> G["Xác minh chữ ký hoặc giải mã có xác thực"]
    G --> H{"Bằng chứng mật mã hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I["Giải mã/parse claims hoặc nội dung lồng, có giới hạn"]
    I --> J{"Cấu trúc, kiểu dữ liệu, dung lượng và độ sâu hợp lệ?"}
    J -- "Không" --> X
    J -- "Có" --> K["Kiểm tra issuer, audience, thời gian và hợp đồng token"]
    K --> L{"Chính sách xác minh đạt?"}
    L -- "Không" --> X
    L -- "Có" --> M["Trả về claims/ngữ cảnh token đã xác minh"]
~~~

Luồng này mô tả các chặng logic. Một thư viện có thể đọc trước một số trường để thực hiện mật mã, nhưng **không thành phần nào được dùng claims chưa xác minh để cấp danh tính hay quyền**. Đối với JWE, việc kiểm tra kích thước plaintext, giải nén và parse claims chỉ thực hiện sau khi bảo vệ mã hóa được xác thực thành công. Đối với JWS, giữ nguyên các octet đã ký để kiểm tra chữ ký; không tái tạo JSON rồi dùng chuỗi tái tạo làm đầu vào kiểm tra mật mã.

## 4. Thiết lập ngân sách kích thước nhiều lớp

Không nên chỉ đặt một giới hạn cho toàn bộ header HTTP. Sau khi giải mã Base64URL, giải mã JWE hoặc giải nén, kích thước và chi phí xử lý có thể thay đổi. Cần quản lý **nhiều ngân sách** cùng lúc.

| Lớp kiểm soát | Đối tượng phải giới hạn | Tác dụng |
| --- | --- | --- |
| Đầu vào mạng | Kích thước header, cookie, request và số trường mang token | Ngăn yêu cầu quá lớn trước khi vào bộ xác minh |
| Chuỗi JWT thô | Tổng số byte/ký tự, số thành phần, độ dài mỗi thành phần | Chặn token bất thường trước khi cấp phát bộ nhớ giải mã |
| JOSE header | Byte sau Base64URL, độ sâu JSON, số trường và độ dài các giá trị | Hạn chế thao túng thuật toán, khóa và quá tải parser |
| Payload JWS hoặc plaintext JWE | Kích thước dữ liệu sau giải mã/giải mật mã | Ngăn xử lý claims hoặc dữ liệu lồng quá lớn |
| Dữ liệu giải nén | Byte đầu ra, tỷ lệ mở rộng, CPU/thời gian | Chống **decompression bomb** nếu profile cho phép nén |
| Cấu trúc JSON | Độ sâu, số khóa, độ dài chuỗi, số phần tử mảng, độ lớn số | Chống lồng sâu, cạn bộ nhớ và sai khác kiểu dữ liệu |
| JWT lồng nhau | Số lớp, tổng lượng dữ liệu, thời gian xử lý tích lũy | Ngăn xử lý đệ quy vô hạn hoặc quá nhiều lớp |
| Xác minh và tra khóa | Số phép thử khóa, số lần làm mới JWKS, thời gian và đồng thời | Chặn tiêu thụ CPU, mạng hoặc kho khóa quá mức |

### 4.1. Ví dụ một ngân sách triển khai

Các giá trị dưới đây **chỉ để minh họa cách cấu hình**, không phải giới hạn do chuẩn JWT bắt buộc. Cần đo theo kích thước token thực tế, yêu cầu tương thích và khả năng hạ tầng.

~~~yaml
validationInputBudget:
  maxCompactTokenBytes: 16384
  maxDecodedProtectedHeaderBytes: 2048
  maxDecodedClaimsOrPlaintextBytes: 12288
  maxJsonDepth: 16
  maxJsonPropertiesPerObject: 64
  maxJsonArrayElements: 128
  maxJsonStringBytes: 4096
  maxNestedJoseLayers: 2
  compressionAllowed: false
  maxTrustedKeyCandidatesPerToken: 3
~~~

Đây là ví dụ chính sách riêng của ứng dụng, **không phải tên tham số chuẩn**. Token thực tế có thể cần hạn mức nhỏ hơn hoặc lớn hơn. Chẳng hạn, access token cho một API đơn giản thường có thể giữ rất ngắn, trong khi JWE hoặc token có chứng cứ kèm theo có thể cần dung lượng lớn hơn. Nếu nới hạn mức, phải đo tác động lên gateway, proxy, bộ nhớ, tốc độ kiểm tra chữ ký và tình huống bị tấn công.

Một số quy tắc triển khai:

1. **Từ chối trước khi cấp phát:** kiểm tra độ dài đầu vào trước thao tác `split`, Base64URL decode, parse JSON, giải mã hay kiểm tra chữ ký tốn kém.
2. **Giới hạn theo byte:** không chỉ dựa trên số ký tự Unicode vì các loại chuỗi có thể chiếm số byte khác nhau. Đối với JWT Compact, các thành phần bắt buộc phải tuân thủ bảng ký tự Base64URL; octet ngoài định dạng phải bị từ chối.
3. **Giới hạn từng đoạn:** một chuỗi có tổng độ dài hợp lệ vẫn có thể chứa protected header quá lớn hoặc payload bất thường.
4. **Giới hạn trước và sau biến đổi:** dữ liệu Base64URL có thể giải mã thành byte; plaintext sau giải mã và đặc biệt sau giải nén phải được kiểm tra lại bằng giới hạn riêng.
5. **Thống nhất các tầng:** reverse proxy, API gateway và dịch vụ xác minh cần có các giới hạn tương thích. Một tầng chấp nhận kích thước quá lớn có thể đã tiêu tốn nhiều tài nguyên trước khi tầng sau từ chối.

Ngoài độ dài, cần kiểm soát **số yêu cầu đồng thời, timeout, tải khóa, số lần thử khóa và công việc mật mã trên mỗi request**. Ví dụ, token có `kid` lạ không được kích hoạt một đợt tải JWKS không giới hạn cho từng yêu cầu.

### 4.2. Giới hạn kích thước là một hợp đồng có ngoại lệ được kiểm soát

Hạn mức quá nhỏ có thể chặn token hợp lệ sau khi bên phát hành bổ sung claims; hạn mức quá lớn mở rộng bề mặt DoS. Cách thiết kế bền vững là:

- Đo phân bố kích thước token hợp lệ tại các điểm tích hợp.
- Ưu tiên phát hành token tối giản, tránh nhúng dữ liệu hồ sơ hoặc danh sách quyền quá dài nếu không cần thiết.
- Cấu hình hạn mức theo **loại token và endpoint**, không dùng một ngưỡng rất lớn cho tất cả.
- Xác định ai được đổi hạn mức, cách kiểm thử tương thích và cách theo dõi số lần bị từ chối vì vượt giới hạn.

Không tự động **cắt ngắn (truncate)** một JWT quá dài để cố phân tích. Cắt bớt byte sẽ thay đổi thông điệp và có thể gây hành vi mơ hồ; đầu vào vượt chính sách phải bị từ chối nguyên vẹn.

## 5. Tiếp nhận token từ HTTP hoặc kênh truyền khác một cách nghiêm ngặt

Một hệ thống có thể nhận JWT qua `Authorization: Bearer <token>`, cookie hoặc kênh đã định nghĩa. Bước trích xuất phải có quy tắc độc lập với việc parse JWT:

- **Chỉ nhận đúng vị trí đã cấu hình.** Không âm thầm lấy token từ URL, body hoặc cookie khi endpoint chỉ hỗ trợ Authorization header.
- **Chặn đầu vào mơ hồ.** Nhiều `Authorization` header, nhiều bearer value, cookie trùng tên hay token đồng thời nằm ở hai nguồn phải có chính sách xử lý rõ ràng; lựa chọn an toàn thường là từ chối.
- **Phân tích đúng cú pháp cơ chế mang token.** Không tìm chuỗi `Bearer` tùy tiện giữa header rồi cắt phần phía sau; kiểm tra tên scheme, dấu phân cách, khoảng trắng, ký tự điều khiển và chuỗi rỗng theo hợp đồng HTTP.
- **Không tự sửa dữ liệu đáng ngờ.** Không bỏ ký tự lạ, tự ghép các đoạn bị tách, bỏ qua dấu xuống dòng hoặc tự giải mã nhiều lần để token “có vẻ hợp lệ”.
- **Dùng kênh vận chuyển an toàn.** TLS giúp bảo vệ bearer token; không đưa token vào URL vì dễ bị lưu trong lịch sử, log, referrer hoặc hệ thống giám sát.

Ví dụ đầu vào đáng từ chối trước khi đến JOSE parser:

~~~http
Authorization: Bearer token-A
Authorization: Bearer token-B
~~~

Nếu hai tầng hạ tầng xử lý header trùng nhau khác nhau (một tầng lấy giá trị đầu, tầng khác lấy giá trị cuối), hệ thống có thể đưa ra quyết định trái ngược. Một chính sách trích xuất nhất quán giúp tránh trường hợp này.

## 6. Kiểm tra Compact Serialization và Base64URL

Sau khi đã có **một** chuỗi JWT và đã qua giới hạn tổng thể, tiến hành kiểm tra dạng biểu diễn.

### 6.1. Số thành phần và ký tự

Với JWS Compact, phải có đúng **3** thành phần; với JWE Compact là **5** thành phần. Số dấu chấm phải tương ứng với dạng đã cho phép. Những thành phần bắt buộc không được rỗng. Một số thành phần JWE như `encrypted-key` có thể rỗng theo thuật toán quản lý khóa cụ thể, nên không được áp dụng luật “mọi phần đều khác rỗng” cho toàn bộ JWE.

Đối với các thành phần được mã hóa Base64URL:

- Chỉ chấp nhận bảng ký tự tương ứng với Base64URL và quy tắc mã hóa của JOSE; không tùy tiện nhận `+`, `/`, dấu cách, xuống dòng hoặc các biến thể Base64 khác.
- Từ chối padding `=` nếu profile sử dụng dạng JOSE Base64URL không padding.
- Kiểm tra độ dài bất hợp lệ, ví dụ độ dài Base64URL có phần dư **1 khi chia cho 4** là không thể giải mã đúng.
- Sử dụng decoder **nghiêm ngặt**, không im lặng bỏ qua ký tự lạ; khi cần bảo đảm biểu diễn chuẩn tắc, có thể kiểm tra encode ngược dữ liệu đã giải mã để phát hiện cách biểu diễn không chuẩn.
- Giữ nguyên chuỗi gốc và đúng các octet đã được ký. Không giải mã rồi encode lại protected header/payload để tạo signing input mới khi xác minh JWS.

Số phần hợp lệ và Base64URL hợp lệ **chưa đủ** để chấp nhận JWT. Đây chỉ là điều kiện cần để parser làm việc an toàn.

### 6.2. Giới hạn từng thành phần trước khi giải mã

Vì Base64URL làm tăng độ dài biểu diễn, nên cần tính hoặc ước lượng kích thước đầu ra trước khi cấp phát buffer. Khi thành phần mã hóa đã quá dài, từ chối trước khi giải mã; sau khi giải mã vẫn kiểm tra byte thật để áp dụng giới hạn nội dung.

Đối với JWE, phải xem xét riêng kích thước `encrypted-key`, `iv`, `ciphertext` và `tag` theo thuật toán đã cho phép. Không đánh giá ciphertext như JSON, và không cố đọc claims từ một chuỗi ciphertext chưa được giải mã có xác thực.

## 7. Phân tích JOSE header an toàn

JOSE header là điểm quyết định cách xác minh token, nhưng các trường trong header vẫn **chưa đáng tin cậy cho tới khi cơ chế mật mã thành công**. Parser cần kiểm tra:

1. Protected header giải mã thành **JSON object hợp lệ**, dùng UTF-8 hợp lệ; không phải mảng, số hoặc chuỗi JSON.
2. Không có tên thuộc tính trùng nhau. Ví dụ hai khóa `alg` có thể khiến parser thứ nhất chọn giá trị đầu, parser thứ hai chọn giá trị cuối.
3. Mỗi trường có đúng kiểu: `alg`, `kid`, `typ`, `cty` thường là chuỗi; `crit` là mảng tên trường theo quy tắc JOSE. Giới hạn độ dài chuỗi và số phần tử.
4. Từ chối tham số `crit` không được hiểu hoặc không được phép. Các tham số quan trọng phải được xử lý theo đúng đặc tả, không chỉ lưu để hiển thị.
5. `alg` nằm trong danh sách thuật toán **đã định nghĩa sẵn** cho endpoint và issuer; không cho token tự quyết định chính sách.
6. `kid` chỉ dùng để tra trong **bộ khóa tin cậy đã được gắn với issuer**; giới hạn độ dài và không biến `kid` thành đường dẫn, truy vấn hoặc URL chưa được kiểm soát.

Ví dụ header nguy hiểm vì trùng thuộc tính:

~~~json
{
  "alg": "RS256",
  "kid": "trusted-key",
  "alg": "none"
}
~~~

Ngay cả khi một thư viện JSON cho phép trùng khóa, ứng dụng vẫn nên **từ chối** để tránh khác biệt xử lý giữa các thành phần. Với trường `alg: none`, một API yêu cầu JWT có chữ ký phải từ chối theo chính sách. Không chấp nhận chuyển từ xác minh bất đối xứng sang HMAC chỉ vì `alg` khai báo thuật toán khác.

Các trường có thể dẫn tới truy cập tài nguyên bên ngoài như `jku` hoặc `x5u` không được khiến bộ xác minh tự động tải URL nằm trong token. Nếu một profile thực sự dùng chúng, phải có nguồn tin cậy, danh sách cho phép, kiểm soát mạng, giới hạn kích thước phản hồi và cache riêng. Tương tự, khóa `jwk` được nhúng trong header không tự trở thành khóa đáng tin cậy.

Trường `typ` (loại token) và `cty` (loại nội dung lồng) cũng phải được ràng buộc với profile thực tế. Khi hệ thống quy định endpoint chỉ nhận JWT access token, không thể bỏ qua khác biệt giữa access token và ID token.

## 8. Parse JSON Claims Set mà không tạo cách hiểu mâu thuẫn

Đối với **JWS**, thư viện xác minh chữ ký trên nội dung JWS gốc; sau khi chữ ký hợp lệ mới sử dụng claims làm đầu vào tin cậy. Đối với **JWE**, phải giải mã và xác thực trước khi parse plaintext, sau đó xử lý token lồng nếu hợp đồng yêu cầu.

### 8.1. Cấu trúc và kiểu dữ liệu

JWT Claims Set phải là **JSON object**. Cần áp dụng parser JSON có hạn mức tài nguyên và chính sách rõ ràng:

- Từ chối JSON không hợp lệ: thiếu dấu đóng, ký tự điều khiển sai, escape không hợp lệ, dữ liệu thừa sau object hoặc UTF-8 không hợp lệ.
- Từ chối tên thuộc tính trùng; không dựa vào quy tắc “lấy khóa đầu” hay “lấy khóa cuối”.
- Giới hạn độ sâu của object/array, số thuộc tính trong object, số phần tử mảng và kích thước mỗi chuỗi.
- Không tự chuyển mọi chuỗi thành số, boolean hay ngược lại. Claim phải được kiểm tra đúng kiểu theo chuẩn và profile.
- Từ chối giá trị số không hữu hạn hoặc không biểu diễn được an toàn trong kiểu dữ liệu đã chọn, và phát hiện tràn số khi tính toán thời gian.
- Không âm thầm cắt bớt chuỗi hay mảng quá dài rồi coi kết quả là claim gốc.

Ví dụ sai kiểu:

~~~json
{
  "iss": "https://issuer.example.org/",
  "aud": {"service": "payments"},
  "exp": "1893456000",
  "sub": ["user-123"]
}
~~~

Theo hợp đồng JWT thông thường, `aud` phải là **chuỗi hoặc mảng các chuỗi**, `exp` là **JSON number** theo NumericDate và `sub` là **chuỗi**. Parser có thể đọc được JSON trên, nhưng bộ xác minh phải từ chối vì kiểu dữ liệu không phù hợp. NumericDate là số giây tính từ mốc Unix và **có thể chứa phần lẻ**, không được mặc định coi đó là mili giây hoặc tự chuyển chuỗi sang số.

### 8.2. Đồng nhất cách hiểu giữa các dịch vụ

Các thành phần cùng xử lý một JWT cần thống nhất về:

- Bộ giải mã UTF-8 và quy tắc từ chối byte sai.
- Cách phát hiện khóa JSON trùng và cấu trúc quá sâu.
- Cách xử lý tên claim và giá trị chuỗi: tránh chuẩn hóa Unicode, thay đổi chữ hoa/chữ thường, thêm hoặc bỏ dấu `/` trong URL theo suy đoán.
- Cách kiểm tra `iss`, `aud`, `sub`, `exp`, `nbf`, `iat` và những claims riêng của profile.
- Cách biểu diễn số lớn, số thực, số âm và giới hạn của đồng hồ.

Một JWT có thể được **parse** hợp lệ nhưng vẫn bị **từ chối** vì sai issuer, audience, thời điểm hoặc mục đích sử dụng. Kiểm tra cú pháp, xác minh mật mã và kiểm tra claims là những bước liên tiếp có nhiệm vụ khác nhau.

## 9. Những điểm đặc biệt của JWE, dữ liệu nén và JWT lồng nhau

### 9.1. Không xử lý plaintext trước khi xác thực bảo vệ mã hóa

Một JWE có thể dùng cơ chế mã hóa có xác thực để bảo vệ nội dung. Bên nhận phải kiểm tra thuật toán và khóa được phép, xác thực thành công cơ chế bảo vệ mật mã rồi mới sử dụng plaintext. Tùy hợp đồng, plaintext có thể là Claims Set hoặc một JWS/JWE lồng bên trong; mã hóa thành công **không tự động chứng minh issuer** nếu nhiều bên có thể tạo ciphertext hợp lệ.

Đối với input JWE lớn, đặt giới hạn cho ciphertext và các phần phụ trợ **trước** phép giải mã; sau đó đặt giới hạn cho plaintext **trước** khi parse hoặc xử lý lớp lồng.

### 9.2. Tránh decompression bomb

JOSE có tham số `zip` dành cho một số trường hợp JWE. Dữ liệu nén nhỏ có thể phình rất lớn sau giải nén. Chính sách an toàn là **không bật giải nén nếu không cần thiết**.

Nếu tích hợp bắt buộc cho phép nén:

1. Chỉ chấp nhận giá trị `zip` được profile cho phép và chỉ xử lý khi phần header đã được bảo vệ, kiểm tra đúng quy trình JOSE.
2. Đặt **giới hạn byte đầu ra của bộ giải nén**; dừng ngay khi vượt, không chờ giải nén toàn bộ rồi mới đo.
3. Đặt ngân sách CPU/thời gian và có thể giới hạn tỷ lệ mở rộng; giới hạn theo byte đầu ra là điều kiện quan trọng nhất.
4. Sau giải nén, áp dụng lại giới hạn kích thước, độ sâu JSON và các giới hạn xử lý lớp lồng.

### 9.3. Giới hạn mức lồng

Ví dụ một JWT được ký có thể được mã hóa thành JWE; sau khi giải mã, bên nhận phải xác minh JWS bên trong theo đúng chính sách. Không cho nội dung tự khai báo `cty: JWT` kích hoạt xử lý đệ quy vô hạn.

Thiết kế nên có giới hạn **số lớp JOSE tối đa**, **tổng số byte xử lý qua các lớp** và **ngân sách thời gian**. Mỗi lớp phải được kiểm tra riêng về loại serialization, thuật toán, khóa, cú pháp và bằng chứng mật mã. Khi vượt giới hạn, từ chối toàn bộ token.

## 10. Mã giả cho bộ tiếp nhận và phân tích cú pháp

Đoạn mã sau mô tả **các bước logic** bằng ngôn ngữ trung lập. Các hàm Base64URL, JSON, JWS/JWE phải đến từ thư viện tiêu chuẩn được duy trì và được cấu hình để xử lý nghiêm ngặt.

~~~text
function acceptJwtFromRequest(request, endpointPolicy):
    rawToken = extractExactlyOneAllowedToken(request)
    require rawToken exists
    require byteLength(rawToken) <= endpointPolicy.maxCompactTokenBytes
    require rawToken has no illegal whitespace or control characters

    parts = splitCompactSegmentsWithBoundedAllocation(rawToken)
    require partCount(parts) is allowed by endpointPolicy
    require each segment's encoded size is within its budget

    protectedHeaderBytes = strictBase64UrlDecodeBounded(parts[0])
    require byteLength(protectedHeaderBytes) <= maxProtectedHeaderBytes
    header = strictJsonObjectParse(
        protectedHeaderBytes,
        rejectDuplicateNames = true,
        budget = endpointPolicy.jsonBudget
    )
    require header matches endpointPolicy.allowedJoseHeaders
    require header.alg is explicitly allowed for this token profile
    require all critical headers are understood and permitted

    trustedKeys = endpointPolicy.preconfiguredTrustedKeys
    key = selectBoundedTrustedKeyCandidate(trustedKeys, header.kid, header.alg)
    require key is permitted for the requested cryptographic operation

    if partCount(parts) == 3:
        require endpointPolicy.allowsSignedJwt
        require decodedPayloadSizeEstimate(parts[1]) <= maxClaimsBytes
        require verifyJwsWithOriginalSigningInput(rawToken, key)
        claimsBytes = strictBase64UrlDecodeBounded(parts[1])
        claimsOrNestedToken = strictParseClaimsOrNestedJwt(
            claimsBytes, endpointPolicy
        )

    else if partCount(parts) == 5:
        require endpointPolicy.allowsEncryptedJwt
        require jweComponentsMatchApprovedAlgorithmAndSizes(parts, header)
        plaintext = authenticatedJweDecryptBounded(parts, key)
        require byteLength(plaintext) <= maxPlaintextBytes
        plaintext = decompressOnlyIfApprovedAndBounded(plaintext, header)
        claimsOrNestedToken = strictParseClaimsOrNestedJwt(
            plaintext, endpointPolicy
        )

    else:
        reject

    verifiedClaims = validateRequiredClaimsAndTokenContract(
        claimsOrNestedToken, endpointPolicy
    )
    return ValidatedTokenContext(verifiedClaims, endpointPolicy.id)
~~~

Trong mã giả, `strictParseClaimsOrNestedJwt` phải áp dụng **ngân sách lồng, độ sâu và kích thước**; khi là nested JWT, nó tiếp tục xác minh lớp bên trong trước khi trả về claims. Với JWE, logic `authenticatedJweDecryptBounded` bao gồm các kiểm tra mật mã bắt buộc theo thuật toán. Với JWS, `verifyJwsWithOriginalSigningInput` không được xác minh bằng JSON đã serialize lại.

Đây là lớp nhận token và kiểm tra hợp đồng, **không phải toàn bộ cơ chế phân quyền**. Khi có `ValidatedTokenContext`, ứng dụng vẫn phải quyết định người gọi có được thực hiện hành động trên tài nguyên cụ thể hay không.

## 11. Các tình huống thực tế cần phân biệt

Giả sử API chỉ chấp nhận JWS Compact với một issuer và tập thuật toán cố định, có hạn mức 16 KiB cho toàn token, 2 KiB cho protected header và 12 KiB cho claims sau giải mã.

| Tình huống | Hành vi mong đợi | Vì sao |
| --- | --- | --- |
| Token dài 200 KiB | Từ chối **trước khi giải mã** | Vượt giới hạn chuỗi thô |
| Token có 4 thành phần, trong khi endpoint chỉ nhận JWS Compact | Từ chối | Sai số thành phần của dạng được phép |
| Một thành phần chứa ký tự `+`, dấu xuống dòng hoặc Base64URL không hợp lệ | Từ chối | Không thuộc biểu diễn JWT Compact được chấp nhận |
| Header JSON có hai trường `alg` | Từ chối | Cách hiểu thuật toán có thể mơ hồ |
| Header có `kid` dài hàng nghìn ký tự hoặc chỉ đến URL ngoài | Từ chối hoặc bỏ qua khả năng truy vấn ngoài theo chính sách | Ngăn làm quá tải parser, tra khóa hoặc mạng |
| Chữ ký hợp lệ nhưng payload chứa mảng 100.000 phần tử | Từ chối theo giới hạn claims | Chữ ký đúng không loại bỏ rủi ro cạn tài nguyên |
| `exp` là chuỗi `"1893456000"` | Từ chối | Sai kiểu NumericDate |
| JWE nén có ciphertext nhỏ nhưng giải nén thành hàng trăm MB | Dừng tại giới hạn byte giải nén | Chống decompression bomb |
| JWE lồng nhiều lớp vượt chính sách | Từ chối | Vượt số lớp và ngân sách xử lý |
| Token hợp lệ về cấu trúc nhưng chữ ký không đúng | Từ chối | Parse hợp lệ không có nghĩa là được xác minh |
| Token qua kiểm tra cú pháp và mật mã nhưng sai `aud` | Từ chối | Không dành cho API này |

Nếu token được nhận qua một gateway và chuyển tiếp sang dịch vụ khác, cần bảo đảm cả hai có cách hiểu thống nhất về chuỗi JWT gốc, giới hạn kích thước và chính sách từ chối. Không nên để một thành phần âm thầm chỉnh sửa/chuẩn hóa token trước khi chuyển cho thành phần khác.

## 12. Kiểm thử và quan sát an toàn trong vận hành

### 12.1. Ma trận kiểm thử bắt buộc

| Nhóm | Ca kiểm thử điển hình |
| --- | --- |
| Ranh giới kích thước | 0 byte, đúng bằng hạn mức, vượt 1 byte, chuỗi rất dài, header nhỏ nhưng claims quá lớn, dữ liệu sau giải nén vượt hạn |
| Trích xuất nguồn | Thiếu token, hai Authorization header, nhiều cookie cùng tên, token nằm ở nguồn không được phép, ký tự điều khiển |
| Compact/Base64URL | Thiếu/thừa dấu chấm, thành phần không hợp lệ, padding không được phép, ký tự ngoài bảng chữ cái, độ dài Base64URL bất hợp lệ |
| JSON | JSON rỗng/sai root, thuộc tính trùng, JSON quá sâu, mảng lớn, chuỗi dài, UTF-8 sai, escape sai, dữ liệu thừa |
| JOSE header | `alg` sai kiểu, `alg: none`, thuật toán khác allowlist, `kid` quá dài, `crit` không hiểu, nguồn khóa không tin cậy |
| Claims | `aud` sai kiểu, `exp` là chuỗi, số quá lớn gây tràn, `iss` khác chính sách, `nbf` ở tương lai |
| JWE/nested | Ciphertext hỏng, authentication tag sai, JWE có tham số không hỗ trợ, giải nén phình lớn, vượt độ sâu lồng |
| Tải và kháng DoS | Nhiều token lỗi đồng thời, nhiều `kid` lạ, JWKS chậm, timeout, bộ nhớ và CPU đạt ngưỡng kiểm soát |

Nên dùng **fuzz testing** cho bộ đọc Base64URL/JSON/JOSE và thử nghiệm khác biệt parser khi hệ thống dùng nhiều ngôn ngữ/thư viện. Bài kiểm thử phải xác nhận không có trường hợp lỗi cú pháp bị chuyển thành “token hợp lệ” hoặc gây ứng dụng dừng đột ngột. Với giới hạn thời gian, kiểm thử nên đo thời gian và số tài nguyên tiêu thụ trong điều kiện có tải.

### 12.2. Lỗi, log và chỉ số giám sát

Khi đầu vào sai, trả về lỗi theo giao thức API, thường là lỗi xác thực khi JWT không hợp lệ; với header quá lớn, một tầng HTTP có thể chặn yêu cầu sớm bằng lỗi phù hợp của tầng đó. Bên nhận **không cần tiết lộ** token sai ở byte nào, đang dùng khóa nào hoặc thuật toán chi tiết trong phản hồi công khai.

Thay vì ghi nguyên JWT, hệ thống có thể ghi các dữ kiện ít nhạy cảm như:

- Mã nguyên nhân: `TOKEN_TOO_LARGE`, `INVALID_BASE64URL`, `INVALID_JOSE_HEADER`, `DUPLICATE_JSON_MEMBER`, `UNSUPPORTED_ALGORITHM`, `INVALID_SIGNATURE`, `CLAIMS_TOO_LARGE`.
- Độ dài token hoặc nhóm độ dài, số lần vượt ngưỡng, số yêu cầu bị từ chối, thời gian parse/xác minh và số lần làm mới khóa.
- ID request và ngữ cảnh dịch vụ được phép đưa vào log theo chính sách bảo vệ dữ liệu.

Không ghi access token, cookie, header Authorization đầy đủ, private key, secret hoặc những claims nhạy cảm. Những giá trị từ token **chưa xác minh** phải được coi là dữ liệu không đáng tin cậy ngay cả trong log để tránh log injection hoặc dữ liệu giả mạo gây hiểu lầm.

## 13. Checklist triển khai

Trước khi đưa bộ xác minh JWT vào vận hành, xác nhận:

1. [ ] Điểm tiếp nhận chỉ đọc token từ nguồn đã cho phép và từ chối trường hợp trùng hoặc mơ hồ.
2. [ ] Có giới hạn **tổng byte JWT**, **độ dài từng thành phần** và **byte sau giải mã**.
3. [ ] Định dạng JWS/JWE được lựa chọn theo chính sách; parser không tự suy đoán rồi sửa đầu vào sai.
4. [ ] Base64URL được giải mã nghiêm ngặt, không bỏ qua ký tự lạ hoặc tự chuẩn hóa nội dung đã ký.
5. [ ] JOSE header và claims được parse với giới hạn JSON, từ chối trường trùng và sai kiểu.
6. [ ] Thuật toán và nguồn khóa được ràng buộc trước; `kid`, `jku`, `x5u` không tự mở rộng vùng tin cậy.
7. [ ] JWE, giải nén và JWT lồng nhau có giới hạn riêng, giới hạn tổng và trình tự xác thực mật mã đúng.
8. [ ] Chữ ký/bảo vệ mật mã, issuer, audience, thời gian và loại token được xác minh đầy đủ trước khi chấp nhận claims.
9. [ ] Bộ xác minh từ chối an toàn khi gặp lỗi định dạng, lỗi tài nguyên, lỗi khóa, lỗi mạng hoặc timeout.
10. [ ] Có kiểm thử ranh giới, fuzzing, theo dõi tài nguyên và log không tiết lộ dữ liệu nhạy cảm.

## 14. Tài liệu tiêu chuẩn để đối chiếu

- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT, JWT Claims Set và quy tắc claims chuẩn.
- **RFC 7515 — JSON Web Signature (JWS):** Compact Serialization, protected header và quy tắc xác minh chữ ký.
- **RFC 7516 — JSON Web Encryption (JWE):** Compact Serialization, mã hóa, giải mã và tham số `zip`.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn và lựa chọn khóa phù hợp.
- **RFC 7797 — JSON Web Signature (JWS) Unencoded Payload Option:** quy tắc liên quan đến `b64`, bao gồm giới hạn dùng với JWT.
- **RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format:** định dạng, kiểu dữ liệu, khả năng tương tác và các vấn đề JSON mơ hồ.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành bảo mật JWT, thuật toán, nguồn khóa, issuer/audience và phân biệt loại token.

**Thông điệp cốt lõi:** Không một lớp kiểm tra riêng lẻ nào đủ để tin JWT. **Giới hạn kích thước bảo vệ tài nguyên; parser nghiêm ngặt bảo vệ sự nhất quán; xác minh mật mã và hợp đồng claims mới tạo ra kết quả tin cậy.**
