# Session timeout

## 1. Session timeout là yêu cầu kiểm soát quyền truy cập

**Session timeout** là quy tắc chấm dứt hiệu lực của phiên sau một khoảng thời gian hoặc tại một thời điểm xác định. Khi phiên không còn hiệu lực, credential đại diện cho phiên đó không được tiếp tục cho phép truy cập tài nguyên cần xác thực theo chính sách đã công bố.

Ví dụ, một người vận hành nền tảng học tập mở trang quản trị trên máy dùng chung rồi rời đi. Nếu phiên vẫn dùng được nhiều giờ sau đó, người khác có thể tiếp tục thao tác dưới danh tính của người vận hành. Idle timeout giới hạn khoảng thời gian không hoạt động mà phiên còn được chấp nhận. Thời hạn tuyệt đối giới hạn toàn bộ vòng đời phiên, kể cả khi có hoạt động liên tục.

Một câu như “tự logout sau 15 phút” chưa đủ để triển khai và kiểm chứng. Cần xác định 15 phút được tính từ đâu, hoạt động nào làm mới bộ đếm, server thực thi ở đâu và các token hoặc kết nối hiện có được xử lý thế nào.

Trong đặc tả yêu cầu bảo mật, timeout phải là một quyết định có hiệu lực tại nơi bảo vệ tài nguyên. Đồng hồ đếm ngược trên giao diện chỉ giúp người dùng hiểu trạng thái; nó không phải nguồn quyết định phiên còn quyền truy cập hay không.

## 2. Các loại thời hạn cần phân biệt

| Khái niệm | Mốc tính | Mục tiêu |
|---|---|---|
| Idle timeout | Lần hoạt động hợp lệ gần nhất theo chính sách | Giới hạn phiên bị bỏ quên hoặc không còn được sử dụng |
| Absolute timeout | Thời điểm bắt đầu vòng đời phiên | Giới hạn thời gian sống tối đa, kể cả hoạt động liên tục |
| Thời hạn token | Thời điểm hết hiệu lực của credential cụ thể | Giới hạn thời gian một token được chấp nhận |
| Yêu cầu xác thực lại | Lần xác thực đáp ứng mức bảo đảm được yêu cầu | Bảo đảm thao tác nhạy cảm có xác thực đủ mới |
| Thời hạn cookie | Thời điểm trình duyệt ngừng lưu hoặc gửi cookie theo cấu hình | Quản lý credential phía trình duyệt |

Các mốc này có liên quan nhưng không thay thế nhau. Cookie còn tồn tại không làm một phiên đã hết hạn trở nên hợp lệ. Cookie bị xóa cũng chưa chứng minh server đã vô hiệu hóa phiên hoặc credential bị sao chép trước đó.

Tương tự, một access token còn hạn không nhất thiết đồng nghĩa phiên người dùng còn đáp ứng idle timeout. Nếu hệ thống vẫn chấp nhận token sau khi phiên đáng lẽ đã hết hiệu lực, phải xem đây là giới hạn thiết kế cần được giải quyết hoặc được mô tả thành chính sách khác một cách rõ ràng.

### 2.1. Idle timeout

Idle timeout thường được biểu diễn bằng khoảng thời gian `I`. Nếu `lastActivityAt` là thời điểm hoạt động hợp lệ cuối cùng, hạn không hoạt động là:

```text
idleDeadline = lastActivityAt + I
```

Không phải mọi gói tin đều là hoạt động phù hợp để làm mới mốc này. Polling nền, heartbeat của WebSocket hoặc script chạy trong một tab bị bỏ quên có thể tiếp tục gửi dữ liệu dù không còn người dùng ở đó.

### 2.2. Absolute timeout

Nếu phiên được tạo tại `createdAt` và thời gian sống tối đa là `A`, hạn tuyệt đối là:

```text
absoluteDeadline = createdAt + A
```

Hoạt động hợp lệ có thể đẩy `idleDeadline` về sau nhưng không được làm thay đổi `absoluteDeadline`, trừ khi chính sách cho phép tạo một vòng đời phiên mới sau một sự kiện xác thực mới có kiểm soát. Việc tự cấp token mới không phải bằng chứng của sự kiện xác thực mới đó.

### 2.3. Xác thực đủ mới cho thao tác nhạy cảm

Phiên có thể còn hiệu lực để đọc tiến độ học tập nhưng không đủ điều kiện đổi phương thức MFA hoặc cấp quyền quản trị. Một yêu cầu xác thực lại có thể dựa trên `lastStrongAuthenticationAt`, riêng biệt với `lastActivityAt`.

Việc người dùng vừa mở một trang không làm lần xác thực mạnh trở nên mới hơn. Vì vậy, không dùng chung một trường thời gian cho cả hoạt động phiên và độ mới của xác thực.

## 3. Mô hình thời gian và điều kiện hết hạn

Với hai giới hạn idle và absolute, thời điểm hết hạn có hiệu lực của phiên là:

```text
effectiveDeadline = min(idleDeadline, absoluteDeadline)
```

Một quy tắc biên rõ ràng có thể là:

```text
sessionExpired = now >= effectiveDeadline
```

Theo quy tắc này, request được đánh giá đúng tại hạn hết hiệu lực không còn được chấp nhận bằng phiên đó. Không nên để mỗi service tự chọn toán tử so sánh khác nhau.

Ví dụ với idle timeout 15 phút và absolute timeout 8 giờ:

```text
08:00  Tạo phiên                 absoluteDeadline = 16:00
08:10  Hoạt động hợp lệ          idleDeadline     = 08:25
08:24  Polling nền               idleDeadline     = 08:25, không đổi
08:25  Request cần xác thực      Phiên đã hết hạn

15:50  Hoạt động hợp lệ trong một phiên liên tục từ 08:00
       idleDeadline             = 16:05
       effectiveDeadline        = 16:00
16:00  Phiên hết hạn tuyệt đối dù vẫn đang được sử dụng
```

Hai nhánh thời gian minh họa hai tình huống khác nhau; phiên đã hết hạn lúc 08:25 không tự sống lại để tiếp tục đến 15:50. Để có nhánh hoạt động liên tục đến cuối ngày, phải có đủ hoạt động hợp lệ trước mỗi lần chạm idle deadline.

Các giá trị 15 phút và 8 giờ là ví dụ thiết kế trong bài, không phải thời hạn áp dụng cho mọi ứng dụng. Chọn thời hạn cần xét dữ liệu, quyền của người dùng, loại thiết bị, tác động khi bị chiếm phiên và nhu cầu thực hiện công việc.

## 4. Định nghĩa hoạt động nào được tính

Yêu cầu “mỗi request làm mới phiên” rất dễ biến idle timeout thành một giới hạn gần như không bao giờ đạt tới. Một tab đang mở có thể gửi request tự động liên tục, kể cả khi người dùng đã rời máy.

Cần phân loại hoạt động một cách có chủ đích:

| Hoạt động | Chính sách minh họa | Lý do |
|---|---|---|
| Người dùng chuyển sang trang nghiệp vụ cần xác thực | Có thể làm mới idle timer | Là thao tác thuộc luồng sử dụng được chấp nhận |
| Người dùng gửi một biểu mẫu hợp lệ | Có thể làm mới idle timer | Có hoạt động nghiệp vụ trong phạm vi phiên |
| Polling thông báo ở nền | Không làm mới | Không chứng minh phiên đang được người dùng sử dụng |
| WebSocket ping/pong | Không làm mới | Chỉ chứng minh kết nối còn hoạt động |
| Tự gia hạn access token | Không làm mới | Là hoạt động kỹ thuật, không phải tương tác được tính |
| Request dùng phiên đã hết hạn | Không làm mới | Không cho phép credential hết hạn khôi phục hiệu lực |
| Tải tài nguyên công khai hoặc tệp giao diện | Không làm mới | Không thể hiện hoạt động nghiệp vụ cần phiên |

Server phải quyết định dựa trên loại thao tác và chính sách được quản lý. Không tin một trường như `userActive=true` hoặc thời gian hoạt động do client gửi để kéo dài phiên vô điều kiện.

Ngay cả request được tính cũng không thể chứng minh tuyệt đối một con người đang ngồi trước màn hình. Kẻ đã chiếm credential có thể tiếp tục tạo hoạt động hợp lệ. Đây là lý do idle timeout cần phối hợp với absolute timeout, bảo vệ credential và phát hiện hành vi bất thường.

Các chức năng như tự lưu bài làm cần quyết định riêng. Nếu tự lưu được tính là hoạt động, một trang bị bỏ quên có thể duy trì phiên. Nếu không được tính, ứng dụng phải có cách cảnh báo và bảo vệ công sức của người dùng khi phiên sắp hết hạn. Không nên để hành vi này là hệ quả tình cờ của một middleware cập nhật thời gian trên mọi request.

## 5. Thực thi tại server và quản lý trạng thái

### 5.1. Client không phải nguồn thời gian đáng tin

Người dùng có thể sửa JavaScript, đồng hồ thiết bị, local storage hoặc request gửi lên server. Các thay đổi đó không được làm tăng thời hạn của phiên.

Giao diện có thể nhận `expiresAt` từ server để hiển thị cảnh báo. Khi máy ngủ hoặc tab bị trình duyệt giảm tần suất chạy, bộ đếm có thể chậm hoặc dừng. Sau khi hoạt động trở lại, ứng dụng cần xác nhận trạng thái phiên qua server trước khi thực hiện thao tác cần bảo vệ.

### 5.2. Kiểm tra trước khi làm mới thời gian

Thứ tự xử lý có ý nghĩa bảo mật. Nếu server cập nhật `lastActivityAt` ngay khi nhận request rồi mới kiểm tra hết hạn, phiên đã hết hạn có thể bị làm mới trước khi bị phát hiện.

Mã giả sau mô tả ý tưởng cho kho phiên tập trung, không phải mã triển khai sẵn:

```text
authorizeSession(sessionId, request):
    atomically for the current session version:
        session = load(sessionId)
        now = authoritativeTime()

        if session does not exist or session.state != ACTIVE:
            return DENY

        deadline = min(
            session.lastActivityAt + session.idleLimit,
            session.createdAt + session.absoluteLimit
        )

        if now >= deadline:
            transition session to EXPIRED
            return DENY

        if request is eligible to renew idle time:
            session.lastActivityAt = now
            save only if the session is still ACTIVE
            and the session version has not changed

        return ALLOW_FOR_THIS_AUTHORIZATION_CHECK
```

Quyết định cho phép ở đây dành cho lần kiểm tra hiện tại, không phải quyền thực hiện mọi thao tác trong tương lai. Phân quyền đối với hành động và tài nguyên vẫn phải được thực hiện theo chính sách nghiệp vụ.

### 5.3. Request đồng thời và trạng thái kết thúc

Hai request gần nhau có thể đọc cùng một bản ghi phiên. Một request cũng có thể đang làm mới thời gian trong lúc request khác thực hiện logout hoặc thu hồi phiên. Thiết kế phải bảo đảm cập nhật muộn không đưa phiên từ `REVOKED` hoặc `EXPIRED` trở lại `ACTIVE`.

Có thể cần thao tác nguyên tử, kiểm tra phiên bản, điều kiện cập nhật hoặc cơ chế tương đương của kho lưu trữ. Điều quan trọng trong yêu cầu là bất biến: **hoạt động từ credential cũ không được khôi phục một phiên đã kết thúc**.

Không cập nhật thời gian theo giá trị cũ hơn chỉ vì request đó hoàn tất sau. Việc dùng thời điểm kết thúc một tác vụ dài để gia hạn cũng cần tránh nếu chính sách xác định hoạt động tại thời điểm request được đánh giá chấp nhận.

## 6. Hệ thống phân tán, cache và độ chính xác

Trong kiến trúc nhiều node, cùng một phiên có thể được xử lý tại nhiều instance hoặc service. Nếu mỗi nơi giữ một `lastActivityAt` riêng mà không có quy tắc đồng bộ, phiên có thể hết hạn ở một node nhưng vẫn hoạt động ở node khác.

Yêu cầu cần xác định nguồn thời gian, nguồn trạng thái phiên và các điểm thực thi. Đồng hồ server cần được quản lý; không dùng đồng hồ phía người dùng để quyết định hiệu lực. Đồng hồ đơn điệu có thể hỗ trợ đo khoảng thời gian trong một tiến trình, nhưng không tự giải quyết việc so sánh thời gian giữa nhiều máy hoặc sau khởi động lại.

Cache cũng tạo ra độ trễ. Một node có thể giữ bản ghi “phiên còn hiệu lực” sau khi nguồn chuẩn đã đánh dấu hết hạn hoặc thu hồi. Nếu chính sách cho phép một khoảng trễ thực thi, phải nêu giới hạn cùng rủi ro được chấp nhận. Nếu yêu cầu hết hạn chính xác tại mốc đã công bố, kiến trúc không được âm thầm thêm thời gian do cache hoặc kiểm tra theo chu kỳ.

Ví dụ yêu cầu:

> **ST-DIST-01:** Mọi điểm chấp nhận credential của phiên quản trị phải thực thi cùng quy tắc idle và absolute timeout. Không điểm nào được chấp nhận request tại hoặc sau `effectiveDeadline` chỉ vì bản ghi phiên còn nằm trong cache hoặc chưa được tiến trình dọn dẹp xử lý.

Tiến trình xóa bản ghi quá hạn chủ yếu phục vụ quản lý dữ liệu và tài nguyên. Tính bảo mật không nên phụ thuộc vào việc tiến trình đó đã chạy hay chưa: bản ghi vẫn còn trong database nhưng đã quá hạn phải bị từ chối.

Khi kho phiên không khả dụng, hệ thống phải có hành vi lỗi đã đặc tả. Đối với tài nguyên cần phiên hợp lệ, không tự cho qua chỉ vì không kiểm tra được. Có thể cho phép chức năng công khai hoặc một đường khôi phục riêng nếu chúng nằm trong chính sách được thiết kế rõ.

## 7. Access token, refresh token và SSO

### 7.1. Token hết hạn không đồng nghĩa phiên hết hạn

Một phiên có thể dùng nhiều access token kế tiếp nhau. Refresh token có thể phát hành token mới mà không có lần tương tác xác thực mới của người dùng. Vì vậy, cần quy định refresh có bị chặn khi phiên đã hết idle hoặc absolute timeout hay không.

> **ST-TOKEN-01:** Việc phát hành hoặc làm mới credential không được tự thay đổi mốc bắt đầu vòng đời phiên và không được làm mới idle timer nếu không có hoạt động thuộc loại được chính sách chấp nhận. Khi phiên hết hạn, hệ thống phải ngăn phát hành credential mới gắn với phiên đó.

Chặn refresh chưa đủ nếu access token cũ còn được các API chấp nhận. Thiết kế phải xác định cách các điểm thực thi nhận biết phiên đã hết hiệu lực, chẳng hạn kiểm tra trạng thái phiên hoặc dùng một cơ chế kiểm tra tập trung phù hợp.

Với token tự chứa được kiểm tra hoàn toàn độc lập, thông tin trong token không tự thay đổi khi `lastActivityAt` ở nơi khác thay đổi. Thời hạn token ngắn giúp giới hạn khoảng phơi lộ nhưng không tự tạo ra idle timeout chính xác cho toàn bộ phiên. Yêu cầu phải khớp với điều mà kiến trúc thực sự thực thi được.

### 7.2. Phiên ứng dụng và phiên nhà cung cấp identity

Trong SSO, phiên tại ứng dụng và phiên tại identity provider có thể có thời hạn riêng. Khi ứng dụng hết hạn, chuyển hướng đến identity provider có thể khiến người dùng quay lại mà không phải nhập thông tin xác thực vì phiên SSO còn hiệu lực.

Nếu mục tiêu chỉ là kết thúc vòng đời phiên cục bộ, hành vi đó có thể phù hợp với chính sách. Nếu mục tiêu là yêu cầu người dùng hiện diện và xác thực lại, cần đặc tả điều kiện về độ mới và phương thức xác thực, đồng thời kiểm tra bằng chứng tương ứng từ nhà cung cấp. Không mặc định một lần chuyển hướng đồng nghĩa một lần xác thực mới.

### 7.3. Remember me và thiết bị tin cậy

Chức năng nhớ đăng nhập có thể dùng credential bền hơn để tạo phiên mới. Nó không được âm thầm vô hiệu hóa giới hạn phiên quản trị hoặc yêu cầu xác thực lại cho thao tác nhạy cảm.

Cần tách việc ghi nhớ định danh, ghi nhớ thiết bị và tự đăng nhập. Mỗi chức năng có tác động khác nhau. Ví dụ, trình duyệt nhớ tên tài khoản không có nghĩa phải giữ phiên được xác thực vô thời hạn.

## 8. Nhiều tab và kết nối dài hạn

### 8.1. Nhiều tab dùng chung phiên

Các tab trong cùng trình duyệt thường có thể dùng chung cookie phiên. Nếu chính sách áp dụng theo phiên, hoạt động hợp lệ ở tab A có thể làm mới idle timer cho phiên mà tab B đang sử dụng.

Không mô tả “mỗi tab tự hết hạn sau 15 phút” nếu credential và trạng thái thực tế vẫn dùng chung. Nếu cần sự cô lập theo tác vụ hoặc theo cửa sổ, phải thiết kế cơ chế riêng thay vì chỉ đặt bộ đếm JavaScript trong từng tab.

Giao diện nên đồng bộ tín hiệu hết hạn hoặc đăng nhập lại giữa các tab khi có thể, nhưng quyết định cuối cùng vẫn ở server. Một tab không nhận được thông báo vẫn phải bị từ chối khi dùng credential đã hết hạn.

### 8.2. WebSocket và streaming

Kiểm tra session lúc bắt tay kết nối không bảo đảm kết nối vẫn hợp lệ nhiều giờ sau đó. Cần xác định cách phát hiện hạn hết hiệu lực khi không có HTTP request mới.

Đối với kết nối dài hạn, yêu cầu có thể bao gồm kiểm tra trước từng thao tác đặc quyền, chặn dữ liệu được bảo vệ sau thời hạn và đóng kết nối theo giới hạn đã công bố. Ping/pong không được tự làm mới idle timer nếu nó chỉ phục vụ giữ kết nối.

Nếu server tiếp tục đẩy dữ liệu nhạy cảm sau khi phiên hết hạn vì chưa có message mới từ client, chính sách timeout chưa được thực thi đầy đủ. Cơ chế hẹn giờ, nhận thông báo trạng thái hoặc kiểm tra định kỳ phải phù hợp với mức trễ mà yêu cầu cho phép.

### 8.3. Tác vụ đang chạy

Một thao tác được chấp nhận trước khi hết hạn có thể vẫn đang chạy sau thời điểm hết hạn. Cần phân biệt quyền gửi thao tác mới với cách xử lý tác vụ đã được chấp nhận.

Ví dụ, tác vụ xuất dữ liệu kéo dài có thể cần kiểm tra lại quyền trước khi phát hành đường tải kết quả. Việc hủy giao dịch đang thực thi hoặc dừng một upload giữa chừng phải được đặc tả theo nghiệp vụ; không giả định đóng phiên tự động đảo ngược mọi tác động đã xảy ra.

## 9. Cảnh báo, xác thực lại và dữ liệu chưa lưu

Một trải nghiệm tốt giúp người dùng biết phiên sắp hết hạn mà không làm suy yếu quy tắc phía server. Ví dụ, ứng dụng có thể hiển thị cảnh báo trước idle deadline 2 phút theo thông tin do server cung cấp.

Nút “Tiếp tục phiên” phải tạo một tương tác được server kiểm tra trong lúc phiên còn hợp lệ. Nếu phiên đã hết hạn, cần đăng nhập hoặc xác thực lại theo chính sách. Không cho phép nút này khôi phục credential cũ chỉ vì cảnh báo vẫn còn trên giao diện.

Nếu người dùng đang làm bài hoặc soạn nội dung dài, cần xác định cách lưu nháp trước khi hết hạn và cách phục hồi sau xác thực lại. Dữ liệu nhạy cảm không nên được lưu vào bộ nhớ bền phía client chỉ để tránh mất công việc mà không có chính sách bảo vệ phù hợp.

Sau khi hết hạn, ứng dụng không được tự gửi lại một request gây tác động chỉ vì người dùng vừa đăng nhập lại. Cần bảo đảm chủ thể hiện tại, ý định và điều kiện nghiệp vụ vẫn phù hợp; các thao tác có thể lặp cần cơ chế kiểm soát trùng tương ứng.

Các trang đã hiển thị có thể vẫn còn trong bộ nhớ hoặc lịch sử của trình duyệt. Timeout kiểm soát việc cấp quyền tiếp tục, không bảo đảm xóa mọi dữ liệu đã được giao cho client. Chính sách cache và cách che giao diện sau hết hạn có thể hạn chế lộ dữ liệu, nhưng không nên được mô tả thành khả năng thu hồi tuyệt đối mọi bản sao.

## 10. Mẫu yêu cầu bảo mật đo được

Giả sử cổng quản trị nền tảng học tập áp dụng idle timeout 15 phút, absolute timeout 8 giờ và yêu cầu xác thực mạnh trong 5 phút gần nhất trước khi đổi phương thức MFA. Các giá trị này là ví dụ cho một hồ sơ rủi ro cụ thể.

| ID | Yêu cầu | Cách kiểm chứng dự kiến |
|---|---|---|
| ST-IDLE-01 | Server từ chối request cần phiên khi thời gian từ hoạt động được tính gần nhất đạt hoặc vượt 15 phút | Gửi request ngay trước, đúng tại và sau deadline bằng nguồn thời gian kiểm soát được |
| ST-ABS-01 | Server từ chối credential của vòng đời phiên khi đạt hoặc vượt 8 giờ từ lúc tạo, kể cả có hoạt động liên tục | Duy trì hoạt động hợp lệ và thử request tại hạn tuyệt đối |
| ST-ACT-01 | Danh mục hoạt động làm mới idle timer được cấu hình và quản lý tập trung; polling, heartbeat và refresh token không thuộc danh mục của ví dụ | Đối chiếu `lastActivityAt` trước và sau từng loại tương tác |
| ST-ORDER-01 | Request đã hết hạn không được cập nhật hoạt động rồi trở thành hợp lệ | Gửi request đầu tiên sau idle deadline và kiểm tra trạng thái |
| ST-END-01 | Logout, thu hồi hoặc hết hạn là trạng thái kết thúc của credential phiên cũ; cập nhật đồng thời không được làm sống lại phiên | Tạo cạnh tranh giữa request làm mới và request kết thúc phiên |
| ST-CLOCK-01 | Thời điểm và thời hạn do client gửi không được dùng để tăng hiệu lực của phiên | Sửa đồng hồ, bộ đếm và dữ liệu client rồi thử truy cập |
| ST-API-01 | Mọi API chấp nhận credential của phiên áp dụng quy tắc hết hạn tương ứng, kể cả API không đi qua giao diện web | Gọi trực tiếp từng điểm thực thi bằng credential cũ |
| ST-REFRESH-01 | Refresh token không được tạo credential mới cho phiên đã hết hạn và không tự khởi tạo lại vòng đời phiên | Thử refresh sau idle và absolute deadline |
| ST-STEPUP-01 | Thao tác đổi phương thức MFA yêu cầu xác thực mạnh trong 5 phút gần nhất; tương tác thông thường không làm mới mốc này | Dùng phiên còn hợp lệ nhưng xác thực mạnh đã quá cũ |
| ST-LONG-01 | Kết nối streaming quản trị của ví dụ ngừng gửi dữ liệu được bảo vệ chậm nhất 5 giây sau khi phiên hết hiệu lực; message đặc quyền mới luôn bị kiểm tra trước khi xử lý | Giữ kết nối không có message mới qua deadline và thử gửi message sau hạn |
| ST-FAIL-01 | Không xác minh được trạng thái phiên thì không chấp nhận thao tác quản trị; lỗi phụ thuộc không tạo thêm thời gian sống | Giả lập kho phiên lỗi và kiểm tra hành vi |
| ST-UX-01 | Giao diện hiển thị cảnh báo theo deadline server và chỉ gia hạn qua tương tác hợp lệ; xác thực lại sau hết hạn không tự gửi lại thao tác nhạy cảm | Kiểm tra tab nền, máy ngủ và biểu mẫu có thay đổi chưa lưu |

Giới hạn 5 giây ở yêu cầu streaming là độ trễ riêng được công bố cho luồng đẩy dữ liệu trong ví dụ. Nó không phải khoảng gia hạn cho HTTP request hoặc message đặc quyền mới. Nếu nghiệp vụ đòi dừng dữ liệu ngay tại deadline, yêu cầu và kiến trúc phải được điều chỉnh tương ứng.

Yêu cầu về thời hạn nên có nguồn thời gian kiểm chứng, điểm quan sát và điều kiện biên. Một phép thử thủ công chờ “khoảng 15 phút” không đủ để kết luận mọi node và mọi đường truy cập đều thực thi chính xác.

## 11. Ví dụ quyết định đối với một thao tác nhạy cảm

Giả sử người quản trị đăng nhập lúc 08:00, có hoạt động hợp lệ lúc 08:10 và chưa xác thực mạnh lại từ lúc đăng nhập. Lúc 08:12, người đó yêu cầu đổi phương thức MFA.

Server phải đánh giá các điều kiện riêng:

1. Phiên có tồn tại và còn trạng thái hoạt động không?
2. Idle deadline và absolute deadline đã đến chưa?
3. Người dùng có quyền thực hiện thao tác đổi phương thức MFA không?
4. Lần xác thực mạnh có còn nằm trong cửa sổ 5 phút không?
5. Các điều kiện nghiệp vụ bổ sung có được đáp ứng không?

Trong tình huống này, phiên chưa hết idle timeout vì hoạt động cuối cùng mới cách 2 phút. Tuy nhiên, lần xác thực mạnh đã cách 12 phút, nên cần xác thực lại trước thao tác nhạy cảm. Mở thêm trang hoặc gọi endpoint làm mới token không được thay thế việc xác thực lại đó.

Nếu người dùng hoàn tất xác thực mới lúc 08:13, hệ thống phải ghi nhận đúng sự kiện xác thực và áp dụng chính sách về phiên sau xác thực. Không tùy tiện đặt lại `createdAt` mỗi lần có một request thành công. Việc tạo vòng đời phiên mới phải là quyết định được thiết kế, có liên kết truy vết và xử lý credential cũ phù hợp.

## 12. Tiêu chí chấp nhận và tình huống biên

Các tình huống sau mô tả kiểm chứng dự kiến cho yêu cầu, chưa phải kết quả kiểm thử của hệ thống thực tế.

| Tình huống | Thao tác kiểm chứng | Kết quả mong đợi |
|---|---|---|
| Trước idle deadline | Gửi request hợp lệ tại thời điểm còn trước hạn | Có thể chấp nhận và làm mới nếu thuộc loại được tính |
| Đúng idle deadline | Gửi request tại thời điểm bằng hạn theo đồng hồ đánh giá | Từ chối theo quy tắc `now >= deadline` |
| Hoạt động liên tục | Duy trì hoạt động được tính đến absolute deadline | Vẫn hết hạn tuyệt đối đúng chính sách |
| Tab chỉ polling | Để tab mở và chỉ có request nền | Không làm tăng idle deadline |
| Làm mới token liên tục | Thực hiện refresh mà không có hoạt động được tính | Không kéo dài idle hoặc absolute deadline |
| Client sửa thời gian | Đổi đồng hồ và dữ liệu local storage | Không thay đổi hiệu lực phía server |
| Credential cũ sau hết hạn | Gọi trực tiếp API bằng cookie hoặc token đã sao chép | Bị từ chối theo phạm vi timeout đã đặc tả |
| Hai request đồng thời | Tạo request làm mới cạnh tranh với logout hoặc thu hồi | Không khôi phục trạng thái của phiên đã kết thúc |
| Chuyển node | Gửi request cùng phiên qua nhiều instance | Các điểm áp dụng cùng chính sách và không cho qua bằng cache cũ |
| Cookie còn tồn tại | Giữ cookie sau khi phiên phía server hết hạn | Cookie không khôi phục được phiên |
| Nhiều tab | Hoạt động hợp lệ ở một tab và kiểm tra tab khác | Hành vi đúng phạm vi phiên dùng chung đã công bố |
| Kết nối dài hạn | Giữ WebSocket hoặc streaming qua deadline | Chặn thao tác mới và ngừng dữ liệu theo giới hạn đã đặc tả |
| Máy ngủ rồi mở lại | Tạm dừng client qua thời hạn của phiên | Server từ chối credential cũ; giao diện không tin bộ đếm bị dừng |
| SSO còn hoạt động | Hết hạn phiên ứng dụng rồi quay lại qua SSO | Đáp ứng chính sách về phiên mới và độ mới xác thực, không suy diễn |
| Tác vụ dài đang chạy | Hết hạn trong lúc tác vụ đã được chấp nhận đang xử lý | Áp dụng quy tắc riêng về tiếp tục, hủy và truy cập kết quả |
| Kho phiên lỗi | Mất kết nối với nguồn trạng thái | Không tự cho phép thao tác cần xác thực |

Ngoài phản hồi từ API, bằng chứng kiểm chứng nên xác nhận tác động nghiệp vụ không được thực hiện khi request bị từ chối. Việc giao diện chuyển về trang đăng nhập chưa chứng minh một tác vụ phía server đã bị ngăn.

## 13. Nhật ký, cấu hình và vận hành

Nhật ký cần hỗ trợ phân biệt hết hạn do idle, hết hạn tuyệt đối, thu hồi chủ động và yêu cầu xác thực lại. Không ghi session cookie, access token hoặc refresh token vào log. Có thể dùng định danh nội bộ hoặc tham chiếu được bảo vệ để liên kết các sự kiện phục vụ điều tra.

Thông tin hữu ích gồm thời điểm quyết định, loại sự kiện, chính sách áp dụng, điểm thực thi và kết quả. Mức chi tiết trả về cho client cần phù hợp, tránh biến phản hồi thành công cụ dò sự tồn tại của phiên khác.

Chính sách timeout nên được quản lý như cấu hình có phiên bản. Khi thay đổi giá trị, cần xác định phiên đang tồn tại áp dụng chính sách cũ hay mới và từ thời điểm nào. Không âm thầm kéo dài phiên quản trị đang hoạt động chỉ vì một giá trị cấu hình toàn cục tăng lên.

Các chỉ số như số phiên hết hạn do idle, số request sau hết hạn, tỷ lệ yêu cầu xác thực lại và lỗi kiểm tra trạng thái giúp theo dõi hành vi thực tế. Chúng cần được đọc trong bối cảnh: nhiều lần hết hạn có thể phản ánh thời hạn không phù hợp hoặc giao diện gây khó hiểu, nhưng cũng có thể là hành vi bình thường của người dùng rời thiết bị.

Khi triển khai phiên bản mới, cần lưu ý sự tương thích của timestamp, đơn vị thời gian và cách tính deadline. Nhầm giây với mili giây, đặt lại thời gian tạo phiên sau restart hoặc dùng các chính sách khác nhau giữa node có thể làm giới hạn thời gian mất ý nghĩa.

## 14. Những cách viết yêu cầu dễ gây hiểu sai

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
|---|---|---|
| “Logout sau 15 phút” | Không có mốc tính hoặc phạm vi thực thi | Xác định idle, absolute, hoạt động được tính và điểm kiểm tra |
| “Cookie hết hạn là an toàn” | Bỏ qua credential sao chép và trạng thái server | Yêu cầu server từ chối phiên theo deadline độc lập với cookie |
| “Có request thì còn hoạt động” | Polling và heartbeat có thể giữ phiên vô hạn | Liệt kê các loại tương tác được làm mới idle timer |
| “Refresh token nghĩa là gia hạn phiên” | Có thể vượt giới hạn vòng đời và không hoạt động | Tách thời hạn credential khỏi thời hạn phiên |
| “Kiểm tra khi mở WebSocket là đủ” | Kết nối có thể sống lâu hơn phiên | Kiểm soát cả message mới và dữ liệu đẩy qua deadline |
| “Frontend đã khóa màn hình” | Có thể gọi thẳng API | Thực thi ở mọi điểm chấp nhận credential |
| “Hết hạn rồi dọn database sẽ chặn được” | Phụ thuộc vào lịch chạy dọn dẹp | Kiểm tra thời hạn trên đường truy cập trước khi thực hiện tác động |
| “Đăng nhập SSO lại là đã nhập MFA mới” | Phiên identity provider có thể được tái sử dụng | Kiểm tra bằng chứng về độ mới và phương thức xác thực |

Một đặc tả session timeout đầy đủ phải xác định được thời điểm credential ngừng có quyền, hoạt động nào được phép thay đổi mốc thời gian và nơi quyết định đó được thực thi. Giao diện, token, cache và kết nối dài hạn phải cùng tuân theo chính sách đã công bố; trường hợp cần độ trễ hoặc ngoại lệ phải có phạm vi và tiêu chí kiểm chứng rõ ràng.
