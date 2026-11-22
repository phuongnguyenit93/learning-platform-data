# Giữ tương thích và phát triển hợp đồng theo thời gian

> **Chương:** Hợp đồng API  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **hợp đồng API** gồm cả cấu trúc dữ liệu, ý nghĩa hành vi, lỗi, quyền truy cập và các bảo đảm mà bên gọi đang dựa vào.
2. Phân biệt tính tương thích theo **hướng nâng cấp bên cung cấp** và **hướng nâng cấp bên tiêu thụ**, thay vì chỉ nhìn vào thay đổi tên trường.
3. Đánh giá các thay đổi thường gặp: thêm hoặc xóa trường, đổi kiểu, mở rộng enum, thay giá trị mặc định, siết validation và thay đổi ý nghĩa của kết quả.
4. Xây dựng kế hoạch phát triển hợp đồng qua các giai đoạn **mở rộng → di chuyển bên dùng → thu hẹp**, có thể triển khai nhiều phiên bản ứng dụng cùng lúc.
5. Biết khi nào cần phiên bản API mới, tài liệu ngừng hỗ trợ, kiểm thử hợp đồng và giám sát mức sử dụng.
6. Áp dụng các quyết định trên vào ví dụ API Java trả thông tin đơn hàng mà không làm các client cũ ngừng hoạt động ngoài ý muốn.

## 1. Hợp đồng API là lời hứa giữa những thành phần triển khai độc lập

Giả sử ứng dụng điện thoại gọi:

~~~http
GET /orders/OD-123 HTTP/1.1
Accept: application/json
Authorization: Bearer <access-token>
~~~

và nhận:

~~~json
{
  "orderId": "OD-123",
  "totalVnd": 250000,
  "status": "PAID"
}
~~~

Nếu người phát triển backend quyết định đổi `totalVnd` thành `amountDueVnd` vì tên mới rõ nghĩa hơn, mã backend có thể được cải thiện khả năng đọc. Nhưng ứng dụng điện thoại đã phát hành trước đó vẫn đọc `totalVnd` và có thể nhận `null` hoặc lỗi khi trường cũ biến mất. **Một thay đổi tốt bên trong mã chưa chắc là thay đổi tương thích ở ranh giới API.**

**Hợp đồng API (API contract)** là tập những điều bên cung cấp (provider) cam kết và bên tiêu thụ (consumer) có thể dựa vào khi trao đổi. Nó rộng hơn danh sách URL hoặc một file OpenAPI.

| Thành phần hợp đồng | Ví dụ câu hỏi cần thống nhất |
| --- | --- |
| Điểm truy cập và thao tác | `GET /orders/{id}` trả gì? `POST` có tạo trùng khi retry không? |
| Đầu vào | Tham số nào bắt buộc, định dạng nào hợp lệ, giới hạn ra sao? |
| Đầu ra | Trường nào luôn có, trường nào có thể thiếu hoặc `null`? |
| Kiểu và đơn vị | `totalVnd` là đồng nguyên hay phần nhỏ nhất, `createdAt` dùng UTC hay giờ địa phương? |
| Ý nghĩa nghiệp vụ | Tổng tiền trước hay sau giảm giá? `PAID` nghĩa là đã nhận tiền hay chỉ đã gửi yêu cầu? |
| Lỗi và trạng thái | Không tìm thấy là 404; sai input là 400/422 theo hợp đồng nào? |
| Xác thực và phân quyền | Ai được xem/sửa tài nguyên nào? |
| Phân trang, sắp xếp và giới hạn | Trang kết quả ổn định thế nào, có cursor không, giới hạn kích thước bao nhiêu? |
| Khả năng thử lại | Timeout có an toàn để gọi lại? Có idempotency key không? |
| Vòng đời | Phiên bản nào còn được hỗ trợ, bao giờ trường hoặc endpoint cũ bị loại bỏ? |

Hợp đồng có thể được ghi bằng OpenAPI, tài liệu, ví dụ, schema sự kiện, mã client sinh tự động và kiểm thử. **Không một nguồn riêng lẻ nào tự chứng minh hệ thống đang tuân thủ hợp đồng**: phải đối chiếu tài liệu với request/response thực tế.

### Vì sao đây là vấn đề của chất lượng mã nguồn?

Trong `CODE_QUALITY_FUNDAMENTALS`, mục tiêu là hiểu những thuộc tính khiến mã **đáng tin cậy, dễ hiểu và dễ thay đổi**. Hợp đồng rõ ràng giúp bên gọi không phải đoán ý nghĩa của trường; hợp đồng tương thích cho phép thay đổi triển khai và triển khai độc lập mà giảm nguy cơ gián đoạn; kiểm thử hợp đồng giúp phát hiện hồi quy trước khi phát hành.

Với hệ thống có nhiều client, chi phí thay đổi không chỉ nằm trong repository backend. Nó còn bao gồm ứng dụng di động chưa cập nhật, hệ thống đối tác, batch job, báo cáo và những client có vòng đời phát hành khác nhau.

## 2. “Tương thích” luôn cần chỉ rõ phiên bản nào nói chuyện với phiên bản nào

Gọi **P1** là provider cũ, **P2** là provider mới; **C1** là consumer cũ, **C2** là consumer mới. Có ít nhất bốn tổ hợp:

| Provider | Consumer | Điều cần kiểm tra |
| --- | --- | --- |
| P1 | C1 | Hệ thống hiện tại hoạt động theo hợp đồng đã công bố |
| **P2** | **C1** | Client cũ có tiếp tục hoạt động khi backend đã nâng cấp? |
| **P1** | **C2** | Client mới có chịu được backend chưa nâng cấp trong lúc triển khai? |
| P2 | C2 | Hành vi mới hoạt động như dự kiến |

Trong giao tiếp bất đồng bộ, tên gọi *backward compatibility* và *forward compatibility* đôi khi được dùng theo quy ước schema writer/reader khác nhau. Để tránh nhập nhằng, khi review hãy nói rõ: **“provider mới phục vụ consumer cũ”** hay **“consumer mới đọc dữ liệu từ provider cũ”**.

Ví dụ:

- **Backend trả thêm một trường:** C1 có thể vẫn chạy nếu nó bỏ qua trường không biết. Nhưng client được cấu hình từ chối trường lạ có thể lỗi.
- **Backend ngừng trả trường cũ:** C1 đang sử dụng trường đó có thể lỗi ngay.
- **Client mới bắt đầu gửi trường mới:** P1 chỉ xử lý được nếu hợp đồng cũ cho phép và bỏ qua/hiểu trường ấy đúng cách.
- **Client mới bắt buộc trường mới trong response:** P1 có thể không cung cấp, làm C2 lỗi trong giai đoạn hai phiên bản cùng tồn tại.

Tương thích cũng phụ thuộc **dữ liệu thực tế**. Schema có thể cho phép giá trị mới, nhưng client có thể chứa một `switch` chỉ xử lý ba trạng thái đã biết. Vì vậy, “schema vẫn hợp lệ” chưa chắc “hành vi người dùng vẫn đúng”.

### Ai chịu trách nhiệm về điều gì?

- **Provider:** giữ các cam kết đã công bố, xác định thay đổi, thông báo vòng đời, kiểm tra các tổ hợp client còn được hỗ trợ.
- **Consumer:** chỉ dựa vào những cam kết thực sự được định nghĩa, xử lý trường tùy chọn và giá trị lạ theo chính sách an toàn.
- **Nhóm sở hữu nền tảng/API:** hỗ trợ tài liệu và quy trình kiểm thử, theo dõi phiên bản, thỏa thuận thời hạn chuyển đổi khi có bên thứ ba.

“Consumer phải linh hoạt” không phải lý do để provider tùy tiện đổi nghĩa của dữ liệu. Ngược lại, một client tự đặt giả định chưa từng có trong hợp đồng có thể bị phá vỡ ngay cả khi provider không làm sai đặc tả; cần kiểm tra thực tế các client đang tồn tại.

## 3. Phân loại thay đổi có thể ảnh hưởng đến tương thích

Không có bảng nào đúng tuyệt đối cho mọi API, nhưng các trường hợp sau là điểm xuất phát tốt:

| Thay đổi ở provider | Đánh giá ban đầu | Điều kiện và rủi ro |
| --- | --- | --- |
| Thêm **trường tùy chọn** vào JSON response | Thường tương thích | Client cũ không được từ chối trường lạ hoặc giả định đúng một tập field |
| Thêm **trường bắt buộc** vào request | Thường phá vỡ | Client cũ không gửi được; cần default hoặc phiên bản mới |
| Thêm trường request tùy chọn có mặc định hợp lý | Thường tương thích | Nếu vắng phải giữ được hành vi cũ; validator cũ/client mới phải xét tương thích hai chiều |
| Xóa hoặc đổi tên trường response cũ | Thường phá vỡ | Consumer đọc trường cũ không còn dữ liệu |
| Đổi kiểu `number` → `string` hoặc đổi định dạng ngày | Có nguy cơ phá vỡ cao | Parser, client sinh tự động hoặc logic tính toán có thể lỗi |
| Đổi trường từ luôn có sang có thể `null` | Thường phá vỡ | Consumer có thể không xử lý null |
| Thêm giá trị mới vào enum response | Có nguy cơ phá vỡ | `switch` toàn diện, validator hoặc UI có thể từ chối |
| Siết giới hạn ký tự hoặc định dạng request | Thường phá vỡ | Request trước đây hợp lệ giờ bị từ chối |
| Mở rộng request được chấp nhận | Có thể tương thích | Cần kiểm tra tác dụng phụ và bảo đảm dữ liệu |
| Đổi mã HTTP hoặc mã lỗi | Có thể phá vỡ | Client thường rẽ nhánh theo status/error code |
| Đổi thứ tự mặc định của danh sách | Có thể phá vỡ ngữ nghĩa | Consumer có thể dựa vào thứ tự cũ để phân trang/hiển thị |
| Đổi ý nghĩa một trường nhưng giữ tên/kiểu | Có thể phá vỡ nghiêm trọng | Kiểm tra schema vẫn qua, quyết định nghiệp vụ có thể sai |
| Thêm quy tắc phân quyền hoặc yêu cầu scope mới | Có thể phá vỡ | Client có quyền cũ không gọi được, cần chuyển đổi có chủ đích |

Điểm cần nhớ là **rủi ro được đánh giá từ hành vi consumer đang được hỗ trợ**, không chỉ từ sự khác biệt văn bản trong tài liệu. Thêm một thuộc tính đôi khi an toàn; thêm một enum value vào dữ liệu quyết định thanh toán có thể nguy hiểm hơn đổi một đường dẫn ít được sử dụng.

## 4. Tương thích cấu trúc chưa đủ: ý nghĩa nghiệp vụ phải giữ ổn định

Giả sử response cũ có:

~~~json
{ "totalVnd": 240000 }
~~~

Trong hợp đồng ban đầu, `totalVnd` là **số tiền cuối cùng cần thanh toán, sau khuyến mãi**. Một phiên bản mới vẫn trả cùng kiểu số nhưng thay nghĩa thành **tổng trước khuyến mãi**:

~~~json
{ "totalVnd": 300000 }
~~~

Schema không thay đổi, JSON vẫn hợp lệ, ứng dụng cũ không crash. Nhưng nếu client dùng trường đó để hiển thị “Cần thanh toán”, người mua thấy giá sai. Đây là **semantic breaking change**, có thể nghiêm trọng hơn lỗi parse dễ nhìn thấy.

Những thay đổi ý nghĩa cần chú ý:

- **Tiền tệ:** VND nguyên hay đơn vị nhỏ nhất? Đã gồm thuế, phí, giảm giá và khoản hoàn chưa?
- **Thời gian:** `createdAt` là thời điểm UTC, giờ địa phương có offset hay chuỗi không có múi giờ?
- **Trạng thái:** `PAID` là đã xác nhận thanh toán hay mới gửi yêu cầu? Có thể chuyển ngược trạng thái không?
- **Định danh:** `orderId` có phân biệt chữ hoa/thường? Có thể tái sử dụng hoặc thay đổi không?
- **Số lượng:** `count` đếm tổng bản ghi hay số phần tử trang hiện tại?
- **Danh sách:** thứ tự mặc định, có bao gồm bản ghi đã xóa, có bảo đảm không trùng không?
- **Giá trị vắng mặt:** `null` nghĩa là chưa biết, chưa cung cấp hay không áp dụng?

Nếu phải đổi ý nghĩa, thường nên tạo **trường hoặc phiên bản mới với tên, đơn vị, mô tả rõ**, rồi lập kế hoạch chuyển đổi. Không nên âm thầm giữ tên cũ và hy vọng các consumer “hiểu theo ngữ cảnh”.

### Nguyên tắc thiết kế kiểu dữ liệu rõ nghĩa

Một contract đáng tin cậy phải nêu ít nhất:

1. Kiểu và miền giá trị: số không âm, độ dài tối đa, tập mã hợp lệ.
2. Đơn vị và độ chính xác: `amountDueVnd` là số nguyên VND; thời gian theo ISO 8601 kèm offset hoặc UTC.
3. Trạng thái tùy chọn: thiếu trường, `null`, chuỗi rỗng và giá trị 0 khác nhau như thế nào.
4. Điều kiện chuyển trạng thái: khi nào từ `PENDING` sang `PAID`, có thể bị đảo ngược không.
5. Cách phản hồi lỗi và hành vi retry.
6. Quy tắc bảo mật: trường nào được phép xuất cho đối tượng nào.

Hệ thống có Java `long` ở server nhưng client JavaScript sử dụng `Number` cần chú ý giá trị nguyên vượt phạm vi chính xác an toàn của client. Chọn định dạng JSON theo dải giá trị thực tế; nếu dùng chuỗi số để tránh mất chính xác, phải **ghi rõ trong hợp đồng**, tránh đổi ngầm khi dữ liệu lớn hơn.

## 5. Mở rộng request và response: trường bắt buộc, tùy chọn, thiếu và null

Một quy tắc hữu ích: **provider mới nên tiếp tục đọc được request cũ** trong các phiên bản vẫn được hỗ trợ. Ví dụ muốn thêm `promotionCode` vào `POST /orders`:

**Request cũ:**

~~~json
{
  "customerId": "C-12",
  "items": [{"sku": "P-01", "quantity": 2}]
}
~~~

**Request mới:**

~~~json
{
  "customerId": "C-12",
  "items": [{"sku": "P-01", "quantity": 2}],
  "promotionCode": "SAVE50"
}
~~~

Nếu `promotionCode` là tùy chọn và **vắng mặt nghĩa là không áp dụng khuyến mãi**, provider mới có thể xử lý request cũ đúng như trước. Ngược lại, nếu provider bắt buộc mọi request có `promotionCode` thì client cũ sẽ bị từ chối.

Đừng tự động đồng nhất:

| Dữ liệu client gửi | Ý nghĩa có thể có |
| --- | --- |
| Không có khóa `promotionCode` | Không cung cấp mã; dùng chính sách mặc định đã nêu |
| `"promotionCode": null` | Cố ý gửi null; chấp nhận hay từ chối phải được định nghĩa |
| `"promotionCode": ""` | Chuỗi rỗng, có thể không hợp lệ hoặc được xem là không dùng |
| `"promotionCode": "SAVE50"` | Mã được cung cấp; cần kiểm tra tính hợp lệ và quyền sử dụng |

Với `PATCH`, trường **không được gửi** có thể nghĩa là “giữ nguyên”, còn **gửi null** có thể nghĩa là “xóa”. DTO deserialize cả hai về `null` sẽ làm mất khác biệt này nếu không giữ thông tin trường có hiện diện. Cách hiểu cụ thể còn phụ thuộc loại PATCH và media type, chẳng hạn JSON Merge Patch khác JSON Patch.

### Consumer nên xử lý trường lạ như thế nào?

Ở **response**, bỏ qua một trường mới không cần dùng có thể giúp client cũ tiếp tục hoạt động. Nhưng các trường được dùng để quyết định quyền, tiền hoặc trạng thái quan trọng không nên có mặc định “thành công” khi không hiểu dữ liệu.

Ở **request**, chấp nhận mọi trường không biết có thể che lỗi đánh máy (`amountVdn` thay vì `amountVnd`) hoặc tạo chênh lệch giữa validation và xử lý. Có thể chọn policy nghiêm ngặt với request, miễn là provider không thay đổi đột ngột hành vi đã công bố.

Sự linh hoạt phải có **ranh giới an toàn**: bỏ qua dữ liệu phụ chưa hiểu khác với bỏ qua điều kiện bắt buộc để quyết định thanh toán.

## 6. Lỗi, mã HTTP và hành vi thử lại cũng là hợp đồng

Hai response cùng mã 200 có thể khác nhau hoàn toàn về ý nghĩa. Hai lỗi cùng nhóm 4xx/5xx cũng không nhất thiết khiến client xử lý giống nhau.

Ví dụ API công bố rằng không tìm thấy đơn trả:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json
~~~

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng",
  "requestId": "req-abc"
}
~~~

Nếu bản mới trả 200 với `{"order":null}`, client cũ đang kiểm tra 404 để hiển thị trang trống có thể coi nhầm là thành công. Nếu backend đổi mã lỗi `ORDER_NOT_FOUND` thành `MISSING_ORDER`, những consumer dùng error code để quyết định xử lý cũng cần cập nhật.

Những phần nên mô tả ổn định:

- Nhóm HTTP status, mã lỗi có cấu trúc, cách phân biệt lỗi đầu vào, phân quyền, không tìm thấy và lỗi tạm thời.
- Trường nào trong lỗi luôn có; `message` có phải chỉ để con người đọc hay là giá trị ổn định cho máy xử lý.
- Khi nào retry được và khoảng thời gian nên chờ; có dùng `Retry-After` hay cơ chế tương đương không.
- Với thao tác ghi, có hỗ trợ **idempotency key** không, key tồn tại trong phạm vi bao lâu và điều gì xảy ra khi gửi lại cùng key với payload khác.
- Khi client timeout hoặc mất kết nối, cách tra cứu trạng thái thực của thao tác đã gửi.

**Timeout phía client không chứng minh server chưa xử lý.** Nếu lệnh `POST` đã tạo đơn hoặc gửi thanh toán, retry thiếu quy tắc có thể nhân đôi tác dụng phụ. Khả năng retry/idempotency là phần quan trọng của tính đúng đắn hợp đồng, không chỉ là chi tiết vận hành nội bộ.

## 7. Phát triển enum, danh sách và kiểu thời gian

### 7.1. Giá trị enum mới có thể phá vỡ consumer cũ

Ban đầu API chỉ trả `PENDING`, `PAID`, `CANCELLED`. Bản mới thêm `REFUND_PENDING`. Client cũ dùng `switch` toàn diện mà không xử lý giá trị lạ có thể lỗi parse hoặc quyết định sai.

Ví dụ Java cho **hiển thị**:

~~~java
static String statusLabel(String status) {
    return switch (status) {
        case "PENDING" -> "Đang chờ";
        case "PAID" -> "Đã thanh toán";
        case "CANCELLED" -> "Đã hủy";
        default -> "Trạng thái chưa được hỗ trợ";
    };
}
~~~

Cách dự phòng này có thể chấp nhận được với **nhãn hiển thị**, nhưng với quyết định cho phép hoàn tiền, một trạng thái không biết phải được xử lý theo hướng an toàn hoặc được đưa ra thành lỗi rõ ràng. Không nên xem giá trị lạ là `PAID` chỉ để tránh lỗi.

Có thể cần thiết kế enum dưới dạng **tập mở** ở client khi hợp đồng hứa sẽ thêm trạng thái, hoặc đặt phiên bản mới khi thêm trạng thái làm thay đổi quy trình nghiệp vụ.

### 7.2. Phân trang và sắp xếp là hành vi có thể dựa vào

Thay từ offset pagination sang cursor pagination hoặc đổi cách sắp xếp mặc định có thể khiến client lặp hoặc bỏ sót đơn hàng nếu nó dựa vào hành vi cũ. Hợp đồng nên nêu:

- Thứ tự ổn định theo khóa nào (ví dụ `createdAt DESC, orderId DESC`).
- Ý nghĩa của `page`, `size`, `cursor` và tổng số phần tử.
- Có thể xuất hiện/xóa bản ghi giữa hai lần tải trang không, và mô hình nhất quán đang bảo đảm điều gì.
- Cách biểu diễn trang cuối và giới hạn `size`.

Thay đổi ngầm mặc định từ 20 lên 100 phần tử mỗi trang có thể làm tăng thời gian tải và chi phí xử lý của client cũ.

### 7.3. Thời gian và giá trị số cần quy ước cố định

Chuỗi thời gian `2026-11-16T09:00:00` thiếu offset có thể bị client diễn giải theo múi giờ máy. Với **thời điểm tuyệt đối**, nên thống nhất biểu diễn có offset/UTC. Với **lịch hẹn theo giờ địa phương**, có thể cần cả ngày giờ và tên vùng (`ZoneId`) vì offset cố định không phản ánh đầy đủ quy tắc lịch.

Khi đổi đơn vị số từ đồng sang nghìn đồng, hoặc thay quy tắc làm tròn tiền, đừng giữ nguyên tên và kiểu trường. Kiểu hợp lệ mà đơn vị sai vẫn là lỗi nghiêm trọng.

## 8. Phiên bản hóa API: một công cụ, không phải lời giải tự động

Có thể chọn những chiến lược phiên bản khác nhau:

| Chiến lược | Ví dụ | Ưu điểm | Chi phí và giới hạn |
| --- | --- | --- | --- |
| Đường dẫn | `/v1/orders`, `/v2/orders` | Dễ nhìn, dễ định tuyến và tài liệu hóa | Dễ nhân đôi endpoint, cần vận hành song song |
| Header/media type | `Accept: application/vnd.example.v2+json` | Giữ URI tài nguyên ổn định | Client và công cụ gateway/cache phải cấu hình đúng |
| Ngày hoặc phiên bản hợp đồng rõ ràng | Header hoặc metadata theo phiên bản cụ thể | Rõ thời điểm/hợp đồng được lựa chọn | Cần quy tắc hỗ trợ và ánh xạ hành vi nhất quán |
| Phát triển tại chỗ với thay đổi bổ sung | Giữ `/orders`, thêm trường tùy chọn | Ít gánh nặng đổi client nếu thật sự tương thích | Không phù hợp để âm thầm thay nghĩa hoặc xóa trường đang dùng |

**Không có lựa chọn luôn tối ưu.** Điều quan trọng là phiên bản nào được hỗ trợ, client chọn phiên bản ra sao, và cách kiểm tra mỗi phiên bản vẫn làm đúng điều đã hứa.

Một số nhóm dùng số phiên bản kiểu `1.2`, nhưng không nên tự suy rằng Semantic Versioning của package áp dụng nguyên vẹn cho mọi thay đổi HTTP API. Quy tắc tăng version và khả năng tương thích phải được nhóm công bố rõ.

### Khi nào cần một phiên bản mới?

Có thể cân nhắc phiên bản mới khi không thể giữ đồng thời hành vi cũ và mới một cách rõ nghĩa, chẳng hạn:

- Đổi trường từ tiền sau giảm sang tiền trước giảm.
- Đổi định dạng dữ liệu mà parser cũ không hiểu.
- Đổi điều kiện phân quyền hoặc luồng nghiệp vụ khiến client cũ không còn xử lý được theo hợp đồng.
- Loại bỏ trường/endpoint cần thiết hoặc thay đổi mô hình trạng thái đáng kể.

Tạo `v2` không giải quyết được vấn đề nếu client cũ vẫn phụ thuộc `v1` và `v1` bị tắt ngay. Phiên bản hóa phải đi kèm **thời gian chuyển đổi, hỗ trợ vận hành và thông báo rõ ràng**.

## 9. Ví dụ xuyên suốt: đổi `totalVnd` thành `amountDueVnd`

Giả sử API cũ trả `totalVnd` với ý nghĩa **số tiền cuối cùng cần thanh toán, bằng VND nguyên**. Tên mới `amountDueVnd` biểu đạt ý nghĩa tốt hơn. Mục tiêu là client mới dùng tên rõ ràng, còn client cũ vẫn đọc được dữ liệu trong giai đoạn chuyển đổi.

### 9.1. Giai đoạn A — mở rộng provider

Giữ trường cũ và **thêm** trường mới, cả hai dùng cùng một giá trị tại cùng thời điểm:

~~~json
{
  "orderId": "OD-123",
  "totalVnd": 250000,
  "amountDueVnd": 250000,
  "status": "PAID"
}
~~~

Nếu client cũ có khả năng bỏ qua thuộc tính mới, nó vẫn đọc `totalVnd` như trước. Client mới đọc `amountDueVnd`. **Hai tên không được tính từ hai chính sách khác nhau**, vì như vậy có thể lệch dữ liệu sau khi thay đổi khuyến mãi.

Ví dụ Java 17:

~~~java
record OrderSnapshot(String orderId, long amountDueVnd, String status) {}

record OrderResponse(
        String orderId,
        long totalVnd,     // Tên cũ, giữ trong giai đoạn chuyển đổi.
        long amountDueVnd, // Tên được khuyến nghị.
        String status
) {}

final class OrderResponseMapper {
    private OrderResponseMapper() {}

    static OrderResponse toResponse(OrderSnapshot order) {
        long amount = order.amountDueVnd();
        return new OrderResponse(
                order.orderId(), amount, amount, order.status());
    }
}
~~~

Đây là **mã ánh xạ dữ liệu**, chưa phải HTTP controller hay cơ chế xác thực. Kết quả phụ thuộc serializer; cần kiểm thử JSON thực tế của framework để chắc chắn hai tên trường được xuất ra đúng như hợp đồng.

### 9.2. Giai đoạn B — di chuyển consumer

1. Công bố trường mới trong tài liệu, ví dụ request/response và SDK tương ứng.
2. Đánh dấu `totalVnd` là **deprecated** (vẫn hoạt động, nhưng có kế hoạch ngừng hỗ trợ).
3. Nâng cấp những consumer đã biết để đọc `amountDueVnd`; trong giai đoạn backend P1/P2 cùng tồn tại, client mới có thể cần fallback tương thích có kiểm soát.
4. Với client di động hoặc tích hợp bên thứ ba, tính đến những phiên bản không thể nâng cấp ngay; kiểm tra thực tế mức sử dụng theo cách tuân thủ quy định dữ liệu.
5. Theo dõi lỗi parse, số lượng request theo phiên bản, tỷ lệ response bất thường và phản hồi từ consumer.

**Deprecated không có nghĩa đã bị xóa.** Phải ghi ngày/thời hạn, kênh thông báo, lựa chọn thay thế và chính sách hỗ trợ phù hợp.

### 9.3. Giai đoạn C — thu hẹp khi an toàn

Chỉ loại bỏ `totalVnd` sau khi phạm vi hỗ trợ đã được cập nhật và các consumer bị ảnh hưởng đã chuyển đổi hoặc có đường sử dụng phiên bản cũ. Nếu không thể bảo đảm, có thể phải giữ cả hai trường lâu hơn hoặc duy trì hai hợp đồng/phiên bản song song.

~~~mermaid
flowchart LR
    A["P1: chỉ totalVnd"] --> B["P2: totalVnd + amountDueVnd"]
    B --> C["Client mới chuyển sang amountDueVnd"]
    C --> D{"Consumer còn dùng tên cũ?"}
    D -->|"Có"| E["Duy trì trường/phiên bản cũ"]
    E --> C
    D -->|"Không, hết thời hạn hỗ trợ"| F["Hợp đồng mới bỏ totalVnd"]
~~~

Đây là cách phát triển **expand → migrate → contract**. Quy tắc tương tự có thể áp dụng cho tên tham số, enum, endpoint và sự kiện, nhưng thứ tự triển khai cụ thể phải xét từng hướng dữ liệu. Với **request mới có trường bắt buộc**, provider thường phải chấp nhận cả request cũ trong một giai đoạn trước khi mọi consumer đều gửi trường mới.

## 10. Mô tả hợp đồng bằng OpenAPI và ví dụ có ý nghĩa

Một đoạn OpenAPI 3.1 rút gọn cho giai đoạn mở rộng có thể là:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.1.0
paths:
  /orders/{orderId}:
    get:
      summary: Xem đơn hàng
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Trả thông tin đơn hàng
          content:
            application/json:
              schema:
                type: object
                required: [orderId, totalVnd, amountDueVnd, status]
                properties:
                  orderId:
                    type: string
                  totalVnd:
                    type: integer
                    format: int64
                    deprecated: true
                    description: |
                      Số tiền cuối cùng phải trả (VND nguyên).
                      Trường cũ, sẽ ngừng hỗ trợ theo lộ trình.
                  amountDueVnd:
                    type: integer
                    format: int64
                    description: Số tiền cuối cùng phải trả (VND nguyên).
                  status:
                    type: string
                    description: Trạng thái đơn theo hợp đồng phiên bản này.
        "404":
          description: Không tìm thấy đơn hàng
~~~

Ví dụ này chỉ minh họa trường hợp thành công và một lỗi. Hợp đồng thực tế cần mô tả xác thực/phân quyền, error schema, trạng thái, định dạng dữ liệu, ví dụ trường hợp biên và các giới hạn cần thiết. `info.version` là phiên bản của **tài liệu API**; nó không tự khiến runtime chọn `v1` hay `v2`.

Đặt `totalVnd` vào danh sách `required` trong giai đoạn mở rộng nghĩa là provider vẫn cam kết luôn trả trường này cho consumer cũ. Muốn bỏ nó khỏi `required` hoặc xóa hẳn, phải coi đây là một thay đổi cần đánh giá tương thích.

Một nguồn đặc tả tốt cần có **chủ sở hữu, lịch sử thay đổi và quy trình đối chiếu** với hệ thống chạy. Tài liệu đầy đủ nhưng không phản ánh mã đang triển khai còn nguy hiểm hơn ghi rõ “chưa hỗ trợ” ở phần chưa hoàn thiện.

## 11. Kiểm thử hợp đồng ở nhiều cấp

Không thể chỉ nhìn diff của OpenAPI để biết mọi consumer sẽ hoạt động đúng. Cần phối hợp:

1. **Schema validation:** request/response thực tế có đúng field, kiểu, nullability và ràng buộc đã công bố không?
2. **Provider contract tests:** server mới vẫn đáp ứng các trường hợp quan trọng mà consumer cũ đang dựa vào không?
3. **Consumer contract tests:** client mới có đọc được phiên bản server còn hỗ trợ trong giai đoạn triển khai không?
4. **Consumer-driven contracts (khi phù hợp):** consumer mô tả những tương tác thực sự sử dụng, provider xác minh các tương tác đó trước khi phát hành.
5. **Integration/end-to-end tests:** lỗi, phân quyền, dữ liệu thực, retry và side effect có đúng không?
6. **Kiểm thử tương thích theo kịch bản:** chạy các tổ hợp P1/C1, P2/C1, P1/C2 và P2/C2 còn được yêu cầu, không chỉ phiên bản mới nhất.

Ví dụ JUnit 5 kiểm tra **mã ánh xạ** ở phần 9:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderResponseMapperTest {
    @Test
    void preservesLegacyFieldWhileAddingNewField() {
        OrderSnapshot order =
                new OrderSnapshot("OD-123", 250_000L, "PAID");

        OrderResponse response = OrderResponseMapper.toResponse(order);

        assertEquals("OD-123", response.orderId());
        assertEquals(250_000L, response.totalVnd());
        assertEquals(250_000L, response.amountDueVnd());
        assertEquals(response.totalVnd(), response.amountDueVnd());
    }
}
~~~

Test này **không thay thế** bài kiểm thử HTTP/serialization. Với API thực, cần gọi endpoint, giải mã JSON và kiểm tra cả hai trường, mã trạng thái, error response và quyền truy cập. Đồng thời phải thử consumer cũ với response có trường mới, vì một số parser nghiêm ngặt có thể từ chối dữ liệu lạ.

### Kịch bản kiểm thử cần có cho thay đổi `totalVnd`

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| C1 đọc P2 | Client cũ vẫn đọc được `totalVnd` |
| C2 đọc P2 | Client mới đọc được `amountDueVnd` |
| C2 đọc P1 trong giai đoạn hỗ trợ chéo | Client xử lý trường mới vắng theo chính sách fallback rõ ràng |
| Đơn hàng có khuyến mãi | Hai trường cùng biểu thị **số cuối cùng** theo hợp đồng cũ |
| Giá trị 0 và giá trị lớn hợp lệ | Không chuyển thành null, mất chính xác hoặc đổi đơn vị |
| JSON response thực tế | Tên trường và kiểu giữ nguyên, không phụ thuộc cấu hình serializer ngoài dự kiến |
| Trường/thông tin không được phép | Không vô tình lộ dữ liệu nhạy cảm do mở rộng response |
| Error 404, 401/403, timeout | Client vẫn phân biệt đúng kết quả tra cứu và lỗi |
| Tạo lại request ghi | Không làm nhân đôi giao dịch nếu hợp đồng retry/idempotency yêu cầu |

Các test trong bảng phải được lựa chọn theo **hợp đồng thực tế**. Không nên viết test kiểm tra một chi tiết nội bộ mà consumer không thể quan sát, rồi coi nó là bằng chứng tương thích API.

## 12. Triển khai an toàn khi provider và consumer không cùng nâng cấp

Một thay đổi có thể đúng về mã nhưng vẫn lỗi do thứ tự rollout. Ví dụ nhiều instance backend P1/P2 cùng phục vụ lưu lượng; client C2 được phát hành trước khi mọi instance hỗ trợ trường mới. C2 chỉ đọc `amountDueVnd` sẽ lỗi trên P1.

### Một trình tự thường hợp lý cho việc thêm trường response

1. **Chuẩn bị hợp đồng:** xác nhận ý nghĩa, quyền truy cập, giới hạn dữ liệu, consumer cần hỗ trợ.
2. **Mở rộng provider:** phát hành P2 có cả trường cũ và mới.
3. **Kiểm tra khi rollout:** giám sát lỗi, thời gian đáp ứng, tương thích client cũ; bảo đảm các instance còn trong cụm đủ khả năng phục vụ client định phát hành.
4. **Phát hành consumer mới:** dùng trường mới, xử lý fallback trong phạm vi phiên bản còn hỗ trợ nếu cần.
5. **Quan sát và thông báo ngừng dùng:** xác nhận các consumer cần chuyển đã chuyển, tránh kết luận từ một nguồn telemetry không đầy đủ.
6. **Loại bỏ trường cũ theo lộ trình hỗ trợ:** triển khai trên hợp đồng/phiên bản phù hợp, có phương án quay lại nếu xuất hiện consumer chưa được nhận diện.

Đối với **thêm field request**, **thay endpoint** hoặc **chuyển định dạng sự kiện**, thứ tự triển khai có thể khác. Cần xác định trước phiên bản nào **đọc được** và **ghi ra** dữ liệu gì trong từng giai đoạn.

### Giám sát và khả năng quay lại

Các chỉ báo có ích:

- Tỷ lệ 4xx/5xx theo endpoint, phiên bản, nhóm client được phép theo dõi.
- Lỗi deserialize/validation và mã lỗi mới phát sinh sau triển khai.
- Tỷ lệ request dùng trường/endpoint cũ nếu đo được mà không thu thập dữ liệu nhạy cảm vượt nhu cầu.
- Dữ liệu bị mất hoặc sai đơn vị, trạng thái không xác định, tăng retry/duplicate.
- Sai khác kết quả giữa phiên bản cũ và mới trên các trường hợp có thể so sánh.

**Rollback code không luôn rollback dữ liệu.** Nếu bản mới đã ghi giá trị hoặc trạng thái mà bản cũ không hiểu, việc quay lại P1 có thể gây lỗi. Với thay đổi đồng thời database hoặc event schema, cần thử cả hướng **bản cũ đọc dữ liệu do bản mới tạo** trước khi coi rollback là an toàn.

## 13. Hợp đồng sự kiện và dữ liệu lưu bền vững

Ngoài HTTP API, hợp đồng còn nằm trong message queue, event stream và dữ liệu lưu giữa các lần phát hành. Producer mới có thể ghi sự kiện trong khi consumer cũ vẫn đang đọc. Một consumer có thể xử lý lại **sự kiện lịch sử** nhiều tháng sau, ngay cả khi provider HTTP hiện tại đã đổi.

Ví dụ sự kiện cũ:

~~~json
{
  "eventType": "OrderPaid",
  "orderId": "OD-123",
  "totalVnd": 250000
}
~~~

Producer muốn thêm `amountDueVnd` có thể phát cả hai trường trong giai đoạn chuyển đổi, nhưng cần xét:

- **Schema của event đã được ghi bền:** các bản cũ sẽ còn được đọc lại bao lâu?
- **Quy tắc schema registry/serialization:** định dạng JSON, Avro, Protobuf... có khả năng bỏ qua field lạ, default hoặc số field tương thích khác nhau.
- **Ý nghĩa bất biến của sự kiện:** `OrderPaid` biểu diễn điều đã xảy ra; không nên đổi nghĩa hồi tố chỉ vì hệ thống hiện tại đổi quy tắc.
- **Consumer mới xử lý sự kiện cũ:** có fallback, transform hoặc versioned deserializer khi cần.
- **Trùng lặp và thứ tự:** thay đổi dữ liệu không loại bỏ yêu cầu idempotency, partition/order và xử lý phát lại.

Không nên giả định quy tắc “thêm trường tùy chọn luôn an toàn” áp dụng giống hệt cho mọi hệ mã hóa và mọi schema registry. Cần kiểm tra **chế độ tương thích cụ thể của định dạng và nền tảng đang sử dụng**.

## 14. Quy trình review một thay đổi hợp đồng

Khi có một pull request sửa API, có thể thực hiện theo trình tự:

1. **Xác định hành vi đang cam kết:** phiên bản, endpoint, request/response, lỗi, quyền, ngữ nghĩa trường.
2. **Liệt kê các consumer có thể bị ảnh hưởng:** web, mobile, SDK, đối tác, cron/batch, event processor; chỉ suy từ repository backend thường chưa đủ.
3. **Phân loại thay đổi:** thêm, xóa, đổi kiểu, đổi nghĩa, thay validation hoặc thay hành vi runtime.
4. **Vẽ ma trận tương thích:** P2/C1 và P1/C2 có cần chạy đồng thời không? Những tổ hợp nào đang được hỗ trợ?
5. **Đề xuất lộ trình phát hành:** giữ trường cũ, thêm default, triển khai song song, tạo phiên bản mới hoặc phương án khác.
6. **Xác định dữ liệu và vận hành:** lịch sử sự kiện, dữ liệu mới, cache, API gateway, khả năng rollback.
7. **Viết kiểm thử có ý nghĩa:** schema, contract, hành vi thực và các trường hợp lỗi/biên.
8. **Cập nhật tài liệu và thông báo:** trường thay thế, trạng thái deprecation, thời hạn hỗ trợ và hướng chuyển đổi.
9. **Giám sát sau triển khai:** phát hiện consumer chưa biết, lỗi parse, kết quả sai và hành vi retry bất thường.

### Checklist ngắn

- [ ] Tôi biết provider và consumer nào đang được hỗ trợ.
- [ ] Tôi xác nhận thay đổi có giữ **nghĩa của dữ liệu**, đơn vị, nullability và hành vi lỗi không.
- [ ] Tôi đã kiểm tra ảnh hưởng tới client nghiêm ngặt với trường/enum mới.
- [ ] Tôi biết request cũ còn được chấp nhận và response cũ còn được trả theo hợp đồng nào.
- [ ] Tôi không dùng “thêm trường” làm lý do bỏ qua quyền truy cập hoặc rò rỉ dữ liệu.
- [ ] Tôi đã xét mã trạng thái, mã lỗi, phân trang, retry và idempotency nếu bị ảnh hưởng.
- [ ] Tôi có chiến lược triển khai cho giai đoạn nhiều phiên bản cùng hoạt động.
- [ ] Tôi có kiểm thử tại ranh giới JSON/HTTP hoặc serialization thực, không chỉ unit test nội bộ.
- [ ] Tôi có tài liệu deprecation và phương án hỗ trợ consumer chưa chuyển.
- [ ] Tôi đã đánh giá khả năng rollback cả mã và dữ liệu.

## 15. Những ngộ nhận cần tránh

**“Chỉ cần OpenAPI diff không báo breaking là an toàn.”** Diff cấu trúc không phát hiện hết thay đổi nghĩa, default, quyền và hành vi runtime.

**“Thêm field vào response luôn không ảnh hưởng.”** Consumer nghiêm ngặt hoặc schema validator cũ có thể từ chối field lạ.

**“Không đổi tên trường thì không có breaking change.”** Đổi đơn vị, thứ tự, cách làm tròn hoặc ý nghĩa là thay đổi hợp đồng dù tên và kiểu giữ nguyên.

**“Tạo `/v2` là xong vấn đề tương thích.”** Cần vận hành và hỗ trợ `/v1` cho consumer vẫn được cam kết, cùng lộ trình di chuyển.

**“Deprecated đồng nghĩa có thể xóa ngay.”** Deprecated là tín hiệu về tương lai; loại bỏ cần quy trình và thời hạn hỗ trợ rõ.

**“Client mới luôn được deploy sau server mới.”** Trong hệ thống nhiều instance, CDN, ứng dụng offline và phiên bản mobile cũ, thứ tự có thể không được kiểm soát hoàn toàn.

**“Chỉ cần test phiên bản mới nhất.”** Nhiều lỗi chỉ xuất hiện trong tổ hợp provider mới với client cũ hoặc ngược lại.

**“Consumer bỏ qua trường không hiểu nghĩa là luôn an toàn.”** Với thông tin quyết định quyền hoặc giao dịch, giá trị không biết cần được xử lý cẩn trọng, có thể từ chối thay vì đoán.

**“Rollback backend nghĩa là mọi thứ đã về trạng thái cũ.”** Dữ liệu hoặc event do phiên bản mới ghi có thể không tương thích với ứng dụng cũ.

## 16. Câu hỏi tự kiểm tra

1. Backend đổi response `totalVnd` thành `amountDueVnd` và xóa trường cũ ngay. Vì sao đây là thay đổi có nguy cơ phá vỡ hợp đồng?
2. Thêm trường response tùy chọn có an toàn với mọi consumer không? Hãy nêu trường hợp client cũ vẫn có thể lỗi.
3. Phân biệt việc provider mới phục vụ client cũ và client mới gọi provider cũ. Mỗi hướng cần kiểm thử gì?
4. Một trường `amount` vẫn là số nguyên nhưng chuyển từ VND sang nghìn VND. Vì sao schema validation chưa đủ phát hiện lỗi?
5. Vì sao thêm `REFUND_PENDING` vào enum có thể ảnh hưởng đến ứng dụng cũ? Xử lý giá trị lạ khác nhau thế nào giữa hiển thị và quyết định hoàn tiền?
6. Trong API cập nhật một phần, việc bỏ trường và gửi trường bằng `null` có thể có ý nghĩa gì? Chúng cần được biểu diễn ra sao ở server?
7. Khi client timeout sau `POST` thanh toán, tại sao không nên retry ngay nếu chưa biết chính sách idempotency?
8. Hãy mô tả ba giai đoạn để đổi tên trường API mà client mobile cũ vẫn được hỗ trợ.
9. Vì sao rollback provider sau khi đã ghi sự kiện có schema mới cần xét cả consumer xử lý sự kiện lịch sử?
10. Hãy viết một bảng kiểm thử ngắn cho một thay đổi từ `/v1/orders` sang `/v2/orders` có thêm trường bắt buộc và thay error code.

## Ghi nhớ

**Hợp đồng API là những cam kết có thể quan sát từ bên ngoài và được nhiều phiên bản phần mềm dựa vào.** Giữ tương thích đòi hỏi xem xét cả cấu trúc **và** ý nghĩa dữ liệu, cả request **và** response, cả hành vi thành công **và** lỗi. Khi phải thay đổi, hãy xác định rõ các consumer bị ảnh hưởng, mở rộng hợp đồng có kiểm soát, chuyển đổi theo lộ trình, kiểm thử các tổ hợp phiên bản đang hỗ trợ và chỉ loại bỏ phần cũ khi điều kiện hỗ trợ cho phép.
