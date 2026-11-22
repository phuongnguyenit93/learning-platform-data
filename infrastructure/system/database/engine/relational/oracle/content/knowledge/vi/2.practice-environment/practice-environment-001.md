# Chọn bản Oracle phù hợp với bài thực hành và giới hạn tài nguyên

Một môi trường Oracle dùng để học cần **đúng chức năng của bài**, **chạy ổn định trên tài nguyên sẵn có** và **có thể tái tạo khi làm lại bài thực hành**. Chọn bản có nhiều tính năng nhất chưa chắc tốt: một máy cá nhân chạy IDE, trình duyệt và database cùng lúc có thể thiếu RAM; ngược lại, một dịch vụ SQL trên trình duyệt tuy nhẹ nhưng không cho thực hành quản trị instance.

Bài học này hướng dẫn cách chọn **phiên bản (release)**, **ấn bản (edition)** và **cách triển khai** Oracle Database cho các bài SQL, PL/SQL, Java/JDBC, thiết kế schema và những bài quản trị cơ bản. Mục tiêu là đưa ra được một cấu hình có lý do rõ ràng trước khi tải phần mềm hoặc tạo máy ảo.

## 1. Phân biệt những lựa chọn dễ bị nhầm

Khi nói “dùng Oracle bản nào?”, thực tế có ít nhất bốn quyết định:

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Release** | Bài học đòi cú pháp và hành vi của thế hệ Oracle nào? | 19c, 21c, 23ai, 26ai |
| **Edition / quyền sử dụng** | Cần tính năng nào, có giới hạn tài nguyên và điều kiện cấp phép nào? | Oracle AI Database Free, Standard Edition 2 (SE2), Enterprise Edition (EE) |
| **Hình thức triển khai** | Database nằm ở đâu, ai chịu trách nhiệm cài đặt và quản trị? | Cài trực tiếp, container, máy ảo, dịch vụ OCI |
| **Công cụ kết nối** | Người học gửi SQL hoặc mã ứng dụng vào database bằng gì? | SQLcl, SQL Developer, SQL*Plus, JDBC |

**SQL Developer và SQLcl là công cụ khách (client), không phải một bản Oracle Database server.** Cài riêng SQL Developer sẽ không tự tạo database trên máy. Tương tự, một container Oracle là cách *đóng gói và chạy* một edition/release cụ thể, không phải edition mới.

### Release và edition có vai trò khác nhau

- **Release** quyết định phiên bản tính năng, cú pháp, khả năng tương thích và chu kỳ hỗ trợ. Một script dùng chức năng mới của 26ai có thể không chạy trên 19c.
- **Edition** quyết định bộ tính năng được phép dùng và các giới hạn sử dụng. Cùng một release nhưng Free, SE2 và EE không nhất thiết có quyền sử dụng mọi tính năng giống nhau.
- **Bài học ghi rõ 19c** thì không tự đổi sang 26ai chỉ vì 26ai mới hơn: kết quả, màn hình và khả năng hỗ trợ một tính năng cụ thể có thể khác. Hãy kiểm tra tài liệu phiên bản và edition đúng với yêu cầu bài.

Tại thời điểm biên soạn, **Oracle AI Database 26ai Free** là lựa chọn Free hiện hành được Oracle giới thiệu cho phát triển và thực hành cục bộ; Oracle cho biết 26ai đã thay thế 23ai trong dòng sản phẩm hiện tại. **Oracle Database 21c XE** và các bản XE cũ có thể còn gặp trong giáo trình cũ, nhưng không nên mặc định tải chúng cho bài mới nếu không có yêu cầu tương thích cụ thể.

## 2. Các lựa chọn phù hợp với phòng thực hành

| Lựa chọn | Phù hợp nhất khi | Điều cần tính trước |
| --- | --- | --- |
| **Oracle AI Database 26ai Free trên máy cá nhân** | Học SQL, PL/SQL, schema, index, transaction, kết nối ứng dụng Java và quản trị cơ bản | Có giới hạn CPU/RAM/dữ liệu; máy phải đủ dung lượng cho cả hệ điều hành, IDE và database |
| **Oracle AI Database 26ai Free trong container** | Muốn cô lập môi trường, dễ tạo lại, thống nhất giữa các thành viên | Docker/Podman vẫn tiêu thụ RAM và dung lượng host; cần volume để giữ dữ liệu |
| **Oracle AI Database 26ai Free cài trực tiếp hoặc trong VM** | Muốn quan sát dịch vụ hệ điều hành, listener, file và thao tác quản trị gần môi trường server | Cài đặt và chăm sóc hệ thống phức tạp hơn container; VM còn tiêu tốn tài nguyên riêng |
| **Oracle Live SQL (trên web)** | Chỉ cần thực hành SQL/PL/SQL cơ bản trên máy yếu hoặc không được phép cài phần mềm | Không có quyền quản lý instance, listener, file hệ thống, backup hoặc cấu hình mạng |
| **OCI Always Free Autonomous Database** | Muốn database hoạt động từ xa, có tài nguyên do cloud cấp, hoặc học cách truy cập dịch vụ quản lý | Cần tài khoản, mạng và tuân theo hạn mức/chính sách cloud hiện hành; quyền quản trị khác database tự cài |
| **Oracle 19c / 21c hoặc SE2 / EE theo môi trường được cấp** | Bài thực hành nêu đích danh release cũ, tính năng thương mại hoặc tương thích hệ thống của doanh nghiệp | Phải xác minh bản cài, quyền sử dụng, hỗ trợ và điều kiện truy cập; không giả định có thể thay bằng Free |

**Gợi ý mặc định:** nếu bài không khóa phiên bản, người học có máy phù hợp và cần SQL/PLSQL/JDBC thực sự, hãy bắt đầu với **26ai Free, triển khai bằng container**. Khi bài yêu cầu quan sát dịch vụ hệ điều hành hoặc phục hồi ở mức máy chủ, cân nhắc cài trực tiếp/VM. Nếu mục tiêu chỉ là viết truy vấn và máy quá yếu, bắt đầu trên Live SQL.

### Free “Full” và “Lite” trong container

Oracle Container Registry có image Free loại **Full** (ví dụ tag `latest`) và **Lite** (tag `latest-lite`). Lite thuận lợi khi ưu tiên image nhỏ và bài rất đơn giản, nhưng **không có một số thành phần của Full**; tài liệu image nêu những giới hạn của Lite, chẳng hạn Oracle Data Pump và RMAN.

Vì vậy:

- Bài `SELECT`, `JOIN`, `GROUP BY` hoặc giao tiếp JDBC đơn giản: có thể cân nhắc Lite sau khi đối chiếu chức năng dùng trong bài.
- Bài `expdp`/`impdp`, backup/recovery với RMAN, một số công cụ chẩn đoán và chức năng nâng cao: chọn **Full** hoặc môi trường Oracle đã xác minh có đủ thành phần.
- Không đổi image từ Full sang Lite trên cùng một data volume nếu chưa có kế hoạch di chuyển/khôi phục được hỗ trợ.

“Nhẹ hơn” ở đây là lựa chọn thành phần đóng gói; **không đồng nghĩa** Oracle Lite là một hệ quản trị quan hệ khác hoặc chắc chắn dùng ít RAM hơn trong mọi bài.

## 3. Đọc giới hạn tài nguyên đúng cách

Với **Oracle AI Database 26ai Free**, Oracle công bố các giới hạn chính sau:

| Giới hạn của Free | Ý nghĩa thực tế |
| --- | --- |
| **Tối đa 2 CPU cores** cho xử lý database | Host có nhiều core hơn không làm Free sử dụng vượt mức xử lý này cho database |
| **Tối đa 2 GB RAM dành cho database** | Giới hạn bộ nhớ cơ sở dữ liệu (SGA và PGA), **không phải** toàn bộ RAM cần cho host/container/IDE |
| **Tối đa 12 GB dữ liệu người dùng** | Giới hạn phần user data bên trong Oracle; **không phải** tổng dung lượng đĩa mà image, redo, temporary files, logs và backup chiếm |
| **Một cài đặt trong mỗi môi trường logic** | Môi trường logic có thể là máy vật lý, VM hoặc container; cần tuân thủ quy định riêng của Free |

Vượt giới hạn kích thước user data có thể gây lỗi `ORA-12954`; cố chạy thêm một bản cài Free trong cùng môi trường logic có thể gây `ORA-00442`. Giới hạn của edition không thể “mở khóa” bằng cách cấp thêm RAM hay CPU cho container.

**Phân biệt giới hạn sản phẩm với yêu cầu máy:**

1. **Giới hạn Free** là trần mà Oracle áp cho engine, kể cả khi máy chủ mạnh.
2. **Yêu cầu tối thiểu để cài** phụ thuộc hệ điều hành và dạng phân phối. Tài liệu cài Linux cho 26ai Free nêu mức tối thiểu 1 GB RAM, khuyến nghị 2 GB RAM và ít nhất 10 GB dung lượng đĩa cho nền tảng Linux được hỗ trợ; tài liệu Windows yêu cầu ít nhất 2 GB RAM, khoảng 8,5 GB cho phần mềm cùng ít nhất 2 GB bộ nhớ tạm trên đĩa.
3. **Tài nguyên để học thoải mái** còn phải tính browser, SQL client, IntelliJ/VS Code, JVM, Docker Desktop/VM, volume dữ liệu và file tải về.

Các con số trong bảng dưới đây là **mức lập kế hoạch gợi ý**, không phải cấu hình tối thiểu do Oracle cam kết:

| Máy học / môi trường | Cách tiếp cận hợp lý | Lý do |
| --- | --- | --- |
| **RAM 2–4 GB, ít dung lượng đĩa** | Live SQL hoặc OCI nếu có Internet và tài khoản phù hợp | Database local + hệ điều hành + IDE dễ tranh chấp RAM |
| **RAM khoảng 8 GB, còn ít nhất 25–40 GB đĩa trống** | Free container hoặc cài trực tiếp; điều chỉnh số ứng dụng mở đồng thời | Dành khoảng đệm cho image, dữ liệu, build Java, logs và các đợt thực hành |
| **RAM 16 GB trở lên, đủ dung lượng đĩa** | Free container/VM, có thể chạy thêm ứng dụng Java và công cụ quản trị | Dư địa host rộng hơn nhưng **Free vẫn chịu trần 2 core / 2 GB RAM** |
| **Máy phòng lab dùng chung / server** | Một môi trường được quản trị và cấp tài khoản/schema riêng cho người học, hoặc mỗi người có môi trường cô lập đã được cấp phép | Tránh trùng service/port, gây xóa dữ liệu lẫn nhau và lộ tài khoản quản trị |

**Lưu ý về ổ đĩa:** không tính `12 GB user data` như thể chỉ cần ổ trống 12 GB. Oracle software/image, cấu trúc database, file tạm, redo, log, Docker layer và bản sao lưu có thể làm dung lượng thực tế lớn hơn đáng kể. Nếu máy chỉ còn vài GB trống, chọn lab web/cloud trước.

### Kiểm tra nhanh tài nguyên trước khi chọn

Ghi ra bốn thông tin của máy:

- **Kiến trúc CPU:** x86-64 hay ARM64; image/bộ cài phải hỗ trợ kiến trúc thực tế, nhất là trên máy Mac dùng Apple Silicon.
- **RAM vật lý và dung lượng đang rảnh:** đánh giá khi các ứng dụng thực hành cần thiết đang chạy.
- **Dung lượng trống ở ổ sẽ đặt image/volume hoặc dữ liệu Oracle:** không chỉ ổ lưu file tải xuống.
- **Khả năng sử dụng container/VM và quyền cài đặt:** Docker Desktop, Podman, BIOS virtualization, quyền quản trị hệ điều hành và giới hạn do phòng lab áp dụng.

Không suy ra “database Free chỉ dùng 2 GB” nghĩa là một laptop 2 GB RAM sẽ chạy cùng Windows, Docker Desktop và IDE một cách ổn định. Giới hạn RAM của database và chi phí của **toàn môi trường** là hai phép tính khác nhau.

## 4. Quy trình quyết định từ yêu cầu bài học

### Bước 1 — Xác định điều bài bắt buộc phải làm

Trước tiên xác nhận bài thuộc nhóm nào:

- **SQL thuần:** DDL, DML, query, join, aggregate, constraint.
- **PL/SQL:** block, function, procedure, package, exception, trigger.
- **Lập trình ứng dụng:** JDBC, Spring JDBC/JPA, transaction, connection pool.
- **Cấu trúc Oracle:** schema, tablespace, CDB/PDB, user/role, service name, listener.
- **DBA/chuyên sâu:** Data Pump, RMAN, flashback, tuning, partitioning, replication, high availability.

Đối chiếu **từng tính năng cần dùng** với tài liệu của release và edition. Các chức năng quản trị/chuyên sâu có thể cần quyền SYSDBA, thành phần không có trong Lite, dịch vụ cloud phù hợp hoặc edition được cấp phép. Không dùng việc một câu lệnh SQL chạy được để kết luận mọi chức năng DBA đều được hỗ trợ.

### Bước 2 — Xác định yêu cầu tương thích

Nếu đề bài/đội dự án nói rõ `Oracle 19c`, cú pháp của 19c và hành vi tương ứng là tiêu chí chính. Nếu bài dành cho một hệ thống doanh nghiệp đã tồn tại, hãy hỏi release/patch level của môi trường đích và cách quản lý schema.

Nếu không có ràng buộc tương thích, ưu tiên release Free hiện hành và tài liệu đi kèm để tránh đầu tư công sức vào môi trường cũ. Việc đổi release phải được xem như một quyết định tương thích có chủ đích, đặc biệt khi bài có SQL nâng cao, JDBC driver hoặc script của DBA.

### Bước 3 — So edition và điều kiện cấp phép

Với bài cơ bản, Free thường đủ để học. Với chức năng yêu cầu SE2/EE hoặc các quyền cụ thể, phải xác minh danh sách tính năng và **quyền sử dụng** qua tài liệu Oracle Licensing cho release đó. “Có thể tải installer” không có nghĩa được phép sử dụng mọi tính năng cho mọi mục đích.

Oracle nêu rằng **AI Database Free không đi kèm hỗ trợ Oracle Support và không nhận bản vá, kể cả bản vá bảo mật**. Vì vậy dùng Free cho lab cô lập, demo và phát triển nhỏ là một lựa chọn thực tế; môi trường có yêu cầu vận hành/an ninh lâu dài nên dùng dịch vụ hoặc edition có hỗ trợ phù hợp.

### Bước 4 — Chọn kiểu chạy dựa vào máy và quyền quản trị

`Nhu cầu chạy SQL nhưng không có quyền cài` → Live SQL.  
`Cần một database riêng và dễ tạo lại` → Free container.  
`Cần tác vụ hệ điều hành/listener/file Oracle` → Cài trực tiếp hoặc VM được chuẩn bị đúng mục tiêu.  
`Máy yếu nhưng cần kết nối từ app` → Database trên OCI/máy chủ lab, bảo đảm mạng và quyền truy cập.  
`Cần tính năng thương mại` → Môi trường SE2/EE được cấp sẵn và xác nhận quyền sử dụng.

### Bước 5 — Xác nhận đầu ra có thể kết nối được

Trước khi kết luận môi trường phù hợp, cần biết:

1. Host và port của listener.
2. **Service name của PDB** dùng cho bài; đừng chỉ ghi một SID phỏng đoán.
3. User/schema dành riêng cho người học và quyền cần thiết.
4. Cách lưu dữ liệu qua lần restart, cách dọn lại lab và cách xuất/nhập dữ liệu khi đổi máy.

Một môi trường chỉ mới “container đang chạy” nhưng ứng dụng không đăng nhập được vào PDB vẫn chưa sẵn sàng để thực hành.

## 5. Ví dụ lựa chọn theo tình huống

### Tình huống A — Học SQL trên laptop 4 GB RAM

**Đề:** viết `CREATE TABLE`, `INSERT`, `SELECT`, `JOIN` và `GROUP BY`. Không yêu cầu Java truy cập máy chủ, không yêu cầu tạo tablespace.

**Chọn:** Oracle Live SQL. Người học chỉ cần trình duyệt và một phiên làm việc; không phải chạy engine Oracle cục bộ. Cần lưu lại script và kết quả riêng vì khả năng lưu trữ, dữ liệu mẫu, quyền schema phụ thuộc dịch vụ.

**Không phù hợp cho bài này:** biến bài SQL thành bài cài VM nhiều GB hoặc giả định có quyền `SYSDBA` trên Live SQL.

### Tình huống B — Học Java JDBC/Spring trên laptop 8 GB RAM

**Đề:** ứng dụng CRUD dùng Oracle, tạo bảng và transaction, chạy đi chạy lại test tích hợp. Có thể cài Docker/Podman.

**Chọn:** Oracle AI Database 26ai Free **Full** trong container, tạo volume lưu dữ liệu, mở listener cho localhost, sử dụng một user/schema riêng. Chọn version JDBC driver tương thích với JDK và Oracle server theo tài liệu driver, rồi cấu hình URL đúng PDB.

**Lưu ý:** đánh giá RAM tổng khi chạy cả JVM/IDE/container; đừng tăng `-Xmx` của JVM hoặc cấu hình container mà không xem RAM còn lại của host.

### Tình huống C — Lab quản trị backup bằng RMAN

**Đề:** backup database, khôi phục và quan sát file/database process.

**Chọn:** Free **Full** trong một VM hoặc container có cách quản lý file/bản sao lưu phù hợp, sau khi xác minh từng thao tác RMAN mà bài yêu cầu. **Không chọn Lite** cho lab RMAN vì tài liệu image liệt kê RMAN trong nhóm không hỗ trợ.

**Lưu ý:** cần nhiều dung lượng hơn mức phục vụ user data, thêm không gian backup/restore. Bài về Oracle RAC, Data Guard hoặc tính năng EE cụ thể phải được đối chiếu riêng; không tự coi Free đủ chỉ vì cùng tên Oracle.

### Tình huống D — Nhóm phải sửa ứng dụng chạy trên Oracle 19c

**Đề:** khắc phục câu lệnh SQL/PLSQL của một hệ thống đang dùng 19c.

**Chọn:** môi trường kiểm thử 19c do nhóm được cấp quyền, có schema và patch level đại diện cho hệ thống đích. Có thể dùng 26ai Free để thử ý tưởng độc lập, nhưng **kết quả trên 26ai không thay cho kiểm thử tương thích 19c**.

## 6. Thử nhanh một phương án local: Oracle 26ai Free Full

Ví dụ dưới đây minh họa một cấu hình lab với **Podman trên môi trường Bash**. Cần Podman đã được cài và có đủ tài nguyên; nếu dùng Docker hoặc hệ điều hành khác, thực hiện theo hướng dẫn image tương ứng của Oracle. Mục đích là chỉ ra các thành phần phải xác định khi chọn bản Oracle: **image, dữ liệu bền vững, mật khẩu, port và service**.

### 6.1. Khởi tạo container

```bash
# Chạy trên máy dùng Bash + Podman; chọn mật khẩu mạnh cho lab.
read -r -s -p "Mật khẩu quản trị Oracle: " DB_PASSWORD
printf '\n'
printf '%s' "$DB_PASSWORD" | podman secret create oracle_pwd -
unset DB_PASSWORD

podman run -d \
  --name oracle-lab \
  --publish 127.0.0.1:1521:1521 \
  --secret oracle_pwd \
  --volume oracle-lab-data:/opt/oracle/oradata \
  container-registry.oracle.com/database/free:latest

# Xem log đến khi database sẵn sàng nhận kết nối.
podman logs -f oracle-lab
```

- `container-registry.oracle.com/database/free:latest`: image **Full** theo tài liệu Oracle Container Registry hiện hành. Ở dự án cần tái hiện kết quả nhiều lần, **pin một tag/digest cụ thể** thay vì để `latest` âm thầm thay đổi.
- `--publish 127.0.0.1:1521:1521`: ánh xạ port 1521 của Oracle vào localhost để phục vụ lab cục bộ; không chủ ý công khai database ra Internet.
- `--volume oracle-lab-data:/opt/oracle/oradata`: dữ liệu không biến mất chỉ vì dừng/xóa container (nhưng xóa volume sẽ làm mất dữ liệu trong volume).
- `--secret oracle_pwd`: chuyển mật khẩu quản trị qua Podman secret; tránh viết mật khẩu trực tiếp vào lệnh và lịch sử shell.

Nếu port 1521 trên host đang được dùng, có thể đổi **port host** thành `1522` trong ánh xạ `127.0.0.1:1522:1521`. Khi đó client nối vào `localhost:1522`, còn listener bên trong container vẫn là 1521.

### 6.2. Kết nối đúng dịch vụ PDB

Với Oracle AI Database 26ai Free mặc định:

| Thành phần | Giá trị thường dùng |
| --- | --- |
| CDB service | `FREE` |
| PDB service đầu tiên | `FREEPDB1` |
| Port listener trong container | `1521` |
| JDBC URL đến PDB từ máy host | `jdbc:oracle:thin:@//localhost:1521/FREEPDB1` |

Trong SQLcl, ví dụ đăng nhập tương tác bằng tài khoản quản trị cho bước **tạo schema học tập**:

```text
sql system@localhost:1521/FREEPDB1
```

SQLcl sẽ yêu cầu nhập mật khẩu. Sau khi đăng nhập, có thể tạo user dành riêng cho lab (thay `<MAT_KHAU_RIENG>` bằng mật khẩu phù hợp):

```sql
CREATE USER lab_student IDENTIFIED BY "<MAT_KHAU_RIENG>"
  QUOTA 200M ON USERS;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW,
      CREATE SEQUENCE, CREATE PROCEDURE TO lab_student;
```

Đăng nhập lại dưới `lab_student` và chạy câu lệnh kiểm tra:

```sql
SELECT USER AS current_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
```

Kết quả mong đợi là user `LAB_STUDENT` và PDB `FREEPDB1` (nếu chưa đổi cấu hình mặc định). Với Java, cấu hình URL và thông tin user này; không dùng tài khoản `SYS` hoặc `SYSTEM` để chạy CRUD thông thường.

> **Vì sao phải chọn PDB?** Các phiên bản Oracle hiện đại thường sử dụng kiến trúc multitenant. `FREE` là dịch vụ của container database (CDB), còn `FREEPDB1` là pluggable database (PDB) nơi schema ứng dụng được tạo cho bài học. Kết nối nhầm CDB root có thể dẫn đến lỗi tạo user, không tìm thấy bảng hoặc thao tác ở sai phạm vi quản trị. Tên service thực tế phải được xác nhận từ môi trường đã cài.

### 6.3. Quản lý vòng đời

```bash
podman stop oracle-lab
podman start oracle-lab
podman ps --filter name=oracle-lab
```

Đối với lab dài ngày, cần có cách sao lưu/export tương ứng với mục tiêu học. **Volume giúp giữ dữ liệu qua việc thay container, nhưng bản thân volume không thay thế một bản backup**. Đặc biệt, các bài thực hành xóa dữ liệu hoặc recovery nên có bản sao độc lập để khôi phục lại trạng thái ban đầu.

## 7. Những sai lầm khi chọn bản Oracle

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Free chỉ dùng 2 GB RAM nên máy 2 GB là đủ.” | 2 GB là giới hạn bộ nhớ database; hệ điều hành, container, SQL client và IDE vẫn cần RAM riêng. |
| “12 GB dữ liệu nghĩa là chỉ cần ổ 12 GB.” | Còn phần mềm/image, system data, temporary files, redo, log, backup và dung lượng build. |
| “Dùng SQL Developer là đã có Oracle server.” | SQL Developer là client, phải kết nối tới database đang chạy ở đâu đó. |
| “Version mới luôn chạy giống 19c.” | Khả năng tương thích và cú pháp phụ thuộc release; phải kiểm thử trên version được yêu cầu. |
| “Container có port 1521 tức ứng dụng nào cũng vào được.” | Còn phải có ánh xạ mạng đúng, database sẵn sàng, service name, user, password và quyền. |
| “Full và Lite như nhau vì cùng Free.” | Lite có thành phần bị lược bỏ; kiểm tra danh sách hỗ trợ trước khi chọn. |
| “Cấp 8 CPU/8 GB cho container sẽ bỏ được giới hạn Free.” | Giới hạn 2 core, 2 GB database RAM và 12 GB user data do edition áp dụng. |
| “Môi trường Free phù hợp mọi hệ thống vận hành.” | Oracle không phát hành bản vá/hỗ trợ như các edition được hỗ trợ; đánh giá yêu cầu bảo mật và SLA. |
| “OCI Always Free và Free local là cùng một cách quản trị.” | Dịch vụ cloud có mô hình vận hành, quyền và hạn mức riêng; bài DBA local không nhất thiết thực hành tương đương. |

## 8. Bài tập ra quyết định

Với mỗi bài dự kiến thực hiện, điền **phiếu chọn môi trường** sau:

```yaml
ten_bai: "Ví dụ: JDBC transaction với Oracle"
bat_buoc:
  release: "Không khóa phiên bản"
  tinh_nang: ["SQL", "transaction", "JDBC"]
  quyen_dba: false
may_thuc_hanh:
  cpu_arch: "x86-64"
  ram_host: "8 GB"
  dia_trong: "35 GB"
  co_the_chay_container: true
lua_chon:
  release: "26ai"
  edition: "Oracle AI Database Free"
  deploy: "Podman container, image Full"
  database_service: "FREEPDB1"
  luu_du_lieu: "Named volume"
ly_do: "Đủ SQL/JDBC; cô lập môi trường; không yêu cầu tác vụ DBA chuyên sâu"
rui_ro_can_kiem_tra:
  - "RAM tổng khi mở IDE và database"
  - "Tag image, quyền truy cập mạng và JDBC driver tương thích"
```

Sau đó tự giải thích ba câu hỏi:

1. Vì sao chọn release/edition này đáp ứng đúng **tính năng bắt buộc** của bài?
2. Vì sao **RAM, CPU, đĩa và quyền cài đặt** của máy đủ cho toàn bộ môi trường, không chỉ riêng engine?
3. Nếu máy quá yếu hoặc lab đòi tính năng không có trong Free/Lite, lựa chọn thay thế là gì và đánh đổi ra sao?

Một quyết định tốt thường ghi đủ **release + edition + cách chạy + tài nguyên host + service name + lý do chọn**. Thông tin này cũng giúp giảng viên hoặc đồng đội tái tạo cùng môi trường khi cần hỗ trợ lỗi.

## Tài liệu Oracle để đối chiếu trước khi cài

- [Oracle AI Database Free – giới thiệu và tài nguyên Free](https://www.oracle.com/database/free/) — release Free hiện hành và tài nguyên.
- [Oracle AI Database Free – Get Started](https://www.oracle.com/database/free/get-started/) — phương thức cài, container image và mẫu kết nối `FREE`/`FREEPDB1`.
- [Oracle Database Free FAQ](https://www.oracle.com/database/free/faq/) — giới hạn, patch/support, migration và công cụ đi kèm.
- [Oracle AI Database 26ai Free – Licensing Restrictions](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/licensing-restrictions.html) — CPU, RAM, kích thước user data và giới hạn môi trường logic.
- [Oracle AI Database 26ai Free – yêu cầu hệ thống Linux](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/requirements.html) và [Windows](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinw/requirements.html) — điều kiện cài đặt theo nền tảng.
- [Oracle Database Docker images](https://github.com/oracle/docker-images/blob/main/OracleDatabase/SingleInstance/README.md) — biến cấu hình, volume, secret và hướng dẫn chạy trong container.

Các đường dẫn và khả năng hỗ trợ có thể thay đổi theo release hoặc tag image. Trước khi chốt môi trường cho một khóa học dài hạn, kiểm tra lại đúng tài liệu của release, edition, kiến trúc máy và tính năng mà bài thực hành sử dụng.
