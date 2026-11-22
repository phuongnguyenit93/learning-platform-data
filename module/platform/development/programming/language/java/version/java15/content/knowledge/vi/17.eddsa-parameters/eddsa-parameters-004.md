# Ed448, Ed448ph và quy tắc context trong Java 15+

## 1. Mục tiêu: ba giá trị phải khớp, không chỉ một tên thuật toán

Trong họ chữ ký số **EdDSA (Edwards-curve Digital Signature Algorithm)**, **Ed448** và **Ed448ph** là hai chế độ được định nghĩa tại RFC 8032. Java 15 đưa vào `Signature` hỗ trợ EdDSA cùng lớp `java.security.spec.EdDSAParameterSpec`; chúng vẫn là API được hỗ trợ trong Java hiện hành.

Khi dùng Ed448, tính đúng đắn không chỉ phụ thuộc vào cặp khóa công khai/riêng. Cả **bên ký** và **bên xác minh** phải thống nhất ba yếu tố:

1. **Đường cong và thuật toán**: dùng khóa Ed448 và triển khai EdDSA phù hợp.
2. **Chế độ `prehash`**: `false` là Ed448 thuần (*pure*); `true` là **Ed448ph**. Hai chữ ký không thể tự thay thế cho nhau.
3. **Context**: chuỗi **byte** định danh miền sử dụng chữ ký. Context phải khớp chính xác từng byte; độ dài tối đa **255 octet (byte)**.

Ngoài ba yếu tố này, nội dung thông điệp cũng phải được xác minh ở dạng **byte[] giống hệt** dữ liệu đã ký. Một chữ ký hợp lệ **không tự chứng minh danh tính người sở hữu public key**, không tự chống replay và không tự mã hóa thông điệp.

**Kết luận sớm:** với Java, `Signature.getInstance("Ed448")` cộng `EdDSAParameterSpec` là cách rõ ràng để chọn Ed448 thuần, Ed448 có context hoặc Ed448ph. Đừng suy đoán rằng tên Java chuẩn phải là `"Ed448ph"`: `Ed448ph` là tên **chế độ trong RFC**, còn Java JCA chuẩn công bố tên `"Ed448"`/`"EdDSA"` và các tham số lựa chọn mode.

## 2. Ed448 và Ed448ph theo RFC 8032

Ed448 dựa trên đường cong Edwards448. Theo RFC 8032, biến thể Ed448 có độ an toàn mật mã cổ điển danh nghĩa khoảng **224 bit**, public key/seed private key thô **57 byte**, và chữ ký **114 byte**. Hai chế độ Ed448 và Ed448ph dùng **cùng đường cong/cấu trúc chữ ký**, nhưng cách xử lý thông điệp và domain separation khác nhau.

| Thuộc tính | **Ed448 (pure)** | **Ed448ph (prehash)** |
|---|---|---|
| Đường cong | Edwards448 | Edwards448 |
| `phflag` theo RFC 8032 | `0` | `1` |
| Hàm biến đổi thông điệp `PH(M)` | **Chính thông điệp `M`** | **`SHAKE256(M, 64)`**, kết quả 64 byte |
| Phép băm bên trong quy trình chữ ký | `SHAKE256` với đầu ra 114 byte cho các bước cần thiết | `SHAKE256` với đầu ra 114 byte cho các bước cần thiết, trên `PH(M)` đã prehash |
| `context` | 0–255 byte | 0–255 byte |
| Kích thước chữ ký | **114 byte** | **114 byte** |
| Nếu ký đúng key + message + context nhưng khác mode | Chữ ký có giá trị khác Ed448ph | Chữ ký có giá trị khác Ed448 |
| Tên ứng dụng Java trong ví dụ | `Signature("Ed448")`, `EdDSAParameterSpec(false, ...)` | `Signature("Ed448")`, `EdDSAParameterSpec(true, ...)` |

**Không suy luận “ph nhanh hơn” hoặc “ph bảo mật hơn” trong mọi tình huống.** `ph` là một **chế độ được giao thức định nghĩa**, không phải cấp độ bảo mật mới. Chỉ dùng khi giao thức yêu cầu hoặc mọi bên đã thống nhất rõ; chế độ pure thường đủ cho quy trình thông thường khi framework hỗ trợ cập nhật dữ liệu theo từng phần.

### Phân biệt `SHAKE256(M,64)` và `SHAKE256(...,114)`

`SHAKE256` là hàm băm *extendable-output* (XOF), có thể tạo đầu ra theo độ dài yêu cầu. Trong Ed448ph:

- **Prehash** của thông điệp là **`SHAKE256(M, 64)`**, tạo **64 byte**, đúng như RFC 8032 mục 5.2.
- Các bước `H` nội bộ của Ed448 dùng **đầu ra 114 byte**, có thêm dữ liệu domain separation/các giá trị của thuật toán.
- **Chữ ký** vẫn dài **114 byte**; nó **không** trở thành chữ ký 64 byte chỉ vì prehash dài 64 byte.

Đừng tự dùng `SHA-256`, `SHA-512` hay đầu ra `SHAKE256` do ứng dụng tính sẵn rồi đặt `prehash=true`: làm vậy sẽ thay đổi thông điệp mà provider thực sự prehash và có thể tạo **double hashing** không tương thích.

## 3. Context của Ed448: domain separation là gì?

Context là chuỗi byte ngắn, được giao thức lựa chọn để **phân tách miền sử dụng chữ ký**. Ví dụ cùng một private key có thể ký hai loại dữ liệu khác nhau nhưng policy muốn chữ ký của một miền không được tái sử dụng như chữ ký của miền kia.

```text
PrivateKey Ed448
    |
    +-- message bytes = "invoice=42;amount=100"
    |
    +-- prehash=false/true
    |
    +-- context = UTF8("billing:v1")  -> miền thanh toán
                  UTF8("shipping:v1") -> miền vận chuyển
    |
    v
Signature bytes (114 byte)
```

Nếu bên ký chọn `context="billing:v1"`, bên xác minh phải chọn **đúng các byte đó**. Dùng `"shipping:v1"`, context rỗng hoặc không có context thì việc verify chữ ký này **không thành công**.

**Context không phải khóa bí mật**; có thể công khai tên miền context trong metadata của giao thức. Nó không phải số ngẫu nhiên/nonce bắt buộc phải khác nhau cho mọi chữ ký; nó thường là một hằng ổn định theo **mục đích, phiên bản và cách diễn giải thông điệp**.

### 3.1. Giới hạn 255 **byte**, không phải 255 ký tự Java

RFC 8032 cho phép Ed448 và Ed448ph dùng context dài **0 đến 255 octet**. Trong Java, một `String` cần được đổi sang `byte[]`, ví dụ:

```java
byte[] contextBytes = "billing:v1".getBytes(java.nio.charset.StandardCharsets.UTF_8);
EdDSAParameterSpec params = new EdDSAParameterSpec(false, contextBytes);
```

Đây là đoạn minh họa trong phương thức có `import java.security.spec.EdDSAParameterSpec;`, không phải chương trình độc lập. Độ dài được xét là **`contextBytes.length`**, không phải `contextString.length()`. Chẳng hạn chuỗi `"ký"` có **2 ký tự UTF-16** nhưng dài **3 byte UTF-8** (`k` chiếm 1, `ý` chiếm 2).

Với `EdDSAParameterSpec(false, new byte[256])`, constructor ném **`InvalidParameterException`**; `255` byte hợp lệ về mặt giới hạn độ dài. Điều này **không có nghĩa mọi byte content đều đúng chính sách nghiệp vụ**: ứng dụng vẫn cần danh sách context hợp lệ.

### 3.2. Context phải trùng *octet by octet*

Hai chuỗi hiển thị giống nhau có thể không có cùng byte do:

- UTF-8 so với charset khác, bao gồm việc dùng charset mặc định ở một ứng dụng.
- Unicode normalization (NFC/NFD) khác nhau.
- Ký tự trống ở cuối, chữ hoa/chữ thường, khoảng trắng, dấu hai chấm hoặc dấu xuống dòng.
- Chuỗi mô tả domain có thêm version/prefix ở một bên.
- Protocol truyền `Base64` của context nhưng phía kia dùng trực tiếp các ký tự Base64 làm context thay vì giải mã.

**Quy tắc:** mô tả context ở dạng **byte string xác định**, ví dụ UTF-8 của một ASCII identifier cố định: `"billing:invoice:v1"`. Ghi rõ nó nằm ở đâu trong protocol và liệu có được kèm với từng bản tin hay được cấu hình theo service/phiên bản. Không dùng `String.getBytes()` thiếu charset trong code cần interoperability.

### 3.3. `dom4` là cơ chế phân miền của RFC

RFC 8032 định nghĩa domain prefix `dom4(F, C)` với:

```text
dom4(F, C) =
    ASCII("SigEd448") || OCTET(F) || OCTET(length(C)) || C
```

Ở đây `F=0` cho Ed448, `F=1` cho Ed448ph, `C` là **context bytes** 0–255 byte, `||` là nối byte, `OCTET` là một byte biểu diễn giá trị. Prefix này là một thành phần của **thuật toán mật mã**, không phải chuỗi ứng dụng cần tự prepend vào message.

**Đừng tự làm** `sign(prefix + context + message)` để “mô phỏng `EdDSAParameterSpec`”. Nếu làm vậy, đó chỉ là chữ ký cho một thông điệp khác ở chế độ đang chọn, **không tương đương** domain separation của RFC. Hãy để provider triển khai `dom4`.

### 3.4. Context không thay thế xác thực và replay protection

Chữ ký với `billing:v1` có thể chứng minh message được ký dưới context đó nếu public key tin cậy và các tham số khớp. Nó **không** tự ngăn đối thủ phát lại **đúng chữ ký và message trong cùng context**. Ứng dụng vẫn cần kiểm tra nonce, request ID, timestamp, hạn sử dụng, sequence number hoặc cơ chế chống replay khác nếu giao thức yêu cầu.

Cũng không nên dùng cùng private key cho các mục đích không liên quan khi chính sách quản lý khóa yêu cầu **key separation**. Domain separation giảm nguy cơ diễn giải nhầm chữ ký giữa miền, nhưng không thay cho quản trị key ID, rotation và quyền ký.

## 4. Không có context và context rỗng: giống hay khác?

Đây là điểm dễ nhầm trong Java `EdDSAParameterSpec`.

```java
new EdDSAParameterSpec(false);                // context vắng mặt (null về mặt spec)
new EdDSAParameterSpec(false, new byte[0]); // context có mặt nhưng dài 0 byte
```

Hai cấu hình **khác nhau ở trạng thái API**:

- Constructor **một tham số**: không cung cấp context; `getContext()` trả **`Optional.empty()`**.
- Constructor **hai tham số**: context hiện diện; mảng byte có thể **rỗng**; `getContext()` trả `Optional` chứa mảng rỗng.

Javadoc nói rõ các trường hợp này **có thể chọn mode khác nhau**, đặc biệt khi so sánh **Ed25519 thuần** với **Ed25519ctx**. Vì vậy không được đặt quy tắc chung “context null và context rỗng luôn là một” cho **mọi EdDSA**.

**Riêng Ed448 theo RFC 8032**, default context là chuỗi rỗng. Ed448 luôn dùng `dom4`; vì vậy **không cung cấp context và cung cấp context rỗng** cho cùng mode **đưa về cùng context 0 byte**, và trong ví dụ với SunEC của OpenJDK hai chữ ký **giống hệt nhau**. Tuy nhiên, khác biệt ở `Optional` vẫn tồn tại. Đừng đánh mất khả năng biểu diễn “absent” và “present-empty” trong một API hỗ trợ **nhiều curve** rồi mặc định mọi chế độ đều tương đương.

Bảng cách đọc:

| Constructor/spec | `isPrehash()` | `getContext().isPresent()` | Mode trên khóa **Ed448** |
|---|---:|---:|---|
| Không set `EdDSAParameterSpec` trên `Signature("Ed448")` | Theo mặc định của provider | Không áp dụng | Ed448 thuần mặc định theo JDK được minh họa |
| `new EdDSAParameterSpec(false)` | `false` | `false` | Ed448 thuần, context mặc định rỗng |
| `new EdDSAParameterSpec(false, new byte[0])` | `false` | `true` | Ed448 thuần, context rỗng |
| `new EdDSAParameterSpec(false, contextBytes)` | `false` | `true` | Ed448 thuần, context được cung cấp |
| `new EdDSAParameterSpec(true)` | `true` | `false` | Ed448ph, context mặc định rỗng |
| `new EdDSAParameterSpec(true, contextBytes)` | `true` | `true` | Ed448ph, context được cung cấp |

Khi triển khai production, nên **set mode và context tường minh** cho cả bên ký và verify, trừ khi chuẩn giao thức quy định rõ dùng Ed448 thuần/context rỗng mặc định. Đừng dựa vào `Signature.getParameters()` để suy diễn chắc chắn EdDSAParameterSpec: JCA cho phép phương thức này trả `null` khi provider không biểu diễn được tham số dưới dạng `AlgorithmParameters`.

## 5. API Java từ Java 15: `EdDSAParameterSpec`

Lớp nằm ở package `java.security.spec`:

```java
import java.security.spec.EdDSAParameterSpec;
```

Hai constructor chính:

```java
new EdDSAParameterSpec(boolean prehash)
new EdDSAParameterSpec(boolean prehash, byte[] context)
```

`EdDSAParameterSpec` implements `AlgorithmParameterSpec`; nó là **bộ tham số chữ ký**, không chứa private/public key và không thay đổi curve. Curve Ed448 được quyết định ở **key type + Signature algorithm**, ví dụ `KeyPairGenerator` initialize với `NamedParameterSpec.ED448`, còn `Signature.getInstance("Ed448")` xử lý đúng thuật toán.

Các API truy vấn:

- `isPrehash()`: trả `true` nếu chọn mode prehash Ed448ph/Ed25519ph.
- `getContext()`: trả `Optional<byte[]>`. `Optional.empty()` nghĩa là context **không được cung cấp**; nếu có context, API trả **bản sao** của mảng.
- Constructor hai tham số sao chép context đầu vào. Truyền `null` làm `context` cho constructor hai tham số ném **`NullPointerException`**, không phải yêu cầu “không có context”.
- Context dài **hơn 255 byte** ném **`InvalidParameterException`** ở constructor.

Ví dụ an toàn khi đọc:

```java
EdDSAParameterSpec spec =
        new EdDSAParameterSpec(true, "billing:v1".getBytes(StandardCharsets.UTF_8));

boolean prehash = spec.isPrehash();
byte[] context = spec.getContext().orElseThrow();
```

Đoạn này **minh họa trong một method có imports tương ứng**; không phải chương trình độc lập. Trong thực tế, việc lưu/công bố context còn phải gắn với một **protocol version** ổn định; không sử dụng `Optional.get()` nếu bạn chưa xác định context hiện diện.

**Defensive copy không phải một tính năng bảo mật khóa bí mật**: context vốn không bí mật, nhưng việc copy ngăn thay đổi context sau khi đã cấu hình. Nếu source `byte[]` bị sửa ở chỗ khác, spec vẫn dùng context đã copy ban đầu; nếu `getContext()` trả mảng và mảng đó bị sửa, spec vẫn giữ giá trị cũ.

## 6. `Signature` và cách áp dụng `EdDSAParameterSpec`

Đối với Ed448, dùng JCA:

```java
KeyPairGenerator keyGen = KeyPairGenerator.getInstance("EdDSA");
keyGen.initialize(NamedParameterSpec.ED448);
KeyPair pair = keyGen.generateKeyPair();
```

Sau đó ký bằng context và chế độ đã chọn:

```java
Signature signer = Signature.getInstance("Ed448");
signer.initSign(pair.getPrivate());
signer.setParameter(new EdDSAParameterSpec(true, "billing:v1".getBytes(StandardCharsets.UTF_8)));
signer.update(messageBytes);
byte[] signatureBytes = signer.sign();
```

Ở đây:
- `NamedParameterSpec.ED448` chọn **đường cong khi sinh khóa**, không phải context.
- `Signature.getInstance("Ed448")` chọn **thuật toán chữ ký**, có thể chọn mode prehash/context qua `setParameter(AlgorithmParameterSpec)`.
- `new EdDSAParameterSpec(true, ...)` chọn **Ed448ph và context**, cho **cả bên ký và bên verify**.
- `update(messageBytes)` đưa **thông điệp gốc** vào provider. Khi `prehash=true`, provider thực hiện prehash theo RFC, ứng dụng **không đưa sẵn `SHAKE256(M,64)`** trừ phi một API khác ghi rõ nhận prehash digest.

Các đoạn này **minh họa bên trong method** với biến `messageBytes` đã có và imports hợp lệ; ví dụ đầy đủ ở phần 7 chạy độc lập.

Khi xác minh:

```java
Signature verifier = Signature.getInstance("Ed448");
verifier.initVerify(pair.getPublic());
verifier.setParameter(new EdDSAParameterSpec(true, "billing:v1".getBytes(StandardCharsets.UTF_8)));
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
```

Tham số phải được set trước khi truyền message qua `update`/trước khi thực hiện `sign` hoặc `verify`. Ví dụ sử dụng **`initSign/initVerify` rồi `setParameter`**, đã được kiểm thử với SunEC, nhưng nếu provider có quy tắc riêng thì cần kiểm chứng chính API của provider đó. `setParameter` có thể ném `InvalidAlgorithmParameterException` nếu provider không chấp nhận cấu hình.

Không dùng API cũ `Signature.setParameter(String, Object)` — nó đã **deprecated**. Dùng overload nhận `AlgorithmParameterSpec` như trên.

### `Signature.getInstance("Ed448ph")` có phải API chuẩn không?

Java Security Standard Algorithm Names hiện hành công bố `"EdDSA"`, `"Ed25519"` và `"Ed448"` cho `Signature`. Tên `"Ed448ph"` **không phải tên chuẩn độc lập được liệt kê**. Một provider bên thứ ba có thể hỗ trợ alias riêng, nhưng code muốn tương thích nên chọn **`"Ed448"` + `EdDSAParameterSpec(true, ...)`** và kiểm tra provider thực tế, thay vì trông chờ alias `"Ed448ph"`.

## 7. Chương trình Java hoàn chỉnh: đối chiếu context/mode

Ví dụ dùng **JDK 17 trở lên** (API EdDSA có từ Java 15), không cần thư viện ngoài trong JDK có provider Ed448 (chẳng hạn SunEC của OpenJDK/Oracle JDK). Chương trình tạo một cặp khóa ngẫu nhiên mới, nhưng **stdout ổn định** vì chỉ in trạng thái xác minh, độ dài chữ ký và tính nhất quán của context.

Tạo tệp **`Ed448ContextDemo.java`** ở UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidParameterException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;

public class Ed448ContextDemo {
    private static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] sign(PrivateKey privateKey, byte[] message,
            EdDSAParameterSpec params) throws GeneralSecurityException {
        Signature signer = Signature.getInstance("Ed448");
        signer.initSign(privateKey);
        if (params != null) {
            signer.setParameter(params);
        }
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(PublicKey publicKey, byte[] message,
            byte[] signature, EdDSAParameterSpec params)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed448");
        verifier.initVerify(publicKey);
        if (params != null) {
            verifier.setParameter(params);
        }
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(NamedParameterSpec.ED448);
        KeyPair keys = generator.generateKeyPair();

        byte[] message = bytes("invoice=42;amount=100");
        byte[] modified = bytes("invoice=42;amount=900");

        EdDSAParameterSpec empty = new EdDSAParameterSpec(false, new byte[0]);
        EdDSAParameterSpec context = new EdDSAParameterSpec(false, bytes("billing:v1"));
        EdDSAParameterSpec otherContext = new EdDSAParameterSpec(false, bytes("shipping:v1"));
        EdDSAParameterSpec prehashContext = new EdDSAParameterSpec(true, bytes("billing:v1"));

        byte[] pure = sign(keys.getPrivate(), message, null);
        byte[] explicitEmpty = sign(keys.getPrivate(), message, empty);
        byte[] scoped = sign(keys.getPrivate(), message, context);
        byte[] prehashed = sign(keys.getPrivate(), message, prehashContext);

        System.out.println("curve=Ed448");
        System.out.println("signatureBytes=" + pure.length);
        System.out.println("pureValid=" + verify(keys.getPublic(), message, pure, null));
        System.out.println("emptyEqualsAbsent=" + Arrays.equals(pure, explicitEmpty));
        System.out.println("contextValid=" + verify(keys.getPublic(), message, scoped, context));
        System.out.println("otherContextValid=" + verify(keys.getPublic(), message, scoped, otherContext));
        System.out.println("omittedContextValid=" + verify(keys.getPublic(), message, scoped, null));
        System.out.println("modifiedMessageValid=" + verify(keys.getPublic(), modified, scoped, context));
        System.out.println("prehashValid=" + verify(keys.getPublic(), message, prehashed, prehashContext));
        System.out.println("pureAsPrehashValid=" + verify(keys.getPublic(), message, pure,
                new EdDSAParameterSpec(true)));
        System.out.println("prehashAsPureValid=" + verify(keys.getPublic(), message, prehashed, context));
        System.out.println("sameSettingsDeterministic=" + Arrays.equals(scoped,
                sign(keys.getPrivate(), message, context)));
        System.out.println("absentContextPresent="
                + new EdDSAParameterSpec(false).getContext().isPresent());
        System.out.println("emptyContextPresent=" + empty.getContext().isPresent());
        System.out.println("maxContextBytes="
                + new EdDSAParameterSpec(false, new byte[255]).getContext().orElseThrow().length);
        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("overlongContext=accepted");
        } catch (InvalidParameterException exception) {
            System.out.println("overlongContext=InvalidParameterException");
        }

        byte[] source = bytes("billing:v1");
        EdDSAParameterSpec copied = new EdDSAParameterSpec(false, source);
        source[0] = (byte) 'X';
        byte[] retrieved = copied.getContext().orElseThrow();
        retrieved[0] = (byte) 'Y';
        System.out.println("contextDefensiveCopy="
                + Arrays.equals(bytes("billing:v1"), copied.getContext().orElseThrow()));
        System.out.println("utf8ContextBytes=" + bytes("ký").length);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 Ed448ContextDemo.java
java -cp . Ed448ContextDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
curve=Ed448
signatureBytes=114
pureValid=true
emptyEqualsAbsent=true
contextValid=true
otherContextValid=false
omittedContextValid=false
modifiedMessageValid=false
prehashValid=true
pureAsPrehashValid=false
prehashAsPureValid=false
sameSettingsDeterministic=true
absentContextPresent=false
emptyContextPresent=true
maxContextBytes=255
overlongContext=InvalidParameterException
contextDefensiveCopy=true
utf8ContextBytes=3
```

Chương trình không in public/private key hay chữ ký ngẫu nhiên; các dòng đầu ra đo bất biến của thuật toán/chế độ. `emptyEqualsAbsent=true` ở đây được kiểm chứng **riêng cho Ed448** với SunEC, không nên mang sang Ed25519 thuần và Ed25519ctx như một quy tắc chung.

## 8. Giải nghĩa đầy đủ những kết quả của ví dụ

### 8.1. Độ dài chữ ký và xác minh bình thường

`signatureBytes=114` đúng với RFC 8032: chữ ký Ed448 và Ed448ph có cùng kích thước 114 byte. `pureValid=true` chứng minh một chữ ký trên `message` xác minh được bằng đúng khóa công khai.

**Kích thước không xác định mode.** Nếu nhận một chữ ký 114 byte từ mạng, không thể dựa vào kích thước để tự đoán đó là Ed448 thuần hay Ed448ph; cần metadata/hợp đồng giao thức có xác thực.

### 8.2. Context đúng, sai hoặc không có

- `contextValid=true`: bên ký và bên verify dùng cùng `bytes("billing:v1")`, `prehash=false`, cùng message.
- `otherContextValid=false`: cùng key và message nhưng context của verifier là `bytes("shipping:v1")`. Kết quả không hợp lệ.
- `omittedContextValid=false`: chữ ký đã gắn với context không rỗng, nhưng verifier dùng Ed448 không context. Không thể xem đây là chữ ký thuần mặc định.
- `modifiedMessageValid=false`: chỉ đổi `amount=100` thành `amount=900`, chữ ký trên dữ liệu ban đầu không còn hợp lệ.

Các lần verify trên đều dùng chữ ký có đúng định dạng 114 byte; khi truyền chữ ký sai định dạng, API `verify` còn có thể ném `SignatureException` thay vì chỉ trả `false`.

### 8.3. Prehash đúng/sai

- `prehashValid=true`: ký/xác minh cùng `prehash=true` và cùng context.
- `pureAsPrehashValid=false`: chữ ký Ed448 thuần không được chấp nhận là Ed448ph, kể cả khi context mặc định đều là rỗng.
- `prehashAsPureValid=false`: chữ ký Ed448ph có context `billing:v1` không được nhận như Ed448 thuần với cùng context.
- `sameSettingsDeterministic=true`: Ed448 thuần là **deterministic signature**: dùng cùng private key, cùng byte message, cùng context/mode thì chữ ký lặp lại giống nhau. Điều này không có nghĩa chữ ký giống nhau giữa **hai cặp khóa ngẫu nhiên khác nhau**.

Đừng “khắc phục” `prehashValid=false` bằng cách thử toàn bộ mode/context cho đến khi một cái xác minh được. Đó là **algorithm/mode confusion**. Mode phải được quyết định bởi giao thức/chính sách đáng tin, không phải đoán từ chữ ký.

### 8.4. Vắng mặt và rỗng trong Java

`absentContextPresent=false` và `emptyContextPresent=true` cho thấy hai constructor khác nhau về **cấu trúc tham số**. `emptyEqualsAbsent=true` cho thấy với Ed448 thuần đang dùng, chúng rút về cùng context rỗng. Với một API tổng quát hỗ trợ Ed25519, không nên bỏ qua khác biệt giữa **không cung cấp context** và **context rỗng đã cung cấp**.

### 8.5. Giới hạn và defensive copying

- `maxContextBytes=255` cho biết constructor chấp nhận context dài 255 byte.
- `overlongContext=InvalidParameterException` cho biết 256 byte bị từ chối ngay ở bước tạo spec.
- `contextDefensiveCopy=true` cho thấy sửa mảng `source` sau constructor và sửa mảng lấy từ `getContext()` không ảnh hưởng context mà spec đang giữ.
- `utf8ContextBytes=3` cho thấy byte length của `"ký"` khác số ký tự Java hiển thị.

Đây là các bất biến hữu ích để test validation đầu vào của một API nhận context dưới dạng chuỗi.

## 9. Vì sao Ed448ph không phải “tự băm rồi gọi Ed448”?

Lỗi thường thấy là:

```java
// Minh họa SAI nếu mục tiêu là chữ ký Ed448ph của message gốc:
byte[] digest = someDigestOf(message);
Signature signer = Signature.getInstance("Ed448");
signer.initSign(privateKey);
signer.update(digest);
byte[] signature = signer.sign();
```

Đoạn trên **không độc lập** vì `someDigestOf`, `message`, `privateKey` chưa được khai báo. Nó diễn đạt một kiểu sai tư duy, không phải mã khuyến nghị:

- Ed448ph có **`PH(M)=SHAKE256(M,64)`** và **`phflag=1`** trong `dom4`.
- Ed448 thuần ký một `digest` tùy ý vẫn có **`phflag=0`**, nên không thể thay cho Ed448ph.
- Nếu bạn tính `SHAKE256(M,64)` rồi lại gọi `Signature` với `EdDSAParameterSpec(true)`, provider có thể **prehash lần thứ hai** (theo API nhận thông điệp gốc), khiến kết quả khác chuẩn.
- Thao tác `SHA256withEd448` không phải tên chuẩn JCA để chọn prehash; Ed448 dùng SHAKE256 nội bộ theo RFC 8032.

**Đúng:** đưa **thông điệp gốc** vào `update(message)` và cấu hình `EdDSAParameterSpec(true, context)`. Để đối chiếu với một thư viện nhận **digest đã prehash** theo API riêng, phải đọc chính xác hợp đồng của thư viện đó; không thể coi các API tự động tương đương.

### 9.1. Prehash có luôn giảm bộ nhớ?

Không có bảo đảm. `Signature.update` cho phép đưa nhiều khối byte, nhưng cách provider xử lý buffering và prehash là chi tiết triển khai. Prehash có thể hữu ích trong một số thiết kế ký dữ liệu lớn/phân luồng, nhưng **không nên chọn Ed448ph chỉ vì file lớn** hoặc giả định mọi triển khai hỗ trợ streaming cùng một kiểu. Hãy chọn theo protocol, provider và kết quả benchmark/kiểm thử đúng mode.

### 9.2. Tính quyết định của chữ ký không thay cho bảo vệ khóa

Ed448/Ed448ph không đòi hỏi mỗi lần ký phải tự tạo nonce ngẫu nhiên mới ở tầng ứng dụng, nhưng **KeyPairGenerator vẫn phải dùng nguồn ngẫu nhiên mật mã an toàn**, private key cần được bảo vệ và provider cần đáp ứng yêu cầu chống side channel. Deterministic không có nghĩa rằng lặp lại chữ ký làm giảm trách nhiệm quản lý key, chống replay hoặc kiểm soát quyền ký.

## 10. Chuẩn hóa giao thức khi truyền chữ ký có context

Một giao thức dùng Ed448/Ed448ph cần có **metadata đủ rõ**, thí dụ về mặt mô hình:

```text
version:          1
algorithm:        Ed448
mode:             pure | prehash
context-encoding: UTF-8
context:          billing:v1
key-id:           signing-key-2026-01
message:          bytes theo canonicalization đã quy định
signature:        114 bytes (thường truyền Base64 trong JSON)
```

Đây là **mô tả trường hợp**, không phải tiêu chuẩn định dạng sẵn có trong JCA. Các trường cần được ràng buộc bằng hợp đồng giao thức, và dữ liệu version/algorithm/context/key-id quan trọng nên được **xác thực/ràng buộc** để chống sửa metadata và nhầm mục đích. Khi cần, hãy đưa purpose/version vào **chính bytes được ký**, đồng thời dùng context như miền mật mã được quy định.

**Không trao cho người nhận một mode tùy chọn không kiểm soát:** nếu nhận `mode` từ JSON, phải kiểm tra nó trong allowlist/chính sách của endpoint. Không tự chuyển từ Ed448ph sang Ed448 khi chữ ký đầu tiên thất bại chỉ để “tăng tương thích”.

### 10.1. Nên chọn context như thế nào?

Context tốt thường:

- Ngắn, ổn định, độc nhất theo **mục đích sử dụng**.
- Chỉ gồm bytes được mô tả rõ, ví dụ ASCII token hoặc UTF-8 chuẩn hóa.
- Có version khi semantics thay đổi, ví dụ `billing:invoice:v1`.
- Được cấu hình đồng bộ ở signer/verifier.
- Không dùng làm kho chứa toàn bộ message hoặc bí mật; message vẫn phải ký riêng.
- Có chính sách đổi phiên bản, thu hồi key và tránh dùng sai domain.

Nếu một bên có context `"billing:v1"` và bên còn lại có `"billing:v1\n"`, hai context **khác nhau**. Bên nhận không nên tự `trim` context từ message chưa tin cậy trừ khi giao thức quy định chính xác quy trình canonicalization.

### 10.2. Context có giải quyết replay không?

Không. Nếu một yêu cầu đã ký ở `billing:v1` được gửi lại nguyên vẹn đến **cùng endpoint và cùng context**, chữ ký vẫn có thể hợp lệ. Replay protection cần thêm request ID/nonce, timestamp, expiration, sequence, idempotency key hoặc state của người nhận. Context chỉ giới hạn **miền** của chữ ký.

### 10.3. Context có cho phép tái sử dụng khóa Ed448 giữa nhiều hệ thống?

Có thể dùng chung một key trong nhiều miền có context khác nhau nếu giao thức/chính sách cho phép và mọi bên áp dụng đúng, nhưng **không** phải là lời khuyên mặc định dùng chung private key ở mọi hệ thống. Tách khóa theo service, mục đích, môi trường hoặc cấp độ quyền vẫn là một biện pháp quản lý rủi ro quan trọng, nhất là khi sự cố lộ private key ở một miền có thể ảnh hưởng các miền khác.

## 11. Lưu ý đặc biệt khi làm việc với Ed25519

Bài này tập trung **Ed448**, nhưng một thư viện generic hỗ trợ cả Ed25519 cần hiểu rằng **context vắng mặt vs context rỗng** có ngữ nghĩa khác đáng kể.

Theo RFC 8032 và Java `EdDSAParameterSpec`:

- **Ed25519 thuần**: `prehash=false`, **không cung cấp context**.
- **Ed25519ctx**: `prehash=false`, **có context** (RFC khuyến nghị context không rỗng); việc truyền mảng context rỗng vẫn không nên mặc nhiên coi là Ed25519 thuần.
- **Ed25519ph**: `prehash=true` và context nếu giao thức quy định.
- **Ed448 thuần**: `prehash=false` và context có thể rỗng.
- **Ed448ph**: `prehash=true` và context có thể rỗng.

**Đừng viết helper chung** tự thay mọi `null` context bằng `new byte[0]` mà không giữ lại thông tin context có/không: đối với Ed25519 nó có thể thay đổi mode mà người gọi yêu cầu. Trên Ed448 hai trạng thái đưa về context rỗng theo RFC, nhưng một API đa thuật toán vẫn cần biểu diễn rõ khác biệt.

## 12. Kiểm tra runtime provider và ngoại lệ

JCA sử dụng các **security provider**. Oracle/OpenJDK thường có `SunEC` hỗ trợ Ed448 cùng `EdDSAParameterSpec`; nhưng môi trường FIPS, HSM/KMS, bản dựng `jlink` tối giản hoặc JVM của nhà cung cấp khác có thể không hỗ trợ mọi mode/context.

Những lỗi cần phân biệt:

| Biểu hiện | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `NoSuchAlgorithmException` với `"Ed448"` | Provider không có Signature hoặc KeyPairGenerator Ed448 | Kiểm tra phiên bản JDK, modules/provider thực, chọn giải pháp đúng policy |
| `InvalidAlgorithmParameterException` khi `Signature.setParameter` | Provider từ chối `EdDSAParameterSpec` hoặc mode/context không hỗ trợ | Kiểm tra tên thuật toán, provider và mode; không tự downgrade |
| `InvalidParameterException` từ constructor `EdDSAParameterSpec` | Context dài **hơn 255 byte** | Ràng buộc `bytes.length <= 255`, không dùng `String.length()` |
| `NullPointerException` ở constructor hai tham số | Truyền `null` làm `byte[] context` | Dùng constructor một tham số nếu **không cung cấp context** |
| `InvalidKeyException` khi `initSign/initVerify` | Dùng sai key/curve hoặc provider từ chối | Kiểm tra Ed448 private/public key, nguồn khóa, key usage |
| `verify` trả `false` | Message/context/prehash/key không khớp hoặc chữ ký bị sửa | Kiểm tra **byte chính xác**, mode, key ID, không thử fallback tùy tiện |
| `SignatureException` | Input chữ ký sai định dạng, thao tác Signature không hợp lệ hoặc lỗi provider | Phân biệt trường hợp lỗi xử lý với xác minh thông thường ra false |
| `"Ed448ph"` không được nhận diện | Không phải tên thuật toán `Signature` chuẩn độc lập | Dùng `Signature("Ed448")` + `EdDSAParameterSpec(true, ...)` |
| Không tương thích với thư viện ngoài Java | Khác protocol profile, context byte encoding, mode hoặc wire format | Dùng RFC 8032 test vectors/cross-language tests, ghi rõ context |
| Đúng chữ ký nhưng sai người ký | Public key không được xác thực nguồn gốc | Kiểm tra trust store, certificate/key registry, key ID và chính sách quyền |

**Giới hạn của `verify(...)`:** giá trị `true` chỉ chứng minh chữ ký hợp lệ theo thuật toán/khóa/dữ liệu/đúng tham số. Chính ứng dụng phải xác thực **nguồn public key**, tính hợp lệ của nghiệp vụ, nonce, permissions và anti-replay.

### Bài toán FIPS và hậu lượng tử

Tên `Ed448` trong JCA **không tự chứng minh** provider hoặc deployment đạt yêu cầu FIPS/compliance. Phải kiểm tra chính **module/provider được chứng nhận**, chế độ vận hành và chính sách thuật toán tương ứng.

Ed448 và Ed448ph là chữ ký dựa trên ECC **không hậu lượng tử**. Nếu hệ thống cần an toàn trước đối thủ có máy tính lượng tử đủ lớn, phải đánh giá các thuật toán chữ ký hậu lượng tử/giải pháp chuyển đổi theo tiêu chuẩn và độ hỗ trợ hiện hành, không coi Ed448ph là “biến thể hậu lượng tử”.

## 13. Kế hoạch kiểm thử đầy đủ

Một bộ test không nên chỉ ký rồi verify trong cùng function — điều đó có thể bỏ sót lỗi context hoặc lựa chọn mode.

**Nhóm kiểm thử có kết quả quyết định được:**

1. **Đúng Ed448, context rỗng**: ký/verify cùng khóa, cùng message → `true`.
2. **Không cung cấp context vs context rỗng**: với Ed448 thuần trên provider phù hợp RFC → cùng kết quả, nhưng `getContext().isPresent()` khác.
3. **Context đúng**: `billing:v1` ở cả hai phía → `true`.
4. **Context sai**: `billing:v1` ký, `shipping:v1` verify → `false`.
5. **Bỏ context**: ký với `billing:v1`, verify với context rỗng → `false`.
6. **Thông điệp thay đổi**: giữ key/context nhưng đổi một byte message → không xác minh được.
7. **Ed448ph đúng**: `prehash=true` ở cả hai phía, context giống hệt → `true`.
8. **Sai mode**: ký pure, verify prehash hoặc ngược lại → không xác minh được.
9. **Giới hạn context**: `255` byte chấp nhận, `256` byte ném `InvalidParameterException`.
10. **Defensive copy**: sửa byte array đưa vào constructor/nhận từ `getContext()` không thay spec gốc.
11. **UTF-8**: context chứa tiếng Việt kiểm tra độ dài **byte**, không độ dài ký tự.
12. **Wrong public key**: tạo hai cặp Ed448, ký bằng private key của A và verify bằng public key của B → không hợp lệ.
13. **Protocol interop**: sử dụng RFC 8032 test vectors cho Ed448, Ed448ph và context không rỗng; thử một implementation ngoài Java khi yêu cầu tích hợp.

**Nhóm kiểm thử ranh giới nghiệp vụ:** xác thực key registry, key rotation, alias context, version của message canonicalization, replay protection, signature encoding và metadata. Không chấp nhận “tự thử hết mode/context” như một cách fallback.

### Test vector RFC 8032

RFC 8032 mục 7 cung cấp **test vectors cố định** cho Ed448 và Ed448ph, có trường context trong những trường hợp phù hợp. Khi cần kiểm tra interoperability cao hơn một test ký/verify trong cùng JVM, hãy dùng vector có **private seed, public key, message, context và signature** đã định nghĩa, nhưng tuyệt đối không dùng seed của test vector làm khóa sản xuất.

## 14. Checklist thiết kế Ed448/Ed448ph an toàn

- [ ] Chọn thuật toán **Ed448** theo policy và kiểm tra provider hỗ trợ.
- [ ] Xác định **pure hay prehash** ở mức protocol, không đoán từ byte chữ ký.
- [ ] Ghi rõ **context encoding**, giá trị context và version; giới hạn **255 byte**.
- [ ] Chọn `EdDSAParameterSpec(false/true, context)` tường minh khi có context.
- [ ] Nếu không có context, phân biệt **constructor một tham số** với **mảng rỗng hai tham số**, nhất là ở API hỗ trợ Ed25519.
- [ ] Bên ký và bên xác minh dùng cùng `prehash`, context bytes và message bytes.
- [ ] Không tự prehash thông điệp rồi để `Signature` prehash tiếp.
- [ ] Không tự prepend `dom4` hoặc context vào message để giả lập RFC 8032.
- [ ] Không xem context là nonce, khóa bí mật hay cơ chế anti-replay.
- [ ] Bảo vệ private key và kiểm tra trust của public key, key ID, quyền ký.
- [ ] Từ chối thuật toán/mode/context không được phép, không fallback tự động khi verify thất bại.
- [ ] Kiểm thử với JDK/provider thật, RFC test vectors và bên nhận thực tế.

## 15. Kết luận và tài liệu chính thức

**Ed448** và **Ed448ph** dùng cùng đường cong/chữ ký 114 byte nhưng khác **`phflag` và prehash**: pure dùng message gốc `PH(M)=M`, còn Ed448ph dùng `SHAKE256(M,64)` trước phần xử lý mật mã nội bộ. **Context** ràng buộc chữ ký với miền sử dụng, tối đa **255 byte** và phải khớp byte-for-byte khi verify.

Trong **Java 15+**, dùng **`Signature("Ed448")`** và **`EdDSAParameterSpec(prehash, context)`**, truyền **message gốc** cho provider và chọn cùng tham số ở hai phía. Riêng Ed448 theo RFC, context mặc định rỗng và context rỗng tường minh tương đương về mật mã, nhưng **`Optional.empty()` và `Optional.of(new byte[0])` vẫn khác nhau về hình thức API**. Không mở rộng quy tắc đó một cách mù quáng sang Ed25519ctx.

Tài liệu chuẩn đang áp dụng:

- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032.html): mục 2 (`dom4`), 5.2 (Ed448 và Ed448ph), 7 (test vectors).
- [Oracle Java SE 26 — `EdDSAParameterSpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): constructors, prehash, context và giới hạn 255 byte.
- [Oracle Java SE 26 — `Signature`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html), [`NamedParameterSpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/NamedParameterSpec.html).
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên chuẩn EdDSA, Ed25519, Ed448.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): tính năng được đưa vào Java 15; API vẫn là thành phần hiện hành của JCA.
