# Phân biệt khóa công khai, khóa riêng, chứng thư và danh sách thu hồi

Trong hệ thống PKI, khóa công khai, khóa riêng, chứng thư số và danh sách thu hồi chứng thư (CRL) là bốn loại dữ liệu có vai trò khác nhau. Chúng thường được trao đổi trong file PEM nên dễ bị nhầm là cùng một loại nội dung. Cần đọc đúng nhãn PEM và cấu trúc ASN.1 bên trong để biết dữ liệu đang cầm là khóa, chứng thư hay thông tin thu hồi.

PEM chỉ là cách biểu diễn văn bản của dữ liệu nhị phân bằng Base64 cùng nhãn BEGIN/END. PEM không tự chứng minh danh tính, không xác thực chữ ký và cũng không tự mã hóa nội dung. Đặc biệt, một file có đuôi .pem không cho biết nó chứa loại đối tượng nào; nhãn bên trong mới là dấu hiệu đầu tiên để phân loại.

## 1. Bốn loại dữ liệu giải quyết bốn mục đích khác nhau

| Loại | Chứa gì? | Dùng để làm gì? | Có cần giữ bí mật? |
|---|---|---|---|
| Khóa công khai (*public key*) | Thành phần công khai của cặp khóa bất đối xứng | Kiểm tra chữ ký, mã hóa hoặc thỏa thuận khóa tùy thuật toán | Không, nhưng cần xác thực nguồn gốc và tính toàn vẹn |
| Khóa riêng (*private key*) | Thành phần bí mật tương ứng với khóa công khai | Tạo chữ ký, giải mã hoặc thực hiện thao tác riêng tư tùy thuật toán | Có. Chỉ chủ thể được ủy quyền mới được truy cập |
| Chứng thư số (*certificate*) | Danh tính/subject, khóa công khai, issuer, thời hạn, extension và chữ ký của issuer | Liên kết khóa công khai với một chủ thể theo chính sách PKI | Thông thường không. Chứng thư có thể được công khai |
| CRL (*Certificate Revocation List*) | Danh sách serial number của chứng thư bị thu hồi, thời điểm và lý do thu hồi cùng chữ ký của bên phát hành | Kiểm tra một chứng thư đã bị thu hồi hay chưa trong phạm vi CRL | Thông thường không. CRL thường được công bố cho bên kiểm tra |

Khóa công khai và khóa riêng là vật liệu mật mã. Chứng thư là lời xác nhận có chữ ký về mối liên hệ giữa một chủ thể và khóa công khai. CRL là thông tin trạng thái về các chứng thư đã bị thu hồi. Không loại nào thay thế được loại còn lại.

Ví dụ, khi máy chủ HTTPS gửi chứng thư cho client, client lấy khóa công khai từ chứng thư để kiểm tra chữ ký trong quá trình TLS. Client không cần và không được nhận khóa riêng của máy chủ. Nếu cần kiểm tra chứng thư còn hiệu lực hay đã bị thu hồi, client phải thực hiện kiểm tra đường dẫn tin cậy, thời hạn và chính sách thu hồi bằng CRL hoặc OCSP.

## 2. PEM là lớp bao văn bản, không phải định dạng khóa hay chứng thư

Một khối PEM có dạng:

```text
-----BEGIN LABEL-----
Base64-encoded binary data
-----END LABEL-----
```

Phần Base64 thường biểu diễn cấu trúc ASN.1 được mã hóa bằng DER hoặc BER. Nhãn xác định loại cấu trúc bên trong. RFC 7468 quy định các nhãn dùng cho chứng thư, CRL, public key, private key, khóa riêng được mã hóa và yêu cầu cấp chứng thư.

DER là cách mã hóa nhị phân ASN.1 có quy tắc xác định; PEM là cách chuyển dữ liệu nhị phân đó thành văn bản để lưu hoặc truyền. Chuyển DER sang PEM chỉ thêm lớp Base64 và nhãn, không thay đổi ý nghĩa mật mã của đối tượng. Ngược lại, giải Base64 chỉ khôi phục dữ liệu nhị phân; nó chưa xác minh chữ ký hay tính hợp lệ của chứng thư.

Không được suy ra rằng mọi file PEM đều an toàn để chia sẻ. Một file PRIVATE KEY chứa bí mật có thể đọc được dưới dạng Base64 nếu không được mã hóa. Base64 không phải mã hóa bảo mật.

## 3. Phân biệt các nhãn PEM phổ biến

| Nhãn PEM | Cấu trúc bên trong | Ý nghĩa |
|---|---|---|
| PUBLIC KEY | X.509 SubjectPublicKeyInfo (SPKI) | Khóa công khai kèm định danh thuật toán và tham số cần thiết |
| PRIVATE KEY | PKCS #8 PrivateKeyInfo hoặc RFC 5958 OneAsymmetricKey | Khóa riêng ở định dạng tổng quát, không mã hóa bằng mật khẩu |
| ENCRYPTED PRIVATE KEY | PKCS #8 EncryptedPrivateKeyInfo | Khóa riêng được mã hóa, cần mật khẩu để giải mã |
| CERTIFICATE | X.509 Certificate | Chứng thư số |
| X509 CRL | X.509 CertificateList | Danh sách thu hồi chứng thư |
| CERTIFICATE REQUEST | PKCS #10 CertificationRequest | Yêu cầu cấp chứng thư (CSR), chưa phải chứng thư do CA phát hành |

Một số file còn có nhãn thuật toán cụ thể như RSA PRIVATE KEY, RSA PUBLIC KEY hoặc EC PRIVATE KEY. Các nhãn này biểu diễn cấu trúc riêng của thuật toán, chẳng hạn RSA PKCS #1 hoặc ECPrivateKey. Chúng không tương đương với các cấu trúc tổng quát PKCS #8 và SubjectPublicKeyInfo. RFC 7468 chuẩn hóa PRIVATE KEY và PUBLIC KEY cho trao đổi tổng quát; khi tạo định dạng mới, ưu tiên hai nhãn tổng quát này để tăng khả năng tương thích.

X509 CERTIFICATE, X.509 CERTIFICATE và CRL là những nhãn từng được một số công cụ sử dụng. RFC 7468 chọn CERTIFICATE và X509 CRL làm nhãn chuẩn. Một số implementation vẫn chấp nhận alias vì tương thích, nhưng không nên tạo dữ liệu mới dựa vào alias cũ.

## 4. Khóa công khai và khóa riêng

Một cặp khóa bất đối xứng gồm hai thành phần có quan hệ toán học:

- **Public key** có thể phân phối cho người khác. Tùy thuật toán, nó được dùng để xác minh chữ ký hoặc tham gia mã hóa/thỏa thuận khóa.
- **Private key** phải được bảo vệ. Tùy thuật toán, nó được dùng để ký, giải mã hoặc hoàn tất thao tác mật mã tương ứng.

Không phải thuật toán nào cũng dùng cùng một luồng thao tác. Ví dụ, với chữ ký số, bên ký dùng private key và bên kiểm tra dùng public key. Với TLS hiện đại, khóa công khai của chứng thư thường tham gia xác thực và trao đổi khóa; không nên diễn giải đơn giản rằng dữ liệu phiên luôn được mã hóa trực tiếp bằng public key của máy chủ.

### SubjectPublicKeyInfo — PUBLIC KEY

PUBLIC KEY chứa cấu trúc SPKI: thuật toán khóa công khai, tham số thuật toán nếu có và phần bit string chứa giá trị khóa. Vì có định danh thuật toán, ứng dụng có thể biết cần dùng RSA, EC, Ed25519 hoặc thuật toán khác được provider hỗ trợ.

Java biểu diễn cấu trúc này bằng X509EncodedKeySpec. Tên X509 trong lớp không có nghĩa dữ liệu là chứng thư X.509; đây là tên encoding của SubjectPublicKeyInfo.

### PKCS #8 / OneAsymmetricKey — PRIVATE KEY

PRIVATE KEY dùng định dạng tổng quát PKCS #8. Cấu trúc này cho biết thuật toán, tham số và phần private key theo cách riêng của thuật toán. RFC 5958 cập nhật cấu trúc này thành OneAsymmetricKey, cho phép mang thêm public key và thuộc tính tùy chọn.

PRIVATE KEY không đồng nghĩa với khóa đã được mã hóa bằng mật khẩu. Nếu nội dung là PKCS #8 không mã hóa, người có quyền đọc file có thể trích xuất khóa riêng.

### ENCRYPTED PRIVATE KEY

Nhãn này chứa EncryptedPrivateKeyInfo: thông tin thuật toán mã hóa và dữ liệu khóa riêng đã mã hóa. Người đọc phải có mật khẩu phù hợp và thuật toán mã hóa/KDF được hỗ trợ mới giải mã được.

Không dùng các header mã hóa PEM cũ kiểu Proc-Type/DEK-Info cho luồng mới. Ưu tiên encrypted PKCS #8 với cấu hình mã hóa hiện đại được thư viện hoặc nền tảng hỗ trợ. Bảo vệ file bằng quyền truy cập phù hợp và lấy mật khẩu từ secret manager; không ghi mật khẩu, private key hay nội dung PEM bí mật vào log, mã nguồn, ticket hoặc tham số dòng lệnh.

## 5. Chứng thư X.509 không phải chỉ là một public key

Một chứng thư X.509 thường chứa:

- Subject: chủ thể mà chứng thư mô tả.
- Issuer: CA hoặc chủ thể đã ký phát hành chứng thư.
- Serial number: số định danh chứng thư trong phạm vi issuer.
- Validity: thời điểm bắt đầu và kết thúc hiệu lực.
- Subject Public Key Info: khóa công khai và thuật toán.
- Extensions: mục đích sử dụng khóa, tên DNS/IP, ràng buộc CA, chính sách, CRL distribution points, authority information access và các thông tin khác.
- Signature algorithm và chữ ký của issuer trên phần thông tin chứng thư.

Nhãn PEM CERTIFICATE chứa cấu trúc X.509 Certificate. Chứng thư công khai thường có thể gửi cho client hoặc lưu cùng cấu hình TLS. Chứng thư không chứa private key tương ứng.

Có thể lấy public key từ chứng thư bằng X509Certificate.getPublicKey(). Tuy nhiên, việc trích xuất thành công không chứng minh chứng thư đáng tin cậy. Ứng dụng vẫn phải kiểm tra:

1. Chữ ký của chứng thư và đường dẫn đến trust anchor đáng tin cậy.
2. Thời hạn hiệu lực và các quy tắc path validation.
3. Key usage, extended key usage, basic constraints và name constraints phù hợp mục đích.
4. Tên máy chủ hoặc danh tính mà ứng dụng đang xác minh.
5. Trạng thái thu hồi theo chính sách của hệ thống.

Gọi certificate.verify(issuerPublicKey) chỉ kiểm tra chữ ký chứng thư bằng khóa công khai được cung cấp. Nó không tự xây dựng đường dẫn tin cậy, không tự xác minh hostname, không kiểm tra toàn bộ extension và không thay thế PKIX validation.

### CSR không phải certificate

CERTIFICATE REQUEST chứa yêu cầu cấp chứng thư PKCS #10, thường gồm subject, public key, thuộc tính yêu cầu và chữ ký chứng minh người tạo nắm private key tương ứng. CSR được gửi đến CA để CA xem xét. Chỉ khi CA phát hành chứng thư, ứng dụng mới có một CERTIFICATE được CA ký. Không đưa CSR vào trust store như thể nó là chứng thư đã được xác thực.

## 6. CRL là danh sách trạng thái thu hồi

CRL là cấu trúc X.509 CertificateList, được phát hành và ký bởi CA hoặc CRL issuer được ủy quyền. CRL thường có:

- Issuer của CRL.
- thisUpdate: thời điểm CRL được phát hành hoặc bắt đầu áp dụng.
- nextUpdate: thời điểm dự kiến có CRL mới.
- Danh sách chứng thư bị thu hồi, thường xác định bằng serial number trong phạm vi issuer.
- Thời điểm thu hồi và reason code nếu có.
- Chữ ký số của bên phát hành CRL.

CRL không chứa private key và không phải bản sao của các chứng thư bị thu hồi. Nó cho biết một chứng thư trong phạm vi CRL đã bị thu hồi hay chưa. Một CRL có thể chứa nhiều mục; không tìm thấy serial number trong CRL không đủ để kết luận chứng thư được tin cậy nếu CRL sai issuer, hết hạn, không đúng phạm vi hoặc chữ ký không hợp lệ.

Khi xử lý CRL, cần xác minh issuer, chữ ký, thisUpdate/nextUpdate, phạm vi áp dụng, CRL distribution point, indirect/delta CRL nếu hệ thống sử dụng. Chỉ sau khi kiểm tra CRL phù hợp mới dùng X509CRL.isRevoked(certificate) để tra cứu trạng thái.

CRL và OCSP là hai cơ chế kiểm tra thu hồi khác nhau:

| Cơ chế | Cách hoạt động | Đặc điểm |
|---|---|---|
| CRL | Tải danh sách đã ký và tra serial number cục bộ | Có thể lớn; dữ liệu được cập nhật theo chu kỳ |
| OCSP | Hỏi responder về trạng thái của một chứng thư cụ thể | Phản hồi theo chứng thư; phụ thuộc khả năng truy cập responder và chính sách cache |

Trong ứng dụng Java, nên cấu hình kiểm tra thu hồi ở tầng PKIX/TLS theo chính sách triển khai, thay vì chỉ đọc CRL rồi tự suy luận toàn bộ trạng thái tin cậy. Một CRL cũ hoặc không đúng issuer không thể dùng để kết luận an toàn.

## 7. Đọc các loại PEM bằng Java 26

JDK 26 bổ sung PEMDecoder và PEMEncoder trong JEP 524 dưới dạng **preview lần thứ hai**. Decoder có thể biến các nhãn phổ biến thành đối tượng Java tương ứng. Ví dụ sau chỉ minh họa đọc chứng thư, khóa công khai, khóa riêng và CRL:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.cert.X509CRL;
import java.security.cert.X509Certificate;

public class ReadPemObjects {
    public static void main(String[] args) throws Exception {
        PEMDecoder decoder = PEMDecoder.of();

        String certificatePem =
                Files.readString(Path.of("server-cert.pem"));
        X509Certificate certificate =
                decoder.decode(certificatePem, X509Certificate.class);

        String publicKeyPem =
                Files.readString(Path.of("public-key.pem"));
        PublicKey publicKey =
                decoder.decode(publicKeyPem, PublicKey.class);

        String privateKeyPem =
                Files.readString(Path.of("private-key.pem"));
        PrivateKey privateKey =
                decoder.decode(privateKeyPem, PrivateKey.class);

        String crlPem =
                Files.readString(Path.of("issuer.crl.pem"));
        X509CRL crl =
                decoder.decode(crlPem, X509CRL.class);

        System.out.println("Certificate subject: "
                + certificate.getSubjectX500Principal());
        System.out.println("Public-key algorithm: "
                + publicKey.getAlgorithm());
        System.out.println("Private-key algorithm: "
                + privateKey.getAlgorithm());
        System.out.println("CRL issuer: "
                + crl.getIssuerX500Principal());
    }
}
```

Đoạn mã yêu cầu file có đúng nhãn mà decoder hỗ trợ: CERTIFICATE, PUBLIC KEY, PRIVATE KEY và X509 CRL. Nếu thuật toán hoặc provider không hỗ trợ nội dung khóa, việc giải mã có thể thất bại. Không dùng PrivateKey.toString() hoặc log đối tượng/encoding private key trong ứng dụng thật.

Với khóa riêng được mã hóa bằng PKCS #8:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.util.Arrays;

static PrivateKey readEncryptedPrivateKey(char[] password)
        throws Exception {
    try {
        String pem = Files.readString(Path.of("private-key-encrypted.pem"));
        return PEMDecoder.of()
                .withDecryption(password)
                .decode(pem, PrivateKey.class);
    } finally {
        Arrays.fill(password, '\0');
    }
}
```

Mật khẩu trong ví dụ phải được lấy từ nguồn quản lý bí mật phù hợp; không hard-code trong mã. Việc xóa mảng char[] của ứng dụng sau khi dùng giúp giảm thời gian giữ bản sao do ứng dụng quản lý, nhưng không bảo đảm mọi bản sao nội bộ trong provider/JVM đã bị xóa ngay.

### Bật preview đúng phiên bản

Với JDK 26, bật preview ở cả lúc biên dịch và lúc chạy:

```bash
javac --release 26 --enable-preview -d out src/ReadPemObjects.java
java --enable-preview -cp out ReadPemObjects
```

Không cần thêm module ngoài cho java.security.PEMDecoder, nhưng API này vẫn là preview. Không dùng lớp đã biên dịch với preview JDK 26 như artifact tương thích với preview của JDK khác.

## 8. API Java ổn định và ranh giới xử lý PEM

Nhiều API JCA dùng để xử lý đối tượng sau khi đã có dữ liệu DER là API ổn định từ lâu:

- CertificateFactory.getInstance("X.509") tạo X509Certificate, CertPath, X509CRL từ encoding được hỗ trợ. API này đọc được một hoặc nhiều chứng thư PEM CERTIFICATE theo hợp đồng của Java SE.
- KeyFactory tạo PublicKey từ X509EncodedKeySpec (SPKI) và PrivateKey từ PKCS8EncodedKeySpec (PKCS #8), khi provider hỗ trợ thuật toán tương ứng.
- CertPathValidator với PKIX kiểm tra đường dẫn chứng thư theo trust anchors và tham số chính sách.
- KeyStore với loại PKCS12 phù hợp để quản lý khóa riêng và chuỗi chứng thư trong một keystore có bảo vệ mật khẩu, thay vì tự tạo cơ chế lưu trữ bí mật.

Ví dụ đọc một chứng thư PEM bằng API ổn định:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

static X509Certificate readCertificate() throws Exception {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    try (InputStream in = Files.newInputStream(Path.of("server-cert.pem"))) {
        return (X509Certificate) factory.generateCertificate(in);
    }
}
```

Đối với khóa công khai/khóa riêng, KeyFactory làm việc với cấu trúc DER, không phải tự động hiểu mọi biến thể PEM. Nếu cần tương thích với JDK không có PEM API ổn định, ứng dụng phải dùng parser PEM được kiểm chứng để lấy đúng DER payload theo nhãn, rồi mới tạo X509EncodedKeySpec hoặc PKCS8EncodedKeySpec. Không chỉ xóa chuỗi BEGIN/END bằng xử lý chuỗi tùy tiện đối với file không tin cậy; cần kiểm tra đúng nhãn, Base64, giới hạn kích thước, cấu trúc DER và lỗi parse.

Ví dụ dưới đây nhận byte array DER đã được parser PEM kiểm tra và tách đúng theo nhãn. Với thuật toán khác RSA, thay tên thuật toán bằng tên mà provider hỗ trợ:

```java
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

static PublicKey publicKeyFromSpki(byte[] spkiDer) throws Exception {
    return KeyFactory.getInstance("RSA")
            .generatePublic(new X509EncodedKeySpec(spkiDer));
}

static PrivateKey privateKeyFromPkcs8(byte[] pkcs8Der) throws Exception {
    return KeyFactory.getInstance("RSA")
            .generatePrivate(new PKCS8EncodedKeySpec(pkcs8Der));
}
```

Các spec class này nhận dữ liệu nhị phân của cấu trúc tương ứng; không truyền nguyên chuỗi PEM có header/footer hoặc chuỗi Base64 chưa giải mã vào constructor.

## 9. Phân biệt trạng thái PEM API qua các phiên bản JDK

PEM API được đưa vào JDK qua nhiều vòng preview. Không nhầm sự tồn tại của lớp trong java.security với việc API đã ổn định:

| Phiên bản | JEP | Trạng thái |
|---|---|---|
| JDK 25 | JEP 470 | Preview lần thứ nhất |
| JDK 26 | JEP 524 | Preview lần thứ hai; dùng DEREncodable, PEMRecord và withFactory(...) |
| JDK 27 | JEP 538 | Preview lần thứ ba; đổi DEREncodable thành BinaryEncodable, PEMRecord thành PEM, và cập nhật tên API provider factory |
| JDK 28 | JEP 542 | Được đưa vào lộ trình hoàn tất API; JDK 28 chưa GA tại ngày 27/11/2026 |

Trong JDK 26, PEMDecoder và PEMEncoder đều là preview, nên ví dụ phải bật --enable-preview. JDK 27 tiếp tục preview lần thứ ba và có thay đổi tên kiểu/phương thức; cần biên dịch lại theo API JDK 27. JEP 542 đã hoàn tất trong quá trình phát triển JDK 28, nhưng bản phát hành JDK 28 chưa GA tại thời điểm bài viết. Khi dùng một bản early-access, hãy kiểm tra tài liệu API đúng build và trạng thái preview thực tế; đừng suy ra từ JDK 26/27 hoặc một bản snapshot cũ.

Với thư viện cần tương thích dài hạn trên các JDK đã phát hành, có thể tiếp tục dùng các API ổn định như CertificateFactory, KeyFactory, KeyStore và một parser PEM đáng tin cậy phù hợp với định dạng đầu vào. Chỉ chuyển sang PEMDecoder/PEMEncoder khi phiên bản JDK triển khai đã cung cấp API ở trạng thái mà chính sách sản phẩm chấp nhận.

## 10. Kiểm tra chứng thư và CRL sau khi parse

Parse thành công chỉ chứng minh dữ liệu có thể được chuyển thành một đối tượng Java. Nó không chứng minh chứng thư hoặc CRL đáng tin cậy. Với chứng thư, cần kiểm tra chuỗi CA và chính sách sử dụng; với CRL, cần kiểm tra issuer, chữ ký, thời hạn và phạm vi.

Ví dụ minh họa kiểm tra chữ ký CRL và tra cứu chứng thư sau khi đã có chứng thư issuer phù hợp:

```java
import java.security.cert.X509CRL;
import java.security.cert.X509Certificate;
import java.util.Date;

static boolean isRevokedByVerifiedCrl(
        X509Certificate certificate,
        X509Certificate crlIssuer,
        X509CRL crl) throws Exception {

    if (!crl.getIssuerX500Principal()
            .equals(crlIssuer.getSubjectX500Principal())) {
        throw new SecurityException("CRL issuer không khớp");
    }

    crl.verify(crlIssuer.getPublicKey());

    Date now = new Date();
    if (crl.getThisUpdate() == null
            || crl.getThisUpdate().after(now)
            || crl.getNextUpdate() == null
            || crl.getNextUpdate().before(now)) {
        throw new SecurityException("CRL không còn trong khoảng hiệu lực");
    }

    return crl.isRevoked(certificate);
}
```

Đây chỉ là bước kiểm tra minh họa, chưa phải một trình xác thực PKIX đầy đủ. Hệ thống thật còn phải kiểm tra CRL distribution point và phạm vi áp dụng, quyền phát hành CRL, indirect/delta CRL nếu có, đường dẫn tin cậy của issuer, thuật toán/chính sách mật mã và trạng thái chứng thư issuer. Nên dùng CertPathValidator/PKIX revocation checker hoặc TLS stack được cấu hình đúng chính sách thay vì tự triển khai toàn bộ PKI.

Đối với chứng thư TLS, còn phải kiểm tra hostname/SAN và mục đích sử dụng serverAuth; việc chữ ký CA hợp lệ không tự chứng minh chứng thư phù hợp với hostname đang kết nối. Không thêm một chứng thư vào trust store chỉ vì nó xuất hiện trong cùng file PEM với chứng thư máy chủ.

## 11. Nguyên tắc bảo vệ và trao đổi dữ liệu

- Không chia sẻ PRIVATE KEY chưa mã hóa. Ưu tiên encrypted PKCS #8, secret manager hoặc keystore được quản lý; hạn chế quyền đọc file và tránh đưa khóa vào log/backup không bảo vệ.
- Không coi PUBLIC KEY là đã xác thực. So sánh fingerprint qua kênh tin cậy hoặc xác minh chứng thư và chuỗi CA.
- Không coi CERTIFICATE hợp lệ chỉ vì parse thành công. Thực hiện path validation, kiểm tra thời hạn, hostname, key usage và revocation.
- Không coi CRL mới tải về là đáng tin cậy trước khi xác minh chữ ký, issuer, thời gian và phạm vi.
- Không dựa vào phần mở rộng .pem, .crt, .cer hoặc .key để đoán cấu trúc. Đọc nhãn PEM và xác nhận cấu trúc ASN.1.
- Không tạo các nhãn cũ hoặc alias không chuẩn cho dữ liệu mới. Ưu tiên PUBLIC KEY, PRIVATE KEY, ENCRYPTED PRIVATE KEY, CERTIFICATE, X509 CRL theo RFC 7468.
- Không tự viết bộ giải mã ASN.1 hoặc xử lý PEM tổng quát bằng regex trong production. Dùng API JDK hoặc thư viện mật mã được duy trì và kiểm thử.
- Nếu cần giữ private key lâu dài trong ứng dụng, cân nhắc PKCS12 KeyStore hoặc phần cứng/secret provider thay vì file PEM thuần.

## 12. Những điểm cần nhớ

- Public key và private key là hai phần của cặp khóa; private key phải được bảo vệ, public key cần được xác thực nguồn gốc.
- Certificate gắn public key với một chủ thể bằng chữ ký issuer; nó không chứa private key.
- CRL là danh sách chứng thư bị thu hồi do issuer ký; cần xác minh chữ ký, issuer, thời gian và phạm vi trước khi tra cứu.
- PUBLIC KEY là SubjectPublicKeyInfo; PRIVATE KEY là PKCS #8/OneAsymmetricKey; ENCRYPTED PRIVATE KEY là EncryptedPrivateKeyInfo.
- CERTIFICATE chứa X.509 Certificate; X509 CRL chứa CertificateList; CERTIFICATE REQUEST là CSR chưa được CA cấp chứng thư.
- PEM là Base64 và nhãn văn bản, không phải cơ chế mã hóa hay xác thực.
- PEMDecoder/PEMEncoder là preview trong JDK 26 và JDK 27; JDK 28 đang hoàn tất JEP 542 nhưng chưa GA tại ngày 27/11/2026.
- Parse PEM thành công không thay thế kiểm tra PKIX, hostname, key usage và trạng thái thu hồi.

## Tài liệu tham khảo

- [RFC 7468: Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html)
- [RFC 5280: Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [RFC 5958: Asymmetric Key Packages — OneAsymmetricKey](https://www.rfc-editor.org/rfc/rfc5958.html)
- [RFC 8017: PKCS #1 — RSA Cryptography Specifications](https://www.rfc-editor.org/rfc/rfc8017.html)
- [RFC 2986: PKCS #10 — Certification Request Syntax](https://www.rfc-editor.org/rfc/rfc2986.html)
- [Java SE 26 API: PEMDecoder (Second Preview)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html)
- [Java SE 26 API: PEMEncoder (Second Preview)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html)
- [Java SE 26 API: CertificateFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertificateFactory.html)
- [Java SE 26 API: X509Certificate](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/X509Certificate.html)
- [Java SE 26 API: X509CRL](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/X509CRL.html)
- [JEP 524: PEM Encodings of Cryptographic Objects (Second Preview), JDK 26](https://openjdk.org/jeps/524)
- [JEP 538: PEM Encodings of Cryptographic Objects (Third Preview), JDK 27](https://openjdk.org/jeps/538)
- [JEP 542: PEM Encodings of Cryptographic Objects, JDK 28](https://openjdk.org/jeps/542)
- [Inside Java: JDK 27 Security Enhancements](https://inside.java/2026/09/16/jdk27-security-enhancements/)
