# Duy trì chiến lược phù hợp với sản phẩm đang vận hành

Chiến lược kiểm thử được xây dựng ở một thời điểm cụ thể, dựa trên kiến trúc, yêu cầu, rủi ro, dữ liệu, nền tảng và năng lực của nhóm lúc đó. Khi sản phẩm đi vào vận hành, những điều kiện này liên tục thay đổi: chức năng mới được phát hành, dịch vụ được tách hoặc hợp nhất, lượng người dùng tăng, nhà cung cấp thay đổi, sự cố bộc lộ điểm yếu và quy định mới xuất hiện. Nếu chiến lược không được cập nhật, tài liệu dần mô tả một sản phẩm đã không còn tồn tại. Nhóm có thể tiếp tục chạy những test ít giá trị, bỏ sót rủi ro mới hoặc duy trì cổng chất lượng không còn phù hợp với cách hệ thống được triển khai.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, duy trì chiến lược phù hợp với sản phẩm đang vận hành là hoạt động quản trị liên tục nhằm giữ cho phạm vi, cấp độ, loại kiểm thử, kỹ thuật, dữ liệu, môi trường, pipeline và tiêu chí phát hành phản ánh đúng trạng thái sản phẩm. Việc duy trì cần dựa trên tín hiệu thay đổi và bằng chứng vận hành, có người chịu trách nhiệm, có đánh giá tác động, có quyết định được ghi lại và có cách xác minh sau khi cập nhật. Chiến lược không nên thay đổi tùy hứng theo từng lần phát hành; nó cần ổn định đủ để các nhóm làm việc nhất quán nhưng linh hoạt đủ để thích ứng với rủi ro mới.

## 1. Vai trò của chiến lược kiểm thử trong giai đoạn vận hành

### Chiến lược là mô hình quyết định, không chỉ là tài liệu mô tả

Một chiến lược kiểm thử hữu ích giúp nhóm trả lời những câu hỏi đang ảnh hưởng trực tiếp đến việc phát triển và vận hành:

- Những hành vi và thuộc tính chất lượng nào cần được bảo vệ?
- Rủi ro nào đã thay đổi kể từ lần rà soát gần nhất?
- Cấp độ và loại kiểm thử nào tạo bằng chứng phù hợp?
- Bộ test nào cần chạy ở pull request, sau tích hợp, theo lịch hoặc trước phát hành?
- Dữ liệu, môi trường và công cụ nào cần để thực hiện các kiểm tra đó?
- Tiêu chí nào chặn phát hành và ai có quyền chấp nhận ngoại lệ?
- Kết quả production và sự cố được đưa trở lại chiến lược bằng cách nào?

Tài liệu chỉ có giá trị khi các quyết định này được phản ánh trong test suite, pipeline, quy trình triage, runbook và hoạt động phát hành. Nếu tài liệu ghi một gate nhưng pipeline không thực thi, hoặc ghi một rủi ro quan trọng nhưng không có test hay kiểm soát thay thế, chiến lược và thực tế đã lệch nhau.

### Phân biệt thay đổi tài liệu với thay đổi chiến lược

Không phải mọi chỉnh sửa câu chữ đều là thay đổi chiến lược. Có thể phân biệt:

- **Cập nhật mô tả:** sửa tên module, liên kết, owner hoặc thông tin đã lỗi thời mà không đổi quyết định kiểm thử.
- **Điều chỉnh thực thi:** đổi lịch chạy, shard, dataset hoặc cấu hình runner trong phạm vi chiến lược đã phê duyệt.
- **Thay đổi chiến lược:** thay đổi rủi ro được ưu tiên, phạm vi kiểm thử, cấp độ, loại kiểm thử, gate, tiêu chí pass/fail hoặc cách chấp nhận rủi ro.
- **Ngoại lệ tạm thời:** tạm bỏ qua hoặc thay thế một kiểm tra vì điều kiện cụ thể, có owner và thời hạn.
- **Thay đổi khẩn cấp:** điều chỉnh để ứng phó incident hoặc rủi ro đang ảnh hưởng người dùng, sau đó phải được rà soát và chuẩn hóa.

Phân loại giúp chọn đúng mức review và phê duyệt. Một thay đổi chiến lược có thể ảnh hưởng nhiều nhóm và cần phân tích rủi ro rộng hơn một cập nhật mô tả.

### Mục tiêu của việc duy trì

Hoạt động duy trì cần bảo đảm:

1. Chiến lược phản ánh kiến trúc và hành vi đang được triển khai.
2. Rủi ro mới được phát hiện và đưa vào phạm vi xác thực.
3. Kiểm thử hiện có vẫn tạo bằng chứng đáng tin cậy.
4. Test lỗi thời, trùng lặp hoặc không còn giá trị được xử lý có kiểm soát.
5. Dữ liệu, môi trường và công cụ còn khả dụng và an toàn.
6. Cổng chất lượng phù hợp với nhịp phát hành và hậu quả lỗi.
7. Quyết định, ngoại lệ và rủi ro còn lại có thể truy vết.
8. Kết quả vận hành được chuyển thành cải tiến có thể kiểm chứng.

## 2. Những tín hiệu cần kích hoạt rà soát chiến lược

### Thay đổi sản phẩm và yêu cầu nghiệp vụ

Rà soát khi:

- Thêm, bỏ hoặc thay đổi một hành trình nghiệp vụ quan trọng.
- Thay đổi quy tắc tính toán, giá, thuế, quyền hoặc trạng thái.
- Mở rộng sang thị trường, ngôn ngữ, tiền tệ hoặc nhóm người dùng mới.
- Thay đổi mô hình tenant hoặc phân vùng dữ liệu.
- Thêm tính năng có tác động lớn đến bảo mật, dữ liệu hoặc doanh thu.
- Thay đổi tiêu chí chấp nhận hoặc cam kết với khách hàng.

Một thay đổi nhỏ về giao diện có thể ít ảnh hưởng đến chiến lược backend, nhưng thay đổi cách xác nhận giao dịch hoặc phân quyền có thể yêu cầu cập nhật nhiều lớp kiểm thử.

### Thay đổi kiến trúc và phụ thuộc

Các trigger quan trọng gồm:

- Tách hoặc hợp nhất service.
- Thay đổi API, event schema, database schema hoặc protocol.
- Chuyển database, broker, cache hoặc nền tảng cloud.
- Thay đổi authentication, authorization hoặc trust boundary.
- Thêm nhà cung cấp bên ngoài hoặc thay sandbox.
- Thay đổi runtime, framework, browser hoặc hệ điều hành.
- Thay đổi mô hình triển khai, vùng hoạt động hoặc cơ chế failover.

Bản đồ phụ thuộc, contract và test impact analysis cần được cập nhật khi ranh giới hệ thống thay đổi. Không chỉ rà soát module trực tiếp được sửa; cần xem consumer, dữ liệu và hành trình bị ảnh hưởng.

### Tín hiệu từ test và pipeline

Kết quả kiểm thử có thể cho thấy chiến lược không còn phù hợp:

- Tỷ lệ flaky hoặc retry tăng kéo dài.
- Thời gian phản hồi vượt mục tiêu.
- Nhiều test bị skip, blocked hoặc cách ly.
- TIA thường xuyên chọn thiếu hoặc chọn quá nhiều test.
- Một cấp kiểm thử có nhiều assertion trùng lặp.
- Test fail thường xuyên do môi trường hoặc dữ liệu.
- Một cổng chất lượng không phát hiện được lỗi mà nó được thiết kế để chặn.
- Chi phí chạy hoặc bảo trì tăng nhanh hơn quy mô sản phẩm.

Không điều chỉnh chiến lược chỉ dựa trên một lần pipeline đỏ. Tìm xu hướng, nguyên nhân và mức ảnh hưởng trước khi quyết định.

### Tín hiệu từ production và hỗ trợ người dùng

Rà soát sau:

- Incident hoặc defect nghiêm trọng.
- Lỗi lọt production lặp lại ở cùng một hành trình.
- Khiếu nại khách hàng hoặc đối tác.
- Cảnh báo cho thấy hành vi ngoài giả định.
- Sự cố dữ liệu, bảo mật, hiệu năng hoặc phục hồi.
- Workaround vận hành được sử dụng thường xuyên.
- Khoảng trống giữa kiểm thử staging và điều kiện production.

Một incident có thể cho thấy thiếu test, nhưng cũng có thể cho thấy thiếu telemetry, dữ liệu kiểm thử không đại diện, cổng phát hành không đúng hoặc quy trình phục hồi chưa được kiểm tra.

### Tín hiệu từ tổ chức và năng lực

Chiến lược cũng cần thích ứng khi:

- Nhóm thay đổi cơ cấu hoặc ownership.
- Một nhóm chuyên môn không còn khả dụng.
- Sản phẩm chuyển sang mô hình phát hành liên tục.
- Khối lượng pull request hoặc release tăng.
- Năng lực runner, lab hoặc sandbox thay đổi.
- Công cụ kiểm thử được thay thế.
- Yêu cầu tuân thủ hoặc chính sách lưu trữ thay đổi.

Không duy trì một quy trình phụ thuộc vào một cá nhân hoặc một môi trường không còn được hỗ trợ.

## 3. Thiết lập chu kỳ rà soát phù hợp

### Kết hợp rà soát định kỳ và rà soát theo sự kiện

Rà soát định kỳ giúp phát hiện lệch dần; rà soát theo sự kiện giúp phản ứng khi có thay đổi quan trọng. Có thể dùng mô hình:

| Nhịp rà soát | Nội dung chính | Ví dụ trigger |
|---|---|---|
| Mỗi pull request hoặc thay đổi lớn | Tác động đến test, dữ liệu, hợp đồng và gate | API/schema thay đổi |
| Mỗi sprint hoặc chu kỳ phát triển | Flaky, backlog test, coverage rủi ro và thời gian chạy | Kết thúc sprint |
| Hàng tháng hoặc theo quý | Kiến trúc, xu hướng defect, chi phí và năng lực | Review chiến lược định kỳ |
| Trước release lớn | Phạm vi regression, migration, acceptance và ngoại lệ | Release candidate |
| Sau incident nghiêm trọng | Khoảng trống phát hiện, khôi phục và kiểm soát bù | Post-incident review |
| Khi có thay đổi nền tảng | Toolchain, môi trường, dữ liệu và tương thích | Nâng cấp runtime hoặc cloud |

Tần suất thực tế phụ thuộc tốc độ thay đổi và rủi ro. Một hệ thống thanh toán có thể cần review một số kiểm soát theo từng thay đổi; một hệ thống ít thay đổi có thể dùng chu kỳ dài hơn.

### Xác định phạm vi cho mỗi lần rà soát

Không cần mở lại toàn bộ chiến lược trong mọi lần review. Xác định:

- Trigger nào đã xảy ra?
- Module, hành trình, dữ liệu và phụ thuộc nào liên quan?
- Quyết định nào có thể bị ảnh hưởng?
- Bằng chứng nào cần thu thập?
- Nhóm hoặc owner nào cần tham gia?
- Có cần cập nhật tài liệu, test, pipeline hay runbook?
- Khi nào phải hoàn tất và xác minh?

Nếu tác động vượt khỏi phạm vi ban đầu, mở rộng review và ghi rõ lý do.

### Tránh rà soát hình thức

Một buổi review chỉ đọc lại tài liệu mà không so sánh với sản phẩm và dữ liệu vận hành sẽ khó phát hiện sai lệch. Cần chuẩn bị bằng chứng trước buổi review, chẳng hạn:

- Danh sách thay đổi kiến trúc và release.
- Defect và incident theo nhóm rủi ro.
- Kết quả test, flaky, retry và thời gian chạy.
- Danh sách test bị cách ly hoặc không có owner.
- Chi phí runner, môi trường và dữ liệu.
- Rủi ro chưa được kiểm tra và ngoại lệ đang mở.
- Thay đổi yêu cầu, pháp lý hoặc chính sách dữ liệu.

Kết quả review phải có quyết định, owner và hạn hoàn thành, không chỉ là biên bản thảo luận.

## 4. Đánh giá tác động trước khi thay đổi chiến lược

### Xác định chuỗi tác động

Với mỗi thay đổi, lần theo quan hệ:

1. Yêu cầu hoặc điều kiện vận hành thay đổi.
2. Thành phần, ranh giới hoặc dữ liệu chịu ảnh hưởng.
3. Rủi ro mới hoặc rủi ro hiện tại thay đổi.
4. Bằng chứng hiện có còn phù hợp hay không.
5. Cấp độ, loại và kỹ thuật kiểm thử cần điều chỉnh.
6. Dữ liệu, môi trường và công cụ cần cập nhật.
7. Pipeline, gate và lịch chạy có cần thay đổi không.
8. Owner, năng lực và chi phí có thay đổi không.

Đánh giá cả tác động trực tiếp và gián tiếp. Ví dụ, thay đổi event schema có thể ảnh hưởng producer, nhiều consumer, dữ liệu replay, contract test và khả năng phục hồi.

### Đánh giá rủi ro còn lại

Với từng rủi ro, xác định:

- Mức nghiêm trọng nếu xảy ra.
- Khả năng xảy ra và mức phơi nhiễm.
- Phạm vi người dùng, tenant hoặc dịch vụ.
- Khả năng phát hiện trước khi người dùng bị ảnh hưởng.
- Khả năng phục hồi hoặc workaround.
- Chi phí sửa và điều tra.
- Bằng chứng hiện có và độ tin cậy.
- Khoảng trống sau thay đổi.

Không coi test pass là bằng chứng đủ nếu dữ liệu, môi trường hoặc oracle không đại diện. Cũng không coi một rủi ro đã được xử lý chỉ vì đã thêm test mới; cần xác minh test thực sự phát hiện được điều kiện lỗi.

### Dùng phân tích tác động có truy vết

Kết nối thay đổi với:

- Requirement hoặc behavior ID.
- Risk ID.
- Component, API, event và schema.
- Test case và test suite.
- Pipeline stage và gate.
- Dữ liệu và môi trường.
- Owner và artifact xác minh.

Khi metadata thiếu hoặc TIA không đáng tin, mở rộng phạm vi theo chính sách fallback. Không kết luận “không có test bị ảnh hưởng” chỉ vì công cụ không tìm thấy liên kết.

### Xác định mức thay đổi cần phê duyệt

Có thể phân loại:

- Thay đổi cục bộ trong phạm vi đã phê duyệt.
- Thay đổi ảnh hưởng nhiều module hoặc nhóm.
- Thay đổi gate, severity threshold hoặc tiêu chí phát hành.
- Thay đổi làm giảm kiểm soát cho rủi ro cao.
- Ngoại lệ khẩn cấp hoặc tạm thời.

Mức thay đổi càng ảnh hưởng rộng hoặc giảm bảo vệ, yêu cầu review và phê duyệt càng cao. Cần quy định rõ ai có quyền chấp nhận rủi ro còn lại.

## 5. Cập nhật các thành phần của chiến lược

### Cập nhật phạm vi và bản đồ rủi ro

Khi sản phẩm thay đổi:

- Thêm hành vi, module hoặc tích hợp mới vào danh mục.
- Cập nhật ranh giới và dependency graph.
- Đánh giá rủi ro mới và mức độ của rủi ro hiện tại.
- Liên kết incident và defect với vùng kiểm thử.
- Ghi rủi ro đã loại bỏ hoặc không còn áp dụng.
- Xác định rủi ro được kiểm soát bằng test hay biện pháp khác.

Không xóa lịch sử rủi ro cũ nếu nó cần để hiểu quyết định hoặc sự cố trước đây. Đánh dấu trạng thái và phiên bản áp dụng.

### Cập nhật cấp độ, loại và kỹ thuật

Một thay đổi có thể yêu cầu:

- Thêm unit test cho quy tắc mới.
- Bổ sung contract test cho API hoặc event.
- Thêm integration test cho database, broker hoặc provider.
- Mở rộng E2E cho hành trình mới.
- Thêm security test cho trust boundary.
- Thêm performance hoặc resilience test cho tải và chế độ lỗi.
- Thay đổi kỹ thuật dữ liệu, concurrency hoặc state transition.

Chọn cấp sớm nhất tạo bằng chứng đáng tin, đồng thời giữ kiểm tra ở ranh giới có rủi ro thực sự. Không dồn mọi kiểm tra vào E2E chỉ vì một hành trình mới đi qua nhiều service.

### Cập nhật dữ liệu và môi trường

Rà soát:

- Seed và fixture có còn phản ánh quy tắc mới không?
- Snapshot có tương thích schema hiện tại không?
- Dữ liệu có cần thêm biến thể, giá trị biên hoặc tenant không?
- Môi trường có đủ thành phần và phiên bản cần thiết không?
- Sandbox và quota có còn khả dụng?
- Namespace, reset, cleanup và TTL có phù hợp không?
- Secret và quyền có đúng phạm vi không?

Dữ liệu production dùng để tái hiện cần tuân thủ chính sách bảo mật, khử định danh và retention.

### Cập nhật pipeline và cổng chất lượng

Có thể cần điều chỉnh:

- Bộ test chạy tại local, pull request, sau tích hợp, nightly hoặc pre-release.
- Phạm vi incremental regression và fallback.
- Thứ tự test và sharding.
- Timeout, retry và concurrency.
- Điều kiện pass/fail và mức độ chặn merge/release.
- Cách xử lý test flaky hoặc bị cách ly.
- Thu thập artifact và báo cáo rủi ro chưa được kiểm tra.

Mỗi gate phải có mục đích và owner. Không hạ ngưỡng chỉ để pipeline xanh nhanh hơn khi chưa đánh giá rủi ro.

### Cập nhật monitoring và vận hành

Nếu test phát hiện lỗi production muộn, có thể cần thêm:

- Metric hoặc log có cấu trúc.
- Correlation ID và trace xuyên dịch vụ.
- Synthetic check cho hành trình quan trọng.
- Alert theo triệu chứng và mức ảnh hưởng.
- Runbook và hướng dẫn đối soát.
- Kiểm tra backup, restore hoặc failover.
- Cơ chế liên kết incident với defect và test hồi quy.

Monitoring bổ sung khả năng phát hiện sau triển khai; nó không thay thế các kiểm thử trước phát hành cần thiết.

## 6. Quản lý quyết định, ngoại lệ và rủi ro chấp nhận

### Ghi quyết định thay đổi

Mỗi thay đổi chiến lược quan trọng nên có bản ghi quyết định gồm:

- Mã quyết định và ngày.
- Bối cảnh và trigger.
- Phạm vi sản phẩm, module và release áp dụng.
- Bằng chứng được xem xét.
- Các phương án đã cân nhắc.
- Phương án được chọn và lý do.
- Rủi ro được giảm hoặc phát sinh.
- Tác động đến thời gian, chi phí và nguồn lực.
- Owner thực hiện và người phê duyệt.
- Ngày hiệu lực và ngày review lại.

Bản ghi quyết định giúp người đọc sau này hiểu vì sao chiến lược thay đổi và tránh lặp lại tranh luận đã được giải quyết.

### Quản lý ngoại lệ tạm thời

Ngoại lệ có thể cần thiết khi test hoặc môi trường không khả dụng. Mỗi ngoại lệ cần:

- Phạm vi chính xác của kiểm soát bị bỏ qua hoặc thay thế.
- Lý do và bằng chứng.
- Rủi ro còn lại.
- Biện pháp bù.
- Người chấp nhận rủi ro.
- Owner khắc phục nguyên nhân.
- Thời hạn hết hiệu lực.
- Điều kiện gỡ ngoại lệ.

Ngoại lệ phải tự hết hạn hoặc được review lại. Không để một test bị skip hoặc gate bị tắt trở thành trạng thái mặc định mà không có quyết định mới.

### Phê duyệt theo mức rủi ro

Có thể áp dụng nguyên tắc:

| Loại quyết định | Review tối thiểu gợi ý |
|---|---|
| Cập nhật mô tả hoặc liên kết | Owner tài liệu |
| Điều chỉnh test cục bộ không đổi mức bảo vệ | Owner module và người review kỹ thuật |
| Thay đổi phạm vi hoặc kỹ thuật cho rủi ro trung bình | QA/test lead và owner sản phẩm |
| Thay đổi gate hoặc giảm kiểm soát rủi ro cao | Người có thẩm quyền phát hành và owner rủi ro |
| Ngoại lệ khẩn cấp trong incident | Người điều phối incident hoặc người được ủy quyền; review lại sau sự cố |

Đây là mô hình tham khảo. Tổ chức cần xác định vai trò và quyền phê duyệt thực tế. Người thực hiện thay đổi không nên tự chấp nhận rủi ro quan trọng nếu quy trình yêu cầu đánh giá độc lập.

## 7. Quản lý phiên bản và tính nhất quán của tài liệu

### Dùng phiên bản có thể truy vết

Tài liệu chiến lược nên có:

- Mã hoặc số phiên bản.
- Ngày hiệu lực.
- Phạm vi sản phẩm và môi trường áp dụng.
- Owner và người phê duyệt.
- Tóm tắt thay đổi.
- Liên kết đến quyết định và bằng chứng.
- Lịch sử phiên bản trước.
- Ngày rà soát tiếp theo.

Nếu chiến lược được quản lý trong Git, dùng pull request để review nội dung, xem diff và liên kết commit. Nếu dùng hệ thống tài liệu khác, cần có lịch sử sửa đổi và quyền truy cập phù hợp.

### Tránh lệch giữa tài liệu và triển khai

Các nguồn cần được đối chiếu:

- Tài liệu chiến lược.
- Test catalog và traceability matrix.
- Cấu hình pipeline và quality gate.
- Test suite và metadata.
- Dữ liệu, fixture và môi trường.
- Runbook và quy trình incident.
- Dashboard và báo cáo vận hành.

Khi tài liệu thay đổi nhưng pipeline chưa thay đổi, ghi rõ phần triển khai còn chờ và deadline. Khi pipeline đã thay đổi khẩn cấp trước tài liệu, tạo hành động cập nhật và review sau đó.

### Lưu lịch sử và trạng thái cũ

Không xóa dấu vết của quyết định đã hết hiệu lực nếu cần cho audit hoặc phân tích sự cố. Đánh dấu phiên bản cũ là superseded, ghi phiên bản thay thế và thời điểm chuyển đổi. Các liên kết từ release cũ cần vẫn trỏ được đến chiến lược có hiệu lực tại thời điểm đó.

### Kiểm soát tài liệu phân tán

Nếu có tài liệu cấp tổ chức, cấp sản phẩm và cấp module, xác định:

- Nội dung nào là chính sách chung.
- Nội dung nào là cấu hình riêng của sản phẩm.
- Quy tắc nào được phép ghi đè.
- Nguồn nào có thẩm quyền khi nội dung mâu thuẫn.
- Cách truyền thay đổi xuống tài liệu con.
- Ai chịu trách nhiệm đồng bộ.

Tránh sao chép cùng một chính sách vào nhiều nơi mà không có owner và cơ chế đồng bộ.

## 8. Duy trì chất lượng và tính hữu dụng của bộ kiểm thử

### Rà soát test không còn phù hợp

Định kỳ xem xét test:

- Gắn với chức năng đã bỏ.
- Không còn yêu cầu hoặc rủi ro tương ứng.
- Trùng lặp mà không tạo thêm bằng chứng.
- Dựa trên fixture hoặc API đã lỗi thời.
- Flaky kéo dài hoặc bị cách ly.
- Không có owner.
- Không chạy trong pipeline nào.
- Có thời gian chạy hoặc chi phí bất thường.

Trước khi xóa test, xác minh không có yêu cầu, nhánh hoặc nghĩa vụ nào chỉ được test đó bảo vệ. Có thể thay thế bằng test ở cấp khác nếu bằng chứng tương đương hoặc tốt hơn.

### Duy trì test có giá trị cao

Ưu tiên test:

- Bảo vệ hành trình cốt lõi.
- Liên quan dữ liệu, bảo mật và quyền.
- Đã từng phát hiện defect nghiêm trọng.
- Bao phủ ranh giới tích hợp quan trọng.
- Chạy thường xuyên hoặc chặn release.
- Có chi phí điều tra cao nếu không có tự động hóa.

Test quan trọng cần có owner, dữ liệu tái tạo, oracle rõ và artifact đủ để chẩn đoán.

### Quản lý flaky và test bị cách ly

Khi test flaky:

1. Ghi nhận kết quả lần chạy đầu.
2. Thu thập seed, run ID, log và trace.
3. Phân loại nguyên nhân có thể.
4. Quyết định sửa, cách ly có thời hạn hoặc thay thế.
5. Ghi owner, rủi ro mất bảo vệ và kiểm soát bù.
6. Xác minh sau sửa bằng chạy lặp phù hợp.
7. Gỡ cách ly khi đủ bằng chứng.

Không dùng retry để che flaky. Không để test bị cách ly vô thời hạn mà không có review.

### Đánh giá khả năng chẩn đoán

Nếu test fail nhưng không chỉ ra nguyên nhân, chiến lược cần xem xét:

- Log và trace có đủ không?
- Assertion có thể hiện expected/actual không?
- Test có ghi phiên bản, môi trường và dữ liệu không?
- Correlation ID có nối được nhiều service không?
- Có nguồn dữ liệu có thẩm quyền để xác minh không?
- Artifact có được giữ đủ lâu không?

Cải thiện observability của test có thể giảm đáng kể thời gian điều tra và giúp chiến lược vận hành được lâu dài.

## 9. Đưa phản hồi từ defect và incident trở lại chiến lược

### Phân tích lỗi lọt

Với mỗi defect nghiêm trọng hoặc incident, xem xét:

- Lỗi bắt nguồn từ yêu cầu, thiết kế, code, dữ liệu hay cấu hình?
- Có test nào được kỳ vọng phát hiện không?
- Test đó có tồn tại và được chạy không?
- Dữ liệu có tái hiện điều kiện production không?
- Oracle có kiểm tra đúng hành vi không?
- Test có bị skip, flaky hoặc cách ly không?
- Pipeline gate có cho phép lỗi đi qua không?
- Monitoring có phát hiện sớm không?
- Có thể bổ sung kiểm tra ở cấp rẻ và ổn định hơn không?

Không mặc định thêm một E2E là câu trả lời. Chọn lớp test phù hợp với nguyên nhân và ranh giới thất bại.

### Chuyển bài học thành hành động có thể xác minh

Một hành động cải tiến cần có:

- Vấn đề hoặc khoảng trống cụ thể.
- Thay đổi dự kiến.
- Owner.
- Mức ưu tiên và thời hạn.
- Test, metric hoặc artifact dùng để xác minh.
- Điều kiện hoàn tất.
- Rủi ro nếu không thực hiện.

Ví dụ, nếu incident do consumer xử lý message trùng, hành động có thể gồm test idempotency ở integration, test retry, metric duplicate event và cập nhật runbook đối soát.

### Theo dõi hiệu quả sau cải tiến

Sau khi thay đổi chiến lược, kiểm tra:

- Test mới có phát hiện được lỗi mô phỏng hoặc lỗi hồi quy tương ứng không?
- Tỷ lệ lỗi cùng loại có giảm không?
- Thời gian phát hiện và điều tra có cải thiện không?
- Pipeline có tăng thời gian hoặc flaky đáng kể không?
- Kiểm soát mới có tạo false positive hoặc chi phí quá lớn không?
- Có phát sinh khoảng trống ở cấp khác không?

Một hành động chỉ được xem là hiệu quả khi có bằng chứng sau triển khai, không chỉ vì tài liệu hoặc test đã được thêm.

## 10. Duy trì chiến lược khi sản phẩm tăng trưởng

### Mở rộng theo quy mô người dùng và dữ liệu

Khi lượng người dùng, tenant hoặc dữ liệu tăng:

- Cập nhật workload và profile tải.
- Bổ sung kiểm tra capacity và saturation.
- Tăng kích thước dataset đại diện.
- Kiểm tra phân vùng, index và truy vấn.
- Xác minh tenant isolation ở quy mô lớn.
- Rà soát retention, backup và phục hồi.
- Đánh giá giới hạn quota và concurrency.

Test với dữ liệu nhỏ có thể không phát hiện vấn đề chỉ xuất hiện khi hệ thống đạt quy mô vận hành.

### Mở rộng theo dịch vụ và tích hợp

Khi thêm service hoặc provider:

- Cập nhật dependency graph và trust boundary.
- Xác định contract và versioning.
- Thêm test cho retry, timeout, duplicate và out-of-order event.
- Bổ sung sandbox, dữ liệu và cleanup.
- Xác định owner ở hai phía provider/consumer.
- Cập nhật hành trình E2E đại diện.
- Kiểm tra degraded mode và khả năng phục hồi.

Không chỉ thêm một service vào sơ đồ kiến trúc; cần cập nhật các rủi ro và bằng chứng mới do service đó tạo ra.

### Mở rộng theo nền tảng và thị trường

Khi hỗ trợ browser, thiết bị, runtime, vùng hoặc ngôn ngữ mới:

- Xác định ma trận tương thích.
- Dùng pairwise hoặc combinatorial testing cho tổ hợp lớn.
- Chọn cấu hình đại diện theo mức sử dụng.
- Kiểm tra locale, timezone, encoding và định dạng.
- Xác minh dữ liệu và quyền theo vùng.
- Cập nhật tiêu chí accessibility và usability.
- Bổ sung kiểm tra upgrade và backward compatibility.

Không nhân toàn bộ bộ test cho mọi tổ hợp nếu rủi ro không yêu cầu; nhưng cần ghi rõ cách chọn và phần chưa được kiểm tra.

### Thay đổi mô hình phát hành

Khi chuyển từ release theo đợt sang continuous delivery, chiến lược có thể cần:

- Tăng kiểm tra tự động ở pull request và sau tích hợp.
- Dùng canary hoặc progressive delivery.
- Bổ sung smoke và synthetic check sau deploy.
- Đặt tiêu chí rollback dựa trên metric.
- Tăng khả năng kiểm soát feature flag.
- Tách gate bắt buộc khỏi kiểm tra theo lịch.
- Rút ngắn vòng phản hồi nhưng vẫn giữ full regression theo trigger.

Nhịp phát hành nhanh hơn không đồng nghĩa giảm chất lượng xác thực; nó đòi hỏi bằng chứng được tạo thường xuyên và khả năng phát hiện/khôi phục tốt hơn.

## 11. Quản trị ownership và phối hợp liên nhóm

### Phân vai rõ ràng

Có thể xác định:

- **Product owner:** chịu trách nhiệm về mục tiêu nghiệp vụ và mức rủi ro chấp nhận.
- **Engineering owner:** chịu trách nhiệm kiến trúc, hành vi và sửa lỗi sản phẩm.
- **QA/test lead:** duy trì phạm vi, cấp độ, loại và kỹ thuật kiểm thử.
- **Platform/CI owner:** duy trì runner, pipeline, gate và công cụ.
- **Data/environment owner:** duy trì dữ liệu, sandbox và môi trường.
- **Security/SRE specialist:** tư vấn và phê duyệt các kiểm soát chuyên môn.
- **Release owner:** xác nhận bằng chứng và quyết định phát hành theo thẩm quyền.

Một người có thể giữ nhiều vai trò ở nhóm nhỏ, nhưng trách nhiệm và quyền quyết định cần rõ.

### Duy trì ma trận trách nhiệm

Với mỗi phần chiến lược, ghi:

- Người chịu trách nhiệm cập nhật.
- Người review.
- Người phê duyệt nếu có thay đổi rủi ro.
- Nhóm bị ảnh hưởng cần được tham vấn.
- Nhóm cần được thông báo.
- Nguồn dữ liệu hoặc artifact có thẩm quyền.

Không để một thay đổi liên nhóm được triển khai mà các consumer hoặc owner phụ thuộc không biết.

### Điều phối thay đổi xuyên nhóm

Khi thay đổi ảnh hưởng nhiều nhóm:

1. Thông báo trigger và phạm vi dự kiến.
2. Chia sẻ dependency và risk map.
3. Thu thập phản hồi từ owner liên quan.
4. Thống nhất test contract và môi trường.
5. Xác định thứ tự triển khai và tương thích.
6. Cập nhật tài liệu và pipeline đồng bộ.
7. Theo dõi kết quả sau chuyển đổi.

Với thay đổi API hoặc schema, có thể cần giai đoạn tương thích song song để provider và consumer nâng cấp độc lập.

## 12. Đo lường mức độ phù hợp của chiến lược

### Chỉ số về độ bao phủ rủi ro

Theo dõi:

- Tỷ lệ rủi ro quan trọng có bằng chứng kiểm thử.
- Số rủi ro mới chưa được đánh giá.
- Defect lọt production theo nhóm nguyên nhân.
- Tỷ lệ incident có hành động kiểm thử theo dõi.
- Test bị skip, blocked hoặc cách ly ở vùng rủi ro cao.
- Tỷ lệ requirement/test mapping còn hợp lệ.

Coverage theo dòng code không đủ để chứng minh chiến lược phù hợp. Cần liên kết yêu cầu, rủi ro, test và bằng chứng vận hành.

### Chỉ số về tốc độ và độ tin cậy

Theo dõi:

- Thời gian phản hồi của pipeline theo stage.
- p50/p95 thời gian chạy suite.
- Tỷ lệ pass lần đầu.
- Flaky và retry rate.
- Thời gian từ defect đến nguyên nhân.
- Thời gian khôi phục incident.
- Tỷ lệ cleanup thành công.
- Số tài nguyên quá TTL.
- Chi phí test theo release hoặc module.

Không tối ưu tốc độ bằng cách bỏ qua kiểm tra có rủi ro cao. Đánh giá tốc độ cùng chất lượng bằng chứng.

### Chỉ số về mức độ duy trì tài liệu

Có thể đo:

- Tỷ lệ phần chiến lược có owner.
- Tuổi của lần review gần nhất.
- Số quyết định chưa được cập nhật vào pipeline.
- Số ngoại lệ quá hạn.
- Số liên kết test hoặc requirement lỗi thời.
- Số hành động sau incident chưa hoàn tất.
- Thời gian từ trigger đến cập nhật chiến lược.

Các chỉ số này giúp phát hiện tài liệu đã cũ trước khi nó gây ra khoảng trống kiểm thử.

### Tránh tối ưu chỉ số đơn lẻ

Số defect giảm có thể do sản phẩm tốt hơn hoặc do ghi nhận kém. Pipeline nhanh hơn có thể do tối ưu tốt hoặc do test bị bỏ qua. Tỷ lệ pass cao có thể phản ánh chất lượng hoặc retry che giấu flaky. Luôn kết hợp chỉ số định lượng với review bằng chứng và bối cảnh.

## 13. Quy trình thực hiện một thay đổi chiến lược

### Các bước từ trigger đến xác minh

Một quy trình chuẩn có thể gồm:

1. Ghi nhận trigger và nguồn bằng chứng.
2. Xác định phạm vi sản phẩm và phần chiến lược bị ảnh hưởng.
3. Phân tích tác động đến yêu cầu, rủi ro, kiến trúc và test.
4. Đề xuất thay đổi và phương án thay thế.
5. Ước lượng chi phí, thời gian và nguồn lực.
6. Review với owner và bên liên quan.
7. Phê duyệt theo mức rủi ro.
8. Cập nhật tài liệu, test, dữ liệu, pipeline hoặc runbook.
9. Xác minh thay đổi trên môi trường phù hợp.
10. Triển khai theo phạm vi và thời điểm đã định.
11. Theo dõi chỉ số và rủi ro sau thay đổi.
12. Đóng quyết định hoặc mở hành động bổ sung.

~~~mermaid
flowchart TD
    A["Trigger: sản phẩm, kiến trúc, test hoặc incident thay đổi"] --> B["Ghi nhận và xác định phạm vi"]
    B --> C["Phân tích tác động và rủi ro"]
    C --> D["Đề xuất điều chỉnh chiến lược"]
    D --> E["Review và phê duyệt"]
    E --> F["Cập nhật tài liệu, test và pipeline"]
    F --> G["Xác minh bằng chứng"]
    G --> H{"Kết quả phù hợp?"}
    H -->|Chưa| D
    H -->|Đạt| I["Áp dụng và truyền thông"]
    I --> J["Theo dõi vận hành"]
    J --> K["Rà soát lại theo chu kỳ"]
~~~

Sơ đồ thể hiện luồng thông thường. Thay đổi khẩn cấp có thể đi theo quy trình rút gọn, nhưng phải có review sau thay đổi và thời hạn chuẩn hóa.

### Checklist cho một change request

Một change request chiến lược nên có:

- Trigger và vấn đề cần giải quyết.
- Trạng thái hiện tại và bằng chứng.
- Phạm vi module, hành trình và release.
- Rủi ro trước và sau thay đổi.
- Các phương án và trade-off.
- Test, dữ liệu, môi trường và pipeline bị ảnh hưởng.
- Tác động đến chi phí và năng lực.
- Owner, reviewer và approver.
- Kế hoạch chuyển đổi và rollback nếu cần.
- Tiêu chí xác minh và ngày review lại.

### Xác minh trước và sau khi áp dụng

Trước thay đổi, ghi baseline: thời gian chạy, flaky, coverage rủi ro, chi phí hoặc defect liên quan. Sau thay đổi, đo lại trong điều kiện tương đương.

Ví dụ, khi chuyển một số E2E sang contract và integration test, cần chứng minh thời gian phản hồi giảm nhưng các rủi ro giao tiếp vẫn được kiểm tra. Nếu không có bằng chứng tương đương, việc chuyển cấp có thể tạo khoảng trống.

## 14. Ví dụ: điều chỉnh chiến lược khi sản phẩm chuyển sang kiến trúc dịch vụ

Giả sử một ứng dụng thương mại điện tử ban đầu là monolith. Sản phẩm tách order, payment và notification thành các service độc lập, đồng thời tăng tần suất triển khai.

### Trạng thái chiến lược cũ

- Nhiều unit test và component test trong monolith.
- Một số E2E chạy sau mỗi build.
- Database dùng chung cho nhiều suite.
- Ít contract test vì các module gọi nhau trong cùng ứng dụng.
- Incident được điều tra chủ yếu qua log ứng dụng đơn lẻ.

Chiến lược này phù hợp khi ranh giới triển khai và dữ liệu còn đơn giản.

### Trigger và phân tích tác động

Sau khi tách service, rủi ro mới xuất hiện:

- API và event schema không tương thích.
- Message bị trùng hoặc đến sai thứ tự.
- Consumer chậm hoặc retry kéo dài.
- Dữ liệu giữa order và payment hội tụ không đồng thời.
- Mỗi service có lịch triển khai riêng.
- Trace bị đứt giữa các service.
- E2E cũ chậm hơn do nhiều network hop.

### Điều chỉnh chiến lược

Nhóm có thể:

- Thêm contract test cho order/payment và event notification.
- Bổ sung integration test cho outbox, retry và idempotency.
- Giữ unit test cho quy tắc tính toán và trạng thái.
- Chọn E2E cho các hành trình thanh toán và hủy đơn có rủi ro cao.
- Tạo namespace dữ liệu theo run và cleanup độc lập.
- Thêm correlation ID, trace và metric consumer lag.
- Chạy contract và test theo tác động ở pull request.
- Chạy E2E xuyên service sau tích hợp và regression rộng theo lịch.
- Đặt gate cho schema compatibility và migration.

### Xác minh kết quả

Sau khi áp dụng, nhóm đo:

- Thời gian phản hồi pull request.
- Tỷ lệ contract mismatch phát hiện trước tích hợp.
- Tỷ lệ lỗi message trùng hoặc retry.
- Thời gian điều tra xuyên service.
- Tỷ lệ E2E flaky.
- Số incident liên quan tương thích và đồng bộ dữ liệu.

Nếu pipeline nhanh hơn nhưng lỗi hợp đồng lọt sang staging tăng, cần xem lại phạm vi contract và chất lượng metadata. Chiến lược chỉ được xem là phù hợp khi tốc độ, độ tin cậy và mức bảo vệ cùng đạt mục tiêu.

## 15. Những sai lầm thường gặp

- **Coi chiến lược là tài liệu viết một lần:** nội dung nhanh chóng lệch khỏi sản phẩm.
- **Chỉ review theo lịch:** bỏ lỡ thay đổi rủi ro lớn giữa hai kỳ.
- **Chỉ phản ứng sau incident:** không phát hiện xu hướng flaky, chi phí hoặc khoảng trống từ sớm.
- **Cập nhật tài liệu nhưng không cập nhật pipeline:** quyết định không được thực thi.
- **Thay đổi pipeline mà không cập nhật tài liệu:** mất khả năng truy vết và review.
- **Không đánh giá tác động gián tiếp:** bỏ sót consumer, dữ liệu và hành trình phụ thuộc.
- **Dùng một lần test fail làm lý do thay đổi rộng:** phản ứng quá mức với tín hiệu đơn lẻ.
- **Giảm gate để đạt tốc độ:** làm giảm bảo vệ mà không có đánh giá rủi ro.
- **Không quản lý ngoại lệ có thời hạn:** kiểm soát tạm thời trở thành vĩnh viễn.
- **Không ghi quyết định và giả định:** khó hiểu lý do khi người hoặc nhóm thay đổi.
- **Không có owner:** hành động sau review không được thực hiện.
- **Xóa test cũ mà không kiểm tra traceability:** vô tình loại bỏ bằng chứng duy nhất.
- **Thêm test sau incident nhưng không xác minh hiệu quả:** có hoạt động mới nhưng không biết rủi ro đã giảm chưa.
- **Chỉ đo số lượng test hoặc tỷ lệ pass:** không phản ánh mức phù hợp với sản phẩm.
- **Không review sau thay đổi khẩn cấp:** giải pháp tạm thời không được chuẩn hóa.

## 16. Đầu ra cần có trước khi chốt cơ chế duy trì chiến lược

Một cơ chế duy trì đủ dùng nên có:

1. **Danh mục trigger:** thay đổi sản phẩm, kiến trúc, test, production, tổ chức và chính sách.
2. **Lịch rà soát:** định kỳ, theo sự kiện, trước release và sau incident.
3. **Phạm vi đánh giá tác động:** requirement, risk, dependency, test, data, environment và pipeline.
4. **Ma trận quyền quyết định:** owner, reviewer, approver và người chấp nhận rủi ro.
5. **Quy trình change request:** trigger, phương án, trade-off, chi phí và kế hoạch chuyển đổi.
6. **Quy tắc ngoại lệ:** phạm vi, kiểm soát bù, owner, thời hạn và điều kiện gỡ.
7. **Quản lý phiên bản:** lịch sử, ngày hiệu lực, phạm vi áp dụng và liên kết quyết định.
8. **Cơ chế đồng bộ:** tài liệu, test catalog, pipeline, gate, runbook và dashboard.
9. **Phản hồi từ defect/incident:** phân tích lỗi lọt và hành động phòng ngừa.
10. **Chỉ số phù hợp:** risk coverage, flaky, thời gian, chi phí và ngoại lệ quá hạn.
11. **Xác minh sau thay đổi:** baseline, tiêu chí thành công và thời điểm review lại.
12. **Truyền thông và đào tạo:** nhóm bị ảnh hưởng, hướng dẫn và trách nhiệm cập nhật.

Trước khi chốt, hãy rà soát:

- Chiến lược có trigger cập nhật rõ ràng không?
- Có cả review định kỳ và review theo sự kiện không?
- Thay đổi có được phân tích tác động đến rủi ro và phụ thuộc không?
- Các quyết định có owner, reviewer và người phê duyệt phù hợp không?
- Ngoại lệ có kiểm soát bù, thời hạn và điều kiện hết hiệu lực không?
- Tài liệu có đồng bộ với test suite, pipeline và runbook không?
- Defect và incident có tạo hành động cải tiến có thể xác minh không?
- Test cũ có được đánh giá trước khi xóa hoặc thay thế không?
- Các chỉ số có phản ánh mức bảo vệ cùng tốc độ và chi phí không?
- Thay đổi khẩn cấp có được review và chuẩn hóa sau đó không?
- Phiên bản cũ và quyết định trước đây có thể truy vết không?
- Có lịch đo lại hiệu quả sau khi áp dụng thay đổi không?

Duy trì chiến lược phù hợp với sản phẩm đang vận hành giúp hoạt động kiểm thử tiếp tục bảo vệ đúng hành vi và rủi ro khi sản phẩm, kiến trúc và tổ chức thay đổi. Khi trigger được nhận diện sớm, tác động được đánh giá có hệ thống, quyết định có owner và thay đổi được xác minh bằng dữ liệu vận hành, chiến lược sẽ vừa nhất quán vừa thích ứng. Hãy xem mỗi release, defect, incident và thay đổi kiến trúc là nguồn bằng chứng để rà soát mức phù hợp, cập nhật có kiểm soát và cải thiện vòng xác thực tiếp theo.

