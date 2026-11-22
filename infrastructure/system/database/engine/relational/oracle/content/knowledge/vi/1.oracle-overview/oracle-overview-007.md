# Vai trò và ranh giới công việc của lập trình viên, DBA và người vận hành trong Oracle Database

Một hệ thống sử dụng **Oracle Database** chỉ hoạt động ổn định khi ba nhóm phối hợp: **lập trình viên (developer)** xây dựng cách ứng dụng sử dụng dữ liệu; **quản trị cơ sở dữ liệu (Database Administrator – DBA)** bảo đảm nền tảng Oracle an toàn, tin cậy và có khả năng phục hồi; **người vận hành (operations/SRE/platform engineer)** triển khai, quan sát và duy trì dịch vụ trong môi trường thực tế. Cả ba có thể cùng làm việc với SQL, log và cảnh báo, nhưng **mục tiêu, quyền hạn và trách nhiệm cuối cùng** của họ khác nhau.

Bài học này phân định vai trò trong bối cảnh ứng dụng kết nối Oracle Database, tập trung vào những điểm dễ giao thoa: thiết kế schema, cấp quyền, thay đổi cấu trúc dữ liệu, tối ưu truy vấn, triển khai, sao lưu/khôi phục và xử lý sự cố. Tên chức danh có thể thay đổi theo tổ chức; việc ai được phép thực hiện thao tác cụ thể còn phụ thuộc vào quy trình, quyền truy cập và mô hình vận hành đã được phê duyệt.

## 1. Nhìn hệ thống Oracle theo các lớp trách nhiệm

Trong một ứng dụng doanh nghiệp, yêu cầu nghiệp vụ đi qua nhiều lớp trước khi dữ liệu được lưu bền vững:

```text
Người dùng / hệ thống gọi API
              |
              v
Ứng dụng (Java, Spring Boot, JDBC, ORM, ...)
  - Quy tắc nghiệp vụ, giao dịch, câu SQL
  - Connection pool, retry, xử lý lỗi
              |
              v
Kết nối Oracle (listener / service / session)
              |
              v
Oracle Database
  - Schema, bảng, chỉ mục, constraint, PL/SQL
  - Optimizer, transaction, redo, undo, bộ nhớ
  - Datafile, tablespace, backup, recovery
              |
              v
Hạ tầng và vận hành dịch vụ
  - Máy chủ / cloud, lưu trữ, mạng, giám sát
  - Triển khai, cảnh báo, ứng phó sự cố
```

Sơ đồ mô tả các lớp kỹ thuật, không phải ba vùng cô lập. Chẳng hạn, một truy vấn chậm có thể bắt nguồn từ câu SQL của ứng dụng, thống kê của optimizer, tài nguyên database hoặc kết nối mạng. Người giải quyết sự cố phải dựa trên bằng chứng thay vì suy đoán theo chức danh.

Một số khái niệm Oracle cần phân biệt trước khi phân công:

| Khái niệm | Ý nghĩa trong việc phân định công việc |
|---|---|
| **Database / instance** | Database lưu các file dữ liệu; instance cung cấp bộ nhớ và tiến trình để truy cập dữ liệu. DBA thường quản trị cấu hình và sức khỏe Oracle ở cấp này. |
| **CDB / PDB** | Ở kiến trúc multitenant, một container database (CDB) có thể chứa nhiều pluggable database (PDB). Ứng dụng thường kết nối tới service của PDB được cấp, không quản trị CDB. |
| **Schema / database user** | Schema chứa đối tượng như bảng, view, sequence và package, gắn với một database user. Developer thiết kế đối tượng nghiệp vụ; DBA quản lý cách cấp quyền và ranh giới truy cập theo chính sách. |
| **Service / session / connection** | Ứng dụng đi qua service để tạo session; pool duy trì và tái sử dụng connection. Cấu hình cả phía ứng dụng lẫn phía Oracle đều ảnh hưởng tới độ ổn định. |
| **Tablespace / datafile** | Không gian lưu trữ logic và các file vật lý của Oracle. Thiết kế bảng có thể làm tăng dung lượng; việc hoạch định và mở rộng không gian thường do DBA phối hợp với vận hành. |

> **Lưu ý về thuật ngữ:** *DBA* có thể chỉ chức danh quản trị viên hoặc một role trong Oracle. *SYSDBA* là quyền quản trị đặc biệt có phạm vi rất rộng. Một lập trình viên có thể là người sở hữu schema ứng dụng mà hoàn toàn không cần quyền `DBA` hay `SYSDBA`.

## 2. Lập trình viên: sở hữu hành vi dữ liệu của ứng dụng

Lập trình viên chịu trách nhiệm giải thích **ứng dụng cần lưu gì, truy vấn gì và bảo đảm quy tắc nghiệp vụ ra sao**. Những quyết định này ảnh hưởng trực tiếp đến hiệu năng và tính đúng đắn của hệ thống, kể cả khi DBA là người duyệt và thực thi thay đổi trên production.

### 2.1. Công việc điển hình

- **Mô hình hóa dữ liệu:** đề xuất bảng, cột, kiểu dữ liệu, khóa chính/ngoại, ràng buộc `NOT NULL`, `UNIQUE`, `CHECK`; giải thích quan hệ và vòng đời dữ liệu theo nghiệp vụ.
- **Viết mã truy cập dữ liệu:** SQL, JDBC, JPA/Hibernate, PL/SQL khi cần; sử dụng bind variable/parameterized query, xử lý `NULL`, phân trang, sắp xếp và ánh xạ kiểu dữ liệu đúng ngữ nghĩa.
- **Thiết kế ranh giới giao dịch:** quyết định đơn vị công việc cần `COMMIT` hoặc `ROLLBACK`, giới hạn thời gian giữ khóa, xử lý cạnh tranh, idempotency, trường hợp lỗi giữa giao dịch.
- **Chuẩn bị thay đổi schema:** cung cấp migration có phiên bản, tính tương thích với mã cũ/mới, kế hoạch chuyển đổi/backfill dữ liệu, đánh giá khóa và lượng dữ liệu có thể bị quét.
- **Tối ưu truy vấn ở mức ứng dụng:** xem execution plan, tránh truy vấn lặp N+1, lọc dữ liệu đúng, đề xuất chỉ mục dựa trên workload đo được và kiểm tra hiệu quả sau thay đổi.
- **Bảo vệ dữ liệu từ ứng dụng:** không ghép trực tiếp đầu vào người dùng vào SQL, hạn chế log dữ liệu nhạy cảm, dùng tài khoản runtime với quyền vừa đủ, quản lý secret qua cơ chế được cấp.
- **Cung cấp khả năng quan sát:** ghi lại mã lỗi Oracle, thời lượng truy vấn, request/trace ID, pool metrics và phiên bản release để người khác có thể khoanh vùng nguyên nhân.

Ví dụ, developer của hệ thống bán hàng đề xuất cấu trúc cơ bản sau trong một migration, rồi gửi nó qua quy trình review và triển khai phù hợp:

```sql
CREATE TABLE app_order (
    order_id    NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    customer_id NUMBER NOT NULL,
    status      VARCHAR2(20 CHAR) DEFAULT 'NEW' NOT NULL,
    created_at  TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_app_order PRIMARY KEY (order_id),
    CONSTRAINT ck_app_order_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX ix_app_order_customer_created
    ON app_order (customer_id, created_at);
```

Developer cần giải thích vì sao `customer_id` bắt buộc, tập giá trị `status` có phù hợp với quy trình nghiệp vụ và chỉ mục phục vụ truy vấn nào. DBA có thể phản biện về tăng trưởng, tính chọn lọc, chi phí duy trì index, naming, phân vùng hoặc tác động của DDL trên production. Không nên tạo chỉ mục chỉ vì một cột xuất hiện trong `WHERE`: cần quan sát execution plan và workload thực tế.

Khi nhận dữ liệu đầu vào, ứng dụng phải dùng bind variable; ví dụ một truy vấn theo khách hàng:

```sql
SELECT order_id, status, created_at
FROM app_order
WHERE customer_id = :customer_id
ORDER BY created_at DESC;
```

`:customer_id` minh họa placeholder được driver hoặc công cụ Oracle bind bằng giá trị đã kiểm tra. Trong Java, `PreparedStatement` (hoặc cơ chế tham số của ORM) thực hiện việc bind; không tạo SQL bằng cách nối chuỗi chứa đầu vào người dùng.

### 2.2. Những việc developer không tự quyết trên production

Không nên mặc định rằng người viết migration được tự cấp quyền cao, sửa cấu hình toàn instance, tăng tablespace, truy cập dữ liệu khách hàng thật, dừng database hoặc thực thi DDL rủi ro trong giờ cao điểm. Developer **đề xuất phương án và cung cấp bằng chứng kỹ thuật**; người được ủy quyền duyệt lịch thay đổi, quyền truy cập và cách triển khai theo quy trình thực tế.

Với Oracle, có một điểm phải ghi nhớ: **nhiều lệnh DDL thông thường như `CREATE`, `ALTER`, `DROP` gây implicit commit**. Vì thế không thể giả định một chuỗi migration DDL sẽ tự đảo ngược chỉ bằng `ROLLBACK` như giao dịch DML. Kế hoạch thay đổi schema cần xét tính tương thích, dữ liệu đã biến đổi và phương án khắc phục sau khi phát hành.

## 3. DBA: sở hữu độ tin cậy và quản trị của Oracle Database

DBA chịu trách nhiệm về **sức khỏe và tính toàn vẹn của nền tảng cơ sở dữ liệu**. DBA cần hiểu workload ứng dụng, nhưng mục tiêu không chỉ là tối ưu một câu SQL mà còn phải bảo đảm nhiều ứng dụng/tenant cùng vận hành an toàn.

### 3.1. Công việc điển hình

| Nhóm nhiệm vụ | Phạm vi DBA thường đảm nhiệm |
|---|---|
| Cài đặt và cấu hình | Cài đặt/nâng cấp Oracle, quản lý instance, CDB/PDB, tham số và dịch vụ Oracle theo mô hình tổ chức. |
| Quyền truy cập | Tạo/quản trị user, role, grant, chính sách mật khẩu, quyền truy cập production, tách tài khoản ứng dụng với tài khoản migration và quản trị. |
| Lưu trữ và dung lượng | Quản lý tablespace, datafile, tăng trưởng, redo/undo, quota và giới hạn tài nguyên; phối hợp với nhóm hạ tầng khi thiếu dung lượng vật lý. |
| Sao lưu và phục hồi | Thiết kế, kiểm tra và giám sát backup bằng RMAN hoặc giải pháp tương thích; thực hành restore/recovery, đối chiếu RPO/RTO đã thống nhất. |
| Tính sẵn sàng | Triển khai, theo dõi và diễn tập cơ chế dự phòng/chuyển đổi như Data Guard, hoặc RAC khi kiến trúc thực sự sử dụng. |
| Chẩn đoán hiệu năng | Phân tích wait event, session, lock, I/O, execution plan, thống kê optimizer, resource contention; hỗ trợ developer tối ưu workload. |
| Bảo trì và an ninh | Lập kế hoạch patch/upgrade, audit, kiểm tra chính sách bảo mật và khả năng tương thích trước khi thay đổi. |

Ví dụ, với yêu cầu bảng `app_order` dự kiến đạt hàng trăm triệu dòng, DBA có thể đánh giá dung lượng, chiến lược index/partition, lịch thu thập optimizer statistics, ảnh hưởng đến redo/undo và cửa sổ bảo trì. Quyết định chia partition hay thay đổi cấu trúc phải dựa trên dữ liệu và yêu cầu truy vấn, không mặc định áp dụng cho mọi bảng lớn.

DBA thường dùng các công cụ/view như `V$SESSION`, `V$SQL`, `DBMS_XPLAN` hoặc các báo cáo chẩn đoán khi được cấp quyền. Một số tính năng Oracle, chẳng hạn AWR/ASH và các công cụ tuning nhất định, có điều kiện cấp phép; không nên mặc định môi trường nào cũng được sử dụng.

### 3.2. Những việc DBA không thể quyết thay ứng dụng

DBA không nên tự sửa ý nghĩa nghiệp vụ của dữ liệu, xóa bản ghi theo suy đoán, chỉnh truy vấn nguồn mà không phối hợp với đội phát triển hoặc bảo đảm tính đúng đắn giao dịch chỉ bằng cách nâng cấu hình máy chủ. Chẳng hạn, tăng `UNDO` có thể hỗ trợ một vấn đề vận hành, nhưng nếu ứng dụng giữ transaction quá lâu thì developer vẫn phải xử lý nguyên nhân tại mã.

Quyền có thể cao không đồng nghĩa với việc có quyền phê duyệt mọi thay đổi: thao tác ảnh hưởng đến dữ liệu, an ninh hoặc khả năng phục hồi vẫn cần quy trình và người chịu trách nhiệm theo tổ chức.

## 4. Người vận hành: sở hữu việc cung cấp và duy trì dịch vụ chạy thực tế

Operations/SRE/platform engineer nhìn hệ thống như một **dịch vụ đầu cuối**: ứng dụng có chạy được, kết nối Oracle có ổn định, triển khai có an toàn, cảnh báo có đến đúng người và sự cố có được xử lý trong thời gian cam kết hay không.

### 4.1. Công việc điển hình

- **Cung cấp môi trường:** hệ điều hành, VM/container nơi phù hợp, mạng, DNS, firewall, load balancer, lưu trữ, chứng chỉ, cấu hình kết nối và tích hợp với nền tảng Oracle theo phân quyền.
- **Triển khai và thay đổi:** CI/CD, cấu hình deployment, lịch phát hành, health check, smoke test, phối hợp chạy migration được duyệt và ghi lại thay đổi đã triển khai.
- **Giám sát và cảnh báo:** độ sẵn sàng API, tỷ lệ lỗi, độ trễ, connection pool, độ trễ kết nối, disk/storage, CPU/RAM, khả năng phục vụ của database service; chuyển cảnh báo đến đúng nhóm.
- **Vận hành sự cố:** nhận alert, xác định phạm vi ảnh hưởng, liên lạc với developer/DBA, thao tác theo runbook, quản lý incident timeline, theo dõi khôi phục và tổ chức postmortem.
- **Bảo đảm năng lực vận hành:** quản lý cấu hình và secret qua cơ chế được phép, diễn tập quy trình failover/khôi phục cùng DBA, duy trì runbook và phương án xử lý thay đổi thất bại.
- **Capacity và bảo trì hạ tầng:** theo dõi tài nguyên, phối hợp nâng cấp host/storage/network, tránh điểm nghẽn nằm ngoài process Oracle.

Trong tổ chức nhỏ, người vận hành có thể kiêm DBA; ở dịch vụ Oracle được quản lý, một số nhiệm vụ quản trị database do nhà cung cấp thực hiện. Khi đó cần một **bảng phân công thực tế** xác định ai có quyền thực thi, ai duyệt, ai trực on-call và ai liên hệ nhà cung cấp.

### 4.2. Những việc operations không tự quyết

Operations không nên tự viết lại SQL nghiệp vụ, sửa dữ liệu production để làm alert biến mất, mở quyền `SYSDBA` cho một job triển khai hoặc khởi động lại Oracle tùy tiện khi chưa biết tác động. Runbook có thể cho phép một thao tác nhất định, nhưng phải xác định trước phạm vi, điều kiện kích hoạt, bằng chứng cần thu thập và người có thẩm quyền.

## 5. Ranh giới ở những công việc thường bị nhầm lẫn

Bảng dưới mô tả **đầu mối chuyên môn thông thường**, không thay thế ma trận trách nhiệm được tổ chức phê duyệt. “Phối hợp” không mặc nhiên có quyền đăng nhập production hoặc thực thi thao tác.

| Công việc | Developer | DBA | Operations/SRE |
|---|---|---|---|
| Thiết kế bảng và constraint nghiệp vụ | **Đề xuất, giải thích quy tắc, kiểm thử** | Review tác động và chuẩn database | Nắm thay đổi khi cần phát hành |
| Tạo/chỉnh schema bằng migration | **Soạn mã, phương án tương thích** | Review hoặc thực thi theo quyền/quy trình | Điều phối pipeline, lịch chạy, theo dõi |
| Tạo user, role, grant/quota | Xác định quyền ứng dụng thật sự cần | **Quản trị và phê duyệt kỹ thuật theo chính sách** | Cấp secret cho workload qua nền tảng an toàn |
| Chẩn đoán truy vấn chậm | **Tối ưu SQL, số lần gọi, transaction** | **Kiểm tra plan, statistics, wait, tài nguyên** | Ghép metric ứng dụng, hạ tầng, thời điểm phát hành |
| Thêm chỉ mục | **Nêu truy vấn và dữ liệu kiểm chứng** | Review lợi ích/chi phí, vận hành DDL khi cần | Điều phối thời điểm thay đổi và cảnh báo |
| Điều chỉnh memory/parameter Oracle | Cung cấp bằng chứng workload | **Đánh giá và điều chỉnh theo quyền** | Chuẩn bị năng lực hạ tầng, cửa sổ bảo trì |
| Tăng tablespace/datafile | Dự báo tăng trưởng dữ liệu nghiệp vụ | **Quản lý không gian Oracle** | **Đảm bảo storage/hạ tầng đủ năng lực** |
| Cấu hình connection pool | **Chọn mức sử dụng ứng dụng và timeout** | Tư vấn giới hạn session, tải trên database | Quan sát pool, giới hạn deployment/replica |
| Backup và thử khôi phục | Xác nhận tính nhất quán nghiệp vụ sau restore | **Thiết kế, quản lý và kiểm chứng database recovery** | Tự động hóa, lưu giữ, cảnh báo, tổ chức diễn tập |
| Phát hành ứng dụng | **Bàn giao artifact, migration, smoke test** | Hỗ trợ thay đổi database và theo dõi rủi ro | **Điều phối, thực thi, quan sát release** |
| Sự cố production | Điều tra logic, SQL, pool, bản phát hành | Điều tra Oracle, lock, space, recovery | **Nhận cảnh báo, điều phối ứng phó đầu cuối** |

Chữ **“đầu mối” không tương đương “chịu trách nhiệm cuối cùng”**. Ví dụ, team SRE có thể trực điều phối incident, nhưng chủ dịch vụ vẫn là người chịu trách nhiệm về đáp ứng mục tiêu dịch vụ. Tổ chức nên dùng RACI cho thay đổi quan trọng:

- **R – Responsible:** người trực tiếp thực hiện.
- **A – Accountable:** người chịu trách nhiệm cuối cùng và phê duyệt kết quả; mỗi hoạt động nên có một đầu mối A rõ ràng.
- **C – Consulted:** chuyên gia cần được tham vấn trước quyết định.
- **I – Informed:** người cần được cập nhật kết quả.

Ví dụ, một kế hoạch mở rộng tablespace có thể phân công `DBA = R`, `database service owner = A`, `operations/storage = C hoặc R` cho phần cấp đĩa và `developer = I`. Đây chỉ là ví dụ; nếu DBA và operations là cùng một nhóm thì vẫn phải định rõ người nhận việc và đường xử lý khi sự cố.

## 6. Quy trình phối hợp: thêm tính năng đặt hàng có thay đổi database

Giả sử API phải bổ sung trạng thái đơn hàng, chỉ mục truy vấn lịch sử và một thao tác cập nhật hàng loạt. Thay đổi có rủi ro vì bảng hiện có dữ liệu lớn và phải chạy trong môi trường Oracle production.

### Bước 1 – Developer chuẩn bị yêu cầu và migration

Developer cung cấp các thành phần sau trong cùng một change request:

1. Mô tả nghiệp vụ, schema trước/sau, DDL/DML theo phiên bản và người sở hữu thay đổi.
2. Dung lượng/khối lượng dự kiến, truy vấn tiêu biểu, execution plan và kết quả đo ở môi trường gần production.
3. Đánh giá tương thích ứng dụng cũ/mới; ví dụ thêm cột `NULL` trước, phát hành mã hỗ trợ cả hai phiên bản, backfill theo batch rồi mới siết constraint nếu phù hợp.
4. Rủi ro locking, thời gian chạy, tác động lên redo/undo, cơ chế chạy tiếp nếu migration bị ngắt.
5. Hướng xử lý khi thất bại: ứng dụng quay lại phiên bản nào, dữ liệu đã ghi sẽ được giữ/khắc phục ra sao, ai quyết định dừng triển khai.

Với các migration Oracle, **phương án khôi phục không đồng nghĩa với `ROLLBACK` của một transaction**: DDL đã implicit commit, index có thể đã được tạo một phần/hoàn tất, backfill DML có thể đã commit theo từng batch. Một kế hoạch sửa tiến (forward fix), tương thích tạm thời hoặc khôi phục từ bản sao lưu phải được xác định theo tình huống và yêu cầu kinh doanh.

### Bước 2 – DBA xem xét tác động cấp database

DBA kiểm tra quyền của tài khoản migration, tính khả thi của DDL, dung lượng, thống kê, ảnh hưởng đến khóa/bảo trì và năng lực recovery. Nếu thay đổi có nguy cơ khóa kéo dài hoặc truy cập dữ liệu lớn, DBA đề xuất kỹ thuật và lịch phù hợp; với trường hợp phức tạp có thể đánh giá phương án online redefinition hoặc giải pháp khác tùy khả năng phiên bản, cấp phép và vận hành.

DBA cũng xác định **điểm quan sát trước và sau thay đổi**: session/lock bất thường, lỗi ORA, mức tiêu thụ tablespace, thời gian truy vấn quan trọng, tốc độ tăng redo và tình trạng backup/recovery.

### Bước 3 – Operations tổ chức phát hành

Operations bảo đảm artifact và migration đã duyệt được triển khai đúng thứ tự, có người trực xử lý và có cơ chế dừng khi vượt ngưỡng. Pipeline phải dùng identity riêng có quyền vừa đủ; account runtime của ứng dụng không cần sở hữu quyền DDL nếu chức năng của nó chỉ đọc/ghi dữ liệu. Sau release, operations theo dõi tỷ lệ lỗi, độ trễ, pool và sức khỏe dịch vụ; developer xác minh nghiệp vụ; DBA theo dõi dấu hiệu bất thường phía Oracle.

```text
Developer: thiết kế -> migration -> test -> bàn giao rủi ro
                                 |
                                 v
DBA:       review DDL/quyền/dung lượng -> chuẩn bị database
                                 |
                                 v
Operations: điều phối release -> chạy bước được duyệt -> quan sát
                                 |
                                 v
            Developer + DBA + Operations xác nhận kết quả
```

Một câu hỏi thiết thực trước khi triển khai là: **“Nếu deployment dừng sau DDL đầu tiên, hệ thống và dữ liệu đang ở trạng thái nào?”** Nếu không ai trả lời được, kế hoạch thay đổi chưa đủ rõ để vận hành an toàn.

## 7. Quy tắc quyền truy cập: tách tài khoản và trách nhiệm

Trong Oracle, quyền mà một thành viên có thể *làm được* về kỹ thuật không có nghĩa người đó *nên làm* trong quy trình. Áp dụng nguyên tắc **least privilege** và **separation of duties**:

| Danh tính/tài khoản | Mục đích | Nguyên tắc |
|---|---|---|
| Runtime application user | Thực thi SQL mà ứng dụng cần trong lúc chạy | Chỉ cấp quyền DML/EXECUTE cần thiết vào đối tượng phù hợp; không tự ý dùng tài khoản quản trị. |
| Migration/deployment user | Chạy thay đổi schema được phê duyệt | Quyền DDL giới hạn theo schema và thời điểm; quản lý secret và audit riêng. |
| DBA/admin identity | Quản trị Oracle, recovery, cấu hình, bảo mật | Cấp đặc quyền theo nhu cầu được kiểm soát; ghi dấu vết thao tác; `SYSDBA` dành cho công việc thật sự cần. |
| Monitoring identity | Đọc metric/view phục vụ chẩn đoán | Quyền chỉ đọc cần thiết; tránh dùng tài khoản toàn quyền chỉ để lấy số liệu. |

Ví dụ, developer có thể yêu cầu “ứng dụng cần đọc `customer_id`, ghi `status` và gọi một package nghiệp vụ”, nhưng DBA/chủ sở hữu dữ liệu mới quyết định cách cấp `SELECT`/`UPDATE`/`EXECUTE` phù hợp. Khi dùng schema chung, synonym, view hoặc PL/SQL definer/invoker rights, cần xem rõ quyền thực thi thực tế thay vì đoán qua tên tài khoản.

Các môi trường `dev`, `test`, `staging`, `production` cũng cần giới hạn độc lập. Dữ liệu production khi sao chép sang môi trường thấp hơn phải tuân thủ quy tắc bảo vệ/masking được duyệt. Mật khẩu và chuỗi kết nối không được hard-code vào mã nguồn hoặc log.

## 8. Phối hợp khi có sự cố: ba ví dụ đặc trưng Oracle

### Tình huống A – API báo `ORA-01653: unable to extend table ...`

Đây thường là dấu hiệu Oracle không thể cấp thêm extent cho một bảng trong tablespace theo điều kiện hiện tại; không kết luận ngay “ổ đĩa máy chủ đã đầy”.

- **Operations** xác định các API và thời điểm bị ảnh hưởng, kiểm tra alert, storage và mức tăng lỗi; mở incident và giữ bằng chứng.
- **DBA** kiểm tra tablespace, datafile/autoextend, quota, dung lượng vật lý và xu hướng tăng trưởng; chọn phương án mở rộng hoặc xử lý dữ liệu theo quy trình.
- **Developer** phân tích workload/tăng trưởng bất thường, batch ghi mới, chính sách lưu trữ và thay đổi gần đây; xác nhận dữ liệu nào có thể được dọn theo quy tắc nghiệp vụ.

Không xóa bảng hay dữ liệu nghiệp vụ chỉ để giải phóng dung lượng. Việc sửa phải dựa vào phạm vi ảnh hưởng và người có quyền quyết định dữ liệu.

### Tình huống B – Giao dịch lỗi `ORA-00060: deadlock detected`

Oracle phát hiện vòng chờ khóa và báo lỗi cho một statement liên quan. Ứng dụng phải xử lý giao dịch thất bại đúng cách và bảo đảm trạng thái nhất quán.

- **Operations** đối chiếu thời điểm phát sinh lỗi với release, lưu lượng và ảnh hưởng người dùng.
- **DBA** cung cấp thông tin khóa, session và deadlock trace phù hợp với quyền truy cập để nhận diện đối tượng liên quan.
- **Developer** kiểm tra thứ tự cập nhật các bảng/dòng, thời gian giữ transaction, xử lý exception và chiến lược retry an toàn nếu nghiệp vụ cho phép.

Thêm CPU hoặc tăng connection pool không sửa được vòng chờ khóa do mã ứng dụng tạo ra. Retry mù quáng có thể nhân đôi tác dụng nghiệp vụ nếu thao tác không idempotent.

### Tình huống C – Ứng dụng kết nối lỗi `ORA-12514`

Thông báo này thường cho biết listener không nhận diện service được yêu cầu trong descriptor kết nối tại thời điểm đó. Nguyên nhân có thể ở cấu hình client/service, đăng ký dịch vụ hoặc trạng thái database/PDB.

- **Operations** kiểm tra DNS, đường mạng, biến cấu hình, secret rotation, health check và thay đổi hạ tầng gần thời điểm lỗi.
- **DBA** kiểm tra listener, database/PDB service, đăng ký dịch vụ và trạng thái khả dụng của điểm kết nối.
- **Developer** xác minh JDBC URL/service name, thay đổi cấu hình ứng dụng, timeout và hành vi retry của pool.

Tách `ORA-12514` khỏi lỗi xác thực như `ORA-01017` sẽ giúp định tuyến sự cố chính xác hơn. Không tự tăng quyền cho ứng dụng để “sửa kết nối”.

## 9. Bàn giao công việc: cần đưa cho nhau thông tin gì?

Một yêu cầu tốt phải giúp người nhận đánh giá **mức ảnh hưởng, bằng chứng và hành động được phép**. Mẫu thông tin tối thiểu:

| Khi nào | Thông tin cần bàn giao |
|---|---|
| Developer nhờ DBA review | Mục đích nghiệp vụ, DDL/SQL cụ thể, schema/PDB dự kiến, số dòng/dung lượng ước tính, execution plan/đo tải, cửa sổ thay đổi đề xuất và phương án nếu thất bại. |
| DBA nhờ operations hỗ trợ | Service/instance bị ảnh hưởng, nhu cầu disk/network/CPU, giới hạn hoạt động, thao tác dự kiến, ngưỡng cảnh báo, đầu mối hỗ trợ và thời điểm có thể can thiệp. |
| Operations mở incident | Bắt đầu lúc nào, môi trường, service, symptom người dùng, error code, release gần nhất, metric/log/trace ID, mức độ ảnh hưởng và điều đã thử. |
| Developer nhận sự cố từ DBA | SQL hoặc transaction có liên quan, hướng dẫn tái hiện, thông tin plan/lock được phép chia sẻ, giả thuyết về mã và kết quả kiểm chứng. |

Trong incident, nhóm vận hành thường điều phối tiến độ và truyền thông, nhưng **quyết định kỹ thuật nên do người sở hữu phần việc tương ứng đưa ra**. Chẳng hạn, DBA có thể xác nhận database cần restore; chủ dịch vụ và người có thẩm quyền nghiệp vụ phải hiểu việc khôi phục về thời điểm cũ có thể làm mất các giao dịch sau mốc đó.

Hai chỉ tiêu cần thỏa thuận trước là **RPO (Recovery Point Objective)** – mức mất dữ liệu tối đa chấp nhận – và **RTO (Recovery Time Objective)** – thời gian tối đa mong muốn để khôi phục dịch vụ. DBA thiết kế và thử nghiệm giải pháp recovery, operations điều phối phục hồi, còn chủ hệ thống/nghiệp vụ xác nhận các mục tiêu và tác động chấp nhận được. **Có backup chưa đủ; phải kiểm chứng khả năng restore/recover.**

## 10. Các hiểu lầm thường gặp

| Nhận định dễ mắc | Cách hiểu đúng |
|---|---|
| “Ứng dụng chậm thì DBA tăng cấu hình database.” | Phải đo xem chậm do SQL, lock, pool, I/O, network hay giới hạn tài nguyên; mỗi nhóm xử lý nguyên nhân thuộc phạm vi của mình. |
| “Developer tạo schema thì developer phải có `SYSDBA`.” | Thiết kế schema và quyền quản trị cao là hai việc khác nhau; migration chỉ cần quyền đúng phạm vi và quy trình. |
| “Có thể `ROLLBACK` mọi migration Oracle.” | DDL thông thường implicit commit; cần thay đổi tương thích và phương án khắc phục cụ thể. |
| “DBA có backup thì chắc chắn khôi phục đúng hạn.” | Cần backup đúng, khả năng restore/recover được diễn tập và hạ tầng đáp ứng RPO/RTO. |
| “Operations nhận alert nên phải tự sửa database.” | Operations điều phối, thực thi runbook được phép và gọi DBA/developer khi cần quyền hoặc chuyên môn tương ứng. |
| “Thêm nhiều connection sẽ làm hệ thống nhanh.” | Pool lớn hơn có thể đẩy database vào quá tải session/CPU/lock; phải cân đối tải của ứng dụng với năng lực database. |
| “DBA luôn sở hữu mọi câu SQL.” | Developer sở hữu ngữ nghĩa và cách gọi SQL của ứng dụng; DBA hỗ trợ optimizer, thống kê, tài nguyên và an toàn vận hành. |

## 11. Thực hành phân công trong một nhóm Oracle

Giả sử sau một bản phát hành, thời gian trả lời API tăng từ khoảng 200 ms lên 4 giây và session Oracle tăng mạnh. Hãy áp dụng cách làm sau:

1. **Operations** phát hiện và ghi nhận khung thời gian, release ID, tỷ lệ lỗi, latency, connection pool, số replica và các alert liên quan; xác định có cần dừng phát hành hoặc kích hoạt phương án khôi phục đã duyệt không.
2. **Developer** so sánh các đường gọi SQL trước/sau release; kiểm tra N+1, truy vấn không có điều kiện lọc, transaction kéo dài, pool bị giữ connection và việc retry làm tăng tải.
3. **DBA** xem session/wait/lock, top SQL theo bằng chứng sẵn có, execution plan, thống kê và năng lực instance; xác nhận có thay đổi plan hay nghẽn tài nguyên database hay không.
4. **Cả nhóm** thống nhất giả thuyết dựa vào dữ liệu: ví dụ release mới thêm truy vấn thiếu điều kiện chọn lọc, khiến hàng loạt session giữ connection lâu. Developer sửa truy vấn; DBA xác nhận plan/tác động; operations triển khai bản sửa và theo dõi hệ thống trở về mức bình thường.
5. **Sau sự cố**, ghi nguyên nhân, thời điểm ảnh hưởng, bước khôi phục, cảnh báo còn thiếu và cải tiến cho migration/monitoring/runbook. Người sở hữu từng hạng mục chịu trách nhiệm thực hiện theo hạn đã thống nhất.

Có thể tự kiểm tra ranh giới bằng ba câu hỏi: **(1)** Ai hiểu ý nghĩa nghiệp vụ của thay đổi? **(2)** Ai có chuyên môn và quyền hợp lệ đối với đối tượng Oracle bị ảnh hưởng? **(3)** Ai theo dõi và điều phối trạng thái dịch vụ khi thay đổi được đưa lên production? Thông thường câu trả lời lần lượt dẫn đến developer, DBA và operations, nhưng một hoạt động chỉ hoàn chỉnh khi ba câu hỏi đã được gắn với người chịu trách nhiệm cụ thể.

## Kết luận

Trong hệ thống dùng Oracle Database, **developer bảo đảm ứng dụng sử dụng dữ liệu đúng và hiệu quả; DBA bảo đảm nền tảng dữ liệu an toàn, có thể quản trị và phục hồi; operations bảo đảm toàn bộ dịch vụ được triển khai, giám sát và xử lý sự cố có kiểm soát**. Đường ranh quan trọng nhất không nằm ở ai biết chạy một lệnh SQL, mà ở **quyền quyết định, trách nhiệm với rủi ro và bằng chứng bàn giao**. Khi thay đổi schema, hiệu năng hoặc availability liên quan đến nhiều lớp, phân công rõ người thực hiện, người phê duyệt và người phối hợp sẽ giảm lỗi và rút ngắn thời gian khôi phục.
