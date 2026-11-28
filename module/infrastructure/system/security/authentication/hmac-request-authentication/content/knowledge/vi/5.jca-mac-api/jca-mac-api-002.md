# Mac.getInstance trong JCA: chọn engine HMAC cho xác thực HTTP request

> **Chương:** JCA Mac API  
> **Chủ đề:** Mac.getInstance  
> **Phạm vi module:** Xác thực HTTP request bằng HMAC với shared secret và canonical request gồm phương thức, URI, header hoặc body theo hợp đồng ký. Bài học tập trung vào API Mac.getInstance trong Java, kết nối với xác minh chữ ký, chống replay bằng timestamp/nonce, key rotation, proxy/gateway và ranh giới giữa xác thực và phân quyền.

## 1. Mac.getInstance là gì?

**MAC (Message Authentication Code)** là giá trị được tính từ một thông điệp và khóa bí mật. **HMAC** là họ MAC dựa trên hàm băm mật mã; một lựa chọn phổ biến cho hệ thống API là **HMAC-SHA-256**. Với HMAC request authentication, client và server cùng nắm **shared secret**. Client ký canonical request; server tính lại giá trị HMAC từ đúng secret và đúng canonical bytes để kiểm tra tính xác thực và toàn vẹn của dữ liệu đã ký.

Java cung cấp engine **javax.crypto.Mac** trong JCA/JCE (Java Cryptography Architecture / Java Cryptography Extension). Phương thức tĩnh **Mac.getInstance** yêu cầu môi trường Java cung cấp một implementation của một thuật toán MAC cụ thể.

~~~java
import javax.crypto.Mac;

Mac mac = Mac.getInstance("HmacSHA256");
~~~

Lệnh trên **chưa sinh khóa**, **chưa nạp shared secret** và **chưa tính HMAC**. Nó chỉ tạo đối tượng engine có thể được khởi tạo với khóa:

~~~mermaid
flowchart TD
    A["Tên thuật toán: HmacSHA256"] --> B["Mac.getInstance"]
    B --> C["JCA tìm implementation trong security providers"]
    C --> D["Mac engine, chưa có secret"]
    D --> E["mac.init(secretKey)"]
    E --> F["mac.update(bytes) hoặc mac.doFinal(bytes)"]
    F --> G["Tag HMAC, thường 32 byte"]
    G --> H["Receiver đối chiếu với tag trong HTTP request"]
~~~

Giá trị HMAC chứng minh bên tạo tag đã nắm secret và **những thành phần được ký** không bị thay đổi. HMAC **không mã hóa** dữ liệu, **không tự ngăn phát lại request** và **không quyết định quyền truy cập**.

### 1.1. Không nhầm Mac với các API mật mã khác

| API Java | Nhiệm vụ | Vai trò trong HTTP HMAC |
|---|---|---|
| MessageDigest.getInstance("SHA-256") | Tính hash không có khóa | Băm raw body trước khi đưa digest vào canonical request |
| **Mac.getInstance("HmacSHA256")** | Tính mã xác thực thông điệp bằng khóa | **Ký và xác minh HMAC** |
| Signature.getInstance("SHA256withRSA") | Chữ ký số với khóa bất đối xứng | Giao thức khác, dùng private/public key |
| Cipher.getInstance(...) | Mã hóa hoặc giải mã | Không thay cho xác thực HMAC |
| TLS/HTTPS | Bảo vệ kết nối truyền tải | Vẫn cần dùng song song với HMAC |

Hash SHA-256 của body không đủ chứng minh danh tính: attacker có thể sửa body rồi tính lại hash. HMAC thêm secret vào phép xác thực theo cấu trúc tiêu chuẩn.

## 2. Ba overload của Mac.getInstance

Trong Java, Mac thuộc gói **javax.crypto**, kể cả khi ứng dụng sử dụng Java 17+ và Jakarta Servlet. JCA cung cấp các overload sau:

~~~java
public static Mac getInstance(String algorithm)
        throws NoSuchAlgorithmException;

public static Mac getInstance(String algorithm, String provider)
        throws NoSuchAlgorithmException, NoSuchProviderException;

public static Mac getInstance(String algorithm, Provider provider)
        throws NoSuchAlgorithmException;
~~~

| Overload | Ý nghĩa | Lựa chọn khi nào? |
|---|---|---|
| getInstance(algorithm) | Tìm implementation trong danh sách provider đã được runtime cấu hình | **Ưu tiên mặc định** |
| getInstance(algorithm, providerName) | Chỉ định provider bằng tên đã đăng ký | Khi có yêu cầu dùng provider cụ thể |
| getInstance(algorithm, providerObject) | Chỉ định trực tiếp một đối tượng Provider | Khi ứng dụng được tích hợp với provider chuyên dụng/HSM |

Ví dụ:

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.Mac;

// Chọn từ cấu hình của runtime.
Mac automatic = Mac.getInstance("HmacSHA256");

// Ví dụ chỉ chạy nếu SunJCE có mặt trong runtime.
Mac byName = Mac.getInstance("HmacSHA256", "SunJCE");

Provider p = Security.getProvider("SunJCE");
if (p == null) {
    throw new IllegalStateException("Security provider chưa được đăng ký");
}
Mac byObject = Mac.getInstance("HmacSHA256", p);
~~~

Tên **SunJCE** thường có ở một số bản phân phối OpenJDK hoặc Oracle JDK, nhưng **không được bảo đảm** ở mọi runtime. Môi trường dùng HSM, PKCS#11 hoặc cấu hình tuân thủ đặc biệt có thể yêu cầu provider khác. Cần xác nhận provider tồn tại và hỗ trợ thuật toán trước khi pin.

### 2.1. Tên thuật toán là hợp đồng giữa các hệ thống

Tên thuật toán thường dùng trong JCA:

~~~text
HmacSHA256      -> Mac (HMAC-SHA-256)
SHA-256         -> MessageDigest (SHA-256)
SHA256withRSA   -> Signature (chữ ký số bất đối xứng)
~~~

Không gọi Mac.getInstance("SHA-256") rồi coi đó là HMAC; cũng không tự tạo HMAC bằng cách nối secret với body và băm. Chọn thuật toán HMAC rõ ràng, ví dụ **HmacSHA256**, là một phần của hợp đồng ký.

Không để client quyết định thuật toán tùy ý:

~~~java
// Sai về thiết kế: người gọi tự chọn thuật toán.
Mac unsafe = Mac.getInstance(request.getHeader("X-Algorithm"));

// Đúng với hợp đồng hmac-v1 minh họa:
Mac approved = Mac.getInstance("HmacSHA256");
~~~

Nếu giao thức có nhiều phiên bản, server phải ánh xạ **version đã phê duyệt → thuật toán và chính sách được phép**, kiểm soát downgrade, không âm thầm chuyển sang thuật toán yếu hơn.

### 2.2. Các lỗi có thể xảy ra

| Trường hợp | Exception/hiện tượng | Cách xử lý |
|---|---|---|
| Provider không hỗ trợ thuật toán | NoSuchAlgorithmException | Lỗi cấu hình/khả năng runtime; kiểm tra lúc startup |
| Tên provider không được đăng ký | NoSuchProviderException | Kiểm tra cấu hình và việc cài đặt provider |
| Provider có tên đúng nhưng không có thuật toán yêu cầu | NoSuchAlgorithmException | Dùng provider/algorithm được phê duyệt |
| Tham số tên provider rỗng hoặc Provider null | Lỗi đối số, thường IllegalArgumentException | Kiểm tra cấu hình trước khi gọi |
| Dùng update hoặc doFinal trước init | IllegalStateException | Khởi tạo Mac bằng khóa hợp lệ |
| init nhận khóa không được provider chấp nhận | InvalidKeyException | Kiểm tra loại khóa và thuật toán tương thích |

Lỗi không tìm thấy thuật toán/provider **không phải** bằng chứng request của client bị giả mạo. Đây là lỗi cấu hình hoặc hạ tầng cần được quan sát và xử lý; không nên tự động bỏ xác thực hoặc fallback sang thuật toán khác.

## 3. JCA provider và việc lựa chọn implementation

**Engine class** xác định API nhất quán, còn **security provider** chứa implementation cụ thể. Một JVM có thể đăng ký nhiều provider theo thứ tự ưu tiên; provider có thể dùng phần mềm thuần Java, native library hoặc thiết bị mật mã.

~~~mermaid
flowchart LR
    A["Ứng dụng: Mac.getInstance"] --> B["JCA/JCE provider lookup"]
    B --> C["Provider A: hỗ trợ HmacSHA256"]
    B --> D["Provider B: hỗ trợ HmacSHA256"]
    B -.-> E["Provider C: không hỗ trợ"]
    C --> F["Mac engine"]
    D --> F
    F --> G["init với khóa được phép"]
~~~

Khi không pin provider, JCA dùng danh sách provider theo cấu hình runtime và điều kiện tương thích. Một số implementation có thể **trì hoãn chọn provider** đến khi init để xét loại khóa. Khi muốn xác nhận provider thực tế, nên gọi getProvider **sau khi init**:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secret, "HmacSHA256"));

String algorithm = mac.getAlgorithm();
String actualProvider = mac.getProvider().getName();
int macLength = mac.getMacLength(); // Full HMAC-SHA-256 thường là 32 byte.
~~~

Có thể xem provider đã đăng ký và thuật toán MAC khả dụng:

~~~java
import java.security.Provider;
import java.security.Security;

for (Provider provider : Security.getProviders()) {
    System.out.println(provider.getName());
}
System.out.println(Security.getAlgorithms("Mac"));
~~~

Tập thuật toán được liệt kê không bảo đảm mọi kiểu khóa đều được chấp nhận. Khi sử dụng provider đặc thù, cần kiểm tra cả **getInstance → init với loại khóa thật → tính một test vector**. Hai provider tuân thủ HMAC-SHA-256 phải tính ra cùng tag với cùng key bytes và message bytes, dù hiệu năng và cơ chế quản lý khóa có thể khác.

## 4. Vòng đời của đối tượng Mac

Một đối tượng Mac có **trạng thái nội bộ**:

| Bước/API | Chức năng | Lưu ý |
|---|---|---|
| Mac.getInstance(...) | Tạo engine | Chưa có secret |
| mac.init(SecretKey) | Thiết lập khóa | Bắt buộc trước khi xử lý message |
| mac.update(byte[]) | Nạp từng phần dữ liệu | Phải giữ đúng thứ tự byte |
| mac.update(ByteBuffer) | Nạp dữ liệu từ buffer | Chú ý vị trí và giới hạn buffer |
| mac.doFinal() | Kết thúc và trả tag từ dữ liệu đã nạp | Sau khi kết thúc, quay về trạng thái sau init |
| mac.doFinal(byte[]) | Nạp message và trả tag trong một lời gọi | Phù hợp canonical request ngắn |
| mac.reset() | Xóa thông điệp chưa hoàn thành khỏi trạng thái MAC | **Không thay khóa** và không xóa secret khỏi engine |
| mac.getMacLength() | Trả kích thước MAC theo byte | Với HMAC-SHA-256 đầy đủ thường là 32 |
| mac.getProvider() | Cho biết provider thực sự dùng | Xem sau init nếu cần xác nhận |

Hai cách gọi sau tạo cùng tag nếu cùng khóa và cùng thứ tự byte:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

byte[] data = "POST\n/v1/payments".getBytes(StandardCharsets.UTF_8);

Mac once = Mac.getInstance("HmacSHA256");
once.init(new SecretKeySpec(secret, "HmacSHA256"));
byte[] tag1 = once.doFinal(data);

Mac streamed = Mac.getInstance("HmacSHA256");
streamed.init(new SecretKeySpec(secret, "HmacSHA256"));
streamed.update("POST\n".getBytes(StandardCharsets.UTF_8));
streamed.update("/v1/payments".getBytes(StandardCharsets.UTF_8));
byte[] tag2 = streamed.doFinal();

boolean equal = MessageDigest.isEqual(tag1, tag2);
~~~

Biến **secret** ở ví dụ là key byte array đã được cấp phát từ trước. Dùng update hữu ích với dữ liệu nhiều phần; dùng doFinal(message) đơn giản hơn khi đã dựng đầy đủ canonical bytes.

### 4.1. Không dùng chung Mac giữa các luồng

Một Mac instance không được mặc định coi là thread-safe. Dùng một biến static chia sẻ sẽ tạo nguy cơ các request xen kẽ init/update/doFinal:

~~~java
// ANTI-PATTERN: không chia sẻ engine có trạng thái như thế này.
static final Mac GLOBAL = Mac.getInstance("HmacSHA256");
// Thread A: GLOBAL.init(keyA); GLOBAL.update(messageA)
// Thread B: GLOBAL.init(keyB); GLOBAL.update(messageB)
// Thread A: GLOBAL.doFinal() -> trạng thái không còn tương ứng với A.
~~~

Giải pháp dễ kiểm chứng là **tạo Mac mới cho mỗi lần ký hoặc verify**. Nếu cần pool hay ThreadLocal để tối ưu hiệu năng, phải có thiết kế vòng đời rõ ràng, không để lộ key/bytes giữa client hoặc tenant; chỉ tối ưu sau khi đo đạc thực tế.

## 5. Bài thực hành Java 17: test vector RFC 4231

Một cách kiểm chứng độc lập là dùng test vector công khai của **RFC 4231, test case 2**:

~~~text
Key             : Jefe
Data            : what do ya want for nothing?
HMAC-SHA-256 hex: 5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843
~~~

Khóa **Jefe** chỉ dùng cho test vector, **không phải secret production**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class MacGetInstanceDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] key = "Jefe".getBytes(StandardCharsets.UTF_8);
        byte[] input = "what do ya want for nothing?"
                .getBytes(StandardCharsets.UTF_8);
        byte[] expected = HexFormat.of().parseHex(
                "5bdcc146bf60754e6a042426089575c75"
              + "a003f089d2739839dec58b964ec3843");

        // 1. Chọn HMAC-SHA-256 từ security provider.
        Mac mac = Mac.getInstance("HmacSHA256");

        // 2. Khởi tạo engine với key test.
        mac.init(new SecretKeySpec(key, "HmacSHA256"));

        // 3. Tính HMAC đúng bytes của thông điệp.
        byte[] actual = mac.doFinal(input);

        // 4. Đối chiếu với test vector tham chiếu.
        if (!MessageDigest.isEqual(expected, actual)) {
            throw new AssertionError("HMAC không khớp RFC 4231");
        }

        System.out.println("RFC 4231: PASS");
        System.out.println("Algorithm: " + mac.getAlgorithm());
        System.out.println("Provider: " + mac.getProvider().getName());
        System.out.println("Tag length: " + mac.getMacLength());
    }
}
~~~

Đặt mã vào file **MacGetInstanceDemo.java** và chạy:

~~~bash
javac MacGetInstanceDemo.java
java MacGetInstanceDemo
~~~

Kết quả kỳ vọng có **RFC 4231: PASS** và tag length 32 byte; tên provider phụ thuộc JVM. Ví dụ chỉ kiểm chứng JCA/HMAC, chưa triển khai HTTP signature, replay hoặc phân quyền.

## 6. SecretKeySpec, sinh khóa và rotation

**SecretKeySpec** là wrapper cho byte khóa, không tạo entropy hoặc sinh secret mới. Một API HMAC server-to-server nên dùng secret đủ mạnh, ví dụ **32 byte từ CSPRNG**, bảo vệ bằng vault/KMS:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

byte[] secret = new byte[32];
new SecureRandom().nextBytes(secret); // 256 bit ngẫu nhiên.

// Mã hóa chỉ để cấp phát qua kênh an toàn; không thêm entropy.
String encoded = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(secret);
~~~

Không derive secret từ client ID, timestamp, chuỗi dễ nhớ hoặc nguồn giả ngẫu nhiên yếu. Không log secret, không đưa vào URL, source code, frontend hay request header. Định danh **X-Key-Id** là selector để tìm khóa; chính secret phải được server tra từ kho khóa theo principal và audience.

Một số provider/HSM không cho export raw key và cung cấp đối tượng SecretKey riêng. Trường hợp đó, init phải nhận đúng loại key do provider quản lý; không ép hệ thống lấy raw bytes chỉ để tạo SecretKeySpec.

### 6.1. Khi dùng nhiều key ID

| Key ID | Trạng thái | Receiver có được verify? |
|---|---|---|
| key-2026-11 | ACTIVE | Có |
| key-2026-10 | VERIFY_ONLY trong cửa sổ chuyển tiếp | Có, đến hạn phê duyệt |
| key-2026-09 | REVOKED | Không |

Receiver tìm đúng bản ghi **(clientId, keyId, audience)**, kiểm tra trạng thái và thời hạn, sau đó tạo Mac và **init với khóa của record đó**. Gọi reset không thực hiện đổi khóa. Khi secret có dấu hiệu lộ hoặc bị đoán, cần revoke nhanh và cấp secret độc lập mới; không giữ overlap vô thời hạn.

## 7. Dữ liệu đưa vào Mac phải là canonical HTTP request

Java Mac chỉ xử lý bytes. Hai HTTP request có ý nghĩa gần giống nhưng khác bytes sẽ cho hai chữ ký khác:

~~~text
/v1/orders?a=1&b=2    != /v1/orders?b=2&a=1
/v1/a%2Fb             != /v1/a/b
{"a":1,"b":2}          != {"b":2,"a":1}
~~~

Sender và receiver phải thống nhất một **signing contract**: method, raw URI, headers được ký, body digest, định dạng timestamp/nonce, thứ tự trường, encoding, delimiter. Nếu contract ký raw body, không parse JSON rồi serialize lại trước khi băm.

### 7.1. Hợp đồng minh họa hmac-v1

Hợp đồng này phục vụ học tập, **không phải chuẩn HTTP HMAC bắt buộc**.

| Thành phần | Quy tắc |
|---|---|
| Phiên bản | Dòng đầu hmac-v1 |
| Method | Token method HTTP, ví dụ POST |
| URI | Encoded path + raw query, giữ nguyên thứ tự/percent-encoding |
| Content-Type | Header đơn; trim và lowercase bằng Locale.ROOT; vắng mặt là chuỗi rỗng |
| X-Client-Id | Định danh client, có trong nội dung ký |
| X-Key-Id | Phiên bản khóa, có trong nội dung ký |
| X-Timestamp | Unix epoch seconds dạng số thập phân canonical |
| X-Nonce | Base64URL không padding của 16–32 byte CSPRNG |
| Body | SHA-256 của raw body bytes, chuyển sang hex chữ thường |
| Dấu phân cách | LF giữa mỗi dòng, không có LF cuối |
| Tag truyền đi | 32 byte HMAC-SHA-256 mã hóa Base64URL không padding trong X-Signature |

Request minh họa:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: nQdcX9lzC_vPV-ia1O2-AQ
X-Signature: <hmac-base64url>

{"orderId":"o-123","amount":150000}
~~~

Chuỗi canonical trước khi đưa vào Mac:

~~~text
hmac-v1
POST
/v1/payments?currency=VND
application/json
merchant-17
key-2026-11
1795824000
nQdcX9lzC_vPV-ia1O2-AQ
<sha256-hex-cua-raw-body>
~~~

Các biểu thức trong dấu ngoặc nhọn góc là **placeholder minh họa**, không phải chữ ký/digest thật. Secret không được gửi trong request.

### 7.2. Java 17: đưa canonical bytes vào Mac

Đây là **lõi mật mã**, chưa phải full HTTP authentication filter. Adapter HTTP phải kiểm tra header trùng, kích thước body, raw target hợp lệ, nonce/timestamp và key record trước khi sử dụng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HttpHmacV1 {
    private HttpHmacV1() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId, String timestamp,
            String nonce, byte[] rawBody) {}

    public static byte[] canonicalBytes(Request r)
            throws GeneralSecurityException {
        if (r == null || r.rawBody() == null) {
            throw new IllegalArgumentException("Request/body không hợp lệ");
        }
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(r.rawBody()));
        String ct = r.contentType() == null ? ""
                : line(r.contentType()).trim().toLowerCase(Locale.ROOT);
        String canonical = String.join("\n",
                "hmac-v1",
                line(r.method()),
                line(r.rawTarget()),
                ct,
                line(r.clientId()),
                line(r.keyId()),
                line(r.timestamp()),
                line(r.nonce()),
                bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static byte[] hmac(byte[] secret, byte[] canonical)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32 || canonical == null) {
            throw new IllegalArgumentException("Secret/message không hợp lệ");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical);
    }

    public static String sign(Request r, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(secret, canonicalBytes(r)));
    }

    // Kiểm tra MAC thuần túy; timestamp/nonce/key status xử lý ở caller.
    public static boolean verifyMac(Request r, String signature, byte[] secret)
            throws GeneralSecurityException {
        if (signature == null || signature.length() != 43) return false;
        final byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (received.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                          .encodeToString(received).equals(signature)) {
            return false;
        }
        byte[] expected = hmac(secret, canonicalBytes(r));
        return MessageDigest.isEqual(expected, received);
    }

    private static String line(String value) {
        if (value == null || value.indexOf('\r') >= 0
                || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Trường canonical không hợp lệ");
        }
        return value;
    }
}
~~~

**Điểm quan trọng:** Mac.getInstance lấy engine; init chọn secret cho **một lần xử lý**; doFinal tính tag từ **đúng canonical bytes**. MessageDigest.isEqual được dùng để so byte tag. So sánh String trong đoạn code chỉ kiểm tra **dạng encoding Base64URL canonical**, không so secret hay hai tag HMAC.

Lõi trên giả định adapter đã giữ đúng raw target, signed headers và raw body; byte array có thể bị thay đổi nếu caller giữ tham chiếu nên cần sao chép/cố định buffer khi chuyển giữa các tầng. Trước khi chấp nhận request, receiver còn phải kiểm tra danh tính/audience/key status, timestamp, nonce và authorization.

## 8. Receiver xác thực còn cần kiểm tra những gì?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant V as HMAC verifier
    participant K as Key store
    participant N as Nonce store
    participant A as Authorization
    C->>C: Canonical bytes + Mac.getInstance/init/doFinal
    C->>G: HTTPS request và chữ ký
    G->>V: Request theo hợp đồng
    V->>V: Validate header, raw URI, raw body, size
    V->>K: Lookup clientId, keyId, audience
    K-->>V: Key hợp lệ để verify
    V->>V: Check timestamp và MAC
    V->>N: Reserve nonce nguyên tử
    N-->>V: Nonce mới hoặc đã dùng
    V->>A: Authenticated principal
    A->>A: Kiểm tra action/resource/tenant
~~~

Mac.getInstance chỉ phụ trách **chọn engine MAC**. Nó không kiểm tra các điều kiện HTTP/bảo mật sau:

- Header bắt buộc, duplicate signed header, giá trị CR/LF hoặc byte không hợp lệ.
- Secret đã được ràng buộc với đúng client ID, key ID, audience, môi trường và trạng thái ACTIVE/VERIFY_ONLY.
- Timestamp có nằm trong cửa sổ chấp nhận, ví dụ ±300 giây.
- Nonce có được sinh theo yêu cầu và **chưa từng sử dụng** trong phạm vi client/key.
- Proxy có giữ nguyên URI, query, header và raw body tại điểm kiểm tra hay không.
- Authenticated principal có quyền thực hiện action trên resource/tenant cụ thể hay không.

### 8.1. Chống replay bằng timestamp và nonce

Chính sách minh họa:

~~~text
now - 300 <= signedTimestamp <= now + 300
HMAC hợp lệ với đúng secret và canonical bytes
nonceScope = (clientId, keyId, nonce)
ghi nonce sau khi HMAC đúng bằng insert-if-absent nguyên tử
TTL ví dụ: 600 giây, đủ bao phủ khoảng timestamp còn hiệu lực
~~~

Với Redis, có thể dùng primitive tương đương **SET nonceKey 1 NX EX 600**. Không dùng GET rồi SET vì hai request chạy song song có thể cùng vượt qua. Nonce store dùng chung giữa nhiều node; lỗi kho nonce phải **fail closed**. Timestamp/nonce chỉ chống phát lại request cũ, không ngăn bên đã biết secret tạo timestamp/nonce mới và ký request mới.

Với thao tác tạo/sửa có tác động nghiệp vụ, **idempotency** là cơ chế bổ sung: retry hợp lệ với nonce mới không được vô tình tạo hai giao dịch.

### 8.2. Authentication khác authorization

HMAC đúng cho thấy người gửi **nắm khóa** của principal, không có nghĩa họ được phép thực hiện mọi hành động:

~~~text
authentication:
  clientId = merchant-17
  keyId    = key-2026-11
  mac      = valid

authorization:
  action   = payments:create
  resource = order-123
  tenant   = merchant-17
  decision = policy(principal, action, resource, tenant)
~~~

Nếu request được ký đúng nhưng thao tác trên đơn hàng của merchant khác, lớp **authorization** vẫn phải từ chối, ví dụ HTTP 403.

## 9. Kiểm thử qua proxy/gateway

Ngay cả khi sender và receiver gọi cùng Mac.getInstance("HmacSHA256"), tag vẫn sai nếu canonical byte khác nhau:

| Thay đổi do hạ tầng | Tác động | Cách kiểm chứng |
|---|---|---|
| Rewrite path từ /public/v1 sang /v1 | URI được verify khác dữ liệu đã ký | Verify trước rewrite hoặc dùng original target do proxy đáng tin cung cấp |
| Decode %2F thành / hoặc sắp xếp query | Raw target thay đổi | Test URI percent-encoding, query order, query trùng khóa |
| Thêm/sửa Content-Type hoặc gộp header | Header ký khác hoặc mơ hồ | Chốt quy tắc canonical hóa; reject duplicate |
| Decompress body hoặc reserialize JSON | SHA-256 body thay đổi | Verify trên byte nhất quán theo hợp đồng |
| TLS termination, HTTP/2 sang HTTP/1.1 | Authority/header/target có thể thay đổi | Test qua đúng tuyến production |
| Load balance qua nhiều verifier node | Nonce cục bộ gây replay chéo node | Shared nonce store với ghi nguyên tử |

Không tin X-Forwarded-* hoặc X-Original-URI nếu người gọi internet có thể tự chèn. Proxy đáng tin phải loại giá trị do client đưa vào và gắn lại metadata qua kênh được bảo vệ.

## 10. Danh sách kiểm thử cần có

| Ca kiểm thử | Kết quả kỳ vọng |
|---|---|
| Mac.getInstance với HmacSHA256 | Engine được tạo trên JDK hỗ trợ |
| Thuật toán/provider không tồn tại | Exception đúng loại, fail closed |
| doFinal trước init | IllegalStateException |
| RFC 4231 case 2 | Tag HMAC-SHA-256 đúng vector |
| update(part1), update(part2), doFinal | Bằng doFinal(part1 + part2) |
| Hai provider cùng chuẩn, cùng khóa/bytes | Tag giống nhau |
| Hai request với key khác nhau chạy đồng thời | Không trộn trạng thái Mac |
| Thay method, URI, query, header ký, raw body | MAC không khớp |
| Signed header bị lặp, signature sai encoding | Reject trước hoặc trong verify |
| Sai client ID/key ID/audience | Không lấy nhầm secret hay principal |
| Timestamp quá cũ/quá mới | Reject dù HMAC đúng |
| Gửi lại nonce ở cùng scope | Request sau bị reject |
| Gửi nonce cùng lúc đến hai node | Chỉ một request reserve thành công |
| Nonce store lỗi | Fail closed, không xử lý nghiệp vụ |
| Key chuyển VERIFY_ONLY sang REVOKED | Không chấp nhận khi đã revoke |
| Gateway đổi URI hoặc body | Integration test phát hiện canonical mismatch |
| HMAC hợp lệ, resource khác tenant | Bước authorization từ chối |

Mã HTTP thường dùng: 400 cho request sai định dạng, 401 cho thiếu/sai xác thực, 403 khi không đủ quyền, 413 khi body quá lớn và 503 khi dependency xác thực không sẵn sàng. Phản hồi cụ thể theo hợp đồng API, không để lộ secret, expected tag hoặc thông tin nhạy cảm về key.

## 11. Các lỗi điển hình khi dùng Mac.getInstance

1. **Nhầm SHA-256 với HmacSHA256:** dùng MessageDigest thay cho Mac.
2. **Nhầm getInstance đã khởi tạo secret:** gọi doFinal trước init.
3. **Secret yếu hoặc hard-code:** độ dài tag 256 bit không cứu được secret dễ đoán.
4. **Dùng charset mặc định:** hai phía có thể tạo canonical byte khác; nên dùng UTF-8 theo contract.
5. **Parse rồi serialize lại JSON:** raw body không còn trùng dữ liệu đã ký.
6. **Chia sẻ Mac static:** nhiều luồng trộn key và message.
7. **So sánh tag bằng String.equals:** giải mã tag rồi dùng so sánh byte phù hợp như MessageDigest.isEqual.
8. **Để client chọn algorithm/provider tùy ý:** có nguy cơ downgrade hoặc cấu hình bất ngờ.
9. **Reset khi đổi khóa:** reset không thay secret; phải init lại.
10. **HMAC đúng là cho qua toàn bộ:** thiếu timestamp, nonce, key status, audience và authorization.

## 12. Bài tập vận dụng

**Bài 1 — Sửa lỗi vòng đời:** Đoạn code sau thiếu gì, sẽ gặp lỗi nào?

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
byte[] tag = mac.doFinal(message);
~~~

**Bài 2 — Chọn provider:** Chạy test vector RFC 4231 ở hai JVM khác nhau. So sánh getProvider, getMacLength và tag. Vì sao tên provider có thể khác mà tag phải trùng?

**Bài 3 — Canonicalization:** Sender ký POST /v1/items?a=1&b=2, receiver nhận POST /v1/items?b=2&a=1. Lỗi nằm ở getInstance hay ở bytes đưa vào doFinal? Đề xuất cách sửa.

**Bài 4 — Key rotation:** Merchant chuyển key A sang key B. Hãy mô tả việc lookup, kiểm tra trạng thái và init đúng key cho request; giải thích vì sao reset không phải rotation.

**Bài 5 — Replay:** Một request có MAC hợp lệ bị gửi lại với cùng timestamp và nonce. Thiết kế nào bảo đảm chỉ một request được xử lý, kể cả khi hai bản đến hai node khác nhau?

**Bài 6 — Phân quyền:** Merchant A ký HMAC đúng nhưng gọi API trên order của merchant B. Tầng nào phải từ chối và dựa trên chính sách gì?

## 13. Ghi nhớ

**Mac.getInstance("HmacSHA256")** là bước đầu của việc tính HMAC bằng Java: nó lựa chọn engine từ security provider. Sau đó cần **init đúng secret**, đưa **đúng canonical bytes** vào update/doFinal và đối chiếu tag bằng cách thích hợp. Với xác thực HTTP request, Mac chỉ là lớp mật mã; tính an toàn thực tế còn phụ thuộc quản lý khóa, timestamp/nonce chống replay, sự nhất quán qua gateway/proxy và phân quyền độc lập.

**Tài liệu tham khảo:**

- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): getInstance, init, update, doFinal, reset, getProvider và getMacLength.
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên thuật toán JCA/JCE.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): cấu trúc và tính chất của HMAC.
- [RFC 4231 — HMAC test vectors](https://www.rfc-editor.org/rfc/rfc4231): test vector HMAC-SHA-256.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): tham khảo cho việc ký các thành phần HTTP. Hợp đồng hmac-v1 ở bài này là ví dụ phục vụ học tập, không phải triển khai RFC 9421.
