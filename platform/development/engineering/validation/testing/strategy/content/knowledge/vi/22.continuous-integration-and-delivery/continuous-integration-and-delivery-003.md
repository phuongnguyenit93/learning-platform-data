# Chạy kiểm tra rộng trên sản phẩm đã đóng gói và triển khai

Trong module **VALIDATION_TESTING_STRATEGY**, kiểm thử trên mã nguồn và kiểm thử trên sản phẩm đã đóng gói, triển khai cung cấp những loại bằng chứng khác nhau. Một bộ kiểm thử chạy trực tiếp trong môi trường phát triển có thể xác nhận logic hoặc một số tương tác, nhưng chưa chứng minh gói phát hành được tạo đúng, cấu hình triển khai hoạt động, các dịch vụ phối hợp chính xác hay hệ thống vận hành ổn định sau khi cài đặt.

**Kiểm tra rộng trên sản phẩm đã đóng gói và triển khai** là hoạt động xác minh bản dựng có thể phát hành trong hình thức gần với cách sản phẩm sẽ được phân phối và vận hành. Phạm vi có thể gồm kiểm tra tính toàn vẹn của artifact, cài đặt và cấu hình, smoke test, integration test, E2E, kiểm tra dữ liệu và migration, hiệu năng, bảo mật, khả năng phục hồi và giám sát. Mỗi nhóm kiểm tra trả lời một câu hỏi khác nhau; cần lựa chọn theo rủi ro và đặc điểm sản phẩm.

Bài học này hướng dẫn cách tổ chức các kiểm tra sau khi đóng gói và sau triển khai trong CI/CD, quản lý artifact xuyên suốt các môi trường, xác định ma trận kiểm tra, thiết lập cổng chất lượng, xử lý lỗi và flaky test, cũng như sử dụng bằng chứng để quyết định promotion, rollback hoặc phát hành. Mục tiêu là xác nhận đúng sản phẩm sẽ được triển khai, trong cấu hình dự kiến, với các hành vi và thuộc tính chất lượng cần thiết.

## 1. Vì sao cần kiểm tra sản phẩm đã đóng gói và triển khai?

### 1.1. Mã nguồn đạt kiểm thử chưa đồng nghĩa gói phát hành đạt

Giữa mã nguồn và sản phẩm đang chạy có nhiều bước có thể tạo ra lỗi:

- Build có thể bỏ sót tài nguyên, file cấu hình hoặc dependency.
- Đóng gói có thể đưa nhầm phiên bản thư viện hoặc thiếu file.
- Image container có thể dùng base image, quyền hoặc entrypoint không phù hợp.
- Cấu hình môi trường có thể sai endpoint, secret reference hoặc feature flag.
- Migration có thể không tương thích với schema đang tồn tại.
- Khởi động dịch vụ có thể thất bại do thứ tự phụ thuộc.
- Gateway, DNS, TLS, routing hoặc service discovery có thể cấu hình sai.
- Các dịch vụ có thể không tương thích về phiên bản hợp đồng.
- Hành vi chỉ xuất hiện khi nhiều instance chạy đồng thời hoặc khi tải tăng.

Unit test và component test thường chạy trong điều kiện kiểm soát. Chúng vẫn rất quan trọng, nhưng không thể thay thế việc kiểm tra artifact và hệ thống đã triển khai.

### 1.2. Kiểm tra artifact và kiểm tra deployment là hai phạm vi liên quan

- **Kiểm tra artifact sau đóng gói:** xác nhận gói phát hành có đúng nội dung, phiên bản, dependency, cấu trúc và metadata.
- **Kiểm tra sau triển khai:** xác nhận artifact được cài đặt hoặc triển khai đúng, dịch vụ khởi động, kết nối và thực hiện hành vi dự kiến trong môi trường.
- **Kiểm tra sau promotion:** xác nhận cùng artifact được đưa sang môi trường tiếp theo với cấu hình phù hợp và không bị thay thế ngoài ý muốn.

Ví dụ, một container image có thể được build thành công và vượt qua kiểm tra bảo mật cơ bản. Sau khi triển khai, dịch vụ vẫn có thể không kết nối được database vì secret hoặc network policy sai. Ngược lại, health endpoint có thể trả thành công nhưng API nghiệp vụ vẫn không xử lý đúng đơn hàng. Vì vậy, cần kiểm tra ở nhiều lớp.

### 1.3. Mục tiêu của kiểm tra rộng

Một chiến lược tốt giúp trả lời:

- Artifact có đúng phiên bản và có thể truy xuất nguồn gốc không?
- Gói có đầy đủ, toàn vẹn và được tạo theo quy trình đáng tin cậy không?
- Cài đặt, khởi động và cấu hình có thành công không?
- Dịch vụ có kết nối đúng các phụ thuộc không?
- Hành trình nghiệp vụ chính có hoạt động trong môi trường triển khai không?
- Dữ liệu và migration có được xử lý an toàn không?
- Các thuộc tính như hiệu năng, bảo mật, khả năng phục hồi có đạt mục tiêu không?
- Hệ thống có thể quan sát, phát hiện lỗi và phục hồi không?
- Có đủ bằng chứng để promotion hoặc phát hành không?

Không phải mọi bản dựng đều cần chạy toàn bộ kiểm thử dài. Phạm vi cần phân tầng: kiểm tra nhanh cho mọi artifact, kiểm tra tích hợp và hành trình cho môi trường phù hợp, kiểm tra sâu theo rủi ro trước các mốc phát hành.

## 2. Phân biệt các giai đoạn kiểm tra trong CI/CD

### 2.1. Từ mã nguồn đến artifact

Một pipeline khái quát:

~~~mermaid
flowchart TD
    A[Commit / Pull Request] --> B[Build và unit/component tests]
    B --> C[Đóng gói artifact]
    C --> D[Kiểm tra artifact và dependency]
    D --> E[Triển khai môi trường kiểm thử]
    E --> F[Smoke và deployment checks]
    F --> G[Integration và API tests]
    G --> H[E2E và kiểm tra nghiệp vụ]
    H --> I[Non-functional checks theo rủi ro]
    I --> J{Quality gates đạt?}
    J -- Không --> K[Điều tra, sửa hoặc dừng promotion]
    J -- Có --> L[Promotion cùng artifact]
    L --> M[Post-deployment verification]
    M --> N[Theo dõi và quyết định tiếp theo]
~~~

Thứ tự cụ thể phụ thuộc công nghệ và thời gian chạy. Các kiểm tra rẻ, nhanh nên chạy sớm; kiểm tra cần hạ tầng hoặc nhiều dịch vụ có thể chạy sau khi artifact được tạo và triển khai vào môi trường phù hợp.

### 2.2. Kiểm tra trước khi đóng gói

Các kiểm tra ở mã nguồn vẫn là nền tảng:

- Compile và static analysis.
- Unit, component và contract tests.
- Kiểm tra dependency, license và cấu hình.
- Review thay đổi và test coverage theo rủi ro.

Mục tiêu là phát hiện lỗi sớm, trước khi tốn chi phí tạo và triển khai artifact. Tuy nhiên, kết quả ở giai đoạn này chưa xác nhận nội dung gói cuối cùng hoặc cách sản phẩm hoạt động sau triển khai.

### 2.3. Kiểm tra ngay sau đóng gói

Sau khi build, kiểm tra:

- Tên, phiên bản và mã định danh artifact.
- Manifest, metadata và cấu trúc file.
- Dependency được đóng gói và phiên bản thực tế.
- Checksum hoặc chữ ký nếu quy trình yêu cầu.
- SBOM và thông tin nguồn build.
- File cấu hình mặc định và tài nguyên cần thiết.
- Không chứa secret, file phát triển hoặc dữ liệu không được phép.
- Artifact có thể được tải, giải nén hoặc khởi chạy trong môi trường kiểm tra.

Đối với container, có thể kiểm tra image metadata, entrypoint, user chạy, package, layer và cấu hình mặc định. Đối với ứng dụng desktop hoặc mobile, cần kiểm tra package, chữ ký, manifest, quyền và tài nguyên đi kèm. Với thư viện, cần kiểm tra package, version, dependency và khả năng tiêu thụ từ repository.

### 2.4. Kiểm tra sau triển khai

Khi artifact đã được triển khai, xác minh:

- Deployment hoàn tất và đúng phiên bản.
- Instance hoặc pod sẵn sàng theo tiêu chí.
- Cấu hình môi trường và secret reference hợp lệ.
- Health và readiness checks phản ánh đúng trạng thái.
- Kết nối database, cache, queue và dịch vụ phụ thuộc.
- API hoặc giao diện có thể truy cập qua đường dẫn thực tế.
- Log, metrics và tracing hoạt động.
- Smoke test và các hành trình chính đạt.
- Không có migration hoặc tác vụ nền bị kẹt.

Health check chỉ là một phần bằng chứng. Một dịch vụ có thể trả `200 OK` ở endpoint health nhưng chức năng quan trọng vẫn lỗi. Cần phân biệt liveness, readiness và kiểm tra nghiệp vụ.

## 3. Quản lý artifact xuyên suốt pipeline

### 3.1. Build một lần, promotion cùng artifact

Một nguyên tắc quan trọng là tạo artifact từ một phiên bản mã xác định rồi đưa chính artifact đó qua các môi trường. Tránh build lại từ cùng commit cho từng môi trường nếu quá trình build có thể tạo ra nội dung khác nhau.

Lợi ích:

- Giảm nguy cơ staging và production chạy artifact khác nhau.
- Dễ truy vết từ kết quả kiểm thử về commit và build.
- Có thể xác minh checksum hoặc digest xuyên suốt.
- Dễ điều tra khi một phiên bản gây lỗi.
- Hỗ trợ rollback về artifact đã biết.

Cấu hình môi trường nên được quản lý riêng theo cơ chế an toàn. Không nhúng secret hoặc dữ liệu môi trường vào artifact chung nếu có thể cung cấp qua secret manager hoặc cấu hình triển khai.

### 3.2. Định danh và truy xuất nguồn gốc

Mỗi artifact nên có định danh duy nhất, chẳng hạn:

- Commit SHA hoặc revision.
- Build ID.
- Version hoặc release candidate.
- Container image digest.
- Package checksum.
- Thời điểm build.
- Phiên bản công cụ và dependency.
- Metadata về quy trình build.

Tag như `latest` không đủ để xác định chính xác artifact vì nó có thể trỏ sang nội dung khác theo thời gian. Với container, digest bất biến là cách tham chiếu chính xác hơn tag có thể thay đổi.

### 3.3. Kiểm tra tính toàn vẹn và nguồn gốc

Tùy quy trình phát hành, kiểm tra:

- Checksum có khớp với artifact được lưu không?
- Chữ ký có hợp lệ và thuộc danh tính được tin cậy không?
- Artifact có được tạo bởi pipeline được phê duyệt không?
- Build provenance có liên kết với source revision không?
- Dependency có được lấy từ nguồn được phép không?
- SBOM có được tạo và lưu cùng bản phát hành không?

Checksum giúp phát hiện thay đổi nội dung; chữ ký và provenance giúp đánh giá nguồn gốc và tính xác thực. Chúng không thay thế kiểm thử chức năng, nhưng là bằng chứng quan trọng để bảo đảm đúng sản phẩm được kiểm tra và phát hành.

### 3.4. Kiểm tra dependency và nội dung đóng gói

Artifact có thể chứa dependency khác với những gì nhóm nghĩ đang dùng. Kiểm tra:

- Phiên bản thực tế của thư viện và runtime.
- Dependency bắc cầu.
- Thành phần lỗi thời hoặc có lỗ hổng đã biết.
- License và điều kiện phân phối.
- Package không cần thiết hoặc không được phép.
- File cấu hình, chứng thư mẫu hoặc secret vô tình bị đóng gói.
- Tài nguyên và migration scripts cần cho triển khai.

Kết quả cần gắn với artifact digest hoặc package version. Nếu artifact được thay đổi sau khi quét, cần chạy lại các kiểm tra áp dụng cho nội dung mới.

## 4. Xác minh cài đặt, khởi động và cấu hình

### 4.1. Kiểm tra cài đặt hoặc triển khai

Với sản phẩm đã đóng gói, xác minh quy trình cài đặt hoặc triển khai trong môi trường mục tiêu:

- Package được tải từ đúng repository.
- Phiên bản và checksum đúng.
- Cài đặt hoặc rollout hoàn tất.
- Quyền file, user và thư mục phù hợp.
- Cấu hình được nạp đúng nguồn.
- Secret reference được phân giải thành công.
- Dịch vụ khởi động theo thứ tự phụ thuộc cần thiết.
- Upgrade từ phiên bản cũ được hỗ trợ.
- Gỡ cài đặt hoặc rollback không làm hỏng dữ liệu ngoài dự kiến.

Một deployment có thể được đánh dấu hoàn tất bởi hệ thống điều phối dù ứng dụng chưa sẵn sàng phục vụ. Cần kiểm tra trạng thái thực của dịch vụ và các hành vi quan trọng.

### 4.2. Liveness, readiness và startup checks

Ba khái niệm thường gặp:

- **Liveness:** tiến trình có còn hoạt động hay không; nếu thất bại liên tục, nền tảng có thể khởi động lại container hoặc instance.
- **Readiness:** dịch vụ đã sẵn sàng nhận lưu lượng hay chưa; nếu chưa, cần tránh gửi request đến instance đó.
- **Startup probe/check:** cho phép ứng dụng có thời gian khởi động ban đầu trước khi áp dụng các kiểm tra tiếp theo.

Không nên đưa mọi phụ thuộc bên ngoài vào liveness check. Nếu dịch vụ thanh toán tạm thời không sẵn sàng, việc liên tục restart một dịch vụ vẫn có thể xử lý các chức năng khác có thể làm tình hình xấu hơn. Readiness cần phản ánh khả năng phục vụ các request mà dịch vụ được kỳ vọng xử lý.

### 4.3. Kiểm tra cấu hình theo môi trường

So sánh các cấu hình có ảnh hưởng đến hành vi:

- Endpoint và URL dịch vụ.
- Database connection và pool.
- Timeout, retry và circuit breaker.
- Cache TTL và giới hạn bộ nhớ.
- Queue, topic và consumer group.
- Feature flag.
- Locale, timezone và định dạng.
- Logging, tracing và mức sampling.
- TLS, certificate và chính sách xác thực.
- Resource requests/limits và autoscaling.

Không đưa giá trị secret vào log hoặc báo cáo. Có thể kiểm tra nguồn secret, phiên bản secret hoặc trạng thái phân giải mà không tiết lộ nội dung.

### 4.4. Kiểm tra migration và tương thích dữ liệu

Khi triển khai phiên bản mới, xác minh:

- Migration chạy đúng và có thể theo dõi.
- Schema mới tương thích với ứng dụng trong giai đoạn chuyển tiếp.
- Dữ liệu cũ được giữ nguyên ý nghĩa.
- Migration có thể xử lý khối lượng dữ liệu dự kiến.
- Rollback ứng dụng không làm schema ở trạng thái không tương thích.
- Các job chuyển đổi dữ liệu không chạy trùng hoặc bỏ sót.
- Có backup, checkpoint hoặc phương án phục hồi phù hợp.

Với triển khai rolling hoặc blue-green, có thể tồn tại đồng thời hai phiên bản ứng dụng. Thiết kế schema theo hướng tương thích ngược và tiến (expand-and-contract) giúp giảm rủi ro khi phiên bản cũ và mới cùng truy cập dữ liệu.

## 5. Chạy smoke test sau triển khai

### 5.1. Mục tiêu của smoke test

Smoke test là tập kiểm tra ngắn, có thời gian chạy thấp nhằm xác nhận hệ thống đã triển khai có thể thực hiện các chức năng nền tảng. Nó trả lời câu hỏi “bản triển khai có đủ khỏe để tiếp tục kiểm tra sâu hoặc nhận lưu lượng không?”.

Smoke test thường bao gồm:

- Trang hoặc API chính có thể truy cập.
- Xác thực hoặc tạo session hoạt động.
- Một thao tác đọc quan trọng.
- Một thao tác nghiệp vụ an toàn trong dữ liệu thử.
- Kết nối đến các phụ thuộc thiết yếu.
- Kiểm tra phiên bản đang chạy.
- Xác nhận log hoặc trace được tạo.

Smoke test không cần bao phủ mọi nhánh. Một tập nhỏ nhưng đại diện cho các điểm chặn quan trọng sẽ có giá trị hơn một bộ lớn chạy chậm mà không rõ mục tiêu.

### 5.2. Phân biệt health check và smoke test

| Kiểm tra | Điều xác nhận | Giới hạn |
|---|---|---|
| Liveness | Tiến trình còn hoạt động | Không chứng minh có thể phục vụ nghiệp vụ |
| Readiness | Instance sẵn sàng nhận lưu lượng theo tiêu chí cấu hình | Không chứng minh mọi hành trình đúng |
| Smoke test | Một số chức năng cốt lõi hoạt động sau triển khai | Không bao phủ toàn bộ nghiệp vụ hoặc tải |
| E2E suite | Hành trình xuyên thành phần trong kịch bản đã chọn | Có thể tốn thời gian và vẫn giới hạn theo dữ liệu/môi trường |

Các kiểm tra bổ sung cho nhau và không nên dùng thay thế lẫn nhau.

### 5.3. Thiết kế smoke test an toàn

Ưu tiên thao tác:

- Read-only khi có thể.
- Dùng tài khoản hoặc tenant thử nghiệm.
- Có dữ liệu nhận diện và dọn được.
- Không gửi thông báo đến người dùng thật.
- Không tạo giao dịch tài chính thật nếu chưa được phê duyệt.
- Có timeout và điều kiện kết thúc rõ.
- Có mã tương quan để điều tra.

Nếu cần kiểm tra thao tác ghi, thiết kế dữ liệu riêng cho smoke test và xác minh tác dụng phụ. Không dùng một giao dịch thử có thể gây ảnh hưởng đến báo cáo hoặc dữ liệu thật.

### 5.4. Ví dụ smoke test cho dịch vụ đơn hàng

1. Gọi endpoint thông tin phiên bản và xác nhận build ID đúng.
2. Kiểm tra readiness của dịch vụ.
3. Đọc danh mục sản phẩm thử.
4. Tạo một đơn hàng bằng tài khoản test nếu môi trường cho phép.
5. Xác nhận đơn được lưu với trạng thái dự kiến.
6. Kiểm tra log hoặc trace có correlation ID.
7. Dọn dữ liệu test hoặc đánh dấu để cleanup theo quy trình.

Nếu bước tạo đơn không được phép trong môi trường đó, thay bằng một hành động read-only hoặc kịch bản synthetic đã được phê duyệt.

## 6. Chạy kiểm thử tích hợp, API và hợp đồng

### 6.1. Xác minh ranh giới giữa các thành phần

Sau khi triển khai, kiểm tra các kết nối thực tế:

- Service-to-service authentication.
- API gateway và routing.
- Database, cache và message broker.
- Dịch vụ nội bộ và dịch vụ ngoài.
- Webhook và callback.
- Schema và phiên bản hợp đồng.
- Timeout, retry và xử lý lỗi.

Kết quả từ unit test không xác nhận DNS, TLS, certificate, network policy hoặc secret trong môi trường triển khai. Cần có kiểm tra ở đúng ranh giới.

### 6.2. Kiểm tra contract trên artifact triển khai

Có thể chạy contract tests hoặc provider verification đối với phiên bản thực sự đang chạy. Điều này giúp phát hiện sai lệch giữa hợp đồng đã kiểm tra trong pipeline và cấu hình serialization hoặc runtime của artifact.

Ghi lại:

- Provider và consumer version.
- Contract version.
- Endpoint hoặc service được kiểm tra.
- Các schema và trạng thái lỗi đã xác minh.
- Thành phần nào được mô phỏng.
- Kết quả và artifact digest.

### 6.3. Kiểm tra bất đồng bộ và sự kiện

Với hệ thống event-driven, kiểm tra:

- Event được phát đúng schema và định danh.
- Broker nhận và lưu event theo cấu hình.
- Consumer xử lý và ghi trạng thái đúng.
- Event lặp không tạo tác dụng phụ trùng.
- Event đến trễ hoặc sai thứ tự được xử lý theo hợp đồng.
- Retry và dead-letter queue hoạt động.
- Có thể truy vết từ request đến event và kết quả xử lý.

Một API có thể trả thành công ngay khi event được đưa vào queue, trong khi nghiệp vụ chưa hoàn tất. Kiểm thử cần phân biệt trạng thái accepted, queued, processed và completed theo hợp đồng.

## 7. Chạy kiểm thử hệ thống và E2E trên bản triển khai

### 7.1. Chọn hành trình đại diện

Ưu tiên các hành trình:

- Đăng nhập và quản lý phiên.
- Tìm kiếm hoặc đọc dữ liệu quan trọng.
- Tạo, cập nhật và hoàn tất giao dịch.
- Thanh toán, hủy hoặc hoàn tiền trong môi trường an toàn.
- Quy trình phê duyệt hoặc phân quyền.
- Tác vụ có xử lý bất đồng bộ.
- Hành trình có nhiều dịch vụ hoặc hệ thống ngoài.

Mỗi hành trình cần tiền điều kiện, dữ liệu, bước thực hiện, kết quả cuối và nguồn bằng chứng. Không nên chỉ xác nhận giao diện hiển thị thành công; cần kiểm tra trạng thái nghiệp vụ tại nguồn có thẩm quyền.

### 7.2. Phân biệt E2E dùng mock với E2E tích hợp thật

Một hành trình có thể chạy qua ứng dụng thật nhưng thay provider ngoài bằng mock. Điều đó vẫn hữu ích để xác minh logic nội bộ, song báo cáo cần nêu rõ ranh giới mô phỏng.

Với những tích hợp quan trọng, bổ sung contract test, sandbox test hoặc một kiểm tra được phê duyệt với endpoint thật. Không suy rộng kết quả mock thành bằng chứng tích hợp thật.

### 7.3. Kiểm tra hồi quy theo phạm vi thay đổi

Không nhất thiết chạy mọi E2E sau mọi commit. Chọn theo:

- Thành phần và dịch vụ bị thay đổi.
- Hành trình phụ thuộc.
- Lịch sử lỗi.
- Mức độ ảnh hưởng dữ liệu và quyền.
- Mức rủi ro của bản phát hành.
- Chi phí và thời gian chạy.

Một thay đổi thư viện dùng chung có thể yêu cầu mở rộng kiểm tra sang nhiều hành trình. Một thay đổi nội dung ít rủi ro có thể chỉ cần một tập kiểm tra nhỏ hơn.

## 8. Kiểm tra phi chức năng trên sản phẩm triển khai

### 8.1. Hiệu năng và khả năng mở rộng

Kiểm tra theo mục tiêu vận hành:

- Thời gian phản hồi theo percentile phù hợp.
- Throughput.
- Tỷ lệ lỗi và timeout.
- CPU, RAM, I/O, connection và queue depth.
- Hành vi autoscaling.
- Thời gian warm-up và cache.
- Hiệu năng với dữ liệu đại diện.
- Tải ổn định, tải đỉnh và stress nếu cần.

Kết quả chỉ có ý nghĩa khi ghi hạ tầng, dữ liệu, mô hình tải và cấu hình. Không dùng mock cho phụ thuộc có chi phí latency quan trọng nếu mục tiêu là đo hiệu năng tích hợp thật.

### 8.2. Bảo mật và cấu hình an toàn

Tùy phạm vi được phê duyệt, kiểm tra:

- Artifact và image có dependency dễ tổn thương không.
- Cấu hình mặc định có an toàn không.
- Endpoint, TLS và certificate đúng không.
- Quyền của service account có tối thiểu không.
- Secret có bị lộ trong image, log hoặc artifact không.
- Authentication và authorization hoạt động đúng.
- Header bảo mật và chính sách mạng phù hợp.
- Audit event được ghi nhận theo yêu cầu.

Không thực hiện kiểm thử xâm nhập hoặc thao tác phá hoại trên môi trường không được cấp phép. Kiểm tra bảo mật cần theo phạm vi và quy trình của tổ chức.

### 8.3. Khả năng phục hồi và chịu lỗi

Kiểm tra các tình huống như:

- Một instance bị dừng.
- Database hoặc broker tạm thời không sẵn sàng.
- Dịch vụ phụ thuộc timeout.
- Mất kết nối mạng và kết nối lại.
- Queue tăng tồn đọng.
- Một node hoặc vùng bị lỗi nếu kiến trúc hỗ trợ.
- Retry, circuit breaker và fallback.
- Khôi phục sau restart hoặc triển khai lại.

Cần quan sát cả thời gian phục hồi, dữ liệu cuối và tác dụng phụ. Hệ thống phục hồi nhưng tạo giao dịch trùng hoặc mất event vẫn là lỗi.

### 8.4. Khả năng truy cập và tương thích nền tảng

Với giao diện web/mobile, kiểm tra trên artifact đã triển khai:

- Hành trình bàn phím.
- Focus và tên truy cập.
- Trình đọc màn hình trên ma trận hỗ trợ.
- Phóng to, reflow và tương phản.
- Tương thích trình duyệt và thiết bị.
- Nội dung đa phương tiện và thông báo lỗi.

Một bản dựng có thể khác hành vi so với môi trường dev do minification, asset pipeline, CSP, routing hoặc cấu hình CDN. Vì vậy, cần kiểm tra đúng bản triển khai và URL người dùng thực sự truy cập.

## 9. Thiết lập quality gates và quyết định promotion

### 9.1. Quality gate là gì?

Quality gate là điều kiện quyết định pipeline có thể tiếp tục, promotion hoặc phát hành hay không. Gate cần dựa trên rủi ro và tiêu chí đã thống nhất, không chỉ dựa vào một con số tổng hợp.

Ví dụ gate:

- Artifact đúng digest và provenance hợp lệ.
- Không có lỗ hổng nghiêm trọng vượt ngưỡng chính sách.
- Deployment và readiness đạt.
- Smoke test bắt buộc đạt.
- Contract test quan trọng đạt.
- Hành trình nghiệp vụ cốt lõi đạt.
- Migration hoàn tất và dữ liệu nhất quán.
- Hiệu năng nằm trong ngưỡng đã xác định.
- Không có lỗi chặn chưa được xử lý hoặc chấp nhận đúng thẩm quyền.

### 9.2. Phân loại kết quả

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Pass | Đáp ứng tiêu chí trong phạm vi chạy | Có thể tiếp tục nếu các gate khác đạt |
| Fail | Có bằng chứng vi phạm tiêu chí | Dừng gate liên quan, điều tra và sửa |
| Blocked | Không thể chạy do môi trường, quyền hoặc phụ thuộc | Khôi phục điều kiện hoặc quyết định theo quy trình |
| Skipped | Không chạy theo thiết kế hoặc điều kiện | Ghi lý do và giới hạn bằng chứng |
| Flaky / inconclusive | Kết quả không ổn định hoặc không đủ căn cứ | Điều tra, không tự động coi là pass |
| Accepted risk | Có rủi ro đã được người có thẩm quyền chấp nhận | Ghi căn cứ, biện pháp và điều kiện xem xét |

Không nên đổi trạng thái blocked hoặc skipped thành pass chỉ để pipeline xanh. Một gate có thể được miễn trong trường hợp cụ thể, nhưng phải có người phê duyệt và hồ sơ.

### 9.3. Gate theo giai đoạn

Có thể thiết kế nhiều gate:

- **Artifact gate:** tính toàn vẹn, provenance, dependency và package contents.
- **Deployment gate:** rollout, readiness, cấu hình và kết nối.
- **Functional gate:** smoke, API, contract và E2E quan trọng.
- **Non-functional gate:** hiệu năng, bảo mật, resilience và accessibility theo rủi ro.
- **Release gate:** tổng hợp bằng chứng, lỗi còn mở và rủi ro được chấp nhận.

Các gate sớm ngăn artifact sai đi xa hơn; các gate sâu xác nhận hành vi trong môi trường gần thực tế.

### 9.4. Quyết định promotion

Trước khi promotion, xác nhận:

- Đúng artifact digest được chọn.
- Kết quả kiểm thử thuộc cùng artifact hoặc phiên bản đã xác định.
- Cấu hình mục tiêu đã được review.
- Migration và tương thích dữ liệu đã được đánh giá.
- Các gate bắt buộc đạt hoặc có ngoại lệ được phê duyệt.
- Rủi ro còn lại có chủ sở hữu và biện pháp theo dõi.
- Kế hoạch rollback hoặc phục hồi đã rõ.

Không promotion chỉ dựa vào việc pipeline hoàn tất nếu một số kiểm tra quan trọng bị bỏ qua hoặc bị chặn.

## 10. Triển khai theo chiến lược và xác minh sau phát hành

### 10.1. Rolling deployment

Khi cập nhật từng instance, có thể tồn tại đồng thời phiên bản cũ và mới. Cần kiểm tra:

- Hai phiên bản có tương thích với schema và message không?
- Load balancer chỉ gửi lưu lượng đến instance sẵn sàng không?
- Session và cache có dùng chung đúng cách không?
- Migration có hỗ trợ giai đoạn chuyển tiếp không?
- Lỗi ở một phần rollout có được phát hiện và dừng không?

### 10.2. Blue-green deployment

Blue-green dùng hai môi trường triển khai, chuyển lưu lượng từ môi trường cũ sang môi trường mới sau khi xác minh.

Kiểm tra:

- Môi trường xanh có đúng artifact và cấu hình không?
- Smoke và E2E có chạy trên đúng endpoint xanh không?
- Dữ liệu và migration có tương thích với cả hai môi trường không?
- Chuyển traffic có thể thực hiện và đảo ngược an toàn không?
- Sau khi chuyển, có xác minh routing và phiên bản đang phục vụ không?

### 10.3. Canary release

Canary đưa bản mới đến một phần lưu lượng hoặc nhóm người dùng trước khi mở rộng. Theo dõi:

- Tỷ lệ lỗi và timeout.
- Latency và throughput.
- Chỉ số nghiệp vụ quan trọng.
- Tỷ lệ giao dịch thành công.
- Crash, restart và tài nguyên.
- Khác biệt giữa nhóm canary và nhóm đối chứng nếu có.

Cần xác định ngưỡng dừng và hành động tự động hoặc thủ công trước khi triển khai. Nếu chỉ theo dõi metrics kỹ thuật mà bỏ qua chỉ số nghiệp vụ, một lỗi như tính sai giá vẫn có thể không được phát hiện.

### 10.4. Xác minh sau triển khai

Sau khi rollout:

- Xác nhận đúng version hoặc digest đang phục vụ.
- Chạy smoke test an toàn.
- Kiểm tra log, metrics, trace và alert.
- Quan sát lỗi và latency trong cửa sổ thời gian đã xác định.
- Kiểm tra trạng thái migration và job nền.
- Xác nhận các hành trình trọng yếu.
- So sánh với baseline hoặc ngưỡng vận hành.

Kết quả post-deployment cần liên kết với release ID và thời điểm triển khai.

### 10.5. Rollback và phục hồi

Nếu gate hoặc giám sát phát hiện vấn đề, xác định:

- Có thể rollback ứng dụng không?
- Schema và dữ liệu có tương thích với phiên bản cũ không?
- Có tác dụng phụ đã xảy ra cần đối soát không?
- Có cần dừng consumer, scheduler hoặc traffic không?
- Ai có quyền quyết định rollback?
- Sau rollback cần chạy kiểm tra nào?

Rollback mã không tự động hoàn tác dữ liệu hoặc giao dịch bên ngoài. Với migration phá vỡ tương thích hoặc giao dịch đã phát sinh, có thể cần forward fix, compensation hoặc quy trình phục hồi riêng.

## 11. Quản lý lỗi, flaky test và thời gian chạy

### 11.1. Phân loại nguyên nhân thất bại

Khi một kiểm tra sau triển khai thất bại, xác định nhóm nguyên nhân:

- Artifact sai hoặc thiếu nội dung.
- Lỗi ứng dụng.
- Cấu hình hoặc secret sai.
- Hạ tầng hoặc network không sẵn sàng.
- Dữ liệu hoặc trạng thái tiền điều kiện sai.
- Phụ thuộc bên ngoài lỗi.
- Test script hoặc assertion sai.
- Timeout do môi trường hoặc tải.
- Flaky test không ổn định.

Không vội sửa assertion hoặc retry pipeline trước khi hiểu nguyên nhân. Việc chạy lại có thể tạo thêm tác dụng phụ hoặc che giấu lỗi thật.

### 11.2. Xử lý flaky test

Với test không ổn định:

1. Ghi lần chạy, môi trường, artifact và dữ liệu.
2. So sánh kết quả pass/fail trước đó.
3. Xác định phụ thuộc thời gian, thứ tự, trạng thái chia sẻ hoặc concurrency.
4. Kiểm tra log và trace.
5. Tái hiện trong môi trường kiểm soát.
6. Sửa nguyên nhân hoặc cô lập test khỏi gate phù hợp trong thời gian xử lý.
7. Theo dõi số lần thất bại và điều kiện tái xuất hiện.

Retry có thể hữu ích để phân loại lỗi tạm thời, nhưng không nên dùng retry vô hạn hoặc coi một lần pass sau retry là bằng chứng đủ. Báo cáo cần giữ lại lịch sử thất bại ban đầu.

### 11.3. Quản lý thời gian pipeline

Kiểm tra rộng có thể kéo dài pipeline. Tối ưu bằng cách:

- Chạy test nhanh ở mỗi thay đổi.
- Chạy bộ sâu hơn theo component, risk hoặc release candidate.
- Song song hóa các suite độc lập.
- Dùng môi trường ephemeral khi phù hợp.
- Tái sử dụng artifact và dependency cache an toàn.
- Dùng test selection dựa trên phạm vi thay đổi.
- Lưu kết quả để tránh chạy lại không cần thiết khi điều kiện không đổi.

Không cắt bỏ kiểm tra rủi ro cao chỉ để đạt thời gian pipeline. Cần phân tầng và xác định gate nào bắt buộc ở từng mốc.

## 12. Bằng chứng, báo cáo và truy vết

### 12.1. Thông tin cần lưu cho mỗi lần chạy

- Release candidate, build ID và artifact digest.
- Commit và nguồn build.
- Môi trường, vùng và thời điểm.
- Phiên bản dịch vụ và cấu hình liên quan.
- Bộ kiểm thử, phiên bản test và dữ liệu.
- Kết quả theo từng gate.
- Log, report, trace, video hoặc artifact cần thiết.
- Lỗi, trạng thái blocked/skipped và ngoại lệ.
- Người phê duyệt và quyết định promotion.

Bằng chứng phải được bảo vệ theo chính sách. Không lưu secret, token hoặc dữ liệu cá nhân trong report không được kiểm soát.

### 12.2. Liên kết artifact với kết quả

Một chuỗi truy vết hữu ích:

~~~text
Source revision
    -> Build ID
        -> Artifact digest
            -> Deployment ID / environment
                -> Test run IDs
                    -> Results and evidence
                        -> Promotion / release decision
~~~

Nếu kết quả kiểm thử không gắn được với artifact cụ thể, nhóm khó chứng minh bản phát hành chính là bản đã được kiểm tra.

### 12.3. Báo cáo kết quả có giới hạn rõ

Một báo cáo nên nêu:

- Artifact nào đã được kiểm tra.
- Môi trường và cấu hình.
- Các nhóm kiểm thử đã chạy.
- Nhóm nào không chạy hoặc bị chặn.
- Kết quả và lỗi quan trọng.
- Khác biệt so với production.
- Rủi ro còn lại.
- Quyết định tiếp theo và người chịu trách nhiệm.

Ví dụ:

> Release candidate có digest đã ghi nhận được triển khai lên staging. Artifact integrity, migration check, readiness, smoke, contract và các hành trình E2E cốt lõi đều đạt. Bộ kiểm thử tải chạy ở mức tải mục tiêu của staging nhưng hạ tầng có ít node hơn production; do đó kết quả chưa chứng minh năng lực tải tối đa của cụm production. Tích hợp thanh toán dùng sandbox, nên settlement production chưa được xác minh. Các giới hạn này đã được ghi vào hồ sơ release và có kiểm tra vận hành sau triển khai theo quy trình được duyệt.

## 13. Ví dụ tổng hợp: pipeline phát hành dịch vụ đơn hàng

Giả sử sản phẩm gồm Web, Order API, Inventory, Payment, database và message broker.

### 13.1. Các bước kiểm tra

| Giai đoạn | Kiểm tra | Bằng chứng |
|---|---|---|
| Build | Compile, unit, static analysis | Build report và test report |
| Package | Image digest, SBOM, scan, nội dung package | Metadata, checksum và findings |
| Deploy integration | Rollout, readiness, config và kết nối | Deployment status, health và log |
| Smoke | Đọc catalog, tạo đơn test an toàn | Response, order ID và trạng thái |
| Integration | Order–Inventory–Payment và event | Trace, event ID và bản ghi |
| E2E | Đặt hàng, thanh toán sandbox, nhận xác nhận | Hành trình và kết quả cuối |
| Non-functional | Load, timeout và retry theo rủi ro | Metrics và fault test report |
| Promotion | Gate, digest và rủi ro còn lại | Release decision record |
| Post-deploy | Version, synthetic check và monitoring | Release ID, metrics và alert |

### 13.2. Một số điều kiện gate minh họa

- Artifact digest được xác minh và đúng nguồn build.
- Không có lỗ hổng nghiêm trọng chưa xử lý theo chính sách.
- Migration hoàn tất và dữ liệu kiểm tra nhất quán.
- Readiness và smoke test đạt.
- Không có lỗi contract hoặc E2E chặn hành trình cốt lõi.
- Các kiểm tra tải bắt buộc nằm trong ngưỡng đã thống nhất.
- Lỗi blocked hoặc skipped có lý do và người chịu trách nhiệm.
- Có kế hoạch rollback hoặc phục hồi phù hợp.

Ngưỡng cụ thể phải dựa trên yêu cầu vận hành và mức rủi ro của sản phẩm, không lấy ví dụ này làm chuẩn mặc định.

### 13.3. Quyết định sau kiểm tra

Nếu tất cả gate bắt buộc đạt, artifact có thể được xem xét promotion theo quy trình. Nếu smoke thất bại do cấu hình, dừng promotion và sửa cấu hình hoặc artifact theo quy trình. Nếu E2E phát hiện đơn bị tạo trùng, điều tra idempotency và dữ liệu trước khi tiếp tục. Nếu tải staging không đại diện production, cần bổ sung bằng chứng hoặc ghi rõ rủi ro và người có thẩm quyền chấp nhận.

## 14. Những sai lầm thường gặp

1. **Chỉ kiểm tra mã nguồn:** bỏ qua package, dependency và cấu hình cuối cùng.
2. **Build lại cho từng môi trường:** tạo nguy cơ các môi trường chạy artifact khác nhau.
3. **Dùng tag thay cho định danh bất biến:** khó xác định chính xác image hoặc package đã kiểm tra.
4. **Chỉ dựa vào health endpoint:** dịch vụ có thể sống nhưng chức năng nghiệp vụ lỗi.
5. **Smoke test quá rộng:** biến smoke thành E2E suite dài và khó dùng làm gate nhanh.
6. **Smoke test có tác dụng phụ không kiểm soát:** tạo giao dịch hoặc thông báo thật.
7. **Bỏ qua migration và tương thích:** triển khai ứng dụng thành công nhưng dữ liệu hoặc phiên bản cũ bị ảnh hưởng.
8. **Coi sandbox như provider production:** suy rộng kết quả vượt phạm vi.
9. **Không kiểm tra cấu hình thực tế:** bỏ sót secret, timeout, routing hoặc feature flag sai.
10. **Chỉ chạy kiểm thử chức năng:** bỏ qua hiệu năng, bảo mật, khả năng phục hồi và quan sát.
11. **Retry để che flaky test:** làm pipeline xanh nhưng không giải quyết nguyên nhân.
12. **Không ghi test bị bỏ qua:** báo cáo tạo ấn tượng rằng toàn bộ phạm vi đã được xác minh.
13. **Không liên kết kết quả với artifact:** không chứng minh được bản phát hành chính là bản đã kiểm tra.
14. **Rollback mà không xem xét dữ liệu:** mã cũ có thể không tương thích schema hoặc tác dụng phụ đã xảy ra.

## 15. Checklist chạy kiểm tra rộng trên sản phẩm đã đóng gói và triển khai

- [ ] Đã xác định mục tiêu kiểm tra và rủi ro của artifact hoặc release.
- [ ] Artifact có version, build ID và digest bất biến.
- [ ] Nguồn build, checksum/chữ ký, provenance và SBOM được kiểm tra theo chính sách.
- [ ] Dependency, package contents và secret được rà soát.
- [ ] Cùng artifact được promotion qua các môi trường.
- [ ] Cấu hình, secret reference, endpoint và feature flag được xác minh.
- [ ] Cài đặt, startup, liveness và readiness đạt theo tiêu chí.
- [ ] Migration và tương thích dữ liệu được kiểm tra.
- [ ] Smoke test ngắn, an toàn và có dữ liệu nhận diện.
- [ ] Contract và integration tests xác nhận các ranh giới quan trọng.
- [ ] E2E kiểm tra hành trình nghiệp vụ ưu tiên trên bản triển khai.
- [ ] Các kiểm tra phi chức năng được chọn theo rủi ro và mục tiêu vận hành.
- [ ] Thành phần mock, sandbox và các giới hạn môi trường được ghi rõ.
- [ ] Quality gates phân biệt pass, fail, blocked, skipped, flaky và accepted risk.
- [ ] Lỗi được điều tra theo artifact, cấu hình, dữ liệu và môi trường.
- [ ] Bằng chứng liên kết với commit, artifact digest, deployment và release.
- [ ] Promotion có người chịu trách nhiệm và rủi ro còn lại được ghi nhận.
- [ ] Post-deployment verification và giám sát được thực hiện.
- [ ] Kế hoạch rollback hoặc phục hồi xét cả mã, schema và tác dụng phụ.

Chạy kiểm tra rộng trên sản phẩm đã đóng gói và triển khai giúp xác nhận bản phát hành trong hình thức và điều kiện gần với cách nó sẽ được sử dụng. Khi artifact được truy vết xuyên suốt, các kiểm tra được phân tầng theo rủi ro và kết quả được gắn với bằng chứng cùng giới hạn rõ ràng, nhóm có cơ sở tốt hơn để promotion, phát hành và xử lý sự cố sau triển khai.
