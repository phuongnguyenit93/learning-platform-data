# DDL implicit commit và thiết kế migration chịu lỗi từng phần trong Oracle

Trong Oracle Database, các câu lệnh DDL (Data Definition Language) như CREATE, ALTER, DROP, TRUNCATE, RENAME và nhiều thao tác định nghĩa object có hành vi commit ngầm. Oracle commit transaction hiện tại trước khi thực thi một DDL hợp lệ, rồi commit phần DDL nếu thao tác thành công. Vì vậy, DDL không thể được gom với các câu DML trước đó vào một transaction duy nhất để rollback toàn bộ bằng ROLLBACK.

Đặc điểm này ảnh hưởng trực tiếp đến cách triển khai schema change. Một migration gồm năm câu DDL và ba bước backfill không phải là một transaction nguyên tử. Nếu bước thứ tư lỗi hoặc deployment process bị dừng giữa chừng, database có thể đã ở trạng thái chỉ áp dụng một phần. Việc chạy lại nguyên script có thể gặp object đã tồn tại, constraint đã được thêm, dữ liệu đã backfill một phần hoặc ứng dụng đang dùng schema mới ở một số bước.

Thiết kế migration an toàn cần giả định rằng lỗi có thể xảy ra sau bất kỳ bước nào. Mỗi bước phải có trạng thái quan sát được, có thể kiểm tra trước khi chạy lại, có checkpoint bền vững và có hành động tiếp tục/khôi phục rõ ràng. Thay đổi schema thường nên được thiết kế theo mô hình expand-contract: mở rộng schema tương thích trước, chuyển ứng dụng và dữ liệu theo từng giai đoạn, rồi mới loại bỏ cấu trúc cũ trong một lần phát hành sau.

Bài học thuộc chủ đề **Thay đổi và nâng cấp** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Quy tắc implicit commit trước và sau DDL.
- Vì sao ROLLBACK không hoàn tác DDL và các DML đã bị commit trước đó.
- Khác biệt giữa atomicity của một DDL và tính nguyên tử của toàn migration.
- Thiết kế migration nhiều bước chịu lỗi từng phần.
- Expand-contract, backward compatibility và thứ tự deploy ứng dụng/schema.
- Migration history, checkpoint, idempotency và retry an toàn.
- Backfill theo batch, validation và cutover.
- DDL lock, online DDL, DDL_LOCK_TIMEOUT và tác động tới workload.
- Rollback so với roll-forward/compensating migration.
- Bài thực hành mô phỏng lỗi giữa migration và tiếp tục từ checkpoint.

## 1. DDL là gì và vì sao implicit commit quan trọng?

DDL thay đổi cấu trúc hoặc metadata của database. Các ví dụ thường gặp:

| Nhóm | Ví dụ |
| --- | --- |
| Tạo object | CREATE TABLE, CREATE INDEX, CREATE VIEW, CREATE SEQUENCE |
| Thay đổi object | ALTER TABLE, ALTER INDEX, ALTER VIEW |
| Xóa/đổi tên | DROP TABLE, DROP INDEX, RENAME |
| Xóa dữ liệu theo cấu trúc | TRUNCATE TABLE |
| Quản lý quyền | GRANT, REVOKE |
| Metadata khác | COMMENT ON, CREATE OR REPLACE PROCEDURE/PACKAGE |

Các câu lệnh này thay đổi dictionary metadata và thường cần database-wide coordination/locks. Oracle không cho phép ứng dụng bao bọc một chuỗi DDL thành transaction user-managed rồi rollback toàn bộ như DML.

### Quy tắc commit ngầm

Với DDL hợp lệ được Oracle thực thi, Oracle thực hiện implicit COMMIT trước khi chạy DDL và COMMIT sau khi DDL thành công. Điều này có hai hệ quả:

1. DML chưa commit trước DDL được commit trước khi DDL bắt đầu.
2. Nếu DDL thành công, thay đổi metadata được commit; ROLLBACK sau đó không hoàn tác DDL.

Nếu DDL thất bại sau khi Oracle đã thực hiện pre-DDL commit, các DML trước đó vẫn đã commit. Không có rollback tự động đưa database về trạng thái trước khi gọi DDL.

### Ví dụ: ROLLBACK không hoàn tác DDL

~~~sql
CREATE TABLE migration_demo (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

INSERT INTO migration_demo(id, note)
VALUES (1, 'created before alter');

ALTER TABLE migration_demo ADD created_at DATE;

ROLLBACK;
~~~

Sau ALTER TABLE, transaction DML trước đó đã bị commit ngầm. ROLLBACK không xóa bảng, không bỏ cột CREATED_AT và không hoàn tác INSERT đã được commit trước DDL.

Có thể kiểm tra:

~~~sql
SELECT * FROM migration_demo;

SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'MIGRATION_DEMO'
ORDER BY column_id;
~~~

### DDL thất bại vẫn có thể đã commit DML trước đó

Ví dụ:

~~~sql
INSERT INTO migration_demo(id, note)
VALUES (2, 'this row may be committed before DDL');

ALTER TABLE migration_demo ADD id NUMBER;
~~~

ALTER TABLE thất bại vì cột ID đã tồn tại. DML trước DDL hợp lệ đã bị commit trước khi Oracle xử lý câu ALTER. Một ROLLBACK tiếp theo không thể khôi phục trạng thái transaction ban đầu.

Điểm cần nhớ: không thiết kế script với giả định rằng nếu câu DDL báo lỗi thì toàn bộ lệnh trước đó sẽ tự rollback.

## 2. Phân biệt atomic DDL và atomic migration

Một DDL đơn lẻ thường được Oracle bảo vệ bằng cơ chế transaction nội bộ để metadata không bị ghi dở dang khi thao tác thất bại. Tuy nhiên, điều đó không tạo ra atomicity cho một chuỗi nhiều DDL/DML do người triển khai ghép lại.

Ví dụ migration:

1. Tạo bảng mới.
2. Thêm cột vào bảng cũ.
3. Tạo index.
4. Backfill dữ liệu.
5. Thêm constraint.
6. Deploy code mới.
7. Xóa cột cũ.

Nếu bước 5 thất bại, các bước 1-4 có thể đã commit và còn tồn tại. Nếu bước 6 deploy thành công nhưng bước 7 thất bại, ứng dụng có thể đang chạy code mới trong khi schema cũ vẫn còn. Đây là trạng thái migration một phần, không nhất thiết là database corruption.

### DDL đơn lẻ và chuỗi migration

| Thuộc tính | Một DDL | Toàn migration nhiều bước |
| --- | --- | --- |
| Transaction user rollback | Không | Không thể rollback toàn chuỗi |
| Có thể dừng giữa các bước | Không áp dụng | Có |
| Có thể đã áp dụng một phần | DDL thất bại thường được xử lý nội bộ | Có, giữa các bước đã commit |
| Cần checkpoint | Thường không cần cho một câu đơn | Cần |
| Cần idempotency/retry | Có thể cần nếu client mất response | Rất cần |
| Rollback | Thường dùng DDL bù hoặc restore | Cần kế hoạch theo từng giai đoạn |

### Timeout không chứng minh DDL chưa chạy

Client có thể mất kết nối hoặc timeout sau khi server đã thực thi DDL nhưng trước khi client nhận được response. Khi kết nối lại, không được mặc định rằng lệnh chưa chạy và chạy lại ngay. Hãy truy vấn data dictionary để xác định object/column/index/constraint đã tồn tại hay chưa, rồi mới quyết định tiếp tục.

## 3. Phân loại thay đổi trước khi thiết kế migration

Trước khi viết script, phân loại từng bước:

| Loại thay đổi | Ví dụ | Rủi ro chính |
| --- | --- | --- |
| Additive DDL | Thêm nullable column, tạo table mới | Lock metadata, tương thích ứng dụng |
| Index DDL | Tạo index, rebuild index | CPU/I/O, lock, space, index status |
| Constraint DDL | Thêm FK/UNIQUE/CHECK/NOT NULL | Validate dữ liệu cũ, lock và lỗi dữ liệu |
| Destructive DDL | DROP column/table, TRUNCATE | Mất khả năng đọc/khôi phục cấu trúc cũ |
| Data migration | UPDATE/INSERT/MERGE backfill | Undo/redo, lock, restartability |
| Application cutover | Đổi code đọc/ghi cột mới | Tương thích phiên bản ứng dụng |
| Cleanup | Xóa cột cũ, index cũ, table cũ | Rollback khó sau khi code cũ không còn |

### Đánh giá từng bước

Với mỗi bước, trả lời:

- Điều kiện trước khi chạy là gì?
- Trạng thái thành công được xác định bằng query nào?
- Nếu client mất kết nối sau lệnh, làm sao biết lệnh đã áp dụng?
- Chạy lại có an toàn không?
- Có thể gây lock hoặc ảnh hưởng workload bao lâu?
- Có cần dung lượng data, index, TEMP, UNDO hoặc REDO bổ sung không?
- Có thể rollback bằng DDL bù không, hay chỉ roll-forward?
- Phiên bản ứng dụng cũ và mới có cùng hoạt động được trong giai đoạn chuyển tiếp không?

## 4. Migration chịu lỗi từng phần: các nguyên tắc cốt lõi

### Nguyên tắc 1: chia migration thành các bước nhỏ

Một migration lớn chứa hàng chục thay đổi khó điều tra và khôi phục. Chia thành các bước có ý nghĩa, mỗi bước có precondition, action, postcondition và checkpoint.

### Nguyên tắc 2: trạng thái phải bền vững

Lưu migration version, step name, trạng thái, thời gian bắt đầu/kết thúc và checksum script vào bảng migration history. Trạng thái này giúp operator biết đã chạy tới đâu sau process crash.

### Nguyên tắc 3: kiểm tra thực tế schema trước khi retry

Không chỉ dựa vào trạng thái runner. Có thể DDL đã thành công nhưng runner chết trước khi cập nhật history. Retry phải so sánh data dictionary với trạng thái mong muốn.

### Nguyên tắc 4: idempotent hoặc có precondition rõ

Một bước idempotent có thể chạy lại mà không tạo thêm thay đổi ngoài dự kiến. Nếu không thể idempotent, script phải phát hiện trạng thái đã áp dụng và dừng với thông báo cụ thể.

### Nguyên tắc 5: tương thích ngược trong giai đoạn chuyển tiếp

Schema mới phải cho phép code cũ tiếp tục chạy cho tới khi toàn bộ application instances được nâng cấp. Không xóa/rename cột cũ ngay trong cùng release với lần đầu code mới được deploy.

### Nguyên tắc 6: ưu tiên roll-forward

Vì DDL đã commit không thể rollback bằng transaction, nhiều migration an toàn hơn khi sửa lỗi bằng một migration tiến tiếp. Rollback cấu trúc chỉ thực hiện khi có DDL bù rõ ràng và dữ liệu chưa bị mất hoặc biến đổi không thể đảo ngược.

### Nguyên tắc 7: đo và giới hạn tác động

Kiểm tra thời gian DDL, lock, redo/undo, index build, validation scan và ảnh hưởng tới workload. Chọn maintenance window hoặc online operation phù hợp với phiên bản và edition.

## 5. Thiết kế bảng migration history

Một bảng history ghi nhận migration đã bắt đầu, hoàn tất hoặc dừng ở bước nào. Bảng này không làm DDL trở thành transactional; nó cung cấp checkpoint bền vững để runner phục hồi.

### Ví dụ cấu trúc

~~~sql
CREATE TABLE schema_migrations (
    migration_id       VARCHAR2(100) PRIMARY KEY,
    checksum           VARCHAR2(128) NOT NULL,
    status             VARCHAR2(20) NOT NULL,
    current_step       VARCHAR2(100),
    started_at         TIMESTAMP WITH TIME ZONE,
    updated_at         TIMESTAMP WITH TIME ZONE,
    completed_at       TIMESTAMP WITH TIME ZONE,
    executed_by        VARCHAR2(128),
    error_code         NUMBER,
    error_message      VARCHAR2(2000),
    CONSTRAINT ck_schema_migrations_status
        CHECK (status IN (
            'STARTED',
            'RUNNING',
            'FAILED',
            'VALIDATED',
            'COMPLETED'
        ))
);
~~~

Tên và cột có thể điều chỉnh theo migration framework. CHECK constraint giới hạn status hợp lệ; cập nhật bảng history là DML nên có thể commit theo transaction riêng.

### Quy tắc sử dụng

- Một migration_id đại diện một migration logic/version.
- Checksum phát hiện file script đã bị thay đổi sau khi chạy ở môi trường khác.
- current_step cho biết bước gần nhất đã ghi nhận.
- STARTED/RUNNING giúp phân biệt migration đang chạy với migration hoàn tất.
- FAILED giữ error_code/error_message và bước lỗi để điều tra.
- COMPLETED chỉ được ghi sau khi postcondition và validation đã đạt.

### Không sửa script cũ sau khi đã chạy ở môi trường

Nếu script version V12 đã chạy ở test/staging/production, không sửa nội dung V12 rồi dùng checksum mới để chạy lại. Tạo migration V13 để thay đổi tiếp. Điều này giữ lịch sử deployment nhất quán giữa môi trường.

### Checkpoint không thay thế kiểm tra schema

Nếu migration history nói step CREATE_INDEX đã hoàn tất nhưng index bị drop thủ công sau đó, runner không được bỏ qua kiểm tra. Ngược lại, nếu index đã được tạo nhưng history vẫn RUNNING do client crash, runner cần phát hiện object đúng định nghĩa và đánh dấu bước hoàn tất.

## 6. Ngăn nhiều migration chạy đồng thời

Hai deployment chạy cùng lúc có thể cùng kiểm tra object chưa tồn tại rồi cùng CREATE, hoặc chạy hai backfill trên cùng tập dữ liệu. Điều này gây race condition, ORA-00955, lock contention hoặc dữ liệu được cập nhật ngoài dự kiến.

### Vì sao SELECT FOR UPDATE không đủ?

Một cách dễ nghĩ tới là tạo một dòng migration lock rồi giữ SELECT FOR UPDATE trong lúc chạy script. Nhưng DDL thực hiện implicit COMMIT, do đó row lock của transaction hiện tại được giải phóng trước khi DDL chạy. Session thứ hai có thể lấy được khóa và bắt đầu migration trong khi session đầu vẫn tiếp tục.

Không dùng transaction row lock trong cùng session làm mutex xuyên suốt một chuỗi DDL.

### Dùng lock ở deployment orchestrator

Nếu migration chạy qua CI/CD hoặc một deployment service, ưu tiên cơ chế concurrency lock của orchestrator:

- Mỗi database/schema có một migration mutex.
- Chỉ một job được chạy migration tại một thời điểm.
- Lock được giữ từ preflight tới khi migration kết thúc hoặc job bị hủy.
- Khi job chết, lock được giải phóng theo cơ chế lease/heartbeat của orchestrator.

### Dùng DBMS_LOCK khi cần mutex trong database

DBMS_LOCK có thể tạo application lock không bị giải phóng bởi commit nếu REQUEST dùng release_on_commit => FALSE. Tài khoản migration cần quyền execute phù hợp.

Ví dụ khái quát:

~~~sql
DECLARE
    l_handle VARCHAR2(128);
    l_result PLS_INTEGER;
BEGIN
    DBMS_LOCK.ALLOCATE_UNIQUE(
        lockname => 'APP_SCHEMA_MIGRATION',
        lockhandle => l_handle
    );

    l_result := DBMS_LOCK.REQUEST(
        lockhandle => l_handle,
        lockmode => DBMS_LOCK.X_MODE,
        timeout => 0,
        release_on_commit => FALSE
    );

    IF l_result NOT IN (0, 4) THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Another schema migration is running; DBMS_LOCK result=' || l_result
        );
    END IF;
END;
/
~~~

Kết quả 0 biểu thị lấy lock thành công; 4 có thể biểu thị session đã sở hữu lock đó. Xác nhận return-code semantics theo phiên bản và cách dùng thực tế.

Lưu ý quan trọng: DBMS_LOCK.ALLOCATE_UNIQUE có thể commit transaction hiện tại. Gọi nó trước khi bắt đầu công việc nghiệp vụ/migration cần transaction, hoặc tạo/đăng ký handle trước trong quy trình setup. Sau migration, gọi DBMS_LOCK.RELEASE trong finally/cleanup path. Nếu process chết, Oracle giải phóng session lock khi session kết thúc.

Ví dụ release:

~~~sql
DECLARE
    l_result PLS_INTEGER;
BEGIN
    l_result := DBMS_LOCK.RELEASE(:lock_handle);
END;
/
~~~

Đoạn release minh họa cần handle thực tế do bước acquire trả về. Không chạy độc lập với bind variable chưa được khởi tạo.

### Lock phải bao trùm toàn bộ lifecycle

Giữ lock qua preflight, DDL, backfill, validation và cutover. Nếu chỉ khóa lúc ghi migration history nhưng nhả trước DDL, vẫn còn race condition. Với DBMS_LOCK, giữ cùng session xuyên suốt và không dùng release_on_commit => TRUE.

## 7. Viết DDL idempotent và kiểm tra trạng thái object

Idempotency nghĩa là chạy lại một bước đã hoàn tất không tạo ra thay đổi sai hoặc lỗi ngoài dự kiến. Oracle không có cú pháp IF NOT EXISTS đồng nhất cho mọi loại DDL ở mọi release, vì vậy nhiều migration dùng PL/SQL kiểm tra dictionary trước khi chạy dynamic SQL.

### Tạo bảng nếu chưa tồn tại

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_tables
    WHERE table_name = 'APP_EVENT';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE TABLE app_event (
                event_id NUMBER PRIMARY KEY,
                event_type VARCHAR2(50) NOT NULL,
                created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
            )
        ]';
    ELSE
        -- Object đã có: xác minh cấu trúc trước khi đánh dấu step hoàn tất.
        SELECT COUNT(*)
        INTO l_count
        FROM user_tab_columns
        WHERE table_name = 'APP_EVENT'
          AND column_name IN ('EVENT_ID', 'EVENT_TYPE', 'CREATED_AT');

        IF l_count <> 3 THEN
            RAISE_APPLICATION_ERROR(
                -20002,
                'APP_EVENT exists with an unexpected structure'
            );
        END IF;
    END IF;
END;
/
~~~

Kiểm tra tên bảng đã tồn tại chưa chỉ là bước đầu. Nếu object cùng tên nhưng khác owner/type/definition, không được xem như migration đã thành công. Kiểm tra đủ cột, datatype, nullability, constraint và default cần thiết.

### Thêm cột nếu chưa có

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_tab_columns
    WHERE table_name = 'CUSTOMERS'
      AND column_name = 'NORMALIZED_EMAIL';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE
            'ALTER TABLE customers ADD (normalized_email VARCHAR2(320))';
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM user_tab_columns
        WHERE table_name = 'CUSTOMERS'
          AND column_name = 'NORMALIZED_EMAIL'
          AND data_type = 'VARCHAR2'
          AND data_length >= 320;

        IF l_count = 0 THEN
            RAISE_APPLICATION_ERROR(
                -20003,
                'NORMALIZED_EMAIL exists with an incompatible definition'
            );
        END IF;
    END IF;
END;
/
~~~

USER_TAB_COLUMNS.DATA_LENGTH tính theo byte hoặc semantics phụ thuộc column definition; với VARCHAR2, kiểm tra thêm CHAR_USED/CHAR_LENGTH khi cần. Ví dụ chỉ minh họa việc xác minh datatype/độ dài.

### Thêm constraint có kiểm tra

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_constraints
    WHERE table_name = 'ORDERS'
      AND constraint_name = 'CK_ORDERS_AMOUNT';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            ALTER TABLE orders
            ADD CONSTRAINT ck_orders_amount
            CHECK (order_amount >= 0)
            ENABLE NOVALIDATE
        ]';
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM user_constraints
        WHERE table_name = 'ORDERS'
          AND constraint_name = 'CK_ORDERS_AMOUNT'
          AND constraint_type = 'C';

        IF l_count = 0 THEN
            RAISE_APPLICATION_ERROR(
                -20004,
                'CK_ORDERS_AMOUNT exists but is not the expected constraint type'
            );
        END IF;
    END IF;
END;
/
~~~

Tên constraint tồn tại chưa đủ chứng minh condition đúng. Khi object đã tồn tại, kiểm tra SEARCH_CONDITION, STATUS, VALIDATED và các cột liên quan trước khi bỏ qua.

### Tạo index nếu chưa tồn tại

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_indexes
    WHERE index_name = 'IX_ORDERS_CUSTOMER_CREATED';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE INDEX ix_orders_customer_created
            ON orders(customer_id, created_at)
        ]';
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM user_ind_columns
        WHERE index_name = 'IX_ORDERS_CUSTOMER_CREATED';

        IF l_count <> 2 THEN
            RAISE_APPLICATION_ERROR(
                -20005,
                'Index exists with unexpected column definition'
            );
        END IF;
    END IF;
END;
/
~~~

Trong production cần xác minh thứ tự cột, ASC/DESC, uniqueness, partitioning, visibility, status và tablespace; số cột bằng nhau không đủ để xác nhận index tương đương.

### Không bắt mọi exception rồi bỏ qua

Mẫu nguy hiểm:

~~~sql
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE app_event (event_id NUMBER)';
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/
~~~

Đoạn này che giấu cả lỗi syntax, thiếu quota, thiếu privilege, tablespace đầy và object conflict. Nếu cần xử lý ORA-00955, chỉ bắt đúng lỗi dự kiến rồi xác minh object thực sự tương thích; mọi lỗi khác phải được raise lại.

### Race giữa kiểm tra và tạo

Dictionary check rồi CREATE vẫn có thể race nếu hai runner chạy đồng thời. Idempotent check không thay thế migration mutex. Dùng một runner/lock duy nhất và vẫn xử lý trường hợp object được tạo ngoài quy trình.

## 8. Chiến lược expand-contract

Expand-contract là cách triển khai schema change theo nhiều release để phiên bản ứng dụng cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp. Thay đổi được chia thành ba pha:

1. **Expand:** thêm cấu trúc mới mà code cũ vẫn dùng được.
2. **Migrate/cut over:** deploy code tương thích, ghi/đọc dữ liệu mới, backfill và chuyển traffic.
3. **Contract:** chỉ xóa cấu trúc cũ sau khi mọi code/consumer cũ đã ngừng sử dụng.

### Ví dụ đổi cột EMAIL sang NORMALIZED_EMAIL

Không nên rename/drop EMAIL ngay khi deploy code mới. Một phiên bản ứng dụng cũ có thể vẫn truy vấn EMAIL trong lúc rolling deployment.

~~~text
Release A: schema có EMAIL
    |
    v
Release B: ADD NORMALIZED_EMAIL (nullable)
    |
    v
Release C: ứng dụng dual-write EMAIL + NORMALIZED_EMAIL
    |
    v
Backfill dữ liệu cũ theo batch
    |
    v
Validate dữ liệu và constraint
    |
    v
Release D: ứng dụng đọc NORMALIZED_EMAIL
    |
    v
Release E: ngừng ghi EMAIL, quan sát hết consumer cũ
    |
    v
Release F: DROP EMAIL trong migration riêng
~~~

### Pha 1: expand schema

~~~sql
ALTER TABLE customers
ADD (normalized_email VARCHAR2(320));
~~~

Cột mới nullable giúp code cũ tiếp tục insert mà không cần biết cột mới. Nếu có default hoặc NOT NULL, cần đánh giá tác động tới dữ liệu hiện tại, DML, lock và version Oracle trước khi thêm.

### Pha 2: deploy code tương thích

Trong giai đoạn rolling deployment, code mới có thể dual-write:

~~~sql
INSERT INTO customers (
    customer_id, email, normalized_email
)
VALUES (
    :customer_id, :email, LOWER(:email)
);
~~~

Với UPDATE, mọi đường ghi phải duy trì cả hai cột. Nếu nhiều application versions, batch jobs hoặc integration clients cùng ghi bảng, cần cập nhật tất cả hoặc dùng cơ chế đồng bộ tạm thời được kiểm soát. Trigger có thể hỗ trợ chuyển tiếp nhưng tăng độ phức tạp và cần đánh giá recursion, ordering và performance.

### Pha 3: backfill dữ liệu cũ

Backfill chỉ cập nhật các hàng chưa có giá trị mới:

~~~sql
UPDATE customers
SET normalized_email = LOWER(email)
WHERE normalized_email IS NULL
  AND email IS NOT NULL;

COMMIT;
~~~

Với bảng lớn, chạy theo batch để giới hạn undo/redo, lock duration và thời gian mỗi transaction. Không chạy một UPDATE toàn bảng trong giờ cao điểm nếu chưa đo.

### Pha 4: validate và chuyển đọc

~~~sql
SELECT COUNT(*) AS missing_normalized_email
FROM customers
WHERE email IS NOT NULL
  AND normalized_email IS NULL;

SELECT COUNT(*) AS mismatched_email
FROM customers
WHERE email IS NOT NULL
  AND normalized_email <> LOWER(email);
~~~

Các phép kiểm tra phải xử lý NULL theo semantics nghiệp vụ. Khi validation đạt, deploy code đọc cột mới; giữ cột cũ thêm một khoảng quan sát để có thể quay về code trước.

### Pha 5: contract

Chỉ sau khi xác nhận mọi application instance, report, ETL, database link consumer và batch job đã ngừng dùng EMAIL mới được drop:

~~~sql
ALTER TABLE customers DROP COLUMN email;
~~~

Đây là DDL destructive. Trước khi chạy, lưu backup/archival phù hợp, xác nhận dependency và chấp nhận rằng code cũ không còn tương thích. Thực hiện ở migration/release riêng để có thời gian quan sát sau cutover.

## 9. Backfill theo batch và checkpoint

Backfill dữ liệu có thể kéo dài hơn DDL. Chia batch giúp mỗi transaction ngắn, giảm lượng undo cần cho một lần rollback và cho phép tiếp tục sau process failure.

### Batch theo khóa chính

Nếu bảng có khóa số tăng dần, có thể chia theo key ranges:

~~~sql
UPDATE customers
SET normalized_email = LOWER(email)
WHERE customer_id >= :range_start
  AND customer_id < :range_end
  AND normalized_email IS NULL
  AND email IS NOT NULL;

COMMIT;
~~~

Runner ghi lại range đã hoàn tất trong migration progress table sau khi DML commit. Nếu process chết, chỉ chạy lại range chưa hoàn tất; điều kiện NORMALIZED_EMAIL IS NULL giúp thao tác không ghi đè giá trị đã được code mới cập nhật.

### Batch theo ROWID

Với bảng không có khóa phù hợp, có thể chọn một nhóm ROWID:

~~~sql
UPDATE customers
SET normalized_email = LOWER(email)
WHERE ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid
        FROM customers
        WHERE normalized_email IS NULL
          AND email IS NOT NULL
          AND ROWNUM <= 1000
    )
);

COMMIT;
~~~

Lặp lại cho tới khi SQL%ROWCOUNT bằng 0. Với workload đồng thời, có thể cần điều chỉnh chiến lược chọn batch để tránh nhiều worker cùng chọn một tập hàng. ROWID chỉ dùng trong phạm vi physical row hiện tại; không lưu ROWID như khóa bền vững qua table move/redefinition.

### PL/SQL loop minh họa

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    LOOP
        UPDATE customers
        SET normalized_email = LOWER(email)
        WHERE ROWID IN (
            SELECT rid
            FROM (
                SELECT ROWID AS rid
                FROM customers
                WHERE normalized_email IS NULL
                  AND email IS NOT NULL
                  AND ROWNUM <= 1000
            )
        );

        l_rows := SQL%ROWCOUNT;
        COMMIT;

        EXIT WHEN l_rows = 0;
    END LOOP;
END;
/
~~~

Đoạn này minh họa batch lặp đơn giản. Production cần thêm sleep/throttle, instrumentation, checkpoint, xử lý exception và giới hạn thời gian/redo. Mỗi COMMIT làm batch trước trở thành bền vững; exception ở batch sau không hoàn tác các batch đã commit.

### Checkpoint cho từng batch

Có thể lưu:

- Migration ID và step.
- Batch key range hoặc chunk ID.
- Số hàng được cập nhật.
- Thời điểm bắt đầu/kết thúc.
- Trạng thái RUNNING/COMPLETED/FAILED.
- Error code/message nếu lỗi.

Ghi checkpoint sau khi batch data commit. Nếu checkpoint commit trước data commit, runner có thể đánh dấu batch hoàn tất dù dữ liệu chưa bền vững. Vì vậy thứ tự commit phải được thiết kế có chủ đích.

### Xử lý concurrent writes

Trong lúc backfill, ứng dụng có thể tiếp tục insert/update. Dùng điều kiện chỉ cập nhật hàng chưa có giá trị mới, dual-write hoặc cơ chế đồng bộ khác để tránh ghi đè dữ liệu mới. Sau backfill, chạy validation lại để bắt các hàng được tạo/cập nhật trong khoảng thời gian migration.

### Theo dõi resource

Theo dõi elapsed time, rows/sec, redo size, undo usage, buffer gets, physical I/O, blocking sessions, archive destination/FRA và application latency. Dừng/throttle batch nếu workload vượt ngưỡng đã thống nhất.

## 10. Thêm constraint mà không buộc validate toàn bộ ngay lập tức

Với bảng lớn, thêm constraint và validate tất cả dữ liệu hiện có có thể tốn thời gian và cần lock. Oracle hỗ trợ các trạng thái ENABLE NOVALIDATE và ENABLE VALIDATE cho nhiều loại constraint.

### ENABLE NOVALIDATE

Ví dụ thêm CHECK constraint:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_amount
CHECK (order_amount >= 0)
ENABLE NOVALIDATE;
~~~

ENABLE NOVALIDATE không quét/khẳng định toàn bộ dữ liệu cũ đã hợp lệ, nhưng constraint được bật để kiểm tra các DML mới theo semantics của loại constraint. Vì vậy, dữ liệu lịch sử có thể còn vi phạm trong khi các thay đổi mới bị kiểm soát.

### Tìm dữ liệu cũ vi phạm trước validate

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM orders
WHERE order_amount < 0;
~~~

Nếu có vi phạm, sửa dữ liệu bằng một migration DML riêng có checkpoint. Không cố ENABLE VALIDATE cho tới khi dữ liệu đạt điều kiện.

### ENABLE VALIDATE

~~~sql
ALTER TABLE orders
ENABLE VALIDATE CONSTRAINT ck_orders_amount;
~~~

Thao tác này xác nhận dữ liệu hiện có tuân thủ constraint và chuyển constraint sang trạng thái validated. Nó có thể cần scan dữ liệu, tài nguyên và lock; đánh giá workload, kích thước bảng và hành vi phiên bản.

### Kiểm tra constraint state

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       rely
FROM user_constraints
WHERE table_name = 'ORDERS'
ORDER BY constraint_name;
~~~

STATUS=ENABLED không đồng nghĩa VALIDATED=VALIDATED. Với NOVALIDATE, constraint có thể enforce DML mới nhưng chưa xác nhận dữ liệu lịch sử.

### Foreign key

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
ENABLE NOVALIDATE;
~~~

Trước khi validate, kiểm tra orphan rows:

~~~sql
SELECT COUNT(*) AS orphan_rows
FROM order_items i
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.order_id = i.order_id
);
~~~

Index trên cột foreign key ở bảng con thường hữu ích cho DML và locking behavior, nhưng không tự động được tạo bởi việc thêm foreign key. Đánh giá workload và tạo index phù hợp.

### NOT NULL

Để chuyển một cột nullable thành NOT NULL, trước hết backfill và kiểm tra:

~~~sql
SELECT COUNT(*) AS null_rows
FROM customers
WHERE normalized_email IS NULL;
~~~

Khi không còn NULL và mọi writer đã duy trì giá trị, thực hiện:

~~~sql
ALTER TABLE customers
MODIFY (normalized_email NOT NULL);
~~~

Việc đổi nullability có thể cần validation/lock và thất bại nếu vẫn còn NULL. Thực hiện trong migration riêng sau khi ứng dụng đã dual-write và validation ổn định.

## 11. Tạo index và online DDL

Tạo index trên bảng lớn có thể tiêu thụ CPU, I/O, temporary space và redo. Nếu phiên bản/edition/cấu hình hỗ trợ, ONLINE có thể cho phép DML tiếp tục trong một phần quá trình build, nhưng vẫn có các giai đoạn cần lock và yêu cầu tài nguyên.

### Tạo index thường

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders(customer_id, created_at);
~~~

### Tạo index ONLINE

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders(customer_id, created_at)
ONLINE;
~~~

ONLINE không có nghĩa không có lock, không phát sinh redo hoặc luôn ít ảnh hưởng. Oracle có thể cần lock ở giai đoạn bắt đầu/kết thúc, theo dõi thay đổi DML đồng thời và sử dụng thêm tài nguyên. Khả năng, giới hạn datatype/partition và entitlement cần kiểm tra đúng release.

### Kiểm tra trạng thái index

~~~sql
SELECT index_name,
       table_name,
       status,
       visibility,
       uniqueness,
       logging,
       degree
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

Với partitioned indexes, kiểm tra thêm USER_IND_PARTITIONS và USER_IND_SUBPARTITIONS. Index INVALID/UNUSABLE có thể không được optimizer dùng như mong đợi; xác định nguyên nhân và rebuild theo quy trình.

### Invisible index cho thử nghiệm

Trong một số phiên bản, có thể tạo index INVISIBLE để kiểm tra tác động mà không cho optimizer mặc định dùng nó:

~~~sql
CREATE INDEX ix_orders_customer_test
ON orders(customer_id)
INVISIBLE;
~~~

Session thử nghiệm có thể bật optimizer_use_invisible_indexes để đánh giá plan. Invisible index vẫn được duy trì bởi DML và tiêu thụ storage; không phải cách tránh chi phí index. Xác nhận khả năng hỗ trợ theo release.

### Rebuild index

~~~sql
ALTER INDEX ix_orders_customer_created REBUILD ONLINE;
~~~

REBUILD là DDL và có implicit commit. ONLINE có điều kiện riêng; đánh giá storage tạm thời, redo, lock và ảnh hưởng tới DML. Nếu rebuild thất bại, kiểm tra USER_INDEXES/partition status trước khi retry.

## 12. DDL locks và tác động availability

DDL cần dictionary/metadata locks để bảo đảm cấu trúc object không thay đổi giữa lúc phân tích và thực thi. Một DDL có thể chờ transaction DML đang giữ lock hoặc bị từ chối khi không lấy được lock trong thời gian cho phép.

### DDL_LOCK_TIMEOUT

Tham số DDL_LOCK_TIMEOUT xác định thời gian session chờ DDL lock trước khi trả lỗi khi lock không lấy được. Có thể đặt trong session:

~~~sql
ALTER SESSION SET ddl_lock_timeout = 60;
~~~

Giá trị 60 là 60 giây minh họa. Đặt timeout không giải quyết blocker; nó chỉ thay đổi thời gian chờ. Chọn timeout dựa trên maintenance window và mức chấp nhận chờ của deployment.

### ORA-00054

ORA-00054 thường báo resource busy khi DDL không lấy được lock cần thiết. Kiểm tra session đang giữ lock, transaction duration và workload; không liên tục retry với timeout rất lớn vì có thể làm hàng đợi deployment kéo dài.

### Xem lock và session

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       s.sql_id,
       s.event,
       s.seconds_in_wait,
       s.blocking_session
FROM v$session s
WHERE s.username IS NOT NULL
ORDER BY s.seconds_in_wait DESC;
~~~

~~~sql
SELECT lo.session_id AS sid,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

Các view giúp điều tra session/object locks; DDL locks và library cache locks có thể cần thêm V$LOCK, V$ACCESS hoặc diagnostic views tùy loại wait.

### Online DDL vẫn có thể chờ lock

Một thao tác ONLINE vẫn cần metadata coordination. Nếu session khác giữ transaction lâu trên object, DDL có thể chờ ở giai đoạn bắt đầu hoặc hoàn tất. Theo dõi session waits và đặt DDL_LOCK_TIMEOUT phù hợp.

### Tránh DDL trong transaction ứng dụng

Không thực hiện ALTER TABLE hoặc CREATE INDEX giữa một transaction nghiệp vụ đang mở. DDL sẽ commit transaction đó trước khi chạy, có thể làm ứng dụng mất khả năng rollback các thay đổi nghiệp vụ chưa hoàn tất.

## 13. Migration runner và xử lý lỗi

Migration runner cần biết cách xử lý lỗi SQL, process interruption, connection loss và trạng thái DDL đã thực thi nhưng response chưa về.

### SQL*Plus/SQLcl error handling

Một script có thể dùng:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

-- Migration steps...
~~~

WHENEVER SQLERROR giúp runner thoát khi có SQL error. ROLLBACK chỉ hoàn tác transaction DML hiện tại chưa commit; nó không undo DDL đã commit ngầm hoặc DML đã commit trước DDL.

### Mỗi step có precondition và postcondition

Ví dụ step ADD_COLUMN:

- Precondition: bảng CUSTOMERS tồn tại, chưa có NORMALIZED_EMAIL hoặc cột hiện có đúng định nghĩa mong muốn.
- Action: ALTER TABLE ADD COLUMN nếu cần.
- Postcondition: USER_TAB_COLUMNS có cột với datatype/nullability/default phù hợp.
- Recovery: nếu postcondition đạt dù runner báo timeout, đánh dấu step hoàn tất; nếu object không tương thích, dừng để xử lý thủ công.

### Trạng thái FAILED không đồng nghĩa phải rollback

Nếu migration thất bại sau khi đã thêm cột và backfill một phần, việc rollback toàn bộ có thể không khả thi hoặc nguy hiểm. Ghi FAILED, bảo toàn trạng thái, xác định step đã hoàn tất, rồi quyết định resume hoặc chạy migration bù.

### Không retry DDL mù quáng

Sau lỗi network/client timeout:

1. Kết nối lại database.
2. Kiểm tra migration history.
3. Kiểm tra data dictionary và trạng thái object.
4. Xác minh DDL có áp dụng hay không.
5. Nếu đã áp dụng đúng, ghi checkpoint.
6. Nếu chưa áp dụng, chạy lại step idempotent.
7. Nếu object tồn tại nhưng definition sai, dừng và tạo remediation migration.

### Error log

Lưu SQLCODE, SQLERRM, migration ID, step, session/module, timestamp và stack/trace cần thiết. Không lưu credentials, bind data nhạy cảm hoặc full customer data trong error message.

## 14. Thứ tự deploy schema và application

Rolling deployment có thể khiến nhiều phiên bản application cùng truy cập database. Schema phải tương thích với tất cả phiên bản đang chạy trong giai đoạn chuyển tiếp.

### Ma trận tương thích

| Trạng thái schema | Application cũ | Application mới |
| --- | --- | --- |
| Trước expand | Có | Chưa chắc chạy được |
| Sau expand, trước cutover | Có | Có nếu code mới hỗ trợ schema cũ/mới |
| Trong dual-write/backfill | Có nếu cột cũ vẫn được duy trì | Có |
| Sau chuyển read sang cột mới | Có thể còn chạy nếu cột cũ vẫn được duy trì | Có |
| Sau contract/drop cột cũ | Không | Có |

Vì vậy, contract chỉ thực hiện sau khi mọi instance cũ, batch, report, ETL, integration và consumer đã được nâng cấp hoặc ngừng hoạt động.

### Trình tự release khuyến nghị

1. **Release schema expand:** chỉ thêm cấu trúc tương thích ngược.
2. **Release application compatibility:** code mới đọc/ghi được cả trạng thái cũ và mới.
3. **Backfill:** lấp dữ liệu cũ theo batch, có checkpoint.
4. **Validation:** kiểm tra đầy đủ và constraint.
5. **Read cutover:** chuyển code sang đọc cấu trúc mới.
6. **Stop old writes:** xác nhận không còn writer cũ.
7. **Observation window:** theo dõi error, data drift, performance và dependency.
8. **Contract release:** drop/rename/cleanup cấu trúc cũ trong migration riêng.

### Không rename/drop trong cùng deployment đầu tiên

ALTER TABLE RENAME COLUMN hoặc DROP COLUMN có thể làm code cũ, view, procedure, trigger, report và integration lỗi ngay lập tức. Dùng expand-contract để giữ cửa sổ tương thích.

### Thay đổi datatype

Nếu cần đổi datatype không tương thích, cân nhắc thêm cột mới với datatype đích, dual-write, backfill có conversion/error handling, validate, chuyển đọc/ghi, rồi drop cột cũ sau. Không ALTER COLUMN trực tiếp khi có nguy cơ mất dữ liệu, rounding, truncation hoặc conversion error.

### Edition-based redefinition

Với ứng dụng cần nâng cấp PL/SQL/database objects ít downtime, Oracle Edition-Based Redefinition (EBR) có thể giúp duy trì nhiều edition và chuyển session sang edition mới theo quy trình. EBR không làm mọi DDL trở nên transactional; nó là kỹ thuật triển khai versioned objects với yêu cầu thiết kế editioning views, crossedition triggers và editionable objects. Kiểm tra edition/feature support và độ phù hợp trước khi chọn.

## 15. Rollback, roll-forward và compensating migration

Vì DDL commit ngầm, không thể dùng một ROLLBACK để đưa toàn schema về trạng thái trước migration. Cần phân biệt ba hướng xử lý.

### Rollback cấu trúc

Rollback cấu trúc là chạy DDL ngược hoặc DDL bù:

- ADD COLUMN có thể bù bằng DROP COLUMN nếu cột chưa chứa dữ liệu cần giữ và không có dependency.
- CREATE INDEX có thể bù bằng DROP INDEX nếu index không được ứng dụng phụ thuộc.
- ADD CONSTRAINT có thể bù bằng DROP CONSTRAINT nếu nghiệp vụ cho phép.
- DROP COLUMN/TABLE thường không thể rollback nếu không có backup hoặc bản sao dữ liệu.

Rollback DDL cũng là DDL và sẽ implicit commit. Mỗi bước rollback phải có precondition/postcondition riêng.

### Roll-forward

Roll-forward tạo migration mới để đưa schema/data từ trạng thái hiện tại tới trạng thái mong muốn. Đây thường là lựa chọn an toàn hơn khi một số bước đã được áp dụng và dữ liệu mới đã được ghi.

Ví dụ nếu cột mới đã được thêm nhưng index build thất bại, sửa nguyên nhân rồi tạo index ở migration tiếp theo hoặc resume step; không cần drop cột chỉ để quay lại trạng thái ban đầu.

### Compensating migration

Compensating migration thực hiện thay đổi nghiệp vụ để bù hậu quả của bước đã commit. Ví dụ dữ liệu đã chuyển sang bảng mới nhưng phát hiện mapping sai; cần migration sửa mapping theo nguồn dữ liệu gốc hoặc business rule, không thể ROLLBACK DDL.

### Khi nào restore backup?

Restore/point-in-time recovery là biện pháp ở mức database khi schema/data bị hỏng nghiêm trọng và không có cách sửa tiến an toàn. Đây là thao tác có thể làm mất các giao dịch sau recovery point, ảnh hưởng toàn database và yêu cầu coordinated outage. Không dùng restore toàn database để rollback một migration nhỏ nếu có thể sửa bằng migration bù.

### Quyết định rollback hay roll-forward

| Tình huống | Hướng xử lý thường phù hợp |
| --- | --- |
| ADD COLUMN thành công, CREATE INDEX thất bại | Kiểm tra trạng thái rồi retry tạo index |
| Backfill hoàn tất một phần | Resume theo checkpoint/điều kiện idempotent |
| Constraint NOVALIDATE đã tạo, validation thất bại | Sửa dữ liệu vi phạm rồi validate lại |
| Code mới lỗi nhưng schema expand tương thích | Rollback application, giữ schema expand |
| Đã chuyển đọc sang cột mới, dữ liệu sai | Dừng cutover, reconcile và roll-forward sửa dữ liệu |
| Đã DROP cột cũ và cần dữ liệu cũ | Restore từ backup/archive hoặc phục hồi dữ liệu nguồn; không có rollback đơn giản |
| Migration tạo object sai định nghĩa | Dừng deployment, đánh giá dependency, chạy remediation có kiểm soát |

## 16. Ví dụ migration nhiều bước có checkpoint

Ví dụ dưới đây minh họa cách tách migration thành các bước bền vững. Cần điều chỉnh tên schema, bảng và quyền cho môi trường thực tế.

### Step 0: ghi migration bắt đầu

~~~sql
INSERT INTO schema_migrations (
    migration_id,
    checksum,
    status,
    current_step,
    started_at,
    updated_at,
    executed_by
)
VALUES (
    'V2026_015_ADD_NORMALIZED_EMAIL',
    'sha256:example-checksum',
    'STARTED',
    'INIT',
    SYSTIMESTAMP,
    SYSTIMESTAMP,
    SYS_CONTEXT('USERENV', 'SESSION_USER')
);

COMMIT;
~~~

Nếu migration_id đã tồn tại, runner phải đọc status/checksum và xác định resume; không insert trùng hoặc reset trạng thái tùy tiện.

### Step 1: add column

~~~sql
ALTER TABLE customers
ADD (normalized_email VARCHAR2(320));
~~~

Sau đó xác minh:

~~~sql
SELECT column_name, data_type, data_length, nullable
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'NORMALIZED_EMAIL';
~~~

Ghi checkpoint sau khi postcondition đạt:

~~~sql
UPDATE schema_migrations
SET status = 'RUNNING',
    current_step = 'COLUMN_ADDED',
    updated_at = SYSTIMESTAMP
WHERE migration_id = 'V2026_015_ADD_NORMALIZED_EMAIL';

COMMIT;
~~~

Nếu process chết sau ALTER TABLE nhưng trước UPDATE history, lần chạy sau kiểm tra dictionary, thấy column đúng định nghĩa và ghi checkpoint mà không chạy ADD lần nữa.

### Step 2: backfill theo batch

Chạy batch update với điều kiện NORMALIZED_EMAIL IS NULL. Commit dữ liệu mỗi batch; chỉ sau commit mới ghi checkpoint range tương ứng. Nếu process chết giữa hai commit, batch có thể chạy lại nhưng điều kiện idempotent giúp không ghi đè giá trị đã có.

### Step 3: tạo index

~~~sql
CREATE INDEX ix_customers_normalized_email
ON customers(normalized_email);
~~~

Xác minh index definition/status qua USER_INDEXES và USER_IND_COLUMNS. Nếu runner mất kết nối sau CREATE, kiểm tra metadata trước khi retry.

### Step 4: validate

~~~sql
SELECT COUNT(*) AS rows_missing_value
FROM customers
WHERE email IS NOT NULL
  AND normalized_email IS NULL;
~~~

Chỉ đánh dấu VALIDATED khi kết quả và các rule nghiệp vụ đều đạt. Nếu có mismatch, giữ trạng thái RUNNING/FAILED kèm step, không đánh dấu COMPLETED.

### Step 5: complete

~~~sql
UPDATE schema_migrations
SET status = 'COMPLETED',
    current_step = 'VALIDATED',
    updated_at = SYSTIMESTAMP,
    completed_at = SYSTIMESTAMP,
    error_code = NULL,
    error_message = NULL
WHERE migration_id = 'V2026_015_ADD_NORMALIZED_EMAIL';

COMMIT;
~~~

Migration chỉ hoàn tất khi schema, data và application cutover theo đúng phạm vi của release đã được xác nhận.

## 17. Kiểm tra dependency trước khi contract

Trước khi drop/rename column hoặc table, cần tìm dependency trong database và hệ thống ngoài database.

### USER_DEPENDENCIES

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE referenced_name = 'CUSTOMERS'
ORDER BY type, name;
~~~

### USER_OBJECTS

~~~sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name IN ('CUSTOMERS', 'CUSTOMER_REPORT_V')
ORDER BY object_type, object_name;
~~~

### DBMS_METADATA

~~~sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'CUSTOMERS', USER)
FROM dual;
~~~

DBMS_METADATA giúp lưu DDL hiện tại để review/restore cấu trúc khi cần. Output có thể chứa tablespace/storage attributes và khác nhau theo release; kiểm tra quyền execute và metadata filtering.

### Dependency ngoài database

Data dictionary không biết tất cả consumer. Tìm thêm trong:

- Source code và ORM mappings.
- Report/BI definitions.
- ETL, scheduler, batch scripts.
- Database links và remote consumers.
- Materialized views/replication.
- Dynamic SQL và SQL generated at runtime.
- Monitoring, audit và integration platform.

Không contract chỉ vì USER_DEPENDENCIES không trả hàng.

## 18. DDL trong PL/SQL và dynamic SQL

Đặt DDL bên trong anonymous block hoặc stored procedure không loại bỏ implicit commit. Oracle thường yêu cầu dynamic SQL để thực thi DDL từ PL/SQL:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'ALTER TABLE customers ADD (source_system VARCHAR2(30))';
END;
/
~~~

ALTER TABLE vẫn thực hiện implicit commit theo quy tắc DDL. Nếu block có DML trước EXECUTE IMMEDIATE, DML có thể đã commit trước DDL. Exception handler gọi ROLLBACK không hoàn tác DDL hoặc DML đã commit trước đó.

### Ví dụ nguy hiểm

~~~sql
BEGIN
    UPDATE accounts
    SET migration_flag = 'Y'
    WHERE migration_flag IS NULL;

    EXECUTE IMMEDIATE
        'ALTER TABLE accounts ADD (new_code VARCHAR2(20))';

    RAISE_APPLICATION_ERROR(-20010, 'simulate later failure');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

UPDATE có thể được commit ngầm trước ALTER TABLE. ALTER TABLE cũng commit khi thành công. Lỗi được raise sau đó không thể rollback hai thay đổi đã commit. Đây là lý do DML migration và DDL nên được chia thành step rõ ràng, không giả định exception handler bao bọc được toàn bộ.

### Stored procedure và CREATE OR REPLACE

CREATE OR REPLACE PROCEDURE/PACKAGE/VIEW là DDL. Nó có thể thay đổi object definition và làm invalidated dependent objects/cursors cần recompile. Khi deploy PL/SQL:

- Lưu source version/checksum.
- Kiểm tra USER_OBJECTS.STATUS sau compile.
- Kiểm tra USER_ERRORS.
- Xác nhận grants/dependencies theo yêu cầu.
- Không giả định lỗi compile tự rollback các DDL trước đó trong release.

~~~sql
SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, sequence;
~~~

## 19. Checklist trước khi chạy migration

### Phạm vi và kế hoạch

- Xác định migration ID, checksum và database/schema mục tiêu.
- Xác định release application cũ/mới cùng tồn tại trong thời gian nào.
- Liệt kê DDL, DML, backfill và cleanup theo thứ tự.
- Xác định precondition/postcondition cho từng step.
- Xác định step nào destructive và cần approval riêng.
- Xác định resume point và remediation nếu step thất bại.

### Database readiness

- Kiểm tra database role/open mode và container/service.
- Kiểm tra free space cho data, index, TEMP, UNDO và archive/FRA.
- Kiểm tra invalid objects, blocking sessions và long-running transactions.
- Kiểm tra object dependencies và schema privileges.
- Kiểm tra statistics, partitioning và data volume.
- Xác nhận backup/recovery readiness cho thay đổi destructive.

### Application readiness

- Code cũ có hoạt động sau expand không?
- Code mới có hoạt động trước và sau backfill không?
- Tất cả writers có dual-write hoặc tương thích không?
- Retry/idempotency đã được kiểm thử chưa?
- Connection pool/session state có cần reset không?
- Reporting/ETL/integration consumers đã được liệt kê chưa?

### Execution readiness

- Migration mutex đã hoạt động chưa?
- Script có thể resume sau process/network failure không?
- Error handling có dừng đúng khi SQL lỗi không?
- DDL lock timeout và maintenance window phù hợp không?
- Logging/checkpoint có ghi bền vững không?
- Operator có biết cách kiểm tra trạng thái schema thực tế không?

## 20. Checklist sau migration

Sau khi runner báo hoàn tất, xác minh database thay vì chỉ tin exit code.

### Schema

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name IN ('CUSTOMERS', 'SCHEMA_MIGRATIONS');

SELECT column_name, data_type, data_length, nullable
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
ORDER BY column_id;

SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'CUSTOMERS'
ORDER BY constraint_name;

SELECT index_name, status, visibility
FROM user_indexes
WHERE table_name = 'CUSTOMERS'
ORDER BY index_name;
~~~

### Data validation

- Row counts trước/sau theo tiêu chí nghiệp vụ.
- Không còn hàng chưa backfill.
- Không có duplicate keys ngoài dự kiến.
- Không có orphan foreign keys.
- Nullability, range và check conditions đạt.
- Aggregate totals/checksum theo nhóm khớp.
- Dữ liệu do application ghi trong lúc backfill không bị bỏ sót.

### Object compilation và runtime

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status <> 'VALID'
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, sequence;
~~~

Kiểm tra application smoke tests, query plans, latency, error rate, blocking, redo/undo, invalid objects và job schedules.

### Migration history

~~~sql
SELECT migration_id,
       checksum,
       status,
       current_step,
       started_at,
       updated_at,
       completed_at,
       error_code,
       error_message
FROM schema_migrations
ORDER BY started_at DESC;
~~~

Đối chiếu status COMPLETED với postcondition thực tế. Nếu history và schema không khớp, dừng rollout tiếp theo và điều tra.

## 21. Lỗi thường gặp trong migration

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORA-00955 name is already used by an existing object | DDL đã chạy ở lần trước hoặc object cùng tên đã tồn tại | Kiểm tra object type/definition; đánh dấu step hoàn tất nếu đúng, nếu sai tạo remediation. |
| ORA-01430 column being added already exists | ADD COLUMN đã chạy hoặc cột được tạo ngoài migration | Kiểm tra datatype/default/nullability và dependency trước khi resume. |
| ORA-02264 name already used by an existing constraint | Constraint name đã tồn tại | Kiểm tra USER_CONSTRAINTS và definition, không đổi tên mù quáng. |
| ORA-02298 cannot validate constraint | Dữ liệu cũ vi phạm constraint | Tìm rows vi phạm, sửa bằng DML migration có checkpoint rồi validate lại. |
| ORA-02291 parent key not found | DML tạo child row không có parent | Kiểm tra mapping/load order và dữ liệu parent. |
| ORA-02292 child record found | Xóa parent còn child rows | Xác định cascade/business rule và xử lý theo thứ tự. |
| ORA-00054 resource busy | DDL không lấy được lock | Tìm blocker, chọn cửa sổ phù hợp, điều chỉnh DDL_LOCK_TIMEOUT. |
| ORA-04021 timeout waiting for object lock | Library cache/object lock đang bị giữ | Xác định session/DDL đang giữ object, tránh retry dồn dập. |
| ORA-01652 unable to extend temp segment | TEMP không đủ cho sort/index/validation | Kiểm tra TEMP capacity, kế hoạch index/validation và batch size. |
| ORA-01653 unable to extend table | Tablespace/datafile không đủ | Kiểm tra free space, autoextend và storage capacity. |
| ORA-01555 snapshot too old trong backfill/query | UNDO retention/volume và transaction duration | Chia batch, giảm thời gian query, kiểm tra UNDO sizing/retention. |
| ORA-01442 column already NOT NULL | Migration lặp lại trên cột đã có trạng thái đích | Kiểm tra metadata; đánh dấu step hoàn tất nếu đúng. |
| ORA-01451 cannot modify to NULL | Thay đổi nullability không phù hợp với trạng thái hiện tại/constraint | Kiểm tra data, constraint và trạng thái cột. |
| ORA-01031 insufficient privileges | Migration account thiếu quyền DDL/object | Cấp đúng privilege qua quy trình quản trị, tránh dùng SYSDBA cho ứng dụng. |
| ORA-00942 table or view does not exist | Sai owner/current schema hoặc dependency chưa deploy | Kiểm tra schema qualification, synonym, grant và thứ tự migration. |
| ORA-04063 object has errors | View/package/procedure invalid sau thay đổi dependency | Xem USER_ERRORS, sửa source và compile theo thứ tự. |
| Client timeout sau DDL | Server có thể đã thực thi DDL nhưng response bị mất | Kiểm tra data dictionary trước khi retry. |
| Migration history RUNNING nhưng schema đã đổi | Process chết giữa DDL và checkpoint | So sánh postcondition, ghi checkpoint nếu object đúng. |
| Migration history COMPLETED nhưng object mất | Object bị sửa/drop ngoài migration | Dừng deployment tiếp theo, điều tra drift và remediation. |

## 22. Bài thực hành: migration có thể resume sau lỗi

Bài lab dùng schema học tập. Mục tiêu là mô phỏng migration nhiều bước, cố ý dừng sau khi DDL đã commit, rồi chạy lại bằng kiểm tra trạng thái. Không thực hiện trên schema dùng chung.

### Bước 1: tạo bảng và dữ liệu ban đầu

~~~sql
CREATE TABLE lab_customer (
    customer_id NUMBER PRIMARY KEY,
    email VARCHAR2(320),
    created_at DATE DEFAULT SYSDATE NOT NULL
);

INSERT INTO lab_customer(customer_id, email)
SELECT level,
       'user' || level || '@example.test'
FROM dual
CONNECT BY level <= 10000;

COMMIT;
~~~

### Bước 2: tạo migration history

~~~sql
CREATE TABLE lab_migration_history (
    migration_id VARCHAR2(100) PRIMARY KEY,
    status VARCHAR2(20) NOT NULL,
    current_step VARCHAR2(100),
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP
);

INSERT INTO lab_migration_history(
    migration_id, status, current_step
)
VALUES (
    'LAB_001_NORMALIZED_EMAIL', 'STARTED', 'INIT'
);

COMMIT;
~~~

### Bước 3: thêm cột mới

~~~sql
ALTER TABLE lab_customer
ADD (normalized_email VARCHAR2(320));
~~~

Kiểm tra cột:

~~~sql
SELECT column_name, data_type, data_length, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_CUSTOMER'
  AND column_name = 'NORMALIZED_EMAIL';
~~~

### Bước 4: mô phỏng runner chết trước checkpoint

Không cập nhật LAB_MIGRATION_HISTORY. Giả sử client mất kết nối ngay sau ALTER TABLE nên runner không biết DDL đã thành công.

Khi kết nối lại, kiểm tra:

~~~sql
SELECT COUNT(*)
FROM user_tab_columns
WHERE table_name = 'LAB_CUSTOMER'
  AND column_name = 'NORMALIZED_EMAIL';
~~~

Nếu cột tồn tại đúng định nghĩa, không chạy ADD COLUMN lần nữa. Cập nhật checkpoint:

~~~sql
UPDATE lab_migration_history
SET status = 'RUNNING',
    current_step = 'COLUMN_ADDED',
    updated_at = SYSTIMESTAMP
WHERE migration_id = 'LAB_001_NORMALIZED_EMAIL';

COMMIT;
~~~

### Bước 5: backfill theo batch

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    LOOP
        UPDATE lab_customer
        SET normalized_email = LOWER(email)
        WHERE normalized_email IS NULL
          AND email IS NOT NULL
          AND ROWID IN (
              SELECT rid
              FROM (
                  SELECT ROWID AS rid
                  FROM lab_customer
                  WHERE normalized_email IS NULL
                    AND email IS NOT NULL
                    AND ROWNUM <= 1000
              )
          );

        l_rows := SQL%ROWCOUNT;
        COMMIT;
        EXIT WHEN l_rows = 0;
    END LOOP;
END;
/
~~~

Nếu process dừng giữa các batch, chạy lại block. Các hàng đã có NORMALIZED_EMAIL sẽ không bị cập nhật lại.

### Bước 6: kiểm tra dữ liệu

~~~sql
SELECT COUNT(*) AS missing_rows
FROM lab_customer
WHERE email IS NOT NULL
  AND normalized_email IS NULL;

SELECT COUNT(*) AS mismatch_rows
FROM lab_customer
WHERE email IS NOT NULL
  AND normalized_email <> LOWER(email);
~~~

Cả hai kết quả cần bằng 0 cho dữ liệu lab.

### Bước 7: tạo index idempotent

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_indexes
    WHERE index_name = 'IX_LAB_CUSTOMER_NORMALIZED';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE
            'CREATE INDEX ix_lab_customer_normalized ON lab_customer(normalized_email)';
    END IF;
END;
/
~~~

Sau đó kiểm tra USER_INDEXES và USER_IND_COLUMNS để xác minh index đúng bảng/cột.

### Bước 8: đánh dấu hoàn tất

~~~sql
UPDATE lab_migration_history
SET status = 'COMPLETED',
    current_step = 'VALIDATED',
    updated_at = SYSTIMESTAMP
WHERE migration_id = 'LAB_001_NORMALIZED_EMAIL';

COMMIT;
~~~

### Bước 9: dọn lab

~~~sql
DROP TABLE lab_migration_history PURGE;
DROP TABLE lab_customer PURGE;
~~~

Chỉ chạy sau khi đã lưu kết quả và chắc chắn đây là object lab.

## 23. Câu hỏi tự kiểm tra

1. **DDL implicit commit là gì?** Oracle commit transaction hiện tại trước DDL hợp lệ và commit DDL khi thành công.
2. **ROLLBACK có hoàn tác ALTER TABLE không?** Không.
3. **Nếu DDL thất bại, DML trước đó có thể đã commit không?** Có, do implicit commit trước khi DDL thực thi.
4. **Atomic DDL có đồng nghĩa atomic migration không?** Không; chuỗi DDL/DML có thể dừng giữa các bước đã commit.
5. **Migration idempotent là gì?** Chạy lại không gây thay đổi sai và nhận diện được trạng thái đã áp dụng.
6. **Vì sao phải kiểm tra data dictionary sau timeout?** DDL có thể đã thành công dù client không nhận response.
7. **Migration history dùng để làm gì?** Lưu version, checksum, step và trạng thái để resume/điều tra.
8. **Vì sao checksum quan trọng?** Phát hiện script đã bị sửa giữa các môi trường sau khi được áp dụng.
9. **Expand-contract có mấy pha chính?** Expand, migrate/cutover và contract.
10. **Tại sao không drop cột cũ ngay khi deploy code mới?** Application instances cũ hoặc consumers khác có thể vẫn phụ thuộc cột đó.
11. **Backfill theo batch có lợi ích gì?** Giới hạn undo/redo, lock duration và cho phép resume.
12. **Checkpoint batch nên ghi khi nào?** Sau khi batch data đã commit bền vững.
13. **Vì sao SELECT FOR UPDATE không giữ migration lock qua DDL?** Implicit commit giải phóng transaction row lock.
14. **DBMS_LOCK release_on_commit=FALSE giúp gì?** Giữ application lock qua các implicit commits trong cùng session.
15. **DBMS_LOCK.ALLOCATE_UNIQUE có lưu ý gì?** Có thể commit transaction hiện tại, nên gọi trước công việc cần transaction.
16. **ENABLE NOVALIDATE có nghĩa gì?** Enforce DML mới theo constraint nhưng chưa xác nhận toàn bộ dữ liệu cũ.
17. **ENABLE VALIDATE làm gì?** Xác nhận dữ liệu hiện có tuân thủ constraint.
18. **ONLINE DDL có hoàn toàn không khóa không?** Không; vẫn có các giai đoạn metadata lock và tài nguyên bổ sung.
19. **DDL_LOCK_TIMEOUT điều khiển gì?** Thời gian session chờ DDL lock.
20. **Nếu migration history FAILED sau khi add column thành công thì làm gì?** Kiểm tra column definition, ghi checkpoint nếu đúng rồi tiếp tục step sau.
21. **Roll-forward là gì?** Chạy migration mới để đưa trạng thái hiện tại tới trạng thái mong muốn.
22. **Khi nào cần compensating migration?** Khi thay đổi đã commit và cần một nghiệp vụ bù để sửa hậu quả.
23. **Có thể dùng ROLLBACK để undo DROP TABLE không?** Không; cần backup/recovery hoặc bản sao dữ liệu.
24. **Vì sao cần dependency inventory trước contract?** Consumer ngoài database có thể không xuất hiện trong dictionary dependencies.
25. **Sau migration cần kiểm tra gì?** Schema, data, constraints, indexes, invalid objects, application workload và migration history.

Oracle implicit commit khiến DDL không thể được gom vào một transaction migration có thể rollback toàn bộ. Vì vậy, migration phải được thiết kế để chịu được lỗi sau bất kỳ bước nào: chia step nhỏ, lưu history/checkpoint, dùng migration mutex sống qua commit, kiểm tra data dictionary trước retry, backfill idempotent theo batch và giữ tương thích ngược bằng expand-contract. Online DDL giảm một số gián đoạn nhưng vẫn cần đánh giá lock/tài nguyên. Khi lỗi xảy ra, xác định trạng thái schema thật rồi resume, roll-forward hoặc chạy compensating migration; chỉ dùng restore khi cần phục hồi ở mức database. Hoàn tất migration phải được xác nhận bằng schema, dữ liệu, application behavior và checkpoint, không chỉ bằng exit code của runner.
