# 13.4 Subject, issuer, serial number, thời hạn và X500Principal

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc và phân biệt năm thông tin lõi của chứng thư số **X.509**: **subject**, **issuer**, **serial number**, **notBefore**, **notAfter**.
2. Dùng `javax.security.auth.x500.X500Principal` đúng cách để làm việc với **Distinguished Name (DN)**, nhận biết **RDN/AVA**, các thuộc tính như `CN`, `O`, `OU`, `C` và quy tắc escape.
3. Hiểu tại sao **subject DN không đồng nghĩa hostname**, **issuer DN không chứng minh CA đáng tin**, và **issuer + serial number** là phạm vi định danh chứng thư theo chuẩn.
4. Đọc một chứng thư thật từ **PEM/DER** bằng `CertificateFactory` và `X509Certificate` trên **Java 17**, xem subject/issuer/serial/time mà không cần API nội bộ `sun.*`.
5. Dùng `checkValidity()`/`checkValidity(Date)`, hiểu lỗi **not yet valid/expired**, UTC và giới hạn của kiểm tra thời hạn.
6. Tránh nhầm lẫn giữa **serial number của chứng thư** và thuộc tính `SERIALNUMBER` **bên trong một DN**; phân biệt **self-issued**, **self-signed** và **trusted**.

## 1. X.509 certificate có những trường gì?

Chứng thư số X.509 gắn **public key** với thông tin định danh theo mô hình PKI. Một **Certificate Authority (CA)** phát hành chứng thư bằng cách ký trên phần dữ liệu cần chứng nhận; người nhận cần xác thực chữ ký, xây dựng và đánh giá chuỗi chứng thư theo chính sách tin cậy.

Cấu trúc mức khái niệm:

```text
Certificate
├── tbsCertificate (To Be Signed Certificate)
│   ├── version                 (v1/v2/v3)
│   ├── serialNumber            (số sê-ri do CA phát hành)
│   ├── signature               (thuật toán ký TBS)
│   ├── issuer                  (DN của bên phát hành)
│   ├── validity
│   │   ├── notBefore           (thời điểm bắt đầu hiệu lực)
│   │   └── notAfter            (thời điểm hết hiệu lực)
│   ├── subject                 (DN của chủ thể, có thể trống)
│   ├── subjectPublicKeyInfo    (thuật toán + public key)
│   └── extensions              (SAN, BasicConstraints, KU, EKU, ...)
├── signatureAlgorithm
└── signatureValue              (chữ ký của CA trên TBS)
```

Phạm vi chính của bài là **issuer, subject, serial number và validity**. Các extension như **Subject Alternative Name (SAN)** được nhắc đến ở mức cần thiết để tránh diễn giải sai subject DN; kiểm tra đường dẫn tin cậy, thu hồi và chính sách TLS được giới thiệu như **ranh giới**, không thay thế bài học chứng thư/PKIX riêng.

Ví dụ một chứng thư server giả định (không phải chứng thư hợp lệ để kết nối thật):

```text
Subject:     CN=api.example.test,O=Example Services,C=VN
Issuer:      CN=Example Issuing CA,O=Example PKI,C=VN
Serial:      0x34A728...              (một BigInteger)
Not Before:  2026-01-01T00:00:00Z
Not After:   2027-01-01T00:00:00Z
Public Key:  EC P-256
SAN:         DNS:api.example.test
```

**Điều quan trọng:** mỗi dòng mô tả một khía cạnh khác nhau. Subject là tên **chủ thể**, issuer là tên **bên phát hành**, serial là định danh **trong phạm vi issuer**, thời hạn chỉ là khoảng **thời gian**. Không trường nào, đứng một mình, là bằng chứng chứng thư đáng tin.

## 2. Subject: tên của chủ thể sở hữu public key

**Subject** trong `TBSCertificate` xác định thực thể gắn với public key trong `subjectPublicKeyInfo`. Có thể là tổ chức, người dùng, CA hay dịch vụ; cách diễn giải danh tính phụ thuộc loại chứng thư, CA và chính sách kiểm chứng.

Một subject DN thường thấy:

```text
CN=api.example.test,OU=Platform,O=Example Corp,L=Hanoi,C=VN
```

| Thuộc tính DN | Nghĩa gần đúng | Lưu ý |
| --- | --- | --- |
| `CN` — Common Name | Tên thông dụng của chủ thể | Không coi là tên miền TLS đã xác minh chỉ bằng `CN` |
| `O` — Organization | Tổ chức | Không mặc định CA đã xác minh ở mọi loại profile |
| `OU` — Organizational Unit | Đơn vị trong tổ chức | Có thể không hiện diện; không dùng làm quyền truy cập |
| `C` — Country | Mã quốc gia, ví dụ `VN` | Không chứng minh nơi đặt máy chủ |
| `L` / `ST` | Địa phương / bang-tỉnh | Dữ liệu định danh, không phải nguồn tin cậy tuyệt đối |
| `DC` / `UID` | Domain component / user ID | Là **attribute type**, không đồng nghĩa SAN DNS hay tên user đã xác thực |

Tên có nhiều thuộc tính gọi là **Distinguished Name** (DN). Một DN là chuỗi có cấu trúc ASN.1 `Name`, gồm những **Relative Distinguished Name (RDN)** theo thứ tự; một RDN có thể gồm **nhiều Attribute Value Assertion (AVA)**. Dấu phẩy và dấu cộng trong biểu diễn text có ý nghĩa cú pháp, không phải ký tự dữ liệu thuần túy.

Ví dụ:

```text
CN=Doe\, Jane,O=Example Lab,C=VN
```

Dấu `\,` thể hiện dấu phẩy **nằm trong giá trị CN**, không phải dấu phân cách RDN. Do đó thao tác như `subjectString.split(",")` là **sai** nếu dùng để parse DN từ bên ngoài. Giá trị còn có thể chứa dấu `+`, `=`, `#`, khoảng trắng có ý nghĩa, mã hóa Unicode/OID; cần parser DN chuẩn.

### 2.1 Subject DN có thể **rỗng**

RFC 5280 cho phép subject được biểu diễn bằng **empty sequence**, nếu thông tin nhận diện nằm trong `subjectAltName`. Khi subject rỗng, extension SAN phải có mặt và được đánh dấu **critical** theo profile. `X509Certificate.getSubjectX500Principal()` vẫn trả về một `X500Principal` hợp lệ; `getName()` có thể trả **chuỗi rỗng**.

Không viết:

```java
// SAI: giả định mọi certificate có CN, và CN luôn là hostname.
String host = cert.getSubjectX500Principal()
        .getName().split(",")[0].substring(3);
```

Đoạn trên là **phản ví dụ**, không nên đưa vào sản phẩm: subject có thể rỗng, CN có thể không ở vị trí đầu, giá trị có ký tự escape và tên TLS cần xử lý **SAN** theo profile xác minh danh tính dịch vụ.

### 2.2 Subject CN và xác minh hostname TLS

**Subject DN không tự là bằng chứng hostname hợp lệ.** Trong TLS hiện đại, nhận diện dịch vụ được biểu diễn và đối chiếu qua **Subject Alternative Name** theo chính sách (ví dụ `dNSName`, `iPAddress`).

RFC 9525 (thay thế RFC 6125) xác định rằng danh tính dịch vụ TLS không còn được lấy từ RDN `commonName` trong subject; thực hành đúng là so tên dịch vụ dự kiến với SAN phù hợp **sau khi** xác thực chứng thư theo PKI.

Trong Java, không tự so sánh `CN=...` với hostname rồi tắt hostname verification. Dùng HTTP/TLS client và cơ chế kiểm tra tên máy chủ/trust của nền tảng hoặc thư viện được cấu hình đúng. Việc subject có chữ `CN=example.com` **không đảm bảo** kết nối `example.com` đáng tin.

## 3. Issuer: tên bên đã phát hành/ký chứng thư

**Issuer** trong `TBSCertificate` là DN của CA đã phát hành và ký chứng thư. RFC 5280 yêu cầu issuer DN **không trống** đối với chứng thư phù hợp profile.

Ví dụ chuỗi:

```text
Leaf certificate:
    subject = CN=api.example.test,O=Example Services,C=VN
    issuer  = CN=Example Issuing CA,O=Example PKI,C=VN

Intermediate CA certificate:
    subject = CN=Example Issuing CA,O=Example PKI,C=VN
    issuer  = CN=Example Root CA,O=Example PKI,C=VN

Root CA certificate:
    subject = CN=Example Root CA,O=Example PKI,C=VN
    issuer  = CN=Example Root CA,O=Example PKI,C=VN
```

Khi xây chứng thư chuỗi, **name chaining** liên hệ `issuer` của chứng thư con với `subject` của chứng thư cấp trên theo quy tắc so sánh DN. Nhưng **trùng tên mới là điều kiện cần, chưa đủ**. Kẻ tấn công có thể tự tạo chứng thư mới với DN giống CA nổi tiếng; tên giống nhau không chứng minh có khóa riêng của CA hay được hệ thống tin cậy.

Một hệ thống xác minh đầy đủ còn cần:

- Xác minh **chữ ký** chứng thư con bằng **public key thật** của CA cấp trên.
- Kiểm tra **CA BasicConstraints**, `keyCertSign` (KeyUsage), path length, thuật toán/key được phép và các ràng buộc liên quan.
- Xây và xác minh đường dẫn tới **trust anchor** được cấu hình tin cậy.
- Kiểm tra **thời hạn**, **thu hồi** (CRL/OCSP theo chính sách), policy/name constraints và định danh dịch vụ.
- Không tin CA chỉ vì tên issuer giống một chuỗi được hard-code.

### 3.1 Self-issued, self-signed và trusted không đồng nghĩa

| Tính chất | Định nghĩa | Điều **không** được suy ra |
| --- | --- | --- |
| **Self-issued** | `subject` và `issuer` DN giống nhau theo quy tắc so sánh tên | Chưa chứng minh chữ ký do public key trong chứng thư tạo ra |
| **Self-signed** | Chữ ký trên chứng thư được kiểm chứng bằng public key của **chính chứng thư** | Chưa chứng minh chứng thư nằm trong trust store |
| **Trusted** | Chứng thư/chuỗi được chính sách tin cậy chấp nhận từ một trust anchor được quản lý | Không chỉ dựa vào `subject == issuer` hay `verify(publicKey)` |

Một **self-issued certificate** không nhất thiết là **self-signed** (ví dụ một số trường hợp CA đổi khóa); và một self-signed certificate dù chữ ký hợp lệ cũng **không tự động đáng tin**. Các root certificate chỉ trở thành trust anchor khi được quản trị trong trust store/chính sách chấp nhận của bên xác minh.

Trong Java:

```java
boolean selfIssued = cert.getSubjectX500Principal()
        .equals(cert.getIssuerX500Principal());
```

Đây là **đoạn code nhúng** với biến `X509Certificate cert` đã được nạp; `selfIssued` chỉ nói về **tên**, không nói về chữ ký hay trust.

## 4. Serial number: định danh chứng thư **trong phạm vi issuer**

`serialNumber` của X.509 nằm trong `TBSCertificate`. Đây là số nguyên do **CA phát hành** gán cho **mỗi chứng thư**, khác với tên subject và khác với ID người dùng.

Theo RFC 5280:

- Serial phải là **số nguyên dương** do CA cấp cho mỗi chứng thư.
- Mỗi serial phải **duy nhất trong tập chứng thư do cùng CA/issuer phát hành**. Do đó **issuer DN + serial number** xác định một chứng thư trong phạm vi PKI được mô tả.
- Các CA tuân thủ không được phát serial dài quá **20 octets** theo profile; các triển khai cần xử lý serial lớn đến giới hạn này.
- Có chứng thư không tuân thủ với serial `0` hoặc âm trong thực tế; bên đọc phải xử lý phù hợp, không crash do giả định mọi thứ hợp lệ.

### 4.1 So sánh đúng đơn vị định danh

```text
Issuer A: CN=CA-A,O=Example,C=VN
  serial 0x01  -> certificate A-1

Issuer B: CN=CA-B,O=Example,C=VN
  serial 0x01  -> certificate B-1

Hai serial bằng nhau vẫn có thể là **hai chứng thư khác nhau**.
```

Không dùng `serial` đơn độc làm primary key **toàn cầu** của mọi chứng thư. Một hệ thống PKI nghiêm túc còn phải xác minh chuỗi/issuer thực tế, vì DN có thể được sử dụng lại và dữ liệu chứng thư có thể bị giả mạo trước khi xác thực.

Trong Java, đọc serial qua:

```java
BigInteger serial = cert.getSerialNumber();
String serialHex = serial.toString(16);
```

Đây là **đoạn nhúng** (cần `java.math.BigInteger`, biến `cert` kiểu `X509Certificate`). `getSerialNumber()` trả `BigInteger`, **không phải `long`**; không dùng `longValue()` vì có thể mất bit và gây trùng sau khi ép kiểu. `toString(16)` hữu ích cho debug/tra cứu nhưng việc so khớp chứng thư nên làm trên giá trị có kiểu và phạm vi issuer đã xác thực.

Định dạng hiển thị hex không nhất thiết giữ byte padding `00` ở đầu của ASN.1 DER; cần phân biệt **giá trị số** và **cách trình bày bytes**. Đừng giả định serial là “random token”, “secret” hoặc một ID máy chủ có thể ủy quyền.

### 4.2 Hai thứ tên “serial number” rất dễ nhầm

Một DN có thể chứa thuộc tính `SERIALNUMBER` với **OID `2.5.4.5`**:

```text
Subject: CN=Device A,SERIALNUMBER=ASSET-123,O=Factory,C=VN
```

Đó là **thuộc tính text của subject DN**, có thể biểu diễn mã thiết bị/công ty theo profile cụ thể. Nó **không phải** trường `TBSCertificate.serialNumber` do CA cấp; hai giá trị có ngữ nghĩa và nơi lưu khác nhau.

| Thuộc tính | Nằm ở đâu? | Java API |
| --- | --- | --- |
| **Certificate serial number** | `TBSCertificate.serialNumber` | `cert.getSerialNumber()` → `BigInteger` |
| **DN SERIALNUMBER attribute** | Một AVA/RDN trong `subject` hoặc `issuer` | `cert.getSubjectX500Principal()` → parse DN/OID phù hợp |

Đừng trích `SERIALNUMBER=...` từ subject string để đưa vào API CRL/revocation hoặc để xây issuer+serial ID.

## 5. Validity: `notBefore` và `notAfter`

Chứng thư chứa một trường `Validity` gồm hai thời điểm:

```asn1
Validity ::= SEQUENCE {
    notBefore Time,
    notAfter  Time
}
```

Theo RFC 5280, khoảng thời gian hiệu lực bao gồm thời điểm bắt đầu và kết thúc; về mặt trực giác:

```text
notBefore <= evaluation_time <= notAfter
```

| Trường | Nghĩa | Java API |
| --- | --- | --- |
| `notBefore` | Thời điểm sớm nhất chứng thư có hiệu lực | `getNotBefore()` → `java.util.Date` |
| `notAfter` | Thời điểm cuối cùng chứng thư có hiệu lực | `getNotAfter()` → `java.util.Date` |
| Check hiện tại | Kiểm tra “lúc này” có nằm trong khoảng không | `checkValidity()` |
| Check tại thời điểm chỉ định | Kiểm tra khoảng thời gian với thời điểm truyền vào | `checkValidity(Date date)` |

Hai ngoại lệ có ý nghĩa riêng:

- `CertificateNotYetValidException`: ngày kiểm tra **trước `notBefore`**.
- `CertificateExpiredException`: ngày kiểm tra **sau `notAfter`**.

`checkValidity()` là kiểm tra khoảng thời gian theo đồng hồ runtime; `checkValidity(Date)` kiểm tra theo thời điểm do caller truyền. Nó **không** tự verify chữ ký, trust chain, hostname, KeyUsage, EKU, CRL hay OCSP.

### 5.1 UTC, UTCTime, GeneralizedTime và múi giờ

Trong ASN.1 của X.509, `Time` có thể được mã hóa dạng `UTCTime` hoặc `GeneralizedTime`. Với profile RFC 5280:

- Những năm **1950–2049** dùng `UTCTime`.
- Năm **2050 trở đi** dùng `GeneralizedTime`.
- Giá trị được biểu diễn theo **Zulu/UTC** với giây và định dạng chuẩn tương ứng.

Java trả `Date` — tức một thời điểm tuyệt đối theo UTC về mặt instant, **không phải chuỗi timezone cụ thể**. Để log/hiển thị không bị hiểu sai do timezone máy, nên đổi:

```java
Instant start = cert.getNotBefore().toInstant();
Instant end   = cert.getNotAfter().toInstant();
System.out.println(start); // ISO-8601 UTC, dạng ...Z
```

Đây là **mã nhúng** (cần `import java.time.Instant;`). `Date.toString()` phụ thuộc múi giờ hiển thị mặc định, nên hai máy có thể in các chuỗi khác nhưng vẫn chỉ **cùng một instant**.

### 5.2 Thời hạn hết không có nghĩa “đã bị thu hồi”

Tình huống:

- Chứng thư **chưa đến notBefore**: chưa có hiệu lực về thời gian.
- Chứng thư **sau notAfter**: hết hiệu lực về thời gian.
- Chứng thư **trong hạn**: **chỉ vượt qua một điều kiện thời gian**, vẫn có thể bị thu hồi, ký bằng CA không tin cậy, có tên dịch vụ sai hoặc key usage không phù hợp.

Đừng viết logic như `if (now < notAfter) allowLogin();`. Nó bỏ qua `notBefore` và mọi điều kiện PKIX còn lại. Đồng hồ hệ thống lệch thời gian cũng có thể làm check sai; cần đồng bộ clock và dùng cơ chế xác minh của nền tảng.

### 5.3 Bản ghi hết hạn và xoay vòng chứng thư

Nếu `notAfter` sắp đến, ứng dụng nên **gia hạn/thay certificate** theo chính sách, đồng thời đảm bảo server đã triển khai leaf cùng chain thích hợp. Không “sửa ngày hết hạn” của chứng thư đã ký: `notBefore/notAfter` nằm trong **TBSCertificate được CA ký**. Thay chúng sẽ làm chữ ký không hợp lệ.

Một chứng thư gia hạn có thể có **serial mới**, validity mới và đôi khi public key mới; không mặc định rằng subject giống nhau thì hai certificate là một bản ghi. Nếu yêu cầu kiểm kê chứng thư, có thể lưu certificate fingerprint cùng issuer+serial, keyId và thời điểm hiệu lực.

## 6. `X500Principal`: kiểu Java chuẩn để xử lý Distinguished Name

API `javax.security.auth.x500.X500Principal` đại diện cho **X.500 DN**, thay cho cách xử lý chuỗi tùy tiện hoặc giao diện `getSubjectDN()/getIssuerDN()` cũ.

Hai phương thức quan trọng trên `X509Certificate`:

```java
X500Principal subject = cert.getSubjectX500Principal();
X500Principal issuer  = cert.getIssuerX500Principal();
```

Đây là **mã nhúng** trong một phương thức đã có biến `cert` và import `X500Principal`.

### 6.1 Các định dạng hiển thị

`X500Principal` có:

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Trả chuỗi **RFC2253** |
| `getName(X500Principal.RFC2253)` | Định dạng RFC2253 cho tích hợp có yêu cầu text DN |
| `getName(X500Principal.RFC1779)` | Biểu diễn thân thiện/kiểu RFC1779 |
| `getName(X500Principal.CANONICAL)` | Chuỗi canonical dùng cho so sánh bình đẳng của `X500Principal` |
| `getEncoded()` | Mã hóa **ASN.1 DER** của **Name**, không phải toàn bộ certificate |
| `new X500Principal(byte[])` | Parse **DER-encoded DN** |
| `equals(...)` | So sánh theo **canonical DN** do Java định nghĩa |

Quan trọng: **RFC2253 là format text của DN, không phải thuật toán tin cậy**. Nếu bạn cần kiểm tra hai DN có bằng nhau, ưu tiên `X500Principal.equals(...)` theo semantics được cung cấp, không tự `String.equalsIgnoreCase(...)` trên hai chuỗi format khác nhau.

Chuỗi canonical hữu ích cho log/tra cứu nhưng **không biến subject/issuer thành xác thực quyền truy cập**. Hai CA có cùng chuỗi DN vẫn không phải một CA đáng tin nếu chữ ký/trust khác.

### 6.2 RDN có thứ tự; giá trị có ký tự escape

Một DN có thể chứa giá trị dấu phẩy, dấu cộng hoặc ký tự quốc tế:

```text
CN=Service\, QA,O=Example Lab,C=VN
```

Nếu bạn tách theo dấu phẩy, bạn sẽ phá vỡ giá trị `CN=Service, QA` thành hai phần không hợp lệ.

Lưu ý thêm:

- DN có thể có **RDN đa giá trị** được nối bằng `+`.
- Dấu phẩy trong giá trị phải escape đúng theo biểu diễn RFC2253.
- Một số attribute type được biểu diễn bằng **OID dạng số**, không nhất thiết có keyword dễ đọc.
- `getName(CANONICAL)` đưa ra biểu diễn canonical phục vụ so sánh; đừng dựa vào thứ tự text “đẹp” để làm chính sách identity.
- Nếu phải truy vấn riêng CN/O/OU, sử dụng parser theo chuẩn DN (ví dụ thư viện LDAP/X.500 phù hợp), **không tự split** và không làm auth dựa trên CN string.

### 6.3 Thực hành 1: tạo, biểu diễn và round-trip `X500Principal`

File **`X500PrincipalNamesDemo.java`**, chạy trên Java 17+:

```java
import javax.security.auth.x500.X500Principal;

public class X500PrincipalNamesDemo {
    public static void main(String[] args) {
        X500Principal original = new X500Principal(
                "CN=Service\\, QA,O=Example Lab,C=VN");
        X500Principal fromDer = new X500Principal(original.getEncoded());
        X500Principal different = new X500Principal(
                "CN=Another Service,O=Example Lab,C=VN");

        String rfc2253 = original.getName(X500Principal.RFC2253);
        String canonical = original.getName(X500Principal.CANONICAL);
        System.out.println("RFC2253 escaped comma: " + rfc2253.contains("\\,"));
        System.out.println("DER round trip equal: " + original.equals(fromDer));
        System.out.println("canonical stable: " +
                canonical.equals(fromDer.getName(X500Principal.CANONICAL)));
        System.out.println("different DN unequal: " + !original.equals(different));
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 17 X500PrincipalNamesDemo.java
java X500PrincipalNamesDemo
```

Đầu ra đã kiểm tra:

```text
RFC2253 escaped comma: true
DER round trip equal: true
canonical stable: true
different DN unequal: true
```

Giải thích:

1. Java string cần viết `\\,` để mang một dấu `\` trước dấu phẩy cho bộ parser DN; nếu thiếu escape thì dấu phẩy sẽ bị hiểu là phân cách RDN.
2. `getEncoded()` tạo byte DER của **chính DN**; xây lại `new X500Principal(bytes)` giữ semantics tên.
3. `equals` trả true cho hai object đại diện cùng DN. Nó không kiểm tra chữ ký certificate hay độ tin cậy của issuer.
4. DN `CN=Another Service,...` khác về subject → không bằng bản gốc.
5. Program không “bóc riêng CN” bằng string split vì đó không phải cách xử lý cấu trúc X.500 an toàn.

**Đừng nhầm `X500Principal.getEncoded()` với `X509Certificate.getEncoded()`**: một bên là DER của **DN**, bên kia là DER của **toàn bộ chứng thư**.

## 7. Thực hành 2: đọc certificate từ PEM bằng Java 17

Một cách thực tế để học các trường này là dùng `keytool` của JDK tạo **một chứng thư lab tự ký** rồi đọc qua `CertificateFactory.getInstance("X.509")`. Ví dụ tạo key RSA 2048 cho mục đích minh họa, subject/issuer đều là `CN=localhost,O=Example Lab,C=VN`, SAN có `DNS:localhost`, thời hạn 30 ngày từ lúc phát hành. **Không dùng chứng thư lab làm certificate production hoặc root trust.**

### 7.1 Tạo certificate fixture bằng `keytool`

Trong **thư mục trống dành cho bài lab**, chạy các lệnh sau với JDK có `keytool`:

```bash
keytool -genkeypair -alias lesson -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost,O=Example Lab,C=VN" -validity 30 -keystore sample.p12 -storetype PKCS12 -storepass changeit -keypass changeit -ext SAN=dns:localhost -noprompt

keytool -exportcert -alias lesson -keystore sample.p12 -storetype PKCS12 -storepass changeit -rfc -file sample-cert.pem
```

- `sample.p12` chứa **private key lab** và certificate; **không commit, chia sẻ hoặc triển khai** lên hệ thống thật. Password `changeit` chỉ là password thử nghiệm, **không phải mật khẩu production**.
- `sample-cert.pem` chỉ chứa **public certificate** và có thể được `CertificateFactory` đọc.
- `-rfc` tạo biểu diễn PEM kiểu `-----BEGIN CERTIFICATE-----` + Base64 của DER; công cụ Java xử lý qua `CertificateFactory("X.509")`.
- `-validity 30` chỉ để bài lab có certificate đang trong hạn tại lúc tạo; nếu bạn chạy lại chương trình sau 30 ngày, `checkValidity()` sẽ báo hết hạn đúng dự kiến.

Có thể kiểm tra trực quan bằng:

```bash
keytool -printcert -file sample-cert.pem
```

Giá trị serial và các mốc thời gian **khác nhau giữa những lần tạo**. Đừng copy serial ngẫu nhiên từ một lần chạy làm assertion ổn định của nhiều máy.

### 7.2 Java code đọc năm trường

Tạo **`X509CertificateFieldsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Instant;
import javax.security.auth.x500.X500Principal;

public class X509CertificateFieldsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java X509CertificateFieldsDemo <cert.pem>");
        }
        X509Certificate certificate;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            certificate = (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }

        X500Principal subject = certificate.getSubjectX500Principal();
        X500Principal issuer = certificate.getIssuerX500Principal();
        String serialHex = certificate.getSerialNumber().toString(16);
        Instant notBefore = certificate.getNotBefore().toInstant();
        Instant notAfter = certificate.getNotAfter().toInstant();

        certificate.checkValidity();
        System.out.println("subject: " + subject.getName(X500Principal.RFC2253));
        System.out.println("issuer: " + issuer.getName(X500Principal.RFC2253));
        System.out.println("serial positive: " +
                (certificate.getSerialNumber().signum() > 0));
        System.out.println("serial hex nonempty: " + !serialHex.isEmpty());
        System.out.println("validity ordered: " + notBefore.isBefore(notAfter));
        System.out.println("valid now: true");
        System.out.println("self-issued names: " + subject.equals(issuer));
        certificate.verify(certificate.getPublicKey());
        System.out.println("self-signature verifies: true");
        System.out.println("SAN extension present: " +
                (certificate.getSubjectAlternativeNames() != null));
    }
}
```

Biên dịch/chạy sau khi tạo file `sample-cert.pem` trong cùng thư mục:

```bash
javac --release 17 X509CertificateFieldsDemo.java
java X509CertificateFieldsDemo sample-cert.pem
```

Đầu ra đã chạy trên JDK có keytool tương thích:

```text
subject: CN=localhost,O=Example Lab,C=VN
issuer: CN=localhost,O=Example Lab,C=VN
serial positive: true
serial hex nonempty: true
validity ordered: true
valid now: true
self-issued names: true
self-signature verifies: true
SAN extension present: true
```

**Lý giải:**

1. `CertificateFactory.getInstance("X.509").generateCertificate(...)` parse chứng thư ở dạng PEM/DER; cast về `X509Certificate` để dùng API chuyên biệt. **Parse thành công chưa tạo trust**.
2. `getSubjectX500Principal` và `getIssuerX500Principal` trả các DN đúng kiểu; fixture tự ký nên subject và issuer **trùng nhau**.
3. `getSerialNumber()` đọc `BigInteger` do `keytool` gán; ví dụ chỉ kiểm số dương và hiển thị hex có dữ liệu để stdout ổn định, không in serial cụ thể.
4. `getNotBefore().toInstant()` và `getNotAfter().toInstant()` đọc hai thời điểm; chương trình kiểm tra trật tự và `checkValidity()` để xét lúc chạy.
5. `certificate.verify(certificate.getPublicKey())` **chỉ** xác minh chữ ký bằng key có trong certificate; trong fixture tự ký, kết quả thành công. **Nó không biến certificate thành trusted root**, không kiểm tra đường dẫn PKIX/hostname/revocation.
6. `getSubjectAlternativeNames()!=null` khẳng định fixture có extension SAN; **không tự xác minh localhost theo tiêu chuẩn TLS**.

Ví dụ chủ động in các assertion có giá trị ổn định thay vì in serial và mốc thời gian chính xác, vì hai trường đó thay đổi theo lúc `keytool` tạo chứng thư. Trong ứng dụng kiểm kê, bạn có thể log **serial hex và ISO timestamp** theo chính sách dữ liệu hệ thống:

```java
String serial = certificate.getSerialNumber().toString(16);
Instant validFrom = certificate.getNotBefore().toInstant();
Instant validUntil = certificate.getNotAfter().toInstant();
```

Đây là **đoạn code nhúng** trong phương thức đã có biến `certificate` kiểu `X509Certificate`, cần import `Instant`. Không dùng các giá trị này làm quyết định cho phép truy cập nếu chưa xác minh chính sách PKIX.

## 8. Thực hành 3: kiểm tra chính xác ranh giới thời hạn

Có thể dùng `checkValidity(Date)` để kiểm tra **cùng một certificate** ở nhiều thời điểm, không phụ thuộc ngày hiện tại của máy. Với fixture 30 ngày ở bước trước, ta thử:

- 1 giây **trước notBefore** → `CertificateNotYetValidException`.
- **Điểm giữa** khoảng hiệu lực → hợp lệ về thời gian.
- 1 giây **sau notAfter** → `CertificateExpiredException`.

Tạo **`X509ValidityBoundsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public class X509ValidityBoundsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java X509ValidityBoundsDemo <cert.pem>");
        }
        X509Certificate cert;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            cert = (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }

        Instant from = cert.getNotBefore().toInstant();
        Instant to = cert.getNotAfter().toInstant();
        Instant midpoint = from.plusMillis(Duration.between(from, to).toMillis() / 2);

        boolean earlierRejected = false;
        try {
            cert.checkValidity(Date.from(from.minusSeconds(1)));
        } catch (CertificateNotYetValidException expected) {
            earlierRejected = true;
        }
        cert.checkValidity(Date.from(midpoint));

        boolean laterRejected = false;
        try {
            cert.checkValidity(Date.from(to.plusSeconds(1)));
        } catch (CertificateExpiredException expected) {
            laterRejected = true;
        }

        System.out.println("before notBefore rejected: " + earlierRejected);
        System.out.println("midpoint accepted: true");
        System.out.println("after notAfter rejected: " + laterRejected);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 X509ValidityBoundsDemo.java
java X509ValidityBoundsDemo sample-cert.pem
```

Đầu ra đã kiểm tra:

```text
before notBefore rejected: true
midpoint accepted: true
after notAfter rejected: true
```

Ý nghĩa:

- Không phụ thuộc timezone hiển thị vì `Instant` và `Date.from` cùng biểu diễn **thời điểm tuyệt đối**.
- Việc bắt hai exception riêng giúp phân biệt lý do về **thời hạn**.
- `midpoint` được tạo từ chính thời hạn của certificate và nằm giữa hai biên của fixture.
- Kiểm tra **tại một thời điểm giả lập** hữu ích cho unit test và test expiry, nhưng **không nên dùng tùy ý một date trong quá khứ để “vượt hạn” certificate trong kết nối TLS hiện tại**.
- Một lần `checkValidity` thành công vẫn chưa xác minh trust chain/revocation/danh tính dịch vụ.

## 9. Từ các trường X.509 đến xác minh chứng thư thật

Một sơ đồ tối giản:

```text
certificate bytes (PEM/DER)
           |
           v
CertificateFactory: parse cấu trúc X.509
           |
           v
Đọc subject / issuer / serial / validity
           |
           v
       checkValidity
           |
           v
  Chỉ biết thông tin và mốc thời gian
           |
           +--> Chưa chứng minh chữ ký của CA đúng
           +--> Chưa tìm trust anchor đáng tin
           +--> Chưa kiểm tra policy/KU/EKU/name constraints
           +--> Chưa kiểm tra hostname/SAN
           +--> Chưa đánh giá revocation
```

Để xác minh toàn bộ đường dẫn trong Java, các API liên quan gồm `CertPathValidator`, `PKIXParameters`, `TrustAnchor` và các thành phần `TrustManager` của TLS, thường do thư viện TLS/HTTPS gọi theo cấu hình. **Đừng tự xây policy xác thực từ chuỗi DN và ngày hết hạn**.

Các ranh giới quan trọng:

1. **`getIssuerX500Principal()` không lấy public key CA.** Tên issuer chỉ là một trường. Public key CA cần lấy từ chain/trust anchor đã kiểm chứng.
2. **`certificate.verify(publicKey)` không xây chain**. Nó chỉ kiểm chữ ký của chứng thư hiện tại với **key được đưa vào**; nếu bạn tự lấy key từ input không tin cậy thì có thể kiểm chữ ký đúng nhưng vẫn không trust.
3. **`checkValidity()` không kiểm tra revocation**. Chứng thư trong hạn vẫn có thể bị CA thu hồi.
4. **Subject DN không thay SAN** trong việc kiểm tên máy chủ TLS hiện đại.
5. **Issuer + serial** hữu ích cho tham chiếu trong PKI/revocation, nhưng **không thay chứng thực issuer/trust**.
6. **X500Principal.equals(...) chỉ so sánh danh tính DN** theo canonical string; nó không kiểm public key hoặc chứng thư.

### 9.1 Làm thế nào để tra chứng thư theo issuer + serial?

Trong hệ thống inventory hoặc CRL, khóa nghiệp vụ có thể gồm:

```text
(canonical issuer DN, certificate serial BigInteger)
```

Điều này phù hợp với phạm vi uniqueness serial trên từng issuer theo RFC 5280. Tuy nhiên, với cơ sở dữ liệu đa PKI, nên kết hợp với **issuer key identifier hoặc certificate fingerprint** khi cần giảm nhầm lẫn giữa CA có tên giống nhau; việc chấp nhận chứng thư vẫn phải dựa trên chain và policy.

Nếu chỉ có chuỗi biểu diễn RFC1779/2253, đừng tự so sánh bằng `String.equalsIgnoreCase`. Dùng `X500Principal` chuẩn và key/chain metadata theo giao thức.

### 9.2 Phân biệt certificate serial với certificate fingerprint

- **Serial number** do CA gán và có uniqueness **trong phạm vi issuer**.
- **Fingerprint** (ví dụ SHA-256 trên toàn bộ DER certificate) là digest của **chính bytes certificate**. Nó hữu ích cho nhận diện/đối chiếu file hoặc pinning theo chính sách, không phải serial.
- Một certificate được parse từ PEM hay DER có cùng bytes DER nội bộ (`getEncoded()`), nên fingerprint DER đúng cách không phụ thuộc whitespace của phần bọc PEM.
- Fingerprint không mặc nhiên là trust anchor: chấp nhận một fingerprint là **quyết định chính sách** và cần quy trình cập nhật/rotation.

## 10. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “Issuer có tên CA nổi tiếng nên trusted.” | Tên có thể bị giả mạo; chưa kiểm chữ ký/chain. | Dùng PKIX/trust store. |
| “`subject.equals(issuer)` = certificate trusted.” | Đây chỉ là **self-issued** theo tên. | Phân biệt self-issued, self-signed, trust anchor. |
| “CN chính là DNS hostname.” | TLS hiện đại so danh tính qua SAN, không CN fallback. | Dùng TLS hostname verification theo RFC 9525. |
| “Serial toàn thế giới là duy nhất.” | Serial duy nhất **theo CA/issuer**. | Kết hợp issuer + serial và trust metadata. |
| “Serial nằm trong subject `SERIALNUMBER=...`.” | Đây là **DN attribute khác**. | `getSerialNumber()` cho certificate serial. |
| “Serial nhỏ, cast `longValue()` cho tiện.” | Có thể mất bit/trùng. | Giữ `BigInteger`. |
| “Mọi subject đều có CN.” | Subject có thể rỗng, SAN có thể mang toàn bộ định danh. | Dùng `getSubjectX500Principal`, xử lý SAN. |
| “Tách DN bằng dấu phẩy.” | Dấu phẩy có thể được escape trong giá trị. | Dùng parser X.500/DN. |
| “So sánh DN text theo ký tự.” | Các format, escape/canonical khác nhau. | Dùng `X500Principal.equals` đúng semantics. |
| “Hết hạn chỉ cần `notAfter`.” | Còn `notBefore` và nhiều yêu cầu PKIX khác. | Dùng `checkValidity` + path validation. |
| “`checkValidity()` = certificate hợp lệ toàn diện.” | Chỉ xét mốc thời gian. | Kiểm chữ ký/chain/trust/policy/revocation/identity. |
| “`Date.toString()` in giờ địa phương là ngày chuẩn trên chứng thư.” | Timezone hiển thị thay đổi, instant không đổi. | Dùng `toInstant()` và ISO-8601 UTC. |
| “Certificate tự ký bằng key đúng là root đáng tin.” | Chứng minh tự ký không đồng nghĩa trust. | Chỉ chấp nhận trust anchor được quản lý. |
| “Có thể sửa ngày/subject trong chứng thư DER.” | Những trường này được CA ký trong TBS. | Phát hành/renew chứng thư mới. |

## 11. Quy trình chẩn đoán trường hợp “certificate rejected”

Một log từ Java ghi “certificate expired”, “PKIX path building failed”, “No subject alternative names matching” có thể xuất phát từ **những lớp kiểm tra khác nhau**. Để phân tích:

1. **Parse certificate**: `CertificateFactory` có đọc đúng PEM/DER không? Có nhầm file private key với certificate không?
2. **Subject/issuer**: in DN bằng `getSubjectX500Principal().getName(RFC2253)` và tương ứng issuer; không xem tên là trust.
3. **Serial**: lấy `BigInteger`/hex để tra CA/CRL hoặc inventory, không trộn với `SERIALNUMBER` thuộc DN.
4. **Validity**: kiểm `notBefore`, `notAfter` bằng UTC; xem đồng hồ máy/server, NTP và thời điểm đang kiểm.
5. **Signature/chain**: chuỗi leaf → intermediate → trust anchor có đủ, issuer DN có nối đúng và chữ ký được verify bằng key CA chính xác không?
6. **Policy**: BasicConstraints, KeyUsage, ExtendedKeyUsage, name constraints và thuật toán có đáp ứng ứng dụng không?
7. **Revocation**: CRL/OCSP được cấu hình và có trạng thái phù hợp theo chính sách không?
8. **TLS service identity**: SAN có DNS/IP đúng tên dịch vụ truy cập không? Có tắt hostname verification không?
9. **Nếu dùng mã tùy chỉnh**: xác minh rằng nó **không** chỉ so chuỗi subject, thời hạn hay serial rồi bypass trust manager.

Không ghi private key, token hay nội dung bí mật vào log. Public certificate thường không bí mật, nhưng vẫn có thể chứa thông tin định danh; hãy áp dụng chính sách logging/quyền truy cập của tổ chức.

## 12. Bài tập tự kiểm tra

**Câu 1.** Subject và issuer khác nhau thế nào?  
**Trả lời:** Subject xác định chủ thể gắn với public key; issuer xác định thực thể CA đã phát hành/ký certificate.

**Câu 2.** `CN=example.com` trong subject có đủ để TLS Java client tin `https://example.com` không?  
**Trả lời:** Không. Cần kiểm tra trust chain/policy và định danh dịch vụ qua SAN theo cơ chế TLS hiện đại.

**Câu 3.** Hai CA khác nhau có thể cấp cùng serial number `42` không?  
**Trả lời:** Có. Serial là duy nhất **trong phạm vi mỗi issuer/CA**, không trên toàn Internet.

**Câu 4.** `SERIALNUMBER=ASSET-123` của subject DN có giống `getSerialNumber()` không?  
**Trả lời:** Không. Một bên là AVA/OID trong DN, bên kia là số serial của chứng thư do CA gán.

**Câu 5.** Khi gặp `CertificateNotYetValidException` và `CertificateExpiredException`, chúng khác gì?  
**Trả lời:** Thời điểm kiểm trước `notBefore` versus sau `notAfter`.

**Câu 6.** `cert.checkValidity()` trả về bình thường có chứng minh certificate trusted không?  
**Trả lời:** Không; mới kiểm tra khoảng thời gian hiệu lực của certificate tại thời điểm hiện tại.

**Câu 7.** Vì sao `X500Principal` tốt hơn `String.split(",")`?  
**Trả lời:** DN có cú pháp ASN.1/RDN, dấu phẩy escape, RDN đa giá trị, OID và canonical form; split chuỗi thô không hiểu cấu trúc.

**Câu 8.** Certificate có `subject == issuer` thì là gì?  
**Trả lời:** **Self-issued** về tên. Cần verify chữ ký riêng để xác định self-signed, và vẫn phải có trust policy.

**Câu 9.** `getNotAfter()` trả `Date` theo múi giờ Việt Nam hay UTC?  
**Trả lời:** Nó đại diện cho một **instant tuyệt đối**; dạng hiển thị `Date.toString()` phụ thuộc timezone máy. Chuyển `toInstant()` để hiển thị UTC rõ ràng.

**Câu 10.** Vì sao subject DN có thể trống?  
**Trả lời:** RFC 5280 cho phép chủ thể được nhận diện qua SAN; khi subject DN rỗng, SAN phải có mặt và được đánh dấu critical.

## Tổng kết

```text
X509Certificate
  ├─ getSubjectX500Principal() -> subject DN
  ├─ getIssuerX500Principal()  -> issuer DN
  ├─ getSerialNumber()         -> BigInteger (duy nhất theo issuer)
  ├─ getNotBefore()            -> Date -> Instant
  ├─ getNotAfter()             -> Date -> Instant
  └─ checkValidity([Date])     -> chỉ xét khoảng thời gian

X500Principal
  ├─ getName(RFC2253/CANONICAL) -> biểu diễn DN
  ├─ getEncoded()               -> DER của Name
  └─ equals(...)                -> so sánh DN canonical

Issuer + serial + validity + subject
  = thông tin cần thiết về chứng thư
  ≠ xác minh hoàn chỉnh chữ ký/PKIX/hostname/revocation
```

Ghi nhớ quan trọng nhất: **subject** là tên chủ thể, **issuer** là tên bên phát hành, **serial** có tính duy nhất **theo CA**, **notBefore/notAfter** xác định cửa sổ thời gian; `X500Principal` xử lý DN có cấu trúc. Khi quyết định có **tin** chứng thư hay không, phải dùng **PKIX và chính sách xác thực dịch vụ** chứ không dựa vào các trường mô tả độc lập.

## Tài liệu tham khảo chính thức

- [Java 17 — X509Certificate API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): subject, issuer, serial, validity, SAN và `checkValidity`.
- [Java 17 — X500Principal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/x500/X500Principal.html): DN, RFC2253/RFC1779/CANONICAL, DER và `equals`.
- [Java 17 — CertificateFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): đọc certificate PEM/DER.
- [RFC 5280 `4.1.2.2–`4.1.2.6](https://www.rfc-editor.org/rfc/rfc5280#section-4.1.2.2): serial number, issuer, validity, subject và quy tắc SAN rỗng/critical.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): định danh dịch vụ TLS dựa trên SAN, thay thế RFC 6125.
- [Java 17 — CertPathValidator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): kiểm tra certification path thay vì chỉ nhìn DN/Date.
