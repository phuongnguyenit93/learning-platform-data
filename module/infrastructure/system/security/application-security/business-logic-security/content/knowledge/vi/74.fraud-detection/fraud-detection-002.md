# Fraud rule evaluation — Đánh giá quy tắc phát hiện gian lận

## Mục tiêu và phạm vi

Fraud rule evaluation là quá trình dùng dữ liệu của một thao tác và ngữ cảnh liên quan để kiểm tra các quy tắc phát hiện gian lận, sau đó đưa ra quyết định xử lý có thể giải thích và thực thi.

Trong bảo mật logic nghiệp vụ, một rule engine chỉ có ích khi kết quả của nó gắn với đúng người dùng, tenant, đối tượng, phiên bản dữ liệu và hành động. Một quyết định “rủi ro thấp” không được cấp quyền sửa giá, bỏ qua quyền sở hữu hoặc thực hiện lại một giao dịch đã hoàn tất.

Sau bài học, bạn có thể:

- Phân biệt bất biến nghiệp vụ bắt buộc với tín hiệu rủi ro.
- Chuẩn hóa dữ liệu đầu vào và định nghĩa rõ cửa sổ đếm hành vi.
- Thiết kế ngữ nghĩa rule, thứ tự đánh giá và cách hợp nhất kết quả.
- Xử lý dữ liệu thiếu, dữ liệu cũ, timeout và xung đột giữa các rule.
- Gắn quyết định với state machine, transaction, idempotency và thời hạn hiệu lực.
- Kiểm thử việc lách rule, thay đổi ngữ cảnh và cạnh tranh giữa nhiều yêu cầu.

Các ngưỡng, điểm số và thời gian trong bài chỉ là ví dụ thiết kế. Chúng cần được lựa chọn bằng dữ liệu, rủi ro và năng lực vận hành của từng sản phẩm.

## 1. Đánh giá gian lận nằm ở đâu trong quy trình nghiệp vụ?

Xét một nền tảng bán khóa học có checkout và mã ưu đãi. Người dùng có thể tìm cách:

- Dùng nhiều tài khoản để nhận ưu đãi không dành cho mình.
- Thử nhiều phương thức thanh toán trong thời gian ngắn.
- Chia nhỏ hành vi để luôn nằm dưới một ngưỡng đơn lẻ.
- Thực hiện nhiều request đồng thời trước khi bộ đếm được cập nhật.
- Lấy quyết định cho một giỏ hàng rồi đổi giỏ hàng trước khi thanh toán.
- Gọi trực tiếp endpoint thực thi để bỏ qua bước đánh giá.

Một luồng phù hợp có thể là:

~~~mermaid
flowchart TD
    A[Yêu cầu checkout] --> B[Xác thực và quyền theo đối tượng]
    B --> C[Kiểm tra bất biến và tính lại dữ liệu nghiệp vụ]
    C --> D[Tạo snapshot và thu thập tín hiệu]
    D --> E[Đánh giá bộ rule đúng phiên bản]
    E --> F[Hợp nhất quyết định và lưu bằng chứng]
    F --> G{Kết quả}
    G -->|DENY| H[Chặn thao tác]
    G -->|REVIEW| I[Chờ xem xét]
    G -->|CHALLENGE| J[Yêu cầu xác minh bổ sung]
    G -->|ALLOW| K[Cổng thực thi]
    J --> K
    I --> L[Quyết định mới sau xem xét]
    L --> K
    K --> M[Kiểm tra lại điều kiện cần thiết và thực hiện nguyên tử]
~~~

Các mũi tên sau challenge và review không có nghĩa “hoàn tất bước đó thì luôn cho qua”. Cổng thực thi vẫn phải kiểm tra bằng chứng, phạm vi, thời hạn, trạng thái và những thay đổi có liên quan.

### 1.1. Bất biến bắt buộc và tín hiệu rủi ro có vai trò khác nhau

| Loại điều kiện | Ví dụ | Hành vi |
| --- | --- | --- |
| Bất biến nghiệp vụ | Tổng tiền tính từ dữ liệu tin cậy; số lượng hợp lệ | Sai thì không thực hiện thao tác |
| Quyền theo đối tượng | Actor được phép checkout giỏ hàng này trong tenant này | Sai thì từ chối, không bù bằng điểm rủi ro thấp |
| Tín hiệu gian lận | Thiết bị mới, nhiều lần thất bại gần đây | Có thể cộng điểm hoặc yêu cầu xác minh |
| Lệnh chặn có thẩm quyền | Phương thức thanh toán bị khóa trong hệ thống | Áp dụng theo chính sách chặn, không để allowlist thông thường ghi đè |

Một tài khoản lâu năm không được thanh toán thay giỏ hàng của người khác. Một thiết bị từng được tin cậy không được đổi `amount` trong request để trả ít hơn.

OWASP nhấn mạnh việc tính lại giá trị ảnh hưởng đến bảo mật ở server và kiểm tra workflow bằng trạng thái rõ ràng. Bài này sử dụng các nguyên tắc đó làm nền cho lớp đánh giá gian lận, thay vì coi rule engine là nơi thay thế mọi kiểm soát nghiệp vụ. [OWASP Business Logic Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html#always-re-derive-security-relevant-values-server-side).

### 1.2. Kết quả ALLOW có nghĩa gì?

Trong bài này:

> ALLOW nghĩa là bộ chính sách gian lận được áp dụng cho snapshot hiện tại không yêu cầu chặn, xem xét hoặc xác minh bổ sung. Nó không phải quyền thực hiện mọi thao tác.

Có thể biểu diễn điều kiện thực thi:

~~~text
canExecute =
    authenticationValid
    AND objectAuthorizationValid
    AND businessInvariantsHold
    AND workflowStateAllowsExecution
    AND applicableFraudDecisionAllowsExecution
    AND decisionBindingStillValid
    AND idempotencyAndConcurrencyChecksPass
~~~

Nếu một vế sai, một `riskScore = 0` không làm điều kiện tổng trở thành đúng.

## 2. Dữ liệu đầu vào: đúng nguồn, đúng nghĩa, đúng thời điểm

### 2.1. Không để client tự khai các dữ kiện quyết định rủi ro

Client có thể gửi ý định mua hàng và dữ liệu cần nhập. Các dữ kiện sau phải được phân giải hoặc kiểm chứng ở backend:

| Dữ kiện | Nguồn phù hợp trong ví dụ | Lỗi cần tránh |
| --- | --- | --- |
| Actor và tenant | Ngữ cảnh xác thực và quyền đã kiểm tra | Tin `userId` hoặc `tenantId` do client tự khai |
| Tổng tiền, loại tiền | Giá, ưu đãi và quy tắc tính tiền phía server | Dùng `total` từ frontend để so ngưỡng |
| Tuổi tài khoản | Thời điểm tạo tài khoản trong hệ thống | Nhận `accountAgeDays` từ request |
| Số lần thử gần đây | Kho sự kiện và bộ đếm có kiểm soát | Tin `recentAttempts = 0` từ client |
| Trạng thái khóa | Nguồn quản trị có thẩm quyền | Dùng cờ `blocked = false` trong payload |
| Kết quả xác minh | Bằng chứng được server xác thực | Tin `challengePassed = true` |
| IP và thông tin thiết bị | Metadata qua ranh giới tin cậy đã xác định | Tin header chuyển tiếp từ bất kỳ nguồn nào |

Thiết bị và IP thường là tín hiệu có thể thiếu, bị thay đổi hoặc dùng chung. Không mặc định chúng là danh tính duy nhất của một con người.

Với tiền, dùng biểu diễn chính xác theo hợp đồng loại tiền, chẳng hạn số nguyên theo đơn vị đã quy định hoặc kiểu decimal phù hợp. Không so ngưỡng tiền bằng số dấu phẩy động tùy ý; không mặc định mọi loại tiền có cùng số chữ số thập phân.

### 2.2. Tạo snapshot có định danh và phiên bản

Một evaluation context có thể chứa:

~~~text
tenantId, actorId, objectId, objectVersion
operationId, action, requestFingerprint
amount, currency, pricingVersion
evaluationTime
featureSnapshotId, featureSchemaVersion
featureValues + featureQuality + sourceVersion
ruleSetVersion, ruleSetDigest
~~~

Snapshot giúp trả lời: rule đã nhìn thấy dữ liệu gì khi đưa ra quyết định?

Không cần sao chép mọi dữ liệu nhạy cảm vào bản ghi quyết định. Có thể lưu tham chiếu có phiên bản, thông tin tối thiểu và dấu vết cần thiết theo chính sách lưu giữ.

Một hash của đầu vào chỉ phát hiện khác biệt khi được tạo từ dữ liệu chuẩn hóa thích hợp. Nó không chứng minh dữ liệu ban đầu là đúng và không thay thế việc bảo vệ quyền ghi snapshot.

### 2.3. Phân biệt “không có”, “bằng 0” và “không lấy được”

Ví dụ feature `failedPaymentAttempts5m`:

- `PRESENT(0)`: nguồn dữ liệu xác nhận không có lần thất bại trong cửa sổ.
- `MISSING`: dữ liệu cần có nhưng chưa tồn tại.
- `STALE`: dữ liệu quá cũ so với hợp đồng của rule.
- `ERROR`: không lấy được do lỗi.
- `NOT_APPLICABLE`: feature không áp dụng cho loại thao tác này.

Không chuyển tất cả thành số 0. Một timeout ở kho dữ liệu không phải bằng chứng tài khoản chưa từng thử thanh toán.

Với feature cần độ mới, lưu cả thời điểm quan sát, thời điểm sự kiện và thông tin độ trễ có liên quan. Dùng ngưỡng tuổi dữ liệu theo từng feature; dữ liệu địa chỉ tài khoản và số lượt thử trong vài phút có yêu cầu khác nhau.

Thiếu dữ liệu bắt buộc phải dẫn tới hành vi đã định nghĩa, ví dụ REVIEW với lý do `INCOMPLETE_EVALUATION`. Không gắn nhãn khách hàng là gian lận chỉ vì hệ thống thu thập feature bị lỗi.

### 2.4. Cửa sổ đếm phải có ngữ nghĩa thống nhất

Giả sử rule dùng số lần thử thanh toán trong 5 phút, bao gồm lần thử logic hiện tại:

~~~text
window = (evaluationTime - 5 phút, evaluationTime]
key    = tenantId + actorId + action
count  = số operationId thử thanh toán khác nhau trong cửa sổ
~~~

Tại 10:00:00, sự kiện lúc 09:55:00 nằm ngoài cửa sổ theo định nghĩa này. Cần sử dụng cùng cách xử lý biên khi tính feature, replay và kiểm thử.

Phải chốt thêm:

- Đếm lần thử, lần được chấp nhận hay lần thành công?
- Retry cùng `operationId` có được tính thêm không?
- Dùng thời điểm sự kiện hay thời điểm hệ thống tiếp nhận?
- Sự kiện đến trễ, trùng hoặc ở tương lai được xử lý thế nào?
- Đếm theo actor, thiết bị, phương thức thanh toán hay kết hợp nhiều chiều?

Trong ví dụ, retry cùng một lần thử logic không tăng bộ đếm lần thử nghiệp vụ, nhưng vẫn có thể được ghi ở lớp chống lạm dụng request. Hai lớp đếm phục vụ mục đích khác nhau.

## 3. Định nghĩa một rule đủ rõ để thực thi

### 3.1. Một rule không chỉ gồm biểu thức boolean

Một rule nên có:

| Thành phần | Mục đích |
| --- | --- |
| ID và version | Định danh ổn định và truy vết thay đổi |
| Phạm vi áp dụng | Tenant, hành động, loại đối tượng và điều kiện applicability |
| Feature phụ thuộc | Những dữ kiện cần có, kiểu và độ mới |
| Điều kiện match | Biểu thức có ngữ nghĩa xác định |
| Hiệu ứng | Chặn, review, challenge hoặc cộng điểm |
| Mức bắt buộc | Cách xử lý khi không đánh giá được |
| Chính sách lỗi | Timeout, kiểu dữ liệu sai, feature thiếu |
| Reason code | Giải thích nội bộ có cấu trúc |
| Giai đoạn và ưu tiên | Quy định thứ tự nếu engine có phụ thuộc thứ tự |
| Khoảng kích hoạt | Thời điểm và bản phát hành được áp dụng |

Ví dụ dạng khai báo minh họa, không gắn với một thư viện cụ thể:

~~~yaml
id: NEW_ACCOUNT_HIGH_VALUE
version: 3
action: CHECKOUT
requiredFeatures:
  - amountVnd
  - accountAgeSeconds
condition:
  all:
    - amountVnd_gte: 2000000
    - accountAgeSeconds_lt: 86400
effect:
  action: CHALLENGE
reasonCode: NEW_ACCOUNT_HIGH_VALUE
onIndeterminate:
  action: REVIEW
~~~

Cần định nghĩa rõ `gte`, `lt`, đơn vị, feature bắt buộc và cách xử lý dữ liệu thiếu. Không để người đọc phải đoán “tài khoản mới” là dưới 24 giờ hay chưa qua ngày lịch đầu tiên.

### 3.2. Phân biệt trạng thái đánh giá với quyết định xử lý

Trạng thái của một rule có thể là:

~~~text
MATCH
NO_MATCH
NOT_APPLICABLE
UNKNOWN
ERROR
~~~

- `MATCH`: đánh giá được và điều kiện đúng.
- `NO_MATCH`: đánh giá được và điều kiện sai.
- `NOT_APPLICABLE`: đã xác định rule không thuộc ngữ cảnh hiện tại.
- `UNKNOWN`: thiếu hoặc không đủ chất lượng dữ liệu để kết luận.
- `ERROR`: thực thi rule gặp lỗi.

Một quyết định tổng hợp có thể là `ALLOW`, `CHALLENGE`, `REVIEW` hoặc `DENY`. Chất lượng của lần đánh giá lại là một thuộc tính riêng, ví dụ `COMPLETE`, `DEGRADED`, `FAILED`.

Không biến exception thành `NO_MATCH`, và không ghi `COMPLETE` khi một rule bắt buộc đã bị bỏ qua.

### 3.3. Bộ rule minh họa

| Rule | Điều kiện | Hiệu ứng |
| --- | --- | --- |
| D10 | Phương thức thanh toán bị khóa theo nguồn có thẩm quyền | DENY |
| V20 | Số lần thử logic trong 5 phút, kể cả lần hiện tại, từ 6 trở lên | REVIEW |
| C30 | Tài khoản dưới 24 giờ và tổng tiền từ 2.000.000 VND | CHALLENGE |
| S40 | Thiết bị mới theo dữ kiện đủ chất lượng | Cộng 25 điểm |
| S50 | Có từ 3 lần thanh toán thất bại trong 5 phút | Cộng 45 điểm |

Ngưỡng điểm của ví dụ:

~~~text
score >= 70       => REVIEW
30 <= score < 70  => CHALLENGE
score < 30        => ALLOW nếu các điều kiện còn lại đều thỏa
~~~

Điểm số này không phải xác suất gian lận. Không diễn giải 70 điểm thành “70% chắc chắn gian lận” nếu hệ thống chưa có mô hình và kiểm định cho cách diễn giải đó.

Các feature có thể tương quan. Cộng điểm cho nhiều biến thể của cùng một hành vi có thể làm mức xử lý tăng không hợp lý; cấu hình cần tính đến điều này.

## 4. Hợp nhất kết quả mà không tạo đường bỏ qua rule

### 4.1. Chọn chiến lược đánh giá tường minh

Các engine có thể hỗ trợ “rule đầu tiên match”, “đánh giá tất cả”, hoặc các giai đoạn có ưu tiên. Không có một ngữ nghĩa mặc định phù hợp cho mọi sản phẩm.

Với ví dụ này:

1. Các kiểm tra quyền và bất biến bắt buộc được thực hiện riêng.
2. Đánh giá bộ rule áp dụng trên cùng snapshot.
3. Thu thập các hiệu ứng trực tiếp, điểm và trạng thái thiếu dữ liệu.
4. Áp dụng chính sách lỗi.
5. Hợp nhất thành quyết định cuối.

Ưu tiên của chính sách minh họa:

~~~text
DENY > REVIEW > CHALLENGE > ALLOW
~~~

Đây là thứ tự do sản phẩm lựa chọn. Nếu sản phẩm yêu cầu vừa xem xét vừa xác minh, nên biểu diễn tập nghĩa vụ thay vì cố ép mọi kết quả vào một mức duy nhất.

### 4.2. Một rule ALLOW không được kết thúc đánh giá quá sớm

Mẫu dễ bị lạm dụng:

~~~java
if (customer.isLongTimeCustomer()) {
    return ALLOW;
}
if (paymentMethod.isBlocked()) {
    return DENY;
}
~~~

Nếu tài khoản lâu năm dùng phương thức đã bị khóa, điều kiện chặn không bao giờ được chạy.

Allowlist thông thường chỉ nên làm thay đổi đúng yếu tố được chính sách cho phép, chẳng hạn bỏ một tín hiệu thiết bị mới. Nó không tự bỏ chặn phương thức thanh toán, quyền sở hữu hoặc bất biến số tiền.

Nếu có ngoại lệ thực sự cần vượt một rule cụ thể, phải ghi rõ rule được miễn, scope, người duyệt, hạn dùng và ưu tiên. Không triển khai dưới dạng `trustedUser => return ALLOW`.

### 4.3. Ví dụ hợp nhất

| Kết quả các rule | Quyết định cuối |
| --- | --- |
| S40 match, S50 không match, các rule khác không match | 25 điểm, ALLOW nếu đánh giá đầy đủ |
| S40 và S50 cùng match | 70 điểm, REVIEW |
| C30 match và tổng điểm 25 | CHALLENGE |
| D10 match cùng bất kỳ tín hiệu thuận lợi nào | DENY |
| Không rule nào match nhưng một rule bắt buộc UNKNOWN | REVIEW theo chính sách thiếu dữ liệu |
| Không tải được bộ rule áp dụng | Đánh giá thất bại; không coi là bộ rule rỗng an toàn |

Nếu đánh giá có song song, không dùng “kết quả đầu tiên trả về” làm kết quả tổng. Với các rule độc lập trong mô hình này, thay đổi thứ tự hoàn thành không được làm thay đổi quyết định.

## 5. Pipeline đánh giá có thể truy vết và chạy lại

Một pipeline nên tách các bước sau:

1. **Xác lập ngữ cảnh:** xác thực actor, kiểm tra quyền đối tượng và action.
2. **Chuẩn hóa dữ liệu nghiệp vụ:** tính tiền, kiểm tra loại tiền, số lượng, trạng thái và phiên bản.
3. **Chọn chính sách:** chọn đúng bundle theo tenant, action và thời điểm hiệu lực.
4. **Thu thập feature:** lấy giá trị, chất lượng, nguồn và thời điểm quan sát.
5. **Đóng băng snapshot:** ghi nhận dữ liệu cùng bộ rule sẽ dùng.
6. **Đánh giá rule:** tạo kết quả có trạng thái cho từng rule trong kế hoạch.
7. **Hợp nhất:** áp dụng ngữ nghĩa điểm, hiệu ứng trực tiếp và fallback.
8. **Lưu quyết định:** scope, bằng chứng, nghĩa vụ còn lại, thời hạn và version.
9. **Thực thi tại cổng nghiệp vụ:** chỉ cho phép thay đổi khi mọi điều kiện còn hợp lệ.

Không thực hiện thanh toán hoặc cấp khóa học ngay trong hàm điều kiện của một rule. Khi đánh giá có side effect, replay, shadow evaluation hoặc retry có thể vô tình tạo nghiệp vụ mới.

### 5.1. Ghim phiên bản rule cho từng lần đánh giá

Một evaluation không nên chạy rule D10 phiên bản cũ và S50 phiên bản mới chỉ vì cấu hình được phát hành giữa chừng.

Nạp một bundle bất biến và dùng nó trong suốt evaluation. Lưu cả định danh phiên bản và digest nội dung để phát hiện cấu hình sai hoặc khác nhau giữa các node.

Ghim phiên bản không có nghĩa mọi quyết định cũ được dùng mãi. Chính sách triển khai phải xác định:

- Quyết định cũ còn dùng trong bao lâu?
- Thay đổi nào buộc đánh giá lại?
- Lệnh chặn khẩn cấp có hiệu lực thế nào tại cổng thực thi?
- Các request đang xử lý áp dụng bản nào?

Một trường hợp chặn có thẩm quyền vừa được cập nhật có thể cần được kiểm tra lại trước thực thi, ngay cả khi bundle của evaluation đã được ghim.

### 5.2. Kiểm tra coverage, không chỉ các rule đã trả kết quả

Kế hoạch đánh giá phải cho biết tập rule dự kiến. Sau thực thi, đối chiếu:

~~~text
expectedRuleIds = tập rule phải có trạng thái đánh giá
actualRuleIds   = tập rule thực tế có kết quả

Không thiếu rule bắt buộc.
Không có kết quả trùng ID gây cộng điểm nhiều lần.
Không có rule lạ từ bundle khác.
Không dùng một bundle không phù hợp với action.
~~~

Nếu một tenant cần bộ rule riêng nhưng cấu hình bị thiếu, không tự coi đó là “không có rule nào match”. Một chính sách baseline hợp lệ phải được khai báo rõ; danh sách rỗng do lỗi tải cấu hình là tình huống khác.

### 5.3. Timeout và lỗi phải có đường xử lý hữu hạn

Đặt giới hạn thời gian cho việc lấy feature và đánh giá, đồng thời giới hạn số rule và độ phức tạp biểu thức.

Trong chính sách ví dụ:

| Tình huống | Hành vi |
| --- | --- |
| Thiếu hoặc lỗi feature bắt buộc | REVIEW với lý do đánh giá chưa đầy đủ |
| Rule có hiệu ứng DENY đã match, rule khác bị lỗi | DENY vẫn chi phối, kèm thông tin chất lượng chưa đầy đủ |
| Rule tùy chọn bị lỗi | Áp dụng fallback đã khai báo; không giả thành NO_MATCH |
| Lỗi toàn engine hoặc bundle không hợp lệ | Không thực thi giao dịch; đưa vào luồng chờ hoặc trả lỗi có kiểm soát |
| Lỗi lưu quyết định | Không cho qua bằng kết quả chỉ tồn tại trong bộ nhớ |
| Hết thời hạn chờ review | Chuyển trạng thái theo chính sách, không tự ALLOW |

REVIEW chỉ có ý nghĩa nếu hệ thống thật sự giữ thao tác ở trạng thái chờ và có đường xử lý. Gửi một cảnh báo rồi vẫn cấp khóa học ngay không phải là thực thi quyết định review.

Fail closed có thể là giữ giao dịch chờ hoặc từ chối thực hiện tạm thời. Không nhất thiết phải đánh dấu người dùng là gian lận vĩnh viễn.

## 6. Ví dụ Java: hợp nhất các rule độc lập

Đoạn mã dưới minh họa phép hợp nhất của chính sách trong bài, không phụ thuộc một rule engine cụ thể. Các kiểu và import được rút gọn.

Giả định bundle và cấu trúc kết quả đã được kiểm tra kiểu; điểm mỗi rule nằm trong khoảng 0 đến 100 và hiệu ứng trực tiếp không null.

~~~java
enum Action {
    ALLOW(0), CHALLENGE(1), REVIEW(2), DENY(3);

    final int severity;

    Action(int severity) {
        this.severity = severity;
    }

    static Action stronger(Action a, Action b) {
        return a.severity >= b.severity ? a : b;
    }
}

enum RuleStatus {
    MATCH, NO_MATCH, NOT_APPLICABLE, UNKNOWN, ERROR
}

enum Quality {
    COMPLETE, DEGRADED
}

record RuleResult(
        String ruleId,
        RuleStatus status,
        Action directAction,
        int points) {}

record CombinedDecision(
        Action action,
        int score,
        Quality quality,
        List<String> reasons) {}

CombinedDecision combine(
        Set<String> expectedRuleIds,
        List<RuleResult> results) {

    Set<String> seen = new HashSet<>();
    List<String> reasons = new ArrayList<>();
    Action direct = Action.ALLOW;
    int score = 0;
    boolean incomplete = expectedRuleIds.isEmpty();

    for (RuleResult result : results) {
        if (!expectedRuleIds.contains(result.ruleId())
                || !seen.add(result.ruleId())) {
            throw new InvalidEvaluation("RULE_COVERAGE_INVALID");
        }

        switch (result.status()) {
            case MATCH -> {
                direct = Action.stronger(direct, result.directAction());
                score = Math.min(100, score + result.points());
                reasons.add(result.ruleId() + ":MATCH");
            }
            case UNKNOWN, ERROR -> {
                incomplete = true;
                reasons.add(result.ruleId() + ":" + result.status());
            }
            case NO_MATCH, NOT_APPLICABLE -> {
                // Không tạo hiệu ứng.
            }
        }
    }

    if (!seen.equals(expectedRuleIds)) {
        incomplete = true;
        reasons.add("RULE_COVERAGE_INCOMPLETE");
    }

    if (expectedRuleIds.isEmpty()) {
        reasons.add("APPLICABLE_POLICY_MISSING");
    }

    Action fromScore = score >= 70
            ? Action.REVIEW
            : score >= 30 ? Action.CHALLENGE : Action.ALLOW;

    Action action = Action.stronger(direct, fromScore);

    if (incomplete) {
        action = Action.stronger(action, Action.REVIEW);
    }

    return new CombinedDecision(
            action,
            score,
            incomplete ? Quality.DEGRADED : Quality.COMPLETE,
            List.copyOf(reasons));
}
~~~

Những điểm đáng chú ý:

- Không return ALLOW ngay khi thấy một rule thuận lợi.
- Điểm chỉ đến từ rule MATCH.
- UNKNOWN và ERROR không bị biến thành NO_MATCH.
- Coverage thiếu làm tăng mức xử lý theo fallback của ví dụ.
- Một hiệu ứng DENY không bị điểm thấp hoặc fallback REVIEW làm nhẹ đi.
- Reason code được lưu có cấu trúc để giải thích nội bộ.

`InvalidEvaluation` phải được tầng điều phối xử lý như lỗi đánh giá, không được catch rồi trả ALLOW. Tương tự, mọi lỗi kiểm tra kiểu, điểm âm hoặc dữ liệu kết quả không hợp lệ đều phải đi qua đường lỗi có kiểm soát.

Đây chỉ là phép hợp nhất. `CombinedDecision` chưa đủ để cấp quyền thực thi vì chưa chứa binding với tenant, actor, đối tượng, snapshot và thời hạn.

Với những chính sách có điểm âm, nhóm rule loại trừ nhau hoặc nhiều nghĩa vụ đồng thời, cần mô hình riêng; không sửa tùy tiện phép cộng rồi giữ nguyên các bất biến của ví dụ.

## 7. Từ quyết định đến thực thi: chống dùng kết quả sai ngữ cảnh

### 7.1. Lưu một decision envelope

Một bản ghi quyết định đầy đủ có thể gồm:

~~~text
evaluationId, operationId
tenantId, actorId, action
objectId, objectVersion
requestFingerprint
featureSnapshotId
ruleSetVersion, ruleSetDigest
actionDecision, evaluationQuality
matchedRuleIds, reasonCodes, obligations
evaluatedAt, validUntil
decisionVersion, executionStatus
~~~

Một quyết định cho `cart-A`, tổng tiền 500.000 VND, không được dùng để thanh toán `cart-B` hoặc tổng tiền mới 5.000.000 VND.

Những thay đổi có thể làm mất hiệu lực gồm phương thức thanh toán, người hưởng ưu đãi, loại tiền, nội dung giỏ, địa chỉ có ý nghĩa rủi ro hoặc quan hệ sở hữu. Phải định nghĩa chúng trong contract của snapshot và fingerprint.

Không chỉ nhận `evaluationId` do client gửi rồi kiểm tra rằng bản ghi đó có kết quả ALLOW. Cần đối chiếu toàn bộ phạm vi liên quan với thao tác đang thực hiện.

### 7.2. State machine không cho bỏ qua REVIEW hoặc CHALLENGE

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> EVALUATING: Đủ quyền và bất biến ban đầu
    EVALUATING --> RISK_ALLOWED: ALLOW
    EVALUATING --> CHALLENGE_REQUIRED: Cần xác minh
    EVALUATING --> REVIEW_REQUIRED: Cần xem xét hoặc thiếu dữ liệu
    EVALUATING --> DENIED: DENY
    EVALUATING --> EVALUATION_FAILED: Không tạo được quyết định hợp lệ
    CHALLENGE_REQUIRED --> EVALUATING: Bằng chứng đúng scope được xác thực
    REVIEW_REQUIRED --> EVALUATING: Có kết quả xem xét hợp lệ
    EVALUATION_FAILED --> EVALUATING: Retry có kiểm soát
    RISK_ALLOWED --> EVALUATING: Dữ liệu hoặc thời hạn không còn hợp lệ
    RISK_ALLOWED --> EXECUTING: Cổng thực thi chấp nhận nguyên tử
    EXECUTING --> COMPLETED: Hoàn tất
    EXECUTING --> OUTCOME_UNKNOWN: Chưa xác định kết quả bên ngoài
    OUTCOME_UNKNOWN --> COMPLETED: Đối soát xác nhận
~~~

Chỉ `RISK_ALLOWED` sau kiểm tra tại cổng thực thi mới được chuyển sang `EXECUTING`. Người gọi không được tự đặt trạng thái hoặc gửi `skipFraud = true`.

Bằng chứng challenge phải gắn với actor, thao tác, dữ liệu quan trọng, thời hạn và nghĩa vụ cần đáp ứng. Khi đánh giá lại, chính sách nhận biết đúng nghĩa vụ đã hoàn tất; không mặc định xác minh thành công sẽ bỏ mọi rule.

Kết quả review cũng cần quyền của người xem xét, scope và audit. Một quyết định thủ công không tự bỏ lệnh chặn có thẩm quyền nếu người đó không được cấp quyền ngoại lệ tương ứng.

OWASP khuyến nghị một cổng kiểm tra cuối gắn với thực thi và bảo vệ dữ liệu giao dịch khỏi thay đổi sau khi được cấp quyền. Trong thiết kế này, decision envelope và chuyển trạng thái có điều kiện thực hiện vai trò đó. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html#28-system-should-check-each-transaction-execution-and-make-sure-it-has-been-properly-authorized).

### 7.3. Kiểm tra còn hiệu lực ngay trước quyết định thực thi

Một cổng thực thi có thể yêu cầu:

~~~text
decision.tenantId = authenticatedTenant
decision.actorId = authenticatedActor
decision.action = requestedAction
decision.objectId = currentObject.id
decision.objectVersion = currentObject.version
decision.requestFingerprint = currentRequestFingerprint
decision.actionDecision = ALLOW
decision.evaluatedAt <= decisionTime < decision.validUntil
decision chưa được tiêu thụ cho thao tác khác
các điều kiện chặn hiện hành vẫn cho phép
~~~

Kết hợp kiểm tra với chuyển trạng thái và cập nhật nghiệp vụ trong transaction hoặc bằng cơ chế nguyên tử phù hợp. Chỉ đọc bản ghi quyết định rồi thực hiện nhiều bước không được bảo vệ vẫn có thể tạo TOCTOU.

Nếu đối tượng hoặc feature quan trọng đã đổi, đánh giá lại theo chính sách. Không đặt TTL thật dài chỉ để tránh phải đánh giá lại.

## 8. Bộ đếm hành vi, transaction và idempotency

### 8.1. “Đọc rồi đếm” có thể cho nhiều yêu cầu cùng vượt ngưỡng

Giả sử trước hai request đồng thời đã có 4 lần thử trong cửa sổ. Rule V20 yêu cầu REVIEW khi số lần thử, kể cả lần hiện tại, đạt 6.

Nếu cả hai request đều đọc 4 rồi tự tính `4 + 1 = 5`, cả hai có thể được ALLOW dù tổng số lần thử thực tế đã đạt 6.

Một cách thiết kế là đăng ký mỗi lần thử logic một cách nguyên tử trước khi lấy số đếm:

~~~text
đăng ký operationId nếu chưa tồn tại
cập nhật hoặc tính số lần thử tại điểm tuần tự hóa đã chọn
trả số đếm có bao gồm operationId hiện tại
đánh giá rule trên kết quả đó
~~~

Khi cùng khóa đếm được xử lý tuần tự, một request có thể thấy 5, request còn lại thấy 6. Retry cùng operationId không đăng ký thêm lần thử.

Cần chọn công nghệ và cơ chế phối hợp theo dữ liệu thực tế. Một phép tăng nguyên tử trên một khóa không tự bảo đảm tính nguyên tử cho nhiều cửa sổ, nhiều chiều và một cơ sở dữ liệu nghiệp vụ khác.

### 8.2. Tín hiệu gần đúng không phải hạn mức cứng

Dữ liệu tổng hợp bất đồng bộ có thể hữu ích để phát hiện xu hướng. Nhưng nếu nghiệp vụ yêu cầu “tối đa N lần”, nó cần một cơ chế cưỡng chế hạn mức phù hợp, không chỉ dựa vào feature trễ.

Phải phân biệt:

- **Velocity signal:** một dữ kiện rủi ro có độ trễ và độ chính xác đã biết.
- **Hard quota:** một bất biến cần được kiểm tra và tiêu thụ nguyên tử.
- **Audit event:** bằng chứng về việc một lần thử đã được tiếp nhận.

Trong ví dụ đếm lần thử, sự kiện thử đã được tiếp nhận có thể vẫn tồn tại khi checkout bị từ chối hoặc thất bại. Không rollback nó chỉ vì không bán được khóa học, nếu hợp đồng vốn đếm cả lần thử không thành công.

Nếu cần đếm thành công, đó là feature khác với vòng đời cập nhật riêng. Đặt tên feature theo đúng ngữ nghĩa để tránh rule dựa vào một con số mơ hồ.

### 8.3. Retry evaluation và retry nghiệp vụ có định danh khác nhau

- `operationId`: thao tác nghiệp vụ logic có payload được ràng buộc.
- `evaluationId`: một lần đánh giá trên snapshot và phiên bản chính sách cụ thể.
- `executionAttemptId`: một lần thử giao hiệu ứng của thao tác đó.

Một operation có thể có evaluation mới vì quyết định cũ đã hết hạn hoặc có dữ kiện mới. Điều đó không tự tạo một lần thử mua hàng mới trong bộ đếm đã chọn.

Với API idempotency:

1. Giới hạn khóa theo tenant, actor và loại hành động.
2. Ràng buộc với fingerprint; cùng khóa nhưng payload khác phải gây xung đột.
3. Claim nguyên tử để chỉ một request khởi tạo thao tác.
4. Lưu trạng thái và kết quả bền vững.
5. Kiểm tra quyền hiện tại trước khi trả kết quả đã lưu.

Retry của thao tác đã hoàn tất chỉ trả lại kết quả phù hợp, không thu tiền hoặc cấp quyền truy cập khóa học lần nữa.

Khi hệ thống thanh toán bên ngoài timeout sau khi đã tiếp nhận, kết quả có thể chưa xác định. Dùng cơ chế idempotency của hệ thống đích hoặc đối soát theo contract; không lấy lý do “fraud engine đã ALLOW” để gửi một khoản thu mới.

## 9. Quản lý rule như một thay đổi có quyền tác động nghiệp vụ

### 9.1. Tách quyền soạn, duyệt và phát hành

Một thay đổi rule có thể làm hàng loạt giao dịch bị chặn hoặc được cho qua. Cần kiểm soát người có thể:

- Sửa điều kiện, điểm và ngưỡng.
- Đổi fallback khi feature lỗi.
- Tạo allowlist hoặc ngoại lệ.
- Bật, tắt, lên lịch và rollback bundle.
- Xem feature nhạy cảm và reason code chi tiết.

Lưu người thay đổi, người phê duyệt, lý do, diff cấu hình, tập kiểm thử và bản phát hành. Không cung cấp một endpoint hỗ trợ cho phép ghi đè `riskDecision = ALLOW` mà không có quyền, scope và kiểm toán.

Lệnh chặn khẩn cấp có thể có quy trình khác, nhưng vẫn cần nguồn thẩm quyền và ngữ nghĩa ưu tiên rõ ràng. Rollback một bundle cũng phải tạo dấu vết; không sửa nội dung của một version đã dùng trong quyết định cũ.

### 9.2. Rule khai báo cần ngôn ngữ bị giới hạn

Nếu cho cấu hình biểu thức, chỉ cho phép các toán tử, kiểu và feature đã được phê duyệt. Giới hạn:

- Độ sâu biểu thức và số điều kiện.
- Độ dài chuỗi, kích thước danh sách và số phần tử cần duyệt.
- Thời gian CPU, số phép tính và ngân sách truy cập feature.
- Các toán tử tìm kiếm hoặc biểu thức chính quy có chi phí cao.
- Khả năng truy cập dữ liệu theo tenant.

Không thực thi chuỗi rule như mã Java, script hoặc biểu thức có quyền gọi phương thức bất kỳ. Rule engine không nên tự truy cập filesystem, mạng, reflection hoặc bí mật của ứng dụng.

Những feature cần lấy từ dịch vụ ngoài nên đi qua adapter có contract, timeout và kiểm soát quyền. Không để mỗi rule tự gọi một URL do người soạn cấu hình.

### 9.3. Shadow evaluation không được tạo hiệu ứng thật

Một quy trình phát hành có thể gồm:

1. Kiểm tra schema, kiểu và tính đầy đủ của bundle.
2. Chạy tập dữ liệu giả hoặc dữ liệu được xử lý phù hợp cho replay.
3. So sánh quyết định mới và cũ trên cùng snapshot.
4. Chạy shadow để ghi kết quả đề xuất mà chưa thực thi chính sách mới.
5. Canary trên nhóm được xác định ổn định.
6. Theo dõi và mở rộng hoặc rollback.

Replay và shadow phải dùng đường đánh giá không có side effect. Không tăng lại bộ đếm lần thử, gửi challenge thật, tạo ticket review thật hoặc gọi thanh toán chỉ vì đang thử rule mới.

Canary cần cách phân nhóm ổn định, không để client chọn bằng một trường request và không đổi nhóm ngẫu nhiên ở mỗi retry. Mỗi evaluation vẫn phải chỉ rõ bundle thực sự được áp dụng.

Replay cùng feature snapshot, cùng bundle, cùng thời gian đánh giá và cùng phiên bản ngữ nghĩa engine phải tạo cùng quyết định. Với trace hoặc fingerprint cần ổn định, chuẩn hóa cả thứ tự danh sách reason code trước khi băm.

## 10. Kiểm thử hành vi đánh giá và các cách lách rule

### 10.1. Tập kiểm thử nhỏ cho bộ rule minh họa

Giả sử dữ liệu đầy đủ, không có phương thức bị khóa và chưa chạm ngưỡng velocity, trừ khi dòng ghi khác:

| Ngữ cảnh | Rule hoặc điểm đáng chú ý | Kết quả |
| --- | --- | --- |
| Tài khoản 48 giờ, 1.000.000 VND, thiết bị cũ, không thất bại | 0 điểm | ALLOW |
| Cùng ngữ cảnh nhưng thiết bị mới | S40, 25 điểm | ALLOW |
| Thiết bị cũ, có 3 thất bại gần đây | S50, 45 điểm | CHALLENGE |
| Thiết bị mới và có 3 thất bại gần đây | S40 + S50, 70 điểm | REVIEW |
| Tài khoản 23 giờ, 2.000.000 VND, không tín hiệu khác | C30 | CHALLENGE |
| Tài khoản đúng 24 giờ, 2.000.000 VND, không tín hiệu khác | C30 không match | ALLOW |
| Số lần thử bao gồm hiện tại đúng bằng 6 | V20 | REVIEW |
| Phương thức bị khóa, tài khoản lâu năm | D10 | DENY |
| Dữ liệu tuổi tài khoản bắt buộc bị lỗi | UNKNOWN hoặc ERROR theo contract | REVIEW |
| Không có bundle áp dụng vì lỗi cấu hình | Coverage không hợp lệ | Không thực thi; không coi là ALLOW |

Bổ sung các ca ngay dưới, đúng bằng và ngay trên ngưỡng. Đối với C30, cần kiểm thử cả hai vế điều kiện: thời gian và số tiền.

### 10.2. Ma trận lạm dụng logic

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Client gửi tổng tiền thấp hơn giá server | Rule dùng tổng tiền tính lại; không mua được với giá giả |
| Client tự khai tài khoản lâu năm hoặc không có thất bại | Feature có thẩm quyền không bị ghi đè |
| Thêm `skipFraud`, `trustedUser` hoặc `challengePassed` | Không mở đường bỏ qua chính sách |
| Gọi trực tiếp endpoint thực thi khi còn REVIEW | Không phát sinh hiệu ứng nghiệp vụ |
| Dùng evaluation ID của actor hoặc tenant khác | Bị chặn trước khi dùng kết quả |
| Đổi giỏ, loại tiền, phương thức thanh toán sau ALLOW | Binding mất hiệu lực hoặc buộc đánh giá lại |
| Dùng quyết định tại đúng `validUntil` | Bị từ chối theo khoảng hiệu lực đã định nghĩa |
| Feature bắt buộc null, thiếu, stale hoặc timeout | Không biến thành giá trị an toàn mặc định |
| Một rule bắt buộc ném exception | Không trở thành NO_MATCH |
| Một rule ALLOW chạy trước D10 | D10 vẫn có hiệu lực theo chính sách |
| Kết quả rule bị lặp ID | Không cộng điểm hai lần hoặc che mất lỗi coverage |
| Bundle thay đổi khi các rule chạy song song | Evaluation vẫn dùng một bundle bất biến |
| Đảo thứ tự hoàn thành các rule độc lập | Quyết định cuối không đổi |
| Hai lần thử khác nhau cùng tới sát ngưỡng velocity | Hành vi tuân theo cơ chế đăng ký và đếm đã chọn |
| Retry cùng operationId trên nhiều node | Không tạo lại lần thử nghiệp vụ hoặc thực thi trùng |
| Cùng idempotency key nhưng thay payload | Bị xử lý như xung đột |
| Review hoàn tất sau khi đối tượng đã đổi version | Không dùng quyết định cũ cho dữ liệu mới |
| Bằng chứng challenge thuộc thao tác khác | Không đáp ứng nghĩa vụ của thao tác hiện tại |
| Cấp khóa học thành công nhưng phản hồi bị mất | Retry không cấp lại hoặc thu tiền lại |
| Shadow và replay được chạy nhiều lần | Không tạo hiệu ứng hay làm thay đổi feature thật |
| Một tenant không có cấu hình hoặc cấu hình sai kiểu | Không vô tình dùng rule của tenant khác |
| Tín hiệu IP hoặc thiết bị dùng chung | Không mặc định đồng nhất mọi người thành một actor |
| Queue giao sự kiện trùng hoặc sai thứ tự | Bộ đếm và trạng thái không bị nhân đôi hay phục hồi sai |
| Rule có biểu thức quá tốn tài nguyên | Bị giới hạn; lỗi không làm fallback sang ALLOW |

Kiểm tra hiệu ứng thực tế, không chỉ mã HTTP hoặc reason code. Một response nói “chờ xem xét” nhưng đã tạo quyền truy cập khóa học là một lỗi thực thi quan trọng.

### 10.3. Kiểm thử theo thuộc tính

Với mô hình cộng điểm không âm và thứ tự ưu tiên của bài:

~~~text
Thêm hiệu ứng DENY không thể làm quyết định nhẹ hơn.

UNKNOWN hoặc ERROR của rule bắt buộc
không thể biến thành ALLOW chỉ vì tổng điểm thấp.

Hoán vị các kết quả rule độc lập
không đổi action và score.

Cùng snapshot + cùng bundle + cùng ngữ nghĩa engine
phải tạo cùng quyết định.

Một quyết định không được thực thi cho scope khác.

Một operation đã hoàn tất không tạo hiệu ứng mới khi retry.
~~~

Không áp dụng máy móc thuộc tính “điểm chỉ tăng” nếu hệ thống có điểm âm hoặc chính sách hiệu chỉnh khác. Thuộc tính kiểm thử phải tương ứng với ngữ nghĩa chính sách đã công bố.

Kiểm thử concurrency bằng các điểm đồng bộ có kiểm soát: cho nhiều request cùng chờ trước bước đăng ký attempt hoặc tiêu thụ quyết định, sau đó xác nhận số lượng thay đổi thành công và trạng thái cuối.

## 11. Giải thích quyết định, quan sát vận hành và phản hồi

### 11.1. Giữ bằng chứng nội bộ đủ để giải thích

Một decision trace có thể trả lời:

- Bộ rule nào đã được chọn và vì sao?
- Rule nào match, không match, không áp dụng hoặc không đánh giá được?
- Feature đã dùng có nguồn, chất lượng và thời điểm nào?
- Điểm được cộng từ đâu, hiệu ứng trực tiếp nào chi phối?
- Fallback nào được kích hoạt?
- Quyết định có còn đúng scope và thời hạn khi thực thi không?

Ghi ID, version và reason code theo cấu trúc. Giới hạn việc lưu dữ liệu cá nhân, dữ liệu phương thức thanh toán, bí mật và nội dung thô không cần thiết.

Thông báo cho người dùng nên hỗ trợ bước tiếp theo hợp lệ, ví dụ cần xác minh bổ sung hoặc giao dịch đang chờ xem xét. Không cần trả nguyên ngưỡng nội bộ và toàn bộ feature cho client; khả năng giải thích chi tiết thuộc các công cụ có quyền thích hợp.

Ẩn ngưỡng không thay thế thiết kế an toàn. Hệ thống vẫn phải giữ bất biến nếu kẻ lạm dụng đoán được một phần rule hoặc thử nhiều yêu cầu.

### 11.2. Theo dõi cả chất lượng phát hiện và độ tin cậy của engine

Các nhóm chỉ số hữu ích:

| Nhóm | Ví dụ |
| --- | --- |
| Phân bố quyết định | Tỷ lệ ALLOW, CHALLENGE, REVIEW, DENY theo action và bundle |
| Chất lượng đánh giá | Missing, stale, timeout, coverage thiếu, lỗi kiểu |
| Hiệu năng | Độ trễ lấy feature, đánh giá, hàng đợi và cổng thực thi |
| Hiệu lực thực thi | Decision hết hạn, sai scope, sai object version, dùng lại |
| Vận hành review | Độ dài hàng chờ, thời gian xử lý, kết quả bị thay đổi sau xem xét |
| Kết quả thực tế | Gian lận được xác nhận, giao dịch hợp lệ bị cản, kết quả khiếu nại |

Không đưa ID khách hàng, email hoặc phương thức thanh toán vào metric label không giới hạn.

Tỷ lệ chặn cao không tự chứng minh hệ thống tốt hơn. Cần đối chiếu với kết quả đáng tin cậy và độ trễ nhãn. Những trường hợp đang review hoặc chưa có kết luận không nên bị ép thành nhãn “gian lận” chỉ để tính chỉ số.

Nếu tính precision và recall, cần xác định tập kết quả và khoảng thời gian quan sát:

~~~text
precision = truePositive / (truePositive + falsePositive)
recall    = truePositive / (truePositive + falseNegative)
~~~

Các chỉ số này không đáng tin nếu nhãn chỉ tồn tại ở nhóm đã bị chặn, còn nhóm ALLOW không được theo dõi tương ứng. Việc so sánh rule cần tính đến cách chọn mẫu và độ trễ phản hồi.

### 11.3. Phân biệt lỗi chính sách với lỗi thực thi

Ví dụ:

- Rule đúng nhưng feature bị trễ: lỗi chất lượng dữ liệu hoặc contract.
- Quyết định REVIEW đúng nhưng backend vẫn cấp khóa học: lỗi thực thi workflow.
- Bundle đúng nhưng một node vẫn dùng bản cũ ngoài chính sách: lỗi phát hành hoặc cache.
- Cả pipeline hoạt động đúng nhưng nhiều giao dịch hợp lệ bị challenge: cần xem lại chính sách và dữ liệu.
- Quyết định ALLOW bị dùng cho payload mới: lỗi binding, không phải thiếu thêm một rule rủi ro.

Phân loại đúng giúp sửa nguyên nhân. Thêm điểm cho mọi tài khoản có thể làm tăng cản trở mà không giải quyết một endpoint bỏ qua kiểm tra.

## 12. Những câu hỏi cần chốt cho một hệ thống đánh giá rule

Trước khi đưa vào sử dụng, cần có câu trả lời cụ thể cho các điểm sau:

1. Bất biến nào luôn bắt buộc và không nằm trong cơ chế bù điểm?
2. Feature đến từ đâu, có độ mới bao nhiêu và thiếu dữ liệu sẽ xử lý thế nào?
3. Bộ rule nào áp dụng cho mỗi tenant và hành động?
4. Ngữ nghĩa hợp nhất là gì; rule thuận lợi có thể tác động tới rule chặn nào?
5. Quyết định gắn với snapshot, version, nghĩa vụ và thời hạn như thế nào?
6. Cổng thực thi nào ngăn bỏ qua review, challenge, thu hồi và idempotency?
7. Bộ đếm, retry và các request đồng thời được phối hợp ở đâu?
8. Có thể replay và giải thích một quyết định mà không tạo side effect không?

Một rule khớp đúng điều kiện mới chỉ là một phần của hệ thống. Khả năng bảo vệ nghiệp vụ phụ thuộc vào dữ liệu có thẩm quyền, ngữ nghĩa đánh giá nhất quán và việc cưỡng chế đúng quyết định tại nơi tạo ra thay đổi.
