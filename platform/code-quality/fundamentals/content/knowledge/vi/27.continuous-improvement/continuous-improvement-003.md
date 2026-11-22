# Đặt hiện trạng, phạm vi và bằng chứng ban đầu

Trong module `CODE_QUALITY_FUNDAMENTALS`, mục tiêu là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Ở chương **Cải thiện liên tục**, trước khi đề xuất một thay đổi lớn, nhóm cần biết mình đang ở đâu, vấn đề nằm trong phạm vi nào và bằng chứng hiện tại cho thấy điều gì. Nếu không có hiện trạng rõ ràng, nhóm khó biết vấn đề có thật sự tồn tại, thay đổi có tạo ra lợi ích hay chỉ làm các con số trông khác đi.

Hãy xét một nhóm thường xuyên nói rằng “CI quá chậm”. Nhóm quyết định chuyển toàn bộ test sang chạy song song. Sau thay đổi, thời gian pipeline trung bình giảm, nhưng một số test bắt đầu flaky và thời gian chờ để điều tra lỗi tăng lên. Nếu trước đó nhóm chỉ nhớ rằng pipeline “mất lâu”, họ không có dữ liệu để xác định thời gian nằm ở compile, unit test, integration test hay chờ runner; cũng không có mốc để so sánh độ ổn định. Một cải thiện được đánh giá chỉ bằng một con số có thể làm chất lượng tổng thể xấu đi.

**Hiện trạng (baseline)** là mô tả có căn cứ về cách hệ thống đang hoạt động trong một phạm vi và khoảng thời gian xác định. Nó có thể gồm số đo định lượng, ví dụ thực tế, quan sát của người phát triển và giới hạn dữ liệu. Baseline không phải mục tiêu, không phải lời phán xét về nhóm và cũng không phải con số được chọn để biện minh cho giải pháp đã định sẵn.

Sau bài học, người học có thể:

- Viết mô tả vấn đề dựa trên triệu chứng và tác động quan sát được.
- Xác định phạm vi hệ thống, luồng, nhóm người dùng và thời gian cần khảo sát.
- Chọn chỉ số phù hợp với mục tiêu chất lượng và định nghĩa cách đo rõ ràng.
- Thu thập bằng chứng từ CI, test, lỗi sản xuất, pull request và phản hồi của nhóm.
- Kiểm tra dữ liệu thiếu, thiên lệch mẫu, thay đổi định nghĩa và yếu tố gây nhiễu.
- Lập hồ sơ baseline có nguồn, chủ sở hữu, giới hạn và thời điểm đo.
- Dùng baseline để đánh giá cải thiện mà không khuyến khích chạy theo chỉ số.

## 1. Vì sao phải xác định hiện trạng trước khi cải thiện?

Một đề xuất cải thiện thường bắt đầu từ cảm nhận: code khó sửa, test không đáng tin, build chậm, lỗi lặp lại hoặc nhóm mất nhiều thời gian tìm nguyên nhân. Cảm nhận là tín hiệu hữu ích, nhưng để chọn đúng giải pháp cần làm rõ **điều gì đang xảy ra, ở đâu, thường xuyên đến mức nào và gây tác động gì**.

Baseline giúp nhóm:

- **Xác nhận vấn đề:** phân biệt một sự cố đơn lẻ với xu hướng lặp lại.
- **Khoanh vùng:** biết module, luồng hoặc bước công việc nào đang tạo ra trở ngại.
- **Chọn ưu tiên:** so sánh mức ảnh hưởng với các vấn đề khác.
- **Chọn giải pháp:** hiểu nguyên nhân khả dĩ trước khi quyết định refactor, thêm test hay thay quy trình.
- **Đánh giá kết quả:** có mốc so sánh trước/sau với cùng định nghĩa.
- **Giải thích quyết định:** giúp người khác hiểu vì sao nhóm đầu tư vào thay đổi đó.

Ví dụ, “test chậm” có thể có nhiều nguyên nhân:

| Quan sát ban đầu | Điều cần kiểm tra |
| --- | --- |
| Toàn bộ pipeline kéo dài | Thời gian compile, test, scan, đóng gói, chờ runner và deploy |
| Integration test chậm | Số lần tạo DB/container, dữ liệu fixture, truy vấn và timeout |
| Test thường phải rerun | Tỷ lệ flaky, nguyên nhân môi trường, thứ tự và dữ liệu chia sẻ |
| Lỗi khó tái hiện | Log, seed, phiên bản phụ thuộc và điều kiện chạy |
| Developer chờ phản hồi lâu | Thời gian từ push đến kết quả hữu ích, không chỉ tổng thời gian job |

Nếu nguyên nhân chính là runner phải chờ tài nguyên, tối ưu thuật toán test có thể không giải quyết được. Nếu integration test flaky, chạy song song nhiều hơn có thể làm tình hình xấu đi.

### Baseline là quan sát, không phải mục tiêu

Baseline trả lời “hiện tại ra sao?”. Mục tiêu cải thiện trả lời “muốn đạt điều gì?”. Hai thứ phải tách biệt:

- Baseline: trung vị thời gian CI của các PR trong bốn tuần gần nhất là 18 phút, theo cách đo đã định nghĩa.
- Mục tiêu: giảm trung vị xuống dưới 14 phút trong khi tỷ lệ flaky không tăng vượt ngưỡng đã thống nhất.

Con số ví dụ chỉ minh họa cách diễn đạt, không phải chuẩn chung. Một nhóm có pipeline 5 phút nhưng thường xuyên bỏ sót lỗi có thể cần cải thiện độ tin cậy hơn là rút thêm thời gian. **Không lấy baseline làm quota hoặc xếp hạng cá nhân.**

## 2. Chuyển cảm nhận thành mô tả vấn đề có thể kiểm chứng

Một mô tả vấn đề tốt tập trung vào triệu chứng và tác động, chưa vội kết luận giải pháp.

Có thể dùng cấu trúc:

> **Trong [phạm vi]**, khi [tình huống], chúng ta quan sát [triệu chứng] với [tần suất/phạm vi]. Điều này gây [tác động]. Bằng chứng hiện có là [nguồn]. Chúng ta chưa biết [điểm chưa rõ] và cần đo thêm [thông tin].

Ví dụ:

> Trong module đặt hàng, các PR thay đổi quy tắc tồn kho thường phải sửa cả service và job đồng bộ. Trong sáu thay đổi gần nhất, ba PR chạm cùng một quy tắc ở hai nơi và một lần gây lệch số lượng giữa màn hình và báo cáo. Điều này làm tăng thời gian review và nguy cơ xử lý sai tồn kho. Bằng chứng hiện có đến từ lịch sử PR và incident ticket; nhóm chưa thống kê đầy đủ tần suất lỗi theo tháng.

Mô tả này có thể kiểm tra bằng PR, issue, log và phỏng vấn người thực hiện. Nó chưa kết luận “phải tách microservice” hay “phải áp dụng pattern X”.

### Phân biệt triệu chứng, nguyên nhân và giải pháp

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Triệu chứng | Điều gì quan sát được? | Một thay đổi quy tắc tồn kho phải sửa hai nơi |
| Tác động | Vì sao điều đó quan trọng? | Có nguy cơ lệch số liệu, review lâu |
| Nguyên nhân giả định | Điều gì có thể tạo ra triệu chứng? | Quy tắc bị sao chép và hai luồng có vòng đời triển khai khác nhau |
| Giải pháp giả định | Có thể thử thay đổi gì? | Trích xuất quy tắc dùng chung hoặc tạo một nguồn dữ liệu chuẩn |
| Kết quả cần đo | Làm sao biết có cải thiện? | Số lần sửa lặp, lỗi phân kỳ và thời gian review |

Không nên trình bày nguyên nhân giả định như sự thật đã được chứng minh. Nếu chưa biết vì sao test flaky, hãy ghi “nghi ngờ do dữ liệu dùng chung” và thu thập log để xác minh.

### Câu hỏi giúp làm rõ vấn đề

- Vấn đề xảy ra ở bước nào trong vòng đời phát triển hoặc vận hành?
- Bắt đầu từ khi nào? Có thay đổi nền tảng, quy mô hoặc quy trình vào thời điểm đó không?
- Tần suất và mức độ ảnh hưởng ra sao?
- Ai bị ảnh hưởng: người dùng, developer, reviewer, vận hành hay dịch vụ khác?
- Có ví dụ cụ thể, PR, test report, incident hoặc log nào?
- Vấn đề có xuất hiện ở mọi trường hợp hay chỉ một nhóm dữ liệu/luồng?
- Điều gì hiện chưa đo được hoặc chưa chắc chắn?

Một câu hỏi tốt giúp thu hẹp phạm vi mà không dẫn người trả lời tới một giải pháp có sẵn.

## 3. Xác định phạm vi baseline

Phạm vi quá rộng khiến dữ liệu khó diễn giải; phạm vi quá hẹp có thể bỏ qua nguyên nhân hoặc tác động nằm ở thành phần khác. Trước khi đo, cần ghi rõ **đối tượng, ranh giới, luồng, thời gian và điều kiện áp dụng**.

### Những chiều phạm vi thường cần xác định

| Chiều | Ví dụ câu hỏi |
| --- | --- |
| Hệ thống/module | Chỉ module đặt hàng hay cả dịch vụ tồn kho và báo cáo? |
| Luồng nghiệp vụ | Tạo đơn, hủy đơn, đồng bộ kho hay tất cả? |
| Người dùng/nhóm | Developer của một squad hay mọi nhóm dùng nền tảng CI? |
| Môi trường | Local, CI, staging hay production? |
| Loại thay đổi | PR sửa logic, dependency, tài liệu hay generated code? |
| Thời gian | Bốn tuần, một chu kỳ release hay một giai đoạn tải cao? |
| Điều kiện dữ liệu | Cỡ dữ liệu, loại khách, khu vực, traffic và phiên bản API nào? |
| Ngoại lệ | Các job thủ công, rerun do runner lỗi hoặc PR bot có được tính không? |

Ví dụ, nếu muốn hiểu thời gian CI của module thanh toán, phải quyết định có tính job release, PR bot cập nhật dependency và rerun do hạ tầng hay không. Nếu thay đổi cách lọc giữa giai đoạn baseline và giai đoạn sau cải thiện, hai tập dữ liệu không còn so sánh trực tiếp được.

### Phân biệt phạm vi hệ thống và phạm vi đo

- **Phạm vi hệ thống:** phần mềm, module, quy trình hoặc nhóm người dùng đang được nghiên cứu.
- **Phạm vi đo:** các sự kiện và dữ liệu cụ thể được đưa vào chỉ số.

Ví dụ, phạm vi hệ thống là toàn bộ dịch vụ checkout, nhưng chỉ số lead time được đo trên các PR thay đổi logic nghiệp vụ, loại trừ PR chỉ sửa tài liệu. Cả hai cần được ghi rõ.

### Nêu rõ điều không nằm trong phạm vi

Việc loại trừ không có nghĩa phần đó không quan trọng. Nó giúp người đọc hiểu giới hạn kết luận:

- Chưa đo thời gian deploy production.
- Chưa có dữ liệu từ một nhóm dùng hệ thống cũ.
- Không tính PR tự động chỉ thay lockfile.
- Chưa khảo sát lỗi từ nhà cung cấp bên ngoài.

Nếu phát hiện yếu tố ngoài phạm vi có thể làm thay đổi kết luận, cần mở rộng baseline hoặc ghi rõ đây là một giới hạn cần theo dõi.

## 4. Chọn chỉ số phản ánh chất lượng cần cải thiện

Không có một chỉ số duy nhất đại diện cho chất lượng mã nguồn. Chỉ số cần gắn với vấn đề và kết quả mà nhóm muốn cải thiện.

### Một số nhóm chỉ số thường dùng

| Nhóm | Ví dụ chỉ số | Điều có thể phản ánh |
| --- | --- | --- |
| Độ tin cậy | Defect thoát ra production, incident, rollback, lỗi theo luồng | Mức độ lỗi ảnh hưởng người dùng/vận hành |
| Khả năng kiểm thử | Tỷ lệ test flaky, thời gian test, test bị skip, thời gian phản hồi | Mức tin cậy và tốc độ phản hồi của hệ thống kiểm thử |
| Khả năng thay đổi | Lead time PR, thời gian review, số nơi phải sửa cho một quy tắc | Ma sát khi phát triển và thay đổi |
| Dễ hiểu/bảo trì | Thời gian onboarding, số lần cần hỏi người sở hữu, hotspot thay đổi | Chi phí tìm hiểu và rủi ro tập trung ở vùng mã |
| Cấu trúc/phụ thuộc | Đồ thị dependency, số module bị ảnh hưởng, chu kỳ phụ thuộc | Mức khớp nối và phạm vi lan truyền thay đổi |
| Hiệu năng/tài nguyên | p50/p95/p99 latency, throughput, CPU, memory, thời gian build | Khả năng đáp ứng và chi phí tài nguyên |
| Quy trình giao hàng | Tần suất release, thời gian từ merge đến deploy, thời gian khôi phục | Khả năng đưa thay đổi ra môi trường và phục hồi |

Chỉ số trong bảng là gợi ý. Chọn ít chỉ số có liên hệ trực tiếp với vấn đề thường tốt hơn thu thập hàng chục số liệu không ai dùng.

### Chỉ số kết quả và chỉ số dẫn dắt

- **Chỉ số kết quả (lagging):** phản ánh điều đã xảy ra, như incident, lỗi production hoặc rollback.
- **Chỉ số dẫn dắt (leading):** phản ánh điều có thể ảnh hưởng kết quả sau này, như test flaky, thiếu kiểm tra ở nhánh rủi ro hoặc phụ thuộc sắp hết hỗ trợ.

Ví dụ, số incident giảm có thể là tín hiệu tốt, nhưng trong một khoảng thời gian ngắn chưa đủ để kết luận chất lượng tăng. Test hồi quy tốt hơn có thể là tín hiệu dẫn dắt, nhưng chỉ khi test có assertion hữu ích và chạy trong pipeline.

Nên kết hợp một chỉ số kết quả với một hoặc vài chỉ số dẫn dắt phù hợp. Tránh dùng một chỉ số thay thế cho mục tiêu thực sự.

### Cân bằng tốc độ và độ tin cậy

Nếu nhóm tối ưu thời gian CI, hãy theo dõi thêm tỷ lệ flaky, số test bị skip và lỗi thoát ra sau merge. Nếu tối ưu số finding analyzer, hãy theo dõi finding được xác nhận, suppression và lỗi thật bị bỏ sót. Một thay đổi có thể cải thiện một con số nhưng làm giảm chất lượng ở chiều khác.

## 5. Định nghĩa chỉ số trước khi thu thập

Tên chỉ số giống nhau chưa chắc có nghĩa giống nhau. “Thời gian review” có thể tính từ lúc mở PR tới lần approve đầu tiên, hoặc từ lúc reviewer nhận yêu cầu tới khi hoàn tất. “Tỷ lệ flaky” có thể tính theo test, theo lần chạy hoặc theo pipeline. Nếu không có định nghĩa, so sánh giữa nhóm hoặc giữa hai thời điểm dễ sai.

Mỗi chỉ số nên có một **hợp đồng đo lường**:

| Thành phần | Cần ghi |
| --- | --- |
| Tên | Tên ngắn, nhất quán |
| Mục đích | Chỉ số trả lời câu hỏi nào? |
| Định nghĩa | Sự kiện nào được tính, sự kiện nào bị loại? |
| Công thức | Tử số, mẫu số, phép tổng hợp |
| Đơn vị | Phút, giờ, phần trăm, số lần, request/giây... |
| Nguồn dữ liệu | CI, Git, issue tracker, APM, log hoặc khảo sát |
| Khoảng thời gian | Ngày bắt đầu/kết thúc và tần suất lấy mẫu |
| Phân nhóm | Module, loại PR, môi trường, mức tải hoặc loại lỗi |
| Chủ sở hữu | Ai kiểm tra chất lượng dữ liệu và giải thích biến động? |
| Giới hạn | Dữ liệu thiếu, sai lệch, thay đổi định nghĩa hoặc điều không đo được |

### Ví dụ định nghĩa một chỉ số

**Tên:** Thời gian từ khi PR sẵn sàng review tới lần review có hành động đầu tiên.

- **Bắt đầu:** thời điểm tác giả đánh dấu PR là ready for review.
- **Kết thúc:** thời điểm reviewer đầu tiên gửi review có nội dung (approve, request changes hoặc comment có ý nghĩa).
- **Đơn vị:** giờ làm việc; quy tắc tính ngoài giờ cần được xác định.
- **Phạm vi:** PR thay đổi source của module checkout; loại trừ PR bot và PR chỉ sửa tài liệu.
- **Tổng hợp:** báo median và percentile phù hợp, kèm số PR.
- **Nguồn:** sự kiện PR của hệ thống quản lý mã nguồn.
- **Giới hạn:** thời gian chờ người review không phân biệt được do tải công việc, thiếu người sở hữu hay PR chưa đủ rõ.

Định nghĩa này chưa đo toàn bộ chất lượng review hoặc thời gian từ lúc bắt đầu tới khi merge. Không nên gọi nó là “lead time thay đổi” nếu chỉ đo một đoạn của quy trình.

### Công thức phải nói rõ cách tổng hợp

Giả sử có các thời gian PR là 2, 3, 4, 4 và 40 giờ:

- Trung bình cộng là 10,6 giờ.
- Trung vị là 4 giờ.
- Giá trị lớn nhất là 40 giờ.

Trung bình bị kéo lên bởi một trường hợp dài. Trung vị mô tả điểm giữa nhưng có thể che các PR bị chờ rất lâu. Báo cáo tốt có thể nêu median, percentile cao và số mẫu để người đọc thấy cả xu hướng điển hình lẫn đuôi phân bố.

Không chọn median hay average chỉ vì một cách cho kết quả đẹp hơn. Hãy chọn cách tổng hợp theo câu hỏi cần trả lời và dùng nhất quán qua các giai đoạn.

## 6. Thu thập dữ liệu có tính đại diện

Một baseline đáng tin cần phản ánh điều kiện vận hành thông thường và những trường hợp quan trọng. Lấy một ngày có incident, một PR đặc biệt lớn hoặc một lần CI chạy nhanh bất thường làm đại diện có thể dẫn tới quyết định sai.

### Chọn khoảng thời gian phù hợp

Khoảng thời gian nên đủ để bao gồm biến động liên quan:

- Một chu kỳ làm việc hoặc release đầy đủ.
- Ngày trong tuần và cuối tuần nếu hoạt động khác nhau.
- Giai đoạn tải cao/thấp nếu đo hiệu năng hoặc vận hành.
- Nhiều loại thay đổi nếu đo lead time hoặc thời gian review.
- Các lần chạy CI bình thường và những lần có retry nếu mục tiêu là độ ổn định.

Không có một khoảng thời gian chuẩn cho mọi chỉ số. Một dịch vụ có lưu lượng theo mùa có thể cần xem nhiều tuần hoặc nhiều tháng; một lỗi build tái hiện ngay trong PR có thể chỉ cần vài lần chạy có kiểm soát để xác nhận nguyên nhân.

### Kiểm tra số lượng và chất lượng mẫu

Khi báo cáo chỉ số, nên ghi:

- Số PR, test run, request, incident hoặc mẫu đã quan sát.
- Số lượng bị loại và lý do.
- Dữ liệu thiếu hoặc không thể ghép nối.
- Các nhóm không được đại diện.
- Những thay đổi về quy trình hoặc môi trường trong khoảng đo.

Ví dụ, “tỷ lệ flaky giảm từ 4% xuống 1%” nghe có vẻ rõ, nhưng cần biết mẫu số là 25 hay 25.000 lần chạy, test selection có giống nhau không và test bị quarantine có còn nằm trong phép tính không. Một tỷ lệ không kèm số mẫu có thể gây hiểu lầm.

### Phân nhóm để tránh che khuất khác biệt

Một chỉ số tổng hợp có thể che giấu nhóm có hành vi rất khác:

- Unit test và integration test có thời gian chạy khác nhau.
- PR nhỏ và PR thay đổi kiến trúc có thời gian review khác nhau.
- Endpoint đọc và endpoint ghi có đặc điểm tải khác nhau.
- Module mới và module cũ có mức độ bao phủ test khác nhau.
- Các vùng mã có tần suất thay đổi và hậu quả lỗi khác nhau.

Hãy phân nhóm theo yếu tố có liên quan đến câu hỏi, nhưng tránh chia quá nhỏ đến mức mỗi nhóm chỉ còn một vài mẫu. Khi so sánh, giữ cách phân nhóm nhất quán giữa baseline và giai đoạn sau.

### Ví dụ về tỷ lệ lỗi

Nếu một nhóm ghi nhận 8 lỗi production trong tháng, con số đó chưa đủ để kết luận chất lượng giảm. Cần biết:

- Số lượng release và thay đổi trong tháng.
- Mức độ sử dụng hoặc số request.
- Định nghĩa “lỗi production” có thay đổi không.
- Cách phát hiện có được cải thiện không.
- Lỗi được gộp, tách hoặc phân loại như thế nào.

Tỷ lệ lỗi trên số release hoặc trên số request có thể bổ sung bối cảnh, nhưng mẫu số cũng phải phù hợp. Một lỗi dữ liệu nghiêm trọng không nên bị xem nhẹ chỉ vì số request rất lớn.

## 7. Kết hợp dữ liệu định lượng và bằng chứng định tính

Không phải mọi khía cạnh của khả năng bảo trì đều đo trực tiếp được. Thời gian tìm hiểu một module, mức dễ hiểu của API hoặc cảm giác khó thay đổi có thể cần phỏng vấn, quan sát công việc và xem ví dụ thực tế.

### Nguồn bằng chứng thường gặp

| Nguồn | Có thể cho biết | Cần lưu ý |
| --- | --- | --- |
| CI/test report | Thời gian chạy, pass/fail, skipped, flaky, coverage | Phải kiểm tra đúng commit, task và phạm vi |
| Git/PR history | Số tệp thay đổi, thời gian review, số lần sửa đi sửa lại | Nhiều tệp không tự động có nghĩa kiến trúc kém |
| Issue/incident | Lỗi, hậu quả, thời gian khôi phục, nguyên nhân lặp | Cách phân loại và mức độ ghi nhận có thể khác nhau |
| APM/log/trace | Latency, lỗi, throughput, đường gọi thực tế | Cần kiểm tra sampling, retention và cấu hình |
| Static analysis | Finding, hotspot, độ phức tạp, dependency | Finding cần xác minh theo ngữ cảnh |
| Phỏng vấn developer | Khó khăn, thời gian tìm hiểu, phụ thuộc kiến thức cá nhân | Có thể chịu ảnh hưởng của ký ức và kỳ vọng |
| Quan sát review/onboarding | Nơi người mới dừng lại, câu hỏi lặp lại, tài liệu thiếu | Cần xin phép và tránh biến quan sát thành đánh giá cá nhân |
| Khảo sát ngắn | Mức tự tin, ma sát và trải nghiệm của nhóm | Cần câu hỏi trung lập, mẫu và bối cảnh rõ |

### Phỏng vấn để tìm bằng chứng, không tìm người có lỗi

Các câu hỏi hữu ích:

- Lần gần nhất bạn cần thay đổi quy tắc này, bạn đã tìm code ở đâu?
- Phần nào mất nhiều thời gian nhất và vì sao?
- Có bước nào bạn phải nhờ một người cụ thể giải thích không?
- Có test hoặc tài liệu nào giúp bạn tự tin thay đổi?
- Điều gì thường khiến bạn phải sửa lại sau review?
- Bạn có ví dụ PR hoặc lỗi cụ thể để minh họa không?

Tránh hỏi dẫn dắt như “module này rất khó hiểu đúng không?” hoặc “bạn có nghĩ cần viết lại không?”. Những câu hỏi như vậy dễ tạo câu trả lời xác nhận giả thuyết sẵn có.

### Tam giác hóa bằng chứng

Khi có thể, hãy kiểm tra một vấn đề qua nhiều nguồn độc lập. Ví dụ, giả thuyết “module giá khó thay đổi vì quy tắc bị sao chép” có thể được hỗ trợ bởi:

- Lịch sử PR cho thấy cùng một quy tắc thường sửa ở nhiều file.
- Incident hoặc defect cho thấy hai đường xử lý từng phân kỳ.
- Developer mô tả việc phải dò nhiều nơi trước khi sửa.

Nếu ba nguồn không thống nhất, đó cũng là thông tin quan trọng. Có thể vấn đề chỉ xảy ra trong một loại thay đổi hoặc dữ liệu PR không ghi nhận đủ công việc ngoài Git.

## 8. Ví dụ xuyên suốt: đặt baseline cho dịch vụ checkout

Giả sử nhóm muốn cải thiện độ tin cậy của dịch vụ checkout. Trong vài buổi review gần đây, developer nhận thấy lỗi hồi quy xuất hiện sau thay đổi giá và test CI mất nhiều thời gian. Nhóm chưa biết nên ưu tiên test, cấu trúc code hay hạ tầng CI.

### 8.1. Viết vấn đề và giới hạn

Mô tả ban đầu:

> Trong dịch vụ checkout, các thay đổi liên quan tới giá và chiết khấu thường cần cập nhật nhiều lớp và có một số lỗi hồi quy được phát hiện sau merge. CI cũng có thời gian phản hồi dài, nhưng chưa rõ thời gian nằm ở unit test, integration test hay chờ runner. Baseline sẽ tập trung vào các PR thay đổi logic giá trong sáu tuần gần nhất, các test liên quan và thời gian phản hồi CI của những PR đó. Thời gian deploy production và các dịch vụ ngoài checkout chưa nằm trong phạm vi ban đầu.

Đây là phạm vi khởi đầu, có thể điều chỉnh nếu bằng chứng cho thấy lỗi đến từ một dịch vụ khác.

### 8.2. Chọn chỉ số và định nghĩa

| Chỉ số | Định nghĩa trong ví dụ | Nguồn |
| --- | --- | --- |
| Số PR thay đổi logic giá | PR chạm source thuộc vùng giá/chiết khấu đã xác định | PR history |
| Thời gian từ PR ready tới review đầu tiên | Số giờ làm việc giữa hai sự kiện | PR events |
| Thời gian CI | Từ lúc job bắt đầu tới lúc hoàn tất; tách queue time và execution time nếu có | CI report |
| Test flaky liên quan | Test có kết quả khác nhau giữa các lần chạy cùng revision/đầu vào được kiểm soát | Test report |
| Lỗi hồi quy sau merge | Defect được xác nhận có liên quan thay đổi logic giá | Issue/incident |
| Số nơi phải sửa quy tắc | Số implementation/điểm cấu hình cần cập nhật cho một thay đổi cùng loại | PR diff và review |

Chỉ số “số nơi phải sửa” cần định nghĩa thế nào là một nơi: file, lớp, module hay nguồn quy tắc. Nếu mỗi người đếm theo cách khác, kết quả không so sánh được.

### 8.3. Ghi nhận baseline giả định

Các số liệu sau **hoàn toàn giả định để minh họa cách lập bảng**, không phải dữ liệu của dự án thật:

| Chỉ số | Giá trị baseline giả định | Số mẫu/giới hạn |
| --- | ---: | --- |
| PR thay đổi logic giá | 12 | Sáu tuần |
| Median từ ready tới review đầu tiên | 7 giờ làm việc | 12 PR; chưa tách theo độ lớn |
| Median thời gian CI execution | 16 phút | 12 PR; chưa bao gồm thời gian chờ runner |
| Test flaky liên quan | 3 test | 40 test được theo dõi; định nghĩa flaky là có kết quả khác nhau cùng revision |
| Defect hồi quy được xác nhận | 2 | 12 PR; phân loại từ issue và review thủ công |
| Số điểm triển khai quy tắc cần sửa | Median 2 điểm | 6 PR có thay đổi chính sách; cách đếm cần được chuẩn hóa |

Không nên diễn giải “2/12 PR gây lỗi” thành xác suất lỗi chung cho mọi thay đổi checkout. Mẫu nhỏ, chỉ gồm một loại PR và cách phân loại thủ công; cần ghi giới hạn đó khi đưa ra quyết định.

### 8.4. Dùng baseline để chọn câu hỏi tiếp theo

Những số liệu trên chưa chứng minh nguyên nhân. Nhóm có thể điều tra:

- Hai defect hồi quy có cùng nguyên nhân không? Có liên quan đến quy tắc bị sao chép hay do test thiếu trường hợp biên?
- Ba test flaky có chạy song song trên dữ liệu dùng chung không?
- 16 phút CI chủ yếu là execution hay queue time?
- Hai điểm triển khai chính sách có thật sự cùng một hợp đồng hay một điểm dùng giá lịch sử?
- PR chờ review lâu vì thiếu reviewer, thiếu thông tin hay do kích thước thay đổi?

Những câu hỏi này giúp chọn cải thiện có mục tiêu. Nếu queue time chiếm phần lớn, tăng số worker hoặc tối ưu test có thể không tạo tác động như mong đợi. Nếu test flaky đến từ DB dùng chung, chỉ chuyển sang framework test khác chưa chắc giải quyết được.

### 8.5. Đặt mục tiêu sau khi hiểu baseline

Sau khi điều tra, nhóm có thể đặt một mục tiêu có cân bằng, ví dụ:

- Giảm median CI execution trong phạm vi PR logic giá.
- Không làm tăng số test flaky hoặc test bị skip.
- Bảo vệ các ngưỡng và quy tắc làm tròn bằng test hồi quy.
- Theo dõi defect hồi quy trong các chu kỳ tiếp theo.

Mục tiêu cụ thể cần dựa trên mức baseline, năng lực nhóm và mức rủi ro chấp nhận. Không đặt con số tùy ý chỉ để tạo cảm giác tham vọng.

## 9. So sánh trước và sau mà không kết luận quá mức

Sau khi triển khai cải thiện, cần so sánh với baseline bằng cùng định nghĩa và điều kiện gần tương đương. Nếu cách đo thay đổi, hãy tạo cầu nối hoặc ghi rõ hai giai đoạn không thể so sánh trực tiếp.

### Những yếu tố gây nhiễu thường gặp

- **Khối lượng công việc:** giai đoạn sau có ít PR hơn hoặc PR nhỏ hơn.
- **Thành phần thay đổi:** nhóm chuyển sang module dễ hơn hoặc ít rủi ro hơn.
- **Môi trường:** runner được nâng cấp, DB test nhanh hơn hoặc cache được cải thiện.
- **Nhân sự:** nhóm có thêm người, người có kinh nghiệm thay đổi hoặc reviewer được phân công khác.
- **Quy trình:** cách đánh dấu PR ready, phân loại defect hoặc chọn test thay đổi.
- **Mùa vụ/tải:** lượng request, release hoặc hoạt động người dùng khác nhau.
- **Cách đo:** timestamp, bộ lọc hoặc định nghĩa metric thay đổi.

Nếu CI nhanh hơn sau khi nâng cấp runner, không nên quy toàn bộ lợi ích cho refactor test. Nếu defect giảm trong tháng ít release hơn, cần thận trọng trước khi kết luận cấu trúc code mới làm hệ thống đáng tin cậy hơn.

### So sánh cùng loại với cùng định nghĩa

Một bảng trước/sau có thể gồm:

| Chỉ số | Baseline | Sau cải thiện | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Median CI execution | 16 phút | 12 phút | Cùng module, loại PR và cách tính chưa? |
| Test flaky | 3/40 | 2/42 | Test selection có thay đổi? Hai test cũ đã được sửa hay quarantine? |
| Defect hồi quy | 2/12 PR | 1/14 PR | Phân loại defect có nhất quán? Mẫu có đủ lớn? |
| Median review đầu tiên | 7 giờ | 5 giờ | Số reviewer và kích thước PR có tương đương? |

Các giá trị sau cải thiện ở bảng này cũng là **số giả định minh họa**. Chúng không chứng minh quan hệ nhân quả nếu có thay đổi môi trường hoặc mẫu. Một cách báo cáo tốt sẽ nêu biến động, dữ liệu hỗ trợ, yếu tố gây nhiễu và mức tin cậy.

### Khi nào có thể nói thay đổi đã góp phần cải thiện?

Một kết luận thận trọng có thể là:

> “Sau khi tách test dùng DB chung và giới hạn dữ liệu fixture theo từng test, tỷ lệ test flaky trong nhóm checkout giảm trong bốn tuần quan sát. Số lần chạy và phạm vi test tương tự giai đoạn baseline. Chúng tôi chưa loại trừ hoàn toàn ảnh hưởng của thay đổi runner trong tuần thứ hai; cần theo dõi thêm trước khi mở rộng kết luận sang toàn bộ repository.”

Đây là kết luận có giới hạn, nhưng hữu ích vì nói rõ hành động, quan sát và yếu tố chưa kiểm soát.

## 10. Lưu baseline thành hồ sơ có thể kiểm tra lại

Baseline nên được ghi lại ở nơi nhóm có thể tìm và cập nhật, chẳng hạn issue, tài liệu cải tiến hoặc ADR. Một bảng số liệu không có định nghĩa, nguồn và giới hạn sẽ nhanh chóng mất ý nghĩa khi người thực hiện thay đổi.

### Mẫu hồ sơ baseline

```yaml
baseline:
  id: BASELINE-CHECKOUT-001
  title: Checkout pricing change and CI feedback
  purpose: >
    Understand regression risk and feedback delay for pricing changes
    before selecting an improvement.
  scope:
    system: checkout
    workflows:
      - pricing
      - discount
    change_types:
      - application-code PR
    period:
      start: 2026-09-01
      end: 2026-10-12
    exclusions:
      - documentation-only PR
      - automated dependency update
  metrics:
    - name: ci_execution_median
      definition: >
        Median elapsed execution time from job start to completion;
        excludes runner queue time.
      unit: minutes
      source: CI reports
      sample_count: 12
      value: 16
      limitations:
        - small sample
        - PR sizes not stratified
    - name: confirmed_regression_defects
      definition: >
        Defects confirmed as regressions in pricing changes
        during the observation period.
      unit: count
      source: issue tracker and PR review
      sample_count: 12
      value: 2
      limitations:
        - manual classification
        - detection may be incomplete
  assumptions:
    - metric definitions remain unchanged during comparison
  owner: checkout-team
  recorded_at: 2026-10-14
  review_when:
    - scope changes
    - metric definition changes
    - new evidence changes the problem statement
```

Đây là cấu trúc minh họa, không phải schema bắt buộc. Dữ liệu ví dụ không phải số liệu của dự án thực tế. Một hồ sơ thật cần liên kết report hoặc nguồn dữ liệu có thể kiểm tra, đồng thời không lưu token, thông tin cá nhân hoặc log nhạy cảm không cần thiết.

### Hồ sơ cần giữ lịch sử thay đổi

Nếu metric đổi định nghĩa, đừng ghi đè âm thầm giá trị cũ. Hãy ghi:

- Định nghĩa cũ và mới.
- Lý do thay đổi.
- Thời điểm bắt đầu áp dụng định nghĩa mới.
- Có thể tính lại baseline cũ theo định nghĩa mới hay không.
- Khoảng thời gian nào không thể so sánh.

Điều này quan trọng vì một dashboard có thể trông như cải thiện chỉ vì nhóm thay cách tính. Lịch sử định nghĩa giúp người đọc phân biệt **thay đổi thực tế** với **thay đổi phép đo**.

### Mẫu ghi một quan sát

Một quan sát nên có tối thiểu:

```text
Metric: ci_execution_time
Revision: <commit hoặc pipeline run id>
Observed at: <timestamp>
Value: <giá trị và đơn vị>
Scope: <module, loại job, môi trường>
Source: <report/log có thể truy vết>
Conditions: <cache, runner, toolchain, test selection>
Notes: <điểm bất thường hoặc giới hạn>
```

Không nhất thiết tạo một bản ghi thủ công cho từng job nếu CI đã lưu metadata đầy đủ. Mục tiêu là bảo đảm có thể truy từ con số tổng hợp về các quan sát gốc khi cần điều tra.

## 11. Dữ liệu thiếu và khi chưa có baseline tốt

Nhiều nhóm chưa có telemetry đầy đủ, issue phân loại không nhất quán hoặc lịch sử PR không ghi lại mọi lần sửa. Không nên bịa một con số để hoàn thành bảng. Có thể bắt đầu bằng **baseline tạm thời** và cải thiện hệ thống đo.

### Ba mức độ bằng chứng

| Mức | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Có dữ liệu hệ thống đáng tin | CI lưu timestamp và revision; APM có định nghĩa rõ | Có thể tính chỉ số trong phạm vi dữ liệu |
| Có dữ liệu một phần | Issue được ghi nhưng phân loại chưa thống nhất; một số job thiếu report | Dùng để hình thành giả thuyết, nêu tỷ lệ thiếu |
| Chủ yếu định tính | Developer nhớ các lần sửa khó; chưa có log hoặc lịch sử đầy đủ | Ghi thành quan sát/phỏng vấn, không chuyển thành tỷ lệ chính xác |

### Cách bắt đầu khi dữ liệu chưa đủ

1. Chọn một câu hỏi nhỏ và một phạm vi hẹp.
2. Thu thập ví dụ gần đây có thể kiểm tra lại.
3. Thống nhất định nghĩa cho những quan sát mới.
4. Bắt đầu ghi dữ liệu từ thời điểm xác định.
5. Đánh dấu rõ giai đoạn đầu là baseline tạm thời.
6. Cải thiện telemetry hoặc quy trình ghi nhận nếu thiếu dữ liệu làm hạn chế quyết định.

Ví dụ, nếu không biết chính xác bao nhiêu PR bị chờ review vì thiếu reviewer, nhóm có thể bắt đầu ghi thời điểm ready, thời điểm review đầu tiên và lý do chờ trong vài tuần. Sau đó mới xem có đủ dữ liệu để phân tích hay không.

### Không lấp chỗ trống bằng giả định

Nếu issue tracker chỉ ghi những lỗi được báo bởi người dùng, số lỗi ghi nhận không phải tổng số lỗi thật. Nếu CI chỉ lưu các lần chạy cuối sau retry, tỷ lệ flaky có thể thấp hơn thực tế. Nếu developer được hỏi sau nhiều tháng, ký ức có thể bỏ sót các trường hợp.

Hãy ghi “chưa có dữ liệu đáng tin” thay vì suy ra “không có vấn đề”. Thiếu dữ liệu có thể là một vấn đề cần cải thiện riêng, đặc biệt khi tổ chức cần chứng minh độ tin cậy hoặc điều tra sự cố.

## 12. Tránh biến baseline thành công cụ gây áp lực

Đo lường có thể giúp nhóm học hỏi, nhưng cũng có thể tạo hành vi đối phó nếu chỉ số bị dùng để đánh giá cá nhân hoặc thưởng phạt trực tiếp.

Ví dụ:

- Đặt mục tiêu số PR mỗi người khiến PR bị chia nhỏ thiếu tự nhiên.
- Đặt ngưỡng thời gian review có thể khiến reviewer approve vội.
- Đặt coverage tối thiểu duy nhất có thể khuyến khích test assertion yếu.
- Đếm số finding giảm có thể khuyến khích suppression rộng.
- Đếm incident ít đi có thể khiến nhóm phân loại sự cố thấp hơn hoặc không ghi nhận.

### Nguyên tắc sử dụng chỉ số có trách nhiệm

- Đo **hệ thống và quy trình** để tìm cơ hội cải thiện, không dùng số liệu đơn lẻ để kết luận năng lực một cá nhân.
- Giải thích mục đích đo trước khi thu thập.
- Dùng chỉ số cân bằng; nếu tối ưu tốc độ, theo dõi chất lượng và độ ổn định.
- Cho nhóm cơ hội kiểm tra định nghĩa, phát hiện sai dữ liệu và nêu yếu tố gây nhiễu.
- Không che giấu mẫu bị loại, test skip hoặc finding được suppression.
- Giữ dữ liệu cá nhân ở mức tối thiểu và chỉ cho người có mục đích phù hợp truy cập.
- Ghi rõ khi số liệu được dùng cho quyết định vận hành, chất lượng hoặc phân bổ nguồn lực.

### Đo lường không thay thế đối thoại

Một biểu đồ thời gian review tăng không nói được reviewer đang quá tải, PR thiếu mô tả, yêu cầu nghiệp vụ chưa rõ hay nhóm phụ thuộc đang chờ. Hãy dùng số liệu để đặt câu hỏi và trao đổi với những người trực tiếp làm việc. Không suy đoán động cơ hoặc đánh giá con người từ một chỉ số tổng hợp.

## 13. Baseline là điểm tham chiếu có thể được cập nhật

Baseline không phải một con số bất biến. Nó có thể cần cập nhật khi:

- Phạm vi hệ thống hoặc luồng nghiệp vụ thay đổi.
- Metric được định nghĩa lại hoặc nguồn dữ liệu được sửa.
- Toolchain, CI runner, quy trình release hoặc cách phân công thay đổi đáng kể.
- Có mùa vụ, sự kiện tải hoặc thay đổi sản phẩm làm dữ liệu cũ không còn đại diện.
- Một giả thuyết nguyên nhân được bác bỏ và cần đo lại phạm vi khác.

Khi cập nhật, hãy giữ **phiên bản baseline trước đó** và ghi lý do. Nếu thay đổi môi trường làm số đo không thể so sánh, có thể cần chạy song song cách đo cũ và mới trong một khoảng thời gian hoặc tạo baseline mới.

### Khi nào nên dùng cùng baseline?

Dùng cùng định nghĩa và phạm vi khi câu hỏi vẫn giống nhau, điều kiện tương đối ổn định và dữ liệu đủ đại diện. Ví dụ, so sánh thời gian CI của cùng module, cùng loại job, cùng cách tính execution time.

### Khi nào cần tạo baseline mới?

Nếu nhóm chuyển từ một monolith sang nhiều service, đổi nền tảng CI hoặc thay toàn bộ quy trình review, metric cũ có thể không còn phản ánh cùng hệ thống. Khi đó nên ghi baseline mới và giải thích vì sao không thể so sánh trực tiếp với số liệu trước.

Không nên ép hai giai đoạn vào một biểu đồ duy nhất nếu định nghĩa hoặc phạm vi khác nhau. Một đường xu hướng đẹp nhưng so sánh sai sẽ làm quyết định kém tin cậy.

## 14. Những sai lầm thường gặp khi đặt baseline

| Sai lầm | Vì sao gây hiểu lầm | Cách xử lý |
| --- | --- | --- |
| Chọn một lần chạy bất thường làm hiện trạng | Không đại diện cho điều kiện thông thường | Dùng khoảng thời gian và mẫu phù hợp, giữ lại outlier để điều tra |
| Đo quá nhiều chỉ số không liên quan | Tốn công nhưng không giúp chọn quyết định | Bắt đầu từ câu hỏi và rủi ro cụ thể |
| Không định nghĩa tử số/mẫu số | Tỷ lệ giữa hai giai đoạn không so sánh được | Ghi công thức và điều kiện tính |
| Chỉ báo trung bình | Giá trị cực đoan có thể che trải nghiệm điển hình | Xem median, percentile, phân bố và số mẫu khi phù hợp |
| Chỉ báo số lượng mà không có mẫu số | Không biết khối lượng hoạt động thay đổi thế nào | Bổ sung mẫu số phù hợp và vẫn nêu hậu quả của từng sự kiện nghiêm trọng |
| Gộp các nhóm khác nhau | Nhóm nhỏ có thể bị che bởi nhóm lớn | Phân nhóm theo yếu tố liên quan và giữ cách phân nhóm nhất quán |
| Thay định nghĩa giữa chừng mà không ghi lại | Biến động có thể chỉ do cách đo | Lưu phiên bản định nghĩa và thời điểm áp dụng |
| Dùng dữ liệu thiếu như thể đầy đủ | Đánh giá thấp vấn đề hoặc phóng đại cải thiện | Báo số mẫu, dữ liệu thiếu và nguồn không bao phủ |
| Coi tương quan là nguyên nhân | Nhiều yếu tố có thể thay đổi cùng lúc | Ghi yếu tố gây nhiễu, kiểm tra giả thuyết và diễn đạt thận trọng |
| Dùng chỉ số để xếp hạng cá nhân | Tạo hành vi chạy theo số và che giấu vấn đề | Dùng để cải thiện hệ thống, kết hợp đối thoại và bối cảnh |
| Chọn baseline sau khi đã biết kết quả mong muốn | Có nguy cơ chọn khoảng đo có lợi | Định nghĩa phạm vi và metric trước khi đánh giá sau cải thiện |
| Không lưu nguồn và revision | Không thể truy nguyên con số | Liên kết report, commit, pipeline run và cách tính |

## 15. Checklist lập baseline trước khi đề xuất cải thiện

Trước khi chọn giải pháp, hãy kiểm tra:

- [ ] Vấn đề được mô tả bằng triệu chứng và tác động quan sát được.
- [ ] Nguyên nhân được ghi là giả thuyết cho tới khi có bằng chứng.
- [ ] Phạm vi hệ thống, luồng, loại thay đổi và môi trường được xác định.
- [ ] Khoảng thời gian và điều kiện dữ liệu đủ đại diện cho câu hỏi.
- [ ] Các trường hợp loại trừ và giới hạn được ghi rõ.
- [ ] Mỗi metric có định nghĩa, công thức, đơn vị, nguồn và chủ sở hữu.
- [ ] Số mẫu, dữ liệu thiếu và cách xử lý outlier được công bố.
- [ ] Các nhóm quan trọng được phân tích riêng khi cần.
- [ ] Có cả bằng chứng định lượng và định tính phù hợp.
- [ ] Chỉ số cân bằng giữa tốc độ, độ tin cậy và khả năng thay đổi.
- [ ] Dữ liệu được dùng cho mục đích cải thiện, có bảo vệ quyền riêng tư.
- [ ] Baseline được lưu với ngày đo, revision/nguồn và phiên bản định nghĩa.

Không phải dự án nào cũng cần đủ mọi loại metric. Checklist giúp phát hiện khoảng trống; hãy giải thích những mục không áp dụng thay vì thu thập dữ liệu không có mục đích.

## 16. Bài tập thực hành

### Bài 1 — Chuyển cảm nhận thành vấn đề

Một developer nói: “Module khách hàng rất khó sửa và test lúc nào cũng chậm.” Viết lại thành mô tả vấn đề có phạm vi, triệu chứng, tác động, bằng chứng hiện có và điều chưa biết. Không đưa giải pháp vào câu mô tả.

### Bài 2 — Chọn phạm vi đo

Nhóm muốn đo thời gian phản hồi CI cho PR của dịch vụ thanh toán. Xác định hệ thống, loại PR, loại job, môi trường, khoảng thời gian và các trường hợp loại trừ. Giải thích vì sao không nên gộp thời gian chờ runner với thời gian thực thi nếu câu hỏi là hiệu năng test.

### Bài 3 — Định nghĩa metric

Viết hợp đồng đo cho “tỷ lệ test flaky”. Xác định đơn vị quan sát (test hay test run), điều kiện để gọi là flaky, mẫu số, khoảng thời gian, cách xử lý retry và test bị quarantine. Nêu giới hạn nếu chỉ lưu kết quả cuối cùng của mỗi pipeline.

### Bài 4 — Đọc số liệu thận trọng

Thời gian review của năm PR là 2, 3, 4, 4 và 40 giờ. Tính trung bình và trung vị; giải thích mỗi số trả lời câu hỏi gì. Nêu vì sao cần xem PR 40 giờ thay vì tự động loại nó như outlier.

### Bài 5 — Kết hợp nhiều nguồn

Nhóm nghi ngờ một quy tắc nghiệp vụ bị sao chép ở nhiều nơi. Hãy đề xuất bằng chứng từ Git/PR, incident/issue và phỏng vấn developer. Nêu một kết quả có thể bác bỏ giả thuyết ban đầu.

### Bài 6 — Đánh giá tính đại diện

Baseline có 4 PR trong tuần release lớn; giai đoạn sau có 20 PR nhỏ trong một tháng ít hoạt động. Hãy chỉ ra vì sao so sánh trực tiếp có thể sai và cách phân nhóm hoặc kéo dài thời gian đo để có kết quả phù hợp hơn.

### Bài 7 — Lập baseline cho checkout

Dựa trên ví dụ ở mục 8, tạo một bảng baseline gồm ít nhất ba metric, định nghĩa, giá trị giả định, số mẫu, nguồn và giới hạn. Phân biệt rõ dữ liệu giả định với dữ liệu thực tế.

### Bài 8 — Nhận diện yếu tố gây nhiễu

Sau khi tối ưu test, CI nhanh hơn 30%. Cùng thời điểm, nhóm cũng nâng cấp runner, giảm số integration test và thay đổi cache. Hãy viết kết luận thận trọng và đề xuất cách thu thập bằng chứng để tách ảnh hưởng của từng thay đổi.

### Bài 9 — Tránh hành vi chạy theo chỉ số

Quản lý đặt mục tiêu mỗi developer phải merge ít nhất năm PR mỗi tuần và thời gian review dưới hai giờ. Phân tích các hành vi đối phó có thể xảy ra, chỉ số cân bằng cần theo dõi và cách dùng baseline để cải thiện quy trình thay vì xếp hạng cá nhân.

### Bài 10 — Viết hồ sơ baseline

Chọn một vấn đề chất lượng trong dự án. Viết hồ sơ gồm mục đích, phạm vi, thời gian, metric, định nghĩa, nguồn, số mẫu, giới hạn, owner và thời điểm xem lại. Một người không tham gia thu thập dữ liệu có thể hiểu con số đến từ đâu và kết luận nào chưa được phép đưa ra không?

**Tiêu chí tự đánh giá:** lời giải cần nối được **vấn đề → phạm vi → metric có định nghĩa → nguồn và mẫu → giới hạn → cách dùng baseline cho quyết định tiếp theo**. Một con số không có công thức, nguồn hoặc bối cảnh chưa phải bằng chứng đủ tin cậy.

## Ghi nhớ

**Cải thiện có căn cứ bắt đầu từ việc hiểu hiện trạng.** Hãy mô tả triệu chứng và tác động trước khi chọn giải pháp; khoanh rõ hệ thống, luồng, thời gian và điều kiện đo; định nghĩa metric với công thức, đơn vị, nguồn và chủ sở hữu; kết hợp số liệu với ví dụ và phản hồi thực tế. Kiểm tra mẫu, dữ liệu thiếu, yếu tố gây nhiễu và giới hạn kết luận. Lưu baseline có thể truy nguyên và cập nhật định nghĩa một cách minh bạch. Mục tiêu không phải tạo dashboard đẹp hoặc xếp hạng con người, mà là giúp nhóm chọn cải thiện phù hợp và biết liệu phần mềm có trở nên **đáng tin cậy, dễ hiểu và dễ thay đổi hơn** hay không.
