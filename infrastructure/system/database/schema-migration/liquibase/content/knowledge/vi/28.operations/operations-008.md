# Nâng cấp Liquibase, JDBC và extension có kiểm thử tương thích

## 1. Vì sao phải nâng cấp cả bộ công cụ như một hệ thống?

Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Để migration hoạt động ổn định, nhóm còn phải kiểm chứng thay đổi, chuẩn bị rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi nâng cấp Liquibase, chỉ đổi version của thư viện lõi có thể chưa đủ: JDBC driver, extension, Java runtime, Spring Boot và DBMS cũng tham gia vào quá trình đọc changelog, sinh SQL, kết nối, thực thi và ghi lịch sử.

Một bộ phiên bản không tương thích có thể gây ra các lỗi khác nhau:

- Ứng dụng không khởi động vì extension không tìm thấy API hoặc class của Liquibase core.
- JDBC driver không hỗ trợ Java runtime, DBMS hoặc authentication mode đang dùng.
- SQL được sinh ra khác trước về kiểu dữ liệu, quoting, default, sequence hoặc cú pháp DDL.
- Changelog cũ không còn parse/validate theo cách trước đây.
- Checksum được tính lại hoặc changeset bị nhận diện khác sau khi đổi phiên bản.
- Migration chạy được trên database mới nhưng lỗi khi nâng từ schema đang tồn tại.
- Plugin/extension kéo vào một JDBC driver hoặc thư viện xung đột.

Vì vậy, nâng cấp cần có **ma trận tương thích, kiểm thử trên trạng thái database thật đại diện, kế hoạch phát hành và khả năng quay lại**. Mục tiêu là chứng minh bộ công cụ mới thực hiện đúng các migration hiện hữu và migration sắp phát hành trước khi đưa nó vào production.

## 2. Những thành phần cần đưa vào ma trận tương thích

### 2.1. Liquibase core

Liquibase core chịu trách nhiệm đọc changelog, tạo change object, đánh giá precondition/context/label, sinh SQL, thực thi changeset, tính checksum và quản lý lịch sử. Khi nâng version, cần kiểm tra:

- Cú pháp YAML, XML, JSON, SQL formatted changelog đang dùng.
- Change type và thuộc tính có trong các changeset cũ.
- Cách sinh SQL theo DBMS và phiên bản DBMS.
- Hành vi transaction, lock, retry và xử lý lỗi.
- Cách tính/đối chiếu checksum và cập nhật bảng DATABASECHANGELOG.
- Thay đổi về command, cấu hình, logging và API được ứng dụng sử dụng.

Không chỉ kiểm tra changelog mới. Một thay đổi trong parser hoặc SQL generator có thể ảnh hưởng tới hàng trăm changeset cũ dù source changelog không đổi.

### 2.2. JDBC driver

JDBC driver chuyển lời gọi JDBC thành giao thức riêng của database. Cần kiểm tra:

- Driver hỗ trợ Java runtime đang chạy.
- Driver hỗ trợ DBMS server version đang vận hành.
- Driver hỗ trợ authentication, TLS, certificate và connection properties của môi trường.
- Metadata mà driver trả về cho Liquibase có đúng không: kiểu dữ liệu, schema, catalog, constraint, sequence, generated column và tên object.
- Hành vi transaction, auto-commit, batch, timeout, network retry và exception SQLState.
- Các thay đổi về timezone, timestamp precision, UUID, JSON, decimal và Unicode.

Driver mới có thể sửa bug nhưng cũng có thể thay đổi metadata hoặc mặc định kết nối. Driver cũ có thể vẫn kết nối được nhưng không nhận diện đúng tính năng của server mới. Không suy ra tương thích chỉ từ việc ứng dụng mở được connection.

### 2.3. Extension và plugin

Extension có thể bổ sung change type, parser, generator, precondition, output format hoặc tích hợp với nền tảng. Extension thường phụ thuộc API của Liquibase core và có thể kéo thêm thư viện khác.

Với mỗi extension, cần biết:

- Version extension hỗ trợ version Liquibase core nào.
- Extension có hỗ trợ Java runtime và DBMS mục tiêu không.
- Nó có dùng SPI/ServiceLoader để đăng ký change type hoặc service không.
- Nó kéo theo dependency nào, đặc biệt là Liquibase core, JDBC driver, logging và thư viện XML/YAML/JSON.
- Có migration hoặc thay đổi cấu hình khi nâng extension không.
- Có license, security advisory và quy trình phát hành phù hợp không.

Không nâng extension độc lập nếu tài liệu của extension yêu cầu một cặp version cụ thể với Liquibase core.

### 2.4. Nền tảng và thành phần tích hợp

| Thành phần | Thông tin phải chốt | Lý do |
|---|---|---|
| Java runtime | Vendor, major version, patch/runtime image | Ảnh hưởng bytecode, TLS, class loading và JDBC |
| Spring Boot | Version ứng dụng và dependency management | Quyết định cách auto-configure Liquibase và quản lý dependency |
| Liquibase core | Version hiện tại và version dự kiến | Parser, SQL generator, checksum, API |
| JDBC driver | Artifact, version, DBMS/server version | Kết nối và metadata |
| Extension | Artifact, version, core compatibility | Change type/service bổ sung |
| DBMS | Engine, edition, version, compatibility level | SQL dialect và tính năng |
| Build tool | Maven/Gradle wrapper và dependency lock/management | Tính tái lập của dependency graph |
| Runtime image | JDK, OS, CA certificates, timezone data | Khác biệt giữa local và production |

Một thay đổi Spring Boot có thể kéo theo version Liquibase hoặc JDBC driver do BOM quản lý. Hãy xem dependency graph thực tế thay vì chỉ đọc version khai báo trực tiếp.

## 3. Lập ma trận tương thích trước khi sửa dependency

### 3.1. Ghi nhận trạng thái hiện tại

Tạo một bản ghi cho bộ phiên bản đang chạy:

| Thành phần | Hiện tại | Dự kiến | Nguồn xác nhận |
|---|---|---|---|
| Java | Ví dụ 17 | Ví dụ 21 | Runtime image và pipeline |
| Spring Boot | Version đang phát hành | Version mục tiêu | BOM / release notes |
| Liquibase core | Version đang phát hành | Version mục tiêu | Dependency tree |
| JDBC driver | Artifact và version hiện tại | Version mục tiêu | Dependency tree, vendor matrix |
| Extension A/B | Version hiện tại | Version tương thích | Tài liệu extension |
| DBMS | Engine và server version | Có thể giữ nguyên hoặc nâng riêng | Inventory database |
| Changelog | Format và change type đang dùng | Không đổi hoặc có chuyển đổi | Repository changelog |

Các version trong bảng ví dụ không phải khuyến nghị phiên bản. Phải điền giá trị thực tế của ứng dụng và xác minh bằng tài liệu phát hành của từng thành phần.

### 3.2. Xác minh theo từng cặp phụ thuộc

Không chỉ hỏi “Liquibase version X có chạy trên Java Y không?”. Hãy kiểm tra các quan hệ:

1. Liquibase core với Java runtime.
2. Liquibase core với từng extension.
3. JDBC driver với Java runtime.
4. JDBC driver với DBMS server version và authentication/TLS mode.
5. Spring Boot với Liquibase core được quản lý hoặc override.
6. Spring Boot với datasource pool và JDBC driver.
7. Extension với các thư viện bắc cầu khác trong ứng dụng.
8. SQL generator của Liquibase với từng DBMS/edition/version trong ma trận triển khai.

Kết quả phải ghi rõ nguồn xác nhận: release notes, compatibility matrix, tài liệu vendor, issue đã được xử lý hoặc kiểm thử nội bộ. Nếu tài liệu không xác nhận một cặp phiên bản, hãy đánh dấu cần thử nghiệm thay vì suy luận từ một cặp gần giống.

### 3.3. Phân biệt tương thích được hỗ trợ và tương thích quan sát được

Một tổ hợp có thể chạy trong một lần thử nhưng chưa chắc nằm trong ma trận được nhà cung cấp hỗ trợ. Ghi nhận hai trạng thái riêng:

- **Supported:** có tài liệu chính thức xác nhận tổ hợp nằm trong phạm vi hỗ trợ.
- **Verified internally:** nhóm đã chạy các kịch bản kiểm thử cần thiết trên tổ hợp đó.

Đối với production, nên có cả bằng chứng hỗ trợ và kết quả kiểm thử nội bộ. Một tổ hợp chưa được xác nhận chính thức có thể vẫn được chấp nhận theo chính sách rủi ro của tổ chức, nhưng quyết định đó cần được ghi nhận.

## 4. Quản lý version trong Maven, Gradle và Spring Boot

### 4.1. Pin version, tránh dependency trôi nổi

Không để version phụ thuộc vào giá trị latest, wildcard hoặc repository có thể thay artifact theo thời gian. Pin version của:

- Liquibase core.
- JDBC driver.
- Mỗi extension.
- Plugin build có tham gia validate/generate changelog.
- Thư viện hỗ trợ được override khỏi BOM.

Nếu Spring Boot BOM quản lý version, hãy để BOM quản lý khi version đó phù hợp. Nếu cần override, ghi lý do, kiểm tra compatibility và kiểm soát nơi override để tránh khai báo nhiều version khác nhau.

### 4.2. Kiểm tra dependency graph

Với Maven, có thể dùng:

~~~bash
mvn dependency:tree
~~~

Với Gradle, có thể dùng:

~~~bash
./gradlew dependencies
~~~

Mục tiêu là phát hiện:

- Có nhiều version Liquibase core cùng xuất hiện không.
- Extension có kéo một Liquibase core khác không.
- Có nhiều JDBC driver cho cùng DBMS không.
- Một thư viện logging/YAML/XML bị kéo về version không mong muốn không.
- Dependency bị exclude hoặc override có làm mất service provider không.

Hãy lưu kết quả dependency graph trong hồ sơ nâng cấp hoặc CI artifact. Dùng Maven/Gradle wrapper và cấu hình repository giống pipeline để kết quả có thể tái lập.

### 4.3. Quản lý version bằng BOM

Spring Boot dependency management BOM có thể điều phối version của nhiều thư viện. Khi nâng Spring Boot, danh sách version được quản lý có thể thay đổi. Cần xem:

- Liquibase version được BOM chọn.
- JDBC driver version được BOM chọn hoặc do dự án khai báo.
- Connection pool và thư viện logging.
- Plugin/runtime dependency có cùng classpath hay được tách riêng.

Không override một dependency chỉ vì muốn dùng bản mới nhất mà chưa kiểm tra những dependency liên quan. Nếu Liquibase CLI trong pipeline khác Liquibase library trong Spring Boot, phải chủ động xác minh hai môi trường dùng cùng changelog và SQL semantics.

## 5. Extension: kiểm tra API và classpath

### 5.1. Đọc release notes của extension

Mỗi extension nên có bảng tương thích riêng:

| Hạng mục | Câu hỏi |
|---|---|
| Liquibase core | Extension build/test với các core version nào? |
| Java | Bytecode và API yêu cầu Java nào? |
| DBMS | Change type hỗ trợ engine/version nào? |
| Changelog | Cấu trúc YAML/XML/SQL và thuộc tính có đổi không? |
| Runtime | Có cần service provider, resource hoặc cấu hình mới không? |
| Dependency | Có kéo thư viện khác hoặc xung đột version không? |
| Security | Có bản vá hoặc CVE cần xử lý không? |

Nếu extension không công bố compatibility matrix, xem release notes/source và thử nghiệm trong ứng dụng thật. Không suy ra extension tương thích chỉ vì Maven/Gradle resolve dependency thành công.

### 5.2. Kiểm tra ServiceLoader và resource

Một số extension đăng ký thành phần bằng Java Service Provider Interface. Khi đóng gói ứng dụng, shading, minimization hoặc repackaging có thể làm mất hoặc ghi đè file service metadata. Triệu chứng thường là Liquibase không nhận diện change type, database implementation hoặc service dù JAR có trong dependency tree.

Kiểm tra:

- Extension JAR có chứa service descriptor cần thiết.
- Packaging process giữ các resource service khi gộp JAR.
- Class loader runtime nhìn thấy đúng class và resource.
- Không có hai extension đăng ký cùng một service theo cách gây xung đột.

Thử trên artifact đã đóng gói giống production, không chỉ chạy test từ IDE nơi classpath khác.

### 5.3. Phân biệt lỗi classpath và lỗi SQL

Nếu Liquibase báo không tìm thấy change type hoặc class, ưu tiên kiểm tra dependency graph, version API và ServiceLoader. Nếu change type đã được nhận diện nhưng SQL sai hoặc database từ chối, kiểm tra SQL generator, DBMS/version, driver và quyền. Chẩn đoán đúng lớp giúp tránh thay đổi changelog để chữa lỗi classpath.

## 6. JDBC driver: kết nối thành công chưa đủ

### 6.1. Kiểm tra kết nối và metadata

Sau khi nâng driver, kiểm tra:

- Kết nối tới đúng host, port, database/catalog và schema.
- TLS, certificate chain, hostname verification và authentication.
- DatabaseMetaData trả đúng product name/version, driver name/version.
- Liệt kê được catalog, schema, table, column, index, primary key và foreign key cần thiết.
- Kiểu dữ liệu và default expression được nhận diện như kỳ vọng.
- Transaction, isolation, auto-commit và batch behavior đúng.

Liquibase dựa vào JDBC metadata trong nhiều hoạt động. Một driver có thể kết nối thành công nhưng trả metadata khác trước, dẫn tới diff, precondition, snapshot hoặc change type xử lý sai.

### 6.2. Các kiểu dữ liệu cần kiểm tra riêng

| Nhóm dữ liệu | Kịch bản kiểm tra |
|---|---|
| Timestamp/date | UTC, offset, session timezone, DST và độ chính xác |
| Decimal/numeric | Precision, scale, rounding, giá trị biên và overflow |
| UUID/GUID | Round-trip, binary/text representation và metadata |
| JSON | Encoding, native type, retrieval và default expression |
| Boolean | Mapping true/false/NULL giữa driver và DBMS |
| Unicode | Ký tự đa byte, collation, độ dài theo byte/ký tự |
| Binary/LOB | Kích thước lớn, streaming và transaction |
| Generated/identity | Metadata, sequence và giá trị sinh tự động |

Nếu ứng dụng dùng Java time API, kiểm tra cả mapping Hibernate/JPA và JDBC thuần. Không mặc định đổi driver sẽ giữ nguyên cách chuyển Timestamp, OffsetDateTime, Instant hoặc LocalDateTime.

### 6.3. Network, timeout và retry

Driver mới có thể thay đổi mặc định socket timeout, login timeout, keepalive, retry hoặc xử lý lỗi mạng. Kiểm thử:

- Database khởi động chậm hơn dự kiến.
- Connection bị ngắt giữa lúc đọc metadata.
- Migration chạy lâu và giữ connection/transaction.
- Failover hoặc proxy chuyển node.
- Timeout xảy ra trong DDL không transactional.

Không tự động retry một changeset không idempotent chỉ vì driver trả lỗi kết nối. Trước khi retry, cần xác định database đã thực thi câu lệnh hay chưa và đối chiếu DATABASECHANGELOG cùng trạng thái object.

## 7. Nâng cấp Liquibase mà không làm sai lịch sử changeset

### 7.1. Chạy thử trên bản sao database

Trước khi đổi version trên production, tạo bản sao có:

- Cùng DBMS engine/edition/version hoặc phiên bản đại diện đã được phê duyệt.
- Schema và dữ liệu đủ để tái hiện precondition, constraint, index và migration dữ liệu.
- Bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK hiện có.
- Các cấu hình context, label, parameter và schema tương đương.

Không chỉ thử trên database trống. Database mới kiểm tra được đường tạo schema từ đầu, nhưng không kiểm tra được nâng cấp một hệ thống đã chạy nhiều release.

### 7.2. Kiểm tra checksum và changeset đã triển khai

Checksum gắn với nội dung changeset và cách Liquibase diễn giải nó theo phiên bản. Khi nâng Liquibase, cần quan sát:

- Changeset cũ có được nhận diện là đã chạy không.
- Có checksum mismatch mới xuất hiện không.
- Có thay đổi checksum version/format cần được Liquibase xử lý không.
- validCheckSum có đang được dùng có chủ đích không.
- Có changeset nào bị sửa sau khi đã triển khai ở một môi trường không.

Không dùng clearCheckSums như bước mặc định của mọi lần nâng cấp. Lệnh này buộc Liquibase tính lại checksum; nó không sửa nội dung changeset sai và không chứng minh migration an toàn. Chỉ dùng khi đã hiểu nguyên nhân, có bản sao database để thử, có phê duyệt và biết chính xác ảnh hưởng lên lịch sử.

Nếu checksum mismatch do changeset cũ bị sửa, ưu tiên khôi phục nội dung đã phát hành hoặc tạo changeset mới cho thay đổi mong muốn. Không thay lịch sử production chỉ để làm cho lệnh update chạy qua.

### 7.3. Kiểm tra lock và trạng thái chạy dở

Nếu tiến trình cũ bị dừng giữa migration, có thể còn trạng thái lock hoặc DDL đã thực thi một phần tùy DBMS. Trước khi nâng cấp:

1. Xác định không còn Liquibase runner cũ đang hoạt động.
2. Kiểm tra DATABASECHANGELOGLOCK và log lần chạy trước.
3. Kiểm tra changeset cuối cùng đã ghi nhận.
4. Đối chiếu object thực tế với SQL của changeset.
5. Chỉ giải phóng lock theo quy trình được phê duyệt sau khi xác nhận không còn process sở hữu lock.

Không xóa hoặc sửa lock row tùy tiện. Không chạy hai version Liquibase đồng thời trên cùng schema metadata nếu chưa xác minh rõ cách phối hợp.

## 8. Quy trình nâng cấp theo từng bước

### Bước 1: Chọn mục tiêu và giới hạn thay đổi

Ghi rõ lý do nâng cấp: vá bảo mật, hỗ trợ Java/DBMS mới, sửa lỗi generator, cần extension mới hay nâng nền tảng Spring Boot. Chọn một tập thay đổi nhỏ có thể quy trách nhiệm. Nếu có thể, không nâng Liquibase core, JDBC driver, DBMS và Spring Boot cùng lúc; tách các thay đổi lớn giúp xác định nguyên nhân khi kiểm thử thất bại.

### Bước 2: Đọc release notes và compatibility matrix

Đọc ghi chú của từng phiên bản từ hiện tại đến mục tiêu, không chỉ bản cuối. Tìm:

- Breaking changes và API bị loại bỏ.
- Thay đổi SQL generator hoặc change type.
- Thay đổi checksum/parser/configuration.
- Bản vá bảo mật.
- Yêu cầu Java hoặc DBMS tối thiểu.
- Thay đổi JDBC authentication, TLS hoặc metadata.
- Yêu cầu version extension tương ứng.

Ghi lại mục nào ảnh hưởng trực tiếp tới changelog đang sử dụng.

### Bước 3: Cập nhật dependency trong nhánh riêng

Pin version mục tiêu, điều chỉnh BOM/override có chủ đích và kiểm tra dependency graph. Xác minh chỉ có một Liquibase core runtime, driver phù hợp và extension tương thích. Đóng gói artifact để phát hiện lỗi resource/classpath.

### Bước 4: Kiểm tra changelog tĩnh

Chạy validate bằng đúng Liquibase version mục tiêu và đúng extension classpath. Kiểm tra cả master changelog lẫn các include, parameter, context, label và formatted SQL. Validate không thay thế việc chạy trên database thật.

### Bước 5: Sinh SQL và review khác biệt

Chạy update-sql cho từng DBMS/version hỗ trợ. So sánh SQL cũ và mới, tập trung vào:

- Datatype, precision và default.
- Identifier quoting/case/schema qualification.
- Identity/sequence, index và constraint.
- DDL transaction boundary.
- SQL native hoặc modifySql.
- Câu lệnh liên quan extension.

Khác biệt SQL không mặc nhiên là lỗi; cần hiểu nó có giữ cùng ý nghĩa và đáp ứng vận hành không.

### Bước 6: Thử trên database có lịch sử

Khôi phục bản sao database đại diện rồi chạy status, update-sql và update với version mới. Xác nhận:

- Không chạy lại changeset đã triển khai.
- Changeset pending được chọn đúng.
- Checksum và lịch sử được xử lý như dự kiến.
- Schema/data sau update đúng.
- Lock được giải phóng.
- Log không có lỗi hoặc warning chưa được giải thích.

### Bước 7: Thử trên database trống

Tạo database mới và chạy toàn bộ changelog từ đầu. Bước này phát hiện dependency vào object tồn tại sẵn, schema thủ công hoặc migration chỉ đúng khi nâng từ một trạng thái cụ thể.

### Bước 8: Thử tích hợp ứng dụng

Khởi động ứng dụng Spring Boot bằng đúng runtime image, datasource, driver và Liquibase configuration. Kiểm tra health check, repository, transaction, truy vấn, routine, connection pool và mapping dữ liệu.

### Bước 9: Diễn tập triển khai và quay lại

Diễn tập đúng pipeline, credential, target, phê duyệt, thời gian chạy và bước quan sát. Chuẩn bị phương án dùng lại artifact/dependency cũ nếu migration chưa chạy; nếu migration đã chạy thì đánh giá forward-fix hoặc rollback có kiểm soát.

### Bước 10: Phát hành có giám sát

Chọn thời điểm, theo dõi migration job, thời lượng, lock, lỗi SQL, số changeset thực thi và trạng thái ứng dụng. Chỉ mở rộng rollout khi các kiểm tra sau migration đạt yêu cầu.

## 9. Bộ kiểm thử tương thích cần có

### 9.1. Ma trận tối thiểu

| Kịch bản | DB trống | DB đã có lịch sử | Mục tiêu |
|---|---:|---:|---|
| Validate changelog | Có | Có | Parser và extension nhận đúng |
| Status/update-sql | Có | Có | Chọn đúng changeset và SQL |
| Update toàn bộ | Có | Có | Fresh install và upgrade path |
| Checksum/history | Không đủ | Có | Giữ lịch sử và nhận diện changeset |
| Rollback hoặc forward-fix | Có | Có | Khôi phục/điều chỉnh trạng thái |
| Metadata/permission | Có | Có | Driver và user đọc/ghi đúng |
| Application smoke test | Có | Có | JDBC mapping và truy vấn thực tế |
| Lock/concurrency | Có | Có | Nhiều runner không làm sai trạng thái |

### 9.2. Kiểm thử theo DBMS

Nếu sản phẩm hỗ trợ PostgreSQL, MySQL, SQL Server và Oracle, chạy bộ kiểm thử trên từng engine/version được hỗ trợ. H2 hoặc database giả lập có thể hữu ích cho test ứng dụng đơn giản nhưng không chứng minh tương thích DDL, metadata, lock và datatype của engine production.

| Lớp | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| JDBC connection/TLS | Test | Test | Test | Test |
| Metadata snapshot | Test | Test | Test | Test |
| SQL generation | Test | Test | Test | Test |
| Fresh install | Test | Test | Test | Test |
| Upgrade từ lịch sử | Test | Test | Test | Test |
| Rollback/forward-fix | Test | Test | Test | Test |
| Spring Boot runtime | Test | Test | Test | Test |

Không cần mọi nhánh pipeline chạy đồng thời nếu chi phí lớn, nhưng mỗi DBMS nằm trong phạm vi hỗ trợ phải có lịch chạy và điều kiện pass rõ ràng trước release.

### 9.3. Dùng database tạm thời và dữ liệu đại diện

Database container/ephemeral instance giúp kiểm thử lặp lại, nhưng phải dùng image/version tương ứng với môi trường mục tiêu. Với tính năng không có trong image test, cần môi trường DBMS phù hợp. Dataset phải đủ để precondition, constraint, backfill, index và migration hiệu năng thể hiện hành vi thực.

Kiểm thử không chỉ hỏi lệnh update có exit code 0. Hãy xác minh metadata schema, số hàng, kiểu cột, default, index, constraint, execution type, checksum và ứng dụng đọc/ghi dữ liệu sau migration.

## 10. Kiểm tra tương thích của extension cụ thể

Với mỗi extension, xây dựng một test nhỏ độc lập:

1. Khai báo extension đúng version trong dependency graph.
2. Đảm bảo Liquibase nhận diện extension/service sau khi đóng gói.
3. Parse changelog có change type hoặc thuộc tính extension.
4. Chạy validate và update-sql trên mỗi DBMS được extension hỗ trợ.
5. Chạy update trên database tạm thời.
6. Kiểm tra metadata, object và dữ liệu sinh ra.
7. Thử rollback nếu extension hỗ trợ rollback hoặc xác định forward-fix.
8. Kiểm tra extension hoạt động trong runtime image giống production.

Nếu extension cung cấp change type custom, không giả định Liquibase có thể tự sinh rollback. Đọc tài liệu extension và kiểm tra SQL/rollback thực tế. Nếu extension dùng API không ổn định, hãy pin version core và extension theo cặp đã thử.

## 11. Tương thích giữa Spring Boot và Liquibase

### 11.1. Auto-configuration và dependency management

Spring Boot có thể tự cấu hình Liquibase khi dependency có mặt và các điều kiện datasource phù hợp. Khi nâng Spring Boot, kiểm tra:

- Property spring.liquibase.* còn được hỗ trợ và binding đúng.
- Version Liquibase được BOM quản lý.
- JDBC datasource/connection pool được tạo trước Liquibase theo đúng điều kiện.
- Datasource riêng cho Liquibase có được chọn như dự kiến.
- Bean custom SpringLiquibase hoặc @LiquibaseDataSource không xung đột với auto-configuration.
- spring.liquibase.enabled được bật/tắt đúng ở job và runtime.

Nếu migration chạy trong CI/CD riêng, ứng dụng runtime có thể tắt Liquibase auto-run sau khi pipeline đã cập nhật schema. Cấu hình phải nhất quán giữa local, test và production; tránh để local startup migration vô tình che một lỗi mà pipeline độc lập sẽ gặp.

### 11.2. Không để hai phiên bản Liquibase chạy lẫn

Một dự án có thể có Liquibase CLI trong pipeline và Liquibase library trong ứng dụng. Hai nơi phải được đồng bộ hoặc khác biệt có chủ đích:

- Cùng version core và extension khi có thể.
- Cùng master changelog và resource SQL.
- Cùng context, label, parameters và schema.
- Cùng DBMS driver hoặc tổ hợp driver đã xác minh.

Nếu CLI chạy version mới còn ứng dụng startup chạy version cũ, cùng changelog có thể được parse hoặc sinh SQL khác nhau. Ghi rõ version trong pipeline log và artifact.

## 12. Kế hoạch rollback khi nâng công cụ

### 12.1. Phân biệt rollback dependency và rollback database

Có hai loại quay lại:

- **Rollback công cụ:** dùng lại artifact/container image cũ, Liquibase core, driver và extension cũ.
- **Rollback database:** đảo ngược changeset hoặc sửa schema/data đã thay đổi.

Rollback công cụ không tự hoàn tác migration đã chạy. Nếu version Liquibase mới đã cập nhật schema hoặc lịch sử, việc chạy lại version cũ có thể không an toàn. Trước release phải xác minh khả năng đọc lịch sử, checksum và schema mới bằng version cũ.

### 12.2. Chọn forward-fix khi cần

DDL trên một số DBMS có thể commit ngầm hoặc không rollback toàn bộ. Một changeset có thể thực hiện một phần trước khi lỗi. Nếu database đã thay đổi, đôi khi forward-fix an toàn hơn rollback toàn bộ. Cần xác định:

- Changeset nào đã ghi vào DATABASECHANGELOG.
- SQL nào đã thực thi trước khi lỗi.
- Object và dữ liệu thực tế hiện tại.
- Driver/Liquibase version nào tạo ra trạng thái đó.
- Ứng dụng cũ/mới có tương thích schema hiện tại không.

Không chỉnh sửa thủ công checksum hoặc xóa history row để ép chạy lại. Ghi nhận trạng thái và tạo changeset sửa chữa có chủ đích.

### 12.3. Expand-contract cho ứng dụng

Khi nâng công cụ đồng thời với thay đổi schema/ứng dụng, ưu tiên thay đổi tương thích ngược:

1. Expand: thêm cột/bảng/index mới mà ứng dụng cũ vẫn chạy được.
2. Deploy ứng dụng có thể đọc/ghi cả cấu trúc cũ và mới khi cần.
3. Backfill và xác minh dữ liệu.
4. Chuyển traffic sang logic mới.
5. Contract: xóa cấu trúc cũ ở một release sau khi chắc chắn không còn consumer.

Không gộp nâng Liquibase, đổi JDBC driver và phá vỡ schema vào một bước không thể phân tách nếu chưa có kiểm thử và kế hoạch phục hồi.

## 13. Quan sát sau nâng cấp

Trong lần chạy đầu tiên với bộ công cụ mới, theo dõi:

- Liquibase version, Java version, JDBC driver và extension version trong log khởi động/job.
- Database product/version mà driver nhận diện.
- Tổng số changeset pending và số changeset thực thi.
- Thời lượng từng changeset và tổng migration.
- Lock wait, connection timeout, deadlock và SQL exception.
- Checksum validation, precondition và warning.
- Trạng thái schema/data sau migration.
- Health check và lỗi truy vấn của ứng dụng sau rollout.

Không log password, access token hoặc JDBC URL có credential. Log nên đủ để liên kết release, commit, migration job và database target mà không lộ bí mật.

Đặt ngưỡng dừng release trước khi chạy: ví dụ migration vượt thời gian dự kiến, lock giữ quá lâu, số changeset không đúng, SQL lỗi hoặc smoke test thất bại. Ngưỡng phải theo đặc tính hệ thống, không dùng một con số chung cho mọi database.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Lớp cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| Không tìm thấy custom change type | Extension/classpath/SPI | Kiểm tra dependency tree, service descriptor và packaging |
| NoSuchMethodError hoặc ClassNotFoundException | Core-extension API hoặc dependency trùng version | Đồng bộ version, loại dependency bắc cầu xung đột |
| Không kết nối được database | JDBC driver, TLS, authentication, network | Kiểm tra driver/server matrix và connection properties |
| Kết nối được nhưng snapshot thiếu object | JDBC metadata, quyền catalog/schema | Kiểm tra metadata API và grants |
| SQL preview khác version cũ | SQL generator, DBMS version, extension | Review SQL diff và chạy trên DBMS thật |
| Checksum mismatch sau nâng cấp | Changeset bị sửa hoặc cách tính checksum thay đổi | Đối chiếu source đã phát hành và thử trên bản sao |
| Chạy được DB trống nhưng lỗi DB hiện hữu | Upgrade path, precondition, dữ liệu thực | Test từ snapshot có lịch sử và dataset đại diện |
| Liquibase lock không giải phóng | Process cũ, timeout hoặc lỗi giữa migration | Xác minh process và trạng thái object trước xử lý lock |
| Spring Boot chạy Liquibase hai lần | Auto-configuration và bean custom | Kiểm tra bean, datasource và lifecycle |
| Local chạy nhưng CI lỗi | Khác JDK, classpath, DBMS, profile hoặc version | Dùng wrapper/image/config giống pipeline |

Khi chẩn đoán, thu thập version đầy đủ, dependency graph, SQL preview, log đã che secret, trạng thái DATABASECHANGELOG và metadata object. Không thay đổi nhiều thành phần cùng lúc trước khi khoanh vùng nguyên nhân.

## 15. Checklist phát hành bộ phiên bản mới

- [ ] Đã ghi lại version Java, Spring Boot, Liquibase core, JDBC driver, extension và DBMS hiện tại/mục tiêu.
- [ ] Đã xác nhận compatibility matrix và release notes cho từng cặp phụ thuộc.
- [ ] Dependency được pin; không dùng latest hoặc version trôi nổi.
- [ ] Dependency graph không có nhiều Liquibase core hoặc JDBC driver xung đột.
- [ ] Extension tương thích với core/Java/DBMS và resource SPI còn nguyên sau packaging.
- [ ] Artifact đã đóng gói được kiểm tra trên runtime image giống production.
- [ ] Validate master changelog và toàn bộ include bằng version mục tiêu.
- [ ] Update-sql đã được review cho từng DBMS/version hỗ trợ.
- [ ] Đã thử update từ database trống và database có lịch sử thực tế.
- [ ] Đã kiểm tra checksum, DATABASECHANGELOG, lock và execution type.
- [ ] Đã kiểm tra kiểu dữ liệu, default, identifier, constraint, index và metadata JDBC.
- [ ] Đã kiểm tra transaction, timeout, retry, TLS, authentication và connection pool.
- [ ] Đã chạy integration/smoke test ứng dụng với driver và schema mới.
- [ ] Đã diễn tập pipeline migration và xác nhận đúng credential/target.
- [ ] Có phương án rollback công cụ và phương án database riêng biệt.
- [ ] Có forward-fix nếu DDL đã commit hoặc migration chỉ thực hiện một phần.
- [ ] Có log/metric để quan sát và ngưỡng dừng release.

**Kết luận:** nâng cấp Liquibase, JDBC và extension là thay đổi của cả chuỗi thực thi migration. Hãy lập ma trận version, kiểm tra API/classpath, metadata JDBC và SQL generator; sau đó thử cả database trống lẫn database đã có lịch sử trên từng DBMS được hỗ trợ. Giữ dependency có thể tái lập, bảo vệ checksum và bảng lịch sử, diễn tập rollback công cụ riêng với rollback database, rồi phát hành có giám sát. Quy trình đó giúp DATABASE_SCHEMA_MIGRATION_LIQUIBASE tiếp tục quản lý schema và dữ liệu đáng tin cậy khi nền tảng Java, Spring Boot, driver, Liquibase và extension thay đổi.
