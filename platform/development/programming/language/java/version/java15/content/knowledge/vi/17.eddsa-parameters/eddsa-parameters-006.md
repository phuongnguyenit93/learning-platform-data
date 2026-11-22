# Giới hạn độ dài context trong EdDSA (Java 15+)

> **Chủ đề cha: Tham số EdDSA.** Trong Java 15 trở lên, `java.security.spec.EdDSAParameterSpec` dùng để cấu hình chế độ Ed25519/Ed448, trong đó có tùy chọn **context**. Theo RFC 8032 và Javadoc hiện hành, context có độ dài **tối đa 255 octets (255 bytes)**. Giới hạn này áp dụng cho **mảng byte context**, **không phải** số ký tự trong `String`, số code point Unicode, số UTF-16 code units hay độ dài dữ liệu được ký. Dữ liệu cần ký có thể dài hơn 255 bytes.

Bài sử dụng API còn được hỗ trợ trong Java hiện đại; các ví dụ hoàn chỉnh đã được biên dịch với `javac --release 17` và chạy trên JDK 24.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phát biểu chính xác giới hạn: **`0 ≤ context.length ≤ 255`**, với `context` là `byte[]`.
2. Hiểu **context**, **message** và **key** là ba dữ liệu khác nhau; giới hạn 255 không áp dụng cho message hay khóa.
3. Dùng hai constructor `EdDSAParameterSpec(boolean prehash)` và `EdDSAParameterSpec(boolean prehash, byte[] context)`, đồng thời nắm khác biệt **không cung cấp context** và **cung cấp mảng rỗng**.
4. Bắt đúng ngoại lệ `InvalidParameterException` với context có 256 bytes, và `NullPointerException` với `null` ở constructor hai tham số.
5. Đếm giới hạn an toàn bằng `context.getBytes(StandardCharsets.UTF_8).length` sau khi xác định quy tắc encoding; không dùng `String.length()` để kết luận.
6. Cấu hình `Signature` với cùng context ở phía ký và kiểm tra; phân biệt Ed25519 thuần, Ed25519ctx, Ed25519ph, Ed448 và Ed448ph.
7. Xử lý Unicode/malformed UTF-16, normalization, domain separation, tính tương thích và chính sách bảo mật khi có nhiều dịch vụ.
8. Viết negative tests cho độ dài 255/256, thiếu context, context khác, chế độ prehash khác và message dài hơn 255.

## 2. Context là gì và tại sao chỉ được dài 255 bytes?

### 2.1. Context là một chuỗi byte tách biệt với message

Trong các biến thể EdDSA có context, người ký và người xác minh thống nhất một chuỗi byte ngắn để **ràng buộc chữ ký vào ngữ cảnh sử dụng**, ví dụ định danh giao thức:

~~~text
context = UTF8("com.example.billing:receipt-v1")
message = bytes của hóa đơn thực sự
private key = khóa ký
public key  = khóa xác minh

Sign(privateKey, context, message)
Verify(publicKey, same context, same message, signature)
~~~

Context không được coi là phần văn bản bất kỳ mà bạn có thể thay sau khi ký: nếu context dùng lúc xác minh khác các bytes mà signer đã dùng, chữ ký thường bị từ chối.

Nó hữu ích để giảm nguy cơ một chữ ký được tạo cho ứng dụng/giao thức A bị chấp nhận bởi ứng dụng/giao thức B dùng cùng cặp khóa. Tuy nhiên context **không chứng thực danh tính**, không cấp quyền và không làm message bí mật. Bên nhận vẫn phải tin cậy public key, hiểu đúng protocol và kiểm tra authorization.

### 2.2. Vì sao là 255?

RFC 8032 dùng một **octet** để biểu diễn độ dài context khi tạo giá trị *domain separation*:

~~~text
dom2(phflag, C) cho Ed25519ctx/Ed25519ph:
    prefix || byte(phflag) || byte(length(C)) || C

dom4(phflag, C) cho Ed448/Ed448ph:
    prefix || byte(phflag) || byte(length(C)) || C

Giới hạn: 0 ≤ length(C) ≤ 255 octets.
~~~

`prefix` là chuỗi cố định theo RFC 8032; không phải một chuỗi tùy ý do ứng dụng tự đặt. Một octet độ dài chỉ biểu diễn các số `0..255`, nên context dài **256 bytes không có representation hợp lệ** trong các chế độ trên.

Đây là **giới hạn của tham số context**, không phải giới hạn độ dài chữ ký, khóa hay message. Với message có kích thước lớn, các API `Signature.update(...)` có thể nhận nhiều đợt dữ liệu; tất nhiên bộ nhớ, tốc độ và giới hạn của ứng dụng vẫn phải được kiểm soát.

### 2.3. Bảng phân biệt các độ dài

| Dữ liệu | Đơn vị/độ dài | Có áp dụng giới hạn 255 bytes của context? |
| --- | --- | --- |
| `byte[] context` | **0 đến 255 bytes** | **Có** |
| `String contextText` | UTF-16 code units khi gọi `length()` | Không phải cách đo giới hạn |
| `String` sau khi encode UTF-8 | `getBytes(UTF_8).length` | **Có**, nếu bytes này được dùng làm context |
| `byte[] message` | Message bytes cần ký | **Không** |
| Ed25519 signature | 64 bytes | Không; là định dạng chữ ký |
| Ed448 signature | 114 bytes | Không; là định dạng chữ ký |
| Ed25519 public key raw | 32 bytes | Không; là khóa công khai |
| Ed448 public key raw | 57 bytes | Không; là khóa công khai |

Vì thế không nên viết “chữ ký EdDSA chỉ hỗ trợ thông điệp tối đa 255 ký tự”. Đây là sự nhầm lẫn giữa **context** và **message**.

## 3. API `EdDSAParameterSpec` vẫn dùng trong Java hiện đại

Class `java.security.spec.EdDSAParameterSpec` được giới thiệu ở Java 15 (JEP 339) và tiếp tục được tài liệu Java SE 25 mô tả. Nó triển khai `AlgorithmParameterSpec`, có hai constructors:

~~~java
// Đoạn minh họa trong phương thức, chưa phải chương trình độc lập.
import java.security.spec.EdDSAParameterSpec;

// Không cung cấp context:
EdDSAParameterSpec noContext =
    new EdDSAParameterSpec(false);

// Context hiện diện, dài 0 bytes:
EdDSAParameterSpec emptyContext =
    new EdDSAParameterSpec(false, new byte[0]);

// Context dài 255 bytes:
EdDSAParameterSpec maxContext =
    new EdDSAParameterSpec(false, new byte[255]);
~~~

**`prehash`** là cờ chọn chế độ *prehash* của RFC 8032, không phải một phương thức “nén context cho ngắn hơn”. Cả `prehash=false` và `prehash=true` đều chịu giới hạn **255 bytes** khi context hiện diện.

### 3.1. Hai constructor và ngoại lệ

| Câu lệnh | Kết quả |
| --- | --- |
| `new EdDSAParameterSpec(false)` | Context **không hiện diện**; `getContext().isEmpty() == true` |
| `new EdDSAParameterSpec(false, new byte[0])` | Context **hiện diện nhưng rỗng**; `getContext().isPresent() == true` |
| `new EdDSAParameterSpec(false, new byte[255])` | Được chấp nhận; context dài 255 bytes |
| `new EdDSAParameterSpec(false, new byte[256])` | Ném `InvalidParameterException` |
| `new EdDSAParameterSpec(false, (byte[]) null)` | Ném `NullPointerException` |
| `new EdDSAParameterSpec(true, new byte[255])` | Được chấp nhận; prehash không nâng giới hạn |

`InvalidParameterException` là lớp con của `IllegalArgumentException`, nhưng nên nêu đúng tên ngoại lệ khi giải thích hành vi của constructor. Lỗi này xảy ra **khi tạo `EdDSAParameterSpec`**, chưa cần đến `Signature.sign()` hoặc `Signature.verify()`.

### 3.2. `getContext()` trả về `Optional<byte[]>`

~~~java
// Minh họa. values đang là EdDSAParameterSpec hợp lệ.
boolean hasContext = values.getContext().isPresent();
byte[] bytes = values.getContext().orElseThrow();
int length = bytes.length;
~~~

- Với constructor một tham số, `getContext()` trả `Optional.empty()`.
- Với constructor hai tham số và mảng rỗng, nó trả `Optional` **có mặt**, nhưng length là `0`.
- Javadoc nêu constructor **sao chép** mảng context, và `getContext()` trả về **bản sao**. Sửa mảng nguồn hoặc mảng nhận từ getter không làm thay đổi tham số đang lưu.
- `getContext().orElseThrow()` chỉ thích hợp khi bạn biết context hiện diện; nếu không, xử lý `Optional` đúng cách.
- Dữ liệu context được lưu như bytes, không tự encode/decode `String` và không tự normalize Unicode.

## 4. Chọn chế độ EdDSA: “absent” và “empty” không luôn tương đương

Một điểm dễ gây lỗi tương tác là **mảng rỗng** không nhất thiết đồng nghĩa **không cung cấp context**.

| Thuật toán `Signature` | `prehash` | Context trong `EdDSAParameterSpec` | Ý nghĩa theo RFC/JCA |
| --- | --- | --- | --- |
| `Ed25519` | `false` | **Không hiện diện** | Ed25519 thuần (*pure Ed25519*) |
| `Ed25519` | `false` | **Hiện diện**, kể cả mảng rỗng | Ed25519ctx (RFC khuyên context không rỗng) |
| `Ed25519` | `true` | Có hoặc không có context | Ed25519ph, với chế độ context tương ứng |
| `Ed448` | `false` | Có hoặc không, có thể rỗng | Ed448 với context (rỗng là giá trị mặc định) |
| `Ed448` | `true` | Có hoặc không, có thể rỗng | Ed448ph |

**Điểm mấu chốt cho Ed25519:**

~~~text
no context:
    new EdDSAParameterSpec(false)
    -> Ed25519 thuần, dom2 không thêm prefix

present but empty context:
    new EdDSAParameterSpec(false, new byte[0])
    -> Ed25519ctx với context 0 bytes, có dom2 prefix
    -> không phải cùng chế độ ký như Ed25519 thuần
~~~

RFC 8032 khuyến cáo `Ed25519ctx` **không nên dùng context rỗng**. Nếu dùng Ed25519 thuần vì một protocol yêu cầu, hãy để context **absent** thay vì vô tình truyền `new byte[0]`. Với Ed448, RFC 8032 luôn có cơ chế `dom4` và giá trị context mặc định là rỗng; trong provider JDK đã kiểm thử, “absent” và “present but empty” cho kết quả xác minh tương đương khi `prehash=false`.

**Không dùng “context là Optional rỗng” và “context byte[] rỗng” như một quy ước chung cho mọi biến thể**. Cần mô tả rõ trong protocol rằng dùng Ed25519 thuần, Ed25519ctx, Ed25519ph, Ed448 hay Ed448ph.

## 5. Ví dụ 1 — Chứng minh giới hạn 255 bytes và sự khác nhau giữa ký tự/bytes

**Tệp `EdDSAContextLimitDemo.java` — độc lập, Java 17+:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.InvalidParameterException;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class EdDSAContextLimitDemo {
    public static void main(String[] args) {
        EdDSAParameterSpec absent = new EdDSAParameterSpec(false);
        EdDSAParameterSpec empty = new EdDSAParameterSpec(
                false, new byte[0]);
        System.out.println("absentPresent=" +
                absent.getContext().isPresent());
        System.out.println("emptyPresent=" +
                empty.getContext().isPresent());
        System.out.println("emptyLength=" +
                empty.getContext().orElseThrow().length);

        EdDSAParameterSpec max = new EdDSAParameterSpec(
                false, new byte[255]);
        System.out.println("maxLengthAccepted=" +
                max.getContext().orElseThrow().length);

        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("overLimitRejected=false");
        } catch (InvalidParameterException expected) {
            System.out.println("overLimitRejected=true");
        }

        try {
            new EdDSAParameterSpec(false, null);
            System.out.println("nullRejected=false");
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        String accented = "\u00E9".repeat(128);
        byte[] utf8 = accented.getBytes(StandardCharsets.UTF_8);
        System.out.println("accentedUtf16Units=" +
                accented.length());
        System.out.println("accentedUtf8Bytes=" + utf8.length);

        try {
            new EdDSAParameterSpec(false, utf8);
            System.out.println("utf8OverLimitRejected=false");
        } catch (InvalidParameterException expected) {
            System.out.println("utf8OverLimitRejected=true");
        }

        String smile = new String(Character.toChars(0x1F642))
                .repeat(64);
        System.out.println("emojiCodePoints=" +
                smile.codePointCount(0, smile.length()));
        System.out.println("emojiUtf16Units=" + smile.length());
        System.out.println("emojiUtf8Bytes=" +
                smile.getBytes(StandardCharsets.UTF_8).length);

        byte[] source = "context-v1"
                .getBytes(StandardCharsets.UTF_8);
        EdDSAParameterSpec copied = new EdDSAParameterSpec(
                false, source);
        byte first = source[0];
        source[0] = 'X';
        System.out.println("constructorCopies=" +
                (copied.getContext().orElseThrow()[0] == first));

        byte[] exposed = copied.getContext().orElseThrow();
        exposed[0] = 'Y';
        System.out.println("getterCopies=" +
                (copied.getContext().orElseThrow()[0] == first));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 EdDSAContextLimitDemo.java
java EdDSAContextLimitDemo
~~~

**Stdout xác định** (đã đối chiếu trên JDK 24):

~~~text
absentPresent=false
emptyPresent=true
emptyLength=0
maxLengthAccepted=255
overLimitRejected=true
nullRejected=true
accentedUtf16Units=128
accentedUtf8Bytes=256
utf8OverLimitRejected=true
emojiCodePoints=64
emojiUtf16Units=128
emojiUtf8Bytes=256
constructorCopies=true
getterCopies=true
~~~

### 5.1. Phân tích từng phần

**255 được chấp nhận, 256 bị từ chối:** Constructor hai tham số cho phép context dài đến **255 bytes** bao gồm cả 255; 256 vượt giới hạn và ném `InvalidParameterException` ngay.

**Không cung cấp khác mảng rỗng:** Cờ `getContext().isPresent()` cho thấy hai trạng thái riêng biệt; điều này liên quan trực tiếp tới cách Ed25519 thuần và Ed25519ctx tính domain separation.

**“128 ký tự” có thể là 256 bytes:**
- `"\u00E9"` (é tiền tổ hợp) là 1 UTF-16 code unit nhưng encode UTF-8 thành **2 bytes**. Lặp 128 lần tạo 128 code units và **256 bytes**.
- Emoji `🙂` có 1 Unicode code point, thường dùng **2 UTF-16 code units** và **4 UTF-8 bytes**; lặp 64 lần có 64 code points, 128 code units và **256 bytes**.
- Cả hai ví dụ đều vượt giới hạn `255` dù số “ký tự” theo cách đếm quen thuộc nhỏ hơn 255.

**Bản sao mảng:** `EdDSAParameterSpec` không giữ trực tiếp tham chiếu tới mảng nguồn. Việc sửa `source` hoặc mảng lấy từ `getContext()` không làm thay đổi context đã được cấu hình; điều này giảm nguy cơ lỗi do vô tình thay đổi mảng giữa lúc ký/verify.

## 6. Ví dụ 2 — Giới hạn context không phải giới hạn message; hai bên phải dùng cùng context

Trong ví dụ này, một `Signature` engine được cấu hình như sau:

~~~java
// Đoạn mã minh họa bên trong một phương thức:
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.setParameter(new EdDSAParameterSpec(
        false, contextBytes));
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Bên xác minh phải chọn **cùng thuật toán, cùng chế độ prehash, cùng context bytes và cùng message bytes**.

**Tệp `EdDSAContextSignatureDemo.java` — chương trình độc lập Java 17+:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class EdDSAContextSignatureDemo {
    static byte[] sign(String algorithm, PrivateKey privateKey,
                       byte[] message, EdDSAParameterSpec parameters)
            throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(privateKey);
        if (parameters != null) {
            signer.setParameter(parameters);
        }
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(String algorithm, PublicKey publicKey,
                          byte[] message, byte[] signature,
                          EdDSAParameterSpec parameters) throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(publicKey);
        if (parameters != null) {
            verifier.setParameter(parameters);
        }
        verifier.update(message);
        return verifier.verify(signature);
    }

    static void run(String algorithm) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance(algorithm)
                .generateKeyPair();
        byte[] message = "approve build #42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] contextA = "release-v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] contextB = "billing-v1"
                .getBytes(StandardCharsets.UTF_8);

        EdDSAParameterSpec a =
                new EdDSAParameterSpec(false, contextA);
        EdDSAParameterSpec b =
                new EdDSAParameterSpec(false, contextB);
        EdDSAParameterSpec empty =
                new EdDSAParameterSpec(false, new byte[0]);
        EdDSAParameterSpec absent =
                new EdDSAParameterSpec(false);

        byte[] signature = sign(
                algorithm, pair.getPrivate(), message, a);

        System.out.println(algorithm + ".sameContext=" +
                verify(algorithm, pair.getPublic(),
                        message, signature, a));
        System.out.println(algorithm + ".differentContextRejected=" +
                !verify(algorithm, pair.getPublic(),
                        message, signature, b));
        System.out.println(algorithm + ".absentContextRejected=" +
                !verify(algorithm, pair.getPublic(),
                        message, signature, absent));

        byte[] defaultSignature = sign(
                algorithm, pair.getPrivate(), message, null);
        byte[] emptySignature = sign(
                algorithm, pair.getPrivate(), message, empty);

        System.out.println(algorithm + ".defaultVsEmptySameBytes=" +
                Arrays.equals(defaultSignature, emptySignature));
        System.out.println(algorithm + ".defaultVerifyWithEmpty=" +
                verify(algorithm, pair.getPublic(),
                        message, defaultSignature, empty));

        EdDSAParameterSpec prehashA =
                new EdDSAParameterSpec(true, contextA);
        byte[] prehashSignature = sign(
                algorithm, pair.getPrivate(), message, prehashA);

        System.out.println(algorithm + ".prehashVerifies=" +
                verify(algorithm, pair.getPublic(),
                        message, prehashSignature, prehashA));
        System.out.println(algorithm + ".prehashMismatchRejected=" +
                !verify(algorithm, pair.getPublic(),
                        message, prehashSignature, a));

        byte[] largeMessage = new byte[1024];
        Arrays.fill(largeMessage, (byte) 42);
        EdDSAParameterSpec maxContext =
                new EdDSAParameterSpec(false, new byte[255]);
        byte[] largeSignature = sign(
                algorithm, pair.getPrivate(),
                largeMessage, maxContext);

        System.out.println(algorithm + ".bigMessageWithMaxContext=" +
                verify(algorithm, pair.getPublic(),
                        largeMessage, largeSignature, maxContext));
    }

    public static void main(String[] args) throws Exception {
        run("Ed25519");
        run("Ed448");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 EdDSAContextSignatureDemo.java
java EdDSAContextSignatureDemo
~~~

**Stdout từ JDK 24/provider mặc định:**

~~~text
Ed25519.sameContext=true
Ed25519.differentContextRejected=true
Ed25519.absentContextRejected=true
Ed25519.defaultVsEmptySameBytes=false
Ed25519.defaultVerifyWithEmpty=false
Ed25519.prehashVerifies=true
Ed25519.prehashMismatchRejected=true
Ed25519.bigMessageWithMaxContext=true
Ed448.sameContext=true
Ed448.differentContextRejected=true
Ed448.absentContextRejected=true
Ed448.defaultVsEmptySameBytes=true
Ed448.defaultVerifyWithEmpty=true
Ed448.prehashVerifies=true
Ed448.prehashMismatchRejected=true
Ed448.bigMessageWithMaxContext=true
~~~

### 6.1. Đọc kết quả một cách chính xác

**`sameContext=true`:** Cả người ký và verifier sử dụng cùng context `release-v1`, cùng message và key; chữ ký khớp.

**`differentContextRejected=true`:** Đổi context từ `release-v1` thành `billing-v1` mà giữ message và chữ ký ban đầu khiến phép xác minh thất bại. Đó là ý nghĩa của context-based domain separation.

**`absentContextRejected=true`:** Một chữ ký tạo với context `release-v1` không còn khớp nếu verifier dùng không context.

**Ed25519: `defaultVsEmptySameBytes=false` và `defaultVerifyWithEmpty=false`:** Ed25519 thuần (`context` absent) khác với Ed25519ctx truyền mảng rỗng (context hiện diện). Điểm này dễ gây lỗi khi một API wrapper biến `null` thành `new byte[0]` mà không nêu rõ protocol mode.

**Ed448: `defaultVsEmptySameBytes=true` và `defaultVerifyWithEmpty=true`:** Trong RFC 8032, Ed448 có domain separator ngay cả khi context rỗng. Đối với JDK/provider được kiểm thử, không cung cấp context và cung cấp mảng rỗng dẫn đến cùng chế độ với `prehash=false`. **Không được từ điều này suy ra Ed25519 cũng giống như vậy.**

**`prehashVerifies=true` và `prehashMismatchRejected=true`:** Bật `prehash=true` thay đổi mode chữ ký; verifier phải có mode phù hợp. `Ed25519ph`/`Ed448ph` không phải việc ứng dụng tự gọi `MessageDigest` trước khi dùng `Ed25519`/`Ed448` thuần.

**`bigMessageWithMaxContext=true`:** Message dài **1024 bytes** vẫn ký và verify được với **context dài 255 bytes**. Vì thế câu “EdDSA không ký được message quá 255 bytes” là **sai**.

### 6.2. Độ dài khác nhau có thể hợp lệ như thế nào?

- `context = new byte[255]`: hợp lệ.
- `message = new byte[1024]`: hợp lệ với API trong ví dụ, vì không chịu giới hạn context.
- `context = new byte[256]`: bị `EdDSAParameterSpec` từ chối.
- `context = new byte[0]`: được chấp nhận bởi constructor nhưng có ngữ nghĩa riêng.
- `Signature.setParameter(...)` có thể bị một provider không hỗ trợ mode từ chối, cho dù `EdDSAParameterSpec` tự nó hợp lệ. Khi tích hợp với provider/HSM, hãy kiểm tra capability và negative test tương tác.

Không bao giờ cố “sửa” lỗi context quá dài bằng cách đổi thứ tự `initSign`, `setParameter` và `update`; cần **định nghĩa lại context bytes theo protocol** đúng giới hạn.

## 7. Unicode: giới hạn tính trên bytes sau khi encode, không phải trên `String.length()`

Trong Java, `String.length()` đếm **UTF-16 code units**, không phải số ký tự người dùng nhìn thấy, cũng không phải số UTF-8 bytes. Đối với context phải truyền `byte[]`, bạn cần xác định encoding chuẩn và **đếm bytes sau khi encode**.

### 7.1. Ví dụ số lượng

| Context theo chuỗi Unicode | UTF-16 code units | Code points | UTF-8 bytes | Có vừa 255 bytes? |
| --- | ---: | ---: | ---: | --- |
| `"A".repeat(255)` | 255 | 255 | **255** | Có |
| `"A".repeat(256)` | 256 | 256 | **256** | Không |
| `"\u00E9".repeat(127) + "A"` | 128 | 128 | **255** | Có |
| `"\u00E9".repeat(128)` | 128 | 128 | **256** | Không |
| `"🙂".repeat(63)` | 126 | 63 | **252** | Có |
| `"🙂".repeat(64)` | 128 | 64 | **256** | Không |
| `"e\u0301"` (e + dấu kết hợp) | 2 | 2 | **3** | Có |
| `"\u00E9"` (é tiền tổ hợp) | 1 | 1 | **2** | Có |

Đừng dùng `s.codePointCount(0,s.length())` để quyết định có vượt 255 hay không. Code points cũng không đo đúng bytes. Ví dụ emoji `🙂` dùng 4 UTF-8 bytes, nhưng một code point.

### 7.2. Unicode normalization: text giống nhau, bytes có thể khác

`"e\u0301"` (chữ e + combining acute) và `"\u00E9"` (é tiền tổ hợp) có thể hiển thị tương tự, nhưng:
- Context trước normalization có thể là **3 UTF-8 bytes**.
- Sau NFC normalization có thể còn **2 UTF-8 bytes**.
- Hai context **khác bytes** sẽ dẫn tới chữ ký khác/người kiểm tra không khớp nếu hai phía tự encode khác nhau.

Nếu protocol cho phép user-facing Unicode context, hai phía phải thống nhất normalization (nếu có), encoder, xử lý Unicode lỗi, phiên bản giao thức và byte length. **Không normalize tùy ý chỉ ở một phía**. Đối với domain identifiers, một chuỗi **ASCII cố định từ cấu hình tin cậy** thường ít rủi ro hơn context tự do từ client.

### 7.3. Không âm thầm thay thế Unicode không hợp lệ

`String.getBytes(StandardCharsets.UTF_8)` thuận tiện, nhưng có thể sử dụng replacement bytes khi String chứa malformed UTF-16 (ví dụ một surrogate lẻ). Với giá trị context dùng trong bảo mật, nếu protocol yêu cầu strict encoding, nên dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để từ chối input không hợp lệ thay vì silently replace.

## 8. Ví dụ 3 — Mã hóa UTF-8 nghiêm ngặt rồi mới áp giới hạn 255 bytes

Hàm `strictUtf8Context` sau đây:
1. Encode `String` sang UTF-8 và từ chối malformed UTF-16.
2. Sao chép bytes vào `byte[]` riêng.
3. Kiểm tra **bytes.length <= 255**.
4. Có thể chuyển trực tiếp bytes vào `EdDSAParameterSpec`.

**Tệp `EdDSAContextUtf8Demo.java` — độc lập Java 17+:**

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.security.spec.EdDSAParameterSpec;

public class EdDSAContextUtf8Demo {
    static byte[] strictUtf8Context(String value)
            throws CharacterCodingException {
        ByteBuffer result = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(value));

        byte[] bytes = new byte[result.remaining()];
        result.get(bytes);
        if (bytes.length > 255) {
            throw new IllegalArgumentException(
                    "EdDSA context exceeds 255 bytes");
        }
        return bytes;
    }

    public static void main(String[] args) throws Exception {
        String exactly255 = "\u00E9".repeat(127) + "A";
        byte[] accepted = strictUtf8Context(exactly255);
        EdDSAParameterSpec spec =
                new EdDSAParameterSpec(false, accepted);
        System.out.println("exact255Bytes=" +
                spec.getContext().orElseThrow().length);

        try {
            strictUtf8Context("\u00E9".repeat(128));
            System.out.println("over255Rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("over255Rejected=true");
        }

        try {
            strictUtf8Context(new String(new char[] {'\uD800'}));
            System.out.println("malformedUtf16Rejected=false");
        } catch (CharacterCodingException expected) {
            System.out.println("malformedUtf16Rejected=true");
        }

        String decomposed = "e\u0301";
        String nfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("decomposedUtf8Bytes=" +
                strictUtf8Context(decomposed).length);
        System.out.println("nfcUtf8Bytes=" +
                strictUtf8Context(nfc).length);
        System.out.println("sameRawBytes=" +
                java.util.Arrays.equals(
                        strictUtf8Context(decomposed),
                        strictUtf8Context(nfc)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 EdDSAContextUtf8Demo.java
java EdDSAContextUtf8Demo
~~~

**Stdout đã được kiểm chứng trên JDK 24:**

~~~text
exact255Bytes=255
over255Rejected=true
malformedUtf16Rejected=true
decomposedUtf8Bytes=3
nfcUtf8Bytes=2
sameRawBytes=false
~~~

**Giải thích:** `exactly255` có 128 UTF-16 code units nhưng đúng 255 UTF-8 bytes; constructor chấp nhận. Trường hợp 128 ký tự `é` có 256 bytes bị từ chối. Unpaired surrogate không được tự động thay thế. Hai chuỗi trông gần như giống nhau (`e\u0301` và `é`) có byte representations khác nhau, nên context phải được xác định ở **tầng protocol**.

**Giới hạn của helper:** Hàm này không tự normalize Unicode; phần normalization trong `main` chỉ để **quan sát sự khác biệt**. Nếu protocol muốn NFC, hãy áp dụng NFC trước khi encode ở **cả signer và verifier**, kiểm tra tính hợp lệ sau normalization, và công bố quy tắc trong version của protocol. Trong API dịch vụ thật cũng nên kiểm tra `value == null` và giới hạn độ dài input text sớm để không tiêu tốn quá nhiều bộ nhớ khi encode.

## 9. Vì sao không nên cắt context còn 255 bytes?

Một giải pháp nhìn có vẻ tiện nhưng **không an toàn cho tính tương thích**:

~~~java
// Mẫu minh họa CẦN TRÁNH, không phải chương trình độc lập.
byte[] original = input.getBytes(StandardCharsets.UTF_8);
byte[] context = Arrays.copyOf(original, Math.min(255, original.length));
~~~

Việc cắt ngang mảng bytes:
- Làm **hai context dài khác nhau** nhưng có 255 bytes đầu trùng nhau bị biến thành một context.
- Có thể cắt ngay giữa sequence UTF-8 nhiều bytes, tạo context không còn là encoding hợp lệ của text ban đầu.
- Khi signer/verifier dùng logic cắt khác nhau, kết quả không tương tác được.
- Khi attacker kiểm soát context text, việc âm thầm cắt làm mơ hồ namespace của domain.

**Nên:** Xác định một context có chiều dài hợp lệ ngay từ **đặc tả protocol**, chẳng hạn một ASCII domain identifier ổn định; nếu input vượt quá 255 bytes, **reject** với lỗi rõ ràng. Nếu tổ chức cần nhiều metadata (tenant, audience, resource, expiry, nonce), cân nhắc đặt chúng vào **phần message được ký** theo schema/canonical serialization thay vì nhét tất cả vào context.

Không tự động lấy `SHA-256(context)` để “lách” giới hạn nếu hai đầu protocol chưa cùng thiết kế và chuẩn hóa phép ánh xạ đó. Context không còn là raw context ban đầu; điều này ảnh hưởng namespace, interop và threat model.

## 10. Context, prehash và các bẫy tương tác

### 10.1. `prehash=true` không nâng giới hạn 255

~~~java
// Đoạn minh họa.
EdDSAParameterSpec prehash =
    new EdDSAParameterSpec(true, contextBytes);
~~~

Context dài 256 bytes vẫn bị từ chối vì đây là cùng constructor. `prehash` chọn Ed25519ph hoặc Ed448ph theo thuật toán, không phải “prehash context” để biến 256 bytes thành 255.

**Quan trọng:** Đừng tự chạy `SHA-512(message)` rồi đưa digest vào `Signature("Ed25519")` và gọi đó là Ed25519ph. RFC 8032 quy định Ed25519ph có domain separation và hashing mode riêng; dùng `EdDSAParameterSpec(true, ...)` với provider hỗ trợ khi protocol yêu cầu.

### 10.2. Giới hạn message không bị context áp đặt

Trong code ví dụ 2, `largeMessage` có `1024 bytes` và `context` có `255 bytes`. Chúng vẫn ký/verify thành công. RFC 8032 mô tả message có độ dài tùy ý theo thuật toán; nhưng ứng dụng thực phải có giới hạn kích thước do tài nguyên/kiểu giao thức quy định.

Với dữ liệu lớn, dùng `Signature.update(byte[], offset, len)` theo chunk có thể tránh tạo một bản sao message lớn, miễn cùng chuỗi bytes. Không được thay đổi thứ tự hoặc thiếu chunk ở phía verify.

### 10.3. Context khác nghĩa là mode/protocol khác

Các bên phải thống nhất **đúng bytes** của context và prehash mode. Một bên dùng `"release-v1"`, bên kia dùng `"Release-V1"`, dấu cách thừa, khác newline, hoặc khác UTF-8 encoding thì signature không còn khớp.

Không đợi tới khi `verify=false` mới thử một loạt context tùy ý để “tìm context đúng”. Quy tắc context phải được quyết định từ **trusted protocol configuration** và phiên bản message.

### 10.4. Không nhầm domain separation và authentication

Hai hệ thống có cùng public key nhưng context khác nhau sẽ không tùy tiện verify chữ ký của nhau. Tuy nhiên nếu kẻ tấn công được phép tạo key pair và tự cung cấp public key thì chữ ký họ vẫn verify đúng với key của họ. Context **không chứng minh key thuộc về người ký đáng tin**.

Bên xác minh phải:
- Lấy public key đã được trust/pin/validated theo chính sách.
- Bảo đảm thuật toán Ed25519/Ed448 và prehash mode đúng với trusted protocol.
- Dùng context cố định/chọn từ allowlist cấu hình.
- Kiểm tra message semantics, audience, issuer, authorization, nonce/freshness khi áp dụng.
- Từ chối malformed input, context dài quá mức hoặc tham số provider không hỗ trợ.

## 11. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Context tối đa 255 ký tự” | Unicode có 1–4 UTF-8 bytes/code point | Kiểm tra `byte[].length` sau encoding |
| Dùng `String.length() <= 255` để chấp nhận | `length()` đếm UTF-16 code units | Dùng `getBytes(UTF_8).length` hoặc strict encoder |
| Cho `new byte[256]` vào `EdDSAParameterSpec` | Giới hạn RFC là 255 bytes | Giảm context theo protocol hoặc reject |
| Bắt nhầm `InvalidAlgorithmParameterException` cho constructor | Constructor context quá dài ném `InvalidParameterException` | Bắt đúng ngoại lệ hoặc policy-layer `IllegalArgumentException` |
| Dùng `null` ở constructor hai tham số | Javadoc không cho phép null | Dùng constructor một tham số nếu muốn context absent |
| Xem `new byte[0]` giống context absent | Ed25519ctx-empty khác pure Ed25519 | Quy định mode và cách tạo spec rõ ràng |
| Dùng context rỗng cho Ed25519ctx mà không hiểu biến thể | RFC 8032 khuyên Ed25519ctx context không rỗng | Dùng context có nghĩa hoặc pure Ed25519 nếu protocol cần |
| Đổi context bên verifier | Domain separation được tính vào signature | Ký và verify với đúng context bytes |
| Cho phép client tùy chọn context một cách không giới hạn | Tạo context confusion/namespace ambiguity | Context do protocol/allowlist đáng tin quyết định |
| Cắt `byte[]` còn 255 bytes | Có thể collision giữa prefixes và cắt UTF-8 | Reject input không hợp lệ, không truncate ngầm |
| Normalize Unicode một phía | Hai text có byte representation khác nhau | Đặc tả encoding + normalization cho cả hai phía |
| Dùng `getBytes()` mặc định charset | Phụ thuộc charset mặc định/encoding policy | Dùng `StandardCharsets.UTF_8`, strict nếu cần |
| Chia context thành nhiều `update(...)` | `update(...)` dành cho **message**, không phải context | Truyền nguyên context qua `EdDSAParameterSpec` |
| Nghĩ `prehash=true` cho phép context dài hơn | Prehash chỉ chọn biến thể EdDSA | Vẫn giới hạn 255 bytes |
| “Không verify được” rồi fallback sang Ed25519 thuần | Mở rủi ro downgrade/protocol confusion | Fail closed và kiểm tra mode cấu hình |
| Coi context là bí mật | Context là domain-separation data, không phải secret key | Không dựa vào context để che giấu dữ liệu |
| Coi verify thành công là đã được cấp quyền | Crypto không tự xác thực danh tính/authorization | Kiểm trust và policy độc lập |
| Tái sử dụng một instance `Signature` đồng thời giữa threads | API có trạng thái, không được coi là thread-safe | Tạo/giới hạn instance theo từng thao tác hoặc quản lý an toàn |

## 12. Checklist cho triển khai thực tế

- [ ] Context được định nghĩa là **byte sequence**, đơn vị là **octets**.
- [ ] Context có độ dài từ `0` đến `255`; input `256` bị từ chối trước khi ký.
- [ ] Nếu context xuất phát từ text, codec và normalization policy đã thống nhất; kiểm **UTF-8 bytes**, không chỉ số ký tự.
- [ ] Có phân biệt **absent** và **present-but-empty** trong API/protocol.
- [ ] Ed25519 thuần không vô tình trở thành Ed25519ctx vì wrapper truyền mảng rỗng.
- [ ] Bên ký và bên verify dùng cùng `EdDSAParameterSpec` semantics: thuật toán, prehash, context.
- [ ] Provider/HSM thực tế hỗ trợ mode đã chọn; có integration test cụ thể.
- [ ] Context là namespace/identifier được verifier chấp nhận, không phải giá trị tự do từ bên không tin cậy.
- [ ] Dữ liệu security-relevant khác được đưa vào signed message nếu cần; không lạm dụng context cho payload dài.
- [ ] Không cắt context hoặc tự băm context mà không có protocol specification.
- [ ] Public key đã được xác thực gốc tin cậy; chữ ký đúng chưa tự cấp quyền.
- [ ] Các test độ dài 0, 1, 254, **255**, **256**, Unicode, malformed UTF-16, wrong-context, wrong-mode đều được áp dụng.
- [ ] Không dùng lỗi verify để thử ngẫu nhiên context khác cho đến khi một lựa chọn thành công.

## 13. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Giới hạn context trong EdDSA là `255` ký tự Java hay 255 bytes?

**Đáp án:** **255 bytes**, chính xác là 255 octets của mảng `byte[]` context. `String.length()` không dùng để đánh giá trực tiếp giới hạn đó.

**Câu 2.** `new EdDSAParameterSpec(false, new byte[255])` và `new EdDSAParameterSpec(false, new byte[256])` khác nhau thế nào?

**Đáp án:** 255 được phép, 256 ném `InvalidParameterException` ngay tại constructor.

**Câu 3.** Vì sao 128 lần `"é"` có thể bị từ chối dù chỉ 128 UTF-16 code units?

**Đáp án:** `é` dạng tiền tổ hợp mã hóa UTF-8 thành 2 bytes; 128 lần thành **256 bytes**, vượt 255.

**Câu 4.** Một context có 64 emoji `🙂` được Java đo thành bao nhiêu code points, UTF-16 units và UTF-8 bytes?

**Đáp án:** **64 code points**, **128 UTF-16 code units** và **256 UTF-8 bytes**. Nó vượt giới hạn context.

**Câu 5.** Với Ed25519, context `new byte[0]` có luôn giống context absent không?

**Đáp án:** **Không.** `new EdDSAParameterSpec(false)` là pure Ed25519, còn `new EdDSAParameterSpec(false, new byte[0])` chọn dạng Ed25519ctx với context present, dù dài 0 bytes. Đó là hai chế độ có domain separation khác nhau.

**Câu 6.** Vì sao trong Ed448 `defaultVsEmptySameBytes=true` ở ví dụ?

**Đáp án:** Ed448 theo RFC 8032 có domain separation ngay cả khi context rỗng; provider JDK được kiểm thử dùng context rỗng làm mặc định, nên absent và empty tương đương trong trường hợp đó. Không được suy rộng sang Ed25519 thuần.

**Câu 7.** Context 255 bytes có làm message chỉ được tối đa 255 bytes?

**Đáp án:** **Không.** Ví dụ ký thành công một message **1024 bytes** cùng context **255 bytes**.

**Câu 8.** Đổi context khi verify nhưng giữ cùng signature, key, message thì sao?

**Đáp án:** Chữ ký không khớp khi context khác; verifier phải sử dụng đúng context và chế độ mà signer đã dùng.

**Câu 9.** `prehash=true` có khắc phục lỗi context 256 bytes không?

**Đáp án:** **Không.** Prehash chọn Ed25519ph/Ed448ph, còn context vẫn bị giới hạn 255 octets.

**Câu 10.** Hai context text `"e\u0301"` và `"\u00E9"` có thể dùng thay nhau không?

**Đáp án:** Không mặc định. Chúng encode ra 3 và 2 UTF-8 bytes trước normalization. Chỉ khi protocol công bố chung một quy tắc normalization/encoding và hai phía tuân thủ mới có thể nhận cùng context bytes.

**Câu 11.** Nếu một chuỗi context dài 300 bytes nhưng bạn cắt còn 255, vì sao không phải giải pháp tốt?

**Đáp án:** Hai input khác nhau có thể bị biến thành cùng prefix 255 bytes, khiến context namespace mơ hồ; có thể cắt giữa multi-byte UTF-8. Cần reject hoặc thiết kế lại context theo protocol.

**Câu 12.** Một chữ ký Ed25519ctx hợp lệ có đủ chứng minh signer là “billing-service” và có quyền truy cập hóa đơn không?

**Đáp án:** **Không.** Context là domain separator; còn cần xác thực nguồn public key, ánh xạ danh tính và kiểm authorization/freshness phù hợp.

## 14. Tóm tắt ngắn

- **Giới hạn cần nhớ:** context dài tối đa **255 bytes**, không phải 255 Java chars.
- **API:** `new EdDSAParameterSpec(prehash, contextBytes)` chấp nhận 0–255 bytes, từ chối 256 bằng `InvalidParameterException`; `null` không được chấp nhận ở constructor hai tham số.
- **Absence khác empty:** Đặc biệt ở `Ed25519`, pure Ed25519 khác Ed25519ctx với mảng context rỗng.
- **Đúng context mới verify:** Hai bên phải dùng cùng thuật toán, prehash mode, context **byte-for-byte** và message.
- **Message không chịu giới hạn 255:** Đây chỉ là độ dài domain-separation context.
- **Unicode:** Đếm sau khi encode UTF-8; nếu protocol yêu cầu, sử dụng strict encoder và quy tắc normalization đã thống nhất.
- **An toàn ứng dụng:** Domain separation không thay thế trust/public-key binding, authorization, chống replay hoặc bảo vệ private keys.

## Tài liệu chính thức và tiêu chuẩn còn áp dụng

- [Oracle Java SE 25 — `EdDSAParameterSpec` Javadoc (hai constructor, giới hạn 255, null/empty)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html)
- [Oracle Java SE 25 — `Signature` Javadoc (`setParameter`, `update`, `sign`, `verify`)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html)
- [Oracle Java SE 25 — `InvalidParameterException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/InvalidParameterException.html)
- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339)
- [RFC 8032 `5.1 — Ed25519/Ed25519ctx/Ed25519ph](https://www.rfc-editor.org/rfc/rfc8032#section-5.1)
- [RFC 8032 `5.2 — Ed448/Ed448ph](https://www.rfc-editor.org/rfc/rfc8032#section-5.2)
- [RFC 8032 `8 — các lưu ý bảo mật về context và variants](https://www.rfc-editor.org/rfc/rfc8032#section-8)
