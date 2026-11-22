# Reject payload quá lớn, sâu hoặc phức tạp

API thường nhận dữ liệu từ client qua JSON, form, multipart upload hoặc query parameter. Dữ liệu hợp lệ về cú pháp vẫn có thể khiến server tiêu tốn quá nhiều bộ nhớ, CPU, thread, kết nối database hoặc băng thông. Một request có thể rất lớn, có cấu trúc lồng nhau quá sâu, chứa hàng trăm nghìn phần tử nhỏ hoặc kích hoạt một phép kiểm tra có chi phí tính toán cao.

Đây là một dạng lạm dụng tài nguyên (resource exhaustion), có thể dẫn đến từ chối dịch vụ (DoS) hoặc làm giảm khả năng phục vụ của các endpoint khác. API cần giới hạn kích thước và độ phức tạp của đầu vào ở nhiều lớp, từ gateway và HTTP server đến parser, schema, nghiệp vụ và các dịch vụ phụ thuộc. Các giới hạn phải phù hợp với nhu cầu thực tế của từng endpoint.

## 1. Vì sao payload hợp lệ vẫn có thể nguy hiểm

Không thể đánh giá mức tiêu tốn tài nguyên chỉ bằng việc request có đúng JSON hay không. Cần xem ít nhất bốn chiều:

| Chiều cần giới hạn | Ví dụ | Tài nguyên có thể bị ảnh hưởng |
|---|---|---|
| Kích thước byte | Một body JSON hoặc file upload rất lớn | Băng thông, bộ nhớ, dung lượng lưu trữ, thời gian đọc |
| Độ sâu cấu trúc | Object lồng nhau hàng nghìn cấp | Stack, parser, recursion, validator |
| Số lượng phần tử | Mảng chứa hàng trăm nghìn object nhỏ hoặc object có quá nhiều property | Bộ nhớ heap, CPU, số lần truy vấn và xử lý |
| Chi phí xử lý | Regex tốn thời gian, schema nhiều nhánh, truy vấn lọc phức tạp | CPU, thread, database và dịch vụ phụ thuộc |

Ví dụ, một request chỉ vài trăm kilobyte vẫn có thể chứa một cấu trúc JSON rất sâu hoặc một mảng có số lượng phần tử lớn. Ngược lại, một file vài chục megabyte có thể hợp lệ đối với endpoint upload tài liệu nhưng không phù hợp với endpoint cập nhật hồ sơ.

Các tình huống thường gặp:

- Client gửi body lớn hơn mức nghiệp vụ cần thiết.
- Client gửi request theo kiểu streaming hoặc chunked để vượt qua giới hạn chỉ dựa trên Content-Length.
- Body nén có kích thước truyền nhỏ nhưng giải nén thành dữ liệu rất lớn (decompression bomb).
- JSON có độ sâu lớn, nhiều node, chuỗi dài hoặc số có biểu diễn bất thường.
- Multipart request có quá nhiều part, file lớn hoặc header của từng part quá dài.
- Endpoint nhận batch, filter, sort hoặc biểu thức tìm kiếm có chi phí tăng nhanh theo đầu vào.
- API GraphQL cho phép truy vấn lồng sâu, nhiều alias hoặc nhiều nhánh có tổng chi phí rất cao.
- Client gửi nhiều request hợp lệ cùng lúc để làm cạn thread, connection pool hoặc quota của dịch vụ phụ thuộc.

Do đó, giới hạn kích thước body đơn lẻ chưa đủ để bảo vệ API.

## 2. Thiết kế giới hạn theo nhiều lớp

Một giới hạn có thể bị bỏ qua nếu chỉ đặt ở một tầng. Ví dụ, kiểm tra @Size trong controller diễn ra sau khi HTTP server đã nhận và parser đã tạo object trong bộ nhớ. Để từ chối sớm, hãy phân chia trách nhiệm:

| Lớp | Giới hạn nên áp dụng | Mục đích |
|---|---|---|
| Reverse proxy/API gateway | Body bytes, header size, thời gian nhận request, số request và concurrency | Chặn request vượt ngưỡng trước khi chuyển vào ứng dụng |
| HTTP server/framework | Request size, multipart size, read timeout, connection và request concurrency | Bảo vệ tiến trình ứng dụng và tài nguyên kết nối |
| Parser | Độ sâu, chiều dài chuỗi/số, số token hoặc giới hạn cấu trúc được thư viện hỗ trợ | Ngăn parser tiêu tốn tài nguyên khi giải mã body |
| Schema và validation | Số phần tử, số property, độ dài, khoảng giá trị và loại dữ liệu | Bảo đảm đầu vào phù hợp với contract của endpoint |
| Nghiệp vụ và truy vấn | Số bản ghi mỗi batch, page size, độ sâu truy vấn, số filter và ngân sách xử lý | Giới hạn chi phí do một yêu cầu tạo ra |
| Runtime và dependency | Timeout, concurrency, bounded queue, giới hạn truy vấn và retry | Ngăn một request chiếm tài nguyên vô hạn hoặc khuếch đại tải |

Giới hạn nên được đặt càng sớm càng tốt. Gateway có thể từ chối body quá lớn trước khi ứng dụng nhận dữ liệu; parser cần giới hạn cấu trúc trước khi tạo object hoàn chỉnh; validation nghiệp vụ kiểm tra các điều kiện mà tầng HTTP không thể hiểu.

Không có một con số phù hợp cho mọi API. Endpoint tìm kiếm có thể chỉ nhận body nhỏ, endpoint import có thể nhận file lớn hơn nhưng cần xử lý bất đồng bộ, còn endpoint thanh toán có thể cần body rất nhỏ và thời gian xử lý ngắn. Hãy xác định ngưỡng từ yêu cầu nghiệp vụ, kích thước dữ liệu thực tế, năng lực hạ tầng và mức rủi ro.

## 3. Giới hạn kích thước request body

### 3.1. Đếm byte ở tầng truyền nhận

Kích thước request body cần được đo bằng byte, không phải số ký tự. Chuỗi Unicode có thể chiếm nhiều byte cho một ký tự. Một request JSON chứa văn bản tiếng Việt, emoji hoặc dữ liệu mã hóa khác có thể có kích thước byte lớn hơn số ký tự hiển thị.

Gateway và HTTP server cần có giới hạn body cụ thể theo route hoặc nhóm endpoint. Ví dụ cấu hình Nginx:

~~~nginx
location /api/profile {
    client_max_body_size 1m;
}
~~~

Giá trị 1m chỉ là ví dụ. Cần đặt theo contract thực tế và cấu hình đồng bộ với giới hạn ở gateway, server và ứng dụng. Nếu các lớp có ngưỡng khác nhau, tài liệu vận hành phải nêu rõ tầng nào sẽ từ chối request và response lỗi dự kiến.

Không nên chỉ dựa vào header Content-Length. Header này có thể không có trong request streaming/chunked, và việc kiểm tra header không thay thế việc đếm số byte thực tế khi đọc body. Server hoặc gateway phải ngừng đọc và từ chối khi tổng số byte vượt ngưỡng, kể cả khi client không khai báo trước kích thước.

### 3.2. Kiểm soát request nén

Nếu API hỗ trợ Content-Encoding như gzip, cần giới hạn cả:

- Kích thước dữ liệu nhận được trước khi giải nén.
- Kích thước dữ liệu sau khi giải nén.
- Tỷ lệ hoặc ngân sách giải nén và thời gian xử lý.

Một body nén nhỏ có thể tạo ra lượng dữ liệu giải nén rất lớn. Nếu chỉ giới hạn byte trên đường truyền, ứng dụng vẫn có thể hết bộ nhớ sau khi giải nén. Việc giải nén cần diễn ra trong một luồng có giới hạn và phải dừng khi vượt ngưỡng dữ liệu đầu ra hoặc thời gian cho phép.

Chỉ chấp nhận những kiểu nén mà hệ thống thực sự cần. Từ chối encoding không được hỗ trợ bằng response phù hợp, thay vì cố đoán hoặc xử lý theo nhiều cách không nhất quán giữa proxy và ứng dụng.

### 3.3. Multipart và upload file

Với multipart/form-data, cần giới hạn riêng:

- Tổng kích thước request.
- Kích thước tối đa của mỗi file.
- Số lượng file và số lượng part.
- Kích thước tên file, tên field và header của từng part.
- Thời gian nhận upload và dung lượng lưu tạm.

Không nên đọc toàn bộ file vào bộ nhớ chỉ để kiểm tra kích thước sau khi nhận xong. Dùng streaming hoặc cơ chế lưu tạm có quota, kiểm tra tổng số byte trong lúc đọc và xóa dữ liệu tạm khi request bị từ chối hoặc xử lý thất bại. Với file cần xử lý tiếp, nên tách bước upload khỏi bước phân tích nội dung và áp dụng kiểm tra loại file, chữ ký nội dung cùng quy trình quét phù hợp.

Ví dụ cấu hình Spring Boot cho multipart:

~~~properties
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=12MB
~~~

Các giá trị trên chỉ minh họa cho upload file. Cấu hình multipart không phải giới hạn chung cho mọi JSON request; body JSON vẫn cần giới hạn ở gateway, HTTP server hoặc bộ đọc request của ứng dụng.

## 4. Giới hạn độ sâu và cấu trúc của JSON

Parser có thể gặp khó khăn khi xử lý object lồng nhau quá sâu, chuỗi rất dài, số có biểu diễn bất thường hoặc số lượng node quá lớn. Giới hạn parser phải được áp dụng trước hoặc trong quá trình parse, vì validation trên object đã được tạo không ngăn được chi phí parse ban đầu.

Các giới hạn nên xem xét:

- Độ sâu lồng nhau tối đa của object và array.
- Chiều dài tối đa của string và numeric literal.
- Số token hoặc node tối đa trong một document nếu parser hỗ trợ.
- Số property của một object và số phần tử của mỗi array.
- Phát hiện hoặc từ chối key trùng lặp nếu cách diễn giải khác nhau giữa các thành phần có thể gây lỗi bảo mật.

Ví dụ cấu hình giới hạn parser Jackson từ phiên bản 2.15 trở lên:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(64)
    .maxStringLength(100_000)
    .maxNumberLength(128)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper objectMapper = JsonMapper.builder(factory).build();
~~~

Đây là ví dụ minh họa; cần xác nhận phiên bản Jackson và cách đăng ký ObjectMapper trong HTTP message converter của ứng dụng. Nếu tạo một mapper riêng nhưng framework vẫn dùng mapper mặc định, các giới hạn sẽ không có tác dụng với request thực tế. Các giới hạn parser cũng không thay thế giới hạn byte của body hoặc giới hạn số phần tử theo nghiệp vụ.

### 4.1. Giới hạn theo JSON Schema và OpenAPI

Schema có thể mô tả nhiều giới hạn cấu trúc:

- maxLength cho chuỗi.
- maxItems cho mảng.
- maxProperties cho object.
- minimum, maximum, exclusiveMinimum hoặc exclusiveMaximum cho số.
- enum để giới hạn tập giá trị.
- additionalProperties: false khi object chỉ được phép có các property đã khai báo.

Ví dụ contract cho endpoint tạo đơn hàng:

~~~yaml
paths:
  /orders/batch:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [orders]
              properties:
                orders:
                  type: array
                  minItems: 1
                  maxItems: 50
                  items:
                    type: object
                    additionalProperties: false
                    required: [productId, quantity]
                    properties:
                      productId:
                        type: string
                        minLength: 1
                        maxLength: 64
                      quantity:
                        type: integer
                        minimum: 1
                        maximum: 100
~~~

Contract giới hạn một batch tối đa 50 đơn vị dữ liệu, độ dài mã sản phẩm và khoảng số lượng. Những ngưỡng này chỉ là ví dụ; hệ thống cần xác định giới hạn thật từ nghiệp vụ.

JSON Schema tiêu chuẩn không cung cấp một keyword tổng quát để giới hạn mọi dạng độ sâu hoặc tổng số node của một tài liệu. Dùng giới hạn parser hoặc validator có hỗ trợ ngân sách cấu trúc cho phần đó. Ngoài ra, maxItems ở một array không giới hạn tổng số phần tử trong tất cả các array lồng nhau; cần xem xét toàn bộ cấu trúc.

### 4.2. Tránh validation có chi phí không kiểm soát

Một schema hoặc biểu thức kiểm tra cũng có thể trở thành nguồn tiêu tốn CPU. Cần cẩn trọng với:

- Regex có backtracking phức tạp hoặc có thể gây catastrophic backtracking.
- Schema lồng nhiều oneOf, anyOf, not hoặc tham chiếu đệ quy sâu.
- Quy tắc uniqueItems trên mảng lớn, có thể yêu cầu so sánh nhiều phần tử.
- Hàm validation tùy chỉnh thực hiện truy vấn database hoặc gọi dịch vụ bên ngoài cho từng phần tử.
- Chuỗi tìm kiếm hoặc filter được chuyển trực tiếp thành biểu thức tốn kém.

Hãy giới hạn độ dài đầu vào trước khi chạy regex, chọn pattern có chi phí dự đoán được và tránh gọi dịch vụ phụ thuộc trong validator chạy đồng bộ. Nếu một batch cần kiểm tra dữ liệu tham chiếu, hãy thiết kế truy vấn theo lô có giới hạn thay vì tạo một truy vấn cho mỗi phần tử.

## 5. Giới hạn theo giao thức và loại nội dung

Không phải API nào cũng chỉ nhận JSON. Mỗi media type có đặc điểm và rủi ro parser riêng:

| Loại nội dung | Giới hạn cần xem xét |
|---|---|
| application/json | Body bytes, độ sâu, chiều dài string/number, số property và array item |
| multipart/form-data | Tổng body, số part, kích thước từng file, header và dung lượng lưu tạm |
| application/x-www-form-urlencoded | Tổng body, số field, chiều dài key/value |
| XML | Body bytes, độ sâu element, số node, kích thước text; tắt DTD và external entity khi không cần |
| GraphQL | Độ sâu query, số field/alias, batch size và chi phí ước tính của query |

Nếu API không hỗ trợ một media type, hãy trả 415 Unsupported Media Type. Không nên tự động parse một định dạng không được công bố trong contract.

### 5.1. XML và parser có khả năng mở rộng entity

Nếu endpoint nhận XML, cần cấu hình parser an toàn: tắt external entity và DTD khi nghiệp vụ không cần, giới hạn độ sâu, số node và kích thước text. Entity expansion có thể làm dữ liệu nhỏ tạo ra lượng xử lý hoặc bộ nhớ rất lớn. Kiểm thử phải xác nhận parser từ chối các cấu trúc bị cấm và không truy cập file hoặc tài nguyên mạng bên ngoài.

### 5.2. GraphQL và truy vấn có cấu trúc

Với GraphQL, body nhỏ vẫn có thể biểu diễn một truy vấn rất tốn kém. Ngoài giới hạn body bytes, cần đặt:

- Độ sâu truy vấn tối đa.
- Số lượng field và alias tối đa.
- Giới hạn batch operation.
- Giới hạn độ phức tạp hoặc cost dựa trên số lượng dữ liệu có thể được trả về.
- Timeout và giới hạn concurrency cho resolver.

Cost cần tính đến quan hệ một-nhiều. Ví dụ một query lấy 100 khách hàng, mỗi khách hàng 100 đơn, mỗi đơn 100 dòng hàng có thể tạo ra lượng dữ liệu rất lớn dù số field trong query không nhiều. Pagination phải có page size tối đa và resolver cần áp dụng giới hạn ở server.

## 6. Giới hạn chi phí nghiệp vụ và truy vấn

Sau khi parse và validate thành công, một request vẫn có thể tạo ra khối lượng công việc quá lớn. Cần áp dụng giới hạn ở cấp nghiệp vụ:

- Batch endpoint giới hạn số phần tử mỗi request và tổng số thao tác.
- Search/filter giới hạn số điều kiện, độ dài chuỗi tìm kiếm và các kiểu toán tử được phép.
- Sort chỉ chấp nhận các field được allowlist; tránh để client tạo biểu thức truy vấn tùy ý.
- Pagination có page size tối đa; không cho phép yêu cầu toàn bộ dữ liệu bằng một tham số đặc biệt.
- Export hoặc import lớn chuyển sang job bất đồng bộ có quota, trạng thái và giới hạn dung lượng.
- Truy vấn database có statement timeout, giới hạn số bản ghi và chỉ mục phù hợp.
- Gọi dịch vụ phụ thuộc có timeout, giới hạn concurrency và ngân sách retry.

Không nên cho phép một request giữ transaction hoặc connection database trong thời gian không giới hạn. Khi vượt deadline, cần hủy công việc phía server nếu có thể; chỉ trả timeout cho client mà vẫn tiếp tục truy vấn tốn kém ở backend sẽ không giải quyết được việc cạn tài nguyên.

## 7. Kiểm soát thời gian, tốc độ và concurrency

Giới hạn kích thước không ngăn được client gửi một request rất chậm hoặc gửi nhiều request vừa đủ nhỏ để chiếm hết tài nguyên. API cần thêm:

- Read timeout và giới hạn thời gian nhận body để giảm nguy cơ slow request.
- Request deadline cho toàn bộ quá trình xử lý.
- Rate limit theo danh tính, API key, tenant hoặc địa chỉ mạng phù hợp với mô hình truy cập.
- Giới hạn concurrency và bounded queue; tránh hàng đợi không giới hạn.
- Quota theo nghiệp vụ, chẳng hạn số bản ghi import hoặc số lần export trong một khoảng thời gian.
- Giới hạn retry và backoff để tránh khuếch đại tải khi dependency gặp sự cố.

Rate limit và body limit giải quyết các vấn đề khác nhau. Một request duy nhất có thể vượt kích thước cho phép dù người dùng chưa vượt rate limit; ngược lại, hàng nghìn request nhỏ có thể gây quá tải dù mỗi body đều hợp lệ. Cần kết hợp các lớp kiểm soát.

Với request chưa xác thực, có thể giới hạn theo IP hoặc tín hiệu mạng ở gateway. Sau xác thực, nên áp dụng thêm quota theo principal hoặc tenant để một client không thể tiêu thụ toàn bộ năng lực dùng chung. Cần tránh chỉ dựa vào IP trong môi trường có NAT hoặc proxy dùng chung.

## 8. Từ chối request và trả lỗi nhất quán

Khi request vượt giới hạn, API cần từ chối sớm và trả mã lỗi phù hợp:

| Tình huống | HTTP status thường dùng | Ý nghĩa |
|---|---:|---|
| Body vượt kích thước tối đa | 413 Payload Too Large | Request entity vượt giới hạn được phép |
| JSON/XML sai cú pháp hoặc vi phạm cấu trúc parser | 400 Bad Request | Request không thể được xử lý theo contract |
| Media type không được hỗ trợ | 415 Unsupported Media Type | Endpoint không nhận loại nội dung được gửi |
| Vượt rate limit hoặc quota tạm thời | 429 Too Many Requests | Client cần giảm tốc độ; có thể kèm Retry-After |
| Client không hoàn tất gửi request trong thời gian cho phép | 408 Request Timeout | Server chờ request quá thời gian nhận được cấu hình |
| Gateway chờ dịch vụ upstream quá lâu | 504 Gateway Timeout | Gateway không nhận được phản hồi kịp thời từ upstream |
| Server quá tải tạm thời | 503 Service Unavailable | Server hiện không thể nhận thêm công việc |

Mã lỗi cụ thể phụ thuộc tầng phát hiện và contract công khai. Gateway có thể trả 413 trước khi request tới ứng dụng; ứng dụng có thể trả 400 khi parser phát hiện nesting vượt ngưỡng. Các response cần có cấu trúc nhất quán và không chứa stack trace, tên thư viện, đường dẫn nội bộ hoặc chi tiết cấu hình giới hạn có thể hỗ trợ kẻ tấn công.

Ví dụ response lỗi đã chuẩn hóa:

~~~json
{
  "type": "about:blank",
  "title": "Payload Too Large",
  "status": 413,
  "detail": "Request body exceeds the allowed size.",
  "instance": "/api/orders/batch"
}
~~~

Thông điệp cho client nên đủ để hiểu request bị từ chối và cách điều chỉnh. Không trả lại toàn bộ body hoặc giá trị nhạy cảm trong thông báo lỗi. Nếu cung cấp giới hạn cụ thể trong tài liệu API, hãy bảo đảm thông tin đó được cập nhật đồng bộ với cấu hình thực tế.

## 9. Ví dụ tổ chức trong ứng dụng Java

Trong ứng dụng Java/Spring, cần phối hợp cấu hình proxy, servlet container, multipart resolver, JSON parser và Bean Validation.

Ví dụ Bean Validation cho DTO:

~~~java
public record CreateBatchRequest(
    @NotEmpty
    @Size(max = 50)
    List<@Valid CreateOrderItem> orders
) {}

public record CreateOrderItem(
    @NotBlank
    @Size(max = 64)
    String productId,

    @Min(1)
    @Max(100)
    int quantity
) {}
~~~

Controller có thể kích hoạt validation:

~~~java
@PostMapping("/orders/batch")
public ResponseEntity<Void> createBatch(
        @Valid @RequestBody CreateBatchRequest request) {
    orderService.createBatch(request);
    return ResponseEntity.accepted().build();
}
~~~

@Size, @Min và @Max giúp kiểm tra quy tắc nghiệp vụ sau khi request đã được parse và bind vào DTO. Chúng không thay thế body limit hoặc parser constraint. Nếu body chứa hàng triệu phần tử, việc tạo danh sách trước khi Bean Validation chạy đã có thể tiêu tốn nhiều bộ nhớ.

Vì vậy, cấu hình hoàn chỉnh cần có giới hạn byte ở proxy/server, giới hạn parser trước khi bind, giới hạn multipart cho upload và validation DTO cho từng endpoint. Cấu hình ở một tầng không tự động áp dụng cho tầng khác.

## 10. Kiểm thử các ranh giới và trường hợp lạm dụng

Test cần xác minh cả request hợp lệ lẫn request vượt giới hạn. Với mỗi ngưỡng, hãy kiểm tra giá trị ngay dưới ngưỡng, đúng ngưỡng và vượt ngưỡng. Cần chạy test qua đường HTTP thực tế để xác nhận proxy, server và parser cùng thực thi chính sách.

| Nhóm test | Trường hợp cần có | Kết quả mong đợi |
|---|---|---|
| Body size | Body nhỏ hơn, bằng và lớn hơn giới hạn | Request trong ngưỡng được xử lý; request vượt ngưỡng bị từ chối |
| Header length | Header hoặc query string quá dài | Bị từ chối ở tầng phù hợp |
| Streaming/chunked | Không có Content-Length, gửi body vượt ngưỡng theo từng chunk | Tổng byte thực tế vẫn bị giới hạn |
| Compression | Body nén nhỏ nhưng giải nén rất lớn | Bị dừng khi vượt giới hạn đầu ra hoặc ngân sách giải nén |
| JSON depth | Nesting ngay dưới, bằng và vượt giới hạn | Parser từ chối cấu trúc vượt ngưỡng |
| JSON structure | Quá nhiều property, array item, token, string hoặc numeric literal | Bị parser/schema/validation từ chối đúng lớp |
| Duplicate key | Object có key trùng lặp | Bị từ chối hoặc xử lý theo một chính sách thống nhất, rõ ràng |
| Multipart | File lớn, nhiều file, nhiều part hoặc header part lớn | Không vượt quota bộ nhớ và dung lượng lưu tạm |
| Query complexity | Nhiều filter, sort không được phép hoặc batch quá lớn | Bị từ chối trước khi tạo công việc không giới hạn |
| Concurrency | Nhiều request đồng thời hoặc request đọc rất chậm | Hệ thống giữ được giới hạn thread, connection và queue |
| Error handling | Parser hoặc gateway từ chối request | Error response không lộ stack trace hoặc body nhạy cảm |

Nên có test tích hợp qua gateway/staging cho các giới hạn được cấu hình ở tầng hạ tầng. Unit test parser hoặc validator không chứng minh rằng giới hạn ở reverse proxy và HTTP server đang được bật trong môi trường triển khai.

Kiểm thử tải cần theo dõi CPU, heap, garbage collection, thread pool, connection pool, độ dài queue và latency. Một bài test chỉ xác minh status code 413 nhưng không kiểm tra server có đọc toàn bộ body vào bộ nhớ trước khi trả lỗi hay không có thể bỏ sót vấn đề quan trọng.

## 11. Giám sát và phản ứng khi có dấu hiệu lạm dụng

Nên ghi nhận metric theo endpoint và loại giới hạn:

- Số request bị từ chối do body size, parser depth, schema, multipart hoặc quota.
- Kích thước body nhận được và kích thước sau giải nén theo các bucket phù hợp.
- Thời gian nhận body, thời gian parse và thời gian validation.
- Tỷ lệ lỗi 400, 413, 415, 429 và 503.
- CPU, heap, garbage collection, active threads, connection pool và queue utilization.
- Số lần timeout hoặc hủy công việc ở database và dịch vụ phụ thuộc.

Log nên ghi request ID, endpoint, principal/tenant ở dạng phù hợp chính sách, loại giới hạn bị chạm và kích thước đo được. Không ghi toàn bộ request body, token hoặc dữ liệu cá nhân chỉ để phục vụ debug. Metric cần tránh label có cardinality cao như giá trị tùy ý từ client.

Khi một endpoint đột ngột có nhiều request vượt ngưỡng, nhóm vận hành có thể giảm quota, chặn nguồn gây lạm dụng theo chính sách, điều chỉnh concurrency hoặc tạm thời vô hiệu hóa chức năng tốn tài nguyên. Mọi thay đổi ngưỡng phải được đánh giá để không vô tình làm hỏng luồng hợp lệ của client.

## 12. Những sai lầm thường gặp

- Chỉ kiểm tra Content-Length: bỏ sót request streaming/chunked hoặc body thực tế vượt quá giá trị dự kiến.
- Chỉ giới hạn body ở gateway: ứng dụng có thể được gọi từ mạng nội bộ hoặc một đường triển khai khác không đi qua gateway đó.
- Chỉ dùng Bean Validation: validation thường chạy sau khi parser đã tạo object trong bộ nhớ.
- Chỉ giới hạn số byte: bỏ sót JSON sâu, nhiều node, regex tốn kém hoặc query có chi phí lớn.
- Chỉ giới hạn file upload: bỏ quên tổng multipart request, số part và dung lượng lưu tạm.
- Chỉ giới hạn dữ liệu nén: bỏ sót kích thước sau giải nén.
- Dùng một ngưỡng cho mọi endpoint: endpoint import, tìm kiếm và cập nhật đơn giản có nhu cầu tài nguyên khác nhau.
- Dùng queue không giới hạn: request vượt qua validation vẫn có thể tích tụ và làm cạn bộ nhớ.
- Retry không giới hạn: lỗi ở dependency bị khuếch đại thành quá tải toàn hệ thống.
- Trả lỗi parser nguyên bản: vô tình tiết lộ tên thư viện, vị trí file, stack trace hoặc dữ liệu request.
- Không test qua hạ tầng thực: cấu hình proxy và server có thể khác với môi trường unit test.

## 13. Checklist trước khi phát hành endpoint

- [ ] Contract xác định media type, kích thước body và giới hạn dữ liệu theo nhu cầu nghiệp vụ.
- [ ] Gateway và HTTP server giới hạn tổng byte thực nhận, kể cả request không có Content-Length.
- [ ] Request nén có giới hạn cả dữ liệu truyền và dữ liệu sau giải nén.
- [ ] Multipart giới hạn tổng body, từng file, số part và dung lượng lưu tạm.
- [ ] Parser có giới hạn độ sâu, chiều dài string/number và cấu trúc theo khả năng thư viện.
- [ ] Schema giới hạn array item, property, chuỗi và khoảng giá trị.
- [ ] Validation tùy chỉnh có chi phí dự đoán được; regex và schema phức tạp đã được xem xét.
- [ ] XML/GraphQL hoặc định dạng khác có giới hạn riêng nếu endpoint hỗ trợ.
- [ ] Batch, pagination, filter, sort và truy vấn có quota hoặc ngân sách xử lý.
- [ ] Read timeout, request deadline, rate limit, concurrency và queue được giới hạn.
- [ ] Request vượt ngưỡng nhận status code và error response nhất quán.
- [ ] Test có trường hợp dưới, bằng và vượt ngưỡng; có test chunked, compression và concurrency khi phù hợp.
- [ ] Metric và log cho phép phát hiện lạm dụng mà không lưu body hoặc dữ liệu nhạy cảm.

Reject payload quá lớn, sâu hoặc phức tạp là một phần của thiết kế API contract và bảo vệ tài nguyên. Khi giới hạn được đặt từ tầng nhận request đến parser và nghiệp vụ, API có thể từ chối đầu vào nguy hiểm sớm, giữ chi phí xử lý trong ngân sách và duy trì khả năng phục vụ cho các client hợp lệ.
