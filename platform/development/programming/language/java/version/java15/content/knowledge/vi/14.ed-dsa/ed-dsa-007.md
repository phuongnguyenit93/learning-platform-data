# Tên thuật toán chuẩn cho KeyPairGenerator, KeyFactory và Signature: EdDSA trong Java 15+

## 1. Mục tiêu

**EdDSA (Edwards-Curve Digital Signature Algorithm)** là họ thuật toán **chữ ký số** được mô tả trong **RFC 8032**, trong đó hai lựa chọn phổ biến và được Java hỗ trợ là **Ed25519** và **Ed448**. Từ **Java 15**, JDK cung cấp triển khai EdDSA tiêu chuẩn qua kiến trúc **Java Cryptography Architecture (JCA)**. Các API và tên thuật toán này **vẫn còn được sử dụng trong Java hiện đại**, không phải tính năng preview hay giải pháp legacy.

Trong Java, tên truyền vào `getInstance(...)` không phải tên class Java, không phải đường cong ECDH và cũng không phải tên thuật toán băm riêng lẻ. Đó là **standard algorithm name** dùng để yêu cầu một dịch vụ mật mã phù hợp từ các **security providers** đã đăng ký.

Sau bài này, bạn có thể:

1. Kể đúng **ba tên chuẩn `EdDSA`, `Ed25519`, `Ed448`** cho **cả** `KeyPairGenerator`, `KeyFactory` và `Signature`.
2. Chọn tên **cụ thể theo đường cong** hay tên **tổng quát theo họ** có chủ đích.
3. Biết ba dịch vụ có trách nhiệm khác nhau, không thay thế lẫn nhau.
4. Chọn đường cong bằng `NamedParameterSpec.ED25519` hoặc `NamedParameterSpec.ED448` khi dùng `KeyPairGenerator.getInstance("EdDSA")`.
5. Sinh khóa, mã hóa/khôi phục khóa bằng chuẩn X.509/PKCS#8, ký và xác thực văn bản trong một ví dụ **chạy được với mức Java 15**.
6. Tránh nhầm EdDSA với ECDSA hoặc X25519/X448, nhầm tên chuẩn với hỗ trợ của provider, hay để lộ private key.

## 2. Bảng tên thuật toán chuẩn quan trọng nhất

Theo tài liệu **Java Security Standard Algorithm Names** của Java SE 15 và các bản Java hiện đại, **cùng ba tên** sau có trong từng nhóm dịch vụ:

| Tên chuẩn (`getInstance(...)`) | `KeyPairGenerator` | `KeyFactory` | `Signature` | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `EdDSA` | Có | Có | Có | **Họ** chữ ký Edwards-Curve theo RFC 8032, có thể sử dụng các tham số/khóa thuộc Ed25519 hoặc Ed448 tùy triển khai |
| `Ed25519` | Có | Có | Có | Chọn **Ed25519**, đường cong và biến thể chữ ký tương ứng |
| `Ed448` | Có | Có | Có | Chọn **Ed448**, đường cong và biến thể chữ ký tương ứng |

Ba tên phải ghi nhớ chính xác là:

```java
"EdDSA"
"Ed25519"
"Ed448"
```

Đây là **ba literal minh họa**, không phải ba câu lệnh có thể đặt trực tiếp trong một class. Tài liệu chuẩn quy định tên thuật toán JCA **không phân biệt chữ hoa/chữ thường** khi tra cứu, nhưng trong mã nguồn và cấu hình nên **dùng cách viết chuẩn** ở bảng để thuận tiện đọc, tra tài liệu và gỡ lỗi.

Các lệnh yêu cầu engine cho ba dịch vụ:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyFactory factory = KeyFactory.getInstance("Ed25519");
Signature signature = Signature.getInstance("Ed25519");
```

Đoạn này chỉ minh họa API; đặt vào một phương thức có import `java.security.*` và xử lý `GeneralSecurityException`. Nếu muốn dùng Ed448, thay **cùng lúc** cả ba tên bằng `"Ed448"`. Nếu muốn engine tổng quát của họ, chọn `"EdDSA"` và bảo đảm các key/parameter thực tế thuộc đường cong bạn định sử dụng.

**Lưu ý có tính triển khai:** một cái tên thuộc danh sách **standard names** không có nghĩa **mọi provider** đều hiện thực nó. `getInstance(...)` tìm trong các provider có sẵn và có thể ném `NoSuchAlgorithmException`. JDK với provider **SunEC** thông thường có triển khai EdDSA cho cả Ed25519 và Ed448, nhưng trong sản phẩm phải kiểm tra JDK, provider được cài, cấu hình và các chế độ bảo mật đang dùng.

## 3. Ba API có ba trách nhiệm khác nhau

### 3.1. `KeyPairGenerator` — tạo cặp khóa

`KeyPairGenerator` sinh một cặp khóa bất đối xứng gồm:

- **`PrivateKey`**: dùng để **ký**; phải được bảo vệ như bí mật.
- **`PublicKey`**: dùng để **xác minh chữ ký**; có thể phân phối theo giao thức nhưng vẫn cần biết **khóa đó thuộc về ai**.

Ví dụ khi quyết định rõ Ed25519:

```java
KeyPairGenerator kpg = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = kpg.generateKeyPair();

PrivateKey privateKey = pair.getPrivate();
PublicKey publicKey = pair.getPublic();
```

Dùng `"Ed448"` nếu yêu cầu một cặp Ed448. Mỗi lần sinh thông thường tạo khóa khác nhau, nên **không cố định giá trị byte của cặp khóa** hay chữ ký làm expected output trong bài test.

### 3.2. `KeyFactory` — chuyển đổi giữa khóa và biểu diễn khóa

`KeyFactory` **không** phải công cụ sinh cặp khóa ngẫu nhiên. Nó chuyển đổi một khóa từ/đến **`KeySpec`**, chẳng hạn:

- `X509EncodedKeySpec`: đọc **SubjectPublicKeyInfo** theo X.509, thường dùng cho **public key**.
- `PKCS8EncodedKeySpec`: đọc encoding **PKCS#8** của **private key**.
- Các specification dạng EdEC như `EdECPublicKeySpec` và `EdECPrivateKeySpec` cho trường hợp giao thức có dữ liệu khóa dạng tham số riêng, **khác** với DER X.509/PKCS#8.

Ví dụ:

```java
KeyFactory factory = KeyFactory.getInstance("Ed25519");

PublicKey restoredPublic = factory.generatePublic(
        new X509EncodedKeySpec(publicKey.getEncoded()));

PrivateKey restoredPrivate = factory.generatePrivate(
        new PKCS8EncodedKeySpec(privateKey.getEncoded()));
```

Đây là **đoạn minh họa**, giả định `publicKey` và `privateKey` đã tồn tại và có encoding xuất được. Chú ý `getEncoded()` của một khóa gắn với HSM, token hoặc một provider đặc biệt **có thể trả `null`** hoặc không cho export. Không mặc nhiên coi mọi `Key` đều có thể xuất private bytes.

**Không nhầm encoding với kích thước khóa thô:** public key Ed25519 có thành phần khóa 32 byte, nhưng kết quả `getEncoded()` của `PublicKey` theo `X.509` chứa cả metadata/ASN.1, nên **không phải chỉ 32 byte**. Tương tự, private key PKCS#8 không phải chuỗi private seed trần. Không đưa trực tiếp raw bytes vào `X509EncodedKeySpec` hoặc `PKCS8EncodedKeySpec` khi giao thức của bạn không cung cấp đúng định dạng đó.

### 3.3. `Signature` — ký và xác minh thông điệp

`Signature` thực hiện phép **chữ ký số**, không phải encryption:

```java
byte[] message = "Hello EdDSA"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(message);
byte[] signatureBytes = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(message);
boolean valid = verifier.verify(signatureBytes);
```

Đây là **đoạn minh họa**, cần có `privateKey`/`publicKey` đúng loại. `update(...)` đưa **byte thông điệp thực tế** vào engine, `sign()` trả chữ ký dưới dạng `byte[]`, `verify(...)` kiểm tra chữ ký với public key đã chọn và các byte thông điệp tương ứng.

**Không tự gọi `MessageDigest.getInstance("SHA-512")` rồi ký digest** nếu giao thức yêu cầu Ed25519/Ed448 **thuần** theo RFC 8032. EdDSA xử lý hash bên trong thuật toán và có các chế độ prehash/context riêng; tự băm input rồi ký sẽ là **ký một thông điệp khác**, không tương đương với chế độ Ed25519ph hay Ed448ph.

## 4. Tên tổng quát `EdDSA` và tên cụ thể `Ed25519`/`Ed448`

### Khi chọn tên cụ thể

Nếu hợp đồng giao thức ghi **Ed25519**, ưu tiên:

```java
KeyPairGenerator.getInstance("Ed25519");
KeyFactory.getInstance("Ed25519");
Signature.getInstance("Ed25519");
```

Nếu ghi **Ed448**, ưu tiên:

```java
KeyPairGenerator.getInstance("Ed448");
KeyFactory.getInstance("Ed448");
Signature.getInstance("Ed448");
```

Đây là những **lời gọi minh họa**; code chạy thực tế phải dùng kết quả, đặt trong một method và xử lý exception. Việc chọn tên cụ thể làm rõ **đường cong và chế độ chữ ký** được yêu cầu. Dữ liệu khóa, chữ ký và metadata giao thức cũng phải khớp với lựa chọn ấy.

### Khi chọn tên tổng quát `EdDSA`

Tên `EdDSA` chỉ **họ thuật toán**. Nếu cần sinh một cặp theo một đường cong xác định, dùng `NamedParameterSpec`:

```java
KeyPairGenerator kpg = KeyPairGenerator.getInstance("EdDSA");
kpg.initialize(NamedParameterSpec.ED25519);
KeyPair pair = kpg.generateKeyPair();
```

Hoặc:

```java
KeyPairGenerator kpg = KeyPairGenerator.getInstance("EdDSA");
kpg.initialize(NamedParameterSpec.ED448);
KeyPair pair = kpg.generateKeyPair();
```

`NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448` là các hằng có từ **Java 15**. Mặc dù chúng biểu diễn tham số curve, tên của hằng **viết hoa toàn bộ phần `ED`**; trái lại string chuẩn để gọi `getInstance` vẫn là `"Ed25519"` và `"Ed448"`.

Nếu gọi `KeyPairGenerator.getInstance("EdDSA").generateKeyPair()` mà **không** chọn tham số, đường cong mặc định có thể là **quyết định của provider** (SunEC thường mặc định Ed25519). Trong mã cần tương tác chuẩn giao thức, **đừng ngầm phụ thuộc mặc định**: hãy chỉ định `NamedParameterSpec` hoặc chọn tên cụ thể.

`Signature.getInstance("EdDSA")` có thể sử dụng key Ed25519 hoặc Ed448 theo hỗ trợ của provider và tham số thực tế. Nếu dùng `EdDSA` cùng `KeyFactory`, dữ liệu khóa mã hóa `X.509`/`PKCS#8` mang thông tin thuật toán/đường cong giúp provider xây dựng đúng key. **Không suy luận rằng tên `EdDSA` có nghĩa là Ed25519 trong mọi hoàn cảnh**.

### Bảng lựa chọn thực hành

| Trường hợp | Cách chọn gợi ý | Lý do |
| --- | --- | --- |
| API yêu cầu chữ ký Ed25519 cố định | Cả 3 service dùng `"Ed25519"` | Thể hiện chính xác hợp đồng |
| API yêu cầu Ed448 | Cả 3 service dùng `"Ed448"` | Không vô tình sinh/chấp nhận đường cong khác |
| Framework hỗ trợ nhiều curve theo cấu hình | `"EdDSA"` + `NamedParameterSpec` + kiểm tra key/protocol | Tách family khỏi curve |
| Nhập DER của Ed25519 và muốn dùng factory theo curve | `KeyFactory.getInstance("Ed25519")` | Dễ kiểm soát lỗi mismatch |
| Nhập DER của Ed25519 **hoặc** Ed448 | Có thể dùng `KeyFactory.getInstance("EdDSA")` | Nhà cung cấp giải mã theo encoding/thuộc tính khóa |
| Cần xác thực thông điệp và chữ ký | `Signature` với public key và message bytes | Không cần `Cipher` |
| Muốn tạo shared secret | **Không dùng EdDSA**; xem XDH/X25519/X448 | Đó là **key agreement**, không phải chữ ký số |

## 5. Ed25519 và Ed448 khác nhau ra sao?

Cả hai đều là các biến thể của EdDSA thuộc RFC 8032, nhưng **không thể hoán đổi khóa/chữ ký**:

| Đặc tính | Ed25519 | Ed448 |
| --- | --- | --- |
| Tên chuẩn JCA | `Ed25519` | `Ed448` |
| Tên tham số trong `NamedParameterSpec` | `ED25519` | `ED448` |
| Độ dài chữ ký ở chế độ thông thường | **64 byte** | **114 byte** |
| Kích thước public key dạng point encoding của RFC 8032 | **32 byte** | **57 byte** |
| Kích thước private seed dạng RFC 8032 | **32 byte** | **57 byte** |
| Hash nội bộ của biến thể cơ bản | SHA-512 | SHAKE256 |
| Có thể xác minh chữ ký của biến thể còn lại? | **Không** | **Không** |

Các độ dài public point/private seed ở đây nói về **biểu diễn thuật toán trong RFC 8032**, **không** phải độ dài của `PublicKey.getEncoded()` (X.509 DER) hay `PrivateKey.getEncoded()` (PKCS#8 DER), vốn có cấu trúc phụ.

`Ed25519` thường được chọn khi cần chữ ký tương đối ngắn và hiệu năng thực tế; `Ed448` có mức bảo mật cao hơn với chữ ký dài hơn. Việc chọn thuật toán phải dựa trên **giao thức, khả năng tương tác và yêu cầu bảo mật** của hệ thống, không phải chỉ chạy benchmark một lần.

**EdDSA không đồng nghĩa ECDSA:** `EC` và những tên `SHA256withECDSA` thuộc hệ ECDSA; không dùng khóa Ed25519 như khóa `EC` thông thường cho `SHA256withECDSA`.

**EdDSA không đồng nghĩa XDH:** `X25519` và `X448` là tên cho **Diffie-Hellman key agreement** (RFC 7748), sử dụng nhóm phép toán khác với chữ ký EdDSA (RFC 8032). Không đổi `"Ed25519"` thành `"X25519"` chỉ vì đều thấy con số 25519. Việc chuyển đổi khóa giữa hai hệ không thuộc luồng API chữ ký cơ bản này, không nên tự thực hiện.

## 6. Ví dụ hoàn chỉnh: kiểm tra đủ ba tên cho đủ ba service

Ví dụ này sử dụng **hai tên cụ thể** và **tên tổng quát**. Các khóa sinh ngẫu nhiên mỗi lần chạy; chương trình **không in raw key hoặc chữ ký**, chỉ in độ dài chữ ký và kết quả xác thực, vì đây mới là những đầu ra cần kiểm tra.

Tạo file **`EdDsaStandardNamesDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.NamedParameterSpec;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

public class EdDsaStandardNamesDemo {

    private static void specific(String algorithm, byte[] message)
            throws GeneralSecurityException {

        // The same standard name is valid for all three JCA services.
        KeyPairGenerator generator = KeyPairGenerator.getInstance(algorithm);
        KeyPair generated = generator.generateKeyPair();

        KeyFactory factory = KeyFactory.getInstance(algorithm);
        PublicKey publicKey = factory.generatePublic(
                new X509EncodedKeySpec(generated.getPublic().getEncoded()));
        PrivateKey privateKey = factory.generatePrivate(
                new PKCS8EncodedKeySpec(generated.getPrivate().getEncoded()));

        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(privateKey);
        signer.update(message);
        byte[] bytes = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(publicKey);
        verifier.update(message);
        boolean valid = verifier.verify(bytes);

        // Change the data while retaining the original signature.
        verifier.initVerify(publicKey);
        verifier.update("tampered".getBytes(StandardCharsets.UTF_8));
        boolean modified = verifier.verify(bytes);

        System.out.println(algorithm
                + ": sigBytes=" + bytes.length
                + ", valid=" + valid
                + ", modified=" + modified);
    }

    private static void generic(NamedParameterSpec curve, byte[] message)
            throws GeneralSecurityException {

        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(curve);
        KeyPair generated = generator.generateKeyPair();

        KeyFactory factory = KeyFactory.getInstance("EdDSA");
        PublicKey publicKey = factory.generatePublic(
                new X509EncodedKeySpec(generated.getPublic().getEncoded()));
        PrivateKey privateKey = factory.generatePrivate(
                new PKCS8EncodedKeySpec(generated.getPrivate().getEncoded()));

        Signature signer = Signature.getInstance("EdDSA");
        signer.initSign(privateKey);
        signer.update(message);
        byte[] bytes = signer.sign();

        Signature verifier = Signature.getInstance("EdDSA");
        verifier.initVerify(publicKey);
        verifier.update(message);
        boolean valid = verifier.verify(bytes);

        System.out.println("EdDSA(" + curve.getName()
                + "): sigBytes=" + bytes.length
                + ", valid=" + valid);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        byte[] message = "Hello EdDSA".getBytes(StandardCharsets.UTF_8);

        specific("Ed25519", message);
        specific("Ed448", message);

        generic(NamedParameterSpec.ED25519, message);
        generic(NamedParameterSpec.ED448, message);
    }
}
```

### Biên dịch và chạy

Tại thư mục chứa file, dùng JDK với `javac` hỗ trợ `--release 15` (ví dụ bản JDK hiện đại còn được hỗ trợ). Có thể biên dịch Java 15-compatible bytecode rồi chạy bằng JVM hỗ trợ:

```bash
javac --release 15 -encoding UTF-8 EdDsaStandardNamesDemo.java
java EdDsaStandardNamesDemo
```

**Stdout kỳ vọng với JDK cung cấp triển khai EdDSA/Ed25519/Ed448 như SunEC:**

```text
Ed25519: sigBytes=64, valid=true, modified=false
Ed448: sigBytes=114, valid=true, modified=false
EdDSA(Ed25519): sigBytes=64, valid=true
EdDSA(Ed448): sigBytes=114, valid=true
```

Tất cả giá trị `valid=true` minh họa ký và xác minh thành công với **cùng khóa và cùng byte thông điệp**. `modified=false` chứng tỏ chữ ký cũ không hợp lệ cho thông điệp `"tampered"` khác với `"Hello EdDSA"`. Khi chạy trên provider/JVM khác, hỗ trợ thuật toán hoặc encoding có thể khác; nếu tên không có trong provider đã đăng ký, chương trình báo lỗi `NoSuchAlgorithmException` thay vì các dòng trên.

### Giải thích cấu trúc code

1. `KeyPairGenerator` sinh cặp khóa theo **tên JCA**. Tên `Ed25519`/`Ed448` trong `specific` cố định đường cong.
2. `KeyFactory` **nhận lại khóa** từ encoded representations. `X509EncodedKeySpec` là cho public key; `PKCS8EncodedKeySpec` cho private key. Đây là bước round-trip hữu ích để hiểu trách nhiệm của `KeyFactory`.
3. `Signature.initSign(privateKey)` thiết lập chế độ ký, còn `Signature.initVerify(publicKey)` thiết lập chế độ xác minh. Không tráo vai trò hai khóa.
4. `update(message)` nhập chính xác bytes sẽ được bảo vệ bằng chữ ký; việc thay đổi nội dung dù chỉ một byte làm mất hiệu lực xác thực đối với chữ ký cũ.
5. Trong `generic`, cả **ba** engine đều được lấy qua tên `"EdDSA"`. Nhưng generator đã được ràng buộc đường cong bằng `NamedParameterSpec`, nên chương trình không lệ thuộc đường cong mặc định của provider.
6. `curve.getName()` cho tên `Ed25519`/`Ed448`, còn `NamedParameterSpec.ED25519`/`ED448` là **tên hằng Java**.
7. `GeneralSecurityException` là superclass checked exception phù hợp cho ví dụ; ứng dụng thật nên phân loại từng lỗi có ý nghĩa nghiệp vụ và không nuốt exception.
8. Kích thước chữ ký được xác định theo dạng Ed25519/Ed448 thông thường trong RFC 8032, nên **có thể dự đoán**; giá trị chữ ký/cặp khóa cụ thể **không** được hard-code.

`Key.getAlgorithm()`, `Key.getFormat()` và `Signature.getProvider()` có thể hữu ích cho gỡ lỗi, nhưng **đừng lấy tên provider hoặc representation của một object làm điều kiện duy nhất quyết định thuật toán của giao thức**. Quyết định phải dựa trên metadata giao thức, tham số đường cong, khóa được phân tích đúng định dạng và các bảo đảm của API.

## 7. Cấu hình thuật toán bằng chuỗi tên: các nguyên tắc quan trọng

### 7.1. Standard name không phải Java package/class name

`"Ed25519"` trong `KeyPairGenerator.getInstance("Ed25519")` là **tên thuật toán** của dịch vụ. Nó **không** phải:

- Tên đầy đủ của class triển khai provider.
- Một `KeySpec`.
- Tên file chứa khóa.
- Một chuỗi transformation dành cho `Cipher`.
- Mã OID DER thô.
- Tên của một digest có thể gọi qua `MessageDigest.getInstance("Ed25519")`.

JCA phân tách **service type + algorithm name + provider**. Chẳng hạn, `KeyFactory` và `Signature` có thể cùng chấp nhận `"Ed448"` nhưng thực hiện **hai trách nhiệm hoàn toàn khác nhau**.

### 7.2. Tên chuẩn khác với mức bắt buộc hỗ trợ

Danh sách **standard names** định nghĩa cách viết thống nhất. Nó **không** yêu cầu mọi security provider tự động hiện thực tất cả dịch vụ/tên. Một JDK/JRE tùy biến, policy công ty, môi trường FIPS hoặc hardware provider có thể thay đổi thuật toán được cung cấp.

Cách kiểm tra hợp lệ khi bắt đầu ứng dụng:

```java
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.Signature;

// Đoạn minh họa trong method:
try {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
    Signature signature = Signature.getInstance("Ed25519");
    System.out.println(generator.getProvider().getName());
    System.out.println(signature.getProvider().getName());
} catch (NoSuchAlgorithmException ex) {
    throw new IllegalStateException("Ed25519 is unavailable", ex);
}
```

Đây **không** phải một class chạy độc lập; các dòng `import` cần đứng ở đầu file và `try` cần đặt trong phương thức. Tên provider in ra có thể khác nhau; không sử dụng một tên provider cụ thể để viết expected stdout. Nếu ứng dụng cần chạy trên provider nhất định, hãy kiểm tra yêu cầu hỗ trợ và test tương thích ngay lúc deploy.

### 7.3. Cách chọn đường cong rõ ràng hơn chọn key size số nguyên

Nên sử dụng `KeyPairGenerator.getInstance("Ed25519")` hoặc `KeyPairGenerator.getInstance("EdDSA")` rồi `initialize(NamedParameterSpec.ED25519)`.

**Không** suy ra rằng phải gọi `initialize(256)` chỉ vì Ed25519 có private seed 32 byte. Các provider có quy tắc riêng cho `initialize(int keysize)`; đó không phải API biểu diễn tên đường cong rõ ràng. Với Ed448 cũng tương tự. Trong mã giao thức, **NamedParameterSpec** đáng đọc và ít mơ hồ hơn.

### 7.4. Kiểu EdEC trong Java

Java 15 có các kiểu biểu diễn khóa Edwards-Curve:

- `java.security.interfaces.EdECPublicKey` và `EdECPrivateKey`.
- `java.security.spec.EdECPublicKeySpec` và `EdECPrivateKeySpec`.
- `java.security.spec.EdECPoint`.
- `java.security.spec.NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448`.

Chúng thích hợp khi cần làm việc với biểu diễn tham số/point theo dạng khóa EdEC **thay vì chỉ DER encoded keys**. Cần giữ đúng endianness, point encoding, seed semantics, định dạng giao thức và quy tắc provider; đừng tự chuyển raw bytes thành các kiểu này bằng cách đoán vị trí từng byte.

Với phần lớn ứng dụng trao đổi public/private key theo chuẩn ASN.1 DER, `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` thường đơn giản hơn.

## 8. `Signature` với EdDSA: tham số và chế độ

### Ed25519/Ed448 thông thường

Nếu giao thức ghi đơn giản **Ed25519** hoặc **Ed448**, dùng tên đúng với RFC 8032 và đưa **message bytes gốc** vào `Signature.update`. Chữ ký được tính bên trong engine, không cần tự băm message để truyền vào.

### Context và prehash là các chế độ khác

Java 15 có `java.security.spec.EdDSAParameterSpec` để mô tả một số lựa chọn theo RFC 8032, ví dụ:

- `prehash = false`, không có context: dạng **Ed25519/Ed448 cơ bản**.
- `prehash = true`: chế độ **Ed25519ph/Ed448ph** tương ứng.
- Context khi được cung cấp có ý nghĩa theo từng mode trong RFC 8032; **không** phải metadata có thể bỏ qua khi xác minh.

Ví dụ minh họa cách tạo spec:

```java
import java.security.spec.EdDSAParameterSpec;

// Đoạn mã nằm trong một method:
EdDSAParameterSpec prehash = new EdDSAParameterSpec(true);
```

Đây là **đoạn minh họa**, chưa bao gồm một chương trình ký hoàn chỉnh. Nếu một hệ thống sử dụng context hoặc prehash, **bên ký và bên xác minh phải đồng ý cùng biến thể/tham số** theo giao thức. Không mặc định rằng `Signature.getInstance("Ed25519")` cùng với việc tự tính SHA-512 bên ngoài sẽ tương đương với Ed25519ph.

Các biến thể này chỉ nên dùng khi hợp đồng giao thức yêu cầu; ví dụ chính sử dụng dạng **thông thường không context và không prehash**.

## 9. Lỗi khi dùng sai tên hoặc sai loại khóa

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `NoSuchAlgorithmException` tại `getInstance` | Tên gõ sai, không có provider hỗ trợ tên/dịch vụ, hoặc cấu hình bảo mật hạn chế | Kiểm tra đúng `EdDSA`/`Ed25519`/`Ed448`; xem provider và danh sách service |
| `InvalidAlgorithmParameterException` khi `initialize(...)` | Curve/parameters không phù hợp với generator hoặc provider | Dùng `NamedParameterSpec.ED25519`/`ED448` cho generic engine; chọn tên đúng |
| `InvalidKeySpecException` từ `KeyFactory` | Encoding không hợp lệ, không đúng chuẩn `X.509`/`PKCS#8`, hoặc curve/key spec không được chấp nhận | Kiểm tra DER và OID, loại khóa, key format, provider |
| `InvalidKeyException` khi `Signature.initSign/initVerify` | Khóa sai họ/sai đường cong, hoặc không phù hợp với engine/provider | Chọn khóa Ed25519/Ed448 tương ứng, không trộn EdDSA với EC/XDH |
| `SignatureException` khi cập nhật/ký/xác minh | Thao tác không hợp lệ, chữ ký sai cấu trúc hoặc engine thất bại | Kiểm tra thứ tự `init*` → `update` → `sign/verify`, độ dài và định dạng chữ ký |
| `verify(...) == false` | Chữ ký không đúng cho message/public key/parameters đã cung cấp | Kiểm tra đúng message bytes, khóa, algorithm, context/prehash và canonicalization |
| `NullPointerException` hoặc `InvalidKeySpecException` khi import | `getEncoded()` không có dữ liệu, public/private key không export được hoặc dùng sai encoding | Kiểm tra `getFormat()`/`getEncoded()`, làm việc qua API của HSM/provider nếu khóa không export |
| `NoSuchAlgorithmException` với `"SHA256withEdDSA"` | Tên này **không phải một standard name** cho EdDSA trong JCA | Dùng tên chuẩn `"EdDSA"`/`"Ed25519"`/`"Ed448"`; chọn RFC mode đúng |
| Chữ ký Ed25519 không xác minh bằng Ed448 | Hai thuật toán và kích thước khóa/chữ ký khác nhau | Không trộn key/curve names; ghi rõ thuật toán trong giao thức |
| Chữ ký xác minh đúng nhưng không biết người ký là ai | Public key chưa được liên kết đáng tin cậy với danh tính | Kiểm tra nguồn gốc/certificate/pinning/metadata theo threat model |
| Chữ ký khác expected hex sau mỗi lần chạy | Sinh cặp khóa mới ngẫu nhiên mỗi lần | Test `verify(...)` và độ dài/định dạng, không hard-code raw signature từ key ngẫu nhiên |

**Đừng bắt `GeneralSecurityException` rồi trả về `true` mặc định.** Lỗi cấu hình hoặc thất bại khi ký/xác minh phải được xử lý theo chính sách an toàn của ứng dụng. Với dữ liệu từ mạng, không để attacker tự chọn bất kỳ tên thuật toán nào mà không có whitelist theo giao thức.

## 10. Quy tắc bảo mật khi dùng EdDSA

1. **Private key là bí mật.** Không ghi `getEncoded()` private key vào log, lỗi HTTP, screenshot hay mã nguồn. Nếu cần lưu lâu dài, dùng giải pháp quản lý khóa phù hợp như KeyStore, KMS/HSM hoặc kho bí mật theo thiết kế và quyền truy cập cụ thể.
2. **Public key cần nguồn gốc đáng tin.** `verify() == true` chỉ chứng minh chữ ký khớp với **public key được đưa vào**; nó không tự bảo đảm public key thuộc đúng người/hệ thống.
3. **Ký đúng byte của giao thức.** Unicode normalization, encoding UTF-8, JSON serialization, xuống dòng, khoảng trắng hoặc trường metadata phải thống nhất giữa bên ký và bên xác minh. Hai chuỗi nhìn giống nhau chưa chắc có byte bằng nhau.
4. **Chọn thuật toán cố định theo giao thức.** Không cho phép payload chưa tin cậy thay `Ed25519` bằng thuật toán khác để “giảm bảo mật”. Các bên cần xác định curve, mode, context và cách biểu diễn key/signature rõ ràng.
5. **Không biến EdDSA thành encryption.** Chữ ký tạo tính xác thực/tính toàn vẹn khi khóa được phân phối tin cậy, nhưng không giữ bí mật nội dung. Nếu cần confidentiality hoặc key agreement, thiết kế giải pháp riêng.
6. **Không tái sử dụng bừa bãi khóa giữa EdDSA và XDH.** X25519/X448 dùng cho trao đổi khóa, không phải alias của Ed25519/Ed448.
7. **Không tự viết triển khai đường cong.** Ưu tiên các JCA provider được bảo trì và đã được kiểm tra; thuật toán mật mã có nhiều chi tiết về validation, scalar, point, side channel và encoding.
8. **EdDSA không phải chữ ký hậu lượng tử.** Với hệ thống có yêu cầu dài hạn chống máy tính lượng tử, cần đánh giá các thuật toán và chuẩn hậu lượng tử theo chính sách hiện hành, không suy ra bảo đảm đó chỉ vì EdDSA hiện đại.

## 11. Checklist chọn đúng tên khi viết code

- [ ] Đã xác định yêu cầu là **chữ ký số** (EdDSA), không phải **key agreement** (X25519/X448)?
- [ ] Đã chọn đúng tên `Ed25519`, `Ed448` hoặc tên family `EdDSA`?
- [ ] Dùng `KeyPairGenerator` để **sinh cặp khóa**, `KeyFactory` để **khôi phục/chuyển key spec**, `Signature` để **ký/xác minh**?
- [ ] Nếu dùng `EdDSA` để sinh khóa, đã chỉ rõ `NamedParameterSpec.ED25519` hoặc `ED448` thay vì dựa vào mặc định?
- [ ] Public key được truyền qua `X509EncodedKeySpec` và private key qua `PKCS8EncodedKeySpec` khi dữ liệu đúng các định dạng đó?
- [ ] Có kiểm tra `getEncoded()` có thể `null` trong provider không hỗ trợ export?
- [ ] Có dùng **UTF-8 hoặc byte representation được giao thức quy định** thống nhất khi ký/xác minh?
- [ ] Có truyền message bytes trực tiếp cho chế độ Ed25519/Ed448 thường, không băm thủ công rồi nhầm với prehash mode?
- [ ] Có thống nhất curve, context/prehash, giao thức và cách mã hóa chữ ký giữa các bên?
- [ ] Có kiểm tra provider thực tế hỗ trợ cả **service + algorithm name** thay vì chỉ tin vào danh sách standard names?
- [ ] Có bảo vệ private key, xác thực nguồn gốc public key và báo lỗi xác minh đúng cách?
- [ ] Đã thử tampering để `verify(...)` trở thành `false` và kiểm tra thông báo lỗi thực tế?

## 12. Tài liệu chính thức

- **Java SE 15 — Java Security Standard Algorithm Names**, các mục `KeyPairGenerator`, `KeyFactory`, `Signature`: https://docs.oracle.com/en/java/javase/15/docs/specs/security/standard-names.html
- **Java SE 25 — Java Security Standard Algorithm Names**, đối chiếu các tên còn được chuẩn hóa trong Java hiện đại: https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html
- **Java SE 15 — Oracle JDK Providers / SunEC**, danh sách EdDSA algorithms và curve sizes: https://docs.oracle.com/en/java/javase/15/security/oracle-providers.html
- **OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm**, tính năng chính thức của Java 15: https://openjdk.org/jeps/339
- **RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)**, các biến thể Ed25519/Ed448 và độ dài chữ ký: https://www.rfc-editor.org/rfc/rfc8032
- **Java SE 15 — `NamedParameterSpec`**, `ED25519`/`ED448`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/NamedParameterSpec.html
- **Java SE 15 — `EdDSAParameterSpec`**, context và prehash: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html
- **Java SE 15 — `KeyPairGenerator`, `KeyFactory`, `Signature`**, Java API: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/KeyPairGenerator.html ; https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/KeyFactory.html ; https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/Signature.html

**Kết luận:** Đối với Java 15+, ba tên thuật toán chuẩn của EdDSA dùng được với cả **`KeyPairGenerator`, `KeyFactory` và `Signature`** là **`EdDSA`, `Ed25519` và `Ed448`**. Chọn tên cụ thể khi giao thức cố định curve; chọn family `EdDSA` khi thật sự cần hỗ trợ nhiều curve và **chỉ định tham số/kiểm tra key rõ ràng**. Mọi ví dụ và API ở đây thuộc Java SE chính thức, còn phù hợp với JDK hiện đại và không dựa trên kỹ thuật legacy.
