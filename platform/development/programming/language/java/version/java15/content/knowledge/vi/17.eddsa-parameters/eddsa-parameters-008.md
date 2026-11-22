# EdDSA: Phối hợp tham số giống nhau ở hai bên trong Java 15+

## 1. Mục tiêu: cùng chữ ký chưa đủ, phải cùng cấu hình

Một hệ thống ký số có thể ký bằng **Ed25519** ở máy A nhưng xác minh thất bại ở máy B mặc dù:
- A và B đều gọi API `Signature` của Java.
- Public key B nắm giữ thực sự tương ứng với private key A dùng để ký.
- Chữ ký không bị cắt cụt và được truyền nguyên vẹn.

Lý do thường gặp là **hai bên không ký và kiểm chứng cùng một tổ hợp tham số**: một bên dùng Ed25519 thuần, bên kia dùng **Ed25519ctx**; một bên bật chế độ **prehash**, bên kia không; hoặc cùng dùng một nhãn context bằng chữ nhưng bytes khác vì encoding. EdDSA không tự gửi kèm tất cả các tham số đó trong `byte[] signature`. Giao thức phải quy định và chuyển giao cấu hình một cách đáng tin cậy.

Trong Java, **`java.security.spec.EdDSAParameterSpec`** được bổ sung từ **Java 15** (JEP 339) và vẫn được Javadoc Java hiện hành mô tả. Nó quy định:
- **`prehash`:** chọn chế độ đã prehash trước bước ký EdDSA theo chuẩn.
- **`context`:** chuỗi **byte** cho domain separation khi biến thể thuật toán cho phép; có thể *vắng mặt* hoặc *hiện diện*.

Bên ký và bên xác minh cần phối hợp đồng thời **(a) thuật toán/đường cong, (b) private/public key tương ứng, (c) chế độ prehash, (d) context bytes và trạng thái có/vắng context, (e) chính xác bytes của thông điệp**.

Sau bài, bạn sẽ biết cách thiết lập tham số với `Signature.setParameter(EdDSAParameterSpec)`, phân biệt các biến thể RFC 8032, kiểm thử cấu hình đúng/sai và thiết kế protocol an toàn mà không fallback mù quáng.

## 2. Bốn điều kiện bảo mật và một điều kiện dữ liệu

| Phần cần thống nhất | Phía ký | Phía xác minh | Nếu lệch nhau |
| --- | --- | --- | --- |
| Thuật toán & curve | `Ed25519` hay `Ed448` | Đúng thuật toán, public key cùng curve | Có thể `InvalidKeyException` hoặc chữ ký không hợp lệ |
| Key identity | Private signing key A | Public verification key **tương ứng A**, đã xác thực | Sai public key → `verify` không chấp nhận |
| Chế độ prehash | `EdDSAParameterSpec(true/false)` | Cùng giá trị boolean | Sai mode → signature mismatch |
| Context | Chính xác byte-array, **kể cả có/vắng context** | Cùng bytes và cùng mode | Sai context → signature mismatch |
| Message | `byte[]` đưa vào `Signature.update` | **Chính xác cùng bytes** | Dữ liệu khác → verify fail |

**Chìa khóa:** Hãy nhìn chữ ký EdDSA như kết quả của một hàm phụ thuộc vào **key + thuật toán + mode + context + message bytes**, chứ không phải chỉ phụ thuộc vào text hiển thị của message.

EdDSA cung cấp chữ ký số, **không tự mã hóa thông điệp**. Một chữ ký xác minh thành công với một public key không đủ chứng minh danh tính nếu key đó chưa được gắn với người gửi qua một nguồn tin cậy. Context giúp tách phạm vi sử dụng chữ ký, nhưng **không thay thế** việc xác thực khóa công khai, chống replay hoặc bảo vệ tính bí mật.

## 3. Các mode EdDSA và EdDSAParameterSpec

Java SE 15 giới thiệu `EdDSAParameterSpec` với hai constructor:

```java
import java.security.spec.EdDSAParameterSpec;

// Context vắng mặt (Optional.empty):
EdDSAParameterSpec noContext = new EdDSAParameterSpec(false);

// Context hiện diện (được sao chép vào spec):
byte[] label = "example/order/v1"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
EdDSAParameterSpec withContext = new EdDSAParameterSpec(false, label);

// Chế độ prehash với cùng context:
EdDSAParameterSpec prehashed = new EdDSAParameterSpec(true, label);
```

Các đoạn trên là mã minh họa trong một phương thức hoặc initializer; ví dụ Java hoàn chỉnh ở mục 8.

Theo Javadoc của `EdDSAParameterSpec` và RFC 8032:

| Curve | `prehash` | Context | Mode/ý nghĩa |
| --- | --- | --- | --- |
| Ed25519 | `false` | **Không có** | **Ed25519** (pure) |
| Ed25519 | `false` | **Có** (kể cả mảng rỗng theo API) | **Ed25519ctx** |
| Ed25519 | `true` | Có hoặc không, theo hợp đồng mode | **Ed25519ph** |
| Ed448 | `false` | Có hoặc không, context mặc định theo chuẩn | **Ed448** |
| Ed448 | `true` | Có hoặc không, context theo chuẩn | **Ed448ph** |

Tên `Signature.getInstance("Ed25519")` xác định **curve/algorithm family**, trong khi `EdDSAParameterSpec` chọn biến thể pure/context/prehash áp dụng cho curve đó. Không giả định `Signature.getInstance("Ed25519")` có thể tự nhận ra mode từ chữ ký.

### 3.1. Vắng context khác context rỗng

Javadoc nêu rõ:
- `new EdDSAParameterSpec(false)` → **không có context**, `getContext()` là `Optional.empty()`.
- `new EdDSAParameterSpec(false, new byte[0])` → **có context** với độ dài 0, `getContext().isPresent() == true`.

Hai trạng thái **có thể biểu thị hai mode khác nhau**. Với **Ed25519**, chúng thực sự tạo ra khác biệt giữa Ed25519 thuần và Ed25519ctx có context rỗng. Bộ kiểm thử ở mục 8 xác nhận chữ ký pure **không** verify được khi đổi sang mode có mảng context rỗng.

Vì thế, đừng mã hóa cấu hình thành chỉ một chuỗi text rồi dùng `null` và `""` thay thế tự do. Có thể định nghĩa một enum/protocol field phân biệt **ABSENT** và **PRESENT**. Trong ứng dụng thật, RFC 8032 khuyến nghị context của Ed25519ctx **không rỗng**; mode có context rỗng được nhắc đến để kiểm thử ranh giới, không phải lựa chọn mặc định khuyên dùng.

### 3.2. Context có độ dài tối đa 255 **byte**, không phải 255 ký tự

Constructor `new EdDSAParameterSpec(prehash, contextBytes)` chấp nhận mảng byte không null, nhưng **ném `InvalidParameterException` nếu mảng dài hơn 255 byte**. Truyền null vào constructor hai tham số sẽ ném `NullPointerException`.

Ví dụ:

```java
byte[] tooLong = new byte[256];
// new EdDSAParameterSpec(false, tooLong);
// Dòng trên cố ý tạo InvalidParameterException.
```

Khi context được viết bằng chữ có dấu tiếng Việt, `"đơn-hàng/v1"` có thể có số **UTF-8 bytes** lớn hơn số ký tự nhìn thấy. Kiểm tra `label.getBytes(StandardCharsets.UTF_8).length`, không chỉ `label.length()`. Đồng thời phải quy định cách chuyển thành bytes (UTF-8, normalization, case, dấu cách...) cho cả hai phía.

### 3.3. Context được sao chép, không phải tham chiếu sống

Đối tượng `EdDSAParameterSpec` sao chép context khi tạo, và `getContext()` trả một bản sao byte-array trong `Optional`. Vì vậy sửa mảng input sau khi xây spec **không đổi context đã gắn vào spec**, và sửa mảng nhận từ getter **không đổi context bên trong**.

Đây là một hành vi quan trọng để tránh bug do shared mutable byte arrays. Bộ kiểm thử ở mục 8 có các ca cho cả hai hướng sao chép.

## 4. Prehash là mode của EdDSA, không phải “tự băm trước cho tiện”

Chế độ **prehash** được RFC 8032 định nghĩa riêng:
- **Ed25519ph:** dùng prehash SHA-512 theo quy trình Ed25519ph và có domain separation thích hợp.
- **Ed448ph:** dùng prehash SHAKE256 theo quy trình Ed448ph.
- **Ed25519 thuần** và **Ed448 thuần** xử lý thông điệp theo mode không prehash.

Khi dùng Java JCA:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(true, contextBytes));
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
```

Đây là đoạn dùng trong ngữ cảnh đã có `contextBytes`, `privateKey`, `messageBytes` và các import JCA.

**Không làm thế này để thay cho Ed25519ph:**

```java
// Sai về mục tiêu nếu bạn cần biến thể Ed25519ph chuẩn.
byte[] digest = java.security.MessageDigest
        .getInstance("SHA-512").digest(messageBytes);
Signature s = Signature.getInstance("Ed25519");
s.initSign(privateKey);
s.update(digest);
byte[] nonEquivalentSignature = s.sign();
```

Đoạn phản ví dụ trên ký chữ ký **Ed25519 thuần của digest**; nó **không tương đương** chữ ký Ed25519ph theo RFC 8032, vốn còn bao gồm các quy tắc domain separation và message processing của mode riêng. Với JCA, hãy truyền **message gốc** vào `update` và đặt `new EdDSAParameterSpec(true, ...)` để provider thực hiện đúng prehash.

Cũng không dùng tên algorithm tự bịa như `SHA512withEd25519` hoặc `Ed25519ph` trong `Signature.getInstance(...)` mà không có hợp đồng provider cụ thể. Cách chuẩn được minh họa ở đây là **`Signature.getInstance("Ed25519")` + `EdDSAParameterSpec`**.

## 5. Context dùng để tách mục đích, nhưng không thay cho metadata

Context là **bytes xác định miền sử dụng** (*domain separation*). Một nhãn như `"example/order/v1"` có thể làm cho chữ ký ký trong chức năng “duyệt đơn hàng v1” không hợp lệ trong một chức năng EdDSA mode/context khác, dù hai chức năng dùng cùng private key và message bytes.

Nhưng cần hiểu giới hạn:

- Context **không bí mật** và không phải password/nonce.
- Context **không tự xác minh danh tính** hay cấp quyền; key đang dùng vẫn phải đáng tin.
- Context **không tự chống replay**: cùng message và cùng context được ký trước đó vẫn có thể bị gửi lại nếu ứng dụng không thêm nonce, timestamp có giới hạn, sequence number hoặc workflow state phù hợp.
- **Phải thiết kế context rõ ràng và nhất quán:** role/application ID, protocol version, purpose và contract encoding được ghi vào đặc tả, không dựa vào một chữ mô tả mơ hồ.
- Không lấy một context Unicode mà một phía NFC còn phía kia NFD rồi giả định bytes giống nhau. Nếu cần normalize, thực hiện theo định dạng chuẩn đã đồng thuận **trước khi mã hóa UTF-8**.
- Không thay đổi context tùy ý dựa trên request chưa xác thực. Kẻ tấn công không nên được tự chọn mode hoặc context buộc ứng dụng bỏ qua chính sách bắt buộc.

### Ví dụ về cách định nghĩa protocol metadata

Giao thức có thể xác định một cấu trúc rõ ràng để gắn với chữ ký:

```text
signature_algorithm = Ed25519
signature_mode      = Ed25519ctx
prehash             = false
context_encoding    = UTF-8
context             = example/order/v1
message_format      = canonical JSON bytes, UTF-8
key_id              = tenantA-key-2026-01
signature_encoding  = base64url
```

Các trường trên chỉ là **minh họa một hợp đồng**, không phải JSON schema chuẩn quốc tế. `key_id` phải được ánh xạ tới public key đã tin cậy; `signature_mode` và `context` cần do policy cho phép, không phải các lựa chọn động được mặc định tin từ input.

Giao thức còn phải quy định liệu các metadata như key ID, sequence number, timestamp, algorithm ID có được **nằm trong chính message bytes đã ký** hay không. EdDSA context **không tự động ký tất cả các HTTP headers, JSON fields hoặc metadata bạn tưởng tượng**. Hãy đóng gói/canonicalize và ký đúng dữ liệu cần bảo vệ.

## 6. Quy trình ký và xác minh đối xứng

Có thể mô tả pipeline:

```text
CẤU HÌNH ĐƯỢC ĐỒNG THUẬN/QUẢN LÝ TIN CẬY
   algorithm = Ed25519
   prehash = false
   context = UTF8("example/order/v1")
   message serialization = UTF-8 canonical bytes
                         |
            +------------+------------+
            |                         |
         PHÍA KÝ                  PHÍA XÁC MINH
  private key Ed25519         public key Ed25519
  Signature.getInstance      Signature.getInstance
  setParameter(spec)         setParameter(spec)
  initSign(privateKey)       initVerify(publicKey)
  update(messageBytes)       update(sameMessageBytes)
  sign() -> signature        verify(signature) -> true/false
            |                         ^
            +------ signature -------+
```

Trình tự API nên rõ ràng:

1. Lấy đúng thuật toán, ví dụ `Signature.getInstance("Ed25519")`.
2. Cấu hình `EdDSAParameterSpec` trên **cả hai** `Signature` bằng `setParameter(AlgorithmParameterSpec)`. Đặt **trước** `initSign`/`initVerify` và `update` trong ví dụ để tránh state ambiguity.
3. Bên ký dùng **Ed25519 private key** tương ứng; bên xác minh dùng **public key** đã ràng buộc với danh tính được tin cậy.
4. Truyền chính xác bytes từ cùng canonical serialization vào `update`.
5. Chỉ coi kết quả `verify(signature) == true` là thành công. Kết quả `false` hoặc ngoại lệ do dữ liệu sai phải dẫn đến từ chối, không fallback sang mode khác cho đến khi “pass”.

**`Signature` là đối tượng có trạng thái**. Tạo phiên `Signature` riêng cho mỗi thao tác/luồng hoặc quản lý vòng đời và đồng bộ rõ ràng; không chia sẻ một instance và gọi `update` lẫn lộn từ nhiều thread.

### Mẫu code ký/xác minh ngắn

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.EdDSAParameterSpec;

byte[] context = "example/order/v1"
        .getBytes(StandardCharsets.UTF_8);
byte[] message = "Hop dong: 42"
        .getBytes(StandardCharsets.UTF_8);

// Bên ký, private key được bảo vệ:
Signature a = Signature.getInstance("Ed25519");
a.setParameter(new EdDSAParameterSpec(false, context));
a.initSign(privateKey);
a.update(message);
byte[] signature = a.sign();

// Bên xác minh, public key đã được xác thực:
Signature b = Signature.getInstance("Ed25519");
b.setParameter(new EdDSAParameterSpec(false, context));
b.initVerify(publicKey);
b.update(message);
boolean valid = b.verify(signature);
```

Đoạn này **không phải chương trình độc lập**: `privateKey` và `publicKey` là cặp khóa đã có, các exception được phương thức bao ngoài xử lý. Mục 8 cung cấp chương trình đầy đủ, chạy được ngay.

## 7. Ma trận negative tests để chứng minh tham số thật sự được ràng buộc

Khi đã ký `"Hop dong: 42"` với Ed25519ctx, `prehash=false` và context `"example/order/v1"`, các thay đổi sau phải làm xác minh thất bại:

| Bên xác minh đổi gì? | Kỳ vọng | Vì sao |
| --- | --- | --- |
| Không đổi gì | **True** | Đúng curve, public key, mode, context, message |
| Context đổi từ `v1` sang `v2` | **False** | Context bytes khác |
| Bỏ context hoàn toàn | **False** | Ed25519ctx khác Ed25519 pure |
| Bật `prehash=true` | **False** | Ed25519ph không tương đương Ed25519ctx |
| Message đổi `42` thành `43` | **False** | Bytes đã ký thay đổi |
| Public key Ed25519 của một cặp khác | **False** | Không còn đúng public key của signer |
| Đổi sang public Ed448 nhưng giữ `Signature("Ed25519")` | **Từ chối key** | Sai curve/loại key |
| Cắt/sửa signature | **False hoặc `SignatureException`** | Signature bị phá hỏng/không khớp |

Bên cạnh đó, cần **positive tests**:
- Ed25519 pure ký và verify bằng mode pure.
- Ed25519ph ký và verify bằng `prehash=true`.
- Ed448 ký và verify với đúng context.
- Context input copy và getter copy không tạo lỗi do mảng bị sửa.
- Context >255 byte bị từ chối theo API.

Test cho Ed25519 **pure vs present empty context** đặc biệt cần thiết, vì nhiều người nhầm “mảng byte rỗng” và “không có context” là như nhau. Chúng là hai trạng thái API khác nhau và có thể tạo ra mode khác nhau.

## 8. Chương trình độc lập Java 15: kiểm chứng toàn bộ phối hợp tham số

Chương trình dùng JCA chuẩn, tạo khóa trong runtime và **không xuất private key/seed**. Không phụ thuộc thư viện ngoài. Nó chủ ý in kết quả boolean thay vì signature bytes ngẫu nhiên, để stdout ổn định.

Lưu nguyên tên **`EdDsaParametersDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;
import java.security.interfaces.EdECPublicKey;

public final class EdDsaParametersDemo {
    static final byte[] MESSAGE =
            "Hop dong: 42".getBytes(StandardCharsets.UTF_8);
    static final byte[] CTX =
            "example/order/v1".getBytes(StandardCharsets.UTF_8);
    static final byte[] OTHER =
            "example/order/v2".getBytes(StandardCharsets.UTF_8);

    private static byte[] sign(
            String alg, KeyPair key, EdDSAParameterSpec params, byte[] msg)
            throws Exception {
        Signature s = Signature.getInstance(alg);
        if (params != null) {
            s.setParameter(params);
        }
        s.initSign(key.getPrivate());
        s.update(msg);
        return s.sign();
    }

    private static boolean verify(
            String alg, PublicKey pub, EdDSAParameterSpec params,
            byte[] msg, byte[] sig) throws Exception {
        Signature v = Signature.getInstance(alg);
        if (params != null) {
            v.setParameter(params);
        }
        v.initVerify(pub);
        v.update(msg);
        try {
            return v.verify(sig);
        } catch (SignatureException malformed) {
            // Malformed signature must never be considered verified.
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair ed25519 = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        KeyPair other = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        KeyPair ed448 = KeyPairGenerator.getInstance("Ed448")
                .generateKeyPair();

        EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
        EdDSAParameterSpec withCtx =
                new EdDSAParameterSpec(false, CTX);
        EdDSAParameterSpec withOtherCtx =
                new EdDSAParameterSpec(false, OTHER);
        EdDSAParameterSpec ph =
                new EdDSAParameterSpec(true, CTX);
        EdDSAParameterSpec emptyCtx =
                new EdDSAParameterSpec(false, new byte[0]);

        byte[] sig = sign("Ed25519", ed25519, withCtx, MESSAGE);

        System.out.println("curve: " +
                ((EdECPublicKey) ed25519.getPublic())
                        .getParams().getName());
        System.out.println("context signature verified: " +
                verify("Ed25519", ed25519.getPublic(),
                        withCtx, MESSAGE, sig));
        System.out.println("wrong context verified: " +
                verify("Ed25519", ed25519.getPublic(),
                        withOtherCtx, MESSAGE, sig));
        System.out.println("context omitted verified: " +
                verify("Ed25519", ed25519.getPublic(),
                        pure, MESSAGE, sig));
        System.out.println("wrong prehash verified: " +
                verify("Ed25519", ed25519.getPublic(),
                        ph, MESSAGE, sig));
        System.out.println("wrong bytes verified: " +
                verify("Ed25519", ed25519.getPublic(), withCtx,
                        "Hop dong: 43".getBytes(StandardCharsets.UTF_8), sig));
        System.out.println("wrong public key verified: " +
                verify("Ed25519", other.getPublic(),
                        withCtx, MESSAGE, sig));

        byte[] pureSig = sign("Ed25519", ed25519, pure, MESSAGE);
        System.out.println("pure verified as pure: " +
                verify("Ed25519", ed25519.getPublic(),
                        pure, MESSAGE, pureSig));
        System.out.println("pure verified with empty ctx: " +
                verify("Ed25519", ed25519.getPublic(),
                        emptyCtx, MESSAGE, pureSig));

        byte[] phSig = sign("Ed25519", ed25519, ph, MESSAGE);
        System.out.println("prehash verified with prehash: " +
                verify("Ed25519", ed25519.getPublic(),
                        ph, MESSAGE, phSig));
        System.out.println("prehash verified as normal ctx: " +
                verify("Ed25519", ed25519.getPublic(),
                        withCtx, MESSAGE, phSig));

        EdDSAParameterSpec ed448Ctx =
                new EdDSAParameterSpec(false, CTX);
        byte[] ed448Sig =
                sign("Ed448", ed448, ed448Ctx, MESSAGE);
        System.out.println("Ed448 context verified: " +
                verify("Ed448", ed448.getPublic(),
                        ed448Ctx, MESSAGE, ed448Sig));
        System.out.println("Ed448 wrong context verified: " +
                verify("Ed448", ed448.getPublic(),
                        withOtherCtx, MESSAGE, ed448Sig));
        System.out.println("Ed448 wrong prehash verified: " +
                verify("Ed448", ed448.getPublic(),
                        new EdDSAParameterSpec(true, CTX),
                        MESSAGE, ed448Sig));

        try {
            Signature.getInstance("Ed25519")
                    .initVerify(ed448.getPublic());
            System.out.println("wrong curve rejected: false");
        } catch (InvalidKeyException expected) {
            System.out.println("wrong curve rejected: true");
        }

        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("long context rejected: false");
        } catch (InvalidParameterException expected) {
            System.out.println("long context rejected: true");
        }

        byte[] mutableCtx = CTX.clone();
        EdDSAParameterSpec copy =
                new EdDSAParameterSpec(false, mutableCtx);
        mutableCtx[0] ^= 1;
        System.out.println("context input copied: " +
                Arrays.equals(copy.getContext().orElseThrow(), CTX));

        byte[] returned = copy.getContext().orElseThrow();
        returned[0] ^= 1;
        System.out.println("context getter copied: " +
                Arrays.equals(copy.getContext().orElseThrow(), CTX));

        System.out.println("context absent: " +
                !pure.getContext().isPresent());
        System.out.println("empty context present: " +
                emptyCtx.getContext().isPresent());
    }
}
```

Biên dịch và chạy trên JDK có hỗ trợ đích Java 15:

```bash
javac --release 15 EdDsaParametersDemo.java
java EdDsaParametersDemo
```

**Stdout chính xác** (đã xác minh bằng `javac --release 15` và chạy trên JDK hiện đại với SunEC):

```text
curve: Ed25519
context signature verified: true
wrong context verified: false
context omitted verified: false
wrong prehash verified: false
wrong bytes verified: false
wrong public key verified: false
pure verified as pure: true
pure verified with empty ctx: false
prehash verified with prehash: true
prehash verified as normal ctx: false
Ed448 context verified: true
Ed448 wrong context verified: false
Ed448 wrong prehash verified: false
wrong curve rejected: true
long context rejected: true
context input copied: true
context getter copied: true
context absent: true
empty context present: true
```

Chương trình có **20 dòng stdout**, sử dụng Ed25519 và Ed448 với các tham số chính thức của Java 15. Kết quả nhận được bằng biên dịch `--release 15` và chạy thực tế; không tự đoán chiều dài signature, byte ngẫu nhiên hoặc tiền tố key.

**Phụ thuộc provider:** Những hệ điều hành/Java runtime hoặc HSM có chính sách JCA khác nhau có thể không có Ed448 hoặc chưa hỗ trợ một biến thể EdDSA nào đó, dù Javadoc mô tả API. Khi đó có thể gặp `NoSuchAlgorithmException`, `InvalidAlgorithmParameterException` hoặc `InvalidKeyException`. Đừng tự đổi từ Ed25519ph sang Ed25519 pure hoặc bỏ context để “chạy cho được”. Phải dùng provider hỗ trợ đúng mode hoặc trả lỗi cấu hình.

### 8.1. Vì sao `withCtx` tạo chữ ký khác pure?

`withCtx = new EdDSAParameterSpec(false, CTX)` làm cho Ed25519 chạy theo biến thể **Ed25519ctx**. Phía xác minh với `pure = new EdDSAParameterSpec(false)` dùng mode Ed25519 thường. Hai phép tính domain separation khác nhau, vì vậy chữ ký của bên thứ nhất không hợp lệ với bên thứ hai dù dùng đúng public key và MESSAGE.

Tương tự, `emptyCtx = new EdDSAParameterSpec(false, new byte[0])` vẫn mang trạng thái **context hiện diện**. Điều đó phân biệt với `pure`, dù chuỗi bytes của context dài 0.

### 8.2. Vì sao `ph` không tương đương `withCtx`?

`new EdDSAParameterSpec(true, CTX)` chọn Ed25519ph; `new EdDSAParameterSpec(false, CTX)` chọn Ed25519ctx. Giữ nguyên curve, khóa, context và message nhưng đổi cờ prehash làm biến thể ký số khác. Kết quả “wrong prehash verified: false” và “prehash verified as normal ctx: false” thể hiện ranh giới đó.

**Đừng thực hiện `MessageDigest.digest(...)` ở ngoài rồi ký Ed25519ctx** để thay thế việc đặt cờ prehash. Cần để provider thực thi mode RFC 8032.

### 8.3. Vì sao Ed448 cũng phải cùng context?

Đối với Ed448, `EdDSAParameterSpec(false, CTX)` định nghĩa context bytes dùng trong chữ ký. Khi giữ Ed448 public key và message nhưng đổi context từ `v1` sang `v2`, xác minh không thành công. Đổi `prehash` sang `true` cũng không thành công vì Ed448ph khác Ed448.

Như vậy nguyên tắc **phối hợp tham số** áp dụng với cả Ed25519 và Ed448, nhưng không được tự suy rằng mọi chi tiết context mặc định của hai curve đều giống nhau. Hãy theo Javadoc và RFC tương ứng.

### 8.4. Ca kiểm tra context copy để phòng lỗi trong code nhiều thành phần

Cả constructor và getter của `EdDSAParameterSpec` xử lý context bằng **bản sao**. Demo xác nhận:
- Sửa `mutableCtx[0]` sau khi tạo spec không làm thay đổi context bên trong.
- Sửa bytes từ `copy.getContext().orElseThrow()` không làm thay đổi lần getter tiếp theo.
- `getContext().isPresent()` vẫn phân biệt spec vắng context và spec có mảng rỗng.

Nếu ứng dụng xây context từ cấu hình chung, hãy lấy một cấu hình bất biến ở đầu mỗi thao tác và ghi lại phiên bản policy; đừng vừa ký vừa cho các thread khác sửa/đổi ý nghĩa của context trong cấu hình bên ngoài.

## 9. Mã hóa thông điệp: thống nhất bytes, không chỉ String

EdDSA ký **bytes**, không ký “nội dung người dùng đọc thấy” theo nghĩa trừu tượng. Hai bên có thể dùng đúng Ed25519ctx, đúng context và đúng public key mà vẫn verify fail nếu tạo bytes khác nhau:

```java
String text = "Hợp đồng số 42";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
byte[] utf16le = text.getBytes(StandardCharsets.UTF_16LE);
// Hai byte-array KHÔNG giống nhau.
```

Đây là mã minh họa bên trong một phương thức đã import `java.nio.charset.StandardCharsets`.

Các nguồn khác biệt điển hình:
- UTF-8 vs UTF-16LE, BOM có hoặc không.
- Ký `"\n"` nhưng xác minh `"\r\n"`; khoảng trắng/tab cuối dòng.
- Unicode normalization NFC vs NFD; ví dụ chữ có dấu có thể được mã hóa theo các chuỗi mã Unicode khác nhau nhưng hiển thị giống nhau.
- JSON field order, whitespace, escaping, newline hay cách biểu diễn số; object có nghĩa nghiệp vụ tương tự nhưng bytes serialize khác.
- Chuẩn hóa chữ hoa/thường, `trim()`/`strip()` hoặc URL decoding chỉ ở một phía.
- Ký một phần payload nhưng xác minh toàn bộ payload hoặc ngược lại.

**Cách làm đúng:** Định nghĩa canonical serialization; ký và xác minh **đúng cùng mảng bytes của thông điệp đã chuẩn hóa theo giao thức**. Nếu protocol không có canonicalization, hãy ký nguyên bytes tải lên và kiểm chứng chính nguyên bytes được truyền/được lưu.

Không dùng `new String(bytes)` hoặc `text.getBytes()` không chỉ định charset trong dữ liệu cần tính chính xác xuyên môi trường. Đừng “thử nhiều charset cho đến khi verify true” bởi điều đó xóa bỏ ranh giới định dạng và policy.

## 10. Đảm bảo khả năng tương tác giữa hai hệ thống

Nếu bên ký chạy Java còn bên xác minh chạy thư viện ngôn ngữ khác, một gói chữ ký cần được hai phía hiểu theo **contract** rõ ràng.

Ví dụ một envelope mang metadata (không phải chuẩn có sẵn):

```json
{
  "version": 1,
  "algorithm": "Ed25519",
  "variant": "Ed25519ctx",
  "prehash": false,
  "context_encoding": "UTF-8",
  "context": "example/order/v1",
  "message_format": "canonical-protocol-bytes-v1",
  "key_id": "signing-key-2026-01",
  "signature_encoding": "base64url"
}
```

Trong thực tế phải có một mục dữ liệu chứa chữ ký và một cách tham chiếu bytes được ký. Nếu envelope truyền các field trên từ nguồn không tin cậy, **không tự động dùng mọi field tùy ý**. Thay vào đó:
1. **Kiểm tra version, algorithm và variant qua allow-list của policy.**
2. Resolve `key_id` tới **public key đã tin cậy**.
3. Áp cùng `prehash` và context bytes theo contract; kiểm tra độ dài context.
4. Tái tạo chính xác bytes thông điệp theo message format được quy định.
5. Giải mã signature theo format đã định nghĩa và gọi `verify`.
6. Chỉ tiếp tục nghiệp vụ khi chữ ký hợp lệ **và** các quy tắc authorization, time validity, chống replay được thỏa mãn.

Nếu protocol có thể nâng cấp từ version 1 sang version 2, hãy tách nhãn context và các key scopes/roles để tránh chấp nhận chữ ký từ chức năng này ở chức năng khác. Đừng làm fallback “thử pure, thử ctx, thử ph, thử mọi key” nếu giao thức đòi hỏi đúng một mode; đó có thể biến một cấu hình sai thành việc chấp nhận chữ ký ngoài ý định.

### Thông tin nào nằm trong chữ ký?

Raw Ed25519 signature theo RFC 8032 dài **64 byte**, Ed448 dài **114 byte**. Raw signature không tự đóng gói:
- Tên người ký hoặc chủ sở hữu public key.
- Key ID đáng tin.
- Thuật toán/variant/context mà phía xác minh nên lựa chọn.
- Encoding của thông điệp.
- Timestamp, nonce, sequence number, quyền nghiệp vụ.

Chính sách triển khai phải cung cấp các thông tin ấy qua kênh được xác thực hoặc cấu hình đáng tin. Nếu muốn metadata được ký bảo vệ, hãy định dạng và **đưa metadata cần bảo vệ vào thông điệp được ký** hoặc dùng một signing envelope/protocol đã định nghĩa việc ràng buộc metadata.

## 11. Lỗi phổ biến, loại lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `verify=false` dù đúng cặp khóa | Context/prehash/message bytes khác | Log metadata **không nhạy cảm** về mode/context encoding, kiểm tra exact bytes theo contract |
| `verify=false` khi một bên bỏ context | Pure vs ctx mode khác nhau | Cấu hình rõ ABSENT hoặc PRESENT, không dùng `null` = `byte[0]` |
| `verify=false` sau khi đổi `prehash` | Ed25519ph/Ed448ph khác pure/ctx | Dùng cùng `EdDSAParameterSpec` theo protocol |
| `InvalidKeyException` tại `initVerify` | Public key sai curve/loại, ví dụ Ed448 cho verifier Ed25519 | Dùng đúng EdEC public key và đối chiếu `getParams().getName()` |
| `InvalidAlgorithmParameterException` tại `setParameter` | Provider không hỗ trợ spec/mode hoặc spec không phù hợp | Kiểm tra provider, policy, API và cấu hình; **không tự bỏ mode** |
| `InvalidParameterException` tại constructor | Context quá 255 bytes | Kiểm tra độ dài byte sau khi encode UTF-8 |
| `NullPointerException` tại constructor có context | Truyền null cho tham số byte-array | Dùng constructor một tham số nếu muốn context absent |
| `SignatureException` tại `verify` | Signature malformed hoặc provider không xử lý input | Từ chối; không coi ngoại lệ là xác minh thành công |
| `NoSuchAlgorithmException` | JCA provider không cung cấp tên thuật toán | Cấu hình JDK/provider thích hợp; không tự downgrade |
| Cùng text mà verify fail | Charset, JSON serialization, newline, normalization khác | So sánh **canonical byte representation** hai phía |
| Một bên dùng thư viện khác chỉ hỗ trợ Ed25519 pure | Bên kia chọn Ed25519ctx/Ed25519ph | Thống nhất mode được cả hai bên hỗ trợ **trước khi triển khai**, không thay mode khi verify fail |

**Phân biệt lỗi cú pháp/loại khóa với chữ ký không khớp:** một key sai loại có thể bị từ chối ngay ở `initVerify`; key đúng thuật toán nhưng sai cặp thường dẫn đến `false`. Signature bytes bị cắt/hỏng có thể cho `false` hoặc `SignatureException` tùy provider. Mục tiêu của hệ thống là **fail closed**, không phải cố ép mọi lỗi vào cùng một exception class.

Đừng ghi private key, seed, message nhạy cảm hoặc signature raw của dữ liệu nhạy cảm vào log chỉ để debug. Log an toàn có thể gồm algorithm/variant, key-id đã qua kiểm soát, phiên bản protocol và mã lỗi tổng quát, tuân thủ chính sách bảo vệ dữ liệu.

## 12. Checklist kiểm thử liên hệ nhiều bên

### 12.1. Những ca cần có trong CI

- **Happy path Ed25519:** mode pure, đúng key + bytes → true.
- **Happy path Ed25519ctx:** đúng context (không rỗng), đúng key + bytes → true.
- **Happy path Ed25519ph:** prehash=true ở cả ký và verify → true.
- **Happy path Ed448:** cùng context và prehash → true; thêm test Ed448ph nếu policy hỗ trợ mode này.
- **Wrong context:** thay 1 byte hoặc đổi version label → verify fail.
- **Wrong mode:** ký ctx → verify pure; ký ph → verify ctx → fail.
- **ABSENT vs empty:** Ed25519 pure signature không được chấp nhận khi verifier chọn Ed25519ctx(empty).
- **Wrong message bytes:** đổi 1 ký tự, whitespace, charset, JSON canonicalization → fail.
- **Wrong EdEC key:** Ed25519 keypair khác, Ed448 key trong Ed25519 verifier → fail/exception.
- **Truncated signature:** phải bị từ chối; chấp nhận `verify=false` hoặc `SignatureException` theo hợp đồng provider.
- **Context >255 bytes:** bị từ chối khi tạo spec.
- **Context mutation:** constructor/getter dùng bản sao như Javadoc.
- **Cross-runtime interoperability:** tạo chữ ký từ Java, verify ở môi trường khác và ngược lại bằng **RFC 8032 official test vectors** có đủ key, message, mode, context.

Một bộ test chỉ kiểm tra `Signature.getInstance("Ed25519")` hoạt động là **chưa đủ**; nó không phát hiện lệch mode hay canonicalization. Các negative tests về context/prehash là phần bắt buộc của bài toán phối hợp tham số.

### 12.2. Test vector và kiểm thử ở hệ thống khác

Các giá trị chữ ký trong chương trình mục 8 thay đổi theo keypair ngẫu nhiên mỗi lần chạy, nhưng **đúng/sai của verification là xác định**. Khi viết tests xuyên nhiều ngôn ngữ hoặc library, nên dùng các **test vectors có key, mode, context và message đã biết** trong RFC 8032. Điều này đặc biệt quan trọng khi:
- Một SDK gọi mode “Ed25519ph” nhưng một SDK khác chỉ cung cấp prehash thủ công.
- Một SDK dùng context null và một SDK dùng mảng byte rỗng.
- Một phía dùng raw public key, phía kia dùng X.509 SPKI envelope.
- Một phía ký bytes đã canonicalize, phía kia chỉ ký text hiển thị.

Phải phân biệt **encoding của public key** (raw EdEC point, SPKI, PKCS#8 private key), **encoding của signature khi truyền** (raw, Base64/Base64URL) và **bytes nội dung được ký** (UTF-8 canonical hay binary). Lỗi ở mỗi tầng có phương thức kiểm tra riêng; tham số giống nhau chỉ có nghĩa khi tất cả các tầng đã thống nhất.

## 13. Bảo mật khi triển khai và các giới hạn cần biết

1. **Chọn curve/variant từ policy tin cậy.** Đừng dùng field `algorithm` do người dùng cung cấp để làm ứng dụng thử không giới hạn mọi mode cho đến khi verify true.
2. **Không chuyển Ed25519 signing key thành X25519 key agreement key bằng cách đổi tên algorithm.** EdDSA ký số khác XDH trao đổi khóa.
3. **Không coi context là secret.** Nó có tác dụng domain separation trong mode hỗ trợ, nhưng không thay thế authorization và quản lý key.
4. **Quy định độ dài context theo bytes**, tối đa 255; với Unicode cần cùng quy tắc encoding/normalization.
5. **Không tự prehash nếu mục đích là Ed25519ph/Ed448ph.** Dùng `EdDSAParameterSpec(true, ...)` cho provider thực hiện đúng RFC 8032.
6. **Không tái sử dụng state của `Signature` giữa thread hoặc giữa nghiệp vụ** nếu không quản lý rõ vòng đời; tạo mới như chương trình mẫu.
7. **Đừng tin `verify=true` với public key tự khai báo bởi attacker.** Cần trust anchor, registry hoặc chứng thư được kiểm tra trước.
8. **Ràng buộc dữ liệu nghiệp vụ cần được bảo vệ** vào bytes ký: phiên bản, purpose, đối tượng, scope/role, nonce/timestamp khi có yêu cầu chống replay.
9. **Quản lý khóa riêng:** giữ private signing key trong keystore/HSM nếu phù hợp, giới hạn quyền truy cập, xoay vòng/thu hồi khóa và tránh log secret.
10. **Nếu kết nối mạng, ưu tiên protocol chuẩn** như TLS 1.3 cho kênh truyền. EdDSA signatures không tự mã hóa dữ liệu, và context cũng không tự cung cấp channel security.
11. **Đảm bảo provider compatibility:** test Ed25519ctx, Ed25519ph, Ed448 và Ed448ph đúng trên runtime đích; không suy từ việc hỗ trợ tên Ed25519 rằng mọi mode đã được cấu hình.
12. **Đặt test vector vào CI và contract ở API boundary.** Nếu một nhóm đổi version hoặc context mà không cập nhật consumer, verification phải fail rõ ràng; đừng “sửa” bằng cách nới lỏng policy.

## 14. Bài luyện tập có đáp án

**Câu 1.** Máy A ký Ed25519 với `new EdDSAParameterSpec(false, contextA)`. Máy B dùng đúng public key và message nhưng `new EdDSAParameterSpec(false)`. Có xác minh được không?

**Đáp án:** **Không** trong trường hợp A dùng Ed25519ctx và B dùng Ed25519 pure. Context *hiện diện* làm thay đổi mode; phải thống nhất cả mode và context bytes.

**Câu 2.** `new EdDSAParameterSpec(false)` và `new EdDSAParameterSpec(false, new byte[0])` có giống nhau hoàn toàn không?

**Đáp án:** **Không.** Đối tượng đầu có context **vắng mặt**, đối tượng sau có context **hiện diện nhưng rỗng**. Ed25519 pure khác Ed25519ctx(empty), được xác nhận bằng negative test trong bài.

**Câu 3.** Với chuỗi context tiếng Việt dài 200 ký tự, có chắc thỏa giới hạn 255 byte không?

**Đáp án:** **Không chắc.** Ký tự Unicode có thể dùng nhiều UTF-8 bytes. Dùng `context.getBytes(StandardCharsets.UTF_8).length` và kiểm tra giới hạn bytes.

**Câu 4.** Có thể làm Ed25519ph bằng `SHA-512(message)` rồi gọi `Signature.getInstance("Ed25519")` ở mode pure không?

**Đáp án:** **Không tương đương RFC 8032 Ed25519ph.** Phải dùng `EdDSAParameterSpec(true, ...)` để provider thực hiện prehash và domain separation của mode đúng.

**Câu 5.** Chữ ký Ed448 được tạo bằng context `v1` và mode `prehash=false`. Verifier đổi sang `v2` hoặc `prehash=true` thì sao?

**Đáp án:** **Không xác minh thành công** với cùng message/key; mode hoặc context đã đổi.

**Câu 6.** Vì sao key ID không nên chỉ lấy từ request tự khai báo rồi coi `verify=true` là đúng người ký?

**Đáp án:** Người gửi không tin cậy có thể cung cấp public key của họ cùng chữ ký tương ứng. Phải resolve key ID tới **khóa xác minh đã tin cậy** và kiểm tra quyền/danh tính.

**Câu 7.** Máy A và B cùng Ed25519ctx, cùng chuỗi context hiển thị, nhưng A dùng UTF-8 và B dùng UTF-16LE. Điều gì xảy ra?

**Đáp án:** **Context bytes khác nhau**, nên verification fail. Hãy đặc tả encoding và Unicode normalization của context, không chỉ chuỗi hiển thị.

**Câu 8.** Nếu bên verify thử pure, ctx, ph, mọi context và mọi public key cho đến khi thấy `true`, đó có phải chiến lược compatibility hợp lệ?

**Đáp án:** **Không nên.** Nó bỏ qua policy, tạo ambiguity và nguy cơ nhận chữ ký từ mục đích/khóa ngoài dự kiến. Phải cấu hình một tập mode được phép theo phiên bản giao thức và danh tính khóa đã tin cậy; từ chối khi không khớp.

**Câu 9.** `EdDSAParameterSpec(false, contextBytes)` có giữ tham chiếu đến mảng input không?

**Đáp án:** **Không.** Constructor sao chép mảng; `getContext()` cũng trả mảng sao chép trong `Optional`. Mỗi lần ký/verify nên có cấu hình và message bytes xác định để tránh mutation ở nơi khác.

**Câu 10.** Một hệ thống dùng đúng context/prehash, nhưng JSON serialization bên ký sắp xếp fields khác bên xác minh. Có chắc verify được không?

**Đáp án:** **Không.** EdDSA ký bytes, không ký “object JSON có nghĩa giống nhau”. Cần canonical serialization được thống nhất hoặc truyền nguyên bytes đã ký.

**Tiêu chí hoàn thành:** bạn tự viết được hai lời gọi `Signature` tương thích ở hai phía, diễn giải đúng `EdDSAParameterSpec`, phân biệt absent/empty context, kiểm thử negative contexts và prehash, xử lý exception fail-closed, và thiết kế metadata/bytes có hợp đồng rõ ràng.

## 15. Tài liệu chuẩn còn áp dụng

- [Java SE 15 Javadoc – EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): các constructor, mode RFC 8032, `isPrehash()`, `getContext()`, giới hạn 255 byte và copy semantics (**Since 15**).
- [Java SE 25 Javadoc – EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): xác nhận API vẫn được hỗ trợ và mô tả hiện hành.
- [Java SE 15 Javadoc – Signature](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/Signature.html): `setParameter(AlgorithmParameterSpec)`, `initSign`, `initVerify`, `update`, `sign`, `verify`.
- [Java SE 25 Javadoc – Signature](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): hợp đồng state và exception được duy trì.
- [Java SE 25 Javadoc – NamedParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html): các tên curve `ED25519` và `ED448` để mô tả tham số khóa.
- [Java SE 25 Javadoc – EdECPublicKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html): đọc `getParams()` để kiểm tra curve khi cần.
- [OpenJDK JEP 339 – EdDSA](https://openjdk.org/jeps/339): hỗ trợ Ed25519/Ed448 và biến thể trong Java 15.
- [RFC 8032 – Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): mode pure/context/prehash, quy tắc domain separation, context max 255 octets và official test vectors.
- [Oracle Java 15 Security Developer’s Guide](https://docs.oracle.com/en/java/javase/15/security/): cấu hình provider, SunEC và hỗ trợ các biến thể EdDSA.

**Ghi nhớ:** Để xác minh EdDSA xuyên hai bên, phải đồng nhất **thuật toán/curve + public key tin cậy + prehash + trạng thái/context bytes + message bytes**. Chỉ “cùng Ed25519” là chưa đủ; một chữ ký không tự mang đầy đủ các tham số. Khi mismatch, phải **từ chối**, không thử mọi mode hoặc tự sửa đầu vào cho tới khi được `true`.