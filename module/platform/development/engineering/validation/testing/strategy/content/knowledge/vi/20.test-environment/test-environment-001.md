# Môi trường kiểm thử: Xác định môi trường cần cho từng cấp độ và loại kiểm thử

## 1. Vì sao cần chọn môi trường theo mục tiêu kiểm thử?

Môi trường kiểm thử là tổ hợp hạ tầng, phần mềm, cấu hình, dữ liệu, quyền truy cập và các phụ thuộc mà hệ thống sử dụng khi thực hiện kiểm tra. Môi trường có thể bao gồm ứng dụng đang chạy, database, message broker, dịch vụ ngoài, trình duyệt, thiết bị, mạng, feature flag, clock và công cụ quan sát.

Một bài kiểm thử có thể thất bại vì sản phẩm có lỗi, nhưng cũng có thể thất bại vì môi trường thiếu cấu hình, phụ thuộc không sẵn sàng, dữ liệu sai hoặc phiên bản không tương thích. Ngược lại, môi trường quá đơn giản có thể che giấu vấn đề chỉ xuất hiện khi các thành phần thật giao tiếp với nhau.

Vì vậy, môi trường cần được chọn theo **cấp độ kiểm thử**, **loại kiểm thử** và **rủi ro cần xác nhận**. Không có một môi trường duy nhất tối ưu cho mọi hoạt động. Unit test cần môi trường nhỏ và kiểm soát cao; kiểm thử tích hợp cần các ranh giới phụ thuộc phù hợp; E2E cần một hành trình đủ thật; kiểm thử hiệu năng cần hạ tầng và tải đại diện; kiểm thử bảo mật cần cấu hình và quyền được thiết kế để kiểm tra đúng bề mặt tấn công.

Trong **VALIDATION_TESTING_STRATEGY**, quyết định môi trường phải giúp nhóm trả lời:

- Hành vi nào cần được xác nhận và thành phần nào nằm trong phạm vi?
- Mức độ chân thực nào là cần thiết để có bằng chứng đáng tin cậy?
- Phụ thuộc nào phải chạy thật, phụ thuộc nào có thể mô phỏng?
- Dữ liệu, quyền, cấu hình và phiên bản nào phải được chuẩn bị?
- Môi trường có đủ khả năng quan sát và tái lập khi lỗi xảy ra không?
- Ai sở hữu, vận hành, làm mới và thu hồi môi trường?

## 2. Các thành phần tạo nên môi trường kiểm thử

Một môi trường không chỉ là một máy chủ hoặc một URL. Cần xem xét các thành phần sau:

| Thành phần | Nội dung cần xác định | Ví dụ |
| --- | --- | --- |
| Artifact và phiên bản | Bản dựng, commit, image, package và schema tương ứng | API service phiên bản 2.8.1 |
| Hạ tầng | Compute, container, cluster, network, storage và database | Namespace Kubernetes riêng |
| Cấu hình | Feature flag, endpoint, giới hạn, timezone và tham số runtime | Cổng thanh toán sandbox |
| Dữ liệu | Dataset, trạng thái ban đầu, quan hệ và cách cleanup | Tập dữ liệu đặt lịch tổng hợp |
| Danh tính và quyền | Tài khoản, role, service identity và secret | User thường và admin test |
| Phụ thuộc | Dịch vụ nội bộ, provider ngoài, queue và cache | Message broker, email sandbox |
| Client và thiết bị | Trình duyệt, hệ điều hành, thiết bị và phiên bản | Desktop Chrome, thiết bị Android |
| Mạng và thời gian | DNS, TLS, latency, clock, timezone và giới hạn kết nối | Network profile có độ trễ |
| Quan sát | Log, metric, trace, audit và dashboard | Correlation ID xuyên dịch vụ |
| Quản trị vòng đời | Tạo, reset, cấp quyền, hết hạn và xóa | Ephemeral environment cho mỗi nhánh |

Các thành phần này cần được ghi nhận đủ để người khác hiểu một kết quả kiểm thử được tạo ra trong điều kiện nào. Nếu chỉ lưu URL mà không lưu phiên bản, cấu hình và dữ liệu, kết quả có thể khó tái hiện.

## 3. Chọn môi trường theo cấp độ kiểm thử

### 3.1. Unit test

Unit test xác nhận một đơn vị nhỏ như hàm, lớp hoặc module trong điều kiện được kiểm soát. Môi trường thường chạy ngay trong tiến trình test hoặc một runtime nhẹ.

Đặc điểm phù hợp:

- Khởi động nhanh và có thể chạy thường xuyên.
- Dùng dữ liệu tổng hợp nhỏ, fixture hoặc builder.
- Thay thế phụ thuộc ngoài bằng stub, fake hoặc mock khi cần.
- Không phụ thuộc vào database, network hoặc provider thật nếu chúng không thuộc mục tiêu.
- Có thể điều khiển clock, random seed và lỗi đầu vào.

Ví dụ: kiểm tra quy tắc tính phí hủy lịch với các mốc thời gian khác nhau. Test không cần triển khai toàn bộ ứng dụng hay kết nối cổng thanh toán thật.

Unit test không chứng minh cấu hình triển khai, giao tiếp mạng hoặc tích hợp với database thật. Những rủi ro đó cần được kiểm tra ở cấp độ phù hợp.

### 3.2. Component test

Component test xác nhận một thành phần có ranh giới rõ, có thể gồm nhiều lớp bên trong nhưng được kiểm tra như một đơn vị. Tùy kiến trúc, thành phần có thể chạy cùng database thật trong container hoặc dùng phụ thuộc giả lập.

Môi trường thường cần:

- Runtime và cấu hình gần với thành phần thực tế.
- Database hoặc broker riêng nếu chúng thuộc ranh giới thành phần cần xác nhận.
- Phụ thuộc ngoài được thay thế có kiểm soát.
- Dữ liệu và trạng thái có thể reset.
- Log và trace đủ để chẩn đoán lỗi trong thành phần.

Ví dụ: kiểm tra dịch vụ đặt lịch với database thật trong container, nhưng dùng payment stub để tạo các kết quả thành công, từ chối và timeout.

### 3.3. Integration test

Integration test xác nhận hai hoặc nhiều thành phần giao tiếp đúng qua một ranh giới như API, database, queue hoặc hợp đồng sự kiện.

Môi trường nên có:

- Các thành phần tham gia ở phiên bản tương thích.
- Dependency thật hoặc test double đúng với mục tiêu.
- Schema, credential, network policy và cấu hình kết nối tương ứng.
- Dữ liệu thể hiện quan hệ giữa các thành phần.
- Cách theo dõi request, event hoặc transaction xuyên ranh giới.

Ví dụ: xác nhận dịch vụ đơn hàng ghi transaction vào database và phát event lên broker với schema đã thống nhất.

Nếu dùng mock thay cho broker thật, test chỉ xác nhận cách thành phần gọi mock. Nó chưa chứng minh serialization, quyền truy cập, routing hoặc cấu hình broker thực tế.

### 3.4. System test

System test đánh giá hệ thống như một tổng thể trong phạm vi đã định nghĩa. Môi trường thường triển khai các thành phần chính cùng cấu hình tích hợp, dữ liệu và phụ thuộc đủ để xác nhận hành vi hệ thống.

Cần quan tâm:

- Artifact của các thành phần thuộc cùng một phiên bản hoặc tập phiên bản tương thích.
- Cấu hình runtime và feature flag đúng với mục tiêu.
- Database, cache, queue và dịch vụ liên quan được khởi tạo nhất quán.
- Danh tính và quyền phản ánh các vai trò cần kiểm tra.
- Khả năng quan sát từ đầu vào tới kết quả cuối.
- Cơ chế reset hoặc làm mới dữ liệu giữa các đợt test.

Ví dụ: triển khai ứng dụng đặt lịch gồm UI, API, database và worker; dùng payment sandbox để xác nhận hành trình tạo lịch và xử lý callback.

### 3.5. End-to-end test

E2E test xác nhận một hành trình đi qua các ranh giới mà người dùng hoặc hệ thống gọi thực sự sử dụng. Môi trường cần đủ gần với đường đi dự kiến để tạo bằng chứng có ý nghĩa.

Môi trường có thể gồm:

- Ứng dụng và API được triển khai.
- Database và worker.
- Trình duyệt hoặc thiết bị nếu hành trình có UI.
- Provider sandbox hoặc dịch vụ ngoài thật được phê duyệt.
- Tài khoản, quyền và dữ liệu kiểm thử.
- Telemetry để theo dõi trạng thái cuối và tác dụng phụ.

Không phải mọi E2E đều cần toàn bộ production dependency. Nếu mục tiêu là xác nhận luồng ứng dụng, một sandbox ổn định có thể phù hợp. Nếu rủi ro nằm ở tích hợp thật với provider, cần có một tập kiểm thử riêng xác nhận ranh giới đó.

### 3.6. UAT và kiểm thử chấp nhận

UAT tập trung vào việc người dùng hoặc đại diện nghiệp vụ đánh giá sản phẩm có hỗ trợ quy trình thực tế và đáp ứng tiêu chí chấp nhận hay không.

Môi trường UAT nên:

- Có quy trình và cấu hình gần với cách sử dụng dự kiến.
- Có dữ liệu mẫu dễ hiểu, an toàn và phù hợp vai trò.
- Có tài khoản cho từng nhóm người dùng tham gia.
- Hạn chế tính năng hoặc quyền không cần cho UAT.
- Có cách reset dữ liệu và ghi nhận phản hồi.
- Ghi rõ khác biệt so với production.

UAT không cần dùng dữ liệu cá nhân thật để tạo cảm giác thực tế. Dữ liệu tổng hợp hoặc dữ liệu mẫu được phê duyệt thường đủ để người dùng đánh giá quy trình.

## 4. Chọn môi trường theo loại kiểm thử

Cấp độ kiểm thử mô tả phạm vi hệ thống được kiểm tra; loại kiểm thử mô tả thuộc tính hoặc rủi ro đang được đánh giá. Một loại kiểm thử có thể được thực hiện ở nhiều cấp độ và môi trường khác nhau.

### 4.1. Kiểm thử chức năng và hồi quy

Mục tiêu là xác nhận hành vi theo yêu cầu và bảo đảm thay đổi không phá vỡ chức năng đã có.

Môi trường phù hợp:

- Unit/component test chạy nhanh trong CI.
- Integration test cho các hợp đồng bị ảnh hưởng.
- System/E2E environment cho hành trình rủi ro cao.
- Dataset phiên bản hóa và có thể reset.

Không cần chạy toàn bộ E2E trên mọi thay đổi nếu các tầng thấp hơn cung cấp bằng chứng phù hợp. Nhưng thay đổi ảnh hưởng ranh giới tích hợp hoặc hành trình quan trọng cần có kiểm tra ở tầng tương ứng.

### 4.2. Kiểm thử hiệu năng và tải

Performance test cần môi trường đủ gần với điều kiện vận hành ở những yếu tố ảnh hưởng đến phép đo:

- Tài nguyên CPU, memory, storage và network.
- Số lượng instance và cách scale.
- Cấu hình cache, database pool và queue.
- Kích thước, phân phối và tốc độ sinh dữ liệu.
- Mẫu tải, thời gian warm-up và thời lượng đo.
- Monitoring và khả năng phân biệt bottleneck.

Không nên dùng một môi trường chia sẻ nhiều tải nền không kiểm soát để kết luận về latency hoặc throughput. Nếu hạ tầng không giống production, cần ghi rõ khác biệt và giới hạn kết luận.

### 4.3. Kiểm thử bảo mật

Security test cần môi trường được cấp phép và cô lập để kiểm tra xác thực, phân quyền, cấu hình, dependency và bề mặt tấn công.

Môi trường cần:

- Tài khoản và vai trò kiểm thử được kiểm soát.
- Dữ liệu giả lập hoặc dữ liệu đã được phê duyệt.
- Network boundary và cấu hình TLS phù hợp mục tiêu.
- Log/audit để xác định hành vi được phép hoặc bị từ chối.
- Phạm vi và giới hạn kiểm tra rõ ràng.

Không thực hiện scan hoặc kiểm thử xâm nhập trên hệ thống production hay hệ thống bên thứ ba khi chưa có ủy quyền và phạm vi cho phép. Với security test, môi trường và quyền thử nghiệm là một phần của thiết kế kiểm thử.

### 4.4. Kiểm thử khả năng phục hồi và độ tin cậy

Resilience test đánh giá hệ thống trước lỗi dependency, mất kết nối, node restart, queue backlog hoặc gián đoạn dịch vụ.

Môi trường nên cho phép:

- Tạo lỗi có kiểm soát và khôi phục được.
- Quan sát retry, timeout, circuit breaker và failover.
- Đo thời gian phục hồi và dữ liệu bị ảnh hưởng.
- Kiểm tra không mất hoặc nhân đôi tác dụng phụ ngoài quy tắc.
- Reset về trạng thái sạch sau thử nghiệm.

Không nên tạo lỗi tùy tiện trên một môi trường dùng chung. Chọn môi trường có giới hạn blast radius và cơ chế khôi phục đã được xác nhận.

### 4.5. Kiểm thử tương thích và khả năng truy cập

Compatibility test có thể cần nhiều trình duyệt, phiên bản hệ điều hành, thiết bị, độ phân giải, locale hoặc cấu hình mạng. Accessibility test cần môi trường có trình đọc màn hình, điều hướng bàn phím và công cụ kiểm tra phù hợp.

Hãy chọn ma trận nền tảng theo nhóm người dùng và mức hỗ trợ được công bố. Không cần kiểm tra mọi tổ hợp thiết bị nếu chúng không nằm trong phạm vi hỗ trợ; cần ghi rõ ma trận đã chọn và phần chưa bao phủ.

### 4.6. Kiểm thử migration và dữ liệu

Migration test cần môi trường có schema nguồn, dữ liệu lịch sử đại diện và phiên bản đích. Cần xác nhận:

- Migration chạy đúng thứ tự và có thể tái lập.
- Dữ liệu và quan hệ được bảo toàn.
- Các trường mới, mặc định và chuyển đổi kiểu được xử lý đúng.
- Ứng dụng tương thích với schema sau nâng cấp.
- Rollback hoặc phương án phục hồi được xác định nếu có yêu cầu.

Dùng snapshot hoặc dataset phiên bản hóa để các lần chạy so sánh được. Không lấy một database đang thay đổi làm baseline.

## 5. Ma trận chọn môi trường theo cấp độ và loại kiểm thử

| Cấp độ / loại | Môi trường thường phù hợp | Phụ thuộc | Bằng chứng trọng tâm |
| --- | --- | --- | --- |
| Unit / chức năng | Runtime cục bộ hoặc CI | Stub/fake cho dependency | Kết quả hàm, nhánh và bất biến |
| Component / chức năng | Container hoặc process riêng | Database hoặc broker cần thiết; phần còn lại có thể giả lập | Hành vi thành phần và tương tác được chọn |
| Integration / hợp đồng | Môi trường tích hợp cô lập | Dependency thật hoặc contract stub | Request/response, schema, event và trạng thái |
| System / hồi quy | Môi trường triển khai đầy đủ | Các dịch vụ chính và dữ liệu tích hợp | Hành vi hệ thống và luồng dữ liệu |
| E2E / nghiệp vụ | Staging hoặc môi trường E2E riêng | UI/API, worker, sandbox và dịch vụ cần thiết | Hành trình, trạng thái cuối và tác dụng phụ |
| UAT / chấp nhận | UAT có cấu hình và dữ liệu mẫu | Dịch vụ nghiệp vụ cần cho quy trình | Nhiệm vụ người dùng và tiêu chí chấp nhận |
| Performance / tải | Performance environment được kiểm soát | Hạ tầng và dependency có năng lực đại diện | Latency, throughput, saturation và lỗi |
| Security | Security test environment cô lập | Tài khoản, network boundary và telemetry | Kết quả xác thực, phân quyền và phát hiện |
| Resilience | Môi trường có fault injection kiểm soát | Dependency có thể gián đoạn an toàn | Phục hồi, mất dữ liệu và tác dụng phụ |
| Compatibility/accessibility | Ma trận thiết bị/trình duyệt được chọn | Browser, OS, assistive technology | Hành vi theo nền tảng và tiêu chí truy cập |
| Migration | Môi trường có snapshot schema/dữ liệu | Database và ứng dụng ở phiên bản nguồn/đích | Tính toàn vẹn, tương thích và khả năng phục hồi |

Ma trận này là điểm xuất phát. Một dự án có thể gộp nhiều loại test vào cùng môi trường nếu tài nguyên, dữ liệu và cấu hình được cô lập. Ngược lại, các hoạt động có rủi ro cao hoặc gây tác động lẫn nhau cần môi trường riêng.

## 6. Mức độ tương đồng với production

### 6.1. Tương đồng theo yếu tố ảnh hưởng đến rủi ro

Môi trường kiểm thử không nhất thiết phải sao chép production hoàn toàn. Điều quan trọng là giữ tương đồng ở những yếu tố có thể làm thay đổi kết quả:

- Kiến trúc và ranh giới thành phần.
- Phiên bản runtime, database engine và middleware.
- Cấu hình timeout, retry, pool và cache.
- Cơ chế xác thực, phân quyền và network policy.
- Schema và kích thước/phân phối dữ liệu.
- Cấu hình scale, tải và concurrency.
- Browser, thiết bị hoặc client được hỗ trợ.

Ví dụ, nếu kiểm thử hiệu năng của truy vấn database, dùng một loại database khác có thể làm kết quả không đại diện. Nếu kiểm tra quy tắc tính phí trong unit test, không cần dựng database production-like.

### 6.2. Ghi nhận khác biệt

Mỗi kết quả quan trọng nên kèm các khác biệt có thể ảnh hưởng:

| Khác biệt | Rủi ro đối với kết luận |
| --- | --- |
| Database engine hoặc phiên bản khác | Query plan, transaction và kiểu dữ liệu có thể khác |
| Provider được mock | Không xác nhận được hành vi, quota hoặc latency provider thật |
| Ít instance hơn production | Không đại diện cho scale, failover và phân phối tải |
| Dataset nhỏ hơn nhiều | Có thể bỏ sót vấn đề phân trang, index và dung lượng |
| Feature flag khác | Hành vi thực tế có thể không trùng bản được test |
| Mạng nội bộ đơn giản hơn | Có thể không tái hiện DNS, TLS, latency hoặc lỗi kết nối |

Khi môi trường có khác biệt lớn, hãy thu hẹp phạm vi kết luận hoặc bổ sung kiểm thử ở môi trường khác. Không mô tả một kết quả là production-equivalent nếu chưa có căn cứ.

### 6.3. Parity không có nghĩa sao chép dữ liệu nhạy cảm

Có thể tăng tính tương đồng bằng cấu hình, schema, workload, topology và dữ liệu tổng hợp đại diện. Việc sao chép nguyên dữ liệu production không phải điều kiện bắt buộc để có môi trường hữu ích.

Nếu cần dữ liệu có cấu trúc vận hành, phải chọn phương án được phê duyệt và đánh giá rủi ro riêng tư, bảo mật, quyền truy cập và thời hạn lưu. Ưu tiên dữ liệu tổng hợp khi nó đủ đáp ứng mục tiêu.

## 7. Quản lý phụ thuộc và test double

### 7.1. Phân loại phụ thuộc

Với mỗi phụ thuộc, xác định:

- Có thuộc phạm vi cần xác nhận không?
- Cần chạy thật, sandbox hay mô phỏng?
- Có thể tạo trạng thái lỗi hoặc phản hồi có kiểm soát không?
- Phụ thuộc có thể dùng chung an toàn không?
- Ai sở hữu cấu hình và tài khoản?
- Cách xác định trạng thái sẵn sàng là gì?

Ví dụ:

| Phụ thuộc | Unit/component | Integration/system | E2E/UAT |
| --- | --- | --- | --- |
| Database | Fake/in-memory hoặc container tùy mục tiêu | Database engine tương ứng trong môi trường cô lập | Database của hệ thống triển khai |
| Payment provider | Stub cho các kết quả | Sandbox hoặc contract test | Sandbox cho hành trình đại diện; kiểm tra thật theo phê duyệt nếu cần |
| Message broker | Fake hoặc adapter test | Broker thật trong container/namespace | Broker của môi trường E2E |
| Email/SMS | Stub ghi nhận yêu cầu | Sandbox provider hoặc mail catcher | Sandbox hoặc hộp thư test được kiểm soát |
| Identity provider | Token fixture hoặc fake | Test tenant/identity service | Test tenant với cấu hình gần thực tế |

Đây là gợi ý, không phải quy tắc cứng. Nếu chính ranh giới với dependency là mục tiêu kiểm thử, phải có bằng chứng từ ranh giới thật hoặc một contract test phù hợp.

### 7.2. Kiểm soát test double

Test double giúp tạo lỗi hiếm và kết quả xác định. Cần ghi rõ:

- Phụ thuộc nào được thay thế.
- Hợp đồng hoặc schema mà double mô phỏng.
- Những hành vi nào chưa được xác nhận với dependency thật.
- Cách đồng bộ double với thay đổi hợp đồng.

Mock sai hợp đồng có thể khiến test pass nhưng sản phẩm lỗi khi tích hợp. Vì vậy, cần contract test hoặc tập kiểm thử tích hợp để kiểm tra sự tương thích.

### 7.3. Quản lý sandbox

Sandbox thường có quota, dữ liệu giả, độ trễ hoặc hành vi khác production. Cần:

- Dùng tài khoản và credential dành riêng cho test.
- Ghi giới hạn quota và rate.
- Reset hoặc làm mới dữ liệu theo quy trình của provider.
- Tránh để nhiều test thay đổi cùng một tài nguyên.
- Xử lý callback và webhook bằng endpoint có thể truy vết.
- Không gửi giao dịch, email hoặc tin nhắn tới người thật.

## 8. Cấu hình, phiên bản và khả năng tái lập

### 8.1. Cấu hình phải được quản lý tập trung

Các tham số môi trường nên có nguồn quản lý rõ:

- Base URL và endpoint.
- Database connection và broker address.
- Feature flag.
- Timeout, retry, polling và rate limit.
- Timezone, locale và clock.
- Tài khoản kiểm thử và secret reference.
- Browser/device profile.

Không hard-code secret trong repository hoặc file cấu hình dùng chung. Tách giá trị không nhạy cảm khỏi secret; cấp secret qua cơ chế được tổ chức quản lý và giới hạn quyền.

### 8.2. Ghi nhận phiên bản môi trường

Một báo cáo test quan trọng nên gắn với:

- Commit hoặc release identifier.
- Container image/package version.
- Phiên bản schema/database migration.
- Phiên bản cấu hình và feature flag.
- Dataset ID và phiên bản.
- Phiên bản runtime, browser và thiết bị.
- Dependency hoặc sandbox version nếu có.

Khi nhiều dịch vụ được triển khai độc lập, ghi tập phiên bản tương thích thay vì chỉ ghi một mã release chung.

### 8.3. Dùng infrastructure as code và cấu hình có thể tái tạo

Infrastructure as code (IaC), container và script provisioning giúp tạo môi trường nhất quán:

- Mô tả hạ tầng và cấu hình dưới dạng phiên bản hóa.
- Tạo namespace hoặc stack riêng cho mỗi nhánh/đợt test khi phù hợp.
- Kiểm tra cấu hình trước khi chạy test.
- Tránh chỉnh tay không được ghi nhận.
- Hủy tài nguyên tạm sau khi hoàn tất.

Không nhất thiết phải dùng IaC cho unit test hoặc môi trường nhỏ. Mức tự động hóa nên tương xứng với chi phí và tần suất sử dụng.

## 9. Cô lập, reset và quản lý vòng đời môi trường

### 9.1. Môi trường dùng chung và môi trường tạm thời

| Kiểu môi trường | Ưu điểm | Rủi ro/cách kiểm soát |
| --- | --- | --- |
| Shared environment | Tiết kiệm tài nguyên, dễ truy cập | Dữ liệu và cấu hình có thể bị test khác thay đổi; cần namespace, lịch sử dụng và reset |
| Dedicated environment | Cô lập tốt, dễ điều tra | Chi phí cao hơn; cần quản lý thời gian cấp phát |
| Ephemeral environment | Tạo theo nhánh/PR hoặc phiên test, dễ loại bỏ | Cần provisioning nhanh, dữ liệu khởi tạo và cleanup tự động |
| Long-lived staging | Hữu ích cho tích hợp liên tục và UAT | Có thể lệch cấu hình, tích tụ dữ liệu và drift theo thời gian |

Không có kiểu nào luôn tốt nhất. Chọn theo mức độ song song, tính ổn định, chi phí và rủi ro tương tác.

### 9.2. Tránh nhiễm chéo giữa các test

Để cô lập:

- Dùng database/schema/namespace riêng hoặc dữ liệu có run ID.
- Tạo tài khoản và tài nguyên riêng theo test.
- Tránh dùng chung queue hoặc mailbox nếu không có correlation.
- Reset state theo cách đã kiểm tra.
- Đảm bảo cleanup chỉ xóa tài nguyên thuộc lần chạy.
- Kiểm soát thời gian và feature flag dùng chung.

Nếu không thể cô lập một phụ thuộc, cần ghi rõ giới hạn và điều phối chạy tuần tự hoặc khóa tài nguyên.

### 9.3. Kiểm tra readiness trước khi test

Không nên bắt đầu suite chỉ vì endpoint trả lời. Readiness cần xác nhận các điều kiện cần cho mục tiêu:

- Dịch vụ đã khởi động và sẵn sàng nhận request.
- Database migration hoàn tất.
- Queue consumer đang hoạt động nếu cần.
- Dependency và sandbox truy cập được.
- Dataset đã được nạp và ở trạng thái mong đợi.
- Tài khoản, quyền và secret hợp lệ.
- Feature flag và cấu hình đúng.
- Telemetry đang thu thập.

Readiness check nên nhanh và báo rõ thành phần nào chưa sẵn sàng. Không dùng retry dài để che giấu môi trường không được chuẩn bị đúng.

### 9.4. Vòng đời môi trường

~~~mermaid
flowchart TD
    A["Yêu cầu môi trường theo mục tiêu test"] --> B["Provision hạ tầng và cấu hình"]
    B --> C["Triển khai artifact và dependency"]
    C --> D["Nạp dữ liệu, cấp quyền và kiểm tra readiness"]
    D --> E["Chạy test và thu thập bằng chứng"]
    E --> F["Debrief, lưu kết quả và trạng thái"]
    F --> G{"Còn cần môi trường?"}
    G -->|"Có"| H["Reset hoặc làm mới dữ liệu"]
    H --> E
    G -->|"Không"| I["Thu hồi secret và xóa tài nguyên tạm"]
~~~

Môi trường dài hạn cần lịch bảo trì, vá lỗi và rà soát drift. Môi trường tạm thời cần cleanup kể cả khi pipeline bị hủy hoặc test thất bại.

## 10. Quan sát và chẩn đoán trong môi trường kiểm thử

Môi trường chỉ hữu ích khi có thể biết điều gì đã xảy ra. Tùy loại test, nên chuẩn bị:

- Log có timestamp và mức độ.
- Metric về latency, error rate, resource utilization và queue depth.
- Distributed trace với correlation ID.
- Audit event cho hành động nhạy cảm.
- Trạng thái dữ liệu và transaction.
- Ảnh chụp màn hình, video hoặc browser console khi có UI.
- Thông tin phiên bản và cấu hình của lần chạy.

### 10.1. Quan sát theo mục tiêu

| Mục tiêu | Bằng chứng cần có |
| --- | --- |
| Unit/component | Input, output, exception và trạng thái phụ thuộc giả |
| Integration | Request/response, schema, event, transaction và log ở hai phía |
| System/E2E | Correlation ID, trạng thái cuối, tác dụng phụ và hành trình |
| Performance | Latency percentile, throughput, error rate, saturation và tải nền |
| Security | Audit log, response, quyền truy cập và phát hiện có thể tái hiện |
| Resilience | Thời điểm fault, hành vi retry/failover, thời gian phục hồi và dữ liệu bị ảnh hưởng |
| Compatibility | Browser/device/OS, kích thước hiển thị và kết quả theo nền tảng |

### 10.2. Bảo vệ thông tin trong log

Không ghi secret, token, mật khẩu, dữ liệu cá nhân hoặc nội dung nhạy cảm không cần thiết vào log và artifact. Dùng dữ liệu tổng hợp, masking có kiểm soát hoặc mã tham chiếu. Nếu cần giữ request/response để điều tra, loại bỏ trường nhạy cảm trước khi lưu.

### 10.3. Phân biệt lỗi môi trường với lỗi sản phẩm

Khi test thất bại, thu thập trạng thái môi trường cùng với bằng chứng của SUT:

- Dependency có sẵn sàng không?
- Có lỗi kết nối, DNS hoặc TLS không?
- Dataset và quyền có đúng không?
- Artifact và cấu hình có đúng phiên bản không?
- Có tải nền hoặc test khác làm thay đổi trạng thái không?
- SUT có trả lỗi hoặc tạo trạng thái sai dù môi trường sẵn sàng không?

Ghi nhận kết quả là product defect, environment issue, test issue hoặc inconclusive theo bằng chứng. Không tự động loại mọi lỗi xảy ra ở staging thành lỗi môi trường.

## 11. Ví dụ: chọn môi trường cho hệ thống đặt lịch

Giả sử hệ thống gồm web client, booking API, database, payment adapter, message broker và notification worker.

### 11.1. Mục tiêu theo cấp độ

| Cấp độ | Mục tiêu | Môi trường |
| --- | --- | --- |
| Unit | Tính phí hủy và kiểm tra guard theo thời hạn | Runtime test với clock được điều khiển |
| Component | Xác nhận booking service không đặt trùng khung giờ | Service và database container riêng |
| Integration | Xác nhận booking API phát event đúng schema | API, database và broker trong namespace test |
| System | Xác nhận các service cập nhật trạng thái nhất quán | Stack triển khai đầy đủ với dữ liệu tổng hợp |
| E2E | Người dùng tìm, đặt và thanh toán lịch | Browser, web, API, worker và payment sandbox |
| UAT | Nhân viên đánh giá quy trình đặt và hủy lịch | UAT với tài khoản vai trò và dataset mẫu |
| Performance | Đo khả năng xử lý yêu cầu đặt đồng thời | Performance stack có tài nguyên và workload kiểm soát |
| Resilience | Kiểm tra payment timeout và broker gián đoạn | Môi trường fault-injection riêng |

### 11.2. Các điều kiện phải đồng bộ

- Các service dùng schema và phiên bản tương thích.
- Clock và timezone được xác định để kiểm tra thời hạn.
- Payment sandbox trả callback theo kịch bản.
- Event có correlation ID để nối API, broker và worker.
- Dữ liệu slot được cô lập theo lần chạy.
- Tài khoản người dùng có quyền rõ.
- Dashboard hiển thị trạng thái booking và payment.

### 11.3. Giới hạn kết luận

Nếu E2E chạy với payment sandbox, kết quả chứng minh hành trình tương tác với sandbox theo cấu hình đó. Nó không tự động chứng minh mọi hành vi của payment provider production, quota, latency hoặc settlement thật. Nếu rủi ro cần xác nhận các yếu tố đó, phải có hoạt động kiểm thử hoặc xác nhận riêng được phê duyệt.

Tương tự, nếu performance test chạy trên ít instance hơn production, báo cáo phải nêu rõ giới hạn về scale và không suy rộng trực tiếp throughput đo được sang production.

## 12. Các sai lầm thường gặp khi chọn môi trường

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng cùng một môi trường cho mọi cấp độ | Test chậm, tốn kém hoặc thiếu kiểm soát | Chọn môi trường theo phạm vi và rủi ro |
| Unit test phụ thuộc dịch vụ ngoài | Chậm và dễ flaky | Thay dependency ngoài bằng double khi phù hợp |
| Mock tất cả trong integration test | Không xác nhận được hợp đồng và cấu hình thật | Dùng dependency thật tại ranh giới cần kiểm tra |
| Staging khác xa production nhưng không ghi nhận | Kết luận thiếu cơ sở | Ghi parity gap và giới hạn kết luận |
| Chỉ kiểm tra endpoint readiness | Test chạy khi migration hoặc worker chưa sẵn sàng | Kiểm tra readiness theo dependency và mục tiêu |
| Dữ liệu dùng chung giữa các test | Nhiễm chéo và lỗi không ổn định | Namespace, reset và cleanup theo run |
| Cấu hình chỉnh tay không phiên bản hóa | Không tái tạo được kết quả | Quản lý config và IaC khi phù hợp |
| Thiếu telemetry | Khó phân biệt lỗi sản phẩm và môi trường | Chuẩn bị log, metric, trace và correlation ID |
| Dùng staging cho fault injection không kiểm soát | Ảnh hưởng người dùng test khác và dữ liệu chung | Dùng môi trường fault riêng có giới hạn |
| Sao chép dữ liệu thật không đánh giá | Rủi ro riêng tư và truy cập | Ưu tiên dữ liệu tổng hợp hoặc nguồn đã phê duyệt |
| Không thu hồi môi trường tạm | Rò rỉ tài nguyên, secret và dữ liệu | Tự động cleanup và kiểm tra sau pipeline |

## 13. Mẫu xác định yêu cầu môi trường kiểm thử

~~~text
Tên môi trường / mục tiêu:
Cấp độ kiểm thử:
Loại kiểm thử:
Phạm vi hệ thống:

Artifact / phiên bản:
Runtime / database / middleware:
Hạ tầng / network:
Cấu hình / feature flag / timezone:

Phụ thuộc:
- Dependency:
- Chạy thật / sandbox / double:
- Lý do lựa chọn:

Dữ liệu:
- Dataset ID / phiên bản:
- Cách nạp và reset:
- Quyền và tài khoản:

Readiness criteria:
Observability:
- Log:
- Metric:
- Trace / correlation ID:

Cô lập và chạy song song:
Chủ sở hữu:
Thời gian tồn tại:
Quy trình reset / cleanup:

Khác biệt so với production:
Rủi ro và giới hạn kết luận:
~~~

## 14. Checklist chọn và vận hành môi trường

- [ ] Mục tiêu, cấp độ và loại kiểm thử được xác định.
- [ ] Thành phần nằm trong phạm vi và ranh giới cần xác nhận đã rõ.
- [ ] Mức độ tương đồng với production được chọn theo yếu tố ảnh hưởng đến rủi ro.
- [ ] Artifact, schema, cấu hình và dependency có phiên bản tương thích.
- [ ] Dependency thật, sandbox hoặc test double được chọn có lý do.
- [ ] Dữ liệu và tài khoản phù hợp, có nguồn gốc và quyền sử dụng rõ.
- [ ] Readiness check xác nhận cả ứng dụng, database, worker và dependency cần thiết.
- [ ] Môi trường có đủ log, metric, trace và correlation ID cho mục tiêu.
- [ ] Test được cô lập, có thể reset và chạy song song an toàn.
- [ ] Secret và quyền truy cập được cấp theo nguyên tắc tối thiểu.
- [ ] Khác biệt với production và giới hạn kết luận được ghi nhận.
- [ ] Môi trường tạm có quy trình thu hồi và cleanup đáng tin cậy.
- [ ] Môi trường dài hạn có lịch bảo trì và rà soát cấu hình drift.
- [ ] Khi test fail, có thể phân loại lỗi sản phẩm, môi trường, test hoặc thiếu bằng chứng.

Chọn môi trường theo cấp độ và loại kiểm thử giúp nhóm đặt đúng mức độ chân thực, kiểm soát và chi phí cho từng hoạt động. Khi phiên bản, cấu hình, dữ liệu, phụ thuộc, quyền và khả năng quan sát được quản lý rõ ràng, kết quả kiểm thử sẽ dễ tái lập, dễ chẩn đoán và có giới hạn kết luận minh bạch.
