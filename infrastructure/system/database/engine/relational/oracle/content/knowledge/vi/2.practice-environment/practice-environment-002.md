# Chuẩn bị môi trường thực hành Oracle Database: máy ảo hoặc container, tài nguyên và cổng mạng

Một hệ quản trị cơ sở dữ liệu Oracle không chỉ là một chương trình nhận câu lệnh SQL. Để học và thực hành ổn định, bạn cần một môi trường có đủ bộ nhớ, dung lượng lưu trữ bền vững, một **Oracle Database instance** đang chạy, một **listener** nhận kết nối và một **database service** trỏ đến đúng cơ sở dữ liệu thực hành. Bài này hướng dẫn chuẩn bị từng thành phần trên máy cá nhân bằng **container** hoặc **máy ảo (VM)**.

Mục tiêu sau bài học:

- Phân biệt khi nào nên dùng container, khi nào nên dùng máy ảo cho phòng lab Oracle.
- Dự trù CPU, RAM, dung lượng đĩa và vị trí lưu dữ liệu để tránh lỗi khi cài đặt hoặc khởi động.
- Hiểu tuyến kết nối từ công cụ SQL trên máy chủ đến cổng Oracle listener và service của pluggable database (PDB).
- Tạo một môi trường Oracle Database Free có dữ liệu lưu bền vững, kết nối thử và chạy lệnh SQL đầu tiên.
- Xử lý những lỗi khởi tạo và kết nối thường gặp mà không làm mất dữ liệu thực hành.

> **Phạm vi:** Các ví dụ sử dụng Oracle Database Free trong môi trường học tập, ưu tiên cách chạy bằng Docker. Tên image, phiên bản, service và yêu cầu nền tảng có thể khác nếu bạn chọn một bản Oracle khác. Hãy đối chiếu tài liệu của chính image/bộ cài trước khi thay đổi phiên bản hoặc chuyển sang môi trường thật.

## 1. Hiểu những thành phần sẽ chạy

Trước khi cấp tài nguyên, cần tách biệt các khái niệm thường bị gọi chung là “Oracle database”:

| Thành phần | Vai trò trong phòng lab | Điều cần nhớ |
| --- | --- | --- |
| **Host** | Máy tính vật lý chạy Windows, Linux hoặc macOS | Host phải đủ tài nguyên cho hệ điều hành, Docker/VM và công cụ học tập. |
| **VM/container** | Môi trường chứa phần mềm Oracle Database | VM có hệ điều hành khách riêng; container chia sẻ kernel của môi trường Linux chạy container. |
| **Oracle instance** | Bộ nhớ và các tiến trình phục vụ cơ sở dữ liệu | Instance khởi chạy không đồng nghĩa PDB đã mở và sẵn sàng nhận kết nối. |
| **CDB/PDB** | Cấu trúc multitenant của Oracle: container database và pluggable database | Thực hành tạo bảng/người dùng ứng dụng trong PDB, không nhầm với CDB root. |
| **Listener** | Tiến trình lắng nghe kết nối Oracle Net, thường qua TCP `1521` | Cổng đang mở chỉ chứng tỏ có listener; chưa đảm bảo service tồn tại hoặc DB đã sẵn sàng. |
| **Service name** | Tên dịch vụ khách hàng dùng để chọn database/PDB | Với cấu hình Oracle Database Free 23ai thông dụng: PDB là `FREEPDB1`, còn root service thường là `FREE`. |
| **Volume/đĩa dữ liệu** | Lưu datafiles, redo logs và các tệp Oracle cần tồn tại lâu dài | Không lưu bài thực hành chỉ trong lớp ghi tạm của container. |

Một công cụ như SQL Developer, SQLcl, SQL*Plus hoặc DBeaver kết nối theo bộ thông số cơ bản: **host + cổng TCP + service name + tài khoản + mật khẩu**. Trong bài này, bộ thông số mặc định sau khi chạy container là `127.0.0.1`, `1521`, `FREEPDB1` và tài khoản thực hành được tạo ở phần sau.

## 2. Chọn container hay máy ảo

| Tiêu chí | Container Oracle Database | Máy ảo cài Oracle Database |
| --- | --- | --- |
| Cách triển khai | Chạy image Oracle đã đóng gói; cấu hình qua biến môi trường, volume và port mapping | Cài một hệ điều hành khách, sau đó cài gói Oracle Database tương thích |
| Thời gian chuẩn bị | Thường nhanh hơn khi Docker đã hoạt động và có sẵn image | Nhiều bước hơn: tạo VM, cài OS, cập nhật, cài Database, thiết lập listener |
| Mức quản trị có thể luyện | Quản lý database, SQL, user, schema, dữ liệu; ít phải quản trị OS bên trong | Luyện cả OS, phân vùng/đĩa, dịch vụ hệ thống, firewall, listener và cài đặt Oracle |
| Tài nguyên bổ sung | Cần bộ nhớ cho database và Docker Desktop/VM nền nếu có | Cần RAM/đĩa cho cả OS khách, database và phần mềm ảo hóa |
| Tính di động | Dễ tạo lại từ image và volume; cần giữ tương thích phiên bản dữ liệu | Có thể sao chép VM/snapshot, thường nặng và tốn dung lượng |
| Phù hợp nhất | Bắt đầu học SQL, bảng, transaction, user, PDB, backup cơ bản | Học cài đặt Oracle trên Linux, cấu hình OS/network, quản trị dịch vụ sâu hơn |

**Đề xuất cho bài thực hành đầu tiên:** chọn container nếu máy của bạn hỗ trợ image và Docker chạy ổn định. Chọn VM khi mục tiêu bao gồm quản trị Linux/Oracle ở mức hệ điều hành hoặc image không hỗ trợ kiến trúc CPU đang dùng.

Trên Windows, Docker Desktop thường dùng nền ảo hóa **WSL 2**; vì vậy “chạy container” vẫn tiêu thụ RAM/đĩa qua môi trường Linux nền. Trên máy dùng CPU ARM (đặc biệt Apple Silicon), hãy kiểm tra image có hỗ trợ kiến trúc đó hay không. Không giả định rằng mọi image Oracle `linux/amd64` sẽ chạy ổn định hoặc được hỗ trợ khi giả lập trên ARM.

## 3. Dự trù CPU, RAM và dung lượng

Tài nguyên cần thiết phụ thuộc phiên bản Oracle, image/bộ cài và khối lượng dữ liệu. Bảng dưới là **mức cấp phát tham khảo để học thoải mái**, không phải yêu cầu tối thiểu chính thức của mọi bản Oracle:

| Hạng mục | Container học SQL/PLSQL | VM thực hành quản trị Oracle | Vì sao cần |
| --- | --- | --- | --- |
| CPU | Dự trù khoảng **2 vCPU** cho database | Dự trù **2–4 vCPU** cho VM | Khởi tạo data dictionary, background processes và truy vấn có thể làm CPU tăng đột biến. |
| RAM cấp cho môi trường | Dự trù **4–6 GB** cho Docker/WSL và container; 6–8 GB nếu còn chạy nhiều công cụ | Dự trù **8 GB RAM** cho VM | Phải tính thêm phần dùng bởi OS, runtime và các tiến trình khởi động; bộ nhớ DB được phép sử dụng có thể bị giới hạn riêng. |
| RAM vật lý của host | **8 GB** chỉ phù hợp phòng lab nhẹ; **16 GB trở lên** dễ làm việc hơn | **16 GB trở lên** được khuyến nghị để host và VM cùng hoạt động | Tránh host phải swap liên tục khi mở IDE, trình duyệt, SQL client. |
| Không gian lưu trữ ban đầu | Dành khoảng **25–40 GB** cho image, volume, log và dữ liệu phát sinh | Dành khoảng **60–80 GB** đĩa ảo có khả năng mở rộng | Database tạo nhiều tệp hệ thống ngay cả khi chưa có bảng người dùng. |
| Dung lượng dự phòng | Duy trì ít nhất **10–20 GB trống** ngoài dữ liệu đang dùng, tùy quy mô host | Chừa khoảng trống cho OS update, archive/log, snapshot và backup | Đầy đĩa có thể khiến database không thể ghi log hoặc mở bình thường. |

**Hai giới hạn không được đánh đồng:**

1. **Giới hạn của phiên bản Oracle:** Chẳng hạn, Oracle Database 23ai Free có hạn mức sử dụng tài nguyên ở cấp database (thường được công bố là tối đa 2 CPU, 2 GB RAM cho database và 12 GB dữ liệu người dùng). Hãy kiểm tra giới hạn của bản Free cụ thể đang sử dụng; cấp 8 GB cho VM không làm tăng hạn mức của edition.
2. **Tài nguyên của môi trường chạy:** Container/VM vẫn cần đủ RAM cho runtime, hệ điều hành và quá trình khởi tạo, kể cả khi edition có giới hạn riêng cho database.

Đối với đĩa, phân biệt ba vùng: dung lượng image/bộ cài; dung lượng **datafiles và redo logs**; dung lượng log, tệp tạm, backup/snapshot. Nếu máy gần hết dung lượng, hãy dọn hoặc mở rộng đĩa **trước** khi import dữ liệu mẫu lớn.

### Kiểm tra trước khi cài

- Bật tính năng ảo hóa CPU trong BIOS/UEFI nếu Docker/VM yêu cầu (Intel VT-x hoặc AMD-V).
- Với Windows: bảo đảm WSL 2/Docker Desktop ở trạng thái hoạt động; kiểm tra giới hạn RAM/đĩa của backend nếu đã từng tùy chỉnh.
- Với Linux: bảo đảm Docker Engine và quyền chạy Docker đã được thiết lập; lưu ý quyền vào Docker socket gần tương đương quyền quản trị host.
- Với VM: chọn hệ điều hành và kiến trúc CPU mà bản Oracle định cài **chính thức hỗ trợ**; đĩa ảo dạng tăng trưởng động vẫn cần dung lượng thật khi được ghi đầy.
- Có kết nối mạng đủ tải image hoặc bộ cài; sau lần tải đầu có thể làm việc phần lớn ở máy cục bộ.

## 4. Hiểu cổng mạng và cách ánh xạ

Ví dụ mô hình một container Oracle trên cùng máy với SQL client:

```text
Máy cá nhân (host)
  SQL Developer / DBeaver / SQLcl
      │ 127.0.0.1:1521, service FREEPDB1
      ▼
  Docker: 127.0.0.1:1521  ──publish──►  container:1521
                                               │
                                               ▼
                                         Oracle Listener
                                               │
                                      service FREEPDB1
                                               │
                                               ▼
                                         Oracle PDB
```

`-p 127.0.0.1:1521:1521` nghĩa là **chỉ công bố cổng host trên loopback `127.0.0.1`** và chuyển tiếp tới cổng `1521` trong container. Đây là lựa chọn phù hợp cho lab dùng ngay trên máy cá nhân. Nếu máy đã có một Oracle listener chiếm cổng `1521`, có thể dùng `-p 127.0.0.1:11521:1521`; khi đó SQL client kết nối tới **cổng host `11521`**.

| Cổng | Ý nghĩa | Có cần mở cho bài này? |
| --- | --- | --- |
| **1521/TCP** | Oracle Net listener (thường là giá trị mặc định) | **Có**, để SQL client bên ngoài container/VM truy cập. |
| **11521/TCP** | Ví dụ cổng host thay thế chuyển vào listener `1521` | Chỉ nếu muốn tránh trùng cổng; không phải cổng Oracle bắt buộc. |
| **5500/TCP** | Có thể liên quan giao diện quản trị Enterprise Manager Express ở một số bản/cấu hình | **Không**; không giả định image Oracle Free đang dùng cung cấp giao diện này. |
| **22/TCP** | SSH vào Linux VM | Chỉ cần khi muốn quản trị VM từ xa qua SSH. |

Không mở toàn bộ dải cổng hoặc chuyển `1521` ra Internet chỉ để học SQL. Cấu hình `-p 1521:1521` không chỉ rõ IP host thường có thể lắng nghe trên nhiều giao diện. Khi cần máy khác trong mạng riêng kết nối, phải chủ động giới hạn IP nguồn qua firewall, chọn interface phù hợp và dùng mật khẩu mạnh.

## 5. Cách A — Dựng Oracle Database Free bằng Docker

### 5.1. Chuẩn bị image và volume

Ví dụ sau dùng image cộng đồng `gvenzl/oracle-free` với nhánh tag `23-slim`, phù hợp để minh họa Oracle Database Free 23ai. **Image cộng đồng không đồng nghĩa image chính thức của Oracle**; khi dùng image khác, phải đọc hướng dẫn riêng về biến môi trường, đường dẫn volume, tên PDB và cách kiểm tra readiness. Tag có thể thay đổi theo thời gian.

Mở terminal (PowerShell trên Windows hoặc shell trên Linux/macOS) và kiểm tra Docker:

```powershell
docker version
docker info
```

Phải thấy Docker client liên lạc được với server. Sau đó tải image và tạo một **named volume** giữ datafiles độc lập với vòng đời container:

```powershell
docker pull gvenzl/oracle-free:23-slim
docker volume create oracle-lab-data
```

Named volume `oracle-lab-data` là nơi lưu dữ liệu Oracle. Nếu xóa container nhưng giữ volume, dữ liệu có cơ hội được gắn trở lại với **phiên bản image tương thích**. Volume không thay thế cơ chế backup.

### 5.2. Tạo container có cổng truy cập cục bộ

Chạy ví dụ một dòng để dùng được cả trong PowerShell và shell thông thường:

```powershell
docker run -d --name oracle-lab --restart unless-stopped -p 127.0.0.1:1521:1521 -e ORACLE_PASSWORD="ThayBangMatKhauRieng_2026!" -v oracle-lab-data:/opt/oracle/oradata gvenzl/oracle-free:23-slim
```

Thay giá trị `ORACLE_PASSWORD` bằng **mật khẩu mạnh riêng của bạn** trước khi chạy. Đây là ví dụ cho phòng lab: cách truyền mật khẩu trực tiếp trên dòng lệnh có thể lưu vào history hoặc metadata của container; với môi trường chia sẻ/nhạy cảm, hãy dùng cơ chế secret theo hướng dẫn image và quy định của môi trường. Không lưu mật khẩu vào mã nguồn công khai.

Ý nghĩa các tùy chọn:

| Tùy chọn | Tác dụng |
| --- | --- |
| `-d` | Chạy container ở chế độ nền. |
| `--name oracle-lab` | Gán tên cố định để thao tác log, `exec`, stop/start. |
| `--restart unless-stopped` | Tự khởi động lại khi Docker daemon khởi động, trừ khi đã chủ động dừng. |
| `-p 127.0.0.1:1521:1521` | Chỉ công bố listener ra loopback của host. |
| `-e ORACLE_PASSWORD=...` | Thiết lập mật khẩu khởi tạo theo quy ước của **image đang dùng**. |
| `-v oracle-lab-data:/opt/oracle/oradata` | Gắn volume bền vững vào đường dẫn dữ liệu của image ví dụ. |

Nếu host đang dùng cổng `1521`, đổi riêng đoạn ánh xạ thành `-p 127.0.0.1:11521:1521` **ngay lúc tạo container** và nhớ dùng `11521` trong cấu hình SQL client. Không thể chỉnh tùy chọn `-p` của container đang tồn tại bằng `docker start`; phải tạo lại container với mapping mới và gắn volume đúng cách.

### 5.3. Theo dõi lần khởi động đầu

```powershell
docker ps -a --filter name=oracle-lab
docker logs --tail 100 oracle-lab
```

Lần chạy đầu cần tạo các tệp database và có thể kéo dài hơn những lần chạy sau. Đợi tới khi **log của chính image báo database sẵn sàng**; không suy ra đã sẵn sàng chỉ vì `docker ps` hiện trạng thái `Up`. Khi cần xem log liên tục:

```powershell
docker logs -f oracle-lab
```

Nhấn `Ctrl+C` để ngừng theo dõi log; thao tác này không dừng container. Nếu log thể hiện thiếu bộ nhớ hoặc thiếu dung lượng, sửa giới hạn Docker/ổ đĩa trước khi thử lại; không xóa volume như một bước khắc phục mặc định.

### 5.4. Kiểm tra CDB, PDB bên trong container

Image ví dụ cung cấp SQL*Plus. Vào bằng quyền quản trị cục bộ:

```powershell
docker exec -it oracle-lab sqlplus "/ as sysdba"
```

Từ dấu nhắc `SQL>`, lần lượt chạy:

```sql
SELECT instance_name, status FROM v$instance;
SHOW PDBS;
SELECT name, open_mode FROM v$pdbs;
```

Bạn cần thấy instance hoạt động và PDB `FREEPDB1` có `OPEN_MODE` là `READ WRITE` để thực hành tạo bảng. `SHOW PDBS` cho biết PDB có đang mở hay không; tên PDB và service của phiên bản/image khác có thể không phải `FREEPDB1`.

> **Lưu ý:** Tài khoản `SYS`/quyền `SYSDBA` dùng cho quản trị. Không sử dụng tài khoản này làm tài khoản chạy ví dụ SQL của ứng dụng.

### 5.5. Tạo tài khoản riêng trong PDB

Trong phiên SQL*Plus đang đăng nhập `SYSDBA`, chuyển sang PDB thực hành:

```sql
ALTER SESSION SET CONTAINER = FREEPDB1;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
```

Kết quả `CURRENT_CONTAINER` cần là `FREEPDB1`. Sau đó tạo tài khoản có quyền cơ bản và hạn mức lưu trữ có chủ đích:

```sql
CREATE USER lab_user IDENTIFIED BY "DoiMatKhauRieng_2026!";

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW,
      CREATE SEQUENCE, CREATE PROCEDURE TO lab_user;

ALTER USER lab_user QUOTA 200M ON USERS;
```

Thay mật khẩu ví dụ trước khi chạy. Trong bước này, `CREATE USER` phải thực hiện **trong PDB**, tránh lỗi hoặc tạo nhầm người dùng chung ở CDB root. `QUOTA 200M ON USERS` giới hạn không gian tài khoản có thể sử dụng trong tablespace `USERS`; tablespace mặc định có thể khác nếu bạn đã tùy biến database. Không cấp `DBA` hoặc `UNLIMITED TABLESPACE` chỉ để chạy các ví dụ bảng đơn giản.

Thoát SQL*Plus bằng `EXIT`. Bây giờ có thể đăng nhập từ host bằng SQL client với thông số:

| Trường | Giá trị cho ví dụ |
| --- | --- |
| Connection type | Basic / Oracle Thin (tùy công cụ) |
| Hostname | `127.0.0.1` |
| Port | `1521` (hoặc `11521` nếu đã đổi cổng host) |
| Service name | `FREEPDB1` |
| Username | `LAB_USER` |
| Password | Mật khẩu đã đặt trong `CREATE USER` |

Trong công cụ có lựa chọn **SID** và **Service name**, hãy chọn **Service name**. Đừng nhập `FREEPDB1` vào ô SID nếu chưa có lý do và cấu hình rõ ràng.

Nếu muốn thử SQL*Plus ngay trong container và nhập mật khẩu theo prompt, có thể dùng:

```powershell
docker exec -it oracle-lab sqlplus lab_user@//localhost:1521/FREEPDB1
```

### 5.6. Chạy truy vấn đầu tiên và xác nhận ghi dữ liệu

Đăng nhập bằng `LAB_USER`, sau đó thực hiện:

```sql
SELECT USER AS current_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;

CREATE TABLE lab_ping (
    id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message    VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO lab_ping (message)
VALUES ('Oracle lab is ready');

COMMIT;

SELECT id, message, created_at
FROM lab_ping;
```

Nếu tạo bảng, `INSERT`, `COMMIT` và `SELECT` thành công, đường kết nối, PDB, quyền của người dùng và vùng dữ liệu đều đã hoạt động cho lab SQL cơ bản. Việc `COMMIT` xác nhận transaction; để kiểm tra **lưu bền vững qua restart**, cần thực hiện thêm bước tiếp theo.

### 5.7. Dừng, khởi động lại và kiểm tra dữ liệu còn tồn tại

Thoát SQL client, rồi chạy trên terminal host:

```powershell
docker stop oracle-lab
docker start oracle-lab
docker logs --tail 40 oracle-lab
```

Sau khi log cho biết database sẵn sàng, kết nối lại bằng `LAB_USER` và chạy `SELECT * FROM lab_ping;`. Bản ghi vẫn phải tồn tại do đã `COMMIT` và dữ liệu được lưu trong named volume.

Các lệnh quản lý thường dùng:

```powershell
docker ps -a --filter name=oracle-lab
docker stop oracle-lab
docker start oracle-lab
docker volume ls
```

**Không chạy `docker volume rm oracle-lab-data` hoặc `docker system prune --volumes` khi còn cần dữ liệu.** Xóa container và xóa volume là hai thao tác khác nhau; đặc biệt, xóa volume có thể mất toàn bộ database và bài thực hành. Trước khi nâng phiên bản image, cần kiểm tra tương thích database/datafiles và có bản backup phù hợp. Snapshot đĩa hoặc sao chép tùy tiện các tệp đang được database ghi không thay thế quy trình backup nhất quán.

## 6. Cách B — Chuẩn bị máy ảo Oracle Linux

Nếu mục tiêu là tự cài đặt Oracle trên hệ điều hành, hãy dùng VM với một bản **Oracle Linux x86-64 được phiên bản database lựa chọn hỗ trợ**. Quy trình khái quát:

1. Chọn VirtualBox, VMware hoặc nền tảng ảo hóa tương đương; kiểm tra host đã bật ảo hóa và có đủ tài nguyên.
2. Tạo VM Linux 64-bit, dự trù 2–4 vCPU, khoảng 8 GB RAM và đĩa ảo khoảng 60–80 GB cho phòng lab nhỏ. Không cấp quá nhiều RAM khiến host thiếu bộ nhớ.
3. Cài hệ điều hành, cập nhật gói và kiểm tra hostname, DNS, đồng hồ hệ thống cùng dung lượng phân vùng lưu dữ liệu.
4. Tải và cài **bản Oracle Database Free hoặc edition phù hợp**, theo hướng dẫn chính thức ứng với đúng cặp phiên bản Oracle/OS. Tên package, script cấu hình, đường dẫn cài đặt và service thay đổi theo phiên bản; không trộn lệnh cài đặt của Oracle XE cũ với Oracle Free mới.
5. Tạo/cấu hình database và PDB, xác nhận Oracle instance, listener cùng database service đang hoạt động.
6. Chọn mô hình mạng NAT hoặc Bridged, cấu hình firewall đúng phạm vi và kết nối thử từ SQL client của host.

### NAT và Bridged khác nhau thế nào?

| Chế độ | Cách kết nối từ host | Khi nên dùng |
| --- | --- | --- |
| **NAT + port forwarding** | Ví dụ host `127.0.0.1:11521` chuyển vào **IP/cổng `1521` của guest** | Muốn cô lập VM khỏi mạng LAN và chỉ thao tác trên máy đang học. |
| **Bridged adapter** | VM có IP trong mạng LAN, SQL client kết nối `IP_VM:1521` | Muốn các máy trong cùng LAN truy cập lab, có kiểm soát firewall. |
| **Host-only** (nếu nền tảng hỗ trợ) | Host và VM giao tiếp qua mạng ảo riêng | Muốn mạng kín giữa host và VM, không cần thiết bị LAN khác truy cập. |

Ví dụ tuyến NAT:

```text
SQL client trên host: 127.0.0.1:11521
                │
                ▼
  Port forwarding của VM: host 11521 → guest 1521
                │
                ▼
    Listener trong VM: TCP 1521
                │
                ▼
           Service FREEPDB1
```

Với NAT, bạn phải khai báo port forwarding tại cấu hình **network của phần mềm VM**; cài Oracle trong guest không tự tạo quy tắc forwarding. Với Bridged, kiểm tra IP thực tế của guest (ví dụ qua `ip addr`) và quy tắc firewall của Linux. Khi dùng hai lớp mạng, chẳng hạn Docker chạy **bên trong** VM, phải thông tuyến cả Docker port mapping và mạng của VM.

Trong Linux guest, các lệnh chẩn đoán hữu ích sau khi database đã cài đúng cách gồm:

```bash
ip addr
ss -lnt
lsnrctl status
```

`lsnrctl status` báo listener và các service đang đăng ký; nếu listener chạy nhưng chưa thấy service mong muốn, cần kiểm tra instance/PDB và quá trình service registration. Không tự ý tắt toàn bộ firewall. Chỉ cho phép cổng `1521/TCP` từ những địa chỉ thực sự cần truy cập, theo cách cấu hình firewall của bản Linux đang dùng.

## 7. Kiểm tra kết nối theo từng lớp

Khi SQL client báo lỗi, hãy kiểm tra từ ngoài vào trong, thay vì đổi ngẫu nhiên hostname, SID hoặc mật khẩu:

**Lớp 1 — Môi trường chạy:** Container phải tồn tại và chạy (`docker ps -a`, `docker logs`), hoặc VM phải bật và Oracle service đã được khởi động. Kiểm tra RAM/đĩa trống nếu tiến trình tự thoát.

**Lớp 2 — TCP:** Từ máy host Windows, có thể chạy:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 1521
```

Với host Linux có `nc`, có thể dùng:

```bash
nc -vz 127.0.0.1 1521
```

Nếu đã dùng host port `11521`, thay số `1521` ở lệnh kiểm tra bằng `11521`. Kết quả TCP thành công chỉ chứng minh có đường đi đến cổng listener, **chưa** chứng minh tài khoản hoặc PDB đúng.

**Lớp 3 — Listener và service:** Trong container/guest, kiểm tra `lsnrctl status` và `SHOW PDBS` khi cần. Đối chiếu service name (`FREEPDB1`) với service thực có ở database đang chạy.

**Lớp 4 — Xác thực và schema:** Đăng nhập bằng `LAB_USER`, xác nhận `SYS_CONTEXT('USERENV', 'CON_NAME')`, sau đó chạy `SELECT` đơn giản và thử ghi một hàng dữ liệu.

### Các tình huống thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý có thứ tự |
| --- | --- | --- |
| Docker báo `port is already allocated` | Host port `1521` đang được dùng | Kiểm tra chương trình đang nghe cổng; nếu cần, tạo lại container với `127.0.0.1:11521:1521`, rồi kết nối qua `11521`. |
| Container thoát hoặc restart liên tục | Thiếu RAM, thiếu đĩa, quyền volume, image/CPU không tương thích, lỗi khởi tạo | Đọc `docker logs`; kiểm tra giới hạn Docker/WSL, dung lượng còn trống và kiến trúc image trước khi can thiệp dữ liệu. |
| `ORA-12541: TNS:no listener` (hoặc thông báo tương đương) | Sai host/port, listener chưa chạy, firewall hoặc forwarding lỗi | Kiểm tra địa chỉ/cổng và kết nối TCP; tiếp theo xem trạng thái listener. |
| `ORA-12514`: listener không biết service được yêu cầu | Sai service name hoặc database/PDB chưa đăng ký/mở | Xem service thực tế qua `lsnrctl status`, trạng thái PDB qua `SHOW PDBS`; sử dụng đúng service. |
| `ORA-01017`: invalid username/password | Nhập sai tài khoản/mật khẩu, có thể nhầm cấu hình PDB | Dùng đúng `LAB_USER` và mật khẩu đã tạo; kiểm tra service hướng tới PDB đúng; lưu ý mật khẩu có phân biệt hoa/thường. |
| `ORA-28000`: account is locked | Tài khoản bị khóa sau nhiều lần đăng nhập sai hoặc do chính sách | Dùng tài khoản quản trị kiểm tra nguyên nhân và thực hiện mở khóa theo chính sách lab; không khắc phục bằng việc cấp quyền quản trị rộng. |
| `ORA-01950`: no privileges on tablespace | User chưa có quota trên tablespace lưu bảng | Kiểm tra tablespace đang dùng; cấp quota phù hợp trong PDB, ví dụ `ALTER USER ... QUOTA 200M ON USERS`. |
| `ORA-01109: database not open` hoặc PDB không `READ WRITE` | Database/PDB chưa mở hoặc khởi tạo chưa xong | Đợi readiness, kiểm tra log và `SHOW PDBS`; nếu cần xử lý trạng thái database bằng quyền quản trị. |
| Sau restart không thấy bảng | Kết nối nhầm PDB/schema, quên `COMMIT`, dùng volume khác hoặc đã xóa dữ liệu | Kiểm tra `USER`, `CON_NAME`, tên volume đang gắn và lệnh `COMMIT`; không xóa môi trường để thử lại. |

**Phân biệt lỗi:** `ORA-12541` thường thuộc kết nối đến listener; `ORA-12514` thường thuộc việc chọn service; `ORA-01017` thuộc xác thực; `ORA-01950` thuộc quota lưu trữ. Phân lớp như vậy giúp sửa đúng nguyên nhân mà không phải cài lại database.

## 8. An toàn và khả năng khôi phục trong phòng lab

Ngay cả với database chỉ chạy trên laptop, nên có một số thói quen quản trị:

- **Giới hạn phạm vi truy cập:** ưu tiên bind `127.0.0.1` cho container cục bộ; với VM, chỉ mở cổng cần thiết trên mạng riêng.
- **Tách tài khoản:** giữ `SYS`/`SYSTEM` cho quản trị và dùng tài khoản riêng có quyền hạn vừa đủ cho ví dụ SQL.
- **Bảo vệ mật khẩu:** không dùng mật khẩu mẫu trong tài liệu, không đưa mật khẩu vào Git hoặc ảnh chụp cấu hình; đổi mật khẩu nếu lỡ công khai.
- **Giữ dữ liệu:** dùng named volume/đĩa ảo có kế hoạch sao lưu; ghi rõ image version, tên volume, cổng host, tên PDB và user để dựng lại kết nối.
- **Không coi volume/snapshot là backup đầy đủ:** cần quy trình backup Oracle nhất quán nếu dữ liệu quan trọng. Khi thay đổi edition, phiên bản major hoặc kiến trúc môi trường, hãy xác nhận đường nâng cấp/di chuyển tương thích.
- **Quản lý tài nguyên:** theo dõi dung lượng trống và mức RAM/CPU trước khi import dữ liệu hoặc bật thêm công cụ phân tích nặng.

Bạn có thể ghi một phiếu cấu hình lab đơn giản như sau (không ghi mật khẩu thật):

```yaml
lab_name: oracle-local
runtime: docker
database_edition: Oracle Database Free
image_example: gvenzl/oracle-free:23-slim
container_name: oracle-lab
volume_name: oracle-lab-data
host: 127.0.0.1
host_port: 1521
container_port: 1521
service_name: FREEPDB1
practice_user: LAB_USER
```

## 9. Kết quả cần đạt trước khi học SQL sâu hơn

Hãy coi môi trường chuẩn bị xong khi có đủ bằng chứng sau:

1. Container hoặc VM khởi động được, không còn lỗi khởi tạo trong log.
2. Tài nguyên đã cấp phát hợp lý, đĩa còn chỗ trống và dữ liệu nằm trên volume/đĩa bền vững.
3. Listener nhận kết nối qua đúng host port và service thực hành `FREEPDB1` (hoặc service tương ứng phiên bản đang dùng) hoạt động.
4. Tài khoản `LAB_USER` truy cập đúng PDB, có thể `CREATE TABLE`, `INSERT`, `COMMIT`, `SELECT` mà không cần quyền `SYSDBA`.
5. Sau khi dừng và khởi động lại môi trường, có thể kết nối lại và đọc được hàng dữ liệu đã ghi.

Khi năm điều kiện này được đáp ứng, bạn đã có nền tảng ổn định để học mô hình quan hệ Oracle, DDL/DML, transaction, index, PL/SQL và các bài quản trị ở những phần tiếp theo.
