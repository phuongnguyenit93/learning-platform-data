# Idle timeout

## 1. Idle timeout là yêu cầu bảo mật nào?

Idle timeout là giới hạn thời gian một phiên được phép không có **hoạt động hợp lệ theo chính sách** trước khi không còn được sử dụng để truy cập tài nguyên được bảo vệ. Mục tiêu thường là giảm thời gian một phiên bị bỏ quên có thể bị lợi dụng, chẳng hạn khi người dùng rời khỏi máy nhưng chưa đăng xuất.

Yêu cầu “tự đăng xuất sau 15 phút không hoạt động” còn thiếu nhiều thông tin: hoạt động nào được tính, hệ thống quan sát nó ở đâu, đồng hồ nào quyết định, các tab có dùng chung phiên không, và token đã phát hành có còn dùng được sau timeout hay không.

Một đặc tả đầy đủ cần mô tả hành vi tại điểm kiểm tra truy cập, thay vì chỉ mô tả việc giao diện chuyển về màn hình đăng nhập. Người dùng hoặc chương trình khác vẫn có thể gửi request trực tiếp dù trang web đã ẩn nội dung.

Idle timeout cũng không chứng minh rằng người dùng hiện tại còn là người đăng nhập ban đầu. Nếu kẻ tấn công đã có phiên và liên tục tạo hoạt động được chấp nhận, phiên có thể không bị coi là nhàn rỗi. Vì vậy, idle timeout cần phối hợp với thời hạn phiên tuyệt đối, thu hồi phiên và yêu cầu xác thực lại khi phù hợp.

## 2. Phân biệt các giới hạn thời gian

| Cơ chế | Mốc bắt đầu hoặc được cập nhật | Câu hỏi được giải quyết |
|---|---|---|
| Idle timeout | Hoạt động hợp lệ gần nhất của phiên | Phiên đã bị bỏ không quá lâu chưa? |
| Absolute timeout | Thời điểm bắt đầu vòng đời phiên theo chính sách | Phiên này đã tồn tại quá lâu chưa, dù vẫn có hoạt động? |
| Thời hạn access token | Thời điểm phát hành và hạn dùng của token | Token cụ thể này còn nằm trong thời hạn được chấp nhận không? |
| Thời hạn refresh token | Vòng đời và quy tắc sử dụng thông tin làm mới | Có được cấp token mới từ thông tin làm mới này không? |
| Độ mới của xác thực | Thời điểm và mức bảo đảm của lần xác thực liên quan | Có cần xác thực lại trước thao tác nhạy cảm không? |
| Thời gian lưu cookie | Quy tắc lưu và gửi cookie của trình duyệt | Trình duyệt còn giữ hoặc gửi thông tin phiên không? |

Những giới hạn này có thể dùng các giá trị khác nhau và không thay thế cho nhau. Cookie còn tồn tại không có nghĩa phiên còn hợp lệ; access token chưa hết hạn cũng không tự chứng minh phiên chưa vượt idle timeout.

Với một mô hình đơn giản, đặt:

```text
idleDeadline     = lastQualifyingActivityAt + idleTimeout
absoluteDeadline = sessionStartedAt + absoluteTimeout
effectiveDeadline = min(idleDeadline, absoluteDeadline)
```

Phiên còn dùng được tại thời điểm đánh giá khi chưa bị thu hồi, chưa vượt các điều kiện bảo mật khác và `serverNow < effectiveDeadline`. Nếu chính sách chọn hết hạn ngay tại mốc giới hạn thì `serverNow >= effectiveDeadline` phải bị từ chối. Quy tắc biên cần thống nhất giữa các thành phần, tránh nơi coi đúng 15 phút là còn hợp lệ còn nơi khác coi là đã hết hạn.

Hoạt động được chấp nhận có thể cập nhật idle deadline nhưng không được âm thầm kéo dài absolute deadline. Cấp một access token mới cũng không nhất thiết là bắt đầu một phiên mới.

## 3. Định nghĩa hoạt động hợp lệ

### 3.1. Hoạt động mà hệ thống thực sự quan sát được

Server thường quan sát request, thông điệp kết nối hoặc một sự kiện được ứng dụng gửi lên. Nó không trực tiếp biết người dùng có đang ngồi trước màn hình, đọc tài liệu hay chỉ để một đoạn mã chạy nền.

Vì thế, nên đặc tả chính xác theo những sự kiện có thể kiểm chứng, ví dụ “request nghiệp vụ đã được xác thực, được phân quyền và thuộc danh sách được tính hoạt động”. Không được diễn đạt rằng server bảo đảm nhận diện sự hiện diện của con người nếu triển khai chỉ dựa trên lưu lượng mạng.

| Sự kiện | Có nên tự động gia hạn phiên? | Điều cần làm rõ |
|---|---|---|
| Người dùng gửi một yêu cầu nghiệp vụ được phép | Có thể được tính | Danh sách loại thao tác và thời điểm ghi nhận |
| Người dùng mở trang chứa dữ liệu được bảo vệ | Có thể được tính | Request có thực sự đi đến server hay chỉ đọc từ cache? |
| Polling thông báo mỗi 30 giây | Thường không nên mặc định tính | Nếu tính, trang mở nền có thể giữ phiên vô hạn theo idle policy |
| Heartbeat hoặc ping của kết nối | Không tự chứng minh có người đang hoạt động | Tách duy trì kết nối khỏi gia hạn phiên |
| Tự động làm mới token | Không nên mặc định coi là hoạt động người dùng | Làm mới phải kiểm tra trạng thái phiên và quy tắc idle riêng |
| Request bị từ chối xác thực hoặc phân quyền | Không nên gia hạn theo mặc định | Tránh lưu lượng không hợp lệ giữ phiên sống |
| Di chuyển chuột hoặc nhấn phím ở frontend | Có thể là tín hiệu hỗ trợ | Dữ liệu client có thể bị giả lập; cần giới hạn và kiểm tra phía server |
| Tác vụ nền do server chạy | Thường không phải hoạt động của phiên người dùng | Tách vòng đời công việc khỏi phiên tương tác |

Chính sách có thể chọn khác nhau theo sản phẩm. Điểm bắt buộc là loại sự kiện nào được tính phải được mô tả rõ và có cùng ý nghĩa ở frontend, gateway và backend.

### 3.2. Không tin thời điểm do client tự khai

Client không được tự đặt `lastActivityAt` trong tương lai hoặc truyền thời gian mới nhất để hồi sinh phiên đã hết hạn. Server quyết định thời điểm chấp nhận hoạt động dựa trên nguồn thời gian và trạng thái phiên có thẩm quyền.

Một header như `X-User-Active: true` chỉ là dữ liệu từ client. Nó không tự chứng minh thao tác của con người và không được bỏ qua xác thực, phân quyền hoặc kiểm tra nguồn request. Tương tự, endpoint gia hạn phiên không được trở thành cách cho request nền hay request bị giả mạo giữ phiên hoạt động mà không đáp ứng chính sách.

Đọc nội dung lâu mà không gửi request cũng là một tình huống cần quyết định. Nếu sản phẩm muốn cho phép người dùng chủ động giữ phiên, có thể cung cấp cảnh báo và thao tác tiếp tục rõ ràng. Yêu cầu vẫn phải thừa nhận đây là một sự kiện do client gửi, không phải bằng chứng tuyệt đối về sự hiện diện của người dùng hợp lệ.

## 4. Phía server phải có thẩm quyền hết hạn

### 4.1. Trạng thái và thứ tự xử lý

Mô hình phiên có thể lưu ID phiên, identity, thời điểm bắt đầu, hoạt động hợp lệ gần nhất, phiên bản trạng thái, cờ thu hồi và mức bảo đảm xác thực. Không nhất thiết mọi hệ thống đều lưu đúng những trường này, nhưng cần có dữ liệu tương đương để thực thi các giới hạn đã cam kết.

Một trình tự xử lý về mặt khái niệm là:

```text
1. Xác minh thông tin phiên và đọc trạng thái có thẩm quyền.
2. Lấy thời gian đánh giá phía server.
3. Kiểm tra thu hồi, idle deadline và absolute deadline.
4. Nếu đã hết hạn, từ chối; không cập nhật hoạt động để khôi phục phiên.
5. Đánh giá quyền truy cập và phân loại request có được tính hoạt động hay không.
6. Với hoạt động hợp lệ, cập nhật mốc hoạt động bằng thao tác có kiểm soát cạnh tranh.
7. Cho phép xử lý theo quy tắc kiểm tra quyền của thao tác.
```

Đây là trình tự minh họa, không phải đoạn mã sẵn sàng cho mọi framework. Việc kiểm tra và cập nhật phiên phải phối hợp đủ chặt để không tạo cửa sổ cho một request sử dụng dữ liệu cũ gia hạn phiên đã hết hạn hoặc đã bị thu hồi.

Tác vụ dọn dữ liệu hết hạn không phải điểm thực thi chính sách. Dù bản ghi phiên chưa bị xóa vật lý, request vẫn phải bị từ chối nếu đã qua deadline. Ngược lại, TTL trong kho dữ liệu không được vô tình xóa sớm một phiên còn hợp lệ nếu việc ghi hoạt động bị tối ưu hóa không đúng.

### 4.2. Cạnh tranh giữa các request

Hai request có thể cùng đọc một mốc hoạt động cũ, hoặc một request đến đúng lúc request khác thu hồi phiên. Cần xác định thứ tự có hiệu lực bằng cơ chế phù hợp như cập nhật có điều kiện, giao dịch hoặc thao tác nguyên tử ở kho phiên.

Nếu phiên bản trạng thái thay đổi trong lúc xử lý, không được ghi đè kết quả mới bằng bản cũ. Đặc biệt, thao tác ghi mốc hoạt động không được xóa cờ thu hồi hoặc khôi phục trạng thái hoạt động từ một bản đọc trước đó.

Không nên dùng thời điểm request bắt đầu tại một máy làm bằng chứng rằng nó được quyền gia hạn mãi về sau. Nếu request chờ trong hàng đợi và đến lúc đánh giá phiên đã hết hạn, chính sách phải chỉ rõ cách xử lý. Việc client gửi request trước deadline không tự chứng minh server đã chấp nhận nó trước deadline.

### 4.3. Thời gian trong hệ thống nhiều node

Các node cần áp dụng cùng cách tính deadline và giả định về sai lệch đồng hồ. Đồng hồ lùi, node khởi động lại hoặc bản sao trạng thái chậm có thể khiến các máy đưa ra kết luận khác nhau.

Không thể chỉ dùng một đồng hồ đơn điệu cục bộ rồi giả định giá trị đó có ý nghĩa trên mọi node hoặc sau khi khởi động lại. Thiết kế cần nguồn thời gian và cách lưu trạng thái phù hợp với kiến trúc, cùng giới hạn sai lệch được chấp nhận. Khi phát hiện bất thường thời gian, phiên đã xác nhận hết hạn hoặc thu hồi không được trở lại hợp lệ do đồng hồ thay đổi.

Nếu cho phép đọc cache hoặc bản sao chậm, phải đưa độ trễ đó vào giới hạn thực thi. Không tuyên bố timeout chính xác tuyệt đối trong khi một node được phép dùng trạng thái cũ thêm nhiều phút.

## 5. Ví dụ về mốc thời gian

Giả sử hệ thống giả định chọn idle timeout là 15 phút và absolute timeout là 8 giờ. Những con số này chỉ minh họa cách đặc tả, không phải giá trị chuẩn áp dụng cho mọi ứng dụng.

| Thời điểm | Sự kiện | Hệ quả theo chính sách minh họa |
|---|---|---|
| 09:00 | Đăng nhập, tạo phiên | Mốc hoạt động ban đầu là 09:00, absolute deadline là 17:00 |
| 09:10 | Gửi yêu cầu nghiệp vụ hợp lệ | Idle deadline chuyển thành 09:25 |
| 09:20 | Polling thông báo tự động | Không thay đổi mốc hoạt động vì polling bị loại khỏi chính sách |
| 09:24:59 | Chỉ đọc trang đã tải, không có request hợp lệ mới | Không có cập nhật hoạt động phía server |
| 09:25 | Request nghiệp vụ được đưa đến điểm đánh giá phiên | Bị từ chối nếu quy tắc hết hạn là `now >= deadline` |
| 09:26 | Client gửi yêu cầu tiếp tục phiên cũ | Không được khôi phục phiên đã hết hạn chỉ bằng thao tác gia hạn |

Nếu một request hợp lệ khác được chấp nhận lúc 09:24, idle deadline có thể chuyển thành 09:39. Tuy nhiên, dù hoạt động tiếp tục cả ngày, phiên ban đầu vẫn không được vượt absolute deadline 17:00 nếu chính sách không quy định một quy trình tạo phiên mới sau xác thực phù hợp.

Thời điểm cập nhật hoạt động cần được chốt là lúc request được chấp nhận, hoàn tất hay một mốc cụ thể khác. Với request kéo dài, các cách chọn này tạo ra hành vi khác nhau và phải xuất hiện trong tình huống nghiệm thu.

## 6. Token, làm mới và đăng nhập liên kết

### 6.1. Access token có thể sống lâu hơn phiên

Một access token tự chứa có thể được dịch vụ đích kiểm tra chỉ bằng chữ ký và thời hạn của token. Nếu dịch vụ không kiểm tra trạng thái phiên, token vẫn có thể được chấp nhận sau khi phiên đã vượt idle timeout.

Để đáp ứng giới hạn thực tế, kiến trúc cần một cơ chế phù hợp, chẳng hạn kiểm tra trạng thái phiên tại điểm thực thi, sử dụng thông tin phiên bản hoặc thu hồi được kiểm tra, hoặc chọn thời hạn token và giới hạn độ trễ phù hợp với yêu cầu. Mỗi phương án có chi phí và giới hạn riêng.

Không được coi thao tác đổi trạng thái trong kho phiên là bằng chứng mọi token đã ngừng hiệu lực. Bằng chứng phải đến từ nơi chấp nhận request, trong phạm vi các dịch vụ được yêu cầu bảo vệ.

### 6.2. Làm mới không được bỏ qua idle timeout

Nếu ứng dụng tự làm mới token mỗi vài phút và mọi lần refresh đều được tính hoạt động, một tab nền có thể giữ phiên luôn hoạt động. Khi đó chính sách thực tế khác với ý định “người dùng không tương tác sẽ hết phiên”.

Endpoint refresh phải kiểm tra các điều kiện áp dụng cho phiên liên quan, không chỉ xem refresh token còn hạn hay không. Phiên đã hết idle deadline không được được hồi sinh bằng cùng thông tin làm mới nếu chính sách yêu cầu xác thực mới.

Các loại client không có tương tác người dùng, như một tác vụ máy chạy dài, nên có loại thông tin xác thực và vòng đời phù hợp. Không nên giả vờ chúng có hoạt động người dùng để né chính sách idle của phiên tương tác.

### 6.3. Phiên ứng dụng và phiên nhà cung cấp danh tính

Phiên tại ứng dụng và phiên tại hệ thống cung cấp đăng nhập có thể có thời hạn khác nhau. Sau khi ứng dụng hết phiên, một luồng đăng nhập liên kết có thể tạo phiên ứng dụng mới mà không yêu cầu người dùng nhập lại thông tin, nếu phiên bên cung cấp vẫn đáp ứng chính sách của nó.

Đặc tả cần quyết định đây có phải hành vi được phép hay không. Nếu mục tiêu là người dùng phải chứng minh lại sự hiện diện hoặc mức bảo đảm mới sau một khoảng nhàn rỗi, chỉ kết thúc phiên ứng dụng có thể chưa đủ. Cần nêu rõ điều kiện xác thực lại và độ mới cần thiết, thay vì mặc định việc chuyển hướng qua màn hình đăng nhập luôn có nghĩa người dùng đã xác thực lại.

Không phải mọi idle timeout đều bắt buộc nhập lại mật khẩu. Yêu cầu phụ thuộc mức rủi ro và chính sách xác thực; điều cần kiểm chứng là điều kiện tạo phiên mới đã được đáp ứng.

## 7. Nhiều tab, thiết bị và kết nối dài

### 7.1. Phạm vi của hoạt động

Nếu nhiều tab dùng chung một phiên cookie, hoạt động hợp lệ ở một tab thường tác động đến idle deadline chung. Một tab đang hiển thị cảnh báo cũ có thể không biết tab khác vừa gia hạn phiên. Frontend nên lấy lại trạng thái từ server thay vì dùng bộ đếm riêng để tự kết luận phiên đã hết hạn.

Các thiết bị thường cần phiên riêng. Hoạt động trên điện thoại không nên tự giữ phiên trên máy tính công cộng hoạt động nếu chính sách quy định idle theo từng phiên hoặc thiết bị. Nếu hệ thống chọn idle theo identity toàn cục, phải nêu rõ hệ quả này và lý do lựa chọn.

Thông báo giữa các tab giúp cập nhật giao diện nhưng chỉ là cơ chế hỗ trợ. Việc một tab không nhận được thông báo, bị trình duyệt tạm dừng hoặc mất mạng không được ảnh hưởng kết luận hết hạn của server.

### 7.2. WebSocket, streaming và tác vụ chạy lâu

Một kết nối vẫn mở không có nghĩa người dùng vẫn hoạt động. Ping, pong, heartbeat, dữ liệu server đẩy xuống và luồng tải dài cần được phân loại rõ. Nếu thông điệp nghiệp vụ trên kết nối được tính là hoạt động, server phải đánh giá trạng thái phiên và quyền cho loại thông điệp đó theo yêu cầu.

Đặc tả cần quyết định khi phiên hết hạn thì đóng kết nối, ngừng gửi dữ liệu được bảo vệ hay từ chối các thao tác mới. Chỉ kiểm tra phiên lúc bắt đầu kết nối có thể không đáp ứng yêu cầu dừng truy cập sau idle timeout.

Với một tác vụ đã được chấp nhận trước deadline, cần phân biệt thời hạn phiên với vòng đời tác vụ. Xuất báo cáo có thể được phép hoàn tất nhưng chỉ tải kết quả sau xác thực mới; một thao tác nhạy cảm có thể cần kiểm tra lại ngay trước khi cam kết thay đổi. Không yêu cầu hủy mọi công việc một cách mặc định mà chưa xác định tác động và tính nhất quán nghiệp vụ.

## 8. Giao diện cảnh báo và bảo toàn công việc

Giao diện có thể cảnh báo trước khi hết phiên và cung cấp thao tác tiếp tục. Bộ đếm chỉ phục vụ trải nghiệm; server vẫn quyết định phiên còn hợp lệ và có được gia hạn hay không.

Ví dụ, hệ thống giả định cảnh báo trước 2 phút. Khi người dùng bấm tiếp tục, server kiểm tra phiên tại thời điểm xử lý. Nếu đã hết hạn trong lúc request di chuyển hoặc chờ xử lý, server yêu cầu xác thực theo chính sách thay vì tin rằng nút được bấm trước đó.

Các yêu cầu trải nghiệm nên xác định:

- Cảnh báo phải nhận biết được bằng bàn phím và công nghệ hỗ trợ phù hợp.
- Giao diện cần cập nhật khi tab hoạt động trở lại sau khi bị tạm dừng hoặc thiết bị thức dậy.
- Không hiển thị thành công cho thao tác chỉ được lưu ở client trong khi server đã từ chối do hết phiên.
- Dữ liệu nhạy cảm đã tải cần được xử lý theo chính sách hiển thị và lưu trữ khi phiên hết hạn.
- Cơ chế giữ bản nháp không được lưu bí mật hoặc dữ liệu nhạy cảm vào vị trí không phù hợp chỉ để tránh mất nội dung.
- Sau xác thực mới, việc gửi lại thao tác thay đổi dữ liệu cần có cơ chế xác nhận và chống xử lý lặp phù hợp.

Hết phiên không thể thu hồi những dữ liệu người dùng đã tải xuống hoặc sao chép trước đó. Các yêu cầu bảo vệ dữ liệu phải phân biệt dừng quyền truy cập mới với xóa dữ liệu đã rời khỏi hệ thống.

## 9. Viết yêu cầu có thể kiểm chứng

Các giá trị trong bảng sau thuộc một ứng dụng giả định và cần điều chỉnh theo rủi ro, người dùng, loại thiết bị và kiến trúc thực tế.

| ID | Yêu cầu mẫu | Cách kiểm chứng dự kiến |
|---|---|---|
| IT-01 | Phiên tương tác phải bị từ chối tại điểm kiểm tra truy cập khi không có hoạt động hợp lệ trong 15 phút; thời điểm bằng deadline được tính là hết hạn. | Gửi request ngay trước, đúng và sau mốc giới hạn bằng thời gian kiểm soát được. |
| IT-02 | Chỉ các request nghiệp vụ thuộc danh sách được phép, đã xác thực và được phân quyền mới được cập nhật hoạt động; polling, heartbeat và tự refresh không được tính. | Phát từng loại request và đối chiếu mốc hoạt động cùng deadline tại server. |
| IT-03 | Client không được tự quyết định thời điểm hoạt động hoặc thay đổi deadline; trường thời gian tự khai không được gia hạn phiên. | Sửa đồng hồ client và gửi thời gian trong tương lai hoặc request gia hạn giả lập. |
| IT-04 | Phiên đã hết hạn hoặc thu hồi không được trở lại hợp lệ do request cập nhật hoạt động, refresh token hoặc bản ghi cache cũ. | Chạy đồng thời thu hồi với gia hạn, rồi phát lại request hoặc token cũ. |
| IT-05 | Absolute timeout 8 giờ phải giữ nguyên dù idle deadline được cập nhật nhiều lần. | Tạo hoạt động liên tục và gửi request tại absolute deadline. |
| IT-06 | Với các điểm thực thi dùng cache, thông tin phiên hết hạn hoặc thu hồi phải được áp dụng trong độ trễ tối đa 5 giây đã công bố; thành phần kiểm tra trực tiếp phải áp dụng deadline tại thời điểm đánh giá. | Gửi request qua nhiều node, gồm node có cache, trong cửa sổ sau deadline hoặc thu hồi. |
| IT-07 | Hoạt động trên một thiết bị không được gia hạn phiên của thiết bị khác; nhiều tab dùng cùng phiên phải áp dụng cùng idle deadline. | Tạo hai phiên trên hai thiết bị và nhiều tab trong một phiên để so sánh hành vi. |
| IT-08 | Giao diện phải cảnh báo trước 2 phút khi có thể quan sát trạng thái, nhưng request tiếp tục chỉ được chấp nhận nếu server xác nhận phiên còn hợp lệ. | Tạm dừng tab, đổi tab, trì hoãn mạng và bấm tiếp tục sát thời điểm hết hạn. |
| IT-09 | Đường dẫn refresh và kết nối dài phải kiểm tra điều kiện phiên theo chính sách; token chưa hết hạn không được tự bỏ qua idle timeout tại các điểm thực thi thuộc phạm vi. | Giữ kết nối hoặc refresh nền rồi thử thao tác sau idle deadline. |
| IT-10 | Khi kho phiên không khả dụng, thao tác quản trị được bảo vệ phải bị từ chối hoặc trả lỗi tạm thời theo contract; không được mặc định chấp nhận dựa trên việc không đọc được trạng thái. | Ngắt kết nối kho phiên và gửi thao tác quản trị qua từng đường truy cập. |
| IT-11 | Thay đổi cấu hình timeout phải có phiên bản, người thực hiện và quy tắc áp dụng cho phiên hiện hữu; giảm timeout không được làm mất dấu phiên cần hết hạn. | Giảm timeout trên hệ thống nhiều node và đối chiếu kết quả của các phiên đang tồn tại. |

IT-01 mô tả deadline của chính sách; IT-06 công khai một cửa sổ lan truyền ở thành phần dùng cache. Nếu rủi ro yêu cầu từ chối ngay tại deadline ở mọi nơi, kiến trúc phải loại bỏ cửa sổ đó hoặc cung cấp cơ chế kiểm tra đáp ứng được yêu cầu. Không được báo “15 phút chính xác” cho toàn hệ thống nếu thực tế còn một khoảng chấp nhận thêm.

Các thuật ngữ “trước deadline” và “sau deadline” phải dựa trên thời điểm đánh giá đã định. Việc kiểm chứng cần xét cả sai lệch đồng hồ và độ chính xác đo, không suy ra kết luận chỉ từ đồng hồ hiển thị trên trình duyệt.

## 10. Tình huống nghiệm thu quan trọng

Những tình huống dưới đây là đầu vào cho triển khai và kiểm chứng sau này, không phải kết quả kiểm thử đã thực hiện.

**Chỉ có polling nền:** Người dùng mở trang rồi rời đi, ứng dụng vẫn gọi API thông báo. Phiên phải hết theo chính sách nếu polling không thuộc hoạt động hợp lệ.

**Request đến đúng biên:** Mốc hoạt động gần nhất là 10:00 và idle timeout là 15 phút. Khi điểm kiểm tra sử dụng thời gian 10:15:00, request phải bị từ chối nếu chính sách chọn `>=`; không được ghi mốc hoạt động mới trước khi kiểm tra.

**Hai tab có thông tin khác nhau:** Tab A vừa thực hiện hoạt động hợp lệ, tab B đang hiển thị cảnh báo từ dữ liệu cũ. Tab B phải đồng bộ lại với trạng thái server thay vì tự đóng phiên còn hợp lệ hoặc tự gia hạn bằng trạng thái cũ.

**Refresh ngay sau hết hạn:** Refresh token vẫn còn hạn nhưng phiên liên quan đã hết idle timeout. Endpoint không được cấp token mới để tiếp tục phiên cũ nếu chính sách đòi hỏi xác thực mới.

**Thu hồi và cập nhật hoạt động chạy đồng thời:** Một quản trị viên thu hồi phiên trong lúc request nghiệp vụ cập nhật hoạt động. Không có thứ tự thực thi nào được phép làm thao tác cập nhật ghi đè cờ thu hồi và khôi phục phiên.

**Node có cache chậm:** Một node nhận biết phiên hết hạn, node khác còn bản cache. Các request tại node chậm phải tuân theo cửa sổ tối đa đã công bố; vượt cửa sổ là chưa đáp ứng yêu cầu.

**Tab hoặc thiết bị bị tạm dừng:** Thiết bị ngủ trong 30 phút nhưng bộ đếm JavaScript không chạy. Khi thức dậy, trạng thái phía server vẫn quyết định; việc bộ đếm chưa chạy hết không được duy trì quyền.

**Request kéo dài qua deadline:** Tác vụ bắt đầu khi phiên hợp lệ và kết thúc sau deadline. Hành vi cần khớp quy tắc đã chọn: tác vụ được phép hoàn tất, cần kiểm tra lại trước thay đổi nhạy cảm, hoặc yêu cầu xác thực mới để nhận kết quả.

**Đồng hồ client hoặc server thay đổi:** Đổi đồng hồ client không được kéo dài phiên. Bất thường đồng hồ phía server phải được phát hiện và xử lý theo thiết kế; một phiên đã hết hạn không được hồi sinh khi đồng hồ lùi.

**Đăng nhập liên kết tạo phiên mới:** Sau timeout ứng dụng, luồng đăng nhập có thể còn phiên bên cung cấp danh tính. Hệ thống phải kiểm chứng điều kiện tạo phiên mới và yêu cầu xác thực mới theo chính sách, không chỉ thấy chuyển hướng thành công rồi coi là đã đáp ứng.

## 11. Quan sát vận hành và tối ưu hóa

Ghi nhận sự kiện hết hạn nên cho phép phân biệt idle timeout, absolute timeout, thu hồi, lỗi kho phiên và lỗi xác thực. Có thể lưu mã liên kết hoặc biểu diễn an toàn của ID phiên, identity phù hợp phạm vi quan sát, thời điểm, phiên bản chính sách và điểm thực thi. Không ghi cookie phiên, bearer token hoặc bí mật làm mới vào log.

Các chỉ số hữu ích gồm số phiên hết hạn theo nguyên nhân, tỷ lệ request bị từ chối sau timeout, độ trễ lan truyền trạng thái, lỗi refresh do phiên hết hạn và số lỗi đọc kho phiên. Chỉ số frontend không thay thế được dữ liệu thực thi phía server.

Việc ghi mốc hoạt động cho mỗi request có thể tốn tài nguyên. Nếu tối ưu bằng cách gộp cập nhật, cần nêu rõ tác động: mốc lưu quá cũ có thể làm phiên hết sớm; TTL được kéo dài tùy tiện hoặc cache cũ có thể làm phiên sống lâu hơn dự kiến. Mọi sai số phải được giới hạn và nằm trong contract được chấp nhận, không được giấu sau mô tả “timeout khoảng 15 phút”.

Khi thay đổi chính sách, phải quyết định áp dụng ngay cho phiên hiện hữu hay chỉ phiên mới. Ví dụ, giảm timeout từ 30 xuống 15 phút có thể làm một số phiên cần hết hạn ngay. Các node phải biết cùng phiên bản chính sách hoặc có cách chuyển đổi được kiểm soát; chỉ thay giá trị ở một gateway không chứng minh mọi dịch vụ đã áp dụng.

## 12. Những lỗi đặc tả thường gặp

| Cách đặc tả hoặc triển khai | Vấn đề | Điều cần làm rõ |
|---|---|---|
| Chỉ đặt bộ đếm và chuyển trang ở frontend | Request trực tiếp vẫn có thể được chấp nhận | Kiểm tra deadline phía server tại điểm bảo vệ tài nguyên |
| Mọi request đều được tính hoạt động | Polling và refresh nền giữ phiên luôn sống | Danh sách sự kiện hợp lệ và quy tắc cập nhật |
| Gia hạn trước, kiểm tra hết hạn sau | Request muộn có thể hồi sinh phiên | Thứ tự đánh giá và cập nhật có kiểm soát cạnh tranh |
| Đồng nhất cookie hết hạn với phiên hết hạn | Trạng thái client và server có thể khác nhau | Phân biệt lưu cookie, trạng thái phiên và token |
| Cho phép refresh miễn token còn hạn | Bỏ qua giới hạn nhàn rỗi của phiên | Kiểm tra điều kiện phiên ở đường refresh |
| Chỉ kiểm tra lúc mở kết nối dài | Dữ liệu tiếp tục được truy cập sau timeout | Kiểm tra tiếp diễn và cách đóng hoặc giới hạn kết nối |
| Dọn bản ghi phiên theo lịch là đủ | Request có thể dùng phiên giữa các lần dọn | Từ chối theo deadline dù bản ghi chưa bị xóa |
| Không nêu phạm vi tab hoặc thiết bị | Hoạt động nơi khác kéo dài phiên ngoài ý định | Đơn vị tính idle: phiên, thiết bị hay identity |

Một yêu cầu idle timeout có thể kiểm chứng phải xác định hoạt động được tính, nguồn trạng thái có thẩm quyền, quy tắc biên, phạm vi phiên và giới hạn thực thi. Những chi tiết này quyết định liệu phiên thực sự ngừng cho phép truy cập hay chỉ biến mất khỏi giao diện.
