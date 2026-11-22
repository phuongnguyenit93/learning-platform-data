# Thiết kế thông điệp có chữ ký với context thống nhất trong Java

> **Thực hành Java 15+**: xây dựng thông điệp liên dịch vụ có chữ ký số, ràng buộc cùng một **context** giữa nơi ký và nơi xác minh; tránh dùng lại chữ ký cho mục đích, tenant hoặc dịch vụ nhận khác. Ví dụ dùng Ed25519 trong Java Cryptography Architecture (JCA), có mặt từ JDK 15 (JEP 339) và vẫn được hỗ trợ trong Java hiện hành. Chương trình chạy độc lập, không cần thư viện bên ngoài.

## 1. Bài toán: cùng payload nhưng khác ngữ cảnh

Giả sử một dịch vụ tạo thông điệp `order=42;amount=100` cho thao tác **phê duyệt đơn hàng**. Nếu chỉ ký đúng payload, một hệ thống khác có thể diễn giải cùng các byte đó như yêu cầu **hủy đơn** hoặc gửi đến tenant khác. Chữ ký hợp lệ cho payload không tự nói thông điệp được phép dùng ở đâu.

Một **context thống nhất** là hợp đồng chung giữa bên ký và bên xác minh, mô tả rõ thông điệp thuộc **giao thức nào, phiên bản nào, mục đích nào, tenant nào, người phát hành nào, đích nhận nào**. Context phải trở thành **một phần của dữ liệu được ký**, và nơi xác minh phải so sánh nó với giá trị **được cấu hình/tin cậy tại điểm xử lý**.

Ví dụ context nghiệp vụ:

| Thuộc tính | Giá trị minh họa | Ý nghĩa bảo vệ |
| --- | --- | --- |
| Giao thức/format | `signed-message/v1` | Phân biệt với định dạng chữ ký khác, là dấu phân tách miền (domain separation) |
| Thuật toán | `Ed25519` | Cố định phép ký/xác minh; không để bên gửi tự chọn thuật toán tùy ý |
| `purpose` | `orders.approve.v1` | Chỉ dùng cho thao tác phê duyệt |
| `tenant` | `tenant-42` | Ràng buộc vào một không gian dữ liệu |
| `issuer` | `orders-service` | Tên chủ thể phát hành được ủy quyền |
| `audience` | `fulfillment-service` | Chỉ dịch vụ đích tương ứng được xử lý |
| `keyId` | `orders-2026-11` | Chỉ ra khóa công khai cần tra trong kho khóa **đã tin cậy** |

Một cùng payload và cùng chữ ký **không được** tự động chấp nhận khi chuyển `purpose` từ `orders.approve.v1` sang `orders.cancel.v1`; đổi `tenant`, `issuer` hoặc `audience` cũng phải bị từ chối. Đổi bất cứ trường nào đã được ký sẽ làm phép xác minh chữ ký thất bại, trừ khi người tấn công có khóa bí mật hợp lệ.

**Lưu ý về thuật ngữ:** context ở đây là **ngữ cảnh nghiệp vụ được ràng buộc bằng chữ ký**, không phải `ThreadLocal`, logging MDC hay biến môi trường. Ta dùng **Ed25519** chuẩn của JCA trên toàn bộ dữ liệu có context. Đây là kỹ thuật domain separation **ở tầng định dạng thông điệp ứng dụng**; không phải khai báo đang dùng biến thể thuật toán mật mã `Ed25519ctx`.

## 2. Những bảo đảm mà chữ ký thực sự cung cấp

Với chữ ký số bất đối xứng:

1. Bên phát hành có **private key** ký lên chuỗi byte xác định.
2. Bên nhận tra **public key tin cậy** tương ứng với `keyId`, tái tạo **đúng cùng chuỗi byte** rồi xác minh chữ ký.
3. Khi thành công, có bằng chứng rằng dữ liệu đã ký không bị sửa và chữ ký được tạo bằng khóa bí mật tương ứng với khóa công khai đang tin cậy, theo giả định mật mã và an toàn khóa.
4. Bên nhận vẫn phải đánh giá **ủy quyền**, context, thời hạn, chống replay và tính hợp lệ của dữ liệu nghiệp vụ **trước khi thực thi**.

Chữ ký **không mã hóa** dữ liệu: payload có chữ ký vẫn có thể bị đọc khi truyền. Khi truyền qua mạng nên dùng TLS/HTTPS hoặc transport bảo mật khác phù hợp. Chữ ký cũng **không tự chống phát lại**: kẻ có được một thông điệp hợp lệ có thể gửi nguyên vẹn lần nữa nếu bên nhận không chặn nonce trùng hoặc không bảo đảm idempotency.

Phân biệt với HMAC: HMAC dùng **khóa bí mật dùng chung** (ví dụ `HmacSHA256`); mọi bên giữ khóa đều có thể tạo MAC. Chữ ký bất đối xứng cho phép bên nhận chỉ giữ public key, giảm việc phát tán khóa ký. Chọn theo mô hình tin cậy của hệ thống; bài này thực hành Ed25519 để bên xác minh không cần private key.

## 3. Hợp đồng thông điệp: những gì cần đưa vào chữ ký

Một thông điệp được ký (envelope) nên có các trường được xác định rõ ràng:

| Thành phần | Cách bảo vệ | Quy tắc |
| --- | --- | --- |
| `format/version` | Đưa vào byte được ký | Thay đổi định dạng phải tăng version và có quy tắc tương thích rõ |
| `algorithm` | Cố định bởi chính sách và gắn vào frame | Chặn thuật toán không được phép, đặc biệt không nhận “none” từ dữ liệu ngoài |
| `keyId` | Đưa vào byte được ký; lookup ở trusted keyring | Không tự tải public key từ URL không tin cậy trong envelope |
| `purpose,tenant,issuer,audience` | Đưa vào byte được ký; đối chiếu với context tin cậy | Từ chối thông điệp sai mục đích, không gian dữ liệu hoặc người nhận |
| `issuedAt` | Đưa vào byte được ký | Epoch seconds UTC, kiểm tra lệch giờ cho phép |
| `expiresAt` | Đưa vào byte được ký | Từ chối hết hạn; khống chế thời gian sống tối đa |
| `nonce` | Đưa vào byte được ký | Ngẫu nhiên đủ mạnh và duy nhất cho mỗi thông điệp |
| `payload` | Ký **đúng byte** ứng dụng sẽ xử lý | Không tự normalize hay sửa payload sau khi xác minh |
| `signature` | Kết quả ký trên toàn bộ trường bên trên | Không đưa chữ ký vào chính dữ liệu đang được ký |

Trong bài thực hành: `format = signed-message/v1`, thuật toán cố định `Ed25519`, nonce gồm 16 byte tạo bằng `SecureRandom`, thời gian sống mẫu 120 giây và mức TTL tối đa cho phép ở verifier là 300 giây. Đây là **chính sách minh họa**, không phải thời hạn dùng chung cho mọi hệ thống.

### Thứ tự xử lý an toàn

```text
Bên ký:
Context chuẩn + keyId + timestamps + nonce + payload bytes
    -> encoder xác định duy nhất
    -> Ed25519 ký bằng private key
    -> gửi envelope có signature

Bên nhận:
Đọc envelope với giới hạn kích thước
    -> lấy expectedContext từ cấu hình/tuyến xử lý tin cậy
    -> kiểm tra context, keyId, timestamp, kích thước
    -> tra public key tin cậy
    -> encode lại chính xác cùng frame
    -> Ed25519 xác minh chữ ký
    -> kiểm tra/ghi nhận nonce nguyên tử
    -> kiểm tra schema & quyền nghiệp vụ
    -> thực thi một lần, có idempotency khi cần
```

Không lấy `expectedContext` trực tiếp từ trường `context` do bên gửi cung cấp rồi coi đã xác minh đúng ngữ cảnh. Bên gửi phải khai báo context để được ký; **bên nhận tự biết context nào đang được phép** ở endpoint/job/handler và phải đối chiếu với khai báo đã ký.

## 4. “Ký cùng một thông điệp” nghĩa là ký cùng một dãy byte

Hai chương trình không thể xác minh chữ ký của nhau nếu chúng tự chọn cách nối trường khác nhau. Các cách dễ sai:

- Nối `"tenant=" + tenant + "|purpose=" + purpose + payload` mà không có framing: ký tự phân tách nằm trong dữ liệu có thể tạo nhập nhằng.
- Dựa vào `Map.toString()`, thứ tự thuộc tính JSON bất định, `Object.hashCode()` hoặc biểu diễn mặc định của object.
- Dùng `String.getBytes()` không chỉ định charset: có thể khác theo môi trường.
- Ký JSON rồi parse/re-serialize trước khi verify mà không có cùng quy tắc canonicalization.
- Ký chuỗi đã trim nhưng khi xử lý lại sử dụng chuỗi chưa trim; hai thành phần sẽ hiểu dữ liệu khác nhau.

### Định dạng nhị phân xác định trong bài

Mỗi trường chuỗi được đổi sang UTF-8 bằng `StandardCharsets.UTF_8`; encoder ghi **4 byte độ dài** (`writeInt` của `DataOutputStream`, thứ tự big-endian) rồi ghi đúng từng byte nội dung. Hai timestamp là `long` 8 byte big-endian (epoch seconds UTC); nonce và payload cũng có tiền tố độ dài 4 byte.

Thứ tự trường trong `signedBytes` được **cố định**:

```text
len("signed-message/v1") + bytes("signed-message/v1")
len("Ed25519")          + bytes("Ed25519")
len(keyId)              + bytes(keyId)
len(purpose)            + bytes(purpose)
len(tenant)             + bytes(tenant)
len(issuer)             + bytes(issuer)
len(audience)           + bytes(audience)
issuedAt: 8 bytes big-endian
expiresAt: 8 bytes big-endian
len(nonce)              + nonce bytes
len(payload)            + payload bytes
```

`len` ở đây luôn là số **byte UTF-8** hoặc byte nhị phân, không phải `String.length()`. Framing theo độ dài tránh nhập nhằng giữa `("ab","c")` và `("a","bc")`. Không dùng `DataOutputStream.writeUTF()` cho giao thức này vì phương thức đó dùng **modified UTF-8**, không phải chính xác UTF-8 thông thường.

**Định dạng truyền qua mạng** có thể là JSON/CBOR/Protobuf gồm các trường envelope và chữ ký Base64url. Đây chỉ là lớp vận chuyển: **chuỗi byte được ký vẫn phải là output của encoder được đặc tả ở trên**, không phải JSON do serializer tùy ý tạo. Khi triển khai parser nhận dữ liệu bên ngoài, phải kiểm tra giới hạn số byte, chiều dài không âm, UTF-8 hợp lệ, trường bắt buộc, trường trùng và format version **trước khi cấp phát/copy**. Ví dụ Java dưới đây biểu diễn envelope **trong bộ nhớ để tập trung vào thiết kế chữ ký**, chưa phải thư viện parse wire protocol hoàn chỉnh.

Nếu cần ký JSON văn bản liên hệ thống, nên chọn một chuẩn canonicalization đã được đặc tả (ví dụ JSON Canonicalization Scheme, RFC 8785), hoặc ký chính byte body truyền qua mạng và xử lý **đúng byte đó**; đừng tự thiết kế chuẩn hóa riêng mà không kiểm thử liên ngôn ngữ. Unicode normalization cũng phải là một phần của hợp đồng rõ ràng, không được âm thầm áp dụng ở một phía.

## 5. Ví dụ hoàn chỉnh: ký, xác minh và mười phép thử

Tạo tệp **`SignedContextDemo.java`**. Chương trình chỉ dùng API chuẩn có từ Java 15; biên dịch với Java 17+ cũng được. Mục tiêu là minh họa **một context đồng nhất và độc lập giữa bên ký/bên nhận**, cách đóng khung byte xác định, whitelist khóa/thuật toán, chống giả mạo trường và replay.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Base64;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class SignedContextDemo {
    private static final String ALG = "Ed25519";
    private static final String KEY_ID = "orders-2026-11";
    private static final int MAX_PAYLOAD = 4096;

    static final class Context {
        final String purpose, tenant, issuer, audience;

        Context(String purpose, String tenant, String issuer, String audience) {
            this.purpose = purpose;
            this.tenant = tenant;
            this.issuer = issuer;
            this.audience = audience;
        }
    }

    static final class Envelope {
        final Context context;
        final String keyId;
        final long issuedAt, expiresAt;
        final byte[] nonce, payload, signature;

        Envelope(Context context, String keyId, long issuedAt, long expiresAt,
                 byte[] nonce, byte[] payload, byte[] signature) {
            this.context = context;
            this.keyId = keyId;
            this.issuedAt = issuedAt;
            this.expiresAt = expiresAt;
            this.nonce = nonce.clone();
            this.payload = payload.clone();
            this.signature = signature.clone();
        }
    }

    static void writePart(DataOutputStream out, byte[] data) throws IOException {
        out.writeInt(data.length);
        out.write(data);
    }

    static void writeString(DataOutputStream out, String value) throws IOException {
        writePart(out, value.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] signedBytes(Envelope msg) throws IOException {
        ByteArrayOutputStream raw = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(raw);
        writeString(out, "signed-message/v1");
        writeString(out, ALG);
        writeString(out, msg.keyId);
        writeString(out, msg.context.purpose);
        writeString(out, msg.context.tenant);
        writeString(out, msg.context.issuer);
        writeString(out, msg.context.audience);
        out.writeLong(msg.issuedAt);
        out.writeLong(msg.expiresAt);
        writePart(out, msg.nonce);
        writePart(out, msg.payload);
        out.flush();
        return raw.toByteArray();
    }

    static Envelope sign(Context context, byte[] payload, long now,
                         PrivateKey privateKey) throws Exception {
        byte[] nonce = new byte[16];
        new SecureRandom().nextBytes(nonce);

        Envelope draft = new Envelope(
                context, KEY_ID, now, now + 120, nonce, payload, new byte[0]);

        Signature signer = Signature.getInstance(ALG);
        signer.initSign(privateKey);
        signer.update(signedBytes(draft));

        return new Envelope(context, KEY_ID, now, now + 120,
                nonce, payload, signer.sign());
    }

    static boolean same(Context a, Context b) {
        return a.purpose.equals(b.purpose)
                && a.tenant.equals(b.tenant)
                && a.issuer.equals(b.issuer)
                && a.audience.equals(b.audience);
    }

    static boolean verify(Envelope msg, Context expected,
                          Map<String, PublicKey> trustedKeys, long now,
                          Set<String> usedNonces) throws Exception {
        if (!same(msg.context, expected)) return false;

        PublicKey key = trustedKeys.get(msg.keyId);
        if (key == null || msg.nonce.length != 16
                || msg.signature.length != 64 || msg.payload.length > MAX_PAYLOAD) {
            return false;
        }

        long ttl;
        try {
            ttl = Math.subtractExact(msg.expiresAt, msg.issuedAt);
        } catch (ArithmeticException ex) {
            return false;
        }

        if (ttl < 1 || ttl > 300 || msg.issuedAt > now + 60
                || now >= msg.expiresAt) return false;

        Signature verifier = Signature.getInstance(ALG);
        verifier.initVerify(key);
        verifier.update(signedBytes(msg));
        if (!verifier.verify(msg.signature)) return false;

        String replayKey = msg.keyId + ":" + Base64.getUrlEncoder()
                .withoutPadding().encodeToString(msg.nonce);
        return usedNonces.add(replayKey);
    }

    static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) throws Exception {
        long now = 1_800_000_000L; // Đồng hồ cố định để test lặp lại được.
        KeyPair pair = KeyPairGenerator.getInstance(ALG).generateKeyPair();
        Map<String, PublicKey> trusted = Map.of(KEY_ID, pair.getPublic());

        Context approval = new Context(
                "orders.approve.v1", "tenant-42",
                "orders-service", "fulfillment-service");
        Context cancellation = new Context(
                "orders.cancel.v1", "tenant-42",
                "orders-service", "fulfillment-service");

        byte[] payload = "order=42;amount=100"
                .getBytes(StandardCharsets.UTF_8);
        Envelope msg = sign(approval, payload, now, pair.getPrivate());
        Set<String> seen = new HashSet<>();

        check("valid", verify(msg, approval, trusted, now, seen));
        check("replay-rejected", !verify(msg, approval, trusted, now, seen));
        check("wrong-expected-context-rejected", !verify(
                msg, cancellation, trusted, now, new HashSet<>()));

        Envelope retagged = new Envelope(
                cancellation, msg.keyId, msg.issuedAt, msg.expiresAt,
                msg.nonce, msg.payload, msg.signature);
        check("retagged-context-rejected", !verify(
                retagged, cancellation, trusted, now, new HashSet<>()));

        Envelope tampered = new Envelope(
                msg.context, msg.keyId, msg.issuedAt, msg.expiresAt,
                msg.nonce, "order=42;amount=999"
                .getBytes(StandardCharsets.UTF_8), msg.signature);
        check("tampered-payload-rejected", !verify(
                tampered, approval, trusted, now, new HashSet<>()));

        Envelope changedExpiry = new Envelope(
                msg.context, msg.keyId, msg.issuedAt, msg.expiresAt + 1,
                msg.nonce, msg.payload, msg.signature);
        check("changed-expiry-rejected", !verify(
                changedExpiry, approval, trusted, now, new HashSet<>()));

        check("expired-rejected", !verify(
                msg, approval, trusted, now + 121, new HashSet<>()));

        Envelope badKid = new Envelope(
                msg.context, "unknown-key", msg.issuedAt, msg.expiresAt,
                msg.nonce, msg.payload, msg.signature);
        check("unknown-key-rejected", !verify(
                badKid, approval, trusted, now, new HashSet<>()));

        PublicKey incorrectKey = KeyPairGenerator.getInstance(ALG)
                .generateKeyPair().getPublic();
        check("wrong-public-key-rejected", !verify(
                msg, approval, Map.of(KEY_ID, incorrectKey),
                now, new HashSet<>()));

        Envelope changedNonce = new Envelope(
                msg.context, msg.keyId, msg.issuedAt, msg.expiresAt,
                new byte[16], msg.payload, msg.signature);
        check("changed-nonce-rejected", !verify(
                changedNonce, approval, trusted, now, new HashSet<>()));

        System.out.println("All 10 checks passed.");
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 SignedContextDemo.java
java SignedContextDemo
```

**Đầu ra chính xác** của các phép thử (khóa và nonce ngẫu nhiên nên không in trực tiếp):

```text
PASS valid
PASS replay-rejected
PASS wrong-expected-context-rejected
PASS retagged-context-rejected
PASS tampered-payload-rejected
PASS changed-expiry-rejected
PASS expired-rejected
PASS unknown-key-rejected
PASS wrong-public-key-rejected
PASS changed-nonce-rejected
All 10 checks passed.
```

Chương trình đã được kiểm tra trên OpenJDK 24. Các trường hợp dự kiến đều thành công, và các nhánh kiểm tra âm tính thực sự được xác minh là **trả về false**. Nếu có lỗi, `check` ném `AssertionError` thay vì âm thầm in `PASS`.

**Giải thích những điểm quyết định của code:**

1. `KeyPairGenerator.getInstance("Ed25519")` sinh khóa dùng cho demo; private key chỉ dùng tại bên ký, public key nằm trong `trusted` tại bên nhận. Trong môi trường thật, hai tiến trình không nên tạo keypair mới tùy ý mỗi lần chạy rồi tự coi khóa bất kỳ là đáng tin.
2. `signedBytes` là định nghĩa **duy nhất** cho mọi bên tham gia giao thức. Nó ký cả `ALG`, `keyId`, bốn trường context, hai timestamp, nonce và payload. `signature` không được đưa vào input ký.
3. `same(msg.context, expected)` buộc **context từ thông điệp** khớp **context do bên nhận mong đợi**. `expected` phải được xây dựng từ cấu hình/endpoint/route mà bên nhận kiểm soát.
4. Ngay cả khi kẻ gửi đổi `msg.context` để khớp một endpoint khác (`retagged-context`), chữ ký vẫn sai vì `signedBytes` đã thay đổi. Đây là chốt bảo vệ chống dùng lại chữ ký **khác mục đích**.
5. `trustedKeys.get(msg.keyId)` lấy khóa từ **keyring tin cậy**; `keyId` chỉ là tên tra cứu, không phải bằng chứng tin cậy. Trong ví dụ, mọi khóa không nằm trong map đều bị từ chối.
6. Kiểm tra `issuedAt`, `expiresAt` và `ttl` chặn thông điệp quá hạn hoặc khai báo khoảng sống bất thường. Thí nghiệm dùng `now` cố định để kết quả lặp lại; production phải lấy đồng hồ UTC đáng tin cậy như `Instant.now().getEpochSecond()` và xác định chính sách clock skew.
7. `SecureRandom` tạo nonce, rồi nonce được ký và dùng để chống gửi lại. Phương thức `usedNonces.add` trả `false` nếu đã có giá trị: ví dụ chỉ dùng một `HashSet` **trong một JVM**, chưa giải quyết replay giữa nhiều instance hoặc sau restart.
8. Mảng byte được `clone()` khi tạo `Envelope` để code bên ngoài không thể thay nội dung thông qua chính mảng đầu vào sau khi ký. Parser/wire adapter thực tế còn phải kiểm tra đối tượng null, kiểu, độ dài và UTF-8 trước khi xây dựng envelope.

### Vì sao phần ký và xác minh phải dùng chung context/encoder?

Nếu nơi ký dùng `purpose = orders.approve.v1` còn nơi nhận tin là `orders.cancel.v1`, thì dù payload giống nhau, **giá trị cần xác minh phải khác**. Nếu hai ứng dụng ký chuỗi JSON có thứ tự field khác nhau hoặc một bên chuyển UTF-8 sang encoding khác, chữ ký sẽ không khớp dù dữ liệu nhìn bằng mắt giống nhau. Do đó cần một **hợp đồng định dạng phiên bản hóa**, code/test chung hoặc golden vectors chia sẻ cho các ngôn ngữ.

Không giải quyết lỗi mismatched signature bằng cách “bỏ context khỏi signedBytes”; như vậy sẽ mở đường cho chữ ký bị dùng sang mục đích khác.

## 6. Kiểm thử âm tính theo ma trận đe dọa

| Tình huống | Thay đổi so với thông điệp đã ký | Kết quả đúng | Lý do |
| --- | --- | --- | --- |
| Hợp lệ | Không thay đổi; context/khóa phù hợp | Chấp nhận lần đầu | Byte frame và chữ ký khớp |
| Replay | Gửi lại nguyên thông điệp | Từ chối | Nonce đã được ghi nhận |
| Sai endpoint/purpose | Verifier mong context khác | Từ chối | Context nhận được không bằng context tin cậy |
| Retag context | Sửa purpose trong envelope và đưa đến endpoint mới | Từ chối | Byte được ký thay đổi, chữ ký không khớp |
| Sửa số tiền | Sửa payload nhưng giữ chữ ký | Từ chối | Tính toàn vẹn bị phá |
| Gia hạn trái phép | Sửa `expiresAt` | Từ chối | Timestamp được ký |
| Gói quá hạn | Chữ ký nguyên vẹn, thời điểm hiện tại đã qua expiry | Từ chối | Chính sách thời gian độc lập với tính hợp lệ chữ ký |
| Khóa lạ | `keyId` không thuộc keyring | Từ chối | Không có trust anchor |
| Khóa sai | `keyId` hợp lệ nhưng public key không đúng | Từ chối | Chữ ký không verify được |
| Sửa nonce | Thay nonce nhưng giữ chữ ký | Từ chối | Nonce cũng nằm trong dữ liệu được ký |

Có thể bổ sung test đổi `tenant`, `issuer`, `audience`, phiên bản, thứ tự trường, chuỗi Unicode có dấu, ký tự null, payload rỗng, payload vượt giới hạn, và key rotation. Với mỗi thay đổi **sau ký** của một trường đã được bảo vệ, kết quả xác minh phải thất bại, trừ trường hợp tạo thông điệp mới và ký lại hợp lệ.

Kiểm thử liên ngôn ngữ nên có golden vector: cùng một context, key test cố định, nonce, timestamps, payload chứa ký tự Unicode/byte nhị phân; các implement phải tạo **cùng một framed byte array**. Với Ed25519 trên cùng key và thông điệp, chữ ký cũng xác định; không đưa private key test vào sản phẩm. Các golden vectors giúp phát hiện khác biệt ở framing và UTF-8 trước khi xảy ra sự cố production.

## 7. Chống replay đúng trong hệ thống nhiều instance

Ví dụ `HashSet` chỉ phù hợp để minh họa. Trong triển khai thực:

1. Tạo nonce từ `SecureRandom` đủ dài; 16 byte là 128 bit ngẫu nhiên trong bài. Không dùng `Random` hoặc timestamp đơn lẻ để thay thế nonce.
2. Khi nhận, xác minh chữ ký, context và thời gian trước khi chấp nhận nonce. Tra cứu nonce theo vùng tin cậy phù hợp, chẳng hạn namespace gồm `issuer`/`tenant`/`keyId` và nonce đã xác thực.
3. Dùng thao tác **insert-if-absent nguyên tử** trong kho chia sẻ (ví dụ Redis với chế độ chỉ đặt khi chưa tồn tại và expiry, hoặc unique constraint trong database). Việc `contains` rồi `add` ở hai thao tác tách rời có race condition.
4. Giữ bản ghi nonce ít nhất đủ lâu để các thông điệp còn hiệu lực không thể phát lại; tính đến lệch đồng hồ, timeout, retry và cơ chế hoạt động của hệ thống.
5. Khi có retry hợp lệ của client, xác định idempotency key và chính sách trả lại cùng kết quả nghiệp vụ hoặc chặn trùng. **Replay prevention** và **business idempotency** có mục đích gần nhau nhưng không tương đương.
6. Ràng buộc TTL ngắn phù hợp; không tích lũy nonce vô hạn. Nếu kho nonce không sẵn sàng ở thao tác nhạy cảm, phải định nghĩa rõ xử lý fail closed hay chiến lược an toàn được thiết kế.

Không nên dùng mỗi `issuedAt` để chống replay. Thông điệp cùng chữ ký vẫn có thể được gửi hàng trăm lần trong khoảng thời gian hợp lệ.

## 8. Quản lý khóa và context xuyên suốt hệ thống

**Đời sống của một keyId:**

- Private key Ed25519 được giữ trong kho bí mật an toàn/KMS/HSM khi yêu cầu, quản lý quyền ký theo role; không đặt trong source, config public, log, query string hoặc file chia sẻ.
- Public key được phát hành qua kênh có xác thực, gắn với issuer/tenant/purpose/audience được phép. Chỉ thấy `keyId` trong một gói không có nghĩa key đó đáng tin.
- Khi đổi khóa, phát hành `keyId` mới, triển khai public key mới tới verifier trước, chuyển signer sang khóa mới, giữ khóa cũ chỉ trong thời gian cần để xác minh thông điệp chưa hết hạn; có phương án revoke khẩn cấp.
- Khóa ký cho môi trường test, staging và production nên tách biệt. Nếu một public key được phép xác minh nhiều use case, **context đã ký và expected context** vẫn phải được thực thi ở từng handler.
- Khi cần giấy chứng nhận hoặc cơ chế trust hierarchy, kiểm tra đúng certificate chain, hiệu lực, mục đích sử dụng và trust anchor; bản thân chữ ký trên payload không thay thế việc xác thực nguồn gốc khóa.

**Đời sống của context:**

- Đặt tên purpose có namespace và version ổn định (ví dụ `orders.approve.v1`) thay vì chuỗi mô tả tiếng Việt dễ thay đổi.
- Cả producer và consumer có một đặc tả chung cho thuật toán, cách encode, field order, charset, policy thời gian và quy tắc context; mỗi phía có thể triển khai độc lập nhưng phải cùng hợp đồng.
- Verifier giữ bảng route/job → expected context từ cấu hình tin cậy, không dựa vào bên gửi để chọn mọi quyền xử lý.
- Khi thay đổi nghĩa nghiệp vụ, nên tăng purpose/version và triển khai tương thích có thời hạn, thay vì âm thầm tái sử dụng version cũ với nghĩa mới.
- Ký thêm thông tin ảnh hưởng quyết định: HTTP method, path, content-type, resource ID, scopes hoặc version schema khi chúng ảnh hưởng xử lý. Với HTTP signatures, cân nhắc dùng chuẩn hiện hành RFC 9421 thay vì tự định nghĩa một hệ chữ ký tùy ý.

## 9. Tính hợp lệ của payload và thứ tự xử lý

Chữ ký xác minh đúng **không có nghĩa payload an toàn**. Sau khi xác minh cần:

- Parse payload theo schema đã version hóa, có kiểm tra kích thước, kiểu, trường bắt buộc và giới hạn giá trị.
- Xác nhận quyền nghiệp vụ của issuer đối với tenant/resource/action đã ký. Việc signer có private key không tự cấp quyền truy cập tất cả order hoặc tenant.
- Kiểm tra rằng resource trong payload thuộc tenant và đối tượng hợp lệ, tránh cross-tenant/confused-deputy.
- Dùng cùng **byte payload đã được xác minh** khi parse để xử lý; không tải lại payload từ URL ngoài, không dùng bản khác bị thay đổi sau verify.
- Thiết kế thao tác nhận thông điệp theo transaction/idempotency để một lỗi mạng ở bước phản hồi không thực hiện thao tác nhạy cảm hai lần.
- Không trả chi tiết “chữ ký sai ở byte nào” hoặc lộ key material qua lỗi/log. Log các thông tin đủ chẩn đoán như reason code, request ID, issuer/kid đã được kiểm soát và số lượng lỗi; tránh lưu bí mật hoặc payload nhạy cảm.

Ví dụ thử nghiệm dùng text `order=42;amount=100` chỉ là các **byte payload mẫu**. Hệ thống thực nên dùng schema đã định nghĩa thay vì dựa vào chuỗi phân tách bằng dấu chấm phẩy; áp dụng whitelist giá trị và xác thực object sau bước verify.

## 10. Lỗi thường gặp và cách sửa

| Lỗi triển khai | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ ký payload, bỏ purpose/tenant/audience | Dùng chữ ký đúng cho endpoint/tenant khác | Đưa context vào frame, verifier lấy expected context tin cậy |
| Chữ ký không bao phủ keyId/timestamp/nonce | Metadata có thể bị thay đổi mà không mất hiệu lực chữ ký | Ký tất cả trường quyết định xử lý |
| Verifier tin URL public key hoặc thuật toán do message cung cấp | Key substitution / algorithm confusion | Tra trusted keyring theo kid và whitelist thuật toán theo policy |
| Nối chuỗi bằng dấu phân cách không được escape | Frame nhập nhằng | Dùng length-prefix, encoding xác định hoặc chuẩn canonicalization |
| Dùng charset mặc định, thay đổi xuống dòng, normalize khác nhau | Các bên ký/xác minh byte khác nhau | Đặc tả UTF-8 và ký exact bytes |
| Coi chữ ký hợp lệ là đã ủy quyền hành động | Confused deputy / thao tác trái phép | Kiểm tra issuer, audience, tenant, resource và permission |
| Không kiểm tra nonce | Có thể replay thông điệp hợp lệ | Nonce ngẫu nhiên được ký + kho replay nguyên tử có TTL |
| Cache nonce cục bộ trong cluster | Replay qua instance khác | Kho chia sẻ có khóa duy nhất và tính nguyên tử |
| Không khống chế time-to-live và lệch giờ | Gói cũ hoặc gói có expiry rất xa được chấp nhận | Ký timestamps, kiểm tra TTL tối đa + clock skew |
| Dùng `MessageDigest` để “ký” | Hash không chứng minh nguồn phát | Dùng `Signature` hoặc HMAC đúng với trust model |
| Dùng RSA padding/MD5/SHA-1 đời cũ theo snippet cũ | Rủi ro kỹ thuật và thiếu chính sách bảo mật hiện hành | Dùng thuật toán/chế độ hiện hành đã được phê duyệt như Ed25519 hoặc RSASSA-PSS phù hợp |
| Ký object rồi serialize khác đi trước khi gửi | Bên nhận xác minh sai hoặc xử lý dữ liệu khác | Đặc tả wire format; tái tạo canonical frame duy nhất |
| Tự chế cơ chế chứng thực cho HTTP dù đã có chuẩn phù hợp | Khó interoperable và dễ thiếu signed components | Xem RFC 9421 (HTTP Message Signatures) và tiêu chuẩn giao thức cụ thể |

Một lưu ý crypto nữa: không tự tạo thuật toán kiểu “SHA-256(payload + secret)” để thay thế chữ ký/HMAC; không lấy `hashCode()` làm chữ ký. Không dùng `Random` thay `SecureRandom`. Đừng giả định chữ ký bao hàm confidentiality hoặc ngăn các bên sở hữu private key cố tình gửi thông điệp sai nghiệp vụ.

## 11. Tự kiểm tra và mở rộng bài thực hành

**Câu 1.** Hai endpoint `orders.approve.v1` và `orders.cancel.v1` cùng nhận payload `order=42`. Nếu chỉ ký payload thì vấn đề gì?  
**Đáp án:** Chữ ký của endpoint thứ nhất có thể hợp lệ về mặt mật mã khi đưa sang endpoint thứ hai nếu cùng khóa được tin cậy. Phải ký purpose và xác minh expected context.

**Câu 2.** Vì sao cần ký cả `expiresAt` và `nonce`?  
**Đáp án:** Để không thể gia hạn expiry hoặc thay nonce mà giữ nguyên chữ ký. Verifier cần kiểm tra hạn dùng và dùng nonce để chống replay.

**Câu 3.** `keyId` xuất hiện trong envelope có thể tự chứng minh public key đó hợp lệ không?  
**Đáp án:** Không. Nó chỉ là nhãn tra cứu; verifier phải có nguồn khóa tin cậy và chính sách issuer/audience/purpose.

**Câu 4.** Tại sao `"ab" + "c"` và `"a" + "bc"` minh họa nguy cơ serialization?  
**Đáp án:** Cả hai cách nối không kèm độ dài đều tạo `"abc"` dù hai bộ trường khác nhau. Length-prefix khắc phục nhập nhằng đó.

**Câu 5.** Payload đã ký hợp lệ được gửi hai lần trong 5 giây. Vì sao lần thứ hai phải có thể bị từ chối?  
**Đáp án:** Chữ ký vẫn đúng nhưng nghiệp vụ có thể bị thực hiện hai lần. Dùng nonce replay store, kết hợp idempotency/transaction khi cần.

**Bài tập mở rộng:**

1. Thêm test sửa `tenant`, `issuer`, `audience` và `keyId` sau khi ký; các test đều phải từ chối.
2. Viết decoder cho frame length-prefix, từ chối trường có length âm, vượt giới hạn, UTF-8 không hợp lệ, field thiếu/thừa; test round-trip giữa hai tiến trình.
3. Xây dựng golden vector byte-level cho payload UTF-8 tiếng Việt và binary; đối chiếu giữa Java và một ngôn ngữ khác.
4. Thay `HashSet` bằng store dùng insert-if-absent + TTL phù hợp, test hai request đồng thời với cùng nonce và bảo đảm chỉ một request thành công.
5. Viết policy key rotation với hai public keys cùng tồn tại trong thời gian ngắn; từ chối khóa bị revoke ngay cả khi chữ ký trước đây hợp lệ.
6. Gắn signed context vào một handler thật, đảm bảo ký đủ resource ID, action, tenant, audience, expiry và phân quyền ở tầng ứng dụng.

## 12. Tài liệu tham chiếu chính thức và hiện hành

- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): EdDSA/Ed25519 trong JDK 15.
- [Oracle Java SE 25 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên thuật toán chuẩn của `KeyPairGenerator`, `Signature` và JCA.
- [Oracle Java SE 25 — Signature API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign` và `verify`.
- [Oracle Java SE 25 — KeyPairGenerator API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html): cách tạo cặp khóa bằng provider được cấu hình.
- [Oracle Java SE 25 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): tổng quan engine class và JCA providers.
- [IETF RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421.html): bao phủ trường có ảnh hưởng xử lý, chữ ký HTTP, chống replay, nonce và thời gian; dùng khi cần ký HTTP theo chuẩn.
- [IETF RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785): ví dụ chuẩn hóa JSON xác định để ký nội dung có cấu trúc.
