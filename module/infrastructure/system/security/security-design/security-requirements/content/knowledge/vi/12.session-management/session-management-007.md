# Absolute timeout

## 1. Giới hạn tuổi tuyệt đối của phiên

Absolute timeout là giới hạn thời gian tối đa mà một phiên được phép tồn tại, tính từ một mốc khởi đầu được chính sách xác định. Khi đạt giới hạn này, hoạt động liên tục của người dùng không làm phiên tiếp tục có hiệu lực.

Ví dụ, một ứng dụng đặt tuổi phiên tối đa 8 giờ. Nếu phiên bắt đầu lúc 08:00, phiên phải hết hiệu lực lúc 16:00 theo ngữ nghĩa thời gian đã quy định, dù người dùng vẫn làm việc, client vẫn gửi request và access token được refresh đều đặn.

Mục tiêu bảo mật là giới hạn thời gian tồn tại của một quan hệ tin cậy đã được thiết lập. Nếu credential bị đánh cắp hoặc phiên được giữ hoạt động bằng tự động hóa, kẻ tấn công không thể chỉ tạo lưu lượng để duy trì phiên đó vô hạn.

Absolute timeout không chứng minh người dùng hợp lệ đang hiện diện và không thay thế thu hồi khi phát hiện sự cố. Nó cung cấp một giới hạn cuối cùng cho phiên theo chính sách; những cơ chế khác có thể chấm dứt phiên sớm hơn.

Trong thiết kế yêu cầu bảo mật, cần trả lời đầy đủ bốn câu hỏi:

1. Giới hạn áp dụng cho phiên hoặc ngữ cảnh tin cậy nào?
2. Mốc bắt đầu được tạo ở sự kiện nào và có được thay đổi không?
3. Những điểm nào phải từ chối quyền truy cập khi hết hạn?
4. Điều kiện nào cho phép bắt đầu một phiên mới?

Chỉ ghi “session timeout = 8 giờ” chưa đủ để các nhóm triển khai và kiểm chứng hiểu giống nhau.

## 2. Phân biệt với các loại thời hạn khác

| Cơ chế | Mốc tính | Hoạt động có thể kéo dài không? | Mục đích |
| --- | --- | --- | --- |
| Idle timeout | Hoạt động được chính sách công nhận gần nhất | Có, theo định nghĩa hoạt động | Hạn chế phiên bị bỏ quên |
| Absolute timeout | Mốc gốc của phiên được định nghĩa | Không, đối với cùng phiên đó | Giới hạn tổng tuổi phiên |
| Access token expiry | Thời điểm phát hành hoặc mốc hết hạn của token | Token cũ không tự kéo dài; có thể cấp token mới | Giới hạn thời gian dùng credential truy cập |
| Refresh token expiry | Mốc của token hoặc chuỗi refresh theo chính sách | Tùy thiết kế, nhưng không được vượt giới hạn phiên đã cam kết | Giới hạn khả năng xin credential mới |
| Thời hạn xác thực gần đây | Sự kiện xác thực đạt mức yêu cầu | Chỉ thay đổi khi có sự kiện được công nhận | Điều kiện cho hành động nhạy cảm |
| Thu hồi phiên | Sự kiện vô hiệu hóa | Không phải cơ chế gia hạn | Chấm dứt trước thời hạn vì logout, khóa hoặc sự cố |

Một access token sống 10 phút không có nghĩa người dùng phải đăng nhập lại sau 10 phút. Nếu refresh token tiếp tục cấp access token, phiên logic có thể tồn tại lâu hơn nhiều.

Ngược lại, một refresh token sống 30 ngày không tự cho phép phiên hoạt động 30 ngày nếu chính sách yêu cầu giới hạn tuyệt đối 8 giờ. Hệ thống phải định nghĩa cách các thời hạn kết hợp và thực thi kết quả đó.

### Thời điểm phiên thực sự mất hiệu lực

Với một phiên chịu nhiều điều kiện, có thể mô tả:

~~~text
Phiên còn hiệu lực khi đồng thời:
- Chưa bị thu hồi.
- Chưa vượt thời hạn không hoạt động.
- Chưa đạt thời hạn tuyệt đối.
- Những điều kiện bắt buộc khác vẫn được đáp ứng.
~~~

Phiên có thể hết hạn sớm hơn giới hạn tuyệt đối do idle timeout hoặc bị khóa. Absolute timeout là trần, không phải lời hứa rằng phiên chắc chắn hoạt động đến hết khoảng thời gian đó.

## 3. Xác định đúng đối tượng và mốc gốc

### 3.1. Phiên logic không đồng nghĩa một cookie hoặc token

Một phiên logic có thể bao gồm nhiều access token nối tiếp, một chuỗi refresh token và nhiều lần thay mã cookie. Nếu tính tuổi từ credential mới nhất, hệ thống có thể vô tình biến giới hạn tuyệt đối thành giới hạn trượt.

Cần phân biệt:

- Mã credential dùng trong request.
- Định danh phiên logic.
- Mốc bắt đầu phiên.
- Thời điểm phát hành credential hiện tại.
- Thời điểm người dùng xác thực đạt một mức cụ thể.

Ví dụ:

~~~text
08:00  Người dùng xác thực đầy đủ, tạo phiên S
08:10  Cấp access token mới cho S
09:00  Thay mã cookie của S
12:00  Refresh token được rotation
16:00  S đạt tuổi tối đa 8 giờ
~~~

Nếu chính sách là 8 giờ cho phiên S, các thao tác 08:10, 09:00 và 12:00 không thay đổi mốc 08:00.

### 3.2. Mốc bắt đầu phải có ngữ nghĩa rõ ràng

Một lựa chọn phổ biến là thời điểm server xác nhận hoàn tất quá trình xác thực cần thiết và tạo phiên đã xác thực. Nhưng hệ thống có thể có nhiều bước đăng nhập, liên kết danh tính hoặc nâng quyền, nên tài liệu phải mô tả chính xác sự kiện.

Không lấy thời điểm client mở trang, gửi request hay cung cấp một trường thời gian làm nguồn tin cậy để quyết định tuổi phiên.

Ví dụ một yêu cầu rõ:

> Mốc bắt đầu của phiên ứng dụng là thời điểm hệ thống xác nhận hoàn tất xác thực bắt buộc và tạo phiên đã xác thực. Mốc này không thay đổi trong mọi lần gia hạn credential của cùng phiên.

Nếu phiên ẩn danh được tạo từ trước, cần xác định phiên đã xác thực có mốc riêng. Không để thời gian giữ giỏ hàng trước đăng nhập vô tình quyết định tuổi đăng nhập, trừ khi đó là chính sách được chủ động lựa chọn.

### 3.3. Khi nào được tạo mốc mới?

Đăng nhập lại đáp ứng đầy đủ yêu cầu có thể tạo một phiên mới với tuổi tuyệt đối mới. Đây là hành vi có chủ đích, không phải kéo dài cùng phiên một cách ngầm định.

Yêu cầu nên mô tả:

- Những bằng chứng nào phải được xác minh.
- Sự kiện nào được coi là xác thực mới đủ điều kiện.
- Phiên cũ có bị chấm dứt hay được quản lý độc lập.
- Cách liên kết lịch sử audit giữa các phiên.
- Quyền và tenant được đánh giá lại ra sao.

Một lần refresh, rotation hoặc đổi mã phiên không tự chứng minh người dùng vừa xác thực lại.

Xác thực bổ sung cho một hành động nhạy cảm cũng không mặc nhiên đặt lại tuổi toàn bộ phiên. Nếu muốn nó khởi tạo phiên mới, phải đặc tả rõ phạm vi và mức xác thực cần đạt, thay vì suy diễn từ việc có một bước MFA thành công.

## 4. Mô hình thời gian và các bất biến

Ký hiệu:

- T0: mốc bắt đầu phiên.
- L: tuổi tuyệt đối tối đa.
- D: thời điểm hết hạn tuyệt đối.
- N: thời điểm server dùng để quyết định yêu cầu.

~~~text
D = T0 + L

Nếu N >= D:
    phiên không còn được chấp nhận
~~~

Trong ví dụ này, khoảng có hiệu lực là từ T0 đến trước D; đúng tại D đã là hết hạn. Việc chọn dấu so sánh phải được thống nhất giữa nơi cấp và nơi kiểm tra credential.

Các bất biến quan trọng:

1. T0 không được cập nhật bởi request thông thường.
2. Rotation và refresh không làm D của cùng phiên tăng lên.
3. Credential mới không cho phép truy cập sau D.
4. Client không được tự khai D để kéo dài phiên.
5. Việc xóa bản ghi phiên chỉ là dọn dữ liệu, không phải cách duy nhất phát hiện hết hạn.
6. Phiên đã hết hạn không được làm sống lại bởi cập nhật last activity hoặc khôi phục trạng thái cũ.

### Kết hợp với idle timeout

Nếu idle timeout là I và mốc hoạt động cuối là A:

~~~text
idleDeadline = A + I
absoluteDeadline = T0 + L
effectiveDeadline = min(idleDeadline, absoluteDeadline)
~~~

Hoạt động được công nhận có thể làm idleDeadline tiến về sau. Nó không làm absoluteDeadline thay đổi.

Ví dụ phiên bắt đầu 08:00, tuổi tối đa 8 giờ, idle timeout 15 phút. Người dùng có hoạt động lúc 15:55; idleDeadline có thể là 16:10, nhưng effectiveDeadline vẫn không muộn hơn 16:00.

### Nguồn thời gian

Thời gian hiển thị trên trình duyệt phục vụ trải nghiệm, không phải căn cứ cho server quyết định quyền. Người dùng đổi múi giờ hoặc đồng hồ thiết bị không được kéo dài phiên.

Trong hệ thống nhiều node, cần xác định nguồn thời gian, giới hạn sai lệch được chấp nhận và cách phản ứng nếu sai lệch vượt ngưỡng. Có thể lưu mốc dạng thời gian tuyệt đối thống nhất để tránh nhập nhằng về múi giờ và thời điểm đổi giờ địa phương.

Không nên mô tả chính sách bằng “đến cuối ngày” nếu mục tiêu thật sự là “sau 8 giờ”. Hai cách này tạo tuổi phiên khác nhau tùy giờ đăng nhập và cách xác định ngày.

Các bộ đếm thời gian cũng phải được thiết kế để không kéo dài hạn khi đồng hồ hệ thống điều chỉnh hoặc tiến trình khởi động lại. Yêu cầu nêu kết quả cần bảo đảm; thiết kế chọn cách phối hợp đồng hồ và mốc lưu bền phù hợp.

## 5. Bảo đảm refresh và rotation không vượt trần

### 5.1. Giới hạn thời hạn credential mới

Giả sử access token có thời gian sống mục tiêu là V. Một cách thể hiện ràng buộc cấp mới là:

~~~text
newAccessTokenExpiry <= min(N + V, D)
~~~

Nếu phiên chỉ còn 2 phút và access token thông thường sống 10 phút, token mới không được cho phép truy cập thêm 10 phút vượt qua D.

Thiết kế có thể chọn không cấp token khi thời gian còn lại quá ngắn để dùng có ý nghĩa. Khi đó cần trả về trạng thái yêu cầu xác thực lại theo chính sách, thay vì tự dời D.

Điểm kiểm tra tài nguyên vẫn cần xác minh các điều kiện bắt buộc. Một token được ký đúng không tự chứng minh nhà cấp đã áp đúng giới hạn tuổi phiên.

### 5.2. Refresh token rotation

Khi refresh token được thay, token mới vẫn thuộc phiên logic hoặc chuỗi đăng nhập có mốc gốc đã xác định. Nếu mỗi lần rotation lại đặt hạn mới từ thời điểm hiện tại mà không có trần chung, một chuỗi refresh có thể kéo dài vô hạn.

Yêu cầu cần áp giới hạn ở cả:

- Đường xin access token.
- Đường cấp refresh token thay thế.
- Đường chấp nhận credential ở tài nguyên được bảo vệ.
- Các API hoặc luồng cấp lại có khả năng tạo credential tương đương.

Không chỉ kiểm tra luồng refresh chính trong khi bỏ sót luồng “tiếp tục phiên” hoặc tự đăng nhập lại bằng cookie dài hạn.

### 5.3. Cookie expiry và thời hạn server

Cookie có thời hạn ở trình duyệt hỗ trợ quản lý credential phía client, nhưng server vẫn phải từ chối phiên hết hạn. Client có thể giữ hoặc gửi bản sao credential theo cách khác.

Tương tự, một tác vụ dọn phiên chạy mỗi 5 phút không phải lý do để phiên được chấp nhận thêm tối đa 5 phút. Nếu yêu cầu là hết hạn tại D, đường xử lý request phải kiểm tra hạn, dù bản ghi chưa bị xóa.

### 5.4. Dung sai thời gian không được trở thành gia hạn bí mật

Một số cơ chế xác minh credential có dung sai đồng hồ. Nếu token được chấp nhận thêm sau hạn ghi trong token, cần đánh giá tác động lên trần phiên.

Không đồng thời khẳng định “không request nào được chấp nhận sau D” và cho phép điểm kiểm tra bỏ qua D trong một khoảng không được công bố.

Có thể kiểm tra D riêng bằng ngữ nghĩa chặt hoặc nêu rõ giới hạn sai lệch trong chính sách thời gian. Điều quan trọng là yêu cầu và phép đo phản ánh đúng hành vi được cam kết.

## 6. Đăng nhập liên kết và cơ chế “ghi nhớ đăng nhập”

Một ứng dụng có thể hết phiên riêng nhưng nhà cung cấp danh tính vẫn giữ phiên đăng nhập. Nếu ứng dụng tự tạo ngay phiên mới từ trạng thái đó, người dùng có thể không trải qua một sự kiện xác thực mới.

Cần phân biệt hai mục tiêu:

- Giới hạn thời gian tồn tại của từng phiên ứng dụng.
- Giới hạn thời gian từ lần xác thực người dùng đạt mức tin cậy được yêu cầu.

Một hệ thống chỉ cần mục tiêu thứ nhất có thể cho phép tạo phiên ứng dụng mới từ phiên của nhà cung cấp danh tính, nếu chính sách đã chấp thuận. Nhưng nếu mục tiêu là bắt buộc xác thực mới sau 8 giờ, việc tạo cookie ứng dụng mới không đủ.

Yêu cầu cần chỉ rõ:

1. Mốc xác thực nào được chấp nhận từ nhà cung cấp danh tính.
2. Cách bảo đảm dữ kiện đó có nguồn gốc và tính toàn vẹn đáng tin cậy.
3. Tuổi tối đa của dữ kiện xác thực.
4. Điều kiện yêu cầu người dùng xác thực lại.
5. Hành vi nếu nhà cung cấp không cung cấp đủ bằng chứng.

Việc client gửi một tham số yêu cầu xác thực mới không tự chứng minh xác thực mới đã xảy ra. Bên nhận phải kiểm tra kết quả theo giao thức và chính sách của mình.

Cookie “remember me” cũng cần quy tắc tương tự. Nếu cookie dài hạn tự tạo phiên mới sau khi phiên cũ hết hạn, phải đánh giá xem hành vi đó có đáp ứng mục tiêu tái xác thực hay đang né nó.

Trong một hệ thống có yêu cầu chặt về tuổi xác thực, có thể dùng cookie ghi nhớ để nhận diện tài khoản hoặc hỗ trợ luồng đăng nhập mà vẫn yêu cầu bằng chứng cần thiết trước khi cấp quyền trở lại.

## 7. Điểm thực thi trong kiến trúc

### 7.1. Phiên có trạng thái ở server

Với mã phiên opaque, bản ghi phía server có thể chứa mốc bắt đầu, hạn tuyệt đối, thời điểm hoạt động cuối và trạng thái thu hồi.

Các thuộc tính thời gian cần được bảo vệ khỏi cập nhật ngoài chính sách. Không cho phép API “cập nhật phiên” thay mốc gốc theo giá trị client cung cấp.

Nơi đọc bản ghi phải kiểm tra hạn ở đường truy cập thực tế. Việc một bản ghi còn trong cache hoặc cơ sở dữ liệu không đồng nghĩa phiên còn hiệu lực.

### 7.2. Token được xác minh tại chỗ

Một token chứa hạn dùng và dữ kiện phiên có thể giúp điểm nhận kiểm tra giới hạn mà không tra trạng thái mỗi request. Điều này không loại bỏ yêu cầu kiểm soát mốc gốc, thời hạn cấp mới và chính sách thu hồi riêng.

Nếu thiết kế dựa vào token hết hạn không muộn hơn D, cần chứng minh:

- Mọi đường phát hành đều áp trần.
- Token không thể bị sửa thời hạn hoặc liên kết sang phiên khác.
- Mọi nơi nhận kiểm tra đúng điều kiện.
- Dung sai thời gian không vượt cam kết.
- Phiên không bị tạo mới âm thầm để kéo dài cùng chuỗi tin cậy.

Absolute timeout không bắt buộc một kiến trúc lưu trạng thái duy nhất. Yêu cầu là kết quả bảo mật; lựa chọn trạng thái tập trung, kiểm tra token hoặc kết hợp phải có bằng chứng đáp ứng.

### 7.3. Gateway và backend

Nếu gateway thực thi timeout, cần xác định backend có thể được gọi theo đường khác hay không. Một đường nội bộ bỏ qua gateway có thể trở thành đường né kiểm soát.

Backend chỉ được tin ngữ cảnh phiên chuyển tiếp qua cơ chế đã được bảo vệ. Một header tự khai “phiên còn hạn” từ client không phải bằng chứng.

Nếu nhiều tầng cache quyết định xác thực, mỗi tầng phải biết hạn không được vượt. Cache có thời gian sống dài không được biến quyết định “hợp lệ trước D” thành “hợp lệ sau D”.

### 7.4. Khởi động lại và phục hồi

Mốc gốc không được đặt lại thành thời điểm node khởi động hoặc khôi phục bản ghi. Nếu không, restart có thể làm phiên cũ nhận thêm một tuổi tối đa mới.

Khi không lấy được mốc hoặc không xác minh được tính hợp lệ cần thiết, không được tự tạo một mốc mới để tiếp tục phiên. Hành vi có thể là yêu cầu đăng nhập lại hoặc từ chối theo chính sách lỗi.

Khôi phục từ backup cũng cần giữ đúng ngữ nghĩa thời gian. Một phiên tồn tại trong bản sao cũ nhưng hiện đã hết hạn vẫn phải bị từ chối.

### 7.5. Phiên gốc và ngữ cảnh nâng quyền

Nếu người dùng có phiên thường và một ngữ cảnh quản trị ngắn hạn, có thể có hai giới hạn:

~~~text
parentDeadline = hạn tuyệt đối của phiên gốc
privilegeDeadline = thời điểm nâng quyền + thời hạn quyền đặc biệt

effectivePrivilegeDeadline = min(parentDeadline, privilegeDeadline)
~~~

Cách kết hợp này phù hợp khi quyền đặc biệt phụ thuộc vào cùng phiên gốc. Nếu quy trình xác thực đầy đủ tạo ra một phiên quản trị độc lập, chính sách phải mô tả nó như một quan hệ tin cậy mới và quản lý vòng đời riêng.

Không dùng bước nâng quyền để âm thầm đặt lại tuổi của phiên gốc trong khi tài liệu vẫn mô tả tuổi gốc là bất biến.

## 8. Request đang chạy và kết nối lâu dài

### 8.1. Quyền bắt đầu khác quyền tiếp tục

Một request có thể được chấp nhận lúc 15:59:59 và xử lý hoàn tất lúc 16:00:03, trong khi hạn là 16:00. Không có một kết quả mặc định phù hợp với mọi nghiệp vụ.

Cần xác định yêu cầu áp dụng ở điểm nào:

- Khi nhận và xác thực request.
- Trước khi thực hiện hành động nhạy cảm.
- Trước khi commit một thay đổi.
- Trong suốt quá trình gửi dữ liệu liên tục.

Nếu chính sách chỉ yêu cầu không chấp nhận request mới sau D, request đã được cho phép trước D có thể được xử lý tiếp theo chính sách giao dịch. Nếu yêu cầu chặt hơn, cần kiểm tra lại hoặc cơ chế dừng phù hợp.

Không suy diễn rằng hết hạn phiên phải hoàn tác mọi giao dịch đã hoàn thành. Khả năng hủy và tính toàn vẹn giao dịch là các yêu cầu riêng cần phối hợp.

### 8.2. WebSocket, stream và kết nối dài

Một kết nối đã xác thực từ đầu có thể tồn tại lâu hơn tuổi phiên. Nếu chỉ kiểm tra khi bắt tay, hệ thống có thể tiếp tục gửi dữ liệu sau D.

Yêu cầu phải nêu:

- Có đóng kết nối tại hạn hay không.
- Có ngừng nhận hoặc xử lý thông điệp mới sau hạn không.
- Có ngừng phát dữ liệu được bảo vệ không.
- Độ trễ tối đa được phép.
- Cách thiết lập kết nối mới sau xác thực lại.

Một thông báo giao diện “phiên đã hết hạn” không chứng minh kết nối server đã dừng quyền truy cập.

### 8.3. Job bất đồng bộ

Một tác vụ có thể được gửi khi phiên còn hạn rồi chạy sau đó. Cần quyết định job thực thi theo quyền dịch vụ, quyền được ủy quyền tại lúc gửi hay quyền được kiểm tra lại lúc thực thi.

Không chuyển nguyên session credential vào hàng đợi để job tiếp tục giả làm phiên của người dùng sau hạn. Yêu cầu ủy quyền tác vụ cần có phạm vi, thời hạn và audit riêng.

Tuổi phiên của người dùng và thời hạn được phép của một job đã phê duyệt có thể khác nhau; sự khác biệt phải được nêu rõ, không được dùng như một đường vòng không kiểm soát.

## 9. Bộ yêu cầu minh họa

Giả sử ứng dụng chọn tuổi tuyệt đối 8 giờ, mốc gốc là lúc hoàn tất xác thực bắt buộc và yêu cầu xác thực mới đủ điều kiện trước khi bắt đầu phiên tiếp theo. Ngưỡng này chỉ phục vụ ví dụ, không phải thời hạn bắt buộc cho mọi hệ thống.

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| AT-01 | Mọi phiên đã xác thực có mốc gốc và hạn tuyệt đối được xác định từ nguồn tin cậy | Không tạo phiên thiếu hạn; sửa dữ kiện từ client không kéo dài được hạn |
| AT-02 | Cùng một phiên không được đổi mốc gốc bởi request thường, polling, refresh hoặc rotation | Sau chuỗi hoạt động và thay credential, mốc gốc cùng hạn vẫn giữ nguyên |
| AT-03 | Mọi request mới đến API được bảo vệ tại hoặc sau hạn bị từ chối theo mô hình thời gian đã định | Request trước hạn, đúng hạn và sau hạn cho kết quả đúng trên mọi điểm thực thi |
| AT-04 | Access token và refresh token cấp mới không cho phép truy cập vượt hạn của phiên | Xin credential gần hạn không tạo quyền có hiệu lực vượt trần; sau hạn không cấp mới cho phiên cũ |
| AT-05 | Hết phiên ở ứng dụng không được tự né yêu cầu xác thực mới qua SSO hoặc cookie ghi nhớ | Tạo lại cookie từ trạng thái đăng nhập cũ không đủ điều kiện nếu thiếu bằng chứng xác thực mới theo chính sách |
| AT-06 | Node restart, thay tuyến và phục hồi trạng thái không làm tăng tuổi phiên | Phiên giữ nguyên hạn trên node khác và sau khởi động; phiên đã hết hạn vẫn bị từ chối |
| AT-07 | Cache không được giữ quyết định cho phép qua hạn tuyệt đối | Cache nóng trước hạn không cho phép request mới sau hạn |
| AT-08 | Kết nối truyền dữ liệu liên tục phải ngừng cấp dữ liệu được bảo vệ trong thời hạn đã phê duyệt sau D | Đo trên kết nối mở trước D; không chỉ kiểm tra bắt tay kết nối mới |
| AT-09 | Client cảnh báo trước hạn khi có thể, nhưng không có quyền thay đổi hạn | Đổi đồng hồ, tắt JavaScript hoặc bỏ cảnh báo không kéo dài quyền server |
| AT-10 | Audit liên kết được sự kiện hết hạn với phiên logic mà không ghi credential nguyên giá trị | Điều tra được mốc, hạn, điểm thực thi và lý do từ chối bằng mã tham chiếu audit |

AT-08 cần một ngưỡng cụ thể trong đặc tả triển khai, ví dụ tối đa 5 giây cho một loại stream đã được đánh giá rủi ro. Không dùng cụm “trong thời hạn đã phê duyệt” làm yêu cầu cuối cùng mà không chốt thời hạn và owner.

Nếu AT-03 yêu cầu chặn request mới đúng tại D trong mô hình thời gian server, AT-08 có thể quy định một thời hạn khác cho việc kết thúc stream. Hai phạm vi phải được phân biệt; không dùng độ trễ stream để cho phép mọi request mới đi qua sau D.

### Mẫu đặc tả chi tiết

~~~yaml
requirement_id: AT-03
subject: Phiên ứng dụng đã xác thực
scope:
  - Mọi API được bảo vệ của ứng dụng
  - Mọi node, gateway và đường truy cập được phép
origin_event: Server xác nhận hoàn tất xác thực bắt buộc
maximum_session_age_seconds: 28800
deadline_rule: origin_time + maximum_session_age_seconds
expiry_boundary: request_decision_time >= deadline
origin_may_change_on:
  - Không thay đổi đối với cùng phiên logic
required_behavior: Từ chối request mới của phiên đã đạt hạn
refresh_effect: Không đặt lại origin_time hoặc tăng deadline
verification:
  - Giữ hoạt động liên tục trong môi trường kiểm chứng
  - Cấp và rotation credential gần hạn
  - Kiểm tra trước hạn, đúng hạn và sau hạn
  - Lặp trên mọi điểm thực thi trong phạm vi
owner: Nhóm ứng dụng và nền tảng identity
~~~

Đây là mẫu nội dung yêu cầu, không phải cấu hình thư viện. Đặc tả còn phải chốt mô hình thời gian, ngưỡng sai lệch và cách xử lý lỗi phù hợp với hệ thống thực tế.

## 10. Ví dụ một phiên từ lúc tạo đến lúc hết hạn

Xét phiên S bắt đầu lúc 08:00, tuổi tối đa 8 giờ, idle timeout 15 phút và access token có thời gian sống mục tiêu 10 phút.

| Thời điểm | Sự kiện | Kết quả theo chính sách |
| --- | --- | --- |
| 08:00 | Xác thực thành công | Tạo S với D = 16:00 |
| 10:00 | Rotation credential | Credential đổi; T0 và D của S giữ nguyên |
| 15:55 | Refresh thành công | Credential truy cập mới không được vượt D |
| 15:59 | Hoạt động hợp lệ | Idle deadline có thể tiến lên, nhưng D vẫn 16:00 |
| 16:00 | Request mới dùng credential của S | Từ chối vì đạt tuổi tuyệt đối |
| 16:01 | Thử refresh S | Không cấp quyền tiếp tục S |
| 16:02 | Thử tự tạo phiên mới từ dữ kiện xác thực quá cũ | Không đáp ứng yêu cầu xác thực mới của ví dụ |
| 16:03 | Hoàn tất xác thực mới đủ điều kiện | Có thể tạo phiên mới theo chính sách, với mốc gốc mới |

Điểm quan trọng không phải token được phát hành gần 16:00 hay người dùng đã click bao nhiêu lần. Quyết định dựa vào quan hệ giữa request, phiên logic và hạn được bảo vệ.

Một client có lỗi vẫn có thể giữ credential của S trong bộ nhớ. Điều đó không được làm server tiếp tục chấp nhận S.

## 11. Kế hoạch kiểm chứng theo rủi ro

### 11.1. Ca ranh giới độc lập

Với hạn D, kiểm tra quyết định tại D trừ một khoảng nhỏ, đúng D và sau D. Trong kiểm chứng có thể điều khiển thời gian theo cơ chế được thiết kế cho môi trường thử nghiệm; không cần chờ đủ 8 giờ cho mọi ca.

Nếu đang kiểm tra đồng thời idle timeout, request thử ngay trước hạn có thể cập nhật hoạt động. Cần tách ca hoặc kiểm soát hoạt động để không nhầm tác động của idle với absolute timeout.

Không điều chỉnh đồng hồ client rồi kết luận server đã tuân thủ tuổi phiên. Phải kiểm chứng điểm quyết định sử dụng thời gian tin cậy.

### 11.2. Chuỗi làm mới liên tục

Tạo phiên, phát sinh hoạt động đều và refresh hoặc rotation nhiều lần trước D. Xác minh:

- Hạn của cùng phiên không trượt.
- Token mới gần hạn không vượt trần.
- Mọi đường cấp lại đều áp cùng giới hạn.
- Refresh sau D bị từ chối.
- Đổi mã phiên không làm mất liên kết với mốc gốc.

Ca này phát hiện lỗi thường bị bỏ sót khi chỉ kiểm tra một token đơn lẻ hết hạn.

### 11.3. Các đường né qua trạng thái khác

Kiểm tra SSO, cookie ghi nhớ, chuyển tenant, nâng quyền, mở tab mới và khởi động lại ứng dụng client. Nếu những thao tác đó không phải xác thực mới đủ điều kiện, chúng không được tự kéo dài cùng chuỗi tin cậy theo chính sách đang kiểm chứng.

Nếu hệ thống chủ động cho phép một loại xác thực mới bắt đầu phiên mới, cần kiểm chứng đúng điều kiện đó thay vì cấm mọi phiên mới sau D.

### 11.4. Phân tán, lỗi và phục hồi

Bao gồm các ca:

- Request trước hạn đi qua node A, request sau hạn đi qua node B.
- Cache được làm nóng ngay trước D.
- Node khởi động lại sau D với dữ liệu phiên còn tồn tại.
- Phục hồi bản ghi phiên từ snapshot cũ.
- Nguồn trạng thái hoặc dữ kiện thời gian bắt buộc không sẵn sàng.
- Đồng hồ node lệch trong và ngoài giới hạn đã định.
- Client gửi lại credential cũ sau khi thấy giao diện hết hạn.

Mục tiêu là chứng minh điểm thực thi không tự tạo thêm thời gian cho phiên khi gặp thay đổi vận hành.

### 11.5. Hành động chạy qua hạn

Kiểm tra riêng request được chấp nhận trước D nhưng commit sau D, stream đang mở và job đang chờ. Kết quả mong đợi phải theo hợp đồng từng loại hành động.

Không coi một stream tiếp tục gửi dữ liệu là hợp lệ chỉ vì request mở stream diễn ra trước D, nếu yêu cầu đã giới hạn việc cấp dữ liệu đến D hoặc một ngưỡng cụ thể sau D.

## 12. Trải nghiệm khi phiên hết tuổi

Client có thể nhận thời điểm hết hạn phù hợp để cảnh báo, hiển thị đồng hồ đếm ngược hoặc chuẩn bị lưu bản nháp. Dữ kiện hiển thị không được trở thành nguồn quyết định quyền.

Một luồng phù hợp có thể gồm:

1. Cảnh báo trước hạn nếu client đang hoạt động.
2. Hỗ trợ lưu bản nháp theo chính sách dữ liệu.
3. Khi hết hạn, dừng thao tác cần quyền và yêu cầu xác thực lại.
4. Sau xác thực mới, kiểm tra lại quyền trước khi khôi phục màn hình hoặc gửi hành động.
5. Không tự phát lại một thao tác nhạy cảm chỉ vì phiên mới đã được tạo.

Thao tác lưu bản nháp lên server cũng cần phiên hợp lệ hoặc một cơ chế riêng được phép. Không mặc định có thể tiếp tục lưu mọi dữ liệu sau khi phiên đã hết hạn.

Nếu hệ thống có “thời gian ân hạn”, phải định nghĩa nó có quyền gì. Một khoảng chỉ cho phép hiển thị thông báo hoặc lưu cục bộ không đồng nghĩa gia hạn quyền truy cập. Nếu khoảng đó vẫn cho phép API được bảo vệ, nó là một phần thực tế của tuổi truy cập và phải được phản ánh trong yêu cầu.

## 13. Audit và vận hành

Một sự kiện hết hạn nên liên kết được với mã phiên phục vụ audit, chủ thể, mốc gốc, hạn, thời điểm quyết định, điểm thực thi và lý do từ chối.

Không ghi access token, refresh token hoặc session ID có thể dùng trực tiếp để xác thực. Có thể dùng định danh audit riêng hoặc tham chiếu được bảo vệ phù hợp.

Các chỉ số hữu ích gồm số phiên hết tuổi, số lần refresh bị từ chối vì đạt trần và tỷ lệ người dùng phải xác thực lại giữa thao tác. Những chỉ số này giúp đánh giá trải nghiệm và lỗi cấu hình, nhưng không phải lý do tự động kéo dài tuổi phiên.

Khi thay chính sách tuổi tối đa, cần xác định tác động lên phiên đang tồn tại. Chẳng hạn, giảm từ 8 giờ xuống 4 giờ có áp ngay cho phiên cũ không, áp ở lần kiểm tra tiếp theo hay chỉ áp với phiên tạo mới? Quyết định phải được đặc tả, có owner và bằng chứng triển khai.

Nếu phiên được gia hạn ngoài chính sách, cần điều tra cả đường phát hành credential, cách đặt lại mốc, cache và luồng đăng nhập liên kết. Chỉ sửa đồng hồ đếm ngược trên giao diện không xử lý được nguyên nhân.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao không đáp ứng absolute timeout |
| --- | --- |
| Đặt lại thời điểm bắt đầu ở mỗi request | Biến tuổi tuyệt đối thành giới hạn trượt |
| Tính tuổi từ access token mới nhất | Refresh liên tục làm phiên không đạt tuổi tối đa |
| Chỉ đặt thời hạn cookie | Bản sao credential vẫn có thể được gửi đến server |
| Chỉ xóa phiên bằng job dọn định kỳ | Có thể chấp nhận phiên quá hạn trước lần dọn tiếp theo |
| Cho token mới sống trọn thời hạn mặc định khi gần D | Credential có thể cho phép truy cập vượt trần |
| Đặt lại mốc khi node khởi động | Thay đổi vận hành kéo dài tuổi phiên |
| Tự tạo phiên mới từ SSO mà không xét mục tiêu tuổi xác thực | Có thể né yêu cầu xác thực mới |
| Chỉ kiểm tra lúc mở kết nối | Stream hoặc kết nối dài tiếp tục có quyền ngoài hạn |
| Gọi khoảng truy cập thêm là “grace period” nhưng không ghi vào chính sách | Cam kết tuổi phiên không khớp quyền truy cập thực tế |

Absolute timeout cần được mô tả như một bất biến của quan hệ tin cậy được xác định rõ, rồi được thực thi xuyên suốt từ cấp credential đến điểm sử dụng. Khi mốc gốc, phạm vi và phép đo đều rõ ràng, yêu cầu mới có thể liên kết được với rủi ro và tiêu chí chấp nhận của toàn hệ thống.
