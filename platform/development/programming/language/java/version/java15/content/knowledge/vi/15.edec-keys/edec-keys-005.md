# EdECPoint: parity của x và tọa độ y trong Java 15+

> **Chủ đề cha: Khóa EdEC.** Từ Java 15 (JEP 339), API `java.security.spec.EdECPoint` biểu diễn điểm công khai dùng trong EdDSA (như Ed25519 và Ed448) bằng **hai thành phần**: tọa độ `y` kiểu `BigInteger` và một cờ `boolean xOdd` cho biết tọa độ `x` là **số lẻ hay chẵn** trong trường hữu hạn. Cách biểu diễn này gắn với kỹ thuật **nén điểm** của RFC 8032, cho phép lưu khóa công khai mà không cần lưu cả `x` và `y`.

Bài tập trung vào API **vẫn còn được hỗ trợ trong Java hiện đại**, dùng chương trình Java 17+ và chỉ rõ những chỗ mã hóa, kiểm tra tính hợp lệ của điểm và xác thực chữ ký là **ba việc khác nhau**.

## 1. Bạn cần hiểu và làm được gì?

Sau khi học, bạn có thể:

1. Mô tả vì sao `EdECPoint` chỉ giữ `y` và **parity của `x`**, thay vì hai tọa độ đầy đủ.
2. Dùng đúng `new EdECPoint(boolean xOdd, BigInteger y)`, `isXOdd()` và `getY()`.
3. Lấy điểm từ `EdECPublicKey.getPoint()` và dựng lại public key bằng `EdECPublicKeySpec`, `NamedParameterSpec` và `KeyFactory`.
4. Hiểu thứ tự byte little-endian, bit cao nhất của byte cuối và sự khác nhau giữa **raw compressed point** của Ed25519/Ed448 và **SubjectPublicKeyInfo (SPKI/X.509)**.
5. Chuyển qua lại giữa raw public-key bytes và `EdECPoint` với kiểm tra kích thước, phạm vi `y` và bit dự trữ.
6. Phân biệt **một object `EdECPoint` được tạo thành công**, **dữ liệu point hợp lệ về toán học** và **public key được tin cậy bởi ứng dụng**.
7. Tránh lỗi xếp nhầm parity, nhầm Ed25519 với X25519, BigInteger có dấu, nhầm encoding hoặc mặc định cho rằng `KeyFactory` luôn kiểm tra mọi trường hợp invalid key.

## 2. Điểm trên Edwards curve có hai tọa độ nhưng mã hóa công khai chỉ cần một cộng một bit

Điểm trên đường cong Edwards được biểu diễn về mặt toán học là `(x, y)` trên trường hữu hạn `F_p`, trong đó `x`, `y` là các phần tử từ `0` đến `p−1`. Với Ed25519:

~~~text
p = 2^255 - 19

Phương trình twisted Edwards (mô tả):
    -x² + y² ≡ 1 + d·x²·y²  (mod p)

Với một giá trị y thích hợp:
    x² ≡ (y² - 1) / (d·y² + 1)  (mod p)
~~~

Phép chia ở đây là **nhân với nghịch đảo modulo `p`**, không phải phép chia số nguyên thông thường. Không phải mọi `y` đều tạo ra một nghiệm `x` hợp lệ. Đối với `y` có nghiệm, thông thường có hai nghiệm `x` và `−x (mod p)`; việc chọn parity giúp xác định đúng nghiệm cần dùng. Ngoại lệ `x=0` chỉ có một nghiệm; bit parity của `x` phải là `0`.

**Quan trọng:** `xOdd` là **bit thấp nhất của giá trị `x` trong khoảng chuẩn `0 ≤ x < p`**:

- `false`: `x` chẵn, bit thấp nhất bằng `0`.
- `true`: `x` lẻ, bit thấp nhất bằng `1`.
- Đây **không phải dấu âm/dương** của một số `BigInteger`.
- Không phải parity của `y` và cũng không có nghĩa `x > 0`.
- Không có method `getX()` trên `EdECPoint`; muốn giải nén đầy đủ phải sử dụng toán học đường cong và bộ kiểm tra phù hợp.

### 2.1. Tại sao một bit là đủ khi điểm hợp lệ?

Với cùng `y`, hai nghiệm `x` và `p−x` có parity đối nhau vì `p` là số nguyên tố lẻ. Chọn bit `xOdd` giúp xác định nghiệm theo quy tắc RFC 8032. Nếu không tồn tại nghiệm modulo `p` thì **không phải điểm hợp lệ**; nếu `x=0` mà `xOdd=true` thì cũng **không có cách giải mã canonical hợp lệ**.

`EdECPoint` lưu **biểu diễn nén ở tầng API** (parity + y); nó **không thực hiện** phép giải nén để cung cấp `x` cho bạn.

### 2.2. So sánh với `java.security.spec.ECPoint`

| Khái niệm | `EdECPoint` | `ECPoint` |
| --- | --- | --- |
| Dùng chính | Edwards curves theo RFC 8032/EdDSA | Weierstrass curves trong API EC truyền thống |
| Thành phần dữ liệu | `boolean xOdd` + `BigInteger y` | `BigInteger x` + `BigInteger y` (và biểu diễn điểm vô cực) |
| Hàm lấy tọa độ | `isXOdd()`, `getY()` | `getAffineX()`, `getAffineY()` |
| Tham số đi kèm khi làm key | `NamedParameterSpec.ED25519` / `ED448` | `ECParameterSpec` phù hợp |
| Không thay thế trực tiếp | **Không** | **Không** |

Không ép `EdECPoint` thành `ECPoint`, không dùng `ECPublicKeySpec` cho Ed25519/Ed448 và không giả định thuật toán `EC`/`ECDSA` dùng cùng kiểu hoặc cùng cách mã hóa với `EdDSA`.

## 3. API Java hiện hành liên quan đến `EdECPoint`

### 3.1. Class `EdECPoint`

Khai báo cốt lõi:

~~~java
// Java 15+; đoạn minh họa chưa phải chương trình độc lập.
EdECPoint point = new EdECPoint(xOdd, y);

boolean odd = point.isXOdd();
BigInteger yValue = point.getY();
~~~

- Constructor `EdECPoint(boolean xOdd, BigInteger y)` lưu các giá trị được cung cấp.
- `getY()` trả `BigInteger`, có thể là số lớn hơn kích thước `long`.
- `isXOdd()` trả parity của `x`, không trả toàn bộ tọa độ `x`.
- Nếu `y == null`, constructor ném `NullPointerException`.
- **Constructor không có tham số `curve` hoặc `p`.** Vì vậy, **chỉ tạo được object không chứng minh `y` nằm trong trường của Ed25519/Ed448 hay điểm có thể giải nén**. Tài liệu JDK cho biết các implementation **sử dụng** `EdECPoint` có thể từ chối `y` ngoài `[0,p)`.

### 3.2. Public key mang `EdECPoint`

Sử dụng những API sau:

~~~java
// Đoạn minh họa trong phương thức.
EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
EdECPoint point = publicKey.getPoint();

// Curve/algorithm phải đến từ cấu hình đáng tin cậy:
NamedParameterSpec params = NamedParameterSpec.ED25519;
EdECPublicKeySpec spec = new EdECPublicKeySpec(params, point);

PublicKey reconstructed = KeyFactory.getInstance("Ed25519")
    .generatePublic(spec);
~~~

Các tên lớp:
- `java.security.interfaces.EdECPublicKey`: interface của public key Edwards; `getPoint()` trả `EdECPoint`.
- `java.security.spec.EdECPublicKeySpec`: key specification gồm `NamedParameterSpec` và `EdECPoint`.
- `java.security.spec.NamedParameterSpec.ED25519`, `NamedParameterSpec.ED448`: chỉ rõ curve/nhóm tham số.
- `java.security.KeyFactory`: tạo `PublicKey` từ key spec theo provider.
- `java.security.Signature`: xác minh chữ ký bằng một public key đã có và một thuật toán phù hợp.

Một vài implementation có thể không cung cấp explicit `getParams()` của public key (API cho phép giá trị `null`). Khi đường cong là một điều kiện của protocol, nên chọn `NamedParameterSpec` **từ cấu hình được kiểm soát** thay vì suy luận từ input không tin cậy.

### 3.3. Đặt `EdECPoint` bên cạnh những KeySpec khác

| Thành phần | Dùng để làm gì? | Không phải là |
| --- | --- | --- |
| `EdECPoint` | Biểu diễn parity `x` + tọa độ `y` | Public key hoàn chỉnh có thuật toán/provenance |
| `EdECPublicKeySpec` | Kết hợp curve và point để tạo public key qua `KeyFactory` | Chứng thư danh tính được tin cậy |
| `EdECPublicKey` | Public key do provider cung cấp | Private key |
| `X509EncodedKeySpec` | Container bytes của **SubjectPublicKeyInfo DER**, để tạo public key | Raw compressed 32/57-byte point |
| `EdECPrivateKeySpec` | Mô tả private key seed/params theo API EdEC | Public point; không nên log hoặc công khai |
| `NamedParameterSpec` | Tên tham số như Ed25519/Ed448 | Dữ liệu `y` hoặc “độ dài khóa” chung |

**Nguyên tắc:** Nếu code nhận **raw public key** 32/57 bytes, không đưa chúng thẳng vào `X509EncodedKeySpec`; format đó cần cấu trúc SPKI DER đầy đủ. Ngược lại, `PublicKey.getEncoded()` thường trả SPKI DER chứ không trả raw compressed point.

## 4. Ví dụ 1 — Lấy `EdECPoint` từ khóa sinh mới, dựng lại khóa và verify

Chương trình sinh key pair cho cả Ed25519 và Ed448, lấy `EdECPoint` từ public key, tạo `EdECPublicKeySpec`, tái tạo public key và kiểm tra chữ ký trên cùng dữ liệu.

**Tệp `EdECPointRoundTripDemo.java` — chương trình Java 17+ độc lập:**

~~~java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.EdECPublicKey;
import java.security.spec.EdECPoint;
import java.security.spec.EdECPublicKeySpec;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;

public class EdECPointRoundTripDemo {
    static void run(String algorithm, NamedParameterSpec params)
            throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance(algorithm)
                .generateKeyPair();
        EdECPublicKey original = (EdECPublicKey) pair.getPublic();
        EdECPoint point = original.getPoint();
        EdECPoint rebuiltPoint =
                new EdECPoint(point.isXOdd(), point.getY());
        PublicKey rebuilt = KeyFactory.getInstance(algorithm)
                .generatePublic(new EdECPublicKeySpec(params, rebuiltPoint));

        byte[] message = "EdEC point round trip"
                .getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(rebuilt);
        verifier.update(message);

        System.out.println(algorithm + ".pointParityPreserved=" +
                (point.isXOdd() == rebuiltPoint.isXOdd()));
        System.out.println(algorithm + ".pointYPreserved=" +
                point.getY().equals(rebuiltPoint.getY()));
        System.out.println(algorithm + ".yNonnegative=" +
                (point.getY().compareTo(BigInteger.ZERO) >= 0));
        System.out.println(algorithm + ".spkiEqual=" +
                Arrays.equals(original.getEncoded(), rebuilt.getEncoded()));
        System.out.println(algorithm + ".signatureVerified=" +
                verifier.verify(signature));
    }

    public static void main(String[] args) throws Exception {
        run("Ed25519", NamedParameterSpec.ED25519);
        run("Ed448", NamedParameterSpec.ED448);
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac --release 17 -encoding UTF-8 EdECPointRoundTripDemo.java
java EdECPointRoundTripDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK/JDK 24:**

~~~text
Ed25519.pointParityPreserved=true
Ed25519.pointYPreserved=true
Ed25519.yNonnegative=true
Ed25519.spkiEqual=true
Ed25519.signatureVerified=true
Ed448.pointParityPreserved=true
Ed448.pointYPreserved=true
Ed448.yNonnegative=true
Ed448.spkiEqual=true
Ed448.signatureVerified=true
~~~

Kết quả:
- `pointParityPreserved=true` và `pointYPreserved=true` cho thấy việc lấy `(xOdd, y)` rồi tạo `EdECPoint` mới giữ nguyên dữ liệu point.
- `spkiEqual=true` trong provider đã kiểm thử cho thấy hai public keys được serialize thành SPKI DER giống nhau. Đây là kết quả của **hai public keys cùng curve và cùng point**; với provider khác, cách công bố encoding có thể phụ thuộc hỗ trợ `getEncoded()`, nên không lấy `SPKI byte equality` làm định nghĩa của mọi dạng identity.
- `signatureVerified=true` chứng minh provider tái tạo public key đúng và dùng được để xác minh chữ ký từ private key tương ứng.

**Không in `point.isXOdd()` của key ngẫu nhiên như một stdout cố định**: nó có thể là `true` hoặc `false` ở từng lần sinh khóa. Bài kiểm tra dùng so sánh parity trước và sau, nên output ổn định.

**Không lộ private key:** `pair.getPrivate()` chỉ nằm trong hoạt động ký nội bộ của demo. Trong hệ thống thật, bảo vệ private keys; đừng đưa `getEncoded()` của private key vào log, worksheet, source code hoặc thông điệp gửi cho người nhận.

## 5. Raw compressed encoding theo RFC 8032: parity nằm ở đâu?

RFC 8032 định nghĩa cách encode một public point `(x,y)` bằng **tọa độ `y` theo little-endian**, sau đó đặt bit thấp nhất của `x` vào **bit cao nhất của octet cuối cùng**. Bit cuối ấy chính là dữ liệu boolean `xOdd`.

### 5.1. Bảng Ed25519 và Ed448

| Thuộc tính | Ed25519 | Ed448 |
| --- | --- | --- |
| Field prime `p` | `2^255 − 19` | `2^448 − 2^224 − 1` |
| Độ dài raw compressed point | **32 bytes** | **57 bytes** |
| Phần giá trị `y` | Tối đa 255 bits (`0 ≤ y < p`) | Tối đa 448 bits (`0 ≤ y < p`) |
| Byte order của `y` | Little-endian | Little-endian |
| Parity bit của `x` | Bit 7 của byte thứ **32** (index `31`) | Bit 7 của byte thứ **57** (index `56`) |
| Bit dự trữ ở octet cuối | 7 bit thấp còn lại thuộc `y` | **7 bit thấp của byte index 56 phải bằng 0** |
| Định dạng `PublicKey.getEncoded()` điển hình | DER SPKI, **khác** 32 raw bytes | DER SPKI, **khác** 57 raw bytes |
| Chữ ký EdDSA (không phải public key) | 64 bytes | 114 bytes |

**Điểm dễ nhầm:** Ed448 dùng **57 bytes** vì format chừa **một bit parity** sau phần y; nhưng bản thân `y` vẫn là số dưới `2^448`, vừa trong 56 bytes. Byte index `56` phải là `0x00` hoặc `0x80` đối với public key canonical.

### 5.2. Hình dung bit parity

~~~text
Ed25519: raw[0] ... raw[30] raw[31]
                                 |
                             bit 7 = xOdd
                         bit 0..6 = phần cao của y

Ed448:   raw[0] ... raw[55] raw[56]
                                 |
                             bit 7 = xOdd
                         bit 0..6 = 0 (reserved)

Cả hai:  y được đọc từ các byte theo thứ tự little-endian.
~~~

Trong Java:
- `(raw[raw.length - 1] & 0x80) != 0` đọc parity.
- `raw[last] &= 0x7F` loại bit parity trước khi giải mã `y`.
- Với Ed448, phải bác bỏ dữ liệu có bất kỳ bit nào trong `raw[56] & 0x7F` là `1`.
- `new BigInteger(1, bigEndianYBytes)` đọc `y` **không âm** sau khi đảo thứ tự bytes từ little-endian sang big-endian.

Đừng tạo `BigInteger` trực tiếp bằng `new BigInteger(raw)`: constructor đó dùng **signed, big-endian two's complement**, không phải little-endian không dấu của RFC 8032. Một raw point có bit parity bằng `1` dễ bị hiểu thành số âm nếu bạn làm sai.

### 5.3. Vì sao `isXOdd()` không phải dấu âm của `y`?

Parity `x` được đặt trong **một bit thuộc octet cuối của encoding `y`**, nhưng sau khi tách phải lưu vào **một biến boolean riêng**. Nó không nói gì về `y` lẻ/chẵn. Có thể có hai `EdECPoint` có cùng `y`, khác `xOdd`, tương ứng hai nghiệm `x` đối nhau khi điểm hợp lệ.

Do đó những phép sau **không có ý nghĩa**:

~~~java
// Minh họa logic SAI, không phải chương trình hoàn chỉnh.
boolean xOdd = y.testBit(0);    // Đang đọc bit 0 của y, không phải x!
boolean xOdd2 = y.signum() < 0;  // Đang đọc dấu BigInteger, không phải x!
~~~

Đúng là lấy parity từ byte cuối của **raw compressed encoding**, hoặc từ API `EdECPoint.isXOdd()` nếu đã có object.

## 6. Ví dụ 2 — Mã hóa/giải mã compressed point, kiểm tra bằng vector RFC

Ví dụ minh họa:
1. `decode(curve, raw)`: kiểm độ dài, tách parity, kiểm bit dự trữ Ed448, đảo endian, đọc `y` và kiểm `0 ≤ y < p`; tạo `EdECPoint`.
2. `encode(curve, point)`: kiểm `y` thuộc trường, ghi bytes little-endian và chèn parity vào bit cao nhất byte cuối.
3. Dùng **public key Ed25519 và signature của RFC 8032** để kiểm tra vector chuẩn với **message rỗng** (không cần private key).
4. Sinh một Ed448 key pair, encode/decode raw public key, tạo `PublicKey` từ point và xác minh chữ ký.
5. Chứng minh decoder từ chối `y = p` (non-canonical) và Ed448 octet cuối có bit dự trữ.

**Giới hạn quan trọng:** Code kiểm *hình thức encoding* và *phạm vi y*, **không tự giải phương trình đường cong, kiểm subgroup hay thay thế bộ kiểm tra chữ ký**. Với input không tin cậy, dùng các API/provider và protocol crypto có kiểm tra cần thiết, không tự coi `new EdECPoint(...)` là “public key đã được xác thực”.

### 6.1. Mã Java 17+ độc lập — `EdECCompressedPointDemo.java`

~~~java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.EdECPoint;
import java.security.spec.EdECPublicKeySpec;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import java.util.HexFormat;

public class EdECCompressedPointDemo {
    static BigInteger prime(String curve) {
        return switch (curve) {
            case "Ed25519" -> BigInteger.ONE.shiftLeft(255)
                    .subtract(BigInteger.valueOf(19));
            case "Ed448" -> BigInteger.ONE.shiftLeft(448)
                    .subtract(BigInteger.ONE.shiftLeft(224))
                    .subtract(BigInteger.ONE);
            default -> throw new IllegalArgumentException("Unsupported curve");
        };
    }

    static int size(String curve) {
        return switch (curve) {
            case "Ed25519" -> 32;
            case "Ed448" -> 57;
            default -> throw new IllegalArgumentException("Unsupported curve");
        };
    }

    static EdECPoint decode(String curve, byte[] raw) {
        int n = size(curve);
        if (raw.length != n) {
            throw new IllegalArgumentException("Wrong raw point length");
        }
        byte[] work = raw.clone();
        boolean xOdd = (work[n - 1] & 0x80) != 0;
        work[n - 1] &= 0x7f;

        if (curve.equals("Ed448") && work[n - 1] != 0) {
            throw new IllegalArgumentException("Ed448 unused bits set");
        }

        byte[] bigEndian = new byte[n];
        for (int i = 0; i < n; i++) {
            bigEndian[n - 1 - i] = work[i];
        }

        BigInteger y = new BigInteger(1, bigEndian);
        if (y.compareTo(prime(curve)) >= 0) {
            throw new IllegalArgumentException("Non-canonical y");
        }
        return new EdECPoint(xOdd, y);
    }

    static byte[] encode(String curve, EdECPoint point) {
        int n = size(curve);
        BigInteger y = point.getY();
        if (y.signum() < 0 || y.compareTo(prime(curve)) >= 0) {
            throw new IllegalArgumentException("y out of field");
        }

        byte[] bigEndian = y.toByteArray();
        byte[] raw = new byte[n];
        for (int i = 0; i < n && i < bigEndian.length; i++) {
            raw[i] = bigEndian[bigEndian.length - 1 - i];
        }

        if (point.isXOdd()) {
            raw[n - 1] |= (byte) 0x80;
        }
        return raw;
    }

    static void testEd25519Vector() throws Exception {
        byte[] raw = HexFormat.of().parseHex(
            "d75a980182b10ab7d54bfed3c964073" +
            "a0ee172f3daa62325af021a68f707511a");
        byte[] signature = HexFormat.of().parseHex(
            "e5564300c360ac729086e2cc806e828a" +
            "84877f1eb8e5d974d873e06522490155" +
            "5fb8821590a33bacc61e39701cf9b46b" +
            "d25bf5f0595bbe24655141438e7a100b");

        EdECPoint point = decode("Ed25519", raw);
        PublicKey key = KeyFactory.getInstance("Ed25519").generatePublic(
            new EdECPublicKeySpec(NamedParameterSpec.ED25519, point));

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(new byte[0]);

        System.out.println("ed25519.rawBytes=" + raw.length);
        System.out.println("ed25519.xOdd=" + point.isXOdd());
        System.out.println("ed25519.yInField=" +
                (point.getY().signum() >= 0 &&
                 point.getY().compareTo(prime("Ed25519")) < 0));
        System.out.println("ed25519.rawReencodedEqual=" +
                Arrays.equals(raw, encode("Ed25519", point)));
        System.out.println("ed25519.rfc8032SignatureValid=" +
                verifier.verify(signature));
        System.out.println("ed25519.spkiBytes=" + key.getEncoded().length);

        byte[] noncanonical = encode("Ed25519",
                new EdECPoint(false,
                    prime("Ed25519").subtract(BigInteger.ONE)));
        noncanonical[0]++;
        try {
            decode("Ed25519", noncanonical);
            System.out.println("ed25519.noncanonicalRejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("ed25519.noncanonicalRejected=true");
        }
    }

    static void testEd448RoundTrip() throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance("Ed448").generateKeyPair();
        java.security.interfaces.EdECPublicKey key =
                (java.security.interfaces.EdECPublicKey) pair.getPublic();

        byte[] raw = encode("Ed448", key.getPoint());
        EdECPoint decoded = decode("Ed448", raw);
        PublicKey rebuilt = KeyFactory.getInstance("Ed448").generatePublic(
                new EdECPublicKeySpec(NamedParameterSpec.ED448, decoded));

        byte[] message = "Ed448 raw point encoding"
                .getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed448");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] sig = signer.sign();

        Signature verifier = Signature.getInstance("Ed448");
        verifier.initVerify(rebuilt);
        verifier.update(message);

        System.out.println("ed448.rawBytes=" + raw.length);
        System.out.println("ed448.lastByteOnlySignBit=" +
                ((raw[56] & 0x7f) == 0));
        System.out.println("ed448.sameY=" +
                key.getPoint().getY().equals(decoded.getY()));
        System.out.println("ed448.sameParity=" +
                (key.getPoint().isXOdd() == decoded.isXOdd()));
        System.out.println("ed448.signatureValid=" +
                verifier.verify(sig));
        System.out.println("ed448.spkiBytes=" +
                rebuilt.getEncoded().length);

        byte[] bad = raw.clone();
        bad[56] |= 0x01;
        try {
            decode("Ed448", bad);
            System.out.println("ed448.unusedBitsRejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("ed448.unusedBitsRejected=true");
        }
    }

    public static void main(String[] args) throws Exception {
        testEd25519Vector();
        testEd448RoundTrip();
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 EdECCompressedPointDemo.java
java EdECCompressedPointDemo
~~~

**Stdout chính xác đã kiểm chứng với JDK 24 và provider mặc định:**

~~~text
ed25519.rawBytes=32
ed25519.xOdd=false
ed25519.yInField=true
ed25519.rawReencodedEqual=true
ed25519.rfc8032SignatureValid=true
ed25519.spkiBytes=44
ed25519.noncanonicalRejected=true
ed448.rawBytes=57
ed448.lastByteOnlySignBit=true
ed448.sameY=true
ed448.sameParity=true
ed448.signatureValid=true
ed448.spkiBytes=69
ed448.unusedBitsRejected=true
~~~

### 6.2. Vì sao kết quả quan trọng?

**Ed25519 test vector:** Raw public key của RFC 8032 trong ví dụ dài `32 bytes`. Byte cuối là `0x1a`, bit cao nhất bằng `0` nên `xOdd=false`. Chữ ký 64 bytes của RFC trên **thông điệp rỗng** được `Signature("Ed25519")` xác minh thành công với public key dựng lại từ `EdECPoint`. Đây là đối chiếu với nguồn chuẩn độc lập, không chỉ với một cặp khóa do chính demo sinh ra.

**Kiểm y canonical:** `p255 = 2^255−19`. Decoder từ chối `y ≥ p255`. Từ `y=p255−1`, tăng byte thấp nhất tạo `y=p255` (trong ví dụ `noncanonical`), và decoder cố ý báo lỗi. Không được tự `mod p` dữ liệu không canonical rồi âm thầm coi như public key chuẩn.

**Ed448:** Raw point phải có `57 bytes`, trong đó `raw[56] & 0x7f == 0`. Decoder từ chối một byte cuối có bit thấp khác 0. Key tạo lại từ `EdECPoint` vẫn xác minh được chữ ký của private key tương ứng.

**SPKI khác raw:** `key.getEncoded().length` là `44` bytes cho Ed25519 và `69` bytes cho Ed448 trong provider được kiểm thử. Đây là **DER SPKI** có phần mô tả thuật toán và BIT STRING chứa raw point. Đừng kết luận rằng mọi `getEncoded()` của mọi provider nhất định không `null`; hãy kiểm tra format được provider trả về và hợp đồng của protocol. Ở Java/JDK thông dụng, RFC 8410 mô tả SPKI cho EdDSA.

### 6.3. Ba điều mà codec chưa làm

Hàm `decode()` trong ví dụ chỉ kiểm:
1. Độ dài và các bits không được dùng.
2. `0 ≤ y < p`, tức encoding canonical về phần `y`.
3. Tách được bit parity `xOdd` để đưa vào `EdECPoint`.

Nó **không** chứng minh:
- `(xOdd,y)` thật sự có nghiệm `x` hợp lệ theo phương trình đường cong.
- Điểm có order/subgroup phù hợp với quy tắc an toàn của protocol chữ ký.
- Public key là khóa của một signer có danh tính hoặc quyền đáng tin.

Các việc đó cần được xử lý bởi bộ crypto/provider và chính sách tin cậy của ứng dụng. **Không tự thay `Signature.verify()` bằng `decode()`.**

### 6.4. Không nhầm endian và số có dấu

Các bytes raw được mô tả **little-endian**. Trong Java, `BigInteger.toByteArray()` lại cho **two's-complement big-endian**, có thể có một byte `0x00` phía trước để bảo đảm số dương. Vì thế:
- **Decode:** Clone raw, tách parity, đảo endian, dùng `new BigInteger(1, bigEndian)`.
- **Encode:** Kiểm range, lấy `BigInteger.toByteArray()`, đảo từ phía byte cuối về raw little-endian, đệm zero tới 32/57 bytes, chèn bit parity.
- Không lấy trực tiếp `toByteArray()` làm raw EdDSA public key.
- Không cắt hoặc thêm byte tùy tiện nếu protocol đòi đúng `32` hoặc `57` bytes.

## 7. Ranh giới kiểm tra: `EdECPoint` là object mang dữ liệu, không phải giấy chứng nhận điểm hợp lệ

### 7.1. Constructor không biết `p` của Ed25519/Ed448

`new EdECPoint(xOdd, y)` nhận `BigInteger y` nhưng **không nhận `NamedParameterSpec`**. Cùng một số nguyên `y` có thể hợp lệ với đường cong này mà không hợp lệ với đường cong khác. Theo Javadoc, implementation dùng object ấy có thể từ chối số nằm ngoài `[0,p)`; thời điểm kiểm tra không nhất thiết là lúc tạo object.

Đối với điểm Ed25519:
- `p = 2^255−19`; `y=p` không thuộc trường.
- Điểm identity có `(x,y)=(0,1)`. Nếu `y=1` thì `x=0` và **parity phải là chẵn**; `EdECPoint(true, 1)` chỉ là một holder chứa dữ liệu không phù hợp với quy tắc RFC.
- Có `y` nằm trong phạm vi nhưng không có nghiệm `x` trên đường cong; range-check chưa đủ.
- Có điểm hợp lệ trên đường cong nhưng protocol verification cần thêm các quy tắc đặc thù về subgroup/order.

### 7.2. Ví dụ 3 — Object vẫn tạo được với dữ liệu không hợp lệ

**Tệp `EdECPointValidationBoundaryDemo.java` — chạy trên Java 17+:**

~~~java
import java.math.BigInteger;
import java.security.spec.EdECPoint;

public class EdECPointValidationBoundaryDemo {
    public static void main(String[] args) {
        BigInteger p255 = BigInteger.ONE.shiftLeft(255)
                .subtract(BigInteger.valueOf(19));

        EdECPoint notCanonical =
                new EdECPoint(false, p255);
        EdECPoint inconsistentParity =
                new EdECPoint(true, BigInteger.ONE);

        System.out.println("holderAcceptsYEqualsP=" +
                notCanonical.getY().equals(p255));
        System.out.println("holderAcceptsOddAtYOne=" +
                inconsistentParity.isXOdd());

        try {
            new EdECPoint(false, null);
            System.out.println("nullYRejected=false");
        } catch (NullPointerException expected) {
            System.out.println("nullYRejected=true");
        }

        EdECPoint otherParity = new EdECPoint(
                !inconsistentParity.isXOdd(),
                inconsistentParity.getY());
        System.out.println("sameYDifferentParity=" +
                (otherParity.getY().equals(inconsistentParity.getY())
                && otherParity.isXOdd() != inconsistentParity.isXOdd()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 EdECPointValidationBoundaryDemo.java
java EdECPointValidationBoundaryDemo
~~~

**Stdout:**

~~~text
holderAcceptsYEqualsP=true
holderAcceptsOddAtYOne=true
nullYRejected=true
sameYDifferentParity=true
~~~

Phân tích:
- `holderAcceptsYEqualsP=true` **không** có nghĩa `y=p` hợp lệ trên Ed25519; chỉ có nghĩa constructor `EdECPoint` đã cất số đó.
- `holderAcceptsOddAtYOne=true` **không** chứng minh `(xOdd=true,y=1)` có điểm Ed25519 hợp lệ (với identity, `x=0` nên parity phải `false`).
- `nullYRejected=true` là kiểm tra đối số được Javadoc công bố.
- `sameYDifferentParity=true` nhắc rằng `getY()` có thể giống hệt trong hai object nhưng cờ `isXOdd()` khác nhau. Đừng kiểm khóa chỉ bằng `y`.

**Ghi chú provider:** Trong JDK/crypto provider, `KeyFactory.generatePublic()` có thể chấp nhận một cấu trúc key spec và chỉ phát hiện vấn đề khi init/verify, hoặc ném exception sớm. **Không dựa vào thứ tự/lớp exception cụ thể từ provider để coi một public point không hợp lệ là đã được chấp nhận.** Phần mềm xử lý input không tin cậy phải dùng hợp đồng validation của protocol và crypto implementation đã được kiểm định.

## 8. Dấu parity `x` có tương đương dấu của nghiệm `x` không?

Trong trường hữu hạn `F_p`, “dương/âm” không hoạt động như số thực. Hai nghiệm của `x²` là `x` và `−x mod p`; RFC 8032 dùng **bit thấp nhất của biểu diễn chuẩn `x`** để lựa chọn. Vì `p` lẻ, hai nghiệm đối nhau có parity khác nhau (trừ `x=0`).

Vì vậy:
- `xOdd=true` nghĩa là integer chuẩn của `x` **lẻ**, không phải tọa độ `x` âm theo số nguyên thông thường.
- Đừng suy ra `x` bằng `BigInteger x = point.isXOdd() ? BigInteger.ONE : BigInteger.ZERO`; đó không phải phép giải nén.
- Đừng lấy `point.getY().testBit(0)` rồi gán thành `xOdd`. `y` có parity riêng và không mã hóa parity `x` trong bit thấp.
- Sau khi chọn nghiệm theo parity, vẫn phải áp dụng điều kiện “điểm tồn tại, hợp lệ với đường cong và quy tắc subgroup” do thuật toán crypto đặt ra.
- Không cần và **không nên** tự viết phép giải nén trên production path chỉ để xác minh chữ ký: dùng `Signature`/provider phù hợp.

Một key kiểm tra chữ ký không thể được xác thực bằng cách nhìn `xOdd` hoặc `y` riêng rẽ. Nó chỉ là dữ liệu công khai cấu thành một point.

## 9. Chọn đúng curve: Ed25519 khác Ed448 và cũng khác X25519

### 9.1. Ed25519 và Ed448

`EdECPoint` không biết curve vì constructor không có tham số `NamedParameterSpec`. Khi tạo public key, bạn phải kết hợp:
- Ed25519: `new EdECPublicKeySpec(NamedParameterSpec.ED25519, point)`.
- Ed448: `new EdECPublicKeySpec(NamedParameterSpec.ED448, point)`.

Không thể lấy raw 32-byte Ed25519 rồi diễn giải là Ed448: độ dài/field/curve khác nhau. Không có quy tắc “cứ cùng `xOdd` và `y` thì là cùng key”.

### 9.2. Ed25519 không phải X25519

Ed25519/Ed448 là **EdDSA signature algorithms**. X25519/X448 thường được dùng cho **key agreement** (XDH); chúng không dùng `EdECPoint`/`EdECPublicKeySpec` và không có cùng định dạng public key/protocol.

| Chủ đề | Ed25519/Ed448 | X25519/X448 |
| --- | --- | --- |
| Nhiệm vụ thường gặp | Digital signatures | Key agreement |
| Điểm công khai trong API | `EdECPoint` (y + x parity) | `XECPublicKey`, `XECPublicKeySpec` (u coordinate) |
| KeyFactory | `"Ed25519"` / `"Ed448"` | `"X25519"` / `"X448"` |
| Chữ ký | `Signature.getInstance("Ed25519"/"Ed448")` | Không phải EdDSA Signature |

Tên đường cong liên quan về mặt toán học không khiến keys/bytes có thể thay thế an toàn cho nhau. Chỉ chuyển khóa giữa các thuật toán khi có protocol và phương pháp đã được đánh giá riêng, **không đổi tên thuật toán**.

## 10. Raw public key và SPKI/X.509 không cùng lớp dữ liệu

Một lời gọi:

~~~java
// Đoạn minh họa trong phương thức.
byte[] encoded = publicKey.getEncoded();
~~~

thường trả về **DER SubjectPublicKeyInfo** (`X.509`) trên các provider phổ biến. RFC 8410 quy định SPKI Ed25519/Ed448 gồm:
- Thuật toán và OID: Ed25519 `1.3.101.112`; Ed448 `1.3.101.113`.
- Một BIT STRING chứa raw compressed public point.
- AlgorithmIdentifier parameters **absent** theo RFC 8410.

Vì thế:
- **Raw Ed25519 point:** 32 bytes, byte cuối high bit là parity `x`.
- **Raw Ed448 point:** 57 bytes, byte cuối chỉ dành high bit parity và 7 bit thấp bằng zero.
- **SPKI Ed25519:** cấu trúc DER bao quanh raw point, demo ra 44 bytes.
- **SPKI Ed448:** cấu trúc DER bao quanh raw point, demo ra 69 bytes.

**Không tự lấy “32 byte cuối” hoặc “57 byte cuối” của bất kỳ DER SPKI không được kiểm tra** làm key. Nếu dữ liệu đầu vào là SPKI, dùng `KeyFactory.getInstance(curve).generatePublic(new X509EncodedKeySpec(spkiBytes))` để parse cấu trúc đúng chuẩn; còn nếu là raw bytes, decode theo protocol rõ ràng rồi dựng `EdECPublicKeySpec` hoặc dùng API thư viện chuyên dụng.

Nhầm lẫn hai format có thể gây lỗi `InvalidKeySpecException`, sai thuật toán, silently-misinterpreted input ở hệ thống tự parser hoặc vấn đề interoperability. **Không bao giờ** chấp nhận input vì chỉ thấy length/bit pattern giống một key hợp lệ.

## 11. Kiểm tra dữ liệu không tin cậy: những lớp cần bảo vệ

Khi tiếp nhận raw public key từ network/file, có ít nhất bốn lớp kiểm tra:

### 11.1. Lớp 1 — Wire format

- Đã biết curve từ protocol/metadata **được phép**, không để attacker downgrade?
- Raw length đúng `32` (Ed25519) hoặc `57` (Ed448)?
- Với Ed448, byte cuối có bit dự trữ bằng 0?
- `y` little-endian được đọc không dấu và canonical `0 ≤ y < p`?
- Có giới hạn size/payload? Không parse một object tùy ý quá lớn.

### 11.2. Lớp 2 — Hợp lệ về toán học và crypto protocol

- Điểm thực sự nằm trên curve?
- Parity có phù hợp với nghiệm `x` không?
- Có quy tắc subgroup/small-order/canonical point encoding cần kiểm?
- Provider có hỗ trợ và thực hiện đúng kiểm tra khóa/chữ ký theo tiêu chuẩn ứng dụng?

**`EdECPoint` constructor** không cung cấp các bảo đảm này. `EdECPublicKeySpec` tự nó cũng chỉ là data holder. Trong đường kiểm tra chữ ký, hãy dựa vào một implementation crypto đáng tin cậy với protocol validation phù hợp.

### 11.3. Lớp 3 — Binding public key với danh tính

Ngay cả một Ed25519 point hợp lệ và chữ ký đúng **không chứng minh** public key đó thuộc về signer mà request tự xưng. Public key phải đến từ trusted registry/pin/đường chứng thư PKIX hợp lệ theo ứng dụng. Đừng tạo trust anchor từ chính raw key request cung cấp.

### 11.4. Lớp 4 — Context, authorization và replay

Ứng dụng vẫn cần kiểm:
- Thông điệp chữ ký trên **đúng bytes** và đúng thuật toán.
- Audience/protocol version/action/resource/expiry/nonce thuộc policy chấp nhận.
- Signer được tin cậy có quyền với action/resource này.
- Replay protection, rotation và key revocation theo điều kiện hệ thống.

`EdECPoint` chỉ giúp **biểu diễn một điểm public key**. Không tự trở thành hệ thống bảo mật toàn phần.

## 12. Lỗi hay gặp và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tưởng `xOdd` là `y` lẻ/chẵn | Tái tạo nhầm điểm, verify không khớp | Lấy từ bit cao nhất của raw byte cuối hoặc `isXOdd()` |
| Tưởng `xOdd` là “`x` âm” như số nguyên dấu | Hiểu sai finite-field encoding | Đó là bit thấp nhất của `x` canonical trong `F_p` |
| Đưa `BigInteger.valueOf(-1)` làm `y` | Giá trị không thuộc `[0,p)` | Check `signum() >= 0` và `compareTo(p) < 0` |
| Dùng `new BigInteger(raw)` trực tiếp | Sai endian và có thể thành số âm | Tách parity, đảo little-endian, `new BigInteger(1, bigEndian)` |
| Dùng `toByteArray()` trực tiếp làm raw key | Big-endian, có dấu và chiều dài biến động | Chuyển về little-endian đúng `32`/`57` bytes, đệm zero |
| Nghĩ Ed25519 point là 31 bytes vì “chỉ có y” | Quên parity và width field | Raw public key cố định **32 bytes** |
| Nghĩ Ed448 point là 56 bytes | Thiếu byte cuối chứa parity | Raw public key cố định **57 bytes** |
| Không kiểm Ed448 7 bit dự trữ | Chấp nhận encoding non-canonical | Yêu cầu `(raw[56] & 0x7f) == 0` |
| Cho `y=p` qua bộ decode | Canonicality bị phá | Reject `y ≥ p`; không tự giảm `mod p` |
| Bật `xOdd` và tin luôn hợp lệ | `x=0` không thể có odd parity; y có thể không có nghiệm | Validation theo RFC/crypto provider |
| Dùng `ECPoint`/`ECPublicKeySpec` | Nhầm Weierstrass và Edwards API | Dùng `EdECPoint`/`EdECPublicKeySpec` |
| Dùng `X25519` thay `Ed25519` | Nhầm key-agreement và signature | Chọn algorithm đúng bằng trusted config |
| Cho raw bytes vào `X509EncodedKeySpec` | Không phải SPKI DER | Dùng `EdECPublicKeySpec` cho point hoặc cung cấp SPKI hợp lệ |
| Tưởng `PublicKey.getEncoded()` là raw point | Nhầm 44/69 bytes với 32/57 bytes | Kiểm format `X.509`/SPKI, parse DER đúng chuẩn |
| Nghĩ `new EdECPoint(...)` kiểm đường cong | Có object không chứng minh key hợp lệ | Xác minh riêng theo crypto protocol/provider |
| Tin key vì ký được một message | Attacker cũng có thể tự ký với key tự tạo | Key phải được ràng buộc danh tính từ nguồn tin cậy |
| In private key seed để debug point | Lộ khóa ký | Chỉ log dữ liệu công khai với chính sách phù hợp |

## 13. Bài tập có đáp án

**Bài 1 — Parity hay dấu?**  
Một `EdECPoint` có `getY() = BigInteger.valueOf(42)` và `isXOdd() = true`. Có thể kết luận `x = -42` hoặc `y` lẻ không?

**Đáp án:** Không. `xOdd=true` chỉ là parity của nghiệm `x`, không phải giá trị/tính âm của `x` hay parity của `y`. `y=42` là chẵn. Chỉ từ cặp data này cũng chưa chứng minh nó có điểm hợp lệ trên curve.

**Bài 2 — Tách byte cuối Ed25519.**  
Raw public point có 32 bytes, byte cuối là `0x9A`. Parity `x` là gì, và phần `y` cao của byte cuối là gì?

**Đáp án:** `0x9A & 0x80 != 0` nên `xOdd=true`. Phần còn lại `0x9A & 0x7F = 0x1A` thuộc `y`. Phải giải mã toàn bộ 32 bytes theo little-endian để nhận `y`.

**Bài 3 — Tách byte cuối Ed448.**  
Byte index `56` của một raw Ed448 public key là `0x81`. Nó có hợp lệ về format canonical không?

**Đáp án:** Không. Parity bit `1` nhưng bit thấp `0x01` trong vùng dự trữ phải bằng `0`. Trường hợp `0x80` mới có hình dạng byte cuối phù hợp; toàn bộ point vẫn phải được kiểm tra thêm.

**Bài 4 — Đọc y bằng `BigInteger`.**  
Vì sao `new BigInteger(raw)` không phải cách đúng để lấy `y` từ raw Ed25519?

**Đáp án:** `BigInteger(byte[])` đọc big-endian có dấu; raw dùng little-endian và chứa parity bit không thuộc `y`. Phải tách bit parity, đảo byte order và dùng `new BigInteger(1, bigEndian)`.

**Bài 5 — Holder vs validation.**  
`new EdECPoint(false, p255)` tạo object thành công. Có được dùng làm Ed25519 public key chuẩn không?

**Đáp án:** Không. `y=p255` vượt miền `[0,p255)`; constructor không chứng minh giá trị hợp lệ. Decoder chuẩn cần reject non-canonical value.

**Bài 6 — Lấy key từ point.**  
Cần ba thành phần/API nào để chuyển một `EdECPoint` thành public key Ed25519 cho JCA?

**Đáp án:** Kết hợp `NamedParameterSpec.ED25519` với `EdECPublicKeySpec`, sau đó `KeyFactory.getInstance("Ed25519").generatePublic(spec)`. Cần xử lý lỗi key spec/provider và xác thực nguồn dữ liệu.

**Bài 7 — Raw vs SPKI.**  
Vì sao một DER SPKI Ed25519 có thể dài 44 bytes trong khi raw point Ed25519 chỉ dài 32 bytes?

**Đáp án:** SPKI chứa thêm ASN.1 cấu trúc, algorithm identifier/OID và BIT STRING. Phần raw compressed point bên trong là 32 bytes; hai format không thay thế nhau.

**Bài 8 — Parity flipped.**  
Hai points có cùng `y` nhưng `xOdd` khác nhau. Có thể coi chúng là cùng một public key vì “y giống nhau” không?

**Đáp án:** Không. Parity chọn nghiệm `x`; với điểm hợp lệ (trừ trường hợp đặc biệt), đổi parity chọn điểm khác. Kiểm equality/identity phải xét curve và cả parity, không chỉ `y`.

**Bài 9 — Chữ ký có đúng làm khóa đáng tin?**  
Một attacker gửi raw public key Ed25519 tự tạo cùng chữ ký hợp lệ của message do họ chọn. Server có nên tin họ là service nội bộ không?

**Đáp án:** Không. Cần ràng buộc public key với danh tính từ trust registry/PKIX và kiểm policy riêng. `EdECPoint` chỉ giúp đọc representation của public key.

**Bài 10 — Bản tương thích JDK.**  
Vì sao ví dụ dùng `HexFormat.of()` và biên dịch `--release 17` dù `EdECPoint` xuất hiện từ Java 15?

**Đáp án:** `HexFormat` là API từ Java 17. Bài này chủ động dùng Java 17+ để có mã hiện đại chạy độc lập; `EdECPoint`, `EdECPublicKeySpec` và constants Ed25519/Ed448 đã có từ Java 15 và vẫn tiếp tục được hỗ trợ.

## 14. Tóm tắt cốt lõi

- **`EdECPoint = (xOdd, y)`**: `y` là `BigInteger` trong trường hữu hạn; `xOdd` là parity (bit thấp nhất) của `x`, **không** phải dấu âm/dương hoặc parity của `y`.
- **Không có `getX()`:** Tọa độ `x` được suy ra khi giải nén point theo curve và bit parity; `EdECPoint` không tự giải nén hoặc tự bảo đảm point hợp lệ.
- **Ed25519 raw point = 32 bytes; Ed448 = 57 bytes**, little-endian `y` và parity ở bit cao nhất byte cuối. Ed448 yêu cầu 7 bits thấp của byte cuối bằng 0.
- **Dùng đúng Java API:** `EdECPublicKey.getPoint()`, `EdECPublicKeySpec(NamedParameterSpec, EdECPoint)`, `KeyFactory`. Không dùng nhầm EC/XEC APIs.
- **Phân biệt format:** Raw compressed point không phải SPKI/X.509 DER từ `PublicKey.getEncoded()`.
- **Không coi holder là validation:** Constructor chấp nhận dữ liệu `y` không canonical; cần kiểm format/range/curve/protocol, rồi verify chữ ký bằng provider đáng tin cậy.
- **Đừng nhầm key hợp lệ với key đáng tin:** Danh tính và quyền phải được cấp từ trust policy riêng.

## Tài liệu tham khảo hiện hành

- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA), Java 15](https://openjdk.org/jeps/339)
- [Java SE 25 — `EdECPoint` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPoint.html)
- [Java SE 25 — `EdECPublicKeySpec` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html)
- [Java SE 25 — `EdECPublicKey` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html)
- [Java SE 25 — `NamedParameterSpec`: ED25519, ED448](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html)
- [Java SE 25 — `KeyFactory` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyFactory.html)
- [RFC 8032 — EdDSA, Ed25519/Ed448 point encoding/decoding](https://www.rfc-editor.org/rfc/rfc8032)
- [RFC 8410 — Algorithm identifiers và SubjectPublicKeyInfo cho Ed25519/Ed448](https://www.rfc-editor.org/rfc/rfc8410)
