# Chọn ví dụ đại diện cho từng nhánh tương tác

## 1. Vì sao cần chọn ví dụ theo nhánh tương tác?

Trong **Spring Cloud Contract** (module `SPRING_CLOUD_CONTRACT`), producer công bố hành vi mà consumer có thể dựa vào thông qua các hợp đồng HTTP hoặc thông điệp, được mô tả bằng Groovy DSL hay YAML DSL. Từ hợp đồng, công cụ có thể sinh kiểm thử cho producer và tạo stub để consumer chạy thử độc lập; Stub Runner giúp consumer sử dụng các stub đã phát hành trong quy trình phát triển và CI.

Tuy nhiên, một hợp đồng chỉ mô tả đường đi thành công thường không đủ. Consumer còn cần biết điều gì xảy ra khi dữ liệu không hợp lệ, tài nguyên không tồn tại, thao tác bị từ chối hoặc một thông điệp dẫn đến kết quả khác. **Chọn ví dụ đại diện cho từng nhánh tương tác** là chọn một tập trường hợp nhỏ nhưng bao phủ những kết quả *quan sát được* và có ý nghĩa đối với consumer.

Sau bài này, bạn có thể:

- Phân biệt nhánh tương tác của API với nhánh điều khiển nội bộ trong mã nguồn.
- Lập ma trận tình huống theo yêu cầu đầu vào, điều kiện, kết quả và người tiêu thụ kết quả.
- Chọn dữ liệu mẫu có tính đại diện, ổn định và có thể chạy lại để viết hợp đồng Groovy/YAML.
- Giải thích nhánh nào cần hợp đồng riêng, nhánh nào nên kiểm tra bằng unit/integration test.
- Liên kết các hợp đồng đã chọn với kiểm thử producer, stub cho consumer và CI.

## 2. Thế nào là một nhánh tương tác?

Một **nhánh tương tác** là một lớp tình huống mà tại ranh giới của dịch vụ, phía gọi nhận được một hành vi khác có ý nghĩa: mã trạng thái, cấu trúc body, header, loại lỗi, hoặc thông điệp được phát ra. Ví dụ, `201 Created` và `409 Conflict` là hai nhánh khác nhau vì consumer có thể quyết định tiếp tục quy trình hoặc thông báo thiếu hàng.

Ngược lại, hai nhánh `if` trong service cùng trả về `200 OK` với cùng hợp đồng dữ liệu có thể chỉ là chi tiết triển khai. Chúng không nhất thiết cần hai hợp đồng. Spring Cloud Contract kiểm chứng **hành vi ở ranh giới tích hợp**, không nhằm đạt độ phủ mọi dòng lệnh.

| Đặc điểm | Thường cần ví dụ hợp đồng riêng | Thường thuộc kiểm thử nội bộ |
| --- | --- | --- |
| Mã HTTP thay đổi | `201` khi tạo thành công, `400` khi dữ liệu sai | Hai thuật toán tạo cùng một kết quả `201` |
| Hình dạng hoặc ý nghĩa body thay đổi | Thành công có `id`; thất bại có `code` | Thay đổi cách xây dựng DTO nhưng JSON không đổi |
| Header mang ý nghĩa tích hợp | `Location`, `Content-Type`, phiên bản API nếu có cam kết | Header chỉ phục vụ giám sát nội bộ |
| Hành vi thông điệp thay đổi | Phát `RESERVED` hay `REJECTED` tới consumer khác | Thay cách ghi log, lưu cache |
| Quy tắc quyền truy cập thay đổi | `401` so với `403` nếu là hợp đồng công khai | Chi tiết kiểm tra token trong thư viện bảo mật |

> Nguyên tắc: phân nhóm theo **kết quả mà consumer phải xử lý**, sau đó chọn ít nhất một ví dụ tiêu biểu cho mỗi nhóm. Không cần biến mọi tổ hợp dữ liệu thành một hợp đồng.

## 3. Ví dụ xuyên suốt: dịch vụ đơn hàng

Giả sử một producer cung cấp API đặt hàng với các quy tắc minh họa sau (đây là **giả định thiết kế bài học**, không phải quy tắc mặc định của Spring Cloud Contract):

- `POST /api/orders` nhận JSON gồm `productId` và `quantity` (số nguyên dương).
- Sản phẩm `SKU-001` tồn tại và còn đủ hàng; `SKU-OUT` tồn tại nhưng không đủ hàng.
- Tạo thành công trả `201`, JSON chứa `id`, `status`, đồng thời trả header `Location`.
- `quantity <= 0` trả `400` với `code = INVALID_QUANTITY`; hết hàng trả `409` với `code = OUT_OF_STOCK`.
- `GET /api/orders/{id}` trả `200` khi tìm thấy và `404` với `ORDER_NOT_FOUND` khi không tìm thấy.
- Nếu dịch vụ có xác thực theo hợp đồng công khai, yêu cầu thiếu hoặc sai thông tin xác thực được xử lý riêng (`401`), yêu cầu có danh tính nhưng thiếu quyền có thể trả `403`.

### 3.1. Lập ma trận nhánh trước khi viết DSL

| Nhánh | Tình huống đầu vào/tiền điều kiện | Kết quả quan sát | Ý nghĩa đối với consumer |
| --- | --- | --- | --- |
| Tạo đơn thành công | `POST`, `SKU-001`, `quantity = 2`, đủ hàng | `201`, `id`, `status = CREATED`, `Location` | Chuyển sang màn hình chi tiết đơn |
| Sai số lượng | `POST`, `quantity = 0` | `400`, `code = INVALID_QUANTITY` | Hiển thị lỗi nhập liệu, không thử lại nguyên yêu cầu |
| Hết hàng | `POST`, `SKU-OUT`, `quantity = 2` | `409`, `code = OUT_OF_STOCK` | Báo xung đột nghiệp vụ, có thể đề nghị số lượng khác |
| Đọc đơn tồn tại | `GET /api/orders/ord-1001` với dữ liệu có sẵn | `200`, thông tin đơn | Hiển thị đơn |
| Đọc đơn không tồn tại | `GET /api/orders/ord-missing` | `404`, `code = ORDER_NOT_FOUND` | Hiển thị trạng thái không tìm thấy |
| Không xác thực | Không có thông tin xác thực, nếu API yêu cầu | `401`, dạng lỗi đã công bố | Yêu cầu đăng nhập/lấy token mới |
| Không đủ quyền | Xác thực hợp lệ nhưng không được phép, nếu áp dụng | `403`, dạng lỗi đã công bố | Không tiếp tục tác vụ bị cấm |

Ma trận này là điểm xuất phát để trao đổi với chủ sở hữu API và consumer. Không nên tự thêm nhánh `401`, `403` hoặc mã lỗi khác vào hợp đồng nếu đó chưa phải hành vi được thống nhất.

### 3.2. Chọn đúng lớp tương đương và giá trị biên

Đối với `quantity`, ba đầu vào `2`, `5`, `9` đều minh họa lớp **hợp lệ** khi còn hàng. Chọn `2` là đủ cho một hợp đồng đại diện. Giá trị `0` thể hiện ngay ranh giới chuyển từ hợp lệ (`1`) sang không hợp lệ (`0`) và vì vậy tốt hơn một giá trị lỗi tùy ý như `-999` cho nhánh kiểm tra số dương.

Nếu API còn giới hạn tối đa, ví dụ `quantity <= 100`, nên bổ sung cặp biên `100`/`101` trong bài kiểm thử phù hợp. Chỉ thêm hợp đồng riêng khi consumer có hành vi quan trọng cần dựa vào, chẳng hạn một mã lỗi riêng cho vượt hạn mức; các biến thể còn lại có thể được unit test hoặc kiểm thử tham số hóa.

## 4. Biến ví dụ đại diện thành hợp đồng HTTP

Trong các ví dụ dưới đây, mỗi hợp đồng là một file độc lập dưới thư mục hợp đồng mà dự án đã cấu hình. Tên file minh họa phản ánh nhánh, giúp truy vết khi producer test hoặc stub bị lỗi. Cú pháp Groovy DSL dùng `Contract.make` của Spring Cloud Contract.

### 4.1. Nhánh tạo đơn thành công: `create_order_success.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'create_order_success'
    description 'Tạo đơn thành công khi sản phẩm còn đủ hàng'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body([
            productId: 'SKU-001',
            quantity : 2
        ])
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
            header 'Location': '/api/orders/ord-1001'
        }
        body([
            id    : 'ord-1001',
            status: 'CREATED'
        ])
    }
}
```

**Vì sao ví dụ này đại diện?** Nó thể hiện đầy đủ hành vi consumer cần khi tạo thành công: phương thức, URL, định dạng request, mã `201`, định dạng response, `id`, `status` và `Location`. Không cần thêm hợp đồng chỉ thay `quantity` từ `2` thành `3` nếu hai trường hợp có cùng lời hứa API.

**Điều kiện ổn định:** Ví dụ dùng `ord-1001` cố định để dễ đọc; khi chạy producer test phải chuẩn bị dữ liệu và cơ chế tạo ID phù hợp (chẳng hạn fixture hoặc cấu hình kiểm thử có thể kiểm soát), đồng thời reset trạng thái giữa các lần chạy. Nếu ID sinh động trong ứng dụng thực tế, nên thay so khớp giá trị cố định bằng matcher hoặc giá trị producer/consumer thích hợp, và bảo đảm `Location` nhất quán với ID trả về.

### 4.2. Nhánh dữ liệu sai: `create_order_invalid_quantity.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'create_order_invalid_quantity'
    description 'Từ chối số lượng bằng 0'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body([
            productId: 'SKU-001',
            quantity : 0
        ])
    }

    response {
        status 400
        headers {
            contentType(applicationJson())
        }
        body([
            code   : 'INVALID_QUANTITY',
            message: 'quantity must be greater than 0'
        ])
    }
}
```

Lỗi đầu vào là một nhánh riêng vì consumer cần ánh xạ `INVALID_QUANTITY` sang thông báo tương ứng. Nếu message có thể được dịch hoặc thay đổi mà vẫn tương thích, nhóm nên cân nhắc chỉ cam kết mã lỗi và cấu trúc lỗi, rồi dùng matcher phù hợp cho phần văn bản thay vì buộc mọi ký tự phải giống nhau.

Cùng hợp đồng này có thể viết bằng **YAML DSL** thay cho Groovy DSL (chọn một biểu diễn cho một tình huống, tránh đăng ký trùng cả hai):

```yaml
name: create_order_invalid_quantity
description: Từ chối số lượng bằng 0
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    productId: SKU-001
    quantity: 0
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
    message: quantity must be greater than 0
```

### 4.3. Nhánh xung đột nghiệp vụ: `create_order_out_of_stock.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'create_order_out_of_stock'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body([
            productId: 'SKU-OUT',
            quantity : 2
        ])
    }

    response {
        status 409
        headers {
            contentType(applicationJson())
        }
        body([code: 'OUT_OF_STOCK'])
    }
}
```

Mặc dù cả `400` và `409` đều là kết quả thất bại, không nên gộp chúng. `400` chỉ ra dữ liệu đầu vào không hợp lệ; `409` biểu thị một xung đột với trạng thái nghiệp vụ hiện tại. Consumer có thể xử lý hai tình huống khác nhau.

### 4.4. Nhánh không tìm thấy: `get_order_not_found.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'get_order_not_found'

    request {
        method GET()
        url '/api/orders/ord-missing'
    }

    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body([code: 'ORDER_NOT_FOUND'])
    }
}
```

Ví dụ này cần đi cùng một hợp đồng `GET` trả `200` với bản ghi có sẵn, vì API đọc dữ liệu có ít nhất hai kết quả mà consumer phân biệt. Nhánh `404` không đồng nghĩa với `400`: request có thể hoàn toàn hợp lệ nhưng tài nguyên không tồn tại.

## 5. Làm sao tránh hợp đồng quá cứng hoặc quá rộng?

Ví dụ đại diện phải đủ cụ thể để sinh stub xác định, đồng thời tránh vô tình biến dữ liệu ngẫu nhiên thành cam kết dài hạn. Có thể áp dụng các nguyên tắc sau:

1. **Ổn định đầu vào.** Dùng dữ liệu fixture có tên rõ ý nghĩa (`SKU-001`, `SKU-OUT`, `ord-missing`); xác định trước bản ghi nào tồn tại, bản ghi nào không, tồn kho bao nhiêu và trạng thái bảo mật cần thiết.
2. **Khẳng định trường consumer thật sự dùng.** Nếu consumer phân nhánh theo `code`, phải kiểm tra `code`. Nếu chỉ cần biết `id` có hình thức hợp lệ, không nhất thiết buộc producer dùng một ID cố định.
3. **Tránh matcher quá rộng.** Regex `.*` cho toàn bộ body không chứng minh được producer giữ cấu trúc JSON. Matcher nên thu hẹp vào thuộc tính thật sự biến đổi, ví dụ `id`, ngày giờ hoặc mã giao dịch.
4. **Đảm bảo stub phân biệt các request.** Hai hợp đồng `POST /api/orders` không thể chỉ khác tên file và cùng được phép khớp mọi body; Stub Runner có thể chọn kết quả không như mong muốn. Điều kiện trên `productId`, `quantity`, header hoặc query parameter phải đủ để tách các nhánh.
5. **Không dùng trạng thái ngầm giữa hợp đồng.** Producer test có thể chạy theo thứ tự bất kỳ. Stub HTTP thông thường không tự thực hiện một chuỗi trạng thái nghiệp vụ. Nếu bài toán cần chuỗi `POST` rồi `GET`, hãy chuẩn bị fixture độc lập hoặc dùng kiểm thử tích hợp riêng cho luồng trạng thái đó.

Trong Groovy DSL, khi cần nhận nhiều ID đầu vào hợp lệ thay vì một giá trị duy nhất, có thể dùng matcher cho request:

```groovy
request {
    method GET()
    urlPath($(consumer(regex('/api/orders/ord-[0-9]+')),
               producer('/api/orders/ord-1001')))
}
```

Đoạn trên chỉ minh họa việc **stub phía consumer** có thể khớp nhiều URL, trong khi **producer test** vẫn dùng URL cụ thể. Chỉ áp dụng dạng này khi *mọi* ID được regex chấp nhận thực sự thuộc cùng một lớp hành vi. Với nhánh `404`, regex bao quát như trên rất dễ bắt nhầm URL dành cho hợp đồng `200`, do đó thường nên dùng đường dẫn ví dụ cụ thể hoặc các mẫu không giao nhau.

## 6. Chọn nhánh cho tương tác thông điệp

Trong hệ thống có message broker, consumer không chỉ quan sát HTTP response mà còn quan sát message đến/đi, destination và payload. Giả sử dịch vụ kho nhận thông điệp `orders.created` và công bố kết quả lên `inventory.reservations`:

| Nhánh | Message đầu vào | Message đầu ra được cam kết |
| --- | --- | --- |
| Giữ hàng thành công | `orderId = ord-1001`, `productId = SKU-001`, `quantity = 2` | `result = RESERVED` |
| Không đủ hàng | `orderId = ord-1002`, `productId = SKU-OUT`, `quantity = 2` | `result = REJECTED`, `reason = OUT_OF_STOCK` |

Nếu hai sự kiện này là hành vi công khai đã thống nhất, nên chọn hai hợp đồng thông điệp khác nhau. Ví dụ cho nhánh thành công:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'inventory_reserved_after_order_created'

    input {
        messageFrom('orders.created')
        messageBody([
            orderId  : 'ord-1001',
            productId: 'SKU-001',
            quantity : 2
        ])
    }

    outputMessage {
        sentTo('inventory.reservations')
        body([
            orderId: 'ord-1001',
            result : 'RESERVED'
        ])
    }
}
```

Ở nhánh `REJECTED`, input dùng fixture hết hàng và output mang `result = REJECTED`, `reason = OUT_OF_STOCK`. Trường hợp hợp đồng chỉ định **không phát thông điệp nào** cần được kiểm thử kỹ bằng integration test hoặc cơ chế quan sát thích hợp; không nên diễn giải sự vắng mặt của `outputMessage` thành bằng chứng đã kiểm tra được việc *không* phát sự kiện.

Destination, định dạng payload, header tương quan (`correlationId` nếu có) và ngữ nghĩa retry/duplicate cần được thỏa thuận với consumer khi chúng ảnh hưởng đến khả năng tương thích. Không mặc định mọi hệ thống đều có cùng tên topic hay cơ chế gửi nhận như ví dụ.

## 7. Từ ma trận nhánh đến producer test, stub và CI

Một quy trình thực hành phù hợp với mục tiêu học Spring Cloud Contract:

1. **Chốt ma trận với consumer.** Mỗi dòng có tiền điều kiện, request/message đại diện, kết quả mong đợi và cách consumer dùng kết quả. Đánh dấu nhánh bắt buộc và nhánh chỉ là giả định cần xác nhận.
2. **Tạo một hợp đồng cho mỗi hành vi phân biệt được.** Đặt tên diễn tả nhánh (`create_order_success`, `create_order_invalid_quantity`); chọn Groovy DSL hoặc YAML DSL theo quy ước dự án.
3. **Thiết lập fixture và sinh kiểm thử producer.** Chạy bước build có tích hợp Spring Cloud Contract để tạo/chạy các kiểm thử tương ứng. Khi producer thay `409` thành `200` hoặc bỏ `code`, bài kiểm thử của nhánh liên quan phải báo lỗi.
4. **Sinh và phát hành stub từ cùng hợp đồng đã kiểm chứng.** Consumer dùng Stub Runner để chạy kiểm thử với các tình huống success/error mà không cần khởi động producer thật. Stub phải đủ khác biệt về điều kiện request để consumer chủ động kích hoạt từng nhánh.
5. **Kiểm tra trong CI.** Pipeline producer xác minh hợp đồng trước khi công bố artifact stub; pipeline consumer kiểm tra với phiên bản stub đã chọn. Khi hợp đồng thay đổi, cả hai phía phải xác nhận hành vi mới trước khi nâng phiên bản phụ thuộc.

Ví dụ một phép thử consumer có giá trị là: khi stub trả `409` kèm `OUT_OF_STOCK`, ứng dụng không chuyển sang trang đơn hàng đã tạo và thay vào đó hiển thị thông báo hết hàng. Kiểm thử này xác minh **quyết định của consumer** dựa trên kết quả đã được hợp đồng mô tả, chứ không chỉ kiểm tra stub có trả JSON hay không.

## 8. Những lỗi thường gặp khi chọn ví dụ

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ ghi nhánh `200`/`201` | Consumer không có stub cho các lỗi quan trọng | Bổ sung nhánh khác nhau về mã trạng thái, error code hoặc sự kiện |
| Một hợp đồng cho mọi giá trị đầu vào | Stub dễ trả sai nhánh; kiểm thử không chứng minh được quy tắc | Dùng dữ liệu và điều kiện matcher phân biệt rõ từng tình huống |
| Một hợp đồng cho mọi giá trị số trong cùng lớp | Bộ hợp đồng phình to, khó bảo trì | Chọn đại diện và điểm biên; chuyển phần còn lại sang unit/parameterized test |
| Phụ thuộc cơ sở dữ liệu còn sót từ lần chạy trước | Producer test không ổn định trong CI | Chuẩn bị và dọn fixture độc lập cho từng kiểm thử |
| So khớp chính xác ID hoặc timestamp ngẫu nhiên | Producer test hỏng dù hành vi tương thích | Dùng matcher có giới hạn hoặc dữ liệu sinh được kiểm soát |
| Quên `Content-Type`, `Location` hoặc `code` mà consumer dùng | Hợp đồng không bảo vệ hành vi tích hợp quan trọng | Liệt kê các trường/header consumer cần và đưa chúng vào kiểm tra |
| Gộp lỗi `400` và `409` vì đều là lỗi | Consumer mất khả năng phân biệt cách xử lý | Giữ riêng các nhánh có ý nghĩa nghiệp vụ khác nhau |

## 9. Bài thực hành tự kiểm tra

Giả sử API `POST /api/orders` được bổ sung quy tắc: `quantity` tối đa `10`, và khi `quantity > 10` trả `422` với `code = QUANTITY_LIMIT_EXCEEDED`.

1. Thêm một dòng vào ma trận gồm input `quantity = 11`, trạng thái `422`, mã lỗi và hành vi consumer dự kiến. Vì có **mã lỗi và cách xử lý mới**, đây là nhánh cần hợp đồng riêng.
2. Chọn `quantity = 10` làm giá trị biên hợp lệ để kiểm chứng bằng một test phù hợp; không nhất thiết phải tạo hợp đồng mới nếu kết quả vẫn giống nhánh tạo đơn thành công.
3. Viết hợp đồng `create_order_quantity_limit_exceeded` (Groovy hoặc YAML) kiểm tra `422` và `QUANTITY_LIMIT_EXCEEDED`; bảo đảm fixture sản phẩm còn đủ hàng để điều kiện giới hạn số lượng là nguyên nhân trực tiếp của lỗi.
4. Giả lập consumer nhận kết quả `422` từ Stub Runner, xác nhận ứng dụng gợi ý giảm số lượng thay vì thử lại yêu cầu không đổi.

**Checklist trước khi chốt một bộ hợp đồng:** mỗi nhánh có kết quả quan sát khác biệt; request đủ cụ thể để chọn đúng stub; dữ liệu fixture có thể tái tạo; các trường và header quan trọng được xác nhận; trường động không bị ràng buộc tùy tiện; mỗi tình huống có mục đích kiểm thử rõ ràng; các nhánh mới được đưa vào CI.

Khi các ví dụ được chọn theo cách này, bộ hợp đồng vừa đóng vai trò tài liệu hành vi dùng chung giữa producer và consumer, vừa trở thành lớp cảnh báo sớm cho các thay đổi API không tương thích.
