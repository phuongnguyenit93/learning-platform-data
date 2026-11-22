# Kiểm thử extension trên các phiên bản Liquibase mục tiêu

## 1. Mục tiêu và bối cảnh

Liquibase có thể được mở rộng để hỗ trợ change type, precondition, database implementation, SQL generator, parser, snapshot generator hoặc cơ chế tích hợp riêng. Extension thường chạy bên trong cùng tiến trình với Liquibase core, dùng các API và cơ chế khám phá extension của chính phiên bản core đang hoạt động. Vì vậy, một extension chạy tốt trên máy phát triển chưa chắc hoạt động đúng khi được triển khai cùng phiên bản Liquibase khác, classpath khác hoặc DBMS khác.

Kiểm thử extension trên các phiên bản mục tiêu phải trả lời ba câu hỏi:

1. Extension có nạp và liên kết được với từng phiên bản Liquibase được công bố hỗ trợ không?
2. Extension có tạo ra hành vi đúng trên các DBMS, JDBC driver và Java runtime thuộc phạm vi hỗ trợ không?
3. Artifact được đóng gói và chạy trong môi trường thật có khám phá đúng extension, không xung đột dependency và không làm sai lịch sử migration không?

Một lần chạy unit test thành công chỉ chứng minh một phần. Cần kết hợp kiểm thử tương thích API, discovery, parsing/serialization, SQL generation, integration với database thật, rollback, upgrade và kiểm tra artifact đã đóng gói.

Bài thuộc chương **Mở rộng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **kiểm thử extension trên các phiên bản Liquibase mục tiêu**.

Sau bài học, bạn cần có thể:

1. Xác định ma trận phiên bản core, Java, DBMS và JDBC driver cần hỗ trợ.
2. Phân biệt tương thích source, binary, runtime behavior và SQL semantics.
3. Kiểm tra extension được phát hiện đúng qua cơ chế discovery/classloader.
4. Kiểm thử parse, serialize, validate, SQL generation, execute và rollback.
5. Chạy integration test trên từng DBMS/version nằm trong phạm vi hỗ trợ.
6. Phát hiện dependency conflict và khác biệt giữa test classpath với artifact triển khai.
7. Kiểm tra nâng cấp Liquibase core trên database đã có DATABASECHANGELOG.
8. Tự động hóa ma trận kiểm thử trong CI và công bố phạm vi hỗ trợ có bằng chứng.

## 2. Extension có thể mở rộng những phần nào?

Liquibase có nhiều điểm mở rộng. Tùy nhu cầu, extension có thể cung cấp:

| Nhóm extension | Trách nhiệm | Rủi ro cần kiểm thử |
|---|---|---|
| Custom change | Mô tả một thay đổi schema/data mới trong changelog | Parse thuộc tính, validate, sinh SQL, execute và rollback |
| Custom precondition | Kiểm tra điều kiện trước changeset | Kết quả đúng, xử lý lỗi, thông điệp và hành vi HALT/MARK_RAN |
| Database implementation | Bổ sung hoặc điều chỉnh nhận diện/capability của DBMS | Nhận diện URL/metadata, quoting, transaction và datatype |
| SQL generator | Chuyển change object thành SQL theo DBMS | Cú pháp, thứ tự statement, quoting và SQL tương đương |
| ChangeLog parser | Đọc định dạng changelog bổ sung | Parse, encoding, include và lỗi cú pháp |
| Snapshot/diff extension | Đọc metadata hoặc so sánh database object | Độ chính xác catalog, dependency và hiệu năng |
| Resource integration | Cung cấp changelog/SQL từ nguồn tài nguyên | Đường dẫn, encoding, quyền truy cập và tính bất biến |
| Command/integration extension | Kết nối workflow hoặc command riêng | Tham số, lifecycle, logging và lỗi |

Không phải extension nào cũng sử dụng cùng một SPI. Một số cơ chế dùng interface/abstract class, annotation, ServiceLocator hoặc service descriptor; cách khám phá cụ thể phụ thuộc extension point và phiên bản Liquibase.

Trước khi viết test, xác định extension đang triển khai hợp đồng nào, entry point nào được Liquibase gọi và những API nào là public extension API. Không dựa vào một class nội bộ chỉ vì nó đang tồn tại trong source của một phiên bản.

## 3. Xây dựng ma trận phiên bản hỗ trợ

Không thể tuyên bố extension tương thích với “Liquibase 4.x” mà không định nghĩa các phiên bản đã kiểm tra. Mỗi major/minor/patch có thể chứa thay đổi API, dependency, parser, SQL generation hoặc behavior.

Một ma trận tối thiểu nên có:

| Trục | Các giá trị cần xác định |
|---|---|
| Liquibase core | Phiên bản thấp nhất được hỗ trợ, phiên bản production hiện tại, phiên bản mới dự kiến nâng cấp |
| Java runtime | Các phiên bản JDK được sản phẩm hỗ trợ |
| DBMS | PostgreSQL, MySQL/MariaDB, SQL Server, Oracle hoặc DBMS thực tế của sản phẩm |
| DBMS version | Các major/minor server được hỗ trợ |
| JDBC driver | Phiên bản driver được kiểm thử với từng DBMS |
| Spring Boot | Phiên bản Boot nếu extension được nạp qua ứng dụng Spring |
| Extension dependencies | Thư viện phụ trợ và phiên bản của chúng |
| Packaging | CLI, Maven/Gradle plugin, Spring Boot JAR, container hoặc môi trường quản trị |

Ghi phiên bản cụ thể trong CI, ví dụ phiên bản Liquibase core dạng 4.x.y, JDK dạng 17/21 và server DBMS dạng 15/16. Các số này chỉ là ví dụ về cách ghi; dự án phải chọn phiên bản đúng với chính sách hỗ trợ của mình.

### 3.1. Không nhất thiết chạy toàn bộ tích Descartes

Nếu có 4 phiên bản Liquibase, 3 JDK, 4 DBMS và 3 driver, kiểm thử mọi tổ hợp có thể rất tốn kém. Hãy phân tầng:

- Chạy unit/contract tests trên mọi phiên bản core được công bố hỗ trợ.
- Chạy integration tests trên các cặp core/DBMS có rủi ro cao hoặc có khác biệt SQL.
- Chạy smoke test artifact trên từng kiểu packaging thực tế.
- Kiểm thử thêm các tổ hợp có thay đổi driver, Java hoặc DBMS.
- Chạy ma trận đầy đủ hơn trước khi công bố major release hoặc thay đổi extension point.

Pairwise testing có thể giảm số tổ hợp, nhưng không được bỏ các tổ hợp bắt buộc theo hợp đồng sản phẩm. Một DBMS có SQL generator riêng cần ít nhất một integration path cho generator đó.

### 3.2. Ghi trạng thái hỗ trợ minh bạch

Mỗi tổ hợp nên có trạng thái:

- Supported: đã kiểm thử và nằm trong cam kết hỗ trợ.
- Experimental: đã thử nhưng chưa có cam kết production.
- Unsupported: biết rõ không hỗ trợ hoặc có giới hạn.
- Not tested: chưa có bằng chứng, không được suy ra là tương thích.

Không gộp Not tested thành Supported chỉ vì extension compile được.

## 4. Các lớp tương thích cần phân biệt

### 4.1. Source compatibility

Mã nguồn extension có thể compile với API của một phiên bản Liquibase hay không? Thay đổi method signature, constructor, generic type hoặc package có thể làm compile fail.

### 4.2. Binary compatibility

JAR extension đã compile có thể load/link với Liquibase core ở runtime hay không? Một method bị đổi/xóa có thể gây NoSuchMethodError, AbstractMethodError hoặc lỗi linkage dù extension build thành công.

### 4.3. Runtime behavior compatibility

Extension có được discovery đúng và thực hiện đúng hành vi không? API vẫn có thể tồn tại nhưng thứ tự gọi, lifecycle, validation hoặc default behavior đã đổi.

### 4.4. SQL/database compatibility

SQL được sinh ra có đúng cú pháp và semantics trên DBMS/version mục tiêu không? Một SQL hợp lệ trên PostgreSQL có thể không hợp lệ trên MySQL hoặc có transaction behavior khác.

### 4.5. Data/history compatibility

Extension có làm thay đổi checksum, changeset identity, serialization hoặc lịch sử triển khai ngoài dự kiến không? Đây là lớp đặc biệt quan trọng vì database đã triển khai có thể chứa changeset được tạo bởi phiên bản extension cũ.

Một bài kiểm thử chỉ compile không chứng minh các lớp còn lại.

## 5. Chọn phiên bản core dùng để biên dịch và chạy

Extension cần khai báo rõ quan hệ dependency với liquibase-core. Chính sách compile/runtime phụ thuộc cách phân phối:

- Nếu extension được nạp vào một Liquibase CLI hoặc ứng dụng đã cung cấp core, tránh đóng gói một bản core thứ hai bên trong extension JAR.
- Dùng dependency scope phù hợp với cách host cung cấp core, chẳng hạn provided trong mô hình Maven mà host chịu trách nhiệm cung cấp runtime.
- Nếu extension là ứng dụng độc lập, dependency graph phải bảo đảm chỉ có một phiên bản core được resolve.
- Không dùng version range rộng nếu chưa kiểm thử mọi phiên bản trong range.

Ví dụ khai báo Maven với phiên bản do parent/BOM quản lý:

~~~xml
<properties>
    <liquibase.version>4.x.y</liquibase.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
        <version>4.x.y</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

Đây là cấu trúc minh họa; thay 4.x.y bằng phiên bản được chọn và xác nhận scope theo cách host nạp extension. Không copy liquibase-core vào shaded extension JAR nếu môi trường chạy đã cung cấp core.

### 5.1. Biên dịch với API thấp nhất được hỗ trợ

Nếu muốn một artifact chạy trên nhiều phiên bản core, biên dịch theo API thấp nhất mà extension cam kết hỗ trợ là một chiến lược thường dùng. Sau đó chạy binary đó trên từng runtime core mục tiêu để phát hiện lỗi linkage/behavior.

Tuy nhiên, chiến lược này chỉ phù hợp nếu các API cần dùng tồn tại và có semantics tương thích. Nếu cần API mới, có thể phải phát hành artifact riêng, dùng adapter theo phiên bản hoặc nâng mức phiên bản tối thiểu. Không che khác biệt bằng reflection tùy tiện.

### 5.2. Dependency resolution phải có bằng chứng

Trong CI, lưu dependency tree hoặc danh sách runtime classpath. Kiểm tra:

- Có nhiều phiên bản liquibase-core không?
- Extension có mang theo bản core ngoài dự kiến không?
- Có xung đột logging/Jackson/Guava hoặc thư viện phụ trợ không?
- Driver DBMS có đúng version không?
- Spring Boot dependency management có ghi đè version không?
- Class nào được load từ JAR nào?

Một lỗi chỉ xuất hiện trong production có thể đến từ classpath khác với unit test.

## 6. Kiểm thử discovery và classloader

Một extension đúng logic nhưng không được Liquibase phát hiện thì về mặt sử dụng vẫn thất bại.

Kiểm tra:

1. Class triển khai đúng interface/abstract class của extension point.
2. Annotation/metadata bắt buộc có đầy đủ nếu extension point yêu cầu.
3. Service descriptor nằm đúng vị trí nếu cơ chế dùng Java ServiceLoader.
4. Resource được đóng gói vào JAR.
5. Package scanning/ServiceLocator thấy class trong classloader thực tế.
6. Không có class trùng tên hoặc dependency xung đột.
7. Extension được phát hiện đúng một lần.
8. Không phụ thuộc thứ tự JAR ngẫu nhiên.

Với extension dùng Java ServiceLoader, kiểm tra nội dung META-INF/services/<fully-qualified-service-interface> trong JAR và thử discovery bằng classloader giống môi trường chạy. Không áp dụng quy tắc này cho extension point không dùng ServiceLoader; phải theo đúng cơ chế discovery của Liquibase ở phiên bản mục tiêu.

### 6.1. Test classpath và artifact là hai môi trường khác nhau

Maven Surefire có thể đưa target/classes và dependency vào classpath trực tiếp, trong khi production chạy extension từ một JAR riêng trong thư mục lib hoặc trong container. Cần có một smoke test sau packaging:

- Build JAR extension.
- Liệt kê nội dung archive.
- Nạp JAR cùng core đúng phiên bản.
- Chạy command hoặc test harness thật.
- Xác nhận extension xuất hiện và hoạt động.

Không chỉ test bằng IDE vì IDE có thể che lỗi thiếu resource hoặc dependency.

## 7. Kiểm thử parse và serialize changelog

Nếu extension cung cấp custom change hoặc định nghĩa thuộc tính changelog, cần kiểm tra chu trình:

1. Đọc changelog có extension.
2. Parse các thuộc tính.
3. Validate giá trị bắt buộc, kiểu và giới hạn.
4. Tạo change object đúng.
5. Serialize/deserialize nếu workflow sử dụng serialization.
6. Tạo checksum theo cơ chế Liquibase.
7. Đảm bảo thứ tự/giá trị thuộc tính không bị thay đổi ngoài dự kiến.

Ví dụ changelog minh họa một custom change:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 610-create-audit-partition
      author: platform-team
      changes:
        - createAuditPartition:
            tableName: audit_event
            partitionKey: created_at
            retentionDays: 365
~~~

Tên change type và thuộc tính trên chỉ là ví dụ do extension giả định cung cấp. Test cần bao gồm:

- Thiếu tableName.
- partitionKey không hợp lệ.
- retentionDays bằng 0 hoặc âm nếu không được phép.
- Thuộc tính không nhận diện.
- Giá trị Unicode và identifier có ký tự đặc biệt.
- Changelog format YAML/XML/JSON nếu extension tuyên bố hỗ trợ nhiều format.
- File include và changelog gốc có encoding đúng.

Nếu extension chỉ hỗ trợ YAML, phải ghi rõ. Không tuyên bố hỗ trợ mọi format chỉ vì Liquibase core hỗ trợ chúng.

## 8. Kiểm thử validate và thông báo lỗi

Extension cần thất bại sớm với lỗi có thể hành động được. Kiểm tra:

- Giá trị bắt buộc được kiểm tra trước khi sinh SQL.
- Kiểu dữ liệu và phạm vi giá trị được xác thực.
- DBMS không hỗ trợ được báo rõ.
- Thiếu dependency hoặc resource được chỉ ra.
- Thông báo không làm lộ secret hoặc dữ liệu nhạy cảm.
- Lỗi parse và lỗi execute được phân biệt.
- Preconditions không biến lỗi kỹ thuật thành kết quả thành công giả.

Nếu custom precondition được triển khai, kiểm thử cả các kết quả pass/fail/error và cách Liquibase áp dụng onFail/onError. Không để exception bị nuốt rồi trả pass.

## 9. Kiểm thử SQL generation theo DBMS

Nếu extension sinh SQL, phải kiểm tra SQL cho từng DBMS/version được hỗ trợ. Cùng một change object có thể cần SQL khác nhau.

Ví dụ bảng test mong đợi:

| DBMS | Hành vi cần xác minh |
|---|---|
| PostgreSQL | Identifier quoting, type mapping, sequence/identity, transaction và index options |
| MySQL/MariaDB | Engine, charset/collation, implicit commit, index/constraint syntax |
| SQL Server | Schema qualification, identity, batch separator và datatype |
| Oracle | Quoting, sequence, tablespace/quota, PL/SQL delimiter và DDL commit behavior |

Test SQL generation nên kiểm tra:

- SQL statement được chọn cho đúng Database implementation.
- Identifier được quote/escape theo DBMS.
- Literal được xử lý đúng, tránh SQL injection.
- Thứ tự statement và dependency hợp lệ.
- Không sinh SQL cho DBMS không hỗ trợ.
- Delimiter và splitStatements phù hợp.
- SQL ổn định giữa các lần chạy cùng input.
- Rollback SQL đúng và có thể thực thi.

### 9.1. So sánh SQL bằng golden file có kiểm soát

Có thể lưu SQL output mong đợi cho mỗi DBMS/version. Khi output thay đổi, reviewer cần thấy diff và xác định thay đổi do extension hay do core.

Không snapshot toàn bộ output chứa timestamp, random identifier hoặc đường dẫn máy. Chuẩn hóa phần không xác định nhưng không loại bỏ khác biệt SQL có ý nghĩa.

### 9.2. Test generator selection

Nếu nhiều SQL generator có thể xử lý cùng một change, kiểm tra priority/selection theo quy tắc của Liquibase. Một generator quá rộng có thể ghi đè generator chuẩn và làm sai SQL cho DBMS khác.

Test cả trường hợp extension không hỗ trợ DBMS: kết quả nên là không hỗ trợ rõ ràng hoặc để generator phù hợp khác xử lý, tùy hợp đồng đã thiết kế.

## 10. Kiểm thử execution trên database thật

SQL output đúng về mặt chuỗi chưa chắc chạy thành công. Integration test cần dùng database thực tế hoặc container cùng DBMS/version mục tiêu.

Kiểm thử nên xác minh:

- Extension được nạp trong runtime thật.
- Liquibase parse và validate changelog.
- Update tạo object và dữ liệu đúng.
- DATABASECHANGELOG ghi nhận changeset.
- Chạy update lần hai không áp dụng lại changeset đã hoàn tất.
- Rollback thực hiện đúng nếu extension cung cấp rollback.
- Precondition và transaction behavior đúng.
- Permission error được trả về rõ.
- DATABASECHANGELOGLOCK được giải phóng sau thành công/lỗi bình thường.

Với DBMS không thể chạy trong container nội bộ, dùng môi trường test do nhà cung cấp hoặc nhóm DBA quản lý. Ghi rõ đây là test environment nào và phiên bản server thực tế.

## 11. Kiểm thử rollback và failure injection

Extension có thể sinh SQL đúng khi thành công nhưng rollback sai hoặc để lại object dở dang khi thất bại.

Tạo các tình huống:

1. Thực thi change thành công rồi rollback.
2. Làm câu lệnh thứ hai trong change nhiều bước thất bại.
3. Hủy job khi DBMS đang chạy câu lệnh.
4. Mất kết nối giữa execute và ghi lịch sử.
5. Chạy trên database có object cùng tên nhưng định nghĩa khác.
6. Chạy với permission thiếu.
7. Chạy trên DBMS/version không hỗ trợ tính năng.
8. Chạy lại sau khi đã reconcile trạng thái dở dang.

Sau mỗi tình huống, kiểm tra schema/data và DATABASECHANGELOG. Đặc biệt với DDL implicit commit hoặc runInTransaction=false, không giả định rollback của Liquibase có thể hoàn tác phần SQL đã commit.

Nếu extension không thể rollback một loại thay đổi, phải khai báo rõ và cung cấp hướng dẫn forward fix hoặc cleanup.

## 12. Kiểm thử checksum và tính ổn định lịch sử

Custom change có thể ảnh hưởng checksum qua thuộc tính, serialization hoặc cách Liquibase biểu diễn change object. Một thay đổi extension vô tình làm thay đổi checksum của changeset đã triển khai có thể khiến các môi trường báo checksum mismatch.

Kiểm tra:

- Cùng changelog và cùng extension version tạo checksum ổn định trong cùng điều kiện.
- Nâng core trong phạm vi hỗ trợ không làm thay đổi checksum ngoài dự kiến.
- Nâng extension không thay đổi cách serialize thuộc tính lịch sử.
- runOnChange/validCheckSum được sử dụng có chủ đích.
- Changeset đã triển khai không cần chỉnh sửa để tương thích extension mới.
- Test upgrade dùng DATABASECHANGELOG được tạo từ phiên bản trước.

Không cố định checksum bằng cách hardcode một giá trị hoặc dùng clear-checksums để làm xanh pipeline. Nếu thay đổi behavior checksum là chủ đích, cần có migration note và quy trình nâng cấp được review.

## 13. Kiểm thử snapshot, diff và metadata

Nếu extension bổ sung Database hoặc SnapshotGenerator, test phải xác minh catalog được đọc đúng:

- Object được nhận diện đúng loại.
- Schema/catalog filtering chính xác.
- Owner, constraint, index và dependency được đọc đầy đủ.
- Identifier có chữ hoa/thường được xử lý đúng.
- Object không được hỗ trợ không bị phân loại sai.
- Snapshot ổn định khi database không đổi.
- Diff không tạo thay đổi giả do metadata thiếu.
- Quyền đọc catalog tối thiểu vẫn đủ cho kết quả mong muốn.

Dùng database có nhiều schema, object trùng tên ở schema khác nhau, identifier được quote và object có dependency. Một test chỉ dùng một schema đơn giản thường không phát hiện lỗi scope.

## 14. Kiểm thử ResourceAccessor và file phụ thuộc

Nếu extension cung cấp hoặc tùy biến ResourceAccessor, cần kiểm tra:

- Master changelog được tìm đúng.
- Include/includeAll được resolve nhất quán.
- SQL file được đọc từ đúng bundle.
- UTF-8 và newline được xử lý ổn định.
- Không cho phép path traversal ra ngoài root được phép.
- Resource không thay đổi giữa validate và update.
- Lỗi resource missing có thông báo rõ.
- Cùng artifact hoạt động trong IDE, CLI, JAR và container theo phạm vi hỗ trợ.

Với filesystem hoặc object storage, dùng một bundle có version/digest cố định. Không đọc một đường dẫn có thể bị ghi đè giữa lúc validate và update.

## 15. Kiểm thử Java runtime và dependency phụ trợ

Extension có thể phụ thuộc thư viện Java ngoài Liquibase core. Một phiên bản dependency mới có thể yêu cầu JDK cao hơn hoặc kéo theo class conflict.

Kiểm tra:

- Bytecode target và Java runtime tối thiểu.
- API Java được sử dụng có tồn tại trên runtime.
- Dependency transitive không thay thế version mà host yêu cầu.
- Không đóng gói class trùng với Liquibase core.
- Logging binding không tạo nhiều provider ngoài dự kiến.
- Reflection/module access không bị chặn trên JDK mục tiêu.
- Không dùng API nội bộ của JDK hoặc Liquibase core mà không có lý do.

Nếu hỗ trợ nhiều JDK, chạy test trên từng runtime chứ không chỉ compile với một JDK rồi suy ra tương thích.

## 16. Kiểm thử nâng cấp Liquibase core trên database đã tồn tại

Đây là một trong những bài test quan trọng nhất. Extension thường được sử dụng trên database đã có lịch sử changeset, không chỉ database mới.

Một kịch bản upgrade:

1. Dùng Liquibase core phiên bản cũ cùng extension version cũ để tạo schema test.
2. Chạy một tập changeset đại diện.
3. Lưu DATABASECHANGELOG, checksum và snapshot schema.
4. Nâng Liquibase core lên phiên bản mục tiêu.
5. Dùng extension artifact tương thích với phiên bản mới.
6. Chạy validate và status.
7. Xác nhận changeset cũ không bị chạy lại hoặc checksum thay đổi ngoài dự kiến.
8. Chạy changeset mới.
9. Kiểm tra schema/data/history.
10. Chạy rollback nếu release có hỗ trợ.
11. So sánh kết quả với baseline và ghi nhận khác biệt.

Không chỉ test database mới trên core mới. Một extension có thể chạy được từ đầu nhưng thất bại khi đọc changeset hoặc history đã tạo bởi phiên bản cũ.

### 16.1. Nâng core và nâng extension riêng biệt

Nếu có thể, tách hai biến:

- Nâng core nhưng giữ extension version tương thích.
- Nâng extension nhưng giữ core.
- Sau đó mới kiểm thử nâng đồng thời cả hai.

Cách này giúp xác định nguyên nhân khi checksum, parser hoặc SQL behavior thay đổi. Nếu extension yêu cầu nâng core đồng thời, ghi rõ coupling đó trong release note và compatibility matrix.

## 17. Kiểm thử trong Spring Boot và CLI

Extension có thể chạy khác nhau giữa Liquibase CLI và Spring Boot do classloader, dependency management và cấu hình.

### 17.1. CLI

Xác minh extension JAR được đặt trong classpath mà CLI sử dụng, đúng core version được CLI nạp và không có bản core thứ hai. Chạy validate/status/update-sql trên một database test trước khi update thật.

### 17.2. Spring Boot

Xác minh:

- Extension nằm trong runtime classpath của ứng dụng.
- Spring Boot dependency management resolve đúng Liquibase core.
- Không có hai phiên bản core trong executable JAR.
- Auto-configuration chỉ tạo một Liquibase instance theo thiết kế.
- Extension được phát hiện khi chạy executable JAR/container, không chỉ trong test.
- Contexts, labels, parameters và DataSource đúng như cấu hình release.

Nếu extension chỉ hỗ trợ CLI, ghi rõ và test để bảo đảm người dùng không nhầm rằng chỉ thêm dependency vào Spring Boot là đủ.

## 18. Kiểm thử bảo mật và đầu vào không tin cậy

Extension chạy với quyền database mà Liquibase được cấp. Nếu extension nhận tham số changelog hoặc đọc file bên ngoài, cần coi đầu vào là dữ liệu không tin cậy.

Kiểm tra:

- Không ghép identifier/SQL từ input tùy ý.
- Validate allowlist cho DBMS, schema, table và option.
- Không log password, token hoặc dữ liệu nhạy cảm.
- ResourceAccessor không cho path traversal.
- Không tải code/plugin tùy ý từ network lúc migration.
- Không thực thi script ngoài bundle đã phê duyệt.
- Không mở quyền database rộng hơn cần thiết.
- Exception không tiết lộ secret hoặc connection string.
- Dependency được scan và pin version.

Một extension có quyền DDL có thể tác động toàn bộ schema. Chỉ cho phép artifact đã review và ký/xác minh theo quy trình cung cấp phần mềm của tổ chức.

## 19. Kiểm thử hiệu năng và tải

Extension có thể hoạt động đúng trên database nhỏ nhưng gây tải lớn trên production.

Kiểm tra:

- Thời gian parse changelog lớn.
- Số lần truy vấn catalog.
- Memory allocation và resource cleanup.
- Thời gian SQL generation.
- Batch size và số hàng backfill.
- Lock duration và statement timeout.
- Replication lag/WAL/binlog generation.
- Số connection khi chạy nhiều tenant.
- Hiệu năng snapshot/diff trên schema lớn.

Không chạy benchmark bằng dữ liệu production nhạy cảm nếu không có kiểm soát. Dùng dataset đại diện và ghi rõ kích thước, DBMS/version, phần cứng và cấu hình.

## 20. Xây dựng test harness tái lập

Một test harness tốt cần cố định:

- Phiên bản Liquibase core.
- Phiên bản extension.
- Java runtime.
- JDBC driver.
- DBMS image/server version.
- Changelog fixture.
- Contexts/labels/parameters.
- Database user và grants.
- Locale/timezone nếu ảnh hưởng output.
- Encoding và line endings.
- Artifact digest.

Mỗi lần chạy nên tạo database/schema cô lập, thực thi test, thu thập logs/history/schema assertions rồi xóa môi trường theo lifecycle test. Không để test phụ thuộc trạng thái database từ lần chạy trước.

### 20.1. Bộ fixture changelog

Nên có các fixture riêng:

- Changelog tối thiểu chỉ dùng extension point.
- Changelog có include và SQL file.
- Changelog với giá trị biên/Unicode/identifier quote.
- Changelog chạy trên DBMS được hỗ trợ.
- Changelog có precondition fail.
- Changelog có rollback.
- Changelog mô phỏng thay đổi từ extension version cũ.
- Changelog có lỗi giữa chừng để kiểm tra recovery.

Không dùng một fixture quá lớn cho mọi test; fixture nhỏ giúp khoanh vùng nguyên nhân.

## 21. Ví dụ ma trận kiểm thử CI

Một ma trận đơn giản có thể được biểu diễn như sau:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    liquibase-core:
      - "4.x.y"
      - "4.a.b"
    java:
      - "17"
      - "21"
    dbms:
      - "postgresql"
      - "mysql"
~~~

Các version trong ví dụ là placeholder; thay bằng phiên bản mục tiêu đã được phê duyệt. Trong pipeline thật, mỗi job phải resolve chính xác core version, JDK và DBMS image/driver tương ứng. Không chỉ đổi biến hiển thị trong job mà vẫn dùng dependency được cache từ phiên bản khác.

Một pipeline có thể chia thành stages:

1. Compile extension với API baseline.
2. Unit/contract test.
3. Discovery/packaging smoke test.
4. Runtime compatibility test theo core matrix.
5. Integration test theo DBMS matrix.
6. Upgrade test từ history cũ.
7. Security/dependency scan.
8. Publish artifact và compatibility report.

### 21.1. Quản lý thời gian CI

Không nhất thiết mọi pull request đều chạy full matrix. Có thể:

- Pull request: compile, unit, contract và một integration DBMS chính.
- Main branch: full core matrix và DBMS matrix.
- Release candidate: full matrix, upgrade/rollback và packaging test.
- Scheduled job: kiểm tra các patch version mới trong phạm vi dự kiến.
- Trước khi mở rộng support: chạy toàn bộ tổ hợp bắt buộc.

Chính sách này phải được ghi trong repository/CI để trạng thái Supported luôn có bằng chứng mới.

## 22. Phân tích lỗi theo lớp

| Triệu chứng | Lớp có thể lỗi | Cách điều tra |
|---|---|---|
| Compile fail sau khi nâng core | Source compatibility | So sánh API signature và changelog release |
| NoSuchMethodError | Binary compatibility/classpath | Kiểm tra core JAR thực tế và dependency tree |
| Extension không xuất hiện | Discovery/classloader | Kiểm tra service descriptor, annotation và packaging |
| Parse custom change thất bại | Parser/serialization | Kiểm tra format, thuộc tính và version |
| SQL khác giữa hai core | Runtime behavior/SQL generator | So sánh generated SQL và generator selection |
| SQL chạy trên PostgreSQL nhưng lỗi MySQL | DBMS semantics | Kiểm tra generator, driver và server version |
| Checksum mismatch sau upgrade | History/serialization | So sánh artifact cũ, extension/core version và changeset |
| Rollback để lại object | Transaction/rollback behavior | Kiểm tra DDL semantics và trạng thái catalog |
| Chỉ lỗi trong Spring Boot JAR | Packaging/classloader | Kiểm tra nested JAR và runtime dependency |
| Test pass nhưng production fail | Environment/configuration | So sánh Java, DBMS, driver, grants và artifact |
| Snapshot/diff báo thay đổi giả | Metadata model | Kiểm tra catalog visibility và normalization |
| Resource không tìm thấy trong container | ResourceAccessor/packaging | Kiểm tra path, case sensitivity và bundle |

Ghi nhận lỗi theo lớp giúp không chữa một lỗi classpath bằng cách sửa SQL hoặc chữa checksum mismatch bằng clear-checksums.

## 23. Quản lý thay đổi API và phát hành extension

Khi nâng Liquibase core, hãy đọc release notes và API/Javadoc của phiên bản mục tiêu, tập trung vào extension point mà dự án sử dụng. Với mỗi thay đổi:

- Xác định API public bị thêm, deprecated, đổi hoặc xóa.
- Kiểm tra compile warnings.
- Xác định behavior thay đổi dù signature không đổi.
- Cập nhật adapter nếu cần.
- Giữ test tương thích cho các phiên bản vẫn hỗ trợ.
- Quyết định versioning extension và thời điểm ngừng hỗ trợ core cũ.
- Viết migration note nếu cấu hình hoặc changelog cần thay đổi.

Không phụ thuộc package internal hoặc reflection vào field/method private nếu có public API phù hợp. Nếu bắt buộc phải dùng internal API, cô lập trong adapter nhỏ, khóa phiên bản và công bố giới hạn hỗ trợ rõ ràng.

### 23.1. Versioning extension

SemVer có thể là quy ước hữu ích:

- Patch: sửa lỗi không thay đổi hợp đồng đã công bố.
- Minor: thêm tính năng tương thích ngược.
- Major: thay đổi hợp đồng, cấu hình hoặc yêu cầu core tối thiểu.

Nếu extension chỉ chạy với một dải Liquibase cụ thể, nêu rõ trong release metadata và tài liệu. Không dùng số version extension để suy ra version core tương thích nếu chưa có ma trận.

### 23.2. Deprecation và loại bỏ hỗ trợ

Khi ngừng hỗ trợ một phiên bản core:

1. Thông báo phiên bản cuối cùng còn hỗ trợ.
2. Cung cấp thời gian chuyển tiếp.
3. Kiểm tra số môi trường còn dùng phiên bản cũ nếu có dữ liệu.
4. Chạy ma trận còn lại và loại job đã hết hỗ trợ.
5. Ghi rõ thay đổi trong release note.

Không xóa một phiên bản khỏi CI mà không cập nhật cam kết hỗ trợ; nếu vẫn tuyên bố hỗ trợ thì cần tiếp tục có test.

## 24. Checklist trước khi công bố extension

- [ ] Đã định nghĩa phiên bản Liquibase core tối thiểu và tối đa hỗ trợ.
- [ ] Đã xác định JDK, DBMS và JDBC driver mục tiêu.
- [ ] Dependency graph không chứa core trùng hoặc version ngoài dự kiến.
- [ ] Extension được phát hiện trong classpath/package thực tế.
- [ ] Parse, validate, serialization và checksum được kiểm thử.
- [ ] SQL generation được kiểm tra cho từng DBMS hỗ trợ.
- [ ] Integration update và rollback chạy trên database thật/container phù hợp.
- [ ] Failure injection và trạng thái DDL không transactional được kiểm tra.
- [ ] Upgrade test dùng DATABASECHANGELOG tạo từ phiên bản cũ.
- [ ] CLI và Spring Boot được kiểm thử theo phạm vi công bố.
- [ ] ResourceAccessor/include/SQL file hoạt động trong JAR/container.
- [ ] Security, permission và dependency scan đạt.
- [ ] Có performance test phù hợp với quy mô sử dụng.
- [ ] CI matrix có kết quả cho mọi tổ hợp bắt buộc.
- [ ] Release note ghi rõ version range, DBMS, giới hạn và breaking changes.
- [ ] Artifact cuối cùng có digest và nguồn build truy vết được.

## 25. Kết luận

Kiểm thử extension trên các phiên bản Liquibase mục tiêu cần bao phủ cả tương thích source/binary, discovery, runtime behavior, SQL semantics và lịch sử database. Ma trận hỗ trợ phải nêu rõ phiên bản core, Java, DBMS và JDBC driver; mỗi tổ hợp được công bố Supported cần có bằng chứng phù hợp.

Một bộ kiểm thử vững chắc kết hợp unit/contract, parse/serialize, SQL generation, integration trên DBMS thật, rollback/failure injection, checksum/history upgrade và smoke test artifact đóng gói. Đặc biệt, hãy nâng core trên database đã có DATABASECHANGELOG để phát hiện sai lệch mà test database sạch không thể cho thấy.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, extension chỉ nên được phát hành khi artifact, dependency và phạm vi hỗ trợ có thể tái lập; migration giữ đúng changeset/checksum/history; SQL hoạt động trên DBMS mục tiêu; và CI lưu được kết quả ma trận. Cách kiểm thử này giúp extension tiếp tục hoạt động đáng tin cậy khi Liquibase, Java, driver và database được nâng cấp.

