# Chế độ thông thường, prehash và context của EdDSA trong Java 15+

## 1. Mục tiêu và phạm vi

EdDSA (*Edwards-Curve Digital Signature Algorithm*) là họ thuật toán **chữ ký số** trên các đường cong Edwards. Java 15 đưa EdDSA vào Java Cryptography Architecture (JCA) theo RFC 8032; Java 17+ tiếp tục cung cấp các API chính thức như `Signature`, `KeyPairGenerator` và `java.security.spec.EdDSAParameterSpec`.

Bài này phân biệt ba khái niệm dễ lẫn:

- **Chế độ thông thường (pure):** chữ ký được tạo trực tiếp theo quy trình EdDSA của biến thể đang chọn, không bật *prehash*.
- **Prehash (ph):** thông điệp được băm theo cơ chế được định nghĩa **bên trong thuật toán EdDSA ph**, sau đó ký theo biến thể prehash với cơ chế tách miền riêng.
- **Context:** một mảng byte tùy chọn, do giao thức quyết định và được gắn vào phép ký/xác minh để **tách miền sử dụng (domain separation)**.

`EdDSAParameterSpec` cho phép cấu hình hai thông tin: `prehash` (boolean) và `context` (byte array có thể vắng mặt). Kết hợp với tên thuật toán Ed25519/Ed448, các thông tin này chọn ra một trong những biến thể RFC 8032.

**Điểm trọng tâm:** signer và verifier phải thống nhất **cùng thuật toán, khóa tương ứng, thông điệp, chế độ prehash và context**. Đổi context hoặc chế độ có thể khiến `Signature.verify(...)` trả `false` dù dùng đúng public key.

Các tính năng này vẫn được hỗ trợ trong JDK hiện đại; bài không dùng các API legacy hoặc tùy chọn preview.

## 2. Năm biến thể trong RFC 8032

RFC 8032 mô tả các biến thể `Ed25519`, `Ed25519ctx`, `Ed25519ph`, `Ed448` và `Ed448ph`. Chúng không phải năm kiểu `KeyPairGenerator` hoàn toàn tách biệt: khóa được tạo trên đường cong **Ed25519** hoặc **Ed448**, còn kiểu ký được chọn bằng **thuật toán Signature và EdDSAParameterSpec**.

| Biến thể RFC 8032 | Đường cong | Prehash? | Context | Ý nghĩa |
| --- | --- | --- | --- | --- |
| **Ed25519** (pure) | Ed25519 | `false` | **Không cung cấp** | Dạng ký Ed25519 thông thường |
| **Ed25519ctx** | Ed25519 | `false` | **Có cung cấp** | Ed25519 có tách miền bằng context |
| **Ed25519ph** | Ed25519 | `true` | Không hoặc có | Ed25519 dùng bước prehash SHA-512 theo RFC 8032 |
| **Ed448** (pure) | Ed448 | `false` | Có thể rỗng hoặc có nội dung | Ed448 có cơ chế context ngay trong định nghĩa |
| **Ed448ph** | Ed448 | `true` | Có thể rỗng hoặc có nội dung | Ed448 dùng prehash SHAKE256 theo RFC 8032 |

Các tên `"Ed25519"` và `"Ed448"` là tên thuật toán JCA dùng trong `Signature.getInstance(...)`. **Không nên suy đoán rằng `Signature.getInstance("Ed25519ph")` là tên portable**: API chuẩn dùng `Signature.getInstance("Ed25519")` rồi `setParameter(new EdDSAParameterSpec(true))` để yêu cầu prehash.

### 2.1. Pure Ed25519 khác Ed25519ctx ngay cả khi context dài 0 byte

Trên Ed25519, Java phân biệt:

```java
EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
EdDSAParameterSpec contextProvidedButEmpty =
        new EdDSAParameterSpec(false, new byte[0]);
```

- Constructor một tham số **không cung cấp context** (`getContext().isEmpty()`).
- Constructor hai tham số **có cung cấp context**, kể cả `new byte[0]` (`getContext().isPresent()` là `true`).
- Với Ed25519 và provider JDK được kiểm chứng, chữ ký pure Ed25519 và Ed25519ctx với context rỗng **khác nhau**, do quy tắc domain separation khác nhau.

RFC 8032 khuyên **không dùng context rỗng cho Ed25519ctx** khi có thể; nếu cần domain separation, hãy đặt context cụ thể, có ý nghĩa và ổn định. Đặc biệt, **đừng biến `null`/vắng mặt thành mảng rỗng một cách tự động** trong code cấu hình Ed25519.

Với Ed448, context là một phần của phép ký chuẩn ngay cả khi rỗng; trên JDK được kiểm chứng, `new EdDSAParameterSpec(false)` và `new EdDSAParameterSpec(false, new byte[0])` cho chữ ký giống nhau với cùng khóa/thông điệp. Vẫn nên chọn rõ chính sách context và kiểm thử tương thích với hệ thống đối tác.

## 3. `EdDSAParameterSpec`: API chính thức từ Java 15

Tên đầy đủ: `java.security.spec.EdDSAParameterSpec`. Lớp này triển khai `AlgorithmParameterSpec` và có hai constructor chính:

```java
new EdDSAParameterSpec(boolean prehash);
new EdDSAParameterSpec(boolean prehash, byte[] context);
```

Các phương thức đọc cấu hình:

```java
boolean isPrehash();
Optional<byte[]> getContext();
```

| Cấu hình | Ý nghĩa |
| --- | --- |
| `new EdDSAParameterSpec(false)` | Không dùng prehash; context **vắng mặt** |
| `new EdDSAParameterSpec(true)` | Dùng prehash; context **vắng mặt** |
| `new EdDSAParameterSpec(false, context)` | Không dùng prehash; **có context** |
| `new EdDSAParameterSpec(true, context)` | Dùng prehash; **có context** |
| `spec.isPrehash()` | Kiểm tra cờ prehash |
| `spec.getContext()` | `Optional<byte[]>`, có giá trị khi context đã được cung cấp |

**Độ dài context tối đa 255 byte**, không phải 255 ký tự Unicode. Constructor có context ném `NullPointerException` nếu mảng `null` và `InvalidParameterException` nếu quá 255 byte.

```java
byte[] context = "order-v1".getBytes(java.nio.charset.StandardCharsets.UTF_8);
EdDSAParameterSpec p = new EdDSAParameterSpec(false, context);

System.out.println(p.isPrehash());            // false
System.out.println(p.getContext().isPresent()); // true
```

Đây là snippet cần đặt trong một method; chương trình đầy đủ có ở phần 7. Constructor **sao chép dữ liệu context**, và `getContext()` trả bản sao khi context có mặt, nhằm tránh thay đổi cấu hình ngầm qua tham chiếu mảng bên ngoài. Tuy nhiên, hãy thiết kế context như **giá trị cấu hình bất biến về mặt nghiệp vụ**.

## 4. Chế độ pure: khi nào nên dùng?

Với lựa chọn thường gặp là **Ed25519 thuần túy**:

```java
Signature signature = Signature.getInstance("Ed25519");
signature.initSign(privateKey);
signature.setParameter(new EdDSAParameterSpec(false));
signature.update(message);
byte[] signed = signature.sign();
```

Đoạn này là minh họa nằm trong method với các biến đã định nghĩa và xử lý `GeneralSecurityException`.

Nếu dùng provider phù hợp, chữ ký Ed25519 thông thường cũng là chế độ mặc định khi không truyền `EdDSAParameterSpec`. Tuy vậy, **khai báo tường minh** ở những nơi cần tuân thủ giao thức và kiểm thử phiên bản sẽ giúp code nói rõ ý định.

Chế độ pure **không có nghĩa là thuật toán không dùng hàm băm**: Ed25519 trong RFC 8032 vẫn sử dụng SHA-512 nội bộ khi tạo chữ ký. “Không prehash” chỉ có nghĩa thông điệp **không được biến đổi bởi bước PH(M) riêng của chế độ ph** trước khi đi vào quy trình EdDSA.

Đừng đổi tên `"Ed25519"` sang `"X25519"` khi gặp lỗi: X25519 thuộc **key agreement**, không phải chữ ký EdDSA.

## 5. Chế độ prehash: `Ed25519ph` và `Ed448ph`

Prehash là biến thể **được chuẩn hóa riêng**, không chỉ là việc ứng dụng tự băm thông điệp rồi đem digest đi ký bằng pure EdDSA.

- **Ed25519ph:** dùng bước prehash **SHA-512(M)** tạo digest 64 byte và có cơ chế domain separation của Ed25519ph.
- **Ed448ph:** dùng bước prehash **SHAKE256(M, 64 byte)** và cơ chế domain separation của Ed448ph.

Cách yêu cầu Java thực hiện prehash đúng chuẩn:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.setParameter(new EdDSAParameterSpec(true));
signer.update(message); // Truyền nguyên message, KHÔNG tự SHA-512 trước.
byte[] signatureBytes = signer.sign();
```

**Không làm như sau nếu giao thức yêu cầu Ed25519ph:**

```java
// Sai về mặt tương đương thuật toán Ed25519ph:
byte[] digest = java.security.MessageDigest.getInstance("SHA-512")
        .digest(message);
Signature pureSigner = Signature.getInstance("Ed25519");
pureSigner.initSign(privateKey);
pureSigner.update(digest);
byte[] notEd25519ph = pureSigner.sign();
```

Đoạn thứ hai dùng pure Ed25519 để ký **digest**, **không tạo cùng chữ ký** với Ed25519ph: domain separation và quy trình ph khác nhau. Đây chỉ là đoạn phản ví dụ, không nên áp dụng trong sản phẩm.

**Khi nào nên chọn prehash?** Khi giao thức tương tác hoặc đặc tả hệ thống **yêu cầu đúng biến thể `ph`**. Không tự coi prehash là “nâng cấp bảo mật” bắt buộc, và không bật chỉ vì thông điệp dài. Nếu cả hai bên đang dùng pure Ed25519 và không có yêu cầu tương tác mới, việc bật `prehash=true` sẽ tạo chữ ký không tương thích.

## 6. Context: domain separation nhưng không phải bí mật

Context là mảng byte được đưa vào cơ chế ký/xác minh để tránh việc một chữ ký cho **một mục đích hoặc miền sử dụng** có thể bị nhầm sang mục đích khác.

Ví dụ: cùng cặp khóa được một hệ thống dùng ở hai luồng `invoice-v1` và `approval-v1`. Thay vì chỉ ký cùng một chuỗi payload, giao thức có thể yêu cầu domain separation:

```java
byte[] context = "invoice-v1"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

EdDSAParameterSpec invoiceMode = new EdDSAParameterSpec(false, context);
```

Người ký và người xác minh phải sử dụng **chính xác cùng dãy byte context**, kể cả chữ hoa/thường, ký tự Unicode và encoding.

**Context không phải:**

- Mật khẩu, secret key hay nonce được giữ bí mật.
- Giấy chứng nhận danh tính của người ký.
- Thay thế cho việc xác thực public key, phân quyền, chống phát lại hoặc quản lý phiên bản giao thức.
- Một trường metadata tự động đi kèm chữ ký: chữ ký EdDSA **không tự chứa context** để bên nhận có thể đoán lại.

Vì vậy, ứng dụng cần **quy định context trong giao thức hoặc truyền nó qua metadata đã được bảo vệ thích hợp**; nếu người xác minh chọn nhầm context, chữ ký sẽ không hợp lệ. Domain separation hữu ích nhưng không thay cho chính sách dùng khóa riêng biệt nếu có yêu cầu cô lập mạnh hơn.

### 6.1. Giới hạn 255 byte và UTF-8

Ví dụ dùng chuỗi Unicode làm context:

```java
byte[] context = "tài liệu-v1"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

Số byte UTF-8 có thể lớn hơn số ký tự; kiểm tra `context.length <= 255`, không chỉ `String.length()`. Tránh để hai hệ thống chuyển đổi encoding khác nhau, chuẩn hóa Unicode khác nhau hoặc tự cắt context khi vượt giới hạn.

### 6.2. Vì sao `getContext().isEmpty()` khác context dài 0?

`EdDSAParameterSpec.getContext()` là `Optional<byte[]>`. `Optional.empty()` nghĩa **không cung cấp context**; `Optional.of(new byte[0])` nghĩa **đã cung cấp một context dài 0 byte**. Sự phân biệt này đặc biệt ảnh hưởng Ed25519 pure so với Ed25519ctx.

Đừng dùng `spec.getContext().orElse(new byte[0])` để quyết định pure/ctx: nó làm mất thông tin “vắng mặt” mà API chủ động bảo tồn.

## 7. Chương trình Java 17+ chạy được: so sánh pure, context và prehash

Ví dụ dùng **cùng cặp khóa** cho ba biến thể của từng đường cong để thấy rõ rằng việc thay đổi tham số đủ làm thay đổi chữ ký. Chương trình không in private key hoặc bytes chữ ký ngẫu nhiên theo khóa; chỉ in các boolean có thể kiểm tra chính xác.

Tạo file **`EdDSAParametersDemo.java`**:

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
import java.util.Arrays;

public class EdDSAParametersDemo {
    private static final byte[] MESSAGE = "signed message"
            .getBytes(StandardCharsets.UTF_8);
    private static final byte[] CONTEXT = "document-v1"
            .getBytes(StandardCharsets.UTF_8);

    static byte[] sign(String algorithm, PrivateKey privateKey,
            EdDSAParameterSpec params) throws GeneralSecurityException {
        Signature signature = Signature.getInstance(algorithm);
        signature.initSign(privateKey);
        signature.setParameter(params);
        signature.update(MESSAGE);
        return signature.sign();
    }

    static boolean verify(String algorithm, PublicKey publicKey,
            EdDSAParameterSpec params, byte[] signatureBytes)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance(algorithm);
        signature.initVerify(publicKey);
        signature.setParameter(params);
        signature.update(MESSAGE);
        return signature.verify(signatureBytes);
    }

    static void exercise(String algorithm) throws GeneralSecurityException {
        KeyPair keys = KeyPairGenerator.getInstance(algorithm).generateKeyPair();
        EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
        EdDSAParameterSpec context = new EdDSAParameterSpec(false, CONTEXT);
        EdDSAParameterSpec prehash = new EdDSAParameterSpec(true, CONTEXT);

        byte[] pureSig = sign(algorithm, keys.getPrivate(), pure);
        byte[] contextSig = sign(algorithm, keys.getPrivate(), context);
        byte[] prehashSig = sign(algorithm, keys.getPrivate(), prehash);

        System.out.println(algorithm + ": pure="
                + verify(algorithm, keys.getPublic(), pure, pureSig)
                + " ctx="
                + verify(algorithm, keys.getPublic(), context, contextSig)
                + " ph="
                + verify(algorithm, keys.getPublic(), prehash, prehashSig));

        System.out.println(algorithm + ": mismatchContext="
                + verify(algorithm, keys.getPublic(),
                    new EdDSAParameterSpec(false,
                        "other".getBytes(StandardCharsets.UTF_8)),
                    contextSig)
                + " mismatchPrehash="
                + verify(algorithm, keys.getPublic(), context, prehashSig)
                + " pureEqualsContext="
                + Arrays.equals(pureSig, contextSig));
    }

    public static void main(String[] args) throws GeneralSecurityException {
        exercise("Ed25519");
        exercise("Ed448");

        EdDSAParameterSpec absent = new EdDSAParameterSpec(false);
        EdDSAParameterSpec empty =
                new EdDSAParameterSpec(false, new byte[0]);
        System.out.println("contextAbsent=" + absent.getContext().isEmpty());
        System.out.println("contextPresentEmpty="
                + empty.getContext().isPresent());
        System.out.println("prehashFlag="
                + new EdDSAParameterSpec(true).isPrehash());

        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("oversize=accepted");
        } catch (InvalidParameterException ex) {
            System.out.println("oversize=rejected");
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên (sử dụng `--release 17` để kiểm tra mức ngôn ngữ và API):

```bash
javac --release 17 EdDSAParametersDemo.java
java EdDSAParametersDemo
```

**Stdout chính xác**, đã xác minh trên JDK 24 với mã nguồn biên dịch bằng `--release 17`:

```text
Ed25519: pure=true ctx=true ph=true
Ed25519: mismatchContext=false mismatchPrehash=false pureEqualsContext=false
Ed448: pure=true ctx=true ph=true
Ed448: mismatchContext=false mismatchPrehash=false pureEqualsContext=false
contextAbsent=true
contextPresentEmpty=true
prehashFlag=true
oversize=rejected
```

### 7.1. Giải thích từng dòng output

1. **`pure=true ctx=true ph=true`**: khi signer và verifier dùng cùng curve, public/private key tương ứng, cùng thông điệp, cờ prehash và context, cả ba chế độ đều ký/xác minh được.
2. **`mismatchContext=false`**: cùng chữ ký và cùng key nhưng đổi context từ `document-v1` thành `other`, nên chữ ký không hợp lệ dưới miền sử dụng mới.
3. **`mismatchPrehash=false`**: chữ ký tạo bằng `prehash=true` không xác minh đúng khi verifier cấu hình `prehash=false`, kể cả context không thay đổi.
4. **`pureEqualsContext=false`**: vì domain separation, chữ ký pure và có context khác nhau với cùng key/message.
5. **`contextAbsent=true`**: `EdDSAParameterSpec(false)` không có context.
6. **`contextPresentEmpty=true`**: `EdDSAParameterSpec(false, new byte[0])` vẫn ghi nhận context *được cung cấp*.
7. **`prehashFlag=true`**: `EdDSAParameterSpec(true)` bật prehash.
8. **`oversize=rejected`**: constructor từ chối context 256 byte vì giới hạn là 255 byte.

Ví dụ này được kiểm chứng với provider EdDSA tích hợp trong JDK 24. Một số runtime hoặc security providers có thể không cung cấp đầy đủ Ed25519/Ed448 hoặc các mode; trong trường hợp đó cần kiểm tra khả năng provider, không im lặng đổi mode của giao thức.

## 8. Quy trình đúng khi dùng Signature.setParameter

Các bước rõ ràng, ít lỗi cho bên ký:

```text
1. KeyPairGenerator.getInstance("Ed25519") -> sinh KeyPair
2. Signature.getInstance("Ed25519") -> tạo engine ký
3. initSign(privateKey) -> chọn khóa riêng
4. setParameter(EdDSAParameterSpec) -> xác định mode/context
5. update(messageBytes) -> đưa nguyên thông điệp vào engine
6. sign() -> nhận chữ ký
```

Bên xác minh dùng:

```text
1. Signature.getInstance("Ed25519")
2. initVerify(publicKey)
3. setParameter(EdDSAParameterSpec khớp hoàn toàn với bên ký)
4. update(cùng messageBytes)
5. verify(signatureBytes) -> boolean
```

**Gọi `setParameter(...)` trước `update(...)`**, khi engine chưa xử lý byte thông điệp nào. Ở một số provider, đổi mode/context sau khi đã cập nhật dữ liệu có thể bị từ chối hoặc tạo hành vi không phù hợp hợp đồng. Ví dụ ở trên luôn tạo một `Signature` riêng cho mỗi phép ký hoặc xác minh, tránh chia sẻ state giữa các operation.

`Signature.setParameter(AlgorithmParameterSpec)` là overload hiện hành; **không** dùng overload `Signature.setParameter(String, Object)` đã deprecated. Sai tham số hoặc provider không hỗ trợ có thể dẫn tới `InvalidAlgorithmParameterException` (thuộc `GeneralSecurityException`).

`Signature` là engine có trạng thái, không nên dùng cùng một instance đồng thời giữa nhiều luồng. Nếu ký nhiều thông điệp có mode/context khác nhau, tạo các instance phù hợp hoặc đảm bảo khởi tạo lại state đúng cách.

## 9. Bảng quyết định: chọn chế độ như thế nào?

| Nhu cầu | Lựa chọn thích hợp | Lý do |
| --- | --- | --- |
| Giao thức yêu cầu Ed25519 thuần | `Signature("Ed25519")` + `EdDSAParameterSpec(false)` hoặc mặc định được xác nhận | Tương thích pure Ed25519 |
| Muốn tách miền bằng context trên Ed25519 | `EdDSAParameterSpec(false, contextBytes)` | Chọn Ed25519ctx; cùng context ở cả hai phía |
| Giao thức yêu cầu Ed25519ph | `EdDSAParameterSpec(true)` hoặc `(true, context)` | Prehash chuẩn cùng domain separation |
| Giao thức yêu cầu Ed448 | `Signature("Ed448")` + `EdDSAParameterSpec(false)` | Ed448 chuẩn, context mặc định rỗng |
| Giao thức yêu cầu Ed448 với context | `EdDSAParameterSpec(false, contextBytes)` | Context được đưa vào ký/xác minh |
| Giao thức yêu cầu Ed448ph | `EdDSAParameterSpec(true)` hoặc `(true, context)` | Prehash SHAKE256 theo RFC 8032 |
| Chỉ muốn tạo khóa EdDSA | `KeyPairGenerator`, `NamedParameterSpec` nếu cần | Tham số tạo khóa **khác** tham số chế độ ký |

**Đừng tự chuyển chế độ khi chữ ký không xác minh được.** Trước tiên xác định protocol specification và so sánh key, message bytes, context bytes, prehash flag.

## 10. Phân biệt EdDSAParameterSpec với NamedParameterSpec

Hai lớp đều là `AlgorithmParameterSpec` nhưng phục vụ **mục đích khác nhau**:

| Lớp | Dùng ở đâu? | Quy định gì? |
| --- | --- | --- |
| `NamedParameterSpec.ED25519` hoặc `ED448` | `KeyPairGenerator.initialize(...)` | Chọn **đường cong của cặp khóa** |
| `EdDSAParameterSpec` | `Signature.setParameter(...)` | Chọn **prehash và context của phép ký/xác minh** |

Ví dụ minh họa khai báo đường cong:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(java.security.spec.NamedParameterSpec.ED25519);
KeyPair keys = generator.generateKeyPair();
```

Sau đó khi ký có thể chọn `EdDSAParameterSpec(false)`, `EdDSAParameterSpec(false, context)` hoặc `EdDSAParameterSpec(true, context)` tùy giao thức. **Không thể dùng `EdDSAParameterSpec` để thay thế tham số tạo cặp khóa** hoặc dùng `NamedParameterSpec` như một cách bật prehash.

Đây là đoạn mã minh họa, cần đặt trong method và xử lý `GeneralSecurityException`; ví dụ phần 7 là chương trình đầy đủ.

## 11. Tình huống liên hệ và khả năng tương tác

### 11.1. Bên ký không gửi thông tin mode/context

Chữ ký EdDSA thông thường là một mảng byte chứa giá trị chữ ký, **không bao gồm tên mode, cờ prehash hoặc context để tự giải mã**. Nếu bên nhận chỉ có public key và bytes chữ ký nhưng không biết mode, việc xác minh có thể thất bại dù khóa đúng.

**Giải pháp:** định nghĩa rõ mode/context ngay trong đặc tả giao thức, tên profile hoặc metadata đáng tin cậy; không đoán dựa vào độ dài chữ ký (Ed25519 và Ed25519ph đều có chữ ký 64 byte).

### 11.2. Dùng cùng text context nhưng khác encoding

Bên ký dùng UTF-8 của `"hồ sơ-v1"`, bên nhận dùng một encoding khác. Dù chữ nhìn giống nhau, các byte context khác nhau sẽ cho kết quả không tương thích.

**Giải pháp:** quy định encoding (thường UTF-8), cách chuẩn hóa văn bản nếu cần, và giới hạn 255 byte; gửi định danh context cố định thay vì chuỗi tùy biến tự do nếu ứng dụng có nhiều thành phần.

### 11.3. Giả định prehash là SHA-512 cho mọi đường cong

Điều này sai: Ed25519ph sử dụng SHA-512(M), còn Ed448ph sử dụng **SHAKE256(M, 64 byte)** theo RFC 8032. Bật `prehash=true` cho `Signature.getInstance("Ed448")` yêu cầu provider thực hiện đúng Ed448ph; đừng tự tạo digest SHA-512 cho cả hai.

### 11.4. Đổi từ Ed25519 pure sang Ed25519ctx mà không cập nhật verifier

Nếu bên ký dùng context mới còn verifier vẫn dùng pure, chữ ký sẽ thất bại. Đây là **thay đổi giao thức**, cần triển khai có versioning rõ ràng, đồng bộ bên ký/xác minh và test vectors tương ứng.

### 11.5. Tưởng context là metadata bảo mật bí mật

Context **không phải secret**; nó làm rõ miền sử dụng và tăng khả năng tách các hoạt động ký khác nhau, nhưng không tự xác thực khóa công khai, ngăn replay theo thời gian hoặc ràng buộc mọi metadata nghiệp vụ. Nếu cần xác minh những trường này, nội dung được ký phải được thiết kế phù hợp.

## 12. Lỗi thường gặp và xử lý

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Provider không hỗ trợ `Ed25519`/`Ed448` | Kiểm tra JDK/provider và thuật toán đã cấu hình |
| `InvalidAlgorithmParameterException` tại `setParameter` | Provider không hỗ trợ mode/context hoặc tham số không phù hợp | Dùng `EdDSAParameterSpec` đúng và provider hỗ trợ RFC 8032 |
| `InvalidParameterException` tại constructor | Context vượt **255 byte** | Định nghĩa context ngắn, kiểm tra `context.length` |
| `NullPointerException` tại constructor hai tham số | `context == null` | Dùng constructor **một** tham số khi muốn vắng context |
| `SignatureException` | Sai trạng thái engine hoặc dữ liệu chữ ký không hợp lệ về mặt kỹ thuật | Kiểm tra `initSign`/`initVerify`, `setParameter`, `update`, `sign`/`verify` |
| `verify(...) == false` | Khóa, thông điệp, prehash hoặc context không khớp | So sánh đúng toàn bộ byte và các tham số |
| Ed25519ctx không tương thích với Ed25519 pure | Context đã được cung cấp, kể cả dài 0 | Giữ đúng distinction “absent” và “empty” |
| Không khớp chữ ký khi tự băm trước | Băm ngoài và ký bằng pure không tương đương chế độ ph | Đưa **nguyên message** vào `update` khi bật `prehash=true` |

Khi xử lý `verify(...) == false`, hãy xem đó là kết quả xác minh không hợp lệ theo tham số hiện tại, **không phải cơ hội thử qua hàng loạt mode để xem mode nào “qua”** nếu giao thức đã quy định cụ thể.

## 13. Lưu ý an toàn khi dùng EdDSA trong sản phẩm

- **Bảo vệ private key:** lưu trong keystore/KMS/HSM theo chính sách; không ghi private seed hoặc khóa dạng PKCS#8 vào log, source code hay test output.
- **Xác thực nguồn public key:** một chữ ký hợp lệ chỉ chứng minh rằng nó khớp với public key được cung cấp, không tự chứng minh ai là người sở hữu key.
- **Không tự chế prehash:** provider JCA triển khai quy tắc EdDSA tương ứng; không tự nối context vào message rồi coi là Ed25519ctx.
- **Khớp tham số trên cả hai phía:** curve, prehash flag, context bytes và bản tin phải giống nhau theo đặc tả.
- **Context chỉ là một thành phần của domain separation:** vẫn cần versioning, chống replay, phân quyền và canonicalization payload phù hợp hệ thống.
- **Tránh legacy APIs:** dùng `Signature.setParameter(AlgorithmParameterSpec)`; không dùng overload deprecated `setParameter(String, Object)`.
- **Kiểm thử liên thông:** khi Java phải làm việc với hệ thống viết bằng ngôn ngữ khác, dùng RFC 8032 test vectors để xác minh đúng biến thể; tránh suy luận từ tên thuật toán riêng của provider.

## 14. Checklist ôn tập

- Đã xác định đúng **Ed25519 hay Ed448**?
- Giao thức yêu cầu **pure, context hay prehash**?
- Với Ed25519, context là **vắng mặt** hay **mảng rỗng đã cung cấp**?
- Prehash do `EdDSAParameterSpec(true)` kích hoạt, hay ứng dụng đang tự hash sai cách?
- Context tính theo **byte**, có tối đa 255 byte, encoding và nội dung được thống nhất?
- `Signature.setParameter` được gọi trước khi `update`?
- Người xác minh có đúng public key, cùng message bytes, cờ prehash và context?
- Các unit test có bao gồm case sai context, sai mode và thay đổi message?
- Provider của runtime thực tế có hỗ trợ biến thể yêu cầu?
- Các khóa riêng và metadata nhạy cảm có được bảo vệ đúng cách?

**Kết luận:** `EdDSAParameterSpec` không chọn đường cong mà chọn **prehash và context cho hoạt động Signature**. Ed25519 pure, Ed25519ctx, Ed25519ph, Ed448 và Ed448ph khác nhau về định nghĩa chữ ký. Sự tương thích đòi hỏi **thống nhất chính xác mode và context ở cả bên ký lẫn bên xác minh**.

## Tài liệu tham khảo chính thức, còn hiệu lực

- [Oracle Java SE 26 — EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): constructor, `isPrehash()`, `getContext()`, giới hạn context, phân biệt absent/empty; *Since: 15*.
- [Oracle Java SE 26 — Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): `Signature.getInstance`, `initSign`, `initVerify`, `update`, `sign`, `verify`, `setParameter(AlgorithmParameterSpec)`.
- [Oracle Java SE 26 — JDK Providers / SunEC](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): hiện trạng provider hỗ trợ Ed25519/Ed448/EdDSA.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): các biến thể pure, context, Ed25519ph/Ed448ph, giới hạn context và test vectors.
- [OpenJDK JEP 339 — EdDSA](https://openjdk.org/jeps/339): EdDSA được chính thức đưa vào Java 15.

Bài học chỉ dùng API Java còn được hỗ trợ hiện nay, không dùng cơ chế cryptography đã lỗi thời hoặc đã trở thành legacy.