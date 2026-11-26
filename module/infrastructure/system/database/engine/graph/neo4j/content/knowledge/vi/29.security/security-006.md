# Bảo vệ đường dẫn tệp, truy cập URL và cấu hình phần mở rộng trong Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **ranh giới tin cậy** giữa ứng dụng Java, Neo4j Server, hệ thống tệp, mạng nội bộ và các nguồn dữ liệu bên ngoài.
- Hiểu cách `LOAD CSV` sử dụng địa chỉ `file:///` và URL từ xa, cũng như vai trò của thư mục import, quyền hệ điều hành và cấu hình bảo mật.
- Phân biệt **Cypher lõi** với procedure của **APOC**, **Graph Data Science (GDS)** và plugin bên thứ ba; cấu hình theo nguyên tắc đặc quyền tối thiểu.
- Nhận diện rủi ro **path traversal**, symlink, SSRF (*Server-Side Request Forgery*), chuyển hướng HTTP, lộ thông tin xác thực và mở rộng bề mặt tấn công qua plugin.
- Đề xuất cách nhập dữ liệu an toàn bằng nguồn đã kiểm duyệt hoặc Java Driver mà không cho client tùy ý yêu cầu database đọc tệp/URL.
- Thiết kế kiểm thử, giám sát và quy trình vận hành để phát hiện truy cập bị từ chối, thay đổi cấu hình nguy hiểm và sự cố nhập dữ liệu.

Bài thuộc chương **Bảo mật** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j lưu node, relationship, thuộc tính theo mô hình **property graph**, hỗ trợ Cypher để đọc/ghi graph và cho phép ứng dụng dùng Java Driver, Spring Data Neo4j, các plugin hoặc công cụ nhập dữ liệu. Những khả năng mở rộng này hữu ích nhưng cũng tạo ra **đường đi từ một câu truy vấn tới tệp trên máy chủ hoặc dịch vụ trên mạng**.

> **Phạm vi:** Ví dụ cấu hình dựa trên tên thiết lập phổ biến của Neo4j 5.x và các dòng hiện đại. Tên cấu hình, mặc định, cách phân quyền procedure và khả năng hỗ trợ trên Aura có thể khác theo **phiên bản, edition và loại triển khai**. Trước khi áp dụng, phải đối chiếu tài liệu và danh sách cấu hình của **đúng bản đang chạy**. Không sao chép cấu hình minh họa vào production mà bỏ qua đánh giá quyền.

## 1. Mô hình mối đe dọa: ai thực sự đọc tệp hoặc gọi URL?

Xét ứng dụng quản lý đơn hàng:

~~~mermaid
flowchart LR
    U["HTTP client"] --> A["Spring Boot API"]
    A -->|Neo4j Java Driver| DB[("Neo4j Server")]
    DB -->|file:///| FS["Import directory / filesystem"]
    DB -->|https://| NET["Remote endpoint"]
    DB -->|CALL apoc.*| PL["APOC / plugin runtime"]
    PL --> FS
    PL --> NET
~~~

Khi API gửi một câu Cypher chứa `LOAD CSV FROM 'file:///customers.csv'`, **tiến trình Neo4j** là bên đọc tệp: đường dẫn không trỏ vào laptop của người gọi Java Driver hay file trong thư mục project Spring. Tương tự, khi một procedure tải JSON từ URL, yêu cầu mạng có thể xuất phát từ **máy hoặc container đang chạy Neo4j**. Đây là yếu tố cốt lõi của mô hình đe dọa.

| Tài sản cần bảo vệ | Đường tấn công thường gặp | Biện pháp chính |
| --- | --- | --- |
| Tệp cấu hình, khóa, backup và dữ liệu ngoài import | Bị đọc do đường dẫn không giới hạn hoặc plugin quá quyền | Giới hạn thư mục, quyền OS/container, allowlist procedure |
| Endpoint nội bộ và metadata cloud | Database bị lợi dụng gọi URL do người dùng điều khiển (**SSRF**) | Không chấp nhận URL tùy ý, egress firewall/proxy và xác thực |
| Database graph | Import dữ liệu sai hoặc câu Cypher ghi ngoài phạm vi | Role truy cập hẹp, validation, constraint và transaction |
| Thông tin xác thực | URL có secret, log tham số, plugin đọc file cấu hình | Secrets manager, redaction, log tối thiểu |
| Khả năng sẵn sàng | Import file lớn, response vô hạn hoặc plugin ngốn heap | Quota, batch, timeout, giám sát tài nguyên |
| Tính toàn vẹn môi trường | JAR plugin không tin cậy, version lệch | Nguồn phát hành chính thức, kiểm tra checksum, quy trình đổi version |

**Ba câu hỏi trước khi cho phép một đường nhập dữ liệu:** nguồn có đáng tin không, dữ liệu nào sẽ đi qua Neo4j, và quyền đọc/ghi cuối cùng thuộc **tài khoản Neo4j Server** hay **tài khoản ứng dụng**?

## 2. Phân biệt local file, remote URL và upload của người dùng

Cùng là “đường dẫn”, nhưng các trường hợp dưới đây không tương đương:

~~~text
file:///customers.csv
https://data.example.org/exports/customers.csv
C:\Users\developer\Downloads\customers.csv
/home/app/uploads/customers.csv
~~~

- `file:///customers.csv` trong `LOAD CSV` là một **file URL do Neo4j Server xử lý**; việc định vị tệp chịu ràng buộc thư mục import và cấu hình.
- `https://...` là **tài nguyên mạng mà server Neo4j có thể phải truy cập**.
- `C:\Users\...` là đường dẫn trên máy Windows của người dùng; thường **không tồn tại trên Neo4j Server**, nhất là khi DB chạy ở container/Aura.
- `/home/app/uploads/...` có thể tồn tại trên máy chạy API nhưng không được mount sang container DB, vì vậy không thể coi là file mà Neo4j có thể đọc.

Đối với upload qua HTTP, phương án tốt thường là:

1. **API tiếp nhận** nội dung và kiểm tra quyền/ngữ nghĩa/kích thước.
2. API lưu vào kho staging riêng với tên file do server sinh, hoặc parse rồi chuyển dữ liệu thành bản ghi có cấu trúc.
3. Worker được ủy quyền dùng `UNWIND` qua Java Driver hoặc quy trình import được kiểm soát.
4. File tạm được xóa theo chính sách sau khi import và đối soát thành công.

**Không dùng tên file do client gửi** để ghép trực tiếp vào file URL mà Neo4j chạy. Việc tham số hóa Cypher giúp giảm Cypher injection, nhưng **không tự bảo vệ khỏi path traversal hoặc SSRF** nếu vẫn chấp nhận URL/đường dẫn tùy ý.

## 3. `LOAD CSV` với file:/// và thư mục import

### 3.1. Nguyên tắc thư mục import

Neo4j có thể nạp CSV từ file URL khi cấu hình cho phép. Trong cấu hình self-managed của dòng 5.x, hai setting liên quan thường gặp:

~~~properties
# neo4j.conf - minh họa cho Neo4j self-managed
server.directories.import=import
dbms.security.allow_csv_import_from_file_urls=true
~~~

Ý nghĩa:

- `server.directories.import` quy định vị trí **thư mục import được phép** cho các file URL mà cơ chế tương ứng đọc. Giá trị tương đối được Neo4j giải quyết theo cấu trúc thư mục server; vị trí vật lý chính xác tùy phương thức cài đặt.
- `dbms.security.allow_csv_import_from_file_urls` kiểm soát việc `LOAD CSV` có được đọc qua **`file:///`** hay không. Đặt `false` khi không có nhu cầu import tệp cục bộ.
- Nếu cần nhập dữ liệu từ URL HTTPS, việc tắt **file URL** không đồng nghĩa đã cấm mọi URL mạng. Hai đường này cần được đánh giá độc lập.

**Không bỏ hẳn ràng buộc import directory chỉ để “cho chạy được” một file nằm ở nơi khác.** Một số cấu hình/cách dùng plugin có thể làm mất ranh giới đường dẫn khi thư mục import không được giới hạn. Thiết kế đúng là **đưa dữ liệu vào khu vực import đã được kiểm duyệt**, không mở toàn bộ filesystem.

### 3.2. Ví dụ nhập CSV trong phạm vi đã cho phép

Giả sử quản trị viên đã đặt tệp `customers.csv` vào thư mục import thực tế của Neo4j và tài khoản đọc có quyền hợp lệ:

~~~csv
customerId,displayName
C-101,Lan
C-102,Minh
~~~

Kiểm tra schema trước:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Lệnh đọc/ghi:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row
WHERE row.customerId IS NOT NULL
  AND trim(row.customerId) <> ''
MERGE (c:Customer {customerId: trim(row.customerId)})
SET c.displayName = row.displayName;
~~~

Điểm cần hiểu:

1. Neo4j Server mở tệp, **không phải Java client**.
2. `WITH HEADERS` đọc dòng đầu làm tên cột; dữ liệu CSV vẫn cần kiểm tra kiểu và điều kiện nghiệp vụ.
3. `MERGE` theo khóa ổn định giúp có thể chạy lại trong trường hợp đơn giản; **constraint** giúp chống node trùng dưới các cuộc đua ghi.
4. Người chạy Cypher còn cần **quyền đọc/ghi graph và quyền nạp dữ liệu** phù hợp với edition/version, không chỉ quyền truy cập hệ điều hành.
5. Một file URL đúng cú pháp không chứng minh rằng file thật sự tồn tại hoặc user/process có quyền đọc.

Với file lớn, chia transaction theo cơ chế `CALL { ... } IN TRANSACTIONS` hoặc batching được hỗ trợ trong phiên bản Cypher đang chạy. **Mỗi batch commit riêng**, vì thế phải thiết kế retry, checkpoint và làm sạch dữ liệu thay vì giả định toàn bộ import là một transaction duy nhất.

### 3.3. Khác biệt giữa file URL và đường dẫn hệ điều hành

Ví dụ Neo4j self-managed:

~~~text
NEO4J_HOME/
  conf/neo4j.conf
  import/
    customers.csv
    products.csv
~~~

Trong cấu hình import directory ở trên, cách dùng thường là `file:///customers.csv`, **không phải** `file:///NEO4J_HOME/import/customers.csv`. Trên Linux container, đường dẫn thật trong container có thể là `/var/lib/neo4j/import`; trên máy Windows, đường dẫn vật lý lại khác. **Đừng dùng đường dẫn máy host trong câu Cypher** khi database chạy trong Docker/Kubernetes.

Tên tệp có khoảng trắng, Unicode hoặc ký tự đặc biệt phải được mã hóa đúng cho file URL, nhưng **việc encode không thay thế kiểm tra đường dẫn**. Không cho người dùng thao tác `..`, dạng URL mã hóa nhiều lần hoặc symlink trỏ ra ngoài khu vực cho phép. Kiểm soát cả cấu hình Neo4j **và** cấp quyền filesystem/mount.

### 3.4. Khi nên tắt local file import hoàn toàn

Nếu mọi lần nhập dữ liệu đều đi qua backend và API dùng `UNWIND`, có thể cấu hình:

~~~properties
dbms.security.allow_csv_import_from_file_urls=false
~~~

Đây là **hàng rào thêm**, không phải thay thế quyền hệ điều hành hoặc kiểm soát procedure: một plugin có khả năng đọc file khác vẫn phải được cấu hình riêng. Đổi cấu hình Neo4j thường cần quy trình restart/redeploy và kiểm tra lại theo bản cụ thể.

## 4. Path traversal, symlink và quyền hệ điều hành

**Path traversal** xảy ra khi đường dẫn do người gọi kiểm soát được diễn giải thành vị trí **ngoài thư mục được cấp phép**. Ví dụ một endpoint:

~~~text
POST /import?filename=customers.csv
POST /import?filename=../../conf/neo4j.conf
~~~

Mã nguy hiểm trong application:

~~~java
// Không làm thế này: tên file do client điều khiển.
String cypher =
        "LOAD CSV FROM 'file:///" + requestFilename + "' AS row ...";
~~~

Đây vừa là thiết kế chấp nhận đường dẫn tùy ý, vừa tiềm ẩn **Cypher injection** vì nối chuỗi đầu vào vào mã truy vấn. Kể cả chuyển sang tham số URL thì đầu vào không đáng tin vẫn có thể chỉ tới một tài nguyên không được phép.

### Ranh giới bảo vệ theo nhiều lớp

| Lớp | Cách áp dụng | Lý do |
| --- | --- | --- |
| **API** | Client chọn `datasetId` trong danh sách được cấp phép, không gửi filesystem path | Không tạo chức năng “đọc file tùy ý” |
| **Staging** | Server tự sinh tên file; kiểm tra định dạng, kích thước, schema, checksum | Ngăn nội dung xấu và file giả mạo |
| **Canonical path** | Khi thao tác file phía ứng dụng, resolve/normalize và so với thư mục gốc đã cố định | Chặn `../` và các biến thể |
| **Filesystem** | User chạy Neo4j chỉ đọc thư mục import; không đọc secret/backup ngoài phạm vi | Giới hạn hậu quả khi có lỗi |
| **Container** | Mount đúng thư mục, ưu tiên read-only, không mount cả host/root/`conf` | Giảm bề mặt filesystem |
| **Plugin config** | Giữ cơ chế dùng import directory, không cho plugin tự ý truy cập mọi path | Tránh vượt ranh giới qua thủ tục mở rộng |

**Một điểm sâu hơn:** `Path.normalize()` hoặc so chuỗi prefix **không đủ** chống symlink và các cuộc đua TOCTOU (*time-of-check to time-of-use*). Với file upload do người dùng có thể thay thế sau lúc kiểm tra, hãy dùng thư mục staging không cho user khác ghi, tên file do backend tạo, mở file bằng API an toàn và kiểm tra *real path* khi thích hợp. Trên production, không mount thư mục chứa symlink chưa kiểm soát vào import.

Một ví dụ ở tầng Java, chỉ minh họa **bước đối chiếu đường dẫn** với tệp đã tồn tại:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SafeStagingFile {
    public static Path resolveExisting(
            Path trustedRoot, String serverGeneratedName)
            throws IOException {
        Path root = trustedRoot.toRealPath();
        Path candidate = root.resolve(serverGeneratedName).normalize();
        Path actual = candidate.toRealPath();

        if (!actual.startsWith(root) || !Files.isRegularFile(actual)) {
            throw new SecurityException("File outside import staging");
        }
        return actual;
    }
}
~~~

**Giới hạn của đoạn mã:** Nó không tự khóa file chống bị thay thế **sau khi kiểm tra**, và không nên dùng trực tiếp với filename do client gửi. Quy trình mạnh hơn mở/đọc file trong staging đã được kiểm soát chặt quyền ghi hoặc chuyển dữ liệu sang container/worker qua kênh đáng tin cậy.

## 5. URL HTTP(S): mối đe dọa SSRF

Neo4j có thể tải dữ liệu từ URL ngoài khi câu Cypher/procedure cho phép, ví dụ:

~~~cypher
LOAD CSV WITH HEADERS
FROM 'https://data.example.org/exports/products.csv' AS row
RETURN row.sku AS sku, row.name AS name
LIMIT 10;
~~~

**SSRF** xảy ra khi kẻ tấn công khiến **server** gửi request tới nơi mà chính kẻ đó bình thường không thể truy cập. Máy Neo4j trong VPC có thể nhìn thấy các endpoint nội bộ, localhost hoặc dịch vụ metadata cloud mà máy của người dùng Internet không nhìn thấy.

Các dạng đầu vào rủi ro:

~~~text
http://127.0.0.1:port/admin
http://10.0.0.5/internal
http://169.254.169.254/...
https://attacker-controlled.example/redirect-to-private
~~~

Các URL chỉ là **minh họa loại đích nguy hiểm**. Việc gọi endpoint metadata hay nội bộ không phải chức năng hợp lệ của một API nhập sản phẩm.

### 5.1. Tại sao “chỉ chấp nhận https” chưa đủ?

HTTPS bảo vệ **kênh truyền** khi xác minh chứng chỉ đúng; nó không xác định URL đó có **được phép về nghiệp vụ** hay không. Một URL HTTPS do kẻ tấn công kiểm soát có thể:

- Chuyển hướng sang HTTP hoặc tới địa chỉ mạng nội bộ.
- Trả file quá lớn, dữ liệu sai schema, nhiều redirect hoặc response chậm.
- Ghi nhận IP máy Neo4j và thông tin có trong header nếu ứng dụng chuyển tiếp.
- Sử dụng DNS thay đổi địa chỉ sau lúc kiểm tra (*DNS rebinding*).

Vì vậy, kiểm soát host/domain **ở tầng ứng dụng** là cần thiết nhưng chưa đủ nếu client được cung cấp URL tự do; phải xét redirect, kết quả DNS, IP đích sau khi resolve, timeout và **egress policy** ở tầng mạng.

### 5.2. Mô hình nhập URL an toàn hơn

~~~mermaid
flowchart LR
    C["Client: datasetId"] --> A["Import API"]
    A --> M["Danh mục nguồn đã duyệt"]
    M --> F["Fetcher/staging service<br/>egress + validation"]
    F --> Q["Parse + schema validate"]
    Q --> J["Java Driver / UNWIND"]
    J --> N[("Neo4j")]
~~~

Thay vì cho client gửi bất kỳ URL nào tới `LOAD CSV` hoặc `apoc.load.json`:

1. API nhận **`datasetId`** hoặc một khóa nguồn đã được cấu hình bởi quản trị viên.
2. Fetcher riêng chỉ được đi tới endpoint đã cho phép, kiểm tra redirect và giới hạn số hop.
3. Kết nối sử dụng HTTPS/TLS với xác minh chứng chỉ; secret lấy từ secret manager, không đưa vào URL query string.
4. Fetcher giới hạn kích thước, thời gian kết nối/đọc, tần suất, định dạng và số bản ghi.
5. Dữ liệu được validate, log theo request ID rồi chuyển thành batch `UNWIND` qua Driver.

Điểm mạnh: **Neo4j không cần kết nối Internet rộng** để thực hiện nhập dữ liệu. Fetcher chuyên trách có thể chạy ở mạng tách biệt và có chính sách tải rõ ràng.

### 5.3. Network egress là hàng rào quan trọng

Tùy deployment, áp dụng firewall, Kubernetes NetworkPolicy, service mesh/proxy hoặc VPC egress control:

- Chỉ cho Neo4j ra mạng khi có yêu cầu nghiệp vụ cụ thể.
- Không cho Neo4j tới metadata cloud, mạng quản trị, loopback của service khác hoặc các dải IP nội bộ ngoài danh sách đã duyệt.
- Hạn chế DNS và redirect theo chính sách của egress proxy; logging không chứa thông tin nhạy cảm trong URL.
- Cho phép endpoint cập nhật plugin/tải file bằng **quy trình quản trị tách biệt**, không mở Internet vô hạn cho tài khoản query.

Một số tính năng Neo4j có cơ chế giới hạn quyền `LOAD` theo URL hoặc dải CIDR tùy phiên bản/edition. Các quyền ở tầng database là hàng rào bổ sung, **không thay thế** firewall và policy của mạng.

## 6. Cypher parameter không phải công cụ kiểm soát URL

Neo4j hỗ trợ dùng tham số thay cho việc nối chuỗi vào Cypher, ví dụ:

~~~cypher
LOAD CSV WITH HEADERS FROM $sourceUrl AS row
RETURN row.customerId
LIMIT 100;
~~~

Việc truyền `$sourceUrl` giảm rủi ro **chèn mã Cypher** so với ghép câu lệnh:

~~~java
// Đúng về tham số hóa, NHƯNG chưa đủ an toàn về URL:
tx.run("""
    LOAD CSV WITH HEADERS FROM $sourceUrl AS row
    RETURN row.customerId AS customerId
    LIMIT 100
    """, java.util.Map.of("sourceUrl", externalUrl));
~~~

Nếu `externalUrl` được người dùng tự do lựa chọn, database vẫn có thể được yêu cầu truy cập đích không được phép. Cần kiểm tra **quyền gọi nguồn** độc lập với kiểm tra cú pháp truy vấn.

Một nguyên tắc thực hành: **tham số hóa chống injection; allowlist nguồn + egress chống SSRF; giới hạn thư mục + quyền OS chống đọc tệp ngoài phạm vi.** Không có lớp nào thay thế hoàn toàn hai lớp còn lại.

## 7. APOC: cấu hình đọc/ghi file riêng với LOAD CSV

**APOC** là bộ procedure/function mở rộng cho Neo4j. Một số procedure hỗ trợ import/export CSV, JSON, XML, GraphML hoặc tải nội dung từ URL. Cài APOC **không đồng nghĩa** mọi chức năng đọc/ghi tệp đã được cho phép.

Trong các dòng APOC Core/Extended hiện đại, cấu hình liên quan tới file thường được đặt trong `apoc.conf`:

~~~properties
# apoc.conf - ví dụ hardening khi KHÔNG cần plugin đọc/ghi file
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

Diễn giải:

- `apoc.import.file.enabled`: bật/tắt chức năng **APOC import file** tương ứng.
- `apoc.export.file.enabled`: bật/tắt chức năng **APOC export file** tương ứng.
- `apoc.import.file.use_neo4j_config=true`: yêu cầu cơ chế import của APOC tuân theo giới hạn thư mục Neo4j trong những procedure hỗ trợ quy tắc này.

**Đừng đặt `apoc.import.file.use_neo4j_config=false` chỉ để truy cập file bên ngoài import folder.** Trong các cấu hình cho phép, điều đó có thể nới đáng kể giới hạn filesystem của APOC. Đây không phải một lựa chọn tối ưu hiệu năng, mà là **thay đổi biên bảo mật**.

### 7.1. Khi thực sự cần import file bằng APOC

Trên **máy chủ tự quản** có quy trình staging an toàn, có thể cân nhắc:

~~~properties
# Chỉ dùng khi đã duyệt nghiệp vụ và quyền OS/container:
apoc.import.file.enabled=true
apoc.import.file.use_neo4j_config=true
apoc.export.file.enabled=false
~~~

Sau đó chỉ cấp quyền thực thi procedure cần dùng cho vai trò importer phù hợp. Bật import file không nên kéo theo bật export file nếu không có nhu cầu; **export** tạo thêm nguy cơ ghi vào filesystem hoặc mang dữ liệu nhạy cảm ra ngoài.

### 7.2. APOC và remote URL là bề mặt riêng

Một procedure như `apoc.load.json` có thể tải dữ liệu JSON từ URL theo chức năng được hỗ trợ. **Tắt `apoc.import.file.enabled` không được xem là đã vô hiệu hóa mọi request HTTP(S)** từ các procedure khác. Mỗi procedure/plugin có khả năng network cần được đánh giá riêng:

- Có nhận URL do user kiểm soát không?
- Có tuân theo chính sách redirect/timeout/TLS không?
- Có thể gửi header chứa secret hay không?
- Có thể truy cập localhost, IP private hoặc metadata service không?
- Role nào có thể gọi procedure đó?

Nếu không thể bảo đảm URL đáng tin, **không cấp quyền thực thi** procedure tải URL cho role đó hoặc chuyển việc tải qua fetcher được kiểm soát ở ứng dụng.

## 8. Phân biệt APOC Core, APOC Extended, GDS và plugin khác

Neo4j có các phần mở rộng khác nhau về mục đích và quyền:

| Thành phần | Vai trò | Điều kiện vận hành/bảo mật |
| --- | --- | --- |
| **Cypher lõi** | `MATCH`, `CREATE`, `LOAD CSV` và các clause được hỗ trợ | Role, quyền `LOAD`, cấu hình file URL |
| **APOC Core** | Utility/procedure phổ biến, tùy bản Neo4j | Plugin đúng version, `apoc.conf`, quyền procedure |
| **APOC Extended** | Các procedure bổ sung, trong đó có thể có tích hợp hệ thống ngoài | Phát hành/version riêng; chỉ cài phần thật sự cần |
| **Graph Data Science (GDS)** | Projection và thuật toán trên graph trong bộ nhớ | Plugin tương thích, license/edition, RAM/CPU và quyền chạy procedure |
| **Plugin bên thứ ba** | Mở rộng do nhà cung cấp hoặc nhóm tự viết | Đánh giá mã/nguồn, dependency, quyền filesystem/network và vòng đời nâng cấp |

**Không coi một JAR plugin là mã “vô hại” chỉ vì câu gọi trông giống Cypher.** Plugin chạy trong tiến trình hoặc môi trường server với những quyền mà cơ chế plugin/procedure được cấp. Lỗ hổng trong plugin hoặc dependency có thể ảnh hưởng dữ liệu, network hoặc khả năng sẵn sàng.

### 8.1. Quy trình đưa plugin vào production

1. Chỉ lấy plugin từ **nguồn phát hành đã duyệt**, ưu tiên official distribution phù hợp edition/version.
2. Ghim version Neo4j và plugin; đối chiếu **compatibility matrix** thay vì dùng `latest` tùy ý.
3. Kiểm tra checksum/chữ ký khi nhà phát hành cung cấp; quét dependency và theo dõi thông báo bảo mật.
4. Kiểm tra nhu cầu `procedures.unrestricted`: quyền không hạn chế chỉ cấp cho namespace/procedure **thật sự bắt buộc**.
5. Đặt plugin ở thư mục có quyền ghi được giới hạn cho quản trị/deployment, không cho tài khoản ứng dụng sửa JAR.
6. Restart/redeploy theo quy trình; kiểm tra log tải plugin và danh sách procedure sau khi khởi động.
7. Đo tài nguyên, điều kiện rollback version và ảnh hưởng tới các transaction đang chạy.

**Đối với Aura:** môi trường được quản lý thường **không cho người thuê tự chép JAR bất kỳ vào máy chủ**. Kiểm tra danh sách procedure/plugin mà gói dịch vụ hỗ trợ và dùng API/Java integration hoặc dịch vụ analytics bên ngoài nếu cần tính năng không có sẵn.

## 9. Procedure allowlist và unrestricted: hai việc khác nhau

Trong self-managed Neo4j 5.x, các setting thường dùng:

~~~properties
# neo4j.conf - MINH HỌA, phải điều chỉnh theo plugin và nhu cầu thật
dbms.security.procedures.allowlist=apoc.coll.*,apoc.text.*

# Không tự cấp unrestricted cho mọi plugin.
# Chỉ khai báo pattern được tài liệu plugin yêu cầu thực sự.
# dbms.security.procedures.unrestricted=...
~~~

`allowlist` kiểm soát **procedure/function nào được phép nạp hoặc hiển thị** theo cơ chế hỗ trợ của version. `unrestricted` liên quan tới việc procedure được phép sử dụng **API nội bộ có đặc quyền nâng cao** mà Neo4j bình thường chặn; nó **không phải một role read-only**.

Hai setting này **không thay thế phân quyền người dùng**:

1. Procedure được **cài đặt/nạp** trên server hay chưa?
2. Procedure có được **cho phép** qua cấu hình allowlist/unrestricted tương ứng không?
3. **Role** của người gọi có quyền `EXECUTE PROCEDURE` (và khi cần `EXECUTE BOOSTED PROCEDURE`) không?
4. Procedure có được phép truy cập file/URL theo cấu hình APOC và network/OS không?

**Anti-pattern nguy hiểm:**

~~~properties
# KHÔNG dùng làm cấu hình bảo mật mặc định.
dbms.security.procedures.unrestricted=*
dbms.security.procedures.allowlist=*
~~~

Thiết lập kiểu “mọi thứ đều được phép” làm tăng mạnh khả năng khai thác các procedure ngoài ý muốn. Không khắc phục lỗi “procedure không tìm thấy” bằng cách mở `*` mà chưa biết nguyên nhân.

### 9.1. Role-based access control (RBAC)

Neo4j Enterprise có mô hình role và quyền chi tiết hơn Community. Với deployment hỗ trợ syntax tương ứng, quản trị viên có thể:

~~~cypher
// Chạy trong ngữ cảnh quản trị phù hợp trên bản hỗ trợ RBAC.
CREATE ROLE import_operator IF NOT EXISTS;

// Chỉ là ví dụ cấp một procedure cụ thể nếu đã được cài và cho phép:
GRANT EXECUTE PROCEDURE apoc.load.json ON DBMS
TO import_operator;
~~~

Cấp thêm **quyền đọc/ghi dữ liệu** theo use case và yêu cầu LOAD của Neo4j phù hợp phiên bản. Không tự gán role import cho tài khoản API phục vụ mọi người dùng Internet. Ngược lại, nếu chỉ cần query graph, role không cần quyền tải file hoặc gọi URL.

Khi một procedure yêu cầu quyền boosted, cần đánh giá **rủi ro và phạm vi quyền cụ thể** thay vì cấp `EXECUTE BOOSTED PROCEDURE *` cho cả nhóm. Mọi ví dụ `GRANT` phải được đối chiếu với version/edition: Community không cung cấp mọi khả năng RBAC của Enterprise.

## 10. Docker, Kubernetes và filesystem hardening

Container không tự biến một đường dẫn file thành an toàn. Nếu mount cả thư mục host chứa secret/backup vào container Neo4j, các file đó có thể bị tiếp cận khi có cấu hình, quyền hoặc plugin nguy hiểm.

### 10.1. Sơ đồ mount an toàn

~~~text
Host:
  /srv/neo4j/data/          (database files, private)
  /srv/neo4j/import-safe/   (chỉ CSV được duyệt)
  /srv/neo4j/secrets/       (không mount vào import)

Container Neo4j:
  /data                     (database volume)
  /import                   (read-only staging mount)
  /conf                     (config do deployment quản lý)
~~~

Đặt trong `neo4j.conf` (nếu áp dụng cho image/version của bạn):

~~~properties
server.directories.import=/import
dbms.security.allow_csv_import_from_file_urls=true
~~~

Ví dụ **minh họa phần mount trong Docker Compose**, không phải cấu hình deploy hoàn chỉnh:

~~~yaml
services:
  neo4j:
    image: neo4j:5.26
    volumes:
      - /srv/neo4j/data:/data
      - /srv/neo4j/import-safe:/import:ro
    # Bổ sung auth, secrets, resource limits, TLS, network và config
    # theo hệ thống thật. Không hard-code mật khẩu ở file compose công khai.
~~~

**Lưu ý:** Chọn image Neo4j tương thích phần cứng và các plugin đang dùng; tag trên chỉ phục vụ ví dụ, không phải khuyến nghị version mới nhất. Container phải có quyền đọc import mount, nhưng không nên có quyền ghi tệp CSV đã duyệt. Quyền truy cập database files và import là hai phạm vi tách biệt.

### 10.2. Checklist triển khai container

- Chạy tiến trình với **user không có quyền root** khi hệ thống hỗ trợ.
- Không dùng privileged container hoặc mount Docker socket vào Neo4j.
- Mount import **đúng một thư mục** và ưu tiên `readOnly`; không mount cả `/`, `/etc`, thư mục home hoặc secret.
- Giữ `plugins`, `conf`, `certificates` và thư mục import ở các volume/permission khác nhau.
- Giới hạn network egress đến những endpoint được duyệt; áp dụng NetworkPolicy phù hợp CNI/Kubernetes thực tế.
- Kiểm soát CPU/RAM; import lớn có thể làm page cache, heap, disk và GC chịu áp lực.
- Thử trên môi trường staging với file giả lập có kích thước tối đa theo nhu cầu nghiệp vụ.

## 11. API Java/Spring: cách nhập dữ liệu mà database không cần đọc URL

Nếu Neo4j chỉ cần nhận bản ghi đã được ứng dụng kiểm duyệt, Java Driver có thể gửi **danh sách dữ liệu có cấu trúc** qua tham số. Đây thường là lựa chọn linh hoạt và giảm đặc quyền hơn so với `LOAD CSV FROM $clientUrl`.

### 11.1. Java Driver + UNWIND

~~~cypher
UNWIND $customers AS item
WITH item
WHERE item.customerId IS NOT NULL
  AND trim(item.customerId) <> ''
MERGE (c:Customer {customerId: item.customerId})
SET c.displayName = item.displayName;
~~~

Ví dụ phần service Java:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerImporter {
    private final Driver driver;

    public CustomerImporter(Driver driver) {
        this.driver = driver;
    }

    public void importBatch(List<Map<String, Object>> sanitizedCustomers) {
        // Caller phải validate schema/kích thước và giới hạn số phần tử.
        if (sanitizedCustomers.isEmpty() || sanitizedCustomers.size() > 500) {
            throw new IllegalArgumentException("Invalid batch size");
        }

        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run("""
                    UNWIND $customers AS item
                    MERGE (c:Customer {customerId: item.customerId})
                    SET c.displayName = item.displayName
                    """, Map.of("customers", sanitizedCustomers))
                  .consume();
                return null;
            });
        }
    }
}
~~~

Điểm tốt của mẫu trên:

- Neo4j không cần mở **tệp** hay đi ra **Internet**; server chỉ nhận tham số qua Bolt.
- Java quản lý xác thực nguồn, parsing và validation; transaction Neo4j commit nguyên tử cho từng batch.
- Query được tham số hóa, không ghép dữ liệu người dùng vào Cypher.
- Dùng `Driver` chung, `Session` theo request/batch và `executeWrite` cho thao tác có ghi.

**Giới hạn:** Callback managed transaction có thể chạy lại vì lỗi transient. Input batch và ID phải ổn định; không phát email/HTTP side effect trong callback. Mỗi batch commit riêng, nên không mặc định tất cả batch rollback cùng nhau khi một batch sau thất bại. Với dữ liệu rất lớn, cần pipeline streaming/batch có checkpoint, retry và backpressure.

### 11.2. Không tin dữ liệu chỉ vì đã qua API

Trước khi đưa row vào `UNWIND`:

- Giới hạn số row, số cột, độ dài chuỗi, số byte và nested depth.
- Kiểm tra kiểu dữ liệu, định dạng ngày, enum/status và các business key.
- Xác thực user có quyền **import đúng dataset/tenant**; không nhập lẫn dữ liệu khách hàng khác.
- Dùng constraint để bảo vệ node ID, điều kiện/transaction để bảo vệ relationship.
- Loại bỏ/sanitize nội dung nguy hiểm cho các hệ thống downstream (HTML/report/log), không chỉ Cypher.
- Ghi ID job, số row nhận/chấp nhận/từ chối; không log toàn bộ dữ liệu nhạy cảm.

Một payload nhỏ có thể chứa chuỗi cực dài hoặc đồ thị quan hệ gây fan-out. Kích thước **số bản ghi** và **tổng byte/độ phức tạp** cần được giới hạn song song.

## 12. Quyền Neo4j và phân tách trách nhiệm

Để giảm hậu quả nếu credential của API bị lộ, không dùng cùng một tài khoản quản trị cho mọi công việc.

| Loại tài khoản | Quyền nên cấp | Quyền nên tránh |
| --- | --- | --- |
| **API đọc graph** | Đọc đúng label/relationship/thuộc tính cần thiết | Import file, gọi URL, procedure đặc quyền, sửa graph |
| **API ghi nghiệp vụ** | Ghi đúng phần graph được sở hữu | Cài plugin, sửa config, truy cập tệp hệ thống |
| **Import worker** | `LOAD`/procedure cần thiết và ghi lên tập dữ liệu được cho phép | Quyền admin tổng thể, export tệp tùy ý |
| **Graph analyst** | Đọc dữ liệu phù hợp, thuật toán/phân tích được duyệt | Tải URL mạng không cần thiết, ghi nhạy cảm |
| **DB administrator** | Quản trị cấu hình, roles, backup và vận hành | Không dùng tài khoản này cho endpoint công khai |

Một tổ chức cần kiểm tra cả **RBAC của Neo4j** và **quyền OS/network**. Ví dụ, role database có thể được phép gọi một procedure nhưng container lại không được phép kết nối Internet; đây là **phòng thủ nhiều lớp**, không phải lỗi phải “mở cho tất cả”.

### 12.1. Multi-tenant và các đường import

Với hệ thống nhiều khách hàng/tenant, một file CSV từ tenant A có thể chứa business ID thuộc tenant B. Nếu `MERGE (c:Customer {customerId: item.id})` không xét tenant khi ID chỉ duy nhất trong tenant, dữ liệu có thể bị nhập đè hoặc nối nhầm relationship.

Nên dùng **khóa logic gồm tenantId + localId**, hoặc ID toàn cục bảo đảm duy nhất, kèm constraint và predicate tương ứng:

~~~cypher
CREATE CONSTRAINT customer_tenant_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

Ở ví dụ này, ứng dụng phải lấy `tenantId` từ **ngữ cảnh xác thực được tin cậy**, không lấy giá trị tùy ý từ CSV để quyết định có thể ghi vào tenant nào. Nếu edition/version không hỗ trợ dạng constraint mong muốn, dùng mô hình định danh/constraint khác được hỗ trợ nhưng không bỏ kiểm tra tenant.

## 13. Giám sát, audit và quản lý sự cố

Không thể bảo vệ import và plugin chỉ bằng một tập setting cố định. Cần biết **ai** gọi chức năng nguy hiểm, **nguồn** nào được tải, **kết quả** ra sao và việc truy cập có đúng kỳ vọng không.

| Nhóm chỉ số/sự kiện | Nên ghi nhận | Dấu hiệu cảnh báo |
| --- | --- | --- |
| **Import job** | Job ID, dataset ID, user/role, thời gian, số row và trạng thái | File lớn bất thường, nhiều row lỗi |
| **Truy cập URL** | Domain đã duyệt, mã lỗi, latency, kích thước; tránh lưu secret trong URL | Nhiều host lạ, redirect bất thường, private IP |
| **Quyền/procedure** | Lần gọi bị từ chối, thay đổi role, cấp boosted procedure | Tăng quyền đột ngột, dùng procedure ngoài kế hoạch |
| **Plugin lifecycle** | Thêm/xóa JAR, checksum, version, lỗi khởi động | JAR không rõ nguồn, thay đổi sau deployment |
| **Neo4j** | CPU, heap, GC, page cache, disk, transaction latency, lỗi Cypher | Import làm nghẽn workload giao dịch |
| **Filesystem** | Dung lượng import, file tạm còn sót, permission change | Tệp lạ/symlink trong thư mục import |
| **Mạng** | Egress đến host/dải IP, DNS, TLS failure | Kết nối tới địa chỉ không thuộc danh sách |

Trong Neo4j Enterprise/self-managed, khả năng audit và các log cụ thể phụ thuộc cấu hình/version. Không bật logging ở mức ghi toàn bộ Cypher parameters nhạy cảm mà chưa đánh giá **bảo mật dữ liệu** và overhead. Với Aura, dùng những log/metric được nhà cung cấp hiển thị thay vì giả định có quyền đọc file log trên máy chủ.

### Quy trình phản ứng khi nghi bị khai thác

1. Giới hạn ngay endpoint import hoặc role/procedure đang bị lạm dụng, tránh làm mất bằng chứng.
2. Kiểm tra egress/network logs, job history, query audit và thay đổi plugin/config.
3. Luân chuyển credential/tokens có khả năng bị lộ; bảo vệ các kho secret liên quan.
4. Đối soát node/relationship và các thay đổi bất thường; dùng backup/restore theo playbook khi cần.
5. Vá ứng dụng/plugin/Neo4j, cập nhật allowlist, kiểm thử hồi quy và theo dõi sau khắc phục.

Đây là quy trình khái quát; phải tuân thủ chính sách ứng cứu sự cố của tổ chức và yêu cầu lưu giữ bằng chứng.

## 14. Các lỗi phổ biến và chẩn đoán theo lớp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra an toàn |
| --- | --- | --- |
| `LOAD CSV` không đọc `file:///customers.csv` | File URL bị cấm, file không có trong import dir, sai quyền OS | Kiểm tra config và đường dẫn trên **Neo4j Server**, không mở toàn filesystem |
| Chỉ đọc được file trên host, không đọc trong Docker | Chưa mount import hoặc mount nhầm đường dẫn container | Kiểm tra volume và cấu hình `server.directories.import` |
| Lỗi HTTP khi tải URL | DNS, TLS, proxy, firewall, timeout hoặc URL không được phép | Kiểm tra allowlist và egress logs; không tắt TLS verification |
| `apoc.load.json` không tồn tại | APOC chưa cài, bản không phù hợp, allowlist loại trừ hoặc thiếu quyền | Kiểm tra plugin/version/procedure catalog/quyền |
| APOC file import bị từ chối | `apoc.import.file.enabled=false` hoặc thư mục/quyền không hợp lệ | Chỉ bật cho use case đã duyệt; giữ `use_neo4j_config=true` |
| Procedure trả `permission denied` | Role thiếu quyền `EXECUTE`/`BOOSTED` hoặc quyền graph | Cấp quyền cụ thể, không cấp admin toàn cục |
| Plugin không khởi động | JAR sai phiên bản hoặc thiếu dependency, cấu hình không hợp lệ | Xem log khởi động và ma trận tương thích |
| Import bị chậm/thiếu RAM | File lớn, transaction quá dài, cạnh tranh tài nguyên | Batch, giới hạn size/timeout, đo heap/GC/disk |
| Đọc được URL nhưng vi phạm chính sách | Server có egress quá rộng hoặc role được cấp nhầm | Thu hẹp nguồn, proxy, firewall và quyền procedure |

**Đặc biệt:** Không khắc phục “đọc file không được” bằng các thay đổi kiểu “tắt tất cả cơ chế kiểm tra”, “unrestricted=*”, “mount root host” hay “bỏ xác minh TLS”. Đó là những thao tác mở rộng bề mặt tấn công vượt xa nhu cầu import một file.

## 15. Bài thực hành: nhập một CSV an toàn

### Mục tiêu

Trong môi trường Neo4j **thử nghiệm tự quản**, nhập dữ liệu khách hàng nhưng không cho tài khoản API đọc mọi file hoặc gọi mọi URL. Thực hiện trên database demo riêng và có quyền chỉnh cấu hình theo quy trình.

### Bước 1 — Xác định ranh giới

Ghi lại:

- Neo4j chạy local, Docker, Kubernetes hay Aura?
- Đường dẫn **import thực sự trên server/container** là gì?
- User hệ điều hành nào chạy Neo4j; thư mục import có quyền đọc/ghi thế nào?
- Ai được gọi `LOAD CSV`; role nào được chạy APOC?
- Neo4j có thực sự cần kết nối Internet để import không?

### Bước 2 — Thiết lập import staging

Đặt **chỉ** `customers.csv` đã kiểm tra schema/size vào thư mục import. Nếu dùng container, mount chỉ thư mục đó và ưu tiên read-only. Không copy secret, file cấu hình, certificate private key hay backup database vào thư mục import.

### Bước 3 — Đọc file trong phạm vi

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN row.customerId AS customerId,
       row.displayName AS displayName
LIMIT 10;
~~~

Xác nhận:

1. Có thể đọc tệp được phép, nếu feature file URL đã được bật cho lab.
2. Không lấy được file nằm ngoài import directory chỉ bằng sửa chuỗi đường dẫn.
3. Nếu tắt file URL theo config, lệnh trên bị từ chối theo kỳ vọng.

Không thử đọc tệp thật chứa dữ liệu nhạy cảm: dùng **tệp giả lập không nhạy cảm** để xác nhận cơ chế chặn.

### Bước 4 — Ghi graph bằng khóa nghiệp vụ

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row
WHERE row.customerId IS NOT NULL
  AND trim(row.customerId) <> ''
MERGE (c:Customer {customerId: trim(row.customerId)})
SET c.displayName = row.displayName;
~~~

Chạy lại bằng cùng file để kiểm tra không tạo node trùng theo `customerId`; nếu dữ liệu nguồn sai schema, đánh dấu lỗi thay vì cố ép import.

### Bước 5 — Kiểm thử URL policy

Thiết kế **một nguồn HTTPS thử nghiệm do nhóm kiểm soát**, không kết nối tới metadata cloud hay endpoint quản trị thật:

- Endpoint nằm trong allowlist được tải thành công nếu use case cho phép.
- Domain không nằm trong danh sách được **ứng dụng/fetcher từ chối** trước khi đến Neo4j.
- Redirect tới domain không được phép bị từ chối.
- File quá giới hạn byte/row hoặc response quá thời hạn bị dừng.
- Một role API chỉ đọc graph không có quyền import file/URL hay gọi procedure import nhạy cảm.

### Bước 6 — Kiểm thử plugin

Nếu không dùng APOC import/export, giữ:

~~~properties
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

Chỉ khi bài lab thực sự cần và môi trường có APOC đúng phiên bản mới cho phép import file trong khu vực được duyệt. Kiểm tra danh sách procedure và role; **không bật unrestricted wildcard để “thử cho dễ”**.

### Bước 7 — So sánh cách nhập bằng Driver

Dùng API Java ở phần 11 để gửi cùng tập `Customer` qua `UNWIND`. So sánh:

| Tiêu chí | `LOAD CSV file:///` | Java Driver + `UNWIND` |
| --- | --- | --- |
| Neo4j cần đọc filesystem server | **Có** | **Không** |
| Database cần egress HTTP | Không, với file URL nội bộ | Không, nếu ứng dụng parse sẵn |
| Validation/authorization trước import | Cần thiết kế ở quy trình staging/ứng dụng | Có thể đặt rõ trong service |
| Batch/retry | Cần thiết kế theo Cypher/transaction | Có thể quản lý theo request/batch Java |
| Phù hợp | File đã được quản trị viên đưa vào staging | API/worker nhập dữ liệu từ nguồn nhiều loại |

**Kết luận bài lab:** Mục tiêu không phải cố làm cho mọi tính năng đọc tệp/URL đều khả dụng, mà là **chỉ mở đúng đường nhập cần thiết** và có bằng chứng các đường khác bị từ chối.

## 16. Checklist hardening trước khi đưa vào production

- [ ] Xác định **ai là người đọc file/URL**: Neo4j Server, APOC procedure hay ứng dụng Java.
- [ ] Nếu dùng `LOAD CSV file:///`, chỉ dùng **thư mục import đã được kiểm duyệt** và quyền OS tối thiểu.
- [ ] Tắt `dbms.security.allow_csv_import_from_file_urls` khi không cần file URL.
- [ ] Không tạo endpoint ghép path hoặc URL do client tự do cung cấp vào Cypher/procedure.
- [ ] Kiểm tra canonical path, symlink, quyền ghi staging và các tình huống path traversal/TOCTOU.
- [ ] Chỉ cho phép URL nguồn đã duyệt; kiểm soát HTTPS, redirect, DNS, private IP, timeout và kích thước tải.
- [ ] Áp dụng firewall/egress proxy hoặc NetworkPolicy; không dựa hoàn toàn vào regex URL.
- [ ] Giữ `apoc.import.file.use_neo4j_config=true` khi dùng APOC file import tương ứng.
- [ ] Không bật `apoc.export.file.enabled` nếu nghiệp vụ không có nhu cầu export.
- [ ] Chỉ cài APOC/GDS/plugin thật sự cần, từ nguồn đáng tin và version tương thích.
- [ ] Không dùng `dbms.security.procedures.unrestricted=*` hoặc cấp boosted procedure wildcard cho role ứng dụng.
- [ ] Phân biệt procedure được **nạp**, được **allowlist**, và role được **EXECUTE**.
- [ ] Ghim image/JAR version, bảo vệ volume `plugins`/`conf`/`secrets`, hạn chế quyền container.
- [ ] Dùng business ID, uniqueness constraint, validation và batching cho dữ liệu nhập.
- [ ] Nếu có thể, tách fetcher/ingest service và chuyển batch có cấu trúc bằng Java Driver/`UNWIND`.
- [ ] Theo dõi audit, quyền bị từ chối, import job, plugin thay đổi, mạng egress và tài nguyên hệ thống.
- [ ] Kiểm thử cả **trường hợp bị chặn** trên staging; có playbook ứng cứu và quy trình rollback cấu hình.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual — File locations](https://neo4j.com/docs/operations-manual/current/configuration/file-locations/)
- [Neo4j Operations Manual — Security and authorization](https://neo4j.com/docs/operations-manual/current/security/authorization/)
- [Neo4j Operations Manual — Docker and configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/)
- [APOC Documentation — Configuration](https://neo4j.com/docs/apoc/current/config/)
- [APOC Documentation — Import](https://neo4j.com/docs/apoc/current/import/)
- [Neo4j Graph Data Science — Installation](https://neo4j.com/docs/graph-data-science/current/installation/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)

**Kết luận:** Bảo vệ đường dẫn tệp, truy cập URL và cấu hình phần mở rộng trong Neo4j là kiểm soát **những gì tiến trình database được phép đọc, gọi ra ngoài và thực thi bằng procedure**. Giới hạn thư mục import, tắt tính năng không cần, kiểm soát SSRF ở cả API lẫn mạng, cấp quyền tối thiểu cho plugin và dùng pipeline nhập dữ liệu có kiểm duyệt là các lớp bảo vệ bổ sung cho nhau. Khi cần nhập dữ liệu, hãy mở **đúng nguồn, đúng role, đúng phạm vi** và xác minh bằng cả kiểm thử thành công lẫn kiểm thử truy cập bị từ chối.
