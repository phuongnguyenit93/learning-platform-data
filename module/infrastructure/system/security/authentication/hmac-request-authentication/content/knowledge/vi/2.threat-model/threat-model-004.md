# Kẻ tấn công đoán secret

> **Chương:** Mô hình đe dọa  
> **Bối cảnh:** Xác thực HTTP request bằng HMAC với khóa bí mật dùng chung (shared secret). Hai bên ký và kiểm tra một canonical request gồm phương thức, URI, header và/hoặc body theo hợp đồng đã thống nhất. Bài học phân tích cách kẻ tấn công đoán secret, tác động tới xác thực, chống replay, key rotation, proxy/gateway và phân quyền.

## 1. Vấn đề an ninh cần nhận diện

HMAC-SHA-256 là thuật toán xác thực thông điệp đã được nghiên cứu rộng rãi. Tuy nhiên, **dùng đúng HMAC không bảo đảm an toàn nếu khóa HMAC có thể đoán được**. Một hệ thống có thể canonical hóa hoàn hảo, sử dụng HTTPS, kiểm tra timestamp và nonce, nhưng vẫn cho phép giả mạo request nếu secret được đặt là `secret123`, một từ trong từ điển, hoặc một chuỗi được tạo theo quy luật dễ suy ra.

Trong mô hình HMAC request authentication, client và server cùng giữ secret `K`. Client ký thông điệp `M` là biểu diễn canonical của yêu cầu HTTP:

\[
T = \operatorname{HMAC\text{-}SHA256}(K, M).
\]

Client gửi request cùng `T`; server tìm secret gắn với danh tính/key ID, dựng lại `M` và đối chiếu HMAC. Nếu đối chiếu thành công, server xác nhận bên gửi **biết khóa tương ứng**, còn các thành phần được ký giữ nguyên tính toàn vẹn.

Điểm yếu xuất hiện khi attacker có thể tìm được `K` từ một tập ứng viên nhỏ. Khi đó attacker có thể tự dựng **request hoàn toàn mới**, timestamp mới, nonce mới rồi tạo chữ ký đúng. Replay protection chỉ phát hiện việc phát lại request cũ; nó không ngăn được người đã biết secret tạo request mới.

Sau bài học, người học cần:

1. Phân biệt **đoán khóa** với **đánh cắp khóa**, **thử chữ ký ngẫu nhiên** và **phát lại request**.
2. Mô tả rõ tài sản, năng lực attacker, ranh giới tin cậy và điều kiện cho đoán secret **offline/online**.
3. Giải thích vì sao độ mạnh của secret phụ thuộc vào **entropy**, không phụ thuộc vào độ dài chuỗi biểu diễn.
4. Chọn các biện pháp bảo vệ phù hợp ở khâu sinh khóa, cấp phát, lưu trữ, xác minh, key rotation và giám sát.
5. Thiết kế được ca kiểm thử chứng minh các kiểm soát hoạt động qua API gateway/proxy và không nhầm xác thực với phân quyền.

## 2. Secret có vai trò gì trong hợp đồng ký HMAC?

Xét yêu cầu tạo giao dịch:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: payments.example
Content-Type: application/json
X-Client-Id: partner-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: HNeiUCs4uf4IT7rbF9HUJQ
X-Signature: <base64url-hmac-tag>

{"source":"acct-01","destination":"acct-02","amount":150000}
~~~

Một hợp đồng minh họa có thể chọn ký các thành phần theo thứ tự:

~~~text
hmac-v1
POST
/v1/transfers?currency=VND
application/json
partner-17
key-2026-11
1795824000
HNeiUCs4uf4IT7rbF9HUJQ
<sha256-hex-cua-raw-body>
~~~

Trong ví dụ, các giá trị `<...>` là ký hiệu minh họa, không phải chữ ký/digest đã tính. Hợp đồng thực phải quy định rõ encoding UTF-8, dấu xuống dòng, thứ tự trường, cách chuẩn hóa header, raw URI, body, thuật toán và cách encode tag.

**Những gì attacker thường có thể biết:**

- Phương thức, URI, body hoặc bản sao các thành phần này khi quan sát được một request hợp lệ trong log/bản ghi mạng/thiết bị đầu cuối.
- Các header `X-Client-Id`, `X-Key-Id`, `X-Timestamp`, `X-Nonce` và `X-Signature` nếu nắm được bản sao request đã ký.
- Quy tắc canonical hóa và thuật toán HMAC: hệ thống **không được dựa vào việc giấu thuật toán hoặc thứ tự trường** làm nền tảng bảo mật.

**Những gì attacker chưa có trong bài toán đoán khóa:** byte secret thật đang được quản lý bởi client và server. `clientId` hay `keyId` chỉ là định danh, không phải secret. Timestamp và nonce cũng không phải secret; chúng bảo vệ tính mới của request.

Nếu attacker biết một cặp `(M, T)` hợp lệ, họ có thể thử các secret ứng viên và so HMAC tạo ra với `T` ngay trên máy mình. **Không cần tương tác với API server cho từng ứng viên**, vì HMAC là phép tính có thể thực hiện độc lập khi đã biết thông điệp và tag.

## 3. Mô hình đe dọa: tài sản, đối thủ, ranh giới

### 3.1. Tài sản cần bảo vệ

| Tài sản | Hệ quả khi bị xâm phạm |
|---|---|
| Secret HMAC của từng client | Giả mạo danh tính client và ký request mới |
| Ràng buộc `clientId → keyId → secret → audience` | Dùng nhầm khóa giữa đối tác, môi trường hoặc dịch vụ |
| Canonical request và chữ ký | Nhận diện request bị sửa đổi hoặc giả mạo |
| Timestamp, nonce và kho chống replay | Ngăn dùng lại một request hợp lệ trong cửa sổ thời gian |
| Quyền API và dữ liệu nghiệp vụ | Hạn chế hành động của principal đã xác thực |
| Log, metric, kênh cấp phát khóa | Không làm lộ dữ liệu đủ để phục hồi hoặc chiếm secret |

### 3.2. Năng lực và giả định của attacker

Mô hình cơ sở giả định attacker **không biết secret ban đầu**, nhưng có thể:

- Xem tài liệu API và định dạng ký; gọi API công khai hoặc gửi nhiều request không hợp lệ.
- Nhìn thấy một request hợp lệ cùng tag HMAC, chẳng hạn từ log bị chia sẻ sai quyền, hệ thống giám sát hoặc một thành phần tích hợp do attacker kiểm soát.
- Tự tạo các secret ứng viên, tính HMAC offline và thử gửi request giả khi cho rằng đã tìm đúng secret.
- Khai thác các quy luật yếu trong quá trình cấp phát khóa: khóa cố định theo môi trường, khóa suy từ tên khách hàng, thời gian tạo, số thứ tự hoặc passphrase dễ nhớ.

Các khả năng như lấy trộm secret từ vault, đổ bộ nhớ, chiếm CI/CD hoặc đọc cấu hình client là **những nhánh đe dọa liên quan nhưng khác với đoán secret**. Khi kiểm soát bị phá do rò rỉ trực tiếp, attacker không cần brute force; xử lý sự cố vẫn có nhiều biện pháp chung như thu hồi khóa và truy vết.

### 3.3. Ranh giới tin cậy

~~~mermaid
flowchart LR
    C["Client hợp lệ<br/>giữ secret"] -->|"HTTPS + request đã ký"| G["API gateway<br/>vùng tiếp nhận"]
    G -->|"raw/canonical request theo hợp đồng"| V["HMAC verifier<br/>kiểm tra chữ ký"]
    V --> K[("Key store<br/>clientId + keyId")]
    V --> N[("Nonce store<br/>atomic + TTL")]
    V --> A["Authorization<br/>principal + tài nguyên"]
    X["Attacker<br/>biết request + tag"] -->|"Tính thử HMAC offline"| D["Tập secret ứng viên"]
    D -->|"Nếu đoán trúng khóa"| F["Tự ký request mới"]
    F -->|"Gửi request giả"| G
~~~

Hợp đồng ký xác định request được bảo vệ **tại điểm nào**: ngay ở gateway hay tại service phía sau. Nếu proxy biến đổi path, query, header hoặc body trước khi xác minh, cả client lẫn verifier cần dùng quy tắc nhất quán; nếu không, chữ ký có thể thất bại dù secret mạnh. Rủi ro canonicalization là một nhánh lỗi riêng, nhưng có thể làm các biện pháp chống giả mạo mất tác dụng.

### 3.4. Mục tiêu của attacker

1. **Spoofing:** được hệ thống công nhận là `partner-17` khi thực tế không nắm quyền hợp pháp của đối tác đó.
2. **Tampering:** thay đổi phương thức, URI, số tiền hoặc đối tượng hưởng lợi rồi tạo HMAC hợp lệ bằng khóa đã đoán.
3. **Lạm dụng quyền được cấp:** yêu cầu giao dịch hoặc đọc dữ liệu mà tài khoản đối tác có quyền, gây hậu quả tài chính hoặc rò rỉ dữ liệu.
4. **Che giấu nguồn gốc:** khiến log quy kết hành vi cho client bị giả mạo. HMAC dùng shared secret nên không tự cung cấp bằng chứng pháp lý kiểu chữ ký số bất đối xứng.

Phân quyền sau xác thực có thể giới hạn phạm vi gây hại; nó không sửa được việc định danh client bị chiếm qua một secret yếu.

## 4. Hai cơ chế đoán secret cần phân biệt

### 4.1. Đoán offline khi đã biết một request và HMAC hợp lệ

Giả sử hệ thống cấp secret theo quy ước nội bộ `merchant-<mã đối tác>-<năm>`. Đây là bí mật về mặt tổ chức nhưng có **không gian ứng viên nhỏ** vì định dạng, mã đối tác và năm có thể suy đoán.

Khi attacker lấy được một cặp request đã ký hợp lệ, quá trình tấn công về mặt khái niệm là:

~~~text
Thông tin đã biết:
    M = canonical bytes của request hợp lệ
    T = HMAC tag hợp lệ gắn với M

Với mỗi secret ứng viên Ki từ tập ứng viên nhỏ:
    tính Ti = HMAC-SHA256(Ki, M)
    so sánh Ti với T
    nếu trùng: đã xác định được ứng viên phù hợp với quan sát

Sau khi tìm được secret:
    tạo request mới M2 với timestamp/nonce mới
    tạo tag T2 = HMAC-SHA256(secret, M2)
~~~

Vì phép thử `Ti == T` xảy ra **ngoài hệ thống**, các biện pháp sau **không ngăn được vòng đoán offline**:

- Rate limit số request hoặc số lỗi `401` ở gateway.
- Giới hạn cửa sổ timestamp của request đã quan sát.
- Kho nonce chống replay; nonce cũ đã dùng không làm mất khả năng kiểm tra ứng viên khóa trên máy attacker.
- Ẩn thông báo lỗi của server (dù đây vẫn là thực hành nên làm với đường tấn công online).

HTTPS giúp hạn chế khả năng người ngoài quan sát request trên đường truyền, nhưng không thay thế entropy của khóa. Một client được cấp secret yếu và tự nhìn thấy các request của mình có thể thử khóa offline, bất kể HTTPS.

Với HMAC-SHA-256 đầy đủ 256 bit và secret ngẫu nhiên đủ mạnh, không có phương pháp thực tế nào được biết để đoán đúng secret bằng cách liệt kê không gian khóa. Rủi ro chủ đạo là **secret yếu do cách tạo hoặc vận hành**, chứ không phải một phép phá HMAC-SHA-256 tổng quát.

### 4.2. Đoán online khi chỉ có quyền gọi API

Nếu attacker **chưa có** cặp `(M, T)` hợp lệ để kiểm tra ứng viên offline, họ có thể tạo request, ký bằng một khóa đoán thử và gửi lên server. Server có thể chấp nhận hoặc từ chối. Mỗi lần thử đòi hỏi tương tác với hệ thống:

~~~text
attacker -> API: request + HMAC đoán bằng secret ứng viên
API -> attacker: accept / reject
~~~

Ở nhánh này, rate limit theo client/nguồn, quota, WAF, giám sát lỗi xác thực và phản hồi lỗi thống nhất **có ích để giảm số lần thử và phát hiện bất thường**. Tuy nhiên, nếu một cặp `(M, T)` bị lộ sau đó, attacker có thể chuyển sang offline ngay lập tức.

### 4.3. Không nhầm đoán secret với các kiểu tấn công khác

| Kiểu tấn công | Attacker cần gì? | Vì sao khác nhau? |
|---|---|---|
| **Đoán secret** | Không gian khóa đủ nhỏ, có kênh kiểm tra ứng viên offline/online | Khôi phục hoặc xác định secret từ tập ứng viên |
| **Đánh cắp secret** | Quyền đọc vault, biến môi trường, file, bộ nhớ, log hoặc thiết bị client | Lấy trực tiếp secret, không phải brute force |
| **Đoán tag ngẫu nhiên** | Thử một giá trị MAC bất kỳ | Với tag đủ dài, mỗi lần thử độc lập có xác suất thành công cực nhỏ; không cần phục hồi khóa |
| **Replay** | Bản sao request + tag từng hợp lệ | Gửi lại byte cũ; timestamp/nonce và idempotency là tuyến phòng thủ riêng |
| **Lỗi canonical hóa** | Khác biệt cách hiểu giữa client, gateway và verifier | Tận dụng sự không nhất quán của những thành phần được ký |
| **Lỗi phân quyền** | Principal đã được xác thực nhưng được cấp quyền sai | Có thể xảy ra ngay cả khi secret mạnh và HMAC được verify chính xác |

## 5. Entropy mới quyết định khả năng đoán khóa

**Entropy của secret** phản ánh mức độ không thể dự đoán nó trước khi được cấp, chứ không chỉ là số ký tự. Nếu có `N` khóa khả dĩ với xác suất gần như đều nhau, độ bất định xấp xỉ:

\[
H = \log_2(N)\ \text{bit}.
\]

Ví dụ, một PIN gồm sáu chữ số có khoảng `10^6` lựa chọn, tương đương xấp xỉ 19,9 bit. Nếu người dùng còn ưu tiên các mẫu quen thuộc, entropy thực tế có thể thấp hơn. Một chuỗi dài 40 ký tự lặp đi lặp lại theo quy luật vẫn có entropy thấp.

| Ví dụ vật liệu khóa | Không gian đoán lý tưởng | Đánh giá khi dùng làm HMAC shared secret |
|---|---|---|
| PIN 4 chữ số | `10^4 ≈ 2^13,3` | Rất yếu |
| PIN 6 chữ số | `10^6 ≈ 2^19,9` | Rất yếu |
| Passphrase do người tự chọn | Phụ thuộc hành vi và từ điển thực tế | Không có bảo đảm entropy; thường không phù hợp |
| 16 byte sinh độc lập, đồng đều bằng CSPRNG | `2^128` | Mạnh đối với đa số mục tiêu bảo mật hiện nay |
| **32 byte sinh độc lập, đồng đều bằng CSPRNG** | **`2^256`** | **Lựa chọn chuẩn thực dụng cho HMAC-SHA-256** |
| 32 byte toàn giá trị `00` | Chỉ một giá trị nếu quy luật được biết | Cực kỳ yếu dù dài 32 byte |

Các con số `2^128` hay `2^256` chỉ đúng khi mỗi bit được sinh ngẫu nhiên đủ tốt và secret không bị lộ. **Base64/Base64URL và hex chỉ là cách biểu diễn byte**, không tạo thêm entropy: mã hóa 32 byte ngẫu nhiên thành chuỗi Base64URL 43 ký tự vẫn có tối đa 256 bit entropy; một chuỗi 43 ký tự được tạo bằng mẫu có sẵn không tự trở thành khóa 256 bit.

### 5.1. Minh họa chi phí thử khóa

Giả sử attacker có thể tính và đối chiếu **một triệu HMAC mỗi giây** trên môi trường minh họa. Không tính chi phí chuẩn bị và giả sử tất cả ứng viên gần như đồng xác suất:

| Không gian ứng viên | Số lần thử tối đa | Thời gian tối đa ở tốc độ minh họa |
|---|---:|---:|
| 4 chữ số | `10^4` | `0,01` giây |
| 6 chữ số | `10^6` | `1` giây |
| 8 chữ số | `10^8` | `100` giây |
| 128 bit ngẫu nhiên | `2^128` | Khoảng `1,1 × 10^25` năm |
| 256 bit ngẫu nhiên | `2^256` | Khoảng `3,7 × 10^63` năm |

Đây là **phép tính quy mô**, không phải benchmark hay dự báo thời gian tấn công một hệ thống cụ thể. Phần cứng, tính song song, entropy thực tế và cách attacker ưu tiên ứng viên có thể thay đổi mạnh thời gian với các khóa yếu. Không nên cố “làm chậm HMAC” để sửa một secret yếu: HMAC được thiết kế để tính nhanh, nên biện pháp bền vững là **sinh khóa ngẫu nhiên đủ entropy**.

### 5.2. Độ dài tag khác với độ mạnh secret

Nếu server dùng đầy đủ tag HMAC-SHA-256 256 bit và attacker chỉ đoán tag ngẫu nhiên, xác suất thành công cho mỗi thử lý tưởng xấp xỉ `2^-256`. Nhưng nếu secret thực tế chỉ có khoảng `2^20` khả năng, attacker có thể thử **khóa** thông qua cặp `(M,T)` trước, thay vì đoán trực tiếp tag 256 bit. Bởi vậy:

> Một MAC dài 256 bit **không bù được** cho secret chỉ có 20 bit entropy.

Không tùy ý cắt ngắn tag nếu hợp đồng chưa quy định và đánh giá an ninh. Tag bị rút ngắn làm tăng xác suất giả mạo trực tiếp và có thể khiến việc xác nhận các ứng viên khóa khó phân biệt hơn. Cấu hình minh họa trong bài dùng **toàn bộ 32 byte HMAC-SHA-256**.

## 6. Các nguồn tạo ra secret có thể đoán

### 6.1. Sinh khóa có quy luật

Những mẫu cần loại bỏ:

~~~text
secret = "merchant-" + clientId
secret = environment + "-" + currentYear
secret = sha256(clientId)
secret = md5(username + timestamp)
secret = "CHANGE_ME"
secret = randomFromPredictableSeed(System.currentTimeMillis())
~~~

Hash một thông tin dễ đoán không làm thông tin đó có thêm entropy. Kẻ tấn công chỉ cần áp dụng cùng công thức cho các ứng viên. Không dùng `java.util.Random`, timestamp hoặc bộ đếm làm nguồn ngẫu nhiên để cấp phát khóa bảo mật.

### 6.2. Khóa dài nhưng có mẫu cố định

Một secret như `AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` dài 32 ký tự nhưng có thể bị đoán ngay. Một UUID phiên bản 4 thường có khoảng 122 bit ngẫu nhiên; không nên dùng nó làm thay thế mặc định cho **32 byte CSPRNG** khi chính sách yêu cầu khóa HMAC-SHA-256 256 bit.

### 6.3. Dùng chung khóa hoặc lấy từ môi trường mẫu

Một shared secret dùng cho nhiều client hoặc dùng lại giữa staging và production có thể làm phạm vi ảnh hưởng tăng mạnh. Việc lộ khóa ở sandbox, code mẫu, image Docker, pipeline hoặc tài khoản thử nghiệm có thể mở đường ký request cho môi trường quan trọng. Trường hợp đó là **rò rỉ khóa**, nhưng nó thường bắt nguồn từ chính sách cấp phát/luân chuyển khóa yếu.

### 6.4. Secret do con người chọn

Password và passphrase có tính dự đoán cao hơn khóa ngẫu nhiên. Nếu bài toán bắt buộc đầu vào do người chọn, một password KDF có salt và chi phí tính toán (ví dụ Argon2id) có thể làm việc đoán offline tốn kém hơn, nhưng **không tự biến mật khẩu yếu thành khóa có entropy cao**. Với API HMAC giữa các hệ thống, giải pháp ưu tiên là cấp secret ngẫu nhiên qua kênh an toàn.

## 7. Biện pháp phòng thủ theo vòng đời khóa

### 7.1. Tạo khóa bằng CSPRNG, bảo đảm nguồn entropy

- Sinh ít nhất **32 byte ngẫu nhiên** cho mỗi secret HMAC-SHA-256 theo chính sách ví dụ; dùng `SecureRandom` của Java hoặc API KMS/secret manager chuyên dụng.
- Cấp **khóa độc lập theo client, dịch vụ/audience và môi trường**; không derive từ `clientId`, email, ngày tạo, hostname hoặc tên tenant.
- Nếu cần derive khóa con từ **master secret đã có entropy cao**, dùng KDF có phân tách ngữ cảnh (chẳng hạn HKDF theo RFC 5869 với `info` khác nhau cho từng audience), quản lý master key chặt chẽ. HKDF không làm một password dễ đoán trở nên mạnh.
- Gắn bản ghi khóa với `clientId`, `keyId`, thuật toán, quyền sử dụng, thời gian hiệu lực và trạng thái. `keyId` chỉ là nhãn để chọn khóa, không phải một phần secret.

**Ví dụ Java 17+:**

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacKeyExample {
    private static final SecureRandom RNG = new SecureRandom();

    private HmacKeyExample() {}

    /** Tạo secret mới bằng CSPRNG. Bên gọi đưa ngay vào kho bí mật. */
    public static byte[] generateSecret() {
        byte[] key = new byte[32]; // 256 bit
        RNG.nextBytes(key);
        return key;
    }

    /** Base64URL chỉ là encoding cho kênh cấp phát; không thêm entropy. */
    public static String encodeForProvisioning(byte[] secret) {
        if (secret == null || secret.length != 32) {
            throw new IllegalArgumentException("Secret phải có 32 byte");
        }
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(secret);
    }

    public static byte[] hmac(byte[] secret, byte[] canonicalRequest)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32
                || canonicalRequest == null) {
            throw new IllegalArgumentException("Khóa hoặc request không hợp lệ");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalRequest);
    }

    /** Đối chiếu tag 32 byte đã được giải mã từ header chữ ký. */
    public static boolean verify(byte[] secret, byte[] canonicalRequest,
                                 byte[] receivedTag)
            throws GeneralSecurityException {
        if (receivedTag == null || receivedTag.length != 32) return false;
        byte[] expectedTag = hmac(secret, canonicalRequest);
        return MessageDigest.isEqual(expectedTag, receivedTag);
    }

    // Ví dụ gọi ở bước cấp phát nội bộ (không in secret ra console/log):
    public static void exampleProvisioning() {
        byte[] key = generateSecret();
        try {
            String encoded = encodeForProvisioning(key);
            // Truyền "encoded" tới secret manager qua kênh bảo vệ và kiểm soát quyền.
            // Không ghi vào source code, URL, telemetry hoặc tài liệu công khai.
            // String không thể xóa khỏi heap một cách bảo đảm.
        } finally {
            Arrays.fill(key, (byte) 0);
        }
    }
}
~~~

Đoạn code minh họa **khâu sinh khóa và kiểm tra MAC thuần túy**, không phải HTTP authentication filter hoàn chỉnh. Trước khi gọi `verify`, hệ thống vẫn phải tra đúng khóa theo `(clientId, keyId)`, xác định canonical request, xác minh timestamp/nonce, giới hạn kích thước đầu vào và kiểm tra phân quyền. Với chữ ký Base64URL, verifier phải kiểm tra cú pháp, độ dài byte và encoding canonical trước khi đối chiếu. Xóa mảng byte sau sử dụng giúp giảm lưu giữ bản sao nhưng không bảo đảm đã xóa mọi bản sao trong JVM.

### 7.2. Cấp phát và lưu trữ bí mật an toàn

Secret phải được cấp qua kênh được xác thực/mã hóa, thường bằng quy trình provisioning được kiểm soát hoặc secret manager. Không đưa secret vào tài liệu API dùng chung, URL, query string, frontend JavaScript, ứng dụng không đáng tin cậy, repository, email thông thường, log hay ảnh chụp màn hình.

Chỉ thành phần có nhiệm vụ ký hoặc verify mới được đọc khóa; hạn chế quyền của service account và audit hoạt động đọc/cập nhật secret. Mã hóa secret khi lưu trữ, giữ secret của từng client tách biệt, ưu tiên KMS/vault với cơ chế rotation/revocation rõ ràng. Key ID và metadata có thể xuất hiện trong log đã làm sạch; **giá trị secret không được xuất hiện**.

### 7.3. Verifier bắt buộc ràng buộc khóa với identity và audience

~~~text
clientId, keyId -> record khóa được cấp phát trước
record -> trạng thái hiệu lực + audience + thuật toán + secret
raw request -> canonicalRequest theo hợp đồng ký
expectedTag -> HMAC-SHA256(secret, canonicalRequest)
so sánh tag -> principal đã xác thực
principal + action + resource -> authorization decision
~~~

Không lấy secret từ header, body hoặc query do client tự đưa vào. Không dùng một secret mặc định khi lookup `keyId` thất bại. Không “thử mọi khóa của mọi client đến khi có một chữ ký khớp” rồi tự suy principal: cách đó tạo nguy cơ nhầm identity, làm phức tạp thu hồi và mở rộng bề mặt lỗi. Nếu cần overlap lúc rotation, chỉ thử **các version khóa được gắn đúng với principal và phạm vi**, theo hợp đồng và chính sách.

Sau khi dựng canonical request, so sánh hai tag bằng hàm có đặc tính chống timing leak như `MessageDigest.isEqual` với byte array đã kiểm tra độ dài. Không log tag kỳ vọng; không tiết lộ server chọn khóa nào qua phản hồi lỗi quá chi tiết. Các bước này chống lỗi triển khai và lộ thông tin; chúng **không thay thế secret có entropy cao**.

### 7.4. Timestamp, nonce và replay protection vẫn phải có

Secret mạnh không ngăn attacker phát lại request đã ghi được. Ngược lại, timestamp và nonce **không chặn được attacker đã đoán được secret**, vì kẻ đó tạo chữ ký mới cho timestamp và nonce mới.

Một chính sách minh họa:

~~~text
Kiểm tra timestamp đã ký: |serverTime - signedTime| <= 300 giây
Kiểm tra HMAC:           expectedTag == receivedTag (so sánh byte an toàn)
Lưu nonce sau HMAC đúng: SET unique(clientId, keyId, nonce) NX EX 600
Yêu cầu nonce chưa tồn tại: chỉ request đầu được đi tiếp
~~~

TTL cần đủ che phủ toàn bộ thời gian request còn có thể hợp lệ; với cửa sổ ±300 giây, TTL khoảng 600 giây từ thời điểm tiếp nhận đầu là một lựa chọn minh họa. Nonce store phải chia sẻ giữa các node, hỗ trợ ghi nguyên tử và thất bại theo chính sách fail-closed khi không thể xác minh tính mới. Với thao tác tạo/sửa có tác động lâu dài, bổ sung `Idempotency-Key` ở tầng nghiệp vụ để tránh giao dịch nhân đôi; key này nên được ký nếu ảnh hưởng tới hành vi request.

### 7.5. Phân quyền hạn chế phạm vi thiệt hại

Một request có HMAC đúng chỉ có nghĩa client nắm được khóa tương ứng. Hệ thống vẫn phải kiểm tra client có quyền với `POST /v1/transfers`, tài khoản nguồn và khoản tiền cụ thể hay không. Nếu attacker đoán được khóa của merchant A, họ không được tự ý thao tác tài nguyên của merchant B. Phân quyền theo nguyên tắc ít quyền nhất và kiểm tra sở hữu tài nguyên giúp giảm thiệt hại khi secret bị lộ hoặc bị đoán.

## 8. Key rotation và phản ứng khi nghi ngờ khóa yếu

Giả sử hệ thống đang dùng secret theo mẫu dễ đoán. **Chỉ thêm timestamp, đổi nonce, đổi thuật toán hash hoặc đổi tên key ID không khắc phục được khóa yếu.** Cần thay bằng khóa mới được cấp bằng CSPRNG và thu hồi khả năng xác thực của khóa cũ.

| Trạng thái khóa | Mục đích | Cách xử lý trong verifier |
|---|---|---|
| `ACTIVE` | Khóa hiện hành để client ký | Chấp nhận xác minh nếu đúng client/audience và còn hiệu lực |
| `VERIFY_ONLY` | Giai đoạn ngắn xử lý request đang chuyển tiếp | Chỉ verify trong cửa sổ thời gian giới hạn; không cho phép tiếp tục sử dụng vô thời hạn |
| `REVOKED` | Khóa đã bị thu hồi hoặc nghi ngờ lộ | Từ chối hoàn toàn, kể cả HMAC đúng |

**Rotation định kỳ có kiểm soát:** phát hành `keyId` mới và secret độc lập; cập nhật phía client; cho phép overlap ngắn đúng principal; theo dõi chuyển đổi; thu hồi bản cũ sau khi hết hạn. Vì người nắm khóa cũ vẫn có thể ký request mới trong giai đoạn overlap, nên cần thời hạn chấp nhận cụ thể, hạn mức và giám sát; `VERIFY_ONLY` không phải một biện pháp mật mã ngăn người giữ khóa ký.

**Khi có dấu hiệu secret bị đoán/lộ:**

1. Đánh giá các client/key ID bị ảnh hưởng và vô hiệu hóa hoặc thu hồi khóa nguy hiểm theo mức độ khẩn cấp; không kéo dài overlap thông thường nếu đã có nguy cơ chiếm quyền.
2. Cấp secret mới độc lập bằng CSPRNG qua kênh xác thực; cập nhật kho khóa và phía client.
3. Rà soát request, giao dịch, audit trail trong khoảng thời gian khóa có thể đã bị xâm phạm; kiểm tra hành vi bất thường ngoài phạm vi merchant.
4. Điều tra nguyên nhân: công thức sinh khóa, rò rỉ config, log, pipeline, quyền truy cập secret, reuse khóa giữa môi trường.
5. Sửa nguồn sinh/cấp khóa, loại bỏ khóa mẫu và kiểm thử lại quy trình rotation/revocation; bổ sung cảnh báo và quy trình tái cấp phát.

Không giả định có thể phát hiện mọi lần đoán offline: kẻ tấn công có thể thử hàng triệu ứng viên trên hệ thống riêng mà server không có bất kỳ log lỗi nào. Chỉ khi họ dùng khóa đã tìm được để gọi API, các tín hiệu về nguồn, thời gian, khối lượng hoặc hành vi nghiệp vụ mới có khả năng xuất hiện.

## 9. Kiểm thử threat model trên hệ thống thực tế

Kiểm thử nên phân biệt hai mục tiêu: **ngăn tạo khóa có thể đoán** và **bảo đảm các lớp khác không khuếch đại thiệt hại khi khóa bị lộ**.

| Ca kiểm thử | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Quy trình sinh khóa | Kiểm tra mã/nguồn entropy và chính sách cấp phát | Secret được tạo bằng CSPRNG; không derive từ dữ liệu dự đoán được |
| Secret mặc định/giá trị mẫu | Thử provision với `CHANGE_ME`, khóa ngắn hoặc khóa cố định | Quy trình cấp phát từ chối hoặc cấm theo chính sách |
| Khóa đúng, request nguyên vẹn | Ký canonical bytes đúng bằng secret đã cấp | Xác thực thành công, sau đó mới xét quyền |
| Secret sai | Ký cùng canonical bằng khóa khác | `401`; không tiết lộ MAC kỳ vọng hoặc secret |
| Client ID/key ID không tương ứng | Ký bằng khóa client A nhưng khai client B | Từ chối; không chọn nhầm principal |
| Thay method, path, query, body | Sửa một thành phần đã ký sau khi ký | MAC không khớp, từ chối |
| Header trùng hoặc ký không canonical | Gửi hai `X-Key-Id` hoặc nhiều `X-Signature` | Từ chối định dạng mơ hồ |
| Replay cùng nonce | Gửi lại request hợp lệ trong cửa sổ | Chỉ bản đầu được reserve nonce |
| Attacker biết secret cũ | Tự ký request mới với key ID đã `REVOKED` | Từ chối dù chữ ký HMAC đúng |
| Khóa của staging trên production | Dùng secret môi trường test để ký production request | Từ chối do tách môi trường/audience |
| Auth hợp lệ nhưng sai phạm vi | Gọi tài nguyên merchant khác | `403` hoặc mã từ chối phân quyền theo hợp đồng |
| Rate limit online | Gửi nhiều MAC không hợp lệ từ nguồn thử nghiệm | Throttling/cảnh báo phù hợp; không làm rò rỉ secret |
| Proxy rewrite path | Gửi request qua gateway có biến đổi URI | Client và verifier thống nhất canonical hoặc từ chối nhất quán |
| Lỗi nonce store | Ngắt tạm kết nối kho nonce trong môi trường test | Fail closed; không âm thầm bỏ kiểm tra replay |

**Giới hạn của kiểm thử entropy:** Chạy vài bài kiểm tra thống kê trên chuỗi secret đã sinh không đủ chứng minh CSPRNG an toàn. Cần kiểm tra **nguồn sinh, cấu hình, quy trình cấp phát và việc không tái sử dụng khóa**. Việc thấy chuỗi Base64 dài hoặc không tìm thấy khóa trong một danh sách từ điển cũng không chứng minh đủ entropy.

### 9.1. Kiểm thử qua gateway và nhiều node

Một bài integration test mẫu:

1. Client tạo body byte-for-byte, canonical method + raw URI + signed headers + body digest; ký với khóa test mạnh được cấp riêng.
2. Gửi request qua đúng chuỗi gateway/WAF/proxy như production; so kết quả với đường vào trực tiếp nếu có.
3. Thử `%2F` so với `/`, thay thứ tự query, query parameter trùng, thay đổi `Content-Type`, header ký có khoảng trắng khác nhau và body JSON khác whitespace.
4. Gửi hai request có cùng nonce đến **hai node verifier** đồng thời; bảo đảm chỉ một request vượt qua replay check.
5. Xoay `keyId` đang dùng, cho phép overlap ngắn, rồi revoke; bảo đảm việc xác minh thay đổi đúng theo trạng thái khóa.
6. Đảm bảo identity sau xác thực được chuyển qua ranh giới mạng nội bộ bằng cơ chế đáng tin; header nhận diện client không được bên ngoài tự ghi đè.

Nếu gateway rewrite request, có thể xác minh HMAC ở edge **trước khi** biến đổi hoặc sử dụng một nguồn raw target gốc do proxy đáng tin bảo vệ. Không tin `X-Forwarded-*`/`X-Original-URI` do request ngoài internet tự cung cấp.

### 9.2. Quan sát và cảnh báo

Theo dõi tỷ lệ lỗi chữ ký theo nhóm client/key ID đã làm sạch, số lần `401` tăng đột ngột, nonce trùng, timestamp skew bất thường, thử dùng khóa đã thu hồi, tỷ lệ lỗi nonce store, và các giao dịch trái với hành vi thường ngày. Có thể đặt ngưỡng alert trên số lần thất bại theo phút hoặc theo tỷ lệ baseline thực tế; không có một ngưỡng dùng chung phù hợp cho mọi hệ thống.

Log chỉ nên có request ID, principal/key ID không nhạy cảm, nguyên nhân lỗi dạng mã phân loại và metadata tối thiểu. **Không log raw shared secret, dữ liệu cấp phát khóa, HMAC kỳ vọng, authorization header nhạy cảm hay body chứa dữ liệu cá nhân**. Cần hiểu rõ: giám sát server hữu ích cho online guessing và hành vi sau xâm phạm nhưng gần như không nhìn thấy quá trình đoán **offline**.

## 10. Câu hỏi thường bị hiểu sai

**“Tag HMAC dài 256 bit thì secret ngắn vẫn an toàn?”** Không. Attacker có cặp canonical request/tag có thể thử tất cả secret khả dĩ offline. Độ dài MAC không làm tăng entropy của secret.

**“Đã sử dụng HTTPS nên không ai có thể đoán khóa?”** HTTPS hạn chế nghe lén trên đường truyền; nó không thay đổi cách khóa được tạo và không bảo vệ khóa nằm trong log/client cấu hình sai.

**“Có nonce ngẫu nhiên rồi thì không thể giả mạo?”** Nonce bảo vệ chống phát lại. Người biết khóa có thể tạo nonce mới và ký request mới. Nonce không phải khóa.

**“Giới hạn mỗi IP 10 request/phút sẽ chặn brute force?”** Chỉ giảm thử online qua server, và vẫn có thể bị né bằng phân tán nguồn. Không chặn phép thử offline dựa trên request/tag đã biết.

**“Tăng độ dài secret bằng cách băm nhiều lần có đủ?”** Không nếu dữ liệu gốc dễ đoán. Hash không tạo entropy; KDF cho password chỉ tăng chi phí đoán, còn secret HMAC API nên sinh ngẫu nhiên.

**“Rotation là đã xử lý xong secret yếu?”** Rotation chỉ an toàn khi khóa mới có entropy mạnh, khóa cũ hết hiệu lực đúng lúc và cách sinh khóa yếu được loại bỏ. Đổi key ID mà giữ nguyên secret không giải quyết nguy cơ.

**“HMAC hợp lệ nghĩa là được phép thực hiện giao dịch?”** Không. HMAC phục vụ **authentication** và bảo vệ phần được ký; **authorization** kiểm tra principal được phép thực hiện thao tác trên tài nguyên cụ thể hay không.

## 11. Bài tập phân tích tình huống

**Tình huống A — Khóa có cấu trúc:** Dịch vụ thanh toán cấp secret theo quy tắc `"pay-" + merchantId + "-" + year`. Một dashboard hỗ trợ hiển thị request và `X-Signature` của một thanh toán thành công. Hãy xác định attacker có thể đoán offline hay online, tài sản nào bị xâm phạm và ba thay đổi ưu tiên nhất để giảm rủi ro.

**Gợi ý:** Đây là tập ứng viên nhỏ; cặp thông điệp và tag hỗ trợ kiểm tra offline. Ưu tiên thay cách sinh khóa bằng CSPRNG, rotation/revoke khóa cũ và loại bỏ việc hiển thị/log các giá trị nhạy cảm.

**Tình huống B — Gateway và nonce:** Client ký `POST /api/v1/orders`, gateway đổi prefix thành `/v1/orders` trước khi chuyển đến verifier. Ngoài ra, mỗi node lưu nonce bằng bộ nhớ cục bộ. Hãy phân tích hai lỗi độc lập có thể xuất hiện và đề xuất integration test tương ứng.

**Gợi ý:** Canonicalization có thể không khớp khi path bị rewrite; replay qua hai node có thể lọt. Xác minh trước khi rewrite hoặc thiết kế hợp đồng thống nhất; dùng nonce store nguyên tử chia sẻ.

**Tình huống C — Khóa cũ chưa thu hồi:** Merchant đã đổi secret, nhưng server vẫn chấp nhận `keyId` cũ vô hạn để “tương thích”. Attacker đã đoán secret cũ và tạo request với timestamp/nonce mới. Tại sao các kiểm soát replay không giúp? Cần điều chỉnh trạng thái khóa và phân quyền thế nào?

**Gợi ý:** Attacker không replay mà ký mới. Khóa cũ phải có hạn xác minh ngắn và thu hồi; principal vẫn phải bị ràng buộc với quyền thao tác/tài nguyên.

## 12. Ghi nhớ

Mấu chốt của đe dọa **“kẻ tấn công đoán secret”** là **không gian khóa nhỏ hoặc có thể dự đoán**. Khi biết một request và tag hợp lệ, attacker có thể kiểm tra ứng viên hoàn toàn offline. HMAC-SHA-256, HTTPS, timestamp, nonce và rate limit không bù được một shared secret yếu. Thiết kế tin cậy cần **khóa sinh bằng CSPRNG, phạm vi khóa hẹp, quản lý an toàn, key rotation/revocation, canonical request xác định, chống replay phân tán, kiểm tra phân quyền và giám sát rủi ro còn lại**.

**Tài liệu tham khảo định hướng:** [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104); [RFC 4231 — HMAC-SHA-256 test vectors](https://www.rfc-editor.org/rfc/rfc4231); [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869); [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421). Hợp đồng `hmac-v1` trong ví dụ chỉ để giải thích nguy cơ đoán khóa; không mặc nhiên là triển khai RFC 9421.
