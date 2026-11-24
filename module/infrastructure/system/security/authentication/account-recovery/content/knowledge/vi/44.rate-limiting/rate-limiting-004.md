# Per device rate limit — Giới hạn tần suất theo thiết bị trong khôi phục tài khoản

Một trình duyệt có thể liên tục yêu cầu gửi email khôi phục cho nhiều tài khoản, thử nhiều mã hoặc tạo hàng loạt phiên khôi phục. Giới hạn theo tài khoản chỉ nhìn thấy từng tài khoản riêng lẻ; giới hạn theo IP có thể gom nhiều người dùng thật vào cùng một nhóm. Giới hạn theo thiết bị bổ sung một góc nhìn khác về nguồn tạo yêu cầu.

**Per device rate limit** là giới hạn số lượng hoặc tốc độ thực hiện một loại thao tác dựa trên định danh thiết bị mà hệ thống quan sát được. Trong ứng dụng web, định danh đó thường đại diện cho một hồ sơ trình duyệt hoặc một lần cài đặt, chứ không phải một máy vật lý được xác định chắc chắn.

Bài học áp dụng cơ chế này vào khôi phục mật khẩu, MFA, passkey và thiết bị xác thực. Các giá trị hạn mức, định dạng cookie và cấu trúc dữ liệu dưới đây là ví dụ thiết kế; chúng cần được điều chỉnh theo rủi ro và hành vi sử dụng của dịch vụ.

## 1. Xác định đúng đối tượng bị giới hạn

Một người có thể dùng nhiều thiết bị, một máy có nhiều hồ sơ trình duyệt và nhiều người có thể dùng chung một máy. Do đó:

```text
deviceId quan sát được
    ≠ một người dùng duy nhất
    ≠ một tài khoản
    ≠ một máy vật lý được chứng minh
```

Cơ chế giúp trả lời câu hỏi: “Nguồn đang mang định danh này đã dùng bao nhiêu ngân sách thao tác?”. Nó không tự trả lời: “Đây có phải chính chủ?” hoặc “Thiết bị này đáng tin đến mức nào?”.

| Tình huống | Kết quả quan sát có thể xảy ra |
| --- | --- |
| Hai tab cùng hồ sơ trình duyệt | Thường dùng chung cookie và hạn mức |
| Cùng máy mở cửa sổ riêng tư | Có thể xuất hiện như định danh mới |
| Người dùng xóa dữ liệu website | Định danh cũ có thể biến mất |
| Cookie bị sao chép sang client khác | Hai client có thể dùng cùng định danh |
| Nhiều người dùng chung máy tại quầy | Hạn mức có thể được dùng chung |
| Ứng dụng bị gỡ và cài lại | Định danh lần cài có thể thay đổi |

Nếu tài liệu vận hành gọi mọi định danh mới là “thiết bị mới”, đội hỗ trợ có thể suy luận sai về gian lận hoặc đánh giá quá cao độ chính xác của cơ chế.

## 2. Chọn thao tác và đơn vị ngân sách

Không nên áp dụng một con số duy nhất cho mọi endpoint khôi phục. Chi phí và hậu quả của từng bước khác nhau.

| Nhóm thao tác | Tài nguyên hoặc rủi ro cần kiểm soát | Đơn vị minh họa |
| --- | --- | --- |
| Bắt đầu yêu cầu khôi phục | Tạo hồ sơ và lạm dụng nhiều tài khoản | Yêu cầu được tiếp nhận |
| Gửi hoặc gửi lại thông điệp | Chi phí nhà cung cấp và làm phiền người nhận | Lần cho phép gửi |
| Kiểm tra OTP hoặc recovery code | Dò mã và tải xác minh | Lần thử xác minh |
| Đổi bằng chứng thành recovery session | Tạo quyền trung gian | Lần thử chuyển quyền |
| Hoàn tất thay credential | Tải xử lý và tác động nhạy cảm | Lần thử thao tác hoàn tất |
| Xem trang hướng dẫn | Tải phục vụ giao diện | Request phục vụ nội dung |

Hạn mức gửi SMS không thay thế ngân sách thử OTP. Hạn mức thử OTP theo thiết bị cũng không thay thế giới hạn theo challenge hoặc tài khoản: kẻ tấn công có thể đổi định danh để tiếp tục thử.

Cần nói rõ bộ đếm đếm request, operation hay tác động thực tế. Ví dụ:

- Hai request retry có thể cùng bị tính vào ngân sách lưu lượng.
- Chúng vẫn chỉ được tạo một lần gửi thông điệp nếu cùng operation idempotent.
- Một request bị từ chối trước khi gọi nhà cung cấp không được ghi nhận thành một SMS đã gửi.

Sự tách biệt này giúp tránh vừa tính sai chi phí vừa tạo thêm đường lạm dụng khi tự động hoàn lại ngân sách.

## 3. Chọn nguồn định danh

| Cách nhận diện | Lợi ích | Giới hạn |
| --- | --- | --- |
| Header device ID do client tự chọn | Dễ tích hợp | Dễ thay giá trị để có bucket mới |
| Cookie ngẫu nhiên do máy chủ phát hành | Ổn định tương đối trong một hồ sơ trình duyệt | Có thể bị xóa hoặc sao chép |
| Định danh lần cài ứng dụng | Hỗ trợ liên kết nhiều request của cùng lần cài | Cài lại hoặc thay đổi môi trường có thể tạo ID mới |
| Fingerprint trình duyệt | Bổ sung tín hiệu tương quan | Có sai số, thay đổi theo môi trường và ảnh hưởng quyền riêng tư |
| Bằng chứng thiết bị được xác thực trong một hệ sinh thái | Có thể tăng độ tin cậy trong phạm vi đã thiết kế | Không tự chứng minh chủ tài khoản hoặc bảo đảm một người một thiết bị |

Không dùng trực tiếp `X-Device-Id` tùy ý làm khóa rồi cấp toàn bộ ngân sách mỗi khi giá trị thay đổi.

Với web, một thiết kế tương đối đơn giản là máy chủ phát hành một mã ngẫu nhiên có thời hạn, kèm cơ chế kiểm tra nguồn phát hành. Khi không có bằng chứng đáng tin cậy về ID, request được xem là nguồn chưa được nhận diện thay vì được hưởng đặc quyền.

Fingerprint nên được coi là tín hiệu hỗ trợ. Không khóa tài khoản chỉ vì fingerprint thay đổi sau một bản cập nhật trình duyệt hoặc vì nhiều người có cấu hình giống nhau.

## 4. Cookie thiết bị do máy chủ phát hành

Một định dạng minh họa:

```text
version.randomDeviceId.expiresAt.authenticationTag
```

Trong đó:

- `randomDeviceId` được máy chủ sinh ngẫu nhiên với độ khó đoán phù hợp.
- `expiresAt` giới hạn thời gian chấp nhận định danh.
- `authenticationTag` là MAC trên các trường đã chuẩn hóa, dùng khóa phía máy chủ.
- `version` giúp diễn giải định dạng và quản lý thay đổi.

MAC giúp phát hiện việc sửa ID hoặc thời hạn. Nó không ngăn người gọi xóa cookie, xin ID mới hoặc sao chép cả cookie hợp lệ.

Ví dụ header, với giá trị cookie được viết tắt:

```http
Set-Cookie: __Host-recovery-device=v1.device-id.expiry.mac; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=86400
```

Thời hạn một ngày chỉ dùng minh họa. Máy chủ phải kiểm tra thời hạn trong giá trị đã xác thực; thuộc tính Max-Age ở trình duyệt không thay thế việc kiểm tra phía máy chủ.

Theo tài liệu Set-Cookie, tiền tố `__Host-` yêu cầu Secure, Path=/ và không có Domain trên trình duyệt hỗ trợ. HttpOnly hạn chế JavaScript đọc cookie; SameSite ảnh hưởng các tình huống gửi cookie qua ngữ cảnh khác site. Xem [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Các thuộc tính trình duyệt không áp dụng như một rào cản tuyệt đối với client HTTP do kẻ tấn công tự điều khiển. Định danh này vẫn không phải credential đăng nhập và không được dùng để bỏ qua bước xác minh tài khoản.

### Luồng kiểm tra cookie

```text
Nhận cookie với giới hạn độ dài.
Kiểm tra định dạng và phiên bản được hỗ trợ.
Xác thực MAC và thời hạn bằng quy tắc phía máy chủ.
Nếu hợp lệ: lấy deviceId đã được máy chủ phát hành.
Nếu thiếu hoặc không hợp lệ: chuyển sang nhánh nguồn chưa nhận diện.
Áp dụng các hạn mức thích hợp trước khi thực hiện tác động.
```

Không tạo key trong kho limiter cho mọi chuỗi cookie tùy ý trước khi kiểm tra. Nếu không, kẻ tấn công có thể làm số key tăng không giới hạn bằng dữ liệu rác.

## 5. Thiết bị chưa nhận diện và việc cấp ID mới

Một lỗi thiết kế phổ biến là:

```text
Không có cookie
    → tạo deviceId mới
    → cấp bucket đầy
    → cho phép gửi thông điệp
```

Nếu mỗi lần xóa cookie đều nhận một bucket đầy, giới hạn thiết bị có thể bị né gần như tức thời.

Nhánh nguồn chưa nhận diện cần có kiểm soát riêng, chẳng hạn:

- Ngân sách tiếp nhận ở gateway hoặc nguồn mạng được xác lập tin cậy.
- Hạn mức theo tài khoản đích và challenge.
- Kiểm soát tốc độ cấp định danh hoặc mở quy trình mới.
- Ngân sách toàn cục cho tài nguyên gửi thông điệp.
- Bước kiểm tra bổ sung theo rủi ro khi cần.

Việc cấp cookie mới không phải một sự kiện xác minh danh tính. Không gán trạng thái “đáng tin” chỉ vì cookie có chữ ký hợp lệ hoặc đã tồn tại một khoảng thời gian.

Cũng không nên chặn vĩnh viễn mọi người chưa có cookie. Người mất thiết bị chính, đổi trình duyệt hoặc dùng một máy khác chính là nhóm cần khôi phục. Họ cần một lối tiếp tục có giới hạn và phù hợp rủi ro.

Không gom toàn bộ người chưa có cookie trên toàn hệ thống vào một bucket nhỏ duy nhất. Một nguồn lạm dụng có thể làm tất cả người dùng mới bị từ chối.

## 6. Phối hợp với các chiều hạn mức khác

Một quyết định tiếp nhận minh họa:

```text
Cho phép thao tác khi:
    Ngân sách nguồn hoặc thiết bị phù hợp còn đủ
    VÀ ngân sách tài khoản đích phù hợp còn đủ
    VÀ ngân sách challenge còn đủ nếu có
    VÀ ngân sách dịch vụ hoặc nhà cung cấp còn đủ
    VÀ các điều kiện xác minh nghiệp vụ được đáp ứng
```

Hạn mức theo từng chiều giải quyết các kiểu lạm dụng khác nhau:

| Mẫu lưu lượng | Chiều hữu ích |
| --- | --- |
| Một deviceId thử nhiều tài khoản | Device và nguồn |
| Nhiều deviceId nhắm một tài khoản | Tài khoản và challenge |
| Nhiều định danh mới liên tục xuất hiện | Cấp ID, nguồn và ngân sách toàn cục |
| Một thiết bị dùng nhiều kênh gửi | Device cùng nhóm thao tác liên quan |
| Nhiều người dùng chung NAT | Device giúp phân biệt thêm, bên cạnh giới hạn nguồn được điều chỉnh phù hợp |
| Một cookie bị sao chép rộng rãi | Device có thể gom lưu lượng, nhưng cần điều tra nguồn và tài khoản liên quan |

OWASP khuyến nghị chống gửi yêu cầu khôi phục tự động quá mức, bao gồm giới hạn theo tài khoản để hạn chế làm ngập kênh nhận. Vì vậy, thêm chiều thiết bị không có nghĩa bỏ chiều tài khoản. Xem [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Không lấy IP trực tiếp từ một header forwarding mà mọi client đều có thể tự gửi. Chuỗi proxy phải xác định trường nào được tin cậy; nếu không, chiều nguồn mạng cũng dễ bị giả.

### Hạn mức thiết bị và độ an toàn của mã

Giả sử mỗi deviceId được phép thử b lần. Nếu một bên có thể tạo m deviceId, họ có thể tìm cách thực hiện tới m × b lần thử nếu không có giới hạn bổ sung.

Do đó, ngân sách thử mã bắt buộc phải được kiểm soát tại phạm vi bằng chứng hoặc tài khoản phù hợp. Device chỉ bổ sung khả năng phát hiện và giảm lưu lượng từ một nguồn quan sát được.

## 7. Thiết kế khóa bộ đếm

Một khóa bucket minh họa:

```text
recovery:rl:v1:tenant:<tenantRef>:device:<deviceRef>:operation:<operationClass>
```

Trong đó:

- `tenantRef` được máy chủ xác lập, không phải một tenant bất kỳ do client chọn.
- `deviceRef` được suy ra từ ID hợp lệ, có thể dùng HMAC với khóa quản lý riêng.
- `operationClass` thuộc một tập cố định, chẳng hạn START, SEND hoặc VERIFY.
- `v1` là phiên bản mô hình key được quản lý.

HMAC của ID hỗ trợ hạn chế việc lộ trực tiếp một định danh qua key hoặc log. Nó không xóa mọi rủi ro liên kết dữ liệu; người có quyền truy cập kết quả vẫn có thể tương quan các hoạt động.

Cần phân biệt:

```text
device:<D>:operation:VERIFY
    Giới hạn tổng các lần thử từ D qua nhiều tài khoản.

device:<D>:account:<A>:operation:VERIFY
    Giới hạn cặp D và A.
```

Nếu chỉ có key theo cặp thiết bị–tài khoản, một thiết bị vẫn có thể chuyển qua nhiều tài khoản. Nếu chỉ có key tổng theo thiết bị, nhiều thiết bị vẫn có thể cùng nhắm một tài khoản.

Không đưa URL tùy ý, User-Agent nguyên văn hoặc toàn bộ payload vào key. Tập operation cần hữu hạn; các trường đầu vào phải có giới hạn và cách chuẩn hóa được kiểm soát.

### Đổi phiên bản và khóa HMAC

Đổi prefix hoặc khóa suy ra deviceRef có thể làm hệ thống nhìn bucket cũ như chưa tồn tại. Nếu rollout không có chiến lược chuyển tiếp, mỗi lần thay cấu hình có thể vô tình cấp thêm một đợt ngân sách.

Cần xác định thời gian hỗ trợ định dạng cũ, cách giữ hiệu lực hạn mức trong giai đoạn chuyển đổi và giới hạn phát sinh khi bắt buộc cắt sang phiên bản mới.

## 8. Chọn thuật toán: ví dụ token bucket

Token bucket cho phép một lượng burst hữu hạn, sau đó nạp lại ngân sách theo tốc độ đã định. Tài liệu Redis minh họa thuật toán này cho limiter phân tán. Xem [Redis — Token bucket rate limiter](https://redis.io/docs/latest/develop/use-cases/rate-limiter/redis-py/).

Ký hiệu:

- B: sức chứa tối đa của bucket.
- r: số token được nạp mỗi giây.
- x: số token đang có ở lần cập nhật trước.
- dt: khoảng thời gian hợp lệ đã trôi qua.
- c: chi phí của request, với 0 < c <= B.

Cách tính:

```text
available = min(B, x + r × dt)

Nếu available >= c:
    cho phép
    remaining = available - c
Ngược lại:
    từ chối
    remaining = available
    thời gian chờ ước tính = (c - available) / r
```

Ví dụ hoàn toàn minh họa: B = 5, r = 1/60 token mỗi giây và c = 1. Sau khi dùng hết bucket, cần khoảng 60 giây để có thêm một lượt; cần khoảng 5 phút không có tiêu thụ mới để nạp lại đầy.

Trong mô hình lý tưởng, một bucket đã đầy không cho vượt quá B + r × T đơn vị chi phí trong khoảng T giây. Đây là thuộc tính của một bucket được duy trì đúng, không phải cam kết cho mọi người dùng khi họ có thể tạo nhiều định danh.

| Thuật toán | Đặc điểm cần xét |
| --- | --- |
| Fixed window | Đơn giản, nhưng có thể dồn hai đợt gần ranh giới cửa sổ |
| Sliding window | Phản ánh khoảng thời gian trượt, đổi lại cần quản lý dữ liệu phù hợp |
| Token bucket | Cho burst có kiểm soát và tốc độ dài hạn |
| Leaky bucket | Hướng tới làm đều nhịp, cần cân nhắc độ trễ hoặc hàng đợi |

Không dùng hàng đợi không giới hạn để “làm mượt” yêu cầu khôi phục. Yêu cầu gửi thông điệp có thể trở nên lỗi thời trong lúc chờ hoặc làm tiêu tốn tài nguyên dù người dùng không còn cần.

## 9. Cập nhật bucket phải nguyên tử

Một cách sai ở nhiều instance:

```text
A đọc còn 1 token.
B đọc còn 1 token.
A cho phép và ghi còn 0.
B cũng cho phép và ghi còn 0.
```

Để xử lý đúng, bước đọc, nạp lại, quyết định và ghi phải được phối hợp như một phép thao tác nguyên tử trên trạng thái chuẩn.

Mã giả cho một bucket:

```text
consume(bucketKey, capacity, refillRate, cost):
    kiểm tra tham số từ cấu hình phía máy chủ

    trong thao tác nguyên tử của kho limiter:
        now = thời gian do hạ tầng tin cậy cung cấp
        state = đọc bucket hoặc trạng thái khởi tạo hợp lệ
        effectiveNow = max(now, state.lastUpdatedAt)
        elapsed = effectiveNow - state.lastUpdatedAt
        available = min(capacity, state.tokens + elapsed * refillRate)

        allowed = available >= cost
        remaining = available - cost nếu allowed, ngược lại available

        lưu remaining và effectiveNow
        đặt thời gian hết hạn phù hợp với thời gian nạp lại và chính sách
        trả allowed cùng thời gian chờ ước tính
```

Mã giả chưa bao gồm cách cấp định danh, xử lý mất dữ liệu hoặc tính nhất quán giữa nhiều bucket. Những phần đó vẫn cần quyết định riêng.

Redis bảo đảm script Lua thực thi nguyên tử tại server; script cũng chặn hoạt động khác trong thời gian chạy, nên logic limiter phải ngắn và có giới hạn. Xem [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/).

Tính nguyên tử không đồng nghĩa script được rollback như transaction cơ sở dữ liệu khi xảy ra lỗi sau một phần ghi. Các tham số và loại dữ liệu cần được kiểm soát trước các thao tác có tác động.

### Nhiều chiều không tự thành một transaction

Một script cập nhật bucket thiết bị không tự làm bucket tài khoản hoặc ngân sách nhà cung cấp trở nên nguyên tử cùng nó. Redis Cluster còn giới hạn thao tác nhiều key theo hash slot. Xem [Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).

Một thiết kế đơn giản có thể tiêu thụ các ngân sách tiếp nhận theo thứ tự và chỉ thực hiện tác động khi mọi điều kiện đạt. Nếu một bước sau từ chối, một số ngân sách trước đã bị tính; cần ghi rõ đây là ngữ nghĩa đếm lượt thử, không phải đếm lần gửi thành công.

Không hoàn lại token một cách tùy tiện sau lỗi. Việc hoàn lại thiếu phối hợp có thể làm bucket vượt sức chứa hoặc bị lợi dụng để tái tạo ngân sách. Với ngân sách cần reservation và xác nhận chi phí thực tế, phải có mô hình riêng cho việc giữ chỗ, hoàn tất và hủy.

## 10. TTL, số lượng key và sự cố kho trạng thái

Limiter cũng là một tài nguyên cần bảo vệ.

### TTL phải phù hợp thuật toán

Với token bucket, xóa trạng thái khi bucket chưa thể nạp đầy sẽ làm request sau được khởi tạo với ngân sách mới quá sớm. TTL cần đủ dài theo thời gian nạp lại và chính sách, có xét cách xử lý đồng hồ và dữ liệu.

Không gia hạn hiệu lực của device cookie chỉ vì bucket được truy cập, trừ khi đó là một chính sách đã được thiết kế. Vòng đời định danh và vòng đời bộ đếm là hai việc khác nhau.

Nếu backend clock bất thường, không lấy thời gian client để bù. Cần phát hiện sai lệch, giữ cách tính thận trọng và có chính sách vận hành phù hợp.

### Số lượng định danh phải có giới hạn

Dù cookie có MAC, một bên vẫn có thể xin nhiều cookie do máy chủ phát hành. Chỉ kiểm tra chữ ký không giải quyết được việc số key tăng.

Cần xét tốc độ cấp ID, thời gian lưu key, ngân sách bộ nhớ, số operation class và năng lực xử lý khi nhiều định danh mới xuất hiện.

Không đưa một key toàn cục cố định vào cùng mọi bucket để ép tất cả vào một shard chỉ nhằm có transaction dễ viết. Cách đó có thể tạo điểm nóng; kiến trúc nhiều chiều cần cân nhắc cả tính nhất quán và khả năng chịu tải.

### Mất dữ liệu và timeout

Nếu kho limiter bị xóa, restart mất trạng thái, eviction hoặc failover làm mất một số lần ghi, bucket có thể được khởi tạo lại. Thuộc tính giới hạn khi đó có một khoảng sai lệch; không nên mô tả nó như giới hạn tuyệt đối không thể vượt.

Timeout không cho biết chắc thao tác đã tiêu thụ ngân sách hay chưa. Retry mù có thể tính hai lần. Cần lựa chọn rõ giữa cách đếm lượt thử thận trọng và một cơ chế deduplicate riêng cho request của limiter.

Với thao tác nhạy cảm như thử mã hoặc gửi thông điệp có chi phí, không chuyển tự động sang “cho phép tất cả” khi kho limiter lỗi. Có thể hạn chế tạm thời thao tác đó và cung cấp hướng dẫn hoặc lối tiếp tục được kiểm soát.

Một limiter cục bộ dự phòng có thể giảm tải, nhưng n instance với ngân sách độc lập có thể cho tổng ngân sách lớn hơn dự kiến. Dự phòng cần một giới hạn và thời gian áp dụng rõ ràng, trong khi các bất biến nghiệp vụ vẫn được thực thi.

## 11. Phản hồi HTTP và trải nghiệm người dùng

RFC 6585 định nghĩa 429 Too Many Requests và cho phép dùng Retry-After để chỉ thời gian chờ trước khi thử lại. Xem [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Ví dụ khi giới hạn dựa trên nguồn hoặc thiết bị và phản hồi không tiết lộ tài khoản tồn tại:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Cache-Control: no-store
Content-Type: application/json

{
  "code": "RECOVERY_RATE_LIMITED",
  "message": "Bạn đã thao tác nhiều lần. Hãy chờ trước khi thử lại."
}
```

Con số 60 chỉ là ví dụ. Nếu còn nhiều hạn mức khác, thời gian chờ của bucket thiết bị không bảo đảm request kế tiếp sẽ thành công.

Không trả số lần thử OTP còn lại của một tài khoản chưa được xác minh cho bất kỳ người gọi nào. Không để khác biệt mã HTTP hoặc thời gian chờ trở thành cách dò tài khoản có tồn tại hay đang nhận yêu cầu khôi phục.

Ở endpoint bắt đầu khôi phục, dịch vụ có thể dùng phản hồi tiếp nhận tổng quát cho các tình huống tài khoản đích khác nhau, trong khi việc gửi được điều phối nội bộ. Nội dung không nên khẳng định thư chắc chắn đã gửi nếu thực tế mới chỉ tiếp nhận yêu cầu.

Giao diện có thể vô hiệu hóa nút gửi lại trong thời gian chờ và hiển thị bước tiếp tục. Máy chủ vẫn phải thực thi hạn mức; đồng hồ đếm ngược trên trình duyệt chỉ hỗ trợ trải nghiệm.

Không hướng dẫn người dùng xóa cookie hoặc đổi thiết bị để vượt hạn mức. Cần có lối hỗ trợ chính thức cho người bị chặn nhầm mà vẫn giữ các điều kiện xác minh.

## 12. Công bằng và quyền riêng tư

Người dùng đang khôi phục thường xuất hiện trên thiết bị mới hoặc môi trường không quen. Một chính sách chỉ ưu ái thiết bị từng dùng có thể khiến nhóm cần hỗ trợ nhất không còn đường tiếp tục.

Các tình huống cần xét:

- Máy dùng chung cho nhiều người trong gia đình hoặc điểm hỗ trợ.
- Trình duyệt tự xóa dữ liệu hoặc chặn lưu trữ.
- Người dùng chuyển từ ứng dụng sang web để khôi phục.
- Nhiều người ở sau cùng NAT hoặc proxy doanh nghiệp.
- Thiết bị bị mất chính là nơi giữ định danh trước đó.
- Người dùng cần công cụ trợ năng hoặc thao tác chậm, dễ gửi lại.

Thiết kế có thể phân biệt trạng thái nhận diện và điều chỉnh bước bổ sung, nhưng không coi thiếu cookie là dấu hiệu đủ để kết luận gian lận.

Chỉ thu tín hiệu thiết bị phục vụ mục đích cụ thể. Không mở rộng fingerprint vô hạn để cố đạt một định danh vật lý duy nhất. Cần quy định thời gian lưu, quyền truy cập và cách xoay định danh phù hợp.

Định danh thiết bị không nên được dùng làm nhãn công khai hoặc cơ sở duy nhất để tiết lộ lịch sử các tài khoản đã dùng trên một máy.

## 13. Quan sát và điều chỉnh chính sách

Một sự kiện nội bộ minh họa:

```json
{
  "event": "RECOVERY_RATE_LIMIT_DECISION",
  "interactionId": "server-generated-id",
  "deviceClass": "SERVER_ISSUED_COOKIE",
  "deviceRef": "restricted-pseudonymous-reference",
  "operationClass": "VERIFY",
  "decision": "DENY",
  "reason": "DEVICE_BUDGET_EXHAUSTED",
  "policyVersion": "recovery-device-v2",
  "limiterMode": "SHARED",
  "retryAfterSeconds": 60
}
```

Không ghi cookie thô, token khôi phục, OTP hoặc URL chứa bí mật. DeviceRef dù đã được biến đổi vẫn có thể liên kết hoạt động, nên cần hạn chế truy cập và thời gian lưu.

Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tỷ lệ từ chối theo operation và lớp thiết bị | Chính sách ảnh hưởng bước nào |
| Tỷ lệ request thiếu hoặc sai cookie | Thay đổi môi trường hoặc chiến dịch né định danh |
| Số ID mới và số key hoạt động | Khả năng tăng cardinality hoặc chi phí lưu trữ |
| Tỷ lệ khôi phục hợp lệ hoàn tất | Tác động tới người dùng thật |
| Thời gian chờ và số lần liên hệ hỗ trợ | Mức bế tắc do giới hạn |
| Lỗi, timeout và chế độ dự phòng của limiter | Độ tin cậy của quyết định |
| Số lần gửi thực tế và chi phí nhà cung cấp | Hiệu quả bảo vệ tài nguyên |

Không đưa từng deviceRef vào label metric không giới hạn. Có thể dùng log hạn chế quyền cho điều tra và metric tổng hợp cho vận hành.

Đặt phiên bản chính sách trong sự kiện để đối chiếu thay đổi. Khi điều chỉnh hạn mức, cần xét hành vi của bucket đang tồn tại, thay vì vô tình cấp lại toàn bộ ngân sách.

## 14. Ví dụ áp dụng và giới hạn cần nhớ

### Một thiết bị gửi tới nhiều tài khoản

Một deviceId tạo yêu cầu cho nhiều email. Bucket tổng của thiết bị giúp giảm tốc nguồn này dù mỗi tài khoản chỉ nhận một yêu cầu. Ngân sách gửi theo tài khoản và nhà cung cấp tiếp tục bảo vệ người nhận và chi phí.

### Nhiều định danh nhắm một OTP

Kẻ tấn công thay cookie sau mỗi nhóm lần thử. Bucket theo thiết bị riêng lẻ có thể không nhận ra cùng một nguồn vật lý. Giới hạn theo challenge hoặc tài khoản vẫn phải ngăn tổng số lần thử tăng không kiểm soát.

### Người dùng thật đổi trình duyệt

Người dùng mất điện thoại và dùng trình duyệt mới trên máy mượn. Hệ thống tiếp nhận theo nhánh chưa nhận diện, với ngân sách nguồn và tài khoản phù hợp. Các bước xác minh quyết định quyền khôi phục; việc không có cookie cũ không tự đóng mọi lối tiếp tục.

### Cookie bị sao chép

Hai client dùng cùng cookie hợp lệ có thể cùng tiêu thụ một bucket. MAC không phát hiện việc sao chép nguyên vẹn. Hệ thống vẫn cần bảo vệ session, bằng chứng khôi phục và đánh giá tín hiệu khác khi có dấu hiệu lạm dụng.

Cơ chế đạt mục đích khi giới hạn được lưu lượng từ một định danh quan sát được, phối hợp với các chiều khác và giữ lối tiếp tục cho người dùng hợp lệ. **Device ID là một khóa điều phối ngân sách; bằng chứng và chính sách khôi phục mới quyết định quyền thay đổi tài khoản.**

## Tài liệu tham khảo

- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): hạn chế lạm dụng yêu cầu khôi phục và kênh nhận.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): thuộc tính và tiền tố cookie.
- [Redis — Token bucket rate limiter](https://redis.io/docs/latest/develop/use-cases/rate-limiter/redis-py/): mô hình bucket và phối hợp trạng thái dùng chung.
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/): tính nguyên tử và phạm vi thực thi script.
- [Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): giới hạn nhiều key và đặc tính lưu trữ phân tán.
- [RFC 6585, mục 4 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4): phản hồi rate limiting.
