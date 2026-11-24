# Preserving user profile data trong khôi phục tài khoản

## 1. Khôi phục khả năng truy cập, giữ nguyên hồ sơ người dùng

Khi người dùng quên mật khẩu hoặc mất MFA, passkey hay thiết bị xác thực, mục tiêu của quy trình khôi phục là tái lập khả năng truy cập hợp lệ. Người dùng không nên mất tên hiển thị, ảnh đại diện, ngôn ngữ, thiết lập trợ năng hoặc dữ liệu hồ sơ chỉ vì cần thay phương thức xác thực.

**Preserving user profile data** là duy trì tính toàn vẹn, mối liên kết và phạm vi sử dụng hợp lệ của dữ liệu hồ sơ trong suốt quy trình khôi phục. Điều này không có nghĩa giữ mọi giá trị mãi mãi, phục hồi mọi bản sao cũ hoặc tự động khôi phục những thông tin đã bị xóa hợp lệ.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, việc bảo toàn hồ sơ phải đi cùng xác minh danh tính, đánh giá rủi ro, token dùng một lần, chống lạm dụng và kiểm soát phiên. Bảo toàn dữ liệu không thể được dùng làm lý do để giữ lại thông tin xác thực đã bị lộ hoặc cấp quyền truy cập trước khi đủ điều kiện.

Ví dụ, Mai mất điện thoại chứa MFA. Sau khi hoàn tất khôi phục, tài khoản của Mai vẫn có cùng account ID, hồ sơ cá nhân và quan hệ với dữ liệu nghiệp vụ. Yếu tố MFA bị mất được xử lý theo kế hoạch bảo mật, nhưng hệ thống không tạo một tài khoản trắng rồi yêu cầu Mai nhập lại hồ sơ.

Một bất biến quan trọng là:

```text
Khôi phục thông tin xác thực
    không tự động đồng nghĩa với
tạo lại tài khoản, đổi chủ sở hữu hoặc phục hồi hồ sơ từ bản cũ
```

## 2. Phân loại dữ liệu trước khi thiết kế thao tác khôi phục

Trong nhiều hệ thống, dữ liệu hồ sơ và dữ liệu xác thực cùng nằm trong một bảng `users`. Vị trí lưu trữ không làm chúng có cùng ý nghĩa bảo mật. Cần phân loại theo chức năng và thẩm quyền thay đổi.

| Nhóm dữ liệu | Ví dụ | Cách xử lý trong khôi phục thông thường |
| --- | --- | --- |
| Định danh ổn định | Account ID, tenant ID, khóa tham chiếu hồ sơ | Giữ nguyên và kiểm tra đúng đích |
| Hồ sơ trình bày | Tên hiển thị, avatar, mô tả cá nhân | Giữ trạng thái hiện hành, không ghi đè từ snapshot khôi phục |
| Tùy chọn trải nghiệm | Ngôn ngữ, múi giờ, trợ năng | Giữ nguyên trừ khi có thao tác riêng được phép |
| Kênh liên lạc và trạng thái xác minh | Email, điện thoại, trạng thái xác minh | Xử lý theo policy bảo mật; không coi là trường hồ sơ vô hại |
| Thông tin xác thực và phiên | Password verifier, MFA, passkey, refresh token | Chỉ thay đổi đúng kế hoạch đã được cho phép |
| Quyền và trạng thái quản trị | Vai trò, thành viên tenant, khóa tài khoản | Không tự phục hồi hoặc cộng thêm trong thao tác đặt lại mật khẩu |
| Liên kết dữ liệu nghiệp vụ | Hồ sơ học tập, đơn hàng, tài nguyên được sở hữu | Giữ mối liên kết tới đúng account ID; không chuyển chủ ngoài phạm vi |
| Hồ sơ đã xóa hoặc bị hạn chế | Dữ liệu đang chờ xóa, dữ liệu bị cách ly | Tôn trọng vòng đời và quyền hạn hiện tại |

Một trường có tên `contactEmail` có thể chỉ phục vụ hiển thị, hoặc có thể là nơi nhận token khôi phục. Trường hợp thứ hai ảnh hưởng trực tiếp đến quyền kiểm soát tài khoản. Không quyết định độ nhạy cảm chỉ bằng tên cột hoặc việc nó xuất hiện trong màn hình chỉnh sửa hồ sơ.

Tương tự, tên hiển thị không phải danh tính đã xác minh. Giữ nguyên tên hiển thị giúp bảo toàn trải nghiệm, nhưng không chứng minh người yêu cầu là chủ tài khoản. Dữ liệu hồ sơ công khai hoặc dễ biết không nên được dùng thay bằng chứng khôi phục đủ mạnh.

## 3. Giữ account ID thay vì tạo một người dùng mới

Định danh ổn định là điểm nối giữa xác thực, hồ sơ, quyền và dữ liệu nghiệp vụ. Khôi phục thường nên cập nhật khả năng xác thực của chính tài khoản hiện có, không thay khóa chính của người dùng.

```text
Trước khôi phục:
  account_id = A17
  authentication → A17
  profile        → A17
  learning_data  → A17

Sau khôi phục:
  account_id = A17
  authentication mới → A17
  profile hiện hành  → A17
  learning_data      → A17
```

Nếu hệ thống tạo A99 thay cho A17 rồi chỉ sao chép tên và email, người dùng có thể trông giống trước nhưng đã mất liên kết với dữ liệu. Các quyền chia sẻ, nhật ký, giao dịch hoặc tham chiếu ở dịch vụ khác vẫn trỏ đến A17. Sao chép thêm dữ liệu một cách tùy tiện còn có thể gây trùng hoặc chuyển quyền không đúng.

Không dùng email làm định danh nội bộ bất biến. Email có thể thay đổi hoặc được tái cấp; hai tài khoản có thể có những dữ liệu liên lạc giống nhau theo cách mà policy không cho phép tự nối. Tìm đúng tài khoản là một phần của quy trình xác minh, không phải phép suy luận “email giống thì cùng chủ”.

Đối với hệ thống nhiều tenant, mọi thao tác cần ràng buộc với tenant và account ID đúng phạm vi. Một account ID trong request từ client không được tin nếu chưa đối chiếu với quyền khôi phục đã được máy chủ xác minh.

Nếu thực sự cần hợp nhất tài khoản hoặc di chuyển danh tính, đó là luồng riêng với bằng chứng cho các tài khoản liên quan, kế hoạch chuyển dữ liệu và quyền tương ứng. Không âm thầm thực hiện việc đó trong một endpoint đặt lại mật khẩu.

## 4. Tách phạm vi ghi của xác thực và hồ sơ

Một thiết kế dễ kiểm soát có thể tách các nhóm dữ liệu:

```text
Account
  account_id, tenant_id, lifecycle_state

AccountAuthentication
  account_id, password_verifier, authentication_version, session_epoch

UserProfile
  account_id, display_name, locale, timezone, avatar_reference
  profile_version, updated_at

AccountContact
  account_id, contact_type, contact_value, verification_state

RecoveryRequest
  request_id, account_id, tenant_id, allowed_actions, expires_at, state
```

Tách bảng không phải điều kiện bắt buộc. Một hệ thống dùng chung bảng vẫn có thể bảo toàn hồ sơ nếu câu lệnh ghi chỉ cập nhật các cột được cho phép. Ngược lại, tách nhiều bảng nhưng dùng một hàm “save toàn bộ user” vẫn có thể làm mất dữ liệu.

Contract của thao tác khôi phục cần nêu rõ tập trường được ghi. Ví dụ, đặt lại mật khẩu có thể thay password verifier, tăng phiên bản xác thực, vô hiệu hóa quyền khôi phục đã dùng và xử lý phiên theo policy. Nó không cần cập nhật tên hiển thị, ngày sinh, avatar hoặc ngôn ngữ.

Tránh một DTO dùng chung cho cập nhật hồ sơ và khôi phục:

```text
RecoverAccountRequest
  accountId
  newPassword
  displayName
  email
  roles
  avatar
```

DTO này tạo cơ hội ghi nhầm hoặc mass assignment: client có thể gửi thêm trường mà endpoint khôi phục không nên có quyền xử lý. Dùng command chuyên biệt và danh sách trường được phép, không ánh xạ tự động toàn bộ JSON vào thực thể người dùng.

Một command thay mật khẩu tối thiểu có thể chỉ chứa token khôi phục và mật khẩu mới trong kênh truyền được bảo vệ. Account ID đích và quyền thay đổi phải được suy ra từ trạng thái khôi phục đã xác minh phía máy chủ, không từ một `userId` tùy chọn do client chọn lại sau bước kiểm tra.

## 5. Tránh ghi đè hồ sơ mới bằng snapshot cũ

Yêu cầu khôi phục có thể tồn tại đủ lâu để dữ liệu thay đổi. Người dùng có thể vẫn còn một phiên hợp lệ trên thiết bị khác và chỉnh ngôn ngữ hoặc avatar trong khi yêu cầu đang chờ. Nhân viên có quyền cũng có thể cập nhật dữ liệu theo một quy trình khác.

Một lỗi thường gặp là lưu toàn bộ đối tượng user lúc tạo yêu cầu rồi ghi nó lại khi khôi phục xong:

```text
09:00  Tạo recovery request, snapshot locale = vi
09:05  Người dùng trên phiên khác đổi locale = en
09:10  Khôi phục xong, save snapshot cũ
Kết quả sai: locale bị trả lại vi
```

Bản snapshot có thể phục vụ ngữ cảnh xác minh hoặc truy vết nếu policy cho phép, nhưng không nên mặc nhiên là nguồn dữ liệu để khôi phục toàn bộ hồ sơ. Nguồn chuẩn cho các trường hồ sơ không thuộc phạm vi khôi phục là trạng thái hiện hành hợp lệ.

Đối với ORM, một thực thể detached cũ hoặc thao tác merge toàn bộ có thể ghi lại các cột mà code khôi phục không chủ ý thay đổi. Cần hiểu tập cột thực tế được cập nhật và ràng buộc phiên bản; không suy ra an toàn chỉ từ việc code chỉ có một lời gọi `save`.

Hai cách thường dùng là:

- Cập nhật có mục tiêu đúng các cột xác thực cần thay đổi.
- Nạp trạng thái hiện tại trong cơ chế đồng bộ phù hợp, thay đúng trường và dùng kiểm tra phiên bản để phát hiện xung đột.

Nếu tách `authentication_version` và `profile_version`, việc cập nhật hồ sơ thông thường không nhất thiết làm thất bại mọi yêu cầu thay mật khẩu. Tuy nhiên, thay đổi có ảnh hưởng đến điều kiện khôi phục — như đổi kênh nhận mã hoặc khóa tài khoản — vẫn phải được kiểm tra lại ở cổng thực thi. Tách version không có nghĩa bỏ qua quan hệ bảo mật giữa các nhóm dữ liệu.

## 6. Luồng khôi phục có bảo toàn hồ sơ

Một luồng có thể được thiết kế như sau:

1. Tiếp nhận yêu cầu và xác định tài khoản qua quy trình được policy cho phép.
2. Xác minh danh tính, đánh giá rủi ro và tạo quyền khôi phục có phạm vi.
3. Gắn quyền đó với account ID, tenant, loại hành động và thời hạn.
4. Khi người dùng hoàn tất, kiểm tra lại token, trạng thái tài khoản, quyền và các điều kiện hiện tại.
5. Thay đổi đúng thông tin xác thực được cho phép; tiêu thụ quyền thực thi một lần.
6. Giữ nguyên hồ sơ hiện hành và các liên kết không thuộc phạm vi thay đổi.
7. Xử lý phiên, cache và thông báo theo kế hoạch; ghi rõ kết quả từng phần.

Trong bước 4, không trả toàn bộ hồ sơ cho người chỉ mới biết email hoặc đang ở phiên khôi phục hạn chế. Bảo toàn dữ liệu gồm cả việc không làm lộ dữ liệu đó trước khi người dùng có quyền truy cập tương ứng.

Sau khi khôi phục thành công, ứng dụng có thể nạp hồ sơ bằng account ID hiện có. Không dùng biểu mẫu “hoàn tất hồ sơ mới” để ghi giá trị mặc định đè lên dữ liệu cũ. Nếu người dùng muốn sửa hồ sơ, thực hiện thao tác riêng với xác thực và quyền phù hợp.

Nếu avatar hoặc ngôn ngữ chưa hiển thị ngay do cache hay dịch vụ phụ trợ chậm, cần phân biệt lỗi hiển thị với mất dữ liệu. Không vội tạo hồ sơ trắng để che một lỗi đọc tạm thời.

## 7. Ví dụ cập nhật có mục tiêu trong Java và SQL

Ví dụ dưới minh họa một thao tác chỉ thay password verifier và phiên bản xác thực. Nó sử dụng JDBC để thấy rõ các cột được ghi. Không có trường hồ sơ trong danh sách cập nhật.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

record AccountKey(UUID tenantId, UUID accountId) {
}

final class AuthenticationWriter {
    static int replacePassword(
            Connection transactionConnection,
            AccountKey target,
            long expectedAuthenticationVersion,
            String encodedPassword) throws SQLException {

        String sql = """
                UPDATE account_authentication
                   SET password_verifier = ?,
                       authentication_version = authentication_version + 1,
                       session_epoch = session_epoch + 1
                 WHERE tenant_id = ?
                   AND account_id = ?
                   AND authentication_version = ?
                """;

        try (PreparedStatement statement =
                     transactionConnection.prepareStatement(sql)) {
            statement.setString(1, encodedPassword);
            statement.setObject(2, target.tenantId());
            statement.setObject(3, target.accountId());
            statement.setLong(4, expectedAuthenticationVersion);
            return statement.executeUpdate();
        }
    }
}
```

Tên bảng, kiểu UUID và cách binding ở ví dụ cần phù hợp với cơ sở dữ liệu cùng driver của triển khai. Cần ràng buộc duy nhất cho cặp tenant/account tương ứng và các điều kiện dữ liệu đầu vào cần thiết. `encodedPassword` là verifier được máy chủ tạo bằng cơ chế lưu mật khẩu của hệ thống, không phải giá trị tùy ý client tự gửi để thay hash.

Phương thức không tự xác minh token, không tự quản lý giao dịch và không đại diện cho endpoint khôi phục đầy đủ. Nó được gọi trong luồng đã kiểm tra quyền, dùng cùng kết nối giao dịch với việc tiêu thụ quyền khôi phục và ghi sự kiện cần thiết. Luồng gọi phải yêu cầu đúng một hàng được cập nhật; không có hàng nào là xung đột hoặc sai điều kiện, không phải thành công.

Một luồng giao dịch khái niệm:

```text
BEGIN
  nạp và khóa quyền khôi phục cùng trạng thái cần kiểm tra
  xác minh account, tenant, phạm vi, thời hạn và trạng thái dùng một lần
  kiểm tra lại điều kiện bảo mật hiện tại
  cập nhật có mục tiêu các trường xác thực; yêu cầu row_count = 1
  đánh dấu quyền khôi phục đã tiêu thụ
  ghi sự kiện cùng outbox nếu kiến trúc sử dụng
COMMIT
```

Việc dùng một giao dịch yêu cầu các kho dữ liệu và thao tác thực sự tham gia cùng ranh giới giao dịch; không chỉ đặt chúng gần nhau trong code. Các đường thu hồi quyền hoặc thay đổi cạnh tranh cũng phải tuân thủ cơ chế khóa hay kiểm tra phiên bản thích hợp.

`session_epoch` chỉ có tác dụng nếu các thành phần chấp nhận phiên hoặc token thực sự kiểm tra nó theo kiến trúc. Tăng một cột trong cơ sở dữ liệu không tự làm mọi access token đã phát hành mất hiệu lực ở các dịch vụ chỉ kiểm tra chữ ký và hạn dùng.

Điểm chính của ví dụ là phạm vi ghi rõ ràng: không `UPDATE display_name`, không ghi lại avatar, không thay email và không tạo account ID mới. Đây là một cách giữ nguyên hồ sơ ngay từ thiết kế thao tác thay vì trông cậy vào việc sao lưu rồi sửa lại sau.

## 8. Bảo toàn hồ sơ không có nghĩa giữ lại mọi trạng thái bảo mật cũ

Cần phân biệt dữ liệu nên giữ với dữ liệu phải thay hoặc vô hiệu hóa. Nếu người dùng báo điện thoại bị mất, việc giữ nguyên MFA trên thiết bị đó chỉ để “không mất dữ liệu” có thể duy trì đường truy cập nguy hiểm.

Các loại thay đổi phải tuân theo kế hoạch khôi phục:

- Mật khẩu cũ được thay khi yêu cầu cho phép đặt lại mật khẩu.
- Yếu tố xác thực bị mất hoặc bị nghi chiếm được thu hồi theo policy.
- Phiên và token cũ được xử lý theo phạm vi sự cố.
- Kênh khôi phục bị nghi chiếm không được tự giữ lại như một kênh đáng tin cậy.
- Quyền và trạng thái khóa không được phục hồi từ snapshot chỉ vì chúng từng tồn tại.

Nếu hồ sơ chứa một email đang có trạng thái chưa xác minh, không nâng nó lên đã xác minh chỉ vì khôi phục hoàn tất. Nếu cần đổi email, thao tác đó phải có quyền, bằng chứng, thông báo và đánh giá rủi ro phù hợp. Không chuyển `pendingEmail` thành email chính bằng một hàm lưu hồ sơ chung.

Một tên hiển thị hoặc avatar bị kẻ tấn công sửa cũng không nhất thiết là giá trị nên giữ mãi. Tuy nhiên, việc khôi phục quyền truy cập và việc sửa dữ liệu bị phá hoại là hai quyết định riêng. Nếu có bằng chứng cần sửa hồ sơ, dùng một kế hoạch sửa được cho phép, xác định trường, nguồn dữ liệu đáng tin cậy và ảnh hưởng; không hoàn nguyên toàn bộ tài khoản theo cảm tính.

## 9. Cache, sự kiện và dữ liệu ở dịch vụ khác

Hồ sơ thường xuất hiện ở nhiều nơi: cơ sở dữ liệu chính, cache, chỉ mục tìm kiếm, dịch vụ avatar và bản chiếu đọc. Bảo toàn cần giữ đúng nguồn chuẩn và tránh để sự kiện khôi phục làm hỏng các bản chiếu đó.

Ví dụ lỗi là phát một sự kiện chung chứa `profile: null`, rồi consumer hiểu null là lệnh xóa hồ sơ. Một lỗi khác là gửi snapshot user cũ trong sự kiện đặt lại mật khẩu và consumer ghi đè hồ sơ hiện hành.

Nên dùng sự kiện có ý nghĩa rõ ràng:

```text
AuthenticationRecovered
  event_id
  account_id
  tenant_id
  authentication_version
  recovery_request_id
  occurred_at
```

Sự kiện này thông báo thay đổi xác thực; nó không phải một bản cập nhật hồ sơ. Consumer cần có contract cụ thể về trường nào được phép thay đổi. Không diễn giải trường không có mặt thành lệnh đặt giá trị rỗng.

Nếu cần cập nhật hoặc vô hiệu hóa cache xác thực, chỉ xử lý đúng khóa và phạm vi. Cache hồ sơ có thể không cần thay nếu hồ sơ không đổi. Nếu ứng dụng phải nạp lại hồ sơ sau đăng nhập mới, dùng account ID ổn định và nguồn dữ liệu hiện hành.

Sự kiện có thể đến trùng hoặc sai thứ tự. Các consumer phải chống áp dụng lặp và không dùng sự kiện cũ để đưa phiên bản mới về trạng thái cũ. Phiên bản xác thực và phiên bản hồ sơ có ý nghĩa riêng; một số tăng của xác thực không tự cho phép sửa hồ sơ.

Nếu avatar hoặc tệp hồ sơ được lưu bên ngoài cơ sở dữ liệu, khôi phục không nên thay khóa đối tượng hoặc di chuyển thư mục chỉ vì mật khẩu thay đổi. Giữ tham chiếu và quyền truy cập phù hợp. Link tạm thời hết hạn có thể được cấp lại sau khi xác thực; không cần sao chép lại tệp hoặc biến tệp riêng tư thành công khai để hiển thị nhanh.

Trong hệ thống nhiều dịch vụ, một bước hậu xử lý lỗi cần được theo dõi bằng execution ID và trạng thái từng phần. Gửi lại sự kiện phải tiếp tục tác vụ đúng phạm vi, không tạo lại hồ sơ hoặc tự đổi chủ tài nguyên.

## 10. Dữ liệu mã hóa và giới hạn có thật của khôi phục

Việc giữ được các hàng hồ sơ chưa chắc đủ để người dùng đọc lại dữ liệu nếu khóa giải mã phụ thuộc trực tiếp vào bí mật đã mất.

Nếu hệ thống chỉ mã hóa dữ liệu bằng một khóa dẫn xuất từ mật khẩu cũ và không có bất kỳ cơ chế khôi phục khóa hợp lệ nào khác, đặt mật khẩu mới không tự tạo lại khóa cũ. Không nên hứa rằng dữ liệu chắc chắn truy cập lại được trong kiến trúc đó.

Đối với dữ liệu cần khôi phục sau khi mất mật khẩu, kiến trúc quản lý khóa phải được thiết kế trước theo mô hình bảo mật của sản phẩm. Có thể có khóa dữ liệu riêng và cơ chế bọc khóa hoặc khôi phục khóa được kiểm soát. Không đồng nhất khóa mã hóa dữ liệu với password verifier dùng để xác thực.

Việc dùng một hệ thống quản lý khóa cũng không tự giải quyết quyền giải mã. Cần xác định ai được mở khóa, ở bước nào của quy trình, với phạm vi nào và cách ngăn người chỉ có token khôi phục hạn chế đọc dữ liệu ngoài quyền được cấp.

Không ghi khóa, dữ liệu giải mã thô hoặc bí mật phục hồi vào log để chứng minh rằng dữ liệu vẫn còn. Nếu có thao tác bọc lại khóa, ghi trạng thái và tham chiếu an toàn; không sao chép bí mật vào ticket hỗ trợ.

Nếu nghi khóa cũ đã bị lộ, kế hoạch ứng phó cần xem xét riêng việc thay khóa và ảnh hưởng đến dữ liệu. Không phục hồi một khóa đã bị thu hồi chỉ để làm thao tác đăng nhập mới trông như thành công.

## 11. Snapshot, backup và vòng đời dữ liệu

Backup hỗ trợ phục hồi sự cố lưu trữ, nhưng không nên là công cụ mặc định cho mọi yêu cầu quên mật khẩu. Phục hồi toàn bộ user từ backup có thể làm sống lại email cũ, quyền đã bị thu hồi, thông tin liên lạc không còn đáng tin cậy hoặc dữ liệu người dùng đã xóa hợp lệ.

Nếu một sự cố đã thực sự làm hỏng hồ sơ, quy trình phục hồi dữ liệu cần xác định:

- Những trường hoặc đối tượng bị ảnh hưởng.
- Điểm dữ liệu đáng tin cậy để phục hồi.
- Các thay đổi hợp lệ sau thời điểm backup cần giữ.
- Trạng thái xóa, hạn chế xử lý và quyền hiện hành.
- Những người có thẩm quyền phê duyệt việc sửa.
- Cách ghi nhận và đối soát kết quả theo phạm vi.

Không khôi phục toàn bộ cơ sở dữ liệu về thời điểm trước khi người dùng mất mật khẩu. Điều đó có thể xóa các thay đổi hợp lệ của nhiều tài khoản khác và vượt xa phạm vi khôi phục truy cập.

Tương tự, không tự bỏ trạng thái tài khoản đang chờ xóa hoặc đã bị hạn chế theo một quy trình hợp lệ. Khả năng chứng minh quyền với tài khoản không đồng nghĩa có quyền đảo ngược mọi quyết định về vòng đời dữ liệu. Nếu có quy trình hủy yêu cầu xóa hoặc phục hồi tài khoản đã đóng, thực hiện theo contract riêng.

Chỉ lưu snapshot bổ sung khi có mục đích và policy rõ ràng. Snapshot toàn bộ hồ sơ làm tăng số bản sao dữ liệu cá nhân, chi phí bảo vệ và nghĩa vụ quản lý vòng đời. Nhiều trường hợp chỉ cần account ID, phiên bản, hành động được phép và các tham chiếu xác minh phù hợp.

Không coi một hash của hồ sơ là bằng chứng đầy đủ rằng mọi dữ liệu và quyền đã được giữ đúng. Hash còn có thể tạo rủi ro nếu dùng để đối chiếu dữ liệu ít khả năng hoặc được công bố không đúng phạm vi. Kiểm tra bảo toàn cần hiểu trường, phiên bản và thay đổi nào được phép, không chỉ so sánh một chuỗi.

## 12. Nhật ký và thông báo mà không làm lộ hồ sơ

Nhật ký nên giải thích được hành động đã thay đổi gì và vì sao có quyền thay đổi, nhưng không cần sao chép toàn bộ hồ sơ trước và sau cho mọi lượt khôi phục.

Một sự kiện audit có thể gồm:

```text
recovery_request_id, execution_id
account_id, tenant_id
authorized_action, policy_reference
authentication_version_before, authentication_version_after
outcome, occurred_at, actor_reference
session_action_result, follow_up_reference
```

Nếu một thao tác sửa hồ sơ riêng được cho phép, cần ghi phạm vi sửa và nguồn quyết định thích hợp. Không đưa mật khẩu, token dùng một lần, mã MFA, cookie hoặc giấy tờ thô vào log vận hành.

Thông báo cho người dùng có thể nêu rằng khả năng đăng nhập đã được khôi phục và hướng dẫn xem trạng thái trong ứng dụng chính thức. Nếu quy trình không sửa hồ sơ, có thể diễn đạt rõ phạm vi thao tác; không khẳng định dữ liệu mã hóa chắc chắn đọc được nếu hệ thống chưa xác lập được khả năng đó.

Nếu phát hiện hồ sơ không khớp account ID, bị mất liên kết hoặc xuất hiện thay đổi ngoài phạm vi, cần xử lý như một sự cố dữ liệu hoặc quyền truy cập. Không tự động điền hồ sơ mặc định và đóng yêu cầu thành công. Trạng thái khôi phục xác thực và trạng thái sự cố dữ liệu có thể phải được theo dõi riêng.

## 13. Tình huống xuyên suốt

Mai có tài khoản A17, dùng ngôn ngữ tiếng Việt và avatar đã tải lên. Mai mất điện thoại chứa MFA nhưng còn một phiên hợp lệ trên máy tính. Mai bắt đầu quy trình khôi phục trên một thiết bị khác.

Hệ thống xác minh danh tính, đánh giá rủi ro và tạo quyền khôi phục chỉ cho phép xử lý yếu tố bị mất cùng đăng ký yếu tố thay thế. Quyền đó gắn với A17 và tenant đúng phạm vi; nó không cho phép đổi email hoặc sửa hồ sơ.

Trong lúc chờ, Mai đổi ngôn ngữ sang tiếng Anh trên máy tính. Một bản ghi khôi phục cũ vẫn có thể phản ánh rằng trước đó Mai dùng tiếng Việt, nhưng giá trị này không được dùng để ghi lại hồ sơ khi hoàn tất.

Khi quyền khôi phục được sử dụng, máy chủ kiểm tra lại điều kiện hiện tại và thay đổi đúng dữ liệu xác thực theo kế hoạch. Account ID vẫn là A17. Hồ sơ hiện hành giữ ngôn ngữ tiếng Anh, avatar và các liên kết dữ liệu nghiệp vụ. Các phiên cũ được xử lý theo policy; việc giữ hồ sơ không yêu cầu giữ phiên có thể không còn an toàn.

Giả sử cache avatar chưa phản hồi ngay sau khi Mai đăng nhập lại. Ứng dụng hiển thị trạng thái tạm thời thích hợp và nạp lại từ nguồn chuẩn. Nó không xóa tham chiếu avatar hoặc tạo một hồ sơ rỗng để thay thế.

Nếu email trong hồ sơ đang có một thay đổi chờ xác minh, thao tác khôi phục không tự phê duyệt email đó. Nếu Mai muốn đổi kênh khôi phục, hệ thống yêu cầu luồng riêng với bằng chứng và quyền tương ứng.

Trong trường hợp khác, nếu dữ liệu riêng của Mai được mã hóa chỉ bằng bí mật cũ đã mất mà không có cơ chế khôi phục khóa, hệ thống cần trình bày đúng giới hạn. Khôi phục đăng nhập không đồng nghĩa đã phục hồi được khóa giải mã.

Bảo toàn hồ sơ bắt đầu từ việc xác định đúng tài khoản và thu hẹp phạm vi ghi. Khi thao tác khôi phục chỉ thay những trường được cho phép, tôn trọng dữ liệu hiện hành và không mở rộng quyền truy cập, người dùng có thể lấy lại khả năng đăng nhập mà không đánh đổi tính toàn vẹn của hồ sơ.
