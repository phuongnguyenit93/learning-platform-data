# Định dạng thông điệp cần ký và quy tắc canonicalization trong Java

Khi tích hợp chữ ký số giữa các hệ thống Java, thuật toán ký chỉ nhận **một dãy byte**, không nhận một “đối tượng nghiệp vụ” theo nghĩa trừu tượng. Hai đối tượng có cùng thông tin nhưng được chuyển thành byte khác nhau sẽ có **signing input khác nhau**, dẫn tới chữ ký không khớp. Vì thế, cần thiết kế **định dạng thông điệp được ký** (*signed message representation*) và **quy tắc canonicalization** trước khi viết lời gọi `Signature.sign()`/`Signature.verify()`.

Chủ đề này thuộc nhóm **Tích hợp chữ ký**. Trong Java 15, EdDSA được đưa vào JDK theo JEP 339; với Java hiện đại, ứng dụng vẫn dùng JCA `java.security.Signature` để ký/xác minh, còn việc định nghĩa byte thông điệp là **trách nhiệm của giao thức và ứng dụng**. Bài học mô tả cách chọn giữa ký byte nguyên gốc, canonical serialization đã được chuẩn hóa và một định dạng nhị phân xác định; minh họa bằng Java 17+ với chữ ký Ed25519.

**Nguyên tắc phải nhớ:** không có “canonicalization mặc định” áp dụng cho mọi văn bản, JSON, XML, HTTP hay mọi giao thức chữ ký. **Chỉ có quy tắc đã được giao thức thống nhất** mới xác định chính xác điều gì được ký.

## 1. Vì sao cần quy tắc biểu diễn thông điệp?

Xét hai chuỗi JSON:

```json
{"orderId":"ord-42","amount":125000}
```

và:

```json
{"amount":125000,"orderId":"ord-42"}
```

Nhiều ứng dụng đọc hai chuỗi thành cùng một đối tượng nghiệp vụ. Tuy nhiên, các byte UTF-8 của chúng **không giống nhau** vì thứ tự thuộc tính khác. Nếu người ký ký chuỗi thứ nhất còn bên xác minh tự serialize thành chuỗi thứ hai, xác minh chữ ký **không thành công**.

Ngay cả khi thứ tự thuộc tính giống nhau, vẫn có thể có khác biệt:

- Khoảng trắng, dấu xuống dòng LF/CRLF hoặc newline cuối tài liệu.
- Chuỗi có ký tự Unicode khác dạng biểu diễn như `é` dựng sẵn so với `e` + combining accent.
- Kiểu biểu diễn số, ví dụ `1`, `1.0`, `1e0`, hoặc số nguyên quá phạm vi biểu diễn của parser phía kia.
- Dạng escape JSON `"é"` và `"\u00e9"`: giá trị sau parse có thể giống nhau nhưng byte JSON nguyên gốc khác.
- Thứ tự phần tử của một tập không có thứ tự, encoding ngày giờ, timezone và locale.
- BOM, charset và trường hợp decoder âm thầm thay thế ký tự lỗi.
- Các trường giao thức được thêm/bớt, hoặc một phía bỏ qua field không hiểu.

Vì vậy, cần xác định ký trên **raw payload bytes** hay ký trên **một biểu diễn chuẩn tắc được tạo lại** từ dữ liệu có cấu trúc. Hai cách là hợp lệ khi được đặc tả đầy đủ, nhưng **không được tự trộn**.

## 2. Ba hướng thiết kế thông điệp được ký

| Cách | Signing input | Phù hợp khi nào | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Raw bytes** | Chính những byte mà bên ký đã chọn, lưu/truyền nguyên vẹn | File, binary blob, HTTP body hoặc payload đã có encoding xác định | Mọi thay đổi byte đều làm chữ ký không khớp |
| **Canonical JSON/XML/HTTP theo chuẩn** | Byte được sinh ra bởi quy tắc chuẩn hóa đã thỏa thuận | Nhiều hệ thống/ngôn ngữ cần ký cùng cấu trúc dữ liệu | Phải dùng **đúng toàn bộ tiêu chuẩn**; không “gần đúng” |
| **Định dạng xác định cho một domain** | Byte do schema/codec ứng dụng sinh theo quy tắc chính xác | Giao thức nội bộ có kiểu dữ liệu và ràng buộc rõ ràng | Phải đặc tả version, kiểu, thứ tự, length, giá trị null, giới hạn và decoder |

Có thể hình dung:

```text
                        Dữ liệu nghiệp vụ / payload
                                    |
                          Hợp đồng phiên bản giao thức
                                    |
                  +-----------------+-----------------+
                  |                                   |
                  v                                   v
          Ký raw bytes                         Parse + validate
                  |                                   |
                  |                                   v
                  |                          Canonical serialization
                  |                                   |
                  +-----------------+-----------------+
                                    |
                                    v
                      byte[] ĐÚNG THEO HỢP ĐỒNG
                                    |
                                    v
                         Signature.update(bytes)
                                    |
                          sign() / verify(signature)
```

Để xác minh, cần **cùng thuật toán và public key đáng tin**. Nhưng kể cả khi những yếu tố ấy đều đúng, `verify` vẫn sẽ thất bại nếu signing input ở hai đầu khác nhau.

### Ví dụ ký raw bytes

```java
byte[] rawPayload = /* bytes đọc chính xác từ request/file */;
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(rawPayload);
byte[] signatureBytes = signer.sign();
```

Đây là **mã minh họa** cần các biến `rawPayload` và `privateKey` đã được chuẩn bị. Bên xác minh phải có đúng raw bytes được ký; **không parse rồi serialize lại**, không sửa whitespace hay Unicode nếu hợp đồng ký raw bytes.

### Ví dụ ký biểu diễn canonical

```java
byte[] signedRepresentation = canonicalEncode(validatedObject);
signer.update(signedRepresentation);
```

Đây cũng là **pseudocode Java về kiến trúc**; `canonicalEncode` phải do giao thức/thư viện quy định cụ thể, chứ JCA không cung cấp sẵn một bộ canonicalization cho mọi object.

## 3. Một định dạng thông điệp ký được phải định nghĩa những gì?

Trước khi dùng `Signature.update(byte[])`, hãy viết một **hợp đồng biểu diễn thông điệp** đủ chính xác để hai triển khai độc lập sinh ra cùng dãy byte.

| Thành phần | Câu hỏi hợp đồng bắt buộc trả lời |
| --- | --- |
| **Phạm vi ký** | Những trường nào **được bảo vệ** bởi chữ ký? Các trường không được ký có ảnh hưởng đến quyết định nghiệp vụ không? |
| **Domain/purpose** | Chữ ký này dùng cho thanh toán, hoàn tiền, đăng nhập hay chức năng nào? Có tiền tố domain separation không? |
| **Version** | Có schema/codec version nào? Phiên bản có nằm trong **chính phần đã ký** không? |
| **Trường và thứ tự** | Thứ tự field cố định hay sort? Nested objects và arrays có quy tắc gì? |
| **Loại dữ liệu** | `null`, thiếu field, boolean, integer, decimal, text, binary và timestamp biểu diễn ra sao? |
| **Độ dài** | String/binary có prefix độ dài, delimiter có escape, tối đa bao nhiêu byte và số phần tử? |
| **Charset** | Nếu là text, dùng UTF-8 hay charset nào; có BOM không; malformed input bị từ chối hay thay thế? |
| **Unicode** | Giữ nguyên string hay áp dụng NFC/NFD? Có giới hạn ký tự hoặc xử lý invalid surrogate không? |
| **Số và tiền** | Số nguyên minor units, decimal string hay floating-point? Thang đo, làm tròn và xử lý số rất lớn? |
| **Thời gian** | Instant/epoch milliseconds hay ISO-8601 có timezone, precision rõ ràng? |
| **Cấu trúc map/set** | Có bảo toàn thứ tự người dùng nhập không, hay sắp xếp deterministically? |
| **Trường mở rộng** | Trường không biết xử lý thế nào, có được bỏ qua khi ký/xác minh không? |
| **Danh tính key/algorithm** | Public key đáng tin được chọn ra sao; thuật toán/variant có bị input tùy ý điều khiển không? |
| **Chống phát lại** | ID, nonce, timestamp và context nào được ký? Bên nhận lưu dấu đã sử dụng thế nào? |

**Đặc tả tốt là đặc tả có thể tạo *test vector***: cùng một object đầu vào, nhiều hệ thống phải tạo đúng cùng byte (hoặc cùng chuỗi hex), rồi xác minh chữ ký nhất quán.

## 4. Tránh nhập nhằng khi ghép trường

Nếu ghép chuỗi không ranh giới:

```java
String data = first + second;
```

thì hai cặp `("ab", "c")` và `("a", "bc")` đều sinh ra `"abc"`. Một chữ ký trên `"abc"` **không phân biệt được cách chia field**. Nếu đây là hai tình huống nghiệp vụ khác nhau, thiết kế đã cho phép nhập nhằng trước cả khi xét tính an toàn của thuật toán ký.

Các cách tránh nhập nhằng:

1. **Length-prefix:** viết độ dài byte của mỗi trường, sau đó viết đúng số byte ấy.
2. **Schema cố định:** quy định thứ tự field, kiểu dữ liệu, độ dài và điều kiện bắt buộc.
3. **Structured format chuẩn:** dùng JSON canonicalization, CBOR deterministic encoding hoặc cơ chế đã được chuẩn hóa khi phù hợp.
4. **Delimiter có escape chính thức:** chỉ dùng khi giao thức đã định nghĩa xử lý delimiter xuất hiện trong dữ liệu và không có ambiguity.
5. **Domain separation:** đặt một định danh giao thức/loại thao tác đã được ký ở vị trí không thể nhầm với một thông điệp khác.

Ví dụ hai thành phần text có thể biểu diễn bằng:

```text
field_1_length (4 bytes, unsigned/giới hạn theo giao thức)
field_1_data   (UTF-8 bytes)
field_2_length (4 bytes)
field_2_data   (UTF-8 bytes)
```

Khi dùng Java `DataOutputStream.writeInt(n)`, nó ghi **4 byte big-endian (byte có trọng số cao trước)**. Hãy viết độ dài của **UTF-8 byte array**, không phải `String.length()` (số UTF-16 code units).

Nếu dùng `DataOutputStream.writeUTF(...)`, lưu ý API đó ghi **modified UTF-8** cùng prefix độ dài 2 byte, **không phải** “UTF-8 chuẩn + độ dài 4 byte” mà nhiều giao thức dùng. Đừng dùng `writeUTF` mà không ghi rõ wire-format đặc thù Java ấy trong hợp đồng.

## 5. JSON Canonicalization Scheme — RFC 8785

Nếu hệ thống cần ký **giá trị JSON** và có nhu cầu tái tạo cùng signing input giữa Java, JavaScript, Go, Python…, có thể cân nhắc **RFC 8785: JSON Canonicalization Scheme (JCS)**. Đây là một đặc tả canonicalization hiện hành, không phải chức năng tự động được cung cấp bởi `String.format`, `Map.toString` hay một JSON serializer thông thường.

JCS kết hợp những quy tắc chính:

- Đầu vào phải phù hợp **I-JSON**: **không có duplicate property names**, dữ liệu chuỗi hợp lệ Unicode và các ràng buộc JSON number phù hợp.
- **Object property names được sắp xếp đệ quy** theo thứ tự giá trị **UTF-16 code units**, không theo locale của người dùng. Các object lồng trong array cũng phải được canonicalize.
- **Thứ tự phần tử trong array phải được giữ nguyên**; array không phải tập hợp có thể sort tùy tiện.
- Giá trị string phải được serialize/escape theo quy tắc của JCS; **không chèn whitespace tùy ý**.
- JSON number phải được serialize theo **quy tắc ECMAScript** mà RFC yêu cầu. Chỉ gọi `BigDecimal.toString()` hoặc `Double.toString()` không đủ để khẳng định đã tuân thủ JCS.
- Kết quả canonical cuối cùng được **mã hóa UTF-8**.

**Quan trọng:** RFC 8785 **không thực hiện Unicode normalization**. Nếu một string chứa `e` cộng dấu sắc và string khác chứa `é` dựng sẵn, JCS **giữ nguyên dữ liệu Unicode** chứ không tự NFC hóa chúng. Một hệ thống tự thêm `Normalizer.Form.NFC` vào tất cả JSON strings rồi gọi kết quả là “JCS thuần” đã thay đổi quy tắc của RFC.

### Ví dụ về thay đổi thứ tự field

```json
{"name":"Lan","count":1}
```

và:

```json
{"count":1,"name":"Lan"}
```

Sau canonicalization phù hợp RFC 8785, các object hợp lệ này có cùng chuỗi canonical:

```json
{"count":1,"name":"Lan"}
```

Nhưng điều đó **không có nghĩa** mọi JSON có cùng ý nghĩa nghiệp vụ đều sinh byte giống nhau: khác biệt text Unicode, kiểu số hoặc những field ngoài phạm vi quy ước vẫn cần được giải quyết theo chính đặc tả và schema.

### Những điểm JCS dễ bị triển khai sai

| Vấn đề | Quy tắc cần nhớ |
| --- | --- |
| Sort property | Sắp xếp đệ quy theo giá trị **UTF-16 code unit**, không phải sort byte UTF-8 hoặc so sánh locale |
| Array | Giữ nguyên thứ tự phần tử; canonicalize object nằm bên trong |
| Duplicate keys | Input thuộc I-JSON không được có duplicate property names; **reject ở tầng parse** thay vì âm thầm chọn first/last |
| Unicode | Giữ chuỗi “as is”; invalid Unicode như lone surrogate phải báo lỗi |
| Số | JCS có quy tắc number serialization riêng; số nguyên rất lớn/decimal chính xác thường cần **mô hình truyền dạng string** |
| Negative zero, exponent | Không tùy ý dùng cách format số mặc định của JVM |
| Whitespace | Không thêm các khoảng trắng ngoài JSON string |
| Encoder | Kết quả cuối là UTF-8, không BOM tùy ý |
| Thư viện | Phải kiểm tra thư viện tự nhận “JCS compliant” với các **RFC test vectors** |

Với số tiền, không nên đưa các giá trị decimal tùy ý vào binary floating point rồi giả định bảo toàn. Một giao thức có thể quy định **integer minor units** hoặc **decimal string đã được ràng buộc rõ**, sau đó áp dụng đúng mô hình serialization. Nếu dùng I-JSON/JCS, phải tuân thủ ràng buộc IEEE-754 và cách biểu diễn số của RFC; không nhầm việc Java hỗ trợ `long`/`BigDecimal` với khả năng JavaScript giữ nguyên chính xác mọi số.

**Đừng tự khẳng định một `TreeMap` cộng `ObjectMapper.writeValueAsString(...)` là triển khai JCS đầy đủ.** Việc sort key chỉ giải quyết một phần; còn số, chuỗi, escaping, nested object, ràng buộc I-JSON và cách tạo UTF-8.

## 6. JWS và HTTP Message Signatures có signing input riêng

Không nên “canonicalize thêm lần nữa” khi **giao thức đã định nghĩa signing input**.

**JWS — RFC 7515:** ở cách mã hóa JWS thông thường, signing input được tạo từ **base64url của UTF-8 protected header**, một dấu chấm `.`, rồi **base64url của payload bytes**:

```text
ASCII(
  BASE64URL(UTF8(protectedHeaderJson))
  + "."
  + BASE64URL(payloadBytes)
)
```

Đây là **công thức khái niệm** cho JWS thông thường theo RFC 7515; các biến thể/extension có thể quy định thêm điều kiện. Không được đơn giản gọi `Signature.update(rawJsonBody)` rồi tuyên bố kết quả tương thích JWS. Cũng không được tự sort protected header JSON hoặc đổi khoảng trắng sau khi bên ký đã tạo base64url segment được bảo vệ.

**HTTP Message Signatures — RFC 9421:** quy định cách chọn các **covered components** của HTTP message và tạo một **signature base** theo các quy tắc canonicalization cho từng thành phần, kể cả signature parameters. Phải thống nhất đúng thành phần (method, target, headers hoặc digest của body nếu cần), cách tạo giá trị và thứ tự thành phần. Thông điệp qua proxy/gateway có thể thay đổi ở những chỗ giao thức HTTP cho phép; đó chính là lý do cần một signing base được đặc tả.

**Bài học tích hợp:** nếu hệ thống dùng chuẩn sẵn có, hãy dùng một implementation duy trì của chuẩn đó. Tránh xây bộ canonicalizer tự chế “gần giống JWS/JCS/HTTP signatures”, bởi chỉ một khác biệt nhỏ cũng làm mất tính tương thích hoặc tạo khoảng trống bảo mật.

## 7. Ví dụ Java 17+: tự định nghĩa một binary canonical envelope để học nguyên lý

Để thấy rõ **thứ tự field cố định, length-prefix, strict UTF-8, NFC theo hợp đồng, sắp xếp metadata, domain separation và version**, chương trình sau định nghĩa một **định dạng nhị phân DEMO riêng** cho record thanh toán.

**Ranh giới rất quan trọng:** codec dưới đây **không phải JCS, JWS, HTTP Message Signatures hay chuẩn truyền tải công khai**. Nó là ví dụ giáo dục minh họa các thành phần cần có trong một codec xác định. Không đưa trực tiếp vào sản phẩm mà không có đặc tả đầy đủ, parser đối xứng, kiểm thử độc lập, đánh giá bảo mật và cơ chế key/anti-replay đúng chuẩn. Khi có tiêu chuẩn đã được duy trì, ưu tiên tiêu chuẩn đó.

### Hợp đồng của demo

Một `Payment` chứa:

- `action`: đúng `PAYMENT` hoặc `REFUND` (phân biệt purpose).
- `orderId`: từ 1 đến 32 ký tự ASCII trong tập `[A-Za-z0-9_-]`.
- `currency`: chính xác ba ký tự ASCII hoa `[A-Z]{3}`, ví dụ `VND`.
- `amountMinor`: số nguyên `long` không âm, đơn vị nhỏ nhất theo hợp đồng nghiệp vụ; demo không tự quyết định currency scale.
- `tags`: tối đa 16 cặp key/value; key ASCII giới hạn bởi regex; value text được chuyển sang Unicode **NFC** theo **hợp đồng riêng của demo**, rồi encode UTF-8 strict; value tối đa 1024 **byte UTF-8**.

Thứ tự bytes do `canonical(...)` sinh:

```text
ASCII "DEMO-SIGNED-ORDER"  (domain fixed prefix)
0x00                       (separator byte)
0x01                       (binary schema version)
u32 length + UTF8(action)      (UTF-8, NFC, max 1024 bytes)
u32 length + UTF8(orderId)
u32 length + UTF8(currency)
i64 amountMinor               (big-endian 8 bytes)
i32 tagCount                  (big-endian 4 bytes, 0..16)
REPEAT sorted tags:
    u32 length + UTF8(key)   (key ASCII, ascending order)
    u32 length + UTF8(value) (NFC rồi strict UTF-8)
```

Ở đây `u32`/`i32` là ký hiệu logic trong tài liệu cho **bốn byte big-endian**; implementation dùng `DataOutputStream.writeInt` và **đã kiểm tra các giá trị length/count nằm trong phạm vi dương hợp lệ**, nên không cần truyền unsigned int tùy ý. `i64` là `writeLong` big-endian.

Tag key chỉ nhận ASCII nên việc dùng `TreeMap<String, String>` (sort theo `String.compareTo`) tạo thứ tự nhất quán mà không phụ thuộc locale. Text value được NFC hóa **chỉ vì hợp đồng demo quy định như vậy**; không suy ra JCS hay JWS cũng làm thế.

### Chương trình có thể biên dịch và chạy

Lưu file `CanonicalEnvelopeDemo.java` bằng UTF-8:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class CanonicalEnvelopeDemo {
    record Payment(String action, String orderId, String currency,
                   long amountMinor, Map<String, String> tags) {}

    private static void check(boolean ok, String message) {
        if (!ok) throw new IllegalArgumentException(message);
    }

    private static byte[] strictUtf8(String value) throws IOException {
        ByteBuffer data = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(value));
        byte[] bytes = new byte[data.remaining()];
        data.get(bytes);
        return bytes;
    }

    private static void writeText(DataOutputStream out, String text)
            throws IOException {
        String normalized = Normalizer.normalize(text, Normalizer.Form.NFC);
        byte[] bytes = strictUtf8(normalized);
        check(bytes.length <= 1024, "text field too large");
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    private static byte[] canonical(Payment p) throws IOException {
        Objects.requireNonNull(p);
        check("PAYMENT".equals(p.action()) || "REFUND".equals(p.action()),
                "unknown action");
        check(p.orderId() != null &&
                p.orderId().matches("[A-Za-z0-9_-]{1,32}"), "bad order ID");
        check(p.currency() != null &&
                p.currency().matches("[A-Z]{3}"), "bad currency");
        check(p.amountMinor() >= 0, "negative amount");
        check(p.tags() != null && p.tags().size() <= 16, "bad tags");

        TreeMap<String, String> sorted = new TreeMap<>();
        for (var entry : p.tags().entrySet()) {
            check(entry.getKey() != null &&
                    entry.getKey().matches("[a-z][a-z0-9_]{0,31}"),
                    "bad tag name");
            check(entry.getValue() != null, "null tag value");
            sorted.put(entry.getKey(), entry.getValue());
        }

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.write("DEMO-SIGNED-ORDER".getBytes(StandardCharsets.US_ASCII));
            out.writeByte(0);
            out.writeByte(1);
            writeText(out, p.action());
            writeText(out, p.orderId());
            writeText(out, p.currency());
            out.writeLong(p.amountMinor());
            out.writeInt(sorted.size());
            for (var entry : sorted.entrySet()) {
                writeText(out, entry.getKey());
                writeText(out, entry.getValue());
            }
        }
        return bytes.toByteArray();
    }

    private static byte[] sign(PrivateKey key, byte[] data) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(data);
        return signer.sign();
    }

    private static boolean verify(PublicKey key, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        Map<String, String> tagsA = new LinkedHashMap<>();
        tagsA.put("source", "mobile");
        tagsA.put("customer", "Caf\u00e9");

        Map<String, String> tagsB = new LinkedHashMap<>();
        tagsB.put("customer", "Cafe\u0301");
        tagsB.put("source", "mobile");

        Payment a = new Payment("PAYMENT", "ord-42", "VND", 125000L, tagsA);
        Payment b = new Payment("PAYMENT", "ord-42", "VND", 125000L, tagsB);
        byte[] aBytes = canonical(a);
        byte[] bBytes = canonical(b);

        KeyPair keyPair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        byte[] signature = sign(keyPair.getPrivate(), aBytes);

        System.out.println("sameCanonical=" + Arrays.equals(aBytes, bBytes));
        System.out.println("payloadBytes=" + aBytes.length);
        System.out.println("verifiedEquivalent=" +
                verify(keyPair.getPublic(), bBytes, signature));

        Payment altered =
                new Payment("PAYMENT", "ord-42", "VND", 125001L, tagsB);
        System.out.println("changedAmount=" +
                verify(keyPair.getPublic(), canonical(altered), signature));

        Payment otherPurpose =
                new Payment("REFUND", "ord-42", "VND", 125000L, tagsB);
        System.out.println("changedAction=" +
                verify(keyPair.getPublic(), canonical(otherPurpose), signature));

        Map<String, String> changedTags = Map.of(
                "customer", "Caf\u00e9", "source", "web");
        Payment changed = new Payment(
                "PAYMENT", "ord-42", "VND", 125000L, changedTags);
        System.out.println("changedTag=" +
                verify(keyPair.getPublic(), canonical(changed), signature));

        System.out.println("signatureBytes=" + signature.length);

        try {
            canonical(new Payment("PAYMENT", "ord-42", "VND", -1, tagsA));
            System.out.println("negativeRejected=false");
        } catch (IllegalArgumentException e) {
            System.out.println("negativeRejected=true");
        }

        try {
            canonical(new Payment("PAYMENT", "ord-42", "VND", 125000L,
                    Map.of("broken", "\uD800")));
            System.out.println("malformedRejected=false");
        } catch (java.nio.charset.CharacterCodingException e) {
            System.out.println("malformedRejected=true");
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên có Ed25519:

```bash
javac -encoding UTF-8 CanonicalEnvelopeDemo.java
java CanonicalEnvelopeDemo
```

**Đầu ra đã biên dịch và kiểm tra với JDK 24:**

```text
sameCanonical=true
payloadBytes=100
verifiedEquivalent=true
changedAmount=false
changedAction=false
changedTag=false
signatureBytes=64
negativeRejected=true
malformedRejected=true
```

**Ý nghĩa từng kết quả:**

1. `sameCanonical=true`: hai `Map` có thứ tự thêm cặp key khác nhau, đồng thời trường `customer` lần lượt dùng NFC và NFD, nhưng **hợp đồng demo có sort tag và normalize NFC trước khi encode**, nên bytes giống nhau.
2. `payloadBytes=100`: kích thước đúng của binary envelope mẫu; đây là kích thước **payload được ký**, không phải kích thước Ed25519 signature.
3. `verifiedEquivalent=true`: chữ ký của `aBytes` hợp lệ với `bBytes` vì hai byte array **bằng nhau**. Đây không phải khả năng “bỏ qua Unicode” của Ed25519.
4. `changedAmount=false`: thay một giá trị nguyên tiền làm byte khác và chữ ký không hợp lệ.
5. `changedAction=false`: đổi `PAYMENT` sang `REFUND` không thể dùng lại chữ ký; purpose thuộc phạm vi được ký.
6. `changedTag=false`: tag `source` cũng nằm trong signing input; đổi tag làm verify thất bại.
7. `signatureBytes=64`: chữ ký Ed25519 thô có độ dài 64 byte theo RFC 8032.
8. `negativeRejected=true`: validation ở tầng codec chặn số tiền âm.
9. `malformedRejected=true`: strict UTF-8 encoder từ chối surrogate UTF-16 không ghép cặp thay vì âm thầm chèn replacement character.

**Lưu ý môi trường:** `Signature.getInstance("Ed25519")` và `KeyPairGenerator.getInstance("Ed25519")` cần provider hỗ trợ; nếu không có sẽ ném `NoSuchAlgorithmException`. Việc Java 15 bổ sung EdDSA không bảo đảm mọi runtime JDK tùy biến, HSM hay provider có cùng khả năng.

## 8. Vì sao không dùng String nối dấu phân cách hoặc writeUTF?

### Ghép dấu phân cách dễ nhập nhằng

Ví dụ:

```java
String signingText = orderId + "|" + customer + "|" + amount;
```

Nếu `customer` chứa `|`, hoặc parser hai phía xử lý escaping khác nhau, không thể khẳng định serialization có một nghĩa duy nhất. Nếu chỉ cho phép một subset ASCII và delimiter đã được escape đúng quy tắc thì format dựa trên text vẫn có thể được thiết kế an toàn; vấn đề là **quy tắc phải được mô tả đủ chặt chẽ**, không phải cứ có delimiter thì chắc chắn sai.

### Sử dụng writeUTF là một hợp đồng khác

`DataOutputStream.writeUTF(String)` ghi độ dài 2 byte cùng **modified UTF-8**, không trùng với giao thức dùng `UTF-8` chuẩn có prefix 4 byte. Chuỗi chứa `U+0000` hoặc một số code point bổ sung có biểu diễn khác UTF-8 chuẩn. Vì vậy:

- Nếu định dạng của bạn **chủ ý dùng modified UTF-8**, phải ghi rõ và kiểm thử decoder tương ứng.
- Nếu hợp đồng yêu cầu **strict UTF-8**, hãy encode bằng `StandardCharsets.UTF_8.newEncoder()` và tự ghi length-prefix như ví dụ.
- Không dùng `String.length()` làm byte length. Đo **`encoded.length`**.
- Quy định rõ endian, kiểu signed/unsigned, tối đa length và cách xử lý overflow.

### Validation và lỗi trước khi ký

Trong demo, `orderId`, `currency`, `action` và tag key bị ràng buộc chặt; text tag value được NFC hóa và strict UTF-8. Điều đó nhằm làm rõ **mỗi input hợp lệ có một representation**.

Nhưng với hệ thống thật, cũng cần:

- **Decoder đối xứng**: đọc đúng số byte, từ chối length âm/quá lớn, field dư, phiên bản lạ và dữ liệu còn thừa.
- **Kiểm tra duplicate fields** ngay khi parse input có cấu trúc; một `Map` đã làm mất thông tin duplicate không thể tự phát hiện lỗi ấy.
- **Giới hạn tổng payload size** trước khi tạo buffer, ký hoặc verify để tránh cạn tài nguyên.
- **Xử lý unknown field** theo chính sách thống nhất; không bỏ qua một field mà nghiệp vụ lại sử dụng sau khi verify.
- **Versioning/test vectors** cho các thay đổi schema, không dựa vào thay đổi tự động của serializer.
- **Kiểm tra nguồn public key đáng tin**; chữ ký hợp lệ với public key do attacker chọn không chứng minh danh tính đáng tin.

Code demo **không triển khai decoder** vì mục tiêu bài học là chứng minh canonical byte generation và tương tác với `Signature`; không được coi đó là một wire protocol hoàn chỉnh có thể triển khai ngay.

## 9. Thiết kế signing input phải bảo vệ mọi yếu tố quyết định nghiệp vụ

Một hệ thống hoàn toàn có thể **xác minh chữ ký thành công mà vẫn thực hiện sai nghiệp vụ** nếu một dữ liệu quan trọng không được ký. Ví dụ application ký `amount` nhưng không ký `currency`, `accountId` hoặc `action`; một bên có thể thay phần không được ký mà chữ ký của phần còn lại vẫn hợp lệ.

Những trường thường cần nằm trong signing input, tùy giao thức:

- **Purpose/action:** `PAYMENT` khác `REFUND`; tránh dùng một chữ ký cho hai loại lệnh.
- **Version/algorithm context:** version và loại thông điệp xác định parser, schema và phương thức kiểm tra.
- **Định danh bên gửi/nhận hoặc tenant:** ngăn một chữ ký có hiệu lực ngoài phạm vi intended party nếu nghiệp vụ có ràng buộc đó.
- **Đơn vị và ý nghĩa của số:** currency, scale, loại phí, account ID.
- **ID giao dịch hoặc request ID:** hỗ trợ kiểm tra duy nhất và chống replay.
- **Timestamp/expiry/nonce/sequence:** chỉ có tác dụng chống replay khi cũng được ký và **được phía nhận kiểm tra**.
- **Chỉ thị về tài nguyên/đích tác động:** loại lệnh, đường dẫn hoặc định danh tài nguyên nếu thay đổi nó gây hậu quả.
- **Các giá trị header/metadata ảnh hưởng đến quyết định:** phải được ký hoặc bị ràng buộc theo một cơ chế đã đặc tả.

**Có nonce/timestamp trong payload chưa tự chặn replay.** Bên nhận phải kiểm tra thời hạn, sự trùng lặp và lưu trạng thái đã sử dụng. Chữ ký chỉ phát hiện sửa đổi; nó không ngăn kẻ khác phát lại nguyên xi một thông điệp hợp lệ.

**Domain separation** là một cách giảm rủi ro cross-protocol: với hai loại message, dùng định danh/purpose đã được ký và không có ambiguity. Demo dùng tiền tố ASCII cố định cùng action và version. Trong hệ thống thật, quy tắc domain separation phải được thiết kế nhất quán với giao thức đang dùng; không được tự chèn prefix vào signing input của chuẩn đã có mà khiến nó không tương thích.

## 10. Những điểm cần kiểm soát khi tích hợp signer và verifier

### Phía ký

1. Nhận object hoặc payload từ lớp nghiệp vụ.
2. Xác định **đúng schema version/algorithm/purpose** được hỗ trợ.
3. Validate kiểu, phạm vi, required fields, các quy tắc Unicode/number/time.
4. Chuyển sang bytes bằng **một codec canonical duy nhất**, hoặc giữ **raw bytes** nếu giao thức ký raw bytes.
5. Gọi `Signature.initSign(privateKey)` → `update(signingBytes)` → `sign()`.
6. Vận chuyển signature theo định dạng quy định, ví dụ Base64url; không tự chuyển chữ ký nhị phân thành `new String(signatureBytes, UTF_8)`.
7. Không log/export private key, kể cả để debug.

### Phía xác minh

1. Đọc payload, signature, version, metadata theo đúng giao thức và giới hạn kích thước.
2. Xác định **public key đáng tin** từ registry/keystore/certificate đã được xác thực; không tin key nhận kèm payload một cách vô điều kiện.
3. **Không cho payload tùy ý quyết định thuật toán được chấp nhận.** Đối chiếu với allowlist/policy và schema đã được cấu hình.
4. Parse và validate đúng quy tắc; nếu canonical protocol, dùng **cùng codec phiên bản** để tạo signing bytes.
5. Nếu raw protocol, **không tái tạo bytes từ object đã parse**; lấy đúng bytes gốc mà bên ký đã dùng.
6. Gọi `Signature.initVerify(publicKey)` → `update(signingBytes)` → `verify(signatureBytes)`.
7. Chỉ coi dữ liệu được xác thực khi `verify` trả `true`. `false` và exception đều phải khiến hành động nhạy cảm **bị từ chối**.
8. Sau verify, áp dụng kiểm tra nghiệp vụ: quyền tài khoản, expiry, replay protection, amount limit và transaction state.
9. Sử dụng **chính dữ liệu đã xác minh** để xử lý; không validate một object rồi sử dụng object khác/field khác lấy từ phần không được ký.

### Bảo đảm dữ liệu sử dụng đúng dữ liệu đã ký

Một lỗi tinh vi xuất hiện khi hệ thống xác minh trên **biểu diễn chuẩn**, nhưng quyết định nghiệp vụ dựa trên một **diễn giải khác** của payload ban đầu. Ví dụ hai parser không thống nhất cách xử lý duplicate JSON keys: phần được ký/verify có `amount=100` nhưng lớp xử lý lại đọc `amount=100000` từ một trường trùng tên.

Cần quy định: **parse một cách không nhập nhằng, reject duplicate/unknown critical fields, canonicalize và xử lý cùng một mô hình dữ liệu đã được chấp nhận**. Đừng để người xác minh và logic nghiệp vụ áp dụng hai bộ parser/quy tắc khác nhau.

## 11. Khả năng tương thích, version và thay đổi schema

Khi hệ thống mới muốn thêm một field vào thông điệp, có các tình huống:

- Field mới **ảnh hưởng quyết định nghiệp vụ**: phải nằm trong phần được ký hoặc bị kiểm soát bằng cơ chế bảo đảm tương đương.
- Field chỉ là metadata không ảnh hưởng nghiệp vụ: cần mô tả rõ nó có được ký không; nếu không ký, không được tin là đã xác thực.
- Một client cũ không biết field mới: phải xác định reject, ignore theo chính sách, hay chọn version khác. **Không tự bỏ qua field critical**.
- Đổi normalization hoặc cách serialize number: có thể làm thay đổi signing input dù logical data không đổi.
- Thay đổi version của thư viện canonicalization: phải chạy lại test vectors, không xem là nâng cấp không ảnh hưởng chữ ký.

Trong các giao thức có nhiều phiên bản, **version phải được ràng buộc bởi chữ ký** và bên xác minh phải chọn parser/canonicalizer dựa trên **một phiên bản đã được allowlist**. Không “thử lần lượt mọi chuẩn” cho tới khi một chữ ký hợp lệ: cách ấy làm mở rộng tập thông điệp được chấp nhận và có thể tạo lỗ hổng downgrade hoặc ambiguity.

**Bộ test vector** nên gồm ít nhất:

| Test | Điều mong đợi |
| --- | --- |
| Object giống nhau, thay đổi thứ tự thêm `Map` | Cùng canonical bytes nếu schema định nghĩa map không thứ tự |
| Một field text có NFC và NFD | Cùng hoặc khác bytes **theo đúng quy tắc đã chọn**, không suy đoán |
| Đổi một số tiền, loại lệnh hoặc currency | Signing bytes khác và chữ ký cũ không còn hợp lệ |
| JSON có duplicate key | Bị reject trước khi canonicalize nếu tuân thủ I-JSON/JCS |
| Invalid Unicode (lone surrogate) | Reject rõ ràng theo hợp đồng, không thay bằng ký tự khác một cách lặng lẽ |
| Field `null`, absent và empty string | Phân biệt hoặc đồng nhất theo một quy tắc đã được đặc tả |
| Số rất lớn, decimal và `-0` | Không mất độ chính xác hoặc khác số khi qua parser |
| Array đổi thứ tự phần tử | Giữ hoặc thay đổi ý nghĩa theo schema, không sort tự tiện |
| Version và domain khác | Không cho phép xác minh chéo mục đích |
| Giới hạn kích thước/length sai | Reject trước khi cấp phát bộ nhớ lớn hoặc xử lý chữ ký |
| Khác provider, JVM hoặc ngôn ngữ lập trình | Cùng test vectors và hành vi verify với khóa tương thích |

**Không dùng `Map.toString()`, `Object.hashCode()`, `Object.toString()` hoặc serialization Java object nội bộ làm signing format công khai.** Những giá trị này không phải hợp đồng canonical độc lập giữa các môi trường.

## 12. Lỗi thường gặp cần tránh

| Cách làm sai | Vì sao rủi ro | Cách đúng |
| --- | --- | --- |
| Sign trực tiếp `object.toString().getBytes()` | `toString()` không phải định dạng truyền chuẩn | Chọn codec canonical hoặc raw bytes được đặc tả |
| Ghép `field1 + field2` | Có thể tạo nhập nhằng giữa các cặp trường | Length-prefix và schema hoặc serializer chuẩn |
| Sắp xếp JSON keys rồi gọi kết quả là JCS | Chưa đáp ứng các quy tắc khác của RFC 8785 | Dùng canonicalizer compliant, kiểm thử vectors |
| Tự NFC hóa tất cả string trong JCS | RFC 8785 yêu cầu giữ Unicode string data as-is | Theo đúng RFC; tiền xử lý riêng nếu giao thức quy định |
| Đổi array thành sorted set khi canonicalize | Thứ tự array có thể mang nghĩa | Giữ array order theo schema |
| Dùng `writeUTF` và gọi nó là UTF-8 chuẩn | `writeUTF` dùng modified UTF-8 và prefix 2 byte | Dùng strict UTF-8 với length-prefix rõ hoặc định nghĩa riêng |
| Dùng `String.length()` làm độ dài byte | `String.length()` đếm UTF-16 code units | Dùng `byte[].length` của chuỗi đã encode |
| Ký amount nhưng không ký currency/purpose | Có thể tái sử dụng chữ ký cho hành động khác | Ký toàn bộ dữ liệu có ý nghĩa bảo mật |
| Chỉ ký payload, không có chống replay | Chữ ký hợp lệ có thể bị gửi lại nguyên vẹn | Ký ID/nonce/time và kiểm tra trạng thái phía nhận |
| Cho decoder tự bỏ qua duplicate keys | Các tầng có thể hiểu field theo cách khác nhau | Reject duplicate/unknown critical field |
| Canonicalize bằng locale mặc định | Số/ngày/chuỗi có thể khác theo hệ điều hành | Quy định serialization/charset/locale độc lập môi trường |
| Nếu verify thất bại thì thử format khác | Mở rộng dữ liệu được chấp nhận ngoài giao thức | Chỉ áp dụng một bộ quy tắc đã xác định/versioned |
| Để payload chỉ định thuật toán nào cũng được | Có thể dẫn đến algorithm confusion/downgrade | Enforce danh sách thuật toán cho phép và key policy |
| Dùng public key tự khai báo trong payload là đã đáng tin | Attacker có thể tự ký dữ liệu bằng key của họ | Xác thực nguồn public key độc lập |

## 13. Bài tập và đáp án

**Bài 1.** Một hệ thống ký `"ab" + "c"`; hệ thống khác nhận hai field `"a"` và `"bc"` rồi cũng nối lại. Vì sao `verify=true` có thể xảy ra dù field khác nhau? Sửa thế nào?

**Bài 2.** Hai JSON object chỉ khác thứ tự property name. Nếu cả hai phía áp dụng **RFC 8785 đầy đủ**, chúng có thể tạo cùng signing bytes không?

**Bài 3.** Một chuỗi ở bên A dùng NFC, bên B dùng NFD. Hợp đồng ghi rõ dùng **JCS thuần**. Có được tự NFC-normalize trước canonicalization mà vẫn tuyên bố chỉ dùng JCS không?

**Bài 4.** Một message payment có `orderId`, `amountMinor`, `currency`, nhưng bên ký chỉ ký `amountMinor`. Người nhận có bảo vệ được ý nghĩa đầy đủ của payment không?

**Bài 5.** Một định dạng nhị phân tự thiết kế dùng `DataOutputStream.writeUTF(value)`, còn decoder phía khác đợi length 4 byte + UTF-8 chuẩn. Điều gì có thể sai?

**Bài 6.** Một client nhận JSON có hai field `"amount"` trùng tên; parser A chọn field đầu, parser B chọn field sau. Có nên cố canonicalize rồi verify không?

**Bài 7.** Nếu chữ ký trên thông điệp thanh toán hoàn toàn hợp lệ nhưng request được gửi lại lần thứ hai, `verify` có tự chặn replay không?

**Đáp án:**

1. Vì phép nối không có ranh giới: hai cặp field cho cùng byte `"abc"`. Dùng length-prefix hoặc một định dạng canonical không nhập nhằng, có schema và type rõ ràng.
2. Có, khi object hợp lệ I-JSON và chỉ khác thứ tự property: JCS sort property names theo UTF-16 code units và tạo JSON canonical byte UTF-8 giống nhau.
3. Không. **JCS không Unicode-normalize**. Nếu có bước NFC riêng thì phải là quy tắc tiền xử lý ngoài JCS, được mô tả rõ và áp dụng nhất quán bởi cả hai bên.
4. Không. Currency, orderId và loại thao tác có thể bị thay mà không tác động đến bytes đã ký. Phải ký những trường có ý nghĩa bảo mật/nghiệp vụ.
5. Hai phía có wire format khác nhau: `writeUTF` dùng modified UTF-8 với prefix 2 byte; không tương thích với length 4 byte + UTF-8 chuẩn.
6. Không. Input ambiguous phải bị reject theo ràng buộc I-JSON/JCS hoặc schema; không để hai parser xử lý khác nhau.
7. Không. Chữ ký chỉ xác nhận nội dung và khóa; chống replay cần nonce/ID/timestamp được ký **và** cơ chế kiểm tra trùng lặp hoặc thời hạn ở server.

## Tài liệu tham khảo hiện hành

- [RFC 8785 — JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785): quy tắc I-JSON, UTF-16 sort, JSON number/string serialization, UTF-8 và **không Unicode-normalize**.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cách tạo JWS Signing Input cho protected header và payload.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): covered components, signature base và canonicalization đối với HTTP.
- [Oracle Java SE 26 — DataOutputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/DataOutputStream.html): big-endian `writeInt`/`writeLong` và modified UTF-8 trong `writeUTF`.
- [Oracle Java SE 26 — Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): `initSign`, `update`, `sign`, `initVerify`, `verify`.
- [Oracle Java SE 26 — Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD khi một giao thức **chủ động yêu cầu** normalization.
- [Oracle Java SE 26 — StandardCharsets / CharsetEncoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, strict encoding và malformed input.
- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): EdDSA/Ed25519/Ed448 được đưa vào JDK 15.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): đặc tả Ed25519 và độ dài chữ ký 64 byte.