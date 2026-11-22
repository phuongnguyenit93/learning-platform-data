# Tiền điều kiện và cách báo đầu vào không hợp lệ

Một API đáng tin cậy cần nói rõ **điều gì phải đúng trước khi thao tác được thực hiện**. Nếu phía gọi gửi số lượng âm, bỏ trống định danh hoặc dùng kiểu dữ liệu sai, API cần từ chối với thông báo nhất quán. Nếu yêu cầu có cấu trúc hợp lệ nhưng đơn đã hủy, vấn đề lại nằm ở **trạng thái nghiệp vụ**, không phải cú pháp đầu vào. Cách phân biệt và phản hồi những trường hợp này là một phần của **hợp đồng API**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một hợp đồng API rõ ràng giúp phía gọi biết cách sử dụng, phía cung cấp biết mình phải bảo đảm gì, và nhóm phát triển có cơ sở để kiểm thử khi yêu cầu thay đổi.

Bài này tập trung vào **tiền điều kiện (preconditions)**, cách kiểm tra chúng tại đúng ranh giới, cách biểu diễn đầu vào không hợp lệ và các đánh đổi trong thiết kế phản hồi lỗi.

## 1. Tiền điều kiện là gì?

**Tiền điều kiện** là những điều phải được thỏa mãn **trước khi một thao tác có thể được thực hiện theo hợp đồng**.

Ví dụ, API tạo đơn hàng yêu cầu:

- Mã sản phẩm phải có mặt và đúng định dạng.
- Số lượng phải là số nguyên từ 1 đến 100.
- Người yêu cầu phải có danh tính được xác thực và đủ quyền.
- Sản phẩm phải còn được phép bán.
- Nếu API yêu cầu một phiên bản tài nguyên cụ thể, phiên bản đó phải khớp.

Các điều kiện trên cùng ảnh hưởng việc thực hiện thao tác, nhưng **thuộc các nhóm khác nhau**. Phân nhóm giúp trả kết quả chính xác:

| Nhóm tiền điều kiện | Câu hỏi | Ví dụ | Khi không đáp ứng |
| --- | --- | --- | --- |
| **Hợp đồng dữ liệu** | Request có hình dạng, kiểu và miền giá trị hợp lệ không? | Số lượng từ 1 đến 100; mã không được trống. | Báo đầu vào không hợp lệ để phía gọi sửa. |
| **Xác thực và phân quyền** | Ai đang gọi, và có được phép làm việc này không? | Người dùng được quyền tạo đơn cho tài khoản tương ứng. | Từ chối theo hợp đồng bảo mật. |
| **Tiền điều kiện nghiệp vụ** | Trạng thái hiện tại có cho phép thao tác không? | Sản phẩm đang bán; hạn mức mua còn hiệu lực. | Trả kết quả từ chối hoặc xung đột nghiệp vụ. |
| **Điều kiện đồng thời / phiên bản** | Dữ liệu có còn đúng phiên bản mà phía gọi dựa vào không? | Header If-Match phải khớp ETag hiện tại. | Từ chối cập nhật theo hợp đồng điều kiện. |
| **Khả năng của phụ thuộc** | Hệ thống có đủ thông tin và năng lực để thực hiện không? | Kho dữ liệu trả được kết quả đáng tin cậy. | Báo lỗi kỹ thuật/phụ thuộc nếu không thể xác nhận. |

Trong tư duy **Design by Contract**, tiền điều kiện mô tả yêu cầu dành cho phía gọi; **hậu điều kiện (postcondition)** mô tả điều phía cung cấp cam kết sau khi thao tác thành công; **bất biến (invariant)** là điều phải tiếp tục đúng trong các trạng thái liên quan.

Ví dụ:

- Tiền điều kiện: số lượng đặt mua lớn hơn 0.
- Hậu điều kiện khi tạo đơn thành công: trả về định danh đơn được tạo theo hợp đồng.
- Bất biến: dữ liệu đơn không được mâu thuẫn với quy tắc trạng thái của hệ thống.

Đừng đồng nhất mọi tiền điều kiện với một câu lệnh if. Quy tắc có thể liên quan dữ liệu, quyền, trạng thái, giao dịch hoặc một ranh giới giữa các dịch vụ.

## 2. Ví dụ xuyên suốt: hợp đồng tạo đơn hàng

Giả sử API giả định có endpoint:

~~~http
POST /orders
Content-Type: application/json
Authorization: Bearer <access-token>
~~~

Một request hợp lệ:

~~~json
{
  "productCode": "SKU-42",
  "quantity": 3,
  "note": "Giao trong giờ hành chính"
}
~~~

Để tránh mơ hồ, **hợp đồng ví dụ** quy định:

| Trường | Bắt buộc? | Điều kiện hợp lệ | Ví dụ không hợp lệ |
| --- | --- | --- | --- |
| productCode | Có | Chuỗi dài 3–20 ký tự, chỉ gồm chữ cái in hoa A–Z, chữ số 0–9 và dấu gạch ngang. | null, chuỗi trống, "sku 42". |
| quantity | Có | Số nguyên từ **1 đến 100**, gồm cả hai đầu mút. | null, 0, -2, 101, chuỗi "three". |
| note | Không | Có thể vắng mặt hoặc null; nếu có chuỗi, dài tối đa 200 **Unicode code points**. | Chuỗi dài hơn 200 code points. |

Các quy tắc bổ sung về hoạt động:

1. Người gọi cần được xác thực và có quyền theo hợp đồng hệ thống.
2. Sản phẩm đang được bán và có thể đáp ứng số lượng yêu cầu.
3. Một request hợp lệ về dữ liệu **chưa có nghĩa** có thể tạo đơn thành công: tồn kho và trạng thái có thể thay đổi.
4. Tạo đơn là thao tác có tác dụng phụ. Hệ thống cần chính sách phù hợp khi client gửi lặp hoặc mất phản hồi.

Các giá trị **3–20**, **1–100** và **200** chỉ là quy tắc giả định cho bài học, không phải quy chuẩn bắt buộc của mọi API.

## 3. Phân biệt không parse được, không hợp lệ và bị từ chối nghiệp vụ

Xét các request:

**Trường hợp A — JSON không thể phân tích:**

~~~json
{"productCode": "SKU-42", "quantity":
~~~

Đây là lỗi cú pháp dữ liệu. Bộ phân tích JSON chưa thể tạo đối tượng request hợp lệ để chuyển sang các bước xác thực trường.

**Trường hợp B — JSON hợp lệ nhưng sai kiểu:**

~~~json
{"productCode": "SKU-42", "quantity": "three"}
~~~

Nếu hợp đồng chỉ chấp nhận số nguyên, tầng giải mã/ánh xạ kiểu sẽ từ chối. Không thể giả định mã nghiệp vụ đã nhận được một đối tượng có quantity là số nguyên.

**Trường hợp C — JSON và kiểu dữ liệu hợp lệ nhưng sai miền giá trị:**

~~~json
{"productCode": "sku 42", "quantity": -2}
~~~

Dữ liệu có thể được ánh xạ thành một đối tượng, nhưng **vi phạm tiền điều kiện đã công bố**.

**Trường hợp D — request hợp lệ, trạng thái nghiệp vụ không cho phép:**

~~~json
{"productCode": "SKU-42", "quantity": 3}
~~~

Nếu sản phẩm đã ngừng bán hoặc kho không đáp ứng, việc từ chối phát sinh từ **trạng thái hoặc quy tắc nghiệp vụ**, không phải từ một trường JSON có kiểu sai.

**Trường hợp E — request hợp lệ, phụ thuộc bị timeout:** Kho dữ liệu không trả kết quả. Chưa có căn cứ để kết luận “hết hàng”; hệ thống cần giữ riêng tình trạng lỗi hạ tầng.

Điều quan trọng là **không biến một nhóm lỗi thành nhóm khác** chỉ vì chúng đều khiến yêu cầu chưa thành công.

## 4. Kiểm tra tiền điều kiện tại đúng ranh giới

Một luồng xử lý dễ hiểu có thể mô tả như sau:

~~~mermaid
flowchart TD
    A["Nhận request"] --> B{"Xác thực và quyền theo hợp đồng?"}
    B -- "Không" --> C["Từ chối theo chính sách bảo mật"]
    B -- "Có" --> D{"Parse và ánh xạ request được?"}
    D -- "Không" --> E["Báo lỗi định dạng / kiểu"]
    D -- "Có" --> F{"Các trường đáp ứng tiền điều kiện?"}
    F -- "Không" --> G["Báo lỗi validation"]
    F -- "Có" --> H{"Trạng thái nghiệp vụ cho phép?"}
    H -- "Không" --> I["Báo từ chối nghiệp vụ"]
    H -- "Có" --> J["Thực hiện thao tác an toàn"]
    J --> K["Trả kết quả theo hợp đồng"]
~~~

Sơ đồ chỉ diễn tả **những trách nhiệm cần có**; thứ tự thực thi thực tế còn phụ thuộc middleware, framework và chính sách bảo mật. Với một số API, kiểm tra cấu trúc request diễn ra trước một phần kiểm tra quyền. Cần tránh để cách sắp xếp đó tiết lộ dữ liệu mà người gọi không được biết.

**Những ranh giới thường gặp:**

- **HTTP boundary:** content type, JSON hợp lệ, giới hạn kích thước request, kiểu dữ liệu và lỗi binding.
- **Request validation:** trường bắt buộc, độ dài, miền số, định dạng, tính nhất quán giữa các trường.
- **Authorization:** danh tính và quyền dựa trên nguồn đáng tin cậy; không lấy vai trò từ payload do client tự khai.
- **Domain/application service:** quy tắc trạng thái, hạn mức, tính hợp lệ của việc chuyển trạng thái.
- **Persistence/transaction:** các bất biến phải đúng khi cập nhật đồng thời, kể cả khi dữ liệu đã thay đổi sau bước đọc.

Đầu vào được xác thực ở Controller không có nghĩa các bất biến nghiệp vụ có thể bỏ qua. Một service có thể được gọi từ HTTP, job hoặc message consumer; ranh giới quan trọng phải được bảo vệ ở nơi sở hữu quy tắc.

## 5. Ví dụ Java 17: biểu diễn lỗi validation rõ ràng

Ví dụ dưới đây không phụ thuộc framework HTTP. Nó nhận một **đối tượng đã được giải mã thành công** và trả danh sách các vi phạm. Để biên dịch riêng, đặt mỗi kiểu public vào tệp Java tương ứng.

### Kiểu dữ liệu request và vi phạm

~~~java
public record CreateOrderRequest(
        String productCode,
        Integer quantity,
        String note) {
}
~~~

Chọn **Integer** thay vì **int** để sau khi ánh xạ JSON có thể phân biệt trường quantity thiếu/null với số **0**. Tầng binding phải có hợp đồng phù hợp để giữ sự khác biệt này.

~~~java
public record FieldViolation(
        String field,
        String code,
        String message) {
}
~~~

Mỗi vi phạm chứa:

- **field:** đường dẫn tương đối tới trường có lỗi.
- **code:** mã máy ổn định để client xử lý.
- **message:** diễn giải dễ hiểu cho người phát triển hoặc người dùng.

### Validator không gây tác dụng phụ

~~~java
import java.util.ArrayList;
import java.util.List;

public final class CreateOrderValidator {
    private CreateOrderValidator() {
    }

    public static List<FieldViolation> validate(CreateOrderRequest request) {
        if (request == null) {
            return List.of(new FieldViolation(
                    "$", "REQUIRED", "Request body is required"));
        }

        List<FieldViolation> errors = new ArrayList<>();

        String code = request.productCode();
        if (code == null || code.isBlank()) {
            errors.add(new FieldViolation(
                    "productCode", "REQUIRED",
                    "Product code is required"));
        } else if (!code.matches("[A-Z0-9-]{3,20}")) {
            errors.add(new FieldViolation(
                    "productCode", "INVALID_FORMAT",
                    "Use 3–20 uppercase letters, digits or hyphens"));
        }

        Integer quantity = request.quantity();
        if (quantity == null) {
            errors.add(new FieldViolation(
                    "quantity", "REQUIRED",
                    "Quantity is required"));
        } else if (quantity < 1 || quantity > 100) {
            errors.add(new FieldViolation(
                    "quantity", "OUT_OF_RANGE",
                    "Quantity must be between 1 and 100"));
        }

        String note = request.note();
        if (note != null && note.codePointCount(0, note.length()) > 200) {
            errors.add(new FieldViolation(
                    "note", "TOO_LONG",
                    "Note must not exceed 200 Unicode code points"));
        }

        return List.copyOf(errors);
    }
}
~~~

Cách viết này có những thuộc tính cần chú ý:

1. **Không truy vấn CSDL hay gửi thông điệp** trong validation dữ liệu; nó chỉ kiểm tra các quy tắc xác định từ request.
2. **Không dừng ở lỗi đầu tiên** trong những trường hợp có thể trả nhiều lỗi cùng lúc, giúp phía gọi sửa một lượt.
3. **Phân biệt mã lỗi** REQUIRED, INVALID_FORMAT, OUT_OF_RANGE và TOO_LONG; client không cần phân tích câu chữ trong message.
4. **Không tự động sửa dữ liệu**: mã “sku-42” bị từ chối thay vì âm thầm viết hoa. Nếu hợp đồng muốn chuẩn hóa, phải mô tả rõ và kiểm thử riêng.
5. **Không giả định UTF-16 length là số ký tự nhìn thấy**: ở đây hợp đồng quy định code points và code dùng codePointCount. Unicode grapheme cluster là một khái niệm khác; nếu sản phẩm tính theo ký tự hiển thị cần quy tắc khác.

**Giới hạn ví dụ:** Validator chỉ chạy khi dữ liệu đã giải mã thành CreateOrderRequest. Lỗi JSON hỏng hoặc quantity là chuỗi “three” cần được bắt và ánh xạ ở tầng HTTP/binding. Phần kiểm tra quyền, tồn kho và giao dịch cũng nằm ngoài lớp này.

## 6. Đầu vào không hợp lệ cần được báo như thế nào?

Một phản hồi tốt phải giúp phía gọi **xác định nguyên nhân và sửa đúng chỗ**, đồng thời không tiết lộ chi tiết nội bộ.

Ví dụ sau dùng HTTP **400 Bad Request** cho các lỗi validation trường theo hợp đồng giả định:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "Yêu cầu chứa trường không hợp lệ.",
  "requestId": "req-8f1a",
  "errors": [
    {
      "field": "productCode",
      "code": "INVALID_FORMAT",
      "message": "Mã sản phẩm phải dài 3–20 ký tự và chỉ có A–Z, 0–9 hoặc dấu gạch ngang."
    },
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "Số lượng phải từ 1 đến 100."
    }
  ]
}
~~~

Ở đây:

- **HTTP status** cho biết nhóm kết quả ở tầng giao thức.
- **code** trên cùng cho biết loại vấn đề ổn định.
- **errors[]** cho phép báo lỗi từng trường, kể cả nhiều lỗi.
- **requestId** hỗ trợ đối chiếu với log và trace phía máy chủ.
- **message** đủ rõ cho người dùng nhưng không chứa stack trace, SQL hoặc cấu hình nội bộ.

Không phải API nào cũng cần đúng cấu trúc trên. Có thể dùng định dạng **Problem Details for HTTP APIs**, với content type **application/problem+json**, hoặc một schema lỗi riêng đã được công bố. Quan trọng là **nhất quán trong toàn bộ hợp đồng**, đặc biệt đối với mã lỗi mà client xử lý tự động.

### Vì sao mã máy và thông điệp cần tách nhau?

Giả sử client muốn hiển thị hướng dẫn riêng cho trường quantity:

- Không nên viết logic kiểu “nếu message chứa chuỗi *must be between* thì đánh dấu ô số lượng”.
- Nên kiểm tra **field = quantity** và **code = OUT_OF_RANGE**.
- Message có thể được dịch sang tiếng Việt, tiếng Anh hoặc điều chỉnh câu chữ mà không làm hỏng logic phía gọi.

Một mã máy được công bố trong API là một phần của hợp đồng; không nên đổi tùy ý chỉ vì chỉnh văn bản.

## 7. Chọn HTTP status theo bản chất thất bại

Bảng sau là **hướng dẫn thiết kế thường gặp**, không phải quy tắc bắt buộc một-một cho mọi API:

| Tình huống | HTTP status thường phù hợp | Điểm cần lưu ý |
| --- | --- | --- |
| JSON hỏng, thiếu trường bắt buộc, dữ liệu vi phạm hợp đồng request | **400 Bad Request** | Cung cấp lỗi parse hoặc trường cụ thể. |
| Nội dung đúng cú pháp và kiểu nhưng không thể xử lý theo ngữ nghĩa đã quy định | **422 Unprocessable Content** | Có thể chọn cho nhóm validation ngữ nghĩa nếu API định nghĩa nhất quán. |
| Hành động xung đột với trạng thái hiện tại, ví dụ cập nhật đơn đã hủy | **409 Conflict** | Nêu quy tắc/trạng thái gây xung đột. |
| Chưa có thông tin xác thực hợp lệ | **401 Unauthorized** | Tuân thủ cơ chế và yêu cầu header xác thực phù hợp. |
| Đã xác thực nhưng không đủ quyền | **403 Forbidden** | Tránh lộ thông tin tài nguyên nhạy cảm. |
| Tài nguyên không tìm thấy theo hợp đồng | **404 Not Found** | Một số chính sách bảo mật có thể chọn phản hồi 404 để tránh tiết lộ sự tồn tại. |
| Payload quá lớn so với giới hạn | **413 Content Too Large** | Giới hạn kích thước cần được công bố hoặc có cách phản hồi phù hợp. |
| Media type không được hỗ trợ | **415 Unsupported Media Type** | Ví dụ endpoint chỉ nhận JSON nhưng client gửi định dạng khác. |
| Điều kiện HTTP như If-Match không khớp | **412 Precondition Failed** | Liên quan conditional request, khác với lỗi validation trường JSON. |
| Máy chủ yêu cầu request phải có điều kiện trước khi xử lý | **428 Precondition Required** | Dùng khi hợp đồng yêu cầu điều kiện HTTP, chẳng hạn bảo vệ cập nhật đồng thời. |
| Phụ thuộc tạm thời không sẵn sàng | **503 Service Unavailable** | Không tự báo thành lỗi đầu vào. |
| Lỗi chưa được xử lý phía máy chủ | **500 Internal Server Error** | Trả thông báo chung, giữ chi tiết kỹ thuật ở log. |

Đối với những tiền điều kiện được gọi là **HTTP conditional request preconditions** như If-Match, 412 có ý nghĩa riêng. Không dùng 412 cho mọi trường bắt buộc bị thiếu chỉ vì chúng cũng là “tiền điều kiện” theo nghĩa nghiệp vụ.

**400 hay 422?** Một API có thể chọn 400 cho toàn bộ lỗi trường đầu vào hoặc phân biệt 400 (cú pháp/kiểu) với 422 (ngữ nghĩa hợp lệ về cú pháp nhưng không thể xử lý). Hai lựa chọn đều cần **được tài liệu hóa và thực hiện nhất quán**. Cần tránh việc cùng một lỗi thiếu quantity trả 400 ở endpoint này nhưng 422 ở endpoint khác mà không có chủ đích thiết kế.

## 8. Khi nào nên trả một lỗi, khi nào trả nhiều lỗi?

Hai cách phổ biến:

| Cách xử lý | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Fail fast**: dừng khi gặp lỗi đầu tiên | Đơn giản, tránh tiếp tục kiểm tra tốn kém hoặc không an toàn. | Người dùng có thể phải gửi lại nhiều lần mới sửa hết trường sai. |
| **Collect errors**: tích lũy nhiều vi phạm | Tiện cho biểu mẫu, cho phép sửa nhiều trường cùng lúc. | Phải kiểm soát thứ tự, độ phức tạp và số lượng lỗi; không phải kiểm tra nào cũng an toàn khi tiếp tục. |

Ví dụ productCode và quantity độc lập: trả cả hai lỗi là hợp lý. Nhưng nếu quantity không thể parse thành số, không được cứ tiếp tục dùng giá trị đó để tính giá hoặc truy cập kho.

Một chính sách có thể là:

1. Dừng sớm khi request không thể parse, vượt giới hạn hoặc không đủ quyền.
2. Với những trường đã được parse thành công, thu thập các lỗi dữ liệu độc lập.
3. Chỉ sau khi hợp đồng dữ liệu hợp lệ mới chạy quy tắc có tác dụng phụ hoặc cần truy cập phụ thuộc.
4. Đặt giới hạn số lượng vi phạm trả về để tránh phản hồi quá lớn khi payload chứa hàng nghìn mục.

Cần giữ **thứ tự lỗi ổn định** nếu client phụ thuộc vào nó; tốt hơn, client nên dựa vào field/code thay vì vị trí của phần tử trong mảng.

## 9. Những vấn đề dễ bị bỏ sót khi thiết kế validation

### Trường thiếu, null và giá trị mặc định

Ba payload sau có thể có ý nghĩa khác nhau:

~~~json
{}
~~~

~~~json
{"quantity": null}
~~~

~~~json
{"quantity": 0}
~~~

Nếu quantity là bắt buộc và phải từ 1 đến 100, cả ba trường hợp đều không hợp lệ, nhưng **nguyên nhân** khác nhau. Tùy framework, thiếu trường và null có thể được ánh xạ giống nhau; cần xác định liệu hợp đồng có cần phân biệt hay không.

Không dùng kiểu nguyên thủy int rồi mặc nhiên coi 0 là giá trị người dùng đã gửi nếu tầng binding đã tự gán mặc định 0 cho trường bị thiếu mà ứng dụng cần phân biệt.

### Chuỗi trống, khoảng trắng và chuẩn hóa

Các giá trị "", "   ", "SKU-42" và "sku-42" không nhất thiết tương đương. Nếu chấp nhận biến thể viết thường hoặc khoảng trắng hai đầu, quy tắc chuẩn hóa phải được công bố và thực hiện nhất quán.

Việc tự động cắt khoảng trắng, đổi kiểu hoặc chuyển dấu có thể làm thay đổi định danh. Đừng chỉ “sửa cho qua validation” mà không xét ngữ nghĩa dữ liệu.

### Validation giữa nhiều trường

Một hợp đồng có thể quy định: nếu deliveryMethod là HOME_DELIVERY thì deliveryAddress phải có mặt; nếu PICKUP thì địa chỉ giao hàng không bắt buộc. Đây là ràng buộc liên trường, không thể chỉ dùng mỗi annotation kiểm tra một field.

Có thể diễn đạt bằng quy tắc:

~~~text
if deliveryMethod == HOME_DELIVERY:
    deliveryAddress is required
else if deliveryMethod == PICKUP:
    pickupLocationId is required
~~~

Tránh để cùng quy tắc bị sao chép khác nhau ở Controller, Service và lớp persistence. Mỗi ranh giới có thể kiểm tra lại điều cần bảo vệ, nhưng **đặc tả và nguồn sở hữu chính** phải rõ.

### Giới hạn tài nguyên

Kiểm tra độ dài một field không thay thế giới hạn tổng kích thước request, độ sâu JSON hoặc số phần tử mảng. Một request chứa nhiều triệu phần tử có thể gây áp lực bộ nhớ trước khi validator được gọi. Ranh giới HTTP/parser cần giới hạn tài nguyên phù hợp để tránh quá tải.

## 10. Tiền điều kiện phải được thực thi trước tác dụng phụ

Xét thứ tự sai:

~~~java
// SAI: ghi dữ liệu trước rồi mới kiểm tra tiền điều kiện.
orderRepository.create(request);

if (request.quantity() == null || request.quantity() <= 0) {
    throw new IllegalArgumentException("Invalid quantity");
}
~~~

Nếu cập nhật đã được commit, việc ném ngoại lệ không tự hoàn tác dữ liệu. Với thao tác tạo đơn, quy trình đúng về mặt ý nghĩa phải là:

~~~text
1. Giải mã request
2. Kiểm tra hợp đồng dữ liệu
3. Xác nhận quyền thực hiện
4. Kiểm tra quy tắc nghiệp vụ ở ranh giới phù hợp
5. Ghi dữ liệu theo transaction/bất biến
6. Trả kết quả hoặc lỗi rõ ràng
~~~

Một đoạn minh họa ở tầng nhận request:

~~~java
List<FieldViolation> errors = CreateOrderValidator.validate(request);

if (!errors.isEmpty()) {
    // Controller chuyển danh sách lỗi thành HTTP 400 theo schema API.
    throw new InvalidRequestException(errors);
}

// Từ đây có thể chuyển request cho use case.
// Các quy tắc trạng thái và giao dịch vẫn được xử lý ở tầng nghiệp vụ.
return orderService.create(request);
~~~

Ở đoạn này, **InvalidRequestException** và **orderService** là các thành phần giả định của ứng dụng; ví dụ tập trung vào thứ tự trách nhiệm, không phải một HTTP framework cụ thể.

### Kiểm tra trước chưa đủ khi có đồng thời

Giả sử tồn kho chỉ còn 1 sản phẩm và hai request hợp lệ cùng lúc yêu cầu mua 1. Cả hai có thể đọc thấy số lượng còn 1. Vì thế:

- Validation request bảo đảm quantity hợp lệ.
- Kiểm tra tồn kho trước khi ghi hỗ trợ thông báo sớm.
- **Cập nhật nguyên tử hoặc transaction thích hợp** mới bảo vệ bất biến không bán vượt tồn kho trong trường hợp cạnh tranh.

Như vậy, không nên gọi mọi xung đột tồn kho là “đầu vào không hợp lệ”: nó có thể xuất hiện dù payload hoàn toàn đúng.

## 11. Bảo mật trong cách báo lỗi

Thông báo cần đủ thông tin để sửa yêu cầu, nhưng có thể gây rủi ro nếu phơi bày dữ liệu không thuộc quyền truy cập.

Ví dụ, với API truy vấn đơn hàng, phản hồi cho người không có quyền không nên vô tình xác nhận “đơn này thuộc về khách hàng X”. Hệ thống có thể chọn phản hồi tổng quát theo chính sách bảo mật.

Một số nguyên tắc thực hành:

- **Không trả stack trace**, đường dẫn nội bộ, truy vấn SQL hoặc thông tin đăng nhập trong response.
- **Không echo toàn bộ dữ liệu đầu vào nhạy cảm** trong lỗi: mật khẩu, token, số thẻ hoặc nội dung riêng tư.
- **Gắn request ID** để điều tra mà không cần lộ chi tiết kỹ thuật ra ngoài.
- **Kiểm tra quyền ở ranh giới tin cậy** và hạn chế thông tin lỗi từ những tài nguyên mà người gọi không được xem.
- **Giới hạn kích thước lỗi** và cẩn trọng khi logging dữ liệu do client cung cấp.
- **Giữ mã lỗi ổn định**; thông điệp mô tả có thể thay đổi nhưng không nên làm client hỏng.

Một số API cần trả một lỗi tổng quát dù hệ thống nội bộ ghi nhận nguyên nhân cụ thể. Đó là quyết định thiết kế có cơ sở khi bảo vệ quyền riêng tư hoặc ngăn tiết lộ tài nguyên.

## 12. Kiểm thử hợp đồng tiền điều kiện

Không chỉ kiểm tra rằng validator “có chạy”. Kiểm thử phải chứng minh **đường đầu vào hợp lệ được chấp nhận** và **đường không hợp lệ bị từ chối với đúng thông tin**.

Ví dụ JUnit 5 cho validator Java ở phần 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class CreateOrderValidatorTest {
    @Test
    void reportsIndependentFieldErrors() {
        var request = new CreateOrderRequest("sku 42", -2, null);

        List<FieldViolation> errors = CreateOrderValidator.validate(request);

        assertEquals(List.of("productCode", "quantity"),
                errors.stream().map(FieldViolation::field).toList());
        assertEquals("INVALID_FORMAT", errors.get(0).code());
        assertEquals("OUT_OF_RANGE", errors.get(1).code());
    }

    @Test
    void acceptsInclusiveQuantityBoundaries() {
        assertTrue(CreateOrderValidator.validate(
                new CreateOrderRequest("SKU-42", 1, null)).isEmpty());

        assertTrue(CreateOrderValidator.validate(
                new CreateOrderRequest("SKU-42", 100, "")).isEmpty());
    }

    @Test
    void rejectsQuantityOutsideBoundaries() {
        assertEquals("OUT_OF_RANGE",
                CreateOrderValidator.validate(
                        new CreateOrderRequest("SKU-42", 0, null))
                        .get(0).code());

        assertEquals("OUT_OF_RANGE",
                CreateOrderValidator.validate(
                        new CreateOrderRequest("SKU-42", 101, null))
                        .get(0).code());
    }

    @Test
    void missingQuantityIsDifferentFromOutOfRange() {
        var errors = CreateOrderValidator.validate(
                new CreateOrderRequest("SKU-42", null, null));

        assertEquals("REQUIRED", errors.get(0).code());
        assertEquals("quantity", errors.get(0).field());
    }

    @Test
    void rejectsOversizedOptionalNote() {
        var errors = CreateOrderValidator.validate(
                new CreateOrderRequest("SKU-42", 3, "x".repeat(201)));

        assertEquals("note", errors.get(0).field());
        assertEquals("TOO_LONG", errors.get(0).code());
    }

    @Test
    void nullBodyIsRejected() {
        var errors = CreateOrderValidator.validate(null);

        assertEquals("$", errors.get(0).field());
        assertEquals("REQUIRED", errors.get(0).code());
    }
}
~~~

Các test này xác nhận logic Java thuần. **Chúng chưa chứng minh hợp đồng HTTP**, vì parse, content type, authentication và ánh xạ lỗi nằm ở những lớp khác.

### Những ca cần kiểm tra ở mức API

| Trường hợp | Điều cần xác minh |
| --- | --- |
| JSON bị cắt giữa chừng | Từ chối ở tầng parse, không chạy use case tạo đơn. |
| quantity là chuỗi thay vì số nguyên | Phản hồi lỗi kiểu phù hợp, không ép kiểu âm thầm nếu hợp đồng không cho phép. |
| Thiếu hoặc null productCode | Mã lỗi/field đúng; không ghi đơn. |
| quantity = 0, 1, 100, 101 | Phân biệt chính xác ranh giới. |
| Không đủ quyền | Phản hồi theo chính sách bảo mật, không lộ thông tin nghiệp vụ. |
| Sản phẩm ngừng bán | Phản hồi từ chối nghiệp vụ phù hợp, không báo lỗi cú pháp request. |
| CSDL timeout | Phản hồi lỗi hệ thống/phụ thuộc, không kết luận hết hàng. |
| Client gửi lại request tạo đơn | Xử lý theo chính sách chống lặp đã công bố. |
| Content-Type không hỗ trợ | Phản hồi giao thức phù hợp, không gọi nghiệp vụ. |
| Request quá lớn | Chặn theo giới hạn tài nguyên và trả lỗi phù hợp. |

Với hành vi có tác dụng phụ, kiểm tra cả **số lần gọi** và **trạng thái dữ liệu sau thất bại**, không chỉ kiểm tra status code. Nếu có concurrency, cần test tích hợp phù hợp để bảo vệ các bất biến lưu trữ.

## 13. Thay đổi tiền điều kiện là thay đổi hợp đồng

Giả sử phiên bản đầu cho phép quantity từ 1 đến 100. Sau đó sản phẩm muốn giới hạn tối đa 20.

Đây không chỉ là sửa hằng số trong validator. Những client trước đây gửi quantity = 50 sẽ bị từ chối. Vì vậy, **thắt chặt miền đầu vào có thể là thay đổi không tương thích ngược**.

Các thay đổi đáng cân nhắc:

| Thay đổi | Tác động có thể có |
| --- | --- |
| Thêm trường **bắt buộc** | Client cũ không gửi trường đó có thể bị lỗi. |
| Thêm trường **không bắt buộc** | Thường dễ tương thích hơn, nhưng cần quy tắc mặc định rõ. |
| Giảm giới hạn quantity 100 xuống 20 | Request từng hợp lệ trở nên không hợp lệ. |
| Đổi mã lỗi INVALID_FORMAT thành BAD_CODE | Client dựa vào mã cũ có thể xử lý sai. |
| Đổi 400 thành 422 cho cùng một trường | Client có logic theo HTTP status cần cập nhật. |
| Đổi ý nghĩa null và trường vắng mặt | Có thể làm sai logic vá một phần dữ liệu hoặc dùng mặc định. |

Khi thay đổi, cần xem **OpenAPI/JSON Schema hoặc tài liệu hợp đồng**, ví dụ request/response, test của bên tiêu thụ và chính sách versioning/chuyển đổi phù hợp. Không được giả định mọi client đều sẽ cập nhật đồng thời.

**API dễ bảo trì là API có điều kiện rõ và thay đổi có chủ đích**, để bên cung cấp và bên gọi biết lúc nào cần phối hợp.

## 14. Checklist review tiền điều kiện và phản hồi lỗi

Trước khi phát hành một endpoint, hãy tự kiểm tra:

1. **Hợp đồng dữ liệu có tường minh không?** Kiểu, required/optional, null, miền giá trị, độ dài và quy tắc liên trường đã được mô tả?
2. **Có phân biệt lỗi parse với lỗi validation không?** Dữ liệu sai kiểu có bị từ chối ở đúng ranh giới?
3. **Có phân biệt từ chối nghiệp vụ với lỗi kỹ thuật không?** Timeout không bị biến thành “hết hàng”?
4. **Có kiểm tra quyền từ nguồn đáng tin cậy không?** Thông tin lỗi có tiết lộ tài nguyên ngoài phạm vi truy cập?
5. **Có phản hồi máy đọc được không?** HTTP status, code, field và message có ổn định, được tài liệu hóa?
6. **Có xử lý nhiều lỗi độc lập hợp lý không?** Tránh chạy bước nguy hiểm khi dữ liệu trước đó chưa hợp lệ.
7. **Có bảo vệ tác dụng phụ không?** Request không hợp lệ không ghi dữ liệu; cập nhật đồng thời vẫn giữ bất biến.
8. **Có kiểm thử tại ranh giới không?** Test validator và test HTTP/binding/authorization theo các mức phù hợp.
9. **Có cân nhắc tương thích không?** Thêm ràng buộc hoặc thay code/status có làm client cũ thất bại?

Không nhất thiết một endpoint nhỏ phải có cả hệ thống validation nhiều lớp. Điều cần bảo đảm là **những tiền điều kiện quan trọng có nơi thực thi rõ ràng và hành vi thất bại có thể dự đoán**.

## 15. Tình huống tự luyện

### Tình huống A — Sai kiểu dữ liệu

Client gửi:

~~~json
{"productCode": "SKU-42", "quantity": "5"}
~~~

**Câu hỏi:** API có nên tự chuyển "5" thành số 5 không?

**Gợi ý:** Phụ thuộc hợp đồng. Nếu quantity được định nghĩa là JSON number, ép kiểu âm thầm có thể che lỗi tích hợp; nên từ chối rõ ràng. Nếu API chủ ý chấp nhận chuỗi số, cần mô tả và kiểm thử quy tắc chuyển kiểu.

### Tình huống B — Sai miền giá trị

Client gửi quantity = 0 và productCode rỗng. Validator trả riêng lỗi cho quantity rồi dừng.

**Câu hỏi:** Có nên trả cả hai lỗi không?

**Gợi ý:** Với hai trường độc lập, có thể thu thập cả hai để giảm số lần gửi lại. Không nên tiếp tục gọi CSDL hoặc tạo đơn chỉ để tìm thêm lỗi.

### Tình huống C — Request hợp lệ nhưng sản phẩm hết hàng

Client gửi productCode đúng định dạng, quantity = 3; kho chỉ còn 1.

**Câu hỏi:** Đây là lỗi đầu vào hay từ chối nghiệp vụ? Có nên trả lỗi INVALID_FORMAT không?

**Gợi ý:** Đây là vấn đề trạng thái nghiệp vụ khi dữ liệu kho đáng tin cậy. Có thể trả kết quả xung đột hoặc từ chối theo hợp đồng; INVALID_FORMAT không phản ánh đúng nguyên nhân.

### Tình huống D — Kiểm tra quyền sau khi trả chi tiết lỗi

API trả “Đơn hàng 4821 thuộc về khách hàng B” cho người không có quyền truy cập đơn đó.

**Câu hỏi:** Vì sao phản hồi dù dễ hiểu vẫn không phù hợp?

**Gợi ý:** Nó có thể tiết lộ thông tin riêng tư. Cần xác thực/phân quyền và thiết kế thông báo lỗi phù hợp mức quyền, đồng thời ghi thông tin điều tra chi tiết ở phía máy chủ khi cần.

### Tình huống E — Thêm trường bắt buộc

Phiên bản mới bắt buộc **deliveryAddress**, trong khi client cũ chỉ gửi productCode và quantity.

**Câu hỏi:** Có thể thay đổi validator trực tiếp và coi đây chỉ là refactor nội bộ không?

**Gợi ý:** Không. Hợp đồng request thay đổi và client cũ có thể thất bại. Cần xem phương án chuyển đổi, default nếu có căn cứ hoặc chiến lược versioning, cùng test tương thích.

---

**Ghi nhớ:** Tiền điều kiện nói rõ **đầu vào, quyền và trạng thái nào cần có trước khi thao tác hợp lệ**. Hãy kiểm tra chúng tại đúng ranh giới, phân biệt sai dữ liệu với từ chối nghiệp vụ và lỗi hạ tầng, rồi trả phản hồi **rõ ràng, ổn định và an toàn**. Một API có hợp đồng dễ hiểu giúp các bên tích hợp đúng, kiểm thử đầy đủ và thay đổi ít rủi ro hơn.
