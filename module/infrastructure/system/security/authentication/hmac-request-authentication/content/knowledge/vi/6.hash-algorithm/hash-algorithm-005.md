# Algorithm strength: đánh giá độ mạnh thuật toán khi xác thực HTTP request bằng HMAC

**Algorithm strength (độ mạnh thuật toán)** mô tả khả năng một thuật toán mật mã chống lại các dạng tấn công trong điều kiện giả định rõ ràng. Với **HMAC request authentication**, câu hỏi không chỉ là “dùng SHA-256 có đủ mạnh không?” mà còn là: shared secret có bao nhiêu bit entropy, chữ ký truyền đi dài bao nhiêu bit, verifier xác minh những byte nào, kẻ tấn công có thể thử bao nhiêu lần, và có cơ chế chống replay hay không?

Bài học thuộc chương **Hash algorithm** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Hệ thống được thiết kế để client ký **canonical HTTP request** gồm method, URI, các header và/hoặc body theo một hợp đồng ký; server dùng shared secret để xác minh chữ ký, kiểm tra timestamp/nonce, hỗ trợ key rotation và kiểm soát hành vi qua proxy/gateway. Bài này tập trung vào **độ mạnh mật mã** và cách biến các con số lý thuyết thành lựa chọn triển khai an toàn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt độ dài digest, tính kháng va chạm, tính kháng tiền ảnh và khả năng chống giả mạo HMAC.
2. Giải thích vì sao **HMAC-SHA256 không tự động chỉ có “128 bit an toàn”** chỉ vì phép tìm va chạm tổng quát đối với SHA-256 có độ phức tạp cỡ \(2^{128}\).
3. Đánh giá tác động của secret yếu, tag bị rút ngắn, thuật toán cũ, thuật toán bị hạ cấp và số lượng lần thử giả mạo.
4. Áp dụng chính sách chọn HMAC-SHA256, tạo khóa đủ entropy, kiểm tra tag đúng độ dài và sử dụng API Java JCA/JCE.
5. Kết hợp độ mạnh của HMAC với canonical request, chống replay, key rotation, xác thực proxy/gateway và phân quyền.

## 2. Trước hết phải xác định mục tiêu bảo vệ

Giả sử client dùng HMAC-SHA256 để gửi lệnh thanh toán:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: {epoch-seconds}
X-Nonce: {128-bit-random-hex}
X-Content-SHA256: {sha256-of-body}
X-Signature: {base64-of-hmac}

{"orderId":"ord-123","amount":50000}
~~~

Các giá trị trong ngoặc nhọn là **placeholder**. Mục tiêu mong muốn là kẻ tấn công **không biết shared secret** không thể tự tạo một request có chữ ký hợp lệ để đổi method, tài nguyên, số tiền, client ID hay những trường đã nằm trong hợp đồng ký.

Không nên gộp các mục tiêu bảo mật khác nhau thành một chỉ số:

| Thuộc tính | Câu hỏi đúng | HMAC có tự cung cấp? |
| --- | --- | --- |
| Tính toàn vẹn được xác thực | Có thể thay byte **đã ký** mà chữ ký vẫn được chấp nhận không? | HMAC hỗ trợ khi khóa an toàn, thuật toán đủ mạnh và canonical nhất quán. |
| Xác thực bên giữ secret | Request có thể được tạo bởi bên không có quyền sử dụng secret không? | HMAC cung cấp bằng chứng về **khả năng sử dụng secret**, không chứng minh danh tính con người. |
| Chống phát lại | Có thể gửi lại nguyên văn request đã có chữ ký hợp lệ không? | **Không**; cần timestamp và nonce được server kiểm tra/lưu. |
| Bí mật dữ liệu | Proxy nhìn thấy plaintext có đọc được body không? | **Không**; cần TLS và kiến trúc kết nối phù hợp. |
| Phân quyền | Client có được xóa tài nguyên của tenant khác không? | **Không**; cần authorization sau xác thực. |
| Tính sẵn sàng | Proxy có thể chặn hoặc trì hoãn request không? | **Không**; cần timeout, rate limit, monitoring. |

Một HMAC có độ mạnh rất cao vẫn không ngăn được việc **đổi phần request chưa được ký**, replay nguyên bản hoặc backend cấp quyền quá rộng.

## 3. Độ mạnh của hàm băm và độ mạnh của HMAC là hai câu chuyện khác nhau

Với một hàm băm mật mã \(H\), đầu vào là dãy byte tùy ý và đầu ra là digest cố định \(n\) bit. Các khái niệm thường gặp:

- **Preimage resistance:** biết digest \(h\), khó tìm một thông điệp \(m\) sao cho \(H(m)=h\).
- **Second-preimage resistance:** biết thông điệp \(m\), khó tìm một thông điệp khác có cùng digest.
- **Collision resistance:** khó tìm **bất kỳ hai** thông điệp khác nhau có cùng digest.
- **Avalanche effect:** thay ít byte đầu vào thường thay nhiều bit digest; đây là đặc điểm hữu ích, không tự nó đủ chứng minh an toàn.

Với một hàm băm lý tưởng có đầu ra \(n\) bit, ước lượng tổng quát thường được dùng để xây trực giác:

| Loại bài toán | Độ phức tạp xấp xỉ trong mô hình lý tưởng |
| --- | --- |
| Tìm tiền ảnh của digest được chọn trước | Cỡ \(2^n\) phép thử |
| Tìm tiền ảnh thứ hai | Thường cỡ \(2^n\) trong bối cảnh tổng quát đơn giản |
| Tìm một cặp va chạm bất kỳ | Cỡ \(2^{n/2}\) phép thử vì hiệu ứng birthday |

Đây là các **ước lượng lý tưởng**, không phải bằng chứng rằng mọi thuật toán hash thực tế đạt đúng các giới hạn. Tấn công cấu trúc có thể làm một thuật toán yếu hơn đáng kể.

### 3.1. Ví dụ với SHA-256

SHA-256 có digest **256 bit = 32 byte**; có thể biểu diễn thành **64 ký tự hex** hoặc **44 ký tự Base64 có padding**. Trong mô hình tổng quát lý tưởng, tìm cặp va chạm có chi phí cỡ \(2^{128}\), còn tìm tiền ảnh cỡ \(2^{256}\).

~~~text
SHA256(UTF8("abc")) =
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad

SHA256(empty body) =
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Hai chuỗi trên là **test vector công khai**, không phải secret. SHA-256(body) chỉ mô tả byte của body. Bất kỳ ai cũng tính được nó, vì vậy một header X-Content-SHA256 **không phải chữ ký xác thực** nếu chưa được ràng buộc vào HMAC.

### 3.2. Vì sao không lấy \(2^{128}\) làm độ khó giả mạo HMAC-SHA256?

HMAC dùng khóa bí mật và một kết cấu có cấu trúc; đối thủ muốn **giả mạo tag HMAC cho thông điệp mới** không chỉ cần tìm hai message có cùng hash SHA-256 thông thường. Tìm va chạm của một hash không khóa **không đồng nghĩa** đã tìm được chữ ký HMAC hợp lệ cho request mong muốn.

Với giả định primitive và khóa thích hợp, nếu hệ thống sử dụng tag HMAC đầy đủ \(t=256\) bit, một lần **đoán tag ngẫu nhiên độc lập** có xác suất trúng xấp xỉ \(2^{-256}\). Nhưng **độ an toàn tổng thể không đơn giản bằng 256 bit**: nó còn phụ thuộc entropy và bảo mật của khóa, số request/tag mà đối thủ quan sát, số lần thử online, cấu trúc HMAC, khả năng phát lại, chính sách khóa và cách verifier thực thi.

Một cách nhớ chính xác hơn:

> Độ dài digest và ngưỡng va chạm của hàm băm không phải là con số duy nhất đại diện cho độ an toàn giả mạo HMAC. Phải phân tích **MAC với khóa** theo mô hình tấn công của chính nó.

## 4. So sánh các thuật toán băm thường gặp

| Hàm băm nền | Digest | Độ phức tạp va chạm tổng quát lý tưởng | Dùng trong thiết kế HMAC request mới |
| --- | --- | --- | --- |
| MD5 | 128 bit | Ước lượng lý tưởng \(2^{64}\), nhưng MD5 có tấn công va chạm thực tế mạnh hơn nhiều | **Tránh** cho giao thức mới. |
| SHA-1 | 160 bit | Ước lượng lý tưởng \(2^{80}\), nhưng có tấn công va chạm thực tế | **Tránh** cho triển khai mới; chỉ cân nhắc legacy có chính sách kiểm soát và kế hoạch di trú. |
| SHA-256 | 256 bit | Cỡ \(2^{128}\) | **Lựa chọn mặc định hợp lý** cho HMAC request authentication. |
| SHA-384 | 384 bit | Cỡ \(2^{192}\) | Có thể dùng khi chính sách hoặc khả năng tương thích yêu cầu. |
| SHA-512 | 512 bit | Cỡ \(2^{256}\) | Có thể dùng khi hai phía thống nhất và có lý do về chính sách/hiệu năng. |

Lưu ý quan trọng: các tấn công va chạm đã biết trên **SHA-1** không tự động suy ra một cách giả mạo **HMAC-SHA1** có chi phí tương ứng. HMAC sử dụng cấu trúc có khóa nên cần đánh giá riêng. Dù vậy, một thiết kế mới vẫn nên tránh phụ thuộc SHA-1/MD5 để đơn giản hóa chính sách an toàn và khả năng bảo trì; nếu phải tương tác với hệ thống cũ, cần giới hạn phạm vi và lên kế hoạch thay thế.

Tên gọi **HmacSHA256**, **HmacSHA384** và **HmacSHA512** trong Java biểu thị **thuật toán MAC**, khác với tên hash **SHA-256**, **SHA-384**, **SHA-512** dùng bởi MessageDigest. HMAC-SHA512 có tag đầy đủ 64 byte; dài hơn không tự làm một ứng dụng an toàn hơn nếu secret dễ đoán, tag bị cắt quá ngắn hoặc request chưa được ký đủ thành phần.

Nếu chọn thuật toán khác, phải kiểm tra hỗ trợ của **cả client, verifier và cryptographic provider**, đo hiệu năng trên môi trường thực tế và ghi rõ trong hợp đồng ký. Không mặc định các thuật toán có tên tương tự là đồng nghĩa: ví dụ **HMAC-SHA512/256** sử dụng biến thể hash SHA-512/256, không tự động giống việc cắt HMAC-SHA512 xuống 256 bit.

## 5. Ba tham số thường quyết định độ mạnh triển khai

### 5.1. Entropy của shared secret

Với HMAC, secret là khóa cần **không đoán được**. Độ dài chuỗi không đồng nghĩa với entropy: một chuỗi 40 ký tự dễ đoán, ghép từ tên công ty và ngày sinh, có thể yếu hơn rất nhiều so với 16 byte ngẫu nhiên.

| Kiểu secret | Đánh giá |
| --- | --- |
| `password123`, tên dịch vụ, một UUID cố định dễ đoán hoặc secret copy công khai | Không phù hợp; có nguy cơ bị đoán hoặc lộ. |
| Secret từ mật khẩu ngắn, rồi hash bằng SHA-256 | **Không tự tạo ra entropy mới**; key vẫn có thể bị dò theo không gian mật khẩu. |
| 16 byte từ CSPRNG (128 bit entropy nếu phân bố đều) | Có thể đáp ứng một số chính sách an toàn 128 bit; cần đối chiếu mục tiêu/thời hạn bảo vệ. |
| **32 byte từ CSPRNG (256 bit entropy nếu phân bố đều)** | Giá trị mặc định thực dụng cho HMAC-SHA256 mới, cùng quản lý khóa an toàn. |
| Secret rất dài nhưng được chọn có mẫu hoặc lưu trong mã nguồn | Vẫn có thể yếu/lộ; chỉ tăng độ dài không bảo đảm an toàn. |

Trong Java dùng **SecureRandom** hoặc hệ thống quản lý khóa để tạo secret. Mã hóa khóa sang Base64 khi lưu/chuyển qua cấu hình chỉ thay **biểu diễn**, không tăng entropy. Client phải giải mã Base64 thành byte thực trước khi `Mac.init`; không được dùng nguyên các ký tự Base64 như khóa.

HMAC-SHA256 sử dụng block nội bộ 64 byte. Với key dài hơn block, thuật toán sẽ xử lý key theo định nghĩa HMAC trước khi dùng; tăng độ dài key mãi không đem lại mức an toàn tuyến tính. Một secret ngẫu nhiên 32 byte là lựa chọn phù hợp về kích thước, nhưng **quyền đọc secret, phân phối an toàn, thu hồi và key rotation** cũng quan trọng như số bit.

### 5.2. Độ dài tag được truyền

HMAC-SHA256 tạo kết quả đầy đủ **32 byte = 256 bit**. Một số giao thức chỉ truyền **phần đầu của tag** (truncation) để tiết kiệm băng thông, nhưng đó phải là **quyết định của hợp đồng ký** và được áp dụng đúng giống nhau tại client/verifier.

Giả sử giao thức cố định độ dài tag là \(t\) bit. Trong mô hình đoán tag độc lập, với \(q\) lần thử hợp lệ để kiểm tra, một trực giác đơn giản cho xác suất đoán đúng ít nhất một lần là khoảng:

\[
P(\text{forgery by guessing}) \approx \frac{q}{2^t}
\]

khi \(q\) nhỏ hơn nhiều so với \(2^t\). Đây chỉ là **giới hạn trực giác cho đoán ngẫu nhiên**, không thay thế phân tích HMAC tổng thể và không bao gồm lộ secret hoặc replay.

| Tag của HMAC-SHA256 | Độ dài | Nhận xét thiết kế |
| --- | --- | --- |
| Full tag | **256 bit, 32 byte** | Mặc định đơn giản nhất, dễ tương thích và tránh nhập nhằng cắt tag. |
| Truncated tag | **128 bit, 16 byte** | Có thể phù hợp khi giao thức **cố định rõ** độ dài và có lý do; vẫn cần bảo mật secret và giới hạn thử giả mạo. |
| Truncated tag | 64 bit, 8 byte | Không nên chọn làm mặc định cho API mới, nhất là hệ thống công khai hoặc có nhiều lượt xác minh. |
| Tag dài tùy request do client chọn | Không cố định | **Không chấp nhận**; có thể tạo đường downgrade xuống tag quá ngắn. |

Tag 16 byte được biểu diễn bằng **32 ký tự hex** hoặc **24 ký tự Base64 có padding**, khác với 16 ký tự Base64. Verifier phải kiểm tra **đúng độ dài tag theo cấu hình** trước khi so sánh. Không được chấp nhận một prefix ngắn bất kỳ của tag đầy đủ vì client tự gửi trường “tag length”.

Khi không có yêu cầu tương thích hoặc tiết kiệm đặc biệt, nên **giữ full HMAC-SHA256 32 byte**. Số byte chữ ký trong header nhỏ so với nội dung HTTP thông thường và tránh thêm bề mặt cấu hình dễ sai.

### 5.3. Số lần thử và cửa sổ phơi lộ

Một kẻ tấn công online có thể gửi nhiều request để thử chữ ký giả. **Rate limit, quota, logging cảnh báo và chặn lạm dụng** giúp giảm số lần thử online; chúng không thay thế tag đủ dài. Timestamp giới hạn tuổi thọ request đã ký và nonce store phát hiện replay, nhưng **không làm tăng số bit mật mã** của HMAC.

Khi đánh giá an toàn, cần xét lượng lưu lượng được xác minh, số client/key, tuổi thọ secret, thời gian chấp nhận timestamp, số gateway và số replica. Chỉ tăng hash từ SHA-256 lên SHA-512 sẽ không cứu một secret bị lộ hoặc một verifier bỏ qua signature ở một route.

## 6. Chọn thuật toán và ngăn hạ cấp (algorithm downgrade)

Một thiết kế an toàn cần **chính sách thuật toán do server kiểm soát**, thay vì để bên gọi chọn thuật toán yếu tùy ý.

**Cấu hình đề xuất cho một API mới:**

1. Chọn **HMAC-SHA256** làm thuật toán mặc định, tag đầy đủ 32 byte và secret 32 byte ngẫu nhiên được phân phối an toàn.
2. Gắn **client ID, key ID, algorithm/version và audience** với một bản ghi key có chính sách rõ ràng; verifier kiểm tra key đang hiệu lực, được phép cho dịch vụ/route đang xử lý.
3. Định nghĩa canonical request có **version marker** và ràng buộc các trường nhạy cảm, ví dụ method, raw path/query, body digest, timestamp/nonce và idempotency key khi cần.
4. Reject thuật toán không nằm trong allowlist, key ID không tồn tại, key đã thu hồi, tag sai độ dài và request thiếu các trường bắt buộc. **Không fallback** sang MD5/SHA-1 khi HMAC-SHA256 thất bại.
5. Khi nâng cấp thuật toán, triển khai phiên bản contract mới bằng chính sách server chủ động; chỉ chấp nhận đồng thời phiên bản cũ trong giai đoạn migration có giới hạn, có giám sát và kế hoạch thu hồi.

Ví dụ không an toàn:

~~~text
Client gửi:
  X-Algorithm: HMAC-SHA256

Server kiểm tra thất bại và thử lại HMAC-SHA1 hoặc "none" để tăng tương thích.
=> Kẻ tấn công có thể tìm đường hạ cấp/chặn kiểm tra theo lỗi cấu hình.
~~~

Thay vào đó, server có thể xác định:

~~~text
(clientId, keyId) -> {
    algorithm: HmacSHA256,
    tagBytes: 32,
    allowedAudience: payments-api,
    status: ACTIVE,
    validityWindow: ...
}
~~~

Đây là **mô hình bản ghi cấu hình**, không phải cú pháp protocol chuẩn. Từ key ID, verifier chọn đúng algorithm và secret, kiểm tra policy, rồi tạo MAC; nếu request khai báo algorithm, giá trị khai báo cũng phải nằm trong phần được bảo vệ và **khớp chính sách server**. Đổi key ID mà giữ secret cũ thường khiến chữ ký không khớp; đổi algorithm phải được điều phối đồng bộ trên cả hai phía.

## 7. HMAC mạnh vẫn cần canonical request chặt chẽ

Một hợp đồng ký tự định nghĩa minh họa:

~~~text
HMAC-V1
alg:hmac-sha256
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Hợp đồng trên định nghĩa **LF (byte 0A)** giữa mỗi dòng, **không có LF cuối**, mọi dòng được mã hóa UTF-8; body hash là SHA-256 của **body bytes thực gửi** mã hóa hex chữ thường. **alg:hmac-sha256** là một literal/field của contract, còn verifier xác định thuật toán được phép từ cấu hình key; đây không phải cơ chế client tự chọn algorithm.

Các nguyên tắc quan trọng:

- **Method và URI:** raw path + raw query phải khớp request thật được xử lý, giữ nguyên percent-encoding, thứ tự query và tham số trùng theo contract; nếu có ambiguity thì từ chối.
- **Header:** phải quy định tên header, thứ tự, whitespace và cách xử lý duplicate. Giá trị chứa CR/LF hoặc nhiều cách hiểu không được đi qua bước xác minh rồi mới xử lý tùy ý.
- **Body:** serialize JSON một lần thành byte array, hash chính byte đó rồi gửi lại đúng byte; nếu proxy nén/giải nén thì hợp đồng quy định rõ hash trước hay sau content encoding.
- **Identity/audience:** không tin X-Forwarded-Host, X-Authenticated-User hoặc X-Verified do proxy không đáng tin tự cấp; verifier sử dụng metadata được thu thập tại trust boundary và cấu hình dịch vụ.
- **Replay metadata:** timestamp và nonce cần xuất hiện trong HMAC; server phải kiểm tra cửa sổ thời gian và lưu nonce đã dùng nguyên tử. Chữ ký hợp lệ có thể bị replay **nguyên văn** nếu bỏ bước này.

Ví dụ: nếu canonical chỉ chứa **body hash**, proxy có thể thay query **currency=VND** thành **currency=USD** mà không cần phá HMAC. Đây là lỗi **phạm vi ký**, không phải SHA-256 yếu. Nếu gateway rewrite path giữa thời điểm client ký và server xác minh, phải đặt verifier ở điểm tin cậy trước rewrite hoặc thiết kế cách truyền dữ liệu gốc có xác thực, không tùy tiện bỏ path khỏi chữ ký.

## 8. Ví dụ Java 17: lựa chọn HMAC-SHA256 và xác minh đúng tag

Đoạn Java tự chứa dưới đây tạo một **secret test ngẫu nhiên 32 byte** để minh họa việc client và verifier dùng cùng key ngay trong một chương trình. Nó **không gửi HTTP request** và **không thiết lập key production**. Trong hệ thống thực, key phải được cấp qua secret manager và gắn với client/key ID; client/server không được tự sinh ngẫu nhiên một key riêng rồi mong chữ ký khớp.

Chương trình minh họa ba điều: test vector công khai của HMAC-SHA256, ký một canonical request mẫu và từ chối khi canonical bị thay đổi hoặc tag bị cắt.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacAlgorithmStrengthExample {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int FULL_TAG_BYTES = 32;
    private static final SecureRandom RANDOM = new SecureRandom();

    public static void main(String[] args) throws Exception {
        verifyPublicTestVector();

        // Secret chỉ dùng cho ví dụ một tiến trình; production dùng key store.
        byte[] sharedSecret = new byte[32];
        RANDOM.nextBytes(sharedSecret);

        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        String bodyHash = HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body)
        );

        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(Instant.now().getEpochSecond());

        // Các dòng và delimiter LF là một phần của contract ví dụ.
        String canonical = String.join("\n",
            "HMAC-V1",
            "alg:hmac-sha256",
            "POST",
            "/v1/payments?currency=VND",
            "audience:payments-api",
            "x-client-id:partner-42",
            "x-key-id:key-2026-11",
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:application/json",
            "x-content-sha256:" + bodyHash
        );

        String signatureBase64 = Base64.getEncoder().encodeToString(
            hmacSha256(sharedSecret, canonical.getBytes(StandardCharsets.UTF_8))
        );

        if (!verifyFullTag(sharedSecret, canonical, signatureBase64)) {
            throw new AssertionError("Request hợp lệ phải verify thành công");
        }
        String tampered = canonical.replace("POST", "DELETE");
        if (verifyFullTag(sharedSecret, tampered, signatureBase64)) {
            throw new AssertionError("Method đã sửa phải bị từ chối");
        }

        byte[] shortened = Arrays.copyOf(
            Base64.getDecoder().decode(signatureBase64), 8
        );
        if (verifyFullTag(sharedSecret, canonical,
                Base64.getEncoder().encodeToString(shortened))) {
            throw new AssertionError("Tag ngắn 8 byte phải bị từ chối");
        }

        System.out.println("PASS: test vector, ký đúng, chống sửa và tag length");
        // Không log secret hoặc chữ ký của request production.
    }

    static byte[] hmacSha256(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(message);
    }

    static boolean verifyFullTag(byte[] secret, String canonical,
            String suppliedBase64) throws GeneralSecurityException {
        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(suppliedBase64);
        } catch (IllegalArgumentException badEncoding) {
            return false;
        }

        // Contract cố định full HMAC-SHA256, không chấp nhận tag ngắn.
        if (supplied.length != FULL_TAG_BYTES) {
            return false;
        }
        byte[] expected = hmacSha256(
            secret, canonical.getBytes(StandardCharsets.UTF_8)
        );
        return MessageDigest.isEqual(expected, supplied);
    }

    static void verifyPublicTestVector() throws GeneralSecurityException {
        // RFC 4231, test case 1 (20 byte 0x0b, message "Hi There").
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] message = "Hi There".getBytes(StandardCharsets.US_ASCII);
        String expected = "b0344c61d8db38535ca8afceaf0bf12b"
            + "881dc200c9833da726e9376c2e32cff7";
        String actual = HexFormat.of().formatHex(hmacSha256(key, message));
        if (!expected.equals(actual)) {
            throw new AssertionError("RFC 4231 test vector không khớp");
        }
    }
}
~~~

**Lưu ý khi mang vào production:**

- Hàm `hmacSha256` là primitive: nó tính HMAC với key đã truyền vào. **Policy khóa** (key đủ entropy, key ID, audience, hiệu lực, rotation) phải được kiểm tra ở lớp gọi. Key 20 byte 0x0b của **test vector** không phải gợi ý tạo secret production.
- Verifier thực tế phải **tự dựng canonical từ HTTP request đã nhận**, chọn secret theo client ID + key ID và chính sách máy chủ; không tin một canonical string do người gửi tự khai báo.
- `MessageDigest.isEqual` giúp so sánh các byte MAC theo thời gian tương đối ổn định; code còn **bắt buộc đúng 32 byte** để không chấp nhận tag bị rút ngắn. Vẫn cần xử lý Base64 sai, request sai format, rate limit và lỗi một cách phù hợp.
- `Mac.getInstance("HmacSHA256")` không tự bật kiểm tra timestamp/nonce, phân quyền hay chống giả mạo forwarded header. Đó là logic ứng dụng.
- Ví dụ kiểm tra tag sai bằng cách đổi chuỗi canonical chỉ minh họa **tính toàn vẹn của dữ liệu đã ký**. Đây không phải test toàn diện cho parser URL, HTTP request smuggling hoặc gateway rewrite.

## 9. Đánh giá điểm yếu theo từng tầng

| Hiện tượng | Nguyên nhân trực tiếp | Có cần đổi SHA-256 thành SHA-512? |
| --- | --- | --- |
| Secret là một từ điển dễ đoán | Entropy khóa thấp; có thể brute-force offline khi đối thủ có cặp message/tag | **Không giải quyết gốc rễ.** Tạo secret ngẫu nhiên, phân phối qua kênh an toàn, rotate. |
| Verifier chấp nhận 4 byte đầu của tag | Tag quá ngắn; đoán tag dễ hơn nhiều | **Không.** Cố định độ dài tag đủ mạnh. |
| Proxy thay URI nhưng chữ ký vẫn đúng | URI không nằm trong canonical hoặc server xác minh sai biểu diễn | **Không.** Ký đúng URI và kiểm tra tại trust boundary. |
| Replay POST hợp lệ | Thiếu timestamp/nonce policy hoặc nonce store không nguyên tử | **Không.** Chống replay và idempotency. |
| Server tự fallback sang HMAC-SHA1 khi HMAC-SHA256 sai | Algorithm downgrade | **Không.** Allowlist và version/key policy chặt chẽ. |
| Key cũ bị lộ hoặc chưa thu hồi | Quản lý vòng đời key kém | **Không.** Thu hồi, đổi khóa, giới hạn audience và giám sát. |
| Bypass verifier qua endpoint backend nội bộ | Trust boundary/route bị cấu hình sai | **Không.** Đóng đường bypass, xác thực hop gateway→backend. |
| Client có chữ ký đúng nhưng truy cập tài nguyên người khác | Thiếu authorization | **Không.** Kiểm tra scope, tenant và tài nguyên. |
| Client/server tính HMAC khác nhau dù cùng key | Canonical byte, charset, newline, body encoding hoặc proxy khác | **Không.** Kiểm tra đúng byte và contract hai phía. |

Độ mạnh của thuật toán là **một lớp** trong thiết kế bảo mật. Đổi sang digest dài hơn có thể hữu ích vì chính sách, vòng đời dài hoặc yêu cầu đặc biệt, nhưng không khắc phục lỗi logic của API.

## 10. Bộ kiểm thử thực hành

Hãy xây dựng client ký và verifier trong môi trường test, dùng secret riêng không bao giờ tái sử dụng trong production. Có thể bắt đầu từ `HmacAlgorithmStrengthExample` và mở rộng sang HTTP request thực tế.

| Ca thử | Thay đổi/đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Test vector RFC 4231 | Key 20 byte 0x0b, message “Hi There” | HMAC-SHA256 bằng chuỗi hex của ví dụ. |
| Digest SHA-256 | Body “abc”, body rỗng | Khớp hai test vector ở mục 3. |
| Cùng key/canonical | Tính nhiều lần, byte hoàn toàn giống nhau | HMAC luôn giống nhau. |
| Khác một byte | Đổi method, query, body hash hoặc header đã ký | Chữ ký cũ bị từ chối. |
| Tag đầy đủ | Base64 của 32 byte HMAC-SHA256 | Được xem xét xác minh theo contract. |
| Tag rút ngắn trái phép | Base64 của 8 byte đầu, 16 byte đầu, tag rỗng | Từ chối vì độ dài không đúng chính sách full tag. |
| Base64 lỗi | Chứa ký tự không hợp lệ | Từ chối không thực thi nghiệp vụ. |
| Đổi algorithm | Header tự khai HMAC-SHA1/none, key record vẫn HmacSHA256 | Từ chối hoặc kiểm tra strict policy, tuyệt đối không fallback yếu. |
| Key rotation | Key active, key overlap được phép, key đã thu hồi | Chỉ key còn hiệu lực và đúng audience được chấp nhận. |
| Replay | Gửi nguyên request hai lần trong cửa sổ thời gian | Lần sau bị từ chối do nonce đã dùng. |
| Replay đồng thời | Hai replica nhận cùng nonce | Tối đa một lần claim nonce thành công. |
| Proxy rewrite | Đổi path, raw query, Content-Type hoặc body encoding sau ký | Không chấp nhận request có signed fields đã đổi. |
| Chênh lệch parser | Query trùng, %2F, dấu +/%20, header trùng, HTTP/2→HTTP/1.1 | Verifier và router có một cách hiểu duy nhất, hoặc từ chối request mơ hồ. |
| Thiếu quyền | HMAC hợp lệ nhưng client thao tác tenant khác | Authentication PASS, authorization DENY. |

### Bài tập phân tích

**Bài 1 — Chọn cấu hình.** Hai API đều dùng HMAC-SHA256; API A có khóa 32 byte ngẫu nhiên, full 32-byte tag và xác minh chặt. API B dùng secret “my-company-password” và full tag. API nào có rủi ro bị giả mạo cao hơn và tại sao? Việc chuyển API B sang HMAC-SHA512 có giải quyết được vấn đề chính không?

**Bài 2 — Độ dài tag.** Một đội muốn cắt HMAC-SHA256 xuống 8 byte để giảm kích thước request. Hãy phân tích khả năng đoán tag theo \(q/2^t\), quyết định cần giới hạn số lần thử ra sao và vì sao full 32 byte thường phù hợp hơn với HTTP API.

**Bài 3 — Downgrade.** Verifier đọc X-Algorithm rồi thử nhiều thuật toán cho tới khi chữ ký khớp. Hãy đề xuất chính sách chọn thuật toán theo client ID/key ID, ràng buộc phiên bản vào canonical và cách thu hồi thuật toán legacy.

**Bài 4 — Proxy.** Client HMAC đúng body, server HMAC đúng body, nhưng proxy thay currency trong query và request vẫn được chấp nhận. Đây là điểm yếu của SHA-256 hay của hợp đồng ký? Cần sửa gì ở cả client và verifier?

**Bài 5 — Replay và phân quyền.** Tại sao một POST thanh toán có HMAC hợp lệ vẫn có thể gây giao dịch trùng? Nếu client ký thành công DELETE trên đơn hàng của tenant khác, HMAC có phải cho phép thao tác không?

## 11. Checklist lựa chọn độ mạnh cho HMAC request authentication

- [ ] Có mô hình đe dọa và mục tiêu an toàn phù hợp với loại request/tài nguyên.
- [ ] Sử dụng thuật toán MAC được cho phép và hỗ trợ đồng nhất trên client/verifier; với API mới, ưu tiên **HMAC-SHA256**.
- [ ] Secret được sinh từ CSPRNG hoặc key manager; chọn đủ entropy (32 byte ngẫu nhiên là mặc định thực dụng), không hard-code hoặc dùng mật khẩu dễ đoán.
- [ ] Tag length được **cố định bằng chính sách**; mặc định dùng full HMAC-SHA256 **32 byte**, Base64 decode và so sánh byte bằng hàm phù hợp.
- [ ] Có version/algorithm allowlist; algorithm và key ID phải khớp cấu hình server; không fallback xuống thuật toán yếu khi verify lỗi.
- [ ] Canonical request bảo vệ method, URI, audience, signed headers và body bytes/hash theo đúng hợp đồng; từ chối byte/parse mơ hồ.
- [ ] Timestamp, nonce được ký và server kiểm tra replay với nonce store nguyên tử; idempotency bảo vệ side effect.
- [ ] Có key rotation, thời gian hiệu lực, cách thu hồi và phân tách key theo client/audience.
- [ ] Gateway/proxy không làm đổi ngữ nghĩa thông tin được ký, hoặc phải có điểm xác minh tại boundary đáng tin trước rewrite.
- [ ] Backend kiểm tra phân quyền sau xác thực; HTTPS, giới hạn lưu lượng và logging an toàn được triển khai riêng.

**Ghi nhớ:** Chọn **HMAC-SHA256 với secret đủ entropy và full tag** là nền tảng tốt, nhưng **độ mạnh bảo mật thực tế là tính chất của toàn bộ giao thức**. Một hash mạnh không cứu được key yếu, tag bị cắt tùy ý, thuật toán bị hạ cấp, URI/body bị bỏ khỏi canonical, request bị replay hoặc backend thiếu phân quyền.
