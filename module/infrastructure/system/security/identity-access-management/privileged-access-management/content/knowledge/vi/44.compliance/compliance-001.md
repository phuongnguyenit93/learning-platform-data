# Evidence của privileged access

Một hệ thống PAM có thể cấp quyền đúng người và ghi rất nhiều log nhưng vẫn khó trả lời một câu hỏi đơn giản: **ai đã dùng quyền gì, trên tài nguyên nào, vì lý do gì, trong khoảng thời gian nào, và dựa vào đâu để tin câu trả lời đó?** Evidence, hay bằng chứng, là những dữ liệu được thu thập và quản lý để kiểm tra các khẳng định ấy.

Trong chương Compliance của module Privileged Access Management, bài học này xem evidence dưới góc nhìn vận hành và kỹ thuật: kiểm kê tài khoản đặc quyền, least privilege, JIT/JEA, vault, luân chuyển credential, giám sát phiên và điều tra sự cố. Mục tiêu là xây dựng hồ sơ có thể truy vết và kiểm tra lại, thay vì chỉ xuất một báo cáo nhiều dòng.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Chuyển một mục tiêu kiểm soát quyền đặc biệt thành những khẳng định có thể kiểm chứng.
- Xác định bằng chứng cần có cho tài khoản quản trị, tài khoản dịch vụ và workload.
- Liên kết danh tính, yêu cầu, quyết định cấp quyền, phiên truy cập, hoạt động đích và thu hồi quyền.
- Nhận diện khoảng trống giữa việc có log và việc chứng minh kiểm soát đã hoạt động.
- Lập gói evidence có phạm vi, nguồn gốc, thông tin toàn vẹn, quyền truy cập và hạn chế rõ ràng.
- Đối soát toàn bộ tập truy cập thuộc phạm vi trước khi chọn mẫu để rà soát sâu.

Các mã kiểm soát và mốc thời gian trong bài là ví dụ nội bộ để học cách thiết kế. Chúng không phải mã của một tiêu chuẩn bên ngoài và không tự tạo ra kết luận đáp ứng một nghĩa vụ pháp lý hay chứng nhận cụ thể.

## 2. Phân biệt log, evidence và kết luận kiểm soát

### 2.1. Log là bản ghi; evidence phụ thuộc câu hỏi

Log là bản ghi về điều một thành phần quan sát hoặc thực hiện. Ví dụ, PAM ghi một sự kiện cấp lease; máy chủ đích ghi một lần đăng nhập; hệ thống quản lý công việc ghi một quyết định phê duyệt.

Một bản ghi trở thành evidence phù hợp khi có thể gắn nó với câu hỏi kiểm tra, đối tượng, thời gian, nguồn và cách diễn giải. Log đăng nhập thành công trên máy chủ có thể hỗ trợ khẳng định tài khoản đã được sử dụng, nhưng không tự chứng minh người sử dụng đã được phê duyệt.

| Dữ liệu | Có thể hỗ trợ chứng minh | Chưa đủ để chứng minh |
|---|---|---|
| Ticket đã được duyệt | Có quyết định cho một yêu cầu xác định | Quyền thực tế đúng phạm vi và đúng thời hạn |
| Sự kiện cấp quyền JIT | PAM đã ghi nhận quyết định hoặc thao tác cấp quyền | Hệ thống đích đã áp dụng quyền đúng như dự kiến |
| Bản ghi lấy credential từ vault | Một chủ thể được phép đã nhận hoặc dùng credential qua luồng được ghi nhận | Toàn bộ thao tác sau đó đều đi qua PAM |
| Phiên ghi hình | Nội dung mà cơ chế ghi hình thực sự thu được | Mọi kênh hoặc mọi hoạt động trên máy chủ đều được bao phủ |
| Sự kiện kết thúc phiên | Kết nối được quan sát đã kết thúc | Mọi token, lease và quyền tạm thời đã bị thu hồi |
| Báo cáo luân chuyển thành công | Thành phần luân chuyển báo thao tác thành công | Mọi bản sao credential cũ đều đã mất hiệu lực |

### 2.2. Kết luận phải nhỏ hơn hoặc bằng phạm vi bằng chứng

Có thể kết luận:

> Trong tập 240 phiên thuộc phạm vi đã đối soát, 238 phiên có quyết định phê duyệt phù hợp trước thời điểm bắt đầu; hai phiên còn lại thiếu bản ghi phê duyệt và đang được xác minh.

Không nên đổi câu trên thành:

> Mọi truy cập đặc quyền của doanh nghiệp đều được phê duyệt.

Kết luận thứ hai mở rộng cả tập đối tượng, khoảng thời gian và mức độ chắc chắn. Evidence tốt không chỉ làm rõ điều đã biết mà còn giữ nguyên những giới hạn của điều chưa biết.

### 2.3. Ba lớp cần tách riêng

**Thiết kế kiểm soát** mô tả điều đáng lẽ phải xảy ra: người yêu cầu không tự phê duyệt; quyền tạm thời có thời hạn; phiên thuộc nhóm xác định phải được giám sát.

**Việc vận hành kiểm soát** cho thấy các sự kiện thực tế trong kỳ: ai yêu cầu, ai duyệt, cấp gì, dùng gì, thu hồi ra sao.

**Việc rà soát kiểm soát** cho thấy người có trách nhiệm đã đối chiếu dữ liệu, xử lý sai lệch và ghi nhận kết quả. Một cấu hình chính sách đúng không thay thế bằng chứng vận hành; một báo cáo rà soát cũng không thay thế nguồn dữ liệu của báo cáo.

## 3. Bắt đầu từ khẳng định cần kiểm tra

Không nên bắt đầu bằng câu hỏi “PAM xuất được báo cáo nào?”. Hãy bắt đầu từ mục tiêu kiểm soát rồi xác định bằng chứng cần để kiểm tra mục tiêu đó.

| Mã ví dụ | Khẳng định cần kiểm tra | Bằng chứng chính | Đối soát bổ sung |
|---|---|---|---|
| PAM-EV-01 | Chủ thể dùng quyền được định danh và còn hiệu lực tại thời điểm sử dụng | ID danh tính ổn định, sự kiện xác thực, trạng thái danh tính có hiệu lực theo thời gian | Nguồn nhân sự hoặc quản lý workload, ánh xạ tài khoản đích |
| PAM-EV-02 | Quyền được cấp đúng mục đích và phạm vi đã duyệt | Yêu cầu, quyết định, phiên bản chính sách, phạm vi cấp quyền | Quyền thực tế tại đích, thời điểm bắt đầu hiệu lực |
| PAM-EV-03 | Quyền tạm thời được thu hồi theo quy định nội bộ | Lease, lịch hết hạn, kết quả thu hồi và xác minh | Trạng thái quyền đích, khả năng dùng lại token hoặc credential nếu có phép thử an toàn |
| PAM-EV-04 | Hoạt động thuộc phạm vi giám sát có thể truy vết | ID phiên, nhật ký thao tác hoặc recording theo thiết kế | Log máy chủ, cơ sở dữ liệu hoặc control plane |
| PAM-EV-05 | Credential được quản lý theo vòng đời đã xác định | ID credential hoặc phiên bản, sự kiện cấp dùng, luân chuyển và thu hồi | Kết quả xác minh trên hệ thống đích, lỗi phụ thuộc |
| PAM-EV-06 | Ngoại lệ và break-glass có người chịu trách nhiệm | Khai báo ngoại lệ, lý do, thời hạn, hồ sơ hậu kiểm | Dòng thời gian sự cố và kết quả khắc phục |

Với mỗi hàng, cần xác định thêm:

1. Kiểm soát áp dụng cho nhóm tài khoản và tài nguyên nào.
2. Hành vi nào được kỳ vọng và điều kiện nào được coi là ngoại lệ.
3. Nguồn nào có thẩm quyền cho từng loại dữ kiện.
4. Ai thu thập, ai rà soát và ai có quyền chấp nhận rủi ro.
5. Bằng chứng nào đủ để đưa ra kết luận, và thiếu gì thì phải giữ trạng thái chưa xác định.

Một kiểm soát “mọi quyền admin phải có ticket” vẫn chưa rõ nếu không định nghĩa ticket nào hợp lệ, phạm vi được duyệt, thời gian hiệu lực và cách xử lý tài khoản tự động.

## 4. Chuỗi bằng chứng của một lần truy cập

Một lần truy cập có thể tạo nhiều bản ghi ở nhiều hệ thống. Không cần ép tất cả vào cùng một file; cần nối chúng bằng các định danh ổn định và quan hệ có thể giải thích.

~~~text
Danh tính hoặc workload
        |
        v
Yêu cầu + mục đích + tài nguyên
        |
        v
Quyết định + người/chính sách phê duyệt
        |
        v
Cấp quyền / lease / credential / certificate
        |
        v
Xác thực tại đích + phiên truy cập
        |
        v
Thao tác thực tế + kết quả + thay đổi
        |
        v
Kết thúc phiên + thu hồi + xác minh
        |
        v
Đối soát + rà soát ngoại lệ + lưu evidence
~~~

Đây là mô hình cho truy cập cần phê duyệt theo yêu cầu. Với một workload được ủy quyền trước qua chính sách, nút “quyết định” có thể là đánh giá chính sách gắn với danh tính workload và bản triển khai đã duyệt, thay vì thao tác bấm duyệt của một người.

### 4.1. Những định danh thường cần giữ

- **subject_id**: định danh ổn định của người hoặc workload; tên hiển thị và email chỉ là thuộc tính hỗ trợ.
- **request_id**: yêu cầu truy cập hoặc công việc làm căn cứ.
- **decision_id**: quyết định cụ thể, bao gồm duyệt, từ chối hoặc cho phép theo chính sách.
- **grant_id / lease_id**: lần cấp quyền hoặc lease cụ thể.
- **session_id**: phiên kết nối được PAM hoặc gateway quan sát.
- **resource_id**: tài nguyên đích ổn định, đi kèm môi trường và vùng quản lý khi cần.
- **target_account_id**: tài khoản hoặc principal được hệ thống đích sử dụng.
- **credential_ref**: tham chiếu credential và phiên bản khi cần, không chứa giá trị bí mật.
- **event_id**: định danh sự kiện tại nguồn.
- **review_id**: hồ sơ rà soát gắn với tập evidence và các phát hiện.

Không mặc định mọi hệ thống dùng chung session ID. Khi cần bảng ánh xạ giữa ID của PAM và ID của máy chủ, hãy lưu nguồn tạo ánh xạ, thời điểm, cách ghép và mức độ chắc chắn. Ghép theo cùng tên tài khoản và thời gian gần nhau có thể hữu ích để điều tra, nhưng yếu hơn quan hệ được truyền trực tiếp qua một ID có kiểm soát.

### 4.2. Một ví dụ cấp quyền JIT

Người vận hành cần đọc trạng thái replication của cơ sở dữ liệu sản xuất. Yêu cầu chỉ cho phép bộ lệnh đọc được xác định trước trong 20 phút.

Evidence phù hợp cần làm rõ:

- Danh tính người vận hành và tài khoản đích được ánh xạ như thế nào.
- Người hoặc chính sách nào chấp thuận, có độc lập theo thiết kế hay không.
- Quyền thực tế là quyền đọc cần thiết hay một vai trò quản trị rộng hơn.
- Lease có hiệu lực từ lúc nào và hết hạn lúc nào.
- Phiên nào dùng lease đó, trên cụm cơ sở dữ liệu nào.
- Hoạt động quan sát được có phù hợp với phạm vi đã duyệt hay không.
- Khi hết hạn, quyền đích đã bị gỡ hay mới chỉ có một lịch thu hồi.
- Sai lệch nào được phát hiện và ai đã xử lý.

Một ticket có ghi “read-only” không chứng minh tài khoản đích chỉ có quyền đọc. Cần đối chiếu đối tượng quyền, nhóm, role hoặc cơ chế giới hạn lệnh thực tế.

## 5. Thiết kế dữ liệu evidence có thể giải thích

### 5.1. Trường tối thiểu của một sự kiện

Một sự kiện chuẩn hóa nên giữ được câu trả lời cho các câu hỏi: ai, làm gì, trên cái gì, lúc nào, kết quả gì và nguồn nào ghi nhận.

~~~json
{
  "schema_version": "1",
  "event_id": "pam-prod:event-48172",
  "event_type": "privilege.grant.created",
  "occurred_at": "2026-11-20T02:00:00Z",
  "observed_at": "2026-11-20T02:00:02Z",
  "ingested_at": "2026-11-20T02:00:05Z",
  "source_system": "pam-prod",
  "source_record_id": "event-48172",
  "subject": {
    "kind": "human",
    "id": "person-128",
    "target_account_id": "db-ops-read"
  },
  "resource_id": "db-prod-cluster-07",
  "request_id": "req-9321",
  "decision_id": "decision-9321-1",
  "grant_id": "grant-506",
  "lease_id": "lease-506",
  "policy": {
    "id": "db-operations-read",
    "version": "12"
  },
  "scope": ["replication.status.read"],
  "valid_from": "2026-11-20T02:00:00Z",
  "valid_until": "2026-11-20T02:20:00Z",
  "outcome": "success"
}
~~~

Đây là schema minh họa cho một sự kiện cấp quyền, không phải yêu cầu mọi sự kiện đều có đủ các trường như nhau. Một sự kiện từ chối có thể chưa có grant; một sự kiện thu hồi cần tham chiếu grant đã có. Quy tắc bắt buộc nên được định nghĩa theo từng loại sự kiện.

Giữ riêng dữ liệu gốc và dữ liệu chuẩn hóa. Nếu đổi tên trường, quy đổi múi giờ, giải mã mã kết quả hay gộp sự kiện, cần lưu phiên bản bộ chuyển đổi để người khác có thể tái lập cách diễn giải.

### 5.2. Ba loại thời gian khác nhau

**occurred_at** là thời điểm hành vi xảy ra theo nguồn. **observed_at** là lúc collector quan sát được sự kiện nếu thiết kế có trường này. **ingested_at** là lúc nền tảng nhận dữ liệu.

Ba mốc này có thể lệch vì buffer, mạng gián đoạn, hàng đợi hoặc đồng hồ nguồn. Vì vậy:

- Lưu múi giờ hoặc chuẩn hóa về UTC nhưng không làm mất ý nghĩa của thời gian gốc.
- Theo dõi đồng bộ thời gian và độ trễ nhận dữ liệu.
- Định nghĩa cửa sổ chờ dữ liệu đến muộn trước khi kết luận thiếu evidence.
- Khi hai nguồn lệch đồng hồ, không khẳng định thứ tự từng giây nếu chưa đủ cơ sở.
- Tách thời gian hết hạn dự kiến khỏi thời gian thu hồi được xác minh.

Nếu quyết định được ghi lúc 02:00:03 nhưng đích ghi đăng nhập lúc 02:00:01, cần điều tra độ lệch đồng hồ và ngữ nghĩa sự kiện trước khi kết luận phê duyệt sau truy cập.

### 5.3. Trạng thái lịch sử quan trọng hơn ảnh chụp hiện tại

Kiểm tra một người đã bị khóa hôm nay không cho biết họ còn hiệu lực tại thời điểm truy cập tuần trước. Tương tự, vai trò “read-only” hiện tại có thể khác vai trò cùng tên tại thời điểm phiên xảy ra.

Evidence cần giữ phiên bản hoặc ảnh chụp có thời gian hiệu lực của:

- Chính sách cấp quyền và điều kiện phê duyệt.
- Thành viên nhóm và gán role liên quan.
- Ánh xạ danh tính sang tài khoản đặc quyền.
- Danh mục tài nguyên thuộc phạm vi kiểm soát.
- Danh sách lệnh hoặc hành động được phép theo JEA.
- Ngoại lệ đang có hiệu lực.

Không nhất thiết chụp toàn bộ hệ thống cho mỗi phiên; có thể dùng nhật ký thay đổi kết hợp snapshot định kỳ nếu đủ khả năng tái dựng trạng thái tại thời điểm cần kiểm tra.

## 6. Chất lượng evidence: những thuộc tính cần xem cùng nhau

### 6.1. Phù hợp và đủ chi tiết

Bằng chứng phải trả lời đúng khẳng định. Một biểu đồ tổng số phiên không đủ để kiểm tra phê duyệt của từng phiên; một danh sách ticket không đủ để xác nhận thời điểm thu hồi.

Chi tiết cũng phải tương xứng mục đích. Để chứng minh đã xác thực bằng một cơ chế, có thể cần loại cơ chế, kết quả và tham chiếu assertion, nhưng không cần lưu OTP, private key hoặc token truy cập.

### 6.2. Đầy đủ trong phạm vi đã công bố

Tính đầy đủ luôn gắn với một tập đối tượng. “Đủ log PAM” không đồng nghĩa “đủ mọi truy cập đặc quyền” nếu tồn tại SSH trực tiếp, tài khoản cục bộ, đường truy cập khẩn cấp hoặc API không đi qua gateway.

Phải đối soát ít nhất hai chiều khi có nguồn phù hợp:

- Từ PAM sang hệ thống đích: quyền và phiên PAM đã ghi có dấu vết tương ứng tại đích không.
- Từ hệ thống đích về PAM: hoạt động đặc quyền tại đích có quan hệ hợp lệ với PAM hoặc ngoại lệ đã được công bố không.

Tài nguyên chưa được tích hợp, nguồn log đang hỏng và kênh chưa quan sát được phải xuất hiện như giới hạn hoặc phát hiện, không bị loại âm thầm khỏi báo cáo.

### 6.3. Toàn vẹn và xác thực nguồn

Hash giúp phát hiện một artifact đã thay đổi so với giá trị hash tin cậy được giữ lại. Hash không tự chứng minh artifact phản ánh sự thật, không tự xác minh người tạo, và không bảo vệ được khi cùng một người có thể sửa cả artifact lẫn manifest.

Có thể kết hợp:

- Kênh thu thập có xác thực và định danh nguồn.
- Quyền ghi tách khỏi quyền đọc/rà soát khi phù hợp.
- Kho lưu có cơ chế chống sửa hoặc hạn chế sửa theo thiết kế.
- Manifest được ký hoặc được lưu ở miền kiểm soát độc lập.
- Nhật ký truy cập, xuất dữ liệu và thay đổi cấu hình thu thập.
- Cơ chế quản lý khóa và xác minh chữ ký nếu áp dụng.

Kho bất biến chỉ bảo vệ những dữ liệu đã được đưa vào kho theo cơ chế đó. Nó không khắc phục việc nguồn bỏ sót sự kiện hoặc dữ liệu bị sửa trước khi thu thập.

### 6.4. Khả dụng và khả năng tái lập

Evidence vẫn phải đọc được sau khi phần mềm xuất báo cáo thay đổi. Gói lưu nên có schema, encoding, mô tả cột, truy vấn, bộ lọc, phiên bản công cụ và hướng dẫn xác minh.

Một recording còn tồn tại nhưng không còn player hoặc khóa giải mã cần thiết có thể không đáp ứng mục đích sử dụng. Hãy kiểm tra khả năng truy xuất và đọc thực tế, không chỉ kiểm tra dung lượng kho.

## 7. Thu thập cho các loại truy cập khác nhau

### 7.1. Truy cập tương tác của con người

Chuỗi thường gồm yêu cầu, phê duyệt, xác thực, cấp quyền, phiên và thu hồi. Cần tách tài khoản cá nhân dùng để xác thực với tài khoản đích được sử dụng để thi hành quyền.

Nếu nhiều người dùng chung một tài khoản đích thông qua PAM, evidence phải bảo toàn ánh xạ người dùng với từng phiên hoặc lần cấp credential. Chỉ biết tên tài khoản đích là chưa đủ để quy trách nhiệm cho một cá nhân.

Cũng cần hiểu phạm vi quan sát: ghi màn hình, ghi terminal, log lệnh và audit ứng dụng là những nguồn khác nhau. Không coi bản ghi màn hình là bản ghi đầy đủ mọi hành động ở tầng cơ sở dữ liệu.

### 7.2. Tài khoản dịch vụ và workload

Không áp dụng máy móc yêu cầu “một người bấm duyệt cho mỗi lần gọi API” nếu kiểm soát được thiết kế theo ủy quyền tự động. Căn cứ có thể gồm:

- Danh tính workload, môi trường và owner chịu trách nhiệm.
- Chính sách cho phép truy cập và phiên bản có hiệu lực.
- Bản triển khai hoặc pipeline làm nguồn phát sinh hành vi.
- Credential, certificate hoặc lease được cấp với phạm vi xác định.
- Kết quả sử dụng trên tài nguyên đích.
- Sự kiện hết hạn, luân chuyển hoặc thu hồi khi vòng đời thay đổi.

Không chỉ gắn evidence với tên service account. Cần phân biệt các workload hoặc deployment cùng dùng tài khoản đó nếu muốn truy vết đến nguồn thực thi. Nếu kiến trúc chưa cho phép phân biệt, phải ghi rõ hạn chế.

### 7.3. Break-glass và ngoại lệ

Một quy trình khẩn cấp có thể cho phép dùng quyền trước khi có phê duyệt thông thường. Evidence cần phản ánh đúng đường đi khẩn cấp, không tạo ticket giả có thời gian lùi để làm hồ sơ trông giống luồng chuẩn.

Hồ sơ nên liên kết:

1. Sự kiện kích hoạt và lý do dùng break-glass.
2. Danh tính hoặc cách kiểm soát người nhận quyền khẩn cấp.
3. Tài nguyên, phạm vi và thời gian sử dụng thực tế.
4. Cảnh báo, nhật ký và thông báo đã được phát.
5. Thu hồi, luân chuyển credential và khôi phục trạng thái sau sử dụng.
6. Hậu kiểm, người rà soát và hành động khắc phục.

Một ngoại lệ được chấp nhận có thời hạn vẫn là ngoại lệ; không đổi thành “đáp ứng luồng chuẩn” chỉ vì đã được ghi nhận.

## 8. Tập đối tượng và đối soát: tránh báo cáo đẹp nhưng thiếu truy cập

### 8.1. Xác định population trước khi tính tỷ lệ

Population là toàn bộ các đối tượng hoặc sự kiện thuộc phạm vi kiểm tra. Với kiểm soát phê duyệt, đơn vị kiểm tra có thể là grant; với giám sát, có thể là phiên; với vòng đời credential, có thể là lần cấp hoặc phiên bản credential.

Cần công bố:

- Khoảng thời gian sự kiện và thời điểm chốt nhận dữ liệu.
- Danh sách tài nguyên, môi trường và loại quyền.
- Đơn vị đếm và cách loại bản ghi trùng.
- Nguồn tạo population và mức bao phủ nguồn.
- Các trường hợp loại trừ cùng lý do và người phê duyệt.
- Cách xử lý bản ghi đến muộn, thiếu khóa nối hoặc nguồn bị gián đoạn.

Không dùng số phiên có recording làm mẫu số cho tỷ lệ phiên có recording. Mẫu số cần đến từ tập phiên thuộc diện phải ghi hình hoặc một nguồn độc lập đủ thẩm quyền xác định tập ấy.

### 8.2. Ví dụ đối soát hai nguồn

Trong một kỳ giả định, PAM ghi nhận 240 phiên tới nhóm máy chủ sản xuất. Audit tại đích có 243 phiên đặc quyền sau khi chuẩn hóa và loại trùng theo quy tắc đã công bố.

Khi đối chiếu:

- 240 phiên đích khớp với các phiên PAM.
- Hai phiên đích dùng kênh break-glass, có hồ sơ ngoại lệ và hậu kiểm.
- Một phiên đích chưa tìm thấy grant, phiên PAM hoặc ngoại lệ phù hợp.

Kết luận hợp lý là có một truy cập chưa giải thích được trong population đã đối soát. Chưa thể tự kết luận đó là tấn công; cũng chưa thể kết luận toàn bộ truy cập đã được kiểm soát.

Nếu nguồn audit đích bị mất dữ liệu trong một phần kỳ, con số 243 chỉ phản ánh phần quan sát được. Báo cáo phải giữ riêng phát hiện về truy cập chưa khớp và giới hạn về độ bao phủ nguồn.

### 8.3. Truy vấn minh họa để giữ lại trường hợp thiếu

Giả sử có hai tập dữ liệu đã được chuẩn hóa:

- **target_privileged_sessions**: phiên đặc quyền tại đích, có target_session_id duy nhất trong phạm vi nguồn và tài nguyên.
- **accepted_access_mapping**: các quan hệ đã được xác minh giữa phiên đích và grant PAM hoặc ngoại lệ hợp lệ. Tập này đã kiểm tra thời gian, tài nguyên, danh tính và tính hợp lệ của căn cứ.

~~~sql
SELECT
    t.source_system,
    t.resource_id,
    t.target_session_id,
    t.target_account_id,
    t.started_at,
    t.ended_at
FROM target_privileged_sessions AS t
LEFT JOIN accepted_access_mapping AS m
    ON m.source_system = t.source_system
   AND m.resource_id = t.resource_id
   AND m.target_session_id = t.target_session_id
WHERE t.started_at >= :period_start
  AND t.started_at <  :period_end
  AND m.target_session_id IS NULL;
~~~

Đây là SQL minh họa, không phải truy vấn dùng ngay cho một sản phẩm cụ thể. Cần chuẩn bị dữ liệu và tham số theo hệ thống thực tế.

Điểm cần giữ là LEFT JOIN: phiên đích thiếu ánh xạ vẫn tồn tại trong kết quả. Nếu bắt đầu bằng INNER JOIN, chính những phiên cần điều tra có thể biến mất. Cũng không được coi một chuỗi request_id bất kỳ là căn cứ hợp lệ; quan hệ cần được kiểm tra về nội dung và hiệu lực, không chỉ về sự tồn tại.

Truy vấn trên chọn phiên theo thời điểm bắt đầu. Nếu mục tiêu là mọi phiên hoạt động trong kỳ, phải định nghĩa điều kiện giao nhau với kỳ, xử lý phiên chưa kết thúc và các phiên bắt đầu trước kỳ. Đơn vị population phải nhất quán với câu hỏi kiểm soát.

## 9. Lập gói evidence có thể bàn giao

Một gói evidence nên chứa dữ liệu cần thiết và đủ thông tin để người nhận hiểu cách nó được tạo. Không nhất thiết gộp tất cả vào một file nén nếu dữ liệu nhạy cảm phải được truy cập qua kho kiểm soát riêng.

~~~text
evidence-package/
  scope.md
  manifest.json
  sources/
    pam-events.jsonl
    target-audit.jsonl
    access-decisions.jsonl
  mappings/
    access-chain.csv
  queries/
    reconciliation.sql
  derived/
    reconciliation-results.csv
    exceptions.csv
  reviews/
    review-record.json
~~~

Đây là cấu trúc khái niệm, không phải yêu cầu tạo các file này trong bài thực hành hiện tại.

### 9.1. Nội dung của phạm vi

File scope.md cần mô tả mục tiêu kiểm tra, kỳ dữ liệu, tài nguyên, đơn vị đếm, các nguồn và giới hạn đã biết. Nó cũng chỉ rõ bản nào là dữ liệu gốc, bản nào là kết quả chuyển đổi và bản nào được che thông tin.

### 9.2. Nội dung của manifest

Manifest có thể giữ:

- ID gói, người hoặc dịch vụ tạo, thời điểm tạo.
- Kỳ sự kiện và thời điểm chốt nhận dữ liệu.
- Đường dẫn hoặc tham chiếu artifact.
- Kích thước byte, số bản ghi nếu có và thuật toán hash.
- Hash được tính từ đúng byte của artifact đã đóng gói.
- Nguồn gốc, điều kiện export, phiên bản schema và công cụ chuyển đổi.
- Phân loại dữ liệu, nhóm được truy cập và chính sách lưu giữ áp dụng.
- Quan hệ giữa bản gốc, bản chuẩn hóa và bản che thông tin.

Đừng ghi một hash minh họa vào manifest thật. Hash phải được tính trên artifact thực tế sau khi hoàn tất export. Nếu thay nội dung, encoding hoặc xuống dòng, cần tạo phiên bản artifact mới và cập nhật manifest theo quy trình kiểm soát.

### 9.3. Bản gốc và bản đã che thông tin

Che thông tin là một phép biến đổi, không phải một thao tác vô hình. Lưu lý do, phạm vi trường bị che, công cụ hoặc quy tắc thực hiện và tham chiếu bản gốc được bảo vệ.

Bản đã che sẽ có hash khác bản gốc. Người rà soát cần biết họ đang kiểm tra bản nào, những kết luận nào còn kiểm tra được và khi nào cần người có quyền đối chiếu với bản gốc.

## 10. Bảo vệ evidence như dữ liệu nhạy cảm

Evidence PAM có thể chứa tên quản trị viên, sơ đồ hệ thống, lệnh vận hành, địa chỉ máy chủ, nội dung terminal và dữ liệu nghiệp vụ. Kho evidence không nên trở thành một nơi tập trung bí mật mà nhiều người có thể tải về.

Áp dụng các nguyên tắc:

- Chỉ thu thập nội dung cần cho mục đích đã xác định.
- Không đưa password, private key, OTP hay bearer token vào log để “chứng minh đã dùng”.
- Dùng tham chiếu credential, phiên bản và kết quả thay cho giá trị bí mật.
- Kiểm soát quyền xem recording, log chi tiết, tải xuống và xuất gói riêng biệt khi cần.
- Ghi nhận ai truy cập hoặc xuất evidence và với mục đích nào.
- Bảo vệ dữ liệu khi truyền và khi lưu bằng cơ chế phù hợp với hệ thống.
- Xác định thời hạn giữ theo chính sách áp dụng; không tự chọn “giữ mãi” hoặc một số ngày tùy ý.

Terminal recording có thể vô tình ghi secret được hiển thị bởi ứng dụng. Cần phòng ngừa từ luồng sử dụng và cơ chế che phù hợp; đồng thời có quy trình xử lý khi phát hiện secret đã lọt vào evidence. Không tự xóa toàn bộ dấu vết đang cần cho điều tra; phải phối hợp bảo toàn bằng chứng và xử lý bí mật theo thẩm quyền.

Việc hết hạn lưu trữ có thể cần tạm hoãn đối với tập dữ liệu đang được bảo toàn phục vụ điều tra hoặc một yêu cầu giữ hợp lệ. Quyết định giữ, xóa hoặc gia hạn cần có owner và dấu vết, thay vì sửa trực tiếp ở kho mà không có hồ sơ.

## 11. Quy trình rà soát từ yêu cầu đến kết luận

### Bước 1: Chốt câu hỏi và phạm vi

Ví dụ: “Các grant JIT đọc trạng thái cơ sở dữ liệu sản xuất được tạo trong kỳ có phê duyệt đúng phạm vi trước khi quyền bắt đầu có hiệu lực và có kết quả thu hồi được xác minh không?”.

Câu hỏi này xác định rõ đơn vị grant, tài nguyên và hai khẳng định cần kiểm tra. Nó không tự bao gồm việc mọi câu lệnh đều an toàn.

### Bước 2: Xác định và kiểm tra nguồn

Kiểm tra nguồn có hoạt động trong kỳ, export có bị giới hạn số dòng hay phân trang bị bỏ sót, khoảng thời gian và múi giờ có đúng không. Ghi nhận số bản ghi và sai lệch giữa các lần lấy dữ liệu nếu có.

Đối với lỗi pipeline, cần tách ba tình huống: nguồn chưa tạo sự kiện, collector chưa lấy được và kho nhận chưa xử lý được. Cách khắc phục và mức tin cậy khác nhau.

### Bước 3: Tạo population và đối soát

Giữ các bản ghi không ghép được, mâu thuẫn ID và dữ liệu trùng để xử lý theo quy tắc đã công bố; không tính bản ghi trùng thành nhiều đối tượng kiểm tra. Không chỉ xuất phần ghép thành công. Khi sửa quy tắc ghép, lưu phiên bản và chạy lại để có kết quả tái lập.

### Bước 4: Kiểm tra từng khẳng định

Với mỗi grant, đối chiếu quyết định, phạm vi, thời gian, phiên liên quan và kết quả thu hồi. Một grant có đủ trường nhưng role rộng hơn yêu cầu vẫn là sai lệch.

Một sự kiện revoke.requested chỉ cho biết đã yêu cầu thu hồi. Cần hiểu sự kiện hoàn tất và mức xác minh thực tế tại đích; nếu chưa có, ghi rõ chưa xác minh được.

### Bước 5: Chọn mẫu sâu khi cần

Có thể đối soát tự động trên toàn population rồi chọn mẫu để xem recording hoặc đánh giá ngữ cảnh. Lưu phương pháp chọn mẫu, tiêu chí rủi ro và đối tượng đã chọn.

Không tự suy tỷ lệ sai phạm của cả population từ một mẫu chọn theo rủi ro. Mẫu tập trung vào break-glass hoặc quyền rộng có mục đích điều tra sâu, không phải mặc nhiên là mẫu ngẫu nhiên đại diện.

### Bước 6: Ghi phát hiện và khắc phục

Mỗi phát hiện cần có:

- Khẳng định kiểm soát bị ảnh hưởng.
- Bản ghi hoặc tập dữ liệu liên quan.
- Điều đã quan sát và điều chưa xác định.
- Mức ảnh hưởng theo phương pháp của tổ chức.
- Owner, hạn xử lý và hành động tiếp theo.
- Evidence bổ sung để xác nhận đã khắc phục.

Đừng ghi “đã sửa” chỉ vì đã đóng ticket. Nếu lỗi là quyền không bị thu hồi, evidence đóng phát hiện phải bao gồm kết quả thu hồi và kiểm tra phù hợp tại đích.

### Bước 7: Chốt kết luận và gói bàn giao

Ghi riêng phạm vi đạt, các sai lệch, giới hạn dữ liệu và việc còn mở. Người rà soát xác nhận đúng phiên bản gói và kết quả truy vấn mà họ đã xem.

## 12. Case xuyên suốt: kiểm tra một quyền tạm thời

Một vận hành viên được cấp quyền đọc trạng thái replication cho db-prod-cluster-07. Tất cả thời gian dưới đây dùng UTC và chỉ mang tính minh họa.

| Thời điểm | Dữ kiện quan sát | Ý nghĩa và điều cần kiểm tra |
|---|---|---|
| 01:56 | Yêu cầu req-9321 được tạo | Mục đích và phạm vi yêu cầu đã được ghi |
| 01:58 | decision-9321-1 được duyệt | Kiểm tra người duyệt và quyền phê duyệt tại thời điểm đó |
| 02:00 | grant-506 có hiệu lực đến 02:20 | Đối chiếu role thực tế và thời điểm áp dụng tại đích |
| 02:02 | Phiên PAM bắt đầu, có liên kết grant | Đối chiếu tài khoản và phiên đích |
| 02:03–02:10 | Log đích ghi các hành động đọc | Hỗ trợ kiểm tra hành động nằm trong phạm vi đã duyệt |
| 02:12 | Phiên kết thúc | Chưa tự chứng minh grant hết hiệu lực |
| 02:20 | Bộ điều phối yêu cầu thu hồi | Có yêu cầu, chưa có kết quả tại đích |
| 02:23 | Kiểm tra đích cho thấy quyền đã bị gỡ | Xác minh trạng thái tại 02:23; thời điểm gỡ chính xác còn phụ thuộc nguồn khác |

Nếu chỉ có snapshot lúc 02:23, không được tự khẳng định quyền đã tồn tại quá hạn đúng ba phút. Snapshot chứng minh quyền đã được gỡ tại thời điểm kiểm tra, nhưng chưa xác định thời điểm gỡ trước đó.

Có hai kết quả cần giữ riêng:

1. Phê duyệt và phạm vi truy cập có thể được kiểm tra bằng các nguồn hiện có.
2. Việc thu hồi đúng hạn chưa đủ evidence nếu chính sách yêu cầu xác nhận tại mốc 02:20 và không có bản ghi phù hợp.

Ngược lại, nếu audit đích ghi rõ quyền vẫn tồn tại lúc 02:21 rồi bị gỡ lúc 02:22, có cơ sở ghi nhận thu hồi trễ. Sự phân biệt giữa thiếu bằng chứng và sai lệch được quan sát giúp tránh cả kết luận quá mạnh lẫn bỏ sót rủi ro.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng ảnh chụp dashboard làm nguồn duy nhất | Khó tái lập bộ lọc và dữ liệu nền | Giữ export, truy vấn, phạm vi và tham chiếu dữ liệu gốc |
| Chỉ xuất bản ghi thành công | Che mất từ chối, lỗi cấp quyền và lỗi thu hồi | Định nghĩa loại sự kiện cần giữ theo từng khẳng định |
| Chỉ ghép bằng tên tài khoản | Gộp nhiều người hoặc workload thành một | Dùng ID ổn định, ánh xạ có thời gian hiệu lực |
| Chỉ kiểm tra cấu hình hiện tại | Không tái dựng được trạng thái trong kỳ | Giữ phiên bản, snapshot và lịch sử thay đổi cần thiết |
| Bỏ phiên không có request ID | Xóa chính tập cần điều tra khỏi population | Giữ bản ghi thiếu quan hệ như một tập đối soát |
| Coi hash là chứng minh sự thật | Bỏ qua nguồn giả hoặc dữ liệu thiếu trước khi hash | Kết hợp xác thực nguồn, kiểm soát thu thập và đối soát |
| Coi logout là thu hồi toàn bộ quyền | Bỏ sót lease, token hoặc quyền còn tồn tại | Kiểm tra vòng đời từng loại quyền và credential |
| Ghi secret vào evidence | Tạo thêm điểm lộ bí mật | Lưu tham chiếu và metadata đủ cho kiểm tra |
| Lấy mẫu thuận tiện rồi kết luận toàn bộ | Kết luận vượt quá phương pháp kiểm tra | Công bố population, phương pháp chọn mẫu và giới hạn |
| Sửa dữ liệu gốc để “làm sạch” báo cáo | Mất khả năng truy nguyên biến đổi | Giữ bản gốc, tạo bản dẫn xuất và ghi quy tắc xử lý |

## 14. Bài thực hành thiết kế hồ sơ evidence

Giả sử một nhóm vận hành quản lý 30 máy chủ và ba cơ sở dữ liệu. Họ có truy cập quản trị tương tác, một tài khoản dịch vụ chạy job đêm và kênh break-glass. Trong kỳ, collector của một máy chủ ngừng gửi log trong hai giờ.

Hãy thiết kế hồ sơ trả lời câu hỏi: “Quyền đặc biệt trong kỳ có được cấp theo căn cứ hợp lệ, sử dụng trong phạm vi cho phép và kết thúc theo vòng đời đã xác định không?”.

Sản phẩm cần mô tả:

1. Population cho grant, phiên và lần cấp credential; vì sao cần tách các đơn vị này.
2. Các nguồn cần thu thập và nguồn có thẩm quyền cho từng dữ kiện.
3. Khóa nối từ danh tính đến tài nguyên và từ phiên đến căn cứ cấp quyền.
4. Cách đối soát truy cập trực tiếp tại đích với dữ liệu PAM.
5. Cách biểu diễn khoảng mất log hai giờ và ảnh hưởng đến kết luận.
6. Hồ sơ dành cho workload và break-glass, bao gồm căn cứ ủy quyền và hậu kiểm.
7. Manifest, cách xác minh toàn vẹn và quyền truy cập gói evidence.
8. Một kết luận đạt có phạm vi rõ ràng, một phát hiện sai lệch và một trường hợp chưa xác định.

Một hướng xử lý phù hợp là giữ máy chủ mất log trong danh mục phạm vi, đánh dấu đoạn thời gian không đủ khả năng quan sát và tìm nguồn bổ sung có thể kiểm chứng. Nếu không phục hồi được, giữ giới hạn ấy trong kết luận; không loại máy chủ để tỷ lệ bao phủ tăng lên.

Nếu chọn xem recording của một số phiên, giải thích cách chọn và điều có thể kết luận từ mẫu. Không cần thu thập bí mật thật hoặc thực hiện truy cập đặc quyền lên hệ thống sản xuất để hoàn thành bài thiết kế này.

## 15. Câu hỏi tự kiểm tra

**Ticket đã được duyệt trước phiên có đủ chứng minh least privilege không?**

Chưa đủ. Cần đối chiếu phạm vi yêu cầu, phạm vi được duyệt và quyền thực tế được cấp tại đích, bao gồm quyền gián tiếp từ nhóm hoặc role liên quan.

**Một gói có SHA-256 và nằm trong kho chống sửa có chắc chắn đầy đủ không?**

Không. Các cơ chế đó hỗ trợ kiểm tra toàn vẹn trong phạm vi thiết kế, nhưng không tự phát hiện nguồn chưa gửi sự kiện hoặc kênh truy cập chưa được thu thập. Tính đầy đủ cần population và đối soát.

**Không thấy sự kiện thu hồi nghĩa là quyền chắc chắn chưa bị thu hồi?**

Chưa thể kết luận như vậy. Có thể thiếu dữ liệu hoặc nguồn không ghi loại sự kiện cần thiết. Cần kiểm tra trạng thái đích và các nguồn khác, đồng thời ghi nhận khoảng trống evidence.

**Workload không có người phê duyệt từng lần gọi có mặc nhiên là ngoại lệ?**

Không mặc nhiên. Cần xét thiết kế ủy quyền đã được chấp thuận, chính sách có hiệu lực, danh tính workload và dấu vết đánh giá chính sách. Luồng tự động phải có căn cứ kiểm tra phù hợp với nó.

**Báo cáo không có phát hiện có nghĩa là không có rủi ro?**

Không. Kết quả phụ thuộc phạm vi, chất lượng nguồn và phương pháp kiểm tra. Một kết luận có giá trị phải nói rõ tập đã kiểm tra, giới hạn quan sát và các việc còn mở.

## 16. Điểm cần ghi nhớ

Evidence của privileged access phải nối được **căn cứ cấp quyền, quyền thực tế, hoạt động được quan sát và vòng đời kết thúc quyền** với đúng danh tính, tài nguyên và thời gian.

Giá trị của hồ sơ nằm ở khả năng kiểm tra lại: nguồn nào tạo dữ liệu, tập nào đã được bao phủ, phép biến đổi nào đã được áp dụng, ai đã rà soát và kết luận nào thực sự được bằng chứng hỗ trợ. Khi thiếu nguồn hoặc có sai lệch, giữ nguyên thông tin đó là một phần của việc quản lý PAM có trách nhiệm.
