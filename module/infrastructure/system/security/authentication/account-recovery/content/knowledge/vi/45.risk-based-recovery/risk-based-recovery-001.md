# Recovery risk score

## 1. Điểm rủi ro phục hồi tài khoản dùng để làm gì?

Recovery risk score là điểm tổng hợp tín hiệu về một yêu cầu khôi phục tài khoản, dùng để chọn mức kiểm soát phù hợp trước khi cho phép thay đổi thông tin xác thực. Trong bài này, thang điểm chạy từ 0 đến 100; điểm cao hơn biểu thị bối cảnh đáng lo hơn.

Người dùng có thể quên mật khẩu, mất điện thoại chứa TOTP, mất khóa bảo mật hoặc không còn truy cập được passkey. Chính các tình huống hợp lệ này thường tạo ra thiết bị mới, địa chỉ mạng mới và thiếu yếu tố xác thực quen thuộc. Hệ thống cần phát hiện chiếm đoạt tài khoản mà vẫn cung cấp đường phục hồi khả thi cho chủ tài khoản.

Điểm số hỗ trợ trả lời: **yêu cầu này cần thêm điều kiện nào trước khi được tiếp tục?** Quyền thay mật khẩu, đặt lại MFA hoặc đăng ký passkey mới phải dựa trên bằng chứng và chính sách riêng của thao tác.

Theo NIST SP 800-63B-4, chỉ báo gian lận không thay thế yếu tố xác thực và không tự thay đổi mức AAL của giao dịch. Vì vậy, IP quen thuộc và điểm thấp không thể biến một yêu cầu chưa xác minh thành yêu cầu đã đủ bằng chứng. [NIST SP 800-63B-4, mục 2](https://pages.nist.gov/800-63-4/sp800-63b.html#aal)

**Phạm vi minh họa:** các trọng số, ngưỡng điểm, cửa sổ thời gian và tên trạng thái dưới đây là thiết kế giả định phục vụ học tập. Chúng không phải công thức của NIST hoặc OWASP và cần được hiệu chỉnh theo dịch vụ thực tế.

## 2. Tách ba câu hỏi trước khi xây dựng công thức

| Câu hỏi | Dữ liệu cần xem | Kết quả |
| --- | --- | --- |
| Yêu cầu có dấu hiệu bị lạm dụng không? | Tần suất, thiết bị, mạng, thay đổi gần đây, tín hiệu gian lận | Điểm rủi ro và mã lý do |
| Người yêu cầu đã chứng minh được điều gì? | Kết quả xác minh recovery code, authenticator còn dùng được, quy trình xác minh được chấp nhận | Hồ sơ bằng chứng có phạm vi và thời hạn |
| Nếu phục hồi sai thì thiệt hại ra sao? | Quyền quản trị, quyền truy cập dữ liệu, khả năng chuyển tài sản | Mức kiểm soát tối thiểu theo thao tác và tài khoản |

Không gộp cả ba câu hỏi thành một số duy nhất rồi cho phép tất cả thao tác khi số đó thấp.

Ví dụ, tài khoản quản trị và tài khoản đọc tin có cùng điểm 18 vẫn có thể đi theo hai quy trình khác nhau. Tài khoản quản trị chịu mức kiểm soát tối thiểu cao hơn vì hậu quả của một quyết định sai lớn hơn.

Tương tự, OTP gửi đến email vừa được xác minh chỉ chứng minh quyền truy cập hộp thư tại thời điểm đó. Phạm vi bằng chứng này không mặc nhiên bao gồm quyền gỡ MFA hoặc thay khóa passkey của tài khoản.

Một quyết định phục hồi có thể mô hình hóa như sau:

~~~text
Quyết định =
    điều kiện bắt buộc của thao tác
    + bằng chứng đã xác minh
    + mức ảnh hưởng của tài khoản
    + đánh giá rủi ro hiện tại
    + trạng thái của hồ sơ phục hồi
~~~

## 3. Chọn tín hiệu và xác định nguồn tin cậy

Trước khi đặt trọng số, cần biết mỗi tín hiệu do ai cung cấp, đo lúc nào và có thể bị giả mạo đến đâu.

| Nhóm tín hiệu | Ví dụ | Cách diễn giải |
| --- | --- | --- |
| Thiết bị và môi trường | Thiết bị chưa từng xuất hiện; dấu hiệu tự động hóa | Thiết bị mới làm tăng bất định; fingerprint không phải bằng chứng sở hữu |
| Mạng | IP có liên quan tới lạm dụng; vị trí khác thường | Dùng như tín hiệu ngữ cảnh; VPN, NAT và chuyển mạng có thể tạo cảnh báo nhầm |
| Kênh phục hồi | Email hoặc số điện thoại vừa thay; cảnh báo chuyển SIM | Đánh giá lịch sử kênh trên máy chủ, không tin lời khai “đây là số cũ” |
| Tần suất | Nhiều lần nhập sai mã trong cửa sổ thời gian | Kết hợp theo hồ sơ, tài khoản và nguồn yêu cầu |
| Thay đổi bảo mật | Vừa thêm authenticator rồi yêu cầu xóa yếu tố cũ | Xem chuỗi sự kiện và bằng chứng đã cho phép từng thay đổi |
| Mức mất quyền truy cập | Mất một yếu tố hoặc mất toàn bộ yếu tố và kênh dự phòng | Phản ánh độ khó của phục hồi, không kết luận người dùng gian lận |
| Chất lượng dữ liệu | Nguồn tín hiệu hết hạn, timeout hoặc chưa có lịch sử | Ghi trạng thái thiếu dữ liệu, không coi là an toàn |

### 3.1. Chỉ máy chủ xây dựng đầu vào quyết định

Trình duyệt có thể gửi thông tin hỗ trợ, nhưng máy chủ phải xác minh và chuẩn hóa trước khi đưa vào bộ đánh giá.

Các giá trị như “trustedDevice=true”, “riskScore=0” hoặc “emailVerified=true” trong request của client không có giá trị làm căn cứ. Máy chủ lấy sự kiện đã xác minh từ kho dữ liệu của mình và dịch vụ tín hiệu được tin cậy.

Địa chỉ IP cũng cần được xác định qua chuỗi proxy đã cấu hình. Không đọc tùy ý header do client gửi rồi coi đó là IP thật.

### 3.2. Tách trạng thái không biết khỏi trạng thái không có rủi ro

Một tín hiệu nên có ít nhất các trạng thái:

~~~text
PRESENT(value, observedAt, source)
ABSENT(observedAt, source)
UNKNOWN(reason)
STALE(lastObservedAt, source)
~~~

“Không tìm thấy sự kiện đổi SIM trong nguồn dữ liệu đã trả lời hợp lệ” khác với “dịch vụ kiểm tra đổi SIM đang timeout”. Trạng thái thứ hai không cung cấp bằng chứng rằng số điện thoại an toàn.

Không phải dịch vụ nào cũng có dữ liệu nhà mạng hoặc lịch sử thiết bị. Với tín hiệu chưa được triển khai, chính sách phải quy định rõ đường xử lý thay thế và giới hạn áp dụng.

## 4. Xây dựng mô hình điểm có thể giải thích

Bắt đầu bằng mô hình quy tắc đơn giản thường giúp nhóm vận hành hiểu được quyết định. Một mô hình minh họa:

~~~text
R = min(100, 10 + E + C + V + H + L + U)

E: môi trường thiết bị và mạng, từ 0 đến 25
C: độ bất định của kênh phục hồi, từ 0 đến 30
V: mức lạm dụng theo tần suất, từ 0 đến 25
H: thay đổi bảo mật gần đây, từ 0 đến 25
L: mức mất phương tiện xác thực, từ 0 đến 15
U: dữ liệu bắt buộc cho đánh giá bị thiếu hoặc hết hạn, 0 hoặc 15
~~~

Ví dụ quy tắc tính các thành phần:

| Thành phần | Quy tắc minh họa |
| --- | --- |
| E | Thiết bị mới cộng 15, mạng đáng ngờ cộng 15; tổng nhóm tối đa 25 |
| C | Kênh vừa đổi cộng 20, cảnh báo kênh có thể bị chiếm quyền cộng 30; nhóm tối đa 30 |
| V | Dựa trên số lần xác minh thất bại trong cửa sổ 15 phút: 0–2 lần là 0; 3–5 lần là 10; từ 6 lần là 25 |
| H | Có thay đổi bảo mật nhạy cảm trong 24 giờ trước yêu cầu thì cộng 20 |
| L | Mất toàn bộ authenticator khả dụng thì cộng 15 |
| U | Thiếu hoặc hết hạn tín hiệu mà chính sách yêu cầu thì cộng 15 và đánh dấu cần xử lý bất định |

Giới hạn điểm theo nhóm giảm ảnh hưởng của việc cộng nhiều chỉ báo gần như cùng một nguyên nhân. Tuy nhiên, cần xem cả tương quan giữa các nhóm. Ví dụ, cùng một lần đổi email có thể xuất hiện trong C và H; phải quyết định có chủ ý xem đó là một tín hiệu hay một tổ hợp thực sự làm tăng rủi ro.

Ở mô hình này, thiết bị quen không được trừ điểm để bù cho một kênh có dấu hiệu bị chiếm quyền. Nếu sau này bổ sung yếu tố giảm điểm, cần giới hạn mức giảm và giữ nguyên các điều kiện bắt buộc.

### 4.1. Điểm 70 không đồng nghĩa xác suất gian lận 70%

Thang điểm quy tắc chỉ biểu thị thứ tự ưu tiên và mức kiểm soát do hệ thống định nghĩa. Không gọi điểm 70 là xác suất 70% nếu chưa có mô hình được hiệu chỉnh và kiểm chứng theo định nghĩa kết quả rõ ràng.

Nếu dùng mô hình xác suất, phải xác định sự kiện dự đoán, chẳng hạn “yêu cầu bị xác nhận chiếm đoạt trong vòng 30 ngày”. Xác suất này vẫn khác thiệt hại kỳ vọng: một yêu cầu ít khả năng gian lận nhưng có hậu quả rất lớn vẫn cần kiểm soát mạnh.

### 4.2. Đặt điều kiện bắt buộc ngoài phép cộng

Một số sự kiện làm cho đường tự phục vụ hiện tại không còn đủ điều kiện, bất kể tổng điểm:

- Token không hợp lệ, hết hạn hoặc đã dùng: từ chối thao tác sử dụng token đó.
- Bằng chứng chưa đủ cho việc thay MFA: tiếp tục xác minh bằng phương thức được chính sách cho phép.
- Kênh nhận mã được xác nhận bị chiếm quyền: ngừng dùng kênh đó cho hồ sơ và chuyển sang đường độc lập.
- Tài khoản có yêu cầu kiểm soát đặc biệt: áp dụng quy trình tối thiểu đã định, có thể gồm xử lý thủ công.
- Có báo cáo chiếm đoạt đã được xác minh: chuyển sang quy trình xử lý sự cố.

Không nhầm một báo cáo chưa được xác minh từ người lạ với bằng chứng đủ để khóa tài khoản. Kẻ tấn công có thể lợi dụng chính điểm vào recovery để gây từ chối dịch vụ.

## 5. Chuyển điểm số thành hành động hữu hạn

Giả sử hệ thống sử dụng bảng chính sách sau:

| Điểm | Nhánh xử lý minh họa | Điều kiện tiếp tục |
| --- | --- | --- |
| 0–24 | Tiếp tục đường phục hồi tiêu chuẩn | Bằng chứng phải đạt yêu cầu của đúng thao tác |
| 25–59 | Yêu cầu xác minh bổ sung | Có phương thức bổ sung khả dụng và đủ độc lập |
| 60–100 | Đưa sang quy trình kiểm soát tăng cường | Xác minh thủ công hoặc quy trình thay thế đã được phê duyệt |
| Bất kỳ điểm nào nhưng dữ liệu bắt buộc chưa đủ | Tạm hoãn quyết định tự phục vụ | Thu thập lại dữ liệu hoặc chuyển sang đường thay thế có kiểm soát |
| Bất kỳ điểm nào nhưng vi phạm điều kiện bắt buộc | Không thực hiện thao tác hiện tại | Xử lý đúng nguyên nhân; không dùng điểm để bỏ qua |

“Tiếp tục” có thể chỉ là cho phép sang màn hình nhập mật khẩu mới. Nó không tự cấp phiên đăng nhập đầy đủ, cho phép chuyển tiền hoặc xóa toàn bộ yếu tố xác thực.

Xác minh bổ sung cần phù hợp với thứ người dùng còn có. Nếu người dùng mất điện thoại TOTP, yêu cầu nhập TOTP từ chính điện thoại đó không tạo ra đường phục hồi hữu ích. Có thể chuyển sang recovery code đã cấp trước, authenticator khác còn kiểm soát được hoặc quy trình thay thế phù hợp.

Hai mã gửi đến cùng một hộp thư vẫn phụ thuộc vào cùng một hộp thư. Gửi thêm OTP qua kênh đó không tạo ra hai bằng chứng độc lập.

OWASP khuyến nghị xem việc thay MFA là thao tác rủi ro cao, kiểm tra lại xác thực thay vì chỉ dựa vào phiên đang mở, và thông báo cho người dùng khi yếu tố thay đổi. [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

## 6. Ví dụ tính điểm và diễn giải quyết định

### Trường hợp A: Mất mật khẩu nhưng còn phương tiện khác

Người dùng dùng thiết bị quen, không có cảnh báo mạng, kênh không vừa thay, không có lần nhập sai gần đây và dữ liệu đầy đủ.

~~~text
R = 10 + 0 + 0 + 0 + 0 + 0 + 0 = 10
~~~

Hệ thống có thể tiếp tục đường tiêu chuẩn. Người dùng vẫn phải hoàn tất bằng chứng mà chính sách đặt lại mật khẩu yêu cầu. Nếu còn authenticator mạnh hợp lệ, ưu tiên sử dụng nó theo chính sách của dịch vụ.

### Trường hợp B: Mất toàn bộ authenticator và dùng máy mới

Thiết bị mới, mạng không đáng ngờ, kênh phục hồi không vừa thay, có bốn lần xác minh sai trong cửa sổ đo, không có thay đổi bảo mật khác.

~~~text
E = 15
C = 0
V = 10
H = 0
L = 15
U = 0

R = 10 + 15 + 0 + 10 + 0 + 15 + 0 = 50
~~~

Nhánh được đề xuất là xác minh bổ sung. Nếu không còn phương thức đủ mạnh nào khả dụng, hệ thống chuyển sang đường xử lý khác theo chính sách; không tự hạ yêu cầu để hoàn thành hồ sơ.

### Trường hợp C: Kênh vừa đổi và có dấu hiệu chiếm quyền

Thiết bị mới và mạng đáng ngờ; email phục hồi vừa đổi và kênh có cảnh báo; bảy lần xác minh sai; có thay đổi bảo mật gần đây; mất toàn bộ authenticator.

~~~text
E = min(25, 15 + 15) = 25
C = min(30, 20 + 30) = 30
V = 25
H = 20
L = 15
U = 0

R = min(100, 10 + 25 + 30 + 25 + 20 + 15) = 100
~~~

Nếu trạng thái bị chiếm quyền của kênh đã được xác nhận, điều kiện bắt buộc ngăn sử dụng kênh đó được áp dụng trước. Điểm 100 giúp xếp ưu tiên kiểm tra, còn lý do dừng đường hiện tại là kênh không còn phù hợp.

### Trường hợp D: Không lấy được dữ liệu

Các tín hiệu đã có không bất thường, nhưng nguồn lịch sử thay đổi bảo mật bắt buộc đang timeout.

~~~text
R = 10 + 15 = 25
dataComplete = false
~~~

Nhánh thiếu dữ liệu được áp dụng, không coi 25 là đủ để dùng một bước OTP thay thế mọi kiểm tra. Có thể thử lại có giới hạn hoặc chuyển sang quy trình khác; tránh chờ vô hạn.

## 7. Ví dụ Java: bộ định tuyến chính sách

Đoạn mã dưới đây chỉ minh họa cách tách điểm khỏi điều kiện bắt buộc. Nó không xác minh token, không thực hiện identity proofing và không thay đổi tài khoản. Đầu vào phải do máy chủ tạo sau khi chuẩn hóa dữ liệu.

~~~java
public final class RecoveryRiskPolicy {
    public enum Route {
        REJECT_CURRENT_PROOF,
        INCIDENT_REVIEW,
        RESTRICTED_CHANNEL_REVIEW,
        INCOMPLETE_DATA_REVIEW,
        PRIVILEGED_ACCOUNT_REVIEW,
        MANUAL_REVIEW,
        COLLECT_REQUIRED_PROOF,
        STEP_UP,
        CONTINUE_STANDARD_FLOW
    }

    public record Signals(
            boolean newDevice,
            boolean suspiciousNetwork,
            boolean recoveryChannelRecentlyChanged,
            boolean channelTakeoverWarning,
            int failedVerificationsInWindow,
            boolean recentSecurityChange,
            boolean allAuthenticatorsLost,
            boolean requiredDataComplete) {
        public Signals {
            if (failedVerificationsInWindow < 0) {
                throw new IllegalArgumentException("Negative failure count");
            }
        }
    }

    public record Gates(
            boolean currentProofInvalid,
            boolean confirmedAccountCompromise,
            boolean confirmedRecoveryChannelCompromise,
            boolean privilegedAccountRequiresReview,
            boolean minimumProofSatisfied) {}

    public record Decision(int score, Route route) {}

    public static int score(Signals s) {
        int environment = Math.min(25,
                (s.newDevice() ? 15 : 0)
                + (s.suspiciousNetwork() ? 15 : 0));
        int channel = Math.min(30,
                (s.recoveryChannelRecentlyChanged() ? 20 : 0)
                + (s.channelTakeoverWarning() ? 30 : 0));
        int velocity = s.failedVerificationsInWindow() >= 6 ? 25
                : s.failedVerificationsInWindow() >= 3 ? 10 : 0;
        int history = s.recentSecurityChange() ? 20 : 0;
        int loss = s.allAuthenticatorsLost() ? 15 : 0;
        int uncertainty = s.requiredDataComplete() ? 0 : 15;
        return Math.min(100,
                10 + environment + channel + velocity
                + history + loss + uncertainty);
    }

    public static Decision evaluate(Signals s, Gates g) {
        int risk = score(s);
        Route route;

        if (g.currentProofInvalid()) {
            route = Route.REJECT_CURRENT_PROOF;
        } else if (g.confirmedAccountCompromise()) {
            route = Route.INCIDENT_REVIEW;
        } else if (g.confirmedRecoveryChannelCompromise()) {
            route = Route.RESTRICTED_CHANNEL_REVIEW;
        } else if (!s.requiredDataComplete()) {
            route = Route.INCOMPLETE_DATA_REVIEW;
        } else if (g.privilegedAccountRequiresReview()) {
            route = Route.PRIVILEGED_ACCOUNT_REVIEW;
        } else if (risk >= 60) {
            route = Route.MANUAL_REVIEW;
        } else if (!g.minimumProofSatisfied()) {
            route = Route.COLLECT_REQUIRED_PROOF;
        } else if (risk >= 25) {
            route = Route.STEP_UP;
        } else {
            route = Route.CONTINUE_STANDARD_FLOW;
        }

        return new Decision(risk, route);
    }

    private RecoveryRiskPolicy() {}
}
~~~

Ví dụ sử dụng record yêu cầu Java 16 trở lên. Những nhánh “review” là kết quả định tuyến; một nhân viên hỗ trợ vẫn phải làm theo quy trình và lưu bằng chứng, không được tùy ý bỏ qua điều kiện.

Bộ điều phối bên ngoài cần quản lý việc đã hoàn thành step-up, phạm vi bằng chứng và chuyển trạng thái hồ sơ. Không gọi lặp evaluate rồi yêu cầu người dùng làm lại cùng một challenge mãi. Sau step-up, hệ thống kiểm tra bộ yêu cầu của nhánh tăng cường đã đạt hay chưa; điểm gốc có thể vẫn cao.

Nếu ưu tiên xử lý có nhiều điều kiện cùng lúc, cần ghi toàn bộ mã lý do liên quan trong audit. Route duy nhất trong ví dụ chỉ biểu diễn hành động tiếp theo.

## 8. Đánh giá theo vòng đời hồ sơ

~~~mermaid
flowchart TD
    A[Yêu cầu phục hồi] --> B[Tạo hồ sơ và chống lạm dụng]
    B --> C[Thu thập dữ liệu và đánh giá rủi ro]
    C --> D{Đường xử lý được phép}
    D --> E[Xác minh tiêu chuẩn]
    D --> F[Xác minh bổ sung]
    D --> G[Kiểm soát tăng cường hoặc tạm hoãn]
    E --> H[Đánh giá lại trước thay đổi]
    F --> H
    G --> H
    H --> I{Đủ bằng chứng và đủ điều kiện hiện tại?}
    I -->|Có| J[Thực hiện thay đổi trong giao dịch]
    I -->|Chưa| K[Thu thập thêm hoặc kết thúc hồ sơ]
    J --> L[Thông báo và kiểm soát phiên]
~~~

Các đường bị từ chối hoặc tạm hoãn chỉ được đến bước đánh giá lại sau khi nguyên nhân tương ứng được xử lý.

Đánh giá ít nhất khi tiếp nhận hồ sơ, sau khi có bằng chứng quan trọng mới và ngay trước thay đổi nhạy cảm. Giữa hai thời điểm, người dùng có thể báo bị chiếm tài khoản, một kênh có thể bị đổi hoặc hồ sơ có thể hết hạn.

Một snapshot đánh giá nên có:

~~~text
caseId
evaluatedAt
validUntil
policyVersion
accountSecurityRevision
recoveryChannelRevision
score
reasonCodes
dataQuality
requiredProofs
route
~~~

Đây là bản ghi nội bộ gắn với hồ sơ. Không gửi toàn bộ snapshot cho client như một giấy phép có thể tự sửa.

Ví dụ, yêu cầu được đánh giá lúc 10:00, nhưng lúc 10:02 tài khoản bị ghi nhận thay đổi email. Khi người dùng nộp mã lúc 10:03, server kiểm tra revision và đánh giá lại thay vì dùng kết quả 10:00. Nếu dữ liệu bắt buộc lúc đó không lấy được, áp dụng nhánh thiếu dữ liệu.

### 8.1. Điểm số không ngăn được race condition

Trước lúc hoàn tất, một giao dịch hoặc cơ chế kiểm soát đồng thời tương đương cần bảo đảm:

1. Hồ sơ còn hiệu lực và chưa hoàn tất.
2. Bằng chứng gắn với đúng tài khoản, đúng hồ sơ và đúng mục đích.
3. Điều kiện hiện tại vẫn phù hợp với quyết định.
4. Token dùng một lần được đánh dấu đã dùng cùng với thay đổi credential.
5. Trạng thái bảo mật và yêu cầu kiểm soát phiên được cập nhật nhất quán.

Có thể dùng kiểm tra revision để phát hiện thay đổi cạnh tranh. Khi revision khác dự kiến, tải lại trạng thái và đánh giá lại, không âm thầm áp dụng quyết định cũ.

Nếu thông báo hoặc vô hiệu phiên nằm ở hệ thống khác, lưu sự kiện bền vững cùng giao dịch, chẳng hạn transactional outbox, rồi xử lý có retry và tính idempotent. Việc hạn chế quyền phải có hiệu lực phù hợp với yêu cầu an toàn trước khi tài khoản được sử dụng đầy đủ.

## 9. Giữ các kiểm soát nền tảng ở mọi mức điểm

Điểm thấp không cho phép bỏ qua tính toàn vẹn của token hoặc biện pháp chống lạm dụng. OWASP khuyến nghị token reset được tạo ngẫu nhiên bằng thuật toán mật mã, đủ khó đoán, lưu an toàn, có hạn dùng và chỉ dùng một lần; phản hồi khởi tạo cần nhất quán để hạn chế dò tài khoản. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Đối với thiết kế trong bài này:

- Chỉ cho phép token thực hiện mục đích đã gắn, không dùng token đặt lại mật khẩu làm quyền gỡ MFA.
- Giới hạn thử mã và gửi lại theo nhiều chiều; rate limit chỉ theo IP dễ ảnh hưởng người dùng chung mạng và có thể bị né bằng nhiều IP.
- Giữ phản hồi công khai ở mức cần thiết cho người dùng; không trả trọng số chi tiết, kết quả tra cứu tài khoản hoặc tín hiệu gian lận nội bộ.
- Dừng hoặc làm chậm yêu cầu đáng ngờ theo phạm vi phù hợp; không khóa đăng nhập hợp lệ chỉ vì ai đó gửi nhiều yêu cầu reset.
- Sau thay đổi, áp dụng chính sách về phiên và refresh token theo loại sự cố; sự cố chiếm quyền cần đường xử lý mạnh hơn một lần quên mật khẩu thông thường.
- Dùng phiên phục hồi với quyền hẹp khi cần, và yêu cầu xác thực phù hợp trước thao tác nhạy cảm tiếp theo.

NIST SP 800-63B-4 mô tả các nhóm phương thức phục hồi và yêu cầu thông báo khi recovery diễn ra. Lựa chọn cụ thể vẫn phải phù hợp với mức bảo đảm và hoàn cảnh của tài khoản. [NIST SP 800-63B-4, mục 4.2](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery)

## 10. Hiệu chỉnh mô hình bằng dữ liệu phù hợp

Bắt đầu bằng chạy quan sát: tính điểm và ghi quyết định đề xuất trong khi quy trình đang có vẫn quyết định kết quả. Sau đó đánh giá theo từng loại phục hồi, quyền tài khoản và nhóm người dùng.

Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tỷ lệ chiếm đoạt sau phục hồi | Đánh giá sự cố được xác nhận trong cửa sổ quan sát đã định |
| Tỷ lệ hồ sơ hợp lệ bị chặn nhầm | Đo mức ảnh hưởng tới chủ tài khoản thực |
| Tỷ lệ hoàn thành và bỏ cuộc | Phát hiện đường phục hồi quá khó hoặc không khả dụng |
| Thời gian hoàn tất và khối lượng hỗ trợ | Đánh giá chi phí vận hành |
| Tỷ lệ thiếu dữ liệu theo nguồn | Nhận diện timeout hoặc độ phủ thấp của tín hiệu |
| Phân bố điểm theo phiên bản | Phát hiện thay đổi bất thường khi triển khai chính sách mới |

Một yêu cầu đã hoàn thành không tự động là nhãn “hợp lệ”. Chủ tài khoản có thể phát hiện chiếm đoạt nhiều ngày sau. Yêu cầu bị chặn cũng thường thiếu nhãn kết quả vì không có cơ hội hoàn tất; dữ liệu chỉ từ hồ sơ được duyệt có thiên lệch chọn mẫu.

Nếu sử dụng mô hình học máy, chia dữ liệu theo thời gian và kiểm soát việc cùng tài khoản xuất hiện ở cả tập học lẫn tập đánh giá. Không dùng sự kiện chỉ có sau quyết định làm đặc trưng đầu vào.

Xem riêng người thường xuyên đi lại, người dùng VPN, thiết bị hỗ trợ tiếp cận và người mới chưa có lịch sử. Thiếu lịch sử không phải bằng chứng gian lận. Ngưỡng cần cân bằng khả năng phát hiện với khả năng phục hồi hợp lệ, đồng thời giữ nguyên điều kiện bắt buộc của từng thao tác.

Trong quá trình hiệu chỉnh, tăng độ khó ở đường self-service cần đi kèm đường thay thế thực sự hoạt động; chuyển mọi trường hợp sang hỗ trợ thủ công không bảo đảm an toàn nếu bộ phận hỗ trợ thiếu quy trình.

## 11. Audit, quyền riêng tư và khả năng giải thích

Bản ghi quyết định cần đủ để trả lời ai hoặc thành phần nào đưa ra quyết định, dựa trên dữ liệu tại thời điểm nào, dùng chính sách phiên bản nào và vì sao.

Có thể ghi các mã lý do như NEW_DEVICE, RECENT_CHANNEL_CHANGE, RECOVERY_FAILURE_BURST hoặc REQUIRED_SIGNAL_UNAVAILABLE. Với điều chỉnh thủ công, lưu danh tính người duyệt, lý do, bằng chứng được tham chiếu và phạm vi ngoại lệ được phép.

Không ghi mật khẩu, OTP, recovery code hay token reset vào log. Dữ liệu vị trí và thiết bị cần có mục đích sử dụng, giới hạn truy cập và thời hạn lưu rõ ràng. Tránh thu thập fingerprint quá chi tiết chỉ vì có thể thu thập.

Nếu bản ghi lịch sử cho biết tài khoản đang bị chiếm quyền, không cập nhật thiết bị hoặc hành vi của giai đoạn đó thành baseline đáng tin. Chỉ thay baseline theo quy trình đã xác định để giảm nguy cơ kẻ tấn công làm “quen hóa” hành vi của mình.

## 12. Những sai lầm dễ biến recovery thành đường chiếm tài khoản

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Cho reset khi điểm dưới ngưỡng dù chưa đủ bằng chứng | Bối cảnh quen bị coi là danh tính | Giữ cổng bằng chứng độc lập |
| Cộng rất nhiều tín hiệu cùng nguyên nhân | Điểm tăng giả tạo | Nhóm tín hiệu và xem tương quan |
| Cho điểm tốt bù điểm cảnh báo nghiêm trọng | Một dấu hiệu quen che mất sự cố | Đặt điều kiện bắt buộc ngoài điểm |
| Timeout được đổi thành điểm 0 | Lỗi hạ tầng làm giảm bảo vệ | Biểu diễn dữ liệu không biết |
| Dùng kết quả cũ xuyên suốt hồ sơ | Bỏ qua thay đổi xảy ra sau đánh giá | Kiểm tra revision và đánh giá lại |
| Hạ yêu cầu vì người dùng không còn yếu tố | Tạo đường bỏ qua MFA | Cung cấp quy trình thay thế đã định |
| Gửi nhiều mã tới cùng kênh rồi coi là step-up | Bằng chứng vẫn có chung điểm thất bại | Kiểm tra tính độc lập của phương thức |
| Khóa cả tài khoản do request reset bất thường | Kẻ tấn công gây từ chối dịch vụ | Giới hạn đúng yêu cầu và đường phục hồi |
| Nhân viên hỗ trợ có thể bỏ qua mọi gate | Quy trình thủ công trở thành cửa hậu | Ràng buộc thẩm quyền, bằng chứng và audit |

Điểm rủi ro có ích khi nó dẫn đến hành động rõ ràng, giải thích được và có đường xử lý dữ liệu thiếu. Điều kiện hoàn tất phục hồi vẫn là đủ bằng chứng, đúng phạm vi quyền, trạng thái hiện tại hợp lệ và thay đổi được thực hiện nhất quán.
