# Excessive data exposure

## 1. Khi API trả nhiều dữ liệu hơn bên gọi được phép biết

Một API có thể xác thực đúng người dùng, trả về đúng tài nguyên và tạo JSON hoàn toàn hợp lệ nhưng vẫn làm lộ dữ liệu. Nguyên nhân là phản hồi chứa những thuộc tính không cần thiết hoặc không được phép công khai cho bên gọi trong tình huống đó.

**Excessive data exposure** là tình trạng API đưa ra ngoài nhiều thông tin hơn hợp đồng và chính sách truy cập cho phép. Dữ liệu bị lộ có thể nằm trong body, header, đường dẫn tải xuống, lỗi trả về, đối tượng lồng nhau hoặc một biến thể endpoint ít được sử dụng.

Ví dụ, khách hàng được phép xem đơn hàng của mình. API trả cả chi phí nhập hàng, ghi chú xử lý gian lận và dữ liệu nội bộ của cổng thanh toán vì controller serialize trực tiếp đối tượng lấy từ cơ sở dữ liệu. Giao diện chỉ hiển thị mã đơn và trạng thái, nhưng trình duyệt đã nhận toàn bộ phần còn lại.

Mục tiêu bảo mật cần chuyển thành yêu cầu cụ thể:

> Mỗi biểu diễn API chỉ chứa những trường mà chủ thể được phép đọc và cần cho chức năng đã định, bao gồm cả dữ liệu lồng nhau và thông tin phụ của phản hồi.

Để kiểm chứng yêu cầu này, phải xác định được **ai gọi**, **đọc tài nguyên nào**, **dùng cho mục đích gì**, **trường nào được trả** và **kiểm soát được thực thi ở đâu**.

## 2. Phân biệt quyền đọc tài nguyên với quyền đọc thuộc tính

Quyền truy cập một đối tượng không mặc nhiên cho phép đọc mọi thuộc tính của đối tượng đó.

| Câu hỏi | Ví dụ với đơn hàng | Kiểm soát tương ứng |
| --- | --- | --- |
| Bên gọi đã được xác thực chưa? | Request có danh tính người dùng hợp lệ | Authentication |
| Bên gọi có được xem đơn hàng này không? | Đơn hàng thuộc khách hàng hoặc phạm vi hỗ trợ được cấp | Quyền trên đối tượng, tenant và quan hệ |
| Bên gọi được xem phần nào của đơn hàng? | Khách hàng thấy trạng thái nhưng không thấy điểm đánh giá gian lận | Quyền đọc thuộc tính và biểu diễn phản hồi |
| Những trường được phép có cần cho chức năng này không? | Danh sách đơn hàng không cần địa chỉ giao hàng đầy đủ của mọi đơn | Giảm thiểu dữ liệu theo mục đích |

Các câu hỏi liên quan nhưng không thể thay thế nhau. Chặn truy cập đơn hàng của người khác không sửa được lỗi trả dư trường trong đơn hàng của chính người dùng. Ngược lại, một DTO chỉ có ít trường cũng không cho phép bỏ kiểm tra chủ sở hữu đối tượng.

Lỗi ghi quá nhiều thuộc tính từ request, thường được mô tả bằng các khái niệm như mass assignment, nằm ở chiều dữ liệu đi vào. Bài này tập trung chiều dữ liệu đi ra. Một hệ thống có thể cần kiểm soát cả hai, nhưng không nên coi một danh sách trường đầu vào là chính sách đầu ra.

## 3. Tại sao lọc trên frontend không giải quyết được vấn đề?

Xét luồng sau:

```text
Cơ sở dữ liệu
    → đối tượng nội bộ chứa nhiều trường
    → API serialize toàn bộ đối tượng
    → body HTTP đến client
    → frontend chỉ render vài trường
```

Ranh giới công khai đã bị vượt qua ngay khi body đến client. Người dùng có thể quan sát response bằng công cụ phát triển, client HTTP hoặc một chương trình tự viết. Họ không bị giới hạn bởi những gì giao diện chọn hiển thị.

Những cách sau đều không phải kiểm soát truy cập dữ liệu:

- Ẩn một cột trong bảng hoặc một phần tử bằng CSS.
- Không tạo nút để xem dữ liệu nhạy cảm.
- Gửi trường nhạy cảm rồi xóa nó khỏi object trong JavaScript.
- Dùng tên thuộc tính khó đoán.
- Mã hóa Base64 một giá trị trước khi trả về.
- Cho rằng ứng dụng di động là client duy nhất có thể gọi endpoint.

Kiểm soát cần nằm ở phía có thẩm quyền tạo phản hồi, trước khi dữ liệu vượt qua ranh giới tin cậy. Frontend có thể xử lý trình bày, nhưng không được là nơi quyết định cuối cùng một người có thể nhận trường nào.

## 4. Mô hình đe dọa cho một phản hồi API

Trước khi chọn giải pháp, cần kiểm kê các loại thông tin mà phản hồi có thể mang theo.

| Nhóm dữ liệu | Ví dụ | Rủi ro khi trả dư |
| --- | --- | --- |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, ngày sinh | Xâm phạm riêng tư, thu thập hàng loạt, lừa đảo nhắm mục tiêu |
| Bí mật xác thực | Token đặt lại mật khẩu, session token, API key | Chiếm quyền hoặc truy cập trái phép |
| Dữ liệu bảo mật nội bộ | Điểm rủi ro, luật chống gian lận, trạng thái điều tra | Hỗ trợ né kiểm soát và suy đoán hoạt động bảo vệ |
| Dữ liệu kinh doanh | Giá vốn, biên lợi nhuận, điều khoản đối tác | Lộ thông tin cạnh tranh hoặc dữ liệu không thuộc bên gọi |
| Thông tin vận hành | Stack trace, tên máy chủ, đường dẫn file, câu truy vấn | Bộc lộ cấu trúc hệ thống và dữ liệu đi kèm lỗi |
| Dữ liệu quan hệ | Mã tenant, danh sách thành viên, liên kết tài khoản | Suy ra quan hệ hoặc mở rộng phạm vi thu thập |
| Dữ liệu tổng hợp | Tổng số kết quả, thống kê theo nhóm nhỏ | Suy ra sự tồn tại hoặc thuộc tính của cá nhân/tài nguyên |

Phân loại này cần bám vào hệ thống thực tế. Một email có thể được phép hiển thị trong một danh bạ nội bộ được quản trị, nhưng không có nghĩa mọi endpoint đều được trả email. Một mã định danh không có thông tin trực tiếp về con người vẫn có thể tạo khả năng liên kết giữa các tập dữ liệu.

Đặc biệt, không xem password hash hoặc token là “dữ liệu đã được bảo vệ nên có thể trả ra”. Password hash vẫn là vật liệu nhạy cảm; token có thể là bằng chứng truy cập. Việc frontend không sử dụng chúng không làm giảm trách nhiệm của API.

## 5. Ví dụ: đối tượng nội bộ không phải hợp đồng phản hồi

Giả sử một đối tượng đơn hàng nội bộ có hình dạng minh họa:

```json
{
  "orderId": "ord-1042",
  "customerId": "customer-demo-42",
  "status": "CONFIRMED",
  "totalAmount": "1250000",
  "currency": "VND",
  "supplierCost": "830000",
  "riskReview": {
    "score": 72,
    "internalNote": "Thông tin minh họa dành cho xử lý nội bộ"
  },
  "payment": {
    "methodLabel": "Thẻ",
    "cardLast4": "4242",
    "providerCredential": "<internal-only-placeholder>",
    "providerResponse": {
      "internalReference": "provider-demo-ref"
    }
  }
}
```

Các giá trị trên chỉ phục vụ minh họa, không phải credential thật. Vấn đề cần nhận ra là đối tượng trộn dữ liệu của nhiều mục đích: hiển thị cho khách hàng, vận hành thanh toán, quản lý chi phí và đánh giá rủi ro.

Với màn hình danh sách đơn hàng, hợp đồng phản hồi có thể chỉ cần:

```json
{
  "orderId": "ord-1042",
  "status": "CONFIRMED",
  "totalAmount": "1250000",
  "currency": "VND"
}
```

Một endpoint chi tiết đơn hàng có thể được phép trả thêm thông tin giao hàng hoặc trạng thái thanh toán theo chính sách. Một công cụ hỗ trợ nội bộ có thể có một biểu diễn khác. Không nên tạo một object lớn chứa mọi trường rồi trông chờ mỗi client tự dùng đúng phần của mình.

Điểm quan trọng không phải số lượng trường càng ít càng tốt một cách tuyệt đối. Phản hồi phải **đủ cho chức năng được phép** và **không vượt phạm vi đã xác định**.

## 6. Thiết kế biểu diễn đầu ra bằng danh sách cho phép

Một cách giảm rủi ro là định nghĩa kiểu đầu ra riêng cho từng chức năng hoặc nhóm quyền phù hợp, thay vì serialize entity lưu trữ hay object của SDK bên ngoài.

### 6.1. Vì sao danh sách chặn dễ bỏ sót?

Ví dụ quy tắc “serialize tất cả trừ password và token” có thể hoạt động hôm nay. Sau này entity được bổ sung `passwordResetSecret`, `fraudExplanation` hoặc một object lồng mới, chúng có thể tự xuất hiện trong response mà không ai sửa controller.

Danh sách chặn phụ thuộc việc đội phát triển luôn nhớ mọi trường nguy hiểm hiện tại và tương lai. Danh sách cho phép xác định những gì thực sự được công khai; thuộc tính nội bộ mới không tự tham gia hợp đồng phản hồi.

Một quy tắc có thể nghiệm thu là:

> Việc thêm thuộc tính vào mô hình lưu trữ hoặc dữ liệu từ nhà cung cấp không được tự động làm thay đổi tập trường công khai của API.

### 6.2. DTO riêng cho đầu ra

Ví dụ Java sau chỉ minh họa kiểu phản hồi cho danh sách đơn hàng. Các giá trị truyền vào phải được lấy sau khi hệ thống xác thực và kiểm tra quyền theo thiết kế.

```java
public final class OrderListItemResponse {
    private final String orderId;
    private final String status;
    private final String totalAmount;
    private final String currency;

    public OrderListItemResponse(
            String orderId,
            String status,
            String totalAmount,
            String currency) {
        this.orderId = orderId;
        this.status = status;
        this.totalAmount = totalAmount;
        this.currency = currency;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getStatus() {
        return status;
    }

    public String getTotalAmount() {
        return totalAmount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

Kiểu này không có trường `supplierCost`, `riskReview` hoặc `providerCredential`. Việc serializer xử lý đúng DTO giúp giữ hợp đồng rõ ràng, nhưng vẫn cần kiểm tra response thực tế: cấu hình serializer, lớp bọc, custom getter hoặc bộ chuyển đổi có thể ảnh hưởng đầu ra.

Annotation ẩn trường có thể là một lớp phòng vệ bổ sung, không nên là lý do để coi entity dùng chung đã trở thành hợp đồng phù hợp cho mọi endpoint. Nếu một trường cần xuất hiện trong luồng nội bộ nhưng không được xuất hiện ở API công khai, biểu diễn riêng thường giúp trách nhiệm dễ thấy hơn.

### 6.3. Tách quyền đọc với phép ánh xạ

Luồng xử lý nên thể hiện được cả hai quyết định:

```text
Request đã có danh tính được xác minh
    → kiểm tra quyền trên đối tượng và tenant
    → xác định biểu diễn được phép cho chức năng
    → lấy/ánh xạ đúng tập dữ liệu cần thiết
    → tạo DTO đầu ra
    → serialize và gửi response
```

DTO không thay thế bước kiểm tra quyền. Ngược lại, xác thực và phân quyền cũng không thay việc lựa chọn trường đầu ra.

## 7. Chính sách đọc thuộc tính theo ngữ cảnh

Một trường có thể được trả trong ngữ cảnh này nhưng không được trả ở ngữ cảnh khác. Cần mô hình hóa chính sách thay vì rải điều kiện ad hoc trong nhiều controller.

Ví dụ ma trận cho dữ liệu đơn hàng:

| Thuộc tính | Khách hàng xem danh sách của mình | Khách hàng xem chi tiết được phép | Nhân viên hỗ trợ được cấp đúng phạm vi |
| --- | --- | --- | --- |
| Mã đơn, trạng thái | Có | Có | Có |
| Tổng tiền, loại tiền | Có | Có | Có theo nhiệm vụ |
| Địa chỉ giao hàng đầy đủ | Không cần cho danh sách | Có nếu chức năng cần và chính sách cho phép | Chỉ khi nhiệm vụ hỗ trợ cần và được cấp |
| Thông tin thanh toán đã giảm thiểu | Không hoặc chỉ trạng thái | Theo hợp đồng chi tiết | Theo quyền được cấp |
| Giá vốn | Không | Không | Không chỉ vì có vai trò hỗ trợ |
| Chi tiết đánh giá gian lận | Không | Không | Theo quyền chuyên biệt, không mặc định |
| Credential nhà cung cấp | Không | Không | Không thuộc biểu diễn hỗ trợ thông thường |

Bảng này là ví dụ thiết kế, không phải một chính sách dùng được cho mọi doanh nghiệp. Dự án phải xác nhận từng ô theo nhu cầu và rủi ro của mình.

Quyền không nên chỉ phụ thuộc một nhãn role. Có thể phải xét quan hệ với đối tượng, tenant, nhiệm vụ được giao, trạng thái dữ liệu và mức xác thực. Một request không được tự khai `purpose=support` rồi nhận dữ liệu hỗ trợ nếu chưa có quyết định có thẩm quyền.

### Trường bị ẩn: bỏ hẳn, null hay giá trị giảm thiểu?

Các biểu diễn sau mang ý nghĩa khác nhau:

```json
{"orderId":"ord-1042"}
```

```json
{"orderId":"ord-1042","riskReview":null}
```

```json
{"orderId":"ord-1042","riskReview":"REDACTED"}
```

Một trường bị bỏ hẳn có thể phù hợp khi nó không thuộc schema của người gọi. Trường `null` có thể mang nghĩa “không có dữ liệu”, còn `REDACTED` có thể tiết lộ rằng dữ liệu có tồn tại nhưng bị che.

Không có một lựa chọn luôn đúng. Hợp đồng phải phân biệt rõ dữ liệu vắng mặt, không áp dụng và không được công khai, đồng thời cân nhắc liệu chính sự khác biệt đó có làm lộ thông tin cần bảo vệ hay không.

Không gửi giá trị thật trong một trường phụ như `rawValue`, `original` hoặc `debug` bên cạnh giá trị đã che. Việc che trên một thuộc tính không có ý nghĩa nếu cùng dữ liệu vẫn tồn tại ở nơi khác trong response.

## 8. Đối tượng lồng nhau, danh sách và mở rộng quan hệ

Lỗi trả dư thường không nằm ở các trường ngoài cùng dễ nhìn thấy, mà trong object con hoặc tập quan hệ được serialize tự động.

Ví dụ, API chỉ có `orderId`, `status` và `customer`, nhưng `customer` lại chứa email, địa chỉ, thiết lập bảo mật cùng danh sách tài khoản liên kết. Một kiểm tra chỉ đếm ba trường ở cấp root sẽ không nhận ra phạm vi dữ liệu thật sự.

Yêu cầu cần áp dụng đệ quy:

- Mỗi object con có tập trường được công khai rõ ràng.
- Mỗi phần tử trong array tuân thủ biểu diễn tương ứng.
- Quan hệ mở rộng cần kiểm tra quyền với tài nguyên liên quan.
- Không để cơ chế tự serialize quan hệ của ORM quyết định phạm vi dữ liệu công khai.
- Dữ liệu dạng map linh hoạt phải có chính sách riêng cho key và value, thay vì được coi là ngoại lệ không cần kiểm tra.

### `fields`, `include`, `expand` và lựa chọn do client gửi

Một API có thể cho client chọn các trường cần lấy hoặc yêu cầu mở rộng quan hệ. Đây là cơ chế tối ưu biểu diễn, không phải quyền vượt chính sách.

Một mô hình xử lý là:

```text
Trường được trả
    = tập trường hợp lệ của biểu diễn
      giao với tập trường bên gọi được phép đọc
      giao với lựa chọn hợp lệ của client nếu chức năng hỗ trợ lựa chọn
```

Hành vi với trường bị cấm cần được quy định: từ chối yêu cầu hay bỏ khỏi kết quả theo hợp đồng. Không để việc client đoán được tên `internalNote` hoặc gửi wildcard tự mở trường đó.

Không dùng trực tiếp tên trường do client gửi để tạo một phép truy vấn hoặc gọi reflection không kiểm soát. Ánh xạ lựa chọn sang danh mục trường được hỗ trợ giúp giữ cả quyền truy cập lẫn hợp đồng biểu diễn.

Trong API truy vấn linh hoạt, bao gồm kiểu API cho phép chọn trường sâu, quyết định quyền vẫn phải được thực thi ở phía server tại các điểm truy cập dữ liệu tương ứng. Client được chọn trường không có nghĩa client được cấp quyền đọc mọi trường có trong mô hình.

## 9. Schema đầu ra là một hợp đồng bảo mật

Schema giúp mô tả trường nào có thể xuất hiện và kiểu của chúng. Với API nhạy cảm, việc không cho phép thuộc tính ngoài schema có thể giúp phát hiện thay đổi vô tình.

Ví dụ một schema JSON cho item danh sách đơn hàng:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["orderId", "status", "totalAmount", "currency"],
  "properties": {
    "orderId": { "type": "string" },
    "status": { "type": "string" },
    "totalAmount": { "type": "string" },
    "currency": { "type": "string" }
  }
}
```

Ví dụ này chỉ minh họa tập trường và kiểu dữ liệu. Những ràng buộc giá trị, phiên bản schema và cách kiểm tra cụ thể cần theo công cụ của dự án.

Một số điểm phải làm rõ:

1. Schema mô tả chính xác biểu diễn cho endpoint và nhóm chủ thể nào.
2. Những object con có kiểm soát thuộc tính ngoài schema ở chính mức của chúng; một ràng buộc ở root không tự áp dụng cho mọi object lồng nhau.
3. Việc khai báo schema không tự bảo đảm framework sẽ lọc response theo schema.
4. Kiểm tra schema chỉ có giá trị bảo mật khi tập trường được duyệt thực sự đúng chính sách.
5. Nếu có nhiều biến thể phản hồi, mỗi biến thể phải có điều kiện chọn và schema tương ứng.

Không tự động sinh schema từ một entity quá rộng rồi dùng schema đó để chứng minh API không trả dư. Nếu cả implementation và schema cùng lấy một mô hình sai, kiểm tra có thể PASS nhưng thông tin vẫn bị lộ.

### Kiểm tra sự vắng mặt của trường ngoài hợp đồng

Một bài kiểm tra chỉ xác nhận `orderId` và `status` có mặt sẽ không phát hiện `providerCredential` xuất hiện thêm. Với những endpoint cần kiểm soát chặt, nên kiểm tra cả tập trường thực tế và cấu trúc lồng nhau sau parse.

Việc thêm trường vào API có thể là thay đổi chức năng hợp lệ, nhưng vẫn cần được xem xét về dữ liệu, quyền và các client có liên quan. “Thêm field không làm client cũ lỗi” không đồng nghĩa “thêm field không tạo rủi ro bảo mật”.

## 10. Những đường xuất dữ liệu dễ bị bỏ sót

### 10.1. Response lỗi và phản hồi validation

Một lỗi validation có thể vô tình trả lại toàn bộ request body, gồm dữ liệu cá nhân hoặc credential. Một lỗi tích hợp có thể trả nguyên response từ nhà cung cấp chứa thông tin chỉ dành cho server.

Yêu cầu cần xác định schema lỗi công khai, những thông tin được phép đưa vào và cách liên hệ sự kiện qua request ID. Không cần gửi stack trace hoặc cấu trúc nội bộ để client biết thao tác thất bại.

Khi một trường đầu vào có lỗi, không mặc định rằng có thể echo giá trị ấy. Có thể chỉ cần tên trường cùng mã lỗi an toàn theo hợp đồng.

### 10.2. Danh sách, tìm kiếm và kết quả tổng hợp

Endpoint danh sách phải áp dụng cả phạm vi hàng và phạm vi trường. Phân trang chỉ giới hạn lượng dữ liệu mỗi lần gọi; nó không làm một tập dữ liệu trái phép trở thành được phép.

Tổng số kết quả, gợi ý tìm kiếm hoặc thông báo “tài khoản đã tồn tại” có thể làm lộ sự tồn tại của dữ liệu. Cần xác định liệu người gọi có được biết thông tin đó hay không, thay vì chỉ kiểm tra item trong body.

Với thống kê của nhóm nhỏ, một con số tổng hợp có thể hỗ trợ suy ra thông tin cá nhân, đặc biệt khi client thay đổi bộ lọc và so sánh nhiều lần. Việc bỏ tên khỏi response không tự loại bỏ rủi ro suy luận.

### 10.3. Export, báo cáo và tác vụ bất đồng bộ

Một màn hình có thể được giới hạn tốt trong khi nút export dùng truy vấn rộng hơn và trả nhiều cột hơn. Cần áp dụng chính sách dữ liệu cho file xuất và mọi tài nguyên được tạo bởi job, không chỉ endpoint tạo job.

Đặc tả phải nêu thời điểm kiểm tra quyền: khi yêu cầu tạo báo cáo, khi job chạy và khi tải kết quả. Nếu quyền bị thu hồi hoặc phạm vi tenant thay đổi giữa các thời điểm đó, hệ thống cần hành vi xác định.

Đường dẫn tải hoặc URL có chữ ký là một phần của cơ chế cấp quyền truy cập dữ liệu. Cần xét phạm vi, thời hạn, khả năng chia sẻ lại và người nhận. Không coi một URL dài khó đoán là chính sách quyền đầy đủ cho mọi trường hợp.

### 10.4. Webhook, event và API dành cho đối tác

Payload gửi sang hệ thống bên ngoài cũng là đầu ra. Một event chứa toàn bộ entity có thể phát tán dữ liệu vượt nhu cầu của từng bên nhận.

Mỗi loại thông điệp cần hợp đồng và danh sách trường riêng, cùng quy tắc ai được đăng ký hoặc nhận thông điệp đó. Không mặc định rằng hệ thống đối tác cần biết mọi trường chỉ vì được tích hợp với một chức năng.

### 10.5. Header và metadata

Một body đã giảm thiểu vẫn có thể đi kèm header chứa email, mã nội bộ, đường dẫn vận hành hoặc thông tin debug. `Location`, link quan hệ, metadata phân trang và giá trị đặt tên file cũng cần được xét theo hợp đồng công khai.

Không được xem body JSON là toàn bộ ranh giới dữ liệu của một response.

## 11. Cache có thể phát tán một phản hồi đúng tới sai người

Giả sử API tạo response chi tiết đúng quyền cho nhân viên hỗ trợ. Nếu cache dùng chung chỉ lấy URL làm key, khách hàng gọi cùng URL có thể nhận lại biểu diễn có nhiều trường hơn quyền của họ.

Đây là lý do cần xét danh tính và ngữ cảnh biểu diễn tại các tầng cache, không chỉ trong hàm tạo DTO.

Các yêu cầu có thể bao gồm:

- Response theo người dùng hoặc quyền không được cache công khai nếu chính sách không cho phép.
- Cache key và chiến lược phân vùng phản ánh những đầu vào thực sự làm thay đổi quyền và biểu diễn.
- Không tái sử dụng response giữa tenant hoặc giữa nhóm quyền không tương đương.
- Có hành vi xác định khi quyền thay đổi trong thời gian response còn được lưu.
- Các đường cache tại gateway, CDN, reverse proxy và ứng dụng đều được xem xét.

Với dữ liệu không được phép lưu vào cache theo chính sách, cần cấu hình phù hợp, chẳng hạn `Cache-Control: no-store` ở những response thuộc phạm vi đó. `private` và `no-cache` có ý nghĩa khác: chúng không phải cách nói thay thế rằng response tuyệt đối không được lưu.

Một header `Vary` không tự chứng minh mọi cache trong hệ thống phân vùng dữ liệu đúng. Cần kiểm tra cấu hình và hành vi thực tế của các thành phần tham gia, bao gồm trường hợp cache tùy biến ở ứng dụng.

## 12. Masking, hashing và giới hạn của việc biến đổi dữ liệu

Giảm chi tiết có thể giúp đáp ứng một mục đích cụ thể. Ví dụ, màn hình chọn phương thức thanh toán chỉ cần nhãn và một phần số hiển thị thay vì dữ liệu thanh toán đầy đủ.

Tuy nhiên, biến đổi dữ liệu không tự đồng nghĩa với vô danh hoặc được phép công khai.

| Cách biến đổi | Điều có thể đạt | Điều không nên suy ra |
| --- | --- | --- |
| Che một phần số điện thoại hoặc email | Giảm chi tiết hiển thị theo mục đích | Không thể nhận diện người dùng khi kết hợp dữ liệu khác |
| Băm một giá trị có không gian nhỏ hoặc dễ đoán | Thay biểu diễn của giá trị | Không ai có thể đoán bằng cách thử các giá trị ứng viên |
| Dùng mã định danh giả | Tách tên trực tiếp khỏi một số luồng | Không thể liên kết hoạt động giữa các lần gọi |
| Làm tròn hoặc tổng hợp | Giảm độ chi tiết của số liệu | Không thể suy luận qua nhóm nhỏ hoặc nhiều truy vấn |
| Base64 hoặc encoding khác | Chuyển định dạng biểu diễn | Bảo mật nội dung hoặc kiểm soát người được đọc |

Chính sách cần nêu trường nào được trả dưới dạng giảm thiểu, thuật toán hoặc quy tắc biến đổi có ý nghĩa gì với chức năng và các dữ liệu đi kèm có làm mất tác dụng của việc che hay không.

Ví dụ, che email ở `contactSummary` nhưng trả email gốc trong `customer.email` không đáp ứng mục tiêu. Tương tự, không nên trả một token mã hóa có thể được hệ thống khác dùng trực tiếp làm credential chỉ vì client không đọc được nội dung bên trong.

## 13. Giảm thiểu dữ liệu từ nguồn tới response

Lọc đầu ra là ranh giới bắt buộc, nhưng lấy ít dữ liệu hơn từ đầu cũng có thể giảm khả năng vô tình đưa dữ liệu vào log, bộ nhớ trung gian hoặc object dùng chung.

Ví dụ, truy vấn danh sách đơn hàng có thể chỉ lấy các cột cần cho item danh sách, đồng thời áp dụng điều kiện chủ sở hữu và tenant. Sau đó, dữ liệu được ánh xạ vào DTO đã xác định.

Những trách nhiệm cần tách rõ:

1. Điều kiện truy vấn giới hạn tài nguyên thuộc phạm vi được phép.
2. Projection hoặc phép chọn dữ liệu giảm lượng thông tin nội bộ được nạp khi phù hợp.
3. DTO và chính sách trường quyết định biểu diễn công khai.
4. Serializer tạo đúng định dạng mà không tự mở rộng object nội bộ.

Không chỉ bỏ cột nhạy cảm khỏi một truy vấn rồi mặc định mọi đường response khác đều an toàn. Một đường fallback, một lần enrich từ dịch vụ khác hoặc một object lồng được thêm sau đó vẫn có thể đưa thông tin ngoài hợp đồng vào đầu ra.

Tương tự, không log nguyên entity trước khi ánh xạ DTO để “dễ debug”. Dữ liệu không đi vào body có thể vẫn bị phát tán qua log hoặc trace. Chính sách dữ liệu và quyền truy cập các kênh quan sát cần được xác định riêng.

## 14. Mẫu yêu cầu bảo mật có thể nghiệm thu

Ví dụ dưới đây áp dụng cho API đơn hàng. Mỗi yêu cầu cần được gắn với endpoint, chủ thể, mục đích và chủ sở hữu triển khai cụ thể trong dự án.

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| DATA-OUT-01 | Mỗi biểu diễn phản hồi có danh sách trường được phép, bao gồm object con, array và metadata | Đối chiếu response thực tế với hợp đồng đã duyệt ở các độ sâu |
| DATA-OUT-02 | Không serialize trực tiếp entity nội bộ hoặc object nhà cung cấp ra API công khai ngoài hợp đồng | Kiểm tra đường tạo phản hồi và thử thêm trường nội bộ vào nguồn dữ liệu kiểm thử |
| DATA-OUT-03 | Quyền đọc thuộc tính được thực thi phía server theo danh tính và ngữ cảnh có thẩm quyền | Cùng tài nguyên, các chủ thể và nhiệm vụ khác nhau nhận đúng biểu diễn |
| DATA-OUT-04 | Client không thể yêu cầu trường bị cấm bằng `fields`, `include`, `expand` hoặc wildcard | Gửi lựa chọn trường không được phép và kiểm tra hành vi đã công bố |
| DATA-OUT-05 | Response lỗi không chứa credential, dữ liệu nội bộ hoặc giá trị đầu vào nhạy cảm ngoài schema lỗi | Gây lỗi validation, lỗi tích hợp và lỗi bất ngờ bằng dữ liệu kiểm thử dễ nhận diện |
| DATA-OUT-06 | Danh sách, tìm kiếm, tổng số và thống kê chỉ phản ánh phạm vi được phép | Đối chiếu kết quả giữa chủ thể/tenant và kiểm tra thông tin về sự tồn tại |
| DATA-OUT-07 | Export, báo cáo, webhook và file tải xuống áp dụng chính sách đầu ra tương ứng | Kiểm tra payload/file thực tế, người nhận và thời điểm quyết định quyền |
| DATA-OUT-08 | Cache không trả biểu diễn của một chủ thể hoặc nhóm quyền sang phạm vi khác | Làm nóng cache bằng người có quyền cao rồi gọi bằng người có quyền thấp và tenant khác |
| DATA-OUT-09 | Trường bị che hoặc giảm thiểu không xuất hiện ở dạng gốc trong vị trí khác của cùng phản hồi | Quét toàn bộ body, object lồng, header và đường dẫn liên quan |
| DATA-OUT-10 | Thuộc tính nội bộ mới không tự xuất hiện trong hợp đồng API | Thay đổi fixture/mô hình nguồn trong kiểm thử hợp đồng và so sánh tập trường đầu ra |
| DATA-OUT-11 | API cũ hoặc biến thể endpoint không duy trì một đường trả dữ liệu rộng hơn chính sách | Kiểm kê phiên bản, route thay thế, method và kiểu nội dung được hỗ trợ |
| DATA-OUT-12 | Dữ liệu quan sát được giảm thiểu và không ghi toàn bộ object nhạy cảm theo mặc định | Kiểm tra log/trace của luồng thành công và lỗi theo quyền đọc dữ liệu quan sát |

“Không có dữ liệu nhạy cảm” là một tiêu chí quá chung nếu chưa định nghĩa dữ liệu nào nhạy cảm với ai. Danh sách trường và ma trận ngữ cảnh làm yêu cầu trở nên có thể đánh giá được.

## 15. Kịch bản chấp nhận minh họa

### 15.1. Khách hàng xem danh sách đơn hàng

```text
Given:
  Khách hàng A được xác thực.
  Danh sách chỉ được phép chứa đơn hàng thuộc phạm vi của A.
  Item danh sách có các trường orderId, status, totalAmount và currency.
  Dữ liệu nội bộ của đơn có supplierCost, riskReview và payment.

When:
  A gọi endpoint danh sách đơn hàng theo hợp đồng.

Then:
  Chỉ có các đơn hàng trong phạm vi được phép.
  Mỗi item chỉ chứa tập trường của biểu diễn danh sách.
  Không có dữ liệu nội bộ trong object con, metadata hoặc header.
  Giao diện có render hết body hay không không làm thay đổi kết quả kiểm tra.
```

### 15.2. Entity được bổ sung trường nội bộ

```text
Given:
  API đang sử dụng biểu diễn danh sách đã duyệt.
  Nguồn dữ liệu kiểm thử có thêm trường internalAuditNote.

When:
  API tạo phản hồi từ dữ liệu đó.

Then:
  internalAuditNote không xuất hiện trong response.
  Tập trường công khai không tự thay đổi theo mô hình nguồn.
```

### 15.3. Client yêu cầu mở rộng trường bị cấm

```text
Given:
  Khách hàng không có quyền đọc riskReview.
  Endpoint có hỗ trợ lựa chọn trường hoặc mở rộng quan hệ.

When:
  Client yêu cầu riskReview hoặc một wildcard bao gồm trường này.

Then:
  Trường bị cấm không được trả về.
  API xử lý lựa chọn không hợp lệ đúng hợp đồng đã công bố.
  Không có đường mở rộng lồng nhau dẫn tới cùng dữ liệu.
```

### 15.4. Cache được làm nóng bởi một người có quyền rộng hơn

```text
Given:
  Người dùng S có quyền nhận biểu diễn hỗ trợ trong đúng phạm vi.
  Khách hàng A chỉ được nhận biểu diễn khách hàng.
  Cả hai gọi một tài nguyên qua đường có cache thuộc phạm vi kiểm tra.

When:
  S gọi trước, sau đó A gọi.

Then:
  A chỉ nhận biểu diễn được phép của A.
  A không nhận trường nội bộ từ response đã được tạo cho S.
  Hành vi vẫn đúng khi đổi thứ tự gọi và khi gọi từ tenant khác.
```

## 16. Thiết kế bằng chứng kiểm chứng

Bằng chứng cần quan sát dữ liệu đã vượt ranh giới API, không chỉ mô hình trong bộ nhớ hoặc ảnh giao diện.

| Mức kiểm tra | Điều cần xác nhận |
| --- | --- |
| HTTP response | Body, header, mã trạng thái và tài nguyên được liên kết đúng hợp đồng |
| Cấu trúc sau parse | Tập trường, kiểu, object con và array không chứa dữ liệu ngoài danh mục |
| Chủ thể và ngữ cảnh | Các vai trò, quan hệ đối tượng, tenant và nhiệm vụ tạo đúng biểu diễn |
| Đường truy cập khác | Danh sách, chi tiết, tìm kiếm, export, lỗi và phiên bản cũ cùng giữ chính sách |
| Cache và tác vụ chậm | Dữ liệu không bị tái sử dụng sai người hoặc sai thời điểm quyền |
| Kênh quan sát | Log và trace không chứa dữ liệu bị loại khỏi đầu ra theo chính sách của chúng |

Nên dùng dữ liệu tổng hợp có dấu hiệu dễ nhận diện cho trường không được phép, chẳng hạn một chuỗi đánh dấu riêng trong `internalNote`. Điều đó giúp phát hiện đường rò rỉ trong kiểm thử mà không dùng dữ liệu cá nhân hay credential thật.

Cần kiểm tra cả trường hợp âm: trường cấm không có mặt. Nếu dữ liệu đã được biến đổi, việc tìm chuỗi đánh dấu đơn thuần có thể không đủ; phải kiểm tra cấu trúc và ý nghĩa của các biểu diễn liên quan. Một trường đã chuyển Base64 vẫn có thể chứa cùng dữ liệu không được phép.

Không tự động cập nhật snapshot response sau khi thấy test thay đổi mà bỏ qua việc xem xét trường mới. Snapshot chỉ có giá trị khi thay đổi tập dữ liệu công khai được đánh giá theo chính sách.

### Thất bại trong phép chiếu hoặc kiểm tra chính sách

Nếu không xác định được biểu diễn được phép hoặc phép ánh xạ thất bại, hệ thống không được fallback sang serialize nguyên entity. Cần trả lỗi có kiểm soát theo hợp đồng, đồng thời bảo đảm lỗi đó không chứa chính dữ liệu vừa được bảo vệ.

Tương tự, không bật debug output công khai chỉ vì một endpoint gặp lỗi ở môi trường triển khai. Khả năng chẩn đoán nên đi qua kênh quan sát được phân quyền, với dữ liệu phù hợp.

## 17. Những ngộ nhận cần tránh

### “Người dùng đã đăng nhập nên có thể nhận toàn bộ object”

Đăng nhập thiết lập danh tính. Quyền trên tài nguyên và thuộc tính còn phụ thuộc chính sách. Ngay cả người sở hữu một tài nguyên cũng không mặc nhiên được xem dữ liệu nội bộ được gắn vào tài nguyên ấy.

### “Chỉ có một client chính thức nên response dư không sao”

Bên gọi có thể quan sát và tự tạo request. Hợp đồng bảo mật của server không được dựa vào việc client chính thức có nút hiển thị dữ liệu hay không.

### “Chỉ cần bỏ password và token”

Dữ liệu cần bảo vệ còn gồm thông tin cá nhân, dữ liệu kinh doanh, quan hệ, thông tin vận hành và dữ liệu suy luận được. Danh sách chặn một vài tên trường không đủ mô tả phạm vi đó.

### “Masking đồng nghĩa vô danh”

Một phần dữ liệu vẫn có thể nhận diện hoặc liên kết khi kết hợp với thông tin khác. Quy tắc che phải phục vụ một mục đích cụ thể và được xem xét cùng toàn bộ response.

### “Schema có khai báo nên framework sẽ tự lọc”

Khả năng kiểm tra hoặc lọc phụ thuộc implementation và cấu hình. Cần quan sát response thực tế; tài liệu schema tự nó không thực thi quyền.

### “Endpoint chính đã sửa thì toàn bộ hệ thống đã hết lộ”

Một route cũ, file export hoặc webhook có thể dùng cùng mô hình nhưng tạo output khác. Yêu cầu cần theo các đường xuất dữ liệu của chức năng, không chỉ một controller dễ thấy.

## 18. Gắn giảm thiểu dữ liệu với vòng đời phát triển

Khi thêm một trường vào API, nhóm cần xác định ai cần đọc trường đó, phục vụ chức năng nào, quyền được kiểm tra ở đâu và dữ liệu có đi qua cache, export hoặc hệ thống bên ngoài hay không. Câu trả lời nên được thể hiện trong biểu diễn đầu ra cùng tiêu chí chấp nhận, thay vì để thành giả định trong giao diện.

Khi thay đổi entity nội bộ, hợp đồng công khai phải giữ ổn định trừ khi có quyết định thay đổi API. Khi mở một phiên bản mới hoặc một quan hệ mở rộng, chính sách trường phải được áp dụng cho đường đi mới. Khi đóng một endpoint cũ, cần xác nhận những đường xuất dữ liệu liên quan cũng được xử lý theo kế hoạch.

Thiết kế đạt mục tiêu khi API trả đủ dữ liệu cho tác vụ được phép, chủ thể không thể mở rộng tập trường bằng request tự khai và mọi đường phản hồi đều giữ cùng ranh giới dữ liệu đã xác định. Việc hiển thị ít thông tin trên màn hình chỉ là kết quả trình bày; quyền nhận dữ liệu phải được quyết định trước khi response đến client.
