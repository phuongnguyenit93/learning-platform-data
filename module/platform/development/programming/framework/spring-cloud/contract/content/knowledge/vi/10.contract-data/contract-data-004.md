# Body từ tệp JSON, XML hoặc tài nguyên nhị phân

## 1. Vì sao cần lấy body từ tệp?

Khi xây dựng **Spring Cloud Contract**, một hợp đồng giữa producer và consumer thường mô tả cả điều kiện request lẫn response mà consumer trông đợi. Với dữ liệu nhỏ, có thể viết body ngay trong Groovy hoặc YAML DSL. Nhưng nếu payload là một hóa đơn JSON dài, tài liệu XML nhiều namespace, ảnh, PDF hoặc một tệp nhị phân thì cách viết trực tiếp trở nên khó đọc, khó so sánh và dễ sai.

Spring Cloud Contract hỗ trợ **lấy nội dung body từ tệp tài nguyên**:

- Với JSON, XML và dữ liệu văn bản: Groovy dùng `file('...')`; YAML dùng `bodyFromFile`.
- Với nội dung cần giữ nguyên dưới dạng **byte nhị phân**: Groovy dùng `fileAsBytes('...')`; YAML dùng `bodyFromFileAsBytes`.

Điểm quan trọng là tệp tài nguyên được **đọc khi công cụ xử lý contract** để sinh producer tests và stub; tệp không phải một đường dẫn mà HTTP consumer tự đi đọc khi gọi API. Vì vậy đường dẫn phải đúng với dự án có chứa DSL và tài nguyên phải có mặt trong quá trình build. 

Bài này thuộc chương **Dữ liệu hợp đồng** của module `SPRING_CLOUD_CONTRACT`. Mục tiêu là viết hợp đồng HTTP/messaging có body thực tế bằng Groovy/YAML DSL, phục vụ sinh test phía producer, đóng gói stub, chạy Stub Runner và phát hiện thay đổi API không tương thích trong CI.

Sau bài học, bạn có thể:

1. Phân biệt body khai báo trực tiếp, body lấy từ tệp văn bản và body lấy từ tệp nhị phân.
2. Đặt đúng tệp fixture theo đường dẫn tương đối của tệp contract.
3. Viết ví dụ request/response sử dụng tệp JSON với cả Groovy và YAML DSL.
4. Dùng tệp XML và XPath matcher để kiểm tra giá trị có thể thay đổi.
5. Dùng tệp PDF/ảnh/byte stream trong contract mà không chuyển nhầm thành String.
6. Chẩn đoán các lỗi thiếu tệp, sai media type, sai encoding, fixture lỗi thời và sai nội dung stub.
7. Thiết kế cách quản lý file fixture an toàn, có phiên bản và tái lập được trong CI.

> **Nguyên tắc:** Chọn cách tham chiếu tệp dựa trên **kiểu dữ liệu thực tế của body**, không dựa vào việc tệp dài hay ngắn. JSON/XML thường là nội dung văn bản có cấu trúc; PDF, ảnh, ZIP và dữ liệu opaque khác phải được xử lý như byte.

## 2. Bốn cách khai báo body cần phân biệt

| Trường hợp | Groovy DSL | YAML DSL | Khi nào dùng |
| --- | --- | --- | --- |
| Body khai báo ngay trong contract | `body(orderId: 'ORD-123')` | `body:` kèm các field | Payload nhỏ, dễ đọc |
| Body là chuỗi văn bản viết ngay trong contract | `body('{"status":"PAID"}')` | `body: '{"status":"PAID"}'` | Text hoặc JSON ngắn |
| Body lấy từ tệp văn bản | `body(file('response.json'))` | `bodyFromFile: response.json` | JSON, XML, văn bản dài |
| Body lấy từ tệp nhị phân | `body(fileAsBytes('receipt.pdf'))` | `bodyFromFileAsBytes: receipt.pdf` | PDF, ảnh, ZIP, byte stream |

Cú pháp `file(...)` và `fileAsBytes(...)` thuộc DSL Spring Cloud Contract. Đây không phải các lời gọi `new File(...)` hoặc `Files.readAllBytes(...)` do lập trình viên phải tự viết.

Chẳng hạn, với response JSON:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(file('order-response.json'))
}
~~~

Đoạn trên mang ý nghĩa: nội dung của `order-response.json` được đưa vào **response body** của contract.

Với response PDF:

~~~groovy
response {
    status OK()
    headers {
        header('Content-Type', 'application/pdf')
    }
    body(fileAsBytes('receipt.pdf'))
}
~~~

Đoạn thứ hai giữ body dưới dạng **byte**. Không lấy PDF bằng `file('receipt.pdf')` rồi coi đó là text; cách đọc văn bản có thể làm sai dữ liệu nhị phân.

### 2.1. File-backed body khác việc trả về đường dẫn file

Hai khai báo sau không tương đương:

~~~groovy
// Gửi chính chuỗi tên tệp trong HTTP body
body('receipt.pdf')
~~~

~~~groovy
// Gửi nội dung các byte của tệp
body(fileAsBytes('receipt.pdf'))
~~~

Ở ví dụ đầu, client nhận văn bản `receipt.pdf` nếu được truyền như literal. Ở ví dụ sau, client nhận nội dung nhị phân đã được nhúng vào stub/kiểm chứng theo cấu hình contract.

### 2.2. Tệp contract và tệp dữ liệu có vai trò riêng

**Tệp contract** xác định request, response, status, headers và các quy tắc khớp. **Tệp dữ liệu** chỉ cung cấp nội dung cho một body cụ thể. Dữ liệu đưa vào contract không tự định nghĩa toàn bộ hành vi API: producer vẫn phải nhận đúng method/path và trả status/header mà consumer đã thống nhất.

## 3. Tổ chức thư mục và cách Spring Cloud Contract tìm tệp

Một cấu trúc minh họa cho producer `Order Service`:

~~~text
order-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── orders/
                    ├── create_order.groovy
                    ├── create-order-request.json
                    ├── create-order-response.json
                    ├── get_invoice.groovy
                    └── invoice-sample.pdf
~~~

Nếu tệp `create_order.groovy` chứa:

~~~groovy
body(file('create-order-request.json'))
~~~

thì tên file được giải quyết **tương đối với thư mục chứa contract**, tức `src/test/resources/contracts/orders/` trong cấu trúc trên. Nó không được hiểu tương đối với thư mục đang chạy lệnh terminal hoặc thư mục package Java. 

Có thể chọn thư mục con cho tệp dữ liệu, miễn đường dẫn tham chiếu đúng:

~~~text
contracts/
└── orders/
    ├── create_order.groovy
    └── fixtures/
        ├── request.json
        └── response.json
~~~

Trong `create_order.groovy`:

~~~groovy
request {
    method 'POST'
    url '/api/orders'
    body(file('fixtures/request.json'))
}
~~~

**Đừng dùng đường dẫn tuyệt đối trên máy một thành viên**, ví dụ `C:\Users\dev\Desktop\request.json`. CI hoặc máy thành viên khác sẽ không có cùng đường dẫn. Tài nguyên phải được lưu cùng source contract hoặc được cung cấp ổn định bởi quy trình build.

### 3.1. Quy ước đặt tên fixture

Một số nguyên tắc dễ bảo trì:

- Đặt tên thể hiện **hành vi**, chẳng hạn `create-order-success-request.json`, `create-order-success-response.json`.
- Không dùng chung một fixture cho các trường hợp có ý nghĩa nghiệp vụ khác nhau chỉ để tiết kiệm vài dòng.
- Khi nhiều contract thật sự cần cùng payload, có thể tái sử dụng file, nhưng phải hiểu rằng sửa file chung sẽ thay đổi **tất cả** contract tham chiếu đến nó.
- Gắn phiên bản hoặc thư mục API `v1`/`v2` nếu các định dạng giao tiếp đang được hỗ trợ song song.
- Xem file fixture là một phần của **giao diện được cam kết**, cần code review tương tự file DSL.

## 4. Ví dụ JSON: dùng file cho cả request và response

Giả sử consumer gửi lệnh tạo đơn hàng:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
~~~

### 4.1. Nội dung tệp request JSON

Tệp mẫu `create-order-request.json`:

~~~json
{
  "customerId": "CUS-7",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-3", "quantity": 1, "unitPrice": 10000}
  ],
  "note": "Giao vào giờ hành chính"
}
~~~

### 4.2. Nội dung tệp response JSON

Tệp mẫu `create-order-response.json`:

~~~json
{
  "orderId": "ORD-123",
  "status": "CREATED",
  "currency": "VND",
  "totalAmount": 110000,
  "accepted": true
}
~~~

Hai payload trên là ví dụ tự chứa để đưa vào **file fixture** trong dự án thực hành. Khi bạn triển khai thật, cần tạo các tệp tại đường dẫn đã thống nhất với contract.

### 4.3. Tệp Groovy DSL

`create_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_from_json_file')
    description('Consumer tạo đơn hàng từ JSON và nhận mã đơn')

    request {
        method 'POST'
        url '/api/orders'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(file('create-order-request.json'))
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
        }

        body(file('create-order-response.json'))
    }
}
~~~

Ở đây:

1. `request.body(file(...))` đưa JSON trong file vào phần **request** của contract; stub sử dụng payload này để xác định điều kiện request theo các quy tắc matching đã tạo.
2. `response.body(file(...))` đưa JSON trong file vào phần **response** của contract; generated producer test dùng nó làm kỳ vọng, còn stub có response mẫu cho consumer.
3. `Content-Type: application/json` và `Accept: application/json` thuộc thỏa thuận HTTP; định dạng file `.json` không tự thêm các header này.
4. `status CREATED()` là HTTP `201`, không phụ thuộc việc body lấy từ file hay khai báo trực tiếp.

Một điểm cần nhớ: khi request body chứa giá trị cụ thể, contract có thể kiểm tra giá trị đó theo cách đã cấu hình. Nếu consumer được phép gửi nhiều giá trị khác nhau, cần thiết kế matcher hoặc thêm kịch bản phù hợp; **việc đọc body từ file không tự tạo matcher linh hoạt**.

### 4.4. Cấu hình YAML DSL tương đương

Để biểu diễn cùng tương tác bằng YAML, dùng `bodyFromFile`:

~~~yaml
name: create_order_from_json_file
description: Consumer tạo đơn hàng từ JSON và nhận mã đơn
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  bodyFromFile: create-order-request.json
response:
  status: 201
  headers:
    Content-Type: application/json
  bodyFromFile: create-order-response.json
~~~

`bodyFromFile` thuộc `request` hay `response` theo vị trí thụt dòng. Hai field giống nhau nhưng có chức năng khác nhau vì nằm ở **hai hướng giao tiếp khác nhau**.

Không dùng đồng thời `body` và `bodyFromFile` trong cùng một request/response mà không có chủ ý: một nội dung đơn lẻ nên có **nguồn dữ liệu rõ ràng**. Trường hợp muốn tùy biến một vài giá trị động, hãy dùng matcher và dữ liệu mẫu phù hợp thay vì khai báo body mâu thuẫn.

## 5. Vì sao JSON từ file vẫn cần kiểm tra kiểu và cấu trúc?

Hai file sau không có cùng schema:

~~~json
{"quantity": 2, "paid": true, "items": []}
~~~

~~~json
{"quantity": "2", "paid": "true", "items": {}}
~~~

Khác biệt bao gồm:

- `quantity` chuyển từ number sang String.
- `paid` chuyển từ boolean sang String.
- `items` chuyển từ array rỗng `[]` sang object rỗng `{}`.

Một consumer dùng kiểu mạnh như `int`, `boolean` hoặc `List<Item>` có thể không deserialize thành công khi nhận cấu trúc thứ hai. Vì thế fixture JSON cần giữ **đúng kiểu và cấp lồng nhau**, không chỉ đúng tên field.

### 5.1. Giá trị động trong file JSON

Một file JSON mẫu có thể chứa:

~~~json
{
  "orderId": "ORD-123",
  "status": "CREATED",
  "createdAt": "2026-11-24T02:00:00Z"
}
~~~

Nhưng producer thật có thể sinh `orderId` hoặc `createdAt` khác. Nếu contract yêu cầu đúng literal từng byte, kiểm chứng sẽ thất bại với thay đổi hợp lệ.

Spring Cloud Contract hỗ trợ **response body matchers**. Có thể giữ body mẫu lấy từ file, đồng thời khai báo matcher cho một số trường quan trọng:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }

    body(file('create-order-response.json'))

    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
        jsonPath('$.status', byEquality())
    }
}
~~~

Ví dụ này giả định file có các trường `orderId` và `status` như mẫu. Matcher `byRegex` kiểm tra định dạng ID; `byEquality` bảo vệ status nghiệp vụ đã cam kết.

Nếu thêm matcher cho `createdAt` thì **phải cập nhật fixture** để có trường đó và chọn kiểu kiểm tra thời gian tương ứng. Matcher quá rộng có thể làm test bỏ lọt thay đổi phá vỡ consumer; matcher quá chặt lại khiến test thất bại vì dữ liệu động.

### 5.2. Body từ file không tự bảo đảm mọi phần tử array

Nếu fixture chứa hai phần tử `items`, đừng mặc định generated test sẽ kiểm tra các tình huống mảng có số phần tử tùy ý. Một hợp đồng chỉ bảo vệ những gì DSL và matcher được cấu hình kiểm chứng. Với collection biến kích thước, hãy cân nhắc matcher về kiểu, số lượng phần tử, trường bắt buộc hoặc integration test phù hợp.

### 5.3. Định dạng file và cách kiểm tra

Trước khi commit fixture, xác định:

- JSON hợp lệ về cú pháp, không có dấu phẩy thừa.
- Number, Boolean, Null, String, Object và Array đúng kiểu.
- Đơn vị tiền tệ và định dạng thời gian được thống nhất.
- Field nào là bắt buộc, tùy chọn hoặc có thể vắng.
- Giá trị nào là dữ liệu mẫu cho stub, giá trị nào là cam kết không được thay đổi.

**Fixture lớn không có nghĩa là contract tốt hơn.** Cấu trúc nên đủ rõ để consumer hiểu và đủ chọn lọc để producer có thể tiến hóa mà không phá vỡ những kỳ vọng thực sự.

## 6. XML từ tệp: giữ nguyên cấu trúc, namespaces và media type

Một số hệ thống kết nối với ứng dụng doanh nghiệp cũ, đối tác thanh toán hoặc SOAP/XML endpoint. Trong XML, phần tử, thuộc tính, namespace, văn bản và thứ tự phần tử có thể mang ý nghĩa nghiệp vụ.

Ví dụ `invoice-request.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<InvoiceRequest>
  <OrderId>ORD-123</OrderId>
  <IncludeDetails>true</IncludeDetails>
</InvoiceRequest>
~~~

Ví dụ `invoice-response.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <InvoiceId>INV-777</InvoiceId>
  <OrderId>ORD-123</OrderId>
  <Currency>VND</Currency>
  <Amount>110000</Amount>
</Invoice>
~~~

### 6.1. Groovy DSL tham chiếu file XML

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_invoice_from_xml_file')

    request {
        method 'POST'
        url '/api/invoices/lookup'

        headers {
            contentType(applicationXml())
            accept(applicationXml())
        }

        body(file('invoice-request.xml'))
    }

    response {
        status OK()

        headers {
            contentType(applicationXml())
        }

        body(file('invoice-response.xml'))
    }
}
~~~

Ở đây `file(...)` phù hợp vì XML được lưu dưới dạng **văn bản**. Spring Cloud Contract hỗ trợ HTTP XML body dưới dạng `String` hoặc `GString`, và hỗ trợ kiểm tra XML với XPath matcher. Khi dùng file, DSL lấy nội dung văn bản để đưa vào body. 

### 6.2. YAML DSL tương đương

~~~yaml
name: get_invoice_from_xml_file
request:
  method: POST
  url: /api/invoices/lookup
  headers:
    Content-Type: application/xml
    Accept: application/xml
  bodyFromFile: invoice-request.xml
response:
  status: 200
  headers:
    Content-Type: application/xml
  bodyFromFile: invoice-response.xml
~~~

Đừng gắn `application/json` chỉ vì bạn đã quen test JSON. Một request/response XML phải mô tả media type mà hai bên thật sự sử dụng, chẳng hạn `application/xml` hoặc một media type XML có tên riêng đã thống nhất.

### 6.3. Dùng XPath để xử lý giá trị XML động

Nếu `InvoiceId` thay đổi theo mỗi lần chạy, có thể khai báo matcher:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationXml())
    }

    body(file('invoice-response.xml'))

    bodyMatchers {
        xPath('/Invoice/InvoiceId/text()', byRegex('INV-[0-9]+'))
        xPath('/Invoice/Currency/text()', byEquality())
    }
}
~~~

Khác với JSONPath (`jsonPath`), XML dùng **`xPath`**. Spring Cloud Contract có các XPath body matchers như `byRegex` và `byEquality`, nhưng `byType()` không được hỗ trợ cho XPath theo tài liệu tham khảo. Đừng sao chép `byType()` từ ví dụ JSON sang XML. 

**XPath với namespace:** Nếu XML có `xmlns` mặc định hoặc prefix, XPath cần chỉ rõ namespace hoặc chọn node bằng `local-name()`/`namespace-uri()` một cách phù hợp. Ví dụ XPath đơn giản `/Invoice/InvoiceId/text()` sẽ không tự khớp nếu các phần tử thật nằm trong namespace khác với biểu thức.

### 6.4. Khoảng trắng và encoding trong XML

XML có thể khác nhau về khoảng trắng, xuống dòng, attribute order và namespace prefix nhưng vẫn biểu diễn nội dung tương đương theo cách parse XML. Ngược lại, một số phần tử chứa văn bản mà khoảng trắng là dữ liệu có nghĩa. Contract cần tập trung vào **ý nghĩa mà consumer phụ thuộc**, sử dụng XPath thích hợp khi byte-by-byte comparison quá chặt.

Nếu tệp có khai báo `encoding="UTF-8"`, hãy lưu nó theo encoding tương ứng. Với XML có bảng mã đặc thù, kiểm tra cẩn thận môi trường build, header charset và cách deserialize của ứng dụng thật.

## 7. Binary body: PDF, ảnh, ZIP và byte stream

Dữ liệu nhị phân không phải String. File PDF chứa các byte mà việc giải mã như UTF-8 có thể làm mất dữ liệu hoặc thay đổi nội dung. Đó là lý do Spring Cloud Contract có cơ chế **file as bytes**.

### 7.1. Contract tải một bản PDF

Cấu trúc thư mục:

~~~text
src/test/resources/contracts/documents/
├── download_receipt.groovy
└── receipt-sample.pdf
~~~

Tệp `download_receipt.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('download_receipt_pdf')

    request {
        method GET()
        url('/api/documents/DOC-7/pdf')

        headers {
            accept('application/pdf')
        }
    }

    response {
        status OK()

        headers {
            header('Content-Type', 'application/pdf')
            header('Content-Disposition',
                   'attachment; filename="receipt.pdf"')
        }

        body(fileAsBytes('receipt-sample.pdf'))
    }
}
~~~

Giải thích:

- `fileAsBytes('receipt-sample.pdf')` là điểm khác biệt quan trọng: công cụ dùng **byte nội dung của tệp**, không coi PDF là XML/JSON hay text.
- `Content-Type: application/pdf` thông báo media type thực tế.
- `Content-Disposition` minh họa hợp đồng về tên tệp khi tải xuống; chỉ nên ràng buộc nếu consumer thật sự phụ thuộc vào header đó.
- Không khai báo `application/json` cho tài liệu PDF.
- Byte nội dung thường cần một fixture nhỏ, ổn định, có thể commit và phát hành trong build.

Nếu tài liệu được cá nhân hóa theo khách hàng hoặc đóng dấu thời gian, **so sánh nguyên toàn bộ PDF** có thể quá chặt. Chỉ sử dụng exact binary fixture khi byte identity thật sự là cam kết cần bảo vệ; nếu yêu cầu là “tài liệu hợp lệ, đúng loại và đúng nghiệp vụ”, kết hợp contract cho HTTP headers với integration/domain test để phân tích nội dung PDF bằng thư viện phù hợp.

### 7.2. YAML DSL cho PDF

~~~yaml
name: download_receipt_pdf
request:
  method: GET
  url: /api/documents/DOC-7/pdf
  headers:
    Accept: application/pdf
response:
  status: 200
  headers:
    Content-Type: application/pdf
    Content-Disposition: 'attachment; filename="receipt.pdf"'
  bodyFromFileAsBytes: receipt-sample.pdf
~~~

Trường `bodyFromFileAsBytes` nằm trong `response`, tương ứng với `body(fileAsBytes(...))` của Groovy.

### 7.3. Upload binary trong request

Một endpoint có thể nhận raw PDF upload dưới dạng `application/pdf`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('upload_pdf_document')

    request {
        method POST()
        url('/api/documents')

        headers {
            header('Content-Type', 'application/pdf')
        }

        body(fileAsBytes('upload-sample.pdf'))
    }

    response {
        status CREATED()
    }
}
~~~

YAML tương ứng:

~~~yaml
name: upload_pdf_document
request:
  method: POST
  url: /api/documents
  headers:
    Content-Type: application/pdf
  bodyFromFileAsBytes: upload-sample.pdf
response:
  status: 201
~~~

**Lưu ý:** Đây là upload **raw binary body**, không phải `multipart/form-data`. Với multipart, body còn được đóng gói theo boundary và part headers; cần dùng DSL/cấu hình multipart phù hợp thay vì lấy file bytes rồi coi chúng là toàn bộ multipart envelope.

### 7.4. Có bắt buộc dùng application/octet-stream?

Không. `application/octet-stream` là kiểu tổng quát cho dữ liệu nhị phân, trong khi `application/pdf`, `image/png` hoặc `application/zip` mô tả loại tệp cụ thể. Chọn đúng media type mà API đã công bố:

| Dữ liệu | Header thường gặp | Cách khai báo body |
| --- | --- | --- |
| PDF | `application/pdf` | `fileAsBytes('receipt.pdf')` |
| PNG | `image/png` | `fileAsBytes('photo.png')` |
| ZIP | `application/zip` | `fileAsBytes('archive.zip')` |
| Byte stream không có loại cụ thể | `application/octet-stream` | `fileAsBytes('payload.bin')` |
| JSON text | `application/json` | `file('response.json')` |
| XML text | `application/xml` | `file('response.xml')` |

Phần mở rộng của tệp fixture **không tự đặt header**; phải khai báo header đúng hợp đồng.

## 8. So sánh file văn bản và file nhị phân

| Tiêu chí | `file(...)` / `bodyFromFile` | `fileAsBytes(...)` / `bodyFromFileAsBytes` |
| --- | --- | --- |
| Kiểu dữ liệu được nhắm tới | Nội dung văn bản | Dãy byte |
| Tệp tiêu biểu | JSON, XML, text | PDF, PNG, ZIP, bin |
| Khả năng dùng matcher theo cấu trúc | JSONPath hoặc XPath khi định dạng phù hợp | Không dùng JSONPath/XPath trực tiếp lên byte opaque |
| Rủi ro nếu chọn sai | Có thể biến binary thành text hỏng | Khó tận dụng kiểm tra cấu trúc của JSON/XML |
| Nội dung stub | Văn bản/body từ fixture | Binary payload từ fixture |
| Công dụng | Test API trả cấu trúc dữ liệu | Test API truyền/tải tệp hoặc nội dung opaque |

**Quy tắc chọn nhanh:** Nếu có thể mở tệp và đọc như một tài liệu JSON/XML/text đúng encoding thì thường dùng `file(...)`. Nếu đó là ảnh, PDF, ZIP hoặc một format không dành để đọc như văn bản thì dùng `fileAsBytes(...)`.

Không tự đưa binary thành chuỗi base64 rồi truyền làm JSON body trừ khi **API thật sự định nghĩa base64 như một trường String**. Đó là một giao diện khác: phía consumer lúc này nhận JSON/text chứa base64 và tự giải mã, chứ không nhận raw bytes.

## 9. File body trong messaging contract

Spring Cloud Contract còn hỗ trợ hợp đồng thông điệp. Khi `Payment Service` phát event `PaymentAuthorized`, payload có thể đủ lớn để tách ra tệp JSON.

Ví dụ message body từ file:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description('Phát sự kiện xác nhận thanh toán')
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')

        headers {
            header('contentType', 'application/json')
        }

        body(file('payment-authorized.json'))
    }
}
~~~

Nội dung minh họa của `payment-authorized.json`:

~~~json
{
  "eventType": "PaymentAuthorized",
  "orderId": "ORD-123",
  "paymentId": "PAY-7",
  "currency": "VND",
  "amount": 110000
}
~~~

Producer verification cho message vẫn cần base class có trigger `publishAuthorizedPayment()` và cơ chế quan sát message được cấu hình. Chỉ có file JSON không bảo đảm producer thực sự phát đúng destination hoặc header.

Nếu message payload là binary, Spring Cloud Contract cho phép dùng phương thức file as bytes tương ứng. Tuy nhiên, việc cấu hình binder, serializer, broker và message verifier phải phù hợp với hệ thống. **Contract test không tự chứng minh at-least-once delivery, retry, thứ tự sự kiện hoặc idempotency**; các thuộc tính đó cần integration/resilience tests.

## 10. Dữ liệu từ tệp, versioning và hợp đồng của consumer

Tệp fixture là một phần của bộ contract, nhưng nó không phải “bản sao chân lý” của toàn bộ entity producer. Thay đổi file này cũng có thể thay đổi những gì producer test kiểm tra và stub trả về.

Ví dụ producer thay:

~~~json
{
  "orderId": "ORD-123",
  "status": "PAID"
}
~~~

thành:

~~~json
{
  "id": "ORD-123",
  "status": "PAID"
}
~~~

Nếu consumer còn đọc `orderId` thì thay đổi này có thể phá vỡ API. Không nên chỉ sửa tệp fixture để generated test xanh mà bỏ qua tác động tới consumer.

### 10.1. Những thay đổi thường cần xem xét

| Thay đổi ở fixture | Rủi ro tương thích | Cách xử lý |
| --- | --- | --- |
| Đổi tên hoặc xóa field mà consumer đọc | Cao | Giữ field cũ, phối hợp migration hoặc version mới |
| Đổi number thành String | Cao khi consumer giải mã mạnh kiểu | Thống nhất schema, cập nhật contract khi có đồng thuận |
| Thêm field mới mà consumer bỏ qua | Thường có thể tương thích | Xác nhận parser của consumer chịu được field lạ |
| Đổi `items: []` thành `items: null` | Có thể phá vỡ nhánh xử lý | Rà soát chính sách null/optional |
| Đổi XML namespace | Cao với XPath/serializer phụ thuộc namespace | Xem đây là thay đổi giao diện, kiểm tra các consumer |
| Đổi định dạng file tải về từ PDF sang PNG | Cao nếu consumer mong PDF | Cập nhật media type và hợp đồng theo phiên bản |
| Đổi một PDF mẫu có timestamp nhưng semantic không đổi | Có thể gây lỗi giả nếu so byte chính xác | Chọn fixture ổn định hoặc test nghiệp vụ ở tầng khác |
| Sửa đường dẫn file nhưng quên cập nhật DSL | Build lỗi khi tạo test/stub | Di chuyển file và tham chiếu trong cùng commit |

### 10.2. Vì sao cần commit fixture vào source control?

Generated tests và stub phải tái lập được. Nếu dùng file chỉ tồn tại trên máy người viết, CI không thể sinh hợp đồng tương đương.

Một thay đổi liên quan contract nên có đủ các phần:

1. Tệp DSL Groovy/YAML.
2. Tệp fixture JSON/XML/binary được DSL tham chiếu.
3. Base test class và dữ liệu setup tương thích với tình huống.
4. Thay đổi code producer khi cần đáp ứng hành vi mới.
5. Kiểm chứng consumer/stub nếu hợp đồng thay đổi về nghĩa.

Không commit dữ liệu thật có thông tin cá nhân, token hay tài liệu nội bộ nhạy cảm làm fixture. Hãy tạo **dữ liệu tổng hợp** có cấu trúc tương đương và loại bỏ metadata không cần thiết.

### 10.3. Cần kiểm tra cả payload khi phát hành stub

Stub artifact được sử dụng qua Stub Runner cần phản ánh đúng body mà consumer sẽ xử lý. Nếu DSL tham chiếu một PDF hoặc JSON nhưng file không có trong bước sinh/đóng gói stub, bộ consumer tests có thể thiếu response đúng kỳ vọng. Hãy kiểm tra trên artifact sinh ra thay vì chỉ xác nhận tệp nguồn đang tồn tại.

## 11. Lỗi phổ biến với file-backed body

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm được `response.json` | Đường dẫn tương đối sai, file không được commit | Đặt file cạnh contract hoặc sửa đường dẫn tương đối |
| Build chạy local nhưng lỗi trên CI | Trỏ đường dẫn tuyệt đối, phân biệt chữ hoa/thường, file bị bỏ qua | Đưa fixture vào source control và dùng tên/path nhất quán |
| `Content-Type` không khớp | Header khai báo sai định dạng body | Dùng JSON/XML/PDF media type đã thỏa thuận |
| PDF/image sau khi tải bị hỏng | Đọc binary qua `file(...)` hoặc xử lý như text | Dùng `fileAsBytes(...)` hoặc `bodyFromFileAsBytes` |
| JSON không parse được | Dấu phẩy thừa, nháy không hợp lệ, encoding sai | Sửa nội dung JSON mẫu |
| XML không parse được | XML sai cú pháp, namespace/encoding không thống nhất | Kiểm tra tài liệu XML và serializer của producer |
| XPath matcher không tìm thấy node | XPath sai cấp hoặc namespace | Sửa XPath theo XML thực tế |
| Generated test fail vì ID ngẫu nhiên | Fixture dùng ID cố định quá chặt | Thêm matcher có ý nghĩa và giữ stub sample |
| Generated test fail vì timestamp trong PDF | Binary fixture không ổn định từng byte | Tách phần semantic cần test khỏi byte identity |
| Stub trả response cố định cho mọi request | Matcher request quá rộng nhưng body mẫu không thay đổi | Thu hẹp matcher, dùng response templating phù hợp hoặc thêm contract |
| Không có generated tests | Plugin chưa cấu hình, sai đường dẫn contract | Kiểm tra bước sinh test và số test thực thi |
| Sửa fixture làm nhiều contract fail | Một file được tái sử dụng ở nhiều nơi | Xem danh sách contract cùng tham chiếu; tách fixture nếu cần |
| Dữ liệu nhị phân quá lớn | Build/stub chậm hoặc artifact nặng | Dùng fixture tối thiểu vẫn đại diện được cam kết |
| Dùng binary DSL cho multipart request | Thiếu boundary/part metadata | Thiết kế contract multipart riêng |

### 11.1. Phân biệt lỗi fixture và lỗi tương thích

Nếu producer test trả `404` vì bản ghi `ORD-123` không có trong môi trường test, khả năng cao là fixture setup sai. Nếu test trả `200` nhưng thiếu field `orderId` mà consumer đã cam kết, đây có thể là breaking change.

Hãy kiểm tra theo thứ tự:

1. Contract DSL có được đọc và biên dịch không?
2. Những tệp được tham chiếu có tồn tại đúng nơi không?
3. Body fixture có đúng cú pháp, encoding, schema và media type không?
4. Generated request có đi tới đúng endpoint và đúng trạng thái dữ liệu không?
5. Response/message thực tế của producer khác ở điểm nào?
6. Consumer có phụ thuộc vào điểm khác biệt đó không?

Không sửa trực tiếp generated test để chữa lỗi vì mã đó sẽ được sinh lại từ DSL. Cách sửa bền vững là chỉnh contract, fixture, base class/setup hoặc code producer theo quyết định tương thích giữa các bên.

## 12. Đưa dữ liệu từ tệp vào kiểm chứng producer và CI

Luồng tích hợp thông dụng:

~~~mermaid
flowchart TD
    DSL["Groovy/YAML contract"] --> GEN["Sinh test và stub"]
    FIX["JSON/XML/PDF fixture"] --> GEN
    GEN --> TEST["Chạy producer verification"]
    TEST --> CHECK{"Hành vi producer khớp?"}
    CHECK -- "Không" --> FAIL["Build thất bại, xem lại contract/fixture/producer"]
    CHECK -- "Có" --> PUBLISH["Đóng gói và phát hành stub có phiên bản"]
    PUBLISH --> CONSUMER["Consumer test bằng Stub Runner"]
~~~

Trong dự án Maven đã cấu hình Spring Cloud Contract plugin và base class:

~~~bash
./mvnw -B clean verify
~~~

Trong dự án Gradle đã cấu hình plugin và task kiểm thử tương ứng:

~~~bash
./gradlew clean build
~~~

Hai lệnh trên là minh họa. Chúng chỉ kiểm chứng hợp đồng nếu **tệp DSL và fixture được tìm thấy, generated tests được biên dịch và thực thi**. Build xanh nhưng không sinh được contract test nào cần được điều tra.

### 12.1. Quy trình CI tối thiểu

- **Kiểm tra nguồn dữ liệu:** Các file `.json`, `.xml`, `.pdf` được khai báo tồn tại, đúng cách viết hoa và được đưa vào build.
- **Sinh test phía producer:** Chạy plugin, kiểm tra thông tin test được tạo từ contract.
- **Thực thi producer verification:** Xác nhận cả status, headers và body đáp ứng mẫu/matcher.
- **Đóng gói stub:** Chỉ phát hành artifact từ producer đã vượt qua kiểm chứng cần thiết.
- **Kiểm tra consumer:** Dùng Stub Runner chạy các client tests với đúng version stub, bao gồm tải file nhị phân nếu đó là giao diện công khai.
- **Rà soát breaking changes:** Trước khi chấp nhận cập nhật fixture, xác định consumer nào bị ảnh hưởng.

### 12.2. Kiểm chứng một binary response có tính ổn định

Với `GET /api/documents/DOC-7/pdf`:

- Contract test có thể bảo vệ `200`, `Content-Type` và raw body bytes theo fixture.
- Test bổ sung có thể kiểm tra PDF mở được, có số trang hoặc metadata nghiệp vụ đúng.
- Nếu PDF thay đổi theo từng lần render (timestamp, ID nội bộ, thứ tự đối tượng), exact byte fixture có thể không phù hợp làm điều kiện kiểm chứng chính.

Như vậy contract giúp bảo vệ **giao diện gửi/nhận tệp**, còn logic dựng tài liệu và tính đúng nghiệp vụ nên được kiểm thử ở tầng thích hợp.

## 13. Thực hành: một dịch vụ trả JSON, XML và PDF

Giả sử `Document Service` cung cấp ba API độc lập:

| Endpoint | Kỳ vọng | Dữ liệu fixture |
| --- | --- | --- |
| `POST /api/documents` | Nhận JSON metadata, trả `201` và JSON ID | `create-request.json`, `create-response.json` |
| `GET /api/documents/DOC-7/metadata.xml` | Trả XML metadata, `200` | `metadata-response.xml` |
| `GET /api/documents/DOC-7/file` | Trả raw PDF, `200` | `document-sample.pdf` |

### 13.1. Yêu cầu A — Chuẩn bị tệp

Trong bài thực hành tại dự án riêng, tạo:

~~~text
src/test/resources/contracts/documents/
├── create_document.groovy
├── create-request.json
├── create-response.json
├── get_document_metadata.groovy
├── metadata-response.xml
├── download_document.groovy
└── document-sample.pdf
~~~

Nội dung mẫu cho `create-request.json`:

~~~json
{
  "title": "Purchase order",
  "customerId": "CUS-7",
  "format": "PDF"
}
~~~

Nội dung mẫu cho `create-response.json`:

~~~json
{
  "documentId": "DOC-7",
  "status": "CREATED"
}
~~~

Nội dung `metadata-response.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Document>
  <DocumentId>DOC-7</DocumentId>
  <Format>PDF</Format>
  <Status>READY</Status>
</Document>
~~~

`document-sample.pdf` phải là **một file PDF thật**, có thể do nhóm tự tạo phục vụ kiểm thử. Đừng lưu chuỗi chữ “PDF test” vào tệp `.pdf` rồi tưởng đó là tài liệu PDF hợp lệ.

### 13.2. Yêu cầu B — Viết ba contract

- Contract tạo tài liệu: khai báo `body(file('create-request.json'))` và `body(file('create-response.json'))`.
- Contract XML: response header `application/xml` và `body(file('metadata-response.xml'))`.
- Contract PDF: response header `application/pdf` và `body(fileAsBytes('document-sample.pdf'))`.

Mỗi contract cần có tên riêng, method, URL và status phù hợp.

### 13.3. Gợi ý hợp đồng XML

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('document_metadata_xml')

    request {
        method GET()
        url('/api/documents/DOC-7/metadata.xml')
    }

    response {
        status OK()
        headers {
            contentType(applicationXml())
        }
        body(file('metadata-response.xml'))
        bodyMatchers {
            xPath('/Document/DocumentId/text()', byEquality())
        }
    }
}
~~~

### 13.4. Gợi ý hợp đồng PDF

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('document_pdf_download')

    request {
        method GET()
        url('/api/documents/DOC-7/file')
        headers {
            accept('application/pdf')
        }
    }

    response {
        status OK()
        headers {
            header('Content-Type', 'application/pdf')
        }
        body(fileAsBytes('document-sample.pdf'))
    }
}
~~~

### 13.5. Bài kiểm tra thay đổi không tương thích

Chạy producer verification của các contract đã tạo, rồi lần lượt thử:

1. Đổi JSON response field `documentId` thành `id`, nhưng consumer vẫn cần `documentId`.
2. Đổi XML node `<DocumentId>` thành `<Id>` khi XPath trong contract không đổi.
3. Đổi `Content-Type` của PDF sang `application/json`.
4. Thay PDF bằng text thường nhưng giữ tên tệp `.pdf`.
5. Sửa đường dẫn `fileAsBytes('document-sample.pdf')` thành tên file không tồn tại.

Ghi lại lỗi ở giai đoạn nào: parse contract, sinh test, producer verification hay consumer stub test. Với thay đổi 4, **khả năng phát hiện phụ thuộc matcher/fixture và kiểm tra bổ sung**; nếu bytes sai mà tiêu chí hợp đồng không kiểm tra tính hợp lệ PDF, hãy thêm kiểm thử phù hợp, không kết luận contract test đã bao phủ mọi yêu cầu.

### 13.6. Câu hỏi tự đánh giá

1. Vì sao phải dùng `fileAsBytes(...)` cho PDF thay vì `file(...)`?
2. `bodyFromFile` và `bodyFromFileAsBytes` khác nhau ở loại dữ liệu nào?
3. Một tệp XML có prefix namespace khác với XPath được viết không khai báo namespace thì có thể xảy ra lỗi gì?
4. Nếu producer trả ID ngẫu nhiên, nên viết fixture và matcher ra sao?
5. Nếu một tệp JSON được 5 contract cùng tham chiếu, sửa tệp đó sẽ ảnh hưởng bao nhiêu contract?
6. Vì sao chỉ chạy Stub Runner mà không chạy producer verification vẫn có thể bỏ sót producer phá vỡ API?
7. Vì sao response PDF từ fixture nhỏ có thể là một ví dụ tốt hơn việc commit một báo cáo 50 MB?

**Gợi ý trả lời:** Binary cần giữ nguyên bytes; JSON/XML là văn bản có cấu trúc; XPath phải khớp namespace; dữ liệu động cần sample ổn định và matcher; fixture dùng chung ảnh hưởng mọi contract tham chiếu; stub chỉ mô phỏng những gì đã khai báo; fixture nhỏ, ổn định làm CI chạy nhanh và dễ review.

## 14. Checklist trước khi hoàn tất contract có body từ file

- [ ] Đã xác định body là **văn bản** (JSON/XML) hay **nhị phân** (PDF/ảnh/ZIP).
- [ ] Groovy dùng `file(...)` hoặc `fileAsBytes(...)` đúng mục đích.
- [ ] YAML dùng `bodyFromFile` hoặc `bodyFromFileAsBytes` đúng vị trí trong `request`/`response`.
- [ ] Tệp fixture nằm ở đường dẫn tương đối đúng với **thư mục chứa contract**.
- [ ] Không dùng đường dẫn tuyệt đối phụ thuộc máy cá nhân.
- [ ] File có mặt trong source control và môi trường CI, tên file đúng cả chữ hoa/thường.
- [ ] HTTP method, URL, status, `Content-Type` và `Accept` được xác định theo giao diện thật.
- [ ] JSON và XML fixture hợp lệ về cú pháp và encoding.
- [ ] Matcher JSONPath/XPath chỉ kiểm tra những phần consumer cần và có giải pháp cho dữ liệu động.
- [ ] Với XML có namespace, XPath đã được thiết kế phù hợp.
- [ ] Với binary, dữ liệu mẫu ổn định, nhỏ và đúng định dạng thật.
- [ ] Không nhầm raw binary upload với multipart/form-data.
- [ ] Không đưa thông tin nhạy cảm hoặc dữ liệu khách hàng thật vào fixture.
- [ ] Generated producer tests được sinh **và chạy**; build thất bại khi có breaking change được hợp đồng bảo vệ.
- [ ] Stub được đóng gói từ producer đã xác minh và được consumer dùng đúng phiên bản qua Stub Runner.
- [ ] Những thuộc tính ngoài phạm vi contract test như chất lượng nội dung PDF, broker retry hoặc nghiệp vụ sâu có test bổ sung.

## 15. Tài liệu tham khảo

- [Spring Cloud Contract — Common Top-Level Elements, Passing Values from Files](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/common-top-elements.html): `file(...)`, `bodyFromFile`, `fileAsBytes(...)`, `bodyFromFileAsBytes` và quy tắc đường dẫn tương đối.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): khai báo HTTP body, headers, XML body, XPath matchers và namespace.
- [Spring Cloud Contract — Contract DSL Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matcher và sự khác biệt giá trị producer/consumer.
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): cấu hình sinh test, quản lý stub và tích hợp với vòng đời build.

**Ghi nhớ:** **Body từ file** giúp contract tập trung vào hành vi giao tiếp thay vì nhét payload dài trong DSL. Dùng `file(...)`/`bodyFromFile` cho JSON, XML và text; dùng `fileAsBytes(...)`/`bodyFromFileAsBytes` cho dữ liệu nhị phân. Giữ file fixture theo đường dẫn tương đối, có phiên bản, đúng media type và có matcher khi cần; kiểm chứng producer và phát hành stub trong CI để bảo vệ consumer trước thay đổi API không tương thích.
