# Ngăn tệp người dùng tùy ý trở thành attachment

Một chức năng gửi email có thể cho phép người dùng tải lên tài liệu rồi yêu cầu ứng dụng gửi tài liệu đó cho người khác: hóa đơn, hồ sơ hỗ trợ, báo cáo hoặc giấy tờ xác nhận. Trong **Spring Framework Mail**, việc gắn file vào email khá đơn giản với `MimeMessageHelper.addAttachment(...)`. Nhưng API này chỉ đóng gói dữ liệu thành MIME part; nó **không xác minh tệp có an toàn, đúng loại, thuộc về người dùng hay được phép gửi tới người nhận hay không**.

Nếu ứng dụng lấy trực tiếp tệp upload, tên file, content type hoặc đường dẫn do client cung cấp rồi đưa vào email, chức năng đính kèm có thể trở thành đường chuyển phát mã độc, dữ liệu nhạy cảm, nội dung giả mạo hoặc tệp vượt giới hạn. Vì email có thể được chuyển tiếp và lưu ở nhiều mailbox, sai sót ở bước này khó thu hồi hơn một file chỉ được giữ trong ứng dụng.

Nguyên tắc cốt lõi là **không biến upload thành attachment ngay lập tức**. Hãy đưa tệp qua quy trình kiểm tra và phê duyệt rõ ràng, chỉ đính kèm bản dữ liệu đã được xác nhận phù hợp với mục đích nghiệp vụ và quyền của người nhận.

## 1. Ranh giới tin cậy từ upload đến email

Một request upload có thể chứa nhiều thông tin do client kiểm soát:
- Byte của file.
- Tên gốc do trình duyệt gửi lên.
- Phần mở rộng như `.pdf`, `.csv` hoặc `.docx`.
- Header `Content-Type` của multipart request.
- Kích thước được khai báo hoặc kích thước thực.
- Các tham số như loại tài liệu, người nhận, mã đơn hàng hoặc ID hồ sơ.
- URL hoặc đường dẫn nếu ứng dụng cho phép chọn tài liệu từ nơi khác.

Những dữ liệu đó **không tự trở thành đáng tin cậy chỉ vì được nhận qua Spring MVC hoặc lưu trong database**. Client có thể gửi header giả, đổi tên file, sửa tham số, phát lại request hoặc chọn ID tài liệu thuộc người dùng khác.

Một luồng an toàn nên có các bước:

```text
Người dùng upload
       |
       v
Giới hạn request và xác thực người dùng
       |
       v
Lưu vào vùng quarantine / staging
       |
       v
Kiểm tra policy theo nghiệp vụ
       |
       +--> kích thước, loại file, signature, cấu trúc
       |
       +--> malware scan / CDR nếu cần
       |
       +--> quyền sở hữu, tenant, phân loại dữ liệu
       |
       v
Đánh dấu APPROVED hoặc REJECTED
       |
       v
Kiểm tra quyền gửi tới recipient
       |
       v
Tạo MimeMessage và addAttachment
       |
       v
JavaMailSender.send(...)
```

Không phải ứng dụng nào cũng cần một hệ thống quarantine phức tạp. Với endpoint chỉ nhận PDF hóa đơn nhỏ, quy trình có thể gọn hơn. Tuy nhiên, **các quyết định về loại tệp, quyền truy cập và kiểm tra an toàn vẫn phải xảy ra trước khi gọi `addAttachment`**.

### 1.1. Phân biệt các trạng thái tệp

Không nên chỉ lưu một cột `uploaded=true` rồi xem mọi file đã tải lên là có thể gửi đi.

| Trạng thái | Ý nghĩa | Có được đính kèm không? |
|---|---|---|
| `RECEIVED` | Server đã nhận dữ liệu upload. | Chưa. |
| `QUARANTINED` | Tệp đang chờ kiểm tra. | Không. |
| `VALIDATING` | Đang kiểm tra định dạng, cấu trúc, kích thước hoặc quyền. | Không. |
| `SCANNING` | Đang quét malware hoặc xử lý CDR. | Không. |
| `APPROVED` | Đã qua các policy bắt buộc cho mục đích cụ thể. | Có, nếu người gửi và người nhận cũng được phép. |
| `REJECTED` | Tệp vi phạm policy hoặc không xác minh được. | Không. |
| `EXPIRED` / `REVOKED` | Tệp hết hạn hoặc bị thu hồi. | Không. |

`APPROVED` nên gắn với **mục đích sử dụng và phiên bản nội dung cụ thể**. Một file được duyệt làm ảnh đại diện không mặc nhiên được duyệt làm attachment tài chính; một file đã thay đổi sau khi scan phải được kiểm tra lại.

## 2. Những giả định nguy hiểm cần tránh

### 2.1. Không tin tên file gốc

Tên file do client cung cấp có thể là:

```text
../../application.yml
invoice.pdf
invoice.pdf.exe
report.pdf%0d%0aBcc:attacker@example.net
C:\Users\Public\secret.txt
.hidden
very-long-name-....pdf
```

Tên này có thể chứa đường dẫn, ký tự điều khiển, dấu phân cách khác hệ điều hành hoặc phần mở rộng gây hiểu nhầm. Không dùng trực tiếp tên đó làm đường dẫn lưu trữ hoặc filename của email.

Nên:
- Tạo storage key/ID do server sinh.
- Sinh tên attachment theo nghiệp vụ, ví dụ `invoice-2026-001.pdf`.
- Nếu cần giữ tên gốc để hiển thị, lưu riêng như metadata đã chuẩn hóa.
- Loại bỏ CR/LF và ký tự điều khiển khỏi tên hiển thị.
- Không để tên file quyết định quyền truy cập hoặc đường dẫn filesystem.

### 2.2. Không tin Content-Type do browser gửi

Client có thể gửi `Content-Type: application/pdf` cho bất kỳ byte nào. Giá trị `MultipartFile.getContentType()` phản ánh metadata request, không phải bằng chứng dữ liệu thật là PDF.

Một file thực thi có thể được đổi tên thành `report.pdf` và gửi kèm header `application/pdf`. Nếu server chỉ kiểm tra hai giá trị này, nó có thể chấp nhận file sai định dạng.

Hãy kết hợp:
- allowlist loại tài liệu theo nghiệp vụ;
- kiểm tra phần mở rộng như một tín hiệu phụ;
- nhận diện định dạng từ byte/signature;
- parser phù hợp để xác nhận cấu trúc;
- malware scan hoặc content disarm/reconstruction khi rủi ro yêu cầu.

Không có một phép kiểm tra đơn lẻ nào chứng minh file hoàn toàn an toàn.

### 2.3. Không tin kích thước do client khai báo

Dùng kích thước thực tế server nhận được, đồng thời đặt giới hạn ở nhiều lớp:
- reverse proxy/API gateway;
- servlet multipart configuration;
- giới hạn theo endpoint;
- giới hạn theo từng tệp và tổng request;
- giới hạn khi tạo MIME message;
- giới hạn của SMTP provider.

`MultipartFile.getSize()` hữu ích sau khi request đã được tiếp nhận, nhưng giới hạn proxy/container phải chặn payload quá lớn **trước khi ứng dụng tiêu tốn quá nhiều RAM hoặc disk**.

### 2.4. Không tin ID file do client gửi

Nếu request yêu cầu gửi `fileId=123`, server phải kiểm tra file đó:
- tồn tại;
- thuộc đúng user/tenant hoặc được chia sẻ hợp lệ;
- đang ở trạng thái `APPROVED`;
- chưa hết hạn hoặc bị thu hồi;
- được phép gửi cho recipient và theo mục đích hiện tại.

Một ID ngẫu nhiên khó đoán không thay thế authorization. Cần kiểm tra quyền trên từng đối tượng (object-level authorization).

## 3. Xây dựng allowlist theo mục đích nghiệp vụ

Không nên đặt policy chung kiểu “mọi loại file trừ .exe đều được phép”. Thay vào đó, xác định **email cụ thể cần loại tài liệu nào**.

| Luồng email | Loại file được chấp nhận | Các loại nên từ chối mặc định |
|---|---|---|
| Gửi hóa đơn | PDF được tạo hoặc xác minh bởi hệ thống | Executable, script, HTML, archive không cần thiết. |
| Báo cáo dữ liệu | CSV hoặc XLSX theo policy | Macro-enabled office file nếu không có nhu cầu rõ ràng, script, archive. |
| Ảnh hỗ trợ | JPEG/PNG đã được kiểm tra hoặc re-encode | SVG/HTML nếu không có sanitizer phù hợp, executable, file không rõ loại. |
| Hồ sơ người dùng | Chỉ loại được nghiệp vụ quy định và đã scan | Các loại ngoài danh sách, file mã hóa không thể scan nếu policy không cho phép. |

Allowlist nên được thể hiện bằng enum hoặc cấu hình phía server, không nhận nguyên một chuỗi MIME tùy ý từ request.

Ví dụ, endpoint gửi biên nhận có thể **chỉ nhận PDF**. Người dùng không được đổi tham số thành `application/zip` để gửi archive qua cùng endpoint.

### 3.1. Từ chối loại không cần thiết

Các loại sau thường cần chính sách chặt chẽ hoặc nên bị từ chối nếu nghiệp vụ không cần:
- chương trình thực thi, thư viện nhị phân và installer;
- script và file có thể thực thi;
- HTML có thể chứa nội dung chủ động;
- SVG có thể chứa markup/active content tùy cách xử lý;
- tài liệu Office có macro;
- archive lồng nhau hoặc archive được mã hóa;
- file không nhận diện được hoặc parser không thể xác minh.

Không dùng phần mở rộng đơn lẻ làm quyết định. Ví dụ `.docx` là một gói ZIP theo định dạng Office Open XML; kiểm tra magic bytes đơn giản chỉ thấy ZIP không đủ để chứng minh đây là tài liệu Word hợp lệ.

## 4. Kiểm tra định dạng: nhiều lớp thay vì một phép thử

Một pipeline kiểm tra file có thể kết hợp:

1. **Allowlist nghiệp vụ:** endpoint có chấp nhận loại file này không?
2. **Tên và phần mở rộng:** có phù hợp với loại được yêu cầu không? Đây chỉ là kiểm tra phụ.
3. **Content-Type detection:** nhận diện định dạng từ byte, chẳng hạn dùng Apache Tika.
4. **Signature/magic bytes:** kiểm tra dấu hiệu định dạng dự kiến.
5. **Parser/validator chuyên biệt:** xác nhận cấu trúc file có thể đọc và không sai định dạng cơ bản.
6. **Malware scanning:** quét bằng dịch vụ hoặc engine được quản lý.
7. **CDR/re-encoding:** với loại file phù hợp, tái tạo nội dung an toàn từ dữ liệu đã parse.
8. **Policy dữ liệu:** kiểm tra file có chứa thông tin được phép gửi qua email không.

Ví dụ với PDF:
- Tệp có thể bắt đầu bằng signature `%PDF-`, nhưng chỉ kiểm tra prefix không chứng minh PDF hoàn chỉnh.
- Dùng parser PDF để mở và kiểm tra cấu trúc.
- Giới hạn số trang, kích thước, object hoặc tính năng theo nhu cầu.
- Quét malware; nếu có khả năng xử lý, dùng CDR để tạo bản PDF sạch theo policy.
- Đính kèm chính **byte của phiên bản đã duyệt**, không quay lại file upload ban đầu.

### 4.1. Dùng Apache Tika để nhận diện loại nội dung

Apache Tika có thể nhận diện media type dựa trên dữ liệu và các quy tắc detection. Ví dụ:

```java
import org.apache.tika.Tika;

Tika tika = new Tika();
String detectedType = tika.detect(fileBytes);
```

Giá trị detection là một tín hiệu hữu ích, không phải phán quyết rằng file an toàn. File polyglot, cấu trúc lỗi, nội dung độc hại hoặc file được tạo để đánh lừa detector vẫn cần policy và kiểm tra chuyên biệt.

Không dùng duy nhất:

```java
if ("application/pdf".equals(upload.getContentType())) {
    // Cho phép gửi
}
```

vì header của client có thể bị giả mạo.

### 4.2. Parser phải chạy với giới hạn tài nguyên

Parser tài liệu cũng có thể bị khai thác bằng file được chế tạo đặc biệt hoặc gây tốn CPU/RAM. Khi xử lý file không tin cậy:
- đặt timeout và giới hạn bộ nhớ;
- dùng phiên bản thư viện được cập nhật;
- dùng process/container có quyền thấp nếu mức rủi ro cao;
- giới hạn kích thước, số trang, số entry và độ sâu lồng;
- không cho parser truy cập mạng hoặc filesystem tùy ý;
- coi parser exception là lỗi xác minh, không tự động chấp nhận file.

## 5. Quét malware và vùng quarantine

Với tài liệu do người dùng upload, có thể cần tích hợp antivirus hoặc dịch vụ scan. Luồng ví dụ:

```text
Upload bytes
    |
    v
Quarantine storage
    |
    v
Type / structure validation
    |
    v
Malware scanner
    |
    +--> CLEAN ----> APPROVED
    |
    +--> INFECTED -> REJECTED
    |
    +--> ERROR ----> QUARANTINED / RETRY / MANUAL REVIEW
```

Không được xem lỗi kết nối scanner là kết quả “clean”. Khi scanner không khả dụng, policy nên **fail closed** cho các loại tài liệu yêu cầu scan: giữ file ở quarantine, retry hoặc báo người dùng thử lại sau.

Một interface có thể tách ứng dụng khỏi nhà cung cấp scan:

```java
public interface MalwareScanner {
    ScanResult scan(byte[] content);
}

public enum ScanResult {
    CLEAN,
    INFECTED,
    UNAVAILABLE
}
```

Đây là abstraction minh họa; implementation thực tế có thể gọi ClamAV, dịch vụ bảo mật hoặc scan gateway nội bộ. Không đặt code giả luôn trả `CLEAN` trong production.

Nếu hệ thống có chức năng **Content Disarm and Reconstruction (CDR)**, có thể tái tạo tài liệu từ nội dung được phép, loại bỏ thành phần active không cần thiết và đưa bản đã tái tạo qua kiểm tra tiếp theo. CDR không phù hợp với mọi loại file và cần đánh giá tác động đến nội dung/định dạng.

### 5.1. Quét đúng phiên bản sẽ gửi

Một lỗi thiết kế là:
1. Quét file upload A.
2. File ở storage bị thay bằng B.
3. Email gửi B vì worker chỉ dùng lại file ID.

Đây là dạng TOCTOU (time-of-check to time-of-use). Cách giảm rủi ro:
- tạo object/version bất biến sau upload;
- lưu checksum/hash của byte đã scan;
- trạng thái approval gắn với object version/hash;
- khi gửi, đọc đúng phiên bản đã được duyệt;
- nếu dữ liệu thay đổi, phải quét và duyệt lại.

Với dữ liệu trong bộ nhớ, có thể giữ cùng byte array đã kiểm tra để tạo attachment. Nếu chuyển qua object storage, phải xác định version hoặc checksum để chắc chắn worker lấy đúng nội dung.

## 6. Giới hạn kích thước và chống archive bomb

Một file nhỏ sau giải nén có thể tạo ra dữ liệu rất lớn. Ví dụ ZIP bomb có thể chứa nhiều lớp nén hoặc số lượng entry khổng lồ. Nếu endpoint nhận archive, đừng chỉ giới hạn kích thước ZIP ban đầu.

Cần cân nhắc:
- số byte upload tối đa;
- tổng dung lượng sau giải nén;
- số lượng entry;
- độ sâu archive lồng nhau;
- tỷ lệ nén bất thường;
- thời gian giải nén;
- đường dẫn entry có traversal như `../../outside.txt`;
- archive được mã hóa khiến antivirus không thể scan nội dung.

Nếu nghiệp vụ không cần ZIP, từ chối archive sẽ đơn giản hơn. Nếu cần, giải nén trong sandbox, không dùng đường dẫn entry làm đường dẫn đích trực tiếp, giới hạn tổng byte và số entry, đồng thời scan từng nội dung theo policy.

### 6.1. Đặt giới hạn ở Spring Boot

Ví dụ cấu hình giới hạn multipart cho upload nhỏ:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 6MB
      file-size-threshold: 1MB
```

Các con số chỉ là ví dụ; chọn theo nghiệp vụ và hạ tầng. `max-file-size` giới hạn từng file, `max-request-size` giới hạn tổng request multipart. `file-size-threshold` ảnh hưởng ngưỡng lưu multipart tạm trong bộ nhớ hay tệp tạm tùy servlet container.

Cần cấu hình giới hạn tương ứng ở reverse proxy/API gateway vì request có thể bị buffering trước khi tới Spring. Đừng dựa duy nhất vào kiểm tra trong service sau khi toàn bộ file đã được nhận.

## 7. Tên attachment phải do server kiểm soát

Tên file gốc là metadata không tin cậy. Trong email, filename được đưa vào MIME header như `Content-Disposition`; ký tự điều khiển hoặc giá trị bất thường có thể gây lỗi parser, hiển thị sai hoặc header injection nếu xử lý không đúng.

Một chiến lược an toàn:
- sinh tên file mới từ loại tài liệu và ID nghiệp vụ;
- chỉ dùng extension đã xác định từ policy/detection;
- giới hạn độ dài;
- loại CR, LF, NUL và ký tự điều khiển;
- không đưa path, username, email hoặc dữ liệu nhạy cảm vào filename;
- không cho client tự chọn filename cuối cùng.

Ví dụ:

```text
invoice-ORD-2026-001.pdf
support-document-8f32a1.pdf
monthly-report-2026-11.csv
```

`MimeMessageHelper.addAttachment` nhận filename hiển thị riêng với resource byte. Hãy truyền tên đã được server tạo, không truyền một đường dẫn filesystem.

Không cần dùng `Paths.get(originalFilename).getFileName()` như biện pháp bảo mật duy nhất. Nó có thể giúp tách path theo một số quy tắc hệ điều hành, nhưng không giải quyết ký tự điều khiển, extension giả, tên trùng hoặc quyền truy cập.

## 8. Kiểm tra quyền người dùng và recipient

Một file sạch về mặt malware vẫn có thể **không được phép gửi**.

Ví dụ:
- Người dùng A đoán được ID file của người dùng B.
- Nhân viên gửi hóa đơn của khách hàng này tới địa chỉ email của khách hàng khác.
- Một tài liệu nội bộ bị đính kèm vào email marketing.
- File đã bị thu hồi nhưng job gửi trong queue vẫn xử lý.
- Người dùng không có quyền gửi tài liệu của tenant khác.

Trước khi tạo attachment, kiểm tra:
1. Actor hiện tại có quyền đọc tài liệu không?
2. Tài liệu có thuộc đúng tenant/customer/case/order không?
3. Trạng thái tài liệu có cho phép gửi không?
4. Recipient có được liên kết với nghiệp vụ và được phép nhận file không?
5. Loại dữ liệu có được phép gửi qua email theo chính sách tổ chức không?
6. Người gửi có quyền thực hiện hành động này không?

**Authorization phải được kiểm tra ở server trên từng file và từng recipient**, không chỉ dựa trên ID trong request hoặc nút bấm đã ẩn ở giao diện.

Nếu email gửi đến địa chỉ do người dùng nhập, cần xác thực quyền gửi tài liệu tới địa chỉ đó. Một địa chỉ hợp lệ về cú pháp không đồng nghĩa người nhận có quyền nhận nội dung.

## 9. Ví dụ Spring Boot: chỉ gửi PDF đã qua kiểm tra

Ví dụ sau minh họa endpoint nhận **PDF hóa đơn**. Policy chỉ cho phép PDF, giới hạn dung lượng, kiểm tra byte signature, nhận diện MIME, gọi malware scanner và parser validator. Tên attachment được server sinh; tên gốc và Content-Type từ client không được dùng làm bằng chứng.

Để tập trung vào quy trình, scanner và PDF validator được biểu diễn bằng interface. Hệ thống thực tế phải cung cấp implementation thật và không được mặc định bỏ qua khi dịch vụ scan không khả dụng.

### 9.1. Dependency nhận diện nội dung

Có thể thêm Apache Tika Core để nhận diện media type. Ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.tika:tika-core:<approved-version>'
}
```

`<approved-version>` là placeholder; hãy chọn phiên bản Tika được tổ chức phê duyệt và tương thích với dependency policy của dự án. Không copy placeholder vào file build.

### 9.2. Model của attachment đã duyệt

```java
package com.example.mail;

public record ApprovedAttachment(
    byte[] content,
    String filename,
    String contentType,
    String sha256
) {
    public ApprovedAttachment {
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
```

Việc copy byte array trong constructor và accessor giúp tránh caller sửa mảng sau khi đã duyệt. Với file lớn, nên dùng object storage version bất biến và một abstraction stream thay vì giữ mọi byte trong RAM.

### 9.3. Các interface kiểm tra

```java
package com.example.mail;

public interface MalwareScanner {
    ScanResult scan(byte[] content);
}

public enum ScanResult {
    CLEAN,
    INFECTED,
    UNAVAILABLE
}
```

```java
package com.example.mail;

public interface PdfValidator {
    void validate(byte[] content);
}
```

`MalwareScanner` cần gọi engine/service scan thật. `PdfValidator` cần dùng parser PDF phù hợp để kiểm tra cấu trúc, giới hạn tài nguyên và từ chối file lỗi. Không cài một implementation “luôn clean” hoặc “luôn valid” để chạy production.

### 9.4. Service xác minh PDF upload

```java
package com.example.mail;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

import org.apache.tika.Tika;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class PdfAttachmentPolicy {

    private static final int MAX_BYTES = 5 * 1024 * 1024;

    private final MalwareScanner malwareScanner;
    private final PdfValidator pdfValidator;
    private final Tika tika = new Tika();

    public PdfAttachmentPolicy(
            MalwareScanner malwareScanner,
            PdfValidator pdfValidator) {
        this.malwareScanner = malwareScanner;
        this.pdfValidator = pdfValidator;
    }

    public ApprovedAttachment approve(MultipartFile upload)
            throws IOException {

        if (upload == null || upload.isEmpty()) {
            throw new IllegalArgumentException("Thiếu tệp PDF");
        }

        // Kiểm tra size trước khi đọc toàn bộ vào RAM.
        if (upload.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("Tệp vượt giới hạn");
        }

        byte[] bytes = upload.getBytes();

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Kích thước tệp không hợp lệ");
        }

        // Signature PDF là một lớp kiểm tra, không phải chứng minh an toàn.
        if (!startsWithPdfSignature(bytes)) {
            throw new IllegalArgumentException("Nội dung không phải PDF");
        }

        String detectedType = tika.detect(bytes);
        if (!"application/pdf".equals(detectedType)) {
            throw new IllegalArgumentException(
                "Định dạng phát hiện không phải PDF"
            );
        }

        // Parser phải xác minh cấu trúc và giới hạn tài nguyên.
        pdfValidator.validate(bytes);

        // Không chấp nhận lỗi scanner như kết quả sạch.
        ScanResult scanResult = malwareScanner.scan(bytes);
        if (scanResult != ScanResult.CLEAN) {
            throw new IllegalArgumentException(
                "Tệp chưa được xác nhận an toàn"
            );
        }

        String hash = sha256(bytes);

        // Tên file do server tạo; không dùng originalFilename.
        String safeFilename =
            "document-" + UUID.randomUUID() + ".pdf";

        return new ApprovedAttachment(
            bytes,
            safeFilename,
            "application/pdf",
            hash
        );
    }

    private static boolean startsWithPdfSignature(byte[] bytes) {
        byte[] signature = "%PDF-".getBytes(StandardCharsets.US_ASCII);
        if (bytes.length < signature.length) {
            return false;
        }
        for (int i = 0; i < signature.length; i++) {
            if (bytes[i] != signature[i]) {
                return false;
            }
        }
        return true;
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(bytes);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 không khả dụng", ex);
        }
    }
}
```

Các giới hạn của ví dụ:
- `MAX_BYTES` là ngưỡng ứng dụng minh họa, phải thấp hơn giới hạn request/provider phù hợp.
- `MultipartFile.getSize()` được kiểm tra trước `getBytes()`, nhưng vẫn cần giới hạn ở proxy/container để ngăn request quá lớn từ sớm.
- Signature và Tika chỉ giúp nhận diện loại file; parser và scanner vẫn cần thiết.
- Scanner `UNAVAILABLE` bị từ chối như một trường hợp chưa được phê duyệt.
- `sha256` liên kết approval với đúng byte đã kiểm tra; nếu lưu sang storage, cần xác minh lại version/hash khi gửi.
- Tên file gốc không được sử dụng làm tên attachment.

### 9.5. Chỉ đính kèm object đã được policy duyệt

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class DocumentMailService {

    private final JavaMailSender mailSender;
    private final PdfAttachmentPolicy attachmentPolicy;
    private final DocumentAuthorization authorization;

    public DocumentMailService(
            JavaMailSender mailSender,
            PdfAttachmentPolicy attachmentPolicy,
            DocumentAuthorization authorization) {
        this.mailSender = mailSender;
        this.attachmentPolicy = attachmentPolicy;
        this.authorization = authorization;
    }

    public void sendPdf(
            String actorId,
            String recipient,
            String orderId,
            org.springframework.web.multipart.MultipartFile upload)
            throws Exception {

        // Kiểm tra quyền gửi tài liệu cho recipient theo order.
        authorization.requireCanSendOrderDocument(
            actorId, orderId, recipient
        );

        // Chỉ trả về dữ liệu đã qua policy.
        ApprovedAttachment attachment =
            attachmentPolicy.approve(upload);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("documents@example.com");
        helper.setTo(recipient);
        helper.setSubject("Tài liệu đơn hàng " + orderId);
        helper.setText(
            "Tài liệu PDF đã được kiểm tra và đính kèm."
        );

        helper.addAttachment(
            attachment.filename(),
            new ByteArrayResource(attachment.content()),
            attachment.contentType()
        );

        mailSender.send(message);
    }
}
```

`DocumentAuthorization` là interface nghiệp vụ minh họa. Implementation phải kiểm tra quan hệ giữa actor, order, tài liệu và recipient trong database/service đáng tin cậy. Không dùng một boolean do client gửi như `isAuthorized=true`.

Đoạn code cũng giả định scanner và parser hoạt động đồng bộ. Với tài liệu lớn hoặc scan chậm, nên chuyển sang quy trình bất đồng bộ: upload vào quarantine, tạo scan job, chỉ khi trạng thái được phê duyệt mới cho phép gửi. Trong trường hợp đó, email worker nhận **ID của attachment đã duyệt**, không nhận lại một file upload tùy ý.

## 10. Thiết kế bất đồng bộ với quarantine và approved storage

Với hệ thống có nhiều người dùng hoặc file lớn, có thể lưu tệp tạm trong object storage:

```text
Upload API
    |
    v
Quarantine object (immutable version)
    |
    v
Validation / parser / malware scan
    |
    +--> REJECTED: giữ metadata, xóa/quarantine theo retention
    |
    +--> APPROVED: lưu approved object reference + hash
                         |
                         v
                  Email request/outbox
                         |
                         v
                   Mail worker
                         |
                         +--> load exact approved version
                         +--> verify status/hash/authorization
                         +--> addAttachment
                         +--> send
```

Ưu điểm:
- Không phải giữ các file lớn trong heap của web request.
- Scan có thể chạy trong worker riêng, có timeout và retry.
- Có thể giữ phiên bản bất biến và hash.
- Mail worker chỉ được đọc approved object theo quyền cần thiết.
- Có thể lưu trạng thái và audit cho từng lần gửi.

Các điểm cần kiểm soát:
- Không dùng key do client chọn làm storage path.
- Không cho người dùng truy cập object quarantine trực tiếp.
- Chỉ worker có quyền gửi mới đọc approved object.
- Kiểm tra file chưa bị thu hồi/hết hạn tại thời điểm gửi.
- Nếu object version hoặc hash khác với bản scan, không đính kèm.
- Có retention và cleanup cho file bị từ chối, file hết hạn và bản tạm.
- Không đặt public-read trên bucket chỉ để mail worker tải được file.

## 11. Không tự động fetch URL do người dùng cung cấp

Một số chức năng cho phép người dùng nhập URL để ứng dụng tải tài liệu rồi gửi email. Đây là một rủi ro khác: **Server-Side Request Forgery (SSRF)**.

URL có thể trỏ tới:
- địa chỉ loopback hoặc private network;
- metadata service của cloud;
- hostname nội bộ chỉ server mới truy cập được;
- URL redirect sang host khác;
- endpoint lớn hoặc phản hồi vô hạn;
- tài nguyên không phải file như HTML hoặc stream.

Nếu nghiệp vụ buộc phải nhận URL:
1. Ưu tiên allowlist domain/host cụ thể.
2. Chỉ cho phép scheme cần thiết, thường là HTTPS.
3. Resolve DNS và chặn địa chỉ private, loopback, link-local, multicast và metadata ranges.
4. Kiểm tra lại đích sau redirect; tốt nhất tắt redirect tự động nếu không cần.
5. Giới hạn connect/read timeout, số byte tải, số redirect và loại nội dung.
6. Không gửi credential nội bộ hoặc cookie người dùng tới host ngoài.
7. Sau khi tải, vẫn đưa byte qua cùng pipeline validate/scan trước khi đính kèm.

Không dùng `new URL(userInput).openStream()` hoặc HTTP client mặc định để tải URL bất kỳ rồi gọi `addAttachment`.

## 12. Các rủi ro định dạng đặc biệt

### 12.1. HTML và SVG

HTML hoặc SVG có thể chứa markup, liên kết, tham chiếu tài nguyên hoặc nội dung chủ động tùy cách trình xem xử lý. Không cho phép chúng chỉ vì có thể đính kèm dưới dạng file. Nếu nghiệp vụ cần ảnh, thường ưu tiên raster PNG/JPEG đã được giải mã và re-encode qua thư viện ảnh phù hợp.

Với ảnh upload:
- kiểm tra định dạng thực;
- giới hạn chiều rộng, chiều cao và tổng pixel;
- giải mã trong môi trường có giới hạn tài nguyên;
- re-encode thành định dạng được cho phép;
- bỏ metadata EXIF nếu không cần;
- không tin extension hoặc content type do client gửi.

### 12.2. Office documents và macro

Một file có đuôi `.docx` hoặc `.xlsx` không đồng nghĩa chắc chắn không có nội dung nguy hiểm. Định dạng Office dựa trên container và có thể chứa nhiều thành phần. Nếu cần hỗ trợ Office:
- giới hạn loại tài liệu được phép;
- từ chối macro-enabled formats nếu không có nhu cầu rõ ràng;
- kiểm tra cấu trúc gói và entry;
- scan nội dung sau khi giải nén có kiểm soát;
- cân nhắc chuyển đổi sang PDF trong sandbox nếu người nhận chỉ cần xem.

### 12.3. Archive và ZIP Slip

Khi giải nén, không nối tên entry trực tiếp vào thư mục đích. Một entry như `../../outside.txt` có thể thoát khỏi thư mục giải nén nếu không chuẩn hóa và xác minh path. Dùng thư viện xử lý archive đã cập nhật, kiểm tra normalized path nằm bên trong destination, giới hạn entry count và expanded size.

### 12.4. File mã hóa hoặc có password

Nếu scanner không thể đọc nội dung của archive/PDF được bảo vệ bằng password, đừng mặc định đó là file sạch. Policy có thể:
- từ chối;
- yêu cầu người dùng cung cấp bản không mã hóa qua kênh phù hợp;
- chuyển sang quy trình review riêng;
- hoặc chỉ chấp nhận nếu có một cách kiểm tra được phê duyệt.

Không gửi file mã hóa qua email để né antivirus scan.

## 13. MIME attachment: API gửi không phải bộ lọc bảo mật

Sau khi file được duyệt, Spring Mail chỉ cần nhận một resource và metadata:

```java
helper.addAttachment(
    approved.filename(),
    new ByteArrayResource(approved.content()),
    approved.contentType()
);
```

`addAttachment` không tự:
- quét virus;
- kiểm tra quyền người nhận;
- xác minh loại file;
- kiểm tra nội dung PDF;
- chuẩn hóa filename theo nghiệp vụ;
- xác minh file có thuộc đúng user/tenant;
- giới hạn tổng dung lượng theo quota ứng dụng.

Đó là lý do không nên truyền trực tiếp `MultipartFile` hoặc tên/Content-Type tùy ý từ request vào helper mà không có policy ở giữa.

### 13.1. Content-Disposition và filename

Attachment thường có MIME header:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-001.pdf"
Content-Transfer-Encoding: base64
```

Filename nên do server tạo. Tránh CR/LF, dấu phân cách đường dẫn và ký tự điều khiển. Không cần đưa path như `/var/app/uploads/invoice.pdf` vào MIME header; chỉ truyền filename hiển thị.

### 13.2. Không dùng Content-Type của client làm Content-Type cuối cùng

Sai:

```java
helper.addAttachment(
    upload.getOriginalFilename(),
    new ByteArrayResource(upload.getBytes()),
    upload.getContentType()
);
```

Đoạn này tin cả tên, MIME type và byte do client cung cấp. Đúng hơn là dùng object đã được policy xác minh:

```java
helper.addAttachment(
    approved.filename(),
    new ByteArrayResource(approved.content()),
    approved.contentType()
);
```

Ở đây `approved` là dữ liệu được tạo bởi server sau khi kiểm tra. Tên và loại MIME là kết quả policy, không phải metadata thô của request.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| File thực thi được nhận dưới tên PDF | Chỉ kiểm tra extension hoặc client MIME | Detection, signature, parser và scan theo allowlist. |
| File PDF giả được đính kèm | Chỉ kiểm tra `%PDF-` | Parser PDF, malware scan và policy cấu trúc. |
| Tên file có đường dẫn hoặc CRLF | Dùng `getOriginalFilename()` trực tiếp | Tạo filename server-side, loại ký tự điều khiển. |
| User gửi được file của tenant khác | Chỉ kiểm tra file ID tồn tại | Object-level authorization và tenant scoping. |
| Scanner lỗi nhưng file vẫn được gửi | Xem lỗi scanner như clean | Fail closed, giữ quarantine và retry/manual review. |
| File thay đổi sau scan | Scan một version, gửi version khác | Immutable object/version và hash gắn approval. |
| Email vượt giới hạn | Không giới hạn file và tổng MIME | Giới hạn upload, attachment và concurrency; gửi link khi cần. |
| Worker heap tăng mạnh | Nhiều byte array/file lớn cùng lúc | Queue, giới hạn concurrency, storage stream hoặc spool. |
| ZIP giải nén quá lớn | Chỉ giới hạn kích thước archive | Giới hạn expanded bytes, entry, depth và thời gian. |
| URL upload bị dùng để truy cập mạng nội bộ | Fetch URL tùy ý | SSRF allowlist, DNS/IP check, redirect policy, timeout và byte limit. |
| File được gửi dù đã thu hồi | Chỉ kiểm tra trạng thái khi upload | Kiểm tra lại approval/authorization tại thời điểm gửi. |
| File độc hại được scan nhưng không gắn với bản gửi | Không liên kết scan result với hash/version | Gửi đúng byte/version đã scan; kiểm tra hash trước khi đính kèm. |

## 15. Kiểm thử policy trước khi cho phép gửi

Kiểm thử nên tập trung vào quyết định **được phép hay bị từ chối** và đảm bảo attachment chỉ dùng dữ liệu đã được duyệt.

| Nhóm | Ví dụ | Kết quả kỳ vọng |
|---|---|---|
| File hợp lệ | PDF mẫu do test tạo | Qua detection, parser và scanner giả lập CLEAN. |
| Empty file | Upload 0 byte | Từ chối. |
| File quá lớn | Lớn hơn giới hạn | Từ chối trước khi đọc toàn bộ byte vào RAM. |
| MIME giả | EXE bytes nhưng header là PDF | Từ chối. |
| Extension giả | PDF bytes nhưng tên có extension khác | Xử lý theo policy; không dựa vào tên gốc. |
| Signature sai | Không có PDF magic | Từ chối. |
| PDF hỏng | Có prefix nhưng parser không đọc được | Từ chối. |
| Malware | Scanner trả INFECTED | Từ chối và ghi trạng thái phù hợp. |
| Scanner không khả dụng | Scanner trả UNAVAILABLE/timeout | Không đính kèm; giữ quarantine/retry. |
| Tên nguy hiểm | Path traversal, CR/LF, tên rất dài | Filename đầu ra do server tạo, an toàn. |
| Unauthorized file | File thuộc user/tenant khác | Từ chối trước khi tạo email. |
| Unauthorized recipient | Recipient không liên quan hồ sơ | Từ chối. |
| File bị thu hồi | Status REVOKED sau upload | Không gửi. |
| Object version đổi | Hash khác bản đã scan | Không gửi; yêu cầu scan lại. |
| Attachment nhiều file | Tổng kích thước vượt quota | Từ chối hoặc chuyển sang link an toàn. |
| Archive bomb | Expanded size hoặc entry count quá lớn | Dừng giải nén trong giới hạn. |

### 15.1. Unit test cho policy

Có thể mock scanner và PDF validator để kiểm tra các nhánh nghiệp vụ. Ví dụ:

```java
@Test
void rejectsFileWhenScannerIsUnavailable() throws Exception {
    when(scanner.scan(any()))
        .thenReturn(ScanResult.UNAVAILABLE);

    assertThatThrownBy(() -> policy.approve(validPdfUpload()))
        .isInstanceOf(IllegalArgumentException.class);
}
```

`validPdfUpload()` là fixture test tạo file PDF phù hợp với validator của test. Không dùng PDF thật có dữ liệu khách hàng trong repository.

Một test khác nên xác nhận file bị từ chối không làm phát sinh lời gọi gửi mail:

```java
@Test
void rejectedUploadDoesNotSendEmail() throws Exception {
    when(scanner.scan(any()))
        .thenReturn(ScanResult.INFECTED);

    assertThatThrownBy(() ->
        documentMailService.sendPdf(
            actorId, recipient, orderId, infectedUpload
        )
    ).isInstanceOf(IllegalArgumentException.class);

    verify(mailSender, never()).send(any(MimeMessage.class));
}
```

Test này minh họa ý tưởng; nếu service tạo `MimeMessage` trước khi policy hoàn tất, xác minh không gọi `send(...)` thay vì xác minh không có tương tác nào. Thiết kế đơn giản nhất là validate/approve trước, sau đó mới tạo MIME message.

### 15.2. Kiểm tra MIME trong test

Với một attachment được duyệt, có thể tạo `MimeMessage` và kiểm tra:
- MIME multipart có part attachment;
- `Content-Type` là loại đã được policy chọn;
- filename là tên server tạo;
- byte trích xuất từ part bằng byte đầu vào đã duyệt;
- không có file upload khác hoặc part ngoài ý muốn.

Không in Base64 vào log. Trong test, so sánh hash hoặc byte array trực tiếp.

## 16. Checklist vận hành theo luồng

**Trước khi nhận file:**
- Chỉ bật các loại file thực sự cần cho nghiệp vụ.
- Giới hạn request ở proxy/container/Spring.
- Xác thực người dùng và quota upload.
- Lưu file vào vùng staging/quarantine với key server sinh.

**Trước khi phê duyệt:**
- Kiểm tra loại file dự kiến, signature, detection và parser.
- Quét malware; xử lý lỗi scanner như chưa được phê duyệt.
- Giới hạn archive, kích thước giải nén và thời gian xử lý.
- Tạo hash/version bất biến và lưu trạng thái approval.
- Áp dụng CDR/re-encode nếu policy yêu cầu.

**Trước khi gửi:**
- Xác minh actor, tenant, tài liệu và recipient.
- Kiểm tra trạng thái vẫn APPROVED, chưa hết hạn/thu hồi.
- Đọc đúng version/hash đã scan.
- Dùng filename và Content-Type do server tạo.
- Giới hạn tổng kích thước attachment.
- Tạo MIME message riêng theo recipient và nghiệp vụ.

**Sau khi gửi:**
- Ghi nhận event ID, attachment ID/version/hash và kết quả gửi.
- Không ghi byte, Base64, token hoặc nội dung nhạy cảm vào log.
- Có retention/cleanup cho quarantine và file tạm.
- Xử lý bounce và trạng thái giao hàng nếu provider hỗ trợ.
- Có quy trình thu hồi quyền hoặc tài liệu nếu phát hiện sự cố.

## 17. Tổng kết

**Ngăn tệp người dùng tùy ý trở thành attachment** là bài toán kiểm soát dữ liệu trước khi gửi email, không chỉ là một thao tác MIME. `MimeMessageHelper.addAttachment(...)` sẽ đính kèm resource mà ứng dụng đưa vào; nó không xác minh nguồn gốc, định dạng, nội dung, quyền sở hữu hay độ an toàn của file.

Một luồng đáng tin cậy cần **allowlist theo nghiệp vụ, giới hạn upload, detection và parser, malware scan, quarantine/approval, authorization cho file và recipient, filename do server tạo, kiểm soát dung lượng và gửi đúng phiên bản đã duyệt**. Với file lớn hoặc xử lý bất đồng bộ, lưu object bất biến và gắn scan result với hash/version. Nếu không thể xác minh một tệp theo policy, đừng chuyển nó thành attachment.
