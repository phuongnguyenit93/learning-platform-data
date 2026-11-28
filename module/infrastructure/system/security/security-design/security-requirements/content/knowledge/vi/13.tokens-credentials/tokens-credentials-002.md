# Refresh token

## 1. Refresh token là gì?

Refresh token là thông tin xác thực mà client có thể sử dụng tại dịch vụ cấp token để xin access token mới trong phạm vi được cho phép, thay vì yêu cầu người dùng thực hiện lại toàn bộ quá trình đăng nhập cho mỗi lần access token hết hạn.

Access token thường được gửi đến API tài nguyên để chứng minh quyền truy cập. Refresh token phục vụ việc xin token mới và không được coi là access token thay thế tại API tài nguyên. Hai loại token có mục đích, nơi sử dụng, thời hạn và rủi ro khác nhau.

Không phải mọi client hoặc mọi luồng đều cần refresh token. Việc cấp nó phải dựa trên nhu cầu duy trì truy cập, khả năng bảo vệ thông tin xác thực của client và mức rủi ro của quyền được cấp. Refresh token tồn tại lâu nhưng bảo vệ kém có thể làm một lần lộ bí mật trở thành khả năng xin quyền truy cập mới trong thời gian dài.

Trong đặc tả yêu cầu bảo mật, câu “hỗ trợ refresh token” chỉ mô tả một tính năng. Cần xác định ai được nhận token, token gắn với lần cấp quyền nào, được lưu ở đâu, khi nào không còn sử dụng được và hệ thống xử lý thế nào nếu token bị đánh cắp hoặc được gửi nhiều lần.

## 2. Phân biệt các thành phần và ranh giới tin cậy

| Thành phần | Vai trò | Điều không được mặc định |
|---|---|---|
| Người dùng hoặc identity được đại diện | Chủ thể của quyền truy cập | Đang hiện diện chỉ vì client vừa làm mới token |
| Client | Xin token và sử dụng quyền được cấp | Client nào cũng có thể giữ bí mật lâu dài một cách an toàn |
| Dịch vụ cấp token | Xác minh yêu cầu làm mới và cấp token mới | Chỉ cần giải mã token mà không kiểm tra trạng thái cấp quyền |
| API tài nguyên | Chấp nhận access token theo chính sách | Có thể dùng refresh token để truy cập tài nguyên |
| Lần cấp quyền hoặc grant | Căn cứ cho client truy cập một phạm vi tài nguyên | Vẫn hợp lệ mãi sau khi người dùng hoặc quản trị viên thu hồi |
| Phiên đăng nhập | Ngữ cảnh tương tác và xác thực của người dùng | Luôn có cùng thời hạn với refresh token |

Một refresh token cần được liên kết với các thông tin phù hợp như identity, client, lần cấp quyền, phạm vi quyền, tài nguyên hoặc audience được phép, tenant và trạng thái vòng đời. Không được dùng token của tenant A để xin quyền cho tenant B chỉ vì cùng một người dùng có tài khoản ở cả hai.

Nếu có nhiều thiết bị hoặc nhiều lần đăng nhập, nên xác định đơn vị thu hồi rõ ràng: một token, một chuỗi rotation, một thiết bị, một grant của client hay mọi phiên của identity. “Thu hồi refresh token” không đủ chính xác khi chưa nói tác động đến những đối tượng liên quan nào.

## 3. Từ nguy cơ đến yêu cầu bảo mật

| Nguy cơ | Yêu cầu cần đặc tả | Bằng chứng mong đợi |
|---|---|---|
| Token bị lộ từ client, log hoặc công cụ quan sát | Giảm bề mặt lưu trữ và không ghi bí mật nguyên vẹn | Kiểm kê vị trí chứa token và kết quả quan sát dữ liệu thử nghiệm |
| Token bị dùng bởi client khác | Ràng buộc với client và cơ chế xác minh phù hợp loại client | Yêu cầu dùng sai client bị từ chối |
| Một token bị đánh cắp có thể dùng nhiều lần | Rotation hoặc cơ chế ràng buộc người gửi theo thiết kế | Hành vi với token cũ, thông tin chứng minh sai và chuỗi token liên quan |
| Làm mới làm tăng quyền | Không cấp vượt phạm vi grant và chính sách hiện hành | Yêu cầu scope, audience hoặc tenant vượt phạm vi bị từ chối |
| Người đã bị khóa vẫn xin access token mới | Kiểm tra trạng thái identity, grant và phiên nếu chính sách yêu cầu | Không cấp token mới sau sự kiện thu hồi trong giới hạn đã cam kết |
| Hai request cùng làm mới tạo nhiều nhánh hợp lệ | Kiểm soát cạnh tranh và xử lý lặp | Chỉ tạo kết quả được phép theo contract rotation |
| Lỗi mạng bị coi nhầm là đánh cắp | Có quy tắc xử lý thử lại và mất phản hồi | Không có hành vi ngẫu nhiên hoặc gia hạn vô hạn do cửa sổ thử lại |

Mỗi lựa chọn có giới hạn. Rotation có thể phát hiện việc dùng lại một token đã được tiêu thụ, nhưng không tự bảo đảm phát hiện lần đầu kẻ tấn công sử dụng một token chưa từng dùng. Ràng buộc người gửi cũng chỉ hữu ích khi khóa hoặc thông tin chứng minh tương ứng được bảo vệ và được kiểm tra đúng tại nơi cấp token.

## 4. Quy tắc cấp và sử dụng

### 4.1. Không tự cấp refresh token cho mọi trường hợp

Đặc tả phải nêu các loại client, luồng cấp quyền và phạm vi được phép nhận refresh token. Một công cụ dùng một lần hoặc phiên quản trị đặc biệt có thể không có cùng chính sách duy trì truy cập với ứng dụng thường dùng trên thiết bị cá nhân.

Client có khả năng giữ bí mật phía server cần xác thực theo cơ chế đã chọn. Client công khai không được giả định giữ được một bí mật dùng chung chỉ vì giá trị đó được nhúng trong mã ứng dụng. `client_id` là định danh, không tự trở thành bằng chứng rằng request đến từ đúng bản cài đặt hoặc người dùng hợp lệ.

Các kiểm soát bảo vệ luồng đăng nhập ban đầu cũng không tự bảo vệ refresh token sau khi đã bị lộ. Không được suy ra rằng một cơ chế xác minh ở bước cấp mã ban đầu sẽ ngăn mọi kiểu phát lại refresh token ở bước sau.

### 4.2. Không tăng phạm vi quyền khi làm mới

Một yêu cầu làm mới không phải quyền tự chọn thêm scope, audience hoặc tenant. Token mới phải nằm trong giới hạn grant và các điều kiện cấp quyền còn hiệu lực. Nếu muốn thêm quyền, client cần đi qua quy trình cho phép tương ứng.

Quyền hợp lệ trong quá khứ chưa chắc còn hợp lệ hiện tại. Khi vai trò bị thu hồi, người dùng bị vô hiệu hóa hoặc grant không còn được phép, endpoint refresh phải áp dụng chính sách kiểm tra trạng thái đã cam kết. Không chỉ sao chép tập quyền từ token cũ rồi coi đó là kết luận đủ.

Một access token mới có thể có phạm vi hẹp hơn trước tùy chính sách. Nếu client yêu cầu phạm vi không được phép, hành vi phải rõ: từ chối hoặc xử lý theo contract cấp quyền, không âm thầm cấp thêm.

### 4.3. Truyền token qua kênh được bảo vệ

Refresh token phải được gửi tới endpoint cấp token phù hợp qua kênh bảo vệ. Không đưa token vào URL truy vấn để tránh lan sang lịch sử, log, mã phân tích hoặc các bản sao ngoài ý định.

Minh họa một yêu cầu làm mới; cách xác thực client phụ thuộc contract thực tế và không được bỏ qua trong triển khai:

```http
POST /oauth/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_PLACEHOLDER&client_id=client-a
```

Các giá trị trong ví dụ là ký hiệu, không phải bí mật sử dụng được. Việc có `client_id` trong request không thay thế xác thực client hoặc cơ chế ràng buộc người gửi khi chính sách yêu cầu.

## 5. Vòng đời và giới hạn thời gian

Refresh token có thể có hạn tuyệt đối, giới hạn không sử dụng hoặc cả hai. Đặc tả phải phân biệt thời hạn của một token trong chuỗi với thời hạn của grant hay toàn bộ chuỗi.

| Mốc hoặc điều kiện | Ý nghĩa cần xác định |
|---|---|
| Thời điểm phát hành | Token hoặc chuỗi bắt đầu tồn tại khi nào? |
| Hạn tuyệt đối | Sau mốc nào phải xác thực hoặc cấp quyền mới dù liên tục làm mới? |
| Hạn không sử dụng | Không có lần refresh hợp lệ trong bao lâu thì không được sử dụng tiếp? |
| Rotation | Token cũ chuyển trạng thái và token mới được cấp khi nào? |
| Thu hồi | Sự kiện nào vô hiệu hóa token, grant hoặc chuỗi? |
| Độ mới của xác thực | Khi nào làm mới không đủ và phải yêu cầu xác thực lại? |

Nếu mỗi lần rotation lại đặt toàn bộ thời hạn về ban đầu mà không có giới hạn khác, một chuỗi có thể sống lâu hơn ý định bảo mật. Nếu yêu cầu có hạn tuyệt đối cho chuỗi, mốc đó phải được bảo toàn qua các lần làm mới.

Ví dụ giả định: một ứng dụng cho phép chuỗi refresh tồn tại tối đa 30 ngày và không được bỏ không quá 7 ngày. Một lần làm mới hợp lệ có thể cập nhật mốc không sử dụng theo chính sách, nhưng không đẩy hạn tuyệt đối của chuỗi vượt 30 ngày. Các con số này chỉ phục vụ minh họa, không phải giá trị chuẩn cho mọi hệ thống.

Server phải xác định thời điểm đánh giá và quy tắc biên. Nếu chính sách chọn hết hạn tại `now >= expiresAt`, request đến đúng mốc không được tiếp tục. Dữ liệu thời gian từ client không được dùng để kéo dài hiệu lực.

Refresh token còn hạn cũng không tự cho phép vượt idle timeout hoặc absolute timeout của phiên nếu chính sách yêu cầu ràng buộc với phiên đó. Ngược lại, một grant được phép hoạt động khi người dùng không hiện diện cần được xác định rõ, thay vì mặc định có cùng vòng đời với phiên web.

## 6. Rotation và phát hiện sử dụng lại

### 6.1. Rotation thay đổi trạng thái như thế nào?

Trong mô hình rotation một lần sử dụng, một yêu cầu hợp lệ tiêu thụ refresh token hiện tại và tạo token kế tiếp. Các token liên quan có thể được nhóm thành một chuỗi hoặc token family để quản lý vòng đời và phát hiện dùng lại.

```text
RT0 -- làm mới hợp lệ --> RT1 -- làm mới hợp lệ --> RT2

Sau mỗi bước:
    token trước: đã tiêu thụ
    token mới: hiện hành, nếu grant và chuỗi vẫn hợp lệ
```

Token mới không phải bản cập nhật mà client tự sửa từ token cũ. Nó phải được dịch vụ cấp token tạo theo cơ chế đã phê duyệt và client thay thế giá trị lưu trữ theo contract.

Một khi `RT0` đã bị tiêu thụ, việc xuất hiện lại của nó là tín hiệu cần xử lý. Chính sách có thể thu hồi cả chuỗi và yêu cầu xác thực lại. Tuy nhiên, cần phân biệt tín hiệu dùng lại với một ID không tồn tại hoặc dữ liệu chưa được xác minh; một giá trị ngẫu nhiên không được trở thành cách thu hồi tùy ý phiên của người khác.

### 6.2. Thao tác tiêu thụ phải kiểm soát cạnh tranh

Hai request có thể cùng đọc thấy `RT0` đang hoạt động. Nếu cả hai đều được phép cập nhật không có điều kiện, hệ thống có thể tạo `RT1a` và `RT1b` cùng hợp lệ. Điều này phá vỡ giả định một token hiện hành trong mô hình đã chọn.

Việc kiểm tra trạng thái, tiêu thụ token cũ và ghi token kế tiếp phải có cơ chế phối hợp phù hợp như giao dịch hoặc cập nhật có điều kiện. Chỉ được trả kết quả sử dụng được khi trạng thái cần thiết đã được ghi bền vững theo contract.

Trình tự khái niệm:

```text
1. Xác minh request, client và thông tin chứng minh bắt buộc.
2. Tra cứu, kiểm tra bí mật và liên kết refresh token.
3. Kiểm tra thời hạn, trạng thái identity, grant, chuỗi và phạm vi yêu cầu.
4. Trong cơ chế kiểm soát cạnh tranh:
   - chỉ token hiện hành đủ điều kiện mới được tiêu thụ;
   - ghi token kế tiếp và quan hệ với chuỗi;
   - lưu trạng thái và sự kiện cần thiết.
5. Trả token mới sau khi đáp ứng điều kiện lưu bền vững.
6. Nếu phát hiện dùng lại đã được xác minh, xử lý theo chính sách chuỗi.
```

Trình tự này không phải mã endpoint hoàn chỉnh. Đặc biệt, kiểm tra sai client hoặc sai bằng chứng không nên tự tiêu thụ token hợp lệ trước khi request được xác minh đủ điều kiện.

### 6.3. Ghi nhận thu hồi dù phản hồi là lỗi

Một lỗi triển khai dễ xảy ra là phát hiện dùng lại, cập nhật chuỗi thành thu hồi rồi ném lỗi khiến giao dịch bị rollback. Client nhận thông báo lỗi nhưng trạng thái thu hồi thực tế không được lưu.

Đặc tả và thiết kế cần tách rõ quyết định trả lỗi với việc lưu bền vững sự kiện bảo mật. Nếu chính sách yêu cầu thu hồi chuỗi sau dùng lại, kết quả đó phải tồn tại và được đối soát dù phản hồi endpoint là thất bại.

Thông tin về token đã tiêu thụ cũng cần được giữ đủ lâu cho khoảng vòng đời và phát lại được hỗ trợ. Xóa ngay bản ghi cũ có thể làm hệ thống không còn phân biệt được token đã dùng với một giá trị không xác định. Thời gian giữ và dữ liệu tối thiểu phải cân bằng nhu cầu phát hiện với chính sách bảo vệ dữ liệu.

## 7. Cạnh tranh, thử lại và mất phản hồi

Rotation làm rõ giới hạn một lần sử dụng nhưng tạo tình huống cần đặc tả: server đã tiêu thụ token và tạo token mới, còn phản hồi bị mất trên mạng. Client chỉ còn token cũ và có thể thử lại.

| Tình huống | Rủi ro nếu không có contract rõ | Hành vi cần quyết định |
|---|---|---|
| Hai tab cùng refresh | Hai nhánh token hoặc cảnh báo dùng lại không mong muốn | Phối hợp phía client và quy tắc server cho request cạnh tranh |
| Timeout sau khi server đã commit | Client thử token cũ và bị thu hồi chuỗi | Yêu cầu xác thực lại hoặc cơ chế thử lại có giới hạn được thiết kế rõ |
| Client lưu access token mới nhưng chưa lưu refresh token mới | Mất khả năng làm mới tiếp theo | Cách cập nhật bộ token và xử lý lưu trữ lỗi |
| Request cũ đến muộn | Có thể bị hiểu là phát lại hoặc tạo thêm token | Kiểm tra trạng thái và thứ tự, không gia hạn tùy tiện |
| Bản sao dữ liệu chậm | Một node chấp nhận token đã tiêu thụ ở node khác | Nguồn trạng thái có thẩm quyền và giới hạn nhất quán |

Client có thể gom các yêu cầu refresh để chỉ một yêu cầu làm mới đang diễn ra cho cùng ngữ cảnh, còn các request API chờ kết quả. Với nhiều tab hoặc tiến trình, cần cơ chế phối hợp phù hợp mà không phát tán bí mật qua kênh không được bảo vệ. Dù client phối hợp tốt, server vẫn phải chịu được request trùng hoặc đối thủ gửi đồng thời.

Nếu chọn hỗ trợ thử lại sau mất phản hồi, phải xác định cách nhận diện đúng yêu cầu lặp, ràng buộc client hoặc người gửi, thời gian cửa sổ và kết quả được trả. Không được đơn giản cho token cũ tạo tiếp một chuỗi mới trong mỗi lần thử.

Việc trả lại đúng token kế tiếp đã phát hành còn có yêu cầu lưu trữ riêng: một bản băm không thể tự phục hồi giá trị bí mật ban đầu. Nếu thiết kế cần giữ kết quả có thể trả lại, phải bảo vệ dữ liệu đó, giới hạn thời gian và kiểm soát truy cập. Không tuyên bố vừa chỉ lưu bản băm không thể đảo ngược vừa luôn có thể gửi lại nguyên token mới mà không có cơ chế bổ sung.

Một chính sách chặt yêu cầu xác thực lại khi không thể khôi phục an toàn cũng có thể là lựa chọn hợp lệ. Cần công khai ảnh hưởng trải nghiệm và nguy cơ gây gián đoạn: kẻ đã giữ token cũ có thể cố phát lại để kích hoạt thu hồi chuỗi trong mô hình phát hiện dùng lại. Rotation hỗ trợ kiểm soát rủi ro, không loại bỏ mọi đánh đổi về tính sẵn sàng.

## 8. Bảo vệ refresh token khi lưu trữ

### 8.1. Phía dịch vụ cấp token

Refresh token có thể là một giá trị opaque hoặc có cấu trúc. Định dạng không quyết định tự động rằng token có thể bị thu hồi, được mã hóa hay khó bị đánh cắp. Token có chữ ký không đồng nghĩa nội dung được giữ bí mật; một token opaque cũng cần được sinh khó đoán và lưu trữ đúng.

Nếu token là bí mật ngẫu nhiên chỉ cần kiểm tra khi được trình lên, hệ thống có thể lưu giá trị kiểm chứng thay vì bản rõ, với cơ chế băm hoặc kiểm chứng được thiết kế phù hợp. Token cần đủ độ khó đoán; mã hóa biểu diễn như Base64 không tự tạo thêm độ ngẫu nhiên.

Các khóa bảo vệ dữ liệu, bản sao dự phòng, bộ nhớ đệm, công cụ hỗ trợ và quyền truy vấn cũng thuộc phạm vi bảo vệ. Băm ở một bảng không có nghĩa token chưa từng đi qua log request hoặc dữ liệu chẩn đoán.

### 8.2. Phía client

Client cần lấy lại token để sử dụng, nên yêu cầu lưu trữ khác với nơi chỉ giữ giá trị kiểm chứng. Cách bảo vệ phụ thuộc môi trường:

- Backend có thể giữ token trong kho bí mật hoặc cơ sở dữ liệu được bảo vệ với quyền truy cập giới hạn và cơ chế bảo vệ dữ liệu phù hợp.
- Ứng dụng trên thiết bị có thể dùng nơi lưu trữ do nền tảng cung cấp, đồng thời xét bản sao lưu, thiết bị bị kiểm soát và khả năng trích xuất.
- Ứng dụng trình duyệt cần đánh giá rủi ro mã JavaScript truy cập dữ liệu, chính sách cookie, giả mạo request và giới hạn lưu trữ của client.

Một kiến trúc backend phục vụ frontend có thể giữ refresh token ở server và chỉ cấp cho trình duyệt cookie phiên có chính sách phù hợp. Đây là cách thay đổi nơi giữ bí mật và ranh giới tin cậy, không phải loại bỏ mọi rủi ro: endpoint vẫn cần kiểm tra phiên, chống request giả mạo và bảo vệ server.

Nếu dùng cookie chứa thông tin làm mới, phải đặc tả `Secure`, `HttpOnly` khi phù hợp, phạm vi host/path và chính sách `SameSite`. `HttpOnly` giảm khả năng JavaScript đọc trực tiếp cookie nhưng không ngăn mọi request trái phép từ mã chạy trong trang.

Không đưa token thật vào source code, nội dung lỗi, hệ thống phân tích hành vi hoặc báo cáo kiểm chứng. Những vị trí đó thường có phạm vi truy cập rộng hơn hệ thống giữ thông tin xác thực.

## 9. Thu hồi và quan hệ với access token đã cấp

Sự kiện thu hồi có thể gồm đăng xuất trên một thiết bị, đăng xuất mọi nơi, người dùng hủy quyền của client, identity bị khóa, phát hiện lộ token hoặc thay đổi bảo mật cần kết thúc grant. Mỗi loại sự kiện cần phạm vi và thời hạn hiệu lực rõ ràng.

Thu hồi refresh token chủ yếu ngăn việc xin token mới từ thông tin làm mới đó. Access token đã phát hành có thể vẫn được API tài nguyên chấp nhận đến khi hết hạn nếu nơi thực thi không kiểm tra thu hồi hoặc trạng thái liên quan.

Vì vậy, hai yêu cầu sau khác nhau:

```text
A. Sau thu hồi, endpoint refresh không được cấp token mới.
B. Sau thu hồi, API tài nguyên không được chấp nhận access token đã cấp.
```

Đáp ứng A không tự chứng minh B. Nếu rủi ro yêu cầu dừng truy cập nhanh, cần cơ chế thực thi và thời hạn access token phù hợp, cùng giới hạn độ trễ ở cache hoặc các node liên quan.

Thay đổi mật khẩu hoặc đóng phiên web cũng không được mặc định có cùng tác động trong mọi hệ thống. Đặc tả phải nêu các sự kiện đó có thu hồi grant hoặc chuỗi refresh không, áp dụng cho thiết bị nào và khi nào kết quả được xác nhận.

## 10. Viết yêu cầu có thể kiểm chứng

Các thời hạn và giá trị trong bảng thuộc hệ thống giả định, không phải quy tắc chung áp dụng cho mọi sản phẩm.

| ID | Yêu cầu mẫu | Cách kiểm chứng dự kiến |
|---|---|---|
| RT-01 | Chỉ client và luồng cấp quyền được đăng ký mới được nhận refresh token; API tài nguyên phải từ chối refresh token như thông tin truy cập. | Thử cấp cho client ngoài phạm vi và dùng refresh token tại endpoint tài nguyên. |
| RT-02 | Mỗi refresh token phải gắn với identity, client, grant, tenant và phạm vi tài nguyên được phép; yêu cầu không khớp không được cấp token. | Dùng token với client, tenant hoặc audience khác. |
| RT-03 | Token mới không được có scope hoặc quyền vượt grant và chính sách hiện hành; trạng thái khóa identity phải được áp dụng khi đánh giá làm mới. | Thu hồi một quyền hoặc khóa identity rồi thử làm mới. |
| RT-04 | Trong mô hình rotation đã chọn, một token hiện hành chỉ được tiêu thụ một lần; các cập nhật trạng thái và token kế tiếp phải được lưu bền vững trước khi trả thành công. | Gửi hai request đồng thời và dừng tiến trình tại các điểm ghi dữ liệu. |
| RT-05 | Dùng lại token đã tiêu thụ sau khi xác minh đủ điều kiện phải kích hoạt chính sách thu hồi chuỗi và ghi sự kiện; token ngẫu nhiên không được thu hồi chuỗi của người khác. | Phát lại token thử nghiệm cũ và gửi dữ liệu không khớp để so sánh hành vi. |
| RT-06 | Chuỗi có hạn tuyệt đối 30 ngày và hạn không sử dụng 7 ngày; rotation không được kéo dài hạn tuyệt đối. | Làm mới liên tục và thử tại các mốc giới hạn bằng thời gian kiểm soát được. |
| RT-07 | Sau khi thu hồi được ghi nhận tại nguồn trạng thái, mọi node cấp token phải từ chối làm mới trong tối đa 5 giây; nếu chưa đọc được trạng thái cho yêu cầu cần kiểm tra, không được mặc định grant còn hợp lệ. | Thu hồi rồi thử qua các node, cache và tình huống kho trạng thái lỗi. |
| RT-08 | Quy tắc thử lại sau mất phản hồi phải có phạm vi, ràng buộc và cửa sổ xác định; không được tạo nhánh refresh hợp lệ không giới hạn từ token cũ. | Làm mất phản hồi sau commit rồi gửi lại trong và ngoài cửa sổ được hỗ trợ. |
| RT-09 | Log request, lỗi, trace và báo cáo không được chứa refresh token nguyên vẹn hoặc bí mật xác thực client. | Dùng token thử nghiệm có thể nhận diện để kiểm tra các kênh quan sát. |
| RT-10 | Đăng xuất một thiết bị phải thu hồi đúng chuỗi hoặc grant thuộc phạm vi đó; tác động đến access token đã cấp phải được quy định riêng. | Đăng nhập hai thiết bị, đăng xuất một thiết bị và kiểm tra cả refresh lẫn API tài nguyên. |
| RT-11 | Xử lý phát hiện dùng lại phải lưu được trạng thái thu hồi và sự kiện bảo mật dù endpoint trả lỗi; rollback không được làm mất quyết định bắt buộc. | Gây lỗi tại nhánh xử lý dùng lại và đọc lại trạng thái chuỗi. |

RT-07 cần có điểm bắt đầu đo, điểm kết thúc và tập node được bao phủ rõ ràng. Nếu một node không đọc được trạng thái, phản hồi lỗi tạm thời không đồng nghĩa token hợp lệ; client phải có cách xử lý lỗi mà không lặp vô hạn hoặc làm lộ thông tin xác thực.

Nếu chọn ràng buộc người gửi thay cho hoặc kết hợp với rotation, cần bổ sung yêu cầu kiểm tra khóa, bằng chứng, phạm vi sử dụng và hành vi khi khóa thay đổi hoặc bị mất. Không coi việc bật một tùy chọn cấu hình là đủ nếu chưa có bằng chứng tại endpoint thực thi.

## 11. Ví dụ vòng đời trên hai lần làm mới

Một ứng dụng nhận access token `AT0` và refresh token `RT0` thuộc chuỗi `F1`. Các ký hiệu chỉ mô tả trạng thái, không đại diện cho giá trị token thật.

| Bước | Sự kiện | Trạng thái mong muốn trong mô hình minh họa |
|---|---|---|
| 1 | Cấp quyền ban đầu hợp lệ | `RT0` hiện hành, `F1` hoạt động |
| 2 | Client dùng `RT0` đúng điều kiện | `RT0` đã tiêu thụ, cấp `AT1` và `RT1` |
| 3 | Client lưu `RT1` và thay bộ token | Các yêu cầu làm mới tiếp theo dùng `RT1` |
| 4 | Client dùng `RT1` hợp lệ | `RT1` đã tiêu thụ, cấp `AT2` và `RT2` |
| 5 | Một bên phát lại `RT0` ngoài cơ chế thử lại được phép | Ghi nhận dùng lại đã xác minh và áp dụng chính sách đối với `F1` |
| 6 | Client tiếp tục dùng `RT2` khi `F1` đã thu hồi | Từ chối, yêu cầu cấp quyền hoặc xác thực mới theo chính sách |

Nếu phản hồi ở bước 2 bị mất, client chưa chắc có `RT1`. Hệ thống phải đi theo contract mất phản hồi đã chọn, không tự suy luận rằng mọi lần dùng `RT0` đều chắc chắn đến từ kẻ tấn công, cũng không vì muốn tránh gián đoạn mà cho phép `RT0` sống lại vô thời hạn.

Một hồ sơ quản lý chuỗi có thể chứa các trường minh họa:

```yaml
familyId: family-042
subjectId: user-184
clientId: client-a
grantId: grant-7831
tenantId: tenant-a
allowedScopes:
  - profile:read
  - orders:read
state: ACTIVE
currentTokenRecordId: refresh-record-003
absoluteExpiresAt: '2026-12-20T03:00:00Z'
lastSuccessfulRefreshAt: '2026-11-27T03:00:00Z'
rotationPolicy: SINGLE_USE
reusePolicy: REVOKE_FAMILY_AFTER_VERIFIED_REUSE
```

Đây là dữ liệu minh họa yêu cầu, không phải schema bắt buộc. `currentTokenRecordId` là định danh bản ghi, không phải bí mật sử dụng để làm mới. Ví dụ cố ý không chứa token nguyên vẹn hoặc thông tin xác thực client.

## 12. Tình huống nghiệm thu và quan sát vận hành

Các tình huống sau phục vụ việc triển khai và kiểm chứng sau này; chúng không phải kết quả kiểm thử đã thực hiện.

**Sai mục đích token:** Gửi refresh token đến API nghiệp vụ hoặc dùng access token tại đường làm mới. Hệ thống phải xác định loại và mục đích được chấp nhận, không cho phép chỉ vì chuỗi có chữ ký hợp lệ hoặc tồn tại trong kho dữ liệu.

**Sai client hoặc tenant:** Một token hợp lệ được gửi với định danh khác. Không được cấp token mới, thay liên kết của token cũ hoặc tiết lộ chi tiết nhạy cảm về identity liên quan.

**Xin thêm quyền:** Client đang có quyền đọc nhưng yêu cầu quyền ghi khi refresh. Kết quả phải tuân theo giới hạn grant và chính sách, không tự mở rộng quyền.

**Hai request đồng thời:** Cùng token được gửi đến hai node. Trạng thái cuối phải phù hợp chính sách rotation và thử lại, không xuất hiện nhiều nhánh ngoài ý định.

**Mất phản hồi sau khi lưu:** Dịch vụ đã commit rotation nhưng client không nhận kết quả. Lần thử tiếp theo phải có hành vi xác định theo contract, kể cả khi lựa chọn là yêu cầu xác thực mới.

**Thu hồi trong khi làm mới:** Một quản trị viên thu hồi grant cùng lúc request refresh đang xử lý. Phải xác định thứ tự có hiệu lực và giới hạn lan truyền, không để trạng thái cũ khôi phục grant đã thu hồi.

**Refresh tự động khi người dùng không hiện diện:** Client hoạt động nền. Nếu chính sách liên kết với idle timeout hoặc độ mới xác thực, hoạt động nền không được tự bỏ qua các giới hạn đó.

**Kho trạng thái không khả dụng:** Endpoint không thể kiểm tra thu hồi hoặc rotation. Hành vi phải theo contract lỗi; không chuyển lỗi đọc thành kết luận token còn hợp lệ.

Quan sát vận hành nên phân biệt thành công, hết hạn, thu hồi, sai client, sai phạm vi, dùng lại đã xác minh, lỗi lưu trữ và lỗi ràng buộc người gửi. Có thể ghi ID bản ghi, grant, chuỗi, client, thời gian và mã liên kết phù hợp, nhưng không ghi token nguyên vẹn. Quyền xem log và thời gian giữ dữ liệu cần nằm trong yêu cầu bảo vệ thông tin.

Các chỉ số đáng theo dõi gồm tỷ lệ refresh thất bại theo nguyên nhân, số chuỗi bị thu hồi do dùng lại, độ trễ áp dụng thu hồi, số request cạnh tranh và tỷ lệ phải xác thực lại sau lỗi mạng. Tăng lỗi dùng lại có thể là tấn công, lỗi phối hợp client hoặc lỗi retry; cần bằng chứng phân tích thay vì kết luận từ một bộ đếm duy nhất.

Một yêu cầu refresh token đầy đủ phải nối việc duy trì trải nghiệm đăng nhập với quyền kiểm soát lâu dài đối với thông tin xác thực. Token mới chỉ được cấp khi các ràng buộc vẫn hợp lệ, trạng thái được cập nhật nhất quán và mọi trường hợp thu hồi hoặc phục hồi lỗi có hành vi xác định.
