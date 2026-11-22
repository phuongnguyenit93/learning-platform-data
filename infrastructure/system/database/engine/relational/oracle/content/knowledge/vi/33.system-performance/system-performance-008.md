# PGA, SGA, ASMM/AMM và đánh đổi bộ nhớ với hệ điều hành

Oracle Database dùng bộ nhớ để chia sẻ dữ liệu và metadata giữa các session, đồng thời cấp vùng làm việc riêng cho từng server process và background process. Hai vùng quan trọng nhất là **SGA (System Global Area)** và **PGA (Program Global Area)**. SGA là bộ nhớ dùng chung của một instance; PGA là bộ nhớ riêng gắn với process. Cách phân bổ hai vùng này ảnh hưởng trực tiếp tới cache hit, parse, sort/hash, TEMP I/O, số session đồng thời và lượng RAM còn lại cho hệ điều hành.

Oracle có ba cách quản lý bộ nhớ thường gặp. Manual memory management yêu cầu DBA đặt kích thước các vùng. ASMM (Automatic Shared Memory Management) tự điều chỉnh các thành phần SGA trong giới hạn SGA_TARGET, còn PGA được quản lý riêng. AMM (Automatic Memory Management) điều chỉnh tổng thể SGA và instance PGA thông qua MEMORY_TARGET. Mỗi cách có lợi ích và chi phí khác nhau, đặc biệt khi máy chủ dùng Linux HugePages, shared memory, container hoặc chạy nhiều instance.

Một cấu hình tốt không phải là cấu hình cấp càng nhiều RAM cho Oracle càng tốt. SGA và PGA cùng cạnh tranh RAM vật lý với kernel, filesystem cache, agent, backup, ASM, các database khác và ứng dụng trên host. Nếu Oracle làm hệ điều hành thiếu RAM, swap hoặc memory reclaim có thể khiến toàn hệ thống chậm hơn dù database có vẻ được cấp bộ nhớ lớn.

Sau bài học, bạn có thể:

- Phân biệt SGA, PGA, UGA và bộ nhớ của Oracle process.
- Nhận diện các thành phần chính của SGA và mục đích sử dụng.
- Hiểu PGA work area cho sort, hash join và các thao tác SQL.
- Giải thích optimal, one-pass và multi-pass execution của work area.
- So sánh manual memory management, ASMM và AMM.
- Hiểu SGA_TARGET, SGA_MAX_SIZE, PGA_AGGREGATE_TARGET, PGA_AGGREGATE_LIMIT, MEMORY_TARGET và MEMORY_MAX_TARGET.
- Sizing bộ nhớ theo workload, concurrency và RAM thực tế.
- Hiểu đánh đổi giữa SGA/PGA với OS, swap, HugePages và /dev/shm.
- Theo dõi bộ nhớ bằng dynamic performance views và advisor.
- Chẩn đoán TEMP spill, ORA-04031, ORA-04036, ORA-00845 và memory pressure.
- Xây dựng thay đổi memory parameter có kế hoạch, đo lường và rollback.

> Cơ chế và tham số có thể khác theo Oracle release, platform, RAC, CDB/PDB và cấu hình OS. Ví dụ dùng instance đơn giản để giải thích; kiểm tra Database Reference/Administrator's Guide của đúng phiên bản trước khi thay đổi production.

## 1. Bức tranh tổng quan về bộ nhớ Oracle

### 1.1. Hai vùng cốt lõi

Oracle instance dùng hai vùng memory chính:

| Vùng | Phạm vi | Mục đích chính |
| --- | --- | --- |
| SGA | Shared giữa các process của instance | Cache database blocks, SQL/PLSQL, metadata, redo và các cấu trúc dùng chung |
| PGA | Riêng cho từng Oracle process | Stack, session/process-private data và SQL work areas |

Khi một session chạy SQL, server process sử dụng SGA để truy cập shared data/cache và dùng PGA cho dữ liệu riêng của quá trình thực thi. Một sort hoặc hash join lớn có thể cần PGA đáng kể. Nhiều session cùng chạy các phép toán như vậy sẽ làm tổng PGA tăng theo concurrency.

### 1.2. Oracle instance và database

Database là tập các datafile, control file, online redo log và các file liên quan. Instance gồm memory structures (đặc biệt SGA) và background processes. Nhiều session có thể kết nối vào một instance; trong RAC, mỗi instance có SGA riêng và các instance phối hợp truy cập database chung qua cơ chế cluster.

SGA không phải một vùng memory dùng chung cho mọi database trên host. Mỗi instance có SGA riêng. PGA cũng được cấp cho các process thuộc instance tương ứng.

### 1.3. Luồng bộ nhớ đơn giản

```text
ỨNG DỤNG / SESSION
        |
        v
ORACLE SERVER PROCESS
        |
        +------ PGA riêng của process
        |         - stack và process state
        |         - private/session work
        |         - sort/hash work area
        |
        v
SGA dùng chung trong instance
        |
        +-- Database Buffer Cache
        +-- Shared Pool
        +-- Redo Log Buffer
        +-- Large Pool / Java Pool / Streams Pool
        |
        v
DATAFILES / REDO LOGS / TEMPFILES
```

### 1.4. Vì sao DBA phải quản lý cả SGA lẫn PGA?

Tăng SGA có thể giảm physical reads hoặc hard parse nếu workload tận dụng được cache, nhưng làm giảm RAM còn lại cho PGA và OS. Tăng PGA có thể giảm sort/hash spill ra TEMP, nhưng có thể làm host thiếu memory khi nhiều process cùng hoạt động.

Nếu chỉ nhìn database metrics, DBA có thể tăng một tham số và thấy một truy vấn nhanh hơn, trong khi OS bắt đầu swap hoặc một workload khác bị chậm. Memory tuning luôn phải nhìn từ instance tới toàn host.

## 2. SGA — System Global Area

### 2.1. Đặc điểm

SGA là vùng bộ nhớ chia sẻ được các Oracle process của cùng instance sử dụng. SGA thường được cấp khi instance khởi động và có thể resize một số thành phần online tùy cấu hình và release.

SGA chứa các cấu trúc dùng chung để giảm I/O, giảm parse và phối hợp hoạt động của instance. Kích thước SGA được kiểm soát bằng các tham số như SGA_TARGET, SGA_MAX_SIZE hoặc MEMORY_TARGET tùy chế độ quản lý.

### 2.2. Database Buffer Cache

Buffer cache lưu các bản sao database block được đọc từ datafile. Khi session cần block, Oracle có thể tìm block trong cache thay vì đọc lại từ storage.

Buffer cache hỗ trợ:

- Giảm physical I/O cho block được truy cập lại.
- Giữ block được sửa trong memory trước khi DBWn ghi xuống datafile.
- Phục vụ consistent read thông qua các cơ chế undo/version.
- Tận dụng cache cho index block và table block.

Buffer cache không phải nơi lưu vĩnh viễn dữ liệu. Datafile vẫn là nơi lưu trữ bền vững; checkpoint và DBWR ghi dirty buffers theo cơ chế Oracle.

Không đánh giá buffer cache chỉ bằng tỷ lệ cache hit. Một số physical read là bình thường, direct path read có thể bỏ qua buffer cache, và tăng cache hit không chắc giảm thời gian nếu workload bị giới hạn bởi CPU, latch/mutex hoặc I/O khác.

### 2.3. Shared Pool

Shared pool chứa các cấu trúc dùng chung, nổi bật gồm:

- Library cache: SQL cursor, PL/SQL program unit và các đối tượng thực thi được cache.
- Data dictionary cache: metadata về object, user, privilege, column và cấu trúc database.
- Các cấu trúc điều khiển/metadata khác phục vụ parse và execution.

Shared pool có vai trò lớn đối với hard parse, cursor sharing, PL/SQL và dictionary lookup. Shared pool quá nhỏ hoặc phân mảnh/áp lực allocation có thể góp phần gây ORA-04031. Tuy nhiên, tăng shared_pool_size không tự sửa được SQL parse liên tục, literal SQL không dùng bind hoặc memory leak trong ứng dụng.

### 2.4. Redo Log Buffer

Redo log buffer lưu các redo entries mô tả thay đổi cần ghi log. LGWR ghi redo từ buffer xuống online redo log theo các điều kiện và cơ chế nội bộ.

Redo buffer không phải cache dữ liệu table/index. Nó phục vụ durability/recovery và phối hợp với COMMIT. Không tăng LOG_BUFFER tùy tiện với giả định sẽ cải thiện mọi workload; sizing và hành vi phụ thuộc release, workload và Oracle tự quản lý một số khía cạnh.

### 2.5. Large Pool

Large pool cung cấp vùng cấp phát cho một số thao tác lớn hoặc dùng chung, ví dụ:

- Shared server UGA (khi cấu hình phù hợp).
- Parallel execution message buffers.
- Một số thao tác RMAN/I/O và backup.

Large pool giúp tránh gây áp lực lên shared pool cho các allocation phù hợp. Không phải mọi thao tác lớn đều tự động dùng large pool; hành vi tùy cấu hình và feature.

### 2.6. Java Pool và Streams Pool

Java pool phục vụ Java execution trong database khi tính năng này được dùng. Streams pool hỗ trợ Oracle Streams và một số thành phần/feature liên quan tới capture/apply hoặc xử lý dữ liệu tích hợp theo release.

Nếu không dùng tính năng tương ứng, nhu cầu hai pool có thể thấp. ASMM có thể điều chỉnh một số component này nếu được quản lý tự động và không bị ràng buộc bởi mức tối thiểu cấu hình.

### 2.7. Fixed SGA và các thành phần khác

SGA còn có fixed SGA và các vùng cấu trúc khác. Một số thành phần không được điều chỉnh như các pool động thông thường. Tổng SGA không chỉ bằng phép cộng các pool quen thuộc nhìn thấy trong một bảng tham số; cần xem V$SGAINFO, V$SGASTAT và các view tương ứng của release.

### 2.8. Xem kích thước SGA

```sql
SELECT name, value
FROM v$sgainfo
ORDER BY name;

SELECT component, current_size, min_size, max_size,
       user_specified_size, oper_count
FROM v$sga_dynamic_components
ORDER BY component;
```

V$SGAINFO cho thông tin tổng quát về SGA; V$SGA_DYNAMIC_COMPONENTS cho trạng thái và lịch sử resize của các component động. Một số cột/view có thể khác theo phiên bản.

## 3. PGA — Program Global Area

### 3.1. Đặc điểm

PGA là vùng memory riêng của Oracle process, không được chia sẻ như SGA. Server process dùng PGA để giữ dữ liệu và trạng thái riêng trong quá trình phục vụ session/request. Background process cũng có PGA riêng.

Tổng PGA của instance là tổng allocation của nhiều process, nên có thể thay đổi nhanh theo số session và workload đang chạy.

### 3.2. Thành phần thường gặp

PGA có thể chứa:

- Private SQL area và trạng thái thực thi liên quan.
- Session/process-private data.
- Stack space của process.
- SQL work areas cho sort, hash join, bitmap merge/create và một số thao tác khác.
- Các allocation riêng do Oracle feature hoặc code sử dụng.

Không phải mọi thành phần PGA đều có thể tự động thu nhỏ hoặc điều chỉnh như work area. Một phần PGA là untunable hoặc chỉ giải phóng theo vòng đời của process/call.

### 3.3. PGA tăng theo số process

Trong dedicated server, mỗi session thường gắn với một server process. Nếu 300 session đồng thời đều thực hiện sort/hash nặng, tổng PGA có thể cao hơn rất nhiều so với lúc chỉ có 30 session.

PGA sizing vì vậy phải dựa trên concurrency và workload đồng thời, không chỉ dựa vào một truy vấn chạy đơn lẻ.

### 3.4. PGA không phải TEMP

PGA là memory; TEMP là storage trong temporary tablespace. Khi work area không đủ memory, Oracle có thể spill dữ liệu trung gian ra TEMP. Điều này giúp xử lý tập dữ liệu lớn hơn memory nhưng phát sinh I/O và có thể làm query chậm.

TEMP không thay thế PGA và tăng TEMP không làm sort/hash trở nên nhanh hơn nếu nguyên nhân là memory pressure.

## 4. UGA và dedicated/shared server

### 4.1. UGA là gì?

UGA (User Global Area) giữ session state như thông tin phiên, trạng thái package, cursor/session data và các cấu trúc riêng của user session. Vị trí UGA phụ thuộc kiến trúc server.

### 4.2. Dedicated server

Với dedicated server, một server process phục vụ một session tại một thời điểm. UGA thường nằm trong PGA của server process. Vì vậy, session state làm tăng PGA của process tương ứng.

### 4.3. Shared server

Với shared server, nhiều session dùng chung một nhóm shared server process theo lượt. UGA phải tồn tại độc lập với process đang phục vụ request, nên thường được cấp trong SGA (large pool nếu cấu hình phù hợp, nếu không có thể dùng shared pool).

Điều này làm thay đổi cách tính memory: không thể nhân toàn bộ UGA như PGA riêng cho mỗi dedicated process.

### 4.4. So sánh

| Kiến trúc | Vị trí UGA thường gặp | Tác động |
| --- | --- | --- |
| Dedicated server | PGA của server process | PGA tăng theo session/process |
| Shared server | SGA, ưu tiên large pool khi phù hợp | Cần tính session state vào shared memory |

Kiến trúc shared server có lợi cho số lượng session lớn nhưng không phù hợp mọi workload. Connection pooling ở tầng ứng dụng thường là một công cụ quan trọng để giảm số session đồng thời.

## 5. PGA work areas và TEMP spill

### 5.1. Work area là gì?

Work area là vùng PGA dùng cho một số thao tác SQL cần xử lý tập dữ liệu trung gian. Các ví dụ:

- Sort cho ORDER BY, GROUP BY và DISTINCT.
- Hash join.
- Hash aggregation.
- Bitmap merge/create.

Kích thước work area ảnh hưởng việc thao tác có thể hoàn thành trong memory hay phải sử dụng TEMP.

### 5.2. Optimal execution

Nếu work area đủ lớn để thao tác hoàn tất trong memory, đây thường được gọi là optimal execution. Ví dụ sort có thể giữ dữ liệu và sắp xếp trong PGA mà không cần spill ra TEMP.

Optimal không có nghĩa toàn bộ query không đọc/ghi disk; table access và các operation khác vẫn có thể phát sinh I/O. Thuật ngữ mô tả riêng cách work area được thực hiện.

### 5.3. One-pass execution

Nếu work area không đủ để giữ toàn bộ dữ liệu nhưng có thể chia thành một số run/partition và hoàn tất với một lượt đọc/ghi trung gian chính, thao tác có thể ở chế độ one-pass. Nó dùng TEMP nhưng ít vòng I/O hơn multi-pass.

### 5.4. Multi-pass execution

Nếu dữ liệu lớn hơn nhiều so với memory có sẵn, sort/hash có thể phải đọc/ghi TEMP nhiều lượt. Đây là multi-pass execution, thường tốn I/O và thời gian hơn.

### 5.5. Vì sao TEMP I/O tăng?

TEMP spill có thể tăng khi:

- PGA_AGGREGATE_TARGET quá thấp so với workload.
- Nhiều sort/hash chạy đồng thời.
- Một số query có cardinality/ước lượng sai khiến work area không phù hợp.
- Dữ liệu trung gian lớn, join order hoặc SQL tạo row explosion.
- PGA bị giới hạn bởi PGA_AGGREGATE_LIMIT hoặc OS memory pressure.

Không phải mọi TEMP usage đều là lỗi. Cần phân biệt TEMP usage bình thường, spill do workload lớn và spill bất thường do SQL/plan/statistics.

### 5.6. Xem thống kê work area

```sql
SELECT name, value, unit
FROM v$pgastat
ORDER BY name;

SELECT
    operation_type,
    policy,
    estimated_optimal_size,
    estimated_onepass_size,
    last_memory_used,
    last_execution,
    last_tempseg_size
FROM v$sql_workarea
ORDER BY last_tempseg_size DESC NULLS LAST;
```

V$PGAStat cung cấp thống kê tổng thể PGA; V$SQL_WORKAREA mô tả work area gắn với SQL cursor. Dùng V$SQL_WORKAREA_ACTIVE để xem work area đang hoạt động tại thời điểm quan sát.

## 6. Manual memory management

### 6.1. Khái niệm

Manual memory management yêu cầu DBA chỉ định kích thước các thành phần SGA và/hoặc chính sách work area PGA bằng các tham số cụ thể. Cách này cho phép kiểm soát chi tiết nhưng cần hiểu workload, theo dõi và điều chỉnh thủ công.

### 6.2. Manual SGA

Khi không dùng ASMM/AMM, DBA có thể đặt các pool như:

- DB_CACHE_SIZE.
- SHARED_POOL_SIZE.
- LARGE_POOL_SIZE.
- JAVA_POOL_SIZE.
- STREAMS_POOL_SIZE.

Ngoài ra còn có các thành phần và tham số khác theo feature/release. Tổng memory phải nằm trong ngân sách SGA được cấu hình và SGA_MAX_SIZE nếu tham số này được dùng.

### 6.3. Manual work area

PGA work area có thể được quản lý bằng WORKAREA_SIZE_POLICY = MANUAL và các tham số như SORT_AREA_SIZE, HASH_AREA_SIZE, BITMAP_MERGE_AREA_SIZE hoặc CREATE_BITMAP_AREA_SIZE tùy thao tác/release.

Các tham số manual thường được áp dụng theo session/process và có thể làm tổng PGA tăng mạnh khi nhiều session chạy đồng thời. Chỉ dùng khi có lý do đặc biệt, workload kiểm soát chặt và hiểu được tổng memory.

### 6.4. Ưu điểm và nhược điểm

| Ưu điểm | Nhược điểm |
| --- | --- |
| Kiểm soát rõ từng component | DBA phải theo dõi và tự điều chỉnh |
| Có thể phù hợp workload ổn định, đặc thù | Dễ cấp thiếu hoặc thừa khi workload đổi |
| Hữu ích cho cấu hình legacy/đặc biệt | Khó quản lý khi concurrency biến động |

Với đa số hệ thống mới, ASMM cho SGA và PGA automatic work area management là điểm khởi đầu dễ vận hành hơn manual sizing hoàn toàn.

## 7. ASMM — Automatic Shared Memory Management

### 7.1. Khái niệm

ASMM tự động điều chỉnh kích thước một số thành phần SGA trong tổng ngân sách do SGA_TARGET xác định. DBA đặt tổng target và có thể đặt mức tối thiểu cho các component cần được bảo vệ. Oracle sử dụng memory advisor/broker để phân bổ lại SGA giữa các pool theo nhu cầu quan sát được.

ASMM quản lý SGA; nó không tự động phân bổ lại tổng memory giữa SGA và PGA như AMM. PGA vẫn được quản lý riêng, thường bằng PGA_AGGREGATE_TARGET và automatic work area management.

### 7.2. Các tham số chính

| Tham số | Vai trò |
| --- | --- |
| SGA_TARGET | Tổng target SGA mà ASMM quản lý |
| SGA_MAX_SIZE | Giới hạn tối đa SGA được xác định khi startup |
| DB_CACHE_SIZE | Kích thước tối thiểu/giá trị component nếu cấu hình rõ |
| SHARED_POOL_SIZE | Mức tối thiểu cho shared pool khi dùng ASMM |
| LARGE_POOL_SIZE | Mức tối thiểu cho large pool khi dùng ASMM |
| JAVA_POOL_SIZE | Mức tối thiểu cho java pool khi dùng ASMM |
| STREAMS_POOL_SIZE | Mức tối thiểu cho streams pool khi dùng ASMM |
| PGA_AGGREGATE_TARGET | Target PGA được quản lý riêng |
| PGA_AGGREGATE_LIMIT | Giới hạn tổng PGA của instance |

Khi SGA_TARGET được bật, các component size được chỉ định tường minh thường trở thành mức tối thiểu mà ASMM phải tôn trọng, thay vì Oracle được tự do giảm chúng xuống thấp hơn.

### 7.3. Cách hoạt động

Oracle có thể tăng/giảm các dynamic SGA component trong tổng SGA target khi nhu cầu thay đổi. Việc resize có thể diễn ra theo granule và chịu các giới hạn component, workload, release và trạng thái instance.

ASMM không có nghĩa tất cả component đều hoàn toàn tự động. Một số vùng SGA là fixed hoặc cần cấu hình riêng. Cần kiểm tra V$SGA_DYNAMIC_COMPONENTS và V$MEMORY_RESIZE_OPS để biết điều gì đang thay đổi.

### 7.4. Cấu hình ASMM minh họa

Một cấu hình minh họa trong SPFILE:

```sql
ALTER SYSTEM SET MEMORY_TARGET = 0 SCOPE = SPFILE;
ALTER SYSTEM SET SGA_TARGET = 8G SCOPE = SPFILE;
ALTER SYSTEM SET SGA_MAX_SIZE = 10G SCOPE = SPFILE;
ALTER SYSTEM SET PGA_AGGREGATE_TARGET = 3G SCOPE = SPFILE;
ALTER SYSTEM SET PGA_AGGREGATE_LIMIT = 6G SCOPE = SPFILE;
```

Đây chỉ là ví dụ số học, không phải khuyến nghị sizing. SGA_MAX_SIZE là tham số giới hạn được xác định khi khởi động; thay đổi có thể cần restart. Kiểm tra scope/modifiability của tham số trên phiên bản và cấu hình thực tế trước khi áp dụng.

### 7.5. Ưu điểm của ASMM

- Tự điều chỉnh các pool SGA khi workload thay đổi.
- Giảm nhu cầu cố định từng pool bằng kinh nghiệm.
- Có thể kết hợp với PGA_AGGREGATE_TARGET để quản lý work area riêng.
- Tương thích với một số cấu hình HugePages trên Linux khi dùng ASMM thay vì AMM.
- Cho phép DBA đặt minimum cho component quan trọng.

### 7.6. Giới hạn của ASMM

- Không tự cân bằng tổng SGA và PGA.
- Không thay thế việc sizing PGA theo concurrency.
- Component bị đặt minimum quá cao làm giảm phần Oracle có thể phân bổ cho pool khác.
- Thiếu RAM OS vẫn có thể xảy ra nếu SGA + PGA + process overhead quá lớn.
- Thống kê/Advisor không thể dự đoán hoàn hảo workload tương lai.

## 8. PGA automatic management

### 8.1. PGA_AGGREGATE_TARGET

PGA_AGGREGATE_TARGET là target tổng PGA cho instance, được dùng bởi automatic PGA memory management để điều tiết work area. Đây không phải quota cứng cho từng session và cũng không phải giới hạn tuyệt đối của mọi allocation PGA.

Nếu tổng nhu cầu work area cao, Oracle có thể cấp ít memory hơn cho từng work area và một số thao tác sẽ spill ra TEMP. PGA_AGGREGATE_TARGET nên được đặt dựa trên workload và RAM host.

### 8.2. WORKAREA_SIZE_POLICY

WORKAREA_SIZE_POLICY xác định chính sách quản lý work area:

- AUTO: Oracle tự điều chỉnh work area theo PGA target và workload.
- MANUAL: DBA dùng các tham số work area manual như SORT_AREA_SIZE và HASH_AREA_SIZE.

Với hệ thống hiện đại, AUTO thường là lựa chọn mặc định phù hợp. Không đổi sang MANUAL để chữa một query spill TEMP trước khi xác định nguyên nhân.

### 8.3. PGA_AGGREGATE_LIMIT

PGA_AGGREGATE_LIMIT đặt giới hạn tổng PGA mà instance được phép sử dụng theo cơ chế Oracle. Khi vượt limit, Oracle có thể hủy các call/session tiêu thụ untunable PGA lớn nhất theo quy tắc của phiên bản để đưa tổng sử dụng về mức cho phép.

Nếu limit quá thấp, workload hợp lệ như parallel query, sort lớn hoặc batch có thể bị abort với ORA-04036. Nếu limit quá cao so với RAM host, OS có thể chịu áp lực nghiêm trọng trước khi database đạt limit.

### 8.4. Target và limit khác nhau

| Tham số | Ý nghĩa |
| --- | --- |
| PGA_AGGREGATE_TARGET | Mục tiêu điều tiết PGA/work area |
| PGA_AGGREGATE_LIMIT | Giới hạn bảo vệ tổng PGA |

Không đặt PGA_AGGREGATE_LIMIT bằng PGA_AGGREGATE_TARGET theo thói quen. Cần khoảng đệm phù hợp với untunable PGA, concurrency, parallel execution và headroom của OS.

### 8.5. Tự động phân bổ work area

Trong AUTO, Oracle điều tiết memory cho sort/hash theo nhu cầu và số work area đang hoạt động. Khi nhiều thao tác cùng chạy, mỗi thao tác có thể nhận ít memory hơn. Một truy vấn chạy riêng có thể optimal, nhưng chạy đồng thời với nhiều truy vấn khác lại one-pass hoặc multi-pass.

Đây là lý do benchmark một query đơn lẻ không đủ để chọn PGA_AGGREGATE_TARGET cho production.

### 8.6. Theo dõi PGA

```sql
SELECT name, value, unit
FROM v$pgastat
ORDER BY name;

SELECT
    pga_target_for_estimate,
    pga_target_factor,
    advice_status,
    estd_pga_cache_hit_percentage,
    estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;
```

V$PGA_TARGET_ADVICE cung cấp ước lượng cho các mức target khác nhau khi advisor có dữ liệu. Xem advice_status và khoảng thời gian thu thập; không coi con số dự đoán là cam kết hiệu năng.

## 9. AMM — Automatic Memory Management

### 9.1. Khái niệm

AMM dùng MEMORY_TARGET để Oracle tự điều chỉnh phân bổ giữa SGA và instance PGA trong tổng memory target. MEMORY_MAX_TARGET xác định mức MEMORY_TARGET tối đa có thể đặt mà không cần tăng giới hạn startup.

Khác ASMM, AMM quản lý cả hai phía SGA/PGA trong cùng một ngân sách tổng thể. Oracle có thể chuyển ngân sách giữa SGA và PGA theo nhu cầu, trong phạm vi giới hạn và các minimum đã cấu hình.

### 9.2. Tham số chính

| Tham số | Vai trò |
| --- | --- |
| MEMORY_TARGET | Tổng target memory Oracle quản lý động giữa SGA và PGA |
| MEMORY_MAX_TARGET | Giới hạn tối đa MEMORY_TARGET được đặt khi startup |
| SGA_TARGET | Minimum target SGA khi AMM được bật, nếu được cấu hình |
| PGA_AGGREGATE_TARGET | Minimum target PGA khi AMM được bật, nếu được cấu hình |
| SGA_MAX_SIZE | Giới hạn SGA theo cấu hình startup; xem xét cùng AMM/platform |

Khi AMM được bật, SGA_TARGET và PGA_AGGREGATE_TARGET có vai trò minimum cho phần tương ứng, không còn là hai ngân sách độc lập được cộng cứng như khi ASMM. Không đặt tổng các minimum vượt MEMORY_TARGET.

### 9.3. Cấu hình AMM minh họa

Ví dụ tham số trong SPFILE:

```sql
ALTER SYSTEM SET MEMORY_MAX_TARGET = 12G SCOPE = SPFILE;
ALTER SYSTEM SET MEMORY_TARGET = 10G SCOPE = SPFILE;
ALTER SYSTEM SET SGA_TARGET = 6G SCOPE = SPFILE;
ALTER SYSTEM SET PGA_AGGREGATE_TARGET = 2G SCOPE = SPFILE;
```

Trong ví dụ, tổng minimum SGA/PGA là 8 GB và MEMORY_TARGET là 10 GB, để Oracle còn khoảng linh hoạt. Đây chỉ là minh họa cú pháp; phải sizing theo RAM host và yêu cầu ứng dụng. MEMORY_MAX_TARGET thường cần được xác định trước khi startup; thay đổi tham số static cần restart.

### 9.4. Memory broker

Oracle dùng cơ chế quản lý memory để điều chỉnh các component và phân bổ giữa SGA/PGA theo target. Việc điều chỉnh có thể dựa trên workload gần đây, không phải một bộ dự đoán biết trước mọi đỉnh tải.

AMM không thể tạo thêm RAM vật lý. Nếu host đã thiếu memory, tăng MEMORY_TARGET có thể làm OS swap hoặc OOM; database không thể tối ưu vượt giới hạn phần cứng.

### 9.5. Ưu điểm

- Một tổng target giúp đơn giản hóa quản lý SGA/PGA.
- Oracle có thể chuyển ngân sách giữa shared memory và process memory theo nhu cầu.
- Có thể giảm công việc DBA phải tự cân bằng hai target.
- Hữu ích ở môi trường đơn giản, không có ràng buộc HugePages hoặc shared memory đặc biệt.

### 9.6. Hạn chế

- Cần kiểm soát RAM host và headroom rất cẩn thận.
- Có yêu cầu platform/OS, đặc biệt /dev/shm trên Linux.
- AMM không tương thích với Linux HugePages theo cách cấu hình Oracle phổ biến; nếu cần HugePages cho SGA lớn, thường chọn ASMM hoặc manual SGA.
- Có thể không phù hợp môi trường production cần pin SGA/huge pages hoặc chạy nhiều instance cạnh tranh RAM.
- Một target tổng không thay thế việc hiểu workload, PGA spill và SGA component pressure.

## 10. So sánh Manual, ASMM và AMM

### 10.1. Bảng so sánh

| Tiêu chí | Manual | ASMM | AMM |
| --- | --- | --- | --- |
| SGA components | DBA đặt thủ công | Oracle điều chỉnh trong SGA_TARGET | Oracle điều chỉnh trong MEMORY_TARGET |
| PGA work area | Có thể manual | Thường automatic qua PGA_AGGREGATE_TARGET | Oracle quản lý trong tổng target, vẫn có các target/minimum |
| Tham số trung tâm | Component *_SIZE, workarea policy | SGA_TARGET + PGA_AGGREGATE_TARGET | MEMORY_TARGET + MEMORY_MAX_TARGET |
| Độ linh hoạt | Phụ thuộc DBA | Linh hoạt trong SGA | Linh hoạt giữa SGA/PGA |
| Độ phức tạp vận hành | Cao | Trung bình | Đơn giản hơn ở cấu hình phù hợp |
| HugePages trên Linux | Có thể dùng | Thường là lựa chọn phù hợp | AMM không tương thích với HugePages |
| Khi phù hợp | Workload đặc thù/legacy, cần kiểm soát chặt | Nhiều production cần HugePages và PGA độc lập | Môi trường đáp ứng điều kiện AMM, ưu tiên một tổng target |

### 10.2. Lựa chọn thường gặp

Với database production trên Linux có SGA lớn và yêu cầu HugePages, cấu hình ASMM cho SGA cùng automatic PGA management thường là lựa chọn phổ biến:

- SGA_TARGET/SGA_MAX_SIZE điều khiển SGA.
- PGA_AGGREGATE_TARGET điều tiết work area.
- PGA_AGGREGATE_LIMIT bảo vệ instance khỏi PGA quá mức.
- HugePages được dùng cho SGA nếu OS và Oracle cấu hình đúng.

Với môi trường đơn giản không dùng HugePages, AMM có thể giảm thao tác sizing thủ công. Cần kiểm tra /dev/shm, platform và tổng RAM.

Manual hoàn toàn chỉ nên dùng khi có yêu cầu kỹ thuật rõ và người vận hành có đủ số liệu để duy trì.

### 10.3. Không trộn các chế độ tùy tiện

Một số tham số có quan hệ loại trừ hoặc thay đổi ý nghĩa theo chế độ. Trước khi chuyển từ AMM sang ASMM hoặc ngược lại:

1. Kiểm tra toàn bộ memory parameters hiện tại.
2. Xác định tham số static/dynamic và scope.
3. Tính lại tổng SGA, PGA và OS headroom.
4. Kiểm tra HugePages và /dev/shm.
5. Lập kế hoạch SPFILE, restart và rollback.
6. Theo dõi memory resize, PGA, TEMP và OS sau thay đổi.

Không chỉ đổi MEMORY_TARGET về 0 rồi cho rằng instance tự chuyển sang cấu hình ASMM đúng.

## 11. Các tham số memory cần hiểu rõ

### 11.1. SGA_TARGET

SGA_TARGET đặt tổng target SGA cho ASMM. Oracle tự điều chỉnh các component được quản lý trong giới hạn target và các minimum cấu hình. Có thể thay đổi online trong phạm vi được hỗ trợ, nhưng không thể vượt giới hạn startup SGA_MAX_SIZE.

### 11.2. SGA_MAX_SIZE

SGA_MAX_SIZE là giới hạn SGA tối đa được cấu hình khi instance khởi động. SGA_TARGET có thể thấp hơn để dành khả năng tăng SGA online trong phạm vi max. Thay đổi SGA_MAX_SIZE thường cần restart; kiểm tra ISSES_MODIFIABLE/ISSYS_MODIFIABLE và tài liệu release trước khi lập kế hoạch.

### 11.3. PGA_AGGREGATE_TARGET

PGA_AGGREGATE_TARGET là target cho automatic PGA/work area management. Đây là target điều tiết, không phải reservation cố định hoặc hard cap. Khi tăng, work area có cơ hội nhận nhiều memory hơn; khi giảm, spill TEMP có thể tăng.

### 11.4. PGA_AGGREGATE_LIMIT

PGA_AGGREGATE_LIMIT bảo vệ instance trước tổng PGA allocation vượt ngưỡng. Cần đặt đủ cao cho workload hợp lệ nhưng vẫn nằm trong ngân sách host. Nếu đặt quá thấp, các call tiêu thụ nhiều untunable PGA có thể bị terminate.

### 11.5. MEMORY_TARGET

MEMORY_TARGET bật AMM và đặt tổng target memory Oracle quản lý giữa SGA và PGA. Giá trị này có thể điều chỉnh online trong phạm vi MEMORY_MAX_TARGET và các điều kiện runtime.

### 11.6. MEMORY_MAX_TARGET

MEMORY_MAX_TARGET là giới hạn tối đa cho MEMORY_TARGET. Nó được xác định khi startup và thay đổi thường cần restart. Trên Linux, phải tính khả năng cấp phát shared memory qua /dev/shm khi bật AMM.

### 11.7. WORKAREA_SIZE_POLICY

WORKAREA_SIZE_POLICY = AUTO cho phép Oracle tự quản lý work area theo PGA target. MANUAL dùng các tham số vùng làm việc thủ công. Với hệ thống mới, AUTO thường phù hợp hơn vì quản lý theo tổng workload đồng thời.

### 11.8. Các component size khi dùng ASMM

Khi SGA_TARGET được bật, các tham số như DB_CACHE_SIZE và SHARED_POOL_SIZE có thể dùng làm mức tối thiểu cho component tương ứng. Đặt các mức tối thiểu quá cao sẽ làm Oracle ít khả năng chuyển memory sang component khác.

### 11.9. Xem giá trị và trạng thái tham số

```sql
SELECT
    name,
    value,
    issys_modifiable,
    isses_modifiable,
    isdefault
FROM v$parameter
WHERE name IN (
    'memory_target',
    'memory_max_target',
    'sga_target',
    'sga_max_size',
    'pga_aggregate_target',
    'pga_aggregate_limit',
    'workarea_size_policy',
    'use_large_pages'
)
ORDER BY name;
```

V$PARAMETER phản ánh giá trị session/instance hiện tại theo ngữ cảnh view. Với cấu hình SPFILE và giá trị pending/restart, kiểm tra thêm V$SPPARAMETER và V$PARAMETER2 khi phù hợp.

## 12. Bộ nhớ Oracle và RAM hệ điều hành

### 12.1. Không phải toàn bộ RAM host thuộc Oracle

Host còn cần memory cho:

- Kernel, driver và system services.
- Filesystem cache và các daemon hệ thống.
- ASM, listener, agent, monitoring và backup.
- Các Oracle instance khác.
- Application server, middleware và job scheduler nếu cùng host.
- Các process quản trị và công cụ vận hành.

Nếu cấp gần hết RAM cho SGA/PGA, hệ điều hành không còn khoảng trống để xử lý burst, process mới, filesystem cache hoặc hoạt động nền.

### 12.2. SGA và PGA nhìn từ OS

SGA là shared memory được nhiều Oracle process map vào address space. PGA là memory riêng của process. Vì SGA có thể xuất hiện trong RSS của nhiều process, cộng RSS từng Oracle process có thể đếm cùng một vùng shared memory nhiều lần.

Trên Linux, PSS (Proportional Set Size) có thể giúp phân bổ phần shared memory theo tỷ lệ giữa các process; tuy vậy, cần hiểu cách công cụ đo và đối chiếu với SGA/PGA views của Oracle.

### 12.3. RAM available quan trọng hơn RAM free

Linux thường dùng RAM nhàn rỗi cho page cache/buffers. MemFree thấp không nhất thiết là thiếu memory. Xem MemAvailable, swap activity, reclaim và memory pressure cùng lúc:

```text
free -h
vmstat 1
cat /proc/meminfo
```

Trong vmstat, các cột si/so cho biết swap in/out theo chu kỳ. Swap activity liên tục cùng latency tăng là dấu hiệu cần điều tra; không chỉ nhìn một snapshot.

### 12.4. Swap và Oracle

Swap cho phép OS chuyển page memory ra thiết bị lưu trữ khi thiếu RAM. Nếu SGA/PGA bị swap hoặc host phải swap mạnh, latency có thể tăng rất lớn. Database có thể vẫn báo target memory bình thường trong khi response time xấu đi do OS paging.

Không xem swap là phần RAM mở rộng hiệu năng. Một số OS/configuration dùng swap như cơ chế bảo vệ hoặc yêu cầu hệ thống, nhưng mục tiêu vận hành là tránh sustained swapping cho memory workload của database.

### 12.5. OOM killer và process termination

Khi host hoặc container hết memory, Linux có thể kích hoạt OOM killer và terminate process. Oracle instance có thể bị ảnh hưởng đột ngột, alert log ghi lỗi process chết hoặc instance recovery. PGA_AGGREGATE_LIMIT không thay thế việc giữ headroom OS; nó chỉ kiểm soát PGA theo quy tắc Oracle.

### 12.6. Memory pressure có thể gây nhiều triệu chứng

- Query chậm do swap/page reclaim.
- Process không khởi tạo được do thiếu memory.
- Oracle process bị OS kill.
- SGA resize thất bại hoặc không thực hiện được.
- PGA allocation bị hạn chế, sort/hash spill TEMP tăng.
- Backup, monitoring hoặc ASM bị thiếu memory.

Khi có sự cố, đối chiếu timestamp giữa alert log, database views, OS metrics và kernel log.

## 13. HugePages và shared memory trên Linux

### 13.1. HugePages là gì?

HugePages cho phép OS quản lý vùng memory bằng page lớn hơn page thông thường. Với SGA lớn, HugePages có thể giảm số page table entries, giảm chi phí quản lý page và TLB pressure. HugePages cũng giúp cấp phát SGA theo vùng được reserve, tránh một số rủi ro paging của shared memory.

HugePages chủ yếu áp dụng cho SGA; PGA của process không được chuyển thành một vùng HugePages chung như SGA.

### 13.2. ASMM và HugePages

Trên Linux, cấu hình ASMM hoặc manual SGA thường được dùng khi muốn tận dụng HugePages. Sizing SGA phải phù hợp với số HugePages đã reserve và memory còn lại cho OS/PGA.

Nếu SGA yêu cầu nhiều HugePages hơn số OS đã reserve, instance có thể không khởi động hoặc không dùng HugePages theo chế độ mong muốn, tùy USE_LARGE_PAGES setting.

### 13.3. AMM và HugePages

AMM trên Linux sử dụng cơ chế shared memory liên quan /dev/shm và không tương thích với cấu hình HugePages Oracle thông thường. Nếu yêu cầu HugePages cho SGA, thường phải chọn ASMM/manual SGA thay vì AMM.

Đây là đánh đổi quan trọng: AMM đơn giản hóa cân bằng SGA/PGA, còn ASMM kết hợp HugePages có thể phù hợp hơn với database lớn cần kiểm soát OS memory.

### 13.4. USE_LARGE_PAGES

USE_LARGE_PAGES điều khiển việc Oracle sử dụng HugePages trên Linux trong các release hỗ trợ. Các mode như TRUE/ONLY có semantics khác nhau; ONLY yêu cầu cấu hình HugePages đủ để startup, trong khi mode fallback có thể cho phép dùng page thường nếu không đủ.

Không thay đổi tham số này trước khi xác nhận HugePages_Total, HugePages_Free, Hugepagesize và lượng SGA cần cấp phát.

### 13.5. Memlock

OS user chạy Oracle cần giới hạn memlock phù hợp để có thể lock/reserve vùng memory theo yêu cầu. Nếu memlock quá thấp, HugePages có thể không được dùng như dự định. Cấu hình ulimit/security limits phụ thuộc Linux distribution và cách cài Oracle.

### 13.6. Kiểm tra HugePages

```text
grep -i Huge /proc/meminfo
ulimit -l
```

Các trường thường xem:

- HugePages_Total: tổng page lớn đã reserve.
- HugePages_Free: page lớn còn trống.
- HugePages_Rsvd: page đã được reserve cho mapping.
- Hugepagesize: kích thước mỗi page.

Không chỉ nhìn HugePages_Free ngay sau startup; đối chiếu SGA thực tế và process mappings.

### 13.7. HugePages và headroom

HugePages được reserve làm giảm phần RAM còn lại cho page allocator thông thường. Reserve quá nhiều có thể làm OS và PGA thiếu memory; reserve quá ít có thể làm SGA không dùng hết huge pages. Tính theo tổng SGA của mọi instance trên host và chừa headroom cho OS.

## 14. AMM và /dev/shm trên Linux

### 14.1. /dev/shm là gì?

/dev/shm thường là tmpfs mount dùng cho POSIX shared memory. Khi AMM được bật trên Linux, Oracle sử dụng vùng shared memory này để quản lý memory target. Kích thước mount phải đủ cho cấu hình AMM.

### 14.2. Kiểm tra dung lượng

```text
df -h /dev/shm
mount | grep /dev/shm
```

Đối chiếu dung lượng mount với MEMORY_TARGET/MEMORY_MAX_TARGET và yêu cầu của release. Cần tính cả các ứng dụng/process khác cũng sử dụng tmpfs.

### 14.3. ORA-00845

ORA-00845: MEMORY_TARGET not supported on this system thường xuất hiện khi điều kiện shared memory cho AMM trên Linux không đáp ứng, ví dụ /dev/shm không tồn tại, mount không đủ dung lượng hoặc cấu hình hệ thống không phù hợp.

Hướng xử lý:

1. Kiểm tra alert log và OS mount.
2. Kiểm tra df -h /dev/shm.
3. Xác nhận MEMORY_TARGET và MEMORY_MAX_TARGET.
4. Tăng dung lượng tmpfs theo hướng dẫn OS/DBA nếu host có đủ RAM.
5. Nếu dùng HugePages, xem xét chuyển sang ASMM/manual SGA thay vì AMM.

Không tăng /dev/shm vượt RAM khả dụng mà không tính tổng memory host.

### 14.4. /dev/shm cũng tiêu thụ tài nguyên host

tmpfs không phải storage miễn phí. Trang tmpfs được hỗ trợ bởi memory và có thể chịu ảnh hưởng swap theo OS. Tăng mount size không tự cấp RAM vật lý; nó chỉ đặt giới hạn tối đa có thể dùng.

### 14.5. Container và /dev/shm

Trong Docker/Kubernetes, /dev/shm và memory limit của container có thể nhỏ hơn host. Oracle trong container phải được cấu hình theo giới hạn container, không theo RAM toàn node. Kiểm tra mount size, cgroup limit và phiên bản Oracle được chứng nhận cho môi trường đó.

## 15. Sizing bộ nhớ theo host

### 15.1. Bắt đầu từ ngân sách RAM

Một cách lập ngân sách:

```text
RAM vật lý khả dụng
  - Kernel và OS reserve
  - Agent, backup, monitoring, ASM
  - Ứng dụng và middleware cùng host
  - Các Oracle instance khác
  - Safety headroom cho burst
  = Ngân sách dự kiến cho instance đang sizing

Ngân sách instance
  -> SGA
  -> PGA theo concurrency/workload
  -> process overhead và phần dao động
```

Đây là mô hình lập kế hoạch, không phải công thức cố định. SGA_TARGET và PGA_AGGREGATE_TARGET là target; actual PGA và process overhead có thể thay đổi.

### 15.2. Không lấy toàn bộ RAM trừ SGA

Phần còn lại không thể mặc định dành hết cho PGA. Host còn cần process memory, kernel, page cache, background process, agent và các workload khác. PGA_AGGREGATE_LIMIT cũng không đại diện cho tổng memory tối đa của toàn Oracle host.

### 15.3. Tính PGA theo concurrency

Đặt câu hỏi:

- Bao nhiêu session chạy đồng thời?
- Bao nhiêu query đồng thời có sort/hash lớn?
- Có batch/reporting chạy cùng OLTP không?
- Parallel query có dùng DOP cao không?
- Một session có thể mở nhiều cursor/work area đồng thời không?
- Có process ETL/backup tiêu thụ PGA lớn không?

PGA demand không bằng số session nhân một con số cố định. Work area cấp phát động và nhiều session chỉ idle. Dùng số liệu V$PGASTAT, V$SQL_WORKAREA_ACTIVE và workload peak để ước lượng.

### 15.4. Parallel execution

Parallel query có thể tạo nhiều PX server process. Mỗi process có PGA riêng và có thể có work area riêng; tổng PGA cho một statement parallel có thể lớn hơn serial execution đáng kể.

Khi tăng DOP, tính cả:

- Số PX server process đồng thời.
- Work area của mỗi process.
- Các statement parallel chạy cùng lúc.
- PGA cho coordinator và background process.
- Tác động tới TEMP và I/O.

Resource Manager, parallel statement queuing và giới hạn DOP có thể giúp bảo vệ host khi nhiều query parallel cùng đến.

### 15.5. Nhiều instance trên cùng host

Với RAC node hoặc host chạy nhiều database instance, phải tính tổng SGA của từng instance và tổng PGA đồng thời của tất cả instance. Không sizing từng instance độc lập như thể chúng sở hữu toàn bộ RAM.

HugePages cũng là tài nguyên host dùng chung. Reserve phải đủ cho tổng SGA cần HugePages của các instance và chừa memory thường cho OS/PGA.

### 15.6. Ví dụ ngân sách minh họa

Giả sử host có 64 GB RAM. Một kế hoạch sơ bộ có thể dành 12 GB cho OS/kernel/headroom, 4 GB cho agent/ASM/backup và 4 GB dự phòng biến động. Phần còn lại khoảng 44 GB là ngân sách dự kiến cho Oracle instance và process overhead liên quan.

Trong ngân sách đó, DBA có thể thử mô hình SGA 24 GB, PGA target 10 GB và PGA limit 14 GB, với phần còn lại cho process overhead/dao động. Các con số chỉ minh họa cách suy nghĩ; phải kiểm chứng bằng actual peak memory, workload và OS metrics. Không lấy ví dụ này làm cấu hình cho host bất kỳ.

## 16. Trade-off SGA với OS và PGA

### 16.1. Tăng SGA

Lợi ích có thể có:

- Buffer cache giữ được nhiều block nóng hơn.
- Shared pool giữ được nhiều cursor/metadata hơn.
- Giảm một số physical reads hoặc parse overhead.

Chi phí/rủi ro:

- Giảm RAM còn lại cho PGA và OS.
- Có thể làm PGA spill TEMP nhiều hơn nếu tổng host memory cố định.
- Có thể tăng shared memory footprint và yêu cầu HugePages.
- Nếu cache hit không phải bottleneck, tăng SGA có thể không cải thiện response time.

### 16.2. Tăng PGA

Lợi ích có thể có:

- Sort/hash work area lớn hơn.
- Giảm one-pass/multi-pass spill.
- Giảm TEMP I/O và elapsed time của một số query.

Chi phí/rủi ro:

- PGA là memory riêng theo process, tăng nhanh khi concurrency tăng.
- Có thể gây memory pressure, swap hoặc OOM.
- Parallel query nhân thêm process/work area.
- PGA_AGGREGATE_LIMIT có thể abort call nếu vượt ngưỡng.

### 16.3. Tăng cả hai

Không thể tăng cả SGA lẫn PGA mà không có giới hạn. Nếu host RAM không tăng, phải lấy memory từ OS/headroom hoặc workload khác. Một query/report nhanh hơn có thể làm OLTP latency tăng do toàn host thiếu RAM.

### 16.4. Giảm SGA quá mức

SGA quá nhỏ có thể tăng physical reads, hard parse hoặc allocation pressure. Khi đó database có thể chậm dù OS còn nhiều memory. Cần xác định component nào thực sự thiếu thay vì tăng toàn bộ SGA.

### 16.5. Giảm PGA quá mức

PGA quá nhỏ làm work area spill TEMP, tăng I/O, thời gian query và cạnh tranh TEMP tablespace. Nếu TEMP tăng nhưng PGA target đã phù hợp với host, nguyên nhân có thể là SQL tạo intermediate set quá lớn hoặc plan kém.

### 16.6. Tối ưu hệ thống thay vì một truy vấn

Đánh giá memory bằng workload mix: OLTP, reporting, batch, ETL, backup và parallel query. Không để một report query chiếm gần hết PGA khiến hàng trăm session OLTP thiếu resource. Resource Manager và workload scheduling là một phần của memory management.

## 17. Theo dõi SGA và dynamic resize

### 17.1. V$SGAINFO

V$SGAINFO cho biết các thông tin tổng quát như kích thước SGA, granule size và một số vùng SGA:

```sql
SELECT name, bytes
FROM v$sgainfo
ORDER BY name;
```

### 17.2. V$SGASTAT

V$SGASTAT cho biết phân bổ memory theo pool/name:

```sql
SELECT
    pool,
    name,
    bytes
FROM v$sgastat
ORDER BY pool, bytes DESC;
```

Đây là view chi tiết allocation, không phải mọi dòng đều tương ứng một component độc lập có thể resize. Dùng để tìm pool/area đang tiêu thụ memory và so sánh theo thời gian.

### 17.3. V$SGA_DYNAMIC_COMPONENTS

Theo dõi kích thước hiện tại/min/max và hoạt động resize:

```sql
SELECT
    component,
    current_size,
    min_size,
    max_size,
    user_specified_size,
    oper_count,
    last_oper_type,
    last_oper_time
FROM v$sga_dynamic_components
ORDER BY current_size DESC;
```

Component có current_size bằng 0 hoặc không xuất hiện tùy cấu hình/feature. Xem cùng tham số và workload, không kết luận thiếu memory chỉ vì một component nhỏ.

### 17.4. V$MEMORY_RESIZE_OPS

View này ghi lại các thao tác resize memory gần đây:

```sql
SELECT
    component,
    oper_type,
    oper_mode,
    initial_size,
    target_size,
    final_size,
    status,
    start_time,
    end_time
FROM v$memory_resize_ops
ORDER BY start_time DESC;
```

Resize failure hoặc repeated resize có thể cho biết target/constraint chưa phù hợp. Kiểm tra alert log và các tham số minimum/maximum để hiểu lý do.

### 17.5. Buffer cache và shared pool

Không chỉ nhìn kích thước:

- Buffer cache: xem physical reads, logical reads, workload reuse và direct path behavior.
- Shared pool: xem parse count, hard parse, cursor reuse, allocation failure và ORA-04031.
- Large pool: xem shared server, parallel execution, RMAN và allocation liên quan.

Cache hit ratio đơn lẻ không đủ để quyết định tăng pool. Dùng wait events, SQL plan, actual I/O và thời gian đáp ứng.

## 18. Theo dõi PGA và work area

### 18.1. V$PGASTAT

Các metric đáng chú ý gồm:

- aggregate PGA target parameter.
- total PGA allocated.
- total PGA inuse.
- maximum PGA allocated.
- over allocation count.
- cache hit percentage.
- extra bytes read/written.
- global memory bound.

Truy vấn:

```sql
SELECT name, value, unit
FROM v$pgastat
WHERE name IN (
    'aggregate PGA target parameter',
    'total PGA allocated',
    'total PGA inuse',
    'maximum PGA allocated',
    'over allocation count',
    'cache hit percentage',
    'extra bytes read/written',
    'global memory bound'
)
ORDER BY name;
```

Cache hit percentage là một metric tổng hợp về work area; không đồng nghĩa buffer cache hit ratio và không nên dùng riêng để tăng target.

### 18.2. V$PROCESS

Xem PGA theo process:

```sql
SELECT
    pid,
    spid,
    program,
    pga_used_mem,
    pga_alloc_mem,
    pga_freeable_mem,
    pga_max_mem
FROM v$process
ORDER BY pga_alloc_mem DESC;
```

Đây là ảnh chụp allocation theo process. Ghép với V$SESSION qua PADDR/ADDR khi cần tìm session đang dùng PGA lớn; background process cũng có thể tiêu thụ memory đáng kể.

### 18.3. V$PROCESS_MEMORY

Phân loại memory theo process/category:

```sql
SELECT
    pid,
    category,
    allocated,
    used,
    max_allocated
FROM v$process_memory
ORDER BY allocated DESC;
```

Các category có thể gồm SQL, PL/SQL, OLAP, Java, Freeable và Other tùy release. Dùng để hiểu loại allocation, không giả định toàn bộ PGA là SQL work area.

### 18.4. V$SQL_WORKAREA_ACTIVE

Xem work area đang hoạt động:

```sql
SELECT
    sid,
    sql_id,
    operation_type,
    policy,
    expected_size,
    actual_mem_used,
    max_mem_used,
    number_passes,
    tempseg_size
FROM v$sql_workarea_active
ORDER BY actual_mem_used DESC;
```

NUMBER_PASSES và TEMPSEG_SIZE giúp nhận biết operation có spill ra TEMP. Đây là snapshot; một work area có thể kết thúc trước khi DBA truy vấn view.

### 18.5. V$TEMPSEG_USAGE

Xem session đang sử dụng temporary segment:

```sql
SELECT
    username,
    session_addr,
    session_num,
    sql_id,
    tablespace,
    segtype,
    blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
```

Ghép với V$SESSION để tìm SQL_ID, module, action và thời gian chạy. TEMP usage cũng có thể đến từ temporary table, index build, bitmap operation hoặc operation khác, không chỉ sort/hash spill.

## 19. Memory advisor

### 19.1. SGA_TARGET_ADVICE

V$SGA_TARGET_ADVICE ước lượng tác động của các mức SGA target khác nhau dựa trên workload đã quan sát:

```sql
SELECT
    sga_size,
    sga_size_factor,
    estd_db_time,
    estd_db_time_factor,
    estd_physical_reads
FROM v$sga_target_advice
ORDER BY sga_size;
```

Advisor chỉ hữu ích khi đã thu thập workload đủ đại diện. Một workload chỉ chạy ban ngày không thể mô tả hoàn toàn batch đêm.

### 19.2. PGA_TARGET_ADVICE

```sql
SELECT
    pga_target_for_estimate,
    pga_target_factor,
    estd_pga_cache_hit_percentage,
    estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;
```

Nếu estimated cache hit tăng ít khi tăng PGA, lợi ích có thể thấp. Nếu overalloc count khác 0, cần hiểu workload/target trước khi kết luận. Advisor không mô phỏng hoàn hảo mọi concurrency peak.

### 19.3. MEMORY_TARGET_ADVICE

Khi AMM được bật và advisor có dữ liệu:

```sql
SELECT
    memory_size,
    memory_size_factor,
    estd_db_time,
    estd_db_time_factor,
    estd_physical_reads
FROM v$memory_target_advice
ORDER BY memory_size;
```

View có thể không có dữ liệu hữu ích nếu AMM không bật hoặc workload chưa đủ. Không dùng advisor để vượt quá ngân sách RAM host.

### 19.4. Advisor là ước lượng

Advisor:

- Dựa trên workload/interval đã quan sát.
- Có thể thiếu đại diện cho peak concurrency.
- Không tính thay cho toàn bộ memory của OS/agent/instance khác.
- Không biết thay đổi workload tương lai.
- Không đảm bảo response time cải thiện tuyến tính theo memory.

Kết hợp advisor với AWR/ASH nếu được cấp quyền/license, SQL Monitor, wait events và OS metrics.

## 20. Theo dõi memory từ hệ điều hành

### 20.1. Linux

Một số lệnh thường dùng:

```text
free -h
vmstat 1
top
ps -eo pid,ppid,rss,vsz,comm --sort=-rss | head
grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree|HugePages|Hugepagesize' /proc/meminfo
```

Ý nghĩa:

- free -h: tổng quan RAM và swap.
- vmstat: run queue, paging, swap và CPU theo chu kỳ.
- top/ps: process tiêu thụ memory/CPU.
- /proc/meminfo: memory available, huge pages và các trạng thái kernel.

RSS của từng Oracle process có thể bao gồm shared SGA mapping; không cộng RSS một cách máy móc để suy ra PGA tổng.

### 20.2. PSS và shared mappings

Trên Linux, smem hoặc /proc/PID/smaps_rollup có thể cung cấp PSS nếu OS hỗ trợ. PSS chia phần shared memory cho các process cùng map vùng đó. Đây là cách nhìn bổ sung, không thay thế Oracle memory views.

### 20.3. Windows

Trên Windows, dùng Task Manager, Resource Monitor, Performance Monitor và các counter về committed memory, available memory, paging, process working set/private bytes. Phân biệt shared memory/working set và private bytes; cách đo khác Linux nên không áp dụng nguyên xi lệnh hoặc công thức Linux.

### 20.4. Container/cgroup

Nếu Oracle chạy trong container, kiểm tra memory limit thực tế của cgroup, memory.current, memory.max và memory.events (cgroup v2) hoặc các file tương ứng cgroup v1. Host có RAM lớn không có nghĩa container được dùng toàn bộ RAM host.

Phiên bản Oracle, platform certification và cách runtime áp dụng cgroup limit quyết định Oracle nhìn thấy bao nhiêu memory. Đừng chỉ dựa trên lệnh free chạy ở host.

### 20.5. OS metrics phải cùng timestamp

Khi query chậm, thu thập database view và OS metrics trong cùng khoảng thời gian. So sánh một ảnh chụp V$PGASTAT lúc 10:00 với vmstat lúc 14:00 không đủ để giải thích incident lúc 11:00.

## 21. Chẩn đoán sự cố memory

### 21.1. ORA-04031 — unable to allocate shared memory

ORA-04031 thường chỉ ra Oracle không cấp phát được một vùng shared memory cần thiết trong SGA. Có thể liên quan shared pool, large pool hoặc pool/heap cụ thể.

Hướng điều tra:

1. Đọc đầy đủ error text để biết pool/heap và allocation size.
2. Kiểm tra alert log và trace file.
3. Xem V$SGASTAT theo pool/name và V$SGA_DYNAMIC_COMPONENTS.
4. Kiểm tra shared pool pressure, hard parse, cursor churn và allocation pattern.
5. Xem component có minimum quá cao hoặc SGA target quá thấp không.
6. Xem application có tạo SQL text với literal khác nhau liên tục hay không.

Không mặc định chỉ tăng SHARED_POOL_SIZE. ORA-04031 có thể xảy ra ở pool khác hoặc do pattern allocation/fragmentation, cursor management và workload.

### 21.2. ORA-04036 — PGA_AGGREGATE_LIMIT exceeded

ORA-04036 xuất hiện khi tổng PGA vượt PGA_AGGREGATE_LIMIT theo cơ chế Oracle. Một số call/session có thể bị terminate.

Hướng điều tra:

- Kiểm tra V$PGASTAT, đặc biệt total/maximum PGA allocated.
- Xem V$PROCESS và V$PROCESS_MEMORY để tìm process lớn.
- Xem V$SQL_WORKAREA_ACTIVE và V$TEMPSEG_USAGE.
- Xác định parallel query, batch hoặc session chạy nhiều sort/hash.
- Kiểm tra PGA_AGGREGATE_TARGET, PGA_AGGREGATE_LIMIT và host headroom.
- Xem application có mở quá nhiều session hoặc chạy query không giới hạn không.

Không chỉ nâng PGA_AGGREGATE_LIMIT để bỏ lỗi. Nếu host không đủ RAM, nâng limit có thể đẩy vấn đề sang swap/OOM.

### 21.3. ORA-04030 — out of process memory

ORA-04030 cho biết một process không cấp phát được private memory. Nguyên nhân có thể là PGA/process memory quá lớn, process limit, address space, OS memory pressure hoặc allocation bất thường.

Kiểm tra:

- Trace/alert log cho biết process và allocation đang yêu cầu.
- PGA theo process và category.
- Số session/process và parallel workers.
- OS memory, swap, ulimit và cgroup limit.
- Application/PLSQL code có giữ collection/LOB lớn hoặc leak không.

ORA-04030 khác ORA-04036: một lỗi nói về allocation của process; lỗi kia liên quan tổng PGA aggregate limit.

### 21.4. ORA-00845 — MEMORY_TARGET not supported on this system

Trên Linux, kiểm tra /dev/shm mount và dung lượng, cùng MEMORY_TARGET/MEMORY_MAX_TARGET. Nếu yêu cầu HugePages, cân nhắc AMM không phù hợp và chuyển sang ASMM theo kế hoạch.

### 21.5. TEMP tablespace đầy

TEMP full không đồng nghĩa PGA hết memory. Một query có thể spill nhiều dữ liệu ra TEMP vì work area nhỏ hoặc intermediate set lớn. Kiểm tra V$TEMPSEG_USAGE, SQL_ID, operation và TEMP capacity. Tăng TEMP chỉ giải quyết dung lượng tạm; không chắc giải quyết hiệu năng.

### 21.6. OS swapping hoặc OOM

Nếu OS swap liên tục hoặc kernel OOM-kill Oracle process:

1. Thu thập free, vmstat, /proc/meminfo hoặc công cụ tương ứng.
2. Kiểm tra SGA, PGA và các process khác trên host.
3. Kiểm tra cgroup/container memory limit.
4. Kiểm tra HugePages và /dev/shm.
5. Giảm concurrency/parallelism hoặc memory target theo kế hoạch nếu host đang quá tải.
6. Không restart nhiều lần khi nguyên nhân RAM chưa được giải quyết.

### 21.7. Triệu chứng và nguồn dữ liệu

| Triệu chứng | Database evidence | OS evidence |
| --- | --- | --- |
| Shared memory allocation fail | ORA-04031, V$SGASTAT, resize ops | RAM available, shared memory limits |
| PGA aggregate vượt limit | ORA-04036, V$PGASTAT, V$PROCESS | RAM, swap, cgroup |
| Process không cấp phát được | ORA-04030, V$PROCESS_MEMORY | ulimit, process RSS/PSS, kernel log |
| Sort/hash chậm | V$SQL_WORKAREA, V$TEMPSEG_USAGE | I/O latency, TEMP storage |
| AMM startup fail | ORA-00845, memory parameters | /dev/shm size/mount |
| Instance bị OS kill | alert/trace, process exit | kernel OOM log, memory.events |

## 22. Quy trình tuning memory có kiểm soát

### 22.1. Bước 1 — Lấy baseline

Thu thập trong cả giờ bình thường và giờ peak:

- SGA component sizes và resize history.
- PGA target, limit, total/max PGA và over-allocation.
- Work area optimal/one-pass/multi-pass và TEMP usage.
- Session/process count và parallel degree.
- OS MemAvailable, swap in/out, CPU, I/O và cgroup limit.
- Response time và throughput của workload chính.

### 22.2. Bước 2 — Xác định bottleneck

Hỏi vấn đề nằm ở đâu:

- Shared pool allocation/parse?
- Buffer cache physical read?
- PGA work area spill?
- Parallel query concurrency?
- OS swapping/OOM?
- /dev/shm hoặc HugePages?
- Process memory của application/agent?

Không tăng SGA/PGA nếu bottleneck là CPU, storage latency, SQL plan hoặc application concurrency.

### 22.3. Bước 3 — Đặt giả thuyết có thể đo

Ví dụ:

- Tăng PGA target một mức vừa phải sẽ giảm multi-pass sort và TEMP I/O trong batch window.
- Giảm DOP sẽ giảm peak PGA nhưng có thể tăng elapsed time của từng statement.
- Tăng shared pool minimum sẽ giảm allocation pressure trong giờ parse peak.
- Chuyển từ AMM sang ASMM sẽ cho phép dùng HugePages trên Linux, nhưng cần thay đổi OS reservation và restart.

Mỗi giả thuyết phải chỉ ra metric sẽ thay đổi và điều kiện thành công.

### 22.4. Bước 4 — Tính headroom

Trước khi tăng memory target, xác nhận RAM vật lý/VM/container, memory của các instance khác, OS reserve, HugePages reservation, /dev/shm, PGA peak và process overhead. Không dùng RAM total đơn lẻ làm ngân sách.

### 22.5. Bước 5 — Thay đổi nhỏ và có rollback

Chỉ thay một nhóm tham số liên quan trong change window phù hợp. Lưu giá trị cũ, SPFILE/PFILE backup, scope, yêu cầu restart và cách rollback. Không thay đổi hidden parameter.

### 22.6. Bước 6 — Quan sát sau thay đổi

So sánh cùng workload và thời gian:

- Response time/throughput.
- SGA resize và component pressure.
- PGA total/max, cache hit, overalloc.
- TEMP I/O và work area passes.
- OS MemAvailable, swap, page reclaim và OOM events.

Một thay đổi thành công phải cải thiện workload mục tiêu mà không làm host mất headroom hoặc làm workload khác suy giảm không chấp nhận được.

### 22.7. Bước 7 — Giữ hoặc rollback

Nếu metric không cải thiện hoặc OS pressure tăng, rollback về giá trị trước. Nếu cải thiện, tiếp tục theo dõi qua nhiều chu kỳ workload để xác nhận không phải hiệu ứng ngắn hạn.

## 23. Thay đổi tham số và scope

### 23.1. SCOPE

ALTER SYSTEM có thể ghi giá trị vào memory, SPFILE hoặc cả hai:

| Scope | Ý nghĩa |
| --- | --- |
| MEMORY | Có hiệu lực trong instance hiện tại; không tự ghi SPFILE |
| SPFILE | Ghi cấu hình cho lần startup sau; chưa nhất thiết có hiệu lực ngay |
| BOTH | Ghi SPFILE và áp dụng runtime nếu tham số hỗ trợ |

Khả năng áp dụng phụ thuộc tham số và trạng thái instance. Nếu instance dùng PFILE, SCOPE=SPFILE/BOTH không phù hợp.

### 23.2. Tham số dynamic và static

SGA_TARGET, PGA_AGGREGATE_TARGET và MEMORY_TARGET thường có thể điều chỉnh online trong giới hạn được hỗ trợ. SGA_MAX_SIZE và MEMORY_MAX_TARGET thường cần startup/restart để thay đổi. Xác nhận bằng V$PARAMETER.ISSYS_MODIFIABLE và tài liệu release.

### 23.3. Thay đổi ASMM minh họa

Ví dụ thay đổi runtime khi tham số cho phép:

```sql
ALTER SYSTEM SET SGA_TARGET = 8G SCOPE = BOTH;
ALTER SYSTEM SET PGA_AGGREGATE_TARGET = 3G SCOPE = BOTH;
```

Chỉ áp dụng sau khi xác nhận ngân sách host, SGA_MAX_SIZE, các component minimum và PGA peak. Giá trị ở đây chỉ minh họa cú pháp.

### 23.4. Thay đổi static parameter

Ví dụ ghi tham số startup:

```sql
ALTER SYSTEM SET SGA_MAX_SIZE = 10G SCOPE = SPFILE;
```

Thay đổi này thường cần restart để có hiệu lực. Không chạy trong production nếu chưa có change approval, startup plan và rollback.

### 23.5. Chuyển AMM sang ASMM

Việc chuyển chế độ có thể cần thay đổi MEMORY_TARGET/MEMORY_MAX_TARGET, SGA_TARGET/SGA_MAX_SIZE, PGA_AGGREGATE_TARGET, HugePages và OS memory configuration. Thực hiện theo runbook đúng Oracle release/platform; xác định các giá trị SPFILE trước, dự kiến restart, xác minh startup và kiểm tra lại memory allocation.

Không thực hiện một chuỗi ALTER SYSTEM rời rạc trên production chỉ dựa vào ví dụ tài liệu. Thứ tự tham số, giới hạn và yêu cầu restart cần được xác nhận với cấu hình hiện tại.

### 23.6. Ghi lại trước/sau

Lưu kết quả các truy vấn V$PARAMETER/V$SPPARAMETER, V$SGAINFO, V$PGASTAT, OS memory và thời gian thay đổi. Ghi lại SQL_ID/workload bị ảnh hưởng để so sánh khách quan.

## 24. Bài thực hành: quan sát SGA/PGA và advisor

Các câu lệnh dưới đây chủ yếu read-only. Chạy trong schema/instance lab với quyền SELECT phù hợp; không thay đổi memory parameter trên production.

### 24.1. Xem chế độ memory hiện tại

```sql
SHOW PARAMETER memory_target
SHOW PARAMETER memory_max_target
SHOW PARAMETER sga_target
SHOW PARAMETER sga_max_size
SHOW PARAMETER pga_aggregate_target
SHOW PARAMETER pga_aggregate_limit
SHOW PARAMETER workarea_size_policy
SHOW PARAMETER use_large_pages
```

### 24.2. Xem SGA components

```sql
SELECT component,
       current_size / 1024 / 1024 AS current_mb,
       min_size / 1024 / 1024 AS min_mb,
       max_size / 1024 / 1024 AS max_mb
FROM v$sga_dynamic_components
ORDER BY current_size DESC;
```

### 24.3. Xem PGA tổng thể

```sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
```

### 24.4. Xem process có PGA lớn

```sql
SELECT pid,
       spid,
       program,
       ROUND(pga_alloc_mem / 1024 / 1024, 1) AS pga_alloc_mb,
       ROUND(pga_used_mem / 1024 / 1024, 1) AS pga_used_mb,
       ROUND(pga_max_mem / 1024 / 1024, 1) AS pga_max_mb
FROM v$process
ORDER BY pga_alloc_mem DESC;
```

### 24.5. Xem PGA advisor

```sql
SELECT
    ROUND(pga_target_for_estimate / 1024 / 1024) AS target_mb,
    pga_target_factor,
    estd_pga_cache_hit_percentage,
    estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;
```

### 24.6. Xem work area đang spill

```sql
SELECT
    sql_id,
    operation_type,
    actual_mem_used,
    number_passes,
    tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
```

### 24.7. Xem OS memory từ Oracle

```sql
SELECT stat_name, value
FROM v$osstat
WHERE stat_name IN (
    'PHYSICAL_MEMORY_BYTES',
    'FREE_MEMORY_BYTES',
    'NUM_CPUS'
)
ORDER BY stat_name;
```

Tên statistic có thể khác hoặc không được cung cấp trên mọi platform/release. Đối chiếu với OS tools trên host.

## 25. Bài thực hành: quan sát sort và TEMP

### 25.1. Chuẩn bị bảng lab

Nếu có schema mẫu đủ lớn, dùng bảng test riêng. Ví dụ:

```sql
CREATE TABLE lab_memory_sort AS
SELECT level AS id,
       MOD(level, 1000) AS group_id,
       RPAD('X', 100, 'X') AS payload
FROM dual
CONNECT BY level <= 500000;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_MEMORY_SORT'
    );
END;
/
```

Kích thước lab cần phù hợp RAM/TEMP của môi trường; giảm số hàng nếu máy nhỏ.

### 25.2. Chạy sort với runtime statistics

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_memory_sort
ORDER BY payload DESC, id DESC;
```

Ngay sau đó xem actual plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +MEMSTATS'
    )
);
```

MEMSTATS hiển thị memory/temp statistics khi có sẵn trong plan. Quan sát operation sort, memory và TEMP usage. Nếu query nhỏ hoặc PGA rộng, sort có thể optimal và không spill.

### 25.3. Quan sát đồng thời

Mở nhiều session lab chạy sort/hash query cùng lúc rồi theo dõi V$SQL_WORKAREA_ACTIVE, V$PGASTAT và V$TEMPSEG_USAGE. Kết quả cho thấy concurrency có thể làm memory mỗi work area giảm và TEMP spill tăng.

Không cố tình đặt PGA limit cực thấp trên production để tạo ORA-04036. Nếu cần thử limit, dùng instance lab có RAM/TEMP giới hạn và kế hoạch phục hồi.

## 26. Bài thực hành: tính ngân sách memory

### 26.1. Lập bảng host

Điền số liệu thực tế:

| Hạng mục | GB |
| --- | ---: |
| RAM vật lý hoặc container limit | |
| OS/kernel reserve | |
| Agent, backup, ASM, middleware | |
| Instance Oracle khác | |
| Safety headroom cho peak | |
| Ngân sách còn lại cho instance đang sizing | |

### 26.2. Tách ngân sách instance

| Hạng mục | Giá trị dự kiến |
| --- | ---: |
| SGA target | |
| PGA aggregate target | |
| PGA aggregate limit | |
| Process/feature overhead ngoài target dự kiến | |
| Tổng peak dự kiến | |

PGA_AGGREGATE_TARGET là target điều tiết, PGA_AGGREGATE_LIMIT là limit theo Oracle; không cộng hai giá trị như hai vùng memory độc lập. Khi tính peak, dùng limit như một ràng buộc PGA và cộng SGA, process/OS overhead theo mô hình phù hợp.

### 26.3. Kiểm tra HugePages hoặc /dev/shm

Nếu dùng HugePages, tính tổng SGA của mọi instance cần HugePages và xác nhận OS reserve đủ page, memlock và RAM thường còn lại. Nếu dùng AMM trên Linux, xác nhận /dev/shm mount đủ lớn và host còn RAM khả dụng.

### 26.4. Kiểm tra peak concurrency

Ghi lại số session active, PX process, query sort/hash và PGA max trong peak. Nếu sizing chỉ dựa trên average, host có thể thiếu memory đúng lúc batch/reporting chạy đồng thời.

## 27. Nguyên tắc thực hành tốt

1. **Nhìn toàn host.** Tính OS, agent, backup, ASM, các instance khác và headroom trước khi đặt SGA/PGA.
2. **Phân biệt SGA và PGA.** SGA dùng chung; PGA riêng theo process.
3. **Tính UGA đúng kiến trúc.** Dedicated server thường giữ UGA trong PGA; shared server thường giữ UGA trong SGA.
4. **Dùng ASMM có chủ đích.** SGA_TARGET điều chỉnh component SGA; PGA_AGGREGATE_TARGET quản lý PGA riêng.
5. **Dùng AMM khi platform phù hợp.** Kiểm tra /dev/shm và HugePages trước khi bật.
6. **Không dùng AMM nếu cần Linux HugePages.** Cân nhắc ASMM/manual SGA theo hướng dẫn Oracle.
7. **Đặt PGA target theo concurrency.** Không sizing chỉ theo một query chạy đơn lẻ.
8. **Giữ PGA limit hợp lý.** Bảo vệ host nhưng không abort workload hợp lệ.
9. **Theo dõi TEMP spill.** Phân biệt thiếu PGA với SQL tạo intermediate data quá lớn.
10. **Không tối ưu cache hit ratio đơn lẻ.** Xem wait, I/O, CPU và response time.
11. **Dùng advisor như dữ liệu tham khảo.** Đối chiếu workload peak và OS headroom.
12. **Không cộng RSS của mọi Oracle process.** Shared SGA có thể bị đếm lặp.
13. **Tránh sustained swapping.** Swap/OOM có thể phá hiệu năng toàn instance.
14. **Chừa headroom cho OS.** Không cấp toàn bộ RAM cho MEMORY_TARGET/SGA/PGA.
15. **Giới hạn parallelism.** DOP cao làm tăng số process và tổng PGA.
16. **Thay đổi có baseline và rollback.** Ghi giá trị cũ, scope, restart và metric trước/sau.
17. **Không chỉnh hidden parameter tùy tiện.** Theo tài liệu và Oracle Support khi cần.
18. **Kiểm tra sau upgrade/container migration.** OS memory visibility và optimizer/runtime behavior có thể thay đổi.

## 28. Câu hỏi tự kiểm tra

1. SGA và PGA khác nhau về phạm vi chia sẻ như thế nào?
2. Các thành phần chính của SGA có chức năng gì?
3. Vì sao shared pool pressure có thể gây ORA-04031?
4. PGA work area được dùng cho những operation nào?
5. Optimal, one-pass và multi-pass work area khác nhau thế nào?
6. Vì sao TEMP usage tăng không nhất thiết có nghĩa TEMP tablespace sai?
7. UGA nằm ở đâu trong dedicated server và shared server?
8. Manual memory management khác ASMM thế nào?
9. ASMM điều chỉnh component nào và PGA được quản lý bằng tham số nào?
10. AMM khác ASMM ở điểm nào?
11. SGA_TARGET và SGA_MAX_SIZE khác nhau ra sao?
12. PGA_AGGREGATE_TARGET có phải hard limit không?
13. PGA_AGGREGATE_LIMIT bảo vệ điều gì?
14. MEMORY_TARGET và MEMORY_MAX_TARGET khác nhau như thế nào?
15. Vì sao ASMM thường được chọn khi cần Linux HugePages?
16. Vì sao AMM trên Linux cần /dev/shm đủ lớn?
17. ORA-00845 thường liên quan điều kiện nào?
18. HugePages giúp ích gì cho SGA và có áp dụng trực tiếp cho PGA không?
19. Vì sao không cộng RSS của tất cả Oracle process để tính tổng SGA?
20. MemAvailable khác MemFree như thế nào trên Linux?
21. Sustained swapping ảnh hưởng Oracle ra sao?
22. Parallel query làm thay đổi peak PGA như thế nào?
23. V$PGASTAT và V$PROCESS cung cấp góc nhìn khác nhau ra sao?
24. V$SQL_WORKAREA_ACTIVE giúp phát hiện TEMP spill thế nào?
25. Vì sao advisor không thay thế OS memory monitoring?
26. ORA-04030 khác ORA-04036 như thế nào?
27. Khi nào cần xem V$MEMORY_RESIZE_OPS?
28. Cần ghi lại gì trước khi thay đổi memory parameter?

## 29. Mô hình ghi nhớ

```text
HOST RAM
   |
   +-- OS / Kernel / Page cache / Agents / ASM
   +-- Safety headroom
   |
   v
ORACLE INSTANCE
   |
   +-- SGA (shared)
   |     +-- Buffer Cache
   |     +-- Shared Pool
   |     +-- Redo Buffer
   |     +-- Large / Java / Streams Pool
   |
   +-- PGA (private per process)
         +-- Process/session memory
         +-- Sort / Hash work areas
         +-- Untunable allocations
   |
   v
MEMORY MANAGEMENT
   |
   +-- Manual: DBA sizes components/work areas
   +-- ASMM: SGA_TARGET + PGA_AGGREGATE_TARGET
   +-- AMM: MEMORY_TARGET + MEMORY_MAX_TARGET
   |
   v
OS TRADE-OFFS
   |
   +-- HugePages: phù hợp SGA, thường đi với ASMM
   +-- AMM Linux: cần /dev/shm, không dùng HugePages
   +-- PGA concurrency và parallelism
   +-- Swap / OOM / container limits
   |
   v
OBSERVABILITY
   |
   +-- V$SGAINFO / V$SGASTAT / resize views
   +-- V$PGASTAT / V$PROCESS / workarea views
   +-- Advisor + actual workload
   +-- OS metrics cùng timestamp
```

**Điểm cần nhớ:** SGA là bộ nhớ chia sẻ của instance, PGA là bộ nhớ riêng theo process. ASMM điều chỉnh SGA còn PGA được quản lý riêng; AMM điều chỉnh tổng SGA/PGA trong một target. Mọi target phải nằm trong ngân sách RAM host sau khi chừa OS và workload khác. Sizing theo peak concurrency, theo dõi TEMP/OS pressure và đo trước/sau thay đổi quan trọng hơn việc chạy theo một con số memory cố định.
