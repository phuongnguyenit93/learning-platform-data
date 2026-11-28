# Audit quyết định phê duyệt trong PAM

## Mục tiêu bài học

Audit quyết định phê duyệt trong Privileged Access Management (PAM) là việc kiểm tra có hệ thống xem quyền đặc biệt đã được chấp thuận, kích hoạt và sử dụng theo đúng chính sách hay chưa, dựa trên bằng chứng có thể đối chiếu.

Một dòng “APPROVED” chưa đủ để kết luận quy trình hoạt động đúng. Cần biết ai quyết định, người đó có thẩm quyền lúc quyết định hay không, họ duyệt nội dung nào, quyết định còn giá trị khi cấp quyền không và quyền thực tế có nằm trong phạm vi đó không.

Sau bài học, bạn có thể:

- Thiết kế chuỗi bằng chứng cho một quyết định phê duyệt quyền đặc biệt.
- Đối chiếu yêu cầu, thẩm quyền, quyết định, grant, phiên và thu hồi.
- Phân biệt tính đầy đủ của hồ sơ với sự tuân thủ thực tế của quy trình.
- Kiểm tra toàn bộ quần thể bằng dữ liệu và chọn mẫu để đánh giá nội dung quyết định.
- Ghi nhận phát hiện, giới hạn bằng chứng và việc khắc phục mà không viết lại lịch sử.

Tên bảng, cấu trúc dữ liệu, mã yêu cầu và tình huống trong bài chỉ là minh họa. Không có yêu cầu về thời hạn lưu hoặc số lượng mẫu nào trong bài được mặc định áp dụng cho mọi tổ chức.

## 1. Audit phải trả lời điều gì?

Giả sử một kỹ sư được cấp quyền quản trị máy chủ sản xuất trong một giờ. Hệ thống workflow báo yêu cầu “đã duyệt”, nhưng khi kiểm tra có thể phát hiện:

- Người duyệt chỉ có thẩm quyền với môi trường thử nghiệm.
- Người dùng đã đổi yêu cầu sau phê duyệt từ đọc log thành quản trị.
- Grant được kích hoạt trước khi đủ các quyết định bắt buộc.
- Quyền vẫn còn sau khi cửa sổ được duyệt kết thúc.
- Không tìm thấy bằng chứng cho biết ai thực sự sử dụng tài khoản đặc quyền.

Một cuộc audit cần đánh giá cả **quyết định** và **mối liên hệ của quyết định với việc thực thi**.

| Câu hỏi audit | Bằng chứng cần đối chiếu |
|---|---|
| Nhu cầu có được mô tả đủ không? | Yêu cầu, mục đích, ticket và phạm vi công việc |
| Ai thực sự quyết định? | Định danh người duyệt, sự kiện xác thực hoặc tham chiếu phiên quyết định |
| Người đó có thẩm quyền khi quyết định không? | Quan hệ vai trò, chủ sở hữu, ủy quyền và thời hạn có hiệu lực trong quá khứ |
| Quyết định áp dụng cho nội dung nào? | Phiên bản yêu cầu, bản chụp tài sản, quyền, thời gian và điều kiện |
| Đã đủ các bước kiểm soát chưa? | Chính sách áp dụng, các quyết định và quy tắc phân tách nhiệm vụ |
| Quyền được cấp đúng không? | Grant, tài khoản đích, vai trò thực tế, thời điểm và kết quả thực thi |
| Quyền có được sử dụng và kết thúc đúng không? | Phiên PAM, log đích, sự kiện hết hạn hoặc thu hồi |
| Có thể tin cậy và tái dựng bằng chứng không? | Nguồn log, bảo vệ toàn vẹn, độ bao phủ và cách trích xuất |

Không tìm thấy vi phạm trong một mẫu không đồng nghĩa toàn bộ quần thể không có vi phạm. Tương tự, một bản ghi đầy đủ trường dữ liệu không tự chứng minh quyết định đúng về nội dung.

## 2. Xác định tiêu chí trước khi kiểm tra

Audit cần có tiêu chí cụ thể: phiên bản chính sách nào áp dụng cho loại quyền, tài sản, thời điểm và đối tượng đang xét.

Ví dụ tiêu chí của một tổ chức có thể là:

> Quyền khởi động lại dịch vụ sản xuất cần quản lý xác nhận nhu cầu và chủ sở hữu dịch vụ chấp thuận phạm vi trước khi kích hoạt. Người hưởng quyền không được tự duyệt. Phê duyệt gắn với một phiên bản yêu cầu và chỉ dùng trong cửa sổ đã xác định.

Từ tiêu chí đó có thể thiết kế phép kiểm tra. Không nên thu thập log rồi suy ngược ra một quy tắc chỉ vì quy tắc đó phù hợp với dữ liệu đang có.

### 2.1. Các chiều đánh giá

- **Thiết kế:** quy tắc có đủ để kiểm soát rủi ro cần giải quyết không?
- **Thực thi:** hệ thống và người dùng có làm đúng quy tắc trong các trường hợp được kiểm tra không?
- **Bằng chứng:** dữ liệu có đủ, đúng nguồn và đủ tin cậy để hỗ trợ kết luận không?

Nếu chính sách yêu cầu người thứ hai độc lập nhưng hệ thống cho cùng một cá nhân dùng hai vai trò để duyệt, đó là vấn đề thực thi hoặc thiết kế cấu hình tùy tình huống.

Nếu không lưu được định danh người duyệt, có thể chưa đủ bằng chứng để xác nhận việc phân tách nhiệm vụ. Không nên chuyển sự thiếu bằng chứng thành một kết luận chắc chắn rằng người dùng đã tự phê duyệt; cần mô tả đúng điều quan sát được.

### 2.2. Phân biệt các đối tượng kiểm soát

| Đối tượng | Nội dung được đánh giá |
|---|---|
| Yêu cầu | Người hưởng quyền, nhu cầu, tài sản, vai trò, thời gian |
| Quyết định phê duyệt | Người quyết định, thẩm quyền, kết quả, phạm vi và điều kiện |
| Grant | Quyền thực tế đã cấp, đích, thời điểm bắt đầu và kết thúc |
| Phiên sử dụng | Người điều khiển, tài khoản thực thi, thao tác và dữ liệu liên quan |
| Thu hồi | Kết quả gỡ quyền, chấm dứt phiên và xử lý credential cần thiết |

Đã có quyết định hợp lệ không chứng minh grant đã được cấp đúng. Grant có thời hạn cũng không chứng minh phiên cũ hoặc token liên quan đã bị vô hiệu hóa khi quyền kết thúc.

## 3. Chuỗi bằng chứng và khóa tương quan

Một chuỗi tham khảo:

```text
Chính sách áp dụng + nguồn thẩm quyền theo thời gian
                         |
                         v
Yêu cầu phiên bản N -> Các quyết định -> Lần kích hoạt
                                              |
                                              v
                                      Grant tại hệ thống đích
                                              |
                                              v
                                      Phiên / sử dụng quyền
                                              |
                                              v
                                      Hết hạn / thu hồi
```

Mỗi quan hệ cần một cách tương quan đáng tin cậy. Chỉ ghép theo tên hiển thị và thời gian gần nhau dễ ghép nhầm khi nhiều yêu cầu cùng tồn tại.

Các định danh hữu ích:

- Mã yêu cầu và số phiên bản.
- Định danh ổn định của người tạo, người hưởng quyền và người duyệt.
- Mã quyết định và mã ủy quyền nếu có.
- Mã chính sách hoặc phiên bản chính sách được áp dụng.
- Mã lần kích hoạt, grant, phiên PAM, tài sản và tài khoản đích.
- Mã sự kiện nguồn và nguồn phát sinh sự kiện.

Một yêu cầu có thể tạo nhiều grant hoặc nhiều phiên nếu chính sách cho phép. Ngược lại, một grant có thể cần nhiều quyết định. Thiết kế dữ liệu phải biểu diễn được quan hệ này; không giả định lúc nào cũng một yêu cầu, một quyết định, một phiên.

### 3.1. Định danh con người và tài khoản kỹ thuật

Nếu nhiều người dùng chung tài khoản đích, log đích chỉ ghi tài khoản đó chưa đủ để xác định người điều khiển. Cần liên kết với danh tính cá nhân tại PAM và mã phiên.

Nếu các phiên đồng thời không thể phân biệt trên nguồn log liên quan, hồ sơ audit phải ghi giới hạn quy trách nhiệm này. Không đưa ra kết luận vượt quá độ phân giải của bằng chứng.

### 3.2. Mẫu dữ liệu quyết định

```yaml
decision:
  decision_id: DEC-514
  request_id: REQ-208
  request_version: 2
  beneficiary_id: user-041
  approver_id: user-008
  approval_role: asset_owner
  authority_reference: AUTH-92
  outcome: APPROVED
  decided_at: "2026-12-04T18:00:00+07:00"
  activation_valid_until: "2026-12-04T20:15:00+07:00"
  approved_scope:
    assets:
      - app-prod-02
    privilege_profile: service-restart-limited
    purpose_ticket: CHG-622
    access_starts_at: "2026-12-04T20:00:00+07:00"
    access_ends_at: "2026-12-04T21:00:00+07:00"
  policy_version: PAM-PROD-EXAMPLE-v3
  authentication_event_reference: AUTHN-310
```

Mẫu trên mô tả một quyết định, không khẳng định rằng quyết định này đã đủ cho toàn bộ quy trình. Nếu chính sách còn yêu cầu quản lý trực tiếp, cần có bằng chứng riêng cho bước đó.

Không lưu bí mật xác thực, mật khẩu, token hoặc khóa riêng vào hồ sơ quyết định. Tham chiếu đến một sự kiện xác thực được bảo vệ phù hợp thường hữu ích hơn việc sao chép dữ liệu nhạy cảm.

## 4. Kiểm tra thẩm quyền tại đúng thời điểm

Một lỗi phổ biến là lấy danh sách quản lý hoặc chủ sở hữu hiện tại để đánh giá tất cả quyết định trong quá khứ.

Ví dụ:

- Ngày 4, An là chủ sở hữu dịch vụ và có quyền duyệt.
- Ngày 10, Bình tiếp nhận vai trò.
- Ngày 20, audit một quyết định do An đưa ra ngày 4.

Danh sách hiện tại chỉ có Bình không chứng minh quyết định của An không hợp lệ. Cần dữ liệu hoặc bằng chứng về khoảng thời gian An có thẩm quyền.

Ngược lại, việc An hiện đang có quyền duyệt cũng không chứng minh An đã có quyền đó vào ngày 4.

### 4.1. Các câu hỏi về thẩm quyền

1. Vai trò phê duyệt được lấy từ nguồn nào có trách nhiệm quản trị?
2. Quan hệ hoặc vai trò có hiệu lực khi quyết định không?
3. Thẩm quyền có bao phủ tài sản, đơn vị, loại quyền và mức rủi ro đang xét không?
4. Người quyết định có còn đủ điều kiện theo chính sách tại thời điểm liên quan không?
5. Có tự phê duyệt, xung đột nhiệm vụ hoặc nhiều vai trò do cùng một người thực hiện không?

Nếu có ủy quyền, cần kiểm tra người giao quyền có quyền ủy quyền, phạm vi được ủy quyền, thời hạn và giới hạn ủy quyền tiếp nếu có.

Tên “delegate” trong log không đủ. Cần biết người thực sự ra quyết định là ai và căn cứ nào cho phép họ làm điều đó.

### 4.2. Thẩm quyền khi quyết định và điều kiện khi kích hoạt

Một người có thể phê duyệt hợp lệ hôm trước nhưng đến lúc kích hoạt, nhân sự hưởng quyền đã bị khóa hoặc yêu cầu đã bị hủy.

Audit phải kiểm tra quy tắc tại cả hai thời điểm. Một thay đổi nhân sự không nhất thiết làm mọi quyết định quá khứ sai; tuy nhiên, việc cấp mới phải tuân theo điều kiện hiện hành mà chính sách yêu cầu.

## 5. Kiểm tra phạm vi, phiên bản và thời hạn

### 5.1. So sánh nội dung được duyệt với quyền được cấp

Cần đối chiếu ít nhất người hưởng quyền, tài sản, môi trường, quyền, mục đích và thời gian. Mối quan hệ đúng thường là quyền thực tế không vượt phạm vi được duyệt và vẫn đáp ứng các điều kiện bắt buộc.

Không chỉ so sánh tên vai trò. Một vai trò giữ nguyên tên nhưng được thêm quyền phía sau có thể làm thay đổi tác động. Khi cần, phải có phiên bản hoặc bản chụp ánh xạ quyền để giải thích vai trò có nghĩa gì ở thời điểm cấp.

Với các tập tài sản hoặc hành động, kiểm tra quyền thực tế có nằm trong phạm vi cho phép. Tuy nhiên, một tập quyền nhỏ hơn chưa chắc tuân thủ mọi điều kiện: chẳng hạn vẫn có thể vi phạm yêu cầu dùng đúng gateway, đúng tài khoản hay đúng mục đích.

### 5.2. Yêu cầu thay đổi sau khi duyệt

Phê duyệt phải gắn với bản mà người duyệt đã xem. Khi đổi người hưởng quyền, tài sản, quyền hoặc thời gian, audit cần xác định thay đổi có yêu cầu tái phê duyệt theo chính sách hay không và cơ chế đó đã chạy chưa.

Bản chụp nội dung và mã phiên bản giúp kiểm tra. Mã băm có thể hỗ trợ phát hiện nội dung không khớp nếu được tạo từ dữ liệu chuẩn hóa và được bảo vệ phù hợp.

Mã băm đơn lẻ không chứng minh ai đã phê duyệt. Nếu một người có thể sửa cả dữ liệu và mã băm mà không bị phát hiện, kiểm soát toàn vẹn vẫn thiếu.

### 5.3. Kiểm tra thứ tự thời gian

Cần phân biệt:

- Thời điểm sự kiện xảy ra tại nguồn.
- Thời điểm log được thu nhận.
- Khoảng thời gian quyết định hoặc thẩm quyền có hiệu lực.

Một quyết định được thu nhận lúc 20:05 có thể đã xảy ra lúc 19:55. Không dùng thời gian nhận log thay thời gian ra quyết định mà không đánh giá độ tin cậy của nguồn và đồng hồ.

Các phép kiểm tra thường gồm:

- Các quyết định bắt buộc đã có trước khi quyền thực tế có hiệu lực.
- Lần kích hoạt không xảy ra sau hạn sử dụng quyết định.
- Quyền không bắt đầu trước hoặc kết thúc sau giới hạn được phép.
- Quyết định chưa bị hủy hoặc thu hồi tại thời điểm được sử dụng.
- Quy tắc dùng một lần, số lần hoặc số phiên đồng thời được tuân thủ.

Không đồng nhất hạn được phép kích hoạt với thời điểm kết thúc grant. Chẳng hạn, một quyết định cho phép bắt đầu trước 20:15 và quyền kết thúc trước 21:00 có thể tạo grant hợp lệ lúc 20:10 đến 20:50.

Cũng cần xác định rõ biên thời gian là bao gồm hay loại trừ, múi giờ và độ chính xác thời gian. Nếu đồng hồ lệch hoặc độ phân giải quá thấp khiến không xác định được thứ tự, ghi giới hạn bằng chứng và tìm nguồn bổ sung; không kết luận chắc chắn chỉ từ những mốc không đủ tin cậy.

### 5.4. Phê duyệt sau sự kiện

Nếu grant có hiệu lực trước quyết định bắt buộc, quyết định được bổ sung sau đó không làm thay đổi thứ tự đã xảy ra.

Có thể đây là đường khẩn cấp hợp lệ nếu chính sách đã định nghĩa điều kiện khác và có bằng chứng đáp ứng. Nếu không, cần ghi nhận sai lệch với tiêu chí áp dụng.

Rà soát sau sự cố giúp đánh giá và khắc phục. Nó không được trình bày như phê duyệt trước sự kiện.

## 6. Bảo đảm quần thể audit đầy đủ

Nếu chỉ lấy các yêu cầu có trạng thái “APPROVED” từ workflow, bạn có thể bỏ sót quyền được cấp trực tiếp hoặc yêu cầu bị hủy nhưng grant vẫn còn.

Cần xác định quần thể theo mục tiêu kiểm tra. Ví dụ, để kiểm tra mọi lần cấp quyền sản xuất trong tháng, nguồn bắt đầu nên bao gồm sự kiện cấp quyền thực tế từ những hệ thống nằm trong phạm vi, sau đó đối chiếu ngược về yêu cầu và quyết định.

### 6.1. Đối soát nhiều chiều

| Hướng đối soát | Điều có thể phát hiện |
|---|---|
| Grant thực tế → yêu cầu và quyết định | Quyền không có hồ sơ, liên kết sai hoặc thiếu phê duyệt |
| Quyết định → lần kích hoạt và grant | Phê duyệt không dùng, dùng lặp hoặc cấp sai phạm vi |
| Phiên PAM/log đích → grant | Sử dụng quyền không khớp grant hoặc đi đường khác |
| Sự kiện thu hồi → trạng thái đích | Ghi nhận thu hồi nhưng quyền hoặc phiên vẫn tồn tại |
| Yêu cầu bị hủy/hết hạn → grant sau đó | Tác vụ bất đồng bộ cấp quyền từ trạng thái cũ |

Không có grant tương ứng với một quyết định chấp thuận chưa chắc là vi phạm. Người dùng có thể không kích hoạt quyền, hoặc việc cấp thất bại. Cần phân loại thay vì mặc định mọi lệch số lượng đều sai.

### 6.2. Kiểm tra nguồn dữ liệu

Trước khi phân tích, xác nhận:

- Những hệ thống, loại tài khoản và loại quyền nào được bao phủ.
- Khoảng thời gian, bộ lọc, phân trang và múi giờ khi trích xuất.
- Có khoảng mất log, độ trễ hoặc thay đổi tích hợp không.
- Dữ liệu có bị gộp, trùng hoặc mất quan hệ một-nhiều không.
- Các đường khẩn cấp, thay đổi thủ công và quyền thường trực có nằm trong phạm vi không.
- Có bằng chứng đủ để biết việc thu thập hoạt động liên tục hay không.

Đối chiếu số lượng theo nguồn và thời gian giúp phát hiện khoảng trống. Nhưng số lượng bằng nhau không chứng minh từng bản ghi đều đúng; một bản ghi thiếu và một bản ghi trùng có thể triệt tiêu về tổng.

Tương tự, kiểm tra trạng thái nhóm quyền hiện tại không tái dựng được toàn bộ quyền ngắn hạn trong quá khứ. Cần log thay đổi, lịch sử grant hoặc nguồn tương đương.

### 6.3. Chọn mẫu sau khi biết quần thể

Có thể kết hợp kiểm tra dữ liệu toàn bộ quần thể với mẫu đánh giá sâu:

- Kiểm tra tự động các liên kết, thời hạn, trùng lặp và trạng thái có thể diễn đạt thành quy tắc.
- Chọn mẫu rủi ro cao: quyền rộng, sản xuất, checkout bí mật, ủy quyền, khẩn cấp hoặc thay đổi sau phê duyệt.
- Chọn thêm mẫu theo phương pháp đã xác định để không chỉ nhìn các trường hợp vốn đã có cảnh báo.
- Đọc nội dung nhu cầu, căn cứ quyết định và bằng chứng thực thi của từng mẫu.

Ghi lại cách chọn, kích thước mẫu, trường hợp loại trừ và giới hạn suy rộng. Không đưa ra tỷ lệ vi phạm cho toàn hệ thống từ một tập mẫu được chọn có chủ đích mà không giải thích phương pháp.

## 7. Ví dụ truy vấn phục vụ sàng lọc

Các truy vấn dưới đây là SQL minh họa trên dữ liệu audit đã được phép đọc. Tên bảng không đại diện cho schema thật và cần được ánh xạ trước khi sử dụng. Chúng tạo danh sách cần điều tra, không tự đủ để chứng nhận một lần cấp quyền là hợp lệ.

Giả sử có:

- `grant_event`: các lần quyền thực tế có hiệu lực.
- `approval_decision`: quyết định, yêu cầu và phiên bản được duyệt.
- `grant_decision_link`: quan hệ giữa grant và các quyết định được viện dẫn.

### 7.1. Grant không có liên kết quyết định

```sql
SELECT
    g.grant_id,
    g.request_id,
    g.beneficiary_id,
    g.asset_id,
    g.effective_at
FROM grant_event AS g
WHERE NOT EXISTS (
    SELECT 1
    FROM grant_decision_link AS l
    WHERE l.grant_id = g.grant_id
);
```

Kết quả có thể là thiếu hồ sơ, lỗi tương quan hoặc một đường truy cập ngoại lệ. Cần đối chiếu nguồn và chính sách trước khi kết luận.

Grant có một liên kết không có nghĩa là đủ các bước phê duyệt; truy vấn chỉ trả lời câu hỏi có liên kết hay không.

### 7.2. Liên kết không khớp phiên bản hoặc quyết định đến sau grant

```sql
SELECT
    g.grant_id,
    g.request_id,
    g.request_version,
    d.decision_id,
    d.request_id AS decision_request_id,
    d.request_version AS decision_request_version,
    d.outcome,
    d.decided_at,
    g.effective_at
FROM grant_event AS g
JOIN grant_decision_link AS l
    ON l.grant_id = g.grant_id
LEFT JOIN approval_decision AS d
    ON d.decision_id = l.decision_id
WHERE
    d.decision_id IS NULL
    OR d.request_id IS NULL
    OR d.request_version IS NULL
    OR g.request_id IS NULL
    OR g.request_version IS NULL
    OR d.request_id <> g.request_id
    OR d.request_version <> g.request_version
    OR d.outcome IS NULL
    OR d.outcome <> 'APPROVED'
    OR d.decided_at IS NULL
    OR g.effective_at IS NULL
    OR d.decided_at > g.effective_at;
```

Các giá trị thiếu được đưa ra kiểm tra thay vì bị SQL bỏ qua do logic `NULL`. Cần đánh giá thêm độ tin cậy của thời gian, chính sách khẩn cấp, trạng thái thu hồi và nội dung phạm vi.

Một grant không xuất hiện trong kết quả vẫn có thể sai vì người duyệt không có thẩm quyền, thiếu một vai trò bắt buộc hoặc quyền thực tế quá rộng.

### 7.3. Kiểm tra logic phê duyệt bắt buộc

Sau sàng lọc, cần đánh giá theo loại yêu cầu:

```text
Với từng grant:
  1. Xác định chính sách và phạm vi áp dụng.
  2. Lấy tất cả quyết định liên quan đúng phiên bản yêu cầu.
  3. Kiểm tra danh tính, thẩm quyền và điều kiện của từng quyết định.
  4. Kiểm tra các vai trò bắt buộc và tính độc lập theo chính sách.
  5. So sánh thời hạn, phạm vi và trạng thái tại lúc kích hoạt.
  6. Đối chiếu quyền thực tế, phiên sử dụng và kết quả thu hồi.
  7. Ghi kết quả cùng bằng chứng hoặc giới hạn chưa xác minh.
```

Đếm hai dòng “APPROVED” không tương đương hai người độc lập. Hai dòng có thể là sự kiện gửi lại, cùng người với hai vai trò, hoặc quyết định cho hai phiên bản khác nhau.

## 8. Bảo vệ tính toàn vẹn và khả năng sử dụng của bằng chứng

### 8.1. Tách quyền thao tác và quyền sửa lịch sử

Người hưởng quyền, người duyệt và người vận hành workflow không nên có khả năng tùy ý sửa hoặc xóa bằng chứng liên quan mà không để lại dấu vết.

Tùy môi trường, có thể sử dụng:

- Nhật ký theo mô hình ghi thêm, với thay đổi được ghi thành sự kiện mới.
- Kho lưu độc lập, quyền quản trị tách biệt và thời hạn giữ dữ liệu được kiểm soát.
- Bảo vệ toàn vẹn hoặc chữ ký cho tập bằng chứng khi phù hợp.
- Ghi nhận việc đọc, xuất, thay đổi cấu hình lưu và yêu cầu xóa.
- Sao lưu và thử khả năng phục hồi bằng chứng.

Không gọi một log là “bất biến” chỉ vì ứng dụng không cung cấp nút sửa. Cần xem quyền của quản trị viên kho lưu, tài khoản dịch vụ và cơ chế xóa dữ liệu bên dưới.

### 8.2. Hiểu giới hạn của chuỗi băm và chữ ký

Chuỗi băm có thể giúp phát hiện một số thay đổi trong một chuỗi sự kiện, nhất là khi có mốc kiểm chứng được giữ độc lập. Nó không tự ngăn việc xóa cả chuỗi hoặc viết lại chuỗi nếu người tấn công kiểm soát cả dữ liệu và các mốc đối chiếu.

Chữ ký số hỗ trợ kiểm tra nội dung có được ký bằng khóa tương ứng và có bị thay đổi sau khi ký hay không. Nó không tự chứng minh người phê duyệt hiểu yêu cầu, có thẩm quyền hoặc rằng dữ liệu nguồn đầy đủ.

Cần quản lý khóa, phân quyền và bảo vệ nguồn thu thập tương xứng với mục tiêu. Không dùng một cơ chế mật mã để thay thế kiểm tra logic phê duyệt.

### 8.3. Gói bằng chứng cho một cuộc audit

Một gói bằng chứng có thể gồm bản trích xuất, mô tả nguồn, khoảng thời gian, bộ lọc, thời điểm xuất, người xuất, mã băm tệp và danh mục các hiện vật.

Mã băm tệp giúp đối chiếu các bản sao. Tính đầy đủ và nguồn gốc vẫn phải dựa trên quy trình trích xuất và kiểm soát nguồn.

Khi chuyển giao, ghi nhận người nhận và cách bảo vệ dữ liệu. Chỉ đưa những thông tin cần thiết; bản ghi phiên hoặc lý do truy cập có thể chứa dữ liệu nhạy cảm.

Thời hạn giữ, xử lý hồ sơ cần bảo toàn và việc xóa sau hạn phải theo yêu cầu áp dụng của tổ chức. Không đặt một thời hạn chung chỉ vì đó là giá trị mặc định của công cụ.

## 9. Tình huống thực hành: ba quyết định “đã duyệt”

### 9.1. Tiêu chí của tình huống

Với quyền khởi động lại dịch vụ sản xuất, chính sách minh họa yêu cầu:

- Quản lý xác nhận nhu cầu và chủ sở hữu dịch vụ duyệt phạm vi.
- Hai người duyệt độc lập với người hưởng quyền và với nhau.
- Các quyết định gắn đúng phiên bản yêu cầu.
- Chỉ kích hoạt sau khi đủ quyết định, trong cửa sổ được phép.
- Quyền được gỡ khi công việc kết thúc hoặc hết hạn theo quy định.

### 9.2. Các hồ sơ được chọn

| Hồ sơ | Dữ liệu quan sát | Hướng kết luận |
|---|---|---|
| REQ-208 | Đủ hai người có thẩm quyền, đúng phiên bản 2; grant đọc log thay vì quyền khởi động lại đã đề nghị sau khi phạm vi được duyệt lại; kết thúc đúng hạn | Kiểm tra sự nhất quán của phiên bản và ánh xạ quyền trước khi xác nhận đạt |
| REQ-209 | Quản lý duyệt phiên bản 1 đọc log; phiên bản 2 đổi sang quản trị; grant quản trị viện dẫn quyết định phiên bản 1 | Sai lệch liên kết quyết định với phạm vi được cấp |
| REQ-210 | Grant có hiệu lực 20:00; quyết định chủ sở hữu xảy ra 20:07; không có bằng chứng đường khẩn cấp áp dụng | Quyền có hiệu lực trước khi đủ phê duyệt theo tiêu chí tình huống |

Trạng thái cuối của cả ba yêu cầu có thể đều là “APPROVED”. Trạng thái đó không phân biệt được các trường hợp trên.

### 9.3. Điều tra REQ-209

Các bước đối chiếu:

1. Lấy bản chụp phiên bản 1 và phiên bản 2.
2. Xác nhận người quản lý đã quyết định trên phiên bản 1.
3. Xác nhận thay đổi quyền và người thực hiện thay đổi.
4. Đối chiếu quyết định chủ sở hữu, kết quả workflow và grant thực tế.
5. Kiểm tra vai trò quản trị có thực sự được cấp và đã được sử dụng hay chưa.
6. Xác định khi nào quyền kết thúc và có còn quyền tồn dư không.

Nếu grant thực tế đúng là quản trị nhưng quyết định chỉ bao phủ đọc log, phát hiện không nên viết mơ hồ “log chưa đẹp”. Cần mô tả quyền nào vượt phạm vi, thời gian tồn tại, tiêu chí bị vi phạm và bằng chứng liên quan.

Nếu chưa có log máy đích để xác nhận thao tác, ghi rõ chưa đủ bằng chứng kết luận hành động đã xảy ra. Việc quyền tồn tại ngoài phê duyệt và việc quyền được sử dụng là hai phát hiện có thể cần đánh giá riêng.

### 9.4. Điều tra REQ-210

Trước khi kết luận, kiểm tra:

- 20:00 và 20:07 là thời điểm sự kiện hay thời điểm thu nhận?
- Đồng hồ và múi giờ có đủ tin cậy không?
- Có quyết định khác còn hiệu lực bị thiếu liên kết không?
- Có đường khẩn cấp đã được kích hoạt hợp lệ không?
- Grant có hiệu lực thật lúc 20:00 hay chỉ mới tạo một tác vụ chờ?

Nếu xác nhận grant có hiệu lực trước quyết định bắt buộc và không có ngoại lệ hợp lệ, ghi nhận sai lệch. Việc chủ sở hữu duyệt lúc 20:07 không xóa khoảng truy cập trước đó.

## 10. Ghi phát hiện và theo dõi khắc phục

Một phát hiện nên cho người đọc biết tiêu chí, điều quan sát được, bằng chứng, tác động và việc cần xử lý.

Ví dụ:

```text
Mã phát hiện: AUD-PAM-014

Tiêu chí:
  Quyền sản xuất phải được cấp từ các quyết định hợp lệ
  cho đúng phiên bản yêu cầu.

Điều quan sát:
  Grant G-209 cấp vai trò quản trị cho phiên bản 2 của REQ-209,
  nhưng quyết định quản lý DEC-511 chỉ bao phủ phiên bản 1 đọc log.

Bằng chứng:
  Bản chụp hai phiên bản, DEC-511, liên kết grant,
  sự kiện cấp quyền tại đích và mốc thu hồi.

Phạm vi đã xác minh:
  Một grant trong mẫu điều tra; chưa kết luận tỷ lệ trên toàn quần thể.

Tác động:
  Quyền thực tế vượt phạm vi đã được người quản lý chấp thuận.

Khắc phục:
  Xử lý quyền tồn dư nếu có; ràng buộc quyết định với phiên bản;
  kiểm tra lại tại lúc kích hoạt; đối soát các grant cùng cơ chế lỗi.

Chủ sở hữu và thời hạn:
  Do tổ chức phân công và ghi nhận trong hồ sơ theo dõi.
```

Nguyên nhân có thể nằm ở thiết kế, cấu hình, tích hợp hoặc quy trình con người. Không mặc định quy kết một cá nhân cố tình vi phạm khi dữ liệu mới chỉ cho thấy một liên kết sai.

### 10.1. Xử lý quyền đang gây rủi ro

Nếu audit phát hiện quyền đặc biệt ngoài phê duyệt đang hoạt động, cần chuyển ngay cho vai trò có thẩm quyền xử lý theo quy trình. Không chờ hoàn thành báo cáo tổng hợp mới phản ánh.

Việc bảo toàn bằng chứng phải phối hợp với thu hồi phù hợp. Không giữ một quyền ngoài kiểm soát tiếp tục tồn tại chỉ để chờ thu thập thêm một cách không cần thiết.

### 10.2. Khắc phục mà không viết lại lịch sử

Bổ sung chú thích hoặc bằng chứng phát hiện sau đó phải có thời điểm, người bổ sung và liên kết tới bản ghi gốc. Không sửa thời điểm phê duyệt để làm cho nó xuất hiện trước grant.

Sau khi sửa cơ chế, kiểm tra cả trường hợp thành công và trường hợp phải bị chặn: thay phiên bản, tự phê duyệt, hết hạn, sự kiện trùng hoặc yêu cầu đã hủy.

Đóng phát hiện khi có bằng chứng rằng thay đổi khắc phục đã được thực thi và kiểm chứng trong phạm vi phù hợp. Việc tạo một ticket sửa lỗi chưa đủ để xác nhận kiểm soát đã hoạt động.

## 11. Sai lầm thường gặp

**Chỉ xuất danh sách quyết định chấp thuận.** Cách này bỏ sót quyền cấp ngoài workflow. Cần bắt đầu thêm từ nguồn grant và sử dụng thực tế.

**Dùng danh sách quản lý hiện tại cho quá khứ.** Cần căn cứ thẩm quyền có hiệu lực tại thời điểm quyết định.

**Đếm số lần bấm duyệt thay số người độc lập.** Sự kiện trùng hoặc một người giữ nhiều vai trò có thể tạo cảm giác đủ số bước.

**So sánh tên quyền mà không biết ánh xạ.** Vai trò có thể thay đổi nội dung theo thời gian hoặc không tương đương giữa các hệ thống.

**Coi có mã băm là bằng chứng toàn vẹn hoàn chỉnh.** Cần nguồn gốc, mốc đối chiếu, kiểm soát người quản trị và độ đầy đủ.

**Gắn mọi khoảng trống log thành hành vi vi phạm chắc chắn.** Phân biệt sai lệch đã chứng minh với kết luận chưa thể xác minh do thiếu bằng chứng.

**Gọi phê duyệt sau sự kiện là phê duyệt trước.** Cần giữ đúng trình tự và đánh giá đường ngoại lệ nếu có.

**Đóng phát hiện sau khi cập nhật tài liệu.** Cần kiểm chứng hành vi thực tế của cơ chế đã sửa.

## 12. Tự kiểm tra

1. Vì sao một bảng gồm mã yêu cầu và trạng thái “APPROVED” chưa đủ để audit?
2. Khi kiểm tra quyết định tháng trước, cần dùng danh sách chủ sở hữu hiện tại hay bằng chứng lịch sử?
3. Grant không có liên kết quyết định chắc chắn là truy cập trái phép không?
4. Hai dòng “APPROVED” có đủ chứng minh hai người độc lập không?
5. Một grant được cấp trước hạn kích hoạt nhưng kết thúc sau cửa sổ quyền. Cần đánh giá gì?
6. Mã băm của hồ sơ chứng minh được điều gì và không chứng minh được điều gì?
7. Vì sao cần đối soát từ máy đích và grant thay vì chỉ từ workflow?
8. Khắc phục thiếu phê duyệt bằng cách sửa thời điểm quyết định có phù hợp không?

### Gợi ý trả lời

1. Thiếu danh tính, thẩm quyền, nội dung, thời gian và liên kết tới quyền thực tế.
2. Cần căn cứ có hiệu lực trong lịch sử; trạng thái hiện tại không đủ để tái dựng.
3. Chưa chắc. Cần điều tra lỗi liên kết, thiếu dữ liệu hoặc ngoại lệ; sau đó đối chiếu tiêu chí.
4. Không. Cần loại trừ sự kiện trùng, cùng người và quyết định khác phạm vi hoặc phiên bản.
5. Hạn kích hoạt và giới hạn kết thúc quyền là hai điều kiện khác nhau; grant không được vượt thời gian được phép.
6. Có thể giúp kiểm tra nội dung giữa các bản sao hoặc so với mốc bảo vệ; không tự chứng minh nguồn đầy đủ, người có thẩm quyền hay quyết định đúng.
7. Để phát hiện quyền cấp trực tiếp, đường bỏ qua, tác vụ cấp muộn và trạng thái thực thi khác hồ sơ.
8. Không. Cần giữ lịch sử, bổ sung nhận xét có dấu vết và sửa cơ chế cấp quyền.

## Kết luận

Audit quyết định phê duyệt trong PAM phải nối được nhu cầu, thẩm quyền, quyết định và quyền thực tế theo đúng thời gian. Một kết luận có giá trị dựa trên tiêu chí rõ ràng, quần thể được đối soát, bằng chứng được bảo vệ và sự phân biệt giữa điều đã chứng minh với điều còn chưa xác minh.

Khi chuỗi bằng chứng đi tiếp đến phiên sử dụng và thu hồi, tổ chức có thể kiểm tra đầy đủ vòng đời quyền đặc biệt: vì sao quyền được cấp, ai chịu trách nhiệm, quyền có vượt phạm vi hay không và khi nào quyền thực sự chấm dứt.
