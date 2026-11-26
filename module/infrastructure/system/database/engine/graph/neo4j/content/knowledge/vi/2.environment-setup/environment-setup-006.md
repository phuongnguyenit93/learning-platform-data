# Cấu trúc thư mục cấu hình, dữ liệu, nhật ký và phần mở rộng

## 1. Mục tiêu của bài học

Neo4j là hệ quản trị cơ sở dữ liệu đồ thị theo mô hình **property graph**. Thông tin được mô hình hóa bằng **node**, **relationship** có hướng và **property**; ngôn ngữ **Cypher** cho phép truy vấn quan hệ và đường đi giữa các node. Để làm việc hiệu quả với Neo4j trong ứng dụng Java, Spring Data Neo4j, khi nhập CSV, tạo index/constraint hoặc vận hành cơ sở dữ liệu, bạn phải biết **file và thư mục nào có chức năng gì**.

Trong chương **Khởi tạo môi trường**, bài này giải thích cấu trúc thư mục khi cài Neo4j trực tiếp trên máy, bằng các gói hệ điều hành, trong Neo4j Desktop và trong Docker. Ta sẽ dùng cấu trúc đó để xác định đúng nơi lưu cấu hình, database, transaction log, nhật ký vận hành, dữ liệu nhập và plugin.

Sau bài học, bạn có thể:

1. Nhận diện ý nghĩa các thư mục `bin`, `conf`, `data`, `logs`, `import`, `plugins`, `labs`, `products` và `lib`.
2. Phân biệt **transaction log** trong vùng dữ liệu với **log chẩn đoán** ở `logs`.
3. Tìm đường dẫn cấu hình theo kiểu cài đặt và kiểm tra các đường dẫn thực tế mà Neo4j đang dùng.
4. Chạy một instance Neo4j bằng Docker Compose với **persistent volume cho dữ liệu/log**, **bind mount chỉ đọc cho CSV** và nơi đặt plugin tùy chọn.
5. Xử lý lỗi về quyền truy cập, plugin không tương thích, CSV không đọc được, thiếu dung lượng hoặc thay container mất dữ liệu.

> **Phạm vi:** Tên đường dẫn và setting minh họa theo dòng Neo4j 5.x/2026.x; ví dụ Docker dùng `neo4j:2026.10.2`. Các bản cũ, edition hoặc phương thức cài khác có thể có bố cục riêng. **Không chỉnh sửa trực tiếp file nội bộ của database đang chạy**; thao tác với dữ liệu phải qua Cypher hoặc công cụ quản trị Neo4j đúng phiên bản.

## 2. Bản đồ thư mục: hiểu từ mục đích sử dụng

Với bản Neo4j Server tải dạng ZIP/TAR, `<NEO4J_HOME>` là thư mục gốc sau khi giải nén. Cấu trúc khái quát:

~~~text
<NEO4J_HOME>/
├── bin/                   # neo4j, neo4j-admin, cypher-shell
├── conf/                  # neo4j.conf, neo4j-admin.conf, *-logs.xml
├── data/                  # database, system database, transaction logs, dumps...
│   ├── databases/         # Nội bộ database; không sửa bằng tay
│   └── transactions/      # Transaction logs theo database (mặc định)
├── import/                # Tệp CSV dùng khi LOAD CSV từ file:///
├── logs/                  # Log vận hành, debug, truy vấn nếu bật
├── plugins/               # Plugin JAR, procedures/functions tự bổ sung
├── labs/                  # Một số plugin đi kèm như APOC Core
├── products/              # Các sản phẩm/tính năng bổ sung đi kèm, tùy edition
├── lib/                   # Thư viện JAR mà Neo4j cần để chạy
├── licenses/              # License file khi có yêu cầu
├── metrics/               # Metric file, tùy edition/cấu hình
└── run/                   # Thông tin tiến trình/PID
~~~

Sơ đồ trên là **bản đồ khái niệm**, không phải cam kết mọi thư mục/file đều xuất hiện trong mọi edition và phiên bản. Neo4j có thể tạo thêm thư mục như `web`, `ssl` hoặc thay đổi thành phần nội bộ giữa các release.

| Thư mục | Công dụng chính | Quyền tối thiểu thường cần | Có nên thao tác trực tiếp? |
| --- | --- | --- | --- |
| `bin` | Khởi động DBMS và công cụ quản trị | Đọc, thực thi | Chạy công cụ; không sửa binary |
| `conf` | Cấu hình DBMS/Log4j | Đọc; quyền sửa của quản trị viên | **Có**, sau khi hiểu setting và quy trình khởi động lại |
| `data` | Store dữ liệu và metadata hệ thống | Đọc, ghi cho tiến trình Neo4j | **Không chỉnh file nội bộ bằng tay** |
| `logs` | Log vận hành/chẩn đoán | Đọc, ghi | Có thể đọc/tập hợp log; xoay vòng theo cấu hình |
| `import` | Dữ liệu nguồn nhập vào | Neo4j cần đọc | **Có**, có thể đặt CSV theo nhu cầu |
| `plugins` | Plugin JAR tự bổ sung | Neo4j đọc | Có, nhưng chỉ thêm plugin đúng phiên bản/nguồn tin cậy |
| `labs`, `products` | Các gói bổ trợ đi kèm bản phân phối | Đọc | Chỉ sao chép/cài theo hướng dẫn plugin |
| `lib` | Thư viện runtime lõi của server | Đọc | Không thêm JAR tùy tiện |
| `licenses` | Tệp giấy phép cần thiết (nếu có) | Đọc | Chỉ quản lý theo cơ chế license chính thức |
| `metrics`, `run` | Metric/tiến trình trong vận hành | Theo chức năng | Không chỉnh/xóa tùy tiện |

**Hai nguyên tắc cần nhớ:**

- **Cấu hình, dữ liệu và nhật ký có vòng đời khác nhau.** Khi nâng cấp image/server, thường cần giữ dữ liệu và backup; cấu hình phải được đối chiếu với bản mới; log có chính sách lưu giữ riêng.
- **Thư mục trên host không nhất thiết giống thư mục trong container.** Docker có thể gắn một volume đặt tên vào `/data`; thư mục ứng dụng Java trên host không thể suy ra đường dẫn thật của volume đó.

## 3. Vị trí mặc định phụ thuộc phương thức cài đặt

### 3.1. Bảng đối chiếu đường dẫn

| Thành phần | ZIP/TAR Linux, macOS | Windows ZIP | Debian/RPM package | Docker |
| --- | --- | --- | --- | --- |
| Executable | `<NEO4J_HOME>/bin` | `<NEO4J_HOME>\bin` | `/usr/bin` | Trong image, gọi qua `docker exec` |
| Cấu hình | `<NEO4J_HOME>/conf` | `<NEO4J_HOME>\conf` | `/etc/neo4j` | `/conf` trong container |
| Dữ liệu | `<NEO4J_HOME>/data` | `<NEO4J_HOME>\data` | `/var/lib/neo4j/data` | `/data` |
| Log | `<NEO4J_HOME>/logs` | `<NEO4J_HOME>\logs` | `/var/log/neo4j`, `journalctl` cho log service | `/logs` và `docker logs` |
| CSV import | `<NEO4J_HOME>/import` | `<NEO4J_HOME>\import` | `/var/lib/neo4j/import` | `/import` |
| Plugin JAR | `<NEO4J_HOME>/plugins` | `<NEO4J_HOME>\plugins` | `/var/lib/neo4j/plugins` | `/plugins` |
| APOC đi kèm | `<NEO4J_HOME>/labs` | `<NEO4J_HOME>\labs` | `/var/lib/neo4j/labs` | Thư mục `labs` trong image |

**Neo4j Desktop:** thay vì đoán thư mục trong `AppData`, `Library` hay home directory, hãy chọn **DBMS instance** đang hoạt động, mở **Open → Terminal** (tên mục có thể khác theo phiên bản Desktop), rồi truy cập `conf`, `data`, `logs` hoặc `plugins` từ terminal của chính instance đó. Một máy có thể có nhiều DBMS do Desktop quản lý, mỗi DBMS có vị trí riêng.

**Neo4j AuraDB:** hệ thống chạy trên hạ tầng do dịch vụ quản lý, vì thế bạn **không có quyền mở trực tiếp `data`, `conf` hay `plugins` trên máy chủ** như với bản tự vận hành. Sử dụng Aura Console, cấu hình dịch vụ, công cụ truy vấn và API được cung cấp theo tier.

> **Lưu ý phiên bản:** Trong Neo4j Community Edition từ 2026.02.3, một thư mục `web` có thể chứa gói Neo4j Browser; cách đóng gói Browser khác nhau giữa Community/Enterprise. Đây là phần phân phối giao diện, không phải thư mục chứa node/relationship.

### 3.2. Tìm đường dẫn từ DBMS, không đoán theo máy

Nếu bạn có quyền xem setting, chạy trong Neo4j Browser hoặc Cypher Shell:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name STARTS WITH 'server.directories.'
RETURN name, value
ORDER BY name;
~~~

Truy vấn giúp xác nhận cấu hình đường dẫn mà Neo4j nhận biết. Một số setting/quyền `SHOW SETTINGS` phụ thuộc phiên bản và edition; nếu lệnh không được cấp quyền, hỏi người quản trị hoặc đọc file cấu hình được phép. Không sửa tệp bên trong database chỉ để tìm nơi lưu.

Trên Linux cài bằng package, có thể kiểm tra file cấu hình bằng lệnh **chỉ đọc**:

~~~bash
# Neu duoc cap quyen doc
ls -l /etc/neo4j
ls -ld /var/lib/neo4j/data /var/log/neo4j
~~~

Với Docker, xem các đường dẫn đã gắn:

~~~bash
docker compose ps
docker compose exec neo4j sh -c 'ls -ld /conf /data /logs /import /plugins'
~~~

Các lệnh được dùng trên **môi trường lab** bạn sở hữu; một số image/permission có thể không cho liệt kê toàn bộ thư mục. Nếu cần xem mount của container từ host, dùng `docker inspect` thay vì tìm vị trí ẩn của volume trong thư mục Docker Engine.

## 4. Thư mục `conf`: quản lý cấu hình đúng cách

### 4.1. Các file quan trọng

| File | Chức năng |
| --- | --- |
| `neo4j.conf` | File cấu hình chính: network, bộ nhớ, đường dẫn, bảo mật và các setting khác |
| `neo4j-admin.conf` | Cấu hình dành cho các lệnh quản trị được hỗ trợ |
| `user-logs.xml` | Cấu hình Log4j cho user log, chẳng hạn `neo4j.log` |
| `server-logs.xml` | Cấu hình Log4j cho `debug.log`, query/security/http logs theo edition/setting |

File cấu hình có thể chứa đường dẫn, hostname, cấu hình bảo mật, tài nguyên, log. **Không đưa password/token trực tiếp vào file được commit**. Chỉ thay đổi setting đã kiểm tra trong tài liệu Neo4j của đúng phiên bản.

### 4.2. Ví dụ các setting đường dẫn

Trong bản Server native, một số setting khả dụng:

~~~properties
# Vi du cac setting duong dan cua Neo4j 5.x/2026.x
server.directories.data=data
server.directories.logs=logs
server.directories.import=import
server.directories.plugins=plugins
server.directories.transaction.logs.root=data/transactions
server.directories.dumps.root=data/dumps
~~~

Đây là **giá trị minh họa để hiểu tên setting**, không phải yêu cầu dán nguyên khối vào mọi `neo4j.conf`. Với gói Debian/RPM, hệ thống đã có bố cục đường dẫn tương ứng. Đổi `server.directories.data` sang thư mục mới mà không chuyển dữ liệu đúng quy trình có thể làm Neo4j khởi động với database khác hoặc báo lỗi.

**Transaction log** được tách qua setting `server.directories.transaction.logs.root`; mặc định nằm trong vùng `data/transactions`. **Dump** (nếu tạo bằng công cụ quản trị) có root riêng; đừng xem cả `data` như một folder có thể tùy ý đổi tên khi database đang chạy.

### 4.3. Biến môi trường trong Docker

Neo4j Docker hỗ trợ chuyển tên setting thành biến môi trường. Quy tắc thường dùng:

- Tiền tố `NEO4J_`.
- Dấu chấm `.` của setting → một dấu gạch dưới `_`.
- Dấu gạch dưới `_` trong tên setting → hai dấu gạch dưới `__`.

Ví dụ:

~~~yaml
environment:
  NEO4J_server_memory_heap_initial__size: "512m"
  NEO4J_server_memory_heap_max__size: "512m"
  NEO4J_server_memory_pagecache_size: "512m"
~~~

Tương ứng các setting `server.memory.heap.initial_size`, `server.memory.heap.max_size`, `server.memory.pagecache.size`. Các giá trị chỉ là điểm khởi đầu của **lab nhỏ**, không phải sizing production. Theo tài liệu Docker Neo4j, khi cấu hình bằng environment variable, giá trị đó có độ ưu tiên cao hơn giá trị tương ứng trong `/conf`.

### 4.4. Cẩn thận khi bind mount `/conf`

Thêm mount kiểu:

~~~yaml
volumes:
  - ./conf:/conf:ro
~~~

sẽ khiến thư mục `/conf` do bạn cung cấp **thay thế** bộ file cấu hình từ image. Một thư mục rỗng hoặc thiếu file `neo4j.conf`/Log4j phù hợp có thể khiến container không chạy đúng. Muốn dùng `/conf` tùy chỉnh, phải có **bộ cấu hình đầy đủ, đúng phiên bản**; tài liệu Neo4j hướng dẫn dùng lệnh `dump-config` của image để lấy bộ config ban đầu rồi chỉnh sửa. Khi tự cung cấp cấu hình network của Docker, kiểm tra `server.default_listen_address=0.0.0.0` để service lắng nghe trong container.

Trong lab, khi chỉ đổi vài setting, dùng **biến môi trường** sẽ rõ ràng và dễ kiểm soát hơn. Ở production, cấu hình nên được quản lý phiên bản, so sánh khi nâng cấp và tách credential khỏi các file thông thường.

## 5. Thư mục `data`: nơi giữ đồ thị và tính nhất quán

### 5.1. Những gì nằm trong `data`?

Theo mặc định, `data` gồm **database stores**, metadata liên quan, hệ thống user (trong database hệ thống), transaction logs và những file/directory nội bộ Neo4j cần dùng. Khi bạn thực thi:

~~~cypher
MERGE (person:Person {personId: 'directory-lab-001'})
  ON CREATE SET person.name = 'An'
RETURN person;
~~~

Neo4j lưu node, label, property và cấu trúc liên quan vào **store files** dưới `data`; chúng không phải các file `.json` hay `.csv` độc lập cho từng node. Khi tạo relationship, index hoặc constraint, dữ liệu/metadata sẽ được cập nhật trong các cấu trúc nội bộ thích hợp.

**Không sửa, di chuyển hoặc xóa thủ công file database khi DBMS đang chạy.** Cấu trúc bên trong `data/databases` có thể thay đổi giữa các phiên bản. Muốn thay đổi nội dung graph, dùng Cypher và transaction; muốn di chuyển/khôi phục database, dùng công cụ `neo4j-admin`, backup/restore hoặc quy trình migration đúng edition/phiên bản.

### 5.2. Transaction log khác `debug.log` ở đâu?

| Đặc điểm | **Transaction logs** | **Nhật ký vận hành `logs`** |
| --- | --- | --- |
| Nơi lưu mặc định | `data/transactions/<database>` | `logs` |
| Mục đích | Ghi nhận thay đổi giao dịch, hỗ trợ bảo đảm nhất quán/khôi phục | Giúp theo dõi startup, lỗi, hoạt động và hiệu năng |
| Có tác động tới khôi phục database? | **Có**; là thành phần hệ thống cơ sở dữ liệu | Không thể dùng một mình để khôi phục nội dung graph |
| Có thể đọc tùy ý bằng editor? | Không phải định dạng log văn bản thông thường | Có thể đọc bằng công cụ phù hợp |
| Có thể xóa khi muốn giải phóng ổ đĩa? | **Không xóa thủ công** | Quản lý bằng log rotation/retention, không xóa bừa |

Giao dịch tạo node/relationship, index hoặc constraint được Neo4j theo dõi để duy trì tính nhất quán. Nếu `data` bị mất hoặc transaction logs bị can thiệp, việc chỉ còn `neo4j.log` **không** giúp tái dựng toàn bộ database.

### 5.3. Volume không phải backup

Gắn `/data` vào Docker named volume giúp dữ liệu tồn tại sau khi container bị thay thế. Nó **không** chống lại xóa volume, lỗi ổ đĩa, lỗi ứng dụng hoặc thao tác Cypher xóa nhầm.

- **Persistence:** giữ data store ngoài writable layer của container.
- **Backup:** tạo bản sao nhất quán theo công cụ/edition được Neo4j hỗ trợ.
- **Restore:** thử khôi phục bản backup trong môi trường tách biệt.
- **Migration/upgrade:** kiểm tra tương thích store và phiên bản trước khi đổi image.

**Không lấy một bản copy file `data` lúc server vẫn ghi rồi mặc định xem đó là backup hợp lệ.** Với hệ thống quan trọng phải dùng quy trình backup/restore của Neo4j, theo đúng khả năng Community/Enterprise và kiểm thử kết quả.

## 6. Thư mục `logs`: đọc đúng loại nhật ký

Neo4j dùng logging framework để ghi trạng thái dịch vụ và sự kiện vận hành. Các file có thể có hoặc không tùy edition và cấu hình.

| File/công cụ | Nội dung điển hình | Khi nào xem? |
| --- | --- | --- |
| `neo4j.log` | Thông tin chung về khởi động/dừng và tình trạng server | DBMS không start hoặc tự restart |
| `debug.log` | Thông tin kỹ thuật chuyên sâu, lỗi và stack trace | Khởi động lỗi, sự cố cần chẩn đoán sâu |
| `query.log` | Thông tin truy vấn theo chính sách query logging; phụ thuộc edition/setting | Điều tra truy vấn chậm, tuning |
| `security.log` | Sự kiện liên quan bảo mật/xác thực; phụ thuộc edition | Xem hoạt động đăng nhập/quyền |
| `http.log` | HTTP request nếu được bật | Tìm vấn đề ở HTTP endpoint |
| `gc.log` | Sự kiện garbage collection JVM nếu bật | Phân tích áp lực bộ nhớ |
| `docker compose logs neo4j` | STDOUT/STDERR của container/service | Docker startup, lỗi cấu hình và tiến trình |
| `journalctl -u neo4j` | Log dịch vụ `systemd`, thường dùng cho gói Debian/RPM | Service không khởi động trên Linux |

**Không suy ra file `query.log` hay `security.log` luôn tồn tại trên Community Edition**. Chúng có thể thuộc chức năng Enterprise hoặc bị tắt theo cấu hình. Trên các bản Neo4j 2025.x/2026.x, `debug.log` mặc định sử dụng dạng JSON; công cụ xem log nên hỗ trợ đọc từng JSON record nếu muốn phân tích theo field.

Ví dụ kiểm tra Docker:

~~~bash
docker compose logs --tail=100 neo4j
docker compose exec neo4j sh -c 'ls -lah /logs'
~~~

Ví dụ đọc file (nếu tồn tại và được cấp quyền):

~~~bash
docker compose exec neo4j sh -c 'tail -n 50 /logs/debug.log'
~~~

Khi đọc log để điều tra truy vấn, **không tự đưa password, token hoặc tham số có dữ liệu cá nhân vào báo cáo**. Phân tích vấn đề nên ghi thời điểm, DBMS version, database, loại lỗi và request/transaction ID nếu có. Để kiểm soát dung lượng, cấu hình **log rotation và retention** qua Log4j đúng phiên bản; tránh tùy ý xóa file log đang được tiến trình mở.

## 7. Thư mục `import`: đường đi thực tế của `LOAD CSV`

Neo4j thường giới hạn file cục bộ được đọc bằng `LOAD CSV` vào thư mục `import` vì lý do bảo mật. Giả sử có file `students.csv`:

~~~csv
studentId,name
S-001,An
S-002,Binh
~~~

Nếu file được đặt ở **`<NEO4J_HOME>/import/students.csv`** (native) hoặc **`/import/students.csv`** (Docker), chạy trong Browser:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///students.csv' AS row
RETURN row.studentId AS studentId, row.name AS name;
~~~

Kết quả mong đợi gồm hai dòng học viên. Điều quan trọng: URI `file:///students.csv` được Neo4j đọc **từ file system của server**, không từ laptop của người dùng Browser. Vì vậy:

- Với Neo4j trong container, file CSV phải nhìn thấy được **bên trong container** ở `/import/students.csv`; CSV ở thư mục Downloads của host không tự xuất hiện trong container.
- Với Neo4j ở máy từ xa, đường dẫn `file:///...` là phía **máy chủ**; Java Driver/Bolt không truyền kèm file local của client khi chạy truy vấn.
- Với AuraDB, không mặc định có quyền upload một tệp vào `/import` hệ điều hành; dùng phương pháp nhập dữ liệu được dịch vụ hỗ trợ, chẳng hạn URL HTTPS có thể truy cập hoặc công cụ import.
- Khi cần nhập dữ liệu lớn, hãy tìm hiểu thêm `neo4j-admin database import` và quy trình đúng version; **không** dùng tùy tiện lệnh quản trị import trên một database đang hoạt động.

Sau khi xác minh file import đúng:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///students.csv' AS row
MERGE (s:Student {studentId: row.studentId})
SET s.name = row.name
RETURN count(s) AS processedRows;
~~~

Trong bài lab, kết quả `processedRows = 2`. Với dữ liệu thật, nên tạo **uniqueness constraint** cho `Student.studentId`, kiểm tra dữ liệu nguồn và tổ chức lô xử lý phù hợp. Phần này dẫn vào chủ đề nhập dữ liệu, không thay thế bài học chuyên sâu về import.

## 8. Thư mục `plugins`, `labs`, `products` và `lib`

Neo4j có thể được mở rộng bằng **procedure/function** và thư viện chuyên dụng. Một plugin thường phân phối dưới dạng file **JAR**:

- **`plugins`:** nơi đặt JAR plugin cần nạp khi Neo4j khởi động.
- **`labs`:** có thể chứa APOC Core đi kèm bản phân phối; cần cài/kích hoạt theo hướng dẫn phù hợp.
- **`products`:** các sản phẩm/plugin bổ trợ đi kèm bản phân phối, khác nhau theo edition/version.
- **`lib`:** thư viện runtime của server; **không sử dụng như thư mục bỏ plugin tùy tiện**.

### 8.1. Cách cài một plugin đúng quy trình

1. Xác định **DBMS Neo4j version và edition** đang chạy. Ví dụ:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

2. Tra **bảng tương thích của plugin**, yêu cầu quyền/license nếu có. Một JAR hợp lệ ở Neo4j 5.26 có thể **không** tương thích với Neo4j 2026.10.
3. Lấy JAR từ **nguồn chính thức**, kiểm tra checksum/chữ ký khi nhà phát hành cung cấp.
4. Đặt JAR vào `plugins` mà **process Neo4j có quyền đọc**, hoặc dùng cơ chế plugin chính thức của Desktop/Docker.
5. Cấu hình các procedure chỉ trong danh sách cho phép khi thật sự cần, rồi **khởi động lại Neo4j** để nạp JAR.
6. Kiểm tra log khởi động và sự tồn tại của procedure/function bằng lệnh phù hợp với phiên bản.

Ví dụ dùng câu lệnh sau để tìm procedure có tên chứa `apoc` (nếu plugin đã cài):

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name
LIMIT 20;
~~~

Nếu kết quả rỗng, có thể plugin chưa được nạp, không tương thích, chưa được phép thực thi hoặc procedure tương ứng không tồn tại trong bản đã cài. **Không** giải quyết bằng cách mở toàn bộ `dbms.security.procedures.unrestricted` thành wildcard ở môi trường thực.

### 8.2. Trường hợp APOC

**APOC Core** là thư viện procedure/function phổ biến. Với server có sẵn JAR trong `labs`, tài liệu Neo4j hướng dẫn sao chép JAR **đúng phiên bản** sang `plugins` rồi restart; Neo4j Desktop có giao diện quản lý plugin; Docker cung cấp tiện ích `NEO4J_PLUGINS` cho môi trường phát triển.

Ví dụ khi **thực sự cần APOC** trong Docker dev:

~~~yaml
environment:
  NEO4J_PLUGINS: '["apoc"]'
~~~

Tiện ích tải/cài plugin khi container khởi động, phù hợp để học và test; **không được khuyến nghị như phương thức quản lý plugin production**. Ở production, kiểm soát JAR, phiên bản và quyền của plugin như một dependency được rà soát. Lưu ý khi Docker mount `/plugins` ở chế độ **chỉ đọc**, cơ chế `NEO4J_PLUGINS` có thể cần quyền ghi để copy/download JAR; hãy chọn một trong hai chiến lược phù hợp thay vì kết hợp mâu thuẫn.

**APOC Extended**, **Graph Data Science** và plugin khác có yêu cầu phiên bản/edition/license riêng. Đừng coi mọi JAR trong `products` tự động được bật.

## 9. Lab Docker Compose: tách rõ data, log và CSV import

### 9.1. Cấu trúc thư mục trên host

Tạo một thư mục lab độc lập, ví dụ:

~~~text
neo4j-paths-lab/
├── compose.yaml
├── .env                      # Mat khau lab, khong commit
├── .gitignore
└── import/
    └── students.csv          # CSV minh hoa o muc 7
~~~

File `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
secrets/
~~~

Không tạo thư mục `data` trong source tree nếu bạn sử dụng **named volume**; Docker sẽ quản lý nơi lưu thực tế. Thư mục `import` trong lab chỉ chứa **file nguồn được phép chia sẻ**, có thể được quản lý bằng Git nếu không chứa dữ liệu cá nhân/bí mật.

### 9.2. File `compose.yaml`

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?Set NEO4J_PASSWORD in .env}"
      NEO4J_server_memory_heap_initial__size: "512m"
      NEO4J_server_memory_heap_max__size: "512m"
      NEO4J_server_memory_pagecache_size: "512m"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - ./import:/import:ro
    restart: unless-stopped
    stop_grace_period: 2m

volumes:
  neo4j_data:
  neo4j_logs:
~~~

Tạo `.env` **chỉ dành cho lab**:

~~~dotenv
NEO4J_PASSWORD=REPLACE_WITH_UNIQUE_STRONG_PASSWORD
~~~

Thay placeholder bằng mật khẩu riêng trước khi chạy. `.env` không phải secret manager; không commit lên Git. Khi triển khai thực tế, sử dụng **Compose secrets / `NEO4J_AUTH_FILE`** hoặc secret manager phù hợp để truyền credential. Trong ví dụ học tập, `NEO4J_AUTH` chỉ có tác dụng **khởi tạo mật khẩu** khi volume database chưa có user.

**Vai trò các mount:**

| Khai báo | Ý nghĩa | Sau khi thay container |
| --- | --- | --- |
| `neo4j_data:/data` | Graph và các file database quan trọng | Được giữ nếu không xóa volume |
| `neo4j_logs:/logs` | Log nằm ngoài writable layer | Được giữ nếu không xóa volume |
| `./import:/import:ro` | Host folder `./import` đọc được từ server | Còn nguyên trên host; Neo4j không ghi vào đây |

Ở ví dụ này **chưa mount `/conf`** để tránh thay bộ cấu hình đầy đủ của image; bộ config gốc tiếp tục được dùng và ta chỉ thay vài setting bằng biến môi trường.

### 9.3. Khởi chạy và kiểm tra file

Từ thư mục lab:

~~~bash
docker compose config --quiet
docker compose pull neo4j
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Khi DBMS sẵn sàng, mở `http://localhost:7474/browser/` rồi kết nối bằng `bolt://localhost:7687`, user `neo4j` và mật khẩu trong `.env`. Chạy:

~~~cypher
RETURN 'Neo4j file structure lab ready' AS message;
~~~

Từ terminal trên máy host (Linux/macOS Bash; Windows PowerShell có thể dùng cùng lệnh `docker compose exec`):

~~~bash
docker compose exec neo4j sh -c 'ls -ld /data /logs /import /plugins'
docker compose exec neo4j sh -c 'ls -lah /import'
docker compose exec neo4j sh -c 'ls -lah /logs'
~~~

Trong `/import` phải thấy `students.csv`. Sau đó chạy truy vấn `LOAD CSV` ở mục 7 và truy vấn `MATCH` xác nhận graph:

~~~cypher
MATCH (s:Student)
WHERE s.studentId IN ['S-001', 'S-002']
RETURN s.studentId AS id, s.name AS name
ORDER BY id;
~~~

### 9.4. Kiểm tra dữ liệu bền vững khi tạo lại container

~~~bash
# Xoa container/network Compose, NHUNG GIU NAMED VOLUMES
docker compose down

# Tao lai container tu cung config va volume
docker compose up -d
docker compose ps
~~~

Đăng nhập lại bằng **mật khẩu cũ đang được lưu trong database**, rồi chạy `MATCH` ở mục 9.3. Nếu hai student còn tồn tại, mount `/data` đã phục vụ đúng mục đích. Named volume thường có tên với tiền tố project Compose, ví dụ `neo4j-paths-lab_neo4j_data`; thay tên project/`-p` có thể tạo volume khác.

**Không chạy `docker compose down -v` trên database cần giữ:** cờ `-v` xóa named volume của project này, có thể khiến mất graph, transaction logs và user. Không xóa volume chỉ để thay mật khẩu hoặc sửa cấu hình.

## 10. Quản lý quyền và vận hành theo thư mục

### 10.1. Quyền file tối thiểu

Neo4j cần **đọc** `conf`, `import`, `plugins`; cần **đọc và ghi** `data` và `logs`. Nếu gắn thư mục host bằng bind mount, quyền sở hữu phải cho phép người dùng chạy Neo4j trong container thao tác.

Đối với Neo4j Docker chính thức, tiến trình thường chạy dưới user `neo4j` (UID thông dụng là **7474**). Tùy cách chạy, startup có thể điều chỉnh quyền chủ sở hữu thư mục mount; việc chỉ định `--user` tùy ý có thể khiến server không đọc/ghi được.

- Trên Linux, đặt quyền tối thiểu, tránh mở `chmod 777` để “sửa nhanh”; dùng tài khoản service và nhóm phù hợp.
- Trên Windows, giới hạn ACL của data/config/log vào tài khoản service và nhóm quản trị cần thiết.
- Với volume chứa dữ liệu thật, ưu tiên quản lý bằng quy trình kiểm soát quyền của tổ chức và có backup.
- Đừng chia sẻ công khai thư mục `data`, log hoặc secret file; có thể làm lộ cấu trúc nội bộ hay thông tin nhạy cảm.

### 10.2. Di chuyển hoặc nâng cấp thư mục

| Mục đích | Cách làm an toàn hơn |
| --- | --- |
| Đổi vị trí log | Cấu hình `server.directories.logs` hoặc mount `/logs` phù hợp, xác minh quyền và rotation |
| Đổi vị trí database | Dừng/cô lập DBMS, theo quy trình migration/restore của Neo4j; kiểm tra nhất quán dữ liệu |
| Nhập thêm CSV | Đưa file vào `import` đã cấu hình, cấp quyền đọc, chạy `LOAD CSV` |
| Thêm plugin | Tra compatibility, đặt JAR vào `plugins`, cấu hình allowlist/quyền rồi restart |
| Nâng image Docker | Đối chiếu release/migration guide và backup/restore trước khi dùng lại volume |
| Giữ log phục vụ điều tra | Mount `/logs`, cấu hình retention, tránh đưa credential vào log |

**Lưu ý:** `/data` bền vững chỉ ngăn mất dữ liệu do **vòng đời container**. Nó không thay cho lịch sao lưu, kiểm thử restore, quản lý dung lượng hay giám sát I/O.

## 11. Chẩn đoán sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/khắc phục |
| --- | --- | --- |
| Neo4j không start sau khi mount `./conf:/conf` | Bộ file `/conf` rỗng/thiếu cấu hình, sai setting hoặc thiếu quyền đọc | Bỏ mount trong lab, dùng environment variables; khi cần custom config hãy tạo đủ file từ `dump-config` đúng image |
| `Permission denied` trên `/data` hoặc `/logs` | User Neo4j không có quyền ghi vào bind mount | Kiểm tra owner/ACL và Docker user; dùng named volume cho lab |
| Restart container xong graph biến mất | Chưa mount `/data`, đã xóa volume hoặc đổi Compose project name | Xem `docker volume ls`, mount và tham số `-p`; tìm volume cũ trước khi sửa |
| Dung lượng tăng nhanh trong `data` | Graph, index hoặc transaction log tăng trưởng | Kiểm tra tăng trưởng và cấu hình retention theo hướng dẫn; **không xóa transaction logs bằng tay** |
| Không thấy `query.log` | Chức năng có thể chỉ có ở edition nhất định hoặc đã tắt | Đối chiếu edition và cấu hình logging thay vì cho rằng file bắt buộc tồn tại |
| `LOAD CSV` báo file không tìm thấy | CSV chỉ ở host, không mount vào `/import`, sai tên/đuôi file | Kiểm tra `ls /import` **trong container**, rồi dùng `file:///students.csv` |
| Không ghi được CSV kết quả vào `/import` | Mount chỉ đọc `:ro`; người dùng/DBMS không có quyền ghi | Giữ import chỉ đọc cho lab; chọn luồng xuất dữ liệu riêng nếu thực sự cần |
| Plugin JAR đã copy nhưng procedure không xuất hiện | Chưa restart, JAR không tương thích hoặc thiếu cấu hình/quyền | Xem log startup, version, edition và `SHOW PROCEDURES` |
| `NEO4J_PLUGINS` không cài được khi mount `/plugins:ro` | Tiện ích startup cần ghi JAR vào thư mục | Dùng mount ghi phù hợp cho môi trường dev hoặc cài JAR thủ công đúng version |
| `debug.log` khó đọc như văn bản | Bản hiện hành có thể ghi JSON | Dùng công cụ đọc JSON/log viewer; không chỉnh format debug tùy tiện |
| Đổi đường dẫn `data` xong Neo4j như database mới | DBMS trỏ sang folder trống hoặc không còn đúng store | Dừng thay đổi, kiểm tra config và backup; không tạo/xóa file store thủ công |

Khi tìm lỗi, xác nhận theo thứ tự **DBMS version/edition → vị trí file thực tế → mount/permission → log startup → cấu hình → truy vấn**. Tách biệt lỗi đường dẫn, lỗi dữ liệu và lỗi quyền trước khi thử thao tác thay đổi dữ liệu.

## 12. Bài tập thực hành

### Bài tập 1 — Lập sơ đồ cấu trúc cho môi trường thật

Chọn một bản cài **ZIP/TAR**, **package Debian/RPM** hoặc **Docker**. Ghi vị trí thực tế của `conf`, `data`, `logs`, `import` và `plugins`. Giải thích vì sao không thể mặc định chúng đều nằm dưới cùng một thư mục khi cài qua APT/RPM.

**Kết quả mong đợi:** có bảng đường dẫn, phương pháp kiểm tra và ghi chú về quyền đọc/ghi.

### Bài tập 2 — Kiểm chứng data persistence và import

Dùng Compose ở mục 9, tạo graph từ `students.csv`. Chạy `docker compose down` rồi `docker compose up -d`. Truy vấn lại hai node `Student`, chụp kết quả và giải thích vì sao graph còn nhưng không nên dùng volume như một bản backup.

**Kết quả mong đợi:** hai học viên vẫn tồn tại trong database; xác định đúng volume giữ `/data`.

### Bài tập 3 — Phân biệt log vận hành và transaction log

Một nhóm thấy `data/transactions` chiếm dung lượng, định xóa folder này vì nghĩ nó là `debug.log`. Hãy giải thích chức năng của transaction log, nêu ít nhất hai rủi ro nếu xóa thủ công và đề xuất cách xử lý dung lượng phù hợp.

### Bài tập 4 — Thêm APOC đúng cách

Bạn muốn dùng một procedure APOC trong lab. Hãy mô tả cách xác định version Neo4j, chọn đúng APOC tương thích, dùng `NEO4J_PLUGINS` hoặc đặt JAR vào `plugins`, restart và kiểm tra qua `SHOW PROCEDURES`. Giải thích vì sao không nên đặt file plugin vào `lib`.

### Checklist hoàn thành

- [ ] Giải thích đúng ý nghĩa `conf`, `data`, `logs`, `import` và `plugins`.
- [ ] Nêu được khác biệt thư mục khi cài ZIP/TAR, Debian/RPM, Docker và Desktop.
- [ ] Phân biệt transaction logs với debug/query/security logs.
- [ ] Biết kiểm tra setting/path và mount của đúng instance Neo4j.
- [ ] Chạy được Compose có `/data` và `/logs` là named volumes.
- [ ] Đọc được `students.csv` từ `/import` và tạo node bằng `LOAD CSV`.
- [ ] Kiểm tra graph còn sau `docker compose down` và `up -d`.
- [ ] Giải thích vì sao không xóa `data`, transaction logs hoặc volume khi vẫn cần dữ liệu.
- [ ] Biết cách kiểm tra plugin đúng phiên bản và vị trí JAR.
- [ ] Biết quản lý quyền file, log retention và backup theo đúng mục đích.

## 13. Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Default file locations](https://neo4j.com/docs/operations-manual/current/configuration/file-locations/) — đường dẫn theo phương thức cài và quyền file.
- [Neo4j Operations Manual — Configuration](https://neo4j.com/docs/operations-manual/current/configuration/) — `neo4j.conf` và các setting được hỗ trợ.
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/) — các loại log, Log4j và chính sách lưu giữ.
- [Neo4j Operations Manual — Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/) — mục đích và vị trí transaction logs.
- [Neo4j Operations Manual — Persisting data with Docker volumes](https://neo4j.com/docs/operations-manual/current/docker/mounting-volumes/) — `/data`, `/logs`, `/conf`, `/import`, `/plugins`.
- [Neo4j Operations Manual — Modify Docker configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/) — environment variables, `/conf` và `dump-config`.
- [Neo4j Operations Manual — Configure plugins](https://neo4j.com/docs/operations-manual/current/configuration/plugins/) — plugin JAR, phiên bản và quyền procedure.
- [Neo4j Operations Manual — Docker plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/) — `NEO4J_PLUGINS` và mount `/plugins`.
- [Neo4j Getting Started — CSV files](https://neo4j.com/docs/getting-started/data-import/csv-files/) — `LOAD CSV` và đường dẫn `file:///`.
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/) — sử dụng dữ liệu khi đổi phiên bản Neo4j.

**Ghi nhớ:** `conf` quyết định hành vi DBMS; `data` giữ dữ liệu đồ thị và transaction logs; `logs` hỗ trợ vận hành; `import` cung cấp dữ liệu nguồn; `plugins` mở rộng chức năng. Đúng đường dẫn, quyền file và chính sách lưu trữ là nền tảng để học Cypher, tối ưu graph và vận hành Neo4j đáng tin cậy.
