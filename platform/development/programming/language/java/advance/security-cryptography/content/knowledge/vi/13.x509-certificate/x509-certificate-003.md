# 13.3 Đọc chứng thư bằng CertificateFactory từ DER hoặc PEM

Trong Java, `java.security.cert.CertificateFactory` là API tiêu chuẩn để **đọc (parse) chứng thư X.509 từ dữ liệu đã mã hóa**. Một chứng thư có thể được cung cấp dưới dạng **DER nhị phân** hoặc **PEM văn bản**; sau khi đọc, Java trả về đối tượng `X509Certificate` để xem subject, issuer, public key, số serial, thời gian hiệu lực và các extension.

Điểm quan trọng nhất: **đọc được chứng thư không có nghĩa là chứng thư được tin cậy**. `CertificateFactory.generateCertificate(...)` kiểm tra/giải mã cấu trúc chứng thư, nhưng **không tự xác minh chuỗi CA tin cậy, hostname, mục đích sử dụng, thu hồi hoặc chính sách TLS**. Bài này trình bày đúng phạm vi đọc DER/PEM và chỉ rõ ranh giới với kiểm tra trust để tránh nhầm lẫn.

Sau bài này, bạn có thể:

- Phân biệt DER (binary ASN.1) và PEM (`BEGIN/END CERTIFICATE` + Base64 DER) về nội dung thực.
- Dùng `CertificateFactory.getInstance("X.509")` cùng `generateCertificate(InputStream)` để đọc một chứng thư từ file DER hoặc PEM.
- Sử dụng `generateCertificates(InputStream)` khi một nguồn chứa nhiều chứng thư hoặc bộ chứng thư PKCS#7.
- Truy xuất trường X.509 một cách an toàn, phân biệt thông tin metadata với kết quả kiểm tra trust.
- Xử lý `CertificateException` và lỗi I/O đúng tầng, không mặc định rằng đuôi file quyết định định dạng.
- Kiểm chứng bằng chương trình Java 17+ có thể chạy, bao gồm so sánh cùng một chứng thư sau khi parse qua DER và PEM.

## 1. Chứng thư X.509 là gì và không phải là gì?

Chứng thư X.509 là cấu trúc dữ liệu đã được ký, thường liên kết **public key** với một tập thuộc tính của chủ thể do issuer chứng nhận theo chính sách PKI. Các thành phần điển hình:

| Trường / thành phần | Ý nghĩa |
| --- | --- |
| **Subject** | Danh tính được mô tả trong chứng thư (Distinguished Name). Với TLS, tên miền thường được kiểm tra qua **Subject Alternative Name (SAN)**, không chỉ dựa vào CN. |
| **Issuer** | Danh tính bên phát hành chứng thư (thường là CA); tên issuer một mình chưa chứng minh chứng thư do CA tin cậy cấp. |
| **Serial number** | Số định danh chứng thư do issuer gán; không phải private key. |
| **NotBefore / NotAfter** | Khoảng thời gian hiệu lực ghi trong chứng thư. |
| **Subject Public Key Info** | Public key và thuật toán/bộ tham số liên quan. |
| **Signature algorithm + signature** | Cách chứng thư được ký và giá trị chữ ký của bên phát hành. |
| **Extensions** | SAN, KeyUsage, ExtendedKeyUsage, BasicConstraints, Authority Key Identifier, Subject Key Identifier, CRL Distribution Points và các trường khác. |

Bên ngoài còn có private key tương ứng public key nhưng **private key không nằm trong chứng thư X.509**. Đọc file `.cer` hoặc `.pem` chứa **CERTIFICATE** không có nghĩa đã lấy được khóa bí mật để ký hay giải mã.

Một chứng thư có thể:
- Được parse hoàn toàn hợp lệ nhưng **hết hạn**.
- Có chữ ký toán học đúng nhưng chuỗi CA không được tin cậy.
- Thuộc CA được tin cậy nhưng **không hợp lệ cho hostname hoặc mục đích** của yêu cầu.
- Là chứng thư tự ký hợp lệ về cú pháp, nhưng không phải trust anchor của hệ thống.
- Chứa public key dùng được cho kiểm tra chữ ký, nhưng chưa thể dùng để nhận diện một người/service cho tới khi trust policy chấp nhận.

Do đó cần phân biệt rõ **parse**, **kiểm tra thời gian**, **kiểm tra chữ ký chứng thư**, **xây dựng/kiểm tra cert path**, và **ràng buộc danh tính ứng dụng**.

## 2. DER và PEM: cùng dữ liệu X.509, hai hình thức biểu diễn

### 2.1. DER — binary encoding

**DER (Distinguished Encoding Rules)** là tập quy tắc mã hóa ASN.1 xác định duy nhất biểu diễn nhị phân của một cấu trúc. Một chứng thư X.509 DER là **dãy byte nhị phân**, không phải UTF-8 văn bản có thể đọc bằng mắt.

~~~text
cert.der hoặc cert.cer
┌───────────────────────────────────────────────┐
│ Các byte ASN.1 DER của X.509 Certificate       │
│ SEQUENCE { tbsCertificate, signatureAlgorithm, │
│            signatureValue }                    │
└───────────────────────────────────────────────┘
~~~

Một vài file extension có thể gặp: `.der`, `.cer`, `.crt`. **Đuôi file không có ý nghĩa mật mã bắt buộc**: `.cer` có thể chứa DER hoặc PEM tùy nguồn, còn `.crt` cũng có thể là cả hai. Dựa vào **nội dung và giao thức cung cấp**, không dựa vào đuôi file khi quyết định parser.

Sai lầm phổ biến là đọc DER bằng `Files.readString(path)` rồi Base64-decode hoặc cố xử lý bằng regex. Binary DER phải được đưa vào `InputStream`/`byte[]` như dữ liệu nhị phân, không tự ý đổi encoding chữ.

### 2.2. PEM — text armor của DER

**PEM** trong trường hợp chứng thư là biểu diễn Base64 của **cùng byte DER**, được bao bằng đúng marker:

~~~text
-----BEGIN CERTIFICATE-----
MIIB...các dòng Base64 DER...ABCD
-----END CERTIFICATE-----
~~~

Đây là **sơ đồ minh họa**, chuỗi Base64 bị rút gọn ở trên **không phải chứng thư có thể parse**. PEM đúng thực sự phải chứa toàn bộ DER hợp lệ, được encode Base64; phần đầu và cuối phải đúng.

Đặc điểm:
- PEM chứng thư chứa **DER đã Base64 hóa** và các marker. Nó không biến public key thành private key, không thêm trust.
- Dấu xuống dòng trong phần Base64 thường dùng độ dài dòng dễ đọc (ví dụ 64 ký tự), không phải trường X.509.
- File PEM có thể chứa **một hoặc nhiều** khối `BEGIN CERTIFICATE`, tùy định dạng/giao thức.
- `-----BEGIN PUBLIC KEY-----` là biểu diễn public key riêng, **không phải nguyên một chứng thư**.
- `-----BEGIN PRIVATE KEY-----`, `-----BEGIN ENCRYPTED PRIVATE KEY-----` hoặc `-----BEGIN RSA PRIVATE KEY-----` chứa khóa private theo định dạng tương ứng, **không được đưa vào CertificateFactory** với kỳ vọng tạo `X509Certificate`.
- `-----BEGIN CERTIFICATE REQUEST-----` (CSR) cũng không phải chứng thư đã phát hành.
- `-----BEGIN PKCS7-----` hoặc file PKCS#7/`.p7b` có thể chứa **bộ chứng thư**, cần dùng đúng API/định dạng và không nhầm là DER của một certificate đơn lẻ.

**Quan hệ DER/PEM:**

~~~text
DER bytes
   |
   | Base64 encode + BEGIN/END CERTIFICATE + xuống dòng
   v
PEM text
   |
   | bỏ armor + Base64 decode theo cấu trúc
   v
DER bytes ban đầu

CertificateFactory("X.509").generateCertificate(...)
          |
          v
X509Certificate
~~~

Không cần tự viết PEM parser thủ công chỉ để đọc chứng thư. Theo hợp đồng Java SE 17, X.509 `CertificateFactory.generateCertificate(InputStream)` phải nhận chứng thư **DER binary** hoặc DER ở dạng **printable Base64** với marker `BEGIN/END CERTIFICATE` chính xác.

### 2.3. Bảng so sánh

| Tiêu chí | DER | PEM |
| --- | --- | --- |
| Dạng vật lý | Binary ASN.1 DER | ASCII text gồm Base64 DER + marker |
| Đọc trực tiếp bằng text editor | Không thích hợp | Có thể nhìn marker và Base64, nhưng không thấy ý nghĩa trường X.509 |
| Hàm đọc X.509 Java | `generateCertificate(InputStream)` | **Cùng hàm** `generateCertificate(InputStream)` |
| Có cần `Base64.getDecoder()` trước không? | Không | **Không** nếu đưa PEM chuẩn trực tiếp vào `CertificateFactory` |
| Private key có nằm sẵn không? | Không, nếu file đúng là X.509 certificate | Không, nếu khối đúng là `CERTIFICATE` |
| Trust được kiểm tra khi parse? | **Không** | **Không** |
| Dung lượng | Thường nhỏ hơn PEM vì không có Base64/marker | Thường lớn hơn DER vì Base64/marker |
| Nhiều certificate | Một hoặc nhiều DER theo định dạng/bộ dữ liệu phù hợp | Có thể nối nhiều khối CERTIFICATE trong một nguồn |

## 3. API chuẩn: `CertificateFactory` và `X509Certificate`

Hai import chính:

~~~java
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
~~~

Đọc một chứng thư, bất kể DER hay PEM chuẩn:

~~~java
CertificateFactory factory = CertificateFactory.getInstance("X.509");
X509Certificate cert = (X509Certificate) factory.generateCertificate(inputStream);
~~~

Đây là **mảnh code minh họa**, cần có `inputStream` thực và xử lý exception. Với factory loại `"X.509"`, chuẩn Java yêu cầu chứng thư trả về có thể biểu diễn bằng `X509Certificate`.

| API | Vai trò |
| --- | --- |
| `CertificateFactory.getInstance("X.509")` | Chọn certificate factory theo JCA provider lookup. Java SE yêu cầu hỗ trợ loại X.509. |
| `getInstance("X.509", providerName)` | Chọn provider theo tên đã đăng ký khi triển khai yêu cầu; không bắt buộc cho ứng dụng thông thường. |
| `factory.getProvider()` | Cho biết provider xử lý parsing, hữu ích cho kiểm thử tương thích. |
| `factory.generateCertificate(InputStream)` | Đọc **một chứng thư** từ stream; ném `CertificateException` nếu parse thất bại. |
| `factory.generateCertificates(InputStream)` | Đọc một **collection** chứng thư từ stream chứa chuỗi các chứng thư/PKCS#7, có thể là collection rỗng. |
| `factory.generateCertPath(...)` | Tạo đối tượng `CertPath` từ encoding path hoặc danh sách chứng thư; **chưa phải validate trust**. |
| `cert.getSubjectX500Principal()` | Trả `X500Principal` của subject (ưu tiên hơn API `getSubjectDN()` đã deprecated). |
| `cert.getIssuerX500Principal()` | Trả `X500Principal` của issuer. |
| `cert.getNotBefore()/getNotAfter()` | Trả giới hạn thời gian trong chứng thư. |
| `cert.getPublicKey()` | Trả public key từ chứng thư. |
| `cert.getEncoded()` | Trả binary DER của certificate; không phải PEM, không phải private key. |
| `cert.checkValidity()` | Kiểm tra **thời gian hiệu lực hiện tại**; không kiểm tra toàn bộ trust chain. |
| `cert.verify(issuerPublicKey)` | Kiểm tra chữ ký của chứng thư bằng public key đã cho; không chứng minh issuer được tin cậy. |

### 3.1. Lỗi theo API

- `getInstance("X.509")` có thể ném `CertificateException` nếu type/provider không tồn tại; `getInstance(type, name)` còn có thể ném `NoSuchProviderException`. X.509 là loại bắt buộc trên Java SE, nhưng provider cụ thể có thể không hỗ trợ.
- `generateCertificate(...)` ném `CertificateException` khi parse dữ liệu lỗi.
- `Files.newInputStream` hoặc `Files.size` có thể ném `IOException`, `NoSuchFileException`, `AccessDeniedException` — đây là lỗi **đọc file**, không phải lỗi ASN.1.
- `cert.checkValidity()` có thể ném `CertificateExpiredException` hoặc `CertificateNotYetValidException` dù việc parse đã thành công.
- Xử lý PKIX có thể ném `CertPathValidatorException` và lỗi trust/policy khác. Đừng quy mọi lỗi kiểu đó thành “DER/PEM hỏng”.

### 3.2. Đọc một file so với bundle

**Một file có một certificate**: `generateCertificate(in)` phù hợp và rõ nghĩa.

**Một file có nhiều PEM blocks** hoặc PKCS#7 certificate set: `generateCertificates(in)` thường hợp lý hơn; nó trả collection, **không hứa hẹn** thứ tự đã là chain leaf -> intermediate -> root, cũng không hứa collection đủ để tạo một trust path hợp lệ.

**Một cert path cần được xây dựng/validate**: chuẩn bị danh sách/chứng thư đúng thứ tự, trust anchors và chính sách PKIX; việc tạo đối tượng `CertPath` không tương đương kiểm tra thành công `CertPathValidator.validate(...)`.

## 4. Chương trình Java 17+: đọc file DER hoặc PEM bằng cùng một hàm

Chương trình dưới đây là ví dụ chính của bài: `ReadX509File.java` chỉ nhận **đường dẫn một file chứa một chứng thư**. Nó không dùng kiểm tra file extension; `CertificateFactory("X.509")` quyết định parse dựa trên nội dung DER/PEM hợp lệ.

**Tệp: `ReadX509File.java`**

~~~java
import java.io.BufferedInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HexFormat;

public class ReadX509File {
    static X509Certificate parse(InputStream in)
            throws CertificateException {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(in);
    }

    static void inspect(X509Certificate cert) throws Exception {
        System.out.println("Type: " + cert.getType());
        System.out.println("Version: " + cert.getVersion());
        System.out.println("Subject: " + cert.getSubjectX500Principal());
        System.out.println("Issuer: " + cert.getIssuerX500Principal());
        System.out.println("Serial (hex): "
                + cert.getSerialNumber().toString(16));
        System.out.println("Not before: "
                + cert.getNotBefore().toInstant());
        System.out.println("Not after: "
                + cert.getNotAfter().toInstant());
        System.out.println("Public key algorithm: "
                + cert.getPublicKey().getAlgorithm());

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(cert.getEncoded());
        System.out.println("SHA-256 DER fingerprint: "
                + HexFormat.of().formatHex(digest));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java ReadX509File <certificate.der|certificate.pem>");
            return;
        }

        Path path = Path.of(args[0]);
        long fileSize = Files.size(path);
        if (fileSize == 0 || fileSize > 1024L * 1024L) {
            throw new IllegalArgumentException(
                    "Empty or unexpectedly large certificate file");
        }

        try (InputStream in = new BufferedInputStream(
                Files.newInputStream(path))) {
            X509Certificate cert = parse(in);
            inspect(cert);
        }
    }
}
~~~

### 4.1. Biên dịch và chạy

~~~bash
javac ReadX509File.java
java ReadX509File certificate.der
java ReadX509File certificate.pem
~~~

Các file `certificate.der` và `certificate.pem` phải là chứng thư thực sự do bài tập/hệ thống cung cấp, không phải nội dung placeholder trong README. Nếu hai file chứa **cùng một chứng thư**, các trường đọc được và fingerprint SHA-256 trên **DER chuẩn hóa** sẽ giống nhau.

Đầu ra có cấu trúc:

~~~text
Type: X.509
Version: <phiên bản từ chứng thư, thường là 3>
Subject: <tên subject từ chứng thư>
Issuer: <tên issuer từ chứng thư>
Serial (hex): <serial thực của chứng thư>
Not before: <thời điểm trong chứng thư>
Not after: <thời điểm trong chứng thư>
Public key algorithm: <RSA, EC hoặc thuật toán thực>
SHA-256 DER fingerprint: <64 ký tự hex của digest SHA-256>
~~~

Các dòng trong dấu `<...>` là **mô tả biến động theo input**, không phải stdout cố định để chép nguyên văn. Trong mọi trường hợp parse thành công bằng X.509 factory, dòng `Type: X.509` là kết quả mong đợi.

### 4.2. Giải thích cặn kẽ

1. `CertificateFactory.getInstance("X.509")` tạo engine parse chứng thư, **không cần tạo `KeyFactory`** và không cần private key.
2. `Files.newInputStream(path)` đọc byte gốc, **không chuyển DER thành `String`**. `BufferedInputStream` hỗ trợ `mark/reset` và dùng `try-with-resources` để đóng file đúng cách.
3. `generateCertificate(in)` nhận DER binary hoặc PEM Base64 có marker hợp lệ. Khi source chỉ chứa một cert, API này phù hợp.
4. `X509Certificate` cho phép xem subject/issuer/public key/validity. `getEncoded()` trả **DER**, nên SHA-256 của cùng cert là như nhau dù lúc nhập qua DER hoặc PEM.
5. SHA-256 fingerprint là **định danh byte của chứng thư**, không phải bằng chứng cert được tin cậy. Nếu dùng pinning, phải so fingerprint với giá trị **được cấp qua kênh tin cậy**, có kế hoạch rotation, không lấy fingerprint từ chính đầu vào chưa xác thực rồi cho rằng an toàn.
6. `Files.size` chỉ kiểm tra sơ bộ dung lượng; file có thể thay đổi giữa `size` và `open` (TOCTOU). Trong production, cần giới hạn **thực sự** số byte parser nhận, kiểm soát đường dẫn/symlink và nguồn dữ liệu. Ví dụ chủ yếu minh họa API X.509.
7. Chương trình **không gọi `checkValidity` và không validate PKIX**, vì mục tiêu hiện tại là **đọc/inspect**, không cấp quyết định trust. Nếu ứng dụng cần xác minh, phải có bước riêng.

### 4.3. Nếu chỉ cần subject và public key thì sao?

Có thể dùng:

~~~java
X509Certificate cert = ...; // Kết quả parse từ CertificateFactory.
System.out.println(cert.getSubjectX500Principal());
System.out.println(cert.getPublicKey().getAlgorithm());
~~~

Nhưng **không được cấp quyền truy cập** chỉ vì subject in ra giống `CN=example.com`. Subject DN là dữ liệu trong cert; kiểm tra tên miền TLS thường dựa trên SAN, và phải có chuỗi trust hợp lệ, hạn chế ExtendedKeyUsage/KeyUsage và các điều kiện chính sách khác.

## 5. Thử nghiệm không cần file: DER -> PEM -> parse cùng một chứng thư

Để xác thực trực tiếp cách Java đọc DER và PEM mà không cần mang một chứng thư giả cố định trong mã nguồn, ví dụ tiếp theo sử dụng **một chứng thư CA công khai sẵn có trong trust anchors mặc định của JVM** làm **dữ liệu thử nghiệm**. Mục đích là dùng byte thật của một chứng thư đã parse được để kiểm thử hai dạng encoding. Đây **không phải** ví dụ thiết lập trust policy mới hoặc chứng minh certificate do người dùng cung cấp được tin cậy.

**Điều kiện chạy:** JVM phải có ít nhất một X.509 trusted issuer trong trust manager mặc định. Một JVM dùng truststore trống/custom có thể không thỏa điều kiện này; khi đó dùng cert hợp lệ khác làm fixture test, không bỏ kiểm tra trust.

**Tệp: `CertificateFormatsDemo.java`**

~~~java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Base64;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public class CertificateFormatsDemo {
    static X509Certificate firstAnchorForDemonstration()
            throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init((KeyStore) null);

        for (TrustManager manager : tmf.getTrustManagers()) {
            if (manager instanceof X509TrustManager x509) {
                X509Certificate[] issuers = x509.getAcceptedIssuers();
                if (issuers.length > 0) {
                    return issuers[0];
                }
            }
        }
        throw new IllegalStateException(
                "No default trust anchor available for this demo");
    }

    public static void main(String[] args) throws Exception {
        byte[] der = firstAnchorForDemonstration().getEncoded();

        String pem = "-----BEGIN CERTIFICATE-----\n"
                + Base64.getMimeEncoder(
                        64, new byte[] {'\n'}).encodeToString(der)
                + "\n-----END CERTIFICATE-----\n";

        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        X509Certificate parsedDer = (X509Certificate)
                factory.generateCertificate(
                        new ByteArrayInputStream(der));

        X509Certificate parsedPem = (X509Certificate)
                factory.generateCertificate(
                        new ByteArrayInputStream(
                                pem.getBytes(StandardCharsets.US_ASCII)));

        System.out.println("DER type: " + parsedDer.getType());
        System.out.println("PEM type: " + parsedPem.getType());
        System.out.println("Same certificate: "
                + Arrays.equals(
                        parsedDer.getEncoded(), parsedPem.getEncoded()));

        int count = factory.generateCertificates(
                new ByteArrayInputStream(
                        (pem + pem).getBytes(StandardCharsets.US_ASCII)))
                .size();
        System.out.println("PEM bundle count: " + count);

        try {
            factory.generateCertificate(
                    new ByteArrayInputStream(new byte[] {0, 1, 2}));
            throw new AssertionError("Malformed DER accepted");
        } catch (CertificateException expected) {
            System.out.println("Malformed DER rejected: true");
        }
    }
}
~~~

Chạy bằng Java 17+ có trust anchors mặc định:

~~~bash
javac CertificateFormatsDemo.java
java CertificateFormatsDemo
~~~

Stdout đã kiểm chứng trên JVM có default trust anchors:

~~~text
DER type: X.509
PEM type: X.509
Same certificate: true
PEM bundle count: 2
Malformed DER rejected: true
~~~

### 5.1. Tại sao ví dụ này có giá trị?

- `getEncoded()` của `X509Certificate` là DER. Ta tái tạo PEM bằng `Base64.getMimeEncoder(64, new byte[]{'\n'})` và header/footer đúng, rồi đưa thẳng PEM vào `CertificateFactory`.
- Không cần `Base64.getDecoder()` trước khi gọi `generateCertificate` với PEM chuẩn, tránh lỗi gỡ marker và whitespace.
- `Arrays.equals(...)` so sánh **DER của chứng thư đã parse**, không so raw bytes của file: PEM và DER raw đương nhiên khác nhau, nhưng X.509 objects mô tả cùng certificate.
- `generateCertificates` xử lý hai khối PEM nối tiếp, trả số certificate tương ứng trong ví dụ (2). **Nó không tự sắp xếp hai certificate thành chain và không validate trust**.
- Input `{0,1,2}` không phải DER X.509; provider ném `CertificateException` khi cố parse. Ứng dụng thật cần kiểm soát message lỗi, không trả nội bộ parser cho client.

### 5.2. Có nên dùng cert từ trust manager để đọc file sản xuất?

Không. Trong bài, cert từ trust manager chỉ là **fixture thuận tiện** để có dữ liệu X.509 hợp lệ, giống như sử dụng sample cert trong test. Chương trình `ReadX509File` mới là ví dụ ứng dụng để đọc file do người dùng chỉ định. Trong hệ thống TLS thực, tin cậy peer certificate phải thông qua cơ chế JSSE/PKIX đã cấu hình, không chọn ngẫu nhiên `getAcceptedIssuers()[0]` làm trust policy.

## 6. Đọc nhiều chứng thư từ PEM bundle hoặc PKCS#7

Một số nguồn cung cấp:

- Một file PEM gồm nhiều đoạn `BEGIN CERTIFICATE`, thường chứa leaf và intermediate certificates.
- Một DER/PEM gói PKCS#7 SignedData chứa tập chứng thư.
- File chain do máy chủ TLS hoặc công cụ CA xuất ra; không nhất thiết chứa root CA.
- Một tập CA certificates dùng để nạp vào kho tin cậy.

**Không mặc định mọi file có nhiều certificate đã được sắp xếp hoặc chứng minh quan hệ issuer/subject.**

Với X.509 `CertificateFactory`:

~~~java
import java.io.InputStream;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.util.Collection;

CertificateFactory factory = CertificateFactory.getInstance("X.509");
try (InputStream in = /* stream của bundle đã được kiểm soát */) {
    Collection<? extends Certificate> certificates =
            factory.generateCertificates(in);
    for (Certificate item : certificates) {
        // Mỗi item có thể cast sang X509Certificate sau khi factory X.509 parse.
    }
}
~~~

Đây là **mảnh API minh họa**, không phải file Java độc lập vì `in` phụ thuộc nguồn thực. Khi viết code, nên dùng `try-with-resources` với stream đã mở, giới hạn số lượng cert/bytes và loại bỏ input rỗng nếu nghiệp vụ bắt buộc có ít nhất một certificate.

### 6.1. `generateCertificate` trên stream nhiều cert

JDK mô tả: nếu `InputStream` **không hỗ trợ `mark/reset`**, `generateCertificate` có thể tiêu thụ **toàn bộ stream**; nếu có hỗ trợ `mark/reset`, mỗi lần gọi sẽ đọc một certificate và đưa vị trí đọc tới sau marker kết thúc của certificate đó.

Vì vậy, với nhiều chứng thư:

- Ưu tiên `generateCertificates` nếu mục tiêu là lấy toàn bộ tập chứng thư từ một stream/bundle.
- Nếu cần đọc tuần tự từng cert bằng nhiều lần `generateCertificate`, dùng `BufferedInputStream` để cung cấp `mark/reset` và thiết kế điểm dừng phù hợp; đừng giả định mỗi lần gọi trên raw `FileInputStream` luôn tiêu thụ đúng một cert.
- `InputStream.available()` **không phải thước đo tổng kích thước** hoặc cách kiểm tra EOF đáng tin cậy cho mọi stream mạng. Ví dụ đọc file của JDK dùng `available` trên `BufferedInputStream`, nhưng ứng dụng streaming thực nên thiết kế EOF/protocol framing và giới hạn byte rõ ràng.
- `generateCertificates` có thể trả về collection trống trong trường hợp không có cert; phải xử lý nếu nghiệp vụ yêu cầu một hoặc nhiều certificate.

### 6.2. `CertPath` và thứ tự chain

`CertificateFactory.generateCertPath(List<? extends Certificate>)` tạo một `CertPath` với thứ tự danh sách mà ứng dụng đưa vào. Nếu cần dựng path, ứng dụng phải đảm bảo danh sách đúng **leaf -> intermediate -> ...** theo yêu cầu của PKIX/giao thức, hoặc dùng `CertPathBuilder` để dựng đường chứng thực.

**Một collection từ `generateCertificates` không mặc nhiên là trust chain hợp lệ.** Có thể có chứng thư không liên quan, trùng nhau, thiếu intermediate hoặc thứ tự khác. Việc kiểm tra chữ ký trên chain và chọn trust anchor là **bước riêng**.

### 6.3. Phân biệt các loại file dễ nhầm

| Dữ liệu đầu vào | Marker/đặc điểm | API đúng hướng |
| --- | --- | --- |
| X.509 certificate DER | Dữ liệu binary ASN.1 DER | `CertificateFactory("X.509").generateCertificate(in)` |
| X.509 certificate PEM | `BEGIN CERTIFICATE` ... `END CERTIFICATE` | **Cùng API** `generateCertificate(in)` |
| Nhiều PEM certificates | Nhiều khối `BEGIN CERTIFICATE` | `generateCertificates(in)` |
| PKCS#7 certificate set | SignedData chứa certificates | `generateCertificates(in)` hoặc `generateCertPath(in, "PKCS7")` tùy mục tiêu |
| X.509 public key SPKI | `BEGIN PUBLIC KEY` hoặc binary SPKI | `KeyFactory` + `X509EncodedKeySpec` |
| PKCS#8 private key | `BEGIN PRIVATE KEY` hoặc binary PKCS#8 | API import private key/`KeyFactory` và bảo vệ riêng; không phải CertificateFactory |
| Certificate signing request (CSR) | `BEGIN CERTIFICATE REQUEST` | Parser CSR phù hợp, không phải `generateCertificate` |
| Keystore `PKCS12/JKS` | Container lưu key/cert chain | `KeyStore` với đúng store type, credential và policy |

**Chú ý:** `X509EncodedKeySpec` có tên “X509” nhưng chứa **SubjectPublicKeyInfo**, tức **public key encoding**, không phải nguyên bản X.509 certificate. Thao tác lấy public key từ certificate đã parse là `cert.getPublicKey()`; không dùng `KeyFactory` để “đọc chứng thư” toàn phần.

## 7. Đọc metadata X.509 một cách có trách nhiệm

Sau parse, `X509Certificate` cung cấp nhiều thông tin có ích cho audit và kiểm tra cấu trúc:

### 7.1. Subject, issuer, serial, version

~~~java
X509Certificate cert = ...;
int version = cert.getVersion();
String subject = cert.getSubjectX500Principal().getName();
String issuer = cert.getIssuerX500Principal().getName();
String serialHex = cert.getSerialNumber().toString(16);
~~~

Đây là đoạn code minh họa. `getSubjectDN()` / `getIssuerDN()` cũ bị deprecated từ Java 16; nên dùng `getSubjectX500Principal()` / `getIssuerX500Principal()` để làm việc với `X500Principal`. **Không định danh/cho phép truy cập chỉ bằng chuỗi subject** nếu chưa có bước trust.

`getVersion()` trong Java X509Certificate trả version theo **cách biểu diễn 1-based** (ví dụ v3 trả 3). `getSerialNumber()` là `BigInteger`, thường hiển thị hex để đối chiếu, nhưng đừng coi serial duy nhất toàn cầu nếu không kết hợp issuer.

### 7.2. Hạn hiệu lực và SAN

~~~java
cert.checkValidity();    // Chỉ kiểm tra thời gian hiện tại.
var notBefore = cert.getNotBefore();
var notAfter = cert.getNotAfter();
var sans = cert.getSubjectAlternativeNames();
~~~

`getSubjectAlternativeNames()` có thể trả `null` nếu extension không có; dữ liệu SAN có nhiều loại như DNS, IP, URI, email. Không lấy một chuỗi subject CN rồi tự so hostname bằng `equals`: TLS hostname verification có quy tắc chứng thư và SAN riêng, bao gồm wildcard/IP/IDNA tùy giao thức. Khi làm TLS, nên để **JSSE endpoint identification/trust manager** đã được cấu hình xử lý.

`cert.checkValidity()`:
- Ném `CertificateNotYetValidException` nếu thời điểm hiện tại trước `NotBefore`.
- Ném `CertificateExpiredException` nếu sau `NotAfter`.
- Không kiểm tra issuer signature, chain trust, revocation, SAN hostname, EKU, policy hay thuật toán yếu.

### 7.3. Public key, key usage và basic constraints

Các API đáng biết:
- `cert.getPublicKey().getAlgorithm()`: tên thuật toán public key (`RSA`, `EC`, ...), không phải trực tiếp tên thuật toán chữ ký certificate.
- `cert.getSigAlgName()` / `getSigAlgOID()`: thông tin thuật toán **issuer đã dùng để ký certificate**.
- `cert.getKeyUsage()`: bitmap chính sách key usage, có thể `null`.
- `cert.getExtendedKeyUsage()`: danh sách OID EKU (hoặc `null`).
- `cert.getBasicConstraints()`: `-1` nếu không phải CA theo extension; không chỉ cần giá trị này là đủ xác nhận CA được tin cậy.
- `cert.getCriticalExtensionOIDs()` và `hasUnsupportedCriticalExtension()`: extension quan trọng cần xử lý theo quy tắc PKIX.

Không tự quyết định một chứng thư dùng được cho TLS server, code signing, email signing hoặc client auth chỉ bằng một field; cần kiểm tra **nhiều ràng buộc với chain, trust, policy và context**.

### 7.4. Fingerprint SHA-256

`SHA-256(cert.getEncoded())` giúp xác định **chính xác certificate DER**. Vì PEM và DER cùng bản chất chứa cùng DER, fingerprint của chứng thư phải giống nhau nếu nội dung thực cùng một certificate.

Tuy nhiên:
- Fingerprint không phải private key, thường có thể công bố; nó vẫn là metadata của đối tượng có thể cần kiểm soát trong hệ thống.
- Không nhầm fingerprint của **certificate** với fingerprint của **public key (SPKI)**: certificate có thể được cấp lại với cùng public key nhưng serial/validity/issuer khác, dẫn đến certificate fingerprint khác.
- Pinning fingerprint chỉ an toàn nếu nguồn giá trị kỳ vọng đáng tin cậy và có kế hoạch cập nhật/rotation. “Đọc cert từ đối thủ rồi tính SHA-256 và tin ngay” không có ý nghĩa xác thực.

## 8. Ranh giới quan trọng nhất: parse thành công KHÔNG bằng trust hợp lệ

Có năm việc dễ bị gộp sai:

| Bước | API/cơ chế | Chứng minh được | **Không chứng minh** |
| --- | --- | --- | --- |
| **Parse DER/PEM** | `CertificateFactory.generateCertificate` | Byte biểu diễn một X.509 certificate có cấu trúc parser chấp nhận. | Không chứng minh issuer đáng tin cậy hoặc cert còn hạn. |
| **Kiểm tra thời gian** | `X509Certificate.checkValidity` | Thời điểm nằm trong khoảng NotBefore–NotAfter. | Không chứng minh chữ ký/chain/hostname/CA đáng tin. |
| **Kiểm tra một chữ ký certificate** | `cert.verify(publicKey)` | Certificate đã được ký bằng private key tương ứng public key cung cấp (nếu verify thành công). | Public key cung cấp thuộc CA tin cậy hoặc đủ điều kiện cấp cert. |
| **Kiểm tra chuỗi chứng thư** | `CertPathValidator("PKIX")` + `PKIXParameters`, trust anchors, path | Đường chứng thực được validate theo tham số/chính sách cung cấp. | Hostname hoặc mọi quy tắc ứng dụng nếu chưa được cấu hình/kiểm tra. |
| **Xác thực endpoint/ứng dụng** | JSSE hostname verification, authz policy, EKU/SAN/tenant | Cert phù hợp danh tính/mục đích cụ thể sau các bước trust. | Không tự động bảo vệ mọi hành vi nghiệp vụ. |

Đối với một ứng dụng **TLS/HTTPS**, dùng `SSLContext`, `X509TrustManager` / `TrustManagerFactory` và endpoint identification phù hợp, không tự xây dựng một “trust manager chấp nhận mọi certificate” chỉ để kết nối thành công.

Đối với việc phân tích **certificate chain ngoài TLS**, chuẩn Java có:
- `CertPathValidator.getInstance("PKIX")`.
- `PKIXParameters` hoặc `PKIXBuilderParameters` cùng trust anchors được phê duyệt.
- `CertPathBuilder` để dựng path khi chưa có thứ tự/cert trung gian đầy đủ.
- Các chính sách kiểm tra key usage, critical extensions, thời gian, revocation/CRL/OCSP và algorithm constraints.

**Pseudocode**, không phải ví dụ Java độc lập, vì cấu hình trust/chuỗi chứng thư phụ thuộc môi trường:

~~~text
certificateBytes = readLimitedBytesFromApprovedSource()
certificates = CertificateFactory("X.509").generateCertificates(stream)

target = chooseLeafCertificateByProtocol()
trustedRoots = loadApprovedTrustAnchorsFromTrustStore()
path = buildOrArrangeCertPath(target, intermediates, trustedRoots)

result = CertPathValidator("PKIX").validate(
    path, PKIXParameters(trustedRoots, configuredPolicies)
)

checkExpectedIdentityAndPurpose(target, expectedHostOrService, constraints)
if all checks pass -> accept trusted certificate for this specific purpose
else -> reject
~~~

Không được gọi `cert.verify(cert.getPublicKey())` trên một chứng thư tự ký rồi suy ra “đáng tin cậy”: phép toán tự xác minh chữ ký không chứng minh chứng thư nằm trong trust store.

### 8.1. Vì sao file có tên `root-ca.pem` vẫn không phải trust anchor?

Tên file, comment PEM, subject `CN=Trusted Root` hay việc chứng thư tự ký đều do người tạo file quyết định. **Trust anchor phải đến từ kho hoặc kênh cấu hình đã tin cậy**, không phải từ file do remote peer vừa gửi. Nếu ứng dụng cho người dùng đưa arbitrary cert vào truststore, họ có thể cấp trust ngoài ý định.

### 8.2. Vì sao parse PEM chain không đủ cho HTTPS?

Một TLS server có thể gửi leaf + intermediates nhưng không gửi root. Các cert này có thể parse đúng; chain trust cần được dựng tới một CA trong truststore client và kiểm tra rằng **SAN phù hợp hostname**, EKU, thời gian và constraints. Kiểm tra số lượng cert là không đủ.

## 9. Chi tiết kỹ thuật về InputStream

### 9.1. `mark/reset` và cách Factory đọc

Java SE 17 mô tả đối với `generateCertificate`:
- Nếu stream **không hỗ trợ `mark` và `reset`**, phương thức có thể tiêu thụ **toàn bộ InputStream**.
- Nếu stream hỗ trợ chúng, mỗi lần gọi có thể đọc **một certificate** và đặt vị trí đọc ngay sau dấu kết thúc nội tại của certificate.
- Nếu dữ liệu không có dấu kết thúc nội tại khác EOF và còn trailing garbage, có thể bị từ chối bằng `CertificateException`.

Vì vậy dùng `BufferedInputStream` là lựa chọn hợp lý khi cần kiểm soát việc đọc một stream chứa nhiều chứng thư, nhưng không biến nó thành parser framing tổng quát cho protocol mạng.

### 9.2. Không dùng `available()` làm kích thước

`InputStream.available()` phản ánh số byte **có thể đọc ngay mà không bị chặn**, không nhất thiết là tổng số byte còn lại từ file/network/HTTP stream. Không viết:

~~~java
byte[] bytes = new byte[input.available()]; // SAI cho stream tổng quát.
input.read(bytes);                            // read() cũng không chắc điền đủ.
~~~

Đoạn trên là ví dụ **anti-pattern**, không phải chương trình chạy độc lập. Với dữ liệu untrusted, đặt **giới hạn kích thước và số lượng** ngay ở tầng HTTP/file/stream, dùng API đọc được kiểm soát, và từ chối input quá lớn trước khi parse ASN.1.

### 9.3. Dùng `try-with-resources` và xử lý I/O đúng tầng

~~~java
try (InputStream in = new BufferedInputStream(
        Files.newInputStream(certPath))) {
    X509Certificate cert = (X509Certificate)
            CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
    // Chỉ kiểm tra cấu trúc/metadata tại đây.
}
~~~

Đây là mảnh code minh họa; `certPath` là đối tượng `Path` đã được kiểm soát. `try-with-resources` sẽ đóng stream kể cả khi `CertificateException` xảy ra.

Phân biệt:
- File không tồn tại, permission denied, I/O lỗi: thường là `IOException` hoặc subclass.
- Byte file không phải DER/PEM X.509 hợp lệ: `CertificateException`.
- Chứng thư parse được nhưng hết hạn: `CertificateExpiredException` khi gọi `checkValidity`.
- Chứng thư parse được nhưng chain không tin cậy: lỗi trong bước PKIX/JSSE, **không phải `generateCertificate`**.

## 10. Sự cố thực tế và cách chẩn đoán

### Tình huống A — File `.cer` không phải lúc nào cũng là DER

Một đối tác gửi `partner.cer`, trong đó có `-----BEGIN CERTIFICATE-----`. Developer tự ép đọc bằng parser DER tự viết vì đuôi `.cer`, dẫn đến lỗi. Giải pháp: cho `CertificateFactory("X.509")` đọc trực tiếp stream; nó hỗ trợ binary DER và Base64 PEM với marker đúng.

### Tình huống B — PEM bị cắt một nửa

File có đầu `BEGIN CERTIFICATE` nhưng thiếu `END CERTIFICATE` hoặc Base64 không đầy đủ. Parser có thể ném `CertificateException`. Giải pháp: kiểm tra luồng truyền file và format, không bỏ qua ngoại lệ rồi coi cert là trusted.

### Tình huống C — Chỉ có `BEGIN PUBLIC KEY`

Đó là public key dạng SPKI, không phải chứng thư X.509. Cần `KeyFactory` + `X509EncodedKeySpec` nếu mục tiêu là đọc khóa; không dùng `CertificateFactory.generateCertificate` để đọc raw public key.

### Tình huống D — PEM bundle chứa ba cert, nhưng `generateCertificate` chỉ lấy một

Hệ thống bỏ sót intermediates, path validation thất bại. Dùng `generateCertificates` để lấy collection rồi xử lý chain theo giao thức; hoặc parse từng certificate theo stream hỗ trợ mark/reset. **Không tin rằng thứ tự/chain đã được validate** vì parse thành công.

### Tình huống E — Chứng thư parse được nhưng trình duyệt báo “unknown CA”

Không có mâu thuẫn: parse chỉ kiểm tra cấu trúc. Client không tìm thấy trust anchor thích hợp hoặc chain có lỗi; phải xử lý CA trust, intermediates, policies, hostname và các ràng buộc chứng thư.

### Tình huống F — `checkValidity()` thành công, HTTPS vẫn không an toàn

Chứng thư trong thời gian hiệu lực nhưng có thể được ký bởi CA không tin cậy, SAN không khớp host hoặc bị revoke. `checkValidity` không thay PKIX/hostname verification.

### Tình huống G — SHA-256 fingerprint từ file DER khác PEM

Nếu hai file chứa **cùng một chứng thư**, fingerprint tính từ `cert.getEncoded()` phải giống nhau. Nếu fingerprint **raw file bytes** thì khác là bình thường vì PEM có ASCII armor. Nếu fingerprint DER chuẩn hóa của parsed objects khác, chúng không hoàn toàn là cùng một certificate hoặc dữ liệu đã bị thay đổi.

### Tình huống H — Chuyển DER thành String rồi đọc lỗi

Binary DER không phải UTF-8. `new String(derBytes, UTF_8)` rồi `getBytes(UTF_8)` có thể làm biến đổi byte không hợp lệ. Đọc binary qua `InputStream` hoặc byte[] gốc; chỉ PEM là dạng text/Base64. Không tự sửa input tới khi parser “đồng ý”.

### Tình huống I — Đọc file từ HTTP request do client chỉ định

Một API nhận đường dẫn file tùy ý, rồi `Files.newInputStream(Path.of(request.path))`. Đây là nguy cơ path traversal/local file disclosure. Không dùng đường dẫn tùy ý từ request; dùng allowlisted path, sandboxed upload, kích thước/loại nội dung được kiểm soát và quyền tối thiểu.

### Tình huống J — In mọi chi tiết chứng thư vào public log

Certificate về bản chất thường có thể chia sẻ công khai nhưng Subject/SAN có thể chứa thông tin tổ chức, host nội bộ hay identifier nhạy cảm. Chỉ log những metadata cần thiết, bảo vệ log và tránh ghi raw certificate/payload nếu không có nhu cầu audit hợp lệ.

## 11. Bảng lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `Files.readString()` cho DER | Binary bị đọc sai/biến đổi. | Đưa file qua `InputStream` nhị phân. |
| Tự Base64-decode một PEM gồm marker bằng decoder sai | Lỗi cú pháp Base64 hoặc không tách đúng nhiều blocks. | Dùng trực tiếp `CertificateFactory.generateCertificate` cho PEM chuẩn. |
| Kỳ vọng `BEGIN PUBLIC KEY` là certificate | `CertificateException` vì không đúng cấu trúc X.509 certificate. | `KeyFactory` + `X509EncodedKeySpec` nếu mục tiêu là raw public key. |
| Dùng `getInstance("RSA")` để tạo CertificateFactory | Không phải tên certificate type. | `CertificateFactory.getInstance("X.509")`. |
| Quên cast sang `X509Certificate` | Chỉ dùng được API base `Certificate`. | Cast khi factory là X.509, sau đó truy xuất metadata. |
| Gọi `generateCertificate` cho cả PEM chain rồi nghĩ đã đọc toàn bộ | Có thể chỉ lấy một cert hoặc tiêu thụ stream theo contract. | Dùng `generateCertificates` cho collection/bundle. |
| Tin collection là path đã hợp lệ | Không có kiểm tra CA trust hoặc thứ tự. | Dùng `CertPathBuilder/Validator` với trust anchors được phê duyệt. |
| `cert.checkValidity()` coi là xác thực thành công | Chỉ kiểm tra ngày hiệu lực. | Kiểm tra PKIX, host identity, EKU, revocation/policy. |
| `cert.verify(cert.getPublicKey())` rồi tự tin cậy self-signed cert | Tự kiểm tra chữ ký không chứng minh trust. | Trust anchor phải được cấp từ nguồn đáng tin. |
| Dùng extension `.cer` để tự chọn DER/PEM | Tên file không quyết định encoding. | Kiểm tra nội dung qua chuẩn certificate factory. |
| Dùng `getSubjectDN()` đã deprecated cho API mới | Kiểu/format phụ thuộc provider. | `getSubjectX500Principal()`. |
| Log full `cert.toString()` vào log không kiểm soát | Có thể lộ metadata và làm log rất lớn. | Log các trường đã được cho phép hoặc fingerprint/hash có policy. |
| Không giới hạn input size, number of certs | CPU/memory denial-of-service do parser và collection. | Giới hạn bytes, cert count, timeout và nguồn dữ liệu. |
| Nhầm `CertificateException` với lỗi file không tồn tại | Chẩn đoán sai tầng. | Phân biệt IOException, CertificateException, PKIX exception. |
| Dùng parser tự chế để “chấp nhận mọi PEM lỗi” | Có thể chấp nhận encoding mơ hồ/malformed. | Theo định dạng X.509/PEM chuẩn, từ chối đầu vào bất thường. |
| Suy ra private key từ `cert.getPublicKey()` | Không khả thi; certificate chỉ chứa public key. | Quản lý private key riêng qua keystore/HSM/KMS. |

## 12. Thực hành kiểm tra đầu vào và QA

Khi xây dựng chức năng import chứng thư trong service:

- [ ] Xác định API nhận **chứng thư đơn lẻ** hay **certificate bundle/PKCS#7**.
- [ ] Giới hạn kích thước file/stream **thật sự**, số certificate và tổng thời gian xử lý.
- [ ] Không tin path do client đưa trực tiếp; chuẩn hóa và kiểm soát upload/permission.
- [ ] Dùng `CertificateFactory.getInstance("X.509")` trên binary stream hoặc PEM text bytes; không tự sửa encoding.
- [ ] Nếu là certificate đơn lẻ, phải rõ liệu trailing bytes/các khối khác có được chấp nhận hay không theo giao thức.
- [ ] Ghi nhận loại lỗi ở đúng tầng (`IOException`, `CertificateException`, PKIX), không in nguyên input ra log.
- [ ] Sau parse, kiểm tra các trường cần thiết (SAN, EKU, KeyUsage, BasicConstraints, issuer/subject, signature algorithm) **theo mục đích**, không chỉ lấy subject.
- [ ] Nếu quyết định trust, dùng truststore/trust anchor từ nguồn phê duyệt và kiểm tra path; không chấp nhận self-signed tùy ý.
- [ ] Nếu là TLS, giữ hostname verification và JSSE trust manager đúng cấu hình.
- [ ] Test cùng một cert DER/PEM cho cùng `cert.getEncoded()` và fingerprint.
- [ ] Test PEM nhiều cert, DER hỏng, PEM marker sai, file rỗng, file quá lớn, parser provider khác nhau.
- [ ] Phân biệt một chứng thư hết hạn nhưng parse được với chứng thư DER hỏng không parse được.

### Gợi ý test case

| Test | Input | Kỳ vọng |
| --- | --- | --- |
| DER chuẩn | Binary DER X.509 hợp lệ | `generateCertificate` trả `X509Certificate`. |
| PEM chuẩn | `BEGIN/END CERTIFICATE` chứa DER Base64 hợp lệ | Trả cùng certificate với DER tương ứng. |
| DER và PEM của cùng cert | Hai luồng cùng nội dung X.509 | `Arrays.equals(certDER.getEncoded(), certPEM.getEncoded()) == true`. |
| Nhiều PEM blocks | Hai hoặc nhiều CERTIFICATE liên tiếp | `generateCertificates` lấy collection phù hợp. |
| DER hỏng | Byte không thể decode thành certificate | `CertificateException`. |
| PEM thiếu marker | Base64/armor không đúng | `CertificateException` theo nhà cung cấp. |
| File không tồn tại | Path sai | `IOException`/`NoSuchFileException`, trước parse. |
| Raw public key PEM | `BEGIN PUBLIC KEY` | Không phải X.509 certificate; từ chối hoặc dùng KeyFactory phù hợp. |
| Cert hết hạn nhưng hợp lệ ASN.1 | X.509 parse được, thời gian ngoài hạn | Parse thành công; `checkValidity()` ném lỗi hạn. |
| Chứng thư CA không tin cậy | DER/PEM hợp lệ nhưng không có trust path | Parse thành công; PKIX trust validation thất bại. |
| Cert có subject đúng nhưng SAN sai | X.509 parse được | TLS hostname verification vẫn thất bại. |

**Lưu ý khi test trên provider khác:** các thông điệp `CertificateException` có thể không giống nhau; chỉ khẳng định điều contract API bảo đảm, không kiểm tra bằng cách so nguyên chuỗi lỗi Java. Chương trình `CertificateFormatsDemo` đã thử DER/PEM/bundle/malformed trên một JVM phổ biến; với môi trường production hãy chạy thêm trên JDK/provider thực tế.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Khi có file `server.der` và `server.pem` mô tả **cùng chứng thư**, Java cần hai loại CertificateFactory không?

**Đáp án:** Không. `CertificateFactory.getInstance("X.509")` và `generateCertificate(InputStream)` xử lý được DER binary và PEM certificate Base64 có marker chuẩn.

**Câu 2.** PEM chứng thư có chứa private key không?

**Đáp án:** Không, nếu khối là `BEGIN CERTIFICATE`. PEM là format text armor; nó còn có thể dùng để biểu diễn private key, CSR hoặc public key **trong các loại khối khác**, nên phải kiểm tra header/footer.

**Câu 3.** `generateCertificate` chạy thành công. Certificate có đáng tin cậy để dùng cho HTTPS không?

**Đáp án:** Chưa biết. Thành công chỉ chứng minh dữ liệu parse thành X.509. Cần validate PKIX chain đến trust anchor đã duyệt, thời gian, mục đích, SAN/hostname và các policy liên quan.

**Câu 4.** `cert.checkValidity()` chạy thành công nhưng certificate tự ký bởi kẻ lạ. Có được xác nhận trust không?

**Đáp án:** Không. `checkValidity` chỉ xét `NotBefore` và `NotAfter`; tự ký không làm một chứng thư trở thành trust anchor.

**Câu 5.** Làm sao đọc PEM có ba khối `BEGIN CERTIFICATE` thành collection?

**Đáp án:** Dùng `factory.generateCertificates(in)`. Sau đó xác định loại, số lượng, thứ tự/quan hệ chain và validate nếu mục đích yêu cầu; không chỉ lấy cert đầu tiên.

**Câu 6.** Tại sao raw file SHA-256 của PEM khác DER nhưng `SHA256(cert.getEncoded())` lại giống?

**Đáp án:** Raw PEM có marker, Base64 và xuống dòng, raw DER là binary; chúng không cùng byte file. `cert.getEncoded()` trả DER của certificate đã parse nên giống cho cùng nội dung X.509.

**Câu 7.** `X509EncodedKeySpec` có dùng để đọc nguyên một X.509 certificate không?

**Đáp án:** Không. Nó biểu diễn public key `SubjectPublicKeyInfo`. Để đọc chứng thư dùng `CertificateFactory`; để nhập raw public key dùng `KeyFactory`.

**Câu 8.** `CertificateException` có chắc chắn nghĩa là CA không được tin cậy không?

**Đáp án:** Không. Nó thường là lỗi parse/construct certificate ở factory. CA trust/PKIX validation là bước khác với các ngoại lệ/chính sách riêng.

**Câu 9.** Có được lấy first cert từ một PEM bundle rồi dùng ngay như trust anchor không?

**Đáp án:** Không. Thứ tự bundle không bảo đảm trust; trust anchors phải đến từ truststore/kênh đã được phê duyệt.

**Câu 10.** Nếu dùng `FileInputStream` trên nguồn có nhiều cert rồi gọi `generateCertificate` nhiều lần, có chắc mỗi lần đọc một cert không?

**Đáp án:** Không. API mô tả cách tiêu thụ stream khác nhau tùy `mark/reset`. Dùng `generateCertificates` hoặc `BufferedInputStream` với framing/boundary đúng.

**Câu 11.** Chứng thư parse được có thể không có SAN không?

**Đáp án:** Có. `getSubjectAlternativeNames()` có thể trả `null`. Với xác thực tên miền TLS, phải áp dụng quy tắc danh tính/giao thức và không mặc định subject CN là đủ.

**Câu 12.** Java đọc được file có đuôi `.crt` thì có nghĩa chắc chắn là PEM hay DER không?

**Đáp án:** Không. Đuôi là quy ước người đặt, không thay cho kiểm tra định dạng thực.

## 14. Tài liệu chính thức

- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): hợp đồng hỗ trợ X.509 DER binary và Base64 PEM với marker, `generateCertificate`, `generateCertificates`, `mark/reset` và `generateCertPath`.
- [Java SE 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): subject/issuer, validity, public key, SAN, KeyUsage, BasicConstraints và chữ ký chứng thư.
- [Java SE 17 — CertificateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateException.html): họ ngoại lệ liên quan certificate parsing.
- [Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): API kiểm tra đường chứng thực, tách khỏi parsing.
- [Java SE 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors và policy cho PKIX.
- [Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust manager phục vụ TLS.
- [Oracle Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): xây dựng, validate certificate path và các thuật ngữ PKI.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc X.509, phần mở rộng và PKIX certificate profile.
