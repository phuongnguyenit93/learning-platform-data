# Phân biệt gói APOC, khả năng hỗ trợ và tương thích phiên bản trong Neo4j

## 1. APOC là gì và vì sao cần hiểu đúng các gói?

**APOC (Awesome Procedures on Cypher)** mở rộng Neo4j bằng những **procedure** và **function** viết bằng Java nhưng có thể được gọi từ Cypher. Trong hệ thống sử dụng property graph, APOC thường giúp xử lý dữ liệu dạng JSON, thao tác danh sách/map, duyệt đường đi theo điều kiện, nhập/xuất dữ liệu và tự động hóa một số bước xử lý graph.

Một vấn đề triển khai hay gặp là: tài liệu hoặc ví dụ trên Internet dùng tên `apoc.*`, nhưng trên máy của bạn lại báo `There is no procedure with the name ...`. Nguyên nhân có thể **không phải lỗi Cypher**: procedure nằm trong một gói khác, chưa được cài, không được cấp quyền, không còn tồn tại ở phiên bản đang chạy hoặc có cú pháp đã được Cypher thay thế.

Trong chương **APOC và phần mở rộng**, cần giải quyết bốn câu hỏi:

1. **APOC Core** và **APOC Extended** khác nhau về đóng gói, khả năng, đơn vị bảo trì và hỗ trợ như thế nào?
2. Phải chọn **phiên bản APOC tương thích** với phiên bản Neo4j bằng nguyên tắc gì?
3. Cách xác minh một procedure/function cụ thể có **thực sự khả dụng trên môi trường của mình**?
4. Khi nâng cấp Neo4j/Cypher, cần kiểm tra những gì để ứng dụng Java Driver hoặc Spring Data Neo4j không bị lỗi?

> Phạm vi: bài viết hướng tới Neo4j 5.x và các bản Neo4j dùng lịch phát hành `2025.MM`/`2026.MM`. Một số tên gọi cũ của thời Neo4j 4.x chỉ được nhắc để giải thích quá trình di chuyển.

## 2. APOC Core và APOC Extended: hai thư viện bổ sung cho nhau

Từ **Neo4j 5**, APOC được tách thành hai dự án/nhóm thư viện riêng. Bản **APOC Full** của các thế hệ cũ không còn là một gói “tất cả trong một” áp dụng cho Neo4j 5+.

| Tiêu chí | APOC Core | APOC Extended |
| --- | --- | --- |
| Đơn vị duy trì | Neo4j product/engineering | Cộng đồng và contributors |
| Hỗ trợ chính thức | **Có** theo phạm vi hỗ trợ APOC Core của Neo4j | **Không** có hỗ trợ sản phẩm chính thức từ Neo4j; bảo trì theo best effort |
| Mục đích | Các procedure/function phổ biến cho graph, chuỗi, map, JSON, path, import/export và xử lý theo lô | Khả năng chuyên biệt hơn, tích hợp ngoài, một số định dạng/công nghệ và dependency tùy chọn |
| Cách có được | Thường đóng gói sẵn trong thư mục `labs` của bản server; có thể bật qua Neo4j Desktop/Docker; tập được phép sử dụng trên Aura | Cài riêng từ bản phát hành tương thích; chủ yếu dành cho môi trường có quyền cài plugin server |
| Tệp JAR | `apoc-<version>-core.jar` hoặc tên JAR theo bản phân phối | `apoc-<version>-extended.jar` hoặc tên JAR theo bản phân phối |
| Quan hệ giữa hai gói | Không phụ thuộc việc cài Extended để chạy các chức năng Core | **Không chứa sẵn toàn bộ Core**; muốn dùng chức năng Core vẫn phải bảo đảm Core hiện diện |
| Quy trình xử lý sự cố | Kiểm tra tài liệu APOC Core và kênh hỗ trợ theo sản phẩm | Kiểm tra tài liệu Extended, release và issue cộng đồng; chủ động đánh giá rủi ro vận hành |

**Không suy ra gói từ tên procedure chỉ bằng tiền tố `apoc.`.** Cả hai có thể đăng ký tên bắt đầu bằng `apoc.`. Cần kiểm tra procedure trên **danh mục của đúng gói và đúng phiên bản**.

### 2.1. Ví dụ chức năng thuộc Core

Các ví dụ sau có tài liệu trong **APOC Core** (khả năng có thể bị hạn chế bởi quyền, edition, môi trường hoặc phiên bản):

| Nhóm | Hàm/procedure | Công dụng |
| --- | --- | --- |
| Chuyển đổi | `apoc.convert.toJson(value)` | Chuyển dữ liệu Cypher thành chuỗi JSON |
| Truy vấn graph | `apoc.path.expandConfig(startNode, config)` | Duyệt quan hệ/đường đi theo filter và quy tắc uniqueness |
| Nhập JSON | `apoc.load.json(...)` | Đọc JSON từ nguồn được cho phép |
| Xuất CSV | `apoc.export.csv.all(...)` | Xuất dữ liệu graph dạng CSV |
| Xử lý theo lô | `apoc.periodic.iterate(...)` | Chia thao tác theo lô; chú ý trạng thái deprecated trên Cypher mới |
| Tra cứu | `apoc.help(...)` và `apoc.version()` | Tra cứu danh sách API, phiên bản thư viện |

**Lưu ý cụ thể:** `apoc.export.csv.all` và `apoc.load.json` **không mặc nhiên là Extended** chỉ vì liên quan đến nhập/xuất. Danh mục Core thực sự có những procedure này.

### 2.2. Ví dụ chức năng thuộc Extended

Một số tên xuất hiện trong tài liệu **APOC Extended**:

- `apoc.export.parquet.all` và các biến thể `apoc.export.parquet.*`: xuất theo định dạng Parquet.
- `apoc.mongodb.get.byObjectId`: tích hợp MongoDB.
- `apoc.bolt.execute`: tương tác qua giao thức Bolt với cơ sở dữ liệu khác trong những kịch bản tương thích.
- Một số procedure `apoc.nlp.aws.*`, `apoc.nlp.azure.*`, `apoc.nlp.gcp.*`: tích hợp nhà cung cấp NLP.

Đây là **ví dụ nhận diện gói**, không phải lời đảm bảo mọi tên đều tồn tại trên mọi bản phát hành Extended. Mỗi tích hợp ngoài còn cần dependency, endpoint, cấu hình, quyền và thông tin xác thực riêng. Tài liệu Extended được phát hành theo các nhánh/version riêng; hãy kiểm tra danh mục trực tiếp của release triển khai.

### 2.3. Core, Extended không đồng nghĩa với GDS

**Neo4j Graph Data Science (GDS)** là một sản phẩm/plugin khác, cung cấp các thuật toán graph và tính năng phân tích chuyên sâu. Một số phép duyệt/tìm đường của APOC không làm APOC trở thành GDS. Tương tự, **Java Driver** và **Spring Data Neo4j** là công cụ kết nối, ánh xạ và thực thi Cypher từ ứng dụng; chúng không tự cài APOC vào máy chủ.

## 3. Tương thích phiên bản: kiểm tra cả Neo4j, APOC và Cypher

### 3.1. Quy tắc ghép phiên bản

APOC dựa vào các API bên trong Neo4j, nên ghép JAR sai phiên bản có thể khiến Neo4j cảnh báo lúc khởi động hoặc không nạp được procedure.

| Dòng Neo4j | Nguyên tắc kiểm tra APOC | Minh họa |
| --- | --- | --- |
| Neo4j 5.x | Chọn dòng APOC cùng nhánh `5.x` và **đúng cặp phiên bản được liệt kê trong compatibility matrix** | Neo4j `5.26.x` cần bản APOC được công bố tương thích với `5.26.x` |
| Neo4j theo lịch `YYYY.MM` | Giữ **năm và tháng phát hành** trùng nhau; patch APOC không nhất thiết bằng patch Neo4j | Neo4j `2026.10.x` dùng APOC phát hành cho `2026.10`, ví dụ `2026.10.2` |
| Neo4j 4.4 | Dùng tài liệu và artifact dành riêng cho 4.4 | Không bê nguyên JAR 4.4 sang Neo4j 5/2026 |

**Không áp dụng một quy tắc kiểu “cứ cùng major là chạy”**: `5.15` và `5.26` cùng major 5 nhưng không thể tự xem là tương thích. Ngược lại, không bắt buộc patch Neo4j và patch APOC bằng nhau nếu compatibility matrix xác nhận cùng dòng.

Các bước kiểm tra tối thiểu:

1. Xác định phiên bản Neo4j đang chạy trên **server thực tế**, không chỉ phiên bản thư viện Java của client.
2. Chọn đúng **Core** hoặc **Extended** theo danh sách procedure ứng dụng dùng.
3. Đọc compatibility matrix của **cả gói** và release notes, bao gồm dependency đặc biệt của Extended.
4. Kiểm tra cú pháp Cypher hiện dùng (`Cypher 5` hay `Cypher 25`), vì API có thể tồn tại ở runtime nhưng bị deprecated hoặc không khả dụng trong ngôn ngữ mặc định.
5. Nạp thư viện, khởi động lại Neo4j và kiểm tra bằng `SHOW PROCEDURES`, `SHOW FUNCTIONS`, một smoke test đọc và log khởi động.

### 3.2. Khác nhau giữa phiên bản thư viện và phiên bản ngôn ngữ

Trong các bản Neo4j mới, một DBMS có thể hỗ trợ lựa chọn **Cypher 5** hoặc **Cypher 25**. Đây là vấn đề **khác** với việc JAR APOC có đúng phiên bản Neo4j không.

Một số API Core từng hữu ích được bổ sung tương đương trong Cypher và chuyển trạng thái **deprecated**. Ví dụ:

| API APOC trước đây | Trạng thái/hướng dùng trong Cypher mới |
| --- | --- |
| `apoc.coll.toSet(list)` | Deprecated trong Cypher 25; ưu tiên `coll.distinct(list)` |
| `apoc.periodic.iterate(...)` | Deprecated từ Neo4j 2026.04/Cypher 25; cân nhắc `CALL { ... } IN CONCURRENT TRANSACTIONS` |
| `apoc.when(...)` | Deprecated trong Cypher 25; xem cú pháp truy vấn điều kiện của Cypher tương ứng |

Ví dụ minh họa sự khác nhau giữa **cú pháp cũ** và **cú pháp Cypher 25**:

```cypher
// Cách APOC từng sử dụng để loại trùng giá trị:
RETURN apoc.coll.toSet([1, 1, 2, 3, 2]) AS ids;
```

```cypher
CYPHER 25
RETURN coll.distinct([1, 1, 2, 3, 2]) AS ids;
```

Cả hai minh họa thao tác loại trùng với list; chọn cú pháp theo phiên bản Cypher và trạng thái deprecation. **Deprecated không có nghĩa “đã bị xóa ngay”**. Một số API không có trong Cypher 25 có thể vẫn dùng qua `CYPHER 5` trên bản hỗ trợ; hãy kiểm tra compatibility notes thay vì giả định một cơ chế fallback áp dụng cho mọi procedure.

### 3.3. Checklist phiên bản khi nâng cấp

Trước mỗi lần nâng cấp, lưu một bản ma trận:

| Thành phần | Ghi nhận |
| --- | --- |
| Neo4j Server | Version, edition, cách triển khai (server/Desktop/Docker/Aura), cụm hoặc đơn máy |
| APOC Core | Có hay không, JAR version, danh sách function/procedure đang dùng |
| APOC Extended | Có hay không, JAR version, dependency ngoài và chức năng đang dùng |
| Cypher | Version mặc định và các query có khai báo `CYPHER 5`/`CYPHER 25` |
| Bảo mật | `allowlist`, `unrestricted`, quyền thực thi của role và chính sách I/O |
| Ứng dụng | Java Driver, Spring Data Neo4j, câu truy vấn và test dùng APOC |

Không thể kết luận “plugin đã tương thích” chỉ vì Neo4j khởi động được; vẫn phải xác minh các procedure nghiệp vụ gọi **đúng signature và quyền thực thi**.

## 4. Cách xác định APOC thực sự có mặt trong database

Hãy chạy các câu lệnh đọc sau qua Neo4j Browser, cypher-shell hoặc Java Driver, bằng tài khoản có quyền xem metadata cần thiết.

### 4.1. Xem phiên bản Neo4j

```cypher
CALL dbms.components()
YIELD name, versions
RETURN name, versions;
```

Kết quả cho biết các component và phiên bản DBMS. Không dùng version của một ứng dụng client để suy ra version server.

### 4.2. Kiểm tra phiên bản APOC

```cypher
RETURN apoc.version() AS apocVersion;
```

Nếu báo function không tồn tại, kiểm tra trước xem **Core đã được nạp và được phép sử dụng chưa**; câu lệnh này không phải bằng chứng Extended có hay không.

### 4.3. Liệt kê procedure và function được đăng ký

```cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
```

```cypher
SHOW FUNCTIONS
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
```

Hai danh sách khác nhau vì **procedure** được gọi bằng `CALL` còn **function** được dùng trong biểu thức. Cần kiểm tra cả hai; đôi khi API ứng dụng cần là function chứ không phải procedure.

### 4.4. Tìm signature và ví dụ sử dụng

```cypher
CALL apoc.help('path');
```

```cypher
CALL apoc.help('convert');
```

`apoc.help` cho phép tra cứu các thành phần APOC khả dụng và signature khi được cấp quyền. Một ví dụ trong tài liệu mới có thể có tham số đầu vào khác tài liệu cũ; luôn đối chiếu **signature thực tế** với phiên bản server.

> Việc một tên procedure xuất hiện trong tài liệu không chứng minh nó đã được cài hoặc role hiện tại có quyền chạy. Ngược lại, tên không xuất hiện ở `SHOW PROCEDURES` có thể do chưa nạp JAR, allowlist hạn chế hoặc scope hiển thị theo quyền; cần đối chiếu log và cấu hình.

## 5. Cài đặt APOC theo từng môi trường

### 5.1. Neo4j Server tự quản lý (binary/tar/zip/package)

Với bản phân phối Neo4j đi kèm APOC Core, JAR thường nằm trong thư mục `$NEO4J_HOME/labs`. Quy trình khái niệm:

1. Xác định Neo4j version và bản Core tương ứng.
2. Sao chép **JAR Core tương thích** từ `labs` sang `plugins`. Không chép toàn bộ JAR không liên quan.
3. Nếu thật sự cần Extended, tải **JAR Extended đúng dòng phiên bản** từ bản phát hành được chỉ rõ; kiểm tra dependency của các chức năng đặc biệt.
4. Thiết lập quyền gọi procedure/đọc ghi file theo yêu cầu nghiệp vụ.
5. Khởi động lại Neo4j, đọc log và chạy các truy vấn kiểm chứng ở mục 4.

Ví dụ **cấu trúc thư mục tham khảo**, tên file thay đổi theo bản phát hành:

```text
NEO4J_HOME/
├── conf/
│   ├── neo4j.conf
│   └── apoc.conf        # chỉ tạo khi cần cấu hình APOC
├── labs/
│   └── apoc-<compatible-version>-core.jar
└── plugins/
    ├── apoc-<compatible-version>-core.jar
    └── apoc-<compatible-version>-extended.jar  # chỉ khi cần
```

**Không giữ nhiều JAR Core khác phiên bản trong `plugins`** hoặc để lẫn JAR APOC Full cũ khi đang dùng Core/Extended mới. Điều này dễ gây trùng đăng ký chức năng hoặc lỗi lớp Java khi khởi động. Khi nâng cấp, dừng DBMS, thay JAR theo kế hoạch rồi khởi động lại và xác minh.

### 5.2. Neo4j Desktop

Trong Neo4j Desktop, giao diện **Plugins** cho phép cài **APOC Core** đối với DBMS/project hỗ trợ. Trên tài liệu hiện hành của Extended, **APOC Extended không được cài bằng nút APOC trên tab Plugins**; cần thêm JAR tương thích vào thư mục `plugins` của DBMS phù hợp và khởi động lại.

Không suy ra “bấm Install APOC” nghĩa là đã có toàn bộ chức năng Extended.

### 5.3. Neo4j Docker

Docker image có cơ chế khai báo plugin qua biến môi trường `NEO4J_PLUGINS`. Ví dụ một cấu hình **môi trường phát triển** sử dụng cả hai gói:

```yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    environment:
      NEO4J_PLUGINS: '["apoc", "apoc-extended"]'
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - ./neo4j-data:/data
      - ./neo4j-plugins:/plugins
```

Đây là **trích đoạn Compose minh họa cơ chế plugin**, chưa có cấu hình xác thực, backup và chính sách mạng đầy đủ để chạy production. `NEO4J_PLUGINS` có thể tải/cài plugin lúc container khởi động và hữu ích cho thử nghiệm; với production, nên **pin image và JAR tương thích**, kiểm soát artifact, checksum và cấu hình thay vì phụ thuộc tải động ở mỗi lần chạy.

**Kiểm tra ngay JAR trong container**: nếu chỉ khai báo `["apoc-extended"]`, không được mặc định rằng Core đã được cài kèm. Nếu chỉ `["apoc"]`, không mặc định có procedure Extended.

### 5.4. Neo4j AuraDB

APOC Core **có sẵn trong AuraDB với phạm vi chức năng được dịch vụ cho phép**. Người dùng Aura thường không có quyền tự sao chép JAR vào `plugins` hay sửa `neo4j.conf`/`apoc.conf` như server tự quản lý.

Khi triển khai trên Aura:

- Dùng tài liệu danh sách APOC **được Aura hỗ trợ**, không lấy danh sách Core hoặc Extended tổng quát làm cam kết.
- Dùng `SHOW PROCEDURES`/`SHOW FUNCTIONS` để kiểm tra chức năng mà deployment và tài khoản hiện tại nhìn thấy.
- Không giả định có thể dùng import/export file trên filesystem của server hoặc cài Extended thủ công.
- Nếu procedure cần không khả dụng, cân nhắc Cypher chuẩn, Java Driver hoặc xử lý tại ứng dụng; không chọn Extended làm một phụ thuộc bắt buộc khi dịch vụ không cho cài.

## 6. Cấu hình: tách `neo4j.conf` khỏi `apoc.conf`

Từ Neo4j 5, cấu hình dạng `apoc.*` được đặt trong **`apoc.conf`** (cùng thư mục với `neo4j.conf`) hoặc qua biến môi trường, thay vì ghi trực tiếp vào `neo4j.conf`.

| Mục đích | Vị trí thường dùng | Ví dụ |
| --- | --- | --- |
| Quyết định procedure/function nào được **nạp** | `neo4j.conf` | `dbms.security.procedures.allowlist` |
| Quyết định procedure nào được thực thi với **quyền không hạn chế** | `neo4j.conf` | `dbms.security.procedures.unrestricted` |
| Điều khiển việc APOC được **đọc file cục bộ** | `apoc.conf` | `apoc.import.file.enabled` |
| Điều khiển việc APOC được **ghi file cục bộ** | `apoc.conf` | `apoc.export.file.enabled` |
| Ràng buộc đường dẫn đọc với thư mục import của Neo4j | `apoc.conf` | `apoc.import.file.use_neo4j_config` |
| Chặn/lọc truy cập outbound URL | Cấu hình DBMS, network policy, quyền tương ứng | Chống SSRF, giới hạn địa chỉ/miền truy cập |

Ví dụ cấu hình giữ I/O file cục bộ ở trạng thái mặc định hạn chế:

```properties
# conf/apoc.conf
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
```

**Chỉ bật quyền đọc/ghi file nếu thật sự cần.** Nhiều procedure JSON/CSV có thể chạm đến filesystem của **máy chủ Neo4j**, không phải máy chạy ứng dụng Java. Tương tự, lấy dữ liệu qua URL có thể tạo yêu cầu HTTP từ server và cần hạn chế để tránh server-side request forgery (SSRF).

### 6.1. `allowlist` và `unrestricted` khác nhau

- `dbms.security.procedures.allowlist` chọn những procedure/function **được phép nạp/đăng ký**. Mặc định có thể là tất cả, nhưng môi trường production thường nên thu hẹp.
- `dbms.security.procedures.unrestricted` cho phép các procedure được chọn truy cập các API nội bộ có thể bị hạn chế. **Không phải mọi procedure APOC đều cần quyền này.**
- Quyền của role/user khi gọi procedure (chẳng hạn quyền thực thi) là lớp kiểm soát bổ sung, không thể thay thế bằng hai setting trên.

Ví dụ minh họa cách chọn hẹp các nhóm API dự định sử dụng:

```properties
# conf/neo4j.conf — ví dụ cần điều chỉnh theo ứng dụng
dbms.security.procedures.allowlist=apoc.version,apoc.help,apoc.convert.*,apoc.path.*
```

Trong trường hợp các API đó không đòi hỏi quyền unrestricted, **không cần** cấp `apoc.*` vào `unrestricted`. Nếu tài liệu của một procedure cụ thể yêu cầu quyền đặc biệt, hãy cấp **đúng tên/chùm tên tối thiểu** sau khi kiểm tra tính năng và mức rủi ro của nó.

> Tránh sao chép vô điều kiện hai dòng `dbms.security.procedures.allowlist=apoc.*` và `dbms.security.procedures.unrestricted=apoc.*` vào production. “Chạy được mọi procedure” làm phạm vi quyền lớn hơn nhu cầu nghiệp vụ.

### 6.2. Sai khác giữa “cài đặt thành công” và “được phép thực thi”

Một procedure có thể tồn tại trong JAR nhưng:
- Không được đăng ký do `allowlist`.
- Không thể khởi tạo do thiếu dependency.
- Bị từ chối vì thiếu quyền execute của tài khoản.
- Không có quyền đọc file, gọi endpoint mạng hoặc dùng API nội bộ cần thiết.
- Chỉ hỗ trợ môi trường tự host nhưng deployment là Aura.
- Bị loại bỏ khi chuyển phiên bản Cypher.

Vì vậy, quá trình nghiệm thu cần kiểm tra **danh sách, signature và một truy vấn thực tế** với đúng tài khoản ứng dụng.

## 7. Ví dụ thực hành với APOC Core và Cypher

Các ví dụ sau chạy trên một database thử nghiệm có **APOC Core** đã cài và được phép gọi `apoc.convert.toJson`, `apoc.path.expandConfig`. Không cần Extended.

### 7.1. Tạo graph nhỏ, có thể chạy lại

```cypher
UNWIND [
  {userId: 'u001', userName: 'An', companyId: 'c001', companyName: 'Acme'},
  {userId: 'u002', userName: 'Bình', companyId: 'c001', companyName: 'Acme'},
  {userId: 'u003', userName: 'Chi', companyId: 'c002', companyName: 'Northwind'}
] AS row
MERGE (u:User {id: row.userId})
SET u.name = row.userName
MERGE (c:Company {id: row.companyId})
SET c.name = row.companyName
MERGE (u)-[:MEMBER_OF]->(c);
```

Graph biểu diễn quan hệ người dùng thuộc doanh nghiệp:

```text
(u001:User) ---MEMBER_OF---> (c001:Company)
(u002:User) ---MEMBER_OF---> (c001:Company)
(u003:User) ---MEMBER_OF---> (c002:Company)
```

Với dữ liệu mẫu và database sạch, có 3 node `User`, 2 node `Company` và 3 relationship `MEMBER_OF`.

### 7.2. Biến đổi dữ liệu bằng function Core

```cypher
MATCH (u:User {id: 'u001'})-[:MEMBER_OF]->(c:Company)
RETURN apoc.convert.toJson({
  userId: u.id,
  userName: u.name,
  companyId: c.id
}) AS jsonText;
```

`apoc.convert.toJson` trả về một **chuỗi JSON**, khác với Cypher map. Nếu Java Driver hoặc Spring Data Neo4j chỉ cần cấu trúc có khóa/giá trị, có thể trả **map Cypher thông thường**:

```cypher
MATCH (u:User {id: 'u001'})-[:MEMBER_OF]->(c:Company)
RETURN {
  userId: u.id,
  userName: u.name,
  companyId: c.id
} AS resultMap;
```

Chọn phương án **không dùng APOC** khi không cần chuyển thành JSON string trên server. Điều đó giảm phụ thuộc plugin và tránh serialize rồi parse lại không cần thiết ở tầng Java.

### 7.3. Duyệt quan hệ bằng procedure Core

```cypher
MATCH (u:User {id: 'u001'})
CALL apoc.path.expandConfig(u, {
  relationshipFilter: 'MEMBER_OF>',
  minLevel: 1,
  maxLevel: 1,
  uniqueness: 'NODE_GLOBAL'
})
YIELD path
RETURN [node IN nodes(path) | node.id] AS nodeIds;
```

Với ví dụ chỉ một bước quan hệ, Cypher thuần đủ để thay thế:

```cypher
MATCH (u:User {id: 'u001'})-[:MEMBER_OF]->(c:Company)
RETURN [u.id, c.id] AS nodeIds;
```

`apoc.path.expandConfig` có giá trị hơn khi cần **lọc loại quan hệ, chiều duyệt, label, số bước, quy tắc duyệt/uniqueness** linh hoạt. Với một quan hệ cố định, Cypher thuần dễ hiểu và giảm coupling với plugin. Procedure này còn có giới hạn an toàn khi chạy trong **parallel runtime**, nên không mặc định chuyển mọi truy vấn sang parallel để tăng tốc.

### 7.4. Gói nào cần cho một thao tác?

| Yêu cầu nghiệp vụ | Cách bắt đầu | Khi nào chọn APOC |
| --- | --- | --- |
| Tra cứu node theo ID có constraint | `MATCH (u:User {id: $id})` | Thường không cần APOC |
| Tìm đường đi theo pattern cố định | `MATCH p = (...)-[:REL*1..3]->(...)` | Khi cần traversal/filter/uniqueness đặc biệt và đã kiểm tra tương thích |
| Trả DTO cho Java | `RETURN { ... }` hoặc nhiều cột | `apoc.convert.toJson` khi thật sự cần server-side JSON string |
| Import CSV thông thường | `LOAD CSV`, `CALL { ... } IN TRANSACTIONS` | APOC nếu cần định dạng khác hoặc workflow đã chấp nhận dependency |
| Xuất toàn bộ graph ra CSV | Kiểm tra yêu cầu định dạng và quyền file | `apoc.export.csv.all` thuộc Core, nhưng có điều kiện về file/stream |
| Xuất Parquet | Kiểm tra công cụ ETL hoặc xử lý ngoài | Một số bản Extended có `apoc.export.parquet.*`; phải kiểm tra release và quyền |
| Truy cập MongoDB từ Neo4j | Đánh giá luồng tích hợp tại ứng dụng/ETL | Extended có các procedure liên quan, tùy môi trường và dependency |
| Phân tích graph phức tạp | Cypher, thuật toán phù hợp | Phân biệt APOC với GDS; không thay thế nhau |

## 8. Tích hợp trong Java Driver và Spring Data Neo4j

**APOC chạy trên Neo4j Server**, còn Java Driver truyền Cypher qua giao thức Bolt. Thêm dependency Java `org.neo4j.driver` hoặc Spring Data Neo4j vào `pom.xml`/**Gradle** **không** đồng nghĩa server đã có APOC Core/Extended.

### 8.1. Java Driver: kiểm tra APOC tại thời điểm khởi động ứng dụng

Giả sử ứng dụng đã có `org.neo4j.driver.Driver driver`:

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    String version = session.executeRead(tx ->
        tx.run("RETURN apoc.version() AS version")
          .single()
          .get("version")
          .asString()
    );

    System.out.println("APOC Core version: " + version);
}
```

Đây là một **smoke test về sự sẵn có của function**. Không coi chuỗi kết quả là bằng chứng tất cả procedure được cấp quyền. Cần thêm một test dành cho **từng procedure mà ứng dụng phụ thuộc**; môi trường production nên ghi lỗi và vô hiệu hóa tính năng phụ thuộc nếu API không hiện diện.

Ví dụ khi service cần chuyển map thành JSON tại server:

```java
String cypher = """
    MATCH (u:User {id: $id})
    RETURN apoc.convert.toJson(properties(u)) AS json
    """;
```

Dùng **tham số `$id`**; không nối chuỗi dữ liệu người dùng thành mã Cypher. Với Extended, đặc biệt những procedure thực thi Cypher động hoặc truy cập endpoint ngoài, phải kiểm soát dữ liệu đầu vào và quyền của tài khoản DB.

### 8.2. Spring Data Neo4j

Trong Spring Data Neo4j:

- `@Query` và `Neo4jClient` có thể gọi các procedure/function APOC **nếu server hỗ trợ**; framework không tự thêm JAR plugin.
- Những truy vấn chỉ dùng Cypher thuần thường dễ di chuyển giữa Neo4j tự host và Aura hơn.
- Nếu procedure trả về `MAP`, `LIST`, `NODE` hoặc `score`, lựa chọn DTO/projection hoặc mapping cần phù hợp kiểu kết quả thực.
- Một procedure có ghi dữ liệu không tự trở thành “read only” vì phương thức Java mang tên `find...`. Phải xác định **transaction mode**, retry semantics và quyền thực thi.
- Kiểm thử migration nên chạy với **đúng Neo4j, đúng JAR APOC và đúng Cypher version** được deploy.

Một cấu hình ứng dụng Java có thể khởi động bình thường nhưng request đầu tiên gọi `apoc.path.expandConfig` mới thất bại vì plugin không được nạp. Do đó, smoke test nên chạy sớm trong pipeline triển khai.

## 9. Quy trình nâng cấp, kiểm thử và xử lý sự cố

### 9.1. Checklist nâng cấp Neo4j + APOC

1. **Lập danh mục:** tìm mọi `apoc.*` trong code Java/Spring, scripts Cypher và jobs; ghi gói Core hay Extended, signature và phiên bản mục tiêu.
2. **Chọn release:** xác định Neo4j server/edition, tra đúng compatibility matrix Core và Extended.
3. **Rà soát Cypher:** đối chiếu các API deprecated/removed trên Cypher 25; ưu tiên chuyển sang Cypher thuần khi có tương đương rõ ràng.
4. **Thử trên staging:** nạp JAR tương thích, restart server, kiểm tra log và `SHOW PROCEDURES`/`SHOW FUNCTIONS`.
5. **Kiểm tra quyền:** chạy bằng đúng role ứng dụng, thử các chức năng đọc, ghi và xuất/nhập được phép.
6. **Kiểm thử nghiệp vụ:** chạy lại các query tạo node, traversal, import và JSON với dataset đại diện; so sánh kết quả trước/sau.
7. **Triển khai có rollback:** backup, giữ danh sách artifact/version chính xác, restart theo quy trình; theo dõi lỗi đăng ký procedure và latency sau nâng cấp.

### 9.2. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
| --- | --- | --- |
| `Unknown function 'apoc.version'` | Core chưa nạp, JAR không hợp lệ, allowlist hoặc quyền hạn chế | Kiểm tra `plugins`/`labs`, log, `SHOW FUNCTIONS` |
| `There is no procedure with the name ...` | Sai gói, procedure đã đổi tên/xóa, JAR thiếu hoặc cấu hình không nạp | Tra Core/Extended đúng release; `SHOW PROCEDURES` |
| Log báo APOC/Neo4j không tương thích | JAR lấy từ dòng release khác | Xem compatibility matrix, thay JAR rồi restart |
| Procedure xuất hiện nhưng user không chạy được | Thiếu quyền execute, unrestricted hoặc quyền hệ thống | Kiểm tra role và cấu hình procedure cụ thể |
| `apoc.load.json(file:///...)` bị từ chối | Đọc file cục bộ chưa bật; không được dùng đường dẫn nguồn | Xem `apoc.conf`, thư mục import và quyền file |
| Không tìm thấy `apoc.export.parquet.*` | Chưa cài Extended hoặc bản Extended thiếu procedure đó | Kiểm tra danh mục Extended và `SHOW PROCEDURES` |
| “Install APOC” trong Desktop nhưng thiếu chức năng Extended | Nút cài đặt chỉ đưa Core vào DBMS | Cài Extended thủ công nếu môi trường hỗ trợ |
| Dùng trên Aura bị chặn | Dịch vụ chỉ cấp tập chức năng APOC cho phép | Tra danh sách Aura hỗ trợ, đổi workflow |
| Sau nâng cấp Cypher 25 procedure cũ báo deprecation/removal | Cypher bổ sung câu lệnh chuẩn và thay đổi API | Kiểm tra release notes, dùng Cypher tương đương hoặc chế độ ngôn ngữ phù hợp |
| Lỗi runtime khi gọi tích hợp ngoài | Thiếu dependency, endpoint hoặc cấu hình/credentials | Xem log và tài liệu procedure của đúng release |
| Query chậm khi dùng `apoc.path.expandConfig` | Traversal quá rộng, uniqueness/bfs/limit chưa hợp lý | Giới hạn độ sâu, kiểm tra fan-out và tính đúng bằng Cypher |

### 9.3. Những ngộ nhận cần tránh

**“Cài Extended tức là có cả Core.”** Không đúng với cấu trúc đóng gói từ Neo4j 5: hai JAR là hai tập chức năng bổ sung.

**“APOC được Neo4j hỗ trợ chính thức, nên mọi procedure Extended đều có support.”** Chính sách hỗ trợ chính thức áp dụng cho **Core**; Extended dựa vào cộng đồng.

**“Tên procedure có trong trang docs mới nên bản Neo4j cũ chắc chắn chạy được.”** Phải tra **tài liệu đúng version**, signature và danh sách runtime.

**“Cùng tên `apoc.*` thì cùng quyền truy cập.”** Procedure có thể chỉ đọc, ghi, gọi HTTP hoặc đụng đến file; không nên cấp unrestricted hàng loạt.

**“`SHOW PROCEDURES` có tên procedure thì ứng dụng chắc chắn chạy được.”** Còn quyền tài khoản, dependency, network/filesystem, Cypher version và logic cụ thể.

**“Khi có APOC thì nên dùng APOC cho mọi truy vấn.”** Cypher chuẩn thường là lựa chọn tốt khi đáp ứng cùng yêu cầu với ít phụ thuộc hơn; nên dùng APOC vì **khả năng thật sự cần**, không chỉ vì cú pháp ngắn.

## 10. Bài tập tự kiểm tra

1. Giả sử hệ thống chạy Neo4j `2026.10.x`, chọn dòng phiên bản APOC cần kiểm tra. Giải thích vì sao chỉ so sánh major version hoặc bắt buộc patch bằng nhau đều không đủ.
2. Một ví dụ cũ dùng `apoc.export.csv.all`. API này thuộc Core hay Extended trong danh mục hiện hành? Phân biệt với `apoc.export.parquet.all`.
3. Trên Neo4j Desktop, đã cài bằng nút `APOC` nhưng `apoc.mongodb.get.byObjectId` không có. Đề xuất quy trình kiểm tra theo thứ tự hợp lý.
4. Viết ba truy vấn để xem **Neo4j version**, **APOC version** và **danh sách APOC procedure** trong DBMS đang chạy.
5. So sánh lợi ích và hạn chế của `apoc.convert.toJson(map)` với việc trả map trực tiếp từ Cypher cho Java Driver.
6. Một ứng dụng chạy trên AuraDB muốn dùng procedure Extended phụ thuộc file cục bộ. Vì sao không thể chỉ thêm dependency Maven để giải quyết?
7. Tìm một chỗ đang dùng `apoc.coll.toSet` và viết lại bằng Cypher 25. Nêu cách kiểm tra chức năng tương đương.
8. Đề xuất bộ smoke test tối thiểu khi nâng cấp Neo4j/ APOC cho một service Java/Spring chứa truy vấn JSON, path expansion và xử lý theo lô.

## 11. Ghi nhớ

- **APOC Core** do Neo4j hỗ trợ chính thức; **APOC Extended** là dự án cộng đồng, mang thêm những khả năng chuyên biệt và dependency riêng.
- Với Neo4j 5+, **Extended không bao gồm Core**, và không còn dùng mô hình “APOC Full” cũ như một JAR chứa toàn bộ chức năng.
- Phải chọn JAR **tương thích với phiên bản Neo4j** bằng **compatibility matrix**, đặc biệt dòng `5.x` và lịch `YYYY.MM`; đồng thời kiểm tra **Cypher 5/Cypher 25**.
- `SHOW PROCEDURES`, `SHOW FUNCTIONS`, `apoc.version()` và `apoc.help(...)` giúp xác minh những gì hiện diện, nhưng còn phải thử **quyền thực thi và hành vi thật**.
- Phân biệt **cấu hình DBMS `neo4j.conf`**, **cấu hình APOC `apoc.conf`**, quyền role và chính sách đọc/ghi file, mạng.
- Ưu tiên **Cypher thuần** khi đủ khả năng; chỉ dùng APOC khi mang lại chức năng cần thiết và đã kiểm chứng hỗ trợ, tương thích, bảo mật, hiệu năng.
- **Java Driver/Spring Data Neo4j không tự cài APOC Server**; cần cấu hình, cập nhật và smoke test plugin trên đúng deployment.

### Tài liệu tham khảo chính thức

- [Neo4j APOC Core — Introduction](https://neo4j.com/docs/apoc/current/introduction/)
- [Neo4j APOC Core — Installation và compatibility matrix](https://neo4j.com/docs/apoc/current/installation/)
- [Neo4j APOC Core — Procedures & Functions](https://neo4j.com/docs/apoc/current/overview/)
- [Neo4j APOC Core — Migration Guide](https://neo4j.com/docs/apoc/current/migration-guide/)
- [Neo4j APOC Core — Additions, deprecations, removals and compatibility](https://neo4j.com/docs/apoc/current/deprecations-and-additions/)
- [Neo4j APOC Core — Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/)
- [Neo4j APOC Core — Configuration Options](https://neo4j.com/docs/apoc/current/config/)
- [Neo4j APOC Extended — Introduction](https://neo4j.com/labs/apoc/2025/introduction/)
- [Neo4j APOC Extended — Installation](https://neo4j.com/labs/apoc/2025/installation/)
- [Neo4j APOC Extended — Procedures & Functions](https://neo4j.com/labs/apoc/2025/overview/)
- [Neo4j Operations Manual — Docker plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/)
- [Neo4j Aura — APOC availability](https://neo4j.com/docs/aura/platform/apoc/)
