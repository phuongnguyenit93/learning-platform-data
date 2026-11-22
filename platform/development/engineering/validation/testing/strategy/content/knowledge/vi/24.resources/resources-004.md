# Tính thời gian cho dữ liệu, môi trường, điều tra và sửa bộ kiểm thử

Một kế hoạch kiểm thử có thể có đủ test case nhưng vẫn không khả thi nếu không tính thời gian chuẩn bị dữ liệu, chờ môi trường, điều tra thất bại và sửa bộ kiểm thử. Một pipeline chỉ ghi nhận thời gian chạy test thường đánh giá thấp công sức thực tế: runner phải được cấp phát, database cần seed, dịch vụ phụ thuộc cần sẵn sàng, artifact cần thu thập, dữ liệu tạm cần dọn và kết quả không ổn định cần được điều tra. Khi những công việc này không được dự trù, nhóm thường phải cắt phạm vi kiểm thử vào cuối chu kỳ hoặc để test flaky tồn tại lâu vì không còn thời gian sửa.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, tính thời gian cho dữ liệu, môi trường, điều tra và sửa bộ kiểm thử là hoạt động lập kế hoạch nguồn lực cho toàn bộ vòng đời xác thực. Mục tiêu là ước lượng đủ các công việc trực tiếp và gián tiếp, phân bổ năng lực phù hợp với rủi ro, giữ thời gian dự phòng cho bất định và đo sai lệch giữa kế hoạch với thực tế. Ước lượng cần bao gồm cả thời gian đồng hồ, công sức con người, năng lực hạ tầng và chi phí lưu giữ dữ liệu hoặc bằng chứng.

## 1. Xác định phạm vi nguồn lực cần tính

### Không chỉ tính thời gian thực thi test

Một chu kỳ kiểm thử thường gồm nhiều hoạt động:

1. Phân tích thay đổi, yêu cầu và rủi ro để xác định phạm vi.
2. Chuẩn bị hoặc làm mới dữ liệu kiểm thử.
3. Cấp phát và cấu hình môi trường.
4. Chờ dịch vụ, quyền truy cập và phụ thuộc sẵn sàng.
5. Chạy test, theo dõi tiến trình và thu thập bằng chứng.
6. Phân loại kết quả và điều tra lỗi.
7. Sửa test, fixture, môi trường hoặc sản phẩm theo nguyên nhân.
8. Chạy lại kiểm chứng sau sửa.
9. Dọn tài nguyên, lưu artifact và cập nhật báo cáo.

Nếu kế hoạch chỉ lấy thời gian thực thi test từ lần chạy gần nhất, các hoạt động còn lại sẽ trở thành chi phí ẩn. Chi phí ẩn thường xuất hiện dưới dạng chờ đợi, thao tác thủ công, hỗ trợ ngoài kế hoạch hoặc làm thêm giờ gần ngày phát hành.

### Phân biệt thời gian đồng hồ và công sức

Hai khái niệm cần được theo dõi riêng:

- **Thời gian đồng hồ (elapsed time):** khoảng thời gian từ lúc bắt đầu đến khi hoàn tất một công việc, bao gồm cả thời gian chờ.
- **Công sức (effort):** thời gian con người hoặc tài nguyên chuyên môn thực sự được sử dụng cho công việc.

Ví dụ, một lần cấp môi trường mất 40 phút theo đồng hồ nhưng chỉ cần 10 phút thao tác của kỹ sư; phần còn lại là thời gian provisioning. Một lần điều tra kéo dài hai giờ có thể chỉ có 70 phút làm việc tập trung và 50 phút chờ log, quyền hoặc phản hồi từ nhóm phụ thuộc.

Cần tách hai số này để biết vấn đề nằm ở năng lực nhân sự, tự động hóa hay thời gian chờ hạ tầng. Không cộng thời gian chờ của nhiều tác vụ song song như thể tất cả đều tiêu tốn cùng một khoảng thời gian lịch.

### Nhóm nguồn lực theo loại

| Nhóm | Ví dụ | Đơn vị có thể theo dõi |
|---|---|---|
| Dữ liệu | Seed, fixture, snapshot, dữ liệu tổng hợp, reset và cleanup | Phút chuẩn bị, dung lượng, số bản ghi |
| Môi trường | Runner, container, database, sandbox, preview environment | Phút cấp phát, giờ sử dụng, số môi trường đồng thời |
| Thực thi | Unit, integration, E2E, performance và regression | Thời gian chạy, CPU-minute, lượt chạy |
| Điều tra | Phân loại lỗi, đọc log/trace, tái hiện và đối soát | Giờ kỹ sư, thời gian đến nguyên nhân |
| Sửa bộ kiểm thử | Sửa assertion, fixture, selector, helper, test flaky | Giờ sửa, số lần chạy xác minh |
| Hỗ trợ phụ thuộc | Quyền truy cập, nhà cung cấp, vận hành và nhóm sở hữu dịch vụ | Thời gian chờ, giờ hỗ trợ |
| Bằng chứng và quản trị | Báo cáo, artifact, review, phê duyệt và lưu giữ | Giờ xử lý, dung lượng và thời hạn |

Phạm vi này cần được điều chỉnh theo loại sản phẩm. Một hệ thống nhúng có thể cần thiết bị vật lý và lịch sử dụng lab; một dịch vụ SaaS có thể cần tenant, sandbox nhà cung cấp và môi trường nhiều vùng.

## 2. Lập danh mục công việc và đầu ra

### Chuyển phạm vi kiểm thử thành công việc có thể ước lượng

Mỗi nhóm test cần được phân rã thành các công việc có đầu vào, đầu ra và người sở hữu. Ví dụ, “chuẩn bị dữ liệu E2E” có thể gồm tạo tenant, cấu hình quyền, tạo sản phẩm, seed trạng thái tồn kho, tạo giao dịch sandbox và xác minh dữ liệu ban đầu.

Một work item nên nêu:

- Mục tiêu và phạm vi kiểm tra.
- Loại dữ liệu hoặc môi trường cần có.
- Điều kiện tiên quyết và phụ thuộc.
- Số lượng hoặc kích thước cần chuẩn bị.
- Phương pháp tự động hay thủ công.
- Đầu ra cần bàn giao.
- Tiêu chí hoàn tất.
- Người hoặc nhóm chịu trách nhiệm.
- Rủi ro và giả định ảnh hưởng đến ước lượng.

Không ước lượng một mục quá lớn như “kiểm thử tích hợp” nếu chưa biết số dịch vụ, số hợp đồng, dataset và môi trường liên quan.

### Xác định đầu ra của từng nhóm công việc

| Công việc | Đầu ra có thể kiểm chứng |
|---|---|
| Chuẩn bị dữ liệu | Fixture có phiên bản, seed thành công, ID và trạng thái ban đầu |
| Chuẩn bị môi trường | Environment ID, cấu hình, phiên bản dịch vụ và health check |
| Chạy test | Kết quả theo test, run ID, log và artifact |
| Điều tra | Phân loại nguyên nhân, bằng chứng và lỗi được liên kết |
| Sửa test | Thay đổi đã review và kết quả xác minh |
| Cleanup | Registry được cập nhật, tài nguyên được thu hồi hoặc ghi nhận còn sót |
| Báo cáo | Phạm vi đã chạy, chưa chạy, rủi ro còn lại và quyết định |

Đầu ra rõ ràng giúp phân biệt công việc hoàn thành với công việc mới chỉ bắt đầu hoặc đang bị chặn.

### Xác định quan hệ phụ thuộc và đường găng

Một số việc có thể chạy song song, một số phải hoàn thành theo thứ tự. Ví dụ, dữ liệu chỉ có thể seed sau khi schema tương ứng đã được triển khai; E2E chỉ chạy sau khi môi trường và dịch vụ phụ thuộc sẵn sàng; điều tra chỉ bắt đầu hiệu quả khi artifact đã được thu thập.

Hãy lập dependency graph hoặc sơ đồ luồng công việc để xác định:

- Việc nào có thể thực hiện độc lập?
- Việc nào cần kết quả từ nhóm khác?
- Việc nào nằm trên đường găng?
- Có thể chuẩn bị dữ liệu hoặc test trước khi môi trường sẵn sàng không?
- Việc nào có thể tự động hóa hoặc tái sử dụng?
- Nếu một phụ thuộc trễ, công việc nào bị ảnh hưởng?

Không giả định mọi người và runner có thể làm việc song song vô hạn. Tính đến giới hạn số môi trường, database connection, sandbox quota và năng lực review.

## 3. Ước lượng thời gian chuẩn bị dữ liệu

### Phân loại dữ liệu theo kích thước và cách tạo

Dữ liệu kiểm thử có thể gồm:

- Fixture nhỏ cho unit hoặc component test.
- Dataset nghiệp vụ có quan hệ cho integration và E2E.
- Dataset lớn cho hiệu năng và khả năng mở rộng.
- Snapshot từ schema cũ cho migration.
- Dữ liệu biên, dữ liệu sai định dạng và trạng thái hiếm.
- Dữ liệu tái hiện sự cố hoặc test flaky.
- Dữ liệu tổng hợp phục vụ kiểm thử quyền và phân tách tenant.

Mỗi loại có chi phí khác nhau. Fixture nhỏ có thể được tạo ngay trong bộ nhớ; dataset lớn có thể cần tải, giải nén, import, index và xác minh. Dữ liệu cần tạo qua API nghiệp vụ có thể chậm hơn seed trực tiếp nhưng tạo bằng chứng sát hành vi người dùng hơn.

### Tính chi phí tạo mới

Các yếu tố cần tính:

- Số lượng bản ghi và độ phức tạp quan hệ.
- Cách tạo: builder, factory, API, seed, import hoặc snapshot.
- Thời gian tạo và xác minh.
- Giới hạn tốc độ của database hoặc dịch vụ ngoài.
- Thời gian tạo index, cache và read model.
- Số worker hoặc shard cần dataset riêng.
- Số lần phải tạo lại trong một chu kỳ.
- Khả năng tái sử dụng dữ liệu nền bất biến.

Có thể dùng công thức ước lượng ban đầu:

\[
T_{data}=T_{prepare}+N_{runs}\times T_{create}+T_{verify}+T_{cleanup}
\]

Trong đó, \(N_{runs}\) là số lần phải tạo dữ liệu riêng. Nếu dùng snapshot, cần cộng thời gian tạo snapshot và restore, đồng thời tính chi phí xác minh tính tương thích.

### Phân biệt seed, fixture và snapshot

- **Seed:** tập dữ liệu nền được quản lý phiên bản và nạp vào môi trường.
- **Fixture:** trạng thái cụ thể mà một test hoặc suite cần.
- **Factory/builder:** cơ chế tạo dữ liệu theo tham số và mục tiêu nghiệp vụ.
- **Snapshot:** bản chụp trạng thái đã biết để khôi phục nhanh.
- **Dataset sự cố:** dữ liệu tối thiểu giúp tái hiện một lỗi đã phát hiện.

Ước lượng cần xem xét chi phí duy trì, không chỉ thời gian tạo lần đầu. Seed có thể nhanh nhưng cần cập nhật khi schema thay đổi. Snapshot có thể restore nhanh nhưng cần tạo lại khi phiên bản không còn tương thích. Fixture dùng chung giảm chi phí nhưng cần bảo đảm bất biến.

### Tính thời gian reset và cleanup

Dữ liệu phải được làm mới giữa các lần chạy để tránh phụ thuộc trạng thái cũ. Cần tính thời gian:

- Rollback transaction hoặc xóa theo namespace.
- Reset database/schema hoặc restore snapshot.
- Xóa queue message, job và outbox.
- Invalidate cache và search index.
- Thu hồi tài khoản, phiên và token.
- Xóa file, bucket hoặc artifact tạm.
- Xác minh không còn tài nguyên ngoài chính sách giữ lại.

Không chỉ tính thời gian gọi lệnh cleanup. Cần tính thời gian kiểm tra kết quả và xử lý khi cleanup thất bại.

### Lập kế hoạch cho dữ liệu cần giữ để điều tra

Một số dữ liệu cần được giữ sau khi test fail để tái hiện hoặc đối soát. Hãy phân loại:

- Dữ liệu có thể xóa ngay sau khi xác minh.
- Dữ liệu cần giữ trong thời gian điều tra.
- Artifact cần lưu theo retention.
- Audit record không được xóa theo cleanup thông thường.
- Dữ liệu nhạy cảm cần khử định danh hoặc hạn chế truy cập.

Việc giữ dữ liệu làm tăng dung lượng và chi phí. Cần xác định trước thời hạn, người sở hữu và cách xóa sau khi kết thúc điều tra.

## 4. Ước lượng thời gian và năng lực môi trường

### Xác định các thành phần của môi trường

Môi trường kiểm thử có thể cần:

- Runner hoặc máy ảo.
- Container, image và runtime.
- Database, cache, broker và object storage.
- Dịch vụ ứng dụng và worker.
- Sandbox của nhà cung cấp.
- DNS, routing, certificate và secret.
- Thiết bị, trình duyệt hoặc lab vật lý.
- Monitoring, log và trace.

Mỗi thành phần có thời gian cấp phát, cấu hình, health check, warm-up, sử dụng và thu hồi. Nếu một môi trường gồm nhiều dịch vụ, thời gian sẵn sàng thường phụ thuộc thành phần chậm nhất hoặc chuỗi phụ thuộc.

### Ước lượng thời gian provisioning

Có thể phân rã:

\[
T_{env}=T_{queue}+T_{provision}+T_{configure}+T_{warmup}+T_{health}
\]

Trong đó:

- \(T_{queue}\): thời gian chờ tài nguyên.
- \(T_{provision}\): thời gian tạo runner, container, database hoặc dịch vụ.
- \(T_{configure}\): nạp cấu hình, secret và quyền.
- \(T_{warmup}\): khởi động ứng dụng, migration, cache hoặc index.
- \(T_{health}\): xác minh readiness và phụ thuộc.

Nếu nhiều thành phần được cấp phát song song, tổng thời gian có thể gần với nhánh lâu nhất thay vì tổng tất cả. Tuy nhiên, cần cộng các bước tuần tự và thời gian điều phối.

### Phân biệt liveness và readiness

Một process đang chạy chưa chắc sẵn sàng nhận test. Health check cần xác minh điều kiện phù hợp:

- Ứng dụng đã khởi động.
- Database có thể truy cập và schema đúng phiên bản.
- Worker đã đăng ký consumer.
- Queue và broker sẵn sàng.
- Dịch vụ phụ thuộc đáp ứng hợp đồng cần thiết.
- Dữ liệu seed đã được nạp và có thể đọc.
- Secret và quyền đã được cấu hình.

Nếu test bắt đầu trước readiness, pipeline có thể ghi nhận lỗi giả do môi trường chưa hoàn tất. Ước lượng phải tính thời gian chờ readiness và xử lý khi không đạt.

### Tính năng lực môi trường đồng thời

Một runner có thể xử lý nhiều job nhưng database hoặc sandbox có giới hạn riêng. Cần xác định:

- Số runner khả dụng.
- Số môi trường có thể cấp đồng thời.
- CPU, bộ nhớ và dung lượng đĩa.
- Database connection pool và giới hạn I/O.
- Queue throughput và số worker.
- Quota API hoặc sandbox.
- Số shard an toàn.
- Thời gian giải phóng tài nguyên.

Không tăng concurrency chỉ dựa trên số CPU. Quá nhiều job đồng thời có thể làm database quá tải, tăng timeout và kéo dài tổng thời gian.

### Môi trường dùng chung và môi trường tạm

Môi trường dùng chung giảm thời gian provisioning nhưng có nguy cơ xung đột dữ liệu và cấu hình. Môi trường tạm tăng tính cô lập nhưng tốn thời gian và tài nguyên.

| Lựa chọn | Lợi ích | Chi phí hoặc rủi ro |
|---|---|---|
| Môi trường dùng chung | Provision một lần, dễ duy trì dịch vụ nền | Cạnh tranh tài nguyên, trạng thái còn sót, khó tái hiện |
| Môi trường theo run | Cô lập tốt, dễ cleanup theo owner | Tăng thời gian tạo và chi phí hạ tầng |
| Môi trường theo shard | Cân bằng giữa cô lập và tái sử dụng | Cần quản lý namespace và concurrency |
| Snapshot restore | Khởi tạo dataset nhanh | Chi phí snapshot, tương thích và dung lượng |
| Sandbox nhà cung cấp | Kiểm tra tích hợp gần thực tế | Quota, độ ổn định và giới hạn dữ liệu |

Lựa chọn cần dựa trên rủi ro của test và chi phí vòng đời. Không nhất thiết mọi unit test cần môi trường riêng; nhưng test có tác dụng phụ hoặc dữ liệu thay đổi cần ranh giới cô lập.

## 5. Tính thời gian chạy test và tài nguyên thực thi

### Dùng dữ liệu lịch sử

Ước lượng thời gian test nên dựa trên kết quả nhiều lần chạy gần đây, theo đúng loại runner, cấu hình và dataset. Thu thập:

- p50, p90 và p95 thời gian chạy.
- Số lần chạy và số test trong suite.
- Thời gian setup/teardown.
- Tỷ lệ retry và flaky.
- Mức sử dụng CPU, bộ nhớ và I/O.
- Thời gian chờ dịch vụ ngoài.
- Khác biệt giữa môi trường local, CI và staging.

Không dùng một lần chạy nhanh nhất làm baseline. Một test có thời gian dao động lớn cần ngân sách và điều tra riêng.

### Ước lượng suite và shard

Nếu suite chạy tuần tự, tổng thời gian gần bằng tổng thời gian từng test cộng setup và teardown. Khi chạy song song, thời gian phụ thuộc vào số shard, phân bố test, giới hạn tài nguyên và test chậm nhất.

Công thức đơn giản cho thời gian tuần tự:

\[
T_{serial}\approx T_{setup}+\sum_{i=1}^{n}T_i+T_{teardown}
\]

Với \(k\) worker, giới hạn lý tưởng có thể gần:

\[
T_{parallel}\geq \max\left(\frac{\sum T_i}{k},T_{longest}\right)
\]

Đây chỉ là cận dưới tham khảo. Thực tế cần tính thời gian khởi tạo mỗi worker, tranh chấp tài nguyên, test không an toàn song song, hàng đợi và phần công việc không thể chia shard.

### Tính chi phí retry

Retry làm tăng thời gian và tài nguyên. Nếu một test có tỷ lệ retry cao, không nên chỉ nhân thời gian trung bình với số lần thử. Cần ghi nhận:

- Số test retry.
- Số lần retry tối đa.
- Thời gian chờ giữa các lần.
- Tỷ lệ pass sau retry.
- Tác dụng phụ và cleanup giữa lần chạy.
- Thời gian điều tra flaky sau khi pipeline hoàn tất.

Retry cần được xem là tín hiệu chất lượng và chi phí, không phải cơ chế làm cho báo cáo xanh.

### Phân biệt CPU time, runner time và elapsed time

- CPU time phản ánh thời gian xử lý trên CPU.
- Runner time phản ánh thời gian tài nguyên runner bị chiếm.
- Elapsed time phản ánh thời gian đồng hồ của công việc.
- Tổng chi phí có thể bao gồm cả dung lượng lưu trữ, network và dịch vụ ngoài.

Một test chờ API 90 giây có thể dùng ít CPU nhưng vẫn giữ runner và môi trường. Tối ưu bằng cách giải phóng runner khi chờ hoặc kiểm tra bất đồng bộ có thể giảm chi phí dù elapsed time của hành trình không đổi.

## 6. Dự trù thời gian điều tra lỗi

### Điều tra là một phần của kế hoạch

Kết quả fail không tự giải thích nguyên nhân. Nhóm cần thời gian để:

1. Phân loại sơ bộ lỗi.
2. Xác định phiên bản, môi trường và dữ liệu.
3. Đọc test report, log, metric và trace.
4. Tái hiện lỗi trong điều kiện phù hợp.
5. Phân biệt lỗi sản phẩm, test, dữ liệu, môi trường hoặc phụ thuộc.
6. Xác định phạm vi ảnh hưởng và mức độ rủi ro.
7. Ghi nhận lỗi và giao người xử lý.
8. Xác minh nguyên nhân sau khi có thay đổi.

Nếu kế hoạch chỉ dành thời gian chạy test mà không dành thời gian điều tra, kết quả fail sẽ tích tụ thành hàng đợi không được xử lý.

### Ước lượng theo loại thất bại

Các nhóm lỗi có chi phí điều tra khác nhau:

| Loại thất bại | Công việc điều tra |
|---|---|
| Assertion sai rõ ràng | Kiểm tra expected/actual, yêu cầu và thay đổi gần nhất |
| Test flaky | Chạy lặp có kiểm soát, kiểm tra dữ liệu, thứ tự, đồng thời và thời gian |
| Timeout | Xem deadline, trạng thái cuối, trace và độ trễ phụ thuộc |
| Lỗi môi trường | Kiểm tra provisioning, health, quota, cấu hình và runner |
| Lỗi tích hợp | Đối chiếu contract, request/response và trạng thái hai phía |
| Lỗi dữ liệu | Kiểm tra seed, fixture, migration, nguồn có thẩm quyền và cleanup |
| Lỗi không tái hiện | Giữ artifact, seed, phiên bản và điều kiện lần chạy đầu |

Ước lượng ban đầu có thể dùng dữ liệu lịch sử theo nhóm lỗi. Không gán một thời gian cố định cho mọi lỗi vì mức độ phức tạp và khả năng tái hiện khác nhau.

### Tính thời gian đến nguyên nhân

Một chỉ số hữu ích là thời gian từ lúc phát hiện thất bại đến khi có phân loại nguyên nhân đủ để hành động. Có thể theo dõi riêng:

- Thời gian chờ người nhận thông báo.
- Thời gian thu thập bằng chứng.
- Thời gian tái hiện.
- Thời gian xác định owner.
- Thời gian chờ nhóm phụ thuộc.
- Thời gian phân tích kỹ thuật.

Nếu phần lớn thời gian là chờ quyền hoặc chờ người sở hữu dịch vụ, cần cải thiện quy trình phối hợp thay vì chỉ tăng số kỹ sư kiểm thử.

### Chuẩn bị ngân sách điều tra theo rủi ro

Dành nhiều thời gian hơn cho:

- Lỗi ở luồng thanh toán, dữ liệu hoặc phân quyền.
- Migration và thay đổi schema.
- Thay đổi shared library hoặc API dùng chung.
- Lỗi khó tái hiện hoặc chỉ xuất hiện khi chạy song song.
- Sự cố có thể ảnh hưởng nhiều tenant hoặc vùng.
- Lỗi không có đủ log/trace hoặc trạng thái có thẩm quyền.

Lỗi ít ảnh hưởng và dễ khắc phục có thể xử lý trong vòng ngắn hơn, nhưng vẫn phải ghi nhận nếu nó cho thấy khoảng trống kiểm thử.

## 7. Dự trù thời gian sửa bộ kiểm thử

### Phân loại việc sửa

Không phải mọi test fail đều cần sửa test. Cần phân biệt:

- **Sửa test:** assertion, selector, fixture, helper hoặc đồng bộ sai.
- **Sửa dữ liệu:** seed lỗi thời, factory thiếu trường hoặc dữ liệu trùng.
- **Sửa môi trường:** cấu hình, image, quota hoặc readiness.
- **Sửa framework:** helper chung, adapter, reporter hoặc cơ chế retry.
- **Sửa sản phẩm:** hành vi không đáp ứng yêu cầu.
- **Cập nhật phạm vi:** test không còn phù hợp với yêu cầu hoặc tính năng đã thay đổi.

Phân loại đúng tránh dùng thời gian sửa test để che lỗi sản phẩm hoặc sửa sản phẩm chỉ để chiều theo một assertion sai.

### Ước lượng theo phạm vi ảnh hưởng

Sửa một selector trong một test thường khác với thay đổi helper được hàng trăm test sử dụng. Ước lượng cần tính:

- Số test bị ảnh hưởng.
- Mức độ dùng chung của helper hoặc fixture.
- Khả năng thay đổi hợp đồng.
- Số môi trường cần xác minh.
- Khả năng phát sinh lỗi ở test khác.
- Review và cập nhật tài liệu.
- Chạy lại bộ kiểm thử liên quan.
- Chi phí triển khai thay đổi nếu là lỗi sản phẩm.

Thay đổi dùng chung cần thêm thời gian review và regression để tránh sửa một lỗi nhưng làm hỏng nhiều suite khác.

### Tính thời gian xác minh sau sửa

Một thay đổi chỉ được xem là hoàn tất khi có bằng chứng phù hợp. Kế hoạch nên dành thời gian cho:

- Chạy test mục tiêu.
- Chạy test liên quan trực tiếp.
- Chạy lại test bị ảnh hưởng bởi helper hoặc fixture.
- Chạy lặp để xác nhận không còn flaky.
- Chạy song song nếu thay đổi liên quan cô lập dữ liệu.
- Kiểm tra artifact và cleanup.
- Review kết quả và cập nhật trạng thái.

Không tính việc sửa code là hoàn tất nếu chưa có thời gian xác minh sau sửa.

### Quản lý test flaky và nợ bảo trì

Một test flaky có thể tiêu tốn chi phí qua nhiều lần chạy: retry, điều tra, trì hoãn review và giảm niềm tin vào pipeline. Hãy theo dõi:

- Tỷ lệ flaky và số lần retry.
- Số giờ điều tra.
- Tuổi của test bị cách ly.
- Số lần sửa nhưng lỗi tái xuất hiện.
- Mức rủi ro bị mất bảo vệ khi test bị vô hiệu hóa.
- Chi phí chạy bổ sung do retry.

Ưu tiên sửa test có tần suất chạy cao, rủi ro bảo vệ lớn hoặc chi phí gây ra cho nhiều nhóm. Test ít chạy và rủi ro thấp có thể xếp lịch sau, nhưng phải có người sở hữu và mốc xem xét.

## 8. Lập kế hoạch nhân lực và năng lực chuyên môn

### Xác định vai trò cần tham gia

Các công việc có thể cần:

- Kỹ sư kiểm thử hoặc QA.
- Nhà phát triển sở hữu module.
- Kỹ sư nền tảng hoặc CI/CD.
- Kỹ sư dữ liệu hoặc database.
- Vận hành hoặc SRE.
- Chuyên gia bảo mật.
- Nhóm sở hữu tích hợp hoặc nhà cung cấp.
- Người phê duyệt rủi ro hoặc phát hành.

Không phải mọi công việc đều cần tất cả vai trò. Hãy gán người chịu trách nhiệm và người hỗ trợ dựa trên ranh giới sở hữu.

### Tính năng lực khả dụng

Công sức kế hoạch cần tính đến:

- Ngày nghỉ, trực vận hành và nhiệm vụ song song.
- Thời gian review và phối hợp.
- Công việc bảo trì thường xuyên.
- Hỗ trợ release hoặc incident.
- Thời gian học và chuyển giao.
- Giới hạn số người có quyền truy cập môi trường hoặc dữ liệu.

Không lấy toàn bộ giờ làm việc danh nghĩa làm năng lực kiểm thử. Nếu một kỹ sư phải hỗ trợ nhiều dự án, năng lực thực tế cho nhiệm vụ này thấp hơn.

### Tránh nút thắt ở người có chuyên môn duy nhất

Nếu chỉ một người biết cách reset môi trường hoặc đọc trace của một dịch vụ, công việc có thể bị chặn khi người đó bận. Hãy:

- Tài liệu hóa quy trình.
- Tự động hóa thao tác lặp.
- Chia sẻ quyền theo nguyên tắc tối thiểu.
- Đào tạo người thay thế.
- Ghi rõ owner và kênh hỗ trợ.
- Lên lịch trước các công việc cần chuyên gia.

Đây cũng là nguồn lực cần tính khi dự trù thời gian điều tra và sửa.

## 9. Tính năng lực hạ tầng và chi phí sử dụng

### Tính tài nguyên đồng thời

Tổng số job không phản ánh đầy đủ nhu cầu. Cần dự báo mức sử dụng đỉnh:

- Số runner đồng thời.
- CPU và memory trên mỗi runner.
- Dung lượng workspace.
- Database instance và connection.
- Queue, broker và worker.
- Sandbox quota.
- Băng thông và dung lượng artifact.
- Thời gian giữ môi trường sau test.

Một pipeline chạy nhiều shard có thể giảm elapsed time nhưng tăng tổng tài nguyên. Cần đặt giới hạn để không làm môi trường kiểm thử ảnh hưởng dịch vụ dùng chung.

### Ước lượng chi phí môi trường tạm

Có thể ước lượng theo:

\[
C_{env}=\sum_j (N_j\times H_j\times R_j)+C_{storage}+C_{network}
\]

Trong đó \(N_j\) là số tài nguyên loại \(j\), \(H_j\) là số giờ sử dụng và \(R_j\) là đơn giá hoặc hệ số chi phí của loại tài nguyên đó. Công thức chỉ là mô hình dự trù; dùng đơn giá và cách tính thực tế của nền tảng.

Cần tính cả tài nguyên bị bỏ quên do cleanup thất bại. Theo dõi tuổi môi trường và số tài nguyên quá TTL giúp phát hiện chi phí mồ côi.

### Giới hạn và phân bổ quota

Đặt quota hoặc giới hạn theo:

- Dự án hoặc nhóm.
- Nhánh hoặc pull request.
- Run ID.
- Loại test.
- Môi trường.
- Thời gian tồn tại.
- Dung lượng artifact.

Khi quota gần hết, pipeline cần báo rõ và có chính sách ưu tiên. Không tự động bỏ qua kiểm thử rủi ro cao chỉ vì quota bị cạn; cần quyết định mở rộng năng lực, xếp lịch hoặc điều chỉnh phạm vi có phê duyệt.

## 10. Ước lượng bằng dữ liệu lịch sử và mức bất định

### Dùng ước lượng ba điểm

Khi công việc chưa rõ, có thể dùng ba giá trị:

- **Lạc quan (O):** điều kiện thuận lợi, ít trở ngại.
- **Khả dĩ nhất (M):** tình huống thường gặp.
- **Bi quan (P):** có phụ thuộc trễ, lỗi dữ liệu hoặc cần điều tra thêm.

Một công thức tham khảo kiểu PERT:

\[
T_{estimate}=\frac{O+4M+P}{6}
\]

Công thức giúp thể hiện bất định nhưng không thay thế dữ liệu lịch sử. Với công việc có phân phối lệch mạnh hoặc nhiều phụ thuộc, nên dùng percentile và kịch bản thay vì coi một con số là chắc chắn.

### Ghi rõ giả định và độ tin cậy

Mỗi ước lượng cần ghi:

- Nguồn số liệu hoặc lần chạy tham chiếu.
- Phiên bản môi trường và dataset.
- Giả định về số runner và concurrency.
- Phụ thuộc bên ngoài.
- Mức độ mới của dữ liệu lịch sử.
- Khoảng ước lượng và độ tin cậy.
- Điều kiện khiến phải ước lượng lại.

Ví dụ, thời gian seed dataset có thể đúng khi database trống nhưng không còn đúng sau khi kích thước tăng gấp đôi. Cần ghi rõ kích thước và cấu hình tham chiếu.

### Dùng khoảng thay vì độ chính xác giả

Nếu chưa đủ dữ liệu, báo khoảng như “20–35 phút” và nêu yếu tố có thể làm tăng thời gian. Tránh ghi “27 phút” nếu độ bất định thực tế là hàng chục phút.

Có thể chia độ tin cậy:

- Cao: công việc lặp lại, đầu vào và môi trường ổn định.
- Trung bình: có dữ liệu tham chiếu nhưng một số phụ thuộc thay đổi.
- Thấp: công việc mới, dữ liệu chưa rõ hoặc cần hỗ trợ bên ngoài.

Độ tin cậy giúp người lập kế hoạch biết nơi cần thêm khảo sát hoặc dự phòng.

### Cập nhật ước lượng khi có bằng chứng mới

Sau mỗi chu kỳ, so sánh dự kiến với thực tế theo từng nhóm công việc. Ghi nguyên nhân sai lệch:

- Dataset lớn hơn giả định.
- Provisioning chậm do quota.
- Test flaky làm tăng retry.
- Thiếu quyền hoặc chờ nhóm khác.
- Cleanup mất nhiều thời gian.
- Lỗi cần tái hiện qua nhiều môi trường.
- Sửa helper ảnh hưởng nhiều suite hơn dự kiến.

Cập nhật mô hình cho lần sau. Không dùng sai lệch để quy trách nhiệm cá nhân; mục tiêu là làm kế hoạch sát thực tế hơn.

## 11. Phân bổ thời gian dự phòng và quản lý ưu tiên

### Dự phòng cho bất định

Một kế hoạch cần dự phòng cho:

- Môi trường không sẵn sàng.
- Dataset hoặc migration lỗi.
- Test flaky và lỗi không tái hiện.
- Nhà cung cấp hoặc nhóm phụ thuộc phản hồi chậm.
- Sửa test dùng chung.
- Cleanup thất bại.
- Thay đổi phạm vi do phát hiện rủi ro mới.

Dự phòng nên dựa trên lịch sử và mức bất định. Không dùng một tỷ lệ tùy ý cho mọi dự án. Khi dự phòng bị sử dụng, ghi rõ nguyên nhân và ảnh hưởng đến phạm vi hoặc mốc phát hành.

### Ưu tiên theo rủi ro và chi phí trì hoãn

Khi thời gian hoặc năng lực hạn chế, ưu tiên dựa trên:

- Mức nghiêm trọng nếu lỗi lọt.
- Khả năng xảy ra và mức phơi nhiễm.
- Độ khó phát hiện sau phát hành.
- Chi phí sửa muộn.
- Mức độ quan trọng của hành trình.
- Khả năng tái sử dụng bằng chứng.
- Thời gian và năng lực cần để kiểm tra.

Một kiểm tra bảo mật hoặc dữ liệu có rủi ro cao không nên bị đẩy xuống chỉ vì nó tốn thời gian. Có thể giảm chi phí bằng cách chuẩn bị sớm, chạy song song an toàn hoặc dùng phương pháp khác tạo bằng chứng tương đương.

### Quản lý công việc bị chặn

Nếu thiếu môi trường, quyền hoặc dữ liệu, ghi nhận:

- Điều kiện đang thiếu.
- Nhóm hoặc người có thể tháo gỡ.
- Thời điểm cần có.
- Công việc thay thế có thể làm trong lúc chờ.
- Tác động đến đường găng.
- Rủi ro nếu không hoàn tất.

Không ghi công việc bị chặn là đã hoàn thành. Nếu không thể thực hiện kiểm thử bắt buộc, cần báo rõ giới hạn bằng chứng và đưa ra quyết định theo thẩm quyền.

## 12. Ví dụ: dự trù nguồn lực cho một đợt hồi quy trước phát hành

Giả sử một bản phát hành có thay đổi ở thanh toán, quyền thành viên và schema đơn hàng. Nhóm dự kiến chạy unit, contract, integration, E2E và một phần hồi quy rộng.

### Phân rã công việc

| Nhóm việc | Công việc cụ thể | Đầu ra |
|---|---|---|
| Dữ liệu | Seed catalog, tạo tenant và tài khoản, dataset migration | Fixture có version và ID |
| Môi trường | Cấp runner, database, broker và payment sandbox | Environment sẵn sàng và health check |
| Thực thi | Unit, contract, integration và E2E | Test report và artifact |
| Điều tra | Phân loại fail, tái hiện và xác định owner | Lỗi có nguyên nhân và bằng chứng |
| Sửa test | Cập nhật fixture hoặc assertion, sửa flaky | Thay đổi đã xác minh |
| Cleanup | Dọn namespace, queue, giao dịch sandbox và artifact tạm | Registry sạch hoặc tài nguyên còn lại được ghi nhận |

### Ước lượng minh họa

Giả sử nhóm có dữ liệu lịch sử và đưa ra các ước lượng sau. Các con số chỉ minh họa cách lập kế hoạch, không phải chuẩn thời gian áp dụng cho mọi dự án.

| Công việc | Elapsed time dự kiến | Công sức dự kiến | Phụ thuộc chính |
|---|---:|---:|---|
| Chuẩn bị dữ liệu | 35–50 phút | 30–45 phút | Schema và seed |
| Provision môi trường | 20–35 phút | 10–20 phút | Quota runner và dịch vụ |
| Chạy test | 45–70 phút | 15–25 phút theo dõi | Môi trường sẵn sàng |
| Điều tra kết quả | 30–90 phút | 30–75 phút | Artifact và owner |
| Sửa test | 45–120 phút | 45–120 phút | Phân loại nguyên nhân |
| Xác minh sau sửa | 25–45 phút | 15–30 phút | Thay đổi đã review |
| Cleanup | 10–25 phút | 5–15 phút | Test đã kết thúc |

Không cộng thẳng mọi elapsed time nếu các công việc có thể chạy song song. Hãy lập lịch theo phụ thuộc: có thể chuẩn bị fixture trong khi runner được cấp phát, nhưng test chỉ bắt đầu sau khi cả hai đạt readiness. Điều tra một test fail có thể diễn ra song song với việc chạy phần suite không bị ảnh hưởng.

### Dự phòng và quyết định

Nếu lịch sử cho thấy E2E thanh toán thường có biến động, dành khoảng dự phòng riêng cho sandbox và đối soát. Nếu sửa fixture dùng chung có thể ảnh hưởng nhiều suite, dành thời gian review và chạy lại các test tiêu thụ fixture đó.

Khi thời gian thực tế vượt kế hoạch, nhóm xem xét nguyên nhân và ưu tiên theo rủi ro. Có thể tăng runner hoặc sửa quy trình setup nếu đó là nút thắt; không tự động bỏ kiểm thử quyền hoặc migration để giữ mốc.

## 13. Theo dõi tiến độ và điều chỉnh trong chu kỳ

### Bảng theo dõi nguồn lực

Một bảng theo dõi có thể có các trường:

~~~yaml
work_item: "Chuẩn bị dataset hồi quy đơn hàng"
owner: "Nhóm kiểm thử đơn hàng"
estimate:
  elapsed_min: 30
  elapsed_most_likely: 40
  elapsed_max: 60
  effort_hours: 0.75
dependencies:
  - "Migration schema 2026.11"
  - "Seed catalog v12"
status: "IN_PROGRESS"
actual:
  elapsed_minutes: null
  effort_hours: null
blocker: null
output: "Fixture version và registry ID"
risk_if_delayed: "Trễ E2E thanh toán và migration"
~~~

Đây là cấu trúc minh họa. Dùng tên trạng thái, trường và công cụ quản lý thực tế của nhóm. Không điền số liệu giả định vào báo cáo vận hành như dữ liệu thực.

### Theo dõi sai lệch

So sánh kế hoạch và thực tế theo nhóm:

- Dữ liệu mất bao lâu để tạo, reset và cleanup?
- Môi trường chờ bao lâu trước readiness?
- Test chạy có đúng baseline không?
- Điều tra mất bao lâu đến khi phân loại?
- Sửa test có ảnh hưởng rộng hơn dự kiến không?
- Bao nhiêu thời gian dự phòng đã dùng?
- Có tài nguyên hoặc artifact còn sót không?

Sai lệch lớn cần có nguyên nhân và hành động. Ví dụ, cleanup tăng từ 10 lên 40 phút có thể do queue consumer còn chạy, registry thiếu tài nguyên hoặc API nhà cung cấp bị giới hạn tốc độ.

### Cập nhật dự báo khi phạm vi thay đổi

Khi phát hiện thêm rủi ro, lỗi hoặc thay đổi phạm vi:

1. Xác định công việc mới.
2. Đánh giá phụ thuộc và mức ưu tiên.
3. Ước lượng elapsed time, effort và tài nguyên.
4. Xác định phần nào có thể chạy song song.
5. Cập nhật đường găng và dự phòng.
6. Thông báo tác động đến mốc và phạm vi.
7. Ghi quyết định nếu cần điều chỉnh phạm vi.

Không giữ nguyên kế hoạch cũ khi đầu vào đã thay đổi đáng kể.

## 14. Những sai lầm thường gặp

- **Chỉ tính thời gian chạy test:** bỏ qua dữ liệu, provisioning, điều tra và cleanup.
- **Đồng nhất elapsed time với effort:** dự báo sai năng lực nhân sự và lịch.
- **Dùng một lần chạy nhanh nhất làm baseline:** đánh giá thấp biến động thực tế.
- **Cộng thời gian song song như tuần tự:** làm lịch dài hơn thực tế hoặc phân bổ sai người.
- **Giả định concurrency vô hạn:** bỏ qua quota database, runner và sandbox.
- **Không tính thời gian điều tra:** lỗi fail tích tụ mà không có người xử lý.
- **Coi sửa test là hoàn tất khi code đã đổi:** thiếu thời gian xác minh sau sửa.
- **Không tính cleanup và dữ liệu còn sót:** môi trường trở nên bẩn và tốn tài nguyên.
- **Ước lượng chính xác giả:** che giấu bất định và phụ thuộc.
- **Không cập nhật khi scope đổi:** kế hoạch nhanh chóng mất hiệu lực.
- **Cắt test rủi ro cao để giữ deadline:** làm suy giảm bằng chứng phát hành.
- **Không tính thời gian chờ chuyên gia:** công việc bị chặn dù tổng công sức kỹ thuật nhỏ.
- **Không đo sai lệch sau chu kỳ:** lặp lại cùng một lỗi lập kế hoạch.
- **Không có owner cho công việc nền:** dữ liệu, môi trường và helper lỗi thời.

## 15. Đầu ra cần có trước khi chốt kế hoạch nguồn lực kiểm thử

Một kế hoạch đủ dùng nên có:

1. **Phạm vi kiểm thử:** yêu cầu, rủi ro, module, hành trình và cấp test.
2. **Danh mục công việc:** dữ liệu, môi trường, thực thi, điều tra, sửa, xác minh và cleanup.
3. **Đầu ra và tiêu chí hoàn tất:** bằng chứng cần bàn giao cho từng work item.
4. **Ước lượng thời gian:** elapsed time, effort và khoảng bất định.
5. **Kế hoạch dữ liệu:** seed, fixture, snapshot, reset, cleanup và retention.
6. **Kế hoạch môi trường:** loại môi trường, provisioning, readiness, quota và concurrency.
7. **Ngân sách thực thi:** thời gian suite, shard, retry và tài nguyên máy chạy.
8. **Ngân sách điều tra:** phân loại, tái hiện, hỗ trợ phụ thuộc và xử lý lỗi.
9. **Ngân sách sửa:** phạm vi ảnh hưởng, review và chạy xác minh sau sửa.
10. **Năng lực nhân sự:** owner, người hỗ trợ, kỹ năng và thời gian khả dụng.
11. **Dự phòng và ưu tiên:** rủi ro, phụ thuộc, công việc bị chặn và điều kiện mở rộng.
12. **Theo dõi thực tế:** baseline, sai lệch, chi phí và hành động cải thiện.

Trước khi chốt, hãy rà soát:

- Có tính đủ dữ liệu, môi trường, chạy test, điều tra, sửa, xác minh và cleanup không?
- Elapsed time và effort có được tách riêng không?
- Ước lượng có nguồn lịch sử, giả định và độ tin cậy không?
- Công việc song song và đường găng có được thể hiện đúng không?
- Năng lực runner, database, sandbox và lưu trữ có đáp ứng tải đỉnh không?
- Có thời gian cho lỗi flaky, tái hiện và hỗ trợ từ nhóm phụ thuộc không?
- Sửa test có bao gồm review và regression sau sửa không?
- Dự phòng có dựa trên bất định và rủi ro không?
- Khi thiếu nguồn lực, quyết định ưu tiên có giữ được kiểm tra rủi ro cao không?
- Có người sở hữu và đầu ra xác minh cho mỗi công việc không?
- Có đo sai lệch và cập nhật ước lượng sau chu kỳ không?

Tính thời gian cho dữ liệu, môi trường, điều tra và sửa bộ kiểm thử giúp kế hoạch xác thực phản ánh toàn bộ công việc cần thiết để tạo ra bằng chứng đáng tin cậy. Khi nhóm tách thời gian chờ khỏi công sức, dùng dữ liệu lịch sử, dự trù bất định và theo dõi năng lực thực tế, các mốc kiểm thử trở nên khả thi hơn và quyết định về phạm vi minh bạch hơn. Hãy cập nhật ước lượng sau mỗi chu kỳ để kế hoạch tiếp theo sát với cách hệ thống và bộ kiểm thử đang vận hành.

