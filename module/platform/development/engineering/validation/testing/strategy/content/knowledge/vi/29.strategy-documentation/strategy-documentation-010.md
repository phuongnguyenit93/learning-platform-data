# Đánh giá tính nhất quán và khả năng thực hiện của tài liệu

Trong chiến lược kiểm thử xác thực (VALIDATION_TESTING_STRATEGY), tài liệu chỉ hữu ích khi các phần mô tả cùng một mục tiêu, không mâu thuẫn về phạm vi và có thể chuyển thành công việc thực tế. Một chiến lược có thể trình bày đầy đủ các tầng kiểm thử nhưng vẫn không khả thi nếu lịch chạy vượt năng lực nhóm, môi trường chưa được cấp, dữ liệu không thể chuẩn bị hoặc không có người chịu trách nhiệm cho các hoạt động quan trọng.

Đánh giá tài liệu cần xem xét đồng thời hai khía cạnh. **Tính nhất quán** xác minh mục tiêu, phạm vi, thuật ngữ, vai trò, tiêu chí và kế hoạch có khớp nhau giữa các phần và giữa các tài liệu liên quan hay không. **Khả năng thực hiện** xác minh nhóm có đủ thời gian, kỹ năng, công cụ, dữ liệu, môi trường, quyền và sự phối hợp để thực hiện những gì tài liệu cam kết hay không.

Bài học này hướng dẫn cách xác định bộ tài liệu cần review, kiểm tra truy vết và mâu thuẫn, đánh giá tính khả thi theo nguồn lực và phụ thuộc, phân loại phát hiện, tổ chức review có bằng chứng và quản lý cập nhật để tài liệu luôn phản ánh cách kiểm thử thực tế.

## 1. Mục tiêu của việc đánh giá tài liệu chiến lược

### 1.1. Tài liệu cần thống nhất từ mục tiêu đến thực thi

Một bộ tài liệu kiểm thử thường gồm chiến lược, kế hoạch kiểm thử, risk register, ma trận truy vết, test design, lịch hồi quy, kế hoạch môi trường, danh sách nguồn lực, tiêu chí hoàn tất, báo cáo và runbook. Mỗi tài liệu có mục đích riêng nhưng phải mô tả cùng một hệ thống và cùng một phiên bản quyết định.

Ví dụ, chiến lược quy định kiểm tra phân quyền ở API và UI, nhưng test plan chỉ liệt kê kiểm tra đăng nhập thành công. Đây là khoảng trống giữa cam kết và kế hoạch thực thi. Nếu test plan có kiểm tra quyền nhưng không có tài khoản với các vai trò khác nhau, kế hoạch có thể nhất quán về nội dung nhưng chưa khả thi.

### 1.2. Tính nhất quán và khả năng thực hiện là hai câu hỏi riêng

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ vấn đề |
|---|---|---|
| Tính nhất quán | Các phần có cùng định nghĩa, phạm vi và tiêu chí không? | Chiến lược yêu cầu full regression trước release nhưng lịch phát hành không có thời gian cho suite đó. |
| Khả năng thực hiện | Nhóm có thể thực hiện điều đã cam kết với điều kiện hiện có không? | Kế hoạch yêu cầu kiểm thử trên thiết bị thật nhưng chưa có thiết bị hoặc quyền truy cập. |
| Tính đầy đủ | Có thiếu thành phần cần thiết để đạt mục tiêu không? | Có test API nhưng không có cách kiểm tra callback bất đồng bộ. |
| Khả năng truy vết | Có thể lần từ mục tiêu/rủi ro đến test và bằng chứng không? | Một rủi ro thanh toán không liên kết với test case hoặc tiêu chí phát hành. |
| Khả năng duy trì | Tài liệu có thể cập nhật khi hệ thống thay đổi không? | Không có owner hoặc ngày review, ma trận browser đã lỗi thời. |

Một tài liệu có thể nhất quán nhưng không khả thi; cũng có thể khả thi về nguồn lực nhưng không nhất quán với mục tiêu. Cần đánh giá cả hai trước khi phê duyệt.

### 1.3. Kết quả review phải hỗ trợ quyết định

Review không chỉ tìm lỗi biên tập. Kết quả cần giúp người chịu trách nhiệm quyết định:

- Có thể phê duyệt và sử dụng tài liệu không?
- Cần sửa nội dung nào trước khi bắt đầu?
- Có hoạt động nào phải đổi phạm vi hoặc lịch?
- Nguồn lực hay phụ thuộc nào cần được bổ sung?
- Rủi ro nào chưa được kiểm soát?
- Có điều kiện nào cần theo dõi hoặc chấp nhận ngoại lệ?

Một nhận xét như “kế hoạch chưa rõ” chưa đủ để hành động. Phát hiện nên chỉ ra vị trí, bằng chứng, tác động và đề xuất xử lý.

## 2. Xác định bộ tài liệu và nguồn chuẩn

### 2.1. Lập danh mục tài liệu cần đánh giá

Trước khi review, xác định tài liệu nào tạo nên quyết định kiểm thử cho phạm vi đang xét. Có thể gồm:

| Tài liệu | Nội dung cần đối chiếu |
|---|---|
| Test strategy | Mục tiêu, nguyên tắc, tầng kiểm thử, phạm vi và tiêu chuẩn chung. |
| Test plan | Phạm vi cụ thể, lịch, môi trường, nguồn lực và cách thực thi. |
| Requirements / acceptance criteria | Hành vi cần đạt và điều kiện chấp nhận. |
| Risk register | Rủi ro, mức ưu tiên, kiểm soát và owner. |
| Traceability matrix | Liên kết yêu cầu, rủi ro, test và kết quả. |
| Test design / test cases | Điều kiện, dữ liệu, bước và kết quả mong đợi. |
| Environment plan | Phiên bản, cấu hình, phụ thuộc, readiness và cleanup. |
| Test data plan | Nguồn dữ liệu, fixture, quyền, bảo vệ dữ liệu và dọn dẹp. |
| Resource plan | Vai trò, kỹ năng, effort, lịch và phụ thuộc. |
| Regression schedule | Suite, trigger, tần suất, ngưỡng và người xử lý kết quả. |
| Quality / release criteria | Gate, ngưỡng, trạng thái chưa đạt và thẩm quyền quyết định. |
| Operations / incident runbook | Giám sát, cảnh báo, rollback, phục hồi và hỗ trợ sau phát hành. |

Không phải dự án nào cũng cần mọi tài liệu độc lập. Có thể gộp chúng trong một tài liệu hoặc hệ thống quản lý, nhưng thông tin cần thiết vẫn phải tồn tại và có thể truy cập.

### 2.2. Xác định nguồn chuẩn cho từng loại thông tin

Khi hai tài liệu mâu thuẫn, reviewer cần biết nguồn nào có thẩm quyền. Ví dụ:

- Yêu cầu nghiệp vụ và acceptance criteria do product owner hoặc người được ủy quyền xác nhận.
- Kiến trúc và contract kỹ thuật do technical owner quản lý.
- Quy định bảo mật và quyền riêng tư do chính sách cùng owner chuyên môn xác định.
- Lịch phát hành do release owner quản lý.
- Quyền truy cập môi trường do environment owner hoặc operations quản lý.
- Tiêu chí chất lượng do các vai trò liên quan thống nhất và phê duyệt.

Không tự chọn tài liệu có ngày sửa mới nhất làm nguồn chuẩn nếu chưa biết ai có quyền quyết định. Nếu không xác định được nguồn chuẩn, ghi thành phát hiện cần làm rõ.

### 2.3. Kiểm soát phiên bản và trạng thái tài liệu

Mỗi tài liệu cần có thông tin tối thiểu:

- Tên và phạm vi áp dụng.
- Owner.
- Version hoặc revision.
- Trạng thái: draft, in review, approved, superseded.
- Ngày hiệu lực.
- Ngày review gần nhất hoặc kế tiếp.
- Liên kết đến tài liệu liên quan.

Review phải dùng các revision đã xác định. Nếu một tài liệu thay đổi trong lúc review, cần ghi lại revision được đánh giá hoặc chạy lại phần đối chiếu bị ảnh hưởng.

### 2.4. Xác định phạm vi review

Ghi rõ:

- Sản phẩm, module, service hoặc release.
- Môi trường và nền tảng liên quan.
- Các tài liệu nằm trong phạm vi.
- Những tài liệu hoặc chủ đề chưa có.
- Mốc thời gian mà quyết định áp dụng.
- Người tham gia và vai trò phê duyệt.

Phạm vi rõ giúp tránh kết luận toàn bộ chiến lược không nhất quán chỉ từ một phần tài liệu chưa hoàn thiện.

## 3. Đánh giá tính nhất quán giữa các tài liệu

### 3.1. Nhất quán về mục tiêu và phạm vi

Đối chiếu mục tiêu kiểm thử với phạm vi được mô tả ở các tài liệu. Kiểm tra:

- Tính năng và hành trình quan trọng có xuất hiện trong test plan không?
- Phần ngoài phạm vi có lý do và người chấp nhận không?
- Rủi ro cao có được phản ánh trong test design?
- Các service và dependency liên quan có được đưa vào phạm vi tích hợp?
- Môi trường hoặc nền tảng được hỗ trợ có khớp ma trận kiểm thử?
- Có tài liệu nào hứa kiểm tra một hành vi mà kế hoạch không có cách thực hiện?

Một phạm vi chỉ ghi tên module có thể chưa đủ. Cần xác định trạng thái, vai trò, dữ liệu và ranh giới hệ thống có liên quan.

### 3.2. Nhất quán về thuật ngữ và định nghĩa

Cùng một thuật ngữ phải có ý nghĩa tương thích giữa các tài liệu. Các từ dễ bị hiểu khác nhau gồm:

- Smoke test, sanity test và regression test.
- Integration test và system test.
- Critical path và critical defect.
- Ready, done, passed và approved.
- Environment available và environment ready.
- Defect, incident, failure và known issue.
- Waiver, exception và out of scope.

Ví dụ, nếu test strategy dùng “full regression” để chỉ toàn bộ test hồi quy bắt buộc, nhưng lịch chạy chỉ chạy smoke suite, cần sửa định nghĩa hoặc lịch. Glossary ngắn có thể giúp các nhóm dùng cùng một ngôn ngữ.

### 3.3. Nhất quán về tầng kiểm thử và mục tiêu bằng chứng

Mỗi mục tiêu cần được kiểm tra ở tầng phù hợp. Đối chiếu:

- Strategy có yêu cầu unit, API, integration, system hoặc E2E nào?
- Test plan có chỉ rõ suite và phạm vi tương ứng?
- Test case có xác minh đúng mục tiêu hay chỉ kiểm tra chi tiết giao diện?
- Mock hoặc stub có được ghi rõ và có kiểm tra dependency thật ở nơi cần thiết?
- Có rủi ro chỉ xuất hiện khi nhiều service phối hợp nhưng chỉ có unit test?
- Có test E2E trùng lặp mà không tạo thêm bằng chứng có giá trị?

Không cần tất cả test ở mọi tầng. Điều quan trọng là mỗi rủi ro quan trọng có một cách xác minh đủ mạnh và có thể truy vết.

### 3.4. Nhất quán về tiêu chí vào, ra và chất lượng

Đối chiếu các điều kiện như:

- Entry criteria trước khi bắt đầu test.
- Readiness của môi trường.
- Điều kiện pass/fail.
- Ngưỡng coverage hoặc hiệu năng.
- Số lượng và severity defect còn mở.
- Điều kiện kết thúc test.
- Gate trước release.
- Điều kiện rollback hoặc dừng rollout.

Ví dụ, test plan có thể cho phép bắt đầu system test khi tất cả service đã sẵn sàng, nhưng environment plan chỉ kiểm tra process đang chạy mà không xác minh database migration. Đây là mâu thuẫn giữa tiêu chí readiness và cách kiểm tra readiness.

### 3.5. Nhất quán về lịch và phạm vi chạy

Kiểm tra xem lịch chạy có thực hiện được cam kết trong strategy không:

- Bộ nhanh chạy khi nào?
- Integration suite chạy sau merge hay trước release?
- Full regression có chu kỳ và cửa sổ thời gian không?
- Ma trận browser/thiết bị được chia theo lịch nào?
- Test bị quarantine hoặc skip được theo dõi ra sao?
- Có đủ thời gian triage và retest trước quyết định không?

Nếu strategy yêu cầu full regression trước mỗi release nhưng release plan không dành thời gian hoặc môi trường, tài liệu đang không nhất quán và kế hoạch chưa khả thi.

### 3.6. Nhất quán về vai trò và quyền quyết định

Đối chiếu:

- Ai viết và duy trì test?
- Ai cấp phát và hỗ trợ môi trường?
- Ai xác nhận dữ liệu?
- Ai triage defect?
- Ai phê duyệt thay đổi phạm vi?
- Ai chấp nhận waiver hoặc rủi ro còn lại?
- Ai quyết định release?

Không để một tài liệu giao quyền phê duyệt cho QA lead trong khi chính sách quản trị yêu cầu risk owner hoặc security owner phê duyệt. Tên vai trò, quyền hạn và người thay thế cần thống nhất.

### 3.7. Nhất quán về dữ liệu, môi trường và bảo mật

Kiểm tra các cam kết liên quan:

- Dữ liệu được phép sử dụng.
- Cách ẩn danh hoặc tạo dữ liệu giả.
- Namespace và quyền truy cập.
- Secret, token và tài khoản thử nghiệm.
- Thời hạn lưu trữ log và artifact.
- Cleanup và thu hồi credential.
- Phân tách test, staging và production.
- Quyền truy cập của nhà cung cấp hoặc bên thứ ba.

Ví dụ, data plan yêu cầu dùng dữ liệu tổng hợp nhưng test plan lại hướng dẫn tải bản sao production chưa xử lý. Đây là mâu thuẫn cần giải quyết trước khi thực thi.

## 4. Đánh giá khả năng truy vết và độ bao phủ tài liệu

### 4.1. Truy vết từ mục tiêu đến bằng chứng

Một chuỗi truy vết hữu ích:

Mục tiêu → yêu cầu → rủi ro → tiêu chí hoàn tất → test design → test case/suite → kết quả → defect hoặc quyết định.

Mỗi liên kết cần có ID hoặc tham chiếu đủ rõ. Không nhất thiết phải dùng một công cụ cụ thể; có thể dùng bảng, issue tracker hoặc test management system.

### 4.2. Phát hiện mục tiêu không có test

Tìm các mục tiêu hoặc rủi ro không liên kết với test hoặc nguồn bằng chứng. Phân loại:

- Chưa có test nhưng có kế hoạch tạo.
- Có test nhưng chưa có dữ liệu hoặc môi trường.
- Có bằng chứng thay thế với giới hạn được ghi.
- Được xác nhận không áp dụng.
- Bị bỏ sót và cần bổ sung.

Không đánh dấu “đã bao phủ” chỉ vì tên rủi ro xuất hiện trong test plan. Cần có kiểm tra cụ thể và kết quả.

### 4.3. Phát hiện test không có mục tiêu rõ

Một test không liên kết với yêu cầu hoặc rủi ro có thể vẫn hữu ích, ví dụ test thăm dò hoặc kiểm tra bảo vệ kỹ thuật. Tuy nhiên, cần ghi mục tiêu của nó để biết vì sao duy trì.

Các câu hỏi:

- Test đang bảo vệ hành vi hoặc rủi ro nào?
- Có test khác cung cấp cùng bằng chứng không?
- Assertion có kiểm tra kết quả có ý nghĩa không?
- Test còn phù hợp với phiên bản hiện tại không?
- Nếu xóa test, khoảng trống nào xuất hiện?

### 4.4. Sử dụng ma trận truy vết

Ví dụ ma trận:

| Objective/Risk ID | Tiêu chí | Test ID | Tầng | Môi trường | Bằng chứng |
|---|---|---|---|---|---|
| OBJ-01: Tính đúng tổng tiền | Tổng tiền theo quy tắc giá và phí | PAY-UNIT-01 | Unit | CI | Kết quả test và coverage nhánh |
| RSK-02: Callback giả mạo | Chữ ký không hợp lệ bị từ chối | PAY-API-04 | API | Integration | Request/response đã lọc |
| RSK-03: Giao dịch trùng | Callback lặp không tạo giao dịch thứ hai | PAY-INT-08 | Integration | Payment sandbox | Trace và trạng thái giao dịch |
| OBJ-04: Hành trình checkout | Người dùng nhận kết quả chính xác | PAY-E2E-02 | E2E | Staging | Báo cáo E2E và screenshot |

Ma trận cần phản ánh trạng thái thực thi. Một test được thiết kế nhưng chưa chạy không phải bằng chứng hoàn tất.

## 5. Đánh giá tính khả thi về thời gian và lịch

### 5.1. Kiểm tra tổng thời lượng

Tổng thời gian cần tính cả:

- Phân tích và làm rõ yêu cầu.
- Thiết kế test và review.
- Cấp phát, cấu hình và readiness môi trường.
- Chuẩn bị dữ liệu và quyền.
- Thực thi suite.
- Triage và điều tra lỗi.
- Sửa lỗi, build lại và retest.
- Báo cáo và phê duyệt.
- Cleanup và bảo trì.

Nếu test suite chạy tự động trong 6 giờ nhưng cần thêm 2 ngày để cấp sandbox, 1 ngày để chuẩn bị dữ liệu và thời gian cho triage, không thể xem 6 giờ là toàn bộ thời lượng.

### 5.2. Phân biệt effort, elapsed time và thời gian chờ

- **Effort:** tổng công sức lao động.
- **Elapsed time:** thời gian lịch từ bắt đầu đến hoàn tất.
- **Waiting time:** thời gian chờ quyền, môi trường, review hoặc phụ thuộc.

Ba loại thời gian cần được ghi riêng để tránh ước lượng sai. Một hoạt động chỉ cần 2 giờ effort có thể nằm trên đường găng nếu phải chờ phê duyệt 3 ngày.

### 5.3. Xác minh lịch có đủ cửa sổ thực thi

Đối chiếu lịch kiểm thử với:

- Ngày đóng code hoặc freeze.
- Thời gian deploy vào môi trường.
- Cửa sổ bảo trì.
- Giờ hoạt động của nhóm hỗ trợ.
- Thời gian sandbox hoặc thiết bị sẵn sàng.
- Thời gian dành cho triage và retest.
- Thời hạn quyết định release.

Không lập lịch full regression vào thời điểm không còn thời gian xử lý failure trước release, trừ khi mục tiêu của lần chạy là cung cấp thông tin sau quyết định và điều đó đã được chấp nhận rõ.

### 5.4. Đánh giá khả năng song song

Chạy song song có thể rút ngắn lịch nhưng cần kiểm tra:

- Test có độc lập dữ liệu không?
- Có dùng chung tài khoản, queue hoặc tài nguyên không?
- Database và sandbox có đủ quota?
- Browser grid có đủ session?
- Runner có đủ CPU và memory?
- Báo cáo có tổng hợp kết quả chính xác?
- Cleanup có thể xóa dữ liệu của job khác không?

Nếu chưa chứng minh được tính cô lập, tăng số worker có thể làm test flaky thay vì nhanh hơn.

## 6. Đánh giá khả năng thực hiện về con người và kỹ năng

### 6.1. So khớp công việc với năng lực

Đối chiếu work package với kỹ năng cần có:

| Công việc | Năng lực cần thiết | Dấu hiệu thiếu khả thi |
|---|---|---|
| Phân tích rủi ro | Hiểu nghiệp vụ và kiến trúc | Không có người hiểu luồng hoặc dependency. |
| Test API/contract | HTTP, schema, auth và service contract | Không có quyền hoặc công cụ gọi API. |
| Test hiệu năng | Thiết kế tải và phân tích metrics | Không có người hiểu baseline và môi trường tải. |
| Security testing | Xác thực, phân quyền, threat model | Chỉ có test chức năng nhưng yêu cầu bảo mật cao. |
| Automation UI | Framework, selector và đồng bộ bất đồng bộ | Test phụ thuộc thao tác thủ công hoặc không có browser runner. |
| Điều tra production escape | Log, trace, dữ liệu và release history | Không có quyền truy cập bằng chứng hoặc owner hệ thống. |

### 6.2. Kiểm tra năng lực sẵn có

Không chỉ xem danh sách nhân sự. Cần xác minh:

- Người có kỹ năng có thời gian trong đúng giai đoạn không?
- Có phụ thuộc vào một cá nhân duy nhất không?
- Người review có đủ thời gian phản hồi?
- Có người thay thế khi vắng mặt?
- Có cần onboarding hoặc đào tạo trước khi thực thi?
- Có quyền truy cập và môi trường làm việc cần thiết?

Một kế hoạch phụ thuộc vào chuyên gia chỉ có thể tham gia sau ngày release là chưa khả thi, dù chuyên gia đó có tên trong danh sách nguồn lực.

### 6.3. Xem xét tải công việc và vai trò

Nếu một người vừa phát triển, vừa review, vừa chạy test và phê duyệt ngoại lệ, cần xem xét xung đột vai trò và quá tải. Với quyết định rủi ro cao, nên có review độc lập phù hợp.

Tài liệu cần ghi người thực hiện, người chịu trách nhiệm cuối cùng, người được tham vấn và người cần được thông báo. Tên nhóm chung chung không đủ để chứng minh nguồn lực đã được phân công.

## 7. Đánh giá môi trường, dữ liệu và công cụ

### 7.1. Môi trường có thực sự sẵn sàng?

Kiểm tra:

- Môi trường có tồn tại và được cấp đúng thời điểm?
- Artifact và dependency có đúng phiên bản?
- Database migration đã hoàn tất?
- Service và message consumer đã sẵn sàng?
- Network, DNS, TLS và quyền truy cập có hoạt động?
- Có thể quan sát log, metrics và trace?
- Có đủ quota cho test song song?
- Có cơ chế cleanup và khôi phục?

Một dòng “staging available” trong tài liệu không phải bằng chứng readiness. Cần owner, tiêu chí và cách xác minh.

### 7.2. Dữ liệu có thể chuẩn bị hợp lệ không?

Xem xét:

- Nguồn dữ liệu và quyền sử dụng.
- Dữ liệu tổng hợp hay đã xử lý nhạy cảm.
- Fixture có thể tái lập không?
- Có tài khoản cho mọi vai trò cần kiểm tra không?
- Có dữ liệu biên và trạng thái đặc biệt?
- Dữ liệu có được cô lập giữa các run?
- Cleanup và thời hạn lưu trữ có rõ?

Nếu test cần dữ liệu hiếm nhưng không có cách tạo hoặc phục hồi, phạm vi đó chưa thể thực hiện đáng tin cậy.

### 7.3. Công cụ và license

Xác minh:

- Tool có được cài đặt và cấu hình?
- License còn hiệu lực và đủ số lượng?
- Runner, browser hoặc thiết bị có sẵn?
- Quyền truy cập repository, pipeline và artifact đã được cấp?
- Công cụ có thể xuất bằng chứng theo định dạng cần thiết?
- Có owner bảo trì tool và tích hợp?

Kế hoạch không khả thi nếu yêu cầu chạy trên nhiều thiết bị nhưng chỉ có một thiết bị và không có lịch phân bổ.

### 7.4. Phụ thuộc bên ngoài

Với nhà cung cấp hoặc nhóm khác, ghi:

- Owner phía phụ thuộc.
- Interface hoặc hợp đồng cần dùng.
- Cửa sổ sẵn sàng.
- Quota, rate limit và giới hạn sandbox.
- Cách xử lý khi dependency gián đoạn.
- Phương án thay thế và giới hạn bằng chứng.

Một mock có thể cho phép tiếp tục kiểm tra logic nội bộ, nhưng không chứng minh tích hợp thật. Tài liệu phải thể hiện phần nào bị block và ai chịu trách nhiệm giải quyết.

## 8. Đánh giá tính khả thi của phạm vi và phương pháp kiểm thử

### 8.1. Phạm vi có tương xứng với mục tiêu không?

Hỏi:

- Có rủi ro quan trọng nào không có test?
- Có test quá rộng nhưng không xác minh tiêu chí rõ?
- Có test trùng lặp làm tiêu tốn thời gian?
- Có phần nào chỉ được kiểm tra bằng mock dù cần dependency thật?
- Có yêu cầu phi chức năng nhưng không có môi trường hoặc chỉ số?
- Có ma trận quá lớn so với thời gian và tài nguyên?

Nếu phạm vi vượt nguồn lực, cần ưu tiên theo rủi ro và ghi phần bị giảm. Không tự xóa test quan trọng để làm kế hoạch có vẻ khả thi.

### 8.2. Phương pháp có thể thực hiện được không?

Một phương pháp có thể hợp lý trên lý thuyết nhưng không phù hợp với hệ thống hiện tại. Ví dụ:

- Yêu cầu stress test nhưng không có môi trường cô lập đủ tải.
- Yêu cầu test concurrency nhưng fixture không hỗ trợ dữ liệu độc lập.
- Yêu cầu kiểm tra timezone nhưng clock không thể điều khiển.
- Yêu cầu test callback nhưng sandbox không hỗ trợ phát lại callback.
- Yêu cầu UI automation nhưng giao diện không có selector ổn định và môi trường browser không sẵn sàng.

Ghi rõ điều kiện kỹ thuật còn thiếu và phương án để đạt được chúng.

### 8.3. Mức tự động hóa có bền vững không?

Đánh giá:

- Test có ổn định và có mục tiêu rõ?
- Selector, fixture và helper có thể bảo trì?
- Pipeline có thời gian phù hợp?
- Có đủ kỹ năng phát triển và sửa automation?
- Kết quả có thể chẩn đoán?
- Có chi phí license, runner và browser grid?
- Test thủ công có cần giữ cho vùng chưa ổn định hoặc khám phá?

Không nên đặt mục tiêu tự động hóa 100% mà không xét giá trị, độ ổn định và chi phí sở hữu.

## 9. Phương pháp review có hệ thống

### 9.1. Review theo chiều ngang

Đọc một chủ đề qua tất cả tài liệu. Ví dụ, chọn chủ đề “quyền truy cập” rồi đối chiếu:

- Yêu cầu và policy.
- Risk register.
- Test strategy.
- Test plan.
- Test case.
- Data/account plan.
- Environment plan.
- Completion criteria.
- Release report.

Cách này dễ phát hiện cùng một khái niệm được mô tả khác nhau hoặc có tài liệu bỏ sót một phần.

### 9.2. Review theo chiều dọc

Đi theo một mục tiêu từ đầu đến cuối:

1. Mục tiêu nghiệp vụ.
2. Rủi ro nếu không đạt.
3. Tiêu chí chấp nhận.
4. Phương pháp và test design.
5. Dữ liệu, môi trường và người thực hiện.
6. Lịch chạy.
7. Bằng chứng và kết quả.
8. Gate và quyết định.

Nếu một mắt xích không có, đánh dấu khoảng trống. Ví dụ có risk nhưng không có test; có test nhưng không có dữ liệu; có kết quả nhưng không có tiêu chí để quyết định.

### 9.3. Walkthrough bằng tình huống thực tế

Chọn một kịch bản đại diện và yêu cầu nhóm mô tả cách thực hiện từ đầu đến cuối. Ví dụ:

- Một user không có quyền truy cập tài nguyên.
- Một giao dịch thanh toán bị timeout.
- Một migration cần rollback.
- Một service phụ thuộc không sẵn sàng.
- Một defect Critical được phát hiện trước release.

Walkthrough giúp kiểm tra tài liệu có đủ thông tin để người thực hiện làm việc hay cần hỏi thêm nhiều quyết định chưa được ghi.

### 9.4. Kiểm tra định lượng

Một số kiểm tra có thể đo:

- Tổng effort so với năng lực khả dụng.
- Thời lượng suite so với cửa sổ test.
- Số test bắt buộc chưa có owner.
- Số rủi ro chưa liên kết với test hoặc kiểm soát.
- Số test không có dữ liệu hoặc môi trường.
- Số phụ thuộc chưa có xác nhận.
- Số waiver chưa hết hạn hoặc thiếu owner.
- Số tài liệu quá hạn review.

Chỉ số định lượng giúp phát hiện điểm nghẽn nhưng không thay thế đánh giá chuyên môn. Ví dụ, một rủi ro có hậu quả rất lớn có thể cần xử lý ngay dù chỉ có một dòng trong danh sách.

### 9.5. Phỏng vấn và xác minh với owner

Hỏi người sở hữu từng phần:

- Ai sẽ thực hiện?
- Khi nào có thể thực hiện?
- Cần quyền hoặc đầu vào gì?
- Bằng chứng nào sẽ được lưu?
- Nếu phụ thuộc không sẵn sàng thì làm gì?
- Ai có quyền quyết định khi tiêu chí không đạt?

Sau đó đối chiếu câu trả lời với tài liệu. Nếu cách làm thực tế khác tài liệu, cần cập nhật một trong hai để loại bỏ khoảng cách.

## 10. Phân loại phát hiện và xác định hành động

### 10.1. Các loại phát hiện

| Loại | Mô tả | Ví dụ |
|---|---|---|
| Mâu thuẫn | Hai nguồn đưa ra chỉ dẫn không thể đồng thời đúng. | Strategy yêu cầu chạy full suite trước release, lịch lại không có lần chạy đó. |
| Thiếu thông tin | Thiếu dữ liệu cần thiết để thực thi hoặc quyết định. | Không có owner cho môi trường. |
| Không truy vết được | Không liên kết mục tiêu/rủi ro với test hoặc bằng chứng. | Rủi ro mất dữ liệu không có test migration. |
| Không khả thi | Nguồn lực, thời gian hoặc điều kiện không đáp ứng cam kết. | Cần 20 thiết bị nhưng chỉ có 2 thiết bị sẵn có. |
| Lỗi thời | Tài liệu không còn phản ánh hệ thống hiện tại. | Ma trận browser chứa phiên bản đã ngừng hỗ trợ. |
| Không rõ thẩm quyền | Không xác định ai phê duyệt hoặc chấp nhận rủi ro. | Waiver được ghi “QA approved” nhưng policy yêu cầu risk owner. |
| Rủi ro chưa xử lý | Có khoảng trống ảnh hưởng chất lượng hoặc nghĩa vụ. | Test bảo mật bị hoãn mà không có biện pháp thay thế. |

### 10.2. Phân mức độ phát hiện

Có thể dùng mức nghiêm trọng:

- **Critical:** có thể dẫn đến quyết định phát hành sai, vi phạm nghĩa vụ bắt buộc hoặc bỏ sót rủi ro nghiêm trọng; cần xử lý trước khi phê duyệt.
- **High:** ảnh hưởng lớn đến phạm vi, bằng chứng hoặc tính khả thi; cần có hành động và owner trước mốc liên quan.
- **Medium:** gây khó khăn hoặc khoảng trống có phạm vi giới hạn; cần kế hoạch khắc phục.
- **Low:** vấn đề biên tập, định dạng hoặc cải tiến nhỏ không làm thay đổi quyết định hiện tại.

Mức độ cần dựa trên hậu quả và thời điểm. Một lỗi chính tả trong tiêu đề thường thấp; một con số ngưỡng sai trong gate phát hành có thể rất cao.

### 10.3. Viết phát hiện có thể hành động

Mỗi phát hiện nên có:

- ID.
- Tài liệu và revision.
- Vị trí hoặc phần liên quan.
- Mô tả vấn đề.
- Bằng chứng hoặc ví dụ.
- Tác động đến mục tiêu, rủi ro hoặc lịch.
- Mức độ.
- Đề xuất xử lý.
- Owner.
- Due date.
- Trạng thái và bằng chứng đóng.

Ví dụ:

“F-07 — High: Test strategy yêu cầu xác minh callback lặp không tạo giao dịch trùng, nhưng test plan không có integration test cho callback lặp và payment sandbox chưa được cấp. Vì vậy, rủi ro giao dịch trùng chưa có bằng chứng. Owner: payment test lead. Hành động: bổ sung test, xác nhận sandbox và cập nhật lịch trước khi phê duyệt release.”

### 10.4. Phân biệt sửa tài liệu với sửa năng lực thực tế

Một số phát hiện có thể đóng bằng cách sửa tài liệu, nhưng nhiều vấn đề cần hành động thực tế:

- Thiếu môi trường: phải cấp phát hoặc điều chỉnh phạm vi.
- Thiếu kỹ năng: phải bố trí người, đào tạo hoặc review chuyên môn.
- Thiếu dữ liệu: phải tạo fixture hoặc được cấp nguồn dữ liệu hợp lệ.
- Lịch không khả thi: phải đổi lịch, nguồn lực hoặc phạm vi.
- Thiếu quyền: phải hoàn tất quy trình cấp quyền.
- Thiếu test: phải thiết kế và thực thi test.

Chỉ sửa câu chữ để tài liệu có vẻ nhất quán không giải quyết được một điều kiện thực thi đang thiếu.

## 11. Ví dụ tổng hợp: review tài liệu cho luồng thanh toán

Giả sử bộ tài liệu mô tả một thay đổi payment service. Mục tiêu là xử lý thanh toán đúng số tiền, xác minh callback và tránh giao dịch trùng.

### 11.1. Kết quả đối chiếu ban đầu

| Chủ đề | Strategy | Test plan / tài liệu khác | Nhận xét |
|---|---|---|---|
| Tính đúng số tiền | Unit và API test cho giá, thuế, phí. | Có test tổng tiền nhưng thiếu giá trị biên giảm giá. | Thiếu bao phủ một rủi ro. |
| Callback giả mạo | Yêu cầu xác minh chữ ký. | Có test chữ ký sai trên API. | Nhất quán, cần xác minh bằng chứng. |
| Callback lặp | Integration test bắt buộc. | Chỉ có mock callback, không có test với sandbox. | Khoảng trống bằng chứng tích hợp. |
| Môi trường | Payment sandbox cần sẵn sàng. | Environment plan chưa có owner hoặc ngày cấp. | Chưa khả thi về phụ thuộc. |
| Lịch | Full regression trước release. | Lịch không có cửa sổ cho full suite và retest. | Mâu thuẫn về lịch. |
| Trách nhiệm | Security review cho luồng callback. | Resource plan không có người review bảo mật. | Thiếu nguồn lực và owner. |
| Tiêu chí release | Không còn lỗi Critical/High chưa được chấp nhận đúng thẩm quyền. | Release checklist chỉ ghi “không còn bug”. | Định nghĩa không tương thích. |

### 11.2. Đánh giá khả năng thực hiện

Nhóm xác minh:

- Payment sandbox có được cấp trước ngày test không?
- Có tài khoản và secret riêng cho test run không?
- Có thể gửi callback lặp và callback sai chữ ký không?
- Log/trace có đủ để xác định transaction ID?
- Có người có chuyên môn review bảo mật không?
- Lịch còn thời gian cho full regression, triage và retest không?

Nếu câu trả lời là không, cần thay đổi kế hoạch hoặc điều kiện phê duyệt. Không thể coi các mục này đã sẵn sàng chỉ vì tài liệu ghi “sẽ kiểm tra”.

### 11.3. Kế hoạch xử lý phát hiện

1. Bổ sung test biên giảm giá và xác định dữ liệu.
2. Xác nhận sandbox, owner, credential và ngày sẵn sàng.
3. Bổ sung integration test callback lặp với dependency phù hợp.
4. Bố trí security reviewer và xác định thời gian review.
5. Cập nhật lịch full regression, triage và retest.
6. Đồng bộ release criteria với severity và quy trình waiver.
7. Chạy walkthrough lại để xác nhận toàn bộ luồng có thể thực hiện.

### 11.4. Điều kiện kết luận review

Tài liệu có thể được đề xuất phê duyệt khi:

- Mục tiêu và rủi ro có liên kết đến tiêu chí và test.
- Các mâu thuẫn quan trọng đã được giải quyết.
- Môi trường, dữ liệu và phụ thuộc có owner cùng thời điểm sẵn sàng.
- Nguồn lực và kỹ năng phù hợp đã được xác nhận.
- Lịch có thời gian thực thi và xử lý kết quả.
- Gate và quyền phê duyệt được định nghĩa rõ.
- Khoảng trống còn lại có mức độ, owner và quyết định phù hợp.

## 12. Quản lý thay đổi sau review

### 12.1. Thiết lập baseline đã được phê duyệt

Sau review, lưu revision được phê duyệt và trạng thái. Các thay đổi sau đó cần được phân loại theo mức ảnh hưởng. Sửa lỗi chính tả có thể không cần review lại toàn bộ; thay đổi phạm vi, gate hoặc nguồn lực có thể cần đánh giá tác động.

### 12.2. Xác định trigger review lại

Nên review lại khi:

- Yêu cầu hoặc acceptance criteria thay đổi.
- Kiến trúc hoặc dependency thay đổi.
- Phạm vi sản phẩm hoặc nền tảng hỗ trợ thay đổi.
- Lịch phát hành hoặc nguồn lực thay đổi đáng kể.
- Có production escape hoặc incident nghiêm trọng.
- Môi trường, dữ liệu hoặc công cụ thay đổi.
- Chính sách bảo mật hoặc tuân thủ thay đổi.
- Waiver hết hạn hoặc rủi ro tăng.

Không cần đợi đến kỳ review định kỳ nếu có thay đổi làm tài liệu hiện tại không còn đúng.

### 12.3. Giữ lịch sử và truy vết

Mỗi thay đổi quan trọng nên ghi:

- Nội dung trước và sau.
- Lý do.
- Người đề xuất và phê duyệt.
- Tác động đến test, lịch, nguồn lực và rủi ro.
- Ngày hiệu lực.
- Kết quả xác minh sau thay đổi.

Lịch sử giúp hiểu tại sao một quyết định được đưa ra và liệu giả định ban đầu còn đúng không.

### 12.4. Rà soát định kỳ

Ngay cả khi không có thay đổi lớn, cần xem lại tài liệu theo chu kỳ phù hợp. Review định kỳ có thể phát hiện:

- Link hỏng hoặc owner đã thay đổi.
- Công cụ và phiên bản đã lỗi thời.
- Test suite không còn chạy.
- Môi trường không còn được hỗ trợ.
- Waiver hết hạn.
- Lịch chạy không còn phù hợp với tốc độ phát triển.
- Tài liệu không còn phản ánh quy trình thực tế.

Tần suất review phụ thuộc mức độ biến động và rủi ro. Tài liệu release hoặc môi trường thay đổi thường xuyên có thể cần rà soát theo từng release; nguyên tắc chung có thể review theo quý hoặc theo chu kỳ quản trị của tổ chức.

## 13. Tổ chức buổi review và theo dõi hành động

### 13.1. Thành phần tham gia

Tùy phạm vi, có thể gồm:

- QA/test lead.
- Product owner hoặc business analyst.
- Engineering lead/architect.
- Developer hoặc service owner.
- DevOps/SRE hoặc environment owner.
- Security/privacy/compliance.
- Data owner.
- Release manager.

Mời đúng người có hiểu biết và quyền quyết định. Không cần tất cả vai trò tham dự mọi buổi review, nhưng các rủi ro chuyên môn phải được đánh giá bởi người phù hợp.

### 13.2. Agenda tham khảo

1. Xác nhận mục tiêu, phạm vi và revision tài liệu.
2. Review mục tiêu, yêu cầu và rủi ro.
3. Đối chiếu chiến lược, kế hoạch, test và tiêu chí.
4. Walkthrough một hoặc nhiều tình huống thực tế.
5. Xác minh thời gian, kỹ năng, môi trường, dữ liệu và phụ thuộc.
6. Xem các mâu thuẫn, khoảng trống và waiver.
7. Phân mức phát hiện và giao owner.
8. Xác định điều kiện phê duyệt hoặc review lại.

### 13.3. Theo dõi đến khi đóng

Mỗi phát hiện cần trạng thái và bằng chứng đóng. Ví dụ:

- OPEN.
- IN PROGRESS.
- BLOCKED.
- READY FOR REVIEW.
- CLOSED.
- ACCEPTED WITH RISK, nếu đúng thẩm quyền và có thời hạn.

Không đóng phát hiện chỉ vì đã sửa tài liệu. Reviewer cần xác minh thay đổi có giải quyết nguyên nhân và điều kiện thực thi hay không.

## 14. Mẫu checklist và báo cáo review

### 14.1. Mẫu danh mục tài liệu

~~~text
Tên tài liệu:
Mục đích:
Phạm vi:
Owner:
Revision:
Trạng thái:
Ngày hiệu lực:
Ngày review gần nhất:
Ngày review kế tiếp:
Nguồn chuẩn / tài liệu liên quan:
~~~

### 14.2. Mẫu ghi nhận phát hiện

~~~text
Finding ID:
Loại phát hiện:
Mức độ:
Tài liệu / revision / vị trí:

Mô tả:
Bằng chứng:
Mục tiêu hoặc rủi ro bị ảnh hưởng:
Tác động đến phạm vi / lịch / nguồn lực:
Đề xuất xử lý:
Owner:
Due date:
Trạng thái:
Bằng chứng đóng:
Reviewer xác nhận:
~~~

### 14.3. Mẫu kết luận review

~~~text
Sản phẩm / module / release:
Phạm vi review:
Tài liệu và revision đã xem:
Người tham gia:
Ngày review:

Kết quả nhất quán:
- Mục tiêu và phạm vi:
- Thuật ngữ và định nghĩa:
- Tầng kiểm thử và bằng chứng:
- Tiêu chí và gate:
- Vai trò và quyền:
- Dữ liệu và môi trường:
- Lịch và nguồn lực:

Kết quả khả thi:
- Thời gian và capacity:
- Kỹ năng và owner:
- Môi trường / công cụ / license:
- Dữ liệu và quyền truy cập:
- Dependency và phương án dự phòng:

Critical findings:
High findings:
Medium / Low findings:
Waiver / rủi ro được chấp nhận:
Điều kiện trước khi phê duyệt:
Quyết định: APPROVED / APPROVED WITH ACTIONS / NOT APPROVED
Người phê duyệt:
Ngày review lại:
~~~

### 14.4. Checklist trước khi phê duyệt tài liệu

- [ ] Tài liệu có owner, revision, phạm vi và trạng thái rõ.
- [ ] Nguồn chuẩn cho yêu cầu, policy và quyết định đã được xác định.
- [ ] Mục tiêu, phạm vi và rủi ro nhất quán giữa các tài liệu.
- [ ] Thuật ngữ, định nghĩa và trạng thái được dùng thống nhất.
- [ ] Rủi ro quan trọng truy vết đến tiêu chí, test và bằng chứng.
- [ ] Test plan thực hiện được các cam kết trong strategy.
- [ ] Entry/exit criteria, gate và waiver được định nghĩa.
- [ ] Lịch có đủ thời gian cho setup, execution, triage và retest.
- [ ] Nguồn lực, kỹ năng và quyền được xác nhận.
- [ ] Môi trường, dữ liệu, công cụ và dependency có owner.
- [ ] Giới hạn và bằng chứng thay thế được ghi rõ.
- [ ] Các phát hiện có severity, owner, due date và trạng thái.
- [ ] Thay đổi sau review có baseline và lịch sử.
- [ ] Có ngày hoặc trigger review lại.

## 15. Những sai lầm thường gặp

- **Chỉ đọc từng tài liệu riêng lẻ:** bỏ lỡ mâu thuẫn giữa các tài liệu.
- **Coi tài liệu mới nhất là nguồn chuẩn:** có thể bỏ qua quyền sở hữu và phê duyệt.
- **Review câu chữ mà không walkthrough:** tài liệu có thể đẹp nhưng không thực thi được.
- **Không kiểm tra nguồn lực thực tế:** tên người trong kế hoạch không chứng minh họ có thời gian hoặc kỹ năng.
- **Không xác minh môi trường và dữ liệu:** kế hoạch phụ thuộc vào tài nguyên chưa tồn tại.
- **Không kiểm tra truy vết:** rủi ro quan trọng không có test hoặc bằng chứng.
- **Coi mock là bằng chứng tích hợp thật:** bỏ qua giới hạn của dependency mô phỏng.
- **Không tính thời gian triage và retest:** lịch kết thúc ngay sau khi suite chạy.
- **Giao phát hiện cho một nhóm chung:** không có người chịu trách nhiệm.
- **Đóng phát hiện chỉ bằng sửa tài liệu:** nguyên nhân thực tế vẫn còn.
- **Không cập nhật baseline:** nhóm không biết revision nào được phê duyệt.
- **Không review lại sau incident hoặc thay đổi lớn:** tài liệu dần lệch khỏi sản phẩm.

## Kết luận

Đánh giá tài liệu chiến lược cần kiểm tra cả sự nhất quán giữa mục tiêu, rủi ro, phạm vi, test, tiêu chí, vai trò và lịch; đồng thời xác minh con người, kỹ năng, thời gian, môi trường, dữ liệu, công cụ và phụ thuộc có đủ để thực hiện hay không. Review theo chiều ngang, chiều dọc, walkthrough tình huống và kiểm tra nguồn lực giúp phát hiện mâu thuẫn cũng như khoảng trống thực tế. Khi mỗi phát hiện có bằng chứng, mức độ, owner và hành động đóng rõ ràng, tài liệu sẽ trở thành kế hoạch có thể thực hiện, theo dõi và cập nhật thay vì chỉ là cam kết trên giấy.
