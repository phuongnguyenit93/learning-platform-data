# Nhãn PEM, nhiều khối dữ liệu và đầu vào không hợp lệ

*Tình trạng API được đối chiếu đến ngày 27/11/2026.*

PEM là định dạng văn bản bao bọc dữ liệu nhị phân bằng Base64 và hai dòng nhãn. Dòng mở đầu xác định loại nội dung, ví dụ `-----BEGIN CERTIFICATE-----`; dòng kết thúc dùng nhãn tương ứng. Một file có thể chứa nhiều khối PEM nối tiếp, chẳng hạn chuỗi chứng thư gồm nhiều certificate.

Trong Java 27, API `PEMDecoder`, `PEMEncoder`, `PEM` và `BinaryEncodable` vẫn là **preview lần thứ ba theo JEP 538**. Java 26 cung cấp preview lần thứ hai theo JEP 524. Các ví dụ hiện hành dưới đây dùng tên API Java 27; không trộn chúng với tên và kiểu dữ liệu của preview Java 26.

## 1. Cấu trúc một khối PEM và ý nghĩa của nhãn

Một khối PEM hiện đại theo RFC 7468 có ba phần:

```text
-----BEGIN CERTIFICATE-----
MIIB...Base64 data...
-----END CERTIFICATE-----
```

- **BEGIN boundary:** năm dấu gạch ngang, từ khóa `BEGIN`, một dấu cách, nhãn và năm dấu gạch ngang.
- **Base64 body:** biểu diễn văn bản của dữ liệu nhị phân, thường là cấu trúc DER.
- **END boundary:** có cùng nhãn với dòng BEGIN.

Nhãn chỉ định dạng hoặc loại đối tượng được đóng gói. Một số nhãn thường gặp:

| Nhãn | Nội dung thường biểu diễn | Kiểu Java có thể nhận |
|---|---|---|
| `CERTIFICATE` | Chứng thư X.509 | `X509Certificate` |
| `X509 CRL` | Danh sách chứng thư bị thu hồi | `X509CRL` |
| `PUBLIC KEY` | Khóa công khai theo SubjectPublicKeyInfo | `PublicKey` |
| `PRIVATE KEY` | Khóa riêng theo PKCS #8 | `PrivateKey` hoặc `KeyPair` nếu có cả khóa công khai |
| `ENCRYPTED PRIVATE KEY` | Khóa riêng PKCS #8 đã mã hóa | `EncryptedPrivateKeyInfo`, hoặc khóa đã giải mã khi cấu hình decoder |
| Nhãn khác | Định dạng PEM chưa có kiểu Java tương ứng | `PEM` để giữ nhãn và Base64 content |

Không suy ra rằng mọi nhãn chứa từ `KEY` đều có cùng cấu trúc. `PRIVATE KEY`, `ENCRYPTED PRIVATE KEY`, `RSA PRIVATE KEY` và `OPENSSH PRIVATE KEY` có thể biểu diễn các cấu trúc nhị phân khác nhau. API chỉ chuyển thành kiểu mật mã Java khi nhãn và nội dung thuộc dạng mà decoder/provider hỗ trợ.

Nhãn không phải bằng chứng xác thực nội dung. Dòng `BEGIN CERTIFICATE` không chứng minh dữ liệu bên trong là chứng thư hợp lệ hoặc được một CA tin cậy ký. Decoder vẫn phải phân tích Base64 và cấu trúc nhị phân; ứng dụng còn phải xác minh mục đích sử dụng, thời hạn, chuỗi tin cậy và chính sách chứng thư.

## 2. Quy tắc viết nhãn và boundary

RFC 7468 quy định các nguyên tắc định dạng quan trọng:

- Nhãn có phân biệt chữ hoa/chữ thường; các nhãn chuẩn được viết hoa, ví dụ `CERTIFICATE`.
- Từ khóa `BEGIN` hoặc `END` cách nhãn bằng đúng một dấu cách.
- Boundary dùng đúng năm dấu gạch ngang ở mỗi bên.
- Nhãn ở dòng END phải giống nhãn ở dòng BEGIN.
- Nhãn không có dấu cách hoặc dấu gạch ngang ở đầu/cuối, không có hai dấu cách hoặc hai dấu gạch ngang liên tiếp.
- Base64 body được ngăn dòng; trình tạo mới nên ghi mỗi dòng tối đa 64 ký tự theo định dạng chuẩn.
- Trình phân tích cần xử lý các kiểu xuống dòng CRLF, CR và LF.

Ví dụ một cặp boundary đúng:

```text
-----BEGIN CERTIFICATE-----
<Base64 certificate>
-----END CERTIFICATE-----
```

Các ví dụ sai về cấu trúc:

```text
----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
```

```text
-----BEGIN CERTIFICATE-----
...
-----END PUBLIC KEY-----
```

Ví dụ thứ nhất thiếu một dấu gạch ngang ở boundary mở đầu. Ví dụ thứ hai dùng nhãn kết thúc khác nhãn mở đầu. Không nên dựa vào việc một parser cụ thể có thể chấp nhận một dạng sai; hãy sinh đúng RFC 7468 và coi dữ liệu sai định dạng là lỗi cần xử lý.

RFC 7468 cho phép dữ liệu văn bản xuất hiện trước một khối PEM. Với decoder Java, muốn lấy phần dữ liệu đi trước này, hãy yêu cầu kiểu `PEM.class`; khi yêu cầu một kiểu mật mã cụ thể, phần leading data có thể bị bỏ qua. Không dùng leading data như một trường đã được xác thực hoặc một phần của chứng thư/khóa.

## 3. Java 27 nhận diện nhãn và chọn kiểu kết quả

`PEMDecoder.decode(String)` và `decode(InputStream)` trả về đối tượng `BinaryEncodable` phù hợp với nhãn và dữ liệu. Những trường hợp phổ biến được ánh xạ như sau:

| PEM label | Kết quả từ decoder mặc định |
|---|---|
| `CERTIFICATE` | `X509Certificate` |
| `X509 CRL` | `X509CRL` |
| `PUBLIC KEY` | `PublicKey` |
| `PRIVATE KEY` | `PrivateKey` hoặc `KeyPair` nếu encoding có cả khóa công khai |
| `ENCRYPTED PRIVATE KEY` | `EncryptedPrivateKeyInfo` nếu chưa cấu hình giải mã |
| Loại không có class tương ứng | `PEM` |

Khi biết trước kiểu dữ liệu mong muốn, dùng overload có tham số `Class` để tránh ép kiểu thủ công:

```java
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

public class DecodeCertificate {
    static X509Certificate decodeCertificate(String pemText) {
        return PEMDecoder.of().decode(pemText, X509Certificate.class);
    }
}
```

Nếu PEM không tương ứng với kiểu yêu cầu, API ném `ClassCastException`. Nếu đầu vào không có PEM hoặc cú pháp/nội dung không giải mã được, `IllegalArgumentException` có thể được ném. Không bắt `RuntimeException` chung rồi coi dữ liệu là hợp lệ; hãy phân biệt sai kiểu, sai định dạng và lỗi mật mã.

### Giữ nhãn chưa được hỗ trợ bằng PEM

Nếu decoder không có kiểu Java tương ứng cho một nhãn, nó trả về `PEM` để ứng dụng vẫn có thể xem nhãn và nội dung Base64. Có thể yêu cầu rõ `PEM.class`:

```java
import java.security.PEM;
import java.security.PEMDecoder;

public class ReadUnknownPem {
    static void inspect(String pemText) {
        PEM raw = PEMDecoder.of().decode(pemText, PEM.class);

        System.out.println("Label: " + raw.type());
        System.out.println("Base64 bytes: " + raw.content().length);

        byte[] binaryContent = raw.decode();
        System.out.println("Decoded bytes: " + binaryContent.length);
    }
}
```

Trong Java 27, `PEM.type()` trả về nhãn, `content()` trả về mảng byte chứa Base64 text, còn `decode()` giải mã Base64 thành byte nhị phân. `PEM.class` hữu ích khi cần lưu trữ hoặc chuyển tiếp một nhãn chưa có kiểu Java, nhưng không tự biến dữ liệu đó thành khóa hay chứng thư đã được kiểm tra.

Lưu ý: `PEM.content()` là Base64 content, không phải dữ liệu DER sau giải mã. Nếu cần dữ liệu nhị phân, gọi `decode()`. Nếu tạo một `PEM` bằng constructor, đối số content cũng phải là Base64 đã mã hóa; constructor không tự Base64-encode byte nhị phân đầu vào.

Với nhãn chưa được ánh xạ, decoder có thể trả về `PEM` và giữ Base64 text mà chưa giải mã payload. Khi đó lỗi Base64 chỉ xuất hiện lúc gọi `raw.decode()`. `PEM.decode()` dùng MIME Base64 decoder; MIME decoder bỏ qua các ký tự không thuộc bảng Base64. Nếu chính sách ứng dụng yêu cầu Base64 chuẩn nghiêm ngặt, hãy kiểm tra body theo chính sách đó trước khi sử dụng payload, thay vì dựa vào khả năng chấp nhận ký tự dư của MIME decoder.

## 4. Một file có thể chứa nhiều khối PEM

RFC 7468 cho phép nhiều textual encoding instance trong cùng file. Trường hợp phổ biến là certificate bundle:

```text
-----BEGIN CERTIFICATE-----
<Base64 root/intermediate certificate>
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
<Base64 leaf certificate>
-----END CERTIFICATE-----
```

Mỗi khối vẫn có cặp boundary và nhãn riêng. Việc nối hai khối không biến chúng thành một đối tượng PEM duy nhất; mỗi khối là một đơn vị được giải mã riêng. Thứ tự certificate có ý nghĩa tùy giao thức và quy trình xác minh chuỗi.

`PEMDecoder.decode(String)` trả về một đối tượng cho lần gọi đó; phương thức không trả về danh sách mọi khối trong chuỗi. Với `InputStream`, decoder đọc đến footer của một khối PEM hoặc đến cuối stream. Khi cần đọc nhiều khối nối tiếp, gọi decoder nhiều lần trên cùng stream sau mỗi lần giải mã thành công.

Ví dụ khi ứng dụng biết trước số certificate cần đọc:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.List;

public class ReadCertificateBundle {
    static List<X509Certificate> readBundle(
            Path path, int expectedCertificates) throws IOException {

        PEMDecoder decoder = PEMDecoder.of();
        List<X509Certificate> certificates = new ArrayList<>();

        try (InputStream input = Files.newInputStream(path)) {
            for (int i = 0; i < expectedCertificates; i++) {
                X509Certificate certificate =
                        decoder.decode(input, X509Certificate.class);
                certificates.add(certificate);
            }

            // Sau số khối dự kiến, chỉ cho phép khoảng trắng ở cuối file.
            int next;
            while ((next = input.read()) != -1) {
                if (!Character.isWhitespace((char) (next & 0xff))) {
                    throw new IOException(
                            "Unexpected data after certificate bundle");
                }
            }
        }

        return List.copyOf(certificates);
    }
}
```

Ví dụ này giả định ứng dụng đã biết số certificate dự kiến từ cấu hình hoặc metadata đáng tin cậy. Nếu stream kết thúc trước khi đọc đủ số khối, decoder báo lỗi thay vì trả về bundle thiếu. Sau khối cuối, code kiểm tra phần còn lại chỉ là whitespace.

Không viết vòng lặp vô hạn rồi bắt mọi `EOFException` và coi đó là kết thúc bình thường. API Java 27 dùng `EOFException` khi không tìm thấy PEM trong stream **hoặc** stream kết thúc bất ngờ khi một khối chưa hoàn chỉnh. Nếu nuốt ngoại lệ mà không kiểm tra số khối hoặc trạng thái framing, một file bị cắt giữa chừng có thể bị hiểu nhầm thành bundle hợp lệ.

Nếu số khối không biết trước, cần có framing/manifest hoặc bước kiểm tra boundary của ứng dụng để xác định rõ đâu là khối hoàn chỉnh và đâu là EOF bất thường. Đừng tự viết một Base64/ASN.1 parser khác chỉ để tách chuỗi; để `PEMDecoder` giải mã từng khối sau khi ranh giới đã được xác định.

## 5. Dữ liệu đứng trước khối PEM và trường leadingData

Một số file có dòng mô tả hoặc metadata trước PEM:

```text
Certificate for api.example.test
-----BEGIN CERTIFICATE-----
<Base64 certificate>
-----END CERTIFICATE-----
```

Khi yêu cầu kiểu mật mã cụ thể, decoder bỏ qua leading data. Khi yêu cầu `PEM.class`, phần leading data có thể được truy cập qua `leadingData()`:

```java
PEM pem = PEMDecoder.of().decode(text, PEM.class);

byte[] metadata = pem.leadingData();
String label = pem.type();
byte[] encodedContent = pem.content();
```

Trong Java 27, constructor và accessor của `PEM` sao chép các mảng byte để tránh thay đổi dữ liệu bên trong object qua mảng đầu vào/đầu ra. Tuy nhiên, `PEMEncoder` chỉ ghi nhãn và Base64 content; `leadingData()` không được đưa vào chuỗi PEM được encode lại. Nếu ứng dụng cần giữ metadata đi trước, phải lưu và xử lý trường đó riêng.

Không nhầm leading data với header thuộc định dạng PEM cũ. RFC 7468 không định nghĩa các header tùy biến nằm giữa BEGIN boundary và Base64 body như một phần của textual encoding hiện đại. Khi tích hợp file do công cụ cũ sinh ra, hãy xác định rõ định dạng mà công cụ thực sự xuất ra và kiểm tra khả năng tương thích; không giả định mọi dạng “trông giống PEM” đều là RFC 7468.

## 6. Đầu vào không hợp lệ và ngoại lệ cần phân biệt

Decoder có thể gặp lỗi ở nhiều tầng. Cách xử lý phù hợp phụ thuộc overload và loại lỗi:

| Tình huống | API Java 27 | Hành vi cần xử lý |
|---|---|---|
| Không tìm thấy khối PEM trong String | `decode(String)` | `IllegalArgumentException` |
| Boundary hoặc dữ liệu không giải mã được thành kiểu mật mã đã biết | `decode(String)` | `IllegalArgumentException` |
| Nhãn không được hỗ trợ | `decode(String)` | Trả về `PEM`; Base64 được giải mã khi gọi `PEM.decode()` |
| Không tìm thấy khối PEM trong InputStream | `decode(InputStream)` | `EOFException` |
| Stream kết thúc bất ngờ trước footer | `decode(InputStream)` | `EOFException` hoặc `IOException` theo lỗi đọc/cú pháp |
| Lỗi I/O khi đọc stream | `decode(InputStream)` | `IOException`; vị trí stream có thể không còn nhất quán |
| Nhãn/nội dung không phù hợp class được yêu cầu | `decode(input, Class)` | `ClassCastException` |
| Lỗi khi giải mã khóa riêng được mã hóa | Decoder có `withDecryption()` | `CryptoException` |
| Gọi `PEM.decode()` với Base64 content không hợp lệ | `PEM.decode()` | `IllegalArgumentException` |

Một số quy tắc thực tế:

- **Không có PEM:** xác nhận file không rỗng, đúng encoding và có boundary mở đầu. Với stream, phân biệt EOF sạch với khối bị cắt cụt bằng số khối dự kiến hoặc framing.
- **Thiếu footer:** không tự ghép footer hoặc cắt bỏ phần dư để ép parser chấp nhận. Yêu cầu nguồn cung cấp lại file.
- **Sai nhãn:** kiểm tra nhãn BEGIN/END có giống nhau, viết đúng chính tả và đúng chữ hoa/chữ thường theo định dạng chuẩn.
- **Base64 lỗi:** kiểm tra body có bị cắt, padding sai hoặc ký tự ngoài chính sách cho phép. Với nhãn không được hỗ trợ, kiểm tra thêm kết quả `PEM.decode()`; đừng nhầm việc decoder giữ được raw PEM với việc Base64 đã hợp lệ.
- **Sai kiểu đích:** dùng `decode(input)` để xem decoder ánh xạ sang kiểu nào, hoặc xác minh nhãn/nguồn trước khi yêu cầu class cụ thể. Không bắt `ClassCastException` rồi cast sang kiểu khác bằng suy đoán.
- **Khóa mã hóa:** nếu chưa cấu hình giải mã, `ENCRYPTED PRIVATE KEY` có thể được trả về dưới dạng `EncryptedPrivateKeyInfo`. Chỉ cấu hình `withDecryption(password)` khi ứng dụng được phép giải mã và có nguồn mật khẩu phù hợp.
- **Lỗi giải mã khóa:** không ghi mật khẩu, private key hoặc toàn bộ PEM vào log. Trả lỗi có mã tham chiếu và thông tin không nhạy cảm.

API `PEM` cũng không kiểm tra đầy đủ tính hợp lệ khi tạo object bằng constructor. Tài liệu Java 27 ghi rõ constructor kiểm tra tham số null và cú pháp boundary trong type, nhưng không xác minh type có tuân RFC 7468, Base64 có hợp lệ hay content có đúng loại dữ liệu được nhãn khai báo. Việc tạo được một `PEM` object không có nghĩa nội dung đã hợp lệ.

## 7. Kiểm tra nghiêm ngặt trước khi tin dữ liệu

PEM thường mang khóa, chứng thư hoặc CRL. Một decoder thành công chỉ xác nhận dữ liệu được phân tích theo một kiểu mà API hỗ trợ. Nó không thay thế quy trình xác minh bảo mật.

Khi nhận PEM từ file upload, secret store, thiết bị hoặc dịch vụ bên ngoài:

1. Giới hạn kích thước đầu vào và số khối để tránh tiêu thụ bộ nhớ/CPU quá mức.
2. Chấp nhận đúng loại nhãn mà use case cho phép; từ chối nhãn không nằm trong allow-list nếu ứng dụng không cần chuyển tiếp dữ liệu không rõ loại.
3. Dùng overload có class đích khi biết rõ muốn certificate, public key hoặc private key.
4. Xác minh certificate chain, thời hạn, issuer, key usage, extended key usage, hostname và trust anchor theo ngữ cảnh.
5. Kiểm tra thuật toán, kích thước khóa và chính sách mật mã của hệ thống.
6. Không coi việc giải mã thành công là bằng chứng private key thuộc về một danh tính cụ thể.
7. Giữ private key trong secret store hoặc cơ chế quản lý khóa phù hợp; không đưa nội dung khóa vào log, exception message hoặc source control.

Đối với certificate bundle, thứ tự các certificate trong file không tự chứng minh chuỗi tin cậy. Ứng dụng cần dựng và xác minh certification path bằng chính sách PKIX phù hợp, thay vì tin vào thứ tự các khối PEM.

## 8. Khác biệt API Java 26 và Java 27 cần cập nhật

PEM API vẫn là preview ở Java 26 và Java 27. Java 27 thay đổi tên kiểu và một số kiểu dữ liệu; code Java 26 không thể sao chép nguyên trạng sang JDK 27.

| Nội dung | Java 26 – JEP 524, Preview 2 | Java 27 – JEP 538, Preview 3 |
|---|---|---|
| Interface biểu diễn đối tượng có binary encoding | `DEREncodable` | `BinaryEncodable` |
| `PEM` | Record | Class thông thường |
| `PEM.content()` | `String` Base64 | `byte[]` Base64 |
| Constructor `PEM` | Nhận type và String content | Có overload String/byte[] content |
| Defensive copy | `leadingData` trong record có thể bị thay đổi qua mảng tham chiếu | Các mảng được sao chép khi tạo và khi trả về |
| Chọn provider cho decoder | `withFactory(provider)` | `withFactoriesOf(provider)` |
| Lỗi xử lý mật mã | Một số lỗi được báo qua `IllegalArgumentException` | Có `CryptoException` preview cho lỗi mật mã |

Khi nâng cấp:

- Thay `DEREncodable` bằng `BinaryEncodable`.
- Thay `withFactory(provider)` bằng `withFactoriesOf(provider)`.
- Nếu đọc `PEM.content()`, cập nhật code từ `String` sang `byte[]`; không dùng trực tiếp như văn bản.
- Nếu tạo `PEM` bằng constructor byte array, truyền Base64 bytes đã mã hóa, không truyền DER thô.
- Cập nhật xử lý ngoại lệ cho `CryptoException` và kiểm tra lại code giải mã khóa.
- Biên dịch lại bằng đúng JDK mục tiêu và chạy test với preview được bật.

Không dùng ví dụ Java 25 hoặc Java 26 dựa trên tên `PEMRecord`, `DEREncodable`, `withFactory()` hoặc accessor `content()` trả String khi viết code Java 27. Những tên và kiểu đó thuộc preview cũ.

## 9. Ví dụ Java 27: giải mã certificate và giữ nhãn lạ

Ví dụ sau cho thấy cách xử lý hai trường hợp: certificate có kiểu Java chuẩn và nhãn không có kiểu tương ứng:

```java
import java.security.BinaryEncodable;
import java.security.PEM;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

public class PemLabelHandling {
    static void inspect(String pemText) {
        BinaryEncodable value = PEMDecoder.of().decode(pemText);

        if (value instanceof X509Certificate certificate) {
            System.out.println("Certificate subject: "
                    + certificate.getSubjectX500Principal());
        } else if (value instanceof PEM raw) {
            System.out.println("Unmapped PEM label: " + raw.type());
            byte[] binary = raw.decode();
            System.out.println("Decoded payload bytes: " + binary.length);
        } else {
            System.out.println("Decoded type: " + value.getClass().getName());
        }
    }

    static X509Certificate requireCertificate(String pemText) {
        return PEMDecoder.of().decode(pemText, X509Certificate.class);
    }
}
```

Trong code ứng dụng, nhánh `PEM` chỉ nên được giữ hoặc chuyển tiếp nếu nghiệp vụ cho phép loại nhãn đó. Nếu yêu cầu bắt buộc là certificate, dùng `requireCertificate()` và xử lý lỗi khi dữ liệu không phải certificate.

## 10. Biên dịch và chạy đúng JDK

PEM API thuộc module chuẩn `java.base`, nhưng vẫn là preview. Không cần thêm module incubator; phải bật preview ở cả compiler và runtime.

Với JDK 27:

```bash
javac --enable-preview --release 27 -d out PemLabelHandling.java
java --enable-preview -cp out PemLabelHandling
```

Với JDK 26, phải dùng API preview lần thứ hai và biên dịch/chạy bằng chính JDK 26:

```bash
javac --enable-preview --release 26 -d out26 Pem26Example.java
java --enable-preview -cp out26 Pem26Example
```

Hai bộ ví dụ không thể dùng chung nếu chúng tham chiếu đến các tên API đã thay đổi. Class file được biên dịch với preview của JDK 26 không phải class file preview hợp lệ để chạy trên JDK 27, và ngược lại. Trước khi điều tra lỗi, kiểm tra:

```bash
javac -version
java -version
```

## 11. Checklist khi xử lý file PEM

- [ ] Đọc giới hạn kích thước và nguồn file trước khi giải mã.
- [ ] Xác định file có một khối hay nhiều khối PEM.
- [ ] Kiểm tra cặp BEGIN/END, nhãn và boundary đúng định dạng.
- [ ] Chọn kiểu đích rõ ràng nếu nghiệp vụ yêu cầu certificate, public key hoặc private key.
- [ ] Chỉ giữ `PEM` thô cho nhãn chưa có kiểu Java khi ứng dụng cho phép.
- [ ] Phân biệt EOF bình thường với stream bị cắt giữa một khối.
- [ ] Xử lý `IllegalArgumentException`, `IOException`, `EOFException`, `ClassCastException` và `CryptoException` theo đúng nguyên nhân.
- [ ] Giải mã private key chỉ khi có quyền và có mật khẩu an toàn.
- [ ] Xác minh trust chain và chính sách khóa sau khi decode certificate/key.
- [ ] Không ghi nội dung private key hoặc password vào log.
- [ ] Ghi rõ JDK 26 Preview 2 hay JDK 27 Preview 3 trong tài liệu và build.

## Tài liệu tham chiếu

1. [JEP 524 – PEM Encodings of Cryptographic Objects (Second Preview, Java 26)](https://openjdk.org/jeps/524)
2. [JEP 538 – PEM Encodings of Cryptographic Objects (Third Preview, Java 27)](https://openjdk.org/jeps/538)
3. [Oracle Java SE 27 API – PEMDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html)
4. [Oracle Java SE 27 API – PEM](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html)
5. [Oracle Java SE 27 API – PEMEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html)
6. [Oracle Java SE 27 API – BinaryEncodable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html)
7. [Oracle Java SE 26 API – PEMDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html)
8. [Oracle Java SE 26 API – PEM](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEM.html)
9. [Oracle – JDK 27 Security Enhancements](https://inside.java/2026/09/16/jdk27-security-enhancements/)
10. [RFC 7468 – Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html)

