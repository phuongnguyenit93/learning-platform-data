# Tích hợp Liquibase bằng API Java khi có nhu cầu đặc thù

## 1. Khi nào nên gọi Liquibase bằng Java API?

Trong ứng dụng Java, Liquibase thường được khởi chạy qua CLI, plugin build, job CI/CD hoặc auto-configuration của Spring Boot. Những cách này phù hợp với phần lớn quy trình migration vì chúng tách việc thay đổi database khỏi logic nghiệp vụ và có cấu hình triển khai dễ kiểm soát.

Có những trường hợp cần tích hợp trực tiếp bằng Java API: một nền tảng quản lý nhiều database tenant cần chọn database đích theo cấu hình đã xác thực; một công cụ provisioning cần tạo schema ngay sau khi cấp database; một ứng dụng quản trị cần chạy validate/status/update theo một workflow riêng; hoặc một hệ thống cần ResourceAccessor, parameter và callback được điều khiển bằng code.

API Java cho phép chương trình tạo đối tượng Database, kết nối Liquibase với changelog, thiết lập contexts/labels/parameters và gọi các thao tác như validate, update hoặc rollback. API không loại bỏ các nguyên tắc của Liquibase: changeset vẫn có định danh, checksum, precondition, lịch sử DATABASECHANGELOG và khóa DATABASECHANGELOGLOCK; transaction và DDL vẫn tuân theo hành vi của DBMS.

Bài thuộc chương **Mở rộng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **tích hợp Liquibase bằng API Java khi có nhu cầu đặc thù**.

Sau bài học, bạn cần có thể:

1. Nhận diện trường hợp thực sự cần API Java và trường hợp nên dùng CLI/CI/CD hoặc Spring Boot auto-configuration.
2. Tạo Database từ JDBC Connection và để Liquibase nhận diện DBMS.
3. Chọn ResourceAccessor phù hợp với classpath, filesystem hoặc nguồn tài nguyên tùy chỉnh.
4. Gọi validate, update và rollback với contexts/labels phù hợp.
5. Truyền changelog parameters an toàn.
6. Quản lý vòng đời connection, database, Liquibase và exception.
7. Tránh chạy migration trùng giữa API Java, Spring Boot và pipeline.
8. Kiểm thử API trên DBMS thật, kiểm tra history, lock và kết quả schema.

## 2. Các trường hợp sử dụng phù hợp

API Java có ích khi logic điều phối cần nằm trong một chương trình Java có kiểm soát:

- **Provisioning database:** sau khi nền tảng tạo database/tenant mới, một service bootstrap schema ban đầu.
- **Multi-tenant có database riêng:** một orchestrator duyệt qua danh sách tenant đã được cấp quyền và chạy migration theo từng database.
- **Công cụ quản trị nội bộ:** cung cấp thao tác validate, xem changeset pending hoặc chạy migration theo quy trình phê duyệt.
- **Nguồn changelog tùy chỉnh:** changelog được đóng gói trong bundle, classloader riêng hoặc một ResourceAccessor đã được kiểm soát.
- **Tích hợp ứng dụng đặc thù:** chương trình cần truyền parameter hoặc chọn contexts/labels dựa trên cấu hình đã xác thực.
- **Kiểm thử/diagnostic:** test harness khởi tạo database, áp dụng changelog và xác minh schema.

Không nên gọi API chỉ để thay một lệnh update đơn giản trong pipeline. Nếu CLI hoặc job migration đã đáp ứng yêu cầu, dùng Java API sẽ làm tăng trách nhiệm về connection lifecycle, exception, logging, version compatibility và quyền truy cập.

### 2.1. Không chạy migration theo từng request nghiệp vụ

Không gọi Liquibase update mỗi khi người dùng đăng nhập, tạo đơn hàng hoặc gọi một endpoint thông thường. Migration là hoạt động thay đổi cấu trúc/dữ liệu có phạm vi lớn và có thể khóa database. Hãy chạy ở thời điểm provisioning, release hoặc một workflow quản trị có điều phối.

Nếu hệ thống có hàng trăm tenant, không khởi chạy hàng trăm migration đồng thời chỉ vì API Java cho phép tạo nhiều thread. Phải có concurrency limit, timeout, retry policy và quan sát trạng thái từng tenant.

## 3. Những lớp chính trong API

Một tích hợp JDBC phổ biến sử dụng các thành phần:

| Thành phần | Vai trò |
|---|---|
| DataSource / JDBC Connection | Cung cấp kết nối tới database đích |
| JdbcConnection | Bọc JDBC Connection để Liquibase sử dụng |
| DatabaseFactory | Chọn implementation Database phù hợp DBMS |
| Database | Đại diện database và khả năng đặc thù của hệ quản trị |
| ResourceAccessor | Tìm master changelog, file include và SQL file |
| Liquibase | Điều phối changelog, changeset, history, lock và lệnh migration |
| Contexts | Chọn changeset theo context |
| LabelExpression | Chọn changeset theo label |
| ChangeLogParameter | Cung cấp giá trị thay thế placeholder trong changelog |

Tên package, constructor và overload có thể thay đổi giữa các phiên bản Liquibase. Ví dụ bên dưới minh họa API Java phổ biến của Liquibase 4.x; hãy đồng bộ phiên bản thư viện và kiểm tra Javadoc đúng phiên bản đang dùng trước khi tích hợp vào sản phẩm.

## 4. Khai báo dependency và quản lý phiên bản

Trong dự án Java, thư viện lõi thường là artifact liquibase-core. Với Spring Boot, ưu tiên dùng dependency management/BOM tương ứng với phiên bản Boot để tránh trộn một phiên bản Liquibase không tương thích với auto-configuration hoặc extension.

Ví dụ Maven tối giản:

~~~xml
<dependency>
    <groupId>org.liquibase</groupId>
    <artifactId>liquibase-core</artifactId>
</dependency>
~~~

Nếu dự án không dùng BOM hoặc dependency management, cần khai báo phiên bản đã được chọn và kiểm thử. Không sao chép một phiên bản tùy ý vào mọi dự án.

Kiểm tra thêm:

- Phiên bản Java runtime.
- Phiên bản JDBC driver.
- Phiên bản DBMS tối thiểu.
- Các Liquibase extension đang sử dụng.
- Cách đóng gói changelog và SQL resource.
- Không để hai phiên bản liquibase-core cùng xuất hiện qua dependency transitive.

Trong môi trường Spring Boot, kiểm tra dependency tree để biết phiên bản thực sự được resolve, không chỉ nhìn phiên bản khai báo trong một file build.

## 5. Luồng tích hợp JDBC cơ bản

Một quy trình Java API thường gồm:

1. Lấy JDBC Connection từ DataSource đã cấu hình cho migration.
2. Tạo JdbcConnection bọc kết nối.
3. Gọi DatabaseFactory để nhận diện DBMS và tạo Database implementation phù hợp.
4. Tạo ResourceAccessor để tìm changelog.
5. Tạo đối tượng Liquibase với đường dẫn master changelog, ResourceAccessor và Database.
6. Thiết lập parameters, contexts và labels nếu cần.
7. Gọi validate trước khi update khi workflow yêu cầu.
8. Gọi update hoặc một thao tác được phê duyệt.
9. Ghi log kết quả, đóng tài nguyên và trả trạng thái cho caller.

Sơ đồ:

~~~text
Provisioning / Release Orchestrator
              |
              v
       Chọn tenant/database
              |
              v
        DataSource lấy JDBC
              |
              v
       JdbcConnection wrapper
              |
              v
       DatabaseFactory
              |
              v
     Database implementation
              |
              +------ ResourceAccessor
              |               |
              v               v
          Liquibase <---- Master changelog
              |
       parameters / contexts / labels
              |
       validate -> update/rollback
              |
              v
 DATABASECHANGELOG + DATABASECHANGELOGLOCK
              |
              v
       Hậu kiểm schema và dữ liệu
~~~

Liquibase phải nhận đúng database đích và đúng artifact changelog. Không chọn tenant chỉ từ một chuỗi do client gửi; tenant/database mapping phải được xác thực từ cấu hình hoặc registry tin cậy.

## 6. Ví dụ gọi update bằng Java API

Ví dụ dưới đây minh họa một phương thức nhận DataSource đã được cấu hình cho migration. Đường dẫn master nằm trên classpath:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import liquibase.Contexts;
import liquibase.LabelExpression;
import liquibase.Liquibase;
import liquibase.database.Database;
import liquibase.database.DatabaseFactory;
import liquibase.database.jvm.JdbcConnection;
import liquibase.exception.LiquibaseException;
import liquibase.resource.ClassLoaderResourceAccessor;

public final class LiquibaseRunner {

    private static final String CHANGELOG =
        "db/changelog/db.changelog-master.yaml";

    private LiquibaseRunner() {
    }

    public static void update(DataSource migrationDataSource)
            throws SQLException, LiquibaseException {

        try (Connection connection = migrationDataSource.getConnection()) {
            Database database =
                DatabaseFactory.getInstance()
                    .findCorrectDatabaseImplementation(
                        new JdbcConnection(connection)
                    );

            try (Liquibase liquibase = new Liquibase(
                    CHANGELOG,
                    new ClassLoaderResourceAccessor(),
                    database)) {

                liquibase.validate();

                Contexts contexts = new Contexts("production");
                LabelExpression labels = new LabelExpression("release");

                liquibase.update(contexts, labels);
            }
        }
    }
}
~~~

Một số điểm cần hiểu:

- CHANGELOG là đường dẫn tương đối với classpath resource accessor; không thêm tiền tố src/main/resources.
- ClassLoaderResourceAccessor tìm changelog và các file con trong classpath. File SQL được tham chiếu cũng phải được đóng gói.
- DatabaseFactory nhận diện DBMS dựa trên JDBC connection và chọn implementation tương ứng.
- validate kiểm tra cấu trúc changelog và các điều kiện kiểm tra mà Liquibase hỗ trợ; nó không chứng minh mọi SQL sẽ chạy thành công hoặc có hiệu năng an toàn.
- update áp dụng changeset pending phù hợp với context/label.
- Ví dụ dùng một connection trong một lượt chạy. Không chia sẻ cùng JDBC Connection hoặc đối tượng Liquibase giữa nhiều thread.
- Liquibase đóng Database khi đóng đối tượng; khối try-with-resources bên ngoài cũng đóng Connection. JDBC close thường có thể gọi lặp, nhưng trong tích hợp thực tế hãy xác nhận quy tắc ownership và lifecycle của phiên bản đang dùng.

Nếu phiên bản Liquibase đang sử dụng có khác biệt về constructor hoặc AutoCloseable, điều chỉnh theo API/Javadoc của đúng phiên bản. Không trộn ví dụ từ nhiều major version.

## 7. DataSource và quyền kết nối

DataSource nên được cấu hình riêng cho vai trò migration nếu runtime role không có quyền DDL. Ví dụ một DataSource được tạo từ secret store hoặc cấu hình release:

~~~java
DataSource migrationDataSource = migrationDataSourceProvider
    .forEnvironment(environmentId);
~~~

Đoạn trên chỉ biểu diễn một provider nội bộ; cách tạo DataSource cụ thể phụ thuộc framework và secret manager của dự án.

Các nguyên tắc:

- URL phải trỏ tới đúng database/cluster.
- Credential chỉ được cấp cho tiến trình có quyền chạy migration.
- TLS và xác thực database phải theo chính sách nền tảng.
- Pool size nhỏ thường đủ vì migration là tác vụ điều phối, không phải traffic nghiệp vụ.
- Connection timeout và socket/query timeout phải được xác định.
- Không ghi password hoặc URL có secret ra log.
- Không dùng runtime DataSource nếu runtime principal không được phép DDL.
- Không cấp superuser chỉ để một changeset chạy được.

Trong hệ thống nhiều tenant, mỗi DataSource phải gắn với một tenant đã được xác minh. Không tạo URL từ input tùy ý hoặc cho phép caller chọn hostname/database tùy ý.

## 8. DatabaseFactory và nhận diện DBMS

Không nên tự suy luận DBMS từ URL rồi chọn implementation thủ công nếu Liquibase có thể nhận diện qua JDBC metadata.

~~~java
Database database =
    DatabaseFactory.getInstance()
        .findCorrectDatabaseImplementation(
            new JdbcConnection(connection)
        );
~~~

Database implementation giúp Liquibase xử lý khác biệt về cú pháp, kiểu dữ liệu, transaction và metadata theo DBMS.

Sau khi tạo Database, có thể ghi log thông tin không nhạy cảm như tên DBMS và phiên bản để phục vụ kiểm toán. Trước khi chạy update, xác nhận database/catalog/schema đúng với môi trường dự kiến.

Nếu dùng custom Database implementation hoặc extension, cần đăng ký đúng cơ chế service discovery của phiên bản Liquibase và kiểm thử nó cùng JDBC driver thực tế. Không ép DBMS nhận diện sai chỉ để vượt qua một kiểm tra tương thích.

## 9. ResourceAccessor và cách tìm changelog

ResourceAccessor trừu tượng hóa cách Liquibase đọc changelog, SQL file và resource liên quan.

Một số lựa chọn thường gặp:

| ResourceAccessor | Nguồn tài nguyên | Khi phù hợp |
|---|---|---|
| ClassLoaderResourceAccessor | Classpath/classloader | Ứng dụng Java đóng gói changelog trong JAR |
| DirectoryResourceAccessor | Thư mục filesystem | Bundle migration được mount hoặc giải nén |
| CompositeResourceAccessor | Kết hợp nhiều accessor | Changelog và SQL nằm ở nhiều nguồn được quản lý |
| Accessor tùy chỉnh | Nguồn do ứng dụng cung cấp | Kho tài nguyên nội bộ hoặc bundle đã xác thực |

Ví dụ classpath:

~~~java
ResourceAccessor accessor = new ClassLoaderResourceAccessor();
~~~

Ví dụ filesystem:

~~~java
ResourceAccessor accessor =
    new DirectoryResourceAccessor(
        Path.of("/opt/orders/migrations")
    );
~~~

Constructor cụ thể của DirectoryResourceAccessor có thể khác theo phiên bản. Với filesystem, cần kiểm soát quyền đọc, version của bundle và tránh để người dùng không tin cậy sửa nội dung sau khi release được phê duyệt.

### 9.1. Đường dẫn include

Nếu master changelog nằm ở db/changelog/db.changelog-master.yaml và include file changes/001-create-table.yaml, hãy dùng relativeToChangelogFile phù hợp để đường dẫn được tính từ changelog chứa include.

Không ghép thủ công prefix nhiều lần. Một lỗi phổ biến là dùng classpath root nhưng lại thêm db/changelog vào cả master path lẫn file con theo cách làm đường dẫn lặp.

### 9.2. Custom ResourceAccessor

Chỉ viết accessor tùy chỉnh khi nguồn resource thực sự đặc thù. Accessor phải:

- Trả về đúng nội dung theo path mà Liquibase yêu cầu.
- Xử lý encoding nhất quán, thường là UTF-8.
- Có quy tắc tìm resource xác định, không phụ thuộc thứ tự ngẫu nhiên.
- Không cho phép path traversal hoặc truy cập ngoài phạm vi.
- Trả về resource ổn định trong toàn bộ một lần update.
- Có kiểm thử cho include, includeAll và SQL file.
- Bảo đảm cùng một artifact không thay nội dung giữa lúc validate và update.

Nếu nội dung lấy từ object storage hoặc repository nội bộ, nên tải/resolve một bundle bất biến đã xác thực trước khi chạy migration thay vì đọc một file có thể thay đổi giữa các bước.

## 10. Truyền changelog parameters

Liquibase cho phép truyền parameter để thay thế placeholder trong changelog. Với Java API, có thể thiết lập parameter trên đối tượng Liquibase trước khi validate/update.

Ví dụ changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 501-create-tenant-table
      author: platform-team
      changes:
        - createTable:
            schemaName: \${appSchema}
            tableName: tenant_note
            columns:
              - column:
                  name: note_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ví dụ Java:

~~~java
liquibase.setChangeLogParameter("appSchema", "app");
liquibase.validate();
liquibase.update(new Contexts("production"), new LabelExpression());
~~~

Tên method và kiểu parameter phải được xác minh theo phiên bản API đang dùng. Parameter phải được thiết lập trước khi Liquibase parse/validate changelog.

Parameter substitution là thay thế nội dung, không phải prepared statement. Với schema/table/role identifier:

- Chỉ chấp nhận giá trị từ allowlist.
- Kiểm tra định dạng identifier theo DBMS.
- Không lấy trực tiếp từ request hoặc header.
- Không truyền nguyên đoạn SQL từ caller.
- Review SQL được resolve trước khi chạy production.

Không dùng parameter để nhúng password/token vào changelog. Secret kết nối phải được cấp qua DataSource hoặc secret manager.

## 11. Contexts và labels

Contexts và labels giúp chọn tập changeset cần chạy theo môi trường hoặc mục đích. Java API nhận chúng qua các đối tượng Contexts và LabelExpression.

Ví dụ:

~~~java
Contexts contexts = new Contexts("production");
LabelExpression labels = new LabelExpression("release");

liquibase.update(contexts, labels);
~~~

Cần đảm bảo changeset được gắn context/label theo quy ước thống nhất. Nếu truyền filter quá hẹp, changeset schema bắt buộc có thể bị bỏ qua; nếu truyền quá rộng, dữ liệu demo hoặc thay đổi chỉ dành cho môi trường khác có thể được chọn.

Trước production:

1. Ghi rõ contexts và labels mà orchestrator sẽ truyền.
2. Kiểm tra danh sách changeset được chọn.
3. So sánh với release manifest.
4. Review SQL dự kiến.
5. Lưu lại filter cùng log của lần chạy.

Không xây dựng filter từ chuỗi tùy ý của người dùng cuối. Đây là quyết định triển khai, cần thuộc quyền của release orchestrator.

## 12. Gọi validate, update và rollback

### 12.1. validate

validate kiểm tra changelog theo các quy tắc mà Liquibase hỗ trợ, chẳng hạn cấu trúc, tham chiếu resource và checksum theo ngữ cảnh thực thi. Nó hữu ích trước update nhưng không thay thế kiểm thử trên DBMS thật.

~~~java
liquibase.validate();
~~~

### 12.2. update

update áp dụng changeset pending theo contexts/labels:

~~~java
liquibase.update(
    new Contexts("production"),
    new LabelExpression("release")
);
~~~

Lệnh này có thể thay đổi schema và dữ liệu. Chỉ gọi sau khi xác nhận database đích, artifact, quyền, filter và trạng thái release.

### 12.3. rollback

Rollback cần có chính sách rõ ràng và rollback logic đã được kiểm thử. Một số overload Java API nhận số changeset, tag hoặc thời điểm cùng contexts/labels; chữ ký chính xác phụ thuộc phiên bản.

Không nên tạo endpoint công khai cho phép caller gửi số lượng changeset hoặc tag bất kỳ để rollback production. Hãy bọc thao tác bằng workflow có phê duyệt, xác minh tag và kiểm tra dữ liệu.

Rollback không thể tự đảo ngược mọi DDL hoặc khôi phục dữ liệu đã bị xóa nếu changeset không có logic phù hợp. Khi migration đã được ứng dụng sử dụng, forward fix có thể an toàn hơn.

### 12.4. Preview SQL

Trong quy trình release, nên review SQL trước khi thực thi. Có thể dùng lệnh update-sql của Liquibase CLI với cùng artifact, DBMS, contexts, labels và parameters. Nếu cần tạo preview từ Java, sử dụng API/command phù hợp với phiên bản và output writer được hỗ trợ; không tự dựng SQL bằng cách stringify change object.

Preview phải sử dụng cùng cấu hình thực tế. Nếu contexts/parameters khác nhau giữa preview và update, kết quả review không còn đại diện.

## 13. API Java và CommandScope

Liquibase cung cấp nhiều lớp API theo thời gian phát triển:

- API đối tượng Liquibase trực tiếp thường dùng để tích hợp JDBC và thao tác changelog.
- Command API dựa trên CommandScope cung cấp cách gọi các command như validate, update, rollback và có thể phù hợp với workflow mới hoặc công cụ cần chuẩn hóa tham số command.

Không nên trộn các ví dụ CommandScope từ những phiên bản khác nhau. Tên command argument, class helper và kiểu output có thể thay đổi giữa các release. Hãy tham khảo Javadoc/reference của đúng phiên bản liquibase-core.

Khi xây dựng wrapper Java, hãy đặt việc tạo CommandScope trong một lớp adapter nhỏ, ánh xạ cấu hình từ domain model sang argument đã được xác thực và kiểm thử output/error. Không để tên command hoặc argument tùy ý từ request đi thẳng vào API.

Dù dùng API đối tượng hay CommandScope, các quy tắc database, changelog, lock, checksum và transaction vẫn phải được tuân thủ.

## 14. Quản lý connection và transaction

Connection lifecycle là phần dễ sai khi tích hợp trực tiếp.

- Không chia sẻ một JDBC Connection giữa nhiều thread.
- Không đóng connection trước khi Liquibase hoàn tất.
- Không giữ connection lâu hơn cần thiết sau migration.
- Xác định rõ Liquibase hay caller chịu trách nhiệm đóng connection.
- Không bọc update trong transaction ngoài nếu DBMS/driver và Liquibase không hỗ trợ cách lồng transaction đó.
- Không giả định mọi DDL đều rollback được.
- Dùng connection pool có giới hạn và timeout phù hợp.

Liquibase có thể quản lý transaction ở cấp changeset theo khả năng DBMS và cấu hình. Nếu ứng dụng mở transaction ngoài rồi gọi update, hành vi commit/rollback có thể không như kỳ vọng. Đặc biệt, một số DDL implicit commit hoặc không chạy trong transaction block.

Nếu cần chạy thao tác không transactional, tổ chức changeset riêng, hiểu trạng thái khi lỗi và có hậu kiểm. Không tự commit/rollback JDBC connection ở giữa khi Liquibase đang điều phối changeset.

## 15. Lock và chạy đồng thời

Liquibase dùng DATABASECHANGELOGLOCK để điều phối các lượt update cùng một lịch sử. Java API cũng đi qua cơ chế lock của Liquibase khi chạy các command phù hợp.

Điều đó không có nghĩa có thể bỏ qua concurrency control ở tầng ứng dụng:

- Không để hai thread trong cùng process chạy update cho cùng database mà không có điều phối.
- Không chạy đồng thời một job CI/CD và một Spring Boot startup migration trên cùng database.
- Multi-tenant chỉ song song giữa các database độc lập khi hạ tầng chịu được tải.
- Một tenant/database chỉ nên có một chủ sở hữu migration tại một thời điểm.
- Theo dõi thời gian chờ lock và xác định holder trước khi xử lý stale lock.

Không cập nhật DATABASECHANGELOGLOCK trực tiếp bằng SQL để ép chạy tiếp. Nếu cần giải phóng stale lock, xác minh process/session cũ đã kết thúc và dùng quy trình Liquibase được phê duyệt.

## 16. Tích hợp trong Spring Boot

Có hai hướng chính:

### 16.1. Dùng Spring Boot auto-configuration

Đây là lựa chọn đơn giản cho phần lớn ứng dụng:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Spring Boot tạo và chạy Liquibase theo vòng đời khởi động. Khi dùng cách này, không cần tự tạo LiquibaseRunner để gọi update thêm lần nữa.

### 16.2. Tự điều phối bằng Java API

Có thể tắt auto-configuration:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Sau đó một service/job riêng lấy DataSource và gọi API Java theo workflow được thiết kế. Chỉ chọn cách này nếu có nhu cầu đặc thù và đã xác định rõ ai sở hữu migration.

Không bật auto-configuration đồng thời gọi update thủ công trên cùng database lúc startup. Dù DATABASECHANGELOGLOCK có thể làm một lượt chờ, hệ thống vẫn có hai chủ thể cạnh tranh, log khó hiểu và startup kéo dài.

### 16.3. Không chạy migration trong constructor hoặc bean bất kỳ

Không đặt update trong constructor của service nghiệp vụ hoặc trong một bean được tạo lại nhiều lần. Nếu cần khởi chạy sau khi Spring context sẵn sàng, dùng một lifecycle component/job có một lần thực thi được kiểm soát, có timeout, trạng thái và logging rõ ràng.

Với production, job migration tách khỏi runtime thường dễ quản lý quyền và phê duyệt hơn.

## 17. Multi-tenant và nhiều database

Một trường hợp Java API có ích là provision database riêng cho từng tenant. Tuy nhiên, phải phân biệt:

- Tenant dùng chung một database/schema.
- Tenant dùng schema riêng trong cùng database.
- Mỗi tenant có một database riêng.
- Tenant nằm trên cluster/DBMS khác nhau.

Với database riêng, orchestrator có thể lặp qua registry tenant đã xác thực, lấy DataSource tương ứng và chạy changelog trên từng database. Mỗi database có lịch sử DATABASECHANGELOG và lock riêng.

Thiết kế cần:

1. Registry tenant là nguồn tin cậy cho database mapping.
2. Mỗi tenant có credential/role trong phạm vi của mình.
3. Có giới hạn concurrency và connection pool.
4. Ghi trạng thái theo tenant và changeset.
5. Có retry độc lập nhưng phải reconcile trạng thái từng database.
6. Không bỏ qua tenant lỗi rồi báo toàn bộ release thành công.
7. Có khả năng tiếp tục từ danh sách tenant pending.
8. Có chính sách tương thích phiên bản ứng dụng/schema trong quá trình rollout.

Không để một lỗi ở tenant A làm mất thông tin rằng tenant B, C đã thành công. Báo cáo theo từng database giúp vận hành tiếp tục có kiểm soát.

## 18. Exception handling và báo cáo kết quả

API có thể phát sinh LiquibaseException và lỗi JDBC/SQL. Không bắt mọi exception rồi chỉ log một dòng “migration failed”.

Một kết quả hữu ích nên ghi:

- Environment và database identifier không nhạy cảm.
- Tenant ID đã được xác thực nếu có.
- DBMS/version.
- Artifact/changelog version.
- Contexts/labels.
- Thời gian bắt đầu/kết thúc.
- Command đã gọi.
- Changeset cuối cùng được ghi nhận nếu xác định được.
- SQLState/vendor error code khi có.
- Correlation ID của pipeline/provisioning job.

Không ghi password, token, raw JDBC URL chứa secret hoặc dữ liệu nghiệp vụ trong exception log.

Ví dụ xử lý ở tầng gọi:

~~~java
try {
    liquibase.validate();
    liquibase.update(contexts, labels);
} catch (LiquibaseException ex) {
    logger.error(
        "Liquibase migration failed for environment {}",
        environmentId,
        ex
    );
    throw new MigrationExecutionException(
        "Database migration failed",
        ex
    );
}
~~~

MigrationExecutionException là exception nghiệp vụ minh họa do ứng dụng định nghĩa. Không nuốt lỗi rồi trả trạng thái thành công cho orchestrator.

### 18.1. Timeout không chứng minh SQL đã dừng

Nếu caller timeout hoặc process bị hủy, DBMS có thể vẫn đang xử lý câu lệnh hoặc đã commit thay đổi. Trước khi retry, kiểm tra session, DATABASECHANGELOGLOCK, DATABASECHANGELOG, schema và dữ liệu thật. Không tự động gọi update lần hai chỉ vì future/promise Java đã timeout.

## 19. Kiểm thử tích hợp API

Kiểm thử cần xác nhận cả API wiring lẫn kết quả database:

- ResourceAccessor tìm được master và file con.
- DatabaseFactory nhận diện đúng DBMS.
- Contexts/labels chọn đúng changeset.
- Parameter được resolve đúng và không thể bị injection.
- validate thành công với changelog hợp lệ.
- update tạo schema/data mong đợi.
- DATABASECHANGELOG ghi đúng ID/author/FILENAME/checksum.
- DATABASECHANGELOGLOCK được giải phóng sau lượt chạy bình thường.
- Chạy update lần hai không thực thi lại changeset đã hoàn tất.
- Lỗi SQL được trả về caller và không bị nuốt.
- Connection được đóng hoặc trả về pool đúng lifecycle.
- Runtime role không thể thực hiện DDL ngoài phạm vi.

Dùng database cùng loại với production, ví dụ Testcontainers cho PostgreSQL/MySQL, nếu migration phụ thuộc hành vi DBMS. H2 không thay thế được kiểm thử DBMS production khi có SQL đặc thù.

### 19.1. Ví dụ kiểm thử ý tưởng

~~~java
@Test
void updateCreatesExpectedTable() throws Exception {
    liquibaseRunner.update(testMigrationDataSource);

    try (Connection connection = testDataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
             "SELECT COUNT(*) FROM information_schema.tables " +
             "WHERE table_name = ?")) {

        statement.setString(1, "customer");
        try (ResultSet result = statement.executeQuery()) {
            assertTrue(result.next());
            assertEquals(1, result.getInt(1));
        }
    }
}
~~~

Truy vấn information_schema và chữ hoa/thường của identifier phụ thuộc DBMS. Đây là ví dụ minh họa; trong test thực tế nên dùng assertion hoặc query metadata phù hợp với database đang chạy.

## 20. Kiểm tra bảo mật cho API Java

Tích hợp API đưa quyền database vào process Java. Cần kiểm soát:

- Chỉ service/job được phép mới có thể gọi update.
- Caller không tự chọn JDBC URL, hostname, schema hoặc changelog path tùy ý.
- Contexts/labels được allowlist.
- Parameters được validate theo kiểu dữ liệu và identifier.
- Credential migration không được chia sẻ với runtime request handler.
- ResourceAccessor không đọc file ngoài bundle được phép.
- Changelog bundle bất biến và có thể xác thực nguồn gốc.
- Log không chứa secret.
- Audit gắn với người/phê duyệt/job/commit.
- Rollback là thao tác đặc quyền và cần phê duyệt.

Không cung cấp endpoint kiểu POST /migrate nhận path, URL và command tùy ý. Nếu cần giao diện quản trị, API ứng dụng nên nhận một release identifier đã đăng ký rồi tự resolve tới artifact và database đích được phê duyệt.

## 21. Lỗi thường gặp khi tích hợp Java API

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy master changelog | Sai resource path hoặc accessor | Kiểm tra classpath và artifact |
| Master tìm thấy nhưng include lỗi | Đường dẫn tương đối không đúng | Xác minh relativeToChangelogFile và vị trí file |
| Không nhận diện DBMS | JDBC driver/metadata hoặc Database implementation không phù hợp | Kiểm tra driver và DatabaseFactory |
| Lỗi permission khi tạo metadata | Thiếu quyền schema/bảng lịch sử | Bootstrap metadata và cấp quyền tối thiểu |
| Update bị treo chờ lock | Một lượt Liquibase khác đang giữ lock | Tìm holder và điều phối, không sửa lock trực tiếp |
| Changeset không chạy | Context/label filter loại bỏ changeset | Kiểm tra filter và danh sách pending |
| Parameter chưa được resolve | Đặt parameter quá muộn hoặc sai tên | Thiết lập trước validate/update |
| SQL file không có trong JAR | Resource chưa được đóng gói | Kiểm tra artifact đầy đủ |
| Connection bị đóng quá sớm | Caller đóng trước khi Liquibase hoàn tất | Sửa lifecycle/ownership |
| Pool cạn sau migration | Connection không được đóng hoặc tác vụ song song quá nhiều | Đóng tài nguyên và giới hạn concurrency |
| Migration chạy hai lần lúc startup | Auto-configuration và API thủ công cùng hoạt động | Chỉ định một chủ sở hữu |
| Timeout nhưng schema đã đổi | DBMS tiếp tục xử lý sau khi caller timeout | Reconcile history/schema/session trước retry |
| Checksum mismatch | Changelog đã triển khai bị sửa hoặc artifact khác | Đối chiếu artifact và tạo changeset mới |
| Rollback làm mất dữ liệu | Rollback logic không phù hợp trạng thái hiện tại | Kiểm thử rollback và đánh giá forward fix |

## 22. Quy trình triển khai Java API có kiểm soát

Một workflow phù hợp cho provisioning hoặc release:

1. Xác thực yêu cầu provisioning/release và quyền caller.
2. Resolve database đích từ registry tin cậy.
3. Resolve artifact changelog bất biến và xác minh phiên bản/checksum.
4. Lấy credential migration từ secret manager.
5. Tạo DataSource/Connection với timeout và pool giới hạn.
6. Tạo Database qua DatabaseFactory.
7. Tạo ResourceAccessor và Liquibase.
8. Thiết lập parameters, contexts và labels đã allowlist.
9. Chạy validate và kiểm tra trạng thái pending.
10. Review/ghi nhận SQL preview nếu workflow yêu cầu.
11. Chạy update dưới một chủ sở hữu migration.
12. Hậu kiểm schema, data, DATABASECHANGELOG và lock.
13. Ghi kết quả theo environment/tenant.
14. Đóng tài nguyên, trả connection về pool và thu hồi credential tạm thời.

Nếu bước update thất bại, không tự động retry vô hạn. Xác minh session, lock, history và schema/data để biết changeset đã áp dụng đến đâu. Chỉ retry sau khi trạng thái database đã rõ.

## 23. Checklist trước khi dùng API Java trong production

- [ ] Có nhu cầu đặc thù mà CLI/CI hoặc Spring Boot auto-configuration không đáp ứng gọn.
- [ ] Phiên bản liquibase-core, Java và JDBC driver được quản lý thống nhất.
- [ ] DataSource/credential chỉ trỏ tới database đã xác thực.
- [ ] DatabaseFactory nhận diện đúng DBMS.
- [ ] ResourceAccessor chỉ đọc bundle changelog được phê duyệt.
- [ ] Master/include/SQL file đều có trong artifact.
- [ ] Parameters, contexts và labels được allowlist và review.
- [ ] validate chạy trước update theo workflow.
- [ ] Chỉ có một chủ sở hữu migration cho database.
- [ ] Không chia sẻ Connection/Liquibase instance giữa các thread.
- [ ] Connection lifecycle, timeout và exception được xử lý.
- [ ] DATABASECHANGELOG/LOCK được theo dõi và không sửa trực tiếp.
- [ ] Rollback/forward fix được thiết kế và kiểm thử.
- [ ] API quản trị không cho caller truyền path/URL/SQL tùy ý.
- [ ] Log không chứa secret và có correlation/audit.
- [ ] Test trên DBMS/version production và kiểm tra update lần hai.
- [ ] Có runbook cho timeout, stale lock và migration một phần.

## 24. Kết luận

Liquibase Java API phù hợp khi một chương trình Java cần điều phối migration theo logic đặc thù như provisioning database, multi-tenant, resource accessor tùy chỉnh hoặc workflow quản trị có kiểm soát. Luồng tích hợp cốt lõi là tạo JDBC connection, nhận diện Database qua DatabaseFactory, chọn ResourceAccessor, tạo Liquibase, thiết lập parameters/contexts/labels rồi gọi validate/update/rollback theo chính sách.

API không làm thay đổi các nguyên tắc nền tảng của Liquibase. DATABASECHANGELOG vẫn là lịch sử changeset, DATABASECHANGELOGLOCK vẫn điều phối các lượt chạy, checksum vẫn ràng buộc artifact và nội dung đã triển khai, còn transaction/DDL vẫn phụ thuộc DBMS. Do đó, cần quản lý connection lifecycle, quyền migration, timeout, concurrency, exception và hậu kiểm cẩn thận.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, tích hợp Java API nên là một phần của workflow có thể kiểm chứng: artifact changelog bất biến, database đích đã xác thực, một chủ sở hữu migration, kiểm thử trên DBMS thật và báo cáo rõ trạng thái sau khi chạy. Khi các ranh giới này được giữ vững, Java API mở rộng khả năng tự động hóa mà không làm mất lịch sử, tính nhất quán và khả năng phục hồi của quy trình schema migration.

