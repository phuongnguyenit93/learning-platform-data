# Provisioning backlog — Công việc cấp phát danh tính còn tồn

## 1. Backlog phản ánh khoảng cách giữa yêu cầu và trạng thái thực tế

Trong IAM, provisioning là quá trình tạo tài khoản, cập nhật thuộc tính, đồng bộ nhóm hoặc cấp quyền tại hệ thống đích theo trạng thái đã được chấp thuận. Luồng quản lý vòng đời danh tính còn cần thực hiện chiều ngược lại: gỡ nhóm, thu hồi quyền, vô hiệu hóa hoặc xóa tài khoản khi điều kiện truy cập không còn phù hợp.

**Provisioning backlog** là tập công việc đã được hệ thống tiếp nhận để thực thi nhưng chưa được giải quyết theo tiêu chí hoàn tất đã định nghĩa. Trong bài này, backlog bao gồm cả cấp phát và thu hồi; dashboard phải tách riêng các loại thao tác để thể hiện tác động khác nhau của chúng.

Ví dụ, một nhân viên mới được duyệt quyền sử dụng ứng dụng nhưng tài khoản chưa được tạo vì connector bị lỗi. Đây là độ trễ cung cấp khả năng làm việc. Một nhân viên đã nghỉ việc nhưng tác vụ gỡ quyền ở ứng dụng vẫn chưa hoàn tất tạo ra một khoảng thời gian quyền cũ có thể còn tồn tại. Hai công việc cùng nằm trong backlog nhưng không có cùng mức ưu tiên.

Quan sát backlog giúp đội IAM trả lời ba câu hỏi: còn bao nhiêu thay đổi chưa hoàn tất, chúng đã chờ bao lâu và thay đổi nào đang tạo tác động lớn nhất? Một con số độ sâu hàng đợi đơn lẻ thường không trả lời đủ cả ba.

Các tên trạng thái, metric và schema dưới đây là mô hình minh họa để thiết kế giám sát. Chúng không phải trạng thái chuẩn chung của SCIM hoặc tên field bắt buộc của một sản phẩm IAM.

## 2. Xác định đơn vị công việc trước khi đếm

### 2.1. Một người dùng có thể tạo nhiều công việc

Một thay đổi nhân sự có thể cần tạo tài khoản ở ba ứng dụng và thêm thành viên vào hai nhóm. Có thể có năm công việc thực thi, dù chỉ liên quan một người. Ngược lại, một công việc đồng bộ nhóm có thể tác động tới nhiều thành viên.

Do đó, cần ghi rõ đơn vị của dashboard:

| Đơn vị đo | Ý nghĩa | Giới hạn khi diễn giải |
|---|---|---|
| Công việc logic | Một thay đổi cụ thể cần đạt ở một hệ thống đích | Không tương đương số người bị ảnh hưởng |
| Danh tính duy nhất | Số danh tính còn ít nhất một công việc tồn | Không thể hiện một người đang thiếu bao nhiêu thay đổi |
| Yêu cầu nghiệp vụ | Một yêu cầu cấp quyền hoặc sự kiện vòng đời có thể tạo nhiều công việc | Có thể che một nhánh thực thi còn lỗi |
| Lần thử thực thi | Mỗi lần connector gửi yêu cầu xử lý | Retry có thể làm số này tăng mà không có công việc mới |
| Message trong queue | Đơn vị truyền tải của hạ tầng hàng đợi | Có thể có bản sao, message đang xử lý hoặc công việc ngoài queue |

Trong phần còn lại, đơn vị chính là **công việc logic**. Mỗi công việc có một định danh ổn định qua các lần thử lại. Các lần thử có `attempt_id` riêng để điều tra, nhưng không được biến thành nhiều công việc tồn khác nhau.

Định danh công việc cần phân biệt đúng tenant, danh tính, hệ thống đích, thao tác, tài nguyên quyền và phiên bản thay đổi. Chỉ dùng cặp người dùng–ứng dụng là chưa đủ: một người có thể đồng thời cần đổi thuộc tính và bị gỡ một quyền cụ thể tại cùng ứng dụng.

### 2.2. Phạm vi bắt đầu và kết thúc

Một cách định nghĩa hữu ích là bắt đầu tính backlog thực thi từ khi thay đổi đã được chấp thuận và được tiếp nhận bền vững để xử lý. Yêu cầu còn chờ người quản lý phê duyệt được đo bằng backlog phê duyệt riêng. Nếu tổ chức chọn bắt đầu từ khi người dùng gửi yêu cầu, cần ghi rõ đó là thời gian toàn quy trình, không so sánh trực tiếp với độ trễ thực thi của định nghĩa trước.

Công việc chỉ được coi hoàn tất khi đạt điều kiện đã công bố. Ví dụ, điều kiện của thao tác gỡ nhóm có thể là connector báo thành công và kiểm tra trạng thái đích xác nhận người dùng không còn trong nhóm. Mức xác minh phải phù hợp khả năng API và rủi ro; không tự coi mọi connector đều cung cấp cùng một mức bảo đảm.

Việc lấy message ra khỏi queue, gửi xong HTTP request hoặc nhận xác nhận tiếp nhận chưa nhất thiết đáp ứng điều kiện hoàn tất. Với API bất đồng bộ, HTTP `202 Accepted` chỉ cho biết yêu cầu được chấp nhận xử lý, chưa bảo đảm xử lý xong. Cần dùng cơ chế theo dõi kết quả mà API cung cấp. [RFC 9110, mục 15.3.3 — 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3).

Đối với thu hồi quyền, cần nêu rõ trạng thái nào được xác minh: tài khoản đã disable, thành viên nhóm đã bị gỡ hay quyền cụ thể đã bị xóa. Những điều này không tự chứng minh mọi phiên đăng nhập hoặc token đã phát hành đều mất hiệu lực ngay. Nếu quy trình yêu cầu thu hồi phiên, phải theo dõi nghĩa vụ đó riêng và xác minh theo khả năng của hệ thống đích.

## 3. Đếm cả phần công việc không còn nằm trong queue chính

### 3.1. Mô hình trạng thái minh họa

| Trạng thái logic | Ý nghĩa | Còn trong backlog chưa giải quyết? |
|---|---|---|
| `READY` | Đủ điều kiện, đang chờ được xử lý | Có |
| `RUNNING` | Đang thực thi hoặc chờ xác minh kết quả | Có |
| `RETRY_WAIT` | Chờ đến thời điểm được thử lại | Có |
| `BLOCKED` | Chờ sửa dữ liệu, quyền connector hoặc phụ thuộc | Có |
| `DEAD_LETTER` | Hết retry tự động, đang chờ xử lý có trách nhiệm | Có |
| `SUCCEEDED_VERIFIED` | Đã đạt điều kiện hoàn tất | Không |
| `CANCELLED_VALIDATED` | Có quyết định hủy hợp lệ và lưu bằng chứng | Không |
| `SUPERSEDED_VALIDATED` | Đã được thay thế hợp lệ bằng trạng thái hoặc công việc mới | Không |

Mỗi công việc thuộc đúng một trạng thái tại một thời điểm. Trong mô hình này:

```text
Backlog chưa giải quyết = READY + RUNNING + RETRY_WAIT + BLOCKED + DEAD_LETTER
```

Nếu sản phẩm gọi một trạng thái là `FAILED`, cần xác định công việc đã thật sự được giải quyết hay chỉ ngừng thử tự động. Đưa một yêu cầu thu hồi quyền vào dead-letter queue không làm quyền ở đích tự biến mất. Vì thế, dashboard cần giữ khả năng nhìn thấy nghĩa vụ còn tồn, kể cả khi bộ lập lịch không tiếp tục chạy nó.

Không cộng thêm tổng message queue vào tổng công việc logic: hai nguồn có thể phản ánh cùng công việc và gây đếm trùng. Queue metrics dùng để hiểu hạ tầng, còn trạng thái công việc bền vững dùng để theo dõi nghĩa vụ nghiệp vụ.

### 3.2. Cân bằng lượng vào và lượng ra

Với cùng phạm vi và cùng đơn vị công việc:

```text
B_cuối = B_đầu + A - D - C

A: công việc logic mới được tiếp nhận trong khoảng đo
D: công việc đạt điều kiện hoàn tất trong khoảng đo
C: công việc được hủy hoặc thay thế hợp lệ trong khoảng đo
```

Retry cùng công việc chỉ chuyển trạng thái bên trong backlog, không làm tăng `A`. Khi một công việc cũ được thay thế bằng công việc mới, ghi nhận rõ việc đóng công việc cũ và tiếp nhận công việc mới; không xóa lịch sử để làm giảm con số tồn.

Nếu hệ thống cho phép mở lại công việc đã đóng, phải có khoản tăng tương ứng hoặc tạo một công việc mới theo contract. Công thức cân bằng chỉ có ích khi mọi chuyển tiếp qua ranh giới backlog đều được ghi nhận đầy đủ.

Ví dụ, đầu giờ có 120 công việc, trong giờ nhận 80 công việc mới, hoàn tất 60 và thay thế hợp lệ 10:

```text
B_cuối = 120 + 80 - 60 - 10 = 130 công việc
```

Backlog tăng 10 công việc. Nếu chỉ nhìn 60 lần hoàn tất, người vận hành có thể thấy hệ thống vẫn hoạt động tốt mà bỏ qua việc lượng tồn đang lớn dần. Ngược lại, backlog giảm do hủy yêu cầu cần được phân biệt với backlog giảm nhờ thực thi thành công.

## 4. Bộ chỉ số cần quan sát cùng nhau

### 4.1. Số lượng, tuổi và tiến độ

| Chỉ số | Cách hiểu | Tác dụng |
|---|---|---|
| Backlog chưa giải quyết | Số công việc logic đang ở các trạng thái còn tồn | Quan sát quy mô công việc chưa xong |
| Backlog theo trạng thái | Tách ready, running, retry, blocked, dead-letter | Xác định công việc kẹt ở giai đoạn nào |
| Tuổi công việc tồn | Thời điểm hiện tại trừ thời điểm tiếp nhận ban đầu | Phát hiện yêu cầu bị bỏ quên |
| Công việc quá hạn | Công việc chưa giải quyết có deadline đã qua | Ưu tiên theo cam kết nghiệp vụ |
| Tốc độ tiếp nhận | Công việc logic mới trên một đơn vị thời gian | Đo tải đi vào |
| Tốc độ hoàn tất | Công việc đạt điều kiện hoàn tất trên một đơn vị thời gian | Đo khả năng giải quyết thực tế |
| Tỷ lệ hoặc số lượng retry | Lần thử lại và công việc phải thử lại | Phát hiện lỗi lặp, giới hạn tốc độ hoặc quá tải |
| Độ trễ hoàn tất | Thời điểm hoàn tất trừ thời điểm tiếp nhận | Đo thời gian của các công việc đã xong |
| Độ mới dữ liệu nguồn | Thời điểm nguồn được đọc hoặc đồng bộ thành công gần nhất | Phát hiện công việc chưa được đưa vào pipeline |

Tuổi công việc phải tính từ lúc tiếp nhận ban đầu. Nếu mỗi lần retry đều đặt lại mốc tuổi, một yêu cầu thất bại suốt ba ngày có thể luôn trông như mới chờ một phút.

Nên theo dõi công việc lâu nhất và phân bố tuổi, chẳng hạn dưới 5 phút, 5–15 phút, 15–60 phút và trên 60 phút. Các khoảng này chỉ là ví dụ; cần thiết kế theo mục tiêu dịch vụ và loại thao tác thực tế.

Độ trễ của công việc đã hoàn tất và tuổi của công việc đang tồn là hai góc nhìn bổ sung. Chỉ đo percentile của công việc hoàn tất có thể làm số liệu đẹp trong khi một nhóm công việc khó vẫn mắc kẹt. Cũng không nên dùng tuổi backlog hiện tại như thể đó là độ trễ hoàn tất đã biết.

### 4.2. Phân tách theo rủi ro và hệ thống đích

Tối thiểu cần có khả năng xem riêng thao tác cấp mới, thay đổi và thu hồi; nhóm tài khoản người dùng, tài khoản đặc quyền và danh tính workload; cùng từng hệ thống đích hoặc connector.

Backlog gỡ quyền trên ứng dụng nhạy cảm có thể cần phản ứng ngay cả khi chỉ có một công việc. Ngược lại, một đợt onboarding đã được lên kế hoạch có thể tạo backlog cấp mới lớn nhưng vẫn nằm trong thời hạn chấp nhận. Số lượng không thay thế được bối cảnh rủi ro.

Với hệ thống nhiều tenant, phân tích phải giữ đúng ranh giới tenant và quyền người xem. Không dùng email, tên tài khoản, `work_id` hoặc token làm label metric có số lượng giá trị tăng theo từng công việc. Có thể giữ định danh công việc trong log hoặc kho truy vấn được kiểm soát truy cập, còn metric tổng hợp theo một tập chiều có giới hạn.

## 5. Dữ liệu và truy vấn minh họa

### 5.1. Một bản ghi công việc

```json
{
  "work_id": "work-demo-1048",
  "request_id": "lifecycle-demo-73",
  "tenant_id": "tenant-demo",
  "subject_key": "subject-pseudo-42",
  "target_system": "finance-app",
  "operation": "remove_group_membership",
  "desired_version": 19,
  "state": "RETRY_WAIT",
  "accepted_at": "2026-10-12T02:00:00Z",
  "deadline_at": "2026-10-12T02:10:00Z",
  "attempt_count": 3,
  "next_attempt_at": "2026-10-12T02:08:00Z",
  "last_error_class": "target_rate_limit",
  "environment": "production"
}
```

`accepted_at` giữ nguyên qua retry. `desired_version` cho phép đối chiếu công việc với phiên bản trạng thái mong muốn; bản thân field này chưa tự bảo đảm thứ tự thực thi. Bộ xử lý còn cần kiểm tra phiên bản hiện hành và cơ chế điều phối phù hợp trước khi áp dụng thay đổi.

Không lưu credential connector, access token, mật khẩu hoặc toàn bộ payload chứa dữ liệu nhạy cảm trong metric hay thông báo cảnh báo. Log chi tiết chỉ chứa dữ liệu cần thiết và phải được bảo vệ theo quyền truy cập, mục đích và thời gian lưu phù hợp.

### 5.2. Truy vấn snapshot backlog

Truy vấn PostgreSQL sau giả định bảng `provisioning_work` có đúng một bản ghi trạng thái hiện hành cho mỗi `work_id`. Các cột thời gian sử dụng kiểu có thông tin múi giờ. Đây là ví dụ đọc dữ liệu giám sát, không phải lệnh thực thi provisioning.

```sql
SELECT
    target_system,
    operation,
    COUNT(*) AS unresolved_work,
    COUNT(*) FILTER (WHERE state = 'READY') AS ready_work,
    COUNT(*) FILTER (WHERE state = 'RUNNING') AS running_work,
    COUNT(*) FILTER (WHERE state = 'RETRY_WAIT') AS retry_work,
    COUNT(*) FILTER (WHERE state = 'BLOCKED') AS blocked_work,
    COUNT(*) FILTER (WHERE state = 'DEAD_LETTER') AS dead_letter_work,
    MAX(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - accepted_at)))
        AS oldest_age_seconds,
    COUNT(*) FILTER (
        WHERE deadline_at IS NOT NULL
          AND deadline_at < CURRENT_TIMESTAMP
    ) AS overdue_work
FROM provisioning_work
WHERE environment = 'production'
  AND state IN (
      'READY', 'RUNNING', 'RETRY_WAIT', 'BLOCKED', 'DEAD_LETTER'
  )
GROUP BY target_system, operation;
```

Nếu bảng nguồn là lịch sử sự kiện thay vì trạng thái hiện hành, phải dựng trạng thái mới nhất của từng công việc trước khi đếm. Đếm mọi sự kiện `RETRY_WAIT` trong lịch sử sẽ biến số lần retry thành số công việc tồn.

Truy vấn trên không trả dòng cho nhóm không có công việc tồn. Tầng hiển thị cần kết hợp danh sách connector đang được giám sát và tín hiệu sức khỏe thu thập để phân biệt giá trị 0 với không có dữ liệu. Trong hệ thống đa tenant, điều kiện truy vấn và phân quyền dữ liệu còn phải giới hạn đúng tenant được phép xem.

Một sản phẩm thực tế có thể có log với ngữ nghĩa khác mô hình trên. Chẳng hạn, Microsoft Entra provisioning logs thể hiện danh tính, hành động, hệ thống nguồn, hệ thống đích và trạng thái sự kiện. Cần ánh xạ các thông tin đó vào định nghĩa công việc của tổ chức, thay vì coi một dòng log tự động tương đương một nghĩa vụ còn tồn. [Microsoft Learn — User provisioning logs](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-provisioning-logs).

## 6. Đọc một tình huống vận hành

Tiếp tục ví dụ có 130 công việc cuối giờ. Snapshot được phân loại như sau:

| Trạng thái | Số công việc |
|---|---:|
| READY | 50 |
| RUNNING | 10 |
| RETRY_WAIT | 35 |
| BLOCKED | 20 |
| DEAD_LETTER | 15 |
| Tổng chưa giải quyết | 130 |

Giả sử trong tổng này có 8 công việc thu hồi quyền đã quá hạn. Đây là một lát cắt theo thao tác và thời hạn, không phải 8 công việc cần cộng thêm vào 130. Việc phân tích nên ưu tiên xác định tài khoản, quyền và ứng dụng chịu ảnh hưởng của nhóm quá hạn đó.

Nếu đội vận hành chỉ tăng số executor, 35 công việc chờ retry vì giới hạn tốc độ có thể tiếp tục bị từ chối. 20 công việc bị block bởi mapping thuộc tính sai cũng không được giải quyết bằng thêm tài nguyên. Cần phân biệt thiếu năng lực xử lý với lỗi dữ liệu, lỗi quyền hoặc hạn chế của hệ thống đích.

Trong một mô hình giản lược, nếu có 130 công việc tồn, hệ thống hoàn tất 30 công việc/phút và nhận mới 20 công việc/phút, tốc độ giảm ròng là 10 công việc/phút. Thời gian xả phần tồn hiện tại ước tính là:

```text
Thời gian xả tồn ≈ 130 / (30 - 20) = 13 phút
```

Ước tính này chỉ có ý nghĩa khi năng lực xử lý và lượng vào tương đối ổn định, công việc có đặc điểm tương đương và không có nhóm bị block. Không thể dùng nó để hứa thời gian khôi phục cho các công việc dead-letter hoặc một connector đang hỏng. Khi tốc độ hoàn tất không lớn hơn tốc độ nhận mới, không có thời gian xả tồn hữu hạn theo mô hình này.

## 7. Cảnh báo và điều tra

### 7.1. Thiết kế cảnh báo theo tác động

Một bộ cảnh báo có thể bao gồm:

- Công việc thu hồi quyền quan trọng đã quá deadline theo chính sách của ứng dụng.
- Tuổi công việc lâu nhất vượt thời gian cho phép của nhóm thao tác tương ứng.
- Backlog tăng liên tục trong khi tốc độ hoàn tất thấp hơn tốc độ tiếp nhận.
- Có công việc tồn nhưng không có tiến độ hoàn tất trong khoảng theo dõi đã định nghĩa.
- Số công việc blocked hoặc dead-letter vượt mức cần can thiệp.
- Nguồn nhân sự, directory hoặc connector không còn đồng bộ thành công dù backlog hiển thị thấp.

Các điều kiện cần gắn với owner, hệ thống đích, tác động và đường dẫn điều tra có kiểm soát quyền. Không đặt một ngưỡng chung cho mọi ứng dụng rồi coi số lượng thấp hơn ngưỡng là an toàn. Sự kiện onboarding theo lô có thể được chú thích trên dashboard, nhưng không nên làm mất cảnh báo về thu hồi quyền quá hạn.

### 7.2. Liên kết tín hiệu với giả thuyết

| Quan sát | Giả thuyết cần kiểm tra | Hướng điều tra |
|---|---|---|
| READY tăng, executor ít hoạt động | Consumer dừng hoặc thiếu năng lực xử lý | Heartbeat, cấu hình consumer, lease và lịch chạy |
| RETRY_WAIT tăng cùng lỗi giới hạn tốc độ | Gửi vượt khả năng hoặc quota của đích | Tốc độ gửi, giới hạn theo tenant, lịch retry và backoff |
| BLOCKED tăng sau thay đổi mapping | Dữ liệu đầu vào không phù hợp contract đích | Phiên bản mapping, thuộc tính bắt buộc và lỗi validation |
| Lỗi xác thực connector trên nhiều công việc | Credential hết hạn hoặc quyền tích hợp thay đổi | Tình trạng credential và quyền tối thiểu cần cho thao tác |
| Backlog bằng 0 nhưng nhân viên mới không có tài khoản | Pipeline nguồn không phát hiện hoặc chưa tiếp nhận thay đổi | Watermark, lần đọc nguồn gần nhất, bộ lọc phạm vi và đối soát |
| Chỉ một hệ thống đích có tuổi backlog tăng | Connector hoặc API của hệ thống đó gặp vấn đề | Sức khỏe đích, log tương quan và trạng thái job |

Các mẫu này định hướng điều tra, không tự chứng minh nguyên nhân. Một số nền tảng còn chủ động giảm tần suất xử lý khi tích hợp không khỏe. Microsoft Entra, ví dụ, có trạng thái quarantine cho provisioning job khi các lời gọi đến hệ thống đích liên tục thất bại; đây là tín hiệu cần quan sát cùng lượng tồn. [Microsoft Learn — Application provisioning in quarantine status](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/application-provisioning-quarantine-status).

### 7.3. Khôi phục mà vẫn bảo toàn quyết định quyền

Trước khi replay công việc, cần xác nhận nguyên nhân đã được xử lý và trạng thái mong muốn vẫn còn hiệu lực. Một công việc cấp quyền từ hôm trước có thể đã lỗi thời sau sự kiện nghỉ việc hôm nay. Thực thi lại mù quáng có thể cấp lại quyền vừa bị thu hồi.

Đối với timeout, trạng thái ở đích có thể chưa rõ: request đã áp dụng nhưng phản hồi bị mất, hoặc request chưa áp dụng. Cần đối chiếu hoặc sử dụng cơ chế idempotency mà API hỗ trợ để tránh tạo tài khoản hay quan hệ quyền trùng. Không mặc định một idempotency key tùy ý sẽ được mọi API đích hiểu và thực thi.

Một trình tự khôi phục hợp lý là xác định nhóm công việc bị ảnh hưởng, kiểm tra yêu cầu hiện hành, sửa lỗi connector hoặc dữ liệu, chạy lại có giới hạn, rồi xác minh trạng thái đích. Với thu hồi quyền khẩn cấp, biện pháp thủ công hoặc kiểm soát tạm thời phải theo quy trình đã được chấp thuận và vẫn cần đối soát lại với hệ thống IAM.

Không xóa queue hoặc đánh dấu thành công hàng loạt để làm backlog giảm. Nếu cần hủy hoặc thay thế công việc, lưu lý do, người hoặc quy tắc quyết định, và liên kết tới thay đổi hiện hành. Công việc hết retry vẫn phải có chủ thể chịu trách nhiệm giải quyết.

## 8. Tự kiểm tra cách hiểu

**Queue chính chỉ còn 5 message, nhưng có 40 công việc ở dead-letter. Backlog có phải là 5 không?**

Không theo định nghĩa của bài. Cần đếm công việc logic chưa giải quyết ở mọi trạng thái liên quan, khử trùng giữa các nguồn và bao gồm cả công việc đang thực thi hoặc bị block. Queue chính chỉ phản ánh một phần của luồng xử lý.

**Một công việc được retry 12 lần có tạo 12 công việc mới không?**

Không. Đó là một công việc với nhiều lần thử. Số lần thử giúp hiểu tải và lỗi, còn backlog vẫn tính một nghĩa vụ chưa giải quyết.

**Backlog giảm từ 1.000 xuống 0 có đủ để khẳng định quyền đã đúng ở mọi ứng dụng không?**

Chưa đủ. Phải biết backlog giảm do hoàn tất được xác minh hay do hủy, thay thế hoặc mất dữ liệu. Cũng cần kiểm tra pipeline nguồn có tiếp nhận đầy đủ thay đổi và đối soát trạng thái thực tế tại các hệ thống đích.

**Tại sao một công việc thu hồi quyền quá hạn có thể quan trọng hơn hàng trăm công việc tạo mới?**

Vì mức ưu tiên còn phụ thuộc quyền đang tồn tại, độ nhạy của ứng dụng và tác động của việc chậm thu hồi. Quan sát provisioning backlog phải kết hợp số lượng, tuổi, deadline và rủi ro để giúp đội IAM đưa trạng thái thực tế về đúng quyết định truy cập hiện hành.
