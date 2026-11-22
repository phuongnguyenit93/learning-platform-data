# Thiết kế schema JSON và quy tắc kiểm tra dữ liệu đầu vào

Trong hệ thống serverless, dữ liệu đi vào function từ HTTP request, queue hoặc event source thường được tạo bởi một thành phần khác. Thành phần gửi và thành phần nhận có thể được triển khai, mở rộng hoặc cập nhật độc lập. Vì vậy, hai phía cần thống nhất một **hợp đồng dữ liệu**: dữ liệu có cấu trúc gì, trường nào bắt buộc, giá trị nào hợp lệ và cách xử lý khi hợp đồng không được đáp ứng.

JSON là định dạng trao đổi phổ biến, nhưng một payload parse được thành JSON chưa chắc đã hợp lệ với nghiệp vụ. Ví dụ, chuỗi rỗng vẫn là một giá trị JSON hợp lệ; một đơn hàng có số lượng bằng 0 vẫn có thể đúng cú pháp JSON nhưng sai quy tắc nghiệp vụ. Thiết kế schema và quy tắc validation giúp phát hiện những trường hợp này ngay tại ranh giới hệ thống.

Bài học tập trung vào ba việc: mô tả cấu trúc bằng JSON Schema, kiểm tra dữ liệu trong Java và áp dụng cùng một hợp đồng cho HTTP, message và event.

## 1. Hợp đồng dữ liệu là gì?

Hợp đồng dữ liệu (data contract) là thỏa thuận giữa bên tạo dữ liệu và bên sử dụng dữ liệu. Hợp đồng cần mô tả ít nhất:

- **Cấu trúc:** object có những trường nào, kiểu dữ liệu của từng trường và quan hệ lồng nhau.
- **Tính bắt buộc:** trường nào phải xuất hiện, trường nào được phép bỏ qua hoặc nhận giá trị null.
- **Miền giá trị:** độ dài chuỗi, khoảng số, tập giá trị cho phép, định dạng thời gian và số phần tử trong mảng.
- **Ngữ nghĩa:** trường đại diện cho điều gì, đơn vị đo là gì, thời điểm được hiểu theo múi giờ nào.
- **Quy tắc tiến hóa:** khi thêm, bỏ hoặc đổi trường thì bên gửi và bên nhận phải tương thích như thế nào.
- **Hành vi khi lỗi:** request bị từ chối ra sao, message lỗi có được retry hay chuyển sang dead-letter queue.

Hợp đồng không chỉ là một file schema. Nó còn gồm quy ước đặt tên, ý nghĩa nghiệp vụ, cách xác thực, phiên bản và chính sách xử lý lỗi.

### Ví dụ: yêu cầu tạo đơn hàng

Một client gửi dữ liệu tạo đơn hàng:

```json
{
  "customerId": "cus_123",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ],
  "currency": "VND",
  "requestedAt": "2026-11-17T10:15:30Z"
}
```

Hợp đồng có thể quy định:

- customerId là chuỗi định danh, không được để trống.
- items là mảng có ít nhất một phần tử và có giới hạn số dòng hàng.
- Mỗi dòng hàng phải có sku và quantity.
- quantity là số nguyên dương trong một khoảng cho phép.
- currency là mã tiền tệ theo quy ước đã thống nhất.
- requestedAt là thời điểm theo định dạng ngày giờ có múi giờ.

Những quy tắc này phải được mô tả rõ để client, API Gateway, function và hệ thống xử lý message không tự suy diễn khác nhau.

## 2. Phân biệt cú pháp JSON, schema và quy tắc nghiệp vụ

Validation nên được tổ chức thành nhiều lớp vì mỗi lớp phát hiện một nhóm lỗi khác nhau.

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Cú pháp và parse | Payload có phải JSON hợp lệ và có thể đọc được không? | Thiếu dấu ngoặc kép, dấu phẩy sai vị trí |
| Cấu trúc/schema | JSON có đúng kiểu và cấu trúc hợp đồng không? | quantity là chuỗi, thiếu customerId, items là object thay vì array |
| Ràng buộc dữ liệu | Giá trị có nằm trong giới hạn đã khai báo không? | quantity bằng 0, sku quá dài |
| Nghiệp vụ | Dữ liệu có hợp lệ trong bối cảnh hệ thống hiện tại không? | Khách hàng bị khóa, SKU không tồn tại, số lượng vượt tồn kho |
| Quyền truy cập | Người gọi có được phép thực hiện hành động trên dữ liệu này không? | Người dùng sửa đơn hàng thuộc tài khoản khác |

JSON Schema mô tả cấu trúc và nhiều ràng buộc dữ liệu. Bean Validation trong Java giúp kiểm tra object sau khi deserialize. Các quy tắc nghiệp vụ và quyền truy cập thường cần logic ứng dụng hoặc truy vấn dữ liệu hiện tại.

Không nên coi một lần kiểm tra schema là bằng chứng rằng request an toàn hoặc thao tác được phép. Ví dụ, customerId đúng định dạng không chứng minh người gọi có quyền tạo đơn cho khách hàng đó.

## 3. Thiết kế schema JSON

JSON Schema là một ngôn ngữ mô tả cấu trúc và ràng buộc của tài liệu JSON. Một schema có thể được dùng trong kiểm thử, tài liệu API, kiểm tra message hoặc xác thực payload trước khi gọi logic nghiệp vụ.

Ví dụ sau sử dụng JSON Schema Draft 2020-12:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/create-order-v1.json",
  "title": "CreateOrderRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["customerId", "items", "currency"],
  "properties": {
    "customerId": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64,
      "pattern": "^[A-Za-z0-9_-]+$"
    },
    "items": {
      "type": "array",
      "minItems": 1,
      "maxItems": 50,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["sku", "quantity"],
        "properties": {
          "sku": {
            "type": "string",
            "minLength": 1,
            "maxLength": 40
          },
          "quantity": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000
          }
        }
      }
    },
    "currency": {
      "type": "string",
      "pattern": "^[A-Z]{3}$"
    },
    "requestedAt": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

Một số keyword quan trọng:

| Keyword | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| type | Kiểu JSON được chấp nhận | object, array, string, integer, number, boolean, null |
| properties | Schema cho từng thuộc tính của object | customerId, items |
| required | Danh sách trường phải xuất hiện | customerId và items |
| additionalProperties | Có cho phép trường chưa khai báo không | false để từ chối trường dư |
| minLength, maxLength | Giới hạn độ dài chuỗi | SKU không quá 40 ký tự |
| minimum, maximum | Giới hạn giá trị số | quantity từ 1 đến 1000 |
| minItems, maxItems | Giới hạn số phần tử mảng | Đơn hàng có từ 1 đến 50 dòng |
| enum, const | Tập giá trị hoặc một giá trị cố định | Trạng thái thuộc tập cho phép |
| pattern | Ràng buộc bằng biểu thức chính quy | Mã định danh theo quy ước |
| format | Gợi ý hoặc kiểm tra định dạng chuyên biệt | date-time, email, uri |

Schema có thể tham chiếu schema khác bằng $ref để tái sử dụng cấu trúc như Address hoặc Money. Khi schema phát triển, nên đặt tên và quản lý phiên bản rõ ràng thay vì sao chép một cấu trúc ở nhiều nơi.

### Trường bắt buộc, trường tùy chọn và null

Ba trạng thái sau khác nhau:

1. Trường không xuất hiện trong JSON.
2. Trường xuất hiện với giá trị null.
3. Trường xuất hiện với một giá trị cụ thể.

Ví dụ, nếu middleName là tùy chọn và không chấp nhận null, client có thể bỏ hẳn trường khi không có dữ liệu. Nếu hợp đồng cho phép null, schema Draft 2020-12 có thể khai báo kiểu như sau:

```json
{
  "type": ["string", "null"]
}
```

Việc trường có nằm trong required hay không là một quy tắc riêng. Một trường có thể bắt buộc xuất hiện nhưng được phép nhận null; ngược lại, trường có thể không bắt buộc xuất hiện nhưng nếu xuất hiện thì phải là string.

Cần quyết định rõ ý nghĩa của chuỗi rỗng, chuỗi chỉ chứa khoảng trắng và null. Với tên người dùng, chuỗi chỉ có khoảng trắng thường không có giá trị; với một ghi chú, chuỗi rỗng có thể được chấp nhận tùy nghiệp vụ. Schema có minLength, nhưng việc loại bỏ khoảng trắng đầu/cuối thường cần quy tắc bổ sung ở tầng ứng dụng.

### Chọn kiểu dữ liệu và đơn vị

- Dùng integer cho số đếm như quantity, retryCount hoặc số phần tử.
- Dùng number cho giá trị số có phần thập phân khi hợp đồng thực sự cần kiểu số JSON.
- Với tiền tệ, cân nhắc biểu diễn bằng số nguyên theo đơn vị nhỏ nhất (ví dụ đồng hoặc xu) hoặc chuỗi thập phân có quy tắc rõ ràng. Trong Java, dùng BigDecimal cho phép tính tiền; tránh dùng float hoặc double để tính toán tài chính.
- Dùng string cho mã định danh, số điện thoại, mã bưu chính và các giá trị có số 0 ở đầu hoặc không mang ý nghĩa số học.
- Dùng boolean cho trạng thái đúng/sai thực sự, không dùng chuỗi "true" hoặc số 0/1 nếu hợp đồng đã quy định boolean.
- Dùng thời điểm ISO 8601 có offset hoặc UTC. Thống nhất cách diễn giải và độ chính xác; không gửi thời điểm địa phương không có múi giờ nếu hệ thống cần xác định một thời điểm tuyệt đối.

JSON Schema có keyword format, nhưng cách validator thực thi format phụ thuộc thư viện và cấu hình. Với một số implementation theo Draft 2020-12, format có thể được xử lý như annotation nếu chưa bật format assertion. Vì vậy, cần kiểm tra cấu hình validator và bổ sung kiểm tra thực tế khi định dạng là điều kiện bắt buộc.

### Có nên từ chối trường không được khai báo?

additionalProperties: false giúp phát hiện lỗi chính tả và ngăn client gửi các trường ngoài hợp đồng. Nó hữu ích với command hoặc request có cấu trúc cần kiểm soát chặt. Tuy nhiên, nếu producer thêm một trường mới, consumer cũ dùng schema nghiêm ngặt có thể từ chối payload dù trường mới không ảnh hưởng đến consumer đó.

Có thể chọn chính sách theo loại hợp đồng:

- Với command đầu vào cần kiểm soát rõ, từ chối trường không biết giúp tránh lỗi và giảm nguy cơ mass assignment.
- Với event được nhiều consumer sử dụng độc lập, cho phép hoặc bỏ qua trường chưa biết thường giúp tiến hóa tương thích hơn.
- Dù chọn chính sách nào, phải kiểm thử hành vi của parser và mapper Java khi gặp trường mới.

Không nên âm thầm bỏ qua các trường có ý nghĩa bảo mật hoặc ảnh hưởng nghiệp vụ. Nếu bỏ qua trường lạ, cần ghi nhận đủ thông tin để phát hiện producer và consumer đang lệch hợp đồng.

## 4. Quy tắc đặt tên và thiết kế payload

Một schema tốt cần nhất quán và dễ hiểu đối với mọi thành phần tham gia.

**Tên trường.** Chọn một quy ước như camelCase và dùng xuyên suốt. Tránh cùng một ý nghĩa nhưng nơi dùng customer_id, nơi dùng customerId. Tên nên thể hiện ngữ nghĩa thay vì cách triển khai nội bộ.

**Đơn vị đo.** Ghi rõ đơn vị trong tên hoặc tài liệu. Ví dụ timeoutMillis dễ hiểu hơn timeout nếu giá trị là mili giây. Với dung lượng, xác định byte, KB hay MiB.

**Mã định danh.** Chọn một định dạng ổn định. Không dùng tên hiển thị làm khóa tham chiếu nếu tên có thể thay đổi. Nếu cần duy nhất trên nhiều hệ thống, dùng ID có phạm vi duy nhất rõ ràng.

**Thời gian.** Thống nhất UTC hoặc offset ISO 8601, ví dụ 2026-11-17T10:15:30Z. Phân biệt thời điểm xảy ra (occurredAt) với thời điểm hệ thống nhận hoặc xử lý (receivedAt, processedAt).

**Dữ liệu dẫn xuất.** Tránh để client quyết định giá trị mà server có thể tính đáng tin cậy. Ví dụ, server nên tự tính tổng tiền từ giá và số lượng đã xác minh thay vì tin vào totalAmount do client gửi.

**Kích thước payload.** Đặt giới hạn cho body, độ sâu object, số phần tử mảng, độ dài chuỗi và kích thước từng message. Giới hạn phải phù hợp với API Gateway, queue, event source và runtime mà hệ thống sử dụng.

**Dữ liệu nhạy cảm.** Không đưa mật khẩu, access token hoặc dữ liệu bí mật không cần thiết vào event. Event thường được lưu, retry, sao chép và chuyển qua nhiều dịch vụ; chỉ phát hành dữ liệu tối thiểu cần cho consumer.

## 5. Kiểm tra dữ liệu đầu vào trong Java

Trong Java, quy trình phổ biến gồm parse JSON thành DTO, kiểm tra constraint, rồi áp dụng quy tắc nghiệp vụ. Jackson thường được dùng để deserialize JSON; Jakarta Bean Validation cung cấp annotation và API để kiểm tra object.

Ví dụ DTO dùng record và Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 64)
        @Pattern(regexp = "^[A-Za-z0-9_-]+$")
        String customerId,

        @NotEmpty
        @Size(max = 50)
        List<@Valid OrderItemRequest> items,

        @NotBlank
        @Pattern(regexp = "^[A-Z]{3}$")
        String currency
) {}

public record OrderItemRequest(
        @NotBlank
        @Size(max = 40)
        String sku,

        @Positive
        int quantity
) {}
```

Annotation có ý nghĩa như sau:

- @NotBlank yêu cầu chuỗi không null và có ít nhất một ký tự không phải khoảng trắng.
- @NotEmpty yêu cầu collection hoặc chuỗi không null và không rỗng.
- @Size giới hạn độ dài hoặc số phần tử.
- @Pattern kiểm tra chuỗi theo biểu thức chính quy.
- @Positive yêu cầu số lớn hơn 0.
- @Valid yêu cầu validator tiếp tục kiểm tra object lồng bên trong hoặc phần tử collection.

Bean Validation chỉ kiểm tra các constraint đã khai báo. Nếu cần kiểm tra currency có được hệ thống hỗ trợ hay SKU có tồn tại, hãy dùng service nghiệp vụ sau bước kiểm tra DTO.

### Gọi Validator

Có thể dùng Validator được tạo khi ứng dụng khởi động và tái sử dụng trong các lần gọi. Ví dụ dưới đây minh họa phần kiểm tra sau khi request đã được deserialize:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

public class OrderRequestValidator {

    private final Validator validator;

    public OrderRequestValidator(Validator validator) {
        this.validator = validator;
    }

    public void validate(CreateOrderRequest request) {
        Set<ConstraintViolation<CreateOrderRequest>> violations =
                validator.validate(request);

        if (!violations.isEmpty()) {
            throw new InvalidRequestException(violations);
        }
    }
}
```

Trong ứng dụng thực tế, dependency injection có thể cung cấp Validator. Nếu tự tạo ValidatorFactory, nên tạo ở giai đoạn khởi động, tái sử dụng Validator và đóng factory khi ứng dụng kết thúc. Tránh tạo ValidatorFactory cho từng request vì sẽ phát sinh chi phí không cần thiết.

Khi chuyển lỗi validation thành response, nên trả tên trường, mã lỗi và thông điệp có thể hành động. Không nên đưa stack trace, giá trị bí mật hoặc toàn bộ payload vào response.

### Phân biệt lỗi parse và lỗi validation

Deserialize có thể thất bại trước khi Bean Validation chạy. Ví dụ quantity nhận chuỗi "two" trong khi DTO yêu cầu int. Hãy xử lý riêng:

- JSON sai cú pháp hoặc không thể chuyển kiểu: lỗi parse/deserialization.
- JSON parse được nhưng thiếu trường hoặc vi phạm constraint: lỗi validation.
- Dữ liệu đúng cấu trúc nhưng sai trạng thái nghiệp vụ: lỗi nghiệp vụ.
- Người gọi không có quyền: lỗi xác thực hoặc phân quyền.

Việc phân biệt giúp client sửa đúng dữ liệu và giúp hệ thống quyết định có nên retry message hay không.

## 6. Áp dụng validation cho HTTP request

HTTP function thường nhận event từ API Gateway hoặc HTTP adapter. Không nên giả định body đã được kiểm tra đầy đủ chỉ vì request đi qua gateway. Gateway có thể kiểm tra một số giới hạn hoặc schema nếu được cấu hình, nhưng handler vẫn cần xác minh dữ liệu tại ranh giới tin cậy của mình.

Một pipeline điển hình:

1. Kiểm tra kích thước body và header cần thiết.
2. Parse JSON với cấu hình parser an toàn.
3. Kiểm tra schema hoặc deserialize sang DTO có cấu trúc.
4. Chạy Bean Validation.
5. Xác thực danh tính và kiểm tra quyền trên tài nguyên liên quan.
6. Kiểm tra quy tắc nghiệp vụ và trạng thái hiện tại.
7. Thực hiện thao tác trong transaction phù hợp và trả response.

Thứ tự xác thực danh tính và validation chi tiết có thể thay đổi theo thiết kế bảo mật. Ví dụ, API có thể xác thực token trước khi đọc sâu body để tránh cho người chưa đăng nhập tiêu tốn tài nguyên. Dù vậy, không được dùng dữ liệu đầu vào để quyết định quyền truy cập mà chưa xác minh danh tính.

### Quy ước phản hồi lỗi

Một API có thể quy định:

| HTTP status | Trường hợp thường gặp |
|---|---|
| 400 Bad Request | JSON sai cú pháp, thiếu trường hoặc không đúng cấu trúc request |
| 401 Unauthorized | Thiếu hoặc không hợp lệ thông tin xác thực |
| 403 Forbidden | Đã xác thực nhưng không có quyền |
| 404 Not Found | Tài nguyên không tồn tại hoặc không được phép tiết lộ sự tồn tại |
| 409 Conflict | Xung đột với trạng thái hiện tại hoặc khóa idempotency được dùng sai |
| 422 Unprocessable Content | JSON đúng cú pháp nhưng vi phạm quy tắc nội dung/nghiệp vụ |

Việc dùng 400 hay 422 cho lỗi validation phụ thuộc quy ước API. Điều quan trọng là tài liệu hóa và giữ nhất quán. Ví dụ response lỗi có thể chứa code, message và danh sách lỗi theo field; không đưa chi tiết nội bộ hoặc stack trace ra ngoài.

## 7. Áp dụng validation cho message và event

Message và event thường được xử lý bất đồng bộ. Không có client HTTP đang chờ để sửa dữ liệu ngay lập tức, nên chính sách lỗi phải gắn với retry, xác nhận message và dead-letter queue.

### Thiết kế event envelope

Một event thường có hai phần:

- **Envelope:** thông tin định tuyến và nhận diện event như ID, nguồn phát, loại event, thời điểm và phiên bản.
- **Data payload:** dữ liệu nghiệp vụ mà consumer cần để xử lý.

Có thể dùng CloudEvents làm quy ước envelope chung. Ví dụ:

```json
{
  "specversion": "1.0",
  "id": "evt-8d3f",
  "source": "/orders/service",
  "type": "com.example.orders.created.v1",
  "subject": "orders/ord-123",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ord-123",
    "customerId": "cus_123",
    "currency": "VND",
    "items": [
      {
        "sku": "BOOK-01",
        "quantity": 2
      }
    ]
  }
}
```

Envelope giúp consumer xác định event đến từ đâu, thuộc loại nào và có thể dùng ID nào để chống xử lý lặp. Schema của data cần được quản lý theo event type và phiên bản. Không nên nhầm event ID với order ID: một đơn hàng có thể tạo ra nhiều event khác nhau.

### Quy trình xử lý message

Một consumer có thể thực hiện:

1. Kiểm tra envelope: spec version, ID, source, type và content type.
2. Chọn schema đúng theo event type và phiên bản.
3. Parse data, kiểm tra schema và DTO.
4. Kiểm tra điều kiện nghiệp vụ cần thiết.
5. Dùng event ID hoặc khóa nghiệp vụ phù hợp để bảo đảm idempotency.
6. Ghi kết quả bền vững rồi mới xác nhận message theo cơ chế của nền tảng.

Cần phân biệt lỗi có thể phục hồi và lỗi dữ liệu cố định:

- **Lỗi tạm thời:** database timeout, dịch vụ phụ thuộc quá tải hoặc lỗi mạng. Có thể retry với backoff và giới hạn số lần thử.
- **Lỗi hợp đồng:** JSON sai, thiếu trường bắt buộc, kiểu dữ liệu sai hoặc event version không hỗ trợ. Retry cùng payload thường không giải quyết được; nên ghi nhận lỗi và chuyển sang dead-letter queue hoặc luồng cách ly.
- **Lỗi nghiệp vụ:** dữ liệu đúng schema nhưng không thể áp dụng tại thời điểm hiện tại. Cần quyết định theo nghiệp vụ: retry sau, bỏ qua, yêu cầu xử lý thủ công hoặc chuyển DLQ.

Với batch message, cần biết nền tảng xác nhận cả batch hay hỗ trợ partial batch response. Nếu chỉ một phần tử lỗi, cơ chế xác nhận không phù hợp có thể khiến toàn bộ batch bị xử lý lại. Consumer vẫn phải idempotent vì retry có thể xảy ra ngay cả khi code đã thực hiện một phần tác dụng phụ.

### Giữ khả năng tương thích giữa producer và consumer

Producer và consumer có thể được triển khai ở thời điểm khác nhau. Vì vậy, hợp đồng event nên ưu tiên tiến hóa tương thích:

- Thêm trường tùy chọn thường dễ tương thích hơn thêm trường bắt buộc.
- Consumer nên bỏ qua trường chưa biết nếu hợp đồng cho phép.
- Không đổi kiểu dữ liệu hoặc ý nghĩa của trường đang dùng.
- Không xóa trường khi vẫn còn consumer phụ thuộc.
- Khi thay đổi không tương thích, tạo phiên bản schema hoặc event type mới và có kế hoạch chuyển đổi consumer.
- Nếu enum có thể mở rộng, consumer cần xử lý giá trị chưa biết theo chính sách an toàn.

Thêm trường mới có thể vẫn gây lỗi nếu consumer dùng schema với additionalProperties: false hoặc DTO mapper từ chối unknown property. Vì vậy, compatibility phải được kiểm tra trên cả schema validator, JSON deserializer và code nghiệp vụ.

## 8. An toàn khi nhận dữ liệu không tin cậy

Validation là một lớp bảo vệ, không thay thế các biện pháp bảo mật khác.

**Giới hạn tài nguyên.** Kiểm tra giới hạn kích thước body trước khi parse; giới hạn độ sâu JSON, độ dài chuỗi, số phần tử mảng và thời gian xử lý. Payload rất lớn hoặc lồng sâu có thể làm tăng bộ nhớ và CPU, gây ảnh hưởng chi phí serverless.

**Dùng allow-list.** Chỉ ánh xạ các trường được hỗ trợ. Tránh tự động bind toàn bộ JSON vào entity database có các trường nhạy cảm như role, ownerId hoặc balance. Nếu client có thể gửi những trường này, lỗi mass assignment có thể cho phép sửa dữ liệu ngoài ý muốn.

**Không tin giá trị do client tính.** Giá, tổng tiền, quyền sở hữu, trạng thái thanh toán và vai trò người dùng phải được xác định hoặc xác minh từ nguồn tin cậy phía server.

**Tách validation khỏi sanitization.** Validation xác định dữ liệu có đáp ứng hợp đồng không. Sanitization hoặc encoding xử lý cách dữ liệu được sử dụng ở ngữ cảnh cụ thể. Không nên cố loại bỏ mọi ký tự đặc biệt bằng một bộ lọc chung; hãy dùng parameterized query cho SQL và encode đầu ra theo ngữ cảnh HTML, URL hoặc log.

**Kiểm tra quyền riêng.** Một ID đúng định dạng không chứng minh caller có quyền truy cập đối tượng đó. Luôn kiểm tra tenant, owner hoặc policy trước khi đọc hay thay đổi dữ liệu.

**Bảo vệ dữ liệu trong log.** Log mã lỗi, event ID, correlation ID và tên trường vi phạm khi cần. Tránh log token, mật khẩu, dữ liệu thanh toán hoặc toàn bộ payload chứa thông tin cá nhân. Với message bị đưa vào DLQ, giới hạn quyền truy cập và thời gian lưu giữ.

## 9. Quản lý phiên bản schema và kiểm thử hợp đồng

Schema là một phần của giao diện giữa các thành phần, nên cần được quản lý như mã nguồn.

### Phiên bản hóa

Có thể đặt version trong đường dẫn schema, tên event type hoặc metadata rõ ràng. Ví dụ:

- https://example.com/schemas/create-order-v1.json
- com.example.orders.created.v1

Chọn một quy tắc nhất quán và ghi rõ version áp dụng cho payload nào. Không chỉ đổi tên file mà không có cách để consumer xác định version từ dữ liệu nhận được.

### Thay đổi tương thích

| Thay đổi | Rủi ro tương thích | Hướng xử lý |
|---|---|---|
| Thêm trường tùy chọn | Thường thấp nếu consumer bỏ qua trường lạ | Kiểm thử consumer cũ với payload mới |
| Thêm trường bắt buộc | Cao với producer cũ | Chỉ áp dụng trong version mới hoặc sau giai đoạn chuyển đổi |
| Xóa trường | Cao với consumer đang dùng trường | Ngừng dùng trước, theo dõi, rồi mới xóa ở version mới |
| Đổi kiểu dữ liệu | Cao | Tạo trường hoặc version mới và chuyển đổi có kế hoạch |
| Thu hẹp miền giá trị | Có thể làm payload cũ không hợp lệ | Kiểm tra dữ liệu thực tế và consumer trước khi áp dụng |
| Thêm giá trị enum | Có thể làm consumer xử lý không đầy đủ | Consumer cần có nhánh cho giá trị chưa biết |
| Đổi ý nghĩa trường | Rất cao dù kiểu dữ liệu không đổi | Dùng trường hoặc event type mới |

### Những kiểm thử nên có

- Payload hợp lệ tối thiểu và payload đầy đủ.
- Thiếu từng trường bắt buộc.
- Kiểu sai, null, chuỗi rỗng, số âm và giá trị vượt giới hạn.
- Mảng rỗng, quá nhiều phần tử hoặc phần tử sai cấu trúc.
- Trường không biết theo chính sách của schema.
- Thời gian sai định dạng, sai offset hoặc không có múi giờ khi hợp đồng yêu cầu.
- Event version cũ và mới.
- Message được gửi lặp lại.
- Consumer hiện tại xử lý payload được producer phiên bản kế tiếp phát ra.

Có thể chạy schema validation trong CI để phát hiện thay đổi không tương thích trước khi triển khai. Với hệ thống có nhiều producer và consumer, kiểm thử contract giữa các bên giúp phát hiện sớm trường hợp một phía thay đổi mà phía còn lại chưa sẵn sàng.

## 10. Quy trình thiết kế và triển khai thực tế

Khi thêm một HTTP function hoặc event consumer mới, có thể làm theo trình tự sau:

1. Xác định ai tạo payload và ai tiêu thụ payload.
2. Viết ví dụ JSON hợp lệ, bao gồm trường bắt buộc, tùy chọn và trường lồng nhau.
3. Định nghĩa JSON Schema: type, required, giới hạn, enum, format và chính sách trường chưa biết.
4. Mô tả ngữ nghĩa: đơn vị, múi giờ, ID, ý nghĩa null và các giá trị dẫn xuất.
5. Ánh xạ schema sang DTO Java và khai báo Bean Validation.
6. Bổ sung kiểm tra nghiệp vụ, quyền truy cập và idempotency ở đúng tầng.
7. Quy định cách phản hồi HTTP hoặc xử lý message lỗi, retry và DLQ.
8. Viết kiểm thử payload hợp lệ, không hợp lệ và kiểm thử tương thích phiên bản.
9. Theo dõi lỗi validation theo event type, producer và schema version để tìm thành phần đang gửi sai hợp đồng.

Với serverless, validation nên diễn ra sớm tại ranh giới nhận dữ liệu để tránh gọi database hoặc dịch vụ bên ngoài cho payload chắc chắn không hợp lệ. Tuy nhiên, không nên tải toàn bộ schema registry hoặc khởi tạo validator nặng cho mỗi invocation. Có thể nạp schema và tạo validator một lần trong vòng đời môi trường thực thi nếu thư viện an toàn khi dùng đồng thời và có cơ chế cập nhật phù hợp.

## 11. Ghi nhớ

Một payload JSON hợp lệ về cú pháp chưa chắc hợp lệ với ứng dụng. Hãy mô tả cấu trúc và giới hạn bằng JSON Schema, ánh xạ sang DTO Java có validation, rồi kiểm tra tiếp quy tắc nghiệp vụ và quyền truy cập.

Với HTTP request, trả lỗi nhất quán để client biết cách sửa dữ liệu. Với message và event, phân biệt lỗi tạm thời với lỗi hợp đồng để quyết định retry hay đưa vào DLQ. Quản lý phiên bản và kiểm thử tương thích để producer, consumer có thể thay đổi độc lập mà không làm hỏng luồng xử lý.

Một hợp đồng dữ liệu rõ ràng giúp function xử lý đầu vào có thể dự đoán, giảm lỗi khi tích hợp và kiểm soát tốt hơn chi phí phát sinh từ retry, payload bất thường hoặc xử lý không cần thiết.

