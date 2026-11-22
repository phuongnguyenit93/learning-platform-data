# Phân rã công việc theo phân tích, chuẩn bị, thực thi và bảo trì

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), nguồn lực không chỉ là số lượng người thực hiện test. Một hoạt động kiểm thử cần có thời gian phân tích, kỹ năng phù hợp, môi trường, dữ liệu, công cụ, quyền truy cập, sự phối hợp với các nhóm khác và công sức duy trì bằng chứng sau khi kiểm tra. Nếu chỉ ước lượng thời gian chạy test, kế hoạch dễ thiếu phần chuẩn bị, điều tra lỗi, dọn dữ liệu và bảo trì bộ kiểm thử.

Phân rã công việc giúp biến mục tiêu kiểm thử thành các hoạt động có thể giao trách nhiệm, ước lượng, theo dõi và điều chỉnh. Bài học này tổ chức công việc theo bốn giai đoạn: **phân tích, chuẩn bị, thực thi và bảo trì**. Mỗi giai đoạn cần xác định đầu vào, hoạt động, đầu ra, vai trò, kỹ năng và nguồn lực cần thiết. Cách làm này giúp nhóm nhìn thấy tổng chi phí kiểm thử, phát hiện điểm nghẽn sớm và phân bổ nguồn lực theo rủi ro.

## 1. Vì sao cần phân rã công việc kiểm thử?

### 1.1. Tránh chỉ tính phần thực thi

Một kế hoạch ghi “kiểm thử chức năng trong ba ngày” thường chưa đủ để dự báo công sức. Trước khi chạy test, nhóm cần hiểu yêu cầu, xác định rủi ro, thiết kế phạm vi, chuẩn bị dữ liệu và môi trường. Sau khi chạy, nhóm còn phải phân loại kết quả, tái hiện lỗi, báo cáo, sửa test, dọn tài nguyên và cập nhật tài liệu.

Tổng công việc có thể bao gồm:

- Phân tích yêu cầu, kiến trúc và thay đổi.
- Xác định rủi ro, phạm vi và tiêu chí hoàn tất.
- Thiết kế test, dữ liệu và chiến lược bao phủ.
- Chuẩn bị môi trường, tài khoản, công cụ và quyền.
- Thực thi thủ công, tự động hoặc kết hợp.
- Theo dõi, điều tra và báo cáo lỗi.
- Xác minh sửa lỗi và chạy hồi quy.
- Bảo trì test, fixture, môi trường và tài liệu.

Nếu các hoạt động này không được thể hiện trong kế hoạch, ước lượng dễ thấp hơn thực tế, người thực hiện bị quá tải và chất lượng bị ảnh hưởng khi thời hạn đến gần.

### 1.2. Phân rã giúp gắn nguồn lực với rủi ro

Không phải mọi chức năng cần cùng mức công sức. Một thay đổi liên quan đến quyền truy cập, giao dịch tài chính hoặc dữ liệu nhạy cảm thường cần nhiều phân tích và bằng chứng hơn một thay đổi nội dung tĩnh.

Phân rã theo rủi ro giúp trả lời:

- Hoạt động nào cần chuyên môn bảo mật, dữ liệu, hiệu năng hoặc tích hợp?
- Cần môi trường và phụ thuộc nào để kiểm tra?
- Công việc nào có thể chạy song song?
- Công việc nào phải chờ đầu ra của giai đoạn trước?
- Nếu thiếu người, thiết bị hoặc môi trường thì rủi ro nào tăng lên?
- Phần nào cần được duy trì sau khi tính năng phát hành?

Nguồn lực nên được phân bổ theo giá trị và hậu quả nếu không thực hiện, thay vì chia đều theo số lượng test case.

### 1.3. Phân rã công việc và phân rã test case là hai việc khác nhau

Phân rã test case chia hành vi cần kiểm tra thành các trường hợp cụ thể. Phân rã công việc kiểm thử chia toàn bộ hoạt động cần làm để có được bằng chứng đáng tin cậy.

Ví dụ, một test case thanh toán thành công là một phần của công việc thực thi. Nhưng để chạy được nó, nhóm có thể cần phân tích hợp đồng nhà cung cấp, tạo tài khoản sandbox, cấu hình secret, chuẩn bị dữ liệu đơn hàng, kiểm tra callback, lưu trace và dọn giao dịch thử nghiệm. Những hoạt động này cần xuất hiện trong kế hoạch nguồn lực.

## 2. Mô hình bốn giai đoạn

### 2.1. Phân tích

Giai đoạn phân tích xác định cần kiểm tra điều gì, vì sao cần kiểm tra và bằng chứng nào đủ để đưa ra quyết định.

Đầu vào thường gồm yêu cầu, tiêu chí chấp nhận, thiết kế, thay đổi mã nguồn, sơ đồ kiến trúc, lịch sử lỗi và dữ liệu vận hành. Đầu ra có thể là phạm vi kiểm thử, danh sách rủi ro, ma trận truy vết, chiến lược test, ước lượng và kế hoạch nguồn lực.

### 2.2. Chuẩn bị

Giai đoạn chuẩn bị biến kế hoạch thành điều kiện có thể thực thi. Nhóm cấp phát hoặc xác minh môi trường, chuẩn bị dữ liệu, tài khoản, công cụ, quyền truy cập, test script và tiêu chí readiness.

Đầu ra cần cho biết môi trường đã sẵn sàng, dữ liệu có thể tái lập, công cụ hoạt động và người thực hiện có đủ quyền hay chưa.

### 2.3. Thực thi

Giai đoạn thực thi chạy test theo kế hoạch, thu thập kết quả, điều tra sai lệch, ghi nhận lỗi và xác minh các bản sửa. Đây không chỉ là thao tác chạy test; còn có triage, trao đổi với phát triển và đánh giá mức độ đủ của bằng chứng.

Đầu ra gồm kết quả test, lỗi đã xác nhận, bằng chứng, trạng thái bao phủ, rủi ro còn lại và đề xuất quyết định.

### 2.4. Bảo trì

Giai đoạn bảo trì giữ cho bộ kiểm thử và tài nguyên hỗ trợ còn phù hợp sau mỗi thay đổi. Nhóm cập nhật test lỗi thời, loại bỏ trùng lặp, xử lý flaky test, cập nhật fixture, môi trường, tài liệu và liên kết truy vết.

Bảo trì là công việc liên tục trong suốt vòng đời sản phẩm, không phải chỉ thực hiện khi bộ test đã hỏng.

### 2.5. Mối quan hệ giữa các giai đoạn

Các giai đoạn thường nối tiếp nhưng không phải lúc nào cũng tuyến tính. Khi thực thi phát hiện yêu cầu chưa rõ, nhóm có thể quay lại phân tích. Khi môi trường không sẵn sàng, nhóm quay lại chuẩn bị. Khi lỗi được sửa, test có thể cần cập nhật và chạy lại. Một thay đổi trong kiến trúc cũng có thể làm phát sinh phân tích và bảo trì mới.

| Giai đoạn | Câu hỏi chính | Đầu ra quan trọng |
|---|---|---|
| Phân tích | Cần xác minh điều gì và rủi ro nào quan trọng? | Phạm vi, rủi ro, chiến lược, tiêu chí, ước lượng. |
| Chuẩn bị | Có đủ điều kiện để kiểm tra đáng tin cậy không? | Môi trường, dữ liệu, công cụ, quyền và readiness. |
| Thực thi | Bằng chứng cho thấy kết quả thực tế là gì? | Kết quả test, lỗi, báo cáo và rủi ro còn lại. |
| Bảo trì | Làm sao giữ kiểm thử hữu ích qua các thay đổi? | Test được cập nhật, flaky được xử lý, tài liệu và môi trường được duy trì. |

## 3. Phân rã công việc trong giai đoạn phân tích

### 3.1. Thu thập và làm rõ đầu vào

Các hoạt động có thể gồm:

- Đọc yêu cầu, user story và tiêu chí chấp nhận.
- Làm rõ hành vi chưa xác định, điều kiện biên và trạng thái lỗi.
- Xem xét thay đổi thiết kế, API contract và schema dữ liệu.
- Xác định thành phần, service và bên thứ ba bị ảnh hưởng.
- Thu thập lịch sử sự cố, lỗi hồi quy và phản hồi người dùng.
- Xác định nền tảng, trình duyệt, thiết bị và môi trường được hỗ trợ.

Cần có người chịu trách nhiệm làm rõ quyết định nghiệp vụ. QA có thể phát hiện câu hỏi và đề xuất tiêu chí, nhưng không nên tự giả định quy tắc mà chủ sở hữu sản phẩm chưa xác nhận.

### 3.2. Phân tích rủi ro và phạm vi

Chia công việc thành các hoạt động cụ thể:

1. Xác định tài sản và hành trình quan trọng.
2. Nhận diện tác nhân, trạng thái và ranh giới có rủi ro.
3. Đánh giá khả năng xảy ra và tác động.
4. Xác định các khu vực cần kiểm thử sâu.
5. Ghi rõ phần nằm ngoài phạm vi và lý do.
6. Xác định rủi ro còn lại cần người có thẩm quyền xem xét.

Đầu ra nên có danh sách rủi ro ưu tiên, không chỉ là một câu “kiểm thử toàn bộ”.

### 3.3. Thiết kế chiến lược và độ bao phủ

Công việc có thể gồm:

- Chọn tầng unit, contract, API, integration, UI/E2E và kiểm thử phi chức năng.
- Xác định phân vùng tương đương và giá trị biên.
- Chọn luồng thành công, lỗi, phục hồi và quyền truy cập.
- Xác định phần có thể tự động hóa và phần cần kiểm thử thủ công/khám phá.
- Xác định dữ liệu, fixture và phụ thuộc.
- Xác định tiêu chí hoàn tất và bằng chứng.
- Liên kết yêu cầu, rủi ro, test case và kết quả.

Không phải mọi mục tiêu cần được kiểm tra ở mọi tầng. Hãy chọn tầng có thể chứng minh rủi ro với độ tin cậy và chi phí phù hợp.

### 3.4. Ước lượng và lập kế hoạch

Ước lượng phân tích cần tính đến:

- Độ rõ của yêu cầu và thời gian cần để làm rõ.
- Số thành phần hoặc nhóm liên quan.
- Mức độ phức tạp của luồng và trạng thái.
- Mức độ mới của công nghệ hoặc công cụ.
- Nhu cầu review chuyên môn.
- Thời gian chuẩn bị ma trận và tài liệu.
- Rủi ro phát sinh từ phụ thuộc bên ngoài.

Đừng chỉ ước lượng theo số lượng test case. Hai test case có thể có chi phí rất khác nhau nếu một ca chỉ kiểm tra API cục bộ, còn ca kia cần nhiều service, tài khoản và callback bất đồng bộ.

## 4. Phân rã công việc trong giai đoạn chuẩn bị

### 4.1. Môi trường và hạ tầng

Các hoạt động thường gồm:

- Đặt chỗ hoặc cấp phát môi trường.
- Triển khai đúng build và phiên bản phụ thuộc.
- Cấu hình database, broker, cache, network và storage.
- Áp dụng migration và feature flag.
- Kiểm tra health, readiness và quyền truy cập.
- Xác minh tài nguyên và quota cho mức song song.
- Chuẩn bị log, metrics, trace và dashboard.

Cần phân biệt thời gian chờ môi trường với công sức lao động. Ví dụ, provisioning mất hai giờ nhưng chỉ cần 20 phút thao tác của kỹ sư; hai con số này ảnh hưởng kế hoạch theo cách khác nhau.

### 4.2. Dữ liệu và tài khoản

Công việc chuẩn bị dữ liệu có thể gồm:

- Thiết kế fixture và trạng thái ban đầu.
- Tạo dữ liệu đại diện và dữ liệu biên.
- Chuẩn bị tài khoản theo vai trò.
- Xác minh quyền và trạng thái session.
- Ẩn danh hoặc tổng hợp dữ liệu nếu cần dữ liệu gần thực tế.
- Định danh dữ liệu theo test run để tránh xung đột.
- Xác định cách cleanup và TTL.

Nếu dữ liệu phụ thuộc nhiều service, cần phối hợp với người sở hữu từng nguồn. Dữ liệu không hợp lệ hoặc không nhất quán có thể khiến test thất bại trước khi hành vi mục tiêu được thực thi.

### 4.3. Công cụ và automation

Các hoạt động có thể gồm:

- Cấu hình test runner và dependency.
- Thiết lập browser grid hoặc thiết bị.
- Cấu hình pipeline, secret và quyền service account.
- Chuẩn bị test script, helper, fixture và assertion.
- Xác minh công cụ báo cáo và lưu artifact.
- Kiểm tra khả năng tái lập trên máy khác hoặc CI.

Không nên tính một framework automation là “đã sẵn sàng” chỉ vì nó cài được. Cần xác minh nó kết nối đúng môi trường, có thể tạo dữ liệu và trả kết quả có thể điều tra.

### 4.4. Readiness gate

Trước khi thực thi, xác minh:

- Artifact đúng commit/build.
- Service bắt buộc đã sẵn sàng.
- Database schema đúng phiên bản.
- Broker, queue và consumer đã sẵn sàng nếu cần.
- Tài khoản và quyền hợp lệ.
- Fixture đã được tạo và kiểm tra.
- Sandbox bên ngoài có thể truy cập.
- Công cụ thu thập bằng chứng hoạt động.
- Không có bảo trì hoặc thay đổi gây nhiễu.

Nếu một điều kiện bắt buộc không đạt, trạng thái cần là BLOCKED hoặc ENVIRONMENT_FAILURE. Không nên bắt đầu suite rồi coi lỗi setup là lỗi chức năng.

## 5. Phân rã công việc trong giai đoạn thực thi

### 5.1. Chạy test và ghi kết quả

Công việc có thể gồm:

- Chạy suite theo thứ tự và mức song song đã định.
- Theo dõi tiến độ, tài nguyên và trạng thái môi trường.
- Lưu kết quả pass, fail, skipped và blocked.
- Thu thập log, screenshot, trace và request/response đã lọc dữ liệu nhạy cảm.
- Ghi nhận phiên bản, dữ liệu và cấu hình của run.
- Đối chiếu test đã chạy với phạm vi kế hoạch.

Thời gian chạy của suite không đồng nghĩa với công sức con người. Một job chạy tự động trong một giờ có thể cần ít thao tác nhưng vẫn cần người theo dõi, triage và xử lý kết quả.

### 5.2. Triage và điều tra lỗi

Khi test thất bại, cần phân loại:

- Lỗi sản phẩm.
- Lỗi test hoặc assertion.
- Lỗi môi trường/hạ tầng.
- Lỗi dữ liệu hoặc fixture.
- Lỗi dependency bên ngoài.
- Flaky hoặc chưa đủ bằng chứng.

Công việc điều tra có thể gồm tái hiện, thu thập trace, kiểm tra dữ liệu, so sánh phiên bản, phân tích thay đổi và trao đổi với developer hoặc owner của dependency.

Không nên ước lượng triage bằng một tỷ lệ cố định cho mọi dự án. Hệ thống mới, tích hợp phức tạp hoặc môi trường không ổn định thường cần dự phòng điều tra lớn hơn.

### 5.3. Báo cáo và quyết định

Báo cáo cần nêu:

- Phạm vi đã thực thi và chưa thực thi.
- Kết quả theo test layer hoặc nhóm rủi ro.
- Lỗi đã xác nhận và mức độ ảnh hưởng.
- Test bị block, skip hoặc quarantine.
- Chất lượng môi trường và giới hạn bằng chứng.
- Rủi ro còn lại, biện pháp giảm thiểu và owner.
- Khuyến nghị cho quyết định tiếp theo.

Người thực hiện kiểm thử cung cấp bằng chứng và khuyến nghị. Quyết định chấp nhận rủi ro hoặc phát hành cần thuộc đúng vai trò có thẩm quyền.

### 5.4. Xác minh sửa lỗi và hồi quy

Khi có bản sửa:

1. Xác minh lỗi gốc đã được tái hiện và hiểu.
2. Chạy lại test tái hiện lỗi.
3. Chạy test liên quan đến vùng bị ảnh hưởng.
4. Chạy regression suite phù hợp.
5. Xác minh không tạo lỗi mới hoặc tác dụng phụ.
6. Cập nhật trạng thái lỗi và bằng chứng.

Cần tính thời gian cho vòng lặp sửa và xác minh. Một lỗi có thể cần nhiều vòng trao đổi và build trước khi được xác nhận đóng.

## 6. Phân rã công việc trong giai đoạn bảo trì

### 6.1. Bảo trì test case và automation

Các hoạt động thường xuyên:

- Cập nhật test theo yêu cầu hoặc hành vi mới.
- Sửa selector, fixture và helper lỗi thời.
- Loại bỏ test trùng hoặc không còn giá trị.
- Điều tra và giảm flaky test.
- Tối ưu thời gian chạy và mức song song.
- Cập nhật test impact mapping và tag.
- Bổ sung regression test từ lỗi đã sửa.

Không nên chỉ sửa test để làm pipeline xanh nếu nguyên nhân là sản phẩm sai. Cần phân biệt lỗi test với regression thật.

### 6.2. Bảo trì môi trường và dữ liệu

Công việc có thể gồm:

- Cập nhật image, runtime và dependency.
- Rà soát cấu hình drift.
- Gia hạn hoặc thu hồi credential.
- Cập nhật sandbox và quota.
- Dọn fixture, tài khoản và tài nguyên mồ côi.
- Kiểm tra backup và khả năng khôi phục nếu thuộc phạm vi.
- Cập nhật readiness và cleanup automation.

Môi trường dùng lâu có thể tích lũy dữ liệu và cấu hình ngoài dự kiến. Cần có lịch reset, kiểm tra drift hoặc cấp phát mới theo mức độ rủi ro.

### 6.3. Bảo trì tài liệu và truy vết

Giữ đồng bộ:

- Yêu cầu và tiêu chí chấp nhận.
- Danh mục rủi ro.
- Test plan và test case.
- Hướng dẫn setup và cleanup.
- Ma trận môi trường.
- Runbook điều tra lỗi.
- Báo cáo và quyết định chấp nhận rủi ro.

Tài liệu cũ có thể khiến người mới chạy test sai cách hoặc hiểu nhầm phạm vi bằng chứng.

### 6.4. Rà soát giá trị và loại bỏ nợ kiểm thử

Định kỳ đánh giá:

- Test nào còn bảo vệ rủi ro hiện tại?
- Test nào không còn chạy hoặc thường xuyên flaky?
- Test nào có thể chuyển xuống tầng thấp hơn để chạy nhanh hơn?
- Test nào cần thêm do lỗi production hoặc thay đổi kiến trúc?
- Môi trường nào không còn được sử dụng?
- Công cụ hoặc tài khoản nào có thể thu hồi?
- Có test nào phụ thuộc vào người hoặc kiến thức đơn lẻ không?

Bảo trì không chỉ là sửa lỗi. Nó còn là việc giảm chi phí sở hữu và giữ bộ kiểm thử phù hợp với sản phẩm.

## 7. Xác định các loại nguồn lực cần thiết

### 7.1. Con người và kỹ năng

Nguồn lực con người nên được mô tả theo kỹ năng và trách nhiệm, không chỉ theo chức danh.

| Năng lực | Hoạt động có thể cần |
|---|---|
| Phân tích nghiệp vụ | Làm rõ hành vi, trạng thái và tiêu chí chấp nhận. |
| Thiết kế kiểm thử | Phân tích rủi ro, phân vùng dữ liệu và thiết kế bao phủ. |
| API và tích hợp | Kiểm tra contract, service, database và message flow. |
| UI/E2E | Thiết kế hành trình, selector và xác minh trải nghiệm. |
| Automation | Framework, pipeline, fixture, báo cáo và giảm flaky. |
| Bảo mật | Xác thực, phân quyền, dữ liệu nhạy cảm và kiểm tra bảo mật. |
| Hiệu năng | Thiết kế tải, dữ liệu, đo lường và phân tích bottleneck. |
| Dữ liệu | Chuẩn bị, ẩn danh, đối soát và cleanup. |
| DevOps/SRE | Cấp phát môi trường, readiness, observability và teardown. |
| Phát triển | Giải thích thiết kế, sửa lỗi và hỗ trợ điều tra. |

Một người có thể đảm nhiệm nhiều năng lực, nhưng cần tránh phụ thuộc vào một cá nhân duy nhất cho kiến thức quan trọng. Với kỹ năng hiếm, cần đặt lịch sớm hoặc chuẩn bị phương án thay thế.

### 7.2. Môi trường và hạ tầng

Ghi rõ nhu cầu:

- Số lượng môi trường và thời gian sử dụng.
- CPU, memory, storage và network.
- Database, broker, cache và service phụ thuộc.
- Browser, thiết bị hoặc hệ điều hành.
- Sandbox và quota bên thứ ba.
- Khả năng chạy song song.
- Thời gian cấp phát và thu hồi.

Môi trường có thể có chi phí theo giờ hoặc theo tài nguyên. Cần tính cả thời gian chờ và chi phí giữ môi trường khi không sử dụng.

### 7.3. Công cụ và giấy phép

Các loại công cụ có thể gồm:

- Test management và quản lý yêu cầu.
- Automation framework và CI runner.
- Browser/device grid.
- API client và contract testing.
- Performance/load testing.
- Security scanning.
- Log, metrics, tracing và dashboard.
- Báo cáo, artifact storage và quản lý dữ liệu.

Ghi rõ ai cần quyền sử dụng, số lượng license, giới hạn concurrent session, thời hạn và chi phí. Không nên giả định mọi thành viên đều có quyền truy cập công cụ hoặc dữ liệu.

### 7.4. Dữ liệu, quyền và phụ thuộc

Dữ liệu thử nghiệm, tài khoản, certificate, API key, network access và sự hỗ trợ từ nhóm khác đều là nguồn lực cần lập kế hoạch. Một test có thể chỉ mất vài phút để chạy nhưng cần nhiều ngày chờ sandbox hoặc quyền truy cập được cấp.

Phân biệt:

- Công sức trực tiếp của nhóm.
- Thời gian chờ phụ thuộc.
- Thời gian tài nguyên được giữ.
- Chi phí giấy phép hoặc hạ tầng.
- Chi phí điều tra và xử lý sự cố.

## 8. Ước lượng công việc và dự phòng

### 8.1. Ước lượng theo work breakdown structure

Tạo danh sách công việc phân cấp theo bốn giai đoạn, sau đó ước lượng từng hoạt động. Ví dụ:

| Giai đoạn | Work package | Đầu ra |
|---|---|---|
| Phân tích | Review yêu cầu và làm rõ | Danh sách câu hỏi được xác nhận. |
| Phân tích | Risk assessment và test strategy | Risk register và phạm vi test. |
| Phân tích | Thiết kế test và ước lượng | Test design và resource plan. |
| Chuẩn bị | Cấp phát môi trường | Environment ID và phiên bản. |
| Chuẩn bị | Chuẩn bị dữ liệu và tài khoản | Fixture và account matrix. |
| Chuẩn bị | Setup automation và readiness | Pipeline/job sẵn sàng. |
| Thực thi | Chạy test và thu bằng chứng | Test results và artifacts. |
| Thực thi | Triage và xác minh lỗi | Bug reports và retest results. |
| Thực thi | Báo cáo và quyết định | Quality report và residual risks. |
| Bảo trì | Cập nhật test/fixture | Bộ test được đồng bộ. |
| Bảo trì | Sửa flaky và môi trường | Reliability improvements. |
| Bảo trì | Cập nhật tài liệu và truy vết | Tài liệu hiện hành. |

Ước lượng nên bao gồm người thực hiện, thời lượng, phụ thuộc và mức độ không chắc chắn. Có thể dùng giờ công, ngày công hoặc story point tùy cách quản lý của nhóm, nhưng phải thống nhất đơn vị.

### 8.2. Phân biệt effort và elapsed time

- **Effort:** tổng thời gian lao động thực tế cần bỏ ra.
- **Elapsed time:** thời gian lịch từ lúc bắt đầu đến khi hoàn thành, gồm cả chờ đợi và phụ thuộc.

Ví dụ, cấp quyền sandbox cần 30 phút công sức của người phụ trách nhưng có thể mất hai ngày lịch để được phê duyệt. Nếu chỉ ghi 30 phút, kế hoạch mốc phát hành sẽ thiếu hai ngày chờ.

### 8.3. Dùng ước lượng theo khoảng khi chưa chắc chắn

Với công việc chưa rõ, có thể dùng ba điểm:

- Optimistic: điều kiện thuận lợi.
- Most likely: kịch bản có khả năng cao nhất.
- Pessimistic: có phụ thuộc hoặc vấn đề phát sinh.

Một cách ước lượng tham khảo là:

\[
E = \frac{O + 4M + P}{6}
\]

Trong đó \(O\) là ước lượng lạc quan, \(M\) là ước lượng có khả năng cao nhất và \(P\) là ước lượng bi quan. Công thức chỉ là công cụ hỗ trợ, không thay thế việc xem xét giả định và rủi ro.

### 8.4. Dự phòng theo rủi ro

Dự phòng cần dựa trên nguồn bất định cụ thể:

- Yêu cầu chưa rõ.
- Phụ thuộc bên ngoài chưa xác nhận.
- Môi trường mới hoặc chưa ổn định.
- Dữ liệu khó chuẩn bị.
- Tích hợp nhiều service.
- Kỹ năng chuyên môn khan hiếm.
- Lịch sử có nhiều vòng sửa và retest.

Không nên thêm một tỷ lệ dự phòng tùy tiện rồi coi mọi rủi ro đã được bao phủ. Hãy ghi lý do, giả định và điều kiện sử dụng dự phòng.

## 9. Phân công, trách nhiệm và phụ thuộc

### 9.1. Giao việc theo năng lực và quyền quyết định

Mỗi work package nên có một người chịu trách nhiệm chính, người phối hợp và người có quyền xác nhận đầu ra. Tránh giao nhiệm vụ chung cho “QA team” mà không có owner cụ thể.

Ví dụ:

| Công việc | Responsible | Accountable / xác nhận | Phối hợp |
|---|---|---|---|
| Làm rõ tiêu chí nghiệp vụ | QA/analyst | Product owner | Developer |
| Phân tích rủi ro kỹ thuật | QA/tech lead | Tech lead | Security, operations |
| Cấp phát môi trường | DevOps/SRE | Environment owner | QA, developer |
| Chuẩn bị fixture | QA/developer | Test lead | Data owner |
| Thực thi và triage | QA/test engineer | Test lead | Developer, service owner |
| Xử lý lỗi | Developer | Tech lead | QA |
| Chấp nhận rủi ro release | Release owner | Người có thẩm quyền | Product, security, operations |

Ma trận này chỉ là ví dụ; tổ chức cần xác định vai trò thật và quyền quyết định tương ứng.

### 9.2. Xác định phụ thuộc và đường găng

Một số công việc không thể bắt đầu trước khi đầu ra khác hoàn tất. Ví dụ, test E2E cần môi trường, tài khoản, dữ liệu và API đã sẵn sàng. Nếu quyền sandbox là phụ thuộc lâu nhất, nó có thể nằm trên đường găng dù công sức trực tiếp thấp.

Ghi:

- Công việc tiền nhiệm.
- Người hoặc nhóm cung cấp đầu vào.
- Ngày cần có đầu ra.
- Thời gian chờ dự kiến.
- Phương án thay thế nếu trễ.
- Tác động đến mốc tổng thể.

Có thể chạy song song các công việc độc lập như review yêu cầu, chuẩn bị test data và viết test ở tầng unit. Nhưng không nên giả định có thể chạy song song nếu chúng cùng sửa dữ liệu hoặc môi trường dùng chung.

### 9.3. Cân bằng tải và tránh phân bổ quá mức

Một người có thể được giao nhiều work package nhưng không thể thực hiện tất cả cùng lúc. Khi lập lịch, cần xem:

- Năng lực thực tế sau khi trừ họp, hỗ trợ và công việc vận hành.
- Thời gian nghỉ và lịch vắng mặt.
- Số nhiệm vụ cần chuyên môn hiếm.
- Công việc đang chạy song song.
- Thời gian chờ review hoặc phê duyệt.
- Khả năng chuyển giao khi người phụ trách vắng mặt.

Không lập kế hoạch với giả định 100% thời gian của mọi người đều dành cho một dự án.

## 10. Ví dụ: phân rã nguồn lực cho một thay đổi checkout

Giả sử nhóm thêm phương thức thanh toán mới và cần kiểm tra tính đúng đắn của giao dịch, callback, UI và khả năng phục hồi.

### 10.1. Work breakdown theo bốn giai đoạn

| Giai đoạn | Hoạt động | Đầu ra | Nguồn lực chính |
|---|---|---|---|
| Phân tích | Làm rõ luồng, hợp đồng và trạng thái giao dịch. | Sequence flow và tiêu chí chấp nhận. | Product, QA, developer. |
| Phân tích | Đánh giá rủi ro tiền, quyền, callback trùng và timeout. | Risk register và test scope. | QA, tech lead, security. |
| Phân tích | Chọn unit, API, integration và E2E test. | Test design và ước lượng. | QA, developer. |
| Chuẩn bị | Cấp phát môi trường và payment sandbox. | Environment sẵn sàng. | DevOps/SRE, service owner. |
| Chuẩn bị | Tạo tài khoản, đơn hàng và fixture. | Dữ liệu test có namespace. | QA, developer. |
| Chuẩn bị | Cấu hình secret, callback URL và log/trace. | Credential và observability sẵn sàng. | DevOps, security, QA. |
| Thực thi | Chạy unit, API, contract và integration test. | Kết quả theo từng tầng. | Developer, QA. |
| Thực thi | Chạy UI/E2E cho hành trình đại diện. | Bằng chứng người dùng. | QA automation. |
| Thực thi | Triage timeout, callback lặp và trạng thái sai. | Bug và phân tích nguyên nhân. | QA, developer, payment owner. |
| Thực thi | Retest và regression. | Xác nhận sửa lỗi. | QA, developer. |
| Bảo trì | Bổ sung regression cho lỗi đã sửa. | Test được duy trì. | QA, developer. |
| Bảo trì | Cập nhật fixture và sandbox credential. | Setup hiện hành. | QA, DevOps. |
| Bảo trì | Cập nhật runbook và cảnh báo. | Tài liệu vận hành. | Operations, service owner. |

### 10.2. Ước lượng minh họa

Giả sử nhóm ước lượng công sức ban đầu như sau. Đây là số liệu giả định để minh họa cách phân rã, không phải định mức chung:

| Giai đoạn | Work package | Effort minh họa |
|---|---|---:|
| Phân tích | Yêu cầu, luồng và rủi ro | 2.5 ngày công |
| Phân tích | Test design và truy vết | 2 ngày công |
| Chuẩn bị | Môi trường, sandbox và quyền | 2 ngày công |
| Chuẩn bị | Fixture, tài khoản và automation setup | 1.5 ngày công |
| Thực thi | Chạy suite và thu bằng chứng | 2 ngày công |
| Thực thi | Triage, retest và regression | 3 ngày công |
| Bảo trì | Test, fixture và tài liệu | 1.5 ngày công |
| **Tổng** | | **14.5 ngày công** |

Elapsed time có thể dài hơn do chờ sandbox hoặc phê duyệt quyền. Nếu hai kỹ sư cùng làm các hoạt động độc lập, thời gian lịch có thể giảm, nhưng tổng effort không tự động giảm tương ứng. Cần kiểm tra phụ thuộc và năng lực thực tế trước khi rút ngắn mốc.

### 10.3. Điều chỉnh khi thiếu nguồn lực

Nếu không có chuyên gia security ngay trong sprint:

- Ưu tiên review luồng xác thực, phân quyền và callback có rủi ro cao.
- Xác định rõ phần đánh giá bảo mật chuyên sâu chưa thực hiện.
- Tìm người có thẩm quyền thay thế hoặc lịch review phù hợp.
- Không coi các test chức năng thông thường là bằng chứng thay thế cho đánh giá bảo mật.
- Ghi rủi ro còn lại và quyết định có cần trì hoãn phát hành hay không.

Nếu sandbox chưa được cấp:

- Tiếp tục unit và contract test có thể thực hiện độc lập.
- Chuẩn bị fixture và integration test cục bộ.
- Đánh dấu test với sandbox là BLOCKED.
- Không kết luận tích hợp nhà cung cấp đã được xác minh.
- Cập nhật lịch khi dependency sẵn sàng.

## 11. Theo dõi tiến độ và điều chỉnh nguồn lực

### 11.1. Theo dõi theo đầu ra, không chỉ phần trăm hoàn thành

Mỗi work package nên có:

- Owner.
- Estimate và actual effort.
- Ngày bắt đầu/kết thúc.
- Trạng thái.
- Dependency.
- Đầu ra và tiêu chí chấp nhận.
- Rủi ro hoặc blocker.

Một công việc “90% hoàn thành” không có nhiều ý nghĩa nếu đầu ra chưa thể sử dụng. Ví dụ, môi trường đã cấp phát nhưng readiness chưa đạt thì vẫn chưa sẵn sàng cho test.

### 11.2. Trạng thái công việc

Có thể dùng các trạng thái:

- NOT STARTED.
- IN PROGRESS.
- BLOCKED.
- READY FOR REVIEW.
- DONE.
- DEFERRED hoặc WAIVED nếu được chấp nhận theo quy trình.

BLOCKED cần có nguyên nhân, người cần hỗ trợ và thời điểm xem xét lại. DEFERRED không đồng nghĩa hoàn thành; nó thể hiện công việc được chuyển sang thời điểm khác cùng rủi ro tương ứng.

### 11.3. Điều chỉnh khi có thay đổi

Khi phạm vi, rủi ro hoặc mốc phát hành thay đổi, cần xem lại:

- Work package nào phát sinh hoặc không còn cần thiết?
- Effort và elapsed time thay đổi thế nào?
- Có kỹ năng hoặc quyền mới cần huy động không?
- Đường găng có thay đổi không?
- Test nào cần ưu tiên hoặc hoãn?
- Rủi ro nào tăng do giảm nguồn lực?
- Người có thẩm quyền đã đồng ý với trade-off chưa?

Không nên âm thầm giảm phạm vi kiểm thử để giữ nguyên ngày phát hành. Mọi điều chỉnh cần cho thấy bằng chứng nào bị giảm và hậu quả có thể xảy ra.

### 11.4. Quản lý công việc ngoài kế hoạch

Điều tra lỗi, môi trường hỏng và thay đổi yêu cầu có thể tạo công việc phát sinh. Hãy ghi lại để cải thiện ước lượng tương lai. Nếu một loại công việc phát sinh lặp lại, có thể cần đưa nó thành work package chuẩn hoặc cải thiện quy trình gốc.

## 12. Đo lường hiệu quả sử dụng nguồn lực

Có thể theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| Effort theo giai đoạn | Cho biết công sức phân bổ vào phân tích, chuẩn bị, thực thi và bảo trì. |
| Estimate variance | Chênh lệch giữa effort ước lượng và thực tế. |
| Elapsed time | Thời gian lịch từ yêu cầu đến đầu ra sẵn sàng. |
| Waiting time | Thời gian chờ quyền, môi trường, review hoặc dependency. |
| Rework effort | Công sức làm lại do yêu cầu thiếu rõ, dữ liệu sai hoặc môi trường không ổn định. |
| Blocked time | Thời gian công việc bị chặn và nguyên nhân. |
| Environment utilization | Mức sử dụng môi trường so với thời gian được cấp. |
| Test maintenance effort | Công sức duy trì test, fixture và pipeline. |
| Defect detection by phase | Giai đoạn phát hiện lỗi và mức độ ảnh hưởng. |
| Unplanned work ratio | Tỷ lệ công việc phát sinh ngoài kế hoạch. |

Không nên dùng chỉ số utilization để buộc mọi người đạt 100% bận rộn. Một phần năng lực dự phòng giúp xử lý lỗi bất ngờ, review và hỗ trợ liên nhóm. Mục tiêu là luồng công việc ổn định và bằng chứng chất lượng, không phải tối đa hóa số giờ được phân bổ.

## 13. Mẫu phân rã công việc và kế hoạch nguồn lực

~~~text
Tên sản phẩm / tính năng:
Mục tiêu kiểm thử:
Phiên bản / mốc phát hành:
Test lead / owner:

PHÂN TÍCH
- Yêu cầu cần làm rõ:
- Rủi ro và mức ưu tiên:
- Phạm vi / ngoài phạm vi:
- Tầng kiểm thử:
- Tiêu chí hoàn tất:
- Work package / owner / estimate:
- Dependency:

CHUẨN BỊ
- Môi trường / hạ tầng:
- Phiên bản artifact:
- Dữ liệu / fixture:
- Tài khoản / vai trò / quyền:
- Công cụ / license:
- Secret / sandbox:
- Readiness criteria:
- Work package / owner / estimate:

THỰC THI
- Suite / test scope:
- Lịch và mức song song:
- Bằng chứng cần lưu:
- Triage / retest:
- Tiêu chí pass/fail/blocked:
- Work package / owner / estimate:

BẢO TRÌ
- Test cần cập nhật:
- Flaky / nợ kiểm thử:
- Fixture / môi trường:
- Tài liệu / truy vết:
- Lịch rà soát:
- Work package / owner / estimate:

TỔNG HỢP NGUỒN LỰC
- Effort theo vai trò:
- Effort theo giai đoạn:
- Elapsed time:
- Năng lực / lịch sẵn có:
- Phụ thuộc và đường găng:
- Dự phòng và cơ sở:
- Chi phí hạ tầng / công cụ:
- Rủi ro còn lại:
- Quyết định / người phê duyệt:
~~~

### 13.1. Checklist review kế hoạch

- [ ] Công việc đã được chia theo bốn giai đoạn.
- [ ] Mỗi work package có đầu ra và owner.
- [ ] Effort được phân biệt với thời gian chờ và elapsed time.
- [ ] Nguồn lực được mô tả theo kỹ năng và quyền cần thiết.
- [ ] Môi trường, dữ liệu, công cụ và license đã được tính đến.
- [ ] Phụ thuộc và đường găng được nhận diện.
- [ ] Mức song song phù hợp với năng lực và môi trường.
- [ ] Có công sức cho triage, retest và điều tra lỗi.
- [ ] Có nguồn lực cho bảo trì test và môi trường.
- [ ] Dự phòng gắn với bất định cụ thể.
- [ ] Rủi ro do thiếu nguồn lực hoặc giảm phạm vi được ghi nhận.
- [ ] Có cơ chế cập nhật kế hoạch khi thay đổi.

## 14. Những sai lầm thường gặp

- **Chỉ ước lượng thời gian chạy test:** bỏ sót phân tích, setup, triage và bảo trì.
- **Đồng nhất effort với elapsed time:** không tính thời gian chờ phê duyệt và dependency.
- **Giao việc theo chức danh thay vì kỹ năng:** có thể thiếu chuyên môn cần thiết.
- **Giả định mọi người có 100% năng lực:** bỏ qua họp, hỗ trợ, nghỉ và công việc khác.
- **Không xác định owner:** đầu ra dễ bị bỏ quên giữa các nhóm.
- **Không tính môi trường và dữ liệu:** test bị block dù kịch bản đã sẵn sàng.
- **Bỏ qua cleanup:** tài nguyên và dữ liệu tạm tích lũy, gây chi phí và xung đột.
- **Không dự phòng triage:** một vài lỗi phức tạp có thể làm trễ toàn bộ kế hoạch.
- **Dùng dự phòng tùy tiện:** không biết nguồn bất định nào đang được bao phủ.
- **Tối đa hóa utilization:** không còn khả năng phản ứng với công việc phát sinh.
- **Giảm test mà không ghi rủi ro:** quyết định phát hành mất minh bạch.
- **Coi bảo trì là việc phụ:** bộ test dần mất độ tin cậy và tăng chi phí.

## Kết luận

Phân rã công việc theo phân tích, chuẩn bị, thực thi và bảo trì giúp nhóm nhìn thấy đầy đủ hoạt động cần thiết để tạo và duy trì bằng chứng kiểm thử. Mỗi giai đoạn cần đầu ra, người chịu trách nhiệm, kỹ năng, môi trường, dữ liệu, công cụ và ước lượng riêng. Khi phân biệt effort với thời gian chờ, xác định phụ thuộc, dành công sức cho triage và bảo trì, đồng thời điều chỉnh nguồn lực theo rủi ro, kế hoạch kiểm thử sẽ thực tế hơn và giúp nhóm đưa ra quyết định chất lượng có cơ sở.
