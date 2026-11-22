# Lập lịch chạy thường xuyên và chạy đầy đủ định kỳ

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), kiểm thử hồi quy cần được thực hiện đủ thường xuyên để phát hiện sớm tác động ngoài ý muốn của thay đổi, đồng thời cần có những lần chạy đầy đủ để tìm lỗi ở các khu vực ít được chạm tới. Nếu chỉ chạy toàn bộ bộ test sau mỗi thay đổi, pipeline có thể quá chậm và tốn tài nguyên. Nếu chỉ chạy một nhóm nhỏ, các lỗi ở luồng ít phổ biến, tích hợp gián tiếp hoặc tổ hợp chức năng có thể bị bỏ sót.

Vì vậy, nhóm cần thiết kế lịch chạy theo nhiều nhịp: kiểm tra nhanh khi thay đổi được tạo, kiểm tra rộng hơn khi tích hợp, chạy bộ hồi quy đầy đủ theo chu kỳ và thực hiện các đợt kiểm tra bổ sung trước hoặc sau những mốc phát hành quan trọng. Lịch chạy phải phản ánh mức độ rủi ro, tốc độ thay đổi, thời gian thực thi, độ ổn định của môi trường và khả năng xử lý kết quả.

Bài học này hướng dẫn cách phân tầng bộ hồi quy, xác định lịch và trigger, chọn phạm vi chạy thường xuyên, tổ chức các lần chạy đầy đủ định kỳ, xử lý thất bại và flaky test, quản lý dữ liệu cùng môi trường, đo hiệu quả và cải tiến lịch chạy theo bằng chứng.

## 1. Vì sao cần nhiều nhịp chạy hồi quy?

### 1.1. Mục tiêu của chạy thường xuyên

Chạy thường xuyên giúp phát hiện sớm lỗi ngay sau khi thay đổi được đưa vào mã nguồn hoặc môi trường tích hợp. Khi khoảng cách giữa thời điểm thay đổi và thời điểm phát hiện ngắn, nhóm thường có ít thay đổi liên quan hơn để điều tra.

Các mục tiêu chính:

- Phát hiện nhanh lỗi ở chức năng cốt lõi.
- Cung cấp phản hồi cho người tạo thay đổi trước khi tích hợp rộng.
- Ngăn lỗi nghiêm trọng đi qua các cổng CI/CD.
- Xác minh các sửa lỗi quan trọng không tái diễn.
- Giữ tín hiệu chất lượng liên tục trong quá trình phát triển.

Bộ test chạy thường xuyên cần ngắn, ổn định và có khả năng chẩn đoán tốt. Nó nên ưu tiên các ca có giá trị cao, thời gian chạy thấp và ít phụ thuộc vào môi trường phức tạp.

### 1.2. Mục tiêu của chạy đầy đủ định kỳ

Chạy đầy đủ định kỳ mở rộng phạm vi đến những test không phù hợp để chạy trên mọi commit hoặc pull request. Nó giúp phát hiện:

- Lỗi ở chức năng ít được sử dụng nhưng vẫn quan trọng.
- Tác động gián tiếp giữa các module hoặc service.
- Tổ hợp trạng thái, quyền và dữ liệu chưa xuất hiện trong bộ nhanh.
- Vấn đề phụ thuộc vào cấu hình, trình duyệt hoặc nền tảng khác.
- Regression tích lũy qua nhiều thay đổi.
- Lỗi do migration, dữ liệu, phiên bản dependency hoặc môi trường tích hợp.

Một lần chạy đầy đủ không có nghĩa là kiểm tra mọi giá trị có thể. Nó có nghĩa là chạy toàn bộ phạm vi hồi quy đã được xác định cho một cấu hình hoặc ma trận môi trường cụ thể.

### 1.3. Hai nhịp bổ sung cho nhau

| Nhịp chạy | Mục tiêu | Phạm vi điển hình | Thời điểm |
|---|---|---|---|
| Nhanh và thường xuyên | Phản hồi sớm, chặn lỗi quan trọng. | Smoke, critical path, test liên quan thay đổi và một phần hồi quy ổn định. | Commit, pull request, trước merge. |
| Tích hợp rộng hơn | Kiểm tra tương tác giữa thành phần. | Integration, API, contract và các luồng liên quan. | Sau merge, khi build tích hợp hoặc deploy vào test environment. |
| Đầy đủ định kỳ | Tìm lỗi ngoài phạm vi chạy nhanh. | Bộ hồi quy đầy đủ theo phạm vi đã phê duyệt. | Nightly, hàng tuần hoặc theo chu kỳ phù hợp. |
| Theo mốc phát hành | Xác minh trạng thái ứng viên phát hành. | Full regression, nền tảng được hỗ trợ và các kiểm tra rủi ro cao. | Trước release candidate hoặc trước production rollout. |
| Sau triển khai | Xác nhận hệ thống thực tế hoạt động. | Smoke, health và các luồng đại diện an toàn. | Sau deploy, theo từng giai đoạn rollout. |

Không có một lịch cố định phù hợp với mọi sản phẩm. Tần suất cần dựa trên hậu quả nếu lỗi lọt, tốc độ thay đổi, thời gian chạy và khả năng phản hồi khi test thất bại.

## 2. Phân tầng bộ kiểm thử hồi quy

### 2.1. Bộ nhanh cho mỗi thay đổi

Bộ nhanh thường chạy trên mỗi commit hoặc pull request. Nên chọn:

- Unit test cho quy tắc quan trọng.
- API test cho hợp đồng và hành vi backend cốt lõi.
- Smoke test xác minh ứng dụng khởi động và các endpoint thiết yếu.
- Các regression test cho lỗi nghiêm trọng đã từng xảy ra.
- Một số integration test nhỏ có thời gian và độ ổn định phù hợp.
- Kiểm tra bảo mật tự động nhanh nếu phù hợp với pipeline.

Bộ nhanh nên có thời gian thực thi nằm trong giới hạn mà nhóm có thể chấp nhận để nhận phản hồi trước khi merge. Không nên đưa một E2E dài và flaky vào cổng bắt buộc nếu có thể xác minh cùng quy tắc ở tầng thấp hơn; tuy nhiên, luồng có rủi ro rất cao có thể cần một E2E đại diện.

### 2.2. Bộ tích hợp sau merge

Bộ tích hợp chạy khi thay đổi đã được hợp nhất hoặc khi build triển khai vào môi trường tích hợp. Nó có thể bao gồm:

- Integration test với database, cache và broker thật.
- Contract test giữa producer và consumer.
- API regression cho các service bị ảnh hưởng.
- E2E quan trọng chạy trên môi trường ổn định.
- Kiểm tra migration và khả năng tương thích dữ liệu.
- Kiểm tra cấu hình và quyền của các service liên quan.

Bộ này cần kiểm tra các ranh giới mà bộ nhanh có thể mô phỏng. Nó cũng cần ghi rõ phiên bản các thành phần và trạng thái môi trường.

### 2.3. Bộ hồi quy đầy đủ

Bộ đầy đủ nên bao phủ toàn bộ danh mục regression test được duy trì và còn phù hợp với phiên bản sản phẩm. Phạm vi có thể gồm:

- Tất cả test unit, API, integration, contract và system được phân loại là regression.
- Các luồng UI/E2E quan trọng.
- Các vai trò, quyền và trạng thái nghiệp vụ chính.
- Phân vùng dữ liệu và giá trị biên có rủi ro.
- Các trình duyệt, thiết bị hoặc cấu hình được hỗ trợ.
- Kiểm tra migration, nâng cấp và tương thích nếu có.
- Các tình huống lỗi và phục hồi đã được đưa vào phạm vi.

Full suite có thể được chia thành nhiều job song song, nhưng báo cáo tổng thể phải cho biết toàn bộ test bắt buộc đã được thực thi hay chưa. Một job bị bỏ qua do thiếu môi trường không được tính như pass.

### 2.4. Phân loại theo thời gian và mức độ quan trọng

Có thể gắn nhãn test bằng các thuộc tính:

- **Critical:** bảo vệ luồng cốt lõi, dữ liệu, tiền hoặc quyền truy cập.
- **High risk:** có hậu quả đáng kể hoặc từng gây lỗi nghiêm trọng.
- **Standard:** kiểm tra hành vi quan trọng nhưng ít rủi ro hơn.
- **Extended:** test dài, ma trận rộng hoặc phụ thuộc môi trường đặc biệt.
- **Platform-specific:** chỉ áp dụng cho một browser, thiết bị, hệ điều hành hoặc cấu hình.
- **Quarantined:** đang điều tra flaky hoặc lỗi môi trường; cần có chủ sở hữu và thời hạn xử lý.

Nhãn giúp lập lịch và lọc phạm vi, nhưng không nên dùng nhãn để âm thầm loại bỏ test quan trọng khỏi báo cáo.

## 3. Chọn trigger và tần suất chạy

### 3.1. Chạy theo sự kiện thay đổi

Một số trigger phù hợp:

- Commit mới trên nhánh làm việc.
- Pull request được tạo hoặc cập nhật.
- Thay đổi được merge vào nhánh tích hợp.
- Build artifact mới.
- Deploy vào môi trường test hoặc staging.
- Thay đổi schema, dependency, cấu hình hoặc feature flag.
- Thay đổi ở module dùng chung có nhiều consumer.
- Sửa một lỗi đã từng gây regression.

Trigger cần gắn với phạm vi thay đổi. Ví dụ, thay đổi schema dùng chung có thể yêu cầu thêm integration test của các consumer liên quan, dù mã nguồn consumer không đổi.

### 3.2. Chạy theo lịch thời gian

Lịch thời gian giúp phát hiện vấn đề không gắn với một commit đơn lẻ, chẳng hạn dữ liệu tích lũy, certificate sắp hết hạn, dependency thay đổi, môi trường drift hoặc lỗi chỉ xuất hiện khi chạy lâu.

Một lịch tham khảo:

| Nhịp | Ví dụ lịch | Mục đích |
|---|---|---|
| Mỗi commit/PR | Khi có push hoặc cập nhật PR | Bộ nhanh và các test liên quan thay đổi. |
| Sau merge | Mỗi lần merge vào nhánh chính | Bộ tích hợp và smoke trong môi trường tích hợp. |
| Hàng đêm | Một lần ngoài giờ cao điểm | Full regression trên cấu hình mặc định. |
| Hàng tuần | Một hoặc nhiều phiên có kiểm soát | Ma trận rộng hơn: browser, cấu hình, dữ liệu và nền tảng. |
| Trước release | Theo từng release candidate | Full regression và kiểm tra rủi ro phát hành. |
| Sau deploy | Ngay sau mỗi giai đoạn rollout | Smoke và xác minh hành trình đại diện. |

Đây là điểm khởi đầu. Một hệ thống có thay đổi liên tục hoặc rủi ro cao có thể cần full suite hằng đêm; một sản phẩm ít thay đổi nhưng có ma trận nền tảng rộng có thể chạy phần mở rộng hằng tuần.

### 3.3. Trigger theo rủi ro, không chỉ theo thời gian

Một số thay đổi cần chạy kiểm tra bổ sung ngay cả khi lịch full suite chưa đến:

- Thay đổi authentication, authorization hoặc session.
- Thay đổi thanh toán, tính giá, dữ liệu tài chính.
- Thay đổi schema, migration hoặc cơ chế lưu trữ.
- Thay đổi API contract hoặc event schema.
- Thay đổi thư viện bảo mật hoặc dependency trọng yếu.
- Thay đổi cấu hình mạng, secret, TLS hoặc quyền service.
- Sửa lỗi production hoặc lỗi có mức độ nghiêm trọng cao.

Có thể dùng phân tích dependency, tag test hoặc quy tắc trong pipeline để mở rộng phạm vi. Nếu không thể xác định chắc chắn tác động, hãy chạy phạm vi rộng hơn hoặc yêu cầu full suite cho thay đổi có rủi ro cao.

### 3.4. Chọn giờ chạy và quản lý cạnh tranh tài nguyên

Lịch chạy cần xem xét:

- Múi giờ của nhóm và thời điểm có người xử lý kết quả.
- Giờ bảo trì hoặc cập nhật môi trường.
- Quota CI runner, database, browser grid và sandbox.
- Tải của các hệ thống dùng chung.
- Thời gian hoàn thành để kết quả còn hữu ích cho quyết định tiếp theo.

Không nên lên lịch full suite vào thời điểm không có người nhận cảnh báo nếu lỗi cần xử lý ngay. Nếu chạy ngoài giờ, cần có cơ chế phân loại, thông báo và người trực hoặc quy trình xử lý vào đầu ngày làm việc.

## 4. Thiết kế chính sách chạy thường xuyên

### 4.1. Đặt ngưỡng thời gian phản hồi

Bộ chạy thường xuyên cần hoàn thành đủ nhanh để không làm tắc luồng phát triển. Hãy đo thời gian thực tế theo từng job và xác định ngân sách cho:

- Setup môi trường.
- Khởi động service.
- Chuẩn bị dữ liệu.
- Thực thi test.
- Thu thập báo cáo.
- Dọn dẹp.

Nếu pipeline quá dài, hãy tìm nguyên nhân trước khi loại test: setup lặp lại, phụ thuộc không cần thiết, test chạy tuần tự, truy vấn chậm hoặc môi trường không ổn định.

### 4.2. Ưu tiên test theo rủi ro và tác động

Khi phải giới hạn bộ nhanh, hãy chọn test dựa trên:

- Mức độ quan trọng với người dùng và kinh doanh.
- Khả năng gây mất dữ liệu, tiền hoặc quyền.
- Lịch sử lỗi và tần suất thay đổi.
- Khả năng test phát hiện lỗi sớm.
- Chi phí thực thi và độ ổn định.
- Mức độ liên quan đến thay đổi hiện tại.

Không nên chỉ chọn test vì chúng chạy nhanh. Một test rất nhanh nhưng ít giá trị không nhất thiết nên được ưu tiên hơn một test hơi dài bảo vệ giao dịch quan trọng.

### 4.3. Sử dụng test impact analysis có kiểm soát

Test impact analysis xác định những test có khả năng bị ảnh hưởng bởi thay đổi. Nguồn thông tin có thể gồm:

- Dependency giữa module và package.
- Quan hệ service/API hoặc producer/consumer.
- Tag test và liên kết test với yêu cầu.
- Thay đổi schema, cấu hình hoặc feature flag.
- Lịch sử lỗi và vùng mã thường xuyên thay đổi.

Phân tích tác động có thể giảm thời gian chạy nhưng có nguy cơ bỏ sót dependency gián tiếp. Vì vậy:

- Giữ một bộ smoke và critical test luôn chạy.
- Chạy bộ rộng hơn sau merge hoặc theo lịch.
- Chạy full suite khi thay đổi có phạm vi không rõ hoặc tác động rộng.
- Định kỳ đánh giá độ chính xác của quy tắc chọn test.

### 4.4. Không để test bị loại bỏ âm thầm

Nếu một test bị skip, quarantine hoặc không chạy do môi trường, báo cáo cần thể hiện rõ:

- Test nào không chạy.
- Lý do.
- Người sở hữu.
- Thời hạn xem xét.
- Rủi ro do thiếu bằng chứng.
- Điều kiện để đưa test trở lại.

Không tính test skipped là passed. Một cổng chất lượng cần phân biệt pass, fail, skipped, blocked và not applicable.

## 5. Tổ chức các lần chạy đầy đủ định kỳ

### 5.1. Xác định ý nghĩa của “đầy đủ”

Full regression cần có danh mục phạm vi được quản lý. Danh mục này có thể thay đổi theo phiên bản sản phẩm, nhưng mỗi lần chạy phải ghi rõ:

- Bộ test và phiên bản danh mục.
- Test bắt buộc và test có điều kiện.
- Môi trường và cấu hình.
- Browser, thiết bị hoặc nền tảng.
- Dữ liệu và vai trò.
- Các phần bị loại trừ.
- Kết quả của test không thực thi được.

Nếu một suite chỉ chạy trên một browser, không nên tuyên bố đã kiểm tra toàn bộ ma trận browser. Cần báo cáo chính xác cấu hình đã được chạy.

### 5.2. Chọn chu kỳ full suite

Tần suất full suite phụ thuộc vào tốc độ thay đổi và thời gian thực thi:

- **Hằng đêm:** phù hợp khi thay đổi liên tục và full suite có thể hoàn thành trong cửa sổ thời gian hợp lý.
- **Vài lần mỗi tuần:** phù hợp khi suite dài hoặc tài nguyên hạn chế, nhưng vẫn cần phản hồi thường xuyên.
- **Hằng tuần:** có thể phù hợp với hệ thống ít thay đổi hoặc ma trận nền tảng rộng.
- **Theo release candidate:** cần thiết trước mốc phát hành, kể cả khi full suite đã chạy định kỳ.
- **Sau thay đổi rủi ro cao:** chạy bổ sung ngay, không đợi chu kỳ kế tiếp.

Không nên dựa vào lịch đơn thuần nếu có thay đổi có khả năng ảnh hưởng rộng vừa được tích hợp.

### 5.3. Mở rộng ma trận theo chu kỳ

Không phải mỗi đêm đều cần chạy mọi tổ hợp môi trường. Có thể phân bổ ma trận:

- Mỗi đêm: cấu hình chuẩn và các luồng quan trọng.
- Một ngày cố định trong tuần: browser hoặc hệ điều hành bổ sung.
- Theo tuần hoặc theo release: locale, timezone, cấu hình nâng cấp và migration.
- Theo quý hoặc mốc kỹ thuật: phiên bản runtime, database hoặc dependency mới.
- Trước release lớn: toàn bộ ma trận được cam kết hỗ trợ.

Ma trận phải được thiết kế dựa trên phạm vi hỗ trợ và rủi ro thực tế. Không chọn nền tảng ngẫu nhiên chỉ để tăng số lần chạy.

### 5.4. Chạy lại sau khi sửa lỗi

Nếu full suite phát hiện lỗi, nhóm cần xác định test thất bại do regression, môi trường hay test không ổn định. Sau khi sửa:

- Chạy lại test tái hiện lỗi.
- Chạy các test liên quan đến vùng bị ảnh hưởng.
- Chạy smoke hoặc bộ tích hợp phù hợp.
- Chạy lại full suite nếu thay đổi sửa lỗi có tác động rộng hoặc chính sách phát hành yêu cầu.

Không cần chạy lại toàn bộ suite chỉ vì một test có lỗi môi trường đã được xác định, trừ khi lỗi môi trường làm mất độ tin cậy của phần lớn kết quả.

## 6. Quản lý môi trường, dữ liệu và phụ thuộc cho lịch chạy

### 6.1. Giữ môi trường sẵn sàng và đại diện

Full suite cần môi trường có phiên bản và cấu hình được ghi nhận. Trước khi chạy, xác minh:

- Artifact và dependency đúng phiên bản.
- Database migration và schema đã hoàn tất.
- Service và broker đã sẵn sàng.
- Feature flag và quyền đúng với mục tiêu.
- Sandbox bên ngoài có thể truy cập.
- Quota và tài nguyên đủ cho mức song song.
- Không có hoạt động bảo trì hoặc thay đổi gây nhiễu.

Nếu readiness thất bại, dừng suite phụ thuộc và ghi environment failure. Không đánh dấu suite là pass hoặc fail chức năng khi nó chưa thực sự chạy.

### 6.2. Cô lập dữ liệu giữa các lần chạy

Lịch chạy thường xuyên và full suite có thể chạy đồng thời. Dữ liệu cần được quản lý để tránh xung đột:

- Namespace theo run hoặc worker.
- Tài khoản riêng cho vai trò cần kiểm tra.
- Fixture có thể tạo lại và dọn sạch.
- Database/schema riêng khi cần.
- Queue/topic và object storage prefix riêng.
- Dữ liệu chỉ đọc dùng chung nếu không có tác dụng phụ.
- Khóa hoặc giới hạn song song cho tài nguyên không thể cô lập.

Một full suite không nên làm thay đổi dữ liệu mà bộ nhanh đang sử dụng. Nếu phải dùng môi trường chung, cần xác định vùng dữ liệu, thời gian khóa và quy tắc điều phối.

### 6.3. Kiểm soát phụ thuộc bên ngoài

Sandbox nhà cung cấp có thể giới hạn tốc độ, reset dữ liệu hoặc không ổn định. Cần:

- Theo dõi quota và rate limit.
- Dùng tài khoản hoặc namespace riêng khi có thể.
- Không tạo giao dịch thật trong lịch test tự động.
- Ghi nhận trạng thái sandbox và thời điểm kiểm tra.
- Phân loại lỗi nhà cung cấp riêng với lỗi sản phẩm.
- Có phương án thay thế hoặc chạy lại có kiểm soát.

Nếu sandbox không sẵn sàng, không nên giả vờ rằng integration test đã được xác minh bằng cách thay thế hoàn toàn bằng mock mà không ghi giới hạn.

### 6.4. Dọn dẹp và tái lập trạng thái

Sau mỗi run, cleanup cần dọn dữ liệu và tài nguyên tạm. Full suite định kỳ có thể tạo nhiều dữ liệu hơn bộ nhanh, do đó cần TTL, owner và báo cáo cleanup. Nếu cleanup thất bại, môi trường cần được cách ly hoặc giao người xử lý.

Dữ liệu đầu vào nên được version hóa hoặc tạo từ fixture để cùng một test có thể chạy lại trên một trạng thái ban đầu tương đương.

## 7. Đảm bảo độ tin cậy của lịch chạy

### 7.1. Quản lý flaky test

Flaky test cho kết quả khác nhau dù mã và điều kiện liên quan không thay đổi. Nó làm giảm niềm tin vào lịch chạy và có thể khiến nhóm bỏ qua cảnh báo.

Nguyên nhân thường gặp:

- Chia sẻ dữ liệu hoặc tài khoản.
- Race condition và xử lý bất đồng bộ.
- Chờ bằng thời gian cố định.
- Phụ thuộc mạng hoặc dịch vụ bên ngoài.
- Thứ tự chạy ảnh hưởng trạng thái.
- Tài nguyên môi trường thiếu ổn định.
- Selector UI phụ thuộc cấu trúc dễ thay đổi.

Khi phát hiện flaky test:

1. Ghi lại tỷ lệ và điều kiện thất bại.
2. Tái hiện độc lập và kiểm tra log/trace.
3. Xác định nguyên nhân test, sản phẩm hay môi trường.
4. Giao owner và thời hạn khắc phục.
5. Chỉ quarantine khi có lý do và cơ chế theo dõi.
6. Đưa test trở lại sau khi sửa và xác minh độ ổn định.

Retry có thể giúp thu thập thêm thông tin nhưng không được biến một test flaky thành pass mà không ghi nhận lần thất bại đầu tiên.

### 7.2. Phân biệt lỗi sản phẩm và lỗi hạ tầng

Báo cáo nên phân loại tối thiểu:

- Assertion failure: hành vi thực tế khác mong đợi.
- Test infrastructure failure: runner, browser grid hoặc công cụ kiểm thử gặp lỗi.
- Environment failure: service, database hoặc dependency không sẵn sàng.
- External dependency failure: sandbox hoặc nhà cung cấp gặp sự cố.
- Test data failure: dữ liệu setup không đúng hoặc bị xung đột.
- Flaky/indeterminate: kết quả không ổn định, chưa xác định nguyên nhân.

Phân loại này giúp quyết định có cần chặn merge, chạy lại, cách ly môi trường hay tạo bug sản phẩm.

### 7.3. Dùng retry có giới hạn và minh bạch

Retry phù hợp cho lỗi tạm thời đã biết, chẳng hạn một lần mất kết nối ngắn trong setup. Nó không nên che giấu assertion failure hoặc lỗi lặp lại ổn định.

Chính sách retry cần quy định:

- Loại lỗi nào được retry.
- Số lần tối đa.
- Khoảng chờ hoặc backoff.
- Có chạy lại toàn test hay chỉ bước setup.
- Cách báo cáo kết quả ban đầu và kết quả retry.
- Khi nào chuyển thành failure cuối cùng.

Nếu test chỉ pass sau nhiều lần retry, cần theo dõi như một tín hiệu chất lượng thấp.

### 7.4. Bảo vệ tính toàn vẹn của kết quả

Mỗi lần chạy cần lưu:

- Run ID và thời điểm.
- Commit/build/image digest.
- Bộ test và phiên bản test.
- Môi trường, cấu hình và feature flag.
- Dữ liệu hoặc fixture version.
- Kết quả từng test và số lần retry.
- Test skipped/quarantined và lý do.
- Log, trace và artifact cần thiết.
- Kết quả cleanup.

Không chỉnh sửa kết quả để biến lỗi thành pass. Nếu một test được xác định là không áp dụng, ghi rõ lý do và người quyết định.

## 8. Song song hóa và tối ưu thời gian chạy

### 8.1. Chia suite thành nhóm độc lập

Có thể chia full suite theo module, service, loại test hoặc nền tảng. Mỗi nhóm cần:

- Có phạm vi rõ.
- Có thể chạy độc lập hoặc biết rõ dependency.
- Có dữ liệu và tài nguyên được cô lập.
- Có timeout riêng.
- Có báo cáo kết quả được tổng hợp.

Không chia theo số lượng test đơn thuần nếu thời gian chạy mỗi test chênh lệch lớn. Nên dùng dữ liệu thời gian thực tế để phân phối cân bằng.

### 8.2. Xác định mức song song an toàn

Mức song song bị giới hạn bởi:

- CPU và memory của runner.
- Connection pool và tải database.
- Quota sandbox hoặc API.
- Số browser session.
- Queue throughput và consumer.
- Dữ liệu hoặc tài nguyên dùng chung.
- Giới hạn rate và chi phí.

Tăng song song có thể làm suite nhanh hơn nhưng cũng gây contention, timeout và flaky. Hãy đo hiệu quả và độ ổn định khi tăng worker; chọn mức tối ưu theo tổng thời gian và tỷ lệ lỗi môi trường.

### 8.3. Tách test dài khỏi bộ chặn merge

Test hiệu năng, test tải lớn, kiểm tra nhiều browser hoặc kịch bản E2E dài có thể chạy ở job riêng. Nếu chúng không cần thiết cho quyết định merge tức thời, có thể đưa vào lịch sau merge hoặc nightly.

Tuy nhiên, nếu thay đổi ảnh hưởng trực tiếp đến rủi ro mà test đó bảo vệ, cần trigger chạy sớm hơn. Không tách test khỏi cổng chỉ vì thời gian dài mà không đánh giá hậu quả.

### 8.4. Dùng cache và tái sử dụng môi trường có kiểm soát

Cache dependency hoặc tái sử dụng môi trường có thể giảm thời gian, nhưng cần tránh trạng thái cũ ảnh hưởng kết quả:

- Cache phải gắn với phiên bản hoặc checksum.
- Dữ liệu test cần reset hoặc namespace riêng.
- Migration phải được xác minh.
- Service không được mang trạng thái từ run trước.
- Cấu hình phải khớp phiên bản hiện tại.
- Có quy trình làm mới hoặc cấp phát lại khi phát hiện drift.

Nếu không thể chứng minh môi trường tái sử dụng ở trạng thái mong đợi, nên tạo môi trường mới cho suite quan trọng.

## 9. Quy trình xử lý một lần chạy định kỳ

Có thể tổ chức một lần chạy theo trình tự sau:

### Bước 1: Chốt phạm vi

Xác định bộ test, phiên bản danh mục, môi trường, ma trận nền tảng và các test có điều kiện. Ghi lý do nếu có phần bị loại trừ.

### Bước 2: Xác nhận thay đổi và trigger

Ghi commit hoặc release candidate, các thay đổi gần đây, trigger theo rủi ro và lý do chạy full suite ở thời điểm này.

### Bước 3: Cấp phát hoặc xác minh môi trường

Kiểm tra artifact, cấu hình, dependency, dữ liệu, quota và readiness. Nếu không đạt, không chạy suite phụ thuộc.

### Bước 4: Thực thi theo nhóm

Chạy bộ nhanh, bộ tích hợp và các nhóm full regression theo kế hoạch. Dùng mức song song an toàn, lưu trạng thái từng job và không bỏ qua test thất bại.

### Bước 5: Phân loại kết quả

Tách lỗi sản phẩm, lỗi môi trường, lỗi hạ tầng, test data và flaky. Tái hiện các failure quan trọng trước khi kết luận.

### Bước 6: Đánh giá tiêu chí chất lượng

Xác định có lỗi nghiêm trọng, test bắt buộc chưa chạy, môi trường không đáng tin hoặc rủi ro chưa được kiểm tra hay không. Quyết định tiếp theo cần dựa trên tiêu chí đã thống nhất.

### Bước 7: Báo cáo và giao việc

Tạo bug hoặc task với bằng chứng, owner, mức độ ảnh hưởng và thời hạn. Ghi test cần thêm, sửa hoặc quarantine.

### Bước 8: Cleanup và cải tiến lịch

Thu hồi tài nguyên, xác minh cleanup, xem thời gian chạy và độ ổn định. Điều chỉnh lịch nếu bộ nhanh quá dài, full suite quá thưa hoặc các test có giá trị cao chưa được trigger đúng lúc.

## 10. Ví dụ: lịch hồi quy cho một ứng dụng thương mại điện tử

Giả sử hệ thống có đăng nhập, tìm kiếm, giỏ hàng, checkout, thanh toán, quản lý đơn và trang quản trị. Nhóm muốn nhận phản hồi nhanh nhưng vẫn kiểm tra đầy đủ trước phát hành.

### 10.1. Lịch đề xuất

| Thời điểm | Bộ test | Phạm vi chính | Quyết định |
|---|---|---|---|
| Mỗi commit/PR | Fast regression | Unit quan trọng, API checkout, quyền truy cập cốt lõi, smoke ngắn. | Chặn merge nếu test bắt buộc thất bại. |
| Sau merge | Integration suite | Database, broker, payment sandbox, contract và migration liên quan. | Chặn promote nếu có lỗi nghiêm trọng. |
| Hàng đêm | Full regression chuẩn | Toàn bộ test hồi quy trên browser và cấu hình chính. | Tạo báo cáo và ticket cho failure. |
| Hàng tuần | Expanded matrix | Browser bổ sung, locale, timezone, vai trò và cấu hình hỗ trợ. | Đánh giá khoảng trống ma trận. |
| Trước release candidate | Release regression | Full suite, migration, luồng quan trọng, bảo mật và smoke trên môi trường gần production. | Cung cấp bằng chứng cho quyết định phát hành. |
| Sau deploy | Production smoke an toàn | Health, đăng nhập thử nghiệm, truy vấn và hành trình không tạo giao dịch thật. | Phát hiện vấn đề triển khai sớm. |

### 10.2. Trigger theo thay đổi

- Thay đổi CSS hoặc layout: chạy UI test liên quan và bộ smoke UI.
- Thay đổi công thức tính giá: chạy unit, API và regression checkout; chạy full suite nếu ảnh hưởng nhiều module.
- Thay đổi quyền hoặc token: chạy bộ security regression và các luồng liên quan đến danh tính.
- Thay đổi schema đơn hàng: chạy migration, integration và consumer contract test.
- Thay đổi payment callback: chạy payment integration và E2E đại diện.
- Thay đổi dependency dùng chung: mở rộng test impact theo các service sử dụng dependency đó.

### 10.3. Xử lý kết quả

Nếu nightly suite có một E2E thất bại do browser grid không sẵn sàng, nhóm ghi environment failure, giữ bằng chứng và chạy lại trên môi trường ổn định. Nếu API test xác nhận người dùng có thể đọc đơn của tài khoản khác, đây là lỗi bảo mật cần được xử lý theo quy trình ưu tiên, không được coi là flaky chỉ vì lần chạy sau pass.

Nếu một test liên tục không ổn định, nhóm có thể quarantine tạm thời nhưng phải giữ owner, deadline và phần rủi ro bị giảm độ bao phủ. Các test quan trọng khác vẫn cần chạy để quyết định chất lượng không phụ thuộc vào một test duy nhất.

## 11. Đo lường hiệu quả lịch chạy

Một lịch chạy tốt cần cân bằng tốc độ phản hồi, độ bao phủ, độ tin cậy và chi phí.

| Chỉ số | Cách diễn giải |
|---|---|
| Thời gian phản hồi bộ nhanh | Từ commit/PR đến kết quả đủ để ra quyết định. |
| Thời gian full suite | Thời gian từ bắt đầu đến báo cáo hoàn chỉnh. |
| Tỷ lệ test bắt buộc được thực thi | Cho biết phạm vi dự kiến có thực sự chạy hay không. |
| Tỷ lệ flaky | Tỷ lệ test có kết quả không ổn định trong điều kiện tương đương. |
| Tỷ lệ lỗi được phát hiện trước release | Đánh giá khả năng phát hiện sớm của lịch. |
| Tỷ lệ regression lọt production | Gợi ý khoảng trống về phạm vi hoặc tần suất. |
| Tỷ lệ môi trường thất bại | Phân biệt chất lượng sản phẩm với độ tin cậy của hạ tầng test. |
| Chi phí CI trên mỗi lần chạy | Hỗ trợ lựa chọn mức song song và tần suất. |
| Thời gian triage và khắc phục | Đo khả năng hành động dựa trên kết quả. |
| Số test bị quarantine quá hạn | Cho biết nợ chất lượng của bộ test. |

Không nên tối ưu một chỉ số đơn lẻ. Giảm thời gian suite bằng cách bỏ test quan trọng có thể làm tăng regression lọt. Tăng số test chạy không có ích nếu phần lớn kết quả không đáng tin hoặc không được xử lý.

### 11.1. Đánh giá giá trị phát hiện

Hãy xem xét test nào thường phát hiện lỗi trước khi lỗi đến người dùng, test nào chỉ lặp lại bằng chứng đã có và test nào tốn nhiều thời gian nhưng hiếm khi cung cấp tín hiệu hữu ích.

Nếu một test không phát hiện lỗi trong thời gian dài, không nên xóa chỉ dựa trên số liệu đó. Có thể nó bảo vệ rủi ro có xác suất thấp nhưng hậu quả rất cao. Cần đánh giá mục tiêu, lịch sử sự cố và mức độ thay thế trước khi thay đổi phạm vi.

### 11.2. Rà soát lịch định kỳ

Khi hệ thống hoặc nhóm thay đổi, hãy rà soát:

- Bộ nhanh có còn đáp ứng ngân sách phản hồi không?
- Full suite có chạy đủ thường xuyên so với tốc độ thay đổi không?
- Các test quan trọng có trigger đúng theo thay đổi không?
- Ma trận môi trường có phản ánh nền tảng đang hỗ trợ không?
- Có test bị quarantine hoặc skip quá lâu không?
- Môi trường và dữ liệu có gây flaky không?
- Kết quả có được xử lý bởi người sở hữu không?

Điều chỉnh lịch dựa trên dữ liệu và thay đổi rủi ro, không chỉ theo thói quen.

## 12. Mẫu chính sách lịch chạy hồi quy

Có thể dùng mẫu sau để thống nhất lịch giữa QA, phát triển, vận hành và quản lý phát hành.

~~~text
Tên sản phẩm / module:
Phiên bản hoặc nhánh áp dụng:
Chủ sở hữu chính sách:

Bộ test:
- Fast regression:
- Integration regression:
- Full regression:
- Expanded platform matrix:
- Release regression:
- Post-deploy smoke:

Trigger:
- Commit / pull request:
- Merge:
- Build / deployment:
- Thay đổi rủi ro cao:
- Lịch thời gian:

Tần suất và cửa sổ chạy:
Môi trường / phiên bản:
Dữ liệu và tài khoản:
Mức song song / quota:
Timeout / retry:
Tiêu chí pass / fail / blocked:
Quy tắc quarantine:
Người nhận cảnh báo:

Yêu cầu bằng chứng:
Quy trình triage:
Owner và SLA xử lý:
Cleanup:
Chỉ số theo dõi:
Ngày rà soát chính sách:
~~~

### 12.1. Checklist trước khi công bố lịch

- [ ] Bộ nhanh bảo vệ luồng cốt lõi và có thời gian phản hồi phù hợp.
- [ ] Bộ tích hợp xác minh các ranh giới quan trọng.
- [ ] Full suite có danh mục và phiên bản phạm vi rõ ràng.
- [ ] Tần suất phản ánh rủi ro và tốc độ thay đổi.
- [ ] Thay đổi rủi ro cao có trigger bổ sung.
- [ ] Ma trận nền tảng được phân bổ theo chu kỳ có chủ đích.
- [ ] Môi trường, dữ liệu, credential và quota sẵn sàng.
- [ ] Mức song song không gây contention hoặc flaky.
- [ ] Test skipped, quarantined và blocked được báo cáo minh bạch.
- [ ] Có người nhận và xử lý kết quả.
- [ ] Cleanup và thu hồi tài nguyên được xác minh.
- [ ] Lịch có ngày rà soát và tiêu chí điều chỉnh.

## 13. Những sai lầm thường gặp

- **Chỉ chạy full suite trước release:** lỗi có thể tồn tại lâu và khó xác định thay đổi gây ra.
- **Chạy full suite trên mọi commit dù quá chậm:** làm giảm tốc độ phản hồi và tăng chi phí không cần thiết.
- **Chỉ chạy test nhanh mãi mãi:** bỏ sót tương tác, ma trận và chức năng ít được sử dụng.
- **Lập lịch theo giờ mà không xét rủi ro:** thay đổi quan trọng có thể chờ đến lần chạy định kỳ tiếp theo.
- **Coi test skipped là pass:** tạo báo cáo bao phủ sai.
- **Retry để che flaky:** làm giảm khả năng nhận biết vấn đề thực.
- **Quarantine không thời hạn:** biến khoảng trống bao phủ thành trạng thái bình thường.
- **Không khóa phiên bản môi trường:** kết quả giữa các lần chạy không thể so sánh.
- **Chạy song song quá mức:** tạo contention và lỗi môi trường.
- **Không có người xử lý kết quả nightly:** lỗi được phát hiện nhưng không dẫn đến hành động.
- **Đo chất lượng bằng số lượng test:** không phản ánh giá trị phát hiện hoặc rủi ro còn lại.
- **Không điều chỉnh lịch khi sản phẩm thay đổi:** phạm vi và nhịp chạy dần mất phù hợp.

## 14. Danh sách rà soát trước khi hoàn tất kế hoạch hồi quy

- [ ] Các test được phân tầng theo tốc độ, phạm vi và mức độ quan trọng.
- [ ] Bộ nhanh chạy trên thay đổi và bảo vệ luồng có rủi ro cao.
- [ ] Bộ tích hợp chạy sau merge hoặc khi có build tích hợp phù hợp.
- [ ] Full regression chạy theo chu kỳ đã xác định.
- [ ] Release regression và post-deploy smoke có tiêu chí riêng.
- [ ] Trigger theo thay đổi rủi ro cao được cấu hình.
- [ ] Tần suất và giờ chạy phù hợp với nguồn lực và người xử lý.
- [ ] Phạm vi full suite, ma trận môi trường và phần loại trừ được ghi rõ.
- [ ] Dữ liệu, tài khoản, phiên bản và môi trường có thể tái lập.
- [ ] Retry, flaky và quarantine có chính sách minh bạch.
- [ ] Kết quả pass, fail, skipped và blocked được phân biệt.
- [ ] Báo cáo có bằng chứng và liên kết với commit/build.
- [ ] Có owner, quy trình triage và thời hạn xử lý.
- [ ] Cleanup được thực hiện và xác minh.
- [ ] Lịch được rà soát dựa trên số liệu và rủi ro mới.

## Kết luận

Lịch hồi quy hiệu quả kết hợp phản hồi nhanh sau thay đổi với những lần chạy đầy đủ theo chu kỳ và theo mốc phát hành. Bộ nhanh bảo vệ luồng quan trọng; bộ tích hợp kiểm tra các ranh giới; full suite mở rộng phạm vi đến các chức năng, trạng thái và nền tảng ít được chạy thường xuyên. Khi trigger theo rủi ro, môi trường và dữ liệu được kiểm soát, kết quả được phân loại minh bạch và có người xử lý, nhóm có thể phát hiện regression sớm mà vẫn duy trì tốc độ phát triển và chi phí hợp lý.
