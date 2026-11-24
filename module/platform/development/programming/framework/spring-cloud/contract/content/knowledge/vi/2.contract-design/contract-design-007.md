# Thiết kế hợp đồng cho thành công, lỗi và dữ liệu rỗng

## Mục tiêu học tập

Trong **Spring Cloud Contract**, hợp đồng là mô tả có thể kiểm thử về tương tác giữa **producer** (dịch vụ cung cấp API hoặc phát thông điệp) và **consumer** (bên sử dụng API hoặc nhận thông điệp). Sau bài học thuộc chương **Thiết kế hợp đồng**, bạn có thể:

- Phân loại phản hồi **thành công có dữ liệu**, **thành công nhưng không có kết quả**, và **lỗi** theo ngữ nghĩa nghiệp vụ.
- Chọn HTTP status, header và cấu trúc body phù hợp để consumer xử lý được từng nhánh.
- Viết ví dụ **Groovy DSL** và **YAML DSL** cho các tình huống quan trọng trong Spring Cloud Contract.
- Hiểu cách contract test được sinh phía producer, cách stub phục vụ consumer qua **Stub Runner**, và cách dùng CI để phát hiện thay đổi API không tương thích.
- Tránh các hợp đồng quá lỏng, quá cứng hoặc bỏ sót trường hợp đặc biệt.

## 1. Vì sao cần thiết kế đủ ba nhóm phản hồi?

Giả sử hệ thống có:

- **Catalog Service**: producer cung cấp API tìm và lấy sản phẩm.
- **Shopfront Service**: consumer hiển thị danh sách và chi tiết sản phẩm.

Chỉ định nghĩa trường hợp “có sản phẩm, trả về `200 OK`” là chưa đủ. Consumer còn phải biết điều gì xảy ra khi bộ lọc không trả kết quả, người dùng truy vấn một mã sản phẩm không tồn tại, hoặc tham số không hợp lệ.

Ví dụ API công bố:

| Tình huống | Yêu cầu HTTP | Kết quả được thỏa thuận | Consumer cần làm gì |
|---|---|---|---|
| Có sản phẩm trong danh mục | `GET /api/products?category=books` | `200 OK` và mảng chứa sản phẩm | Hiển thị danh sách |
| Không có sản phẩm phù hợp | `GET /api/products?category=no-match` | `200 OK` và mảng rỗng `[]` | Hiển thị trạng thái “chưa có kết quả” |
| Tham số danh mục sai định dạng | `GET /api/products?category=INVALID!` | `400 Bad Request` và mã lỗi `INVALID_CATEGORY` | Hiển thị hoặc xử lý lỗi đầu vào |
| Truy vấn ID không tồn tại | `GET /api/products/P-404` | `404 Not Found` và mã lỗi `PRODUCT_NOT_FOUND` | Hiển thị “không tìm thấy sản phẩm” |

Ở ví dụ này, `category` chỉ chấp nhận chữ thường và dấu gạch nối; `no-match` hợp lệ về cú pháp nhưng hiện không có sản phẩm. Các đường dẫn và mã lỗi là **quy ước minh họa** do hai nhóm thống nhất, không phải quy tắc bắt buộc cho mọi API.

Điểm mấu chốt: **“không tìm thấy kết quả trong một tập hợp” không đồng nghĩa với “đường dẫn tài nguyên không tồn tại”, và cả hai đều khác “request không hợp lệ”.**

## 2. Xác định ranh giới hợp đồng trước khi viết DSL

Hợp đồng nên mô tả **những gì consumer quan sát được** ở ranh giới giao tiếp, thay vì cấu trúc nội bộ của producer.

| Cần thiết kế/kiểm chứng | Ví dụ | Không nên khóa cứng nếu consumer không phụ thuộc |
|---|---|---|
| Phương thức, URL, query parameter | `GET`, `/api/products`, `category` | Tên controller hay tên method Java |
| HTTP status theo từng tình huống | `200`, `400`, `404` | Cách service truy vấn cơ sở dữ liệu |
| Header liên quan đến hợp đồng | `Content-Type: application/json` | Header hạ tầng không có ý nghĩa với consumer |
| Hình dạng và kiểu dữ liệu JSON | `id` là chuỗi, `price` là số | Thứ tự các thuộc tính JSON |
| Mã lỗi ổn định và ngữ nghĩa xử lý | `INVALID_CATEGORY` | Nội dung stack trace, tên exception |
| Biểu diễn trường hợp rỗng | `[]`, `null`, field bị lược bỏ hoặc `204` | Dữ liệu demo cụ thể nếu giá trị biến động |

Trước khi viết hợp đồng, hãy làm rõ bốn câu hỏi:

1. **Consumer phân biệt những nhánh nào?** Chẳng hạn: có kết quả / không có kết quả / lỗi đầu vào / ID không tồn tại.
2. **Mỗi nhánh có ý nghĩa gì?** Không có kết quả tìm kiếm là trạng thái nghiệp vụ bình thường hay là lỗi?
3. **Consumer dựa vào trường nào?** Ví dụ `id`, `name`, `price`, `code`, kiểu dữ liệu và tính bắt buộc của chúng.
4. **Thay đổi nào là phá vỡ kỳ vọng?** Ví dụ đổi `[]` thành `null`, hoặc đổi status `404` thành `200` kèm error body.

Một hợp đồng HTTP thường cần mô tả ít nhất: **request** (method, path, query, header/body nếu có) và **response** (status, header, body). Các quy tắc khớp (matcher) giúp kiểm chứng kiểu hoặc định dạng mà không nhất thiết khóa mọi giá trị ví dụ.

## 3. Thiết kế phản hồi thành công có dữ liệu

Với danh mục `books`, producer trả về:

~~~http
GET /api/products?category=books HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[
  {
    "id": "B-101",
    "name": "Java Fundamentals",
    "price": 150000
  }
]
~~~

Các quyết định phải thống nhất gồm: đây là **mảng JSON**, mỗi phần tử có `id` (string), `name` (string), `price` (number), và giá phải có ý nghĩa xác định (ví dụ số tiền theo đơn vị tiền tệ mà API quy định). Nếu thiếu hợp đồng ngữ nghĩa giá, hai bên vẫn có thể giải mã JSON đúng nhưng tính tiền sai.

### Groovy DSL: thành công có dữ liệu

Ví dụ một file riêng, `src/test/resources/contracts/products/listBooks.groovy`, trong dự án đã cấu hình Spring Cloud Contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Danh sach san pham thuoc danh muc books'

    request {
        method 'GET'
        urlPath('/api/products') {
            queryParameters {
                parameter 'category': 'books'
            }
        }
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body([
            [
                id: 'B-101',
                name: 'Java Fundamentals',
                price: 150000
            ]
        ])
        bodyMatchers {
            jsonPath('$[0].id', byRegex('B-[0-9]+'))
            jsonPath('$[0].price', byType())
        }
    }
}
~~~

**Cách đọc:**

- `urlPath` cùng `queryParameters` quy định đường dẫn và giá trị tham số mà tình huống này áp dụng.
- `status 200` và `contentType(applicationJson())` thể hiện phản hồi thành công dưới dạng JSON.
- `body` cung cấp một ví dụ hợp lệ: mảng gồm một sản phẩm.
- `bodyMatchers` nêu rõ quy tắc khi kiểm chứng phản hồi producer: ID theo dạng `B-` cộng chữ số và giá là kiểu dữ liệu tương ứng ví dụ. Tùy DSL, có thể bổ sung matcher cho các trường biến động khác.

Nếu ứng dụng thực có thể trả nhiều sản phẩm, cần quyết định consumer có phụ thuộc **số lượng hoặc thứ tự phần tử** hay không. Không nên biến “luôn có đúng một phần tử và ID cố định” thành yêu cầu ngoài ý muốn. Ví dụ cố định giúp stub có dữ liệu rõ ràng, nhưng muốn bao phủ sắp xếp, phân trang hay nhiều phần tử thì phải thiết kế thêm tình huống và matcher thích hợp.

## 4. Thiết kế phản hồi thành công nhưng dữ liệu rỗng

Consumer tìm sản phẩm với danh mục **hợp lệ** nhưng hiện chưa có sản phẩm:

~~~http
GET /api/products?category=no-match HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

Trong hợp đồng minh họa, `200 OK` + `[]` có nghĩa: **truy vấn hợp lệ, được xử lý thành công, nhưng không có bản ghi phù hợp**. Đây vẫn là danh sách, có kiểu dữ liệu nhất quán với trường hợp có kết quả.

### Groovy DSL: danh sách rỗng

Lưu ở file riêng `src/test/resources/contracts/products/listNoMatch.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Danh muc hop le nhung khong co san pham'

    request {
        method 'GET'
        urlPath('/api/products') {
            queryParameters {
                parameter 'category': 'no-match'
            }
        }
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body([])
    }
}
~~~

Dòng `body([])` rất quan trọng: nó biểu diễn **mảng JSON rỗng**, khác với body vắng mặt, chuỗi rỗng `""`, object rỗng `{}` hay giá trị JSON `null`. Với dữ liệu tiêu thụ theo dạng danh sách, giữ nhất quán kiểu mảng thường giúp consumer ít nhánh xử lý hơn.

### Các cách biểu diễn “rỗng” không tương đương

| Phản hồi | Ý nghĩa có thể dùng | Điều consumer phải lưu ý |
|---|---|---|
| `200` + `[]` | Truy vấn danh sách thành công, 0 phần tử | Vẫn giải mã JSON array |
| `200` + `{}` | Object hợp lệ nhưng không có thuộc tính, nếu API quy định | Không thể thay tùy tiện cho array |
| `200` + `null` | Giá trị được biểu diễn bằng JSON null, nếu hợp đồng cho phép | Consumer cần chấp nhận null, khác với danh sách rỗng |
| `200` + field bị thiếu | Field có thể tùy chọn | Consumer cần biết field thiếu khác field = null hay không |
| `204 No Content` | Yêu cầu thành công, không có response body | Consumer **không nên** cố đọc `[]` hoặc JSON từ body |
| `404 Not Found` | Tài nguyên được định danh không tồn tại | Thường có nhánh xử lý riêng cho lỗi “không tìm thấy” |

Việc chọn `200 []` hay `204` phải xuất phát từ **ngữ nghĩa API và thỏa thuận với consumer**. Đã công bố `200 []` thì đổi sang `204` chỉ vì “cũng là không có dữ liệu” có thể phá vỡ consumer đang chờ JSON array. Với `204`, không mô tả response body trong hợp đồng.

Nếu API phân trang trả về một object dạng `{ "items": [], "total": 0 }` thì tình huống rỗng phải giữ đúng **shape phân trang đã công bố**, không tự đổi thành `[]`.

## 5. Thiết kế lỗi do request không hợp lệ

Trong ví dụ, `category` chỉ được chứa chữ thường và dấu gạch nối. Vì vậy, `INVALID!` sai định dạng; đây là **lỗi đầu vào**, không phải danh mục hợp lệ nhưng rỗng.

~~~http
GET /api/products?category=INVALID! HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "INVALID_CATEGORY",
  "message": "category must contain lowercase letters or hyphens"
}
~~~

Consumer nên có thể xử lý bằng **mã lỗi máy đọc được** như `INVALID_CATEGORY`. Trường `message` dùng để giải thích hoặc hiển thị khi thích hợp; không nên lấy câu chữ tiếng Anh làm điều kiện phân nhánh vì nội dung này có thể được điều chỉnh hoặc dịch ngôn ngữ.

### Groovy DSL: lỗi 400

Lưu ở `src/test/resources/contracts/products/invalidCategory.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tu choi tham so category sai dinh dang'

    request {
        method 'GET'
        urlPath('/api/products') {
            queryParameters {
                parameter 'category': 'INVALID!'
            }
        }
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 400
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVALID_CATEGORY',
            message: 'category must contain lowercase letters or hyphens'
        )
    }
}
~~~

Hợp đồng trên bảo vệ **một trường hợp không hợp lệ cụ thể**. Nó chưa chứng minh mọi input không hợp lệ đều bị từ chối. Nếu producer phải kiểm tra query parameter thiếu, để trống, quá dài hoặc chứa ký tự đặc biệt khác, cần thêm tình huống hoặc matcher phù hợp theo tiêu chí nghiệp vụ.

### Thiết kế error body ổn định

Nên thống nhất một mẫu lỗi nhất quán giữa các endpoint, chẳng hạn:

~~~json
{
  "code": "INVALID_CATEGORY",
  "message": "category must contain lowercase letters or hyphens"
}
~~~

Có thể bổ sung `requestId` để hỗ trợ truy vết, `details` cho lỗi trường cụ thể hoặc `retryable` nếu đó là cam kết chính thức. Khi đó cần quy định field nào bắt buộc, kiểu dữ liệu và trường hợp xuất hiện. Tránh ràng buộc hợp đồng vào timestamp, ID ngẫu nhiên hoặc thông báo lỗi động bằng cách so khớp nguyên văn nếu consumer không dựa vào chúng; sử dụng matcher nếu cần kiểm chứng định dạng.

Không nên trả stack trace hay chi tiết triển khai nội bộ trong error body. Với lỗi yêu cầu xác thực hoặc phân quyền, cần phân biệt `401 Unauthorized` và `403 Forbidden` theo đúng giao thức; với lỗi phụ thuộc dịch vụ, có thể thiết kế trường hợp `503 Service Unavailable` nếu consumer có logic dự phòng hoặc retry. Chỉ thêm các trường hợp mà consumer thực sự cần và có thể kiểm chứng.

## 6. Thiết kế lỗi khi tài nguyên không tồn tại

Giờ xét yêu cầu lấy **một sản phẩm theo ID**:

~~~http
GET /api/products/P-404 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "PRODUCT_NOT_FOUND",
  "message": "Product does not exist"
}
~~~

Đây là trường hợp khác với truy vấn danh sách trả mảng rỗng. Consumer đang yêu cầu **một tài nguyên cụ thể** không có trong hệ thống; nếu API quy định `404`, consumer có thể chuyển sang màn hình “sản phẩm không tồn tại”.

### YAML DSL: lỗi 404

Spring Cloud Contract cũng hỗ trợ định nghĩa hợp đồng bằng **YAML DSL**. Ví dụ file `src/test/resources/contracts/products/productNotFound.yml`:

~~~yaml
description: San pham theo ID khong ton tai
request:
  method: GET
  url: /api/products/P-404
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: PRODUCT_NOT_FOUND
    message: Product does not exist
~~~

YAML diễn đạt cùng các thành phần cốt lõi như Groovy DSL: request, response, status, header, body. Chọn định dạng theo quy ước dự án; không cần duy trì hai bản trùng lặp cho một tình huống chỉ để “đủ hai DSL”.

Đừng sử dụng cùng một `404` để che giấu lỗi dữ liệu trống, lỗi validation và lỗi hạ tầng nếu consumer cần xử lý chúng theo cách khác nhau. Mã lỗi và ngữ nghĩa phải rõ ràng.

## 7. Bảng quyết định khi thiết kế hợp đồng

Khi phân vân giữa các trạng thái, có thể áp dụng quy trình sau:

~~~mermaid
flowchart TD
    A["Nhận request"] --> B{"Request hợp lệ?"}
    B -- "Không" --> C["400 + mã lỗi validation"]
    B -- "Có" --> D{"Truy vấn một ID cụ thể?"}
    D -- "Có" --> E{"Tài nguyên tồn tại?"}
    E -- "Không" --> F["404 + mã lỗi không tìm thấy"]
    E -- "Có" --> G["200 + object"]
    D -- "Không, truy vấn danh sách" --> H{"Có kết quả?"}
    H -- "Có" --> I["200 + mảng có phần tử"]
    H -- "Không" --> J["200 + mảng rỗng []"]
~~~

**Lưu ý:** Đây là **quyết định thiết kế của API minh họa**, không phải sơ đồ chuẩn bắt buộc cho mọi hệ thống. Một số API dùng `204` cho thao tác thành công không có nội dung, dùng `201` khi tạo tài nguyên hoặc `202` khi chấp nhận xử lý bất đồng bộ. Điều quan trọng là mỗi nhánh được định nghĩa rõ và nhất quán trong hợp đồng.

Trước khi chốt, hãy trả lời:

- Với trường hợp thành công, shape JSON có ổn định dù số lượng bản ghi thay đổi không?
- Khi không có kết quả, consumer nhận `[]`, `204` hay một object phân trang? Có chính xác một quy ước không?
- Với lỗi, status và `code` có đủ giúp consumer chọn cách xử lý không?
- Mã lỗi, kiểu dữ liệu, tên field và đường dẫn có nằm trong các bài test hợp đồng đã thống nhất không?
- Các tình huống có **phân biệt rõ request** để stub chọn đúng phản hồi không?

## 8. Spring Cloud Contract giúp kiểm chứng ba nhánh thế nào?

Ba loại tình huống được định nghĩa bằng các file contract khác nhau. Khi đã cấu hình plugin và test infrastructure phù hợp:

1. **Producer chạy generated contract tests.** Spring Cloud Contract sinh test từ hợp đồng, gửi request tới ứng dụng hoặc tầng HTTP producer được dựng cho test rồi kiểm tra status, header, body theo kỳ vọng.
2. **Producer xuất bản stub.** Build có thể đóng gói stub tương ứng với các hợp đồng đã xác minh vào một artifact; quy trình thường tích hợp với Maven hoặc Gradle.
3. **Consumer chạy test với Stub Runner.** Consumer dùng Stub Runner tải hoặc chạy stub đúng phiên bản, gửi request của chính mình và kiểm tra nhánh xử lý thành công, rỗng và lỗi.
4. **CI phát hiện thay đổi không tương thích.** Pipeline producer báo lỗi nếu triển khai lệch hợp đồng; pipeline consumer báo lỗi nếu code consumer xử lý sai phản hồi của stub mà nó đang dùng.

Ví dụ các kỳ vọng consumer nên kiểm tra:

| Test phía consumer | Request gửi tới stub | Kỳ vọng với code consumer |
|---|---|---|
| `shouldDisplayBooks` | `category=books` | Hiển thị sản phẩm từ mảng kết quả |
| `shouldShowEmptyState` | `category=no-match` | Nhận `[]` và hiển thị “không có kết quả”, không báo lỗi hệ thống |
| `shouldHandleInvalidCategory` | `category=INVALID!` | Nhận `400` và xử lý `INVALID_CATEGORY` |
| `shouldHandleUnknownProduct` | `/api/products/P-404` | Nhận `404` và xử lý `PRODUCT_NOT_FOUND` |

Nếu muốn kiểm thử qua một stub HTTP do Stub Runner khởi chạy trên cổng cấu hình, consumer phải gọi **địa chỉ của stub** (không gọi producer thật). Các tọa độ artifact, cổng, chế độ lấy stub và version phụ thuộc dự án.

**Cảnh báo về tính đại diện của stub:** consumer test chạy thành công với stub không chứng minh producer thật đúng hợp đồng; cần kết quả generated contract tests của producer. Ngược lại, producer test xanh cũng không tự kiểm tra toàn bộ logic phía consumer.

**Cảnh báo về phiên bản:** nếu consumer tiếp tục dùng stub cũ, pipeline vẫn có thể xanh sau khi producer thay đổi interface. CI cần chính sách đồng bộ/kiểm tra phiên bản hợp đồng và stub, cùng quy trình phê duyệt khi có thay đổi phá vỡ tương thích.

## 9. Các lỗi thiết kế thường gặp

| Lỗi thiết kế | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ có contract thành công | Consumer chưa được bảo vệ ở nhánh lỗi/rỗng | Thiết kế test matrix từ hành vi consumer |
| Trả `404` cho truy vấn danh sách hợp lệ nhưng không có kết quả, trong khi tài liệu hứa `200 []` | Consumer báo lỗi thay vì trạng thái rỗng | Giữ nguyên ngữ nghĩa và status đã công bố |
| Trả `200` với `null` sau khi công bố mảng JSON | Consumer có thể lỗi khi duyệt danh sách | Giữ shape nhất quán `[]` |
| Trả `200` kèm một field `error` thay cho HTTP status lỗi đã thỏa thuận | Consumer có thể coi lỗi là thành công | Dùng status và error body thống nhất |
| Dùng thông báo lỗi tự nhiên để quyết định nhánh | Thay đổi ngôn ngữ/câu chữ làm hỏng consumer | Kiểm tra mã lỗi ổn định |
| Khóa cứng timestamp, UUID, dữ liệu ngẫu nhiên | Producer test lỗi khi dữ liệu hợp lệ biến đổi | Dùng matcher cho định dạng/kiểu phù hợp |
| Matcher quá rộng, không kiểm tra field quan trọng | Không phát hiện thay đổi sai kiểu hoặc thiếu field | Ràng buộc rõ các field consumer phụ thuộc |
| Stub không khớp với phiên bản producer sắp phát hành | Test xanh nhưng tích hợp thật lỗi | Quản lý version, tích hợp kiểm chứng vào CI |

## 10. Bài thực hành tự đánh giá

Yêu cầu mới: Shopfront hiển thị sản phẩm theo danh mục `electronics`. Nhóm producer muốn thêm phân trang và đổi phản hồi của danh mục không có kết quả từ `[]` sang:

~~~json
{
  "items": [],
  "total": 0
}
~~~

Hãy trả lời:

1. **Đây là thay đổi có khả năng phá vỡ consumer không?** Có. Shape thay đổi từ array sang object; consumer đang parse danh sách trực tiếp có thể hỏng dù status vẫn là `200`.
2. **Cần hợp đồng mới cho tình huống nào?** Ít nhất cho danh sách có dữ liệu và danh sách rỗng theo shape phân trang. Nếu consumer cần phân trang, bổ sung hành vi với query `page`, `size` và các ràng buộc liên quan.
3. **Producer và consumer nên triển khai theo trình tự nào?** Thống nhất contract mới, cân nhắc duy trì cách trả cũ hoặc version API, cho consumer chuyển đổi và chạy test với stub mới trước khi bỏ giao diện cũ.
4. **Nếu `page=-1` thì sao?** Nếu API định nghĩa `page` phải không âm, tạo hợp đồng validation, chẳng hạn `400` với mã lỗi `INVALID_PAGE`. Đừng nhầm request sai với trang kết quả rỗng.

### Câu hỏi tự kiểm tra

- Khi nào `200 []` thích hợp hơn `404`?
- Vì sao `204` khác `200 []` từ góc nhìn consumer?
- Những phần nào của error response cần ổn định để code consumer xử lý được?
- Một hợp đồng thành công có dữ liệu có thể bỏ lọt lỗi nào ở nhánh rỗng?
- Vì sao cần cả generated contract test phía producer lẫn test consumer với stub?

## Ghi nhớ

**Thiết kế hợp đồng theo hành vi mà consumer thật sự cần:** thành công có dữ liệu, thành công với dữ liệu rỗng và lỗi là những kết quả khác nhau, phải có **ngữ nghĩa, HTTP status và body nhất quán**. Spring Cloud Contract cho phép biểu diễn chúng bằng Groovy/YAML DSL, sinh kiểm thử producer và stub để chạy consumer test qua Stub Runner. Khi đưa các kiểm tra cùng quản lý phiên bản stub vào CI, nhóm phát hiện sớm những thay đổi phá vỡ kỳ vọng thay vì chỉ biết sau khi tích hợp thực tế.
