# Kiểm thử khác chế độ, khác context và sai thông điệp với EdDSA (Java 15+)

## Mục tiêu

Một chữ ký EdDSA không chỉ phụ thuộc **khóa công khai**, **khóa riêng** và **thông điệp**. Với các biến thể **Ed25519**, **Ed25519ctx**, **Ed25519ph**, **Ed448** và **Ed448ph**, chương trình còn cần nhất quán **chế độ prehash** và **context**. Bài học hướng dẫn xây dựng bộ kiểm thử Java với cả đối chứng hợp lệ và các trường hợp cố ý làm chữ ký không xác minh được.

Sau bài, bạn có thể:

- Dùng **EdDSAParameterSpec** để cấu hình **prehash=true/false** và context.
- Viết chương trình ký/xác minh với **Signature** trên **Ed25519** và **Ed448**.
- Kiểm tra đổi **context**, đổi **prehash**, đổi **message bytes**, sửa **signature bytes** và chứng minh các trường hợp ấy không dùng lại được chữ ký ban đầu.
- Phân biệt **context không được cung cấp** với **context là byte[0]**, đặc biệt với Ed25519.
- Phân biệt **verify(false)** với **InvalidKeyException**, **InvalidAlgorithmParameterException**, **SignatureException** hay lỗi khởi tạo tham số.
- Thiết kế test matrix đủ để phát hiện lỗi cấu hình giữa các dịch vụ và bảo đảm đúng hợp đồng ký số.

**EdDSAParameterSpec** là API chuẩn từ **Java 15** và vẫn được hỗ trợ trong Java 17 trở lên. Ví dụ sử dụng API chính thức, biên dịch ở mức **Java 17** và không dựa vào cơ chế đã lỗi thời.

## 1. EdDSA có nhiều chế độ — không chỉ hai tên thuật toán

EdDSA (Edwards-curve Digital Signature Algorithm) được định nghĩa trong **RFC 8032**. Trong Java, hai lựa chọn đường cong thường gặp là **Ed25519** và **Ed448**. Mỗi đường cong có các biến thể tùy việc tiền băm thông điệp và context:

| Đường cong | Chế độ | Ý nghĩa |
| --- | --- | --- |
| Ed25519 | **Ed25519** | Không prehash, không context (pure Ed25519) |
| Ed25519 | **Ed25519ctx** | Không prehash, **có context** |
| Ed25519 | **Ed25519ph** | **Prehash** theo RFC 8032; có thể có context |
| Ed448 | **Ed448** | Không prehash; hỗ trợ context, mặc định context rỗng |
| Ed448 | **Ed448ph** | **Prehash** theo RFC 8032; có thể có context |

Một bên ký Ed25519ctx và bên kia xác minh Ed25519 thuần **không phải cùng một chế độ**, dù dùng đúng cặp khóa, cùng message bytes và cùng tên thuật toán ở lời gọi Signature.getInstance.

**Phân biệt hai cấp lựa chọn:**

1. **Signature.getInstance("Ed25519")** hoặc **Signature.getInstance("Ed448")** chọn thuật toán gắn với đường cong.
2. **Signature.setParameter(EdDSAParameterSpec)** quyết định **prehash** và **context** trong các biến thể được provider hỗ trợ.

Không suy ra rằng cứ ghi Ed25519 ở tên Signature thì nó bắt buộc là biến thể thuần. Các API Java 15+ hỗ trợ mô tả những biến thể khác theo RFC 8032 thông qua EdDSAParameterSpec.

## 2. Cách EdDSAParameterSpec xác định chế độ

Hai constructor hiện hành:

~~~java
EdDSAParameterSpec(boolean prehash);
EdDSAParameterSpec(boolean prehash, byte[] context);
~~~

Đây là **chữ ký constructor để giải thích API**, không phải chương trình độc lập. EdDSAParameterSpec thuộc package **java.security.spec**.

Bảng ánh xạ:

| Signature algorithm | Tham số | Chế độ sử dụng |
| --- | --- | --- |
| Ed25519 | new EdDSAParameterSpec(false) | Ed25519 thuần |
| Ed25519 | new EdDSAParameterSpec(false, ctx) | Ed25519ctx |
| Ed25519 | new EdDSAParameterSpec(true) | Ed25519ph, không cung cấp context |
| Ed25519 | new EdDSAParameterSpec(true, ctx) | Ed25519ph, với context |
| Ed448 | new EdDSAParameterSpec(false) | Ed448, context mặc định rỗng |
| Ed448 | new EdDSAParameterSpec(false, ctx) | Ed448, với context |
| Ed448 | new EdDSAParameterSpec(true) hoặc (true, ctx) | Ed448ph, context tương ứng |

Ví dụ trong một phương thức Java:

~~~java
EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
EdDSAParameterSpec orders = new EdDSAParameterSpec(
        false, "orders-v1".getBytes(StandardCharsets.UTF_8));
EdDSAParameterSpec ordersPrehash = new EdDSAParameterSpec(
        true, "orders-v1".getBytes(StandardCharsets.UTF_8));
~~~

Cần import **java.security.spec.EdDSAParameterSpec** và **java.nio.charset.StandardCharsets**. Ba đối tượng trên đại diện ba cấu hình khác nhau.

### Prehash được triển khai theo thuật toán, không phải tự băm bên ngoài

**prehash=true** chọn biến thể Ed25519ph hoặc Ed448ph. Không nên hiểu đó là chỉ thị “hãy tự gọi SHA-256 rồi truyền digest vào Signature.update()”.

- Ed25519ph dùng bước prehash theo **SHA-512** do RFC 8032 xác định.
- Ed448ph dùng bước prehash theo **SHAKE256** cùng quy tắc đầu ra trong RFC.
- Provider xử lý logic prehash khi dùng EdDSAParameterSpec.
- Ứng dụng vẫn truyền **message bytes ban đầu** bằng **Signature.update(...)**, không thay bằng một digest do ứng dụng tự tính, trừ khi toàn bộ giao thức thiết kế cụ thể như vậy.

**Điều cần kiểm thử:** Một chữ ký được tạo với **prehash=false** không thể được xác minh bằng **prehash=true** chỉ vì giống private/public key và context. Bộ test cần có cả kết quả false của cấu hình không trùng và kết quả true của **cùng prehash=true ở hai phía**.

## 3. Context là một phần của hợp đồng mật mã

Context trong EdDSA là **byte[]** dùng để tách miền sử dụng chữ ký (*domain separation*). Ví dụ cùng một ứng dụng dùng khóa EdDSA để ký hai loại thông điệp:

- **"orders-v1"**: thông điệp nghiệp vụ đơn hàng.
- **"invoices-v1"**: thông điệp nghiệp vụ hóa đơn.

Khi bên ký dùng context orders-v1 nhưng bên xác minh dùng invoices-v1, chữ ký ban đầu **không xác minh được** ngay cả khi thông điệp, khóa và chế độ prehash đều giữ nguyên.

Ví dụ:

~~~java
byte[] orderContext = "orders-v1".getBytes(StandardCharsets.UTF_8);
byte[] invoiceContext = "invoices-v1".getBytes(StandardCharsets.UTF_8);

EdDSAParameterSpec orders = new EdDSAParameterSpec(false, orderContext);
EdDSAParameterSpec invoices = new EdDSAParameterSpec(false, invoiceContext);
~~~

Đoạn trên là **code minh họa bên trong phương thức** với import thích hợp. Khi ký bằng orders, xác minh bằng invoices phải được xem là một case âm.

### Quy tắc context trong API Java

- **Context dài tối đa 255 byte**. Đây là **byte**, không phải số ký tự Unicode.
- Constructor hai tham số **sao chép** byte[] context. Nếu truyền **null**, nó ném **NullPointerException**; nếu context dài **hơn 255 byte**, nó ném **InvalidParameterException**.
- Constructor một tham số tạo spec **không cung cấp context**.
- **getContext()** trả **Optional<byte[]>**, là Optional.empty() nếu không có context, hoặc Optional chứa **bản sao** context nếu có.
- Context **không cần bí mật** nhưng cần được cả hai bên thống nhất chính xác, có thể là một nhãn giao thức ổn định.
- Nếu context biểu diễn bằng String, phải thống nhất **UTF-8, normalization, chữ hoa/thường và khoảng trắng** trước khi chuyển thành byte[].
- Context không được tự động truyền kèm trong mảng signature; dịch vụ xác minh phải biết context phù hợp qua giao thức hoặc cấu hình đáng tin cậy.

**Sai lầm dễ mắc:** áp dụng **getContext().orElse(new byte[0])** rồi tạo một EdDSAParameterSpec mới. Cách đó làm mất sự khác biệt giữa **không có context** và **có context rỗng**, ảnh hưởng trực tiếp tới chế độ Ed25519 không prehash.

## 4. Context rỗng khác context vắng mặt khi nào?

So sánh:

~~~java
EdDSAParameterSpec absent = new EdDSAParameterSpec(false);
EdDSAParameterSpec empty = new EdDSAParameterSpec(false, new byte[0]);
~~~

Đoạn code là minh họa. Cả hai đều không có byte context hữu ích theo nghĩa độ dài, nhưng **tính hiện diện của context** là dữ liệu cần được API xử lý đúng.

**Đối với Ed25519 không prehash:**

- **absent** tạo chế độ **Ed25519 thuần**.
- **empty** tạo chế độ **Ed25519ctx với context dài 0**.
- Hai chế độ dùng domain separation khác nhau. Chữ ký thuần Ed25519 **không xác minh được** dưới cấu hình Ed25519ctx rỗng.

**Đối với Ed448 không prehash:**

- Khi context không được cung cấp, context hiệu dụng là rỗng theo chế độ Ed448.
- Khi cung cấp byte[0], context hiệu dụng vẫn rỗng.
- Vì vậy, ở Ed448 **không prehash**, chữ ký tạo bằng cấu hình absent có thể xác minh bằng explicit empty context, nếu các yếu tố khác khớp.

Bộ test ở mục 7 in đúng hai kết quả **false** (Ed25519) và **true** (Ed448) để chứng minh khác biệt này.

Đừng suy đoán rằng mọi biến thể EdDSA xử lý absent và empty giống nhau. Cần bám vào hợp đồng của **RFC 8032** và **EdDSAParameterSpec**.

## 5. Dùng Signature đúng cách để tách test case

Một test chỉ nên thay đổi **một điều kiện** so với mẫu đối chứng. Vì **Signature** có trạng thái, nên tốt nhất mỗi test sử dụng đối tượng Signature mới:

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(
        false, "orders-v1".getBytes(StandardCharsets.UTF_8)));
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signatureBytes = signer.sign();
~~~

Đây là đoạn code minh họa trong phương thức có privateKey, messageBytes cùng import tương ứng. Khi xác minh, đặt tham số tương thích:

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.setParameter(new EdDSAParameterSpec(
        false, "orders-v1".getBytes(StandardCharsets.UTF_8)));
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
~~~

**Thứ tự của ví dụ:** chọn thuật toán → đặt EdDSAParameterSpec → initSign/initVerify → update → sign/verify. Việc tạo Signature mới giúp các test không phụ thuộc trạng thái, dữ liệu hoặc tham số của test trước.

Không sử dụng overload **Signature.setParameter(String,Object)** đã bị deprecated; sử dụng **setParameter(AlgorithmParameterSpec)** như trên. Một provider không hỗ trợ mode hoặc tham số cần thiết có thể ném **InvalidAlgorithmParameterException**; đó là lỗi cấu hình, **không** phải bằng chứng thông điệp bị sửa.

## 6. Ma trận test dương tính và âm tính

Giả sử người ký tạo chữ ký trên **"order=42;amount=100"**, với **Ed25519ctx**, **context=orders-v1**, **prehash=false**. Cùng cặp khóa và chữ ký, các test sau đổi duy nhất yếu tố cần khảo sát:

| Case | Bên xác minh | Message xác minh | Kỳ vọng |
| --- | --- | --- | --- |
| Đối chứng đúng | Ed25519ctx, orders-v1 | order=42;amount=100 | **true** |
| Context khác | Ed25519ctx, invoices-v1 | Message gốc | **false** |
| Chế độ khác | Ed25519ph, orders-v1 | Message gốc | **false** |
| Thông điệp khác | Ed25519ctx, orders-v1 | order=42;amount=101 | **false** |
| Bỏ context | Ed25519 thuần, không chỉ định context | Message gốc | **false** |
| Sửa chữ ký một bit | Ed25519ctx, orders-v1 | Message gốc | **false** trong ví dụ |
| Ký bằng Ed25519ph rồi xác minh Ed25519ph | Prehash=true, orders-v1 ở cả hai phía | Message gốc | **true** |
| Ký Ed25519ph rồi xác minh Ed25519 thuần | Prehash=false, không context | Message gốc | **false** |

**Vì sao bắt buộc có test true?** Một bộ kiểm thử mà tất cả trường hợp đều false có thể bị sai **public key** hoặc **Signature algorithm** ngay từ đầu; không chứng minh được rằng cơ chế ký và xác minh cơ bản hoạt động.

Chạy bảng đối chứng tương tự cho Ed448 nếu ứng dụng dùng cả hai đường cong. Khi đổi từ **Ed25519 sang Ed448**, dùng **cặp khóa mới phù hợp** để tránh biến test context thành lỗi do khóa không tương thích.

Bên cạnh các case sai dữ liệu, thêm test **context quá 255 byte**, **context null**, **khóa sai đường cong**, **signature format không hợp lệ** và **provider không hỗ trợ tham số**. Một số trường hợp phải kiểm tra **exception**, không phải chỉ verify(false).

## 7. Chương trình Java 17+ hoàn chỉnh: kiểm thử hai đường cong

Chương trình tạo một cặp khóa cho từng đường cong, cố ý xác minh sai context, sai thông điệp, sai prehash, bỏ context và sửa chữ ký. Sau đó thử ký và xác minh lại bằng cùng prehash, cùng context để có **đối chứng dương tính** ở biến thể prehash.

Toàn bộ mã lưu vào file **EdDSAModeContextDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class EdDSAModeContextDemo {
    private static byte[] context(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] sign(String algorithm, PrivateKey key,
                               EdDSAParameterSpec parameters, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(algorithm);
        signer.setParameter(parameters);
        signer.initSign(key);
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(String algorithm, PublicKey key,
                                  EdDSAParameterSpec parameters,
                                  byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.setParameter(parameters);
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signature);
    }

    private static void exercise(String algorithm) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance(algorithm).generateKeyPair();

        byte[] message = context("order=42;amount=100");
        byte[] changed = context("order=42;amount=101");

        EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
        EdDSAParameterSpec orders =
                new EdDSAParameterSpec(false, context("orders-v1"));
        EdDSAParameterSpec otherContext =
                new EdDSAParameterSpec(false, context("invoices-v1"));
        EdDSAParameterSpec prehash =
                new EdDSAParameterSpec(true, context("orders-v1"));

        byte[] signed = sign(algorithm, pair.getPrivate(), orders, message);
        System.out.println("[" + algorithm + "]");
        System.out.println("Same context/message: "
                + verify(algorithm, pair.getPublic(), orders, message, signed));
        System.out.println("Other context: "
                + verify(algorithm, pair.getPublic(), otherContext, message, signed));
        System.out.println("Other message: "
                + verify(algorithm, pair.getPublic(), orders, changed, signed));
        System.out.println("Other prehash mode: "
                + verify(algorithm, pair.getPublic(), prehash, message, signed));
        System.out.println("Context vs absent: "
                + verify(algorithm, pair.getPublic(), pure, message, signed));

        byte[] prehashedSignature = sign(algorithm, pair.getPrivate(), prehash, message);
        System.out.println("Prehash matches: "
                + verify(algorithm, pair.getPublic(), prehash, message, prehashedSignature));
        System.out.println("Prehash vs pure: "
                + verify(algorithm, pair.getPublic(), pure, message, prehashedSignature));

        EdDSAParameterSpec emptyContext =
                new EdDSAParameterSpec(false, new byte[0]);
        byte[] pureSignature = sign(algorithm, pair.getPrivate(), pure, message);
        System.out.println("Absent vs explicit empty context: "
                + verify(algorithm, pair.getPublic(), emptyContext, message, pureSignature));

        byte[] modified = signed.clone();
        modified[0] ^= 1;
        System.out.println("Modified signature: "
                + verify(algorithm, pair.getPublic(), orders, message, modified));
    }

    public static void main(String[] args) throws Exception {
        exercise("Ed25519");
        exercise("Ed448");
        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("256 byte context: accepted");
        } catch (InvalidParameterException e) {
            System.out.println("256 byte context: InvalidParameterException");
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 EdDSAModeContextDemo.java
java EdDSAModeContextDemo
~~~

**Stdout chính xác** sau khi biên dịch bằng --release 17 và thực thi thành công trên **JDK 24**:

~~~text
[Ed25519]
Same context/message: true
Other context: false
Other message: false
Other prehash mode: false
Context vs absent: false
Prehash matches: true
Prehash vs pure: false
Absent vs explicit empty context: false
Modified signature: false
[Ed448]
Same context/message: true
Other context: false
Other message: false
Other prehash mode: false
Context vs absent: false
Prehash matches: true
Prehash vs pure: false
Absent vs explicit empty context: true
Modified signature: false
256 byte context: InvalidParameterException
~~~

### Giải thích kết quả

1. **Same context/message: true:** ký và xác minh cùng khóa, thuật toán, mode, context và bytes thông điệp.
2. **Other context: false:** giữ các yếu tố khác, thay duy nhất context orders-v1 thành invoices-v1; chữ ký không còn xác minh.
3. **Other message: false:** sửa số tiền từ 100 thành 101, giữ context và mode.
4. **Other prehash mode: false:** biến thể xác minh prehash=true khác biến thể đã ký prehash=false.
5. **Context vs absent: false:** chữ ký đã ký với context orders-v1 không được xác minh khi bỏ context.
6. **Prehash matches: true:** chứng minh prehash=true không phải một cấu hình luôn sai; khi cả hai bên đồng nhất, nó hoạt động.
7. **Prehash vs pure: false:** chữ ký prehash không tự tương thích với chế độ không prehash.
8. **Absent vs explicit empty context:** **false ở Ed25519**, **true ở Ed448** trong trường hợp prehash=false; đây là bẫy về tính hiện diện context.
9. **Modified signature: false:** chương trình lật một bit trong bản sao chữ ký. Với chữ ký sai định dạng theo cách khác, một provider có thể ném SignatureException.
10. **256 byte context: InvalidParameterException:** kiểm tra ranh giới độ dài context.

Chương trình dùng cặp khóa sinh ngẫu nhiên ở mỗi lượt nhưng không in private key hoặc chữ ký. Các kết quả true/false ở đây là những case được xây dựng và kiểm chứng, không phụ thuộc vào giá trị khóa cụ thể.

Dòng **import java.util.Arrays** không được sử dụng trong ví dụ và có thể bỏ khi đưa vào dự án thật; nó không ảnh hưởng kết quả biên dịch/chạy.

## 8. Đọc kết quả test: false không phải mọi loại lỗi

**Signature.verify(...) == false** có nghĩa chữ ký **không hợp lệ theo dữ liệu, khóa, thuật toán và tham số đã dùng trong phép xác minh cụ thể**. Nó không phân biệt giúp bạn sai ở context, message, prehash hay key.

| Tình huống | Điều nên ghi nhận |
| --- | --- |
| Khác context, mode hoặc thông điệp nhưng chữ ký có định dạng hợp lệ | **false** trong bộ test |
| Chữ ký bị thay một bit | **false** trong ví dụ; có thể có ngoại lệ với dữ liệu chữ ký sai định dạng |
| Khóa sai loại hoặc không tương thích đường cong | **InvalidKeyException** có thể xuất hiện tại initSign/initVerify |
| Không hỗ trợ tham số EdDSA ở provider | **InvalidAlgorithmParameterException** có thể xuất hiện tại setParameter |
| Lỗi cấu trúc chữ ký hoặc trạng thái engine | **SignatureException** có thể xuất hiện |
| Context dài hơn 255 byte | **InvalidParameterException** khi tạo EdDSAParameterSpec |
| context=null trong constructor hai tham số | **NullPointerException** |
| Provider không có Ed25519 hoặc Ed448 | **NoSuchAlgorithmException** khi getInstance |

Không bắt mọi exception rồi trả false mà không ghi nguyên nhân vào hệ thống quan sát. **Lỗi cấu hình, lỗi hỗ trợ provider và chữ ký không đúng là ba vấn đề khác nhau**.

## 9. Kiểm soát message bytes và domain separation

Để các test có ý nghĩa, bảo đảm thông điệp ở hai phía có **cùng dãy byte chính xác**. Nếu một bên dùng UTF-8 còn bên kia dùng charset khác, hoặc một bên đổi LF thành CRLF, có thể làm verify=false ngay cả khi context và mode giống nhau.

Một quy trình tốt:

1. Chọn biểu diễn thông điệp bất biến, ví dụ raw UTF-8 của một snapshot với schema ổn định.
2. Nếu cần normalize Unicode hoặc canonicalize JSON, quy định **phiên bản thuật toán canonicalization** rồi thực hiện giống nhau trước ký và trước xác minh.
3. Chọn context bằng **byte[] theo hợp đồng**; không lấy từ một chuỗi chưa xác thực không có giới hạn.
4. Chọn prehash mode rõ ràng; tránh dựa vào mặc định không được văn bản giao thức quy định.
5. Thực hiện Signature.update với chính message bytes đã chọn; không tự thêm hoặc bỏ trường.
6. Sau khi verify, kiểm tra ngữ cảnh nghiệp vụ: người gửi có quyền gì, thông điệp còn hạn, có bị replay không.

### Context khác với nối tiền tố vào message

Giả sử dùng Ed25519 thuần để ký chuỗi được ghép:

~~~java
byte[] payload = ("orders-v1:" + message)
        .getBytes(StandardCharsets.UTF_8);
~~~

Đây là **cách ghép thông điệp ở tầng ứng dụng**, không tương đương Ed25519ctx với context "orders-v1". Context của Ed25519ctx được đưa vào công thức mật mã bằng quy tắc **RFC 8032**, không phải thay bằng một phép nối chuỗi tùy ý. Hai phía phải thống nhất đúng một cách.

**Context không tự chống replay.** Nếu cần bảo vệ endpoint/audience/timestamp/nonce, đưa các yếu tố đó vào thông điệp được ký theo schema không nhập nhằng và kiểm tra ở tầng ứng dụng.

## 10. Prehash không giống chia nhỏ Signature.update

Bộ test cần tránh một cách hiểu sai phổ biến: gọi update thành nhiều chunk **không tự làm chuyển sang Ed25519ph**.

- **prehash=true** là một **chế độ EdDSA được chuẩn hóa**.
- Gọi update(byte[]) một lần hay update(byte[], offset, len) nhiều lần vẫn xử lý tổng dãy byte được cập nhật, **không đổi prehash mode**.
- Nếu tự gọi MessageDigest lên thông điệp rồi đưa digest bytes vào Signature.update, bạn đã đổi thông điệp được ký, trừ khi giao thức đặc tả tường minh bước đó.
- Không bật prehash=true chỉ vì dữ liệu lớn hoặc nghĩ rằng nó “luôn nhanh hơn”; khả năng tương thích giao thức là ưu tiên.

Trong hệ thống liên thông Java với thư viện khác, kiểm tra cả tên biến thể **Ed25519ph**, **Ed25519ctx**, **Ed448ph** và quy tắc context. Không cho rằng tất cả thư viện chỉ có tham số boolean prehash như Java.

## 11. Mở rộng bộ test cho ứng dụng thật

Ngoài ví dụ chạy độc lập, một bộ kiểm thử tích hợp nên có:

- **Known-answer test từ RFC 8032:** dùng public/private key và signature test vector đã công bố, cho các chế độ thực sự được hệ thống dùng.
- **Đối chứng dương**: ký/xác minh thành công cùng thông điệp, key, mode và context.
- **Sai context**: khác một byte; khác độ dài; khác Unicode encoding; có và không có context.
- **Sai mode**: Ed25519ctx vs Ed25519ph; Ed448 vs Ed448ph; các kiểu absent/empty.
- **Sai thông điệp**: đổi một byte, đổi newline hoặc đổi serialization, nếu đầu vào văn bản được giao thức định nghĩa.
- **Sai chữ ký**: đổi một bit, sai chiều dài, base64 decode sai; xử lý cả false và exception.
- **Sai khóa**: đúng thuật toán nhưng public key khác; khác thuật toán/đường cong và xử lý InvalidKeyException.
- **Ranh giới tham số**: 0, 1, 255 và 256 byte context; null.
- **Khả năng tương tác**: cùng message, key, mode, context trên các provider/libraries được hỗ trợ; đối chiếu test vectors của RFC.
- **Giới hạn vận hành**: không log bí mật, khóa phải được xác thực, có bảo vệ chống replay và quản lý vòng đời khóa.

Khi cần phân biệt kết quả, lưu **tên case, curve, prehash, context ID, message length và loại lỗi**; không in key private, seed hay payload nhạy cảm. Đừng dựa trên việc một chữ ký bị từ chối để khẳng định nguyên nhân duy nhất khi chưa kiểm tra thông số đầu vào.

## 12. Lỗi thường gặp

1. **Chỉ test thay message, không test context/mode.** Dễ bỏ sót cấu hình EdDSA không tương thích.
2. **Cho rằng EdDSA chỉ có Ed25519 và Ed448 thuần.** RFC 8032 có biến thể context/prehash.
3. **Bật prehash ở một bên rồi giữ chế độ cũ ở bên kia.** Chữ ký không thể xác minh theo biến thể khác.
4. **Cho rằng context rỗng đồng nghĩa không context với Ed25519.** Ed25519 thuần khác Ed25519ctx context rỗng.
5. **Đo độ dài context theo ký tự thay vì byte.** Giới hạn là 255 byte.
6. **Đưa null vào constructor hai tham số để biểu thị absent.** API ném NullPointerException; dùng constructor một tham số.
7. **Tự hash message rồi gọi EdDSAParameterSpec(true).** Đây là ký một message khác, không thay thế cơ chế prehash của RFC.
8. **Tự ghép context vào message rồi mong tương thích Ed25519ctx.** Hai cách dùng domain separation không giống nhau.
9. **Đánh đồng verify(false) và InvalidKeyException.** Bất tương thích khóa là lỗi cấu hình riêng.
10. **Bỏ test true đối chứng.** Nếu mọi phép verify đều false, không biết hệ thống đã hoạt động đúng bao giờ.
11. **Dùng charset mặc định tạo context.** Bên ký và xác minh có thể nhận byte khác nhau.
12. **Tái dùng Signature có trạng thái ở nhiều request/thread.** Dễ trộn dữ liệu và cấu hình.
13. **Cho rằng có context là không cần xác thực public key.** Một chữ ký với public key không tin cậy không chứng minh danh tính.
14. **Xác minh thành công rồi bỏ kiểm tra replay/audience.** Chữ ký không tự ngăn phát lại.
15. **Không tách lỗi của provider khi tích hợp đa nền tảng.** Một số provider không hỗ trợ mọi chế độ; không được ngầm đổi sang mode khác.

## 13. Tự kiểm tra

**Câu 1.** Ký bằng Ed25519ctx, context orders-v1 và message M, xác minh cùng khóa và M nhưng context invoices-v1 thì sao?  
**Đáp án:** Không xác minh được, vì context bytes khác.

**Câu 2.** Chữ ký Ed25519ph có thể xác minh bằng Ed25519ctx cùng context và message không?  
**Đáp án:** Không, prehash mode khác.

**Câu 3.** Ed25519 prehash=false với context absent khác explicit byte[0] không?  
**Đáp án:** Có. Absent là Ed25519 thuần; explicit byte[0] là Ed25519ctx context rỗng.

**Câu 4.** Ed448 prehash=false với context absent và explicit byte[0] khác nhau không?  
**Đáp án:** Không; hai cấu hình dùng context rỗng hiệu dụng.

**Câu 5.** Khi tạo EdDSAParameterSpec với 256 byte context, lỗi nào xảy ra?  
**Đáp án:** InvalidParameterException.

**Câu 6.** Cùng mode/context nhưng sửa một byte thông điệp, chữ ký ban đầu có xác minh được không?  
**Đáp án:** Không, vì chữ ký xác nhận dãy byte ban đầu.

**Câu 7.** Nếu verify=false, có chắc sai message?  
**Đáp án:** Không. Có thể sai context, mode, key hoặc signature; cần kiểm tra từng yếu tố.

**Câu 8.** prehash=true có yêu cầu ứng dụng tự tính SHA-512 trước Signature.update không?  
**Đáp án:** Không. Provider thực hiện prehash theo biến thể EdDSA và RFC 8032.

## 14. Ghi nhớ

**Chữ ký EdDSA chỉ xác minh được khi thông tin mật mã và bytes thông điệp khớp.** Với Java, **EdDSAParameterSpec** điều khiển **prehash** và **context**; dùng constructor tương ứng chính xác và không đánh đồng context absent với context rỗng ở Ed25519. Một bộ test tốt phải có **đối chứng true**, các case **khác mode**, **khác context**, **sai thông điệp**, **sai chữ ký** và kiểm tra **lỗi API riêng biệt**.

## Tài liệu tham khảo chính thức

- Oracle, **EdDSAParameterSpec**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html
- Oracle, **Signature**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- Oracle, **KeyPairGenerator**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html
- IETF, **RFC 8032 – Edwards-Curve Digital Signature Algorithm (EdDSA)**: https://www.rfc-editor.org/rfc/rfc8032
