# Recovery timeout experience: trải nghiệm khi khôi phục tài khoản hết thời gian

Người dùng đang nhập mã khôi phục thì trang báo “Phiên hết hạn”. Họ không biết mã hết hạn, trang bị mất kết nối, hay mật khẩu mới đã được lưu nhưng phản hồi chưa về. Nếu giao diện chỉ đưa họ về màn hình đăng nhập, họ có thể tiếp tục dùng một liên kết cũ, gửi nhiều yêu cầu mới hoặc tưởng tài khoản đã được khôi phục.

**Recovery timeout experience** là cách một hệ thống giải thích giới hạn thời gian, cảnh báo khi cần và đưa người dùng đến hành động tiếp theo an toàn khi không thể tiếp tục theo trạng thái hiện tại.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, trải nghiệm này phải gắn với quy trình khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là giảm bối rối và thao tác thừa, đồng thời giữ nguyên thời hạn, điều kiện xác minh và cơ chế chống chiếm đoạt tài khoản do máy chủ thực thi.

## 1. Không gom mọi loại timeout thành một lỗi

Các giới hạn thời gian khác nhau trả lời những câu hỏi khác nhau.

| Loại giới hạn | Ý nghĩa | Hành động có thể phù hợp |
| --- | --- | --- |
| Thời hạn mã hoặc liên kết | Bằng chứng được phát hành không còn được chấp nhận sau một mốc | Yêu cầu mã mới hoặc bắt đầu yêu cầu mới theo chính sách |
| Thời hạn giao dịch khôi phục | Toàn bộ lần khôi phục đã vượt thời gian tối đa | Bắt đầu lại từ điểm mà hệ thống cho phép |
| Idle timeout của phiên khôi phục | Phiên không có hoạt động được tính là hợp lệ trong một khoảng thời gian | Xác minh lại hoặc mở một phiên khôi phục mới |
| Absolute timeout của phiên | Phiên đạt giới hạn tối đa dù vẫn có hoạt động | Thiết lập lại ngữ cảnh xác minh theo chính sách |
| Timeout yêu cầu mạng | Trình duyệt chưa nhận được kết quả trong thời gian chờ | Kiểm tra trạng thái; chưa vội kết luận giao dịch thất bại |
| Khoảng chờ gửi lại | Chưa được phép phát sinh một lần gửi mã tiếp theo | Chờ đến thời điểm máy chủ cho phép |
| Chờ xử lý thủ công | Hồ sơ còn đang được xem xét theo quy trình hỗ trợ | Xem hướng dẫn hoặc trạng thái phù hợp, không coi là mã hết hạn |

Khoảng chờ gửi lại mã không phải thời gian sống của mã. Timeout mạng cũng không chứng minh phiên khôi phục đã hết hạn.

Trước khi chọn câu chữ, hệ thống cần biết đối tượng nào đã hết hiệu lực và mức thông tin được phép công khai tại bước đó. Khi không thể phân biệt an toàn giữa hết hạn, đã dùng hoặc đã bị thu hồi, có thể dùng thông báo chung “Không thể tiếp tục bằng liên kết này”.

## 2. Máy chủ quyết định hiệu lực, giao diện giúp người dùng hiểu

### 2.1. Đồng hồ đếm ngược không phải quyền truy cập

Người dùng có thể đổi giờ hệ thống, tắt JavaScript, giữ một tab cũ hoặc sửa dữ liệu phía trình duyệt. Vì vậy, việc một nút vẫn mở hay bộ đếm còn thời gian không chứng minh mã hoặc phiên còn hợp lệ.

[OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) nhấn mạnh việc thực thi hết hạn phiên ở phía máy chủ và phân biệt idle timeout với absolute timeout. Giao diện có thể hỗ trợ cảnh báo, nhưng không thay thế việc vô hiệu hóa phiên.

Tương tự, [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) yêu cầu token khôi phục có thời hạn phù hợp và chỉ dùng một lần. Một yêu cầu đến sau hạn không được chấp nhận chỉ vì trang cũ vẫn hiển thị thời gian còn lại.

Máy chủ cần kiểm tra trạng thái ở thời điểm xử lý hành động nhạy cảm. Người dùng bắt đầu gõ trước hạn không tự tạo quyền hoàn tất sau hạn.

### 2.2. Giới hạn áp dụng phụ thuộc vào bước hiện tại

Giả sử bước nhập mã có:

- Mã hết hạn lúc 09:05.
- Giao dịch hết hạn lúc 09:12.
- Phiên giới hạn của bước nhập mã hết hạn lúc 09:08.

Nếu cả ba giới hạn cùng áp dụng cho thao tác xác nhận mã, mốc sớm nhất là 09:05. Trang nên mô tả thời gian thực sự còn lại cho thao tác đó.

Tuy nhiên, không lấy thời hạn của mọi token từng xuất hiện rồi áp dụng cho toàn bộ luồng. Sau khi một mã đã được tiêu thụ hợp lệ và đổi thành phiên khôi phục giới hạn, bước đặt mật khẩu có thể có chính sách thời hạn riêng. Máy chủ phải cung cấp giới hạn phù hợp với trạng thái mới.

Không để frontend tự suy ra rằng “mã mới vừa được gửi” đồng nghĩa với “toàn bộ giao dịch được gia hạn”. Hai việc đó cần có quyết định chính sách riêng.

### 2.3. Tải trạng thái không được vô tình giữ phiên sống mãi

Nếu mọi lần tải trạng thái đều được tính là hoạt động làm mới idle timeout, một vòng polling có thể giữ phiên khôi phục tồn tại ngay cả khi người dùng đã rời đi.

Thiết kế cần phân biệt hoạt động người dùng được chính sách chấp nhận với hoạt động nền của giao diện. Absolute timeout vẫn cần được thực thi độc lập với việc trang liên tục gửi yêu cầu.

Không dùng heartbeat phía trình duyệt để tự kéo dài quyền khôi phục mà người dùng và chính sách không chủ động cho phép.

## 3. Cung cấp một mô hình thời gian rõ ràng cho giao diện

Một phản hồi nội bộ cho trang đang có ngữ cảnh khôi phục hợp lệ có thể chứa:

```json
{
  "state": "ACTIVE",
  "stage": "VERIFY_CODE",
  "version": 7,
  "serverNow": "2026-11-23T09:00:00Z",
  "actionExpiresAt": "2026-11-23T09:05:00Z",
  "resendAvailableAt": "2026-11-23T09:00:45Z",
  "canResend": false
}
```

Đây là schema minh họa, không phải API chung cho mọi hệ thống.

- `actionExpiresAt` là hạn áp dụng cho thao tác hiện tại.
- `resendAvailableAt` nói về lần gửi tiếp theo.
- `version` giúp nhận biết phản hồi thuộc trạng thái nào.
- `canResend` hỗ trợ trình bày nút, nhưng máy chủ vẫn kiểm tra quyền khi người dùng thực hiện.

Không cung cấp endpoint công khai cho phép nhập email rồi đọc toàn bộ trạng thái khôi phục. Thông tin trả về phải được giới hạn theo ngữ cảnh và mức xác minh.

### Ước lượng thời gian hiển thị

Có thể tính khoảng còn lại từ thời gian máy chủ, rồi giảm theo thời gian đơn điệu ở trình duyệt:

```javascript
function createTimeEstimate(snapshot) {
  const serverNow = Date.parse(snapshot.serverNow);
  const deadline = Date.parse(snapshot.actionExpiresAt);

  if (!Number.isFinite(serverNow) || !Number.isFinite(deadline)) {
    throw new Error("Không có dữ liệu thời gian hiển thị hợp lệ.");
  }

  const initialRemaining = Math.max(0, deadline - serverNow);
  const baseline = performance.now();

  return function remainingMilliseconds() {
    const elapsed = performance.now() - baseline;
    return Math.max(0, initialRemaining - elapsed);
  };
}
```

Đây chỉ là hàm ước lượng cho giao diện. Nó chưa tính độ trễ truyền phản hồi và không thay thế đồng hồ máy chủ. Hành vi khi thiết bị ngủ hoặc trình duyệt tạm dừng cũng cần được xử lý bằng việc tải lại trạng thái khi phù hợp.

Không triển khai bộ đếm chỉ bằng cách trừ một giây ở mỗi callback rồi coi kết quả là chính xác. Timer trong tab nền có thể bị trì hoãn.

Khi người dùng quay lại tab hoặc nối mạng lại, giao diện nên lấy trạng thái hiện tại trước khi tiếp tục một hành động nhạy cảm. Nếu chưa tải được, cần diễn đạt rằng trạng thái chưa được xác nhận.

## 4. Trải nghiệm trước khi hết hạn

### 4.1. Nêu giới hạn khi nó có ích

Người dùng nên biết giới hạn có liên quan trước khi bị chặn, chẳng hạn:

> Mã này có thời hạn sử dụng. Hãy nhập mã gần đây nhất được hệ thống cho phép. Nếu không còn dùng được, bạn có thể yêu cầu mã mới.

Khi biết chính xác hạn của mã đang dùng, có thể hiển thị thời gian còn lại hoặc thời điểm hết hiệu lực. Không khẳng định “còn đủ thời gian” từ một giá trị cũ chưa được đồng bộ.

Không bắt người dùng hoàn thành các phần không cần thiết trong khoảng thời gian nhạy cảm. Chẳng hạn, phần giải thích dài về chính sách có thể được trình bày trước khi phát mã, thay vì chiếm phần lớn thời gian sống của mã.

### 4.2. Cảnh báo có mục đích

Một cảnh báo gần hết hạn cần nói rõ điều gì sắp hết:

- “Mã xác minh sắp hết hiệu lực.”
- “Phiên khôi phục hiện tại sắp kết thúc.”
- “Bạn vẫn cần chờ trước khi yêu cầu gửi lại mã.”

Tránh một đồng hồ không nhãn ở góc trang. Nó khiến người dùng không biết đang đếm đến lúc mã hết hạn hay đến lúc được gửi lại.

Không dùng câu gây áp lực như “Chỉ còn vài giây để cứu tài khoản”. Thông báo nên bình tĩnh, cụ thể và gắn với lựa chọn tiếp theo.

Nếu thiết kế hỗ trợ xin thêm thời gian cho một phiên, nút cần gọi một hành động được máy chủ cho phép. Không chỉ đặt lại bộ đếm tại trình duyệt. Khi máy chủ từ chối, giao diện phải giải thích bước tiếp theo thay vì vẫn hiển thị một hạn mới giả.

### 4.3. Khả năng tiếp cận và giới hạn bảo mật

Người dùng trình đọc màn hình, người có hạn chế vận động hoặc người cần đọc chậm có thể cần nhiều thời gian hơn. Không nên coi mọi thời hạn là cố định chỉ vì tính năng thuộc lĩnh vực bảo mật.

[W3C WAI về Timing Adjustable](https://www.w3.org/WAI/WCAG22/Understanding/timing-adjustable) trình bày các cách cho người dùng kiểm soát giới hạn thời gian và các ngoại lệ liên quan. Một số mã xác thực có giới hạn thời gian thiết yếu có thể thuộc ngoại lệ; điều đó không có nghĩa mọi idle timeout hoặc chuyển trang tự động đều mặc nhiên được miễn.

Cần chọn giải pháp theo từng giới hạn. Có thể giảm thao tác không cần thiết, cho phép dán hoặc tự điền mã, cung cấp phương thức phù hợp hơn, hoặc hỗ trợ gia hạn phiên nếu chính sách cho phép. Không tự kéo dài token đã hết hạn.

Đồng hồ có thể cập nhật trực quan mỗi giây, nhưng không nên phát toàn bộ số giây qua live region. Chỉ thông báo các mốc có ý nghĩa. Thông tin hết hạn và lựa chọn tiếp theo cần tồn tại để người dùng đọc lại.

## 5. Khi thời gian hiển thị về không

Giao diện cần phân biệt ước lượng cục bộ với kết luận từ máy chủ.

| Tình trạng | Câu chữ có thể dùng | Bước tiếp theo |
| --- | --- | --- |
| Bộ đếm cục bộ về không, chưa có xác nhận | “Đang kiểm tra liệu bước này còn có thể tiếp tục.” | Tải lại trạng thái theo ngữ cảnh hiện tại |
| Máy chủ xác nhận mã không còn dùng được | “Không thể xác nhận bằng mã này. Bạn có thể yêu cầu mã mới nếu được phép.” | Cung cấp hành động phát mã theo chính sách |
| Máy chủ xác nhận phiên khôi phục đã hết hạn | “Phiên khôi phục đã hết thời gian. Hãy bắt đầu lại để xác minh an toàn.” | Điểm bắt đầu lại được máy chủ xác định |
| Không có kết nối để xác nhận | “Chưa kiểm tra được trạng thái khôi phục. Kiểm tra kết nối rồi thử lại.” | Nút kiểm tra lại, không giả định giao dịch thất bại |
| Giao dịch đã hoàn tất và ngữ cảnh được phép biết | “Thao tác đã hoàn tất.” | Đưa đến bước đăng nhập hoặc hướng dẫn tiếp theo theo chính sách |

Các thông báo là ví dụ. Nếu trạng thái nội bộ không được phép công khai, dùng nhóm thông báo trung tính phù hợp.

Không kết luận “Mã đã hết hạn” chỉ vì một fetch timeout. Cũng không hiển thị thành công dựa trên việc người dùng đã nhấn nút trước khi đồng hồ về không.

### Giữ một điểm kết thúc rõ ràng

Màn hình hết hạn nên giải thích:

1. Bước nào không còn tiếp tục được.
2. Điều gì người dùng cần làm tiếp theo.
3. Thông tin nào phải nhập lại.
4. Lựa chọn hỗ trợ nếu không còn phương thức phù hợp.

Không để người dùng ở một biểu mẫu bị vô hiệu hóa mà không có đường đi tiếp. Nếu chỉ được bắt đầu lại, cần có hành động “Bắt đầu yêu cầu mới” rõ nghĩa.

Tránh chuyển trang ngay khi hết hạn rồi làm thông báo biến mất. Có thể thay vùng nội dung bằng trạng thái hết hạn, giữ hướng dẫn đọc được và đặt focus có chủ đích khi thay đổi đó phù hợp với tương tác hiện tại.

## 6. Timeout mạng sau hành động nhạy cảm

Tình huống khó nhất thường xảy ra sau khi người dùng gửi mật khẩu mới hoặc xác nhận thay đổi phương thức xác thực.

Có ba khả năng:

- Yêu cầu chưa đến máy chủ.
- Máy chủ đã nhận nhưng chưa hoàn tất.
- Máy chủ đã hoàn tất, còn phản hồi bị mất hoặc đến muộn.

Từ phía trình duyệt, timeout có thể không phân biệt được ba khả năng đó. Do vậy, câu “Thay đổi thất bại, hãy gửi lại” có thể sai.

Một thông báo phù hợp hơn:

> Chưa xác nhận được kết quả thao tác. Hệ thống đang kiểm tra trạng thái. Đừng gửi lại yêu cầu cho đến khi có hướng dẫn tiếp theo.

Nếu không thể kiểm tra tự động, cung cấp hành động kiểm tra lại có giới hạn và hướng dẫn cụ thể. Không để trạng thái “đang kiểm tra” kéo dài vô hạn mà không có lựa chọn.

### Đồng bộ theo giao dịch

Máy chủ có thể cung cấp trạng thái của chính giao dịch trong ngữ cảnh được bảo vệ. Nếu hành động hỗ trợ idempotency, yêu cầu thử lại phải gắn với cùng thao tác và cùng nội dung theo contract của hệ thống.

Một khóa idempotency không tự cấp quyền, không bỏ qua hết hạn và không biến yêu cầu mới thành giao dịch cũ. Máy chủ cần quyết định cách trả lại kết quả đã hoàn tất mà không thực hiện thay đổi lần nữa.

Không tự gửi lại một lệnh thay đổi mật khẩu liên tục chỉ vì trình duyệt không nhận phản hồi. Cũng không giữ mật khẩu mới trong log, URL hoặc kho lưu trữ phía trình duyệt để phục vụ retry.

Nếu kết quả cho biết đã hoàn tất, xử lý theo chính sách session của luồng. Không mặc định tự đăng nhập chỉ vì một thao tác khôi phục thành công.

## 7. Bắt đầu lại mà không phá vỡ ranh giới xác minh

Bắt đầu lại cần giảm công sức thừa, nhưng không được biến trạng thái đã hết hạn thành quyền còn hiệu lực.

Có thể giữ một số lựa chọn trình bày ít nhạy cảm, như ngôn ngữ hoặc nhu cầu trợ giúp giao diện. Việc giữ địa chỉ nhận, dữ liệu nhận dạng hoặc bằng chứng đã nhập cần có chính sách riêng, phù hợp với thiết bị dùng chung và mức nhạy cảm.

Không tự sao chép mã hết hạn sang yêu cầu mới. Không khôi phục mật khẩu hoặc mã bí mật từ localStorage, tham số URL hay lịch sử điều hướng.

### Điểm tiếp tục do máy chủ quyết định

Có thể chia việc bắt đầu lại thành các trường hợp:

| Trạng thái thật | Điểm có thể tiếp tục |
| --- | --- |
| Mã cũ hết hạn nhưng giao dịch còn hợp lệ | Yêu cầu bằng chứng mới trong giao dịch nếu chính sách cho phép |
| Phiên bước hiện tại hết hạn, còn bằng chứng khác đủ điều kiện | Máy chủ đánh giá lại và xác định bước được phép |
| Giao dịch hết hiệu lực hoàn toàn | Bắt đầu một yêu cầu mới |
| Đang có hồ sơ khôi phục thủ công | Hướng dẫn theo hồ sơ, không tự tạo nhiều hồ sơ trùng |

Không để frontend tự quyết định bỏ qua bước xác minh vì nó còn nhớ một biến `verified = true`.

Nếu việc xác minh trước đó có thể được tái sử dụng, máy chủ cần quản lý phạm vi, thời hạn và điều kiện của bằng chứng đó. Giao diện chỉ trình bày bước tiếp theo được cho phép.

## 8. Gửi lại mã, nhiều tab và thiết bị ngủ

### 8.1. Gửi lại không đồng nghĩa gia hạn

Khi người dùng yêu cầu mã mới, giao diện cần làm rõ chính sách áp dụng. Nếu mã mới thay thế mã trước, nói rõ chỉ dùng mã mới. Nếu hệ thống có quy tắc khác, không tự viết câu “mọi mã cũ đều bị hủy”.

Máy chủ quyết định:

- Có cho phép gửi lại hay không.
- Mã cũ có còn hiệu lực không.
- Thời hạn mã mới.
- Giới hạn của giao dịch và phiên có thay đổi không.
- Giới hạn chống lạm dụng còn lại.

Không tạo đường vòng cho phép gửi lại vô hạn để né thời hạn tối đa. Khoảng chờ gửi lại cần được thực thi phía máy chủ, ngay cả khi người dùng tải lại trang.

### 8.2. Nhiều tab

Một tab có thể hiển thị mã còn hạn, trong khi tab khác vừa hoàn tất hoặc bắt đầu yêu cầu mới. Giao diện không nên để phản hồi từ tab cũ ghi đè trạng thái mới khi người dùng tiếp tục.

Thông báo giữa các tab có thể hỗ trợ trải nghiệm, nhưng không là nguồn xác thực cuối cùng. Mỗi hành động nhạy cảm vẫn cần máy chủ kiểm tra phiên và giao dịch.

Khi người dùng bấm Back về biểu mẫu cũ, trạng thái được lưu trong lịch sử trình duyệt không chứng minh quyền còn hiệu lực. Trang cần đồng bộ phù hợp trước khi chấp nhận thao tác mới.

### 8.3. Thiết bị ngủ hoặc chuyển ứng dụng

Người dùng có thể rời trang để đọc email hoặc mở ứng dụng xác thực. Đây là một phần bình thường của khôi phục, không nên bị diễn đạt như hành vi sai.

Khi họ quay lại, tải trạng thái hiện tại và giải thích nếu cần mã mới. Không cho rằng việc mở lại tab là bằng chứng đủ để gia hạn phiên.

Nếu trạng thái không xác định do ngoại tuyến, giữ thông báo trung tính và cung cấp cách kiểm tra lại. Không hiển thị cả “Mã hết hạn” và “Đang xác minh mã” cùng lúc.

## 9. Mô hình trạng thái trình bày

Có thể dùng các trạng thái giao diện để tránh nhiều thông báo mâu thuẫn:

```text
ACTIVE
  -> EXPIRING_SOON
  -> CHECKING_CURRENT_STATE

CHECKING_CURRENT_STATE
  -> ACTIVE
  -> NO_LONGER_USABLE
  -> OUTCOME_PENDING
  -> COMPLETED
  -> CONNECTION_UNAVAILABLE

OUTCOME_PENDING
  -> CHECKING_CURRENT_STATE

CONNECTION_UNAVAILABLE
  -> CHECKING_CURRENT_STATE

NO_LONGER_USABLE
  -> START_ALLOWED_RECOVERY_PATH
```

Đây là mô hình trình bày minh họa, không phải state machine xác thực trên máy chủ.

Khi chuyển trạng thái:

- Chỉ nhận phản hồi phù hợp với giao dịch và phiên bản đang hiển thị.
- Bỏ qua phản hồi cũ có thể kéo màn hình về bước trước.
- Xóa trạng thái bận khi đã có kết quả cuối cùng.
- Không giữ nút gửi hoạt động trong một trạng thái mà máy chủ đã xác nhận không còn dùng được.
- Không coi nút bị vô hiệu hóa là biện pháp kiểm soát quyền.

Nếu một phản hồi bị nhóm thành “không thể tiếp tục”, giao diện không cần tiết lộ mọi lý do nội bộ. Máy chủ vẫn có thể ghi nhận nguyên nhân kỹ thuật bằng dữ liệu quan sát được giới hạn quyền truy cập.

## 10. Một diễn tiến hoàn chỉnh

Người dùng bắt đầu khôi phục tài khoản vì mất mật khẩu và không còn điện thoại cũ. Sau khi chọn một phương thức được hệ thống cho phép, họ nhận mã nhưng mất thời gian chuyển ứng dụng để đọc.

Trang cảnh báo rằng mã sắp hết hiệu lực. Khi quay lại, bộ đếm cục bộ đã về không nên giao diện kiểm tra trạng thái. Máy chủ cho biết mã không còn dùng được nhưng giao dịch vẫn cho phép yêu cầu bằng chứng mới. Người dùng nhận hướng dẫn lấy mã mới; hạn tối đa của giao dịch không tự được đặt lại.

Sau khi xác minh, người dùng nhập mật khẩu mới. Lần gửi này gặp timeout mạng. Giao diện nói chưa xác nhận được kết quả, kiểm tra trạng thái của thao tác và nhận được xác nhận đã hoàn tất. Nó không gửi lại thay đổi một cách mù quáng và không báo sai rằng mật khẩu chưa được lưu.

Người dùng được hướng dẫn đăng nhập theo chính sách của hệ thống. Những phiên cần thu hồi được xử lý ở máy chủ; giao diện không tự giữ một phiên khôi phục hết hạn như phiên đăng nhập đầy đủ.

Trải nghiệm timeout rõ ràng giúp người dùng hiểu điều gì đã hết hiệu lực, điều gì còn chưa biết và hành động an toàn nào có thể thực hiện tiếp theo.
