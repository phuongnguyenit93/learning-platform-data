# Quyền chạy UDF, plugin hoặc tính năng mở rộng

> **Chương:** Bảo mật  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu phân tán *wide-column*, phân quyền CQL theo role và các cơ chế mở rộng có thể chạy mã bên trong tiến trình máy chủ. Bài gồm ví dụ CQL, mô hình rủi ro, quy trình vận hành và một đoạn kiểm tra bằng Cassandra Java Driver 4.x.
>
> **Mục tiêu học tập:** Biết phân biệt **quyền tạo/đổi/xóa/gọi UDF hoặc UDA**, **công tắc cho phép tính năng ở cấp cluster/node**, và **quyền cài đặt/chạy plugin ở cấp máy chủ**. Thiết kế quyền tối thiểu, kiểm tra khả năng lạm dụng tài nguyên, triển khai có phê duyệt, thu hồi quyền và bảo vệ cluster khi có lỗi.

## 1. Bài toán: ứng dụng chỉ cần SELECT, tại sao UDF có thể tạo rủi ro lớn?

Một ứng dụng Java muốn hiển thị điểm đã chuẩn hóa của thiết bị. Thay vì chỉ đọc cột `score`, đội phát triển đề xuất một **User-Defined Function (UDF)** chạy ngay trên Cassandra:

```cql
SELECT device_id, lab.score_plus_one(score) AS adjusted_score
FROM lab.metric_by_id
WHERE device_id = 'device-01';
```

Thoạt nhìn đây là một hàm tính toán nhỏ. Nhưng có những câu hỏi bảo mật khác nhau:

1. Ai được **định nghĩa** hàm bằng `CREATE FUNCTION`?
2. Ai được **gọi** hàm trong câu SELECT?
3. Cluster có **cho phép UDF** ở phiên bản/cấu hình hiện tại không?
4. Nội dung hàm được chạy **ở đâu**, dùng CPU và bộ nhớ của ai?
5. Nếu hàm chậm, lỗi hoặc cố truy cập tài nguyên ngoài phạm vi, ai chịu ảnh hưởng?
6. Nếu một thư viện bên thứ ba được cài vào Cassandra như **plugin/server extension**, quyền CQL có đủ để kiểm soát nó không?

Điểm quan trọng: **mã do người dùng đưa vào để chạy trong database có ranh giới tin cậy khác một câu SELECT thuần túy**. Quản trị quyền dữ liệu không thể thay thế quản trị mã thực thi.

Một service có quyền `SELECT` bảng có thể không được phép gọi một UDF; một role có `EXECUTE` UDF không có nghĩa được phép sửa định nghĩa UDF. Và **không phải mọi plugin đều có resource để `GRANT EXECUTE`**.

## 2. Ba lớp kiểm soát phải có đồng thời

```text
                  ỨNG DỤNG / NGƯỜI DÙNG
                            |
                  CQL qua TLS, authentication
                            |
                            v
              +---------------------------+
              | LỚP 1: CQL AUTHORIZATION  |
              | SELECT / EXECUTE / CREATE |
              | roles, resources, grants  |
              +---------------------------+
                            |
                            v
              +---------------------------+
              | LỚP 2: FEATURE GATE       |
              | UDF có được bật không?    |
              | Runtime/engine hỗ trợ?    |
              +---------------------------+
                            |
                            v
              +---------------------------+
              | LỚP 3: SERVER TRUST       |
              | JVM process / classpath   |
              | plugin package / OS user  |
              | node rollout / sandbox    |
              +---------------------------+
                            |
                            v
              CPU / MEMORY / DISK / NETWORK CỦA NODE
                            |
                            v
                 CQL p99, GC, REPLICA, CL
```

| Lớp | Mục đích | Ví dụ | Không thay thế được |
| --- | --- | --- | --- |
| **Authentication** | Xác nhận danh tính client | Role login, credential, TLS client identity nếu được hỗ trợ | Quyền làm gì sau đăng nhập |
| **Authorization CQL** | Giới hạn thao tác của role trên resource | `SELECT` trên bảng, `EXECUTE` trên một UDF | Chính sách OS cho code đã cài vào JVM |
| **Feature gate** | Cho phép/cấm một loại tính năng ở server | Cấu hình bật/tắt UDF theo release | Phân quyền chi tiết cho từng role |
| **Runtime/security boundary** | Giới hạn các khả năng và tác động của mã chạy | Mô hình Java UDF/runtime, hạn chế API theo bản phát hành | Kiểm thử code, quyền tối thiểu và quản lý nguồn |
| **OS/deployment control** | Ai được sửa JAR/classpath/config/restart | File permissions, CI/CD, package signing, approval | Tự động hạn chế mọi hành vi của plugin khi đã nạp |
| **Observability** | Phát hiện rủi ro và hiệu năng xấu | Audit, JVM/CPU/GC, CQL p99, error rate | Ngăn mọi lỗi ngay từ đầu |

Một role có quyền `EXECUTE` vẫn không thể làm UDF hoạt động nếu **cấp server đã tắt tính năng**. Ngược lại, bật UDF toàn cluster mà không cấu hình authorization và vòng kiểm soát mã sẽ tạo bề mặt tấn công lớn.

## 3. Định nghĩa UDF, UDA và plugin

### UDF — User-Defined Function

UDF là hàm do người dùng định nghĩa trong ngữ cảnh CQL. Hàm có **tên, danh sách kiểu đối số, kiểu trả về và phần thân**, được lưu trong schema metadata và được gọi khi xử lý truy vấn.

Ví dụ khái niệm:

```text
lab.score_plus_one(int) -> int
Input: 41
Output: 42
```

Nếu một query trả nhiều hàng, hàm có thể được đánh giá nhiều lần. **Một UDF chạy nhanh với một hàng chưa chắc an toàn khi dùng trong truy vấn quét một partition lớn**.

### UDA — User-Defined Aggregate

UDA là hàm tổng hợp do người dùng định nghĩa, thường dùng một **state function**, kiểu trạng thái và có thể có **final function** để tích lũy/biến đổi kết quả của nhiều giá trị.

Nếu aggregate chạy trên rất nhiều hàng, trạng thái và phép tính có thể tiêu tốn CPU/memory, làm tăng thời gian đọc. Khả năng tạo/gọi aggregate và quyền trên các hàm phụ trợ cần xác minh theo Cassandra version.

### Plugin/server extension

Từ “plugin” ở đây có thể chỉ các dạng mở rộng khác nhau:

- **Server-side Java extension** được cài vào classpath/đóng gói cùng Cassandra.
- Các lớp tùy biến cho cơ chế xác thực/ủy quyền, tích hợp ngoài hoặc những *extension point* được release hỗ trợ.
- **Custom index** hoặc **trigger** (nếu release/cấu hình có hỗ trợ), có thể tham chiếu mã chạy trong JVM.
- Thành phần tích hợp ngoài Cassandra, ví dụ agent thu metrics hoặc một service truy cập CQL.
- **Client-side plugin** như custom codec/load balancing policy của Java Driver — chạy trong ứng dụng, không phải trong tiến trình Cassandra.

**Không có một lệnh CQL phổ quát kiểu `GRANT EXECUTE ON PLUGIN ...` cho mọi dạng plugin.** Cách cài đặt, cho phép và kiểm soát phụ thuộc từng extension point, phiên bản và chính sách hệ thống.

## 4. Phân biệt “được gọi” với “được cài đặt”

Giả sử nhóm A có một UDF `lab.score_plus_one(int)`, nhóm B cung cấp một JAR cài vào Cassandra.

| Tình huống | Cần kiểm tra quyền nào? | Ai chịu trách nhiệm? |
| --- | --- | --- |
| Service đọc bảng và gọi UDF | `SELECT` bảng **và** `EXECUTE` resource function | Chủ role ứng dụng và quản trị CQL |
| Developer tạo UDF mới | Quyền `CREATE` trên function resource scope, feature gate | Người sở hữu schema/security |
| Developer thay thân hàm | Quyền thay thế/ALTER theo CQL release và process xét duyệt mã | Security reviewer + schema owner |
| Operator triển khai JAR vào classpath | OS/filesystem/CI-CD/deployment admin; chính sách rollout | Platform/SRE |
| Service gọi một custom endpoint bên ngoài Cassandra | Auth/RBAC của endpoint đó | Chủ hệ thống ngoài |
| Java application cài custom codec | Quyền triển khai mã ứng dụng | Chủ ứng dụng, không phải Cassandra CQL role |

Điểm ranh giới: **cấp quyền trong database không tự giới hạn hành vi của một JAR đã được operator tin cậy chạy cùng tiến trình Cassandra**. Phải xem code server-side như một phần của *trusted computing base*.

## 5. Mô hình RBAC trong Cassandra

Cassandra có mô hình **role-based access control** với các khái niệm:

- **Role:** một danh tính có thể mang `LOGIN`, có thể được cấp quyền và có thể được kế thừa qua role khác.
- **Permission:** thao tác như `SELECT`, `MODIFY`, `CREATE`, `ALTER`, `DROP`, `AUTHORIZE`, `EXECUTE` tùy loại resource.
- **Resource:** bảng, keyspace, role hoặc **function/aggregate** theo cú pháp và phiên bản.
- **Authorizer:** thành phần quyết định role có quyền hay không; phải được cấu hình trên server.

**Không phải mọi loại permission đều hợp lệ cho mọi resource.** Ví dụ `SELECT` áp dụng bảng, còn `EXECUTE` áp dụng function/aggregate resource; không được lấy một ví dụ `GRANT` rồi áp tùy tiện lên custom plugin.

### Superuser là ngoại lệ có rủi ro cao

Một superuser/role quản trị rộng có thể bỏ qua nhiều giới hạn thông thường và làm thao tác quản trị cấp cluster. Không cấp superuser cho application chỉ để một câu SELECT gọi được UDF.

Nên tách:

1. `platform_admin`: vận hành node/config/triển khai plugin, truy cập tối thiểu có kiểm toán.
2. `schema_maintainer`: cập nhật schema/định nghĩa function trong keyspace được duyệt.
3. `app_reader`: đọc bảng và gọi **đúng UDF cần thiết**.
4. `security_auditor`: xem cấu hình/quyền/log theo nhiệm vụ, không mặc định sửa dữ liệu.
5. `incident_operator`: thực hiện quy trình khẩn cấp có thời hạn và phê duyệt.

Đây là mô hình vai trò gợi ý, **không phải danh sách role Cassandra tự tạo sẵn**.

## 6. Phạm vi function resource: cấp cho một hàm hay toàn keyspace?

Giả sử keyspace `lab` có hai UDF:

```text
lab.score_plus_one(int)
lab.normalize_label(text)
```

Với CQL authorization có hỗ trợ function resources, các phạm vi thường gồm:

| Resource scope | Ví dụ ý nghĩa | Mức độ rộng |
| --- | --- | --- |
| **Một function signature** | `FUNCTION lab.score_plus_one(int)` | Hẹp nhất cho một UDF |
| **Tất cả functions trong keyspace** | `ALL FUNCTIONS IN KEYSPACE lab` | Bao gồm nhiều UDF/UDA hiện tại và có thể cả sau này |
| **Tất cả functions toàn cluster** | `ALL FUNCTIONS` | Rất rộng; tránh cấp cho application |

**Tên hàm chưa đủ để phân biệt các overload.** Cassandra có thể có các hàm cùng tên với kiểu đối số khác nhau; resource function được định danh bằng **chữ ký tên và danh sách kiểu** theo CQL.

Ví dụ `lab.cast_score(int)` và `lab.cast_score(text)` là hai function resources khác nhau. Cấp `EXECUTE` cho bản `int` không được hiểu mặc định là cấp cho bản `text`.

### Vì sao `ALL FUNCTIONS IN KEYSPACE` có thể quá rộng?

Nếu một ngày nhóm khác thêm hàm tốn CPU hoặc chứa logic nhạy cảm trong cùng keyspace, role có quyền EXECUTE trên phạm vi toàn bộ có thể gọi hàm mới đó mà không cần cấp phép riêng.

**Least privilege:** cấp quyền cho **từng signature cần dùng**; mở rộng scope khi đã có nhu cầu có kiểm soát, không để “cho tiện”.

## 7. Thực hành CQL: UDF trong môi trường thử nghiệm

> **Điều kiện tiên quyết:** Ví dụ chỉ áp dụng trên Cassandra version có hỗ trợ UDF Java **và** được operator cho phép trong một cluster lab cô lập. Nếu UDF bị tắt theo cấu hình hoặc runtime không hỗ trợ cú pháp, **không chỉnh server production để chạy bài tập**. Các role `app_reader` và `udf_maintainer` được giả định đã tồn tại trong một hệ authentication/authorization hoạt động.

### Bước A — Tạo schema dữ liệu thử nghiệm

Giả sử đã có keyspace `lab` được thiết kế replication đúng với số node/DC thực tế:

```cql
CREATE TABLE IF NOT EXISTS lab.metric_by_id (
    device_id text PRIMARY KEY,
    score int,
    updated_at timestamp
);
```

Ghi một hàng:

```cql
INSERT INTO lab.metric_by_id (device_id, score, updated_at)
VALUES ('device-01', 41, '2026-11-21T08:00:00Z');
```

### Bước B — Định nghĩa UDF đơn giản, thuần tính toán

Một người có quyền quản lý function và được duyệt thay đổi trên **lab** có thể tạo hàm:

```cql
CREATE FUNCTION IF NOT EXISTS lab.score_plus_one(x int)
RETURNS NULL ON NULL INPUT
RETURNS int
LANGUAGE java
AS 'return x + 1;';
```

Ý nghĩa:

- `RETURNS NULL ON NULL INPUT`: không đánh giá hàm khi đầu vào null, trả null.
- `RETURNS int`: kiểu kết quả.
- `LANGUAGE java`: thân hàm được xử lý theo khả năng Java UDF của phiên bản.
- `x + 1` chỉ là ví dụ; với `int` có nguy cơ overflow gần giới hạn kiểu số, **không dùng làm logic tài chính hoặc đối soát không có kiểm tra biên**.

Ở một số release, UDF có thể bị vô hiệu hóa mặc định hoặc cách thực thi/giới hạn Java UDF khác. Hãy đọc tài liệu/hướng dẫn tương ứng với release đang chạy và kiểm thử trong lab.

### Bước C — Query với UDF

```cql
SELECT device_id, score,
       lab.score_plus_one(score) AS adjusted_score
FROM lab.metric_by_id
WHERE device_id = 'device-01';
```

Expected trong dữ liệu lab là `device_id=device-01`, `score=41`, `adjusted_score=42`.

UDF được đánh giá phía Cassandra khi thực thi truy vấn, **không phải hàm Java được client tự động tải về chạy**.

### Bước D — Cấp quyền tối thiểu

Ví dụ lệnh thực hiện bởi role quản trị có quyền cấp phép phù hợp:

```cql
GRANT SELECT ON TABLE lab.metric_by_id TO app_reader;

GRANT EXECUTE ON FUNCTION lab.score_plus_one(int)
TO app_reader;
```

Hai quyền tách nhau:

- `SELECT` cho phép đọc các cột mà role có thể truy vấn trên bảng theo mô hình quyền của Cassandra.
- `EXECUTE` cho phép dùng đúng function signature đã cấp.

**Cấp quyền EXECUTE không cấp quyền CREATE/ALTER/DROP function.** Cũng không biến một role thành superuser hay cho phép role thêm JAR vào Cassandra classpath.

### Bước E — Kiểm tra quyền

Người dùng có đủ quyền xem metadata có thể thử:

```cql
LIST ALL PERMISSIONS OF app_reader;
```

Cú pháp `LIST PERMISSIONS`, ý nghĩa quyền kế thừa từ role khác và khả năng xem danh sách phụ thuộc authorizer/release/quyền của người kiểm tra. Kết quả kỳ vọng phải được đối chiếu với **role graph**, không chỉ đọc một dòng grant riêng lẻ.

Có thể thực hiện **negative test** với danh tính bị giới hạn:

1. `app_reader` đọc bảng và gọi `lab.score_plus_one(int)` được.
2. Một role có `SELECT` bảng nhưng **không có EXECUTE tương ứng** bị từ chối gọi function.
3. `app_reader` không được tạo function mới hay sửa định nghĩa khi không có quyền DDL.
4. Sau khi thu hồi EXECUTE, request gọi function phải bị từ chối **sau khi các cache quyền đã hội tụ theo cấu hình**.

### Bước F — Thu hồi quyền

```cql
REVOKE EXECUTE ON FUNCTION lab.score_plus_one(int)
FROM app_reader;
```

Lệnh thu hồi quyền **không xóa function**, không thay table data và không dừng ngay mọi request đã bắt đầu trước đó. Auth/permission caches và phiên đang mở có thể ảnh hưởng thời điểm thấy thay đổi; kiểm tra thực tế theo chính sách cluster.

Nếu chỉ muốn ngừng một application gọi hàm, **không nên DROP FUNCTION đang được hệ khác sử dụng** khi chưa có inventory dependency.

## 8. Quyền tạo, thay thế và xóa UDF/UDA

Tạo mới một UDF thường liên quan quyền `CREATE` trên phạm vi function của keyspace. Ví dụ khái niệm, chỉ cấp khi người vận hành đã xác nhận chính sách tương thích:

```cql
GRANT CREATE ON ALL FUNCTIONS IN KEYSPACE lab
TO udf_maintainer;
```

Một số hành vi như thay thế thân hàm hoặc xóa function có thể yêu cầu `ALTER`/`DROP` trên function resource và những quyền liên quan, theo CQL release. UDA cũng có thể phụ thuộc **quyền EXECUTE trên các state/final functions**, không chỉ quyền CREATE aggregate.

**Không suy ra quyền thay thế chỉ từ quyền tạo ban đầu.** Trước khi triển khai thực tế, xem bảng quyền hỗ trợ của đúng Cassandra version và thử bằng role không phải superuser trên lab.

### Cấp CREATE rộng có nguy cơ gì?

Một role được phép tạo bất kỳ function nào trong keyspace có thể cung cấp thân hàm phức tạp hoặc gây tốn tài nguyên dù chỉ có mục đích nghiệp vụ ban đầu là “viết một hàm xử lý text”.

Quy trình tốt:

- Người viết đề xuất code, người duyệt bảo mật/hiệu năng chấp thuận.
- CI tạo artifact/schema migration có thể kiểm tra, kèm hash và version.
- Một role deployment chuyên biệt thực thi thay đổi tại thời điểm duyệt.
- Role ứng dụng chỉ giữ quyền gọi function đã duyệt.
- Sau rollout, theo dõi query p99, GC, CPU và timeout.

Không cấp `CREATE ON ALL FUNCTIONS` toàn cluster cho người phát triển chỉ để thử nghiệm một hàm.

## 9. Feature gate: có quyền nhưng Cassandra vẫn từ chối chạy UDF

Các phiên bản Cassandra có các công tắc/cấu hình bảo mật điều khiển việc cho phép user-defined functions; ví dụ có release sử dụng tên cấu hình như:

```yaml
# Chỉ minh họa các tên tùy chọn thường gặp; xác minh theo release.
enable_user_defined_functions: false
enable_scripted_user_defined_functions: false
```

**Không copy những dòng này vào cấu hình production hoặc cho rằng hai khóa đều tồn tại trên mọi bản.** Ý nghĩa, mặc định và việc hỗ trợ scripted functions đã thay đổi giữa các release. Có phiên bản hạn chế hoặc không hỗ trợ một số loại UDF/runtime vì lý do bảo mật.

Nếu query báo tính năng bị cấm:

1. Kiểm tra Cassandra version và tài liệu cấu hình tương ứng.
2. Phân biệt **bị tắt ở server** với **thiếu quyền EXECUTE/CREATE**.
3. Kiểm tra auth/authorizer và role đang được client sử dụng.
4. Xác định nhu cầu thực sự: có thể đưa phép tính vào Java application thay vì bật UDF.
5. Chỉ cân nhắc bật tính năng qua quy trình phê duyệt, thử nghiệm và rollout đồng nhất.

**Bật UDF là thay đổi bề mặt rủi ro của cluster**, không phải cách sửa một permission error đơn lẻ.

## 10. Vì sao UDF đặc biệt nhạy cảm với tài nguyên?

CQL có thể áp dụng UDF lên rất nhiều row/cell. Nếu một lần đánh giá tốn 1 ms CPU và query khiến hàm chạy 10.000 lần, chi phí lý thuyết lên tới 10 giây CPU một luồng tương đương, chưa xét overhead.

```text
Một UDF:
  score_plus_one(41) -> 42
  Chi phí nhỏ với 1 row.

Một query khác:
  SELECT udf(big_column) ...
  Trên partition rất lớn, nhiều kết quả.
  UDF có thể được gọi lặp lại rất nhiều lần.
        |
        +--> CPU tăng
        +--> allocation / GC tăng
        +--> coordinator/replica chậm
        +--> pending read và timeout tăng
```

Một body UDF có vòng lặp không giới hạn hoặc cấp phát dữ liệu lớn còn có thể làm mọi request dùng chung tài nguyên bị ảnh hưởng.

### Vì sao `LIMIT 20` không phải biện pháp an toàn đầy đủ?

`LIMIT` giới hạn số row kết quả trong truy vấn CQL, nhưng replica vẫn có thể phải duyệt SSTable và tombstone để tìm các row sống. Nếu hàm được gọi nhiều lần theo cách truy vấn và engine thực thi, chi phí có thể khác kỳ vọng. Không dựa vào `LIMIT` như một sandbox.

Bảo vệ:

- Truy vấn theo **partition key cụ thể**, clustering range được giới hạn.
- Dữ liệu/collection có giới hạn kích thước.
- UDF thuần tính toán, không phụ thuộc I/O ngoài, không vòng lặp/cấp phát không giới hạn.
- Kiểm thử số lần gọi/CPU/memory với phân phối key nóng thật.
- Kiểm soát concurrency và rate limit ở tầng service/gateway.
- Alert theo p95/p99, query timeouts, GC và CPU per node.

**Consistency level `LOCAL_QUORUM` không giới hạn CPU hoặc số lần hàm thực thi.** CL quy định điều kiện phản hồi replica, không phải ngân sách CPU của một UDF.

## 11. UDA: trạng thái tổng hợp là nguồn rủi ro riêng

UDA có thể xử lý nhiều giá trị, duy trì state và gọi final function. Tùy mô hình, state rất lớn hoặc phép tổng hợp không được giới hạn có thể gây áp lực RAM và CPU.

Ví dụ nghiệp vụ “tính median trên tất cả event của một khách hàng” nghe đơn giản nhưng có thể yêu cầu duyệt hàng triệu row, giữ state lớn hoặc chạy nhiều phép toán.

Một kiểm tra thiết kế UDA nên trả lời:

| Câu hỏi | Lý do |
| --- | --- |
| Có cần scan bao nhiêu partition/row? | Dữ liệu lớn gây read amplification và CPU |
| State có thể tăng theo số phần tử không? | Nguy cơ memory exhaustion |
| Aggregate có kết quả xác định và đủ kiểm thử không? | Dễ làm báo cáo nghiệp vụ sai |
| State/final function có bị gọi trên null không? | Ngữ nghĩa cần rõ |
| Ai được CREATE/DROP/EXECUTE UDA và các hàm phụ? | Tránh scope permission quá rộng |
| Có cache/pre-aggregate theo query được không? | Đôi khi phù hợp hơn tính trực tiếp tại query time |

Nếu UDA tốn kém, nên xem xét **bảng tổng hợp theo truy vấn**, xử lý trong stream processing hoặc ứng dụng Java, với cơ chế đồng bộ phù hợp.

Đừng nhầm quyền `EXECUTE` một UDA với quyền được chạy bất kỳ mã bên ngoài nào. Hành vi quyền đối với aggregate và các function phụ trợ phải kiểm tra theo version.

## 12. Server plugin: quyền thực thi nằm ở đâu?

Một plugin được cài như JAR/lớp Java server có thể được nạp và chạy trong cùng tiến trình Cassandra hoặc trong một extension point cụ thể. Khi đó:

- Nó chia sẻ ít nhiều không gian lỗi của JVM server: CPU, heap/native memory, GC, thread và đôi khi các tài nguyên OS theo quyền tiến trình.
- Nó có thể tương tác với storage/messaging/callback nội bộ theo API extension.
- Nó có thể cần triển khai nhất quán trên các node liên quan; phiên bản không đồng nhất gây lỗi runtime.
- Nó có thể thay đổi hành vi của read/write path hoặc thành phần quan sát, tùy loại plugin.

**CQL RBAC không tự sandbox một JAR server-side**. Một plugin do operator cài vào classpath không thể được xem là an toàn chỉ vì role ứng dụng không có `EXECUTE ON FUNCTION`.

### Các lớp kiểm soát plugin

| Giai đoạn | Kiểm soát bắt buộc | Bằng chứng |
| --- | --- | --- |
| Chọn plugin | Nhu cầu nghiệp vụ, nguồn cung cấp, license, maintenance | Hồ sơ phê duyệt |
| Đánh giá bảo mật | Dependency/SBOM, nguồn code và vulnerability scan | Kết quả review phù hợp |
| Kiểm tra tương thích | Cassandra/JDK version, API binary, serialization/schema | Kết quả thử trên cluster tương đương |
| Xác định quyền OS | File ownership, classpath/config access, secret access | Access review |
| Kiểm thử hiệu năng | CPU, GC, off-heap, p99 read/write, compaction/repair | So benchmark trước/sau |
| Rollout | Canary theo node/rack/DC, cửa sổ thay đổi | Kế hoạch thay đổi |
| Vận hành | Log/audit, health checks, alert, rollback | Dashboard/runbook |
| Gỡ bỏ | Dependency, schema, trạng thái dữ liệu sau disable | Kết quả validation |

Một JAR không có lỗi build vẫn có thể làm JVM crash, làm I/O tệ hơn hoặc đổi semantics của hệ. Vì vậy việc duyệt plugin phải tương đương một **thay đổi server code**.

## 13. Custom trigger, index và extension point có thể có CQL DDL riêng

Không nên gom tất cả vào một khái niệm “UDF”.

- **Trigger:** trên một số bản Cassandra, có thể tham chiếu lớp server-side và cần cấu hình cho phép. Mã chạy theo hoạt động DML/callback và có thể ảnh hưởng write latency.
- **Custom index:** có thể dùng implementation server-side; schema index là metadata CQL nhưng mã thực hiện có thể đến từ classpath/JAR.
- **Authenticator/authorizer tùy chỉnh:** tham gia trực tiếp vào ranh giới đăng nhập/cấp quyền. Nếu lỗi, có nguy cơ khiến cluster không thể được quản trị hoặc truy cập bị cấp sai.
- **Custom compaction/extension nội bộ:** khi được hỗ trợ, có thể thay đổi chi phí I/O và độ bền vận hành.
- **Driver codecs/policies:** chạy phía Java client, không phải Cassandra server.

**Mỗi extension point có syntax, quyền DDL, lifecycle và rủi ro khác nhau**. Không sử dụng lệnh `GRANT EXECUTE ON FUNCTION` để suy luận việc tạo custom index hoặc cài một trigger class.

Trong bài này chỉ minh họa các permission chính xác dành cho function; với trigger/index/plugin, hãy tra tài liệu của **đúng release và extension** trước khi thực thi lệnh thật.

## 14. Threat model: một quyền rộng có thể dẫn đến hậu quả gì?

Xét các chủ thể:

1. **Application role** có credential trong service.
2. **Schema/deployment role** có quyền tạo function hoặc index.
3. **Operator/CI runner** có quyền triển khai JVM code và restart node.
4. **Attacker** chiếm được một trong ba loại credential hoặc supply-chain artifact.
5. **Người dùng nghiệp vụ** gửi dữ liệu đầu vào khiến query/UDF tốn tài nguyên.

Bốn nhóm rủi ro:

| Rủi ro | Ví dụ | Biện pháp giảm |
| --- | --- | --- |
| **Privilege escalation** | Role được cấp function scope quá rộng | Least privilege, review role graph, không dùng superuser cho app |
| **Denial of service** | UDF/UDA tạo allocation/CPU lớn, làm node chậm | Giới hạn query, resource testing, monitoring, rate limit |
| **Supply chain** | Plugin/JAR có dependency bị thay đổi | Version pin, verify artifact, SBOM, approval |
| **Data integrity** | Extension ghi hoặc diễn giải dữ liệu sai | Test schema/serialization, canary, audit và rollback |
| **Credential/secret exposure** | Plugin đọc/log secret mà process có quyền thấy | File/service isolation, secret management, không log nhạy cảm |
| **Availability failure** | Auth plugin lỗi làm login/admin không hoạt động | Staged rollout, break-glass plan, rollback đã thử |

Không có một chính sách `GRANT` nào đủ để giải quyết tất cả. Trong mô hình *defense in depth*, phải giảm cả **quyền gọi** lẫn **khả năng đưa code mới vào server**.

## 15. Khi nào nên tránh UDF hoàn toàn?

Một phép tính trong CQL không tự động là tối ưu nhất. Hãy chọn theo nơi nên đặt CPU và ranh giới quyền:

| Lựa chọn | Ưu điểm | Nhược điểm | Thường phù hợp |
| --- | --- | --- | --- |
| **UDF phía Cassandra** | Diễn giải giá trị gần đường đọc; có thể tránh logic lặp ở client | Mã tùy biến chạy trong database JVM, khó cô lập tài nguyên | Phép tính nhỏ, thuần túy, được duyệt và được version hỗ trợ |
| **Java service** | Dễ test, deploy, circuit-breaker, cô lập tài nguyên theo service | Có thể truyền nhiều dữ liệu hơn qua mạng | Business logic thay đổi thường xuyên, nhạy bảo mật |
| **Bảng projection/precomputed** | Read nhanh theo query, không đánh giá hàm trên mọi lần đọc | Tốn write/storage, cần đối soát | API đọc nhiều và logic tính ổn định |
| **Stream processing/analytics** | Có thể scale/tách tải khỏi OLTP Cassandra | Cần pipeline/checkpoint và dữ liệu hội tụ | Tổng hợp lớn, xử lý batch/stream |
| **Built-in CQL function** | Không cần tự đưa body code mới vào cluster | Giới hạn ở chức năng có sẵn | Chuyển đổi nhỏ đã được engine hỗ trợ |

### Ví dụ chuyển logic sang Java

Thay vì `lab.score_plus_one(score)` trong SELECT, có thể đọc giá trị thô:

```cql
SELECT score
FROM lab.metric_by_id
WHERE device_id = 'device-01';
```

Sau đó tính trong service Java. Lựa chọn này thường dễ rollout/rollback hơn, nhất là khi tổ chức không muốn bật UDF trên Cassandra production.

Với dữ liệu nhạy cảm, không mặc định cho phép Java service đọc mọi cột chỉ vì logic chuyển về client. **Quyền SELECT và kiểm soát dữ liệu trên ứng dụng vẫn cần tối thiểu hóa**.

## 16. Java Driver 4.x: kiểm tra UDF với role có quyền

Ví dụ Java 4.x sử dụng `CqlSession` đã được cấu hình **để đăng nhập đúng role thử nghiệm**, chọn local DC và bật TLS theo môi trường. Code này không tạo role hay hardcode password:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class UdfAuthorizationProbe {
    private final CqlSession session;
    private final PreparedStatement byDevice;

    public UdfAuthorizationProbe(CqlSession session) {
        this.session = session;
        this.byDevice = session.prepare(
            "SELECT score, lab.score_plus_one(score) AS adjusted_score " +
            "FROM lab.metric_by_id WHERE device_id = ?"
        );
    }

    public Integer readAdjustedScore(String deviceId) {
        BoundStatement stmt = byDevice.bind(deviceId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        Row row = session.execute(stmt).one();
        if (row == null || row.isNull("adjusted_score")) {
            return null;
        }
        return row.getInt("adjusted_score");
    }
}
```

Các điều kiện cần có:

- Cluster **đã cho phép loại UDF tương ứng** và schema đã chứa `lab.score_plus_one(int)`.
- Role đăng nhập có `SELECT` bảng và `EXECUTE` đúng function signature.
- RF/datacenter phù hợp với `LOCAL_QUORUM`; mỗi môi trường cần local DC của driver đúng.
- Không giả định `prepare` thành công chứng minh quyền đủ; phải kiểm tra **execution** và cả negative test.
- `setIdempotent(true)` hợp lý cho SELECT thuần túy; **không tự bật speculative execution**.

### Không nuốt lỗi authorization

Trong hệ thống thực, phân loại:

- **Authentication failure:** credential hoặc cơ chế login bị từ chối.
- **Authorization failure:** role đã đăng nhập nhưng không có quyền resource.
- **Feature disabled/invalid function:** server không cho phép UDF hoặc function không tồn tại/không tương thích.
- **Execution error:** body function ném lỗi hoặc dùng tài nguyên quá mức.
- **Timeout:** coordinator/replica/driver không đáp ứng kịp, có thể do tải chứ không phải thiếu permission.

Đừng retry liên tục một lỗi permission không thể tự hồi phục. Việc spam retry có thể làm log và tài nguyên cluster quá tải.

## 17. Kiểm thử security: phải có cả positive và negative test

### Ma trận thử nghiệm đề xuất

| Actor/role | `SELECT lab.metric_by_id` | `EXECUTE lab.score_plus_one(int)` | CREATE UDF | Kỳ vọng |
| --- | --- | --- | --- | --- |
| `app_reader` | Có | Có | Không | SELECT có UDF thành công |
| `read_only_without_udf` | Có | Không | Không | SELECT thường được; gọi UDF bị từ chối |
| `udf_maintainer` | Theo nhiệm vụ | Chỉ khi cần | Có trong keyspace lab | Được deploy theo phạm vi |
| `unrelated_service` | Không | Không | Không | Bị từ chối đọc/call |
| Superuser thử nghiệm | Quyền cao | Quyền cao | Quyền cao | Chỉ dùng để kiểm tra setup, không làm service role |

Cần tạo/dùng các role trong **cluster lab có authentication+authorization đúng**, không test bằng superuser rồi kết luận RBAC hiệu lực.

### Thử các ranh giới khác

1. **Feature gate off:** function không chạy kể cả khi role có EXECUTE; kiểm tra cách báo lỗi.
2. **Grant một signature:** role không tự được gọi overload khác.
3. **Revoke:** role mất quyền sau cache convergence, các service khác giữ quyền theo kế hoạch.
4. **DROP/replace attempt:** role chỉ có EXECUTE không thể thay body hoặc xóa function.
5. **Oversized input:** UDF xử lý null, empty, biên dữ liệu, overflow theo quy tắc.
6. **Load test:** tăng QPS/rows; đảm bảo CPU/GC/p99 nằm trong SLO.
7. **Node failure/rollout:** cluster vẫn phục vụ khi một node không có plugin hoặc đang lỗi — kết quả tùy extension, nên thử trên lab.
8. **Audit/trace:** có thể truy nguyên role/DDL/authz error mà không lộ dữ liệu nhạy cảm.

Không thử body có hành vi nguy hiểm hoặc cố vượt sandbox trên production để “kiểm chứng”. Đánh giá mã chạy trong môi trường cách ly, có đội bảo mật chịu trách nhiệm.

## 18. Auth cache, role inheritance và độ trễ khi thu hồi

Cassandra có thể dùng cache cho role, authentication và permission data theo phiên bản/cấu hình. Vì vậy:

- Một `GRANT` hoặc `REVOKE` có thể không thấy hiệu lực đồng thời trên mọi node ngay tức thì.
- Client đang mở session có thể vẫn có kết nối; hiệu lực của mỗi request tùy cách server kiểm tra quyền và cache.
- Role có thể nhận EXECUTE **gián tiếp** qua role được grant.
- Việc revoke một grant trực tiếp có thể **không đủ** nếu một role cha còn cấp cùng quyền rộng hơn.

### Cách xác nhận thu hồi

1. Inventory role graph và quyền trên function.
2. Revoke từ những resource scopes cần thiết.
3. Kiểm tra metadata permissions theo API/CQL được release hỗ trợ.
4. Từ role bị hạn chế, chạy query **thực** để chứng minh bị từ chối.
5. Kiểm tra trên nhiều coordinator nếu cluster có nhiều node/DC và auth caches.
6. Đảm bảo không có credential/service account thay thế vẫn được cấp cùng quyền ngoài dự kiến.

**Không dùng restart toàn cluster để “ép revoke nhanh”** khi chưa hiểu cơ chế và tác động availability. Nếu cần khóa khẩn cấp, theo runbook credential rotation, disable role, isolate traffic hoặc các công cụ quản trị được hệ thống hỗ trợ.

## 19. Audit và quan sát: gọi hàm có đang làm node chậm?

Mục đích của audit là biết **ai** tạo/đổi/gọi các tính năng rủi ro và **khi nào**. Mục đích của monitoring là phát hiện **tác động tài nguyên**.

### Nhật ký sự kiện cần có

- Ai đề xuất, duyệt và triển khai function/plugin; phiên bản, hash, thời điểm.
- Grant/revoke/role changes, thất bại authentication/authorization.
- Schema DDL với function/aggregate/index/trigger theo khả năng audit của release.
- Error và timeout liên quan truy vấn gọi function.
- Sự kiện rollout/rollback plugin, restart node, thay classpath/config.

**Không được mặc định hệ thống audit Cassandra ghi từng lần thực thi UDF**, vì loại sự kiện, cấu hình audit và khả năng lưu log thay đổi giữa các release. Nếu cần biết call count theo hàm, thiết kế telemetry ở tầng application/driver hoặc cơ chế quan sát thích hợp, bảo đảm không tạo cardinality quá lớn.

### Metrics cần theo dõi

| Chỉ số | Tại sao quan trọng? |
| --- | --- |
| CQL read/write p95/p99 và timeout | SLO ứng dụng có bị tác động? |
| Request rate theo query shape sử dụng UDF | Hàm có bị gọi trong đường truy vấn nóng? |
| CPU process/node và container throttling | Code hoặc UDA có tranh CPU? |
| JVM heap/GC pause, native memory/RSS | Body/UDA/plugin có gây allocation? |
| `nodetool tpstats` pending/dropped | Stage có bị dồn việc? |
| Disk read/write latency và compaction | Query/UDF trên partition lớn có làm read amplification tệ? |
| Crash/restart/OOM | Plugin ảnh hưởng availability? |
| Permission-denied rate | Có sai quyền hoặc attempt đáng ngờ? |
| Deployed version/hash theo node | Có lệch plugin giữa replica/DC? |

**Một metric tăng không tự chứng minh do UDF.** Hãy so thời gian deploy, query profile, GC logs, network/compaction/repair và workload tương đương trước khi rollback.

## 20. Liên hệ với consistency level và kiến trúc nhiều datacenter

Cassandra chọn replica theo partition key, token và RF; coordinator phản hồi khi đủ consistency level. UDF chạy trong phần xử lý truy vấn phía server và có thể làm tăng thời gian thực thi, nhưng **không thay đổi công thức quorum**.

Với RF=3 ở một DC:

- `LOCAL_ONE` cần một replica local phản hồi.
- `LOCAL_QUORUM` cần hai replica của DC coordinator phản hồi.
- Một replica chậm do UDF/plugin có thể kéo dài read latency hoặc gây timeout tùy request path.
- Trong multi-DC, `QUORUM` toàn cục có thể cần ACK từ DC xa; plugin/extension rollout không đều giữa DC làm việc chẩn đoán khó hơn.

**Đừng coi `LOCAL_QUORUM` là sandbox bảo mật**. Nó là mức nhất quán của request, không giới hạn những gì code server-side có thể sử dụng.

### Bảo vệ đường ghi

Một server-side extension gắn vào đường mutation (nếu cơ chế hỗ trợ) có thể ảnh hưởng commit log, memtable, write path và replication latency.

Khi một plugin làm write timeout, kết quả ghi có thể **không xác định** ở góc nhìn client: một số replica đã áp dụng mutation. Retry phải xét idempotency, timestamp, LWT và hậu quả nghiệp vụ.

Cần quan sát cả **đường đọc lẫn đường ghi** và đánh giá khả năng lỗi ở một replica ảnh hưởng quorum của cả ứng dụng.

## 21. Tương thích triển khai theo phiên bản

Plugin hoặc UDF chạy trong Cassandra có nhiều ràng buộc version-specific:

| Phạm vi | Điều cần xác minh |
| --- | --- |
| Cassandra release | CQL function syntax, enablement flags, RBAC function resources |
| JDK/runtime | API Java được hỗ trợ, sandbox/giới hạn thực thi |
| Plugin binary | Tương thích ABI/API với Cassandra và dependency |
| Schema | Function signature, UDA state/final functions, index/trigger definitions |
| Cluster mixed-version | Mọi node có xử lý request đã nhận version phù hợp chưa? |
| Rolling restart | Có cần restart để nạp JAR hoặc đổi cấu hình không? |
| Rollback | Có thể phục hồi artifact và schema mà không phá data format không? |
| Observability | Audit/metrics/reporting có đủ để xác nhận an toàn không? |

Không khẳng định một tên flag, một lớp plugin hay một lệnh grant chạy giống nhau trên Cassandra 3.x, 4.x, 5.x hoặc các sản phẩm tương thích CQL. **Thử lại trên môi trường cùng phiên bản/cấu hình** trước mọi triển khai.

## 22. Quy trình phê duyệt và rollout UDF/plugin

### Giai đoạn A — Triage yêu cầu

1. Ghi trường hợp sử dụng và query nào thực sự cần extension.
2. Hỏi có thể dùng built-in CQL function, Java service hay bảng projection thay thế không.
3. Phân loại UDF/UDA/trigger/index/server plugin/client codec chính xác.
4. Xác định dữ liệu truy cập, hành vi mã, nguồn dependency và quyền tối thiểu.
5. Xác minh feature gate và khả năng tương thích phiên bản.

### Giai đoạn B — Review và test

6. Tách người viết code và người phê duyệt quyền chạy/deploy.
7. Review code, dependency, tính thuần túy/idempotent và xử lý đầu vào biên.
8. Kiểm tra không có I/O ngoài/side effect không được phép theo khả năng runtime.
9. Dựng negative tests cho quyền `SELECT`/`EXECUTE`/`CREATE`/`DROP`.
10. Benchmark CPU, memory, GC, p99 và failure scenarios trên lab có dữ liệu đại diện.
11. Định nghĩa rollback an toàn, bao gồm dependency của query/index/aggregate.

### Giai đoạn C — Triển khai

12. Ghi change ticket, artifact hash, scope role/resource và thời gian.
13. Triển khai canary theo node/rack/DC nếu plugin yêu cầu.
14. Đồng bộ schema và quyền; chỉ cấp EXECUTE tới roles thực sự cần.
15. Canary application qua Java Driver với local DC, RF, CL như production.
16. Theo dõi p95/p99, timeout, GC, CPU, disk và permission errors.

### Giai đoạn D — Hậu kiểm

17. Kiểm tra plugin version đồng nhất trên các node liên quan.
18. Xác nhận audit và khả năng truy hồi thay đổi.
19. Xóa quyền tạm hoặc deployment credential khi hết nhu cầu.
20. Đo lại SLO sau một chu kỳ đủ dài có compaction/repair/load thật.
21. Lưu runbook rollback và bằng chứng security review.

Không gọi canary thành công chỉ vì query trên một node trả 42. Phải kiểm chứng **quyền, tính đúng đắn, tác động hiệu năng và tính đồng nhất triển khai**.

## 23. Runbook khi UDF/plugin gây lỗi hoặc có dấu hiệu bị lạm dụng

### A — Lỗi "not authorized" khi gọi UDF

**Dấu hiệu:** application đọc bảng thường được nhưng SELECT có hàm bị từ chối.

**Kiểm tra:** role thực đang login, `SELECT` bảng, `EXECUTE` đúng function signature, role inheritance/permissions cache.

**Cách xử lý:** cấp quyền tối thiểu sau phê duyệt hoặc sửa query không dùng UDF. Không đổi service thành superuser chỉ để hết lỗi.

### B — Role có EXECUTE nhưng server từ chối function

**Dấu hiệu:** báo feature disabled, không hỗ trợ function/runtime hoặc function chưa tồn tại.

**Kiểm tra:** Cassandra version, feature flags, schema/function signature và cluster mixed-version.

**Cách xử lý:** khắc phục deployment/config theo thay đổi có kiểm soát; có thể chuyển phép tính sang Java application. Không bật UDF production không qua review.

### C — Sau rollout, p99 và GC tăng

**Dấu hiệu:** read p99 tăng, CPU/GC allocation lớn, pending read/dropped message tăng.

**Kiểm tra:** tỷ lệ query gọi UDF, số row per query, hot partitions, GC/CPU timeline và plugin rollout.

**Cách xử lý:** hạn chế traffic hoặc rollback theo runbook, đưa tính toán ra service nếu thích hợp. Không chỉ nâng read timeout.

### D — Plugin không có trên một số node

**Dấu hiệu:** request qua một số replica/coordinator thành công, node khác báo class not found hoặc lỗi khởi tạo.

**Kiểm tra:** artifact checksum, classpath, restart status, compatibility từng node và topology.

**Cách xử lý:** dừng mở rộng rollout, đưa cluster về trạng thái version thống nhất theo kế hoạch; không sửa classpath từng node tùy hứng ngoài change control.

### E — Mất quyền quản trị vì custom authenticator/authorizer

**Dấu hiệu:** operator và application đều không đăng nhập/cấp quyền được sau đổi plugin.

**Kiểm tra:** log deployment/config, role backend và cơ chế fail-safe đã được thử trên lab.

**Cách xử lý:** kích hoạt break-glass/rollback theo quy trình được duyệt; bảo vệ credential và giữ bằng chứng. Đây là thay đổi rủi ro cao hơn một UDF đơn giản.

### F — Phát hiện quyền EXECUTE quá rộng

**Dấu hiệu:** role ứng dụng có `EXECUTE ON ALL FUNCTIONS` hoặc được thừa kế scope rộng.

**Kiểm tra:** role graph và danh sách callers/functions thực tế; xem có ứng dụng khác phụ thuộc không.

**Cách xử lý:** lập inventory, cấp quyền từng signature thay thế, thử traffic, rồi revoke scope rộng; kiểm tra cache convergence và các role khác.

### G — Một UDA tiêu tốn bộ nhớ khi query quét nhiều hàng

**Dấu hiệu:** query aggregate có p99 cao, heap/native memory tăng, GC/OOM.

**Kiểm tra:** state size, partition size, fan-out, số row và giai đoạn processing.

**Cách xử lý:** ngừng/giới hạn query nguy cơ, chuyển sang pre-aggregation hoặc xử lý bên ngoài; không tăng heap không giới hạn.

## 24. Mẫu bảng quyền cho môi trường production

| Actor | Bảng cần đọc | Function EXECUTE | Function DDL | OS/plugin deployment |
| --- | --- | --- | --- | --- |
| API service | Chỉ bảng API cần | Chỉ signature được duyệt | Không | Không |
| Batch analytics | Những bảng đã duyệt | Hàm riêng nếu cần | Không | Không |
| Schema CI/CD | Theo migration | Có điều kiện | CREATE/replace/drop theo keyspace được giao | Không mặc định |
| Security team | Metadata/audit theo policy | Không cần để đọc audit | Quản lý grant/revoke được phê duyệt | Không mặc định |
| Platform operator | Khi cần vận hành | Không mặc định | Không mặc định | Có, qua pipeline phê duyệt |
| Emergency admin | Theo break-glass | Theo incident | Theo incident | Theo incident, có hết hạn |

Nguyên tắc:

- **Separation of duties:** người duyệt code, cấp quyền và triển khai không nhất thiết là một tài khoản.
- **Time-bounded privileges:** quyền DDL/deployment tạm được thu hồi sau khi hoàn tất.
- **No secrets in CQL/scripts:** mật khẩu và token lưu trong secret manager/CI protected variables.
- **Audit mọi thay đổi đặc quyền** và kiểm tra định kỳ scope role.
- **Giảm blast radius:** keyspace, table, function signature, node/DC rollout và application rate limits.
- **Rehearsed rollback:** không đợi production lỗi mới tìm cách tháo plugin.

## 25. Sai lầm thường gặp

**“Đã có SELECT trên bảng thì mặc nhiên được gọi mọi UDF.”** Không đúng khi function authorization được bật và enforce theo release. Cần kiểm tra `EXECUTE` trên function resource.

**“EXECUTE trên một function cho phép sửa code của function đó.”** Sai. Gọi và quản lý định nghĩa là những quyền khác nhau.

**“Bật UDF một lần là mọi role có thể dùng không kiểm soát.”** Cần xét authorizer và RBAC thực tế; bật tính năng và cấp quyền là hai lớp riêng.

**“Plugin có thể bị chặn bằng `REVOKE EXECUTE ON FUNCTION`.”** Không có bảo đảm. Java server plugin chạy theo quyền triển khai và runtime của extension, không nhất thiết là CQL function.

**“Nếu UDF viết Java thì chạy trong Java Driver.”** Sai. CQL UDF được thực thi phía Cassandra khi xử lý query; Java Driver chỉ gửi request và nhận kết quả.

**“Một function không có I/O thì không ảnh hưởng cluster.”** Sai. CPU, memory allocation và lỗi khi xử lý nhiều hàng vẫn có thể làm p99 tăng.

**“UDF đơn giản được gọi trên hàng triệu row vẫn rẻ.”** Không chắc. Chi phí mỗi row nhân với số lần đánh giá, cộng read amplification.

**“LOCAL_QUORUM bảo đảm UDF không ảnh hưởng các node khác.”** Sai. CL không phải chính sách resource isolation.

**“Một quyền trên `ALL FUNCTIONS IN KEYSPACE` tương đương một function.”** Sai. Scope rộng có thể ảnh hưởng các hàm mới phát sinh trong tương lai.

**“Revoke quyền là mọi session ngay lập tức dừng chạy.”** Không được giả định; cần tính cache, request in-flight và role inheritance.

**“Superuser dễ dùng hơn nên cho service account superuser.”** Đây là anti-pattern nghiêm trọng, làm mất giới hạn blast radius khi credential lộ.

**“Có thể triển khai JAR mới lên một replica rồi coi cluster đã hỗ trợ plugin.”** Sai. Tương thích/rollout phải được đánh giá trên topology và request path.

**“CQL permission thay thế được OS file permission cho classpath.”** Sai. Đây là hai ranh giới bảo mật khác nhau.

**“Gọi query thành công đồng nghĩa plugin an toàn.”** Sai. Còn rủi ro supply chain, side effect, memory/CPU, mixed-version và dữ liệu đúng.

**“Bỏ hết audit để giảm CPU khi UDF chậm.”** Không phải cách giải quyết chính; cần chẩn đoán chi phí và giữ bằng chứng bảo mật phù hợp.

## 26. Câu hỏi và bài tập

1. Phân biệt authentication, authorization và feature gate trong trường hợp một role muốn gọi `lab.score_plus_one(int)`.
2. Vì sao quyền `SELECT` bảng và `EXECUTE` function phải được kiểm tra riêng?
3. Vai trò của function signature khi có hai overload `lab.f(int)` và `lab.f(text)` là gì?
4. So sánh nguy cơ cấp `EXECUTE` trên một signature với `ALL FUNCTIONS IN KEYSPACE`.
5. Khi muốn sửa thân UDF, nên kiểm tra các quyền/quy trình nào ngoài EXECUTE?
6. Vì sao cấp superuser cho service Java để gọi UDF là vi phạm least privilege?
7. Một UDF rất nhanh với một row nhưng làm p99 tăng trên partition có 5 triệu row. Phân tích nguyên nhân.
8. Tại sao một UDA có state tăng theo số phần tử có nguy cơ OOM?
9. Một plugin JAR được cài trong JVM Cassandra nhưng role app không có EXECUTE UDF. Plugin có mặc nhiên bị vô hiệu hóa không? Vì sao?
10. Phân biệt custom codec trong Java Driver với server-side plugin.
11. Nếu cluster tắt UDF ở server, role có EXECUTE có chạy được không?
12. Tại sao không nên tự bật `enable_user_defined_functions` trên production chỉ để thử một function?
13. Một role mất quyền trực tiếp nhưng vẫn gọi UDF được; cần điều tra role inheritance/cache thế nào?
14. Một UDF đã bị revoke nhưng request cũ vẫn còn; điều này có thể đến từ đâu?
15. Hãy lập bảng 3 role: `app_reader`, `udf_maintainer` và `platform_operator`, cấp quyền tối thiểu cho từng vai trò.
16. Làm thế nào để thử một role được phép đọc bảng nhưng bị từ chối gọi UDF mà không dùng superuser?
17. Một plugin mới làm `tpstats` pending/dropped tăng. Những metrics nào giúp quy nguyên nhân?
18. Trong cụm RF=3 hai DC, UDF/plugin lỗi tại một node có thể ảnh hưởng `LOCAL_QUORUM` như thế nào?
19. Vì sao không được coi một truy vấn thành công trên một node là bằng chứng JAR/plugin đã triển khai đầy đủ?
20. Khi custom authorizer lỗi gây mất đăng nhập, runbook break-glass phải được chuẩn bị thế nào?
21. Lập danh sách các bằng chứng cần lưu: artifact hash, security review, grant/revoke, benchmark, canary và rollback.
22. Nêu trường hợp chuyển logic UDF về Java service hoặc bảng precomputed tốt hơn.
23. Nếu một plugin có dependency CVE, vì sao scan SBOM và version pin lại cần thiết dù CQL role chỉ có SELECT?
24. Giải thích khác biệt giữa quyền thực thi CQL và quyền OS/JVM trong mô hình defense in depth.
25. Thiết kế một negative test để xác nhận role app không thể tạo, thay thế hoặc xóa function khác.

## 27. Sơ đồ quyết định

```text
CÓ YÊU CẦU TÍNH NĂNG MỞ RỘNG TRÊN CASSANDRA
                         |
                         v
          Có thể giải quyết bằng built-in CQL,
          Java service hoặc bảng projection?
                  |                   |
                 Có                  Không
                  |                   |
          Ưu tiên giải pháp             v
          ít đặc quyền hơn       Đây là UDF/UDA hay plugin?
                                        |
                       +----------------+----------------+
                       |                                 |
                     UDF/UDA                         Server plugin
                       |                                 |
             Kiểm tra feature gate              Review artifact, OS,
             + version + CQL RBAC                classpath, rollout
                       |                                 |
             GRANT đúng signature                Kiểm soát CI/CD
             + role cần thiết                     và deployment admin
                       |                                 |
                       +----------------+----------------+
                                        |
                               Lab security + load test
                                        |
                              Canary/metrics/rollback
                                        |
                           Giám sát p99, CPU, GC, errors
                                        |
                              Audit và review định kỳ
```

**Ghi nhớ:** Quyền chạy UDF là **quyền CQL trên function resource**, nhưng khả năng UDF hoạt động còn phụ thuộc **công tắc tính năng và runtime của Cassandra**. Plugin/server extension là **thay đổi mã trong ranh giới tin cậy của máy chủ**, không thể kiểm soát chỉ bằng `GRANT EXECUTE`. Bảo vệ cluster cần **least privilege theo signature, tách người tạo và người gọi, kiểm soát OS/classpath, review code/dependency, đo hiệu năng p99/GC/CPU và rollback có kiểm chứng**. Đặc biệt, không đánh đổi an toàn của toàn bộ replica để tiết kiệm một phép tính có thể thực hiện tại Java application.
