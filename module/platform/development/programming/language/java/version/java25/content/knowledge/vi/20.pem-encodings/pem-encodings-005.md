# Xử lý đầu vào sai định dạng và bảo vệ khóa riêng cùng mật khẩu liên quan

> **Chương:** Mã hóa PEM  
> **Phạm vi module:** `JAVA_VERSION_JAVA25` — sử dụng các khả năng Java hiện đại còn phù hợp để xử lý khóa, chứng chỉ và tích hợp bảo mật; nắm vững JCA, ASN.1/DER và quản lý vòng đời khóa trong ứng dụng doanh nghiệp.  
> **Mục tiêu:** Nhận diện PEM label và định dạng khóa; xử lý boundary thiếu, label sai, Base64 hỏng, ASN.1 không hợp lệ, nhiều block hoặc thuật toán không hỗ trợ; bảo vệ private key và passphrase khi đọc, giải mã, lưu trữ, ghi log và vận hành.  
> **Mốc cập nhật:** JDK 25 giới thiệu PEMEncoder/PEMDecoder qua JEP 470 dưới dạng preview; JDK 26 và 27 tiếp tục preview qua JEP 524 và JEP 538. Đến **27/11/2026**, JDK 27 là bản GA mới nhất và API PEM vẫn là preview lần thứ ba. JEP 542 đã hoàn thiện API cho JDK 28; nhánh JDK 28 đang phát triển đã có API không còn preview, nhưng JDK 28 chưa phát hành GA. Các ví dụ JDK 25 trong bài phải bật preview; phần cuối nêu cách chuyển sang API final.

PEM thường được dùng để trao đổi private key, public key, certificate và certificate chain giữa OpenSSL, Java, reverse proxy, máy chủ TLS và hệ thống quản lý bí mật. Vì nội dung PEM là văn bản, người vận hành có thể chỉnh sửa bằng editor, copy qua ticket hoặc ghép nhiều certificate vào một file. Sự tiện lợi này cũng tạo ra lỗi thường gặp: thiếu footer, sai label, cắt mất Base64, ghép nhầm nhiều block hoặc lưu private key không được bảo vệ.

Một lỗi parser không chỉ làm ứng dụng khởi động thất bại. Nếu ứng dụng chấp nhận nhầm loại dữ liệu, âm thầm bỏ qua block đầu/cuối, hoặc ghi nội dung khóa ra log khi báo lỗi, sự cố có thể trở thành vấn đề bảo mật. Vì vậy, quy trình PEM cần kiểm soát cả **định dạng**, **ngữ nghĩa khóa**, **chính sách chấp nhận đầu vào** và **vòng đời secret**.

## 1. PEM là lớp biểu diễn văn bản, không phải thuật toán mã hóa

PEM là dạng biểu diễn văn bản của dữ liệu nhị phân. Với các cấu trúc PKIX/PKCS/CMS, nội dung thường là dữ liệu ASN.1 được mã hóa BER hoặc DER, sau đó chuyển thành Base64 và đặt giữa hai dòng boundary:

```text
-----BEGIN CERTIFICATE-----
<Base64 data>
-----END CERTIFICATE-----
```

PEM cung cấp:

- **Boundary:** đánh dấu nơi bắt đầu và kết thúc của một object.
- **Label:** cho biết kiểu cấu trúc được mã hóa, ví dụ `CERTIFICATE` hoặc `PRIVATE KEY`.
- **Base64:** chuyển bytes nhị phân thành văn bản ASCII.
- **ASN.1/DER:** biểu diễn cấu trúc certificate, key hoặc container bên trong.

**Base64 không mã hóa bí mật.** Bất kỳ ai có file `PRIVATE KEY` không được mã hóa đều có thể giải mã Base64 và lấy private-key material. Chỉ label `ENCRYPTED PRIVATE KEY` mới biểu thị cấu trúc PKCS#8 đã được mã hóa bằng password-based encryption hoặc cơ chế khóa tương ứng.

Không nhầm ba lớp sau:

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| PEM | `-----BEGIN PRIVATE KEY-----` | Bao dữ liệu nhị phân bằng label và Base64 |
| ASN.1/DER | PKCS#8 `PrivateKeyInfo`, X.509 `SubjectPublicKeyInfo` | Mô tả cấu trúc và trường dữ liệu |
| Mật mã | RSA, EC, Ed25519, PBES2/PBE | Xác định thuật toán khóa hoặc bảo vệ dữ liệu |

Một file có boundary đúng và Base64 hợp lệ vẫn có thể chứa ASN.1 sai cấu trúc, thuật toán không được provider hỗ trợ hoặc khóa không phù hợp với mục đích sử dụng.

## 2. Nhận diện label trước khi chọn API giải mã

Label cho biết cấu trúc bên trong. Không thể chỉ đổi tên label để chuyển một định dạng thành định dạng khác.

| PEM label | Cấu trúc thường gặp | Ý nghĩa | Ghi chú tương thích |
|---|---|---|---|
| `CERTIFICATE` | X.509 Certificate | Chứng chỉ chứa public key và thông tin định danh | Dùng `X509Certificate` hoặc `CertificateFactory` |
| `PUBLIC KEY` | X.509 `SubjectPublicKeyInfo` | Public key độc lập | Dùng `PublicKey`/`X509EncodedKeySpec` |
| `PRIVATE KEY` | PKCS#8 `PrivateKeyInfo` hoặc RFC 5958 `OneAsymmetricKey` | Private key chưa mã hóa | Dùng `PKCS8EncodedKeySpec`/`PrivateKey` |
| `ENCRYPTED PRIVATE KEY` | PKCS#8 `EncryptedPrivateKeyInfo` | Private key được bảo vệ bằng PBE hoặc khóa mã hóa | Cần password/khóa và provider tương thích |
| `X509 CRL` | X.509 CertificateList | Danh sách chứng chỉ bị thu hồi | Dùng `X509CRL` |
| `RSA PRIVATE KEY` | PKCS#1 `RSAPrivateKey` | Private key RSA ở định dạng riêng của PKCS#1 | Không phải PKCS#8; hỗ trợ trực tiếp phụ thuộc parser |
| `EC PRIVATE KEY` | SEC 1 `ECPrivateKey` | Private key EC ở định dạng SEC1 | Cần parser/provider hỗ trợ SEC1 hoặc chuyển đổi có kiểm soát |
| `CERTIFICATE REQUEST` | PKCS#10 CertificationRequest | CSR gửi CA | Không phải certificate đã được CA cấp |
| `OPENSSH PRIVATE KEY` | OpenSSH private-key format | Container khóa riêng theo định dạng OpenSSH | Không phải PKCS#8; không đổi label thành `PRIVATE KEY` |

### 2.1. PRIVATE KEY và RSA PRIVATE KEY không giống nhau

`PRIVATE KEY` là label chuẩn cho cấu trúc PKCS#8. `RSA PRIVATE KEY` thường biểu diễn trực tiếp cấu trúc PKCS#1 của RSA. Cả hai có thể chứa cùng một khóa RSA về mặt toán học, nhưng bytes ASN.1 bên trong khác nhau.

Tương tự, `EC PRIVATE KEY` là cấu trúc SEC1. Muốn chuyển sang PKCS#8 phải parse cấu trúc đúng, giữ đúng curve parameters và tạo container mới theo chuẩn. Không sửa dòng header/footer để giả vờ dữ liệu đã là PKCS#8.

JDK 25 PEMDecoder liệt kê các label chuẩn và có ghi chú rằng implementation OpenJDK bổ sung hỗ trợ `RSA PRIVATE KEY` không mã hóa. Đây là hỗ trợ implementation-specific; ứng dụng cần chạy trên nhiều JDK/provider không nên coi nó là bảo đảm portable. `EC PRIVATE KEY` và `OPENSSH PRIVATE KEY` cũng không nằm trong danh sách chuẩn mà JDK 25 PEM API cam kết.

### 2.2. Phân biệt key, certificate và CSR

- Public key có thể được trích xuất từ certificate, nhưng certificate còn có issuer, validity, extensions, serial number và chữ ký CA.
- CSR chứa public key cùng thông tin yêu cầu chứng chỉ và chữ ký chứng minh người tạo sở hữu private key tương ứng.
- Certificate chưa chắc đáng tin chỉ vì parse thành công; cần xác minh chain tới trust anchor và các policy liên quan.
- Private key không thể được xác minh là thuộc certificate chỉ bằng cách so label hoặc algorithm name.

## 3. Những lỗi đầu vào PEM thường gặp

Một ứng dụng xử lý PEM nên phân loại lỗi theo giai đoạn, để có thể chẩn đoán mà không làm lộ dữ liệu bí mật.

| Lỗi | Ví dụ | Kết quả có thể gặp |
|---|---|---|
| Thiếu BEGIN | File chỉ còn Base64 body | Không tìm thấy PEM block |
| Thiếu END | File bị cắt khi copy hoặc upload | Parser báo EOF hoặc dữ liệu không hoàn chỉnh |
| Sai label | Dữ liệu PKCS#1 nhưng đặt `PRIVATE KEY` | ASN.1 parser hoặc key factory từ chối |
| Mismatch label | BEGIN là `PRIVATE KEY` nhưng END là `CERTIFICATE` | Parser nghiêm ngặt từ chối; parser khác có thể xử lý khác |
| Base64 lỗi | Ký tự ngoài alphabet, padding sai hoặc thiếu dữ liệu | Decode thất bại hoặc kết quả bị cắt |
| ASN.1 lỗi | Base64 hợp lệ nhưng DER/BER không hợp lệ | Lỗi parse cấu trúc nhị phân |
| Sai key algorithm | Provider không hỗ trợ OID hoặc key algorithm | `NoSuchAlgorithmException` hoặc lỗi provider |
| Encrypted key nhưng không có password | `ENCRYPTED PRIVATE KEY` được đọc như key thường | Decoder trả object encrypted hoặc báo lỗi kiểu |
| Password sai | Không giải mã được encrypted private key | Lỗi giải mã/key generation |
| Thuật toán PBE không được hỗ trợ | File dùng PBE provider hiện tại không có | Lỗi khởi tạo cipher hoặc KDF |
| Nhiều block ngoài dự kiến | Hai private key trong file cấu hình chỉ cho phép một | Có thể chỉ xử lý block đầu và bỏ sót block sau |
| Prefix/suffix ngoài dự kiến | Text hướng dẫn, log hoặc shell prompt dính vào file | Parser có thể bỏ qua hoặc lưu leading data |
| Certificate hết hạn/không tin cậy | PEM parse được nhưng chain sai | Parse thành công nhưng xác minh TLS thất bại |

### 3.1. Phân biệt lỗi cú pháp và lỗi mật mã

Có ít nhất bốn giai đoạn khác nhau:

1. **Envelope parsing:** tìm boundary, đọc label và body.
2. **Base64 decoding:** chuyển văn bản thành bytes.
3. **ASN.1/key decoding:** đọc cấu trúc và tạo key/certificate object.
4. **Cryptographic validation:** kiểm tra algorithm policy, key/certificate relation, certificate chain và quyền sử dụng.

Không gom tất cả vào một thông báo như `PEM invalid` trong log nội bộ, vì sẽ khó xác định nguyên nhân. Tuy nhiên, API công khai không nên tiết lộ chi tiết nhạy cảm như password đúng/sai hoặc nội dung private key.

## 4. RFC 7468: parser có thể linh hoạt, ứng dụng phải có policy rõ ràng

RFC 7468 định nghĩa các boundary và label cho nhiều cấu trúc PKIX, PKCS và CMS. Một số quy tắc quan trọng:

- Boundary có đúng năm dấu gạch nối ở mỗi bên.
- Có một dấu cách giữa `BEGIN`/`END` và label.
- Label là chữ hoa và phân biệt hoa thường.
- Generator phải dùng cùng label cho BEGIN và END.
- Generator mới nên tạo Base64 thành các dòng 64 ký tự, trừ dòng cuối.
- Parser phải xử lý newline LF, CRLF và CR.
- Parser có thể chấp nhận whitespace hoặc dữ liệu không thuộc Base64 trong một số vị trí để tương thích.
- File có thể chứa nhiều PEM blocks, ví dụ certificate chain.

RFC cho phép parser linh hoạt để tương thích với dữ liệu đã được triển khai rộng rãi. Nhưng điều đó không có nghĩa mọi ứng dụng nên chấp nhận mọi dạng input.

### 4.1. Tại sao parser quá dễ dãi tạo rủi ro?

RFC 7468 cảnh báo rằng nhiều parser xử lý whitespace, non-Base64 characters và label alias khác nhau. Một chuỗi có thể được hai thư viện hiểu thành hai object khác nhau. Nếu một lớp bảo mật xác minh block A nhưng lớp nạp khóa sử dụng block B, ứng dụng có thể tạo ra parser differential.

Ví dụ:

```text
Comment: this file is for production
-----BEGIN PRIVATE KEY-----
<Base64 của khóa A>
-----END PRIVATE KEY-----

-----BEGIN PRIVATE KEY-----
<Base64 của khóa B>
-----END PRIVATE KEY-----
```

Nếu hợp đồng cấu hình chỉ cho phép một private key, không nên để parser âm thầm đọc block đầu và bỏ qua block thứ hai. Cũng không nên lấy block đầu để xác minh nhưng lấy block cuối để nạp vào TLS.

### 4.2. Xác định policy theo ngữ cảnh

| Ngữ cảnh | Policy nên áp dụng |
|---|---|
| File chỉ chứa một private key | Chấp nhận đúng một block với label được cho phép; từ chối block thừa |
| File chứa certificate chain | Chấp nhận nhiều `CERTIFICATE` blocks theo thứ tự được định nghĩa |
| Upload certificate từ người dùng | Cho phép label certificate; từ chối private-key labels |
| Import private key | Chỉ cho phép `PRIVATE KEY` hoặc `ENCRYPTED PRIVATE KEY` theo hợp đồng |
| Hỗ trợ nhiều định dạng legacy | Dùng parser được duy trì và allowlist từng label/algorithm |
| Hệ thống cần fingerprint/canonical identity | Decode rồi chuẩn hóa về DER trước khi hash/so sánh |

RFC 7468 không định nghĩa một canonical textual representation duy nhất cho mọi input. Nếu cần so sánh hoặc fingerprint, không hash trực tiếp chuỗi PEM do whitespace, newline và biểu diễn Base64 có thể khác nhau. Decode cấu trúc rồi chuẩn hóa dữ liệu theo DER hoặc theo cách canonical được chuẩn liên quan quy định.

## 5. Giới hạn kích thước và cấu trúc trước khi parse

PEM thường nhỏ, nhưng ứng dụng nhận input qua HTTP, message queue hoặc file upload vẫn phải giới hạn tài nguyên.

Các kiểm soát cần có:

1. Giới hạn số byte đọc vào trước khi tạo String/byte array lớn.
2. Giới hạn tổng số PEM blocks.
3. Giới hạn số certificate trong chain nếu ứng dụng chỉ cần một chain có độ dài nhất định.
4. Giới hạn kích thước từng block và tổng kích thước Base64.
5. Từ chối dữ liệu không phải ASCII khi hợp đồng PEM yêu cầu ASCII.
6. Không giải mã hoặc decrypt một object trước khi kiểm tra label và policy.
7. Không parse ASN.1 tự viết bằng regex hoặc phép cắt chuỗi.

Ví dụ giới hạn đầu vào:

```java
private static final int MAX_PEM_BYTES = 1_048_576;

static byte[] readBounded(InputStream source) throws IOException {
    byte[] data = source.readNBytes(MAX_PEM_BYTES + 1);

    if (data.length > MAX_PEM_BYTES) {
        throw new IOException("PEM input exceeds the configured limit");
    }

    return data;
}
```

`readNBytes` chỉ đọc tối đa giới hạn cộng một byte để phát hiện input vượt mức. Con số 1 MiB là ví dụ cho cấu hình ứng dụng; certificate chain, key algorithm và giao thức của hệ thống có thể cần giới hạn khác. Đừng lấy con số minh họa làm chuẩn chung.

### Không dùng regex làm ASN.1 parser

Regex có thể hỗ trợ kiểm tra số lượng boundary hoặc label được phép. Nó không thể thay thế Base64 decoder, ASN.1 parser, key factory hoặc certificate validator. Không viết parser bằng cách xóa tất cả ký tự ngoài Base64 rồi đưa bytes vào `KeyFactory` mà không xác minh container và label.

## 6. Dùng PEMDecoder của JDK 25 đúng cách

JDK 25 giới thiệu `java.security.PEMDecoder` và `PEMEncoder` qua JEP 470. Đây là **preview API**. Khi biên dịch và chạy ví dụ cần bật preview:

```bash
javac --release 25 --enable-preview -d out src/*.java
java --enable-preview -cp out com.acme.Main
```

PEMDecoder có các dạng:

- `decode(String)`: đọc PEM từ String.
- `decode(InputStream)`: đọc một PEM object từ stream.
- `decode(String, Class)`: yêu cầu kiểu object mong muốn.
- `decode(InputStream, Class)`: đọc stream và yêu cầu kiểu object.
- `withDecryption(char[])`: tạo decoder mới để giải mã encrypted private key.
- `withFactory(Provider)`: chỉ định provider cho KeyFactory/CertificateFactory trong JDK 25.

Các loại object JDK 25 API hỗ trợ gồm:

| Label | Kiểu trả về |
|---|---|
| `CERTIFICATE` | `X509Certificate` |
| `X509 CRL` | `X509CRL` |
| `PUBLIC KEY` | `PublicKey` |
| `PRIVATE KEY` | `PrivateKey` hoặc `KeyPair` nếu có public key |
| `ENCRYPTED PRIVATE KEY` | `EncryptedPrivateKeyInfo`, hoặc `PrivateKey` khi decoder được cấu hình giải mã |
| Label khác | `PEMRecord` |

JDK 25 implementation của OpenJDK còn hỗ trợ thêm `RSA PRIVATE KEY` không mã hóa, `X509 CERTIFICATE`, `X.509 CERTIFICATE` và `CRL`. Đây là ghi chú implementation; không dùng nó làm bảo đảm cho mọi JDK distribution/provider.

### 6.1. Yêu cầu kiểu trả về thay vì cast tùy tiện

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.security.PrivateKey;
import java.security.PEMDecoder;

static PrivateKey decodePrivateKey(byte[] pemBytes) throws IOException {
    try (var input = new ByteArrayInputStream(pemBytes)) {
        return PEMDecoder.of().decode(input, PrivateKey.class);
    }
}
```

Dạng có tham số class giúp API xác nhận kiểu dữ liệu mong muốn. Nếu label không tương ứng với kiểu được yêu cầu, decoder có thể ném `ClassCastException`. Nếu không tìm thấy PEM hoặc nội dung sai định dạng, có thể nhận `IllegalArgumentException`, `IOException` hoặc lỗi runtime tùy overload và giai đoạn lỗi.

### 6.2. Decoder không tự áp dụng policy của ứng dụng

Javadoc JDK 25 nêu `decode(String)` đọc đến khi tìm thấy PEM data. Với loại dữ liệu có kiểu Java tương ứng, dữ liệu không phải PEM đứng trước header có thể bị bỏ qua. Với label không hỗ trợ, `PEMRecord` có thể giữ `leadingData`.

Do đó, nếu API của ứng dụng yêu cầu chính xác một private-key block, hãy kiểm tra envelope trước khi gọi decoder:

- Chỉ một BEGIN và một END.
- Label đúng với loại khóa được chấp nhận.
- END xuất hiện sau BEGIN và label khớp.
- Không có block thứ hai.
- Không có prefix/suffix ngoài policy.
- Tổng input nằm trong giới hạn.

Việc kiểm tra envelope chỉ xác định phạm vi input. `PEMDecoder` vẫn phải chịu trách nhiệm decode Base64 và cấu trúc nhị phân.

### 6.3. Ví dụ kiểm tra một block private key

```java
import java.nio.charset.StandardCharsets;

static void requireSinglePrivateKeyBlock(byte[] bytes) {
    if (bytes.length == 0 || bytes.length > MAX_PEM_BYTES) {
        throw new IllegalArgumentException("Invalid PEM size");
    }

    for (byte value : bytes) {
        if ((value & 0x80) != 0) {
            throw new IllegalArgumentException("PEM must be ASCII");
        }
    }

    String text = new String(bytes, StandardCharsets.US_ASCII);

    String beginPrefix = "-----BEGIN ";
    String endPrefix = "-----END ";
    String begin = "-----BEGIN PRIVATE KEY-----";
    String end = "-----END PRIVATE KEY-----";

    int beginAt = text.indexOf(beginPrefix);
    int endAt = text.indexOf(endPrefix);

    boolean oneBegin = beginAt >= 0
            && text.indexOf(beginPrefix, beginAt + beginPrefix.length()) < 0;
    boolean oneEnd = endAt >= 0
            && text.indexOf(endPrefix, endAt + endPrefix.length()) < 0;

    if (!oneBegin || !oneEnd
            || !text.startsWith(begin, beginAt)
            || !text.startsWith(end, endAt)
            || endAt <= beginAt
            || !text.substring(0, beginAt).isBlank()
            || !text.substring(endAt + end.length()).isBlank()) {
        throw new IllegalArgumentException(
                "Expected exactly one PRIVATE KEY block");
    }
}
```

Đây là policy minh họa cho endpoint chỉ nhận một `PRIVATE KEY` chưa mã hóa. Nếu endpoint nhận `ENCRYPTED PRIVATE KEY`, hãy dùng label tương ứng. Nếu cần chấp nhận cả hai, allowlist chính xác hai label và xác định rõ cách xử lý từng trường hợp. Đoạn kiểm tra không thay thế decoder và không xác thực ASN.1.

## 7. Đọc private key PKCS#8 không mã hóa

`PRIVATE KEY` chứa PKCS#8 PrivateKeyInfo hoặc RFC 5958 OneAsymmetricKey. Với JDK 25:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.security.PEMDecoder;
import java.security.PrivateKey;

static PrivateKey loadUnencryptedPkcs8(byte[] pemBytes)
        throws IOException {

    requireSinglePrivateKeyBlock(pemBytes);

    try (var input = new ByteArrayInputStream(pemBytes)) {
        return PEMDecoder.of().decode(input, PrivateKey.class);
    }
}
```

Không dùng hàm này cho `RSA PRIVATE KEY` hoặc `EC PRIVATE KEY` nếu parser/provider không hỗ trợ định dạng đó. Hãy chuyển đổi bằng công cụ hoặc thư viện mật mã được duy trì, sau đó kiểm tra kết quả PKCS#8 trước khi đưa vào hệ thống.

Với file `PRIVATE KEY` không mã hóa, `pemBytes` chứa private-key material dạng văn bản. Caller nên giới hạn lifetime của mảng và xóa nó best-effort sau khi decode xong; không giữ bản sao trong cache hoặc log.

### Một số lưu ý khi nhận PrivateKey object

- `PrivateKey.getAlgorithm()` cho biết thuật toán mà provider nhận diện; nó không chứng minh khóa đạt policy của ứng dụng.
- `PrivateKey.getFormat()` thường trả `PKCS#8` với khóa có encoding tương ứng; một khóa không exportable có thể không có encoded form.
- `PrivateKey.getEncoded()` có thể trả dữ liệu nhạy cảm. Không gọi chỉ để debug hoặc ghi log.
- `PrivateKey.toString()` không phải giao diện an toàn để log. Không phụ thuộc vào nội dung mà provider hiển thị.
- Khóa từ HSM/PKCS#11 có thể là object tham chiếu tới phần cứng, không phải byte array có thể export.

## 8. Đọc encrypted private key và kiểm tra thuật toán trước khi decrypt

`ENCRYPTED PRIVATE KEY` chứa PKCS#8 `EncryptedPrivateKeyInfo`. Cấu trúc này gồm `AlgorithmIdentifier` và `encryptedData`. Thuật toán và parameters quyết định cách tạo khóa giải mã và giải mã private key.

Khi input đến từ nguồn không tin cậy, nên kiểm tra thuật toán và parameters trước khi dùng password. Không chấp nhận mọi PBE algorithm chỉ vì provider có thể thực thi nó.

### 8.1. Parse trước, kiểm tra policy, sau đó mới decrypt

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.PEMDecoder;
import java.util.Arrays;
import javax.crypto.EncryptedPrivateKeyInfo;

static PrivateKey decryptPkcs8(
        byte[] pemBytes,
        char[] password
) throws IOException, GeneralSecurityException {

    requireSingleEncryptedPrivateKeyBlock(pemBytes);

    try (var input = new ByteArrayInputStream(pemBytes)) {
        EncryptedPrivateKeyInfo encrypted =
                PEMDecoder.of().decode(
                        input, EncryptedPrivateKeyInfo.class);

        String algorithm = encrypted.getAlgName();
        var parameters = encrypted.getAlgParameters();

        if (!isAllowedPbe(algorithm, parameters)) {
            throw new GeneralSecurityException(
                    "Encrypted key algorithm is not allowed");
        }

        return encrypted.getKey(password);
    } finally {
        Arrays.fill(password, '\0');
    }
}
```

Ví dụ giả định method nhận quyền sở hữu mảng `password` và xóa nó khi kết thúc; không truyền vào đây một mảng đang được thành phần khác dùng chung. `requireSingleEncryptedPrivateKeyBlock` tương tự ví dụ trước nhưng chỉ chấp nhận label `ENCRYPTED PRIVATE KEY`. `isAllowedPbe` là policy helper do ứng dụng định nghĩa: cần kiểm tra algorithm identifier, parameters, KDF và mức chi phí phù hợp với provider được triển khai. Không viết allowlist chỉ dựa vào một chuỗi thuật toán nếu parameters cũng ảnh hưởng độ an toàn.

Ví dụ sử dụng `EncryptedPrivateKeyInfo.getKey(char[])` là preview API của JDK 25. Nó nhận password và tạo `PrivateKey`; lỗi parse/decrypt/key generation được biểu diễn qua `GeneralSecurityException`.

### 8.2. Giải mã trực tiếp qua PEMDecoder

Nếu ứng dụng chấp nhận thuật toán PBE theo cấu hình provider đã được kiểm soát, có thể dùng:

```java
char[] password = secretProvider.readPassword();

try {
    var decoder = PEMDecoder.of().withDecryption(password);

    try (var input = new ByteArrayInputStream(pemBytes)) {
        PrivateKey key = decoder.decode(input, PrivateKey.class);
        useKey(key);
    }
} catch (IOException | RuntimeException ex) {
    throw new KeyMaterialException(
            "Private key is invalid, unsupported, or cannot be decrypted", ex);
} finally {
    Arrays.fill(password, '\0');
}
```

`KeyMaterialException` là exception do ứng dụng định nghĩa; giữ cause trong log nội bộ có kiểm soát nhưng không trả chi tiết đó cho caller bên ngoài. Đây là cách ngắn hơn, nhưng decoder sẽ giải mã trước khi ứng dụng có thể kiểm tra riêng `EncryptedPrivateKeyInfo.getAlgName()` và parameters. Nếu policy cần allowlist thuật toán, dùng cách parse `EncryptedPrivateKeyInfo` trước.

### 8.3. Password được clone trong decoder

JDK 25 `PEMDecoder.withDecryption(char[])` tạo decoder mới và **clone rồi lưu password** trong instance đó. `EncryptedPrivateKeyInfo.getKey(char[])` cũng clone password trước khi dùng.

Vì vậy:

- Xóa mảng `char[]` do ứng dụng sở hữu trong `finally`.
- Tạo decoder có password trong phạm vi ngắn, không giữ trong static field hoặc cache dùng chung.
- Không chuyển password thành `String`; `String` immutable và không thể chủ động ghi đè nội dung.
- Không giả định `Arrays.fill` xóa được mọi bản sao trong heap; API có thể đã clone và JVM/provider có thể tạo bản sao nội bộ.
- Nếu yêu cầu không export key ở dạng plaintext, dùng HSM/PKCS#11 hoặc dịch vụ quản lý khóa để thực hiện thao tác trong vùng bảo vệ.

## 9. Tạo encrypted PKCS#8 PEM đúng cách

JDK 25 `PEMEncoder` hỗ trợ mã hóa private key khi cấu hình `withEncryption(char[])`:

```java
import java.security.PEMEncoder;
import java.security.PrivateKey;
import java.util.Arrays;

static byte[] encodeEncryptedPrivateKey(
        PrivateKey privateKey,
        char[] password
) {
    try {
        PEMEncoder encoder = PEMEncoder.of().withEncryption(password);
        return encoder.encode(privateKey);
    } finally {
        Arrays.fill(password, '\0');
    }
}
```

Encoder được cấu hình chỉ dùng để mã hóa `PrivateKey`; encode các loại object khác bằng encoder này sẽ gây `IllegalArgumentException`. `withEncryption` clone và giữ password trong encoder mới, vì vậy giữ encoder trong scope ngắn và không lưu vào singleton lâu dài.

### 9.1. Không mặc định rằng PBE algorithm giống nhau ở mọi provider

JDK 25 quy định default password-based encryption algorithm qua security property `jdk.epkcs8.defaultAlgorithm`. Parameters mặc định do provider được chọn quyết định.

Trước khi dùng để lưu private key lâu dài:

1. Xác nhận security property đang được áp dụng.
2. Xác nhận provider cung cấp đúng `SecretKeyFactory`/`Cipher`.
3. Kiểm tra thuật toán, KDF, salt, iteration/work factor, IV/nonce và parameters thực tế trong `EncryptedPrivateKeyInfo`.
4. Kiểm tra khả năng giải mã tương thích với hệ thống sẽ đọc khóa.
5. Có quy trình thay đổi thuật toán khi policy bảo mật thay đổi.

Nếu cần thuật toán và parameters cụ thể, JDK 25 cung cấp preview API `EncryptedPrivateKeyInfo.encryptKey(...)` để chỉ định algorithm, `AlgorithmParameterSpec`, provider và secure random. Chỉ dùng cấu hình đã được review theo tiêu chuẩn bảo mật của hệ thống; không tự ghép cipher/KDF hoặc tái sử dụng salt/IV.

### 9.2. Không sử dụng cơ chế mã hóa PEM legacy cho thiết kế mới

Các file cũ có thể chứa header kiểu `Proc-Type: 4,ENCRYPTED` hoặc `DEK-Info` cùng các label như `RSA PRIVATE KEY`. Đây là kiểu mã hóa PEM truyền thống, khác với PKCS#8 `ENCRYPTED PRIVATE KEY`. Một số thuật toán cũ không còn phù hợp cho lưu trữ mới.

Khi di chuyển dữ liệu legacy:

- Dùng công cụ hoặc thư viện được duy trì để đọc đúng định dạng cũ.
- Chuyển private key sang PKCS#8.
- Mã hóa lại theo policy PBE hiện hành hoặc chuyển vào key vault/HSM.
- Xác minh key mới khớp public key/certificate trước khi thay thế.
- Xóa bản plaintext/legacy theo quy trình sanitization và backup retention của tổ chức.

Không chỉ thay label từ `RSA PRIVATE KEY` sang `ENCRYPTED PRIVATE KEY`; nội dung phải được chuyển đổi cấu trúc và mã hóa thực sự.

## 10. Bảo vệ passphrase và private key trong ứng dụng

Encrypted PEM chỉ bảo vệ private key khi attacker không đồng thời lấy được password giải mã. Nếu private key và password nằm cùng thư mục, cùng image hoặc cùng repository, mã hóa tại file không đem lại nhiều lợi ích.

### 10.1. Nguồn password

Ưu tiên lấy password từ:

- Secret manager hoặc vault có phân quyền.
- HSM/KMS hoặc dịch vụ quản lý khóa nếu có thể tránh export private key.
- Cơ chế nhập secret được bảo vệ trong môi trường vận hành có kiểm soát.

Tránh:

- Hard-code password trong source code.
- Commit password vào Git.
- Đặt password trong Dockerfile, container image hoặc file cấu hình chung.
- Truyền password trong command-line arguments.
- Ghi password vào environment variables nếu nền tảng có nguy cơ lộ qua process inspection hoặc diagnostic dump.
- Lưu password cạnh file PEM hoặc trong cùng một secret bundle không có kiểm soát truy cập.

### 10.2. Passphrase cần có entropy phù hợp

Passphrase dùng để mã hóa private key cần đủ khó đoán và được tạo theo policy. Không dùng password đăng nhập thông thường hoặc password dùng lại ở nhiều hệ thống. Nếu cần con người nhập, sử dụng passphrase dài, được tạo từ nguồn ngẫu nhiên phù hợp; nếu secret do hệ thống cấp, dùng secret có entropy cao.

Không áp dụng trực tiếp khuyến nghị password hashing cho login vào cơ chế mã hóa PKCS#8. Password hashing và password-based encryption là hai mục đích khác nhau. Hãy chọn thuật toán PBE/KDF được provider hỗ trợ và được policy mật mã phê duyệt.

### 10.3. Thời gian tồn tại của key material

- Chỉ decrypt khi cần nạp key vào TLS/signature operation.
- Không tạo nhiều bản sao `byte[]`/`String` của PEM hoặc DER.
- Không lưu private key trong cache không có thời hạn.
- Hạn chế heap dump và diagnostic dump ở môi trường chứa khóa.
- Giới hạn quyền đọc file và thư mục chứa PEM.
- Không gửi key qua ticket, chat, paste service hoặc log aggregator.
- Có quy trình rotate khi key bị nghi lộ hoặc người có quyền truy cập rời tổ chức.

`Arrays.fill` là biện pháp best-effort cho mảng mà ứng dụng sở hữu. Garbage collector, JIT, provider và API có thể tạo bản sao khác; không xem Java heap là vùng nhớ zeroization được bảo đảm.

## 11. Xử lý lỗi mà không tạo password oracle hoặc rò rỉ dữ liệu

Trong một dịch vụ nhận PEM qua API, phản hồi quá chi tiết có thể giúp attacker dò password hoặc fingerprint nội dung. Hãy phân biệt thông tin nội bộ và thông tin trả ra ngoài.

| Lỗi nội bộ | Log an toàn | Phản hồi bên ngoài |
|---|---|---|
| Không có PEM boundary | Mã lỗi `PEM_NO_BLOCK` | Dữ liệu khóa không hợp lệ |
| Sai label/kiểu object | Mã lỗi `PEM_TYPE_NOT_ALLOWED` | Dữ liệu khóa không hợp lệ |
| Base64/ASN.1 sai | Mã lỗi parse và correlation ID | Dữ liệu khóa không hợp lệ |
| Provider không hỗ trợ algorithm | Mã lỗi `KEY_ALGORITHM_UNSUPPORTED` | Không thể sử dụng khóa |
| Password sai hoặc decrypt thất bại | Mã lỗi `KEY_DECRYPT_FAILED` | Không thể mở khóa |
| Certificate chain không tin cậy | Mã lỗi validation cụ thể trong log bảo mật | Chứng chỉ không được chấp nhận |

Không ghi vào log:

- Toàn bộ PEM hoặc Base64 body.
- Private-key bytes, `getEncoded()` hoặc `PKCS8EncodedKeySpec`.
- Password/passphrase hoặc String tạo từ password.
- Toàn bộ `EncryptedPrivateKeyInfo` nếu có dữ liệu nhạy cảm.
- Exception message nếu provider có thể đưa dữ liệu đầu vào vào thông báo.

Log nên chứa loại object, kích thước input, JDK/provider version, mã lỗi, nguồn request đã xác thực và correlation ID. Không ghi password hoặc raw key để hỗ trợ debug.

### Tránh phân biệt sai password với dữ liệu hỏng ở endpoint công khai

Nếu endpoint giải mã được gọi từ bên ngoài, không trả thông tin khác nhau cho “password sai”, “ciphertext sai” và “private key không parse được” nếu sự khác biệt có thể giúp dò đoán. Có thể giữ phân loại chi tiết trong log nội bộ có kiểm soát, nhưng trả thông báo tổng quát và áp dụng rate limit.

## 12. Parse certificate thành công không đồng nghĩa certificate đáng tin

PEM decoder có thể tạo `X509Certificate`, nhưng điều đó chỉ chứng minh cấu trúc có thể parse theo provider. Nó không chứng minh certificate được CA tin cậy hoặc phù hợp cho TLS.

Các bước xác minh cần tách riêng:

1. Kiểm tra thời gian bằng `checkValidity()`.
2. Xây dựng chain tới trust anchor được ứng dụng cấu hình.
3. Dùng `CertPathValidator` để xác minh path.
4. Kiểm tra KeyUsage và ExtendedKeyUsage theo mục đích.
5. Kiểm tra Subject Alternative Name/hostname khi dùng TLS.
6. Kiểm tra algorithm/key size theo security policy.
7. Kiểm tra CRL/OCSP nếu policy yêu cầu revocation checking.

Ví dụ kiểm tra thời gian:

```java
import java.security.cert.X509Certificate;

static void checkCertificateTime(X509Certificate certificate)
        throws java.security.cert.CertificateExpiredException,
               java.security.cert.CertificateNotYetValidException {

    certificate.checkValidity();
}
```

`checkValidity()` chỉ kiểm tra thời gian hiệu lực. Nó không xác minh chain, chữ ký CA, hostname hoặc trạng thái thu hồi. Đối với certificate chain nhiều block, dùng `CertificateFactory.generateCertificates(...)` hoặc quy trình parse tương ứng rồi dựng `CertPath` theo policy.

### Kiểm tra private key có khớp certificate

Không chỉ so sánh algorithm name. Một private key RSA có thể không tương ứng với certificate RSA khác. Cần kiểm tra bằng cách ký một challenge ngẫu nhiên và xác minh bằng public key trong certificate, với signature algorithm được chọn theo loại khóa và policy.

Ví dụ minh họa cho RSA:

```java
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.cert.X509Certificate;

static boolean matchesRsaCertificate(
        PrivateKey privateKey,
        X509Certificate certificate
) throws java.security.GeneralSecurityException {

    byte[] challenge = new byte[32];
    new SecureRandom().nextBytes(challenge);

    byte[] signed = null;
    try {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(privateKey);
        signer.update(challenge);
        signed = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(certificate.getPublicKey());
        verifier.update(challenge);
        return verifier.verify(signed);
    } finally {
        java.util.Arrays.fill(challenge, (byte) 0);
        if (signed != null) {
            java.util.Arrays.fill(signed, (byte) 0);
        }
    }
}
```

Ví dụ này chỉ dành cho RSA. Với EC hoặc EdDSA phải chọn signature algorithm tương ứng. Đây là kiểm tra cặp key/certificate; nó không thay thế xác minh certificate chain.

## 13. Xử lý nhiều PEM blocks và certificate chain

Một file có nhiều block không mặc nhiên là sai. Certificate chain thường được lưu bằng nhiều `CERTIFICATE` blocks. Nhưng file cấu hình private key thường cần một private key cụ thể, nên policy khác nhau.

| Loại file | Cách xử lý |
|---|---|
| Một private key | Yêu cầu đúng một private-key block |
| Private key + certificate chain | Parse từng loại theo allowlist, kiểm tra private key khớp leaf certificate |
| Certificate bundle | Parse tất cả certificate, dựng path theo issuer/subject và kiểm tra trust |
| Public key bundle | Xác định cách chọn key theo ID/algorithm; không lấy tùy tiện block đầu |
| File lẫn private key và CSR | Từ chối nếu ứng dụng chỉ nhận certificate hoặc private key |

Không dựa vào thứ tự file để tự kết luận certificate nào là leaf, intermediate hoặc root nếu format giao thức không quy định. Dùng issuer/subject, Authority Key Identifier, Subject Key Identifier và path validation để xây dựng chain.

JDK 25 `PEMDecoder` đọc một PEM object mỗi lần gọi. Nếu xử lý bundle, hãy dùng cách đọc nhiều object có chủ đích hoặc API `CertificateFactory.generateCertificates` phù hợp với certificate collection. Đừng gọi decoder một lần rồi giả định mọi block trong stream đã được kiểm tra.

## 14. Khi nào cần provider hoặc thư viện PEM bổ sung?

JDK 25 PEM API hỗ trợ các loại chuẩn phổ biến, nhưng không phải parser đa định dạng cho mọi hệ sinh thái. Một số hệ thống có thể cung cấp:

- SEC1 `EC PRIVATE KEY`.
- OpenSSH `OPENSSH PRIVATE KEY`.
- PKCS#10 CSR.
- CMS/PKCS#7.
- Các label mở rộng của nhà cung cấp.
- Encrypted private key với PBE algorithm hoặc provider không có sẵn trong runtime.

Nếu cần các định dạng này:

1. Dùng thư viện mật mã được duy trì và có tài liệu tương thích với JDK đích.
2. Cố định phiên bản provider, cập nhật theo security advisory.
3. Chỉ bật các label/algorithm thật sự cần.
4. Chuyển đổi sang định dạng chuẩn được hệ thống đích hỗ trợ.
5. Kiểm tra key/certificate sau chuyển đổi.
6. Không tự viết ASN.1 parser hoặc tự giải mã OpenSSH/SEC1 bằng phép cắt bytes.

Bouncy Castle là một lựa chọn phổ biến khi cần parse nhiều định dạng PKCS/SEC1/OpenSSH hơn JDK API. Tuy nhiên, phải chọn module/provider phù hợp, kiểm tra phiên bản đang được duy trì và tuân thủ policy cryptographic provider của tổ chức. Không thêm dependency chỉ để parse một label mà JDK đã hỗ trợ tốt.

## 15. Thay đổi PEM API giữa JDK 25, 26, 27 và 28

JEP 470 được preview trong JDK 25. API thay đổi qua các vòng preview, vì vậy source code của một bản preview không thể mặc nhiên dùng nguyên vẹn ở bản khác.

| Phiên bản | JEP | Trạng thái | Thay đổi đáng chú ý |
|---|---|---|---|
| JDK 25 | JEP 470 | Preview lần đầu | `DEREncodable`, `PEMRecord`, `withFactory`, `encryptKey` |
| JDK 26 | JEP 524 | Preview lần hai | `PEMRecord` đổi thành `PEM`; hỗ trợ encode/decode thêm `KeyPair` và encoded key specs |
| JDK 27 | JEP 538 | Preview lần ba | `DEREncodable` đổi thành `BinaryEncodable`; `withFactoriesOf`; `CryptoException` |
| JDK 28 | JEP 542 | API final trong nhánh phát triển | Không cần preview flag; `BinaryEncodable` và API final; JDK 28 GA chưa phát hành tại mốc bài viết |

### Những điểm cần đổi khi nâng cấp

| JDK 25 preview | JDK 27 preview / JDK 28 final |
|---|---|
| `DEREncodable` | `BinaryEncodable` |
| `PEMRecord` | `PEM` |
| `PEMDecoder.withFactory(provider)` | `PEMDecoder.withFactoriesOf(provider)` |
| `EncryptedPrivateKeyInfo.encryptKey(...)` | `EncryptedPrivateKeyInfo.encrypt(...)` |
| Một số lỗi giải mã biểu diễn qua `RuntimeException`/`GeneralSecurityException` | JDK 27 thêm `CryptoException` cho lỗi xử lý mật mã trong PEM API |
| Compile/run với `--enable-preview` | JDK 28 final không cần `--enable-preview` |

### JDK 25: compile và chạy preview

```bash
javac --release 25 --enable-preview -d out src/*.java
java --enable-preview -cp out com.acme.Main
```

### JDK 27: vẫn là preview

JDK 27 dùng API lần preview thứ ba, vì vậy vẫn cần preview flags. Cập nhật tên interface, kiểu PEM và provider configuration theo Javadoc JDK 27; không chỉ đổi `--release` rồi giữ nguyên source JDK 25.

### JDK 28: API final

JEP 542 hoàn thiện PEM API cho JDK 28. Khi JDK 28 được phát hành và dự án chọn toolchain đó, dùng API final không cần preview flags. Nhánh JDK 28 đang phát triển đã có Javadoc tương ứng; trước khi rollout production, kiểm tra đúng JDK 28 build được chứng nhận và provider/algorithm support của runtime.

**Khuyến nghị vận hành:** nếu hệ thống đang chạy JDK 27 GA và không muốn phụ thuộc preview API, dùng provider PEM bên ngoài được duy trì hoặc pipeline parse chuẩn PKCS#8/X.509 đã được kiểm thử. Không đưa preview API vào hợp đồng lâu dài chỉ vì nó có sẵn trong JDK.

## 16. Các lỗi thiết kế và cách khắc phục

| Lỗi thiết kế | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi Base64 là mã hóa | Private key bị lộ khi file bị đọc | Dùng encrypted PKCS#8 hoặc key vault/HSM |
| Chỉ kiểm tra label | ASN.1 bên trong có thể sai loại hoặc hỏng | Decode bằng parser phù hợp và yêu cầu kiểu trả về |
| Đổi label bằng cách sửa text | Container không đổi cấu trúc | Chuyển đổi ASN.1 bằng thư viện/provider |
| Chấp nhận mọi label | Parser có thể trả opaque record hoặc object ngoài dự kiến | Allowlist label theo endpoint |
| Chấp nhận nhiều private-key blocks ngoài ý muốn | Có thể nạp nhầm key hoặc bỏ qua block độc hại | Enforce đúng số block |
| Dùng `decode(String)` mà không kiểm tra prefix | Dữ liệu ngoài PEM có thể bị bỏ qua | Prevalidate envelope theo policy |
| Không giới hạn file upload | DoS qua input quá lớn | Giới hạn bytes, blocks và certificate count |
| Bỏ qua algorithm parameters của encrypted key | Chấp nhận PBE/KDF yếu hoặc provider không tương thích | Allowlist algorithm và parameters |
| Để password trong String | Không thể chủ động xóa nội dung | Dùng `char[]`, xóa mảng sở hữu và giảm lifetime |
| Giữ decoder đã cấu hình password trong singleton | Password clone tồn tại lâu | Tạo decoder ngắn hạn |
| Lưu password cạnh PEM | Một lần lộ file có thể lộ cả hai | Tách secret và kiểm soát quyền truy cập |
| Ghi PEM/DER vào log | Rò rỉ private key | Chỉ log metadata và mã lỗi |
| Parse certificate rồi coi là trusted | Chấp nhận certificate không đáng tin | Validate CertPath, hostname, usage và revocation |
| Chỉ so algorithm để ghép key/cert | Có thể ghép nhầm key cùng loại | Thực hiện challenge sign/verify |
| Tự viết parser bằng regex | Bỏ sót quy tắc Base64/ASN.1 và tạo parser differential | Dùng JDK API hoặc thư viện được duy trì |
| Dùng PBE legacy cho file mới | Bảo vệ yếu và khó tương thích | Chuyển sang encrypted PKCS#8 theo policy hiện hành |

## 17. Bài tập thực hành

### Bài A — Tạo ma trận PEM input

Tạo các file thử nghiệm riêng, không dùng private key production:

1. Một `PRIVATE KEY` hợp lệ.
2. Một `ENCRYPTED PRIVATE KEY` hợp lệ.
3. Một certificate `CERTIFICATE`.
4. Một file thiếu END boundary.
5. Một file sai label.
6. Một file Base64 padding sai.
7. Một file chứa hai private-key blocks.
8. Một file có text trước/sau PEM.
9. Một file chứa `RSA PRIVATE KEY` thay vì PKCS#8.
10. Một file encrypted key dùng password sai.

Ghi nhận exception type, giai đoạn lỗi và thông báo ứng dụng trả ra. Đảm bảo log không chứa nội dung PEM hoặc password.

### Bài B — Kiểm tra typed decode

1. Dùng JDK 25 preview để parse `PRIVATE KEY` bằng `PrivateKey.class`.
2. Thử parse cùng input bằng `X509Certificate.class`.
3. Quan sát `ClassCastException` và chuyển thành lỗi cấu hình an toàn.
4. Gửi label không hỗ trợ và quan sát `PEMRecord`.
5. Đảm bảo ứng dụng từ chối object không thuộc allowlist.

### Bài C — Kiểm tra encrypted private key

1. Sinh một key thử nghiệm.
2. Mã hóa bằng `PEMEncoder.withEncryption`.
3. Đọc lại bằng `PEMDecoder.withDecryption`.
4. Thử password sai.
5. Parse `EncryptedPrivateKeyInfo` để xem algorithm name và parameters.
6. Xóa mảng password sau khi dùng.
7. Kiểm tra encoder/decoder có được giữ ngoài scope không.

### Bài D — Certificate và private-key matching

1. Parse certificate và private key riêng biệt.
2. Gọi `checkValidity`.
3. Xây dựng CertPath tới trust anchor.
4. Ký challenge bằng private key.
5. Verify bằng public key từ certificate.
6. Thử ghép với certificate khác cùng algorithm và xác nhận kiểm tra thất bại.

### Bài E — Migration preview API

1. Biên dịch ví dụ JDK 25 với `--enable-preview`.
2. Chạy cùng bài lab trên JDK 27 preview.
3. Cập nhật `DEREncodable` thành `BinaryEncodable`.
4. Cập nhật `PEMRecord` thành `PEM`.
5. Thử trên JDK 28 build đã tích hợp JEP 542 và bỏ preview flags.
6. Ghi lại khác biệt exception, provider và kiểu trả về.

**Tiêu chí đạt:** người học phân biệt được label và ASN.1 container; phát hiện input hỏng/nhiều block; giải mã PKCS#8 encrypted key; kiểm tra algorithm parameters; bảo vệ password; xác minh certificate và key pair; chuyển đổi đúng API theo JDK.

## 18. Checklist trước khi nạp PEM trong production

- [ ] Input có giới hạn byte, số block và thời gian xử lý.
- [ ] Label nằm trong allowlist theo use case.
- [ ] Số block đúng với hợp đồng input.
- [ ] BEGIN/END label khớp theo policy.
- [ ] Không có prefix/suffix hoặc block phụ ngoài dự kiến.
- [ ] Typed decoder yêu cầu đúng loại `PrivateKey`, `PublicKey` hoặc `X509Certificate`.
- [ ] Encrypted key dùng PBE/KDF và parameters được policy cho phép.
- [ ] Password lấy từ secret manager hoặc nguồn được kiểm soát.
- [ ] `char[]` được xóa best-effort; decoder có bản clone được giữ trong scope ngắn.
- [ ] Không ghi PEM, DER, private key hoặc password vào log.
- [ ] Không lưu password cạnh file encrypted PEM.
- [ ] Certificate chain được validate; parse thành công không được coi là trust.
- [ ] Private key được kiểm tra khớp certificate khi cần.
- [ ] Agent/provider/library có phiên bản hỗ trợ JDK đích.
- [ ] Preview API chỉ được dùng khi đã chấp nhận rủi ro tương thích.
- [ ] Có quy trình rotate và xử lý key compromise.

## 19. Nguồn tham khảo chính thức

1. [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html): boundary, label, Base64, nhiều block, PKCS#8 và các lưu ý parser/security.
2. [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958.html): cấu trúc OneAsymmetricKey, phiên bản PKCS#8 mới.
3. [RFC 5208 — PKCS #8 Private-Key Information Syntax](https://www.rfc-editor.org/rfc/rfc5208.html): PrivateKeyInfo và EncryptedPrivateKeyInfo.
4. [RFC 5915 — Elliptic Curve Private Key Structure](https://www.rfc-editor.org/rfc/rfc5915.html): cấu trúc SEC1 ECPrivateKey.
5. [Java SE 25 — PEMDecoder API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMDecoder.html): preview decoder, typed decode, decryption và các loại PEM được hỗ trợ.
6. [Java SE 25 — PEMEncoder API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMEncoder.html): encode key/certificate và encrypted private key.
7. [Java SE 25 — EncryptedPrivateKeyInfo API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): PBE algorithm, parameters, encryptKey và getKey.
8. [JEP 470 — PEM Encodings of Cryptographic Objects (Preview)](https://openjdk.org/jeps/470): API preview lần đầu trong JDK 25.
9. [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): thay đổi API ở JDK 26.
10. [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): thay đổi API ở JDK 27.
11. [JEP 542 — PEM Encodings of Cryptographic Objects](https://openjdk.org/jeps/542): API final được tích hợp cho JDK 28.
12. [Java SE 27 — PEMDecoder API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html): BinaryEncodable, PEM, CryptoException và provider configuration.
13. [Java SE 27 — EncryptedPrivateKeyInfo API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): encrypt/decrypt và các kiểu dữ liệu được hỗ trợ.
14. [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): quản lý, lưu trữ, tách biệt và luân chuyển khóa.
15. [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): vòng đời khóa, vault/HSM và bảo vệ key material.

**Điểm mấu chốt:** PEM chỉ là lớp biểu diễn văn bản; Base64 không bảo vệ private key. Hãy xác định đúng label và container, giới hạn input, yêu cầu kiểu trả về cụ thể, từ chối block ngoài policy và kiểm tra thuật toán trước khi giải mã. Private key cần được mã hóa theo PKCS#8 hoặc giữ trong vault/HSM; password phải được quản lý tách biệt, tồn tại trong bộ nhớ trong thời gian ngắn và không bao giờ xuất hiện trong log. Khi dùng Java 25, nhớ PEM API còn preview; JDK 27 vẫn preview và JDK 28 mới có API final theo JEP 542.
