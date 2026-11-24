# Recovery initiation rate — Đo tần suất khởi tạo khôi phục tài khoản

## 1. Chỉ số này trả lời câu hỏi gì?

Recovery initiation rate cho biết luồng khôi phục tài khoản được bắt đầu thường xuyên đến mức nào trong một phạm vi và khoảng thời gian xác định.

Trong module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, một lần bắt đầu có thể liên quan đến quên mật khẩu, mất MFA, mất passkey hoặc mất thiết bị xác thực. Đo bước đầu giúp nhận ra thay đổi về nhu cầu, lỗi trải nghiệm đăng nhập, tác động của một bản phát hành và áp lực lên dịch vụ recovery.

Tuy nhiên, chữ “rate” có thể chỉ hai đại lượng khác nhau:

- Tần suất: bao nhiêu lượt khởi tạo trong một đơn vị thời gian.
- Tỷ lệ: bao nhiêu phần tử của một tập đủ điều kiện có khởi tạo recovery.

Nếu không định nghĩa, hai dashboard có thể cùng ghi “recovery initiation rate” nhưng một bên đếm request mỗi giây, một bên tính phần trăm người dùng. Hai số đó không thể so sánh trực tiếp.

Một sự gia tăng cũng chưa chứng minh tài khoản bị chiếm đoạt. Nó có thể do chiến dịch email, thay đổi giao diện, sự cố đăng nhập, bot hoặc instrumentation bị đếm trùng. Mục tiêu của phép đo là tạo tín hiệu có thể giải thích, không biến một đường biểu diễn thành kết luận về danh tính hoặc quyền truy cập.

Sau bài học, người học có thể:

- Chọn đúng sự kiện đánh dấu một lần khởi tạo.
- Phân biệt request, initiation, recovery transaction, account và login journey.
- Đặt tử số, mẫu số, cửa sổ và đơn vị rõ ràng.
- Xử lý retry, giao event trùng, dữ liệu đến muộn và mất telemetry.
- Tạo truy vấn vận hành cùng truy vấn phân tích có phạm vi nhất quán.
- Đọc biến động mà không làm suy yếu kiểm soát recovery để cải thiện số liệu.

Các event, schema, truy vấn và số liệu trong bài là ví dụ thiết kế cho một hệ thống giả định. Không có một ngưỡng initiation rate mặc định phù hợp với mọi dịch vụ.

## 2. Phân biệt những đơn vị dễ bị gộp

| Đơn vị | Ý nghĩa trong bài | Có thể có quan hệ nhiều lần không? |
|---|---|---|
| HTTP request | Một lần gửi tới endpoint | Một initiation có thể nhận nhiều request do retry |
| Recovery initiation | Một ý định mới đã được server ghi nhận bền vững tại điểm vào | Một người có thể khởi tạo nhiều lần |
| Recovery transaction | Hồ sơ xử lý nghiệp vụ ở các bước tiếp theo | Không phải mọi initiation đều tạo transaction có thể tiếp tục |
| Grant hoặc token | Quyền giới hạn cho hành động recovery | Đếm token không tương đương đếm initiation |
| Login journey | Một hành trình đăng nhập được định nghĩa bởi sản phẩm | Có thể có nhiều lần thử và nhiều initiation |
| Account | Đối tượng tài khoản đã được hệ thống xác định | Không phải mọi initiation đều gắn được với account có thật |
| Người sử dụng | Chủ thể thực tế | Không suy ra chắc chắn từ IP, cookie hay một account ID |

### 2.1. Một ví dụ về đếm sai

Một người nhấn gửi, mạng timeout, ứng dụng tự retry hai lần. Sau đó người này yêu cầu gửi lại mã trong cùng hồ sơ recovery.

Tùy giao thức, có thể quan sát:

~~~text
3 request cho thao tác tạo ban đầu
1 initiation mới
1 recovery transaction
1 thao tác resend trong transaction
~~~

Đếm bốn thao tác mạng thành bốn initiation sẽ làm tín hiệu phụ thuộc vào chất lượng mạng và cách client retry.

Ngược lại, nếu người dùng chủ động bắt đầu một ý định mới sau khi hồ sơ cũ kết thúc, hệ thống có thể ghi một initiation mới. Không gộp mọi lần thử trong ngày thành một lượt chỉ vì cùng địa chỉ email.

### 2.2. Mất passkey khác quên password ở bước sau, chưa chắc khác ở bước đếm đầu

Điểm khởi tạo có thể chung, nhưng quy tắc xác minh và quyền được cấp sau đó khác nhau. Chỉ số đầu vào nên giữ loại đường recovery khi server có cơ sở phân loại.

Nếu người gửi chỉ tự chọn “mất MFA”, đó là loại yêu cầu được khai báo, chưa phải bằng chứng đã mất MFA thật. Tên trường và dashboard cần phản ánh mức biết này.

Nếu loại đường chưa xác định, dùng nhóm unknown có ý nghĩa rõ thay vì tự suy từ thông tin account chưa được xác minh.

## 3. Chọn một điểm khởi tạo có hợp đồng đo lường rõ

### 3.1. Quy ước dùng trong bài

Bài học chọn sự kiện nội bộ:

~~~text
recovery.initiation.recorded
~~~

Sự kiện được tạo khi:

1. Yêu cầu đã đi qua kiểm tra giao thức và admission áp dụng tại điểm vào.
2. Server xác định đây là một ý định mới theo quy tắc idempotency.
3. Một bản ghi initiation đã được lưu bền vững.
4. Bản ghi có định danh và thời gian do server quản lý.

Điểm đếm này có thể nằm trước việc phân giải account. Vì vậy, một initiation không khẳng định rằng account tồn tại, rằng người gửi là chủ account hoặc rằng recovery sẽ được cho phép.

Một sản phẩm có thể chọn điểm khác, chẳng hạn chỉ đếm khi tạo transaction đủ điều kiện. Khi đó phải đặt tên riêng và ghi ranh giới khác biệt. Không thay đổi ngầm điểm đếm giữa hai bản phát hành.

### 3.2. Những gì không làm tăng số initiation theo quy ước này

| Hành vi | Cách xử lý |
|---|---|
| Refresh trang recovery | Không phải initiation mới nếu chưa ghi nhận ý định mới |
| Retry cùng thao tác idempotent | Trả về cùng kết quả công khai phù hợp, không tạo lượt mới |
| Giao lại cùng event qua broker | Không tính thêm một business initiation |
| Resend mã trong cùng hồ sơ | Ghi chỉ số resend riêng |
| Chuyển bước xác minh | Ghi tiến trình, không bắt đầu lại bộ đếm |
| Request bị từ chối trước điểm ghi nhận | Ghi attempt/admission outcome riêng |
| Health check hoặc synthetic probe | Nhận diện bằng nguồn tin cậy và phân loại riêng |
| Tạo ý định mới theo giao thức sản phẩm | Tính initiation mới, dù có cùng account đích |

Việc phân loại synthetic không dựa vào một header tự khai từ bên ngoài. Nếu attacker có thể gắn nhãn “test”, bộ lọc sẽ che khuất lưu lượng cần quan sát.

### 3.3. HTTP 200 hoặc 202 không phải bằng chứng đủ

Endpoint công khai có thể cố ý trả thông báo giống nhau cho account tồn tại và không tồn tại. Một số lỗi nghiệp vụ cũng có thể được xử lý bất đồng bộ.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) hướng dẫn tránh tiết lộ sự tồn tại của account qua thông báo hoặc thời gian phản hồi, đồng thời kiểm soát gửi yêu cầu tự động quá mức.

Do đó, không lấy toàn bộ response 2xx làm tử số của initiation nghiệp vụ nếu hợp đồng thực tế không bảo đảm chúng tương đương. Cũng không sửa response công khai để phục vụ dashboard.

Phép đo nội bộ có thể phân biệt các giai đoạn cần thiết với quyền truy cập phù hợp. Thiết kế đó không được tạo thêm đường dò account qua API metric hoặc dashboard bị công khai.

### 3.4. Một metric contract minh họa

~~~yaml
metricContract:
  id: recovery-initiation-v1
  countedUnit: server-recorded-new-intent
  sourceEvent: recovery.initiation.recorded
  eventTimeField: recordedAt
  uniquenessKey:
    - issuerRef
    - initiationRef
  included:
    - production-public-intake-admitted-new-intents
  excluded:
    - transport-retries-for-the-same-intent
    - resend-within-existing-transaction
    - trusted-synthetic-traffic
  accountExistenceRequired: false
  primaryUnit: initiations-per-second
  ownerRole: recovery-platform
~~~

Đây là ví dụ tài liệu trong Markdown, không phải metadata của bài học.

Contract thực tế còn cần quy tắc định danh, phạm vi admission, cách xử lý thiếu dữ liệu và phiên bản. Đặc biệt, phải biết những lớp như WAF hoặc gateway đã loại lưu lượng nào trước khi server có thể ghi nhận initiation.

## 4. Ba công thức khác nhau và cách đặt mẫu số

### 4.1. Tần suất theo thời gian

Gọi I(W) là số initiation mới, không trùng, có thời điểm ghi nhận thuộc cửa sổ W. Gọi duration(W) là độ dài cửa sổ theo giây.

~~~text
Initiation frequency(W) = I(W) / duration(W)
Đơn vị: initiations/second
~~~

Ví dụ tổng hợp: 600 initiation trong 30 phút:

~~~text
600 / 1.800 = 0,333... initiation/giây
600 / 30 = 20 initiation/phút
~~~

Cần ghi rõ cửa sổ 30 phút. Một đỉnh 20 initiation/phút trong một phút và trung bình 20/phút trong nửa giờ có ý nghĩa vận hành khác nhau.

### 4.2. Tỷ lệ login journey chuyển sang recovery

Gọi J là tập login journey đủ điều kiện. Gọi H là thời gian theo dõi được quy định. Một journey được tính vào tử số nếu có ít nhất một initiation liên kết hợp lệ trong H.

~~~text
Journey initiation share
  = số journey trong J có ít nhất một initiation trong H
    / số journey trong J
    × 100%
~~~

Ví dụ, 10.000 journey được chọn vào cohort và 420 journey có ít nhất một initiation trong thời gian theo dõi:

~~~text
420 / 10.000 × 100% = 4,2%
~~~

Nếu 420 journey tạo tổng cộng 500 initiation thì:

~~~text
500 / 10.000 × 100 = 5 initiation trên 100 journey
~~~

Con số 5 là mật độ sự kiện trên journey, không phải tỷ lệ journey có recovery. Khi một journey có thể khởi tạo nhiều lần, mật độ này có thể lớn hơn 100 trên 100 journey.

### 4.3. Mật độ trên một tập account

Có thể đo initiation trên 1.000 account thuộc một population được định nghĩa:

~~~text
Account-normalized event density
  = số initiation gắn với population P trong W
    / số account trong P
    × 1.000
~~~

Cần nói rõ P là account có quyền dùng recovery, account hoạt động theo tiêu chí nào hay account hiện diện trong kỳ. Những lựa chọn này trả lời các câu hỏi khác nhau.

Không dùng initiation chưa phân giải account ở tử số rồi gọi kết quả là tỷ lệ account bị ảnh hưởng. Nếu muốn tỷ lệ account, tử số phải là số account duy nhất trong chính population đó có sự kiện đủ điều kiện.

Mẫu số “account đăng nhập thành công hôm nay” đặc biệt dễ gây lệch khi sự cố khiến người dùng không thể đăng nhập. Nó có thể loại đúng nhóm đang cần recovery.

### 4.4. Mẫu số bằng không và dữ liệu thiếu

Nếu population rỗng, tỷ lệ không có nghĩa; hiển thị N/A hoặc trạng thái tương đương. Không tự thay mẫu số bằng 1.

Nếu không có dữ liệu vì pipeline gián đoạn, hiển thị thiếu dữ liệu. Chỉ hiển thị 0 khi nguồn đáng tin xác nhận cửa sổ đã có độ bao phủ cần thiết và không có initiation.

Đối với một tỷ lệ, tử số và mẫu số phải cùng phạm vi, cách loại traffic, phiên bản định nghĩa và mức độ hoàn tất dữ liệu.

## 5. Cohort, thời gian theo dõi và attribution

### 5.1. Không chia tùy tiện hai tổng trong cùng ngày

Một người có thể mở login journey lúc cuối ngày và bắt đầu recovery sau nửa đêm. Nếu chia initiation hôm sau cho journey hôm sau, tử số và mẫu số có thể không cùng tập.

Với journey initiation share, chọn journey theo thời điểm bắt đầu rồi theo dõi từng journey trong H. Ví dụ H là 24 giờ chỉ là lựa chọn minh họa, cần phù hợp hành vi sản phẩm.

Một cohort chỉ nên có kết quả cuối khi:

- Mọi journey trong cohort đã có đủ thời gian theo dõi.
- Dữ liệu initiation liên quan đã tới mức hoàn tất được chấp nhận.
- Phương pháp liên kết giữa journey và initiation được xác định.

Một cohort đang mở có thể hiển thị provisional. Không so nó như thể đã có cùng thời gian quan sát với cohort tuần trước.

### 5.2. Giữ liên kết do server có thể kiểm tra

Nếu muốn biết initiation xuất phát từ login journey nào, cần reference được hệ thống kiểm soát và quy tắc liên kết rõ.

Reference dùng cho phân tích không tự cấp quyền recovery. Việc biết một journey ID không được đủ để thay password hay đăng ký passkey mới.

Không tin tùy tiện parent journey do client khai. Kiểm tra scope, nguồn, thời gian và khả năng liên kết theo giao thức được thiết kế. Với tenant, không dùng một ID cục bộ để join xuyên tenant.

### 5.3. Giữ các trường hợp không liên kết được

Người dùng có thể vào recovery qua bookmark, ứng dụng khác hoặc nhân viên hỗ trợ. Những initiation đó không có parent login journey hợp lệ.

Giữ nhóm direct hoặc unattributed theo định nghĩa. Không gán chúng cho journey gần nhất của cùng IP; nhiều người có thể dùng chung mạng.

Mức độ liên kết cũng là một thuộc tính chất lượng dữ liệu. Nếu phiên bản mobile mới làm mất reference, journey initiation share có thể giảm dù số initiation thực tế không giảm.

## 6. Đặt instrumentation ở ranh giới nghiệp vụ

### 6.1. Event cần đủ để tính nhưng không chứa bí mật

~~~json
{
  "schemaVersion": 1,
  "eventId": "event-example-101",
  "eventType": "recovery.initiation.recorded",
  "issuerRef": "recovery-authority-example",
  "initiationRef": "initiation-example-35",
  "recordedAt": "2026-09-18T08:15:00Z",
  "ingestedAt": "2026-09-18T08:15:02Z",
  "environment": "production",
  "tenantScopeRef": "trusted-tenant-scope-example",
  "entryChannel": "web",
  "requestedPath": "lost-mfa",
  "parentLoginJourneyRef": null,
  "trafficClass": "unclassified",
  "metricDefinitionVersion": "recovery-initiation-v1"
}
~~~

Đây là dữ liệu tổng hợp. requestedPath thể hiện loại yêu cầu ban đầu; trafficClass unclassified không khẳng định đây là người thật hay bot.

Không cần email, số điện thoại, password, recovery code, token, seed TOTP hoặc private key để tính tần suất tổng hợp. Nếu phân tích account duy nhất thực sự cần thiết, dùng nguồn có kiểm soát và quyền truy cập phù hợp, thay vì đưa account ID lên mọi hệ thống metrics.

Một định danh đã hash vẫn có thể là dữ liệu liên kết được. Hash email cũng không tự giải quyết tấn công đoán trên một miền giá trị có thể dự đoán.

### 6.2. Idempotency là thuộc tính giao thức, không chỉ là DISTINCT

Quy tắc tạo initiation cần phân biệt retry cùng ý định với ý định mới. Server có thể sử dụng idempotency key theo một scope được xác định, lưu kết quả và ràng buộc key với nội dung thao tác cần thiết.

Nếu client đổi key ở mỗi lần retry, cùng ý định có thể tạo nhiều initiation. Nếu key được dùng chung quá rộng, hai ý định hợp lệ lại có thể bị gộp.

Đối chiếu DISTINCT theo initiationRef chỉ loại giao lại cùng initiation. Nó không sửa được lỗi server đã cấp hai initiationRef cho cùng một thao tác mà giao thức đáng lẽ phải gộp.

Không dùng email cộng một khoảng thời gian tùy tiện làm định nghĩa duy nhất cho ý định. Cách đó có thể che hành vi lặp lại hoặc gộp nhầm hoạt động hợp lệ.

### 6.3. Chọn một nơi phát sinh bản ghi chuẩn

Nếu API gateway, recovery service và worker cùng tăng một metric tên “initiations”, tổng có thể bị nhân lên ba lần.

Chọn một authority cho bản ghi initiation. Các lớp khác giữ metric request, admission hoặc delivery với tên khác. Nếu nhiều region đều có quyền tạo initiation, phải định nghĩa phạm vi uniqueness và cơ chế chuyển vùng.

Một outbox trong cùng transaction với bản ghi initiation có thể giúp event chỉ phản ánh các bản ghi đã commit. Consumer vẫn cần xử lý giao trùng và phát hiện backlog. Không tự suy rằng outbox mang lại exactly-once cho mọi phép đếm.

### 6.4. Counter quan sát và số liệu chuẩn có thể khác nhau

Một counter trong tiến trình được tăng sau commit có thể bỏ lỡ một initiation nếu tiến trình dừng giữa commit và increment. Tăng trước commit lại có thể đếm một lần ghi bị rollback.

Vì vậy, counter phục vụ quan sát nhanh phải ghi rõ bảo đảm và giới hạn. Khi cần số liệu nghiệp vụ cuối kỳ có thể đối chiếu, dùng bản ghi chuẩn hoặc pipeline tổng hợp có cơ chế bền vững, khử trùng và xác nhận độ bao phủ.

Nếu tăng counter mỗi lần consumer nhận event, consumer retry sẽ làm phồng số. Khử trùng bền vững và cập nhật tổng hợp cần được thiết kế cùng nhau; chỉ kiểm tra trong một cache có thể mất sau restart không tạo ra bảo đảm toàn kỳ.

## 7. Tính tần suất bằng Prometheus

### 7.1. Counter và label

Một counter minh họa:

~~~text
recovery_initiations_recorded_total{
  environment="production",
  entry_channel="web",
  requested_path="lost-mfa"
}
~~~

Counter này chỉ đếm phạm vi public intake đã nêu trong contract. Nhánh hỗ trợ hoặc quản trị có thể có chỉ số tương ứng, nhưng cần contract và phạm vi riêng trước khi tổng hợp chung.

Các giá trị label phải đến từ tập được kiểm soát. Không dùng URL đầy đủ, initiationRef, account ID, email, IP hoặc idempotency key làm label.

[Tài liệu instrumentation của Prometheus](https://prometheus.io/docs/practices/instrumentation/) giải thích chi phí của mỗi tập label và phân biệt counter tích lũy sự kiện với gauge phản ánh trạng thái. Trong ví dụ này, counter dùng cho số sự kiện; trạng thái backlog cần một phép đo khác.

Có thể ước lượng số tổ hợp bằng tích số giá trị của các chiều, rồi tính thêm instance và các label do hạ tầng gắn. Đây là cách dự trù chi phí, không phải lý do tạo mọi tổ hợp nếu chưa có câu hỏi cần trả lời.

### 7.2. Lượt khởi tạo mỗi giây

~~~promql
sum(
  rate(
    recovery_initiations_recorded_total{
      environment="production"
    }[5m]
  )
)
~~~

Kết quả là tần suất trung bình mỗi giây trên cửa sổ 5 phút theo các series có dữ liệu. Muốn hiển thị mỗi phút, nhân kết quả với 60.

[Tài liệu hàm Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate) mô tả rate tính tốc độ tăng trung bình theo giây, xử lý counter reset và ngoại suy theo cửa sổ. Khi tổng hợp nhiều series, tính rate trước rồi sum để còn nhận ra reset ở từng series.

Không lấy hiệu hai giá trị counter tổng rồi chia thời gian mà bỏ qua restart hoặc series biến mất. Cũng không áp dụng rate cho gauge số transaction hiện đang mở để gọi đó là initiation rate.

### 7.3. Phân tách theo kênh

~~~promql
sum by (entry_channel) (
  rate(
    recovery_initiations_recorded_total{
      environment="production"
    }[5m]
  )
)
~~~

Các giá trị channel phải có cùng ý nghĩa trên mọi producer. Nếu web đếm lúc người dùng nhấn nút còn mobile đếm lúc lưu initiation, so sánh theo channel sẽ trộn hai định nghĩa.

Khi một loại yêu cầu được đổi tên hoặc chia nhóm, giữ quy tắc nối dữ liệu lịch sử hoặc đánh dấu một điểm gãy. Không coi thay schema là biến động hành vi người dùng.

### 7.4. Ước lượng số lượt trong cửa sổ

~~~promql
sum(
  increase(
    recovery_initiations_recorded_total{
      environment="production"
    }[30m]
  )
)
~~~

Theo [tài liệu increase](https://prometheus.io/docs/prometheus/latest/querying/functions/#increase), phép tính có ngoại suy nên có thể trả số không nguyên dù counter tăng theo từng sự kiện nguyên.

Đây là ước lượng từ dữ liệu scrape cho cửa sổ, không phải danh sách initiation chuẩn để quyết toán hay đối chiếu từng hồ sơ. Làm tròn chỉ thay cách trình bày, không khôi phục sự kiện bị mất.

Khoảng scrape, restart, target ngừng tồn tại và độ bao phủ collector đều ảnh hưởng cách đọc kết quả. Một cửa sổ ngắn thiếu điểm quan sát có thể không cho kết quả có nghĩa.

### 7.5. Series không có khác với counter bằng không

Đối với các tổ hợp label được dự kiến, có thể khởi tạo counter bằng 0 và giám sát target cùng pipeline. Tuy nhiên, nhìn thấy target còn sống chưa đủ chứng minh mọi đường nghiệp vụ đều instrument đúng.

Đừng dùng một phép mặc định về 0 cho tất cả khoảng trống trên biểu đồ rồi kết luận không có nhu cầu recovery. Dashboard cần thể hiện dữ liệu thiếu và cảnh báo chất lượng thu thập ở nơi phù hợp.

## 8. Tính từ bản ghi chuẩn bằng SQL

### 8.1. Giả định dữ liệu

Ví dụ PostgreSQL dưới đây giả định:

- recovery_initiation có một dòng chuẩn cho mỗi khóa issuer_ref và initiation_ref.
- recorded_at là thời điểm server ghi nhận initiation, có kiểu timestamp with time zone.
- intake_scope, entry_channel và phiên bản định nghĩa là thuộc tính đã được cố định khi khởi tạo.
- is_trusted_synthetic do hệ thống xác định từ nguồn tin cậy.
- Query đọc một snapshot có phạm vi và mức hoàn tất được ghi lại.

Các bảng và truy vấn là minh họa, không được thực thi trong bài. Nếu nguồn thực tế là event giao nhiều lần, phải tạo tập initiation chuẩn trước; không sao chép nguyên truy vấn lên log thô.

### 8.2. Tổng số và tần suất trong một cửa sổ

~~~sql
WITH counted AS (
    SELECT
        issuer_ref,
        initiation_ref,
        entry_channel
    FROM recovery_initiation
    WHERE environment = 'production'
      AND intake_scope = 'public-intake'
      AND metric_definition_version = 'recovery-initiation-v1'
      AND is_trusted_synthetic = FALSE
      AND recorded_at >= :window_start
      AND recorded_at <  :window_end
)
SELECT
    COUNT(*) AS initiation_count,
    COUNT(*)::numeric
        / NULLIF(
            EXTRACT(EPOCH FROM (
                CAST(:window_end AS timestamptz)
                - CAST(:window_start AS timestamptz)
            )),
            0
        ) AS initiations_per_second
FROM counted;
~~~

Hai tham số đầu vào phải được kiểm tra để window_end lớn hơn window_start. NULLIF tránh phép chia cho 0 trong biểu thức, nhưng không thay việc kiểm tra một cửa sổ đầu vào không hợp lệ.

Dùng khoảng nửa mở: bao gồm đầu, loại cuối. Hai cửa sổ liền nhau sẽ không đếm hai lần một sự kiện đúng tại ranh giới.

Với cửa sổ hợp lệ, COUNT bằng 0 có nghĩa không có dòng trong snapshot đáp ứng điều kiện. Nó chỉ hỗ trợ kết luận không có initiation trong phạm vi nếu snapshot đủ đầy và đúng nguồn.

### 8.3. Theo dõi cohort login journey

Giả sử login_journey có khóa issuer_ref và journey_ref. Parent reference của initiation được lưu bằng parent_journey_issuer_ref và parent_journey_ref sau khi kiểm tra liên kết.

eligible_for_recovery là điều kiện đủ để đưa journey vào phân tích tại lúc bắt đầu theo contract, không phải kết luận rằng người gửi đã chứng minh quyền sở hữu account.

~~~sql
WITH cohort AS (
    SELECT
        issuer_ref,
        journey_ref,
        started_at
    FROM login_journey
    WHERE environment = 'production'
      AND eligible_for_recovery = TRUE
      AND analysis_population_version = 'login-cohort-v1'
      AND is_trusted_synthetic = FALSE
      AND started_at >= :cohort_start
      AND started_at <  :cohort_end
      AND started_at + INTERVAL '24 hours' <= :observation_cutoff
),
marked AS (
    SELECT
        j.issuer_ref,
        j.journey_ref,
        EXISTS (
            SELECT 1
            FROM recovery_initiation AS i
            WHERE i.parent_journey_issuer_ref = j.issuer_ref
              AND i.parent_journey_ref = j.journey_ref
              AND i.environment = 'production'
              AND i.intake_scope = 'public-intake'
              AND i.metric_definition_version = 'recovery-initiation-v1'
              AND i.is_trusted_synthetic = FALSE
              AND i.recorded_at >= j.started_at
              AND i.recorded_at < j.started_at + INTERVAL '24 hours'
        ) AS has_initiation
    FROM cohort AS j
)
SELECT
    COUNT(*) AS eligible_journeys,
    COUNT(*) FILTER (WHERE has_initiation) AS initiated_journeys,
    100.0 * COUNT(*) FILTER (WHERE has_initiation)
        / NULLIF(COUNT(*), 0) AS initiation_share_percent
FROM marked;
~~~

EXISTS giúp mỗi journey chỉ đóng góp tối đa một đơn vị vào tử số, dù có nhiều initiation.

Điều kiện observation_cutoff bảo đảm thời gian theo dõi đã trôi qua, nhưng không tự chứng minh dữ liệu đã được thu thập đủ. Vẫn cần xác nhận watermark, tình trạng nguồn và quy tắc xử lý event đến muộn.

Nếu chưa đủ thời gian cho toàn bộ cohort dự kiến, truy vấn sẽ chỉ giữ phần đã trưởng thành. Báo cáo phải ghi số journey được giữ và bị loại; không gọi phần đó là kết quả cuối cho toàn kỳ. Một lựa chọn khác là chờ cả cohort hoàn tất rồi mới phát hành số liệu cuối.

Phạm vi tenant cần được bảo đảm bởi khóa và kiểm tra parent link trong schema thật. Nếu journey_ref chỉ duy nhất theo tenant, khóa join phải bổ sung tenant; không giả định ví dụ issuer_ref luôn đủ cho mọi hệ thống.

### 8.4. Không lấy trung bình đơn giản các tỷ lệ

Giả sử hai nhóm có số liệu:

| Nhóm | Journey đủ điều kiện | Journey có initiation | Tỷ lệ |
|---|---:|---:|---:|
| A | 100 | 10 | 10% |
| B | 9.900 | 99 | 1% |

Tỷ lệ chung là:

~~~text
(10 + 99) / (100 + 9.900) × 100% = 1,09%
~~~

Trung bình 10% và 1% thành 5,5% là sai cho toàn population này vì hai nhóm có kích thước khác nhau.

Khi tổng hợp, cộng các tử số và mẫu số tương thích rồi chia. Điều đó chỉ đúng nếu các tập không bị chồng lặp và cùng định nghĩa.

## 9. Dữ liệu đến muộn, sửa số liệu và kiểm tra chất lượng

### 9.1. Thời gian nghiệp vụ và thời gian nhận

recordedAt trả lời lúc initiation được ghi nhận tại nguồn. ingestedAt trả lời lúc pipeline phân tích nhận được sự kiện.

Nếu backlog được xả lúc 10:00, gom theo ingestedAt có thể tạo đỉnh lúc 10:00 dù initiation thực tế diễn ra rải rác trước đó. Điều này có ích khi đo tải ingestion, nhưng không phải cùng phép đo nhu cầu recovery.

Với dữ liệu event-time, cần một chính sách rõ về cửa sổ provisional, cutoff, late arrival và thời điểm tính lại. Nếu số liệu đã công bố được sửa, giữ dấu hiệu revision và lý do.

### 9.2. Khử trùng theo định danh nghiệp vụ

Một event có thể được broker giao lại với cùng eventId. Trong một số pipeline, cùng initiation có thể được xuất lại với eventId mới. Vì vậy, khóa đếm initiation phải theo contract, không chỉ dựa vào định danh lần giao.

Nếu hai bản ghi cùng khóa initiation nhưng khác recordedAt hoặc entryChannel một cách mâu thuẫn, không tùy tiện chọn một bản rồi coi như sạch. Cần quy tắc nguồn chuẩn và xử lý conflict; sai khác có thể phản ánh lỗi producer.

Khử trùng cũng không được trộn dữ liệu của các authority có namespace khác nhau. Hai initiationRef giống chuỗi chưa có nghĩa cùng initiation.

### 9.3. Đối chiếu với nguồn có thẩm quyền

Có thể kiểm tra theo từng scope và cửa sổ:

~~~text
Số initiation chuẩn tại nguồn
  ↔ Số initiation duy nhất trong pipeline phân tích
  ↔ Ước lượng counter phục vụ quan sát nhanh
~~~

Chênh lệch cần được giải thích bằng bảo đảm của từng nguồn: scrape bỏ lỡ, event đến muộn, khử trùng sai, filter khác nhau hoặc đường nghiệp vụ thiếu instrumentation.

Không yêu cầu counter ngoại suy phải khớp từng đơn vị với số dòng chuẩn. Nhưng nếu một kênh mất hoàn toàn trên metrics trong khi nguồn chuẩn có initiation, đó là vấn đề cần điều tra.

### 9.4. Những điều kiện cần hiển thị cùng số liệu

Một kết quả đáng đọc nên đi kèm:

- Phiên bản định nghĩa và phạm vi.
- Cửa sổ, múi giờ và đơn vị.
- Nguồn dữ liệu cùng thời điểm cập nhật.
- Trạng thái hoàn tất hoặc provisional.
- Số mẫu và mẫu số nếu là tỷ lệ.
- Phần traffic không phân loại hoặc không liên kết được.
- Khoảng mù và sự cố pipeline đang biết.

Không cần đưa mọi thông tin thành label thời gian thực. Có thể để trong mô tả metric, metadata của báo cáo và màn hình chi tiết.

## 10. Diễn giải biến động trong bối cảnh

### 10.1. Tăng không đồng nghĩa xấu, giảm không đồng nghĩa tốt

| Quan sát | Những khả năng cần kiểm tra | Dữ liệu đối chiếu |
|---|---|---|
| Initiation tăng sau release | Lỗi đăng nhập, recovery dễ tìm hơn, đổi cách đếm | Login error, entry point, metric version |
| Request tăng nhưng initiation không tăng | Retry, admission chặn, lỗi trước commit | Outcome request, rate limit, lỗi ghi |
| Initiation giảm mạnh | Nhu cầu giảm, endpoint hỏng, giao diện mất nút, mất telemetry | Tải login, synthetic, nguồn chuẩn |
| Một kênh tăng riêng | Lỗi client, thay UX, traffic mix đổi | Client version, cohort, attribution coverage |
| Nhóm unclassified tăng | Traffic mới hoặc classifier mất dữ liệu | Chất lượng phân loại và nguồn đầu vào |
| Counter tăng nhưng nguồn chuẩn ổn định | Đếm event giao lại hoặc instrumentation đổi | Consumer retry, event key, release |
| Nguồn chuẩn tăng, email gửi không tăng | Nhánh không gửi, không đủ điều kiện hoặc lỗi downstream | Quy tắc gửi và provider outcome |

Không dùng initiation rate làm mục tiêu đơn độc cho một đội. Nếu chỉ thưởng cho việc giảm lượt khởi tạo, đội có thể vô tình làm recovery khó tiếp cận hơn.

Đối với người mất MFA hoặc thiết bị xác thực, không có initiation có thể là dấu hiệu bị mắc kẹt trước điểm vào. Cần theo dõi cả khả năng người hợp lệ tìm và dùng được con đường hỗ trợ phù hợp.

### 10.2. Thay đổi traffic mix có thể đảo kết luận

Số liệu tổng hợp dưới đây đều là giả định và đã được tính theo cùng contract cohort:

| Giai đoạn | Desktop: journey / có initiation | Tỷ lệ desktop | Mobile: journey / có initiation | Tỷ lệ mobile | Tỷ lệ chung |
|---|---|---:|---|---:|---:|
| A | 9.000 / 90 | 1% | 1.000 / 100 | 10% | 1,9% |
| B | 1.000 / 8 | 0,8% | 9.000 / 810 | 9% | 8,18% |

Trong cả desktop và mobile, tỷ lệ giảm. Nhưng tỷ lệ chung tăng vì phần lớn traffic chuyển sang mobile, nhóm vốn có tỷ lệ cao hơn.

Kết luận hợp lý là cần phân tích thay đổi cơ cấu và từng nhóm. Chưa thể nói một release làm recovery xấu đi chỉ dựa vào tỷ lệ tổng.

Ngay cả tỷ lệ giảm trong từng nhóm cũng chưa tự chứng minh trải nghiệm tốt hơn. Có thể người dùng bỏ cuộc trước điểm khởi tạo; cần xem thêm tín hiệu liên quan.

### 10.3. So sánh theo baseline phù hợp

Một baseline có thể xét cùng giờ, cùng ngày trong tuần, cùng kênh và những thay đổi đã biết như chiến dịch hoặc phát hành phiên bản.

Không mặc định một trung bình dài hạn đại diện cho mọi thời điểm. Tài khoản doanh nghiệp có nhịp làm việc khác tài khoản cá nhân; một đợt thay thiết bị tập trung có thể làm tăng nhu cầu thật.

Khi baseline gần 0, tỷ lệ tăng tương đối có thể rất lớn dù chỉ có vài sự kiện. Luôn xem số tuyệt đối và mức biến động tự nhiên của nhóm.

Một mô hình cảnh báo phức tạp không sửa được tử số đếm trùng hoặc mẫu số sai phạm vi.

## 11. Tách nhu cầu, retry và dấu hiệu lạm dụng

### 11.1. Giữ lớp request để giải thích initiation

Giả sử trong một cửa sổ, 920 request đi vào điểm đo admission đã chọn và được phân loại thành các nhóm loại trừ nhau:

| Outcome tại điểm đo | Số request | Tăng initiation? |
|---|---:|---|
| Tạo ý định mới đã lưu | 600 | Có, mỗi request trong nhóm này tạo một lượt |
| Trả kết quả cho retry cùng ý định | 210 | Không |
| Bị rate limit trước điểm ghi nhận | 90 | Không |
| Không hợp lệ theo giao thức | 20 | Không |
| Tổng | 920 | 600 initiation |

Tổng nhóm outcome bằng tổng request trong ví dụ vì mỗi request có đúng một outcome cuối tại điểm đo. Nếu pipeline thực tế ghi cả outcome trung gian, không cộng chúng như những nhóm độc lập.

Lưu lượng bị WAF loại trước điểm này không nằm trong 920. Tên báo cáo phải chỉ rõ ranh giới, tránh gọi đây là toàn bộ traffic bên ngoài.

600 initiation cũng không phải 600 người dùng duy nhất. Nó có thể gồm nhiều ý định của một actor, yêu cầu nhắm vào account không tồn tại và các trường hợp chưa đủ dữ kiện phân loại.

### 11.2. Chỉ số đã lọc bot cần nêu hạn chế

Có thể cung cấp cả all admitted initiations và một tập được phân loại là likely legitimate theo phiên bản classifier.

Tập thứ hai là ước lượng theo mô hình, không phải chứng minh danh tính. Nếu classifier thay đổi giữa kỳ, số liệu có thể đổi dù hành vi không đổi.

Nên giữ nguồn tổng hợp gốc trong phạm vi chính sách để có thể đối chiếu. Không âm thầm xóa những initiation “trông có vẻ bot” khỏi mọi báo cáo, khiến người vận hành không còn thấy áp lực thực tế.

Một attacker cũng có thể thay key hoặc thiết bị để tạo nhiều initiation. Idempotency xử lý retry theo giao thức; nó không thay kiểm soát lạm dụng.

### 11.3. Không tăng tỷ lệ bằng cách nới quyền

Khi thấy nhiều request bị chặn, chưa thể kết luận nên bỏ rate limit hoặc hạ yêu cầu xác minh. Cần kiểm tra đối tượng bị ảnh hưởng, cơ chế chặn và bằng chứng về false positive.

Tương tự, không tự động phát hành thêm token, thay MFA hay vô hiệu credential chỉ vì một chỉ số đầu vào tăng. Initiation không chứng minh quyền sở hữu tài khoản.

Các thay đổi về token dùng một lần, xác minh danh tính và session phải được quyết định theo thiết kế bảo mật của luồng. Metrics cung cấp tín hiệu đánh giá, không thay cho authorization.

## 12. Dashboard và cảnh báo có thể hành động

### 12.1. Một bố cục nhỏ nhưng đủ ngữ cảnh

Có thể tổ chức theo ba tầng:

~~~text
Nhu cầu được ghi nhận
  initiation/giây, số lượt trong cửa sổ, phân tách kênh

Giải thích đầu vào
  request outcome, retry, admission, attribution

Độ tin cậy và hậu quả
  dữ liệu thiếu, backlog, lỗi ghi, tín hiệu downstream cần đối chiếu
~~~

Tỷ lệ cohort nên nằm ở một vùng riêng với thời gian theo dõi và trạng thái trưởng thành. Không đặt một đường phần trăm bên cạnh tần suất mỗi giây mà dùng chung nhãn “rate”.

Các phân tách có volume nhỏ hoặc nhạy cảm cần quyền truy cập và cách trình bày phù hợp. Một dashboard theo account hoặc tenant quá chi tiết có thể tiết lộ hành vi recovery.

### 12.2. Cảnh báo theo câu hỏi điều tra

Một cảnh báo về tăng bất thường nên nói rõ scope, số hiện tại, baseline, thời gian duy trì và nơi kiểm tra chất lượng dữ liệu. Khi cần, thêm điều kiện volume tối thiểu để tránh nhiễu, nhưng ghi đây là lựa chọn vận hành.

Cảnh báo về giảm bất thường cần phân biệt:

- Traffic đầu vào thực sự giảm.
- Yêu cầu vẫn tới nhưng không tạo được initiation.
- Bản ghi chuẩn vẫn có nhưng metrics mất.
- Cả nguồn và telemetry đều không đủ để kết luận.

Không chỉ cảnh báo khi số tăng. Một sự cố chặn người dùng ở điểm vào có thể làm đường biểu diễn rất thấp.

### 12.3. Trình tự điều tra minh họa

1. Xác nhận định nghĩa, đơn vị, scope và tình trạng dữ liệu.
2. So request với initiation để tìm thay đổi ở admission hoặc retry.
3. Phân tách theo kênh, đường yêu cầu và thay đổi triển khai.
4. Xem population hoặc attribution có thay đổi không.
5. Đối chiếu lỗi login, trải nghiệm recovery và tín hiệu lạm dụng liên quan.
6. Chọn hành động theo nguyên nhân đã có bằng chứng, rồi theo dõi kết quả với cùng contract.

Các bước này là phương pháp phân tích, không phải lệnh thay cấu hình production. Nếu xuất hiện bằng chứng chiếm đoạt account hoặc vi phạm kiểm soát, cần đưa vào quy trình ứng phó phù hợp thay vì chỉ chỉnh dashboard.

## 13. Dùng initiation rate để lập kế hoạch mà giữ đúng giới hạn

### 13.1. Ước lượng nhu cầu tài nguyên

Nếu tần suất là 20 initiation/phút và quan sát trong cùng phạm vi cho thấy trung bình 1,4 tác vụ downstream trên mỗi initiation, có thể ước lượng tải trung bình:

~~~text
20 × 1,4 = 28 tác vụ downstream/phút
~~~

Đây là phép ước lượng từ một hệ số quan sát, không phải quy tắc mỗi initiation phải gửi email hay SMS. Những nhánh không đủ điều kiện có thể không phát sinh tác vụ gửi.

Cần xem thêm tải đỉnh, burst, retry của provider và giới hạn đồng thời. Trung bình theo nửa giờ có thể che một đỉnh ngắn làm đầy queue.

Nếu policy hoặc cơ cấu đường recovery thay đổi, hệ số 1,4 có thể không còn đại diện. Đừng giữ cố định hệ số chỉ vì nó thuận tiện cho dự báo.

### 13.2. Đánh giá một thay đổi sản phẩm

Giả sử đổi giao diện giúp người dùng mất thiết bị tìm được recovery dễ hơn. Initiation rate tăng có thể là kết quả mong muốn.

Để đánh giá, cần biết nhóm đủ điều kiện, phân bổ traffic, thời gian theo dõi và các thay đổi đồng thời. Quan sát trước/sau đơn thuần chưa chứng minh quan hệ nhân quả.

Giữ thêm những tín hiệu phục hồi hợp lệ và an toàn: người dùng có tiếp tục được không, bằng chứng xác minh có đúng điều kiện không và có phát sinh hành vi lạm dụng không. Không cần gộp tất cả thành một điểm số duy nhất.

Initiation là đầu phễu. Không dùng nó thay cho kết quả hoàn tất, quyền kiểm soát account đã phục hồi hoặc session trái phép đã bị loại bỏ.

## 14. Bài tập vận dụng

### Bài tập 1: Client tự retry

Trong một phút có 100 ý định mới, mỗi ý định được client gửi ba lần với cùng idempotency key. Service trả lại kết quả cũ cho hai lần retry.

Hãy nêu số request và số initiation theo contract của bài.

Gợi ý: 300 request và 100 initiation. Counter tăng ở mỗi request sẽ đo lưu lượng request, không đo số ý định mới.

### Bài tập 2: Mẫu số là login thành công

Sau sự cố đăng nhập, login thành công giảm một nửa nhưng số initiation không đổi. Dashboard lấy initiation chia login thành công và báo tỷ lệ tăng gấp đôi.

Hãy phân tích kết luận.

Gợi ý: phép chia có thể đúng về số học nhưng mẫu số phản ứng trực tiếp với sự cố. Nó không chứng minh số người cần recovery tăng gấp đôi. Cần tên chỉ số đúng, population phù hợp và dữ liệu login journey nếu muốn đo chuyển sang recovery.

### Bài tập 3: Counter đột ngột giảm

Một instance restart làm giá trị counter trở về 0. Kỹ sư lấy tổng counter hiện tại trừ tổng của 5 phút trước và nhận số âm.

Hãy đề xuất cách tính.

Gợi ý: dùng phép tính rate trên từng counter series rồi tổng hợp, giữ các label xác định series. Đồng thời xem target bị mất và giới hạn quan sát; không ép số âm thành 0 rồi coi đó là đủ.

### Bài tập 4: Cohort còn mở

Cohort hôm nay có 10.000 journey nhưng nhiều journey mới chỉ được theo dõi vài phút. Cohort tuần trước đã có đủ 24 giờ.

Hãy giải thích vì sao so tỷ lệ hiện tại có thể lệch.

Gợi ý: thời gian có cơ hội xuất hiện initiation khác nhau. Dùng cohort đã trưởng thành hoặc hiển thị kết quả provisional và cùng tuổi quan sát; vẫn cần xem dữ liệu đến muộn.

### Bài tập 5: Tăng sau backlog

Pipeline ngừng 30 phút rồi giao lại toàn bộ event lúc 10:00. Biểu đồ dùng ingestedAt xuất hiện một đỉnh.

Hãy phân biệt hai câu hỏi đo lường.

Gợi ý: đỉnh đó phản ánh tải nhận event tại collector. Muốn phân tích nhu cầu theo thời gian nghiệp vụ, dùng recordedAt với chính sách late arrival và revision.

### Bài tập 6: Thiếu parent reference trên mobile

Số initiation chuẩn trên mobile ổn định, nhưng tỷ lệ journey có recovery giảm mạnh sau release. Kiểm tra cho thấy parent reference không còn được gửi theo giao thức.

Hãy đưa ra kết luận và bước tiếp theo.

Gợi ý: chưa có bằng chứng nhu cầu giảm. Cần sửa liên kết, đánh dấu khoảng dữ liệu bị ảnh hưởng và đánh giá khả năng tính lại từ nguồn hợp lệ; không gán parent bằng IP để che khoảng trống.

### Bài tập 7: Đòi thu thập token để khử trùng

Một đề xuất muốn ghi recovery token plaintext làm khóa distinct trong kho analytics.

Hãy đề xuất lựa chọn khác.

Gợi ý: dùng initiation reference không mang quyền, được tạo và quản lý tại server. Khóa distinct phục vụ đo lường không cần là bí mật cho phép hoàn tất recovery.

## 15. Những điều cần giữ khi sử dụng chỉ số

Một con số initiation rate có ý nghĩa khi biết chính xác điều gì được đếm, ở điểm nào, trong phạm vi nào và với dữ liệu đầy đủ đến đâu.

Tần suất giúp quan sát tải và biến động nhu cầu được ghi nhận. Tỷ lệ theo cohort giúp xem một population xác định chuyển sang recovery như thế nào. Cả hai đều cần được đọc cùng chất lượng telemetry, thay đổi traffic và bằng chứng của luồng xác thực.

Trong một hệ thống phục hồi tài khoản, giá trị của phép đo nằm ở việc giúp phát hiện và giải thích thay đổi, đồng thời giữ con đường khôi phục hợp lệ và những ràng buộc bảo vệ quyền truy cập.

## Tài liệu tham khảo

- [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): loại metric và chi phí của label.
- [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): hành vi của rate, increase và xử lý counter reset.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): tránh account enumeration và kiểm soát yêu cầu recovery tự động.
