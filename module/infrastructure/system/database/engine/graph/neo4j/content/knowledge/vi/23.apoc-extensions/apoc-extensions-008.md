# Đánh giá rủi ro của thủ tục không giới hạn và truy cập hệ thống

## 1. Vì sao APOC vừa hữu ích vừa cần kiểm soát chặt?

Trong Neo4j, Cypher thao tác với **property graph** gồm node, relationship, label, type và property. APOC (*Awesome Procedures on Cypher*) bổ sung nhiều procedure và function để biến đổi dữ liệu, nhập/xuất tệp, tải nguồn từ xa, chạy truy vấn động, làm việc theo lô và hỗ trợ vận hành. Chẳng hạn, việc trích xuất JSON từ một API có thể rất thuận tiện khi đưa dữ liệu liên kết vào đồ thị.

Tuy nhiên, một số tính năng APOC có thể tương tác với **tệp trên máy chủ**, **địa chỉ mạng**, **quy trình thực thi Cypher** hoặc những API nội bộ của Neo4j. Nếu bật quá nhiều procedure, cấu hình `unrestricted` quá rộng hoặc cấp quyền thực thi nâng cao sai đối tượng, một tài khoản ứng dụng bình thường có thể được tiếp cận chức năng mà nghiệp vụ không cần. Hậu quả tiềm ẩn gồm lộ dữ liệu, truy cập tài nguyên nội bộ qua máy chủ, ghi/xóa dữ liệu ngoài ý muốn, tiêu hao tài nguyên và mất khả năng kiểm toán.

Bài này thuộc chương **APOC và phần mở rộng** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`. Mục tiêu là **đánh giá rủi ro của thủ tục không giới hạn và truy cập hệ thống**, rồi thiết kế các lớp bảo vệ phù hợp cho ứng dụng sử dụng Cypher, Neo4j Java Driver hoặc Spring Data Neo4j.

Sau bài học, bạn có thể:

1. Phân biệt APOC Core/Extended, procedure/function và quyền thực thi của người dùng.
2. Hiểu đúng các lớp `allowlist`, `unrestricted`, `EXECUTE PROCEDURE` và `EXECUTE BOOSTED PROCEDURE`.
3. Phân tích bề mặt rủi ro từ file, mạng, Cypher động, tác vụ nền và plugin.
4. Dùng các lệnh **chỉ đọc** để kiểm kê procedure đang được nạp và quyền có liên quan.
5. Lập bảng đánh giá mức độ rủi ro, đề xuất kiểm soát và kiểm thử trên môi trường cô lập.

> **Phạm vi:** Ví dụ dành cho Neo4j 5 và các bản hiện hành, kiểm tra tài liệu tính đến **25/11/2026**. Tên procedure, hỗ trợ Cypher 5/Cypher 25, edition, quyền RBAC và cấu hình APOC có thể khác theo phiên bản. Bài chỉ dùng ví dụ kiểm tra an toàn, không yêu cầu gọi URL lạ, đọc tệp nhạy cảm hay thay đổi cấu hình của máy chủ thật.

## 2. Phân biệt APOC Core, APOC Extended và procedure tự viết

APOC không phải một quyền duy nhất, cũng không phải một process riêng biệt chạy tách Neo4j. Các procedure/function được cài dưới dạng thư viện Java, được Neo4j nạp và có thể được gọi trong Cypher theo cấu hình và quyền của người dùng.

| Thành phần | Vai trò | Điểm cần kiểm soát |
|---|---|---|
| **APOC Core** | Thư viện procedure/function được Neo4j hỗ trợ chính thức từ Neo4j 5; thường dùng cho biến đổi, nhập/xuất và thao tác graph | Chỉ kích hoạt những gì ứng dụng cần; theo dõi tương thích Neo4j/APOC |
| **APOC Extended** | Các phần mở rộng bổ sung do cộng đồng duy trì; có thể bao gồm tích hợp ngoài hoặc chức năng thực nghiệm | Xem xét dependency, quyền và cập nhật bảo mật kỹ hơn; hỗ trợ khác Core |
| **Procedure/function do tổ chức tự viết** | Mã Java chạy bên trong Neo4j qua extension API | Review mã, thư viện phụ thuộc, quyền đọc/ghi và phạm vi truy cập hệ thống |
| **Cypher thuần** | Câu lệnh được trình phân tích, planner và quyền Neo4j kiểm soát | Ưu tiên khi đã đủ tính năng; giảm dependency extension không cần thiết |

Tên bắt đầu bằng `apoc.` không nói lên rằng mọi procedure đều có cùng mức nguy hiểm. Một hàm xử lý chuỗi không giống một thủ tục mở kết nối ra ngoài hoặc thực thi truy vấn động. Phải xem **chức năng thực sự**, tham số nhận vào và quyền đang cấp.

Từ Neo4j 5, APOC Core và Extended là hai thư viện tách biệt. APOC cần tương thích với phiên bản Neo4j sử dụng; bản Neo4j mới có thể đưa một số tính năng tương đương vào Cypher, khiến procedure APOC tương ứng bị deprecated hoặc thay đổi khả dụng. Khi nâng cấp, kiểm tra **tài liệu đúng phiên bản** trước khi cho phép truy cập hệ thống.

## 3. Bốn lớp kiểm soát cần tách bạch

Một procedure xuất hiện trong danh mục không đồng nghĩa mọi người dùng được chạy nó với mọi quyền.

~~~mermaid
flowchart TD
    A["Plugin/JAR được triển khai"] --> B{"Procedure có trong allowlist để được nạp?"}
    B -->|Không| C["Không xuất hiện như procedure có thể dùng"]
    B -->|Có| D{"Procedure có cần cơ chế unrestricted?"}
    D -->|Có, được cho phép chính xác| E["Có thể dùng API bị sandbox hạn chế"]
    D -->|Không| F["Hoạt động trong ràng buộc thông thường"]
    E --> G{"Người dùng có EXECUTE và quyền dữ liệu thích hợp?"}
    F --> G
    G -->|Không| H["Bị từ chối hoặc chỉ thấy dữ liệu được phép"]
    G -->|Có| I["Chạy trong phạm vi quyền người dùng"]
    G -->|Có BOOSTED| J["Một phần quyền được nâng khi thực thi procedure"]
    I --> K["Vẫn chịu hạn chế file, mạng, OS, container"]
    J --> K
~~~

Sơ đồ là mô hình khái niệm: còn phụ thuộc quyền và cơ chế của từng procedure. Phần **unrestricted** ở đây là cấu hình cho quyền truy cập API/sandbox của extension; còn **boosted** là đặc quyền Neo4j cấp cho một **role** khi gọi procedure. Chúng khác nhau.

### 3.1. `dbms.security.procedures.allowlist` — nạp cái gì?

Đây là setting của Neo4j trong `neo4j.conf`. Nó xác định danh sách procedure/function cho phép **được nạp**. Danh sách có thể gồm tên đầy đủ hoặc ký tự đại diện `*`. Giá trị mặc định theo tài liệu hiện hành là `*`: cho phép nạp tất cả procedure có trong plugin, **nhưng không cấp quyền thực thi nâng cao cho tất cả người dùng**.

Ví dụ minh họa về một chính sách chỉ chấp nhận nhóm chức năng cần thiết:

~~~properties
# MẪU ĐỂ REVIEW, không áp dụng nguyên xi cho mọi deployment.
dbms.security.procedures.allowlist=apoc.text.*,apoc.map.*
~~~

Hãy kiểm tra dependency thực tế: có thể ứng dụng cần thêm procedure không có trong mẫu; đồng thời glob quá rộng có thể nạp tính năng ngoài dự kiến khi nâng cấp.

### 3.2. `dbms.security.procedures.unrestricted` — bỏ hạn chế sandbox đối với cái gì?

Setting này cũng ở `neo4j.conf`, cho phép những procedure/function được liệt kê có quyền truy cập đầy đủ hơn vào các API Neo4j bị hạn chế bởi sandbox. Giá trị mặc định theo tài liệu hiện hành là **rỗng**. Việc ghi `unrestricted` quá rộng có thể tạo đường đi vượt qua những rào chắn an toàn mà extension vốn phải tuân thủ.

**Ví dụ cấu hình rủi ro cần tránh**, chỉ để nhận diện trong review:

~~~properties
# ANTI-PATTERN — KHÔNG đưa vào cấu hình.
# dbms.security.procedures.unrestricted=apoc.*
~~~

Cấu hình `unrestricted=apoc.*` **không phải** câu lệnh cho phép một user đăng nhập, cũng **không giống** quyền `EXECUTE BOOSTED`. Nó mở rộng khả năng phía mã extension, trong khi người dùng vẫn cần quyền gọi procedure và các kiểm soát khác. Tuy nhiên, sự kết hợp giữa cấu hình rộng và role có quyền cao làm tăng nguy cơ đáng kể.

### 3.3. Quyền `EXECUTE PROCEDURE` / `EXECUTE FUNCTION`

Trong Neo4j Enterprise, RBAC quyết định role nào được gọi procedure/function nào. Với quyền thực thi thông thường, một procedure đọc/ghi dữ liệu phải chịu **quyền đọc/ghi của chính người dùng**. Ví dụ, role chỉ có quyền đọc không tự biến thành role ghi chỉ bằng cách gọi một procedure.

Một tài khoản có `EXECUTE PROCEDURE` cũng **không mặc nhiên** có quyền `LOAD` để đọc tài nguyên URL hoặc có quyền ghi graph. Cần kiểm tra toàn bộ quyền có hiệu lực, bao gồm quyền mặc định/thừa hưởng qua role `PUBLIC`.

### 3.4. Quyền `EXECUTE BOOSTED PROCEDURE`

`EXECUTE BOOSTED PROCEDURE` có thể cho phép procedure chạy với các quyền cao hơn quyền của user khi ở bên trong procedure. Tài liệu Neo4j nhấn mạnh người dùng cần **cả quyền EXECUTE và quyền BOOSTED** để gọi procedure ở chế độ nâng quyền.

Quyền này đặc biệt nguy hiểm đối với các họ chạy Cypher động như `apoc.cypher.*`, `apoc.do.*`, `apoc.periodic.*`, hoặc các cơ chế trigger có khả năng thực hiện lệnh dựa trên đầu vào. Nếu người dùng được boosted quá rộng và có khả năng quyết định nội dung truy vấn động, ranh giới phân quyền dữ liệu có thể mất tác dụng. Quyền boosted còn có thể vượt qua giới hạn `LOAD` của procedure.

**Không dùng `BOOSTED` để sửa một lỗi “permission denied” trước khi hiểu vì sao thao tác bị từ chối.** Thiết kế role có quyền chính xác hoặc chuyển công việc quản trị sang luồng được xác thực riêng thường phù hợp hơn.

## 4. Ma trận: cơ chế nào kiểm soát rủi ro nào?

| Câu hỏi | Kiểm soát chính | Không nên suy luận |
|---|---|---|
| Procedure có được nạp trong DBMS không? | `dbms.security.procedures.allowlist` | Nạp được ≠ user nào cũng gọi được |
| Extension có được sử dụng API Neo4j hạn chế không? | `dbms.security.procedures.unrestricted` | Unrestricted ≠ role boosted |
| Tài khoản nào được gọi procedure? | `EXECUTE PROCEDURE` / `EXECUTE FUNCTION` | Có EXECUTE ≠ có quyền ghi ngoài role |
| Procedure có chạy với quyền nâng cao không? | `EXECUTE BOOSTED PROCEDURE` | Chỉ cấp BOOSTED không đồng nghĩa tự cấp EXECUTE |
| Procedure đọc/ghi tệp nào? | `apoc.conf` + cấu hình import directory + OS permissions | Đã nạp `apoc.load.*` ≠ được đọc mọi file |
| Procedure gọi URL nào? | `LOAD` privileges/CIDR, egress firewall, IP blocklist và kiểm soát input | URL HTTPS hợp lệ ≠ endpoint được tin cậy |
| Mã extension có thể đọc gì trên host? | Quyền user chạy Neo4j, container/VM, filesystem mounts | Quyền DBMS không thay thế quyền OS |
| Ai đổi cấu hình và cài JAR? | Quyền quản trị máy chủ, quy trình deploy, review và audit | Chặn một câu Cypher không thay thế review plugin |

Điểm cốt lõi của **defense in depth** là kiểm soát ở cả ba lớp: **ứng dụng/Cypher**, **Neo4j/APOC**, **host/mạng**. Một lỗi ở một lớp không nên tự động trở thành lộ toàn bộ dữ liệu.

## 5. Những nhóm khả năng cần đánh giá rủi ro

| Họ thao tác | Ví dụ tính năng | Rủi ro cần xem xét | Hướng giảm thiểu |
|---|---|---|---|
| Đọc dữ liệu từ URL | `apoc.load.json`, `apoc.load.xml`, một số `apoc.import.*` | SSRF, đọc từ mạng nội bộ, lộ dữ liệu qua URL | Kiểm soát `LOAD`, IP/CIDR, egress, URL allowlist phía ứng dụng |
| Đọc tệp cục bộ | Những procedure nhập dữ liệu từ `file:///` | Đọc ngoài thư mục cho phép, lộ nội dung trên host | Vô hiệu khi không cần; giới hạn import directory, OS file permissions |
| Ghi/xuất tệp | `apoc.export.*` | Tạo tệp ngoài dự kiến, tràn ổ, dữ liệu nhạy cảm nằm trên disk | Tắt xuất tệp, giới hạn thư mục, quota và logging |
| Cypher động | `apoc.cypher.*`, `apoc.do.*` | Cypher injection, bypass ý định phân quyền khi boosted | Tham số hóa, không nhận fragment tùy ý, cấm boosted với role ứng dụng |
| Thực thi theo lô | `apoc.periodic.*` | Ghi số lượng lớn, khóa, áp lực heap/log và retry | Hạn chế role, batch/concurrency, timeout, kiểm soát job |
| Trigger/tác vụ nền | `apoc.trigger.*`, `apoc.jobs.*` nếu được cài | Thay đổi dữ liệu do luồng nền, khó truy nguồn và giám sát | Chỉ bật nếu cần, review trigger/job, audit và giới hạn tài nguyên |
| Tích hợp ngoài | Procedure thuộc APOC Extended hoặc plugin riêng | Credential, dependency, kết nối mạng, quyền host | Phân loại từng module, quản lý secret, cập nhật bản vá |

**Mức rủi ro không chỉ dựa vào tên procedure.** Một tính năng tải URL có thể an toàn khi URL cố định và được kiểm soát; rủi ro cao khi người dùng bên ngoài trực tiếp chọn bất kỳ địa chỉ nào, nhất là khi chạy bằng role có đặc quyền.

## 6. Rủi ro truy cập tệp và cách cấu hình theo nhu cầu

APOC Core có cấu hình đọc/ghi file riêng trong `apoc.conf`. Với Neo4j 5+, các setting `apoc.*` **không đặt trong `neo4j.conf`**; chúng nằm trong `apoc.conf` cùng thư mục cấu hình hoặc được truyền qua environment, trong đó environment có thể ghi đè giá trị của tệp.

| Setting | Công dụng | Giá trị mặc định theo tài liệu APOC Core |
|---|---|---|
| `apoc.import.file.enabled` | Cho phép APOC đọc tệp cục bộ | `false` |
| `apoc.export.file.enabled` | Cho phép APOC ghi tệp cục bộ | `false` |
| `apoc.import.file.use_neo4j_config` | Khi `true`, áp các hạn chế thư mục của Neo4j cho file access trong APOC | `true` |
| `server.directories.import` (Neo4j) | Thư mục import được dùng khi bật chế độ tuân theo cấu hình Neo4j | Thường là `import` |
| `dbms.security.allow_csv_import_from_file_urls` (Neo4j) | Cho phép/từ chối `LOAD CSV` đọc `file:///`; có liên quan khi APOC tuân theo cấu hình Neo4j | Kiểm tra giá trị hiệu lực trên phiên bản đang chạy |

**Ví dụ cấu hình hạn chế** cho dịch vụ **không cần** đọc/ghi file:

~~~properties
# conf/apoc.conf — giữ các khả năng đọc/ghi tệp bị tắt.
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

Nếu nghiệp vụ cần tải file, hãy bật **đúng chiều** đọc hoặc ghi cần thiết và giữ `apoc.import.file.use_neo4j_config=true`; xem xét quyền filesystem của process Neo4j và thư mục import. Không dùng `false` cho setting tuân thủ đường dẫn Neo4j như một cách “sửa lỗi không mở được file”: việc đó có thể mở rộng truy cập tới các đường dẫn ngoài import directory.

Lưu ý một số tài liệu APOC hoặc ví dụ cũ có biến thể tên setting. Luôn đối chiếu tên thực tế trong **tài liệu và bản APOC đang triển khai**, đồng thời phân biệt cấu hình của **Neo4j** với của **APOC**. Nếu tải file thông qua HTTP(S), bật/tắt file access **không thay thế** kiểm soát truy cập mạng.

### File access của Neo4j chạy ở đâu?

Một lệnh đọc tệp trên Neo4j server sẽ chịu quyền của **OS account chạy tiến trình Neo4j**, không phải đường dẫn và quyền của laptop đang mở Neo4j Browser. Container volume, Kubernetes mount và service account là một phần quan trọng của bề mặt rủi ro.

Nếu process chạy với quyền quá cao hoặc mount thư mục chứa backup/secret không cần thiết, việc giới hạn role database đơn thuần có thể không đủ nếu extension bị khai thác hoặc cấu hình sai. Giảm quyền OS, giới hạn mount và tách vùng dữ liệu thực hành khỏi vùng nhạy cảm.

## 7. Rủi ro mạng và SSRF: URL đến từ đâu?

**SSRF (Server-Side Request Forgery)** xảy ra khi hệ thống máy chủ bị khiến gọi tới một đích mạng ngoài ý định, dựa trên input không tin cậy. Trong bối cảnh APOC, Neo4j server là bên thực hiện HTTP request; người dùng ứng dụng có thể không có đường mạng trực tiếp tới đích đó nhưng máy chủ Neo4j có thể có.

~~~mermaid
flowchart LR
    U["Input URL từ ứng dụng"] --> A["Java/Spring API"]
    A --> N["Neo4j + APOC load từ URL"]
    N --> T["Nguồn dữ liệu được cho phép"]
    N -. "Nếu kiểm soát yếu" .-> I["Tài nguyên nội bộ ngoài phạm vi"]
~~~

Đánh giá nên hỏi:

- URL có đến từ người dùng bên ngoài, dữ liệu graph, tệp cấu hình hay một nguồn tin cậy?
- Ứng dụng có giới hạn **scheme**, host/port, redirect và địa chỉ IP sau khi phân giải DNS không?
- Neo4j server có thể truy cập private network, hệ thống quản trị, metadata service hoặc những dịch vụ vốn không dành cho luồng nhập dữ liệu không?
- Quyền `LOAD`, chính sách firewall/egress và quyền boosted có tương thích với chính sách hạn chế không?
- Có giới hạn timeout, dung lượng phản hồi, định dạng JSON/XML và số lượng request để tránh cạn tài nguyên không?

### Hai hướng kiểm soát theo edition

**Neo4j Enterprise:** dùng `LOAD` privileges với `CIDR` phù hợp để hạn chế các địa chỉ được phép nạp dữ liệu; kiểm tra quyền kế thừa từ role `PUBLIC`. Tài liệu APOC cảnh báo `EXECUTE BOOSTED` có thể vượt qua hạn chế `LOAD`, vì vậy role ứng dụng không nên có quyền này cho các procedure tải tài nguyên ngoài.

**Neo4j Community:** RBAC chi tiết không có như Enterprise; kết hợp cấu hình chặn địa chỉ nội bộ theo tài liệu phiên bản (ví dụ `internal.dbms.cypher_ip_blocklist`), quy tắc egress của host/container và API gateway.

**Trong cả hai edition:** không nhận một URL bất kỳ rồi chuyển thẳng vào procedure. Dùng danh sách nguồn cho phép trong ứng dụng, xử lý redirect/DNS hợp lệ, giới hạn kích thước response và tuyệt đối không đưa credential vào URL hoặc query log.

> Không thử “chứng minh SSRF” bằng cách gọi địa chỉ nội bộ hay dịch vụ không được phép. Để kiểm thử, sử dụng endpoint giả lập trong mạng test do nhóm sở hữu, hoặc xác minh **quyền bị từ chối** bằng cách review cấu hình, không tạo yêu cầu tới tài nguyên nhạy cảm.

## 8. Rủi ro từ Cypher động và thực thi nâng quyền

Một số procedure APOC có thể chạy **đoạn Cypher được truyền dưới dạng chuỗi**. Điều này có ích cho bài toán thật sự cần query động, nhưng có thể làm mất ranh giới giữa **giá trị dữ liệu** và **cấu trúc câu lệnh**.

### 8.1. Ví dụ tham số hóa an toàn

Nếu ứng dụng Java cần tra cứu người dùng bằng email, hãy ưu tiên Cypher có cấu trúc cố định và truyền dữ liệu bằng tham số:

~~~cypher
MATCH (u:User)
WHERE u.email = $email
RETURN u.userId AS userId, u.email AS email;
~~~

Tham số `$email` chỉ là **giá trị dữ liệu**. Không ghép trực tiếp email, mệnh đề `WHERE`, danh sách relationship type hoặc một fragment Cypher do người dùng nhập vào chuỗi thực thi.

### 8.2. Khi nào truy vấn động đặc biệt nguy hiểm?

Nguy cơ tăng nhanh nếu có đồng thời:

1. Input người dùng được ghép thành fragment Cypher tùy ý.
2. Fragment được chuyển tới một procedure có khả năng thực thi câu lệnh đó.
3. Procedure được chạy bằng `BOOSTED`, hoặc bằng role có quyền rộng hơn nghiệp vụ.
4. Không có review, validation, audit hoặc giới hạn truy vấn/timeout.

Khi ấy, việc “API chỉ cho nhập tên bộ lọc” không đủ nếu bộ lọc đó thực tế có thể thay đổi cấu trúc Cypher. Tham số hóa giá trị, chọn template có sẵn và chỉ cho phép các nhánh truy vấn đã được review sẽ an toàn hơn.

Đối với Neo4j 5/Cypher 25, một số chỗ đã có cú pháp dùng tham số cho label/type động theo version; cần kiểm tra khả năng thực tế và **không** mặc định rằng mọi vị trí trong câu lệnh đều nhận tham số. Nếu không thể tham số hóa một thành phần cấu trúc, hãy ánh xạ giá trị đầu vào vào một **tập tên cho phép cố định**.

## 9. Không nhầm “unrestricted” với “boosted”

Xét hai kịch bản:

**Kịch bản A:** Quản trị viên mở `dbms.security.procedures.unrestricted` cho một procedure cần API hạn chế, nhưng user gọi procedure vẫn là role đọc. Thay đổi cấu hình giúp extension dùng API cần thiết; nó **không tự cấp** quyền ghi toàn bộ graph cho user. Tuy nhiên, bản thân API được nới lỏng có thể nhạy cảm, nên vẫn phải review mã extension.

**Kịch bản B:** Một role được cấp `EXECUTE BOOSTED PROCEDURE` cho một procedure chạy truy vấn động, và user được phép quyết định query. Trong khi chạy procedure, quyền thao tác có thể **vượt quyền dữ liệu bình thường của user**. Đây là một rủi ro RBAC khác với việc mở sandbox.

| Khía cạnh | `unrestricted` | `EXECUTE BOOSTED` |
|---|---|---|
| Thuộc loại | Setting của DBMS | Quyền của role (Enterprise) |
| Áp lên | Tên procedure/function trong cấu hình | Quyền khi user gọi procedure/function phù hợp |
| Mục đích kỹ thuật | Cho extension truy cập API bị giới hạn | Thực thi phần bên trong bằng quyền cao hơn |
| Rủi ro khi quá rộng | Extension chạm API nhạy cảm | User vượt ranh giới quyền đọc/ghi/LOAD |
| Cách đánh giá | Kiểm tra `neo4j.conf` và danh sách extension | Kiểm tra `SHOW ROLE ... PRIVILEGES`, `SHOW PROCEDURES` và đường gọi từ ứng dụng |
| Có tự thay thế lớp khác? | Không | Không |

Một checklist chỉ hỏi “có `unrestricted=apoc.*` hay không?” là **chưa đủ**. Cần đánh giá cả ai có thể gọi procedure, với những tham số nào, và procedure có thể truy cập dữ liệu/tệp/mạng gì khi chạy.

## 10. Kiểm kê an toàn bằng Cypher chỉ đọc

Các lệnh dưới đây phục vụ **quan sát**, không gọi procedure nhập/xuất hay tạo tác động bên ngoài. Chỉ chạy với tài khoản đã được phân quyền kiểm kê trên hệ thống do nhóm quản lý.

### 10.1. Liệt kê procedure APOC được nạp

~~~cypher
SHOW PROCEDURES
YIELD name, mode, admin, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, mode, admin, signature
ORDER BY name;
~~~

`mode` mô tả loại procedure như `READ` hoặc `WRITE`, không thay thế kiểm tra side effect ngoài database. Một procedure mode `READ` vẫn có thể được thiết kế để đọc từ URL hoặc file.

Để xem **những procedure mà tài khoản hiện tại có quyền thực thi**:

~~~cypher
SHOW PROCEDURES EXECUTABLE BY CURRENT USER
YIELD name, mode
WHERE name STARTS WITH 'apoc.'
RETURN name, mode
ORDER BY name;
~~~

Kết quả giữa hai lệnh có thể khác nhau vì phân quyền. Nếu tài khoản thiếu quyền hiển thị toàn bộ catalog, kết luận phải ghi rõ phạm vi quan sát thay vì cho rằng procedure không được cài đặt.

### 10.2. Xem role có quyền boosted

Trên **Enterprise Edition**, với tài khoản được quyền xem role:

~~~cypher
SHOW PROCEDURES
YIELD name, rolesExecution, rolesBoostedExecution
WHERE name STARTS WITH 'apoc.'
RETURN name, rolesExecution, rolesBoostedExecution
ORDER BY name;
~~~

Các cột role có thể là `null` khi người xem không có `SHOW ROLE` privilege. `null` ở đây **không đủ chứng minh** procedure không có role được boosted.

Nếu được phép kiểm toán role cụ thể, có thể đối chiếu:

~~~cypher
SHOW ROLE PUBLIC PRIVILEGES AS COMMANDS;
~~~

Và kiểm tra các role ứng dụng (đặt tên theo môi trường thực):

~~~cypher
SHOW ROLE app_reader PRIVILEGES AS COMMANDS;
~~~

`SHOW ROLE ...` chỉ áp dụng khi edition và quyền quản trị tương ứng có sẵn. Không sao chép ví dụ role `app_reader` nếu hệ thống không có role này.

### 10.3. Xem setting Neo4j có hiệu lực

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'dbms.security.procedures.allowlist',
  'dbms.security.procedures.unrestricted',
  'dbms.security.allow_csv_import_from_file_urls',
  'server.directories.import'
]
RETURN name, value
ORDER BY name;
~~~

Lệnh yêu cầu quyền xem setting phù hợp. Một số bản Neo4j/managed service giới hạn thông tin này. Cấu hình `apoc.import.file.enabled` và `apoc.export.file.enabled` nằm ở **apoc.conf** hoặc environment, không nên mặc định rằng `SHOW SETTINGS` của Neo4j sẽ hiển thị chúng. Kiểm tra bằng công cụ quản lý cấu hình/deployment có phân quyền, tránh in secrets trong log.

## 11. Ví dụ bảng đánh giá rủi ro với dữ liệu giả định

Giả sử một nhóm vận hành ba ứng dụng kết nối cùng Neo4j:

- **Cổng tra cứu:** chỉ cần đọc thông tin công khai trong graph.
- **Dịch vụ đồng bộ:** nhập JSON định kỳ từ một dịch vụ nội bộ đã xác thực.
- **Job bảo trì:** cập nhật theo lô dưới tài khoản quản trị có kiểm soát.

Ta dùng thang điểm minh họa: **Khả năng xảy ra (L)** từ 1 đến 3, **Mức ảnh hưởng (I)** từ 1 đến 3, điểm ưu tiên `R = L × I`. Đây chỉ là **thang sàng lọc**, không thay thế phương pháp đánh giá an ninh của tổ chức.

| ID | Tình huống | L | I | R | Đánh giá và hướng xử lý |
|---|---|---:|---:|---:|---|
| R01 | Cổng tra cứu được cấp boosted cho toàn bộ `apoc.*` | 3 | 3 | **9** | Rất cao: thu hồi quyền nâng, tách role đọc |
| R02 | Dịch vụ đồng bộ nhận URL tùy ý từ request ngoài | 3 | 3 | **9** | Rất cao: chỉ nhận nguồn đã định nghĩa và chặn egress ngoài phạm vi |
| R03 | Bật đọc file cho APOC nhưng chưa giới hạn import directory | 2 | 3 | **6** | Cao: tắt nếu không cần hoặc giới hạn đường dẫn + OS |
| R04 | Job bảo trì dùng batch quá lớn, không giới hạn concurrency | 2 | 2 | **4** | Trung bình: điều chỉnh batch, timeout và quota |
| R05 | Ứng dụng dùng duy nhất hàm biến đổi chuỗi cho đầu vào đã kiểm tra | 1 | 1 | **1** | Thấp: chỉ nạp đúng function cần thiết và cập nhật phiên bản |

**Kết luận mẫu:** Ưu tiên xử lý R01/R02 vì có khả năng vượt phân quyền hoặc tạo yêu cầu mạng ngoài ý định. Sau đó xử lý R03 vì rủi ro với file hệ thống. R04 cần đo vận hành; R05 vẫn cần kiểm toán nhưng ít ưu tiên hơn.

### Bốn câu hỏi để chấm một trường hợp cụ thể

1. **Nguồn kích hoạt:** ai gọi procedure? User bên ngoài, service account, cron job hay DBA?
2. **Dữ liệu điều khiển:** caller có kiểm soát URL/path/Cypher fragment/batch size/target label không?
3. **Quyền thực tế:** caller có quyền graph, `EXECUTE`, `BOOSTED`, `LOAD` nào? Extension có `unrestricted` không?
4. **Ảnh hưởng nếu sai:** lộ graph, đọc tệp, truy cập mạng nội bộ, ghi hàng loạt, tắc tài nguyên hay khó khôi phục?

Mỗi câu trả lời nên có **bằng chứng cấu hình, role, đoạn mã gọi và log**. Không nên chấm rủi ro chỉ theo cảm tính hoặc đoán tên procedure.

## 12. Mẫu chính sách tối thiểu cho ba nhóm workload

| Nhóm | Nhu cầu hợp lệ | Thiết kế khuyến nghị |
|---|---|---|
| Cổng tra cứu | `MATCH`, thống kê, format trả về | Role chỉ đọc; Cypher tham số hóa; không cần boosted |
| Dịch vụ đồng bộ | Đọc API định kỳ, `MERGE` vào graph đã cho phép | Service account tách riêng, nguồn mạng cố định, quyền ghi trên graph cần thiết, file access tắt nếu không dùng |
| Công cụ quản trị | Một số công việc thay schema, bảo trì theo lô | Chỉ DBA/job được ủy quyền; thời gian chạy, audit, giới hạn batch, review thay đổi và rollback plan |

Một cấu hình minh họa **để review**:

~~~properties
# conf/neo4j.conf — ví dụ cho hệ thống chỉ dùng một tập nhỏ APOC.
dbms.security.procedures.allowlist=apoc.text.*,apoc.map.*

# Không cấp toàn bộ apoc.* quyền unrestricted.
# Chỉ thêm tên chính xác sau khi review sự cần thiết.
# dbms.security.procedures.unrestricted=
~~~

~~~properties
# conf/apoc.conf — dịch vụ không cần truy cập file cục bộ.
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

Hai khối trên **chưa phải cấu hình production hoàn chỉnh**: cần kết hợp authentication, RBAC, TLS, ACL hệ điều hành, chính sách mạng và cấu hình cụ thể theo version. Đừng áp dụng allowlist ví dụ khi chưa kiểm tra tất cả chức năng đang phụ thuộc APOC.

Đối với Enterprise, một nguyên tắc hardening được tài liệu APOC nêu là từ chối thực thi nâng quyền APOC đối với `PUBLIC`:

~~~cypher
// Chỉ là ví dụ chính sách RBAC; DBA cần review trước khi áp dụng.
DENY EXECUTE BOOSTED PROCEDURE apoc.* ON DBMS TO PUBLIC;
~~~

Điều này giúp tránh kế thừa quyền boosted từ `PUBLIC`; vẫn phải review các grant/deny khác, quyền quản trị và privilege hiệu lực theo version. Không tự cấp `EXECUTE BOOSTED` cho một role ứng dụng để xử lý các lỗi truy cập file/URL.

## 13. Quy trình kiểm toán từng bước không tạo side effect

Một đợt kiểm toán an toàn nên tiến hành như sau:

1. **Xác định phạm vi:** phiên bản Neo4j/APOC, Core/Extended, edition, cluster nodes, database, ứng dụng và người chịu trách nhiệm.
2. **Kiểm kê JAR và plugin:** xác nhận source, checksum hoặc bằng chứng artifact và version tương thích; không tự nạp file JAR lạ.
3. **Trích danh mục procedure:** dùng `SHOW PROCEDURES` và `SHOW FUNCTIONS`, lưu `name`, `mode`, `signature`, khả năng deprecated; đánh dấu nhóm file/network/dynamic query.
4. **Đối chiếu cấu hình:** `allowlist`, `unrestricted`, `apoc.conf`, environment, import directory, OS permissions và egress firewall; kiểm tra cài đặt trên **tất cả server** trong cluster.
5. **Đối chiếu quyền:** dùng `SHOW ROLE ... PRIVILEGES` và `rolesBoostedExecution`, kiểm tra `PUBLIC`, quyền `LOAD`, admin role và service account.
6. **Đối chiếu caller:** tìm ứng dụng/service nào gọi từng procedure, input nào có thể thay đổi; đặc biệt quan tâm đến URL, file path, Cypher fragment và số lượng batch.
7. **Phân loại mức ưu tiên:** ghi bằng chứng, giả thuyết tác động, người chịu trách nhiệm, phương án giảm thiểu và yêu cầu nghiệp vụ phải giữ.
8. **Thử trên môi trường staging:** sử dụng tài khoản chỉ có đúng quyền dự kiến, chạy các lệnh quan sát và **test từ chối quyền** trên dữ liệu giả lập.
9. **Triển khai qua quy trình change:** backup và phương án rollback cấu hình; ghi lại tác động với ứng dụng, restart theo hướng dẫn của phiên bản rồi xác nhận quyền sau deploy.
10. **Theo dõi liên tục:** audit log, query log, thay đổi role/config/JAR, kết nối outbound và tác vụ tiêu hao tài nguyên; rà soát lại sau mỗi lần nâng cấp.

Các lệnh `SHOW` không gọi tới endpoint hay đọc tệp hệ thống. Nếu phải kiểm thử một cơ chế bị chặn, sử dụng **tài khoản và endpoint test do nhóm sở hữu**; không chạy các thao tác ghi/xóa hoặc đọc tài nguyên ngoài phạm vi để “thử quyền”.

## 14. Ba bài thực hành đánh giá tình huống có đáp án

### Bài 1 — Nhận diện quyền nguy hiểm

Một service chỉ hiển thị node `Article` được cấp:

- `EXECUTE PROCEDURE apoc.*`.
- `EXECUTE BOOSTED PROCEDURE apoc.*`.
- Quyền đọc một phần graph.

**Hỏi:** Điều gì cần sửa trước? Có nên tăng `unrestricted` để đảm bảo service chạy ổn định?

**Đáp án:** Thu hồi quyền boosted rộng và thu hẹp phạm vi EXECUTE đến đúng procedure được dùng; xác minh role thực sự cần gì. Không tăng `unrestricted` khi không có yêu cầu về API sandbox đã được review. Service đọc nên dùng Cypher thuần hoặc một function ít quyền, tránh mở thao tác Cypher động và nhập/xuất không cần thiết.

### Bài 2 — Xác định nguồn SSRF

Một API nhận trường `sourceUrl` từ request, rồi chuyển cho procedure tải JSON trên Neo4j server. Neo4j có thể gọi tới mạng nội bộ.

**Hỏi:** Rủi ro nằm ở chặng nào, và ba lớp bảo vệ là gì?

**Đáp án:** Rủi ro xảy ra khi **Neo4j server** gọi URL được quyết định từ input không tin cậy. Ba lớp: (1) API chỉ chấp nhận nguồn đã định nghĩa, kiểm tra redirect/DNS; (2) quyền `LOAD`/CIDR theo edition và không cấp boosted; (3) egress firewall/IP blocklist và network segmentation ở host/container.

### Bài 3 — Chọn cách cấp quyền file

Một job quản trị cần xuất dữ liệu vào một thư mục import riêng trên máy Neo4j mỗi đêm. Job không cần đọc file từ bất cứ thư mục khác.

**Hỏi:** Có nên để `apoc.import.file.use_neo4j_config=false` để tránh lỗi đường dẫn?

**Đáp án:** Không. Chỉ bật khả năng xuất file cần thiết, **giữ true** cho cơ chế tuân thủ đường dẫn, cấu hình import directory chính xác và giới hạn quyền OS của process Neo4j. Mọi điều chỉnh phải được kiểm thử ở staging và kiểm toán thư mục đầu ra. Nếu chỉ cần lấy dữ liệu về client, cân nhắc luồng trả kết quả/stream thay vì cấp quyền ghi filesystem cho server.

### Bài 4 — Giải thích một kết quả kiểm kê

Một admin chạy:

~~~cypher
SHOW PROCEDURES
YIELD name, rolesExecution, rolesBoostedExecution
WHERE name = 'apoc.load.json'
RETURN name, rolesExecution, rolesBoostedExecution;
~~~

`rolesBoostedExecution` trả `null`. Người kiểm toán kết luận “Không role nào được boosted”.

**Đáp án:** Kết luận chưa đủ cơ sở. Các cột role có thể trả `null` khi tài khoản **không có quyền SHOW ROLE**. Kiểm tra quyền quan sát và đối chiếu `SHOW ROLE ... PRIVILEGES AS COMMANDS` bằng tài khoản quản trị thích hợp.

### Bài 5 — Tại sao đếm procedure chưa đủ?

Một deployment có đúng 20 procedure APOC và một deployment khác có 100 procedure. Có thể khẳng định deployment thứ hai rủi ro hơn?

**Đáp án:** Chưa. Mức rủi ro phụ thuộc **loại procedure**, khả năng chạm file/network/Cypher động, quyền caller, boosted/unrestricted, input và khả năng giám sát. Số lượng là chỉ dấu bề mặt tấn công, không phải thang đo an ninh duy nhất.

## 15. Những nhầm lẫn thường gặp khi hardening

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Đã đặt `allowlist=apoc.*` thì an toàn vì có allowlist.” | Wildcard rất rộng; allowlist chỉ xác định **được nạp**, không quyết định hành vi và quyền. |
| “`unrestricted` đồng nghĩa với quyền admin của user.” | Đó là cấu hình sandbox cho extension; quyền role là cơ chế khác. |
| “`EXECUTE PROCEDURE` sẽ tự vượt mọi quyền graph.” | Thực thi thông thường theo quyền user; **BOOSTED** có thể mở rộng quyền. |
| “Đặt `apoc.import.file.enabled=false` là chặn mọi kết nối ra ngoài.” | Setting này liên quan **file cục bộ**; cần kiểm soát riêng URL/network. |
| “Không dùng `file:///` là đủ chống SSRF.” | SSRF thường liên quan HTTP(S) tới đích không mong muốn. |
| “Procedure mode `READ` không thể gây rủi ro hệ thống.” | Mode chỉ mô tả hoạt động graph; khả năng gọi network/đọc file vẫn cần đánh giá. |
| “Đã có firewall nên không cần quyền Neo4j.” | Firewall và quyền dữ liệu bảo vệ các lớp khác nhau; cần cả hai. |
| “APOC Core và Extended được cập nhật/hỗ trợ như nhau.” | Core được hỗ trợ chính thức; Extended do cộng đồng quản lý. |
| “Cấu hình `apoc.*` nằm trong `neo4j.conf` như Neo4j 4.x.” | Từ Neo4j 5, dùng `apoc.conf`/environment theo tài liệu phiên bản. |
| “Thử gọi nội bộ là cách kiểm tra an ninh tốt nhất.” | Nên kiểm tra cấu hình/quyền và dùng endpoint giả lập được ủy quyền. |

## 16. Danh sách kiểm tra trước khi đưa APOC lên production

- [ ] Có danh sách procedure/function thực sự cần, chủ sở hữu nghiệp vụ và lý do sử dụng.
- [ ] Có bằng chứng phiên bản APOC tương thích Neo4j, JAR đến từ nguồn đáng tin cậy.
- [ ] `allowlist` thu hẹp theo nhu cầu; `unrestricted` không dùng wildcard rộng.
- [ ] Role ứng dụng không có `EXECUTE BOOSTED PROCEDURE apoc.*` nếu không có lý do được phê duyệt.
- [ ] Quyền `PUBLIC` và các role kế thừa đã được kiểm tra bằng account đủ quyền.
- [ ] Đọc/ghi file bị tắt khi không cần; nếu bật, chỉ cho phép đúng thư mục và OS account.
- [ ] URL nguồn được kiểm soát ở ứng dụng, có quyền `LOAD`/CIDR hoặc cơ chế hạn chế tương đương.
- [ ] Egress firewall, DNS/redirect checks và giới hạn response phù hợp rủi ro SSRF.
- [ ] Không ghép input không tin cậy thành Cypher fragment rồi chạy với quyền cao.
- [ ] Đã giới hạn batch, concurrency, timeout và tài nguyên với tác vụ nền.
- [ ] Query/audit log và chính sách quản lý secrets phù hợp; không ghi token/credential vào URL hoặc log.
- [ ] Đã xác minh ở staging với role ứng dụng và kiểm tra lại sau nâng cấp.
- [ ] Có phương án rollback cấu hình, tài liệu quyền và người chịu trách nhiệm.

## 17. Tài liệu chính thức để kiểm chứng

- [APOC Core — Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/): nguyên tắc ít quyền, file/network/SSRF, boosted procedure, Cypher động và cơ chế defense in depth.
- [APOC Core — Configuration Options](https://neo4j.com/docs/apoc/current/config/): vị trí `apoc.conf`, ưu tiên environment, các setting nhập/xuất file.
- [APOC Core — Installation](https://neo4j.com/docs/apoc/current/installation/): cài đặt và tính tương thích theo phiên bản Neo4j.
- [Neo4j Operations — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): `dbms.security.procedures.allowlist`, `dbms.security.procedures.unrestricted` và các cấu hình bảo mật của Neo4j.
- [Neo4j Operations — Procedure and user-defined function privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/): phân biệt `EXECUTE` và `EXECUTE BOOSTED`.
- [Neo4j Operations — SHOW PROCEDURES](https://neo4j.com/docs/operations-manual/current/procedures/show-procedures/): `mode`, `rolesExecution`, `rolesBoostedExecution` và kiểm kê khả năng thực thi.
- [Neo4j Operations — LOAD privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/load-privileges/): phân quyền truy cập nguồn dữ liệu theo CIDR trong Enterprise.
- [Neo4j Operations — Security checklist](https://neo4j.com/docs/operations-manual/current/security/checklist/): cấu hình host, network, TLS, file permissions và cập nhật bản vá.
- [APOC — Core và Extended](https://neo4j.com/labs/apoc/): sự khác biệt giữa các nhánh extension.

**Ghi nhớ:** rủi ro APOC không nằm ở việc “có thư viện APOC” mà ở **khả năng của procedure**, **nguồn dữ liệu người dùng điều khiển**, **quyền thực tế khi gọi** và **mức truy cập file/network mà máy chủ được phép**. Đánh giá cả `allowlist`, `unrestricted`, `EXECUTE/BOOSTED`, file access, egress và audit mới tạo được đường biên an toàn cho hệ thống đồ thị.
