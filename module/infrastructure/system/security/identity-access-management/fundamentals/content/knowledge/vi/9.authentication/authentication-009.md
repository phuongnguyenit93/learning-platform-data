# Account lockout

## 1. Account lockout giải quyết vấn đề gì?

Account lockout là cơ chế tạm dừng hoặc ngăn một đường xác thực sau những sự kiện như nhiều lần thử sai. Mục tiêu thường là giảm khả năng đoán bí mật trực tuyến. Tuy nhiên, nếu bất kỳ ai chỉ cần biết username cũng khóa được tài khoản đó vô thời hạn, cơ chế bảo vệ lại trở thành cách gây từ chối dịch vụ cho người dùng hợp lệ.

Ví dụ, ứng dụng có thể tạm chặn đăng nhập bằng mật khẩu sau một nhóm lần sai trong thời gian ngắn. Người dùng cần chờ, sử dụng một phương thức khác được chấp nhận hoặc hoàn tất recovery theo chính sách. Điều đó khác với việc tổ chức vô hiệu hóa tài khoản vì nhân viên đã nghỉ việc.

Một thiết kế tốt cần trả lời được: đang chặn tài khoản hay authenticator nào, đếm những lần nào, trong khoảng nào, chặn bao lâu, ai được mở và khi nào bộ đếm được đặt lại.

## 2. Phân biệt các lớp kiểm soát

| Cơ chế | Đối tượng tác động | Ý nghĩa |
|---|---|---|
| Request rate limiting | Nguồn truy cập, client, endpoint, tập lưu lượng | Giới hạn số request được tiếp nhận |
| Login throttling | Các lần thử xác thực | Làm chậm hoặc giảm số lần kiểm tra bí mật |
| Temporary lockout | Một đường xác thực hoặc tài khoản theo policy | Chặn thử tiếp trong thời gian nhất định |
| Authenticator disabled | Một authenticator hoặc tập authenticator | Không được dùng lại trước khi đáp ứng quy trình phục hồi cần thiết |
| Administrative disable | Trạng thái quản trị của tài khoản | Tài khoản không được hoạt động dù bí mật đúng |
| Incident containment | Danh tính, credential, phiên hoặc hệ thống liên quan | Chặn truy cập khi có nghi ngờ/hiện tượng bị chiếm |

Các lớp có thể phối hợp, nhưng không nên dùng chung một cờ `locked=true` cho tất cả. Nếu chỉ có một cờ, thao tác “mở khóa sau thử sai” có thể vô tình bật lại tài khoản đã bị offboard.

Tương tự, khóa đăng nhập mới không tự hủy các phiên đang có. Muốn kết thúc phiên hoặc thu hồi token phải có cơ chế và chính sách tương ứng, không suy ra từ trạng thái bộ đếm password.

## 3. Ba tham số cơ bản và phạm vi áp dụng

OWASP nêu ba quyết định quan trọng khi thiết kế lockout: ngưỡng số lần sai, cửa sổ quan sát và thời gian khóa. Bộ đếm cần gắn với tài khoản, không chỉ IP, để tránh việc đổi nguồn truy cập làm mất dấu các lần thử. [OWASP Authentication — Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#account-lockout)

### 3.1. Ngưỡng thử sai

Cần quy định chính xác hành vi tại biên. Với ngưỡng 5 trong một policy mẫu, lần sai thứ năm được ghi nhận rồi kích hoạt cooldown; request tiếp theo không tiếp tục được kiểm tra mật khẩu trong thời gian đó.

Không dùng các câu mơ hồ như “cho phép 5 lần” mà không biết lần thứ năm hay thứ sáu sẽ bị chặn. Khi có request đồng thời, còn phải quy định số lượt đang xác minh được tính vào khả năng tiếp nhận thế nào.

### 3.2. Cửa sổ quan sát

Một cửa sổ cố định chia thời gian thành các đoạn; cửa sổ trượt xét các sự kiện gần thời điểm hiện tại. Hai cơ chế có hành vi khác nhau ở ranh giới phút.

Ví dụ, người dùng nhập sai ba lần ngay trước ranh giới cửa sổ cố định và ba lần ngay sau đó có thể không đạt ngưỡng 5 trong bất kỳ đoạn nào. Một cửa sổ trượt 10 phút có thể ghi nhận đủ sáu lần gần nhau. Chọn mô hình nào cần được ghi rõ để lập trình và kiểm thử nhất quán.

### 3.3. Thời gian khóa

Thời gian có thể cố định hoặc tăng dần khi sự kiện lặp lại. Nếu dùng backoff tăng dần, phải có giới hạn và điều kiện giảm/reset. Không để mỗi request bị chặn lại kéo thời điểm hết khóa ra xa hơn mà không có chủ đích; cách đó cho phép kẻ tấn công giữ người dùng trong trạng thái khóa bằng lưu lượng rẻ.

### 3.4. Khóa tài khoản hay khóa phương thức?

Nếu chỉ mật khẩu bị nhắm tới, sản phẩm có thể chọn chặn đường password nhưng vẫn cho phép một phương thức độc lập đáp ứng policy. Đây không phải “cho đi vòng” nếu phương thức đó thực sự đã được đăng ký và được chấp nhận cho mức xác thực yêu cầu.

Ngược lại, không được dùng một phương thức yếu hơn để bỏ qua kiểm soát của một tài khoản đặc quyền. Phải phân biệt phương thức đăng nhập thay thế được phép với recovery hoặc ngoại lệ cần phê duyệt.

## 4. Hiểu đúng giới hạn thử sai của NIST

NIST SP 800-63B-4 quy định giới hạn thử sai liên tiếp đối với authenticator cụ thể trên tài khoản khi yêu cầu chống đoán trực tuyến áp dụng. Giới hạn chung không quá 100 là trần, có ngoại lệ theo loại authenticator; không phải khuyến nghị mọi sản phẩm nên cho đúng 100 lần sai. Khi chạm giới hạn vô hiệu hóa, authenticator cần được gắn lại theo quy trình để dùng về sau. [NIST SP 800-63B-4 — Rate Limiting](https://pages.nist.gov/800-63-4/sp800-63b.html#rate-limiting)

Một cooldown 60 giây và việc vô hiệu hóa authenticator tại giới hạn cuối cùng là hai tầng khác nhau. Nếu hết cooldown lại xóa toàn bộ lịch sử liên tiếp, hệ thống có thể cho thử vô hạn qua nhiều chu kỳ mà chưa thực hiện ý nghĩa của tầng thứ hai.

Không đồng nhất giới hạn tại máy chủ với số lần nhập PIN sai để mở khóa cục bộ một authenticator. Chúng có vị trí thực thi, loại bí mật và yêu cầu riêng.

Bài học sử dụng một policy mẫu để giải thích thiết kế, không tuyên bố chỉ cần áp dụng các con số trong ví dụ là đã đáp ứng toàn bộ hướng dẫn NIST hoặc mọi yêu cầu của một tổ chức.

## 5. Một policy minh họa có hai tầng bộ đếm

Ứng dụng Expense sử dụng mật khẩu và MFA. Nhóm chọn policy sau cho đường xác minh mật khẩu:

| Thành phần | Quyết định của ví dụ |
|---|---|
| Phạm vi | Đúng account và password authenticator trong một identity realm |
| Ngưỡng ngắn hạn | 5 lần xác minh mật khẩu sai trong cửa sổ trượt 10 phút |
| Cooldown lần đầu | 60 giây |
| Cooldown lặp trong 60 phút | Lần tiếp theo 5 phút, sau đó tối đa 15 phút |
| Khi hết cooldown | Mở lại khả năng thử theo policy, bắt đầu nhóm ngắn hạn mới |
| Bộ đếm liên tiếp | Không tự xóa khi cooldown kết thúc |
| Giới hạn liên tiếp mẫu | 20 lần sai thì vô hiệu hóa password authenticator, yêu cầu recovery/thiết lập lại hợp lệ |
| Request đã bị chặn | Không tính như một lần xác minh mật khẩu sai mới và không kéo dài cooldown hiện tại |
| Thành công hợp lệ | Reset bộ đếm liên quan theo quy tắc đã xác định, không bật lại trạng thái quản trị |

Mọi con số là lựa chọn phục vụ ví dụ. Cần điều chỉnh theo loại người dùng, authenticator, nguy cơ và vận hành thực tế.

Tầng ngắn hạn hạn chế nhịp đoán. Tầng liên tiếp giữ giới hạn tổng thể khi chưa có thành công đủ điều kiện hoặc phục hồi hợp lệ. Khi đạt ngưỡng cuối cùng, không dùng một timer thông thường để tự đưa authenticator trở lại hoạt động.

“Bắt đầu nhóm ngắn hạn mới” ở ví dụ nghĩa là xóa các lần sai của nhóm đã gây cooldown sau khi cooldown kết thúc. Nó không xóa `consecutiveFailures`. Các sự kiện lockout trong 60 phút dùng để chọn backoff cũng được quản lý riêng.

### 5.1. Timeline minh họa

```text
09:00:00  Password sai lần 1
09:00:10  Password sai lần 2
09:00:20  Password sai lần 3
09:00:30  Password sai lần 4
09:00:40  Password sai lần 5 -> cooldown đến 09:01:40
09:01:00  Request tới -> bị chặn, không kiểm tra password
09:01:40  Có thể tiếp nhận lại theo policy
           Bộ đếm ngắn hạn bắt đầu nhóm mới
           consecutiveFailures vẫn là 5
```

Nếu người dùng tiếp tục sai, cooldown sau có thể dài hơn. Nếu lần sai thứ 20 đạt giới hạn liên tiếp, trạng thái chuyển sang yêu cầu phục hồi; hết 15 phút không tự mở nó.

### 5.2. Không đếm lẫn lỗi của các yếu tố

Password sai và OTP sai thuộc các phép xác minh khác nhau. Khi password đúng nhưng OTP sai, phải ghi nhận đúng yếu tố thất bại, không cộng bừa vào cả hai.

Ngược lại, cũng không đặt lại bộ đếm OTP chỉ vì request vừa vượt qua password. Nếu làm vậy, một người đã biết password có thể thử OTP nhiều lần bằng cách khởi động lại luồng.

Trong policy mẫu, việc reset bộ đếm sau đăng nhập được thực hiện khi luồng yêu cầu đã hoàn tất, theo các authenticator thực sự được dùng và điều kiện bảo đảm của policy. Không dùng một request bất kỳ trong phiên cũ làm “đăng nhập thành công” để reset mọi bộ đếm.

## 6. Khóa chính xác đối tượng và các đường đăng nhập

### 6.1. Gắn bộ đếm với danh tính chuẩn

Username, email và bí danh có thể cùng trỏ tới một tài khoản. Sau khi phân giải định danh hợp lệ, các đường đó cần áp dụng cùng policy cho cùng authenticator. Nếu bộ đếm chỉ dùng chuỗi client nhập, kẻ tấn công có thể thay bí danh hoặc cách viết để tạo nhiều ngân sách thử sai.

Một khóa nội bộ có thể gồm:

```text
identityRealm + accountId + authenticatorRecordId
```

Cách chuẩn hóa định danh phải theo quy tắc của hệ thống. Không tự lowercase mọi định danh hoặc dùng email toàn cục để gộp tài khoản thuộc các realm khác nhau.

Đối với username không tồn tại, vẫn cần kiểm soát lạm dụng đầu vào và tránh phân biệt tài khoản qua phản hồi. Không tạo một bản ghi tài khoản thật cho mỗi chuỗi giả, cũng không cho phép số lượng khóa limiter tăng vô hạn mà không có cơ chế quản lý tài nguyên.

### 6.2. Bao phủ mọi endpoint thực sự xác minh bí mật

Giao diện web, ứng dụng di động, endpoint cũ và bước reauthentication có thể cùng xác minh một password. Nếu một đường không tham gia bộ đếm chung, nó có thể trở thành đường thử thay thế.

Cần lập bảng ánh xạ endpoint tới verifier và khóa trạng thái. Có thể có rate limit riêng cho từng endpoint, nhưng việc chia endpoint không nên vô tình tạo thêm ngân sách đoán cùng một bí mật.

Với SSO, xác minh có thể nằm ở IdP thay vì ứng dụng. Ứng dụng không thể biết một password sai tại IdP nếu giao thức không cung cấp sự kiện phù hợp. Cần xác định thành phần sở hữu lockout và những đường local login còn tồn tại, thay vì tạo hai bộ đếm không phản ánh cùng luồng.

### 6.3. Không chỉ dựa vào IP

Nhiều người có thể dùng chung IP do NAT; một người dùng di động có thể đổi IP; kẻ tấn công có thể dùng nhiều nguồn. Vì vậy, giới hạn theo nguồn cần phối hợp với trạng thái theo danh tính và tín hiệu tổng thể.

Không tin trực tiếp header như `X-Forwarded-For` từ mọi client. Nếu hạ tầng dùng proxy, chỉ lấy thông tin nguồn theo cấu hình chuỗi proxy đáng tin cậy. Sai nguồn truy cập làm limiter và bằng chứng điều tra mất ý nghĩa.

## 7. Quản lý trạng thái và tính đồng thời

### 7.1. Trạng thái cần đủ tách biệt

Ví dụ bản ghi điều khiển thử sai:

```yaml
identityRealm: workforce-example
accountId: account-0042
authenticatorRecordId: password-17
credentialVersion: 6
consecutiveFailures: 4
recentFailureTimes:
  - '2026-12-01T09:00:00+07:00'
  - '2026-12-01T09:00:10+07:00'
  - '2026-12-01T09:00:20+07:00'
  - '2026-12-01T09:00:30+07:00'
cooldownUntil: null
authenticatorStatus: ACTIVE
stateVersion: 21
```

Đây là schema khái niệm, không phải yêu cầu lưu mọi timestamp trong một YAML thực. Cấu trúc lưu cần có giới hạn kích thước, thao tác nguyên tử và chính sách thời gian phù hợp.

Trạng thái quản trị như `accountStatus=OFFBOARDED` thuộc đối tượng riêng. Một thao tác reset cooldown không được sửa nó.

### 7.2. Tránh kiểu đọc rồi ghi không nguyên tử

Giả sử hai node cùng đọc `failedCount=4`, cùng xác minh sai rồi cùng ghi `failedCount=5`. Hai phép thử thực tế chỉ được tính thành một. Nếu nhiều request đã vượt kiểm tra “chưa khóa” trước khi bộ đếm tăng, số lần đoán còn có thể vượt ngưỡng.

Không chỉ cần tăng nguyên tử; cần điều phối việc tiếp nhận và hoàn tất attempt. Một lựa chọn đơn giản cho ví dụ là tối đa một phép xác minh password đang xử lý cho một authenticator tại một thời điểm. Những request khác bị trì hoãn hoặc từ chối theo policy, không giữ kết nối vô hạn.

Không nên giữ một transaction database dài chỉ để chờ hàm password hashing tốn tài nguyên. Có thể dùng permit/reservation ngắn hạn và bước commit kết quả nguyên tử, có phiên bản và cách xử lý worker lỗi.

Luồng khái niệm:

```java
LoginResult tryPassword(LoginContext context, char[] candidate) {
    enforceRequestLimits(context);
    AccountRef account = resolveAccountWithinRealm(context);

    AttemptPermit permit = attempts.admitAndReserve(account, context);
    if (!permit.admitted()) {
        return genericRejectedResponse(permit.publicRetryPolicy());
    }

    VerificationResult result = passwordVerifier.verify(
        account, candidate, permit.credentialVersion());

    AttemptDecision decision = attempts.commitVerification(
        permit, result, context);

    if (!decision.mayContinueAuthentication()) {
        return genericRejectedResponse(decision.publicRetryPolicy());
    }

    return continueRequiredAuthentication(account, context, decision);
}
```

Các kiểu và hàm là pseudocode thiết kế, không phải implementation hoàn chỉnh. `admitAndReserve` phải xét cooldown, trạng thái authenticator, account, ngân sách và số lượt đang chạy bằng cơ chế phối hợp phù hợp.

`commitVerification` cần xác nhận permit còn hiệu lực, đúng credential/state version và không bị xử lý lặp. Nếu mật khẩu đã reset, tài khoản đã offboard hoặc policy đã chuyển trạng thái trong khi hash đang tính, kết quả cũ không được tự cấp quyền tiếp tục.

Một verifier timeout không đồng nghĩa mật khẩu sai. Attempt chưa biết kết quả cần được reconcile hoặc xử lý theo chính sách rõ ràng; không giải phóng ngân sách vô điều kiện rồi tiếp tục cho xác minh vô hạn. Đồng thời không ghi người dùng nhập sai chỉ vì hạ tầng gặp lỗi.

### 7.3. Nhiều node cần cùng nhìn một trạng thái hiệu lực

Bộ đếm trong RAM từng instance cho phép việc chuyển node hoặc restart làm thay đổi ngân sách. Trạng thái authoritative cần có khả năng phối hợp phù hợp giữa các node, bao gồm tính nhất quán và hành vi khi failover.

TTL có thể hữu ích cho bucket ngắn hạn, nhưng không được làm biến mất trạng thái vô hiệu hóa authenticator hoặc bộ đếm liên tiếp đang cần giữ. Snapshot cũ và replica trễ cũng không được dùng để cấp lại khả năng xác minh khi node khác đã ghi khóa.

Nếu kho điều khiển thử sai bị lỗi, không mặc định bỏ qua mọi kiểm soát. Định nghĩa trước phương án từ chối tạm thời hoặc chế độ suy giảm có giới hạn được đánh giá phù hợp; ghi nhận tác động vận hành và cảnh báo.

## 8. Giảm nguy cơ kẻ tấn công khóa người dùng hợp lệ

Lockout phải cân bằng chống đoán và khả năng sử dụng. OWASP WSTG đặt cả hai mục tiêu trong việc đánh giá cơ chế khóa tài khoản. [OWASP WSTG — Weak Lock Out Mechanism](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/04-Authentication/03-Weak_Lock_Out_Mechanism/)

Một số quyết định thiết kế có ích:

- Chặn hoặc làm chậm nguồn lạm dụng trước khi nó liên tục tiêu thụ ngân sách của nhiều tài khoản.
- Dùng cooldown có giới hạn, không kéo dài chỉ vì request đã bị chặn.
- Có phương thức xác thực thay thế hoặc recovery phù hợp cho chủ tài khoản.
- Phát hiện việc nhiều tài khoản bị thử cùng mẫu để xử lý spraying, không chỉ từng người riêng lẻ.
- Hạn chế luồng thông báo và yêu cầu hỗ trợ bị spam theo mỗi lần sai.

Chúng làm giảm nguy cơ nhưng không loại bỏ hoàn toàn việc kẻ tấn công gây lockout. Nếu hệ thống cho phép thử công khai một username đã biết, cần đánh giá cả kịch bản kẻ xấu chỉ muốn tiêu thụ ngân sách chứ không muốn đoán đúng.

CAPTCHA hoặc tín hiệu thiết bị có thể là một lớp bổ sung, không phải bằng chứng danh tính thay cho MFA. Một thiết bị được nhận diện trước cũng không phải lý do xóa bộ đếm toàn cục một cách không giới hạn.

Đối với tài khoản quản trị, tránh cả hai cực đoan: không có kiểm soát thử sai, hoặc khóa duy nhất đường vận hành mà không có recovery. Nếu có tài khoản khẩn cấp, cần cơ chế bảo vệ, giám sát và kiểm thử riêng, không phải một cờ bỏ qua mọi kiểm soát.

## 9. Mở khóa và account recovery

### 9.1. Hết cooldown

Trong ví dụ, khi hết `cooldownUntil`, hệ thống có thể tiếp nhận lại attempt theo policy và làm mới nhóm ngắn hạn. Nó không tự đổi `authenticatorStatus=DISABLED` về active, cũng không bật lại tài khoản bị vô hiệu hóa quản trị.

Giao diện cần hỗ trợ người dùng biết cách tiếp tục mà không công khai quá nhiều trạng thái tài khoản cho một người chưa xác thực. Thông tin chi tiết có thể được cung cấp trong kênh hoặc ngữ cảnh đã xác nhận quyền kiểm soát.

### 9.2. Tự phục vụ qua bằng chứng phù hợp

Người dùng có thể dùng phương thức khác hoặc quy trình recovery được chấp nhận. Bằng chứng cần gắn với đúng account, mục đích và thời hạn. Không chỉ cần biết username rồi gọi `POST /unlock` là xóa trạng thái.

Một yêu cầu “quên mật khẩu” chưa được xác minh không phải một lần nhập password sai và không được tự khóa tài khoản. OWASP cảnh báo việc khóa tài khoản theo lạm dụng forgot-password có thể bị dùng để gây từ chối dịch vụ. [OWASP Forgot Password — Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-lockout)

Reset thành công cần định nghĩa rõ thay đổi credential và trạng thái thử sai của credential liên quan. Nó không được bỏ qua việc tài khoản bị offboard, không tự reset mọi yếu tố MFA và không tự phục hồi tất cả các phiên.

### 9.3. Mở qua hỗ trợ hoặc quản trị

Người xử lý cần quyền phù hợp, xác thực mạnh theo policy, phạm vi quản trị đúng realm/tenant và hồ sơ lý do. Audit phải cho biết ai mở cho ai, đã xác minh gì và trạng thái nào được thay đổi.

Thao tác mở cooldown, thiết lập lại một authenticator và bật lại tài khoản là ba quyền khác nhau. Đừng tạo một nút “Unlock” thực hiện đồng thời cả ba mà không có phân biệt.

Nếu một tài khoản liên tục bị khóa vì ứng dụng cũ đang gửi mật khẩu sai trong nền, chỉ mở đi mở lại sẽ không sửa được nguyên nhân. Cần tìm client, credential cũ hoặc cấu hình automation gây ra lưu lượng đó.

## 10. Phản hồi, phiên và quan sát vận hành

### 10.1. Tránh lộ tài khoản qua trạng thái khóa

Thông báo “tài khoản tồn tại nhưng đã bị khóa đến 09:30” có thể tiết lộ danh tính hợp lệ. Đồng thời, thông báo quá mơ hồ trong mọi kênh có thể làm người dùng không biết cách phục hồi.

Thiết kế phản hồi theo mức tin cậy của ngữ cảnh. Ở endpoint công khai, tránh khác biệt đơn giản giữa username giả, password sai và cooldown. Xét cả HTTP status, thời gian, redirect và trường `Retry-After`; header này không nên vô tình trở thành API tra trạng thái tài khoản.

Có thể công bố thông tin chờ ở mức tổng quát phù hợp, còn chi tiết tài khoản và hướng dẫn riêng qua kênh đã được xác nhận. Không tuyên bố chỉ một câu lỗi chung là đã giải quyết mọi kênh account enumeration.

### 10.2. Không suy ra phiên hiện tại đã bị chiếm

Nhiều request password sai có thể do người ngoài cố khóa người dùng. Nếu mỗi lần như vậy lại đăng xuất mọi phiên hợp lệ, kẻ tấn công có thêm cách gây gián đoạn.

Policy có thể chọn giữ phiên đang có khi chỉ cooldown đường login, nhưng yêu cầu reauthentication cho thao tác nhạy cảm. Khi có bằng chứng chiếm tài khoản, incident policy có thể yêu cầu thu hồi phiên và credential. Hai quyết định cần có lý do và điểm thực thi riêng.

### 10.3. Ghi đúng sự kiện và đo cả tác dụng phụ

Theo dõi các nhóm riêng: request bị limiter chặn, phép xác minh sai, cooldown mới, authenticator bị vô hiệu hóa, mở qua recovery và lỗi hạ tầng. Không gộp tất cả thành “login failed”.

Chỉ số hữu ích gồm số tài khoản bị ảnh hưởng, thời gian người dùng hợp lệ bị chặn, số lần recovery, tỷ lệ false positive, mẫu nguồn truy cập và số lần chạm giới hạn cuối cùng. Giảm số lần login thành công của kẻ tấn công là mục tiêu, nhưng số người dùng hợp lệ phải gọi hỗ trợ cũng là một tín hiệu thiết kế.

Log nên chứa định danh nội bộ phù hợp, realm, authenticator reference, reason code, thời gian, policy version và correlation ID. Không ghi mật khẩu, OTP, reset token hoặc cookie phiên. Thông báo bảo mật cần gộp sự kiện và giới hạn tốc độ để không trở thành nguồn spam.

## 11. Thiết kế kiểm thử bằng thời gian có thể điều khiển

Dùng tài khoản lab và đồng hồ kiểm thử thay vì phải chờ thực nhiều phút. Với cơ chế phân tán, bổ sung các bài thử qua nhiều node và các tình huống lỗi kho trạng thái. Không chạy thử khóa tài khoản của người thật ngoài phạm vi được phép.

| ID | Tình huống | Kết quả cần chứng minh |
|---|---|---|
| LK-01 | Sai 4 lần trong cửa sổ, sau đó sai lần thứ 5 | Lần thứ 5 kích hoạt cooldown đúng ngưỡng |
| LK-02 | Gửi tiếp trong cooldown | Không xác minh password mới; không kéo dài hạn khóa |
| LK-03 | Tới đúng thời điểm hết cooldown | Có hành vi biên đã định nghĩa; không reset bộ đếm liên tiếp |
| LK-04 | Các lần sai nằm hai phía ranh giới phút | Phù hợp mô hình cửa sổ trượt đã chọn |
| LK-05 | Đổi IP nhưng vẫn cùng account | Không nhận một ngân sách password hoàn toàn mới |
| LK-06 | Đổi email/username alias của cùng account | Cùng policy và trạng thái thử sai |
| LK-07 | Cùng username ở hai realm khác nhau | Không khóa nhầm tài khoản thuộc realm khác |
| LK-08 | Request đồng thời tới nhiều node | Không mất phép đếm hoặc vượt ngân sách do race |
| LK-09 | Restart hoặc failover trong cooldown | Không tự bỏ trạng thái hiệu lực |
| LK-10 | Password đúng nhưng OTP sai nhiều lần | Không reset ngân sách OTP bằng việc khởi động lại password |
| LK-11 | Đạt giới hạn liên tiếp mẫu 20 lần | Password authenticator bị vô hiệu hóa; timer thường không mở lại |
| LK-12 | Account bị offboard khi verification đang chạy | Kết quả đến muộn không tạo phiên hoạt động |
| LK-13 | Credential reset đồng thời với kết quả password cũ | Không cấp quyền từ verifier/version cũ |
| LK-14 | Request malformed hoặc verifier timeout | Không ghi sai thành password mismatch; vẫn có chống lạm dụng |
| LK-15 | Chỉ gửi yêu cầu quên mật khẩu | Không tự khóa hoặc mở account |
| LK-16 | Mở cooldown cho account đã bị disable quản trị | Trạng thái disable quản trị được giữ nguyên |
| LK-17 | Đối chiếu username giả và account đang cooldown | Không có kênh phản hồi đơn giản làm lộ trạng thái |
| LK-18 | Kho trạng thái thử sai tạm lỗi | Thực hiện đúng chế độ lỗi đã công bố, có bằng chứng và cảnh báo |

Với mỗi ca, kiểm tra số lần verifier thực sự được gọi, trạng thái trước/sau, phiên có được tạo không và các sự kiện audit. Một HTTP lỗi không chứng minh request đã bị chặn trước khi kiểm tra bí mật; một trường `locked=true` cũng không chứng minh mọi endpoint đã thực thi nó.

Bảng là yêu cầu cho kiểm thử sản phẩm khi triển khai, không phải tuyên bố các phép thử đó đã được chạy trong bài Knowledge này.

## 12. Bài tập vận dụng

Hãy thiết kế lockout cho một dịch vụ có ba node, hỗ trợ password rồi TOTP và có thêm passkey làm phương thức đăng nhập khác. Quy định phạm vi bộ đếm, điều kiện reset, cooldown, giới hạn cuối cùng và đường recovery.

Mô tả cách xử lý hai request password đồng thời ở sát ngưỡng, một lần OTP sai sau password đúng và việc account bị offboard trong lúc verification chưa hoàn tất. Bổ sung kịch bản kẻ tấn công chỉ muốn khóa một tài khoản đã biết, cùng cách đo ảnh hưởng lên người dùng hợp lệ.

Thiết kế cần chứng minh được giới hạn số phép đoán, không để endpoint phụ hoặc node khác cấp thêm ngân sách, đồng thời không biến thao tác mở khóa kỹ thuật thành quyền bật lại danh tính đã bị vô hiệu hóa. Chính sách rõ ràng, trạng thái tách biệt và bằng chứng tại điểm xác minh là cơ sở để đánh giá cơ chế lockout.
