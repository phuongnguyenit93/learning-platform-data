# Ed25519, Ed25519ctx, Ed25519ph theo tham số trong Java

> **Chủ đề:** Java 15 → **Tham số EdDSA**. Bài học giải thích ba chế độ chữ ký **Ed25519**, **Ed25519ctx**, **Ed25519ph** theo **RFC 8032** và cách lựa chọn đúng bằng `java.security.spec.EdDSAParameterSpec` cùng `java.security.Signature`. Đây là các API **ổn định từ Java 15** và vẫn được hỗ trợ trong các JDK hiện đại, gồm Java 17, 21 và 25. Ví dụ ưu tiên **Java 17+**, sử dụng provider EdDSA tương thích của Oracle/OpenJDK, không dùng API nội bộ hoặc kỹ thuật lỗi thời.

## 1. Một đường cong Ed25519, ba chế độ chữ ký khác nhau

EdDSA (*Edwards-curve Digital Signature Algorithm*) là họ thuật toán chữ ký số khóa bất đối xứng. Với đường cong Ed25519, RFC 8032 mô tả ba chế độ liên quan:

1. **Ed25519 (pure):** ký trực tiếp thông điệp theo quy trình Ed25519 thông thường, **không** có ngữ cảnh (*context*) và **không** dùng chế độ prehash riêng.
2. **Ed25519ctx:** vẫn thuộc Ed25519, nhưng kèm **context bytes** cho mục đích *domain separation*. Theo RFC 8032, context của chế độ này **nên không rỗng**; về mặt API, context có thể được truyền là một mảng byte rỗng, nhưng đó **không** phải trạng thái “không có context”.
3. **Ed25519ph:** sử dụng **prehash** theo RFC 8032; giá trị thông điệp được xử lý qua SHA-512 trong chế độ chữ ký, kết hợp phân tách miền bằng thông tin chế độ và context. Context có thể được chỉ định hoặc vắng mặt (chế độ thông dụng dùng context rỗng theo chuẩn).

Cả ba chế độ dùng cơ chế khóa Ed25519 và đều tạo chữ ký chuẩn **64 byte**. Tuy nhiên, **cùng private key và cùng message chưa đủ để chữ ký ba chế độ có thể thay thế nhau**: dấu hiệu phân tách miền và/hoặc prehash làm quy trình toán học khác nhau.

| Thuộc tính | Ed25519 | Ed25519ctx | Ed25519ph |
| --- | --- | --- | --- |
| Đường cong | Ed25519 | Ed25519 | Ed25519 |
| Prehash theo RFC 8032 | Không | Không | **Có** (SHA-512) |
| Context | **Không có** | **Có mặt**; nên không rỗng | Có thể vắng mặt hoặc được cung cấp |
| Cờ `phflag` của RFC 8032 | Không sử dụng `dom2` | `0` | `1` |
| Phân tách miền `dom2` | **Không** | **Có** | **Có** |
| Độ dài chữ ký | 64 byte | 64 byte | 64 byte |
| Có thể xác minh chữ ký của chế độ khác như cùng một mode? | Không | Không | Không |
| Cách chọn ở Java | Mặc định hoặc `EdDSAParameterSpec(false)` | `EdDSAParameterSpec(false, context)` | `EdDSAParameterSpec(true)` hoặc có context |

**Điểm quan trọng:** tên `"Ed25519"` trong `Signature.getInstance("Ed25519")` xác định **đường cong/thuật toán nền**, còn `EdDSAParameterSpec` mới mô tả **mode có/không prehash và context**. Không nên giả định phải có tên thuật toán JCA riêng là `"Ed25519ctx"` hoặc `"Ed25519ph"` trên mọi provider.

Chọn đúng mode không chỉ là chi tiết triển khai: hai hệ thống muốn tương tác phải **thống nhất mode, thuật toán, context bytes, khóa và message bytes**.

## 2. Cách Java mô tả mode: `EdDSAParameterSpec`

Class chính thức:

```java
import java.security.spec.EdDSAParameterSpec;
```

Hai constructor:

```java
new EdDSAParameterSpec(boolean prehash)
new EdDSAParameterSpec(boolean prehash, byte[] context)
```

Hai phương thức đọc:

```java
boolean isPrehash()
java.util.Optional<byte[]> getContext()
```

Trong đó:

- `prehash=false`: không bật chế độ prehash; khi **context vắng mặt**, đó là Ed25519 thuần; khi **context có mặt**, đó là Ed25519ctx.
- `prehash=true`: chọn chế độ Ed25519ph (hoặc Ed448ph nếu sử dụng thuật toán đường cong Ed448). Context vẫn là tham số phân tách miền khi được cung cấp.
- `context` là **mảng byte**, không phải `String`. Nếu muốn dùng một nhãn văn bản, cần encode rõ ràng, ví dụ `"payment:v1".getBytes(StandardCharsets.UTF_8)`.
- Constructor có context **sao chép mảng bytes** được truyền. `getContext()` cũng trả bản sao, giúp mã bên ngoài không vô tình đổi context bên trong một `EdDSAParameterSpec` đã tạo.
- `getContext()` trả `Optional.empty()` khi không có context, hoặc `Optional.of(byte[])` nếu đã truyền context, kể cả khi mảng đó dài **0 byte**.
- Constructor `new EdDSAParameterSpec(prehash, context)` không chấp nhận `null`; dùng constructor **một tham số** nếu cần trạng thái không có context.
- Context dài **hơn 255 byte** bị từ chối bằng `InvalidParameterException` ngay ở constructor.

### Bảng lựa chọn mode bằng constructor

| Mã Java | Prehash | Trạng thái context | Ý nghĩa với Ed25519 |
| --- | --- | --- | --- |
| `new EdDSAParameterSpec(false)` | `false` | **Không có** (`null` theo ý nghĩa API) | **Ed25519 thuần** |
| `new EdDSAParameterSpec(false, bytes)`, `bytes.length > 0` | `false` | Có | **Ed25519ctx** với context đó |
| `new EdDSAParameterSpec(false, new byte[0])` | `false` | **Có, dài 0** | Chế độ có context; **không coi là pure Ed25519** |
| `new EdDSAParameterSpec(true)` | `true` | Không cung cấp | **Ed25519ph** với cấu hình không cung cấp context |
| `new EdDSAParameterSpec(true, bytes)` | `true` | Có | **Ed25519ph** với context đã cho |
| `new EdDSAParameterSpec(true, new byte[0])` | `true` | Có, dài 0 | Prehash mode với context rỗng được cung cấp rõ ràng |

**Phân biệt đặc biệt:** `new EdDSAParameterSpec(false)` và `new EdDSAParameterSpec(false, new byte[0])` **không tương đương**. Oracle Javadoc cảnh báo rõ rằng **vắng mặt context** và **mảng context rỗng** có thể chọn hai mode khác nhau. Với Ed25519, điều đó tương ứng Ed25519 thuần so với Ed25519ctx có context rỗng.

Trong RFC 8032, Ed25519ctx có context **SHOULD NOT** rỗng; vì vậy với ứng dụng mới, **hãy chọn một context có ý nghĩa và không rỗng** nếu mục tiêu thật sự là Ed25519ctx.

### Tại sao `Optional<byte[]>` quan trọng?

Thử:

```java
EdDSAParameterSpec plain = new EdDSAParameterSpec(false);
EdDSAParameterSpec contextual =
        new EdDSAParameterSpec(false, new byte[0]);

System.out.println(plain.getContext().isPresent());
System.out.println(contextual.getContext().isPresent());
```

Kết quả:

```text
false
true
```

Đây là snippet cần được đặt trong một chương trình Java có import thích hợp. Kết quả trên **không** nói rằng context rỗng là lựa chọn tốt cho Ed25519ctx; nó chỉ làm rõ hợp đồng API. Không dùng `getContext().orElse(new byte[0])` rồi coi hai trường hợp `Optional.empty()` và `Optional.of(empty)` là cùng mode.

## 3. Phần lý thuyết: context và `dom2` bảo vệ miền sử dụng

Trong cryptography, **domain separation** giúp các chữ ký dành cho những **ngữ cảnh giao thức khác nhau** không được diễn giải như nhau, dù ứng dụng có thể dùng cùng một cặp khóa.

Ví dụ một hệ thống có hai loại yêu cầu:

- Xác nhận một chứng từ: context bytes `"document:v1"`.
- Phê duyệt giao dịch: context bytes `"payment:v1"`.

Với Ed25519ctx, nếu bên ký tạo chữ ký theo `"document:v1"`, bên xác minh dùng context `"payment:v1"` sẽ không xác minh thành công cho cùng message và khóa, trừ những tình huống mật mã học không đáng kể về xác suất. Như vậy **context là một phần của cấu hình mật mã**, không phải nhãn trang trí để ghi log.

RFC 8032 định nghĩa một thành phần phân tách miền gọi là `dom2` cho Ed25519ctx và Ed25519ph, với thông tin gồm:

1. Chuỗi đánh dấu miền cố định do chuẩn quy định.
2. Cờ `phflag` cho biết prehash mode.
3. Độ dài context (tính bằng **byte**).
4. Chính xác những **context bytes** đã được chọn.

Ở Ed25519 **pure**, `dom2` được xem là rỗng theo quy tắc riêng của mode này. Do đó, **Ed25519ctx với context rỗng** vẫn dùng cơ chế phân tách miền và không phải Ed25519 thuần.

### Context không phải private key hoặc salt ngẫu nhiên

Context có các đặc điểm:

- **Không phải bí mật:** bên xác minh phải biết đúng context bytes.
- **Không phải khóa thứ hai:** context không thay private/public key.
- **Không phải nonce ngẫu nhiên bắt buộc:** context thường là nhãn ổn định, biểu diễn phiên bản giao thức hoặc mục đích chữ ký.
- **Không tự chống replay:** cùng message + signature hợp lệ có thể bị phát lại; ứng dụng vẫn cần nonce/request ID/timestamp/expiry theo nghiệp vụ.
- **Không phải toàn bộ dữ liệu được ký:** message bytes vẫn phải chứa những trường nghiệp vụ quan trọng. Context chỉ phân tách cách diễn giải mật mã của signature.

Lựa chọn context tốt cần ổn định, rõ ràng, không dễ trùng nhau giữa nhiều kiểu yêu cầu. Nếu context được dùng làm domain separation cho một giao thức, hai bên cần thỏa thuận bằng **cùng bytes** chứ không chỉ cùng nghĩa ngôn ngữ của nhãn.

### Context phải được phân phối và xác minh theo giao thức

Chữ ký Ed25519ctx **không tự mang metadata context** bên trong 64 bytes của signature. Người nhận cần biết:

- Thuật toán/curve: Ed25519.
- Mode: context-bearing (không prehash) hay prehash.
- Context bytes chính xác.
- Message bytes được ký.
- Public key đáng tin cậy.

Nếu dữ liệu gửi sang bên nhận có một trường `context`, đừng mù quáng dùng bất kỳ giá trị do request đưa vào mà không ràng buộc với chính sách nghiệp vụ. Bên xác minh phải chọn **mode/context phù hợp mục đích được phép**, sau đó mới thực hiện phép verify.

## 4. Prehash mode: Ed25519ph thực chất khác pure Ed25519

Một lỗi phổ biến là nghĩ rằng:

```text
Ed25519ph(message) == Ed25519(SHA-512(message))
```

**Không đúng.** Theo RFC 8032, Ed25519ph sử dụng **prehash SHA-512** trong quy trình ký **và** một **cờ phân tách miền** riêng (`phflag=1`). Ký digest bằng Ed25519 pure bỏ qua phân tách miền của Ed25519ph nên là một chữ ký **khác mode**.

Khái niệm:

```text
Ed25519 pure:
    message bytes ----------> pure Ed25519 signing --> signature

Ed25519ctx:
    message bytes --+
                    +--> Ed25519 signing với dom2(ph=0, context)
    context bytes --+

Ed25519ph:
    message bytes --> internal SHA-512 prehash --+
                                                  +--> Ed25519 signing với dom2(ph=1, context)
    context (optional) --------------------------+
```

**Không tự hash trước khi gọi `Signature.update(...)`** khi đang dùng `EdDSAParameterSpec(true)`. Thay vào đó, cung cấp **message gốc** cho `update`. Provider hỗ trợ RFC 8032 phải thực hiện prehash theo mode đã chọn.

Nếu tự gọi `MessageDigest.getInstance("SHA-512").digest(message)` rồi truyền digest 64 byte cho chữ ký Ed25519ph, bạn đang yêu cầu **prehash lại digest**. Đó **không phải** chữ ký Ed25519ph của message gốc.

Nếu chỉ gọi pure Ed25519 trên digest, bạn cũng không tự tạo được Ed25519ph vì thiếu phân tách miền chuyên biệt.

### Lúc nào chọn Ed25519ph?

- Khi **giao thức được định nghĩa rõ** là Ed25519ph, bao gồm lựa chọn context nếu có.
- Khi cần khả năng tương tác với một hệ thống/định dạng ngoài Java **quy định chế độ prehash RFC 8032**.
- Khi yêu cầu triển khai gắn với prehash mode theo đặc tả.

**Không tự đổi sang Ed25519ph** chỉ vì message dài; tính phù hợp với giao thức và mô hình bảo mật là tiêu chí đầu tiên. Ed25519 thuần vốn hỗ trợ thông điệp có độ dài tùy ý theo giao diện. Chế độ prehash có thể hữu ích trong những thiết kế nhất định, nhưng API/provider cụ thể mới quyết định cách buffer và streaming trong bộ nhớ; không hứa hẹn mọi implementation luôn giữ bộ nhớ hằng số.

**Cả bên ký và bên xác minh** phải thống nhất mode. Chữ ký Ed25519ph thông thường không xác minh được nếu verifier sử dụng Ed25519 pure trên cùng message bytes và public key.

## 5. Quy trình API Java: đặt tham số trước khi khởi tạo và update

Khai báo tham số rồi truyền qua overload hiện hành `Signature.setParameter(AlgorithmParameterSpec)`:

```java
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.nio.charset.StandardCharsets;

// Pure Ed25519.
Signature pure = Signature.getInstance("Ed25519");

// Ed25519ctx, context hiện diện và không prehash.
Signature ctx = Signature.getInstance("Ed25519");
ctx.setParameter(new EdDSAParameterSpec(
        false,
        "document:v1".getBytes(StandardCharsets.UTF_8)));

// Ed25519ph, prehash true và không cung cấp context.
Signature ph = Signature.getInstance("Ed25519");
ph.setParameter(new EdDSAParameterSpec(true));
```

Đoạn này là **snippet tạo các engine**, chưa ký/xác minh; cần xử lý các checked exceptions thích hợp khi đặt vào phương thức.

**Trình tự khuyến nghị nhất quán** khi dùng provider hỗ trợ EdDSA parameters:

1. `Signature.getInstance("Ed25519")`.
2. `setParameter(spec)` **nếu** cần một mode cụ thể; với pure có thể bỏ bước này.
3. `initSign(privateKey)` hoặc `initVerify(publicKey)`.
4. `update(messageBytes)` (có thể gọi theo nhiều mảnh và **giữ đúng thứ tự bytes**).
5. `sign()` hoặc `verify(signatureBytes)`.

**Cấu hình cả hai phía:** Cả signer và verifier phải tạo engine với **cùng mode/context**. Không có tác dụng nếu signer dùng `EdDSAParameterSpec(false, context)` nhưng verifier chỉ `Signature.getInstance("Ed25519")` và mặc định pure.

Tại sao nên đặt `setParameter` **trước** `initSign`/`initVerify`? Đó là cách rõ ràng để provider có đủ cấu hình mode ngay từ thời điểm khởi tạo. Một số provider giới hạn việc đổi tham số sau khi đã khởi tạo hoặc sau khi đã gọi `update`. Không dựa vào việc thay mode giữa chừng trong cùng một `Signature` instance.

### Phân biệt tham số mode và tham số tạo khóa

`EdDSAParameterSpec` **không chọn đường cong Ed25519 hay Ed448**. Nó chọn **prehash/context** cho quá trình ký/xác minh. Đường cong được quyết định bằng tên thuật toán và/hoặc loại khóa, ví dụ:

```java
KeyPairGenerator generator =
        KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(false,
        "document:v1".getBytes(StandardCharsets.UTF_8)));
signer.initSign(pair.getPrivate());
```

Snippet cần các import `java.security.*` và đặt trong phương thức xử lý checked exceptions. Thay `EdDSAParameterSpec(false, ...)` **không biến** một cặp khóa Ed25519 thành Ed448.

### Tại sao lại dùng một `Signature` instance mới?

Đối tượng `Signature` có trạng thái nội bộ. Với mỗi thao tác cụ thể, tạo instance mới giúp:

- Không vô tình giữ lại mode/context của lần trước.
- Không dùng chữ ký đã update nửa chừng.
- Không chia sẻ một instance mutable giữa nhiều luồng mà không có quy tắc đồng bộ.
- Không gây nhầm lẫn về lựa chọn provider đã được cố định.
- Dễ ghi rõ mode trong mã và kiểm thử tương thích.

## 6. Ví dụ hoàn chỉnh: ký/xác minh ba mode và thử mode sai

Ví dụ dùng **một cặp khóa Ed25519** để phân biệt **sự khác nhau của mode**, không cố tình trộn thêm yếu tố khóa. Nó ký cùng một message theo nhiều cách rồi cố xác minh chéo.

### 6.1. Tệp `Ed25519ModesDemo.java`

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class Ed25519ModesDemo {
    private static byte[] sign(
            PrivateKey key, byte[] message, EdDSAParameterSpec spec)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("Ed25519");
        if (spec != null) {
            signer.setParameter(spec);
        }
        signer.initSign(key);
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(
            PublicKey key, byte[] message, byte[] signature,
            EdDSAParameterSpec spec)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        if (spec != null) {
            verifier.setParameter(spec);
        }
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPair keys = KeyPairGenerator
                .getInstance("Ed25519").generateKeyPair();
        byte[] message = "invoice=42;amount=100"
                .getBytes(StandardCharsets.UTF_8);

        byte[] domain = "payment:v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] otherDomain = "payment:v2"
                .getBytes(StandardCharsets.UTF_8);

        EdDSAParameterSpec ctx =
                new EdDSAParameterSpec(false, domain);
        EdDSAParameterSpec wrongCtx =
                new EdDSAParameterSpec(false, otherDomain);
        EdDSAParameterSpec ph =
                new EdDSAParameterSpec(true);
        EdDSAParameterSpec phCtx =
                new EdDSAParameterSpec(true, domain);
        EdDSAParameterSpec emptyCtx =
                new EdDSAParameterSpec(false, new byte[0]);

        // Cùng key + message nhưng 5 cách cấu hình khác nhau.
        byte[] pureSig = sign(keys.getPrivate(), message, null);
        byte[] ctxSig = sign(keys.getPrivate(), message, ctx);
        byte[] phSig = sign(keys.getPrivate(), message, ph);
        byte[] phCtxSig = sign(keys.getPrivate(), message, phCtx);
        byte[] emptyCtxSig =
                sign(keys.getPrivate(), message, emptyCtx);

        System.out.println("pure.valid="
                + verify(keys.getPublic(), message, pureSig, null));
        System.out.println("ctx.valid="
                + verify(keys.getPublic(), message, ctxSig, ctx));
        System.out.println("ph.valid="
                + verify(keys.getPublic(), message, phSig, ph));
        System.out.println("phCtx.valid="
                + verify(keys.getPublic(), message,
                        phCtxSig, phCtx));

        System.out.println("ctx.wrongContext="
                + verify(keys.getPublic(), message, ctxSig, wrongCtx));
        System.out.println("ctx.asPure="
                + verify(keys.getPublic(), message, ctxSig, null));
        System.out.println("ph.asPure="
                + verify(keys.getPublic(), message, phSig, null));
        System.out.println("phCtx.asPhNoContext="
                + verify(keys.getPublic(), message, phCtxSig, ph));

        System.out.println("emptyCtx.differsFromPure="
                + !Arrays.equals(emptyCtxSig, pureSig));

        System.out.println("lengths="
                + pureSig.length + "," + ctxSig.length + ","
                + phSig.length + "," + phCtxSig.length);
    }
}
```

### 6.2. Biên dịch và chạy

Sử dụng JDK 17+ với provider hỗ trợ các mode RFC 8032, chẳng hạn `SunEC` trong các bản Oracle/OpenJDK phổ biến:

```bash
javac -encoding UTF-8 Ed25519ModesDemo.java
java Ed25519ModesDemo
```

**Stdout dự kiến theo chế độ EdDSA của provider tương thích:**

```text
pure.valid=true
ctx.valid=true
ph.valid=true
phCtx.valid=true
ctx.wrongContext=false
ctx.asPure=false
ph.asPure=false
phCtx.asPhNoContext=false
emptyCtx.differsFromPure=true
lengths=64,64,64,64
```

### 6.3. Giải thích từng kết quả

**`pure.valid=true`**: không chỉ định context, không prehash; verify dùng Ed25519 pure với cùng public key và bytes message.

**`ctx.valid=true`**: signer/verifier cùng sử dụng `EdDSAParameterSpec(false, domain)`, tức prehash tắt và context tồn tại. Đây là Ed25519ctx.

**`ph.valid=true`**: signer/verifier dùng `new EdDSAParameterSpec(true)`, tức chế độ Ed25519ph.

**`phCtx.valid=true`**: prehash vẫn bật nhưng kèm context. Đây **vẫn là Ed25519ph**, không phải Ed25519ctx vì `prehash=true`.

**`ctx.wrongContext=false`**: context khác nhau dù message/key giống, verify thất bại. Mode/context là dữ liệu cần phối hợp.

**`ctx.asPure=false`**: chữ ký Ed25519ctx không thể kiểm tra như chữ ký Ed25519 thuần.

**`ph.asPure=false`**: chữ ký Ed25519ph không thể kiểm tra như Ed25519 thuần, kể cả bên xác minh có cùng message bytes.

**`phCtx.asPhNoContext=false`**: cùng prehash mode nhưng context một phía có, phía kia không, không tương tác.

**`emptyCtx.differsFromPure=true`**: context rỗng **có mặt** là lựa chọn khác với không có context ở Ed25519. Đó là lý do không nên âm thầm biến `Optional.empty()` thành `new byte[0]`.

**`lengths=64,64,64,64`**: bốn chữ ký đều dài 64 bytes như đặc tả Ed25519. **Độ dài chữ ký không cho biết chữ ký thuộc mode nào**; cần metadata giao thức.

Mặc dù keypair được tạo ngẫu nhiên mỗi lần chạy, các mệnh đề đúng/sai trên có kết quả ổn định theo RFC 8032 và triển khai đúng chuẩn. Ví dụ **không** in bytes khóa/chữ ký, vì chúng khác nhau giữa các lần tạo keypair.

### 6.4. Vì sao không gọi tên `Ed25519ctx` trong `getInstance`?

Ở Java, việc chọn **context và prehash** được mô tả bằng `EdDSAParameterSpec`. `Signature.getInstance("Ed25519")` cho engine Ed25519; sau đó `setParameter(...)` yêu cầu mode cụ thể. Đây là API ổn định được chuẩn hóa từ Java 15 và được mô tả trong `EdDSAParameterSpec` của Java 25.

Không mặc định rằng những tên không thuộc danh sách chuẩn như `"Ed25519ctx"` sẽ được mọi provider hiểu. Một thư viện khác có thể đặt tên riêng cho mode, nhưng khi viết Java JCA, cần kiểm tra đúng thuật toán **và** tham số theo API hiện hành.

## 7. Ví dụ thứ hai: Ed25519ph không bằng pure Ed25519 trên SHA-512

Tạo tệp **`Ed25519PrehashDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class Ed25519PrehashDemo {
    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPair keys = KeyPairGenerator
                .getInstance("Ed25519").generateKeyPair();
        byte[] message = "Hello from RFC 8032"
                .getBytes(StandardCharsets.UTF_8);

        // ĐÚNG: yêu cầu Ed25519ph và cung cấp message GỐC.
        Signature phSigner = Signature.getInstance("Ed25519");
        phSigner.setParameter(new EdDSAParameterSpec(true));
        phSigner.initSign(keys.getPrivate());
        phSigner.update(message);
        byte[] phSignature = phSigner.sign();

        // KHÁC MODE: tự SHA-512 rồi ký digest bằng PURE Ed25519.
        byte[] digest = MessageDigest
                .getInstance("SHA-512").digest(message);
        Signature pureSigner = Signature.getInstance("Ed25519");
        pureSigner.initSign(keys.getPrivate());
        pureSigner.update(digest);
        byte[] pureOfDigest = pureSigner.sign();

        Signature phVerifier = Signature.getInstance("Ed25519");
        phVerifier.setParameter(new EdDSAParameterSpec(true));
        phVerifier.initVerify(keys.getPublic());
        phVerifier.update(message);

        System.out.println("ph.valid="
                + phVerifier.verify(phSignature));
        System.out.println("sameAsPureOfDigest="
                + Arrays.equals(phSignature, pureOfDigest));
        System.out.println("message.length=" + message.length);
        System.out.println("digest.length=" + digest.length);
        System.out.println("signature.length=" + phSignature.length);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Ed25519PrehashDemo.java
java Ed25519PrehashDemo
```

**Stdout dự kiến:**

```text
ph.valid=true
sameAsPureOfDigest=false
message.length=19
digest.length=64
signature.length=64
```

**Giải thích:** `"Hello from RFC 8032"` gồm 19 ký tự ASCII nên ở UTF-8 có 19 bytes. SHA-512 tạo digest 64 bytes. Ed25519ph vẫn tạo chữ ký Ed25519 64 bytes; việc kết quả có cùng độ dài **không** khiến nó tương đương với chữ ký pure Ed25519 trên digest.

Cả hai quy trình đều có thể tạo ra chữ ký mật mã hợp lệ **cho mode và message riêng của chúng**, nhưng chỉ cách thứ nhất đúng với hợp đồng **Ed25519ph(message gốc)**. Thử đối chiếu chữ ký của hai mode theo `Arrays.equals` sẽ cho `false` trong ví dụ. Với các thuộc tính mật mã định trước, không dùng giá trị bytes chữ ký ngẫu nhiên từ một phiên chạy làm output cố định.

**Tránh double hashing:** nếu đã sử dụng `new EdDSAParameterSpec(true)`, đừng tự đưa digest vào `update` trừ khi giao thức của bạn thật sự muốn ký digest **như message mới**. Đó là hai mục tiêu khác nhau.

## 8. Giới hạn context: tối đa 255 **byte**, không phải 255 ký tự

`EdDSAParameterSpec(boolean, byte[])` cho phép context dài từ **0 đến 255 bytes**, nhưng các chế độ và chuẩn khuyến nghị có thể đặt ý nghĩa khác nhau cho context rỗng.

Ví dụ:

```java
byte[] shortContext =
        "invoice:v1".getBytes(StandardCharsets.UTF_8);

EdDSAParameterSpec ok =
        new EdDSAParameterSpec(false, shortContext);
```

Đây là snippet với import `StandardCharsets` và `EdDSAParameterSpec`. Trong khi đó:

```java
byte[] tooLong = new byte[256];
new EdDSAParameterSpec(false, tooLong);
```

Constructor ở snippet thứ hai **ném `InvalidParameterException`** (unchecked), vì quá 255 bytes.

### Vì sao cần đếm bytes?

- Context là **bytes**; `context.length` là số bytes.
- Nếu source là văn bản Java `String`, `text.length()` đếm **UTF-16 code units**, không phải bytes UTF-8.
- Các ký tự ngoài ASCII có thể chiếm **nhiều bytes**; tên context nhìn ngắn hơn 255 ký tự vẫn có thể vượt hạn mức.
- Nếu bên ký dùng UTF-8 còn bên xác minh dùng charset khác, context bytes khác nhau khiến verify thất bại.

Tốt nhất nên dùng các context là mã miền ngắn, ASCII/UTF-8 có quy tắc ổn định và có phiên bản, ví dụ `"myapp:invoice:v1"`. **Không** dùng nội dung người dùng tùy ý hoặc mô tả dài làm context nếu không có chuẩn hóa/bounds rõ ràng.

### Defensive copying

`EdDSAParameterSpec` sao chép context được truyền khi tạo object, đồng thời `getContext()` trả **bản sao**. Vì vậy việc thay đổi mảng gốc **sau khi** tạo tham số không làm đổi context bên trong spec.

Tạo **`EdDsaSpecDemo.java`** để kiểm tra:

```java
import java.nio.charset.StandardCharsets;
import java.security.InvalidParameterException;
import java.security.spec.EdDSAParameterSpec;

public class EdDsaSpecDemo {
    public static void main(String[] args) {
        byte[] original = "v1".getBytes(StandardCharsets.UTF_8);
        EdDSAParameterSpec spec =
                new EdDSAParameterSpec(false, original);

        // Thay mảng gốc sau khi constructor đã copy.
        original[0] = 'X';
        String inside = new String(
                spec.getContext().orElseThrow(),
                StandardCharsets.UTF_8);
        System.out.println("storedContext=" + inside);

        // Bản sao do getter trả về có thể thay mà không đổi spec.
        byte[] extracted = spec.getContext().orElseThrow();
        extracted[0] = 'Y';
        System.out.println("getterIsCopy="
                + (spec.getContext().orElseThrow()[0] == 'v'));

        System.out.println("pure.hasContext="
                + new EdDSAParameterSpec(false)
                        .getContext().isPresent());

        System.out.println("empty.hasContext="
                + new EdDSAParameterSpec(false, new byte[0])
                        .getContext().isPresent());

        System.out.println("prehash="
                + new EdDSAParameterSpec(true).isPrehash());

        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("longContext=accepted");
        } catch (InvalidParameterException ex) {
            System.out.println("longContext=rejected");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 EdDsaSpecDemo.java
java EdDsaSpecDemo
```

Stdout:

```text
storedContext=v1
getterIsCopy=true
pure.hasContext=false
empty.hasContext=true
prehash=true
longContext=rejected
```

**Ý nghĩa:** context của spec là dữ liệu của đối tượng tham số, không nên biến đổi ngầm sau khi đã chọn mode. Nếu cần đổi context, tạo một `EdDSAParameterSpec` mới và `Signature` instance mới.

## 9. Điều gì phải thống nhất giữa signer và verifier?

Một verifier muốn kiểm tra chữ ký EdDSA cần có ít nhất:

1. **Thuật toán/curve:** `Ed25519`, không tự đổi thành `Ed448`.
2. **Mode:** pure, context mode hoặc prehash mode.
3. **Context:** trạng thái có/vắng mặt và **bytes chính xác** nếu có; quan trọng đặc biệt với Ed25519ctx.
4. **Message bytes:** cùng serialization, charset và thứ tự dữ liệu.
5. **Public key đúng:** được ràng buộc với chủ thể đáng tin, tương ứng private key ký.
6. **Signature bytes:** nguyên vẹn và đúng encoding của giao thức.

Một cách mô tả hợp đồng ví dụ:

```text
signatureProfile: ed25519ctx
curve: Ed25519
prehash: false
contextEncoding: UTF-8
context: myapp:invoice:v1
messageEncoding: canonical-binary-v1
signatureEncoding: raw-64-byte
trustedKeyId: issuer-2026-01
```

Đây là **ví dụ mô tả hợp đồng**, không phải định dạng chuẩn Java tự sinh. Cần thiết kế và kiểm tra kiểu/độ dài/giới hạn dữ liệu phù hợp.

**Lưu ý:** một gói truyền gồm algorithm, context, key ID và signature chưa chắc là đáng tin. Bên xác minh phải áp dụng **profile đã được hệ thống cho phép**. Nếu bên gửi được tùy ý chọn mode và context yếu hơn, có thể phá yêu cầu về phân tách miền của ứng dụng. Metadata cần được ràng buộc bằng chính sách giao thức và, khi thích hợp, được đưa vào message đã ký.

### Các cặp mismatch phổ biến

| Bên ký | Bên xác minh | Kết quả kỳ vọng |
| --- | --- | --- |
| Ed25519 pure | Ed25519 pure, đúng message/key | `true` |
| Ed25519ctx context `A` | Ed25519ctx cùng `A`, đúng message/key | `true` |
| Ed25519ctx `A` | Ed25519ctx `B` | `false` |
| Ed25519ctx `A` | Ed25519 pure | `false` |
| Ed25519ph | Ed25519ph, cùng context policy/message/key | `true` |
| Ed25519ph | Ed25519 pure | `false` |
| Ed25519ph context `A` | Ed25519ph context `B` | `false` |
| Ed25519ctx context **rỗng** | Ed25519 pure context **vắng mặt** | `false` |
| Ed25519ctx đúng context | Ed25519ctx nhưng message byte khác | `false` |
| Ed25519ph đúng mode | Ed25519ph nhưng public key của cặp khác | `false` |

Các dòng trên nói về **chữ ký hợp lệ theo chuẩn và đầu vào đúng định dạng**. Nếu provider không chấp nhận mode/tham số hoặc signature bytes sai định dạng, API có thể ném ngoại lệ thay vì trả `false`; đó là lỗi cấu hình/đầu vào riêng.

## 10. Ed25519 so với Ed448: cùng lớp tham số, mode khác theo curve

`EdDSAParameterSpec` được thiết kế cho **EdDSA**, không chỉ riêng Ed25519. Theo Java API:

- `prehash=true` với Ed448 chọn **Ed448ph**.
- `prehash=false` với Ed448 và có context là mode Ed448 hỗ trợ context.
- `prehash=false` với Ed448 và không cung cấp context là Ed448 không prehash theo cấu hình mặc định tương ứng.

Tuy nhiên Ed448 có quy tắc phân tách miền riêng trong RFC 8032 và **không nên gọi chế độ context của Ed448 là “Ed25519ctx”**. Các giá trị khóa/độ dài signature cũng khác: Ed448 tạo chữ ký chuẩn **114 bytes**.

Ví dụ chọn đúng curve:

```java
KeyPairGenerator gen =
        KeyPairGenerator.getInstance("Ed448");
KeyPair keys = gen.generateKeyPair();

Signature signer = Signature.getInstance("Ed448");
signer.setParameter(new EdDSAParameterSpec(true));
signer.initSign(keys.getPrivate());
```

Đây là snippet, không phải chương trình chạy độc lập. Nó minh họa việc cùng `EdDSAParameterSpec(true)` có ý nghĩa **prehash của curve Ed448** khi engine/key là Ed448.

**Không** dùng Ed25519 private key trong `Signature("Ed448")`; không đổi curve chỉ bằng cách thay context/prehash. Phải đồng bộ cả thuật toán, tham số và loại khóa.

## 11. Các lỗi API và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Giải pháp |
| --- | --- | --- |
| `verify(...) == false` | Sai mode, context, message bytes, public key hoặc signature | So sánh profile, bytes message, key ID, cấu hình `EdDSAParameterSpec` hai phía |
| `InvalidAlgorithmParameterException` khi `setParameter` | Provider không chấp nhận bộ tham số hoặc thời điểm đặt tham số | Kiểm tra provider hỗ trợ RFC 8032 modes; đặt tham số trước `init...` |
| `UnsupportedOperationException` ở provider | Provider không hiện thực method/cấu hình tham số yêu cầu | Chọn provider hỗ trợ bằng chính sách hợp lệ; không mặc định mọi provider đồng nhất |
| `InvalidParameterException` khi tạo spec | Context dài hơn 255 bytes | Giới hạn context `byte[].length <= 255` |
| `NullPointerException` ở constructor hai tham số | Truyền context là `null` | Muốn không có context, dùng `new EdDSAParameterSpec(prehash)` |
| `InvalidKeyException` | Private/public key không tương thích curve/provider | Dùng đúng cặp khóa và thuật toán Ed25519 hoặc Ed448 |
| `SignatureException` | Engine sai trạng thái, chữ ký sai format, provider không xử lý được input | Kiểm tra `initSign`/`initVerify`, `update` và dữ liệu signature |
| Chữ ký ctx khác nhau dù message/key giống | Context bytes khác hoặc bị đổi charset | Dùng một chuẩn encoding/chuỗi domain có version |
| Pure Ed25519 không verify được chữ ký `ctx(new byte[0])` | Vắng context và context rỗng có **mode khác nhau** | Bảo toàn sự khác nhau của hai constructor |
| Ed25519ph không trùng Ed25519(SHA-512(message)) | Prehash mode có **domain separation** riêng | Dùng `EdDSAParameterSpec(true)`, truyền message nguyên bản |
| `getContext()` có `Optional.empty()` | Không truyền context bằng constructor một tham số | Đừng tự diễn giải là một mảng context rỗng |
| Ký/xác minh bằng hai thuật toán khác curve | Ví dụ Ed25519 vs Ed448 | Quy định curve rõ và kiểm tra dữ liệu khóa |
| Dùng thuật toán tên `Ed25519ctx` nhưng provider không có | Đây không phải tên JCA standard bắt buộc | Dùng `"Ed25519"` + `EdDSAParameterSpec(false, context)` |
| Ghi profile context trong metadata nhưng không kiểm tra | Bên nhận chọn mode/context sai hoặc do người gửi thao túng | Verifier phải có danh sách profile được phép và xác thực nguồn khóa |
| Đổi context sau khi ký | Context là một phần tính toán signature | Nếu cần context mới, phải tạo **chữ ký mới** theo mode mới |

### Cách phân biệt chữ ký sai với input/config sai

- **`false` từ `verify`:** chữ ký không hợp lệ cho **đúng bộ (public key, message, mode, context)** đã cung cấp.
- **Exception:** thuật toán/provider/khóa/tham số/trạng thái/dữ liệu bị lỗi hoặc không hỗ trợ.

Trong hệ thống xử lý yêu cầu có chữ ký, cả hai trường hợp thường phải **từ chối hành động** và ghi nhận nguyên nhân ở mức phù hợp, không báo một chữ ký sai là hợp lệ chỉ vì muốn thông qua quy trình.

## 12. Lưu ý bảo mật khi dùng context/prehash

### 12.1. Domain separation giúp giảm nhầm mục đích, không thay ủy quyền

Context có thể giúp phân biệt chữ ký “duyệt hợp đồng” và “duyệt thanh toán”. Nhưng hệ thống vẫn cần:

- Xác thực public key thuộc người/tổ chức nào.
- Kiểm tra người ký có quyền thực hiện hành động tương ứng.
- Xác nhận message bytes bao gồm toàn bộ trường cần được bảo vệ.
- Kiểm tra phiên bản giao thức, hạn hiệu lực, nonce/message ID nếu cần chống replay.

Không dùng mỗi context để thay thế tất cả kiểm tra nghiệp vụ.

### 12.2. Context cố định và có version

Một chính sách tốt:

```text
context = "myapp:payment:approval:v1"
message = canonicalized(serialized request)
```

Đó là ví dụ ý tưởng về một domain ổn định. Phải quy định cả hai vế ở mức bytes. Nếu sau này giao thức thay đổi mà mode hoặc cấu trúc message khác, tạo profile/version mới thay vì tiếp tục dùng một context có nghĩa cũ một cách mơ hồ.

### 12.3. Không tự trộn thêm prehash bên ngoài

Không có lý do thông thường để gọi SHA-512 thủ công rồi vẫn bật `prehash=true` cho cùng **message gốc**. Hãy để provider thực hiện RFC 8032 prehash. Nếu bên nhận đang dùng thư viện ngoài Java, phải xác nhận thư viện đó hỗ trợ **Ed25519ph thực sự** và có cùng quy tắc context; không dựa vào cách đặt tên gần giống.

### 12.4. Chữ ký không mã hóa nội dung

Ba mode Ed25519 đều là **chữ ký số**, không phải encryption. Context thường công khai; message có thể công khai hoặc bí mật theo ứng dụng, nhưng signature không tự giấu message. Cần bảo vệ truyền/lưu trữ nếu dữ liệu nhạy cảm.

### 12.5. Các khác biệt liên quan đến khóa

Private key cần được giữ bí mật. Public key phải được gắn với chủ thể đáng tin. Việc chọn `ctx` hoặc `ph` **không cải thiện một hệ thống** đang chấp nhận public key bất kỳ do người gửi cung cấp mà không kiểm tra danh tính. Muốn có bảo đảm an toàn, phải bảo vệ private key và kiểm soát nguồn public key song song với việc chọn mode.

## 13. Quy trình kiểm tra tích hợp giữa hai hệ thống

Dành cho trường hợp một hệ thống ký bằng Java, một hệ thống xác minh bằng Java hoặc thư viện khác:

1. **Chốt profile** trước: `Ed25519` / `Ed25519ctx` / `Ed25519ph`; nếu là ctx/ph thì context bytes phải được khai báo và versioned.
2. **Chốt charset/serialization**: với text chọn UTF-8 rõ; với dữ liệu có cấu trúc chọn định dạng bytes canonical của giao thức.
3. **Chốt định dạng public key**: ví dụ X.509 SPKI hay raw public key theo một chuẩn cụ thể; chúng **không** phải cùng một chuỗi bytes.
4. **Chốt định dạng signature**: Ed25519 signature chuẩn raw 64 bytes, có thể encode Base64 chỉ để vận chuyển.
5. **Đối chiếu mode**: bảo đảm cả hai đầu sử dụng cùng cờ prehash và trạng thái context.
6. **Thử vector chuẩn RFC 8032** cho đúng mode/context/curve khi triển khai giao thức mới hoặc viết library.
7. **Thử nghiệm dương tính**: đúng key, đúng mode, đúng context, đúng message → `true`.
8. **Thử nghiệm âm tính**: đổi một byte của message, đổi context, đổi mode, dùng key khác → phải từ chối.
9. **Thử context rỗng/vắng** để bắt lỗi chuyển `Optional.empty()` thành `new byte[0]`.
10. **Thử môi trường thực**: JDK/provider, policy security và hệ thống lưu khóa. Đừng giả định mọi provider có cùng tập mode chỉ vì có tên `Signature.Ed25519`.

**Không** dùng một giao thức không định nghĩa context/curve để tự đoán mode tại bên nhận. Việc “thử lần lượt pure, ctx, ph và nhận mode nào verify được” có thể phá thiết kế domain separation nếu verifier bỏ qua chính sách giao thức. Hãy biết và áp dụng **mode được phép ngay từ đầu**.

### Ví dụ về dữ liệu hợp đồng truyền tải

```text
protocolVersion: 1
signatureAlgorithm: Ed25519
signatureMode: Ed25519ctx
contextBytesUtf8: "myapp:invoice:v1"
keyId: "seller-key-2026"
messageSerialization: "canonical-v1"
signature: 64 raw bytes (hoặc Base64 của 64 bytes)
```

Đây chỉ là cấu trúc minh họa cho tài liệu thiết kế. Trong sản phẩm thật, cách serialize field phải được quyết định bằng đặc tả rõ ràng, không để người gửi lựa chọn algorithm/mode bất kỳ rồi yêu cầu bên nhận tin theo. Khi ký một payload lớn, có thể gọi `update(byte[], off, len)` nhiều lần, nhưng **toàn bộ bytes trong cùng thứ tự** vẫn là một message duy nhất.

## 14. Bài tập tự luyện có đáp án

**Bài 1.** Với `Signature.getInstance("Ed25519")` không gọi `setParameter`, mode thông thường là gì?

**Đáp án:** Ed25519 thuần theo chế độ mặc định của provider Ed25519 tương thích. Nếu yêu cầu profile rõ ràng, có thể dùng `new EdDSAParameterSpec(false)` và kiểm tra provider chấp nhận; không tự gán context không cần thiết.

**Bài 2.** Hai constructor sau có tương đương nhau đối với Ed25519 không?

```java
new EdDSAParameterSpec(false);
new EdDSAParameterSpec(false, new byte[0]);
```

**Đáp án:** Không. Dòng đầu **không cung cấp context**, chọn pure Ed25519; dòng sau **có cung cấp context rỗng**, chọn mode có context và phân tách miền khác. Với Ed25519ctx, RFC 8032 còn khuyến nghị context nên không rỗng.

**Bài 3.** Nếu `new EdDSAParameterSpec(true, context)` được dùng với `Signature("Ed25519")`, đây là Ed25519ctx hay Ed25519ph?

**Đáp án:** **Ed25519ph** với context, vì `prehash=true`. Context không làm prehash tự tắt.

**Bài 4.** Context `"a"` và `"A"` (đều UTF-8) có là cùng context không?

**Đáp án:** Không. Context so sánh theo **bytes**; khác chữ hoa/thường làm khác bytes. Không tự đổi `toLowerCase` nếu giao thức không quy định.

**Bài 5.** Context 200 ký tự tiếng Việt có luôn hợp lệ theo giới hạn 255 không?

**Đáp án:** Không thể biết chỉ từ số ký tự. Java giới hạn **255 bytes**, và Unicode khi encode UTF-8 có thể chiếm nhiều bytes. Phải kiểm tra mảng `contextBytes.length`.

**Bài 6.** Bên ký đã bật `prehash=true`. Có nên cung cấp SHA-512 digest thay cho message gốc vào `update`?

**Đáp án:** Không nếu mục tiêu là Ed25519ph của **message gốc**. Provider tự prehash; đưa digest vào `update` sẽ khiến mode ph xử lý digest như **một message mới**.

**Bài 7.** Có thể dùng Ed25519 pure ký SHA-512 digest rồi coi đó là Ed25519ph không?

**Đáp án:** Không. Ed25519ph có domain separation/`phflag` khác pure. Chương trình ở phần 7 minh họa chữ ký khác nhau.

**Bài 8.** Ed25519ctx với `context="payment:v1"` có thể được xác minh bằng `context="payment:v2"` khi message/key vẫn đúng không?

**Đáp án:** Không. Context bytes là một phần của profile chữ ký; thay context khiến verify không khớp.

**Bài 9.** Khi nào dùng `new EdDSAParameterSpec(true)` với `Signature("Ed448")`?

**Đáp án:** Khi muốn chọn chế độ **Ed448ph** theo RFC 8032, không phải Ed25519ph. Curve được chọn bởi engine/key; tham số chọn prehash/context.

**Bài 10.** `EdDSAParameterSpec(false, new byte[256])` cho kết quả gì?

**Đáp án:** Ném `InvalidParameterException`, vì context vượt **255 bytes**.

**Bài 11.** Hai chữ ký đều dài 64 bytes. Có suy ra chúng cùng Ed25519 mode không?

**Đáp án:** Không. Ed25519, Ed25519ctx và Ed25519ph đều có chữ ký 64 bytes; cần metadata mode/context để xác minh đúng.

**Bài 12.** Một verifier cho phép request tự chọn context và mode tùy ý. Chỉ dựa vào `verify==true` có đủ để bảo đảm quyền phê duyệt đúng domain không?

**Đáp án:** Không. Phải kiểm tra profile/mode/context **được policy cho phép**, nguồn public key đáng tin, danh tính và quyền thực hiện hành động. Verify true chỉ chứng minh sự phù hợp mật mã theo cấu hình đã chọn.

### Checklist kiến thức

- [ ] Tôi phân biệt **Ed25519 pure**, **Ed25519ctx** và **Ed25519ph** theo RFC 8032.
- [ ] Tôi hiểu `EdDSAParameterSpec(prehash, context)` chọn mode chứ không chọn curve.
- [ ] Tôi biết context **vắng mặt** khác context **mảng rỗng** ở Ed25519.
- [ ] Tôi biết context tính bằng bytes và bị giới hạn **255 bytes**.
- [ ] Tôi biết `EdDSAParameterSpec.getContext()` trả `Optional<byte[]>` và trả bản sao bytes.
- [ ] Tôi đặt `Signature.setParameter(spec)` trước `initSign`/`initVerify`.
- [ ] Tôi hiểu prehash=true yêu cầu provider **xử lý prehash theo RFC 8032**, không phải tự SHA-512 hai lần.
- [ ] Tôi không nhầm Ed25519ph với pure Ed25519 ký digest.
- [ ] Tôi bảo đảm verifier dùng **đúng mode, context, public key và message bytes**.
- [ ] Tôi không dùng context để thay thế yêu cầu xác thực, phân quyền hay chống replay.
- [ ] Tôi không suy ra mode từ độ dài signature (64 bytes).
- [ ] Tôi biết cần kiểm tra khả năng hỗ trợ tham số của provider thực tế.
- [ ] Tôi có thể chạy các chương trình Java 17+ và giải thích đầu ra đúng/sai.

## 15. Tài liệu chính thức, còn áp dụng

1. [Java SE 25 — `EdDSAParameterSpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): hai constructor, prehash, context có/vắng, giới hạn 255 bytes và defensive copying. **API since Java 15**.
2. [Java SE 25 — `Signature`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): `getInstance`, `setParameter(AlgorithmParameterSpec)`, `initSign`, `initVerify`, `update`, `sign`, `verify`.
3. [Java SE 25 — `KeyPairGenerator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html): tạo cặp khóa Ed25519/Ed448 theo provider hỗ trợ.
4. [Java SE 25 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên chuẩn `EdDSA`, `Ed25519` và `Ed448` cho các JCA engine.
5. [Java SE 25 — Oracle Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): các thuật toán do provider `SunEC` cung cấp trong Oracle JDK.
6. [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032.html): `5.1 Ed25519ph, Ed25519ctx, Ed25519`; `7 Test Vectors`.
7. [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): EdDSA được đưa vào Java 15 và chuẩn hóa API Java.

**Kết luận thực hành:** `Signature.getInstance("Ed25519")` chọn nền tảng Ed25519; `EdDSAParameterSpec` mới chỉ định **prehash** và **context**. Không có context và không prehash là **Ed25519 pure**; có context và không prehash là **Ed25519ctx**; bật prehash là **Ed25519ph** (context tùy cấu hình). Bên ký và bên xác minh phải thống nhất hoàn toàn **mode, context bytes, message bytes và khóa**. Context rỗng **không** đồng nhất với context vắng mặt trong pure Ed25519, và Ed25519ph **không** tương đương việc tự băm message rồi ký bằng pure Ed25519.