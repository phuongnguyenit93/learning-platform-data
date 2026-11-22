# Kiểm tra thay đổi ở Spring Data Relational, Spring R2DBC và trình điều khiển

## 1. Vì sao cần kiểm tra thay đổi trước khi nâng cấp?

Một ứng dụng Spring Data R2DBC không phụ thuộc vào một thư viện duy nhất. Khi chạy một câu query, nhiều lớp phối hợp:

1. Spring Data Relational cung cấp các abstraction và mapping model dùng chung.
2. Spring Data R2DBC cung cấp repository reactive và tích hợp persistence với R2DBC.
3. Spring Framework R2DBC cung cấp ConnectionFactory integration, DatabaseClient và transaction support.
4. R2DBC SPI định nghĩa hợp đồng giữa framework và driver.
5. R2DBC driver chuyển thao tác thành giao thức cụ thể của PostgreSQL, MySQL, SQL Server hoặc hệ quản trị khác.
6. Connection pool và database server ảnh hưởng tới lifecycle, hiệu năng và hành vi lúc chạy.

Một thay đổi ở một lớp có thể ảnh hưởng các lớp còn lại. Ví dụ:

- Driver mới yêu cầu một phiên bản R2DBC SPI khác.
- Spring Framework đổi API bind hoặc transaction integration.
- Spring Data thay đổi mapping metadata hoặc cách tạo query.
- Database nâng phiên bản bổ sung reserved keyword hoặc thay đổi codec.
- Spring Boot nâng BOM khiến nhiều dependency được resolve sang phiên bản mới.

Vì vậy, trước khi nâng cấp cần biết **thành phần nào thay đổi, thay đổi thuộc loại nào, các phiên bản có tương thích không và hành vi thực tế của ứng dụng có bị ảnh hưởng không**.

Mục tiêu của việc kiểm tra không chỉ là làm cho project biên dịch được. Ứng dụng còn phải khởi động, kết nối database, map dữ liệu đúng, thực thi query chính xác, quản lý transaction và hoạt động ổn định dưới tải.

## 2. Hiểu đúng các lớp thành phần và phiên bản

Trước tiên cần xác định dependency nào thuộc lớp nào. Tên gần giống nhau không có nghĩa chúng là cùng một module.

| Thành phần | Trách nhiệm chính | Ví dụ artifact/package |
| --- | --- | --- |
| Spring Boot | Auto-configuration, starter và dependency management | `spring-boot-starter-data-r2dbc` |
| Spring Data Relational | Mapping metadata và abstraction relational dùng chung | `spring-data-relational` |
| Spring Data R2DBC | Repository reactive và tích hợp Spring Data với R2DBC | `spring-data-r2dbc` |
| Spring Framework R2DBC | DatabaseClient, transaction manager và connection integration | `spring-r2dbc` |
| R2DBC SPI | Hợp đồng ConnectionFactory, Connection, Statement, Result | `r2dbc-spi` |
| R2DBC driver | Giao tiếp với database cụ thể | `r2dbc-postgresql`, `r2dbc-mysql`, `r2dbc-mssql` |
| R2DBC pool | Quản lý pool cho ConnectionFactory | `r2dbc-pool` |
| Database server | SQL dialect, kiểu dữ liệu, protocol và hành vi server | PostgreSQL, MySQL, SQL Server |

### 2.1. Spring Data Relational và Spring Data R2DBC

Spring Data Relational chứa các thành phần relational được dùng chung trong hệ sinh thái Spring Data. Spring Data R2DBC xây dựng phần tích hợp reactive trên các abstraction đó.

Khi đọc release notes, cần phân biệt thay đổi của module relational dùng chung với thay đổi riêng của R2DBC. Một thay đổi mapping có thể ảnh hưởng nhiều module, trong khi một thay đổi về reactive repository hoặc R2DBC query execution chỉ tác động phần R2DBC.

### 2.2. Spring R2DBC thuộc Spring Framework

Spring Framework có package `org.springframework.r2dbc`. Các API ở đây gồm:

- `DatabaseClient`.
- `R2dbcEntityTemplate` integration.
- `R2dbcTransactionManager`.
- Connection lifecycle và transaction support.
- Bind marker abstraction được dùng bởi các thành phần Spring.

Khi nâng Spring Framework, cần kiểm tra các API này ngay cả khi version Spring Data không đổi trực tiếp trong source code.

### 2.3. R2DBC SPI và driver là một cặp cần kiểm tra

R2DBC SPI xác định hợp đồng mà driver triển khai. Driver cụ thể có thể yêu cầu một khoảng SPI nhất định và có những khác biệt riêng về:

- Bind marker và positional index.
- Codec và kiểu dữ liệu.
- Prepared statement.
- Generated value và result metadata.
- Cancellation, timeout và error mapping.
- SSL/TLS, authentication và protocol.

Một driver mới có thể biên dịch được nhưng vẫn thay đổi hành vi lúc chạy. Vì vậy, phải kiểm tra cả dependency compatibility lẫn database integration.

## 3. Phân biệt các loại thay đổi

Không phải mọi thay đổi trong release notes đều có mức độ rủi ro giống nhau. Có thể phân loại như sau:

| Loại thay đổi | Ý nghĩa | Ví dụ tác động |
| --- | --- | --- |
| Source/API | Thay đổi API mà code gọi trực tiếp | Method bị xóa, đổi signature hoặc chuyển package |
| Binary | Thay đổi ở mức bytecode/linkage | `NoSuchMethodError`, `NoClassDefFoundError` |
| Behavior | API vẫn chạy nhưng kết quả hoặc semantics thay đổi | Mapping, ordering hoặc transaction behavior |
| Configuration | Property, default hoặc tên cấu hình thay đổi | Pool option, initialization, SSL |
| Dependency | Phiên bản hoặc dependency bắc cầu thay đổi | R2DBC SPI được resolve khác |
| SQL/Dialect | SQL được sinh hoặc được driver diễn giải khác | Bind marker, pagination, generated key |
| Type/Codec | Cách encode/decode dữ liệu thay đổi | UUID, JSON, timestamp, array |
| Performance | Latency, allocation hoặc resource usage thay đổi | Pool acquire, fetch size, backpressure |
| Security | TLS, authentication, CVE hoặc default an toàn thay đổi | Certificate validation, protocol |

Khi review một nâng cấp, ghi nhận từng thay đổi theo nhóm này. Việc phân loại giúp chọn đúng cách xác nhận: compile test cho API, integration test cho behavior, dependency graph cho compatibility và load test cho hiệu năng.

## 4. Xác định phiên bản hiện tại trước khi đọc release notes

Không nên bắt đầu bằng việc tìm phiên bản mới nhất rồi nâng đồng loạt. Trước tiên hãy chụp lại trạng thái dependency đang chạy.

Thu thập:

- Spring Boot plugin và BOM version.
- Spring Framework version thực tế.
- Spring Data release train và version các module.
- `r2dbc-spi` version.
- R2DBC driver và pool version.
- Database server version.
- Java runtime version.
- Build tool và dependency management mechanism.

Ví dụ dependency declarations trong Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Nếu dùng Spring Boot dependency management, project thường không cần ghi version riêng cho các dependency đã được BOM quản lý.

### 4.1. Lưu lại dependency graph hiện tại

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

Để xem vì sao một artifact được chọn:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-relational \
  --configuration runtimeClasspath
```

Lặp lại với các artifact quan trọng:

```bash
./gradlew dependencyInsight --dependency spring-data-r2dbc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-r2dbc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-spi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-pool --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree
```

Có thể lọc cây dependency theo artifact:

```bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-relational
mvn dependency:tree -Dincludes=org.springframework:spring-r2dbc
mvn dependency:tree -Dincludes=io.r2dbc:r2dbc-spi
```

Lưu output làm baseline để so sánh sau nâng cấp. Không chỉ nhìn version ghi trong `build.gradle`; version thực tế là version build tool đã resolve sau khi áp dụng BOM, constraints, exclusions và dependency overrides.

### 4.2. Kiểm tra runtime classpath

Dependency có trong file build chưa chắc là dependency được dùng lúc chạy. Cần xem đúng configuration:

- `compileClasspath`: dependency dùng để biên dịch.
- `runtimeClasspath`: dependency có mặt lúc chạy.
- Test runtime configuration: dependency dùng trong integration test.

Driver và pool thường là runtime dependency. Nếu test dùng driver khác production, kết quả test có thể không phản ánh đúng hành vi production.

## 5. Hiểu vai trò của BOM và dependency management

Một BOM (Bill of Materials) cung cấp tập version đã được kiểm tra tương thích. Spring Boot BOM quản lý nhiều phiên bản Spring Framework, Spring Data và thư viện tích hợp.

Khi nâng Spring Boot, BOM có thể đồng thời thay đổi:

- Spring Framework.
- Spring Data release train.
- Micrometer.
- Reactor.
- R2DBC SPI hoặc driver được quản lý.
- Các thư viện hỗ trợ khác.

Đó là lý do nâng Spring Boot thường là một thay đổi theo cụm, không chỉ đổi một dòng version.

### 5.1. Ưu tiên version được BOM quản lý

Ví dụ:

```groovy
plugins {
    id "org.springframework.boot" version "<boot-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Placeholder `<boot-version>` phải được thay bằng phiên bản đã chọn sau khi kiểm tra compatibility. Ví dụ không cố định một version cụ thể vì project có thể dùng release train khác nhau.

Khi BOM quản lý version, tránh thêm version thủ công cho `spring-data-relational`, `spring-data-r2dbc`, `spring-r2dbc` hoặc `r2dbc-spi` nếu không có lý do và kiểm tra tương thích rõ ràng.

### 5.2. Khi cần override version

Đôi khi driver hoặc dependency cần một bản vá chưa có trong BOM. Trước khi override:

1. Xác định vì sao version do BOM quản lý chưa đáp ứng yêu cầu.
2. Kiểm tra release notes của artifact được override.
3. Kiểm tra dependency constraints của các artifact phụ thuộc.
4. Xem version SPI mà driver yêu cầu.
5. Kiểm tra các module Spring đang dùng SPI đó có tương thích không.
6. Thêm integration test chạy với driver và database mục tiêu.
7. Ghi rõ lý do override và điều kiện gỡ override.

Không override riêng `r2dbc-spi` chỉ để làm dependency resolution hết xung đột. Ép version có thể làm ứng dụng biên dịch nhưng phát sinh lỗi linkage hoặc behavior lúc chạy.

### 5.3. Spring Data release train

Spring Data phát hành theo release train, trong đó nhiều module Spring Data được căn chỉnh cùng một dòng phát hành. Khi dùng Spring Boot, hãy xem BOM của Boot đang quản lý release train nào.

Không trộn module Spring Data từ các release train khác nhau nếu không có xác nhận tương thích. Một module mới hơn có thể cần API từ module relational hoặc Spring Framework mới hơn.

## 6. Đọc release notes theo thứ tự

Khi một dependency thay đổi, nên đọc tài liệu theo thứ tự:

1. Release notes của framework/platform đang nâng.
2. Migration guide hoặc upgrade guide.
3. Changelog của module có thay đổi.
4. API documentation của các class/method liên quan.
5. Release notes của driver và R2DBC SPI.
6. Release notes của database server nếu server cũng được nâng.

Mỗi nguồn trả lời một câu hỏi khác nhau:

| Nguồn | Cần tìm |
| --- | --- |
| Spring Boot release notes | BOM, auto-configuration, property, starter và logging thay đổi |
| Spring Data release notes | Repository, mapping, conversion và query generation |
| Spring Framework release notes | DatabaseClient, transaction, connection lifecycle |
| R2DBC SPI release notes | Contract giữa framework và driver |
| Driver changelog | Codec, protocol, pooling, binding, SSL và bug fixes |
| Database release notes | SQL syntax, type, reserved keyword, authentication và server behavior |

Không chỉ tìm tiêu đề có chữ "breaking". Một thay đổi mặc định hoặc bug fix có thể ảnh hưởng hành vi dù không được đánh dấu breaking API.

### 6.1. Tìm breaking changes và deprecations

Tìm các từ khóa:

- Breaking change.
- Removed.
- Deprecated.
- Behavior change.
- Default changed.
- Migration.
- Compatibility.
- Requires.
- Minimum supported.
- Security.

Deprecated không đồng nghĩa bị xóa ngay. Tuy nhiên, nếu code đang gọi API deprecated, hãy xác định replacement được khuyến nghị và thời điểm API có thể bị loại bỏ.

### 6.2. Đọc đúng khoảng version

Nếu project nâng từ version A lên version D, hãy kiểm tra thay đổi từ A tới D. Không chỉ đọc release notes của D; thay đổi có thể xuất hiện ở B hoặc C.

Nếu release notes chia theo từng minor release, đọc tuần tự từng mốc hoặc dùng migration guide tổng hợp. Ghi lại version đầu tiên có thay đổi và version cuối cùng mà project sẽ dùng.

### 6.3. Kiểm tra issue và pull request khi release notes chưa rõ

Release notes đôi khi mô tả ngắn. Khi thay đổi có thể ảnh hưởng code:

- Tìm issue liên quan tới tên class/method hoặc behavior.
- Đọc pull request đã sửa.
- Kiểm tra test mới trong project upstream.
- Xác định thay đổi là bug fix, API design hay behavior có chủ đích.

Issue discussion có thể hữu ích nhưng không thay thế tài liệu phát hành. Quyết định nâng cấp phải dựa trên phiên bản artifact thực tế và test của ứng dụng.

## 7. Kiểm tra thay đổi ở Spring Data Relational

Spring Data Relational ảnh hưởng tới mapping model và cách framework diễn giải entity metadata. Khi nâng version, hãy chú ý các nhóm sau.

### 7.1. Mapping annotations và metadata

Kiểm tra:

- `@Table`, `@Column`, `@Id`.
- `@MappedCollection` và mapping aggregate.
- Naming strategy và cách tạo tên bảng/cột.
- Embedded/complex property mapping nếu ứng dụng sử dụng.
- Entity constructor và property access.
- Generated identifier và lifecycle của entity.

Một thay đổi mapping có thể không gây lỗi compile nhưng làm framework đọc/ghi nhầm cột, đổi tên SQL identifier hoặc thay cách hydrate entity.

### 7.2. Aggregate và collection mapping

Spring Data Relational có mô hình aggregate. Quan hệ giữa root entity và collection được lưu theo cách mapping mà framework hỗ trợ, không giống ORM quản lý lazy relationship.

Khi nâng cấp, kiểm tra:

- Collection được lưu và tải có đúng không.
- Foreign key/key column có đúng tên không.
- Thứ tự collection có được giữ nếu ứng dụng yêu cầu không.
- Insert/update/delete của child rows có thay đổi không.
- Mapping của `@MappedCollection` có giữ đúng cấu hình cũ không.

### 7.3. Custom conversions

Ứng dụng có thể dùng converter để chuyển Java type sang database type:

- UUID.
- Enum.
- JSON document.
- Value object.
- Money hoặc decimal wrapper.
- Date/time type.

Kiểm tra registration và precedence của custom converter sau nâng cấp. Một converter có thể vẫn compile nhưng không còn được chọn do thay đổi mapping configuration hoặc converter discovery.

### 7.4. Entity callbacks và auditing

Nếu ứng dụng dùng callback hoặc auditing, kiểm tra:

- Callback nào được gọi trước/sau insert/update.
- Giá trị created/modified có được cập nhật đúng không.
- Reactive callback có trả publisher đúng lifecycle không.
- Entity được persist có chứa giá trị callback cập nhật không.

Không chỉ test callback method riêng; hãy chạy thao tác repository thực tế để xác nhận callback được framework gọi trong đúng thời điểm.

### 7.5. Optimistic locking và version field

Nếu entity có version field để phát hiện concurrent update, kiểm tra:

- Giá trị version tăng đúng sau update.
- Update với version cũ có phát hiện conflict không.
- Insert ban đầu có khởi tạo version đúng không.
- Exception được ánh xạ đúng cho service layer.

Đây là behavior cần kiểm thử trên database thật, vì SQL update predicate và số hàng bị tác động phụ thuộc dialect/driver.

## 8. Kiểm tra thay đổi ở Spring Data R2DBC

Spring Data R2DBC cung cấp reactive repository và query execution integration. Khi nâng cấp, chú ý:

### 8.1. Repository API

Kiểm tra:

- `ReactiveCrudRepository` và derived query method.
- `@Query` và parameter binding.
- `@Modifying` cho query ghi nếu project dùng.
- Projection và result mapping.
- Paging/sorting API được hỗ trợ.
- Custom repository implementation.

Nếu method signature thay đổi, lỗi compile sẽ chỉ ra một phần vấn đề. Cần kiểm tra cả semantics của query derivation và cách kết quả được map.

### 8.2. Query derivation

Derived query có thể tạo SQL từ tên method. Sau nâng cấp, xác nhận:

- Tên property được phân tích đúng.
- Điều kiện nested property hoạt động như mong muốn.
- Sort order và null behavior không thay đổi ngoài dự kiến.
- Query count và SQL shape không tăng bất thường.
- Các keyword trong method name vẫn được hỗ trợ.

Không giả định mọi method name hợp lệ trong module Spring Data khác đều được hỗ trợ giống nhau ở R2DBC.

### 8.3. Custom query và bind parameter

Với `@Query`, `DatabaseClient` hoặc custom repository, kiểm tra:

- Named parameter được chuyển thành marker phù hợp.
- Thứ tự positional binding không bị đổi.
- Null được bind với kiểu thích hợp.
- Collection parameter và empty collection được xử lý đúng.
- Identifier được quote đúng theo dialect.
- Native SQL không phụ thuộc cú pháp của database khác.

### 8.4. Reactive semantics

Spring Data R2DBC làm việc với `Mono` và `Flux`. Kiểm tra:

- Publisher có lazy như mong đợi không.
- Một subscription có thực hiện query nhiều lần ngoài ý muốn không.
- Cancellation có giải phóng resource không.
- Error được propagate tới caller không.
- Backpressure có được giữ đúng không.
- Không có `subscribe()` hoặc `block()` ẩn trong custom repository.

### 8.5. Result mapping và projections

Nếu nâng cấp thay đổi mapping metadata, projection hoặc constructor binding, hãy kiểm tra:

- Alias cột trong native query.
- Constructor parameter name/type.
- Nullability.
- Numeric conversion.
- Timestamp/timezone.
- Column label và case.

## 9. Kiểm tra thay đổi ở Spring Framework R2DBC

Spring Framework cung cấp lớp kết nối trực tiếp giữa ứng dụng và R2DBC SPI. Khi nâng Framework, cần đọc release notes của phần data access và R2DBC.

### 9.1. DatabaseClient

Nếu code dùng `DatabaseClient` trực tiếp, kiểm tra:

- Builder và cách cấu hình `ConnectionFactory`.
- Named parameter expansion.
- Bind API theo tên và index.
- `bindNull` và kiểu dữ liệu.
- Row mapping và metadata.
- Fetch API, `rowsUpdated()` và result consumption.

Các thay đổi API có thể làm compile fail; thay đổi behavior có thể khiến query chạy khác mà không có lỗi biên dịch.

### 9.2. ConnectionFactory và connection lifecycle

Kiểm tra:

- Connection được acquire/release đúng không.
- Connection close có trả về pool đúng không.
- Cancellation có giải phóng resource không.
- Error path có đóng resource không.
- Connection validation hoặc lifecycle hooks có đổi không.

Các lỗi lifecycle thường xuất hiện dưới tải hoặc khi request bị cancel, nên unit test đơn lẻ chưa đủ.

### 9.3. Transaction manager

Nếu dùng `R2dbcTransactionManager` hoặc `TransactionalOperator`, kiểm tra:

- Transaction bắt đầu đúng thời điểm.
- Connection được bind vào reactive transaction context.
- Repository và DatabaseClient dùng cùng ConnectionFactory khi cần chung transaction.
- Rollback xảy ra khi publisher phát lỗi.
- Cancellation và nested transaction behavior phù hợp.
- Isolation level và timeout được áp dụng như mong đợi.

Đặc biệt kiểm tra context propagation. R2DBC transaction dựa trên reactive context; không thay bằng giả định ThreadLocal transaction kiểu JDBC.

### 9.4. Bind marker và dialect integration

Nếu dùng nhiều database, kiểm tra marker expansion và dialect. Framework có thể thay đổi cách tạo marker hoặc xử lý identifier để phù hợp driver.

Test với đúng database/driver là cách xác nhận đáng tin cậy hơn việc chỉ so sánh SQL string trong unit test.

## 10. Kiểm tra thay đổi ở R2DBC SPI

R2DBC SPI là hợp đồng giữa framework và driver. Thay đổi SPI có thể ảnh hưởng nhiều module cùng lúc.

Những khu vực cần xem:

- Interface và method của `ConnectionFactory`.
- `Connection`, `Statement`, `Batch`, `Result`.
- `Row`, `RowMetadata`, `ColumnMetadata`.
- `Readable`, `Parameter`, `Type`.
- `ValidationDepth` và validation API.
- Transaction methods và isolation level.
- Lifecycle, cancellation và reactive publisher contract.

### 10.1. Compile compatibility chưa đủ

Driver có thể biên dịch với SPI nhưng behavior vẫn thay đổi do:

- Default method hoặc contract mới.
- Kiểu dữ liệu mới.
- Metadata được trả về khác.
- Cancellation được xử lý khác.
- Error mapping thay đổi.

Đọc release notes của SPI và driver cùng lúc. Nếu driver nâng SPI transitive dependency, kiểm tra Spring Framework/Spring Data có hỗ trợ version SPI đó không.

### 10.2. Không ép một SPI version bằng dependency resolution

Nếu Gradle/Maven báo xung đột `r2dbc-spi`, không giải quyết ngay bằng force version. Trước tiên xác định:

1. Artifact nào yêu cầu SPI version nào.
2. Driver đang triển khai SPI version nào.
3. Spring Framework hỗ trợ SPI contract nào.
4. Version được BOM quản lý có phải version dự kiến không.

Sau đó chọn một bộ version đã được nhà phát hành hỗ trợ hoặc nâng cả platform theo lộ trình tương thích.

## 11. Kiểm tra thay đổi của R2DBC driver

Driver là nơi chuyển R2DBC operation thành protocol của database. Vì vậy, changelog driver có thể chứa thay đổi ảnh hưởng trực tiếp đến dữ liệu và vận hành.

### 11.1. Bind parameter và prepared statement

Kiểm tra:

- Marker native.
- Bind index và tên parameter.
- Bind null.
- Batch execution.
- Prepared statement cache.
- Kiểu dữ liệu được encode.

Một query có thể không thay đổi source code nhưng driver mới xử lý một parameter type khác trước.

### 11.2. Codec và type mapping

Đặc biệt kiểm tra các type ứng dụng đang dùng:

| Java type / dữ liệu | Điều cần xác nhận |
| --- | --- |
| UUID | Format, byte order hoặc native type |
| `Instant`, `OffsetDateTime` | Timezone và precision |
| `BigDecimal` | Precision và scale |
| Boolean | Native boolean, bit hoặc numeric representation |
| Enum | String, ordinal hay custom codec |
| JSON | String/document codec và null handling |
| Array | Element type và collection mapping |
| Binary | Byte order, length và memory behavior |

Chạy round-trip test: ghi giá trị, đọc lại và so sánh theo semantics của domain. Không chỉ kiểm tra query thành công.

### 11.3. Generated key và result metadata

Nếu driver thay đổi generated value hoặc result metadata, có thể ảnh hưởng insert repository:

- ID có được trả về không.
- Column label có đúng không.
- Numeric type có thay đổi không.
- Row metadata có giữ case không.
- `rowsUpdated` có phản ánh đúng số hàng không.

Test cả insert đơn và insert trong transaction nếu ứng dụng phụ thuộc generated ID.

### 11.4. Cancellation và timeout

Reactive request có thể bị cancel khi client ngắt kết nối hoặc timeout. Kiểm tra driver mới:

- Có cancel query đang chạy không.
- Connection có được trả về pool không.
- Server có tiếp tục thực thi query sau cancellation không.
- Timeout được ánh xạ thành exception nào.
- Connection có còn usable sau cancellation không.

Các behavior này quan trọng với query dài, stream result và endpoint có client timeout thấp.

### 11.5. TLS, authentication và protocol

Driver changelog có thể thay đổi:

- TLS protocol hoặc cipher support.
- Certificate validation.
- Authentication mechanism.
- Database protocol version.
- DNS/host resolution.
- Keepalive và socket timeout.

Không tắt certificate validation để giải quyết lỗi sau nâng cấp. Kiểm tra cấu hình trust store, certificate chain và server policy theo hướng dẫn driver.

## 12. Kiểm tra thay đổi ở connection pool

Nếu dùng `r2dbc-pool`, cần đọc changelog riêng. Pool ảnh hưởng trực tiếp tới concurrency và connection lifecycle.

Kiểm tra:

- `maxSize`, `initialSize`.
- Acquire timeout.
- Max idle time và max life time.
- Validation query hoặc validation depth.
- Background eviction.
- Pool disposal/shutdown.
- Metrics active, idle, pending acquire.

Một default mới có thể khiến ứng dụng mở nhiều connection hơn hoặc timeout sớm hơn dù code không đổi.

### 12.1. Phân biệt pool timeout và query timeout

Hai lỗi này có nguyên nhân khác:

- Acquire timeout: không lấy được connection từ pool trong thời gian cho phép.
- Query timeout: connection đã có nhưng thao tác database vượt giới hạn.

Trace và metrics nên giúp phân biệt hai khoảng thời gian. Khi nâng pool hoặc driver, test tình huống concurrency và connection exhaustion.

## 13. Đọc migration guide và xử lý deprecated API

Khi release notes báo API deprecated:

1. Tìm API trong codebase.
2. Xem lý do deprecated.
3. Đọc replacement được đề xuất.
4. Kiểm tra behavior khác nhau giữa API cũ và mới.
5. Thay đổi trong một phạm vi nhỏ.
6. Chạy test liên quan.
7. Chỉ nâng tiếp sau khi migration hoàn tất.

Không xóa cảnh báo deprecated bằng cách suppress warning nếu chưa xác định lộ trình thay thế. Warning có thể là dấu hiệu API sẽ bị loại bỏ ở major release sau.

### 13.1. Search API sử dụng trong project

Có thể tìm các class thường dùng:

```bash
rg -n "DatabaseClient|R2dbcEntityTemplate|R2dbcTransactionManager" src
rg -n "ReactiveCrudRepository|@Query|@MappedCollection" src
rg -n "ConnectionFactory|Statement\.bind|bindNull" src
```

Tìm các package cụ thể giúp xác định code nào chịu ảnh hưởng khi API thay đổi.

### 13.2. Không refactor toàn bộ persistence trong cùng một lần nâng

Nếu vừa nâng version vừa đổi repository design, query strategy và mapping model, khi test lỗi sẽ khó biết nguyên nhân đến từ đâu.

Tách nâng cấp nền tảng khỏi refactor nghiệp vụ nếu có thể. Nếu buộc phải kết hợp, ghi rõ từng thay đổi và kiểm thử riêng từng lớp.

## 14. So sánh dependency graph trước và sau

Sau khi cập nhật version/BOM, tạo lại dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

So sánh các artifact:

| Artifact | Baseline | Candidate | Cần xác nhận |
| --- | --- | --- | --- |
| `spring-data-relational` | Version hiện tại | Version sau nâng | Mapping metadata |
| `spring-data-r2dbc` | Version hiện tại | Version sau nâng | Repository/query |
| `spring-r2dbc` | Version hiện tại | Version sau nâng | DatabaseClient/transaction |
| `r2dbc-spi` | Version hiện tại | Version sau nâng | Contract driver |
| R2DBC driver | Version hiện tại | Version sau nâng | Codec/protocol |
| `r2dbc-pool` | Version hiện tại | Version sau nâng | Connection lifecycle |

Không cần giữ mọi artifact ở cùng một số version. Các project có release cadence khác nhau. Điều cần kiểm tra là compatibility matrix và dependency management được hỗ trợ.

### 14.1. Tìm version bị override

Gradle `dependencyInsight` cho biết vì sao một version được chọn, chẳng hạn:

- BOM/platform constraint.
- Version conflict resolution.
- Dependency constraint.
- Explicit version.
- Resolution rule.

Nếu version được chọn không giống version dự kiến từ BOM, tìm nguyên nhân trước khi nâng tiếp.

### 14.2. Lockfile và reproducibility

Nếu project dùng Gradle dependency locking, cập nhật lock state có chủ đích và commit cùng thay đổi dependency. Không xóa lockfile để build tool tự chọn version mới không kiểm soát.

Nếu dùng dependency verification, cập nhật checksum/signature metadata theo quy trình của project sau khi xác minh artifact nguồn.

## 15. Xây dựng compatibility matrix

Một bảng compatibility matrix giúp team biết bộ version nào đã được xác nhận.

Ví dụ cấu trúc:

| Stack | Spring Boot | Spring Data train | Framework | R2DBC SPI | Driver | Database |
| --- | --- | --- | --- | --- | --- | --- |
| Current | Version đang chạy | Train hiện tại | Version resolve | Version resolve | Version resolve | Server hiện tại |
| Candidate | Version định nâng | Train theo BOM | Version theo BOM | Version được hỗ trợ | Driver tương thích | Server mục tiêu |
| Tested | Version test pass | Train test pass | Version test pass | Version test pass | Version test pass | Server test pass |

Không điền version theo phỏng đoán. Lấy version từ dependency graph và release documentation của từng project.

### 15.1. Một số quy tắc đọc matrix

- Spring Boot BOM là điểm bắt đầu để xác định bộ version được quản lý.
- Spring Data release train cần tương thích với Spring Framework được chọn.
- Driver phải tương thích với R2DBC SPI mà dependency graph resolve.
- Database server cần được driver hỗ trợ.
- Java runtime phải đáp ứng minimum requirement của platform và driver.
- Connection pool phải tương thích với SPI và driver.

### 15.2. Nâng một chiều có kiểm soát

Nếu cần nâng nhiều lớp, hãy xác định một candidate stack rồi kiểm tra từng thành phần. Không tự kết luận driver mới nhất luôn tương thích với Spring Data mới nhất; release cadence độc lập.

## 16. Quy trình nâng cấp an toàn

Một quy trình thực tế có thể chia thành các bước:

### Bước 1: Ghi nhận baseline

- Ghi lại Java, Spring Boot, Spring Framework và Spring Data version.
- Lưu dependency graph.
- Ghi database server và driver version.
- Chạy test hiện tại để biết baseline đang pass hay đã có lỗi.
- Lưu metrics latency, pool và error rate nếu có.

### Bước 2: Xác định mục tiêu nâng cấp

Ghi rõ lý do:

- Security patch.
- Bug fix cần thiết.
- Hỗ trợ database version mới.
- Nâng Java/Spring Boot platform.
- Cần API hoặc feature mới.
- Hết thời gian hỗ trợ của version hiện tại.

Lý do nâng cấp giúp xác định phạm vi test. Security patch có thể cần ưu tiên xác minh CVE và TLS; driver major có thể cần tập trung codec và protocol.

### Bước 3: Đọc tài liệu thay đổi

Đọc release notes, migration guide và changelog cho toàn bộ version range. Tạo danh sách:

- Breaking changes.
- Deprecated APIs.
- Default changes.
- Minimum supported Java/SPI/database.
- Driver fixes.
- Security fixes.
- Known issues.

### Bước 4: Cập nhật platform/BOM

Nếu nâng Spring Boot, cập nhật plugin và BOM theo bộ version mục tiêu. Tránh override module Spring Data/Framework riêng lẻ trừ khi đã có compatibility rationale.

### Bước 5: Resolve dependency graph

Chạy dependency report và dependency insight. Xác nhận không có SPI hoặc framework version bị ép sai.

### Bước 6: Sửa compile/API

Xử lý compile error và deprecated API. Giữ thay đổi source ở phạm vi cần thiết.

### Bước 7: Chạy unit và slice tests

Kiểm tra logic mapping, converter, query builder và service behavior.

### Bước 8: Chạy integration test với driver thật

Dùng Testcontainers hoặc database test tương ứng. Xác nhận query, codec, transaction, pool, cancellation và migration.

### Bước 9: Kiểm tra hiệu năng và vận hành

So sánh latency, throughput, pool usage, error rate và resource consumption với baseline.

### Bước 10: Triển khai có kiểm soát

Dùng staging/canary hoặc rollout từng phần nếu hệ thống hỗ trợ. Theo dõi lỗi driver, SQL state, pool exhaustion và slow query.

### Bước 11: Ghi lại bộ version đã xác nhận

Cập nhật compatibility matrix, dependency lock, upgrade note và hướng rollback.

## 17. Bộ kiểm thử cần có sau nâng cấp

Không phải mọi ứng dụng cần cùng một bộ test. Chọn test dựa trên tính năng persistence mà project thực sự dùng.

| Nhóm | Trường hợp cần xác nhận |
| --- | --- |
| Startup | Application context tạo ConnectionFactory và repository |
| Connectivity | Kết nối, authentication, TLS và validation |
| CRUD | Insert, select, update, delete |
| Mapping | Table/column, constructor, naming, aggregate |
| Conversion | UUID, enum, JSON, decimal, timestamp, boolean |
| Binding | Named, positional, null và collection |
| Query | Derived query, native query, sort và pagination |
| Generated values | Identity, sequence hoặc returned key |
| Transaction | Commit, rollback, isolation và timeout |
| Concurrency | Optimistic locking và concurrent updates |
| Lifecycle | Cancellation, connection release và pool shutdown |
| Error handling | SQL state, constraint violation, timeout |
| Migration | Schema migration và compatibility với dữ liệu cũ |
| Performance | Latency, throughput, pool saturation và memory |

### 17.1. Unit test không thay integration test

Unit test có thể xác nhận converter hoặc business logic. Nhưng nó không chứng minh driver thực thi SQL đúng trên database thật.

Ví dụ:

- Mock repository không kiểm tra bind marker.
- Mock ConnectionFactory không kiểm tra codec.
- H2 không chứng minh PostgreSQL hoặc MySQL behavior giống nhau.
- Test chỉ insert không kiểm tra rollback hoặc cancellation.

Giữ unit test để chạy nhanh, đồng thời có integration test trên driver/database production sử dụng.

### 17.2. Testcontainers

Testcontainers cho phép chạy database thực tế trong test environment:

```java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    // Configure R2DBC URL and credentials from the container.
    // Run repository operations against this database.
}
```

Đoạn code là khung minh họa. Cấu hình Spring R2DBC URL phải dùng R2DBC driver tương ứng; Testcontainers container JDBC URL không tự trở thành R2DBC URL.

Nếu project hỗ trợ nhiều database, tạo test suite riêng cho mỗi driver/server được hỗ trợ chính thức.

## 18. Kiểm tra migration schema và dữ liệu hiện có

Nâng driver/framework có thể làm lộ vấn đề schema tồn tại từ trước. Trước khi deploy:

- Chạy migration từ schema version hiện tại.
- Kiểm tra reserved keyword trên server version mới.
- Kiểm tra index, constraint, generated column và sequence.
- Xác nhận kiểu dữ liệu tương thích với codec mới.
- Kiểm tra dữ liệu legacy có giá trị null hoặc format bất thường.
- Xác nhận application version cũ và mới có thể cùng chạy trong giai đoạn rollout nếu cần.

### 18.1. Expand-and-contract

Nếu nâng cấp ứng dụng đồng thời đổi schema, có thể dùng chiến lược expand-and-contract:

1. Thêm cấu trúc mới mà code cũ vẫn hoạt động.
2. Deploy code có khả năng đọc/ghi cấu trúc mới.
3. Chuyển dữ liệu hoặc bật feature flag.
4. Xác nhận mọi instance đã dùng cấu trúc mới.
5. Xóa cấu trúc cũ ở một release sau.

Điều này giảm rủi ro khi rollout không đồng thời tất cả instance.

### 18.2. Driver rollback không thay thế schema rollback

Nếu rollback ứng dụng về driver cũ, schema đã migration có thể không còn tương thích với code cũ. Cần có kế hoạch schema tương thích ngược hoặc migration bù trừ.

## 19. Kiểm tra hiệu năng sau nâng cấp

Một version mới có thể sửa bug nhưng cũng thay đổi allocation, codec, pool hoặc query execution.

So sánh cùng workload:

- Request latency p50, p95, p99.
- Query duration theo operation.
- Throughput.
- Connection acquire time.
- Active/idle/pending pool connections.
- Timeout và error rate.
- CPU, heap và garbage collection.
- Số hàng được fetch và memory footprint.

Giữ test data, concurrency, database configuration và workload gần giống baseline. Nếu thay đổi nhiều yếu tố cùng lúc, khó xác định nguyên nhân hiệu năng.

### 19.1. Tránh kết luận từ một lần chạy

Chạy benchmark nhiều lần, bỏ qua giai đoạn warm-up và xem phân phối latency. Một lần chạy nhanh hơn có thể chỉ do cache hoặc database load khác.

### 19.2. Query span và database execution plan

Nếu query span dài hơn trước:

1. Kiểm tra connection acquire latency.
2. Kiểm tra network và result consumption.
3. So sánh SQL được sinh.
4. Lấy execution plan từ database.
5. Kiểm tra index và statistics.
6. So sánh driver version và codec.

Không đổ lỗi cho driver chỉ dựa trên tổng thời gian publisher.

## 20. Security và maintenance review

Release notes có thể chứa security fixes hoặc thay đổi về TLS/authentication. Khi nâng cấp:

- Kiểm tra CVE trong dependency tree.
- Xác nhận driver không còn version bị cảnh báo.
- Kiểm tra TLS certificate validation.
- Kiểm tra authentication plugin của database.
- Kiểm tra secret rotation và credential handling.
- Kiểm tra dependency từ nguồn tin cậy.
- Cập nhật SBOM và dependency verification nếu project dùng.

Không tắt TLS validation hoặc hạ authentication policy để làm bản driver mới kết nối được. Tìm nguyên nhân thực sự trong certificate, server configuration và driver documentation.

## 21. Tự động theo dõi dependency

Các công cụ như Renovate hoặc Dependabot có thể tạo pull request khi dependency mới được phát hành.

Để review hiệu quả:

- Gom các dependency thuộc cùng platform/BOM vào một nhóm hợp lý.
- Không gom mọi driver/database vào một thay đổi không thể review.
- Yêu cầu dependency graph và release notes trong PR.
- Chạy unit và integration tests tự động.
- Chỉ auto-merge patch release có rủi ro thấp nếu chính sách dự án cho phép.
- Với minor/major, yêu cầu review compatibility và migration.

Automation phát hiện version mới, nhưng không thay thế việc kiểm tra behavior và tương thích của stack.

## 22. Ví dụ review một thay đổi version

Giả sử một pull request nâng Spring Boot từ dòng A lên dòng B và driver PostgreSQL từ dòng X lên dòng Y.

Reviewer có thể đọc theo trình tự:

### 22.1. Thay đổi dependency

```diff
- id("org.springframework.boot") version "<boot-A>"
+ id("org.springframework.boot") version "<boot-B>"
```

Driver có thể được BOM quản lý hoặc có version riêng. Nếu driver được override, PR phải nêu lý do và compatibility evidence.

### 22.2. Thay đổi resolved graph

Đính kèm phần so sánh:

```text
spring-data-relational: A -> B
spring-data-r2dbc:      A -> B
spring-r2dbc:           A -> B
r2dbc-spi:              A -> B
r2dbc-postgresql:       X -> Y
```

Các ký hiệu A/B/X/Y chỉ đại diện cho version trước/sau. Reviewer cần xem version thực tế trong dependency report.

### 22.3. Bằng chứng test

PR nên cho biết:

- Application context khởi động thành công.
- Repository CRUD pass.
- Custom query và binding pass.
- Converter round-trip pass.
- Transaction commit/rollback pass.
- Test chạy với đúng PostgreSQL driver/server version.
- Pool và latency không có regression đáng kể.

### 22.4. Kết luận có điều kiện

Một nâng cấp chỉ nên được coi là sẵn sàng khi version graph đã được hiểu, các migration bắt buộc đã thực hiện và test phản ánh được database thực tế. Compile thành công chỉ xác nhận source/API ở một mức nhất định.

## 23. Những lỗi thường gặp khi kiểm tra thay đổi

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Compile lỗi sau khi nâng | API bị đổi/xóa hoặc module không tương thích | Đọc migration guide và kiểm tra version alignment |
| `NoSuchMethodError` lúc chạy | Dependency runtime khác compile classpath hoặc binary mismatch | Kiểm tra runtime dependency graph |
| `ClassNotFoundException` | Artifact/package bị chuyển hoặc dependency bị loại | Kiểm tra dependency tree và migration guide |
| Driver không khởi tạo được | R2DBC SPI không tương thích | Kiểm tra SPI requirement của driver và BOM |
| Repository chạy nhưng map sai dữ liệu | Mapping/converter behavior thay đổi | Chạy round-trip tests trên database thật |
| Query lỗi cú pháp | Dialect hoặc bind marker thay đổi | Kiểm tra SQL được sinh và driver native syntax |
| Insert không trả generated ID | Driver/result metadata behavior khác | Kiểm tra generated values và integration test |
| Transaction không rollback | Reactive transaction context hoặc factory không đồng nhất | Kiểm tra transaction manager và publisher chain |
| Connection pool cạn | Pool defaults/lifecycle hoặc cancellation thay đổi | Kiểm tra pool metrics và stress test |
| Local pass nhưng production fail | Database server/driver khác hoặc config khác | Dùng cùng driver/server major trong integration test |
| Version bị chọn ngoài BOM | Explicit override hoặc transitive constraint | Dùng dependencyInsight và sửa nguồn override |
| Patch nâng cấp gây latency tăng | Codec, pool hoặc query behavior đổi | So sánh benchmark và trace theo operation |

## 24. Tạo báo cáo thay đổi cho mỗi lần nâng cấp

Một báo cáo ngắn nhưng có thể review nên chứa:

| Mục | Nội dung |
| --- | --- |
| Lý do | Security, bug fix, platform support hoặc feature |
| Baseline | Boot, Data, Framework, SPI, driver, pool và database |
| Target | Bộ version sau nâng |
| Release notes | Breaking changes, deprecations, defaults |
| Dependency graph | Artifact thay đổi và lý do version được chọn |
| Source changes | API migration và config changes |
| Data behavior | Mapping, codec, binding, transaction, generated values |
| Test evidence | Compile, unit, integration, migration, performance |
| Risk | Thành phần chưa được xác nhận hoặc limitation |
| Rollback | App version và schema compatibility |

Không ghi "nâng tất cả dependency lên latest" như một mô tả đủ. Reviewer cần biết version nào thay đổi và vì sao bộ version đó tương thích.

## 25. Tài liệu chính thức nên kiểm tra

Khi thực hiện một lần nâng cấp cụ thể, ưu tiên tài liệu phát hành của đúng version:

- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/) — dependency management, auto-configuration và observability.
- [Spring Boot Release Notes](https://github.com/spring-projects/spring-boot/releases) — thay đổi theo từng bản phát hành.
- [Spring Data Relational Documentation](https://docs.spring.io/spring-data/relational/reference/) — mapping, repository và relational behavior.
- [Spring Data Release Notes](https://github.com/spring-projects/spring-data-relational/releases) — thay đổi của Spring Data Relational/R2DBC.
- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html) — Spring R2DBC, DatabaseClient và transaction.
- [Spring Framework Releases](https://github.com/spring-projects/spring-framework/releases) — thay đổi API và behavior của Framework.
- [R2DBC SPI](https://r2dbc.io/spec/) — contract giữa driver và client.
- [R2DBC Drivers](https://r2dbc.io/drivers/) — driver và database được hỗ trợ.
- [R2DBC Pool](https://github.com/r2dbc/r2dbc-pool) — release và cấu hình pool.

Tài liệu online có thể hiển thị phiên bản mới nhất. Khi điều tra một dự án cụ thể, hãy mở tài liệu/release tag đúng version đang dùng và version định nâng, không áp dụng mặc định hướng dẫn của bản mới nhất cho project cũ.

## 26. Checklist trước khi chấp nhận nâng cấp

Trước khi merge một thay đổi version, xác nhận:

1. Đã ghi lại baseline và dependency graph hiện tại.
2. Đã xác định đầy đủ Spring Boot, Spring Data, Spring Framework, R2DBC SPI, driver, pool và database version.
3. Đã đọc release notes trong toàn bộ khoảng version.
4. Đã đọc migration guide và xử lý deprecated/breaking API.
5. Đã xác nhận BOM và dependency constraints.
6. Không có SPI hoặc Spring module bị override tùy tiện.
7. Runtime dependency graph đúng với version dự kiến.
8. Compile và unit test pass.
9. Integration test chạy với driver/database production sử dụng.
10. Mapping, custom converter, bind, generated values và transaction được xác nhận.
11. Pool lifecycle, timeout và cancellation được kiểm tra.
12. Schema migration tương thích với app version cũ/mới theo rollout plan.
13. Latency, throughput, pool usage và error rate không có regression ngoài ngưỡng.
14. Security/TLS/authentication được kiểm tra.
15. Có báo cáo version, test evidence và rollback plan.

## 27. Quy trình xử lý khi phát hiện regression sau nâng cấp

Nếu sau deploy xuất hiện lỗi:

1. Xác định thời điểm lỗi bắt đầu và deployment/version liên quan.
2. So sánh dependency graph đang chạy với baseline.
3. Phân loại lỗi: API/linkage, mapping, driver, SQL, transaction, pool hay database server.
4. Dùng trace/log để tìm operation đầu tiên bị ảnh hưởng.
5. Kiểm tra release notes và issue liên quan.
6. Tái hiện bằng integration test tối thiểu với đúng driver/database.
7. Xác định có cần rollback ứng dụng, driver hoặc database migration không.
8. Nếu rollback, kiểm tra schema hiện tại còn tương thích app cũ không.
9. Tạo test regression trước khi phát hành bản sửa.
10. Cập nhật compatibility matrix và upgrade notes sau khi khắc phục.

Không force một dependency version trong production chỉ để hết lỗi trước mắt khi chưa hiểu contract bị vi phạm. Một bản rollback có kiểm soát thường an toàn hơn một tổ hợp dependency không được xác nhận.

## 28. Kết luận

Kiểm tra thay đổi ở Spring Data Relational, Spring R2DBC và driver là công việc theo dõi tương thích xuyên nhiều lớp. Hãy bắt đầu từ dependency graph thực tế, dùng BOM và release train để xác định bộ version, đọc migration guide trong toàn bộ khoảng nâng cấp, rồi kiểm tra API, mapping, binding, codec, transaction, pool và protocol. Compile test chỉ là bước đầu; integration test với đúng R2DBC driver và database server mới xác nhận được hành vi persistence. Mỗi lần nâng cấp nên có compatibility matrix, bằng chứng kiểm thử, ghi nhận rủi ro và kế hoạch rollback rõ ràng.
