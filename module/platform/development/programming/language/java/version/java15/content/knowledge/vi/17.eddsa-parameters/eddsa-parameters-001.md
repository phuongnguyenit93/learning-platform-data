# EdDSAParameterSpec và tham số cho Signature (Java 15+)

## 1. Mục tiêu bài học

Từ **Java 15**, Java Cryptography Architecture (JCA) hỗ trợ thuật toán chữ ký số **EdDSA** theo RFC 8032, thường dùng hai bộ tham số **Ed25519** và **Ed448**. Bên cạnh việc chọn thuật toán và cặp khóa, người viết ứng dụng còn cần kiểm soát **chế độ xử lý thông điệp trước khi ký** và **context** nhằm tách biệt mục đích sử dụng chữ ký.

Lớp tiêu chuẩn để biểu diễn những lựa chọn đó là:

~~~java
java.security.spec.EdDSAParameterSpec
~~~

`EdDSAParameterSpec` triển khai `AlgorithmParameterSpec` và được truyền vào đối tượng `java.security.Signature` qua phương thức **`setParameter(AlgorithmParameterSpec)`**.

Trong bài này, chúng ta sẽ hiểu:

1. `prehash` trong `EdDSAParameterSpec` có nghĩa gì, khác việc tự gọi `MessageDigest` ra sao.
2. `context` là dữ liệu gì, giới hạn 255 **byte**, và tại sao **không có context** khác **context rỗng** trong một số chế độ.
3. Tương quan giữa các chế độ RFC 8032: **Ed25519, Ed25519ctx, Ed25519ph, Ed448 và Ed448ph**.
4. Cách gắn **cùng tham số** cho cả `Signature` ký và `Signature` xác minh.
5. Những khác biệt giữa tham số chữ ký, tham số đường cong khóa (`NamedParameterSpec`), nội dung thông điệp, và định dạng chữ ký.
6. Cách kiểm thử, xử lý lỗi provider và tích hợp an toàn trong giao thức thực tế.

Đây là kiến thức **vẫn đang được sử dụng** trong Java hiện đại, không phải API preview hoặc cơ chế legacy. Không cần thư viện mật mã ngoài JDK để chạy ví dụ khi provider EdDSA hiện diện.

## 2. EdDSA, Ed25519/Ed448 và vai trò của Signature

EdDSA là thuật toán **ký/xác minh thông điệp**. Khóa riêng ký dữ liệu; khóa công khai xác minh chữ ký đó. Java cung cấp API chung `KeyPairGenerator`, `Signature` và `KeyFactory` cho nhiều thuật toán, bao gồm EdDSA.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

// Doan minh hoa can dat trong mot phuong thuc co throws Exception.
KeyPairGenerator keyGen = KeyPairGenerator.getInstance("Ed25519");
KeyPair keys = keyGen.generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(keys.getPrivate());
signer.update(new byte[] { 1, 2, 3 });
byte[] signed = signer.sign();
~~~

Mặc định thường là chế độ chữ ký Ed25519 không prehash, không context khi provider hỗ trợ theo chuẩn. Nhưng nếu **giao thức yêu cầu một chế độ khác**, bạn phải cấu hình tham số phù hợp thay vì dựa vào giá trị mặc định của provider.

**Phân biệt ba loại thông tin:**

| Khái niệm | API Java | Vai trò |
| --- | --- | --- |
| **Tên thuật toán ký** | `Signature.getInstance("Ed25519")` / `"Ed448"` / tên chung `"EdDSA"` khi provider hỗ trợ | Chọn engine và thuật toán chữ ký. |
| **Thông số đường cong của khóa** | `NamedParameterSpec.ED25519`, `NamedParameterSpec.ED448` | Dùng cho `KeyPairGenerator.initialize` và các KeySpec liên quan; xác định tập tham số khóa. |
| **Chế độ EdDSA của thao tác ký** | `EdDSAParameterSpec(prehash, context)` | Xác định việc prehash và context gắn với `Signature`. |

**`EdDSAParameterSpec` không tạo khóa, không chứa khóa bí mật và không quyết định cặp Ed25519/Ed448 thay cho khóa.** Nó điều khiển **chế độ ký/xác minh** trong phạm vi một `Signature` instance.

Đừng nhầm Ed25519 với **X25519**: X25519/X448 là cơ chế trao đổi khóa XDH, không phải thuật toán tạo chữ ký EdDSA. `EdDSAParameterSpec` cũng không phải `PSSParameterSpec` của RSA-PSS hay `ECGenParameterSpec` của đường cong ECDSA.

## 3. API EdDSAParameterSpec: hai constructor và hai getter

Java 15 cung cấp hai constructor:

~~~java
new EdDSAParameterSpec(boolean prehash);
new EdDSAParameterSpec(boolean prehash, byte[] context);
~~~

Và hai phương thức đọc thuộc tính:

~~~java
boolean isPrehash();
Optional<byte[]> getContext();
~~~

Ý nghĩa:

- `prehash=false`: không bật biến thể **ph** do RFC 8032 định nghĩa. Tùy sự hiện diện của context, đây có thể là Ed25519 thường hoặc Ed25519ctx; với Ed448 là chế độ không prehash.
- `prehash=true`: dùng biến thể **prehash** (Ed25519ph hoặc Ed448ph). Việc băm trước được **provider thực hiện theo định nghĩa thuật toán**.
- `context`: dãy byte ứng dụng cung cấp để phân biệt miền sử dụng chữ ký (*domain separation*).
- Constructor một tham số biểu diễn **context không hiện diện** (null bên trong đặc tả, `getContext().isEmpty()==true`).
- Constructor hai tham số biểu diễn **context hiện diện** và chấp nhận mảng byte **rỗng**; `getContext().isPresent()==true` kể cả khi mảng dài 0.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.spec.EdDSAParameterSpec;

EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
EdDSAParameterSpec withContext = new EdDSAParameterSpec(
        false, "orders:v1".getBytes(StandardCharsets.US_ASCII));
EdDSAParameterSpec prehash = new EdDSAParameterSpec(
        true, "orders:v1".getBytes(StandardCharsets.US_ASCII));

System.out.println(pure.isPrehash());            // false
System.out.println(pure.getContext().isEmpty()); // true
System.out.println(withContext.getContext().isPresent()); // true
System.out.println(prehash.isPrehash());         // true
~~~

Các class ở đây là những cấu trúc dữ liệu mô tả tham số. Chúng **chưa tự tạo một chữ ký**: bạn phải gọi `Signature.setParameter(...)` trên engine thích hợp, rồi `initSign/initVerify`, `update` và `sign/verify`.

### 3.1. Bảng chọn chế độ theo RFC 8032

Theo mô tả chính thức của `EdDSAParameterSpec`:

| Đường cong / thuật toán | `prehash` | Context | Chế độ cần hiểu |
| --- | --- | --- | --- |
| Ed25519 | `false` | **Không hiện diện** (`new EdDSAParameterSpec(false)`) | **Ed25519** thông thường (*pure Ed25519*). |
| Ed25519 | `false` | **Có hiện diện** (kể cả `new byte[0]`) | **Ed25519ctx**. |
| Ed25519 | `true` | Có hoặc không có context theo cấu hình | **Ed25519ph**. |
| Ed448 | `false` | Có hoặc không có context theo cấu hình | **Ed448** (chế độ không prehash). |
| Ed448 | `true` | Có hoặc không có context theo cấu hình | **Ed448ph**. |

Vì `EdDSAParameterSpec` là cơ chế mô tả **nhiều mode của RFC 8032**, hai chữ ký đều ghi tên engine `"Ed25519"` vẫn có thể **không tương thích** nếu một bên dùng `Ed25519` thường còn bên kia bật context hoặc prehash.

**Chú ý quan trọng với Ed448:** chế độ không prehash là Ed448; context là thành phần cấu hình của Ed448. Tài liệu Java cho phép phân biệt context vắng mặt với mảng context rỗng ở mức spec. Việc hai cấu hình có tạo ra chữ ký tương thích hay không phải được xác nhận theo thuật toán và provider đích; không suy diễn rằng mọi thuật toán xử lý hai trường hợp giống nhau.

### 3.2. Context **không có** khác context **rỗng**

So sánh:

~~~java
EdDSAParameterSpec absent =
        new EdDSAParameterSpec(false);

EdDSAParameterSpec explicitlyEmpty =
        new EdDSAParameterSpec(false, new byte[0]);

System.out.println(absent.getContext().isEmpty());           // true
System.out.println(explicitlyEmpty.getContext().isPresent()); // true
System.out.println(explicitlyEmpty.getContext().orElseThrow().length); // 0
~~~

Tài liệu API nêu rõ hai cấu hình **có thể tương ứng với các chế độ khác nhau**. Với **Ed25519**, việc đặt context hiện diện (dù là mảng rỗng) chuyển từ Ed25519 thường sang **Ed25519ctx**. Một hệ thống xác minh cấu hình “không context” có thể từ chối chữ ký được tạo trong chế độ “context rỗng”.

Trong thử nghiệm JDK 24/SunEC:

- Ed25519 ký bằng `new EdDSAParameterSpec(false)` rồi xác minh bằng `new EdDSAParameterSpec(false, new byte[0])` trả `false`.
- Ed448 trong cấu hình tương tự của thử nghiệm cho kết quả `true`, phù hợp với cách xử lý context rỗng ở chế độ Ed448 không prehash.

**Quy tắc thực hành:** Truyền cùng đặc tả chế độ đã thỏa thuận ở phía ký và phía xác minh. Không tự coi `null`/vắng mặt tương đương `new byte[0]` cho mọi chế độ và mọi provider.

## 4. Context là gì và những gì context không làm

**Context** là chuỗi byte dùng để phân biệt mục đích ký. Ví dụ, cùng hệ thống có nhiều loại thông điệp:

- Hóa đơn: `"invoices:v1"`.
- Lệnh thanh toán: `"payments:v1"`.
- Biên nhận đơn hàng: `"orders:v1"`.

Nếu giao thức được thiết kế có context phù hợp, chữ ký trong một miền không được chấp nhận trong miền khác, kể cả khi các thông điệp có thể trông giống nhau.

Đây là một dạng **domain separation** do thuật toán chữ ký triển khai theo RFC 8032. Context **không phải** là password, salt bí mật hay khóa. Nó thường có thể công khai; bên xác minh phải biết **cùng bytes context** để xác minh.

### 4.1. Giới hạn 255 byte

Constructor hai tham số cho phép context dài từ **0 đến 255 byte**:

~~~java
byte[] maxLengthContext = new byte[255];
EdDSAParameterSpec allowed =
        new EdDSAParameterSpec(false, maxLengthContext);
~~~

Nếu `context.length > 255`, constructor ném **`InvalidParameterException`**. Nếu truyền `null` cho constructor hai tham số, nó ném **`NullPointerException`**. Khi **không muốn có context**, dùng constructor **một tham số** thay vì truyền `null`.

~~~java
import java.security.InvalidParameterException;
import java.security.spec.EdDSAParameterSpec;

try {
    new EdDSAParameterSpec(false, new byte[256]);
    throw new AssertionError("Expected an exception");
} catch (InvalidParameterException expected) {
    System.out.println("context too long");
}
~~~

Giới hạn là **byte**, không phải ký tự Java (`String.length()`). Ví dụ context có dấu tiếng Việt mã hóa UTF-8 có thể dùng nhiều byte cho một ký tự. Hãy tính `contextBytes.length` **sau khi chọn encoding**.

### 4.2. Chọn bytes context ổn định

Nếu context lấy từ văn bản, cần xác định chuẩn encoding:

~~~java
import java.nio.charset.StandardCharsets;

byte[] context = "orders:v1"
        .getBytes(StandardCharsets.US_ASCII);
~~~

Nếu dùng UTF-8, cả bên ký và bên xác minh phải dùng **đúng dãy byte UTF-8**. Thay đổi khoảng trắng, chữ hoa/thường hoặc Unicode normalization sẽ tạo context khác và có thể làm việc xác minh thất bại.

Một convention như `"company-app:orders:v1"` có thể phù hợp với domain separation nếu được thiết kế xuyên suốt giao thức. Nhưng **đổi context sau khi ký không làm thay đổi chữ ký đã tạo**; cần giữ metadata cho bên xác minh theo chuẩn giao thức đã chọn.

### 4.3. Context không thay thế bảo mật giao thức

Context giúp tách miền sử dụng chữ ký, nhưng **không tự**:

- Xác định danh tính người ký.
- Bảo đảm public key được lấy từ nguồn tin cậy.
- Chống replay nếu giao thức không có timestamp/nonce/id và chính sách kiểm tra.
- Che giấu hoặc mã hóa thông điệp.
- Chứng minh context do một người có quyền phê duyệt.

Do đó, ứng dụng vẫn cần mô hình tin cậy khóa, quy tắc serialize thông điệp và các kiểm tra nghiệp vụ. **Mọi thứ được ký là bytes**, không phải đối tượng Java đã được người lập trình tưởng tượng sau khi serialize.

## 5. Prehash là gì? Không tự băm rồi giả làm chế độ ph

`prehash=true` kích hoạt biến thể EdDSA được định nghĩa trong RFC 8032:

- **Ed25519ph** dùng prehash dựa trên **SHA-512** theo đặc tả thuật toán.
- **Ed448ph** dùng prehash **SHAKE256** với đầu ra cần thiết theo RFC 8032.

Cơ chế prehash không chỉ là “băm trước một lần rồi gọi Ed25519 thường”. Các mode ph dùng **quy tắc domain separation** riêng, vì vậy:

~~~text
Ed25519ph(message, context)
    !=
Ed25519(SHA-512(message))
~~~

Ở đây dấu `!=` mô tả **hai cơ chế khác nhau**, không phải một phép so sánh Java thực thi. Nếu giao thức quy định Ed25519ph, dùng `new EdDSAParameterSpec(true, ...)` và đưa **thông điệp gốc** vào `Signature.update(...)`. Đừng tự băm message rồi lại bật `prehash=true`, vì bạn sẽ làm prehash hai lần/đổi nội dung ký.

~~~java
// Minh hoa trong ngữ cảnh đã có signer là Signature("Ed25519").
signer.setParameter(new EdDSAParameterSpec(true));
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Phần trên không phải chương trình độc lập: cần `privateKey` Ed25519 và `messageBytes` hợp lệ. Nó minh họa đúng **thứ tự cấu hình tham số rồi khởi tạo engine rồi đưa bytes thông điệp vào**.

**Không suy ra prehash luôn làm một chữ ký an toàn hơn.** Việc chọn Ed25519 thường, Ed25519ctx hay Ed25519ph phải tuân theo giao thức và profile đã thỏa thuận giữa hai bên. Nhiều trường hợp Ed25519 thông thường là đủ; không tự chọn một mode khác vì thấy thông điệp dài.

## 6. Gắn EdDSAParameterSpec vào Signature đúng cách

### 6.1. Luồng ký

~~~java
Signature signer = Signature.getInstance("Ed25519");
EdDSAParameterSpec params = new EdDSAParameterSpec(
        false, "orders:v1".getBytes(StandardCharsets.US_ASCII));

signer.setParameter(params);
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Đây là đoạn minh họa trong ngữ cảnh đã có khóa Ed25519 và dữ liệu bytes. Với `Ed448`, dùng `Signature.getInstance("Ed448")` và khóa Ed448, không trộn loại khóa.

Thứ tự **`setParameter → initSign → update → sign`** được dùng trong ví dụ đã kiểm thử, giúp cấu hình rõ mode trước khi gửi dữ liệu vào engine. Đừng đổi tham số khi đã bắt đầu xử lý thông điệp; provider có thể từ chối cập nhật trạng thái không hợp lệ.

### 6.2. Luồng xác minh

~~~java
Signature verifier = Signature.getInstance("Ed25519");

verifier.setParameter(params); // Cung tham so voi ben ky.
verifier.initVerify(publicKey);
verifier.update(messageBytes);

boolean accepted = verifier.verify(signature);
~~~

Các thành phần **phải tương thích**:

1. Thuật toán và tập tham số khóa: Ed25519 với Ed25519, Ed448 với Ed448.
2. Mode EdDSA: cùng lựa chọn prehash và sự hiện diện/bytes context theo quy định.
3. Public key thực sự tương ứng với private key đã ký.
4. **Cùng message bytes** (không chỉ cùng văn bản hiển thị).

Nếu một yếu tố thay đổi, `verify` thường trả `false` cho chữ ký đúng định dạng nhưng không khớp. Với dữ liệu chữ ký bị lỗi encoding hoặc tham số/provider không chấp nhận, `SignatureException` hoặc exception khác có thể xảy ra: không coi mọi lỗi là kết quả `false`.

### 6.3. Vì sao cần một Signature instance riêng cho mỗi bên?

`Signature` là một **đối tượng có trạng thái**. Một lần `initSign` hoặc `initVerify` định hướng nó vào chế độ ký hoặc xác minh; `update` tích lũy dữ liệu; `sign/verify` kết thúc operation. Đừng chia sẻ cùng một `Signature` instance đồng thời giữa nhiều thread và nhiều yêu cầu nếu không có chiến lược đồng bộ rõ.

Tạo một đối tượng mới cho mỗi operation giúp tránh state còn sót lại và làm hợp đồng tham số dễ kiểm toán. Provider có thể đặt những điều kiện riêng về thời điểm gọi `setParameter`; cấu hình nhất quán ngay trước mỗi operation là lựa chọn dễ bảo trì.

### 6.4. Không dùng setParameter(String,Object) đã deprecated

`Signature` có overload cũ:

~~~java
// Khong nen dung trong code moi:
signature.setParameter("name", value);
~~~

Overload nhận `String,Object` đã **deprecated**. Bài này dùng API **còn được khuyến nghị**:

~~~java
signature.setParameter(
        new EdDSAParameterSpec(false, contextBytes)
);
~~~

`EdDSAParameterSpec` là một triển khai `AlgorithmParameterSpec` có kiểu rõ ràng, tránh tên tham số string tùy ý. Nếu provider không chấp nhận spec đã truyền, `setParameter(AlgorithmParameterSpec)` có thể ném `InvalidAlgorithmParameterException`.

## 7. Ví dụ đầy đủ chạy được: Ed25519, Ed448, context và prehash

Chương trình sau kiểm thử nhiều cấu hình EdDSA mà **không in khóa riêng hoặc raw signature**. Nó chủ động tạo các cặp khóa bằng provider, ký message cố định, xác minh bằng cùng thông số, thử sai context và sai mode, kiểm tra defensive copy và giới hạn context.

**Lưu tệp `EdDSAParamsDemo.java`:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.InvalidParameterException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;

public class EdDSAParamsDemo {
    static byte[] sign(String algorithm, KeyPair keys, EdDSAParameterSpec params,
                       byte[] message) throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.setParameter(params);
        signer.initSign(keys.getPrivate());
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(String algorithm, KeyPair keys, EdDSAParameterSpec params,
                          byte[] message, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.setParameter(params);
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        return verifier.verify(signature);
    }

    static void demonstrate(String algorithm, NamedParameterSpec curve)
            throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance(algorithm);
        generator.initialize(curve);
        KeyPair keys = generator.generateKeyPair();

        byte[] message = "Java EdDSA modes".getBytes(StandardCharsets.UTF_8);
        byte[] context = "orders:v1".getBytes(StandardCharsets.US_ASCII);

        EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
        EdDSAParameterSpec contextual =
                new EdDSAParameterSpec(false, context);
        EdDSAParameterSpec prehashed =
                new EdDSAParameterSpec(true, context);

        byte[] copied = contextual.getContext().orElseThrow();
        context[0] = 'x';
        copied[0] = 'y';
        boolean copyProtected = Arrays.equals(
                "orders:v1".getBytes(StandardCharsets.US_ASCII),
                contextual.getContext().orElseThrow());

        byte[] plainSignature = sign(algorithm, keys, pure, message);
        byte[] ctxSignature = sign(algorithm, keys, contextual, message);
        byte[] phSignature = sign(algorithm, keys, prehashed, message);

        EdDSAParameterSpec wrongCtx = new EdDSAParameterSpec(
                false, "orders:v2".getBytes(StandardCharsets.US_ASCII));

        System.out.println(algorithm + ".pure=" +
                verify(algorithm, keys, pure, message, plainSignature));
        System.out.println(algorithm + ".context=" +
                verify(algorithm, keys, contextual, message, ctxSignature));
        System.out.println(algorithm + ".contextMismatch=" +
                verify(algorithm, keys, wrongCtx, message, ctxSignature));
        System.out.println(algorithm + ".prehash=" +
                verify(algorithm, keys, prehashed, message, phSignature));
        System.out.println(algorithm + ".modeMismatch=" +
                verify(algorithm, keys, pure, message, phSignature));
        System.out.println(algorithm + ".contextCopy=" + copyProtected);
        System.out.println(algorithm + ".prehashFlag=" +
                prehashed.isPrehash());
        System.out.println(algorithm + ".signatureBytes=" +
                phSignature.length);
    }

    public static void main(String[] args) throws Exception {
        EdDSAParameterSpec noContext = new EdDSAParameterSpec(false);
        EdDSAParameterSpec emptyContext =
                new EdDSAParameterSpec(false, new byte[0]);

        System.out.println("absentContext=" +
                noContext.getContext().isEmpty());
        System.out.println("presentEmptyContext=" +
                emptyContext.getContext().isPresent());

        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("context256Rejected=false");
        } catch (InvalidParameterException expected) {
            System.out.println("context256Rejected=true");
        }

        demonstrate("Ed25519", NamedParameterSpec.ED25519);
        demonstrate("Ed448", NamedParameterSpec.ED448);
    }
}
~~~

Biên dịch bằng JDK 17+ có hỗ trợ EdDSA; `--release 15` đảm bảo chương trình sử dụng API và ngôn ngữ tương thích Java 15:

~~~bash
javac --release 15 -encoding UTF-8 EdDSAParamsDemo.java
java EdDSAParamsDemo
~~~

**Đầu ra thực tế đã kiểm chứng trên JDK 24, SunEC:**

~~~text
absentContext=true
presentEmptyContext=true
context256Rejected=true
Ed25519.pure=true
Ed25519.context=true
Ed25519.contextMismatch=false
Ed25519.prehash=true
Ed25519.modeMismatch=false
Ed25519.contextCopy=true
Ed25519.prehashFlag=true
Ed25519.signatureBytes=64
Ed448.pure=true
Ed448.context=true
Ed448.contextMismatch=false
Ed448.prehash=true
Ed448.modeMismatch=false
Ed448.contextCopy=true
Ed448.prehashFlag=true
Ed448.signatureBytes=114
~~~

Kết quả có ý nghĩa như sau:

- **`absentContext=true`, `presentEmptyContext=true`:** Optional rỗng nghĩa là không có context; Optional có giá trị vẫn có thể chứa mảng dài 0.
- **`context256Rejected=true`:** độ dài context 256 byte bị từ chối trước khi gọi `Signature`.
- **`pure=true`, `context=true`, `prehash=true`:** mỗi cấu hình được dùng nhất quán ở cả phía ký và xác minh nên chữ ký hợp lệ.
- **`contextMismatch=false`:** chỉ thay từ context `orders:v1` sang `orders:v2` đã khiến xác minh thất bại, dù khóa và thông điệp không đổi.
- **`modeMismatch=false`:** lấy chữ ký tạo với prehash rồi kiểm tra bằng cấu hình không prehash thất bại.
- **`contextCopy=true`:** sửa mảng context ban đầu và bản sao từ `getContext()` không thay đổi bytes đã ràng buộc trong spec.
- **`signatureBytes=64` với Ed25519 và `114` với Ed448:** độ dài chữ ký theo các thuật toán thử nghiệm, không phải chiều dài của message hay khóa riêng.

`generator.generateKeyPair()` tạo **khóa ngẫu nhiên mới** mỗi lần chạy. Chương trình chỉ in trạng thái xác minh và độ dài chữ ký; không đưa raw key/signature ra log. Output này được kiểm chứng với provider/JDK đã nêu, không phải bảo đảm mọi provider sẽ hỗ trợ các mode tương tự.

### 7.1. Vì sao mã cố tình không tự gọi MessageDigest?

Vì `EdDSAParameterSpec(true, ...)` yêu cầu provider thực hiện **biến thể EdDSAph**. Mã gửi **message gốc** cho `Signature.update`, không gửi digest đã băm thủ công.

### 7.2. Vì sao sửa `context` sau khi dựng spec không đổi mode?

Constructor có sao chép `context` đầu vào; `getContext()` trả về bản sao. Vì vậy, việc sửa mảng nguồn hay bản sao chỉ sửa các byte ở bên ngoài đặc tả. Hãy xem `EdDSAParameterSpec` là cấu hình được chốt khi tạo, và tạo spec **mới** nếu cần chọn context khác.

### 7.3. Một thử nghiệm riêng về context rỗng

Trên JDK 24/SunEC, với cùng cặp khóa và message:

~~~text
Ed25519.pureToEmpty=false
Ed25519.emptyToPure=false
Ed448.pureToEmpty=true
Ed448.emptyToPure=true
~~~

Ở đây `pure` dùng `new EdDSAParameterSpec(false)` và `empty` dùng `new EdDSAParameterSpec(false, new byte[0])`. Đây là **kết quả của một phép thử bổ sung**, không phải output của chương trình chính. Nó minh họa tại sao tài liệu Java cảnh báo không được đồng nhất context vắng mặt với context rỗng trong mọi mode.

Đặc biệt với **Ed25519**, hai lựa chọn biểu diễn **hai mode** khác nhau. Trong giao thức thực tế, nên quy định rõ “absent” hoặc “present empty” thay vì ngầm chuẩn hóa chúng thành một.

## 8. Hợp đồng giao thức: phải lưu gì cùng chữ ký?

Chữ ký EdDSA thường được truyền dưới dạng dãy byte theo RFC 8032, **không phải tự đóng gói đủ thuật toán, context và thông tin cặp khóa**.

Vì thế, nếu bạn chỉ lưu:

~~~text
signature = <bytes>
~~~

thì bên nhận có thể chưa biết:

- Chữ ký được tạo bằng **Ed25519 hay Ed448**.
- Có bật **prehash** hay không.
- Có dùng **context** hay không; nếu có, bytes context cụ thể là gì.
- Khóa công khai xác minh là khóa nào.
- Thông điệp gốc đã được serialize thành bytes ra sao.

**Hợp đồng ở tầng giao thức nên có** những thông tin có thể tái tạo đúng operation, ví dụ một envelope dữ liệu được thiết kế và xác thực:

~~~text
algorithm = Ed25519
prehash = false
context_present = true
context_bytes = UTF8("orders:v1")
key_id = validated-key-identifier
message_bytes = canonical-serialized-data
signature_bytes = RFC-8032-signature
~~~

Đây là **sơ đồ khái niệm**, không phải định dạng JSON hay một API JDK có sẵn. Các field tùy ứng dụng cần được xác thực, tránh bị sửa đổi/đánh tráo. Không để đối tượng tấn công tự chọn mode hoặc public key tùy ý rồi coi verify thành công là người gửi đáng tin.

### 8.1. Domain separation và versioning

Một ứng dụng có thể đặt context `"invoice:v1"` để không chấp nhận chữ ký dành cho miền `"order:v1"`. Khi nâng phiên bản giao thức, cần cân nhắc **có đổi context không**, cách tương thích với chữ ký cũ, cách lưu metadata và cách ngăn kẻ tấn công ép hệ thống dùng lại mode cũ.

Context không có tính bí mật; **không nhét mật khẩu, token, private-key bytes** vào context rồi tưởng thuật toán tự mã hóa chúng.

### 8.2. Signature xác minh dữ liệu byte-for-byte

~~~java
byte[] messageBytes = messageText.getBytes(StandardCharsets.UTF_8);
~~~

Ví dụ này cần một `messageText` có sẵn. Nếu bên ký và bên xác minh dùng encoding khác, Unicode normalization khác, hoặc serialized JSON khác thứ tự trường/khoảng trắng, chữ ký có thể không hợp lệ dù văn bản đọc được trông tương đương.

Với tài liệu có cấu trúc, hãy chọn canonical serialization và encoding ổn định trước khi ký; context được kiểm soát độc lập với message bytes.

## 9. EdDSAParameterSpec khác NamedParameterSpec và các KeySpec

Hai tên cùng có chữ “ParameterSpec” nhưng mục đích khác nhau:

| API | Thuộc lớp | Được dùng tại đâu? |
| --- | --- | --- |
| `NamedParameterSpec.ED25519` / `ED448` | Tham số đường cong/thuật toán khóa | `KeyPairGenerator.initialize`, đặc tả EdEC key, chọn curve. |
| `EdDSAParameterSpec` | Tham số **chế độ chữ ký** | `Signature.setParameter(AlgorithmParameterSpec)`. |
| `EdECPublicKeySpec` | Mô tả public key | `KeyFactory.generatePublic`. |
| `EdECPrivateKeySpec` | Mô tả private key | `KeyFactory.generatePrivate`. |
| `PSSParameterSpec` | Tham số RSA-PSS | Chỉ dùng với signature algorithms thích hợp, **không phải EdDSA**. |

Chọn Ed25519 cho `Signature` rồi truyền `NamedParameterSpec.ED448` qua `Signature.setParameter` **không phải** cách đổi curve. Engine EdDSA kỳ vọng loại tham số phù hợp như `EdDSAParameterSpec`; provider có quyền từ chối spec không thích hợp.

KeySpec dùng để **tạo/khôi phục khóa**; EdDSAParameterSpec dùng để **cấu hình mode ký/xác minh**. Hai tầng này nên được cấu hình, kiểm tra và ghi nhận riêng trong dự án.

## 10. Lỗi thường gặp và hành vi provider

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ký với context nhưng verify không đặt context | Hai `Signature` khác mode. | Cấu hình cùng `EdDSAParameterSpec` đã thỏa thuận ở cả hai phía. |
| Ký với `prehash=true`, xác minh với `false` | EdDSAph khác mode không prehash. | Truyền đúng cờ và context khi verify. |
| Ký với context `A`, xác minh context `B` | Domain separation làm chữ ký không tương thích. | Truyền đúng bytes context, không chỉ cùng độ dài. |
| Tự băm SHA-512 rồi bật `prehash=true` | Dữ liệu đưa vào provider đã bị biến đổi; tạo chữ ký khác giao thức. | Đưa message gốc vào `update`; để provider xử lý chế độ ph. |
| Coi `new EdDSAParameterSpec(false)` giống `(..., new byte[0])` với Ed25519 | Ed25519 và Ed25519ctx là hai mode khác nhau. | Ghi rõ context có hiện diện hay không trong hợp đồng. |
| Context 256 ký tự/byte bị từ chối | API giới hạn **255 byte**, không phải 255 Java chars. | Tạo bytes theo encoding đã chọn, kiểm tra `bytes.length`. |
| Sửa context nguồn rồi mong spec thay đổi | Spec giữ defensive copy. | Tạo spec mới nếu cần context khác. |
| Dùng `setParameter(String,Object)` | Overload deprecated, thiếu type safety. | Dùng `setParameter(AlgorithmParameterSpec)`. |
| Truyền `EdDSAParameterSpec` cho `KeyPairGenerator.initialize` | Khác loại/ý nghĩa tham số. | Dùng `NamedParameterSpec` cho key generation. |
| Truyền `NamedParameterSpec` cho `Signature.setParameter` | Provider có thể không hỗ trợ loại spec đó cho Signature. | Dùng `EdDSAParameterSpec` cho mode. |
| `Signature.getInstance("Ed448")` thất bại | Provider không hỗ trợ thuật toán được yêu cầu. | Kiểm tra JDK và provider JCA trước khi triển khai. |
| `Signature.setParameter(...)` ném `InvalidAlgorithmParameterException` | Mode/context/spec không được provider chấp nhận. | Xác nhận hỗ trợ và profile giao thức; không ép bỏ params âm thầm. |
| `Signature.initSign/initVerify` ném `InvalidKeyException` | Khóa sai curve, sai provider hoặc không dùng được. | Chọn khóa EdDSA phù hợp với engine. |
| `Signature.verify` trả `false` | Chữ ký, message, khóa hoặc mode/context không khớp. | Xem đây là xác minh thất bại; kiểm tra các yếu tố, không chấp nhận dữ liệu. |
| `Signature.verify` ném `SignatureException` | Chữ ký bị hỏng cấu trúc hoặc engine không xử lý được. | Xử lý lỗi an toàn, không tự chuyển thành hợp lệ. |
| Tin rằng context hay chữ ký tự chứng minh danh tính | Verify chỉ kiểm tra với public key được chọn. | Phải tin cậy public key và kiểm soát metadata/giao thức. |

**Kiểm soát provider:** Tên `"Ed25519"` và `"Ed448"` có trong danh mục Java Security Standard Algorithm Names, nhưng chi tiết hỗ trợ phụ thuộc JCA provider và cấu hình runtime. Khi ứng dụng cần cả Ed25519ph/Ed448ph hoặc context, hãy **kiểm thử trên đúng JDK/provider sẽ triển khai**. Không lặng lẽ bỏ context hay tắt prehash để “chạy được”, vì như vậy làm **đổi hợp đồng mật mã**.

**Không dựa vào `Signature.getParameters()` để tự động chuyển mọi tham số sang bên nhận.** JavaDoc nêu rằng một số signature schemes không cung cấp được params qua `AlgorithmParameters`, nên phương thức có thể trả `null`; hãy truyền thông tin thuật toán, mode và context bằng giao thức đã thiết kế.

## 11. Bộ kiểm thử đề xuất

### 11.1. Ma trận chức năng

Với mỗi curve mà provider hỗ trợ, test ít nhất:

| Ca | Cấu hình ký | Cấu hình xác minh | Kỳ vọng |
| --- | --- | --- | --- |
| Cùng mode đơn giản | `prehash=false`, không context | Giống bên ký | `true`. |
| Cùng context | `false`, `orders:v1` | `false`, `orders:v1` | `true`. |
| Sai context | `false`, `orders:v1` | `false`, `orders:v2` | `false`. |
| Cùng ph | `true`, `orders:v1` | Giống bên ký | `true`. |
| Sai chế độ | `true`, `orders:v1` | `false`, không context | `false`. |
| Đổi message | Bất kỳ mode hợp lệ | Giữ mode, thay message bytes | `false`. |
| Đổi public key | Ký bởi khóa A | Xác minh bằng khóa B | `false` cho chữ ký đúng định dạng. |

Khi gặp chữ ký không đúng định dạng hoặc tham số không hỗ trợ, provider có thể ném exception: test negative cần cho phép hoặc kiểm tra **lỗi được quy định rõ**, không khẳng định mọi dữ liệu sai đều trả `false`.

### 11.2. Test ranh giới context

- Context **vắng mặt** → `getContext().isEmpty() == true`.
- Context **rỗng có hiện diện** → `getContext().isPresent() == true`, mảng dài 0.
- Context **255 byte** → constructor chấp nhận.
- Context **256 byte** → `InvalidParameterException`.
- Context `null` ở constructor hai tham số → `NullPointerException`.
- Sửa byte[] đầu vào hoặc mảng lấy từ `getContext()` không sửa được dữ liệu trong spec.
- Context UTF-8 có dấu cần kiểm tra **độ dài bytes**, không phải số ký tự Unicode.

### 11.3. Test tích hợp và bảo mật

- Dùng **đúng curve** tại `KeyPairGenerator`, `Signature` và public/private keys.
- Test trên runtime/provider giống production; kiểm tra đủ các mode ứng dụng cần.
- Không log raw private key và không log message nhạy cảm khi có thể tránh.
- Dùng serialization ổn định, xác minh public key qua nguồn đáng tin.
- Kiểm soát replay/id/timestamp khi yêu cầu nghiệp vụ; chữ ký hợp lệ **không tự chống replay**.
- Nếu đồng thời chạy nhiều operation, mỗi operation tạo `Signature` riêng hoặc sử dụng thread confinement thích hợp.
- Không giả định có thể chuyển đổi trực tiếp Ed25519ph thành Ed25519 thường hoặc ngược lại; phải ký lại bằng mode mong muốn.

## 12. Tự kiểm tra

**1. `EdDSAParameterSpec` dùng để tạo khóa Ed25519 hay đặt mode cho `Signature`?**

Nó đặt mode prehash và context cho **Signature**. Để chọn curve tạo khóa, sử dụng `NamedParameterSpec` với `KeyPairGenerator`.

**2. `new EdDSAParameterSpec(false)` khác `new EdDSAParameterSpec(false, new byte[0])` thế nào?**

Constructor một tham số biểu diễn **không có context**. Constructor hai tham số biểu diễn **context có hiện diện**, dù byte array rỗng. Với Ed25519, việc có context kích hoạt **Ed25519ctx**, khác chế độ Ed25519 thông thường.

**3. `prehash=true` có nghĩa tự băm message trước rồi dùng Ed25519 thường không?**

Không. Nó chọn **Ed25519ph/Ed448ph**; provider xử lý prehash cùng domain separation đúng RFC 8032. Ứng dụng đưa thông điệp gốc vào `Signature.update`.

**4. Context có được dài 256 byte không?**

Không. `EdDSAParameterSpec(boolean, byte[])` giới hạn tối đa **255 byte** và ném `InvalidParameterException` nếu dài hơn.

**5. Sửa mảng context truyền vào constructor sau khi tạo spec có đổi chữ ký không?**

Không đổi cấu hình trong spec vì constructor sao chép context. `getContext()` cũng trả bản sao. Muốn đổi context, tạo một spec mới và cấu hình operation mới.

**6. Tại sao bên xác minh phải biết prehash và context?**

Vì mode và context tham gia vào phép tính chữ ký; hai bên phải xử lý đúng cùng dạng message bytes và cùng mode. Chữ ký raw không tự bảo đảm rằng bên nhận có đủ metadata ấy.

**7. Xác minh thành công có chứng minh key thuộc người gửi tự nhận không?**

Không. `verify` chứng minh chữ ký phù hợp với public key đã chọn và message bytes. Ứng dụng phải kiểm tra nguồn tin cậy của public key và thông tin định danh riêng.

## Ghi nhớ

- **`EdDSAParameterSpec(boolean prehash[, byte[] context])` là cấu hình EdDSA cho `Signature`**; Java 15+ hỗ trợ các mode RFC 8032.
- **`prehash=true` chọn Ed25519ph/Ed448ph**, không phải “băm thủ công rồi dùng Ed25519 thường”.
- **Context tối đa 255 byte**, không bí mật, dùng cho domain separation; constructor và getter sao chép mảng.
- **Vắng mặt context khác hiện diện nhưng rỗng**, đặc biệt quan trọng với Ed25519 và Ed25519ctx.
- **Cùng khóa/chữ ký chưa đủ**: ký và xác minh phải thống nhất thuật toán, mode, context và message bytes.
- **Dùng `Signature.setParameter(AlgorithmParameterSpec)`**, tránh overload `setParameter(String,Object)` đã deprecated.
- **Không dùng `EdDSAParameterSpec` thay `NamedParameterSpec` hoặc KeySpec**, vì chúng phục vụ các tầng khác nhau.

### Tài liệu chính thức còn áp dụng

- [Oracle Java 15 – EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): constructor, `isPrehash`, `getContext`, context absent/empty và giới hạn 255 byte.
- [Oracle Java 25 – EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): API EdDSAParameterSpec trên Java hiện đại.
- [Oracle Java 25 – Signature](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): `setParameter`, `initSign`, `initVerify`, `update`, `sign`, `verify` và lifecycle của engine.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên thuật toán EdDSA, Ed25519, Ed448.
- [JEP 339 – Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): giới thiệu EdDSA và API từ Java 15.
- [RFC 8032 – Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): định nghĩa Ed25519, Ed25519ctx, Ed25519ph, Ed448 và Ed448ph.
