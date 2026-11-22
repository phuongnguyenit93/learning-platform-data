# Kiểm chứng SQL plan, driver, timezone, quyền và ứng dụng sau nâng cấp Oracle

## 1. Mục tiêu của kiểm chứng sau nâng cấp

Nâng cấp Oracle Database có thể thay đổi database release, Release Update (RU), optimizer behavior, data dictionary, timezone file, driver compatibility và một số mặc định cấu hình. Ứng dụng vẫn có thể khởi động thành công nhưng truy vấn chậm hơn, mapping thời gian sai, stored procedure thiếu quyền hoặc connection pool giữ session được tạo trước khi nâng cấp.

Vì vậy, kiểm chứng sau nâng cấp không dừng ở câu hỏi “database đã OPEN chưa?”. Cần chứng minh rằng các luồng nghiệp vụ quan trọng tiếp tục trả kết quả đúng, với hiệu năng và quyền truy cập nằm trong giới hạn đã thống nhất.

Bài học thuộc module **Database Engine Relational Oracle**, chương **Thay đổi và nâng cấp**, tập trung vào **kiểm chứng SQL plan, driver, timezone, quyền và ứng dụng sau nâng cấp**.

Năm nhóm cần xác nhận:

1. **SQL plan:** các SQL quan trọng vẫn dùng plan phù hợp, cardinality và runtime không suy giảm ngoài ngưỡng.
2. **Driver:** Oracle JDBC, JDK, connection pool, ORM và cấu hình TLS/wallet tương thích với database mới.
3. **Timezone:** database, session, JVM và ứng dụng diễn giải timestamp nhất quán, đặc biệt ở vùng có DST.
4. **Quyền:** runtime account vẫn có đúng object/system privileges, role, synonym và quyền gọi package.
5. **Ứng dụng:** transaction, connection pool, batch, scheduler, tích hợp và các luồng nghiệp vụ đều hoạt động.

Một đợt kiểm chứng tốt có baseline trước nâng cấp, môi trường thử nghiệm đại diện, tiêu chí pass/fail, bằng chứng sau nâng cấp và phương án rollback hoặc mitigation.

## 2. Phạm vi và nguyên tắc kiểm chứng

Trước khi chạy test, xác định rõ:
- Database nào được nâng cấp, CDB/PDB nào bị ảnh hưởng.
- Oracle Database release, RU và timezone file version trước/sau.
- Java runtime, Oracle JDBC driver, UCP hoặc pool khác.
- Spring Boot, Hibernate/JPA, framework và thư viện tích hợp.
- Những schema, service account, database link, job và external dependency liên quan.
- Các SQL/API/transaction quan trọng nhất.
- SLA về latency, throughput, lỗi và thời gian phục hồi.

### 2.1. Kiểm chứng theo rủi ro

Không cần đo mọi câu SQL với cùng mức độ. Ưu tiên:
- SQL có thời gian chạy hoặc CPU cao.
- SQL có nhiều lượt gọi.
- SQL có bind value phân bố lệch.
- SQL dùng partitioning, function, analytic, parallelism hoặc database link.
- Giao dịch cập nhật số dư, tồn kho, thanh toán và trạng thái đơn hàng.
- Query có timezone conversion hoặc so sánh ngày.
- Procedure/package dùng dynamic SQL hoặc quyền definer/invoker.
- Luồng chạy qua connection pool và nhiều tenant.

### 2.2. Phân biệt lỗi database với lỗi ứng dụng

Một lỗi sau nâng cấp có thể đến từ:
- Database hoặc optimizer.
- Driver/protocol.
- Cấu hình datasource/pool.
- Mapping ORM.
- Thay đổi quyền.
- Dữ liệu hoặc statistics.
- DNS, listener, TLS hoặc wallet.
- Thay đổi JVM, framework hoặc cấu hình triển khai.

Ghi lại tầng phát sinh lỗi, SQL_ID nếu có, Oracle error code, service, module/action và request ID. Tránh kết luận “Oracle upgrade gây lỗi” trước khi có bằng chứng.

### 2.3. Kiểm chứng trên môi trường tương đương production

Môi trường staging cần gần production về:
- Database release/RU và initialization parameters.
- Schema, object, index, partition và statistics.
- Dữ liệu có quy mô và phân bố đại diện.
- Service, PDB, network và authentication.
- Java/JDBC/pool/ORM version.
- Concurrency và workload.

Một database nhỏ với dữ liệu thử nghiệm ít không thể chứng minh SQL plan hoặc pool behavior sẽ giống production.

## 3. Thu thập baseline trước nâng cấp

Baseline là dữ liệu đối chiếu để biết điều gì đã thay đổi. Nếu chỉ đo sau nâng cấp, rất khó phân biệt regression mới với vấn đề đã tồn tại.

### 3.1. Database identity và version

Ghi lại thông tin phiên bản:

```sql
SELECT banner_full
FROM v$version
ORDER BY banner_full;
```

```sql
SELECT instance_name,
       host_name,
       version,
       version_full,
       status
FROM v$instance;
```

Trong CDB/PDB, ghi lại container hiện tại:

```sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM dual;
```

Ghi nhận database identity:

```sql
SELECT name,
       db_unique_name,
       open_mode,
       database_role,
       log_mode
FROM v$database;
```

Các dynamic performance view yêu cầu quyền phù hợp. Nếu runtime account không có quyền, DBA chạy phần inventory và cung cấp kết quả đã được phê duyệt.

### 3.2. Initialization parameters

Lưu các tham số có ảnh hưởng đến optimizer, memory, parallelism, cursor và session:

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name IN (
    'compatible',
    'optimizer_features_enable',
    'optimizer_mode',
    'cursor_sharing',
    'statistics_level',
    'parallel_degree_policy',
    'pga_aggregate_target',
    'sga_target',
    'open_cursors',
    'processes',
    'sessions',
    'timezone'
)
ORDER BY name;
```

Không sao chép toàn bộ parameter file sang môi trường mới mà không đánh giá thay đổi mặc định và tham số không còn được hỗ trợ. Mục đích baseline là phát hiện khác biệt và xác định tham số nào cần giữ/chỉnh.

### 3.3. Object và invalid objects

Lưu số lượng object theo owner/type/status:

```sql
SELECT owner,
       object_type,
       status,
       COUNT(*) AS object_count
FROM dba_objects
GROUP BY owner, object_type, status
ORDER BY owner, object_type, status;
```

Lưu danh sách invalid object:

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM dba_objects
WHERE status <> 'VALID'
ORDER BY owner, object_type, object_name;
```

Không phải mọi invalid object đều do nâng cấp, nhưng phải so sánh với baseline. Sau nâng cấp, xác định object nào cần compile lại và điều tra lỗi compile thay vì chỉ chạy compile hàng loạt rồi bỏ qua kết quả.

### 3.4. Baseline SQL và ứng dụng

Với SQL quan trọng, lưu:
- SQL text đã chuẩn hóa hoặc SQL_ID.
- Plan hash value và execution plan.
- Bind data type và các nhóm bind value đại diện.
- Elapsed time, CPU, buffer gets, physical reads.
- Rows processed và số lần thực thi.
- Parse count, version count nếu có.
- Wait events nổi bật.
- p50/p95/p99 latency ở tầng ứng dụng.

Ở tầng ứng dụng, lưu:
- Tỷ lệ request thành công/thất bại.
- Throughput.
- API latency p50/p95/p99.
- Pool active/idle/pending và acquisition latency.
- Batch duration, số bản ghi và lỗi.
- Transaction rollback/deadlock.
- Scheduler/job duration.
- Tỷ lệ lỗi JDBC và Oracle vendor code.

Baseline phải gắn với thời điểm, workload, dataset và cấu hình rõ ràng.

## 4. Xác nhận database sau nâng cấp

Trước khi kiểm thử ứng dụng, xác nhận database ở trạng thái có thể phục vụ và các thành phần cần thiết đã hoàn tất.

### 4.1. Kiểm tra database và PDB

```sql
SELECT name,
       open_mode,
       database_role
FROM v$database;
```

Trong CDB:

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Xác nhận đúng PDB, đúng service và trạng thái mở phù hợp. Một PDB mở READ ONLY hoặc RESTRICTED có thể làm một số tác vụ ứng dụng thất bại dù instance đang OPEN.

### 4.2. Kiểm tra registry và component

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

Kiểm tra trạng thái SQL patch:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Tên/cột và khả năng truy cập phụ thuộc release. Đối chiếu với upgrade guide và kết quả công cụ nâng cấp của phiên bản đang triển khai.

### 4.3. Kiểm tra invalid object sau upgrade

```sql
SELECT owner,
       object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
```

Nếu cần compile lại, dùng quy trình được DBA phê duyệt, ví dụ `utlrp.sql` theo hướng dẫn Oracle cho release đó. Sau khi compile, kiểm tra lại `DBA_OBJECTS` và `DBA_ERRORS`. Không coi việc script kết thúc là bằng chứng mọi object đã hợp lệ.

### 4.4. Alert log và dịch vụ

Kiểm tra:
- Alert log không còn lỗi startup/upgrade chưa xử lý.
- Listener đăng ký đúng service.
- PDB service đang hoạt động.
- Job cần thiết đã được bật theo kế hoạch.
- Archive/FRA, Data Guard hoặc backup job hoạt động nếu thuộc phạm vi.
- Các thành phần bảo mật/wallet mở được theo đúng quy trình.

Database OPEN chỉ là điều kiện ban đầu, chưa phải kết quả nghiệm thu.

## 5. Kiểm chứng SQL execution plan sau nâng cấp

Optimizer có thể chọn plan khác sau nâng cấp vì thay đổi phiên bản, `OPTIMIZER_FEATURES_ENABLE`, statistics, histogram, adaptive behavior, cardinality estimate hoặc cấu hình hệ thống.

Plan hash thay đổi không tự động có nghĩa regression. Ngược lại, plan hash giống nhau cũng không bảo đảm latency giống nhau nếu dữ liệu, cache, concurrency hoặc I/O thay đổi.

### 5.1. Chọn SQL quan trọng

Tạo danh sách SQL theo nghiệp vụ:
- Đăng nhập và tải dashboard.
- Tìm kiếm khách hàng/đơn hàng.
- Tạo đơn, cập nhật tồn kho và thanh toán.
- Báo cáo ngày/tháng.
- Batch import/export.
- Stored procedure chạy định kỳ.
- SQL truy cập database link.
- SQL có bind values lệch mạnh.

Mỗi SQL cần owner nghiệp vụ và tiêu chí hiệu năng.

### 5.2. Xem plan thực tế

Sau khi chạy câu SQL đại diện với runtime statistics, có thể xem cursor plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

Nếu dùng SQL_ID hiện tại của session, có thể lấy từ `V$SQL` hoặc công cụ giám sát. `ALLSTATS LAST` hữu ích khi statistics thực thi được thu thập, ví dụ qua `GATHER_PLAN_STATISTICS` hoặc cấu hình phù hợp.

Cần quyền đọc cursor và các view liên quan. Không đưa bind values nhạy cảm vào báo cáo hoặc log chia sẻ.

### 5.3. So sánh plan trước và sau

Đối chiếu:
- Plan hash value.
- Join order và join method.
- Access path: index range scan, unique scan, full scan, partition scan.
- Predicate access/filter.
- Estimated rows so với actual rows.
- Buffer gets và physical reads.
- Sort/hash operation và spill.
- Remote operation nếu có database link.
- Parallel execution.
- Adaptive plan và child cursor.

Không chỉ so sánh plan hash. Hãy đọc các operation và số liệu thực thi.

### 5.4. Estimated rows và actual rows

Chênh lệch lớn giữa `E-Rows` và `A-Rows` có thể khiến optimizer chọn join method hoặc access path không phù hợp.

Nguyên nhân có thể là:
- Statistics cũ hoặc chưa đại diện.
- Histogram không phù hợp.
- Data skew.
- Bind peeking/adaptive cursor sharing.
- Correlation giữa các cột.
- Predicate dùng function hoặc implicit conversion.
- Partition pruning không xảy ra như mong đợi.

Sau nâng cấp, không vội gather statistics toàn bộ schema trong production nếu chưa đánh giá. Thu thập statistics có thể thay đổi plan hàng loạt. Dùng kế hoạch statistics có kiểm soát, so sánh và có phương án phục hồi.

### 5.5. Kiểm tra nhiều nhóm bind value

Một SQL có thể chạy tốt với bind value phổ biến nhưng rất chậm với giá trị hiếm hoặc tenant có dữ liệu lớn.

Chạy test với:
- Giá trị có selectivity cao.
- Giá trị có selectivity thấp.
- Tenant nhỏ và tenant lớn.
- Khoảng ngày ngắn và dài.
- NULL nếu SQL hỗ trợ.
- Các kiểu bind thực tế của JDBC.

Không chỉ chạy một giá trị mẫu rồi kết luận SQL ổn định.

### 5.6. SQL Plan Management

SQL Plan Management (SPM) có thể giúp quản lý và kiểm soát các SQL plan đã được chấp nhận. DBA có thể inventory SQL plan baseline:

```sql
SELECT sql_handle,
       plan_name,
       enabled,
       accepted,
       fixed,
       reproduced
FROM dba_sql_plan_baselines
ORDER BY sql_handle, plan_name;
```

SPM có thể hữu ích khi cần giữ plan đã được xác nhận trong giai đoạn chuyển đổi. Tuy nhiên:
- Baseline phải được capture/transport và kiểm tra đúng SQL.
- Plan cũ phải còn reproduce được trên database mới.
- Không cố định plan xấu chỉ vì nó là plan trước nâng cấp.
- Baseline không thay thế kiểm thử workload và dữ liệu.
- Cần quản lý lifecycle để tránh tích lũy baseline không cần thiết.

Các thủ tục SPM và quyền cần theo tài liệu Oracle release đang dùng.

### 5.7. Optimizer parameter không phải nút rollback duy nhất

`OPTIMIZER_FEATURES_ENABLE` có thể điều khiển tập optimizer feature theo release, nhưng hạ giá trị này không phải cách sửa chung cho mọi regression. Thay đổi tham số có thể ảnh hưởng nhiều SQL khác.

Nếu cần mitigation:
1. Xác định SQL cụ thể bị regression.
2. Thu thập plan và runtime evidence.
3. Xác định nguyên nhân.
4. Thử statistics, SQL patch/baseline hoặc điều chỉnh SQL trong staging.
5. Đánh giá tác động rộng trước khi áp dụng production.

## 6. Kiểm chứng statistics, index và partition

### 6.1. Statistics

Kiểm tra thời điểm statistics:

```sql
SELECT owner,
       table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM dba_tab_statistics
WHERE owner IN ('APP', 'SALES')
ORDER BY owner, table_name;
```

Tên schema là ví dụ. Kiểm tra cả:
- Table statistics.
- Column statistics.
- Histogram.
- Index statistics.
- Partition/subpartition statistics.
- Extended statistics nếu có.

Không dùng `NUM_ROWS` như số hàng chính xác tức thời; đây là thông tin thống kê được thu thập.

### 6.2. Index status

```sql
SELECT owner,
       index_name,
       table_name,
       status,
       visibility,
       uniqueness
FROM dba_indexes
WHERE owner IN ('APP', 'SALES')
ORDER BY owner, table_name, index_name;
```

Với partitioned index, kiểm tra thêm trạng thái từng partition/subpartition qua dictionary views tương ứng. Index UNUSABLE hoặc invisible ngoài dự kiến có thể làm thay đổi plan.

### 6.3. Partition pruning

Nếu SQL lọc theo partition key, xác nhận plan có pruning đúng. Predicate có implicit conversion hoặc function bọc cột có thể làm mất pruning.

So sánh partition được truy cập trước/sau và kiểm thử nhiều khoảng thời gian. Không chỉ xem query có trả đúng dữ liệu; phải xem nó có quét quá nhiều partition hay không.

### 6.4. Không rebuild mọi index sau upgrade theo thói quen

Rebuild index không phải bước mặc định để “làm database nhanh hơn” sau mọi nâng cấp. Chỉ thực hiện khi có lý do kỹ thuật, bằng chứng và change plan. Rebuild có thể tiêu thụ I/O, redo, space và ảnh hưởng workload.

## 7. Kiểm chứng Oracle JDBC driver và Java runtime

Database upgrade có thể yêu cầu hoặc khuyến nghị phiên bản Oracle JDBC driver khác. Driver phải tương thích với:
- Oracle Database release/RU.
- Java/JDK version.
- JDBC API level.
- Thin hoặc OCI mode.
- UCP/connection pool.
- TLS, wallet và authentication.
- Framework ORM và thư viện phụ thuộc.

### 7.1. Inventory driver đang chạy

Trong Java, lấy metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
    System.out.println(metadata.getJDBCMajorVersion());
    System.out.println(metadata.getJDBCMinorVersion());
}
```

Trong môi trường production, ghi metadata vào diagnostics được bảo vệ, không in credential hoặc dữ liệu nhạy cảm.

Ghi thêm:
- JDK vendor/version.
- Oracle JDBC artifact/version.
- UCP version nếu dùng.
- HikariCP hoặc pool version.
- Spring Boot version.
- Hibernate version.
- Các extension/custom type handler.

### 7.2. Kiểm tra dependency tree

Đảm bảo ứng dụng không vô tình nạp hai phiên bản `ojdbc` hoặc hai bản thư viện Oracle khác nhau qua dependency transitive.

Với Maven:

```bash
mvn dependency:tree
```

Với Gradle:

```bash
./gradlew dependencies
```

Đối chiếu runtime artifact thực tế trong container/application package, vì dependency tree ở source chưa chắc phản ánh classpath của image đang chạy.

### 7.3. Kiểm tra driver/database compatibility

Dùng ma trận hỗ trợ Oracle chính thức cho:
- Database release và RU.
- JDK release.
- JDBC driver family.
- UCP nếu dùng.
- Authentication/TLS feature cần thiết.

Không chọn driver chỉ vì version number lớn hơn. Một driver mới có thể thay đổi behavior, deprecate API hoặc yêu cầu JDK khác.

### 7.4. Smoke test JDBC cơ bản

Chạy qua đúng datasource/pool của ứng dụng:

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(3)) {
        throw new IllegalStateException("Oracle connection is not valid");
    }

    try (PreparedStatement statement =
                 connection.prepareStatement("SELECT 1 FROM dual");
         ResultSet resultSet = statement.executeQuery()) {

        if (!resultSet.next() || resultSet.getInt(1) != 1) {
            throw new IllegalStateException("Unexpected Oracle response");
        }
    }
}
```

`Connection.isValid()` phụ thuộc driver và có thể thực hiện network round-trip. Không dùng nó như test duy nhất; cần test transaction, fetch, bind, LOB và stored procedure.

### 7.5. Kiểm tra kiểu dữ liệu JDBC

Ưu tiên kiểm thử các mapping ứng dụng thật sự sử dụng:
- `NUMBER` ↔ `BigDecimal`.
- DATE/TIMESTAMP ↔ Java date/time type.
- CLOB/BLOB.
- RAW/UUID mapping nếu có.
- ARRAY/STRUCT hoặc Oracle-specific types.
- REF CURSOR.
- Boolean mapping qua NUMBER/CHAR nếu ứng dụng có quy ước.
- Generated keys và sequence/identity.
- Batch update và OUT parameters.

Đối chiếu cả null, precision, scale, timezone và dữ liệu biên.

### 7.6. Kiểm tra TLS, wallet và authentication

Nếu ứng dụng dùng TCPS, Oracle Wallet, mTLS, Kerberos, token hoặc external authentication, test trên đúng runtime/container:
- Trust chain và certificate expiry.
- Wallet path và file permissions.
- Alias/service descriptor.
- JDK truststore.
- TLS protocol/cipher được phép.
- Rotation certificate/secret.
- Authentication mode của driver.

Một kết nối SQL Developer thành công trên máy DBA không chứng minh Java container có cùng wallet hoặc truststore.

## 8. Kiểm chứng connection pool và session behavior

Driver mới hoặc database upgrade có thể làm lộ vấn đề ở pool:
- Connection idle bị firewall đóng.
- Validation behavior thay đổi.
- Session state không được reset.
- Statement cache giữ cursor không phù hợp.
- Timeout hoặc failover behavior khác.
- Pool tạo connection vượt session limit.

### 8.1. Kiểm tra pool metrics

Ghi nhận:
- Active/idle/total connections.
- Pending borrowers.
- Acquisition latency.
- Connection creation latency.
- Validation failures.
- Evicted connections.
- Connection timeout count.
- Leak detection warnings.
- Maximum lifetime và idle timeout.

So sánh trước/sau dưới cùng concurrency và workload.

### 8.2. Test stale connection và restart/failover

Trong staging:
1. Mở connection qua pool.
2. Để idle theo khoảng thời gian có kiểm soát.
3. Mô phỏng network interruption hoặc database service restart.
4. Mượn lại connection.
5. Xác nhận connection hỏng bị phát hiện và loại bỏ.
6. Xác nhận pool tạo connection mới và request hồi phục trong deadline.

Không thực hiện fault injection trên production nếu chưa có change approval và kế hoạch bảo vệ.

### 8.3. Session state

Kiểm tra:
- NLS session parameters.
- `CURRENT_SCHEMA`.
- `SESSIONTIMEZONE`.
- Application context.
- `CLIENT_IDENTIFIER`, module/action.
- Auto-commit/isolation.
- Temporary table/package state nếu ứng dụng dùng.

Đảm bảo mọi trạng thái request-specific được thiết lập và reset theo vòng đời connection. Pool không tự biết mọi lệnh `ALTER SESSION` hoặc `DBMS_SESSION.SET_CONTEXT` mà ứng dụng đã chạy.

### 8.4. Statement cache

Oracle JDBC implicit/explicit statement cache có thể ảnh hưởng parse và cursor reuse. Sau upgrade/driver change:
- Xác nhận cache size và cấu hình.
- Kiểm tra statement close lifecycle.
- Kiểm tra child cursor/version count.
- Kiểm tra bind metadata ổn định.
- Kiểm tra lỗi invalid cursor hoặc statement reuse.
- Đo parse count và latency.

Không tăng cache size chỉ để giảm parse mà chưa xem open cursors và workload.

## 9. Kiểm chứng timezone giữa Oracle, JDBC và JVM

Timezone là một trong những khu vực dễ phát sinh lỗi âm thầm vì cùng một thời điểm có thể được biểu diễn bằng local time, offset hoặc timezone region.

Cần phân biệt:
- Database time zone.
- Session time zone.
- Timezone file của Oracle.
- JVM default time zone.
- Timezone của ứng dụng/người dùng.
- Timezone region và UTC offset.

### 9.1. Kiểm tra timezone trong Oracle

```sql
SELECT dbtimezone,
       sessiontimezone
FROM dual;
```

Timezone file/version:

```sql
SELECT filename,
       version
FROM v$timezone_file;
```

`DBTIMEZONE` và `SESSIONTIMEZONE` có ý nghĩa khác nhau. Đừng giả định session timezone luôn bằng database timezone hoặc JVM timezone.

### 9.2. Kiểm tra JVM timezone

Trong Java:

```java
ZoneId systemZone = ZoneId.systemDefault();
ZoneId utc = ZoneId.of("UTC");

System.out.println(systemZone);
System.out.println(ZoneRulesProvider.getVersions(systemZone.getId()).lastKey());
```

Kiểm tra timezone JVM trong container/runtime thực tế, không chỉ trên máy build. `TZ`, JVM startup option và image base có thể làm default zone khác giữa các môi trường.

### 9.3. Phân biệt các kiểu Oracle thời gian

| Oracle type | Đặc tính |
|---|---|
| `DATE` | Ngày và giờ đến giây, không lưu timezone |
| `TIMESTAMP` | Ngày/giờ với fractional seconds, không lưu timezone |
| `TIMESTAMP WITH TIME ZONE` | Có timezone displacement hoặc region information |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Chuẩn hóa theo database time zone khi lưu và hiển thị theo session time zone khi đọc |

Không đổi kiểu cột hoặc mapping ORM trong quá trình upgrade mà chưa kiểm tra semantics dữ liệu hiện tại.

### 9.4. DST và timezone region

Một offset như `+07:00` không chứa quy tắc lịch sử hoặc tương lai của một khu vực. Timezone region như `Europe/Paris` có quy tắc daylight saving time (DST) thay đổi theo ngày và có thể thay đổi theo luật.

Khi ứng dụng lưu lịch hẹn hoặc sự kiện tương lai theo địa điểm, region thường mang nhiều thông tin hơn offset cố định. Khi lưu một thời điểm đã xảy ra, UTC instant là cách biểu diễn thuận tiện cho việc so sánh và trao đổi.

### 9.5. Kiểm tra timezone file sau upgrade

Timezone file Oracle có version riêng. Upgrade database hoặc áp dụng RU có thể đi kèm thay đổi timezone file và quy trình DST upgrade. Cần:
- Ghi version trước/sau.
- Đọc upgrade guide cho release.
- Xác định dữ liệu/column có timezone-sensitive.
- Lập kế hoạch nâng version timezone file nếu cần.
- Dùng quy trình `DBMS_DST` phù hợp với release.
- Test dữ liệu ở các thời điểm chuyển DST.
- Không tự chạy `DBMS_DST` production ngoài change plan.

Timezone file mới có thể thay đổi cách Oracle diễn giải một số region/date lịch sử hoặc tương lai. Không coi đây chỉ là thay đổi hiển thị.

### 9.6. TIMESTAMP WITH LOCAL TIME ZONE

Giá trị được chuẩn hóa theo database time zone khi lưu và chuyển sang session time zone khi truy vấn. Vì thế cùng một dữ liệu có thể hiển thị khác nhau ở hai session timezone nhưng vẫn đại diện cùng thời điểm.

Test với:
- Session timezone UTC.
- Session timezone nghiệp vụ.
- Thời điểm trước/sau DST.
- Các giá trị gần nửa đêm.
- Dữ liệu có fractional seconds.

Không so sánh chuỗi hiển thị để xác định hai timestamp có cùng instant hay không.

## 10. Mapping Java time và JDBC sau nâng cấp

Java Time API cung cấp các kiểu khác nhau:

| Java type | Ý nghĩa |
|---|---|
| `Instant` | Một thời điểm trên timeline UTC |
| `OffsetDateTime` | Date/time kèm offset cụ thể |
| `ZonedDateTime` | Date/time kèm timezone region và rules |
| `LocalDateTime` | Date/time không có timezone |
| `LocalDate` | Chỉ ngày |
| `LocalTime` | Chỉ giờ |

### 10.1. Chọn kiểu theo semantics

- Sự kiện đã xảy ra, cần so sánh toàn cục: cân nhắc `Instant`.
- Thời điểm kèm offset đã biết: `OffsetDateTime`.
- Lịch địa phương gắn với region và DST: lưu region riêng hoặc dùng `ZonedDateTime` ở domain.
- Ngày nghiệp vụ không có giờ: `LocalDate`.
- Giờ mở cửa không gắn ngày: `LocalTime`.
- `LocalDateTime` chỉ phù hợp khi nghiệp vụ thực sự không có timezone; không dùng nó như một instant.

### 10.2. JDBC 4.2 và typed mapping

Driver hỗ trợ JDBC 4.2 có thể hỗ trợ `setObject`/`getObject` với một số Java Time types. Hành vi cụ thể phụ thuộc Oracle JDBC version và Oracle column type.

Ví dụ cần kiểm thử trên driver thực tế:

```java
OffsetDateTime input = OffsetDateTime.now(ZoneOffset.UTC);

try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO app.event_log(event_time_tz) VALUES (?)")) {
    statement.setObject(1, input);
    statement.executeUpdate();
}
```

Đọc lại:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT event_time_tz FROM app.event_log WHERE event_id = ?")) {
    statement.setLong(1, eventId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            OffsetDateTime value =
                    resultSet.getObject(1, OffsetDateTime.class);
        }
    }
}
```

Không giả định mọi driver version map mọi Java Time type giống nhau. Có thể cần `getTimestamp`, `Calendar` hoặc mapping riêng theo cột và driver.

### 10.3. Không dùng Timestamp để mang timezone region

`java.sql.Timestamp` biểu diễn timestamp nhưng không mang đầy đủ timezone region như `Europe/Paris`. Nếu cần giữ region, lưu region ID riêng hoặc dùng một mapping domain rõ ràng.

### 10.4. Kiểm tra Spring/Hibernate mapping

Sau khi đổi driver hoặc Hibernate:
- Kiểm tra JDBC type được bind cho `LocalDateTime`, `OffsetDateTime`, `Instant`.
- Kiểm tra column type thật.
- Kiểm tra Hibernate timezone storage strategy nếu có.
- Kiểm tra `hibernate.jdbc.time_zone` nếu ứng dụng dùng.
- Kiểm tra JSON serialization/deserialization.
- Kiểm tra precision fractional seconds.
- Kiểm tra null và boundary.

Không đổi `hibernate.jdbc.time_zone` chỉ để làm một test pass; xác định semantics dữ liệu trước.

## 11. Kiểm chứng quyền và danh tính runtime

Sau nâng cấp, application account có thể gặp lỗi `ORA-01031`, `ORA-00942`, `PLS-00201` hoặc lỗi execute package dù schema object vẫn tồn tại.

Nguyên nhân thường gặp:
- Grant bị thiếu hoặc khác giữa PDB.
- User/role không được tạo trong container đúng.
- Quyền được cấp qua role nhưng PL/SQL definer-rights cần direct grant.
- Synonym trỏ tới object khác hoặc object invalid.
- Account bị khóa/hết hạn.
- Proxy authentication hoặc common/local user thay đổi.
- Quyền trên sequence, directory, DB link hoặc network ACL thiếu.

### 11.1. Xác nhận danh tính trong session ứng dụng

Từ connection thực tế của ứng dụng:

```sql
SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_USER') AS current_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
```

Đừng chỉ đăng nhập SQL Developer bằng một tài khoản gần giống rồi kết luận quyền của application account đúng.

### 11.2. Kiểm tra object privileges

DBA có thể kiểm tra:

```sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
FROM dba_tab_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, owner, table_name, privilege;
```

Column-level grants:

```sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege
FROM dba_col_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, owner, table_name, column_name;
```

### 11.3. Kiểm tra system privileges và roles

```sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, privilege;
```

```sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, granted_role;
```

Trong session ứng dụng:

```sql
SELECT * FROM session_roles;
SELECT * FROM session_privs;
```

So sánh quyền thực tế sau đăng nhập, không chỉ danh sách grant dự kiến.

### 11.4. Direct grant và definer-rights PL/SQL

Stored procedure/package mặc định thường chạy với quyền definer (`AUTHID DEFINER`). Static SQL bên trong definer-rights unit không dùng privilege chỉ được thừa hưởng qua role của owner theo quy tắc Oracle.

Nếu package owner truy cập table khác schema, cần direct object grant phù hợp cho owner. Một ứng dụng có thể chạy SELECT trực tiếp nhờ role nhưng gọi procedure tương ứng lại nhận lỗi thiếu quyền.

Ví dụ DBA cấp direct grant:

```sql
GRANT SELECT ON sales.customer TO app_owner;
```

Không giải quyết bằng cách cấp DBA hoặc quyền `ANY` quá rộng. Cấp đúng object privilege cần thiết.

### 11.5. AUTHID DEFINER và AUTHID CURRENT_USER

- `AUTHID DEFINER`: quyền thực thi dựa trên owner của program unit theo quy tắc definer-rights.
- `AUTHID CURRENT_USER`: thực thi theo invoker/current user với semantics invoker-rights.

Thay đổi `AUTHID` có thể thay đổi security boundary. Không đổi chỉ để vượt qua lỗi quyền sau upgrade; cần review bảo mật và test đầy đủ.

### 11.6. Kiểm tra object, synonym và sequence

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM dba_objects
WHERE owner IN ('APP', 'SALES')
  AND status <> 'VALID'
ORDER BY owner, object_type, object_name;
```

Kiểm tra synonym:

```sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM dba_synonyms
WHERE owner IN ('APP', 'PUBLIC')
ORDER BY owner, synonym_name;
```

Kiểm tra quyền sequence và object được package sử dụng. Một synonym hợp lệ về mặt metadata không chứng minh runtime account có quyền truy cập object đích.

### 11.7. PDB và common/local user

Trong multitenant, phân biệt:
- Common user/role ở cấp CDB.
- Local user/role trong một PDB.
- Common grant và local grant.
- Object nằm trong PDB cụ thể.
- Service kết nối tới đúng PDB.

Một grant ở container này không tự động có nghĩa runtime session trong PDB khác có quyền tương tự. Chạy kiểm tra ở đúng container và service ứng dụng.

### 11.8. Account status và password policy

Kiểm tra account status, expiry, profile, proxy authentication và password rotation theo policy. Không đưa password vào báo cáo kiểm chứng. Xác nhận secret manager, wallet hoặc vault đã cập nhật đúng cho ứng dụng sau deployment.

## 12. Kiểm chứng stored procedure, job và external access

Một số ứng dụng không chỉ truy cập table:
- Gọi package/procedure/function.
- Dùng sequence/identity.
- Ghi file qua directory object.
- Gọi external procedure.
- Truy cập database link.
- Gọi HTTP endpoint qua ACL/network package.
- Chạy scheduler job.

Tạo danh sách API database được sử dụng và kiểm thử bằng đúng runtime identity. Kiểm tra:
- Package/function status VALID.
- `EXECUTE` privilege.
- Direct grants cho definer-rights owner.
- Argument datatype và overload.
- OUT parameter/cursor.
- Scheduler credential/job state.
- Directory object và quyền OS liên quan.
- DB link service/credential.
- Network ACL/host permission nếu có sử dụng.

Đừng chỉ chạy unit test trên repository SELECT. Một package báo cáo, batch hoặc job chạy đêm có thể là nơi đầu tiên lộ lỗi quyền.

## 13. Kiểm chứng ứng dụng Spring Boot/JPA sau nâng cấp

Ứng dụng cần được test qua đúng đường chạy production: cùng image, JDK, datasource, pool, ORM, secret và service name.

### 13.1. Startup smoke test

Xác nhận:
- Application context khởi động.
- DataSource tạo được connection.
- Flyway/Liquibase migration không chạy ngoài kế hoạch.
- Hibernate schema validation thành công nếu được bật.
- Health/readiness endpoint đúng.
- Không có lỗi class loading hoặc driver incompatibility.
- Không có connection pool leak ngay lúc startup.

Không cho phép migration tự động chạy trong production nếu release plan yêu cầu migration được quản lý riêng.

### 13.2. Repository và transaction test

Test:
- SELECT theo primary key và filter.
- INSERT/UPDATE/DELETE.
- Transaction rollback.
- Unique/foreign key.
- Optimistic locking.
- Pessimistic lock nếu dùng.
- Batch operation.
- Stored procedure call.
- Pagination/sorting.
- Native query.
- LOB/large result.
- Lazy/eager loading.
- Multi-tenant/VPD context nếu có.

Kiểm tra cả kết quả dữ liệu và số lượng statement/latency. Một repository vẫn trả đúng dữ liệu nhưng tạo nhiều query hơn sau nâng cấp có thể gây regression.

### 13.3. Transaction boundary

Xác nhận `@Transactional` vẫn được áp dụng đúng:
- Đúng transaction manager.
- Đúng datasource/persistence unit.
- Proxy được gọi đúng cách.
- Rollback rule không đổi ngoài ý muốn.
- Isolation level phù hợp.
- Connection được trả về pool.
- Không có self-invocation làm bỏ qua transaction proxy.

### 13.4. Batch và scheduler

Chạy thử:
- Job theo lịch.
- Batch import/export.
- Retry/restart job.
- Lock tránh chạy trùng.
- Checkpoint và resume.
- Thời gian chạy với dữ liệu đại diện.
- Quyền file/directory hoặc remote database nếu có.

Không chạy hai job production đồng thời chỉ để kiểm tra nếu job không idempotent hoặc chưa có cơ chế chống trùng.

### 13.5. End-to-end business flow

Chọn các luồng đại diện:
1. Xác thực và tạo session.
2. Đọc dữ liệu tham chiếu.
3. Tạo giao dịch.
4. Cập nhật trạng thái và ghi audit.
5. Phát event hoặc gọi hệ thống ngoài.
6. Đọc lại kết quả.
7. Báo cáo/đối soát.

Kiểm tra dữ liệu cuối, side effect, latency và log correlation. Test phải xác nhận nghiệp vụ đúng, không chỉ HTTP 200.

## 14. Kiểm chứng connection pool và session state sau deployment

Khi deploy application mới, pool thường tạo connection mới, nhưng rolling deployment có thể để process cũ chạy song song. Cần xác nhận cả process mới lẫn process cũ theo chiến lược rollout.

Kiểm tra:
- Pool size/connection timeout.
- Validation và stale connection eviction.
- Maximum lifetime/idle timeout.
- Driver socket/connect/read timeout.
- Statement cache.
- Session NLS baseline.
- Application context initialize/reset.
- `CLIENT_IDENTIFIER`, module/action.
- Timezone session.
- Connection leak và transaction duration.

### 14.1. Không chỉ test connection đầu tiên

Pool có thể có nhiều physical connection với session state khác nhau. Test nhiều lần borrow/return, ép reuse cùng connection trong môi trường test và kiểm tra state ở mỗi lần.

### 14.2. Reset session state

Nếu ứng dụng thay đổi `ALTER SESSION`, NLS, application context hoặc module/action, cần reset khi request/transaction kết thúc. `Connection.close()` trong pool thường chỉ trả logical connection về pool, không đảm bảo xóa mọi Oracle session state.

### 14.3. Rolling deployment

Trong rollout nhiều instance:
- Xác nhận mọi pod/process dùng cùng driver/config được phê duyệt.
- Theo dõi pool metrics từng instance.
- Không để phiên bản cũ kết nối vào database mới nếu chưa nằm trong compatibility matrix.
- Drain connection và request trước khi dừng instance.
- Theo dõi lỗi theo application version.

## 15. Kiểm thử chức năng và dữ liệu biên

Sau nâng cấp, chạy regression test có dữ liệu biên:
- NUMBER precision/scale lớn.
- NULL và empty string theo semantics Oracle.
- Unicode và collation.
- DATE/TIMESTAMP với fractional seconds.
- Timestamp có timezone region/offset.
- Dữ liệu gần DST transition.
- CLOB/BLOB lớn.
- Chuỗi dài và ký tự đặc biệt.
- Partition boundary.
- Nhiều tenant và dữ liệu skew.
- Constraint và concurrent update.

Đặc biệt kiểm tra implicit conversion. SQL có thể vẫn compile nhưng cho kết quả khác do NLS hoặc kiểu bind thay đổi.

## 16. Performance test và tiêu chí pass/fail

### 16.1. So sánh workload cùng điều kiện

Giữ ổn định:
- Dataset và data distribution.
- Warm/cold cache state hoặc ghi rõ khác biệt.
- Concurrency.
- Thời lượng test.
- Bind value mix.
- JVM heap/CPU.
- Pool size.
- Network path.
- Background job load.

Không so sánh một lần test database cache nóng với một lần cache lạnh rồi kết luận regression.

### 16.2. Metric cần so sánh

| Metric | Mục đích |
|---|---|
| API p50/p95/p99 | Độ trễ người dùng |
| Throughput | Năng lực xử lý |
| SQL elapsed/CPU | Chi phí query |
| Buffer gets | Logical I/O |
| Physical reads | I/O storage |
| Rows processed | Khối lượng kết quả |
| Parse count | Chi phí parse |
| Pool acquisition latency | Áp lực connection |
| Active sessions | Concurrency database |
| Wait events | Bottleneck |
| Error/rollback rate | Độ ổn định nghiệp vụ |
| Batch duration | Khả năng xử lý nền |

### 16.3. Đặt ngưỡng trước khi test

Ví dụ minh họa:
- Không có lỗi nghiệp vụ hoặc sai dữ liệu.
- Không có lỗi quyền ngoài danh sách đã chấp nhận.
- API p95 không tăng quá ngưỡng SLA được phê duyệt.
- SQL critical không tăng logical I/O vượt ngưỡng.
- Batch hoàn thành trong cửa sổ.
- Pool không có pending borrower kéo dài.
- Không phát sinh timezone offset ngoài mong đợi.

Ngưỡng phải được chủ hệ thống/owner nghiệp vụ phê duyệt. Không dùng một tỷ lệ phần trăm chung cho mọi ứng dụng.

## 17. Canary và rollout theo giai đoạn

Nếu kiến trúc cho phép, rollout có thể theo các bước:
1. Kiểm chứng trên clone/staging.
2. Chạy smoke và regression.
3. Chuyển một workload/instance canary.
4. Theo dõi lỗi, latency, SQL plan và pool metrics.
5. Mở rộng theo từng nhóm.
6. Kiểm tra batch/scheduler sau khi traffic ổn định.
7. Kết thúc rollout và lưu evidence.

Canary cần có khả năng cô lập và rollback. Nếu database đã được nâng cấp và không thể chạy đồng thời application cũ/new theo compatibility matrix, cần chọn chiến lược phù hợp thay vì tự ý trộn phiên bản.

### 17.1. Tiêu chí dừng rollout

Dừng mở rộng nếu:
- Sai dữ liệu hoặc sai timezone.
- Quyền bị mở rộng ngoài dự kiến.
- SQL critical có regression vượt ngưỡng.
- Tỷ lệ lỗi JDBC tăng.
- Pool cạn hoặc session tăng bất thường.
- Batch/job không hoàn thành.
- Có dấu hiệu transaction in-doubt hoặc lỗi consistency.

### 17.2. Rollback và forward fix

Rollback application image có thể đơn giản hơn rollback database upgrade. Sau khi data dictionary hoặc compatibility level đã thay đổi, không giả định có thể downgrade bằng cách đổi binary hoặc restore snapshot một cách tùy tiện.

Runbook phải xác định:
- Có thể rollback application không?
- Database downgrade có được hỗ trợ cho đường nâng cấp này không?
- Backup/restore point đã sẵn sàng chưa?
- Data migration có tương thích ngược không?
- Credential/driver/schema có thể coexist không?
- Ai quyết định rollback hay forward fix?

## 18. Runbook kiểm chứng theo thứ tự

Một trình tự thực tế:

### Trước nâng cấp
1. Inventory database, PDB, service, version/RU và timezone file.
2. Inventory JDK, JDBC, pool, Spring Boot, Hibernate và artifact triển khai.
3. Lưu SQL critical, execution plan, runtime metrics và bind data type.
4. Lưu NLS/timezone/session parameters.
5. Lưu object status, grants, roles, synonyms, jobs và account status.
6. Lưu application smoke/regression results.
7. Xác nhận backup và rollback/restore plan.

### Sau nâng cấp database
1. Xác nhận database/PDB/service state.
2. Kiểm tra registry, SQL patch và alert log.
3. Kiểm tra invalid objects và compile errors.
4. Kiểm tra timezone file và DST status.
5. Kiểm tra schema, index, partition và statistics.
6. Kiểm tra quyền và danh tính runtime trong đúng PDB.

### Sau nâng cấp application/driver
1. Xác nhận runtime JDK và JDBC driver thực tế.
2. Tạo connection qua pool production-like.
3. Test TLS/wallet/authentication.
4. Test NLS/session context.
5. Test typed JDBC mapping, transaction và procedure.
6. Test pool reuse/stale connection.
7. Test repository, batch và scheduler.

### Nghiệm thu
1. Chạy SQL workload đại diện.
2. So sánh plan và runtime với baseline.
3. Chạy end-to-end business flows.
4. Đo p50/p95/p99, throughput và pool health.
5. Đối chiếu timezone, quyền và dữ liệu.
6. Thu thập evidence, ghi deviation và quyết định go/no-go.

## 19. Ma trận kiểm chứng

| Nhóm | Kiểm tra | Bằng chứng cần lưu |
|---|---|---|
| Database | Version, RU, PDB/service, registry | Query output và change record |
| Object | Invalid objects, index/partition status | Dictionary query và compile log |
| SQL plan | Plan, actual rows, buffer gets, latency | DBMS_XPLAN và workload report |
| Statistics | Last analyzed, stale stats, histogram | DBA statistics views |
| JDBC | Driver/JDK/version, connect, bind/fetch | Runtime metadata và integration test |
| Pool | Active/idle/pending, eviction, timeout | Pool metrics và test log |
| Timezone | DB/session/JVM/file version, DST | SQL/Java test output |
| Privileges | Session user, roles, direct grants, object access | Dictionary views và runtime tests |
| Application | API, transaction, batch, scheduler | Regression results và application logs |
| Operations | Alert log, monitoring, rollback readiness | Runbook sign-off |

## 20. Troubleshooting theo triệu chứng

| Triệu chứng | Hướng kiểm tra đầu tiên |
|---|---|
| Query trả đúng nhưng chậm | Plan, actual rows, statistics, wait events, bind mix |
| `ORA-01031` | Runtime principal, direct grants, role, definer-rights package |
| `ORA-00942` | Current schema, synonym, PDB, object owner và quyền |
| `ORA-01882` hoặc timezone region error | Timezone region/file version, JVM tzdata, driver |
| Ngày/giờ lệch | DATE/TIMESTAMP semantics, session timezone, JVM zone, mapping |
| Numeric conversion khác | NLS numeric characters, implicit conversion, bind type |
| App khởi động nhưng query fail | Driver compatibility, service/PDB, account/grants |
| Lỗi chỉ xuất hiện ngẫu nhiên | Pool session state, connection reuse, child cursor/bind skew |
| Stored procedure fail nhưng SELECT thành công | Direct grants, AUTHID, package status |
| Batch chậm hoặc timeout | Plan, fetch/batch size, pool, locks và commit frequency |
| TLS handshake fail | Wallet/truststore, certificate, protocol, driver/JDK |
| Một số pod lỗi, pod khác không | Runtime image, secret/config drift, driver classpath |

Điều tra theo timestamp và application version. So sánh một request thành công với một request thất bại để tìm khác biệt về service, session, bind, context và connection.

## 21. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách làm phù hợp |
|---|---|---|
| Chỉ kiểm tra database OPEN | Bỏ sót lỗi driver, quyền, plan và nghiệp vụ | Có ma trận kiểm chứng nhiều lớp |
| So sánh plan hash duy nhất | Bỏ qua runtime và cardinality | Đọc plan, A-Rows, I/O và latency |
| Gather statistics toàn bộ ngay sau upgrade | Có thể gây plan regression hàng loạt | Đánh giá và thu thập có kiểm soát |
| Hạ optimizer feature toàn cục để chữa một SQL | Ảnh hưởng SQL khác | Xử lý theo SQL và bằng chứng |
| Dùng driver mới nhất mà không kiểm tra JDK | Có thể không tương thích runtime | Theo compatibility matrix |
| Test JDBC bằng SQL Developer | Không kiểm tra driver Java thực tế | Test qua datasource/container thật |
| Chỉ test timestamp ở UTC | Bỏ sót DST và region rules | Test nhiều timezone và boundary |
| Coi DBTIMEZONE là SESSIONTIMEZONE | Diễn giải sai dữ liệu | Kiểm tra riêng các lớp timezone |
| Chỉ kiểm tra quyền qua role | Package definer-rights có thể thiếu direct grant | Test bằng runtime account và package |
| Cấp DBA để chữa ORA-01031 | Mở rộng quyền quá mức | Cấp đúng object/system privilege |
| Không drain pool sau deploy | Session cũ giữ state/driver behavior | Drain/recycle connection có kiểm soát |
| Chỉ chạy unit test | Bỏ sót Oracle driver/database semantics | Có integration và end-to-end test |
| Không lưu baseline | Không biết điều gì đã thay đổi | Thu thập trước upgrade |
| Rollback bằng cách đổi app binary | Database/schema có thể không tương thích ngược | Dùng rollback matrix và restore plan |

## 22. Checklist go/no-go

### Database
- Đúng version/RU và PDB/service.
- Registry và SQL patch status đạt yêu cầu.
- Không còn invalid object ngoài danh sách được chấp nhận.
- Alert log không có lỗi chưa xử lý.
- Index/partition/statistics được kiểm tra.
- Backup/restore và rollback plan xác nhận.

### SQL plan
- SQL critical có baseline trước/sau.
- Không có regression vượt ngưỡng.
- Bind value đại diện đã được thử.
- Actual rows/cardinality và I/O được xem.
- SQL Plan Baseline/mitigation được quản lý nếu cần.

### Driver và pool
- JDK/JDBC/pool/ORM nằm trong compatibility matrix.
- Driver runtime version được xác nhận.
- TLS/wallet/authentication thành công.
- Bind/fetch/LOB/batch/procedure test đạt.
- Pool health và stale connection recovery đạt.
- Session state được reset đúng.

### Timezone
- DBTIMEZONE và SESSIONTIMEZONE được ghi nhận.
- Timezone file version được kiểm tra.
- JVM timezone/tzdata được xác nhận.
- DST boundary và region mapping đã test.
- Java/JDBC/ORM mapping đúng semantics.

### Quyền
- Runtime principal và PDB đúng.
- Object/system privileges và roles được đối chiếu.
- Definer-rights package có direct grants cần thiết.
- Synonym, sequence, job, DB link và ACL hoạt động.
- Không có quyền đặc biệt thừa.

### Ứng dụng
- Startup/readiness đạt.
- Repository và transaction tests đạt.
- API business flows đạt.
- Batch/scheduler/message consumer đạt.
- Latency/throughput nằm trong SLA.
- Log, alert và rollback readiness được xác nhận.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao cần baseline trước nâng cấp?

**Trả lời:** Để so sánh plan, latency, quyền, timezone và hành vi ứng dụng, xác định regression mới thay vì đoán nguyên nhân.

**Câu 2.** Plan hash thay đổi có luôn là lỗi không?

**Trả lời:** Không. Cần so sánh operation, actual rows, I/O, latency và workload trước/sau.

**Câu 3.** Vì sao phải test nhiều bind value?

**Trả lời:** Selectivity và data skew có thể làm optimizer chọn plan khác nhau cho cùng SQL.

**Câu 4.** `DBMS_XPLAN.DISPLAY_CURSOR` giúp gì?

**Trả lời:** Hiển thị execution plan của cursor, có thể kèm runtime statistics và predicate khi đã thu thập.

**Câu 5.** Vì sao không gather statistics toàn schema một cách tùy tiện?

**Trả lời:** Statistics mới có thể làm optimizer đổi plan cho nhiều SQL, gây regression ngoài phạm vi test.

**Câu 6.** JDBC driver cần được kiểm tra với những gì?

**Trả lời:** Database release/RU, JDK, JDBC API, pool/UCP, ORM, TLS/wallet và authentication.

**Câu 7.** Vì sao SQL Developer test thành công chưa đủ?

**Trả lời:** SQL Developer dùng driver/runtime/configuration khác ứng dụng Java production.

**Câu 8.** `DBTIMEZONE` và `SESSIONTIMEZONE` có giống nhau không?

**Trả lời:** Không. Chúng đại diện hai lớp timezone khác nhau và có thể có giá trị khác nhau.

**Câu 9.** Vì sao cần test DST?

**Trả lời:** Quy tắc timezone region thay đổi theo lịch; timestamp gần thời điểm chuyển DST có thể bị diễn giải khác nếu timezone data khác.

**Câu 10.** Vì sao `TIMESTAMP WITH LOCAL TIME ZONE` hiển thị khác giữa hai session?

**Trả lời:** Giá trị được chuẩn hóa theo database time zone khi lưu và hiển thị theo session time zone khi đọc.

**Câu 11.** Vì sao package definer-rights có thể lỗi dù user SELECT được bảng?

**Trả lời:** Static SQL trong definer-rights unit cần direct privilege cho owner; quyền chỉ qua role không đủ theo quy tắc Oracle.

**Câu 12.** Làm thế nào xác nhận quyền đúng?

**Trả lời:** Kiểm tra session principal, container, role/system/object grants và chạy test bằng đúng runtime account.

**Câu 13.** Vì sao cần drain/recycle connection pool sau deployment?

**Trả lời:** Để loại session cũ và bảo đảm connection mới dùng driver/configuration đã triển khai, đồng thời tránh session state cũ.

**Câu 14.** Test API 200 có đủ nghiệm thu không?

**Trả lời:** Không. Cần xác nhận dữ liệu, transaction, side effect, latency, quyền và các luồng nghiệp vụ.

**Câu 15.** Khi nào dùng canary?

**Trả lời:** Khi có thể cô lập một phần workload/instance để kiểm tra hành vi thực tế trước khi mở rộng rollout.

**Câu 16.** Vì sao không luôn rollback bằng cách downgrade database?

**Trả lời:** Downgrade chỉ được hỗ trợ cho một số đường nâng cấp và điều kiện cụ thể; phải dựa vào upgrade guide, backup và rollback plan đã kiểm chứng.

## 24. Kết luận

Kiểm chứng sau nâng cấp Oracle phải bao phủ database, SQL optimizer, JDBC driver, timezone, quyền và ứng dụng. Database OPEN và một câu `SELECT 1 FROM dual` chỉ chứng minh kết nối cơ bản. Chúng không chứng minh SQL critical giữ hiệu năng, Java mapping giữ đúng dữ liệu, session timezone đúng, stored procedure còn đủ quyền hoặc các transaction nghiệp vụ hoạt động.

Hãy thu thập baseline trước nâng cấp, kiểm tra release/RU, PDB, registry, invalid objects, statistics và index sau nâng cấp. So sánh execution plan cùng actual rows, buffer gets và latency trên nhiều nhóm bind value. Xác nhận JDBC/JDK/ORM/pool theo compatibility matrix và test trên đúng runtime artifact. Kiểm tra riêng DB/session/JVM timezone, timezone file và các thời điểm DST. Kiểm tra quyền bằng đúng runtime principal trong đúng PDB, đặc biệt direct grants cho definer-rights PL/SQL.

Cuối cùng, chạy regression và end-to-end flow qua datasource/pool thật, bao gồm transaction, batch, scheduler, LOB, procedure và các tích hợp. Đặt tiêu chí go/no-go trước khi rollout, theo dõi canary, lưu evidence và chuẩn bị phương án rollback hoặc forward fix. Chỉ nghiệm thu khi dữ liệu đúng, quyền đúng, thời gian đúng, plan đạt ngưỡng và ứng dụng đáp ứng SLA trên workload đại diện.

