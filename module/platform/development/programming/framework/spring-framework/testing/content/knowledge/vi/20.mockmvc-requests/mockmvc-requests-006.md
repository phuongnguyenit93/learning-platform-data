# Multipart request với tệp và các phần dữ liệu

Nhiều API cần nhận một tệp cùng dữ liệu mô tả trong cùng một HTTP request. Ví dụ, người dùng tải tài liệu lên kèm tiêu đề, loại tài liệu hoặc thông tin phân loại. Giao thức thường dùng cho trường hợp này là `multipart/form-data`: request được chia thành nhiều phần (part), mỗi phần có tên, header và nội dung riêng.

Spring MVC hỗ trợ binding multipart request vào `MultipartFile`, `Part`, các tham số biểu mẫu và đối tượng Java. Spring Test cung cấp `MockMvcRequestBuilders.multipart(...)` để tạo request multipart giả lập. Ta có thể thêm tệp bằng `MockMultipartFile`, thêm các part dữ liệu bằng `MockPart`, sau đó gửi request qua `MockMvc` và kiểm tra controller xử lý từng phần như mong đợi.

## 1. Cấu trúc của multipart request

Một request `multipart/form-data` chứa nhiều phần được phân tách bởi boundary. Mỗi phần có header riêng, thường bao gồm `Content-Disposition` với tên trường và có thể có tên tệp; phần dữ liệu cũng có thể khai báo `Content-Type`.

Ví dụ về cấu trúc khái niệm:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary123

------Boundary123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Q4 report","category":"FINANCE"}
------Boundary123
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<binary file content>
------Boundary123--
```

Request có hai part:

- `metadata` chứa JSON mô tả tài liệu. Part này có thể được Spring chuyển đổi thành một DTO bằng `HttpMessageConverter`.
- `file` chứa nội dung tệp, tên tệp gốc và content type. Spring có thể bind nó thành `MultipartFile`.

Tên part là một phần của hợp đồng HTTP. Nếu controller yêu cầu `@RequestPart("file")` thì tên part trong test phải là `file`. Tên trường sai thường khiến Spring không tìm thấy tham số bắt buộc và trả về lỗi request.

## 2. Tạo multipart request bằng `MockMvc`

Spring MVC Test cung cấp request builder `multipart(...)`. Builder này tạo một multipart request giả lập để gửi qua `MockMvc`.

Tệp được tạo bằng `MockMultipartFile`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.mock.web.MockMultipartFile;
import org.springframework.http.MediaType;

MockMultipartFile file = new MockMultipartFile(
        "file",
        "report.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "PDF test content".getBytes(StandardCharsets.UTF_8)
);
```

Các đối số lần lượt là:

1. `name`: tên part mà controller sẽ nhận, ví dụ `file`.
2. `originalFilename`: tên tệp do client gửi, ví dụ `report.pdf`.
3. `contentType`: kiểu nội dung của tệp, ví dụ `application/pdf`.
4. `content`: byte array chứa nội dung tệp.

Có thể dùng constructor nhận `InputStream` khi dữ liệu test được đọc từ nguồn stream. Với bài kiểm thử nhỏ, byte array thường giúp nội dung đầu vào rõ ràng và dễ kiểm soát.

Sau đó thêm file vào request:

```java
mockMvc.perform(multipart("/api/documents")
                .file(file)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk());
```

`multipart(...)` mặc định tạo request POST dạng multipart. `file(...)` thêm một file part vào request. `MockMvc` chuyển request qua Spring MVC để controller xử lý mà không cần mở HTTP server.

## 3. Controller nhận tệp bằng `MultipartFile`

`MultipartFile` là abstraction của Spring để làm việc với nội dung một tệp đã được phân tích từ multipart request. Một số phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getName()` | Tên trường/part trong form, chẳng hạn `file`. |
| `getOriginalFilename()` | Tên tệp gốc client gửi lên. |
| `getContentType()` | Content type được khai báo cho tệp. |
| `isEmpty()` | Cho biết không có tệp hoặc nội dung tệp rỗng. |
| `getSize()` | Kích thước nội dung theo byte. |
| `getBytes()` | Đọc toàn bộ nội dung thành byte array. |
| `getInputStream()` | Đọc nội dung qua stream. |
| `transferTo(...)` | Ghi nội dung vào đích lưu trữ. |

Ví dụ controller nhận một tệp và trường mô tả dạng text:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    UploadResponse upload(
            @RequestParam("description") String description,
            @RequestParam("file") MultipartFile file
    ) {
        return new UploadResponse(
                description,
                file.getOriginalFilename(),
                file.getContentType(),
                file.getSize()
        );
    }
}

record UploadResponse(
        String description,
        String filename,
        String contentType,
        long size
) {
}
```

`consumes = MediaType.MULTIPART_FORM_DATA_VALUE` giới hạn endpoint nhận request có content type multipart/form-data. `@RequestParam` bind trường biểu mẫu `description` và file part `file` vào tham số tương ứng.

## 4. Gửi tệp cùng trường biểu mẫu dạng text

Khi dữ liệu mô tả chỉ là các trường text đơn giản, có thể dùng `.param(...)` trên multipart request builder:

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void shouldUploadFileWithDescription() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "report.pdf",
            MediaType.APPLICATION_PDF_VALUE,
            "PDF test content".getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/documents")
                    .file(file)
                    .param("description", "Quarterly report")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.description").value("Quarterly report"))
            .andExpect(jsonPath("$.filename").value("report.pdf"))
            .andExpect(jsonPath("$.contentType").value("application/pdf"))
            .andExpect(jsonPath("$.size").value(16));
}
```

`param("description", ...)` đặt giá trị tham số trong request giả lập. Đây là cách gọn để kiểm tra controller nhận trường form thông qua `@RequestParam`. Trong multipart form thực tế, các trường text cũng được biểu diễn như các phần dữ liệu của form và được servlet multipart processing đưa vào request parameter map.

Nếu muốn kiểm tra một phần dữ liệu như một `Part` thực sự, đặc biệt khi part có header hoặc content type riêng, hãy tạo `MockPart` và thêm bằng `.part(...)`.

## 5. Gửi JSON metadata cùng file bằng `MockPart`

Một API thường nhận metadata có cấu trúc, chẳng hạn tiêu đề, category hoặc thông tin quyền truy cập. Khi part metadata có content type `application/json`, có thể dùng `@RequestPart` để Spring chuyển JSON thành DTO.

DTO metadata:

```java
public record DocumentMetadata(String title, String category) {
}
```

Controller:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    UploadResponse upload(
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("file") MultipartFile file
    ) {
        return new UploadResponse(
                metadata.title(),
                metadata.category(),
                file.getOriginalFilename(),
                file.getContentType(),
                file.getSize()
        );
    }
}

record UploadResponse(
        String title,
        String category,
        String filename,
        String contentType,
        long size
) {
}
```

Tạo JSON part bằng `MockPart`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockPart;

MockPart metadataPart = new MockPart(
        "metadata",
        "{\"title\":\"Q4 report\",\"category\":\"FINANCE\"}"
                .getBytes(StandardCharsets.UTF_8)
);
metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

Tên `metadata` khớp với `@RequestPart("metadata")`. Header `Content-Type: application/json` báo cho Spring biết part này cần được đọc qua message converter JSON. Nếu content type thiếu hoặc khai báo sai, Spring có thể không chọn được converter phù hợp để chuyển part thành `DocumentMetadata`.

Ghép metadata và file vào cùng request:

```java
MockMultipartFile filePart = new MockMultipartFile(
        "file",
        "quarterly-report.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "sample pdf bytes".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
                .file(filePart)
                .part(metadataPart)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Q4 report"))
        .andExpect(jsonPath("$.category").value("FINANCE"))
        .andExpect(jsonPath("$.filename").value("quarterly-report.pdf"));
```

Trong ví dụ này:

- `MockMultipartFile` biểu diễn file part với tên tệp, content type và byte content.
- `MockPart` biểu diễn metadata part có header `Content-Type` riêng.
- `multipart(...).file(...).part(...)` tạo một request chứa cả hai phần.
- `@RequestPart` yêu cầu Spring giải quyết từng part theo kiểu tham số. Với `MultipartFile`, Spring cung cấp abstraction file; với DTO metadata, Spring dùng `HttpMessageConverter` dựa trên content type của part.

Test này kiểm tra cả multipart binding lẫn khả năng chuyển JSON part thành object. Để phần JSON hoạt động, test cần có JSON converter tương ứng, thường là Jackson khi dùng Spring Boot web starter.

## 6. Phân biệt `@RequestParam`, `@RequestPart` và `Part`

Các annotation có thể cùng xuất hiện trên endpoint multipart nhưng mục đích binding không hoàn toàn giống nhau.

| Cách nhận dữ liệu | Cách dùng thường gặp | Hành vi chính |
| --- | --- | --- |
| `@RequestParam("description") String description` | Trường form dạng text hoặc tham số request. | Lấy giá trị tham số theo tên từ request parameter map. |
| `@RequestParam("file") MultipartFile file` | File upload theo tên trường. | Spring phân giải file part thành `MultipartFile`. |
| `@RequestPart("metadata") Metadata metadata` | JSON/XML hoặc dữ liệu có content type cần message converter. | Đọc nội dung part và chuyển đổi theo content type. |
| `@RequestPart("file") MultipartFile file` | File upload trong endpoint nhận nhiều part. | Phân giải file part thành `MultipartFile`. |
| `Part` hoặc `@RequestPart("file") Part file` | Khi cần làm việc gần với Servlet Part API. | Truy cập tên, header, kích thước, stream và thao tác của part. |

Với `@RequestParam`, Spring chủ yếu xử lý giá trị như request parameter. Với `@RequestPart`, Spring xem nội dung của part và dùng `HttpMessageConverter` khi kiểu tham số cần chuyển đổi, tương tự cách xử lý `@RequestBody`. Vì thế, `@RequestPart` đặc biệt hữu ích khi metadata là JSON bên cạnh file binary.

Nếu controller nhận một form object qua `@ModelAttribute`, Spring có thể bind các trường form và `MultipartFile` vào các thuộc tính của object. Cách này tiện cho biểu mẫu có nhiều trường đơn giản. Khi cần JSON metadata có cấu trúc riêng và file độc lập, `@RequestPart` giúp thể hiện rõ ranh giới của từng part.

## 7. Kiểm tra nhiều tệp trong cùng request

Một form có thể gửi nhiều file với cùng tên trường, chẳng hạn `attachments`. Controller có thể nhận một danh sách `MultipartFile`:

```java
@PostMapping(
        path = "/api/documents/attachments",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
UploadBatchResponse uploadMany(
        @RequestParam("attachments") List<MultipartFile> attachments
) {
    List<String> filenames = attachments.stream()
            .map(MultipartFile::getOriginalFilename)
            .toList();
    return new UploadBatchResponse(filenames);
}

record UploadBatchResponse(List<String> filenames) {
}
```

Trong test, gọi `.file(...)` nhiều lần với cùng tên part:

```java
MockMultipartFile first = new MockMultipartFile(
        "attachments", "one.txt", MediaType.TEXT_PLAIN_VALUE,
        "first".getBytes(StandardCharsets.UTF_8)
);
MockMultipartFile second = new MockMultipartFile(
        "attachments", "two.txt", MediaType.TEXT_PLAIN_VALUE,
        "second".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents/attachments")
                .file(first)
                .file(second)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.filenames[0]").value("one.txt"))
        .andExpect(jsonPath("$.filenames[1]").value("two.txt"));
```

Tên part phải khớp với tên trong `@RequestParam` hoặc `@RequestPart`. Nếu controller nhận `List<MultipartFile>` nhưng test gửi hai tên part khác nhau, binding có thể không tạo ra danh sách như mong đợi.

## 8. Kiểm tra trường hợp thiếu tệp, tệp rỗng và metadata không hợp lệ

Kiểm thử multipart không chỉ cần tình huống thành công. API upload thường có quy tắc về part bắt buộc, kích thước tối thiểu, định dạng hoặc metadata.

### Tệp rỗng

`MockMultipartFile` có thể được tạo với byte array rỗng:

```java
MockMultipartFile emptyFile = new MockMultipartFile(
        "file",
        "empty.txt",
        MediaType.TEXT_PLAIN_VALUE,
        new byte[0]
);
```

Controller có thể kiểm tra `file.isEmpty()` và trả lỗi phù hợp. Test gửi file rỗng rồi xác nhận status và error response theo hợp đồng API. Điều này kiểm tra logic ứng dụng xử lý nội dung rỗng.

### Thiếu part bắt buộc

Nếu controller khai báo `@RequestPart("file") MultipartFile file` với `required = true` mặc định, request không có part `file` sẽ không thỏa mãn tham số bắt buộc. Có thể kiểm tra bằng cách gửi request chỉ có metadata hoặc request multipart không có file.

```java
mockMvc.perform(multipart("/api/documents")
                .part(metadataPart))
        .andExpect(status().isBadRequest());
```

Status cụ thể có thể thay đổi nếu ứng dụng có `@ControllerAdvice` chuyển lỗi binding sang response riêng. Test nên xác nhận hợp đồng lỗi mà ứng dụng thực sự công bố.

### Metadata không hợp lệ

Nếu DTO dùng Bean Validation:

```java
public record DocumentMetadata(
        @NotBlank String title,
        @NotBlank String category
) {
}
```

Controller có thể khai báo `@Valid @RequestPart("metadata") DocumentMetadata metadata`. Test gửi metadata thiếu `title`, hoặc `title` rỗng, rồi xác nhận lỗi validation. Để validation hoạt động, test cần Bean Validation provider và cấu hình validator tương ứng. Nếu dùng standalone MockMvc, hãy đăng ký validator phù hợp trong builder.

## 9. Kiểm tra nội dung file và tương tác với service

Một assertion chỉ kiểm tra `originalFilename` hoặc `size` chưa chứng minh controller chuyển đúng byte content xuống tầng nghiệp vụ. Nếu controller gọi service để lưu file, có thể dùng Mockito `ArgumentCaptor` hoặc `verify` để kiểm tra dữ liệu được truyền đi.

Ví dụ, service có phương thức:

```java
public interface DocumentStorageService {
    void store(String title, MultipartFile file);
}
```

Sau khi gửi request, test có thể bắt tham số file và so sánh nội dung:

```java
ArgumentCaptor<MultipartFile> fileCaptor =
        ArgumentCaptor.forClass(MultipartFile.class);

verify(documentStorageService).store(
        eq("Q4 report"),
        fileCaptor.capture()
);

assertThat(fileCaptor.getValue().getOriginalFilename())
        .isEqualTo("quarterly-report.pdf");
assertThat(fileCaptor.getValue().getBytes())
        .containsExactly("sample pdf bytes".getBytes(StandardCharsets.UTF_8));
```

Đoạn trên cần static import `eq` và AssertJ `assertThat`. Nếu service đọc stream hoặc gọi `transferTo`, test có thể xác nhận hành vi tương ứng bằng một fake storage service hoặc mock phù hợp. Mục tiêu là kiểm tra dữ liệu multipart được chuyển đúng qua ranh giới controller/service.

## 10. Giới hạn của multipart request trong MockMvc

`MockMvcRequestBuilders.multipart(...)` tạo một `MockMultipartHttpServletRequest` đã có các file/part được gắn vào. Request này giúp kiểm tra cách Spring MVC bind và xử lý multipart data sau khi dữ liệu đã được biểu diễn thành các part.

Nó không gửi một chuỗi HTTP multipart thô qua socket và không yêu cầu servlet container phân tích boundary thật. Vì vậy, test với MockMvc phù hợp để kiểm tra:

- Controller có nhận đúng tên part và kiểu tham số hay không.
- JSON metadata có được chuyển đổi bằng message converter hay không.
- File có đúng tên, content type, kích thước và nội dung trong request giả lập hay không.
- Logic ứng dụng phản ứng thế nào với file rỗng, part thiếu hoặc metadata không hợp lệ.

Test này không xác nhận trực tiếp:

- Servlet container phân tích multipart boundary và header từ raw HTTP body đúng hay không.
- Giới hạn `max-file-size` hoặc `max-request-size` của container được áp dụng thế nào.
- File tạm được ghi xuống đĩa, dọn dẹp hoặc quản lý vòng đời ra sao.
- Reverse proxy, gateway hoặc mạng truyền tải file lớn có hoạt động đúng hay không.

Nếu cần kiểm tra các hành vi phụ thuộc container, hãy bổ sung bài kiểm thử tích hợp khởi động server thật, gửi multipart HTTP qua client như `TestRestTemplate`, `WebTestClient` phù hợp hoặc HTTP client khác. Trong Spring Boot, có thể dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` để chạy server trên cổng ngẫu nhiên. Khi đó request multipart được truyền qua HTTP stack thực tế của ứng dụng.

## 11. Lưu ý về bảo mật và kiểm tra tệp

Tên tệp, phần mở rộng và content type do client gửi lên đều là dữ liệu đầu vào. Không nên xem `getOriginalFilename()` hoặc `getContentType()` là bằng chứng đáng tin cậy rằng nội dung tệp an toàn. Ứng dụng nên xác thực theo yêu cầu nghiệp vụ, giới hạn kích thước, kiểm tra nội dung khi cần và tạo tên lưu trữ an toàn ở server.

Trong test controller, có thể tạo file giả với tên như `../../outside.txt` hoặc content type không đúng với nội dung để kiểm tra quy tắc xử lý tên tệp và loại file. Việc kiểm tra này nên tập trung vào hành vi ứng dụng như từ chối hoặc chuẩn hóa dữ liệu. Kiểm tra parser, giới hạn upload và lưu trữ thực tế cần test tích hợp phù hợp với hạ tầng.

Nếu endpoint được bảo vệ bởi Spring Security, request POST có thể cần CSRF token khi filter chain được tích hợp trong `MockMvc`. Với dependency Spring Security Test, có thể thêm `.with(csrf())` vào request builder. Nếu không tích hợp filter chain trong test standalone, CSRF filter có thể không tham gia; hãy xác định rõ test đang kiểm tra controller hay cả lớp bảo mật.

## 12. Lỗi thường gặp khi viết multipart test

**Tên part không khớp với tham số controller.**

Nếu controller dùng `@RequestPart("metadata")`, test phải thêm part tên `metadata`. Với file, tên truyền vào `MockMultipartFile` phải trùng với tên binding.

**Dùng `.file(...)` cho dữ liệu JSON nhưng không khai báo content type.**

`MockMultipartFile` biểu diễn một file part. Nếu metadata là JSON cần chuyển thành DTO, nên dùng `MockPart` và đặt `Content-Type: application/json`, sau đó bind bằng `@RequestPart`.

**Dùng `.param(...)` rồi mong đợi có header riêng của một part.**

`.param(...)` thêm request parameter vào request giả lập; nó không tạo một `Part` có header riêng. Khi cần kiểm tra content type hoặc header của từng phần, hãy dùng `.part(...)` với `MockPart`.

**Quên JSON message converter.**

`@RequestPart` với DTO yêu cầu converter tương ứng. Nếu standalone setup không có Jackson converter, Spring không thể chuyển JSON part thành object. Hãy thêm converter hoặc dùng context có cấu hình MVC phù hợp.

**Kiểm tra file chỉ bằng tên.**

Tên tệp không chứng minh byte content đúng. Khi controller chuyển file cho service, hãy xác nhận nội dung byte hoặc hành vi đọc stream nếu đó là yêu cầu cần kiểm chứng.

**Cho rằng MockMvc kiểm tra được giới hạn upload của server.**

Mock multipart request không chạy qua parser multipart của servlet container. Dùng test với server thật khi cần kiểm tra giới hạn kích thước, xử lý boundary, lưu trữ tệp tạm hoặc hành vi hạ tầng.

## 13. Quy trình kiểm thử multipart bằng MockMvc

Một bài kiểm thử multipart có thể triển khai theo trình tự:

1. Xác định hợp đồng endpoint: tên part, kiểu dữ liệu, content type, part bắt buộc và response mong đợi.
2. Tạo `MockMultipartFile` cho từng tệp, khai báo đúng tên, tên tệp gốc, content type và byte content.
3. Tạo `MockPart` cho dữ liệu có header hoặc content type riêng, chẳng hạn JSON metadata.
4. Dùng `multipart("/path")` để tạo request, sau đó thêm `.file(...)`, `.part(...)` hoặc `.param(...)` phù hợp.
5. Gửi request qua `mockMvc.perform(...)`.
6. Kiểm tra status, response content type, body và các tương tác với service.
7. Bổ sung tình huống lỗi như thiếu part, file rỗng, metadata không hợp lệ hoặc nhiều file.
8. Dùng server thật nếu mục tiêu bao gồm quá trình parse multipart và giới hạn upload của servlet container.

## Kết luận

Để kiểm thử endpoint nhận file cùng dữ liệu multipart, dùng `MockMvcRequestBuilders.multipart(...)` kết hợp `MockMultipartFile` cho file và `MockPart` cho các part có header hoặc content type riêng. `@RequestParam` phù hợp với trường form và file binding thông thường; `@RequestPart` phù hợp khi cần chuyển đổi nội dung part như JSON thành DTO.

MockMvc giúp kiểm tra binding, message conversion và logic controller trong môi trường servlet giả lập. Khi cần xác nhận raw multipart parsing, giới hạn kích thước, file tạm hoặc hành vi của servlet container, cần một bài kiểm thử tích hợp gửi request qua server thật.
