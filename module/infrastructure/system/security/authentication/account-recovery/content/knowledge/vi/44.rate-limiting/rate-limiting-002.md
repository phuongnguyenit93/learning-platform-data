# Per identifier rate limit

## 1. Giới hạn theo định danh bảo vệ mục tiêu nào?

**Per identifier rate limit** là giới hạn số lần thực hiện một loại hành động đối với cùng định danh trong một khoảng thời gian. Trong khôi phục tài khoản, định danh có thể là tên đăng nhập, email, số điện thoại hoặc ID tài khoản mà máy chủ đã phân giải.

Giới hạn theo IP trả lời câu hỏi “nguồn này gửi bao nhiêu yêu cầu?”. Giới hạn theo định danh trả lời câu hỏi “mục tiêu này đang nhận bao nhiêu yêu cầu từ tất cả nguồn?”. Hai lớp bổ sung cho nhau.

Ví dụ minh họa: một endpoint cho mỗi IP gửi tối đa ba lần thử mã. Tám IP cùng nhắm một tài khoản vẫn có thể tạo 24 lượt thử nếu không có ngân sách chung cho tài khoản đó. Giới hạn theo định danh gom các nguồn về cùng một mục tiêu để kiểm soát tổng lượt.

Trong hướng dẫn chống dò mật khẩu, OWASP đề xuất gắn bộ đếm thất bại với tài khoản thay vì chỉ với IP, nhằm chống nguồn tấn công phân tán. Khi áp dụng tư tưởng này cho recovery, cần xác định rõ hành động nào được đếm và tránh tạo khả năng khóa nạn nhân từ bên ngoài. Xem [OWASP — Login Throttling](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#login-throttling).

Trong bài này, các khóa và thuật toán là mô hình thiết kế minh họa. Chúng không thay thế chính sách mức bảo đảm hoặc yêu cầu xác minh danh tính của hệ thống.

## 2. Không phải mọi định danh đều đại diện cùng một thứ

| Loại định danh | Có thể bảo vệ điều gì? | Giới hạn |
| --- | --- | --- |
| Chuỗi người dùng nhập | Kiểm soát đầu vào trước khi tra tài khoản | Có thể có nhiều cách viết hoặc bí danh |
| ID tài khoản nội bộ | Gom hoạt động hướng đến cùng tài khoản | Chỉ có sau khi máy chủ phân giải |
| Email hoặc số nhận đã đăng ký | Bảo vệ tài nguyên phân phối | Nhiều tài khoản có thể dùng cùng địa chỉ nhận |
| ID giao dịch recovery | Giới hạn hoạt động trong một giao dịch | Tạo giao dịch mới có thể vượt giới hạn nếu thiếu lớp tổng hợp |
| ID challenge hoặc token | Giới hạn lượt đoán một bằng chứng | Đổi challenge không được tự cấp thêm lượt vô hạn |

Một số điện thoại không nhất thiết tương đương một người hoặc một tài khoản. Nó có thể được dùng chung, thay đổi chủ sở hữu hoặc gắn với nhiều hồ sơ. Bộ đếm theo người nhận và bộ đếm theo tài khoản có mục đích khác nhau.

Tương tự, username và email có thể cùng ánh xạ đến một tài khoản. Nếu mỗi chuỗi được phép thử độc lập, người gọi có thể chuyển qua lại giữa các bí danh để lấy thêm ngân sách.

Một mô hình phù hợp có hai lớp:

~~~text
Trước tra cứu:
    ngân sách theo định danh nhập đã chuẩn hóa

Sau phân giải:
    ngân sách theo accountId chuẩn của máy chủ
~~~

Lớp đầu giúp hạn chế việc tra cứu và lạm dụng cùng chuỗi đầu vào, kể cả chuỗi chưa thuộc tài khoản nào. Lớp sau gom tất cả bí danh thực sự thuộc cùng tài khoản.

Khi chưa tìm thấy tài khoản, hệ thống không cần tạo một hồ sơ tài khoản giả. Nó có thể tiếp tục phản hồi chung, trong khi lớp kiểm soát đầu vào vẫn hoạt động.

## 3. Chuẩn hóa phải theo cùng quy tắc với tra cứu tài khoản

Nguyên tắc quan trọng:

> Nếu hai giá trị được hệ thống đăng nhập và recovery coi là cùng một định danh, chúng phải hội tụ về cùng ngân sách mục tiêu.

Ví dụ, nếu ứng dụng đã quy định username không phân biệt chữ hoa và chữ thường, username “Lan” và “lan” không nên tạo hai ngân sách tài khoản khác nhau.

Tuy nhiên không nên áp dụng một phép biến đổi tùy ý cho mọi loại định danh:

- Không tự xóa dấu chấm hoặc phần sau dấu cộng của mọi email theo quy tắc của một nhà cung cấp riêng.
- Không mặc định mọi phần của mọi địa chỉ email có cùng quy tắc so sánh.
- Không bỏ mã quốc gia của số điện thoại nếu dữ liệu cần mã đó để xác định đúng số.
- Không tự loại mọi dấu câu trong username nếu ứng dụng cho phép chúng phân biệt hai tài khoản.
- Không dùng một chuẩn hóa Unicode khác với quy tắc đã dùng khi đăng ký và tra cứu.

Chuẩn hóa quá ít tạo đường vượt giới hạn. Chuẩn hóa quá nhiều có thể gom nhầm người dùng và cho người này tiêu hao ngân sách của người khác.

Nên có một thành phần dùng chung cho đăng ký, đăng nhập, recovery và xây khóa đầu vào. Kết quả chuẩn hóa cần chứa cả loại định danh và giá trị dùng để tra cứu, thay vì chỉ trả một chuỗi đã lower-case.

### Ví dụ ánh xạ

| Đầu vào | Quy tắc của ứng dụng | Ngân sách sau phân giải |
| --- | --- | --- |
| Lan và lan | Username không phân biệt hoa/thường | Cùng accountId |
| Username và email của Lan | Cả hai là bí danh đã xác minh | Cùng accountId |
| Cùng username ở hai tenant khác nhau | Không gian tài khoản tách biệt | Khác khóa theo tenant |
| Hai tài khoản dùng cùng số nhận | Hai accountId riêng | Khác ngân sách tài khoản, có thể chung ngân sách người nhận |
| Chuỗi không đúng cú pháp | Quy tắc kiểm tra đầu vào công khai | Bị xử lý ở lớp đầu vào, không suy ra việc tài khoản tồn tại |

Tên tenant cũng phải đến từ ngữ cảnh đã được hệ thống phân giải. Một trường tenant tùy ý do client gửi không được cho phép người gọi tạo vô hạn không gian ngân sách mới.

## 4. Tạo khóa có phạm vi rõ và bảo vệ dữ liệu cá nhân

Một khóa logic có thể gồm:

~~~text
application / tenant / actionFamily / subjectKind / subjectValue
~~~

Trong đó:

- actionFamily xác định nhóm hành động cùng chia sẻ ngân sách.
- subjectKind phân biệt định danh nhập, accountId hoặc người nhận.
- subjectValue là giá trị chuẩn do máy chủ xác định.

Đừng chỉ nối các trường bằng một ký tự mà người dùng cũng được phép nhập. Cần mã hóa tuple rõ ràng, chẳng hạn các thành phần có độ dài xác định hoặc biểu diễn chuẩn được thiết kế để không gây nhập nhằng.

Không nên lưu email hoặc số điện thoại nguyên văn trong mọi tên key của kho rate limit. Có thể dùng HMAC với khóa bí mật do máy chủ quản lý trên tuple đã mã hóa:

~~~text
key = prefix + HMAC(serverKey, encodedTuple)
~~~

HMAC giúp tránh việc kho key lộ trực tiếp danh sách địa chỉ và hạn chế việc dò giá trị bằng một bảng băm công khai. Nó không biến dữ liệu thành vô danh: cùng đầu vào vẫn tạo định danh có thể liên kết.

Ví dụ ranh giới trách nhiệm trong Java:

~~~java
String identifierBudgetKey(
    TrustedTenant tenant,
    NormalizedIdentifier identifier
) {
    byte[] payload = tupleEncoder.encode(
        "account-recovery.request",
        tenant.id(),
        identifier.kind().name(),
        identifier.lookupValue()
    );

    return "rl:recovery:identifier:v1:"
        + keyHasher.hmacBase64Url(payload);
}
~~~

tupleEncoder và keyHasher là thành phần giả định. Cần triển khai bằng cơ chế mã hóa và mật mã phù hợp, giữ khóa khỏi log và dùng thống nhất giữa các instance.

### Đổi khóa không được tự xóa lịch sử hạn chế

Thêm một phiên bản vào tên key giúp quản lý định dạng, nhưng triển khai v2 không nên vô tình cấp lại toàn bộ lượt thử khi v1 đang bị giới hạn.

Khi đổi định dạng key, khóa HMAC hoặc chính sách, cần một kế hoạch chuyển tiếp giữ được ngân sách còn lại: duy trì quyết định từ trạng thái cũ, chuyển trạng thái có kiểm soát hoặc áp dụng giao thức tương đương. Không chỉ đọc key mới và xem không tồn tại là chưa dùng lượt nào.

Với tài khoản đã phân giải, ID nội bộ ổn định giúp tránh reset ngân sách chỉ vì người dùng đổi email hoặc username. Việc chuyển một bí danh sang tài khoản khác vẫn cần được xử lý theo vòng đời bí danh; không trộn lịch sử của hai tài khoản một cách vô hạn.

## 5. Tách hành động được đếm

Một giới hạn “năm lần mỗi phút” chưa đủ để hiểu chính sách. Phải biết năm lần của hành động nào.

| Hành động | Thứ được kiểm soát |
| --- | --- |
| Bắt đầu recovery | Chi phí tiếp nhận và tra cứu, số giao dịch được tạo |
| Gửi email/SMS/push | Lượng phân phối và mức làm phiền người nhận |
| Resend | Số lần gửi lại trong cùng giao dịch |
| Thử OTP hoặc mã recovery | Số lần kiểm tra bằng chứng, nguy cơ dò mã |
| Thất bại xác minh liên tiếp | Trạng thái chống đoán theo chính sách authenticator |
| Hoàn tất thay đổi | Quyền thực hiện một thao tác nhạy cảm |

Bộ đếm gửi không thay thế bộ đếm đoán mã. Ngừng gửi SMS mới không ngăn người gọi tiếp tục thử những mã khác ở endpoint xác minh nếu endpoint đó không có kiểm soát riêng.

Tương tự, một bộ đếm **lượt được tiếp nhận để xác minh** khác với bộ đếm **lần xác minh thất bại**:

- Bộ đếm tiếp nhận được giữ trước khi làm công việc kiểm tra.
- Bộ đếm thất bại chỉ cập nhật khi có kết quả thất bại có thẩm quyền.
- Thử lại do lỗi hạ tầng chưa chắc là thất bại xác minh.
- Một lượt bị chặn trước xác minh không chứng minh bằng chứng đúng hay sai.

NIST yêu cầu kiểm soát số lần thất bại trong các cơ chế thích hợp và nêu rõ rằng phát hành bí mật ngoài băng mới không được đặt lại bộ đếm thất bại. Vì vậy việc xin mã mới hoặc tạo challenge mới không thể là cách lấy lại ngân sách đoán không giới hạn. Xem [NIST — Out-of-Band Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#oobver).

Một thiết kế có thể có đồng thời giới hạn theo challenge, theo accountId và theo nhóm hành động recovery. Các ngân sách con không được tạo quyền vượt ngân sách tổng.

Các endpoint thay thế có cùng bản chất cũng cần chia sẻ nhóm hành động phù hợp. Nếu API web, mobile và công cụ hỗ trợ đều thử cùng loại bằng chứng nhưng dùng ba ngân sách độc lập, tổng số lượt có thể lớn hơn chính sách dự kiến.

## 6. Chọn thuật toán theo điều cần bảo đảm

| Thuật toán | Cách hoạt động | Điều cần cân nhắc |
| --- | --- | --- |
| Cửa sổ cố định | Đếm trong mỗi cửa sổ xác định | Có thể tạo burst quanh ranh giới |
| Cửa sổ trượt | Xét hoạt động trong khoảng gần nhất | Cần giới hạn bộ nhớ và chọn cách biểu diễn |
| Token bucket | Tích lũy quyền đến sức chứa tối đa, nạp lại theo tốc độ | Cố ý cho phép một lượng burst |
| Cooldown | Chờ một khoảng trước lần tiếp theo | Không tự giới hạn tổng lượt trong thời gian dài |
| Bộ đếm thất bại liên tiếp | Giữ lịch sử thất bại đến điều kiện reset hợp lệ | Cần quy định rõ reset, trì hoãn và phương thức thay thế |

Ví dụ “năm lượt trong mười phút” chỉ là số minh họa, không phải ngưỡng khuyến nghị. Nếu cửa sổ cố định cho phép năm lượt ngay trước ranh giới và năm lượt ngay sau ranh giới, người gọi có thể tạo mười lượt trong một khoảng rất ngắn.

Nếu mục tiêu là giảm dội tin nhắn, cooldown kết hợp ngân sách dài hơn có thể hữu ích. Nếu mục tiêu là kiểm soát dò một bí mật ngắn, cần xem tổng cơ hội đoán và các yêu cầu về số lần thất bại; một token bucket tự nạp lại không tự đáp ứng mọi yêu cầu đó.

Không dùng cùng một thuật toán và cùng một ngưỡng cho mọi hành động chỉ vì dễ tái sử dụng mã. Thành phần rate limit có thể dùng chung, nhưng chính sách phải được đặt tên và quản lý riêng.

## 7. Kiểm tra và tăng bộ đếm phải nguyên tử

Mẫu sau có race condition:

~~~text
đọc số lượt hiện tại
nếu còn ngân sách:
    tăng bộ đếm
    cho tiếp tục
~~~

Hai instance có thể cùng đọc số lượt chưa đạt ngưỡng, rồi cùng cho tiếp tục. synchronized trong một JVM không giải quyết được trường hợp hai JVM khác nhau.

Phép quyết định cần kết hợp việc kiểm tra và giữ lượt tại cùng nguồn trạng thái có thẩm quyền.

### Ví dụ một cửa sổ bắt đầu từ lượt đầu tiên

Lua dưới đây minh họa một key trong Redis. Nó đếm **lượt được tiếp nhận** vào một hành động, không phải bộ đếm thất bại xác minh liên tiếp.

~~~lua
-- KEYS[1]: key do server xây từ định danh chuẩn
-- ARGV[1]: số lượt tối đa, cấu hình số nguyên dương
-- ARGV[2]: độ dài cửa sổ bằng mili giây, cấu hình hợp lệ

local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local raw = redis.call('GET', KEYS[1])

if not raw then
    redis.call('SET', KEYS[1], '1', 'PX', windowMs)
    return {1, limit - 1, windowMs}
end

local used = tonumber(raw)
local ttl = redis.call('PTTL', KEYS[1])

-- Trạng thái sai hoặc key không có TTL: trả lỗi nội bộ.
if not used or used < 0 or ttl < 0 then
    return {-1, 0, 0}
end

if used >= limit then
    return {0, 0, ttl}
end

local nextUsed = redis.call('INCR', KEYS[1])
return {1, limit - nextUsed, ttl}
~~~

Ý nghĩa kết quả:

- 1: đã giữ một lượt cho hành động.
- 0: không còn lượt trong cửa sổ.
- -1: trạng thái kho không hợp lệ; không được diễn giải thành cho phép.

Server phải kiểm tra cấu hình trước khi gọi: limit và windowMs là số nguyên dương trong phạm vi được hỗ trợ. Client không được tự chọn chúng.

TTL được đặt khi tạo cửa sổ, không được kéo dài sau mỗi request. Vì thế một request bị từ chối không tự giữ định danh ở trạng thái chặn mãi mãi. Nếu chính sách muốn trì hoãn tăng dần, cần biểu diễn riêng thay vì vô tình tạo ra từ cách cập nhật TTL.

Redis thực thi script nguyên tử trên server, nên các client không xen một cập nhật khác vào giữa các bước của script. Script cũng chặn công việc khác trong thời gian chạy, nên logic cần ngắn và có chi phí được giới hạn. Xem [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/).

Ví dụ này chỉ bảo vệ một key. Nó không chứng minh rằng nhiều ngân sách theo accountId, IP và tenant đã được giữ nguyên tử cùng lúc, hoặc rằng việc gọi nhà cung cấp bên ngoài nằm trong cùng một transaction.

Nếu giữ ngân sách theo nhiều chiều, phải xác định rõ:

- Tất cả cùng được cấp lượt hoặc không cấp lượt bằng cơ chế phù hợp; hoặc
- Các bộ đếm độc lập có chủ đích tính cả những lần bị chặn ở lớp sau.

Không mặc định rằng gọi nhiều script hoặc nhiều kho dữ liệu nối tiếp sẽ tạo ra một phép cấp lượt tất cả-hoặc-không.

### Cấp lượt không đồng nghĩa thực thi một lần

Sau khi được rate limiter cho qua, thao tác vẫn cần kiểm tra bằng chứng, quyền, thời hạn và trạng thái tiêu thụ token. Rate limit không thay thế replay defense hoặc idempotency.

Nếu phản hồi từ kho rate limit bị mất, lượt có thể đã bị tính. Retry không kiểm soát có thể làm tốn thêm lượt. Không tự hoàn lượt chỉ vì client không thấy phản hồi; chính sách phải phân biệt lỗi truyền thông với bằng chứng rằng lượt chưa được giữ.

## 8. Đặt lớp giới hạn đúng chỗ trong recovery

Một luồng tham chiếu:

~~~mermaid
flowchart TD
    A[Yêu cầu công khai] --> B[Kiểm tra định dạng và nguồn gọi]
    B --> C[Chuẩn hóa cùng quy tắc tra cứu]
    C --> D[Giới hạn theo định danh nhập]
    D --> E[Tra cứu có kiểm soát]
    E --> F[Ánh xạ về accountId chuẩn]
    F --> G[Giới hạn theo tài khoản và hành động]
    G --> H[Kiểm tra điều kiện recovery]
    H --> I[Giữ ngân sách gửi hoặc xác minh]
    I --> J[Thực hiện thao tác được phép]
~~~

Phản hồi bên ngoài cần được thiết kế sao cho các nhánh không tìm thấy, bị gộp hoặc bị giới hạn không trở thành cách dò tài khoản. Sơ đồ không yêu cầu đồng bộ mọi bước trong HTTP request; phần việc đắt có thể được xử lý bất đồng bộ với hàng đợi được giới hạn.

Đối với endpoint thử mã, accountId nên được lấy từ giao dịch recovery hoặc ánh xạ mà server đã xác minh. Không cho người gọi gửi một accountId tùy ý để đổi ngân sách sau mỗi lần thử.

Nếu không thể ánh xạ một request không hợp lệ tới tài khoản, vẫn phải có giới hạn nguồn gọi và toàn hệ thống để tránh công việc tra cứu vô hạn. Không cần xác minh mật mã hoặc truy vấn nặng cho mọi giá trị rác trước khi áp dụng mọi lớp bảo vệ.

Cùng một chính sách phải được áp dụng ở tất cả đường tương đương: web, mobile, API phiên bản cũ và công cụ hỗ trợ. Bỏ sót một endpoint thường biến giới hạn còn lại thành biện pháp hình thức.

### Không dùng IP để thay thế khóa mục tiêu

IP hữu ích cho admission và phát hiện nguồn, nhưng nhiều người dùng có thể cùng IP. Kẻ tấn công cũng có thể thay IP. Vì thế nên coi IP là một chiều bổ sung, không phải danh tính mặc định của người dùng.

Ngược lại, giới hạn theo accountId không bảo vệ hệ thống khỏi người gọi thay đổi hàng triệu định danh. Cần thêm ngân sách theo nguồn, tenant, công việc đang chờ và năng lực toàn dịch vụ.

## 9. Phản hồi HTTP phải giữ tính riêng tư

RFC 6585 định nghĩa 429 Too Many Requests cho trường hợp quá nhiều yêu cầu và cho phép dùng Retry-After để biểu thị thời gian nên chờ. Tiêu chuẩn không quyết định ứng dụng phải nhận diện người dùng bằng email, tài khoản hay cơ chế khác. Phản hồi 429 không được lưu bởi cache. Xem [RFC 6585 — Section 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Trong recovery công khai, việc chọn trả 429 ở lớp nào cần tránh lộ trạng thái mục tiêu:

- Giới hạn theo nguồn gọi có thể trả thông tin chờ mà không phụ thuộc tài khoản tồn tại.
- Giới hạn nội bộ theo accountId không nên tự làm tài khoản có thật nhận mã trạng thái khác tài khoản không có.
- Ngữ cảnh đã được xác minh có thể nhận hướng dẫn cụ thể hơn theo quyền của nó.

Một phản hồi chung có thể là:

> Nếu thông tin hợp lệ, yêu cầu sẽ được xử lý theo chính sách của dịch vụ. Bạn có thể chờ hoặc dùng phương thức khôi phục khác đã thiết lập.

Không khẳng định “đã gửi mã” nếu thực tế công việc bị chặn hoặc gộp. Đồng thời không nêu rằng một tài khoản cụ thể đang bị giới hạn, còn bao nhiêu lượt, hoặc có bao nhiêu giao dịch đang chờ.

Cùng câu chữ nhưng khác mã trạng thái, header, độ dài nội dung hoặc thời gian xử lý rõ rệt vẫn có thể lộ thông tin. Đặc biệt, Retry-After chính xác của ngân sách tài khoản có thể phản ánh hoạt động của nạn nhân cho người ngoài.

Việc làm phản hồi nhất quán không đòi hỏi giữ thread bằng các khoảng ngủ dài. Có thể thiết kế đường tiếp nhận và xử lý bất đồng bộ để giảm khác biệt không cần thiết, đồng thời bảo vệ năng lực phục vụ.

## 10. Tránh biến giới hạn thành công cụ khóa nạn nhân

Kẻ ngoài thường chỉ cần biết email hoặc username để tiêu hao ngân sách khởi tạo recovery. Nếu ngưỡng đó khóa luôn đăng nhập, kiểm tra mọi bằng chứng và mọi phương thức dự phòng, cơ chế phòng vệ đã tạo ra một đường từ chối dịch vụ.

OWASP khuyến cáo không khóa tài khoản chỉ vì bị tấn công qua chức năng quên mật khẩu. Xem [OWASP — Forgot Password: Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-lockout).

Cần phân biệt hai tình huống:

**Hết ngân sách gửi hoặc khởi tạo:** có thể tạm ngừng tạo thêm thông điệp, trong khi một giao dịch hợp lệ và bằng chứng còn hiệu lực tiếp tục theo các giới hạn riêng của chúng.

**Hết ngân sách xác minh mã:** không thể tiếp tục kiểm tra mọi OTP vượt giới hạn chỉ để tìm xem request nào là của chủ tài khoản. Làm vậy sẽ mở lại đường dò mã. Người dùng có thể phải chờ hoặc dùng một phương thức độc lập đã thiết lập với chính sách thích hợp.

Một passkey dự phòng hoặc recovery code có thể thuộc luồng xác minh riêng nếu thiết kế mức bảo đảm cho phép. Không cấp ngoại lệ chỉ vì người gọi đánh dấu “tôi là chủ tài khoản” hoặc hoàn thành CAPTCHA.

Các nguyên tắc giúp giảm tổn hại:

1. Không xóa hiệu lực của quyền recovery hợp lệ chỉ vì có thêm request chưa xác minh.
2. Không kéo dài thời gian chặn vô hạn do mọi request đã bị chặn.
3. Không tạo ngoại lệ miễn mọi giới hạn cho tài khoản “quan trọng”.
4. Không cho nhân viên hỗ trợ đặt lại bộ đếm tùy ý mà thiếu thẩm quyền và bằng chứng.
5. Không coi thao tác resend, đổi IP, tạo session mới hoặc tạo challenge mới là xác thực thành công.

Điều kiện reset bộ đếm cần được ghi rõ cho từng chính sách. Việc xác minh thành công một bằng chứng phù hợp có thể là một điều kiện trong thiết kế; một request khởi tạo mới hoặc một lỗi nhà cung cấp không tự có cùng ý nghĩa.

Không có một giới hạn mục tiêu công khai nào vừa phân biệt hoàn hảo chủ tài khoản với kẻ ngoài vừa không cần bằng chứng. Thiết kế phải thừa nhận sự đánh đổi và chuẩn bị đường recovery dự phòng an toàn.

## 11. Kho trạng thái, nhiều instance và số lượng key

Giới hạn theo định danh chỉ có ý nghĩa khi những request cùng mục tiêu thực sự chia sẻ ngân sách.

Nếu mỗi instance cho phép L lượt độc lập, N instance có thể tạo gần N × L lượt trong cùng giai đoạn. Nếu mỗi vùng triển khai tự cấp toàn bộ ngân sách, chuyển vùng cũng có thể lấy thêm lượt.

Cần chọn nguồn trạng thái có thẩm quyền hoặc phân bổ ngân sách giữa các vùng sao cho tổng vẫn trong phạm vi chính sách. Không chỉ dựa vào việc phần lớn request thường đến cùng một instance.

Các tình huống mất trạng thái cần được tính tới:

| Tình huống | Rủi ro |
| --- | --- |
| Restart kho chỉ lưu trong bộ nhớ | Bộ đếm có thể quay về chưa có lượt |
| Eviction do thiếu bộ nhớ | Một định danh đang bị giới hạn có thể được xem như mới |
| Đọc replica trễ | Quyết định dựa trên ngân sách cũ |
| Failover mất cập nhật gần nhất | Số lượt thực tế lớn hơn số được nhớ |
| Thay định dạng key khi triển khai | Tạo một ngân sách mới ngoài ý muốn |

Một script nguyên tử không tự bảo đảm độ bền sau mọi sự cố. Đối với ngân sách chống đoán bằng chứng ngắn, cần chọn cơ chế lưu và phương án khi lỗi phù hợp với yêu cầu bảo mật; không mặc định kho rate limit chỉ là cache có thể mất tùy ý.

Khi kho không khả dụng, không tắt giới hạn xác minh rồi tiếp tục dò mã theo cách chỉ kiểm giá trị. Có thể từ chối tạm thời thao tác phụ thuộc kho, giữ phản hồi công khai phù hợp và tiếp tục những đường độc lập vẫn có đủ bảo đảm.

### HMAC không làm số lượng key trở nên hữu hạn

Người gọi có thể gửi vô hạn định danh khác nhau. Dù mỗi định danh được HMAC, kho vẫn có thể nhận vô hạn key.

Cần giới hạn kích thước đầu vào, chi phí chuẩn hóa, tần suất theo nguồn và số trạng thái đang giữ. Dùng TTL phù hợp với thuật toán, theo dõi sức chứa và tránh cấu hình tự xóa bộ đếm quan trọng để dành chỗ cho key rác.

Đừng ghi username, email hoặc HMAC của từng người dùng thành nhãn metric có độ đa dạng không giới hạn. Quan sát nên dùng số liệu tổng hợp; điều tra trường hợp cụ thể đi qua nhật ký có quyền truy cập và thời hạn lưu phù hợp.

## 12. Những tình huống dễ áp dụng sai

**Đổi cách viết email để lấy lượt mới:** nếu các cách viết thật sự cùng ánh xạ đến một tài khoản theo quy tắc của ứng dụng, ngân sách theo accountId phải gom chúng lại. Không sửa bằng cách chuẩn hóa tùy tiện mọi email.

**Xin mã mới sau mỗi lần đoán sai:** ngân sách theo challenge có thể đổi, nhưng ngân sách tổng theo tài khoản và cơ chế xác minh phải giữ đúng chính sách. Resend không phải sự kiện reset thất bại.

**Nhắm một tài khoản từ nhiều IP:** giới hạn nguồn giúp giảm từng nhánh; ngân sách theo định danh kiểm soát tổng trên mục tiêu. Cả hai vẫn cần bảo vệ khỏi khóa nạn nhân.

**Thay hàng nghìn định danh không có thật:** giới hạn từng định danh không đủ. Lớp admission và giới hạn năng lực toàn hệ thống phải chặn việc tạo công việc và trạng thái vô hạn.

**Đổi phiên bản ứng dụng làm key cũ không còn được đọc:** rollout có thể vô tình nạp lại toàn bộ ngân sách. Việc chuyển đổi cần bảo toàn ý nghĩa của trạng thái đang tồn tại.

Một chính sách per identifier hoàn chỉnh phải trả lời được: **định danh nào, hành động nào, cửa sổ nào, nguồn trạng thái nào, điều kiện reset nào và tác động gì tới chủ tài khoản?** Chỉ khi những phần đó nhất quán, việc đếm request mới trở thành kiểm soát recovery có ý nghĩa.
