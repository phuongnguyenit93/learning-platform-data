# Recovery link revocation — Thu hồi liên kết khôi phục tài khoản

## 1. Thu hồi liên kết là thu hồi quyền nào?

**Thu hồi liên kết khôi phục** là làm cho quyền được mang bởi liên kết mất hiệu lực trước thời điểm hết hạn tự nhiên. Sau khi quyết định thu hồi đã có hiệu lực, người cầm liên kết không được dùng nó để tiếp tục hành động mà hệ thống vừa cấm.

Ví dụ, Lan yêu cầu liên kết đặt lại mật khẩu lúc 09:00. Đến 09:03, Lan phát hiện hộp thư bị truy cập trái phép và yêu cầu vô hiệu các liên kết khôi phục đang tồn tại. Một liên kết vẫn ghi “có hiệu lực trong 15 phút” không được tiếp tục hoạt động tới 09:15 nếu hệ thống đã xác nhận thu hồi thành công.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, thu hồi giúp giảm nguy cơ chiếm đoạt tài khoản khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Nó nối thiết kế token dùng một lần với xác minh danh tính, đánh giá rủi ro, chống lạm dụng và quản lý phiên. Một liên kết bị thu hồi đúng lúc phải chặn được quyền khôi phục tương ứng, kể cả khi người tấn công đang thao tác ở bước tiếp theo.

Điểm quan trọng là liên kết có thể đã được đổi thành **recovery grant**: quyền tạm thời để đặt mật khẩu hoặc thực hiện bước khôi phục cụ thể. Chặn riêng token trong URL mà vẫn để grant đã tạo hoạt động có thể không đáp ứng mục tiêu bảo mật.

Sau bài này, người học cần xác định được sự kiện nào gây thu hồi, phạm vi thu hồi, cách kiểm tra hiệu lực tại máy chủ và cách xử lý cạnh tranh giữa thu hồi với hoàn tất khôi phục.

## 2. Phân biệt hết hạn, đã dùng và bị thu hồi

| Khái niệm | Nguyên nhân | Ý nghĩa khi người dùng mở liên kết |
|---|---|---|
| Hết hạn | Thời gian máy chủ đã tới hoặc vượt `expiresAt` | Token không còn dùng được, dù tác vụ dọn dữ liệu chưa chạy |
| Đã dùng | Token được tiêu thụ thành công theo thiết kế dùng một lần | Không được đổi lại cùng token thành quyền mới |
| Bị thu hồi | Một quyết định bảo mật hoặc nghiệp vụ chủ động vô hiệu hóa quyền | Không được dùng dù thời hạn ban đầu vẫn còn |
| Đã hoàn tất khôi phục | Hành động cuối đã được chấp nhận | Quyền tạm thời đã đóng; các liên kết và grant liên quan cần được xử lý theo chính sách |

Ba điều kiện đầu có thể cùng tồn tại theo thời gian. Token đã dùng lúc 09:01 vẫn có thể thuộc một yêu cầu bị thu hồi lúc 09:03. Không nên làm mất lịch sử tiêu thụ chỉ vì sau đó có quyết định thu hồi.

Một mô hình đơn giản lưu các mốc độc lập:

```text
EmailRecoveryChallenge
  id
  accountId
  tenantId
  purpose
  tokenDigest
  issuedEpoch
  contactId
  contactVersion
  expiresAt
  consumedAt       // null nếu chưa đổi token
  revokedAt        // null nếu chưa bị thu hồi riêng
  revocationReason // mã lý do nội bộ
```

Với mô hình này, email token chỉ được sử dụng khi chưa tiêu thụ, chưa bị thu hồi, còn hạn và vẫn khớp trạng thái bảo mật liên quan. Kiểm tra thời hạn ngay khi nhận hành động; xóa bản ghi cũ bằng job nền chỉ là quản lý dữ liệu.

Không xóa email khỏi hộp thư để biểu diễn thu hồi. Hệ thống thường không thể thu hồi mọi bản sao đã giao hoặc được chuyển tiếp. Việc bắt buộc là làm cho phía máy chủ từ chối quyền mang bởi bản sao đó.

## 3. Chọn phạm vi thu hồi trước khi chọn cách lưu

“Thu hồi liên kết” cần được cụ thể hóa thành tập quyền bị ảnh hưởng.

| Phạm vi | Ví dụ sử dụng | Quyền cần xem xét |
|---|---|---|
| Một challenge | Người dùng hủy một lần yêu cầu cụ thể | Token của challenge và grant bắt nguồn từ nó |
| Một yêu cầu hoặc giao dịch khôi phục | Một yêu cầu đã bị đánh dấu gian lận | Tất cả challenge và grant thuộc yêu cầu đó |
| Một mục đích trên một tài khoản | Hoàn tất đặt lại mật khẩu | Các quyền đặt lại mật khẩu cũ có thể cạnh tranh với kết quả vừa hoàn tất |
| Một kênh liên hệ hoặc phiên bản kênh | Email cũ bị thay đổi hoặc bị xác định không còn tin cậy | Quyền phát hành dựa trên kênh cũ |
| Toàn bộ khôi phục của tài khoản | Phát hiện nguy cơ chiếm đoạt tài khoản | Mọi quyền khôi phục thuộc phạm vi chính sách, kể cả grant đã phát hành |
| Nhiều tài khoản | Sự cố lộ dữ liệu hoặc khóa của một thành phần | Chỉ tập quyền xác định thuộc ảnh hưởng; cần quy trình vận hành riêng |

Phạm vi tenant và tài khoản phải được xác thực ở máy chủ. Nhận `challengeId` hoặc `accountId` từ client không chứng minh người gọi được phép thu hồi đối tượng đó.

Thu hồi quyền khôi phục không tự động đồng nghĩa thu hồi phiên đăng nhập, refresh token, access token, passkey hoặc recovery code. Mỗi loại có vòng đời riêng. Nếu sự cố đòi hỏi xử lý cả chúng, kế hoạch phải ghi rõ các thao tác bổ sung và bằng chứng hoàn thành.

## 4. Những sự kiện nào nên kích hoạt thu hồi?

### 4.1. Hoàn tất một thay đổi bảo mật

Khi đặt lại mật khẩu thành công, các liên kết đặt lại mật khẩu và grant cũ liên quan có thể trở thành đường ghi đè mật khẩu vừa được thiết lập. Một chính sách phù hợp thường đóng các quyền cạnh tranh thuộc mục đích đó ngay trong xử lý hoàn tất.

Nếu hệ thống có nhiều loại khôi phục, cần xác định việc đặt lại mật khẩu tác động đến những loại nào. Không mặc định một chính sách dùng chung sẽ phù hợp cho thay MFA, đăng ký passkey mới và đổi địa chỉ email.

### 4.2. Kênh liên hệ hoặc mức tin cậy thay đổi

Email được thay thế, địa chỉ bị thu hồi khỏi tài khoản hoặc một kênh bị đánh dấu xâm nhập là các sự kiện cần đánh giá lại quyền đã cấp dựa trên kênh đó. Một token còn hạn không được vượt qua việc quan hệ kênh đã mất hiệu lực.

Có thể ràng buộc challenge với `contactVersion` khi phát hành. Khi phiên bản thay đổi, quyền cũ bị từ chối. Grant đã đổi từ challenge cũng phải giữ hoặc kiểm tra ràng buộc tương ứng, nếu không token cũ vẫn có thể sống tiếp dưới dạng khác.

### 4.3. Người dùng hoặc bộ phận vận hành chủ động hủy

Người dùng đã xác thực có thể yêu cầu hủy một giao dịch đáng ngờ. Bộ phận hỗ trợ hoặc quản trị có thể thu hồi sau quy trình xác minh và phân quyền phù hợp. Cần ghi nhận chủ thể thực hiện, phạm vi, lý do và thời điểm quyết định có hiệu lực.

Đối với hành động vô hiệu hóa toàn bộ khôi phục, yêu cầu xác thực và mức kiểm soát nên tương ứng với tác động. Nếu người dùng mất mọi yếu tố, cần một quy trình xác minh thay thế; không bỏ qua kiểm tra quyền chỉ vì hành động được gọi là “hủy”.

### 4.4. Yêu cầu gửi lại chưa xác minh

Một người biết email có thể gửi yêu cầu khôi phục nhiều lần. Nếu mỗi yêu cầu mới lập tức thu hồi mọi token và grant cũ, người đó có thể liên tục phá quá trình khôi phục của chủ tài khoản.

Gửi lại cần chính sách riêng: giới hạn số lần, xác định challenge nào được thay thế và giữ trải nghiệm rõ ràng khi thư đến sai thứ tự. Không cho thao tác khởi tạo công khai tùy ý hủy các grant mà người thật đã xác minh và đang sử dụng.

## 5. Hai cách biểu diễn thu hồi và khi nào kết hợp

### 5.1. Đánh dấu thu hồi từng đối tượng

Để thu hồi một challenge cụ thể, máy chủ có thể đặt `revokedAt` và lý do nội bộ. Khi xử lý token, phải đọc trạng thái đó từ nguồn dữ liệu đáng tin cậy.

Nếu challenge đã sinh grant, thao tác thu hồi cần vô hiệu grant bắt nguồn từ nó hoặc yêu cầu mọi lần dùng grant kiểm tra dấu thu hồi của challenge nguồn. Chỉ nhìn `consumedAt` là chưa đủ: token đã tiêu thụ là trạng thái bình thường sau khi tạo grant, còn `revokedAt` là một quyết định chặn tiếp tục.

```text
RecoveryGrant
  id
  accountId
  tenantId
  purpose
  sourceChallengeId
  issuedEpoch
  contactVersion
  expiresAt
  usedAt
  revokedAt
```

Grant hợp lệ không đòi challenge nguồn phải còn “chưa tiêu thụ”. Nó cần nguồn không bị thu hồi theo chính sách, ràng buộc bảo mật còn đúng và bản thân grant chưa dùng, chưa bị thu hồi, còn hạn.

### 5.2. Tăng phiên bản quyền khôi phục

Với thu hồi cả một phạm vi, có thể duy trì một bộ đếm phiên bản, gọi là **recovery epoch**. Mỗi challenge và grant lưu phiên bản tại lúc phát hành. Quyền chỉ hợp lệ nếu phiên bản đó vẫn bằng phiên bản hiện hành của đúng phạm vi.

```text
Trạng thái hiện tại:
  account = A
  purpose = PASSWORD_RESET
  currentEpoch = 18

Challenge C và grant G phát hành ở epoch 18.

Thu hồi toàn bộ quyền đặt lại mật khẩu của A:
  currentEpoch: 18 -> 19

Kết quả:
  C.issuedEpoch = 18 != 19 -> từ chối
  G.issuedEpoch = 18 != 19 -> từ chối
```

Phương pháp này không cần cập nhật từng bản ghi để tạo hiệu lực logic. Tuy vậy, trạng thái hiển thị và audit phải giải thích được rằng một token không có `revokedAt` riêng vẫn đã mất hiệu lực do epoch thay đổi.

Phạm vi của epoch phải rõ: toàn bộ recovery của tài khoản hay riêng từng purpose. Dùng một bộ đếm chung có thể gây ảnh hưởng rộng hơn mong muốn. Bộ đếm cần tránh tái sử dụng giá trị cũ khi khôi phục dữ liệu hoặc di chuyển tài khoản.

Có thể kết hợp hai cách: dấu thu hồi riêng cho một challenge, epoch cho thu hồi cả phạm vi và phiên bản kênh để chặn quyền dựa trên email cũ. Hàm kiểm tra hiệu lực phải áp dụng tất cả ràng buộc liên quan, không chọn kiểm tra một điều kiện rồi bỏ các điều kiện còn lại.

### 5.3. Token tự chứa không tự có khả năng thu hồi

Một JWT còn hạn và có chữ ký đúng vẫn có thể đã bị thu hồi về mặt nghiệp vụ. Nếu bên xác minh chỉ kiểm tra chữ ký và `exp`, thay đổi một dòng dữ liệu trong Recovery API không làm JWT mất hiệu lực ở bên đó.

Muốn thu hồi trước hạn cần cơ chế kiểm tra trạng thái như denylist theo mã token, đối chiếu phiên bản ở nguồn có thẩm quyền hoặc introspection. Token opaque cũng cần tra cứu và kiểm tra đúng trạng thái; việc chuỗi token trông ngẫu nhiên không tự giải quyết thu hồi.

Thời hạn ngắn chỉ giới hạn khoảng thời gian rủi ro. Nó không thay thế việc thu hồi khi sản phẩm đã cam kết vô hiệu quyền ngay sau một sự kiện.

## 6. Chặn cuộc đua giữa thu hồi và sử dụng liên kết

### 6.1. Kiểm tra trước rồi ghi sau có thể để lọt hành động

Xét hai request đồng thời:

```text
T1: đọc token, thấy chưa bị thu hồi
T2: thu hồi token và trả thành công
T1: dựa trên kết quả đọc cũ, cấp grant hoặc đổi mật khẩu
```

Nếu T1 không kiểm tra lại trong ranh giới cập nhật được bảo vệ, thu hồi có thể đã báo thành công nhưng quyền cũ vẫn được sử dụng. Vấn đề tương tự xuất hiện khi token được đổi thành grant trước sự kiện thu hồi, rồi grant chỉ được kiểm tra thời hạn.

### 6.2. Chọn một điểm tuần tự hóa chung

Một thiết kế có thể dùng khóa theo tài khoản và purpose trong cơ sở dữ liệu. Các luồng thu hồi, đổi token, phát hành grant và hoàn tất hành động phải phối hợp trên cùng nguồn trạng thái, với thứ tự khóa nhất quán.

Mã giả thu hồi cả phạm vi:

```text
BEGIN TRANSACTION
  scope = lockRecoveryScope(tenantId, accountId, purpose)
  require caller is authorized for this scope

  previousEpoch = scope.currentEpoch
  scope.currentEpoch = previousEpoch + 1
  record audit event with scope, actor, reason and new epoch
  record outbox event if other components need notification
COMMIT

return revocation confirmed for this scope
```

Mã giả hoàn tất hành động:

```text
BEGIN TRANSACTION
  scope = lockRecoveryScope(tenantId, accountId, purpose)
  grant = lockGrant(grantReference)
  source = loadSourceChallenge(grant.sourceChallengeId)

  require grant is bound to this account, tenant and purpose
  require grant.usedAt == null and grant.revokedAt == null
  require serverNow < grant.expiresAt
  require grant.issuedEpoch == scope.currentEpoch
  require source has not been revoked for this action
  require contact version and account policy are still valid

  apply permitted recovery change
  mark grant used
  invalidate competing rights according to policy
  persist audit and required outbox events
COMMIT
```

Đây là mã giả về tính nhất quán, không phải một triển khai cơ sở dữ liệu hoàn chỉnh. Khi thu hồi riêng challenge, luồng thu hồi cũng phải dùng cơ chế đồng bộ tương thích với luồng hoàn tất và đổi token. Với thiết kế nhiều kho dữ liệu, cần cơ chế bảo đảm tương đương, không giả định một giao dịch local bao phủ mọi hệ thống.

Kết quả được xác định bởi thứ tự commit đã bảo vệ:

- Thu hồi commit trước thì hành động sử dụng quyền cũ phải bị từ chối.
- Hành động hợp lệ commit trước thì thu hồi không thể làm thay đổi đó “chưa từng xảy ra”. Cần chuyển sang xử lý sự cố nếu thay đổi có dấu hiệu trái phép.
- Hai request hoàn tất dùng cùng grant không được tạo hai lần thay đổi thành công.

Thu hồi là biện pháp chặn quyền còn tồn tại. Nó không phải thao tác hoàn tác mật khẩu đã đổi, khôi phục yếu tố đã xóa hoặc lấy lại dữ liệu mà kẻ tấn công đã đọc.

## 7. Cache, nhiều vùng triển khai và khoảng trễ hiệu lực

Một hệ thống có thể lưu challenge trong cơ sở dữ liệu nhưng cache epoch hoặc trạng thái thu hồi ở nhiều node. Nếu node vẫn dùng cache cũ sau khi thu hồi đã xác nhận, liên kết có thể hoạt động thêm một khoảng thời gian.

Cần xác định rõ mức bảo đảm:

| Thiết kế kiểm tra | Hệ quả cần tính |
|---|---|
| Mỗi hành động nhạy cảm đọc nguồn có thẩm quyền với bảo đảm nhất quán phù hợp | Có thể thiết lập hiệu lực thu hồi theo điểm commit đã xác định |
| Kiểm tra từ cache với TTL | Có cửa sổ chấp nhận trạng thái cũ nếu không có biện pháp bổ sung |
| Lan truyền sự kiện thu hồi bất đồng bộ | Sự kiện có thể đến trễ, giao lặp hoặc cần retry; không mặc định có hiệu lực tức thì ở mọi nơi |
| Đọc replica có độ trễ | Có thể nhìn thấy epoch cũ dù primary đã tăng phiên bản |

Với điểm hoàn tất khôi phục, có thể yêu cầu kiểm tra trực tiếp tại nguồn thẩm quyền hoặc chuyển hành động về node sở hữu trạng thái tài khoản. Việc phát sự kiện vẫn hữu ích để dọn cache và cập nhật giao diện, nhưng không nên là lớp duy nhất chặn hành động nếu yêu cầu bảo mật là có hiệu lực ngay sau xác nhận.

Nếu không đọc được trạng thái bắt buộc, hành động nhạy cảm nên tạm bị từ chối thay vì chấp nhận quyền dựa trên dữ liệu không biết còn đúng hay không. Giao diện có thể thông báo lỗi tạm thời và cho thử lại; không biến sự cố hạ tầng thành bằng chứng rằng tài khoản không tồn tại.

Khi kiến trúc chỉ cung cấp hiệu lực theo thời gian hội tụ, cần mô tả và đo cửa sổ này một cách trung thực. Không trả “đã vô hiệu trên toàn hệ thống” trong khi vẫn còn một vùng chấp nhận token cũ mà chưa có biện pháp chặn.

## 8. Thu hồi không được trở thành công cụ gây gián đoạn

### 8.1. Bảo vệ endpoint quản lý thu hồi

Endpoint hủy hoặc thu hồi là thao tác thay đổi trạng thái. Nó cần phân quyền, ràng buộc đối tượng và chống CSRF phù hợp khi dùng cookie. Không triển khai GET có tác dụng thu hồi chỉ vì muốn đặt một liên kết “Hủy yêu cầu” trong email.

Email có thể chứa đường dẫn tới trang xác nhận hủy, nhưng GET đầu tiên không làm thay đổi quyền. Trình quét hoặc người vô tình mở thông điệp không nên tự động hủy quá trình của người dùng.

Nếu dùng token chuyên cho thao tác hủy, phải tách mục đích và phạm vi khỏi token dùng để khôi phục. Token hủy một yêu cầu không được cấp quyền đổi mật khẩu, cũng không được tự động cho phép chặn toàn bộ recovery của tài khoản.

Khả năng đọc một thư cảnh báo chưa đủ để thực hiện mọi hành động quản trị tài khoản, đặc biệt khi chính hộp thư có thể bị xâm nhập. Phạm vi hủy và yêu cầu xác minh cần được thiết kế theo rủi ro gây gián đoạn.

### 8.2. Tính lặp lại và phản hồi công khai

Gửi cùng lệnh thu hồi nhiều lần không được tái kích hoạt quyền hoặc gây tác dụng phụ vượt phạm vi. Với thu hồi theo epoch, có thể dùng mã thao tác/idempotency phù hợp để một lần retry được nhận diện là cùng quyết định, thay vì vô tình làm ảnh hưởng quyền mới phát hành sau quyết định đầu tiên.

Không tiết lộ số liên kết đang tồn tại hoặc định danh đích qua endpoint chưa xác minh. Phản hồi công khai cần tránh giúp người gọi dò tài khoản. Giao diện quản lý đã xác thực có thể cung cấp thông tin chi tiết hơn trong phạm vi quyền được phép.

## 9. Xử lý email đang chờ gửi và liên kết đã giao

Một challenge có thể bị thu hồi trong lúc email còn ở hàng đợi. Worker gửi cần kiểm tra lại quyền gửi theo trạng thái hiện hành trước khi tạo hoặc chuyển thông điệp cho nhà cung cấp. Điều này giảm việc giao một liên kết chắc chắn không còn dùng được.

Tuy nhiên, giữa lần kiểm tra cuối và lúc nhà cung cấp nhận thư vẫn có thể có cuộc đua. Một email đã chuyển sang hạ tầng bên ngoài có thể tiếp tục được giao sau thu hồi. Vì vậy, an toàn phải nằm ở kiểm tra quyền tại thời điểm sử dụng, không phụ thuộc khả năng chặn giao thư tuyệt đối.

Các thành phần vận hành cần thống nhất:

- Retry gửi thư không được phát hành challenge mới để “thay” một challenge đã bị thu hồi nếu chưa có yêu cầu và chính sách cho phép.
- Job gửi lại phải giữ đúng account, purpose, kênh và phiên bản đã được phê duyệt.
- Dữ liệu token trong outbox, hàng đợi lỗi và log phải được bảo vệ theo vòng đời bí mật.
- Xóa payload gửi thư không được làm mất bằng chứng audit cần thiết; audit không cần lưu token bản rõ.

Khi người dùng mở một email đã giao nhưng quyền đã bị thu hồi, trang có thể thông báo:

> Liên kết này không còn sử dụng được. Bạn có thể bắt đầu lại quy trình khôi phục hoặc liên hệ hỗ trợ nếu nghi ngờ hoạt động bất thường.

Không cần công khai việc thu hồi do email bị nghi xâm nhập, tài khoản bị điều tra hoặc nhân viên nào thực hiện. Lý do chi tiết thuộc dữ liệu nội bộ được phân quyền.

## 10. Ví dụ theo dòng thời gian

Giả sử hệ thống dùng epoch riêng cho đặt lại mật khẩu và kiểm tra epoch cả khi đổi token lẫn khi hoàn tất bằng grant.

| Thời điểm | Sự kiện | Trạng thái liên quan |
|---|---|---|
| 09:00 | Phát hành challenge C1 cho Lan | `C1.issuedEpoch=18`, chưa tiêu thụ |
| 09:01 | Lan xác nhận liên kết và nhận G1 | C1 đã tiêu thụ; `G1.issuedEpoch=18` |
| 09:02 | C1 được mở lại ở thiết bị khác | Không tạo thêm grant vì token đã dùng |
| 09:03 | Thao tác thu hồi được xác thực commit | Epoch hiện tại tăng lên 19 |
| 09:04 | Người đang cầm G1 gửi mật khẩu mới | Từ chối vì grant ở epoch 18 |
| 09:05 | Phát hành yêu cầu mới theo chính sách | Challenge mới ghi epoch 19 |

Nếu chỉ đánh dấu token C1 là đã dùng mà không kiểm tra epoch hoặc nguồn của G1, người giữ G1 vẫn có thể đổi mật khẩu ở 09:04. Đây là lý do cần xác định tập quyền phải đóng, thay vì chỉ xử lý chuỗi token trong email.

Nếu mật khẩu đã đổi hợp lệ và commit lúc 09:02:59, còn thu hồi commit lúc 09:03:00, thu hồi không đảo ngược kết quả trước đó. Khi nghi ngờ chiếm đoạt, phải xem xét riêng việc thu hồi phiên, khóa hành động nhạy cảm và quy trình xác minh lại.

## 11. Audit và tiêu chí kiểm tra thiết kế

Một sự kiện audit thu hồi có thể chứa mã yêu cầu thao tác, chủ thể thực hiện, tenant, tham chiếu tài khoản nội bộ, phạm vi, mã lý do, epoch trước/sau và thời điểm commit. Với thu hồi riêng, ghi tham chiếu challenge hoặc yêu cầu phù hợp.

Không ghi token bản rõ, mật khẩu mới hoặc toàn bộ URL khôi phục. Mã tham chiếu vẫn có thể liên kết hoạt động của cá nhân nên cần hạn chế người đọc và thời gian lưu. Nếu thu hồi theo epoch, đừng báo một số lượng liên kết “đã cập nhật” như bằng chứng hiệu lực khi thực tế không có thao tác cập nhật từng dòng.

Các tình huống đánh giá quan trọng:

| Tình huống | Kết quả mong muốn |
|---|---|
| Token còn hạn bị thu hồi trước khi đổi grant | Không cấp grant |
| Token đã đổi grant, sau đó yêu cầu nguồn bị thu hồi | Grant không hoàn tất được nếu thuộc phạm vi thu hồi |
| Thu hồi và đổi token chạy đồng thời | Kết quả tuân theo điểm tuần tự hóa, không tạo grant còn dùng được sau quyết định thu hồi tương ứng |
| Thu hồi và đổi mật khẩu chạy đồng thời | Kiểm tra lại trong ranh giới cập nhật, xác định rõ giao dịch nào thắng |
| Hai lần hoàn tất dùng cùng grant | Không có hai lần thay đổi thành công |
| Email thay đổi sau khi phát hành | Quyền dựa trên phiên bản kênh cũ bị chặn theo chính sách |
| Endpoint khởi tạo bị gọi lặp | Không tùy ý hủy grant đã xác minh của người thật |
| Node hoặc replica còn cache cũ | Điểm thực thi nhạy cảm không chấp nhận quyền cũ vượt cam kết hiệu lực |
| Không đọc được kho trạng thái thu hồi | Không cho phép hành động bằng trạng thái không xác minh được |
| Trình quét mở đường dẫn hủy bằng GET | Không phát sinh thay đổi bảo mật |
| Retry cùng quyết định thu hồi sau khi có challenge mới | Không vô tình biến retry cũ thành quyết định thu hồi mới |
| Email đã vào nhà cung cấp trước khi thu hồi | Có thể vẫn được giao nhưng liên kết không cấp quyền khi mở |

Các số liệu vận hành có thể theo dõi độ trễ lan truyền, lỗi thu hồi, lỗi đọc trạng thái và số lần sử dụng quyền bị từ chối sau thu hồi. Tránh dùng email hoặc token làm nhãn metric và tránh diễn giải mọi lần mở liên kết cũ là hành vi tấn công.

## 12. Bài tập áp dụng

Lan có tài khoản bật MFA và còn email dự phòng. Hệ thống phát hành liên kết đặt lại mật khẩu, sau đó Lan đổi liên kết thành grant. Bộ phận hỗ trợ nhận được báo cáo nghi ngờ hộp thư bị xâm nhập và thực hiện lệnh thu hồi. Cùng lúc đó, một POST đặt mật khẩu mới đang xử lý trên node khác.

Hãy đề xuất thiết kế và giải thích:

1. Lệnh thu hồi tác động tới token, grant, những purpose nào và các phiên đăng nhập ra sao?
2. Nguồn trạng thái nào quyết định quyền còn hiệu lực, và node xử lý POST có được dùng cache cũ không?
3. Điều kiện nào phải được kiểm tra lại trước khi commit thay đổi mật khẩu?
4. Nếu đổi mật khẩu commit trước thu hồi, thao tác xử lý sự cố nào cần được xem xét thêm?
5. Làm sao tránh việc người ngoài liên tục gửi lại email để phá khôi phục của Lan?

Một thiết kế đầy đủ phải nêu được phạm vi và thời điểm thu hồi có hiệu lực, đồng thời chặn mọi quyền còn sống bắt nguồn từ liên kết trong phạm vi đó. Trạng thái trong cơ sở dữ liệu chỉ có ý nghĩa bảo mật khi các điểm cấp và sử dụng quyền đều kiểm tra nó một cách nhất quán.
