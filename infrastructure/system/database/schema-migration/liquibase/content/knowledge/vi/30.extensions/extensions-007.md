# Đánh giá tính năng bổ sung theo phiên bản và giấy phép

## 1. Mục tiêu đánh giá

Trong phạm vi DATABASE_SCHEMA_MIGRATION_LIQUIBASE, Liquibase giúp quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; nhóm cần thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi cần một tính năng mà bộ công cụ hiện tại chưa đáp ứng, nhóm có thể cân nhắc extension, plugin, gói thương mại hoặc nâng lên một phiên bản có tính năng tương ứng.

Quyết định này có ít nhất bốn chiều độc lập:

1. **Năng lực:** tính năng có giải quyết đúng vấn đề kỹ thuật và vận hành không?
2. **Tương thích:** tính năng có hoạt động với Liquibase core, Java, Spring Boot, JDBC driver và DBMS đang dùng không?
3. **Giấy phép:** tổ chức có quyền sử dụng tính năng đó trong đúng môi trường, quy mô và cách phân phối không?
4. **Vòng đời:** có thể nâng cấp, kiểm thử, hỗ trợ, thay thế và vận hành lâu dài không?

Một extension có thể đáp ứng yêu cầu kỹ thuật nhưng không được phép dùng trong môi trường production theo license hiện tại. Ngược lại, một tính năng nằm trong gói đã mua vẫn có thể không tương thích với version Liquibase hoặc DBMS mục tiêu. Vì vậy phải đánh giá cả bốn chiều trước khi đưa dependency vào artifact hoặc pipeline.

Sau bài học, bạn có thể lập yêu cầu tính năng, phân biệt extension với tính năng core và gói thương mại, xác minh ma trận phiên bản, đọc điều kiện license, chạy proof of concept, định lượng chi phí/rủi ro và ghi nhận quyết định có thể kiểm tra lại.

## 2. Phân biệt các loại tính năng bổ sung

### 2.1. Tính năng đã có trong Liquibase core

Trước khi thêm dependency, kiểm tra khả năng của version Liquibase core đang dùng. Một nhu cầu có thể đã được đáp ứng bởi change type, precondition, context, label, parameter, `modifySql`, SQL formatted changelog hoặc command sẵn có.

Nếu tính năng đã có trong core nhưng dự án đang dùng version cũ, nâng cấp core có thể là lựa chọn đơn giản hơn việc thêm extension. Tuy nhiên, nâng core cũng cần kiểm tra checksum, SQL generator, API, Java runtime và các DBMS hỗ trợ.

### 2.2. Extension hoặc plugin

Extension thường bổ sung một hoặc nhiều thành phần:

- Change type mới để biểu diễn một thao tác database.
- Parser hoặc định dạng changelog bổ sung.
- SQL generator hoặc database implementation.
- Precondition, custom task hoặc command.
- Tích hợp với dịch vụ lưu trữ, nền tảng triển khai hay công cụ khác.

Extension có thể do Liquibase, nhà cung cấp khác hoặc cộng đồng phát triển. Nguồn phát hành và tên gọi không tự chứng minh mức hỗ trợ. Cần xác minh chủ sở hữu, repository, tài liệu, release cadence, cách báo lỗi và phạm vi license.

### 2.3. Gói thương mại hoặc edition có tính năng riêng

Một số năng lực có thể được phân phối trong sản phẩm/edition thương mại, gói hỗ trợ hoặc dịch vụ có license riêng. Tên edition, danh sách tính năng, cơ chế cấp license và điều khoản có thể thay đổi theo thời gian. Không suy luận quyền sử dụng từ tên artifact, tài liệu marketing, một lần chạy thử thành công hoặc việc tải được binary.

Hãy xác minh với tài liệu sản phẩm và hợp đồng hiện hành:

- Tính năng thuộc edition/gói nào.
- Có cần license key, tài khoản, subscription hoặc entitlement không.
- License áp dụng cho developer, build agent, server, database, instance hay môi trường nào.
- Có giới hạn số lượng database, deployment target, user hoặc node không.
- Có quyền dùng trong CI, staging, production, disaster recovery và môi trường air-gapped không.

### 2.4. Driver và tích hợp không phải extension Liquibase

JDBC driver, connection pool, Spring Boot starter, plugin Maven/Gradle và công cụ CI có thể bổ sung khả năng cho pipeline nhưng không nhất thiết là Liquibase extension. Chúng có vòng đời, license và ma trận tương thích riêng. Đừng gộp tất cả vào một mục “plugin” rồi bỏ qua dependency graph hoặc license của từng thành phần.

| Loại | Ví dụ vai trò | Cần xác minh |
|---|---|---|
| Liquibase core | Changelog, changeset, checksum, SQL generation | Version, Java, DBMS và thay đổi hành vi |
| Extension | Change type hoặc service bổ sung | Core API, DBMS, nguồn phát hành, license |
| Edition/gói thương mại | Năng lực được phân phối theo entitlement | Feature matrix, hợp đồng, phạm vi triển khai |
| JDBC driver | Kết nối và metadata database | Java, DBMS, TLS, authentication, license |
| Build/CI integration | Chạy validate/update trong pipeline | Plugin version, runtime, secret và license |

## 3. Bắt đầu từ yêu cầu có thể kiểm chứng

Không nên chọn extension chỉ vì tên tính năng nghe phù hợp. Hãy mô tả vấn đề bằng một tình huống cụ thể:

- **Tác nhân:** ai hoặc tiến trình nào cần tính năng?
- **Điểm kích hoạt:** tính năng được dùng lúc viết changelog, build, review hay deploy?
- **Đầu vào:** changelog, metadata, database connection hay cấu hình nào được cung cấp?
- **Đầu ra:** SQL, báo cáo, artifact, trạng thái database hoặc quyết định nào được tạo?
- **Hành vi lỗi:** điều gì xảy ra nếu thiếu quyền, mất mạng, license hết hạn hoặc DBMS không hỗ trợ?
- **Tiêu chí đạt:** bằng chứng nào chứng minh vấn đề đã được giải quyết?

Ví dụ, yêu cầu “cần kiểm tra migration trước production” còn quá rộng. Có thể viết lại thành: “Pipeline phải tạo được SQL preview cho từng DBMS được hỗ trợ, phát hiện changeset có thao tác phá hủy dữ liệu, lưu kết quả review theo release và dừng khi target database không nằm trong allowlist”. Mô tả cụ thể giúp so sánh core, extension và gói thương mại trên cùng tiêu chí.

### 3.1. Phân biệt yêu cầu bắt buộc và mong muốn

| Nhóm | Câu hỏi | Cách đánh giá |
|---|---|---|
| Bắt buộc | Thiếu tính năng thì release hoặc vận hành có bị chặn không? | Điều kiện pass/fail |
| Quan trọng | Có giảm lỗi, thời gian hoặc rủi ro đáng kể không? | Chấm điểm theo bằng chứng |
| Tùy chọn | Có tiện lợi nhưng không thay đổi kết quả chính không? | Chỉ cân nhắc khi chi phí thấp |
| Ngoài phạm vi | Không liên quan use case hiện tại? | Không đưa vào PoC |

Không biến một tính năng tiện lợi thành yêu cầu bắt buộc nếu chưa có dữ liệu chứng minh. Việc thu hẹp phạm vi giúp PoC ngắn và dễ kết luận.

## 4. Đánh giá tính năng theo version

### 4.1. Xác định đúng artifact và version

Với mỗi ứng viên, ghi chính xác:

- Tên artifact/package và group/module.
- Version đang đánh giá.
- Nhà phát hành hoặc repository chính thức.
- Version Liquibase core được hỗ trợ.
- Phiên bản Java tối thiểu/tối đa đã kiểm chứng.
- DBMS, edition và server version hỗ trợ.
- Spring Boot version hoặc cách tích hợp được hỗ trợ.
- Ngày phát hành, trạng thái maintenance và ngày kết thúc hỗ trợ nếu có.

Không ghi chung “extension mới nhất”. Một version cụ thể có thể là bản thử nghiệm, bản cộng đồng, bản thương mại hoặc đã hết hỗ trợ. Khóa version và checksum/artifact provenance trong quy trình build để các môi trường dùng cùng binary.

### 4.2. Ma trận tương thích phải bao gồm toàn bộ chuỗi

| Thành phần | Điều cần xác minh |
|---|---|
| Liquibase core | API, parser, SQL generator, checksum và command |
| Extension | Version core được hỗ trợ, change type và service |
| Java | Bytecode, module system, TLS và class loading |
| Spring Boot | Auto-configuration, dependency management và bean lifecycle |
| JDBC driver | Metadata, authentication, transaction và DBMS version |
| DBMS | Engine, edition, version, compatibility mode và tính năng SQL |
| Build/CI | Maven/Gradle plugin, CLI, runtime image và classpath |
| Hệ điều hành/container | Certificate, timezone data, filesystem và kiến trúc CPU |

Một extension chạy được với Liquibase CLI chưa chắc chạy được khi đóng gói trong Spring Boot. Tương tự, change type có thể được parse nhưng SQL generator chỉ hỗ trợ một số DBMS. Cần đánh dấu riêng từng ô trong ma trận là “được nhà cung cấp hỗ trợ”, “đã kiểm thử nội bộ”, “không hỗ trợ” hoặc “chưa xác minh”.

### 4.3. Kiểm tra thay đổi giữa các phiên bản

Đọc release notes từ version hiện tại tới version mục tiêu, không chỉ đọc ghi chú của bản cuối. Tìm:

- Tính năng mới, giới hạn mới và thay đổi mặc định.
- API hoặc thuộc tính bị deprecated/removed.
- Thay đổi cú pháp changelog hoặc cấu hình.
- Thay đổi checksum, snapshot, SQL generation và transaction.
- Thay đổi license, edition, entitlement hoặc cách kích hoạt.
- Lỗi đã biết và security advisory.
- Thay đổi về Java/DBMS tối thiểu hoặc version extension phụ thuộc.

Ghi lại tác động lên changelog đang có. Một tính năng mới có thể chỉ hoạt động với changeset mới tạo; không mặc định nó thay đổi hoặc nâng cấp tự động các changeset cũ.

### 4.4. Phân biệt tương thích được công bố và đã thử

Hai trạng thái này có ý nghĩa khác nhau:

- **Supported:** tài liệu chính thức xác nhận tổ hợp nằm trong phạm vi hỗ trợ.
- **Verified internally:** nhóm đã chạy kịch bản kiểm thử trên tổ hợp đó và lưu bằng chứng.

Một lần chạy thành công không thay thế cam kết hỗ trợ. Ngược lại, có tên trong ma trận hỗ trợ cũng không chứng minh cấu hình riêng của tổ chức không có lỗi. Production nên có cả hai loại bằng chứng, hoặc ghi nhận rõ rủi ro khi một loại chưa có.

## 5. Đánh giá giấy phép và quyền sử dụng

### 5.1. Xác định license của từng thành phần

Một ứng dụng có thể chứa nhiều loại license:

- License nguồn mở có điều kiện sử dụng, phân phối hoặc cung cấp mã nguồn khác nhau.
- License thương mại yêu cầu subscription, entitlement hoặc license key.
- License riêng của extension do nhà cung cấp thứ ba phát hành.
- Điều khoản của JDBC driver, build plugin, thư viện bắc cầu hoặc công cụ đi kèm.

Không kết luận một dependency miễn phí chỉ vì source code công khai hoặc có thể tải từ Maven repository. Không kết luận một dependency được phép dùng production chỉ vì developer đã chạy được trên máy cá nhân.

Với từng artifact, lưu:

1. Tên license và version của văn bản license.
2. URL hoặc vị trí tài liệu chính thức.
3. Nhà phát hành và artifact/version tương ứng.
4. Quyền sử dụng, sửa đổi, phân phối và triển khai.
5. Nghĩa vụ thông báo, attribution, cung cấp source hoặc giữ notice nếu có.
6. Giới hạn user, server, database, environment, node hoặc deployment.
7. Thời hạn subscription, support và quyền dùng sau khi hết hạn.
8. Quy trình audit, gia hạn, thu hồi và xử lý license key.

### 5.2. Kiểm tra phạm vi triển khai

Đọc điều khoản để trả lời các câu hỏi theo mô hình sử dụng thật:

- Developer có được dùng trên laptop và workstation không?
- Build agent, CI runner và ephemeral container có được tính là một installation/instance riêng không?
- Staging, UAT, performance test và production có cùng entitlement không?
- Disaster recovery, standby, replica và môi trường dự phòng có được bao gồm không?
- Có giới hạn số database, schema, user, node hoặc deployment target không?
- Có được chạy trong cloud, private cloud, on-premises hoặc môi trường cách ly mạng không?
- Có được nhúng binary vào image hoặc phân phối cùng sản phẩm cho khách hàng không?

Không tự suy ra cách tính license từ số pod hoặc số database. Mỗi nhà cung cấp có thể định nghĩa metric khác nhau; cần đối chiếu hợp đồng, order form và tài liệu license áp dụng cho đúng sản phẩm.

### 5.3. License key và entitlement

Nếu tính năng yêu cầu license key hoặc token:

- Xác minh key áp dụng cho đúng sản phẩm, edition và version.
- Xác định thời điểm cần kiểm tra license: lúc build, lúc chạy command hay lúc khởi động ứng dụng.
- Kiểm tra hành vi khi key hết hạn, không hợp lệ hoặc không thể liên hệ license server.
- Xác định có cần outbound network, proxy, allowlist hoặc cơ chế offline activation không.
- Lưu key trong secret manager, không commit vào changelog, properties, Docker image hay log.
- Giới hạn quyền đọc secret và có quy trình xoay vòng/thu hồi.

Một PoC chạy trên máy có license developer không chứng minh CI/CD hoặc production đã có entitlement. Hãy thử trong đúng loại môi trường và danh tính sẽ sử dụng khi triển khai.

### 5.4. Kiểm tra license của dependency bắc cầu

Extension có thể kéo nhiều thư viện khác. License của extension không tự bao phủ license của mọi dependency bắc cầu. Dùng công cụ inventory/SBOM và quy trình review license của tổ chức để:

- Liệt kê dependency trực tiếp và gián tiếp.
- Phát hiện license chưa xác định hoặc không được chính sách cho phép.
- Lưu notice/attribution cần thiết.
- Kiểm tra nghĩa vụ khi phân phối artifact cho khách hàng.
- Theo dõi thay đổi license giữa các version.

Nếu có điều khoản chưa rõ về phân phối hoặc sử dụng thương mại, chuyển cho bộ phận pháp chế/procurement xem xét trước khi phát hành. Đánh giá kỹ thuật không thay thế kết luận pháp lý.

## 6. Quy trình đánh giá một tính năng bổ sung

### Bước 1: Viết use case và tiêu chí chấp nhận

Ghi rõ vấn đề, người dùng, luồng chạy, đầu vào/đầu ra, DBMS mục tiêu và điều kiện lỗi. Mỗi tiêu chí cần có cách kiểm chứng. Ví dụ: “change type tạo partition phải sinh DDL đúng cho PostgreSQL phiên bản đang hỗ trợ, có rollback hoặc forward-fix được mô tả, và không làm thay đổi checksum của changeset đã triển khai”.

### Bước 2: Kiểm tra core và phiên bản hiện tại

Đọc tài liệu version hiện tại để xem có cách làm sẵn hay không. Nếu tính năng nằm trong version core mới hơn, so sánh chi phí nâng core với chi phí thêm extension. Bao gồm rủi ro checksum, SQL generator, Java, Spring Boot và DBMS.

### Bước 3: Lập danh sách ứng viên

Với mỗi ứng viên, ghi nguồn phát hành, artifact, version, tính năng, compatibility matrix, license, support channel, release cadence và tình trạng bảo trì. Không đưa binary không rõ nguồn gốc vào PoC production-like.

### Bước 4: Xác minh license trước khi thử

Đọc điều khoản sử dụng cho developer, CI, staging, production, DR và phân phối. Nếu cần trial, xác định giới hạn trial và không dùng trial để đại diện cho quyền production lâu dài.

### Bước 5: Tạo proof of concept nhỏ

PoC nên chỉ chứa một changelog hoặc change type đại diện, một database tạm thời và một pipeline tối giản. Đo:

- Khả năng parse/validate.
- SQL được sinh theo DBMS.
- Hành vi update và trạng thái lịch sử.
- Rollback hoặc phương án forward-fix.
- Log, lỗi và thời gian thực thi.
- Hành vi khi thiếu license hoặc cấu hình sai.

PoC phải chạy trên đúng version core, Java, driver và runtime image dự kiến. Kết quả từ IDE hoặc laptop chỉ là một phần bằng chứng.

### Bước 6: Kiểm thử tương thích và vận hành

Thử database trống và database có lịch sử; thử mọi DBMS trong phạm vi hỗ trợ; kiểm tra concurrency/lock, quyền, timeout, secret, mạng và triển khai CI/CD. Nếu extension chỉ hỗ trợ một engine, đảm bảo các engine còn lại có phương án rõ ràng.

### Bước 7: Đánh giá chi phí và rủi ro

Tính tổng chi phí sở hữu: license/subscription, support, thời gian nâng cấp, kiểm thử, vận hành, đào tạo, bảo mật, dependency review và chi phí thay thế nếu nhà cung cấp ngừng duy trì.

### Bước 8: Ghi quyết định

Lưu kết quả dưới dạng Architecture Decision Record (ADR) hoặc hồ sơ lựa chọn nội bộ. Ghi rõ lựa chọn, lý do, version đã thử, license đã xác minh, giới hạn, người chịu trách nhiệm và điều kiện đánh giá lại.

## 7. Ma trận chấm điểm ứng viên

Trước tiên áp dụng các điều kiện bắt buộc: license hợp lệ; version tương thích; không có lỗ hổng chưa được chấp nhận; tính năng đáp ứng use case tối thiểu; có thể vận hành trong môi trường mục tiêu. Ứng viên trượt một điều kiện bắt buộc không nên được bù điểm bằng giao diện tốt hoặc nhiều tính năng phụ.

Sau đó chấm điểm các tiêu chí còn lại theo thang 1–5:

| Tiêu chí | Trọng số minh họa | Bằng chứng |
|---|---:|---|
| Độ phù hợp chức năng | 25% | PoC đạt tiêu chí nghiệp vụ |
| Tương thích phiên bản/DBMS | 20% | Compatibility matrix và test report |
| Chất lượng bảo trì/hỗ trợ | 15% | Release cadence, issue handling, support |
| Vận hành và tích hợp CI/CD | 15% | Pipeline thử, logging, secret handling |
| License và khả năng phân phối | Điều kiện bắt buộc | Văn bản license/entitlement được xác minh |
| Bảo mật và provenance | Điều kiện bắt buộc | SBOM, nguồn phát hành, advisory |
| Tổng chi phí sở hữu | 10% | License, vận hành, nâng cấp, đào tạo |
| Khả năng thay thế | 15% | Export format, SQL thuần, phương án thoát |

Trọng số chỉ là ví dụ; nhóm cần điều chỉnh theo mức độ quan trọng của từng use case. Không cộng điểm số khi license hoặc security chưa qua điều kiện bắt buộc. Ghi lý do cho từng điểm, tránh tạo một con số tổng thiếu căn cứ.

### 7.1. Ví dụ so sánh giả định

Giả sử nhóm cần một báo cáo SQL preview có phân loại migration nguy hiểm:

| Phương án | Ưu điểm | Giới hạn cần kiểm tra |
|---|---|---|
| Dùng core và script CI hiện có | Ít dependency, nhóm tự kiểm soát | Phải tự duy trì logic phân tích và báo cáo |
| Extension cộng đồng | Có thể triển khai nhanh, source dễ xem | Support, compatibility, license và bảo trì phụ thuộc dự án |
| Gói thương mại | Có thể có support/SLA và workflow tích hợp | Entitlement, chi phí, phạm vi triển khai và phụ thuộc nhà cung cấp |
| Tự viết extension nội bộ | Kiểm soát hành vi và tích hợp riêng | Chi phí phát triển, test, tương thích API và trách nhiệm bảo trì |

Không có lựa chọn thắng mặc định. Nếu script hiện tại đáp ứng đầy đủ tiêu chí, thêm extension có thể làm tăng bề mặt phụ thuộc mà không đem lại giá trị tương xứng. Nếu yêu cầu audit/support là bắt buộc và gói thương mại đáp ứng với license hợp lệ, chi phí có thể được biện minh.

## 8. Kiểm thử tính năng theo version và DBMS

### 8.1. Ma trận test

| Kịch bản | Liquibase core | DBMS | Kết quả cần lưu |
|---|---|---|---|
| Parse/validate changelog | Version mục tiêu | Không cần kết nối hoặc theo yêu cầu extension | Parser nhận đúng cấu hình |
| Generate SQL | Version mục tiêu | Mỗi engine hỗ trợ | SQL preview và diff |
| Fresh install | Version mục tiêu | Database trống | Object, dữ liệu và history |
| Upgrade path | Version mục tiêu | Database có lịch sử | Changeset pending và checksum |
| Rollback/forward-fix | Version mục tiêu | Database thử nghiệm | Trạng thái sau phục hồi |
| Quyền hạn | Version mục tiêu | Principal migration/runtime | Quyền cần có và quyền bị từ chối |
| License | Version/edition mục tiêu | CI/staging/production-like | Entitlement hợp lệ |
| Packaging | Artifact thực tế | Runtime image thực tế | Extension/resource được nạp |

Nếu sản phẩm hỗ trợ PostgreSQL, MySQL, SQL Server và Oracle, mỗi engine phải có test riêng. Không dùng H2 làm bằng chứng thay thế cho SQL generator, metadata hoặc DDL của DBMS production.

### 8.2. Kiểm thử từ hai trạng thái database

**Database trống** kiểm tra đường triển khai mới từ đầu. **Database đã có lịch sử** kiểm tra việc extension/version mới xử lý DATABASECHANGELOG, checksum, precondition và changeset pending ra sao. Cả hai đều cần thiết.

Database có lịch sử nên được tạo từ bản sao đã làm sạch dữ liệu nhạy cảm hoặc dataset tổng hợp đại diện. Giữ nguyên cấu trúc metadata và các trạng thái quan trọng để tái hiện vấn đề.

### 8.3. Kiểm tra hành vi lỗi

Thử các tình huống:

- Extension không có trên classpath.
- Version core không được extension hỗ trợ.
- License key thiếu, hết hạn hoặc không hợp lệ.
- CI không thể truy cập license server trong môi trường cách ly.
- DBMS không hỗ trợ change type hoặc syntax.
- User migration thiếu quyền DDL/metadata.
- Hai runner cùng yêu cầu lock.
- Connection timeout sau khi DDL có thể đã thực thi.

Ghi rõ lỗi có thể nhận biết, thông điệp log, exit code, trạng thái database và hướng phục hồi. Tính năng tốt phải thất bại theo cách có thể chẩn đoán và không để trạng thái nửa vời bị che giấu.

## 9. Kiểm soát dependency và nguồn cung cấp

### 9.1. Pin artifact và xác minh nguồn

Pin version extension và dependency trực tiếp; không dùng tag trôi nổi hoặc tải binary từ URL không được kiểm soát. Ưu tiên repository chính thức hoặc registry nội bộ đã kiểm tra. Lưu checksum/signature hoặc provenance theo chính sách supply chain của tổ chức.

Kiểm tra dependency graph để phát hiện:

- Extension kéo thêm Liquibase core khác version.
- Hai extension yêu cầu API không tương thích.
- JDBC driver bị thay thế ngoài ý muốn.
- Thư viện logging, parser hoặc YAML có xung đột.
- Dependency có license hoặc advisory chưa được xử lý.

### 9.2. SBOM và kiểm tra bảo mật

Tạo Software Bill of Materials (SBOM) cho artifact chứa extension. Lưu tên, version, nguồn, license và dependency bắc cầu. Quét lỗ hổng theo quy trình của tổ chức; đánh giá cả extension và thư viện đi kèm.

Một extension nhỏ vẫn chạy với quyền database cao của migration job. Vì vậy, review source/provenance, giới hạn quyền, network egress và secret access có ý nghĩa đặc biệt. Không cấp quyền production rộng cho một plugin chưa được đánh giá.

### 9.3. Phân biệt extension lúc build và lúc runtime

Một số plugin chỉ cần trong build/CLI; một số phải có trên classpath khi ứng dụng chạy Liquibase. Đưa dependency vào sai scope có thể làm build pass nhưng runtime không tìm thấy class, hoặc đưa thư viện không cần thiết vào production image.

Ghi rõ extension được nạp ở bước nào: authoring, validate, SQL generation, migration job hay Spring Boot startup. Tách dependency scope phù hợp và test trên artifact cuối cùng.

## 10. Triển khai license an toàn

Nếu license key/token được yêu cầu, chỉ cấp cho process cần sử dụng tính năng:

- Dùng secret manager hoặc cơ chế secret của CI/CD.
- Không đặt key trong changelog, source code, image layer hoặc file properties commit vào Git.
- Tránh truyền secret qua command line nếu có thể bị lưu trong process list hoặc shell history.
- Không in giá trị secret trong log khi debug.
- Hạn chế quyền đọc secret theo environment và service account.
- Có cách thu hồi/rotate key và xử lý khi nhân sự hoặc runner bị thay đổi.
- Xác định yêu cầu kết nối tới license server, proxy, DNS và thời gian hệ thống.

Với môi trường air-gapped, xác minh quy trình offline activation/renewal bằng tài liệu chính thức trước khi chọn giải pháp. Đừng đợi đến production mới phát hiện license cần kết nối outbound.

License hết hạn hoặc server xác thực không sẵn sàng có thể khiến tính năng bị vô hiệu hóa, command thất bại hoặc hệ thống chuyển sang chế độ giới hạn; hành vi tùy sản phẩm. Hãy thử đúng kịch bản và có runbook. Không giả định license failure chỉ ảnh hưởng bước build nếu tính năng được kiểm tra lúc runtime.

## 11. Tích hợp vào Spring Boot và CI/CD

### 11.1. Tách cấu hình theo môi trường

Nếu extension được dùng trong migration job riêng, hãy bảo đảm job có đúng extension classpath và license entitlement. Ứng dụng runtime không nhất thiết phải đóng gói extension nếu không chạy Liquibase khi startup. Nếu Spring Boot tự chạy Liquibase, extension phải có mặt trong runtime classpath và license/configuration phải được cấp cho tiến trình đó.

Đối chiếu:

- Spring Boot version và Liquibase core thực tế được nạp.
- Extension version và dependency graph.
- JDBC driver được dùng bởi migration datasource.
- Changelog, context, label, parameters và schema.
- License key/entitlement của CI, staging và production.

### 11.2. Pipeline tham khảo

~~~text
Resolve pinned dependencies
        |
        v
Generate SBOM and license report
        |
        v
Validate changelog with target extension
        |
        v
Generate SQL for each supported DBMS
        |
        v
Run PoC/integration tests on fresh and upgraded databases
        |
        v
Review license, security and compatibility evidence
        |
        v
Approve artifact and target environment
        |
        v
Run migration with scoped credentials/entitlement
        |
        v
Verify DATABASECHANGELOG, schema and application
~~~

Pipeline nên fail sớm nếu thiếu artifact, sai version, license không hợp lệ hoặc DBMS không được hỗ trợ. Kết quả SQL preview, test report, SBOM và license decision phải gắn với cùng commit/artifact được phát hành.

### 11.3. Không để khác biệt giữa CLI và ứng dụng

Nếu CI dùng Liquibase CLI còn Spring Boot dùng library, phải đồng bộ core/extension version hoặc ghi nhận lý do khác biệt. Cùng một changelog có thể được xử lý khác nếu hai classpath khác nhau. Chạy test với cả CLI và runtime path nếu production có thể dùng cả hai.

## 12. Quản lý vòng đời và rủi ro phụ thuộc

### 12.1. Release cadence và hỗ trợ

Đánh giá tần suất phát hành, thời gian phản hồi issue, mức độ hoạt động của repository, số maintainer, chính sách security fix và thời hạn support. Extension cộng đồng có thể phù hợp nhưng nhóm phải chấp nhận trách nhiệm bảo trì nếu dự án ngừng hoạt động.

### 12.2. Lock-in và khả năng thay thế

Một extension có thể tạo changelog dùng change type riêng hoặc định dạng độc quyền. Trước khi chọn, hỏi:

- Changelog có thể đọc bằng Liquibase core khi bỏ extension không?
- Có thể chuyển sang SQL thuần hoặc change type chuẩn không?
- SQL đã sinh có thể lưu lại/review độc lập không?
- License hoặc dịch vụ có thể chấm dứt mà không làm mất khả năng đọc lịch sử không?
- Có thể duy trì fork nội bộ nếu nhà cung cấp ngừng phát hành không?

Không phải lock-in nào cũng xấu; một tính năng có giá trị cao có thể đáng phụ thuộc. Điều cần thiết là nhận diện chi phí thoát và chuẩn bị phương án nếu phụ thuộc đó không còn khả dụng.

### 12.3. Nâng version và bỏ extension

Khi nâng extension:

1. Đọc release notes và compatibility matrix.
2. Kiểm tra dependency graph, license và advisory.
3. Chạy validate và SQL preview.
4. Thử fresh install và upgrade từ database có lịch sử.
5. Kiểm tra checksum, metadata, rollback và behavior lỗi.
6. Phát hành theo môi trường, quan sát và có điểm dừng.

Khi bỏ extension, không xóa dependency trước khi xác định changelog cũ còn cần parser/change type của nó để validate hoặc rollback hay không. Có thể phải giữ extension trong pipeline lịch sử, chuyển các change type sang SQL/core change type bằng changeset mới, hoặc duy trì một công cụ đọc lịch sử riêng. Không sửa changeset đã triển khai chỉ để loại bỏ dependency.

## 13. Ví dụ quyết định: có nên mua hoặc thêm extension?

Một nhóm cần một change type chuyên biệt để tạo object mà Liquibase core hiện tại chưa biểu diễn trực tiếp. Có ba phương án:

**Phương án A — SQL native trong changeset:** phù hợp nếu cú pháp ổn định, phạm vi DBMS nhỏ và nhóm có thể kiểm thử SQL/rollback. Chi phí license thấp nhưng nhóm tự chịu trách nhiệm dialect và bảo trì.

**Phương án B — Extension cộng đồng:** phù hợp nếu dự án có maintainer hoạt động, release hỗ trợ core version đang dùng, DBMS mục tiêu rõ và license cho phép triển khai. Cần dự phòng việc fork hoặc tự duy trì.

**Phương án C — Extension/gói thương mại:** phù hợp nếu tính năng, support hoặc SLA tạo giá trị đủ lớn và entitlement bao phủ developer, CI, staging, production cùng DR. Cần tính subscription, gia hạn, license server, giới hạn triển khai và chi phí thoát.

Quyết định cuối không dựa vào số lượng tính năng. Nhóm chọn phương án đáp ứng yêu cầu bắt buộc với bằng chứng tương thích và quyền sử dụng rõ ràng, đồng thời có chi phí vòng đời chấp nhận được.

## 14. Mẫu hồ sơ đánh giá

Có thể dùng cấu trúc sau cho từng ứng viên:

| Trường | Nội dung cần ghi |
|---|---|
| Use case | Vấn đề và người dùng |
| Tính năng | Hành vi cụ thể cần đạt |
| Ứng viên | Core version, extension/artifact hoặc edition |
| Version | Version chính xác và ngày đánh giá |
| Compatibility | Java, Liquibase core, Spring Boot, driver, DBMS |
| License | Tên license, entitlement, môi trường và giới hạn |
| Security | Provenance, SBOM, advisory, secret/network |
| PoC | Changelog, database và kịch bản đã chạy |
| Kết quả | Pass/fail theo từng tiêu chí |
| Vận hành | Logging, support, upgrade, rollback, air-gap |
| Chi phí | License, engineering, maintenance, support |
| Exit plan | Cách thay thế hoặc ngừng sử dụng |
| Quyết định | Adopt / Reject / Defer và người phê duyệt |
| Review lại | Mốc thời gian hoặc sự kiện kích hoạt đánh giá lại |

Gắn tài liệu license, release notes, test report, SQL preview và SBOM với hồ sơ này. Nếu một thông tin chưa xác minh, ghi rõ owner và điều kiện cần hoàn tất trước production.

## 15. Lỗi thường gặp khi đánh giá

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chọn extension theo tên tính năng | Có thể không đáp ứng use case thực tế | Viết tiêu chí chấp nhận trước PoC |
| Chỉ kiểm tra version Liquibase | Bỏ sót Java, Spring Boot, JDBC và DBMS | Dùng ma trận toàn chuỗi |
| Nghĩ tải được artifact là có quyền dùng | Vi phạm điều kiện license hoặc thiếu entitlement | Đọc license và hợp đồng hiện hành |
| PoC chỉ chạy trên laptop developer | CI/production có thể thiếu key, network hoặc classpath | Test đúng runtime image và môi trường |
| Chỉ test database trống | Không phát hiện lỗi checksum/upgrade path | Test thêm database có lịch sử |
| Chỉ nhìn feature matrix marketing | Bỏ qua giới hạn DBMS/version và điều kiện sử dụng | Đối chiếu tài liệu kỹ thuật và license |
| Không kiểm tra dependency bắc cầu | Bỏ sót license/CVE/xung đột | Dependency tree, SBOM và security scan |
| License key nằm trong image/log | Khó thu hồi và có thể bị lộ | Secret manager, quyền đọc tối thiểu |
| Không có phương án bỏ extension | Changelog cũ không còn đọc/rollback được | Lập exit plan trước khi adopt |
| Dùng trial làm bằng chứng production | Trial có thể giới hạn tính năng hoặc môi trường | Xác nhận entitlement production riêng |

## 16. Checklist trước khi chấp thuận tính năng bổ sung

- [ ] Use case và tiêu chí chấp nhận được mô tả cụ thể.
- [ ] Đã xác nhận Liquibase core hiện tại hoặc version mục tiêu chưa đáp ứng đủ.
- [ ] Đã ghi chính xác artifact, nhà phát hành và version.
- [ ] Đã kiểm tra compatibility matrix cho Java, Liquibase core, Spring Boot, JDBC và từng DBMS.
- [ ] Đã đọc release notes, breaking changes, deprecation và security advisory.
- [ ] Đã phân biệt tính năng core, extension, plugin tích hợp và edition thương mại.
- [ ] Đã xác minh license của dependency trực tiếp và bắc cầu.
- [ ] Entitlement bao phủ developer, CI, staging, production, DR và cách phân phối thực tế.
- [ ] License key/activation được thử trong đúng môi trường, gồm cả air-gapped nếu cần.
- [ ] Dependency được pin, nguồn artifact và SBOM được lưu.
- [ ] PoC chạy trên runtime image, classpath và JDBC driver dự kiến.
- [ ] Đã thử validate, SQL preview, fresh install, upgrade từ lịch sử và rollback/forward-fix.
- [ ] Đã kiểm tra hành vi khi thiếu extension, thiếu quyền, license lỗi và DBMS không hỗ trợ.
- [ ] Có support owner, lịch nâng cấp và phương án xử lý khi extension ngừng duy trì.
- [ ] Có exit plan để giữ khả năng đọc changelog và quản lý lịch sử.
- [ ] Quyết định cùng bằng chứng được lưu trong ADR/hồ sơ và có lịch review lại.

**Kết luận:** đánh giá tính năng bổ sung cho DATABASE_SCHEMA_MIGRATION_LIQUIBASE cần xem đồng thời giá trị chức năng, tương thích theo version, quyền sử dụng theo license và khả năng vận hành lâu dài. Hãy bắt đầu từ use case có tiêu chí đo được; xác minh Liquibase core, extension, Java, Spring Boot, JDBC và DBMS; đọc điều khoản license cho đúng môi trường; thử trên database trống lẫn database có lịch sử; kiểm tra dependency, bảo mật, secret và phương án thoát. Chỉ chấp thuận khi có bằng chứng kỹ thuật, entitlement hợp lệ và người chịu trách nhiệm bảo trì rõ ràng.
