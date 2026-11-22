# Thiết kế cấp phát, kiểm tra sẵn sàng và thu hồi môi trường

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), chất lượng bằng chứng phụ thuộc nhiều vào môi trường nơi kiểm thử được thực hiện. Một bộ test tốt vẫn có thể cho kết quả sai lệch nếu phiên bản dịch vụ không đồng nhất, cấu hình khác mục tiêu, dữ liệu dùng chung bị thay đổi hoặc phụ thuộc chưa sẵn sàng. Vì vậy, môi trường kiểm thử cần được quản lý như một tài nguyên có vòng đời rõ ràng: **cấp phát, cấu hình, kiểm tra sẵn sàng, sử dụng, thu hồi và xác nhận đã dọn sạch**.

Thiết kế vòng đời môi trường giúp nhóm tái lập điều kiện kiểm thử, giảm xung đột giữa các lần chạy, phát hiện sớm vấn đề cấu hình và tránh để tài nguyên thử nghiệm tồn tại ngoài nhu cầu. Bài học này trình bày cách xác định nhu cầu môi trường, lựa chọn mô hình cấp phát, tự động hóa bằng cấu hình có thể quản lý, kiểm tra readiness trước khi chạy test, cô lập dữ liệu và bí mật, xử lý lỗi trong vòng đời và thu hồi tài nguyên an toàn.

## 1. Hiểu vòng đời của môi trường kiểm thử

### 1.1. Môi trường kiểm thử là gì?

Môi trường kiểm thử là tập hợp tài nguyên và cấu hình cần thiết để thực thi một nhóm kiểm tra trong điều kiện xác định. Nó có thể gồm:

- Ứng dụng và các service cần kiểm tra.
- Cơ sở dữ liệu, cache, message broker và object storage.
- API gateway, DNS, mạng, chứng thư và quy tắc truy cập.
- Dịch vụ bên ngoài hoặc sandbox của nhà cung cấp.
- Cấu hình, feature flag, biến môi trường và secret.
- Dữ liệu kiểm thử, tài khoản và quyền.
- Công cụ quan sát như log, metrics, trace và dashboard.
- Runner hoặc máy thực thi test, trình duyệt và thiết bị.

Một môi trường không chỉ là một URL. Hai môi trường có cùng URL dạng ứng dụng nhưng khác phiên bản database, cấu hình timeout hoặc feature flag có thể tạo ra kết quả kiểm thử khác nhau.

### 1.2. Các giai đoạn trong vòng đời

Một vòng đời cơ bản có thể chia thành sáu giai đoạn:

1. **Cấp phát (provision):** tạo hoặc đặt trước compute, network, database, service và các tài nguyên cần thiết.
2. **Cấu hình (configure):** áp dụng phiên bản, biến cấu hình, quyền, secret, feature flag và dữ liệu khởi tạo.
3. **Kiểm tra sẵn sàng (readiness):** xác minh các thành phần cần thiết đã hoạt động và có thể phục vụ loại test dự kiến.
4. **Sử dụng (use):** chạy kiểm thử, thu thập kết quả, log và thông tin phiên bản.
5. **Thu hồi (teardown):** dừng service, xóa tài nguyên tạm, thu hồi credential và dọn dữ liệu.
6. **Xác nhận sau thu hồi (verify cleanup):** kiểm tra tài nguyên đã được xóa hoặc đưa về trạng thái được quy định.

Không nên xem cấp phát thành công là đồng nghĩa môi trường đã sẵn sàng. Một container có thể đang chạy nhưng ứng dụng chưa hoàn tất migration; một endpoint có thể trả HTTP 200 nhưng phụ thuộc quan trọng vẫn chưa kết nối được.

### 1.3. Trạng thái vòng đời cần được biểu diễn rõ

Một môi trường nên có trạng thái dễ quan sát, ví dụ:

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| REQUESTED | Có yêu cầu cấp phát và thông tin phạm vi. | Xác thực yêu cầu, kiểm tra quota. |
| PROVISIONING | Tài nguyên đang được tạo. | Theo dõi kết quả và timeout. |
| CONFIGURING | Đang cài phiên bản, cấu hình và dữ liệu ban đầu. | Kiểm tra cấu hình và quyền. |
| VERIFYING | Đang chạy readiness checks. | Chỉ chuyển tiếp khi các điều kiện bắt buộc đạt. |
| READY | Môi trường đủ điều kiện cho nhóm test được chỉ định. | Cấp thông tin truy cập cho test runner. |
| IN_USE | Có test run đang sử dụng. | Theo dõi sức khỏe và thời hạn. |
| TEARING_DOWN | Đang thu hồi tài nguyên. | Hoàn tất cleanup và thu hồi credential. |
| CLEANED | Tài nguyên tạm đã được dọn và xác minh. | Lưu báo cáo vòng đời. |
| FAILED / QUARANTINED | Cấp phát, readiness hoặc cleanup gặp lỗi cần xử lý. | Điều tra, cách ly hoặc thu hồi theo chính sách. |

Trạng thái giúp pipeline biết có thể chạy test hay cần dừng. Nó cũng giúp phân biệt lỗi sản phẩm với lỗi môi trường. Ví dụ, nếu readiness thất bại do database không sẵn sàng, không nên ghi nhận toàn bộ test suite là lỗi chức năng của ứng dụng.

## 2. Xác định nhu cầu trước khi cấp phát

### 2.1. Bắt đầu từ mục tiêu kiểm thử

Không phải mọi bộ test cần một môi trường hoàn chỉnh giống production. Hãy xác định:

- Thành phần nào cần chạy thật?
- Phụ thuộc nào có thể được thay bằng stub, fake hoặc sandbox?
- Mức độ giống production cần thiết đến đâu?
- Cần bao nhiêu test run đồng thời?
- Mỗi môi trường cần tồn tại trong bao lâu?
- Dữ liệu và tài khoản nào cần được chuẩn bị?
- Những kiểm tra nào có thể chạy song song?
- Có yêu cầu về vị trí dữ liệu, quyền truy cập hoặc phân tách mạng không?

Ví dụ, unit test có thể chỉ cần runtime và test double. Integration test persistence cần database tương thích. E2E test cho checkout có thể cần UI, API, database, payment sandbox và message broker. Cấp phát toàn bộ hệ thống cho một bộ unit test sẽ lãng phí tài nguyên và làm tăng thời gian pipeline.

### 2.2. Chọn mức độ đại diện của môi trường

Môi trường cần đại diện cho rủi ro đang kiểm tra. Không nhất thiết phải giống production ở mọi chi tiết, nhưng khác biệt quan trọng phải được biết và ghi nhận.

Các chiều cần xem xét:

- Phiên bản runtime, framework, database và broker.
- Hệ điều hành, kiến trúc CPU và cấu hình container.
- Topology mạng, DNS, TLS và routing.
- Quyền service account và chính sách truy cập.
- Dung lượng, giới hạn tài nguyên và cấu hình autoscaling.
- Feature flag, timeout, retry và rate limit.
- Dữ liệu, locale, timezone và cấu hình vùng.
- Cơ chế backup, logging, metrics và tracing.

Nếu kiểm thử một migration, phiên bản database và schema ban đầu có thể quyết định kết quả. Nếu kiểm thử hiệu năng, CPU, memory, network và dữ liệu cần đủ đại diện. Nếu kiểm thử quyền, danh tính và policy phải tương ứng với ranh giới đang được xác minh.

### 2.3. Chọn mô hình môi trường theo nhu cầu

| Mô hình | Đặc điểm | Phù hợp khi | Hạn chế |
|---|---|---|---|
| Local | Chạy trên máy phát triển, thường dùng container hoặc service cục bộ. | Phát triển nhanh, unit và một số integration test. | Khác biệt máy cá nhân; khó đại diện hệ thống phân tán đầy đủ. |
| Shared test | Nhiều người hoặc pipeline dùng chung một môi trường. | Test thủ công, tích hợp chung hoặc môi trường có chi phí cao. | Dễ xung đột dữ liệu, cấu hình và thời điểm sử dụng. |
| Dedicated persistent | Môi trường riêng tồn tại lâu, được cập nhật theo lịch. | Kiểm thử tích hợp dài hạn, exploratory testing hoặc staging. | Tốn chi phí và có nguy cơ drift cấu hình. |
| Ephemeral | Cấp phát riêng cho branch, pull request hoặc test run rồi thu hồi. | CI, kiểm tra thay đổi độc lập và test song song. | Cần automation tốt; phụ thuộc ngoài có thể khó tạo mới. |
| Sandbox provider | Dùng môi trường thử nghiệm của nhà cung cấp. | Kiểm tra tích hợp bên ngoài mà không tạo giao dịch thật. | Có thể giới hạn dữ liệu, tải, độ ổn định hoặc tính năng. |

Có thể kết hợp nhiều mô hình. Ví dụ, service và database được tạo ephemeral, trong khi sandbox của nhà cung cấp được dùng chung nhưng có tài khoản hoặc namespace riêng cho mỗi test run.

## 3. Thiết kế cấp phát có thể tái lập

### 3.1. Dùng cấu hình dưới dạng mã

Infrastructure as Code (IaC) mô tả tài nguyên và cấu hình môi trường bằng file có thể quản lý phiên bản. Cách làm này giúp tạo lại môi trường với cùng đầu vào, review thay đổi và phát hiện khác biệt giữa các lần cấp phát.

Một mô tả môi trường nên xác định:

- Loại tài nguyên và kích thước.
- Phiên bản image hoặc artifact.
- Mạng, subnet, DNS và policy.
- Cấu hình database, broker và storage.
- Quyền service account.
- Tham số ứng dụng và feature flag.
- Tag hoặc nhãn sở hữu.
- TTL và chính sách thu hồi.

Không đưa secret trực tiếp vào file IaC hoặc repository. Cấu hình chỉ nên tham chiếu đến secret store hoặc cơ chế cấp credential phù hợp.

### 3.2. Định danh môi trường và tài nguyên

Mỗi môi trường tạm nên có định danh duy nhất, ví dụ theo repository, branch hoặc pipeline run. Dùng định danh này làm nhãn cho các tài nguyên để có thể truy vết và thu hồi.

Ví dụ:

~~~text
project: checkout
environment: pr-4821
owner: ci-pipeline
commit: 8f31c2a
expiresAt: 2026-11-16T18:00:00+07:00
~~~

Nhãn giúp trả lời tài nguyên thuộc về ai, được tạo cho mục đích gì và khi nào cần dọn. Không nên chỉ dựa vào tên ngẫu nhiên không có thông tin chủ sở hữu.

### 3.3. Khóa phiên bản và artifact

Môi trường cần triển khai đúng artifact đang được kiểm tra. Hãy lưu:

- Commit hoặc revision nguồn.
- Build ID.
- Image digest hoặc checksum artifact.
- Phiên bản schema và migration.
- Phiên bản các service phụ thuộc.
- Cấu hình và feature flag có ảnh hưởng đến kết quả.

Dùng tag có thể thay đổi như latest có thể khiến hai lần cấp phát cùng một cấu hình nhưng chạy hai phiên bản khác nhau. Ưu tiên định danh bất biến như digest hoặc version đã khóa.

Nếu một service được cập nhật trong khi test đang chạy, kết quả có thể không còn đại diện cho một phiên bản nhất quán. Pipeline cần khóa hoặc ghi nhận chính xác phiên bản từng thành phần.

### 3.4. Cấp phát theo thứ tự phụ thuộc

Một thứ tự triển khai điển hình:

1. Network, DNS, policy và secret access.
2. Database, broker, cache và storage.
3. Migration hoặc schema initialization.
4. Service nền và API.
5. Frontend hoặc client cần kiểm tra.
6. Test data, tài khoản và feature flag.
7. Readiness checks.

Thứ tự cụ thể phụ thuộc kiến trúc. Nếu ứng dụng khởi động trước database, readiness cần chờ kết nối và migration hoàn tất thay vì chỉ chờ process tồn tại.

### 3.5. Xử lý cấp phát lặp và thất bại một phần

Pipeline có thể bị chạy lại sau timeout hoặc bị hủy giữa chừng. Quy trình cấp phát nên có tính idempotent hoặc có khả năng nhận diện tài nguyên đã tạo.

Các nguyên tắc:

- Tạo tài nguyên theo định danh run thay vì tạo trùng mỗi lần retry.
- Lưu trạng thái từng bước cấp phát.
- Có timeout và retry có giới hạn.
- Khi một bước thất bại, xác định tài nguyên nào đã được tạo.
- Dọn tài nguyên một phần theo cùng phạm vi sở hữu.
- Không đánh dấu READY khi còn bước bắt buộc chưa hoàn tất.

Ví dụ, nếu database đã tạo nhưng deployment ứng dụng thất bại, pipeline cần dọn database và network tạm hoặc chuyển môi trường sang FAILED để cleanup worker xử lý. Không để tài nguyên mồ côi vì tiến trình cấp phát dừng giữa chừng.

## 4. Cấu hình môi trường và quản lý bí mật

### 4.1. Tách cấu hình khỏi mã nguồn

Cùng một artifact có thể được triển khai ở nhiều môi trường với cấu hình khác nhau. Hãy tách các tham số như endpoint, timeout, retry, feature flag và giới hạn tài nguyên khỏi mã nguồn, đồng thời quản lý thay đổi có review.

Cấu hình cần có:

- Giá trị hoặc nguồn lấy giá trị.
- Môi trường áp dụng.
- Chủ sở hữu.
- Mặc định an toàn.
- Giới hạn hợp lệ.
- Cách xác minh sau khi áp dụng.

Tránh cấu hình ngầm phụ thuộc vào máy người chạy hoặc biến môi trường không được tài liệu hóa.

### 4.2. Quản lý secret an toàn

Credential cho database, API hoặc sandbox cần được cấp qua secret manager hoặc cơ chế identity phù hợp. Nên:

- Cấp quyền tối thiểu cho test runner.
- Dùng credential ngắn hạn khi có thể.
- Tách secret giữa local, CI, staging và production.
- Không ghi secret vào log, artifact, screenshot hoặc báo cáo test.
- Thu hồi credential khi môi trường bị thu hồi.
- Không dùng lại mật khẩu hoặc khóa của người dùng thật.

Khi môi trường ephemeral được tạo, secret chỉ nên được cấp cho service hoặc runner cần dùng. Không chuyển secret cho mọi container chỉ vì chúng cùng thuộc một môi trường.

### 4.3. Cô lập dữ liệu và danh tính

Dữ liệu kiểm thử nên được tạo từ fixture hoặc dữ liệu giả có thể tái lập. Mỗi run cần namespace, tenant hoặc tài khoản riêng nếu test có thể chạy song song.

Nếu cần dữ liệu gần production, hãy sử dụng bản sao đã được xử lý dữ liệu nhạy cảm và được phê duyệt. Không mặc định rằng staging là nơi có thể sao chép nguyên dữ liệu production.

Cần xác định:

- Ai sở hữu dữ liệu.
- Test nào có thể đọc hoặc sửa.
- Dữ liệu được tạo lúc nào và dọn bằng cách nào.
- Có cần giữ lại bằng chứng sau test không.
- Dữ liệu có được phép xuất khỏi môi trường không.

### 4.4. Kiểm tra drift cấu hình

Configuration drift xảy ra khi môi trường thay đổi khỏi cấu hình được quản lý, ví dụ người vận hành sửa thủ công một biến hoặc cập nhật service mà không cập nhật IaC.

Để phát hiện drift:

- So sánh trạng thái thực tế với cấu hình mong đợi.
- Ghi nhận thay đổi thủ công và người thực hiện.
- Định kỳ tái áp dụng cấu hình chuẩn khi được phép.
- Kiểm tra phiên bản và feature flag trước khi chạy test.
- Cách ly môi trường khi phát hiện khác biệt có thể ảnh hưởng kết quả.

Không tự động ghi đè thay đổi vận hành quan trọng nếu chưa hiểu tác động. Hãy xác định chủ sở hữu và quy trình xử lý drift.

## 5. Kiểm tra sẵn sàng trước khi chạy test

### 5.1. Phân biệt liveness và readiness

Hai khái niệm này trả lời câu hỏi khác nhau:

- **Liveness:** tiến trình có còn sống và có thể tiếp tục chạy không?
- **Readiness:** thành phần đã sẵn sàng nhận loại lưu lượng hoặc thực hiện loại công việc dự kiến chưa?

Một service có thể liveness thành công nhưng readiness thất bại vì chưa kết nối database, chưa nạp cấu hình hoặc chưa hoàn tất khởi tạo. Pipeline chỉ nên chạy test phụ thuộc vào service khi điều kiện readiness tương ứng đạt.

### 5.2. Readiness cần phản ánh mục tiêu test

Không nên dùng một endpoint health chung cho mọi loại kiểm thử. Mỗi suite cần các điều kiện sẵn sàng phù hợp.

Ví dụ:

| Loại test | Điều kiện readiness cần xem xét |
|---|---|
| Unit test | Runtime, dependency cục bộ và fixture đã sẵn sàng. |
| Integration test database | Database chấp nhận kết nối, schema đúng phiên bản và tài khoản có quyền cần thiết. |
| Contract/API test | Service đúng phiên bản, endpoint có thể truy cập và cấu hình xác thực hợp lệ. |
| Message workflow | Broker sẵn sàng, topic/queue tồn tại, consumer đã đăng ký và có thể xử lý. |
| UI/E2E test | Frontend và backend sẵn sàng, tài khoản test hợp lệ, dữ liệu ban đầu đã được tạo. |
| Performance test | Môi trường đủ tài nguyên, tải nền được kiểm soát và dữ liệu có quy mô đại diện. |

Một service trả 200 không đủ chứng minh luồng bất đồng bộ đã sẵn sàng. Với message workflow, có thể cần kiểm tra consumer đã đăng ký hoặc thực hiện một probe an toàn.

### 5.3. Kiểm tra phụ thuộc theo chiều sâu cần thiết

Readiness có thể gồm nhiều lớp:

1. Process đang chạy.
2. Endpoint nội bộ có thể truy cập.
3. Cấu hình đã được nạp và hợp lệ.
4. Phụ thuộc bắt buộc kết nối được.
5. Schema hoặc migration ở phiên bản mong đợi.
6. Tài khoản và quyền hoạt động.
7. Tác vụ khởi tạo đã hoàn tất.
8. Một probe nghiệp vụ an toàn có thể thực hiện.

Không nên làm health check quá nặng hoặc tạo tác dụng phụ. Probe cần đọc hoặc thao tác trên tài nguyên thử nghiệm có thể dọn; không tạo giao dịch thật hoặc gửi thông báo ra ngoài.

### 5.4. Chờ readiness có giới hạn

Tránh dùng một khoảng sleep cố định rồi giả định môi trường đã sẵn sàng. Thay vào đó:

- Poll điều kiện readiness theo khoảng thời gian hợp lý.
- Có timeout tổng thể.
- Dùng backoff khi phù hợp.
- Ghi lại lần kiểm tra và nguyên nhân thất bại.
- Dừng sớm nếu phát hiện lỗi cấu hình không thể tự phục hồi.
- Chỉ retry những lỗi tạm thời đã được xác định.

Ví dụ thuật toán tổng quát:

~~~text
deadline = now + readiness_timeout

while now < deadline:
    result = check_required_dependencies()

    if result.ready:
        mark_environment_ready()
        continue_tests()

    if result.permanent_failure:
        mark_environment_failed()
        stop_pipeline()

    wait_with_bounded_backoff()

mark_environment_failed_due_to_timeout()
stop_pipeline()
~~~

Timeout phải dựa trên đặc tính khởi động và yêu cầu của hệ thống. Không tăng timeout vô hạn để che giấu service bị lỗi hoặc dependency không thể kết nối.

### 5.5. Ghi lại readiness evidence

Khi readiness đạt hoặc thất bại, lưu bằng chứng đủ để điều tra:

- Thời điểm bắt đầu và kết thúc.
- Phiên bản service và artifact.
- Các dependency đã kiểm tra.
- Kết quả từng probe.
- Cấu hình liên quan đã được xác minh.
- Timeout, retry và lỗi cuối cùng.
- Correlation ID hoặc trace ID nếu có.

Readiness evidence giúp phân biệt test chưa chạy vì môi trường không sẵn sàng với test chạy và phát hiện lỗi sản phẩm.

## 6. Chuẩn bị dữ liệu và xác minh tính cô lập

### 6.1. Dữ liệu phải có trạng thái xác định

Trước khi chạy test, dữ liệu nền cần được chuẩn bị theo cách tái lập. Có thể dùng:

- Migration và seed data được quản lý phiên bản.
- Fixture API có schema và giới hạn.
- Snapshot dữ liệu thử nghiệm đã được xử lý.
- Factory tạo đối tượng theo test run.
- Tập dữ liệu bất biến dùng chung nếu chỉ đọc.

Tránh phụ thuộc vào dữ liệu được tạo thủ công từ những lần chạy trước. Một test cần biết rõ trạng thái ban đầu thay vì giả định môi trường vẫn còn dữ liệu phù hợp.

### 6.2. Cô lập giữa các test run

Khi nhiều test chạy song song, dữ liệu và tài nguyên có thể xung đột. Các biện pháp thường dùng:

- Namespace theo pipeline hoặc test run.
- Tài khoản riêng cho từng worker.
- Database/schema riêng hoặc transaction rollback khi phù hợp.
- Queue và topic có định danh theo run.
- Object storage prefix riêng.
- Khóa phân tán hoặc giới hạn song song cho tài nguyên không thể chia sẻ an toàn.

Nếu hai test cập nhật cùng một tài khoản hoặc cùng một đơn hàng, kết quả có thể phụ thuộc thứ tự chạy. Cần cô lập hoặc thiết kế test không chia sẻ trạng thái có thể thay đổi.

### 6.3. Kiểm tra tính nhất quán và khả năng dọn

Sau khi setup, xác minh dữ liệu đã ở trạng thái mong đợi trước khi bắt đầu test. Với xử lý bất đồng bộ, chờ điều kiện trạng thái thay vì giả định seed hoặc message đã được xử lý ngay.

Ghi lại ID dữ liệu tạo ra để cleanup chính xác. Nếu test thất bại giữa chừng, cleanup vẫn cần chạy theo cơ chế cuối cùng như pipeline finalizer hoặc TTL.

### 6.4. Không dùng dữ liệu thật không cần thiết

Dữ liệu thật có thể chứa thông tin cá nhân, bí mật kinh doanh hoặc thông tin tài chính. Ưu tiên dữ liệu tổng hợp hoặc đã ẩn danh. Nếu cần bản sao dữ liệu thực tế để kiểm tra hiệu năng hoặc tương thích, phải có quyền, quy trình xử lý và giới hạn truy cập phù hợp.

Không đưa dữ liệu nhạy cảm vào screenshot, log hoặc artifact của pipeline. Kiểm tra cả bản sao lưu, file export và dữ liệu tạm vì chúng có thể tồn tại sau khi test kết thúc.

## 7. Quản lý tài nguyên trong khi test chạy

### 7.1. Theo dõi trạng thái và sức khỏe

Trong thời gian test, cần theo dõi:

- Service có còn sẵn sàng không.
- CPU, memory, disk và network có đạt giới hạn không.
- Database connection pool và số kết nối.
- Queue depth, consumer lag và retry.
- Tỷ lệ lỗi, latency và timeout.
- Dung lượng storage và log.
- Trạng thái các phụ thuộc bên ngoài.

Nếu môi trường mất readiness trong lúc test, cần ghi nhận thời điểm và phạm vi ảnh hưởng. Không nên gộp lỗi môi trường vào lỗi sản phẩm mà không có phân loại.

### 7.2. Giới hạn tài nguyên và chống cạnh tranh

Môi trường dùng chung hoặc ephemeral có thể bị quá tải khi nhiều pipeline chạy đồng thời. Hãy xác định quota cho:

- CPU, memory và số replica.
- Database instance, connection và storage.
- Queue, topic và số consumer.
- Test runner và browser session.
- API rate limit và sandbox account.
- Số môi trường tồn tại đồng thời.

Nếu vượt quota, pipeline nên chờ hoặc từ chối cấp phát có thông báo rõ, thay vì tạo một môi trường thiếu tài nguyên rồi chạy test cho kết quả không đáng tin.

### 7.3. Xử lý môi trường không ổn định

Khi readiness hoặc sức khỏe suy giảm:

1. Ghi lại trạng thái và timestamp.
2. Xác định test nào bị ảnh hưởng.
3. Kiểm tra dependency, tài nguyên và thay đổi cấu hình.
4. Phân loại lỗi là môi trường, hạ tầng hay sản phẩm nếu đủ bằng chứng.
5. Cách ly môi trường nếu tiếp tục chạy có thể tạo kết quả sai.
6. Khôi phục hoặc cấp phát lại theo quy trình.
7. Chạy lại các test bị ảnh hưởng sau khi readiness được xác nhận.

Không tự động retry mọi test thất bại. Nếu lỗi là assertion sai ổn định, retry có thể che giấu regression. Retry chỉ phù hợp với lỗi tạm thời đã được xác định và cần được ghi nhận.

## 8. Thu hồi môi trường an toàn và đầy đủ

### 8.1. Điều kiện kích hoạt thu hồi

Môi trường nên được thu hồi khi:

- Test run hoàn tất.
- Pull request hoặc branch bị đóng.
- TTL hết hạn.
- Người sở hữu yêu cầu dừng.
- Cấp phát thất bại và không thể tiếp tục.
- Môi trường bị cách ly vì lỗi hoặc rủi ro.
- Quota cần được giải phóng.

Cần có chính sách cho cả đường thành công lẫn đường thất bại. Pipeline bị hủy, runner mất kết nối hoặc tiến trình bị timeout không được khiến tài nguyên tồn tại vô thời hạn.

### 8.2. Thứ tự thu hồi

Một trình tự tham khảo:

1. Ngừng nhận test mới và đánh dấu môi trường đang teardown.
2. Chờ hoặc dừng test runner theo chính sách.
3. Thu thập báo cáo, log và artifact cần giữ.
4. Thu hồi token, credential và quyền tạm.
5. Dừng job, worker hoặc service tạm.
6. Xóa fixture, database, queue, storage và network tạm theo thứ tự phụ thuộc.
7. Xóa compute và tài nguyên nền.
8. Xác minh không còn tài nguyên thuộc môi trường.
9. Ghi báo cáo cleanup và trạng thái cuối.

Thứ tự thực tế cần bảo đảm bằng chứng cần thiết được lưu trước khi xóa. Ví dụ, nếu cần log để điều tra, hãy xuất log đã lọc dữ liệu nhạy cảm trước khi xóa môi trường.

### 8.3. Thu hồi theo nhãn và quyền sở hữu

Chỉ xóa tài nguyên có nhãn và bằng chứng thuộc môi trường cần thu hồi. Không dùng lệnh xóa rộng theo tên gần giống hoặc theo toàn bộ project nếu nhiều nhóm chia sẻ project đó.

Một quy trình cleanup nên xác minh:

- Environment ID khớp yêu cầu.
- Owner và testRunId khớp.
- Tài nguyên nằm trong allowlist đã tạo.
- Không có tài nguyên dùng chung bị tham chiếu.
- Caller có quyền xóa đúng phạm vi.

Nếu không xác định được quyền sở hữu, hãy cách ly và yêu cầu xử lý theo quy trình thay vì xóa đoán.

### 8.4. Thu hồi credential và secret

Khi môi trường kết thúc:

- Thu hồi token ngắn hạn nếu vẫn còn hiệu lực.
- Xóa hoặc vô hiệu hóa service account tạm.
- Thu hồi certificate hoặc credential riêng của run.
- Xóa secret tạm trong phạm vi cho phép.
- Xác minh runner không còn giữ credential trong workspace hoặc artifact.
- Kiểm tra log và báo cáo không chứa secret.

Không nên chỉ dựa vào TTL của token nếu môi trường có thể tồn tại lâu hơn dự kiến hoặc token có quyền cao.

### 8.5. Xác nhận cleanup

Cleanup thành công cần có bằng chứng. Có thể xác minh:

- Compute và container đã dừng/xóa.
- Database hoặc schema tạm đã được xóa hoặc reset đúng chính sách.
- Queue, topic, bucket prefix và fixture đã được dọn.
- Network, IP, load balancer hoặc volume tạm đã được thu hồi.
- Token và quyền tạm không còn hiệu lực.
- Không còn tài nguyên mang nhãn environment ID.
- Chi phí và quota được giải phóng theo hệ thống quản lý.

Một lệnh teardown trả exit code 0 chưa chắc đã chứng minh mọi tài nguyên đã biến mất. Với tài nguyên quan trọng hoặc có chi phí cao, cần truy vấn trạng thái thực tế sau cleanup.

### 8.6. Xử lý cleanup thất bại

Nếu cleanup thất bại:

- Đánh dấu môi trường CLEANUP_FAILED hoặc QUARANTINED.
- Lưu danh sách tài nguyên còn lại và lỗi cụ thể.
- Tạo tác vụ retry có giới hạn hoặc chuyển cho người phụ trách.
- Giữ nhãn owner, environment ID và thời điểm hết hạn.
- Thu hồi credential trước nếu có thể thực hiện an toàn.
- Cảnh báo khi tài nguyên vượt thời hạn hoặc quota.
- Không đánh dấu CLEANED cho đến khi đã xác minh.

Một bộ dọn dẹp định kỳ có thể tìm tài nguyên hết TTL, nhưng phải dựa trên nhãn sở hữu và chính sách đã xác định. Không xóa tài nguyên không rõ chủ sở hữu chỉ vì nó cũ.

## 9. Tự động hóa vòng đời trong CI/CD

### 9.1. Đưa cấp phát và readiness vào pipeline

Một pipeline có thể có các giai đoạn:

~~~text
Validate request and quota
        |
Provision infrastructure
        |
Deploy pinned artifacts
        |
Apply configuration and secrets
        |
Initialize schema and test data
        |
Run readiness checks
        |
Execute test suites
        |
Collect evidence
        |
Teardown environment
        |
Verify cleanup
~~~

Nếu cấp phát hoặc readiness thất bại, pipeline cần dừng các suite phụ thuộc và chuyển sang cleanup. Không để bước teardown chỉ chạy khi toàn bộ pipeline thành công.

### 9.2. Dùng finalizer hoặc cơ chế cleanup luôn chạy

Thiết kế pipeline cần có một bước cuối được thực thi cả khi test fail, timeout hoặc bị hủy nếu nền tảng hỗ trợ. Có thể dùng job cleanup độc lập theo environment ID để không phụ thuộc vào runner ban đầu còn sống.

Nếu cleanup chạy trong cùng job, cần bảo đảm tín hiệu hủy không bỏ qua thao tác thu hồi credential và tài nguyên. Một TTL và cleanup controller định kỳ là lớp dự phòng cho các trường hợp runner biến mất.

### 9.3. Phân loại kết quả pipeline

Nên phân biệt:

- Provisioning failure.
- Configuration failure.
- Readiness timeout.
- Test assertion failure.
- Environment instability.
- Test runner failure.
- Teardown failure.
- Cleanup verification failure.

Việc phân loại giúp nhóm không kết luận sai rằng ứng dụng lỗi khi thực tế môi trường chưa sẵn sàng. Nó cũng giúp theo dõi chất lượng hạ tầng kiểm thử như một phần của chiến lược xác thực.

### 9.4. Gắn bằng chứng với đúng môi trường và phiên bản

Mỗi báo cáo test nên liên kết với:

- Environment ID.
- Commit/build/image digest.
- Cấu hình và feature flag quan trọng.
- Phiên bản database/schema.
- Dữ liệu hoặc fixture version.
- Thời điểm readiness đạt.
- Kết quả suite và log liên quan.
- Kết quả teardown.

Nếu không có các thông tin này, việc tái hiện lỗi có thể khó khăn vì nhóm không biết test đã chạy trên cấu hình nào.

## 10. Ví dụ: môi trường ephemeral cho kiểm thử pull request

Giả sử một pull request thay đổi checkout API và trang xác nhận đơn hàng. Pipeline cần chạy integration test và một số E2E test.

### 10.1. Cấp phát

Khi pipeline bắt đầu, hệ thống tạo environment ID dựa trên pull request và run number. IaC cấp:

- Namespace hoặc network riêng.
- Database tạm với schema tương ứng.
- Checkout service và frontend từ artifact của commit.
- Message broker hoặc namespace queue riêng.
- Tài khoản và fixture thử nghiệm.
- Kết nối tới payment sandbox với credential ngắn hạn.

Tài nguyên được gắn owner, commit, run ID và TTL. Các phiên bản service phụ thuộc được khóa để kết quả có thể tái lập.

### 10.2. Kiểm tra sẵn sàng

Trước khi chạy test, pipeline xác minh:

- Database chấp nhận kết nối và migration hoàn tất.
- Checkout API trả readiness thành công.
- Frontend tải được và gọi đúng API.
- Broker có queue cần thiết và consumer đã sẵn sàng.
- Sandbox credential hợp lệ.
- Fixture và tài khoản test có thể truy cập.
- Trace hoặc log có thể truy vấn theo environment ID.

Nếu broker chưa sẵn sàng, E2E test liên quan không chạy. Pipeline ghi readiness failure và chuyển sang cleanup.

### 10.3. Sử dụng và thu thập bằng chứng

Integration test xác minh checkout lưu dữ liệu và phát sự kiện. E2E test thực hiện hành trình đặt hàng qua UI. Kết quả được gắn với commit, environment ID và trace ID. Log được lọc để không chứa token hoặc dữ liệu cá nhân.

Nếu test phát hiện lỗi, nhóm có thể dùng environment ID và artifact đã khóa để tái lập trước khi môi trường hết TTL, hoặc tạo lại môi trường với cùng cấu hình.

### 10.4. Thu hồi và xác minh

Sau test, pipeline lưu báo cáo và log cần thiết, thu hồi credential sandbox, dừng service và xóa database, broker namespace, network cùng fixture. Sau đó, cleanup verifier truy vấn theo environment ID để xác nhận không còn tài nguyên tạm.

Nếu database xóa thất bại, môi trường được đánh dấu CLEANUP_FAILED và đưa vào hàng đợi xử lý. Dashboard hiển thị owner, tài nguyên còn lại và thời điểm hết hạn để không bị bỏ quên.

## 11. Đo lường chất lượng quản lý môi trường

Có thể theo dõi các chỉ số sau:

| Chỉ số | Ý nghĩa |
|---|---|
| Thời gian từ REQUESTED đến READY | Đo tốc độ cấp phát và khởi tạo. |
| Tỷ lệ readiness thành công | Phản ánh độ ổn định của cấu hình và phụ thuộc. |
| Tỷ lệ test bị ảnh hưởng bởi môi trường | Giúp phân biệt lỗi sản phẩm với lỗi hạ tầng test. |
| Tỷ lệ cleanup thành công | Đo mức độ thu hồi tài nguyên đầy đủ. |
| Số tài nguyên mồ côi hoặc quá TTL | Cho biết lỗ hổng trong quản lý vòng đời. |
| Chi phí trung bình mỗi test run | Hỗ trợ tối ưu kích thước và thời gian tồn tại. |
| Tỷ lệ drift cấu hình | Cho biết mức độ nhất quán giữa cấu hình mong đợi và thực tế. |
| Thời gian điều tra lỗi môi trường | Phản ánh chất lượng diagnostics và bằng chứng. |
| Số lần xung đột dữ liệu giữa test run | Đo hiệu quả cô lập. |

Không tối ưu riêng thời gian cấp phát nếu điều đó làm giảm tính đại diện hoặc readiness. Một môi trường nhanh nhưng thiếu dependency cần thiết sẽ tạo kết quả kiểm thử không đáng tin.

## 12. Những sai lầm thường gặp

- **Coi process đang chạy là môi trường sẵn sàng:** service có thể chưa kết nối dependency hoặc hoàn tất migration.
- **Dùng cấu hình không được quản lý:** môi trường dễ drift và khó tái lập.
- **Dùng tag artifact thay đổi được:** các lần chạy có thể kiểm tra phiên bản khác nhau mà không nhận ra.
- **Chia sẻ dữ liệu có thể thay đổi giữa nhiều test:** tạo xung đột và lỗi không ổn định.
- **Chỉ cleanup khi pipeline thành công:** tài nguyên bị bỏ lại khi test fail hoặc runner bị hủy.
- **Xóa theo tên hoặc project quá rộng:** có thể ảnh hưởng tài nguyên dùng chung.
- **Không thu hồi credential:** môi trường đã xóa nhưng quyền truy cập vẫn tồn tại.
- **Không xác minh sau teardown:** lệnh cleanup thành công nhưng tài nguyên vẫn còn.
- **Retry mọi test thất bại:** có thể che giấu lỗi sản phẩm ổn định.
- **Tăng timeout vô hạn:** che giấu dependency không sẵn sàng.
- **Không ghi phiên bản và cấu hình:** khó tái hiện và so sánh kết quả.
- **Không có TTL và owner:** môi trường tạm trở thành tài nguyên mồ côi.

## 13. Mẫu đặc tả và checklist vòng đời môi trường

### 13.1. Mẫu yêu cầu cấp phát

~~~text
Environment ID:
Mục tiêu kiểm thử:
Owner / team:
Commit / build / image digest:

Loại môi trường:
Thời hạn / TTL:
Số lượng test run đồng thời:

Thành phần cần cấp phát:
- Application services:
- Database / schema:
- Broker / queue:
- Cache / storage:
- Network / DNS:
- External sandbox:

Cấu hình:
- Feature flags:
- Timeout / retry:
- Locale / timezone:
- Resource limits:

Danh tính và quyền:
- Test runner identity:
- Service accounts:
- Secret references:
- Tenant / namespace:

Dữ liệu khởi tạo:
Readiness conditions:
Timeout và retry:
Observability:
Cleanup policy:
Điều kiện xác nhận CLEANED:
Rủi ro hoặc giới hạn:
~~~

### 13.2. Checklist trước khi chạy test

- [ ] Environment ID và owner đã được gán.
- [ ] Artifact và phiên bản dependency đã được khóa.
- [ ] Cấu hình và feature flag đúng với mục tiêu kiểm thử.
- [ ] Secret được cấp đúng scope và không nằm trong log.
- [ ] Database, broker, storage và service bắt buộc đã sẵn sàng.
- [ ] Migration và dữ liệu ban đầu hoàn tất.
- [ ] Tài khoản và quyền test hoạt động.
- [ ] Dữ liệu và tài nguyên được cô lập theo run.
- [ ] Readiness evidence đã được lưu.
- [ ] Timeout, quota và điều kiện dừng đã xác định.

### 13.3. Checklist sau khi chạy test

- [ ] Báo cáo và log cần thiết đã được lưu an toàn.
- [ ] Kết quả được liên kết với environment ID và artifact.
- [ ] Test runner đã dừng.
- [ ] Token và credential tạm đã bị thu hồi.
- [ ] Fixture và dữ liệu tạm đã được dọn.
- [ ] Compute, database, broker, storage và network tạm đã được thu hồi.
- [ ] Cleanup verifier xác nhận không còn tài nguyên thuộc run.
- [ ] Cleanup failure được ghi nhận và giao người phụ trách.
- [ ] Môi trường đã chuyển sang CLEANED hoặc trạng thái lỗi phù hợp.
- [ ] Chi phí và tài nguyên còn lại được theo dõi.

## Kết luận

Môi trường kiểm thử đáng tin cậy cần được quản lý xuyên suốt vòng đời từ cấp phát đến xác nhận thu hồi. Cấp phát phải tái lập và gắn với đúng artifact; cấu hình, secret và dữ liệu phải được cô lập; readiness phải xác minh các dependency cần thiết cho từng suite; teardown phải chạy cả khi pipeline thất bại và có bước xác nhận tài nguyên đã được dọn. Khi trạng thái, owner, phiên bản, bằng chứng và TTL được quản lý rõ ràng, nhóm có thể chạy kiểm thử ổn định, tái hiện lỗi tốt hơn và hạn chế chi phí từ môi trường bị bỏ quên.
