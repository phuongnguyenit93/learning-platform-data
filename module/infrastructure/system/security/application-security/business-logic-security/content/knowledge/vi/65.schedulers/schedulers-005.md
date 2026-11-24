# Schedule overlap — Kiểm soát các lần chạy lịch chồng lấn

> Bài học thuộc chương **Schedulers** của module **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**. Trọng tâm là giữ đúng quy tắc nghiệp vụ khi nhiều lần kích hoạt, nhiều worker hoặc nhiều lịch cùng tác động lên một đối tượng: không vượt quyền, không bỏ qua phê duyệt, không tạo hóa đơn hay thu tiền trùng.

## 1. Schedule overlap là gì?

**Schedule overlap** xảy ra khi các lần thực thi có khoảng thời gian xử lý giao nhau. Ví dụ, lịch chạy mỗi phút nhưng một lần xử lý mất ba phút; lần tiếp theo được kích hoạt khi lần trước vẫn chưa hoàn tất.

Trong bảo mật logic nghiệp vụ, vấn đề quan trọng hơn là các lần chạy có cạnh tranh trên cùng một nghĩa vụ hay tài nguyên không. Hai job chạy đồng thời nhưng xử lý hai tenant độc lập có thể hoàn toàn hợp lệ. Hai job được tạo bởi hai lịch khác nhau lại có thể cùng thu tiền cho một hóa đơn.

Cần phân biệt ba dạng:

| Dạng chồng lấn | Ví dụ | Nguy cơ |
|---|---|---|
| Cùng một lần lịch bị thực thi nhiều lần | Hai replica cùng nhận một occurrence | Cùng công việc được xử lý lặp |
| Hai occurrence khác nhau cùng đang chạy | Lần 09:00 chưa xong thì lần 09:01 bắt đầu | Cạnh tranh trên dữ liệu hoặc cùng xử lý một đối tượng |
| Các nguồn kích hoạt khác nhau cùng ý định nghiệp vụ | Lịch định kỳ, retry và nút “chạy ngay” cùng thu một hóa đơn | Khóa theo riêng lịch không bao phủ hết đường gây tác động |

Một scheduler chỉ chạy một callback mỗi lần trong một tiến trình vẫn chưa đủ để bảo vệ nghiệp vụ toàn hệ thống. Khi có nhiều replica, worker, lịch hoặc công cụ quản trị, ranh giới cần bảo vệ phải nằm ở nơi quyết định và ghi nhận tác động nghiệp vụ.

## 2. Vì sao đây là một vấn đề bảo mật nghiệp vụ?

Giả sử hệ thống có lịch thu phí thuê bao. Mỗi lần chạy tìm các hóa đơn đến hạn rồi gửi lệnh thanh toán.

Một người có thể tạo hoặc sửa lịch với tần suất rất cao, gọi “chạy ngay” nhiều lần, kích hoạt retry trong lúc lần trước chưa rõ kết quả, hoặc tạo hai lịch cùng chọn một nhóm thuê bao. Nếu mỗi lần chạy đều tin rằng mình là lần duy nhất, họ có thể tạo ra:

- Hai hóa đơn cho cùng thuê bao và cùng kỳ.
- Hai lệnh thu cho một nghĩa vụ thanh toán.
- Hai quyết định đều nhìn thấy hạn mức còn đủ rồi cùng sử dụng nó.
- Việc thực thi theo phê duyệt cũ sau khi giá trị tiền hoặc đối tượng đã đổi.
- Kết quả bị worker cũ ghi đè sau khi quyền thực thi đã được bàn giao.

Ngay cả khi người dùng không trực tiếp điều khiển lịch, message trùng, tiến trình khởi động lại, mạng chậm và thao tác hỗ trợ thủ công vẫn có thể tạo cùng tình huống.

Bảo vệ overlap cần dựa trên bất biến mà hệ thống phải giữ, thay vì dựa vào giả định rằng các lần kích hoạt “thường cách nhau đủ lâu”.

### Mô hình tấn công tối thiểu

Khi thiết kế, nên xét actor có thể:

1. Yêu cầu thực thi thủ công trong phạm vi quyền của họ.
2. Gửi lại request hoặc làm phát sinh nhiều message tương đương.
3. Đề nghị đổi tần suất, vùng thời gian hoặc khoảng backfill nếu hệ thống cho phép.
4. Tạo nhiều lịch có cùng bộ chọn đối tượng.
5. Tận dụng thời gian xử lý dài, timeout hoặc worker mất lease để tạo cạnh tranh.

Không cần actor có quyền quản trị toàn hệ thống thì lỗ hổng overlap mới bị khai thác. Một quyền hợp lệ nhưng được dùng theo cách hệ thống không dự tính có thể đủ để phá quy tắc nghiệp vụ.

## 3. Bắt đầu bằng business invariants

Với ví dụ thu phí thuê bao, có thể xác định:

- Một thuê bao có một nghĩa vụ lập hóa đơn chính cho một kỳ theo chính sách đã chọn. Hóa đơn điều chỉnh, nếu có, là nghiệp vụ riêng có quy tắc rõ ràng.
- Cùng một ý định thu tiền không tạo nhiều hiệu ứng chỉ vì được kích hoạt từ nhiều nguồn.
- Tổng phần đã thu và phần đang giữ chỗ cho các lần thu chưa ngã ngũ không vượt giới hạn được phép.
- Actor hoặc ủy quyền thực thi có hiệu lực đối với đúng tenant và đúng đối tượng.
- Nội dung đã được phê duyệt vẫn khớp với nội dung chuẩn bị thực thi.
- Một worker hết quyền sở hữu không được tiếp tục cấp phép mới hoặc ghi đè trạng thái điều phối.

Một bất biến tiền tệ minh họa:

```text
confirmedCaptures + reservedCaptures <= authorizedChargeLimit
```

Trong đó, `reservedCaptures` bao gồm phần nghĩa vụ dành cho các lệnh đã cấp phép hoặc đã gửi nhưng chưa xác định kết quả. Hạn mức và số tiền lấy từ dữ liệu nghiệp vụ có thẩm quyền.

Không tự trừ tiền đã hoàn khỏi `confirmedCaptures` để tạo quyền thu lại. Việc một khoản hoàn tiền có mở ra nghĩa vụ thu mới hay không phải được quy định riêng.

### Ba lớp bảo vệ có mục đích khác nhau

```text
Kiểm soát lịch:
  Giới hạn số lần chạy và cách xử lý occurrence chồng lấn.

Kiểm soát tài nguyên:
  Tuần tự hóa hoặc phối hợp các thao tác cạnh tranh trên cùng đối tượng.

Idempotency nghiệp vụ:
  Cùng một ý định được nhận lại vẫn không tạo thêm hiệu ứng trái phép.
```

Khóa lịch giúp giảm cạnh tranh, nhưng không tự bảo đảm một hóa đơn chỉ được thu đúng số lần. Idempotency cũng không thay thế kiểm tra hạn mức cho hai ý định nghiệp vụ khác nhau cùng dùng một số dư.

## 4. Chọn chính sách overlap theo ý nghĩa nghiệp vụ

Các chính sách dưới đây là khái niệm thiết kế. Tên và hành vi thực tế phải được mô tả rõ trong hệ thống cụ thể.

| Chính sách | Cách xử lý lần kích hoạt mới | Phù hợp khi | Điều cần kiểm soát |
|---|---|---|---|
| Cho phép chạy đồng thời | Nhận thêm lần chạy | Dữ liệu độc lập hoặc thao tác có kiểm soát cạnh tranh phù hợp | Quyền, phạm vi tài nguyên và idempotency vẫn bắt buộc |
| Bỏ qua khi đang bận | Ghi nhận không chạy occurrence mới | Một lần quét sau có thể bao phủ công việc còn lại | Không báo occurrence bị bỏ là đã xử lý thành công |
| Xếp hàng | Giữ từng occurrence để chạy lần lượt | Mỗi occurrence mang nghĩa vụ riêng | Backlog, giới hạn thời gian và hiệu lực phê duyệt |
| Gộp lần chờ | Hợp nhất nhiều kích hoạt thành một lần xử lý | Chỉ cần cập nhật trạng thái mới nhất hoặc quét một khoảng đã xác định | Không làm mất nghĩa vụ độc lập của từng kỳ |
| Yêu cầu thay thế lần đang chạy | Đề nghị dừng cũ rồi chuyển sang mới | Kết quả cũ có thể bị thay thế theo hợp đồng rõ ràng | Hủy là một giao thức; không coi tiến trình cũ đã ngừng ngay |

### 4.1. Bỏ qua occurrence không đồng nghĩa bỏ qua nghĩa vụ

Một lịch quét hóa đơn mỗi phút có thể bỏ một lần quét khi lần trước còn chạy, miễn lần tiếp theo vẫn tìm được những hóa đơn chưa được xử lý. Điều này khác với bỏ vĩnh viễn một kỳ tính phí mà hệ thống có nghĩa vụ phải xử lý.

Nên ghi trạng thái như `SKIPPED_DUE_TO_OVERLAP`, kèm tham chiếu lần chạy đang giữ quyền. Không ghi `SUCCEEDED` cho một occurrence chưa thực hiện công việc.

### 4.2. Gộp không được làm sai tập công việc

Có thể gộp mười tín hiệu “hãy quét các hóa đơn đến hạn” thành một lần quét. Không thể mặc nhiên gộp mười kỳ hợp đồng khác nhau thành một khoản tiền nếu nghiệp vụ không cho phép.

Một lần gộp cần xác định khoảng dữ liệu, watermark hoặc tập kỳ đã được bao phủ. Việc đẩy watermark vượt quá phần đã commit có thể làm các nghĩa vụ bị bỏ sót vĩnh viễn.

### 4.3. Thay thế không phải rollback

Nếu lần chạy cũ đã gửi tiền hoặc thông báo, khởi động lần mới không xóa các tác động đó. Cần ngăn cấp phép thêm, theo dõi công việc đang chạy và đối soát kết quả trước khi quyết định tiếp tục.

Với công việc có hiệu ứng không thể thu hồi, chính sách xếp hàng hoặc phối hợp theo đối tượng thường dễ xác định hơn một lời hứa “lần mới luôn thay thế lần cũ”.

## 5. Phân biệt thời điểm kích hoạt với kỳ nghiệp vụ

Một occurrence là một lần lịch dự kiến được kích hoạt. Nó có thời điểm được lập kế hoạch, còn lúc worker thật sự bắt đầu có thể muộn hơn nhiều.

```text
scheduledFor: Thời điểm dự kiến của occurrence
startedAt:   Thời điểm bắt đầu xử lý thực tế
businessPeriod: Kỳ nghiệp vụ mà lần xử lý đang giải quyết
```

Không dùng `startedAt` hoặc “ngày hiện tại” làm căn cứ duy nhất xác định kỳ. Một lần chạy bị trễ qua nửa đêm có thể vẫn phải xử lý kỳ trước.

### 5.1. Vùng thời gian và giờ mùa hè

Lịch theo giờ địa phương có thể gặp thời điểm không tồn tại hoặc xuất hiện hai lần ở nơi áp dụng đổi giờ mùa hè. Cần quy định cách giải quyết và lưu occurrence đã được xác định, thay vì để mỗi replica tự diễn giải khác nhau.

Thời điểm UTC giúp định danh một instant rõ ràng, nhưng kỳ tính phí vẫn có thể dựa trên vùng thời gian của hợp đồng. Đổi sang UTC không tự giải quyết ý nghĩa của một kỳ nghiệp vụ hoặc làm đồng hồ các máy đồng bộ tuyệt đối.

### 5.2. Misfire và chạy bù

Khi scheduler dừng lâu, có thể xuất hiện nhiều occurrence bị lỡ. Chính sách chạy bù cần trả lời:

- Chạy từng occurrence hay chỉ một lần tổng hợp?
- Những kỳ nghiệp vụ nào thật sự còn nghĩa vụ?
- Giới hạn số lượng, giá trị và tốc độ xử lý là bao nhiêu?
- Các quyền, phê duyệt và dữ liệu đầu vào còn hợp lệ không?

Không biến “đã lỡ 60 lần quét” thành “được phép thu cùng hóa đơn 60 lần”. Nguồn kích hoạt chỉ yêu cầu kiểm tra công việc; quyền tạo hiệu ứng phải dựa trên trạng thái nghiệp vụ.

Đổi tần suất hoặc vùng thời gian cũng không được ngầm tạo lại một nghĩa vụ đã hoàn tất. Mọi thay đổi lịch cần giữ được liên kết với những kỳ và thao tác đã được ghi nhận.

## 6. Chọn đúng khóa: occurrence, tài nguyên và ý định nghiệp vụ

Các khóa này phục vụ các câu hỏi khác nhau:

| Loại khóa | Ví dụ khái niệm | Câu hỏi được trả lời |
|---|---|---|
| Khóa occurrence | Tenant, schedule, revision, thời điểm dự kiến đã được xác định | Đây có phải cùng một lần kích hoạt bị nhận lại không? |
| Khóa phối hợp tài nguyên | Tenant, đối tượng hoặc miền nghiệp vụ có xung đột | Những thao tác nào không được cùng quyết định trên tài nguyên này? |
| Khóa idempotency nghiệp vụ | Tenant, thuê bao, loại nghĩa vụ, kỳ nghiệp vụ | Đây có phải cùng một ý định đã hoặc đang được thực hiện không? |
| Attempt ID | Một lần thử cụ thể của thao tác | Lần thử nào đã gửi và nhận kết quả gì? |

### 6.1. Không đưa yếu tố thay đổi tùy lần chạy vào khóa nghiệp vụ

Ví dụ cho nghĩa vụ lập hóa đơn chính:

```text
businessKey = (
    tenantId,
    subscriptionId,
    operationType = PRIMARY_BILLING,
    businessPeriod
)
```

Các thành phần được chuẩn hóa và lấy từ dữ liệu có thẩm quyền. Kỳ nghiệp vụ phải có định nghĩa thống nhất, không chỉ là một chuỗi ngày do client tự chọn.

Không thêm `attemptId`, thời điểm bắt đầu, tên worker, nguồn kích hoạt hoặc schedule revision vào khóa này chỉ để tránh xung đột. Nếu cùng nghĩa vụ được kích hoạt bằng lịch mới hoặc nút “chạy ngay”, nó vẫn cần liên kết với thao tác gốc.

Schedule revision hữu ích cho lịch sử điều khiển. Nó không tự tạo quyền lập hóa đơn hoặc thu tiền lại.

### 6.2. Khóa theo lịch có thể quá hẹp

```text
Schedule A -> thu hóa đơn I-81
Schedule B -> thu hóa đơn I-81
Manual run -> thu hóa đơn I-81
```

Ba nguồn có thể giữ ba khóa lịch khác nhau mà vẫn cùng gây tác động lên `I-81`. Điểm cấp phép thu phải phối hợp theo hóa đơn hoặc miền số dư phù hợp.

Ngược lại, khóa toàn hệ thống cho mọi tenant có thể quá rộng: làm giảm khả năng phục vụ và tạo điều kiện gây nghẽn bằng một job chậm. Nên chọn phạm vi nhỏ nhất vẫn bao phủ toàn bộ thao tác có khả năng phá cùng bất biến.

Nếu bất biến nằm trên số dư chung của một tài khoản, khóa từng hóa đơn riêng lẻ có thể chưa đủ. Hai hóa đơn khác nhau vẫn cạnh tranh trên cùng hạn mức; khi đó phải phối hợp thêm tại tài khoản hoặc dùng cập nhật số dư nguyên tử tương ứng.

### 6.3. Bộ chọn tài nguyên không được do request tùy ý quyết định

Nếu client được chọn `lockKey`, họ có thể đổi khóa để chạy song song trên cùng đối tượng. Khóa phải được suy ra ở phía máy chủ từ tenant, tài nguyên và loại thao tác đã được kiểm tra quyền.

Khi một lần chạy cần nhiều khóa, xác định thứ tự lấy khóa thống nhất để giảm deadlock. Nếu cần thu hẹp hoặc chia miền khóa để tăng thông lượng, phải kiểm tra rằng các bất biến liên quan vẫn được bảo vệ.

## 7. Lease và fencing: tránh worker cũ tiếp tục có quyền

### 7.1. Lease không chứng minh tiến trình cũ đã chết

Một worker nhận lease trong thời hạn nhất định. Nếu xử lý chậm, bị ngừng tạm hoặc mất kết nối, lease có thể hết hạn trong khi worker vẫn còn hoạt động.

```text
T0: Worker A nhận lease.
T1: A bị treo tạm thời hoặc mất kết nối.
T2: Lease hết hạn; worker B được quyền tiếp quản.
T3: A hoạt động lại và tiếp tục từ dữ liệu cũ.
```

Chỉ tăng TTL lớn hơn thời gian chạy thông thường không bảo đảm đúng: thời gian xử lý có thể vượt dự kiến, heartbeat có thể lỗi và process có thể ngừng lâu bất thường.

### 7.2. Fencing token xác định thế hệ quyền thực thi

Một thiết kế có thể cấp số thế hệ tăng dần mỗi lần bàn giao:

```text
A: owner = worker-A, epoch = 104
B: owner = worker-B, epoch = 105
```

Các thay đổi được bảo vệ phải xác minh thế hệ hiện hành. Worker A không được cấp phép mới hoặc ghi đè trạng thái bằng epoch 104 sau khi quyền đã chuyển sang 105.

Việc kiểm tra epoch và ghi thay đổi nghiệp vụ phải được phối hợp nguyên tử tại kho dữ liệu hoặc ranh giới thực thi. Đọc epoch rồi ghi ở một bước không có điều kiện vẫn tạo khoảng hở.

Một giao thức khái niệm:

```text
Acquire:
  Atomically verify the coordination record is available or expired.
  Increment its persistent epoch.
  Record owner and expiry using the authority's time semantics.

Renew:
  Update only if owner and epoch still match.
  Do not revive a superseded ownership generation.

Release:
  Release only if owner and epoch still match.
  Do not let a delayed release remove a successor's ownership.
```

Kho phối hợp phải cung cấp các thao tác điều kiện và tính nhất quán phù hợp với bảo đảm đã hứa. Không giả định một bản sao đọc cũ hoặc một phép ghi không nguyên tử là đủ để quyết định chủ sở hữu.

Không xóa rồi tạo lại bộ đếm thế hệ về giá trị ban đầu nếu token cũ còn có thể tồn tại. Cần duy trì tính đơn điệu trong miền mà ranh giới bảo vệ sử dụng.

### 7.3. Lease không thay thế idempotency bên ngoài

Nhà cung cấp thanh toán có thể không hiểu fencing token nội bộ. Một worker cũ vẫn có thể gửi HTTP request nếu đường gửi hoặc nhà cung cấp không thực thi điều kiện tương ứng.

Vì vậy, cần giữ business operation ID ổn định, dùng cơ chế chống trùng của nhà cung cấp nếu được hỗ trợ và đối soát kết quả chưa rõ. Không mô tả fencing ở DB như một lời bảo đảm rằng không request cũ nào có thể ra mạng.

Tương tự, kết quả thành công của một attempt cũ không được bỏ qua chỉ vì worker đã mất lease. Luồng tiếp nhận kết quả được xác thực cần ghi nhận sự thật nghiệp vụ; điều đó khác với cho worker cũ tiếp tục điều phối hoặc tạo hiệu ứng mới.

## 8. Giao dịch nghiệp vụ vẫn là điểm bảo vệ quyết định

Ví dụ dưới đây dùng giả mã, không áp đặt cú pháp SQL hay thư viện khóa cụ thể.

### 8.1. Ghi nhận hoặc tìm lại nghĩa vụ kỳ

```text
resolveBillingOperation(trigger):
  BEGIN
  load authoritative schedule / manual command and execution authority
  determine tenant, subscription and canonical business period
  verify scope and approved business inputs

  create or load operation with unique business key:
      (tenant, subscription, PRIMARY_BILLING, businessPeriod)

  if an operation already exists:
      verify the new request is compatible with its recorded intent
      return its current identity and state

  persist operation and input version
  persist audit / outbox if further work is needed
  COMMIT
```

Ràng buộc duy nhất ở kho có thẩm quyền giúp hai lần chạy không cùng tạo hai bản ghi nghĩa vụ chính. Cần xử lý xung đột bằng cách nạp thao tác đã tồn tại và kiểm tra nội dung, không tự tạo khóa khác để “cho chạy tiếp”.

Hai lần kích hoạt cùng khóa nhưng khác giá hoặc loại tiền là xung đột ý định cần xem xét, không phải một retry giống hệt. Giá, giảm giá, loại tiền và phiên bản hợp đồng phải lấy từ nguồn có thẩm quyền theo chính sách kỳ đó.

Một quyết định điều chỉnh hóa đơn cần đi qua nghiệp vụ điều chỉnh đã được thiết kế. Không sửa nội dung thao tác cũ sau khi đã phát sinh hiệu ứng rồi coi các attempt trước như thuộc nội dung mới.

### 8.2. Cấp phép hiệu ứng theo đối tượng

```text
authorizeCapture(operationId, executionToken):
  BEGIN
  lock and verify the relevant coordination / ownership record
  verify executionToken is current where this token is required
  lock the business operation and relevant balance records

  verify tenant and execution authority
  verify business state and required approvals
  verify the recorded input version is still permitted

  if operation already succeeded:
      return stored result without creating another capture

  if operation is in flight or outcome is unknown:
      return tracking / reconciliation work, not a new capture

  verify confirmed + reserved amount stays within authorized limit
  reserve the permitted amount atomically
  record the authorized attempt with a stable business operation identity
  create a uniquely identified dispatch / outbox record
  COMMIT
```

Mọi đường tạo cùng hiệu ứng phải dùng các kiểm soát tương đương: lịch định kỳ, retry, API quản trị và lệnh thủ công. Một đường cập nhật trực tiếp có thể phá toàn bộ bảo đảm dù phần scheduler được khóa đúng.

Nếu dùng fencing, bước kiểm tra thế hệ và commit thay đổi phải nằm trong cơ chế phối hợp phù hợp. Đoạn giả mã không tự bảo đảm điều đó nếu được triển khai bằng hai hệ thống độc lập không có giao thức liên kết.

Thứ tự khóa cần thống nhất giữa các đường gọi. Nếu retry một giao dịch do xung đột, phải đánh giá lại trạng thái, quyền và định danh cũ thay vì tái tạo một ý định mới.

### 8.3. Outbox không làm API ngoài trở thành giao dịch DB

Outbox giúp ghi nhận công việc cần gửi cùng giao dịch với thay đổi nghiệp vụ. Dispatcher vẫn có thể gửi rồi lỗi trước khi lưu phản hồi, hoặc nhận timeout trong khi nhà cung cấp đã xử lý.

Các lần gửi lại cho cùng ý định phải giữ định danh chống trùng phù hợp. Nếu tuyến thanh toán đã được chọn cho một attempt chưa ngã ngũ, không đổi sang nhà cung cấp khác chỉ vì timeout: nhà cung cấp mới có thể không biết khóa ở nhà cung cấp cũ, dẫn tới hai lần thu.

Khi chưa xác định kết quả, thực hiện tra cứu hoặc đối soát theo hợp đồng của nhà cung cấp. Nếu họ không hỗ trợ cơ chế đủ tin cậy, giữ trạng thái chưa rõ và quy trình xử lý thích hợp; không hứa đúng một hiệu ứng ngoài hệ thống chỉ từ unique constraint nội bộ.

## 9. Quyền thực thi, phê duyệt và thay đổi lịch

Một lịch được tạo hôm qua có thể chạy khi vai trò người tạo, trạng thái hợp đồng hoặc nội dung phê duyệt đã thay đổi. Cần định nghĩa lịch chạy dựa trên quyền hiện tại của actor hay một ủy quyền nghiệp vụ riêng có phạm vi và thời hạn.

Trong cả hai trường hợp, service có quyền rộng không được mặc nhiên dùng quyền của chính nó để hợp thức hóa mọi đối tượng mà payload chỉ ra.

Trước khi tạo hiệu ứng cần kiểm tra:

- Tenant và tập đối tượng có thuộc phạm vi thực thi đã được cho phép không?
- Lịch hoặc lệnh thủ công có còn hiệu lực theo hợp đồng không?
- Giá trị, người nhận, loại tiền và hạn mức có lấy từ dữ liệu có thẩm quyền không?
- Phê duyệt có gắn với đúng phiên bản nội dung không?
- Thay đổi lịch có được phép làm tăng tần suất, mở rộng tenant hoặc tạo thêm nghĩa vụ không?

### Cạnh tranh giữa sửa lịch và lần đang chạy

Nếu một người tắt lịch, đổi vùng thời gian hoặc sửa bộ chọn trong lúc worker đang hoạt động, phải xác định thay đổi tác động lên các occurrence tương lai hay cả công việc đã được cấp phép.

Không dùng revision mới để làm biến mất lịch sử của revision cũ. Các quyết định cần ghi nhận phiên bản đã sử dụng, thời điểm cấp phép và đối tượng bị tác động.

Tắt lịch không tự hủy lệnh đã gửi. Nếu cần dừng phần còn lại, dùng một giao thức hủy có kiểm soát; nếu đã có hiệu ứng thì xử lý theo nghiệp vụ đối soát hoặc bù đắp tương ứng.

## 10. Recovery, backlog và tiến độ không làm lặp nghĩa vụ

### 10.1. Khôi phục sau khi worker dừng

Recovery nên phân loại thao tác:

| Trạng thái nghiệp vụ | Hành vi khôi phục |
|---|---|
| Chưa được cấp phép | Có thể đánh giá lại quyền, trạng thái và hạn mức để tiếp tục |
| Đã cấp phép nhưng chưa chứng minh đã gửi hay chưa | Kiểm tra attempt và khả năng có hiệu ứng; không mặc định tạo mới |
| Đã gửi, chưa rõ kết quả | Đối soát bằng định danh gốc |
| Thành công đã xác nhận | Trả hoặc dùng kết quả đã ghi, không gửi lại |
| Thất bại chắc chắn, không còn hiệu ứng có thể xuất hiện | Retry theo chính sách, vẫn giữ quan hệ với ý định gốc |

Hết lease hoặc process dừng không tự chuyển mọi mục `IN_FLIGHT` về `NEW`. Cách làm đó có thể tạo nhiều lần thu khi attempt trước vẫn đang được nhà cung cấp xử lý.

### 10.2. Watermark và checkpoint

Với lịch quét theo khoảng thời gian, checkpoint phải phản ánh phần dữ liệu đã được xử lý bền vững hoặc đã được ghi nhận đủ để tiếp tục an toàn.

Nếu đánh dấu “đã xử lý đến 10:00” trước khi công việc tương ứng được commit, sự cố có thể làm mất dữ liệu. Nếu checkpoint không được cập nhật sau khi có hiệu ứng, lần quét sau có thể gặp lại đối tượng; idempotency và trạng thái nghiệp vụ phải làm việc đó an toàn.

Không dùng một watermark duy nhất để suy ra mọi tenant hoặc partition đã hoàn tất nếu tiến độ của chúng độc lập. Cần mô hình tiến độ phù hợp với cách chia công việc.

### 10.3. Backlog cần giới hạn theo nghĩa vụ

Sau một thời gian ngừng, xếp hàng mọi tick có thể tạo lượng công việc rất lớn. Cần giới hạn tốc độ và đồng thời xác định các kỳ còn nghĩa vụ thật sự.

Đừng tăng thông lượng bằng cách bỏ kiểm tra số dư, phê duyệt hoặc idempotency. Nếu chia batch hoặc chạy song song, chia theo tài nguyên độc lập; các đối tượng dùng chung hạn mức vẫn cần kiểm soát chung.

## 11. Tình huống xuyên suốt: lịch thu phí chạy chồng lấn

### 11.1. Bối cảnh

Tenant `shop-a` có thuê bao `S-7`, kỳ nghiệp vụ `2026-11`, nghĩa vụ thu hợp lệ 900.000 VND. Hệ thống có lịch quét mỗi phút, nhưng một lần xử lý có thể mất ba phút. Ngoài ra còn có một lịch hỗ trợ và nút chạy thủ công.

Chính sách của lịch chính là bỏ occurrence mới khi lần cũ còn giữ quyền. Điều đó giúp giảm tải; kiểm soát nghiệp vụ vẫn phải bao phủ hai nguồn còn lại.

### 11.2. Diễn biến đúng

1. Occurrence `O-1` bắt đầu ở worker A. A nhận epoch 104 cho miền phối hợp tương ứng và tìm hoặc tạo nghĩa vụ chính bằng khóa `(shop-a, S-7, PRIMARY_BILLING, 2026-11)`.
2. Hệ thống ghi hóa đơn `I-81` và thao tác thu `C-81`, giữ chỗ 900.000 VND rồi gửi attempt đầu tiên. Nhà cung cấp chưa trả kết quả rõ ràng.
3. Occurrence `O-2` đến khi lần trước còn chạy. Theo chính sách lịch, nó được ghi là bỏ qua do overlap, không được báo đã thu tiền thành công.
4. Một lịch hỗ trợ và một lệnh thủ công cũng chọn `I-81`. Chúng có thể đi qua các khóa lịch khác nhau, nhưng ranh giới nghiệp vụ nhận ra `C-81` đang có attempt chưa ngã ngũ. Không tạo thêm khoản thu và không giữ thêm 900.000 VND.
5. Worker A mất kết nối, lease hết hạn. Worker B tiếp quản với epoch 105. Việc đổi worker không tạo nghĩa vụ thu mới.
6. B tra cứu hoặc đối soát `C-81` bằng định danh gốc. Nó không coi timeout của A là bằng chứng thất bại chắc chắn.
7. A hoạt động lại và cố cấp phép công việc mới bằng epoch 104. Ranh giới có thẩm quyền từ chối quyền đã lỗi thời.
8. Một kết quả hợp lệ xác nhận nhà cung cấp đã thu thành công `C-81`. Luồng tiếp nhận ghi nhận hiệu ứng, chuyển 900.000 VND từ phần giữ chỗ sang đã thu một cách nhất quán.
9. Response hoặc callback trùng chỉ gắn lại với kết quả đó, không tạo lần thu thứ hai. Các nguồn kích hoạt tiếp theo nhìn thấy nghĩa vụ kỳ đã được xử lý.

### 11.3. Những điều tạo ra bảo đảm

| Kiểm soát | Vai trò trong tình huống |
|---|---|
| Chính sách overlap của lịch | Tránh tích lũy các lần quét không cần thiết |
| Khóa nghiệp vụ duy nhất | Không tạo hai nghĩa vụ chính cho cùng thuê bao và kỳ |
| Phối hợp theo hóa đơn và hạn mức | Không cấp phép hai thao tác cạnh tranh trên cùng tiền phải thu |
| Fencing token | Chặn quyền điều phối đã lỗi thời của A |
| Idempotency của hiệu ứng | Liên kết retry với cùng thao tác thu |
| Đối soát kết quả chưa rõ | Không tạo khoản thu mới khi lần trước có thể đã thành công |
| Audit và lịch sử phiên bản | Giải thích vì sao mỗi lần chạy được xử lý, bỏ qua hoặc bàn giao |

Không có một khóa duy nhất nào thay thế toàn bộ các kiểm soát này.

### 11.4. Biến thể lạm dụng

Nếu người dùng sửa lịch rồi hệ thống đưa schedule revision mới vào khóa thu, nghĩa vụ cũ có thể bị nhận thành nghĩa vụ mới. Nếu retry tạo operation ID mới hoặc đổi nhà cung cấp khi kết quả cũ chưa rõ, hai bên có thể cùng thu thành công.

Nếu chỉ có khóa theo schedule ID, người dùng tạo lịch thứ hai hoặc bấm chạy thủ công có thể vượt kiểm soát. Nếu chỉ có idempotency theo hóa đơn nhưng hệ thống lại cho tạo hai hóa đơn chính cho cùng kỳ, mỗi hóa đơn có thể được thu một lần và tổng vẫn bị trùng.

Các biến thể này cho thấy cần giữ đúng định danh ở cả tầng nghĩa vụ và tầng hiệu ứng.

## 12. Dấu vết, kết quả occurrence và chỉ số vận hành

### 12.1. Phân biệt kết quả điều phối với kết quả nghiệp vụ

Một occurrence có thể có kết quả:

```text
EXECUTED
SKIPPED_DUE_TO_OVERLAP
COALESCED_INTO_OTHER_RUN
WAITING
FAILED_TO_ACQUIRE_OWNERSHIP
```

Đây là nhãn minh họa cho điều phối. `EXECUTED` chỉ cho biết đã thực hiện luồng xử lý; nó không mặc nhiên có nghĩa mọi hóa đơn đã thu thành công.

Hệ thống cần liên kết occurrence với các thao tác nghiệp vụ có trạng thái riêng, chẳng hạn chờ cấp phép, đang xử lý, thành công, thất bại đã xác định hoặc chưa rõ kết quả.

Một lần quét hợp lệ có thể không tìm thấy nghĩa vụ mới. Một occurrence bị bỏ qua cũng không chứng minh có dữ liệu bị mất nếu lần khác đã bao phủ phần đó. Báo cáo phải thể hiện quan hệ bao phủ thay vì suy từ một nhãn chung.

### 12.2. Audit nên liên kết được những gì?

- Tenant, schedule ID, revision và actor hoặc ủy quyền điều khiển.
- Occurrence ID, thời điểm dự kiến, thời điểm thực thi và kỳ nghiệp vụ.
- Chính sách overlap và quyết định áp dụng cho lần kích hoạt.
- Miền phối hợp, chủ sở hữu, epoch và các lần bàn giao liên quan.
- Đối tượng nghiệp vụ, business key, operation ID và phiên bản nội dung.
- Attempt, định danh chống trùng, mã nhà cung cấp và kết quả đối soát.
- Checkpoint, watermark hoặc tập đối tượng đã xử lý nếu có.

Không ghi bí mật thanh toán hay token truy cập vào audit. Quyền sửa lịch không nên kéo theo quyền xóa bằng chứng về các lần chạy đã tạo ra tác động.

Ghi thay đổi quan trọng cùng audit hoặc outbox bền vững trong giao dịch phù hợp. Nếu xuất bằng chứng sang hệ khác, cần chống trùng và đối chiếu để biết sự kiện nào chưa được chuyển.

### 12.3. Đo những chỉ số phản ánh rủi ro

Một số chỉ số hữu ích:

- Thời gian xử lý và số lần chạy đang hoạt động theo miền nghiệp vụ.
- Số occurrence bị bỏ, xếp hàng hoặc gộp, kèm tuổi backlog.
- Số lần xung đột business key và cách chúng được giải quyết.
- Số cập nhật bằng fencing token cũ bị từ chối.
- Số nghĩa vụ hoặc giá trị tiền đang ở trạng thái chưa rõ kết quả, tách theo loại tiền.
- Số tác động vượt hạn mức hoặc hiệu ứng trùng được đối soát xác nhận.
- Số checkpoint tiến vượt phần công việc đã ghi nhận bền vững.

Nhiều xung đột được chặn có thể cho thấy kiểm soát đang phát huy tác dụng, đồng thời phản ánh tần suất hoặc cách phân chia lịch chưa phù hợp. Không nên xóa ràng buộc chỉ để chỉ số xung đột giảm.

## 13. Ma trận kiểm thử overlap và tình huống tấn công

Các tình huống dưới đây là đề xuất kiểm thử cho hệ thống áp dụng thiết kế, không phải báo cáo các kiểm thử đã chạy trong tài liệu này.

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Cùng occurrence được hai replica nhận | Quyết định điều phối nhất quán; không tạo hiệu ứng trùng |
| Lần chạy dài hơn chu kỳ | Thực hiện đúng chính sách cho phép, bỏ qua, xếp hàng hoặc gộp |
| Hai lịch chọn cùng thuê bao và kỳ | Cùng liên kết với nghĩa vụ chính đã có |
| Lệnh thủ công đua với lịch định kỳ | Không có đường bỏ qua quyền, hạn mức hoặc idempotency |
| Retry cùng ý định nhưng operation ID hoặc nội dung bị thay | Phát hiện quan hệ nghĩa vụ cũ hoặc xung đột nội dung, không tự tạo hiệu ứng mới |
| Hai nghĩa vụ khác nhau dùng chung số dư | Giữ đúng tổng hạn mức dù mỗi nghĩa vụ có khóa riêng |
| Worker A mất lease, B tiếp quản, A hoạt động lại | A không cấp phép mới hoặc ghi đè điều phối bằng token cũ |
| Release trễ của A đến sau khi B tiếp quản | Không xóa quyền của B |
| Nhà cung cấp thành công nhưng worker nhận timeout | Giữ nghĩa vụ và đối soát, không thu lại một cách mù quáng |
| Retry định đổi nhà cung cấp | Không tạo lần thu ở nơi mới khi hiệu ứng cũ còn chưa rõ |
| Sự kiện kết quả của attempt cũ đến muộn | Ghi nhận sự thật qua luồng xác thực, chống trùng; không phục hồi quyền worker cũ |
| Đổi schedule revision hoặc tạo lịch mới | Không tạo lại nghĩa vụ kỳ đã tồn tại |
| Backfill nhiều occurrence bị lỡ | Xử lý đúng tập kỳ, không nhân số lần thu theo số tick |
| Lần chạy bị trễ qua ngày hoặc qua kỳ | Kỳ nghiệp vụ không bị suy lại tùy tiện từ giờ bắt đầu |
| Thời điểm địa phương bị lặp hoặc không tồn tại | Áp dụng quy tắc đã chọn và định danh occurrence nhất quán |
| Tắt lịch trong lúc worker đang chạy | Thực hiện đúng hợp đồng với công việc đã cấp phép và phần còn lại |
| Process dừng giữa hiệu ứng và cập nhật checkpoint | Lần quét sau gặp lại đối tượng nhưng không gây thêm hiệu ứng trái phép |
| Client chọn tenant, bộ lọc hoặc khóa phối hợp khác | Máy chủ kiểm tra quyền và suy ra khóa từ dữ liệu có thẩm quyền |
| Quyền hoặc nội dung phê duyệt thay đổi khi đang xếp hàng | Điểm cấp phép áp dụng đúng hợp đồng quyền và phiên bản nội dung |

### Kiểm thử phải điều khiển thứ tự cạnh tranh

Chỉ chạy hai request liên tiếp không chứng minh được hành vi đua. Cần tạo các mốc kiểm soát, ví dụ:

```text
1. Cho A đọc hoặc chuẩn bị xử lý cùng nghĩa vụ.
2. Giữ A trước điểm cấp phép có hậu quả.
3. Cho B hoặc lệnh thủ công xử lý và commit.
4. Cho A tiếp tục.
5. Kiểm tra bản ghi nghĩa vụ, số tiền giữ chỗ, attempt và hiệu ứng ngoài.
```

Với lease, giữ A đủ để quyền được bàn giao rồi cho A hoạt động lại. Với nhà cung cấp, dùng môi trường giả lập hoặc sandbox phù hợp để mô phỏng timeout, kết quả trùng và callback muộn.

Kết quả cần kiểm tra là bất biến nghiệp vụ và hiệu ứng, không chỉ số thread đang chạy hoặc việc một hàm khóa trả về thành công.

## 14. Các thiết kế thường làm mất bảo đảm

| Thiết kế | Vì sao không đủ | Hướng sửa |
|---|---|---|
| Khóa trong bộ nhớ của một process | Replica khác và lệnh thủ công vẫn chạy | Đưa phối hợp và kiểm tra nghiệp vụ vào ranh giới chung |
| Chỉ khóa theo schedule ID | Lịch khác có thể tác động cùng đối tượng | Bảo vệ thêm theo tài nguyên và ý định nghiệp vụ |
| Tăng TTL thật lớn | Vẫn có pause dài và bàn giao sai | Có fencing, kiểm tra quyền hiện hành và recovery |
| Xóa lease không kiểm tra owner/epoch | Worker cũ có thể giải phóng quyền của worker mới | Release có điều kiện |
| Đọc số dư rồi ghi riêng lẻ | Hai lần chạy cùng sử dụng một phần hạn mức | Kiểm tra và giữ chỗ nguyên tử theo miền xung đột |
| Tạo operation ID mới mỗi lần retry | Nhà cung cấp có thể coi là ý định mới | Giữ định danh nghiệp vụ ổn định |
| Gắn revision lịch vào khóa thu tiền | Sửa lịch có thể làm thu lại cùng kỳ | Tách phiên bản điều khiển khỏi định danh nghĩa vụ |
| Coi timeout là thất bại chắc chắn | Lần trước có thể đã thành công | Giữ trạng thái chưa rõ và đối soát |
| Đánh dấu mọi occurrence bị bỏ là thành công | Che mất nghĩa vụ chưa được bao phủ | Ghi đúng kết quả điều phối và liên kết phần công việc |
| Đẩy watermark trước khi ghi công việc bền vững | Sự cố có thể làm mất nghĩa vụ | Checkpoint theo bằng chứng commit và cơ chế tiếp tục an toàn |
| Bỏ kiểm soát khi chạy bù hoặc hỗ trợ thủ công | Tạo đường vòng vượt nghiệp vụ bình thường | Dùng cùng bất biến, quyền và idempotency |

Các lớp bảo vệ cần được chọn theo tác động thực tế. Không nhất thiết phải dùng một loại khóa phân tán cho mọi job; thao tác độc lập hoặc cập nhật có điều kiện tại DB có thể đã đáp ứng yêu cầu. Tuy nhiên, quyết định bỏ khóa phải dựa trên cơ chế khác bảo vệ được bất biến, không dựa vào tần suất overlap thấp.

## 15. Câu hỏi tự đánh giá

1. Hai lịch, retry và lệnh thủ công có thể cùng chọn đối tượng nào? Ranh giới chung ngăn chúng tạo tác động trái phép nằm ở đâu?
2. Khóa đang bảo vệ schedule, occurrence, hóa đơn hay số dư? Nó có đúng miền chứa bất biến không?
3. Khóa nghiệp vụ có giữ nguyên khi đổi lịch, đổi worker hoặc chạy lại cùng nghĩa vụ không?
4. Worker cũ có thể làm gì sau khi hết lease? Ranh giới nào thực sự kiểm tra fencing token?
5. Timeout hoặc đổi nhà cung cấp có thể làm cùng nghĩa vụ được thực hiện hai lần không?
6. Lần chạy bị trễ, chạy bù và đổi vùng thời gian xác định kỳ nghiệp vụ như thế nào?
7. Báo cáo có phân biệt occurrence bị bỏ qua, công việc đã được bao phủ và hiệu ứng thành công thật sự không?

Kiểm soát schedule overlap đạt mục tiêu khi nhiều lần kích hoạt vẫn hội tụ về đúng nghĩa vụ, đúng quyền và đúng trạng thái. Bằng chứng quan trọng là các bất biến được giữ tại điểm gây tác động, kể cả khi lịch, worker và mạng hoạt động không theo thứ tự dự kiến.
