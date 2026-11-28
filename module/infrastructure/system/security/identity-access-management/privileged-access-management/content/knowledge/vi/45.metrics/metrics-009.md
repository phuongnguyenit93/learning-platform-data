# Time to revoke trong quản lý truy cập đặc quyền

## 1. Ý nghĩa của chỉ số

Trong Privileged Access Management (PAM), cấp quyền đúng người và đúng lúc mới giải quyết một phần của vấn đề. Quyền quản trị còn phải mất hiệu lực đúng lúc: khi nhân sự rời tổ chức, nhà cung cấp hết cửa sổ hỗ trợ, quyền JIT hết hạn hoặc đội ứng phó yêu cầu khóa khả năng truy cập.

**Time to revoke (TTR)** là thời gian từ một mốc kích hoạt thu hồi được định nghĩa rõ đến mốc xác nhận khả năng truy cập trong phạm vi yêu cầu đã mất hiệu lực. Chỉ số này đo kết quả kiểm soát truy cập, không chỉ đo tốc độ cập nhật trạng thái trên giao diện PAM.

Ví dụ, sau khi một tài khoản bị vô hiệu:

- Phiên SSH đã mở có thể còn hoạt động.
- Mật khẩu đã checkout có thể vẫn được máy chủ chấp nhận.
- Access token đã phát hành có thể còn hiệu lực.
- Một đường truy cập trực tiếp có thể không đi qua PAM proxy.
- Entitlement còn sót có thể cho phép xin cấp quyền trở lại.

Vì vậy, sự kiện “đã gửi lệnh thu hồi” không tự chứng minh nghĩa vụ thu hồi đã hoàn tất.

Bài học giúp người học định nghĩa mốc đo, xác định điều kiện kết thúc, tính chỉ số theo yêu cầu và theo nhóm, xử lý ca chưa hoàn tất và tìm nguyên nhân chậm. Các schema và mục tiêu thời gian dưới đây là ví dụ thiết kế, không phải quy định của một sản phẩm hoặc ngưỡng tuân thủ chung.

## 2. Xác định phạm vi trước khi đo

### 2.1. Một yêu cầu thu hồi là một đơn vị nghiệp vụ

Mỗi yêu cầu cần một định danh ổn định, chẳng hạn revocation_request_id, liên kết sự kiện kích hoạt, các lần thực thi, kết quả xác minh và bằng chứng.

Không tạo một yêu cầu nghiệp vụ mới sau mỗi lần retry. Nếu một yêu cầu phải gọi lại connector năm lần, đó vẫn là một nghĩa vụ thu hồi với cùng mốc bắt đầu.

Phạm vi cần trả lời các câu hỏi sau:

| Thành phần | Câu hỏi | Ví dụ trong PAM |
|---|---|---|
| Chủ thể | Ai hoặc workload nào mất quyền? | Kỹ sư trực ca, nhà cung cấp, danh tính pipeline |
| Quyền | Khả năng nào phải bị loại bỏ? | Quản trị máy chủ, chạy lệnh đặc quyền, đọc secret |
| Tài nguyên | Quyền bị thu hồi ở đâu? | Cụm máy chủ sản xuất, cơ sở dữ liệu, API hạ tầng |
| Đường truy cập | Có những cách nào để dùng quyền? | Proxy, truy cập trực tiếp, SSH key, token API |
| Đối tượng còn sống | Có phiên hoặc vật liệu nào đã phát hành? | Phiên SSH/RDP, password checkout, token |
| Nguyên nhân | Vì sao phải thu hồi? | Hết JIT, hết ca, offboarding, xử lý sự cố |
| Khả năng cấp lại | Chủ thể còn được xin quyền mới không? | Hết một grant có thể xin lại; nghỉ việc phải chặn cả điều kiện cấp |

Kết thúc một grant JIT và thu hồi toàn bộ quyền của người nghỉ việc có phạm vi khác nhau. Không áp cùng một điều kiện hoàn tất cho cả hai.

### 2.2. Tách các lớp quyền cần xử lý

Một yêu cầu có thể liên quan đến năm lớp:

1. **Điều kiện cấp quyền:** danh tính, nhóm, role, policy hoặc khả năng yêu cầu quyền.
2. **Grant hiện tại:** grant JIT, membership tạm thời hoặc entitlement cụ thể.
3. **Khả năng tạo truy cập mới:** đăng nhập, lấy secret, đổi token, mở phiên.
4. **Truy cập đang hoạt động:** phiên quản trị, kết nối cơ sở dữ liệu, tiến trình đặc quyền.
5. **Vật liệu đã phát hành:** mật khẩu, SSH key, certificate, access token hoặc refresh token.

Không phải yêu cầu nào cũng bao phủ cả năm lớp. Tuy nhiên, lớp nằm trong phạm vi phải có điều kiện hoàn tất và bằng chứng riêng. Không tự loại một lớp khỏi phạm vi chỉ vì connector chưa hỗ trợ xử lý.

Thu hồi quyền cũng không xóa được dữ liệu đã bị sao chép và không tự hoàn tác hành động quản trị trước đó. Những việc này thuộc phần ứng phó và khắc phục tiếp theo.

## 3. Chọn mốc bắt đầu và kết thúc

### 3.1. Các mốc thời gian

Có thể ghi nhận chuỗi mốc sau:

~~~text
t_trigger -> t_received -> t_started -> t_last_action -> t_confirmed
   |              |             |              |               |
Nghĩa vụ       Tiếp nhận      Bắt đầu       Thao tác       Đủ bằng chứng
có hiệu lực    sự kiện         xử lý          cuối         hoàn tất
~~~

Trong đó:

- **t_trigger:** thời điểm nghĩa vụ thu hồi có hiệu lực theo chính sách.
- **t_received:** thời điểm bộ điều phối tiếp nhận sự kiện.
- **t_started:** thời điểm bắt đầu hành động thực thi đầu tiên.
- **t_last_action:** thời điểm hành động thu hồi cuối cùng trong phạm vi được báo thành công.
- **t_confirmed:** thời điểm thu thập đủ bằng chứng xác minh điều kiện hoàn tất.

Một cách đo thận trọng, dễ truy nguyên:

~~~text
TTR_confirmed = t_confirmed - t_trigger
~~~

Nếu hệ thống có bằng chứng đáng tin cậy về thời điểm quyền thực sự mất hiệu lực, có thể lưu thêm t_effective:

~~~text
TTR_effective = t_effective - t_trigger
Verification_delay = t_confirmed - t_effective
~~~

Không gán t_effective bằng thời điểm gửi lệnh chỉ để có kết quả nhanh hơn. Một HTTP response thành công có thể chỉ cho biết yêu cầu được chấp nhận hoặc cấu hình đã cập nhật ở một điểm.

Nếu chỉ kiểm tra định kỳ, thời điểm mất hiệu lực thường chỉ biết nằm sau lần kiểm tra còn thành công cuối cùng và không muộn hơn lần xác minh bị từ chối. Khi đó nên công bố khoảng quan sát hoặc dùng mốc xác minh làm cận trên thận trọng.

### 3.2. Mốc bắt đầu theo nguyên nhân

| Tình huống | Mốc bắt đầu phù hợp | Sai lệch thường gặp |
|---|---|---|
| Nghỉ việc | Thời điểm chấm dứt quyền có hiệu lực theo quy trình đã duyệt | Lấy lúc đội PAM đọc ticket |
| Hết cửa sổ hỗ trợ | Thời điểm cửa sổ truy cập kết thúc | Lấy lúc batch chạy vào ngày hôm sau |
| Grant JIT hết hạn | Thời điểm grant phải mất hiệu lực | Lấy lúc tác vụ cleanup phát hiện grant |
| Thu hồi sớm | Thời điểm yêu cầu hợp lệ có hiệu lực | Lấy lúc connector sẵn sàng |
| Ứng phó sự cố | Thời điểm lệnh hoặc chính sách thu hồi được kích hoạt | Tự thay bằng thời điểm phát hiện mà không đổi tên chỉ số |

Trong ứng phó sự cố, nên phân biệt các mốc:

~~~text
A = thời điểm phát hiện
B = thời điểm quyết định thu hồi có hiệu lực
C = thời điểm xác minh thu hồi đầy đủ

Detection-to-decision              = B - A
Time to revoke                    = C - B
Detection-to-confirmed-revocation  = C - A
~~~

Cả ba phép đo đều hữu ích, nhưng trả lời các câu hỏi khác nhau. Không trộn những yêu cầu dùng mốc bắt đầu khác nhau vào một phân vị rồi so sánh như thể chúng tương đương.

### 3.3. Độ trễ truyền sự kiện vẫn thuộc chỉ số đầu cuối

Giả sử nghĩa vụ có hiệu lực lúc 08:15, bộ điều phối nhận lúc 08:18 và xác minh xong lúc 08:27:

~~~text
TTR đầu cuối = 08:27 - 08:15 = 12 phút
Tiếp nhận đến xác minh = 08:27 - 08:18 = 9 phút
Độ trễ tiếp nhận = 08:18 - 08:15 = 3 phút
~~~

Chỉ số 9 phút giúp đánh giá bộ điều phối sau khi nhận sự kiện. Nó không thay thế được 12 phút đầu cuối vì chủ thể có thể tiếp tục dùng quyền trong thời gian sự kiện chưa tới PAM.

## 4. Điều kiện “thu hồi xong” trong PAM

### 4.1. Xác minh đúng loại đối tượng

| Đối tượng | Hành động thường có | Điều cần xác minh |
|---|---|---|
| Role hoặc group quản trị | Gỡ membership, vô hiệu grant | Nguồn quyền đã cập nhật và điểm thực thi không còn cho hành động thuộc quyền cũ |
| Quyền lấy secret | Chặn checkout hoặc quyền đọc vault | Chủ thể không thể lấy hoặc cấp lại secret qua các đường trong phạm vi |
| Mật khẩu đã checkout | Đổi mật khẩu ở hệ thống đích | Mật khẩu cũ không còn được chấp nhận |
| SSH public key | Gỡ hoặc vô hiệu key ở các điểm xác thực | Các nút bắt buộc không còn chấp nhận key cũ |
| Certificate | Áp dụng cơ chế vô hiệu được hỗ trợ hoặc chờ hết hạn nếu chính sách chấp nhận | Điểm thực thi thực sự áp dụng cơ chế đó hoặc thời hạn đã hết |
| Token | Chặn cấp mới, xử lý access/refresh token theo cơ chế thực tế | Token cũ không còn cho truy cập trong phạm vi |
| Phiên đặc quyền | Ngắt phiên hoặc cô lập khả năng hoạt động theo playbook | Phiên không còn thực hiện được hành động bị thu hồi |
| Danh tính dịch vụ | Thu hồi grant, chuyển credential hoặc dừng workload theo kế hoạch | Credential cũ hết hiệu lực, workload hợp lệ đã chuyển hoặc được dừng có kiểm soát |

Xóa secret trong vault không tự làm bản secret đã lấy trước đó mất hiệu lực tại hệ thống đích. Ngược lại, đổi mật khẩu ở hệ thống đích cũng không nhất thiết chấm dứt một kết nối đã xác thực.

Với token, không giả định mọi định dạng đều hỗ trợ thu hồi tức thời. Một access token được dịch vụ xác minh độc lập có thể tiếp tục được chấp nhận đến hết hạn nếu tại điểm thực thi không có cơ chế chặn phù hợp. Thu hồi refresh token mới giải quyết một phần của phạm vi trong trường hợp đó.

### 4.2. Đường cuối cùng quyết định thời điểm hoàn tất

Gọi P là tập đường truy cập bắt buộc phải thu hồi. Nếu mọi đường đều có xác minh hợp lệ:

~~~text
t_confirmed(request) = max(t_confirmed(p)), với mọi p thuộc P
TTR(request) = t_confirmed(request) - t_trigger
~~~

Một đường chưa xác minh không được đưa vào phép max với giá trị 0 và cũng không được âm thầm bỏ khỏi tập.

Nếu đăng nhập mới bị chặn sau hai phút nhưng phiên trực tiếp còn dùng được sau mười phút thì TTR của yêu cầu đầy đủ chưa phải hai phút.

Số lượng “3/4 đường đã xong” là thông tin tiến độ. Nó không đồng nghĩa yêu cầu đã hoàn tất 75% về mức rủi ro: đường còn lại có thể chính là đường nguy hiểm nhất.

### 4.3. Chặn khẩn cấp và thu hồi lâu dài

Trong sự cố, đội vận hành có thể cô lập workload hoặc chặn đường mạng trước khi thu hồi xong entitlement ở nguồn.

Cần phân biệt:

- **Containment confirmed:** hành động trong phạm vi đã bị chặn bằng biện pháp cô lập được xác minh.
- **Durable revocation confirmed:** quyền nguồn, credential và khả năng cấp lại đã được xử lý theo yêu cầu lâu dài.

Nếu chính sách chấp nhận containment làm điểm kết thúc cho một chỉ số khẩn cấp, phải đặt tên và định nghĩa riêng. Việc bỏ cô lập khi quyền nguồn còn nguyên có thể làm khả năng truy cập xuất hiện trở lại.

Không mặc định việc thu hồi chỉ hoàn tất khi mọi hệ thống đều khỏe. Một biện pháp chặn khác có thể hợp lệ nếu bao phủ đúng phạm vi và được chính sách chấp nhận; nhưng bằng chứng và nghĩa vụ xử lý lâu dài vẫn phải được ghi rõ.

## 5. Dữ liệu và bằng chứng cho phép đo

### 5.1. Một sự kiện minh họa

~~~json
{
  "revocation_request_id": "rvk-example-027",
  "event_id": "evt-example-071",
  "event_type": "PATH_REVOCATION_CONFIRMED",
  "subject_id": "vendor-example-17",
  "subject_type": "HUMAN",
  "reason": "CONTRACT_END",
  "scope_version": 1,
  "target_id": "production-admin-zone",
  "path_id": "direct-ssh",
  "trigger_at": "2026-11-27T08:15:00+07:00",
  "occurred_at": "2026-11-27T08:27:00+07:00",
  "observed_at": "2026-11-27T08:27:03+07:00",
  "outcome": "CONFIRMED",
  "verification_method": "CONTROL_STATE_AND_AUTHORIZATION_CHECK",
  "evidence_ref": "evidence-example-027",
  "policy_version": "revocation-example-v3"
}
~~~

Đây là schema học tập. Một hệ thống thực tế có thể đặt tên khác nhưng cần giữ rõ ý nghĩa:

- occurred_at: thời điểm nguồn xác nhận sự kiện xảy ra.
- observed_at: thời điểm bộ thu thập quan sát sự kiện.
- scope_version: phiên bản tập tài nguyên và đường truy cập dùng để kết luận.
- evidence_ref: tham chiếu đến bằng chứng có kiểm soát truy cập.
- policy_version: quy tắc mốc đo, điều kiện hoàn tất và mục tiêu tại thời điểm đó.

Không ghi mật khẩu, private key hoặc token vào log để làm bằng chứng. Dùng định danh tham chiếu và kho bằng chứng được bảo vệ.

### 5.2. Bản ghi tổng hợp cho một yêu cầu

~~~text
request_id
trigger_at
received_at
started_at
scope_version
required_path_count
confirmed_path_count
status
confirmed_at
objective_seconds
reason
risk_tier
subject_type
verification_state
last_error_category
~~~

Trạng thái tổng hợp có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| PENDING | Chưa bắt đầu hoặc chưa có kết quả |
| IN_PROGRESS | Đang xử lý các đường truy cập |
| PARTIAL | Một phần đã xác minh, còn điều kiện bắt buộc chưa đạt |
| CONFIRMED | Đủ bằng chứng cho mọi điều kiện bắt buộc |
| FAILED | Có hành động thất bại, cần xử lý tiếp |
| UNKNOWN | Thiếu dữ liệu hoặc không đủ khả năng kết luận |
| CANCELLED | Yêu cầu được hủy hợp lệ, có lý do và dấu vết |

FAILED và UNKNOWN không làm nghĩa vụ thu hồi biến mất. Nếu quyền vẫn phải bị thu hồi, tuổi nghĩa vụ tiếp tục tăng cho đến khi có kết quả hoặc quyết định xử lý hợp lệ.

CANCELLED không phải kết quả thu hồi thành công. Báo riêng số lượng và lý do hủy để tránh dùng trạng thái này làm cách loại ca chậm khỏi thống kê.

### 5.3. Chất lượng dữ liệu thời gian

Đồng bộ đồng hồ và dùng timestamp có múi giờ hoặc UTC thống nhất. Nếu confirmed_at nhỏ hơn trigger_at, đánh dấu lỗi dữ liệu; không lấy trị tuyệt đối và không ép về 0.

Cần xử lý các tình huống:

- Sự kiện trùng: gộp theo event_id hoặc khóa tương đương.
- Retry: mỗi lần thử có attempt_id nhưng giữ nguyên request_id và trigger_at.
- Sự kiện đến muộn: giữ cả thời điểm xảy ra và thời điểm nhận, sửa báo cáo theo chính sách công bố.
- Sai thứ tự: tổng hợp theo nội dung và mốc hợp lệ, không chỉ theo thứ tự nhận.
- Thay đổi phạm vi: ghi phiên bản và lý do; phát hiện thêm đường bắt buộc phải dẫn tới đánh giá lại kết luận.
- Mất dữ liệu: biểu diễn là thiếu bằng chứng, không coi khoảng trống là thành công.

Đồng hồ đơn điệu hữu ích cho thời lượng cục bộ trong một tiến trình. Đo giữa nhiều hệ thống vẫn cần timestamp có nguồn và chất lượng đồng bộ được kiểm soát.

## 6. Tính toán ở mức yêu cầu và mức nhóm

### 6.1. Phân rã để tìm nguyên nhân chậm

Các đoạn thời gian hỗ trợ phân tích:

~~~text
Ingestion_delay   = received_at - trigger_at
Queue_delay       = started_at - received_at
Execution_span    = last_action_at - started_at
Verification_span = confirmed_at - last_action_at
~~~

Nếu thực thi và xác minh diễn ra xen kẽ hoặc song song, đây chỉ là cách chia theo các mốc đã chọn. Muốn tìm nút thắt cần xem timeline từng nhánh. Không cộng thời gian của các nhánh chạy song song thành thời gian đầu cuối.

Ví dụ, hai connector cùng chạy trong bốn phút không tạo ra tám phút TTR. Thời điểm hoàn tất phụ thuộc nhánh kết thúc cuối cùng và thời gian xác minh sau đó.

### 6.2. Trung bình, trung vị và phân vị

Với các ca đã xác minh hoàn tất, nên xem đồng thời:

- Trung vị: thời gian điển hình.
- p95 hoặc p99: phần đuôi phân phối.
- Giá trị lớn nhất: ca hoàn tất chậm nhất.
- Số ca: mức độ đại diện của thống kê.

Có 20 ca hoàn tất: 18 ca mất hai phút, một ca mất 20 phút và một ca mất 40 phút.

~~~text
Trung bình = (18 × 2 + 20 + 40) / 20 = 4,8 phút
Trung vị   = 2 phút
p95        = 20 phút, nếu dùng nearest-rank
Tối đa     = 40 phút
~~~

Theo nearest-rank, vị trí p95 trong dãy tăng dần là ceil(0,95 × 20) = 19. Công cụ khác có thể dùng phép nội suy khác; thống nhất phương pháp trước khi so sánh dashboard.

Trung bình 4,8 phút che khuất hai ca chậm. Nhưng ngay cả p95 cũng chưa phản ánh ca chưa hoàn tất nếu dữ liệu chỉ gồm những yêu cầu đã đóng.

Không lấy trung bình các p95 theo nhóm để tạo p95 toàn hệ thống. Cần tổng hợp lại quan sát phù hợp hoặc gộp histogram theo một phương pháp nhất quán.

### 6.3. Ca chưa hoàn tất không có TTR hoàn tất

Giả sử ngoài 20 ca trên còn một yêu cầu chưa xác minh sau 90 phút.

Không ghi TTR của yêu cầu này bằng 0. Cũng không kết luận “mọi yêu cầu được thu hồi trong tối đa 40 phút”, vì 40 phút chỉ là tối đa của nhóm đã hoàn tất.

Tại thời điểm báo cáo:

~~~text
open_age = report_time - trigger_at = 90 phút
TTR hoàn tất = chưa xác định
~~~

Open age đo thời gian nghĩa vụ chưa được xác nhận hoàn tất. Nó không chứng minh quyền còn hoạt động trong toàn bộ khoảng đó: có thể điểm thực thi đã chặn nhưng telemetry bị hỏng. Cả việc chưa thu hồi và việc chưa xác minh đều cần được xử lý, với nguyên nhân riêng.

Trong phân tích thời gian đến sự kiện, đây là quan sát bị kiểm duyệt phải. Với dashboard vận hành cơ bản, hãy ghi rõ “phân vị trên ca đã hoàn tất”, đi kèm số ca mở, tuổi ca mở lớn nhất và mức đầy đủ bằng chứng. Không tự gán một thời lượng hoàn tất giả cho dữ liệu chưa biết.

### 6.4. Tỷ lệ đáp ứng mục tiêu cần mẫu số rõ ràng

Giả sử mỗi yêu cầu có mục tiêu S giây. Tại thời điểm báo cáo R:

~~~text
Eligible = các yêu cầu trong cohort có trigger_at + S <= R

On_time = các yêu cầu thuộc Eligible có xác minh hợp lệ
          và confirmed_at <= trigger_at + S

On_time_rate = count(On_time) / count(Eligible)
~~~

Ca mở, lỗi hoặc thiếu bằng chứng sau deadline vẫn thuộc mẫu số, trừ khi có quy tắc loại trừ hợp lệ đã công bố và báo cáo riêng.

Yêu cầu chưa tới deadline được ghi “đang trong cửa sổ mục tiêu”; không coi là đã thành công hoặc đã trễ. Nếu Eligible rỗng, hiển thị N/A thay vì 100%.

Ví dụ có 100 yêu cầu đã tới deadline:

| Kết quả | Số ca | Tính đúng hạn? |
|---|---:|---|
| Xác minh trước hoặc đúng deadline | 92 | Có |
| Hoàn tất sau deadline | 4 | Không |
| Còn mở sau deadline | 3 | Không |
| Chưa biết kết quả do thiếu telemetry | 1 | Không |

Tỷ lệ đúng hạn là 92/100 = 92%. Có thể công bố phân vị trên 96 ca đã đóng, nhưng không dùng tập đó để xóa bốn ca chưa có kết luận khỏi tỷ lệ đúng hạn.

### 6.5. Chọn cohort phù hợp

Hai cách nhìn có mục đích khác nhau:

- **Theo ngày phát sinh nghĩa vụ:** yêu cầu bắt đầu trong khoảng nào, đã được xử lý ra sao đến thời điểm chốt.
- **Theo ngày hoàn tất:** các yêu cầu đóng trong khoảng nào, thời gian xử lý là bao lâu.

Báo cáo theo ngày hoàn tất giúp nhìn throughput nhưng có thể bỏ qua backlog. Báo cáo theo ngày phát sinh giúp thấy nghĩa vụ tồn đọng nhưng phải ghi thời điểm chốt và cách xử lý những yêu cầu chưa tới deadline.

Phân nhóm theo mức rủi ro, người/workload, sự cố/thường lệ và loại tài nguyên. Một nhóm đông với thao tác đơn giản có thể che lấp nhóm nhỏ chứa quyền quản trị rất nhạy cảm.

## 7. Ví dụ xuyên suốt: thu hồi quyền nhà cung cấp

Một nhà cung cấp kết thúc cửa sổ hỗ trợ sản xuất lúc 08:15. Phạm vi gồm grant PAM, khả năng mở phiên mới, phiên SSH hiện hữu và key của đường truy cập trực tiếp trên các máy chủ liên quan.

| Thời điểm | Sự kiện | Điều có thể kết luận |
|---|---|---|
| 08:15 | Cửa sổ hỗ trợ kết thúc | Nghĩa vụ thu hồi bắt đầu |
| 08:16 | Bộ điều phối nhận sự kiện | Truyền sự kiện mất một phút |
| 08:17 | Grant bị vô hiệu; xác minh không mở được phiên mới qua proxy | Đường mở phiên mới qua proxy bị chặn |
| 08:20 | Phiên SSH qua proxy đã đóng, có xác nhận | Phần phiên qua proxy hoàn tất |
| 08:25 | Key cũ được loại khỏi các máy chủ trong phạm vi | Thao tác cấu hình đã xong |
| 08:27 | Xác minh trạng thái điểm thực thi và việc từ chối key cũ đạt yêu cầu | Mọi đường bắt buộc được xác minh |

Kết quả:

~~~text
TTR_confirmed = 08:27 - 08:15 = 12 phút
Độ trễ tiếp nhận = 1 phút
Chặn mở phiên mới qua proxy = 2 phút từ mốc kích hoạt
Xử lý từ tiếp nhận đến xác minh đầy đủ = 11 phút
~~~

Nếu chỉ dùng sự kiện “grant revoked” lúc 08:17, dashboard sẽ báo hai phút và bỏ qua đường SSH trực tiếp.

Giả sử mục tiêu minh họa là 10 phút, yêu cầu bị trễ hai phút. Cần xem xét tốc độ xử lý key và xác minh, không chuyển mốc bắt đầu sang 08:17 để làm kết quả đạt mục tiêu.

### 7.1. Khi một máy chủ không thể xác minh

Nếu một máy chủ mất kết nối, yêu cầu chưa có đủ bằng chứng hoàn tất toàn phạm vi. Timeout từ lệnh kiểm tra không chứng minh key cũ bị từ chối.

Nếu có biện pháp cô lập được xác minh bao phủ máy chủ đó, ghi nhận containment theo đúng chính sách. Nghĩa vụ xử lý key và kiểm tra trước khi đưa máy trở lại vẫn cần tồn tại.

### 7.2. Khi phát hiện tài nguyên ngoài inventory

Nếu sau khi đóng yêu cầu mới phát hiện một máy chủ khác chấp nhận key cũ:

1. Bổ sung tài nguyên và bằng chứng vào phạm vi theo quy trình.
2. Đánh giá lại kết luận hoàn tất, mở lại hoặc tạo nghĩa vụ liên kết theo chính sách.
3. Điều chỉnh báo cáo và giữ lịch sử kết luận trước đó.
4. Xử lý nguyên nhân thiếu inventory.

Không xóa dấu vết cũ và không giữ nguyên kết luận “đủ phạm vi” khi đã có bằng chứng trái ngược.

## 8. Đặt mục tiêu theo rủi ro và năng lực thực thi

Không có một con số TTR phù hợp cho mọi danh tính và tài nguyên.

Khi chọn mục tiêu, cần xét mức đặc quyền, độ nhạy cảm, nguyên nhân thu hồi, loại chủ thể, phiên đang mở, credential đã cấp, năng lực điểm thực thi và thời gian xác minh.

Một bảng mục tiêu minh họa:

| Nhóm | Kết quả cần theo dõi | Mục tiêu ví dụ |
|---|---|---|
| Sự cố trên hệ thống trọng yếu | Chặn hành động trong phạm vi bằng biện pháp khẩn cấp đã xác minh | Containment trong 5 phút |
| Offboarding quản trị theo lịch | Thu hồi đủ entitlement, phiên và vật liệu liên quan | Xác minh revocation trong 15 phút |
| Hết JIT thường lệ | Grant mất hiệu lực và xử lý phiên theo chính sách | Trong độ trễ cho phép đã công bố |
| Workload chuyển credential | Credential cũ mất hiệu lực, workload chuyển đổi hoặc dừng có kiểm soát | Mục tiêu riêng theo quy trình chuyển đổi |

Các con số không phải chuẩn tuân thủ. Cần đo thử để biết năng lực thực tế, khoảng trống và chi phí cải thiện.

### 8.1. Chuẩn bị trước với deadline đã biết

Với offboarding theo lịch, có thể kiểm kê quyền, liệt kê phiên, kiểm tra connector và chuẩn bị phương án trước thời điểm có hiệu lực. Việc làm mất quyền thực tế vẫn theo lịch đã duyệt.

TTR được tính từ mốc nghĩa vụ có hiệu lực. Hoạt động chuẩn bị được ghi riêng; không tự đẩy mốc bắt đầu sớm hoặc muộn để đạt một kết quả mong muốn.

### 8.2. Giới hạn kỹ thuật phải xuất hiện trong báo cáo

Nếu access token còn hạn tối đa 60 phút và điểm thực thi chưa có cơ chế chặn phù hợp, một mục tiêu thu hồi toàn bộ trong năm phút có khoảng trống thiết kế.

Các hướng cải thiện có thể gồm giảm thời gian sống token, bổ sung kiểm tra trạng thái được điểm thực thi hỗ trợ, hoặc dùng biện pháp cô lập theo playbook. Cần đánh giá tác động vận hành và kiểm thử cơ chế đã chọn.

Chặn cấp token mới sau một phút không chứng minh token cũ đã mất khả năng truy cập. Không đổi nhãn phép đo của một hành động thành kết quả của toàn bộ yêu cầu.

### 8.3. Ngoại lệ phải có dấu vết

Một ngoại lệ vận hành cần có phạm vi, lý do, người có thẩm quyền, thời hạn và biện pháp bù đắp. Báo riêng ca có ngoại lệ và tác động tới mục tiêu.

Không âm thầm thu hẹp mẫu số hoặc tăng mục tiêu hồi tố sau khi một yêu cầu bị trễ.

## 9. Cải thiện theo từng nguyên nhân chậm

### 9.1. Chậm truyền sự kiện

Dấu hiệu: received_at trễ nhiều so với trigger_at nhưng các bước sau chạy nhanh.

Hướng cải thiện:

- Kết nối nguồn nhân sự, lịch nhà cung cấp và quản lý JIT với bộ điều phối.
- Theo dõi sự kiện thất lạc, hàng đợi lỗi và thông điệp đến muộn.
- Có đối soát định kỳ để phát hiện nghĩa vụ chưa được đưa vào hàng đợi.
- Chuẩn bị trước đối với thời điểm đã biết.

Không bỏ thời gian trước lúc PAM nhận sự kiện khỏi chỉ số đầu cuối chỉ vì nguồn thuộc đội khác.

### 9.2. Chậm ở hàng đợi và quyết định

Dấu hiệu: sự kiện đã nhận nhưng chưa bắt đầu hành động.

Phân biệt việc đã được chính sách cho phép tự động với việc cần phê duyệt. Quy trình khẩn cấp có thể có tuyến quyết định riêng, được định nghĩa trước và lưu dấu vết.

Theo dõi năng lực hàng đợi, độ ưu tiên và đầu mối chịu trách nhiệm. Một ca quản trị trọng yếu không nên chìm trong hàng đợi các tác vụ thường lệ chỉ vì tất cả được xử lý cùng thứ tự.

### 9.3. Chậm ở thực thi

Dấu hiệu: retry nhiều, tài nguyên chỉ cập nhật theo batch, phiên không đóng hoặc workload chưa chuyển credential.

Hướng cải thiện:

- Thiết kế hành động idempotent để retry an toàn.
- Chạy song song các nhánh độc lập nếu cơ chế cho phép.
- Đặt timeout, phân loại lỗi, backoff và chuyển người xử lý khi cần.
- Kiểm kê đường trực tiếp, local admin và credential ngoài vault.
- Dùng JIT/JEA để giảm quyền thường trực và phạm vi phải thu hồi.
- Với workload, chuẩn bị khả năng đổi credential và quan sát việc dùng vật liệu cũ.

Thời hạn JIT không tự chứng minh mọi phiên đã mất hiệu lực. JEA giới hạn hành động có thể làm, nhưng không thay thế vòng đời cấp và thu hồi quyền.

Đối với credential dịch vụ, cần phân biệt hai kết quả: loại bỏ khả năng dùng credential cũ và duy trì workload hợp lệ bằng credential mới. Nếu quy trình cho phép một thời gian chồng lấn credential, thời gian cũ vẫn được chấp nhận phải được phản ánh trong phép đo phù hợp.

### 9.4. Chậm ở xác minh

Dấu hiệu: thao tác báo thành công sớm nhưng phải chờ lâu mới có đủ bằng chứng.

Hướng cải thiện:

- Quy định bằng chứng theo loại đường truy cập.
- Thu thập trạng thái điểm thực thi và trạng thái phiên.
- Điều chỉnh tần suất kiểm tra theo rủi ro và giới hạn tải.
- Có phương án xác minh độc lập khi telemetry chính hỏng.
- Bảo vệ tài khoản, kênh và dữ liệu dùng cho xác minh.

Một lần gọi API lỗi do mạng không chứng minh quyền đã bị thu hồi. Một phép thử bằng tài khoản mẫu cũng không tự chứng minh quyền của danh tính thật đã hết, nếu không có bằng chứng cấu hình và phạm vi tương đương.

Không phát lại credential thật tùy tiện lên hệ thống sản xuất. Chọn phương thức xác minh đã được quy định, sử dụng dữ liệu ít nhạy cảm nhất đủ để kết luận.

## 10. Logic tổng hợp trạng thái minh họa

Thuật toán sau mô tả việc tổng hợp bằng chứng, không phải API của một sản phẩm:

~~~text
on_event(event):
    validate_schema_and_time(event)

    if event was already processed:
        return

    request = find_request(event.revocation_request_id)
    append_event_and_evidence(request, event)

    if required scope changes:
        record_new_scope_version(request)
        re_evaluate_previous_completion(request)

    for each required path in current scope:
        derive_verified_state(path)

        if evidence is missing or contradictory:
            mark_path_as_unconfirmed(path)

    if every required condition is verified:
        request.status = CONFIRMED
        request.confirmed_at = latest_required_confirmation_time()
        request.ttr = request.confirmed_at - request.trigger_at
    else:
        preserve_any_previous_completion_in_history()
        request.confirmed_at = absent
        request.ttr = absent
        request.open_age = report_time - request.trigger_at
        request.status = derive_incomplete_status()

    publish_aggregate_without_secrets(request)
~~~

Một hệ thống thực tế cần lưu lịch sử, xử lý sự kiện đến muộn và điều chỉnh báo cáo đã công bố. Không âm thầm xóa kết luận trước đó khi yêu cầu bị mở lại.

Điều kiện hoàn tất không nên chỉ là “số connector trả thành công bằng số connector đã gọi”. Điều đó bỏ qua connector chưa được gọi, đường chưa có trong inventory và khác biệt giữa cập nhật cấu hình với hiệu lực thực thi.

## 11. Dashboard và cảnh báo

Dashboard cần trả lời ba câu hỏi: nhanh đến đâu, còn nghĩa vụ nào chưa xong và có đủ bằng chứng để tin kết quả không?

| Nhóm | Chỉ số gợi ý | Mục đích |
|---|---|---|
| Ca đã hoàn tất | Trung vị, p95, tối đa, số ca | Nhìn phân phối thời gian |
| Đáp ứng mục tiêu | Tỷ lệ đúng hạn trên cohort đã tới deadline | Giữ ca mở và ca lỗi trong bức tranh |
| Tồn đọng | Ca mở, ca quá hạn, tuổi lớn nhất | Tìm nghĩa vụ cần xử lý |
| Chất lượng xác minh | Ca thiếu bằng chứng, đường chưa rõ | Đánh giá độ tin cậy |
| Nguyên nhân | Tiếp nhận, hàng đợi, connector, phiên, token, xác minh | Chọn hành động cải thiện |
| Phân nhóm | Risk tier, người/workload, thường lệ/sự cố | Tránh che khuất nhóm rủi ro cao |

Một cảnh báo có thể chứa:

~~~text
Yêu cầu: rvk-example-027
Nhóm: quản trị sản xuất
Mốc bắt đầu: 08:15
Deadline: 08:25
Trạng thái: PARTIAL
Đã xác minh: 3/4 đường bắt buộc
Còn thiếu: direct-ssh tại một điểm thực thi
Lỗi gần nhất: chưa có xác nhận trạng thái đích
Đầu mối xử lý: đội vận hành tài nguyên
Tham chiếu bằng chứng: evidence-example-027
~~~

Cần có người hoặc đội chịu trách nhiệm, cơ chế chuyển cấp và hành động tiếp theo. Một cảnh báo “p95 tăng” không thay thế cảnh báo cho ca quản trị trọng yếu đang quá hạn.

Không đưa request ID, session ID hoặc từng danh tính vào mọi nhãn metric có số lượng giá trị rất lớn. Dùng chiều tổng hợp cần thiết cho metric; giữ dữ liệu tra cứu chi tiết trong hệ thống sự kiện có kiểm soát truy cập.

## 12. Các lỗi đo thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Kết thúc ở lúc API tiếp nhận lệnh | Chưa chứng minh hiệu lực | Tách command accepted và revocation confirmed |
| Chỉ kiểm tra đăng nhập mới | Phiên cũ có thể còn chạy | Bao phủ phiên theo phạm vi |
| Chỉ chặn vault | Credential đã lấy có thể còn dùng được | Kiểm tra tại hệ thống đích |
| Reset mốc sau retry | Che tổng thời gian tồn đọng | Giữ request gốc, tách attempt |
| Loại ca mở và ca lỗi | Tạo thiên lệch về ca thành công | Báo backlog và mẫu số đầy đủ |
| Coi timeout là bị từ chối | Không phân biệt lỗi kết nối và mất quyền | Xác minh đúng nguyên nhân |
| Thu hẹp phạm vi khi gặp máy khó | Nghĩa vụ ban đầu chưa được đáp ứng | Version hóa phạm vi và báo ngoại lệ |
| Lấy trung bình các p95 | Không tạo được p95 chung | Tổng hợp quan sát hoặc histogram phù hợp |
| Coi TTR thấp là PAM tốt toàn diện | Không chứng minh inventory hay phát hiện đầy đủ | Xem cùng độ bao phủ, least privilege và chất lượng phát hiện |

TTR phải được xem cùng mức đầy đủ của inventory. Thu hồi rất nhanh trên một tập chỉ bao phủ một phần tài nguyên không chứng minh rằng mọi đường truy cập đã an toàn.

## 13. Bài tập áp dụng

### Bài tập 1: Tính theo đường cuối cùng

Yêu cầu có hiệu lực lúc 14:00, được tiếp nhận lúc 14:01. Grant PAM được xác minh vô hiệu lúc 14:02, phiên cơ sở dữ liệu kết thúc lúc 14:04 và credential cũ bị từ chối lúc 14:09.

**Câu hỏi:** TTR đầu cuối và thời gian từ tiếp nhận là bao nhiêu?

**Gợi ý giải:** TTR đầu cuối là chín phút; từ tiếp nhận đến xác minh đầy đủ là tám phút. Không dùng mốc vô hiệu grant để đóng toàn yêu cầu vì hai điều kiện khác chưa hoàn tất.

### Bài tập 2: Thiếu một máy chủ

Trong phạm vi có 10 máy chủ. Chín máy đã xác minh key cũ bị từ chối. Máy thứ mười mất kết nối và lệnh quản trị timeout.

**Câu hỏi:** Có thể ghi CONFIRMED không?

**Gợi ý giải:** Chưa đủ bằng chứng. Timeout không chứng minh key bị từ chối. Giữ trạng thái chưa hoàn tất, xác định đường thiếu bằng chứng và dùng phương án xác minh hoặc cô lập hợp lệ. Không giảm phạm vi xuống chín máy chỉ để đóng yêu cầu.

### Bài tập 3: Mẫu số của tỷ lệ đúng hạn

Có 50 yêu cầu đã tới deadline: 43 ca đúng hạn, bốn ca hoàn tất trễ, hai ca mở và một ca thiếu telemetry.

**Câu hỏi:** Tỷ lệ đúng hạn là bao nhiêu?

**Gợi ý giải:** 43/50 = 86%. Hai ca mở và một ca thiếu telemetry vẫn trong mẫu số. Phân vị trên 47 ca đã đóng là báo cáo khác và phải được ghi rõ.

### Bài tập 4: Token còn hiệu lực

Access token còn hạn 30 phút; điểm thực thi chưa có cơ chế chặn token đó. PAM ngăn cấp token mới sau một phút. Mục tiêu thu hồi toàn bộ khả năng truy cập là năm phút.

**Câu hỏi:** Có được báo TTR một phút không?

**Gợi ý giải:** Không. Chỉ điều kiện ngăn cấp mới đã đạt. Cần xử lý khả năng dùng token cũ bằng cơ chế thực thi hoặc containment được chấp nhận và xác minh những phần còn lại. Nếu không đạt, báo khoảng trống đối với mục tiêu.

### Bài tập 5: Đọc báo cáo có phân vị đẹp

Dashboard ghi p95 là hai phút trên 200 yêu cầu hoàn tất. Cùng cohort có 12 yêu cầu đã quá hạn nhưng chưa xác minh, trong đó hai ca thuộc hệ thống trọng yếu.

**Câu hỏi:** Có thể kết luận quy trình đáp ứng tốt chỉ từ p95 không?

**Gợi ý giải:** Chưa thể. Phải xem mẫu số, tuổi các ca mở, nhóm rủi ro và chất lượng bằng chứng. p95 của nhóm hoàn tất không đại diện cho nghĩa vụ đang tồn đọng.

## 14. Điểm cần giữ khi vận hành

Một giá trị Time to revoke chỉ đáng tin khi trả lời được bốn điều: bắt đầu từ đâu, bao phủ khả năng truy cập nào, kết thúc bằng bằng chứng gì và những ca chưa hoàn tất đang ở đâu trong báo cáo.

Trong PAM, thu hồi entitlement, ngăn cấp mới, kết thúc phiên và vô hiệu credential có liên quan nhưng không tự thay thế nhau. Đo từng phần để tìm nguyên nhân chậm; dùng điều kiện hoàn tất toàn phạm vi để xác nhận nghĩa vụ đã được xử lý.

Kết hợp TTR với kiểm kê quyền, least privilege, JIT/JEA, quản lý vault, luân chuyển credential và giám sát phiên giúp tổ chức giảm thời gian quyền đặc biệt còn tồn tại ngoài nhu cầu, đồng thời có bằng chứng phục vụ kiểm toán và ứng phó sự cố.
