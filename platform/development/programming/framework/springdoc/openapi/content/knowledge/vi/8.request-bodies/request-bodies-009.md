# Encoding Object và kiểu nội dung của từng phần

Khi API nhận `multipart/form-data` hoặc `application/x-www-form-urlencoded`, một request body có thể chứa nhiều trường với cách biểu diễn khác nhau. Ví dụ, một request upload có thể gồm file PDF, metadata JSON và danh sách nhãn văn bản. OpenAPI mô tả cấu trúc các trường bằng Schema Object, còn **Encoding Object** quy định cách mã hóa từng property trong body, bao gồm media type, header của từng phần và cách tuần tự hóa array hoặc object. Springdoc-openapi có thể tạo tài liệu từ controller Spring Boot, đồng thời cho phép bổ sung Encoding Object bằng Swagger annotations khi cần kiểm soát hợp đồng chi tiết.

## 1. Vì sao cần Encoding Object?

Với JSON thông thường, toàn bộ body thường có một media type chung:

```http
POST /api/products HTTP/1.1
Content-Type: application/json

{"name":"Bút bi","price":12000}
```

Nhưng `multipart/form-data` chia body thành nhiều phần. Mỗi phần có tên trường, nội dung và có thể có media type riêng. Một request upload tài liệu có thể gửi:

- `file`: nội dung PDF hoặc ảnh.
- `metadata`: một object JSON chứa tiêu đề, loại tài liệu và mô tả.
- `labels`: một hoặc nhiều giá trị văn bản.

Header ở cấp request cho biết body tổng thể là multipart; header của từng phần cho biết cách đọc nội dung của phần đó. Nếu chỉ khai báo schema mà không chỉ rõ cách mã hóa property phức tạp, client có thể không biết cần gửi metadata dưới dạng JSON hay chuỗi form.

Encoding Object giải quyết vấn đề này bằng cách gắn quy tắc mã hóa với từng property trong schema của request body. Nó không định nghĩa lại cấu trúc dữ liệu; Schema Object vẫn mô tả tên trường, kiểu và ràng buộc.

## 2. Phân biệt Content-Type của request và của từng part

Một request multipart có hai cấp media type:

1. **Media type tổng thể:** thường là `multipart/form-data` và có tham số `boundary` để phân cách các phần.
2. **Media type của từng part:** ví dụ `application/pdf`, `image/png`, `application/json` hoặc `text/plain`.

Ví dụ rút gọn:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=Boundary-123

--Boundary-123
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...bytes của file PDF...
--Boundary-123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Hướng dẫn sử dụng","category":"manual"}
--Boundary-123
Content-Disposition: form-data; name="labels"
Content-Type: text/plain

internal
--Boundary-123--
```

Header `Content-Type: multipart/form-data; boundary=...` mô tả toàn bộ request. `Content-Type: application/pdf` và `Content-Type: application/json` nằm bên trong từng part. Hai cấp này không thay thế nhau.

Khi dùng trình duyệt hoặc curl để tạo multipart request, client thường tự sinh boundary. Không đặt thủ công `Content-Type: multipart/form-data` mà bỏ boundary, vì server sẽ không biết cách tách các part.

## 3. Encoding Object nằm ở đâu trong OpenAPI?

Encoding Object được khai báo trong `encoding` của Media Type Object, bên trong `content` của Request Body Object. Mỗi khóa trong `encoding` phải tương ứng với tên property của schema body.

Ví dụ:

```yaml
paths:
  /api/documents:
    post:
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required: [file, metadata]
              properties:
                file:
                  type: string
                  format: binary
                metadata:
                  $ref: '#/components/schemas/DocumentMetadata'
            encoding:
              file:
                contentType: application/pdf
              metadata:
                contentType: application/json
```

Trong ví dụ, `schema.properties` định nghĩa hai trường `file` và `metadata`. Phần `encoding.file` quy định part `file` được gửi dưới dạng PDF; `encoding.metadata` quy định part `metadata` có media type JSON. Tên `file` và `metadata` phải khớp với tên property trong schema.

Encoding Object chỉ có ý nghĩa với các request body dạng `multipart/form-data` và `application/x-www-form-urlencoded`. Với body JSON thông thường, hãy mô tả cấu trúc bằng schema JSON; không dùng `encoding` để thay thế `properties` hoặc `content` của JSON.

## 4. Các thuộc tính của Encoding Object

Encoding Object có các thuộc tính chính sau:

| Thuộc tính | Ý nghĩa | Khi thường dùng |
|---|---|---|
| `contentType` | Media type của property hoặc part | Chọn JSON cho metadata, PDF cho file hoặc text cho trường chuỗi |
| `headers` | Các header bổ sung áp dụng cho từng part multipart | Mô tả checksum, ngôn ngữ hoặc metadata header riêng của part |
| `style` | Quy tắc tuần tự hóa array/object | Chọn cách biểu diễn object hoặc danh sách trong form body |
| `explode` | Quyết định giá trị array/object được tách thành nhiều trường hay ghép lại | Điều khiển cách gửi danh sách hoặc object theo style |
| `allowReserved` | Cho phép giữ nguyên một số ký tự reserved thay vì percent-encode | Có ý nghĩa với `application/x-www-form-urlencoded` |

Các thuộc tính này không thay đổi kiểu dữ liệu trong schema. Chúng chỉ mô tả cách giá trị của property được chuyển thành nội dung request theo media type đang khai báo.

### contentType: media type của property

`contentType` chỉ định media type dùng để mã hóa một property. Giá trị có thể là một media type hoặc danh sách media type phân cách bằng dấu phẩy nếu property chấp nhận nhiều định dạng.

```yaml
encoding:
  file:
    contentType: application/pdf, image/png
  metadata:
    contentType: application/json
  comment:
    contentType: text/plain; charset=UTF-8
```

Trong ví dụ, client có thể gửi file dưới dạng PDF hoặc PNG; metadata là JSON; comment là văn bản UTF-8. Các định dạng được công bố phải phù hợp với khả năng endpoint thực sự xử lý.

Nếu không khai báo `contentType`, OpenAPI quy định giá trị mặc định dựa trên schema property:

- Kiểu nguyên thủy hoặc array chứa kiểu nguyên thủy thường dùng `text/plain`.
- Kiểu object hoặc array chứa object thường dùng `application/json`.
- Chuỗi có `format: binary` thường dùng `application/octet-stream`.

Khi hợp đồng yêu cầu media type cụ thể, nên khai báo tường minh để client không phải dựa vào mặc định. Với file PDF hoặc ảnh, khai báo `application/pdf` hoặc `image/png` giúp người tích hợp hiểu loại file được chấp nhận.

### headers: header của từng part

`headers` là bản đồ các Header Object được áp dụng cho từng part của multipart request. Ví dụ, API có thể yêu cầu client gửi checksum của file trong header riêng:

```yaml
encoding:
  file:
    contentType: application/pdf
    headers:
      X-Checksum-SHA256:
        description: SHA-256 của nội dung file
        schema:
          type: string
          pattern: '^[a-fA-F0-9]{64}$'
```

Header này thuộc part `file`, không phải header ở cấp request. Không nhầm `headers` trong Encoding Object với `parameters` ở cấp operation. Parameter header mô tả header của toàn request; Encoding Object headers mô tả header của từng part multipart.

`Content-Type` của part được điều khiển bằng `contentType`. Nếu khai báo `Content-Type` trong `encoding.headers`, mục đó bị bỏ qua theo quy tắc OpenAPI. Các header multipart tiêu chuẩn như `Content-Disposition` thường do client tạo dựa trên tên property và tên file; chỉ mô tả header tùy chỉnh khi API thực sự yêu cầu nó.

### style và explode: cách tuần tự hóa array/object

`style` xác định cách giá trị array hoặc object được biểu diễn. Giá trị mặc định của Encoding Object là `form`. `explode` quyết định object hoặc array có được tách thành các giá trị riêng hay không; mặc định là `true` khi `style` là `form`, và `false` với các style khác.

Ví dụ schema có một danh sách nhãn:

```yaml
schema:
  type: object
  properties:
    labels:
      type: array
      items:
        type: string
encoding:
  labels:
    style: form
    explode: true
```

Với `form` và `explode: true`, các phần tử có thể được gửi thành nhiều giá trị cùng tên field, ví dụ `labels=internal` và `labels=approved`. Nếu dùng `explode: false`, danh sách được ghép thành một giá trị theo quy tắc serialize của style, chẳng hạn một chuỗi phân cách bằng dấu phẩy.

Với object, `style` và `explode` cũng ảnh hưởng cách biểu diễn các thuộc tính. Hãy chọn cách serialize mà framework và client cùng hỗ trợ; đừng khai báo `deepObject`, `spaceDelimited` hoặc `pipeDelimited` theo thói quen nếu media type và công cụ xử lý không hỗ trợ quy tắc đó.

### allowReserved: ký tự reserved trong form URL encoded

`allowReserved` điều khiển việc các ký tự reserved trong giá trị có được giữ nguyên hay phải percent-encode. Giá trị mặc định là `false`. Thuộc tính này chỉ có ý nghĩa với `application/x-www-form-urlencoded`.

Ví dụ:

```yaml
content:
  application/x-www-form-urlencoded:
    schema:
      type: object
      properties:
        callback:
          type: string
    encoding:
      callback:
        allowReserved: false
```

Thông thường nên giữ `false` để tránh ký tự như `&`, `=`, `?` hoặc `#` làm thay đổi cách phân tích form/query. Chỉ bật `true` khi hợp đồng có lý do rõ ràng và client/server thống nhất cách diễn giải giá trị.

## 5. Ví dụ multipart: file PDF, metadata JSON và danh sách nhãn

Một endpoint upload thường có schema tổng thể là object. Property file dùng `type: string` và `format: binary`; metadata tham chiếu một schema JSON; labels là array các chuỗi.

```yaml
paths:
  /api/documents:
    post:
      summary: Tải tài liệu lên
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - file
                - metadata
              properties:
                file:
                  type: string
                  format: binary
                  description: File PDF cần tải lên
                metadata:
                  $ref: '#/components/schemas/DocumentMetadata'
                labels:
                  type: array
                  items:
                    type: string
            encoding:
              file:
                contentType: application/pdf
                headers:
                  X-Checksum-SHA256:
                    description: SHA-256 của file
                    schema:
                      type: string
              metadata:
                contentType: application/json
              labels:
                style: form
                explode: true
      responses:
        '201':
          description: Đã lưu tài liệu
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DocumentResponse'
components:
  schemas:
    DocumentMetadata:
      type: object
      required: [title, category]
      properties:
        title:
          type: string
        category:
          type: string
          enum: [manual, invoice, contract]
        description:
          type: string
    DocumentResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        fileName:
          type: string
```

Ở đây, `file` được gửi với media type `application/pdf`; `metadata` được gửi như một JSON part; `labels` được tuần tự hóa thành các giá trị form riêng. `X-Checksum-SHA256` là header của part file. Response của operation vẫn là JSON bình thường và không liên quan đến Encoding Object của request.

### Request mẫu bằng curl

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -H 'Accept: application/json' \
  -F 'file=@guide.pdf;type=application/pdf' \
  -F 'metadata={"title":"Hướng dẫn sử dụng","category":"manual"};type=application/json' \
  -F 'labels=internal' \
  -F 'labels=approved'
```

curl tự tạo boundary cho request multipart. Trong ví dụ, `type=application/json` gắn media type JSON cho part metadata; hai trường `labels` được gửi lặp lại để biểu diễn array khi `explode: true`. Nếu API yêu cầu checksum, client cần gửi checksum dưới dạng header của part file theo đúng quy ước mà server đọc. Khả năng đặt header tùy chỉnh cho từng part phụ thuộc công cụ client; API `FormData` tiêu chuẩn của trình duyệt không cung cấp cách đặt tùy ý header cho từng part.

## 6. Ánh xạ Encoding Object với Spring Boot

Trong Spring MVC, `@RequestPart` thường phù hợp khi một phần multipart cần được chuyển đổi thành DTO bằng `HttpMessageConverter`. `MultipartFile` dùng để nhận nội dung file; phần metadata JSON có thể được deserialize thành một DTO riêng.

```java
@RestController
@RequestMapping("/api/documents")
class DocumentController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentResponse upload(
        @RequestPart("file") MultipartFile file,
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestParam(value = "labels", required = false) List<String> labels
    ) {
        return documentService.store(file, metadata, labels);
    }
}
```

`@RequestPart("metadata")` cho phép Spring dùng converter phù hợp với media type của part để chuyển JSON thành `DocumentMetadata`. `@RequestPart("file")` nhận file dưới dạng `MultipartFile`. `@RequestParam("labels")` phù hợp với các trường form lặp lại cùng tên và có thể bind chúng thành `List<String>`.

Nếu metadata được gửi dưới dạng JSON, client cần đặt `Content-Type: application/json` cho part metadata. Nếu gửi nó như `text/plain`, Spring có thể không tìm được converter JSON phù hợp hoặc không thể deserialize thành DTO.

Spring `consumes = multipart/form-data` xác định media type của toàn request. Encoding Object trong OpenAPI mô tả media type và cách serialize của từng property. Hai phần này cần khớp nhau nhưng thực hiện hai nhiệm vụ khác nhau.

## 7. Bổ sung Encoding Object bằng Swagger annotations

Swagger Core cung cấp annotation `@Encoding`, được đặt trong thuộc tính `encoding` của `@Content`. Annotation này cho phép mô tả `contentType`, `headers`, `style`, `explode` và `allowReserved` cho từng property.

Ví dụ:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Encoding;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.headers.Header;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Operation(
    summary = "Tải tài liệu lên",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = DocumentUploadSchema.class),
            encoding = {
                @Encoding(
                    name = "file",
                    contentType = "application/pdf",
                    headers = @Header(
                        name = "X-Checksum-SHA256",
                        description = "SHA-256 của file",
                        schema = @Schema(type = "string")
                    )
                ),
                @Encoding(
                    name = "metadata",
                    contentType = MediaType.APPLICATION_JSON_VALUE
                ),
                @Encoding(
                    name = "labels",
                    style = "form",
                    explode = true
                )
            }
        )
    )
)
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
DocumentResponse upload(
    @RequestPart("file") MultipartFile file,
    @Valid @RequestPart("metadata") DocumentMetadata metadata,
    @RequestParam(value = "labels", required = false) List<String> labels
) {
    return documentService.store(file, metadata, labels);
}
```

Ví dụ dùng `jakarta.validation.Valid`, phù hợp với Spring Boot 3 trở lên; dự án Spring Boot 2 dùng package `javax.validation.Valid` tương ứng.

Trong ví dụ, `DocumentUploadSchema` là kiểu dùng để mô tả cấu trúc body trong OpenAPI. Có thể định nghĩa riêng schema này với property `file` dạng binary, `metadata` là `DocumentMetadata` và `labels` là danh sách chuỗi. Controller vẫn bind các part thành các tham số riêng bằng `@RequestPart`.

Ví dụ schema dùng riêng cho tài liệu:

```java
public class DocumentUploadSchema {
    @Schema(type = "string", format = "binary", description = "File PDF")
    private MultipartFile file;

    private DocumentMetadata metadata;

    private List<String> labels;
}
```

Annotation `@Encoding` không tự thay đổi cách Spring đọc part. Nó chỉ mô tả cho client biết cần gửi từng phần ra sao. Runtime vẫn phụ thuộc `@RequestPart`, converter, multipart resolver và logic xử lý file.

## 8. application/x-www-form-urlencoded và Encoding Object

Encoding Object cũng có thể mô tả cách tuần tự hóa property của `application/x-www-form-urlencoded`. Loại body này không chia thành các part MIME như multipart; các trường được gửi thành chuỗi key-value trong một body form đã encode.

Ví dụ schema:

```yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        properties:
          username:
            type: string
          roles:
            type: array
            items:
              type: string
          address:
            type: object
            properties:
              city:
                type: string
              postalCode:
                type: string
      encoding:
        roles:
          style: form
          explode: true
        address:
          style: deepObject
          explode: true
```

Với `roles`, `form` và `explode: true` cho phép lặp lại key để biểu diễn nhiều giá trị. Với object `address`, `deepObject` biểu diễn các thuộc tính lồng nhau qua dạng key có ngoặc vuông, chẳng hạn `address[city]=...`, nếu client và server cùng hỗ trợ quy tắc này.

Không dùng `headers` để mô tả field form URL encoded, vì các trường đó không phải MIME part riêng có header. `allowReserved` có thể điều chỉnh việc encode ký tự reserved trong giá trị form; cần cân nhắc kỹ để không làm thay đổi cách parser phân tách key/value.

## 9. Quy tắc mặc định và những điểm dễ nhầm

Một số quy tắc giúp đọc và viết Encoding Object chính xác:

| Trường hợp | Cách hiểu |
|---|---|
| Không có `encoding` cho property | Dùng quy tắc mã hóa mặc định của OpenAPI dựa trên schema và media type |
| Property là `string` với `format: binary` | Media type mặc định thường là `application/octet-stream` |
| Property là object | Media type mặc định thường là `application/json` |
| Property là primitive hoặc array kiểu primitive | Media type mặc định thường là `text/plain` |
| `style` không được khai báo | Mặc định là `form` |
| `explode` không được khai báo và style là `form` | Mặc định là `true` |
| `explode` không được khai báo và style khác `form` | Mặc định là `false` |
| `allowReserved` không được khai báo | Mặc định là `false` |
| `Content-Type` được đặt trong `encoding.headers` | Bị bỏ qua; dùng `encoding.contentType` |

Không nhầm `encoding` với `schema`:

- `schema` trả lời: property nào tồn tại, kiểu dữ liệu gì, bắt buộc hay không?
- `encoding` trả lời: property đó được serialize thành nội dung request như thế nào?

Không nhầm media type của request với media type của part:

- `content.multipart/form-data` là định dạng tổng thể của request.
- `encoding.file.contentType` là định dạng của part `file`.
- `encoding.metadata.contentType` là định dạng của part `metadata`.

Không khai báo `encoding` cho một property không tồn tại trong schema. Khóa trong `encoding` phải tương ứng với tên property được định nghĩa trong schema của media type đó.

## 10. Giới hạn và tương thích công cụ

Encoding Object là một phần của hợp đồng OpenAPI, nhưng mức độ hỗ trợ giao diện và code generator có thể khác nhau. Một số công cụ hiển thị được file upload nhưng không cho người dùng chọn media type riêng cho từng part; một số generator có thể bỏ qua `headers`, `style` hoặc `explode` khi tạo client.

Khi sử dụng OpenAPI 3.0.x hoặc 3.1.x, hãy kiểm tra phiên bản Swagger UI, springdoc-openapi và code generator đang dùng. Cách biểu diễn file thường dùng `type: string`, `format: binary`, nhưng cách xử lý schema binary có thể khác giữa công cụ và phiên bản đặc tả.

Encoding Object không xác thực nội dung file, không kiểm tra MIME type thực tế của bytes và không thay thế kiểm tra bảo mật upload. Ứng dụng vẫn cần xác thực phần mở rộng, kích thước, chữ ký nội dung, checksum nếu có, quyền truy cập và chính sách lưu trữ. Giá trị `contentType` do client gửi lên là metadata có thể bị giả mạo; server nên kiểm tra nội dung thực tế theo yêu cầu nghiệp vụ.

## 11. Kiểm tra Encoding Object trong tài liệu và request thật

Sau khi ứng dụng khởi động, tải `/v3/api-docs` hoặc `/v3/api-docs.yaml` và kiểm tra operation upload:

1. Request body có media type tổng thể `multipart/form-data` không?
2. Schema có đủ property `file`, `metadata`, `labels` và ràng buộc `required` không?
3. `encoding.file.contentType` có đúng loại file được nhận không?
4. `encoding.metadata.contentType` có là `application/json` nếu server deserialize metadata thành DTO không?
5. `encoding.labels.style` và `explode` có phù hợp cách server bind danh sách không?
6. Các header trong `encoding.<property>.headers` có đúng là header của part không?
7. Swagger UI và client generator có hiển thị/gửi được từng part theo hợp đồng không?

Sau đó gửi request thực tế bằng curl hoặc Postman. Quan sát request multipart để xác nhận boundary, tên part, `Content-Disposition`, `Content-Type` riêng của từng part và số lần lặp của field array. Nếu tài liệu đúng nhưng server binding sai, kiểm tra `@RequestPart`, converter và cấu hình multipart. Nếu server xử lý đúng nhưng tài liệu thiếu encoding, bổ sung `@Encoding` hoặc tùy chỉnh OpenAPI.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Metadata JSON không deserialize thành DTO | Part metadata bị gửi dưới dạng `text/plain` hoặc không có Content-Type phù hợp | Đặt `Content-Type: application/json` cho part và khai báo `encoding.metadata.contentType` |
| File hiển thị như chuỗi thông thường trong Swagger UI | Schema file thiếu `format: binary` hoặc công cụ không hỗ trợ cách mô tả đang dùng | Kiểm tra schema và phiên bản Swagger UI/code generator |
| Server không tách được multipart request | Client tự đặt Content-Type nhưng thiếu boundary | Để client tự sinh boundary |
| Danh sách chỉ nhận được một giá trị | Client gửi một chuỗi ghép nhưng server mong nhiều part, hoặc `explode` không khớp | Đồng bộ `style`, `explode` và cách gửi field lặp lại |
| Header checksum không xuất hiện ở server | Header được khai báo ở cấp request thay vì trong encoding của part, hoặc client không hỗ trợ part header | Kiểm tra header của từng part và khả năng client |
| Thay `encoding.contentType` nhưng runtime vẫn nhận sai định dạng | Encoding chỉ thay đổi tài liệu | Điều chỉnh cách client gửi part và cấu hình converter/server |
| Swagger UI hiển thị đúng nhưng upload bị từ chối | Server validation hoặc kiểm tra file không chấp nhận nội dung | Xem log, MIME detection, kích thước, checksum và quy tắc nghiệp vụ |

## 13. Quy trình thiết kế request body nhiều phần

Khi thiết kế endpoint nhận multipart hoặc form URL encoded, thực hiện theo trình tự:

1. Xác định media type tổng thể của request body.
2. Thiết kế schema object với tên property ổn định, kiểu dữ liệu và trường bắt buộc.
3. Với multipart, chỉ rõ `contentType` cho file và object phức tạp khi cần.
4. Dùng `headers` để mô tả header tùy chỉnh của part, không dùng nó để thay thế `contentType`.
5. Chọn `style` và `explode` theo cách client gửi array/object và cách Spring bind dữ liệu.
6. Với form URL encoded, xem xét `allowReserved` và cách serialize object lồng nhau.
7. Ánh xạ từng part vào `MultipartFile`, `@RequestPart` hoặc tham số form phù hợp trong Spring.
8. Kiểm tra OpenAPI JSON/YAML, Swagger UI, request thật và khả năng của code generator.

Encoding Object giúp hợp đồng OpenAPI mô tả chính xác cách từng trường trong form được gửi qua HTTP. Kết hợp schema, media type của từng part và cách binding trong Spring Boot giúp client gửi đúng payload, còn server nhận được dữ liệu theo cấu trúc đã công bố.

## 14. Tài liệu tham khảo

- [OpenAPI Specification – Encoding Object](https://spec.openapis.org/oas/latest.html#encoding-object): thuộc tính `contentType`, `headers`, `style`, `explode` và `allowReserved`.
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object): `schema`, `example`, `examples` và `encoding`.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): mô tả body request và media type.
- [Spring Framework: Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): cách Spring MVC tiếp nhận multipart request.
- [Spring Framework: @RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): binding từng part của multipart request.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): annotation `@Content`, `@Encoding` và schema cho tài liệu OpenAPI.
- [Springdoc OpenAPI](https://springdoc.org/): tạo và tùy chỉnh tài liệu OpenAPI từ controller Spring Boot.
