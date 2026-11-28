# Refresh token

Refresh token là thông tin xác thực mà client dùng để xin access token mới từ authorization server. Nó giúp ứng dụng tiếp tục hoạt động khi access token ngắn hạn hết hiệu lực, trong khi quyền được cấp vẫn còn hợp lệ. Refresh token được cấp tùy chính sách; không phải mọi ứng dụng hay mọi luồng OAuth đều nhận được nó. [RFC 6749, mục 1.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.5)

Trong IAM, refresh token tạo ra một sự đánh đổi: người dùng ít phải đăng nhập lại, nhưng hệ thống phải bảo vệ một thông tin xác thực có thể duy trì quyền truy cập lâu hơn một access token đơn lẻ. Hiểu đúng refresh token vì vậy gắn trực tiếp với vòng đời quyền, phiên đăng nhập và khả năng thu hồi truy cập.

## 1. Phân biệt access token, refresh token và phiên

Access token và refresh token có nơi sử dụng khác nhau. Client đưa access token đến API; refresh token chỉ được gửi đến authorization server trong quá trình xin token mới. [RFC 6749, mục 1.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.5)

Ví dụ xuyên suốt bài học: Lan dùng ứng dụng OrderDesk để xem đơn hàng. Hệ thống giả định gồm OrderDesk, dịch vụ IAM và Orders API.

| Thành phần trong ví dụ | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| Access token `AT1` | Cho phép OrderDesk gọi Orders API trong phạm vi được cấp | Gửi cùng yêu cầu đến Orders API |
| Refresh token `RT1` | Cho phép OrderDesk yêu cầu IAM cấp access token tiếp theo | Gửi đến token endpoint của IAM |
| Phiên OrderDesk | Trạng thái Lan đang sử dụng ứng dụng | Do OrderDesk quản lý theo kiến trúc của nó |
| Phiên tại IAM | Trạng thái đăng nhập của Lan tại nhà cung cấp danh tính | Do IAM quản lý |

Đây là những trạng thái liên quan nhưng không phải một. OrderDesk có thể vẫn đang mở trong trình duyệt khi `AT1` đã hết hạn. Ngược lại, đóng cửa sổ trình duyệt chưa chứng minh mọi token đã bị thu hồi.

Refresh token cũng không phải “access token có thời hạn dài”. Nếu OrderDesk gửi `RT1` đến Orders API thay cho `AT1`, ứng dụng đã dùng sai loại thông tin xác thực.

## 2. Hình dung một lần refresh

Giả sử chính sách thử nghiệm cho access token có thời hạn 5 phút. OrderDesk đã hoàn tất quy trình cấp quyền ban đầu và nhận `AT1` cùng `RT1`. Sau đó, khi cần access token mới, ứng dụng trao đổi `RT1` với IAM.

```mermaid
sequenceDiagram
    participant Client as OrderDesk - Client
    participant AS as IAM - Authorization server
    participant API as Orders API - Resource server

    Note over Client,AS: Đã nhận AT1 và RT1 từ quy trình cấp quyền ban đầu
    Client->>API: Gọi API với AT1 còn hiệu lực
    API-->>Client: Trả dữ liệu được phép truy cập
    Note over Client: Cần access token mới
    Client->>AS: Yêu cầu refresh với RT1
    AS->>AS: Kiểm tra token, client và chính sách
    AS-->>Client: AT2 và RT2 nếu áp dụng rotation
    Client->>Client: Lưu trạng thái token mới
    Client->>API: Gọi API với AT2
    API-->>Client: Trả dữ liệu được phép truy cập
```

Sơ đồ minh họa trách nhiệm của từng thành phần, không liệt kê đầy đủ biện pháp bảo vệ giao thức.

Trong tình huống này, `AT1` không được sửa để sống thêm. IAM phát hành `AT2`, rồi client dùng giá trị mới cho các yêu cầu tiếp theo. Orders API không có trách nhiệm giữ refresh token của OrderDesk để tự gia hạn hộ.

Việc refresh thành công cũng không có nghĩa là OrderDesk được thực hiện mọi hành động. Với chính sách ví dụ chỉ cấp quyền xem đơn hàng, yêu cầu xóa đơn vẫn bị từ chối.

## 3. Yêu cầu refresh trông như thế nào?

Một refresh request sử dụng token endpoint với `grant_type=refresh_token`, giá trị refresh token và có thể có `scope`. Scope yêu cầu không được vượt quá quyền đã cấp; confidential client phải xác thực theo phương thức được cấu hình. Nếu response trả refresh token mới, client phải thay giá trị cũ bằng giá trị mới. [RFC 6749, mục 6](https://www.rfc-editor.org/rfc/rfc6749.html#section-6)

Đoạn HTTP dưới đây là minh họa cho OrderDesk có backend là confidential client, kết nối qua HTTPS. `BASE64_CLIENT_CREDENTIALS`, `RT1_PLACEHOLDER` và mọi token trong bài đều là giá trị giả. Phương thức xác thực client trong triển khai thực tế phải theo cấu hình của IAM.

```http
POST /oauth2/token HTTP/1.1
Host: iam.example.test
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT1_PLACEHOLDER&scope=orders.read
```

Response giả định của hệ thống có rotation:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "AT2_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "RT2_PLACEHOLDER",
  "scope": "orders.read"
}
```

Trong ví dụ, `expires_in: 300` mô tả thời hạn access token tính bằng giây, không phải thời hạn refresh token. Không nên tự diễn giải trường này thành “RT2 hết hạn sau 5 phút”. Thông tin về hạn refresh token phải lấy từ contract và chính sách của IAM, thay vì đoán từ thời hạn access token.

Nếu người dùng muốn OrderDesk có thêm quyền sửa đơn, ứng dụng phải đi qua quy trình cấp thêm quyền phù hợp. Thay `orders.read` bằng `orders.write` trong request refresh không phải một cách xin quyền mới.

Tên scope `orders.read` và đường dẫn `/oauth2/token` là lựa chọn của ví dụ, không phải tên bắt buộc cho mọi nhà cung cấp.

## 4. Thiết kế thời hạn bằng một dòng thời gian

Không có một thời hạn refresh token cố định đúng cho mọi hệ thống. Khi xây dựng chính sách, cần trả lời ít nhất ba câu hỏi: access token dùng được bao lâu, quan hệ refresh tồn tại tối đa bao lâu và được bỏ không bao lâu.

Giả sử môi trường thử nghiệm của OrderDesk chọn:

| Chính sách minh họa | Giá trị giả định | Mục đích trong ví dụ |
| --- | --- | --- |
| Access token | 5 phút | Giới hạn thời gian sử dụng một access token |
| Thời hạn tuyệt đối của quan hệ refresh | 7 ngày từ lúc cấp quyền ban đầu | Đặt mốc kết thúc dù ứng dụng liên tục hoạt động |
| Thời gian không hoạt động tối đa | 24 giờ không refresh | Chấm dứt khả năng tiếp tục phiên bị bỏ quên |

Đây là số liệu để hiểu hành vi, không phải khuyến nghị thời hạn cho một hệ thống sản xuất.

Nếu Lan dùng OrderDesk mỗi giờ, mốc không hoạt động có thể liên tục được cập nhật theo chính sách giả định. Tuy vậy, mốc tuyệt đối 7 ngày vẫn giữ nguyên. Nếu mỗi lần rotation lại đặt lại toàn bộ mốc 7 ngày, ứng dụng đã vô tình biến giới hạn tuyệt đối thành giới hạn trượt.

Ngược lại, nếu Lan không sử dụng ứng dụng trong hơn 24 giờ, lần mở lại có thể cần quy trình cấp quyền mới dù chưa đến ngày thứ bảy.

Một chính sách rõ ràng phải xác định thời hạn được tính trên token hiện tại, trên chuỗi rotation hay trên quan hệ cấp quyền gốc. Nếu ba nơi tính khác nhau, người dùng có thể bị ngắt phiên bất ngờ hoặc giữ quyền lâu hơn dự định.

## 5. Rotation và phát hiện tái sử dụng

Refresh token rotation thay refresh token sau mỗi lần refresh. Đối với public client được cấp refresh token, RFC 9700 yêu cầu cơ chế phát hiện replay bằng rotation hoặc token có ràng buộc mật mã với client instance; confidential client cũng phải được kiểm tra ràng buộc với token đã cấp. [RFC 9700, mục 4.14.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2)

Tại OrderDesk giả định, chuỗi token có thể được mô tả:

```text
RT1 --refresh thành công--> RT2 --refresh thành công--> RT3

RT1: đã dùng, không còn chấp nhận
RT2: đã dùng, không còn chấp nhận
RT3: hiện hành
```

Hệ thống cần nhớ quan hệ giữa các token để xử lý việc một token cũ xuất hiện lại. Chỉ tạo một chuỗi ngẫu nhiên mới mà vẫn cho phép chuỗi cũ dùng tiếp vô hạn không đạt được mục đích phát hiện tái sử dụng.

Xét kịch bản giả định:

| Thời điểm | Sự kiện | Điều hệ thống quan sát |
| --- | --- | --- |
| T0 | OrderDesk nhận `RT1` | Có token hiện hành cho một phiên ứng dụng |
| T1 | Một bản sao `RT1` bị lấy cắp | Hệ thống có thể chưa biết |
| T2 | OrderDesk dùng `RT1`, nhận `RT2` | `RT1` đã được thay thế |
| T3 | Bên giữ bản sao gửi lại `RT1` | Token cũ xuất hiện sau khi đã dùng |

RFC 9700 mô tả việc phát hiện token đã vô hiệu hóa bị tái sử dụng và thu hồi refresh token hiện hành của quan hệ liên quan. Máy chủ không thể chỉ từ sự kiện ấy xác định bên nào là người dùng hợp lệ. [RFC 9700, mục 4.14.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2)

Với OrderDesk, kết quả có thể là Lan phải kết nối lại để tạo quan hệ cấp quyền mới. Đây là cái giá của việc chặn một chuỗi nghi bị lộ, không nên bị giao diện che giấu bằng vòng lặp refresh vô hạn.

Token có ràng buộc mật mã yêu cầu bên sử dụng chứng minh nắm giữ khóa phù hợp. Cách này và rotation xử lý rủi ro khác với PKCE trong bước đổi authorization code. Không nên nghĩ rằng đã có PKCE thì mọi lần sử dụng refresh token tự được bảo vệ tương đương.

## 6. Refresh đồng thời: lỗi có thể đến từ chính client

Không phải mọi lần token cũ xuất hiện lại đều đủ để kết luận có người đánh cắp. Một lỗi thường gặp trong thiết kế ứng dụng là nhiều request cùng nhận thấy access token sắp hết hạn rồi đồng thời refresh.

Giả sử OrderDesk mở hai tác vụ A và B:

```text
A đọc RT1
B đọc RT1
A refresh RT1 thành công, nhận RT2
B tiếp tục refresh RT1
```

Theo chính sách rotation nghiêm ngặt của ví dụ, request B có thể bị coi là tái sử dụng. Người dùng chỉ mở một ứng dụng nhưng vẫn bị buộc đăng nhập lại vì client không điều phối cập nhật token.

Một cách tổ chức ở mức ý tưởng là gom các yêu cầu refresh của cùng một phiên thành một công việc đang chạy:

```text
layAccessToken(phien):
    neu access token hien tai con dung duoc:
        tra access token hien tai

    tham gia cong viec refresh duy nhat cua phien:
        doc lai phien va token moi nhat
        neu phien da ket thuc:
            dung va yeu cau dang nhap

        neu tac vu khac da cap nhat access token:
            tra token moi nhat

        goi IAM bang refresh token hien hanh
        luu dong bo access token, refresh token va phien ban moi
        tra access token moi
```

Đây là pseudocode minh họa điều phối, không phải mã triển khai OAuth đầy đủ. Trong một backend có nhiều instance, khóa chỉ nằm trong bộ nhớ một instance không tự ngăn instance khác dùng cùng token. Cần cơ chế phối hợp phù hợp với nơi lưu phiên.

Cập nhật kết quả cũng phải tránh để response cũ ghi đè response mới. Một số trường hợp cần kiểm tra phiên bản bản ghi và xác nhận phiên chưa bị đăng xuất trong lúc request refresh đang chạy.

Lỗi mạng tạo thêm một tình huống khó: IAM có thể đã nhận `RT1`, cấp `RT2`, nhưng response bị mất. OrderDesk chưa biết kết quả mà cứ gửi lại `RT1` có thể kích hoạt phát hiện replay. Cách phục hồi phải theo contract của nhà cung cấp; không tự mặc định retry là an toàn.

## 7. Lưu trữ refresh token theo kiến trúc ứng dụng

Refresh token có giá trị vì nó mở khả năng xin những access token tiếp theo. Nơi lưu phải phù hợp với ranh giới tin cậy của client.

| Kiến trúc giả định | Hướng xử lý cần xem xét | Sai lầm cần tránh |
| --- | --- | --- |
| Web có backend giữ token | Backend lưu token; trình duyệt dùng phiên ứng dụng được bảo vệ | Đưa refresh token vào HTML hoặc dữ liệu bootstrap |
| Ứng dụng native | Dùng khả năng lưu trữ an toàn của nền tảng và quản lý khóa phù hợp | Ghi token vào file debug hoặc bản sao lưu không kiểm soát |
| Ứng dụng chạy trong trình duyệt | Đánh giá việc cấp token, bảo vệ replay và rủi ro mã JavaScript | Xem `localStorage` là kho bí mật chống được XSS |
| Dịch vụ phía máy chủ | Giới hạn quyền đọc kho token và bảo vệ thông tin xác thực client | Cho mọi dịch vụ trong mạng nội bộ đọc cùng kho token |

Bảng nêu các quyết định kiến trúc cần đánh giá, không khẳng định một nơi lưu có thể chống mọi kiểu xâm nhập.

Nếu OrderDesk dùng backend giữ token, cookie phiên cần được cấu hình phù hợp; `HttpOnly` hạn chế JavaScript đọc cookie nhưng không tự ngăn mọi hành động nguy hiểm do XSS. Token không xuất hiện ở trình duyệt là một ranh giới hữu ích, song backend vẫn phải kiểm soát các API và bảo vệ phiên.

Ở mọi mô hình, tránh đưa token vào URL, log, telemetry, thông báo lỗi hoặc ảnh chụp phục vụ hỗ trợ. Nhật ký nên dùng mã tham chiếu phiên hoặc sự kiện không mang giá trị xác thực.

Public client không thể trở thành confidential client chỉ bằng cách nhúng một `client_secret` trong JavaScript hoặc gói cài đặt. Thông tin mà mọi bản sao ứng dụng đều có thể lấy được không tạo ra bí mật dùng để xác thực riêng một client instance.

## 8. Phân biệt lỗi refresh với lỗi gọi API

Nếu Orders API trả lỗi, chưa thể kết luận nguyên nhân là access token hết hạn. Client cần phân biệt trạng thái token, quyền thao tác và kết quả của giao thức.

| Tình huống | Cách diễn giải trong OrderDesk |
| --- | --- |
| Access token hết hạn, quan hệ refresh còn hợp lệ | Có thể thử lấy access token mới theo cơ chế đã cấu hình |
| Token endpoint trả `invalid_grant` | Dừng dùng token lỗi; xử lý việc kết nối lại hoặc sự cố trạng thái |
| Token endpoint trả `invalid_client` | Kiểm tra phương thức xác thực và cấu hình client |
| Token endpoint trả `invalid_scope` | Kiểm tra quyền ứng dụng yêu cầu |
| Lỗi mạng hoặc timeout | Kết quả refresh có thể chưa rõ; tránh retry mù |
| API từ chối vì thiếu quyền sửa đơn | Refresh không phải cơ chế tự bổ sung quyền |

Các mã `invalid_grant`, `invalid_client` và `invalid_scope` thuộc bộ lỗi token endpoint. Một lỗi `invalid_grant` có thể liên quan refresh token không hợp lệ, hết hạn, bị thu hồi hoặc không thuộc client đang sử dụng. [RFC 6749, mục 5.2](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.2)

Trong vận hành OrderDesk, không nên yêu cầu Lan thử mật khẩu liên tục khi nguyên nhân là backend cấu hình sai phương thức xác thực client. Cũng không nên refresh vô hạn khi người dùng đã bị thu hồi quyền.

Nếu ứng dụng tự gửi lại một yêu cầu nghiệp vụ sau khi refresh, cần xem xét tính an toàn của thao tác đó. Gửi lại yêu cầu đọc danh sách đơn khác với gửi lại yêu cầu tạo thanh toán mà chưa biết lần đầu đã được xử lý hay chưa. Cơ chế chống xử lý trùng của nghiệp vụ phải được thiết kế riêng.

## 9. Thu hồi, đăng xuất và thay đổi quyền

Đối với OrderDesk, một yêu cầu “ngắt kết nối tài khoản Lan” nên được phân tích thành các phần:

1. Kết thúc phiên tại ứng dụng và xóa token khỏi nơi lưu của client.
2. Thực hiện thu hồi tại IAM theo cơ chế mà hệ thống hỗ trợ.
3. Xác định những access token đã cấp còn được API chấp nhận trong bao lâu.
4. Ghi nhận sự kiện và phản ánh đúng kết quả cho người dùng.

Thu hồi refresh token có thể kéo theo thu hồi token liên quan theo chính sách máy chủ. Tuy nhiên, hệ thống phân tán cần xử lý việc truyền trạng thái vô hiệu hóa; token được API xác minh cục bộ không tự nhận được thông báo chỉ vì client đã xóa bản sao của mình. [RFC 7009, mục 2.1 và 3](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1)

Giả sử Lan bị chuyển khỏi nhóm hỗ trợ khách hàng lúc 10:00. OrderDesk không nên xem refresh token cũ là cam kết cho phép giữ mọi quyền hỗ trợ vô thời hạn. IAM và API phải áp dụng chính sách thay đổi quyền của hệ thống, với độ trễ được xác định rõ.

Đổi mật khẩu hoặc đăng xuất tại IAM có tự thu hồi refresh token hay không cũng là hành vi cần kiểm tra ở nhà cung cấp. Không nên khẳng định hiệu lực này chỉ từ tên nút “Đăng xuất”. Một client vẫn cần xử lý việc token mất hiệu lực trước thời hạn dự kiến.

Refresh thành công cũng không chứng minh người dùng vừa nhập mật khẩu hoặc hoàn thành MFA. Nếu nghiệp vụ cần xác thực lại cho thao tác nhạy cảm, ứng dụng phải thực hiện quy trình tương ứng thay vì coi một lần refresh chạy nền là bằng chứng người dùng đang hiện diện.

## 10. Những ngộ nhận cần sửa

**“Refresh token lúc nào cũng là JWT.”** Client nên xử lý token theo contract của nhà cung cấp, không tự giải mã để lấy quyền hoặc tự sửa payload. Hình thức chuỗi token không thay thế kiểm tra phía máy chủ.

**“Access token ngắn hạn thì refresh token có thể giữ mãi.”** Với OrderDesk giả định, access token 5 phút không giúp giới hạn phiên ở 7 ngày nếu ứng dụng cứ gia hạn chuỗi refresh vô hạn.

**“Có refresh token thì không bao giờ cần đăng nhập lại.”** Quyền có thể bị thu hồi, thời hạn có thể kết thúc và trạng thái bảo mật có thể thay đổi.

**“Mỗi lần API báo 401 đều refresh và thử lại.”** Client cần hiểu nguyên nhân, giới hạn số lần thử và tránh gửi lại nghiệp vụ một cách thiếu kiểm soát.

**“Rotation chỉ là thay một chuỗi trong response.”** Cả máy chủ và client phải quản lý trạng thái: token cũ, token hiện hành, quan hệ giữa chúng, cập nhật đồng thời và cách xử lý sự cố.

## 11. Tự kiểm tra

**Tình huống 1:** Response chứa `expires_in: 300`. Có thể kết luận refresh token sống 300 giây không?

Không. Trường ấy mô tả thời hạn access token. Thời hạn refresh token phải được xác định riêng.

**Tình huống 2:** Hai instance OrderDesk cùng refresh bằng `RT1`. Một instance nhận `RT2`, instance kia nhận lỗi. Có đủ bằng chứng kết luận Lan bị đánh cắp token không?

Chưa. Cần kiểm tra điều phối request, cập nhật trạng thái và chính sách phát hiện reuse, đồng thời xử lý tín hiệu bảo mật theo quy trình của hệ thống.

**Tình huống 3:** Lan có `orders.read` và ứng dụng muốn xóa đơn. Có thể refresh với `orders.delete` để lấy quyền không?

Không. Ứng dụng phải xin quyền qua quy trình cấp quyền phù hợp.

**Tình huống 4:** OrderDesk xóa refresh token trong cơ sở dữ liệu khi đăng xuất. Có thể kết luận mọi access token đã hết hiệu lực ở mọi API ngay lập tức không?

Không. Cần xác định cơ chế thu hồi và thực thi ở IAM, API cùng những thành phần liên quan.

Một thiết kế refresh token đầy đủ phải làm rõ nơi lưu, đối tượng được sử dụng, giới hạn thời gian, cách chống tái sử dụng và hành vi khi quyền kết thúc. Sự thuận tiện cho người dùng chỉ bền vững khi những giới hạn ấy được thực thi nhất quán.
