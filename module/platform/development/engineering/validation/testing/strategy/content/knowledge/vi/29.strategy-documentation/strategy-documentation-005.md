# Mô tả dữ liệu, môi trường, công cụ và trách nhiệm

## Mục tiêu bài học

Một chiến lược kiểm thử chỉ có thể được thực hiện nhất quán khi những người tham gia hiểu dữ liệu nào được sử dụng, môi trường nào cần có, công cụ nào hỗ trợ và ai chịu trách nhiệm cho từng hoạt động. Nếu các thông tin này chỉ nằm trong trí nhớ của một vài thành viên, nhóm mới khó tiếp nhận công việc, sự cố khó được khôi phục và kết quả kiểm thử khó tái lập.

Trong VALIDATION_TESTING_STRATEGY, tài liệu chiến lược cần mô tả đủ bối cảnh vận hành để nhóm có thể chuẩn bị, thực thi, đánh giá và duy trì hoạt động kiểm thử. Bốn phần dữ liệu, môi trường, công cụ và trách nhiệm phải liên kết với mục tiêu, phạm vi, rủi ro và quy trình kiểm thử. Tài liệu cần chỉ ra nguồn dữ liệu và cách quản lý, mục đích và giới hạn của từng môi trường, vai trò của từng công cụ, cùng người sở hữu và cách phối hợp khi có thay đổi hoặc sự cố.

Sau bài học, người học có thể:

- Xác định thông tin cần mô tả về dữ liệu kiểm thử, môi trường, công cụ và trách nhiệm.
- Thiết kế cấu trúc tài liệu để người thực hiện dễ tìm và cập nhật.
- Ghi nhận nguồn gốc, phân loại, tạo lập, làm mới, bảo vệ và dọn dẹp dữ liệu.
- Mô tả môi trường, cấu hình, phụ thuộc, mức tương đồng và giới hạn sử dụng.
- Lập danh mục công cụ, phiên bản, mục đích, tích hợp và chủ sở hữu.
- Phân công trách nhiệm bằng vai trò, RACI, đầu mối và đường escalation.
- Liên kết các thông tin vận hành với test, yêu cầu, rủi ro và bản build.
- Quản lý phiên bản, rà soát và cập nhật tài liệu theo thay đổi sản phẩm.

## 1. Vai trò của tài liệu vận hành trong chiến lược kiểm thử

Tài liệu chiến lược không chỉ giải thích nhóm sẽ kiểm thử điều gì. Nó còn cần cho biết nhóm sẽ thực hiện công việc trong điều kiện nào và bằng nguồn lực nào. Bốn nhóm thông tin có mối liên hệ chặt chẽ:

- **Dữ liệu:** trạng thái, bản ghi, tài khoản và nội dung cần thiết để kiểm tra hành vi.
- **Môi trường:** nơi phần mềm và các phụ thuộc được triển khai, cấu hình và chạy.
- **Công cụ:** phương tiện tạo dữ liệu, thực thi test, thu thập bằng chứng và quản lý kết quả.
- **Trách nhiệm:** người hoặc nhóm sở hữu dữ liệu, môi trường, công cụ, kiểm tra và quyết định.

Ví dụ, một test kiểm tra quyền truy cập chéo tenant cần dữ liệu của ít nhất hai tenant, tài khoản có vai trò khác nhau, môi trường có cấu hình xác thực phù hợp, công cụ gửi API request và thu thập trace, cùng owner có thể điều tra khi kết quả sai. Nếu tài liệu chỉ ghi tên test mà thiếu những điều kiện này, người khác có thể không tái hiện được kết quả.

### 1.1. Tài liệu cần hỗ trợ những quyết định nào?

Người đọc nên có thể tìm được câu trả lời cho các câu hỏi:

- Dữ liệu nào được phép dùng và lấy từ đâu?
- Dữ liệu có nhạy cảm không, ai được truy cập và khi nào phải xóa?
- Môi trường nào dùng cho unit, integration, E2E, performance hoặc security testing?
- Phiên bản và cấu hình nào đang được sử dụng?
- Phụ thuộc nào phải sẵn sàng trước khi chạy?
- Công cụ nào là nguồn chuẩn cho test, kết quả, log và defect?
- Ai duy trì từng tài sản và ai hỗ trợ khi có lỗi?
- Thay đổi nào cần review hoặc phê duyệt?
- Bằng chứng nào cho biết môi trường, dữ liệu và công cụ đã sẵn sàng?

### 1.2. Mức chi tiết phù hợp

Tài liệu cần đủ chi tiết để người có quyền và năng lực phù hợp thực hiện công việc, nhưng không nên chứa bí mật hoặc hướng dẫn thao tác có thể gây tác động ngoài phạm vi. Ví dụ, tài liệu có thể nêu tên secret, vị trí trong secret manager và owner; không ghi giá trị token hoặc private key.

Nên phân biệt:

- **Thông tin chiến lược:** mục đích, nguyên tắc, phạm vi, tiêu chí và trách nhiệm.
- **Thông tin vận hành:** cấu hình, endpoint, quy trình tạo dữ liệu, cách chạy test và khôi phục.
- **Thông tin nhạy cảm:** credential, dữ liệu cá nhân hoặc chi tiết hạ tầng bị hạn chế truy cập.

Tài liệu chiến lược có thể liên kết đến runbook hoặc kho lưu trữ được kiểm soát thay vì sao chép mọi chi tiết vào một nơi.

## 2. Cấu trúc đề xuất cho tài liệu chiến lược

Một cấu trúc nhất quán giúp người đọc tìm đúng thông tin và hỗ trợ rà soát khi có thay đổi.

| Phần | Nội dung chính | Kết quả mong đợi |
|---|---|---|
| Tổng quan và phạm vi | Mục đích, sản phẩm, thành phần, nhóm người dùng và loại kiểm thử. | Người đọc hiểu tài liệu áp dụng ở đâu. |
| Mục tiêu và rủi ro | Mục tiêu chất lượng, rủi ro ưu tiên và tiêu chí đánh giá. | Có căn cứ để chọn dữ liệu, môi trường và công cụ. |
| Dữ liệu kiểm thử | Nguồn, phân loại, mô hình, fixture, quyền, vòng đời và cleanup. | Dữ liệu có thể chuẩn bị và quản lý an toàn. |
| Môi trường | Danh mục, topology, cấu hình, phụ thuộc, truy cập và giới hạn. | Biết nơi chạy từng loại kiểm thử. |
| Công cụ | Danh mục, mục đích, phiên bản, tích hợp, quyền và owner. | Biết công cụ nào hỗ trợ từng bước. |
| Quy trình thực thi | Chuẩn bị, chạy, thu thập kết quả, xử lý lỗi và xác minh. | Các hoạt động có thể lặp lại. |
| Trách nhiệm | Vai trò, owner, RACI, hỗ trợ và escalation. | Biết ai làm, ai quyết định và ai cần được thông báo. |
| Quản lý thay đổi | Versioning, review, phê duyệt và lịch rà soát. | Tài liệu luôn phản ánh hiện trạng. |
| Giới hạn và ngoại lệ | Khác biệt môi trường, khoảng trống và rủi ro được chấp nhận. | Không diễn giải quá mức bằng chứng. |
| Phụ lục và liên kết | Runbook, dashboard, repository, risk register và biểu mẫu. | Có đường dẫn đến nguồn chi tiết. |

Không phải mọi dự án đều cần một tài liệu dài duy nhất. Có thể chia thành các trang hoặc tệp nhỏ theo chủ đề, miễn là có trang chỉ mục, owner, phiên bản và liên kết hai chiều rõ ràng.

### 2.1. Metadata của tài liệu

Phần đầu nên có:

- Tên tài liệu và mã định danh.
- Sản phẩm hoặc module áp dụng.
- Phạm vi và môi trường áp dụng.
- Người sở hữu tài liệu.
- Người review và người phê duyệt khi cần.
- Phiên bản, ngày hiệu lực và lần cập nhật gần nhất.
- Trạng thái: draft, review, approved, superseded hoặc archived.
- Tài liệu liên quan.
- Phân loại truy cập nếu có thông tin hạn chế.

Metadata giúp người đọc biết họ đang dùng bản nào và có thể hỏi ai khi phát hiện nội dung lỗi thời.

## 3. Mô tả dữ liệu kiểm thử

Dữ liệu kiểm thử là một phần của điều kiện kiểm thử, không chỉ là tập bản ghi để điền vào biểu mẫu. Tài liệu cần mô tả dữ liệu đại diện cho trạng thái nào, phục vụ mục tiêu gì, được tạo hoặc lấy từ đâu, ai quản lý và khi nào phải làm mới hoặc dọn dẹp.

### 3.1. Phân loại dữ liệu theo mục đích

Có thể phân loại theo:

- **Dữ liệu tổng hợp (synthetic):** được tạo riêng cho kiểm thử, không đại diện trực tiếp cho cá nhân hoặc khách hàng thật.
- **Dữ liệu đã ẩn danh:** dữ liệu nguồn đã được xử lý để giảm khả năng nhận diện cá nhân theo quy trình được phê duyệt.
- **Dữ liệu giả lập (mock/fake):** dữ liệu hoặc phản hồi do test double tạo ra để kiểm tra logic.
- **Dữ liệu seed:** dữ liệu nền ổn định được nạp khi khởi tạo môi trường.
- **Fixture theo test:** dữ liệu được tạo cho một test hoặc nhóm test.
- **Dữ liệu tải/hiệu năng:** dữ liệu có quy mô và phân bố phục vụ đo hiệu năng.
- **Dữ liệu migration:** tập dữ liệu dùng để xác minh chuyển đổi giữa schema hoặc phiên bản.
- **Dữ liệu sự cố đã kiểm soát:** dữ liệu mô phỏng tình huống lỗi, biên hoặc bất thường.

Mỗi loại có yêu cầu khác nhau về tính ổn định, tính đại diện, quyền truy cập và vòng đời. Không nên dùng một bộ dữ liệu chung cho mọi mục tiêu nếu điều đó làm mất khả năng cô lập hoặc tái lập.

### 3.2. Mô tả nguồn gốc dữ liệu

Với mỗi tập dữ liệu hoặc fixture, ghi:

- Mã hoặc tên định danh.
- Mục đích kiểm thử và rủi ro được hỗ trợ.
- Nguồn tạo: factory, script, seed, generator hoặc quy trình nhập.
- Phiên bản schema và phiên bản fixture.
- Các thực thể, quan hệ và trạng thái chính.
- Kích thước, phân bố và phạm vi giá trị nếu có.
- Cách tái tạo và điều kiện tiên quyết.
- Owner và nơi lưu trữ.
- Ngày tạo hoặc lần làm mới gần nhất.

Nếu dữ liệu được sinh bằng seed, ghi seed hoặc cách cấu hình để có thể tái tạo. Nếu dùng snapshot đã xử lý, ghi ngày snapshot, phương pháp xử lý và người phê duyệt nguồn dữ liệu.

### 3.3. Mô tả dữ liệu theo yêu cầu và rủi ro

Không cần liệt kê mọi bản ghi. Nên mô tả các đặc tính quan trọng để kiểm tra:

- Vai trò và trạng thái tài khoản.
- Quan hệ giữa tenant, người dùng và tài nguyên.
- Trạng thái nghiệp vụ như pending, approved, cancelled hoặc expired.
- Giá trị biên, rỗng, trùng, thiếu và không hợp lệ.
- Quy mô, phân bố và mức độ lệch.
- Dữ liệu lịch sử và quan hệ cha-con.
- Trường hợp concurrency, retry hoặc idempotency.
- Dữ liệu phục vụ phân quyền, quyền riêng tư và retention.

Ví dụ, để kiểm tra tenant isolation, tài liệu cần chỉ rõ có ít nhất hai tenant độc lập, người dùng thuộc các tenant, vai trò khác nhau và tài nguyên được gắn đúng tenant. Chỉ ghi “có dữ liệu khách hàng mẫu” là chưa đủ.

### 3.4. Phân loại và bảo vệ dữ liệu

Tài liệu nên chỉ ra dữ liệu nào:

- Công khai hoặc không nhạy cảm.
- Nội bộ.
- Nhạy cảm hoặc có thể chứa thông tin cá nhân.
- Bị giới hạn theo hợp đồng hoặc yêu cầu tuân thủ.
- Chỉ được sử dụng trong môi trường được phê duyệt.

Nêu nguyên tắc xử lý:

- Ưu tiên dữ liệu tổng hợp.
- Không sao chép dữ liệu production tùy tiện.
- Nếu cần dùng dữ liệu nguồn, phải có căn cứ và quy trình ẩn danh/giả danh phù hợp.
- Không ghi credential, token hoặc bí mật vào fixture, log và tài liệu.
- Giới hạn quyền truy cập theo vai trò và mục đích.
- Quy định thời hạn lưu, xóa và xác minh cleanup.
- Kiểm soát việc tải xuống hoặc chia sẻ dữ liệu.

Thay tên hoặc email không tự động làm dữ liệu trở thành ẩn danh nếu các thuộc tính khác vẫn có thể nhận diện cá nhân.

### 3.5. Tạo, làm mới và dọn dẹp

Tài liệu vận hành nên mô tả vòng đời:

1. Xác định test và trạng thái cần có.
2. Tạo dữ liệu bằng factory, seed hoặc generator đã quản lý.
3. Gán namespace, tenant hoặc mã lần chạy để cô lập.
4. Kiểm tra tính hợp lệ và quan hệ trước khi chạy.
5. Thực thi test và thu thập bằng chứng.
6. Giữ lại dữ liệu cần điều tra theo chính sách.
7. Dọn dẹp đúng tài nguyên do lần chạy sở hữu.
8. Kiểm tra dữ liệu tồn dư và làm mới theo lịch.

Cần phân biệt reset môi trường với xóa dữ liệu dùng chung. Một cleanup rộng có thể xóa dữ liệu của test khác hoặc người dùng khác. Tài liệu phải nêu phạm vi và quyền cần thiết trước khi thực hiện thao tác phá hủy.

### 3.6. Mẫu mô tả tập dữ liệu

~~~text
Data set ID:
Tên:
Mục tiêu kiểm thử / Risk ID:
Loại dữ liệu:
Nguồn tạo và phiên bản:
Schema/version:
Thực thể và trạng thái:
Kích thước / phân bố:
Seed hoặc cách tái tạo:
Mức phân loại dữ liệu:
Vị trí lưu trữ:
Quyền truy cập:
Owner:
Ngày tạo / làm mới:
Thời hạn lưu:
Cách cleanup:
Giới hạn đã biết:
~~~

## 4. Mô tả môi trường kiểm thử

Môi trường kiểm thử là tập hợp hạ tầng, ứng dụng, cấu hình, dữ liệu và phụ thuộc nơi hoạt động kiểm thử diễn ra. Tài liệu cần giúp người đọc biết môi trường nào phục vụ mục tiêu gì, cách truy cập hợp lệ, trạng thái sẵn sàng và những sai khác so với production.

### 4.1. Danh mục môi trường

Một hệ thống có thể có:

| Môi trường | Mục đích điển hình | Kiểm thử phù hợp |
|---|---|---|
| Local/development | Phát triển nhanh và debug. | Unit, component, thử nghiệm ban đầu. |
| Integration/test | Kiểm tra giao tiếp giữa thành phần. | API, contract, integration, migration. |
| QA/system | Kiểm tra hệ thống theo luồng và yêu cầu. | System, E2E, exploratory, regression. |
| Staging/pre-production | Xác minh gần điều kiện phát hành. | Release regression, smoke, UAT, kiểm tra cấu hình. |
| Performance | Đo tải và tài nguyên trong điều kiện kiểm soát. | Load, stress, spike, endurance. |
| Security | Kiểm tra bảo mật trong phạm vi được phép. | Security verification, penetration test theo kế hoạch. |
| Resilience/DR | Xác minh khả năng phục hồi. | Failover, backup/restore, chaos/resilience. |

Tên môi trường trong từng tổ chức có thể khác. Điều quan trọng là mục đích, phạm vi và giới hạn phải rõ ràng.

### 4.2. Thông tin kỹ thuật của môi trường

Với mỗi môi trường, mô tả:

- Environment ID, tên và owner.
- Vị trí hoặc vùng triển khai.
- Kiến trúc và topology ở mức cần thiết.
- Phiên bản ứng dụng, runtime và dependency.
- Database, broker, cache, storage và API phụ thuộc.
- Số instance, giới hạn CPU/memory và autoscaling nếu liên quan.
- Network boundary, DNS, TLS và cơ chế xác thực.
- Feature flag và cấu hình quan trọng.
- Cách triển khai, reset, rollback và kiểm tra health.
- Lịch bảo trì, thời gian sẵn sàng và hạn chế sử dụng.
- Mức tương đồng và khác biệt so với production.

Không cần công khai sơ đồ mạng nhạy cảm hoặc chi tiết có thể tạo rủi ro. Có thể liên kết tới kho tài liệu hạ tầng có kiểm soát.

### 4.3. Mô tả cấu hình và quản lý secrets

Tài liệu nên nêu tên và mục đích của cấu hình cần thiết, ví dụ timeout, retry, feature flag, locale, connection pool hoặc endpoint. Không lưu giá trị bí mật trực tiếp.

Với secrets, ghi:

- Loại secret hoặc danh tính dịch vụ.
- Hệ thống quản lý secret.
- Owner và quy trình yêu cầu quyền.
- Môi trường áp dụng.
- Quy trình rotation và thu hồi.
- Cách xử lý khi credential hết hạn hoặc bị lộ.

Mỗi môi trường nên dùng danh tính và bí mật riêng theo nguyên tắc tối thiểu quyền. Không dùng credential production để thuận tiện cho test.

### 4.4. Phụ thuộc và điều kiện sẵn sàng

Môi trường có thể phụ thuộc vào dịch vụ nội bộ hoặc nhà cung cấp ngoài. Tài liệu cần ghi:

- Tên phụ thuộc và mục đích.
- Owner nội bộ hoặc nhóm liên hệ.
- Endpoint hoặc định danh theo cơ chế truy cập được phép.
- Phiên bản/hợp đồng.
- Cách kiểm tra health.
- Sandbox, stub hay dịch vụ thật được dùng.
- Giới hạn quota, rate limit hoặc thời gian sẵn sàng.
- Hành vi dự phòng khi phụ thuộc không khả dụng.

Trước khi chạy test, nên có readiness check cho database, broker, identity provider, object storage và các dịch vụ quan trọng. Nếu một phụ thuộc không sẵn sàng, cần phân biệt test blocked với test failed do sản phẩm.

### 4.5. Mức tương đồng và giới hạn môi trường

Không phải môi trường nào cũng cần giống production ở mọi chiều. Hãy ghi sai khác ảnh hưởng đến mục tiêu:

- Khác engine hoặc phiên bản database.
- Ít instance hơn hoặc không có nhiều vùng.
- Dữ liệu nhỏ hơn hoặc phân bố khác.
- Dịch vụ ngoài dùng sandbox.
- Cấu hình bảo mật hoặc quyền khác.
- Không có autoscaling hoặc tải nền thực tế.

Với mỗi sai khác, ghi tác động có thể có, biện pháp kiểm tra thay thế và giới hạn của kết luận. Không diễn giải kết quả performance staging như dự báo production nếu tài nguyên và workload không tương đương.

### 4.6. Mẫu mô tả môi trường

~~~text
Environment ID:
Tên / mục đích:
Loại môi trường:
Owner / người hỗ trợ:
Vùng / vị trí triển khai:
Phiên bản ứng dụng / artifact:
Runtime và dependency:
Database / broker / cache / storage:
Topology và tài nguyên:
Cấu hình quan trọng:
Feature flags:
Cơ chế xác thực / quyền:
Phụ thuộc ngoài:
Health check:
Cách triển khai / reset / rollback:
Lịch bảo trì / giới hạn:
Khác biệt so với production:
Rủi ro và biện pháp thay thế:
Ngày xác minh gần nhất:
~~~

## 5. Mô tả công cụ kiểm thử

Danh mục công cụ giúp nhóm hiểu công cụ nào được dùng cho từng mục tiêu, ai duy trì và kết quả được lưu ở đâu. Chỉ liệt kê tên sản phẩm là chưa đủ; cần mô tả vai trò trong quy trình và giới hạn của công cụ.

### 5.1. Nhóm công cụ thường gặp

| Nhóm | Mục đích | Ví dụ loại chức năng |
|---|---|---|
| Test management | Quản lý test case, kế hoạch, kết quả và truy vết. | Test repository, execution record, coverage link. |
| Automation framework | Tự động thực thi test. | Unit, API, UI, contract, integration. |
| CI/CD platform | Điều phối build, test và deploy. | Pipeline, runner, artifact, gate. |
| API/client tools | Gửi request và kiểm tra contract. | HTTP client, schema validation, mock server. |
| Performance tools | Tạo tải và phân tích hiệu năng. | Load generator, profiler, metrics collector. |
| Security tools | Phân tích mã, dependency, cấu hình và ứng dụng. | SAST, DAST, SCA, secret scanning. |
| Data tools | Tạo, kiểm tra và đối soát dữ liệu. | Generator, migration validator, SQL client. |
| Observability tools | Thu thập bằng chứng vận hành. | Logs, metrics, traces, dashboards. |
| Defect/incident management | Theo dõi lỗi và sự cố. | Issue tracker, incident record, postmortem. |
| Collaboration/documentation | Chia sẻ quyết định và hướng dẫn. | Wiki, repository, review và approval. |

Tên công cụ cụ thể phụ thuộc tổ chức. Tài liệu cần ưu tiên chức năng, quy trình và owner thay vì giả định một sản phẩm duy nhất.

### 5.2. Thông tin cần ghi cho mỗi công cụ

- Tool ID và tên.
- Mục đích, loại kiểm thử hoặc quy trình được hỗ trợ.
- Owner và nhóm hỗ trợ.
- Phiên bản hoặc cách quản lý nâng cấp.
- Nơi cài đặt hoặc cách truy cập.
- Repository, plugin hoặc integration liên quan.
- Quyền truy cập và loại dữ liệu công cụ xử lý.
- Cách cấu hình và sử dụng chuẩn.
- Nơi lưu kết quả, log và artifact.
- Giới hạn, chi phí hoặc quota.
- Cách xử lý sự cố và phương án thay thế.
- Ngày rà soát gần nhất.

### 5.3. Phân biệt công cụ chuẩn và công cụ thử nghiệm

Có thể phân loại:

- **Approved/standard:** công cụ được tổ chức chấp nhận cho mục tiêu cụ thể.
- **Pilot/evaluation:** đang thử nghiệm, chưa dùng làm nguồn quyết định chính thức.
- **Legacy:** còn được duy trì cho hệ thống cũ hoặc giai đoạn chuyển đổi.
- **Deprecated:** không nên dùng cho công việc mới và có kế hoạch thay thế.
- **Prohibited/restricted:** không được dùng hoặc chỉ dùng trong phạm vi được phê duyệt.

Tình trạng phải có ngày hiệu lực, owner và kế hoạch chuyển đổi nếu cần. Tránh để một công cụ thử nghiệm âm thầm trở thành phụ thuộc bắt buộc của pipeline.

### 5.4. Tích hợp và luồng dữ liệu giữa công cụ

Tài liệu cần mô tả luồng chính, chẳng hạn:

1. Repository nhận thay đổi.
2. CI tạo build và chạy test.
3. Test framework gửi kết quả và artifact.
4. Test management hoặc dashboard nhận kết quả.
5. Defect tracker nhận lỗi được phân loại.
6. Observability lưu log, trace và metric.
7. Release process sử dụng trạng thái gate và bằng chứng.

Nêu nguồn dữ liệu chuẩn cho mỗi loại thông tin. Nếu kết quả được sao chép qua nhiều hệ thống, cần biết hệ thống nào là source of truth để tránh trạng thái không nhất quán.

### 5.5. Quản lý phiên bản và thay đổi công cụ

Nâng cấp framework, runner hoặc scanner có thể làm thay đổi kết quả. Cần có:

- Phiên bản đang dùng và phiên bản mục tiêu.
- Lý do nâng cấp.
- Phạm vi pipeline bị ảnh hưởng.
- Kiểm tra tương thích và thử nghiệm pilot.
- Kế hoạch rollback hoặc pin phiên bản khi cần.
- Người review và phê duyệt.
- Thời điểm triển khai và xác minh.

Không nên nâng cấp công cụ quan trọng đồng thời với thay đổi lớn về test hoặc môi trường nếu việc đó làm khó xác định nguyên nhân khi kết quả thay đổi.

### 5.6. Mẫu danh mục công cụ

~~~text
Tool ID:
Tên / nhóm:
Mục đích:
Loại kiểm thử hoặc quy trình:
Owner / nhóm hỗ trợ:
Phiên bản:
Trạng thái sử dụng:
Cách truy cập:
Tích hợp:
Quyền và dữ liệu xử lý:
Nơi lưu kết quả:
Giới hạn / quota / chi phí:
Runbook:
Phương án thay thế:
Ngày rà soát:
~~~

## 6. Mô tả trách nhiệm và quyền quyết định

Tài liệu phải làm rõ ai sở hữu từng phần công việc, ai trực tiếp thực hiện, ai có quyền phê duyệt và ai cần được thông báo. Không nên chỉ ghi tên nhóm chung chung nếu người đọc vẫn không biết phải liên hệ ai.

### 6.1. Các vai trò thường gặp

- **Test/QA owner:** duy trì test strategy, test case, test data và bằng chứng kiểm thử.
- **Developer/component owner:** chịu trách nhiệm về mã nguồn, hành vi và sửa lỗi thành phần.
- **Test automation/SDET:** duy trì framework, helper, pipeline test và độ tin cậy tự động hóa.
- **Environment/platform owner:** duy trì môi trường, runner, hạ tầng và phụ thuộc dùng chung.
- **Data owner:** quản lý nguồn dữ liệu, phân loại, quyền truy cập, chất lượng và vòng đời dữ liệu.
- **Tool owner:** quản lý công cụ, phiên bản, tích hợp và hỗ trợ.
- **Security/privacy owner:** tư vấn hoặc phê duyệt các yêu cầu bảo mật, quyền riêng tư và xử lý dữ liệu.
- **Product/business owner:** xác nhận quy tắc nghiệp vụ, mức ưu tiên và tiêu chí chấp nhận.
- **Release owner:** điều phối release gate và quyết định phát hành trong phạm vi thẩm quyền.
- **Incident coordinator:** điều phối sự cố cần nhiều nhóm tham gia.

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ. Điều quan trọng là phạm vi trách nhiệm và quyền quyết định phải rõ.

### 6.2. RACI

RACI giúp tránh tình trạng mọi người cùng được thông báo nhưng không ai chịu trách nhiệm cuối cùng:

- **R — Responsible:** thực hiện công việc.
- **A — Accountable:** chịu trách nhiệm cuối cùng và bảo đảm kết quả.
- **C — Consulted:** được tham vấn.
- **I — Informed:** được thông báo.

Ví dụ:

| Hoạt động | QA/Test Owner | Developer | Data Owner | Platform Owner | Tool Owner | Release Owner |
|---|---|---|---|---|---|---|
| Xác định mục tiêu và phạm vi test | A/R | C | C | C | I | I |
| Thiết kế test data | R | C | A | C | I | I |
| Phân loại và cấp quyền dữ liệu | C | I | A/R | C | I | I |
| Cấp phát môi trường | C | I | C | A/R | C | I |
| Duy trì framework test | A/R hoặc R | C | I | C | C | I |
| Nâng cấp công cụ dùng chung | C | C | I | C | A/R | I |
| Phân tích lỗi sản phẩm | R/C | A/R | C | C | I | I |
| Khôi phục môi trường | C | I | C | A/R | C | I |
| Chấp nhận ngoại lệ release gate | C | C | C | C | I | A/R |
| Rà soát tài liệu chiến lược | A/R | C | C | C | C | I |

Ma trận chỉ là ví dụ. Cần điều chỉnh theo cơ cấu thật và xác định một A cho mỗi hoạt động hoặc quyết định. Có thể có nhiều người R ở các phần việc khác nhau, nhưng cần một đầu mối điều phối.

### 6.3. Owner và người thay thế

Với mỗi tài sản quan trọng, ghi:

- Owner chính.
- Người thay thế hoặc nhóm dự phòng.
- Kênh liên hệ và thời gian hỗ trợ.
- Phạm vi quyền hạn.
- Quy trình bàn giao.
- Tài liệu/runbook liên quan.

Nếu chỉ một người biết reset dữ liệu hoặc khôi phục môi trường, nhóm có rủi ro phụ thuộc cá nhân. Cần tạo người dự phòng thông qua pairing, tài liệu hóa và thực hành chuyển giao.

### 6.4. Escalation và quyết định

Nêu rõ khi nào cần escalation:

- Dữ liệu có nguy cơ bị lộ hoặc sử dụng sai mục đích.
- Môi trường dùng chung không sẵn sàng và chặn nhiều nhóm.
- Công cụ gây mất kết quả hoặc làm sai trạng thái gate.
- Phụ thuộc ngoài không đáp ứng thời hạn.
- Không có owner tiếp nhận trong thời gian quy định.
- Rủi ro chưa được kiểm soát trước release.

Tài liệu cần chỉ ra người điều phối, cấp quyết định và thông tin phải bàn giao. Không mặc định người vận hành công cụ có quyền chấp nhận rủi ro sản phẩm.

## 7. Liên kết dữ liệu, môi trường, công cụ và trách nhiệm

Bốn nhóm thông tin chỉ hữu ích khi có thể truy vết qua lại.

Ví dụ một integration test cần:

- Data set TENANT-ISOLATION-SET do Data Owner duy trì.
- Environment QA-INTEGRATION do Platform Owner duy trì.
- API test framework và CI pipeline do Test Automation/Tool Owner duy trì.
- Test case API-ACL-021 do QA/Test Owner sở hữu.
- Component API do Developer/Component Owner chịu trách nhiệm.
- Quyết định release do Release Owner quản lý.

Khi test thất bại, người điều tra có thể lần theo từng liên kết để xác định dữ liệu sai, môi trường không sẵn sàng, công cụ lỗi hay hành vi sản phẩm không đúng.

### 7.1. Mô hình liên kết

~~~mermaid
flowchart TD
    STRATEGY[Chiến lược và mục tiêu kiểm thử] --> DATA[Dữ liệu kiểm thử]
    STRATEGY --> ENV[Môi trường]
    STRATEGY --> TOOL[Công cụ]
    STRATEGY --> ROLE[Trách nhiệm]
    DATA --> TEST[Test case / test run]
    ENV --> TEST
    TOOL --> TEST
    ROLE --> TEST
    TEST --> EVIDENCE[Kết quả và bằng chứng]
    EVIDENCE --> DEFECT[Defect / risk]
    DEFECT --> CHANGE[Thay đổi và build]
    CHANGE --> VERIFY[Xác minh lại]
    VERIFY --> OWNER[Owner xác nhận]
~~~

### 7.2. Mã định danh và liên kết

Dùng mã định danh ổn định cho các tài sản, ví dụ:

- DATA-... cho tập dữ liệu.
- ENV-... cho môi trường.
- TOOL-... cho công cụ.
- TEST-... cho test case hoặc nhóm test.
- RISK-... cho rủi ro.
- DEF-... cho defect.
- ROLE-... hoặc mã nhóm cho vai trò/owner.

Quy ước mã cần thống nhất và tránh tái sử dụng ID đã retire. Nếu tên hiển thị thay đổi, ID ổn định giúp giữ liên kết lịch sử.

### 7.3. Nguồn dữ liệu chuẩn

Chỉ định hệ thống chuẩn cho từng loại thông tin:

| Thông tin | Nguồn chuẩn có thể dùng |
|---|---|
| Yêu cầu và tiêu chí chấp nhận | Requirement/backlog management. |
| Test case và test run | Test management hoặc repository kiểm thử. |
| Defect và incident | Issue/incident tracker. |
| Build và artifact | CI system và artifact registry. |
| Môi trường và cấu hình | Infrastructure/configuration repository. |
| Dữ liệu kiểm thử | Data catalog hoặc repository fixture được kiểm soát. |
| Công cụ và quyền truy cập | Tool catalog hoặc service ownership registry. |
| Trách nhiệm và escalation | Ownership directory/runbook. |
| Tài liệu chiến lược | Kho tài liệu được quản lý phiên bản. |

Không nên duy trì cùng một danh sách owner hoặc endpoint bằng tay ở nhiều tài liệu. Hãy liên kết đến nguồn chuẩn và ghi ngày đồng bộ nếu cần.

## 8. Quy trình chuẩn bị trước khi thực thi kiểm thử

Tài liệu nên mô tả điều kiện sẵn sàng trước khi chạy để giảm lỗi do thiếu dữ liệu, môi trường hoặc quyền.

### 8.1. Checklist readiness

1. Xác nhận phạm vi, build và loại kiểm thử.
2. Kiểm tra môi trường đúng mục đích và đang sẵn sàng.
3. Xác minh phiên bản ứng dụng, schema và dependency.
4. Kiểm tra dữ liệu đã được tạo, hợp lệ và đúng namespace.
5. Xác nhận quyền truy cập theo vai trò.
6. Kiểm tra công cụ, runner, plugin và phiên bản.
7. Kiểm tra phụ thuộc ngoài, quota và health.
8. Xác nhận người thực hiện và người hỗ trợ.
9. Kiểm tra vị trí lưu log, report và artifact.
10. Ghi nhận giới hạn hoặc điều kiện chưa đáp ứng trước khi bắt đầu.

### 8.2. Phân loại lỗi chuẩn bị

Nếu không thể chạy test, cần ghi đúng trạng thái:

- **Blocked:** điều kiện tiên quyết hoặc phụ thuộc không sẵn sàng.
- **Environment failure:** môi trường không hoạt động theo yêu cầu.
- **Data setup failure:** không tạo hoặc nạp được dữ liệu.
- **Tool failure:** công cụ hoặc runner không thực thi đúng.
- **Test failure:** test đã chạy và phát hiện hành vi không đạt.
- **Inconclusive:** đã chạy nhưng bằng chứng không đủ kết luận.

Không ghi mọi trường hợp thành “test failed”. Phân loại đúng giúp chuyển đúng owner và tránh báo cáo sai chất lượng sản phẩm.

### 8.3. Bằng chứng readiness

Có thể lưu:

- Environment health check.
- Build ID và artifact digest.
- Data set/version và namespace.
- Tool/version.
- Test suite/version.
- Người xác nhận và thời điểm.
- Các điều kiện bị giới hạn.

Mức bằng chứng nên tương xứng với rủi ro và quy mô hoạt động.

## 9. Quản lý thay đổi dữ liệu, môi trường và công cụ

Bất kỳ thay đổi nào trong bốn nhóm thông tin đều có thể ảnh hưởng kết quả kiểm thử. Ví dụ, thay đổi schema làm fixture cũ không hợp lệ; nâng cấp runner làm thay đổi thời gian chạy; đổi quyền service account khiến test integration bị chặn.

### 9.1. Các thay đổi cần được ghi nhận

- Thêm, sửa hoặc retire tập dữ liệu.
- Thay đổi schema, seed, generator hoặc quy trình ẩn danh.
- Tạo, xóa hoặc nâng cấp môi trường.
- Thay đổi topology, network, secrets hoặc feature flag.
- Nâng cấp framework, scanner, plugin hoặc runner.
- Thay đổi owner, nhóm hỗ trợ hoặc quyền quyết định.
- Thay đổi lịch bảo trì, quota hoặc điều kiện truy cập.

### 9.2. Quy trình thay đổi

1. Đề xuất thay đổi và nêu lý do.
2. Xác định tài sản, test, requirement và risk bị ảnh hưởng.
3. Đánh giá bảo mật, tương thích, vận hành và chi phí.
4. Xác định owner, reviewer và người phê duyệt.
5. Chuẩn bị kế hoạch kiểm tra và rollback.
6. Thực hiện thay đổi trong phạm vi được phép.
7. Xác minh dữ liệu, môi trường, công cụ hoặc ownership mới.
8. Cập nhật tài liệu và liên kết.
9. Thông báo nhóm bị ảnh hưởng.
10. Theo dõi kết quả sau thay đổi.

### 9.3. Quản lý phiên bản tài liệu

Mỗi thay đổi quan trọng nên ghi:

- Phiên bản trước và sau.
- Ngày thay đổi.
- Người thực hiện.
- Lý do.
- Nội dung thay đổi.
- Tài sản và test bị ảnh hưởng.
- Kết quả review/approval.
- Bằng chứng xác minh.
- Kế hoạch rollback hoặc xử lý nếu có vấn đề.

Không nên chỉ ghi “cập nhật môi trường” mà không cho biết thay đổi phiên bản hoặc cấu hình nào.

## 10. Quy trình rà soát và duy trì tài liệu

Tài liệu chỉ hữu ích nếu phản ánh trạng thái hiện tại. Cần có lịch rà soát và sự kiện kích hoạt cập nhật.

### 10.1. Sự kiện cần cập nhật

- Sản phẩm thêm hoặc loại bỏ thành phần.
- Mô hình dữ liệu hoặc schema thay đổi.
- Môi trường được tạo mới, hợp nhất hoặc retire.
- Công cụ hoặc framework nâng cấp.
- Thay đổi quyền truy cập hoặc chính sách bảo mật.
- Thay đổi nhóm, owner hoặc nhà cung cấp.
- Incident cho thấy runbook hoặc thông tin tài liệu sai.
- Release mới làm thay đổi quy trình kiểm thử.
- Audit hoặc review phát hiện nội dung thiếu.

### 10.2. Chu kỳ rà soát

Có thể rà soát theo quý, theo release lớn hoặc theo mức độ biến động. Tài liệu về dữ liệu nhạy cảm, quyền truy cập và môi trường production-like có thể cần chu kỳ ngắn hơn tài liệu công cụ ít thay đổi.

Mỗi lần review cần xác nhận:

- Liên kết còn hoạt động.
- Owner vẫn đúng.
- Phiên bản và cấu hình còn hiện hành.
- Hướng dẫn không chứa thao tác nguy hiểm hoặc thông tin bí mật.
- Các giới hạn và ngoại lệ vẫn được chấp nhận.
- Các tài sản đã retire được đánh dấu rõ.
- Tài liệu liên quan không mâu thuẫn.

### 10.3. Trạng thái tài liệu

Có thể dùng các trạng thái:

- **Draft:** đang soạn, chưa dùng làm hướng dẫn chuẩn.
- **In review:** đang được kiểm tra.
- **Approved/current:** đã được phê duyệt và còn hiệu lực.
- **Superseded:** đã có bản mới thay thế.
- **Archived:** lưu để tham chiếu lịch sử, không dùng cho công việc mới.

Cần hiển thị rõ trạng thái để người đọc không dùng nhầm bản nháp hoặc tài liệu đã lỗi thời.

## 11. Ví dụ tổng hợp: tài liệu cho kiểm thử API nhiều tenant

Một nền tảng SaaS có API quản lý khách hàng và đơn hàng. Nhóm cần kiểm tra quyền truy cập, tính toàn vẹn dữ liệu và hành vi API trước release.

### 11.1. Dữ liệu

Tài liệu ghi tập DATA-TENANT-ACL gồm:

- Tenant Alpha và Beta.
- User Admin, Staff và Viewer.
- Membership active và suspended.
- Khách hàng và đơn hàng thuộc từng tenant.
- Một số trường hợp ID hợp lệ nhưng thuộc tenant khác.
- Seed và factory để tái tạo.
- Dữ liệu tổng hợp, không chứa thông tin khách hàng thật.
- Owner chịu trách nhiệm cập nhật schema và cleanup.

### 11.2. Môi trường

Môi trường ENV-API-QA có:

- Phiên bản API và database được ghi nhận.
- Hai tenant dữ liệu tổng hợp.
- Identity provider thử nghiệm.
- TLS và service identity theo cấu hình kiểm thử.
- API gateway và database test.
- Health check và hướng dẫn reset namespace.
- Giới hạn: không có topology nhiều vùng như production.

### 11.3. Công cụ

Danh mục ghi:

- TOOL-API-TEST: framework chạy API/contract test.
- TOOL-CI: pipeline thực thi test theo commit.
- TOOL-OBS: log và trace để điều tra request.
- TOOL-DEFECT: nơi quản lý defect và liên kết test run.

Với mỗi công cụ có phiên bản, owner, cách truy cập, nơi lưu report và phương án khi dịch vụ không sẵn sàng.

### 11.4. Trách nhiệm

- QA/Test Owner duy trì test case, mục tiêu và kết quả.
- Data Owner quản lý fixture, seed và cleanup.
- Platform Owner duy trì môi trường và identity provider thử nghiệm.
- Tool Owner duy trì framework, runner và tích hợp CI.
- API Component Owner điều tra và sửa hành vi API.
- Release Owner quyết định tiếp tục hoặc chặn release theo các gate.

### 11.5. Khi test phát hiện truy cập chéo tenant

Người thực hiện liên kết test run với build, environment và data set. Bằng chứng gồm request/response đã loại bỏ thông tin nhạy cảm, trace ID và trạng thái dữ liệu. Defect được liên kết với yêu cầu tenant isolation và rủi ro rò rỉ dữ liệu. Component Owner xử lý API; Test Owner xác nhận test và retest; Platform Owner hỗ trợ nếu cấu hình môi trường có liên quan. Sau bản sửa, test được chạy lại trên artifact xác định và các kiểm tra truy cập danh sách, chi tiết, tìm kiếm và export được đánh giá theo phạm vi ảnh hưởng.

Ví dụ cho thấy tài liệu dữ liệu, môi trường, công cụ và trách nhiệm phải liên kết với nhau để sự cố có thể được tái hiện, xử lý và xác minh.

## 12. Những sai lầm thường gặp

- **Chỉ liệt kê tên dữ liệu:** không có nguồn, mục tiêu, quyền hoặc cách tái tạo.
- **Dùng dữ liệu production không kiểm soát:** tạo rủi ro quyền riêng tư và bảo mật.
- **Không phân biệt seed và fixture theo test:** dễ gây phụ thuộc thứ tự và xung đột.
- **Chỉ ghi tên môi trường:** thiếu phiên bản, cấu hình, phụ thuộc và giới hạn.
- **Coi staging mặc nhiên giống production:** không đánh giá sai khác theo mục tiêu.
- **Ghi secret trực tiếp vào tài liệu:** làm lộ credential và khó quản lý rotation.
- **Chỉ liệt kê công cụ mà không có owner:** không biết ai nâng cấp hoặc xử lý sự cố.
- **Không ghi phiên bản công cụ:** kết quả khó tái lập sau nâng cấp.
- **Duy trì nhiều nguồn thông tin thủ công:** tạo mâu thuẫn giữa tài liệu.
- **RACI có nhiều người chịu trách nhiệm cuối cùng:** không rõ quyền quyết định.
- **Không có người thay thế:** công việc dừng khi owner vắng mặt.
- **Không cập nhật sau incident:** hướng dẫn tiếp tục chứa giả định sai.
- **Tài liệu không có ngày review:** người đọc không biết nội dung còn hiệu lực.
- **Chỉ ghi quy trình lý tưởng:** bỏ qua blocked, phụ thuộc và phương án khôi phục.

## 13. Checklist hoàn thiện phần dữ liệu, môi trường, công cụ và trách nhiệm

- [ ] Tài liệu có mục đích, phạm vi, owner, phiên bản và trạng thái rõ ràng.
- [ ] Dữ liệu được phân loại theo mục tiêu và mức nhạy cảm.
- [ ] Nguồn, schema, seed, fixture và cách tái tạo được ghi.
- [ ] Quyền truy cập, retention và cleanup dữ liệu được mô tả.
- [ ] Môi trường có ID, mục đích, owner và danh mục phụ thuộc.
- [ ] Phiên bản, topology, cấu hình và giới hạn môi trường được ghi.
- [ ] Secrets được quản lý qua cơ chế phù hợp, không lưu giá trị trong tài liệu.
- [ ] Khác biệt so với production và tác động đến kết luận được nêu.
- [ ] Công cụ có mục đích, phiên bản, trạng thái, owner và cách hỗ trợ.
- [ ] Luồng tích hợp và nguồn dữ liệu chuẩn được xác định.
- [ ] Trách nhiệm có owner chính, người thay thế và quyền quyết định.
- [ ] RACI không mơ hồ về Accountable.
- [ ] Quy trình readiness và phân loại blocked/failure được mô tả.
- [ ] Có quy trình thay đổi, review, approval và rollback.
- [ ] Tài liệu có chu kỳ rà soát và sự kiện kích hoạt cập nhật.
- [ ] Liên kết tới test, risk, build, defect, runbook và dashboard còn hiệu lực.
- [ ] Ngoại lệ, khoảng trống và giới hạn được ghi rõ.
- [ ] Có ví dụ hoặc biểu mẫu giúp người khác áp dụng nhất quán.

## Kết luận

Tài liệu chiến lược kiểm thử cần mô tả dữ liệu, môi trường, công cụ và trách nhiệm như những phần liên kết của cùng một hệ thống vận hành. Dữ liệu phải có nguồn, mục tiêu, phân loại, quyền và vòng đời; môi trường cần có mục đích, cấu hình, phụ thuộc và giới hạn; công cụ cần có vai trò, phiên bản, tích hợp và owner; trách nhiệm cần xác định người thực hiện, người chịu trách nhiệm cuối cùng, người hỗ trợ và đường escalation. Hãy quản lý các thông tin này bằng định danh ổn định, nguồn dữ liệu chuẩn, versioning và review theo thay đổi. Khi tài liệu phản ánh đúng điều kiện thực tế và được duy trì bởi các owner rõ ràng, nhóm có thể chuẩn bị kiểm thử nhất quán, tái hiện sự cố, phối hợp khôi phục và đánh giá kết quả với bằng chứng đáng tin cậy.
