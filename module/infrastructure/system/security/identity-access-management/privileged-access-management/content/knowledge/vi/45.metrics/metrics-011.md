# PAM availability: đo khả dụng của dịch vụ truy cập đặc quyền

## 1. Mục tiêu bài học

PAM availability là mức độ dịch vụ quản lý truy cập đặc quyền sẵn sàng phục vụ những nhu cầu truy cập hợp lệ trong phạm vi đã cam kết. Một máy chủ PAM vẫn chạy chưa đủ chứng minh người quản trị có thể mở phiên, ứng dụng lấy được credential, hoặc quyền JIT được cấp và thu hồi đúng hạn.

Trong chương Metrics, chỉ số này giúp trả lời câu hỏi vận hành: **người hoặc workload có thực hiện được luồng truy cập đặc quyền được phép, trong thời gian chấp nhận được và với các kiểm soát bắt buộc hay không?** Câu trả lời phải gắn với phạm vi dịch vụ, dữ liệu đo và cửa sổ thời gian cụ thể.

Sau bài học, người học có thể:

- Xác định ranh giới dịch vụ PAM và các hành trình cần đo.
- Xây dựng chỉ số khả dụng theo yêu cầu và theo thời gian.
- Phân loại thành công, thất bại, từ chối hợp lệ và khoảng thiếu dữ liệu.
- Tính SLI, SLO, ngân sách lỗi và mức tiêu thụ ngân sách.
- Đọc dashboard mà không nhầm sức khỏe thành phần với trải nghiệm truy cập.
- Đề xuất hành động vận hành từ bằng chứng đo lường, đồng thời giữ least privilege, JIT/JEA, vault, luân chuyển credential và giám sát phiên.

Các ngưỡng, số liệu và tình huống trong bài là ví dụ để học cách đo. Chúng không phải mục tiêu mặc định cho mọi tổ chức hoặc mọi sản phẩm PAM.

## 2. Định nghĩa điều cần khả dụng

### 2.1. Dịch vụ PAM gồm nhiều hành trình khác nhau

Một tổ chức có thể dùng PAM để phục vụ cả tài khoản quản trị con người, tài khoản dịch vụ và truy cập hạ tầng nhạy cảm. Những nhu cầu này có thể đi qua các thành phần và có cam kết thời gian khác nhau.

| Hành trình | Điểm bắt đầu để đo | Điều kiện hoàn tất điển hình |
|---|---|---|
| Mở phiên quản trị tương tác | Yêu cầu hợp lệ đã đáp ứng điều kiện tiên quyết của hành trình | Phiên đến đúng target sẵn sàng trong hạn, các kiểm soát bắt buộc đã hoạt động |
| Lấy credential cho workload | Workload gửi yêu cầu hợp lệ bằng danh tính được phép | Nhận được credential đúng phạm vi, còn hiệu lực, trong hạn |
| Cấp quyền JIT | Yêu cầu đủ điều kiện cấp quyền tự động hoặc đã được phê duyệt | Quyền có hiệu lực trên đúng tài nguyên, đúng phạm vi, trong hạn |
| Thu hồi quyền khi hết hạn | Đến thời điểm phải thu hồi theo chính sách | Quyền thực tế bị loại bỏ trong hạn thu hồi đã định |
| Duy trì phiên đang chạy | Phiên đã được thiết lập thành công | Phiên duy trì được chức năng đã cam kết trong khoảng quan sát |
| Truy xuất bằng chứng kiểm toán | Người có quyền yêu cầu dữ liệu trong thời hạn lưu trữ | Truy xuất đúng bằng chứng được phép trong hạn |

Không nên gom tất cả thành một con số duy nhất rồi dùng con số đó để bảo đảm mọi hành trình. Khả dụng cấp phiên mới, khả dụng của phiên đang chạy và khả dụng của việc lấy credential có thể khác nhau trong cùng một sự cố.

Ví dụ, broker không nhận được phiên mới nhưng các phiên cũ vẫn hoạt động. Với nhóm quản trị đang làm việc, sự cố có vẻ nhỏ; với nhóm cần xử lý khẩn cấp một target khác, dịch vụ đang không đáp ứng nhu cầu.

### 2.2. Thành công phải giữ đầy đủ điều kiện bảo vệ

Một lần truy cập không trở thành “thành công” chỉ vì người dùng đến được máy đích bằng bất kỳ cách nào.

Nếu chính sách yêu cầu phê duyệt, MFA, ghi phiên hoặc giới hạn lệnh, hành trình chỉ tốt khi những điều kiện đó được đáp ứng tại thời điểm cần thiết. Một đường truy cập bỏ qua kiểm soát để làm dashboard xanh không thể được tính là thành công của hành trình PAM chuẩn.

Cũng cần phân biệt hai chiều đánh giá:

- **Khả dụng:** dịch vụ có phục vụ đúng nhu cầu hợp lệ trong hạn hay không.
- **Đúng đắn của kiểm soát:** dịch vụ có chỉ cho phép đúng quyền, đúng điều kiện và đúng thời hạn hay không.

Một quyết định từ chối đúng đối với tài khoản không đủ quyền là kết quả kiểm soát đúng. Một tài khoản đủ quyền bị chặn vì policy engine bị lỗi là một thất bại phục vụ. Hai trường hợp có thể cùng trả về trạng thái “denied” trên giao diện nhưng phải có nguyên nhân phân loại khác nhau.

Việc PAM đóng truy cập khi không thể xác minh điều kiện bảo vệ có thể là hành vi bảo vệ đúng. Nếu nhu cầu hợp lệ không được phục vụ, tác động khả dụng vẫn phải được ghi nhận; không vì hệ thống bảo vệ đúng mà xóa khoảng gián đoạn khỏi số liệu.

## 3. Chọn ranh giới đo trước khi chọn công thức

### 3.1. Khả dụng đầu cuối và khả dụng nội bộ

Đo đầu cuối nhìn từ phía người dùng hoặc workload. Nó có thể bao gồm DNS, mạng, nhà cung cấp danh tính, MFA, phê duyệt, broker, vault và kết nối đến target, tùy hợp đồng đo.

Đo nội bộ chỉ nhìn phần trách nhiệm kỹ thuật của nền tảng PAM, chẳng hạn API của vault hoặc dịch vụ thiết lập phiên sau khi đã xác thực.

Cả hai đều có ích, nhưng trả lời hai câu hỏi khác nhau:

- SLI đầu cuối cho biết người sử dụng có nhận được dịch vụ hay không.
- SLI nội bộ giúp khoanh vùng thành phần và trách nhiệm khắc phục.

Nếu IdP ngừng hoạt động và người quản trị không thể đăng nhập, SLI đầu cuối có thể ghi nhận thất bại theo phạm vi đã công bố. Một health check nội bộ của vault vẫn có thể xanh. Không được dùng kết quả xanh đó để kết luận trải nghiệm truy cập vẫn khả dụng.

### 3.2. Thời gian chờ nghiệp vụ cần được định nghĩa riêng

Một yêu cầu chờ người phê duyệt không nhất thiết phản ánh lỗi nền tảng. Có thể tách:

1. Thời gian từ gửi yêu cầu đến khi được phê duyệt.
2. Thời gian từ khi đã đủ điều kiện đến khi quyền hoặc phiên sẵn sàng.
3. Tổng thời gian người dùng chờ đầu cuối.

Nếu mục tiêu là đo tốc độ cấp quyền tự động sau phê duyệt, đồng hồ của SLI đó bắt đầu khi phê duyệt hợp lệ đã có. Thời gian chờ phê duyệt vẫn được đo và hiển thị như một phần trải nghiệm, không bị âm thầm biến mất.

Không thể lấy “thời gian xử lý sau phê duyệt” để quảng bá thành “toàn bộ thời gian truy cập” nếu hai phép đo có điểm bắt đầu khác nhau.

### 3.3. Phạm vi dịch vụ theo lịch

Một dịch vụ cam kết 24/7 khác với dịch vụ chỉ cam kết trong khung giờ hỗ trợ. Trước khi đo, cần ghi rõ lịch, múi giờ, ngày áp dụng và đối tượng được phục vụ.

Đối với tài khoản vận hành hệ thống sản xuất hoặc workload chạy liên tục, lịch đo quá hẹp có thể che khuất gián đoạn ngoài giờ nhưng vẫn gây tác động thật. Việc chọn lịch phải phù hợp nhu cầu sử dụng, không chỉ làm tỷ lệ đẹp hơn.

## 4. Thiết lập hợp đồng đo lường

Một chỉ số có thể được kiểm chứng cần nhiều thông tin hơn một tên metric và một ngưỡng phần trăm.

| Thuộc tính | Nội dung cần chốt |
|---|---|
| Tên hành trình | Ví dụ: thiết lập phiên SSH có ghi phiên đến nhóm target sản xuất |
| Nhóm đối tượng | Người quản trị, workload, khu vực, lớp quan trọng của target |
| Ranh giới | Bắt đầu ở đâu, kết thúc ở đâu, dependency nào nằm trong phép đo |
| Nhu cầu hợp lệ | Cách xác định yêu cầu đủ điều kiện theo chính sách |
| Điều kiện tốt | Kết quả đúng, kiểm soát đủ, hoàn tất trước deadline |
| Đơn vị đo | Một logical request, một phiên, một cơ hội thu hồi, hoặc một khoảng thời gian |
| Cửa sổ | Tháng lịch, cửa sổ trượt hoặc khoảng theo hợp đồng |
| Trường hợp loại trừ | Danh sách cố định, có lý do, được công bố trước |
| Dữ liệu thiếu | Cách phát hiện, cách báo cáo, điều kiện chưa thể kết luận |
| Nguồn bằng chứng | Client, gateway, audit, probe và hệ thống đích có liên quan |
| Chủ sở hữu | Người chịu trách nhiệm định nghĩa, vận hành và duyệt thay đổi |

Ví dụ hợp đồng thu gọn cho một hành trình:

~~~yaml
measurement:
  journey: privileged_session_establishment
  population: production_admins_region_a
  boundary: eligible_request_to_target_session_ready
  unit: logical_request
  deadline_seconds: 10
  good_requires:
    - policy_allows_requested_scope
    - required_approval_and_authentication_satisfied
    - target_session_ready
    - required_session_controls_active
  window: calendar_month_utc
  objective_percent: 99.9
  missing_final_outcome: unresolved_until_reconciled
~~~

Đây là mô hình minh họa cho thiết kế phép đo, không phải cấu hình của một sản phẩm cụ thể. Thuộc tính `population` phải đủ chính xác để người khác có thể tái tạo cùng tập dữ liệu.

Khi thay đổi deadline, nhóm target hoặc cách xác định yêu cầu hợp lệ, cần tạo phiên bản định nghĩa mới và ghi thời điểm áp dụng. Nếu không, biến động của tỷ lệ có thể chỉ do thay cách đếm.

## 5. Tính khả dụng theo yêu cầu

### 5.1. SLI cơ bản

Với một tập yêu cầu đã xác định và đã có kết quả cuối:

~~~text
N = số logical request hợp lệ nằm trong cửa sổ đo
G = số logical request đáp ứng đầy đủ tiêu chí tốt

Availability_request = G / N × 100%
~~~

Trong đó:

- “Logical request” là một nhu cầu nghiệp vụ duy nhất, có định danh để gắn các lần thử lại.
- Yêu cầu tốt phải thành công trong deadline của chính hành trình đó.
- Một yêu cầu trả về kết quả đúng nhưng quá deadline không thuộc G.
- Mẫu số phải phản ánh nhu cầu hợp lệ, không chỉ những yêu cầu đã đến được backend.

Nếu người dùng không kết nối được gateway, backend có thể không có bản ghi nào. Chỉ đếm các log thành công ở backend sẽ tạo mẫu số sai và bỏ mất chính thời gian dịch vụ ngừng phục vụ.

### 5.2. Phân loại kết quả

| Kết quả quan sát | Xử lý đối với SLI phục vụ yêu cầu hợp lệ |
|---|---|
| Đúng credential hoặc phiên đúng target, đủ kiểm soát, trong hạn | Good |
| Lỗi dịch vụ, timeout hoặc kết nối thất bại trong phạm vi đo | Bad |
| Thành công sau deadline | Bad đối với SLI có deadline |
| Người không có quyền bị từ chối đúng | Theo dõi riêng về quyết định chính sách; không trộn vào nhu cầu được phép phục vụ |
| Người có quyền bị từ chối do lỗi triển khai chính sách | Bad |
| Workload gửi thông tin đầu vào không hợp lệ | Phân loại lỗi đầu vào theo hợp đồng, có số lượng riêng |
| Người dùng chủ động hủy trước khi dịch vụ có lỗi | Xử lý theo quy tắc hủy đã chốt; không tự động coi mọi hủy là loại trừ |
| Chưa có bằng chứng về kết quả cuối | Unresolved hoặc unknown, cần đối soát |

Cần tránh phân loại vòng tròn: “yêu cầu nào PAM cho phép mới là yêu cầu hợp lệ”. Nếu một bản triển khai policy vô tình chặn toàn bộ quản trị viên, định nghĩa đó có thể loại mọi thất bại ra khỏi mẫu số.

Tính hợp lệ cần dựa vào điều kiện nghiệp vụ, danh tính, tài nguyên và chính sách đã được phê duyệt. Khi có tranh chấp hoặc chưa đủ bằng chứng, giữ trạng thái chưa xác định và điều tra; không ép thành một lượt từ chối đúng.

### 5.3. Retry không được thay đổi đơn vị đếm

Giả sử workload cần lấy một credential. Lần thử đầu timeout, lần hai gặp lỗi, lần ba thành công.

- Nếu deadline cho logical request là 5 giây và lần ba hoàn tất trong 4 giây, nhu cầu này có thể được tính tốt theo định nghĩa đó.
- Nếu lần ba hoàn tất sau 8 giây, nó là nhu cầu hoàn tất quá hạn.
- Hai lỗi đầu vẫn là tín hiệu vận hành quan trọng và nên có chỉ số theo attempt riêng.

Không được vừa tính ba attempt trong mẫu số của một giai đoạn, vừa tính một logical request ở giai đoạn khác. Cũng không được reset đồng hồ mỗi lần retry để biến một trải nghiệm chờ dài thành nhiều lần thử “nhanh”.

Một `request_id` hoặc `journey_id` ổn định giúp nhóm các attempt, kiểm tra deadline từ thời điểm bắt đầu ban đầu và tránh đếm trùng sự kiện.

### 5.4. Ví dụ có số liệu

Trong một cửa sổ đo, hành trình lấy credential có 20.000 logical request hợp lệ. Các nhóm kết quả sau không chồng lấn:

| Kết quả | Số lượng |
|---|---:|
| Đúng phạm vi, đủ điều kiện, trong hạn | 19.970 |
| Lỗi dịch vụ được xác nhận | 10 |
| Trả kết quả đúng nhưng quá deadline | 12 |
| Timeout được phía gọi xác nhận là thất bại | 8 |
| Tổng | 20.000 |

~~~text
Availability = 19.970 / 20.000 × 100% = 99,85%
Bad requests = 30
~~~

Nếu mục tiêu là 99,9% cho cùng mẫu số, số yêu cầu xấu cho phép là:

~~~text
Allowed_bad = 20.000 × (1 − 0,999) = 20
Consumed_bad = 30
Remaining_budget = 20 − 30 = −10
Budget_consumption = 30 / 20 = 150%
~~~

Tỷ lệ 99,85% nghe có vẻ cao nhưng vẫn chưa đạt SLO 99,9%. Đọc dashboard cần so với mục tiêu và mức tiêu thụ ngân sách, không chỉ nhìn số chữ số 9.

## 6. Tính khả dụng theo thời gian

### 6.1. Công thức và điều kiện “khoảng thời gian xấu”

Với phép đo theo thời gian:

~~~text
T = tổng thời gian nằm trong phạm vi cam kết
D = tổng thời gian dịch vụ không đáp ứng tiêu chí khả dụng

Availability_time = (T − D) / T × 100%
~~~

Điều quan trọng nhất là cách xác định D. Ví dụ, tổ chức có thể coi một khoảng là xấu khi một hành trình quan trọng không thực hiện được từ vị trí quan sát đại diện, hoặc khi tỷ lệ thành công của khoảng đó xuống dưới ngưỡng đã chốt.

Phải quy định trước:

- Độ dài khoảng quan sát và tần suất probe.
- Số bằng chứng cần có để xác nhận gián đoạn.
- Điều kiện bắt đầu và kết thúc khoảng xấu.
- Cách xử lý probe mất dữ liệu hoặc vị trí quan sát bị lỗi.
- Cách ghi nhận sự cố chỉ ảnh hưởng một phần người dùng hay target.

Probe mỗi phút không chứng minh hệ thống tốt trong mọi giây giữa hai lần kiểm tra. Độ phân giải của phép đo phải xuất hiện trong phần diễn giải độ chính xác.

### 6.2. Không cộng trùng các khoảng gián đoạn

Trong một tháng giả định dài 30 ngày, dịch vụ được đo 24/7:

~~~text
T = 30 × 24 × 60 = 43.200 phút
~~~

Có ba khoảng lỗi thành phần ảnh hưởng cùng hành trình:

| Khoảng | Thời gian | Độ dài |
|---|---|---:|
| Broker lỗi | 09:00–09:07 | 7 phút |
| Kết nối vault lỗi | 09:03–09:15 | 12 phút |
| Một gián đoạn khác | 17:10–17:16 | 6 phút |

Hai khoảng đầu chồng nhau 4 phút. Tổng gián đoạn của hành trình là hợp các khoảng, không phải tổng thời gian mọi component báo lỗi:

~~~text
D = (7 + 12 − 4) + 6 = 21 phút
Availability_time = (43.200 − 21) / 43.200 × 100%
                  ≈ 99,95139%
~~~

Nếu SLO thời gian là 99,95%, ngân sách tương ứng trong ví dụ là:

~~~text
Allowed_downtime = 43.200 × 0,0005 = 21,6 phút
Remaining_budget = 21,6 − 21 = 0,6 phút
~~~

Phần ngân sách còn lại chỉ là 36 giây trong mô hình tính toán này. Nếu công cụ đo chỉ có độ phân giải theo phút, cần nêu giới hạn đó và không trình bày 36 giây như mức chính xác đã quan sát được.

Cũng không được làm tròn sớm tỷ lệ để che việc gần hết ngân sách. Giữ số liệu gốc cho tính toán, chỉ làm tròn khi hiển thị.

### 6.3. Hai loại khả dụng có thể dẫn đến kết luận khác nhau

Gián đoạn 5 phút trong giờ cao điểm có thể ảnh hưởng hàng nghìn yêu cầu. Gián đoạn 5 phút khi ít người dùng có thể ảnh hưởng rất ít yêu cầu. Hai trường hợp giống nhau trong SLI theo thời gian, nhưng khác nhau trong SLI theo yêu cầu.

Ngược lại, nếu không có lưu lượng trong một giờ, SLI theo yêu cầu không có mẫu số để kết luận. Không được tự gán 100% chỉ vì không có lỗi được ghi nhận. Probe hoặc phép đo theo thời gian có thể cung cấp góc nhìn bổ sung.

Chỉ số theo thời gian và theo yêu cầu nên được hiển thị cùng định nghĩa riêng. Không đổi trực tiếp một tỷ lệ theo yêu cầu thành số phút downtime nếu chưa có mô hình dữ liệu chứng minh mối liên hệ đó.

## 7. Dữ liệu thiếu và nhu cầu không đến được PAM

### 7.1. Mất log không có nghĩa là không có lỗi

Trong sự cố, chính hệ thống tạo log có thể ngừng hoạt động. Nếu dashboard chỉ lấy dữ liệu từ thành phần đang lỗi, khoảng nghiêm trọng nhất có thể xuất hiện như “không có traffic”.

Nên kết hợp các góc nhìn phù hợp:

- Sự kiện ở phía gọi hoặc điểm tiếp nhận độc lập.
- Kết quả từ gateway hoặc broker.
- Audit của vault và policy engine.
- Probe từ vị trí đại diện cho nhóm sử dụng.
- Bằng chứng trên target cho các hành trình cần xác nhận quyền thực tế.

Không nguồn nào tự động là sự thật duy nhất cho mọi trường hợp. Khi chúng mâu thuẫn, cần đối soát bằng định danh hành trình và mốc thời gian.

### 7.2. Phân biệt unknown với bad đã xác nhận

Nếu phía gọi xác nhận timeout, đó có thể là thất bại đã biết của hành trình, dù log server chưa về. Nếu chỉ thiếu bản ghi hoàn tất và chưa biết kết quả thực tế, trạng thái thích hợp là unresolved.

Ví dụ có 1.000 nhu cầu hợp lệ đã biết ở điểm tiếp nhận:

~~~text
Good_confirmed = 970
Bad_confirmed = 10
Unresolved = 20
~~~

Nếu cả 1.000 nhu cầu đều đã được kiểm kê đầy đủ, giới hạn có thể trình bày là:

~~~text
Lower_bound = 970 / 1.000 = 97%
Upper_bound = (970 + 20) / 1.000 = 99%
Outcome_completeness = (970 + 10) / 1.000 = 98%
~~~

Khoảng 97%–99% thể hiện điều chưa biết, không phải khoảng tin cậy thống kê. Nó chỉ đúng dưới giả định tổng số 1.000 nhu cầu đã đầy đủ. Nếu còn nhu cầu thất bại trước điểm tiếp nhận mà chưa được đếm, chưa thể dùng khoảng đó để kết luận khả dụng đầu cuối.

Một tổ chức có thể định nghĩa trước rằng kết quả chưa xác nhận sau hạn đối soát sẽ được tính xấu theo cách bảo thủ. Quy tắc đó phải cố định, công khai và có cơ chế hiệu chỉnh khi nhận được bằng chứng mới. Không áp dụng chọn lọc chỉ trong tháng tỷ lệ thấp.

### 7.3. Thời điểm dữ liệu đến khác thời điểm sự kiện

Cửa sổ đo thường cần gắn với thời điểm sự kiện hoặc thời điểm bắt đầu logical request theo hợp đồng. Log đến trễ không nên bị đẩy sang tháng sau chỉ để tháng hiện tại đạt mục tiêu.

Với yêu cầu sát cuối cửa sổ, cần chờ đủ deadline và khoảng đối soát đã định trước khi chốt báo cáo. Báo cáo tạm thời phải có nhãn “provisional”, thời điểm cập nhật và tỷ lệ kết quả chưa xác định.

## 8. Tách các lớp khả dụng đặc thù của PAM

### 8.1. Cấp truy cập mới và duy trì truy cập hiện có

Một phiên đã mở có thể vẫn chạy khi cổng cấp phiên mới bị lỗi. Tương tự, một workload có thể tiếp tục dùng credential hoặc lease còn hiệu lực trong thời gian dịch vụ phát credential gặp sự cố.

Cần đo riêng ít nhất những khía cạnh liên quan đến thiết kế thực tế:

| Lớp quan sát | Câu hỏi cần trả lời |
|---|---|
| New access | Có mở được phiên, lấy credential mới hoặc cấp quyền mới không? |
| Existing session | Các phiên đã mở có tiếp tục hoạt động đúng cam kết không? |
| Lease renewal | Workload có gia hạn được lease trước khi hết hạn không? |
| Revocation | Quyền hoặc credential phải thu hồi có bị thu hồi đúng hạn không? |
| Required evidence | Bằng chứng bắt buộc có được tạo và truy xuất theo cam kết không? |

Credential còn dùng được trong ứng dụng không chứng minh vault đang cấp phát tốt. Phiên còn chạy không chứng minh hệ thống đang thu hồi quyền đúng hạn. Các trạng thái này cần được đặt cạnh nhau để người trực vận hành nhìn thấy rủi ro tích lũy.

### 8.2. Rotation và availability có quan hệ nhưng không đồng nhất

Luân chuyển credential có thể hoàn tất trên vault nhưng chưa đồng bộ đúng với ứng dụng hoặc target. Nếu kiểm tra chỉ dừng ở trạng thái job “completed”, dashboard có thể xanh trong khi ứng dụng không xác thực được.

Đối với đường sử dụng liên quan, cần xem kết quả phục vụ sau rotation:

- Credential được cấp có còn được target chấp nhận không?
- Ứng dụng có lấy và sử dụng được phiên bản đúng không?
- Một lỗi đồng bộ có làm mất khả năng truy cập trong khoảng nào không?
- Có phát sinh việc dùng credential cũ ngoài chính sách hay không?

Chỉ số job rotation thành công vẫn cần thiết, nhưng là chỉ số quá trình. Availability của hành trình thể hiện kết quả người dùng hoặc workload thực sự nhận được.

### 8.3. Khả dụng của đường break-glass

Đường truy cập khẩn cấp cần được kiểm tra và đo theo quy trình riêng đã được phê duyệt. Nó không tự động biến một thất bại trên đường chuẩn thành thành công.

Ví dụ, trong 15 phút broker chính bị lỗi, hai quản trị viên sử dụng được đường khẩn cấp. Có thể báo cáo:

- Hành trình chuẩn bị gián đoạn 15 phút.
- Cơ chế khẩn cấp đã phục vụ hai nhu cầu theo quy trình.
- Có bằng chứng truy cập, giới hạn phạm vi và việc xử lý sau sử dụng.
- Tác động vận hành được giảm nhờ phương án khẩn cấp.

Không được xóa 15 phút khỏi SLI đường chuẩn chỉ vì có phương án dự phòng ngoài hành trình đó. Nếu một thiết kế dự phòng nằm ngay trong ranh giới dịch vụ chuẩn và vẫn đáp ứng toàn bộ tiêu chí tốt, kết quả đầu cuối có thể tiếp tục được tính tốt; ranh giới đó phải có từ trước sự cố.

## 9. Thiết kế nguồn đo và kiểm tra tổng hợp

### 9.1. Probe cần đi đủ xa để có ý nghĩa

Một probe kiểm tra cổng TCP hoặc trang đăng nhập chỉ chứng minh một phần rất nhỏ của hệ thống. Nó không chứng minh đường đến target, tính hợp lệ của credential hoặc trạng thái của kiểm soát phiên.

Nên có nhiều mức probe với nhãn rõ ràng:

1. Kiểm tra thành phần, như API còn phản hồi.
2. Kiểm tra hành trình trong môi trường hoặc tài nguyên kiểm thử chuyên dụng.
3. Đối chiếu với kết quả truy cập thật đã được tổng hợp và bảo vệ dữ liệu.

Một probe hành trình PAM có thể đi qua xác thực bằng danh tính kiểm thử, kiểm tra quyền được cấp cho target kiểm thử, mở phiên với thao tác vô hại, xác nhận dấu hiệu sẵn sàng, rồi kết thúc và dọn tài nguyên phát sinh.

Quyền của probe phải tối thiểu, giới hạn trong tài nguyên kiểm thử đã cho phép. Không cho probe quyền quản trị rộng trên production chỉ để đo khả dụng, cũng không chạy lệnh gây thay đổi dữ liệu nghiệp vụ như một health check.

### 9.2. Đại diện cho vị trí sử dụng

Probe đặt cùng mạng với vault có thể xanh trong khi người quản trị ở khu vực khác không đến được broker. Khi dịch vụ phục vụ nhiều khu vực hoặc nhiều kênh truy cập, cần có vị trí quan sát tương ứng.

Không nhất thiết cần probe cho từng cá nhân. Cần lựa chọn các đường có ý nghĩa: khu vực mạng, miền danh tính, loại target, lớp quan trọng của dịch vụ và kiểu hành trình.

Kết quả probe phải tách khỏi lưu lượng thật. Nếu một probe chạy liên tục tạo ra hàng chục nghìn lượt tốt, việc trộn vào mẫu số có thể che hàng trăm lần thất bại của người dùng.

### 9.3. Bảo vệ dữ liệu đo

Thông tin phục vụ đo lường nên đủ để tái tạo kết quả, nhưng không được biến telemetry thành nơi rò rỉ quyền đặc biệt.

Có thể lưu các trường như:

~~~text
journey_id
attempt_id
event_time
journey_type
region
target_class
eligibility_result
policy_reason_code
outcome
duration_ms
required_controls_ok
definition_version
~~~

Không đưa mật khẩu, private key, token, toàn bộ credential hoặc nội dung nhạy cảm của phiên vào nhãn metric hay log đo availability. Với định danh người dùng và target, cân nhắc dùng định danh thay thế và phân quyền truy cập theo nhu cầu điều tra.

`journey_id` nên xuất hiện trong log hoặc kho sự kiện phục vụ đối soát. Không nên dùng mỗi định danh duy nhất đó làm nhãn time series vì số tổ hợp có thể tăng rất nhanh. Dashboard thường tổng hợp theo các chiều có giới hạn như hành trình, khu vực và lớp target.

## 10. SLO, ngân sách lỗi và cảnh báo

### 10.1. Chọn mục tiêu theo nhu cầu phục vụ

SLO là mục tiêu nội bộ gắn với SLI đã định nghĩa. Một cam kết hợp đồng với khách hàng có thể có phạm vi, cửa sổ và ngoại lệ khác. Không dùng chung tên rồi coi chúng là tương đương.

Mục tiêu nên xuất phát từ tác động nếu truy cập không thực hiện được: vận hành hệ thống quan trọng, ứng phó sự cố, ứng dụng phụ thuộc credential hoặc công việc quản trị thông thường.

Ví dụ hai mục tiêu riêng:

| Hành trình minh họa | Điều kiện tốt | SLO minh họa |
|---|---|---|
| Mở phiên quản trị sản xuất | Đủ kiểm soát, phiên sẵn sàng trong 10 giây sau khi đủ điều kiện | 99,9% logical request |
| Lấy credential cho workload quan trọng | Đúng phạm vi, còn hiệu lực, hoàn tất trong 2 giây | 99,95% logical request |

Hai tỷ lệ trên không nên được lấy trung bình để thành một SLO PAM chung. Nếu cần một chỉ số quản trị tổng hợp, phải mô tả trọng số, phạm vi và vẫn giữ kết quả từng hành trình bên cạnh.

### 10.2. Mức đốt ngân sách lỗi

Với cùng định nghĩa theo yêu cầu:

~~~text
Allowed_error_fraction = 1 − SLO_fraction
Observed_error_fraction = Bad / Eligible_requests
Burn_rate = Observed_error_fraction / Allowed_error_fraction
~~~

Nếu SLO là 99,9%, phần lỗi cho phép là 0,1%. Trong một khoảng có lỗi 1%:

~~~text
Burn_rate = 1% / 0,1% = 10
~~~

Điều đó có nghĩa là tỷ lệ lỗi của khoảng này cao gấp 10 lần mức phân bổ đều của mục tiêu. Nó không tự chứng minh toàn bộ ngân sách tháng sẽ hết sau một thời gian cố định, vì lưu lượng và tỷ lệ lỗi trong tương lai có thể thay đổi.

Nên xem đồng thời khoảng ngắn để nhận ra sự cố đang tăng nhanh và khoảng dài để tránh phản ứng quá mức với một mẫu nhỏ. Với hành trình ít lượt sử dụng, một tỷ lệ lớn có thể chỉ đến từ vài yêu cầu; cần hiển thị số lượng, tác động và bằng chứng probe.

Một thất bại ở target cực kỳ quan trọng vẫn có thể cần xử lý ngay dù số lượng thấp. Đừng để điều kiện tối thiểu về cỡ mẫu khiến cảnh báo bỏ qua tình huống đó.

### 10.3. Cảnh báo khả dụng khác cảnh báo tài nguyên

CPU cao, hàng đợi dài, lỗi replication hoặc dung lượng gần đầy là tín hiệu dự báo và khoanh vùng. Cảnh báo availability nên dựa vào nhu cầu phục vụ bị ảnh hưởng hoặc dấu hiệu đủ mạnh cho thấy hành trình không đáp ứng được.

Một cảnh báo có ích cần chỉ ra:

- Hành trình, khu vực và lớp target bị ảnh hưởng.
- Số lượt tốt/xấu, deadline và cửa sổ tính.
- Mức tiêu thụ ngân sách và mức độ đầy đủ dữ liệu.
- Link hoặc định danh bằng chứng để người trực đối soát.
- Runbook xử lý và chủ sở hữu chịu trách nhiệm.

Không cần đợi báo cáo tháng để phản ứng với mất khả năng truy cập đang diễn ra. Báo cáo dài hạn và cảnh báo sự cố phục vụ hai mục đích khác nhau.

## 11. Các cách tổng hợp dễ làm sai kết luận

### 11.1. Lưu lượng lớn che lớp dịch vụ quan trọng

Giả sử hai nhóm trong một cửa sổ có dữ liệu:

| Nhóm | Yêu cầu tốt | Yêu cầu hợp lệ | Availability |
|---|---:|---:|---:|
| Môi trường phát triển | 99.900 | 100.000 | 99,9% |
| Target sản xuất quan trọng | 900 | 1.000 | 90% |

Tỷ lệ tổng theo số yêu cầu là:

~~~text
(99.900 + 900) / (100.000 + 1.000) × 100%
≈ 99,802%
~~~

Con số tổng cao hơn nhiều so với 90% của nhóm sản xuất quan trọng. Phải giữ phân đoạn theo mức quan trọng, thay vì chỉ hiển thị tổng module.

Ngược lại, trung bình số học của hai tỷ lệ là 94,95%, cũng không phải tỷ lệ tổng theo yêu cầu. Mỗi phép tổng hợp có ý nghĩa khác nhau; cần nói rõ đang dùng cách nào.

### 11.2. Bảo trì theo kế hoạch

Một đợt bảo trì có kế hoạch vẫn có thể gây ảnh hưởng thật. Nếu hợp đồng SLO cho phép loại trừ một số cửa sổ bảo trì, cần công bố và giữ bằng chứng về phạm vi đó.

Cách báo cáo minh bạch là hiển thị cả:

- Khả dụng theo trải nghiệm trên toàn thời gian quan sát.
- Khả dụng theo định nghĩa SLO sau các loại trừ được phê duyệt.
- Số phút và số nhu cầu bị ảnh hưởng bởi các loại trừ.

Không thêm ngoại lệ sau khi sự cố xảy ra để sửa kết quả. Cũng không đổi tên một sự cố ngoài kế hoạch thành “bảo trì” khi đã biết tác động.

### 11.3. Tính sẵn sàng của node và của dịch vụ

Hai node đều báo healthy nhưng kết nối đến target bị lỗi thì hành trình vẫn có thể không khả dụng. Một node hỏng nhưng failover hoạt động đúng và người dùng vẫn đạt deadline thì dịch vụ đầu cuối có thể vẫn tốt.

Bởi vậy, availability của node là dữ liệu chẩn đoán; nó không thay thế availability của hành trình. Công thức nhân tỷ lệ khả dụng của các thành phần cũng không đủ để thay cho đo thực tế, nhất là khi có lỗi chung về mạng, danh tính, cấu hình hoặc nguồn điện.

### 11.4. RTO không phải tỷ lệ availability

RTO diễn đạt mục tiêu thời gian khôi phục trong một tình huống được xác định. Availability diễn đạt tỷ lệ phục vụ trong cửa sổ đo.

Một đội có thể khôi phục đúng RTO sau một sự cố nhưng vẫn không đạt SLO tháng do có quá nhiều sự cố. Ngược lại, tỷ lệ tháng có thể cao trong khi một nhu cầu khẩn cấp duy nhất bị gián đoạn quá lâu. Hai thông tin nên cùng tồn tại để phản ánh cả độ thường xuyên và độ dài tác động.

## 12. Dashboard tối thiểu có thể dùng để ra quyết định

Một dashboard PAM availability hữu ích nên cho người xem hiểu nhanh dịch vụ nào đang bị ảnh hưởng, mức độ ảnh hưởng và độ chắc chắn của dữ liệu.

| Khu vực hiển thị | Nội dung chính |
|---|---|
| Kết quả đầu cuối | SLI, SLO, số good/bad/eligible của từng hành trình |
| Tác động theo phân đoạn | Khu vực, lớp target, nhóm người dùng/workload quan trọng |
| Ngân sách lỗi | Cho phép, đã dùng, còn lại và burn rate theo cửa sổ |
| Duy trì và thu hồi | Phiên đang chạy, cấp mới, gia hạn, thu hồi quyền |
| Chất lượng dữ liệu | Unknown, completeness, nguồn mất dữ liệu, thời điểm cập nhật |
| Chẩn đoán thành phần | IdP/MFA, broker, vault, policy, mạng và target có liên quan |
| Dấu mốc vận hành | Deploy, rotation, failover, bảo trì và incident |
| Định nghĩa | Phiên bản SLI, deadline, lịch phục vụ và ngoại lệ |

Đường biểu diễn nên giữ số lượng bên cạnh phần trăm. Giá trị “99,9% với 10 yêu cầu” và “99,9% với một triệu yêu cầu” có mức thông tin rất khác nhau.

Khi dữ liệu chưa đủ để kết luận, dashboard cần hiển thị trạng thái đó thay vì tô xanh mặc định. Các báo cáo đã chốt nên giữ phiên bản dữ liệu hoặc dấu vết hiệu chỉnh để người kiểm toán có thể lần lại.

## 13. Tình huống vận hành: broker lỗi sau thay đổi cấu hình

Một nhóm triển khai thay đổi cấu hình broker. Sau đó:

- Trang đăng nhập vẫn mở bình thường.
- API vault vẫn trả lời health check.
- Phiên đã mở tiếp tục hoạt động.
- Nhiều yêu cầu mở phiên mới đến một nhóm target bị timeout.
- Phần lớn request ở môi trường phát triển vẫn thành công.

Nếu dashboard chỉ nhìn health check của vault và lưu lượng tổng, sự cố có thể bị đánh giá thấp. Cách đọc theo hành trình sẽ cho thấy cấp truy cập mới vào nhóm target bị ảnh hưởng đã giảm, trong khi duy trì phiên chưa giảm tương ứng.

### 13.1. Thu thập bằng chứng theo tác động

Đội vận hành kiểm tra:

1. Các logical request hợp lệ bắt đầu trong khoảng ảnh hưởng.
2. Kết quả cuối và deadline từ phía gọi, không chỉ log broker.
3. Mức ảnh hưởng theo nhóm target và khu vực.
4. Thời điểm thay đổi cấu hình so với thời điểm bắt đầu lỗi.
5. Trạng thái ghi phiên và các kiểm soát bắt buộc khi thử khôi phục.
6. Các yêu cầu chưa xác định kết quả để đối soát sau khi log về đủ.

Cấu hình thay đổi gần thời điểm lỗi là giả thuyết nguyên nhân, chưa phải bằng chứng kết luận. Cần đối chiếu thêm phạm vi tác động và kết quả xác minh của đội vận hành.

### 13.2. Đánh giá khôi phục theo chính hành trình bị lỗi

Sau khi áp dụng phương án khôi phục được phép, không chỉ kiểm tra broker “up”. Cần xác nhận:

- Mở phiên mới đến đúng lớp target đã bị ảnh hưởng.
- Thời gian thiết lập nằm trong deadline.
- Phê duyệt, quyền, giới hạn phiên và bằng chứng bắt buộc vẫn đúng.
- Lưu lượng thật và probe đại diện cùng cho thấy dịch vụ phục hồi.
- Các nhu cầu tồn đọng được xử lý mà không cấp quyền thừa hoặc tạo phiên trùng.

Việc kết thúc incident và việc hoàn tất đối soát số liệu có thể khác thời điểm. Dịch vụ đã phục hồi không có nghĩa toàn bộ request trong thời gian lỗi đã có kết quả đầy đủ.

### 13.3. Chuyển kết quả đo thành cải tiến

Nếu lỗi chủ yếu xuất hiện sau deploy, đội có thể cải thiện kiểm tra trước thay đổi và điều kiện rollback. Nếu lỗi tập trung vào một đường mạng, ưu tiên cải thiện đường đó. Nếu credential cấp đúng nhưng ứng dụng sử dụng thất bại sau rotation, cần xem lại chuỗi đồng bộ và bằng chứng sử dụng.

Mục tiêu là giảm nhu cầu bị ảnh hưởng và thời gian gián đoạn, đồng thời duy trì các kiểm soát đặc quyền. Tăng uptime bằng cách cấp quyền lâu dài, bỏ MFA hoặc nới phạm vi tài khoản không phải kết quả đạt yêu cầu của bài toán PAM.

## 14. Bài tập thực hành

### Bài tập 1: tính SLI theo deadline

Một hành trình mở phiên có 5.000 logical request hợp lệ:

- 4.975 hoàn tất đúng điều kiện trong deadline.
- 10 thất bại do lỗi dịch vụ.
- 15 hoàn tất đúng target nhưng quá deadline.
- Có thêm 200 lượt bị từ chối đúng vì không có quyền; chúng được theo dõi trong tập quyết định chính sách riêng.

Hãy tính SLI availability, số lượt xấu, ngân sách cho phép nếu SLO là 99,5%, và xác định mục tiêu có đạt hay không.

Gợi ý đối chiếu:

~~~text
Availability = 4.975 / 5.000 × 100% = 99,5%
Bad = 10 + 15 = 25
Allowed_bad = 5.000 × 0,005 = 25
Remaining_budget = 0
~~~

Mục tiêu vừa đạt trong cửa sổ này nhưng không còn ngân sách. Việc thêm 200 lượt từ chối đúng vào mẫu số phục vụ sẽ làm thay đổi ý nghĩa chỉ số.

### Bài tập 2: xác định giới hạn của dữ liệu

Trong một giờ, vault không phát sinh log và dashboard ghi “0 lỗi, 0 request”. Probe từ khu vực quản trị báo không kết nối được gateway.

Hãy giải thích vì sao chưa thể kết luận availability là 100%. Cần bổ sung nguồn nào để kiểm kê nhu cầu thực và xác nhận khoảng gián đoạn?

Hướng trả lời: số request bằng 0 làm SLI theo yêu cầu không xác định cho nguồn đó. Mất log có thể là triệu chứng của sự cố; probe cung cấp bằng chứng về đường truy cập nhưng không tự đếm được toàn bộ nhu cầu thật. Cần đối chiếu phía gọi, điểm tiếp nhận, dữ liệu mạng phù hợp và các nguồn độc lập theo ranh giới đã chốt.

### Bài tập 3: tách các hành trình

Vault ngừng cấp credential mới trong 12 phút. Các workload đang giữ credential còn hiệu lực tiếp tục chạy, nhưng một số lần gia hạn thất bại.

Hãy đề xuất ít nhất ba chỉ số riêng để tránh kết luận “ứng dụng vẫn chạy nên PAM khả dụng”.

Một thiết kế phù hợp sẽ tách cấp credential mới, gia hạn lease và khả năng tiếp tục dùng quyền hiện có. Nếu đến hạn thu hồi trong cùng khoảng, cần theo dõi thêm kết quả thu hồi thay vì mặc định hệ thống đã làm được.

### Bài tập 4: phát hiện thay đổi định nghĩa

Tháng trước SLI đo từ khi người dùng gửi yêu cầu. Tháng này nó đo từ khi đã được phê duyệt, nhưng dashboard giữ nguyên tên và kết luận thời gian truy cập được cải thiện mạnh.

Hãy chỉ ra vấn đề và cách sửa báo cáo.

Hướng trả lời: hai tháng đang đo hai ranh giới khác nhau. Cần công bố phiên bản định nghĩa, tách thời gian chờ phê duyệt khỏi thời gian cấp quyền, rồi chỉ so sánh những tập dữ liệu có cùng ý nghĩa hoặc tính lại bằng dữ liệu đủ điều kiện.

## 15. Các điểm cần nhớ khi sử dụng chỉ số

PAM availability phải gắn với một hành trình, một tập nhu cầu và một tiêu chí tốt rõ ràng. Tỷ lệ chỉ có giá trị khi mẫu số phản ánh đúng nhu cầu hợp lệ và các thất bại không biến mất vì thiếu log, retry hoặc thay đổi định nghĩa.

Khi đánh giá dịch vụ, hãy đọc kết quả đầu cuối cùng phân đoạn quan trọng, ngân sách lỗi và mức đầy đủ dữ liệu. Sức khỏe của vault, broker hay từng node giúp giải thích kết quả nhưng không thay thế bằng chứng phục vụ.

Một dịch vụ PAM khả dụng cần giúp đúng người hoặc workload thực hiện đúng việc trong hạn, với các kiểm soát đặc quyền đã cam kết. Đo lường tốt tạo ra cơ sở để cải thiện khả năng phục vụ mà vẫn giữ được giới hạn quyền, thời hạn truy cập và bằng chứng cần thiết.

