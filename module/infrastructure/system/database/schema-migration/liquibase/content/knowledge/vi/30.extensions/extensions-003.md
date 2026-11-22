# Viết custom precondition và xử lý lỗi

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Mở rộng**, precondition giúp Liquibase xác minh điều kiện trước khi thực thi changeset. Các precondition dựng sẵn như tableExists, columnExists, dbms, runningAs và sqlCheck đáp ứng phần lớn nhu cầu. Tuy nhiên, có những quy tắc phụ thuộc nghiệp vụ hoặc cấu trúc riêng của hệ thống mà các điều kiện chuẩn không biểu diễn rõ được. Khi đó có thể viết **custom precondition** bằng Java và đóng gói nó cùng Liquibase extension hoặc runtime.

Custom precondition phải trả lời một câu hỏi cụ thể về trạng thái hiện tại của database, chẳng hạn: một bảng cấu hình đã có bản ghi marker của đợt chuyển đổi dữ liệu hay chưa; một schema đã đạt phiên bản tối thiểu; hoặc một tập điều kiện metadata đặc thù có thỏa mãn hay không. Kết quả cần phân biệt rõ hai tình huống: **điều kiện được kiểm tra nhưng không thỏa mãn** và **không thể thực hiện việc kiểm tra**. Tình huống thứ nhất là precondition failure; tình huống thứ hai là precondition error. Phân biệt đúng giúp nhóm chọn cách dừng, bỏ qua hoặc cảnh báo phù hợp, tránh để migration chạy trên database chưa sẵn sàng.

Bài học này trình bày khi nào nên dùng custom precondition, API Java, cách truyền tham số từ changelog, phân biệt failure/error, chính sách onFail/onError, cách kiểm thử và đóng gói class, cũng như các lỗi thường gặp. Mục tiêu của **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Custom precondition mở rộng khả năng kiểm tra của Liquibase nhưng vẫn phải giữ nguyên nguyên tắc migration có thể review, lặp lại và kiểm toán.

## 1. Khi nào cần custom precondition?

Precondition là điều kiện phải được đánh giá trước khi Liquibase thực thi changeset hoặc tiếp tục xử lý changelog. Chúng giúp kiểm tra giả định về database: bảng đã tồn tại, cột chưa tồn tại, đang kết nối đúng DBMS, hoặc dữ liệu đã ở trạng thái phù hợp.

Liquibase có nhiều precondition dựng sẵn:

| Precondition | Mục đích |
|---|---|
| **dbms** | Giới hạn changeset theo loại DBMS |
| **runningAs** | Kiểm tra user đang kết nối |
| **tableExists** | Kiểm tra bảng tồn tại |
| **columnExists** | Kiểm tra cột tồn tại |
| **indexExists** | Kiểm tra index tồn tại |
| **sequenceExists** | Kiểm tra sequence tồn tại |
| **foreignKeyConstraintExists** | Kiểm tra foreign key |
| **primaryKeyExists** | Kiểm tra primary key |
| **uniqueConstraintExists** | Kiểm tra unique constraint |
| **viewExists** | Kiểm tra view |
| **changeSetExecuted** | Kiểm tra changeset khác đã chạy |
| **changeLogPropertyDefined** | Kiểm tra property changelog |
| **sqlCheck** | Chạy truy vấn và so sánh kết quả với giá trị mong đợi |
| **customPrecondition** | Gọi lớp Java do nhóm triển khai |

Trước khi viết mã tùy chỉnh, hãy kiểm tra xem precondition dựng sẵn hoặc sqlCheck có biểu diễn được quy tắc không. Custom precondition làm tăng số thành phần phải build, kiểm thử, version và triển khai cùng Liquibase. Không nên tạo một lớp Java chỉ để kiểm tra một bảng hoặc một cột mà Liquibase đã hỗ trợ.

Custom precondition phù hợp khi logic kiểm tra có nhiều bước, cần gọi API metadata, cần áp dụng quy tắc nghiệp vụ đặc thù hoặc cần tái sử dụng một phép kiểm tra phức tạp ở nhiều changelog.

### 1.1. Ví dụ các quy tắc có thể cần mở rộng

- Xác nhận bảng migration marker có bản ghi cho một đợt backfill cụ thể.
- Kiểm tra một tập bảng có cùng schema version do hệ thống nội bộ quản lý.
- Kiểm tra metadata hoặc kiểu đối tượng riêng của một DBMS.
- Xác minh dữ liệu đã được chuẩn hóa theo quy tắc nghiệp vụ trước khi thêm constraint.
- Kiểm tra một cấu hình database đặc thù mà precondition chuẩn không cung cấp.
- Kiểm tra trạng thái của một extension hoặc feature database trước khi dùng nó trong changeset.

Không dùng custom precondition để thay thế database constraint, khóa ngoại, unique constraint hoặc validation của dữ liệu ở mọi writer. Precondition chỉ kiểm tra trước thời điểm migration. Sau khi kiểm tra, ứng dụng hoặc một tiến trình khác vẫn có thể thay đổi dữ liệu.

## 2. Phân biệt precondition failure và precondition error

Đây là điểm quan trọng nhất khi triển khai custom precondition.

**Failure** nghĩa là phép kiểm tra đã chạy thành công và kết luận điều kiện không thỏa mãn. Ví dụ truy vấn được thực thi, nhưng không tìm thấy marker bắt buộc.

**Error** nghĩa là Liquibase không thể hoàn tất phép kiểm tra. Ví dụ không kết nối được database, truy vấn bị lỗi, tham số cấu hình không hợp lệ hoặc class tùy chỉnh không thể đọc metadata cần thiết.

| Kết quả | Ý nghĩa | Ví dụ |
|---|---|---|
| **Pass** | Điều kiện được đáp ứng | Tìm thấy marker của đợt backfill |
| **Failed** | Đã kiểm tra và điều kiện sai | Không có marker cần thiết |
| **Error** | Không thể xác định điều kiện | Connection timeout, SQL exception, thiếu tham số |

Không chuyển mọi exception thành failure. Nếu database timeout, custom precondition không thể kết luận marker không tồn tại; nó chỉ biết rằng việc kiểm tra thất bại về mặt kỹ thuật. Phân loại sai có thể khiến pipeline dùng MARK_RAN hoặc WARN và tiếp tục trên trạng thái chưa được xác minh.

Một quy tắc thực tế:

- Điều kiện nghiệp vụ không đạt: ném CustomPreconditionFailedException.
- Không thể thực hiện phép kiểm tra: ném CustomPreconditionErrorException.
- Điều kiện đạt: kết thúc phương thức check bình thường.

Thông báo lỗi nên nêu tên điều kiện và ngữ cảnh đủ để điều tra, nhưng không chứa password, token, dữ liệu cá nhân hoặc chuỗi kết nối đầy đủ.

## 3. API Java của custom precondition

Liquibase cung cấp interface **liquibase.precondition.CustomPrecondition** để triển khai phép kiểm tra tùy chỉnh. Lớp thường cần:

- Implement CustomPrecondition.
- Có constructor không tham số để Liquibase có thể khởi tạo.
- Cung cấp các thuộc tính JavaBean public setter cho tham số cấu hình.
- Implement phương thức check nhận đối tượng Database.
- Ném đúng loại exception để phân biệt failure và error.
- Được đặt trong classpath của Liquibase runtime.

Khung lớp:

~~~java
package com.example.database.liquibase;

import liquibase.database.Database;
import liquibase.exception.CustomPreconditionErrorException;
import liquibase.exception.CustomPreconditionFailedException;
import liquibase.precondition.CustomPrecondition;

public class RequiredMigrationMarker implements CustomPrecondition {

    private String schemaName;
    private String tableName;
    private String markerKey;

    public RequiredMigrationMarker() {
        // Liquibase tạo instance qua constructor không tham số.
    }

    public void setSchemaName(String schemaName) {
        this.schemaName = schemaName;
    }

    public void setTableName(String tableName) {
        this.tableName = tableName;
    }

    public void setMarkerKey(String markerKey) {
        this.markerKey = markerKey;
    }

    @Override
    public void check(Database database)
            throws CustomPreconditionFailedException,
                   CustomPreconditionErrorException {
        // Kiểm tra tham số, truy vấn database và phân loại kết quả.
    }
}
~~~

Tên package của hai exception và interface ở trên thuộc API Liquibase. Khi build extension, khai báo dependency Liquibase API/core tương thích với runtime triển khai. Không đóng gói một bản Liquibase core khác vào extension nếu ứng dụng hoặc CLI đã cung cấp cùng thư viện, vì có thể gây xung đột classloader.

### 3.1. Vai trò của đối tượng Database

Đối tượng Database được Liquibase truyền vào đại diện cho database đang thực thi changelog. Có thể dùng nó để lấy:

- Database product name và version.
- Default catalog/schema.
- Connection do Liquibase quản lý.
- Quy tắc escape tên bảng/cột.
- Thông tin capability của DBMS.

Ưu tiên dùng API Liquibase hoặc JDBC metadata thay vì tự giả định tên schema, cách viết hoa tên đối tượng hay dialect. Một custom precondition dùng trực tiếp SQL cần tính đến khác biệt PostgreSQL, MySQL, Oracle, SQL Server và các DBMS khác nếu extension tuyên bố hỗ trợ nhiều engine.

### 3.2. Không tự quản lý connection tùy tiện

Liquibase sở hữu vòng đời connection cho migration. Custom precondition nên sử dụng connection được cung cấp qua Database, không tự mở connection thứ hai bằng DriverManager với URL/credential riêng. Mở kết nối riêng có thể:

- Dùng nhầm database hoặc schema.
- Bỏ qua TLS/configuration của Liquibase.
- Không dùng cùng transaction/session.
- Làm rò rỉ connection nếu không đóng đúng cách.
- Tạo thêm quyền truy cập ngoài dự kiến.

Nếu cần dùng JDBC API trực tiếp, lấy connection hiện tại từ Database và đóng các Statement/ResultSet do custom precondition tạo. Không đóng connection chính do Liquibase quản lý.

## 4. Ví dụ: kiểm tra migration marker bằng JDBC

Giả sử hệ thống có bảng APP_MIGRATION_MARKER với cột MARKER_KEY. Một bước backfill dữ liệu phải được một job riêng hoàn thành và ghi marker trước khi Liquibase thêm constraint NOT NULL.

Điều kiện mong muốn: marker có giá trị CUSTOMER_REGION_BACKFILL_V2 phải tồn tại. Nếu không tìm thấy, changeset phải dừng. Nếu truy vấn không thể thực hiện, đó là error.

Ví dụ Java dưới đây minh họa cách dùng PreparedStatement để truyền giá trị marker. Tên bảng và cột được cố định trong mã mẫu để tránh ghép identifier tùy ý từ input:

~~~java
package com.example.database.liquibase;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

import liquibase.database.Database;
import liquibase.database.jvm.JdbcConnection;
import liquibase.exception.CustomPreconditionErrorException;
import liquibase.exception.CustomPreconditionFailedException;
import liquibase.precondition.CustomPrecondition;

public class RequiredMigrationMarker implements CustomPrecondition {

    private String markerKey;

    public RequiredMigrationMarker() {
    }

    public void setMarkerKey(String markerKey) {
        this.markerKey = markerKey;
    }

    @Override
    public void check(Database database)
            throws CustomPreconditionFailedException,
                   CustomPreconditionErrorException {

        if (markerKey == null || markerKey.trim().isEmpty()) {
            throw new CustomPreconditionErrorException(
                "RequiredMigrationMarker: markerKey is required"
            );
        }

        String sql =
            "SELECT 1 FROM APP_MIGRATION_MARKER " +
            "WHERE MARKER_KEY = ?";

        try {
            JdbcConnection liquibaseConnection =
                (JdbcConnection) database.getConnection();

            Connection jdbc = liquibaseConnection.getUnderlyingConnection();

            try (PreparedStatement statement = jdbc.prepareStatement(sql)) {
                statement.setString(1, markerKey);
                statement.setMaxRows(1);

                try (ResultSet result = statement.executeQuery()) {
                    if (!result.next()) {
                        throw new CustomPreconditionFailedException(
                            "Required migration marker was not found: " + markerKey
                        );
                    }
                }
            }
        } catch (CustomPreconditionFailedException e) {
            throw e;
        } catch (Exception e) {
            throw new CustomPreconditionErrorException(
                "Could not verify migration marker using the Liquibase connection",
                e
            );
        }
    }
}
~~~

Đây là ví dụ minh họa cho JDBC-backed database và một bảng marker có tên cố định. Trong dự án thực tế, cần kiểm tra chữ hoa/thường, schema mặc định và quy tắc quote identifier của DBMS. Nếu bảng nằm trong schema riêng, hãy mở rộng lớp để nhận schemaName, validate identifier và dùng quy tắc escape của Liquibase/DBMS. Không ghép trực tiếp giá trị marker hoặc dữ liệu không tin cậy vào SQL; dùng PreparedStatement cho giá trị.

### 4.1. Vì sao marker phù hợp với precondition?

Marker đại diện cho kết quả của một công việc dữ liệu bên ngoài, chẳng hạn batch backfill. Liquibase không cần tự suy luận rằng job đã hoàn tất dựa trên một truy vấn đếm dữ liệu rất lớn; nó kiểm tra một dấu mốc được ghi sau khi job xác minh thành công.

Tuy nhiên, marker chỉ đáng tin nếu quy trình ghi marker có kiểm soát:

- Job chỉ ghi marker sau khi toàn bộ batch hoàn thành.
- Job xác minh số lượng và invariant dữ liệu trước khi ghi.
- Marker gắn với đúng phiên bản/đợt backfill.
- Marker không bị ghi bởi tài khoản ứng dụng thông thường nếu không cần.
- Có audit hoặc bằng chứng vận hành cho lần tạo marker.

Không để một marker chung chung như BACKFILL_DONE đại diện cho nhiều lần chuyển đổi khác nhau.

## 5. Khai báo custom precondition trong YAML changelog

Custom precondition được gọi bằng className và các tham số tương ứng với JavaBean setter.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-030-add-region-constraint"
      author: "platform"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - customPrecondition:
            className: com.example.database.liquibase.RequiredMigrationMarker
            param:
              - name: markerKey
                value: CUSTOMER_REGION_BACKFILL_V2
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: region
            columnDataType: VARCHAR(40)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: region
            columnDataType: VARCHAR(40)
~~~

Khi chạy changeset:

1. Liquibase khởi tạo class được chỉ định.
2. Liquibase gán tham số markerKey thông qua setter.
3. Liquibase gọi check với Database hiện tại.
4. Nếu marker tồn tại, precondition pass và changeset có thể chạy.
5. Nếu marker không tồn tại, custom class ném CustomPreconditionFailedException.
6. Nếu truy vấn không thực hiện được, custom class ném CustomPreconditionErrorException.
7. Liquibase áp dụng onFail hoặc onError theo cấu hình scope.

Tên class phải đầy đủ package và class phải có trong classpath của Liquibase runtime. YAML phải giữ đúng cấu trúc danh sách param theo parser/phiên bản Liquibase được sử dụng. Hãy chạy validate và integration test bằng đúng runtime đã pin.

### 5.1. Tham số JavaBean

Mỗi tham số khai báo trong YAML phải có setter tương ứng:

~~~yaml
param:
  - name: markerKey
    value: CUSTOMER_REGION_BACKFILL_V2
  - name: schemaName
    value: app
~~~

Tương ứng:

~~~java
public void setMarkerKey(String markerKey) {
    this.markerKey = markerKey;
}

public void setSchemaName(String schemaName) {
    this.schemaName = schemaName;
}
~~~

Không dựa vào constructor có tham số hoặc field private không có setter nếu cơ chế khởi tạo của Liquibase yêu cầu JavaBean property. Kiểm tra spelling, kiểu dữ liệu và giá trị mặc định. Nếu thiếu tham số bắt buộc, nên báo CustomPreconditionErrorException với thông điệp rõ ràng vì Liquibase không thể thực hiện phép kiểm tra hợp lệ.

### 5.2. Tránh để tham số nhạy cảm trong changelog

Tham số custom precondition thường được lưu trong source changelog và có thể xuất hiện trong log. Chỉ truyền metadata không nhạy cảm như marker key, tên schema hoặc ngưỡng kiểm tra. Không truyền password, token, private key hoặc dữ liệu bí mật qua param.

## 6. Chọn onFail và onError đúng mục đích

Liquibase cung cấp chính sách xử lý khi precondition thất bại hoặc phát sinh lỗi. Hai thuộc tính này có ý nghĩa khác nhau:

- **onFail** xử lý trường hợp điều kiện đã được đánh giá nhưng không đạt.
- **onError** xử lý trường hợp không thể hoàn tất việc đánh giá điều kiện.

Các lựa chọn phổ biến:

| Giá trị | Hành vi |
|---|---|
| **HALT** | Dừng quá trình update và báo lỗi |
| **CONTINUE** | Bỏ qua changeset hiện tại, tiếp tục xử lý; changeset chưa được đánh dấu đã chạy và có thể được đánh giá lại ở lần update sau |
| **MARK_RAN** | Đánh dấu changeset là đã chạy mà không thực thi changeset |
| **WARN** | Ghi cảnh báo và tiếp tục xử lý theo luồng triển khai |

CONTINUE và MARK_RAN là lựa chọn ở scope changeset; không dùng chúng như chính sách changelog-level nếu phiên bản Liquibase không hỗ trợ. Ở scope changelog, thường chọn HALT hoặc WARN. Luôn xác minh quy tắc theo phiên bản Liquibase đang dùng.

### 6.1. Khi nào chọn HALT?

Dùng HALT khi điều kiện là yêu cầu bắt buộc để migration an toàn:

- Backfill chưa hoàn tất.
- Bảng hoặc cột cần thiết chưa có.
- Kết nối tới DBMS/schema không đúng.
- Dữ liệu còn NULL trước khi thêm NOT NULL.
- Tài khoản hiện tại không đáp ứng chính sách triển khai.
- Một trạng thái không thể xác minh được.

Đây thường là lựa chọn an toàn cho custom precondition kiểm tra điều kiện dữ liệu trước thay đổi phá tương thích.

### 6.2. Khi nào chọn CONTINUE?

CONTINUE phù hợp khi changeset có thể chờ một điều kiện bên ngoài và được thử lại ở lần triển khai sau. Ví dụ một migration tùy chọn chỉ chạy khi một feature đã được bật.

Cần lưu ý changeset bị bỏ qua không tự trở thành hoàn tất. Pipeline phải biết rằng một phần migration còn pending và không báo toàn bộ release thành công nếu ứng dụng yêu cầu changeset đó.

### 6.3. Khi nào chọn MARK_RAN?

MARK_RAN chỉ nên dùng khi failure chứng minh rằng hiệu ứng mà changeset định tạo đã tồn tại chính xác và có thể coi như changeset đã được áp dụng.

Ví dụ một quy trình baseline có thể cần ghi nhận trạng thái đã tồn tại từ trước. Nhưng chỉ kiểm tra “bảng có tên này” rồi MARK_RAN có thể che một schema sai: bảng tồn tại nhưng thiếu cột, sai kiểu hoặc thiếu constraint.

Nếu điều kiện không đạt vì migration chưa được thực hiện, MARK_RAN sẽ làm Liquibase ghi changeset vào DATABASECHANGELOG dù thay đổi chưa xảy ra. Khi đó lịch sử và schema thực tế lệch nhau. Trước khi chọn MARK_RAN, phải xác minh trạng thái đích đầy đủ, có bằng chứng và có review.

### 6.4. Khi nào chọn WARN?

WARN dành cho điều kiện mang tính cảnh báo, không phải điều kiện an toàn bắt buộc. Vì pipeline có thể tiếp tục, không dùng WARN để xử lý thiếu dữ liệu, sai schema hoặc lỗi kết nối mà changeset phụ thuộc.

Nếu custom precondition phát hiện trạng thái không xác minh được do database timeout, WARN có thể khiến changeset vẫn chạy. Hành vi đó thường nguy hiểm. Hãy phân loại đúng failure/error và dùng HALT khi không có cơ sở an toàn để tiếp tục.

## 7. Xử lý exception bên trong custom precondition

Một custom precondition tốt có luồng xử lý đơn giản:

1. Validate tham số đầu vào.
2. Lấy connection từ Database do Liquibase truyền vào.
3. Thực hiện phép kiểm tra read-only.
4. Nếu điều kiện sai, ném CustomPreconditionFailedException.
5. Nếu có lỗi kỹ thuật, ném CustomPreconditionErrorException và giữ nguyên cause.
6. Nếu đạt, trả về bình thường.

Ví dụ phân loại:

~~~java
if (markerKey == null || markerKey.trim().isEmpty()) {
    throw new CustomPreconditionErrorException(
        "markerKey must be configured"
    );
}

try {
    boolean markerExists = queryMarker(markerKey);

    if (!markerExists) {
        throw new CustomPreconditionFailedException(
            "Required migration marker is missing"
        );
    }
} catch (CustomPreconditionFailedException e) {
    throw e;
} catch (Exception e) {
    throw new CustomPreconditionErrorException(
        "Unable to evaluate migration marker",
        e
    );
}
~~~

Đoạn trên là mẫu luồng xử lý; phương thức queryMarker cần dùng connection do Liquibase quản lý và đóng tài nguyên JDBC do nó tạo.

Không bắt exception rồi trả về false cho mọi trường hợp. Cách đó biến network outage, SQL syntax error và quyền truy cập bị từ chối thành failure nghiệp vụ. Pipeline khi đó có thể xử lý theo onFail dù thực tế phép kiểm tra chưa chạy được.

### 7.1. Giữ nguyên nguyên nhân gốc

Khi ném CustomPreconditionErrorException, truyền cause nếu constructor của phiên bản API hỗ trợ. Điều này giữ stack trace và giúp phân biệt:

- Connection refused/timeout.
- Authentication failed.
- SQL syntax/permission error.
- Class cast hoặc lỗi API.
- Lỗi chuyển đổi dữ liệu.
- Metadata không được DBMS cung cấp.

Thông báo hướng tới người vận hành nên có tên precondition và bước kiểm tra, không in password hoặc URL chứa secret.

### 7.2. Không dùng exception làm nhánh nghiệp vụ thông thường

Failure là kết quả kiểm tra dự kiến, được biểu diễn bằng CustomPreconditionFailedException. Error là sự cố khi thực hiện kiểm tra. Không dùng RuntimeException chung cho mọi kết quả nếu API cho phép phân loại cụ thể.

## 8. Precondition ở scope changelog và changeset

Precondition có thể áp dụng ở hai scope:

- **Changelog-level**: điều kiện tổng thể trước khi Liquibase xử lý các changeset trong changelog.
- **Changeset-level**: điều kiện riêng cho một changeset.

Changelog-level thích hợp cho điều kiện nền tảng như DBMS, schema hoặc môi trường mà toàn bộ changelog yêu cầu. Changeset-level thích hợp cho điều kiện cục bộ như marker backfill hoặc bảng/cột mà chỉ một migration cần.

Ví dụ changelog-level:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql
  - changeSet:
      id: "BASE-001"
      author: "platform"
      changes:
        - createTable:
            tableName: migration_audit
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ví dụ changeset-level:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "DATA-024"
      author: "platform"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - customPrecondition:
            className: com.example.database.liquibase.RequiredMigrationMarker
            param:
              - name: markerKey
                value: CUSTOMER_REGION_BACKFILL_V2
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: region
            columnDataType: VARCHAR(40)
~~~

Không đặt điều kiện chỉ liên quan một changeset ở scope toàn changelog nếu nó có thể làm dừng cả những changeset độc lập. Ngược lại, điều kiện nền tảng bắt buộc nên được đặt ở scope rõ ràng để không bị bỏ sót ở một changeset mới.

## 9. Kết hợp custom precondition với điều kiện chuẩn

Custom precondition không phải thay thế toàn bộ precondition dựng sẵn. Có thể kết hợp để tạo điều kiện rõ ràng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "DATA-025"
      author: "platform"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - dbms:
            type: postgresql
        - tableExists:
            schemaName: app
            tableName: APP_MIGRATION_MARKER
        - customPrecondition:
            className: com.example.database.liquibase.RequiredMigrationMarker
            param:
              - name: markerKey
                value: CUSTOMER_REGION_BACKFILL_V2
      changes:
        - addNotNullConstraint:
            schemaName: app
            tableName: customer
            columnName: region
            columnDataType: VARCHAR(40)
~~~

Các điều kiện trong preConditions mặc định được kết hợp theo logic AND nếu không chỉ định logic container khác. Nếu cần OR/NOT, dùng cấu trúc tương ứng và đọc kỹ cách nhóm điều kiện. Không viết một custom class quá lớn chỉ để thay thế dbms, tableExists hay columnExists.

Việc đặt tableExists trước customPrecondition có thể làm thông báo lỗi rõ hơn, nhưng custom class vẫn cần xử lý trường hợp bảng biến mất giữa hai lần kiểm tra hoặc schema khác với dự kiến.

## 10. Thiết kế custom precondition an toàn và hiệu quả

Custom precondition chạy trong quá trình migration, thường có quyền kết nối database đáng kể. Vì vậy, nó phải được thiết kế như một thành phần triển khai có độ tin cậy cao.

### 10.1. Chỉ đọc, không tạo side effect

Precondition nên chỉ quan sát trạng thái database. Không thực hiện:

- CREATE/ALTER/DROP.
- INSERT/UPDATE/DELETE.
- Gọi procedure có side effect.
- Ghi marker hoặc sửa trạng thái migration.
- Thay đổi session setting lâu dài.
- Gọi dịch vụ ngoài để tạo dữ liệu.

Nếu phép kiểm tra cần tạo hoặc sửa dữ liệu, đó là một change hoặc bước vận hành riêng, không phải precondition. Side effect trong precondition có thể xảy ra trước changeset nhưng không được ghi nhận như một changeset độc lập, làm khó rollback và kiểm toán.

### 10.2. Truy vấn nhỏ và có giới hạn

Không chạy COUNT(*) trên bảng rất lớn nếu chỉ cần biết có một bản ghi tồn tại. Dùng truy vấn dạng EXISTS hoặc SELECT 1 với giới hạn phù hợp DBMS. Đảm bảo cột điều kiện có index nếu cần.

Một precondition quét hàng triệu bản ghi mỗi lần Liquibase update có thể kéo dài startup, giữ lock và làm tăng tải database. Đo thời gian thực tế trên kích thước dữ liệu gần production.

### 10.3. Tránh SQL injection và lỗi identifier

- Dùng PreparedStatement cho giá trị.
- Không nối chuỗi input vào WHERE clause.
- Identifier như schema/table/column không thể bind bằng placeholder JDBC; validate theo allowlist và quote theo DBMS.
- Không nhận SQL tùy ý từ changelog nếu không có kiểm soát review.
- Không log dữ liệu bí mật của bản ghi được kiểm tra.

Nếu class hỗ trợ nhiều DBMS, dùng Database.escapeTableName/escapeColumnName hoặc metadata phù hợp thay vì tự ghép dấu quote.

### 10.4. Null, kiểu dữ liệu và collation

Tham số YAML thường được chuyển thành chuỗi. Hãy parse rõ số, boolean, ngày hoặc enum; validate giá trị null/rỗng và miền hợp lệ. Không so sánh chuỗi tùy tiện khi database có collation/case sensitivity khác nhau.

Ví dụ marker key có thể phân biệt hoa thường ở một DBMS nhưng không phân biệt ở DBMS khác. Nếu đây là định danh, quy định canonical format và kiểm tra trên từng engine.

## 11. Tính đúng đắn trong điều kiện đồng thời

Precondition kiểm tra một thời điểm. Sau khi nó pass, một ứng dụng hoặc job khác vẫn có thể thay đổi dữ liệu trước khi changeset chạy. Đây là race condition giữa check và action.

Ví dụ:

1. Custom precondition xác nhận không còn customer có region NULL.
2. Một writer cũ tiếp tục insert customer với region NULL.
3. Liquibase thực hiện addNotNullConstraint.
4. DDL thất bại vì có bản ghi mới vi phạm constraint.

Liquibase DATABASECHANGELOGLOCK ngăn nhiều tiến trình Liquibase cùng cập nhật changelog table theo cơ chế lock. Nó không khóa tất cả writer của ứng dụng và không ngăn thay đổi dữ liệu ngoài Liquibase.

Cách giảm rủi ro:

- Deploy application ngừng tạo dữ liệu vi phạm trước migration.
- Dùng database constraint/transaction/lock phù hợp DBMS.
- Chạy backfill và xác minh gần thời điểm thay đổi.
- Dùng migration expand-contract.
- Nếu cần, tạm dừng writer hoặc bật chế độ maintenance.
- Để database constraint là hàng rào cuối cùng.

Không dựa vào precondition như một khóa đồng bộ. Nếu tính đúng đắn phụ thuộc trạng thái không được phép thay đổi giữa check và DDL, phải có cơ chế đồng bộ ở database hoặc ở quy trình triển khai.

## 12. Đóng gói custom precondition thành Liquibase extension

Custom precondition là Java class nên phải có trong classpath của Liquibase khi chạy. Có thể đóng gói class vào JAR extension.

Một cấu trúc dự án minh họa:

~~~text
liquibase-custom-preconditions/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/database/liquibase/
                └── RequiredMigrationMarker.java
~~~

Dependency Liquibase API/core cần được khai báo ở scope phù hợp. Nếu extension được nạp bởi Liquibase CLI, hãy đặt JAR trong classpath/lib theo cách phân phối CLI hỗ trợ. Nếu chạy trong Spring Boot, JAR extension cần nằm trong runtime classpath của ứng dụng.

### 12.1. Tương thích phiên bản

Custom class biên dịch với một phiên bản Liquibase nhưng chạy với phiên bản khác có thể gặp:

- NoSuchMethodError.
- NoClassDefFoundError.
- ClassCastException.
- Thay đổi package/API.
- Khác biệt behavior của parser hoặc reflection.

Pin version API mà extension biên dịch cùng và kiểm thử với Liquibase runtime thật. Không đóng gói hai bản Liquibase core cạnh nhau nếu classloader có thể nạp nhầm.

### 12.2. Extension discovery và className

Với customPrecondition khai báo className, Liquibase cần load đúng class theo tên đầy đủ. Vì vậy:

- Class phải public và có constructor không tham số.
- Class phải implement đúng interface của Liquibase runtime.
- Tất cả dependency của class phải có mặt.
- Tên class trong YAML phải đúng package/case.
- Setter phải public và khớp tên param.
- Class phải được đóng gói vào artifact đang thực thi, không chỉ tồn tại trong module source.

Nếu dùng các extension mechanism khác của Liquibase, kiểm tra quy tắc discovery/service registration tương ứng. Không giả định mọi custom class đều tự được phát hiện chỉ vì JAR nằm trong repository.

## 13. Kiểm thử custom precondition

Một custom precondition cần được kiểm thử ở ba lớp:

| Lớp kiểm thử | Mục tiêu |
|---|---|
| Unit test | Validate tham số và logic phân loại pass/fail/error |
| Integration test | Thực thi với database thật hoặc container đúng DBMS |
| Packaging test | Xác minh class và dependency có trong runtime artifact |

### 13.1. Unit test

Có thể kiểm tra:

- Thiếu markerKey phải trả error.
- markerKey hợp lệ và marker tồn tại phải pass.
- marker không tồn tại phải trả failure.
- SQLException phải trở thành error và giữ nguyên cause.
- Thông báo không chứa credential.
- Kết nối do Liquibase cung cấp không bị đóng.

Nếu dùng mock Database/Connection, chỉ kiểm tra logic đơn vị; mock không thay thế integration test với DBMS thật.

### 13.2. Integration test với Testcontainers

Dùng container cùng loại DBMS với production:

1. Khởi tạo database rỗng.
2. Tạo bảng marker bằng fixture hoặc changeset chuẩn bị.
3. Chạy changeset có custom precondition khi marker tồn tại.
4. Xác minh changeset chạy và DATABASECHANGELOG ghi nhận.
5. Xóa marker ở database test.
6. Chạy trong database mới hoặc trạng thái được reset; xác nhận HALT/CONTINUE/MARK_RAN theo cấu hình.
7. Mô phỏng lỗi kết nối hoặc quyền để xác nhận onError.
8. Kiểm tra custom class được nạp từ artifact, không chỉ từ IDE classpath.

Không dùng lại database đã bị MARK_RAN để kiểm thử nhánh failure; Liquibase có thể bỏ qua changeset vì nó đã được ghi vào DATABASECHANGELOG. Tạo database mới hoặc reset trạng thái kiểm thử theo cách có kiểm soát.

### 13.3. Kiểm thử nhiều phiên bản Liquibase

Nếu extension hỗ trợ nhiều phiên bản Liquibase, chạy ma trận kiểm thử cho các phiên bản được hỗ trợ. Nếu chỉ hỗ trợ một dải hẹp, ghi rõ dải đó trong tài liệu và manifest artifact. Không tuyên bố tương thích rộng khi chỉ thử một version.

## 14. Chẩn đoán lỗi custom precondition

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Class not found | JAR custom precondition không nằm trong runtime classpath | Kiểm tra CLI lib hoặc Spring Boot runtime dependency |
| Could not instantiate class | Class không public, thiếu no-arg constructor hoặc constructor ném lỗi | Sửa constructor và kiểm tra class loading |
| Property/parameter not found | Tên param không khớp setter | Đối chiếu YAML param với JavaBean setter |
| NoSuchMethodError | Extension và Liquibase runtime không tương thích | Pin và kiểm tra version |
| ClassCastException | Nạp hai bản Liquibase API/core hoặc dùng connection không phải JdbcConnection | Kiểm tra dependency tree và loại DatabaseConnection |
| Always fails | Logic query, schema hoặc marker key sai | Kiểm tra dữ liệu test, default schema và query |
| Always errors | SQL exception, quyền thiếu hoặc kết nối lỗi | Đọc root cause đã redact |
| Migration tiếp tục dù điều kiện sai | onFail=WARN hoặc policy không phù hợp | Chọn HALT nếu điều kiện là bắt buộc |
| Changeset bị đánh dấu ran dù chưa thay đổi schema | onFail/onError=MARK_RAN | Kiểm tra DATABASECHANGELOG và trạng thái thật; lập kế hoạch sửa |
| Precondition chạy quá lâu | Query scan lớn hoặc thiếu index | Tối ưu truy vấn, giới hạn kết quả, đo trên dữ liệu đại diện |
| IDE chạy nhưng CLI lỗi | Extension chỉ có trong application classpath | Đóng gói JAR vào CLI runtime |
| Local chạy nhưng container lỗi | Image thiếu extension hoặc mount/classpath sai | Kiểm tra artifact bên trong container |

### 14.1. Trình tự điều tra

1. Xác định changeset và custom class được gọi.
2. Kiểm tra className trong YAML.
3. Kiểm tra JAR có trong classpath của đúng runtime không.
4. Xác nhận Liquibase API/runtime version tương thích.
5. Kiểm tra constructor và setter.
6. Đọc exception gốc để phân biệt failure với error.
7. Kiểm tra schema, quyền và dữ liệu mà query phụ thuộc.
8. Xem onFail/onError ở đúng scope.
9. Kiểm tra DATABASECHANGELOG nếu changeset đã bị MARK_RAN.
10. Chạy lại trong database test sạch và đúng DBMS.

Không xóa dòng DATABASECHANGELOG để ép chạy lại trước khi hiểu trạng thái schema. Nếu changeset đã bị MARK_RAN sai, cần đánh giá cách đồng bộ lịch sử với schema thật theo kế hoạch được review.

## 15. Tích hợp với Spring Boot và CI/CD

Nếu custom precondition được dùng trong ứng dụng Spring Boot:

- Đóng gói JAR extension trong runtime dependency.
- Đảm bảo Liquibase auto-configuration nạp đúng datasource.
- Giữ changelog và class extension cùng phiên bản release.
- Dùng tài khoản migration có quyền cần thiết.
- Chạy Hibernate validate sau khi migration hoàn tất nếu ứng dụng dùng JPA.
- Kiểm tra startup log để xác nhận class được load.

Nếu dùng migration job độc lập:

- Đóng gói CLI, extension JAR, JDBC driver và changelog trong cùng artifact.
- Pin Liquibase version.
- Chạy validate và integration test bằng chính artifact.
- Cấp secret runtime qua secret manager.
- Dừng pipeline nếu custom precondition error hoặc failure có policy HALT.
- Lưu log đã redact, artifact digest và changeset history.
- Không dùng WARN để biến điều kiện bắt buộc thành advisory.

### 15.1. Tách build và deploy

CI build extension và migration artifact một lần. CD promote cùng artifact qua development, staging và production. Không biên dịch lại custom class ở từng môi trường hoặc tải extension phiên bản khác khi deploy.

Manifest nên ghi:

- Artifact version và digest.
- Source commit.
- Liquibase version.
- Java runtime.
- Custom extension version.
- JDBC driver version.
- DBMS/version đã kiểm thử.
- Master changelog path.
- Kết quả unit/integration/packaging test.

Credential, private key và URL có password không nằm trong manifest.

## 16. Những anti-pattern cần tránh

**Dùng custom precondition cho việc đã có built-in precondition**: làm tăng mã và dependency mà không tăng khả năng kiểm soát.

**Đưa DDL/DML vào precondition**: tạo side effect ngoài changeset, làm khó audit và rollback.

**Nuốt mọi exception rồi trả false**: biến lỗi kết nối thành failure nghiệp vụ, khiến onFail xử lý sai.

**Dùng WARN cho điều kiện bắt buộc**: pipeline có thể tiếp tục dù trạng thái database không an toàn.

**Dùng MARK_RAN như cách bỏ qua lỗi**: DATABASECHANGELOG có thể ghi changeset đã chạy trong khi schema chưa đạt trạng thái đích.

**Quét toàn bảng ở mỗi lần update**: tăng thời gian giữ Liquibase lock và tải database.

**Ghép input trực tiếp vào SQL**: tạo nguy cơ SQL injection hoặc lỗi quote identifier.

**Mở connection riêng bằng credential hard-code**: bỏ qua datasource, TLS và quyền được cấu hình cho Liquibase.

**Không pin Liquibase API**: extension có thể hỏng khi runtime nâng phiên bản.

**Chỉ thử trong IDE**: CLI, JAR hoặc container có thể thiếu custom class.

**Dựa vào precondition thay cho constraint**: dữ liệu có thể đổi sau khi check; database vẫn cần ràng buộc thực thi lâu dài.

## 17. Bài thực hành: chặn constraint khi backfill chưa hoàn tất

**Bối cảnh:** Bảng customer có cột region cho phép NULL. Một job đã backfill dữ liệu. Trước khi thêm NOT NULL, Liquibase phải xác nhận marker CUSTOMER_REGION_BACKFILL_V2 tồn tại.

### Bước 1 — Chuẩn bị bảng marker

Tạo bảng marker qua changeset có version và quyền phù hợp. Job backfill chỉ ghi marker sau khi xác minh toàn bộ dữ liệu.

### Bước 2 — Viết custom precondition

Tạo lớp RequiredMigrationMarker với tham số markerKey. Lớp dùng connection do Liquibase cung cấp và PreparedStatement để tìm marker. Nếu không tìm thấy, ném CustomPreconditionFailedException; nếu truy vấn lỗi, ném CustomPreconditionErrorException.

### Bước 3 — Khai báo trong changelog

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "CUSTOMER-042-region-not-null"
      author: "platform"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - customPrecondition:
            className: com.example.database.liquibase.RequiredMigrationMarker
            param:
              - name: markerKey
                value: CUSTOMER_REGION_BACKFILL_V2
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: region
            columnDataType: VARCHAR(40)
~~~

### Bước 4 — Kiểm thử nhánh pass

- Chạy job backfill trên database test.
- Xác minh không còn customer có region NULL.
- Ghi marker.
- Chạy Liquibase update.
- Xác minh constraint được tạo và changeset có trong DATABASECHANGELOG.

### Bước 5 — Kiểm thử nhánh failure

- Tạo database test mới.
- Không ghi marker.
- Chạy Liquibase update.
- Xác nhận changeset dừng theo HALT.
- Xác nhận changeset không bị ghi nhận là đã chạy.
- Ghi marker hợp lệ và chạy lại để xác nhận migration có thể tiếp tục.

### Bước 6 — Kiểm thử nhánh error

- Dùng database test với quyền không đủ đọc bảng marker hoặc mô phỏng kết nối không khả dụng.
- Xác nhận custom class phân loại là error.
- Xác nhận onError=HALT dừng migration.
- Khôi phục quyền/kết nối và chạy lại.

### Bước 7 — Kiểm tra đóng gói

- Build extension JAR.
- Đưa JAR vào Spring Boot runtime hoặc Liquibase CLI classpath.
- Chạy test bằng artifact đã build.
- Xác minh className được load trong môi trường container/CI.
- Ghi lại version, digest và kết quả kiểm thử.

### Bước 8 — Đánh giá race condition

Xác định writer nào có thể tiếp tục ghi region NULL sau khi precondition pass. Nếu còn writer như vậy, phải triển khai tương thích ngược, dừng writer hoặc dùng cơ chế đồng bộ phù hợp trước khi thêm constraint. Marker không tự ngăn dữ liệu vi phạm mới xuất hiện.

## 18. Checklist review custom precondition

Trước khi đưa custom precondition vào release:

- Đã xác nhận precondition dựng sẵn hoặc sqlCheck không đáp ứng nhu cầu?
- Quy tắc kiểm tra được mô tả rõ và có thể kiểm chứng?
- Failure và error được phân biệt đúng?
- Class implement đúng CustomPrecondition API của phiên bản Liquibase?
- Có constructor không tham số và setter cho mọi param?
- Tham số được validate, có giá trị mặc định hoặc báo lỗi rõ?
- Custom class chỉ đọc và không tạo side effect?
- Dùng connection do Liquibase cung cấp?
- PreparedStatement được dùng cho giá trị truy vấn?
- Identifier được validate/escape theo DBMS?
- Query có giới hạn và không quét bảng lớn không cần thiết?
- Có xét schema, catalog, case sensitivity và DBMS dialect?
- onFail/onError phù hợp với mức độ bắt buộc của điều kiện?
- MARK_RAN chỉ dùng khi đã chứng minh trạng thái đích tương đương?
- WARN không được dùng để bỏ qua lỗi an toàn?
- Exception giữ nguyên root cause nhưng không lộ secret?
- Extension JAR và Liquibase runtime được pin phiên bản?
- Class có trong CLI/Spring Boot/container runtime classpath?
- Có unit test cho pass/failure/error?
- Có integration test trên DBMS đại diện?
- Có packaging test bằng artifact thực tế?
- Đã đánh giá race condition giữa precondition và thay đổi dữ liệu?
- Database constraint vẫn bảo vệ invariant sau migration?
- Log, artifact và deployment record đủ để điều tra?

**Kết luận:** Custom precondition mở rộng Liquibase cho những điều kiện đặc thù mà precondition dựng sẵn không biểu diễn được. Hãy triển khai qua CustomPrecondition, truyền tham số bằng JavaBean setter, dùng connection hiện tại do Liquibase cung cấp và giữ phép kiểm tra read-only. Phân biệt failure với error để áp dụng onFail/onError chính xác; dùng HALT cho điều kiện bắt buộc, thận trọng với MARK_RAN và WARN. Đóng gói class cùng runtime, pin phiên bản, kiểm thử pass/failure/error trên DBMS thực tế và đánh giá race condition trước khi chạy DDL. Khi được thiết kế như một phần của migration artifact có version, custom precondition giúp kiểm tra giả định một cách minh bạch, giữ lịch sử changeset nhất quán và làm pipeline triển khai an toàn hơn.

