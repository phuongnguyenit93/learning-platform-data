# Multipart trong HTTP và khác biệt với nội dung JSON

## 1. Vấn đề cần giải quyết

Một API nhận thông tin đơn hàng thường chỉ cần JSON. Nhưng API nhận một ảnh đại diện, tài liệu PDF hoặc tệp CSV còn phải nhận **nội dung file dạng byte**. Nếu gửi file dưới dạng chuỗi JSON, ta phải biến đổi byte sang một biểu diễn văn bản như Base64, làm payload lớn hơn và tăng nhu cầu bộ nhớ. HTTP có một cách khác: `multipart/form-data`, cho phép một request chứa **nhiều phần (part)**, mỗi phần có tên, header và nội dung riêng.

Trong Spring Boot, hiểu đúng định dạng HTTP quyết định cách viết controller:
- Với `Content-Type: application/json`, dùng `@RequestBody` để đọc và chuyển toàn bộ body thành đối tượng Java.
- Với `Content-Type: multipart/form-data; boundary=...`, dùng `@RequestParam`, `@RequestPart` và `MultipartFile` ở Spring MVC, hoặc `FilePart`/`Part` ở Spring WebFlux.
- Khi gửi **metadata JSON kèm file**, phần metadata có thể mang `Content-Type: application/json` để `@RequestPart` giải mã bằng JSON converter.

Bài này thuộc ngữ cảnh **tải và nhận tệp** của Spring Boot web runtime. Sau bài học, bạn sẽ đọc được một raw multipart request, phân biệt JSON/multipart/nhị phân thuần, tự chạy một upload endpoint Java 17, hiểu cấu hình giới hạn dung lượng và nhận biết các lỗi thường gặp liên quan đến bảo mật, memory, temporary storage và HTTP status.

> **Phiên bản thực hành:** ví dụ chạy độc lập dùng Java 17+ và **Spring Boot 3.5.x, Spring MVC** với starter `spring-boot-starter-web`. Trên Spring Boot 4.x chọn starter `spring-boot-starter-webmvc`. Những khác biệt Servlet/WebFlux được giải thích riêng; không trộn `MultipartFile` của MVC với `FilePart` của WebFlux.

## 2. “Body HTTP” không đồng nghĩa “JSON”

Một HTTP request có method, URL, headers và body (nếu có). `Content-Type` mô tả cách diễn giải body. Dữ liệu JSON chỉ là **một định dạng nội dung**, không phải cơ chế duy nhất của HTTP.

### 2.1. Body JSON thông thường

Ví dụ request gửi một đối tượng:

~~~http
POST /api/documents/metadata HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "title": "Bao cao",
  "category": "finance"
}
~~~

Toàn bộ phần sau dòng trống giữa header/body là **một tài liệu JSON**. Spring MVC có thể đọc trực tiếp bằng:

~~~java
// Fragment trong một @RestController, không phải chương trình chạy độc lập.
@PostMapping(
    path = "/api/documents/metadata",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Metadata create(@RequestBody Metadata metadata) {
    return metadata;
}
~~~

`@RequestBody` nhờ `HttpMessageConverter` (thường là Jackson JSON converter) chuyển toàn bộ body thành `Metadata`. Nếu client gửi JSON không hợp lệ, không đúng kiểu dữ liệu hoặc header không phù hợp, controller có thể không được gọi.

### 2.2. Body multipart/form-data

Ví dụ request mang **metadata JSON** và **file**:

~~~http
POST /api/documents HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary

--DemoBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Bao cao","category":"finance"}
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<noi-dung-byte-cua-tap-tin-PDF>
--DemoBoundary--
~~~

Đây là **minh họa cấu trúc HTTP**, không phải yêu cầu copy nguyên văn gửi lên mạng: ký hiệu `<noi-dung-byte-cua-tap-tin-PDF>` đại diện cho các byte PDF thật, và ở wire format dòng phân cách sử dụng CRLF (`\r\n`). Một trình HTTP client sẽ tạo boundary hợp lệ và phát các byte đúng chuẩn.

Điểm khác biệt:
1. Header ngoài có `Content-Type: multipart/form-data` và tham số bắt buộc `boundary=DemoBoundary`.
2. Mỗi part bắt đầu bằng `--DemoBoundary`, sau đó có header part, một dòng trống và body riêng.
3. `Content-Disposition: form-data; name="metadata"` xác định **tên trường**. Trường `file` còn có `filename="report.pdf"`, chỉ là thông tin do client gửi lên.
4. `Content-Type: application/json` nằm **trên part metadata**; `application/pdf` nằm **trên part file**. Content-Type của mỗi part có thể khác Content-Type ngoài cùng.
5. Delimiter cuối `--DemoBoundary--` có thêm hai dấu gạch ngang kết thúc. Boundary được chọn sao cho delimiter không trùng với nội dung part.

**Không nhầm boundary với tên file hoặc tên field.** Client quyết định chuỗi boundary và phải khớp chính xác giữa header ngoài và các delimiter. Theo RFC 7578, `multipart/form-data` sử dụng cơ chế MIME multipart, mỗi part phải có `Content-Disposition` chứa `name`; file part thường bổ sung `filename`. Những header khác của part phụ thuộc nội dung và không nhất thiết luôn có.

## 3. Bảng so sánh JSON và multipart

| Tiêu chí | `application/json` | `multipart/form-data` |
|---|---|---|
| Bản chất | Một tài liệu JSON là body của request | Body gồm nhiều part phân cách bằng boundary |
| Mục đích thường gặp | Dữ liệu cấu trúc: metadata, lệnh nghiệp vụ, danh sách | Form chứa file, hoặc file và metadata cùng request |
| Dữ liệu nhị phân | Thường cần Base64/string hoặc giao thức khác | File bytes có thể giữ dưới dạng nhị phân trực tiếp |
| Header ngoài | `Content-Type: application/json` | `Content-Type: multipart/form-data; boundary=...` |
| Header từng phần | Không có part riêng | Mỗi part có `Content-Disposition`, có thể có `Content-Type` |
| Nhận ở Spring MVC | `@RequestBody Dto` | `@RequestPart Dto`, `@RequestParam`, `MultipartFile` |
| Nhận ở WebFlux | `@RequestBody Mono<Dto>`/Dto | `@RequestPart`, `Part`, `FilePart`, `Flux<PartEvent>` |
| Browser form | JSON thường do JavaScript tự tạo body | `<form enctype="multipart/form-data">` hoặc JavaScript `FormData` |
| Dung lượng | Rất phù hợp dữ liệu text có cấu trúc | Phù hợp file, nhưng multipart cũng có overhead header/boundary |
| Validation | Kiểu trường, schema, Bean Validation | Kiểm tra từng part, JSON metadata và file bytes riêng |
| Hiển thị/debug | Dễ đọc trong JSON viewer | Phải xem part, field name, content type và boundary |
| Khi nào ưu tiên | Không cần file bytes | Cần gửi file và thuộc tính trong cùng một request |

**Không có quy tắc “multipart luôn tốt hơn JSON”.** JSON đơn giản hơn cho API chỉ nhận metadata. Multipart hữu ích khi nhiều nội dung hoặc tệp binary được gửi trong một request. Cũng có API nhận **một file nhị phân thuần** bằng `Content-Type: application/octet-stream`, nhưng lúc đó không có cơ chế phân chia các part như multipart.

### JSON chứa Base64 vẫn là JSON

Một API có thể nhận:

~~~json
{
  "filename": "report.pdf",
  "contentBase64": "JVBERi0xLjQK..."
}
~~~

Cách này hợp lệ nếu hợp đồng API quy định như vậy, nhưng không phải multipart. Khi encode binary Base64, dữ liệu thường tăng gần **33%** (chưa tính JSON wrapper), đồng thời tăng chi phí encode/decode và các bản sao chuỗi/byte trong bộ nhớ. Không suy diễn Base64 là bảo mật/mã hóa; đó chỉ là mã hóa biểu diễn dữ liệu.

Ví dụ file 3 MiB có thể thành chuỗi Base64 khoảng 4 MiB. Với file lớn, streaming multipart hoặc một binary-body endpoint thường phù hợp hơn, tùy yêu cầu kiểm soát dữ liệu.

## 4. Những tên và header dễ nhầm

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Outer media type | `multipart/form-data` | Toàn body là multipart |
| Outer boundary | `boundary=----client123` | Chuỗi delimiter do client sinh, phải khớp raw body |
| Part field name | `name="file"` | Khớp với `@RequestPart("file")` hoặc `@RequestParam("file")` |
| Part filename | `filename="photo.jpg"` | Tên client báo cáo; **không được tin** khi lưu |
| Part media type | `Content-Type: image/jpeg` | Loại nội dung client khai báo; cần xác thực nếu ảnh hưởng bảo mật |
| Part body | Các byte ảnh | Nội dung thật của file |
| Request length | `Content-Length` hoặc chuyển truyền tương đương | Kích thước/truyền tải ngoài; không thay giới hạn multipart server |
| Closing delimiter | `--boundary--` | Đánh dấu kết thúc multipart body |

Tên `metadata`, `file` trong controller là contract của API. Nếu client gửi `name="upload"` nhưng handler bắt buộc `@RequestPart("file")`, phía server sẽ báo thiếu part `file`. Đổi tên biến Java thôi không thay đổi tên part mà client phải gửi; chính giá trị trong annotation là hợp đồng.

**Lưu ý Content-Type của part JSON:** JSON metadata là một part độc lập, vì vậy nếu muốn `@RequestPart("metadata") Metadata` tự deserialize JSON, part đó nên có `Content-Type: application/json`. Nếu chỉ gửi một string text/plain chứa chuỗi JSON, Spring có thể không chọn JSON converter và trả `415 Unsupported Media Type`. Dùng `@RequestPart("metadata") String` để xử lý text thuần khi hợp đồng thiết kế như vậy, hoặc sửa client gửi part JSON đúng media type.

## 5. Chọn annotation đúng trong Spring MVC

### `@RequestBody` — toàn body là JSON

~~~java
@PostMapping(
    path = "/api/metadata",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Metadata postMetadata(@RequestBody Metadata metadata) {
    return metadata;
}
~~~

Phù hợp khi **cả HTTP body** chỉ là JSON. Không đặt một tham số `@RequestBody Metadata` rồi kỳ vọng Spring tự tách `multipart/form-data` thành JSON part và file part.

### `@RequestParam` — trường form hoặc file

~~~java
// Fragment Spring MVC, cần import MultipartFile và RequestParam.
@PostMapping(
    path = "/api/simple-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public String upload(
    @RequestParam("description") String description,
    @RequestParam("file") MultipartFile file
) {
    return description + ": " + file.getSize();
}
~~~

Khi form có trường text `description` và một trường file `file`, `@RequestParam` là lựa chọn trực tiếp. Spring MVC cho phép `MultipartFile` hoặc `jakarta.servlet.http.Part` cho file và có thể nhận `List<MultipartFile>` khi nhiều file cùng field name.

### `@RequestPart` — một part cần message conversion

~~~java
// Fragment Spring MVC; metadata part phải được gửi như application/json.
@PostMapping(
    path = "/api/upload-with-meta",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public String upload(
    @RequestPart("metadata") Metadata metadata,
    @RequestPart("file") MultipartFile file
) {
    return metadata.title() + " (" + file.getSize() + " bytes)";
}
~~~

`@RequestPart` hữu ích khi metadata là đối tượng JSON phức tạp cần `HttpMessageConverter`. Có thể kết hợp `@Valid`/Bean Validation trên DTO; validation của metadata **không thay thế** kiểm tra file.

### `@ModelAttribute` — bind dữ liệu form thành object

Một form đơn giản có các thuộc tính text và `MultipartFile` cũng có thể bind vào một form object. Dùng khi muốn dữ liệu form theo cấu trúc JavaBean; dùng `@RequestPart` khi client rõ ràng gửi JSON subpart cần deserialize.

**Không trộn annotation theo thói quen:** lựa chọn tùy media type ngoài, media type của từng part và loại dữ liệu.

## 6. Bài thực hành chạy được: JSON riêng và multipart gồm file + JSON

Tạo **một dự án Spring Boot 3.5.x**, Java 17+ bằng Spring Initializr, loại build Gradle, dependency **Spring Web**. Dự án do Initializr tạo sẵn `build.gradle` và Gradle wrapper. Với Boot 4.x dùng dependency `spring-boot-starter-webmvc` tương ứng.

Nếu bổ sung dependency vào dự án Boot 3.5 đã có plugin và dependency management, fragment Gradle là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tạo file Java duy nhất tại `src/main/java/demo/upload/UploadDemoApplication.java`:

~~~java
package demo.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@RestController
public class UploadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(UploadDemoApplication.class, args);
    }

    public record Metadata(String title) { }

    public record Receipt(String title, long bytes, boolean received) { }

    @PostMapping(
        path = "/api/metadata",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Metadata json(@RequestBody Metadata metadata) {
        return metadata;
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Receipt upload(
            @RequestPart("metadata") Metadata metadata,
            @RequestPart("file") MultipartFile file) {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "File must not be empty");
        }

        return new Receipt(metadata.title(), file.getSize(), true);
    }
}
~~~

Mã này **chạy hoàn chỉnh** trong ứng dụng Boot MVC đã có dependency. Nó chỉ kiểm tra và trả thông tin file, **không ghi file xuống ổ đĩa**; điều đó giúp thí nghiệm tập trung vào cách HTTP multipart được parse. Trong production, sau validation cần quyết định cơ chế lưu trữ, sinh ID, phân quyền và xử lý file an toàn.

Chạy ở thư mục gốc dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows, dùng `gradlew.bat bootRun`.

### 6.1. Gửi JSON

Lệnh sau dùng `curl` trong Bash/macOS/Linux:

~~~bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"title":"Demo"}' \
  http://localhost:8080/api/metadata
~~~

**Response body JSON kỳ vọng:**

~~~json
{"title":"Demo"}
~~~

### 6.2. Gửi multipart

Tạo file ASCII chính xác 3 byte:

~~~bash
printf 'abc' > sample.txt
~~~

Gửi metadata JSON **dưới dạng một part** và file **dưới dạng part khác**:

~~~bash
curl -sS \
  -F 'metadata={"title":"Demo"};type=application/json' \
  -F 'file=@sample.txt;type=text/plain' \
  http://localhost:8080/api/upload
~~~

**Response body JSON kỳ vọng:**

~~~json
{"title":"Demo","bytes":3,"received":true}
~~~

Giải thích từng thành phần:

- `-F` khiến curl tạo `multipart/form-data` và boundary phù hợp.
- `metadata=...;type=application/json` bảo đảm part metadata có media type JSON, giúp Spring deserialize thành record `Metadata`.
- `file=@sample.txt;type=text/plain` gửi **nội dung file 3 byte**, không gửi nguyên văn string `@sample.txt`; dấu `@` là cú pháp của curl khi dùng `-F`.
- `@RequestPart("file") MultipartFile` đọc part `file`; `file.getSize()` trả số byte nhận được trong ví dụ này.
- Server trả JSON vì `@RestController` và có JSON converter, mặc dù **request là multipart**. Media type của request và response không bắt buộc giống nhau.

Nếu chạy bằng Windows PowerShell, hãy dùng `curl.exe` thay vì alias `curl` của Windows PowerShell 5.1 và điều chỉnh quoting phù hợp. Câu lệnh `printf` là lệnh POSIX; có thể tạo `sample.txt` với đúng ba byte `abc` bằng editor không thêm newline.

### 6.3. So sánh bằng HTTP inspector

Thử gửi JSON tới URL chỉ chấp nhận multipart:

~~~bash
curl -i -H 'Content-Type: application/json' \
  -d '{"title":"Demo"}' \
  http://localhost:8080/api/upload
~~~

Vì `/api/upload` khai báo `consumes=multipart/form-data`, request này không khớp media type, thông thường trả **415 Unsupported Media Type**. Đây là lỗi **header/body contract**, không phải lỗi controller Java record hay thiếu file trên ổ đĩa.

Thử bỏ JSON content type của part metadata. Tùy curl và converter, server có thể không deserialize metadata thành `Metadata` và báo lỗi media type; kiểm tra header từng part bằng `curl -v` hoặc công cụ HTTP inspector trước khi đổi annotation.

## 7. Client trình duyệt: HTML form và JavaScript FormData

### HTML form tiêu chuẩn

~~~html
<form method="post" action="/api/upload" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">Send</button>
</form>
~~~

Form này chỉ gửi file; nó **chưa gửi part metadata dạng JSON** nên chưa đáp ứng hoàn toàn endpoint trong mục 6. Nó minh họa rằng `enctype="multipart/form-data"` là cách browser gửi nội dung form chứa file. Có thể thiết kế server nhận trường text qua `@RequestParam` thay vì JSON part, hoặc dùng JavaScript bên dưới.

### JavaScript gửi file và JSON part

Đoạn code sau là **fragment phía browser**; giả sử trang có `<input id="file" type="file">` và người dùng đã chọn file:

~~~javascript
const selected = document.querySelector("#file").files[0];
if (!selected) {
  throw new Error("Choose a file first");
}

const form = new FormData();
form.append(
  "metadata",
  new Blob([JSON.stringify({ title: "Demo" })],
           { type: "application/json" })
);
form.append("file", selected);

const response = await fetch("/api/upload", {
  method: "POST",
  body: form
});
if (!response.ok) {
  throw new Error("Upload failed: " + response.status);
}
const receipt = await response.json();
console.log(receipt);
~~~

**Không tự đặt header `Content-Type: multipart/form-data` trong `fetch`** khi dùng `FormData`: browser phải sinh boundary và điền tham số `boundary` vào header. Nếu tự đặt header nhưng không kèm boundary trùng với body, server sẽ không tách được part và request có thể bị 400. Dùng `FormData` cũng không tự xác thực loại file hay quyền của user.

Với API khác origin, còn có CORS/preflight và chính sách cookie/credentials cần cấu hình độc lập. Một request có body hợp lệ vẫn có thể bị chặn bởi CORS hoặc Security.

## 8. Nhiều file, file rỗng và metadata phức tạp

### Nhiều file cùng tên part

Theo RFC 7578, client có thể gửi **nhiều part cùng `name="files"`**, mỗi part mang một file. Trong Spring MVC:

~~~java
// Fragment trong controller, không phải chương trình Java độc lập.
@PostMapping(
    path = "/api/bulk-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public int uploadMany(@RequestPart("files") List<MultipartFile> files) {
    return files.size();
}
~~~

Client:

~~~bash
curl -sS \
  -F 'files=@a.txt' \
  -F 'files=@b.txt' \
  http://localhost:8080/api/bulk-upload
~~~

Lệnh giả định `a.txt` và `b.txt` tồn tại. Không phải tạo một JSON array chứa file hay dùng tên part tùy ý khác nhau. Đừng lẫn `files` với `file` trong annotation.

### File rỗng, thiếu file và file 0 byte

- **Thiếu part**: controller yêu cầu `@RequestPart("file")` nhưng request không có `name="file"`, Spring thường trả 400 vì thiếu part bắt buộc.
- **Có part nhưng rỗng**: `file.isEmpty()` là true khi không có dữ liệu hoặc file không được chọn theo cách biểu diễn của request; ví dụ mục 6 chủ động trả 400.
- **File hợp lệ có 0 byte**: một số nghiệp vụ vẫn cho phép (ví dụ file marker), nên `isEmpty()` không phải quy tắc toàn cục. Hãy xác định contract theo từng endpoint.
- **Tên file rỗng hoặc vắng mặt**: `MultipartFile.getOriginalFilename()` có thể null/rỗng tùy client; đừng dựa vào tên để kết luận dữ liệu thực sự có hay không.

### Metadata JSON nhiều trường

~~~json
{
  "title": "Báo cáo tháng",
  "category": "finance",
  "tags": ["internal", "2026"],
  "notify": false
}
~~~

Vẫn chỉ là **một part JSON**. Spring sẽ deserialize cấu trúc đó thành một DTO/record tương thích nếu đúng media type và có JSON converter. Validation của DTO có thể được kích hoạt bằng `@Valid @RequestPart("metadata")` khi đã thêm Bean Validation và constraint tương ứng. Sau đó **vẫn phải** kiểm tra file ngoài DTO: kích thước, format, quyền, số lượng, virus scanning theo nghiệp vụ.

## 9. Spring MVC: multipart resolver, lifecycle và giới hạn upload

Spring Boot MVC dùng hỗ trợ multipart của Servlet container (như Tomcat) và cấu hình resolver để phần `multipart/form-data` được parse trước khi argument resolver truyền chúng vào controller. Thông thường starter MVC cung cấp cơ chế này và không cần tự viết parser MIME.

**Default của Spring Boot MVC** theo tài liệu hiện hành:
- `spring.servlet.multipart.enabled=true`: bật multipart.
- `spring.servlet.multipart.max-file-size=1MB`: giới hạn **mỗi file**.
- `spring.servlet.multipart.max-request-size=10MB`: giới hạn **cả request multipart**, bao gồm file/part và overhead.
- `spring.servlet.multipart.file-size-threshold=0B`: ngưỡng việc buffer dữ liệu file chuyển sang disk.
- `spring.servlet.multipart.location`: thư mục **tạm/intermediate** phục vụ parse, không phải đường dẫn lưu kết quả cuối cùng của nghiệp vụ.

Ví dụ **cấu hình minh họa** cho API cho phép file tối đa 5MB và request tối đa 6MB:

~~~yaml
spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 5MB
      max-request-size: 6MB
      file-size-threshold: 0B
~~~

Với multipart có metadata, tổng request lớn hơn tổng kích thước file đơn thuần do header/boundary và part khác; chọn `max-request-size` phù hợp, không mặc định bằng `max-file-size` nếu có nhiều file hoặc metadata lớn.

**Giới hạn phụ thuộc nhiều tầng:** reverse proxy/CDN/ingress, servlet container, Spring multipart parsing, application validation, filesystem/object storage đều có thể giới hạn kích thước khác nhau. Hãy chọn ngưỡng nhất quán và biết tầng nào có khả năng từ chối trước controller. Upload quá lớn thường được biểu hiện bằng **413 Payload Too Large**, nhưng HTTP status/error body thực tế có thể khác do exception handler, proxy và container.

**Thư mục tạm không phải storage nghiệp vụ.** Nội dung multipart có thể được buffer trong bộ nhớ hoặc ghi ra temp file theo implementation/threshold. Sau khi request được xử lý, dữ liệu tạm có thể bị xóa; muốn giữ file phải copy/transfer đến nơi lưu trữ ổn định trước khi request kết thúc.

### Không đọc tất cả file vào heap nếu không cần

~~~java
// Fragment MVC: file lớn có thể chiếm nhiều memory nếu getBytes().
byte[] bytes = file.getBytes();
~~~

`getBytes()` đưa toàn bộ nội dung vào byte array; không phù hợp với nhiều file lớn đồng thời. Có thể dùng `getInputStream()` để xử lý theo dòng hoặc `transferTo(...)` để lưu. Chúng vẫn cần validation và quản lý tài nguyên; không tự bảo đảm an toàn file.

Ví dụ fragment lưu file với tên do server sinh:

~~~java
// Fragment thực hiện sau khi validate quyền và loại file.
// uploadDir đã được tạo, nằm ngoài public static folder và có quyền phù hợp.
Path target = uploadDir.resolve(
    java.util.UUID.randomUUID() + ".bin"
);
try (InputStream in = file.getInputStream()) {
    java.nio.file.Files.copy(in, target);
}
~~~

`uploadDir`, `InputStream`, `Path` trong đoạn trên là biến/import của service thật; **không phải chương trình độc lập**. Random name tránh tin vào đường dẫn từ `getOriginalFilename()`, nhưng production còn cần atomic creation, quota, cleanup, kiểm tra nội dung, idempotency và transaction với metadata DB.

## 10. Spring WebFlux: dùng FilePart, Part và xử lý reactive

Spring WebFlux không dùng Servlet `MultipartFile` làm API chính. Đối tượng thường gặp:
- `Part`: giao diện cho một part của multipart request.
- `FilePart`: part mang file; có `filename()` và `transferTo(Path)` trả về `Mono<Void>`.
- `@RequestPart("metadata") Metadata`: có thể deserialize JSON part; có thể dùng `Mono<Metadata>` tùy cách xử lý.
- `@RequestBody Mono<MultiValueMap<String, Part>>`: xử lý tập part.
- `@RequestBody Flux<PartEvent>`: xử lý dữ liệu multipart theo luồng part/event, cần quản lý/release `DataBuffer` chính xác để tránh memory leak.

Ví dụ **fragment riêng cho một ứng dụng WebFlux** (không ghép vào ứng dụng MVC mục 6):

~~~java
// Giả sử đây là method trong @RestController của ứng dụng WebFlux.
// /srv/app/uploads đã được tạo và ứng dụng có quyền ghi ở máy chạy.
@PostMapping(
    path = "/api/reactive-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<Void> upload(@RequestPart("file") FilePart file) {
    Path target = Path.of(
        "/srv/app/uploads",
        UUID.randomUUID().toString() + ".bin"
    );
    return file.transferTo(target);
}
~~~

Các import tương ứng là `org.springframework.http.codec.multipart.FilePart`, `org.springframework.http.MediaType`, `reactor.core.publisher.Mono`, `java.nio.file.Path`, `java.util.UUID` và annotations MVC-style từ `org.springframework.web.bind.annotation` nhưng thực thi bởi WebFlux. Đây là ví dụ về **cách sử dụng FilePart**, chưa bao gồm validation/authorization và quản lý storage production. `transferTo` trả về một pipeline `Mono<Void>`; Spring đăng ký và thực thi khi xử lý request, tránh gọi `block()` trên event-loop.

Cấu hình multipart của **WebFlux** khác Servlet:

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 256KB
      max-headers-size: 10KB
      max-parts: 50
~~~

Các property này điều chỉnh mức dùng bộ nhớ của mỗi part, kích thước headers và số lượng part theo codec/implementation của phiên bản Boot. Chúng **không phải** `spring.servlet.multipart.max-file-size` của Tomcat MVC. Ngưỡng `max-in-memory-size` là cách xử lý/buffer part, **không đồng nghĩa** giới hạn tối đa tổng kích thước upload.

Nếu cần ràng buộc dung lượng file ở mức nghiệp vụ trong WebFlux, phải kiểm tra giới hạn của parser/server/gateway, theo dõi kích thước dữ liệu nhận trong flow hoặc áp dụng storage policy. Với `Flux<PartEvent>`, mọi buffer phải được tiêu thụ, chuyển tiếp hoặc giải phóng; chỉ nhận event đầu tiên rồi bỏ các event còn lại có thể gây giữ bộ nhớ/tài nguyên.

## 11. Upload file khác download file

Trong ngữ cảnh “tải và nhận tệp”, cần tách hai chiều HTTP:

| Luồng | HTTP phổ biến | Body thường gặp |
|---|---|---|
| **Upload**: client gửi file lên server | `POST`/`PUT` | `multipart/form-data` cho file + fields, hoặc `application/octet-stream` cho file thuần |
| **Download**: server gửi file về client | `GET` | Một body binary với `Content-Type` phù hợp, có thể có `Content-Disposition: attachment` |
| **Metadata**: trao đổi thuộc tính về file | `GET`/`POST`/`PATCH` tùy API | `application/json` |

Một file download đơn lẻ **không cần multipart** chỉ vì đó là file. Response có thể là `application/pdf` hoặc `application/octet-stream` với `Content-Disposition: attachment; filename=...`. Ngược lại, API upload có thể trả JSON gồm file ID, kích thước và trạng thái xử lý. **Media type của request không bắt buộc giống media type của response.**

## 12. Bảo mật: client filename, MIME, nội dung và giới hạn

Nhận file là nhận dữ liệu **không đáng tin cậy**. Multipart chỉ là cách đóng gói, không tự kiểm tra độ an toàn.

1. **Không tin `filename`:** giá trị từ client có thể chứa path separator, chuỗi `..`, ký tự điều khiển hoặc tên xung đột. Sinh storage ID trên server, lưu tên gốc riêng với escaping cần thiết khi hiển thị; tuyệt đối không gọi `Path.of(uploadDir, file.getOriginalFilename())` rồi ghi trực tiếp.
2. **Không tin `Content-Type` từ client:** `image/jpeg` có thể được gửi dù nội dung là HTML hoặc executable. Khi nghiệp vụ cần whitelist, kết hợp kiểm tra content signature/file parser, loại file được phép, extension đầu ra và MIME thực tế.
3. **Giới hạn dung lượng và số part:** chặn từ gateway và server, không chỉ `if (file.getSize() > limit)` sau khi server đã buffer file. Đặt max file/max request, rate limit, timeouts, quota, tránh nạn upload nhiều file nhỏ.
4. **Phân quyền trước khi lưu/công khai:** authentication, authorization theo chủ sở hữu/tài nguyên, CSRF protection với browser session, kiểm soát CORS, và không đưa uploads riêng tư vào public static resources.
5. **Lưu ở vùng an toàn:** thư mục ngoài web root, quyền filesystem tối thiểu hoặc object storage riêng; thiết kế antivirus/malware scanning, quarantining, lifecycle cleanup, encryption và audit theo độ nhạy nghiệp vụ.
6. **Chặn rủi ro nội dung:** file nén quá lớn sau giải nén (zip bomb), ảnh/csv/pdf gây lỗi parser, loại extension nguy hiểm, HTML/SVG chứa script khi phục vụ cùng origin. Khi download, thiết lập `Content-Disposition`, `X-Content-Type-Options: nosniff` và cache policy phù hợp.
7. **Chú ý memory/temp disk:** nhiều upload cùng lúc có thể hết temp disk hoặc RAM; giám sát dung lượng, lỗi I/O, số upload đang hoạt động và thời gian xử lý. Temp storage trong container có thể bị xóa khi pod restart.
8. **Bảo vệ metadata và idempotency:** lưu file và record DB có thể thất bại ở hai bước khác nhau. Thiết kế xử lý orphan files, retries và IDs để tránh upload lặp.

**Cần ghi nhớ:** “đúng multipart” mới chỉ xác nhận parser đọc được body; việc lưu và phục vụ file an toàn đòi nhiều kiểm soát độc lập.

## 13. Lỗi HTTP thường gặp và cách tìm nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| **400 Bad Request**, thiếu part | `@RequestPart("file")` nhưng client gửi `name="upload"` hoặc không gửi file | Xem `Content-Disposition name` từng part; khớp chính xác annotation |
| **400** khi parse | Boundary thiếu/khác giữa header và body, multipart body bị cắt | Đừng tự đặt Content-Type của `FormData`; xem raw request |
| **415 Unsupported Media Type** | Gửi JSON toàn body đến endpoint `consumes=multipart/form-data` | Xem header ngoài và `consumes` |
| **415** tại JSON part | Metadata là text/plain/octet-stream nhưng controller cần DTO từ JSON | Đặt `Content-Type: application/json` trên **part metadata** |
| **413 Payload Too Large** | Vượt giới hạn proxy/server/multipart, hoặc gateway chặn trước Spring | Xem limit ở từng tầng và log error source |
| **400** với DTO JSON metadata | JSON sai cú pháp, field type không khớp, validation thất bại | Xem exception conversion/validation và payload part |
| **401/403** | Security/filter, CSRF, user không được phép upload | Xem rule Security, session/token, log và CORS |
| **500 / I/O error** | Temp directory không còn dung lượng, lỗi quyền hoặc storage hỏng | Xem disk, filesystem permissions, storage logs |
| File nhận về **0 byte** | Client chọn file rỗng, dùng `-F file=path` thay vì `file=@path`, hoặc đọc sai part | Xem curl syntax, `isEmpty()` và `getSize()` |
| Có form field nhưng file không nhận | HTML thiếu `enctype="multipart/form-data"` hoặc `name` không đúng | Xem DevTools Network, Request payload |
| Lỗi ở WebFlux do buffer | Dùng API reactive sai, `DataBuffer` không được consume/release | Review publisher chain và giới hạn part codec |

**Quy trình điều tra:** kiểm tra HTTP method + URL → header `Content-Type` ngoài → boundary → từng `Content-Disposition name` → per-part Content-Type → annotation controller → container/parser limits → Security → storage. Đặt breakpoint vào controller mà chưa xem raw request dễ bỏ qua lỗi xảy ra từ trước khi controller được gọi.

Đừng ép mọi lỗi thành cùng status. Spring MVC/WebFlux, proxy, server, Bean Validation và exception handler có thể phát body/status cụ thể khác nhau. Hãy quan sát kết quả thực tế rồi gắn lỗi với đúng tầng.

## 14. Đo lường và kiểm thử upload

Để biết API upload đáp ứng tải thật, chỉ đo HTTP 200 là chưa đủ. Cần quan sát:

- **Kích thước**: nhỏ, đúng max size, vượt max size, nhiều part, nhiều file, file rỗng, file lỗi MIME.
- **Thời gian**: thời gian nhận body, parsing, validation, scan, ghi storage, commit metadata và response.
- **Tài nguyên**: heap, direct buffers, temp disk, container I/O, số kết nối, network, timeout.
- **An toàn**: tên tệp chứa `../`, file đuôi `.jpg` nhưng nội dung khác, file nén độc hại, user không có quyền, uploads trùng ID.
- **Khả năng khôi phục**: client ngắt kết nối giữa chừng, retry cùng request, storage fail, pod restart, scan chậm.
- **Response**: 2xx khi đúng, 4xx khi request không hợp lệ/quá giới hạn, 5xx khi sự cố server; thông báo lỗi rõ nhưng không rò rỉ đường dẫn hoặc stack trace.

Ví dụ test case gọn:

| Test | Request | Kết quả cần kiểm tra |
|---|---|---|
| JSON đúng | `Content-Type: application/json` + JSON metadata | Endpoint metadata trả JSON |
| Multipart đúng | File + JSON part có `application/json` | Endpoint upload trả receipt đúng |
| Thiếu part file | Chỉ có metadata | Trả lỗi thiếu part phù hợp |
| Sai outer Content-Type | JSON tới route chỉ chấp nhận multipart | Không route như multipart; thường 415 |
| Metadata part sai media type | Chuỗi JSON nhưng part đánh dấu text/plain | Converter/validation phản ánh sai contract |
| Quá max file size | File > `spring.servlet.multipart.max-file-size` | Bị chặn đúng tầng và không lưu file |
| Tên file không an toàn | `filename="../../a.txt"` | Storage không sử dụng trực tiếp path client |
| WebFlux file lớn | Multi-part payload thực tế | Không giữ toàn file trong memory chỉ vì handler reactive |

## 15. Câu hỏi tự kiểm tra

**1.** Khi gửi một `multipart/form-data` có metadata và file, có đúng là cả body phải mang `Content-Type: application/json`?

**Đáp án:** Không. Content-Type ngoài là `multipart/form-data; boundary=...`; riêng part metadata mang `Content-Type: application/json`.

**2.** Tại sao dùng `fetch(..., { body: formData })` mà không tự đặt multipart Content-Type?

**Đáp án:** Browser phải sinh boundary rồi đưa cùng giá trị vào header và body. Tự đặt Content-Type không có boundary hoặc sai boundary khiến server parse lỗi.

**3.** Trong MVC, khi nào dùng `@RequestBody` thay vì `@RequestPart`?

**Đáp án:** `@RequestBody` cho **toàn bộ body** (ví dụ JSON). `@RequestPart` cho **một phần** trong multipart, có thể deserialize part JSON.

**4.** Có thể gửi hai file cùng part name không?

**Đáp án:** Có. Gửi hai part đều `name="files"` và nhận bằng `List<MultipartFile>` trong MVC.

**5.** `MultipartFile.getOriginalFilename()` có an toàn để dùng làm đường dẫn lưu file không?

**Đáp án:** Không. Giá trị do client cung cấp; sinh tên lưu trữ/ID ở server và bảo vệ path traversal, collisions và phân quyền.

**6.** Trong Spring MVC Boot, `max-file-size=5MB` và `max-request-size=6MB` nghĩa là mỗi file dưới 5MB chắc chắn upload nhiều file thoải mái?

**Đáp án:** Không. Tổng các file cùng part khác và multipart overhead phải nằm trong **6MB** (và còn có các giới hạn proxy/container).

**7.** Khi API dùng WebFlux, có nhận file bằng Spring MVC `MultipartFile` như ví dụ Servlet không?

**Đáp án:** Không phải kiểu handler chính của WebFlux. Dùng `FilePart`/`Part` hoặc `Flux<PartEvent>` cho multipart reactive.

**8.** Multipart có bắt buộc để download một PDF không?

**Đáp án:** Không. Một response GET có thể gửi PDF với `Content-Type: application/pdf` và `Content-Disposition: attachment`; multipart chỉ cần khi giao thức nghiệp vụ có nhiều part.

## 16. Tài liệu tham khảo

- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [Spring Framework — MVC Multipart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — MVC @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux Multipart Content và PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/)
- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)

**Điểm cốt lõi:** JSON biểu diễn **một nội dung có cấu trúc**; multipart biểu diễn **nhiều phần có thể khác loại nội dung** trong một HTTP body. Hợp đồng upload đúng phải thống nhất outer Content-Type, boundary, field names, per-part media types, giới hạn parser và quy tắc lưu file an toàn.
