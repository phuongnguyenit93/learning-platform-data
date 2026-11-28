# Security monitoring requirement

## 1. Yêu cầu giám sát phải gắn với rủi ro và quyết định cần thực hiện

Security monitoring requirement là yêu cầu xác định hệ thống phải quan sát, phân tích và chuyển thông tin bảo mật cho chủ thể có trách nhiệm như thế nào để quản lý một rủi ro đã xác định.

Ví dụ, hệ thống có thể vẫn trả request nhanh và không có lỗi 5xx trong khi một tài khoản bị chiếm đang xuất dữ liệu ngoài mục đích được phép. Theo dõi CPU, latency và uptime có ích cho vận hành nhưng chưa bao phủ kịch bản bảo mật đó.

Một yêu cầu còn mơ hồ:

> Hệ thống phải có monitoring bảo mật và cảnh báo kịp thời.

Một cách đặc tả có thể kiểm chứng hơn:

> Với các thay đổi quyền quản trị thành công thuộc phạm vi đã xác định, hệ thống phải thu thập sự kiện từ nguồn đáng tin, đối chiếu quyết định phê duyệt và tạo cảnh báo cho nhóm trực nếu điều kiện phát hiện đạt. Phải quy định thời hạn, hành vi khi dữ liệu thiếu và bằng chứng cho toàn luồng.

NIST CSF 2.0 phân biệt Continuous Monitoring, DE.CM, với Adverse Event Analysis, DE.AE, trong chức năng Detect. Việc quan sát tài sản và phân tích sự kiện liên quan cùng cần thiết để phát hiện và hiểu các tình huống bất lợi. Xem [NIST Cybersecurity Framework 2.0](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf).

Trong module yêu cầu bảo mật, mục tiêu là nối được:

> Rủi ro → tình huống cần phát hiện → tài sản và nguồn tín hiệu → logic và thời hạn → cảnh báo và chủ sở hữu → phản ứng → kiểm thử và cải tiến.

Có monitoring không đồng nghĩa ngăn được mọi tấn công. Đặc tả phải nêu được phạm vi bảo đảm và điểm mù còn được chấp nhận.

## 2. Phân biệt logging, monitoring, detection và response

| Khái niệm | Vai trò | Giới hạn |
|---|---|---|
| Logging hoặc telemetry | Tạo và chuyển các quan sát có cấu trúc | Có log chưa chứng minh log đúng, đủ hoặc đang được phân tích |
| Monitoring | Theo dõi trạng thái, hành vi, kiểm soát và chất lượng tín hiệu | Một dashboard xanh chưa chứng minh không có sự kiện bảo mật |
| Detection | Đánh giá điều kiện hoặc mẫu để nhận diện tình huống cần chú ý | Kết quả có thể cần xác minh và có thể có bỏ sót |
| Alerting | Chuyển một phát hiện tới kênh và chủ thể thích hợp | Gửi thành công chưa chứng minh có người tiếp nhận |
| Triage | Xác minh, phân loại, xác định mức ưu tiên và phạm vi | Không phải mọi alert đều là incident |
| Incident response | Điều phối xử lý sự cố đã đáp ứng tiêu chí | Cần quyền, quy trình, bằng chứng và kiểm tra kết quả |
| Assurance về kiểm soát | Đánh giá kiểm soát còn hoạt động và phù hợp rủi ro không | Không thể suy ra chỉ từ một mẫu thử thành công |

Một yêu cầu “dùng SIEM” hoặc “cài agent” mô tả một lựa chọn công cụ. Cần thêm kết quả phải đạt, nguồn dữ liệu, thời gian, trách nhiệm và bằng chứng nghiệm thu.

NIST SP 800-137 đặt continuous monitoring trong bối cảnh khả năng nhìn thấy tài sản, mối đe dọa và hiệu quả kiểm soát. Có thể tham khảo [NIST SP 800-137 — Information Security Continuous Monitoring](https://csrc.nist.gov/pubs/sp/800/137/final) khi xác định phạm vi chương trình.

Giám sát liên tục cũng không có nghĩa mọi tín hiệu đều được lấy ở cùng tần suất. Tần suất và độ trễ phải phù hợp rủi ro, loại nguồn và khả năng xử lý.

## 3. Bắt đầu từ tình huống rủi ro thay vì danh sách metric chung

### 3.1. Lập danh mục use case

| Rủi ro minh họa | Tình huống cần quan sát | Nguồn tín hiệu có thể cần |
|---|---|---|
| R1: chiếm tài khoản | Chuỗi đăng nhập hoặc sử dụng phiên bất thường | Identity provider, ứng dụng, ngữ cảnh phiên |
| R2: nâng quyền ngoài quy trình | Quyền quản trị được cấp không có quyết định phù hợp | Audit quyền, hệ thống phê duyệt, danh mục vai trò |
| R3: lấy dữ liệu hàng loạt | Export hoặc đọc dữ liệu vượt mẫu và phạm vi đã phê duyệt | Audit truy cập, job export, phân phối artifact |
| R4: can thiệp kiểm soát | Tắt logging, đổi policy, bỏ sensor hoặc thay retention | Audit quản trị, trạng thái cấu hình và nguồn kiểm tra độc lập |
| R5: tác động toàn vẹn | Thay đổi cấu hình hoặc dữ liệu quan trọng ngoài điều kiện được phép | Audit thay đổi, manifest, kết quả kiểm tra toàn vẹn |
| R6: mất khả năng quan sát | Nguồn dừng, pipeline tồn, parser bỏ event hoặc rule không chạy | Health, heartbeat, counter, kiểm tra toàn luồng |
| R7: rò rỉ từ monitoring | Telemetry hoặc alert chứa bí mật, dữ liệu cá nhân ngoài mục đích | Schema, policy thu thập và kiểm tra đích |
| R8: phản ứng gây hại | Tự khóa chủ thể hoặc chặn dịch vụ từ tín hiệu chưa đủ tin cậy | Quyết định detection, policy phản ứng và audit hành động |

Bảng là ví dụ cho một ứng dụng nhiều tenant, không phải danh sách đủ cho mọi sản phẩm.

Mỗi use case cần chủ sở hữu rủi ro, tác động cần hạn chế và phạm vi cần bảo vệ. Có thể ưu tiên theo độ nhạy dữ liệu, mức đặc quyền, khả năng tác động và thời gian tổ chức có để phản ứng.

### 3.2. Viết giả thuyết phát hiện có giới hạn

Một giả thuyết có ích là:

> Nếu quyền quản trị được cấp thành công cho một chủ thể mà không có bằng chứng phê duyệt hợp lệ theo policy tại thời điểm đó, hệ thống cần tạo phát hiện để kiểm tra.

Giả thuyết này cần thêm câu trả lời: nguồn cấp quyền có đáng tin không; bằng chứng phê duyệt đến trễ bao lâu; trường hợp khẩn cấp được biểu diễn thế nào; và nếu hệ thống phê duyệt lỗi thì kết quả là gì.

Không thể chuyển trực tiếp “có nhiều lỗi đăng nhập” thành “tài khoản đã bị chiếm”. Tình huống cần được phân tích cùng dữ liệu có sẵn và mức chắc chắn.

### 3.3. Ghi nhận điểm mù

Một nguồn không được cấu hình, một endpoint chưa instrument hoặc một log chỉ được giao theo best effort đều có thể làm thiếu bằng chứng.

Danh mục nên có trạng thái như được bao phủ, đang suy giảm, chưa được bao phủ hoặc chưa xác minh. Tỷ lệ nguồn đã kết nối không tự là tỷ lệ tấn công phát hiện được.

Nếu một điểm mù được chấp nhận, cần người chịu trách nhiệm, lý do, phạm vi, biện pháp khác và mốc xem xét lại. Không chỉ để một ghi chú không có chủ sở hữu.

## 4. Xác định tài sản, nguồn và chất lượng dữ liệu

### 4.1. Tài sản phải có owner và liên kết tới chức năng

Cần kiểm kê ứng dụng, API, identity provider, database, kho object, worker, tài khoản quản trị, hạ tầng và nhà cung cấp thuộc phạm vi. Với mỗi tài sản, cần biết nó hỗ trợ chức năng nào và chứa hoặc xử lý loại dữ liệu gì.

Một dịch vụ mới không tự được giám sát chỉ vì nó được triển khai trong cùng cluster. Cần kiểm tra nguồn telemetry, schema và rule liên quan đã được kết nối.

Nếu phạm vi còn bao gồm thiết bị hoặc môi trường vật lý, nguồn và trách nhiệm cho phần đó cũng phải được xác định riêng.

### 4.2. Source contract

| Thuộc tính nguồn | Câu hỏi cần trả lời |
|---|---|
| Chủ sở hữu | Ai bật, duy trì và xử lý mất nguồn? |
| Loại sự kiện | Hành động nào tạo event, gồm thành công, từ chối hay lỗi? |
| Nguồn đáng tin | Ai được phát event, trường nào được xác minh? |
| Độ đầy đủ | Có sampling, giới hạn, khoảng không được ghi hoặc điều kiện bật không? |
| Độ trễ | Khi nào event được tạo, giao, parse và có thể đánh giá? |
| Thứ tự và trùng | Có gửi lại, đảo thứ tự, batch hoặc reset sequence không? |
| Schema | Phiên bản, kiểu, đơn vị và ý nghĩa trường là gì? |
| Sức khỏe | Dùng chỉ báo nào để phân biệt im lặng bình thường với nguồn hỏng? |
| Quyền và vòng đời | Ai được đọc, xuất, sửa cấu hình và giữ dữ liệu bao lâu? |

Một nguồn phù hợp điều tra sau sự cố chưa chắc đáp ứng phát hiện trong vài phút. Phải đối chiếu bảo đảm nguồn với mục tiêu use case.

### 4.3. Chất lượng là điều kiện của phát hiện

Nếu trường actor thiếu, một rule theo actor có thể bỏ sót hoặc gom nhầm nhiều người vào cùng nhóm “unknown”. Nếu timestamp không tin cậy, cửa sổ thời gian có thể bị đánh giá sai.

Nên có kiểm tra schema, tỷ lệ thiếu trường, độ trễ, lỗi parse và dữ liệu bị loại. Nếu chất lượng không đủ cho một rule, trạng thái rule cần thể hiện không đủ điều kiện đánh giá hoặc suy giảm.

Không loại một event hỏng rồi mặc định coi nguồn vẫn hoàn toàn tốt. Cần tín hiệu phù hợp về phần dữ liệu không thể sử dụng và nguyên nhân theo phạm vi quan sát.

## 5. Metadata, thời gian và ranh giới danh tính

### 5.1. Thu thập đủ để giải thích, không thu mọi nội dung

Một event có thể cần event ID, loại, producer, thời gian, tenant reference, actor reference, hành động, tài nguyên hoặc phạm vi, quyết định và kết quả.

Không mặc định cần request body, token, cookie, khóa, hồ sơ cá nhân hoặc toàn bộ câu truy vấn. Thu thập phải có schema, mục đích, quyền đọc và retention.

Thông báo phát hiện có thể dùng reference tới bằng chứng hạn chế quyền. Không cần sao chép chi tiết nhạy cảm vào mọi pager, ticket và dashboard.

### 5.2. Danh tính tự khai phải được phân biệt

Username trong request chưa phải người thực hiện đã xác thực. Tenant trong payload chưa chứng minh quyền thuộc tenant đó. IP từ header chưa đủ đáng tin nếu chưa xử lý ranh giới proxy.

Rule và phản ứng không được dựa vào các trường đó như danh tính đã xác minh mà không có nguồn phù hợp. Nếu dùng tín hiệu mạng, cần ghi rõ nguồn, mức tin cậy và khả năng dùng chung.

Request ID, trace ID và incident ID hỗ trợ liên kết, không tự cấp quyền đọc bằng chứng hoặc thao tác khôi phục.

### 5.3. Thời gian và quan hệ nhân quả

Cần phân biệt thời điểm sự kiện xảy ra hoặc commit, thời điểm nhận, thời điểm đủ dữ liệu để đánh giá, thời điểm tạo alert và thời điểm kênh nhận xác nhận.

Hai dịch vụ có thể lệch đồng hồ hoặc giao event đảo thứ tự. Correlation, causation, sequence trong phạm vi đã định và thông tin độ tin cậy thời gian giúp diễn giải đúng hơn việc chỉ sắp xếp timestamp.

Event đến trễ cần policy: có đánh giá lại cửa sổ cũ không, có tạo cảnh báo bổ sung không và có cập nhật kết luận trước đó không. Không sửa thời gian nguồn thành thời gian nhận để làm độ trễ trông thấp hơn.

## 6. Đặc tả logic phát hiện bằng một use case

### 6.1. Bối cảnh giả lập

Giả sử một hệ thống quản trị tenant có quy trình phê duyệt cấp quyền ADMIN. Dự án muốn phát hiện thay đổi thành công chưa đối chiếu được với phê duyệt hợp lệ.

Đầu vào cần có:

- Event cấp quyền thành công từ dịch vụ quản lý quyền được xác thực.
- Tenant, chủ thể được cấp, người thực hiện và phạm vi quyền.
- Reference phê duyệt hoặc quyết định khẩn cấp nếu áp dụng.
- Thời điểm có hiệu lực, phiên bản policy và ID thay đổi.
- Nguồn phê duyệt có trạng thái, phạm vi và thời gian phù hợp.

Chỉ thấy một chuỗi `role=ADMIN` trong input hoặc log tùy ý chưa đủ điều kiện kích hoạt use case như một thay đổi thành công.

### 6.2. Logic minh họa

```text
Khi nhận một thay đổi ADMIN thành công từ nguồn được phép:

    xác minh schema và phạm vi dữ liệu cần thiết

    đối chiếu phê duyệt theo tenant, chủ thể, quyền,
    thời điểm và policy áp dụng

    nếu tìm thấy phê duyệt hợp lệ:
        ghi kết quả đối soát phù hợp

    nếu phê duyệt có thể đến trễ:
        chờ trong cửa sổ đã đặc tả và đánh giá lại

    nếu nguồn phê duyệt không thể xác minh:
        đánh dấu INDETERMINATE hoặc DEGRADED
        tạo tín hiệu sức khỏe hoặc chuyển xem xét theo policy

    nếu hết điều kiện chờ mà vẫn không có phê duyệt phù hợp:
        tạo phát hiện để triage với bằng chứng và mức tin cậy
```

Mã giả mô tả trách nhiệm, không phải implementation hoàn chỉnh. Dự án cần định nghĩa rõ khi nào “không có phê duyệt” là kết quả đối chiếu đầy đủ và khi nào chỉ là không đọc được nguồn.

### 6.3. Kết quả phát hiện cần giải thích được

Một phát hiện nên chứa rule ID và version, nguồn bằng chứng, phạm vi, điều kiện đã đạt, điều còn chưa biết, mức ưu tiên đề xuất và owner.

Có thể gọi tình huống là “thay đổi quyền chưa đối chiếu được phê duyệt”. Không tự khẳng định “người dùng đã tấn công thành công” nếu bằng chứng chưa đủ.

NIST CSF 2.0 phân biệt việc phân tích, tương quan thông tin và tuyên bố incident theo tiêu chí đã định. Xem [NIST CSF 2.0 — DE.AE](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf). Trong thiết kế minh họa, alert là đầu vào cho triage, không tự là kết luận cuối cùng.

## 7. Đặc tả thời gian theo từng chặng

### 7.1. Chọn mốc đo có thể quan sát

Một chuỗi thời gian minh họa:

```text
t0: thay đổi được commit tại nguồn đáng tin
t1: dữ liệu cần thiết có mặt ở lớp phân tích
t2: điều kiện phát hiện đủ để đánh giá theo rule
t3: alert được tạo
t4: kênh xử lý xác nhận đã nhận
t5: người có trách nhiệm xác nhận tiếp nhận
t6: quyết định triage hoặc phản ứng được ghi nhận
```

Các mốc này trả lời các câu hỏi khác nhau:

- Độ trễ tín hiệu: t1 - t0.
- Thời gian chờ dữ liệu hoặc cửa sổ: t2 - t1.
- Độ trễ tạo alert sau khi đủ điều kiện: t3 - t2.
- Độ trễ chuyển cảnh báo: t4 - t3.
- Thời gian con người tiếp nhận: t5 - t4.
- Thời gian tới một quyết định xử lý: cần chọn mốc đầu và cuối riêng.

Không dùng “realtime” hoặc “ngay lập tức” thay cho những giới hạn có định nghĩa. Một rule cần cửa sổ quan sát năm phút không thể vừa đợi đủ cửa sổ vừa cam kết phát hiện từ sự kiện đầu tiên trong một giây.

### 7.2. Độ trễ toàn luồng gồm cả dữ liệu và chuyển cảnh báo

Nếu chỉ đo từ lúc event đã vào detector, kết quả bỏ qua nguồn giao chậm hoặc backlog. Cần cả số liệu từng chặng và mục tiêu từ mốc nguồn tới đầu ra quan trọng.

Với ví dụ cấp quyền, dự án có thể chọn mục tiêu tạo alert trong 240 giây từ t0 khi các điều kiện vận hành đã định được đáp ứng, gồm cửa sổ chờ phê duyệt. Chuyển tới kênh xử lý trong 60 giây tiếp theo là một yêu cầu khác; tổng mục tiêu tới kênh là tối đa 300 giây trong điều kiện đó.

Nếu nguồn thời gian không đáng tin hoặc lệch ngoài giới hạn, số liệu phải được gắn cờ. Không tính độ trễ âm rồi diễn giải là hệ thống phát hiện nhanh hơn.

### 7.3. MTTD cần định nghĩa rõ

Mean time to detect chỉ có ý nghĩa khi nói rõ thời điểm bắt đầu, thời điểm phát hiện, tập vụ việc và cách tổng hợp. Thời điểm đầu tiên có bằng chứng chưa chắc là lúc cuộc tấn công thực sự bắt đầu.

Chỉ tính các vụ đã phát hiện có thể che khuất những vụ bị bỏ sót hoàn toàn. Trung bình thấp cũng có thể đi cùng một số vụ bị phát hiện rất chậm.

Cần theo dõi số lượng mẫu, phân bố hoặc percentile phù hợp và các khoảng không thể đo. Không dùng một con số trung bình như bằng chứng đủ cho mọi use case.

## 8. Đo chất lượng phát hiện và quản lý cảnh báo sai

### 8.1. Các kết quả phải dựa trên tập được gán nhãn

Trong một bộ kiểm thử giả lập, mỗi tình huống có nhãn và tiêu chí kết quả đã xác định:

| Nhãn thực tế trong bộ thử | Có phát hiện phù hợp | Không có phát hiện phù hợp |
|---|---|---|
| Tình huống cần phát hiện | True positive, TP | False negative, FN |
| Tình huống không cần phát hiện | False positive, FP | True negative, TN |

Đơn vị có thể là tình huống, chuỗi thao tác hoặc incident, nhưng phải thống nhất. Một tình huống tạo mười alert trùng không được tính thành mười lần phát hiện đúng.

### 8.2. Ví dụ các tỷ lệ khác nhau

Giả sử có 10 tình huống cần phát hiện và 1.000 tình huống hợp lệ. Rule phát hiện đúng 8, bỏ sót 2, đồng thời tạo phát hiện sai cho 10 tình huống hợp lệ.

```text
TP = 8
FN = 2
FP = 10
TN = 990

Precision = TP / (TP + FP) = 8 / 18 ≈ 44,4%
Recall    = TP / (TP + FN) = 8 / 10 = 80%
FPR       = FP / (FP + TN) = 10 / 1000 = 1%
```

FPR thấp không đồng nghĩa phần lớn alert đều đúng. Tỷ lệ alert sai trong ví dụ là 10/18, khác với FPR.

Các số trên chỉ mô tả bộ thử. Trong production, tổ chức thường không biết đầy đủ mọi tình huống đã bị bỏ sót, nên không thể suy ra recall thật chỉ từ danh sách alert đã điều tra.

### 8.3. Chọn mục tiêu theo use case và chi phí phản ứng

Một use case quan trọng có thể ưu tiên hạn chế bỏ sót và yêu cầu triage sâu hơn. Một rule nhiễu với phản ứng tự động tác động người dùng cần kiểm soát chặt hệ quả của phát hiện sai.

Không đặt mục tiêu “không false positive và không bỏ sót” nếu không có cơ sở. Yêu cầu nên nêu bộ thử, phạm vi tải, các tình huống phải bắt được, tình huống không được kích hoạt và mức nhiễu vận hành được chấp nhận.

Các ngoại lệ cần có phạm vi, chủ sở hữu, căn cứ và thời hạn. Không bỏ qua toàn bộ tài khoản quản trị hoặc đối tác chỉ vì họ thường tạo nhiều event.

## 9. Giám sát chính khả năng giám sát

### 9.1. Im lặng có nhiều nguyên nhân

Không có alert có thể nghĩa là không có điều kiện kích hoạt. Cũng có thể do producer dừng, parser lỗi, queue tồn, rule bị tắt, lịch chạy hỏng hoặc kênh thông báo không nhận.

Một heartbeat chỉ chứng minh một thành phần còn phát tín hiệu ở mốc đó. Nó chưa chứng minh mọi thao tác nghiệp vụ vẫn được instrument đầy đủ.

Cần các kiểm tra phù hợp ở nhiều lớp:

| Lớp | Chỉ báo hoặc kiểm tra cần cân nhắc |
|---|---|
| Nguồn | Heartbeat, trạng thái cấu hình, counter sự kiện kỳ vọng |
| Thu thập | Độ trễ, backlog, quota, buffer và event bị giới hạn |
| Parser và schema | Tỷ lệ parse lỗi, thiếu trường, version chưa được hỗ trợ |
| Detector | Lần chạy cuối, rule version, dữ liệu bị bỏ qua và trạng thái đánh giá |
| Notification | Kết quả gửi, receipt từ kênh, retry và đường dự phòng |
| Xử lý | Alert chưa có owner, chưa được tiếp nhận và quá hạn triage |

### 9.2. Kiểm tra toàn luồng bằng tín hiệu giả lập được kiểm soát

Một canary hoặc tình huống tổng hợp có thể đi qua nguồn, collector, detector và kênh tiếp nhận để kiểm tra khả năng hoạt động toàn luồng.

Tín hiệu đó phải an toàn, có nguồn được xác thực và phạm vi thử rõ. Không cần thực sự cấp quyền quản trị hoặc xuất dữ liệu thật chỉ để kiểm tra một kênh cảnh báo.

Client không được tự gắn một cờ `test=true` rồi làm dữ liệu bị bỏ qua. Marker kiểm thử và ngoại lệ phải được quản lý ở ranh giới tin cậy.

Một canary đi qua pipeline vẫn chưa chứng minh mọi nguồn hoặc mọi rule đều đúng. Cần kết hợp inventory, test theo use case và đối soát nghiệp vụ.

### 9.3. Tránh điểm lỗi chung

Nếu cảnh báo “collector chết” chỉ được gửi qua chính collector đó, khả năng thông báo có thể mất cùng sự cố. Cần đánh giá đường health hoặc kênh dự phòng theo mô hình lỗi.

Tương tự, sự cố identity provider có thể ảnh hưởng cả ứng dụng lẫn khả năng operator mở dashboard. Phương án vận hành khẩn cấp phải được thiết kế và kiểm thử theo quyền, không tạo cửa hậu tùy tiện.

Khi khả năng quan sát suy giảm, trạng thái nên phản ánh mức bao phủ bị ảnh hưởng. Không tiếp tục hiển thị mọi use case là healthy chỉ vì trang dashboard còn tải được.

## 10. Cảnh báo, triage và phản ứng an toàn

### 10.1. Nội dung cảnh báo cần hỗ trợ hành động

Một alert nên có rule và phiên bản, điều kiện quan sát, phạm vi, thời gian, mức tin cậy, chất lượng dữ liệu, reference bằng chứng, owner và runbook.

Bản tóm tắt gửi tới kênh trực chỉ nên có thông tin cần thiết. Chi tiết nhạy cảm được mở qua dịch vụ kiểm tra quyền, không qua link mang token dài hạn.

Có thể vận dụng nguyên tắc cảnh báo phải có hành động rõ trong tài liệu SRE khi thiết kế luồng trực. Xem [Google SRE — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/). Với bảo mật, tác động cần xét cả nguy cơ đối với dữ liệu và kiểm soát, không chỉ lỗi mà người dùng thấy ngay.

### 10.2. Phân vai và escalation

Cần biết ai nhận alert, ai xác minh, ai quyết định incident và ai được thực hiện hành động khắc phục. Thời hạn tiếp nhận phải phù hợp lịch trực thực tế.

Nếu một nhóm chỉ làm giờ hành chính, không nên cam kết phản ứng người trực trong vài phút suốt 24/7 mà chưa có cơ chế tương ứng.

Runbook cần hướng dẫn đối soát, điều kiện dừng, bảo toàn bằng chứng, phạm vi thao tác, kiểm tra sau phản ứng và escalation. Dấu vết triage cần giữ được lý do kết luận và người chịu trách nhiệm.

NIST SP 800-61 Rev. 3 gắn phát hiện, ứng phó và khôi phục với quản lý rủi ro theo CSF 2.0. Tham khảo [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) khi liên kết yêu cầu monitoring với trách nhiệm incident response.

### 10.3. Phản ứng tự động cần quyền và giới hạn riêng

Tạo alert không tự cấp quyền khóa tài khoản, thu hồi mọi phiên hoặc thay firewall. Những hành động đó cần điều kiện, mức tin cậy, phạm vi, thời hạn, audit và cách khôi phục.

Một username do người ngoài tự khai không được dùng như căn cứ duy nhất để khóa tài khoản của người khác. Một nguồn IP dùng chung cũng cần được xem xét trước phản ứng có tác động rộng.

Nếu không xác minh được dữ liệu đầu vào của phản ứng, cần nhánh an toàn theo policy. Không biến hệ thống monitoring thành đường để bên gửi input điều khiển tác vụ quản trị.

### 10.4. Bảo vệ hệ thống monitoring như một tài sản nhạy cảm

Collector, kho dữ liệu, rule engine và công cụ điều tra cần xác thực, phân quyền, tenant isolation và audit thay đổi.

Cần tối thiểu hóa dữ liệu, bảo vệ lúc truyền và lưu, kiểm soát export bằng chứng, quản lý retention và các bản sao. Người có quyền xem một alert không mặc nhiên được đọc mọi dữ liệu nguồn.

Thay rule, tắt nguồn, đổi threshold hoặc tạo mute cần có phạm vi, người chịu trách nhiệm và thời hạn nếu phù hợp. Việc giảm mức giám sát không được diễn ra ngoài kiểm soát chỉ để dashboard bớt nhiễu.

## 11. Ví dụ đặc tả đo được và ma trận nghiệm thu

### 11.1. Bối cảnh và các mục tiêu minh họa

Giả sử một hệ thống nhiều tenant chọn các mục tiêu cho use case cấp ADMIN:

- Nguồn thay đổi quyền và nguồn phê duyệt thuộc danh mục bắt buộc, có schema và owner.
- Các thay đổi quyền thành công thuộc phạm vi không được sampling.
- Event nội bộ có thể sử dụng để phân tích trong 30 giây từ mốc ghi bền tại nguồn khi điều kiện vận hành bình thường được đáp ứng.
- Cho phép cửa sổ chờ phê duyệt 90 giây theo quy tắc thời gian đã xác định.
- Nếu điều kiện “không có phê duyệt phù hợp” được xác minh và vẫn tồn tại, tạo alert trong 240 giây từ t0.
- Kênh xử lý xác nhận nhận alert trong 60 giây từ lúc alert được tạo.
- Nhóm trực có lịch tương ứng xác nhận tiếp nhận trong 5 phút từ receipt của kênh.
- Nguồn bắt buộc mất heartbeat quá 180 giây hoặc chất lượng không đủ phải có tín hiệu suy giảm theo policy.
- Metadata monitoring ở kho chính giữ 90 ngày theo mốc tin cậy; dữ liệu bổ sung, mapping và backup có vòng đời được quản lý riêng.
- Mỗi rule có phiên bản, chủ sở hữu, bộ thử và runbook được liên kết.

**Các con số là giả định minh họa, không phải thời hạn bắt buộc từ NIST hoặc Google.** Chúng cần kiểm thử theo tải, lỗi, schema và kiến trúc cụ thể.

Mốc 240 giây là mục tiêu từ nguồn tới tạo alert của use case đã định, không phải tuyên bố mọi kiểu tấn công đều được phát hiện trong bốn phút. Nếu dữ liệu phê duyệt không thể xác minh, hệ thống phải biểu diễn trạng thái không đủ điều kiện thay vì bịa một kết quả đối chiếu.

### 11.2. Ma trận rủi ro, yêu cầu và bằng chứng

| Mã | Rủi ro | Yêu cầu cụ thể | Bằng chứng nghiệm thu |
|---|---|---|---|
| SM-01 | R1–R6 | Mỗi use case ưu tiên gắn rủi ro, tài sản, nguồn, owner và điểm mù | Đối chiếu inventory với chức năng và kiến trúc; nguồn chưa bao phủ có trạng thái và quyết định rõ |
| SM-02 | R2, R6 | Nguồn cấp quyền và phê duyệt có contract, danh tính và schema được kiểm tra | Event giả từ producer ngoài quyền, sai tenant hoặc thiếu trường không tạo bằng chứng hợp lệ |
| SM-03 | R2 | Rule đối chiếu đúng chủ thể, quyền, phạm vi và thời điểm | Phê duyệt đúng được nhận diện; phê duyệt sai tenant, hết hiệu lực hoặc khác quyền không làm hợp lệ thay đổi |
| SM-04 | R2, R6 | Phân biệt không có phê duyệt với không thể đọc nguồn; xử lý dữ liệu đến trễ | Nguồn lỗi tạo trạng thái INDETERMINATE hoặc DEGRADED; phê duyệt đến trong cửa sổ được đánh giá đúng |
| SM-05 | R1–R5 | Có positive, negative và boundary test theo từng rule; đánh giá chất lượng theo đơn vị thống nhất | Bộ thử có kết quả TP, FP, FN và các ca biên; không đếm alert trùng như nhiều lần phát hiện đúng |
| SM-06 | R6 | Event nguồn sẵn cho phân tích trong 30 giây khi điều kiện đã định được đáp ứng | Đo từ ghi bền tại nguồn; backlog và timestamp không tin cậy không bị loại khỏi báo cáo một cách âm thầm |
| SM-07 | R2 | Alert được tạo trong 240 giây từ t0 cho tình huống đã đặc tả | Diễn tập toàn luồng, gồm chờ dữ liệu, đánh giá và tạo alert; ghi rõ tập tình huống và điều kiện tải |
| SM-08 | R6 | Chuyển alert trong 60 giây; tiếp nhận người trực trong 5 phút theo lịch cam kết | Kiểm tra receipt kênh, retry, escalation và bằng chứng ack; gửi thành công không thay thế ack con người |
| SM-09 | R4, R6 | Giám sát nguồn, parser, detector và kênh; mất heartbeat quá 180 giây có tín hiệu | Dừng từng thành phần có kiểm soát; dashboard thể hiện suy giảm và có đường thông báo phù hợp |
| SM-10 | R7 | Schema tối thiểu, quyền đọc/xuất và retention theo phạm vi | Dữ liệu thử có secret không lọt các đích ngoài quyền; người tenant khác không đọc được bằng chứng |
| SM-11 | R4, R8 | Rule, mute và phản ứng có quyền, phiên bản, audit và giới hạn | Thay threshold hoặc tắt rule ngoài quyền bị từ chối; phản ứng không chạy từ danh tính tự khai thiếu xác minh |
| SM-12 | R1–R8 | Thay đổi sản phẩm và rule phải cập nhật coverage, bộ thử và runbook | Thêm dịch vụ, đổi schema hoặc đổi provider phát hiện được yêu cầu cập nhật; regression test và owner được ghi nhận |

Các yêu cầu cần chỉ ra nơi thực thi và bằng chứng được lưu. Không dùng một ảnh dashboard xanh hoặc danh sách công cụ đã cài như kết quả nghiệm thu đầy đủ.

### 11.3. Tiêu chí chấp nhận cho phát hiện và độ trễ

```gherkin
Given thay doi ADMIN thanh cong tu nguon duoc xac thuc commit tai t0
And nguon phe duyet hoat dong va khong co quyet dinh phu hop
And cua so cho du lieu da duoc ap dung theo policy
When pipeline danh gia thay doi
Then alert duoc tao cham nhat tai t0 + 240 giay trong dieu kien da dinh
And alert co rule version, pham vi, bang chung, owner va runbook
And kenh xu ly co receipt trong 60 giay tu luc tao alert
```

### 11.4. Tiêu chí chấp nhận cho mất khả năng xác minh

```gherkin
Given co event cap ADMIN thanh cong duoc xac minh
When nguon phe duyet khong the duoc kiem tra
Then he thong khong ket luan chac chan rang khong co phe duyet
And trang thai danh gia the hien INDETERMINATE hoac DEGRADED theo contract
And co tin hieu suc khoe hoac escalation theo policy
And khong tu dong khoa chu the chi tu du lieu chua duoc xac minh
```

### 11.5. Tiêu chí chấp nhận cho im lặng của pipeline

```gherkin
Given nguon bat buoc phai phat heartbeat theo contract
When khong co heartbeat moi qua 180 giay
Then pham vi giam sat lien quan duoc danh dau suy giam
And co thong bao qua duong da duoc kiem tra
And dashboard khong dien giai viec khong co alert la khong co rui ro
```

Các đoạn trên là tiêu chí để xây dựng kiểm thử dự án, không phải thông báo rằng một hệ thống thực tế đã vượt qua chúng.

## 12. Kiểm chứng toàn luồng và cải tiến trong vòng đời phát triển

### 12.1. Bộ thử cần bao phủ cả hành vi hợp lệ và đối kháng

Cần các tình huống dương tính, âm tính, sát ngưỡng, dữ liệu trùng, đảo thứ tự, đến trễ, nguồn lỗi, clock lệch và trường bị thiếu.

Với rule dựa trên số lượng hoặc cửa sổ, cần thử nhiều nhịp hành vi. Một mẫu gây burst không đại diện cho mọi hành vi chậm hoặc phân tán mà use case có thể quan tâm.

Bộ thử nên dùng dữ liệu giả lập và môi trường được kiểm soát. Tín hiệu thử không được tạo tác động quản trị thật ngoài kế hoạch; việc ghi nhận marker thử cũng phải có ranh giới tin cậy.

Kiểm thử một rule bằng cách chèn thẳng event vào detector chỉ xác minh đoạn đó. Cần thêm bài thử từ nguồn đến kênh và thao tác triage để kiểm tra toàn contract.

### 12.2. Đánh giá sau cảnh báo và sự cố

Kết quả triage cần quay lại rule catalog: điều gì đúng, trường hợp nhiễu, nguyên nhân bỏ sót, dữ liệu thiếu và thay đổi cần thực hiện.

Nếu phát hiện một sự cố mà rule không bắt được, cần ghi nhận false negative trong phạm vi có thể xác minh và đánh giá lại coverage. Không chỉ điều chỉnh dashboard để che khoảng trống.

Các trường hợp thiếu bằng chứng hoặc chưa xác định cần giữ trạng thái phù hợp. Không gán nhãn “benign” chỉ để đóng nhanh hàng đợi.

### 12.3. Quản lý thay đổi có trách nhiệm

Thêm tài sản, SDK, nhà cung cấp hoặc luồng dữ liệu mới có thể tạo điểm mù. Đổi schema, parser, sampling hoặc policy quyền có thể làm rule cũ mất ý nghĩa.

Cần kiểm soát phiên bản, kiểm thử, phê duyệt theo quy trình dự án, triển khai theo phạm vi và khả năng khôi phục cấu hình. Thay một threshold để giảm nhiễu phải xét tác động đến bỏ sót.

Các ngoại lệ và khoảng chưa bao phủ cần có ngày review. Một quyết định chấp nhận rủi ro không nên tồn tại mãi sau khi kiến trúc hoặc tác động đã đổi.

### 12.4. Những câu đặc tả cần viết rõ hơn

| Câu còn mơ hồ | Điều cần bổ sung |
|---|---|
| “Có security monitoring” | Rủi ro, use case, tài sản, nguồn, logic, thời hạn và owner |
| “Giám sát 24/7” | Khả năng thu thập, phát hiện, chuyển cảnh báo và lịch người tiếp nhận |
| “Cảnh báo realtime” | Mốc đo, độ trễ nguồn, cửa sổ rule, receipt và điều kiện vận hành |
| “Không có false positive” | Bộ thử, đơn vị tính, mục tiêu nhiễu và giới hạn kết luận |
| “Phát hiện 100% tấn công” | Các tình huống đã định, nguồn cần thiết, điểm mù và phạm vi kiểm chứng |
| “Không có log nghĩa là không có sự cố” | Health, backlog, parsing, sampling và nguồn bị mất |
| “Alert tự khóa tài khoản” | Nguồn danh tính, mức tin cậy, quyền, phạm vi, thời hạn và khôi phục |
| “Cài công cụ là đạt yêu cầu” | Kết quả đầu cuối, khả năng vận hành, bằng chứng và regression test |

Một đặc tả security monitoring hoàn chỉnh cần nối được **rủi ro → coverage nguồn → chất lượng dữ liệu → phát hiện có giới hạn → thời gian → chủ thể xử lý → phản ứng an toàn → kiểm chứng và cập nhật**. Chuỗi này giúp giám sát trở thành một năng lực có thể đo và vận hành, thay vì chỉ là việc thu thêm log hoặc tạo thêm cảnh báo.
