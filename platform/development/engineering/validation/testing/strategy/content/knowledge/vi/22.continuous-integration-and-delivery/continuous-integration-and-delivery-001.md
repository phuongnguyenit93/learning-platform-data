# Phân bổ kiểm tra theo thời điểm commit, pull request, tích hợp và phát hành

Một pipeline CI/CD hiệu quả cần trả lời hai câu hỏi: thay đổi có đủ an toàn để đi tiếp không, và nhóm cần nhận bằng chứng nào ở từng thời điểm để đưa ra quyết định đó? Nếu chạy toàn bộ kiểm thử sau mỗi commit, phản hồi có thể quá chậm và tốn tài nguyên. Nếu chỉ chạy vài kiểm thử nhanh rồi chờ đến trước phát hành mới kiểm tra sâu, lỗi có thể đã lan rộng và khó xác định nguyên nhân.

Vì vậy, cần phân bổ hoạt động kiểm thử theo các điểm kiểm soát của vòng đời thay đổi: commit, pull request, tích hợp, tạo bản dựng phát hành và triển khai. Mỗi giai đoạn có mục tiêu, phạm vi, thời gian phản hồi và mức rủi ro khác nhau. Các kiểm tra nhanh giúp phát hiện lỗi gần thời điểm viết mã; các kiểm tra rộng hơn xác minh tương tác giữa thành phần và hành vi toàn hệ thống; các kiểm tra trước và sau phát hành cung cấp bằng chứng cho quyết định triển khai và vận hành.

## 1. Nguyên tắc phân bổ kiểm tra trong CI/CD

CI (Continuous Integration — tích hợp liên tục) đưa thay đổi mã vào nhánh chung thường xuyên, tự động xây dựng và kiểm tra để phát hiện xung đột hoặc sai lệch sớm. CD có thể chỉ việc phân phối liên tục (Continuous Delivery) hoặc triển khai liên tục (Continuous Deployment), tùy quy trình tổ chức. Dù dùng cách nào, kiểm thử cần được gắn với quyết định chuyển thay đổi qua từng giai đoạn.

Các nguyên tắc quan trọng:

- **Phản hồi sớm:** chạy kiểm tra nhanh ngay sau khi thay đổi được tạo để người viết có thể sửa khi ngữ cảnh còn rõ.
- **Phạm vi tăng theo rủi ro:** càng gần tích hợp và phát hành, càng cần thêm bằng chứng về tương tác, hành trình và thuộc tính chất lượng.
- **Đúng kiểm tra ở đúng thời điểm:** không phải mọi kiểm tra đều cần chạy ở mọi commit; chọn theo chi phí, tốc độ và hậu quả nếu lỗi lọt qua.
- **Tự động hóa quyết định lặp lại:** build, test, scan, đóng gói và triển khai cần có kết quả có thể truy vết.
- **Cổng chất lượng minh bạch:** quy định điều kiện đạt, thất bại, cảnh báo và ngoại lệ trước khi pipeline chạy.
- **Kết quả có thể chẩn đoán:** lưu log, báo cáo, artifact và thông tin phiên bản để người xử lý biết lỗi xảy ra ở đâu.
- **Bảo vệ môi trường và dữ liệu:** kiểm thử không được tạo tác động ngoài ý muốn lên dịch vụ, tài khoản hoặc dữ liệu thật.
- **Cải tiến dựa trên số liệu:** theo dõi thời gian phản hồi, độ ổn định, lỗi lọt và chi phí để điều chỉnh phân bổ.

Không có một sơ đồ pipeline duy nhất phù hợp cho mọi sản phẩm. Dịch vụ backend, ứng dụng di động, hệ thống dữ liệu và nền tảng có nhiều tích hợp sẽ cần các tập kiểm tra khác nhau. Khung phân bổ phải xuất phát từ kiến trúc, rủi ro và mục tiêu phát hành.

## 2. Bốn thời điểm kiểm tra chính

| Thời điểm | Mục tiêu chính | Loại kiểm tra tiêu biểu | Quyết định |
|---|---|---|---|
| Commit | Phản hồi nhanh về thay đổi nhỏ | Format/lint, static analysis, unit test, kiểm tra cấu hình và secret cơ bản | Thay đổi có đủ điều kiện để tiếp tục review không? |
| Pull request (PR) | Đánh giá thay đổi trong ngữ cảnh tích hợp vào nhánh chung | Unit/component mở rộng, contract test, API test, kiểm tra bảo mật và review | Có thể merge thay đổi không? |
| Tích hợp | Xác minh các thành phần và bản dựng hoạt động cùng nhau | Integration test, system test, migration, message/event, một số E2E và kiểm tra phi chức năng phù hợp | Bản dựng tích hợp có đủ tin cậy để tạo ứng viên phát hành không? |
| Phát hành | Xác minh ứng viên phát hành và điều kiện triển khai | Regression chọn lọc, E2E quan trọng, kiểm tra bảo mật/hiệu năng, cấu hình, smoke test sau triển khai | Có thể triển khai hoặc tiếp tục mở rộng phát hành không? |

Các giai đoạn này có thể ánh xạ vào nhiều pipeline hoặc một pipeline nhiều stage. Một nhóm nhỏ có thể gộp PR và tích hợp; hệ thống lớn có thể tách chúng thành nhiều workflow. Điều quan trọng là mục tiêu và tiêu chí của từng điểm kiểm soát phải rõ.

## 3. Kiểm tra tại thời điểm commit

Commit là thời điểm thích hợp để chạy những kiểm tra có thời gian phản hồi ngắn, ít phụ thuộc môi trường và giúp người viết sửa lỗi ngay.

### 3.1. Mục tiêu

- Ngăn lỗi cú pháp, định dạng và cấu hình cơ bản đi xa hơn.
- Xác minh logic nhỏ vừa thay đổi.
- Phát hiện lỗi biên dịch, kiểu dữ liệu hoặc dependency.
- Phát hiện một số vấn đề bảo mật rõ ràng như secret vô tình được thêm vào mã nguồn.
- Giữ chất lượng mã và quy ước dự án nhất quán.

### 3.2. Kiểm tra phù hợp

- Format, lint và kiểm tra quy ước mã.
- Biên dịch hoặc build module bị ảnh hưởng.
- Unit test cho logic thay đổi và các thành phần liên quan.
- Static analysis và kiểm tra kiểu dữ liệu.
- Kiểm tra dependency hoặc secret ở mức nhanh.
- Kiểm tra tính hợp lệ của file cấu hình, schema hoặc migration.

Không nên đưa một bộ E2E dài, phụ thuộc nhiều dịch vụ vào mọi lần commit nếu thời gian chạy làm gián đoạn vòng lặp phát triển. Tuy nhiên, với mã có rủi ro cao như xác thực, mã hóa, tính tiền hoặc kiểm soát quyền, có thể cần thêm một số kiểm tra chuyên biệt ngay ở bước này.

### 3.3. Cách tổ chức

Có thể chạy kiểm tra trước khi push bằng hook cục bộ, nhưng kết quả quyết định cần được xác minh lại trên CI vì môi trường máy cá nhân khác nhau. CI nên chạy tập kiểm tra nhanh trên commit hoặc nhánh cập nhật, dùng cache và build incremental khi phù hợp.

Nếu một kiểm thử thất bại, báo cáo nên chỉ ra tên test, dòng lỗi, log và commit liên quan. Người viết cần biết lỗi thuộc mã nguồn, cấu hình, môi trường hay test không ổn định.

### 3.4. Cổng chất lượng ở commit

Điều kiện tối thiểu thường gồm:

- Build/compile thành công đối với phạm vi cần kiểm tra.
- Lint hoặc quy tắc bắt buộc đạt.
- Unit test trọng yếu đạt.
- Không phát hiện secret hoặc lỗi static analysis nghiêm trọng theo chính sách.
- Artifact và kết quả được gắn với commit cụ thể.

Có thể cho phép cảnh báo không chặn đối với một số rule có độ tin cậy thấp, nhưng cần người sở hữu và thời hạn xử lý. Không nên biến cảnh báo thành trạng thái xanh vĩnh viễn mà không có rà soát.

## 4. Kiểm tra tại thời điểm pull request

PR là điểm kiểm soát quan trọng trước khi hợp nhất thay đổi vào nhánh chung. Ở đây, nhóm cần đánh giá không chỉ mã mới mà cả tác động của nó lên hợp đồng và hành vi của thành phần liên quan.

### 4.1. Mục tiêu

- Xác minh thay đổi đáp ứng yêu cầu và tiêu chí chấp nhận.
- Phát hiện lỗi do tương tác với thành phần khác.
- Kiểm tra tính tương thích của API, schema và sự kiện.
- Xem xét rủi ro bảo mật, chất lượng mã và tác động dữ liệu.
- Bảo đảm thay đổi không phá vỡ hành vi đã có.

### 4.2. Kiểm tra phù hợp

- Toàn bộ unit test của module bị ảnh hưởng.
- Component test và kiểm thử API.
- Contract test giữa consumer và provider.
- Integration test có phụ thuộc nhẹ hoặc môi trường tạm thời.
- Kiểm tra migration, schema và tương thích ngược.
- Static analysis, SAST, dependency scan và kiểm tra license theo chính sách.
- Kiểm thử hồi quy chọn lọc theo vùng mã và rủi ro.
- Kiểm tra coverage hoặc mutation testing theo phạm vi khi phù hợp.

Không nên chỉ chạy test được sửa trong PR. Thay đổi một interface có thể ảnh hưởng đến nhiều consumer; thay đổi schema có thể ảnh hưởng đến dữ liệu cũ; thay đổi cấu hình có thể ảnh hưởng đến cả ứng dụng. Cần xác định phạm vi phụ thuộc để chọn test liên quan.

### 4.3. Review và bằng chứng

Tự động hóa không thay thế review của con người. PR nên có:

- Mô tả mục tiêu và phạm vi thay đổi.
- Liên kết yêu cầu, issue hoặc tiêu chí chấp nhận.
- Kết quả kiểm thử tự động và artifact.
- Giải thích migration hoặc thay đổi hợp đồng nếu có.
- Rủi ro còn lại và hướng kiểm soát.
- Phê duyệt của người có trách nhiệm theo chính sách nhánh.

Các kiểm tra bắt buộc có thể được cấu hình thành required status checks. PR chỉ được merge khi tất cả điều kiện bắt buộc đạt và review đã hoàn tất. Ngoại lệ cần có người phê duyệt, lý do và dấu vết.

### 4.4. Kiểm tra theo phạm vi thay đổi

Có thể dùng danh sách file, dependency graph, module hoặc tag để chạy test liên quan. Tuy nhiên, chọn test theo diff có nguy cơ bỏ sót ảnh hưởng gián tiếp. Cần có một tập kiểm tra nền chạy rộng hơn theo lịch hoặc sau khi merge để phát hiện những phụ thuộc chưa được nhận diện.

## 5. Kiểm tra tại thời điểm tích hợp

Sau khi thay đổi được hợp nhất hoặc một nhóm thành phần được ghép thành bản dựng, cần kiểm tra hành vi khi chúng hoạt động cùng nhau.

### 5.1. Mục tiêu

- Xác minh giao tiếp giữa dịch vụ, database, broker và hệ thống ngoài.
- Phát hiện lỗi cấu hình, thứ tự khởi động và phụ thuộc.
- Kiểm tra migration và tương thích dữ liệu.
- Xác minh trạng thái và sự kiện xuyên qua các ranh giới.
- Kiểm tra nhánh lỗi, retry, timeout và phục hồi.
- Đánh giá một số yêu cầu hệ thống và phi chức năng trong môi trường đại diện.

### 5.2. Kiểm tra phù hợp

- Integration test với database, broker hoặc dịch vụ nội bộ thật trong môi trường kiểm soát.
- Contract verification ở provider và consumer.
- System test cho các yêu cầu quan trọng.
- E2E cho hành trình nghiệp vụ có giá trị cao.
- Kiểm tra migration từ phiên bản dữ liệu trước.
- Kiểm thử xử lý bất đồng bộ, callback, retry và idempotency.
- Smoke test trên bản dựng tích hợp.
- Kiểm tra hiệu năng hoặc tải ở quy mô phù hợp nếu bản dựng cần đánh giá năng lực.

### 5.3. Môi trường tích hợp

Môi trường cần có phiên bản và cấu hình được quản lý. Nếu dùng service virtualization hoặc stub cho phụ thuộc bên ngoài, ghi rõ giới hạn và bổ sung kiểm thử sandbox hoặc môi trường gần production khi rủi ro yêu cầu.

Nên dùng dữ liệu có thể tái lập, tài khoản thử nghiệm và namespace riêng. Mỗi lần chạy cần có run ID để truy vết log, metric, trace và trạng thái dữ liệu. Các job tích hợp không nên ghi đè dữ liệu của nhau.

### 5.4. Tích hợp liên tục và chất lượng bản dựng

Khi có commit mới vào nhánh tích hợp, CI nên tạo bản dựng bất biến, gắn mã phiên bản hoặc commit SHA và chạy tập kiểm tra phù hợp. Artifact đã kiểm thử cần là artifact được đưa sang bước phát hành; tránh build lại từ mã nguồn khác mà không xác minh tương đương.

Nếu integration test thất bại, cần phân biệt lỗi sản phẩm với lỗi môi trường, dữ liệu hoặc dịch vụ phụ thuộc. Không nên tự động bỏ qua test để pipeline tiếp tục xanh mà không ghi nhận quyết định.

## 6. Kiểm tra tại thời điểm phát hành

Trước khi triển khai, nhóm cần đánh giá ứng viên phát hành (release candidate) trên một tập bằng chứng đã xác định. Mức kiểm tra phụ thuộc rủi ro thay đổi, mức ảnh hưởng và khả năng quay lui.

### 6.1. Mục tiêu

- Xác minh artifact cuối cùng đúng phiên bản và đã qua các cổng trước đó.
- Kiểm tra hồi quy các hành trình quan trọng.
- Xác minh cấu hình, secret, migration và khả năng tương thích triển khai.
- Đánh giá rủi ro bảo mật, hiệu năng, khả năng phục hồi và vận hành.
- Bảo đảm có kế hoạch rollback hoặc roll-forward và theo dõi sau triển khai.

### 6.2. Kiểm tra trước phát hành

- Regression suite ưu tiên cao.
- E2E cho hành trình có tác động lớn như đăng nhập, thanh toán, tạo đơn hoặc cập nhật dữ liệu.
- Kiểm tra API và hợp đồng với phiên bản phụ thuộc dự kiến.
- Kiểm tra migration, backward compatibility và khả năng khôi phục dữ liệu.
- Security scan và kiểm thử chuyên sâu theo mức rủi ro.
- Performance/load test khi thay đổi có thể ảnh hưởng năng lực.
- Kiểm tra cấu hình, feature flag, secret và quyền.
- Kiểm tra runbook, dashboard, alert và readiness của vận hành.

Không cần chạy mọi bài kiểm thử dài ở mọi bản phát hành nếu không có rủi ro tương ứng. Tuy nhiên, các kiểm tra bắt buộc theo chính sách, quy định hoặc mức độ nghiêm trọng không được bỏ qua chỉ vì thời gian.

### 6.3. Kiểm tra sau triển khai

Kiểm thử không kết thúc khi deployment hoàn tất. Cần xác minh ứng dụng đã sẵn sàng trong môi trường đích:

- Health check và readiness đạt.
- Smoke test cho các endpoint và hành trình quan trọng.
- Xác minh cấu hình, kết nối và migration.
- Theo dõi error rate, latency, saturation và log.
- Kiểm tra một giao dịch tổng hợp an toàn nếu phù hợp.
- Xác minh không có lỗi mới trong các luồng nghiệp vụ chính.

Với triển khai canary hoặc progressive delivery, mở rộng lưu lượng theo từng bước khi các chỉ số và smoke test đạt. Nếu vượt ngưỡng, dừng rollout hoặc quay lui theo chính sách đã định.

## 7. Ma trận phân bổ kiểm tra theo thời điểm

Ma trận dưới đây là khung tham khảo. Nhóm cần điều chỉnh theo kiến trúc, tốc độ pipeline và rủi ro.

| Loại kiểm tra | Commit | Pull request | Tích hợp | Phát hành |
|---|---|---|---|---|
| Format/lint | Mặc định | Có thể xác minh lại | Theo cấu hình | Không cần lặp nếu artifact đã xác minh |
| Compile/build | Phạm vi thay đổi | Build đầy đủ cần thiết | Build artifact tích hợp | Xác minh artifact bất biến |
| Unit test | Test nhanh/liên quan | Suite module hoặc toàn bộ phù hợp | Có thể chạy lại theo bản dựng | Không nhất thiết chạy lại toàn bộ |
| Component test | Chọn lọc | Có | Có | Theo rủi ro |
| API test | Một số test nhanh | Suite liên quan | Suite tích hợp | Smoke/regression chọn lọc |
| Contract test | Có thể chạy theo thay đổi hợp đồng | Ưu tiên | Provider verification | Xác minh tương thích phiên bản |
| Integration test | Chọn lọc nếu nhanh | Một phần | Trọng tâm | Smoke hoặc tập rủi ro cao |
| System test | Hiếm khi chạy đầy đủ | Có thể chạy chọn lọc | Trọng tâm | Tập xác nhận release |
| E2E | Chỉ smoke rất nhanh nếu cần | Một số luồng quan trọng | Luồng nghiệp vụ đại diện | Regression hành trình ưu tiên cao |
| Security scan | Secret/static check nhanh | SAST/dependency scan | DAST hoặc kiểm tra môi trường phù hợp | Kiểm tra theo chính sách và rủi ro |
| Performance/load | Microbenchmark chọn lọc | Benchmark nếu thay đổi liên quan | Test tải ở môi trường phù hợp | Xác minh năng lực khi cần |
| Migration/data | Kiểm tra schema hoặc script | Kiểm tra tương thích | Chạy trên dữ liệu đại diện | Diễn tập, xác minh backup/rollback |
| Smoke/readiness | Không phải mục tiêu chính | Có thể chạy trên preview | Sau deploy vào môi trường tích hợp | Sau deploy ở môi trường đích |

Một loại kiểm tra có thể xuất hiện ở nhiều giai đoạn nhưng mục đích khác nhau. Ví dụ, API test ở PR có thể xác minh hành vi của module; API test ở tích hợp xác minh nhiều dịch vụ phối hợp; smoke API sau triển khai xác minh môi trường đích đang phục vụ.

## 8. Xây dựng cổng chất lượng (quality gates)

Quality gate là tập điều kiện cần đạt để thay đổi được chuyển sang giai đoạn tiếp theo. Cổng cần có ngưỡng, nguồn bằng chứng, người chịu trách nhiệm và quy trình xử lý ngoại lệ.

### 8.1. Cổng commit

Ví dụ điều kiện:

- Build hoặc compile thành công.
- Unit test trọng yếu đạt.
- Không có lỗi lint hoặc static analysis bị cấm.
- Không phát hiện secret theo chính sách.
- Báo cáo được lưu gắn với commit.

### 8.2. Cổng pull request

- Các kiểm tra bắt buộc đã hoàn tất và đạt.
- Contract/API test liên quan không có lỗi chưa xử lý.
- Không có lỗ hổng bảo mật vượt ngưỡng chấp nhận.
- Review và phê duyệt theo quy định nhánh đã hoàn tất.
- Migration và thay đổi schema có phương án tương thích.
- Rủi ro còn lại được ghi nhận và có người chấp nhận nếu cần.

### 8.3. Cổng tích hợp

- Artifact được tạo thành công và có định danh bất biến.
- Integration/system test ưu tiên cao đạt.
- Các phụ thuộc và môi trường ở trạng thái sẵn sàng.
- Không còn lỗi nghiêm trọng trong hành trình chính.
- Log, metric và trace đủ để điều tra.
- Migration và xử lý lỗi có bằng chứng.

### 8.4. Cổng phát hành

- Release candidate đã qua các kiểm tra bắt buộc.
- Artifact và cấu hình đúng phiên bản đã xác minh.
- Không còn lỗi nghiêm trọng chưa được xử lý hoặc chấp nhận.
- Kế hoạch triển khai, rollback/roll-forward và giám sát đã sẵn sàng.
- Smoke test sau triển khai đạt trước khi mở rộng rollout.
- Người có thẩm quyền đưa ra quyết định phát hành theo chính sách.

### 8.5. Quản lý ngoại lệ

Không phải mọi cảnh báo đều có thể chặn pipeline, nhưng ngoại lệ cần minh bạch. Một bản ghi ngoại lệ nên có:

- Kiểm tra hoặc rule bị bỏ qua.
- Lý do và phạm vi ảnh hưởng.
- Rủi ro và biện pháp bù đắp.
- Người phê duyệt.
- Thời hạn hết hiệu lực.
- Ticket hoặc hành động khắc phục.

Ngoại lệ không nên tồn tại vô thời hạn. Pipeline cần báo cáo rõ kiểm tra nào bị skip, vì sao và ai đã chấp nhận.

## 9. Tổ chức thời gian phản hồi và tài nguyên pipeline

Phân bổ kiểm tra cần cân bằng giữa độ bao phủ và thời gian phản hồi.

### 9.1. Chia tầng theo tốc độ

- **Nhanh:** lint, compile, unit test nhỏ, secret check.
- **Trung bình:** component, API, contract và integration test chọn lọc.
- **Rộng/chậm:** system, E2E, regression lớn, performance, security chuyên sâu.

Có thể chạy song song những kiểm tra độc lập, nhưng cần giới hạn tài nguyên và tránh các job tranh chấp dữ liệu hoặc môi trường. Một pipeline song song quá mức có thể chậm hơn do CPU, database, browser hoặc quota bị bão hòa.

### 9.2. Chạy theo thay đổi và chạy định kỳ

Một số kiểm tra có thể chạy theo diff hoặc dependency graph để phản hồi nhanh. Các suite rộng hơn nên chạy sau merge, theo lịch, ban đêm hoặc trước phát hành. Chọn cách nào cần dựa trên khả năng nhận diện tác động và hậu quả nếu bỏ sót.

Không nên chỉ chạy test theo file thay đổi khi có quan hệ gián tiếp. Thay đổi thư viện dùng chung, schema hoặc cấu hình có thể ảnh hưởng nhiều module không nằm trong diff trực tiếp.

### 9.3. Quản lý flaky test

Test không ổn định làm giảm niềm tin vào cổng chất lượng. Cần:

- Theo dõi tỷ lệ flaky theo test và môi trường.
- Lưu log, trace, screenshot hoặc dữ liệu tái hiện.
- Phân loại lỗi sản phẩm, test, dữ liệu và hạ tầng.
- Có owner và thời hạn sửa test flaky.
- Chỉ quarantine khi có lý do, thời hạn và kiểm tra bù đắp.
- Không biến retry thành cách che giấu lỗi.

Nếu một test bắt buộc đang bị quarantine, quality gate cần hiển thị rõ khoảng trống và rủi ro.

## 10. Ví dụ pipeline cho một dịch vụ Java

Giả sử nhóm phát triển dịch vụ đặt hàng bằng Java, dùng build tool, unit test, database quan hệ, message broker và một nhà cung cấp thanh toán. Có thể phân bổ kiểm tra như sau:

### 10.1. Commit

- Format/lint và compile module thay đổi.
- Unit test cho logic tính giá, quyền và trạng thái đơn.
- Static analysis và secret scan nhanh.
- Lưu kết quả theo commit SHA.

### 10.2. Pull request

- Chạy toàn bộ unit/component test liên quan.
- Kiểm tra API và contract của Order Service.
- Kiểm tra migration schema và tương thích dữ liệu.
- Chạy integration test với database/broker thử nghiệm.
- SAST và dependency scan.
- Yêu cầu review và các status check bắt buộc đạt.

### 10.3. Tích hợp

- Tạo artifact từ commit đã merge.
- Deploy vào môi trường tích hợp có phiên bản và cấu hình cố định.
- Chạy integration/system test cho tạo đơn, cập nhật trạng thái và sự kiện.
- Chạy E2E thanh toán sandbox, callback và xử lý lặp.
- Kiểm tra smoke, log, trace và một số mục tiêu hiệu năng.

### 10.4. Phát hành

- Tạo release candidate từ artifact đã xác minh.
- Chạy regression cho đăng nhập, tạo đơn, thanh toán và xem lịch sử.
- Kiểm tra cấu hình, secret, migration và khả năng rollback.
- Triển khai canary hoặc theo nhóm nhỏ.
- Chạy readiness và smoke test an toàn.
- Theo dõi error rate, latency, giao dịch thất bại và backlog trước khi mở rộng rollout.

~~~mermaid
flowchart TD
    A["Commit<br/>Lint, compile, unit, secret check"]
    B["Pull request<br/>Component, API, contract, SAST, review"]
    C["Merge / tích hợp<br/>Build artifact và deploy môi trường tích hợp"]
    D["Integration / system<br/>Database, broker, system test"]
    E["E2E và hồi quy chọn lọc<br/>Hành trình nghiệp vụ quan trọng"]
    F["Release candidate<br/>Security, performance, migration, config"]
    G["Deploy canary / progressive"]
    H["Readiness, smoke và observability"]
    I{"Ngưỡng vận hành đạt?"}
    J["Mở rộng rollout"]
    K["Dừng rollout / rollback / điều tra"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    I -->|Có| J
    I -->|Không| K
~~~

Đây là ví dụ cho một dịch vụ có tích hợp và giao dịch. Với thư viện dùng chung, ứng dụng di động hoặc hệ thống dữ liệu, tập kiểm tra và thứ tự có thể khác.

## 11. Artifact, truy vết và khả năng tái lập

Mỗi lần chạy CI/CD cần gắn kết quả với phiên bản cụ thể. Nên lưu:

- Commit SHA, branch, pull request và build ID.
- Phiên bản compiler/runtime, dependency và container image.
- Cấu hình pipeline, test tag và tập kiểm tra đã chạy.
- Phiên bản môi trường, dữ liệu hoặc fixture.
- Báo cáo test, log, screenshot, video và trace khi phù hợp.
- Kết quả scan, coverage và thông tin quality gate.
- Artifact đã build và checksum hoặc định danh bất biến.
- Người phê duyệt và các ngoại lệ đã chấp nhận.

Nếu phát hành dùng artifact được build lại từ cùng nhánh thay vì artifact đã kiểm thử, cần có cơ chế bảo đảm tính tương đương hoặc kiểm tra lại. Tốt hơn là promote cùng một artifact qua các môi trường, chỉ thay cấu hình được quản lý và xác minh.

## 12. Đo lường hiệu quả phân bổ kiểm tra

Theo dõi các chỉ số sau để điều chỉnh pipeline:

- Thời gian từ commit đến phản hồi đầu tiên.
- Thời gian PR chờ đủ các required checks.
- Thời gian chạy theo từng stage và từng loại test.
- Tỷ lệ pipeline thất bại do sản phẩm, test, dữ liệu hoặc hạ tầng.
- Tỷ lệ flaky test và số lần retry.
- Số lỗi phát hiện ở commit/PR so với lỗi phát hiện sau merge hoặc production.
- Tỷ lệ lỗi lọt và mức độ nghiêm trọng.
- Tỷ lệ kiểm tra bị skip hoặc được miễn trừ.
- Mức sử dụng runner, database, browser và môi trường.
- Thời gian từ phát hiện lỗi đến khi khắc phục.

Không nên tối ưu chỉ số thời gian bằng cách bỏ kiểm thử quan trọng. Mục tiêu là giảm thời gian phản hồi không tạo giá trị trong khi vẫn giữ đủ bằng chứng cho rủi ro cần kiểm soát.

## 13. Những sai lầm thường gặp

- **Chạy toàn bộ suite ở mọi commit:** làm phản hồi chậm và tốn tài nguyên; cần phân tầng theo thời gian và rủi ro.
- **Chỉ chạy unit test trước merge:** bỏ sót hợp đồng, tích hợp, migration và tương tác liên dịch vụ.
- **Chỉ chạy test ở cuối pipeline:** lỗi được phát hiện muộn và khó truy nguyên.
- **Dựa hoàn toàn vào test theo diff:** bỏ sót tác động gián tiếp qua thư viện, schema hoặc cấu hình dùng chung.
- **Xem pipeline xanh là bảo đảm phát hành:** vẫn cần đánh giá artifact, cấu hình, rủi ro và môi trường đích.
- **Bỏ qua test flaky bằng retry:** che giấu tín hiệu và làm giảm độ tin cậy.
- **Không phân biệt lỗi sản phẩm và lỗi hạ tầng:** dẫn đến quyết định sai về chất lượng.
- **Không lưu artifact và phiên bản:** không thể tái lập hoặc chứng minh bản nào đã được kiểm thử.
- **Bỏ qua kiểm tra sau triển khai:** deployment thành công không chứng minh ứng dụng đã sẵn sàng.
- **Ngoại lệ không có thời hạn:** các kiểm tra bị bỏ qua có thể trở thành khoảng trống lâu dài.
- **Không điều chỉnh theo rủi ro:** mọi thay đổi bị áp dụng cùng một pipeline dù mức ảnh hưởng khác nhau.

## 14. Checklist phân bổ kiểm tra trong CI/CD

- [ ] Mục tiêu và rủi ro của từng điểm kiểm soát đã rõ.
- [ ] Commit chạy các kiểm tra nhanh và có phản hồi dễ xử lý.
- [ ] PR chạy kiểm tra liên quan đến thay đổi và phụ thuộc.
- [ ] Có contract/API/integration test cho ranh giới quan trọng.
- [ ] Nhánh chung có pipeline tích hợp và bản dựng có định danh.
- [ ] System/E2E được chọn theo hành trình và rủi ro.
- [ ] Release candidate có regression, security, performance hoặc migration check khi cần.
- [ ] Có smoke/readiness sau triển khai và theo dõi chỉ số vận hành.
- [ ] Quality gate có ngưỡng, owner và quy trình ngoại lệ.
- [ ] Flaky test được theo dõi, quarantine có thời hạn và người chịu trách nhiệm.
- [ ] Runner, dữ liệu và môi trường được phân bổ để tránh tranh chấp ngoài ý muốn.
- [ ] Artifact đã kiểm thử được truy vết và promote nhất quán.
- [ ] Báo cáo, log, trace và kết quả scan được lưu theo build.
- [ ] Các chỉ số thời gian, độ ổn định, lỗi lọt và chi phí được theo dõi.

## 15. Quy trình điều chỉnh theo rủi ro và phản hồi

~~~mermaid
flowchart TD
    A["Phân loại thay đổi và rủi ro"]
    B["Chọn kiểm tra nhanh cho commit"]
    C["Bổ sung kiểm tra PR theo phụ thuộc"]
    D["Chạy kiểm tra tích hợp theo ranh giới"]
    E["Chọn regression và kiểm tra phát hành"]
    F["Đánh giá quality gate và bằng chứng"]
    G{"Đạt tiêu chí chuyển giai đoạn?"}
    H["Chuyển tiếp hoặc triển khai"]
    I["Điều tra, sửa lỗi hoặc chấp nhận ngoại lệ có hạn"]
    J["Theo dõi production và cập nhật chiến lược"]
    A --> B --> C --> D --> E --> F --> G
    G -->|Có| H --> J
    G -->|Không| I --> B
    J -. "Lỗi lọt và thay đổi rủi ro" .-> A
~~~

Phân bổ kiểm tra theo commit, pull request, tích hợp và phát hành giúp nhóm nhận phản hồi với độ sâu tăng dần theo mức rủi ro. Kiểm tra nhanh bảo vệ vòng lặp phát triển; kiểm tra PR bảo vệ nhánh chung; kiểm tra tích hợp xác minh các thành phần phối hợp; kiểm tra phát hành và sau triển khai cung cấp bằng chứng cho quyết định rollout. Khi mỗi stage có mục tiêu, quality gate, artifact và chủ sở hữu rõ ràng, CI/CD trở thành cơ chế kiểm soát chất lượng liên tục thay vì chỉ là nơi tự động chạy lệnh build và test.
