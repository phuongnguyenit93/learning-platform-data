# Đánh giá độ tin cậy, hiệu năng và khả năng di chuyển trước khi phụ thuộc vào PostgreSQL extension

PostgreSQL có một hệ sinh thái extension phong phú. Extension có thể bổ sung kiểu dữ liệu, hàm, operator, index access method, background worker, khả năng tìm kiếm, xử lý địa lý, lập lịch công việc, quan sát hệ thống hoặc tích hợp với dịch vụ khác. Một extension phù hợp có thể giải quyết bài toán nhanh và hiệu quả. Nhưng khi đưa extension vào production, database và ứng dụng bắt đầu phụ thuộc vào mã nguồn, binary, schema objects, quy trình phát hành và chính sách hỗ trợ của extension đó.

Chi phí của một lựa chọn không chỉ là thời gian cài đặt. Extension có thể ảnh hưởng tới độ ổn định của backend, query latency, WAL volume, vacuum, backup/restore, failover, major upgrade, bảo mật và khả năng chuyển database sang một nền tảng khác. Một extension chạy tốt trên máy development chưa chắc có package cho operating system production, được dịch vụ PostgreSQL managed cho phép hoặc có bản build cho major version tiếp theo.

Vì vậy, trước khi phụ thuộc vào extension, cần đánh giá có hệ thống ba nhóm: **độ tin cậy** (maintainer, chất lượng, bảo mật, support và failure modes), **hiệu năng** (overhead, latency, throughput, I/O, WAL và vận hành), và **khả năng di chuyển** (PostgreSQL versions, OS/architecture, packaging, managed services, backup/restore, replication và upgrade path). Sau đó phải chứng minh bằng thử nghiệm có workload đại diện và ghi rõ điều kiện chấp nhận.

Bài học thuộc chương **Mở rộng** của module *Database Engine Relational PostgreSQL*. Nội dung tập trung vào PostgreSQL extensions và các thành phần mở rộng gắn với database. Các nguyên tắc cũng hữu ích khi đánh giá foreign data wrappers, procedural languages, plugins, drivers hoặc dịch vụ phụ trợ mà hệ thống sẽ phụ thuộc.

> **Nguyên tắc:** Đừng chỉ hỏi extension có giải quyết được use case hay không. Hãy xác định ai duy trì nó, điều gì xảy ra khi nó lỗi, nó tiêu tốn tài nguyên nào, và hệ thống có thể nâng cấp hoặc rời bỏ nó bằng cách nào.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích extension là gì và extension khác với tính năng built-in của PostgreSQL như thế nào.
2. Nhận diện các loại extension SQL-only, C/shared library, procedural language và background worker.
3. Kiểm tra extension đang có, version, dependency và trạng thái cài đặt.
4. Đánh giá maintainer, release cadence, issue tracker, security policy và support.
5. Đọc license và xác định ràng buộc phân phối/vận hành.
6. Đánh giá quyền cài đặt, trusted status và rủi ro chạy mã trong database backend.
7. Kiểm tra nguồn package, build provenance, ABI và dependencies.
8. Đánh giá khả năng tương thích với PostgreSQL major/minor versions.
9. Kiểm tra khả năng chạy trên operating systems, CPU architectures và managed services.
10. Xác định tác động tới backup, restore, replication, failover và pg_upgrade.
11. Thiết kế benchmark có baseline và workload đại diện.
12. Đo latency, throughput, CPU, memory, I/O, WAL và tác động lên các replicas.
13. Đánh giá index/operator class, vacuum, bloat và maintenance cost.
14. Thực hiện proof of concept có acceptance criteria và failure scenarios.
15. Lập dependency inventory, risk register và migration/exit plan.
16. Quyết định adopt, pilot, defer hoặc reject extension dựa trên evidence.

## 2. PostgreSQL extension là gì?

Extension là một gói các đối tượng database và/hoặc mã thực thi được cài đặt vào PostgreSQL để bổ sung chức năng. Một extension có thể cung cấp:
- SQL functions và procedures.
- Data types, casts và operators.
- Operator classes/families và index support.
- Views, tables và metadata.
- Triggers.
- Procedural language handlers.
- Background workers.
- Shared libraries được PostgreSQL load khi cần hoặc khi server khởi động.
- Các tiện ích quản trị hoặc tích hợp.

Extension thường được khai báo bằng file control và một hoặc nhiều SQL installation scripts. Với extension có mã native, package còn chứa shared library được PostgreSQL load khi cần hoặc khi server khởi động.

### 2.1. Extension khác với database object tự tạo

Một function tự viết bằng SQL/PLpgSQL có thể được quản lý như object trong schema. Extension gom các objects thuộc một đơn vị phát hành, có version, dependency và upgrade scripts riêng.

PostgreSQL ghi nhận extension đã cài trong catalog pg_extension. Các objects là thành viên extension có quan hệ dependency với extension đó. Điều này giúp quản lý update/drop theo gói, nhưng cũng có nghĩa thao tác extension có thể tác động tới nhiều objects.

### 2.2. Extension không tự động được cài chỉ vì database có metadata

CREATE EXTENSION sử dụng control file và SQL scripts trên máy chủ. Nếu extension có native code, shared library tương ứng cũng phải có trên từng host PostgreSQL cần load nó. Những files này không nằm trong database catalog và không được WAL replication chuyển sang standby như một package OS.

### 2.3. Extension không đồng nghĩa plugin an toàn

Extension có thể chạy code trong process PostgreSQL. Một lỗi memory, crash hoặc deadlock trong native code có thể ảnh hưởng backend hoặc cả server. Đánh giá extension cần nghiêm túc như đánh giá một dependency chạy trong hạ tầng database trọng yếu.

## 3. Các loại extension và hệ quả vận hành

| Loại | Đặc điểm | Điều cần đánh giá |
|---|---|---|
| SQL-only | Chủ yếu là SQL objects/functions | Script, dependency, query cost, upgrade SQL |
| PL/pgSQL hoặc procedural language | Thực thi code qua language handler | Runtime, permissions, trust model, sandbox |
| C/shared library | Native code load vào PostgreSQL | ABI, memory safety, crash risk, build per major |
| Index/operator extension | Thêm access method, opclass hoặc operators | Index correctness, build/reindex, planner, vacuum |
| Background worker | Chạy process/worker cùng server | Lifecycle, restart, CPU/memory, failure handling |
| FDW/integration | Truy cập hệ thống bên ngoài | Network, credentials, consistency, timeout, remote availability |
| Observability/admin | Cung cấp views, stats hoặc helper functions | Privileges, overhead, version-specific catalog |

Một extension có thể thuộc nhiều nhóm. Ví dụ một extension có SQL objects, native library và background worker. Phải đánh giá từng thành phần.

### 3.1. SQL-only không có nghĩa overhead bằng zero

SQL functions có thể thực hiện nhiều joins, scans hoặc tạo locks. Một view có thể che một query rất đắt. Cần đo workload thật.

### 3.2. Native code có rủi ro riêng

C extension có thể truy cập PostgreSQL internals và chạy trong address space của backend. Bug có thể gây segmentation fault, memory corruption hoặc server instability. Native code cần review build provenance, compatibility và security response.

### 3.3. FDW phụ thuộc cả hệ thống ngoài

FDW có thể khiến query PostgreSQL phụ thuộc network, remote credentials, remote schema và behavior của hệ thống khác. Availability của database local không bảo đảm remote source sẵn sàng.

## 4. Xác định use case và nhu cầu thực tế

Trước khi tìm extension, viết rõ vấn đề cần giải quyết.

Mô tả:
- Business capability cần có.
- Workload và data shape.
- Expected query/operation.
- Throughput và latency target.
- Data freshness/consistency requirement.
- Security boundary.
- Availability/RPO/RTO.
- Data retention.
- Growth forecast.
- Operational owner.

### 4.1. Đặt tiêu chí thành công đo được

Ví dụ:
- Query p95 dưới 100 ms ở concurrency 50.
- Ingest đạt 20.000 rows/second trong workload thử nghiệm.
- Không tăng p99 latency của transaction hiện hữu quá 5%.
- Replica lag vẫn trong SLA.
- Restore staging hoàn tất trong RTO đã định.
- Có package cho tất cả PostgreSQL versions được hỗ trợ.

Đây là ví dụ minh họa. Mỗi hệ thống phải chọn ngưỡng dựa trên SLO và baseline thực tế.

### 4.2. Kiểm tra tính năng built-in trước

Trước khi thêm dependency, xem PostgreSQL core đã cung cấp tính năng phù hợp chưa. Tính năng built-in thường có compatibility, security review và upgrade lifecycle gắn với PostgreSQL release.

Không phải lúc nào built-in cũng tốt hơn. Extension có thể cung cấp thuật toán hoặc capability chuyên biệt. Mục tiêu là hiểu rõ lợi ích gia tăng so với chi phí dependency.

### 4.3. So sánh các lựa chọn

Có thể so sánh:
- PostgreSQL built-in feature.
- SQL/PLpgSQL implementation riêng.
- Extension community.
- Extension có vendor support.
- External service hoặc application-layer processing.

Đánh giá tổng chi phí sở hữu (TCO), bao gồm license, infrastructure, on-call, upgrade, migration và exit cost.

## 5. Lập inventory extension hiện có

Trên từng database/cluster, thu thập extension đã cài và version:

```sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
```

Danh sách extension packages có sẵn trên server hiện tại:

```sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
```

Các version và properties có sẵn:

```sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires,
    comment
FROM pg_available_extension_versions
ORDER BY name, version;
```

Schema/cột có thể thay đổi theo PostgreSQL major version; xác nhận catalog của đúng phiên bản. Một số thuộc tính như trusted phụ thuộc version.

### 5.1. Inventory theo cluster và database

Extension được tạo trong một database cụ thể, còn shared library/control files được cài ở cấp host. Một cluster có thể có nhiều databases và mỗi database có danh sách extension khác nhau.

Lập inventory cho:
- Production primary.
- Mọi standby/failover nodes.
- DR cluster.
- Staging và pre-production.
- Reporting/analytics clusters.
- Development/test clusters.
- Các region/cloud environments.

### 5.2. Extension được preload nhưng chưa được CREATE EXTENSION

Một module có thể xuất hiện trong shared_preload_libraries nhưng chưa có extension entry trong một database. Ngược lại, một extension có thể được cài nhưng library chỉ load khi function được gọi. Kiểm tra cả catalog và effective configuration.

```sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
SHOW local_preload_libraries;
```

### 5.3. Kiểm tra package files

Trên host, xác định:
- Control files.
- SQL installation/update scripts.
- Shared library files.
- Runtime libraries.
- Package version/build.
- Package owner/repository.
- File permissions và checksums.

Dùng package manager và pg_config phù hợp với instance đang chạy. Không copy một shared library build cho major version khác vào thư mục library để thử load.

## 6. Đánh giá độ tin cậy của maintainer và dự án

Một extension có tính năng tốt nhưng không có người chịu trách nhiệm bảo trì sẽ trở thành rủi ro lâu dài.

### 6.1. Ownership và governance

Tìm hiểu:
- Ai là maintainer chính?
- Có nhiều maintainer độc lập hay chỉ một cá nhân?
- Có tổ chức/vendor đứng sau không?
- Quy trình review/merge thay đổi ra sao?
- Có governance và release authority rõ không?
- Nếu maintainer rời dự án, ai tiếp quản?
- Có kênh hỗ trợ production không?

Bus factor thấp làm tăng rủi ro dependency. Một dự án có một maintainer giỏi vẫn có thể phù hợp cho use case nhỏ, nhưng cần exit plan rõ.

### 6.2. Release cadence

Xem:
- Lần phát hành gần nhất.
- Khoảng cách giữa các releases.
- Có release tương ứng mỗi PostgreSQL major không?
- Security fixes được phát hành thế nào?
- Có release branch cho phiên bản cũ?
- Các bản phát hành có changelog và upgrade instructions không?

Release thường xuyên không tự động chứng minh chất lượng. Release chậm cũng không luôn là dấu hiệu bỏ dự án. Cần đối chiếu cadence với mức độ thay đổi và support commitments.

### 6.3. Issue và pull request health

Quan sát:
- Số issue tồn đọng và tuổi issue.
- Bug nghiêm trọng có được xác nhận không?
- Security issues có được xử lý riêng tư không?
- Pull requests có review không?
- Release notes có phản ánh các fix quan trọng không?
- Có maintainer trả lời user reports không?
- Có regression tests cho bug đã sửa không?

Không dùng số stars/downloads làm thước đo duy nhất. Chúng phản ánh mức độ chú ý, không chứng minh correctness hoặc production readiness.

### 6.4. Quality signals

Các tín hiệu tốt gồm:
- Automated tests và CI matrix.
- Test trên nhiều PostgreSQL major versions.
- Static analysis và compiler warnings được xử lý.
- Fuzz/property tests khi phù hợp.
- Documented upgrade paths.
- Reproducible builds.
- Security policy và disclosure contact.
- Release artifacts có checksum/signature.
- Changelog nêu rõ breaking changes.

### 6.5. Support model

Xác định support đến từ:
- Community best-effort.
- Maintainer sponsorship.
- Commercial vendor.
- Internal fork/team.
- Managed database provider.

Nếu extension là critical dependency, cần biết thời gian phản hồi, thời gian fix, support window và escalation path. Có GitHub issue không tương đương SLA.

## 7. Đánh giá license và quyền sử dụng

License ảnh hưởng việc sử dụng, sửa đổi, phân phối binary, đóng gói container và cung cấp dịch vụ.

Kiểm tra:
- License file trong repository.
- License của transitive dependencies.
- NOTICE/copyright obligations.
- Điều kiện phân phối modified builds.
- Điều kiện dùng trong SaaS/hosted service nếu có.
- Patent clauses hoặc trademark terms.
- Vendor commercial terms.
- Quy định nội bộ về open-source approval.

Không suy ra license chỉ từ tên dự án hoặc badge trên README. Đọc license thực tế và nhờ bộ phận pháp lý/compliance review khi có nghĩa vụ phân phối hoặc điều kiện sử dụng đặc biệt.

### 7.1. Source available không đồng nghĩa open source

Một repository công khai có thể dùng source-available hoặc custom license. Kiểm tra quyền sử dụng production và quyền tạo fork.

### 7.2. Fork có thể tạo nghĩa vụ riêng

Nếu sửa extension và duy trì fork, tổ chức phải sở hữu patch management, security fixes, merge upstream, build matrix, release artifacts, support/on-call và compatibility testing.

Đừng tính chi phí fork như một lần sửa code duy nhất.

## 8. Đánh giá security và trust boundary

Extension có thể có quyền rất lớn trong database server.

### 8.1. Quyền cài đặt

Các thuộc tính extension có thể gồm:
- superuser: việc cài đặt có yêu cầu superuser không.
- trusted: extension có cho phép non-superuser cài đặt khi role có quyền CREATE phù hợp không.
- relocatable: objects có thể được cài vào schema khác theo cơ chế extension hay không.
- requires: các extension dependencies.

Kiểm tra metadata bằng pg_available_extension_versions và tài liệu extension.

### 8.2. Trusted không phải security certification

trusted = true là thuộc tính cài đặt do extension author khai báo và có ý nghĩa đối với quyền cài đặt. Nó không chứng minh code đã được audit, không có CVE hoặc an toàn cho mọi threat model.

### 8.3. Native code và backend process

C extension chạy trong process PostgreSQL. Nếu code có lỗi memory hoặc xử lý pointer sai, có thể làm crash backend. Một lỗi nghiêm trọng trong library có thể ảnh hưởng nhiều connections hoặc toàn instance.

Đánh giá:
- Source code review.
- Dependency scanning.
- Compiler/build flags.
- Memory-safety testing.
- Privilege boundaries.
- Input validation.
- Error handling.
- Crash/restart behavior.

### 8.4. SECURITY DEFINER và privileges

Kiểm tra functions có SECURITY DEFINER, owner, search_path và quyền execute. Function chạy với quyền owner có thể tạo privilege escalation nếu dùng object resolution không an toàn.

### 8.5. Dynamic loading và preload

shared_preload_libraries load library khi server start. Một lỗi library hoặc dependency thiếu có thể ngăn PostgreSQL khởi động. Cần test restart và có cách gỡ library khỏi config khi boot failure.

### 8.6. Secrets và external connections

FDW/extension tích hợp remote systems có thể lưu credentials hoặc mở network connections. Kiểm tra:
- Credential storage.
- Rotation.
- TLS verification.
- Network egress.
- Timeout.
- Audit.
- Secret exposure qua logs/catalog.
- Least privilege trên remote system.

### 8.7. Security response

Xác định cách theo dõi CVEs/advisories, ai đánh giá mức độ ảnh hưởng, thời gian triển khai patch và cách rebuild packages. Extension native cần patch/restart process để nạp binary mới.

## 9. Đánh giá chất lượng và correctness

Độ tin cậy không chỉ là server không crash. Extension phải trả kết quả đúng, duy trì invariant và xử lý edge cases.

### 9.1. Correctness contract

Xác định:
- Function semantics.
- NULL behavior.
- Type coercion.
- Collation/locale assumptions.
- Transaction semantics.
- Concurrency behavior.
- Determinism.
- Error/exception behavior.
- Index consistency.
- Data format/version.

### 9.2. Test edge cases

Tùy use case, kiểm tra empty input, NULL, Unicode, very large values, boundary numeric values, duplicate data, concurrent updates, long transactions, crash/restart, disk full, network timeout và corrupt/malformed input.

### 9.3. Data integrity và index correctness

Nếu extension cung cấp index access method hoặc custom operator class, cần xác minh:
- Index results khớp sequential scan.
- Insert/update/delete giữ index consistent.
- Vacuum/reindex hoạt động.
- Crash recovery không làm index corrupt.
- Operator semantics phù hợp với index ordering.
- Backup/restore giữ được index objects.

### 9.4. Deterministic output

Nếu extension phục vụ ranking, similarity hoặc analytics, xác định output có deterministic không. Thay đổi version/algorithm có thể thay kết quả; ứng dụng có cần stable pagination hoặc reproducible output không?

### 9.5. Failure modes

Mô tả điều gì xảy ra khi extension function timeout, background worker crash, remote service mất kết nối, extension library không load, upgrade script fail giữa chừng, index build bị hủy hoặc database restart trong lúc extension đang xử lý.

Không chấp nhận một dependency critical nếu không biết cách phát hiện và phục hồi khi nó lỗi.

## 10. Đánh giá hiệu năng: xác định chi phí nào cần đo

Hiệu năng extension cần được đánh giá trong bối cảnh workload toàn hệ thống.

Các nhóm metric:
- Query latency: p50, p95, p99, max.
- Throughput: requests/transactions/rows per second.
- CPU time và CPU utilization.
- Memory usage và allocation.
- Shared buffers/cache hit behavior.
- Disk I/O và IOPS.
- Temporary files/spill.
- WAL bytes và replication lag.
- Lock waits và contention.
- Index size, table bloat và vacuum work.
- Background worker activity.
- Network traffic nếu extension gọi hệ thống ngoài.

### 10.1. Đo baseline trước khi cài

Chụp metrics trên cùng dataset/workload khi chưa có extension hoặc khi tính năng chưa bật. Không chỉ so sánh hai lần chạy trên hai cluster khác hardware.

### 10.2. Tách install cost và runtime cost

Extension có thể tốn thời gian cài/update, tăng startup time, thêm background workers, tăng overhead trên mọi transaction, chỉ tốn tài nguyên khi gọi một function/index hoặc tạo maintenance workload định kỳ.

Đo từng phần phù hợp.

### 10.3. Đo cả workload hiện hữu

Một extension phục vụ một query mới có thể làm chậm mọi query khác do CPU, memory, locks hoặc I/O. Đánh giá impact tới critical workload hiện tại.

## 11. Thiết kế benchmark có kiểm soát

Benchmark tốt cần tái hiện workload đủ đại diện và có thể lặp lại.

### 11.1. Xác định test cases

Bao gồm typical read, typical write, peak concurrency, bulk ingest, update/delete, large scans, worst-case input, mixed workload, background maintenance và recovery/restart khi cần.

### 11.2. Giữ điều kiện so sánh nhất quán

Cố định hoặc ghi lại:
- PostgreSQL version.
- Extension version.
- Hardware/VM/container limits.
- Storage type.
- Dataset size/distribution.
- shared_buffers, work_mem, parallel settings.
- Connection count/pooler.
- Cache state.
- Statistics state.
- Query parameters.
- Network location.

### 11.3. Chạy nhiều lần

Thực hiện warm-up, nhiều lần đo và ghi phân phối thay vì chỉ average. Tránh kết luận từ một lần chạy có cache nóng hoặc background activity khác thường.

### 11.4. Không dùng dữ liệu quá nhỏ

Dataset nhỏ hơn RAM có thể che giấu disk I/O và cache pressure. Dùng data volume, skew và cardinality gần production.

### 11.5. Tách microbenchmark và end-to-end test

Microbenchmark giúp hiểu function/operator riêng. End-to-end test cho biết extension có cải thiện business path khi cộng với network, application, pooler và database load.

## 12. Đo query performance bằng PostgreSQL

### 12.1. EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...
FROM ...
WHERE ...;
```

EXPLAIN ANALYZE thực thi query. Chỉ dùng trên statement an toàn và workload thử nghiệm hoặc theo quy trình production đã phê duyệt.

So sánh actual time, rows estimated/actual, loops, shared/local/temp buffers, I/O timing nếu có, sort/hash spills, parallel workers và function/operator execution path.

### 12.2. pg_stat_statements

Nếu được cài và cấu hình, pg_stat_statements giúp theo dõi query workload theo normalized query identity.

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Schema/cột thay đổi theo version của extension. Query trên là ví dụ cho các versions cung cấp các fields này; kiểm tra view definition thực tế.

### 12.3. So sánh trước/sau

Thu thập snapshot trước và sau khi bật extension. Dùng delta counters và workload-normalized rates. Tránh so sánh counter tích lũy từ hai khoảng thời gian khác nhau.

### 12.4. p95/p99 ở tầng ứng dụng

PostgreSQL statistics views thường không cung cấp toàn bộ latency percentile cho từng business request. Kết hợp tracing/metrics của application để đánh giá tail latency và end-to-end impact.

### 12.5. Explain plan có thể khác theo statistics

Chạy ANALYZE phù hợp, ghi lại data distribution và planner settings. Nếu extension thêm operator/index, xác nhận planner thật sự dùng nó trong workload mục tiêu.

## 13. Đánh giá index và write amplification

Extension tạo index hoặc access method có thể tăng tốc reads nhưng làm writes đắt hơn.

Đo:
- Index size.
- Build time.
- Insert/update/delete throughput.
- WAL bytes per row/transaction.
- Vacuum duration.
- Reindex duration.
- Cache footprint.
- Index bloat.
- Replication lag.
- Query plan stability.

### 13.1. Read improvement có thể đổi lấy write cost

Nếu extension index làm read nhanh gấp nhiều lần nhưng mỗi write tạo thêm index maintenance, phải so sánh theo workload mix. Một hệ thống write-heavy có thể không phù hợp.

### 13.2. Index build và rebuild

Xác định extension index có hỗ trợ concurrent build hay không, có thể resume sau lỗi không, có cần lock mạnh không và quy trình REINDEX khi upgrade ra sao.

### 13.3. Operator class semantics

Custom operator class phải khớp semantics của operators và ordering. Nếu extension thay đổi thuật toán hoặc binary representation, index cũ có thể cần rebuild theo release notes.

### 13.4. Vacuum và maintenance

Kiểm tra extension có yêu cầu vacuum/analyze riêng, retention cleanup, compaction hoặc background maintenance không. Tính cả thời gian maintenance vào operational capacity.

## 14. CPU, memory và background workers

Một extension có thể tạo resource overhead không xuất hiện trong một query benchmark đơn giản.

Kiểm tra:
- Background worker count.
- Worker restart policy.
- Memory contexts.
- Shared memory requirements.
- shared_preload_libraries.
- Parallel worker interactions.
- CPU saturation.
- Scheduler behavior.
- Long-lived memory allocations.
- Worker shutdown/restart behavior.

### 14.1. Shared memory requirements

Một số extension yêu cầu tham số shared memory hoặc worker count được tăng. Kiểm tra setting context (postmaster/reload/user), restart requirement và total memory budget.

### 14.2. Worker capacity

PostgreSQL có giới hạn worker/process liên quan. Extension có thể cạnh tranh với parallel query, logical replication, autovacuum hoặc workers của extensions khác. Không chỉ xem riêng số workers extension cần.

### 14.3. Startup and recovery

Extension preload có thể kéo dài startup hoặc recovery/failover. Test restart sau khi bật extension và đo thời gian phục hồi.

## 15. WAL, replication và durability overhead

Extension có thể ghi thêm tables/indexes, thay đổi write patterns hoặc thực hiện background updates.

Đo WAL bytes per business operation, checkpoint frequency/pressure, replica receive/replay lag, archive volume, slot retention, logical decoding behavior và crash recovery time.

### 15.1. Physical standby

Physical replication chuyển database changes qua WAL, nhưng shared libraries và OS packages không được replicate. Cài đúng extension binary trên mọi standby trước khi failover/promote nếu node cần load extension.

### 15.2. Logical replication

Logical replication không tự động phân phối extension package, shared library hoặc mọi DDL. Tạo extension tương ứng trên subscriber, đồng bộ schema theo quy trình riêng và kiểm tra extension-specific data/objects.

### 15.3. Synchronous replication

Nếu extension tăng WAL hoặc làm transaction lâu hơn, có thể tác động commit latency trong synchronous replication. Đo write path với topology gần production.

### 15.4. Replication slots và WAL retention

Extension có background workers/consumers hoặc logical decoding integration có thể tạo/giữ replication slots. Theo dõi slot ownership, inactive slots, restart LSN và retained WAL.

## 16. Đánh giá khả năng tương thích PostgreSQL versions

Một extension cần có compatibility matrix rõ ràng.

Kiểm tra:
- PostgreSQL major versions được hỗ trợ.
- Minor version constraints nếu có.
- Extension release hỗ trợ target major.
- PostgreSQL internal API usage.
- Upgrade scripts từ version đang cài.
- Downgrade policy.
- Known incompatibilities.
- Support window.

### 16.1. Native extension và ABI

C extension thường cần build cho PostgreSQL major version tương ứng vì PostgreSQL server internals/extension ABI không được bảo đảm tương thích giữa các major versions. Không giả định một shared library build cho PG16 sẽ load an toàn trên PG17.

### 16.2. Minor updates

Binary compatibility trong cùng major thường được kỳ vọng, nhưng phải tuân theo package/vendor support matrix và security advisories. Nếu extension dùng internal APIs hoặc custom build, kiểm tra kỹ hơn.

### 16.3. SQL-only extension

SQL-only extension có thể ít phụ thuộc ABI hơn nhưng vẫn có thể phụ thuộc catalog, function signatures, syntax, planner behavior và extension update scripts. Không kết luận portable chỉ vì không có shared library.

### 16.4. Compatibility matrix

| Thành phần | Source | Target | Evidence |
|---|---|---|---|
| PostgreSQL major | Version đang chạy | Version dự kiến | Extension support matrix |
| Extension release | Installed version | Supported release | Changelog/update path |
| Native library | Binary source build | Target build | Package/build artifact |
| Dependencies | OS libraries | Target libraries | Package metadata/SBOM |
| Upgrade path | Current extension version | Target extension version | SQL update scripts |
| Managed service | Current platform | Target platform/version | Provider allowlist |

## 17. Operating system, architecture và packaging

Portability còn phụ thuộc môi trường chạy.

Kiểm tra Linux distribution/version, Windows/macOS nếu cần, CPU architecture (x86_64, ARM64...), libc/toolchain, compiler version, OpenSSL/ICU và các libraries liên quan, kernel/system calls, package manager, container base image, file path và permissions, runtime service account.

### 17.1. Package source

Ưu tiên package từ nguồn tin cậy, có provenance và được cập nhật. Ghi repository/vendor, package name/version, build target, checksum/signature, dependencies, patch set và support lifecycle.

### 17.2. Build from source

Nếu phải tự build:
- Pin source commit/tag.
- Pin compiler/toolchain.
- Dùng pg_config đúng PostgreSQL installation.
- Ghi build flags.
- Lưu build logs.
- Quét dependencies.
- Tạo reproducible artifact.
- Test install/upgrade/restart.
- Lưu SBOM và checksums theo policy.

Ví dụ build extension PGXS:

```bash
make USE_PGXS=1 PG_CONFIG=/usr/pgsql-17/bin/pg_config
make USE_PGXS=1 PG_CONFIG=/usr/pgsql-17/bin/pg_config install
```

Đây là ví dụ đường dẫn. Dùng pg_config thuộc đúng target installation và build theo hướng dẫn của extension. Không build/install trực tiếp vào production như một thử nghiệm.

### 17.3. Container image

Đóng gói extension cùng PostgreSQL image giúp pin versions, nhưng cần:
- Base image được duy trì.
- Extension packages đúng major.
- Security patches.
- Image digest.
- Multi-architecture builds.
- Startup/health checks.
- Reproducible deployment.
- Rollback image.

### 17.4. Mọi failover node phải có dependency

Nếu extension được preload hoặc dùng bởi application sau promotion, standby/DR node phải có binary và dependencies tương ứng. Kiểm tra package parity bằng automation, không dựa vào ghi nhớ thủ công.

## 18. Managed PostgreSQL và cloud portability

Không phải dịch vụ PostgreSQL managed nào cũng cho phép cài mọi extension.

Provider có thể allowlist extension, giới hạn extension versions, yêu cầu parameter group/flag, chặn shared_preload_libraries, không cho superuser thực sự, giới hạn background workers hoặc shared memory, chỉ cung cấp extension ở một số region/instance classes, cập nhật extension theo lịch provider hoặc có quy tắc riêng cho major upgrade.

### 18.1. Kiểm tra allowlist trước khi thiết kế

Xác nhận extension có sẵn ở:
- Engine major/minor target.
- Region.
- Instance class/tier.
- Deployment mode (single/HA/serverless).
- Read replicas.
- DR region.

Một extension hiện có trong một region không bảo đảm có trong region khác.

### 18.2. Privilege limitations

Managed service có thể không cấp superuser OS hoặc database thực sự. Một extension yêu cầu thao tác filesystem, preload hoặc OS package tùy chỉnh có thể không cài được.

### 18.3. Provider-managed versions

Provider có thể quyết định version extension được cung cấp. Xác nhận upgrade schedule, deprecation window và cách kiểm tra version thực tế.

### 18.4. Multi-cloud strategy

Nếu portability giữa cloud providers là yêu cầu, chỉ chọn extension có sẵn và được hỗ trợ ở mọi target, hoặc thiết kế abstraction/fallback. Nếu không, ghi rõ extension là provider-specific dependency và đánh giá exit cost.

## 19. Backup, restore và disaster recovery

Extension có thể lưu state ở nhiều nơi:
- PostgreSQL tables/indexes/catalog.
- Shared libraries trên host.
- Configuration files.
- External services.
- Filesystem paths.
- Remote object stores.
- Credentials/secrets.
- Background worker checkpoints.

Một database backup không nhất thiết chứa toàn bộ những thứ này.

### 19.1. pg_dump/pg_restore

Logical dump thường lưu lệnh CREATE EXTENSION và các objects phụ thuộc phù hợp với cơ chế extension, nhưng không đóng gói shared library/control files của extension. Host restore phải cài package tương thích trước khi restore extension.

Extension có configuration tables hoặc data ngoài catalog cần xem cách backup riêng. Không giả định pg_dump đã lưu toàn bộ external state.

### 19.2. Physical backup

Physical backup chứa data files và WAL theo phương thức backup, nhưng không thay thế việc quản lý OS packages/shared libraries/configuration cần thiết để server start và extension load.

### 19.3. Restore drill

Thực hiện restore vào host mới:
1. Cài PostgreSQL target.
2. Cài extension packages/versions cần thiết.
3. Khôi phục database.
4. Kiểm tra CREATE EXTENSION và library loading.
5. Chạy extension-specific validation.
6. Kiểm tra indexes/types/functions.
7. Kiểm tra external credentials/services.
8. Chạy application smoke tests.

### 19.4. RPO/RTO

Đo thời gian phục hồi extension state, index rebuild, background worker catch-up và remote dependency recovery. Nếu extension làm tăng restore time, cập nhật RTO plan.

### 19.5. External state

FDW, search service, object storage hoặc external scheduler có thể giữ state ngoài database. Backup database không bảo đảm snapshot nhất quán với external system. Thiết kế snapshot/reconciliation riêng.

## 20. Upgrade và migration path của extension

PostgreSQL major upgrade và extension upgrade là hai hoạt động liên quan nhưng khác nhau.

### 20.1. Kiểm tra extension update paths

Có thể xem các update paths được cài trên server:

```sql
SELECT *
FROM pg_extension_update_paths('extension_name');
```

Function và kết quả phụ thuộc version/package. Một path có trong source host không bảo đảm target package đã cài scripts tương ứng.

### 20.2. Xem extension metadata

```sql
SELECT
    e.extname,
    e.extversion,
    e.extrelocatable,
    e.extnamespace::regnamespace AS extension_schema
FROM pg_extension AS e
ORDER BY e.extname;
```

### 20.3. ALTER EXTENSION UPDATE

Khi đã xác nhận update path và target package, extension có thể được cập nhật bằng:

```sql
ALTER EXTENSION extension_name UPDATE TO '2.0';
```

Thay extension_name và version bằng giá trị thực tế. Đọc release notes của extension để biết thứ tự, preconditions, lock và data migration.

### 20.4. pg_upgrade không thay extension package

pg_upgrade chuyển database cluster theo quy trình PostgreSQL. Native extension binaries/control files/SQL scripts phải được cài phù hợp trên target hosts. Extension SQL update có thể là bước riêng sau cluster upgrade theo hướng dẫn tương ứng.

### 20.5. Không giả định downgrade được hỗ trợ

Extension có thể có upgrade path một chiều. Nếu target extension version thay đổi data format hoặc catalog objects, rollback có thể cần restore backup. Kiểm tra downgrade policy trước khi chạy.

### 20.6. Upgrade rehearsal

Test từ đúng installed extension version lên target trên bản restore/clone. Kiểm tra pre-upgrade checks, package installation, pg_upgrade hoặc dump/restore, ALTER EXTENSION UPDATE, reindex nếu cần, application behavior, restart/failover, backup/restore và rollback/recovery.

## 21. Dependency graph và blast radius

Extension hiếm khi đứng một mình. Nó có thể phụ thuộc:
- Một extension khác.
- Shared libraries.
- Procedural language.
- PostgreSQL internal APIs.
- OS packages.
- Remote services.
- Credentials.
- Background workers.
- Custom operators/types/indexes.
- Monitoring tools.

### 21.1. Ghi dependency graph

Với mỗi dependency, ghi version range, owner, source, update cadence và failure mode. Đánh dấu dependency critical và single point of failure.

### 21.2. Extension dependency trong catalog

pg_available_extension_versions.requires cho biết các extension requirements được khai báo trong metadata cài đặt. Catalog dependencies không thể hiện mọi OS library, network service hoặc operational dependency.

### 21.3. Blast radius

Đánh giá phạm vi khi extension crash backend, làm startup fail, tạo CPU saturation, giữ locks, gây WAL burst, làm index results sai, không tương thích target hoặc không thể cài trên DR node.

### 21.4. Isolation

Nếu extension không đáng tin hoặc có failure blast radius quá lớn, cân nhắc xử lý ở application/external service thay vì load native code vào database. Đổi lại, external service có latency/network/consistency cost cần đánh giá.

## 22. Thiết kế proof of concept (PoC)

PoC cần trả lời các giả thuyết đã đặt ra, không chỉ chứng minh CREATE EXTENSION chạy được.

### 22.1. Scope

Ghi use case, extension/version, PostgreSQL version, environment, dataset, workload, baseline, metrics, acceptance thresholds, failure scenarios và test owner.

### 22.2. PoC environment

Dùng môi trường tách biệt, dữ liệu đại diện đã xử lý theo policy, cấu hình gần production và cùng loại package/OS. Không thử extension native chưa review trực tiếp trên production.

### 22.3. Test cases

- Install/uninstall.
- Restart.
- Upgrade extension.
- Application integration.
- Concurrent workload.
- Peak load.
- Backup/restore.
- Physical failover.
- Logical replication nếu dùng.
- Managed-service restrictions.
- Failure injection.
- Resource exhaustion.
- Security/privilege tests.

### 22.4. PoC exit criteria

Mỗi test có pass/fail rõ ràng. Không để “trông có vẻ nhanh” hoặc “không thấy lỗi” làm tiêu chí chấp nhận.

### 22.5. Không dùng production data một cách tùy tiện

Mask/anonymize theo policy. Nếu data distribution quan trọng, giữ đặc điểm thống kê mà không để lộ thông tin nhạy cảm.

## 23. Benchmark matrix

Một ma trận benchmark hữu ích:

| Scenario | Workload | Metrics | Mục tiêu |
|---|---|---|---|
| Baseline | Không bật extension | Latency, throughput, CPU, I/O | Mốc so sánh |
| Typical | Request thường ngày | p50/p95/p99, error rate | Hiệu năng thực tế |
| Peak | Concurrency cao | Queueing, CPU, locks | Capacity |
| Write-heavy | Insert/update | WAL, IOPS, replication lag | Write amplification |
| Read-heavy | Search/scan | Buffers, CPU, p95 | Query benefit |
| Mixed | Read/write đồng thời | Throughput, tail latency | Production realism |
| Restart | Restart/failover | Recovery time, worker state | Reliability |
| Restore | Restore từ backup | RTO, missing dependencies | Portability/recovery |
| Upgrade | Version transition | Duration, errors, reindex | Lifecycle |
| Failure | Remote/service/library failure | Detection, blast radius, recovery | Resilience |

### 23.1. Đo ở nhiều mức concurrency

Một extension có thể tốt ở concurrency 1 nhưng giảm throughput ở concurrency cao do lock contention hoặc shared resource contention.

### 23.2. Theo dõi cả hệ thống

Thu thập PostgreSQL metrics, OS/container metrics, application tracing và external service metrics cùng một timeline.

### 23.3. Ghi cấu hình benchmark

Lưu exact SQL, parameters, dataset generator, random seed nếu có, PostgreSQL settings, extension version và hardware. Kết quả không thể tái lập khó dùng làm decision evidence.

## 24. Reliability testing và failure injection

Thử nghiệm lỗi có kiểm soát để biết hệ thống phục hồi thế nào.

### 24.1. Restart và crash

Kiểm tra extension có load lại sau restart, background worker có resume, persistent state có consistency và startup có phụ thuộc external service không.

Không cố tình kill production backend/server để thử.

### 24.2. Remote dependency failure

Với FDW/integration, mô phỏng DNS failure, connection refused, timeout, TLS certificate invalid, credential expired, remote service overload và partial response.

Xác nhận timeout, retry, circuit breaker và transaction behavior.

### 24.3. Disk/memory pressure

Đánh giá behavior khi temp storage, memory hoặc filesystem gần giới hạn. Extension có thể tạo spill files hoặc cache riêng.

### 24.4. Worker crash

Kiểm tra restart loop, log noise, duplicate processing, checkpoint recovery và khả năng operator disable worker.

### 24.5. Corrupt input

Test malformed data và oversized payload. Extension phải báo lỗi có thể xử lý thay vì crash hoặc làm hỏng state.

### 24.6. Failure recovery criteria

Ghi detection time, alert, user impact, recovery steps, data loss/duplication, manual intervention và time to restore normal service.

## 25. Observability và vận hành

Trước khi adopt, xác nhận đội vận hành có thể nhìn thấy trạng thái extension.

Cần biết extension version hiện tại, worker status, queue/backlog, error/retry counts, resource consumption, index/maintenance state, external dependency health và upgrade status.

### 25.1. Logging

Log cần có extension name/version, operation, error category và correlation identifier khi phù hợp. Tránh log raw secrets hoặc payload nhạy cảm.

### 25.2. Metrics

Ưu tiên metrics có ý nghĩa với SLO:
- Operation count/rate.
- Success/error rate.
- Queue depth.
- Processing lag.
- Latency distribution.
- Cache hit/miss.
- Worker restarts.
- External request latency.
- Resource usage.

### 25.3. Health checks

Health check phải phản ánh khả năng xử lý thật. Một extension library load thành công chưa chứng minh remote service hoặc background worker đang khỏe.

### 25.4. Runbooks

Viết runbook cho install/update, restart/reload, worker stuck, queue backlog, index invalid/corrupt, remote credentials expired, upgrade failure, disable/rollback và failover/restore.

### 25.5. On-call readiness

Chỉ định owner và người trực có thể chẩn đoán extension. Nếu chỉ một developer biết cách sửa, đây là operational risk cần được ghi nhận.

## 26. Managed service và self-managed deployment: so sánh

| Tiêu chí | Self-managed | Managed PostgreSQL |
|---|---|---|
| Cài OS package | Có quyền kiểm soát | Phụ thuộc provider |
| shared library | Có thể tự build/cài | Thường allowlist |
| Superuser | Quyền theo quản trị host | Thường hạn chế |
| Preload settings | Tự cấu hình | Theo parameter group/allowlist |
| Version cadence | Tự quyết định | Theo provider |
| OS portability | Do đội vận hành quản lý | Bị trừu tượng hóa |
| Failover nodes | Tự đồng bộ packages | Provider quản lý node, nhưng vẫn cần kiểm tra support |
| Extension updates | Tự quản lý | Có thể do provider quản lý/giới hạn |

### 26.1. Managed service không xóa bỏ extension risk

Provider có thể quản lý binary, nhưng tổ chức vẫn chịu trách nhiệm query behavior, data correctness, schema dependencies, backup policy và exit cost.

### 26.2. Portability giữa self-managed và managed

Nếu có kế hoạch chuyển deployment model, test extension trên cả hai môi trường từ đầu. Không đợi đến lúc migration mới phát hiện target không hỗ trợ extension.

## 27. Exit strategy: có thể rời bỏ extension không?

Một dependency tốt cần có đường thoát có thể thực hiện.

### 27.1. Data export

Xác định cách export tables/data, custom types, index definitions, extension-owned metadata, external state, configuration và credentials.

### 27.2. Replacement path

Nếu thay extension bằng built-in feature hoặc service khác:
- Mapping data types.
- Mapping operators/functions.
- Rebuild indexes.
- Recompute derived data.
- Change application queries.
- Validate output equivalence.
- Plan dual-run/cutover.

### 27.3. Extension-specific storage format

Một số extension lưu data theo binary format hoặc index structure riêng. Cần biết format có thể dump/restore hoặc phải rebuild. Không giả định database dump là portable giữa mọi extension versions.

### 27.4. Exit cost

Ước lượng engineering effort, migration duration, downtime, data conversion, reindex/recompute, performance impact, temporary infrastructure, rollback và contract/vendor cost.

### 27.5. Tránh coupling không cần thiết

Đặt extension-specific SQL sau repository/service boundary khi hợp lý. Tránh để extension-specific types/operators lan vào API public, event schema và mọi application module nếu không cần.

## 28. Ví dụ: đánh giá một extension tìm kiếm vector

Giả sử ứng dụng muốn thêm vector similarity search trong PostgreSQL.

### 28.1. Reliability questions

- Extension hỗ trợ các PostgreSQL major nào?
- Ai duy trì và phát hành binary?
- Index có behavior gì khi insert/update/delete đồng thời?
- Crash/restart có giữ index consistency không?
- Có tài liệu reindex/upgrade không?
- Có package cho mọi architecture và DR region không?
- Managed provider có cho phép không?

### 28.2. Performance questions

- Query p95 ở dataset thực tế là bao nhiêu?
- Index build mất bao lâu?
- Recall/accuracy thay đổi theo index parameters thế nào?
- Insert throughput giảm bao nhiêu?
- Index size và memory footprint?
- WAL volume/replica lag?
- Query planner có dùng index trong các filter combinations không?

### 28.3. Portability questions

- Có thể chuyển từ self-managed sang managed không?
- Index có cần rebuild khi đổi extension version không?
- Có thể export vectors và tạo lại index không?
- Logical migration có chuyển đủ dữ liệu và schema không?
- Target architecture có binary tương ứng không?

### 28.4. Acceptance criteria

Ví dụ:
- Recall đạt ngưỡng được product chấp nhận.
- p95 latency đạt SLO ở concurrency mục tiêu.
- Write throughput giảm không quá budget.
- Backup restore và failover test thành công.
- Extension có support path cho hai major versions kế tiếp.
- Có phương án rebuild index từ source data.

Các ngưỡng phải được xác định theo sản phẩm; đây không phải mặc định chung cho vector extensions.

## 29. Ví dụ: đánh giá FDW kết nối hệ thống ngoài

Một foreign data wrapper có thể cho phép query remote data như foreign tables.

Đánh giá remote server availability và latency, remote schema, authentication, network egress/ingress, timeout, retry, transaction semantics, snapshot consistency, query fan-out, connection pooling, data residency và backup/recovery của remote source.

### 29.1. Pushdown

Kiểm tra filters/joins/aggregates có được push xuống remote source hay thực hiện local. Một query nhìn ngắn có thể kéo toàn bộ remote table về PostgreSQL.

### 29.2. Transaction consistency

Không giả định transaction local và remote có atomicity giống một database đơn. Kiểm tra FDW support và remote transaction semantics.

### 29.3. Remote outage

Xác định query local có fail, timeout hay dùng cache/stale data. Đặt timeout hợp lý để remote outage không giữ connection/backend quá lâu.

## 30. Ví dụ: đánh giá extension quan sát hệ thống

Extension monitoring có thể cung cấp views/functions nhưng cần xem overhead và quyền truy cập.

Đánh giá sampling frequency, shared memory requirements, data retention, query cost, cardinality và label explosion, permissions, exposure of query text/PII, exporter compatibility, restart requirements và stats reset semantics.

Một extension theo dõi query có thể làm tăng shared memory hoặc lưu query text. Cần cấu hình retention, masking và role permissions theo policy.

## 31. Quy trình đánh giá và quyết định adopt

Một quy trình thực tế:

1. **Define use case:** mô tả nhu cầu, SLO, data shape và alternative.
2. **Identify candidate:** ghi tên, source, license, current release và owner.
3. **Inspect project health:** maintainer, release cadence, issues, tests và support.
4. **Review security:** code type, privilege, trust, CVEs, build provenance và external access.
5. **Check compatibility:** PostgreSQL versions, OS, architecture, packages, managed services.
6. **Review lifecycle:** install, upgrade, backup, restore, failover và rollback.
7. **Run PoC:** workload đại diện, failure tests và benchmark.
8. **Calculate TCO:** engineering, infrastructure, support, operations và exit costs.
9. **Record decision:** adopt, pilot, defer hoặc reject cùng evidence và owner.
10. **Set review date:** đánh giá lại khi PostgreSQL major, extension version, provider hoặc workload thay đổi.

## 32. Decision matrix

Có thể chấm từng tiêu chí theo thang 1–5, nhưng điểm số cần đi kèm evidence.

| Tiêu chí | Câu hỏi | Evidence |
|---|---|---|
| Maintainer health | Có người duy trì và phản hồi không? | Maintainers, release history, issue response |
| Security | Có policy, advisory và patch process không? | Security policy, CVE review, code/build scan |
| Correctness | Kết quả có đúng edge cases không? | Test suite, PoC, data validation |
| Performance | Đạt SLO và không phá workload cũ không? | Benchmark, p95/p99, resource metrics |
| Version support | Hỗ trợ target PostgreSQL versions không? | Compatibility matrix |
| Platform | Có package cho OS/architecture/provider không? | Build artifacts, provider allowlist |
| Recovery | Backup/restore/failover có hoạt động không? | Restore/failover rehearsal |
| Operations | Có metrics, logs, runbook và owner không? | Dashboard, runbook, on-call plan |
| License | Có quyền sử dụng/phân phối phù hợp không? | License/legal review |
| Exit | Có thể thay thế và export dữ liệu không? | Migration plan, rebuild test |

### 32.1. Không lấy tổng điểm để che blocker

Một extension có performance 5/5 nhưng không có binary cho target major vẫn có thể là blocker. Xác định các tiêu chí hard gate trước khi tính tổng điểm.

### 32.2. Kết quả quyết định

- **Adopt:** đáp ứng hard gates, SLO và vận hành; có owner.
- **Pilot:** có tiềm năng nhưng còn thiếu evidence; giới hạn blast radius.
- **Defer:** phụ thuộc chưa sẵn sàng hoặc target platform chưa hỗ trợ.
- **Reject:** risk/cost lớn hơn lợi ích hoặc không đáp ứng yêu cầu bắt buộc.

## 33. Compatibility register cho extension

Ghi mỗi dependency thành một record:

| Field | Nội dung |
|---|---|
| Extension | Tên và mục đích |
| Source | Repository/vendor/package |
| Installed/target version | Version hiện tại và mục tiêu |
| PostgreSQL range | Major versions được hỗ trợ |
| Platform | OS/architecture/provider |
| Extension type | SQL-only, native, worker, FDW... |
| Dependencies | Extension/OS libraries/services |
| License | License và approval |
| Maintainer/support | Owner, SLA/support model |
| Security | Advisory, CVE, trust, privilege |
| Performance | Benchmark baseline/result |
| Recovery | Backup/restore/failover evidence |
| Upgrade path | Extension update và PG major upgrade |
| Exit path | Replacement/export/rebuild |
| Risk/owner | Severity, mitigation, responsible team |
| Decision | Adopt/Pilot/Defer/Reject |

Một record cần lưu ngày review và version của tài liệu đã dùng. Khi PostgreSQL hoặc extension thay đổi version, cập nhật lại assessment.

## 34. Production rollout và change management

Sau khi PoC đạt, vẫn cần rollout theo giai đoạn.

### 34.1. Pre-production

- Pin extension version.
- Cài package trên mọi nodes.
- Cấu hình preload/settings.
- Kiểm tra privilege.
- Chạy restore test.
- Kiểm tra monitoring.
- Review runbook.
- Chuẩn bị rollback artifact.

### 34.2. Canary

Bật extension/functionality trên một cluster, database, tenant hoặc workload nhỏ nếu kiến trúc cho phép. So sánh metrics với baseline và kiểm tra correctness.

### 34.3. Gradual rollout

Tăng traffic/usage theo từng bước. Theo dõi latency, error, resource usage, WAL, replica lag và external dependencies.

### 34.4. Full adoption

Chỉ tăng lên production-wide sau khi canary và acceptance tests đạt. Ghi lại exact package/image digest và configuration.

### 34.5. Post-deploy review

Sau một khoảng quan sát:
- So sánh actual với benchmark.
- Review incidents/errors.
- Xác nhận backup/restore.
- Cập nhật dependency inventory.
- Xác nhận owner/on-call.
- Cập nhật exit plan và next review date.

## 35. Runbook: extension không load sau restart

1. Kiểm tra PostgreSQL startup logs.
2. Xác nhận shared_preload_libraries và thứ tự load.
3. Kiểm tra shared library có tồn tại trong library directory đúng không.
4. Kiểm tra ABI/major version của binary.
5. Kiểm tra OS shared-library dependencies.
6. Kiểm tra permissions/service account.
7. Nếu server không start, dùng quy trình recovery để gỡ extension khỏi preload config.
8. Cài package/build tương thích trên host.
9. Restart staging và xác nhận worker/function load.
10. Thực hiện production change theo approved rollback plan.

Không xóa binary đang dùng hoặc sửa library path ngẫu nhiên trên production.

## 36. Runbook: extension upgrade thất bại

1. Dừng rollout và giữ lại logs.
2. Xác định PostgreSQL version và extension version trước/sau.
3. Kiểm tra package/control/SQL update scripts.
4. Xác định migration script đã commit một phần hay transaction rollback.
5. Kiểm tra extension catalog và dependent objects.
6. Đọc vendor upgrade instructions.
7. Restore staging clone và tái hiện.
8. Chọn forward fix hoặc restore theo recovery plan.
9. Xác nhận backup trước khi tiếp tục production.
10. Chạy validation functions/queries và application tests.

Không tự sửa pg_extension catalog trực tiếp để ép version metadata khớp binary.

## 37. Runbook: performance regression

1. Xác định workload/query fingerprint bị ảnh hưởng.
2. So sánh baseline với current metrics.
3. Dùng EXPLAIN/BUFFERS trên query đại diện.
4. Kiểm tra extension index/operator có được planner dùng đúng không.
5. Kiểm tra CPU, memory, I/O, locks, WAL và background workers.
6. Kiểm tra data distribution/statistics.
7. Giảm hoặc tắt feature flag nếu có thể.
8. Dừng workload mới nếu vượt SLO.
9. Revert config hoặc extension usage theo rollback plan.
10. Ghi benchmark mới sau remediation.

Không drop extension ngay lập tức nếu database objects/indexes đang phụ thuộc vào nó.

## 38. Runbook: chuẩn bị rời bỏ extension

1. Inventory mọi objects, types, functions, operators và indexes phụ thuộc.
2. Xác định data và external state cần export.
3. Chọn replacement và mapping semantics.
4. Tạo schema mới theo expand/contract.
5. Backfill/rebuild indexes hoặc derived data.
6. Dual-read/compare outputs nếu phù hợp.
7. Chuyển traffic theo canary.
8. Xác nhận không còn extension-specific calls.
9. Backup và kiểm tra rollback.
10. Drop dependent objects theo thứ tự, rồi DROP EXTENSION khi không còn dependency.
11. Gỡ preload settings/package sau khi mọi database/cluster không còn sử dụng.
12. Cập nhật dependency inventory và security/package automation.

DROP EXTENSION ... CASCADE có thể xóa nhiều dependent objects. Luôn review dependency graph và dùng RESTRICT/default behavior để phát hiện dependencies trước khi xóa.

## 39. Checklist reliability

- [ ] Maintainer và ownership được xác định.
- [ ] Release cadence và support window phù hợp.
- [ ] Issue/security response có quy trình.
- [ ] Test suite và compatibility matrix tồn tại.
- [ ] License được review.
- [ ] Native code/procedural language/trust boundary đã đánh giá.
- [ ] Privileges và SECURITY DEFINER functions được kiểm tra.
- [ ] Failure modes và recovery behavior đã thử.
- [ ] Backup/restore và failover có evidence.
- [ ] On-call owner và runbook đã sẵn sàng.

## 40. Checklist performance

- [ ] Baseline workload được ghi lại.
- [ ] Dataset và concurrency đại diện.
- [ ] p50/p95/p99 latency được đo.
- [ ] Throughput và error rate được đo.
- [ ] CPU/memory/I/O được theo dõi.
- [ ] WAL và replica lag được đo.
- [ ] Index build/write amplification được đánh giá.
- [ ] Vacuum/reindex/maintenance cost được đo.
- [ ] Background worker overhead được đo.
- [ ] Workload hiện hữu không vượt regression budget.

## 41. Checklist portability và lifecycle

- [ ] PostgreSQL major/minor support được xác nhận.
- [ ] Native binary build đúng major/architecture.
- [ ] OS/runtime dependencies có package.
- [ ] Managed-service allowlist được xác nhận.
- [ ] Mọi standby/DR nodes có package tương thích.
- [ ] Logical replication/migration behavior được kiểm tra.
- [ ] Backup host có extension files cần thiết.
- [ ] Restore và failover rehearsal thành công.
- [ ] Extension update path có tài liệu.
- [ ] pg_upgrade/dump-restore path đã thử.
- [ ] Exit strategy và data export được chứng minh.
- [ ] Version pinning và package provenance được lưu.

## 42. Những hiểu lầm thường gặp

### 42.1. “Extension phổ biến thì chắc chắn an toàn”

Mức độ phổ biến không thay thế security review, support matrix, workload test hoặc restore rehearsal.

### 42.2. “CREATE EXTENSION thành công nghĩa là dependency sẵn sàng”

Cài thành công chỉ chứng minh server tìm thấy control/SQL files và hoàn thành script. Nó không chứng minh hiệu năng, HA, backup, portability hoặc correctness.

### 42.3. “SQL-only extension không có rủi ro”

SQL có thể tạo query đắt, locks, recursive behavior hoặc thay đổi privilege. SQL objects vẫn cần correctness và performance testing.

### 42.4. “Một binary dùng được cho mọi PostgreSQL major”

Native extensions thường phải build/cài theo major version. Không copy binary giữa các major.

### 42.5. “Physical standby đã có extension vì WAL được replicate”

WAL replicate database changes/catalog metadata, không phân phối shared libraries hoặc OS packages. Mọi failover host cần binary/dependencies phù hợp.

### 42.6. “pg_dump đã backup extension hoàn chỉnh”

Dump có thể chứa CREATE EXTENSION và database objects/data phù hợp, nhưng không đóng gói native binaries/control files hoặc mọi external state.

### 42.7. “Benchmark query nhanh là đủ”

Cần đo mixed workload, writes, tail latency, WAL, replicas, memory, maintenance và failure scenarios.

### 42.8. “Có thể drop extension để rollback”

Dependent objects/indexes có thể bị ảnh hưởng; extension-specific data có thể cần export/rebuild. Drop không phải rollback mặc định.

### 42.9. “Trusted nghĩa là đã được audit”

Trusted là metadata về quyền cài đặt, không phải chứng nhận bảo mật.

### 42.10. “Managed service sẽ tự lo mọi compatibility”

Provider quản lý host nhưng không bảo đảm application semantics, extension version, restore workflow hoặc portability sang provider khác.

## 43. Tài liệu chính thức tham khảo

- [PostgreSQL — Packaging Related Objects into an Extension](https://www.postgresql.org/docs/current/extend-extensions.html): cấu trúc extension, control files, scripts và versioning.
- [PostgreSQL — CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html): cài đặt extension và các properties.
- [PostgreSQL — ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html): cập nhật extension.
- [PostgreSQL — DROP EXTENSION](https://www.postgresql.org/docs/current/sql-dropextension.html): xóa extension và dependent objects.
- [PostgreSQL — Extension Building Infrastructure](https://www.postgresql.org/docs/current/extend-pgxs.html): PGXS và build extensions.
- [PostgreSQL — C Language Functions](https://www.postgresql.org/docs/current/xfunc-c.html): native C functions và runtime considerations.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): pg_extension và metadata liên quan.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): workload và system statistics.
- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backup.
- [PostgreSQL — pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): major version upgrade.
- [PostgreSQL — Foreign Data Wrappers](https://www.postgresql.org/docs/current/ddl-foreign-data.html): foreign tables và external data access.

Các đường dẫn /current/ thay đổi theo tài liệu phiên bản hiện hành. Trước khi quyết định, đọc tài liệu của đúng PostgreSQL major version, extension release và managed-service provider đang triển khai. Compatibility matrix của extension/vendor là nguồn bổ sung quan trọng nhưng cần được kiểm chứng bằng PoC.

## 44. Tổng kết

Một PostgreSQL extension có thể giải quyết một bài toán khó, nhưng cũng tạo thêm dependency trong database engine, deployment, backup, HA và quy trình nâng cấp. Quyết định adopt cần dựa trên evidence về độ tin cậy, hiệu năng và khả năng di chuyển.

1. **Reliability:** kiểm tra maintainer, release cadence, support, license, security, correctness và failure modes.
2. **Performance:** đo baseline và workload đại diện; xem latency, throughput, CPU, memory, I/O, WAL, replication, index và maintenance overhead.
3. **Portability:** xác nhận PostgreSQL versions, ABI, OS/architecture, package, managed-service support, standby parity và upgrade path.
4. **Recovery:** chứng minh backup/restore, failover, external state và RTO/RPO.
5. **Operations:** có metrics, logs, runbooks, owner và security patch process.
6. **Exit:** biết cách export/rebuild data, thay API/index và loại bỏ dependency.
7. **Decision:** chỉ adopt khi hard gates đạt, benchmark phù hợp và các rủi ro còn lại có owner/mitigation.

Trước khi phụ thuộc vào extension, hãy chứng minh hệ thống có thể cài, chạy, quan sát, phục hồi, nâng cấp và rời bỏ nó theo quy trình có thể lặp lại.
