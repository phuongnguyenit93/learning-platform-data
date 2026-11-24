# Channel exhaustion abuse

## 1. Khi recovery trở thành công cụ làm cạn kênh liên lạc

**Channel exhaustion abuse** là việc lạm dụng luồng khôi phục tài khoản để tiêu hao khả năng gửi, ngân sách hoặc sự chú ý của người nhận. Kẻ tấn công không nhất thiết phải đoán đúng mật khẩu hay lấy được OTP. Chỉ cần khiến hệ thống gửi quá nhiều email, SMS, push hoặc cuộc gọi cũng có thể gây thiệt hại.

Trong account recovery, một yêu cầu công khai thường kích hoạt công việc đắt hơn nhiều so với chi phí gửi request: tra tài khoản, tạo token, ghi dữ liệu, gọi nhà cung cấp, gửi lại khi lỗi và chuyển kênh khi không giao được. Sự chênh lệch này tạo ra khả năng khuếch đại.

Ví dụ: một người bị gửi dồn hàng loạt email đặt lại mật khẩu. Người đó khó tìm được thông điệp hợp lệ; đồng thời hàng đợi và quota gửi của dịch vụ bị chiếm dụng. Nếu hệ thống chuyển sang gọi điện mỗi khi SMS thất bại, sự cố có thể lan sang cả kênh dự phòng.

OWASP cảnh báo rằng yêu cầu quên mật khẩu tự động có thể làm ngập hộp thư hoặc SMS của một tài khoản, và đề xuất kiểm soát như giới hạn theo tài khoản hoặc CAPTCHA. Xem [OWASP — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Mục tiêu phòng vệ gồm ba phần đồng thời:

- Bảo vệ người dùng khỏi bị làm phiền và thao túng.
- Giữ đủ năng lực recovery cho yêu cầu hợp lệ.
- Hạn chế chi phí và ảnh hưởng đến hạ tầng phân phối.

Giảm lượng gửi bằng cách khóa mọi tài khoản đang bị nhắm tới có thể bảo vệ hóa đơn nhưng lại giúp kẻ tấn công gây từ chối dịch vụ. Vì vậy cần kiểm soát quyền tạo thông điệp, không mặc định biến người nhận thành đối tượng chịu phạt.

## 2. Phân biệt các dạng cạn kiệt

| Dạng lạm dụng | Tài nguyên bị tiêu hao | Hậu quả trong recovery |
| --- | --- | --- |
| Gửi dồn đến một người nhận | Hộp thư, điện thoại, sự chú ý | Người dùng bỏ qua thông điệp thật hoặc mất khả năng sử dụng kênh |
| Gửi đến nhiều người nhận | Quota nhà cung cấp, ngân sách, worker | Yêu cầu hợp lệ bị chậm hoặc không được gửi |
| Dội push phê duyệt | Sự chú ý và khả năng ra quyết định | Người dùng có thể bấm chấp thuận để ngừng bị làm phiền |
| Lạm dụng SMS/cuộc gọi có tính phí | Ngân sách và tuyến phân phối | Chi phí tăng mà không có recovery hợp lệ tương ứng |
| Lặp lại resend và fallback | Số lần dispatch trên mỗi giao dịch | Một yêu cầu ban đầu tạo nhiều lần gửi |
| Làm đầy hàng đợi hỗ trợ | Thời gian nhân viên và hồ sơ cần xử lý | Trường hợp thực sự cần xác minh bị chậm |

Hai kiểu phân bố cần được nhận diện riêng:

**Tập trung:** nhiều nguồn cùng nhắm một tài khoản hoặc một địa chỉ nhận. Giới hạn theo IP khó bảo vệ nạn nhân trong trường hợp này.

**Dàn trải:** mỗi tài khoản hoặc số điện thoại chỉ nhận ít yêu cầu, nhưng tổng số đích rất lớn. Giới hạn theo tài khoản có thể không bảo vệ được ngân sách toàn dịch vụ.

Một hệ thống thực tế có thể gặp cả hai cùng lúc. Không có một khóa rate limit duy nhất giải quyết được toàn bộ bài toán.

Đối với push ngoài băng, NIST khuyến nghị giới hạn hợp lý tốc độ hoặc tổng số thông báo gửi đến thiết bị. Tài liệu cũng nêu rằng tạo bí mật xác thực mới không được đặt lại bộ đếm xác thực thất bại. Đây là hai ngân sách khác nhau: số lần gửi và số lần đoán bằng chứng. Xem [NIST — Out-of-Band Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#oobver).

## 3. Xem toàn bộ đường đi từ request đến lần gửi

Không chỉ đếm request ở API. Cần nhìn thấy mọi nơi có thể tạo thêm thông điệp.

~~~mermaid
flowchart TD
    A[Yêu cầu recovery công khai] --> B[Kiểm soát tiếp nhận]
    B --> C[Tra tài khoản và kênh đã đăng ký]
    C --> D[Gộp yêu cầu tương đương]
    D --> E[Kiểm tra và giữ ngân sách gửi]
    E --> F[Hàng đợi có giới hạn]
    F --> G[Worker kiểm tra lại quyền gửi]
    G --> H[Nhà cung cấp email SMS push voice]
    H --> I[Trạng thái giao nhận]
    I --> J{Có được gửi lại không?}
    J -->|Có ngân sách và còn hạn| F
    J -->|Không| K[Dừng hoặc chuyển quy trình đã định]
~~~

Một mô hình khuếch đại đơn giản:

~~~text
số lần thử phân phối
    = số yêu cầu đầu vào
      × số kênh được kích hoạt
      × số lần thử tối đa trên mỗi kênh
~~~

Ví dụ minh họa: 120 yêu cầu, mỗi yêu cầu gửi qua hai kênh và mỗi kênh có tối đa ba lần thử, có thể tạo đến 720 lần thử phân phối. Đây là số lần thử theo mô hình, không phải khẳng định tất cả đều được nhà cung cấp tính phí.

Các đường thường bị bỏ sót:

- Nút “gửi lại mã” dùng endpoint khác với endpoint bắt đầu recovery.
- Worker tự retry dù tầng API đã giới hạn.
- Webhook báo lỗi làm tạo một thông điệp mới.
- SMS thất bại dẫn đến cuộc gọi rồi email.
- Nhân viên hỗ trợ bấm gửi từ công cụ nội bộ.
- Một thay đổi ngôn ngữ hoặc mẫu thông điệp tạo khóa dedup khác.
- Nhiều vùng triển khai mỗi vùng tự cho phép một quota đầy đủ.

Mọi đường gửi cần nằm trong chính sách chung. Giới hạn ở một endpoint không đủ nếu những đường khác vẫn gửi không có ngân sách.

## 4. Lập ngân sách theo nhiều chiều

Một thiết kế minh họa có thể dùng các chiều sau:

| Chiều ngân sách | Vai trò | Lưu ý |
| --- | --- | --- |
| Nguồn yêu cầu | Hạn chế tự động hóa từ một nguồn | NAT, proxy và mạng di động có thể làm nhiều người dùng chung nguồn |
| Tài khoản | Bảo vệ một chủ tài khoản khỏi bị nhắm tập trung | Không được biến hết quota gửi thành khóa đăng nhập |
| Địa chỉ hoặc số nhận | Bảo vệ một kênh dù nhiều tài khoản cùng dùng | Không giả định một số điện thoại chỉ thuộc một tài khoản |
| Giao dịch recovery | Giới hạn tổng resend, retry và fallback | Đổi kênh không được tạo ngân sách mới vô hạn |
| Tenant hoặc nhóm khách hàng | Chia sẻ tài nguyên công bằng | Tránh để một tenant dùng hết năng lực chung |
| Kênh và tuyến phân phối | Giới hạn tải và chi phí | SMS, voice, email có mức tiêu hao khác nhau |
| Toàn dịch vụ | Chặn sự cố quy mô lớn | Cần cơ chế giữ năng lực cho công việc quan trọng |

Có thể kết hợp cửa sổ ngắn để chặn burst với cửa sổ dài để kiểm soát tổng lượng gửi. Một khoảng cooldown ngắn không thay thế được ngân sách theo giờ hoặc theo ngày nếu chi phí tiếp tục tích lũy.

Nếu dùng ngân sách theo trọng số:

~~~text
ngân sách tiêu hao
    = tổng trọng số của những lần phân phối được giữ chỗ hoặc thực hiện
~~~

Trọng số cần phản ánh mục tiêu vận hành của hệ thống. Không nhất thiết mỗi lần gửi qua mọi kênh đều có giá như nhau. Khi đánh giá chi phí, cần tính cả công việc đang chờ có khả năng trở thành chi phí, không chỉ số đã xuất hiện trên hóa đơn.

Các ngưỡng phải được lựa chọn từ lưu lượng hợp lệ, khả năng phân phối, rủi ro và ngân sách của dịch vụ. Không có một con số chung phù hợp cho mọi hệ thống account recovery.

### Định danh khóa một cách ổn định

Một số điện thoại nên được chuẩn hóa theo quy tắc của ứng dụng trước khi dùng làm khóa. Với email, không tự ý xóa dấu chấm hoặc phần sau dấu cộng theo giả định áp dụng cho mọi nhà cung cấp; có thể gộp nhầm những địa chỉ thực sự khác nhau.

Có thể dùng HMAC với khóa do server quản lý để tạo định danh người nhận cho kho chống lạm dụng, thay vì lưu địa chỉ nguyên văn ở mọi bộ đếm. Định danh này vẫn có thể liên kết hoạt động của cùng người nhận, nên cần quyền truy cập và thời hạn lưu phù hợp.

Không tin địa chỉ IP do client tự điền vào header. Hệ thống phải xác định nguồn từ chuỗi proxy tin cậy đã cấu hình.

Một ví dụ ở tầng nhà cung cấp là Twilio Verify Service Rate Limits, cho phép ứng dụng cung cấp thuộc tính dùng làm khóa giới hạn. Cơ chế của nhà cung cấp có thể bổ sung kiểm soát, nhưng ứng dụng vẫn phải bao phủ những endpoint, hàng đợi và kênh thuộc hệ thống của mình. Xem [Twilio — Service Rate Limits](https://www.twilio.com/docs/verify/api/service-rate-limits).

## 5. Hết ngân sách gửi không đồng nghĩa mất quyền khôi phục

Đây là điểm khó nhất của phòng vệ theo người nhận: kẻ ngoài có thể cố tình dùng hết quota của nạn nhân trước khi nạn nhân cần recovery thật.

Cần tách các quyết định:

- Có cho tiếp nhận thêm công việc tốn tài nguyên không?
- Có gửi thêm thông điệp không?
- Có cho kiểm tra một bằng chứng đã phát hành không?
- Có cho tiếp tục giao dịch đã được xác minh không?
- Có thay đổi quyền truy cập của tài khoản không?

Một tài khoản đang bị spam có thể tạm thời không nhận thêm SMS, nhưng một recovery code hợp lệ đã lưu riêng hoặc một authenticator dự phòng vẫn cần được xử lý theo chính sách tương ứng. Không dùng trạng thái hết quota thông báo làm lý do tự động từ chối mọi bằng chứng hợp lệ.

Nếu người dùng đã có link còn hạn, không tự vô hiệu link đó chỉ vì một người ngoài bấm resend. Nếu mỗi lần bấm “quên mật khẩu” đều hủy mọi quyền trước, kẻ tấn công có thể liên tục đẩy chủ tài khoản ra khỏi luồng recovery.

Có thể dành năng lực riêng cho ngữ cảnh đã có bằng chứng đáng tin hơn, nhưng việc phân loại phải do backend quyết định. Một cờ trusted=true trong request, cookie mới hoặc idempotency key do người gọi tự chọn không làm yêu cầu trở thành tin cậy.

Ngay cả yêu cầu đã xác thực cũng cần giới hạn. Session bị chiếm không được trở thành công cụ gửi thông điệp vô hạn.

## 6. Gộp yêu cầu và thiết kế resend có giới hạn

Gộp yêu cầu tương đương giúp giảm số lần gửi mà không cần tạo thêm thử thách cho người dùng trong mọi trường hợp.

Một khóa gộp minh họa:

~~~text
accountId / purpose / channel / destinationVersion / activeRecoveryWindow
~~~

Khóa phải do máy chủ xây dựng từ thông tin chuẩn. Nếu khóa chỉ chứa requestId mới do client tạo, mỗi request mới vẫn có thể vượt qua gộp. Ngược lại, khóa quá rộng có thể gộp nhầm những giao dịch hoặc thao tác khác nhau.

Các quy tắc hữu ích:

1. Một giao dịch đang chờ có số lần gửi tối đa rõ ràng.
2. Resend tuân theo khoảng chờ và ngân sách dài hạn.
3. Retry của cùng một lần dispatch có định danh ổn định.
4. Gửi lại không tự kéo dài vô hạn hạn của token.
5. Gộp không cho người gọi thay địa chỉ nhận hoặc tập thay đổi đang chờ.
6. Gửi lại mã không đặt lại ngân sách đoán mã.
7. Thay kênh vẫn tiêu hao ngân sách của giao dịch gốc.

Gộp việc gửi không có nghĩa là có thể bỏ qua vòng đời bí mật. Nếu hệ thống chỉ lưu digest của token, không thể lấy lại raw token từ digest để gửi lại. Thiết kế phải quyết định rõ cách tạo hoặc giữ bí mật cần phân phối, thời hạn, bảo vệ dữ liệu và quan hệ giữa quyền mới với quyền cũ.

Không chèn mật khẩu, OTP hoặc recovery token vào log để phục vụ resend. Lưu trạng thái công việc và lưu bí mật là hai trách nhiệm cần được thiết kế riêng.

## 7. Giữ chỗ ngân sách trước khi đưa công việc vào hàng đợi

Chỉ kiểm tra ngân sách sau khi đã gọi nhà cung cấp là quá muộn. Nếu có hàng nghìn công việc đang chờ và tất cả đều thấy ngân sách chưa bị trừ, chúng có thể cùng tạo chi phí khi worker chạy.

Cần phân biệt:

- **Admission:** có cho yêu cầu vào đường xử lý tiếp theo không?
- **Reservation:** đã giữ phần ngân sách nào cho công việc đang chờ?
- **Dispatch:** đã thực sự thử gửi ra ngoài chưa?
- **Settlement:** kết quả cuối cùng tiêu hao bao nhiêu theo dữ liệu đáng tin?

Việc kiểm tra và giữ ngân sách phải chống được nhiều instance chạy đồng thời. Mẫu “đọc bộ đếm, thấy còn, rồi tăng” không nguyên tử có thể cho quá nhiều yêu cầu cùng vượt qua.

Một reservation cần gắn với định danh dispatch và có vòng đời rõ:

~~~text
RESERVED -> DISPATCHING -> ACCOUNTED
    |
    -> RELEASED nếu chắc chắn chưa phát sinh lần gửi
~~~

DISPATCHING có thể bao gồm trường hợp chưa biết nhà cung cấp đã nhận hay chưa. Không tự hoàn ngân sách ở trường hợp này chỉ vì HTTP timeout.

### Minh họa trách nhiệm của service Java

Các thành phần dưới đây là giả định để diễn tả thiết kế, không phải thư viện có sẵn:

~~~java
PlanResult planRecoveryMessage(
    ResolvedRecoveryTarget target,
    RecoveryFlowRef flowRef,
    Channel channel
) {
    return transactions.required(() -> {
        RecoveryFlow flow = flows.lockCurrent(flowRef.id());

        policy.requireChannelAllowed(flow, target, channel);
        destinations.requireCurrentRegisteredVersion(target);

        DeliveryKey key = deliveryKeys.fromServerState(
            flow, target, channel
        );

        if (deliveries.hasEquivalentPendingDelivery(key)) {
            return PlanResult.COALESCED;
        }

        Instant deadline = policy.deliveryDeadline(flow);
        DeliveryCost cost = costs.estimate(channel, target);

        // Kiểm tra và giữ mọi ngân sách bắt buộc một cách nguyên tử.
        Reservation reservation = budgets.tryReserveAll(
            budgetKeys.forDelivery(flow, target, channel),
            cost,
            deadline
        );

        if (reservation == null) {
            return PlanResult.SUPPRESSED;
        }

        deliveryOutbox.enqueueOnce(
            key, flow.id(), target.reference(),
            target.version(), reservation.id(), deadline
        );

        return PlanResult.SCHEDULED;
    });
}
~~~

Trong mô hình này, cập nhật reservation, kiểm soát trùng và ghi outbox phải có cùng bảo đảm nguyên tử, chẳng hạn cùng kho dữ liệu giao dịch. Chỉ đặt một lời gọi cache từ xa bên trong callback transaction không tạo ra transaction chung giữa hai hệ thống.

Nếu dùng nhiều kho dữ liệu, cần giao thức giữ chỗ và đối soát riêng. Khi chưa chắc reservation có hiệu lực, không được cho worker gửi chỉ để tránh làm người dùng chờ.

PlanResult là kết quả nội bộ. Endpoint công khai không nhất thiết trả lại COALESCED hoặc SUPPRESSED, vì những giá trị này có thể làm lộ trạng thái tài khoản và người nhận.

Mỗi loại bộ đếm có ý nghĩa khác nhau. Ngân sách phân phối có thể được giải phóng khi chắc chắn chưa gửi; ngân sách chống lạm dụng đầu vào vẫn có thể tính lần yêu cầu bị chặn. Không hoàn mọi bộ đếm chỉ vì cuối cùng không có tin nhắn được gửi.

## 8. Hàng đợi phải có giới hạn và thời hạn

Hàng đợi không làm công việc biến mất; nó chỉ chuyển chi phí sang tương lai. Một hàng đợi không giới hạn có thể gây cạn bộ nhớ, tăng thời gian chờ và tạo một đợt gửi dồn sau khi hệ thống phục hồi.

Theo mô hình tải đơn giản:

~~~text
nếu tốc độ công việc đi vào liên tục lớn hơn tốc độ xử lý,
số công việc chờ sẽ tiếp tục tăng
~~~

Vì vậy cần giới hạn cả lượng công việc được nhận lẫn số đang chờ. Khi vượt ngưỡng, có thể gộp hoặc loại công việc gửi mới theo chính sách thay vì giữ vô hạn.

Worker cần kiểm tra lại trước dispatch:

- Giao dịch recovery còn đang hoạt động không?
- Người nhận và phiên bản kênh có còn đúng không?
- Thông điệp hoặc token còn đủ thời gian hữu ích để gửi không?
- Reservation có còn hợp lệ và thuộc worker/operation này không?
- Kênh hoặc tuyến phân phối đang bị dừng bảo vệ không?
- Dispatch này đã được xử lý hay chưa?

Nếu token đã hết hạn, gửi email chứa token đó không giúp người dùng khôi phục tài khoản. Cũng không được âm thầm kéo dài token chỉ vì thông điệp bị xếp hàng lâu.

Có thể tách nhóm công việc theo tenant, kênh và mức tin cậy để phân phối công bằng. Một tenant bị tấn công không nên chiếm tất cả worker phục vụ tenant khác.

Các thông báo về thay đổi bảo mật đã commit cần được phân biệt với email khởi tạo recovery công khai. Có thể dành năng lực riêng cho nhóm thông báo quan trọng này, nhưng client không được tự chọn nhãn “khẩn cấp” để đi vào hàng ưu tiên.

Nếu năng lực dành riêng cũng bị ảnh hưởng, cần cảnh báo và phương án vận hành đã định. Không tuyên bố rằng dành một queue riêng sẽ bảo đảm giao nhận trong mọi sự cố nhà cung cấp.

## 9. Retry và fallback có thể làm sự cố lớn hơn

### Retry phải có ngân sách riêng hoặc được tính trong reservation

Một lần timeout có thể mang hai ý nghĩa:

- Nhà cung cấp chưa nhận công việc.
- Nhà cung cấp đã nhận, nhưng phản hồi không tới ứng dụng.

Gửi lại ngay có thể tạo thông điệp trùng. Nếu nhà cung cấp hỗ trợ idempotency phù hợp, dùng định danh ổn định theo hợp đồng của họ. Nếu không, hệ thống phải quản lý trạng thái chưa biết và cân nhắc nguy cơ gửi trùng; không mặc định mỗi retry đều miễn phí và an toàn.

Retry cần có số lần tối đa, thời hạn kết thúc và giãn thời gian có độ ngẫu nhiên để tránh nhiều worker gọi lại đồng thời. Những lần thử này vẫn phải tuân theo ngân sách kênh và giao dịch.

Callback giao nhận cần được xác thực theo cơ chế của nhà cung cấp và xử lý trùng an toàn. Một callback lỗi bị giả mạo không được kích hoạt chuỗi resend hoặc fallback vô hạn.

### Fallback không phải lối thoát khỏi giới hạn

Luồng sau nguy hiểm nếu từng bước có ngân sách riêng không liên kết:

~~~text
SMS bị chặn -> gọi điện
Cuộc gọi thất bại -> gửi email
Email không xác nhận -> tạo push mới
Push không phản hồi -> gọi lại
~~~

Chuyển kênh phải là quyết định của chính sách: kênh đã đăng ký, bằng chứng cần thiết, số lần thử còn lại và tổng chi phí của giao dịch.

Một lỗi gửi không chứng minh danh tính người yêu cầu. Không chuyển sang phương thức yếu hơn chỉ vì kênh mạnh đang hết quota hoặc người gọi nói rằng họ không nhận được tin.

Phạm vi bảo vệ của nhà cung cấp cũng có giới hạn. Chẳng hạn tài liệu Twilio Verify Fraud Guard mô tả bảo vệ cho SMS và nêu rằng voice không nằm trong phạm vi hỗ trợ của cơ chế đó. Đây là ví dụ vì sao không nên suy rằng bảo vệ SMS tự bao phủ cuộc gọi fallback. Xem [Twilio — Verify Fraud Guard](https://www.twilio.com/docs/verify/preventing-toll-fraud/sms-fraud-guard).

Khi mở lại một tuyến vừa bị ngắt, cần tăng lưu lượng có kiểm soát và bỏ công việc đã hết hạn. Đẩy toàn bộ backlog ngay lập tức có thể tạo một đợt cạn quota mới.

## 10. Thiết kế phản hồi không tiết lộ trạng thái kênh

Với endpoint recovery công khai, có thể trả thông điệp:

> Nếu yêu cầu hợp lệ và kênh đã đăng ký còn khả dụng, hướng dẫn sẽ được xử lý. Bạn có thể dùng phương thức khôi phục khác đã thiết lập trước.

Thông điệp này không khẳng định chắc chắn email hoặc SMS đã được gửi. Nó phù hợp với cả trường hợp yêu cầu không tồn tại, được gộp hoặc không được gửi vì chính sách.

Không trả chi tiết như:

- Tài khoản này đã dùng hết quota SMS.
- Email này có ba yêu cầu đang chờ.
- Số điện thoại kết thúc bằng các chữ số cụ thể đang bị nhà cung cấp chặn.
- Hãy thử lại sau đúng số giây còn lại của quota người nhận.

Những chi tiết đó có thể trở thành công cụ dò tài khoản hoặc theo dõi việc nạn nhân dùng recovery. Ngữ cảnh đã được xác minh có thể nhận hướng dẫn cụ thể hơn nếu được phân quyền phù hợp.

Nếu giới hạn đầu vào theo nguồn gọi, hệ thống có thể dùng phản hồi quá nhiều yêu cầu mà không phụ thuộc tài khoản có tồn tại. Quy tắc bên ngoài cần nhất quán với mô hình chống enumeration; không chỉ dùng cùng câu chữ nhưng khác hẳn mã trạng thái, độ dài hoặc thời gian xử lý theo tài khoản.

Xử lý bất đồng bộ giúp tách phản hồi công khai khỏi kết quả gửi, nhưng không tự giải quyết mọi kênh rò thông tin. Tầng tiếp nhận vẫn phải giới hạn công việc tra cứu và không cho số định danh giả vô hạn làm đầy hàng đợi.

### CAPTCHA chỉ là một lớp tăng chi phí

CAPTCHA có thể giảm một số loại tự động hóa trước khi phát sinh công việc gửi. Nó không chứng minh người giải là chủ tài khoản, không thay thế ngân sách người nhận và không chặn mọi nguồn phân tán.

Cần tính đến khả năng tiếp cận của người dùng. Khi một người không hoàn thành được CAPTCHA, đường thay thế phải là quy trình recovery có chính sách rõ, không phải nút bỏ qua mọi kiểm soát.

## 11. Bảo vệ kênh mà không làm yếu xác minh danh tính

Khi kênh bị quá tải, áp lực hỗ trợ thường tăng: người dùng không nhận được mã, nhân viên muốn gửi thủ công, hệ thống muốn bỏ một bước để tăng tỷ lệ hoàn tất.

Đây là lúc cần giữ nguyên các ranh giới:

- Không chấp nhận OTP sai vì người dùng đã thử nhiều lần.
- Không bỏ xác nhận MFA chỉ vì push đang bị hạn chế.
- Không nhận số điện thoại mới làm kênh đáng tin ngay trong yêu cầu chưa xác minh.
- Không cho công cụ hỗ trợ gửi không giới hạn.
- Không miễn kiểm soát toàn cục cho một địa chỉ chỉ vì đã được thêm vào danh sách cho phép.
- Không coi “đã gửi thành công” là “đã xác minh chủ tài khoản”.

Một ngoại lệ hợp lệ có thể có phạm vi và thời hạn giới hạn, do người có quyền phê duyệt và có nhật ký. Ngoại lệ cần giữ giới hạn chi phí và năng lực bắt buộc của hệ thống; không biến thành một cờ bỏ qua mọi lớp bảo vệ.

Nếu tất cả kênh đáng tin đều không dùng được, người dùng có thể phải chờ hoặc chuyển sang quy trình xác minh khác. Không thể bảo đảm tự phục vụ ngay lập tức bằng cách chỉ giảm chuẩn xác minh. Thiết kế nên chuẩn bị phương thức dự phòng từ trước, như mã recovery hoặc authenticator bổ sung, thay vì sáng tác đường tắt khi sự cố xảy ra.

## 12. Quan sát đúng tài nguyên và đúng kết quả

Một dashboard chỉ có số request API sẽ bỏ qua phần lớn chi phí phía sau. Cần theo dõi các bước riêng:

| Nhóm chỉ số | Điều cần hiểu |
| --- | --- |
| Yêu cầu đầu vào | Nguồn, tốc độ, số định danh được nhắm đến |
| Quyết định nội bộ | Được gộp, bị trì hoãn, bị chặn theo ngân sách nào |
| Công việc gửi | Đã giữ chỗ, đang chờ, đã dispatch, chưa biết kết quả |
| Phân phối | Nhà cung cấp nhận, báo giao nhận, lỗi theo kênh |
| Chi phí | Ước tính đã giữ, lượng được xác nhận, sai lệch cần đối soát |
| Hiệu quả recovery | Số giao dịch duy nhất hoàn tất, thời gian hoàn tất, bỏ dở |
| Tác động tới người dùng | Khiếu nại spam, yêu cầu hỗ trợ, trì hoãn hợp lệ |
| Hạ tầng | Tuổi công việc lâu nhất, backlog, tốc độ retry và fallback |

Một số tín hiệu đáng xem xét:

- Tổng số gửi tăng nhanh trong khi số giao dịch recovery duy nhất hoàn tất không tăng tương ứng.
- Một người nhận bị nhiều nguồn không liên quan nhắm tới.
- Nhiều người nhận mới xuất hiện trong một tuyến phân phối với ít bước xác minh tiếp theo.
- Tỷ lệ retry hoặc fallback tăng vượt thay đổi của lưu lượng gốc.
- Quota gần hết dù ứng dụng vẫn trả phản hồi thành công cho nhiều request.

Không kết luận gian lận chỉ từ tỷ lệ hoàn tất thấp. Sự cố nhà mạng, email bị chậm hoặc lỗi ứng dụng cũng có thể tạo tín hiệu tương tự. Cần đối chiếu dữ liệu phân phối và tình trạng dịch vụ.

Không đưa số điện thoại, email hay token trực tiếp vào nhãn metric có độ đa dạng không giới hạn. Ngoài rò dữ liệu, việc này còn có thể làm hệ thống quan sát cạn tài nguyên. Dùng chỉ số tổng hợp và nhật ký truy cập được kiểm soát để điều tra trường hợp cụ thể.

Giới hạn cả lượng sự kiện chống lạm dụng được ghi. Một request bị chặn không nên tạo hàng loạt email cảnh báo, hồ sơ hỗ trợ và log nặng, vì chính hoạt động phòng vệ có thể trở thành một bộ khuếch đại mới.

## 13. Ba tình huống vận dụng

**Một người dùng bị gửi dồn email recovery:** gộp yêu cầu tương đương, giới hạn gửi theo tài khoản và người nhận, giữ hiệu lực của quyền hợp lệ đã phát hành theo chính sách. Người dùng vẫn có thể tiếp tục bằng bằng chứng hợp lệ; không khóa tài khoản chỉ vì người ngoài tạo nhiều request.

**Lưu lượng SMS dàn trải làm tăng chi phí:** ngân sách toàn dịch vụ, theo tenant và tuyến phân phối giúp bổ sung cho giới hạn từng tài khoản. Chỉ gửi đến kênh được phép; các đường resend, retry và công cụ nội bộ đều đi qua cùng kiểm soát bắt buộc.

**Nhà cung cấp chậm rồi phục hồi:** không retry đồng loạt hoặc tự chuyển toàn bộ sang voice. Theo dõi trạng thái chưa biết, giữ ngân sách tương ứng, loại công việc hết hạn và phục hồi lưu lượng có kiểm soát.

Nguyên tắc thiết kế là: **mỗi thông điệp recovery phải có lý do hợp lệ, người nhận được xác định từ nguồn tin cậy, ngân sách được kiểm soát và thời điểm kết thúc rõ ràng**. Bảo vệ kênh liên lạc phải đi cùng khả năng tiếp tục xác minh an toàn của chủ tài khoản.
