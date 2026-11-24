# Body dạng chuỗi, XML và dữ liệu nhị phân

## Mục tiêu học tập

Trong **Spring Cloud Contract**, một HTTP contract mô tả request mà **consumer** gửi đến **producer**, cùng response mà producer cam kết trả về. Hợp đồng có thể được khai báo bằng **Groovy DSL** hoặc **YAML DSL**, sau đó dùng để sinh test phía producer, tạo stub và cho consumer chạy kiểm thử với **Stub Runner**.

Trong chương **Request HTTP**, bài này tập trung vào các trường hợp request body **không phải JSON object thông thường**. Sau bài học, bạn có thể:

- Phân biệt body dạng văn bản thuần, chuỗi JSON, XML và byte nhị phân ở cấp giao thức HTTP.
- Chọn đúng `Content-Type`, charset, cách biểu diễn `body` và mức độ so khớp.
- Viết contract Groovy/YAML cho `text/plain`, `application/xml` và `application/octet-stream`.
- Sử dụng `xPath(...)` với XML và `fileAsBytes(...)` / `bodyFromFileAsBytes` với tệp nhị phân.
- Phân biệt raw binary request với `multipart/form-data` có phần chứa tệp.
- Đưa các trường hợp này vào generated producer tests, stub test và CI mà không vô tình làm mất hoặc đổi dữ liệu.

## 1. Body của HTTP request thực chất là gì?

Ở tầng HTTP, body là **dãy byte** được gửi sau phần header. Kiểu nội dung của body do giao thức/ứng dụng quy định; header `Content-Type` cho biết producer cần giải mã dữ liệu theo định dạng nào. Các trường hợp thường gặp:

| Kiểu request | `Content-Type` điển hình | Body trên đường truyền | Cách mô tả trong contract |
|---|---|---|---|
| Văn bản thuần | `text/plain; charset=UTF-8` | Byte được mã hóa từ một chuỗi | `body('...')` hoặc `body: '...'` |
| JSON string | `application/json` | Văn bản JSON bao gồm dấu ngoặc kép của JSON string | Chuỗi JSON hợp lệ; không nhầm với raw text |
| XML | `application/xml` hoặc theo API là `text/xml` | Byte văn bản XML, có thể có namespace | XML dưới dạng String/GString trong Groovy; YAML block scalar trong YAML DSL |
| Nhị phân trực tiếp | `application/octet-stream`, `application/pdf`, `image/png`, … | Byte của tệp/payload, có thể không phải UTF-8 | `fileAsBytes('...')` hoặc `bodyFromFileAsBytes: ...` |
| Multipart | `multipart/form-data; boundary=...` | Nhiều phần, mỗi phần có header và body riêng | `multipart(...)` cùng mô tả part phù hợp |

Hai khái niệm dễ nhầm:

- **Content-Type** mô tả định dạng của **body được gửi**. `Accept` mô tả định dạng **response mà consumer muốn nhận**. Một consumer hoàn toàn có thể gửi XML nhưng yêu cầu producer trả JSON.
- **Chuỗi trong mã nguồn** không đồng nghĩa với **kiểu dữ liệu trên HTTP**. Chuỗi Java/Groovy có thể được mã hóa thành raw text, XML hoặc JSON; chỉ nhìn vào lời gọi `body(...)` chưa đủ để biết ngữ nghĩa nếu bỏ qua header và dữ liệu thực.

Ví dụ hai request dưới đây **khác nhau**:

~~~http
POST /api/notes HTTP/1.1
Content-Type: text/plain; charset=UTF-8

hello
~~~

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json

"hello"
~~~

Trường hợp thứ nhất mang byte của từ `hello`. Trường hợp thứ hai là **JSON string**, có dấu ngoặc kép nằm trong văn bản JSON. Nếu contract và producer không thống nhất, cùng một đoạn nhìn như “hello” có thể được xử lý bằng hai converter khác nhau.

### Ví dụ xuyên suốt

Giả sử **Document Service** là producer, còn **Checkout Service** là consumer cần gửi một ghi chú, một đơn hàng XML hoặc một tệp PDF. Ta thiết kế ba endpoint minh họa:

| Endpoint | Mục đích | Request body | Response |
|---|---|---|---|
| `POST /api/notes` | Gửi ghi chú giao hàng | Raw text UTF-8 | `202 Accepted`, JSON xác nhận |
| `POST /api/orders/xml` | Gửi đơn hàng theo XML | XML | `202 Accepted`, JSON xác nhận |
| `PUT /api/attachments/ATT-101/content` | Tải nội dung tệp lên | Byte của tệp | `204 No Content` |

Tên endpoint, payload và status chỉ là **quy ước của hệ thống minh họa**, không phải cấu hình mặc định của Spring Cloud Contract.

## 2. Body dạng chuỗi: text/plain

### Thiết kế giao diện

Consumer gửi ghi chú giao hàng:

~~~http
POST /api/notes HTTP/1.1
Content-Type: text/plain; charset=UTF-8
Accept: application/json

Giao sau 18:00
~~~

Producer trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"accepted":true}
~~~

Ở đây, body là **văn bản thuần**, không phải JSON object có trường `message`. Consumer phụ thuộc vào ba điều: request là `POST /api/notes`, chuỗi được truyền bằng UTF-8 và phản hồi thành công có status `202` cùng JSON `accepted`.

### Groovy DSL cho raw text

Lưu ví dụ này thành một file, chẳng hạn `src/test/resources/contracts/notes/acceptNote.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Nhan ghi chu giao hang dang text'

    request {
        method 'POST'
        url '/api/notes'
        headers {
            contentType('text/plain;charset=UTF-8')
            accept(applicationJson())
        }
        body('Giao sau 18:00')
    }

    response {
        status 202
        headers {
            contentType(applicationJson())
        }
        body(
            accepted: true
        )
    }
}
~~~

`body('Giao sau 18:00')` chỉ định giá trị mẫu trong request body. Khi tạo stub, Spring Cloud Contract dùng điều kiện request để nhận diện tình huống; khi sinh producer test, nó dùng request tương ứng rồi kiểm chứng response.

Nếu producer chấp nhận **mọi ghi chú hợp lệ**, một ví dụ cố định chưa đủ để kiểm thử các biến thể. Có thể bổ sung các hợp đồng cho ghi chú trống, quá dài hoặc chứa ký tự đặc biệt; tùy yêu cầu, dùng matcher của DSL thay vì ràng buộc chính xác một giá trị.

### YAML DSL tương đương

~~~yaml
description: 'Nhan ghi chu giao hang dang text'
request:
  method: POST
  url: '/api/notes'
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
    Accept: 'application/json'
  body: 'Giao sau 18:00'
response:
  status: 202
  headers:
    Content-Type: 'application/json'
  body:
    accepted: true
~~~

YAML `body: 'Giao sau 18:00'` có kiểu **string**. Chú ý `response.body.accepted: true` là **boolean**, không phải chuỗi `'true'`.

### Chuỗi rỗng và body không hiện diện

Ba tình huống sau cần phân biệt về mặt hợp đồng:

| Tình huống | Ý nghĩa |
|---|---|
| Raw text có nội dung `hello` | Request mang 5 byte ASCII/UTF-8 cho chữ `hello` |
| Body có độ dài 0 | Có thể là chuỗi rỗng; hành vi hợp lệ hay lỗi tùy API |
| Không gửi body | Có thể được framework xử lý khác với gửi một body trống |

Ở tầng nghiệp vụ, producer có thể **chấp nhận ghi chú rỗng**, **từ chối bằng `400`** hoặc **cho phép request không có body**. Điều cần làm là thống nhất từng trường hợp mà consumer sử dụng và tạo hợp đồng kiểm chứng; không mặc định chúng luôn tương đương.

## 3. Chuỗi nhiều dòng, newline và charset

Văn bản thuần đôi khi là CSV, log hoặc ghi chú nhiều dòng. Nếu hợp đồng so khớp nguyên văn, **xuống dòng và khoảng trắng cuối** có thể quyết định request có khớp hay không.

### YAML block scalar

~~~yaml
# Giữ dấu xuống dòng giữa hai hàng, bỏ newline cuối.
body: |-
  Giao sau 18:00
  Để hàng tại quầy bảo vệ
~~~

So sánh:

| Cú pháp YAML | Tác dụng chính |
|---|---|
| `|-` | Giữ các newline giữa dòng, bỏ newline cuối |
| `|` | Giữ newline kết thúc khối theo quy tắc clip |
| `>` | Gộp những xuống dòng thông thường thành dấu cách (folding) |
| `> -` *(viết liền là `>-`)* | Gộp dòng và bỏ newline cuối |

Ví dụ nếu dùng `body: |` thay cho `body: |-`, parser có thể tạo **thêm byte newline** cuối chuỗi. Nếu consumer gửi body không có newline đó và stub yêu cầu so khớp chính xác, test có thể thất bại.

Trong Groovy, có thể biểu diễn chuỗi nhiều dòng như sau:

~~~groovy
body('''Giao sau 18:00
Để hàng tại quầy bảo vệ''')
~~~

Ba dấu nháy đơn là cú pháp **Groovy**, không phải cú pháp YAML. Với cả hai DSL, hãy kiểm tra giá trị sau khi parse, đặc biệt là ký tự xuống dòng đầu/cuối khi định dạng code.

### Charset và độ dài byte

`Giao sau 18:00` có ký tự tiếng Việt nên số **byte** khi mã hóa UTF-8 không nhất thiết bằng số **ký tự**. Khi trao đổi hợp đồng:

- Xác định charset nếu định dạng là văn bản; với ví dụ này dùng `text/plain;charset=UTF-8`.
- Không tự thay UTF-8 bằng mã hóa mặc định của hệ điều hành.
- Nếu body có Unicode, kiểm tra bằng consumer client thực tế, không chỉ đọc file DSL bằng mắt.
- Phân biệt xuống dòng `LF` và `CRLF` khi hệ thống yêu cầu khớp byte chính xác. Khi yêu cầu không phụ thuộc byte, cân nhắc matcher hoặc xử lý chuẩn hóa phù hợp thay vì khóa cứng.
- `Content-Length` là số **byte của body trên đường truyền**, không phải số ký tự. Thường để HTTP client tự tính header này.

## 4. Body XML: giữ cấu trúc và ngữ nghĩa, tránh so khớp vô tình

XML thường dùng cho hệ thống tích hợp doanh nghiệp, SOAP hoặc API lâu đời. Khác với JSON map, XML có **element, attribute, text node, namespace** và có thể có thứ tự phần tử quan trọng theo schema.

Ví dụ request:

~~~http
POST /api/orders/xml HTTP/1.1
Content-Type: application/xml; charset=UTF-8
Accept: application/json

<order>
  <orderId>ORD-101</orderId>
  <quantity>2</quantity>
</order>
~~~

Producer nên đọc body này như **XML**, không phải chuỗi JSON. Trong Spring Cloud Contract, XML body được truyền vào `body` dưới dạng **String/GString**. Khi cần kiểm chứng phần tử cụ thể, dùng **XPath matcher** (`xPath`), thay vì JSONPath.

### Groovy DSL: XML request và XPath

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Nhan don hang XML'

    request {
        method 'POST'
        url '/api/orders/xml'
        headers {
            contentType('application/xml;charset=UTF-8')
            accept(applicationJson())
        }
        body('''<order>
  <orderId>ORD-101</orderId>
  <quantity>2</quantity>
</order>''')

        bodyMatchers {
            xPath('/order/orderId/text()', byRegex('ORD-[0-9]{3}'))
            xPath('/order/quantity/text()', byRegex('[1-9][0-9]*'))
        }
    }

    response {
        status 202
        headers {
            contentType(applicationJson())
        }
        body(
            accepted: true
        )
    }
}
~~~

Các dòng `xPath(...)` xác định điểm cần so khớp trong XML: `orderId` có dạng `ORD-` + ba chữ số, `quantity` chứa một số nguyên dương được biểu diễn bằng text. Trong XML, nội dung giữa hai thẻ ban đầu là **text**; kiểu integer của `quantity` đến từ schema/logic giải mã, không phải tự động do XML biến nó thành số.

**Quan trọng:** cách generated stub sử dụng matcher đối với request và cách generated producer test gửi giá trị mẫu là hai mặt khác nhau. Consumer test vẫn cần gửi một XML thực sự hợp lệ mà producer có khả năng xử lý, còn producer contract test phải được cấu hình để dựng được controller/service cần thiết.

### YAML DSL: XML với block scalar

~~~yaml
description: 'Nhan don hang XML'
request:
  method: POST
  url: '/api/orders/xml'
  headers:
    Content-Type: 'application/xml;charset=UTF-8'
    Accept: 'application/json'
  body: |-
    <order>
      <orderId>ORD-101</orderId>
      <quantity>2</quantity>
    </order>
  matchers:
    body:
      - path: '/order/orderId/text()'
        type: by_regex
        value: 'ORD-[0-9]{3}'
      - path: '/order/quantity/text()'
        type: by_regex
        value: '[1-9][0-9]*'
response:
  status: 202
  headers:
    Content-Type: 'application/json'
  body:
    accepted: true
~~~

`|-` giúp XML body không có newline cuối ngoài ý muốn; `matchers.body` áp dụng các quy tắc XPath. File YAML phải có đúng indentation; `body` ở đây là **một string XML**, không phải YAML mapping mô tả các element.

### Những lưu ý quan trọng với XML

1. **Tính hợp lệ:** XML phải có cấu trúc thẻ đúng; các ký tự như `&` trong text cần viết thành `&amp;` nếu không dùng cơ chế phù hợp.
2. **Namespace:** `<ns:order xmlns:ns="urn:example:orders">` khác với `<order>` không namespace. XPath không nhận diện đúng namespace có thể trả về kết quả rỗng. Với default namespace, XPath thường cần prefix được đăng ký hoặc điều kiện `local-name()`/`namespace-uri()`.
3. **Whitespace:** phần thụt lề, newline và text node có thể ảnh hưởng matcher. Hãy kiểm tra các giá trị consumer quan tâm, tránh giả định hai XML chỉ cần giống hình thức.
4. **Attribute và thứ tự:** thứ tự attribute XML thường không mang ngữ nghĩa; thứ tự các element có thể có nghĩa theo schema. Không biến thứ tự attribute thành quy tắc contract nếu consumer không dựa vào đó.
5. **Encoding:** header charset và khai báo `<?xml version="1.0" encoding="UTF-8"?>` nếu xuất hiện cần nhất quán với byte thật được gửi.
6. **Bảo mật parser:** producer cần cấu hình XML parser an toàn, đặc biệt là chống tải external entity/XXE. Một contract test với XML hợp lệ không tự kiểm chứng mọi trường hợp tấn công.

**Không dùng `byType()` để thay cho matcher XML:** bộ XPath matcher của Spring Cloud Contract hỗ trợ các kiểu như regex/equality, nhưng `byType()` không phải lựa chọn được hỗ trợ trong XML XPath matchers. Khi cần kiểm tra schema XSD hoặc ràng buộc nghiệp vụ phức tạp, bổ sung kiểm thử thích hợp ngoài hợp đồng cơ bản.

## 5. Request body nhị phân: đừng ép tệp thành chuỗi

Một file PDF, ảnh hoặc dữ liệu nhị phân bất kỳ có thể chứa byte không phải ký tự hợp lệ trong UTF-8. Nếu đọc nó bằng `String` hoặc chép vào YAML/Groovy text, dữ liệu có thể thay đổi:

- Byte bị chuyển mã hoặc thay bằng ký tự lỗi.
- Newline được chuẩn hóa.
- Dấu backslash hoặc chuỗi trông giống escape được diễn giải.
- Nội dung base64 bị dùng nhầm thành **dữ liệu thô**, khiến producer nhận **các ký tự base64** thay vì byte ban đầu.

Với HTTP, **raw binary upload** có thể như sau:

~~~http
PUT /api/attachments/ATT-101/content HTTP/1.1
Content-Type: application/octet-stream

<dãy byte nhị phân của tài liệu>
~~~

Dòng nằm giữa dấu ngoặc nhọn trong ví dụ chỉ để người đọc hình dung, **không phải body thực tế**. Body thật là các byte của file, không có ký tự `<` hay `>` nào được thêm vào trừ khi chúng vốn nằm trong file.

### Groovy DSL: `fileAsBytes(...)`

Spring Cloud Contract hỗ trợ đọc nội dung file dưới dạng byte bằng `fileAsBytes`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Nhan file nhi phan'

    request {
        method 'PUT'
        url '/api/attachments/ATT-101/content'
        headers {
            contentType(applicationOctetStream())
        }
        body(fileAsBytes('upload.pdf'))
    }

    response {
        status 204
    }
}
~~~

`upload.pdf` là file **fixture nhị phân** đặt trong dự án cùng vùng hợp đồng mà DSL có thể tham chiếu. File này phải thật sự tồn tại khi người học chạy quá trình sinh contract test/stub. Ví dụ cấu trúc:

~~~text
src/test/resources/contracts/attachments/
├── uploadContent.groovy
└── upload.pdf
~~~

`fileAsBytes('upload.pdf')` yêu cầu lấy **byte của file**, không lấy đường dẫn làm body. Với định dạng chỉ chấp nhận PDF, API có thể công bố `application/pdf` thay vì `application/octet-stream`; phải thống nhất với producer và consumer.

### YAML DSL: `bodyFromFileAsBytes`

~~~yaml
description: 'Nhan file nhi phan'
request:
  method: PUT
  url: '/api/attachments/ATT-101/content'
  headers:
    Content-Type: 'application/octet-stream'
  bodyFromFileAsBytes: 'upload.pdf'
response:
  status: 204
~~~

Giả sử YAML được lưu ở:

~~~text
src/test/resources/contracts/attachments/
├── uploadContent.yml
└── upload.pdf
~~~

Trong DSL của Spring Cloud Contract, trường `bodyFromFileAsBytes` trỏ tới file chứa byte. Đường dẫn được giải quyết tương đối với vị trí hợp đồng theo quy ước của công cụ, không phải tùy ý theo thư mục chạy lệnh trong terminal.

### `file(...)` khác `fileAsBytes(...)` thế nào?

| Mục đích | Groovy DSL | YAML DSL | Điều cần nhớ |
|---|---|---|---|
| Lấy nội dung từ file văn bản/JSON/XML | `body(file('request.xml'))` | `bodyFromFile: request.xml` | Chọn khi nội dung được xử lý như văn bản |
| Lấy nguyên byte của file nhị phân | `body(fileAsBytes('upload.pdf'))` | `bodyFromFileAsBytes: upload.pdf` | Tránh chuyển file thành string rồi mã hóa lại |

**Không giả định rằng `bodyFromFile: upload.pdf` sẽ bảo toàn mọi byte.** Với binary payload, hãy dùng API đọc byte dành riêng cho trường hợp này.

Với `204 No Content`, producer không trả response body. Nếu API muốn trả metadata của file vừa tải lên, có thể thiết kế `201 Created` hoặc `200 OK` cùng JSON response, nhưng phải thống nhất cụ thể; không gắn JSON body vào `204`.

## 6. Khi response cũng là binary

Một API tải file xuống đôi khi có request `GET` không body nhưng **response là byte**. Cùng kỹ thuật `fileAsBytes` / `bodyFromFileAsBytes` có thể được sử dụng ở **response**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tai tep nhi phan'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/content'
    }

    response {
        status 200
        headers {
            contentType(applicationOctetStream())
        }
        body(fileAsBytes('download.pdf'))
    }
}
~~~

YAML tương ứng:

~~~yaml
description: 'Tai tep nhi phan'
request:
  method: GET
  url: '/api/attachments/ATT-101/content'
response:
  status: 200
  headers:
    Content-Type: 'application/octet-stream'
  bodyFromFileAsBytes: 'download.pdf'
~~~

Hai ví dụ này chỉ minh họa **khả năng tái sử dụng cơ chế đọc byte**. Trong bài toán request HTTP, điểm chính vẫn là phân biệt request body raw text/XML/binary để producer tiếp nhận đúng. File `download.pdf` cũng phải tồn tại tại vị trí mà contract tham chiếu.

Khi consumer xử lý file tải xuống, test nên kiểm tra byte/content-type/đặc điểm tệp theo nghiệp vụ (chẳng hạn checksum, magic bytes hoặc khả năng mở file), thay vì chỉ xác nhận HTTP status.

## 7. Raw binary khác `multipart/form-data`

Người học dễ nhầm request upload file nào cũng là `application/octet-stream`. Thực tế có hai cách giao tiếp khác nhau:

~~~mermaid
flowchart TD
    A["Consumer cần gửi file"] --> B{"API yêu cầu kiểu upload nào?"}
    B -->|Raw body| C["Một dãy byte<br/>Content-Type: application/octet-stream hoặc MIME cụ thể"]
    B -->|Form upload| D["multipart/form-data<br/>Có boundary và các part"]
    C --> E["fileAsBytes / bodyFromFileAsBytes"]
    D --> F["multipart(...)<br/>Mô tả tên part, file, content type"]
~~~

**Raw binary** gửi trực tiếp byte của một payload làm body. **Multipart** là cấu trúc gồm nhiều phần, có thể trộn các field văn bản với file. Mỗi part có thể có `Content-Disposition` và `Content-Type` riêng; header tổng `Content-Type` chứa một tham số `boundary` để phân tách các part.

Ví dụ wire format minh họa của multipart:

~~~http
POST /api/attachments/multipart HTTP/1.1
Content-Type: multipart/form-data; boundary=AaB03x

--AaB03x
Content-Disposition: form-data; name="description"

Proof of delivery
--AaB03x
Content-Disposition: form-data; name="file"; filename="proof.txt"
Content-Type: text/plain

signed by recipient
--AaB03x--
~~~

Đây là **text part + file part có nội dung văn bản** để dễ quan sát. Nếu file là ảnh/PDF thật, nội dung part file sẽ là byte nhị phân. Header boundary chỉ ra cách chia phần; boundary thực tế có thể được HTTP client tạo khác nhau giữa các request.

Spring Cloud Contract có DSL `multipart(...)`. Ví dụ Groovy cho file part **dùng dữ liệu văn bản minh họa**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Nhan form kem file van ban'

    request {
        method 'POST'
        url '/api/attachments/multipart'
        headers {
            contentType('multipart/form-data;boundary=AaB03x')
        }
        multipart(
            description: 'Proof of delivery',
            file: named(
                name: 'proof.txt',
                content: 'signed by recipient',
                contentType: 'text/plain'
            )
        )
    }

    response {
        status 201
    }
}
~~~

Mục tiêu của ví dụ là cho thấy **tên field, filename, nội dung và MIME của part**. Nó không kiểm chứng upload PDF byte-for-byte. Với file thực, cần xem xét khả năng biểu diễn multipart binary của phiên bản DSL và thêm test tích hợp chuyên biệt nếu producer phải bảo toàn chính xác byte hoặc metadata của file.

**Đừng chuyển một API raw binary sang multipart hoặc ngược lại mà không cập nhật contract và consumer.** Đó là thay đổi định dạng request, dù hai API cùng “nhận một file”.

## 8. Thiết kế matcher thế nào để không khóa nhầm chi tiết?

Matcher giúp mô tả **ràng buộc mà consumer và producer cần cam kết**, thay vì cố định mọi byte nếu không có ý nghĩa.

| Loại body | Nên kiểm chứng | Cẩn trọng với |
|---|---|---|
| Raw text | Nội dung hoặc mẫu hợp lệ, charset, quy tắc rỗng/độ dài | Dấu cách, newline cuối, Unicode; matcher quá lỏng |
| XML | Element/attribute/XPath quan trọng, namespace, giá trị nghiệp vụ | XML so khớp nguyên văn khi serializer có thể thay indentation hoặc thứ tự attribute |
| Raw binary | Byte của fixture hoặc đặc điểm đã cam kết, Content-Type, giới hạn kích thước | Chuyển thành string, so sánh base64 như raw bytes, fixture quá lớn |
| Multipart | Field name, filename, content type từng part, dữ liệu bắt buộc | Boundary động, thứ tự part nếu API không quy định, kiểm tra sót file part |

Ví dụ, nếu API chỉ cần XML `orderId` đúng dạng và `quantity` dương, **XPath matcher** thường diễn đạt ý nghĩa rõ hơn việc yêu cầu toàn bộ XML phải khớp từng dấu cách. Nhưng nếu nhận XML có chữ ký số mà việc thay đổi byte hoặc canonicalization ảnh hưởng xác thực, test phải tôn trọng yêu cầu riêng của giao thức ký số.

Với PDF hoặc ảnh, một fixture nhỏ, ổn định giúp generated test dễ chạy. Tuy nhiên, **một fixture hợp lệ không tự chứng minh** hệ thống xử lý mọi file, mọi kích thước và mọi lỗi truyền tải. Các trường hợp file rỗng, quá lớn, sai MIME, PDF hỏng hoặc checksum không đúng cần test bổ sung theo hợp đồng nghiệp vụ.

## 9. Thiết kế phản hồi lỗi cho ba loại request

Cùng một endpoint có thể trả các lỗi khác nhau tùy nguyên nhân. Ví dụ:

| Request | Tình huống | Phản hồi có thể thống nhất | Ý nghĩa với consumer |
|---|---|---|---|
| `text/plain` | Ghi chú quá dài | `413 Content Too Large` hoặc `400 Bad Request` tùy chính sách API | Rút ngắn dữ liệu hoặc báo lỗi cho người dùng |
| `application/xml` | XML sai cú pháp | `400 Bad Request` + `INVALID_XML` | Không gửi lại cùng body chưa sửa |
| `application/xml` | XML hợp lệ cú pháp nhưng thiếu trường bắt buộc | `422 Unprocessable Content` hoặc `400` theo quy ước | Sửa dữ liệu nghiệp vụ |
| `application/octet-stream` | MIME không được hỗ trợ | `415 Unsupported Media Type` | Đổi định dạng file được phép |
| Raw binary/multipart | File vượt giới hạn | `413 Content Too Large` | Thông báo giới hạn và chặn upload |
| Upload bất kỳ | Lỗi hạ tầng tạm thời | `503 Service Unavailable` nếu API quy định | Consumer cân nhắc retry theo chính sách |

Mã status và lỗi ứng dụng trong bảng là **đề xuất minh họa**, không tự động được Spring Cloud Contract áp đặt. Khi producer và consumer đã thống nhất lựa chọn, mỗi trường hợp quan trọng nên có **một contract riêng** hoặc một tình huống kiểm thử phù hợp.

Tránh trả stack trace của XML parser hoặc đường dẫn lưu file nội bộ trong body lỗi. Hợp đồng lỗi nên công bố mã máy đọc được (`INVALID_XML`, `FILE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, …) và cấu trúc ổn định mà consumer có thể xử lý.

## 10. Từ contract đến generated test, stub và CI

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant C as Groovy/YAML contract
    participant P as Producer test
    participant S as Stub artifact
    participant U as Consumer test
    Dev->>C: Định nghĩa request text/XML/binary
    C->>P: Sinh producer contract test
    P->>P: Gửi request thực theo hợp đồng
    alt Producer đáp ứng
      P-->>S: Tạo/đóng gói stub đã kiểm chứng
      S-->>U: Stub Runner chạy stub đúng phiên bản
      U->>U: Gửi request bằng client thực
    else Sai body, header hoặc response
      P-->>Dev: Build thất bại, điều tra sai lệch
    end
~~~

### Phía producer

Producer cấu hình **Spring Cloud Contract Verifier** và plugin tương ứng, đặt contract dưới thư mục mà build đọc, đồng thời chuẩn bị base test class/môi trường test.

- Với raw text, generated test gửi request phù hợp với `Content-Type` và `body` được định nghĩa.
- Với XML, generated test gửi XML theo ví dụ; có thể dùng matcher để kiểm chứng hành vi cần thiết.
- Với binary, file fixture phải có sẵn trước khi chạy bước sinh test và stub. Không đặt tên file trong DSL rồi quên kiểm tra sự hiện diện của nó trong build.

Generated test đạt chỉ chứng minh producer đáp ứng **các tình huống đã mô tả**, không tự chứng minh mọi payload hợp lệ hoặc môi trường mạng/production.

### Phía consumer

Consumer dùng **Spring Cloud Contract Stub Runner** để tải hoặc khởi chạy stub của producer theo tọa độ/phiên bản được xác định. Test consumer phải dùng **HTTP client thật của ứng dụng**:

- Gửi raw text qua client đúng `Content-Type`, không tự serialize thành JSON string.
- Gửi XML với namespace và charset chính xác.
- Gửi byte của file bằng công cụ phù hợp (ví dụ resource/byte array) thay vì chuyển qua `String`.
- Đọc và xử lý response thành công/lỗi theo contract.

**Test consumer xanh với stub chưa chứng minh producer thật đúng**, vì stub là dữ liệu giả lập. Ngược lại, producer test xanh chưa chứng minh consumer dùng đúng cách. Để phát hiện thay đổi API không tương thích, CI cần chạy cả hai phía với phiên bản contract/stub tương ứng.

### Quy trình CI tối thiểu

1. Kiểm tra file hợp đồng Groovy/YAML và các fixture văn bản/nhị phân đã được commit tại đường dẫn hợp lệ.
2. Sinh và chạy generated producer tests theo phiên bản Spring Cloud Contract của dự án.
3. Chỉ sau khi producer tests đạt, đóng gói/publish candidate stub có tọa độ và version rõ ràng.
4. Chạy consumer tests dùng Stub Runner với **chính candidate stub đó**.
5. Nếu thay đổi `Content-Type`, cách encoding, XML schema/namespace hoặc raw binary ↔ multipart, đánh giá khả năng tương thích với consumer đang dùng phiên bản cũ trước khi phát hành.

Đừng dùng artifact `latest` không kiểm soát trong CI rồi kết luận kiểm thử đã xác nhận đúng phiên bản producer sẽ triển khai.

## 11. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Producer trả `415` khi consumer gửi ghi chú | Body là raw text nhưng Content-Type lại là `application/json` | Công bố và gửi đúng `text/plain;charset=UTF-8` |
| Stub không khớp request text | Newline cuối, dấu cách hoặc encoding khác nhau | Kiểm tra body sau YAML/Groovy parse và byte HTTP thực |
| Contract XML parse lỗi | Body XML thiếu escape, thẻ không đóng, ký tự `&` thô | Sửa XML/encoding, kiểm tra với XML parser phù hợp |
| XPath matcher không tìm thấy element | Namespace XML hoặc XPath sai | Kiểm tra prefix, URI namespace, `local-name()` khi cần |
| Matcher XML cho kết quả khó hiểu | Dùng JSONPath hoặc `byType()` như với JSON | Dùng XPath và matcher được DSL hỗ trợ |
| PDF đến producer bị hỏng | Đã chuyển binary thành String hoặc nhầm base64 | Dùng `fileAsBytes` / `bodyFromFileAsBytes`, kiểm tra byte thực |
| Build sinh stub lỗi thiếu file | Fixture nhị phân chưa có, sai path tương đối | Đặt file bên cạnh contract đúng đường dẫn, commit fixture |
| Server không đọc được file multipart | Consumer gửi raw binary hoặc sai tên part/boundary | Đối chiếu `multipart/form-data` và từng part |
| Consumer test xanh nhưng deploy lỗi | Test dùng stub cũ hoặc không chạy client thật | Pin version stub, kiểm tra chính client và pipeline producer |
| Build chạy rất chậm vì fixture lớn | Contract đính kèm payload nặng không cần thiết | Dùng fixture nhỏ có đại diện, kết hợp test hiệu năng/kích thước riêng |

## 12. Bài tập: chọn cách biểu diễn body

### Tình huống A: consumer gửi mã vận đơn

API `POST /api/tracking/codes` nhận một mã vận đơn dưới dạng raw text `000987`, có thể chứa số 0 đầu.

**Lựa chọn nên dùng:**

~~~yaml
request:
  method: POST
  url: '/api/tracking/codes'
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
  body: '000987'
response:
  status: 202
~~~

**Giải thích:** `'000987'` là string có số 0 đầu. Nếu viết YAML `body: 000987` không quote, parser có thể suy kiểu khác. Nếu endpoint mong raw text, không gửi JSON string `"000987"` như một JSON payload.

### Tình huống B: consumer gửi XML có namespace

Request body:

~~~xml
<o:order xmlns:o="urn:example:orders">
  <o:id>ORD-105</o:id>
  <o:quantity>3</o:quantity>
</o:order>
~~~

**Câu hỏi:** XPath `/order/id/text()` có luôn tìm được ID không?

**Đáp án:** Không. XML dùng namespace `urn:example:orders`, nên XPath phải xử lý namespace. Ví dụ cách không cần đăng ký prefix là dùng `local-name()` và `namespace-uri()` cho các node cần kiểm chứng. Khi thiết kế contract nên dùng XPath phù hợp với namespace thực và kiểm tra parser/matcher của Spring Cloud Contract.

### Tình huống C: consumer tải tệp PDF lên

Producer công bố `PUT /api/attachments/ATT-105/content` nhận byte PDF thô.

**Chọn cách viết phù hợp:**

~~~yaml
request:
  method: PUT
  url: '/api/attachments/ATT-105/content'
  headers:
    Content-Type: 'application/pdf'
  bodyFromFileAsBytes: 'sample.pdf'
response:
  status: 204
~~~

Cần đặt `sample.pdf` ở đường dẫn tương đối mà contract DSL tham chiếu được và giữ file là **byte nhị phân**. Nếu giao diện mới thay `application/pdf` bằng `multipart/form-data` mà không đồng thời chuyển consumer, đó là thay đổi không tương thích về request.

### Câu hỏi tự kiểm tra

1. Vì sao `Content-Type` và `Accept` không có cùng ý nghĩa?
2. Vì sao `body: |-` có thể khác `body: |` khi kiểm thử text?
3. XML namespace ảnh hưởng XPath matcher như thế nào?
4. Vì sao không nên truyền PDF qua `body: '...'` như một chuỗi thường?
5. `bodyFromFile` và `bodyFromFileAsBytes` khác nhau ở đâu?
6. Vì sao contract test của producer và test consumer với stub phải sử dụng cùng revision/phiên bản?
7. Hai cách raw binary và multipart có cùng HTTP request body không?

## 13. Tham khảo và ghi nhớ

Tài liệu chính thức của Spring Cloud Contract mô tả [HTTP contracts và XML/XPath](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html), cũng như cách [đọc payload từ file dưới dạng văn bản hoặc byte](https://docs.spring.io/spring-cloud-contract/docs/current/reference/htmlsingle/index.html) và [YAML DSL schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html). Kiểm tra lại cú pháp theo **phiên bản Spring Cloud Contract** đang dùng trước khi áp dụng nguyên xi ví dụ vào dự án.

**Body của HTTP request không mặc nhiên là JSON.** Với raw text cần thống nhất encoding và newline; với XML cần kiểm chứng cấu trúc, namespace và XPath; với dữ liệu nhị phân cần bảo toàn byte bằng `fileAsBytes` hoặc `bodyFromFileAsBytes`; với multipart phải mô tả đúng các part. Spring Cloud Contract giúp biến những thỏa thuận này thành generated tests ở producer và stubs ở consumer. Sử dụng đúng phiên bản stub trong CI giúp phát hiện sớm thay đổi request/response không tương thích.
