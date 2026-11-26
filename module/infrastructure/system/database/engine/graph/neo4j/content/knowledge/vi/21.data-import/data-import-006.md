# Neo4j Admin Import và điều kiện sử dụng cho khối lượng lớn

## 1. Khi nào nên dùng Neo4j Admin Import?

Trong một hệ thống dùng **property graph**, dữ liệu không chỉ gồm các node như `Customer`, `Company`, `Product` mà còn gồm rất nhiều relationship như `PURCHASED`, `MEMBER_OF` và `SUPPLIES`. Với vài triệu đến hàng tỷ node hoặc relationship, việc gửi từng lệnh `CREATE` qua Cypher có thể tốn thời gian vì phải xử lý transaction, tra cứu node đầu mút, cập nhật index và đi qua giao thức client/server.

`neo4j-admin database import` là công cụ dòng lệnh để **nạp dữ liệu số lượng lớn trực tiếp vào định dạng lưu trữ của Neo4j**. Nó đọc đầu vào đã chuẩn hóa, dựng node và nối relationship theo các mã định danh trong nguồn dữ liệu. Thay vì mở hàng triệu transaction Cypher, importer tối ưu quá trình xây dựng database từ tập dữ liệu đầu vào.

Chọn `neo4j-admin database import full` chủ yếu khi:

- Cần **nạp dữ liệu ban đầu** vào database chưa tồn tại hoặc chưa có dữ liệu cần giữ.
- Số lượng thực thể và liên kết đủ lớn để hiệu suất nhập trở thành yếu tố quan trọng.
- Có **quyền chạy công cụ quản trị trên máy chủ Neo4j** và có cửa sổ vận hành phù hợp.
- Dữ liệu đầu vào có thể được làm sạch, xác định khóa cho node, kiểm tra tham chiếu giữa các bảng trước khi chạy.
- Muốn dựng một graph lớn từ hệ thống khác như cơ sở dữ liệu quan hệ, kho dữ liệu hoặc tệp CSV/Parquet.

**Không dùng full import để bổ sung vài bản ghi vào database đang phục vụ ứng dụng**. Chế độ full được thiết kế cho nạp ban đầu; nếu ép ghi đè database đã có, dữ liệu đích có thể bị thay thế hoàn toàn. Với dữ liệu thay đổi liên tục, ưu tiên `LOAD CSV` theo lô, Java Driver, Spring Data Neo4j hoặc một quy trình incremental import được hỗ trợ.

## 2. Phân biệt các cách nhập dữ liệu

| Phương pháp | Cơ chế | Khi phù hợp | Điều kiện đáng chú ý |
| --- | --- | --- | --- |
| `neo4j-admin database import full` | Dựng các tệp lưu trữ Neo4j từ dữ liệu nguồn | Nạp ban đầu hàng triệu/hàng tỷ thực thể | Có quyền trên máy chủ; database đích chưa tồn tại hoặc được xử lý theo quy trình offline |
| `neo4j-admin database import incremental` | Thêm hoặc cập nhật lượng dữ liệu lớn theo quy trình riêng | Database đã có dữ liệu, cần import bổ sung ở quy mô lớn | **Enterprise Edition**, constraint thích hợp, các giai đoạn bảo trì; có giới hạn theo phiên bản/format |
| `LOAD CSV ... CALL { ... } IN TRANSACTIONS` | Cypher đọc CSV và commit theo các lô | Dữ liệu vừa/lớn; cần logic `MERGE`, biến đổi, cập nhật graph hiện có | Gửi query trong **implicit transaction**; phải thiết kế retry khi commit một phần |
| Java Driver / Spring Data Neo4j | Ứng dụng gửi Cypher qua Bolt và quản lý transaction | Ghi nghiệp vụ liên tục, API, sự kiện và batch có quy tắc phức tạp | Tối ưu số lần gọi, kích thước transaction và index |
| Công cụ nhập giao diện / dịch vụ quản lý | Ánh xạ tệp và dữ liệu bằng UI/connector | Nhập mang tính tương tác, dịch vụ không cấp quyền chạy `neo4j-admin` | Khả năng và giới hạn tùy dịch vụ |

**Admin import không phải một câu lệnh Cypher**. Không thể chạy `neo4j-admin database import full` trong `session.run(...)`, `@Query` hay Neo4j Browser. Nó được chạy tại terminal của môi trường có cài Neo4j; Java Driver hoặc Spring Data Neo4j được dùng **sau khi database sẵn sàng** để truy vấn và kiểm tra graph.

## 3. Cơ chế full import và các điều kiện bắt buộc

### 3.1. Nạp trực tiếp vào store

Luồng xử lý ở mức khái niệm:

```text
Nguồn dữ liệu
    |
    +-- users.csv        --> Node :User
    +-- companies.csv    --> Node :Company
    +-- memberships.csv  --> Relationship :MEMBER_OF
    |
    v
Chuẩn hóa header, kiểu dữ liệu, ID space và tính toàn vẹn
    |
    v
neo4j-admin database import full
    |
    +-- Tạo node + ánh xạ ID nguồn
    +-- Liên kết relationship theo START_ID/END_ID
    +-- Ghi dữ liệu ra native store của Neo4j
    |
    v
Database có thể được đăng ký/khởi động
    |
    v
Kiểm tra số lượng, relationship, schema và truy vấn Cypher
```

Tập dữ liệu sạch và một mô hình ID rõ ràng quan trọng hơn việc thử tăng số luồng import vô điều kiện.

### 3.2. Điều kiện về database đích

- **Database chưa tồn tại** là trường hợp đơn giản nhất để học và triển khai full import. Sau khi importer ghi các store file, cần tạo/đăng ký database bằng lệnh quản trị phù hợp; công cụ import **không tự tạo database trong system catalog**.
- Nếu database đã tồn tại, công cụ chỉ cho phép thay thế khi bật `--overwrite-destination`. Tùy chọn này **xóa các tệp database đích đang có trước khi nhập**. Chỉ sử dụng theo một kế hoạch thay thế có backup và cửa sổ offline đã được phê duyệt.
- Nếu target đã tồn tại, phải **stop database đó** trước full import. Việc chạy công cụ trên DBMS đang phục vụ những database khác có thể khả thi tùy triển khai, nhưng database đích không được vừa bị ghi vừa bị thay store.
- Importer cần quyền đọc nguồn và quyền ghi các thư mục dữ liệu/log tương ứng. Nó chạy trong môi trường máy chủ, không mặc nhiên nhìn thấy file trong máy cá nhân đang mở Neo4j Browser.
- Neo4j AuraDB và các dịch vụ được quản lý thường **không cấp terminal/neo4j-admin** cho người sử dụng; cần chọn cơ chế nhập mà dịch vụ hỗ trợ.

Trong bài này dùng database **`supplygraph` chưa tồn tại** để tránh ảnh hưởng dữ liệu cũ. Các lệnh shell đều là ví dụ cho môi trường thử nghiệm có quyền quản trị; không nên thực thi trực tiếp trên hệ thống sản xuất mà chưa xác định đường dẫn, edition, database đích và bản sao lưu.

### 3.3. Full và incremental không thể thay thế tùy ý

`neo4j-admin database import incremental` là một chế độ khác, **chỉ có trong Enterprise Edition**. Nó đòi hỏi database đích **đã tồn tại**, khóa định danh có uniqueness constraint phù hợp và `--force` theo tài liệu sản phẩm. Có thể chạy theo một lệnh khi database dừng, hoặc chia thành các bước `prepare` → `build` → `merge`.

Với incremental theo giai đoạn, `prepare` và `merge` cần database ở trạng thái dừng; `build` có thể xử lý với database ở chế độ read-only. Theo phiên bản/record format, chế độ incremental còn có giới hạn về khả năng cập nhật/xóa node, label, relationship và thuộc tính; không được mặc định xem nó là `MERGE` Cypher trực tuyến. Các tính năng cập nhật/xóa qua `:ACTION` từ Neo4j 2025.01 chỉ hỗ trợ **block format**.

**Trước incremental import phải backup đầy đủ**. Lỗi hoặc hủy trong giai đoạn merge có thể khiến database không còn nhất quán. Phạm vi bài này tập trung vào **full import**, còn incremental cần quy trình vận hành chuyên biệt và đọc tài liệu đúng phiên bản.

## 4. Chuẩn bị CSV cho node và relationship

### 4.1. Graph mẫu

Giả sử một nền tảng B2B quản lý nhân viên và doanh nghiệp:

```text
(:User {userId, name})-[:MEMBER_OF {since}]->(:Company {companyId, name})
```

Ta có ba người dùng và hai công ty. Quan hệ `MEMBER_OF` mang thuộc tính ngày bắt đầu `since`.

Điểm khác biệt lớn giữa import và `LOAD CSV`: importer **không dùng `MATCH` để tìm đầu mút quan hệ**. Thay vào đó, các file node khai báo khóa bằng `:ID` và file relationship khai báo `:START_ID`, `:END_ID`.

### 4.2. `users.csv`: node User

```csv
userId:ID(UserIds),name,:LABEL
u001,An,User
u002,Bình,User
u003,Chi,User
```

Định nghĩa header:

- `userId:ID(UserIds)`: cột ID của node, thuộc **ID space `UserIds`**; do có tên `userId`, mã này đồng thời được lưu thành thuộc tính `userId` của node.
- `name`: thuộc tính chuỗi `name`.
- `:LABEL`: label của node, ở đây là `User`. Một node có nhiều label thì dùng dấu phân tách mảng thích hợp, mặc định `;`.

### 4.3. `companies.csv`: node Company

```csv
companyId:ID(CompanyIds),name,:LABEL
c001,Acme,Company
c002,Northwind,Company
```

Việc dùng **ID space riêng** giúp phân biệt `UserIds` và `CompanyIds`, nhất là nếu cả hai nguồn sử dụng khóa số tự tăng `1`, `2`, `3`. Đừng nhầm ID space với label hoặc tên property: chúng phục vụ ba mục đích khác nhau.

### 4.4. `memberships.csv`: relationship

```csv
:START_ID(UserIds),:END_ID(CompanyIds),:TYPE,since:date
u001,c001,MEMBER_OF,2024-01-15
u002,c001,MEMBER_OF,2024-03-01
u003,c002,MEMBER_OF,2025-06-10
```

Ý nghĩa:

| Header | Vai trò | Ví dụ |
| --- | --- | --- |
| `:START_ID(UserIds)` | Chỉ node đầu, tra trong ID space `UserIds` | `u001` |
| `:END_ID(CompanyIds)` | Chỉ node cuối, tra trong ID space `CompanyIds` | `c001` |
| `:TYPE` | Loại relationship | `MEMBER_OF` |
| `since:date` | Thuộc tính `since` kiểu ngày | `2024-01-15` |

Các dấu ngoặc trong `:START_ID(UserIds)` phải trùng chính xác ID space của file node. Nếu `u001` chưa được khai báo ở file User, relationship tương ứng không thể nối đúng.

### 4.5. Các loại cột và định dạng thường gặp

| Cú pháp trong header | Kiểu dữ liệu | Ví dụ |
| --- | --- | --- |
| `name:string` hoặc `name` | Chuỗi | `An` |
| `age:int` | Số nguyên | `25` |
| `price:float` | Số thực | `149.5` |
| `active:boolean` | Boolean | `true` |
| `createdAt:datetime` | Thời gian | `2026-01-15T09:30:00+07:00` |
| `tags:string[]` | Mảng chuỗi | `neo4j;cypher;graph` |
| `location:point` | Điểm không gian | Cần giá trị point đúng cú pháp và CRS được hỗ trợ |

Trong file CSV của importer, **cột ID dùng để nối quan hệ không phải nội bộ `elementId()` của Neo4j**. Nó là khóa nguồn do bạn định nghĩa để importer tra cứu khi xây dựng relationship. Nếu muốn dùng khóa đó để truy vấn về sau, đặt tên trước `:ID`; nếu header chỉ là `:ID` thì ID vẫn có thể phục vụ import nhưng không nhất thiết được lưu làm thuộc tính node.

**Chuẩn hóa dữ liệu trước khi nhập:**

1. Mỗi ID node phải **duy nhất trong ID space tương ứng**.
2. Mọi `:START_ID` và `:END_ID` của relationship đều phải tham chiếu được đến node đã khai báo.
3. Kiểu cột trong header phải tương thích với giá trị thực; ví dụ `price:float` không thể nhập chuỗi `'một trăm'` như số.
4. Các file dùng đúng encoding (thông thường UTF-8), delimiter, quote escaping và array delimiter. Nội dung có dấu phẩy cần được đặt trong dấu quote.
5. Không vô tình để **hai dòng header** trong cùng một nhóm file. Importer sẽ đọc header ở đầu nhóm; dòng header thứ hai có thể bị hiểu là bản ghi dữ liệu.

## 5. Chạy thử `neo4j-admin database import full`

### 5.1. Giả định môi trường

Các bước sau minh họa với **Neo4j cài trên Linux/macOS từ bản phân phối có thư mục `bin/`**, terminal đang ở `NEO4J_HOME`, database `supplygraph` chưa tồn tại và ba file đầu vào đặt tại:

```text
<NEO4J_HOME>/
├── bin/
│   ├── neo4j-admin
│   └── cypher-shell
└── import/
    ├── users.csv
    ├── companies.csv
    └── memberships.csv
```

Trên Windows, Docker, Kubernetes hoặc Neo4j Desktop, đường dẫn nhị phân, file mount và cách quản lý service sẽ khác; hãy điều chỉnh theo môi trường đó. Tất cả đường dẫn dữ liệu ở đây được Neo4j **server-side process** đọc, không phải URI `file:///` của một câu lệnh `LOAD CSV`.

### 5.2. Xem cú pháp trên phiên bản đã cài

```bash
bin/neo4j-admin database import full --help
```

Xem `--help` trước khi sử dụng tùy chọn mới. Ví dụ `--dry-run` được bổ sung từ **Neo4j 2026.02**; không thể giả định phiên bản Neo4j 5.x cũ cũng nhận cờ này.

### 5.3. Dry run khi phiên bản hỗ trợ

```bash
bin/neo4j-admin database import full \
  --dry-run=true \
  --id-type=string \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

`--dry-run=true` kiểm tra đối số và nguồn đầu vào, đồng thời ước lượng quy mô import mà **không ghi graph**. Nó không phải cam kết mọi dữ liệu nghiệp vụ đều hợp lệ hoặc mọi relationship đều tồn tại: vẫn cần kiểm tra khóa, kiểu dữ liệu và thử import trên môi trường riêng.

### 5.4. Thực hiện full import vào database mới

```bash
bin/neo4j-admin database import full \
  --id-type=string \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

Các tham số:

- `--id-type=string`: ID nhập bằng chuỗi (ví dụ `u001`). Đây là mặc định thông dụng; ghi rõ để tránh nhầm khi đọc ví dụ.
- `--nodes`: mỗi lần khai báo một nhóm file node; một nhóm có thể gồm file header và nhiều file dữ liệu.
- `--relationships`: khai báo một hoặc nhiều nhóm file relationship, hỗ trợ lookup theo ID đã xuất hiện ở node.
- `supplygraph`: tên database đích; đặt **ở cuối câu lệnh** theo cú pháp hiện hành.

Lệnh import thành công tạo **các tệp lưu trữ** cho `supplygraph`. Nếu không có database trong system catalog trước đó, cần thực hiện bước tạo database sau đây; đừng giả định có thể kết nối Bolt ngay chỉ vì import kết thúc với exit code 0.

### 5.5. Đăng ký database và xác minh

Khi DBMS sẵn sàng, kết nối tới `system` bằng một công cụ quản trị phù hợp (ví dụ `cypher-shell -d system -u neo4j`, nhập mật khẩu theo hướng dẫn của công cụ), sau đó:

```cypher
CREATE DATABASE supplygraph IF NOT EXISTS;
```

Nếu bản phân phối/edition hoặc hệ quản trị database đang dùng có hạn chế về việc tạo database, cần làm theo quy trình khởi tạo database tương ứng của môi trường. Khi database đã `ONLINE`, kết nối trực tiếp đến `supplygraph` và kiểm tra:

```cypher
MATCH (u:User)
RETURN count(u) AS users;
```

```cypher
MATCH (c:Company)
RETURN count(c) AS companies;
```

```cypher
MATCH (u:User)-[r:MEMBER_OF]->(c:Company)
RETURN u.userId AS userId,
       c.companyId AS companyId,
       r.since AS memberSince
ORDER BY userId;
```

Với **chỉ dữ liệu ví dụ** và không có bản ghi khác, mong đợi **3 User, 2 Company và 3 relationship `MEMBER_OF`**. Kiểm tra hướng relationship và giá trị `since`, thay vì chỉ nhìn tổng số node.

## 6. Tạo constraint và index sau full import

Ở nhiều phiên bản/format, quy trình chuẩn là **import dữ liệu trước, tạo schema sau**. Trên database `supplygraph`, ví dụ:

```cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.userId IS UNIQUE;
```

```cypher
CREATE CONSTRAINT company_id_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.companyId IS UNIQUE;
```

```cypher
CREATE RANGE INDEX idx_member_since IF NOT EXISTS
FOR ()-[r:MEMBER_OF]-() ON (r.since);
```

Kiểm tra:

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
```

`CREATE CONSTRAINT ... IS UNIQUE` xác nhận giá trị khóa không trùng và tạo backing index tương ứng. Nếu dữ liệu nhập thực tế có khóa trùng, bước tạo constraint sẽ lỗi: đó là dấu hiệu cần sửa dữ liệu, **không phải lý do nên bỏ constraint**.

**Ngoại lệ theo phiên bản:** bắt đầu từ **Neo4j 2025.02**, **Enterprise Edition dùng block format** có thể tạo index/constraint ngay trong quá trình import bằng tùy chọn `--schema`. Không suy rộng tính năng đó sang Community Edition, format khác hoặc phiên bản cũ; với ví dụ ở trên, tạo schema sau import là cách dễ kiểm tra.

## 7. Cấu hình hiệu năng khi nhập dữ liệu lớn

### 7.1. Những tài nguyên quyết định

| Yếu tố | Tác động | Cách xử lý |
| --- | --- | --- |
| Tốc độ ổ đĩa và I/O | Đọc CSV/Parquet, ghi store, tạo và nối relationship | Dùng storage đủ băng thông; theo dõi throughput và I/O wait |
| Dung lượng trống | Dữ liệu đích và file tạm có thể lớn | Dự phòng chỗ trống cho output, temporary data và log |
| RAM/off-heap | Tạo cấu trúc ID lookup, quản lý bộ nhớ import | Điều chỉnh `--max-off-heap-memory` dựa trên RAM thật; không chiếm hết bộ nhớ hệ điều hành |
| JVM heap của admin process | Parsing, cấu trúc quản lý và phần xử lý trên heap | Cấu hình heap riêng cho lệnh admin theo tài liệu phiên bản |
| Số worker `--threads` | Mức song song giữa các bước | Tăng theo CPU/I/O thực tế; quá nhiều thread có thể làm nghẽn đĩa hoặc RAM |
| Tính sạch của dữ liệu | Duplicate ID, endpoint thiếu, sai kiểu gây lỗi hoặc phát sinh báo cáo | Làm sạch trước nhập, đặt tiêu chí lỗi được chấp nhận |
| Cấu trúc ID đầu vào | Lookup và liên kết relationship | Dùng ID space đúng, tránh collision và ép kiểu không cần thiết |

`--max-off-heap-memory` điều khiển ngân sách working memory **ngoài heap** của importer. Không nhầm cờ này với `server.memory.pagecache.size`: tham số page cache của DBMS **không trực tiếp ấn định ngân sách import**.

Ví dụ cú pháp, cần điều chỉnh theo RAM khả dụng:

```bash
bin/neo4j-admin database import full \
  --max-off-heap-memory=8G \
  --threads=8 \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

**Các con số `8G` và `8` chỉ minh họa cú pháp, không phải cấu hình tối ưu phổ quát.** Nếu database đích đã import ở bước trước, không chạy lại lệnh này trên cùng đích như cách benchmark; dùng database thử nghiệm mới hoặc một quy trình thay thế có chủ đích.

### 7.2. Chia file nguồn đúng cách

Một nhóm `--nodes` hoặc `--relationships` có thể gồm một file header và nhiều file dữ liệu. Ví dụ:

```bash
bin/neo4j-admin database import full \
  --nodes=import/users-header.csv,import/users-part1.csv,import/users-part2.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

Trong trường hợp này, `users-header.csv` chứa **chỉ header**, còn `users-part1.csv` và `users-part2.csv` phải có cùng cấu trúc cột và **không chứa header lặp lại**. Đặt header đầu tiên trong nhóm. Có thể dùng pattern tệp trên phiên bản hỗ trợ, nhưng phải hiểu cơ chế sắp xếp và mẫu `regex`/`glob` đang chọn; tránh pattern bắt luôn file header vào dữ liệu.

### 7.3. Format và tính năng mới theo phiên bản

Tài liệu Neo4j hiện hành hỗ trợ đầu vào **CSV** và **Parquet** thông qua `--input-type=csv|parquet`. Với dữ liệu lớn, Parquet có thể hữu ích khi nguồn vốn đã ở dạng cột, nhưng cần mapping và chuẩn bị schema đúng định dạng importer.

Neo4j có các **store format** khác nhau, trong đó `block` có những khả năng Enterprise riêng. Không tự ép `--format=block` nếu deployment/edition chưa hỗ trợ; phải kiểm tra tương thích với phiên bản và mục tiêu vận hành sau import.

**Không có con số “X triệu node/giây” áp dụng cho mọi hệ thống.** Thông lượng phụ thuộc kích thước thuộc tính, số relationship, phân bố endpoint, thiết bị lưu trữ, số luồng, record format và lỗi nguồn. Hãy chạy thử trên tập dữ liệu đại diện và đo thời gian cùng tài nguyên thực tế.

## 8. Làm sạch đầu vào và xử lý bản ghi lỗi

### 8.1. Các nhóm lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
| --- | --- | --- |
| Duplicate node ID | Hai node có cùng ID trong **cùng ID space** | Deduplicate đầu vào hoặc sửa mô hình khóa |
| Relationship trỏ tới node không tồn tại | Sai `:START_ID`, `:END_ID`, ID space hoặc thiếu file node | Đối soát khóa nguồn trước khi import |
| Sai kiểu `int`, `float`, `date` | Header yêu cầu kiểu khác giá trị nhập | Chuẩn hóa dữ liệu hoặc sửa header |
| Header bị đọc như data | File dữ liệu có header lặp sau header của nhóm | Xóa header lặp, kiểm tra thứ tự file |
| Unicode lỗi | File nguồn không đúng encoding, quote hoặc delimiter | Chuyển sang UTF-8 và kiểm tra parser |
| Import không chạy do database đích đã có | Full import mặc định không thay database hiện hữu | Chọn database mới; chỉ overwrite theo kế hoạch thay thế |
| Hết dung lượng hoặc thiếu tài nguyên | Store, file tạm, log hoặc cấu trúc lookup vượt mức còn trống | Ước lượng dung lượng, rà soát disk, RAM, giới hạn thread |

Tùy chọn `--skip-duplicate-nodes` và `--skip-bad-relationships` cho phép bỏ qua một số dòng lỗi, nhưng **không giải quyết nguyên nhân dữ liệu không nhất quán**. Nếu bật, đầu ra có thể thiếu node/relationship quan trọng với nghiệp vụ. Không đặt giá trị `--bad-tolerance` quá cao chỉ để thấy import báo thành công.

### 8.2. Chính sách kiểm tra nghiêm ngặt khi nạp ban đầu

Có thể yêu cầu importer dừng khi gặp bản ghi xấu trong môi trường cần tính đúng cao:

```bash
bin/neo4j-admin database import full \
  --bad-tolerance=0 \
  --strict=true \
  --report-file=import-errors.log \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

- `--bad-tolerance=0`: xác định rõ ngưỡng chấp nhận lỗi dữ liệu có thể bỏ qua, **không cần dựa vào mặc định khác nhau giữa phiên bản**.
- `--strict=true`: kiểm tra chặt tham chiếu relationship đến node, có thể chậm hơn.
- `--report-file`: ghi thông tin lỗi/bản ghi xấu để phân tích; kiểm tra tệp báo cáo trước khi nghiệm thu.

Không phải lỗi nào cũng được bỏ qua theo tolerance: lỗi sai kiểu dữ liệu, file CSV hỏng hoặc thiếu tài nguyên có thể khiến cả import thất bại. Nếu import lỗi, **không dùng graph đích để phục vụ ứng dụng** cho đến khi đã xử lý và xác minh lại dữ liệu.

## 9. Kiểm tra tính đầy đủ và tính đúng sau import

Import báo kết thúc thành công mới là **điều kiện kỹ thuật ban đầu**. Với dữ liệu liên kết, cần kiểm tra số lượng, ID và chất lượng relationship:

### 9.1. Đối soát số lượng

```cypher
MATCH (u:User)
RETURN count(u) AS users;
```

```cypher
MATCH (c:Company)
RETURN count(c) AS companies;
```

```cypher
MATCH ()-[r:MEMBER_OF]->()
RETURN count(r) AS memberships;
```

So sánh kết quả với **số dòng dữ liệu hợp lệ trong file nguồn**, không phải số dòng vật lý nếu file có header hoặc bản ghi bị loại. Nếu dữ liệu rất lớn, kết hợp kiểm tra theo label/type và mẫu truy vấn chọn lọc, đồng thời lưu số liệu từ báo cáo importer.

### 9.2. Kiểm tra khóa và logic nghiệp vụ

```cypher
MATCH (u:User)
WITH u.userId AS id, count(*) AS occurrences
WHERE occurrences > 1
RETURN id, occurrences
ORDER BY occurrences DESC;
```

```cypher
MATCH (u:User)-[:MEMBER_OF]->(c:Company)
RETURN c.companyId AS companyId,
       count(u) AS memberCount
ORDER BY companyId;
```

Cần hiểu mô hình để diễn giải kết quả: một `User` có thể có nhiều `MEMBER_OF` trong lịch sử, vì vậy `count(u)` là **số relationship khớp**, không luôn là số người dùng duy nhất. Nếu muốn đếm người dùng khác nhau, dùng `count(DISTINCT u)`.

### 9.3. Kiểm tra schema và hiệu năng đọc

Sau khi tạo constraint/index:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties;
```

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent;
```

Các index được tạo sau import có thể đang `POPULATING`. Trước khi benchmark hoặc mở lưu lượng lớn, hãy chờ chúng chuyển `ONLINE`; dùng `EXPLAIN`/`PROFILE` trên truy vấn đại diện để xác định planner sử dụng index, số `Rows` và `DB Hits` phù hợp.

## 10. Tích hợp vào quy trình Java/Spring Data Neo4j

### 10.1. Vai trò của ứng dụng

Một ứng dụng Java/Spring thường làm ba nhiệm vụ riêng:

1. **Chuẩn bị nguồn dữ liệu** từ hệ thống nghiệp vụ: xuất CSV/Parquet, chuẩn hóa ID và loại bỏ bản ghi lỗi.
2. **Điều phối vận hành** ở tầng job/CI/CD hoặc công cụ quản trị phù hợp: chạy `neo4j-admin` ở môi trường có quyền truy cập store file, theo dõi log và exit code.
3. **Kiểm chứng và khai thác graph** sau khi database đã `ONLINE`: dùng Java Driver hoặc Spring Data Neo4j để truy vấn, tạo schema migration hoặc tính toán nghiệp vụ.

Không nhúng lệnh `neo4j-admin database import full` vào method repository `@Query`; đó là lệnh shell và có thể thay thế cả database. Thay vào đó, tách bước nhập dữ liệu lớn thành một **quy trình triển khai được điều phối** với backup, điều kiện dừng/khởi động và đối soát.

### 10.2. Ví dụ Java Driver để xác minh dữ liệu đã nhập

Giả sử `Driver driver` đã được tạo bằng cấu hình kết nối Neo4j:

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

try (Session session = driver.session(
        SessionConfig.forDatabase("supplygraph"))) {

    var records = session.executeRead(tx ->
        tx.run(
            """
            MATCH (u:User)-[:MEMBER_OF]->(c:Company)
            WHERE c.companyId = $companyId
            RETURN u.userId AS userId, u.name AS name
            ORDER BY userId
            """,
            Values.parameters("companyId", "c001")
        ).list()
    );

    records.forEach(record -> System.out.println(
        record.get("userId").asString() + ": " +
        record.get("name").asString()
    ));
}
```

`executeRead` phù hợp vì đây là truy vấn chỉ đọc sau import. Ví dụ này giả định database đã được tạo/khởi động và có quyền truy cập. Nếu chạy ngay sau khi file import xong nhưng database chưa `ONLINE`, driver sẽ chưa thể truy vấn.

### 10.3. Spring Data Neo4j

Trong Spring Data Neo4j, có thể ánh xạ `User`, `Company` và relationship `MEMBER_OF` thành entity/relationship properties phù hợp. Tuy nhiên:

- Neo4j Admin Import **không gọi lifecycle callback** hoặc logic validation của repository/entity trong ứng dụng; dữ liệu phải được chuẩn hóa trước.
- Nếu entity mapping yêu cầu property `id` mà CSV nhập vào property `userId`, application có thể không ánh xạ như mong đợi. Cần thống nhất tên trường giữa header CSV, constraint và `@Property`/`@Id` trong Java.
- Spring Data Neo4j không tự thiết lập đúng mọi constraint/index chỉ vì Java entity đã tồn tại; quản lý schema rõ ràng trong migration.
- Sau import, kiểm tra các truy vấn traversal, paging, aggregation và mapping các property kiểu `date`/khác để chắc chắn mô hình sử dụng đúng graph đã nạp.

## 11. Những giới hạn cần hiểu trước khi chọn Admin Import

### 11.1. Không phải công cụ ghi trực tuyến từng bản ghi

`full import` thao tác với store file; không phục vụ API cập nhật theo thời gian thực và không cung cấp semantics `MERGE` trên graph đang chạy. Nếu người dùng liên tục phát sinh đơn hàng hay quan hệ, thiết kế luồng ghi bằng transaction Cypher/driver riêng.

### 11.2. Các thay đổi do admin import không đi qua CDC thông thường

Neo4j Change Data Capture (CDC) **không ghi nhận các thay đổi được tạo bởi `neo4j-admin database import`** như một chuỗi transaction ghi trực tuyến. Nếu hệ thống downstream cần đồng bộ sự kiện thay đổi, phải thiết kế cơ chế công bố snapshot/đối soát hoặc nạp lại dữ liệu phù hợp sau import; không kỳ vọng subscriber CDC nhận từng node/relationship đã được tạo trong quá trình offline.

### 11.3. Quan hệ và thứ tự nguồn dữ liệu quan trọng

Importer cần biết một relationship nối node nào qua ID. Thiếu `:START_ID`, `:END_ID` hoặc khai báo sai ID space sẽ làm mất khả năng nối graph. Không suy ra quan hệ chỉ nhờ hai node có cùng giá trị `name`; định danh và ngữ nghĩa relationship phải được thiết kế từ trước.

### 11.4. Khối lượng lớn không chỉ là số hàng

Một graph có 10 triệu node với vài thuộc tính nhỏ có thể rẻ hơn đáng kể so với 10 triệu node chứa nội dung văn bản lớn và hàng trăm triệu relationship. Khi lập kế hoạch capacity, đếm cả:

- Số node theo label và relationship theo type.
- Số và kích thước thuộc tính trên mỗi thực thể.
- Phân bố bậc quan hệ (*degree*), đặc biệt các node kết nối hàng triệu đầu mút.
- Chi phí xây dựng index/constraint sau khi nạp, thời gian downtime và bước nghiệm thu.

## 12. Quy trình vận hành đề xuất

| Giai đoạn | Việc cần hoàn tất | Tiêu chí kết thúc |
| --- | --- | --- |
| Thiết kế | Xác định node, label, relationship, direction, ID space, kiểu property | Schema nguồn và đích rõ ràng |
| Chuẩn bị | Xuất dữ liệu, làm sạch duplicate/missing endpoint, chuẩn hóa encoding | CSV/Parquet nhất quán và có số liệu đối soát |
| Đánh giá | Chọn full/incremental/Cypher theo dữ liệu và thời gian offline | Công cụ phù hợp edition và yêu cầu cập nhật |
| An toàn | Dùng database mới, backup nếu thay database cũ, xác nhận quyền thư mục | Có phương án phục hồi và đường dẫn chính xác |
| Thử nghiệm | Dry run (nếu có), import trên bản thử nhỏ/đại diện | Báo cáo không có lỗi không chấp nhận |
| Import | Chạy `neo4j-admin database import full`, theo dõi log/tài nguyên | Lệnh hoàn thành, tệp lưu trữ sẵn sàng |
| Đăng ký | Tạo/khởi động database theo môi trường | Database `ONLINE` và kết nối được |
| Hoàn thiện | Tạo schema cần thiết hoặc xác minh schema đã import | Index/constraint hợp lệ, index `ONLINE` |
| Nghiệm thu | So tổng số node/relationship, truy vấn mẫu, hiệu năng Java | Dữ liệu và kết quả nghiệp vụ đúng |

## 13. Sai lầm thường gặp

**“Admin Import giống `LOAD CSV` nhưng nhanh hơn.”** Cả hai đọc dữ liệu ngoài, nhưng khác ở ranh giới vận hành: `LOAD CSV` chạy bằng Cypher trong database hoạt động, còn full import ghi trực tiếp vào store và hướng tới nạp ban đầu.

**“Import full có thể nối thêm vào database đang chạy.”** Full import không phải incremental update; một database hiện có muốn bị thay thế phải dừng và dùng `--overwrite-destination`, nghĩa là dữ liệu cũ có thể bị xóa.

**“CSV có cột `userId` là đủ để nối quan hệ.”** Với Admin Import cần khai báo `:ID` và các cột relationship `:START_ID`/`:END_ID`; khi có nguồn khác nhau cần ID space nhất quán.

**“Chỉ cần bỏ qua bản ghi lỗi để nhập nhanh.”** Bỏ duplicate node hoặc relationship có endpoint thiếu có thể làm sai graph. Quan hệ mất thường nguy hiểm hơn sai số đếm node; phải đối soát và xem report.

**“Import thành công nghĩa là ứng dụng có thể phục vụ ngay.”** Còn bước đăng ký/khởi động database, tạo/kiểm tra constraint/index, đối soát dữ liệu và chạy truy vấn nghiệp vụ.

**“`--max-off-heap-memory` là size page cache của DBMS.”** Importer quản lý ngân sách bộ nhớ riêng; phải xem cấu hình admin process và tài nguyên thực tế.

**“Có thể chạy `neo4j-admin` từ bất kỳ client Java nào.”** Lệnh yêu cầu quyền filesystem và môi trường cài đặt Neo4j; Java Driver chỉ kết nối qua giao thức truy vấn.

## 14. Bài tập tự luyện

1. Với các file `users.csv`, `companies.csv`, `memberships.csv` ở trên, giải thích vì sao `:START_ID(UserIds)` không được đổi thành `:START_ID(CompanyIds)`.
2. Nếu cả `User` và `Company` có ID `1`, hãy thiết kế header để không bị collision và viết ba dòng dữ liệu node/relationship mẫu.
3. Một file `memberships.csv` chứa tham chiếu `u999` chưa tồn tại. Nêu hai cách xử lý và hệ quả của việc bật `--skip-bad-relationships`.
4. Lập quy trình nhập 50 triệu node và 150 triệu relationship vào database **chưa tồn tại**. Liệt kê các phép đo và kiểm tra cần thực hiện trước khi chấp nhận database.
5. Giải thích vì sao không thể dùng `@Transactional` trong Spring Data Neo4j để bao `neo4j-admin database import full` thành một transaction nghiệp vụ.
6. So sánh yêu cầu downtime của full import, incremental import theo giai đoạn và `LOAD CSV ... IN TRANSACTIONS` khi hệ thống cần tiếp nhận đơn hàng liên tục.
7. Vì sao subscriber CDC không thể mặc nhiên nhận các sự kiện tạo node/relationship từ lần full import?

## 15. Ghi nhớ

- **`neo4j-admin database import full`** phù hợp để nạp ban đầu graph cực lớn, yêu cầu quyền quản trị và thao tác trực tiếp với dữ liệu lưu trữ.
- Chuẩn bị **CSV header, `:ID`, ID space, `:START_ID`, `:END_ID`, `:TYPE`** và kiểu property đúng là điều kiện cốt lõi để nhập property graph.
- **Database chưa tồn tại** là trường hợp an toàn nhất để học và thử full import; sau khi import phải đăng ký/khởi động DB, tạo index/constraint và đối soát graph.
- **Không dùng `--overwrite-destination` một cách tùy tiện**: đây là thao tác thay thế các file database, có thể xóa dữ liệu hiện có.
- **Incremental import là quy trình riêng của Enterprise Edition**, có điều kiện schema, backup và trạng thái database cụ thể.
- Với cập nhật thường xuyên trên graph đang chạy, dùng **Cypher `LOAD CSV` theo lô, Java Driver hoặc Spring Data Neo4j** khi phù hợp nghiệp vụ.
- Đánh giá chất lượng import bằng **tính đúng của quan hệ, số lượng, khóa, schema và truy vấn nghiệp vụ**, không chỉ exit code hay tốc độ nạp.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Import](https://neo4j.com/docs/operations-manual/current/import/)
- [Neo4j Operations Manual — Full import](https://neo4j.com/docs/operations-manual/current/import/full-import/)
- [Neo4j Operations Manual — Full data import tutorial](https://neo4j.com/docs/operations-manual/current/tutorial/neo4j-admin-import/)
- [Neo4j Operations Manual — CSV header format](https://neo4j.com/docs/operations-manual/current/import/header-format/)
- [Neo4j Operations Manual — Incremental import](https://neo4j.com/docs/operations-manual/current/import/incremental-import/)
- [Neo4j Data Ingestion Guide — Offline bulk loading](https://neo4j.com/docs/data-ingestion-guide/ingestion-methods/admin-import/)
