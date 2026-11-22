# 13.5. Subject Alternative Name và danh tính DNS hoặc địa chỉ IP

## 1. SAN giải quyết vấn đề gì trong chứng thư X.509?

Khi một HTTPS client kết nối tới `https://api.example.test`, việc máy chủ trình ra **một chứng thư X.509 có chữ ký hợp lệ** chưa đủ. Client cần biết chứng thư đó có được cấp cho **đúng máy chủ mà client định truy cập** hay không. Nếu chỉ xác thực đường dẫn chứng thư (*certificate path*) đến một CA tin cậy nhưng bỏ qua **danh tính endpoint**, kẻ tấn công có thể dùng một chứng thư hợp lệ cấp cho tên **khác** để đánh lừa client.

**Subject Alternative Name (SAN)** là extension của chứng thư X.509, có OID `2.5.29.17`, dùng để chứa một hoặc nhiều định danh có kiểu rõ ràng: tên DNS, địa chỉ IP, địa chỉ email, URI và một số dạng khác. Đối với danh tính máy chủ TLS/HTTPS, hai kiểu rất quan trọng là:

- **dNSName (GeneralName type 2):** tên DNS, ví dụ `api.example.test` hoặc `*.svc.example.test`.
- **iPAddress (GeneralName type 7):** địa chỉ IPv4/IPv6 dạng **octet nhị phân** trong extension, ví dụ IPv4 `192.0.2.10` hoặc IPv6 `2001:db8::10`.

Trong Java, `java.security.cert.X509Certificate.getSubjectAlternativeNames()` cho phép **đọc** các SAN của chứng thư, nhưng **không tự thực hiện xác minh danh tính máy chủ**. Để bảo vệ kết nối thực tế, phải có đồng thời:

1. **Tin cậy chứng thư:** xác minh certificate path, CA/trust anchor, hiệu lực, key usage/EKU và các chính sách cần thiết.
2. **Khớp endpoint identity:** so hostname/IP **mà client muốn truy cập** với SAN đúng kiểu, theo quy tắc giao thức.
3. **Handshake và chính sách TLS:** kết nối thật sự dùng private key tương ứng với chứng thư được chấp nhận, các tham số TLS an toàn và không vô hiệu hóa các bước kiểm tra trên.

Bài này làm rõ vì sao **DNS SAN không thay thế IP SAN**, vì sao không nên dựa vào `Common Name (CN)`, cách đọc SAN bằng Java 17+, và cách yêu cầu JSSE/HTTP client kiểm tra danh tính đúng thay vì tự viết bộ so khớp tên đơn giản.

## 2. Cấu trúc SubjectAltName trong X.509

Theo RFC 5280, extension gồm chuỗi `GeneralName`; mỗi phần tử có **type** và **value** riêng:

```text
X.509 Certificate
├─ Subject Distinguished Name (DN)
│  └─ CN=legacy.example.test                 <-- thuộc subject, KHÔNG phải SAN
├─ Subject Public Key Info (SPKI)
├─ Issuer, serial, validity, signature...
└─ Extensions
   └─ subjectAltName (OID 2.5.29.17)
      ├─ [2] dNSName: api.example.test
      ├─ [2] dNSName: *.svc.example.test
      ├─ [7] iPAddress: 192.0.2.10
      └─ [7] iPAddress: 2001:db8::10
```

Đây là dữ liệu của **một chứng thư thử nghiệm**, không phải chứng thư của máy chủ công khai thật. Miền `.test`, IPv4 `192.0.2.0/24` và IPv6 `2001:db8::/32` được dùng cho ví dụ/tài liệu.

Một chứng thư có thể chứa **nhiều SAN cùng loại** và nhiều loại khác nhau. Việc có hai dNSName không có nghĩa một tên “ghi đè” tên kia: tùy chính sách, bất kỳ dNSName hợp lệ nào khớp với tên được mong đợi đều có thể được chấp nhận. Các chứng thư dùng chung cho nhiều hostname phải được cấp phát, kiểm soát và xoay vòng cẩn thận vì sự cố private key có thể ảnh hưởng đến tất cả các tên trên chứng thư.

### Bảng các GeneralName thường gặp

| Type trong `getSubjectAlternativeNames()` | Tên ASN.1 | Mục đích và cách hiểu |
| --- | --- | --- |
| `1` | `rfc822Name` | Địa chỉ email. Không phải DNS-ID thay thế cho HTTPS. |
| `2` | `dNSName` | Danh tính dựa trên DNS, dùng khi client truy cập theo tên miền. |
| `6` | `uniformResourceIdentifier` | URI identity ở giao thức quy định; không mặc nhiên thay thế dNSName của HTTPS. |
| `7` | `iPAddress` | Địa chỉ IPv4/IPv6, dùng khi reference identity là IP literal theo quy tắc ứng dụng. |
| `0`, `3`, `4`, `5`, `8` | OtherName, X.400, directoryName, EDI, registeredID | Các định danh có cấu trúc khác, chỉ có ý nghĩa theo giao thức và chính sách tương ứng. |

**SubjectAltName khác IssuerAlternativeName.** SAN mô tả danh tính liên quan đến **subject** của chứng thư; extension `IssuerAlternativeName` mô tả các định danh bổ sung của **issuer**. Khi đối chiếu server hostname, không tìm DNS SAN trong IssuerAlternativeName.

## 3. DNS-ID: khi client truy cập bằng hostname

Nếu ứng dụng gọi `https://api.example.test/orders`, reference identity thường là **hostname `api.example.test` từ đích kết nối đã được ứng dụng lựa chọn**, không phải chuỗi do certificate tự gợi ý, do reverse DNS ngẫu nhiên tạo ra hoặc do một HTTP header kẻ tấn công điều khiển.

Ví dụ chứng thư có:

```text
subjectAltName:
  DNS:api.example.test
  DNS:*.svc.example.test
  IP Address:192.0.2.10
```

Theo quy tắc DNS-ID hiện đại, chứng thư có thể dùng cho `api.example.test`; wildcard `*.svc.example.test` có thể khớp với **một nhãn** như `a.svc.example.test` nhưng không được hiểu là khớp mọi cấp sâu tùy ý.

### 3.1. Tên DNS được so khớp theo tên, không theo IP DNS trả về

Ví dụ DNS trả về:

```text
api.example.test  --DNS A-->  192.0.2.10
```

Client truy cập bằng URL `https://api.example.test` sẽ kiểm tra **DNS-ID cho `api.example.test`**, dù kết nối TCP tới một địa chỉ IP sau khi phân giải. Điều này là cách bình thường khi nhiều virtual host được phục vụ trên cùng IP.

Không được lấy kết quả DNS A/AAAA, rồi tự đổi yêu cầu sang IP-ID nếu người dùng thực ra đã chỉ định tên DNS. Danh tính mong đợi phải xuất phát từ thông tin đích được tin cậy trong ứng dụng/giao thức.

### 3.2. So khớp wildcard không phải String.endsWith()

Theo RFC 9525, wildcard trong DNS-ID chỉ được chấp nhận dưới dạng **nguyên nhãn nằm ngoài cùng bên trái**. Với mẫu `*.svc.example.test`:

| Reference hostname | Khớp wildcard đó? | Vì sao |
| --- | --- | --- |
| `a.svc.example.test` | Có, theo quy tắc wildcard một nhãn | `*` thay cho nhãn `a` |
| `b.svc.example.test` | Có | Một nhãn hợp lệ |
| `svc.example.test` | Không | Thiếu nhãn bên trái |
| `a.b.svc.example.test` | Không | Có **hai** nhãn bên trái |
| `not-svc.example.test` | Không | Không cùng cấu trúc nhãn |
| `192.0.2.10` | Không | IP-ID và DNS-ID là hai kiểu khác nhau |

Các chuỗi như `a*.example.test`, `*.*.example.test` hoặc dùng `*` như phép so khớp tùy ý không đáp ứng quy tắc chuẩn này. Kiểm tra còn phụ thuộc yêu cầu giao thức/ứng dụng và chính sách xử lý wildcard; **đừng tự triển khai** dựa vào `replace("*", ".*")`, regex tự chế hay kiểm tra suffix mà không hiểu chuẩn.

### 3.3. Chữ hoa, IDN và định dạng tên miền

Tên DNS được so khớp theo quy tắc DNS/IDNA thích hợp, không phải đơn giản so byte UTF-8 của text hiển thị. Các domain quốc tế hóa thường phải được biểu diễn bằng **ASCII A-label/Punycode theo IDNA** trong dNSName, thay vì bỏ trực tiếp Unicode U-label vào extension IA5String.

Ứng dụng cần dùng thư viện TLS/hostname verification và quy tắc hostname normalization được profile của giao thức quy định. Không tự gọi `toLowerCase()` theo locale rồi so suffix, không bỏ qua ký tự đặc biệt hoặc dấu chấm một cách tùy tiện, và không cho phép client chuyển danh tính mong đợi qua input không tin cậy.

## 4. IP-ID: khi client truy cập bằng địa chỉ IP

Nếu URL/endpoint được chỉ định trực tiếp là `https://192.0.2.10` hoặc `https://[2001:db8::10]`, reference identity là **IP address**, không phải DNS hostname. Theo RFC 9525, IP-ID so khớp **chính xác các octet của địa chỉ IP** với trường `iPAddress` nằm trong SAN.

Trong ASN.1 X.509:

- `iPAddress` IPv4 được mã hóa thành **4 octet**.
- `iPAddress` IPv6 được mã hóa thành **16 octet**.
- Không phải văn bản `"192.0.2.10"` được nhét vào `dNSName` rồi coi là IP-ID.
- Các cách biểu diễn text IPv6 khác nhau có thể trỏ tới **cùng 16 octet**; parser Java có thể trả lại chuỗi IP ở dạng mở rộng thay vì dạng nén ban đầu.

Ví dụ:

```text
DNS SAN: api.example.test
IP SAN: 192.0.2.10

Client A: https://api.example.test  -> cần DNS-ID api.example.test
Client B: https://192.0.2.10        -> cần IP-ID 192.0.2.10
Client C: https://192.0.2.11        -> IP không khớp, phải từ chối
```

**Sai lầm phổ biến:** chứng thư có `DNS:192.0.2.10` nhưng không có `IP Address:192.0.2.10`. Đó là một dNSName chứa các ký tự trông giống địa chỉ IP, **không phải** SAN iPAddress đúng kiểu. Không cố “cứu” bằng cách so text giữa hai type.

**Cũng sai:** khi kết nối tới `192.0.2.10`, thực hiện reverse DNS rồi cho phép bất kỳ hostname nhận được khớp với DNS SAN. Việc so IP-ID cần dựa vào IP reference được chọn, không bị thay bằng tên từ reverse DNS không đáng tin.

Nếu ứng dụng cần truy cập backend theo IP nhưng chứng thư được cấp cho DNS hostname, hãy cấu hình **hostname chuẩn được tin cậy** và kết nối theo mô hình/giao thức đúng (ví dụ kết nối TCP tới IP được chỉ định nhưng TLS endpoint identity và SNI được cấu hình cho DNS tên đã biết). Không tắt hostname verification để chữa lỗi chứng thư.

## 5. Common Name (CN) có còn được dùng làm danh tính server không?

Trước đây nhiều triển khai kiểm tra CN trong `Subject DN` khi chứng thư không chứa dNSName SAN. Thực hành này có thể gây nhầm lẫn vì CN không có kiểu ràng buộc đủ rõ như SAN, và chính sách fallback từng khác nhau giữa client/provider.

**RFC 9525 (2023), thay thế RFC 6125**, quy định **không sử dụng Common Name RDN để nhận diện dịch vụ**; server identity được biểu diễn trong các subjectAltName phù hợp. Vì thế với thiết kế mới:

- Cấp chứng thư HTTPS có **SAN dNSName và/hoặc iPAddress đúng kiểu** cho mọi endpoint được cho phép.
- **Không dựa** vào `CN` để hợp thức hóa hostname/IP khi SAN không phù hợp.
- Không dựa vào việc một client cũ có thể fallback sang CN như bằng chứng sản phẩm sẽ hoạt động an toàn trên các JDK/client khác.
- `Subject DN` vẫn có vai trò metadata của chứng thư theo PKI; câu này chỉ nói đến cách xác minh **service endpoint identity**, không nói bỏ mọi thông tin Subject.

Bộ fixture trong phần Java cố ý tạo `CN=legacy.example.test` nhưng **không** đưa tên đó vào DNS SAN. Chương trình sẽ chứng minh việc đọc SAN **không tự thêm CN**; khi dùng TLS client theo policy hiện đại, không được xem CN là một danh tính thay thế nếu không có DNS-ID đúng.

## 6. SAN matching khác với xác minh chứng thư đáng tin

Những thao tác sau có vai trò khác nhau:

| Thao tác | Nó kiểm tra gì? | Điều **chưa** được chứng minh |
| --- | --- | --- |
| `CertificateFactory.generateCertificate(...)` | Parse DER/PEM thành `Certificate` | Không chứng minh CA, trust path, hiệu lực hoặc hostname đã được chấp nhận |
| `X509Certificate.getSubjectAlternativeNames()` | Liệt kê subject SAN được mã hóa trong chứng thư | Không thực hiện hostname verification |
| `X509Certificate.getSubjectX500Principal()` | Trả Subject DN như X.500 principal | CN không phải DNS-ID/IP-ID hợp lệ theo RFC 9525 |
| `X509Certificate.checkValidity()` | Kiểm tra `notBefore`/`notAfter` theo thời gian | Không xác thực chuỗi chứng thư hoặc hostname |
| `X509Certificate.verify(issuerPublicKey)` | Kiểm tra chữ ký chứng thư với public key đã đưa vào | Không tự xây trust path hoặc xác minh tên máy chủ |
| `CertPathValidator` với PKIX policy | Xác minh đường dẫn chứng thư theo tham số/trust anchor được cung cấp | Không mặc nhiên so hostname URL với SAN |
| JSSE/HTTP TLS client cấu hình đúng | Handshake, trust manager và endpoint identification | Không thay thế business authorization/identity mapping cấp ứng dụng |

**Phải có đủ cả hai điều kiện**: certificate chain hợp lệ theo trust policy **và** SAN khớp danh tính endpoint. Nếu chứng thư tự ký chứa `DNS:api.example.test` nhưng không được một trust anchor được cấu hình tin cậy, vẫn phải bị từ chối. Ngược lại, nếu chứng thư của CA tin cậy có SAN cho `other.example.test` nhưng client đang kết nối `api.example.test`, cũng phải bị từ chối.

SAN extension **không phải chữ ký riêng**: nó nằm trong nội dung chứng thư được issuer ký. Tuy nhiên một extension SAN chứa text đúng **không tự tạo ra trust**; client phải xác minh toàn bộ chứng thư theo PKI và biết mình đang yêu cầu tên nào.

### 6.1. Chain, thời hạn, KeyUsage, EKU và Name Constraints

Ngoài SAN, hệ thống production thường cần kiểm tra:

- Chữ ký/certificate path dẫn về trust anchor được chấp nhận; CA có thẩm quyền cấp phát chứng thư tương ứng.
- `notBefore`/`notAfter` và chính sách về thời gian, certificate revocation khi profile yêu cầu.
- `BasicConstraints`, `KeyUsage` và `ExtendedKeyUsage` phù hợp với vai trò server TLS (ví dụ EKU `serverAuth` khi được quy định).
- `NameConstraints` trên CA/intermediate certificate nếu có, có thể giới hạn các subtree DNS/IP được phép.
- Algorithm policy, độ mạnh khóa, signature algorithm, key rotation và pinning nếu áp dụng.
- Kết nối mạng đến đúng endpoint và ứng dụng không bị chuyển hướng sang một origin khác mà bỏ kiểm tra.

Không cố tái hiện tất cả các kiểm tra PKIX/TLS ở lớp ứng dụng chỉ với `X509Certificate` getter. Hãy tận dụng JSSE/HTTP client và truststore hợp lệ, hoặc một TLS implementation đã được kiểm toán.

## 7. Java 17+: đọc SAN thật từ một chứng thư X.509

Trong JCA, `X509Certificate.getSubjectAlternativeNames()` trả `Collection<List<?>>` hoặc `null` nếu chứng thư không có extension SAN. Mỗi phần tử là một list hai phần:

1. `Integer` biểu diễn GeneralName type (0–8).
2. Giá trị thường là `String` cho các type như DNS `2`, IPv4/IPv6 `7`, URI `6` hoặc byte[] DER với một số type khác.

Đặc biệt, với type `7` Java trả chuỗi IP ở định dạng có thể hiển thị, **không nhất thiết giữ nguyên text IPv6 nén**. Ví dụ dùng `InetAddress` để so octet của hai **IP literal đã biết**, chỉ phục vụ khám phá dữ liệu SAN; đây **không phải** thuật toán hostname verification cho HTTPS.

### 7.1. Chứng thư thử nghiệm nhúng trong mã

Để ví dụ chạy độc lập mà không phụ thuộc máy chủ mạng, chương trình nhúng **một chứng thư self-signed công khai dành riêng cho demo** dưới dạng PEM. Fixture có:

```text
Subject DN: CN=legacy.example.test, OU=Testing, O=Demo, C=US
SAN:
  DNS:api.example.test
  DNS:*.svc.example.test
  IP Address:192.0.2.10
  IP Address:2001:db8::10
```

**Không có private key trong source**. Đây không phải chứng thư server hợp lệ trên Internet: self-signed và sử dụng tên/địa chỉ tài liệu. Chương trình **chỉ parse** chứng thư và in các SAN. Nó **không** kiểm tra path đến CA tin cậy, không tạo kết nối TLS và không chứng minh tên máy chủ được chấp nhận.

Tạo tệp `SanCertificateDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;

public final class SanCertificateDemo {
    // Public, self-signed test certificate; no private key is embedded.
    private static final String CERT_PEM = """
            -----BEGIN CERTIFICATE-----
            MIIB+DCCAZ+gAwIBAgIJAJ14rTcMr16LMAoGCCqGSM49BAMDMEwxCzAJBgNVBAYT
            AlVTMQ0wCwYDVQQKEwREZW1vMRAwDgYDVQQLEwdUZXN0aW5nMRwwGgYDVQQDExNs
            ZWdhY3kuZXhhbXBsZS50ZXN0MB4XDTI2MTAzMTEzMjQxMVoXDTI5MDcyNzEzMjQx
            MVowTDELMAkGA1UEBhMCVVMxDTALBgNVBAoTBERlbW8xEDAOBgNVBAsTB1Rlc3Rp
            bmcxHDAaBgNVBAMTE2xlZ2FjeS5leGFtcGxlLnRlc3QwWTATBgcqhkjOPQIBBggq
            hkjOPQMBBwNCAARGSmwZAOpA+2rAEjrl4hYnRfXTYl5cG2hOHfsJs1fPt1B/fxv0
            Saplz7XtuMHGX7uCY+ftWgQlA18JsxMk4oQto2owaDAdBgNVHQ4EFgQU4oNvse+X
            n0vCSxlfkgX1Lp3Tg9cwRwYDVR0RBEAwPoIQYXBpLmV4YW1wbGUudGVzdIISKi5z
            dmMuZXhhbXBsZS50ZXN0hwTAAAIKhxAgAQ24AAAAAAAAAAAAAAAQMAoGCCqGSM49
            BAMDA0cAMEQCIEpTPuvkpgvpAdaxnl2kpOek3cBS4Jl+/xOBcTpBj/NqAiBgfrDl
            ZfNneRagyWvbB3UzpTea0ddr9XAePvhjG/e0BQ==
            -----END CERTIFICATE-----
            """;

    private static boolean hasIp(List<String> ipSans, String literal)
            throws Exception {
        byte[] expected = InetAddress.getByName(literal).getAddress();
        for (String ipSan : ipSans) {
            byte[] actual = InetAddress.getByName(ipSan).getAddress();
            if (Arrays.equals(expected, actual)) return true;
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        byte[] pem = CERT_PEM.getBytes(StandardCharsets.US_ASCII);
        X509Certificate certificate = (X509Certificate) factory
                .generateCertificate(new ByteArrayInputStream(pem));

        Collection<List<?>> sans = certificate.getSubjectAlternativeNames();
        List<String> dnsSans = new ArrayList<>();
        List<String> ipSans = new ArrayList<>();
        if (sans != null) {
            for (List<?> name : sans) {
                int type = ((Integer) name.get(0)).intValue();
                Object value = name.get(1);
                if (type == 2 && value instanceof String dns) dnsSans.add(dns);
                if (type == 7 && value instanceof String ip) ipSans.add(ip);
            }
        }

        System.out.println("Certificate type: " + certificate.getType());
        System.out.println("DNS SANs: " + dnsSans);
        System.out.println("IPv4 SAN present: " + hasIp(ipSans, "192.0.2.10"));
        System.out.println("IPv6 SAN present: " + hasIp(ipSans, "2001:db8::10"));
        System.out.println("Legacy CN in DNS SAN: " +
                dnsSans.contains("legacy.example.test"));
        System.out.println("DNS SAN count: " + dnsSans.size());
        System.out.println("IP SAN count: " + ipSans.size());
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac SanCertificateDemo.java
java SanCertificateDemo
```

Stdout chính xác:

```text
Certificate type: X.509
DNS SANs: [api.example.test, *.svc.example.test]
IPv4 SAN present: true
IPv6 SAN present: true
Legacy CN in DNS SAN: false
DNS SAN count: 2
IP SAN count: 2
```

### 7.2. Đọc đúng kết quả

- `CertificateFactory` đã parse một chứng thư dạng X.509 — **chưa có trust decision**.
- Hai giá trị type `2` của SAN đúng thứ tự trong fixture là `api.example.test` và `*.svc.example.test`.
- Hai giá trị type `7` chứa IPv4 và IPv6. Hàm `hasIp` chuyển **IP literal** sang octet để kiểm tra sự hiện diện, do text IPv6 có thể được định dạng khác nhau dù giá trị nhị phân giống nhau.
- Tên `legacy.example.test` nằm trong **CN**, không nằm trong DNS SAN, nên kiểm tra `dnsSans.contains(...)` trả `false`.
- `getSubjectAlternativeNames()` có thể là `null` nếu không có SAN; code xử lý tình huống đó bằng danh sách rỗng. Một ứng dụng hostname verification hiện đại nên từ chối server identity không có SAN phù hợp thay vì tự lấy CN thay thế.
- Việc dữ liệu SAN được liệt kê **không nghĩa là** chương trình đã xác minh wildcard, chain, hạn dùng, key usage hoặc quyền điều khiển domain.

**Đây là demo đọc metadata, không phải hàm kiểm tra hostname.** Đặc biệt không copy `hasIp` hoặc `dnsSans.contains` làm bộ xác minh TLS tự viết: các phép kiểm này bỏ qua trust path, chính sách reference identity, wildcard, IDNA, certificate constraints và nhiều yếu tố bảo mật khác.

## 8. Để Java thực sự xác minh hostname/IP khi kết nối TLS

### 8.1. Ưu tiên HTTP client cấu hình an toàn mặc định

Với HTTPS, các API như `java.net.http.HttpClient` hoặc `HttpsURLConnection` có cơ chế TLS và xác minh server identity theo cấu hình mặc định thích hợp. Khi xây ứng dụng, hãy để hostname từ **URI/endpoint mong đợi** tham gia xác minh chứng thư, dùng truststore tin cậy và không vô hiệu hóa việc kiểm tra tên.

Ví dụ **đoạn mã minh họa**, không phải chương trình độc lập với fixture tự ký:

```java
// Chỉ gửi tới endpoint thật với chứng thư hợp lệ theo trust policy.
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/orders"))
        .GET()
        .build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Trong code thực cần import `java.net.URI` và `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`. Host `api.example.test` ở đây **chỉ là ví dụ**, không phải tên một server công khai có sẵn. Đừng thực thi snippet này rồi diễn giải lỗi DNS hoặc lỗi trust là lỗi của SAN parser phía trên.

**Không** đặt trust manager “accept all”, không cài `HostnameVerifier` luôn trả true và không cố tắt endpoint identification để “sửa lỗi SAN”.

### 8.2. Với SSLSocket/SSLEngine, bật endpoint identification rõ ràng

Khi sử dụng socket TLS mức thấp, lập trình viên có thể cần cấu hình `SSLParameters` để kích hoạt kiểm tra danh tính endpoint. Ví dụ **đoạn mã minh họa cho một server thật**, không dùng fixture self-signed ở demo:

```java
SSLSocketFactory factory = (SSLSocketFactory) SSLSocketFactory.getDefault();
try (SSLSocket socket =
        (SSLSocket) factory.createSocket("api.example.test", 443)) {
    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);
    socket.startHandshake(); // Trust chain + endpoint identity theo JSSE.
}
```

Cần import `javax.net.ssl.SSLSocketFactory`, `SSLSocket` và `SSLParameters`. Một `SSLContext`/truststore thích hợp và chính sách chứng thư đúng vẫn là điều kiện bắt buộc. Ví dụ được viết để giải thích cách sử dụng API; tên miền `.test` không phục vụ kết nối thật.

`setEndpointIdentificationAlgorithm("HTTPS")` là **không phải** lời gọi `X509Certificate.getSubjectAlternativeNames()`. Nó chỉ dẫn JSSE thực hiện xác minh endpoint trong handshake theo cấu hình và implementation hỗ trợ. Không đặt thuật toán thành `null` hoặc chuỗi rỗng để bỏ qua bước kiểm tra vì các tùy chọn đó có thể khiến danh tính không được xác minh.

**SNI và endpoint identification khác nhau:** SNI giúp client *nói với server* mình muốn virtual host nào để server chọn certificate; endpoint identification là việc *client kiểm tra* chứng thư nhận được có khớp với đích mong đợi không. Gửi SNI đúng **không thay thế** kiểm tra hostname.

### 8.3. Nếu client kết nối theo địa chỉ IP

Ví dụ với `https://192.0.2.10`, chứng thư cần chứa SAN type `7` tương ứng với IPv4 đó, theo policy ứng dụng. Không thay bằng `DNS:192.0.2.10` hoặc `CN=192.0.2.10`.

Với IPv6 URL, địa chỉ phải được viết trong dấu ngoặc vuông ở phần authority của URI, ví dụ `https://[2001:db8::10]/`; SAN iPAddress chứa **16 octet IP**, không chứa ký tự ngoặc vuông. Nếu thực tế kết nối bằng DNS hostname nhưng socket đi tới IP đã biết, phải giữ **hostname tin cậy** làm reference identity cho TLS và cấu hình socket/peer host phù hợp, không đơn giản dùng IP rồi tắt kiểm tra.

## 9. SAN matching, truststore, certificate pinning: quan hệ thế nào?

### Truststore và CA

Truststore chứa các trust anchors/certificates mà client được phép tin theo policy. Một CA tin cậy có thể cấp nhiều chứng thư cho các máy chủ khác nhau; vì vậy **đường tin cậy hợp lệ chưa đủ**, vẫn phải đối chiếu SAN hostname/IP của **đích client đang truy cập**.

### Certificate/public-key pinning

Pinning có thể ràng buộc kết nối với một certificate hoặc SPKI/public key đã biết từ một kênh tin cậy. Nó có thể giảm một số rủi ro thay chứng thư nhưng phát sinh bài toán **rotation**, thu hồi, pin dự phòng và cấu hình outage. Không lấy “pin” bằng cách chấp nhận nguyên certificate vừa nhận từ kênh chưa được xác thực rồi coi mọi lần kết nối đầu tiên đều an toàn. Pinning **không phải** lý do mặc định để bỏ qua hostname verification hoặc chain validation, trừ khi ứng dụng có profile tin cậy được thiết kế/kiểm toán rõ ràng.

### mTLS (mutual TLS)

Trong mTLS, **client** cũng trình chứng thư cho server. Kiểm tra danh tính của **client** thường dựa vào profile ứng dụng (ví dụ URI SAN, DNS SAN, danh tính service mesh hoặc đặc tả nội bộ) và policy authorization. Không mặc định lấy bất kỳ DNS SAN của client certificate để cho phép mọi tenant. Xác thực client và xác thực hostname server là **hai hướng khác nhau** cần quản trị identity riêng.

## 10. Các tình huống thực tế và kết quả mong đợi

| Client mong đợi | SAN của server | Kết luận ở bước khớp danh tính | Nhắc lại |
| --- | --- | --- | --- |
| `api.example.test` | `DNS:api.example.test` | Khớp DNS-ID | Vẫn cần trust chain, hiệu lực và policy |
| `API.EXAMPLE.TEST` | `DNS:api.example.test` | Phù hợp khi so sánh DNS đúng chuẩn không phân biệt hoa/thường | Không dùng locale tùy ý |
| `a.svc.example.test` | `DNS:*.svc.example.test` | Khớp wildcard một nhãn theo RFC 9525 | Không cho phép wildcard vượt một label |
| `a.b.svc.example.test` | `DNS:*.svc.example.test` | Không khớp | Không dùng suffix-only |
| `svc.example.test` | `DNS:*.svc.example.test` | Không khớp | Wildcard không có nghĩa zero label |
| `192.0.2.10` | `IP:192.0.2.10` | Khớp IP-ID | Kiểm tra octet, đúng type |
| `192.0.2.11` | `IP:192.0.2.10` | Không khớp | Không có subnet/range matching |
| `192.0.2.10` | `DNS:192.0.2.10` | Không phải IP-ID theo quy tắc chuẩn | Text giống nhau không đủ |
| `2001:db8::10` | `IP:2001:0db8:0:0:0:0:0:10` | Khớp nếu 16 octet bằng nhau | Text nén/mở rộng không đổi IP |
| `legacy.example.test` | Chỉ `CN=legacy.example.test` | Không đủ theo RFC 9525 | Không fallback CN |

Bảng này nói về **bước so danh tính theo tiêu chuẩn**, không là lời cam kết rằng mọi Java provider/version/lớp ứng dụng sẽ xử lý từng trường hợp hệt nhau. Đối với hệ thống được kiểm soát, hãy test chính xác JDK/provider/TLS stack đang deploy và tuân thủ security policy đã chọn; không vì một client legacy chấp nhận CN mà làm yếu policy.

### 10.1. Reverse proxy, load balancer và service mesh

Ứng dụng có thể kết nối tới load balancer hoặc sidecar, trong khi hostname logic của dịch vụ khác với IP node. Một bộ chứng thư có SAN DNS cho tên **dịch vụ chuẩn** vẫn là cách phù hợp nếu client xác minh đúng tên đó. Đừng tự thay “hostname dùng để xác minh” bằng nội dung header `Host`/`X-Forwarded-Host` được nhận từ nguồn không tin cậy; các header này có thể bị giả mạo ở ranh giới proxy cấu hình sai.

### 10.2. Chứng thư có nhiều SAN

Một chứng thư cho `api.example.test` và `admin.example.test` có thể được client cho hai hostname dùng chung (nếu tất cả điều kiện khác hợp lệ), nhưng gây tăng phạm vi khi private key lộ. Cần phân nhóm dịch vụ/tenant theo rủi ro, certificate rotation, cơ chế quản lý khóa và giới hạn quyền cấp phát SAN.

### 10.3. Khi không có SAN

Java API có thể trả `null`. Hãy xem việc thiếu SAN phù hợp là vấn đề phát hành chứng thư cần sửa theo tiêu chuẩn mới. Không tự chuyển sang chấp nhận mọi hostname, không so CN như cứu cánh, không trust-all để bỏ qua lỗi.

## 11. Lỗi Java/TLS thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `getSubjectAlternativeNames() == null` | Certificate không có SAN extension | Phát hành lại certificate có đúng DNS/IP SAN và trust profile |
| DNS hostname không khớp | Chứng thư chứa SAN của service khác hoặc wildcard không đúng số nhãn | Định nghĩa hostname tham chiếu đúng; sửa certificate/SAN |
| HTTPS truy cập theo IP bị lỗi dù DNS SAN hợp lệ | Thiếu `iPAddress` type 7, client kiểm IP-ID | Cấp IP SAN đúng hoặc dùng hostname tin cậy đúng cách |
| IPv6 string nhìn khác nhau | Text có thể ở dạng nén/mở rộng nhưng cùng octet | Để TLS verifier so IP theo chuẩn; không so chuỗi tùy tiện |
| `CertificateException`/PKIX path building failure | Không tin CA/chain, thiếu intermediate hoặc truststore sai | Cấu hình trust anchor/chain đúng; không tắt trust validation |
| Chứng thư parse được nhưng TLS từ chối | Parse không kiểm trust, hostname hoặc EKU | Xác định loại lỗi: chain, validity, SAN/identity, policy |
| `SSLHandshakeException` có thông tin tên không phù hợp | Endpoint identification từ chối chứng thư | Kiểm tra hostname mong đợi và SAN đúng type |
| Wildcard `*.example.test` không hợp `a.b.example.test` | Wildcard chỉ bao một nhãn | Cấp SAN cụ thể cho hostname cần phục vụ |
| CN trùng hostname nhưng client vẫn từ chối | CN fallback không được dùng theo profile hiện đại | Đưa hostname vào SAN DNS/IP đúng type |
| `X509Certificate.verify(issuerKey)` chạy được nhưng URL sai host | Kiểm signature không so hostname hoặc xác minh trust path đầy đủ | Sử dụng JSSE client endpoint verification + PKIX |
| Tự implement `HostnameVerifier` trả `true` để chữa lỗi | Vô hiệu hóa bảo vệ MITM ở lớp tên | Xóa bypass, sửa cert hoặc client reference identity |
| TLS client raw `SSLSocket` chạy nhưng không kiểm hostname | Endpoint identification chưa được bật/cấu hình | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` theo ngữ cảnh |
| Kết nối bằng IP trong khi chứng thư cho DNS | SNI, peer host và reference identity không khớp | Cấu hình tên logic đã xác thực và cách connect đúng; không tắt check |
| Dùng self-signed fixture trong môi trường thật | Không có chain đến trust anchor theo policy | Dùng PKI/truststore thật; fixture chỉ để đọc SAN |

**Cách debug an toàn:** ghi hostname mong đợi, loại SAN và giá trị công khai, issuer/subject phù hợp, chain path và loại exception; không log private key, credential, session secret hoặc bypass xác thực để vượt lỗi. Phân biệt lỗi **name mismatch** với **untrusted issuer** vì hai lỗi cần sửa ở hai nơi khác nhau.

## 12. Kiểm thử đúng hành vi, không chỉ kiểm thử parser

Một bộ test tốt cho client HTTPS cần bao gồm:

1. Chứng thư được tin cậy theo truststore nhưng có **DNS SAN khớp** → handshake được chấp nhận nếu mọi policy khác hợp lệ.
2. Chain hợp lệ nhưng **DNS SAN khác đích** → từ chối.
3. Chain hợp lệ, chỉ có **CN khớp** nhưng thiếu SAN → từ chối theo policy mới.
4. DNS wildcard `*.svc.example.test` với một nhãn, với zero nhãn và với hai nhãn → các kết quả phù hợp với RFC 9525.
5. Kết nối bằng IP, chứng thư có IP SAN chính xác → chấp nhận theo các điều kiện khác; chỉ có DNS SAN ghi IP text → từ chối.
6. IPv6 nén/mở rộng tương đương → so theo octet, không so text thuần.
7. Chứng thư self-signed không được trust → từ chối dù DNS/IP SAN khớp.
8. Chứng thư hết hạn, revocation/policy failure hoặc KeyUsage/EKU không phù hợp → từ chối.
9. Trường hợp SNI không đúng nhưng certificate được chọn vẫn chứa SAN mong đợi → đánh giá kết quả bằng kiểm tra thực tế chứng thư nhận được; không coi SNI đã thay thế identity check.
10. Đảm bảo raw socket TLS được bật endpoint identification và các HTTP client không có cấu hình "trust-all"/"hostname verifier always true".

**Gợi ý tạo test fixture:** trong môi trường phát triển, có thể dùng `keytool` với `-ext SAN=dns:...,ip:...` để tạo một certificate tự ký cho **unit/integration test** rồi cấp truststore **test-only**. Không đem test CA/root key vào production. Khi cần xác minh failure của PKIX/SAN, test phải chạy trong mạng/test runner cô lập hoặc local server kiểm soát được, không dựa vào hostname tài liệu `.test` có tồn tại trên Internet.

### Checklist trước khi triển khai

- [ ] Mỗi hostname của dịch vụ được liệt kê bằng **dNSName SAN type 2** đúng tên.
- [ ] Nếu khách hàng kết nối bằng IP literal, chứng thư có **iPAddress SAN type 7** chính xác.
- [ ] Không phụ thuộc CN fallback; không bỏ qua hostname verification.
- [ ] Client có reference identity lấy từ endpoint được tin cậy, không từ nguồn bị attacker điều khiển.
- [ ] Có truststore/PKIX chain validation và policy issuer, validity, EKU, key usage, revocation phù hợp.
- [ ] Wildcard giới hạn đúng chuẩn, được kiểm thử ở một và nhiều mức nhãn.
- [ ] IDN/ASCII A-label và xử lý Unicode theo quy tắc giao thức/provider.
- [ ] Có kế hoạch cập nhật SAN khi đổi DNS/service host/IP, triển khai certificate rotation không tạo downtime.
- [ ] Không dùng test certificate/self-signed demo hoặc private key test trong production.
- [ ] Logs phân biệt lỗi trust chain và lỗi tên endpoint mà không để lộ bí mật.

## 13. Câu hỏi tự kiểm tra

1. SAN extension có OID nào, khác Subject CN ở điểm gì?
2. `dNSName` và `iPAddress` thuộc GeneralName type bao nhiêu? Chúng có thể hoán đổi khi giá trị text nhìn giống địa chỉ IP không?
3. Client truy cập `https://api.example.test` nhưng DNS ánh xạ tới `192.0.2.10`: nên so DNS-ID hay IP-ID? Vì sao?
4. Client truy cập `https://192.0.2.10` nhưng chỉ có `DNS:api.example.test`: vì sao chứng thư không tự được chấp nhận theo IP-ID?
5. Nếu chứng thư có `CN=legacy.example.test` và `DNS:api.example.test`, client yêu cầu `legacy.example.test` theo RFC 9525 có được dùng CN làm fallback không?
6. Vì sao `*.svc.example.test` không khớp `a.b.svc.example.test`?
7. `X509Certificate.getSubjectAlternativeNames()` trả kiểu dữ liệu gì và trường hợp nào trả `null`?
8. Vì sao `CertificateFactory` parse thành công chưa có nghĩa chứng thư đáng tin hoặc hostname đã match?
9. `X509Certificate.verify(...)` khác gì với `CertPathValidator` và endpoint identification?
10. Nếu tắt hostname verification nhưng vẫn kiểm CA chain, còn nguy cơ nào?
11. SNI giúp server làm gì? Nó có tự kiểm tra server identity cho client không?
12. Vì sao một chứng thư chứa DNS SAN và IP SAN có thể được dùng cho nhiều cách truy cập nhưng vẫn cần quản lý rủi ro private key?

**Bài tập A:** thay tệp PEM trong demo bằng một certificate thử nghiệm khác có nhiều dNSName và IP SAN. Đọc các type 2/7 và kiểm tra các giá trị theo đúng API. Không tự suy ra trust decision từ kết quả in.

**Bài tập B:** tạo certificate chỉ có CN nhưng không có DNS SAN, và certificate khác có SAN DNS khớp. Viết integration test dùng HTTPS client với truststore test để chứng minh policy endpoint identity được áp dụng.

**Bài tập C:** kiểm tra `https://hostname` và `https://IP` trên local TLS server do bạn kiểm soát với certificate có cả DNS SAN và IP SAN. Quan sát khác biệt giữa name mismatch và untrusted CA.

**Bài tập D:** viết unit test cho wildcard một nhãn/zero nhãn/nhiều nhãn dựa trên TLS hostname verifier thật của provider, không thay bằng `String.endsWith`.

## 14. Tài liệu chính thức

- [Java SE 17 — X509Certificate.getSubjectAlternativeNames](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html#getSubjectAlternativeNames()): cấu trúc `Collection<List<?>>`, SAN type 2/7, biểu diễn giá trị và trường hợp `null`.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `GeneralName` và extension `subjectAltName` (OID 2.5.29.17), certificate chain và name constraints.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): DNS-ID, IP-ID, wildcard một nhãn, IDNA và không fallback CN; cập nhật/obsoletes RFC 6125.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm`, cấu hình kiểm tra endpoint.
- [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): `getSSLParameters`/`setSSLParameters` và handshake.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): parse chứng thư X.509 từ DER/PEM.
- [Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): kiểm tra certificate path theo tham số PKIX, phân biệt với hostname matching.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client HTTP/HTTPS và cấu hình TLS.
