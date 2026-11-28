# Opaque token

Opaque token là token mà bên sử dụng không dựa vào cấu trúc bên trong để diễn giải thông tin. Trong kiến trúc API, thuật ngữ này thường chỉ một chuỗi khó đoán đóng vai trò tham chiếu đến ngữ cảnh ủy quyền được quản lý phía máy chủ. Client nhận chuỗi đó rồi trình cho API; API dùng một cơ chế đáng tin cậy để biết token còn hiệu lực và cho phép những thao tác nào.

Đặc tính opaque không có nghĩa token đã được mã hóa, cũng không có nghĩa token bị lộ thì vô hại. Để hiểu cách bảo vệ hệ thống IAM, cần tách định dạng token, cách kiểm tra token và quyết định phân quyền.

## 1. Token đại diện cho một ngữ cảnh truy cập

Giả sử ứng dụng báo cáo cần đọc hóa đơn của một người dùng. Authorization Server (AS) cấp access token với quyền đọc; Resource Server (RS), tức API hóa đơn, thực thi quyền truy cập.

Ví dụ chuỗi token giả dùng trong bài:

```text
ot_demo_R7kQ2mV9xN4cL8sT6pA3
```

Chuỗi này chỉ để minh họa, không phải token thật hay ví dụ về độ ngẫu nhiên đạt yêu cầu sản xuất. Client không tách chuỗi để tìm `userId`, quyền hoặc ngày hết hạn. Token có thể trông khác hoàn toàn sau khi AS thay đổi cách phát hành, trong khi hợp đồng sử dụng access token vẫn giữ nguyên.

[RFC 6749, mục 1.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.4) mô tả access token là chứng thư truy cập và cho phép cả kiểu tham chiếu lẫn kiểu chứa thông tin có thể xác minh. Vì vậy, OAuth 2.0 không bắt buộc access token phải là JWT.

Trong bài này, kiến trúc chính là opaque access token dạng tham chiếu. Một cách triển khai điển hình lưu phía AS các thông tin liên quan đến token như chủ thể, client, quyền, tài nguyên đích, thời hạn và trạng thái thu hồi.

## 2. Phân biệt ba khái niệm độc lập

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| Định dạng | Token có được bên nhận diễn giải trực tiếp không? | Opaque hoặc định dạng JWT |
| Cách sử dụng | Người gửi cần trình token hay phải chứng minh thêm việc giữ khóa? | Bearer hoặc sender-constrained |
| Cách kiểm tra | API xác định tính hợp lệ bằng cách nào? | Tra cứu nội bộ, introspection hoặc xác minh cục bộ phù hợp định dạng |

Với bearer token, bên giữ token có thể dùng nó mà không phải chứng minh sở hữu một khóa mật mã riêng. Do đó phải bảo vệ token khi truyền và lưu trữ. Đây là ngữ nghĩa của bearer trong [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html).

Các kết luận cần tránh:

- Không đọc được nội dung không đồng nghĩa với không thể sử dụng token bị đánh cắp.
- Chuỗi có dạng JWT không đồng nghĩa chữ ký đã hợp lệ.
- Chọn opaque không tự tạo ra MFA, giới hạn tenant hay quyền ít nhất.
- Introspection không chỉ dành riêng cho chuỗi ngẫu nhiên; cách API kiểm tra token là một quyết định kiến trúc.

## 3. Luồng truy cập qua introspection

Token introspection là giao thức để API hỏi AS về trạng thái và metadata của token. Endpoint phải được bảo vệ; API cần được phép thực hiện truy vấn. Theo [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html#section-2), phản hồi có trường Boolean `active`; những trường như `scope`, `client_id`, `sub`, `aud`, `iss`, `exp` là tùy chọn trong giao thức cơ sở.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Authorization Server
    participant R as API hóa đơn
    C->>A: Hoàn tất luồng cấp token phù hợp
    A-->>C: Access token opaque
    C->>R: Yêu cầu API kèm access token
    R->>A: Introspection với xác thực của API
    A-->>R: Trạng thái và metadata được phép công bố
    R->>R: Kiểm tra quyền và điều kiện nghiệp vụ
    R-->>C: Dữ liệu hoặc kết quả từ chối
```

Yêu cầu tới API có thể dùng header:

```http
GET /invoices/inv-203 HTTP/1.1
Host: api.example.org
Authorization: Bearer ot_demo_R7kQ2mV9xN4cL8sT6pA3
```

Phản hồi introspection giả định trong ví dụ:

```json
{
  "active": true,
  "client_id": "reporting-app",
  "sub": "user-42",
  "scope": "invoices:read",
  "aud": "https://api.example.org/invoices",
  "iss": "https://auth.example.org",
  "exp": 1893456000
}
```

Các giá trị trên là dữ liệu minh họa. `exp` là mốc thời gian theo giây Unix, không phải thời lượng sống còn lại. Một phản hồi `active: false` có thể được trả về với HTTP 200; vì vậy HTTP thành công không đủ để kết luận token dùng được.

API không lấy URL introspection từ token do người gửi cung cấp. Endpoint và thông tin xác thực cần đến từ cấu hình tin cậy của kết nối. Với hệ thống nhiều AS, phải có cách chọn kết nối được kiểm soát, không gửi thử token đến tùy ý nhiều máy chủ.

## 4. Active chưa phải là được phép làm mọi việc

Trong ví dụ, `active: true` chỉ là một đầu vào cho quyết định truy cập. Ứng dụng vẫn cần kiểm tra yêu cầu cụ thể. Những câu hỏi sau là thiết kế đề xuất cho API hóa đơn:

1. Token có dành cho API hóa đơn theo hợp đồng với AS không?
2. Yêu cầu có cần `invoices:read`, và token có scope đó không?
3. Chủ thể có được xem hóa đơn `inv-203` không?
4. Hóa đơn có thuộc tenant mà chủ thể được phép truy cập không?
5. Có điều kiện nghiệp vụ bổ sung như tài khoản bị khóa hoặc hồ sơ đang bị hạn chế không?

Ví dụ, token của `user-42` có quyền đọc hóa đơn nhưng `inv-203` thuộc khách hàng khác. API phải từ chối nếu không có quan hệ truy cập phù hợp. Scope là quyền theo phạm vi đã định nghĩa, không thay thế kiểm tra quyền trên từng đối tượng.

[RFC 9700, mục 2.3](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.3) khuyến nghị giới hạn đặc quyền và tài nguyên đích của access token; resource server phải từ chối token không dành cho mình. Khi introspection không trả về `aud`, kiến trúc vẫn phải có cơ chế xác lập ràng buộc tài nguyên theo hợp đồng với AS. Không được tự hiểu thiếu audience là có quyền gọi mọi API.

Một mã giả cho tầng ứng dụng:

```text
context = tokenVerifier.verify(request.accessToken)
require context.isActive
require context.isIntendedFor(INVOICE_API)
require context.hasScope("invoices:read")
require policy.canReadInvoice(context.principal, invoice)
return invoice
```

`tokenVerifier` ở đây bao gồm việc liên lạc với bên tin cậy, xử lý thời hạn và kiểm tra hợp đồng token. Nó không phải hàm chỉ kiểm tra chuỗi có tồn tại trong cache.

## 5. Liên hệ với triển khai Java

Trong Spring Security, Resource Server có hỗ trợ xác thực opaque bearer token bằng introspection: gửi token đến endpoint được cấu hình, kiểm tra `active` và ánh xạ scope thành authority với tiền tố `SCOPE_`. Tài liệu cũng mô tả khả năng dùng introspection cho token có định dạng JWT. Xem [Spring Security: Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).

Điều này giúp tách hai trách nhiệm:

- Cơ chế xác thực token tạo ra principal và các thuộc tính/authority được tin cậy theo cấu hình.
- Chính sách ứng dụng quyết định principal được thực hiện thao tác nào trên dữ liệu nào.

Ví dụ, authority `SCOPE_invoices:read` có thể là điều kiện ở cấp endpoint. Kiểm tra chủ sở hữu hóa đơn và ranh giới tenant vẫn thuộc chính sách truy cập của ứng dụng. Không tự giả định bật hỗ trợ opaque token là đã có đủ mọi kiểm tra nghiệp vụ hoặc audience mong muốn.

## 6. Opaque token và JWT: khác biệt vận hành

So sánh sau giả định opaque token dạng tham chiếu được introspect, còn JWT access token được API xác minh cục bộ:

| Khía cạnh | Opaque dạng tham chiếu | JWT xác minh cục bộ |
|---|---|---|
| Nơi lấy ngữ cảnh token | AS hoặc thành phần tra cứu tin cậy | Claims trong token đã được xác minh |
| Phụ thuộc khi có yêu cầu | Thường cần tra cứu hoặc cache | Thường không cần introspect từng yêu cầu |
| Thay đổi trạng thái | Có thể phản ánh qua lần tra cứu mới | Cần cơ chế bổ sung nếu muốn phát hiện trước khi token hết hạn |
| Thông tin trong chuỗi trình cho API | Thường không lộ trực tiếp metadata | JWT ký thông thường có payload đọc được; ký không phải mã hóa |
| Gánh nặng vận hành | Độ sẵn sàng, độ trễ và tải của dịch vụ tra cứu | Quản lý trust, khóa và quy tắc xác minh token |

[RFC 9068](https://www.rfc-editor.org/rfc/rfc9068.html) chuẩn hóa một profile JWT access token với claims và quy tắc xác minh tương ứng. JWT không có nghĩa là tự động đáng tin hay được phép truy cập chỉ vì giải mã được payload.

Không có kết luận chung rằng một định dạng luôn an toàn hoặc nhanh hơn trong mọi hệ thống. Nếu hệ thống cần kiểm soát trạng thái tập trung và có hạ tầng tra cứu ổn định, opaque dạng tham chiếu là một lựa chọn phù hợp để đánh giá. Nếu API cần giảm phụ thuộc trực tuyến, có thể đánh giá mô hình JWT cùng chiến lược thời hạn và thu hồi tương ứng.

## 7. Cache tạo ra một cửa sổ dữ liệu cũ

Introspection mỗi yêu cầu làm tăng tải và độ trễ. Cache giúp giảm chi phí đó nhưng có thể giữ kết quả hợp lệ sau khi token đã bị thu hồi. RFC 7662 yêu cầu cân nhắc đánh đổi này và không cache vượt thời điểm `exp` nếu phản hồi có trường đó. Xem [RFC 7662, mục 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-4).

Giả sử một thiết kế chọn TTL cache là 30 giây:

| Thời điểm | Sự kiện |
|---|---|
| 10:00:00 | API introspect, nhận active và cache kết quả |
| 10:00:05 | AS đánh dấu token bị thu hồi |
| 10:00:10 | API dùng kết quả cache cũ và có thể vẫn chấp nhận |
| 10:00:30 | Cache hết hạn; lần kiểm tra mới thấy token không còn active |

Trong giả định này, thu hồi tại AS không đồng nghĩa mọi API từ chối ngay lập tức. Đồng bộ trạng thái giữa các nút hoặc thành phần trung gian còn có thể làm thay đổi thời gian quan sát thực tế.

Một công thức thiết kế minh họa khi biết thời điểm hết hạn:

```text
cacheDeadline = min(now + configuredTTL, tokenExpiration)
```

Giá trị TTL phải xuất phát từ mục tiêu thu hồi quyền và mức chấp nhận rủi ro, không chỉ từ mong muốn giảm số lần gọi. Với thao tác đặc quyền, có thể cần TTL ngắn hơn hoặc không dùng cache cho quyết định đó.

Khóa cache nên gắn với token và ngữ cảnh kiểm tra như kết nối AS, danh tính API gọi introspection và tài nguyên đích. Không dùng một kết quả lấy cho API A làm bằng chứng mặc định để cấp quyền tại API B.

## 8. Thu hồi token khác với xóa token ở client

[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html) định nghĩa endpoint thu hồi token. Mức tác động đến các token liên quan còn phụ thuộc loại token và chính sách AS; không suy ra rằng thu hồi một token luôn xóa mọi phiên và mọi token của người dùng.

Với hệ thống minh họa, cần phân biệt:

| Thao tác | Điều nó trực tiếp thay đổi |
|---|---|
| Xóa token khỏi một thiết bị | Bản sao token ở thiết bị đó |
| Thu hồi access token tại AS | Trạng thái mà AS dùng để đánh giá token |
| Thu hồi refresh token hoặc grant | Khả năng tiếp tục lấy token theo chính sách tương ứng |
| Đóng phiên ứng dụng | Phiên do ứng dụng quản lý |
| Khóa tài khoản và thu hồi quyền | Trạng thái danh tính và chính sách; cần được truyền tới các điểm thực thi |

Nếu kẻ khác đã sao chép bearer token, việc client xóa bản của mình không thu hồi được bản đã bị sao chép. Quy trình offboarding vì thế cần xác định rõ sẽ cập nhật những trạng thái nào, khi nào API nhận biết và những phiên nào còn tồn tại.

## 9. Thiết kế kho token và bảo vệ token

Đối với opaque token dạng tham chiếu tự triển khai, một phương án là sinh giá trị bằng bộ sinh số ngẫu nhiên mật mã và ánh xạ sang bản ghi phía máy chủ. Chẳng hạn, đội thiết kế có thể chọn đầu vào ngẫu nhiên 256 bit rồi mã hóa base64url; đây là ví dụ lựa chọn kỹ thuật, không phải quy định chung cho mọi opaque token.

Các nguyên tắc thiết kế đề xuất:

- Không ghép token từ mã người dùng, số thứ tự hay thời gian dễ dự đoán.
- Bản ghi cần thể hiện rõ loại token, tài nguyên, quyền, thời hạn và trạng thái.
- Nếu chỉ cần tra cứu đối chiếu, cân nhắc lưu digest hoặc HMAC thay vì token thô; vẫn phải bảo vệ cơ sở dữ liệu và khóa HMAC nếu có.
- Không ghi token thô vào log, trace, thông báo lỗi hay nhãn metric.
- Giới hạn số lượng và kích thước đầu vào để tránh biến tra cứu token thành nguồn gây cạn tài nguyên.

Digest trong kho không làm token đang lưu tại client mất khả năng bị sử dụng khi lộ. Tương tự, HTTPS bảo vệ quá trình truyền nhưng không sửa được việc ứng dụng chủ động đưa token vào báo cáo lỗi. RFC 6750 khuyến nghị dùng header Authorization và mô tả rủi ro token trong URI, nơi dễ bị lưu vào log. Xem [RFC 6750, mục 2 và 5](https://www.rfc-editor.org/rfc/rfc6750.html).

## 10. Xử lý lỗi mà không cấp quyền ngoài ý muốn

Đây là chính sách vận hành đề xuất cho API hóa đơn:

| Tình huống | Hướng xử lý |
|---|---|
| Introspection trả `active: false` | Từ chối token; không tự suy đoán quyền từ phần khác của chuỗi |
| Token active nhưng thiếu scope | Từ chối thao tác theo chính sách phân quyền |
| Token dành cho API khác | Từ chối yêu cầu tại API hóa đơn |
| Timeout, lỗi TLS hoặc phản hồi hỏng | Không coi là active; phân biệt sự cố hạ tầng với token không hợp lệ trong quan sát vận hành |
| Credential introspection của API hết hiệu lực | Xử lý lỗi cấu hình và luân chuyển credential, không bỏ qua xác minh |
| Cache đã hết hạn mà AS chưa phục hồi | Không tự kéo dài cache vô hạn để cho truy cập |

Fail closed trong tình huống không thể xác minh có nghĩa là không mở quyền ngoài chính sách. Nó không bắt buộc hệ thống phải trả cùng một mã HTTP cho lỗi xác thực và lỗi phụ thuộc dịch vụ. API nên có phản hồi phù hợp và telemetry giúp vận hành phân biệt được nguyên nhân, đồng thời không để lộ token.

Những chỉ số hữu ích gồm độ trễ introspection, tỷ lệ timeout, tỷ lệ inactive, cache hit và độ trễ thu hồi quan sát được. Không đưa giá trị token vào nhãn để tránh rò rỉ và số lượng nhãn tăng không kiểm soát.

## 11. Tự kiểm tra

**Một token không decode được thành JSON có chắc là không hợp lệ không?**

Không. Với opaque access token, API phải dùng cơ chế kiểm tra đã thỏa thuận với AS. Khả năng decode không phải bằng chứng về tính hợp lệ.

**Token active và có `invoices:read` có được đọc mọi hóa đơn không?**

Không. Trong thiết kế ví dụ, còn phải kiểm tra tài nguyên đích, tenant và quyền trên hóa đơn cụ thể.

**AS đã thu hồi token nhưng API vẫn cho dùng trong vài giây. Có thể kiểm tra gì?**

Kiểm tra cache introspection, thời gian hết hạn cache và cách đồng bộ trạng thái. Đối chiếu mục tiêu thu hồi của hệ thống với hành vi đo được, không chỉ với trạng thái tại một nút AS.

**Opaque access token và refresh token có phải là cùng một loại không?**

Không. Opaque mô tả cách nhìn nhận định dạng; access token và refresh token có mục đích khác nhau. Refresh token được dùng với AS để lấy access token, không trình cho API nghiệp vụ thay access token, theo [RFC 6749, mục 1.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.5).

Điểm cần giữ khi thiết kế là: chuỗi token chỉ là phương tiện mang quyền truy cập. Cơ chế xác minh, hợp đồng metadata, chính sách phân quyền và vòng đời thu hồi mới quyết định API có cho đúng chủ thể thực hiện đúng thao tác hay không.
