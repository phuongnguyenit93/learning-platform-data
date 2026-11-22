# 9.7 Định dạng chữ ký ECDSA DER và P1363 khi trao đổi với hệ thống khác

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao cùng thuật toán **ECDSA** và cùng khóa công khai vẫn có thể gặp lỗi xác minh khi hai hệ thống dùng **hai cách mã hóa chữ ký** khác nhau.
2. Phân biệt chữ ký **ASN.1 DER** dạng `SEQUENCE { INTEGER r, INTEGER s }` và **IEEE P1363** dạng byte thô `r || s`, có độ dài cố định.
3. Tính chính xác độ dài P1363 theo **số bit bậc nhóm (curve order)**, kể cả P-521 có độ dài thành phần 66 byte.
4. Dùng **Java 17 `Signature`** để ký/xác minh ở cả hai định dạng; chuyển đổi DER ↔ P1363 có kiểm tra chuẩn tắc.
5. Kết nối đúng với giao thức **JWS/JWT ES256, ES384, ES512**, phân biệt Base64URL và encoding chữ ký.
6. Chẩn đoán các lỗi sai curve, sai hash, khác byte dữ liệu ký, nhầm chữ ký DER với key/certificate DER, sai padding số nguyên và vấn đề low-S.

## 1. ECDSA tạo cặp số (r, s), định dạng là bước tiếp theo

**ECDSA (Elliptic Curve Digital Signature Algorithm)** là sơ đồ chữ ký số trên đường cong elliptic. Người ký dùng **private key**, người kiểm tra dùng **public key**. Sau khi xử lý hash của dữ liệu cần ký và phép toán ECDSA, kết quả logic là **hai số nguyên**:

```text
                 private key d
                      |
Message bytes -> Hash -> ECDSA sign -> (r, s)
                                        |
                                 MÃ HÓA / SERIALIZE
                                  /               \
                                 v                 v
                       ASN.1 DER bytes       P1363 raw bytes
                        SEQUENCE(r,s)           r || s
```

**`(r, s)` mới là ý nghĩa toán học của chữ ký; DER và P1363 là hai cách biến chính cặp số đó thành byte.** Việc đổi định dạng **không thay khóa**, **không đổi curve**, **không đổi hash**, **không tạo một chữ ký mới**. Nếu giải mã và mã hóa lại chính xác, hệ thống bên kia vẫn đang xác minh cùng chữ ký ECDSA.

Một quy trình xác minh thành công còn yêu cầu hai bên thống nhất:

- **Bytes được ký**: đúng từng byte, kể cả UTF-8, xuống dòng, khoảng trắng, JSON canonicalization hay Base64URL signing input.
- **Thuật toán digest**: ví dụ SHA-256 trong `SHA256withECDSA`.
- **Curve và public key**: ví dụ P-256, P-384 hay P-521; không được tráo khóa.
- **Signature encoding**: ASN.1 DER hay IEEE P1363 raw; một số giao thức có thêm wrapper hoặc yêu cầu canonicalization.
- **Chính sách giao thức**: danh sách thuật toán được phép, key ID, chữ ký của đúng đối tượng và các trường ngữ cảnh cần xác thực.

Việc gửi đúng chữ ký với nhãn sai encoding sẽ khiến verifier lỗi hoặc từ chối ngay cả khi dữ liệu, khóa và thuật toán toán học đều đúng.

## 2. Hai định dạng: DER và P1363

| Tiêu chí | ECDSA ASN.1 DER | IEEE P1363 raw |
| --- | --- | --- |
| Cấu trúc | ASN.1 `SEQUENCE` chứa hai `INTEGER` là `r` và `s` | Hai số `r` và `s` nối trực tiếp: `r \|\| s` |
| Biểu diễn số | Số nguyên **có dấu** theo DER (giá trị ECDSA phải dương), big-endian, độ dài tối thiểu | Số nguyên **không dấu**, big-endian, **đệm zero bên trái đủ độ rộng** |
| Byte mở đầu | Thường `0x30` (ASN.1 SEQUENCE) | Byte đầu là dữ liệu của `r`, **không có tag chuẩn** |
| Kích thước | Thay đổi theo giá trị `r`, `s` và byte độ dài ASN.1 | **Cố định theo curve order** |
| Java 17 | `SHA256withECDSA` (định dạng DER tiêu chuẩn của JCA) | `SHA256withECDSAinP1363Format` (nếu provider hỗ trợ) |
| Thực tế trao đổi | Nhiều API crypto, X.509/TLS và công cụ theo truyền thống ASN.1 | JWS/JOSE ES256, ES384, ES512; một số SDK/API theo IEEE P1363 |

Không nên gọi P1363 là “DER không có header”. P1363 yêu cầu **chiều rộng cố định cho cả r và s**, trong khi DER cho phép mỗi INTEGER có số byte thay đổi và đôi khi thêm byte `00` để tránh bị hiểu là số âm. Chỉ cắt các byte `30, 02` không tạo ra P1363 hợp lệ.

### 2.1 DER: hai ASN.1 INTEGER bên trong một SEQUENCE

Trong một chữ ký ECDSA DER thông thường, cấu trúc logic là:

```asn1
Ecdsa-Sig-Value ::= SEQUENCE {
    r INTEGER,
    s INTEGER
}
```

Byte biểu diễn theo **DER (Distinguished Encoding Rules)**:

```text
30 <SEQUENCE length>
   02 <r length> <r bytes, signed-positive, minimal>
   02 <s length> <s bytes, signed-positive, minimal>
```

- `0x30`: tag của ASN.1 SEQUENCE.
- `0x02`: tag của INTEGER.
- Các trường length dùng DER length encoding (short form nếu dưới 128, long form nếu từ 128 trở lên).
- INTEGER dùng big-endian, được mã hóa theo biểu diễn có dấu hai phần bù, **không có các zero thừa**.
- Vì `r, s > 0` trong chữ ký hợp lệ, nếu bit cao nhất của byte có nghĩa đầu tiên bằng `1`, DER **phải thêm một byte `0x00` phía trước** để không biến số dương thành số âm.

Ví dụ chỉ nhằm giải thích **mã hóa**, không phải chữ ký ECDSA thật của một thông điệp/khóa:

```text
r = 1, s = 2

DER:
30 06  02 01 01  02 01 02

30 06       : SEQUENCE, nội dung dài 6 byte
02 01 01    : INTEGER r = 1
02 01 02    : INTEGER s = 2
```

Với một giá trị có byte đầu `0x80` (bit dấu bật), DER INTEGER cần:

```text
Giá trị r = 128 = 0x80
INTEGER DER = 02 02 00 80
                   ^^ byte 00 bắt buộc để giữ số dương
```

Ngược lại, `02 02 00 01` là DER **không chuẩn tắc** vì giá trị 1 chỉ cần `02 01 01`. Khi xử lý dữ liệu không tin cậy, cần từ chối INTEGER âm, độ dài không đúng, zero thừa, dữ liệu dư hay SEQUENCE không chuẩn.

**Không dùng độ dài DER cố định.** Với ECDSA P-256, thường thấy chữ ký quanh 70–72 byte, nhưng còn có thể ngắn hơn do r/s bỏ zero đầu; cần parse theo cấu trúc chứ không suy luận bằng độ dài. Với P-521, phần nội dung SEQUENCE thường vượt 127 byte nên DER dùng **long-form length**, ví dụ dạng `30 81 ...`. Parser chỉ hỗ trợ “một byte length” sẽ hỏng khi gặp curve lớn.

### 2.2 P1363: hai số unsigned với độ dài cố định

Với IEEE P1363:

```text
P1363 = I2OSP(r, width) || I2OSP(s, width)

width = ceil(bitLength(curve_order) / 8)
length(P1363) = 2 * width
```

`I2OSP` ở đây nghĩa là chuyển số nguyên **không dấu** thành đúng `width` byte, big-endian; nếu số có ít byte có nghĩa hơn thì **đệm `00` ở bên trái**. Không thêm ASN.1 tag, length hoặc byte báo dấu. Nửa đầu là `r`, nửa cuối là `s`; **không đảo thứ tự**.

| Curve thường dùng | Số bit của order | Width mỗi phần | Tổng P1363 |
| --- | ---: | ---: | ---: |
| NIST P-256 (`secp256r1`) | 256 | 32 byte | **64 byte** |
| NIST P-384 (`secp384r1`) | 384 | 48 byte | **96 byte** |
| NIST P-521 (`secp521r1`) | 521 | 66 byte | **132 byte** |

Chú ý **P-521 là 521 bit**, nên mỗi số phải dùng `ceil(521/8) = 66` byte, không phải 65. Tổng độ dài chữ ký raw là `132` byte; 7 bit cao chưa dùng của byte đầu vẫn phải được biểu diễn đúng.

Một cặp số minh họa `r=1, s=2` với P-256:

```text
r: 00 00 ... 00 01   (tổng 32 byte)
s: 00 00 ... 00 02   (tổng 32 byte)
=> r || s dài đúng 64 byte
```

Khi chuyển từ DER sang P1363, bỏ byte `00` **dấu dương** của DER nếu có, nhưng sau đó **phải thêm đủ leading zero** để mỗi phần đúng `width`. Khi chuyển ngược lại, bỏ các zero dư của raw, rồi thêm `00` nếu byte cao nhất có bit dấu, mã hóa INTEGER/SEQUENCE DER.

## 3. Vì sao hai hệ thống có thể trả “invalid signature”?

Giả sử Java ký:

```java
Signature signer = Signature.getInstance("SHA256withECDSA");
```

Đây là **mã nhúng** (cần import, khóa và các lệnh `initSign/update/sign`). Trong JDK thông dụng, nó trả **DER-encoded** ECDSA `SEQUENCE(INTEGER r, INTEGER s)`.

Một API khác ghi trong hợp đồng “ECDSA SHA-256, signature is IEEE P1363 r||s”, hoặc yêu cầu **JWS ES256**. Nếu bạn gửi thẳng byte DER cho bên đó, họ nhận khoảng 70 byte thay vì **64 byte**. Hai bên vẫn dùng SHA-256/P-256 nhưng **khác hợp đồng serialization** nên sẽ lỗi.

Chiều ngược lại cũng vậy: đưa raw `r||s` 64 byte cho verifier chờ ASN.1 DER thì parser không tìm thấy `SEQUENCE` và hai `INTEGER`. Tùy provider, Java có thể trả `false` hoặc ném `SignatureException` với lỗi encoding. Không nên bắt exception rồi coi “signature valid” hay mặc định thử cả hai định dạng trên input không được gắn nhãn.

Luồng tích hợp đúng:

```text
Bên A tạo (r, s)
       |
       +--> serialize DER ----> giao thức mong DER
       |
       +--> serialize P1363 --> giao thức mong raw r||s

Bên B đọc theo định dạng đã quy định
       |
       v
Tách r, s và kiểm tra 0 < r,s < order
       |
       v
ECDSA.verify(hash(bytes), publicKey, r, s)
```

Nếu phải chuyển encoding, hãy làm **một lần tại ranh giới hệ thống**, ghi rõ kỳ vọng; lưu test vector và fail closed với input sai thay vì sử dụng heuristic “byte đầu 0x30 thì chắc DER” vì raw P1363 cũng có thể tình cờ bắt đầu `0x30`.

## 4. Java 17 có thể làm trực tiếp cả hai định dạng

Java 17 định nghĩa các tên algorithm gồm:

- `SHA256withECDSA` → chữ ký ECDSA dùng SHA-256, encoding ASN.1 DER thông dụng.
- `SHA256withECDSAinP1363Format` → cùng hashing/ECDSA, encoding IEEE P1363.
- Tương ứng `SHA384withECDSA` / `SHA384withECDSAinP1363Format` cho P-384.
- Tương ứng `SHA512withECDSA` / `SHA512withECDSAinP1363Format` cho P-521.

**Tên trong Java không tự buộc dùng đúng curve**. Ví dụ `SHA256withECDSA` mô tả digest/ECDSA, còn curve đến từ **EC key**. Giao thức ES256 lại yêu cầu **P-256 + SHA-256**, nên phải kiểm tra cả curve lẫn algorithm; không chỉ nhìn tên.

Các thuật toán có trong danh sách **standard algorithm names** và được SunEC cung cấp trên nhiều JDK; khả năng sẵn có phụ thuộc provider/cấu hình runtime. Ưu tiên `Signature.getInstance(name)` và kiểm tra khả năng hỗ trợ khi khởi động, tránh gắn chặt provider name nếu không cần.

### 4.1 Thực hành 1: tạo chữ ký DER và P1363, xác minh bằng API tương ứng

Tạo file **`EcdsaSignatureFormatsDemo.java`** (Java 17 trở lên):

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;

public class EcdsaSignatureFormatsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = generator.generateKeyPair();
        byte[] message = "document:v1".getBytes(StandardCharsets.UTF_8);

        Signature derSigner = Signature.getInstance("SHA256withECDSA");
        derSigner.initSign(pair.getPrivate());
        derSigner.update(message);
        byte[] der = derSigner.sign();

        Signature p1363Signer =
                Signature.getInstance("SHA256withECDSAinP1363Format");
        p1363Signer.initSign(pair.getPrivate());
        p1363Signer.update(message);
        byte[] p1363 = p1363Signer.sign();

        Signature derVerifier = Signature.getInstance("SHA256withECDSA");
        derVerifier.initVerify(pair.getPublic());
        derVerifier.update(message);

        Signature rawVerifier =
                Signature.getInstance("SHA256withECDSAinP1363Format");
        rawVerifier.initVerify(pair.getPublic());
        rawVerifier.update(message);

        int componentBytes =
                ((((ECPublicKey) pair.getPublic()).getParams()
                        .getOrder().bitLength()) + 7) / 8;
        System.out.println("component bytes: " + componentBytes);
        System.out.println("DER starts with SEQUENCE: " +
                (der.length > 0 && (der[0] & 0xff) == 0x30));
        System.out.println("P1363 bytes: " + p1363.length);
        System.out.println("DER verifies: " + derVerifier.verify(der));
        System.out.println("P1363 verifies: " + rawVerifier.verify(p1363));

        Signature changed = Signature.getInstance("SHA256withECDSAinP1363Format");
        changed.initVerify(pair.getPublic());
        changed.update("document:v2".getBytes(StandardCharsets.UTF_8));
        System.out.println("changed message verifies: " + changed.verify(p1363));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 EcdsaSignatureFormatsDemo.java
java EcdsaSignatureFormatsDemo
```

Đầu ra đã kiểm tra:

```text
component bytes: 32
DER starts with SEQUENCE: true
P1363 bytes: 64
DER verifies: true
P1363 verifies: true
changed message verifies: false
```

Giải thích:

1. `KeyPairGenerator("EC")` tạo khóa với curve `secp256r1` (NIST P-256); mỗi ECDSA signature dùng cùng cặp khóa nhưng được ký **riêng hai lần**.
2. `SHA256withECDSA` trả DER; `SHA256withECDSAinP1363Format` trả raw fixed-width. `der[0]==0x30` là **quan sát cấu trúc trong ví dụ**, không phải quy tắc nhận diện định dạng từ dữ liệu bất kỳ.
3. `ECPublicKey.getParams().getOrder().bitLength()` cho biết chiều rộng thành phần từ **group order**. P-256 có 32 byte mỗi phần, nên raw dài 64.
4. Mỗi verifier nhận đúng encoding mà `Signature.getInstance(...)` của nó yêu cầu, nên xác minh thành công.
5. Khi bytes thông điệp thay đổi từ `document:v1` sang `document:v2`, chữ ký không còn hợp lệ.

**Hai chữ ký ký riêng có thể khác nhau về `r, s` do giá trị nonce nội bộ ECDSA.** Bài này không so sánh trực tiếp mảng DER với mảng P1363 của hai lần ký độc lập; muốn chứng minh conversion bảo toàn *cùng một* chữ ký, dùng thực hành tiếp theo.

## 5. Chuyển DER ↔ P1363 một cách đúng đắn

Trong ứng dụng, ưu tiên chọn **đúng format ngay khi gọi `Signature`**. Nếu provider hoặc SDK chỉ trả định dạng còn lại, conversion tại ranh giới API là hợp lý, nhưng **DER là một định dạng có quy tắc canonical nghiêm ngặt**.

### 5.1 Quy trình DER → P1363

1. Đọc một ASN.1 SEQUENCE tag `0x30` và length **đúng**, không có trailing bytes.
2. Trong SEQUENCE phải có **đúng hai** INTEGER theo thứ tự `r, s`, không thêm trường.
3. DER INTEGER phải dương, biểu diễn tối thiểu, không có dấu âm hay prefix `00` dư.
4. Kiểm tra các scalar `1 <= r,s < n`, trong đó `n` là bậc nhóm EC lấy từ curve của public key.
5. Chuyển mỗi số sang unsigned big-endian với đúng `ceil(bitLength(n)/8)` byte. Thêm zero ở **bên trái** nếu số ít byte có nghĩa.
6. Ghép hai mảng không có separator và giữ đúng thứ tự `r||s`.

### 5.2 Quy trình P1363 → DER

1. Yêu cầu **chính xác** `2 * width` byte; từ chối raw bị cắt hoặc thừa byte.
2. Chia thành `rBytes` và `sBytes`, mỗi phần dài `width`.
3. Tạo `BigInteger(1, bytes)` để đọc **unsigned**; nếu dùng `new BigInteger(bytes)` không có `signum=1` thì các giá trị bắt đầu bằng bit `1` có thể bị hiểu thành số âm.
4. Kiểm tra `1 <= r,s < n` theo curve thực.
5. Chuyển từng số thành DER INTEGER tối thiểu: loại zero dư, **thêm một byte `00`** nếu cần giữ dấu dương.
6. Đóng gói hai INTEGER vào một SEQUENCE; dùng DER short/long length đúng quy tắc.

**Không ghép/xóa byte theo offset cố định kiểu “`DER.substring(4)`”**. DER P-256 có thể chứa số byte khác nhau; P-521 còn có trường length long-form. Parser cần chống DER không chuẩn tắc, length overflow, trailing data, INTEGER âm/zero, thừa zero và scalar vượt bậc nhóm. Việc tuân thủ canonical encoding còn giúp các hệ thống khác nhau không diễn giải cùng một giá trị theo nhiều dạng byte tùy tiện.

### 5.3 Thực hành 2: bộ chuyển định dạng tối giản có kiểm tra chuẩn tắc

Ví dụ sau là **một chương trình Java 17 độc lập**. Nó:

- Parse DER theo quy tắc tối thiểu cần thiết cho ECDSA `SEQUENCE(INTEGER r, INTEGER s)`.
- Mã hóa DER length ở cả short và long form, hoạt động với P-521.
- Kiểm tra r/s trong miền hợp lệ của group order thay vì chỉ dựa vào số bit.
- Dùng `BigInteger(1, bytes)` cho raw và xử lý đúng zero dành cho dấu DER.
- Ký một lần bằng DER, chuyển sang P1363, chuyển về DER, rồi kiểm chữ ký bằng **cả hai API Java**.
- Từ chối một DER INTEGER có leading `00` không cần thiết.

**Giới hạn:** đây là codec học tập cho chữ ký ECDSA, không thay một ASN.1/cryptography library đã được audit khi xử lý các giao thức nhiều cấu trúc phức tạp. Không dùng `sun.security.util.*` hoặc reflection vào JDK internals.

Tạo file **`EcdsaDerP1363Bridge.java`**:

```java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

public class EcdsaDerP1363Bridge {
    private static int width(BigInteger order) {
        return (order.bitLength() + 7) / 8;
    }

    private static void checkScalar(BigInteger x, BigInteger order) {
        if (x.signum() <= 0 || x.compareTo(order) >= 0) {
            throw new IllegalArgumentException("ECDSA scalar outside (0, n)");
        }
    }

    private static void requireTag(byte[] in, int[] pos, int end, int tag) {
        if (pos[0] >= end || (in[pos[0]++] & 0xff) != tag) {
            throw new IllegalArgumentException("Wrong DER tag");
        }
    }

    private static int readLength(byte[] in, int[] pos, int end) {
        if (pos[0] >= end) throw new IllegalArgumentException("Missing length");
        int first = in[pos[0]++] & 0xff;
        if (first < 128) return first;
        int count = first & 0x7f;
        if (count == 0 || count > 4 || count > end - pos[0]) {
            throw new IllegalArgumentException("Invalid DER length");
        }
        if (in[pos[0]] == 0) throw new IllegalArgumentException("Non-minimal length");
        long length = 0;
        for (int i = 0; i < count; i++) {
            length = (length << 8) | (in[pos[0]++] & 0xff);
        }
        if (length < 128 || length > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid long length");
        }
        return (int) length;
    }

    private static BigInteger readInteger(byte[] in, int[] pos, int end) {
        requireTag(in, pos, end, 0x02);
        int length = readLength(in, pos, end);
        if (length < 1 || length > end - pos[0]) {
            throw new IllegalArgumentException("Invalid INTEGER length");
        }
        int first = in[pos[0]] & 0xff;
        if ((first & 0x80) != 0) {
            throw new IllegalArgumentException("Negative INTEGER");
        }
        if (length > 1 && first == 0 &&
                (in[pos[0] + 1] & 0x80) == 0) {
            throw new IllegalArgumentException("Redundant 00 prefix");
        }
        BigInteger out = new BigInteger(
                1, Arrays.copyOfRange(in, pos[0], pos[0] + length));
        pos[0] += length;
        return out;
    }

    private static byte[] fixed(BigInteger n, int width) {
        byte[] bytes = n.toByteArray();
        int start = bytes.length > 1 && bytes[0] == 0 ? 1 : 0;
        int bytesToCopy = bytes.length - start;
        if (bytesToCopy > width) {
            throw new IllegalArgumentException("Scalar too wide");
        }
        byte[] result = new byte[width];
        System.arraycopy(bytes, start, result, width - bytesToCopy, bytesToCopy);
        return result;
    }

    public static byte[] derToP1363(byte[] der, BigInteger order) {
        int[] pos = {0};
        requireTag(der, pos, der.length, 0x30);
        int sequenceLength = readLength(der, pos, der.length);
        if (sequenceLength != der.length - pos[0]) {
            throw new IllegalArgumentException("Trailing data or bad SEQUENCE length");
        }
        BigInteger r = readInteger(der, pos, der.length);
        BigInteger s = readInteger(der, pos, der.length);
        if (pos[0] != der.length) {
            throw new IllegalArgumentException("Wrong SEQUENCE contents");
        }
        checkScalar(r, order);
        checkScalar(s, order);
        int width = width(order);
        byte[] result = new byte[2 * width];
        System.arraycopy(fixed(r, width), 0, result, 0, width);
        System.arraycopy(fixed(s, width), 0, result, width, width);
        return result;
    }

    private static byte[] derLength(int length) {
        if (length < 128) return new byte[] {(byte) length};
        int count = 0;
        for (int n = length; n != 0; n >>>= 8) count++;
        byte[] bytes = new byte[1 + count];
        bytes[0] = (byte) (0x80 | count);
        for (int i = count; i > 0; i--) {
            bytes[i] = (byte) length;
            length >>>= 8;
        }
        return bytes;
    }

    private static byte[] tlv(int tag, byte[] value) {
        byte[] len = derLength(value.length);
        byte[] result = new byte[1 + len.length + value.length];
        result[0] = (byte) tag;
        System.arraycopy(len, 0, result, 1, len.length);
        System.arraycopy(value, 0, result, 1 + len.length, value.length);
        return result;
    }

    public static byte[] p1363ToDer(byte[] raw, BigInteger order) {
        int width = width(order);
        if (raw.length != width * 2) {
            throw new IllegalArgumentException("P1363 must be 2*width bytes");
        }
        BigInteger r = new BigInteger(1, Arrays.copyOfRange(raw, 0, width));
        BigInteger s = new BigInteger(1, Arrays.copyOfRange(raw, width, 2 * width));
        checkScalar(r, order);
        checkScalar(s, order);
        byte[] ri = tlv(0x02, r.toByteArray());
        byte[] si = tlv(0x02, s.toByteArray());
        byte[] both = new byte[ri.length + si.length];
        System.arraycopy(ri, 0, both, 0, ri.length);
        System.arraycopy(si, 0, both, ri.length, si.length);
        return tlv(0x30, both);
    }

    public static void main(String[] args) throws Exception {
        String[] curves = {"secp256r1", "secp384r1", "secp521r1"};
        String[] hashes = {"SHA256", "SHA384", "SHA512"};
        byte[] data = "signed-record-v1".getBytes(StandardCharsets.UTF_8);

        for (int i = 0; i < curves.length; i++) {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
            generator.initialize(new ECGenParameterSpec(curves[i]));
            KeyPair pair = generator.generateKeyPair();
            BigInteger order = ((ECPublicKey) pair.getPublic()).getParams().getOrder();

            Signature signer = Signature.getInstance(hashes[i] + "withECDSA");
            signer.initSign(pair.getPrivate());
            signer.update(data);
            byte[] der = signer.sign();

            byte[] raw = derToP1363(der, order);
            byte[] derAgain = p1363ToDer(raw, order);

            Signature verifyRaw =
                    Signature.getInstance(hashes[i] + "withECDSAinP1363Format");
            verifyRaw.initVerify(pair.getPublic());
            verifyRaw.update(data);

            Signature verifyDer =
                    Signature.getInstance(hashes[i] + "withECDSA");
            verifyDer.initVerify(pair.getPublic());
            verifyDer.update(data);

            System.out.println(curves[i] + ": P1363=" + raw.length +
                    ", both verify=" + (verifyRaw.verify(raw) && verifyDer.verify(derAgain)) +
                    ", DER exact=" + Arrays.equals(der, derAgain));
        }

        // Chỉ dùng để test DER parser; đây không phải curve order sản xuất.
        BigInteger exampleOrder = BigInteger.ONE.shiftLeft(256)
                .subtract(BigInteger.valueOf(189));
        byte[] malformed = {0x30, 0x07, 0x02, 0x02, 0x00, 0x01,
                0x02, 0x01, 0x01};
        boolean invalidDerRejected;
        try {
            derToP1363(malformed, exampleOrder);
            invalidDerRejected = false;
        } catch (IllegalArgumentException expected) {
            invalidDerRejected = true;
        }
        System.out.println("non-minimal DER rejected: " + invalidDerRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 EcdsaDerP1363Bridge.java
java EcdsaDerP1363Bridge
```

Đầu ra đã kiểm tra với provider hỗ trợ P-256/P-384/P-521 và các tên JCA tương ứng:

```text
secp256r1: P1363=64, both verify=true, DER exact=true
secp384r1: P1363=96, both verify=true, DER exact=true
secp521r1: P1363=132, both verify=true, DER exact=true
non-minimal DER rejected: true
```

**Giải thích các kết quả:**

- Mỗi curve tạo **một chữ ký DER**, sau đó chuyển byte của **chính cặp `r,s` đó** sang P1363; verifier P1363 chấp nhận chữ ký, chứng minh không cần ký lại.
- Chuyển ngược P1363 → DER và so sánh `Arrays.equals(der, derAgain)` trả `true`, vì DER chuẩn tắc có biểu diễn duy nhất cho cặp số này.
- P-521 có `width=66` nên P1363 132 byte; codec xử lý DER long-form length thay vì giả định một byte length.
- Kiểm tra `malformed` sử dụng một `INTEGER 00 01` với leading zero **không cần thiết**. Parser từ chối; biến `exampleOrder` chỉ tạo miền đủ lớn cho **test cú pháp**, hoàn toàn không dùng làm khóa/curve order cho ký thật.
- Các kết quả boolean là đầu ra xác định khi môi trường có thuật toán; byte DER thực tế và chiều dài DER có thể thay đổi từ lần ký này sang lần khác.

**Không thay converter bằng một phép chia chuỗi theo số byte DER cố định.** Ngoài việc parse đúng, sản phẩm cần test parser với dữ liệu sai cố ý và ràng buộc kích thước đầu vào để ngăn xử lý ASN.1 không an toàn. Khi dùng thư viện ASN.1 chuyên dụng, vẫn cần kiểm soát **canonical DER** và **range của r/s**, chứ không chỉ gọi parse để được hai BigInteger.

## 6. JWS/JWT ES256, ES384, ES512 dùng P1363 raw

Đây là nguồn sai lệch định dạng phổ biến khi ứng dụng Java giao tiếp với SDK/identity provider. Trong **JSON Web Signature (JWS)**, các giá trị:

| JOSE `alg` | Curve bắt buộc | Hash | Chữ ký JWS (trước Base64URL) | Signature segment Base64URL không padding |
| --- | --- | --- | ---: | ---: |
| **ES256** | P-256 | SHA-256 | **64 byte** | 86 ký tự |
| **ES384** | P-384 | SHA-384 | **96 byte** | 128 ký tự |
| **ES512** | P-521 | SHA-512 | **132 byte** | 176 ký tự |

**ES512** không có nghĩa “curve P-512”; nó dùng **P-521** và **SHA-512** theo RFC 7518. Chữ ký JWS được định nghĩa là `r||s` cố định, không phải DER. Vì thế cách làm:

```text
Base64URL(ASN1_DER_ECDSA_SIGNATURE)
```

**không** tạo JWS ES256 hợp lệ, dù nhìn bên ngoài giống một đoạn Base64URL. Phải lấy raw 64 byte `r||s` (hoặc chuyển DER → raw đúng cách) rồi mới Base64URL không padding.

### 6.1 Dữ liệu được ký trong JWS là “signing input”

Một JWS Compact có ba segment:

```text
base64url(header).base64url(payload).base64url(raw_ECDSA_signature)
```

Signature được tạo trên **ASCII bytes của chuỗi**:

```text
base64url(header) + "." + base64url(payload)
```

chứ không phải ký nguyên văn JSON payload riêng lẻ. Hai đối tượng JSON tương đương ngữ nghĩa nhưng khác thứ tự trường, dấu cách, cách escape hoặc cách Base64URL có thể tạo **signing input khác**.

Việc cấu hình `"alg": "ES256"` trong header không tự chứng minh có thể tin header đó. Khi xác minh JWS, server phải xác định **các thuật toán được phép, khóa tin cậy, issuer/audience/expiry và ngữ cảnh ứng dụng** theo chính sách, không để attacker chọn thuật toán hoặc khóa chỉ bằng các trường header không tin cậy.

### 6.2 Thực hành 3: Java 17 ký đúng JWS ES256 raw P1363

Ví dụ tạo **một signing input JWS** tối giản, ký bằng `SHA256withECDSAinP1363Format` và xác minh đúng bytes. Đây là demo về **encoding và Signature API**, chưa phải một thư viện JWT và không xử lý claims, trust, issuer hoặc expiry cho đăng nhập thực tế.

Tạo **`EcdsaJwsEs256Demo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Base64;

public class EcdsaJwsEs256Demo {
    private static String b64url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = generator.generateKeyPair();

        String header = b64url(
                "{\"alg\":\"ES256\"}".getBytes(StandardCharsets.UTF_8));
        String payload = b64url(
                "{\"sub\":\"demo\"}".getBytes(StandardCharsets.UTF_8));
        byte[] signingInput = (header + "." + payload)
                .getBytes(StandardCharsets.US_ASCII);

        Signature signer =
                Signature.getInstance("SHA256withECDSAinP1363Format");
        signer.initSign(pair.getPrivate());
        signer.update(signingInput);
        byte[] raw = signer.sign();
        String signatureSegment = b64url(raw);

        Signature verify = Signature.getInstance("SHA256withECDSAinP1363Format");
        verify.initVerify(pair.getPublic());
        verify.update(signingInput);
        boolean valid = verify.verify(Base64.getUrlDecoder().decode(signatureSegment));

        Signature changed = Signature.getInstance("SHA256withECDSAinP1363Format");
        changed.initVerify(pair.getPublic());
        changed.update((header + "." + b64url(
                "{\"sub\":\"changed\"}".getBytes(StandardCharsets.UTF_8)))
                .getBytes(StandardCharsets.US_ASCII));
        boolean tamperedValid = changed.verify(raw);

        System.out.println("signature bytes: " + raw.length);
        System.out.println("signature segment chars: " + signatureSegment.length());
        System.out.println("correct input verifies: " + valid);
        System.out.println("changed input verifies: " + tamperedValid);
    }
}
```

Lệnh chạy:

```bash
javac --release 17 EcdsaJwsEs256Demo.java
java EcdsaJwsEs256Demo
```

Đầu ra đã kiểm tra:

```text
signature bytes: 64
signature segment chars: 86
correct input verifies: true
changed input verifies: false
```

Chuỗi `signatureSegment` thực tế thay đổi vì `r,s` thay đổi, nhưng **raw luôn dài 64 byte**, và Base64URL không padding từ 64 byte luôn dài **86 ký tự**. Cấu trúc ký đúng signing input với dấu chấm phân tách hai đoạn mã hóa; sửa payload làm xác minh thất bại.

Trong hệ thống thật, sử dụng **thư viện JOSE/JWT có kiểm thử và chính sách thuật toán/khóa rõ ràng**. Đừng tự viết JWT authorization bằng cách nối chuỗi từ ví dụ này. Ở đây, trọng tâm là: **JOSE ECDSA signature segment = Base64URL(P1363 raw)**.

## 7. ASN.1 DER của chữ ký không phải mọi loại “DER”

Trong Java và PKI, từ “DER” xuất hiện ở nhiều nơi:

| Đối tượng | Ví dụ Java / cấu trúc | Nội dung |
| --- | --- | --- |
| **ECDSA signature value** | `SEQUENCE { INTEGER r, INTEGER s }` | Chỉ hai số của chữ ký |
| **X.509 certificate** | Cấu trúc `Certificate` DER | Chứa TBS certificate, thuật toán ký, `signatureValue` và nhiều trường |
| **X.509 public key (SPKI)** | `publicKey.getEncoded()`, thường `X.509` | Chứa thuật toán/curve và bitstring public key, **không phải chữ ký** |
| **PKCS#8 private key** | `privateKey.getEncoded()` (nếu exportable) | Cấu trúc khóa riêng được mã hóa ASN.1, **không phải chữ ký** |
| **PEM** | Base64 bao quanh DER/khóa/chứng chỉ kèm marker | Cách bọc nội dung, không xác định DER vs P1363 của một chữ ký API |

Ví dụ, khi X.509 certificate mang ECDSA signature, `signatureValue` là **BIT STRING chứa encoding DER của ECDSA-Sig-Value**. Đừng lấy toàn bộ certificate DER hoặc toàn bộ BIT STRING wrapper rồi đưa nguyên cho `Signature.verify(...)` vốn đang chờ chỉ **signature bytes**.

Tương tự, gọi `publicKey.getEncoded()` cho X.509/SPKI chỉ cho byte mã hóa **key**, không có ý nghĩa “signature được mã hóa X.509”. Việc parse signature và việc parse public key phải dùng đúng API khác nhau.

## 8. Curve order, r/s hợp lệ và vấn đề high-S/low-S

### 8.1 Vì sao dùng `order` thay vì độ dài key file?

ECDSA hoạt động trên nhóm điểm có bậc `n`. Hai số chữ ký phải nằm trong miền:

```text
1 <= r < n
1 <= s < n
```

Trong Java, với `ECPublicKey`, đọc:

```java
BigInteger order = ((ECPublicKey) publicKey)
        .getParams().getOrder();
int width = (order.bitLength() + 7) / 8;
```

Đây là **đoạn mã nhúng** trong hàm đã có biến `publicKey` và import `ECPublicKey`/`BigInteger`. Độ dài P1363 được tính bằng **order bit length**, không phải độ dài DER của key hay hash. Với các curve P thường dùng, width trùng với độ dài thường gặp của tọa độ đường cong, nhưng quy tắc đúng là theo miền số `r/s`.

Nếu API đối tác gửi một P1363 raw dài 64 byte nhưng yêu cầu P-384, đừng “bổ sung một ít zero” để ép dùng: phải từ chối sai độ dài và xác nhận rõ curve mà giao thức quy định.

### 8.2 DER canonical encoding khác low-S canonicalization

ECDSA có một dạng **signature malleability**: với chữ ký hợp lệ `(r,s)` theo công thức chuẩn, `(r, n-s)` cũng có thể xác minh thành công, khi `s` nằm trong miền hợp lệ. Một số hệ sinh thái yêu cầu **low-S**, thường `s <= n/2`, nhằm chọn một đại diện duy nhất cho một lớp tương đương toán học.

Cần phân biệt:

- **Canonical DER**: mỗi cặp số `(r,s)` có **một encoding DER chuẩn tắc** (không zero thừa, không length bất chuẩn).
- **Low-S policy**: một ràng buộc **trên giá trị `s`**, không phải cách đặt tag/length của DER.
- **DER ↔ P1363 conversion**: chỉ đổi biểu diễn của **cùng `r,s`**; không tự đổi `s` thành `n-s`.

Đừng tự “normalize low-S” trong bộ chuyển nếu giao thức không quy định. Việc đổi `s` tạo **giá trị chữ ký khác**, dù có thể xác minh cùng message/key; nó có thể ảnh hưởng đối chiếu byte, key attestation, transaction ID hoặc quy tắc canonical hóa của hệ thống khác. Nếu giao thức yêu cầu low-S, xử lý có chủ đích và kiểm thử bằng test vector chính thức.

**Không tái sử dụng nonce bí mật `k` khi ký ECDSA.** Đó là lỗi an toàn khóa riêng nghiêm trọng, độc lập với DER hay P1363. Để crypto provider đáng tin cậy quản lý randomness/deterministic signing; không tự đặt `k` qua ứng dụng. RFC 6979 mô tả deterministic ECDSA; một chữ ký sử dụng deterministic `k` vẫn có thể mã hóa dưới DER hoặc P1363.

## 9. Checklist tích hợp hai hệ thống

Khi một đội Java nhận lỗi “signature invalid” từ hệ thống khác, hỏi theo thứ tự:

1. **Định dạng bytes?** Hợp đồng nhận DER `SEQUENCE(INTEGER r,s)` hay raw `r||s`? Nếu là JOSE ES256, phải raw 64 byte **trước** Base64URL.
2. **Curve?** P-256/P-384/P-521 có đúng không? Kiểm tra key thực tế, không chỉ tên algorithm Java.
3. **Hash?** `SHA256withECDSA` hay SHA384/SHA512 theo giao thức? Không tự hash trước rồi lại đưa vào API có tích hợp hashing.
4. **Dữ liệu ký có trùng byte-for-byte?** JSON whitespace, UTF-8, newline `LF/CRLF`, thứ tự trường, compression, encoding của JWS signing input.
5. **Độ dài raw?** 64/96/132 byte tùy curve; kiểm thử trước khi gọi verify.
6. **DER parser chấp nhận canonical encoding không?** Không có INTEGER âm, leading zero thừa, trailing data, length sai, r/s ngoài miền hợp lệ.
7. **Base64 hay Base64URL?** JWS dùng URL-safe alphabet `-` và `_`, thường không padding; không nhập nhằng với hex/PEM.
8. **Đúng public key?** Kiểm tra key ID, nguồn tin cậy, chuỗi chứng chỉ/metadata/permission; không tin khóa do payload không đáng tin đề xuất.
9. **Chính sách low-S?** Nếu một bên từ chối high-S, phải biết đó là **quy tắc giao thức**, không phải DER parser sai.
10. **Provider/version?** Java 17 support tên P1363 trong chuẩn, nhưng provider đích có cài thuật toán/curve đó không? Log tên thuật toán và provider trong môi trường kiểm thử, không log private key.
11. **Lỗi được xử lý fail closed?** `Signature.verify(...)` có thể trả `false` hoặc ném exception khi encoding sai. Bắt lỗi để **từ chối**, không tự thử nhiều cách không được giao thức cho phép.
12. **Có test vector chia sẻ?** Cả hai bên cần cùng public key, message/signing input, format và signature bytes. Test cả hai chiều, byte đầu có bit dấu, r/s có leading zero, P-521 length long-form và dữ liệu malformed.

### 9.1 Những anti-pattern cần tránh

- **“DER và P1363 đều ECDSA nên byte giống nhau.”** Sai: chúng biểu diễn cùng `r,s` bằng hai cấu trúc khác nhau.
- **“DER P-256 luôn 70/71/72 byte.”** Sai: DER có độ dài biến thiên; không nên hard-code.
- **“Bỏ hai byte đầu DER rồi chia đôi.”** Sai: còn tag INTEGER, length, signed-zero và long-form length.
- **“Cắt leading zero ở raw để chữ ký ngắn hơn.”** Sai: P1363 cần **fixed width**.
- **“Dùng `BigInteger(rawBytes)` là đủ.”** Sai: constructor có dấu có thể đọc số dương thành âm; dùng `BigInteger(1, rawBytes)` và kiểm tra miền.
- **“Chỉ cần `SHA256withECDSA` là ES256.”** Chưa đủ: ES256 buộc **P-256 + SHA-256 + JWS P1363 encoding** và ký đúng signing input.
- **“Base64URL(DER) là P1363.”** Sai: Base64URL chỉ mã hóa văn bản từ byte, không chuyển ASN.1.
- **“Public key trả DER nên chữ ký cũng phải DER.”** Sai: key encoding và signature encoding độc lập.
- **“Đổi format cũng phải ký lại.”** Sai: conversion chính xác không cần private key; chỉ cần `r,s` và curve order để quyết định width/miền.
- **“Low-S là một kiểu DER.”** Sai: low-S giới hạn scalar, DER quy định serialization.
- **“Chữ ký khác byte có nghĩa không hợp lệ.”** ECDSA có thể dùng nonce khác khi ký cùng message/key; hãy **verify**, không chỉ so sánh hai chữ ký sinh ở hai lần ký độc lập.
- **“Verifier lỗi parser nên thử tất cả encodings và chấp nhận kết quả đầu tiên.”** Không nên: phạm vi thuật toán/encoding phải đến từ hợp đồng đáng tin, tránh làm tăng bề mặt diễn giải không mong muốn.

## 10. Bài tập tự kiểm tra

**1.** ECDSA tạo ra hai giá trị nào trước khi serialize?  
**Đáp:** Hai scalar dương `r` và `s` trong miền `1..n-1`.

**2.** Với P-256, một chữ ký P1363 raw dài bao nhiêu?  
**Đáp:** `32 + 32 = 64` byte, dù r/s có bao nhiêu leading zero.

**3.** Vì sao DER có thể thêm byte `00` vào đầu một INTEGER?  
**Đáp:** Để số có bit cao bằng `1` vẫn được đọc là **số dương** theo ASN.1 INTEGER có dấu.

**4.** P-521 dùng mỗi phần `r`/`s` 65 hay 66 byte?  
**Đáp:** `ceil(521/8) = 66` byte; toàn chữ ký raw 132 byte.

**5.** `SHA256withECDSAinP1363Format` khác `SHA256withECDSA` về mặt nào?  
**Đáp:** Chủ yếu **mã hóa output/input chữ ký** P1363 vs DER; cùng primitive hash + ECDSA khi dùng cùng EC key.

**6.** Muốn gửi chữ ký từ Java DER sang JWS ES256, làm thế nào?  
**Đáp:** Parse DER lấy `r,s`, encode hai số unsigned big-endian mỗi số 32 byte, ghép thành raw 64 byte, rồi **Base64URL không padding**.

**7.** Có thể dùng hash SHA-256 với khóa P-384 rồi tự nhận đó là ES384 không?  
**Đáp:** Không. ES384 yêu cầu **P-384 và SHA-384** theo chuẩn JOSE.

**8.** Một verifier có thể phân biệt DER và P1363 chỉ bằng byte đầu `0x30` không?  
**Đáp:** Không đáng tin. P1363 raw cũng có thể bắt đầu `0x30`; phải dựa vào hợp đồng và parse đúng cấu trúc.

**9.** “Canonical DER” có bảo đảm low-S không?  
**Đáp:** Không. DER chuẩn tắc chỉ đảm bảo cách mã hóa duy nhất cho cặp `r,s`; low-S là chính sách giới hạn giá trị `s`.

**10.** Tại sao verify JWS trên raw JSON payload có thể sai?  
**Đáp:** JWS ký trên **ASCII của `base64url(header).base64url(payload)`**, không phải raw JSON.

## Ghi nhớ

Mô hình quan trọng nhất khi tích hợp ECDSA là:

```text
ECDSA math -> (r, s) -> signature encoding -> bytes on wire

ASN.1 DER: SEQUENCE(INTEGER r, INTEGER s), signed-positive/minimal, variable length
IEEE P1363: unsigned fixed-width r || s, length from curve order

Java: SHA256withECDSA  <->  SHA256withECDSAinP1363Format
JWS ES256: P-256 + SHA-256 + raw 64-byte P1363 + Base64URL segment
```

Bằng cách **thống nhất curve, hash, chính xác bytes được ký và encoding chữ ký**, rồi kiểm tra `r,s` và DER canonical tại ranh giới, bạn có thể trao đổi chữ ký giữa Java, thư viện ASN.1 và hệ thống JOSE mà không cần ký lại hoặc thay khóa.

## Nguồn tham khảo chính thức

- [Java 17 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): các tên `SHA256withECDSA` và `...inP1363Format`, cấu trúc chữ ký Java.
- [Java 17 — Signature API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): vòng đời `initSign/update/sign` và `initVerify/update/verify`.
- [Java 17 — Oracle JDK Providers](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): phạm vi hỗ trợ SunEC và hành vi provider.
- [RFC 3279 2.2.3 — ECDSA Signature Algorithm](https://www.rfc-editor.org/rfc/rfc3279#section-2.2.3): ECDSA-Sig-Value là DER `SEQUENCE(r INTEGER, s INTEGER)`.
- [RFC 5759 4.2 — ECDSA signatureValue in X.509](https://www.rfc-editor.org/rfc/rfc5759#section-4.2): INTEGER dương/byte `00` và BIT STRING chứa DER chữ ký.
- [RFC 7518 3.4 — ECDSA for JWS](https://www.rfc-editor.org/rfc/rfc7518#section-3.4): ES256/384/512, byte-width P1363 và JWS signature length.
- [RFC 6979 — Deterministic ECDSA](https://www.rfc-editor.org/rfc/rfc6979): cách sinh nonce ký xác định, độc lập với encoding DER/P1363.
