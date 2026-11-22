# Tải tệp, dữ liệu nhị phân và `Content-Disposition`

Không phải response API nào cũng là JSON. Nhiều endpoint cần trả về PDF, ảnh, CSV, Excel, ZIP hoặc một luồng dữ liệu nhị phân. Với Spring Boot, controller có thể trả dữ liệu dưới dạng `Resource`, `byte[]` hoặc `StreamingResponseBody`; HTTP response cần khai báo đúng media type và các header mô tả cách trình duyệt xử lý tệp. Trong tài liệu OpenAPI, response body được mô tả theo media type và schema nhị phân, còn `Content-Disposition` được khai báo như một response header.

Với `springdoc-openapi`, việc khai báo rõ các thông tin này giúp Swagger UI, client generator và người tiêu dùng API hiểu endpoint trả tệp như thế nào. Hợp đồng cũng cần mô tả các response lỗi, bởi endpoint tải tệp vẫn có thể trả `404`, `403` hoặc lỗi máy chủ dưới dạng JSON.

## 1. Response tải tệp khác response JSON

Một response JSON thường có body là object hoặc array được serialize từ DTO. Response tải tệp có body là các byte của nội dung file. Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-2026.pdf"
Content-Length: 48291

%PDF-1.7...
```

Các header quan trọng:

| Header | Vai trò |
|---|---|
| `Content-Type` | Cho biết media type của nội dung, ví dụ `application/pdf`, `text/csv` hoặc `application/octet-stream` |
| `Content-Disposition` | Gợi ý trình duyệt hiển thị nội dung hay tải xuống, đồng thời có thể cung cấp tên tệp |
| `Content-Length` | Cho biết số byte của body nếu kích thước đã biết |
| `Cache-Control` | Kiểm soát việc lưu cache; đặc biệt quan trọng với tài liệu riêng tư |
| `Content-Range` | Mô tả đoạn byte được trả về trong response một phần |
| `Accept-Ranges` | Cho biết server hỗ trợ yêu cầu tải theo byte range khi thực sự có triển khai |

`Content-Disposition` là metadata của HTTP response, không nằm trong nội dung file và không phải schema của body. Tương tự, `Content-Type` được thể hiện trong phần `content` của Response Object trong OpenAPI thông qua media type, không cần khai báo lại như một header thông thường.

## 2. Chọn kiểu trả dữ liệu trong Spring MVC

Spring MVC hỗ trợ nhiều kiểu trả response. Lựa chọn phụ thuộc kích thước file, nguồn dữ liệu và cách ứng dụng quản lý stream.

| Kiểu trả về | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| `ResponseEntity<Resource>` | Tệp nằm trên filesystem, storage hoặc một nguồn có thể biểu diễn bằng `Resource` | Có thể cung cấp content type, content length và disposition qua header |
| `ResponseEntity<byte[]>` | Nội dung nhỏ đã được nạp vào bộ nhớ | Đơn giản nhưng toàn bộ dữ liệu nằm trong heap |
| `ResponseEntity<ByteArrayResource>` | Dữ liệu nhỏ đã có sẵn dưới dạng byte array nhưng muốn dùng abstraction `Resource` | Vẫn tiêu thụ bộ nhớ theo kích thước file |
| `ResponseEntity<InputStreamResource>` | Dữ liệu được đọc từ một stream có sẵn | Stream thường chỉ đọc một lần; cần cẩn trọng khi tính content length |
| `ResponseEntity<StreamingResponseBody>` | Tệp lớn hoặc dữ liệu được tạo/đọc tuần tự | Ghi trực tiếp vào output stream, không cần giữ toàn bộ file trong heap |

Với file lớn, không nên đọc toàn bộ nội dung vào `byte[]` chỉ để trả response. Có thể dùng `FileSystemResource` hoặc `StreamingResponseBody` để giảm áp lực bộ nhớ. Với stream chỉ đọc một lần, tránh gọi các thao tác có thể tiêu thụ stream trước khi response được ghi.

## 3. `Content-Disposition`: `attachment` và `inline`

Header `Content-Disposition` mô tả cách nội dung được cung cấp trong response HTTP.

### `attachment`

`attachment` yêu cầu trình duyệt xem nội dung như một tệp cần tải xuống. Tham số `filename` gợi ý tên file:

```http
Content-Disposition: attachment; filename="report.csv"
```

Đây là lựa chọn phổ biến cho endpoint tải báo cáo, hóa đơn, bản sao lưu hoặc tài liệu mà người dùng cần lưu về máy.

### `inline`

`inline` cho phép trình duyệt hiển thị nội dung ngay trong cửa sổ nếu trình duyệt hỗ trợ media type đó:

```http
Content-Disposition: inline; filename="manual.pdf"
```

Ví dụ, PDF hoặc ảnh có thể được hiển thị trực tiếp. `inline` chỉ là gợi ý xử lý; trình duyệt, plugin, chính sách bảo mật và `Content-Type` vẫn quyết định khả năng hiển thị thực tế.

### Tên tệp và ký tự Unicode

Tên tệp có thể chứa dấu tiếng Việt hoặc ký tự ngoài ASCII. Cần xử lý encoding đúng theo quy tắc HTTP, thường thông qua tham số `filename*` theo RFC 5987/RFC 6266 cùng tên dự phòng `filename` khi cần. Không tự ghép chuỗi header bằng cách nối trực tiếp tên file chưa kiểm tra.

Spring cung cấp `ContentDisposition` builder để tạo header:

```java
import org.springframework.http.ContentDisposition;
import java.nio.charset.StandardCharsets;

ContentDisposition disposition = ContentDisposition.attachment()
        .filename("hoa-don-thang-11.pdf", StandardCharsets.UTF_8)
        .build();

String headerValue = disposition.toString();
```

Builder xử lý việc biểu diễn tên tệp theo quy tắc của framework. Hãy kiểm tra header thực tế với trình duyệt và client mục tiêu, đặc biệt khi cần hỗ trợ tên file Unicode.

## 4. Trả file bằng `ResponseEntity<Resource>`

Đây là cách phổ biến khi file đã tồn tại trong filesystem hoặc storage abstraction. Ví dụ dưới đây giả định `fileService` xác thực quyền truy cập và cung cấp metadata cùng `Resource` có thể đọc.

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DocumentController {

    private final FileService fileService;

    DocumentController(FileService fileService) {
        this.fileService = fileService;
    }

    @GetMapping("/api/files/{fileId}/download")
    ResponseEntity<Resource> download(@PathVariable UUID fileId) throws IOException {
        StoredFile file = fileService.findReadableFile(fileId);
        Resource resource = fileService.openResource(fileId);

        if (!resource.exists() || !resource.isReadable()) {
            throw new FileNotFoundException("Không tìm thấy tệp");
        }

        String safeName = safeDownloadName(file.downloadName());
        ContentDisposition disposition = ContentDisposition.attachment()
                .filename(safeName, StandardCharsets.UTF_8)
                .build();

        MediaType mediaType = MediaType.parseMediaType(file.contentType());

        return ResponseEntity.ok()
                .contentType(mediaType)
                .contentLength(resource.contentLength())
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .body(resource);
    }

    private String safeDownloadName(String suppliedName) {
        if (suppliedName == null || suppliedName.isBlank()) {
            return "download.bin";
        }
        String leaf = suppliedName.replace('\\', '/');
        leaf = leaf.substring(leaf.lastIndexOf('/') + 1);
        leaf = leaf.replaceAll("[\\r\\n\\p{Cntrl}]", "_").trim();
        return leaf.isBlank() ? "download.bin" : leaf;
    }
}
```

`FileService` và `StoredFile` là các kiểu minh họa thuộc ứng dụng; `FileNotFoundException` là exception chuẩn của JDK. Trong triển khai thực tế:

- `findReadableFile` phải kiểm tra người dùng có quyền đọc tệp.
- ID công khai nên được ánh xạ sang vị trí lưu trữ thông qua service; không lấy đường dẫn filesystem tùy ý từ request.
- Tên file phải được làm sạch trước khi đưa vào header, loại bỏ đường dẫn và ký tự điều khiển.
- `contentType` phải lấy từ metadata đáng tin cậy hoặc được xác định bằng quy tắc kiểm tra nội dung; không mặc định tin mọi giá trị do client tải lên.
- Chỉ đặt `Content-Length` khi biết chính xác kích thước mà không tiêu thụ stream ngoài ý muốn.

Nếu loại file cố định, có thể khai báo `produces`, ví dụ `produces = MediaType.APPLICATION_PDF_VALUE`. Nếu một endpoint trả nhiều loại file tùy theo metadata, hãy chọn content type tại runtime và mô tả đầy đủ các media type được hỗ trợ trong OpenAPI.

## 5. Trả dữ liệu nhỏ bằng `byte[]`

Khi nội dung nhỏ và đã được tạo trong bộ nhớ, có thể trả trực tiếp `byte[]`:

```java
@GetMapping("/api/reports/summary")
ResponseEntity<byte[]> downloadSummary() {
    byte[] content = reportService.createSummaryCsv();

    ContentDisposition disposition = ContentDisposition.attachment()
            .filename("summary.csv", StandardCharsets.UTF_8)
            .build();

    return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/csv"))
            .contentLength(content.length)
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .body(content);
}
```

`byte[]` dễ dùng và kích thước có sẵn để đặt `Content-Length`. Tuy nhiên, file được giữ trong bộ nhớ ứng dụng; với nhiều request đồng thời hoặc file lớn, tổng lượng heap có thể tăng nhanh. Chỉ dùng cách này khi kích thước được giới hạn phù hợp.

## 6. Streaming file lớn bằng `StreamingResponseBody`

`StreamingResponseBody` cho phép ghi dữ liệu vào response output stream theo từng phần. Ví dụ:

```java
@GetMapping("/api/exports/{exportId}/download")
ResponseEntity<StreamingResponseBody> downloadExport(
        @PathVariable UUID exportId) {

    ExportMetadata metadata = exportService.getReadableExport(exportId);
    StreamingResponseBody body = outputStream ->
            exportService.copyTo(exportId, outputStream);

    ContentDisposition disposition = ContentDisposition.attachment()
            .filename(safeDownloadName(metadata.fileName()), StandardCharsets.UTF_8)
            .build();

    return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(metadata.contentType()))
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .body(body);
}
```

Ví dụ bỏ qua `Content-Length` vì kích thước có thể chưa biết trước. Khi server và nguồn dữ liệu biết kích thước chính xác, có thể đặt header này; nếu không, để HTTP server quản lý framing của response.

Khi dùng streaming:

- Không đóng `OutputStream` do Spring cung cấp; framework quản lý vòng đời stream.
- Đóng stream nguồn trong service bằng try-with-resources.
- Xử lý lỗi đọc/ghi và log theo cách không làm lộ dữ liệu nhạy cảm.
- Không đặt status `200` rồi mới phát hiện quyền truy cập không hợp lệ trong callback; xác thực và kiểm tra quyền trước khi bắt đầu ghi body.
- Cấu hình executor và timeout phù hợp với thời lượng tải.
- Kiểm thử tải đồng thời, client ngắt kết nối và lỗi xảy ra giữa chừng.

Với `InputStreamResource`, cần chú ý stream có thể chỉ đọc một lần. Việc framework hoặc code gọi `contentLength()` có thể làm tiêu thụ stream tùy loại resource. Với file trên đĩa, `FileSystemResource` thường thuận tiện hơn vì có thể truy cập metadata và mở stream theo yêu cầu.

## 7. Mô tả binary response trong OpenAPI

OpenAPI mô tả response body theo media type. Với tài liệu OpenAPI 3.0, quy ước phổ biến cho nội dung file nhị phân là schema `type: string`, `format: binary`.

Ví dụ response PDF:

```yaml
paths:
  /api/files/{fileId}/download:
    get:
      summary: Tải tệp PDF
      parameters:
        - name: fileId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Nội dung tệp PDF
          headers:
            Content-Disposition:
              description: Tên tệp được gợi ý cho thao tác tải xuống
              schema:
                type: string
                example: 'attachment; filename="invoice.pdf"'
            Content-Length:
              description: Kích thước body tính bằng byte nếu được cung cấp
              schema:
                type: integer
                format: int64
          content:
            application/pdf:
              schema:
                type: string
                format: binary
        '404':
          description: Không tìm thấy tệp
```

Với file bất kỳ không có media type cụ thể, có thể dùng `application/octet-stream`. Với CSV, dùng `text/csv`; với ZIP, dùng `application/zip`; với ảnh, dùng media type phù hợp như `image/png`.

Trong OpenAPI 3.1, Schema Object dựa trên JSON Schema 2020-12 và cách mô tả nội dung nhị phân có những khác biệt so với quy ước `format: binary` của OpenAPI 3.0. Các keyword như `contentMediaType` và `contentEncoding` mô tả media type hoặc encoding của nội dung dạng chuỗi khi phù hợp; chúng không thay thế media type của response trong `content`. Hỗ trợ của Swagger UI, validator và client generator cũng khác nhau; cần kiểm tra phiên bản OpenAPI thực tế mà springdoc xuất cùng bộ công cụ dự án.

## 8. Khai báo response binary và header bằng annotation springdoc

Có thể mô tả response file ngay trên controller bằng `@ApiResponse`, `@Content`, `@Schema` và `@Header`.

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.headers.Header;

@Operation(summary = "Tải hóa đơn PDF")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Nội dung hóa đơn PDF",
        headers = {
            @Header(
                name = "Content-Disposition",
                description = "Tên file được trình duyệt sử dụng khi tải xuống",
                schema = @Schema(
                    type = "string",
                    example = "attachment; filename=\"invoice.pdf\""
                )
            ),
            @Header(
                name = "Content-Length",
                description = "Kích thước nội dung tính bằng byte",
                schema = @Schema(type = "integer", format = "int64")
            )
        },
        content = @Content(
            mediaType = "application/pdf",
            schema = @Schema(type = "string", format = "binary")
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy hóa đơn",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(responseCode = "403", description = "Không có quyền tải hóa đơn")
})
@GetMapping("/api/invoices/{invoiceId}/download")
ResponseEntity<Resource> downloadInvoice(@PathVariable UUID invoiceId) {
    // Lấy Resource và trả về cùng Content-Type, Content-Disposition phù hợp.
    throw new UnsupportedOperationException("Ví dụ minh họa");
}
```

`ApiError` là DTO lỗi minh họa của ứng dụng. Các điểm cần lưu ý:

- `content` mô tả body theo media type; `application/pdf` hoặc `application/octet-stream` là khóa media type.
- `schema` dạng binary mô tả nội dung file; không dùng schema của DTO JSON cho body nhị phân.
- `headers` mô tả `Content-Disposition` và `Content-Length` nếu endpoint cung cấp chúng.
- `Content-Type` đã được biểu diễn bằng media type trong `content`; không khai báo trùng như header thông thường.
- Response lỗi có thể có schema JSON riêng, độc lập với response thành công dạng file.

Nếu controller trả `Resource`, springdoc có thể suy luận response không đúng với ý nghĩa file ở một số cấu hình hoặc phiên bản. Khai báo response tường minh và kiểm tra JSON/YAML sinh ra để bảo đảm schema là binary.

## 9. Tên file an toàn và tránh lỗi header injection

Không lấy trực tiếp chuỗi tên file tùy ý từ request rồi ghép vào `Content-Disposition`. Tên file có thể chứa dấu phân cách đường dẫn, ký tự xuống dòng hoặc ký tự điều khiển. Nếu đưa dữ liệu không an toàn vào header, ứng dụng có thể tạo header sai hoặc mở ra nguy cơ response splitting.

Các nguyên tắc:

- Tên lưu trữ và đường dẫn file do server quản lý; client chỉ nên chọn file thông qua ID hoặc một định danh đã được kiểm tra.
- Loại bỏ đường dẫn (`../`, `\\`, `/`) khỏi tên hiển thị; chỉ dùng tên cuối cùng, không dùng tên đó để xác định đường dẫn lưu trữ.
- Loại bỏ CR, LF và ký tự điều khiển.
- Dùng `ContentDisposition` builder thay vì tự nối chuỗi header.
- Đặt tên dự phòng nếu tên file trống hoặc không hợp lệ.
- Không đưa đường dẫn tuyệt đối, bucket nội bộ hoặc thông tin lưu trữ vào header response.
- Không tin phần mở rộng file để xác định nội dung; kiểm tra media type theo metadata đáng tin cậy hoặc nội dung thực tế.

Việc làm sạch tên file trong ví dụ chỉ xử lý tên hiển thị. Quyền truy cập file và chống path traversal phải được thực thi tại tầng lưu trữ/service, nơi ánh xạ ID sang đối tượng file được phép đọc.

## 10. Media type và nội dung được tải

`Content-Type` cần phản ánh loại nội dung thực tế. Một số media type thường gặp:

| Loại tệp | Media type phổ biến |
|---|---|
| PDF | `application/pdf` |
| CSV | `text/csv` |
| ZIP | `application/zip` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| JSON | `application/json` |
| Không xác định cụ thể | `application/octet-stream` |

Nếu media type không chắc chắn, `application/octet-stream` là lựa chọn tổng quát cho dữ liệu nhị phân. Không nên dùng `application/octet-stream` cho mọi file nếu ứng dụng biết chính xác loại nội dung và cần trình duyệt hiển thị inline.

Với `inline`, browser thường cần media type phù hợp để render. Ví dụ PDF cần `application/pdf`; nếu trả `application/octet-stream`, nhiều trình duyệt sẽ coi nội dung là file tải xuống hoặc không hiển thị trực tiếp.

## 11. CORS và việc đọc tên file từ JavaScript

Khi frontend và API ở hai origin khác nhau, trình duyệt có thể nhận `Content-Disposition` nhưng JavaScript không được phép đọc header này trừ khi server expose nó qua CORS.

Ví dụ cấu hình:

```http
Access-Control-Expose-Headers: Content-Disposition, Content-Length
```

Trong Spring MVC, có thể khai báo qua `CorsConfiguration` hoặc cấu hình CORS phù hợp cho endpoint. Header `Access-Control-Expose-Headers` chỉ ảnh hưởng khả năng JavaScript đọc response header; nó không quyết định trình duyệt có tải file hay không.

Frontend dùng `fetch` thường phải đọc response body thành `Blob`, sau đó tạo URL tạm và kích hoạt download. Nếu cần tên file do server gợi ý, frontend đọc `Content-Disposition` sau khi header được expose. Cần xử lý cả `filename` và `filename*` nếu muốn hỗ trợ Unicode đầy đủ.

## 12. Response lỗi của endpoint tải tệp

Endpoint tải file vẫn có thể trả các lỗi thông thường:

| Status | Tình huống |
|---|---|
| `400 Bad Request` | ID hoặc tham số không hợp lệ |
| `401 Unauthorized` | Chưa xác thực |
| `403 Forbidden` | Người dùng không có quyền đọc file |
| `404 Not Found` | File không tồn tại hoặc không được công bố cho người gọi |
| `416 Range Not Satisfiable` | Byte range yêu cầu không hợp lệ khi server hỗ trợ range |
| `500 Internal Server Error` | Lỗi khi truy xuất hoặc tạo nội dung file |

Các lỗi nên được trả bằng representation nhất quán của API, chẳng hạn `application/problem+json` hoặc DTO lỗi riêng. Không trả một trang HTML lỗi từ reverse proxy nếu client kỳ vọng error schema JSON, trừ khi đó là chính sách gateway đã được công bố.

Không nên bắt đầu stream body rồi mới kiểm tra quyền hoặc xác định file có tồn tại hay không. Hãy hoàn tất xác thực, phân quyền và chuẩn bị metadata trước khi gửi header `200 OK`; sau khi body đã bắt đầu, server không thể dễ dàng thay response thành JSON lỗi.

## 13. Hỗ trợ tải theo byte range

Với file lớn hoặc media có thể tua, client có thể gửi header `Range` để yêu cầu một phần dữ liệu. Nếu server hỗ trợ, response có thể là `206 Partial Content` kèm `Content-Range`, và có thể có `Accept-Ranges: bytes`.

Ví dụ response một phần:

```http
HTTP/1.1 206 Partial Content
Content-Type: video/mp4
Accept-Ranges: bytes
Content-Range: bytes 0-999/5000
Content-Length: 1000

...1000 byte đầu tiên...
```

Không khai báo `206` hoặc `Accept-Ranges` trong tài liệu chỉ vì file có thể đọc được từ `Resource`. Endpoint phải thực sự xử lý request `Range`, trả đúng byte segment và header liên quan. Nếu không triển khai range request, chỉ mô tả response `200` đầy đủ.

Khi hỗ trợ range, bổ sung response `206` và `416` vào OpenAPI, đồng thời kiểm thử các trường hợp range hợp lệ, vượt kích thước và nhiều range theo phạm vi server hỗ trợ.

## 14. Bảo mật và cache cho file tải xuống

File có thể chứa dữ liệu cá nhân, hợp đồng, báo cáo tài chính hoặc thông tin nội bộ. Endpoint tải xuống phải áp dụng cùng chính sách phân quyền như endpoint đọc dữ liệu tương ứng.

- Xác thực người gọi và kiểm tra quyền trên chính file được yêu cầu.
- Không cho phép client truyền đường dẫn filesystem hoặc object storage key tùy ý.
- Tránh để ID tuần tự dễ đoán trở thành cơ chế bảo vệ duy nhất; vẫn phải kiểm tra quyền sở hữu và quyền truy cập.
- Với file nhạy cảm, cân nhắc `Cache-Control: private, no-store` theo chính sách bảo mật.
- Không ghi nội dung file, token hoặc thông tin nhạy cảm vào log.
- Kiểm tra media type và nội dung thực tế, nhất là khi file do người dùng tải lên.
- Không dùng `inline` cho nội dung không tin cậy nếu trình duyệt có thể thực thi hoặc render nội dung nguy hiểm theo cách không mong muốn.
- Nếu dùng URL ký có thời hạn, giới hạn thời gian, phạm vi file và quyền truy cập.

`Content-Disposition: attachment` có thể giảm khả năng browser render trực tiếp, nhưng không thay thế kiểm tra nội dung, quyền truy cập hoặc các header bảo mật phù hợp.

## 15. Kiểm tra response tải tệp

Sau khi triển khai endpoint, cần kiểm tra cả body, header và tài liệu OpenAPI:

1. Gọi endpoint với file hợp lệ và xác nhận status `200`.
2. Kiểm tra `Content-Type` khớp với nội dung thực tế.
3. Kiểm tra `Content-Disposition` có `attachment` hoặc `inline` theo yêu cầu và tên file hợp lệ.
4. Nếu có `Content-Length`, so sánh với số byte thực nhận.
5. Mở file đã tải bằng ứng dụng phù hợp để xác nhận nội dung không bị cắt hoặc hỏng.
6. Kiểm tra tên file Unicode trên các trình duyệt mục tiêu.
7. Gọi bằng user không có quyền và xác nhận response lỗi đúng.
8. Nếu dùng CORS, xác nhận JavaScript có thể đọc `Content-Disposition` khi cần.
9. Nếu streaming, kiểm thử file lớn, client ngắt kết nối và nhiều request đồng thời.
10. Nếu hỗ trợ range, kiểm tra `206`, `Content-Range` và `416`.
11. Tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`, xác nhận response thành công có media type binary, header được mô tả và response lỗi có schema phù hợp.
12. Kiểm tra Swagger UI và client generator đang dùng có thể xử lý binary response theo cách mong đợi.

Các công cụ HTTP như curl có thể kiểm tra header và lưu body:

```bash
curl -fS -D response-headers.txt \
  http://localhost:8080/api/files/550e8400-e29b-41d4-a716-446655440000/download \
  -o downloaded-file.pdf
```

`-D` lưu response header để kiểm tra `Content-Type` và `Content-Disposition`; `-o` ghi body vào file. Nếu endpoint yêu cầu bearer token, bổ sung header `Authorization` theo cấu hình bảo mật.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| File tải về có tên ngẫu nhiên hoặc sai | Thiếu `Content-Disposition` hoặc filename không được mã hóa phù hợp | Dùng `ContentDisposition` builder và kiểm tra header |
| Trình duyệt hiển thị PDF thay vì tải xuống | Dùng `inline` hoặc thiếu disposition attachment | Đặt `Content-Disposition: attachment` nếu cần tải |
| File bị hỏng | Sai content type, stream bị đọc trước, ghi thiếu byte hoặc đóng stream sớm | Kiểm tra nguồn dữ liệu và vòng đời stream |
| File lớn gây tăng heap | Nạp toàn bộ file vào `byte[]` | Dùng `Resource` hoặc `StreamingResponseBody` |
| `Content-Length` sai | Tính kích thước từ stream không thể đọc lại hoặc đặt giá trị không chính xác | Chỉ đặt khi biết chắc số byte |
| Tên file Unicode bị lỗi | Encoding header hoặc client không tương thích | Dùng builder UTF-8 và kiểm thử `filename*` trên browser mục tiêu |
| Swagger UI mô tả body là object | Springdoc suy luận từ kiểu trả về thay vì schema binary mong muốn | Khai báo `@ApiResponse` và `@Content` tường minh |
| Client không đọc được tên file qua fetch | CORS không expose `Content-Disposition` | Cấu hình `Access-Control-Expose-Headers` |
| File riêng tư bị truy cập trái phép | Chỉ kiểm tra ID hoặc không xác thực quyền trên file | Kiểm tra quyền tại service trước khi mở stream |
| Header bị lỗi với tên file đặc biệt | Ghép chuỗi header trực tiếp từ dữ liệu không tin cậy | Làm sạch tên và dùng `ContentDisposition` |

## 17. Nguyên tắc thiết kế

- Dùng `Resource` hoặc streaming cho file lớn; chỉ dùng `byte[]` khi kích thước được giới hạn.
- Chọn `Content-Type` đúng với nội dung; dùng `application/octet-stream` khi không xác định được loại cụ thể.
- Dùng `attachment` để yêu cầu tải xuống và `inline` khi muốn trình duyệt thử hiển thị.
- Tạo `Content-Disposition` bằng Spring `ContentDisposition` builder, hỗ trợ tên file UTF-8 và làm sạch tên trước khi đưa vào header.
- Chỉ đặt `Content-Length` khi kích thước chính xác và không làm tiêu thụ stream.
- Mô tả body binary theo media type trong OpenAPI; mô tả `Content-Disposition` bằng response header.
- Mô tả response lỗi JSON riêng với response thành công dạng file.
- Không khai báo range response nếu server chưa thực sự hỗ trợ byte range.
- Kiểm tra quyền truy cập trước khi bắt đầu gửi body; không để client tự chọn đường dẫn lưu trữ.
- Đồng bộ schema OpenAPI, header runtime và hành vi tải trên trình duyệt/client.

## Kết luận

Endpoint tải tệp cần trả đúng byte content cùng `Content-Type` và `Content-Disposition`. Spring MVC có thể dùng `Resource`, `byte[]` hoặc `StreamingResponseBody` tùy kích thước và nguồn dữ liệu. Springdoc-openapi mô tả body bằng media type cùng schema nhị phân, còn `Content-Disposition` và các header khác được khai báo trong Response Object. Khi triển khai, hãy xử lý tên file an toàn, hỗ trợ UTF-8, kiểm soát quyền trước khi stream và kiểm tra cả header lẫn nội dung thực tế để hợp đồng OpenAPI khớp với response mà client nhận được.
