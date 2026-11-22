# CustomTaskChange, CustomSqlChange và khả năng hoàn tác

Trong chương **Mở rộng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase cho phép bổ sung change type bằng Java khi các change type chuẩn hoặc SQL khai báo chưa diễn đạt được yêu cầu. Hai điểm mở rộng thường được dùng là `CustomTaskChange` và `CustomSqlChange`. Chúng có mục đích khác nhau: một loại thực thi công việc Java trực tiếp; loại còn lại sinh ra các `SqlStatement` để Liquibase thực thi. Khác biệt này ảnh hưởng đến khả năng xem trước SQL, transaction, tính portable, quan sát và đặc biệt là rollback.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học trình bày cách chọn đúng loại custom change, triển khai hợp đồng hoàn tác và kiểm thử hành vi trên DBMS mục tiêu.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Một custom change không tự động an toàn chỉ vì nó chạy được. Trước khi dùng, phải trả lời được nó thay đổi gì, có thể sinh SQL để review hay không, có thể chạy lại không, rollback có khôi phục dữ liệu thật không, và runner nào cần class đó trong classpath.

## 1. Phân biệt hai loại custom change

| Tiêu chí | CustomTaskChange | CustomSqlChange |
|---|---|---|
| Cách hoạt động | Thực thi logic Java thông qua phương thức task | Sinh mảng `SqlStatement` cho Liquibase |
| Kết quả chính | Side effect do code thực hiện | Câu lệnh SQL do Liquibase thực thi |
| Phù hợp | Tác vụ cần điều phối hoặc xử lý Java không biểu diễn tốt bằng SQL | SQL đặc thù hoặc cần tạo statement theo DBMS |
| Khả năng xem trước | Không thể hiện đầy đủ hành vi Java trong SQL preview | Có thể sinh SQL preview từ statement đã tạo |
| Rollback | Cần định nghĩa hành vi task hoàn tác riêng | Có thể sinh statement rollback riêng |
| Kiểm thử | Cần test logic Java, transaction và side effect | Cần test statement sinh ra và SQL trên DBMS thật |
| Rủi ro chính | Hành vi ẩn, khó quan sát, side effect ngoài SQL | SQL đặc thù, khác biệt DBMS và rollback sai |

Cả hai đều là custom change được khai báo trong changeset. Chúng vẫn tham gia lịch sử changeset của Liquibase, nhưng không có cùng khả năng quan sát và quản lý SQL.

**Quy tắc chọn nhanh:**
- Nếu có thể diễn đạt thay đổi bằng change type chuẩn, ưu tiên change type chuẩn.
- Nếu cần SQL mà Liquibase chưa có change type tương ứng, cân nhắc SQL thuần hoặc CustomSqlChange.
- Chỉ dùng CustomTaskChange khi thực sự cần logic Java thực thi trực tiếp và chấp nhận được giới hạn về SQL preview, tính portable và vận hành.
- Không chọn CustomTaskChange chỉ để bọc một câu INSERT/UPDATE/DDL đơn giản.

## 2. Vòng đời chung của một custom change

Một custom change được Liquibase khởi tạo và cấu hình như một phần của quá trình đọc changelog. Hợp đồng `CustomChange` cung cấp các bước chuẩn bị, cấp resource accessor, validation và confirmation message; loại cụ thể bổ sung phần thực thi task hoặc sinh SQL.

Ở mức khái niệm, vòng đời gồm:

1. Liquibase đọc changelog và nhận diện `customChange`.
2. Khởi tạo class được khai báo.
3. Gán các tham số cấu hình từ changelog vào thuộc tính tương ứng.
4. Gọi phần setup và cấp ResourceAccessor theo API phiên bản đang dùng.
5. Gọi validate để phát hiện cấu hình không hợp lệ trước khi chạy.
6. Đối với CustomSqlChange, gọi generateStatements để lấy danh sách statement.
7. Đối với CustomTaskChange, gọi execute để thực hiện tác vụ Java.
8. Ghi nhận changeset theo cơ chế lịch sử của Liquibase nếu quá trình hoàn tất.
9. Khi rollback, gọi logic hoàn tác được hỗ trợ hoặc rollback block đã khai báo.

Các phương thức cụ thể và lớp base có thể khác theo phiên bản Liquibase. Khi phát triển extension, cần biên dịch và kiểm thử theo đúng phiên bản Liquibase được pin trong CLI và ứng dụng.

## 3. Hợp đồng CustomChange

Hai loại custom change thường kế thừa lớp base tương ứng:
- `AbstractCustomTaskChange` cho task.
- `AbstractCustomSqlChange` cho SQL.

Lớp base giúp triển khai các phương thức vòng đời chung của `CustomChange`. Class vẫn cần định nghĩa phần hành vi chính và có thể override validation, setup hoặc confirmation message khi cần.

Hợp đồng chung có các trách nhiệm:
- **Setup:** kiểm tra và chuẩn bị cấu hình của custom change.
- **Resource access:** truy cập tài nguyên được Liquibase cung cấp nếu cần.
- **Validation:** kiểm tra tham số, định dạng và điều kiện đầu vào.
- **Confirmation:** cung cấp thông điệp xác nhận có ý nghĩa sau khi chạy.
- **Execution/generation:** thực thi task hoặc sinh SQL statement.

Không đặt logic nghiệp vụ quan trọng trong constructor. Việc tạo object có thể xảy ra trong giai đoạn parse/validation hoặc nhiều lần tùy quy trình; constructor nên đơn giản, không kết nối database, không ghi dữ liệu và không gọi dịch vụ ngoài.

## 4. CustomTaskChange: thực thi một tác vụ Java

`CustomTaskChange` phù hợp khi cần thực hiện logic Java mà không thể mô tả hợp lý bằng một tập SQL statement được Liquibase quản lý. Ví dụ:
- Chuyển đổi dữ liệu có thuật toán Java phức tạp và phạm vi nhỏ.
- Đọc resource đã đóng gói cùng artifact và biến đổi dữ liệu theo quy tắc rõ ràng.
- Thực hiện một thao tác quản trị đặc thù thông qua API database được hỗ trợ.
- Điều phối một tác vụ nội bộ có thể quan sát và kiểm soát trong transaction của migration.

Task change có phương thức thực thi nhận đối tượng Database và có thể ném CustomChangeException. Lớp base giúp giảm boilerplate của vòng đời chung.

Ví dụ skeleton:

~~~java
package com.example.database.migration;

import liquibase.change.custom.AbstractCustomTaskChange;
import liquibase.change.custom.CustomTaskRollback;
import liquibase.database.Database;
import liquibase.exception.CustomChangeException;
import liquibase.exception.ValidationErrors;

public final class NormalizeCustomerCode
        extends AbstractCustomTaskChange
        implements CustomTaskRollback {

    private int batchSize = 500;

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    @Override
    public ValidationErrors validate(Database database) {
        ValidationErrors errors = new ValidationErrors();
        if (batchSize <= 0 || batchSize > 5000) {
            errors.addError("batchSize must be between 1 and 5000");
        }
        return errors;
    }

    @Override
    public void execute(Database database) throws CustomChangeException {
        // Thực hiện logic Java bằng API Liquibase phù hợp phiên bản.
        // Chia phạm vi xử lý theo batchSize, có điều kiện dừng rõ ràng.
        // Không tự commit/rollback transaction do Liquibase quản lý.
    }

    @Override
    public void rollback(Database database) throws CustomChangeException {
        // Chỉ hoàn tác nếu có thể xác định chính xác dữ liệu cần khôi phục.
        // Nếu không thể khôi phục, phải thiết kế forward-fix/restore riêng.
    }

    @Override
    public String getConfirmationMessage() {
        return "Customer codes normalized in controlled batches";
    }
}
~~~

Đây là skeleton minh họa hợp đồng và trách nhiệm, không phải implementation xử lý dữ liệu hoàn chỉnh. Phương thức `validate(Database)` trả về ValidationErrors để Liquibase kiểm tra tham số trước khi thực thi; cách tạo lỗi validation cụ thể cần đối chiếu với API của phiên bản đang pin.

Một task change tốt phải có giới hạn rõ: tập bản ghi, điều kiện chọn, batch size, cách resume, lỗi được phép retry và tiêu chí xác nhận hoàn tất. Nếu tác vụ cần chạy hàng giờ hoặc phải điều tiết tải độc lập, một job dữ liệu riêng thường phù hợp hơn việc giữ một migration process lâu.

## 5. CustomSqlChange: sinh SqlStatement cho Liquibase

`CustomSqlChange` phù hợp khi muốn dùng Java để tạo ra các statement nhưng vẫn để Liquibase quản lý việc thực thi chúng. Phương thức chính là `generateStatements(Database database)`, trả về một mảng `SqlStatement`.

Ví dụ tạo một index bằng SQL đặc thù:

~~~java
package com.example.database.migration;

import liquibase.change.custom.AbstractCustomSqlChange;
import liquibase.change.custom.CustomSqlRollback;
import liquibase.database.Database;
import liquibase.exception.CustomChangeException;
import liquibase.statement.SqlStatement;
import liquibase.statement.core.RawSqlStatement;

public final class CreateCustomerSearchIndex
        extends AbstractCustomSqlChange
        implements CustomSqlRollback {

    @Override
    public SqlStatement[] generateStatements(Database database)
            throws CustomChangeException {
        if (!"postgresql".equalsIgnoreCase(database.getShortName())) {
            throw new CustomChangeException(
                "This custom change supports PostgreSQL only"
            );
        }

        return new SqlStatement[] {
            new RawSqlStatement(
                "CREATE INDEX ix_customer_email_lower " +
                "ON app.customer (lower(email))"
            )
        };
    }

    @Override
    public SqlStatement[] generateRollbackStatements(Database database)
            throws CustomChangeException {
        return new SqlStatement[] {
            new RawSqlStatement(
                "DROP INDEX IF EXISTS app.ix_customer_email_lower"
            )
        };
    }
}
~~~

Ví dụ minh họa việc sinh statement cho PostgreSQL. Trong production cần xác minh cú pháp drop index, schema qualification, transaction behavior và yêu cầu online/concurrently theo DBMS/version. Nếu sử dụng `CREATE INDEX CONCURRENTLY`, cần xử lý yêu cầu chạy ngoài transaction và trạng thái index sau khi bị gián đoạn; không chỉ thay câu CREATE INDEX mà bỏ qua semantics đó.

CustomSqlChange có ưu điểm là statement nằm trong luồng thực thi SQL của Liquibase. Điều này thường giúp update-sql tạo được SQL preview và cho phép review câu lệnh trước deployment. Tuy nhiên, khả năng sinh preview thực tế còn phụ thuộc statement, database implementation và phiên bản Liquibase. Phải kiểm tra output bằng CLI đã pin; không suy ra rằng mọi code Java trong custom change đều có thể preview.

## 6. Khai báo custom change trong changelog

Custom change được tham chiếu bằng tên class trong changeset. Ví dụ XML:

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261120-001-normalize-customer-code"
               author="team-db">
        <customChange class="com.example.database.migration.NormalizeCustomerCode">
            <param name="batchSize" value="500"/>
        </customChange>
    </changeSet>
</databaseChangeLog>
~~~

Liquibase ánh xạ parameter vào thuộc tính Java tương ứng theo cơ chế bean/property của phiên bản. Tên parameter, setter và kiểu dữ liệu cần khớp. Nếu class không có setter hoặc tên không đúng, validation/khởi tạo có thể thất bại.

Với XML, khai báo custom change được thể hiện tường minh. YAML/JSON có thể dùng cấu trúc customChange tương ứng của parser và phiên bản; hãy xác minh cú pháp bằng một changelog test trong đúng toolchain. Không sao chép cấu trúc YAML suy đoán vào production.

Các tham số nên:
- Có default hợp lý nếu an toàn.
- Được validate trước khi thực thi.
- Có giới hạn trên/dưới.
- Không chứa password/token.
- Không lấy trực tiếp từ dữ liệu request hoặc người dùng cuối.
- Được ghi nhận trong manifest khi ảnh hưởng kết quả migration.

## 7. Khả năng rollback của CustomTaskChange

Liquibase không thể tự suy ra cách đảo ngược một chương trình Java tùy ý. Nếu task thay đổi dữ liệu hoặc schema, cần cung cấp hành vi hoàn tác bằng hợp đồng rollback tương ứng, thường là `CustomTaskRollback`.

Task rollback phải trả lời:
- Có lưu được giá trị trước thay đổi không?
- Có thể xác định chính xác những hàng do task đã sửa không?
- Có thể phân biệt dữ liệu mới phát sinh sau migration không?
- Có thể chạy rollback nhiều lần an toàn không?
- Có phụ thuộc vào resource hoặc service bên ngoài đã thay đổi không?
- Có thể phục hồi trong cùng transaction hay cần quy trình riêng?

Ví dụ, task chuẩn hóa mã khách hàng từ chữ thường sang chữ hoa không thể khôi phục nguyên trạng nếu trước đó có nhiều biểu diễn khác nhau và không lưu giá trị gốc. Việc gọi `toUpperCase()` không có phép đảo ngược duy nhất.

Một cách an toàn hơn là ghi nhận giá trị cũ vào bảng staging/audit có phạm vi và retention rõ trước khi chuyển đổi, hoặc tạo một mapping đủ để rollback. Nhưng bảng phụ và dữ liệu lưu tạm cũng cần changeset, quyền, cleanup và kiểm thử.

Nếu không thể hoàn tác chính xác, đừng tuyên bố rollback hỗ trợ. Hãy ghi rõ thay đổi không đảo ngược và xác định forward fix hoặc restore từ backup là phương án recovery.

## 8. Khả năng rollback của CustomSqlChange

CustomSqlChange có thể cung cấp statement hoàn tác thông qua hợp đồng `CustomSqlRollback`, thường với phương thức sinh rollback statements. Liquibase có thể sử dụng các statement này khi tạo hoặc thực thi rollback theo phiên bản hỗ trợ.

Ví dụ logic:
- Forward: CREATE INDEX.
- Rollback: DROP INDEX.
- Forward: ADD COLUMN.
- Rollback: DROP COLUMN, nhưng dữ liệu đã ghi vào cột sẽ mất.
- Forward: INSERT reference row.
- Rollback: DELETE row, nhưng chỉ an toàn nếu row chưa được ứng dụng sử dụng hoặc thay đổi.

Rollback SQL phải phản ánh tác động thực tế, không chỉ đảo ngược cú pháp. Một câu DROP có thể đảo CREATE về cấu trúc nhưng không khôi phục dữ liệu đã bị xóa. Một câu ADD COLUMN có rollback DROP COLUMN nhưng không bảo toàn giá trị đã được ghi.

Nếu SQL change sinh nhiều statement, rollback cần đảo dependency theo thứ tự ngược. Nếu statement thứ ba thất bại sau khi hai statement đầu thành công và DBMS không hỗ trợ transactional DDL, trạng thái có thể là một phần. Phải test failure ở giữa chuỗi.

## 9. Phân biệt rollback tự động và rollback tùy biến

Liquibase có thể tự sinh rollback cho một số change type chuẩn có inverse rõ ràng. Custom change không nên kỳ vọng cơ chế đó tự hiểu Java code hoặc SQL được sinh động.

Các trường hợp:

| Loại change | Cách hoàn tác |
|---|---|
| Change type chuẩn có inverse | Liquibase có thể sinh rollback tự động |
| CustomTaskChange có CustomTaskRollback | Code cung cấp thao tác rollback Java |
| CustomSqlChange có CustomSqlRollback | Code cung cấp SqlStatement rollback |
| Custom change có rollback block trong changelog | Changelog mô tả change/SQL hoàn tác theo cú pháp hỗ trợ |
| Thay đổi không đảo ngược | Forward fix, restore hoặc quy trình bù trừ |

Không khai báo đồng thời nhiều cơ chế rollback gây xung đột hoặc thực hiện cùng một hành động hai lần. Chọn một nguồn định nghĩa rollback rõ ràng và test bằng rollback-sql/rollback trên database dùng một lần.

Cần kiểm tra API và ưu tiên rollback theo tài liệu phiên bản đang dùng; không giả định mọi phiên bản hỗ trợ cùng cách kết hợp interface, rollback block và custom change.

## 10. Transaction boundary và quản lý kết nối

Liquibase thường quản lý transaction của changeset theo cấu hình và khả năng DBMS. Custom change cần tôn trọng transaction boundary đó.

Không nên:
- Tự gọi commit trên connection do Liquibase quản lý.
- Tự rollback transaction bên ngoài khi chưa hiểu executor.
- Mở connection thứ hai tới database mà không có lý do.
- Giữ transaction lâu cho tác vụ xử lý dữ liệu lớn.
- Để một phần side effect nằm ngoài transaction mà không có recovery.
- Bắt exception rồi trả về thành công.
- Đóng connection do Liquibase sở hữu.

Với CustomSqlChange, Liquibase nhận các SqlStatement và điều phối thực thi. Đây thường là lựa chọn tốt hơn khi công việc có thể biểu diễn bằng SQL.

Với CustomTaskChange, nếu phải truy cập database, hãy dùng API Liquibase được hỗ trợ cho phiên bản mục tiêu và tuân theo quản lý connection/transaction của nó. Nếu phải dùng JDBC trực tiếp, xác định rõ connection ownership, resource cleanup, parameter binding, transaction và exception mapping; không lấy connection rồi tự commit tùy tiện.

Một task có side effect ngoài transaction database — ghi file, gọi HTTP, gửi message — không thể được rollback tự động chỉ vì transaction DB rollback. Tránh các side effect này trong migration; nếu bắt buộc, cần thiết kế idempotency, outbox/compensation và runbook riêng.

## 11. Idempotency và khả năng chạy lại

Liquibase đánh dấu changeset đã chạy để tránh thực thi lại trong các lần update bình thường. Tuy nhiên, lỗi giữa chừng, transaction không nguyên tử, thao tác DBA hoặc retry thủ công có thể tạo trạng thái không như mong đợi.

Custom change nên được thiết kế để:
- Có thể phát hiện trạng thái đã hoàn tất.
- Không tạo dữ liệu trùng khi retry được cho phép.
- Dùng khóa duy nhất hoặc điều kiện cập nhật phù hợp.
- Có checkpoint nếu xử lý nhiều batch.
- Ghi nhận tiến độ ở nơi có thể kiểm toán.
- Phân biệt lỗi tạm thời và lỗi vĩnh viễn.
- Không tiếp tục từ trạng thái không rõ.

Không thêm `runAlways` hoặc `runOnChange` để chữa một custom change không idempotent. Hai thuộc tính này làm thay đổi quy tắc thực thi và cần có lý do riêng. Một custom change chạy lại ngoài dự kiến có thể gửi thông báo trùng, ghi file lặp hoặc biến đổi dữ liệu lần thứ hai.

## 12. CustomTaskChange không thay thế job backfill dài hạn

Một task Java chạy trong Liquibase có thể giữ tiến trình migration và lock trong suốt thời gian thực thi. Với bảng lớn, điều này có thể:
- Giữ transaction lâu.
- Tạo lock contention.
- Làm tăng WAL/redo/transaction log.
- Gây replication lag.
- Vượt timeout của CI/CD hoặc startup.
- Khó pause/resume.
- Khó điều tiết tải.
- Làm rollback tốn kém.

Nếu backfill cần hàng triệu bản ghi, checkpoint, throttling, progress metrics và resume, hãy cân nhắc job dữ liệu riêng. Liquibase quản lý schema trước/sau job và dùng changeset/precondition để kiểm tra trạng thái hoàn tất.

CustomTaskChange phù hợp hơn với thao tác ngắn, có phạm vi nhỏ, xác định và có thể kiểm chứng trong thời gian migration được phép.

## 13. So sánh khả năng update-sql và review

Đây là điểm khác biệt quan trọng:

- CustomSqlChange sinh `SqlStatement[]`, do đó Liquibase có thể render statement thành SQL theo DBMS. Reviewer có thể xem output update-sql nếu statement và executor hỗ trợ.
- CustomTaskChange chạy logic Java. Một chương trình Java có thể đọc dữ liệu, phân nhánh và gọi API; không thể chuyển toàn bộ hành vi đó thành một file SQL preview tổng quát.
- Vì vậy, SQL preview không phải bằng chứng đầy đủ cho CustomTaskChange.
- Nếu task change được dùng, cần bổ sung review code, test result, configuration manifest, log, metrics và post-check.

Trong pipeline, nếu policy yêu cầu mọi thay đổi phải có SQL preview đầy đủ, CustomTaskChange có thể không phù hợp. Khi đó hãy chuyển logic sang CustomSqlChange, SQL changeset hoặc job riêng có bằng chứng tương ứng.

Không chấp nhận một file update-sql rỗng hoặc thiếu phần task như bằng chứng rằng custom task không có tác động. Phải xác định rõ command đã render gì và hành vi nào chỉ xảy ra lúc update.

## 14. Chọn CustomSqlChange thay vì SQL thuần khi nào?

CustomSqlChange có thể có ích khi:
- Cần sinh statement dựa trên Database object/DBMS.
- Cần tái sử dụng một quy tắc sinh SQL trong nhiều changelog.
- Cần kiểm tra cấu hình Java trước khi tạo statement.
- Cần một abstraction nội bộ có contract ổn định và được nhiều dự án sử dụng.

SQL thuần thường đơn giản hơn khi chỉ có một câu lệnh rõ ràng. CustomSqlChange tạo thêm:
- Java class và dependency.
- Cơ chế nạp extension.
- Unit/integration tests.
- Version compatibility.
- Quy trình packaging cho CLI và Spring Boot.
- Rollback implementation.
- Tài liệu và ownership.

Nếu custom class chỉ trả về một RawSqlStatement cố định, hãy cân nhắc dùng change type chuẩn hoặc `sql` trực tiếp. Chỉ giữ abstraction nếu lợi ích tái sử dụng hoặc kiểm soát DBMS đủ lớn.

## 15. Validation tham số và lỗi có chủ đích

Custom change nên từ chối input không hợp lệ trước khi bắt đầu thay đổi.

Ví dụ tham số:
- batchSize phải lớn hơn 0 và nằm trong giới hạn.
- schema/table identifier phải nằm trong allowlist.
- file/resource phải tồn tại trong artifact.
- giá trị enum phải thuộc tập được hỗ trợ.
- DBMS/version phải nằm trong compatibility matrix.

Validation không nên kết nối mạng, sửa dữ liệu hoặc có side effect. Nó phải trả lỗi cụ thể để người review biết tham số nào sai.

Khi thực thi, ném CustomChangeException với nguyên nhân có thể điều tra. Không bắt exception rộng rồi chỉ log WARN và trả về bình thường, vì Liquibase có thể ghi nhận changeset thành công dù công việc chưa hoàn tất.

Thông báo lỗi cần tránh chứa password, token, dữ liệu cá nhân hoặc toàn bộ SQL literal nhạy cảm. Ghi changeset identity và deployment ID trong log để liên kết sự cố.

## 16. Xử lý DBMS khác nhau

CustomSqlChange nhận đối tượng Database, có thể dùng thông tin DBMS để sinh statement phù hợp. Nhưng việc phân nhánh phải minh bạch.

Ví dụ:
- PostgreSQL dùng expression index.
- MySQL có cú pháp/giới hạn index khác.
- SQL Server có filtered index và cách quoting riêng.
- Oracle có cơ chế sequence/identity và DDL behavior riêng.

Không tạo một chuỗi SQL "gần giống nhau" rồi gửi cho mọi engine. Hãy:
1. Xác định DBMS được hỗ trợ.
2. Sinh statement rõ cho từng engine.
3. Từ chối DBMS không được hỗ trợ.
4. Có integration test trên từng DBMS/version.
5. So sánh semantics cuối cùng, không chỉ so sánh cú pháp.

Nếu có thể dùng change type chuẩn và Liquibase đã xử lý khác biệt, tránh tự viết DBMS branch.

## 17. Resource, classpath và packaging

Custom change class phải có mặt trong classpath của tiến trình chạy Liquibase:
- Liquibase CLI.
- Spring Boot application nếu migration chạy lúc startup.
- CI/CD migration container/job.
- Test runtime.
- Công cụ rollback hoặc update-sql.

Một class có trong application JAR nhưng không có trong CLI runner sẽ khiến pipeline không nạp được custom change. Ngược lại, CLI có extension nhưng application runtime thiếu nó sẽ gây lỗi nếu Spring Boot tự chạy migration.

Cần:
- Pin Liquibase version.
- Pin extension version.
- Quản lý dependency transitive.
- Build artifact reproducible.
- Kiểm tra classpath thực tế.
- Không tải class hoặc JAR động từ nguồn không tin cậy.
- Chạy test từ artifact đóng gói, không chỉ từ IDE.
- Có quy trình nâng cấp API extension.

Không đổi implementation của custom change đã được dùng trong changeset cũ mà không đánh giá checksum và semantics. Dù class Java đổi nhưng changelog text không đổi, hành vi thực thi có thể đổi mà checksum changeset không phản ánh thay đổi code. Đây là lý do phải pin version extension và ghi artifact digest.

## 18. Bảo vệ tính bất biến và checksum

Liquibase checksum phản ánh nội dung changeset theo thuật toán/phiên bản, nhưng không phải chữ ký của Java class hay dependency.

Vì vậy:
- Changeset đã triển khai phải bất biến.
- Custom extension cần version rõ.
- Artifact extension cần digest.
- Migration release phải pin dependency.
- Không thay JAR cùng version sau khi đã phát hành.
- Không dùng clear-checksums để che thay đổi implementation.
- Log cần ghi Liquibase/extension version.
- Rollback phải dùng đúng artifact/API tương thích.

Một thay đổi code custom change có thể làm cùng một changeset tạo SQL hoặc side effect khác dù nội dung changelog không đổi. Quản lý version extension là một phần của quản lý lịch sử migration.

## 19. Thiết kế rollback cho dữ liệu biến đổi

Với data migration, rollback thường khó hơn DDL. Ví dụ:
- Chuẩn hóa email có thể làm mất cách viết ban đầu.
- Gộp hai cột thành một có thể làm mất ranh giới dữ liệu.
- Mã hóa dữ liệu cần giữ khóa và version thuật toán.
- Xóa bản ghi trùng có thể không xác định bản ghi nào cần phục hồi.
- Chuyển trạng thái có thể bị ứng dụng cập nhật tiếp sau migration.

Trước khi viết rollback, phân loại:
1. **Reversible:** có phép biến đổi nghịch đảo chính xác.
2. **Reversible with retained source:** có thể phục hồi nếu giữ giá trị cũ.
3. **Compensating:** không đảo ngược đúng từng thao tác nhưng có hành động bù nghiệp vụ.
4. **Irreversible:** phải forward-fix hoặc restore.

Không đánh đồng rollback với compensation. Một hành động gửi email không thể "unsend" bằng rollback; một sự kiện đã publish có thể cần sự kiện bù. CustomTaskChange không nên làm các side effect này trong migration nếu không có cơ chế điều phối độc lập.

## 20. Test rollback theo failure point

Không chỉ test một lần rollback thành công sau khi changeset hoàn tất. Cần thử các tình huống:
- Lỗi trước khi thay đổi dữ liệu.
- Lỗi giữa hai batch.
- Lỗi sau khi một statement đã thành công.
- Lỗi khi ghi history.
- Mất kết nối khi task đang chạy.
- Process bị kill.
- Rollback được gọi hai lần.
- Rollback sau khi ứng dụng đã ghi dữ liệu mới.
- Rollback trên từng DBMS hỗ trợ.

Với DBMS có DDL transaction behavior khác nhau, test phải phản ánh đúng engine. Không dựa vào H2 để kết luận rollback trên PostgreSQL/MySQL/Oracle.

Nếu task chạy nhiều batch và commit theo từng batch, transaction changeset không còn đại diện cho toàn bộ công việc. Cần lưu checkpoint và có cơ chế resume/compensation; rollback phải biết batch nào đã hoàn tất.

## 21. Kiểm thử CustomSqlChange

Một bộ test nên gồm:
- Database giả lập hoặc mock để kiểm tra nhánh chọn DBMS khi phù hợp.
- Test generateStatements trả đúng số lượng và nội dung statement.
- Test parameter validation.
- Test DBMS không hỗ trợ bị từ chối.
- Test update-sql output.
- Integration test thực thi trên DBMS thật.
- Test rollback statements.
- Test trạng thái sau khi statement thứ hai thất bại.
- Test schema/data assertions.
- Test đóng gói trong CLI và Spring Boot.

Không chỉ assert chuỗi SQL. Kiểm tra kết quả database cuối cùng: index có tồn tại với đúng columns/expressions không, constraint có đúng semantics không và rollback có thực sự xóa đúng object không.

## 22. Kiểm thử CustomTaskChange

Với task change, cần test:
- Setup và parameter mapping.
- Validation trước khi thực thi.
- Tập bản ghi được chọn.
- Batch boundary và checkpoint.
- Idempotency/retry.
- Transaction behavior.
- Resource cleanup.
- Exception mapping.
- Rollback hoặc compensation.
- Không tạo side effect ngoài phạm vi.
- Log/metric/progress.
- Process interruption.
- DBMS/version compatibility.

Dùng database integration test có dữ liệu đại diện. Với dữ liệu nhạy cảm, fixture phải được tổng hợp hoặc mask. Test cần xác minh số hàng và nội dung, không chỉ kiểm tra phương thức execute không ném exception.

## 23. Khai báo rollback và kiểm tra bằng Liquibase

Sau khi custom change được khai báo, chạy các lệnh kiểm tra theo phiên bản:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase rollback-sql --tag=before-custom-change
~~~

Tên option và rollback target phải khớp phiên bản CLI và tag thực tế. `rollback-sql` sinh SQL dự kiến cho rollback; nó không thực hiện rollback.

Với CustomTaskChange, rollback logic Java không nhất thiết được biểu diễn thành SQL trong rollback-sql. Cần test hành vi rollback thực tế trên database cô lập. Không duyệt rollback chỉ dựa vào một file SQL nếu task còn có logic Java ngoài SQL.

Sau khi chạy update trên database test:
1. Đọc log.
2. Đối chiếu DATABASECHANGELOG.
3. Kiểm tra schema và dữ liệu.
4. Chạy rollback.
5. Xác minh trạng thái sau rollback.
6. Dựng lại database và chạy update lại.
7. Kiểm tra artifact extension/version được sử dụng.

## 24. Ví dụ lựa chọn: tạo index hay chuẩn hóa dữ liệu?

**Tình huống A — Tạo expression index:** cần index `lower(email)` trên PostgreSQL. Đây là SQL được sinh theo DBMS và có rollback là DROP INDEX. CustomSqlChange có thể phù hợp nếu logic tạo statement được tái sử dụng; một SQL changeset có dbms filter có thể còn đơn giản hơn.

**Tình huống B — Chuẩn hóa mã dữ liệu nhỏ:** cần chuyển một tập giá trị theo thuật toán Java đã xác định, có mapping cũ/mới và có thể phục hồi. CustomTaskChange có thể phù hợp nếu task ngắn, giới hạn phạm vi, có transaction/recovery rõ và test kỹ.

**Tình huống C — Backfill hàng chục triệu bản ghi:** cần checkpoint, throttle, resume và theo dõi tiến độ. Job dữ liệu riêng thường phù hợp hơn. Liquibase có thể quản lý các thay đổi schema và điều kiện xác nhận trước/sau job.

**Tình huống D — Thêm một cột:** dùng addColumn chuẩn. Không cần viết custom class.

## 25. Các anti-pattern cần tránh

- Dùng CustomTaskChange cho một câu SQL đơn giản.
- Gọi HTTP/API ngoài trong migration mà không có compensation.
- Tự commit connection do Liquibase quản lý.
- Bắt exception rồi coi task thành công.
- Tạo SQL từ parameter không được allowlist.
- Để task chạy toàn bảng không có batch hoặc checkpoint.
- Không triển khai CustomTaskRollback/CustomSqlRollback nhưng vẫn tuyên bố rollback được hỗ trợ.
- Rollback xóa dữ liệu mới mà không cảnh báo.
- Thay implementation extension nhưng giữ version/artifact identity cũ.
- Chỉ test trên H2.
- Chỉ kiểm tra SQL preview mà không test hành vi task.
- Dùng CustomSqlChange cho SQL cố định chỉ để tăng abstraction.
- Không đóng gói extension vào CLI/CI runtime.
- Sửa changeset cũ để đổi logic custom change.
- Đưa task có side effect không thể đảo ngược vào startup migration.

## 26. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy custom class | Extension thiếu trong classpath | Kiểm tra dependency CLI/Spring Boot/job |
| Không gán được parameter | Thiếu setter hoặc sai tên/kiểu | Kiểm tra changelog và bean properties |
| Validation không chạy như mong đợi | Override sai API/phiên bản | Đối chiếu CustomChange contract |
| update-sql thiếu tác động task | CustomTaskChange chạy Java trực tiếp | Bổ sung review code, test và evidence riêng |
| SQL preview khác execution | DBMS/config/extension version khác | Pin và đối chiếu manifest |
| Rollback không tìm thấy | Thiếu rollback interface hoặc khai báo không đúng | Implement rollback contract và test |
| Rollback chạy nhưng dữ liệu sai | Phép biến đổi không có inverse chính xác | Giữ source value hoặc forward recovery |
| Task chạy quá lâu | Công việc dữ liệu quá lớn | Chuyển thành job riêng có batch/checkpoint |
| Task bị chạy lại | Retry hoặc history chưa ghi nhận | Kiểm tra trạng thái và thiết kế idempotency |
| Một phần DDL còn sau lỗi | DBMS không rollback DDL nguyên tử | Reconcile object và kiểm tra history |
| CLI chạy, Spring Boot lỗi | Classpath/version khác | Kiểm thử từ artifact và runtime thật |
| Nâng Liquibase làm extension lỗi | API/Java compatibility thay đổi | Pin version và chạy compatibility matrix |

Khi lỗi xảy ra, bảo toàn log và database state trước khi retry. Không xóa DATABASECHANGELOG hoặc force release lock để che trạng thái chưa rõ.

## 27. Bài thực hành: xây custom change có rollback

**Bối cảnh:** một hệ thống cần chuẩn hóa mã customer cũ thành dạng chữ hoa. Tập dữ liệu nhỏ, quy tắc chuyển đổi xác định và cần lưu lại giá trị gốc để có thể phục hồi.

### Phần A — Thiết kế

1. Xác định phạm vi bản ghi cần xử lý.
2. Xác định quy tắc chuyển đổi và dữ liệu ngoại lệ.
3. Thiết kế nơi lưu giá trị cũ có khóa liên kết và release ID.
4. Chọn CustomTaskChange vì cần logic Java đã xác định.
5. Chọn CustomTaskRollback để khôi phục từ giá trị gốc.
6. Xác định transaction boundary và giới hạn số bản ghi.

### Phần B — Triển khai

1. Tạo class kế thừa AbstractCustomTaskChange.
2. Khai báo parameter có setter và validation.
3. Thực thi theo phạm vi được chỉ định.
4. Lưu giá trị gốc trước khi cập nhật.
5. Không tự commit transaction.
6. Ném CustomChangeException nếu có lỗi.
7. Implement rollback chỉ phục hồi bản ghi thuộc đúng release.
8. Ghi confirmation message rõ ràng.

### Phần C — Changelog và kiểm thử

1. Khai báo customChange trong changeset.
2. Chạy validate.
3. Kiểm tra parameter mapping.
4. Chạy trên database test có dữ liệu biên.
5. Kiểm tra log và DATABASECHANGELOG.
6. Chạy rollback trên database có thể khôi phục.
7. Xác minh dữ liệu bằng đúng giá trị ban đầu.
8. Mô phỏng lỗi giữa chừng và chạy lại theo quy trình.
9. Test trên DBMS/version được hỗ trợ.
10. Kiểm tra extension được đóng gói trong CLI và CI job.

### Phần D — Đánh giá

1. Nếu task không thể lưu giá trị gốc, rollback còn chính xác không?
2. Nếu app thay đổi bản ghi sau migration, rollback có ghi đè dữ liệu mới không?
3. Nếu task bị dừng giữa batch, làm sao biết bản ghi nào đã xử lý?
4. Nếu database không hỗ trợ transactional DDL, trạng thái sau lỗi được reconcile thế nào?
5. Nếu update-sql không biểu diễn được task, pipeline sẽ lưu bằng chứng nào?
6. Khi dữ liệu tăng lên hàng triệu hàng, có nên chuyển sang job riêng không?

### Câu hỏi tự kiểm tra

- CustomTaskChange thực hiện điều gì? **Chạy logic Java trực tiếp trong tiến trình Liquibase.**
- CustomSqlChange thực hiện điều gì? **Sinh SqlStatement để Liquibase thực thi.**
- Loại nào thường phù hợp hơn cho SQL preview? **CustomSqlChange**, vì statement có thể được render; vẫn cần xác minh bằng phiên bản/DBMS thực tế.
- Liquibase tự suy ra rollback cho code Java tùy ý không? **Không.** Cần rollback contract hoặc phương án recovery rõ.
- CustomTaskRollback và CustomSqlRollback khác nhau thế nào? **Một loại hoàn tác bằng task Java; loại kia sinh statement SQL để hoàn tác.**
- Vì sao không tự commit connection? **Vì có thể phá transaction boundary và làm trạng thái history/schema không nhất quán.**
- Vì sao extension cần pin version? **Vì code Java có thể thay đổi hành vi của changeset dù changelog checksum không đổi.**
- Khi nào nên dùng job riêng? **Khi backfill dài, cần checkpoint, throttle, resume hoặc có side effect ngoài transaction.**

## 28. Checklist trước khi đưa custom change vào production

**Lựa chọn**
- [ ] Đã xem xét change type chuẩn và SQL thuần.
- [ ] Đã giải thích lý do cần CustomTaskChange hoặc CustomSqlChange.
- [ ] Phạm vi và side effect được mô tả.
- [ ] Không dùng custom change chỉ để bọc thao tác đơn giản.

**Implementation**
- [ ] Dùng đúng API của phiên bản Liquibase đã pin.
- [ ] Parameter có setter và validation.
- [ ] Không có side effect trong constructor/setup/validation.
- [ ] Không log secret hoặc dữ liệu nhạy cảm.
- [ ] Không tự commit/rollback connection Liquibase sở hữu.
- [ ] Exception được truyền về Liquibase khi thao tác thất bại.
- [ ] Resource được đóng đúng ownership.
- [ ] DBMS không hỗ trợ bị từ chối rõ ràng.

**Rollback**
- [ ] CustomTaskChange có CustomTaskRollback nếu cần hoàn tác task.
- [ ] CustomSqlChange có CustomSqlRollback hoặc rollback block phù hợp.
- [ ] Rollback được test trên database thật.
- [ ] Không tuyên bố inverse khi dữ liệu không thể phục hồi.
- [ ] Có forward-fix/restore plan khi rollback không khả thi.
- [ ] Đã test lỗi giữa chừng và retry.

**Kiểm thử và phát hành**
- [ ] Unit test và parameter validation.
- [ ] Generated SQL/update-sql được review nếu áp dụng.
- [ ] Integration test trên DBMS/version mục tiêu.
- [ ] Test fresh install và upgrade.
- [ ] Test transaction, idempotency và failure recovery.
- [ ] Extension được pin và đóng gói trong CLI/CI/Spring Boot cần thiết.
- [ ] Artifact digest và version được ghi nhận.
- [ ] Changeset đã triển khai được giữ bất biến.
- [ ] Có owner và tài liệu vận hành.

**Kết luận:** CustomTaskChange và CustomSqlChange mở rộng Liquibase theo hai hướng khác nhau. CustomTaskChange thực thi Java trực tiếp nên cần đặc biệt chú ý side effect, transaction, idempotency và bằng chứng ngoài SQL preview. CustomSqlChange sinh statement để Liquibase thực thi nên dễ đưa vào luồng review SQL hơn, nhưng vẫn cần SQL theo DBMS, test và rollback chính xác. Khi chọn đúng loại, triển khai rollback contract trung thực, pin extension version và kiểm thử cả failure path, custom change có thể giải quyết nhu cầu đặc thù mà vẫn giữ lịch sử migration có thể kiểm tra và vận hành.
