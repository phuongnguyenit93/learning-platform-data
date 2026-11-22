# Đọc release notes và đối chiếu ma trận tương thích trước khi nâng cấp

Nâng cấp Spring Data R2DBC không chỉ là đổi một con số version trong Gradle hoặc Maven. Một ứng dụng R2DBC chạy trên nhiều lớp phụ thuộc nhau: Java, Spring Boot, Spring Framework, Spring Data, Reactor, R2DBC SPI, driver của database, connection pool và chính database server. Một phiên bản mới có thể yêu cầu Java cao hơn, Spring Framework mới hơn, SPI khác, hoặc thay đổi hành vi mapping và transaction.

Trước khi nâng cấp, hãy đọc release notes và migration guide của toàn bộ dải phiên bản từ bản đang chạy tới bản đích, sau đó đối chiếu từng thành phần với compatibility matrix chính thức. Kết quả cần là một quyết định có bằng chứng: phiên bản đích được hỗ trợ, các thay đổi ảnh hưởng ứng dụng đã được nhận diện, dependency graph được căn chỉnh và kế hoạch kiểm thử/rollback đã rõ.

## 1. Vì sao phải đọc release notes trước khi đổi version?

Release notes ghi lại thay đổi giữa các phiên bản: tính năng mới, bug fixes, deprecation, breaking changes, dependency baseline và hành vi được điều chỉnh. Một nâng cấp có thể biên dịch thành công nhưng vẫn làm thay đổi runtime behavior.

Trong Spring Data R2DBC, tác động có thể xuất hiện ở nhiều lớp:

- Spring Data Relational/R2DBC thay đổi mapping, query derivation, repository API, converters hoặc dialect.
- Spring Framework thay đổi reactive transaction, bean lifecycle, proxy hoặc tích hợp Reactor.
- R2DBC SPI thay đổi interface/contract mà driver và pool triển khai.
- Database driver thay đổi type mapping, bind parameter, generated values, cancellation hoặc protocol behavior.
- Spring Boot thay đổi auto-configuration, property names, dependency versions và điều kiện tạo bean.
- Java baseline thay đổi khiến ứng dụng hoặc plugin build không còn chạy trên JDK cũ.
- Database server mới/cũ có thể không còn nằm trong ma trận hỗ trợ của driver.

Release notes giúp phát hiện những thay đổi này trước khi chúng trở thành lỗi ở production.

### 1.1. Nâng cấp thành công không chỉ có nghĩa là build pass

Một build pass chỉ cho biết mã nguồn và dependency đã qua được một phần kiểm tra compile/test. Nó không chứng minh:

- Driver có tương thích với database server đang dùng.
- Transaction rollback/commit vẫn đúng.
- Mapping cho JSON, UUID, enum, array, timestamp hoặc decimal vẫn như cũ.
- Connection pool xử lý timeout, validation và shutdown đúng.
- Query tùy chỉnh vẫn chạy đúng SQL dialect.
- Migration và schema hiện tại vẫn tương thích.
- Runtime Java trong production đáp ứng baseline mới.

Vì vậy, cần kết hợp release-note review, dependency analysis, compatibility matrix và integration test trên database mục tiêu.

## 2. Xác định chính xác phiên bản hiện tại

Trước khi chọn phiên bản đích, hãy xác định ứng dụng thực sự đang chạy phiên bản nào. Version khai báo trực tiếp trong build file có thể khác version cuối cùng được resolve do BOM, dependency constraints, plugin hoặc dependency bắc cầu.

Thu thập tối thiểu:

| Thành phần | Cần xác định |
|---|---|
| Java | JDK dùng để build và JRE/JDK dùng khi chạy |
| Spring Boot | Plugin và dependency management version |
| Spring Framework | spring-core, spring-context, spring-r2dbc và các module liên quan |
| Spring Data | Release train và spring-data-relational/spring-data-r2dbc |
| Reactor | reactor-core và Reactor BOM |
| R2DBC SPI | io.r2dbc:r2dbc-spi |
| Database driver | Ví dụ r2dbc-postgresql hoặc r2dbc-mysql |
| Connection pool | Ví dụ r2dbc-pool nếu dùng |
| Database server | Engine, major/minor version và extensions |
| Build tool | Gradle wrapper hoặc Maven wrapper |
| Migration tool | Flyway/Liquibase version và JDBC driver nếu có |

### 2.1. Kiểm tra dependency graph thực tế

Với Gradle, xem dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để tìm lý do một dependency có version cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-data-r2dbc --configuration runtimeClasspath
~~~

Kiểm tra các thành phần liên quan khác:

~~~bash
./gradlew dependencyInsight --dependency r2dbc-spi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Có thể lọc theo artifact:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-r2dbc
mvn dependency:tree -Dincludes=io.r2dbc:r2dbc-spi,io.r2dbc:r2dbc-postgresql
~~~

Hãy kiểm tra output và xác nhận dependency được resolve từ nguồn nào. Không chỉ xem file build. Hãy kiểm tra dependency lockfile, version catalog, platform/BOM, plugin và cấu hình CI để hiểu version thực tế trong mọi môi trường.

## 3. Xác định phiên bản đích và phạm vi nâng cấp

Trước khi chọn target, trả lời các câu hỏi:

- Phiên bản hiện tại còn được hỗ trợ và nhận security fixes không?
- Có CVE hoặc lỗi nghiêm trọng nào buộc phải nâng cấp không?
- Phiên bản đích có hỗ trợ JDK production không?
- Spring Boot target quản lý Spring Framework và Spring Data release train nào?
- Driver R2DBC target hỗ trợ database server hiện tại không?
- Có bắt buộc nâng cấp database server cùng lúc không?
- Có breaking changes hoặc migration guide cần thực hiện không?
- Build tool/plugin hiện tại có hỗ trợ JDK cần thiết không?

### 3.1. Phân biệt patch, minor và major

Tên và quy tắc version khác nhau giữa các dự án. Không nên áp dụng SemVer một cách máy móc cho mọi thành phần Spring.

Một cách phân loại thực tế:

- **Patch update:** thường tập trung vào bug fixes và security fixes trong cùng dòng phát hành, nhưng vẫn cần đọc release notes vì có thể thay đổi hành vi hoặc dependency.
- **Minor/feature update:** có thể bổ sung API, deprecate API cũ và thay đổi dependency baseline.
- **Major hoặc release-train transition:** có khả năng chứa breaking changes, yêu cầu JDK/Spring Framework mới hơn và migration steps rõ ràng.

Spring Data dùng release train để phối hợp các module. Spring Boot quản lý một tập version cụ thể của Spring Framework, Spring Data, Reactor và các dependency khác. Vì vậy, target cần được chọn theo một tổ hợp được hỗ trợ, không phải chọn riêng từng artifact có số version mới nhất.

### 3.2. Không nhảy qua các release notes trung gian

Giả sử ứng dụng đang ở release train A và muốn chuyển tới train D. Cần đọc các thay đổi của B, C và D, không chỉ trang release notes của D.

Một thay đổi có thể được giới thiệu ở B, deprecate ở C và bị xóa ở D. Nếu chỉ đọc D, có thể bỏ qua lý do API cũ đã bị thay thế và cách migration được khuyến nghị từ trước.

Với một nâng cấp lớn, hãy ghi lại chuỗi phiên bản:

~~~text
Current
  -> intermediate release 1
  -> intermediate release 2
  -> target release
~~~

Không nhất thiết phải deploy từng phiên bản trung gian vào production. Nhưng cần đọc và xử lý các migration notes trong toàn bộ dải nâng cấp; đôi khi build/test theo từng bước trung gian giúp cô lập nguyên nhân lỗi.

## 4. Nguồn tài liệu cần đối chiếu

Ưu tiên tài liệu chính thức của từng dự án và đúng phiên bản.

| Nguồn | Dùng để kiểm tra |
|---|---|
| Spring Boot release notes và migration guide | JDK baseline, auto-configuration, property changes, dependency versions |
| Spring Boot dependency versions appendix | Phiên bản Spring Framework, Spring Data, Reactor và thư viện được quản lý |
| Spring Data release notes | Thay đổi repository, mapping, query, dialect, converter và module |
| Spring Data compatibility matrix | Quan hệ giữa release train và Spring Framework baseline |
| Spring Framework release notes | Reactive transaction, bean lifecycle, proxy và API framework |
| R2DBC SPI release notes/specification | Contract giữa framework, driver và pool |
| R2DBC driver documentation | Database server, Java, SPI, TLS, type mapping và driver-specific behavior |
| Database vendor support matrix | Database server version, protocol và tính năng được hỗ trợ |
| Reactor release notes/BOM | API Reactor và tương thích với Spring Framework |
| Gradle/Maven release notes | JDK và plugin/build compatibility |
| Security advisories/CVE | Phiên bản bị ảnh hưởng và bản vá |

Không dùng một bảng compatibility cũ trong blog hoặc câu trả lời diễn đàn làm bằng chứng duy nhất. Nếu thông tin trong blog khác tài liệu chính thức, ghi nhận sự khác biệt và xác minh theo tài liệu đúng version.

### 4.1. Đọc đúng phiên bản tài liệu

Một trang reference documentation có thể mặc định hiển thị phiên bản mới nhất. Khi ứng dụng đang nâng cấp lên phiên bản cũ hơn, phải chuyển trang tài liệu sang đúng version hoặc đọc tag release tương ứng.

Đối chiếu các tài liệu cùng một target line. Không lấy migration guide của Spring Boot mới nhất rồi ghép với driver cũ mà chưa xác nhận tương thích.

### 4.2. Kiểm tra support lifecycle

Compatibility không đồng nghĩa với còn được hỗ trợ. Một tổ hợp có thể chạy được nhưng đã hết thời gian nhận security fixes.

Ghi nhận ngày phát hành và trạng thái support, hạn kết thúc hỗ trợ cộng đồng hoặc commercial support nếu tổ chức sử dụng, security fixes có được backport không, target có phải release line được tổ chức chấp nhận không và thời gian dự kiến phải nâng cấp tiếp theo.

## 5. Lập compatibility matrix cho ứng dụng

Compatibility matrix là bảng ghi lại phiên bản hiện tại, phiên bản đích, ràng buộc chính thức và kết quả xác minh của từng thành phần.

Ví dụ mẫu:

| Thành phần | Hiện tại | Target | Bằng chứng cần có | Trạng thái |
|---|---|---|---|---|
| Java runtime | JDK hiện tại | JDK target | Spring Boot system requirements | Chưa xác minh |
| Spring Boot | Boot current | Boot target | Boot release notes/dependency appendix | Chưa xác minh |
| Spring Framework | Framework current | Boot-managed target | Boot BOM + Framework release notes | Chưa xác minh |
| Spring Data train | Train current | Boot-managed target | Spring Data compatibility matrix | Chưa xác minh |
| spring-data-r2dbc | Resolved current | Managed target | Spring Data release notes | Chưa xác minh |
| Reactor | Resolved current | Boot-managed target | Reactor BOM/release notes | Chưa xác minh |
| R2DBC SPI | Resolved current | Driver-compatible target | SPI contract + driver docs | Chưa xác minh |
| R2DBC driver | Driver current | Driver target | Driver compatibility matrix | Chưa xác minh |
| Connection pool | Pool current | Pool target | Pool/SPI compatibility | Chưa xác minh |
| Database server | Server current | Current hoặc target | Vendor support matrix | Chưa xác minh |
| Build tool | Wrapper current | Wrapper target | Gradle/Maven JDK compatibility | Chưa xác minh |
| Migration tool | Flyway/Liquibase current | Target | Migration tool compatibility | Chưa xác minh |

Không điền “compatible” chỉ vì version numbers gần nhau. Mỗi trạng thái cần bằng chứng cụ thể, ví dụ tên trang tài liệu, version range hoặc kết quả integration test.

### 5.1. Phân loại trạng thái trong matrix

Có thể dùng các trạng thái:

- **Supported:** được tài liệu chính thức xác nhận hoặc nằm trong ma trận hỗ trợ.
- **Verified:** đã kiểm thử trong môi trường tương ứng và đạt yêu cầu.
- **Conditional:** có điều kiện như database minimum version, JDK hoặc driver option.
- **Unknown:** chưa tìm thấy bằng chứng đủ tin cậy.
- **Unsupported:** tài liệu xác nhận không hỗ trợ.
- **Blocked:** có incompatibility hoặc lỗi chưa xử lý.

Supported và Verified là hai khái niệm khác nhau. Một tổ hợp có thể được vendor hỗ trợ nhưng chưa được ứng dụng kiểm thử; ngược lại, một tổ hợp có thể chạy qua vài test nhưng nằm ngoài ma trận hỗ trợ chính thức.

### 5.2. Ghi rõ nguồn và ngày kiểm tra

Mỗi hàng quan trọng nên có URL hoặc tên tài liệu chính thức, phiên bản tài liệu đã xem, ngày kiểm tra, điều kiện hỗ trợ, kết quả test nội bộ và người chịu trách nhiệm nếu quy trình của tổ chức yêu cầu.

Compatibility matrix nhanh chóng lỗi thời khi driver hoặc database phát hành bản mới. Ghi nguồn và ngày giúp lần nâng cấp sau xác minh lại được.

## 6. Quan hệ giữa Spring Boot, Spring Framework và Spring Data

Trong ứng dụng Spring Boot, Boot BOM quản lý một tổ hợp dependency đã được kiểm thử cùng nhau. Spring Data release train cũng phối hợp version của các module Spring Data.

Vì vậy, khi nâng cấp Boot:

1. Xác định target Boot release.
2. Đọc Boot release notes và migration guide.
3. Xem dependency versions appendix để biết Framework, Data, Reactor và các dependency được quản lý.
4. Kiểm tra Spring Data compatibility matrix cho release train đó.
5. Đối chiếu driver R2DBC và database riêng vì không phải mọi driver đều được Boot quản lý hoặc kiểm thử end-to-end.

Không tự nâng spring-data-r2dbc lên một version mới hơn Boot BOM chỉ vì kho artifact có bản mới. Việc override có thể kéo theo Spring Data Relational, Spring Framework hoặc API khác không tương thích.

### 6.1. Dùng Spring Boot BOM

Với Gradle, một cấu hình phổ biến là dùng Spring Boot plugin và dependency management do Boot cung cấp:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<boot-target>"
    id("io.spring.dependency-management") version "<dependency-management-plugin>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Version placeholder cần được thay bằng version target đã chọn và xác minh. Nếu dự án dùng Gradle platform/BOM trực tiếp thay cho dependency-management plugin, hãy nhất quán với cách quản lý dependency của dự án.

Với Maven, dùng spring-boot-starter-parent hoặc import spring-boot-dependencies BOM theo cấu trúc dự án. Đừng khai báo version riêng cho từng Spring Framework/Spring Data artifact nếu BOM đã quản lý chúng.

### 6.2. Khi không dùng Spring Boot

Nếu dùng Spring Data R2DBC độc lập:

- Chọn Spring Data release train phù hợp.
- Import Spring Data BOM của train đó.
- Kiểm tra Spring Framework baseline được train yêu cầu.
- Chọn R2DBC SPI và driver theo tài liệu driver.
- Căn chỉnh Reactor và các dependency reactive theo yêu cầu framework.
- Tự kiểm tra dependency convergence vì không có Boot BOM làm bộ quản lý tổng thể.

Không trộn module Spring Data từ các release train khác nhau trừ khi tài liệu chính thức chỉ rõ một trường hợp được hỗ trợ.

## 7. Đối chiếu R2DBC SPI, driver và connection pool

Đây là phần đặc biệt quan trọng với ứng dụng R2DBC. Spring Data có thể tương thích với Spring Framework nhưng driver vẫn có thể không tương thích với SPI mà framework/pool đang dùng.

### 7.1. R2DBC SPI là hợp đồng giữa các thành phần

R2DBC SPI định nghĩa các abstraction như ConnectionFactory, Connection, Statement, Result, Row và transaction-related operations. Driver triển khai các abstraction này cho database cụ thể.

Khi SPI thay đổi:

- Driver cần hỗ trợ contract tương ứng.
- Pool cần tương thích với SPI và driver.
- Framework cần dùng API SPI phù hợp.
- Một số behavior về cancellation, metadata, result mapping hoặc connection lifecycle có thể khác.

Không ép một version r2dbc-spi tùy ý để “sửa” dependency conflict. Hãy xác định version nào được driver và framework hỗ trợ, rồi dùng dependency management tương ứng.

### 7.2. Driver có ma trận riêng

Đối chiếu tối thiểu:

- Driver version có hỗ trợ R2DBC SPI version được resolve không?
- Driver có hỗ trợ Java runtime đang dùng không?
- Driver hỗ trợ database server major version nào?
- Driver có hỗ trợ TLS/authentication mode production không?
- Type mapping có thay đổi giữa các phiên bản không?
- Có thay đổi bind parameter, generated key hoặc batch statement không?
- Cancellation/timeout có behavior hoặc limitation mới không?
- Có known issue với pooling hoặc transaction không?

Ví dụ PostgreSQL, MySQL và SQL Server dùng driver khác nhau; không suy ra compatibility của một driver từ driver khác.

### 7.3. Connection pool

Nếu dùng r2dbc-pool, kiểm tra:

- Pool version và SPI version.
- Connection validation và validation query.
- max-size, initial-size và acquire timeout.
- max-idle-time, max-life-time và background eviction.
- Hành vi khi connection bị đóng hoặc database restart.
- Connection disposal khi cancellation/timeout.
- Graceful shutdown và leak detection nếu hỗ trợ.

Không chỉ kiểm tra ứng dụng tạo được connection. Cần test pool dưới tải, khi database restart và khi connection hết hạn.

## 8. Đối chiếu database server và tính năng được sử dụng

Driver hỗ trợ một database server version không có nghĩa mọi tính năng của database đều giống nhau giữa các major version.

Hãy kiểm tra:

- Database server hiện tại còn được vendor hỗ trợ không?
- Driver target hỗ trợ server major version nào?
- SQL syntax hoặc data type nào được ứng dụng dùng?
- Extension/plugin nào đang được bật?
- TLS/authentication policy có thay đổi không?
- Query plan hoặc index behavior có thay đổi đáng kể không?
- Replication, failover hoặc cluster topology có được hỗ trợ?
- Migration có sử dụng tính năng riêng của một server version không?

Nếu đồng thời nâng cấp database server và R2DBC driver, thay đổi có thể chồng lấp. Khi có thể, tách hai thay đổi để dễ xác định nguyên nhân khi lỗi.

### 8.1. Type mapping và dữ liệu

Đặc biệt kiểm tra UUID, JSON/JSONB, enum, array, numeric/decimal precision, timestamp with/without time zone, binary/LOB, null handling và generated identity/sequence values.

Driver có thể thay đổi Java type trả về hoặc cách bind giá trị. Custom converter có thể cần điều chỉnh dù repository method vẫn compile.

### 8.2. Query và dialect

Kiểm tra derived query, @Query, DatabaseClient SQL, Criteria và custom repository implementation. Một query chạy được trên database version cũ có thể phụ thuộc behavior không còn giống ở version mới.

Đọc dialect-related release notes và kiểm tra query plan cho những truy vấn quan trọng sau nâng cấp driver/database.

## 9. Đọc release notes theo một quy trình có hệ thống

Không chỉ tìm từ khóa “breaking”. Hãy đọc release notes theo thứ tự:

1. **Overview:** mục tiêu và phạm vi release.
2. **Requirements:** JDK, Spring Framework, SPI hoặc database baseline.
3. **Breaking changes:** API bị xóa, thay đổi contract, behavior không tương thích.
4. **Deprecations:** API đã deprecated và thời điểm dự kiến bị xóa.
5. **Behavior changes:** default, mapping, transaction, pooling hoặc error handling thay đổi.
6. **Dependency updates:** version BOM, driver, Reactor hoặc library bắc cầu.
7. **Bug fixes:** lỗi đang ảnh hưởng ứng dụng có được sửa không.
8. **Security fixes:** CVE, mức độ ảnh hưởng và bản vá.
9. **Migration guide:** bước chuyển đổi cụ thể và cấu hình thay thế.
10. **Known issues:** lỗi đã biết hoặc workaround.

### 9.1. Tìm thay đổi liên quan trực tiếp tới codebase

Từ inventory của ứng dụng, lập danh sách các API và tính năng đang dùng:

- ReactiveCrudRepository, R2dbcEntityTemplate.
- DatabaseClient và bind/bindNull.
- Mapping annotations và custom converters.
- Auditing.
- Reactive transaction manager và TransactionalOperator.
- Custom dialect/repository implementation.
- ConnectionFactory, pooling và driver options.
- Spring Boot R2DBC auto-configuration.
- Migration và database initialization.

Tìm các thuật ngữ này trong release notes, migration guide và issue tracker của phiên bản liên quan. Chỉ đọc phần chung mà không đối chiếu codebase dễ bỏ sót tác động thực tế.

### 9.2. Phân loại mỗi thay đổi

Ghi từng thay đổi vào bảng:

| Phân loại | Ý nghĩa | Hành động |
|---|---|---|
| Breaking API | Mã nguồn có thể không compile | Sửa code theo migration guide |
| Breaking behavior | Compile được nhưng runtime behavior khác | Thêm regression test |
| Deprecation | API vẫn chạy nhưng sẽ bị loại bỏ | Lập kế hoạch thay thế |
| Dependency baseline | Yêu cầu JDK/Framework/SPI mới | Điều chỉnh platform |
| Security fix | Sửa lỗ hổng | Xác định mức độ khẩn cấp và phạm vi |
| Bug fix | Sửa lỗi hiện tại | Kiểm thử case tương ứng |
| Configuration change | Property/default thay đổi | Cập nhật config và deployment |
| Operational change | Pool, metrics, logging hoặc lifecycle đổi | Cập nhật vận hành/monitoring |

Không cần sửa mọi deprecated API ngay nếu release guide không bắt buộc, nhưng phải ghi nhận để tránh bị bất ngờ ở lần nâng cấp major tiếp theo.

## 10. Kiểm tra thay đổi trong Spring Data R2DBC

Một số nhóm thay đổi cần chú ý khi đọc Spring Data release notes.

### 10.1. Repository API và query derivation

Kiểm tra thay đổi trong ReactiveCrudRepository method signatures, query method parsing, Pageable/sort support, @Query parameter binding, projection/DTO mapping và custom repository fragment.

Test những method quan trọng với cả trường hợp có kết quả, không có kết quả và nhiều kết quả.

### 10.2. Mapping và conversion

Kiểm tra naming strategy, constructor/property access, @Id và generated values, embedded/value object mapping, custom converters, enum, UUID, JSON và database-specific type, nullability và primitive/wrapper handling.

Một thay đổi conversion có thể chỉ xuất hiện khi dữ liệu cụ thể được đọc/ghi; compile test không đủ.

### 10.3. Reactive transaction

Kiểm tra R2dbcTransactionManager, TransactionalOperator, @Transactional reactive method, rollback rules, cancellation behavior, isolation/propagation và connection binding vào Reactor Context.

Nếu release thay đổi Spring Framework hoặc R2DBC SPI, transaction behavior cần được kiểm tra lại ngay cả khi Spring Data API không đổi.

### 10.4. DatabaseClient và template

Kiểm tra API của DatabaseClient, R2dbcEntityTemplate, mapping converter và result handling. Những thay đổi ở parameter binding hoặc Result mapping có thể ảnh hưởng custom SQL.

Chạy integration tests trên database thật cho câu lệnh insert/update/delete, generated ID, batch và truy vấn có kiểu dữ liệu đặc thù.

## 11. Dependency management và tránh version conflict

Một ứng dụng có thể khai báo một version nhưng nhận version khác do BOM, plugin hoặc dependency bắc cầu. Khi nâng cấp, cần giữ dependency graph nhất quán.

### 11.1. Không override version của từng Spring module tùy tiện

Không nên tự ghim spring-data-r2dbc khác release train với spring-data-relational hoặc Spring Framework mà Boot quản lý.

Hãy để Boot BOM quản lý các module Spring nếu ứng dụng dùng Boot. Chỉ override khi có lý do rõ, tài liệu hỗ trợ và kiểm thử tương ứng.

### 11.2. R2DBC driver và SPI

Driver thường khai báo dependency lên r2dbc-spi. Pool cũng có thể phụ thuộc SPI. Nếu một thư viện kéo version SPI khác, dependency resolution có thể chọn một version làm driver khác không tương thích.

Dùng dependencyInsight/dependency tree để tìm đường dẫn kéo version. Đừng chữa conflict bằng cách exclude hoặc force một artifact trước khi hiểu quan hệ phụ thuộc.

### 11.3. Lockfile và reproducibility

Nếu dự án dùng Gradle dependency locking hoặc Maven dependency management, cập nhật lockfile có kiểm soát và review diff. Build local và CI cần resolve cùng một dependency graph.

Không dùng dynamic version như latest.release cho dependency production; kết quả resolve có thể thay đổi giữa hai lần build mà không có source change.

## 12. Ma trận kiểm thử sau khi đối chiếu tương thích

Khi matrix cho thấy tổ hợp target có thể dùng, cần xác minh trên ứng dụng thực tế.

| Nhóm kiểm thử | Nội dung cần xác minh |
|---|---|
| Build/runtime | JDK, plugin, packaging và startup |
| Connection | Tạo connection, authentication, TLS |
| Repository | CRUD, derived query, empty result, multiple rows |
| Mapping | UUID, JSON, enum, array, decimal, timestamp, null |
| Custom SQL | Bind parameter, bindNull, generated values, batch |
| Transaction | Commit, rollback, isolation, propagation |
| Cancellation/timeout | Cancel query, timeout, connection cleanup |
| Pool | Acquire, validation, max size, idle/lifetime, shutdown |
| Migration | Flyway/Liquibase và schema hiện có |
| Performance | Latency, throughput, pool saturation, query plan |
| Security | CVE, TLS, credential source và permission |
| Deployment | Config, health check, graceful shutdown, rollback |

### 12.1. Integration test trên database mục tiêu

Dùng Testcontainers hoặc môi trường test tương đương để chạy đúng database engine và major version. H2 hoặc mock repository không thể thay thế mọi khác biệt về dialect, type mapping, lock và transaction.

Nếu production dùng PostgreSQL với extension cụ thể, test nên bật extension đó. Nếu dùng MySQL hoặc SQL Server, test bằng đúng driver và server version được dự kiến hỗ trợ.

### 12.2. Regression test cho bug đã sửa

Nếu release notes nói sửa lỗi liên quan tới ứng dụng, tạo test tái hiện case đó. Ví dụ mapping JSON/UUID bị sai, bind null parameter không đúng, generated key không được trả về, transaction giữ connection, pool không phục hồi sau network reset, cancellation không giải phóng tài nguyên hoặc query có sort/page tạo SQL sai.

Đây là cách chứng minh nâng cấp thực sự giải quyết vấn đề cần xử lý.

## 13. Quy trình nâng cấp từng bước

### Bước 1: Chốt baseline

- Ghi JDK, Boot, Framework, Data, Reactor, SPI, driver, pool và database.
- Lưu dependency graph hiện tại.
- Chạy test suite và ghi lại lỗi có sẵn.
- Ghi các cấu hình R2DBC và migration đang dùng.

### Bước 2: Chọn target được hỗ trợ

- Chọn Spring Boot target nếu ứng dụng dùng Boot.
- Xem Boot dependency appendix.
- Xác nhận Spring Data release train tương ứng.
- Kiểm tra R2DBC SPI/driver/database compatibility.
- Xác nhận JDK và build tool baseline.
- Kiểm tra support lifecycle và security advisories.

### Bước 3: Đọc toàn bộ release notes

- Đọc từng release giữa baseline và target.
- Ghi breaking changes, deprecations, behavior changes và migration steps.
- Tìm các API/tính năng ứng dụng đang dùng.
- Đánh dấu thay đổi nào cần code change, config change hoặc test mới.

### Bước 4: Cập nhật dependency management

- Cập nhật Boot plugin/BOM hoặc Spring Data BOM theo target.
- Bỏ các version override không còn cần.
- Cập nhật driver/pool theo compatibility matrix.
- Cập nhật JDK và build wrapper nếu cần.
- Refresh lockfile có kiểm soát.

### Bước 5: Biên dịch và xử lý migration

- Compile để phát hiện API bị xóa/đổi.
- Sửa code theo migration guide.
- Cập nhật configuration/property đã đổi.
- Không kết hợp refactor không liên quan trong cùng thay đổi nếu làm khó xác định nguyên nhân.

### Bước 6: Kiểm thử

- Chạy unit tests.
- Chạy integration tests trên database mục tiêu.
- Kiểm tra transaction, type mapping, pool và migration.
- Chạy performance/regression test cho workload quan trọng.
- Kiểm tra logs/metrics và startup trên môi trường tương đương production.

### Bước 7: Triển khai có kiểm soát

- Deploy staging trước.
- Quan sát error rate, latency, connection pool và database load.
- Canary hoặc rollout theo từng nhóm instance nếu nền tảng hỗ trợ.
- Giữ phương án rollback ứng dụng và schema.
- Chỉ mở rộng rollout khi các chỉ số ổn định.

## 14. Quản lý thay đổi database schema khi nâng cấp

Nâng cấp framework/driver và thay đổi schema cùng lúc làm tăng độ khó rollback. Nếu cần thay schema, dùng chiến lược expand-migrate-contract.

1. **Expand:** thêm cột/bảng/index mới theo cách tương thích với code cũ.
2. **Migrate:** cập nhật ứng dụng để đọc/ghi cấu trúc mới, backfill dữ liệu nếu cần.
3. **Verify:** xác nhận mọi instance đã dùng cấu trúc mới.
4. **Contract:** chỉ xóa cột/bảng cũ khi không còn code version nào phụ thuộc.

Không phát hành migration phá hủy ngay trong cùng đợt nâng cấp nếu ứng dụng cần khả năng rollback về bản cũ. Database migration thường không tự rollback được chỉ bằng cách redeploy binary cũ.

### 14.1. Rollback phải xét cả ứng dụng và schema

Kế hoạch rollback cần trả lời:

- Có thể chạy binary cũ với schema mới không?
- Migration có thao tác destructive không?
- Có cần restore backup hoặc chạy forward-fix không?
- Driver mới có thay đổi dữ liệu đã ghi theo format khác không?
- Có thể chạy song song version cũ và mới trong rollout không?
- Có cần giữ compatibility trong thời gian rolling deployment?

Một rollback an toàn thường dựa vào schema backward-compatible trong giai đoạn rollout, không dựa vào việc luôn có thể downgrade database.

## 15. Ví dụ checklist compatibility matrix cho một lần nâng cấp

Trước khi chấp nhận target, có thể ghi một bảng quyết định:

| Câu hỏi | Kết quả cần có |
|---|---|
| Target Boot có hỗ trợ JDK production? | Có bằng chứng từ system requirements |
| Boot BOM quản lý Spring Framework/Data nào? | Version cụ thể từ dependency appendix |
| Spring Data train có tương thích Framework target? | Có trong compatibility matrix |
| R2DBC SPI có tương thích driver/pool? | Driver/pool docs xác nhận |
| Driver có hỗ trợ database server hiện tại? | Version range rõ ràng |
| Các release notes trung gian đã đọc? | Có danh sách và migration notes |
| API deprecated/breaking đã xử lý? | Có code change hoặc risk acceptance |
| Dependency graph không có conflict? | Có output tree/insight đã review |
| Integration tests trên DB mục tiêu pass? | Có kết quả CI |
| Transaction/pool/mapping được kiểm tra? | Có test coverage tương ứng |
| Security support còn hiệu lực? | Có trạng thái lifecycle/CVE review |
| Rollback ứng dụng/schema khả thi? | Có kế hoạch và người phụ trách |

Nếu một thành phần quan trọng có trạng thái Unknown hoặc Unsupported, chưa nên coi tổ hợp là đã được xác nhận. Hãy tìm bằng chứng, thay đổi target hoặc ghi nhận quyết định chấp nhận rủi ro theo quy trình của tổ chức.

## 16. Những lỗi thường gặp

**Chỉ đọc release notes của phiên bản đích.** Có thể bỏ lỡ deprecation và migration change ở release trung gian. Đọc toàn bộ dải phiên bản.

**Chọn từng dependency mới nhất độc lập.** Các module Spring, Reactor, SPI và driver có quan hệ tương thích. Chọn một tổ hợp được BOM/matrix hỗ trợ.

**Chỉ xem version khai báo trong build file.** Version thực tế có thể bị BOM hoặc dependency transitive thay thế. Kiểm tra resolved dependency graph.

**Ép version R2DBC SPI để xử lý conflict.** Driver hoặc pool có thể không tương thích. Tìm dependency path và dùng tổ hợp driver/SPI được hỗ trợ.

**Bỏ qua Java và build tool.** Ứng dụng có thể compile local nhưng CI/production dùng JDK không đáp ứng baseline. Kiểm tra cả build và runtime JDK.

**Bỏ qua database server version.** Driver target có thể không hỗ trợ database đang chạy. Đối chiếu vendor/driver support matrix.

**Chỉ chạy unit test.** Mock không kiểm tra protocol, type mapping, transaction hoặc pool. Chạy integration test trên database mục tiêu.

**Nâng cấp framework, driver và database cùng lúc.** Khi có lỗi, khó tìm nguyên nhân. Tách thay đổi nếu có thể.

**Không kiểm tra migration.** Binary mới có thể chạy nhưng schema production không tương thích. Test migration từ snapshot gần production.

**Không có rollback plan.** Schema destructive hoặc format dữ liệu mới có thể khiến binary cũ không chạy lại. Dùng expand-migrate-contract.

## 17. Nguyên tắc thiết kế

- Xác định resolved versions trước khi chọn target.
- Chọn tổ hợp Spring Boot, Spring Framework và Spring Data theo BOM/compatibility matrix.
- Đọc release notes và migration guide của mọi phiên bản trung gian.
- Ghi nhận JDK, Reactor, R2DBC SPI, driver, pool, database server và build tool.
- Xác minh compatibility bằng tài liệu chính thức đúng version và ngày kiểm tra.
- Phân biệt trạng thái Supported với Verified trong matrix.
- Không override Spring module hoặc R2DBC SPI tùy tiện.
- Kiểm tra type mapping, query, transaction, cancellation và pool behavior.
- Chạy integration test trên đúng database engine/major version.
- Review security advisories và support lifecycle.
- Cập nhật BOM/lockfile nhất quán và kiểm tra dependency graph sau nâng cấp.
- Tách nâng cấp framework, driver và database nếu có thể.
- Dùng expand-migrate-contract để giữ khả năng rollback schema.
- Triển khai staging/canary và theo dõi latency, errors, pool và database load.
- Lưu compatibility matrix, nguồn tài liệu và kết quả test để lần nâng cấp sau có thể đối chiếu.

## 18. Ghi nhớ

Trước khi nâng cấp Spring Data R2DBC, hãy xác định phiên bản thực tế từ dependency graph, chọn target theo Spring Boot/Spring Data compatibility matrix và kiểm tra R2DBC SPI, driver, pool, Java cùng database server. Đọc release notes của mọi phiên bản trung gian để tìm breaking changes, deprecations, behavior changes, security fixes và migration steps.

Một compatibility matrix có giá trị khi mỗi kết luận đi kèm nguồn chính thức và kết quả xác minh. Sau khi căn chỉnh BOM và dependency graph, hãy kiểm thử repository, mapping, SQL, transaction, pool, cancellation, migration và workload quan trọng trên database mục tiêu. Cuối cùng, triển khai theo từng giai đoạn với schema backward-compatible và rollback plan rõ ràng.

