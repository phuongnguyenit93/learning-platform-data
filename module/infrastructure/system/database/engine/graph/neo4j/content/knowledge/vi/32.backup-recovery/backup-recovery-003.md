# Dump và load ngoại tuyến theo công cụ của phiên bản đang dùng

## 1. Tại sao phải biết chính xác phiên bản trước khi dump/load?

Khi vận hành Neo4j, người quản trị có thể cần sao chép một database sang môi trường kiểm thử, lưu một ảnh chụp dữ liệu trước đợt thay đổi lớn hoặc phục hồi database từ tệp lưu trữ. Hai lệnh thường được sử dụng là **dump** (đóng gói database thành archive) và **load** (nạp archive trở lại thành database). Tuy nhiên, **tên lệnh, đối số, yêu cầu dừng database và phương thức đăng ký database thay đổi theo phiên bản/edition**.

Một hướng dẫn dành cho Neo4j 4.4 dùng lệnh `neo4j-admin dump` không thể được sao chép nguyên xi sang Neo4j 5 hoặc Neo4j 2025–2026, nơi công cụ được nhóm dưới `neo4j-admin database dump`. Tương tự, `--from` của 4.4 khác `--from-path` trong những bản mới; tùy chọn ghi đè và cách xử lý cluster cũng khác. Dùng sai cách có thể gây downtime ngoài ý muốn, ghi đè database hoặc tạo trạng thái không nhất quán.

Bài này thuộc chương **Sao lưu và phục hồi** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`. Nội dung hướng dẫn thao tác phù hợp cho property graph gồm node, relationship, index, constraint và dữ liệu do ứng dụng Cypher, Neo4j Java Driver hay Spring Data Neo4j tạo ra.

**Mục tiêu học tập:**

1. Phân biệt **offline dump/load**, online backup/restore và xuất dữ liệu mức logic.
2. Kiểm tra phiên bản và nhận diện cú pháp `neo4j-admin` đúng với nơi đang chạy.
3. Thực hiện quy trình dump/load có kiểm soát trên **database test độc lập**.
4. Hiểu giới hạn của archive đối với `system`, users/roles, cấu hình, extension và cluster.
5. Đối soát tính toàn vẹn bằng đáp án Cypher sau khi phục hồi.
6. Lập runbook vận hành với tiêu chí thành công, phương án rollback, RPO và RTO.

> **Cảnh báo thao tác:** Các khối shell trong bài là **mẫu để hiểu và điều chỉnh trong phòng lab**; không chạy trực tiếp trên production. `neo4j stop` làm gián đoạn dịch vụ, còn `--overwrite-destination=true` có thể thay thế dữ liệu đích. Không sử dụng các lệnh phá hủy hoặc ghi đè nếu chưa có phê duyệt, bản sao khôi phục được và xác nhận chính xác database/instance đích.

## 2. Bốn thao tác nghe giống nhau nhưng không tương đương

| Thao tác | Công cụ hoặc cơ chế | Trạng thái database | Đầu ra/ý nghĩa |
|---|---|---|---|
| **Dump** | `neo4j-admin database dump` ở Neo4j 5+ | Database nguồn **không được đang mounted/running** | Archive dump toàn bộ nội dung của một database |
| **Load** | `neo4j-admin database load` ở Neo4j 5+ | Database đích **không được đang mounted/running** khi thay thế | Chuyển archive thành store của database đích |
| **Online backup** | `neo4j-admin database backup`, tính năng Enterprise theo bản hỗ trợ | Database nguồn đang online | Artifact backup; có thể hỗ trợ full/differential và chính sách metadata riêng |
| **Export logic** | Cypher, APOC export hoặc ứng dụng Java | Có thể chạy online tùy giải pháp | CSV/JSON/Cypher; **không tự tương đương** dump của store |

**Dump không phải câu lệnh Cypher.** Nó là lệnh dòng lệnh `neo4j-admin` chạy tại môi trường có quyền truy cập những file database cần thiết. Java Driver và Spring Data Neo4j không biến một câu `CALL` tùy ý thành bản dump vật lý.

**Dump không phải online backup thông thường.** Khi ứng dụng vẫn đang ghi, phải dùng phương án online backup được edition hỗ trợ hoặc lập lịch downtime đủ dài để database thực sự offline. Sao chép thư mục database bằng cách copy file trong lúc Neo4j đang chạy **không phải** phương pháp backup được hỗ trợ.

**Load không phải import CSV.** `neo4j-admin database import` tạo database từ các bản ghi CSV/Parquet theo quy trình import riêng; `database load` khôi phục định dạng archive được tạo bởi dump/backup hợp lệ. Không dùng hai lệnh thay cho nhau.

## 3. Sơ đồ vòng đời một đợt dump/load

~~~mermaid
flowchart TD
    A["Xác minh phiên bản, edition và database nguồn"] --> B["Ghi baseline: node, relationship, constraint, dữ liệu nghiệp vụ"]
    B --> C["Dừng database nguồn / đưa về trạng thái offline phù hợp"]
    C --> D["neo4j-admin database dump → archive"]
    D --> E["Kiểm tra exit code, kích thước, quyền, checksum và metadata"]
    E --> F["Chuyển archive sang instance phục hồi độc lập"]
    F --> G["Bảo đảm database đích offline và không ghi đè ngoài ý muốn"]
    G --> H["neo4j-admin database load"]
    H --> I["Start / đăng ký database theo edition và tình huống"]
    I --> J["So baseline, schema, chức năng Java Driver/SDN"]
    J --> K{"Tất cả kiểm tra PASS?"}
    K -->|Có| L["Đóng runbook, ghi thời gian và bảo quản archive"]
    K -->|Không| M["Ngừng cutover, phân tích log và rollback theo kế hoạch"]
~~~

**Điều kiện trước mỗi mũi tên:** tên database, đường dẫn, quyền file và node/instance đang thao tác phải được xác nhận. Trong cluster, không tự nhân quy trình load của một standalone instance sang nhiều thành viên.

## 4. Bảng phiên bản: chọn đúng lệnh, đúng đối số

| Dòng phiên bản | Dump | Load | Điểm khác cần nhớ |
|---|---|---|---|
| **Neo4j 4.4 (legacy)** | `neo4j-admin dump --database=neo4j --to=/path/neo4j.dump` | `neo4j-admin load --database=neo4j --from=/path/neo4j.dump` | `--to` và `--from` thường nhận **đường dẫn tệp**; khi thay thế bản cũ có `--force` |
| **Neo4j 5.x** | `neo4j-admin database dump neo4j --to-path=/backup-dir` | `neo4j-admin database load neo4j --from-path=/backup-dir` | Có nhóm lệnh `database`; đường dẫn là **thư mục** chứa archive |
| **Neo4j 2025–2026 hiện hành** | `neo4j-admin database dump` | `neo4j-admin database load` | Kiểm tra `--help` ở đúng bản cài đặt; một số tùy chọn cloud/split archive được thêm theo release |

**Không tự đoán từ nội dung trên Internet.** Trên chính server/ảnh container cần vận hành, chạy các lệnh **chỉ đọc** sau để biết công cụ thực sự hỗ trợ gì:

~~~bash
# Từ môi trường shell có neo4j-admin trong PATH.
neo4j-admin --version
neo4j-admin database dump --help
neo4j-admin database load --help
~~~

Nếu `neo4j-admin database dump --help` không tồn tại trên Neo4j 4.4, xem:

~~~bash
# Chỉ áp dụng cho công cụ Neo4j 4.4 tương ứng.
neo4j-admin dump --help
neo4j-admin load --help
~~~

Đọc các mục **Syntax**, **Default**, **Overwrite**, **From/To**, và điều kiện edition trong output. Trong doanh nghiệp, quản lý cả version của **binary công cụ** lẫn version **store nguồn và server đích**. Không chạy công cụ của một image bất kỳ trên store cũ mà chưa xác minh compatibility.

### 4.1. Không nhầm phiên bản Neo4j với phiên bản Java Driver

Cấu hình `spring.neo4j.uri`, Maven `neo4j-java-driver` và version Neo4j DBMS là các thành phần khác nhau. `Driver 5.x` không có nghĩa server đang chạy Neo4j 5.26. Khi thực hiện dump/load, cú pháp phải theo **neo4j-admin nằm trong cài đặt Neo4j server**, không theo phiên bản thư viện Java của ứng dụng.

### 4.2. Lưu ý về đường nâng cấp

Neo4j 4.4 đã hết vòng hỗ trợ dài hạn theo lịch tài liệu hiện hành. Việc chuyển store từ **4.4 sang 5** có hướng dẫn migration và các bước tương thích cụ thể; không phải cứ load archive 4.4 vào bất kỳ release 2026 nào là sẽ tự nâng cấp thành công. Tương tự, **hạ cấp store về phiên bản cũ hơn không được hỗ trợ như một thao tác downgrade thông thường**.

Khi vừa đổi phiên bản vừa phục hồi, tách hai câu hỏi:

1. Archive có **đọc/load được** theo định dạng của công cụ đích không?
2. Database sau khi load có cần **migrate store/schema**, tạo lại người dùng/role hoặc cấu hình theo hướng dẫn chuyển phiên bản không?

Một kết quả “load thành công” chưa chứng minh ứng dụng chạy được trên bản mới.

## 5. Edition và trạng thái online/offline

Tài liệu Neo4j hiện hành phân biệt:

- **Community Edition:** `database dump` và `database load` thực hiện khi **DBMS offline**. Thực tế trong lab thường tắt process Neo4j trước khi chạy.
- **Enterprise Edition:** có thể chạy công cụ cục bộ trong khi **DBMS vẫn online**, nhưng **database cần dump hoặc thay thế không được đang mounted/running trên server đó**. Với database user riêng, có thể dùng quy trình `STOP DATABASE` theo quyền và hướng dẫn quản trị.
- **Cluster Enterprise:** database là một phần của topology phân tán. Việc seed, restore hoặc thay thế store phải tuân thủ quy trình cluster, không đơn thuần chạy `load --overwrite-destination` trên từng thành viên.

Một ví dụ kiểm tra trước khi bảo trì:

~~~cypher
// Chạy trong phiên làm việc quản trị thích hợp.
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Nếu triển khai Enterprise và đã được phê duyệt đưa một database user sang offline, lệnh quản trị có thể là:

~~~cypher
// CHỈ trong cửa sổ bảo trì đã phê duyệt; không chạy trong lab chung.
STOP DATABASE mydb WAIT;
~~~

Không trộn giữa **dừng database** và **dừng cả DBMS**. Cú pháp `STOP DATABASE`, quyền admin, hành vi cluster và điều kiện cho `system` phải được xác minh theo phiên bản. Trong Community hoặc tình huống đơn giản, dùng dừng DBMS trong một **instance test riêng**.

## 6. Kiểm tra trước khi dump: đừng chỉ nhìn file đích

Runbook tối thiểu phải ghi:

| Cần xác minh | Tại sao quan trọng? |
|---|---|
| Database và instance nguồn | Không dump nhầm dữ liệu của tenant/cluster khác |
| Edition, server version, admin tool version | Xác định lệnh, syntax và phương án chuyển phiên bản |
| Database đã offline theo đúng quy trình | Không đọc store đang thay đổi |
| Quyền OS chạy công cụ | Tránh file sinh ra bằng `root` rồi Neo4j không đọc/ghi được |
| Thư mục archive tồn tại, đủ dung lượng và không bị public truy cập | Tránh thất bại giữa chừng, rò rỉ graph |
| RPO/RTO và downtime cho phép | Offline dump là hoạt động gây gián đoạn cho database nguồn |
| Backup trước đó độc lập và đã restore thử | Có đường lui nếu archive mới bị lỗi |
| Baseline dữ liệu/schema | Có thể đối chiếu sau load, tránh “khởi động được nhưng sai dữ liệu” |
| Tính tương thích plugin, cấu hình, JDK và store | Archive của user DB không bao gồm toàn bộ môi trường vận hành |
| Log và checklist phê duyệt | Có người chịu trách nhiệm rollback/cutover |

**An ninh tệp:** Dump có thể chứa dữ liệu nhạy cảm như email, order, relationship nghiệp vụ, hashed passwords hoặc thuộc tính cá nhân. Chỉ lưu ở vị trí hạn chế người đọc, áp mã hóa khi lưu/truyền, không đưa dump lên Git hoặc artifact công khai. Không đặt quyền thư mục backup cho “mọi người” chỉ để tránh lỗi permission.

## 7. Fixture Cypher có đáp án trước khi dump

Để đo tính đúng sau restore, dùng **database test riêng** với nhãn `QA003ArchiveItem`, `QA003ArchiveOwner` và relationship `QA003_OWNED_BY`. Đừng chạy cleanup trên database có dữ liệu thật hoặc nhãn được chia sẻ.

### 7.1. Tạo dữ liệu định danh rõ ràng

Trên một database test có tên `neo4j` (hoặc thay tên theo deployment lab), chỉ khi chắc chắn fixture chưa tồn tại:

~~~cypher
CREATE CONSTRAINT qa003_archive_item_id IF NOT EXISTS
FOR (i:QA003ArchiveItem)
REQUIRE i.itemId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa003_archive_owner_id IF NOT EXISTS
FOR (o:QA003ArchiveOwner)
REQUIRE o.ownerId IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 5) AS id
MERGE (i:QA003ArchiveItem {itemId:id})
SET i.title = 'Muc ' + toString(id),
    i.score = id * 10,
    i.recordedOn = date('2026-11-01');
~~~

~~~cypher
UNWIND [
  {id:'U01', name:'An'},
  {id:'U02', name:'Binh'}
] AS row
MERGE (o:QA003ArchiveOwner {ownerId:row.id})
SET o.name = row.name;
~~~

~~~cypher
UNWIND [
  {item:1, owner:'U01'},
  {item:2, owner:'U01'},
  {item:3, owner:'U02'},
  {item:4, owner:'U02'}
] AS row
MATCH (i:QA003ArchiveItem {itemId:row.item})
MATCH (o:QA003ArchiveOwner {ownerId:row.owner})
MERGE (i)-[:QA003_OWNED_BY]->(o);
~~~

**Chú ý:** Có đúng năm item nhưng **item 5 không có owner**. Đây là trường hợp đối chứng cho `OPTIONAL MATCH`, kiểm tra xem sau restore các relationship có được giữ đầy đủ hay không.

### 7.2. Ghi baseline trước dump

~~~cypher
MATCH (i:QA003ArchiveItem)
WITH count(i) AS items, sum(i.score) AS scores
MATCH (o:QA003ArchiveOwner)
WITH items, scores, count(o) AS owners
MATCH ()-[r:QA003_OWNED_BY]->()
RETURN items, scores, owners, count(r) AS relationships;
~~~

| items | scores | owners | relationships |
|---:|---:|---:|---:|
| **5** | **150** | **2** | **4** |

Vì điểm của item 1–5 là 10, 20, 30, 40, 50 nên `sum(score)=150`.

Kiểm tra từng item, bao gồm item không có quan hệ:

~~~cypher
MATCH (i:QA003ArchiveItem)
OPTIONAL MATCH (i)-[:QA003_OWNED_BY]->(o:QA003ArchiveOwner)
RETURN i.itemId AS itemId,
       i.title AS title,
       i.score AS score,
       i.recordedOn AS recordedOn,
       collect(o.ownerId) AS owners
ORDER BY itemId;
~~~

| itemId | title | score | recordedOn | owners |
|---:|---|---:|---|---|
| 1 | Muc 1 | 10 | 2026-11-01 | [U01] |
| 2 | Muc 2 | 20 | 2026-11-01 | [U01] |
| 3 | Muc 3 | 30 | 2026-11-01 | [U02] |
| 4 | Muc 4 | 40 | 2026-11-01 | [U02] |
| 5 | Muc 5 | 50 | 2026-11-01 | [] |

Danh sách `owners` nên được so sánh theo tập hoặc sắp xếp nếu có nhiều owner; không xem thứ tự trong `collect` là bất biến nếu query không sắp xếp trước aggregation.

### 7.3. Ghi nhận schema/constraint

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name IN [
  'qa003_archive_item_id',
  'qa003_archive_owner_id'
]
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

Đáp án: có hai constraint `IS UNIQUE` tương ứng `QA003ArchiveItem(itemId)` và `QA003ArchiveOwner(ownerId)`; index phục vụ constraint cần đạt `ONLINE` trước khi dùng để benchmark. Sau load phải so cả **dữ liệu** và **schema**, không chỉ hai số đếm.

## 8. Quy trình dump Neo4j 5.x và Neo4j 2025–2026

**Giả định:** đây là một **standalone lab riêng**, database test tên `neo4j` đã được đưa về offline theo quy trình, công cụ Neo4j cài tại máy chủ và thư mục `/secure/neo4j-dumps` có sẵn, chỉ những account cần thiết mới đọc/ghi được.

### 8.1. Kiểm tra trước khi chạy

~~~bash
neo4j-admin --version
neo4j-admin database dump --help

# Các lệnh đọc metadata filesystem, chỉ chạy trong môi trường lab.
ls -ld /secure/neo4j-dumps
df -h /secure/neo4j-dumps
~~~

Đối với Community lab, **chỉ sau khi đã dừng traffic/được phép dừng DBMS**, vận hành viên có thể dùng:

~~~bash
# CHỈ trên instance test. Lệnh này dừng Neo4j.
neo4j stop
~~~

Đối với Enterprise, có thể dừng riêng database user qua Cypher quản trị trong DBMS online, nhưng phải kiểm tra database đã thực sự offline. **Không** chạy dump trên database còn mounted.

### 8.2. Tạo archive

~~~bash
# Neo4j 5+/2025–2026; tên database là neo4j.
# --to-path chỉ thư mục ĐÃ TỒN TẠI và có quyền ghi.
neo4j-admin database dump neo4j --to-path=/secure/neo4j-dumps
~~~

Tương đương vị trí đối số trong tài liệu:

~~~bash
neo4j-admin database dump --to-path=/secure/neo4j-dumps neo4j
~~~

`--to-path` là **thư mục đích**. Ở nhiều bản, lệnh tạo archive mang tên `neo4j.dump`; những release mới có thể thay đổi cách đặt tên/thêm timestamp hoặc hỗ trợ chia archive thành nhiều phần. **Đọc output và liệt kê file thật**, không viết script mặc định mọi phiên bản đều tạo cùng một tên.

**Không thêm `--overwrite-destination=true` vào dump nếu không thật sự muốn thay thế một archive có sẵn.** Dump của tuần trước có thể là bản cứu dữ liệu khi bản mới bị lỗi; nên lưu theo thư mục/vòng đời riêng và áp retention rõ ràng.

### 8.3. Xác minh archive

~~~bash
# Kiểm tra file mới tạo trong thư mục.
ls -lh /secure/neo4j-dumps

# Kiểm tra help để biết có hỗ trợ info và cách chọn artifact không.
neo4j-admin database load --help
~~~

Nếu thư mục có một dump phù hợp và phiên bản hỗ trợ `--info`:

~~~bash
# In metadata archive; KHÔNG nạp database.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps --info
~~~

`--info` giúp nhìn metadata như định dạng, số file và kích thước, **không thay thế** checksum hoặc diễn tập load + truy vấn dữ liệu. Nếu có nhiều archive của cùng database trong một thư mục, cần xác minh cách công cụ **chọn artifact nào**; cân nhắc tổ chức mỗi lần dump thành thư mục riêng.

Ví dụ kiểm tra checksum khi đã xác định được **file thật** tên `neo4j.dump`:

~~~bash
sha256sum /secure/neo4j-dumps/neo4j.dump
~~~

Không tính checksum trên tên tệp đoán trước nếu công cụ thực sự tạo filename khác. Ghi checksum cùng thời gian, phiên bản, database nguồn và người tạo trong manifest được quản lý; không chỉnh sửa archive để “sửa” nội dung dump.

## 9. Load ngoại tuyến vào instance test độc lập — lựa chọn an toàn nhất

**Không phục hồi thử trực tiếp lên production.** Chuẩn bị **instance Neo4j mới, cô lập**, cùng phiên bản hoặc bản tương thích theo tài liệu, với volume đích khác hoàn toàn volume nguồn.

Giả định:

- Nguồn: database test `neo4j` đã tạo dump.
- Đích: **instance test phục hồi riêng**, dùng database tên `neo4j`.
- Thư mục archive `/secure/neo4j-dumps` đã được chuyển đến đích, checksum khớp.
- Database đích **chưa có store tồn tại**, hoặc được chuẩn bị đúng theo hướng dẫn phiên bản mà **không yêu cầu overwrite**.

Trên **instance đích đã offline**:

~~~bash
neo4j-admin --version
neo4j-admin database load --help

# Ví dụ load trên nơi chưa có database store tương ứng.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps
~~~

Với `--from-path`, phiên bản Neo4j 5+ mong đợi **thư mục chứa archive**, không phải đường dẫn trực tiếp đến file `.dump`. Một số release có cơ chế nạp trực tiếp từ `--from-stdin`; chỉ dùng khi thực sự cần chọn artifact cụ thể và đã kiểm tra stdin trên nền tảng shell.

**Khi có store đã tồn tại:** Lệnh mặc định có thể từ chối nạp, đó là **cơ chế bảo vệ quan trọng**. Đừng ngay lập tức thêm `--overwrite-destination`; cần chắc chắn đang nhìn đúng instance test, đã giữ bản sao dữ liệu đích và có quyền thay thế.

### 9.1. Khởi động hoặc đăng ký database sau load

Trên một standalone instance Community **đã tắt DBMS**, hoàn tất load rồi khởi động lại DBMS theo quy trình:

~~~bash
# Chỉ dùng trên instance phục hồi test.
neo4j start
~~~

Trên **Enterprise**, khi load một database **chưa từng tồn tại trong catalog**, tài liệu Neo4j hiện hành yêu cầu **đăng ký bằng `CREATE DATABASE` trên database `system` sau khi load**:

~~~cypher
// Ví dụ chỉ dùng trong instance Enterprise test,
// khi dữ liệu đã load nhưng catalog chưa có database này.
CREATE DATABASE restoredtest WAIT;
~~~

Tên `restoredtest` chỉ đúng khi archive/store đã được load cho **đúng tên đó** theo quy trình của bản đang dùng. Đừng dùng `CREATE DATABASE` tùy tiện để “chữa” lỗi load; phải hiểu trạng thái filesystem và catalog, tránh tạo một database rỗng ngoài ý muốn.

Nếu khôi phục để **thay thế một database đã tồn tại**, quy trình khởi động/đăng ký khác; hãy làm theo hướng dẫn riêng ở mục 10.

### 9.2. Xác minh database thực sự online

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Chỉ sau khi database mong đợi `ONLINE` và tài khoản có quyền, chạy các câu Cypher kiểm chứng ở mục 7. Nếu output đếm 0 node, đừng vội kết luận dump rỗng: hãy kiểm tra tên database trong session của Java Driver, Neo4j Browser hoặc Spring Data Neo4j.

## 10. Thay thế database đã tồn tại: thao tác có rủi ro cao

Neo4j 5+ hỗ trợ `--overwrite-destination=true` khi **phục hồi trên standalone server** và database đích **đã được dừng hoàn toàn**. Đây là một ví dụ để **nhận diện cú pháp trong runbook**, không phải lệnh thực thi ngay:

~~~bash
# CHỈ TRÊN INSTANCE PHỤC HỒI CÔ LẬP, SAU KHI ĐƯỢC PHÊ DUYỆT.
# Database đích đã dừng, đã backup dữ liệu hiện tại và xác minh đúng đường dẫn.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps \
  --overwrite-destination=true
~~~

Mặc định `--overwrite-destination=false` là an toàn hơn. Trong bản 4.4, tùy chọn có ý nghĩa tương ứng là `--force`; **không** thay tên cờ mà bỏ qua các điều kiện dừng database và tương thích archive.

### Checklist phê duyệt khi overwrite

1. Có ticket/change request, chủ sở hữu database và khoảng downtime đã thông báo.
2. Tên host, instance, data directory, database đích được đối chiếu **hai lần**.
3. Lệnh quản trị dùng **đúng binary cùng version** với quy trình phục hồi.
4. Database đích đã ngừng ghi và ở trạng thái offline; trong Community, DBMS offline.
5. Có bản backup **của dữ liệu đích trước khi ghi đè**, lưu ngoài vùng lỗi.
6. Archive nguồn đã được xác minh metadata/checksum và từng restore thử.
7. Có người chịu trách nhiệm rollback, tiêu chí xác nhận và mốc RTO.
8. Chỉ start/cho ứng dụng kết nối khi validation sau load đã PASS.

**Không dùng một ví dụ `--overwrite-destination=true` sao chép từ internet để ghi đè database production ngay lập tức.**

## 11. Khác biệt căn bản ở Neo4j 4.4

Neo4j 4.4 dùng dòng lệnh legacy, ví dụ:

~~~bash
# Neo4j 4.4, môi trường offline lab.
neo4j-admin dump \
  --database=neo4j \
  --to=/secure/neo4j-dumps/neo4j-legacy.dump
~~~

Nạp lại archive ở **đích tương thích**:

~~~bash
# Neo4j 4.4, khi database đích chưa có store.
neo4j-admin load \
  --database=neo4j \
  --from=/secure/neo4j-dumps/neo4j-legacy.dump
~~~

Nếu đích đã có dữ liệu và cần thay thế sau quy trình dừng/backup, Neo4j 4.4 có cờ `--force`. Ở Neo4j 5+, cờ được thay bằng `--overwrite-destination` với nhóm lệnh `database load`.

| Nhầm lẫn | Hậu quả |
|---|---|
| Dùng `neo4j-admin dump` trên 5+ | Có thể báo không tìm thấy command |
| Dùng `--to-path=/file.dump` như 4.4 | Tool mới kỳ vọng **thư mục**, không phải đường dẫn file |
| Dùng `--from=/file.dump` trên 5+ | Không đúng cú pháp mới thông thường |
| Dùng `--force` từ 4.4 sang lệnh mới | Không phải cú pháp `--overwrite-destination` mới |
| Cho rằng archive 4.4 load vào bản 2026 bất kỳ | Bỏ qua lộ trình migrate/store-format compatibility |
| Cho rằng Driver version quyết định lệnh admin | Sai: binary Neo4j DBMS quyết định cú pháp |

Neo4j 4.4 đã ngoài vòng hỗ trợ dài hạn; với hệ thống còn vận hành 4.4, nên lập kế hoạch nâng cấp theo hướng dẫn chính thức thay vì coi dump/load là toàn bộ chiến lược migration.

## 12. Docker: file archive và database nằm trên volume nào?

Trong Docker, quá trình database có thể đang chạy trong container với volume `/data`. Để dump khi database offline, tài liệu Neo4j minh họa khởi tạo **container admin tạm** trỏ tới cùng volume data và volume dump.

Ví dụ **mô hình lab**, trên Linux, sau khi container Neo4j chính đã dừng hoàn toàn:

~~~bash
# BẢN MẪU: thay volume host và image theo deployment thật.
docker run --rm \
  --volume=/srv/lab-neo4j/data:/data \
  --volume=/srv/lab-neo4j/dumps:/backups \
  neo4j/neo4j-admin:2026.10.2 \
  neo4j-admin database dump neo4j --to-path=/backups
~~~

Sau khi có archive, dùng **một volume data mới** cho target restore:

~~~bash
# ĐÍCH TEST MỚI: không mount volume data nguồn.
docker run --rm \
  --volume=/srv/lab-neo4j/restored-data:/data \
  --volume=/srv/lab-neo4j/dumps:/backups \
  neo4j/neo4j-admin:2026.10.2 \
  neo4j-admin database load neo4j --from-path=/backups
~~~

**Quan trọng:**

- Hai volume `data` và `restored-data` phải thực sự khác nhau.
- Container Neo4j đang dùng volume nguồn không được tiếp tục ghi trong lúc admin dump store.
- Version image admin phải phù hợp với version database; các số version trên chỉ là mẫu từ tài liệu, **không phải khuyến nghị nâng cấp**.
- Quyền owner/permission của volume cần tương thích với user Neo4j; tránh để file tạo bằng root rồi process Neo4j không khởi động được.
- Dump archive cần được chuyển và lưu ở vị trí riêng, không chỉ nằm trong layer dễ mất của container.
- Với cluster/Kubernetes, tham khảo Helm/operator và hướng dẫn backup đúng topology; không chạy một container admin cùng lúc trên volume đang mounted bởi server khác.

## 13. Kubernetes và cluster: không làm theo quy trình standalone

### 13.1. Kubernetes

Neo4j trên Kubernetes có thể sử dụng PVC, StatefulSet, các container được operator/Helm chart quản lý. Để dump/load:

1. Xác định PVC dữ liệu và vị trí archive.
2. Đưa database vào **offline maintenance mode** theo hướng dẫn deployment.
3. Dùng công cụ trong image cùng phiên bản, với volume mounts được xác nhận.
4. Chỉ load lên một **đích thử nghiệm** hoặc môi trường phục hồi được quản trị.
5. Xác minh pod, database status, quyền volume và truy vấn ứng dụng sau phục hồi.

Không tự xóa PVC, scale ngẫu nhiên hoặc thay pod của production để “làm cho load chạy được”. Tác động tới volume có thể lớn hơn thao tác Cypher thông thường.

### 13.2. Cluster Enterprise

Một cluster còn có metadata về membership, identity và trạng thái của database. Khi seed cluster từ một dump và database cùng tên đã tồn tại trong cluster state, việc **load đè file cục bộ mà không xử lý catalog/topology đúng cách có thể gây logical corruption**.

Tài liệu hiện hành khuyến nghị dùng phương pháp **tạo/khôi phục database từ URI** hoặc quy trình designated seeder phù hợp. Không chạy `neo4j-admin database load --overwrite-destination=true` lần lượt trên từng node của cluster như trên standalone; và không đề xuất `DROP DATABASE` cluster mà chưa có runbook/backup/approval riêng.

**Composite database** không phải đích hỗ trợ trực tiếp cho một số lệnh dump/load; thao tác trên các database thành phần được công cụ hỗ trợ, với quy trình phù hợp topology.

## 14. Database system, users/roles và những gì không tự được bao gồm

Một archive dump của database user như `neo4j` chủ yếu chứa **dữ liệu database**, bao gồm graph/schema của database đó theo định dạng store. Nó **không đồng nghĩa đã sao lưu toàn bộ DBMS**, bởi vì:

- User và role metadata liên quan thường thuộc **system database**, không nằm trong dump của từng user database.
- Cấu hình `neo4j.conf`, biến môi trường, secret manager, chứng chỉ TLS, plugin JAR (APOC, GDS hoặc plugin riêng), container manifest và policy mạng có lifecycle riêng.
- Full-text/vector index, analyzer hoặc procedure phụ thuộc plugin/version đích cần kiểm tra tương thích sau restore.
- Thông tin route/topology của cluster không thể được phục hồi bằng cách chép store một cách tùy tiện.

Với chiến lược DR toàn DBMS, tài liệu Neo4j yêu cầu **lập kế hoạch backup từng database, bao gồm `system`** khi phù hợp với phiên bản và cách triển khai. Tuy nhiên:

**Không load/overwrite `system` trên DBMS hiện hữu chỉ để “khôi phục role”.** Database `system` chứa trạng thái quản trị nhạy cảm; phục hồi sai có thể ảnh hưởng database catalog, user/role và khả năng đăng nhập. Hãy dùng runbook riêng được kiểm chứng trên bản/edition tương ứng.

Sau khi restore user database, cần đối soát:

| Thành phần | Kiểm tra sau load |
|---|---|
| Node, relationship, property | Count, checksum logic hoặc dữ liệu nghiệp vụ mẫu |
| Constraints/indexes | `SHOW CONSTRAINTS`, `SHOW INDEXES`, trạng thái `ONLINE` |
| Users/roles | Quyền đăng nhập và READ/WRITE/EXECUTE; có cần khôi phục riêng metadata không |
| Java Driver | URI, database name, TLS, read/write, query parameter hóa |
| Spring Data Neo4j | Entity mapping, repository, relationship hydration, transaction |
| Plugins và extensions | Đã cài bản tương thích và cấu hình quyền phù hợp |
| Backup configuration | Lịch backup, retention, encryption, monitoring đã hoạt động lại |

## 15. Kiểm chứng archive: kiểm tra ba tầng

### Tầng 1 — File vật lý

- File tồn tại, không có lỗi ghi, kích thước khác 0.
- Checksum khớp sau truyền file giữa host/object storage.
- Quyền file, user/group sở hữu và mã hóa đáp ứng chính sách.
- Tên thư mục, phiên bản tool, database nguồn và thời điểm dump được ghi trong manifest.
- Dung lượng đích đủ cho việc extract/load và tạo index/recovery nếu phát sinh.

### Tầng 2 — Định dạng và tương thích

~~~bash
# Chỉ xem metadata; không load.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps --info
~~~

Ghi định dạng và metadata mà bản lệnh cung cấp. Chạy `neo4j-admin database load --help` nếu phiên bản khác. **Archive đọc được metadata vẫn có thể lỗi khi load** do store incompatibility, thiếu dung lượng hoặc file hỏng.

### Tầng 3 — Restore thực và xác minh nghiệp vụ

Trên instance test cô lập, sau load/start:

~~~cypher
MATCH (i:QA003ArchiveItem)
WITH count(i) AS items, sum(i.score) AS scores
MATCH (o:QA003ArchiveOwner)
WITH items, scores, count(o) AS owners
MATCH ()-[r:QA003_OWNED_BY]->()
RETURN items, scores, owners, count(r) AS relationships;
~~~

Kết quả mong đợi từ fixture: **5 / 150 / 2 / 4**. Truy vấn thêm item 5 và xác nhận không có owner:

~~~cypher
MATCH (i:QA003ArchiveItem {itemId:5})
OPTIONAL MATCH (i)-[:QA003_OWNED_BY]->(o)
RETURN i.itemId AS itemId, count(o) AS owners;
~~~

**Đáp án:** `itemId=5` và `owners=0`. Kiểm tra thêm ngày `recordedOn` bằng query:

~~~cypher
MATCH (i:QA003ArchiveItem {itemId:1})
RETURN i.recordedOn AS recordedOn, i.score AS score;
~~~

**Đáp án:** `recordedOn = date('2026-11-01')` và `score=10`.

Không chỉ kiểm tra `RETURN 1` hoặc dòng “database online”. Database có thể khởi động được nhưng không phải database bạn định khôi phục, hoặc thiếu schema/plugin/role.

## 16. Kiểm chứng từ Java Driver và Spring Data Neo4j

### 16.1. Java Driver phải chỉ đúng database phục hồi

Một chương trình Java có thể kết nối thành công nhưng mặc định dùng **home database** khác database test đã restore. Nên chỉ định tường minh:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public static long restoredCount(
        Driver driver, String database) {
    try (Session session = driver.session(
            SessionConfig.forDatabase(database))) {
        return session.executeRead(tx ->
            tx.run("""
                MATCH (i:QA003ArchiveItem)
                RETURN count(i) AS total
                """).single().get("total").asLong()
        );
    }
}
~~~

**Đáp án:** `restoredCount(driver, "neo4j") == 5` nếu đó đúng là database test chứa fixture, user đủ quyền và dữ liệu đã load chính xác. Đoạn code này không thay thế đối soát relationship/schema nhưng giúp phát hiện lỗi chọn nhầm database trong ứng dụng Java.

### 16.2. Spring Data Neo4j

Ở Spring Data Neo4j, cấu hình database, repository/entity mapping và transaction manager cần được kiểm tra riêng:

- Repository có đọc được node `QA003ArchiveItem` bằng khóa nghiệp vụ hay không?
- Entity có khôi phục đúng `LocalDate recordedOn`, `score` và relationship owner không?
- Các custom `@Query` còn tương thích với Cypher runtime/index ở phiên bản đích?
- User/role có đủ quyền để thực hiện `MERGE`, query `MATCH` và schema migration do ứng dụng sử dụng?
- Transaction sau restore có commit và rollback theo kỳ vọng không?

Nếu dump được chuyển sang Neo4j release khác, smoke test Java/SDN có thể phát hiện vấn đề compatibility mà chỉ nhìn số lượng node không nhận ra.

## 17. Phân biệt dump với RPO/RTO và kế hoạch lưu trữ lâu dài

**RPO (Recovery Point Objective)** là mức mất dữ liệu theo thời gian tối đa mà nghiệp vụ cho phép. **RTO (Recovery Time Objective)** là mục tiêu thời gian phục hồi dịch vụ.

Ví dụ **giả định**:

- Cứ 24 giờ mới tạo offline dump một lần.
- Một lỗi xảy ra 23 giờ sau dump cuối.
- Nếu chỉ có dump đó và không có cơ chế recovery khác, bản dữ liệu sẵn sàng có thể cũ gần **23 giờ**.
- Quá trình download, load, start và kiểm tra ứng dụng mất **70 phút** trong một lần diễn tập.

Ở điều kiện giả định trên, chiến lược này **không đáp ứng** RPO 5 phút hoặc RTO 30 phút. Nếu nghiệp vụ cần ít downtime, cân nhắc online backup Enterprise, backup chain và topology phù hợp thay vì liên tục dừng database để dump.

### 17.1. Dump có thay thế backup chiến lược không?

Dump là một **cơ chế tạo archive đầy đủ** trong điều kiện được hỗ trợ, có thể là một phần chiến lược phục hồi. Nhưng nếu chỉ giữ một file trên cùng máy:

- Khi mất máy/volume, cả database và archive có thể mất.
- Khi bị xóa nhầm hoặc ransomware, archive cũng có thể bị ảnh hưởng.
- Khi file bị hỏng, không có bản thay thế.
- Khi không thử load, không ai biết RTO thực tế hoặc có thể phục hồi được không.

Cần bản sao khác failure domain, phiên bản/archive retention, kiểm soát quyền, checksum và định kỳ restore test.

### 17.2. Dung lượng và tốc độ

Thời gian offline thực tế có thể bao gồm:

\[
T_{\text{downtime}} \approx
T_{\text{stop}} + T_{\text{dump/load}} +
T_{\text{start}} + T_{\text{verify}} + T_{\text{cutover}}
\]

Công thức chỉ là mô hình planning; một số bước có thể chạy song song trên instance khác. Thời gian dump phụ thuộc store, index, filesystem, mức nén/archive, I/O và CPU; load còn chịu chi phí giải nén, ghi dữ liệu, recovery và khởi động. **Không suy thời gian chỉ từ số node** hoặc từ throughput tối đa quảng cáo của SSD.

## 18. Lỗi thường gặp khi dump và load

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý an toàn |
|---|---|---|
| `Unrecognized command: database dump` | Đang dùng neo4j-admin 4.4 hoặc binary khác | Xem `--version`/`--help`; dùng syntax đúng release |
| `Unknown option --to-path` | Dùng cú pháp mới trên binary cũ | 4.4 thường dùng `--to=/file.dump` |
| `--from-path` không tìm thấy archive | Truyền file thay vì thư mục, sai tên database/file, sai quyền | Kiểm tra directory, output dump, `--info` và quyền OS |
| `Database is in use` / cannot dump | Database đang được mounted hoặc process còn giữ file | Dừng đúng database/DBMS theo edition; không ép copy file đang chạy |
| Permission denied ở dump folder | OS user chạy tool không được ghi | Sửa ownership/ACL tối thiểu, không mở world-readable |
| Load từ chối vì database đã tồn tại | Default không overwrite | Xác minh target; tránh thêm flag ghi đè khi chưa phê duyệt |
| Load thành công nhưng database không ONLINE | Chưa start/đăng ký, lỗi config, store migration hoặc thiếu quyền | Kiểm tra catalog/log, quy trình Enterprise/Community và version |
| Query trả 0 node sau restore | Chọn nhầm database, archive khác hoặc dữ liệu nguồn khác | Chỉ rõ `SessionConfig.forDatabase`, đối chiếu manifest và fixture |
| Java/SDN kết nối nhưng bị permission denied | User/role metadata không đi cùng user DB dump | Kiểm tra quyền trên DBMS đích, restore RBAC đúng quy trình |
| Index chưa ONLINE | Index đang population hoặc môi trường khác | `SHOW INDEXES`, đợi online trước kiểm thử hiệu năng |
| Cluster xuất hiện lỗi store/state sau load | Chép store không theo topology/cluster procedure | Dừng thao tác; dùng URI/seed/recovery theo hướng dẫn cluster |
| 4.4 archive không tương thích target mới | Bỏ qua lộ trình migration/store-format | Thực hiện migration phiên bản được hỗ trợ, giữ dump gốc |
| Checksum khác sau truyền | Truyền thiếu/hỏng, nhầm artifact | Không load; chuyển lại bản đúng, xác minh nguồn |
| Dump tạo được nhưng backup không đáp ứng RPO | Tần suất dump quá thưa, cần downtime | Thiết kế online backup/retention và thử restore theo RPO/RTO |

**Quy tắc xử lý lỗi:** không dùng `--overwrite-destination=true`, không xóa store directory và không load lại `system` theo phản xạ. Ghi log lỗi và xác minh nguyên nhân trên một môi trường không có dữ liệu không thể thay thế.

## 19. Kỹ thuật quản lý archive: naming, checksum và bảo mật

Một bộ artifact có thể gồm:

~~~text
offline-dumps/
  run-2026-11-25T020000Z/
    neo4j.dump                 # Tên chỉ mang tính minh họa.
    manifest.txt               # Metadata vận hành quản lý riêng.
    sha256.txt                 # Checksum của artifact.
~~~

Tùy phiên bản, tên dump thực tế có thể gồm timestamp hoặc nhiều phần. **Đừng đổi tên tùy ý** khi công cụ load dựa vào cấu trúc/tên artifact; xác minh trước và giữ nguyên nội dung gốc.

Manifest nên lưu:

| Trường | Ví dụ cần ghi |
|---|---|
| Run ID, thời gian UTC | `run-2026-11-25T020000Z` |
| Database/source DBMS | `neo4j / lab-db-01` |
| Neo4j edition/version/tool | `5.x, Community, admin cùng version` |
| Trạng thái offline và bước kiểm soát | `DBMS stopped / verified` |
| Archive path, size, SHA-256 | Path thực, byte count, digest |
| Query baseline | 5 item, 2 owner, 4 relationship, sum score 150 |
| Constraint/index inventory | Tên, loại, trạng thái |
| Lịch backup retention và nơi lưu thứ hai | Đối tượng sở hữu, chính sách |
| Kết quả thử restore | Thời gian, validation PASS/FAIL |
| RPO/RTO và phạm vi phục hồi | Mốc dữ liệu, giới hạn |

Không ghi mật khẩu, private key hoặc token vào manifest. Các file dump chứa dữ liệu nghiệp vụ phải được mã hóa/truy cập theo principle of least privilege. Nếu cần lưu ở cloud, xác minh tính năng đọc/ghi object storage của **đúng phiên bản**; không mặc định mọi bản Neo4j 5 đều có mọi URI cloud mới.

## 20. Mẫu runbook vận hành có điểm dừng

**Giai đoạn trước cửa sổ bảo trì**

1. Chủ sở hữu phê duyệt database nguồn/đích và mục tiêu phục hồi.
2. Xác minh edition/version/tool và compatibility.
3. Chạy baseline query dữ liệu/schema, lưu kết quả.
4. Xác minh tài nguyên đĩa, archive destination, quyền và backup trước đó.
5. Chuẩn bị instance restore độc lập và quyền truy cập đến archive.

**Giai đoạn dump**

6. Ngừng ghi và đưa database vào offline theo quy trình phù hợp edition.
7. Chạy `database dump` hoặc legacy `dump` theo công cụ thực.
8. Xác minh exit code, archive, metadata và checksum.
9. Nếu nguồn cần phục vụ lại, chỉ mở sau khi đã xác minh dump; ghi thời điểm downtime.

**Giai đoạn restore test**

10. Chuyển archive/checksum sang đích độc lập, kiểm tra trùng khớp.
11. Xác nhận database đích offline, không có dữ liệu cần giữ hoặc đã có bản backup trước khi overwrite.
12. Chạy `database load`, đăng ký/start database đúng cách.
13. Đối chiếu node/relationship/property/schema và smoke test Java/SDN.
14. Nếu fail, dừng cutover, lưu log, phân tích và quay lại trạng thái đích ban đầu.
15. Nếu pass, ghi version và thời gian restore thực, cập nhật RPO/RTO, lưu audit trail.

### Tiêu chí hoàn thành

Một đợt dump/load chỉ được báo **PASS** nếu đủ:

- Archive có thể đọc/load bằng tool được hỗ trợ.
- Database đích đã hoạt động và đúng tên.
- Các đáp án dữ liệu, relationship, temporal property và schema cần thiết khớp baseline.
- Ứng dụng qua Java Driver/SDN có thể đọc/ghi đúng quyền (nếu thuộc phạm vi kiểm tra).
- Quy trình rollback, bảo mật artifact và khả năng restore lại đã được chứng minh.

Chỉ thấy “command exited 0” là **chưa đủ**.

## 21. Bài tập có đáp án

### Bài 1 — Chọn đúng cú pháp

Một máy đang chạy Neo4j 5.26. Kỹ sư thử `neo4j-admin dump --database=neo4j --to=/x/neo4j.dump` và nhận thông báo lệnh không tồn tại. Cú pháp nào phù hợp?

**Đáp án:** kiểm tra `neo4j-admin database dump --help` và sử dụng `neo4j-admin database dump neo4j --to-path=/x`, trong đó `/x` là **thư mục**, sau khi database đã offline.

### Bài 2 — Edition và downtime

Một Neo4j Community đang phục vụ request. Có thể chạy dump với DBMS đang tiếp tục online như một thao tác online backup không?

**Đáp án:** Không. Theo tài liệu Neo4j hiện hành, Community chỉ chạy `database dump` khi DBMS offline. Phải chuẩn bị cửa sổ bảo trì hoặc kiến trúc backup phù hợp.

### Bài 3 — Info có phải restore test?

`neo4j-admin database load neo4j --from-path=/x --info` in metadata hợp lệ. Có thể tuyên bố backup chắc chắn phục hồi được không?

**Đáp án:** Chưa. `--info` không load; cần thử load trên instance độc lập, start database và đối chiếu node/relationship/schema/ứng dụng.

### Bài 4 — Đáp án fixture

Database trước dump chứa năm item có score 10,20,30,40,50; hai owner; bốn relationship. Sau load, query đối chứng phải cho kết quả nào?

**Đáp án:** `items=5`, `scores=150`, `owners=2` và `relationships=4`. Item ID 5 có `owners=0`.

### Bài 5 — Quyền của user sau load

Sau khi load user database vào một DBMS mới, ứng dụng mất quyền truy cập dù dữ liệu và constraint vẫn đúng. Vì sao?

**Đáp án:** Dump user database không tự bao gồm metadata user/role và toàn bộ DBMS config; cần thiết lập/phục hồi RBAC và security state theo quy trình system database/edition.

### Bài 6 — Ghi đè đích

`database load` từ chối vì database đã tồn tại. Có nên lập tức thêm `--overwrite-destination=true`?

**Đáp án:** Không. Phải xác minh instance/database đích, giữ backup độc lập của đích, đưa database offline, đánh giá tác động và có phê duyệt. Flag overwrite có thể thay thế dữ liệu cần giữ.

### Bài 7 — Lưu tệp trong Docker

Một container dump tạo `neo4j.dump` trong filesystem layer tạm, sau khi container bị xóa không còn file. Sai ở đâu?

**Đáp án:** Archive không được mount sang volume/persistent storage. Dùng volume dump riêng và sao chép ra failure domain khác; container tạm chỉ nên xử lý công việc, không là nơi lưu bản sao duy nhất.

### Bài 8 — Cluster restore

Kỹ sư định load cùng một archive đè vào data directory của từng thành viên cluster đang giữ database cùng tên. Hành động hợp lý?

**Đáp án:** Không thực hiện. Cần quy trình restore cluster bằng URI/seed và quản lý state/topology. Ghi đè file store đơn thuần có thể làm trạng thái cluster không nhất quán.

### Bài 9 — Tính RPO/RTO

Dump duy nhất lúc 00:00, lỗi lúc 20:00, phục hồi test mất 50 phút. Nếu nghiệp vụ yêu cầu RPO 10 phút và RTO 20 phút, cách này đạt không?

**Đáp án:** Không. Bản dump có thể cũ **20 giờ** và thời gian restore thực **50 phút**, đều vượt mục tiêu. Cần thay đổi chiến lược backup/recovery và đo lại.

### Bài 10 — Phục hồi để nâng cấp

Có dump từ Neo4j 4.4 và một server Neo4j 2026. Có nên load thẳng rồi mặc định không cần migrate?

**Đáp án:** Không. Phải theo lộ trình migration được hỗ trợ, kiểm tra tương thích store/archive/tool và quy trình roles/plugins/config. Không mặc định load thành công tương đương nâng cấp hoàn tất.

### Bài 11 — Dump hay online backup?

Một doanh nghiệp không được phép ngắt giao dịch trong giờ làm việc, muốn tạo điểm phục hồi thường xuyên. Nên dùng offline dump liên tục không?

**Đáp án:** Offline dump gây downtime cho database nguồn; với yêu cầu online, xem `neo4j-admin database backup` của Enterprise hoặc phương án vận hành được hỗ trợ, kèm retention và restore drills.

## 22. Dọn fixture (chỉ trên database test)

Sau khi đã hoàn tất kiểm thử phục hồi và không còn cần bằng chứng dữ liệu, có thể dọn **đúng fixture** trên instance lab. **Không chạy** nếu những label demo đã được sử dụng cho dữ liệu thật.

~~~cypher
MATCH (n)
WHERE n:QA003ArchiveItem OR n:QA003ArchiveOwner
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa003_archive_item_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa003_archive_owner_id IF EXISTS;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA003ArchiveItem OR n:QA003ArchiveOwner
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining = 0`. Cleanup sau restore **không sửa file dump đã có**; nếu muốn tạo bản dump mới từ trạng thái đã dọn, đó là một đợt backup khác và phải ghi run ID mới.

## 23. Tài liệu chính thức và ghi nhớ

- [Neo4j Operations — Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/): cú pháp `neo4j-admin database dump`, điều kiện edition/offline, đích archive và an toàn file.
- [Neo4j Operations — Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/): `database load`, `--info`, `--from-path`, overwrite, đăng ký database và rủi ro cluster.
- [Neo4j Operations — Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/): bảng so sánh backup/restore với dump/load/copy, yêu cầu downtime và capability.
- [Neo4j Operations — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/): full/differential backup, metadata RBAC và giới hạn dump.
- [Neo4j Operations — Docker: dump and load](https://neo4j.com/docs/operations-manual/current/docker/dump-load/): dùng container admin tạm và mount volume.
- [Neo4j Operations — Kubernetes: dump/load](https://neo4j.com/docs/operations-manual/current/kubernetes/operations/dump-load/): offline maintenance trong Kubernetes.
- [Neo4j Operations — Neo4j admin tool](https://neo4j.com/docs/operations-manual/current/neo4j-admin-neo4j-tools/): cú pháp các nhóm lệnh, `--version`, `--help` và quyền OS.
- [Neo4j Upgrade and Migration Guide — Migrate 4.4 to 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/): lộ trình tương thích và cách chuẩn bị database/roles.
- [Neo4j Upgrade and Migration Guide — Legacy 4.4 syntax](https://neo4j.com/docs/upgrade-migration-guide/current/version-4/migrate-community-enterprise/): ví dụ `neo4j-admin dump`/`load` đời 4.4.

**Ghi nhớ:** **Chọn công cụ theo version thực của DBMS**, không theo ví dụ của phiên bản khác hoặc Java Driver. `dump` chỉ có ý nghĩa khi database nguồn ở trạng thái offline được hỗ trợ; `load` phải hướng tới database đích offline và đúng instance. **Không mặc định ghi đè**, không load file cục bộ tùy tiện vào cluster, và không coi archive của user database là bản sao toàn bộ user/role/config. Chỉ khi **restore thử thành công và đối soát dữ liệu, schema, quyền, ứng dụng** mới có cơ sở tin rằng bản dump hỗ trợ phục hồi thực tế.
