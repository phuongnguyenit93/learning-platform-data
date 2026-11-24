# Progressive friction

## 1. Progressive friction là gì?

**Progressive friction** là cách tăng dần trở ngại đối với một thao tác khi bằng chứng rủi ro hoặc mức thiệt hại có thể gây ra tăng lên. Trở ngại có thể là giảm tốc độ, thời gian chờ, xác minh con người, xác thực lại, yêu cầu phê duyệt hoặc tạm giữ yêu cầu để xem xét.

Mục đích là làm cho hành vi lạm dụng khó mở rộng quy mô, đồng thời giữ luồng thông thường đủ thuận tiện cho người dùng hợp lệ. Một tài khoản sử dụng chức năng đúng định dạng, có đăng nhập và gọi API thành công vẫn có thể gây hại nếu liên tục giữ chỗ, thử mã khuyến mại hoặc tạo yêu cầu hoàn tiền.

Trong chương **Abuse Controls** của module bảo vệ logic nghiệp vụ, progressive friction nằm giữa việc phát hiện dấu hiệu lạm dụng và quyết định cho thực hiện hành động. Cơ chế này phải kết hợp với các quy tắc nghiệp vụ, state machine, quyền theo đối tượng, transaction và idempotency.

Sau bài học, bạn cần có khả năng:

- Xác định thao tác nào cần tăng kiểm soát và thiệt hại nào cần ngăn chặn.
- Thiết kế các mức kiểm soát có điều kiện tăng, giảm và hết hạn rõ ràng.
- Ràng buộc kết quả xác minh với đúng người dùng, đối tượng và nội dung thao tác.
- Giữ nguyên các business invariants khi có retry, yêu cầu song song hoặc dịch vụ phụ trợ gặp lỗi.
- Đánh giá đồng thời hiệu quả giảm lạm dụng và chi phí gây ra cho người dùng hợp lệ.

## 2. Bắt đầu từ thiệt hại nghiệp vụ

Một API có thể hoàn toàn đúng về cấu trúc HTTP nhưng vẫn cho phép khai thác quy trình kinh doanh. OWASP API6:2023 mô tả rủi ro khi những luồng nghiệp vụ nhạy cảm bị sử dụng quá mức, chẳng hạn mua gom hàng, giữ chỗ hoặc khai thác chương trình giới thiệu. Vì vậy, cần xác định luồng và tác động trước khi chọn biện pháp kỹ thuật. [OWASP API6:2023 — Unrestricted Access to Sensitive Business Flows](https://api-security.owasp.org/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/).

Các tình huống dưới đây là ví dụ thiết kế cho bài học:

| Luồng nghiệp vụ | Hành vi gây hại | Friction có thể áp dụng | Quy tắc luôn phải giữ |
| --- | --- | --- | --- |
| Áp mã giảm giá | Tự động thử nhiều mã trên nhiều giỏ hàng | Giảm tốc độ, xác minh con người, tạm dừng thử mã | Đúng điều kiện chiến dịch; không vượt ngân sách và số lượt hưởng |
| Giữ chỗ | Liên tục tạo rồi bỏ giữ chỗ | Giới hạn số lượt giữ đang hoạt động, hàng đợi, thời gian chờ | Không bán vượt khả năng phục vụ; giữ chỗ phải hết hạn |
| Hoàn tiền | Chia nhỏ nhiều yêu cầu để tránh ngưỡng kiểm soát | Xác thực lại, giữ để duyệt, kiểm soát tổng theo kỳ | Tổng hoàn tiền không vượt khoản có thể hoàn; không tự duyệt nếu bị cấm |
| Đổi thông tin nhận tiền | Tài khoản bị chiếm quyền thay đích nhận | Xác thực lại bằng yếu tố đã đăng ký, xác nhận nội dung thay đổi | Chỉ chủ thể có quyền mới được đổi; mọi thay đổi có dấu vết |
| Phê duyệt đơn | Người tạo yêu cầu tìm cách tự duyệt | Yêu cầu đúng người phê duyệt, chuyển xử lý thủ công | Tách biệt người tạo và người duyệt theo chính sách |

Không phải dòng nào cũng cần CAPTCHA. Nếu rủi ro là người đã đăng nhập đổi tài khoản nhận tiền, bài toán chính là độ tin cậy của xác thực và nội dung giao dịch. Nếu rủi ro là tự động giữ hàng hàng loạt, cần giới hạn tài nguyên và số thao tác ngoài việc xác minh người dùng.

### 2.1. Phân biệt điều kiện bắt buộc và kiểm soát thích ứng

**Điều kiện bắt buộc** xác định hành động có hợp lệ hay không:

- Người gọi có quyền trên chính đơn hàng đang thao tác.
- Giá và số tiền được tính từ dữ liệu đáng tin cậy ở máy chủ.
- Chuyển trạng thái nằm trong state machine cho phép.
- Người phê duyệt đáp ứng vai trò và yêu cầu tách biệt nhiệm vụ.
- Ràng buộc số lượng, ngân sách, số dư và tính duy nhất vẫn thỏa mãn.

**Kiểm soát thích ứng** xác định cần thêm bằng chứng hoặc giảm khả năng thực hiện hành động đến mức nào trong một trường hợp cụ thể.

Người dùng vượt qua CAPTCHA vẫn không có quyền sửa đơn của người khác. Xác thực lại thành công vẫn không cho phép hoàn tiền nhiều hơn số đã thanh toán. Người tạo yêu cầu nhập đúng OTP vẫn không trở thành người duyệt độc lập.

Có thể biểu diễn điều kiện thực thi:

~~~text
được thực thi =
    đã xác thực theo yêu cầu
    AND được phép trên đối tượng
    AND trạng thái và dữ liệu nghiệp vụ hợp lệ
    AND còn hạn mức bắt buộc
    AND đáp ứng các kiểm soát thích ứng hiện tại
~~~

Giảm friction chỉ được giảm yêu cầu bổ sung mà chính sách cho phép giảm; các điều kiện bắt buộc vẫn được kiểm tra.

## 3. Thiết kế thang kiểm soát

Một thang minh họa gồm năm mức:

| Mức | Tình huống thường gặp | Cách xử lý |
| --- | --- | --- |
| L0 — Thông thường | Hành vi nằm trong mẫu sử dụng dự kiến | Cho tiếp tục sau các kiểm tra cơ sở |
| L1 — Giảm tốc độ | Tần suất tăng hoặc có dấu hiệu thăm dò | Giảm tốc độ, giới hạn burst, đặt thời điểm thử lại |
| L2 — Xác minh bổ sung | Có bằng chứng tự động hóa đáng chú ý | Yêu cầu thử thách phù hợp; vẫn giữ các giới hạn tốc độ |
| L3 — Bảo đảm danh tính hoặc ý định | Thao tác nhạy cảm hoặc có dấu hiệu chiếm tài khoản | Xác thực lại, xác nhận nội dung; yêu cầu người có thẩm quyền nếu nghiệp vụ quy định |
| L4 — Tạm dừng hoặc giữ để duyệt | Bằng chứng rủi ro cao hoặc thiệt hại tiềm tàng lớn | Chặn thực thi trong thời hạn xác định hoặc tạo hồ sơ chờ duyệt |

Đây là mô hình để suy nghĩ, không phải danh sách phải đi qua lần lượt. Một yêu cầu đổi thông tin nhận tiền có thể cần L3 ngay từ lần đầu. Một yêu cầu rõ ràng vi phạm quyền phải bị từ chối ngay, không cần cho người gọi cơ hội vượt qua các mức thấp hơn.

Các biện pháp cũng không hoàn toàn thay thế nhau:

- Xác thực mạnh chứng minh mức tin cậy của người điều khiển tài khoản, nhưng tài khoản đó vẫn có thể tự động lạm dụng khuyến mại.
- CAPTCHA cung cấp một loại bằng chứng về tương tác, nhưng không chứng minh quyền sở hữu đơn hàng.
- Duyệt thủ công có thể phù hợp với hoàn tiền giá trị lớn, nhưng dễ quá tải nếu mọi yêu cầu đều bị đẩy vào hàng chờ.
- Thời gian chờ làm giảm tốc độ theo một phạm vi nhất định, nhưng có thể bị phân tán qua nhiều tài khoản nếu thiếu kiểm soát tổng.

OWASP xem CAPTCHA là một lớp phòng vệ bổ sung vì có thể bị giải tự động hoặc thuê người giải. Hướng dẫn xác thực thích ứng cũng dùng ngữ cảnh để quyết định mức xác minh, thay vì coi IP hay dấu vết thiết bị là thông tin xác thực. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

## 4. Chọn tín hiệu rủi ro đúng phạm vi

Không nên bắt đầu bằng câu hỏi “IP này đã gọi bao nhiêu lần?”. Hãy bắt đầu bằng “hành động kinh doanh nào đang bị sử dụng và ai hoặc tài nguyên nào chịu tác động?”.

### 4.1. Các nhóm tín hiệu

| Nhóm | Ví dụ | Điều cần tránh |
| --- | --- | --- |
| Tốc độ | Số mã khác nhau được thử; số lần tạo giữ chỗ theo cửa sổ | Đếm mọi retry như một giao dịch kinh doanh mới |
| Mẫu kết quả | Tỷ lệ thất bại, liên tục đổi mã, nhiều bước kết thúc thất bại giống nhau | Đồng nhất thao tác sai do khó sử dụng với hành vi xấu |
| Ngữ cảnh tài khoản | Thiết bị mới kết hợp thay đổi nhạy cảm; nhiều phiên bất thường | Mặc định tài khoản lâu năm luôn an toàn |
| Quan hệ với tài nguyên | Nhiều tài khoản cùng giữ một nhóm hàng hoặc nhắm cùng đối tượng | Để một người lạ tạo yêu cầu giả rồi khóa toàn bộ chủ tài nguyên |
| Mức tác động | Giá trị giao dịch, số tài nguyên bị giữ, tổng tiền hoàn theo kỳ | Chỉ xét từng request nhỏ và bỏ qua tổng tích lũy |
| Hạ tầng | Đặc điểm mạng, độ tin cậy của dữ liệu thiết bị, proxy đã được xác minh | Coi mạng dùng chung, VPN hoặc công cụ hỗ trợ tiếp cận là bằng chứng kết luận |

Tín hiệu có mức tin cậy khác nhau. Một trường `riskScore` do trình duyệt gửi lên không phải điểm rủi ro đáng tin cậy. IP từ `X-Forwarded-For` chỉ có ý nghĩa sau khi xác định đúng chuỗi proxy được tin cậy. Cookie thiết bị chưa được bảo vệ có thể bị tạo lại tùy ý.

Dữ liệu thiếu cũng cần có ý nghĩa riêng: “chưa biết” không đồng nghĩa “an toàn”, nhưng cũng không tự động đồng nghĩa “gian lận”.

### 4.2. Kết hợp nhiều khóa kiểm soát

Đối với áp mã giảm giá, có thể cần đồng thời:

~~~text
tenant + account + action
tenant + account + campaign
tenant + cart + action
tenant + campaign + aggregate-impact
network-signal + action
~~~

Khóa theo tài khoản giảm hiệu quả đổi IP. Khóa theo chiến dịch giúp thấy tổng thiệt hại. Khóa theo giỏ hàng phát hiện việc xoay tài khoản để tác động cùng một đối tượng. Tín hiệu mạng bổ sung ngữ cảnh khi chưa có tài khoản đáng tin cậy.

Một hạn mức toàn chiến dịch không được biến thành nút khóa mọi khách hàng chỉ vì một nguồn tạo nhiều request. Cần phân biệt tín hiệu cảnh báo tổng với điều kiện chặn một chủ thể, có giới hạn theo phạm vi hẹp và cơ chế bảo vệ năng lực phục vụ chung.

### 4.3. Điểm số là công cụ ra quyết định

Ví dụ minh họa, không phải ngưỡng triển khai mặc định:

| Tín hiệu | Điểm cộng có giới hạn |
| --- | ---: |
| Tốc độ thử mã vượt mẫu nền của nhóm sử dụng | +20 |
| Thử nhiều mã khác nhau với tỷ lệ thất bại cao | +25 |
| Nhiều tài khoản có quan hệ đáng chú ý cùng nhắm một chiến dịch | +25 |
| Ngữ cảnh mới kết hợp hành động có tác động lớn | +15 |
| Tiếp tục gửi yêu cầu trong thời gian chờ đã áp dụng | +15 |

Trong ví dụ, mỗi nhóm tín hiệu chỉ đóng góp trong giới hạn đã đặt; tổng được chặn trong khoảng 0–100. Không cộng điểm không giới hạn cho từng request rồi vô tình tạo lệnh cấm kéo dài vô tận.

Một ánh xạ có thể là:

~~~text
0–19:   xử lý thông thường
20–39:  giảm tốc độ
40–59:  giảm tốc độ + thử thách nếu có dấu hiệu tự động hóa
60–79:  tăng bảo đảm danh tính/ý định theo loại thao tác
80–100: tạm giữ hoặc từ chối tạm thời theo chính sách
~~~

Điểm 70 không mặc nhiên là xác suất gian lận 70%. Nếu chưa hiệu chỉnh bằng dữ liệu phù hợp, đây chỉ là thứ tự ưu tiên do mô hình hoặc tập quy tắc tạo ra.

Các ngưỡng phải được đánh giá theo luồng nghiệp vụ, nhóm khách hàng và thiệt hại. Hành động bắt buộc xác thực lại vẫn cần xác thực lại khi điểm bằng 0.

## 5. Tăng nhanh, giảm có điều kiện

Nếu mỗi request độc lập quyết định mức kiểm soát, người dùng có thể bị chuyển qua lại giữa “được phép” và “phải xác minh”. Chính sách nên có trạng thái và điều kiện chuyển rõ ràng.

~~~mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Throttled: Tần suất hoặc rủi ro tăng
    Throttled --> Challenged: Có dấu hiệu tự động hóa
    Challenged --> Restricted: Thất bại lặp lại hoặc tác động lớn
    Normal --> Restricted: Bằng chứng nghiêm trọng
    Challenged --> Throttled: Bằng chứng hợp lệ, giới hạn vẫn giữ
    Restricted --> Throttled: Hết thời hạn và đánh giá lại
    Throttled --> Normal: Cửa sổ sạch và rủi ro giảm
~~~

Đây là trạng thái kiểm soát lạm dụng, tách biệt với trạng thái nghiệp vụ như `DRAFT`, `APPROVED`, `PAID` hoặc `REFUNDED`. Thoát trạng thái hạn chế không tự chuyển một yêu cầu nghiệp vụ sang đã phê duyệt.

### 5.1. Hysteresis và suy giảm tín hiệu

**Hysteresis** là dùng điều kiện vào và ra khác nhau để tránh dao động. Ví dụ, vào chế độ thử thách khi điểm đạt 40, nhưng chỉ trở lại bình thường sau khi điểm dưới 25 trong một cửa sổ ổn định. Đây là ví dụ riêng về cách giảm mức, không thay thế kiểm soát bắt buộc của từng thao tác.

Các tín hiệu ngắn hạn có thể suy giảm theo thời gian; bằng chứng vi phạm đã xác nhận có thể cần thời hạn xử lý khác. Cần ghi rõ:

- Tín hiệu nào hết hạn sau cửa sổ nào.
- Một lần xác minh thành công gỡ được yêu cầu nào.
- Thời điểm nào được thử lại.
- Ai có quyền mở hạn chế thủ công và trong phạm vi nào.

Đăng xuất, xóa cookie hoặc tạo idempotency key mới không được tự xóa lịch sử theo tài khoản. Ngược lại, người dùng cũng cần một lối khôi phục khả thi khi mạng thay đổi hoặc có đánh giá nhầm.

### 5.2. Backoff có giới hạn

Một công thức minh họa:

~~~text
delay(n) = min(cap, base × 2^min(n, exponentLimit)) + boundedJitter
~~~

Trong đó, `n` là số sự kiện vi phạm đủ điều kiện trong cửa sổ đang xét, không phải số lần giao diện tự retry vì mất mạng. Cần chặn số mũ để tránh tràn số và chặn tổng thời gian chờ.

Thời điểm `nextAllowedAt` phải do máy chủ thực thi. Đồng hồ đếm ngược và nút bị vô hiệu hóa ở trình duyệt chỉ giúp trình bày.

Không dùng `Thread.sleep` trên mỗi request để giữ kết nối chờ. Có thể từ chối sớm với thời điểm thử lại hoặc dùng hàng đợi có giới hạn, cơ chế hết hạn và kiểm tra lại điều kiện khi thực thi.

## 6. Tình huống xuyên suốt: áp mã giảm giá

Giả sử cửa hàng có chức năng áp mã vào giỏ hàng. Các quy tắc nghiệp vụ gồm:

1. Người gọi phải có quyền sửa giỏ.
2. Giỏ còn ở trạng thái cho phép thay đổi.
3. Giá, điều kiện khuyến mại và mức giảm được tính tại máy chủ.
4. Một tài khoản chỉ được hưởng quyền lợi theo số lần chiến dịch cho phép.
5. Ngân sách chiến dịch không bị chi vượt do yêu cầu đồng thời.
6. Retry cùng một lệnh không tạo thêm quyền lợi.

Kẻ lạm dụng có thể thử nhiều mã, thay đổi IP, tạo nhiều phiên hoặc gửi đồng thời. Progressive friction bổ sung chi phí thử mã và phát hiện mẫu hành vi; transaction và ràng buộc dữ liệu vẫn chịu trách nhiệm bảo vệ ngân sách.

Một diễn biến hợp lý:

- Tài khoản thử mã đầu tiên trong nhịp sử dụng bình thường: xử lý sau các kiểm tra cơ sở.
- Nhiều mã khác nhau thất bại trong cửa sổ ngắn: giảm tốc độ và lưu thời điểm thử lại.
- Có bằng chứng tự động hóa: yêu cầu xác minh cho đúng lần thử.
- Người dùng hoàn thành xác minh: được đánh giá lại; tốc độ và hạn mức chiến dịch vẫn giữ.
- Lạm dụng tiếp diễn hoặc xuất hiện cụm tài khoản liên quan: hạn chế theo phạm vi phù hợp hoặc giữ để xem xét.
- Yêu cầu sai quyền hoặc giỏ đã chốt: từ chối theo quy tắc nghiệp vụ, kể cả đã xác minh.

Không nên cấp thêm lượt thử không giới hạn sau mỗi CAPTCHA thành công. Nếu một lần giải mở khóa vô số lần thử, chi phí xác minh có thể được chia nhỏ cho toàn bộ đợt dò mã.

## 7. Đặt điểm thực thi tại máy chủ

~~~mermaid
flowchart TD
    A[Yêu cầu web, mobile hoặc API] --> B[Kiểm soát lưu lượng thô]
    B --> C[Xác thực, kiểm tra cấu trúc và quyền]
    C --> D[Nhận diện lệnh và đối tượng nghiệp vụ]
    D --> E[Đánh giá rủi ro và chính sách]
    E --> F{Đủ điều kiện tiếp tục?}
    F -->|Chưa đủ| G[Trả yêu cầu xác minh, thời gian chờ hoặc trạng thái giữ]
    F -->|Đủ| H[Transaction thực thi]
    H --> I[Kiểm tra lại trạng thái, hạn mức, grant và idempotency]
    I --> J[Ghi thay đổi, kết quả và outbox nếu cần]
~~~

Gateway phù hợp với giới hạn lưu lượng và các tín hiệu thô. Service nghiệp vụ biết tài khoản có quyền trên giỏ nào, chiến dịch nào đang bị tác động và tiền có được phép thay đổi hay không. Vì vậy, không thể chỉ đặt một CAPTCHA ở trang giao diện rồi xem nghiệp vụ đã được bảo vệ.

Cần bao phủ mọi đường đi có cùng tác động: website, ứng dụng di động, phiên bản API cũ, endpoint hàng loạt, tác vụ nền và công cụ vận hành. Tài khoản máy có cơ chế phù hợp như workload identity, scope và hạn mức được cấp rõ ràng; không bỏ kiểm soát chỉ vì không thể hiện CAPTCHA.

Các kiểm tra sơ bộ giúp từ chối sớm. Điều kiện có thể thay đổi, như trạng thái giỏ hoặc ngân sách, cần được kiểm tra lại tại điểm ghi với mức cô lập, khóa hoặc cập nhật có điều kiện phù hợp.

## 8. Thử thách phải gắn với đúng thao tác

Một thuộc tính `captchaPassed=true` do client gửi lên không đủ làm bằng chứng. Máy chủ cần kiểm tra kết quả với bộ xác minh đáng tin cậy, kiểm tra phạm vi và quản lý vòng đời của quyền được cấp sau xác minh.

### 8.1. Mô hình challenge và grant

- **Challenge** là yêu cầu hoàn thành một bước xác minh.
- **Grant** là bằng chứng phía máy chủ cho phép một lần tiếp tục trong phạm vi xác định sau khi challenge được xác minh thành công.

Một grant cho áp mã có thể gắn với:

~~~json
{
  "grantId": "opaque-random-id",
  "tenantId": "shop-a",
  "subjectId": "account-42",
  "sessionBinding": "server-session-reference",
  "operation": "APPLY_COUPON",
  "resourceId": "cart-815",
  "commandId": "server-command-id",
  "requestDigest": "digest-of-canonical-command",
  "resourceVersion": 12,
  "challengeType": "HUMAN_CHECK",
  "policyVersion": "coupon-abuse-v3",
  "expiresAt": "2026-11-22T10:05:00Z",
  "maxUses": 1
}
~~~

Đây là dữ liệu minh họa phía máy chủ. API có thể chỉ trả một tham chiếu mờ thay vì công khai toàn bộ cấu trúc. Hạn hết hiệu lực và mã định danh trong ví dụ không phải cấu hình mặc định.

`requestDigest` cần được tính từ dạng chuẩn hóa của các trường có ý nghĩa: loại hành động, giỏ, mã khuyến mại, phiên bản dữ liệu liên quan. Máy chủ tự tạo hoặc tự tính lại thông tin này, không tin digest do client khai báo. Digest giúp ràng buộc nội dung; bản thân digest không phải bí mật xác thực.

Nếu client thay mã, đổi giỏ hoặc nội dung có ý nghĩa sau xác minh, grant cũ không còn đủ điều kiện cho lệnh mới. Nếu phiên bản giá hoặc giỏ thay đổi, cần đánh giá lại và có thể yêu cầu xác nhận mới.

OWASP khuyến nghị thực thi xác minh giao dịch tại máy chủ, bảo vệ dữ liệu giao dịch khỏi thay đổi, kiểm soát thứ tự bước và giới hạn thời gian sử dụng bằng chứng. Với bằng chứng dùng một lần, trạng thái đã sử dụng cũng cần được kiểm tra và cập nhật nguyên tử để chống phát lại. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

### 8.2. Xác minh thành công không xóa mọi loại rủi ro

Grant giải CAPTCHA chỉ đáp ứng yêu cầu về thử thách đó. Nó không thay thế grant xác thực lại, không tăng quyền và không đặt toàn bộ điểm rủi ro về 0.

Nếu chính sách yêu cầu xác thực lại, máy chủ phải kiểm tra độ mới, phương thức và sự gắn kết với phiên hoặc thao tác. Với xác nhận giao dịch, người dùng cần thấy nội dung quan trọng đang đồng ý. Một lần đăng nhập thành công trước đó không mặc nhiên chứng minh ý định đối với mọi giao dịch phát sinh sau đó.

Ngay trước khi thực thi, hệ thống cần xác nhận grant vẫn phù hợp với yêu cầu hiện tại. Khi chính sách đổi, phải có quy tắc chấp nhận hoặc vô hiệu hóa phiên bản cũ; không được lặng lẽ dùng một grant yếu hơn yêu cầu mới.

### 8.3. Chống phát lại trên nhiều instance

Nếu grant có thể dùng một lần, hai instance phải cùng nhìn thấy trạng thái đã dùng. Mẫu `read unused → execute → mark used` không có bảo vệ đồng thời sẽ có race condition.

Một cập nhật có điều kiện minh họa:

~~~sql
UPDATE challenge_grant
SET used_by_command_id = :command_id,
    used_at = :server_now
WHERE grant_id = :grant_id
  AND tenant_id = :tenant_id
  AND subject_id = :subject_id
  AND command_id = :command_id
  AND request_digest = :request_digest
  AND expires_at > :server_now
  AND used_by_command_id IS NULL;
~~~

Máy chủ yêu cầu đúng một bản ghi được cập nhật. Đây chỉ là phần tiêu thụ grant; các ràng buộc phiên, đối tượng, phiên bản và chính sách vẫn phải được kiểm tra theo thiết kế.

Nếu grant và dữ liệu nghiệp vụ cùng một cơ sở dữ liệu, có thể tiêu thụ grant trong cùng transaction với thay đổi nghiệp vụ. Khi rollback, cả hai cùng rollback. Nếu dùng các kho khác nhau, một lệnh cập nhật nguyên tử ở kho grant không tự tạo ra transaction xuyên hệ thống; cần mô hình reservation, trạng thái lệnh và phục hồi đã thiết kế rõ.

## 9. Phối hợp với idempotency và transaction

Progressive friction xử lý mức kiểm soát; idempotency xử lý ngữ nghĩa retry; transaction và ràng buộc dữ liệu bảo vệ tính nhất quán. Ba phần cần phối hợp.

### 9.1. Tách ngân sách request và quyền lợi nghiệp vụ

**Ngân sách request** hạn chế việc tiêu thụ CPU, kết nối, bộ xác minh và năng lực dịch vụ. Mọi request, kể cả retry, vẫn có thể chịu giới hạn thô ở lớp này.

**Ngân sách nghiệp vụ** theo dõi số lần thử có ý nghĩa, số lệnh mới, số lượt hưởng hoặc số tiền đã sử dụng. Một retry đã được nhận diện đúng không tự tạo thêm quyền lợi hay lặp lại tác động nghiệp vụ.

Ví dụ:

| Trường hợp | Cách hiểu |
| --- | --- |
| Cùng khóa, cùng payload, lệnh đã thành công | Trả kết quả đã lưu sau khi kiểm tra quyền đọc kết quả; không trừ ngân sách chiến dịch lần nữa |
| Cùng khóa, payload khác | Xung đột; không coi là lệnh mới hợp lệ |
| Cùng khóa, lệnh đang chạy | Trả trạng thái đang xử lý hoặc xử lý xung đột theo giao thức đã công bố |
| Khóa mới, cùng ý định hưởng quyền lợi đã dùng | Vẫn bị ràng buộc bởi invariant và tính duy nhất trong dữ liệu |
| Tạo vô số khóa mới | Không làm mất lịch sử theo tài khoản, giỏ hoặc chiến dịch |

Khóa idempotency phải được gắn phạm vi với tenant, chủ thể và hành động. Thời hạn lưu kết quả phải phù hợp với cửa sổ retry và cơ chế chống trùng nghiệp vụ. Không coi khóa do client chọn là một hạn mức chống lạm dụng.

### 9.2. Thứ tự xử lý một lệnh

Một luồng minh họa:

~~~text
1. Xác thực và xác định tenant từ ngữ cảnh đáng tin cậy.
2. Kiểm tra quyền trên giỏ; chuẩn hóa lệnh và tính digest.
3. Tìm hoặc nhận quyền xử lý command theo khóa idempotency.
4. Nếu đã có kết quả cuối cùng cùng digest:
   kiểm tra quyền xem kết quả và trả kết quả đã lưu.
5. Nếu chưa hoàn tất:
   đánh giá rủi ro, hạn mức và các bằng chứng cần có.
6. Nếu cần challenge:
   lưu/tiếp tục trạng thái WAITING_FOR_VERIFICATION, chưa tạo quyền lợi.
7. Sau khi có bằng chứng, bắt đầu transaction ngắn:
   - khóa/kiểm tra command và đối tượng theo thứ tự nhất quán;
   - nếu command đã hoàn tất, dùng kết quả đã lưu;
   - kiểm tra lại quyền, trạng thái, phiên bản và điều kiện khuyến mại;
   - kiểm tra chính sách/bằng chứng còn hiệu lực;
   - cập nhật ngân sách và quyền lợi bằng thao tác có bảo vệ đồng thời;
   - tiêu thụ grant đúng phạm vi;
   - lưu kết quả cuối và sự kiện outbox nếu cần.
8. Commit rồi trả kết quả.
~~~

Không giữ transaction cơ sở dữ liệu mở trong khi chờ người dùng giải challenge hoặc gọi mạng tới nhà cung cấp. Bước kiểm tra bằng chứng bên ngoài nên tạo ra một kết quả nội bộ có phạm vi và thời hạn phù hợp; transaction kiểm tra kết quả nội bộ trước khi ghi.

Kết quả “cần xác minh” là một trạng thái trung gian của lệnh, không nên bị lưu thành thành công cuối cùng khiến cùng khóa không thể tiếp tục. Cần phân biệt rõ `WAITING_FOR_VERIFICATION`, `PROCESSING`, `SUCCEEDED` và các trạng thái kết thúc khác.

Nếu commit đã thành công nhưng phản hồi bị mất, retry phải đọc được kết quả cũ. Không yêu cầu grant còn chưa dùng hoặc chưa hết hạn để trả lại kết quả đã hoàn tất, vì retry đó không thực thi giao dịch mới. Tuy vậy, người gọi vẫn phải có quyền truy cập kết quả.

### 9.3. Các ràng buộc phải tồn tại độc lập

Ví dụ, chiến dịch chỉ cho một lượt hưởng trên mỗi tài khoản có thể cần ràng buộc duy nhất trên bộ `tenant + campaign + account`, tùy mô hình quyền lợi. Ngân sách cần cập nhật có điều kiện hoặc cơ chế khóa phù hợp.

Với hai request đồng thời, cả hai vượt qua challenge vẫn không được cùng sử dụng phần ngân sách chỉ đủ cho một. Nếu gửi sự kiện tới hệ thống ngoài sau commit, outbox và cơ chế xử lý trùng ở consumer giúp tránh việc retry tạo thêm tác động.

## 10. Ví dụ chính sách bằng Java

Ví dụ sau chỉ biểu diễn quyết định chính sách. Nó không triển khai kho hạn mức, xác minh CAPTCHA, transaction hay toàn bộ state machine. Các tín hiệu trong `Context` phải do máy chủ nạp và xác minh, không bind trực tiếp từ JSON client.

~~~java
import java.util.EnumSet;
import java.util.Set;

enum Control {
    THROTTLE,
    HUMAN_CHECK,
    STEP_UP,
    HOLD,
    DENY
}

record Context(
        int riskScore,
        boolean hardViolation,
        boolean automationSuspected,
        boolean stepUpRequiredByOperation,
        boolean humanProofValidForCommand,
        boolean freshAuthValidForCommand) {
}

record Decision(Set<Control> controls) {
    Decision {
        controls = Set.copyOf(controls);
    }
}

final class FrictionPolicy {
    Decision decide(Context context) {
        if (context.riskScore() < 0 || context.riskScore() > 100) {
            throw new IllegalArgumentException("Invalid risk score");
        }

        if (context.hardViolation()) {
            return new Decision(Set.of(Control.DENY));
        }

        if (context.riskScore() >= 80) {
            return new Decision(Set.of(Control.HOLD));
        }

        EnumSet<Control> controls = EnumSet.noneOf(Control.class);

        if (context.riskScore() >= 20) {
            controls.add(Control.THROTTLE);
        }

        if (context.riskScore() >= 40
                && context.automationSuspected()
                && !context.humanProofValidForCommand()) {
            controls.add(Control.HUMAN_CHECK);
        }

        boolean needsStepUp = context.stepUpRequiredByOperation()
                || context.riskScore() >= 60;

        if (needsStepUp && !context.freshAuthValidForCommand()) {
            controls.add(Control.STEP_UP);
        }

        return new Decision(controls);
    }
}
~~~

Các điểm cần đọc đúng:

- `DENY` biểu thị vi phạm điều kiện bắt buộc đã phát hiện; hoàn thành challenge không sửa được vi phạm đó.
- `HOLD` dừng thực thi cho đến khi đáp ứng luồng xử lý tương ứng, không chỉ hiển thị cảnh báo.
- `THROTTLE` yêu cầu lớp thực thi kiểm tra và cập nhật hạn mức; bản thân enum chưa giảm tốc độ.
- Khi đã có bằng chứng xác minh con người hợp lệ, chỉ yêu cầu `HUMAN_CHECK` được gỡ; giới hạn tốc độ vẫn giữ.
- Khi thao tác bắt buộc xác thực lại, điểm rủi ro thấp không gỡ yêu cầu này.
- Tập điều khiển rỗng nghĩa là không thêm friction từ ví dụ chính sách; mọi kiểm tra cơ sở vẫn chạy.

Trong hệ thống thực, cần bổ sung điều kiện hết hạn, trạng thái hạn chế hiện có, hysteresis, phiên bản chính sách, loại bằng chứng được chấp nhận và cách xử lý tín hiệu thiếu. Không nên trả tập điều khiển rỗng chỉ vì risk engine phát sinh exception.

## 11. Giao thức phản hồi và trải nghiệm người dùng

Client cần hiểu phải chờ, phải xác minh hay phải theo dõi trạng thái xử lý. Client không cần biết trọng số hoặc quy tắc phát hiện nội bộ.

Ví dụ phản hồi khi bị giảm tốc độ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Cache-Control: no-store
Content-Type: application/json

{
  "code": "RETRY_LATER",
  "message": "Bạn đang thực hiện thao tác quá nhanh. Vui lòng thử lại sau.",
  "retryAfterSeconds": 30,
  "correlationId": "req-example"
}
~~~

Máy chủ vẫn kiểm tra thời điểm được phép thử lại. Client nên tránh tự gửi dồn ngay khi hết thời gian chờ; có thể phân tán thời điểm retry trong giới hạn được phép.

Với yêu cầu xác minh, có thể trả một mã nghiệp vụ như `VERIFICATION_REQUIRED`, tham chiếu challenge và các phương thức được phép. Việc chọn HTTP status cần nhất quán với hợp đồng API và ngữ nghĩa xác thực của hệ thống; không mặc định mọi challenge đều là `429`.

Nếu yêu cầu được nhận vào hàng chờ, phản hồi cần có định danh và đường theo dõi trạng thái theo hợp đồng API. Người dùng phải hiểu hành động chưa hoàn tất, đặc biệt khi có tiền hoặc giữ chỗ liên quan.

Thông báo tốt nên:

- Nói rõ bước tiếp theo và khi nào được thử lại.
- Giữ dữ liệu đã nhập ở mức phù hợp để người dùng không phải tạo lại toàn bộ lệnh.
- Có phương thức xác minh thay thế đáp ứng cùng mục tiêu bảo đảm.
- Hỗ trợ bàn phím, trình đọc màn hình và tình huống mạng không ổn định.
- Không tiết lộ tài khoản có tồn tại, số điểm nội bộ hay chính xác tín hiệu đã bị kích hoạt.

Không nên thông báo “thiết bị của bạn nằm trong nhóm gian lận” chỉ dựa trên một tín hiệu chưa chắc chắn. Với các luồng dễ dò tồn tại tài khoản, cần xem cả mã phản hồi, nội dung và khác biệt thời gian xử lý.

OWASP lưu ý cơ chế khóa tài khoản có thể bị lợi dụng để gây từ chối dịch vụ cho người khác; thông báo xác thực cũng cần tránh tạo khác biệt làm lộ trạng thái tài khoản. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

## 12. Khi phụ thuộc gặp lỗi

Risk engine, kho đếm, dịch vụ challenge và hệ thống duyệt đều có thể chậm hoặc không truy cập được. Chính sách suy giảm phải được xác định trước theo mức tác động của hành động.

| Phụ thuộc gặp lỗi | Cách xử lý có thể phù hợp |
| --- | --- |
| Risk engine tạm không trả lời | Dùng tập quy tắc cục bộ có giới hạn cho luồng ít tác động; giữ hoặc từ chối tạm thời với luồng nhạy cảm |
| Kho hạn mức phân tán lỗi | Áp giới hạn cục bộ tạm thời có kiểm soát; không tuyên bố vẫn giữ được trần toàn cụm |
| Nhà cung cấp challenge lỗi | Chuyển sang phương thức đã được phép với bảo đảm phù hợp; hoặc yêu cầu thử lại |
| Hệ thống duyệt quá tải | Giới hạn đầu vào, hết hạn hồ sơ và trả trạng thái rõ ràng |
| Kho idempotency không bảo đảm đọc/ghi | Không thực hiện thêm tác động có nguy cơ trùng khi chưa có cơ chế an toàn tương đương |

“Cho qua để không làm phiền người dùng” có thể mở đúng đường vòng mà người tấn công cần. Ngược lại, chặn mọi chức năng vì một phụ thuộc phụ trợ lỗi có thể làm mất tính sẵn sàng quá mức cần thiết.

Cần xác định cụ thể hành động nào được tiếp tục, hạn mức tạm thời là bao nhiêu, thời gian áp dụng, người chịu trách nhiệm và tín hiệu nào kết thúc chế độ suy giảm. Các điều kiện bắt buộc về quyền và tính hợp lệ nghiệp vụ vẫn phải giữ.

Không để yêu cầu đắt tiền đi đến nhà cung cấp challenge không giới hạn. Cần quota cho cấp challenge, gửi OTP, kiểm tra bằng chứng, polling và tạo hồ sơ duyệt để tránh biến cơ chế bảo vệ thành nguồn tiêu hao chi phí.

## 13. Những cách triển khai dễ bị vượt qua

### 13.1. Chỉ chặn ở giao diện

**Sai:** Sau nhiều lần thử, website hiển thị CAPTCHA nhưng API áp mã vẫn nhận request trực tiếp.

**Sửa:** Máy chủ đánh giá chính sách và kiểm tra bằng chứng trước tác động nghiệp vụ; mọi kênh đi qua cùng điểm thực thi.

### 13.2. Coi xác minh là quyền thông hành toàn phiên

**Sai:** Sau một CAPTCHA thành công, đặt cờ “trusted” cho mọi hành động trong nhiều giờ.

**Sửa:** Giới hạn phạm vi, thời hạn và số lần dùng của bằng chứng. Chỉ nới yêu cầu mà bằng chứng đó đáp ứng.

### 13.3. Dựa hoàn toàn vào IP

**Sai:** Đổi IP là lấy lại toàn bộ lượt thử; nhiều người cùng mạng bị khóa chung.

**Sửa:** Kết hợp chủ thể, hành động, đối tượng, mức tác động và tín hiệu mạng. Đánh giá riêng trường hợp mạng dùng chung.

### 13.4. Tăng hình phạt vô hạn

**Sai:** Mỗi request tiếp tục kéo dài khóa, kể cả request do bên khác nhắm vào tài khoản nạn nhân.

**Sửa:** Giới hạn thời gian, nguồn sự kiện được tính, phạm vi bị hạn chế và đường khôi phục; tránh cho người chưa được xác thực quyền kéo dài khóa của người khác.

### 13.5. Cho phép đổi phương thức xuống mức yếu hơn

**Sai:** Client tự gửi `verificationMethod=none` hoặc dùng endpoint cũ để bỏ xác thực lại.

**Sửa:** Máy chủ quyết định phương thức tối thiểu, kiểm tra đúng loại bằng chứng và quản lý ngoại lệ có phạm vi, thời hạn, người cấp và audit.

### 13.6. Dùng friction để vá thiếu invariant

**Sai:** Tin rằng người dùng đã giải CAPTCHA nên không cần ràng buộc một lượt hưởng.

**Sửa:** Giữ invariant ở dữ liệu và transaction. Friction giảm khả năng khai thác quy mô; invariant bảo vệ tính đúng của từng giao dịch và toàn bộ tổng hợp liên quan.

## 14. Quan sát hiệu quả và tác dụng phụ

Số lượng challenge đã hiển thị không chứng minh hệ thống đã an toàn hơn. Cần đo cả thiệt hại nghiệp vụ lẫn ảnh hưởng đến người dùng.

| Chỉ số | Câu hỏi được trả lời |
| --- | --- |
| Tỷ lệ hành động ở từng mức kiểm soát | Có đẩy quá nhiều người vào luồng khó hơn không? |
| Tỷ lệ hoàn thành challenge và bước nghiệp vụ sau đó | Người dùng có vượt qua được và thực sự hoàn tất công việc không? |
| Tỷ lệ bỏ cuộc sau khi tăng friction | Chi phí trải nghiệm đang ở đâu? |
| Giá trị khuyến mại, tài nguyên giữ chỗ hoặc số tiền lạm dụng đã xác nhận | Thiệt hại thực có giảm không? |
| Thời gian chờ p95/p99 của quyết định kiểm soát | Bộ bảo vệ có làm chậm luồng quá mức không? |
| Khiếu nại, mở khóa và kết quả xem xét | Có dấu hiệu đánh giá nhầm theo nhóm sử dụng không? |
| Chi phí OTP, challenge và hàng chờ thủ công | Chi phí phòng vệ có bị lạm dụng hoặc vượt khả năng vận hành không? |
| Số lần dùng lại grant và xung đột idempotency | Có phát lại, lỗi tích hợp hoặc retry không đúng giao thức không? |

Tỷ lệ challenge thất bại không tự bằng tỷ lệ kẻ tấn công. Người dùng thật có thể thất bại do khó tiếp cận, nhà cung cấp lỗi hoặc mạng yếu. Tương tự, một challenge thành công không chứng minh giao dịch sau đó không gian lận.

Log quyết định nên có mã tương quan, tenant, định danh nội bộ phù hợp, hành động, đối tượng, mức kiểm soát, mã lý do, phiên bản chính sách và thời điểm. Không ghi OTP, token grant, bí mật phiên hoặc dữ liệu cá nhân không cần thiết. Các đặc trưng thiết bị và dữ liệu liên kết hành vi cần được giới hạn mục đích, thời hạn lưu và quyền truy cập.

Khi so sánh trước và sau thay đổi, cần lưu ý mùa khuyến mại, lượng truy cập, cơ cấu người dùng và thay đổi hành vi đối thủ. Cải thiện một biểu đồ không đủ kết luận có quan hệ nhân quả.

## 15. Ma trận kiểm thử tình huống lạm dụng

Các tình huống sau dùng để thiết kế kiểm thử trong môi trường được phép và kiểm soát tác động. Tập trung vào kết quả nghiệp vụ, không chỉ HTTP status.

| Tình huống | Kết quả cần bảo đảm |
| --- | --- |
| Sử dụng bình thường, ít tác động | Không bị áp friction không có lý do; các kiểm tra cơ sở vẫn chạy |
| Request đúng bằng và ngay quanh ngưỡng | Điều kiện tăng/giảm mức đúng định nghĩa, không có sai lệch biên |
| Gọi API trực tiếp, bỏ bước giao diện | Không bỏ được yêu cầu xác minh của máy chủ |
| Dùng grant của tài khoản hoặc tenant khác | Bị từ chối; không thay đổi đối tượng |
| Giải challenge cho giỏ A rồi áp vào giỏ B | Không chấp nhận phạm vi sai |
| Giữ grant nhưng đổi mã hoặc phiên bản giỏ | Đánh giá lại; không dùng bằng chứng cũ cho nội dung mới |
| Grant hết hạn hoặc sai loại xác minh | Không được dùng để thực thi lệnh mới |
| Hai request đồng thời dùng cùng grant | Chỉ một lần thực thi mới được tiêu thụ grant; retry đúng nghĩa nhận kết quả tương ứng |
| Hai lệnh đồng thời tranh phần ngân sách cuối | Không chi vượt ngân sách dù cả hai có bằng chứng hợp lệ |
| Mất phản hồi sau commit rồi retry cùng khóa | Trả kết quả cũ; không tạo thêm quyền lợi |
| Cùng khóa nhưng payload khác | Từ chối xung đột, không thay đổi nghĩa của lệnh đã nhận |
| Tạo khóa mới, đổi cookie hoặc đổi IP | Không xóa hạn chế theo chủ thể và invariant nghiệp vụ |
| Nhiều người thật dùng chung NAT | Không khóa hàng loạt chỉ vì chung IP |
| Kẻ khác tạo yêu cầu nhắm vào tài khoản nạn nhân | Không dễ biến bộ bảo vệ thành công cụ khóa nạn nhân |
| Người cần công nghệ hỗ trợ hoàn thành xác minh | Có lối thực hiện phù hợp, không hạ yêu cầu bảo đảm tùy tiện |
| Kho đếm hoặc nhà cung cấp challenge lỗi | Hành vi suy giảm đúng chính sách; không bỏ qua kiểm tra bắt buộc |
| Endpoint mobile, API cũ hoặc batch tạo cùng tác động | Giữ mục tiêu kiểm soát tương đương |
| Hạn chế hết thời gian | Đánh giá lại đúng điều kiện; không vừa hết hạn đã mất toàn bộ bảo vệ |
| Xác minh thành công nhưng hành động sai quyền | Vẫn bị từ chối; không rò dữ liệu hoặc ghi thay đổi |
| Duyệt thủ công chấp thuận nhưng dữ liệu đã đổi | Kiểm tra lại phạm vi phê duyệt và dữ liệu trước thực thi |

Với kiểm thử đồng thời, cần đồng bộ thời điểm bắt đầu và xác nhận trạng thái cuối ở dữ liệu: số lượt hưởng, ngân sách, trạng thái grant và command. Hai phản hồi nhìn có vẻ hợp lý vẫn có thể che một lần ghi thừa.

Với kiểm thử thời gian chờ và suy giảm tín hiệu, nên dùng đồng hồ có thể điều khiển trong môi trường kiểm thử thay vì chờ thời gian thực kéo dài. Không cần ghi token thật vào báo cáo để chứng minh kết quả.

## 16. Triển khai theo từng bước

Một trình tự triển khai có thể áp dụng:

1. **Chọn một luồng và định nghĩa thiệt hại.** Ví dụ: giảm số lượt dò mã và quyền lợi bị chi sai, đồng thời giữ khả năng hoàn tất mua hàng.
2. **Xác nhận các invariant đang được thực thi.** Friction không bù được thiếu kiểm tra quyền, thiếu ràng buộc duy nhất hoặc cập nhật ngân sách không an toàn.
3. **Ghi nhận quyết định dự kiến ở chế độ quan sát.** Chưa chặn nhưng vẫn kiểm soát chi phí thu thập và đánh giá.
4. **Đánh giá mẫu được gắn nhãn và phản hồi vận hành.** Kiểm tra các nhóm dễ bị ảnh hưởng như người dùng mới, mạng dùng chung hoặc người cần hỗ trợ tiếp cận.
5. **Bật theo phạm vi nhỏ.** Theo dõi cả chỉ số thiệt hại và tỷ lệ hoàn thành nghiệp vụ; đặt điều kiện dừng thử nghiệm.
6. **Mở rộng, hiệu chỉnh và quản lý phiên bản.** Mỗi thay đổi có lịch sử, người chịu trách nhiệm và cách khôi phục.
7. **Diễn tập lỗi phụ thuộc và đường hỗ trợ.** Bảo đảm bộ phận vận hành có thể xử lý nhầm lẫn mà không tạo đường bỏ qua quyền.

Chế độ quan sát không ngăn tấn công và không chứng minh ngưỡng đã an toàn. Việc quay lại chính sách trước đó cũng không được vô hiệu hóa kiểm tra quyền, state machine hay các invariant bắt buộc.

## 17. Bài tập vận dụng

Thiết kế progressive friction cho chức năng giữ chỗ một dịch vụ có số lượng vị trí hữu hạn.

Yêu cầu đầu vào:

- Mỗi tài khoản chỉ được có tối đa một số lượng giữ chỗ đang hoạt động theo chính sách.
- Giữ chỗ tự hết hạn nếu không xác nhận.
- Hệ thống phục vụ cả người dùng cùng mạng và tích hợp đối tác được cấp quyền.
- Tác vụ xác nhận có thể được retry sau khi mất kết nối.
- Nhiều request có thể tranh cùng vị trí.

Hãy mô tả:

1. Những invariant cần bảo vệ bằng dữ liệu và transaction.
2. Các tín hiệu phân biệt sử dụng nhanh hợp lệ với giữ chỗ hàng loạt.
3. Mức kiểm soát, điều kiện tăng/giảm và thời hạn.
4. Phạm vi của grant nếu cần xác minh bổ sung.
5. Cách xử lý retry, grant dùng một lần và hai yêu cầu đồng thời.
6. Hành vi khi kho hạn mức bị lỗi.
7. Các chỉ số cho thấy giảm thiệt hại mà không loại bỏ quá nhiều người dùng hợp lệ.

Một thiết kế đạt yêu cầu cần chỉ ra chính xác điểm máy chủ quyết định và điểm dữ liệu ngăn giữ vượt khả năng phục vụ. Chỉ thêm CAPTCHA hoặc ẩn nút xác nhận chưa đáp ứng bài toán.
