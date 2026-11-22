# Lập ngân sách công cụ, hạ tầng và dịch vụ bên ngoài

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, chất lượng kiểm thử phụ thuộc vào con người, phương pháp và cả nguồn lực kỹ thuật được cung cấp. Nhóm cần công cụ quản lý test, môi trường chạy ứng dụng, dữ liệu, pipeline CI/CD, thiết bị, dịch vụ tích hợp và đôi khi cả nhà cung cấp kiểm thử chuyên biệt. Nếu ngân sách không phản ánh đúng nhu cầu, nhóm có thể thiếu môi trường, phải chia sẻ tài nguyên gây xung đột, không đủ license hoặc bỏ qua những phép kiểm tra quan trọng vì chi phí phát sinh ngoài dự kiến.

**Lập ngân sách công cụ, hạ tầng và dịch vụ bên ngoài** là quá trình xác định nhu cầu, ước lượng chi phí, lựa chọn phương án, phân bổ ngân sách, theo dõi sử dụng và điều chỉnh theo rủi ro cùng tiến độ sản phẩm. Mục tiêu là bảo đảm nguồn lực cần thiết cho hoạt động kiểm thử trong suốt vòng đời phát triển và vận hành, đồng thời giúp tổ chức hiểu rõ chi phí, trách nhiệm và giá trị nhận được.

Ngân sách kiểm thử không nên chỉ là danh sách giá mua license. Cần xem xét tổng chi phí sở hữu (Total Cost of Ownership - TCO), gồm phí thuê bao, hạ tầng, lưu trữ, băng thông, tích hợp, bảo mật, quản trị, hỗ trợ, đào tạo, bảo trì và chi phí thoát khỏi nhà cung cấp. Một công cụ có giá mua thấp vẫn có thể tốn kém nếu khó tích hợp, cần nhiều thao tác thủ công hoặc không đáp ứng yêu cầu bảo mật.

## 1. Vì sao cần lập ngân sách nguồn lực kiểm thử?

Kiểm thử cần được thực hiện xuyên suốt từ làm rõ yêu cầu, phát triển, tích hợp, phát hành đến giám sát sau triển khai. Mỗi giai đoạn có nhu cầu nguồn lực khác nhau. Ví dụ, kiểm thử đơn vị cần môi trường phát triển và công cụ phân tích; kiểm thử tích hợp cần database, broker và API sandbox; kiểm thử hiệu năng cần tài nguyên tính toán và dữ liệu đại diện; kiểm thử khả năng sử dụng có thể cần người tham gia và thiết bị; kiểm thử bảo mật có thể cần công cụ chuyên dụng hoặc dịch vụ chuyên gia.

Lập ngân sách giúp:

- **Đảm bảo năng lực kiểm thử:** có đủ môi trường, công cụ, thiết bị và dịch vụ để thực hiện phạm vi đã cam kết.
- **Lập kế hoạch sớm:** phát hiện chi phí license, hạ tầng hoặc nhà cung cấp cần phê duyệt trước khi đến mốc sử dụng.
- **Kiểm soát tổng chi phí:** tránh chỉ tính giá mua ban đầu mà bỏ qua vận hành, lưu trữ, hỗ trợ và nâng cấp.
- **Ưu tiên theo rủi ro:** tập trung tiền và năng lực vào các luồng có hậu quả lớn nếu không được kiểm tra.
- **Giải thích quyết định đầu tư:** liên kết khoản chi với năng lực, bằng chứng chất lượng và mục tiêu sản phẩm.
- **Dự báo và điều chỉnh:** nhận biết mức tiêu thụ tăng, license không sử dụng hoặc môi trường chạy vượt dự toán.
- **Tuân thủ và quản trị:** bảo đảm mua sắm, dữ liệu, bảo mật, hợp đồng và quyền sử dụng được xử lý đúng quy trình.

Ngân sách không thay thế quyết định kỹ thuật. Nó tạo ra giới hạn và lựa chọn có thể thảo luận; nhóm kỹ thuật cần giải thích rủi ro của việc giảm nguồn lực, còn người quản lý ngân sách cần hiểu tác động đến chất lượng và lịch phát hành.

## 2. Xác định phạm vi ngân sách

Trước khi ước lượng, cần xác định ngân sách dành cho sản phẩm, chương trình, dự án, nhóm hoặc một giai đoạn phát hành. Phạm vi càng rõ, khả năng tránh tính trùng hoặc bỏ sót càng cao.

### Phạm vi theo vòng đời

Có thể lập ngân sách cho:

- Khám phá yêu cầu, prototype và kiểm thử khả năng sử dụng.
- Phát triển và kiểm thử đơn vị.
- Kiểm thử component, API, contract và tích hợp.
- Kiểm thử hệ thống, hồi quy và chấp nhận.
- Kiểm thử hiệu năng, bảo mật, accessibility và tương thích.
- CI/CD, môi trường staging, pre-production và kiểm tra sau triển khai.
- Monitoring, observability, hỗ trợ và điều tra lỗi sau phát hành.
- Bảo trì test suite, dữ liệu, môi trường và công cụ trong giai đoạn vận hành.

Không phải mọi khoản chi đều do nhóm QA trực tiếp sở hữu. Ví dụ, cloud platform có thể do nhóm hạ tầng quản lý, license IDE do bộ phận phát triển mua chung, còn dịch vụ kiểm thử xâm nhập do bộ phận bảo mật điều phối. Cần ghi rõ khoản nào thuộc ngân sách trực tiếp, khoản nào được chia sẻ và khoản nào do đơn vị khác chịu trách nhiệm.

### Phạm vi theo thời gian

Phân biệt:

- **Chi phí một lần:** thiết lập ban đầu, tích hợp, di chuyển dữ liệu, thiết bị, tư vấn triển khai hoặc đào tạo ban đầu.
- **Chi phí định kỳ:** thuê bao hàng tháng/năm, cloud usage, bảo trì, hỗ trợ, gia hạn chứng thư hoặc dịch vụ ngoài.
- **Chi phí biến đổi:** tăng theo số người dùng, số test run, phút CI, số thiết bị, dung lượng lưu trữ, băng thông hoặc số giao dịch.
- **Chi phí theo sự kiện:** kiểm thử tải trước release, đánh giá bảo mật định kỳ, kiểm thử xâm nhập hoặc hỗ trợ khẩn cấp.

Một dự án có thể có ngân sách đầu tư ban đầu và ngân sách vận hành sau khi bàn giao. Cần xác định ai nhận chi phí khi dự án chuyển sang giai đoạn vận hành để tránh công cụ được mua nhưng không có kinh phí gia hạn.

### Xác định điều kiện và giả định

Ghi lại số nhóm, số người, số môi trường, tần suất release, thời lượng test, quy mô dữ liệu, số browser/thiết bị, yêu cầu lưu trữ và mức độ sẵn sàng dịch vụ. Đây là các giả định ảnh hưởng trực tiếp đến chi phí. Khi giả định thay đổi, dự toán cần được cập nhật.

## 3. Phân loại các nhóm chi phí

Một cấu trúc ngân sách dễ quản lý thường chia nguồn lực thành các nhóm. Cách phân loại có thể điều chỉnh theo mô hình kế toán và quy trình mua sắm của tổ chức.

### Công cụ và license

Ví dụ:

- Test management, test case repository và defect tracking.
- API testing, browser automation và mobile automation.
- Performance/load testing và service virtualization.
- Static analysis, coverage, security scanning và dependency scanning.
- Test data management, database tooling và synthetic data generation.
- CI/CD platform, artifact repository và observability tooling.
- Thiết bị kiểm thử, browser/device farm và license hệ điều hành hoặc phần mềm chuyên dụng.

Các mô hình giá có thể tính theo người dùng, concurrent user, agent, project, repository, test execution, phút chạy, số request hoặc mức sử dụng. Cần xác định đơn vị tính và giới hạn của từng gói, không chỉ ghi giá niêm yết.

### Hạ tầng và môi trường

Các khoản có thể gồm:

- Máy ảo, container, Kubernetes cluster và compute runner.
- Database, cache, message broker, object storage và backup.
- Network, load balancer, NAT, IP, DNS và băng thông.
- Môi trường dev/test/integration/staging/pre-production.
- Thiết bị vật lý, điện, mạng và phòng lab.
- Giám sát, logging, tracing, metrics và lưu trữ telemetry.
- Khôi phục thảm họa, môi trường dự phòng và tài nguyên failover.

Hạ tầng cloud thường có chi phí theo thời gian, dung lượng hoặc mức sử dụng. Môi trường chạy liên tục dù không được sử dụng có thể làm tăng chi phí đáng kể.

### Dịch vụ bên ngoài

Ví dụ:

- API sandbox của payment gateway, identity provider hoặc đối tác.
- Dịch vụ email/SMS thử nghiệm, bản đồ, vận chuyển hoặc dữ liệu.
- Browser/device cloud và test execution service.
- Dịch vụ kiểm thử xâm nhập, đánh giá bảo mật hoặc accessibility.
- Dịch vụ kiểm thử hiệu năng chuyên sâu hoặc tư vấn kiến trúc.
- Dịch vụ dữ liệu tổng hợp, ẩn danh hoặc quản lý test data.
- Hỗ trợ kỹ thuật, đào tạo và tư vấn từ nhà cung cấp.

Cần phân biệt sandbox miễn phí với sandbox có giới hạn, môi trường production-like có tính phí và chi phí phát sinh khi vượt quota. Một API test có thể không thu phí theo tháng nhưng vẫn có giới hạn request, dữ liệu hoặc hỗ trợ.

### Nhân lực triển khai và vận hành nguồn lực

Chi phí nguồn lực còn gồm thời gian của nhân sự để:

- Tích hợp và cấu hình công cụ.
- Xây dựng pipeline, dashboard và môi trường.
- Tạo dữ liệu, fixture và automation.
- Quản lý license, quyền và hợp đồng.
- Theo dõi sử dụng, tối ưu và xử lý sự cố.
- Đào tạo người dùng và chuyển giao vận hành.

Thời gian nhân sự có thể không nằm trong hóa đơn mua sắm, nhưng vẫn là chi phí thực tế cần xem xét khi so sánh phương án tự xây dựng với thuê dịch vụ.

### Dự phòng và chi phí rủi ro

Ngân sách có thể cần khoản dự phòng cho thay đổi quy mô, phát sinh tích hợp, gia hạn, biến động tỷ giá, yêu cầu bảo mật hoặc một đợt kiểm thử bổ sung. Mức dự phòng cần dựa trên độ bất định và chính sách tài chính của tổ chức, không lấy một tỷ lệ tùy tiện cho mọi dự án.

## 4. Thu thập nhu cầu trước khi ước lượng

Ước lượng chính xác bắt đầu từ nhu cầu, không bắt đầu từ danh mục công cụ mà nhóm muốn mua.

### Xác định mục tiêu kiểm thử

Liệt kê loại bằng chứng cần có: kiểm tra chức năng, hồi quy, API, tương thích, hiệu năng, bảo mật, accessibility, khả năng phục hồi, kiểm thử chấp nhận hoặc giám sát. Với mỗi mục tiêu, xác định liệu công cụ hiện có đã đáp ứng chưa và khoảng trống nằm ở đâu.

Ví dụ, nếu mục tiêu là chạy hồi quy giao diện trên nhiều browser, nhu cầu có thể gồm browser automation, browser binaries, runner song song, thiết bị và nơi lưu screenshot/video. Nếu mục tiêu là kiểm tra API bất đồng bộ, có thể cần broker test, schema registry hoặc simulator cùng công cụ truy vết message.

### Ước lượng quy mô sử dụng

Thu thập các dữ liệu như:

- Số tester, developer, reviewer và người cần quyền xem báo cáo.
- Số test run mỗi ngày/tuần/tháng.
- Thời gian chạy trung bình và mức song song cần thiết.
- Số pipeline, repository, project và môi trường.
- Số browser, thiết bị, OS và phiên bản cần hỗ trợ.
- Dung lượng artifact, log, video, trace và báo cáo.
- Số request đến sandbox/API và giới hạn quota.
- Số lần đánh giá chuyên biệt trong năm.

Không nên dùng số người hiện tại làm dự báo duy nhất nếu sản phẩm sắp mở rộng hoặc thêm nhóm. Hãy ước lượng theo giai đoạn và đưa giả định vào tài liệu.

### Phỏng vấn các bên liên quan

Trao đổi với QA/Test Lead, engineering, platform/DevOps, security, procurement, finance, product owner và vận hành. Mỗi nhóm có góc nhìn khác nhau: QA biết mục tiêu test; platform biết chi phí hạ tầng; security biết yêu cầu kiểm soát; procurement biết điều khoản mua sắm; finance biết cách ghi nhận và chu kỳ ngân sách.

### Phân biệt nhu cầu bắt buộc và mong muốn

Chia nhu cầu thành:

- **Bắt buộc:** yêu cầu hợp đồng, bảo mật, pháp lý, vận hành hoặc điều kiện tối thiểu để kiểm thử rủi ro cao.
- **Cần thiết:** giúp đạt mục tiêu chất lượng và giảm chi phí/rủi ro đáng kể.
- **Có thể trì hoãn:** tiện ích hoặc năng lực nâng cao có thể bổ sung ở giai đoạn sau.

Không nên cắt một yêu cầu bảo mật hoặc khả năng khôi phục bắt buộc chỉ vì công cụ đó có giá cao. Cần tìm phương án thay thế đáp ứng cùng mục tiêu hoặc đưa rủi ro lên cấp có thẩm quyền.

## 5. Ước lượng chi phí và tổng chi phí sở hữu (TCO)

Giá mua ban đầu chỉ là một phần. TCO giúp so sánh các lựa chọn trên cùng khoảng thời gian và phạm vi sử dụng.

### Cấu phần TCO

Có thể mô hình hóa:

**TCO = Chi phí thiết lập + Chi phí thuê/mua + Chi phí sử dụng + Chi phí vận hành + Chi phí tích hợp/đào tạo + Chi phí hỗ trợ/bảo trì + Chi phí thoát hoặc chuyển đổi.**

Trong đó:

- Chi phí thiết lập gồm cấu hình, migration, tích hợp SSO, pipeline và dữ liệu.
- Chi phí thuê/mua gồm license, subscription hoặc phí theo gói.
- Chi phí sử dụng gồm compute, storage, network, test minutes và API calls.
- Chi phí vận hành gồm thời gian quản trị, giám sát, cập nhật và xử lý sự cố.
- Chi phí hỗ trợ/bảo trì gồm support plan, nâng cấp và gia hạn.
- Chi phí thoát gồm export dữ liệu, thay công cụ, chuyển test suite, chấm dứt hợp đồng hoặc đào tạo lại.

TCO nên được tính trong một khoảng thời gian thống nhất, ví dụ 12, 24 hoặc 36 tháng tùy chu kỳ kế hoạch. Cần nêu rõ khoản nào là chi phí một lần và khoản nào lặp lại.

### Mô hình ước lượng theo đơn vị sử dụng

Ví dụ các phép tính:

- License theo người dùng: `số người dùng x giá mỗi người/tháng x số tháng`.
- CI runner theo phút: `tổng phút chạy x giá mỗi phút`.
- Storage: `dung lượng trung bình x giá mỗi GB/tháng x số tháng`.
- Browser/device farm: `số phút thiết bị x đơn giá` hoặc gói concurrent session.
- API sandbox: `số request vượt quota x phí mỗi request` cộng phí cố định nếu có.
- Hỗ trợ chuyên gia: `số ngày công x đơn giá ngày công`.

Phải kiểm tra đơn vị giá, mức tối thiểu, quota, phí vượt ngưỡng, thuế, tỷ giá và điều khoản tăng giá. Không so sánh hai báo giá nếu một bên tính theo concurrent user còn bên kia tính theo named user mà chưa quy đổi nhu cầu thực tế.

### Chi phí ẩn cần kiểm tra

- Thời gian đào tạo và onboarding.
- Tích hợp với SSO, issue tracker, source control và CI/CD.
- Giới hạn export dữ liệu hoặc API.
- Chi phí lưu video, screenshot, trace và log dài hạn.
- Phí hỗ trợ ngoài giờ hoặc hỗ trợ ưu tiên.
- Nâng cấp bắt buộc, plugin trả phí và tính năng bảo mật cao cấp.
- Chi phí duy trì test suite khi công cụ thay đổi.
- Chi phí chuyển đổi khi hợp đồng kết thúc.

### So sánh tự xây dựng và mua dịch vụ

Tự xây dựng có thể giảm phí license nhưng cần nhân lực phát triển, bảo trì, bảo mật, hỗ trợ và nâng cấp. Thuê dịch vụ có thể triển khai nhanh hơn nhưng tạo phụ thuộc nhà cung cấp, chi phí định kỳ và giới hạn kiểm soát. Cần so sánh TCO, thời gian đưa vào sử dụng, mức đáp ứng yêu cầu, khả năng tích hợp, bảo mật và chi phí thoát.

## 6. Lập ngân sách hạ tầng kiểm thử

Hạ tầng là một trong những khoản biến đổi mạnh theo quy mô, mức song song và thời gian chạy. Cần ước lượng theo workload thay vì chỉ chọn cấu hình máy chủ theo cảm tính.

### Môi trường cần thiết

Một sản phẩm có thể cần:

- Dev/test environment cho kiểm tra nhanh.
- Integration environment cho các thành phần và phụ thuộc.
- Staging/pre-production gần với cấu hình production.
- Performance environment có tài nguyên và dữ liệu đại diện.
- Security testing environment được cô lập.
- Sandbox hoặc mock services cho đối tác.
- Environment phục vụ đào tạo, UAT hoặc demo.

Không phải mọi môi trường đều phải chạy liên tục. Có thể tạo theo nhu cầu, tắt ngoài giờ hoặc dùng ephemeral environment cho pull request nếu kiến trúc hỗ trợ.

### Ước lượng compute

Xác định số job chạy đồng thời, CPU/RAM trung bình và đỉnh, thời gian hoạt động, loại workload và thời gian chờ. Với test song song, số runner cần thiết phụ thuộc thời lượng test và thời gian phản hồi mong muốn.

Một ước lượng sơ bộ:

`Tổng runner-hours = số runner trung bình x số giờ hoạt động trong kỳ`.

Ví dụ, 4 runner hoạt động trung bình 5 giờ/ngày trong 20 ngày làm việc tương đương 400 runner-hours/tháng. Đây là phép tính tải sử dụng, chưa phải chi phí; cần nhân với đơn giá và cộng thời gian khởi tạo, lưu trữ hoặc tài nguyên phụ trợ.

Không nên chọn runner quá lớn cho mọi test. Có thể tách pool theo workload: unit/API test nhẹ, browser test nặng, performance test chuyên biệt. Theo dõi thời gian chờ queue và mức sử dụng để quyết định tăng/giảm năng lực.

### Ước lượng storage và network

Log, artifact, screenshot, video, trace, database snapshot và test data có thể tích lũy nhanh. Ước lượng theo:

- Số build/test run trong kỳ.
- Kích thước trung bình của artifact và report.
- Dung lượng log/video mỗi lần chạy.
- Retention theo loại dữ liệu.
- Tỷ lệ tăng trưởng và bản sao lưu.
- Băng thông giữa runner, cloud service, registry và môi trường.

Có thể ước lượng dung lượng lưu trung bình bằng `số lần chạy x dung lượng mỗi lần x thời gian lưu` khi dữ liệu được lưu theo chu kỳ; cần điều chỉnh nếu có compression, deduplication hoặc lifecycle tiering.

### Môi trường tạm thời và tự động tắt

Ephemeral environment tạo theo nhánh hoặc pull request giúp giảm xung đột và có thể giảm chi phí nếu tự động hủy sau khi dùng. Cần tính cả thời gian tạo, migration, seed data và cleanup. Đặt TTL, owner tag và cảnh báo cho tài nguyên không có chủ sở hữu.

Tắt môi trường ngoài giờ có thể tiết kiệm nhưng phải bảo đảm không làm gián đoạn test dài, backup hoặc lịch chạy nightly. Quy tắc tắt cần dựa trên trạng thái và lịch, không chỉ dựa vào thời gian im lặng.

### Kiểm soát chi phí cloud

Thiết lập budget alert, quota, tagging, cost center và dashboard. Phân loại chi phí theo service, environment, team, project và loại workload. Theo dõi chi phí bất thường, tài nguyên nhàn rỗi, volume tồn đọng và log retention quá dài.

## 7. Lập ngân sách công cụ và license

Trước khi mua công cụ, cần xác định người dùng, tính năng, cách tích hợp và mô hình cấp phép.

### Xác định nhu cầu license

Ghi rõ:

- Số named user và concurrent user.
- Vai trò cần tạo/sửa test, thực thi, review hoặc chỉ xem báo cáo.
- Số agent/runner hoặc parallel execution.
- Số project/repository/workspace.
- Số test run, API call, device minute hoặc storage quota.
- Các tính năng nâng cao như SSO, audit, RBAC, private runner và data residency.

Có thể cấp license theo vai trò nếu nhà cung cấp hỗ trợ. Người chỉ xem dashboard có thể không cần license đầy đủ. Tuy nhiên, cần xác nhận điều khoản hợp đồng để tránh vi phạm khi dùng chung tài khoản hoặc chia sẻ credential.

### Kiểm tra khả năng tích hợp

Một công cụ có thể có nhiều tính năng nhưng không phù hợp nếu không tích hợp với hệ thống hiện tại. Đánh giá:

- Source control và pull request workflow.
- CI/CD và artifact repository.
- Issue/defect tracking và test management.
- SSO, identity provider và role mapping.
- API, webhook, export và reporting.
- Log/metrics/observability platform.
- Khả năng nhập/xuất dữ liệu khi chuyển đổi.

Ưu tiên thử nghiệm một luồng thực tế từ đầu đến cuối trước khi ký hợp đồng dài hạn. Một demo của nhà cung cấp không thay thế pilot trên quy trình của nhóm.

### Quản lý license theo vòng đời

- Ghi nhận owner, người dùng, loại license, ngày bắt đầu/kết thúc và cost center.
- Review người dùng không hoạt động hoặc license trùng.
- Thu hồi quyền khi nhân sự chuyển nhóm hoặc rời tổ chức.
- Theo dõi mức sử dụng so với quota và điều khoản.
- Đặt lịch nhắc gia hạn đủ sớm để đánh giá lựa chọn.
- Lưu hợp đồng, hóa đơn và phê duyệt ở hệ thống được tổ chức chỉ định.

Không nên giảm license chỉ dựa trên số lần đăng nhập. Một người có thể cần công cụ cho một đợt release hoặc hoạt động kiểm thử chuyên biệt. Cần xem lịch sử sử dụng, kế hoạch công việc và vai trò trước khi thu hồi.

## 8. Đánh giá và dự toán dịch vụ bên ngoài

Dịch vụ ngoài có thể cung cấp năng lực khó tự xây dựng, nhưng tạo phụ thuộc về chi phí, dữ liệu, tính sẵn sàng và hợp đồng.

### Xác định phạm vi dịch vụ

Với mỗi nhà cung cấp, ghi:

- Mục đích và kết quả cần nhận.
- Phạm vi kỹ thuật, môi trường và thời gian cung cấp.
- Số lượng test, request, thiết bị, ngày công hoặc đơn vị tính.
- Giới hạn sử dụng và cách tính phí vượt quota.
- Mức hỗ trợ, thời gian phản hồi và lịch bảo trì.
- Trách nhiệm của nhà cung cấp và của nhóm nội bộ.
- Dữ liệu được gửi, xử lý, lưu và xóa như thế nào.

Ví dụ, một dịch vụ browser cloud có thể tính theo phút session và mức song song; một đơn vị kiểm thử xâm nhập có thể tính theo ngày công, số ứng dụng và phạm vi retest; một API sandbox có thể giới hạn số giao dịch hoặc loại dữ liệu.

### Đánh giá nhà cung cấp

Xem xét:

- Khả năng đáp ứng kỹ thuật và độ ổn định.
- Bảo mật, quyền riêng tư, vị trí lưu dữ liệu và chứng nhận phù hợp.
- SLA, support, escalation và lịch bảo trì.
- Khả năng tích hợp, export và chuyển đổi.
- Minh bạch giá, quota, phí vượt mức và điều khoản tăng giá.
- Uy tín, năng lực hỗ trợ và rủi ro gián đoạn dịch vụ.
- Quyền sở hữu dữ liệu, kết quả kiểm thử và tài liệu được tạo.
- Điều khoản chấm dứt, xóa dữ liệu và hỗ trợ thoát.

Đối với dịch vụ xử lý mã nguồn, log, dữ liệu khách hàng hoặc thông tin nhạy cảm, cần đánh giá bảo mật và pháp lý trước khi gửi dữ liệu. Không đưa dữ liệu thật vào dịch vụ ngoài chỉ vì gói dùng thử cho phép upload.

### Quản lý sandbox và quota

Ghi nhận môi trường sandbox có khác production ở điểm nào, dữ liệu giả lập nào được hỗ trợ và giới hạn nào có thể ảnh hưởng kết quả. Theo dõi quota và đặt giới hạn để test tự động không vô tình tạo nhiều request hoặc giao dịch ngoài dự kiến.

Nếu sandbox không ổn định, có thể dùng simulator cho test lặp lại và giữ một số test tích hợp thật theo lịch. Cần nêu rõ phần nào được chứng minh bằng simulator và phần nào được kiểm tra với nhà cung cấp.

### Điều khoản và rủi ro nhà cung cấp

Hợp đồng cần làm rõ quyền sử dụng, bảo mật, dữ liệu, hỗ trợ, SLA, thay đổi API, thông báo chấm dứt, lưu trữ và xóa dữ liệu. Với dịch vụ quan trọng, đánh giá phương án dự phòng hoặc khả năng thay nhà cung cấp.

## 9. Ưu tiên đầu tư theo rủi ro và giá trị

Ngân sách thường có giới hạn. Không phải công cụ đắt nhất hoặc nhiều tính năng nhất luôn là lựa chọn tốt nhất. Cần liên kết khoản đầu tư với rủi ro được giảm, năng lực được bổ sung và chi phí vận hành.

### Đánh giá rủi ro nếu không đầu tư

Hỏi:

- Rủi ro nào không thể kiểm tra nếu thiếu nguồn lực?
- Hậu quả nếu lỗi không được phát hiện trước phát hành là gì?
- Tần suất và mức độ sử dụng của năng lực này?
- Có biện pháp thay thế thủ công hoặc công cụ hiện có không?
- Biện pháp thay thế có tốn thời gian, dễ sai hoặc không đáp ứng quy định không?

Ví dụ, nếu hệ thống xử lý thanh toán, thiếu sandbox hoặc khả năng mô phỏng lỗi có thể làm giảm bằng chứng về retry và idempotency. Nếu sản phẩm chỉ có một giao diện nội bộ ít rủi ro, đầu tư device farm lớn có thể chưa phải ưu tiên đầu tiên.

### Ma trận ưu tiên

| Mức ưu tiên | Đặc điểm | Cách xử lý ngân sách |
|---|---|---|
| Bắt buộc | Nghĩa vụ pháp lý/hợp đồng, bảo mật, an toàn hoặc điều kiện vận hành | Bảo đảm nguồn lực hoặc tìm phương án tương đương được phê duyệt |
| Cao | Rủi ro nghiệp vụ lớn, phát hành thường xuyên, tiết kiệm thời gian đáng kể | Ưu tiên đầu tư và đo hiệu quả sau triển khai |
| Trung bình | Cải thiện năng suất hoặc độ bao phủ nhưng có workaround chấp nhận được | Thử nghiệm/pilot, triển khai theo giai đoạn |
| Thấp | Tiện ích, ít dùng hoặc chưa có bằng chứng về giá trị | Trì hoãn, dùng công cụ hiện có hoặc đánh giá lại sau |

Mức ưu tiên phải được giải thích bằng rủi ro và mục tiêu. Không nên dùng điểm số tổng hợp để tự động loại bỏ yêu cầu bắt buộc.

### So sánh phương án

Với mỗi nhu cầu, có thể so sánh:

- Công cụ hiện có và khả năng mở rộng.
- Mua license mới.
- Dùng dịch vụ cloud theo mức sử dụng.
- Tự xây dựng hoặc mở rộng công cụ nội bộ.
- Thuê dịch vụ chuyên gia theo đợt.
- Giảm phạm vi hoặc thay đổi lịch test, nếu rủi ro cho phép.

So sánh theo TCO, thời gian triển khai, mức đáp ứng, độ tin cậy, bảo mật, khả năng mở rộng và khả năng thoát. Ghi rõ đánh đổi; không chỉ chọn phương án có chi phí trực tiếp thấp nhất.

## 10. Xây dựng ngân sách theo giai đoạn

Ngân sách nên phản ánh lộ trình sản phẩm. Nhu cầu trong giai đoạn prototype khác với giai đoạn mở rộng người dùng và vận hành dài hạn.

### Giai đoạn khám phá và pilot

Ưu tiên chi phí thấp và thời hạn ngắn để xác minh nhu cầu:

- Dùng trial hoặc pilot có điều khoản rõ.
- Tận dụng công cụ hiện có khi đáp ứng yêu cầu.
- Thuê dịch vụ chuyên gia cho đánh giá cần kỹ năng hiếm.
- Dựng môi trường nhỏ, có thể hủy sau pilot.
- Xác định tiêu chí thành công và TCO dự kiến trước khi mở rộng.

Không đưa dữ liệu nhạy cảm vào trial nếu chưa đánh giá điều khoản bảo mật và quyền xử lý dữ liệu.

### Giai đoạn phát triển và tích hợp

Ước lượng theo số nhóm, pipeline, test run, môi trường và mức song song. Xem xét chi phí CI runner, artifact, database, broker, test management, automation và sandbox.

### Giai đoạn release và nghiệm thu

Có thể phát sinh chi phí tăng tạm thời cho môi trường staging gần production, kiểm thử hiệu năng, bảo mật, accessibility, browser/device matrix, hỗ trợ nhà cung cấp và retest.

### Giai đoạn vận hành

Lập ngân sách recurring cho license, cloud, logging, monitoring, backup, hỗ trợ, gia hạn, nâng cấp và kiểm tra định kỳ. Xác định owner và cost center sau khi dự án bàn giao.

### Dự báo theo kịch bản

Nên lập ít nhất các kịch bản:

- **Cơ sở:** quy mô và tần suất sử dụng theo kế hoạch hiện tại.
- **Tăng trưởng:** số người dùng, test run, môi trường hoặc lưu lượng tăng.
- **Tiết kiệm:** giảm tài nguyên nhàn rỗi, tối ưu retention hoặc chuyển sang gói phù hợp.
- **Rủi ro:** release bị kéo dài, cần retest, nhà cung cấp tăng giá hoặc phát sinh đánh giá bảo mật.

Kịch bản giúp nhận biết yếu tố nào làm chi phí biến động và mức dự phòng cần xem xét.

## 11. Mẫu bảng dự toán và công thức theo dõi

Một bảng dự toán cơ bản có thể gồm các cột:

| Trường | Mục đích |
|---|---|
| Cost ID | Mã khoản chi để truy vết |
| Nhóm chi phí | Công cụ, compute, storage, dịch vụ, nhân lực, hỗ trợ |
| Mục đích kiểm thử | Năng lực/rủi ro được hỗ trợ |
| Nhà cung cấp/đơn vị sở hữu | Bên cung cấp hoặc nhóm quản lý |
| Đơn vị tính | User-month, runner-hour, GB-month, request, day-rate... |
| Khối lượng | Số lượng dự kiến |
| Đơn giá | Giá theo báo giá/hợp đồng |
| Tần suất/thời hạn | Một lần, tháng, năm hoặc theo sự kiện |
| Chi phí dự kiến | Khối lượng x đơn giá, cộng khoản liên quan |
| Cost center | Đơn vị chịu ngân sách |
| Owner | Người chịu trách nhiệm |
| Giả định/rủi ro | Điều kiện có thể làm thay đổi chi phí |
| Trạng thái | Đề xuất, pilot, phê duyệt, đang dùng, gia hạn |

### Công thức cơ bản

`Chi phí kỳ = Khối lượng sử dụng trong kỳ x Đơn giá`.

`Tổng dự toán = Chi phí một lần + Tổng chi phí định kỳ + Chi phí biến đổi + Dự phòng được phê duyệt`.

`Chênh lệch = Chi phí thực tế - Ngân sách đã duyệt`.

`Tỷ lệ chênh lệch (%) = (Chi phí thực tế - Ngân sách đã duyệt) / Ngân sách đã duyệt x 100%`.

Nếu ngân sách bằng 0 hoặc khoản chi mới chưa có ngân sách, cần báo cáo riêng thay vì tính tỷ lệ phần trăm gây hiểu nhầm.

### Ví dụ dự toán minh họa

Giả sử một nhóm sản phẩm lập kế hoạch cho một quý. Các con số dưới đây chỉ minh họa cách tính, không phải báo giá thị trường:

| Khoản mục | Khối lượng giả định | Đơn giá giả định | Dự toán kỳ |
|---|---:|---:|---:|
| Test management | 12 user x 3 tháng | 18 USD/user/tháng | 648 USD |
| CI runner | 400 runner-hour | 0.12 USD/giờ | 48 USD |
| Browser/device cloud | 900 device-minute | 0.08 USD/phút | 72 USD |
| Test environment compute | 2 môi trường x 3 tháng | 110 USD/môi trường/tháng | 660 USD |
| Log và artifact storage | 300 GB-month | 0.04 USD/GB-tháng | 12 USD |
| Security assessment | 4 ngày chuyên gia | 650 USD/ngày | 2,600 USD |
| **Tổng minh họa** |  |  | **4,040 USD** |

Trong ví dụ, chi phí đánh giá bảo mật là khoản theo sự kiện; các khoản còn lại có mô hình định kỳ hoặc theo mức sử dụng. Khi lập dự toán thật, cần thêm thuế, tỷ giá, phí tối thiểu, hỗ trợ, setup, retention và các điều khoản khác nếu áp dụng.

## 12. Theo dõi ngân sách và kiểm soát chi phí thực tế

Ngân sách chỉ hữu ích nếu được so sánh với mức sử dụng thực tế và dự báo được cập nhật.

### Thiết lập cost ownership

Mỗi khoản chi cần có owner chịu trách nhiệm theo dõi, cost center và mục đích sử dụng. Với chi phí cloud dùng chung, xác định quy tắc phân bổ theo team, service, môi trường hoặc mức tiêu thụ.

### Theo dõi định kỳ

Theo tháng hoặc chu kỳ phù hợp, so sánh:

- Ngân sách đã duyệt và chi phí thực tế.
- Dự toán đến cuối kỳ (forecast) và mức tiêu thụ hiện tại.
- Sử dụng license so với số được cấp.
- Runner-hours, queue time và mức sử dụng compute.
- Storage growth, retention và chi phí log/artifact.
- API calls, quota và phí vượt mức.
- Tài nguyên không hoạt động hoặc không có owner.

Không chỉ nhìn hóa đơn tổng. Phân tích theo nhãn và workload để biết khoản nào tăng, vì sao và ai có thể hành động.

### Cảnh báo và ngưỡng kiểm soát

Có thể thiết lập cảnh báo khi tiêu thụ đạt một tỷ lệ ngân sách, khi tăng đột biến hoặc khi quota gần hết. Ngưỡng cần phù hợp với thời điểm trong kỳ và khả năng phản ứng. Cảnh báo quá nhiều hoặc không có owner sẽ mất tác dụng.

### Quản lý thay đổi ngân sách

Khi nhu cầu thay đổi, ghi lý do, tác động, lựa chọn thay thế và người phê duyệt. Ví dụ, thêm browser matrix có thể tăng device-minute; tăng retention có thể tăng storage; release kéo dài có thể cần thêm staging compute. Không nên để khoản chi phát sinh tự động mà không cập nhật forecast.

### Review license và dịch vụ định kỳ

Trước gia hạn, đánh giá số người dùng thực tế, mức sử dụng tính năng, support, giá mới, điều khoản dữ liệu và khả năng thay thế. Đối với dịch vụ ít sử dụng, cân nhắc giảm gói hoặc chuyển sang pay-as-you-go nếu TCO phù hợp.

## 13. Tối ưu chi phí mà vẫn bảo vệ chất lượng

Tối ưu chi phí không có nghĩa cắt giảm kiểm thử quan trọng. Cần loại bỏ lãng phí, cải thiện hiệu quả sử dụng và phân bổ test theo rủi ro.

### Tối ưu hạ tầng

- Tắt môi trường không dùng theo lịch hoặc TTL.
- Dùng autoscaling và runner pool phù hợp với workload.
- Chọn kích thước máy theo số liệu CPU/RAM thực tế.
- Dọn volume, snapshot và artifact hết retention.
- Dùng storage tier phù hợp cho dữ liệu ít truy cập.
- Chạy test song song có kiểm soát để giảm thời gian mà không tạo quá nhiều tài nguyên nhàn rỗi.
- Tách workload nhẹ và nặng để tránh cấp cấu hình lớn cho mọi job.

### Tối ưu công cụ và license

- Thu hồi license không còn sử dụng sau khi xác nhận nhu cầu.
- Cấp quyền theo vai trò và mức sử dụng.
- Hợp nhất công cụ có chức năng trùng lặp nếu không làm giảm khả năng kiểm soát.
- Ưu tiên chuẩn mở và khả năng export để giảm lock-in.
- Đàm phán gói theo số người dùng và mức sử dụng thực tế.
- Tận dụng công cụ sẵn có nếu đáp ứng bảo mật, độ tin cậy và hỗ trợ.

### Tối ưu test execution

- Chạy smoke và core nhanh ở các cổng thường xuyên.
- Chạy extended theo lịch hoặc theo thay đổi có tác động.
- Chuyển kiểm tra chi tiết xuống unit/API khi vẫn bảo vệ đúng hành vi.
- Loại test trùng lặp sau khi xác minh có bằng chứng thay thế.
- Giảm flaky test và thời gian chờ môi trường.
- Dùng simulator cho kiểm tra lặp lại, đồng thời duy trì test với dịch vụ thật theo rủi ro.

Không nên bỏ test bảo mật, phục hồi, giao dịch quan trọng hoặc yêu cầu bắt buộc chỉ để giảm phút CI. Nếu cần giảm phạm vi, phải đánh giá và chấp nhận rủi ro đúng thẩm quyền.

### Tối ưu dữ liệu và log

- Dùng dữ liệu tổng hợp và fixture tái sử dụng có kiểm soát.
- Lưu report máy đọc được và log cần thiết; tránh lưu payload/video không cần thiết vô thời hạn.
- Áp dụng retention khác nhau cho log debug, audit và release evidence.
- Nén hoặc chuyển tầng lưu trữ khi phù hợp.
- Giữ bằng chứng cần thiết cho kiểm toán, điều tra và rollback.

## 14. Rủi ro tài chính, hợp đồng và bảo mật

Ngân sách công cụ và dịch vụ ngoài thường liên quan đến cam kết dài hạn và dữ liệu tổ chức. Cần đánh giá các rủi ro trước khi mua.

### Rủi ro hợp đồng

- Gia hạn tự động hoặc thời hạn thông báo chấm dứt.
- Giá tăng sau giai đoạn dùng thử hoặc khi vượt quota.
- Giới hạn số người dùng, project, API hoặc dữ liệu export.
- SLA không phù hợp với nhu cầu kiểm thử hoặc hỗ trợ.
- Phí hỗ trợ, triển khai, đào tạo và retest chưa được tính.
- Điều khoản quyền sở hữu dữ liệu, test script và kết quả.
- Khó chuyển đổi hoặc chi phí thoát cao.

### Rủi ro bảo mật và dữ liệu

- Dịch vụ lưu mã nguồn, log hoặc dữ liệu người dùng ở vị trí không phù hợp.
- Tài khoản dùng chung hoặc quyền quá rộng.
- Dữ liệu được dùng để huấn luyện hoặc chia sẻ theo điều khoản chưa được xem xét.
- Secret hoặc token xuất hiện trong test artifact/log.
- Không có cơ chế xóa dữ liệu sau khi kết thúc hợp đồng.

Đưa security, privacy và procurement vào quy trình đánh giá khi dịch vụ xử lý dữ liệu hoặc có quyền truy cập hệ thống. Không tự ý ký hợp đồng, tạo tài khoản trả phí hoặc gửi dữ liệu thật qua nhà cung cấp ngoài quy trình được tổ chức phê duyệt.

### Rủi ro phụ thuộc nhà cung cấp

Đánh giá khả năng gián đoạn, thay đổi API, ngừng sản phẩm, thiếu hỗ trợ hoặc tăng giá. Với dịch vụ quan trọng, cần phương án dự phòng, dữ liệu có thể export, tài liệu tích hợp và kế hoạch thay thế.

## 15. Quản trị và quy trình phê duyệt ngân sách

Quy trình cụ thể phụ thuộc tổ chức, nhưng cần có vai trò và bằng chứng rõ ràng.

### Các vai trò thường tham gia

- **QA/Test Lead:** xác định nhu cầu kiểm thử, quy mô suite và khoảng trống năng lực.
- **Engineering Lead:** xác nhận kiến trúc, tích hợp và tác động kỹ thuật.
- **Platform/DevOps:** ước lượng hạ tầng, CI/CD, lưu trữ và vận hành.
- **Security/Privacy:** đánh giá kiểm soát, dữ liệu và rủi ro nhà cung cấp.
- **Procurement/Legal:** xem xét báo giá, điều khoản, SLA và hợp đồng.
- **Finance:** kiểm tra ngân sách, cost center, thuế, tỷ giá và dự báo.
- **Product Owner/Project Manager:** ưu tiên phạm vi, thời điểm và giá trị nghiệp vụ.
- **Budget owner:** phê duyệt khoản chi theo thẩm quyền.

Một người có thể giữ nhiều vai trò ở nhóm nhỏ, nhưng quyền đề xuất, review kỹ thuật và phê duyệt tài chính cần rõ.

### Quy trình tham khảo

1. Xác định mục tiêu và rủi ro cần hỗ trợ.
2. Lập danh mục nguồn lực và giả định sử dụng.
3. Thu thập báo giá, phương án thay thế và TCO.
4. Đánh giá kỹ thuật, bảo mật, pháp lý và khả năng tích hợp.
5. Lập dự toán theo giai đoạn và kịch bản.
6. Trình budget owner phê duyệt.
7. Mua sắm/thiết lập theo quy trình và cấp quyền tối thiểu.
8. Theo dõi sử dụng, chi phí thực tế và forecast.
9. Review định kỳ, điều chỉnh và chuẩn bị gia hạn/thoát dịch vụ.

### Hồ sơ cần lưu

- Business/technical justification.
- Danh mục nhu cầu và tiêu chí chấp nhận công cụ/dịch vụ.
- Báo giá và so sánh phương án.
- TCO và giả định dự toán.
- Đánh giá bảo mật, privacy và pháp lý khi áp dụng.
- Phê duyệt ngân sách và cost center.
- Hợp đồng, SLA, license entitlement và ngày gia hạn.
- Hóa đơn, usage report và forecast.
- Quyết định gia hạn, giảm gói hoặc chấm dứt.

## 16. Ví dụ xuyên suốt: lập ngân sách kiểm thử cho nền tảng thương mại điện tử

Giả sử một nhóm chuẩn bị phát triển và vận hành nền tảng thương mại điện tử có đăng nhập, giỏ hàng, thanh toán, kho và vận chuyển. Nhóm có 10 tester/developer thường xuyên dùng công cụ, 3 môi trường chính và cần chạy hồi quy hàng ngày.

### Xác định nhu cầu

- Test management và defect tracking để quản lý test case, kết quả và lỗi.
- CI runner cho unit, API, integration và browser test.
- PostgreSQL, Redis và message broker trong môi trường tích hợp.
- Payment sandbox và API vận chuyển thử nghiệm.
- Browser/device service để kiểm tra các nền tảng được hỗ trợ.
- Logging/metrics/tracing để điều tra test và xác minh sau deploy.
- Một đợt security assessment trước release lớn.

### Phân loại mức ưu tiên

| Nhu cầu | Rủi ro được giảm | Ưu tiên |
|---|---|---|
| Payment sandbox | Giao dịch sai, retry trùng, trạng thái thanh toán không nhất quán | Bắt buộc/cao theo phạm vi sản phẩm |
| CI runner | Phản hồi chậm, không đủ năng lực chạy hồi quy | Cao |
| Database/broker test environment | Lỗi tích hợp và dữ liệu | Cao |
| Test management | Mất truy vết và khó quản lý bằng chứng | Trung bình đến cao |
| Browser/device cloud | Lỗi tương thích trên nền tảng người dùng | Theo ma trận hỗ trợ |
| Security assessment | Lỗ hổng nghiêm trọng trước phát hành | Theo yêu cầu và rủi ro |

### Xem xét phương án

Nhóm so sánh browser cloud trả theo phút với thiết bị nội bộ; CI runner cloud theo mức sử dụng với runner tự quản; test management SaaS với công cụ hiện có; sandbox nhà cung cấp với simulator cho test lặp lại. Mỗi phương án được so sánh theo TCO, khả năng tích hợp, bảo mật, độ ổn định, quota và khả năng export.

### Dự toán và theo dõi

Nhóm lập dự toán quý, ghi rõ số runner-hours, device-minutes, GB-month, số user-month và ngày công chuyên gia. Mỗi khoản có owner. Hàng tháng, nhóm so sánh actual với forecast, kiểm tra runner nhàn rỗi, storage growth, license không sử dụng và quota sandbox.

Nếu chi phí browser cloud tăng do extended regression chạy toàn bộ ma trận mỗi commit, nhóm có thể chuyển phần lớn ma trận sang nightly và release candidate, giữ smoke/core cho các browser trọng yếu ở PR. Quyết định phải bảo đảm các browser được hỗ trợ vẫn có lịch kiểm tra đủ thường xuyên và rủi ro được chấp nhận.

Nếu nhóm muốn giảm chi phí bằng cách bỏ security assessment, cần xem xét nghĩa vụ, rủi ro và phương án thay thế. Không nên tự loại bỏ yêu cầu bảo mật bắt buộc để cân bằng bảng ngân sách.

## 17. Những sai lầm thường gặp

**Chỉ tính giá license.** Hạ tầng, tích hợp, hỗ trợ, đào tạo, vận hành và chi phí thoát có thể lớn hơn phí thuê bao. Tính TCO trong cùng một khoảng thời gian.

**Mua công cụ trước khi xác định nhu cầu.** Công cụ có nhiều tính năng nhưng không giải quyết khoảng trống thực tế. Bắt đầu từ mục tiêu kiểm thử, rủi ro và quy mô sử dụng.

**Ước lượng cloud theo cấu hình máy mà không đo workload.** Tài nguyên có thể quá lớn hoặc thiếu khi chạy song song. Dùng runner-hours, queue time, CPU/RAM, storage và network thực tế để dự báo.

**Bỏ qua phí vượt quota.** Test tự động có thể tạo nhiều API call, device-minute hoặc storage hơn dự kiến. Xác định quota, cảnh báo và giới hạn trước khi vận hành.

**Không tính chi phí nhân lực quản trị.** Công cụ tự xây dựng hoặc SaaS đều cần tích hợp, cập nhật, phân quyền và hỗ trợ. Đưa thời gian nhân lực vào so sánh TCO.

**Gia hạn tự động mà không review.** License không dùng hoặc gói không còn phù hợp vẫn tiếp tục tính phí. Đặt lịch review trước thời hạn thông báo chấm dứt.

**Cắt giảm test quan trọng để đạt ngân sách.** Điều này có thể chuyển chi phí từ kiểm thử sang sự cố production. Đánh giá rủi ro và tìm cách tối ưu thực thi, môi trường hoặc công cụ trước.

**Không có owner cho chi phí dùng chung.** Không ai chịu trách nhiệm nên tài nguyên nhàn rỗi và chi phí tăng không được phát hiện. Gắn cost center, tag và owner.

**Không đánh giá dữ liệu nhà cung cấp xử lý.** Mã nguồn, log và dữ liệu khách hàng có thể bị lưu hoặc truy cập ngoài dự kiến. Đánh giá security/privacy trước khi sử dụng.

**Không có phương án thoát.** Dữ liệu, test script hoặc report bị khóa trong nền tảng có thể làm chi phí chuyển đổi cao. Kiểm tra export, API và quyền sở hữu dữ liệu trước khi ký.

## 18. Checklist lập và quản lý ngân sách nguồn lực kiểm thử

### Nhu cầu và phạm vi

- [ ] Mục tiêu kiểm thử, rủi ro và năng lực cần có đã được xác định.
- [ ] Phạm vi theo vòng đời, dự án và thời gian đã rõ.
- [ ] Số người dùng, test run, runner, môi trường, thiết bị và dữ liệu được ước lượng.
- [ ] Nhu cầu bắt buộc được phân biệt với nhu cầu có thể trì hoãn.
- [ ] Khoản chi dùng chung và đơn vị chịu trách nhiệm đã được xác định.

### Ước lượng và lựa chọn

- [ ] Có báo giá hoặc đơn giá với đơn vị tính và quota rõ.
- [ ] TCO gồm setup, license, usage, vận hành, hỗ trợ và exit cost.
- [ ] Có phương án hiện có, mua dịch vụ, tự xây dựng hoặc thay thế để so sánh.
- [ ] Giả định, kịch bản và dự phòng được ghi nhận.
- [ ] Khả năng tích hợp, mở rộng, export và lock-in được đánh giá.

### Hạ tầng và dịch vụ ngoài

- [ ] Compute, storage, network, backup và môi trường được ước lượng theo workload.
- [ ] Có cơ chế tắt tài nguyên nhàn rỗi, TTL và cảnh báo chi phí.
- [ ] Quota, phí vượt mức, sandbox limit và SLA được hiểu rõ.
- [ ] Security, privacy, data residency và hợp đồng được review khi cần.
- [ ] Có owner và phương án dự phòng/thoát cho dịch vụ quan trọng.

### Theo dõi và tối ưu

- [ ] Mỗi khoản có owner, cost center và mục đích.
- [ ] Actual, forecast và budget variance được review định kỳ.
- [ ] License, runner, storage và dịch vụ được kiểm tra mức sử dụng.
- [ ] Thay đổi ngân sách có lý do và phê duyệt.
- [ ] Tối ưu chi phí không loại bỏ kiểm thử bắt buộc hoặc rủi ro quan trọng.
- [ ] Gia hạn/chấm dứt được review trước thời hạn hợp đồng.

## 19. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một công cụ test management có giá thấp hơn đối thủ nhưng không hỗ trợ export test case và lịch sử kết quả ở định dạng dùng được. TCO và exit cost có thể cao. Cần kiểm tra khả năng export, API và quyền sở hữu dữ liệu trước khi quyết định.

**Tình huống 2:** Cloud bill tăng mạnh vì môi trường staging chạy cả cuối tuần dù không có test. Cần phân tích usage, gắn owner/tag, đặt lịch hoặc TTL để tắt môi trường khi an toàn và bảo đảm không ảnh hưởng backup/nightly job.

**Tình huống 3:** Browser/device cloud tính theo phút. Nhóm chạy toàn bộ ma trận trên mỗi pull request, khiến chi phí vượt dự toán. Có thể giữ smoke/core trên nền tảng trọng yếu ở PR và chuyển ma trận rộng sang nightly/release candidate, sau khi đánh giá tần suất kiểm tra và rủi ro.

**Tình huống 4:** Payment sandbox có quota thấp nhưng test tự động retry vô hạn khi timeout. Cần giới hạn retry, dùng idempotency và simulator cho các trường hợp lặp; đồng thời giữ kiểm tra sandbox theo lịch để xác nhận tích hợp thật.

**Tình huống 5:** Nhóm muốn chuyển log test lên dịch vụ SaaS miễn phí nhưng log chứa email khách hàng và token. Cần đánh giá dữ liệu, che thông tin, điều khoản xử lý và phê duyệt bảo mật trước khi upload.

**Tình huống 6:** Một license chuyên dụng chỉ dùng trong đợt kiểm thử bảo mật mỗi quý. Không nên tự động thu hồi chỉ vì ít đăng nhập; hãy xem lịch sử sử dụng, lịch kiểm thử, quyền sở hữu và lựa chọn gói theo thời gian nếu có.

Khi lập ngân sách, hãy tự hỏi: **nguồn lực này hỗ trợ rủi ro hoặc năng lực nào, tổng chi phí trong suốt thời gian sử dụng là bao nhiêu, ai sở hữu và theo dõi khoản chi, và nếu không mua thì bằng chứng kiểm thử nào sẽ thiếu?** Trả lời rõ giúp ngân sách gắn với chất lượng sản phẩm thay vì chỉ là danh sách mua sắm.

## Kết luận

Lập ngân sách công cụ, hạ tầng và dịch vụ bên ngoài cần bắt đầu từ mục tiêu kiểm thử, rủi ro và quy mô sử dụng. Nhóm cần phân loại chi phí một lần, định kỳ và biến đổi; tính TCO; ước lượng compute, storage, network, license và quota; đánh giá nhà cung cấp, bảo mật, hợp đồng và khả năng thoát; sau đó theo dõi actual, forecast và mức sử dụng. Khi mỗi khoản chi có owner, mục đích và bằng chứng giá trị, tổ chức có thể đầu tư đúng năng lực, kiểm soát chi phí và duy trì mức kiểm thử phù hợp trong suốt vòng đời sản phẩm.
