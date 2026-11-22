# Kiểm tra tên tệp, loại nội dung và đường dẫn lưu khi tải tệp lên Spring Boot

> **Phạm vi:** Trong nhóm **Tải và nhận tệp** của **Spring Boot - web-runtime**, bài học trình bày cách coi multipart upload là đầu vào không tin cậy, kiểm tra tên tệp, loại nội dung và thư mục đích, tránh ghi đè hoặc cho phép đường dẫn tùy ý, cũng như quản lý giới hạn tài nguyên. Ví dụ thực hành dùng **Spring Boot 4.1.2**, **Java 17+**, Maven và **Spring MVC**. Những nguyên tắc bảo vệ áp dụng cho WebFlux/object storage; cơ chế nhận file của các stack khác nhau.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `MultipartFile.getOriginalFilename()`, `MultipartFile.getContentType()`, phần mở rộng tên tệp, **file signature (magic bytes)** và cấu trúc dữ liệu thật.
2. Nhận diện **path traversal**, tên giả mạo, double extension, ghi đè tệp, symlink, đường dẫn công khai và lưu file có khả năng thực thi.
3. Thiết kế **allowlist** cho tên/định dạng, phát sinh tên lưu bằng UUID hoặc ID do server cấp và kiểm soát vị trí lưu bằng `Path`.
4. Đặt giới hạn kích thước request, từng file, nội dung giải mã và hạn ngạch tài nguyên; phân biệt storage tạm của multipart parser với storage bền vững.
5. Xây dựng một endpoint chạy được nhận PNG, kiểm tra khai báo MIME, byte signature, kích thước và nội dung giải mã, rồi **re-encode** trước khi lưu file mới.
6. Phân tích các giới hạn còn lại: antivirus, quét file, quyền truy cập, download, tài liệu PDF/Office, ZIP, SVG, quá tải khi decode và tính nhất quán giữa file với database.

## 1. Trust boundary của multipart/form-data

Khi browser hoặc API client gửi:

~~~http
POST /api/images/upload HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=----demo

------demo
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

[dữ liệu nhị phân của tệp]
------demo--
~~~

cả `filename="avatar.png"` và `Content-Type: image/png` của **multipart part** đều do client kiểm soát. Spring MVC có thể cung cấp hai giá trị này qua `MultipartFile`, nhưng việc nhận dữ liệu **không tự biến chúng thành thông tin đáng tin**. Một client có thể khai `image/png` cho file script, cho một file không hợp lệ hoặc cho một file chứa định dạng phức hợp.

Cần phân biệt ba cấp độ:

| Cấp độ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Khai báo của client** | `filename="avatar.png"` và `Content-Type: image/png` | Dữ liệu đầu vào để kiểm tra sơ bộ, **có thể giả mạo** |
| **Định dạng được xác minh** | Magic bytes PNG, parser nhận PNG, kích thước hợp lệ | Bằng chứng mạnh hơn về loại file; không có nghĩa đã sạch mã độc |
| **Định danh và quyền do server quản lý** | ID ngẫu nhiên, private storage path, quyền theo user/tenant | Quyết định tệp nào được lưu và ai được đọc sau này |

Luồng xử lý đề xuất:

~~~text
HTTP client
   |
   v
Gateway / Reverse proxy
   +-- authentication, request-body limit, rate limit (nếu cấu hình)
   |
   v
Servlet multipart parser
   +-- spring.servlet.multipart.max-file-size
   +-- spring.servlet.multipart.max-request-size
   +-- bộ nhớ / temporary disk của server
   |
   v
@RestController nhận MultipartFile
   |
   +-- Kiểm tra quyền và quota theo người dùng
   +-- Kiểm tra original filename (chỉ là metadata)
   +-- Kiểm tra declared Content-Type (dữ liệu không tin cậy)
   +-- Đọc bytes có bound và kiểm magic bytes
   +-- Parse nội dung thật bằng parser phù hợp
   +-- Giới hạn dimensions/pages/entries/CPU/RAM
   +-- Scan hoặc re-encode nếu loại file cho phép
   +-- Tạo tên lưu do server sinh
   +-- Ghi private storage với CREATE_NEW
   +-- Ghi metadata owner, type, size, trạng thái
   |
   v
HTTP 201 + opaque ID (không trả absolute path)
~~~

**Không có một kiểm tra đơn lẻ nào đủ:** extension, MIME, signature, decoder, thư mục ngoài webroot, scan và phân quyền là những lớp phòng vệ bổ sung cho nhau.

### Ngữ nghĩa các API Spring

- `MultipartFile.getName()`: tên **form field** của file, chẳng hạn `"file"`, không phải filename gốc.
- `MultipartFile.getOriginalFilename()`: tên file do client cung cấp, có thể `null` hoặc rỗng; tài liệu Spring cảnh báo có thể chứa path và ký tự `..`.
- `MultipartFile.getContentType()`: media type part do client khai báo, có thể `null`.
- `MultipartFile.getSize()`: kích thước phần file mà multipart parser cung cấp.
- `MultipartFile.getInputStream()`: đọc bytes thực tế; quản lý stream và không đọc vô hạn vào heap.
- `MultipartFile.transferTo(...)`: có thể chuyển nội dung thành file đích, nhưng **không thực hiện thay** chính sách validation, chống path traversal, content scan hoặc chống ghi đè của ứng dụng.

Không nhầm `multipart/form-data` là Content-Type của **toàn request** với `image/png` là Content-Type của **part**.

## 2. Tên tệp: kiểm metadata nhưng không dùng để đặt tên lưu

### 2.1. Các mẫu filename nguy hiểm

~~~text
../../application.properties
..\..\secret.txt
/var/app/config.yaml
C:\Windows\temp\evil.exe
file.png.exe
report.pdf.jsp
photo.php%00.png
avatar.png:alternate-stream
NUL.png
CON.png
.
..
photo.png.
photo.png 
dir/photo.png
dir\photo.png
Ảnh hồ sơ.png
PHOTO.PNG
~~~

Rủi ro gồm:

- **Traversal:** `../` và `..\` có thể đi ra ngoài thư mục dự kiến nếu ghép thẳng thành path. Trên Windows có thêm UNC và drive letter.
- **Double extension:** chỉ tìm chuỗi `.png` ở bất cứ vị trí nào sẽ nhận nhầm `file.png.exe`; dùng allowlist **phần mở rộng cuối** và parser.
- **Null/control/encoded characters:** mã hóa nhiều lớp hoặc ký tự NUL có thể được các thư viện xử lý khác nhau; không “vá” bằng một vài lệnh `replace("../", "")`.
- **Tên thiết bị và đặc biệt:** `CON`/`NUL`, dấu hai chấm, ký tự điều khiển, dấu chấm hoặc khoảng trắng cuối có ý nghĩa đặc biệt trên một số filesystem.
- **Unicode:** khác biệt normalize NFC/NFD, ký tự giống nhau về hình dáng nhưng khác mã, không phân biệt hoa/thường hoặc độ dài theo byte có thể gây collision.
- **Các tên hợp lệ về ngôn ngữ:** `Ảnh hồ sơ.png` có thể phù hợp UX, nhưng không nên trở thành tên file trực tiếp trên đĩa; nếu muốn hiển thị thì lưu metadata riêng và escape khi xuất HTML/HTTP header.

**Chính sách đề xuất:** nhận một allowlist filename khi cần giải thích lỗi cho client, nhưng **luôn dùng tên lưu do server tạo**, kể cả khi filename qua kiểm tra.

### 2.2. Vì sao chỉ lấy basename là chưa đủ?

Đoạn sau không giải quyết toàn bộ vấn đề:

~~~java
// Chỉ minh họa một cách thường thấy; không dùng làm đường ghi upload.
String original = file.getOriginalFilename();
String base = Path.of(original).getFileName().toString();
Path destination = uploadRoot.resolve(base);
~~~

`Path.getFileName()` chịu ngữ nghĩa hệ điều hành đang chạy: dấu `\` là separator ở Windows nhưng không phải lúc nào ở Linux; `Path.of(...)` có thể ném lỗi với ký tự không hợp lệ. Kể cả kết quả là `avatar.png`, file cùng tên có thể tồn tại và bị ghi đè. Tên đặc biệt, symlink và race vẫn tồn tại. Cách tốt hơn là **không dùng tên gốc làm thành phần đích**.

Nếu app phải hỗ trợ tên gốc trong metadata, có thể chuẩn hóa Unicode NFC, giới hạn chiều dài theo byte và ký tự cho phép; chỉ hiển thị sau khi escape đúng ngữ cảnh. Không đưa trực tiếp tên gốc vào log, HTML hoặc `Content-Disposition` mà không xử lý.

### 2.3. Dùng filename ngẫu nhiên, format từ server

~~~text
originalFilename (metadata): "avatar.png"
storedFilename (server ID):   "1bc30dd3-c831-4c3c-9c68-ac3b17de6515.png"
storageRoot (config trusted): /srv/app/private-uploads
absolute storedPath:         /srv/app/private-uploads/1bc30dd3-c831-4c3c-9c68-ac3b17de6515.png
client-visible ID:           1bc30dd3-c831-4c3c-9c68-ac3b17de6515.png
~~~

UUID làm xác suất trùng cực thấp, nhưng vẫn cần `CREATE_NEW` để không ghi đè tệp đã tồn tại. UUID chỉ là **định danh**, không phải bằng chứng người dùng được phép tải file. Metadata database nên lưu owner, tenant, media type đã xác minh, size, checksum nếu cần và scan status.

## 3. Kiểm tra loại nội dung ở nhiều lớp

### 3.1. Allowlist theo tính năng

Chọn đúng định dạng nghiệp vụ cần, ví dụ ảnh đại diện chỉ nhận `.png` và `.jpg`. Nếu không thật sự cần SVG, HTML, Office, ZIP, PHP, JSP, EXE... thì đừng bật. Blacklist chỉ một vài extension nguy hiểm không bao quát mọi biến thể có khả năng thực thi.

Cho một tính năng **chỉ PNG**, thứ tự kiểm tra có thể là:

1. Filename đúng cú pháp/chiều dài và kết thúc bằng `.png` (chính sách không phân biệt chữ hoa/thường).
2. Declared MIME part là `image/png`, chỉ dùng để loại sớm.
3. Byte signature đúng PNG.
4. Parser ảnh có thể đọc thật, xác nhận format và kích thước hợp lệ.
5. Nếu có thể, decode thành ảnh raster và encode lại thành PNG mới.
6. Dùng tên server-generated `UUID.png` và chỉ ghi vào private storage.

### 3.2. File signature (magic bytes)

| Loại | Dấu hiệu nhận biết phổ biến | Điều chưa được xác minh |
| --- | --- | --- |
| PNG | `89 50 4E 47 0D 0A 1A 0A` | Kết cấu chunk/CRC, pixels, parser safety, nội dung lạ |
| JPEG | `FF D8 FF` | Decoder/EXIF/ICC, tính toàn vẹn ảnh |
| GIF | `GIF87a` hoặc `GIF89a` | Frame/animation, kích thước sau giải mã |
| PDF | `%PDF-` thường ở đầu | Embedded content, JavaScript, objects, mức độ nguy hiểm |
| ZIP | Nhiều dạng signature như `PK 03 04` | Entries, decompression bombs, Zip Slip, loại payload bên trong |
| OOXML Office | Container ZIP với entries đặc thù | Không đồng nghĩa bất kỳ ZIP nào cũng là DOCX/XLSX hợp lệ |

File có signature đúng vẫn có thể là file hỏng, chứa dữ liệu chèn thêm hoặc **polyglot** (hợp lệ theo nhiều format). Parser/decoder chuyên dụng, limit và scan vẫn cần thiết.

### 3.3. MIME khai báo và MIME được phục vụ

Content-Type của upload part có thể bị client giả mạo, ví dụ:

~~~bash
curl -F "file=@payload.txt;filename=photo.png;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Việc HTTP request nói `image/png` không biến text thành PNG. Ngược lại, khi download, backend phải **tự xác định response Content-Type từ metadata đã xác thực**: không phản chiếu giá trị `getContentType()` nguyên gốc.

### 3.4. Parser và giới hạn tài nguyên

Dùng decoder ảnh là một lớp xác minh mạnh hơn signature. Tuy nhiên, ảnh nén nhỏ có thể giải mã thành bitmap rất lớn. Cần kiểm:

- Kích thước file trước/sau parse; kích thước output re-encode có thể lớn hơn input.
- Width, height và tổng pixels; số frame nếu GIF/multipage image.
- Thời gian decode, CPU, heap, concurrent upload; thư viện decoder đã vá.
- Quy tắc metadata (EXIF, màu, orientation), việc chấp nhận tệp rút gọn/hỏng.
- Antivirus hoặc content disarm khi tải file không thể re-encode an toàn.

Không hứa một regex extension hoặc một bộ magic bytes đủ để ngăn malware.

## 4. Đường dẫn lưu: root tin cậy, tên được sinh mới, không overwrite

### 4.1. Path traversal phòng ngừa theo chiều từ vựng

Nếu buộc phải tính path từ một ID, cần kiểm tra `normalize()`/`startsWith()`:

~~~java
// Minh họa, root là Path tuyệt đối được quản trị và bảo vệ trước đó.
Path target = root.resolve(candidateName).normalize();
if (!target.getParent().equals(root)) {
    throw new SecurityException("Invalid target path");
}
~~~

Chỉ kiểm tra từ vựng **không đủ** nếu attacker có thể tạo/thay symlink hoặc directory ancestor. Đối với upload bình thường, tên đích hoàn toàn do server tạo, không chứa separator, để không cần nhận path từ client.

### 4.2. Symlink và TOCTOU

Giả sử một bên không tin cậy có quyền ghi vào thư mục chứa file, họ có thể tạo symlink hoặc thay directory giữa lúc ứng dụng kiểm tra và mở file (**time-of-check to time-of-use**). `Path.normalize()` không theo symlink, còn `toRealPath()` chỉ cho biết trạng thái tại thời điểm gọi, không khóa cấu trúc filesystem vĩnh viễn.

Quy tắc vận hành:

- Tạo private directory do tài khoản dịch vụ/administrator sở hữu; chỉ cấp quyền tối thiểu.
- Không cho untrusted process sửa directory/parent (đặc biệt trên shared hosts).
- Dùng API tạo file mới `StandardOpenOption.CREATE_NEW`; khi threat model có adversary cục bộ, dùng directory-relative safe open hoặc object-store policy phù hợp nền tảng.
- Không tự động mở quyền read mọi file trong storage để phục vụ web.
- Có quota và cảnh báo disk-full, read-only filesystem, permissions.

### 4.3. Phân biệt storage tạm và storage lâu dài

Spring MVC multipart parser có thể lưu dữ liệu upload tạm trong RAM hoặc file tạm, rồi xóa khi request kết thúc. `spring.servlet.multipart.location` chỉ là **vị trí tạm**, không phải kho business. Ứng dụng phải xác minh rồi ghi sang storage riêng của mình.

Nếu lưu trên object storage như S3, Blob Storage hoặc GCS, nguyên tắc vẫn tương đương: bucket private, key do server sinh, không cho client quyết định bucket/key tùy ý, policy IAM, checksum và scan state. Nếu dùng presigned upload, phải kiểm điều kiện content length/type trước và **xác minh lại sau upload** trước khi publish.

## 5. Giới hạn kích thước và tấn công tài nguyên

Spring Boot hỗ trợ:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
~~~

- `max-file-size` giới hạn từng file part.
- `max-request-size` giới hạn toàn request multipart gồm các part và overhead.
- Có thể bổ sung giới hạn reverse proxy, load balancer và web server.
- Service vẫn nên đọc stream với bound để phòng thủ nhiều lớp, và thiết lập quota theo user/tenant.

Trong Java 17:

~~~java
// Đoạn minh họa trong method service; MAX_BYTES là giới hạn do ứng dụng chọn.
try (InputStream in = file.getInputStream()) {
    byte[] data = in.readNBytes(MAX_BYTES + 1);
    if (data.length > MAX_BYTES) {
        throw new ResponseStatusException(
                HttpStatus.PAYLOAD_TOO_LARGE, "Upload too large");
    }
}
~~~

Tại thời điểm controller chạy, servlet multipart parser có thể đã nhận/lưu tạm dữ liệu. Vì thế **giới hạn ở parser và proxy** cần bật trước để giảm nguy cơ request lớn chiếm tài nguyên.

Giới hạn kích thước **sau khi giải mã/giải nén** quan trọng ngang giới hạn file gốc. Ảnh chỉ 100 KiB có thể chứa nhiều triệu pixels; ZIP vài MB có thể giải nén thành hàng GB; PDF phức tạp có thể tiêu thụ CPU lâu. Giới hạn số part, depth của archive, số pages/frames, concurrency, thời gian và bộ nhớ của parser.

## 6. Ví dụ hoàn chỉnh: endpoint upload PNG bằng Spring MVC

Ứng dụng minh họa **chỉ nhận PNG** để có chính sách đơn giản, xác định rõ. Demo từ chối tên có đường dẫn, ký tự nguy hiểm, double extension và declared MIME sai; kiểm chữ ký PNG, kiểm định dạng bằng `ImageIO` và width×height, re-encode, rồi ghi vào thư mục private dưới tên UUID mới. Các file PNG không hợp lệ không được lưu vào đích.

**Sơ đồ:**

~~~text
POST /api/images/upload
    -> MultipartFile
    -> validateOriginalName
    -> getContentType == image/png
    -> bounded read <= 2 MiB
    -> PNG signature + ImageIO reader
    -> dimensions <= 4,000,000 pixels
    -> decode BufferedImage
    -> encode lại PNG
    -> random UUID.png + CREATE_NEW
    -> 201 {id,sizeBytes,width,height}
~~~

### 6.1. Cấu trúc

~~~text
safe-upload/
  pom.xml
  src/main/java/com/example/safeupload/
    SafeUploadApplication.java
    ImageUploadService.java
    ImageUploadController.java
  src/main/resources/
    application.properties
~~~

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>safe-upload</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-webmvc` có Spring MVC và servlet container cần cho `MultipartFile`. Parent Boot quản lý dependency versions. Với Spring Boot 3.x thường dùng starter `spring-boot-starter-web` phù hợp phiên bản. Không bắt buộc thêm thư viện Commons FileUpload cho cơ chế servlet multipart thông thường.

### 6.3. `SafeUploadApplication.java`

~~~java
package com.example.safeupload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeUploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeUploadApplication.class, args);
    }
}
~~~

### 6.4. `ImageUploadService.java`

~~~java
package com.example.safeupload;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Iterator;
import java.util.UUID;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ImageUploadService {
    private static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final long MAX_PIXELS = 4_000_000L;
    private static final byte[] PNG_SIGNATURE = {
        (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
    };

    private final Path storageRoot;

    public ImageUploadService(
            @Value("${app.upload.directory}") String configuredDirectory)
            throws IOException {
        Path configured = Path.of(configuredDirectory)
                .toAbsolutePath().normalize();

        // Config do admin quản lý, không đọc từ request.
        Files.createDirectories(configured);
        if (!Files.isDirectory(configured, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(configured)) {
            throw new IOException("Unsafe upload directory");
        }
        storageRoot = configured.toRealPath();
    }

    public SavedImage save(MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw badRequest("PNG file is required");
        }

        validateOriginalName(file.getOriginalFilename());

        if (!"image/png".equalsIgnoreCase(file.getContentType())) {
            throw badRequest("Declared type must be image/png");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
        }

        byte[] bytes;
        try (InputStream in = file.getInputStream()) {
            bytes = in.readNBytes(MAX_BYTES + 1);
        }
        if (bytes.length > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
        }

        if (bytes.length < PNG_SIGNATURE.length
                || !Arrays.equals(
                        Arrays.copyOf(bytes, PNG_SIGNATURE.length),
                        PNG_SIGNATURE)) {
            throw badRequest("File is not PNG");
        }

        // Decoder đọc cấu trúc và chặn ảnh có số pixel quá lớn.
        BufferedImage image = decodePng(bytes);

        // File đích do server sinh, không chứa user filename.
        String generatedName = UUID.randomUUID() + ".png";
        Path target = storageRoot.resolve(generatedName).normalize();

        if (!target.getParent().equals(storageRoot)) {
            throw new IOException("Invalid upload target");
        }

        boolean opened = false;
        boolean completed = false;
        try {
            try (OutputStream out = Files.newOutputStream(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                opened = true;
                if (!ImageIO.write(image, "png", out)) {
                    throw new IOException("PNG encoder unavailable");
                }
            }
            completed = true;
        } finally {
            if (opened && !completed) {
                Files.deleteIfExists(target);
            }
        }

        return new SavedImage(
                generatedName, Files.size(target),
                image.getWidth(), image.getHeight());
    }

    private static void validateOriginalName(String name) {
        // Demo giới hạn tên ASCII, chỉ 1 dấu chấm cuối + extension png.
        if (name == null
                || !name.matches(
                        "[A-Za-z0-9][A-Za-z0-9_-]{0,79}\\.[Pp][Nn][Gg]")) {
            throw badRequest("Unsafe or unsupported filename");
        }
    }

    private static BufferedImage decodePng(byte[] bytes) {
        try (ImageInputStream stream = ImageIO.createImageInputStream(
                new ByteArrayInputStream(bytes))) {
            if (stream == null) {
                throw badRequest("Image stream unavailable");
            }
            Iterator<ImageReader> it = ImageIO.getImageReaders(stream);
            if (!it.hasNext()) {
                throw badRequest("Unsupported image data");
            }

            ImageReader reader = it.next();
            try {
                reader.setInput(stream, true, true);
                if (!"png".equalsIgnoreCase(reader.getFormatName())) {
                    throw badRequest("Actual format is not PNG");
                }

                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                if (width <= 0 || height <= 0
                        || (long) width * height > MAX_PIXELS) {
                    throw badRequest("Image dimensions exceed limit");
                }

                BufferedImage image = reader.read(0);
                if (image == null) {
                    throw badRequest("Cannot decode image");
                }
                return image;
            } finally {
                reader.dispose();
            }
        } catch (IOException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid PNG structure", ex);
        }
    }

    private static ResponseStatusException badRequest(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }

    public record SavedImage(
            String id, long sizeBytes, int width, int height) {}
}
~~~

**Giải thích code:**

- Regex filename chỉ cho một basename ASCII ngắn, một dấu chấm cuối và extension `.png` không phân biệt chữ hoa/thường. `abc.php.png`, `../../file.png`, `photo.png.exe`, `file:name.png`, dấu cách và dấu phân cách đều bị từ chối. Quy tắc ASCII là lựa chọn **cố ý của demo**, không phải quy tắc bắt buộc cho ngôn ngữ quốc tế; tên có dấu có thể được lưu như metadata sau khi xử lý an toàn.
- `getContentType()` là kiểm tra sớm **không đáng tin một mình**. Magic bytes và `ImageIO` kiểm định tiếp theo.
- `readNBytes(MAX_BYTES + 1)` không đọc vô hạn vào RAM. Multipart parser cũng bị giới hạn bởi property. Với upload lớn không thể giữ trong RAM, thiết kế stream/quarantine và scanner riêng.
- `ImageIO.getImageReaders` + `getWidth/getHeight` kiểm tra số pixel trước khi decode. Re-encode qua `ImageIO.write` loại bỏ nhiều dữ liệu không cần thiết của file gốc nhưng **không là biện pháp bảo mật duy nhất**.
- `MAX_PIXELS=4_000_000` là ví dụ; một bitmap 4 triệu pixel có thể chiếm hàng chục MB hoặc hơn tùy decoder. Nên đo tài nguyên ở concurrency thật.
- `UUID.randomUUID() + ".png"` do server quyết định tên lưu, `CREATE_NEW` ngăn ghi đè khi trùng; check `target.getParent().equals(storageRoot)` là thêm phòng vệ cho code.
- Cờ `opened/completed` xóa file chưa ghi xong chỉ khi chính request đã tạo file. Nếu `CREATE_NEW` từ chối vì file đã tồn tại, không xóa file của người khác.
- `Files.createDirectories(...)` chỉ an toàn khi cấu hình storage root và các thư mục parent **do quản trị viên kiểm soát**, không cho attacker local sửa symlink. Demo không giải quyết toàn bộ race trong môi trường shared filesystem không tin cậy.
- `SavedImage` chứa tên ID và thông số đã kiểm tra; không xuất đường dẫn tuyệt đối của máy chủ.

### 6.5. `ImageUploadController.java`

~~~java
package com.example.safeupload;

import java.io.IOException;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.example.safeupload.ImageUploadService.SavedImage;

@RestController
@RequestMapping("/api/images")
public class ImageUploadController {
    private final ImageUploadService service;

    public ImageUploadController(ImageUploadService service) {
        this.service = service;
    }

    @PostMapping(
            path = "/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<SavedImage> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        SavedImage saved = service.save(file);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
~~~

Controller không tạo path từ input, chỉ chuyển part cho service rồi trả HTTP **201 Created** khi upload hoàn tất. Error từ validation được map theo `ResponseStatusException`. I/O error khác (ví dụ hết disk) thường thành 5xx; production nên chuẩn hóa error response mà không rò đường dẫn thật.

### 6.6. `application.properties`

~~~properties
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB

# Folder private minh họa: dưới home của account chạy ứng dụng.
# Production phải cấp quyền riêng và tách khỏi static/webroot.
app.upload.directory=${user.home}/private-uploads-demo
~~~

`app.upload.directory` là property riêng do code đọc bằng `@Value`; không phải location tạm của multipart parser. Muốn đổi folder tạm, dùng `spring.servlet.multipart.location` với cấu hình và quyền phù hợp.

### 6.7. Chạy và thử nghiệm

Tại thư mục `safe-upload`, chạy:

~~~bash
mvn spring-boot:run
~~~

Chuẩn bị một file PNG hợp lệ `photo.png` trong thư mục gọi curl. Gửi:

~~~bash
curl -i \
  -F "file=@photo.png;filename=photo.png;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

HTTP thành công là **201 Created**, nội dung JSON có dạng sau (chỉ minh họa format, số đo thực tế phụ thuộc ảnh):

~~~json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.png",
  "sizeBytes": 12345,
  "width": 640,
  "height": 480
}
~~~

Tệp vật lý được lưu dưới tên UUID tại `private-uploads-demo` trong thư mục home của account chạy JVM, khác tên client. Kích thước output có thể khác input vì ảnh được re-encode.

Kiểm tra double extension:

~~~bash
curl -i \
  -F "file=@photo.png;filename=photo.png.exe;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Kỳ vọng **400** do tên bị từ chối.

Kiểm tra traversal:

~~~bash
curl -i \
  -F "file=@photo.png;filename=../../config.png;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Kỳ vọng **400**; ứng dụng không tạo file ở `../../`.

Kiểm tra MIME giả:

~~~bash
curl -i \
  -F "file=@photo.png;filename=photo.png;type=text/plain" \
  http://localhost:8080/api/images/upload
~~~

Kỳ vọng **400** theo declared MIME. Nếu client khai `type=image/png` nhưng bytes thực tế không phải PNG, code chặn ở signature/decoder.

PowerShell trên Windows dùng `curl.exe`:

~~~powershell
curl.exe -i -F "file=@photo.png;filename=photo.png;type=image/png" http://localhost:8080/api/images/upload
~~~

Đóng gói và chạy JAR:

~~~bash
mvn package
java -jar target/safe-upload-0.0.1-SNAPSHOT.jar
~~~

Với Spring, chỉ chạy `javac` trần không đủ vì classpath Maven chứa thư viện Spring cần thiết.

### 6.8. Status và nguyên nhân cần phân biệt

| Tình huống | Kết quả được kỳ vọng | Giai đoạn |
| --- | --- | --- |
| PNG hợp lệ, filename/MIME đúng | **201**, JSON có ID do server tạo | Controller và service |
| Tên có `../`, dấu `\`, double extension | **400** | Filename validation |
| Declared MIME là `text/plain` | **400** | Metadata validation |
| Không có PNG signature | **400** | Byte validation |
| Decoder không đọc được ảnh | **400** | Format validation |
| Width×height vượt limit | **400** | Resource validation |
| Upload vượt max file/request size | Thường phản hồi lỗi quá lớn, có thể **413**, tùy exception mapping/container | Multipart parser, trước controller |
| Folder không thể ghi hoặc disk đầy | Thường **5xx**, cần server log/alert | Storage I/O |

Trong production, thêm `@RestControllerAdvice` hoặc cơ chế xử lý exception chung để bảo đảm status/body lỗi nhất quán; không tiết lộ hệ thống file, stack trace hay nội dung không an toàn trong thông báo lỗi.

## 7. Những giới hạn còn lại của ví dụ

Ví dụ là **đường upload PNG có kiểm tra nhiều lớp**, chưa phải một hệ thống upload production hoàn chỉnh.

- **Authentication/authorization:** endpoint cần giới hạn ai được tải và lưu vào kho của ai; tránh endpoint công khai không quota.
- **Quota:** giới hạn request rate, số lượng file, tổng byte theo tenant, số upload đồng thời, thời gian decode/CPU.
- **Output quota:** PNG re-encode có thể tạo file lớn hơn 2 MiB; cân nhắc stream encoding có bound, disk quota, limit pixels thấp hơn hoặc lưu staging rồi đo trước khi publish.
- **Antivirus/scan:** ảnh parser hợp lệ vẫn có thể chứa exploit nhắm vào thư viện xử lý ở bên khác; scan phù hợp mức rủi ro.
- **Quarantine:** upload vào khu riêng, scan và chỉ chuyển sang trạng thái ACTIVE khi đủ kiểm định; cleanup bản bị từ chối.
- **Database consistency:** nếu file tạo thành công nhưng ghi DB lỗi sẽ xuất hiện orphan; nếu DB ghi trước rồi file lỗi sẽ có metadata trỏ tới file thiếu. Dùng staging, trạng thái và cleanup/retry idempotent.
- **File permissions:** đảm bảo storage root và các ancestor không writable bởi untrusted accounts; quyền file mới kế thừa môi trường/umask/ACL, nên cần kiểm cấu hình OS.
- **Atomic publishing:** nếu reader khác có thể đoán ID hoặc filesystem có nhiều actor, tạo file ở staging private rồi atomic move vào vùng chỉ đọc khi hoàn thành.
- **Server-side threat model:** ImageIO và encoder cần được cập nhật, có giới hạn số request và giám sát parser; re-encode không phải antivirus.
- **Business metadata:** giữ owner, checksum, verified MIME, file size thực sau khi ghi, upload timestamp, retention, trạng thái, audit events.

## 8. Khi cần hỗ trợ PDF, Office, SVG, ZIP hoặc video

| Định dạng | Đặc thù phải kiểm | Hướng xử lý |
| --- | --- | --- |
| JPEG | EXIF, kích thước ảnh, màu, metadata, parser | Image decoder, pixel cap, re-encode, optional metadata stripping |
| PDF | Embedded files/JS, số trang, parser, external links | Parser PDF, pages/resources limits, scan/CDR, sandbox khi render |
| DOCX/XLSX/PPTX | ZIP container, external relationships, embedded objects | Thư viện Office, validate entries, scan; không chỉ kiểm `PK` |
| SVG | XML, script, external resources, active content | Chỉ bật nếu bắt buộc; sanitizer chuyên dụng, CSP, serve thận trọng |
| ZIP/TAR | Zip Slip, symlinks, recursive archives, decompress bombs | Giới hạn entries/depth/ratio/output bytes; kiểm từng entry path |
| MP4/video | Parser/transcoder, codec, duration, CPU/disk | Sandbox ffmpeg, resource/time budget, normalize/scan |
| HTML | XSS và active content nếu serve inline | Không cho tệp HTML tùy ý vào public static; escape/attachment |
| CSV | Formula injection khi mở bằng spreadsheet app | Xử lý giá trị ô khi export và chính sách content disposition |

**ZIP Slip** là lỗi lấy tên entry như `../../config.txt` rồi giải nén vào `root.resolve(entryName)` mà không xác minh đường dẫn. Nếu cho phép archive, phải kiểm từng entry, symlink và giới hạn tổng tài nguyên sau giải nén.

**PDF/Office:** signature đúng không chứng minh không có mã độc hoặc active content; chọn thư viện parser được hỗ trợ, nhận diện số pages/objects và giới hạn xử lý. Tùy hệ thống, có thể dùng content disarm and reconstruction hoặc scan asynchronous trước khi người khác được tải xuống.

**Không dùng regex để parse định dạng phức tạp.** Regex tên file hợp lệ chỉ là tuyến phòng vệ cho metadata, không kiểm nội dung.

## 9. Download: kiểm tra lại đường đi từ storage ra client

Upload thành công không có nghĩa client bất kỳ được dùng `/download?path=...` để đọc tệp. Endpoint download nên:

1. Nhận **file ID** do server phát hành, không nhận absolute/relative filesystem path tùy ý.
2. Tra metadata và kiểm owner/tenant, quyền đọc, file status (chẳng hạn ACTIVE sau scan) và retention.
3. Lấy storage key từ metadata đã kiểm định, kiểm tra định dạng key nếu cần, resolve trong root tin cậy.
4. Chọn response `Content-Type` theo loại thực **đã xác minh**, không phản ánh `getContentType()` ban đầu.
5. Xét `Content-Disposition: attachment` để hạn chế browser render nội dung không tin cậy và `X-Content-Type-Options: nosniff`; escape/encode filename khi gửi HTTP header.
6. Stream có quota/timeout, phù hợp cache control và audit, không log secret/path của tenant.

Chỉ có UUID khó đoán **không phải** cơ chế authorization. Nếu browser được render HTML/SVG từ cùng origin và các file không được xử lý đúng, có thể mở ra nguy cơ XSS; cần policy response tương ứng với content thực.

## 10. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `uploadRoot.resolve(file.getOriginalFilename())` | Traversal, collision, ghi sai thư mục | Tên lưu từ UUID hoặc internal ID |
| Dùng `Path.getFileName()` rồi lưu ngay | Vẫn là tên client, có tên đặc biệt/collision | Chỉ giữ để hiển thị; path do server tạo |
| Cho phép đuôi file qua `name.contains(".png")` | Nhận `photo.png.exe` | Validate full extension allowlist; parse thật |
| Tin `getContentType()` | Giả mạo MIME | Validate signature + format parser |
| Chỉ kiểm signature | Có thể file hỏng, polyglot, bom tài nguyên | Parse, limit, re-encode/scan |
| Tin `normalize().startsWith(root)` đủ chống symlink | Race hoặc link đổi nơi đích | Root private, quyền OS/ACL, safe open |
| Ghi file bằng cách replace/truncate | Ghi đè file tồn tại | `CREATE_NEW`, random file ID |
| Đặt file trong `static/`/webroot | Bypass auth, file có thể được phục vụ trực tiếp | Private storage và authorized download |
| Chỉ giới hạn size sau controller | Multipart parser/gateway đã tốn tài nguyên | Proxy + servlet multipart + service limits |
| Không giới hạn pixels/pages/entries | Decompression bomb/CPU/memory overload | Resource budgets cho decoder |
| Đọc mọi file vào `byte[]` không giới hạn | OOM hoặc GC pressure | Bounded read hoặc streaming |
| Re-encode mà không xét output size | Kích thước file lưu có thể tăng | Disk/bytes quota, staging |
| Dùng filename gốc trong HTML/header không escape | XSS, response splitting hoặc lỗi encoding | Encode/escape theo ngữ cảnh |
| Upload thành công là file công khai ngay | Chưa scan/kiểm quyền vẫn bị tải | Quarantine và trạng thái publish |
| Không xử lý partial write | File rác/orphan | Cleanup khi lỗi, staged publish |
| Không giới hạn theo user/tenant | Disk fill/cost abuse | Auth, rate limit, storage quota, audit |

## 11. Câu hỏi tự kiểm tra

**Câu A:** Tệp có tên `photo.png` và declared `Content-Type: image/png`. Đã đủ để tin nó là ảnh an toàn chưa?

**Đáp án:** Chưa. Tên/MIME là dữ liệu client. Kiểm tra bytes, parser/decoder, giới hạn dung lượng và loại file; scan/transform khi mức độ rủi ro yêu cầu.

**Câu B:** Vì sao `Path.of(name).getFileName()` không bảo đảm an toàn tuyệt đối?

**Đáp án:** Tên vẫn có thể không phù hợp OS, gây collision hoặc bị lợi dụng symlink; dấu phân cách cũng khác giữa nền tảng. Tên storage nên do backend tạo.

**Câu C:** `target.normalize().startsWith(root)` có đủ chống mọi path traversal không?

**Đáp án:** Không. Kiểm tra lexical không ngăn symlink/TOCTOU khi parent writable bởi bên không tin cậy. Root private và quyền OS rất quan trọng.

**Câu D:** PNG chỉ 50 KiB có cần giới hạn pixels không?

**Đáp án:** Có. Kích thước nén và kích thước bitmap sau decode rất khác; giới hạn width, height, số pixel và concurrency.

**Câu E:** `spring.servlet.multipart.location` là thư mục lưu vĩnh viễn?

**Đáp án:** Không. Nó là vùng tạm của multipart parser; vị trí lưu lâu dài do ứng dụng quyết định.

**Câu F:** File đã có UUID ngẫu nhiên có cần kiểm quyền download?

**Đáp án:** Có. UUID là ID tránh trùng và khó đoán, không phải quyền truy cập.

**Câu G:** Có nên hỗ trợ file ZIP chỉ vì magic bytes bắt đầu bằng `PK`?

**Đáp án:** Không. Phải kiểm cấu trúc archive, entries, số bytes giải nén, symlink, Zip Slip, recursion và malware.

## 12. Tài liệu chính thức

- [Spring Boot — Spring MVC multipart upload](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)
- [Spring Boot — Common Application Properties: servlet.multipart](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework — MultipartFile API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html)
- [Spring Framework — Multipart forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Guides — Uploading Files](https://spring.io/guides/gs/uploading-files/)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload)
- [Java SE 17 — java.nio.file.Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 17 — ImageIO](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/imageio/ImageIO.html)

**Nguyên tắc:** client được quyền gửi metadata và bytes, nhưng **không được quyết định đường dẫn lưu hoặc loại file đáng tin**. Backend xác thực định dạng bằng parser có giới hạn, sinh storage ID mới, ghi vào root riêng với quyền OS chặt chẽ và `CREATE_NEW`, chỉ cung cấp download sau khi kiểm quyền và trạng thái file.