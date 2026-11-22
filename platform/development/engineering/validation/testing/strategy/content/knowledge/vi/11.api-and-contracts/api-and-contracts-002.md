# Chọn phạm vi kiểm tra schema, ngữ nghĩa và lỗi của API

Trong module `VALIDATION_TESTING_STRATEGY`, kiểm thử API cần xác nhận hợp đồng mà một dịch vụ cung cấp cho các bên tiêu thụ. Hợp đồng API không chỉ quy định tên endpoint hoặc cấu trúc JSON. Nó còn bao gồm kiểu dữ liệu, trường bắt buộc, ý nghĩa của dữ liệu, điều kiện nghiệp vụ, quyền truy cập, trạng thái phản hồi và cách hệ thống xử lý khi có lỗi.

Khi xác định phạm vi kiểm tra, cần phân biệt ba lớp chính:

- **Schema:** hình dạng và ràng buộc cấu trúc của request, response, header và các đối tượng dữ liệu.
- **Ngữ nghĩa (semantics):** ý nghĩa và quy tắc xử lý của dữ liệu, trạng thái, hành động và kết quả nghiệp vụ.
- **Lỗi API:** cách API phản hồi khi đầu vào, quyền hạn, trạng thái hệ thống hoặc phụ thuộc không đáp ứng điều kiện.

Ba lớp có liên hệ nhưng cung cấp các bằng chứng khác nhau. Một response có thể hợp lệ theo JSON Schema nhưng vẫn chứa tổng tiền sai. Một request có thể đúng cấu trúc nhưng vi phạm quyền nghiệp vụ. Một API có thể xử lý đúng luồng thành công nhưng trả lỗi không nhất quán hoặc để lại tác dụng phụ khi timeout.

Bài học này hướng dẫn cách chọn phạm vi kiểm tra schema, ngữ nghĩa và lỗi dựa trên hợp đồng, thay đổi và rủi ro. Mục tiêu là tạo danh mục kiểm thử có thể truy vết, đủ sâu ở các điểm quan trọng và phù hợp với vai trò của API trong hệ thống.

## 1. Hiểu hợp đồng API trước khi chọn phạm vi

### 1.1. Hợp đồng API bao gồm những gì?

Hợp đồng API (API contract) mô tả cách bên tiêu thụ tương tác với bên cung cấp và những điều hai bên có thể kỳ vọng. Tùy giao thức và kiểu API, hợp đồng có thể bao gồm:

- Đường dẫn, phương thức và phiên bản endpoint.
- Query parameter, path parameter, header và nội dung request.
- Schema của request và response.
- Mã trạng thái, header và cấu trúc response.
- Quy tắc xác thực, phân quyền và giới hạn sử dụng.
- Ý nghĩa nghiệp vụ của trường dữ liệu và thao tác.
- Quy tắc idempotency, thứ tự xử lý và trạng thái bất đồng bộ.
- Cách biểu diễn lỗi, điều kiện retry và khả năng phục hồi.
- Các giới hạn tương thích và chính sách thay đổi phiên bản.

Hợp đồng có thể được mô tả bằng OpenAPI, AsyncAPI, JSON Schema, tài liệu giao thức, ví dụ request/response hoặc thỏa thuận giữa các nhóm. Tài liệu chỉ là một phần bằng chứng; cần đối chiếu với hành vi triển khai và kỳ vọng của consumer.

### 1.2. Ba lớp kiểm tra

| Lớp | Câu hỏi chính | Ví dụ phát hiện |
|---|---|---|
| Schema | Dữ liệu có đúng hình dạng và ràng buộc cấu trúc không? | Trường bắt buộc bị thiếu, sai kiểu, enum không hợp lệ |
| Ngữ nghĩa | Dữ liệu và hành vi có đúng ý nghĩa nghiệp vụ không? | Tổng tiền sai, trạng thái chuyển không hợp lệ, quyền truy cập vượt phạm vi |
| Lỗi API | Khi điều kiện không đạt, API có phản hồi và giữ trạng thái đúng không? | Trả sai mã lỗi, lộ stack trace, tạo dữ liệu một phần sau khi thất bại |

Một trường hợp kiểm thử có thể bao phủ nhiều lớp. Ví dụ, gửi một request có kiểu dữ liệu hợp lệ nhưng số lượng âm có thể kiểm tra schema nếu schema quy định minimum, đồng thời kiểm tra ngữ nghĩa nếu quy tắc nghiệp vụ cấm số lượng âm. Khi ghi phạm vi, nêu rõ mục tiêu chính để tránh hiểu nhầm về độ bao phủ.

### 1.3. Phân biệt kiểm tra API với kiểm thử giao diện

Kiểm thử API tập trung vào hợp đồng và hành vi của endpoint hoặc thông điệp. Nó có thể chạy trực tiếp qua HTTP, RPC, message broker hoặc công cụ phù hợp với giao thức. Kiểm thử giao diện xác nhận cách người dùng tương tác với sản phẩm.

API có thể đúng hợp đồng nhưng giao diện gửi sai dữ liệu. Ngược lại, giao diện có thể hiển thị đúng một thông báo trong khi API lưu dữ liệu không chính xác. Vì vậy, cần phối hợp kiểm thử ở các tầng:

- Schema và contract test để xác nhận hình dạng giao tiếp.
- Kiểm thử thành phần và tích hợp để xác nhận logic cùng tương tác dịch vụ.
- Kiểm thử API theo ngữ nghĩa để xác nhận quy tắc nghiệp vụ.
- E2E để xác nhận hành trình người dùng khi kết quả phụ thuộc nhiều thành phần.

Không cần đẩy mọi trường hợp lên E2E nếu API có thể được kiểm tra trực tiếp với dữ liệu và bằng chứng đáng tin cậy.

## 2. Chọn phạm vi kiểm tra schema

Schema xác định cấu trúc dữ liệu mà API chấp nhận hoặc trả về. Kiểm tra schema giúp phát hiện sai lệch giữa tài liệu, consumer và provider trước khi chúng gây lỗi ở các tầng cao hơn.

### 2.1. Những thành phần schema cần xem xét

Với request và response, kiểm tra các thuộc tính phù hợp:

| Thành phần | Câu hỏi kiểm tra | Ví dụ |
|---|---|---|
| Kiểu dữ liệu | Giá trị có đúng kiểu được công bố không? | `amount` là number, `createdAt` là string theo định dạng thời gian |
| Trường bắt buộc | Trường nào phải có? | Request tạo đơn cần `customerId` và `items` |
| Nullable | Trường có được phép nhận null không? | `middleName` có thể null theo hợp đồng |
| Định dạng | Giá trị có đúng định dạng được quy định không? | UUID, email, date-time |
| Giới hạn số | Giá trị tối thiểu, tối đa và độ dài có đúng không? | `quantity` lớn hơn 0 |
| Enum | Giá trị có thuộc tập cho phép không? | `status` là một trong các trạng thái được công bố |
| Mảng | Kiểu phần tử, số lượng và tính duy nhất có đúng không? | `items` là mảng các item, có ít nhất một phần tử |
| Đối tượng lồng nhau | Cấu trúc con có đúng không? | Mỗi item có `productId` và `quantity` |
| Trường bổ sung | Có cho phép thuộc tính ngoài schema không? | Hợp đồng quy định reject hay ignore trường không biết |
| Header | Content-Type, Accept, Authorization và header tùy chỉnh có đúng không? | Response JSON có Content-Type phù hợp |

Không phải mọi schema đều dùng cùng cách biểu diễn null, format hoặc trường bổ sung. Hãy đọc đúng phiên bản đặc tả và xác định công cụ kiểm tra có diễn giải các từ khóa giống provider hay không.

### 2.2. Kiểm tra request schema

Request schema cần được kiểm tra với:

- Request hợp lệ tối thiểu theo hợp đồng.
- Request hợp lệ có các trường tùy chọn.
- Thiếu từng trường bắt buộc quan trọng.
- Sai kiểu dữ liệu.
- Giá trị null ở trường không cho phép null.
- Giá trị ngoài giới hạn hoặc sai định dạng.
- Enum không được hỗ trợ.
- Mảng rỗng, phần tử sai kiểu hoặc vượt giới hạn.
- Đối tượng lồng nhau thiếu hoặc sai trường.
- Trường không được công bố hoặc trường mở rộng theo chính sách.
- Header hoặc content type không phù hợp.

Không cần tạo tổ hợp mọi trường sai trong một request. Nên chọn trường hợp cô lập để xác định rõ quy tắc bị vi phạm và bổ sung một số trường hợp kết hợp có ý nghĩa để kiểm tra thứ tự xác thực hoặc xử lý nhiều lỗi.

### 2.3. Kiểm tra response schema

Response schema thường bị bỏ sót vì nhóm chỉ tập trung vào request. Tuy nhiên, response là hợp đồng mà consumer dựa vào để xử lý dữ liệu.

Kiểm tra:

- Response thành công có đủ trường được cam kết.
- Kiểu, định dạng và nullability ổn định.
- Giá trị enum thuộc tập đã công bố.
- Các trường tùy chọn xuất hiện đúng điều kiện.
- Mảng và đối tượng lồng nhau có cấu trúc đúng.
- Trường nhạy cảm hoặc trường nội bộ không bị trả ra ngoài.
- Response lỗi tuân theo schema lỗi đã thống nhất.
- Các mã trạng thái khác nhau trả về cấu trúc phù hợp.
- Header, pagination và metadata có định dạng đúng.

Nếu một trường response mới được thêm, cần đánh giá liệu consumer cũ có chấp nhận trường bổ sung không. Nếu trường cũ bị xóa, đổi kiểu hoặc đổi ý nghĩa, nguy cơ phá vỡ tương thích cao hơn.

### 2.4. Ví dụ schema request và response

Giả sử API tạo đơn hàng nhận danh sách sản phẩm và trả về mã đơn cùng trạng thái:

```yaml
CreateOrderRequest:
  type: object
  required:
    - customerId
    - items
  properties:
    customerId:
      type: string
      format: uuid
    items:
      type: array
      minItems: 1
      items:
        type: object
        required:
          - productId
          - quantity
        properties:
          productId:
            type: string
          quantity:
            type: integer
            minimum: 1
    note:
      type: string
      maxLength: 500

CreateOrderResponse:
  type: object
  required:
    - orderId
    - status
    - totalAmount
  properties:
    orderId:
      type: string
    status:
      type: string
      enum: [PENDING_PAYMENT, CONFIRMED]
    totalAmount:
      type: number
      minimum: 0
```

Từ schema này có thể tạo kiểm tra cho trường bắt buộc, kiểu UUID, mảng items, quantity và các trường response. Tuy nhiên, schema chưa mô tả đầy đủ các quy tắc như khách hàng có được phép mua sản phẩm đó không, giá lấy từ nguồn nào, tồn kho có đủ không hoặc tổng tiền đã bao gồm thuế và phí nào. Những điều đó thuộc kiểm tra ngữ nghĩa và nghiệp vụ.

### 2.5. Kiểm tra schema có tính tương thích

Khi hợp đồng thay đổi, cần đánh giá tác động đến consumer hiện tại.

| Thay đổi schema | Rủi ro thường gặp | Câu hỏi cần xác minh |
|---|---|---|
| Thêm trường response tùy chọn | Consumer nghiêm ngặt có thể từ chối trường lạ | Consumer có bỏ qua trường chưa biết không? |
| Thêm trường request bắt buộc | Consumer cũ có thể không gửi trường mới | Có default, phiên bản mới hoặc giai đoạn chuyển tiếp không? |
| Xóa trường response | Consumer đang đọc trường có thể lỗi | Có consumer nào còn phụ thuộc không? |
| Đổi kiểu trường | Consumer không parse được | Có thể thêm trường mới và duy trì trường cũ tạm thời không? |
| Thu hẹp enum | Giá trị cũ có thể không còn được chấp nhận | Có consumer hoặc dữ liệu đang dùng giá trị bị loại không? |
| Thay đổi nullable | Consumer có thể xử lý null hoặc thiếu trường sai cách | Hành vi cũ và mới có tương thích không? |
| Đổi ý nghĩa trường nhưng giữ kiểu | Schema checker có thể không phát hiện | Có cần trường mới hoặc phiên bản hợp đồng mới không? |

Một số thay đổi nhìn qua có vẻ bổ sung nhưng vẫn phá vỡ consumer. Ví dụ, thêm một trường bắt buộc trong request có thể khiến mọi client cũ gửi request không còn hợp lệ. Cần kiểm tra tương thích theo cả chiều request và response, theo cách provider và consumer sử dụng hợp đồng.

## 3. Chọn phạm vi kiểm tra ngữ nghĩa API

Schema xác nhận cấu trúc; ngữ nghĩa xác nhận giá trị và hành vi có đúng ý nghĩa hay không. Đây là lớp cần kiến thức nghiệp vụ và hiểu biết về vòng đời dữ liệu.

### 3.1. Kiểm tra quy tắc nghiệp vụ

Với mỗi endpoint, xác định:

- Điều kiện để thao tác được phép.
- Quy tắc tính toán hoặc biến đổi dữ liệu.
- Quan hệ giữa các trường.
- Điều kiện chuyển trạng thái.
- Tác động đến dữ liệu và đối tượng liên quan.
- Quyền hạn của tác nhân.
- Hành vi khi cùng một thao tác được gửi lặp hoặc đồng thời.

Ví dụ, `quantity` là số nguyên dương theo schema vẫn chưa đủ. API cần xác nhận số lượng không vượt tồn kho khả dụng, sản phẩm còn được bán và khách hàng được phép mua trong giới hạn chính sách.

### 3.2. Kiểm tra quan hệ giữa các trường

Nhiều quy tắc không thể diễn tả chỉ bằng kiểu dữ liệu của từng trường:

- `startDate` phải trước `endDate`.
- `currency` phải phù hợp với đơn vị tiền trong `amount`.
- `discountAmount` không được lớn hơn giá trị đủ điều kiện giảm.
- Nếu `paymentMethod` là chuyển khoản, một số thông tin ngân hàng có thể bắt buộc.
- Nếu `status` là CONFIRMED, phải có điều kiện xác nhận tương ứng.
- Tổng các dòng chi tiết phải khớp với tổng đơn theo quy tắc làm tròn.

Các trường hợp này cần kiểm tra ở lớp nghiệp vụ hoặc validation logic của API. Schema có thể biểu diễn một số quan hệ đơn giản, nhưng không nên giả định schema checker đã xác minh mọi bất biến.

### 3.3. Kiểm tra trạng thái và chuyển trạng thái

Với API thay đổi trạng thái, cần xác định:

- Trạng thái ban đầu hợp lệ.
- Hành động được phép trong trạng thái đó.
- Trạng thái tiếp theo.
- Các chuyển đổi bị cấm.
- Hành vi khi yêu cầu lặp.
- Tác động đến dữ liệu hoặc dịch vụ liên quan.

Ví dụ với đơn hàng:

| Trạng thái hiện tại | Hành động | Kết quả mong đợi |
|---|---|---|
| PENDING_PAYMENT | Thanh toán thành công | Chuyển sang trạng thái đã xác nhận theo quy trình |
| PENDING_PAYMENT | Hủy đơn | Hủy nếu chính sách cho phép và giải phóng giữ chỗ |
| CONFIRMED | Hủy đơn | Xử lý theo chính sách hủy sau xác nhận |
| SHIPPED | Hủy đơn | Từ chối hoặc chuyển sang quy trình trả hàng phù hợp |
| CANCELLED | Xác nhận thanh toán mới | Không tự động khôi phục đơn nếu không có quy trình hợp lệ |

Bảng là ví dụ minh họa. Trạng thái và chuyển đổi thực tế phải được xác nhận theo nghiệp vụ. Kiểm thử cần quan sát cả response và trạng thái được lưu, vì API có thể trả thành công nhưng dữ liệu chuyển sai.

### 3.4. Kiểm tra quyền và ngữ cảnh người gọi

Một request đúng schema vẫn có thể không được phép thực hiện. Phạm vi ngữ nghĩa cần xem xét:

- Người gọi đã xác thực hay chưa.
- Vai trò có quyền gọi endpoint không.
- Người gọi có quyền trên đối tượng cụ thể không.
- Có giới hạn theo tenant, tổ chức hoặc chủ sở hữu dữ liệu không.
- Quyền có thay đổi theo trạng thái đối tượng không.
- Dữ liệu nhạy cảm có bị lộ trong response hoặc error không.

Kiểm tra cả truy cập hợp lệ, thiếu quyền, quyền sai phạm vi và truy cập trực tiếp bằng ID của đối tượng không thuộc người gọi. Đừng chỉ dựa vào việc giao diện ẩn nút thao tác; API phải thực thi kiểm soát quyền ở phía server.

### 3.5. Kiểm tra tính lặp và đồng thời

Với các thao tác tạo, thanh toán, đặt chỗ hoặc cập nhật trạng thái, gửi lại request có thể tạo tác dụng phụ trùng lặp. Cần làm rõ API có hỗ trợ idempotency key hay không, key có phạm vi và thời hạn ra sao, và cùng key với payload khác được xử lý thế nào.

Các tình huống cần cân nhắc:

- Gửi cùng request hai lần liên tiếp.
- Gửi lại sau khi client timeout nhưng server có thể đã xử lý.
- Hai request đồng thời cập nhật cùng đối tượng.
- Hai người cùng lấy tài nguyên cuối cùng.
- Cùng idempotency key nhưng payload khác.
- Retry sau khi nhận lỗi tạm thời.

Kết quả cần kiểm tra số bản ghi, số giao dịch, trạng thái cuối và response của từng lần gọi. Một mã HTTP thành công không đủ chứng minh thao tác chỉ được thực hiện một lần.

### 3.6. Kiểm tra thời gian, đơn vị và độ chính xác

Các lỗi ngữ nghĩa thường xuất hiện khi dữ liệu có thời gian hoặc đơn vị:

- Timestamp có timezone hay không.
- Ngày giờ được hiểu theo UTC hay múi giờ nghiệp vụ.
- Khoảng thời gian có bao gồm thời điểm đầu hoặc cuối không.
- Số tiền dùng đơn vị nhỏ nhất hay số thập phân.
- Quy tắc làm tròn và độ chính xác được áp dụng ở đâu.
- Đơn vị đo có được chuyển đổi đúng không.
- Giá trị mặc định có ý nghĩa gì khi trường bị bỏ qua.

Ví dụ, `amount: 1000` có thể là 1.000 đồng, 1.000 đơn vị tiền hoặc 10,00 theo đơn vị nhỏ nhất tùy hợp đồng. Nếu không xác định rõ đơn vị và currency, schema vẫn hợp lệ nhưng consumer có thể xử lý sai giá trị.

## 4. Chọn phạm vi kiểm tra lỗi API

Kiểm thử lỗi xác nhận API phản hồi đúng khi điều kiện không đạt và không tạo ra tác dụng phụ sai. Phạm vi cần bao gồm cả lỗi do client, quyền hạn, trạng thái nghiệp vụ, giới hạn hệ thống và phụ thuộc.

### 4.1. Nhóm lỗi cần xem xét

| Nhóm | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Request không hợp lệ | Thiếu trường, sai kiểu, sai format | Mã trạng thái, cấu trúc lỗi, không tạo dữ liệu |
| Xác thực | Token thiếu, hết hạn hoặc không hợp lệ | Từ chối truy cập, không lộ thông tin |
| Phân quyền | Vai trò hoặc chủ sở hữu không đủ quyền | Không thực hiện thao tác, không tiết lộ dữ liệu ngoài phạm vi |
| Không tìm thấy | ID không tồn tại hoặc tài nguyên không khả dụng | Phản hồi nhất quán và không làm thay đổi trạng thái |
| Xung đột trạng thái | Cập nhật không phù hợp trạng thái hiện tại | Báo xung đột theo hợp đồng và giữ dữ liệu nhất quán |
| Giới hạn sử dụng | Vượt rate limit hoặc quota | Phản hồi giới hạn và thông tin retry nếu có |
| Phụ thuộc lỗi | Database, dịch vụ ngoài hoặc hàng đợi không sẵn sàng | Timeout, lỗi tạm thời, phục hồi và trạng thái cuối |
| Lỗi nội bộ | Exception hoặc lỗi xử lý ngoài dự kiến | Phản hồi an toàn, log có thể truy vết, không lộ chi tiết nhạy cảm |
| Payload quá lớn | Vượt giới hạn kích thước hoặc số phần tử | Từ chối có kiểm soát, không làm cạn tài nguyên |
| Trùng lặp hoặc đồng thời | Gửi lại hoặc tranh chấp tài nguyên | Không tạo tác dụng phụ trùng và xử lý xung đột đúng |

Không phải mọi API cần tất cả tình huống với cùng mức độ. Chọn theo chức năng, rủi ro, hợp đồng và khả năng ảnh hưởng đến consumer.

### 4.2. Kiểm tra mã trạng thái và error schema

Với mỗi lỗi được công bố, xác nhận:

- Mã trạng thái HTTP hoặc mã lỗi theo giao thức phù hợp.
- Content-Type và cấu trúc payload.
- Mã lỗi máy đọc được có ổn định theo hợp đồng.
- Thông điệp đủ hữu ích nhưng không tiết lộ thông tin nhạy cảm.
- Trường chi tiết hoặc lỗi theo từng field nếu hợp đồng yêu cầu.
- Correlation ID hoặc trace ID để hỗ trợ điều tra nếu được thiết kế.
- Header retry hoặc thời điểm thử lại nếu có.
- Không trả stack trace, câu truy vấn, secret hoặc dữ liệu nội bộ cho consumer.

Không nên giả định mọi lỗi đều dùng một mã chung. Ví dụ, request sai cấu trúc thường được xử lý khác với request hợp lệ về cấu trúc nhưng xung đột với trạng thái hiện tại. Mã và cấu trúc cụ thể phải theo hợp đồng đã thống nhất.

### 4.3. Phân biệt lỗi client và lỗi server

Ở mức khái quát, nhóm có thể xem xét:

- **Lỗi phía client:** request không hợp lệ, thiếu xác thực, không đủ quyền, tài nguyên không tồn tại hoặc xung đột trạng thái.
- **Lỗi phía server hoặc phụ thuộc:** lỗi nội bộ, dịch vụ phụ thuộc không sẵn sàng, gateway timeout hoặc lỗi xử lý tạm thời.

Cách phân loại này giúp định hướng retry và chẩn đoán, nhưng không nên chỉ dựa vào dải mã trạng thái để quyết định. Hợp đồng cần nói rõ lỗi nào có thể thử lại, lỗi nào cần sửa request hoặc yêu cầu người dùng can thiệp.

### 4.4. Kiểm tra tác dụng phụ khi API thất bại

Một API có thể trả lỗi nhưng đã tạo một phần dữ liệu. Đây là vấn đề quan trọng với thao tác nhiều bước.

Ví dụ, API tạo đơn ghi bản ghi đơn hàng, sau đó gọi dịch vụ thanh toán và gặp timeout. Cần xác định trạng thái nào được phép tồn tại, cách đối soát và cơ chế thử lại. Kiểm thử nên xác minh:

- Có bản ghi nào đã được tạo hoặc cập nhật?
- Trạng thái có phản ánh đúng mức độ hoàn tất không?
- Có giao dịch hoặc sự kiện trùng không?
- Có cơ chế rollback, compensation hoặc reconciliation không?
- Request retry có tạo thêm tác dụng phụ không?
- Consumer có đủ thông tin để biết kết quả chưa xác định không?

Đừng mặc định timeout nghĩa là server chưa xử lý. Client có thể mất phản hồi sau khi server đã hoàn tất thao tác. Với thao tác có tác dụng phụ, cần kiểm tra cơ chế truy vấn trạng thái hoặc idempotency.

### 4.5. Kiểm tra lỗi bảo mật và dữ liệu

Với lỗi xác thực, phân quyền và validation, cần xác nhận:

- Không thể truy cập tài nguyên bằng cách thay ID.
- Không tiết lộ sự tồn tại của tài khoản hoặc dữ liệu nếu chính sách yêu cầu che giấu.
- Không trả lại dữ liệu nhạy cảm trong response lỗi.
- Không ghi secret hoặc token vào log không phù hợp.
- Không thể dùng trường bổ sung để ghi đè thuộc tính được bảo vệ.
- Đầu vào được xử lý an toàn ở truy vấn, biểu thức hoặc lệnh.
- Thông tin lỗi không tạo kênh dò tìm hoặc lộ cấu trúc nội bộ.

Các kiểm tra này cần dữ liệu và tài khoản được cấp phép trong môi trường phù hợp. Phạm vi kiểm thử bảo mật cần tuân theo quy trình và quyền truy cập của tổ chức.

## 5. Phân bổ kiểm tra schema, ngữ nghĩa và lỗi theo tầng

Không phải mọi kiểm tra đều cần thực hiện qua cùng một tầng. Chọn tầng phù hợp giúp phản hồi nhanh, cô lập nguyên nhân và vẫn giữ được bằng chứng tích hợp.

### 5.1. Ma trận phân bổ gợi ý

| Mục tiêu | Tầng phù hợp | Lý do |
|---|---|---|
| Kiểu, required, enum và giới hạn schema | Unit / schema validation / contract | Kiểm tra nhanh và có thể tạo nhiều trường hợp |
| Request và response đúng với OpenAPI hoặc JSON Schema | Contract test | Phát hiện lệch hợp đồng giữa provider và consumer |
| Quy tắc quan hệ giữa trường | Unit / component / API test | Có thể kiểm tra logic nghiệp vụ với dữ liệu kiểm soát |
| Quyền truy cập theo vai trò và đối tượng | API integration / security test | Cần xác nhận kiểm soát thực ở phía server |
| Chuyển trạng thái và tác dụng phụ | Component / integration | Kiểm tra logic và tương tác với lưu trữ hoặc dịch vụ |
| Timeout, retry, idempotency | Integration / fault injection | Cần kiểm tra hành vi ở ranh giới phụ thuộc |
| Hành trình nghiệp vụ xuyên dịch vụ | E2E | Xác nhận kết quả cuối cùng cho consumer hoặc người dùng |
| Hiệu năng và giới hạn tải API | Performance test | Đo trong điều kiện tải, dữ liệu và môi trường xác định |

### 5.2. Dùng contract test đúng mục tiêu

Contract test xác nhận provider và consumer hiểu cùng một hợp đồng. Nó đặc biệt hữu ích khi các nhóm phát triển độc lập hoặc triển khai theo lịch khác nhau.

Có thể kiểm tra:

- Consumer chỉ yêu cầu các trường provider cam kết hỗ trợ.
- Provider trả về schema và status phù hợp.
- Các giá trị enum, nullability và trường tùy chọn không phá vỡ consumer.
- Header, version và error response được giữ nhất quán.
- Thay đổi hợp đồng không làm hỏng các consumer đã đăng ký.

Contract test không thay thế kiểm thử nghiệp vụ đầy đủ. Một provider có thể trả JSON đúng schema nhưng tổng tiền hoặc trạng thái vẫn sai. Vì vậy, cần thêm kiểm thử ngữ nghĩa ở tầng phù hợp.

### 5.3. Tránh lặp kiểm tra không tạo thêm bằng chứng

Nếu cùng một quy tắc schema đã được xác minh bằng validator trong CI, không nhất thiết lặp mọi tổ hợp qua E2E. E2E nên tập trung vào một số hành trình đại diện và xác nhận các điểm tích hợp quan trọng.

Tuy nhiên, cần có kiểm tra ở provider thực tế để bảo đảm cấu hình và serialization không làm response khác với schema đã xác thực. Kiểm thử hợp đồng và kiểm thử triển khai có thể bổ sung cho nhau.

## 6. Xác định phạm vi theo thay đổi và rủi ro

Phạm vi kiểm tra API cần được cập nhật khi schema, logic, quyền hạn, cấu hình hoặc phụ thuộc thay đổi.

### 6.1. Khi thay đổi schema

Mở rộng kiểm tra khi:

- Thêm, xóa hoặc đổi tên trường.
- Đổi kiểu, format, enum hoặc nullability.
- Thay đổi trường bắt buộc hoặc giới hạn.
- Thay đổi cấu trúc đối tượng lồng nhau.
- Thay đổi response hoặc error schema.
- Thay đổi version hoặc content negotiation.
- Có consumer mới hoặc consumer cũ chưa được cập nhật.

Tìm consumer thực tế và xác định cách họ dùng trường. Không thể kết luận tương thích chỉ dựa vào việc schema validator của provider chạy qua.

### 6.2. Khi thay đổi ngữ nghĩa

Mở rộng kiểm tra khi:

- Thay đổi công thức hoặc quy tắc nghiệp vụ.
- Thay đổi trạng thái và chuyển trạng thái.
- Thay đổi nguồn dữ liệu hoặc cách tính dữ liệu dẫn xuất.
- Thay đổi quyền hạn hoặc phạm vi tài nguyên.
- Thay đổi idempotency, retry hoặc xử lý đồng thời.
- Thay đổi thời gian, đơn vị, làm tròn hoặc quy tắc mặc định.
- Thay đổi thứ tự xử lý hoặc hành vi bất đồng bộ.

Ngoài các trường hợp mới, cần kiểm tra lại các consumer và luồng nghiệp vụ phụ thuộc vào ý nghĩa cũ.

### 6.3. Khi thay đổi xử lý lỗi

Mở rộng kiểm tra khi:

- Thay đổi mã trạng thái hoặc error code.
- Thay đổi payload lỗi hoặc thông điệp.
- Thay đổi điều kiện retry hoặc timeout.
- Thay đổi rollback, compensation hoặc reconciliation.
- Thay đổi cách log và mã tương quan.
- Thay đổi cơ chế xác thực, phân quyền hoặc giới hạn sử dụng.

Một thay đổi error response có thể phá vỡ client dù luồng thành công không thay đổi. Consumer có thể dựa vào status, error code hoặc trường chi tiết để hiển thị thông báo và quyết định retry.

### 6.4. Ưu tiên theo rủi ro

Đánh giá các yếu tố:

1. Mức độ hậu quả nếu API xử lý sai.
2. Số lượng consumer và phạm vi người dùng bị ảnh hưởng.
3. Khả năng xảy ra lỗi và độ phức tạp của đường xử lý.
4. Khả năng phát hiện hoặc đối soát.
5. Khả năng phục hồi và đảo ngược tác dụng phụ.
6. Lịch sử lỗi ở endpoint hoặc dịch vụ.
7. Mức độ thay đổi của hợp đồng và phụ thuộc.

| Mức ưu tiên | Dấu hiệu | Phạm vi gợi ý |
|---|---|---|
| Rất cao | API xử lý tiền, quyền truy cập nhạy cảm, dữ liệu quan trọng hoặc luồng cốt lõi | Schema request/response, ngữ nghĩa, lỗi, bảo mật, retry và tác dụng phụ |
| Cao | Nhiều consumer hoặc phụ thuộc liên dịch vụ | Contract, schema, luồng chính, lỗi phổ biến và tương thích |
| Trung bình | API có phạm vi sử dụng giới hạn, tác động có thể phục hồi | Schema, quy tắc chính và lỗi đại diện |
| Thấp | API nội bộ ít dùng, rủi ro thấp và dễ phát hiện | Kiểm tra hợp đồng và các quy tắc cơ bản; mở rộng khi có thay đổi |

Đây là hướng dẫn phân bổ, không phải thay thế đánh giá nghiệp vụ. Một endpoint ít được gọi nhưng cấp quyền truy cập dữ liệu nhạy cảm vẫn có thể có mức ưu tiên rất cao.

## 7. Ví dụ tổng hợp: API tạo đơn hàng

Giả sử API `POST /orders` nhận khách hàng và danh sách sản phẩm, sau đó tạo đơn và khởi tạo thanh toán.

### 7.1. Phạm vi schema

| Trường hợp | Loại kiểm tra | Kết quả mong đợi |
|---|---|---|
| Thiếu `customerId` | Required | Từ chối theo hợp đồng |
| `customerId` sai format | Format | Từ chối request |
| `items` là mảng rỗng | Constraint | Từ chối request |
| `quantity` là chuỗi | Type | Từ chối request |
| `quantity` bằng 0 hoặc âm | Schema/business constraint | Từ chối theo quy tắc |
| `note` dài hơn giới hạn | Length | Từ chối hoặc xử lý theo hợp đồng |
| Response thiếu `orderId` | Response schema | Phát hiện provider không tuân thủ hợp đồng |

### 7.2. Phạm vi ngữ nghĩa

| Trường hợp | Mục tiêu xác minh | Bằng chứng |
|---|---|---|
| Khách hàng tồn tại và được phép đặt | Quyền và điều kiện nghiệp vụ | Kết quả API và bản ghi đơn |
| Sản phẩm còn hàng | Quy tắc tồn kho | Số lượng giữ hoặc trừ |
| Sản phẩm không còn hàng | Từ chối đúng và không tạo đơn đã xác nhận | Response, trạng thái đơn và tồn kho |
| Giá thay đổi trước khi xác nhận | Dùng nguồn giá có thẩm quyền | Chi tiết giá và tổng đơn |
| Hai request đồng thời mua sản phẩm cuối | Không vượt tồn kho | Số đơn xác nhận và số lượng còn lại |
| Cùng idempotency key được gửi lại | Không tạo tác dụng phụ trùng | Mã đơn, mã giao dịch và response |
| Khách không sở hữu tài nguyên | Không truy cập trái phép | Status, error code và không rò dữ liệu |

### 7.3. Phạm vi lỗi

| Tình huống | Điều cần kiểm tra |
|---|---|
| Thiếu hoặc sai token | Từ chối xác thực, không tạo đơn |
| Token hợp lệ nhưng thiếu quyền | Từ chối phân quyền, không lộ dữ liệu |
| Dịch vụ tồn kho timeout | Trạng thái đơn không bị xác nhận sai |
| Cổng thanh toán từ chối | Đơn và thanh toán phản ánh đúng kết quả |
| Server timeout sau khi đã tạo đơn | Client có thể truy vấn hoặc retry an toàn |
| Vượt rate limit | Response và thông tin retry theo hợp đồng |
| Lỗi nội bộ | Error response an toàn, có mã truy vết phù hợp |
| Payload quá lớn | Từ chối có kiểm soát và không làm cạn tài nguyên |

### 7.4. Kết luận phạm vi

Với API tạo đơn hàng, schema cần được kiểm tra ở cả request và response; ngữ nghĩa cần bao phủ quyền, tồn kho, giá, trạng thái và idempotency; lỗi cần bao phủ xác thực, xung đột, phụ thuộc và timeout. Các tổ hợp chi tiết có thể được kiểm tra ở unit hoặc component, còn tích hợp và E2E xác nhận phối hợp thực giữa dịch vụ đơn hàng, tồn kho và thanh toán.

## 8. Ghi nhận phạm vi và bằng chứng

### 8.1. Mẫu ma trận kiểm tra API

| Trường | Nội dung |
|---|---|
| API ID | Mã endpoint hoặc operation |
| Consumer / Provider | Bên sử dụng và bên cung cấp |
| Version | Phiên bản hợp đồng |
| Schema scope | Request, response, header, error schema |
| Semantic scope | Quy tắc, bất biến, quyền, trạng thái và tác dụng phụ |
| Error scope | Mã lỗi, error payload, retry và phục hồi |
| Rủi ro | Hậu quả nếu hợp đồng hoặc hành vi sai |
| Test ID | Các trường hợp kiểm thử liên quan |
| Tầng kiểm thử | Schema, contract, component, integration, E2E |
| Bằng chứng | Response, log, dữ liệu, trace hoặc báo cáo |
| Trạng thái | Chưa thiết kế, sẵn sàng, đạt, không đạt, bị chặn |
| Giới hạn | Điều kiện chưa kiểm tra hoặc phụ thuộc được mô phỏng |

### 8.2. Mẫu truy vết hợp đồng

Một luồng truy vết có thể tổ chức như sau:

```
API requirement
    -> API operation / contract version
        -> Schema rule
        -> Semantic rule
        -> Error behavior
            -> Test case
                -> Execution evidence
                    -> Decision
```

Ví dụ:

| Requirement | Contract rule | Test case | Bằng chứng |
|---|---|---|---|
| Tạo đơn hợp lệ | Request cần customerId và items | API-001 | Request/response và bản ghi đơn |
| Không bán vượt tồn kho | quantity được kiểm tra với tồn kho khả dụng | API-002 | Số lượng giữ và trạng thái đơn |
| Không thu tiền trùng | Idempotency key duy nhất trong phạm vi xác định | API-003 | Mã giao dịch và số lần thu |
| Không truy cập đơn người khác | Quyền kiểm tra theo chủ sở hữu | API-004 | Response lỗi và không có dữ liệu lộ |
| Xử lý timeout an toàn | Trạng thái có thể đối soát sau timeout | API-005 | Trace, trạng thái đơn và giao dịch |

### 8.3. Ghi nhận giới hạn và điều chưa kiểm tra

Nếu một phụ thuộc không có môi trường thử nghiệm hoặc không thể mô phỏng một lỗi, hãy ghi rõ:

- Thành phần nào được thay thế bằng mock hoặc stub.
- Tình huống nào không thể tái hiện.
- Bằng chứng nào được dùng thay thế.
- Rủi ro còn lại.
- Người chịu trách nhiệm chấp nhận hoặc theo dõi.
- Điều kiện để kiểm tra lại khi môi trường sẵn sàng.

Không nên báo cáo “API đã kiểm thử đầy đủ” nếu chỉ xác minh schema mà chưa kiểm tra ngữ nghĩa hoặc lỗi quan trọng.

## 9. Những sai lầm thường gặp

1. **Chỉ kiểm tra schema:** request và response đúng kiểu nhưng dữ liệu hoặc quy tắc nghiệp vụ sai.
2. **Bỏ qua response schema:** consumer gặp lỗi vì provider thay đổi kiểu hoặc thiếu trường.
3. **Coi schema là toàn bộ hợp đồng:** bỏ qua quyền, trạng thái, idempotency và ý nghĩa dữ liệu.
4. **Chỉ kiểm tra mã HTTP:** không kiểm tra error payload, tác dụng phụ và trạng thái cuối.
5. **Retry mọi lỗi:** tạo tác dụng phụ trùng hoặc làm tăng tải khi lỗi không thể phục hồi bằng retry.
6. **Không kiểm tra timeout sau xử lý:** hiểu nhầm client timeout là server chưa thực hiện thao tác.
7. **Không xác minh quyền ở API:** chỉ kiểm tra giao diện và bỏ qua truy cập trực tiếp.
8. **Bỏ qua tương thích consumer:** thay đổi schema mà không tìm các bên đang sử dụng.
9. **Chỉ kiểm thử endpoint riêng lẻ:** không kiểm tra tương tác với dịch vụ và dữ liệu liên quan.
10. **Dùng mock nhưng kết luận đã xác minh tích hợp thật:** không công khai giới hạn bằng chứng.
11. **Không truy vết phiên bản hợp đồng:** kết quả kiểm thử không rõ áp dụng cho phiên bản nào.
12. **Đánh giá thấp lỗi ngữ nghĩa:** một response hợp lệ về cấu trúc vẫn có thể gây hậu quả tài chính hoặc quyền truy cập.

## 10. Checklist chọn phạm vi kiểm tra API

- [ ] Đã xác định API, consumer, provider và phiên bản hợp đồng.
- [ ] Đã xác định request, response, header và error schema liên quan.
- [ ] Đã kiểm tra kiểu, trường bắt buộc, nullability, format, enum và giới hạn.
- [ ] Đã đánh giá tương thích khi thêm, xóa hoặc đổi trường.
- [ ] Đã xác định quy tắc nghiệp vụ và quan hệ giữa các trường.
- [ ] Đã kiểm tra quyền, trạng thái, idempotency và xử lý đồng thời nếu liên quan.
- [ ] Đã xác định lỗi đầu vào, xác thực, phân quyền, xung đột và phụ thuộc.
- [ ] Đã kiểm tra mã trạng thái, error schema, thông tin retry và bảo vệ dữ liệu.
- [ ] Đã xác minh tác dụng phụ khi lỗi, timeout hoặc retry.
- [ ] Đã phân bổ kiểm tra vào schema, contract, unit, component, integration hoặc E2E phù hợp.
- [ ] Đã liên kết yêu cầu, quy tắc hợp đồng, test case và bằng chứng.
- [ ] Đã ghi rõ phụ thuộc mô phỏng, giới hạn và rủi ro còn lại.
- [ ] Đã xác định người chịu trách nhiệm xác nhận kết quả và chấp nhận rủi ro.

Chọn đúng phạm vi kiểm tra schema, ngữ nghĩa và lỗi giúp nhóm xác nhận API ở cả cấu trúc, ý nghĩa và hành vi khi điều kiện không thuận lợi. Khi các lớp kiểm tra được phân bổ theo hợp đồng và rủi ro, consumer có bằng chứng đáng tin cậy hơn để tích hợp, còn provider có thể thay đổi API với mức kiểm soát rõ ràng.
