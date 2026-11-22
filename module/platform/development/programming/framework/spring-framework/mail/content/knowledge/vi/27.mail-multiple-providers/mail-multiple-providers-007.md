# Không thử lại sang provider khác với lỗi không thể gửi trong Spring Framework Mail

Khi một hệ thống dùng nhiều nhà cung cấp email (multi-provider), ý tưởng thường gặp là: “Nếu provider A báo lỗi thì chuyển ngay sang provider B”. Cách làm này hữu ích khi một **đường gửi đang bị gián đoạn tạm thời**, nhưng có thể gây hậu quả nghiêm trọng nếu email thực ra **không thể gửi một cách hợp lệ**: địa chỉ người nhận sai, thông điệp thiếu dữ liệu, nội dung vi phạm chính sách, recipient đã unsubscribe, email xác thực hết hạn hoặc tài khoản không có quyền gửi từ domain đã chọn.

Trong các tình huống đó, gửi cùng thông điệp qua provider B không làm thông điệp trở nên đúng. Hệ thống chỉ khuếch đại lỗi, tăng chi phí và nguy cơ bị đánh dấu spam, đôi khi còn tìm cách vòng qua các quy tắc từ chối của provider A. Vì vậy, một kiến trúc Spring Framework Mail an toàn phải đặt **điều kiện dừng** trước cơ chế failover:

> **Không chuyển sang provider khác chỉ vì một lần gửi thất bại. Chỉ cho phép chuyển khi nguyên nhân thật sự có khả năng được khắc phục bằng cách đổi tuyến gửi, dữ liệu và quyền gửi vẫn hợp lệ, đồng thời kết quả submit trước đó đã đủ rõ để tránh gửi trùng không kiểm soát.**

Bài học tập trung vào **quy tắc không failover đối với lỗi không thể gửi**, cách phân loại, tổ chức nhiều `JavaMailSender`, kiểm soát retry/outbox, kiểm thử và vận hành. Các policy và Java type trong ví dụ là thành phần **ứng dụng tự thiết kế**; Spring Mail không có sẵn một hệ thống multi-provider failover hoàn chỉnh.

## 1. Phân biệt retry, failover, resend và provider-owned retry

Các khái niệm dễ bị trộn lẫn:

| Hành động | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Retry cùng provider | Thử lại submission qua cùng tuyến, sau backoff | A tạm mất kết nối trước khi gửi DATA |
| Failover sang provider khác | Chuyển submission chưa thành công sang tuyến B đủ điều kiện | A có outage hạ tầng, B được phép gửi cùng loại thư |
| Resend nghiệp vụ | Tạo yêu cầu gửi mới theo hành động được ủy quyền | Người dùng yêu cầu gửi lại hóa đơn |
| Replay dead letter | Xem xét và xử lý lại bản ghi đã dừng sau khi sửa nguyên nhân | Sửa template bị lỗi rồi gửi theo quy trình |
| Provider-owned retry | Relay đã accepted, đang thử giao tới remote MX | A trả event DEFERRED và tự retry downstream |

**Không tự failover khi provider A đã accepted một message và đang retry downstream.** Nếu ứng dụng gửi lại qua B, recipient có thể nhận nhiều bản và hai relay cùng cố giao thư. Lỗi delivery downstream phải được theo dõi theo event/DSN của provider, không tự biến thành một SMTP submission mới.

### Một sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Submit qua provider A"] --> B{"Kết quả?"}
    B -- "Accepted rõ ràng" --> C["SUBMITTED: theo dõi delivery event"]
    B -- "Không rõ sau DATA" --> D["SUBMISSION_UNKNOWN: đối soát"]
    B -- "Bị từ chối rõ ràng" --> E{"Failure có tính chất nào?"}
    E -- "Payload / recipient / consent / policy không hợp lệ" --> F["Dừng: không failover"]
    E -- "Có thể khắc phục bằng sửa cấu hình" --> G["Hold để sửa; không chuyển mù"]
    E -- "Outage riêng tuyến A, kết quả chắc chắn chưa accepted" --> H{"B hợp lệ và có budget?"}
    H -- "Không" --> I["Retry/defer có giới hạn"]
    H -- "Có" --> J["Failover có kiểm soát sang B"]
~~~

Đây là luồng khái niệm: để quyết định, ứng dụng còn cần biết trạng thái outbox, expiry, địa chỉ được phép, provider eligibility, số attempts và quy tắc tránh duplicate.

## 2. “Lỗi không thể gửi” là gì?

Một lỗi **không thể gửi (non-sendable)** nghĩa là bản thông điệp hoặc yêu cầu gửi hiện tại **không đáp ứng một điều kiện bắt buộc**. Việc thay SMTP relay thường không sửa được điều kiện đó.

Các nhóm cần dừng:

1. **Recipient không hợp lệ:** địa chỉ không đúng cú pháp, mailbox không tồn tại được xác nhận, recipient bị suppress hoặc không được phép nhận.
2. **Thông điệp không hợp lệ:** template không render, dữ liệu thiếu, MIME lỗi, attachment không được phép hoặc payload vi phạm ràng buộc nghiệp vụ.
3. **Tính hợp lệ theo thời gian:** OTP/reset link đã hết hạn; chiến dịch đã kết thúc.
4. **Quyền và chính sách gửi:** không có consent cần thiết, recipient unsubscribe/complain, From identity chưa được ủy quyền hoặc nội dung bị từ chối bởi một chính sách mà tuyến B cũng phải tôn trọng.
5. **Kết quả chưa chắc chắn:** provider A có thể đã nhận message nhưng client mất final response. Đây không phải “không thể gửi” theo nghĩa dữ liệu sai, nhưng **không đủ điều kiện failover an toàn ngay lập tức**.

### Ba câu hỏi cần trả lời trước failover

**A. Payload còn hợp lệ không?** Không chỉ cú pháp email mà còn TTL, suppression, template, From, loại email, phạm vi tenant và giới hạn recipient.

**B. Sự cố có thực sự gắn với tuyến A không?** Một lỗi DNS của hostname A hay outage provider A có thể cải thiện khi dùng B. Mailbox không tồn tại sẽ không được sửa chỉ bằng đổi nhà cung cấp.

**C. A đã nhận email chưa?** Nếu có hoặc chưa biết chắc, gửi qua B có thể làm duplicate. Quy trình đối soát quan trọng hơn retry tức thời.

## 3. Không đồng nhất SMTP 4xx và 5xx với chính sách failover

SMTP có các nhóm reply code phổ biến:

- **4xx:** lỗi tạm thời tại giao dịch/lệnh hiện tại.
- **5xx:** từ chối vĩnh viễn cho yêu cầu hiện tại.

Tuy nhiên, **5xx không tự động có nghĩa “mọi provider đều không thể gửi”**, cũng như **4xx không tự động có nghĩa “an toàn chuyển provider”**.

| Tình huống | Mức độ và ngữ cảnh | Quyết định thường phù hợp |
| --- | --- | --- |
| `550 5.1.1` khi RCPT TO, mailbox không tồn tại | Recipient-level permanent theo bằng chứng cụ thể | Dừng; không thử B với cùng recipient |
| `553` do địa chỉ From không được phép | Sender identity/configuration | Dừng để sửa quyền; không thử “lách” bằng B |
| `554 5.7.x` nội dung bị từ chối bởi chính sách | Content/policy; cần điều tra lý do | Không tự failover B để né policy |
| `552` kích thước vượt giới hạn | Payload/size; cần xem từng provider và yêu cầu sản phẩm | Không chuyển mù; điều chỉnh MIME/attachment hoặc route được phê duyệt |
| `535` SMTP AUTH thất bại | Lỗi credential/account A, không phải recipient | Tạm dừng A, sửa secret; B chỉ khi là route được phê duyệt và vẫn đáp ứng quyền gửi |
| `421` A tạm unavailable trước submit | Có thể là outage tuyến A | Failover có điều kiện hoặc retry sau |
| `451` remote service tạm lỗi | Có thể là temporary recipient/domain/provider | Phân loại bằng phase và provider context; không chuyển mù |
| `452` resource limitation | Có thể do capacity/quota | Throttle/backoff; chỉ chuyển B nếu được phép |
| Connection refused trước SMTP session | Outage hạ tầng A có bằng chứng | B có thể phù hợp khi payload hợp lệ |
| DNS lookup SMTP host A thất bại | Không truy cập được tuyến A | B có thể phù hợp nếu tên B và TLS của B hợp lệ |
| Socket timeout sau DATA, không có final reply | Outcome không xác định | Không failover tức thời, đối soát |
| `JavaMailSender.send()` thành công | Relay A chấp nhận submission | Không tự failover vì chưa thấy delivered |

Giá trị phản hồi và enhanced status code tùy SMTP provider, vị trí lệnh (AUTH, MAIL FROM, RCPT TO, DATA) và implementation. Đọc cả **SMTP phase, reply/enhanced status, response reason và provider contract**; không viết `if (code >= 500) { tryProviderB(); }`.

### Ví dụ phân biệt 5xx ở nhiều giai đoạn

~~~text
AUTH -> 535 5.7.8 Authentication credentials invalid
    -> Credential A sai; không làm địa chỉ khách hàng thành invalid.

MAIL FROM -> 553 5.7.1 Sender not permitted
    -> Identity / quyền gửi không hợp lệ trên tuyến đang dùng.

RCPT TO -> 550 5.1.1 User unknown
    -> Recipient cụ thể bị từ chối permanent.

DATA -> 554 5.7.1 Message rejected due to policy
    -> Điều tra content/reputation/policy; không “đi đường vòng” mù.
~~~

Một số provider có thể trả cùng mã 550 cho nhiều nguyên nhân. Vì vậy, việc đọc riêng ba chữ số 550 là chưa đủ để áp dụng suppression vĩnh viễn. Nếu bằng chứng chưa rõ, cần giữ trạng thái **NEEDS_REVIEW** hoặc phân loại thận trọng thay vì gán recipient invalid.

## 4. Vì sao chuyển provider có thể làm vấn đề nghiêm trọng hơn?

### 4.1. Tăng số lần gửi mà không tăng khả năng thành công

Nếu địa chỉ mailbox không tồn tại, cả A và B đều có thể mất tài nguyên xác thực, SMTP connection, quota và retry cho một message không có khả năng giao.

### 4.2. Gây duplicate

Nếu A đã accepted nhưng event `delivered` đến muộn, gửi B khi chưa đủ bằng chứng sẽ tạo hai bản. Điều này đặc biệt nguy hiểm với OTP, reset link, hóa đơn có yêu cầu kiểm toán hoặc cảnh báo bảo mật.

### 4.3. Tránh né chính sách của provider

Nếu A từ chối nội dung vì consent, abuse hoặc content policy, cố đưa qua B để được chấp nhận có thể vi phạm chính sách, uy tín gửi hoặc yêu cầu pháp lý. Provider failover phải phục vụ **tính sẵn sàng hợp lệ**, không phải bỏ qua cơ chế bảo vệ.

### 4.4. Làm bẩn suppression/feedback

Hard bounce và complaint từ A có thể là thông tin cần áp dụng ở cấp recipient trong toàn hệ thống. Nếu chỉ lưu suppression tại adapter A, tuyến B có thể gửi lại cho người đã complaint.

### 4.5. Khuếch đại lỗi theo cấp số nhân

Nếu mỗi provider retry ba lần và có hai provider trong vòng lặp, một message có thể tạo nhiều lời gọi SMTP không phản ánh số attempts trong outbox. Không để cơ chế failover lồng trong retry mà không có **global attempt budget**.

## 5. Kiến trúc multi-provider: một cổng điều phối, nhiều adapter

Thay vì business service tự gọi A rồi catch exception và gọi B, nên có một **mail dispatch gateway** quyết định tuyến gửi theo policy tập trung.

~~~mermaid
flowchart LR
    A["Order / User event"] --> B["Transactional outbox"]
    B --> C["Mail dispatcher"]
    C --> D["Validate payload + eligibility"]
    D --> E["Route / failover policy"]
    E --> F["Rate + concurrency budget"]
    F --> G["Provider A adapter"]
    F --> H["Provider B adapter"]
    G --> I["SMTP / API A"]
    H --> J["SMTP / API B"]
    G --> K["Result normalizer"]
    H --> K
    K --> L["Outbox state + events + metrics"]
~~~

Những thành phần quan trọng:

| Thành phần | Trách nhiệm |
| --- | --- |
| Notification/outbox | Lưu nhu cầu gửi bền vững và idempotency key |
| Payload validator | Kiểm tra recipient, content, expiry, consent, template |
| Provider registry | Những tuyến đã được phê duyệt, capability, quota, From identity |
| Router | Chọn tuyến ban đầu theo region, category, policy |
| Transport adapter | Gọi `JavaMailSender` hoặc provider API |
| Failure normalizer | Chuẩn hóa exception/SMTP reply thành lỗi nội bộ |
| Failover policy | Quyết định STOP/HOLD/RETRY/FAILOVER/RECONCILE |
| Rate/concurrency gate | Bảo vệ tổng tốc độ và tài nguyên từng provider |
| Event processor | Nhận bounce, deferred, complaint và delivery status |
| Audit/metrics | Ghi nhận quyết định tuyến và lý do, không lộ secret |

Đặc biệt, **validator và suppression check phải chạy trước mọi attempt**, kể cả attempt đầu tiên, retry cùng provider, failover và manual replay. Một email hợp lệ lúc enqueue có thể đã hết hạn hoặc recipient đã unsubscribe khi tới lượt gửi.

## 6. Một trạng thái duy nhất là không đủ

Multi-provider mail cần phân biệt submission với delivery và trạng thái nghiệp vụ.

| Trạng thái minh họa | Ý nghĩa | Có tự failover không? |
| --- | --- | --- |
| `PENDING` | Có yêu cầu gửi hợp lệ chưa submit | Có thể chọn route |
| `PROCESSING` | Worker đang sở hữu lease | Không để worker khác claim |
| `RETRY_PENDING` | Lỗi tạm thời, đã đặt lịch | Chỉ khi đến hạn và policy cho phép |
| `HOLD_FOR_CORRECTION` | Dữ liệu/From/content chưa hợp lệ | Không |
| `FAILED_PERMANENT` | Không thể gửi theo evidence hiện có | Không |
| `SUPPRESSED` | Không được gửi theo consent/complaint | Không |
| `EXPIRED` | Thời hạn message/token đã hết | Không |
| `SUBMITTED` | Relay/provider nhận thành công | Không; theo dõi delivery |
| `SUBMISSION_UNKNOWN` | A có thể đã nhận, client thiếu final confirmation | Không failover mù |
| `NEEDS_REVIEW` | Bằng chứng mâu thuẫn/không đủ để quyết định | Chờ đối soát hoặc quyết định có audit |

Trạng thái `SUBMITTED` không có nghĩa inbox delivered. Bounce hoặc complaint có thể đến sau accepted. Không reset `SUBMITTED` thành `PENDING` chỉ vì một lần polling không thấy event delivered.

## 7. Ma trận lỗi: trường hợp tuyệt đối không chuyển mù sang B

| Nhóm lỗi | Bằng chứng ví dụ | Vì sao B không giải quyết | Hành động |
| --- | --- | --- | --- |
| Email address sai cú pháp | Parser/address validation failed | Cùng address vẫn sai | Sửa dữ liệu đầu vào |
| Mailbox không tồn tại xác nhận | RCPT 550 5.1.1, hard bounce tin cậy | Mailbox đích không tồn tại | Suppress/đề nghị cập nhật địa chỉ |
| Recipient unsubscribe | Preference store cập nhật | Quyền nhận đã bị rút | SUPPRESSED |
| Spam complaint | Feedback loop được xác minh | Gửi qua B vẫn là không mong muốn | Suppress marketing; điều tra |
| OTP hết hạn | `expiresAt` trong quá khứ | Nội dung không còn hữu ích | EXPIRED, yêu cầu mã mới |
| Template render lỗi | Missing template/null data/invalid expression | B nhận cùng body lỗi | Sửa template/model trước khi replay |
| MIME lỗi | Multipart, address, encoding không hợp lệ | Không tạo được message chuẩn | FIX_CONTENT |
| Attachment không hợp lệ | File quá lớn/thiếu/không được phép | Đổi route không sửa file | Giảm kích thước/xử lý theo policy |
| Nội dung bị policy chặn | Provider phản hồi policy abuse/content | Chuyển tuyến có thể né cơ chế bảo vệ | Điều tra/sửa nội dung |
| From identity không hợp lệ | Quyền send-as/verified sender thiếu | B cần có quyền riêng, không tự hợp lệ | Sửa quyền hoặc route được phê duyệt |
| Tenant không được dùng B | Jurisdiction/contract/region | Failover vi phạm ràng buộc | Hold/retry A theo policy |
| B không hỗ trợ tính năng | Attachment size, encoding, category | B không thể đảm bảo fidelity | Không chọn B |
| A đã accepted | Final SMTP 250 hoặc provider accepted | Không có submission nào cần retry | Theo dõi downstream |
| A outcome unknown | Mất reply sau DATA | B có thể tạo duplicate | Đối soát trước |

Với những lỗi thuộc chính sách hoặc tuân thủ, cần tránh cách đặt tên `fallbackAllowsPolicyBypass`. Tầng route không được dùng để lách unsubscribe, complaint, suppression hoặc security checks.

## 8. Lỗi vĩnh viễn của request khác lỗi cấu hình riêng provider

Không phải mọi phản hồi 5xx đều chứng minh message “không thể gửi ở mọi nơi”. Cần phân biệt **phạm vi lỗi**:

### 8.1. Permanent ở cấp recipient hoặc nghiệp vụ

- Một mailbox được xác nhận không tồn tại.
- Địa chỉ không hợp lệ và không thể chuẩn hóa.
- Không có consent/đã unsubscribe.
- Attachment bị cấm theo chính sách sản phẩm.
- OTP hoặc reset token đã hết hạn.

**Kết quả:** dừng việc gửi nội dung hiện tại; không chọn B. Người dùng hoặc nghiệp vụ phải sửa yêu cầu trước khi có notification mới.

### 8.2. Permanent ở cấp cấu hình tài khoản A

- SMTP username/password A không hợp lệ.
- Sender identity chưa được xác minh với A.
- Một cấu hình A đã hết quyền gửi.
- Tenant A không còn quota hợp đồng hay account bị khóa.

Những lỗi này có thể chỉ ảnh hưởng **tuyến A**, nhưng không tự chứng minh B là lựa chọn an toàn. Có thể:

1. Tạm dừng lane A và sửa cấu hình/credential.
2. Kiểm tra B có được **phê duyệt** cho loại email, sender identity, tenant, quốc gia, chính sách lưu trữ dữ liệu và quota hay không.
3. Chỉ cân nhắc B nếu lỗi không liên quan consent/content/recipient, và A chắc chắn chưa accepted.
4. Giữ audit cho lý do chuyển tuyến.

Vì thế policy hợp lý thường là **HOLD_FOR_OPERATOR** với lỗi account/config chưa phân loại đầy đủ, không phải `FAILOVER` mặc định. Với một incident đã được xử lý trước và B là standby route được phép, operator hoặc policy có thể cho phép route switch có kiểm soát.

### 8.3. Temporary ở cấp hạ tầng A

- DNS của endpoint A không resolve.
- TCP connection refused/timeout trước submit.
- Provider A có outage được xác nhận.
- A đang throttling hoặc queue quá tải theo bằng chứng.

Đây là các tình huống B có thể tăng availability, nhưng vẫn phải kiểm tra eligibility, budget, duplicate risk và điều kiện nghiệp vụ trước khi gửi.

### 8.4. Lỗi chưa xác định

Nếu adapter chỉ trả `MailSendException` mà không biết nguyên nhân, không nên suy luận “A lỗi nên dùng B”. Cần:

- Lưu original cause/SMTP phase đã được làm sạch.
- Phân loại tạm là `UNCLASSIFIED`.
- Defer hoặc hold theo chính sách thận trọng.
- Đối soát nếu có khả năng A đã nhận message.
- Cải thiện transport instrumentation trước khi tự động failover.

**Unknown error** khác **unknown outcome**. Unknown error chỉ nói chưa phân loại được lỗi; unknown outcome có nghĩa không biết chắc SMTP relay đã nhận message. Cả hai không đủ điều kiện failover mù, nhưng hướng điều tra có thể khác nhau.

## 9. Giai đoạn SMTP quyết định rủi ro failover

~~~text
Application                 SMTP relay A
    |                           |
    | --- TCP connect --------> |
    | <------ 220 -------------- |
    | --- EHLO / TLS / AUTH ---> |
    | --- MAIL FROM ----------> |
    | --- RCPT TO ----------->  |
    | --- DATA -------------->  |
    | <------ 354 ------------  |
    | --- headers/body -------> |
    | --- CRLF . CRLF --------> |
    |                           |
    | <------ final reply ----- |
~~~

### Trước khi body được submit

Nếu connect không thành công hoặc server từ chối AUTH trước DATA, lần thử này không thể đã submit body tới A. Vấn đề quan trọng lúc đó là **phân loại lỗi và eligibility**, không phải duplicate do chính lần thử đó.

Tuy nhiên, nếu notification đã có **attempt khác** từng được A accepted hoặc có `SUBMISSION_UNKNOWN`, vẫn cần kiểm tra toàn bộ lịch sử; không chỉ nhìn attempt mới nhất.

### Sau khi A trả final success

Nếu client nhận final SMTP 250 sau DATA, A đã nhận trách nhiệm xử lý message theo giao thức. **Không chuyển B** chỉ vì chưa nhận được delivered event trong vài giây/phút.

### Sau DATA nhưng mất phản hồi

Nếu server đã nhận dấu kết thúc body rồi connection đứt trước final reply, client không biết A đã accepted hay chưa. Đổi ngay sang B có thể tạo duplicate. Cần `SUBMISSION_UNKNOWN`, đối soát với provider ID/log nếu có, hoặc quy trình resend theo nghiệp vụ với audit và chấp nhận rủi ro đã được duyệt.

### Server trả final 5xx sau DATA

Nếu server phản hồi một mã 5xx rõ ràng ở cuối DATA, đó là explicit rejection cho SMTP transaction tại A. Nó khác “không biết kết quả”. Tuy nhiên **explicit rejection không tự biến B thành tuyến hợp lệ**: nếu nguyên nhân là content, permission hoặc policy, cần sửa nguyên nhân. Chỉ cân nhắc B sau khi đã phân loại rằng vấn đề riêng A và chuyển tuyến được phép.

## 10. Mô hình kết quả transport trung lập với provider

Ứng dụng nên dịch phản hồi SMTP của từng nhà cung cấp sang một mô hình chung trước khi ra quyết định:

~~~java
package com.example.mail.routing;

public enum FailureKind {
    INVALID_RECIPIENT,
    INVALID_PAYLOAD,
    CONTENT_POLICY_REJECTED,
    SENDER_NOT_AUTHORIZED,
    SMTP_AUTH_REJECTED,
    PROVIDER_UNAVAILABLE,
    PROVIDER_THROTTLED,
    TEMPORARY_RECIPIENT,
    SUBMISSION_OUTCOME_UNKNOWN,
    UNCLASSIFIED
}
~~~

~~~java
package com.example.mail.routing;

public enum FailureScope {
    REQUEST,
    RECIPIENT,
    PROVIDER_ACCOUNT,
    PROVIDER_INFRASTRUCTURE,
    UNKNOWN
}
~~~

~~~java
package com.example.mail.routing;

public record NormalizedMailFailure(
        FailureKind kind,
        FailureScope scope,
        String providerKey,
        String smtpPhase,
        String smtpReplyCode,
        String enhancedStatusCode,
        boolean acceptedByTransport,
        boolean outcomeUnknown
) {
}
~~~

Đây là **model nội bộ**, không phải lớp Spring Mail có sẵn. Không dựa duy nhất vào `MailException.getMessage()` để điền `smtpPhase` hoặc `acceptedByTransport`. Phải dựa trên sự kiện mà adapter thật có thể quan sát và tin cậy; nếu thiếu thì để trạng thái không rõ, không tự điền dữ kiện thuận tiện cho failover.

### Cẩn trọng với `MailException` của Spring

`JavaMailSender.send(...)` không trả provider message ID hoặc một trạng thái `delivered` phổ quát. Những exception có thể gặp:

| Spring/Jakarta Mail signal | Điều có thể biết | Điều còn phải tra cứu |
| --- | --- | --- |
| `MailAuthenticationException` | Có lỗi xác thực | Credential sai, quyền, provider tạm lỗi hay sai AUTH mechanism? |
| `MailSendException` | Một hoặc nhiều message không submit thành công theo transport | Phase, reply code, failed messages, partial success |
| `MailParseException` | Message không parse/chuẩn bị được theo trường hợp | Payload/template lỗi gì? |
| `MailPreparationException` | Lỗi chuẩn bị MIME/message | Dữ liệu đầu vào hay resource lỗi? |
| Jakarta Mail `SMTPSendFailedException` | Có thể có SMTP reply cụ thể | Reply thuộc lệnh/giai đoạn nào, outcome? |
| Jakarta Mail `SMTPAddressFailedException` | Có thể có lỗi liên quan recipient | Có nhiều recipient/partial acceptance không? |
| `SocketTimeoutException` trong cause chain | Có thao tác socket timeout | Timeout trước hay sau dấu kết thúc DATA? |

Một `MailSendException` có thể chứa danh sách failed messages và cause cho từng message. Không viết xử lý giống nhau cho **một người nhận** và **nhiều người nhận**: khi partial-send được bật, một số recipient có thể đã được accepted trong khi một số khác bị từ chối.

### Không mất thông tin của provider

Khi chuẩn hóa, vẫn nên giữ metadata có kiểm soát:

- Provider key và account/route ID.
- SMTP command/phase nếu có.
- Ba chữ số reply và enhanced status.
- Reason family đã chuẩn hóa.
- Provider-specific error key.
- Attempt ID và internal notification ID.
- Thời điểm và trust level của nguồn dữ kiện.

Raw SMTP text có thể chứa email address hoặc dữ liệu nhạy cảm; cần redaction và quyền truy cập. Không ghi password, access token hay toàn bộ MIME body trong log.

## 11. Quy tắc dừng trước khi ra quyết định failover

Một policy nên kiểm tra **các chốt chặn theo thứ tự**, không chỉ xem provider có lỗi hay không.

~~~text
if notification has expired:
    STOP_EXPIRED

if recipient is suppressed or lacks required consent:
    STOP_SUPPRESSED

if payload/template/MIME is invalid:
    STOP_INVALID_CONTENT

if any previous attempt was accepted:
    NO_FAILOVER_ALREADY_SUBMITTED

if any relevant attempt has unknown submission outcome:
    RECONCILE_BEFORE_RETRY

if failure scope is RECIPIENT or REQUEST permanent:
    STOP_PERMANENT

if failure is content/policy or sender authorization:
    HOLD_FOR_CORRECTION

if failure is provider-specific infrastructure:
    evaluate eligible backup providers
else:
    HOLD or RETRY according to conservative policy

if backup is not approved or lacks capacity:
    RETRY_LATER / HOLD
else:
    schedule one controlled failover attempt
~~~

Một số điều kiện (consent, expiry, suppression, provider capability) có thể thay đổi giữa thời điểm quyết định và lúc worker thực sự submit, vì vậy worker cần **kiểm tra lại ngay trước dispatch**, không chỉ lúc enqueue.

### Idempotency key không thay mọi điều kiện

Unique `notificationId` giúp không enqueue trùng một nghiệp vụ. Nhưng ngay cả khi tất cả adapters dùng cùng `Message-ID`, SMTP không bảo đảm mọi relay/mailbox loại trùng. Provider có API idempotency (nếu có) có thể cung cấp cơ chế bổ sung riêng; không thể mặc định `JavaMailSender` có exactly-once semantics.

## 12. Một policy Java nhỏ để chặn failover sai

Ví dụ Java 17 dưới đây tách **quyết định nghiệp vụ** khỏi lời gọi socket:

~~~java
package com.example.mail.routing;

public enum RecoveryAction {
    STOP_PERMANENT,
    HOLD_FOR_CORRECTION,
    RETRY_SAME_PROVIDER_LATER,
    FAILOVER_TO_APPROVED_PROVIDER,
    RECONCILE_UNKNOWN
}
~~~

~~~java
package com.example.mail.routing;

public record CandidateProvider(
        String key,
        boolean approvedForNotification,
        boolean senderAuthorized,
        boolean recipientAndRegionAllowed,
        boolean supportsPayload,
        boolean hasCapacity
) {
    public boolean eligible() {
        return approvedForNotification
                && senderAuthorized
                && recipientAndRegionAllowed
                && supportsPayload
                && hasCapacity;
    }
}
~~~

~~~java
package com.example.mail.routing;

public final class MailFailoverPolicy {

    public RecoveryAction decide(
            NormalizedMailFailure failure,
            CandidateProvider candidate,
            boolean hasPriorAcceptedAttempt,
            boolean hasUnknownAttempt,
            boolean attemptsAvailable) {

        // Chốt an toàn phải được áp dụng trước mọi xem xét tuyến B.
        if (hasPriorAcceptedAttempt || hasUnknownAttempt
                || failure.outcomeUnknown()
                || failure.acceptedByTransport()) {
            return RecoveryAction.RECONCILE_UNKNOWN;
        }

        if (!attemptsAvailable) {
            return RecoveryAction.STOP_PERMANENT;
        }

        return switch (failure.kind()) {
            case INVALID_RECIPIENT,
                 INVALID_PAYLOAD,
                 CONTENT_POLICY_REJECTED ->
                    RecoveryAction.STOP_PERMANENT;

            case SENDER_NOT_AUTHORIZED,
                 SMTP_AUTH_REJECTED ->
                    RecoveryAction.HOLD_FOR_CORRECTION;

            case PROVIDER_UNAVAILABLE,
                 PROVIDER_THROTTLED ->
                    candidate != null && candidate.eligible()
                        ? RecoveryAction.FAILOVER_TO_APPROVED_PROVIDER
                        : RecoveryAction.RETRY_SAME_PROVIDER_LATER;

            case TEMPORARY_RECIPIENT ->
                    RecoveryAction.RETRY_SAME_PROVIDER_LATER;

            case SUBMISSION_OUTCOME_UNKNOWN ->
                    RecoveryAction.RECONCILE_UNKNOWN;

            case UNCLASSIFIED ->
                    RecoveryAction.HOLD_FOR_CORRECTION;
        };
    }
}
~~~

**Giới hạn của code minh họa:**

- `attemptsAvailable` chỉ là một chốt; ứng dụng cần kiểm tra deadline và total budget cho cả A+B.
- `STOP_PERMANENT` khi hết attempts trong ví dụ nghĩa là **kết thúc vòng tự động**, không khẳng định recipient không tồn tại. Tầng lưu trạng thái nên phân biệt `DEAD_LETTER` (hết budget) và `FAILED_PERMANENT` (lỗi không thể gửi).
- `RECONCILE_UNKNOWN` ở đây còn được dùng cho trường hợp `hasPriorAcceptedAttempt`; production nên có kết quả riêng `ALREADY_SUBMITTED` để không trông như phải đối soát mọi accepted attempt.
- Classifier phải phân biệt provider throttling thật với một recipient temporary error; không chuyển mọi 4xx thành `PROVIDER_THROTTLED`.
- `candidate.eligible()` chỉ là snapshot. Worker cần thực hiện eligibility check lại ngay trước send.

Trong môi trường production, có thể tách `DeliveryTerminalReason` thành hai nhóm **lỗi nghiệp vụ/permanent** và **tự động thử đã hết giới hạn**. Không áp dụng suppression recipient nếu chỉ hết retry budget của provider.

### Không viết vòng catch thử tất cả providers

~~~java
// KHÔNG NÊN:
for (JavaMailSender sender : allSenders) {
    try {
        sender.send(message);
        return;
    } catch (MailException ignored) {
        // Mọi lỗi đều bị xem là có thể thử provider kế tiếp.
    }
}
~~~

Đoạn code trên không biết:

- Lỗi có phải `INVALID_RECIPIENT` hoặc `CONTENT_POLICY` không.
- Provider trước đã accepted message chưa.
- Có consent, From permission hay data residency không.
- `MimeMessage` có tương thích/được chuẩn bị đúng cho session của provider kế tiếp không.
- Các lần thử có vượt budget và rate limiter không.

**Không phải bắt lỗi càng rộng thì hệ thống càng sẵn sàng.** Bắt lỗi không phân loại có thể khiến một yêu cầu không hợp lệ bị gửi tới nhiều tuyến với hậu quả khó kiểm soát.

## 13. Lỗi không thể gửi xảy ra trước khi mở kết nối SMTP

Một số trường hợp cần dừng **trước khi tạo message và gọi sender**:

### Địa chỉ email sai

Tại boundary nghiệp vụ, validate cú pháp/required fields; có thể dùng thư viện địa chỉ email hoặc Jakarta Mail `InternetAddress` để kiểm tra cấu trúc, nhưng một địa chỉ đúng cú pháp **không chứng minh mailbox tồn tại**.

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class RecipientSyntax {
    public static boolean isValid(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            InternetAddress address = new InternetAddress(value, true);
            address.validate();
            return value.equals(address.getAddress());
        } catch (AddressException exception) {
            return false;
        }
    }
}
~~~

Đây chỉ là kiểm tra cú pháp theo thư viện/chuỗi đã chuẩn hóa; không thay việc xử lý EAI/internationalized addresses hoặc chính sách sản phẩm khi có yêu cầu. Nếu `InternetAddress` trả về normalized address khác input, có thể cần quy trình normalization rõ ràng thay vì so sánh string như ví dụ.

### Thiếu dữ liệu template

Nếu Thymeleaf/FreeMarker hoặc engine khác không render được vì model thiếu biến hoặc template hỏng, đổi provider không giải quyết. Một công đoạn `render` nên hoàn tất trước `selectProvider` hoặc trước SMTP submit:

~~~text
Notification input
   -> Validate recipient, consent, expiry
   -> Render subject/body from trusted template
   -> Validate MIME/attachment
   -> Choose approved provider
   -> Submit
~~~

Nếu render sai, ghi trạng thái `HOLD_FOR_CORRECTION` hoặc `FAILED_PERMANENT` tùy chính sách, không tạo hai SMTP attempts chỉ vì có hai providers.

### Message đã hết hạn

Một email chứa mã xác thực hết hạn phải dừng. Việc chấp nhận gửi qua provider B sau khi A lỗi sẽ tạo thông báo vô dụng, gây nhầm lẫn và có thể khiến người dùng hiểu nhầm mã vẫn hiệu lực.

## 14. Recipient suppression phải là chính sách dùng chung

Nếu A nhận được hard bounce, complaint hoặc unsubscribe, điều đó không được chỉ cập nhật danh sách riêng của A. Hệ thống gửi cần có một nguồn quyết định suppression thống nhất phù hợp với phạm vi chính sách.

~~~text
Provider A -- hard bounce / complaint -->
                 Suppression store
                         |
                         v
               Shared pre-send check
                 /             \
                v               v
           Provider A       Provider B
~~~

### Phạm vi suppression

Một record suppression nên có:

- Recipient identity hoặc email address đã được chuẩn hóa.
- Tenant/account scope.
- Reason: `HARD_BOUNCE`, `COMPLAINT`, `UNSUBSCRIBE`, `ADMIN_BLOCK`...
- Message category scope: marketing, transactional, security, v.v.
- Source provider/event ID.
- CreatedAt, optional expiry/review status.
- Audit về việc áp dụng hoặc gỡ bỏ.

Không dùng một boolean toàn cục bất biến cho mọi loại mail. Ví dụ unsubscribe newsletter khác với email xác minh bảo mật; nhưng một mailbox được xác nhận không tồn tại cũng không phải địa chỉ thích hợp để cố gửi OTP. Chính sách cụ thể phải theo pháp lý, consent, sản phẩm và mức độ xác thực recipient.

### Tránh suppress chỉ dựa trên tín hiệu không tin cậy

Webhook bounce/complaint cần được xác minh chữ ký và correlation provider/account/recipient. Không cho một HTTP request giả mạo quyết định việc chặn mọi provider.

### Complaint không được bypass

Nếu một recipient đã complaint email marketing, **chuyển sang provider B để tiếp tục marketing là hành vi trái mục tiêu suppression**. Đường gửi qua mọi provider phải dùng cùng eligibility check trước send.

## 15. Provider B chỉ hợp lệ khi đáp ứng đầy đủ yêu cầu tuyến gửi

“Có provider dự phòng” không đồng nghĩa “có thể gửi mọi email qua dự phòng”.

Một tuyến B chỉ đủ điều kiện nếu:

| Điều kiện | Câu hỏi cần trả lời |
| --- | --- |
| Provider contract | B có được dùng cho loại thông điệp này không? |
| Tenant/region/data residency | B được xử lý dữ liệu của tenant và địa bàn này không? |
| Sender authorization | B có quyền gửi `From` hoặc envelope sender dự kiến không? |
| Domain authentication | DKIM/SPF/DMARC alignment, bounce domain/return-path có được cấu hình đúng không? |
| Recipient permissions | Consent/suppression được dùng chung hay đã đồng bộ đáng tin? |
| MIME compatibility | B có hỗ trợ nội dung, attachment size và encoding không? |
| Tracking requirements | B có cung cấp event/correlation cần thiết cho audit hay không? |
| Quota/rate budget | B còn công suất cho email khẩn cấp và lượng failover không? |
| Provider health | B có đang gặp outage hoặc bị throttling tương tự không? |
| Security | B dùng TLS, credential hợp lệ và secret handling đúng policy không? |
| Idempotency | Có nguy cơ A đã nhận message không? B có dedup API nếu dùng HTTP API không? |
| Business constraints | Email có quá hạn, bị hủy hoặc thuộc chiến dịch đã đóng không? |

### Provider B chưa xác minh From

Nếu A lỗi do mạng, nhưng B chưa verify sending domain, gửi qua B có thể thất bại ở `MAIL FROM` hoặc bị remote receiving server từ chối sau submission. Đây là **route không đủ điều kiện**, không phải một cơ hội thử thêm.

### Provider B có quota khác

Nếu B chỉ được dùng cho OTP/security, không được xả toàn bộ backlog marketing qua B sau khi A outage. Router cần xét category và reserved capacity trước khi chọn B.

### Provider B nằm ngoài khu vực cho phép

Một tenant có yêu cầu dữ liệu email chỉ được xử lý tại khu vực nhất định có thể không được dùng B dù B đang khỏe và nhanh hơn. Cần coi đây là **hard eligibility constraint**, không phải yếu tố xếp hạng có thể bị override bởi retry.

### Khác provider, khác chính sách recipient

Khi B có suppression list riêng, ứng dụng không được giả định B đã biết mọi unsubscribe/complaint mà A nhận. Thường cần suppression ở tầng ứng dụng và đồng bộ theo provider requirement, với kiểm tra cuối trước dispatch.

## 16. Thiết kế nhiều JavaMailSender trong Spring

`JavaMailSender` là abstraction gửi mail của Spring; `JavaMailSenderImpl` là implementation SMTP dựa trên Jakarta Mail. Một hệ thống multi-provider có thể khai báo nhiều sender bean, nhưng Spring Boot Mail auto-configuration thông thường **không tự tạo router/failover policy** cho tất cả providers.

Ví dụ cấu hình application-owned riêng theo provider:

~~~yaml
mail:
  routes:
    primary:
      host: smtp-a.example.net
      port: 587
      username: app-a
      tls-mode: starttls
    secondary:
      host: smtp-b.example.net
      port: 587
      username: app-b
      tls-mode: starttls
~~~

Credential thực tế nên lấy từ secret manager/env injection, không đưa password vào source control. YAML trên là namespace minh họa do ứng dụng định nghĩa, **không phải schema multi-provider mặc định của Spring Boot**.

### Tạo sender độc lập

~~~java
package com.example.mail.routing;

import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    public static JavaMailSenderImpl forStartTls(
            String host,
            int port,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "3000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

Đây là cách cấu hình transport cho SMTP submission sử dụng STARTTLS, không áp dụng nguyên vẹn cho provider dùng implicit TLS, OAuth2/XOAUTH2 hoặc REST API. `password` được truyền dưới dạng secret runtime; đừng log `JavaMailSenderImpl` hoặc các field nhạy cảm.

### Bean riêng và registry

~~~java
package com.example.mail.routing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration
public class MultiProviderMailConfig {

    @Bean("primaryMailSender")
    JavaMailSender primaryMailSender(
            PrimarySmtpSecrets secrets) {
        return SmtpSenderFactory.forStartTls(
                secrets.host(),
                secrets.port(),
                secrets.username(),
                secrets.password());
    }

    @Bean("secondaryMailSender")
    JavaMailSender secondaryMailSender(
            SecondarySmtpSecrets secrets) {
        return SmtpSenderFactory.forStartTls(
                secrets.host(),
                secrets.port(),
                secrets.username(),
                secrets.password());
    }
}
~~~

`PrimarySmtpSecrets` và `SecondarySmtpSecrets` là interfaces/types của ứng dụng hoặc adapter secret manager, không có sẵn trong Spring. Khi inject hai sender, dùng `@Qualifier` hoặc registry cấu hình rõ ràng để tránh chọn nhầm bean. Không đổi username/password trên một sender đang dùng chung giữa các thread khi rotation; dùng restart hoặc tạo candidate mới và swap có kiểm soát.

### Adapter SMTP không tự quyết định failover

~~~java
package com.example.mail.routing;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class SmtpProviderAdapter {

    private final String key;
    private final JavaMailSender sender;

    public SmtpProviderAdapter(
            String key, JavaMailSender sender) {
        this.key = key;
        this.sender = sender;
    }

    public void submit(SimpleMailMessage message) {
        sender.send(message);
    }

    public String key() {
        return key;
    }
}
~~~

Adapter chỉ gửi qua một route. Nó không tự catch exception để thử adapter khác. Một lớp ở ngoài phải chuẩn hóa lỗi, kiểm tra state/eligibility và quyết định hành động. `SimpleMailMessage` chỉ phù hợp email plain text đơn giản; với HTML/attachment, dùng `MimeMessage` và tạo message hợp lệ cho sender/session tương ứng.

## 17. Retry/failover không nên thực hiện trong một vòng synchronous không giới hạn

Mẫu code sau thường gây nguy hiểm trong web request:

~~~java
try {
    primary.send(message);
} catch (MailException failure) {
    secondary.send(message);
}
~~~

Những vấn đề:

1. B được gọi với cả `MailParseException`, `MailAuthenticationException` và lỗi recipient permanent.
2. Không có thời gian backoff, giới hạn attempts hoặc quota.
3. Không rõ A đã accepted message trước khi exception xuất hiện chưa.
4. HTTP transaction có thể bị giữ lâu vì hai lần network call.
5. Không có audit lý do chuyển tuyến.
6. Không kiểm tra lại consent/expiry/suppression tại thời điểm B send.

Với transactional outbox, một hướng an toàn hơn:

~~~text
Business transaction
    -> Persist notification + outbox
    -> Commit

Worker claims due record
    -> Validate business prerequisites
    -> Choose provider A
    -> Reserve provider-specific budget
    -> Attempt submit A
    -> Normalize outcome
    -> Persist outcome + next action

If eligible for B:
    -> Persist scheduled failover attempt
    -> Release lease
    -> Worker later claims due attempt B
    -> Revalidate + reserve B budget
    -> Submit B once
~~~

Việc đặt lịch B **không có nghĩa phải đợi nhiều phút** nếu có outage thực; một số hệ thống có thể cho failover nhanh. Nhưng mọi lần gọi phải được ghi vào attempt history và kiểm soát quota. Chọn xử lý qua worker bền vững thường giúp kiểm soát concurrency và duplicate tốt hơn vòng catch synchronous.

## 18. State machine cho nhiều provider

Một message nghiệp vụ có thể có nhiều attempts ở những route khác nhau nhưng chỉ một **yêu cầu gửi bền vững**.

~~~text
PENDING
   |
   v
CLAIMED
   |
   v
ATTEMPT_A
   |
   +-- Accepted --------------------> SUBMITTED
   |
   +-- Unknown ---------------------> SUBMISSION_UNKNOWN
   |
   +-- Invalid/Policy --------------> HOLD / FAILED_PERMANENT
   |
   +-- Provider temporary ----------> RETRY_PENDING / FAILOVER_SCHEDULED
                                         |
                                         v
                                      ATTEMPT_B
                                         |
                                         +--> SUBMITTED
                                         +--> RETRY_PENDING / DEAD_LETTER
                                         +--> HOLD / UNKNOWN
~~~

Không nên tạo một outbox record *mới* cho mỗi lần provider thất bại nếu điều đó làm mất liên kết idempotency với notification gốc. Nên lưu một notification ID và nhiều provider-attempt IDs.

### Trạng thái đề xuất cho attempt

| Attempt status | Ý nghĩa |
| --- | --- |
| `READY` | Đã lên kế hoạch, chưa gọi transport |
| `SENDING` | Đã claim và đang dùng route |
| `ACCEPTED` | Relay chấp nhận submission |
| `REJECTED_TEMPORARY` | Có response từ chối tạm thời |
| `REJECTED_PERMANENT` | Có response từ chối permanent theo phase |
| `FAILED_BEFORE_SUBMISSION` | Transport không đi đến bước submit body |
| `OUTCOME_UNKNOWN` | Có khả năng provider đã accepted |
| `CANCELLED` | Attempt không còn hợp lệ/đã thay bằng quyết định khác |

Projection tổng hợp ở notification level phải xét **tất cả attempts**, không chỉ attempt mới nhất. Nếu attempt A đã ACCEPTED, không cho attempt B gửi vì một webhook của A đến trễ hoặc một retry scheduler khác đang xem trạng thái cũ.

## 19. Database: lưu lý do ngừng và tuyến đã thử

Một schema khái niệm:

~~~sql
CREATE TABLE mail_notification (
    id                   VARCHAR(100) PRIMARY KEY,
    idempotency_key      VARCHAR(250) NOT NULL UNIQUE,
    recipient_key        VARCHAR(100) NOT NULL,
    category             VARCHAR(100) NOT NULL,
    status               VARCHAR(50) NOT NULL,
    created_at           TIMESTAMP NOT NULL,
    expires_at           TIMESTAMP,
    next_attempt_at      TIMESTAMP,
    stop_reason          VARCHAR(100)
);

CREATE TABLE mail_provider_attempt (
    id                   VARCHAR(100) PRIMARY KEY,
    notification_id      VARCHAR(100) NOT NULL,
    provider_key         VARCHAR(100) NOT NULL,
    attempt_number       INTEGER NOT NULL,
    status               VARCHAR(50) NOT NULL,
    smtp_phase           VARCHAR(100),
    reply_code           VARCHAR(20),
    failure_kind         VARCHAR(100),
    created_at           TIMESTAMP NOT NULL,
    finished_at          TIMESTAMP,
    FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id),
    UNIQUE (notification_id, attempt_number)
);

CREATE TABLE mail_route_decision (
    id                   VARCHAR(100) PRIMARY KEY,
    notification_id      VARCHAR(100) NOT NULL,
    from_provider        VARCHAR(100),
    to_provider          VARCHAR(100),
    action               VARCHAR(100) NOT NULL,
    normalized_reason    VARCHAR(100) NOT NULL,
    decided_at           TIMESTAMP NOT NULL
);
~~~

Schema rút gọn; production cần bổ sung tenant scope, recipient-level tracking, attempt ownership/lease, event storage, indexes, constraint và retention/audit. `provider_key` là một định danh nội bộ, không phải credential.

### Vì sao lưu cả stop reason?

Ví dụ:

~~~text
notification: notif-1042
status: FAILED_PERMANENT
stopReason: INVALID_RECIPIENT
attempts:
  - provider=A, smtpPhase=RCPT_TO, replyCode=550
routeDecision:
  - STOP_PERMANENT, not routed to B
~~~

Người vận hành cần chứng minh **tại sao hệ thống không failover** chứ không chỉ nhìn email không đến. Stop reason giúp phân biệt lỗi recipient với outage và quyết định điều tra đúng.

### Không tăng attempts khi chưa gọi transport

Nếu worker kiểm tra payload invalid, recipient suppressed hoặc provider B không đủ quota **trước khi gửi**, đó là validation/deferred decision, không phải một SMTP attempt mới. Metrics và attempt history nên phản ánh số lần gọi transport thực.

## 20. Kiểm soát nhiều worker bằng lease và fencing

Nếu hai replica cùng thấy A lỗi và cùng chọn B, chúng có thể gửi trùng. Cần cơ chế claim atomically:

1. Chọn notification `PENDING` hoặc `RETRY_PENDING` đã đến hạn.
2. Gán `PROCESSING`, `leaseOwner`, `leaseUntil` và generation trong transaction.
3. Commit claim.
4. Thực hiện SMTP send ngoài transaction database.
5. Ghi kết quả nếu lease owner/generation vẫn hợp lệ.

Với PostgreSQL, một phần truy vấn:

~~~sql
SELECT id
FROM mail_notification
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

Trong cùng transaction, worker phải UPDATE trạng thái/lease của các ID vừa chọn trước khi commit; câu SELECT đơn lẻ **không tự tạo claim bền vững**. Các database khác có cơ chế locking/cas khác.

### Lease không tạo exactly-once SMTP

Nếu worker A đã submit thành công nhưng chết trước khi ghi `SUBMITTED`, lease có thể hết và worker khác claim lại. Vì vậy:

- Không reset mọi `PROCESSING` hết lease thành `PENDING` một cách mù quáng.
- Ghi nhận phase/attempt outcome đáng tin nếu có.
- Dùng `SUBMISSION_UNKNOWN` và reconciliation cho cửa sổ không chắc chắn.
- Áp dụng fencing token để worker cũ không ghi đè state mới.

Fencing token giúp bảo vệ database state, **không thu hồi được email đã đi ra ngoài ứng dụng**.

## 21. Multi-recipient: không failover toàn message nếu chỉ một địa chỉ lỗi

Một MIME message có nhiều To/Cc/Bcc có thể được SMTP relay A chấp nhận cho một số recipient và từ chối recipient khác. Hành vi partial-send phụ thuộc Jakarta Mail provider/SMTP configuration, chẳng hạn thuộc tính `mail.smtp.sendpartial` trong nhiều implementation.

Ví dụ:

~~~text
RCPT TO: alice@example.org  -> 250 accepted
RCPT TO: bob@example.org    -> 550 5.1.1 user unknown
DATA                        -> may or may not proceed
~~~

Nếu service chỉ thấy `MailSendException` rồi gửi **toàn bộ message** qua B, Alice có thể nhận bản thứ hai còn Bob vẫn không tồn tại.

### Hướng thiết kế

- Với transactional mail cá nhân hóa, nên ưu tiên **một recipient cho một notification/submission** khi phù hợp.
- Nếu nhiều recipient là yêu cầu bắt buộc, lưu trạng thái ở **recipient-attempt level**.
- Phân biệt accepted, rejected temporary và rejected permanent cho từng recipient.
- Không failover recipient đã accepted.
- Không failover recipient permanent invalid chỉ vì những recipient khác đang có lỗi tạm thời.
- Không dùng một boolean `allFailed` khi transport có partial acceptance.

Một test integration dùng SMTP fake trả 250 cho recipient đầu, 550 cho recipient sau có thể xác minh `JavaMailSenderImpl` và adapter ghi kết quả theo cấu hình dự án.

## 22. Provider A báo hard bounce sau khi đã accepted

Sau khi A accepted message, relay có thể tiếp tục retry với remote MX, rồi nhận kết quả bounce cuối. Tình huống này khác lỗi submit ngay.

~~~text
Spring Mail -> Provider A SMTP: 250 accepted
     |
     v
Notification = SUBMITTED
     |
     v
Provider A -> Recipient MX: 550 5.1.1
     |
     v
Provider event: HARD_BOUNCE
     |
     v
Suppress recipient / mark downstream delivery failed
     |
     X
No automatic Provider B resend
~~~

Một hard bounce đáng tin về mailbox không tồn tại là lý do **ngừng gửi tiếp tới recipient đó**, không phải tín hiệu dùng B.

### Provider deferred

Nếu A báo `DEFERRED`, thường chính A đang sở hữu retry tới remote MX. Không tạo một bản gửi mới qua B nếu chưa có tín hiệu A đã kết thúc/đã hủy trách nhiệm giao thư và một quyết định nghiệp vụ riêng cho phép resend.

### Complaint

Nếu A gửi `COMPLAINED` event, xử lý suppression ở tầng dùng chung trước các lần gửi mới qua B. Không dùng provider switching để né feedback loop.

### Webhook có thể trễ/trùng

Provider events có thể đến không theo thứ tự. Cần xác thực chữ ký, lưu event bền vững, dedup provider event ID có scope và correlate theo provider message ID, attempt ID và recipient. Không cập nhật notification status đơn giản bằng event cuối được nhận.

## 23. Tách “kết thúc retry” khỏi “recipient permanent invalid”

Một hệ thống có thể dừng gửi vì nhiều nguyên nhân rất khác nhau:

| Trường hợp | Kết quả vận hành | Có suppress recipient không? |
| --- | --- | --- |
| RCPT `550 5.1.1` xác nhận mailbox không tồn tại | `FAILED_PERMANENT` hoặc `BOUNCED` theo stage | Có thể, theo policy và nguồn dữ liệu tin cậy |
| Template lỗi không render | `HOLD_FOR_CORRECTION` | Không |
| MIME vượt giới hạn sản phẩm | `HOLD_FOR_CORRECTION` | Không |
| Campaign hết hạn | `EXPIRED` | Không nhất thiết |
| Người dùng unsubscribe marketing | `SUPPRESSED` | Có, theo category |
| A outage, đã dùng hết số attempts | `DEAD_LETTER` / `RETRY_BUDGET_EXHAUSTED` | Không |
| A đã accepted | `SUBMITTED` | Không |
| Mất final reply | `SUBMISSION_UNKNOWN` | Không |
| Account A bị khóa | `HOLD_FOR_PROVIDER_RECOVERY` | Không |

Nếu dùng cùng một status `FAILED` rồi tự thêm mọi địa chỉ vào suppression, hệ thống có thể cấm gửi cho recipient hợp lệ chỉ vì provider down. Nếu xem mọi `FAILED` là cơ hội thử B, nó lại có thể gửi cho recipient đã unsubscribe. Do đó nên lưu **stop reason** ngoài status và đánh giá ở policy.

### Policy cần thể hiện hai trục

1. **Có được phép thử một submission nữa không?**
2. **Có được phép dùng provider khác không?**

Ví dụ, một lỗi 451 tạm thời có thể cho phép retry sau, nhưng tenant chỉ được dùng provider A, nên **không được failover**. Ngược lại, A đang unavailable và B được phê duyệt, hệ thống có thể chọn B mà không cần retry A quá nhiều.

### Các quyết định không nên bị “override” bởi ưu tiên khẩn cấp

Email OTP quan trọng nhưng không hợp lệ nếu đã hết hạn. Một cảnh báo bảo mật cần đến nhanh nhưng không có nghĩa được bypass suppression quy định hoặc gửi qua provider không được phép xử lý dữ liệu tenant. Priority giúp phân bổ quota **trong phạm vi tuyến hợp lệ**, không biến một yêu cầu sai thành hợp lệ.

## 24. Giới hạn ngân sách lần gửi ở cấp notification

Chạy nhiều providers làm tăng nguy cơ nhân số attempts:

~~~text
Outbox retry limit:        5
Provider A adapter retry:  3
Provider B adapter retry:  3
Broker redelivery:         Có thể xảy ra
~~~

Nếu mỗi lớp tự retry mà không phối hợp, số lời gọi transport thực có thể vượt xa dự kiến. Cần một **global attempt budget** cho notification và hạn mức riêng cho từng provider/route.

### Đếm đúng physical submissions

Một attempt nên được ghi khi transport thực sự bắt đầu gọi SMTP/API. Các thao tác sau **không tự được coi là SMTP attempt**:

- Validation từ chối recipient.
- Template render thất bại trước send.
- Suppression check từ chối.
- Không còn rate token.
- Provider B không đủ quyền hoặc quota.
- Route policy trả `HOLD`.

Nếu adapter nội bộ đã có retry, cần đếm/quan sát các lời gọi transport thật, không chỉ số lần `dispatcher.dispatch()`.

### Ví dụ budget

Giả sử một notification được phép **tối đa 4 lần submit thực**:

~~~text
Attempt 1: Provider A -> TCP refused
Attempt 2: Provider A -> TCP refused
Attempt 3: Provider B -> SMTP 421
Attempt 4: Provider B -> SMTP 250 accepted

Total physical attempts = 4
Final submission state = SUBMITTED
~~~

Nếu B trả `550 5.1.1` vì mailbox không tồn tại ở attempt 3, **không có attempt 4** chỉ vì budget còn 1. Một lỗi permanent dừng vòng thử độc lập với quota chưa dùng hết.

### Retry budget và deadline

Không dùng chỉ attempts count. Thêm:

- `expiresAt` hoặc `maxAge`.
- `nextAttemptAt` và backoff.
- Số attempts tối đa trên mỗi provider.
- Global messages/second và per-recipient/day nếu chính sách yêu cầu.
- Quyền dùng provider B theo category/tenant.

Một OTP có thể vẫn còn attempts nhưng đã hết TTL trước khi được gửi qua B. Trường hợp đó phải `EXPIRED`.

## 25. Backoff, jitter và circuit breaker cho lỗi được phép retry

Với outage thật ở A, một số yêu cầu hợp lệ có thể failover sang B. Tuy nhiên, **chuyển tuyến không được phá các giới hạn tải**.

### Exponential backoff

Một công thức thường dùng:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

Trong đó:

- `n`: số lần lỗi đã hoàn tất.
- `d0`: thời gian chờ cơ sở.
- `dmax`: thời gian chờ tối đa.
- Jitter giúp phân tán các lần thử, tránh hàng nghìn job cùng đến hạn.

Không dùng jitter làm thay thế global rate limiter. Khi backlog quá lớn, dù thời gian retry được phân tán, tốc độ gửi thực vẫn phải nằm trong quota của B.

### Circuit breaker theo provider/account

Một breaker có thể mở khi A bị outage diện rộng:

~~~text
Provider A:
  CLOSED -> OPEN -> HALF_OPEN -> CLOSED

Provider B:
  Independent health/budget, not affected by A's state alone
~~~

Không mở breaker toàn provider chỉ vì một recipient bị từ chối `550 5.1.1`. Permanent recipient error không phải tín hiệu hạ tầng A outage.

Khi A OPEN, không có nghĩa phải chuyển tất cả email sang B. Router vẫn cần eligibility, preference, expiry, sender identity và B capacity. Nếu B cũng bị outage, giữ outbox thay vì chuyển vòng lặp A→B→A.

### Không chọn B nếu B đang thiếu quota

Ví dụ B có ngân sách giới hạn chỉ phục vụ email bảo mật. Khi A outage, marketing backlog có thể lớn gấp hàng nghìn lần lưu lượng thường ngày. Nếu route marketing qua B, OTP mới có thể bị chậm. Cần quota theo category và reserved capacity, không chỉ “B healthy”.

## 26. Không dùng failover để né rate limit hoặc complaint policy

Một số lỗi mang tính giới hạn dịch vụ chứ không phải lỗi địa chỉ:

- Provider A trả throttling vì vượt quota.
- A giảm tốc do gửi quá nhiều đến một recipient domain.
- A tạm chặn account vì spam complaints.

Cần phân biệt:

**Capacity failover hợp lệ:** B là provider dự phòng đã được phê duyệt với quota, sender identity và recipient policy tương thích. Có thể phân phối thêm một phần lưu lượng không vượt hợp đồng.

**Policy circumvention không hợp lệ:** A chặn vì abuse/complaint nhưng hệ thống cố gửi nội dung tương tự qua B để vượt bộ lọc. Cần dừng và điều tra nguyên nhân thay vì gửi sang nơi khác.

### SMTP 4xx không luôn là “đổi provider”

Một `451` ở RCPT TO có thể là mailbox tạm unavailable; việc chuyển provider có thể không giúp vì remote MX vẫn là một. Nếu vấn đề nằm ở recipient domain, B có thể nhận cùng lỗi, tăng số requests tới remote domain và làm tình hình xấu hơn.

Chỉ nếu có bằng chứng A-route-specific và B được phép, failover mới là quyết định có cơ sở.

## 27. Cấu hình tính hợp lệ theo từng nhà cung cấp

Trong một hệ thống thực tế, các điều kiện không nên được hardcode thành `if (provider.equals("A"))` rải rác nhiều nơi. Có thể mô hình hóa:

~~~java
public record ProviderCapabilities(
        String providerKey,
        boolean supportsHtml,
        boolean supportsAttachments,
        long maxMessageBytes,
        boolean supportsDeliveryEvents,
        boolean verifiedSender,
        boolean eligibleForTransactional,
        boolean eligibleForMarketing
) {
}
~~~

Khi kiểm tra một notification:

1. Loại email có thuộc category provider được phê duyệt không?
2. Nội dung có chứa attachment và B có hỗ trợ không?
3. Kích thước ước tính của MIME có vượt `maxMessageBytes` không?
4. From/envelope sender có được B cho phép không?
5. B có hỗ trợ theo dõi kết quả cần cho audit/SLA không?
6. Region, tenant, dữ liệu nhạy cảm có được B xử lý không?

**Không tự suy luận maxMessageBytes từ kích thước file thô.** MIME encoding, base64 và headers có thể làm message lớn hơn attachment gốc; nên đo hoặc ước tính có biên an toàn theo provider.

### Thay đổi provider có thể thay đổi MIME

Với hai SMTP senders, thông điệp nên được xây dựng từ **một domain notification/payload đã xác thực**. Các cấu hình From/Reply-To/Return-Path/DKIM có thể khác theo route và phải được chuẩn bị đúng.

Không thay nội dung một cách lén lút ở adapter B để vượt policy của A. Nếu cần giảm kích thước attachment hoặc thay template, đó là một **quyết định nội dung mới** phải được xác minh, không phải automatic retry cùng payload.

## 28. Giữ nguyên ý nghĩa của notification qua provider

Một thông điệp nghiệp vụ có thể có:

~~~text
notificationId:     notif-9001
businessKey:        ORDER_PAID:order-800:recipient-42
category:           TRANSACTIONAL
recipient:          recipient-42
payloadVersion:     order-receipt-v3
expiresAt:          optional
preferredProvider:  A
eligibleFallback:   B
~~~

Router có thể chọn route khác, nhưng:

- Không tự tạo một idempotency key mới làm mất liên hệ với yêu cầu gốc.
- Không tạo OTP/token mới chỉ vì A lỗi; nếu cần mã mới, nghiệp vụ phải sinh notification mới.
- Không gửi lại hóa đơn có dữ liệu cũ khi đơn hàng đã được điều chỉnh, trừ khi policy ghi rõ.
- Không đổi From domain gây hiểu nhầm người nhận hoặc phá sự xác thực domain.
- Không bỏ attachment/bớt nội dung để được B nhận nếu điều đó thay đổi ý nghĩa nghiệp vụ mà chưa được phê duyệt.

Sự tương đương của hai tuyến không chỉ là “cùng chữ text”; nó còn gồm quyền gửi, nội dung, cách xử lý dữ liệu và thông tin xác thực/ghi nhận kết quả.

## 29. Tình huống điển hình: lỗi recipient 550

Giả sử ứng dụng gửi hóa đơn:

~~~text
Notification: receipt-184
Recipient: buyer@example.org
Provider A:
  MAIL FROM  -> 250
  RCPT TO    -> 550 5.1.1 User unknown
~~~

**Quyết định:**

1. Ghi attempt của A bị từ chối ở RCPT TO.
2. Normalize `INVALID_RECIPIENT` khi reply/provider đủ tin cậy.
3. Chuyển notification sang `FAILED_PERMANENT` hoặc trạng thái tương đương.
4. Cập nhật suppression/đề nghị khách hàng sửa email theo policy.
5. **Không gửi qua B.**
6. Giữ audit để giải thích vì sao email không gửi.

Nếu một nhân viên sửa địa chỉ nhận sau khi xác minh, hệ thống có thể tạo **notification mới** hoặc một tác vụ replay được kiểm soát theo nghiệp vụ. Không đơn giản chuyển A→B với cùng địa chỉ đã bị từ chối.

## 30. Tình huống: nội dung không đúng chính sách

Ví dụ A từ chối một email có attachment vi phạm chính sách:

~~~text
Provider A:
  DATA -> 554 5.7.1 Content rejected

Provider B:
  available and accepts same MIME type
~~~

**Không nên** lấy “B có thể accepted” làm lý do thử. Nếu nguyên nhân là chính sách nội dung phải tôn trọng (ví dụ payload nguy hiểm, liên kết lừa đảo, attachment bị cấm), tiếp tục qua B có thể làm tăng rủi ro.

Thay vào đó:

1. Tạm dừng message.
2. Ghi code/phase và reason đã làm sạch.
3. Phân biệt giới hạn kỹ thuật (ví dụ B hỗ trợ kích thước lớn hơn) với content policy rejection thực sự.
4. Sửa nội dung hoặc quyền gửi theo quy trình được phép.
5. Đảm bảo request mới còn consent/expiry.
6. Chỉ replay qua tuyến hợp lệ sau khi nguyên nhân đã được khắc phục.

### Attachment quá lớn có ngoại lệ không?

Giả sử A chỉ nhận message tối đa một kích thước nhất định, B có giới hạn cao hơn và sản phẩm **cho phép** B xử lý nội dung này. Đây có thể là bài toán **chọn route phù hợp theo capability trước khi gửi**, không phải cứ để A từ chối rồi dùng B.

Nếu A đã từ chối do message size và B có thể nhận hợp lệ, một route correction có kiểm soát có thể phù hợp **sau khi xác minh**. Nhưng chính sách mặc định không nên là thử vô hạn các providers để tìm nơi chấp nhận bất kỳ payload nào.

## 31. Tình huống: provider A outage trước submit

~~~text
Provider A:
  DNS lookup smtp-a.example.net -> timeout

Provider B:
  Verified sender, correct TLS, healthy quota
  Approved for notification category/tenant
~~~

Hướng xử lý:

1. Ghi lỗi `PROVIDER_UNAVAILABLE` ở A, không gán recipient invalid.
2. Kiểm tra notification chưa hết hạn, chưa suppress và không có prior accepted/unknown attempt.
3. Xác nhận B đủ điều kiện và còn rate budget.
4. Lên lịch một attempt B và giữ idempotency key gốc.
5. Ghi route decision A→B với reason `A_ENDPOINT_UNAVAILABLE`.
6. Theo dõi B submission result, không tiếp tục A song song.

Đây là trường hợp failover có thể **thật sự tăng availability**. Nó khác hoàn toàn mailbox không tồn tại hoặc content bị cấm.

## 32. Tình huống: SMTP AUTH A thất bại

Giả sử A trả `535`:

~~~text
Provider A:
  SMTP AUTH -> 535 invalid credentials
Provider B:
  independent credential, healthy
~~~

Lỗi AUTH chỉ chứng minh account A không xác thực được, không chứng minh notification sai. Nhưng **không nên luôn chuyển sang B**:

- Có thể A là provider duy nhất được contract cho phép.
- B chưa được xác minh From domain.
- AUTH error có thể xuất hiện do một cấu hình TLS sai chung.
- Khi A bị compromise, security incident có thể yêu cầu dừng dispatch.
- B có thể có một quota bảo vệ riêng cho OTP.

Policy gợi ý: `HOLD_FOR_CORRECTION` tại account A, alert secret owner, xử lý rotation. Nếu B là standby route đã được phê duyệt và có runbook chuyển route rõ, một operator/automation có thể bật failover **sau khi kiểm tra mọi điều kiện**. Không để catch `MailAuthenticationException` tự động chuyển B cho mọi message.

## 33. Tình huống: timeout sau DATA rồi B đang khỏe

~~~text
Provider A:
  DATA body sent
  final response lost

Provider B:
  healthy
~~~

Trong trường hợp này, trạng thái đúng ban đầu thường là `SUBMISSION_UNKNOWN`, **không phải** `PROVIDER_UNAVAILABLE_SAFE_TO_FAILOVER`.

Một hướng xử lý:

1. Không gửi B ngay.
2. Lưu attempt ID, Message-ID, provider route và thời gian.
3. Tra provider event API/relay queue logs nếu có.
4. Nếu có bằng chứng A đã accepted, cập nhật `SUBMITTED`.
5. Nếu có bằng chứng A chắc chắn từ chối/chưa nhận, cân nhắc retry/failover theo policy.
6. Nếu không thể biết, áp dụng quyết định resend dựa trên rủi ro nghiệp vụ và audit.

Không tuyên bố exactly-once SMTP delivery. Ngay cả khi giữ cùng `Message-ID`, các hệ thống nhận không bắt buộc loại bỏ duplicate.

## 34. Unit test policy: chứng minh lỗi permanent không chọn B

Để tránh hồi quy khi thêm provider mới, test cần khẳng định các tình huống **phải dừng**, không chỉ test đường failover thành công.

Với các enum, record và `MailFailoverPolicy` ở phần trước, có thể dùng JUnit 5:

~~~java
package com.example.mail.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class MailFailoverPolicyTest {

    private final MailFailoverPolicy policy =
            new MailFailoverPolicy();

    private static CandidateProvider approvedB() {
        return new CandidateProvider(
                "B",
                true,  // notification category approved
                true,  // sender verified
                true,  // tenant/region/recipient allowed
                true,  // payload supported
                true); // capacity available
    }

    private static NormalizedMailFailure failure(
            FailureKind kind,
            FailureScope scope) {
        return new NormalizedMailFailure(
                kind,
                scope,
                "A",
                "RCPT_TO",
                "550",
                "5.1.1",
                false,
                false);
    }

    @ParameterizedTest
    @EnumSource(value = FailureKind.class, names = {
            "INVALID_RECIPIENT",
            "INVALID_PAYLOAD",
            "CONTENT_POLICY_REJECTED"
    })
    void neverFailsOverPermanentRequestFailures(
            FailureKind kind) {
        var event = failure(kind, FailureScope.REQUEST);

        var decision = policy.decide(
                event, approvedB(),
                false, false, true);

        assertEquals(
                RecoveryAction.STOP_PERMANENT,
                decision);
    }

    @Test
    void providerOutageMayFailOverToApprovedB() {
        var event = failure(
                FailureKind.PROVIDER_UNAVAILABLE,
                FailureScope.PROVIDER_INFRASTRUCTURE);

        assertEquals(
                RecoveryAction.FAILOVER_TO_APPROVED_PROVIDER,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void providerOutageCannotUseIneligibleB() {
        var unapproved = new CandidateProvider(
                "B", false, true, true, true, true);
        var event = failure(
                FailureKind.PROVIDER_UNAVAILABLE,
                FailureScope.PROVIDER_INFRASTRUCTURE);

        assertEquals(
                RecoveryAction.RETRY_SAME_PROVIDER_LATER,
                policy.decide(
                        event, unapproved,
                        false, false, true));
    }

    @Test
    void authFailureIsNotAutomaticFailover() {
        var event = failure(
                FailureKind.SMTP_AUTH_REJECTED,
                FailureScope.PROVIDER_ACCOUNT);

        assertEquals(
                RecoveryAction.HOLD_FOR_CORRECTION,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void unknownSubmissionOutcomeBlocksFailover() {
        var event = new NormalizedMailFailure(
                FailureKind.SUBMISSION_OUTCOME_UNKNOWN,
                FailureScope.UNKNOWN,
                "A",
                "DATA_FINAL_REPLY",
                null,
                null,
                false,
                true);

        assertEquals(
                RecoveryAction.RECONCILE_UNKNOWN,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void previousAcceptedAttemptBlocksAnotherSubmission() {
        var event = failure(
                FailureKind.PROVIDER_UNAVAILABLE,
                FailureScope.PROVIDER_INFRASTRUCTURE);

        assertEquals(
                RecoveryAction.RECONCILE_UNKNOWN,
                policy.decide(
                        event, approvedB(),
                        true, false, true));
    }

    @Test
    void recipientTemporaryFailureDoesNotForceProviderB() {
        var event = failure(
                FailureKind.TEMPORARY_RECIPIENT,
                FailureScope.RECIPIENT);

        assertEquals(
                RecoveryAction.RETRY_SAME_PROVIDER_LATER,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }

    @Test
    void unclassifiedFailureNeverTriggersBlindFailover() {
        var event = failure(
                FailureKind.UNCLASSIFIED,
                FailureScope.UNKNOWN);

        assertEquals(
                RecoveryAction.HOLD_FOR_CORRECTION,
                policy.decide(
                        event, approvedB(),
                        false, false, true));
    }
}
~~~

Test trên kiểm tra **decision function** đã minh họa. Vì record `NormalizedMailFailure` nhận mã SMTP thô, helper đã cố ý dùng cùng mã giả cho các nhóm để chứng minh policy quyết định theo *failure kind đã chuẩn hóa*; **không dùng cách gán 550 cho một provider outage trong classifier thực tế**. Trong hệ thống thật, cần thêm test classifier ánh xạ reply code/phase → `FailureKind` một cách đúng đắn.

### Các chốt nên kiểm tra ở một tầng trước policy

~~~text
notification.expiresAt < now
    => EXPIRED, no transport call

recipient is unsubscribed from marketing
    => SUPPRESSED, no A/B call

template cannot render
    => HOLD_FOR_CORRECTION, no A/B call

notification already SUBMITTED
    => no new attempt
~~~

Nếu chỉ unit test `MailFailoverPolicy` mà không test pre-send validation, vẫn có thể xảy ra lỗi: router chọn B hợp lệ nhưng worker không kiểm tra recipient vừa unsubscribe.

## 35. Integration test: provider A từ chối, provider B không hề được gọi

Unit test policy không chứng minh application wiring thật gọi đúng sender. Integration test cần quan sát cả hai tuyến.

### Kịch bản

1. Khởi động SMTP test server A và B trên hai cổng loopback khác nhau.
2. A trả `550 5.1.1` tại `RCPT TO`.
3. B chấp nhận message nhưng chỉ ghi số kết nối/commands.
4. Dispatcher gửi notification qua A.
5. Chờ hệ thống xử lý outcome và trạng thái cuối.
6. Xác minh A đã nhận RCPT TO và B **không nhận bất kỳ attempt nào**.

### Kết quả mong đợi

~~~text
A.receivedConnections = 1
A.receivedRCPT        = 1
A.reply              = 550 5.1.1

B.receivedConnections = 0
B.receivedDATA        = 0

notification.status   = FAILED_PERMANENT
notification.reason   = INVALID_RECIPIENT
routeDecisions        = STOP_PERMANENT
~~~

Đây là kết quả kỳ vọng của bài test, không phải output đã chạy. Nó chỉ đúng nếu adapter/classifier ánh xạ 550 5.1.1 và phase RCPT TO theo fixture thành invalid recipient.

### Test thêm một lỗi nội dung

Cho message thiếu attachment bắt buộc hoặc template render lỗi **trước SMTP submission**:

- A không được gọi.
- B không được gọi.
- Notification được giữ để sửa dữ liệu hoặc chuyển terminal theo policy.
- Metrics validation failure tăng.
- Không tạo physical attempts.

Nếu code cứ `catch(Exception)` và thử B, test này sẽ phát hiện ngay dù B đang healthy.

## 36. Integration test: outage tuyến A được phép chuyển B

Một bài test đối chứng là cần thiết để chứng minh hệ thống **không chặn failover trong mọi trường hợp**.

### Bố trí test

- A là SMTP endpoint test không truy cập được, hoặc fake server trả temporary failure đã được classifier định nghĩa là outage tuyến A.
- B là SMTP test server chấp nhận DATA, được đánh dấu approved/verified và có quota.
- Notification còn hạn, hợp lệ và chưa có accepted/unknown attempt.

### Kỳ vọng

~~~text
attempt[1]: provider=A
            status=FAILED_BEFORE_SUBMISSION
            reason=PROVIDER_UNAVAILABLE

decision:   FAILOVER_TO_APPROVED_PROVIDER

attempt[2]: provider=B
            status=ACCEPTED

notification:
            status=SUBMITTED
            attempts=2
~~~

Đo thêm số kết nối vào A/B, số physical SMTP attempts, duration và tài nguyên được giải phóng. Không đòi `DELIVERED` nếu fake B chỉ trả SMTP final 250; đây là submission test.

### B ineligible

Chạy lại test nhưng cấu hình B không được phép cho notification category. Kết quả:

- A thất bại.
- B không nhận kết nối.
- Notification chờ retry A hoặc trạng thái hold theo policy.
- Route decision nêu rõ `CANDIDATE_INELIGIBLE`.

Đây là một test quan trọng vì hệ thống phải tôn trọng contract **ngay cả khi A outage**.

## 37. Kiểm thử trường hợp A đã nhận nhưng worker không chắc chắn

Một SMTP scripted server có thể nhận body đến dấu kết thúc `CRLF . CRLF`, sau đó **đóng socket trước phản hồi cuối**.

Các assertion:

1. Client có thể nhận `MailSendException` hoặc exception bọc lỗi kết nối.
2. Nếu adapter được instrument để biết phase, result nên là `SUBMISSION_OUTCOME_UNKNOWN`.
3. Outbox chuyển `SUBMISSION_UNKNOWN`.
4. Không gọi B tự động dù B healthy.
5. Attempt history vẫn chứa provider A và dữ liệu tương quan.
6. Một reconciliation worker có thể kiểm tra provider logs/events nếu có.

**Giới hạn:** chỉ dựa vào `JavaMailSender` public API có thể không biết chính xác socket đã gửi hết DATA hay chưa. Nếu không đủ bằng chứng, chọn phân loại thận trọng; không tự tuyên bố chắc chắn A chưa nhận email chỉ vì thấy exception.

### Thử mất database sau khi A accepted

Một tình huống khác:

~~~text
A SMTP -> final 250 received
Worker -> database update SUBMITTED fails
Worker process terminates
~~~

Khi worker khởi động lại, outbox có thể vẫn `PROCESSING` hoặc đã hết lease. Nếu logic phục hồi tự chuyển sang B, message có nguy cơ gửi trùng. Bài test phải kiểm tra state reconciliation/attempt ledger và chính sách khi không thể xác định kết quả.

## 38. Kiểm thử provider downstream bounce và complaint

Không chỉ test SMTP submission exception. Với provider event:

### Hard bounce

~~~text
1. A accepted -> notification SUBMITTED.
2. Event A: hard bounce recipient invalid.
3. Consumer verifies signature and correlates event.
4. Recipient-level suppression updated.
5. B is healthy.
6. Assert no B submission is scheduled for same notification.
~~~

### Deferred

~~~text
1. A accepted.
2. Event A: deferred / provider retry in progress.
3. Assert no new B attempt.
4. Wait for delivered/bounced outcome from A.
~~~

### Complaint

~~~text
1. A accepted/delivered.
2. Event A: complained from recipient.
3. Suppression policy marks marketing as blocked.
4. A new marketing notification selects B.
5. Shared suppression check blocks the B attempt.
~~~

Webhook cần chống giả mạo và giao trùng. Test phải tính unique event theo provider event ID/recipient, không chỉ tăng số lần gọi handler.

## 39. Ma trận kiểm thử đầy đủ

| ID | Lỗi/điều kiện | A | B | Kết quả phải kiểm tra |
| --- | --- | --- | --- | --- |
| F01 | Email address sai cú pháp | Không gọi | Không gọi | Validation failure |
| F02 | Recipient hard bounce đã xác nhận | Không gửi tiếp | Không gửi tiếp | Suppression đúng scope |
| F03 | RCPT 550 5.1.1 user unknown | Rejected | Không gọi | `FAILED_PERMANENT` |
| F04 | RCPT 451 temporary recipient | Temporary | Không tự chuyển | Retry theo policy |
| F05 | Template missing | Không gọi | Không gọi | Hold/sửa template |
| F06 | MIME invalid | Không gọi | Không gọi | Không nhân attempts |
| F07 | Attachment vượt policy | Không gọi hoặc rejected | Không gọi | Content correction |
| F08 | A content rejection 554 | Rejected | Không gọi | Audit policy |
| F09 | A From not authorized | Rejected | Không chuyển mù | Sửa quyền sender |
| F10 | A SMTP AUTH 535 | Rejected | Không auto failover | Hold credential, alert |
| F11 | A TCP refused trước submit | Unavailable | Cho phép nếu eligible | Một attempt B có kiểm soát |
| F12 | A DNS endpoint fail | Unavailable | Cho phép nếu eligible | Không suppress recipient |
| F13 | B không được tenant dùng | Unavailable | Không gọi | Eligibility hard stop |
| F14 | B chưa verify From | Unavailable | Không gọi | Không bypass identity |
| F15 | B vượt quota | Unavailable | Không gọi | Defer, không loop |
| F16 | Provider A throttling | Temporary | Tùy policy | Backoff/budget và tuân thủ provider |
| F17 | A final SMTP 250 | Accepted | Không gọi | SUBMITTED |
| F18 | A mất final reply sau DATA | Unknown | Không gọi | Reconcile |
| F19 | A accepted rồi downstream hard bounce | Accepted → bounce | Không gọi | Delivery failed/suppression |
| F20 | A deferred rồi delivered | Accepted/deferred | Không gọi | Không duplicate |
| F21 | A complaint sau delivered | Delivered/complaint | Không gửi marketing | Shared suppression |
| F22 | Email OTP hết hạn giữa hai attempts | Temporary | Không gọi | EXPIRED |
| F23 | Người dùng unsubscribe trước B attempt | Temporary | Không gọi | SUPPRESSED |
| F24 | Hai worker cùng chọn B | Temporary | Một attempt | Atomic claim/lease |
| F25 | Broker redelivers same notification | Nhiều event | Không nhân sends | Idempotency key |
| F26 | Retry A và B lồng nhiều lớp | Temporary | Có thể | Physical attempt budget |
| F27 | Hết maxAttempts | Repeated failures | Không tạo thêm | DEAD_LETTER đúng reason |
| F28 | B accepted rồi provider event trễ | Accepted | Không tạo route mới | Submission/delivery tách biệt |
| F29 | Unclassified MailException | Unclear | Không gọi | Hold/triage |
| F30 | A và B outage cùng lúc | Unavailable | Unavailable | Outbox bền vững, không hot loop |
| F31 | Operator replay sau sửa recipient | Đúng route | Chỉ nếu được phép | Request mới có audit |
| F32 | Provider A đã nhận nhưng DB update fail | Accepted | Không gọi | Unknown/reconciliation |
| F33 | A rejected partial multi-recipient | Mixed | Không resend toàn message | Recipient-level outcomes |
| F34 | Provider B bị hạn chế region | Unavailable | Không gọi | Residency policy |
| F35 | Retry sau provider recovery | Pending | Theo route policy | Drain không vượt quota |

### Điều quan trọng trong test

**Đếm số lần gửi thật.** Chỉ assert state `FAILED_PERMANENT` chưa đủ nếu adapter đã lén thử B trước khi ghi state. Fake SMTP B hoặc mock/spy của B phải xác nhận **không có submission** khi policy yêu cầu dừng.

**Không chỉ test với một worker.** Race giữa instance, lease recovery và redelivery của broker có thể làm cùng một notification đi qua hai providers.

**Không chỉ test exception mock.** Với tình huống SMTP RCPT/DATA, nên có integration test dùng `JavaMailSenderImpl` thật với fake SMTP server lập trình reply code và phase. Mock phù hợp cho business guard nhưng không xác nhận transport mapping chính xác.

## 40. Eventual consistency và thứ tự của provider events

Hệ thống multi-provider dễ gặp event đến trễ:

~~~text
09:00  A accepted notification N
09:00  Worker DB update temporarily fails
09:02  A webhook ACCEPTED arrives
09:03  Recovery worker reads stale outbox state
09:04  B is considered healthy
~~~

Nếu chỉ đọc một trạng thái cũ rồi failover, nguy cơ duplicate. Cần:

- Durable event inbox và idempotent correlation.
- Cập nhật projection theo attempt/recipient.
- Có trạng thái `SUBMISSION_UNKNOWN` và terminal/accepted guard.
- Kiểm tra state ở transaction trước khi claim B attempt.
- Không dựa vào timeout webhook như bằng chứng “A không gửi”.

### Không suy diễn delivery từ thời gian im lặng

Nếu không nhận `delivered` trong 2 phút, có thể là provider đang queue, webhook bị trễ hoặc remote MX đang defer. **Không dùng absence of event làm trigger tự động resend qua B** khi A đã accepted.

## 41. Kiểm soát dữ liệu và quyền riêng tư khi đổi provider

Một notification có thể chứa PII, địa chỉ, số đơn hàng, chứng từ hoặc đường dẫn bảo mật. Chuyển B làm nội dung được xử lý bởi thêm một bên. Vì vậy policy cần kiểm tra:

- Provider B có nằm trong danh sách nhà cung cấp được chấp thuận không?
- Tenant/region có cho phép chuyển dữ liệu sang B không?
- Có cơ sở xử lý dữ liệu và mục đích gửi hợp lệ không?
- Credential/transport B có dùng TLS đúng không?
- B có retention/observability đáp ứng yêu cầu không?
- Có giới hạn loại nội dung (marketing, OTP, hóa đơn) không?
- Có sự khác biệt giữa From/domain authentication của A và B không?

**Không đánh đổi chính sách dữ liệu để đạt tỷ lệ gửi thành công cao hơn.** Một route không đủ điều kiện phải bị từ chối ngay cả trong outage P1; khi cần, kích hoạt kênh thay thế được phê duyệt thay vì gửi qua provider sai phạm vi.

## 42. Khi nào nên chọn route B từ đầu thay vì thử A rồi failover?

Nếu B đáp ứng một capability mà A không có (kích thước message, category, region, sender domain), **router nên chọn B trước khi gọi A**. Không tạo một lỗi permanent ở A chỉ để khám phá ra B thích hợp.

Ví dụ:

~~~text
Notification type: INVOICE_WITH_ATTACHMENT
Estimated MIME size: 15 MiB

Provider A limit: 10 MiB
Provider B limit: 25 MiB
Both providers allowed by policy

Router -> choose B initially
No A attempt is needed
~~~

Giới hạn và kích thước chỉ là số liệu minh họa. Quá trình tính MIME size cần xét encoding/headers; provider có thể có giới hạn size khác nhau.

### Lợi ích

- Ít rejected attempts và log nhiễu.
- Không lãng phí quota.
- Không làm tăng reputation risk của A.
- Tối ưu tracking và giảm retry complexity.
- Cải thiện tính minh bạch của quyết định tuyến.

Đây là **capability-based routing**, không phải “failover lỗi không thể gửi”.

## 43. Ghi log quyết định không failover

Một hệ thống vận hành cần trả lời được hai câu hỏi:

1. Vì sao message không được gửi?
2. Vì sao hệ thống **không thử provider B**, dù B được cấu hình làm dự phòng?

Nếu không có decision log, người vận hành có thể nhầm một hành vi an toàn thành lỗi của router và vô tình bật cờ “always fallback”.

### Structured log minh họa

~~~json
{
  "event": "mail_route_decision",
  "notificationId": "notif-1042",
  "attemptId": "attempt-a-1",
  "sourceProvider": "A",
  "candidateProvider": "B",
  "smtpPhase": "RCPT_TO",
  "failureKind": "INVALID_RECIPIENT",
  "smtpReplyCode": "550",
  "action": "STOP_PERMANENT",
  "fallbackAttemptCreated": false
}
~~~

Không ghi raw message body, OTP, recipient address đầy đủ, secret, access token hoặc toàn bộ SMTP transcript vào một log thông thường. Nếu cần chi tiết để điều tra, sử dụng record ID và một hệ thống sự kiện/diagnostic có quyền truy cập, retention và masking.

### Những quyết định đáng ghi riêng

- `FAILOVER_ALLOWED`: đã qua mọi eligibility checks, A outage rõ ràng.
- `FAILOVER_BLOCKED_PERMANENT`: lỗi recipient/content/permission.
- `FAILOVER_BLOCKED_SUPPRESSION`: recipient không được phép nhận.
- `FAILOVER_BLOCKED_EXPIRED`: message đã hết hạn.
- `FAILOVER_BLOCKED_UNKNOWN`: A có thể đã accepted.
- `FAILOVER_BLOCKED_ROUTE`: B chưa đủ điều kiện.
- `FAILOVER_BLOCKED_BUDGET`: B hết permit/quota.
- `FAILOVER_SKIPPED_ALREADY_ACCEPTED`: không có yêu cầu submit tiếp.
- `HOLD_FOR_REVIEW`: chưa đủ dữ kiện để quyết định an toàn.

Các tên trên là taxonomy ứng dụng, không phải giá trị có sẵn trong Spring Mail.

## 44. Metrics để phát hiện failover sai

Nếu hệ thống chỉ đo “bao nhiêu lần failover thành công”, nó có thể bỏ qua hàng nghìn lần gửi B không cần thiết. Nên theo dõi:

| Metric gợi ý | Mục tiêu |
| --- | --- |
| `mail_submission_attempts_total` | Đếm physical attempts theo provider |
| `mail_failover_decisions_total` | Số quyết định ALLOW/STOP/HOLD/RECONCILE |
| `mail_failover_executed_total` | Số attempt thực sự chuyển route |
| `mail_failover_blocked_total` | Số lần chặn với reason family |
| `mail_permanent_failures_total` | Lỗi recipient/payload/policy |
| `mail_outcome_unknown_total` | Lỗi cần reconciliation |
| `mail_provider_auth_failures_total` | Phân biệt lỗi account với lỗi recipient |
| `mail_provider_unavailable_total` | Đo outage riêng từng tuyến |
| `mail_provider_throttled_total` | Theo dõi capacity/provider policy |
| `mail_outbox_pending` | Backlog |
| `mail_outbox_oldest_age_seconds` | Tuổi thông điệp đang chờ |
| `mail_suppression_decisions_total` | Số lần chặn gửi theo category/reason |
| `mail_duplicate_suspected_total` | Các tình huống nghi ngờ submit trùng |
| `mail_rate_limiter_denied_total` | Permit bị từ chối, không phải SMTP failure |
| `mail_provider_delivery_events_total` | Delivered/deferred/bounced/complained nếu có |

Đây là tên metric gợi ý cho Micrometer/Actuator hoặc hệ thống observability đang dùng. Chúng **không được Spring Mail cung cấp đầy đủ mặc định**.

### Những cảnh báo hữu ích

| Tín hiệu | Điều có thể sai | Hành động |
| --- | --- | --- |
| B attempts tăng cùng hard bounce A | Router có thể đang fallback sai permanent failure | Tạm dừng failover tự động, kiểm tra classifier |
| Số B attempts gần bằng số A 550 | Có thể thử B cho recipient invalid | Xem audit và suppression |
| A accepted nhưng B cũng gửi cùng notification | Duplicate/unknown outcome guard lỗi | Cô lập router, đối soát |
| Failover lên B nhưng B throttling mạnh | Quota dự phòng không đủ | Giảm tốc, bảo vệ category quan trọng |
| B attempts dù tenant không cho phép | Route eligibility bug | Ngừng route B, điều tra data handling |
| AUTH errors A gây B flood | Sai policy account-level failure | Pause A, kiểm tra secret và breaker |
| Complaint A rồi marketing qua B | Shared suppression bị bypass | Chặn marketing, sửa suppression pipeline |
| `UNCLASSIFIED` tăng | Adapter mất dữ liệu lỗi hoặc provider đổi response | Điều tra transport mapping trước khi mở fallback |

### Đừng dùng recipient làm metric label

Full email address, notification ID và provider message ID có cardinality rất cao và có thể lộ PII. Dùng label hữu hạn như `provider`, `category`, `failureKind`, `action`, `region`; tra cứu message cụ thể qua log có phân quyền.

## 45. Runbook: phát hiện hệ thống tự thử B khi gặp lỗi permanent

Một incident có thể được báo qua bounce tăng, complaint tăng, quota B cạn nhanh hoặc khách hàng phản ánh nhận nhiều email.

### Bước 1 — Ngăn tác động

1. Tạm dừng **automatic failover rule đang gây lỗi**, không dừng toàn bộ email giao dịch nếu có thể cô lập theo provider/category.
2. Giữ outbox để không mất yêu cầu gửi hợp lệ.
3. Không replay hàng loạt các message đã qua A/B.
4. Bảo vệ B quota cho email quan trọng còn hợp lệ.
5. Nếu có dấu hiệu vi phạm consent hoặc data residency, kích hoạt quy trình bảo mật/tuân thủ tương ứng.

### Bước 2 — Xác định phạm vi

- Từ khi nào router bắt đầu tạo nhiều attempts ở B?
- Có deployment nào thay mapping SMTP 550/554/535 không?
- Có chuyển API provider khiến error schema thay đổi không?
- Có rule nào đổi `catch MailException` thành unconditional fallback không?
- Có dùng `status=FAILED` chung cho recipient permanent và provider temporary không?
- Có thấy `SUBMITTED` ở A nhưng B vẫn có attempt không?
- Có webhook A đến trễ khiến business state bị cập nhật sai không?
- Có category/tenant nào bị ảnh hưởng đặc biệt?

### Bước 3 — Phân loại và sửa nguyên nhân

| Nhóm | Sửa ở đâu |
| --- | --- |
| Invalid recipient | Validation/classifier/suppression |
| Template/MIME lỗi | Render pipeline/data quality |
| Policy violation | Nội dung, consent, compliance |
| AUTH/From permission | Secret/provider configuration |
| A accepted, B cũng gửi | Outcome/attempt ledger, lease, router guard |
| Unknown outcome | Reconciliation/protocol instrumentation |
| Provider B ineligible | Route catalog/policy gating |
| B overload | Rate budget/reserved capacity |

### Bước 4 — Xử lý những message đã gửi

Không thể thu hồi chắc chắn email đã được SMTP accepted. Cần:

- Đếm attempts và accepted submissions theo notification.
- Đối chiếu provider A/B events và recipient delivery khi có.
- Xác định duplicate hoặc unauthorized sends đã xảy ra.
- Đánh dấu suppression/complaint phù hợp cho các lần gửi sau.
- Tách message phải gửi lại sau khi sửa địa chỉ khỏi message đã accepted.
- Thông báo/khắc phục theo chính sách nghiệp vụ nếu người nhận bị ảnh hưởng.

### Bước 5 — Chỉ mở lại khi test có bằng chứng

Chạy fixture permanent recipient/content, accepted/unknown, provider outage và B ineligible; xác nhận B **không được gọi** trong nhánh cấm. Kiểm tra rate limiter và audit. Triển khai theo canary trước khi mở lưu lượng toàn cụm.

## 46. Runbook: provider A outage nhưng B không nhận được email

Không phải mọi trường hợp B không được gọi đều là lỗi. Kiểm tra stop reason:

1. Notification có bị `EXPIRED` hoặc `SUPPRESSED` không?
2. A có accepted hoặc unknown attempt trước đó không?
3. B có đủ quyền sender/tenant/region không?
4. B có khỏe và còn quota không?
5. Lỗi A có thật sự là provider outage không hay recipient/content permanent?
6. Đã hết maxAttempts/global budget chưa?
7. Circuit breaker A đang OPEN hay policy đang HOLD?
8. Có operator gate yêu cầu phê duyệt trước failover với loại email này không?

Nếu B không đủ điều kiện, hướng xử lý là **sửa điều kiện tuyến/đợi A** hoặc dùng kênh được phép, không bỏ điều kiện eligibility để cứu một message.

### Giảm độ trễ mà không bypass policy

Một số notification cực kỳ khẩn cấp có thể:

- Dùng provider B được cấu hình sẵn và kiểm thử định kỳ.
- Được route tới B ngay từ đầu theo chính sách high priority.
- Có reserved throughput.
- Dùng kênh thay thế như in-app notification nếu sản phẩm cho phép.

Những điều này nên được thiết kế **trước outage**. Không tạo một “emergency bypass” cho consent, TLS, data residency hoặc provider account security khi incident đang diễn ra.

## 47. Những lỗi thiết kế thường gặp

### 47.1. Catch mọi MailException rồi gọi provider tiếp theo

Làm mất phân biệt recipient, content, credential, network và outcome unknown. Thay bằng failure normalizer và decision policy.

### 47.2. Coi mọi 5xx là lỗi hạ tầng A

Nhiều 5xx phản ánh yêu cầu hiện tại không hợp lệ. Cần biết SMTP command và enhanced status.

### 47.3. Coi mọi 4xx là an toàn failover

Một 4xx có thể là throttling trên remote recipient domain, đổi provider chưa chắc giúp và có thể làm tăng tải.

### 47.4. Gửi B sau khi không thấy delivered event

Provider A có thể đã accepted và đang queue; absence of event không chứng minh failure.

### 47.5. Không có trạng thái SUBMISSION_UNKNOWN

Mất final reply sau DATA có thể dẫn đến gửi trùng nếu mọi exception được coi là “chưa submit”.

### 47.6. Không dùng shared suppression

Complaint hoặc hard bounce A không ngăn B gửi tiếp. Hệ thống có thể làm hại uy tín sender và quyền riêng tư người nhận.

### 47.7. Chỉ giới hạn attempts trong từng adapter

Outbox × A retries × B retries × broker redelivery làm số lần SMTP tăng ngoài dự kiến. Cần global attempt budget.

### 47.8. Không lưu route decision

Không thể giải thích lý do failover, lý do dừng hoặc chứng minh một message không bị gửi qua provider không được phép.

### 47.9. Không revalidate trước B send

Trong lúc A fail, OTP có thể hết hạn hoặc recipient unsubscribe. Check chỉ lúc enqueue không đủ.

### 47.10. Provider B thiếu From authorization

AUTH với B có thể thành công nhưng MAIL FROM bị từ chối; cần verify identity/DMARC alignment.

### 47.11. Cho B dùng dữ liệu không được phép

Quyền xử lý dữ liệu và region là hard constraint, không phải một tiêu chí mềm cho router.

### 47.12. Failover khi chưa có quota B

Khi A outage, B có thể bị dồn hàng nghìn job và tiếp tục lỗi; rate limiter/reserved budget cần áp dụng trên tất cả tuyến.

### 47.13. Gộp lỗi cấp account với recipient

SMTP AUTH 535 ở A không chứng minh mọi địa chỉ nhận sai. Không tự suppress khách hàng vì lỗi credential.

### 47.14. Gộp lỗi recipient với provider outage

RCPT 550 5.1.1 không nên mở circuit breaker A hay chuyển toàn bộ message sang B.

### 47.15. Không xem xét partial acceptance

Với multi-recipient message, một người có thể đã accepted; gửi lại toàn bộ message qua B gây duplicate.

### 47.16. Không phân biệt bounce event với submit failure

Downstream hard bounce sau accepted không phải một `JavaMailSender.send()` failure cần retry sang B.

### 47.17. Thay provider để bỏ qua content policy

Có thể gây vi phạm provider rules và abuse; cần sửa nội dung/consent thay vì tìm đường vòng.

### 47.18. Dùng `Message-ID` làm exactly-once guarantee

Message-ID giúp correlation, không bảo đảm mọi mailbox loại duplicate.

### 47.19. Replay mọi FAILED sau khi sửa route

`FAILED` có thể chứa permanent recipient, expired và unknown. Phải filter/reconcile trước replay.

### 47.20. Ghi raw SMTP exception và recipient vào metric labels

Có thể lộ PII/secret và gây cardinality cao. Chuẩn hóa và làm sạch.

## 48. Checklist thiết kế failover trước khi triển khai

### Dữ liệu và nghiệp vụ

- [ ] Notification có một idempotency key bền vững.
- [ ] Recipient được chuẩn hóa và kiểm tra hợp lệ trước submit.
- [ ] Consent, unsubscribe và complaint được kiểm tra từ nguồn đáng tin.
- [ ] Suppression áp dụng trên mọi provider.
- [ ] Template/MIME/attachment được xác minh trước dispatch.
- [ ] Expiry của OTP/reset link/campaign được kiểm tra lại trước từng attempt.
- [ ] Có quy tắc riêng cho email marketing, transactional và security.

### Transport và policy

- [ ] Biết ranh giới A accepted, A refused, và A outcome unknown.
- [ ] Classifier dùng SMTP phase/enhanced status khi có, không chỉ message string.
- [ ] Permanent recipient/content failure dẫn đến stop/hold, không chọn B.
- [ ] Provider account failure được hold/điều tra; không fallback tự động bằng catch-all.
- [ ] Chỉ chuyển B khi sự cố là route-specific và B đủ điều kiện.
- [ ] B được phê duyệt cho From, category, tenant, region, content và quota.
- [ ] Không retry khi A đã accepted hoặc có outcome unknown chưa đối soát.
- [ ] Không chuyển B để vượt content-policy/complaint/suppression.

### Worker, transaction và tài nguyên

- [ ] Business transaction lưu outbox bền vững trước khi gửi.
- [ ] Claim có transaction/lease, không có hai worker gửi cùng notification.
- [ ] Mỗi SMTP attempt được ghi với provider và trạng thái.
- [ ] Retry/failover dùng chung global attempt budget và deadline.
- [ ] Có backoff+jitter, rate limiter và max concurrent SMTP sends.
- [ ] Không sleep trong transaction database hoặc tạo unbounded executor queue.
- [ ] Replay/dead-letter đi qua cùng pre-send checks và limiter.
- [ ] Trạng thái `SUBMISSION_UNKNOWN` có quy trình reconciliation.

### Quan sát và vận hành

- [ ] Log quyết định không failover với reason chuẩn hóa.
- [ ] Metric phân biệt physical attempts, route decisions, permanent errors.
- [ ] Provider event processor chống duplicate/out-of-order.
- [ ] Có alert khi B attempts tăng cùng permanent failures A.
- [ ] Có runbook khi A outage/B ineligible/account lỗi.
- [ ] Có phương án canary và rollback/roll-forward.
- [ ] Không lộ secret/PII qua log, metrics hoặc provider debug trace.
- [ ] Có test xác nhận B **không** được gọi với các nhánh dừng.

Checklist là một bộ tiêu chí thiết kế. Việc một mục được tick ở tài liệu không thay thế kết quả kiểm thử hoặc audit hệ thống thật.

## 49. Quy trình triển khai theo từng giai đoạn

Một nhóm kỹ thuật có thể đưa policy mới vào hệ thống theo thứ tự:

1. **Inventory các đường gửi:** Web request, outbox worker, retry scheduler, manual resend, campaign, bulk import và provider fallback cũ.
2. **Định nghĩa failure taxonomy:** recipient, payload, policy, provider account, provider infrastructure, unknown outcome.
3. **Chuẩn hóa transport adapters:** A và B cùng trả `NormalizedMailFailure` mà không mất phase/provider metadata.
4. **Thêm guard trước send:** expiry, consent, suppression, MIME, sender/tenant eligibility.
5. **Lưu state và decision audit:** một notification, nhiều attempts, route decisions và stop reason.
6. **Cập nhật router:** bỏ catch-all failover, chuyển sang decision policy.
7. **Bổ sung unit tests:** permanent failures, A outage, B ineligible, accepted và unknown.
8. **Bổ sung integration tests:** SMTP fake A trả 550/451/554, B đếm kết nối, outbox database và multi-worker race.
9. **Đưa vào canary:** ban đầu có thể chỉ quan sát “would fail over” trong môi trường không tạo gửi thật, sau đó bật policy có kiểm soát.
10. **Theo dõi metrics:** tỷ lệ dừng/permanent, số attempt B, backlog, latency, duplicate suspected và complaint.
11. **Mở rộng rollout:** tăng dần phạm vi tenant/category đã được phê duyệt.
12. **Chuẩn hóa runbook:** người trực biết khi nào dừng, sửa, retry, chuyển tuyến và đối soát.

### Không dùng dry-run để gửi hai bản

“Shadow evaluation” có thể chỉ chạy **hàm quyết định route** và ghi `wouldFailover=true/false`, không thực sự gọi B. Nếu shadow mode gửi một bản qua B, đó đã là gửi thật và có nguy cơ duplicate. Cần đặc biệt chú ý trong thử nghiệm quy tắc mới.

### Feature flag an toàn

Một flag `enableFailover` chỉ quyết định có cho phép failover ở những nhánh **đủ điều kiện** hay không. Nó không được tắt các hard guards. Ví dụ:

~~~text
if validation fails:
    STOP  // applies even if enableFailover=true

if accepted or outcome unknown:
    STOP / RECONCILE

if provider-specific temporary failure:
    if enableFailover and backupEligible:
        schedule backup
    else:
        defer or retry primary safely
~~~

Không tạo `forceFailoverIgnoringPolicy=true` như một phương án cứu incident chung.

## 50. Câu hỏi tự kiểm tra

**1. Vì sao không nên catch mọi `MailException` rồi gửi qua provider B?**

Vì `MailException` có thể bao nhiều lỗi khác nhau: recipient không tồn tại, template sai, credential sai, TLS/DNS outage hoặc kết quả submit không xác định. Chỉ một số lỗi hạ tầng riêng A mới có thể được cải thiện bằng chuyển tuyến.

**2. Nếu A trả 550 5.1.1 mailbox không tồn tại, B đang healthy thì sao?**

Không gửi qua B. Cần ghi nhận invalid recipient theo bằng chứng, dừng gửi và xử lý suppression/xác minh địa chỉ theo policy.

**3. Có nên chuyển B khi A trả 535 SMTP AUTH không?**

Không tự động. Cần kiểm tra credential/account A, incident security và điều kiện B. Nếu B là route dự phòng hợp lệ đã được phê duyệt, có thể chuyển theo chính sách kiểm soát; mặc định nên hold để sửa cấu hình.

**4. 4xx có phải luôn được phép failover không?**

Không. Một 4xx có thể phản ánh vấn đề recipient/domain downstream mà B cũng gặp. Cần phân loại phase và nguyên nhân.

**5. 5xx có phải luôn permanent cho mọi provider không?**

Không. Một số 5xx phản ánh tài khoản/cấu hình riêng A; nhưng nó cũng không tự động cho phép B. Cần phân biệt phạm vi và xem route eligibility.

**6. Nếu A accepted nhưng chưa có delivered event, có nên dùng B cho nhanh không?**

Không. A có thể đang queue hoặc remote MX đang defer. Chưa có delivered event không chứng minh message chưa được relay nhận.

**7. Vì sao không failover sau khi mất final SMTP response ở DATA?**

Vì A có thể đã accepted; gửi B sẽ tạo duplicate. Cần trạng thái `SUBMISSION_UNKNOWN` và đối soát.

**8. Có thể dùng cùng Message-ID để bảo đảm hai provider không gửi trùng không?**

Không. Message-ID giúp trace, nhưng SMTP không có exactly-once guarantee dựa trên header đó.

**9. Hard bounce từ A có khiến B được thử lại không?**

Không đối với hard bounce đáng tin xác nhận mailbox không tồn tại. Hãy xử lý recipient và suppression thay vì chuyển tuyến.

**10. Deferred event từ A có nghĩa ứng dụng phải gửi bản mới qua B không?**

Thông thường không: A đã accepted và có thể đang tự retry tới remote MX. Cần chờ outcome/downstream status.

**11. Có thể chuyển B để vượt nội dung bị A chặn theo chính sách không?**

Không nên. Failover phục vụ tính sẵn sàng của yêu cầu **hợp lệ**, không phải né content/abuse policy.

**12. Có cần kiểm tra consent lại ở attempt B không?**

Có. Recipient có thể unsubscribe hoặc complaint giữa lần A lỗi và lúc B bắt đầu gửi.

**13. Nếu B có quota lớn hơn và hỗ trợ attachment cỡ lớn hơn A?**

Nên chọn B theo capability-based routing trước khi gửi, nếu nội dung hợp lệ và B được phê duyệt; không dùng chiến thuật gửi sai A để thử lần lượt mọi providers.

**14. Có nên giữ một suppression list riêng cho mỗi SMTP adapter?**

Không đủ. Ứng dụng nên có một policy quyết định dùng chung với phạm vi phù hợp, để complaint/hard bounce không bị bypass khi đổi route.

**15. Nếu worker chết sau khi A accepted nhưng trước khi cập nhật database, có được gửi B không?**

Không tự động. Cần attempt ledger, trạng thái outcome không rõ và đối soát để tránh gửi trùng.

**16. MaxAttempts có nên tính cả A và B không?**

Có một ngân sách tổng ở cấp notification, đồng thời có thể có giới hạn riêng từng provider. Đếm physical SMTP/API submissions, không chỉ dispatcher calls.

**17. Vì sao cần test B không nhận kết nối?**

Vì một test chỉ assert `FAILED_PERMANENT` sau cùng có thể bỏ sót việc adapter đã gửi thử B trước khi ghi status. Cần quan sát transport thật.

**18. Khi SMTP AUTH A lỗi vì secret rotation, phải làm gì?**

Tạm dừng retry storm của A, xác minh secret version/credential, cập nhật sender và kiểm tra canary. Chỉ cân nhắc B nếu đã đủ điều kiện và có quyết định routing hợp lệ.

**19. Một tenant không cho phép dùng B nhưng A đang outage, có thể bỏ ràng buộc region không?**

Không. Data residency/contract là điều kiện cứng, không bị tự động vô hiệu hóa bởi outage.

**20. Failover an toàn được xác nhận bằng những tiêu chí gì?**

Failure thật sự route-specific, A chưa accepted, không có outcome unknown, notification vẫn hợp lệ, B được phép/khỏe/còn quota, attempts không vượt giới hạn và mọi quyết định được ghi audit.

## Kết luận

**Không thử lại sang provider khác với lỗi không thể gửi là quy tắc nền tảng của hệ thống multi-provider email an toàn.** Spring Framework Mail giúp submit email qua `JavaMailSender`, nhưng ứng dụng phải tự chuẩn hóa lỗi SMTP/Jakarta Mail, kiểm tra trạng thái notification, quyết định route và thực thi giới hạn retry. Recipient invalid, payload/template/MIME lỗi, consent bị rút, message hết hạn hoặc nội dung/policy bị từ chối không tự trở nên hợp lệ khi chuyển A sang B. Ngược lại, outage hạ tầng thật của A có thể là lý do dùng B, **chỉ khi** B được phê duyệt, có quyền sender, đúng phạm vi dữ liệu và còn quota, đồng thời lần gửi trước chắc chắn chưa được accepted.

Hãy tách submission khỏi delivery; phân biệt explicit refusal với `SUBMISSION_UNKNOWN`; lưu một notification với nhiều attempt records, áp dụng shared suppression, transaction/lease và global attempt budget. Kiểm thử phải chứng minh **B không hề được gọi** đối với lỗi permanent, accepted/unknown và eligibility failure, song vẫn cho phép failover có kiểm soát khi A thật sự unavailable. Với logging, metrics và runbook rõ ràng, hệ thống có thể tăng availability mà **không gửi trùng, không lách chính sách và không thử đi thử lại những email vốn không đủ điều kiện gửi**.
