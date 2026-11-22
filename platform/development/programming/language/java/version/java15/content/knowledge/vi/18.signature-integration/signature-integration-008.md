# Tránh ghi khóa riêng hoặc thông điệp nhạy cảm vào log khi tích hợp chữ ký số (Java 15+)

## 1. Mục tiêu và vấn đề thực tế

Khi tích hợp chữ ký số EdDSA (chẳng hạn **Ed25519** hoặc **Ed448**) trong một ứng dụng Java, nhóm phát triển thường cần **log để chẩn đoán lỗi, đối soát và phát hiện hành vi bất thường**. Tuy nhiên, chính log cũng có thể trở thành nơi làm lộ khóa riêng, dữ liệu nghiệp vụ và thông tin cá nhân mà quy trình ký đang cố bảo vệ.

Các ví dụ về câu lệnh dễ gây rủi ro:

```java
// KHÔNG LÀM: minh họa anti-pattern, KHÔNG phải mã cần chạy.
logger.info("privateKey=" + java.util.Arrays.toString(privateKey.getEncoded()));
logger.fine("message=" + new String(messageBytes, java.nio.charset.StandardCharsets.UTF_8));
logger.info("payload=" + requestBody);
logger.warning("Sign failed: " + exception.getMessage());
```

Trong các đoạn trên, biến `privateKey`, `messageBytes`, `requestBody`, `exception` là dữ liệu minh họa đã có từ code xung quanh. **Không** phải mẫu Java hoàn chỉnh và **không** được sao chép vào production.

Hai câu đầu có thể tiết lộ trực tiếp vật liệu khóa riêng hoặc thông điệp; câu thứ ba có thể đưa toàn bộ JSON/HTTP body chứa dữ liệu cá nhân, chứng từ, số tiền, credential vào kho log; câu cuối có thể đưa nội dung lỗi do provider hoặc dịch vụ bên ngoài tạo ra vào nơi không được kiểm soát. **Không được suy luận rằng mọi exception message đều chứa bí mật**; vấn đề là message đó có thể chứa dữ liệu chưa được kiểm tra.

**Mục tiêu bài học:** vẫn có đủ *audit trail* để biết một thao tác ký/xác minh xảy ra, thuộc thuật toán nào, kết quả ra sao, tương quan với giao dịch nào, nhưng **không ghi nội dung cần bảo vệ**. Cách làm bền vững là **allowlist trường log + ID tương quan an toàn + phân quyền hệ thống log + kiểm thử không rò rỉ**, không chỉ chạy một regex “che thông tin nhạy cảm” ở cuối pipeline.

Theo **MITRE CWE-532**, ghi thông tin nhạy cảm vào log là một loại lỗ hổng riêng; **OWASP Logging Cheat Sheet** cũng yêu cầu hạn chế ghi keys, tokens, thông tin cá nhân và dữ liệu nhạy cảm. Đây là nguyên tắc hiện hành, không phụ thuộc riêng vào Java 15.

## 2. Đặc thù của thao tác ký EdDSA trong Java

Java 15 đưa hỗ trợ EdDSA vào JCA (JEP 339). Trong Java 17+ và các JDK hiện hành, một luồng ký thường dùng:

```java
// Đoạn minh họa trong method đã có PrivateKey privateKey và byte[] payload.
java.security.Signature signer = java.security.Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(payload);
byte[] signature = signer.sign();
```

Bên xác minh dùng `Signature.initVerify(publicKey)`, `update(payload)` và `verify(signature)`. Mỗi lời gọi có những đối tượng mà lập trình viên rất dễ vô tình đưa vào log:

- **`PrivateKey`**: có thể là khóa phần mềm có thể xuất ra PKCS#8 hoặc một handle đến khóa không xuất được trong KeyStore/HSM.
- **`PrivateKey.getEncoded()`**: nếu trả byte[] thì thường là **vật liệu khóa riêng mã hóa dưới dạng container** (ví dụ PKCS#8), tuyệt đối không phải nội dung vô hại chỉ vì tên là “encoded”.
- **`EdECPrivateKey.getBytes()`**, `EdECPrivateKeySpec.getBytes()`: có thể cung cấp **byte khóa riêng** Ed25519/Ed448; các mảng này không được log, dù dùng Base64, hex hay `Arrays.toString`.
- **`payload`/message**: bytes gốc để ký; có thể bao gồm hợp đồng, dữ liệu khách hàng, thông tin thanh toán, kết quả xét duyệt, token hoặc dữ liệu nội bộ.
- **`signature`**: chữ ký **thường không phải bí mật mật mã** như private key, nhưng có thể là dữ liệu theo giao thức cần tránh lưu lâu, tạo khả năng liên kết giao dịch hoặc tiết lộ cấu trúc; **không mặc định dump toàn bộ vào log**.
- **`PublicKey`, chứng chỉ, key ID**: public key không cần bảo mật như private key nhưng vẫn phải bảo đảm nguồn tin cậy; tên alias, thông tin chứng chỉ hoặc fingerprint có thể là thông tin nội bộ hoặc định danh nhạy cảm theo chính sách.

**Không có chuyện chữ ký số tự mã hóa thông điệp.** Chữ ký đảm bảo kiểm tra tính toàn vẹn/xác thực bằng khóa tương ứng, chứ không che nội dung. Nếu ứng dụng log `payload` trước khi ký, việc ký đúng hoàn toàn không cứu được sự cố lộ dữ liệu ở log.

## 3. Phân loại trường dữ liệu trước khi thiết kế log

| Loại dữ liệu xuất hiện khi ký | Có nên ghi vào log ứng dụng thông thường? | Lý do/hướng xử lý |
|---|---|---|
| Private key object, PKCS#8, raw EdEC seed, PEM private key | **Không** | Rủi ro lộ bí mật ký; không serialize, không `toString` hay encode để ghi |
| PIN HSM, passphrase, KeyStore password, access token, session cookie | **Không** | Là credential; không log kể cả dạng Base64 hoặc sau biến đổi đơn giản |
| Message/payload gốc, request/response body chứa dữ liệu nhạy cảm | **Không** | Có thể chứa PII, số tài khoản, chứng từ, dữ liệu kinh doanh |
| Hash không có khóa của message | **Không mặc định** | Với message dễ đoán/ít entropy có thể tra từ điển; cũng liên kết giao dịch |
| Full signature bytes | **Tránh theo mặc định** | Thường không bí mật nhưng có thể là dữ liệu nhạy cảm theo chính sách/giao thức |
| Public key/DER certificate | **Không dump toàn bộ theo mặc định** | Có thể tiết lộ danh tính, topology hoặc thông tin nội bộ; thường không cần |
| Key alias, certificate subject, email, user ID, tenant ID | **Cần xem chính sách** | Có thể là identifier nhạy cảm; dùng ID nội bộ đã được duyệt và tối thiểu hóa |
| Tên thuật toán từ **allowlist** (ví dụ `Ed25519`) | **Thường được** | Metadata kỹ thuật hữu ích, không chứa bytes bí mật |
| Event code do ứng dụng định nghĩa | **Nên** | Hữu ích cho audit/alert: `SIGN_OK`, `VERIFY_REJECTED` |
| Outcome/nhóm lỗi đã chuẩn hóa | **Nên nếu phù hợp** | Không đưa chi tiết exception/raw body; dùng mã lỗi hữu hạn |
| Correlation ID ngẫu nhiên do hệ thống cấp | **Thường được** | Kết nối các bước xử lý mà không cần log message |
| Thời điểm, service/component, latency bucket | **Theo nhu cầu** | Có ích cho vận hành; kiểm soát metadata có thể mang tính nhạy cảm |

Một sự kiện có thể chứa **thông tin được phép ở hệ thống A nhưng không phù hợp ở hệ thống B**. Không có quy tắc “mọi public key đều luôn công khai trong mọi ngữ cảnh”, cũng không có quy tắc rằng mọi key ID đều được log. Hãy dùng **classification policy** và mục đích log đã thống nhất trong tổ chức.

## 4. Những đường dữ liệu thường bị rò rỉ ngoài câu lệnh `logger.info`

### 4.1. Log ứng dụng và console

`System.out.println`, `System.err.println`, `java.util.logging`, SLF4J/Logback, Log4j2 và các wrapper khác đều có thể chảy về cùng một hệ thống thu thập. **Đổi từ `println` sang logger có cấu trúc không tự làm log an toàn** nếu vẫn đưa private key hoặc payload làm tham số.

Các chỗ dễ có lỗi:

```java
// ANTI-PATTERN: không dùng cho dữ liệu thật.
System.out.println("signed=" + requestBody);
logger.fine("private=" + java.util.Base64.getEncoder()
        .encodeToString(privateKey.getEncoded()));
logger.info("signature=" + java.util.HexFormat.of().formatHex(signatureBytes));
```

Base64, hex và `Arrays.toString` **chỉ là thay cách biểu diễn**; chúng **không** che bí mật. Nếu log collector giữ lại raw bytes, kẻ có quyền đọc log có thể khôi phục giá trị hoặc dùng cho các mục đích ngoài dự kiến.

### 4.2. Logging tự động ở HTTP, framework và middleware

Một API ký tài liệu có thể đi qua:

```text
Client → API gateway → reverse proxy → HTTP middleware
       → controller → signing service → JCA provider/HSM
       → metrics/traces/log aggregator → backups
```

Ngay cả khi signing service đã cẩn thận, **gateway hoặc filter log toàn bộ request body** vẫn có thể lưu chứng từ nhạy cảm. Những điểm cần rà:

- HTTP access logs có query string, token hoặc định danh trong URL.
- HTTP client/server interceptors ghi request/response body và headers.
- Debug logs của JSON serializer, exception mapper, validation framework.
- Tracing/APM có request body, headers, spans attributes/baggage.
- Error reporting/crash reporting gửi request context hoặc local variables.
- SQL/query logs và message broker logs nếu payload hoặc khóa bị đưa vào đối số.
- CI test logs, stdout của container, log trên hệ thống monitoring và bản sao backup.

Cấu hình **không capture body/authorization headers** nên áp dụng từ **điểm thu thập sớm nhất**; một filter redaction ở cuối pipeline không chắc xử lý được mọi bản sao đã được ghi ở nơi khác.

### 4.3. Exception và stack trace

Đoạn này **không nên dùng** khi exception đến từ mã xử lý bí mật hoặc dữ liệu nhập chưa tin cậy:

```java
// ANTI-PATTERN; exception là biến giả định đã có.
logger.log(java.util.logging.Level.SEVERE,
        "sign failed; payload=" + requestBody, exception);
```

Tham số `exception` của nhiều logger cho phép in **toàn bộ stack trace và exception message**, bao gồm chuỗi do provider, parser, HTTP client hoặc thành phần bên thứ ba tạo. Không thể mặc định an toàn chỉ vì không tự nối `privateKey`.

**Giải pháp:** ở log audit/operational thông thường, ghi **mã lỗi đã phân loại** như `SIGN_PROVIDER_UNAVAILABLE`, `SIGN_INVALID_KEY`, `VERIFY_INVALID_SIGNATURE`, `INPUT_INVALID_FORMAT` thay vì dump nguyên exception. Khi thật sự cần stack trace, sử dụng một kênh chẩn đoán **được phân quyền riêng, có chính sách lọc, retention và phê duyệt**, đồng thời xem xét nguồn exception có khả năng chứa dữ liệu gì.

### 4.4. `toString()`, log arguments và lazy logging

Không dùng `privateKey.toString()`, `signatureObject.toString()`, `request.toString()` hoặc structured object serialization như bằng chứng rằng dữ liệu đã an toàn. Hành vi `toString()` của một lớp có thể thay đổi, wrapper dữ liệu có thể lồng secrets, và logger format placeholders vẫn có thể chuyển đối tượng thành chuỗi.

Một câu lệnh kiểu `logger.info("payload={}", payload)` (với API hỗ trợ placeholders) chỉ tránh nối chuỗi thủ công, **không tránh việc payload xuất hiện trong log**. Lazy supplier `logger.log(Level.FINE, () -> secretAsString)` cũng không giải quyết vấn đề: khi mức log bật, chuỗi bí mật vẫn được sinh/ghi.

## 5. Thiết kế audit event tối thiểu và an toàn

Một **audit event có cấu trúc** nên trả lời “hoạt động gì đã xảy ra, ở service nào, kết quả thế nào, liên quan tới request nào” mà **không trả lời nội dung ký cụ thể là gì**.

Ví dụ schema được phép:

```text
time                 : từ hệ thống ghi log (không lấy từ payload)
service              : signature-service
event_code           : SIGN_OK | VERIFY_OK | VERIFY_REJECTED | SIGN_ERROR
algorithm            : Ed25519 | Ed448 (allowlist)
correlation_id       : opaque ID do server phát, không chứa PII
outcome              : SUCCESS | REJECTED | ERROR
error_category       : NONE | INVALID_KEY | PROVIDER_FAILURE | INPUT_ERROR
```

Trong vận hành thật, logger/sink có thể tự thêm thời điểm, tên service, severity. Đừng lặp các trường đó trong message nếu đã có **structured logging** phù hợp.

### 5.1. Chọn dữ liệu theo allowlist, không theo blacklist

**Allowlist** nghĩa là log API chỉ chấp nhận những trường đã được xác định an toàn. Các trường khác **không có cách đi vào log một cách vô ý**:

```text
SigningService.sign(privateKey, payload, requestContext)
        |
        +----> JCA Signature (được phép thấy key và payload)
        |
        +----> AuditLogger.log(Event.SIGN_OK, opaqueCorrelationId)
                   |
                   +----> chỉ event code + algorithm allowlist + ID hợp lệ
```

Ngược lại, helper nhận `Map<String,Object>` rồi “xóa các key tên password/privateKey” không đủ an toàn: dữ liệu bí mật có thể mang tên `value`, `document`, `body`, `details`, `exception` hoặc lồng sâu trong đối tượng.

**Khuyến nghị:** dùng **enum event code**, enum/result code hữu hạn, ID tương quan kiểm tra định dạng/độ dài, và không cho API log nhận `PrivateKey`, `byte[] payload`, `byte[] signature` hoặc `Throwable` trong lối gọi mặc định.

### 5.2. Correlation ID phải tách khỏi nội dung thông điệp

Một correlation ID nên được tạo độc lập bởi hệ thống — chẳng hạn UUID ngẫu nhiên do server sinh hoặc một định danh opaque đáp ứng tiêu chuẩn nội bộ. Nó **không nên là email, số điện thoại, số tài khoản, JWT, access token hay digest trực tiếp của payload**.

Nếu client gửi `X-Request-ID`, chỉ dùng trong log sau khi đã **kiểm tra giá trị được phép, giới hạn độ dài, loại CR/LF/delimiters** hoặc thay bằng ID do server tạo. ID không an toàn có thể gây **log injection** (giả mạo dòng log) hoặc mang dữ liệu nhạy cảm.

Ở ví dụ runnable, `demo-001` là **giá trị cố định chỉ dành cho test** để stdout ổn định; production cần **ID duy nhất không chứa PII**, không dùng `demo-001` cho mọi request.

## 6. Mã Java hoàn chỉnh: ký Ed25519 và chỉ ghi audit allowlist

Chương trình sau dùng **Java 17+**, API EdDSA đã có từ Java 15. Chương trình tạo **cặp khóa tạm trong RAM** và một payload giả lập được sinh bằng `SecureRandom` để minh họa dữ liệu không nên ghi ra log. Không có private key hay thông điệp thực của người dùng.

Một logger `java.util.logging.Logger` được cấu hình với **Handler minh họa chỉ in message cho bài học**. Điều này tạo stdout ổn định khi QA; production nên sử dụng logging pipeline của tổ chức với **access controls, log rotation và structured fields** thay vì bắt chước cấu hình Handler trong `static` block.

Tạo tệp **`SafeSignatureLogDemo.java`** (UTF-8):

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeSignatureLogDemo {
    private static final Logger AUDIT = Logger.getLogger("demo.signature.audit");

    private enum Event {
        SIGN_OK, VERIFY_OK, VERIFY_REJECTED
    }

    static {
        AUDIT.setUseParentHandlers(false);
        AUDIT.setLevel(Level.INFO);
        AUDIT.addHandler(new Handler() {
            {
                setLevel(Level.INFO);
            }

            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() { }

            @Override
            public void close() { }
        });
    }

    private static void audit(Event event, String correlationId) {
        if (!correlationId.matches("demo-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid demo correlation ID");
        }
        AUDIT.info("event=" + event.name()
                + " correlation_id=" + correlationId
                + " algorithm=Ed25519");
    }

    private static byte[] sign(byte[] payload, KeyPair keys)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keys.getPrivate());
        signer.update(payload);
        return signer.sign();
    }

    private static boolean verify(byte[] payload, byte[] signed, KeyPair keys)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keys.getPublic());
        verifier.update(payload);
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        // Demo only: random, synthetic payload; never hardcode a real secret.
        byte[] sensitivePayload = new byte[128];
        new SecureRandom().nextBytes(sensitivePayload);
        byte[] modifiedPayload = sensitivePayload.clone();
        modifiedPayload[0] ^= 1;

        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keys = generator.generateKeyPair();
        String correlationId = "demo-001";
        byte[] signature = null;

        try {
            signature = sign(sensitivePayload, keys);
            audit(Event.SIGN_OK, correlationId);

            if (verify(sensitivePayload, signature, keys)) {
                audit(Event.VERIFY_OK, correlationId);
            } else {
                audit(Event.VERIFY_REJECTED, correlationId);
            }

            if (!verify(modifiedPayload, signature, keys)) {
                audit(Event.VERIFY_REJECTED, correlationId);
            }
        } finally {
            Arrays.fill(sensitivePayload, (byte) 0);
            Arrays.fill(modifiedPayload, (byte) 0);
            if (signature != null) {
                Arrays.fill(signature, (byte) 0);
            }
        }
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 SafeSignatureLogDemo.java
java -cp . SafeSignatureLogDemo
```

**Stdout chính xác**:

```text
event=SIGN_OK correlation_id=demo-001 algorithm=Ed25519
event=VERIFY_OK correlation_id=demo-001 algorithm=Ed25519
event=VERIFY_REJECTED correlation_id=demo-001 algorithm=Ed25519
```

Cặp khóa và payload thay đổi ngẫu nhiên mỗi lần chạy, nhưng stdout không thay đổi. Không có giá trị private key, payload gốc, public key, chữ ký hoặc các chuỗi nhạy cảm nào được đưa vào message.

### 6.1. Vì sao mẫu này hạn chế khả năng rò rỉ?

- **`sign`/`verify`** có quyền nhận `KeyPair` và `byte[]` vì cần thực hiện mật mã.
- **`audit`** chỉ nhận `Event` trong enum và `correlationId` theo mẫu giới hạn; nó **không có tham số** private key, payload, signature hay exception.
- **`AUDIT.info`** xây dựng message chỉ từ event code, correlation ID đã kiểm tra và tên thuật toán hằng.
- Sau khi thay đổi một byte, `verify` trả false; audit ghi **`VERIFY_REJECTED`**, không ghi nội dung payload sai.
- **`Arrays.fill`** được dùng cho các mảng byte do demo kiểm soát để giảm khả năng tồn tại của bản sao; **không hứa xóa toàn bộ dấu vết trong JVM**. Provider có thể có buffer hoặc object khác, và `PrivateKey` vẫn được quản lý riêng.

**Bất biến quan trọng:** chương trình **không phát biểu** rằng nó đã bảo vệ toàn bộ ứng dụng chỉ nhờ đoạn logger này. HTTP gateway, JCA provider, APM, framework, backup, debugging hoặc các thành phần khác vẫn phải tuân chính sách log an toàn.

### 6.2. Những gì ví dụ chủ ý không làm

- Không gọi `keys.getPrivate().getEncoded()` hoặc `EdECPrivateKey.getBytes()` chỉ để in/đo đạc.
- Không in payload dạng `String`, Base64, hex hoặc `Arrays.toString`.
- Không in full signature. Chữ ký không tương đương private key, nhưng giữ log tối thiểu vẫn là lựa chọn an toàn.
- Không log stack trace hoặc exception message tùy ý.
- Không dùng `demo-001` làm correlation ID cho production.
- Không trích xuất private key sang KeySpec hoặc lưu vào file để minh họa debug.

Dữ liệu đầu vào của ví dụ là mảng ngẫu nhiên sinh bằng `SecureRandom`, không phải một “bí mật thật”; không cần có secret thật để chứng minh log chỉ chứa metadata.

## 7. Cách xử lý lỗi ký mà không tiết lộ dữ liệu

Một signing service cần phân biệt **lỗi hệ thống** với **chữ ký không hợp lệ**:

| Kết quả | Có thể ghi event | Tránh ghi |
|---|---|---|
| Ký thành công | `SIGN_OK` | Nội dung đã ký, private key, chữ ký raw |
| Xác minh thành công | `VERIFY_OK` | Nội dung/headers chứa dữ liệu nhạy cảm, public key dump |
| Chữ ký không xác minh được | `VERIFY_REJECTED` | Full message, full signature, payload từ client |
| Thuật toán không khả dụng | `SIGN_PROVIDER_UNAVAILABLE` | Chi tiết hệ thống hoặc tham số bí mật không được kiểm duyệt |
| Khóa không dùng được | `SIGN_INVALID_KEY` | `getEncoded()`, private seed, PIN/alias nhạy cảm |
| Payload không hợp lệ | `INPUT_INVALID_FORMAT` | Lỗi parser chứa nguyên trường/giá trị của payload |

**Một `verify(...)` trả `false` là kết quả kiểm tra mật mã**, không nhất thiết là lỗi infrastructure. Ngược lại, `SignatureException`, `InvalidKeyException`, `NoSuchAlgorithmException` hoặc `InvalidAlgorithmParameterException` cho biết điều kiện xử lý khác và có thể cần cảnh báo/can thiệp.

Không nên có quy tắc “bất kỳ exception nào xảy ra thì log `getMessage()`” vì exception từ một thư viện khác có thể chứa dữ liệu người dùng, đường dẫn, alias hoặc giá trị đã bị từ chối. Hãy **map lỗi thành code trong enum** ở ranh giới đã tin cậy:

```java
// Minh họa bên trong SigningService có sẵn logger/audit function:
// catch (java.security.InvalidKeyException exception) {
//     audit(Event.SIGN_INVALID_KEY, correlationId);
//     throw new SigningUnavailableException("Cannot sign request");
// }
```

Đây chỉ là **phác thảo xử lý**: tên `Event.SIGN_INVALID_KEY` và `SigningUnavailableException` cần được định nghĩa trong ứng dụng thật; chúng **không nằm trong ví dụ hoàn chỉnh phần 6**. Không đưa exception gốc làm một trường log thường nếu chưa xác định an toàn; cũng không phát nguyên exception message cho client. Khi cần lưu thông tin chẩn đoán sâu, tách kênh được kiểm soát nghiêm ngặt và rà soát dữ liệu rò rỉ.

## 8. Tránh nhầm “đã hash” với “đã ẩn danh”

**Không nên lấy `SHA-256(payload)` làm correlation ID mặc định.** Một digest không có khóa có thể:

- Bị đoán bằng dictionary attack nếu payload đến từ tập giá trị nhỏ, ví dụ `status=paid`, mã trạng thái, số đơn hàng ngắn, vài mẫu hồ sơ có cấu trúc.
- Cho phép người đọc log kiểm tra liệu **hai request có cùng payload** hay không.
- Trở thành định danh theo dõi hành vi khi xuất hiện trong nhiều hệ thống.
- Không đủ điều kiện privacy chỉ vì không còn nhìn thấy văn bản gốc.

Tương tự, `hashCode()` của Java **không phải công cụ che giấu mật mã**. Dùng `Base64`, `HexFormat`, URL encoding, truncate rồi log hoặc encrypt bằng một khóa được đặt cùng hệ thống log cũng không tự làm dữ liệu an toàn.

Nếu thật sự cần **đối chiếu cùng thông điệp mà không lưu thông điệp**, phải đặt yêu cầu bảo mật/riêng tư rõ ràng. Một giải pháp có thể là **HMAC với khóa bí mật riêng được quản lý chặt chẽ**, có domain separation, kiểm soát quyền, retention và rotation; nó vẫn tạo khả năng liên kết, vẫn có rủi ro khi khóa HMAC bị lộ, và không nên triển khai chỉ để tiện debug. Đối với logging thường ngày, **opaque request ID ngẫu nhiên** độc lập với message đơn giản và ít gây hệ quả hơn.

**Fingerprint của public key** cũng cần được xem xét theo chính sách: nó có thể không tiết lộ private key nhưng vẫn giúp liên kết các giao dịch/định danh. Nếu phải log key reference, dùng identifier **được duyệt**, tránh đưa PEM/DER/key object hoặc certificate subject đầy đủ vào log.

## 9. Dùng định danh tương quan và metadata như thế nào?

### 9.1. Correlation ID

Có thể tạo ID cho request bằng `UUID.randomUUID()` hoặc cơ chế random opaque được ứng dụng kiểm soát. Lưu ý:

- Tránh để client chọn bất kỳ chuỗi nào rồi đưa trực tiếp vào log.
- Không dùng token truy cập, email, số điện thoại, họ tên, số thẻ làm correlation ID.
- Ràng buộc độ dài/charset và định dạng; đặc biệt loại hoặc mã hóa `CR`, `LF`, delimiter để chống **log injection**.
- Nên gắn ID với vòng đời request, và không tái sử dụng ID cố định qua nhiều giao dịch.
- Không đặt private key, chữ ký, payload hoặc credential trong MDC/ThreadContext/trace baggage.

Với một ID do server sinh, một exception xảy ra vẫn có thể được kết nối với request mà không phải log raw message.

### 9.2. Key reference thay vì private key

Trong HSM/KMS/KeyStore, ứng dụng thường có một **handle/alias/key ID** để lựa chọn khóa mà không cần xuất private key. Nếu policy cho phép, audit có thể ghi một **reference đã kiểm duyệt** nhằm giúp truy vấn thao tác theo key generation hoặc phiên bản. Không mặc định log raw alias vì alias có thể chứa thông tin khách hàng, hệ thống hoặc cấu trúc nội bộ.

Nên có bảng ánh xạ được bảo vệ riêng giữa **opaque key reference** và khóa thực. Không chuyển private seed hay PKCS#8 sang hex rồi đặt tên là `keyRef`.

### 9.3. Thời gian và outcome

Audit đáng tin cần timestamp và outcome; đồng bộ thời gian của các service bằng cơ chế tổ chức cho phép. Timestamps có thể được sink ghi tự động. Không viết lại timestamp do client gửi chưa tin cậy như một chứng cứ server time.

Nên biểu diễn outcome bằng giá trị hữu hạn (`SUCCESS`, `REJECTED`, `ERROR`), không ghi `errorMessage` raw rồi mới tìm regex để che.

## 10. Các bề mặt nguy hiểm trong Java thường bị bỏ sót

### 10.1. `PrivateKey.getEncoded()` và EdEC private key

Một số implementation có thể cho `privateKey.getEncoded()` trả **PKCS#8 DER**. Đó là container chứa thông tin khóa riêng, không phải ciphertext được bảo vệ mặc định. `EdECPrivateKey.getBytes()` có thể cung cấp seed private raw dạng `Optional<byte[]>`. Nếu key do HSM quản lý, các API này có thể trả `null`/`Optional.empty()` hoặc provider từ chối việc xuất.

**Không gọi các API export chỉ để log “độ dài”, “kiểm tra khóa”, “in vài byte đầu” hay tạo fingerprint từ private key.** Nếu muốn quan sát khả năng ký, hãy dùng `Signature.initSign(privateKey)` rồi kiểm tra kết quả nghiệp vụ một cách an toàn, không xuất secret.

Với khóa riêng bị lộ qua log, cần kích hoạt quy trình **incident response**, phân tích nơi log đã được sao chép, đánh giá thu hồi/rotation theo chính sách chữ ký và bảo vệ hệ thống thu thập log.

### 10.2. Trace attributes và baggage

Dữ liệu đưa vào OpenTelemetry/OpenTracing/span attributes, MDC và các context propagators có thể đi tới **hệ thống quan sát tập trung** hoặc qua ranh giới dịch vụ. Không dùng:

```text
span.attribute("signature.input", rawMessage)
span.attribute("private_key", privateKey)
trace.baggage("authorization", bearerToken)
```

Đây là **sơ đồ anti-pattern**, không phải cú pháp API Java chuẩn hoàn chỉnh. Ngay cả khi trace chỉ bật theo sampling, những trace được lấy mẫu vẫn có thể bị lưu/đẩy sang vendor. Mặc định chỉ cho phép **event code, algorithm, outcome, correlation ID** và những attribute đã được phê duyệt.

### 10.3. HTTP/client và serialization

Cẩn thận với `toString()` của DTO, auto-logging `record`, JSON serializer và các helper gửi toàn bộ object vào logger. Một Java `record` có `toString()` do compiler tạo ra có thể in **tên và giá trị các component**, nên không dùng cách này cho DTO chứa thông điệp/credential mà mong đợi sẽ tự được redacted.

Giới hạn rõ logging của middleware trong route ký, tránh log các request body hoặc trường trong headers như `Authorization`, cookie, token. Log URL/query string có thể gây lộ bí mật nếu client nhét token vào query; thiết kế API không truyền secret qua URL, đồng thời bảo vệ cả access logs.

### 10.4. JCA/provider diagnostics

Những cờ debug của runtime và thư viện có thể tạo **nhiều thông tin kỹ thuật nhạy cảm** (ví dụ thuộc tính bảo mật, key store, đường dẫn, tên provider, TLS handshake metadata, tùy chọn triển khai). Đừng bật các cờ debug chi tiết trên hệ thống production chỉ vì một lỗi ký mà không có **phạm vi, phê duyệt và kiểm soát đầu ra**. Không giả định rằng mọi cờ debug đều in private key; phải rà chính hành vi của phiên bản/provider và nơi log được gửi tới.

### 10.5. Thread-local / MDC context

MDC/ThreadContext là tiện cho correlation ID, nhưng có thể bị tái sử dụng giữa các request nếu không clear đúng vòng đời (đặc biệt với thread pool). Tránh đặt secret vào MDC ngay từ đầu; khi dùng ID, cần dọn hoặc khôi phục context ở `finally` và kiểm tra propagation trong tác vụ bất đồng bộ.

## 11. Redaction, masking và lọc log

**Bảo vệ tốt nhất là dữ liệu bí mật không đi vào pipeline log ngay từ đầu.** Redaction ở cuối vẫn có vai trò *defense in depth*, nhưng có giới hạn:

- Một regex tìm `password=` không bắt được key trong Base64/hex, field đổi tên hoặc payload dạng JSON lồng.
- Một sanitizer chạy sau khi app đã gửi event tới nhiều sink có thể không xóa được bản sao ở những sink khác.
- Log formatting có thể gọi `toString()` trước khi filter nhìn thấy dữ liệu.
- Việc cắt chuỗi sau N ký tự có thể giữ nguyên phần đầu của bí mật.
- Mask `****` một phần secret vẫn có thể tạo rủi ro và không có giá trị audit.

Nếu bắt buộc có logging dữ liệu cấu trúc, hãy đặt **schema allowlist**, kiểm tra type/size và encode đúng cách trước khi đưa sang sink. Tại điểm nhận dữ liệu từ vùng không tin cậy, loại hoặc escape **CR, LF và delimiter** để chống log forging. Điều đó khác với lọc nội dung bí mật: escape giúp giữ cấu trúc log, không thay cho cấm log secret.

### Một mô hình bảo vệ nhiều lớp

```text
signing code
   |
   +--> SecurityEvent(code, opaqueRequestId, algorithm, outcome)
             |
             v
       Schema allowlist / type validation
             |
             v
       Structured logger / approved sink
             |
             +--> transport protection
             +--> storage access control
             +--> retention + deletion policy
             +--> tamper detection + monitoring
```

Không để một bản sao full request body chảy song song qua một “debug channel” ngoài sơ đồ này, vì kênh đó có thể phá hỏng toàn bộ kiểm soát ở phía sau.

## 12. Quản lý log sau khi ghi

**Log audit vẫn là tài sản cần bảo vệ** ngay cả khi bạn không đưa private key hoặc message vào đó. Bản ghi kết quả ký có thể tiết lộ hành vi người dùng, lịch thao tác, lỗi provider hoặc cấu trúc nội bộ.

Những yêu cầu vận hành thông thường:

1. **Quyền đọc tối thiểu:** phân quyền theo vai trò; không để tất cả developer/nhà cung cấp đọc toàn bộ log production.
2. **Bảo vệ khi truyền và lưu:** dùng transport bảo mật tới collector, quản trị khóa mã hóa log khi áp dụng.
3. **Retention rõ ràng:** đủ phục vụ điều tra/đối soát và các yêu cầu hiện hành, nhưng không giữ vô hạn; quản lý cả replicas, backup và exports.
4. **Bảo vệ tính toàn vẹn:** hạn chế quyền sửa/xóa, cân nhắc audit riêng cho truy cập và thay đổi log, cảnh báo khi logging bị tắt hoặc sai lệch.
5. **Quy trình khẩn cấp:** nếu phát hiện private key/payload nhạy cảm trong log, dừng nguồn ghi, khoanh vùng nơi dữ liệu lan truyền, đánh giá thu hồi/quay vòng khóa và xử lý bản sao theo chính sách.
6. **Không tắt audit an ninh hoàn toàn để tránh rò rỉ:** thay vào đó, sửa schema audit để không chứa secret. Việc mất audit có thể khiến không phát hiện thao tác ký bất thường.

OWASP lưu ý logging phải cân bằng an toàn, khả năng phát hiện và các nghĩa vụ pháp lý liên quan. Không tự đưa thời hạn retention hoặc thuật toán mã hóa cụ thể vào mọi ứng dụng nếu chưa biết yêu cầu tổ chức và loại dữ liệu.

## 13. Kiểm thử chống rò rỉ: kiểm tra bằng hành vi, không chỉ review code

Một bài kiểm thử tốt nên chứng minh dữ liệu nhạy cảm **không có trong output và không được gửi sang sink**. Không chỉ grep từ khóa `privateKey` trong source: leakage có thể đi qua cấu trúc object hoặc framework khác.

### 13.1. Bài test tối thiểu với dữ liệu giả

Trong môi trường test, tạo payload **canary giả** mà bạn kiểm soát, ví dụ `"TEST_SECRET_7vQ4"` và một fake credential không có giá trị thật. Thực hiện các luồng:

- Ký thành công.
- Xác minh thành công.
- Xác minh không hợp lệ.
- Sai input/định dạng.
- Lỗi provider/khóa.
- Request bị từ chối bởi validation.
- Exception từ middleware có input chưa tin cậy.

Sau đó quét **mọi sink được cấu hình cho test**: application log, stdout/stderr, access log, trace exporter, error reporter, test reports, container logs. Đảm bảo canary **không xuất hiện** ở bất kỳ đâu. Cần kiểm tra cả Base64, hex và cách biểu diễn mà ứng dụng có thể tạo trong quy trình, khi phù hợp.

**Đừng sử dụng private key production thật làm canary.** Một fake private key với biểu diễn giả chỉ dùng cho test đủ để kiểm tra rủi ro đưa dữ liệu ra log.

### 13.2. Kiểm tra nội dung của audit schema

Chỉ cho phép các trường đã phê duyệt và các enum phù hợp. Một event có `message`, `payload`, `body`, `privateKey`, `secret`, `rawSignature` hoặc `exceptionDetails` nên bị **từ chối ngay tại API tạo event**, không đợi log shipper xóa.

Kiểm tra các ID không chứa `CR`, `LF`, ký tự điều khiển, delimiter nguy hiểm và không vượt độ dài tối đa. Test cả input từ client có nhiều ký tự Unicode/chuỗi dài để đảm bảo không gây log forging, tăng dung lượng bất thường hoặc lách validation.

### 13.3. Test thao tác ký và log độc lập

Một hệ thống có thể ký đúng nhưng log sai; cũng có thể log an toàn nhưng dùng sai khóa/mode. Cần kiểm tra **hai hợp đồng độc lập**:

- **Hợp đồng mật mã:** ký/xác minh đúng key, đúng byte, đúng Ed25519/Ed448/mode/context; sửa thông điệp làm verify thất bại.
- **Hợp đồng quan sát:** các event được ghi đúng loại nhưng **không chứa dữ liệu nhạy cảm**, có đủ correlation/outcome và không mở rộng fields ngoài allowlist.

Ví dụ chạy ở phần 6 kiểm chứng cả hai nhóm ở mức minh họa: `SIGN_OK`, `VERIFY_OK`, `VERIFY_REJECTED` xuất hiện và không có payload/key/signature trong stdout. Tuy nhiên, nó **không phải kiểm thử toàn bộ các sink** của một ứng dụng production.

## 14. Lỗi thường gặp khi triển khai

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
|---|---|---|
| Log `privateKey.getEncoded()` hoặc private seed | Ghi trực tiếp vật liệu khóa riêng vào kho truy cập rộng | Không gọi export vì mục đích logging; dùng key reference đã duyệt |
| Log request body trước hoặc sau khi ký | Lộ tài liệu, PII, giá trị tài chính và dữ liệu kinh doanh | Log outcome và opaque request ID; tắt body capture |
| Log toàn bộ chữ ký | Có thể liên kết giao dịch hoặc lộ dữ liệu không cần thiết | Không log theo mặc định; nếu cần đối chiếu, xem xét metadata được phê duyệt |
| “Bảo mật” bằng Base64/hex | Chỉ là encoding, dễ đảo ngược | Không ghi bytes gốc dưới dạng nào |
| “Bảo mật” bằng SHA-256(message) | Cho phép dictionary/correlation trên input ít entropy | Dùng request ID độc lập; xem xét HMAC chỉ khi có yêu cầu và threat model |
| Log exception/stack trace chưa rà | Exception message có thể chứa input/alias/đường dẫn | Map sang error code, kênh debug riêng có kiểm soát |
| Dùng `record.toString()` cho DTO chứa secret | Tự động đưa component values vào log | Tách DTO nhạy cảm và audit event an toàn |
| Bật full HTTP debug hoặc trace attributes chứa body | Dữ liệu rò qua các collector/sink ngoài app | Tắt capture, allowlist attribute trước export |
| Dùng request ID từ client không kiểm tra | Có thể chứa token, CR/LF hoặc giá trị giả mạo | Server-generated ID hoặc validate giới hạn chặt |
| Chỉ redaction bằng regex | Không bao quát nested fields, tên tùy ý, encoding khác | Allowlist tại nguồn, redaction chỉ là lớp phụ |
| Xóa log ở service nhưng quên backup | Secret vẫn tồn tại ở collector, archives, vendor exports | Incident response phải bao quát toàn bộ bản sao |
| Coi log nội bộ là an toàn tuyệt đối | Nội bộ vẫn có phân quyền rộng và nguy cơ rò rỉ | Access control, monitoring, retention, kiểm thử |
| Tắt toàn bộ logging an ninh | Mất khả năng truy vết chữ ký gian lận/lỗi | Giữ audit event tối thiểu, không đưa bí mật vào trường |
| Ghi quá nhiều metadata định danh | Dễ tái nhận diện/correlation người dùng | Phân loại metadata, chỉ giữ trường thật cần thiết |

## 15. Quy trình tích hợp trong dự án thực tế

Một chu trình thực dụng:

1. **Xác định ranh giới tin cậy:** nơi nhận payload và private key, nơi ký, nơi xác minh và nơi đẩy logs/traces. Phân loại dữ liệu cho từng bước.
2. **Thiết kế một API audit chuyên biệt:** event enum, algorithm enum, outcome enum, request correlation ID; không truyền `Key`, `byte[]`, `Throwable` hay raw DTO vào API audit.
3. **Rà framework/middleware:** cấu hình để không ghi authorization headers, request body, chứng từ, exception details hoặc private key object tự động.
4. **Tạo/chuẩn hóa correlation ID:** độc lập với payload, không chứa PII, có kiểm tra định dạng và giới hạn độ dài.
5. **Ánh xạ lỗi:** nhận diện nhóm JCA errors thành error code hữu hạn; phân biệt `verify==false` với lỗi provider.
6. **Chọn sink được phê duyệt:** kiểm soát vận chuyển, quyền truy cập, lưu trữ, thời gian giữ, backup và audit của chính log.
7. **Kiểm thử bằng canary giả:** xác nhận không rò sang logger, HTTP/access log, trace exporter hoặc error reporter.
8. **Giám sát và cập nhật:** theo dõi thay đổi cấu hình debug, phiên bản framework/provider, incident mới và các rule kiểm tra tự động trong CI.

Có thể dùng static analysis/lint để cảnh báo code gọi `getEncoded()`, `EdECPrivateKey.getBytes()`, `Arrays.toString`, `Base64.encodeToString` hoặc dump HTTP body trong logging method. Tuy nhiên những API này **không mặc nhiên nguy hiểm ở mọi ngữ cảnh**; cảnh báo cần review vị trí dữ liệu đi tới **sink**, tránh quy tắc “cấm tuyệt đối mọi lần gọi API”. Mục tiêu là không cho secret đi vào log, không phải cấm toàn bộ công việc nhập/xuất khóa hợp lệ.

## 16. Ghi nhớ quan trọng

**Đối với tích hợp chữ ký số, log nên ghi “sự kiện” chứ không ghi “bằng chứng mật mã/raw business data”.** Nhóm vận hành cần biết một lần ký thành công hay thất bại, thuật toán được phép, request ID và mã lỗi hữu hạn; họ không cần private key, PKCS#8, EdEC seed, chứng từ, payload nhạy cảm hoặc chữ ký đầy đủ trong log mặc định.

Một nguyên tắc an toàn theo thứ tự:

**Không thu thập** dữ liệu nhạy cảm → **allowlist metadata** → **kiểm tra input/encode để chống injection** → **bảo vệ log khi vận chuyển/lưu trữ** → **giới hạn truy cập/retention** → **kiểm thử và giám sát mọi sink**.

Trên Java 15+ các API EdDSA vẫn còn hiện hành; điều cần tránh không phải API `Signature` mà là **cách sử dụng logging sai ở các ranh giới hệ thống**. Đừng nghĩ một dòng `privateKey.toString()` là vô hại chỉ vì private key được dùng trong một phép ký an toàn.

### Tài liệu chính thức và hướng dẫn còn áp dụng

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): quản lý dữ liệu không được log, log injection, bảo vệ/retention và kiểm thử.
- [MITRE CWE-532 — Insertion of Sensitive Information into Log File](https://cwe.mitre.org/data/definitions/532.html): phân loại rủi ro và các nhóm mitigation.
- [Oracle Java SE 26 — `Signature`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): luồng initSign/update/sign, initVerify/update/verify.
- [Oracle Java SE 26 — `java.util.logging.Logger`](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html), [`Handler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Handler.html): hành vi ghi log và xuất log ra sink.
- [Oracle Java SE 26 — `EdECPrivateKey`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html), [`EdECPrivateKeySpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html): vật liệu khóa riêng và giới hạn xuất khóa.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): tính năng EdDSA đưa vào Java 15 và vẫn được dùng trên Java hiện hành.
