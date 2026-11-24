# Recovery test data

## 1. Dữ liệu kiểm thử phải biểu diễn được nguy cơ nào?

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, kiểm thử cần đánh giá khả năng khôi phục quyền truy cập khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Dữ liệu kiểm thử phải làm rõ hệ thống cho phép ai thay đổi điều gì, dựa trên bằng chứng nào, trong khoảng thời gian nào và với tác động nào lên credential hoặc session.

Một tài khoản mẫu cùng một token còn hạn chỉ đủ cho happy path rất hẹp. Nó không phát hiện token dùng lại được, bằng chứng của tenant khác bị chấp nhận, request bị hủy vẫn tiếp tục đổi MFA, hoặc mật khẩu đã đổi nhưng session của kẻ tấn công còn sử dụng được.

Recovery test data là tập dữ liệu được thiết kế để tạo các trạng thái và chuỗi thao tác có ý nghĩa đối với những nguy cơ đó. Nó gồm không chỉ hàng database mà còn thời gian kiểm thử, danh tính actor, kết quả của nhà cung cấp xác minh, trạng thái thiết bị, session, message và các lỗi được chủ động tạo ra.

Bài học tập trung vào cách xây dựng, phân loại và sử dụng dữ liệu này. Các schema, tên lớp và ví dụ bên dưới là minh họa cho test harness; chúng không phải yêu cầu sửa cấu trúc metadata của bài học hay mô tả những thành phần đã có sẵn trong dự án.

## 2. Bắt đầu từ bất biến và kết quả quan sát được

Mỗi nhóm dữ liệu cần gắn với một bất biến bảo mật. Nếu không xác định oracle, tức căn cứ để kết luận kết quả đúng, một tập fixture lớn vẫn có thể chỉ kiểm tra được HTTP status.

| Bất biến cần bảo vệ | Dữ liệu cần tạo | Kết quả cần quan sát |
| --- | --- | --- |
| Token chỉ dùng một lần | Một token hợp lệ và hai lần sử dụng | Chỉ một thay đổi được áp dụng; replay không tạo quyền mới |
| Quyền khôi phục đúng mục đích | Token password reset dùng cho MFA reset | Từ chối tác động sai mục đích |
| Không vượt ranh giới tenant | Hai tenant có dữ liệu dễ nhầm lẫn | Tenant A không thay credential hay xem request của tenant B |
| Thời hạn được thực thi ở điểm quyết định | Token trước hạn, đúng hạn và sau hạn | Hành vi đúng theo quy tắc so sánh đã công bố |
| Quyết định không dựa vào dữ liệu do client tự khai | Payload nói `verified=true` nhưng không có bằng chứng hợp lệ | Không cấp quyền thay credential |
| Session được xử lý theo policy | Nhiều session trước và sau thay đổi | Session trong phạm vi bắt buộc không còn truy cập được |
| Thất bại không để lại thành công giả | Lỗi sau tiêu thụ token hoặc trước commit | Trạng thái phản ánh đúng tác động đã commit và việc còn chờ |
| Không lộ tài khoản qua phản hồi khởi tạo | Định danh tồn tại và không tồn tại | Hợp đồng phản hồi công khai nhất quán theo thiết kế |
| Không lộ bí mật trong quan sát | Token tổng hợp đặc trưng | Log, event, report và trace không chứa raw secret |

Một lần từ chối có thể vẫn tăng bộ đếm thử, ghi audit hoặc tạo metric. Vì vậy “không thay đổi dữ liệu” cần được diễn đạt chính xác: credential, quyền và session được bảo vệ không thay đổi ngoài chính sách; các tác động quan sát hoặc chống lạm dụng được phép vẫn có thể xảy ra.

Với phản hồi chống enumeration, kiểm tra status và nội dung là cần thiết nhưng chưa đủ để chứng minh không có kênh rò rỉ thời gian, kích thước hoặc hành vi vận hành. Bộ dữ liệu nên tạo được hai nhóm so sánh; việc đánh giá kênh rò rỉ cần phương pháp và môi trường đo riêng.

## 3. Mô hình dữ liệu tối thiểu cho một kịch bản

Một kịch bản tự chứa cần cho người đọc biết actor, subject và trạng thái của các quyền liên quan. Không nên dựa vào một tài khoản dùng chung đã được các test trước vô tình chuẩn bị sẵn.

| Nhóm dữ liệu | Những thuộc tính hữu ích |
| --- | --- |
| Tenant và tài khoản | Tenant ID, account ID, trạng thái hoạt động/khóa, kênh liên hệ đã xác minh |
| Actor | Người dùng chưa đăng nhập, người dùng có session giới hạn, nhân viên hỗ trợ, workload |
| Credential | Mật khẩu có thể dùng, MFA đã đăng ký, passkey, trạng thái thiết bị hoặc credential bị thu hồi |
| Recovery request | Purpose, trạng thái, generation, thời điểm tạo/hết hạn, phiên bản policy |
| Bằng chứng | Nguồn xác minh, mức bảo đảm, binding, thời hạn, kết quả đã xác thực hoặc chưa rõ |
| Token/challenge | Trạng thái, digest đúng định dạng, thời hạn, ngân sách thử, binding với request |
| Risk decision | Decision ID, kết quả cho phép/từ chối/step-up, phiên bản policy và hạn hiệu lực |
| Session | Session của chủ tài khoản, session nghi bị chiếm, refresh token, phiên bản xác thực |
| Hỗ trợ thủ công | Quyền của nhân viên, phạm vi tenant, ticket, phê duyệt cần thiết |
| Delivery/event | Intent gửi, outbox, message ID, inbox, trạng thái pending hoặc đã áp dụng |
| Môi trường | Clock, run scope, fake provider, nơi nhận thông báo và lịch lỗi |

Không phải test nào cũng cần đủ mọi nhóm. Một unit test kiểm tra predicate thời hạn chỉ cần các trường liên quan. Một integration test chứng minh tiêu thụ token cùng thay credential cần database thật trong phạm vi đó và những quan hệ tương ứng. Một bài end-to-end phải thực sự đi qua đường cấp quyền được đánh giá, thay vì seed sẵn kết quả cuối rồi gọi API đọc trạng thái.

### 3.1. Phân biệt actor và subject

Trong khôi phục tự phục vụ, actor có thể đang chưa có session bình thường. Trong hỗ trợ thủ công, actor là nhân viên, subject là tài khoản khách hàng. Nếu fixture dùng cùng một ID cho cả hai ở mọi test, lỗi ghi nhận sai người thao tác hoặc kiểm tra quyền sai đối tượng có thể không bị phát hiện.

Nên có ít nhất một trường hợp actor và subject khác nhau, một trường hợp actor thuộc tenant khác, và một trường hợp actor có quyền đọc ticket nhưng không có quyền thay MFA. Không coi mọi tài khoản có role support là có toàn quyền khôi phục.

### 3.2. Dữ liệu hợp lệ trước, biến thể sai có chủ đích sau

Fixture cơ sở nên thỏa mãn khóa ngoại, trạng thái và timestamp. Từ đó, mỗi test làm sai một hoặc một nhóm điều kiện có mục đích. Nếu token vừa hết hạn, sai tenant, sai digest và sai purpose, test bị từ chối không cho biết cơ chế nào thực sự được thực thi.

Dữ liệu cố tình vi phạm constraint là một nhóm riêng cho kiểm thử persistence hoặc migration. Không dùng cách tắt constraint rồi insert hàng bất khả thi để chứng minh một luồng API bình thường an toàn, trừ khi test đang mô phỏng rõ ràng tình huống dữ liệu hỏng.

## 4. Xây ma trận dữ liệu theo trạng thái và ranh giới tin cậy

Không cần lấy tích Descartes của mọi thuộc tính. Bắt đầu từ các tình huống quan trọng, rồi bổ sung những tương tác có nguy cơ cao.

| Mã kịch bản | Biến thể chính | Điều phải được chứng minh |
| --- | --- | --- |
| `PW_VALID` | Mất mật khẩu, token đúng, đủ điều kiện | Đổi mật khẩu theo policy, token bị tiêu thụ, session được xử lý |
| `TOKEN_USED` | Token đã được tiêu thụ | Không thực hiện một thay đổi credential mới |
| `TOKEN_REVOKED` | Token đã bị thu hồi nhưng còn thời gian | Trạng thái thu hồi có hiệu lực độc lập với thời hạn |
| `TOKEN_WRONG_PURPOSE` | Token password reset gửi vào MFA reset | Binding mục đích được kiểm tra |
| `TOKEN_WRONG_ACCOUNT` | Token của tài khoản khác trong cùng tenant | Không chỉ kiểm tra digest rồi tin account ID từ client |
| `TOKEN_WRONG_TENANT` | Cùng local account ID ở hai tenant | Không nhầm ranh giới tenant |
| `REQUEST_CANCELLED` | Request đã hủy, token chưa được dùng | Không tiếp tục thao tác theo request đã đóng |
| `PROOF_STALE` | Quyết định xác minh không còn hiệu lực tại thời điểm yêu cầu dùng quyền | Không cấp quyền từ bằng chứng đã hết hiệu lực |
| `RISK_DENIED` | Token đúng nhưng risk policy từ chối | Token không tự vượt qua quyết định rủi ro |
| `MFA_LOST` | Không còn thiết bị MFA hiện tại | Đi đúng luồng chứng minh thay thế, không giả định có OTP cũ |
| `PASSKEY_LOST` | Không có private key của passkey đã mất | Không dùng một credential còn dùng được để giả lập mất toàn bộ |
| `SUPPORT_SCOPE_DENIED` | Nhân viên có quyền không đủ hoặc sai tenant | Không thay credential ngoài phạm vi phân quyền |
| `PROVIDER_UNKNOWN` | Nhà cung cấp xác minh timeout | Không coi chưa biết là xác minh thành công |
| `SESSION_PENDING` | Credential đã đổi, thu hồi session chưa đạt điều kiện | Không công bố hoàn tất quá sớm |

Các tương tác nên được ưu tiên gồm token hết hạn trong lúc chờ khóa, resend cạnh tranh với consume, cancellation cạnh tranh với finalization và hai recovery request tác động cùng tài khoản. Pairwise có thể giúp mở rộng dữ liệu thông thường, nhưng không thay thế những tổ hợp được chọn theo mô hình đe dọa.

## 5. Thời gian là một phần của fixture

### 5.1. Chọn một mốc cố định và định nghĩa biên

Giả sử quy tắc token là `expires_at > checked_at`, nghĩa là tại thời điểm bằng nhau token đã hết hạn. Đặt một mốc kiểm thử cố định:

```text
T0 = 2026-11-24T00:00:00Z

TOKEN_BEFORE_EXPIRY: expires_at = T0 + 1 giây
TOKEN_AT_EXPIRY:     expires_at = T0
TOKEN_AFTER_EXPIRY:  expires_at = T0 - 1 giây

Điểm kiểm tra quyết định: checked_at = T0
```

Những khoảng thời gian trong ví dụ chỉ để tạo biên kiểm thử, không phải khuyến nghị TTL cho production. Cần chọn độ phân giải phù hợp với nơi lưu: nếu database làm tròn hoặc cắt timestamp ở mức microsecond, một biến thể chỉ khác nhau một nanosecond có thể không còn khác sau khi persist.

| Nhóm thời gian | Dữ liệu cần kiểm tra |
| --- | --- |
| Thời hạn token | Trước, đúng, sau `expires_at` |
| Thời hạn request | Token còn hạn nhưng request cha đã hết hạn |
| Hiệu lực bắt đầu | Trước, đúng, sau `not_before` nếu hệ thống có trường này |
| Phê duyệt hỗ trợ | Phê duyệt đúng mục đích nhưng hết hạn trước hành động |
| Cooldown/resend | Ngay trước và đúng biên cho phép gửi lại |
| Thời gian chờ | Dữ liệu hợp lệ lúc vào queue nhưng hết hiệu lực trước điểm cấp quyền |

Tách thời điểm cấp quyền, thời điểm áp dụng tác động và thời điểm phát sự kiện. Một token hết hạn sau khi được tiêu thụ hợp lệ không làm thay đổi đã commit tự biến mất. Fixture phải mô tả thứ tự thao tác, không chỉ một cờ `expired=true`.

### 5.2. Clock của ứng dụng không tự điều khiển clock của database

Unit test có thể dùng `Clock.fixed(...)` hoặc clock có thể tiến từng bước. Nếu production SQL dùng thời gian database, thay clock trong Java không làm `now()` của database thay đổi. Integration test cần xác định rõ nguồn thời gian thực sự được dùng để ra quyết định.

Có thể dùng giá trị timestamp tương đối với thời gian database, hoặc một thiết kế nhận thời gian tin cậy từ lớp đã được kiểm soát khi phù hợp. Không thêm header công khai để client tùy ý đặt “thời gian hiện tại” nhằm phục vụ test. Test seam không được trở thành khả năng bỏ qua thời hạn trong môi trường thật.

Trong test chờ khóa, cần xác định thời gian được lấy trước hay sau khi chờ và bảo đảm đang kiểm tra đúng hợp đồng. Dùng một lần `sleep` rồi mong token hết hạn thường tạo test chậm và dễ chập chờn; ưu tiên clock được điều khiển hoặc điểm đồng bộ rõ ràng.

## 6. Dữ liệu tổng hợp và bí mật kiểm thử

### 6.1. Không sao chép dữ liệu khôi phục thật

Không sử dụng mật khẩu, recovery token, OTP, recovery code, session cookie, private key hay hồ sơ xác minh của người dùng thật. Đổi email trong một bản dump chưa làm các dữ liệu còn lại an toàn: digest, lịch sử hỗ trợ, thiết bị, IP và các tham chiếu vẫn có thể liên kết tới người dùng.

Mọi tài khoản, hành vi và bằng chứng dùng trong fixture nên được tạo tổng hợp. Nếu kiểm thử tích hợp nhà cung cấp định danh, dùng bộ dữ liệu sandbox mà nhà cung cấp dành cho kiểm thử, với quyền và cấu hình môi trường phù hợp; không dùng giấy tờ thật để làm cho test “giống thực tế”.

### 6.2. Địa chỉ mẫu không thay thế chặn delivery thật

Có thể dùng email như `learner-a@example.invalid` để thể hiện dữ liệu tổng hợp. Tuy nhiên, kiểm soát quyết định vẫn là mail transport giả, test sink và cấu hình chặn gửi ra ngoài. Không dựa vào việc một địa chỉ trông giả để bảo đảm mọi provider hoặc đường gửi đều an toàn.

Với SMS, không tự chọn một chuỗi số có vẻ ngẫu nhiên vì nó có thể thuộc về người thật. Unit test có thể dùng reference tượng trưng với fake provider; test kiểm tra định dạng dùng dữ liệu đúng mục đích; integration với provider dùng số sandbox được cấp cho môi trường kiểm thử.

Các địa chỉ và kênh tổng hợp cần có trạng thái verified/unverified rõ ràng. Không mặc định mọi contact do fixture tạo đều đủ tin cậy cho khôi phục.

### 6.3. Tách tính tái lập của nghiệp vụ khỏi bí mật

ID tài khoản, mốc thời gian và kết quả fake risk có thể được tạo tái lập để dễ điều tra. Recovery token phải có cơ chế riêng. Trong test cần kiểm tra đường codec thật, dùng token tổng hợp được sinh và encode bằng cơ chế tương thích với production, với khóa chỉ thuộc môi trường test.

Không seed raw token bằng account ID rồi để factory đó lọt vào đường production. Một chuỗi cố định chỉ phù hợp với test cố lập và seam đã được xác định; nó không kiểm tra chất lượng bộ sinh ngẫu nhiên. Các test về bộ sinh token phải gọi đúng bộ sinh cần đánh giá, không gọi fixture generator thay thế.

Secret của test chỉ nên tồn tại ở nơi cần để thực hiện request và so sánh có kiểm soát. Khi báo lỗi, in case ID, secret reference hoặc fingerprint an toàn theo thiết kế, không in raw value. Tránh mặc định `toString()` của record/DTO hoặc assertion message làm lộ toàn bộ secret vào CI report.
