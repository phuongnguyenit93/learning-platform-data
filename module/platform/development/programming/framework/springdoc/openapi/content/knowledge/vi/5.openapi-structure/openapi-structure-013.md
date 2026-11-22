# Tài liệu JSON hoặc YAML khác cách diễn giải và hiển thị trên giao diện

OpenAPI có thể được biểu diễn dưới dạng JSON hoặc YAML. Hai định dạng này có cú pháp khác nhau, nhưng khi mô tả cùng một mô hình OpenAPI thì chúng mang cùng ý nghĩa: cùng endpoint, HTTP method, parameter, request body, response, schema và yêu cầu bảo mật. Springdoc-openapi có thể cung cấp cả hai cách biểu diễn để phục vụ công cụ tự động, người review tài liệu và giao diện Swagger UI.

Với module `SPRINGDOC_OPENAPI`, cần phân biệt ba vấn đề: dữ liệu hợp đồng OpenAPI, cách dữ liệu đó được tuần tự hóa thành JSON hoặc YAML, và cách Swagger UI đọc rồi trình bày hợp đồng. Định dạng tệp ảnh hưởng đến khả năng đọc và xử lý của công cụ; nó không tự làm thay đổi hành vi API hay nội dung hợp đồng.

## 1. Một mô hình OpenAPI, hai định dạng biểu diễn

Springdoc thu thập metadata từ controller Spring, DTO, annotation và cấu hình để xây dựng mô hình OpenAPI. Mô hình này có thể được tuần tự hóa thành JSON hoặc YAML.

Với cấu hình mặc định thường gặp:

| Endpoint | Định dạng |
|---|---|
| `/v3/api-docs` | JSON |
| `/v3/api-docs.yaml` | YAML |

Hai endpoint cung cấp cùng một đặc tả. Nếu chuyển đổi JSON sang YAML bằng parser phù hợp, rồi đọc lại thành cấu trúc dữ liệu, các thành phần OpenAPI có ý nghĩa tương đương. Thứ tự trình bày, khoảng trắng, dấu ngoặc và cách xuống dòng có thể khác nhau mà không làm thay đổi hợp đồng.

Ví dụ, cùng mô tả một thao tác lấy đơn hàng:

**Dạng YAML**

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: '1.0'
paths:
  /orders/{id}:
    get:
      summary: Lấy đơn hàng
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Tìm thấy đơn hàng
```

**Dạng JSON tương đương**

```json
{
  "openapi": "3.0.3",
  "info": {
    "title": "Order API",
    "version": "1.0"
  },
  "paths": {
    "/orders/{id}": {
      "get": {
        "summary": "Lấy đơn hàng",
        "parameters": [
          {
            "name": "id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Tìm thấy đơn hàng"
          }
        }
      }
    }
  }
}
```

Các dấu ngoặc nhọn, dấu phẩy và dấu ngoặc kép của JSON được thay bằng cấu trúc thụt lề và dấu hai chấm trong YAML. Nhưng cả hai đều mô tả một path `/orders/{id}`, một operation `get`, một path parameter bắt buộc và response `200`.

## 2. Khác biệt về cú pháp và cách đọc

JSON biểu diễn object bằng `{}`, array bằng `[]`, cặp khóa và giá trị bằng dấu hai chấm, các phần tử được phân tách bằng dấu phẩy. Tên thuộc tính và giá trị chuỗi phải đặt trong dấu ngoặc kép. JSON không hỗ trợ comment và không cho phép dấu phẩy thừa ở cuối object hoặc array.

YAML thường dùng thụt lề để biểu diễn cấu trúc. Dấu gạch ngang tạo phần tử danh sách, dấu hai chấm phân tách khóa và giá trị. YAML hỗ trợ comment bằng `#`, chuỗi nhiều dòng và nhiều cách viết scalar nên thường dễ đọc khi tài liệu có nhiều schema hoặc mô tả dài.

| Tiêu chí | JSON | YAML |
|---|---|---|
| Cấu trúc object | `{ ... }` | Các khóa và giá trị theo thụt lề |
| Danh sách | `[ ... ]` | Các dòng bắt đầu bằng `-` hoặc dạng flow |
| Chuỗi | Dùng dấu ngoặc kép | Có thể dùng plain, single-quoted hoặc double-quoted |
| Comment | Không có cú pháp comment chuẩn | Dùng `#` |
| Chuỗi nhiều dòng | Phải escape ký tự xuống dòng | Có block scalar `|` và `>` |
| Phân tách phần tử | Dùng dấu phẩy | Chủ yếu dựa trên xuống dòng và thụt lề |
| Xử lý bằng chương trình | Có parser tích hợp rộng trong hệ sinh thái | Cần parser YAML tương thích |
| Review thủ công | Rõ ràng với công cụ và cấu trúc nhỏ | Thường gọn, dễ đọc với tài liệu dài |

JSON có cú pháp chặt chẽ, thuận tiện cho hệ thống tự động và trao đổi giữa các dịch vụ. YAML có cách trình bày ít ký tự cấu trúc hơn, thuận tiện cho người viết và review hợp đồng. Việc chọn định dạng nên dựa vào công cụ tiêu thụ, quy trình review và quy ước của nhóm.

## 3. Những khác biệt cú pháp dễ làm sai ý nghĩa

Khi chuyển tài liệu giữa JSON và YAML, cần chú ý kiểu dữ liệu và quy tắc escape. Một file vẫn có thể trông hợp lý với mắt người nhưng parser lại đọc thành kiểu khác.

### Chuỗi và giá trị có hình dạng đặc biệt

Trong JSON, chuỗi luôn được đặt trong dấu ngoặc kép. Trong YAML, nhiều chuỗi có thể viết không cần dấu nháy, nhưng nên đặt trong dấu nháy khi giá trị có thể bị hiểu nhầm là boolean, số, null hoặc có ký tự mang ý nghĩa cú pháp.

```yaml
info:
  version: '1.0'
  description: 'API quản lý đơn hàng: tạo, đọc và hủy đơn.'
paths:
  /orders/{id}:
    get:
      responses:
        '200':
          description: Thành công
```

Trong ví dụ, `info.version` là chuỗi phiên bản, vì vậy đặt `'1.0'` trong dấu nháy giúp tránh parser diễn giải thành số. Mã trạng thái response cũng nên được đặt trong dấu nháy, chẳng hạn `'200'`, để giữ đúng dạng khóa chuỗi mà OpenAPI yêu cầu.

Các giá trị như `true`, `false`, `null`, `on`, `off`, chuỗi chỉ gồm chữ số hoặc chuỗi có dấu `:` và `#` cần được kiểm tra theo phiên bản YAML và parser đang sử dụng. Khi mục đích là chuỗi, hãy đặt trong dấu nháy để biểu đạt rõ ràng.

### Ký tự `#` và tham chiếu `$ref`

Trong YAML, `#` có thể bắt đầu comment khi xuất hiện ở vị trí phù hợp. Vì vậy, giá trị tham chiếu có dấu `#` nên được đặt trong dấu nháy:

```yaml
schema:
  $ref: '#/components/schemas/OrderResponse'
```

Nếu bỏ dấu nháy và viết `$ref: #/components/schemas/OrderResponse`, parser có thể xem phần sau dấu `#` là comment và đọc giá trị rỗng. JSON bắt buộc biểu diễn giá trị này bằng chuỗi:

```json
{
  "$ref": "#/components/schemas/OrderResponse"
}
```

### Chuỗi nhiều dòng

YAML hỗ trợ block scalar. Dấu `|` giữ các dấu xuống dòng trong nội dung; dấu `>` gộp các dòng theo quy tắc folded scalar. Điều này hữu ích khi mô tả operation hoặc schema có nhiều đoạn văn.

```yaml
description: |
  Tạo đơn hàng mới.
  API kiểm tra dữ liệu khách hàng và số tiền trước khi lưu.
```

Trong JSON, nội dung tương đương được biểu diễn bằng ký tự escape `\n`:

```json
{
  "description": "Tạo đơn hàng mới.\nAPI kiểm tra dữ liệu khách hàng và số tiền trước khi lưu."
}
```

Comment YAML giúp người bảo trì ghi chú trong file nguồn, nhưng comment không phải một phần của mô hình OpenAPI và thường không còn sau khi parser đọc rồi tuần tự hóa lại tài liệu. Nếu thông tin cần xuất hiện với người tiêu dùng API, hãy dùng các trường `description`, `summary`, `example` hoặc metadata phù hợp.

## 4. Kiểu dữ liệu và quy tắc diễn giải

JSON có một tập kiểu dữ liệu rõ ràng: object, array, string, number, boolean và null. YAML có nhiều kiểu scalar và quy tắc nhận diện giá trị, nên parser có thể suy luận kiểu từ cách viết.

Ví dụ:

```yaml
example:
  active: true
  retryCount: 3
  customerCode: '00123'
  description: 'Mã trạng thái: đã tiếp nhận'
```

Trong cấu trúc này, `active` là boolean, `retryCount` là số, còn `customerCode` là chuỗi giữ nguyên các số 0 ở đầu. Nếu viết `customerCode: 00123` mà không đặt dấu nháy, kết quả diễn giải có thể phụ thuộc quy tắc parser/YAML version và không còn là giá trị chuỗi mong muốn.

Khi định nghĩa OpenAPI, kiểu của schema cần phù hợp với dữ liệu API thực tế:

- Dữ liệu định danh có thể là chuỗi, kể cả khi chỉ chứa chữ số.
- Mã bưu chính, mã khách hàng hoặc số tài khoản thường là chuỗi vì có thể có số 0 ở đầu và không dùng để tính toán.
- Số tiền nên được mô tả theo kiểu và định dạng phù hợp với cách serialize của ứng dụng; không tự chuyển chuỗi thành số hoặc ngược lại khi đổi định dạng.
- Trường boolean cần là boolean thực sự, không phải chuỗi `'true'`.
- Giá trị rỗng, thiếu thuộc tính và `null` là những trạng thái khác nhau trong JSON/OpenAPI; không dùng lẫn lộn.

Với YAML, ưu tiên scalar đơn giản, đặt dấu nháy cho các chuỗi dễ nhập nhằng và tránh dựa vào các tính năng YAML nâng cao nếu công cụ trong pipeline không hỗ trợ đồng nhất. Với JSON, luôn kiểm tra escape của dấu ngoặc kép, dấu gạch chéo ngược và ký tự xuống dòng.

## 5. Parser và công cụ tiêu thụ tài liệu

Định dạng quyết định parser nào cần dùng trước khi công cụ có thể xử lý mô hình OpenAPI. Sau bước parse, các công cụ thường làm việc với cấu trúc dữ liệu đã được chuẩn hóa.

| Công cụ hoặc quy trình | JSON | YAML |
|---|---|---|
| Trình duyệt mở trực tiếp endpoint | Thường hiển thị nội dung JSON | Có thể hiển thị YAML dạng văn bản |
| JavaScript `JSON.parse` | Đọc trực tiếp | Không đọc YAML trực tiếp |
| YAML parser | Không cần thiết | Cần parser YAML |
| OpenAPI validator | Hỗ trợ khi validator nhận JSON | Hỗ trợ khi validator nhận YAML |
| Git diff | Có thể nhiều dấu ngoặc và dấu phẩy | Thường gọn hơn với cấu trúc lồng nhau |
| Sinh client hoặc mock server | Dùng được nếu công cụ hỗ trợ OpenAPI JSON | Dùng được nếu công cụ hỗ trợ OpenAPI YAML |

Không phải mọi công cụ đều tự nhận dạng định dạng trong mọi tình huống. Khi gọi API hoặc cấu hình pipeline, nên cung cấp đúng URL, phần mở rộng file hoặc content type theo yêu cầu của công cụ. Nếu parser JSON nhận nội dung YAML, lỗi sẽ xảy ra trước khi công cụ kiểm tra được OpenAPI.

Ví dụ, trong JavaScript:

```javascript
// Đọc tài liệu JSON
const openApiDocument = JSON.parse(jsonText);
```

Với YAML, cần dùng thư viện parser YAML rồi nhận về object tương đương:

```javascript
// Ví dụ với package yaml
import { parse } from 'yaml';

const openApiDocument = parse(yamlText);
```

Sau khi parse, công cụ có thể truy cập `openApiDocument.paths`, `openApiDocument.components` hoặc các trường khác mà không phụ thuộc cú pháp nguồn ban đầu.

## 6. Swagger UI hiển thị JSON và YAML như thế nào?

Swagger UI không hiển thị nguyên văn dấu ngoặc JSON hay thụt lề YAML làm giao diện API. Nó tải tài liệu OpenAPI từ URL được cấu hình, parse tài liệu và dựng giao diện dựa trên các thành phần như tags, paths, operations, parameters, schemas, responses và security.

Do đó, nếu JSON và YAML mô tả cùng một mô hình OpenAPI, Swagger UI sẽ trình bày cùng các operation và thông tin tương ứng. Người dùng vẫn nhìn thấy endpoint, mô tả, biểu mẫu nhập parameter, request body, response và nút thử request theo cấu hình của Swagger UI. Việc nguồn là JSON hay YAML không làm xuất hiện một giao diện nghiệp vụ khác.

Trong cấu hình mặc định, Swagger UI thường sử dụng endpoint JSON `/v3/api-docs`. Nếu muốn giao diện đọc endpoint YAML, có thể cấu hình URL tài liệu, ví dụ:

```yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs.yaml
```

Tên thuộc tính và cách kết hợp với danh sách nhiều tài liệu cần được đối chiếu với phiên bản springdoc đang sử dụng. Nếu đã cấu hình `springdoc.swagger-ui.urls`, cần bảo đảm URL của từng tài liệu trong danh sách trỏ đến đúng endpoint JSON hoặc YAML.

Những yếu tố thực sự ảnh hưởng đến cách Swagger UI hiển thị gồm:

- `tags` và thứ tự các tag trong tài liệu, ảnh hưởng đến cách nhóm operation.
- `summary`, `description`, `operationId` và `deprecated`, ảnh hưởng đến nội dung và nhãn thao tác.
- `parameters`, `requestBody`, `responses` và schema, ảnh hưởng đến biểu mẫu nhập liệu và thông tin request/response.
- `securitySchemes` cùng `security`, ảnh hưởng đến phần khai báo xác thực và thao tác authorize.
- Cấu hình Swagger UI, phiên bản giao diện và cách tài liệu được nạp.

Nếu Swagger UI hiển thị khác nhau giữa hai nguồn JSON và YAML, hãy tải cả hai, parse chúng rồi so sánh mô hình OpenAPI. Khác biệt thường đến từ nội dung hai tài liệu, cấu hình URL, nhóm API, phiên bản Swagger UI hoặc cache, thay vì bản thân định dạng.

## 7. Xuất JSON và YAML từ springdoc

Springdoc cung cấp hai endpoint mặc định để lấy tài liệu. Có thể tải riêng từng định dạng:

```bash
curl.exe -fS http://localhost:8080/v3/api-docs -o openapi.json
curl.exe -fS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
```

Nếu ứng dụng thay đổi `springdoc.api-docs.path`, cần dùng đường dẫn mới và endpoint YAML tương ứng. Nếu ứng dụng có context path hoặc reverse proxy prefix, URL gọi từ bên ngoài cũng cần có tiền tố đó.

Tài liệu của một nhóm API có thể được cấu hình riêng. Khi đó, cần tải đúng tài liệu nhóm thay vì mặc định lấy tài liệu tổng. Swagger UI cũng có thể trỏ đến một hoặc nhiều URL tài liệu; cần xác minh URL đang dùng là URL JSON hay YAML và tương ứng với nhóm nào.

Không cần duy trì hai bộ annotation chỉ để sinh hai định dạng. Controller, DTO và cấu hình OpenAPI là nguồn dữ liệu; springdoc tuần tự hóa cùng mô hình thành JSON hoặc YAML.

## 8. Lựa chọn định dạng theo mục đích sử dụng

Không có định dạng nào tốt hơn trong mọi trường hợp. Chọn dựa vào cách tài liệu được tạo, review, xử lý và phân phối.

| Tình huống | Lựa chọn thường thuận tiện | Lý do |
|---|---|---|
| Lưu đặc tả trong Git để người phát triển review | YAML | Gọn, dễ đọc và có thể dùng comment cho ghi chú nội bộ |
| Trao đổi với hệ thống chỉ nhận JSON | JSON | Phù hợp trực tiếp với parser và API JSON |
| Xử lý bằng JavaScript mà không thêm parser | JSON | Có thể dùng `JSON.parse` |
| Mô tả dài, nhiều schema lồng nhau | YAML hoặc JSON | YAML thường dễ đọc hơn; JSON vẫn phù hợp nếu công cụ yêu cầu |
| Sinh client, mock hoặc kiểm thử hợp đồng | Cả hai | Chọn định dạng mà công cụ hỗ trợ và thống nhất trong pipeline |
| Tích hợp Swagger UI | Cả hai | Giao diện đọc mô hình OpenAPI sau khi parse |

Một nhóm có thể lưu YAML làm bản đặc tả dễ review, đồng thời cung cấp JSON cho hệ thống tự động. Điều cần giữ nhất quán là cả hai bản phải được sinh từ cùng phiên bản ứng dụng và cùng cấu hình OpenAPI. Không chỉnh sửa riêng một bản rồi để hai định dạng mô tả hai hợp đồng khác nhau.

## 9. So sánh hai bản tài liệu đúng cách

So sánh trực tiếp văn bản JSON với YAML thường tạo ra nhiều khác biệt hình thức vì hai định dạng có cấu trúc ký tự khác nhau. Để xác định hợp đồng có thực sự thay đổi hay không, nên parse cả hai về cùng một mô hình rồi so sánh dữ liệu.

Quy trình có thể thực hiện như sau:

1. Tải JSON và YAML từ cùng ứng dụng, cùng profile và cùng nhóm tài liệu.
2. Parse JSON bằng JSON parser và YAML bằng YAML parser tương thích.
3. Chuẩn hóa cách biểu diễn nếu công cụ so sánh yêu cầu, nhưng không tự loại bỏ các trường có ý nghĩa.
4. So sánh các trường OpenAPI như `openapi`, `info`, `servers`, `paths`, `components` và `security`.
5. Nếu có khác biệt, xác định đó là thay đổi dữ liệu hay chỉ khác thứ tự, định dạng chuỗi và cách trình bày.
6. Chạy validator OpenAPI và kiểm thử hợp đồng trên tài liệu được chọn để phân phối.

Trong JSON, thứ tự thuộc tính của object không mang ý nghĩa hợp đồng. Tương tự, không nên dựa vào thứ tự trình bày khóa trong YAML để xác định API nào có ưu tiên cao hơn. Tuy nhiên, thứ tự của array là một phần dữ liệu và có thể ảnh hưởng đến cách công cụ trình bày một số nội dung; không sắp xếp lại array một cách tùy tiện khi chuẩn hóa.

## 10. Lỗi thường gặp khi chuyển đổi hoặc hiển thị

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JSON parser báo lỗi khi đọc YAML | Dùng parser không đúng định dạng | Chọn YAML parser hoặc tải endpoint JSON |
| YAML parser đọc `version` thành số | Chuỗi phiên bản không được đặt trong dấu nháy | Đặt giá trị chuỗi như `'1.0'` trong dấu nháy |
| `$ref` trở thành giá trị rỗng | Dấu `#` bị hiểu là comment YAML | Đặt giá trị `$ref` trong dấu nháy |
| Mã response bị đọc thành số | Khóa mã trạng thái không được quote | Dùng `'200'`, `'404'` và các khóa dạng chuỗi |
| JSON không hợp lệ sau khi sửa tay | Thiếu dấu phẩy, escape sai hoặc có comment/trailing comma | Chạy JSON parser và sửa cú pháp |
| YAML lỗi do thụt lề | Dùng tab, sai cấp lồng nhau hoặc scalar chưa quote | Dùng khoảng trắng nhất quán và validator YAML |
| Swagger UI không đổi khi chuyển sang YAML | UI vẫn đang tải URL JSON cũ hoặc cache tài liệu | Kiểm tra URL tài liệu, cấu hình Swagger UI và cache |
| Swagger UI hiển thị operation khác nhau | Hai tài liệu không cùng nội dung, khác group hoặc profile | Parse và so sánh mô hình OpenAPI của cả hai |
| Comment biến mất sau khi xuất lại | Comment không thuộc mô hình dữ liệu OpenAPI | Đưa nội dung cần công bố vào `description` hoặc metadata |

## 11. Quy trình khuyến nghị cho ứng dụng Spring Boot

Một quy trình thực tế để duy trì JSON, YAML và Swagger UI đồng bộ:

1. Khai báo mapping Spring, DTO, validation và metadata OpenAPI tại nguồn.
2. Khởi động ứng dụng với profile cần kiểm tra.
3. Tải `/v3/api-docs` và `/v3/api-docs.yaml`.
4. Parse cả hai định dạng và xác nhận mô hình OpenAPI tương đương.
5. Chạy validator để phát hiện lỗi cú pháp và lỗi cấu trúc đặc tả.
6. Kiểm tra Swagger UI đang nạp đúng URL và hiển thị đúng nhóm API.
7. Gọi các endpoint đại diện để đối chiếu request, response và security với hợp đồng.
8. Lưu hoặc phân phối artifact theo phiên bản API, đồng thời bảo đảm JSON và YAML được sinh từ cùng một nguồn.

Nếu cần thay đổi cách trình bày trên Swagger UI, hãy xem xét metadata OpenAPI và cấu hình giao diện. Đổi từ JSON sang YAML chỉ thay đổi cách biểu diễn dữ liệu đầu vào; nó không tự đổi tags, thứ tự nhóm nghiệp vụ, mô tả endpoint hay biểu mẫu request.

## Kết luận

JSON và YAML là hai định dạng tuần tự hóa của cùng mô hình OpenAPI. JSON có cú pháp chặt chẽ và phù hợp với xử lý tự động; YAML gọn, dễ đọc và thuận tiện cho review thủ công. Swagger UI parse tài liệu rồi hiển thị dựa trên nội dung OpenAPI, vì vậy hai bản tương đương sẽ cung cấp cùng thông tin giao diện. Khi làm việc với springdoc-openapi, hãy chọn parser đúng định dạng, chú ý kiểu scalar và ký tự đặc biệt trong YAML, cấu hình đúng URL tài liệu cho Swagger UI và kiểm tra tính tương đương trước khi phân phối hợp đồng API.
