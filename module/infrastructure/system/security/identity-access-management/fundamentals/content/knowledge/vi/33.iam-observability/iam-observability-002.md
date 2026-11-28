# Authentication failure rate

## 1. Authentication failure rate cho biết điều gì?

**Authentication failure rate** là tỷ lệ các lần xác thực không thành công trong một tập lần xác thực được xác định rõ. Chỉ số này giúp nhận biết vấn đề trong trải nghiệm đăng nhập, cấu hình danh tính, credential của workload hoặc sức khỏe của dịch vụ xác thực.

Một biểu đồ ghi “failure rate = 12%” chưa đủ để kết luận nếu chưa biết:

- Một lần xác thực được tính là request kiểm tra password, một bước MFA hay toàn bộ giao dịch đăng nhập?
- Thất bại gồm từ chối credential, tài khoản bị khóa và lỗi hệ thống hay chỉ một số loại?
- Mẫu số gồm những lần nào?
- Cửa sổ đo và phạm vi dịch vụ là gì?
- Số liệu có bị trùng, thiếu hoặc đến trễ không?

Ví dụ, nhiều người nhập sai password có thể làm tỷ lệ tăng nhưng dịch vụ vẫn xử lý đúng. Ngược lại, nhà cung cấp danh tính timeout cũng làm người dùng không đăng nhập được, nhưng cần một hướng điều tra và phản ứng khác.

Vì vậy, authentication failure rate cần đi cùng phân loại kết quả, số lượng tuyệt đối, độ trễ và chất lượng telemetry. Nó là một tín hiệu quan sát, không tự chứng minh hệ thống bị tấn công hoặc đang hoạt động an toàn.

## 2. Chọn đơn vị đo trước khi tính tỷ lệ

Trong IAM có nhiều hoạt động dễ bị gọi chung là “authentication attempt”:

| Đơn vị | Ví dụ | Điều cần tránh |
|---|---|---|
| Giao dịch đăng nhập hoàn chỉnh | Bắt đầu login, kiểm tra password và MFA, kết thúc bằng kết quả cuối | Trộn từng bước bên trong với kết quả cả luồng |
| Lần kiểm tra credential | Một lần xác minh password hoặc certificate | Xem mọi lần kiểm tra như một người dùng riêng |
| Bước MFA | Một lần xác minh mã hoặc bằng chứng bổ sung | Tính việc phát challenge là thất bại |
| Token refresh | Dùng refresh token để xin credential mới | Gộp tùy tiện vào tỷ lệ đăng nhập tương tác |
| Xác thực request API | Kiểm tra access token của một request | Để lưu lượng API lớn che vấn đề login |
| Xác thực workload | Workload trình bày credential để truy cập | Gộp các kiểu máy và người có hành vi khác nhau |

Trong bài này, chỉ số chính minh họa sử dụng **giao dịch đăng nhập đã có kết quả cuối cùng**. Từng giao dịch có một kết quả cuối trong nguồn đo đã chọn.

Một giao dịch MFA có thể có vài lần nhập mã sai rồi cuối cùng thành công. Trong chỉ số toàn giao dịch, đây là một giao dịch thành công; các lần nhập sai vẫn có thể được đo bằng chỉ số riêng của bước MFA.

Không cộng các bước password, MFA và phát hành session vào cùng một mẫu số rồi gọi chúng là số lần đăng nhập của người dùng.

## 3. Định nghĩa kết quả và công thức

Có thể chia các giao dịch hoàn tất thành ba nhóm:

| Kết quả | Ý nghĩa | Ví dụ |
|---|---|---|
| SUCCESS | Đạt điều kiện xác thực và hoàn tất theo hợp đồng của luồng | Phiên được thiết lập thành công |
| REJECTED | Hệ thống đưa ra quyết định từ chối có ý nghĩa | Credential không hợp lệ hoặc tài khoản không được phép xác thực |
| ERROR | Không hoàn tất thành công do lỗi xử lý hoặc thành phần phụ thuộc | Timeout nguồn danh tính, lỗi xác minh do hạ tầng |

Với cửa sổ W và cùng một phạm vi đo:

```text
N = SUCCESS(W) + REJECTED(W) + ERROR(W)

authentication_failure_rate =
    (REJECTED(W) + ERROR(W)) / N

authentication_rejection_rate =
    REJECTED(W) / N

authentication_error_rate =
    ERROR(W) / N
```

Trong định nghĩa minh họa này, failure rate là tỷ lệ mọi kết quả cuối không thành công. Một tổ chức có thể dùng tên “failure” chỉ cho REJECTED, nhưng phải công bố định nghĩa và đặt nhãn dashboard rõ ràng. Không so sánh hai hệ thống có cùng tên metric nhưng khác tử số hoặc mẫu số.

Nếu muốn trình bày dạng phần trăm, nhân tỷ lệ với 100%.

### Ví dụ tính

Trong 10 phút:

```text
SUCCESS  = 990
REJECTED = 8
ERROR    = 2
N        = 1.000

failure rate   = (8 + 2) / 1.000 = 1%
rejection rate = 8 / 1.000       = 0,8%
error rate     = 2 / 1.000       = 0,2%
```

Ba số có ý nghĩa khác nhau. Chỉ nhìn 1% sẽ không cho biết phần nào do credential bị từ chối và phần nào do hệ thống không xử lý được.

Nếu N bằng 0, tỷ lệ không xác định. Dashboard nên biểu diễn “không có giao dịch hoàn tất” hoặc “không đủ dữ liệu”, không tự hiển thị 0% như thể đã có bằng chứng xác thực hoạt động tốt.

## 4. Những trường hợp không nên phân loại nhầm

### 4.1. Authentication khác authorization

Một request có danh tính hợp lệ nhưng bị từ chối đọc tài liệu là một quyết định authorization, không mặc nhiên là authentication failure.

Cần đo riêng:

```text
Xác thực token thất bại     -> authentication
Token hợp lệ, thiếu quyền  -> authorization
```

Mã phản hồi HTTP có thể hỗ trợ phân loại, nhưng không nên là nguồn duy nhất. Cùng một mã có thể được nhiều lớp sử dụng cho các nguyên nhân khác nhau.

### 4.2. Challenge chưa phải kết quả cuối

Việc hệ thống yêu cầu MFA hoặc chuyển người dùng tới nguồn SSO không phải một lần từ chối xác thực. Giao dịch còn đang tiến hành.

Một lần xác minh MFA bị từ chối có thể là kết quả cuối hoặc vẫn cho thử lại theo workflow. Instrumentation phải dựa trên trạng thái thực tế, không suy ra từ việc một màn hình challenge đã xuất hiện.

### 4.3. Hủy và hết thời gian chờ

Người dùng có thể đóng trình duyệt, bỏ dở hoặc không quay lại từ nhà cung cấp danh tính. Có hai cách mô hình hóa phổ biến:

- Theo dõi chúng bằng trạng thái kết thúc riêng, có công thức completion và abandonment rõ ràng.
- Chỉ đo kết quả hoàn tất tại một điểm, đồng thời theo dõi số giao dịch bắt đầu nhưng chưa kết thúc.

Nếu chọn mẫu số chỉ gồm giao dịch hoàn tất như bài này, cần công bố giới hạn: tỷ lệ có thể không phản ánh những người không bao giờ tới được điểm kết thúc.

Không ghép số bắt đầu theo thời điểm khởi tạo với số kết thúc theo thời điểm hoàn tất trong cùng cửa sổ rồi mặc định chúng thuộc cùng một tập giao dịch. Nếu tính theo cohort bắt đầu, cần chờ hoặc xử lý những giao dịch chưa kết thúc.

### 4.4. Rate limiting và lưu lượng bị chặn sớm

Request bị chặn trước khi đi vào luồng xác thực có thể không thuộc mẫu số giao dịch đăng nhập đã nhận. Nên có chỉ số riêng về request bị chặn tại lớp bảo vệ.

Nếu hệ thống định nghĩa chúng là kết quả cuối của một giao dịch login, cần phân loại và đưa chúng vào công thức một cách nhất quán. Không thay đổi cách đếm giữa các phiên bản mà vẫn so sánh tỷ lệ như không có gì thay đổi.

## 5. Thiết kế nguồn đo và instrumentation

Một hệ thống nhiều tầng có thể ghi cùng một lần lỗi ở gateway, identity service, connector SSO và ứng dụng. Nếu cộng tất cả log lỗi, một giao dịch có thể bị đếm nhiều lần.

Cần chỉ định **nguồn chịu trách nhiệm cho kết quả cuối** của đơn vị đo. Các tầng khác cung cấp metric của riêng chúng, nhưng không được tự cộng vào số giao dịch tổng.

Một luồng khái niệm:

```text
Giao dịch login có ID tương quan
        |
        v
Các bước password / SSO / MFA
        |
        v
Nguồn xác định kết quả cuối
        |
        +--> tăng counter theo outcome và nhóm nguyên nhân
        |
        +--> ghi event có mã tương quan và thông tin tối thiểu
```

Các nguyên tắc cần giữ:

- Mỗi giao dịch logic được ghi kết quả cuối theo đúng hợp đồng đếm.
- Retry vận chuyển cùng một event không trở thành giao dịch xác thực mới.
- Retry nghiệp vụ tạo một lần kiểm tra mới phải được biểu diễn đúng đơn vị đã chọn.
- Có phân biệt giao dịch đã xác thực thành công nhưng lỗi ở giai đoạn khác của ứng dụng.
- Không ghi password, OTP hoặc token để xác định nguyên nhân.

Counter trong bộ nhớ và event audit bền vững có đặc tính khác nhau. Không mặc định chúng luôn trùng tuyệt đối khi tiến trình chết hoặc telemetry bị mất. Cần biết giới hạn và có cách phát hiện khoảng trống, thay vì tuyên bố một callback tăng counter bảo đảm không thiếu hoặc không trùng trong mọi sự cố.

### Pseudocode

```text
onLoginTransactionFinalized(transaction):
    result = classifyTerminalOutcome(transaction)

    recordCompletedCounter(
        flow = "interactive_login",
        methodClass = transaction.methodClass,
        outcome = result.outcome,
        reasonGroup = result.reasonGroup
    )

    recordSanitizedEvent(
        transactionReference = transaction.internalReference,
        outcome = result.outcome,
        reasonGroup = result.reasonGroup,
        producer = trustedProducerIdentity
    )
```

Hàm trên chỉ minh họa điểm ghi nhận. Việc bảo đảm kết quả cuối không bị gọi lặp, phân loại đúng và xử lý restart cần được thiết kế trong workflow thực tế.

## 6. Phân nhóm nguyên nhân có ích

Một hệ thống có thể dùng taxonomy như:

| Nhóm nguyên nhân | Loại kết quả minh họa | Hướng điều tra |
|---|---|---|
| CREDENTIAL_INVALID | REJECTED | Credential sai, cũ hoặc lưu lượng thử sai |
| ACCOUNT_NOT_ALLOWED | REJECTED | Tài khoản bị disable, trạng thái chưa đủ điều kiện |
| MFA_VERIFICATION_REJECTED | REJECTED khi là kết quả cuối | Bước xác minh bổ sung bị từ chối |
| FEDERATION_RESPONSE_INVALID | Tùy nguyên nhân và hợp đồng | Kiểm tra thông điệp, mapping, cấu hình và nguồn |
| IDENTITY_PROVIDER_TIMEOUT | ERROR | Độ trễ hoặc sự cố nguồn phụ thuộc |
| INTERNAL_PROCESSING_ERROR | ERROR | Lỗi ứng dụng, kho phiên hoặc dịch vụ cần thiết |
| WORKLOAD_CREDENTIAL_REJECTED | REJECTED ở flow workload | Credential, đích sử dụng hoặc vòng đời workload |

Không phải mọi phản hồi liên kết không hợp lệ đều có cùng bản chất. Nó có thể do cấu hình sai, dữ liệu đầu vào không hợp lệ hoặc hành vi không được chấp nhận. Taxonomy cần phản ánh khả năng quan sát thực tế, tránh gắn nhãn “tấn công” khi chưa có bằng chứng.

Reason group nên là một tập giá trị được kiểm soát. Không dùng toàn bộ exception message làm label vì vừa khó tổng hợp vừa có thể chứa dữ liệu nhạy cảm.

Thông tin chi tiết hơn có thể nằm trong log đã lọc, được phân quyền và liên kết bằng mã nội bộ. Thông báo trả cho người dùng có thể ít chi tiết hơn log nội bộ để hạn chế tiết lộ trạng thái tài khoản.

## 7. Metric label và cardinality

Một counter minh họa:

```text
iam_auth_completed_total{
    environment="production",
    flow="interactive_login",
    method_class="password_mfa",
    outcome="rejected",
    reason_group="credential_invalid"
}
```

Đây là tên metric và label do bài học tự đặt, không phải schema bắt buộc của một thư viện.

Các chiều có thể hữu ích:

- Môi trường.
- Loại flow.
- Nhóm phương thức xác thực.
- Nhóm ứng dụng hoặc client đã được xác định.
- Khu vực vận hành.
- Nhóm nguồn danh tính.
- Outcome và reason group.

Mỗi tập label tạo ra các chuỗi số liệu riêng. Cần giới hạn số giá trị và kiểm soát nguồn sinh chúng.

Không nên mặc định dùng các giá trị sau làm label:

- Username, email hoặc subject ID.
- Session ID, transaction ID hoặc request ID.
- Token hoặc fingerprint của từng token.
- Địa chỉ IP của từng request.
- URL đầy đủ hoặc exception message tùy ý.
- Tenant ID của một hệ thống có số lượng tenant lớn và biến động mạnh.

Ngay cả một ID đã băm vẫn có thể tạo rất nhiều giá trị khác nhau; băm không giải quyết cardinality.

Nếu cần phân tích tenant hoặc chủ thể, có thể dùng log được phân quyền, truy vấn điều tra hoặc một chiến lược phân nhóm và giới hạn phù hợp. Đừng dùng việc tránh cardinality làm lý do mất hoàn toàn khả năng phát hiện vấn đề của một nhóm nhỏ nhưng quan trọng.

## 8. Tính theo cửa sổ và tổng hợp đúng

### 8.1. Dùng số phát sinh trong cùng cửa sổ

Counter tích lũy từ lúc tiến trình khởi động không phải tỷ lệ của 5 hoặc 10 phút gần nhất.

Ở mức khái niệm:

```text
failed_in_window =
    tổng số phát sinh REJECTED và ERROR trong W

completed_in_window =
    tổng số phát sinh mọi outcome kết thúc trong W

failure_rate = failed_in_window / completed_in_window
```

Khi dùng counter, cơ chế tính số phát sinh cần xử lý reset, restart và thay đổi instance. Thường cần xử lý số tăng của từng chuỗi phù hợp trước khi tổng hợp; không lấy hai tổng counter thô rồi giả định restart không ảnh hưởng.

Tử số và mẫu số phải cùng phạm vi, cửa sổ, loại flow và cách xử lý dữ liệu thiếu.

### 8.2. Không lấy trung bình tùy tiện các tỷ lệ

Ví dụ:

| Nhóm | Giao dịch hoàn tất | Không thành công | Failure rate |
|---|---:|---:|---:|
| Ứng dụng A | 1.000 | 5 | 0,5% |
| Ứng dụng B | 10 | 9 | 90% |
| Tổng | 1.010 | 14 | Khoảng 1,39% |

Trung bình đơn giản của 0,5% và 90% là 45,25%, không phải tỷ lệ tổng.

Tỷ lệ tổng cần lấy tổng tử số chia tổng mẫu số. Nhưng chỉ xem 1,39% cũng che được sự cố rất nặng ở ứng dụng B. Dashboard nên có cả tổng quan và các lát cắt quan trọng.

### 8.3. Trễ dữ liệu và sampling

Nếu log được dùng để tính metric, cần biết event được xếp cửa sổ theo thời điểm xảy ra hay thời điểm thu nhận. Sự kiện tới muộn có thể làm biểu đồ thay đổi hoặc làm cảnh báo lệch thời gian.

Nếu sampling có tỷ lệ khác nhau theo outcome, không lấy số log quan sát được để tính trực tiếp tỷ lệ toàn bộ. Cần cơ chế ước lượng phù hợp hoặc nguồn đếm không bị lệch theo cách đó.

Trace được lấy mẫu hữu ích cho điều tra luồng, nhưng không mặc nhiên là mẫu đại diện để tính authentication failure rate.

## 9. Diễn giải cùng số lượng và các tín hiệu khác

Một tỷ lệ cao ở mẫu nhỏ có độ ổn định thấp. Hai lần lỗi trên ba giao dịch có thể chỉ là một người nhập sai hai lần; nó khác với hàng nghìn lần lỗi trên một ứng dụng đang dùng rộng rãi.

Tuy vậy, mẫu nhỏ không đồng nghĩa ít quan trọng. Một luồng quản trị khẩn cấp hoặc workload thiết yếu có thể có ít request nhưng cần được theo dõi riêng.

Các tín hiệu nên đặt cạnh nhau:

| Tín hiệu | Giá trị bổ sung |
|---|---|
| Số giao dịch và tốc độ phát sinh | Phân biệt biến động tỷ lệ với biến động lưu lượng |
| SUCCESS, REJECTED, ERROR riêng | Tách quyết định từ chối khỏi sự cố kỹ thuật |
| Độ trễ và timeout | Nhận biết thành phần phụ thuộc hoặc xử lý chậm |
| Số giao dịch bắt đầu nhưng chưa kết thúc | Phát hiện bỏ dở và khoảng mù của mẫu số hoàn tất |
| Số request bị chặn trước xác thực | Hiểu tác động của lớp chống lạm dụng |
| Nhóm phương thức và nguồn danh tính | Khoanh vùng một flow bị ảnh hưởng |
| Độ trễ thu nhận, mất event, scrape failure | Đánh giá sức khỏe của chính telemetry |

Tỷ lệ có thể giảm chỉ vì lưu lượng thành công tăng, trong khi số lần thất bại vẫn tăng. Cũng có thể tăng vì lưu lượng thành công giảm chứ không phải số lỗi tăng.

Tỷ lệ thấp không chứng minh không có chiếm đoạt tài khoản. Credential đã bị lộ có thể được sử dụng thành công; cần kết hợp tín hiệu phiên, hành vi và thay đổi quyền theo mục đích giám sát.

## 10. Thiết kế cảnh báo theo mục tiêu

Cần phân biệt ít nhất hai mục tiêu:

**Vận hành.** Phát hiện lỗi kỹ thuật làm người dùng hoặc workload không hoàn tất xác thực.

**An ninh.** Phát hiện mẫu từ chối hoặc hành vi cần điều tra, kể cả khi dịch vụ kỹ thuật vẫn đáp ứng đúng.

Một điều kiện cảnh báo minh họa có thể xét:

```text
tỷ lệ vượt ngưỡng đã chọn cho flow
AND số giao dịch đủ để kết luận ở mức yêu cầu
AND tình trạng kéo dài trong cửa sổ phù hợp
```

Có thể bổ sung điều kiện số lỗi tuyệt đối hoặc theo dõi cả cửa sổ ngắn và dài. Ngưỡng không có một giá trị chung cho mọi hệ thống; cần dựa trên baseline, độ quan trọng, lưu lượng và khả năng phản ứng.

Không nên loại bỏ mọi nhóm ít lưu lượng chỉ vì không đạt một ngưỡng mẫu chung. Với các flow quan trọng, có thể dùng cảnh báo theo sự kiện hoặc kiểm tra tổng hợp được thiết kế riêng.

### Failure rate và SLO

Nếu mục tiêu đo độ tin cậy của nền tảng xác thực, việc người dùng nhập sai credential thường cần được phân biệt với lỗi mà dịch vụ chịu trách nhiệm xử lý.

SLO phải định nghĩa rõ giao dịch đủ điều kiện, kết quả tốt và nguồn đo. Không lấy toàn bộ REJECTED làm downtime một cách máy móc; cũng không gán mọi lỗi cấu hình hoặc timeout thành “lỗi người dùng” để làm số liệu tốt hơn.

Trải nghiệm login và sức khỏe hạ tầng có thể cần hai chỉ số khác nhau. Việc tách chúng giúp tìm đúng bên cần hành động.

### Không phản ứng tự động quá mức

Failure rate tăng không nên trực tiếp khóa hàng loạt tài khoản. Một nguồn SSO lỗi hoặc một cấu hình mới có thể tạo nhiều lần từ chối hợp lệ về mặt quan sát nhưng không phải hành vi của chủ tài khoản.

Các biện pháp phản ứng cần dựa trên chính sách và bằng chứng phù hợp, có giới hạn tác động và cơ chế giám sát kết quả.

## 11. Quy trình điều tra một đợt tăng tỷ lệ

Có thể đi theo trình tự:

1. Xác nhận telemetry có hoạt động và công thức không vừa bị thay đổi.
2. Xem tử số, mẫu số và lưu lượng tuyệt đối.
3. Tách REJECTED và ERROR.
4. Khoanh vùng flow, phương thức, ứng dụng, nguồn danh tính và khu vực.
5. Đối chiếu thời điểm với triển khai, cấu hình, xoay credential hoặc thay đổi nguồn phụ thuộc.
6. Mở log và trace được phép xem để tìm nguyên nhân cụ thể.
7. Chọn biện pháp xử lý tương xứng rồi kiểm tra lại cả tỷ lệ và số lượng.

Một số ví dụ:

| Quan sát | Giả thuyết cần kiểm tra |
|---|---|
| ERROR tăng cùng timeout ở một nguồn SSO | Thành phần phụ thuộc hoặc kết nối có vấn đề |
| REJECTED tăng ở workload sau thay credential | Credential, đích sử dụng hoặc triển khai chưa đồng bộ |
| Từ chối tăng trên một số nhóm nhưng lỗi kỹ thuật bình thường | Thay đổi tài khoản, mapping hoặc policy liên quan |
| Số lỗi tăng nhưng tỷ lệ tổng ổn định | Mẫu số cũng tăng; cần xét số lượng tuyệt đối |
| Dashboard về 0 giao dịch khi login vẫn có lưu lượng | Instrumentation hoặc pipeline quan sát có khoảng trống |
| MFA transaction hoàn tất giảm nhưng lỗi cuối không tăng | Có thể người dùng bỏ dở hoặc flow đang treo trước kết quả cuối |

Đây là các giả thuyết, không phải kết luận tự động. Nếu có nghi ngờ hành vi lạm dụng, cần điều tra trong phạm vi dữ liệu và quyền được cấp, không suy ra chỉ từ một tỷ lệ.

Không sửa sự cố bằng cách bỏ xác thực hoặc mở rộng quyền cho mọi request. Mục tiêu là phục hồi luồng hợp lệ mà vẫn giữ ranh giới bảo vệ.

## 12. Bảo vệ dữ liệu và kiểm chứng phép đo

Telemetry xác thực có thể chứa thông tin về tài khoản, nguồn truy cập và các cơ chế bảo vệ. Cần phân quyền dashboard, log và khả năng xuất dữ liệu theo nhu cầu.

Không ghi password, OTP, recovery code, access token hoặc cookie. Nếu cần liên kết, dùng ID nội bộ không phải credential và kiểm soát quyền truy vấn.

Các giá trị như IP hoặc header client cần có nguồn và độ tin cậy rõ ràng. Một giá trị tự khai không nên được trình bày như danh tính nguồn đã xác minh. Log chi tiết phải được giới hạn dữ liệu, thời gian lưu và khả năng truy cập phù hợp với chính sách đã xác định.

Các tình huống kiểm chứng nên bao gồm:

| Tình huống | Kết quả đo mong đợi |
|---|---|
| Login hoàn tất thành công | Một kết quả cuối SUCCESS trong nguồn đo chính |
| Credential bị từ chối ở kết quả cuối | Một REJECTED với nhóm nguyên nhân phù hợp |
| Nguồn danh tính timeout | ERROR được tách khỏi từ chối credential |
| MFA phát challenge | Không tự tạo authentication failure |
| MFA sai một lần rồi login thành công | Chỉ số bước và chỉ số toàn giao dịch giữ đúng nghĩa riêng |
| Người dùng bỏ dở | Không biến mất khỏi mọi quan sát; có completion hoặc abandoned/pending signal phù hợp |
| API từ chối quyền trên tài nguyên | Không tự cộng thành lỗi xác thực |
| Event được chuyển tiếp lặp | Không bị đếm như giao dịch mới ngoài hợp đồng |
| Instance restart | Cách tính cửa sổ xử lý reset counter phù hợp |
| Không có giao dịch hoàn tất | Tỷ lệ không xác định, không được diễn giải là 0% lỗi |
| Một nhóm nhỏ có sự cố nặng | Lát cắt vẫn giúp phát hiện dù tỷ lệ tổng thấp |
| Telemetry ngừng thu nhận | Có tín hiệu chất lượng dữ liệu, không coi là hệ thống hết lỗi |

Authentication failure rate hữu ích khi đơn vị đếm, outcome, cửa sổ và phạm vi đều rõ ràng. Khi tách từ chối khỏi lỗi kỹ thuật, theo dõi cả mẫu số và khoảng trống quan sát, chỉ số mới giúp người vận hành và đội an ninh hiểu đúng điều đang xảy ra thay vì phản ứng với một phần trăm thiếu ngữ cảnh.
