# Phân biệt khả năng của Community, Enterprise và gói dịch vụ Neo4j đang sử dụng

*Chương: Khởi tạo môi trường Neo4j.*

## 1. Vì sao cần phân biệt?

Neo4j lưu trữ dữ liệu theo **property graph**: thực thể là *node*, liên kết là *relationship*, cả hai có thể mang *property*. Ta sử dụng Cypher để tìm quan hệ và đường đi; ứng dụng Java có thể kết nối bằng Neo4j Java Driver hoặc Spring Data Neo4j. Những kỹ năng nền tảng này có thể thực hành trên nhiều hình thức triển khai Neo4j.

Tuy nhiên, khi thiết kế hệ thống thực tế, câu hỏi không chỉ là “có chạy được Cypher không?” mà còn là:

- Có cần một hay nhiều cơ sở dữ liệu (*database*) trong cùng hệ quản trị?
- Nếu máy chủ ngừng hoạt động, hệ thống có tự chuyển sang máy khác để tiếp tục phục vụ không?
- Có cần phân quyền chi tiết cho nhiều nhóm người dùng, xác thực tập trung hay không?
- Cần sao lưu khi dịch vụ vẫn chạy, giữ bản sao lưu bao lâu?
- Đội ngũ có tự quản lý máy chủ và nâng cấp Neo4j, hay muốn dùng dịch vụ do Neo4j vận hành?
- Hạn mức node, relationship, bộ nhớ và cam kết mức độ sẵn sàng (*SLA*) của gói hiện tại là gì?

**Mục tiêu bài học:** phân biệt hai edition tự quản lý (Community, Enterprise), bốn cấp AuraDB phổ biến, tự xác định môi trường đang dùng và chọn cấu hình phù hợp với một bài toán.

## 2. Hai trục phân loại không nên nhầm lẫn

Neo4j có hai cách triển khai chính:

1. **Self-managed (tự quản lý):** bạn cài Neo4j trên máy cá nhân, máy chủ, VM, Docker hoặc Kubernetes; bạn chọn **Community Edition** hay **Enterprise Edition**, đồng thời tự chịu trách nhiệm cấu hình, sao lưu và vận hành.
2. **Managed cloud (Neo4j AuraDB):** Neo4j vận hành dịch vụ; bạn tạo instance và chọn một **tier/gói dịch vụ** như **Free**, **Professional**, **Business Critical** hoặc **Virtual Dedicated Cloud (VDC)**.

| Khái niệm | Đang trả lời câu hỏi nào? | Ví dụ |
|---|---|---|
| **Edition** | Phần mềm Neo4j tự cài thuộc bộ tính năng nào? | Community, Enterprise |
| **Deployment** | Ai vận hành máy chủ và hạ tầng? | Tự quản lý bằng Docker; dịch vụ AuraDB |
| **AuraDB tier** | Dịch vụ đám mây được cấp hạn mức, độ sẵn sàng và hỗ trợ đến đâu? | Free, Professional, Business Critical, VDC |
| **Version** | Phiên bản phần mềm đang chạy là gì? | Neo4j 5.x, nhánh phiên bản đặt theo năm như 2026.x |
| **License / subscription** | Quyền sử dụng và hợp đồng dịch vụ áp dụng thế nào? | GPLv3 cho Community; hợp đồng thương mại/đánh giá cho Enterprise; đăng ký AuraDB |

**Điểm mấu chốt:** một instance AuraDB có thể sử dụng khả năng của máy chủ Enterprise, nhưng tên edition trong kết quả truy vấn không cho biết instance thuộc gói AuraDB nào. Ngược lại, tự chạy Enterprise không đồng nghĩa đã có hệ thống HA: cần cấu hình cụm, đủ máy chủ và quy trình vận hành.

## 3. Community Edition và Enterprise Edition: những khác biệt thực tế

Cả hai edition đều hỗ trợ property graph, node, relationship, property, truy vấn Cypher, giao dịch ACID, index cơ bản, constraint phù hợp với edition và giao tiếp qua giao thức Bolt/Driver. Bạn có thể học mô hình dữ liệu và viết phần lớn truy vấn Cypher trên Community trước khi triển khai sản phẩm.

| Khả năng | Community Edition (CE) | Enterprise Edition (EE) |
|---|---|---|
| **Mục đích điển hình** | Học tập, thử nghiệm, ứng dụng một máy chủ hoặc dự án tự quản lý quy mô vừa/nhỏ | Ứng dụng cần bảo mật, sẵn sàng cao, khả năng mở rộng và quản trị nâng cao |
| **Bản quyền** | Mã nguồn mở theo GPLv3; cần tuân thủ nghĩa vụ giấy phép tương ứng | Giấy phép thương mại hoặc giấy phép đánh giá theo điều khoản Neo4j |
| **Mô hình graph, Cypher, ACID, Driver** | Có | Có |
| **Số standard database trong một DBMS** | Một database dữ liệu thông thường, ngoài database hệ thống <code>system</code> | Có thể tạo nhiều standard database, phụ thuộc tài nguyên và thiết kế |
| **Clustering, bầu chọn máy ghi, tự động failover** | Không có clustering tích hợp | Có kiến trúc clustering; phải triển khai đúng mới đạt HA |
| **Backup** | Có thể sao lưu offline bằng dump khi đáp ứng điều kiện dừng database | Hỗ trợ online backup và phục hồi phục vụ nhu cầu vận hành |
| **Bảo mật nâng cao** | Xác thực và cấu hình bảo mật cơ bản; không có RBAC chi tiết của EE | Phân quyền theo role, kiểm soát truy cập chi tiết, tích hợp LDAP/Active Directory |
| **Khả năng nâng cao khác** | Đủ để phát triển phần lớn ví dụ graph cơ bản | Có thêm tính năng như Change Data Capture, parallel runtime và các tùy chọn quản trị/giám sát doanh nghiệp |

### 3.1. Một database khác với một DBMS

Trong cài đặt thông thường, **DBMS** là tiến trình Neo4j quản lý các database. Database <code>system</code> dùng cho metadata và quản trị, không phải nơi ứng dụng lưu graph kinh doanh.

Community cho phép **một standard database** (mặc định thường tên <code>neo4j</code>) bên cạnh <code>system</code>. Enterprise cho phép quản lý nhiều standard database, ví dụ <code>catalog</code>, <code>recommendation</code> và <code>fraud</code>. Không cần Enterprise chỉ để có nhiều loại node hay relationship trong **cùng một graph**: các nhãn như <code>User</code>, <code>Product</code>, <code>Order</code> vẫn có thể sống chung trong một Community database.

Một transaction không tự động trải qua nhiều database. Khi tách database trong Enterprise, cần thiết kế rõ ranh giới truy vấn, giao dịch và quản trị.

### 3.2. Clustering và backup là hai yêu cầu khác nhau

**Clustering** giúp tăng tính sẵn sàng và khả năng phục vụ, nhưng cần nhiều bản sao dữ liệu, cơ chế điều phối, theo dõi và thử nghiệm chuyển đổi khi lỗi. Enterprise cung cấp tính năng này; không có nghĩa cứ cài Enterprise trên một máy là được bảo vệ trước hỏng máy.

**Backup** giúp phục hồi khi xóa nhầm, lỗi dữ liệu hoặc sự cố khác. Một cluster sao chép cả dữ liệu tốt lẫn thao tác xóa sai, vì vậy **cluster không thay thế backup**. Community hỗ trợ đường sao lưu offline theo quy trình phù hợp; Enterprise có online backup. Trong AuraDB, dịch vụ quản lý snapshot/backup theo từng tier với tần suất và thời gian lưu giữ khác nhau.

### 3.3. Bảo mật và hiệu năng

Community có cơ chế xác thực và có thể cấu hình kết nối bảo mật; không nên hiểu “Community không có bảo mật”. Enterprise bổ sung các khả năng như **role-based access control (RBAC)**, quản lý quyền tinh vi hơn và tích hợp hệ thống nhận dạng doanh nghiệp.

Cả hai edition đều cần index đúng chỗ, kế hoạch truy vấn tốt và giới hạn số lượng dữ liệu truy xuất. Enterprise mở thêm các lựa chọn tối ưu và xử lý, nhưng không tự khắc phục truy vấn Cypher viết kém hoặc mô hình graph thiếu hợp lý.

> **Lưu ý bản quyền:** việc tải image Enterprise và chấp nhận điều khoản trong Docker không tự tạo quyền sử dụng thương mại. Cần kiểm tra giấy phép/đăng ký hợp lệ theo mục đích triển khai.

## 4. Nếu dùng Neo4j AuraDB: so sánh bốn gói dịch vụ

AuraDB là dịch vụ graph database do Neo4j quản lý. Thay vì chọn binary Community/Enterprise, bạn chọn **tier** phù hợp với dữ liệu, yêu cầu vận hành, độ sẵn sàng và ngân sách. Bảng sau tóm tắt theo tài liệu AuraDB công bố tại thời điểm biên soạn (11/2026); hạn mức và điều khoản có thể thay đổi nên phải kiểm tra trang chính thức trước khi triển khai.

| Tier AuraDB | Phù hợp | Khác biệt vận hành quan trọng |
|---|---|---|
| **Free** | Học Cypher, demo, prototype nhỏ | Không có SLA uptime hay HA; hạn mức Free hiện được công bố tối đa **200.000 node**, **400.000 relationship**, **1 GB storage** |
| **Professional** | Ứng dụng cần mở rộng tài nguyên và có cơ chế quản lý backup tốt hơn Free | Trả phí theo tài nguyên; không có HA/SLA uptime; snapshot định kỳ hằng ngày với thời gian lưu giữ công bố là **7 ngày** |
| **Business Critical** | Hệ thống cần độ sẵn sàng cao, tính liên tục của dịch vụ | HA theo kiến trúc nhiều node, SLA uptime **99,95%**, snapshot theo giờ; thời gian lưu giữ công bố **30 ngày** |
| **Virtual Dedicated Cloud (VDC)** | Tổ chức cần môi trường tách biệt, yêu cầu hạ tầng và bảo mật đặc thù | Môi trường dedicated riêng, HA và SLA **99,95%**; chính sách snapshot, thời gian lưu trữ và cấu hình phụ thuộc phiên bản/hợp đồng |

Các tier có thể giới hạn **số database trong một instance** khác nhau. Theo bảng giới hạn AuraDB hiện tại, Free và Professional có **1 database/instance**, trong khi Business Critical và VDC cho phép nhiều hơn theo quota của tier. Vì vậy, **không được suy rằng “Aura dùng engine Enterprise nên mọi tier đều hỗ trợ nhiều database”**.

Khi so sánh, đừng chỉ nhìn dung lượng graph. Hãy đối chiếu đồng thời:

- Hạn mức **node/relationship**, storage, RAM và khả năng tăng cấu hình.
- **HA, SLA**, region, yêu cầu kết nối riêng hoặc cách ly mạng.
- **Lịch snapshot, thời gian lưu bản sao, phương án export và khôi phục**.
- Tính năng quản trị, quyền truy cập, khả năng tích hợp và chi phí tăng trưởng.

**AuraDB khác AuraDS:** AuraDB phục vụ lưu trữ và truy vấn graph vận hành; AuraDS hướng tới tác vụ data science. Tên sản phẩm, tier và các quyền sử dụng cần kiểm tra riêng.

## 5. Xác định chính xác môi trường hiện tại

Không thể xác định edition hoặc tier của một hệ thống chỉ từ tên dự án, công cụ kết nối hoặc ví dụ trong tài liệu. Vì vậy, quy trình dưới đây giúp **tự xác minh môi trường đang sử dụng**, thay vì suy đoán.

### Bước 1 — Xác định bạn kết nối vào đâu

- Nếu bạn tự chạy máy chủ Neo4j bằng bộ cài, Neo4j Desktop, Docker hoặc Kubernetes, hãy xác định máy chủ **self-managed** và kiểm tra edition.
- Nếu bạn tạo instance trong **Neo4j Aura Console** và dùng URI do Aura cấp (thường là <code>neo4j+s://...</code>), hãy kiểm tra **tên instance và tier trên Aura Console**. URI một mình không đủ để suy ra tier.
- Nếu kết nối qua hạ tầng của nhóm khác, hỏi người quản trị về phương thức triển khai và quyền vào console/quản trị; tài khoản chỉ có quyền đọc dữ liệu có thể không xem được mọi thông tin.

### Bước 2 — Truy vấn phiên bản và edition

Đăng nhập Neo4j Browser hoặc cypher-shell vào DBMS được giao, chạy câu lệnh **chỉ đọc metadata**:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions[0] AS version, edition;
~~~

Kết quả minh họa (giá trị edition/version cần đọc từ hệ thống thực):

| name | version | edition |
|---|---|---|
| Neo4j Kernel | 2026.x.y | community hoặc enterprise |

Nếu <code>edition = community</code>, đó là dấu hiệu máy chủ chạy Community. Nếu <code>edition = enterprise</code>, đó là edition của engine; **vẫn chưa cho biết tier AuraDB**. Lệnh có thể bị giới hạn bởi quyền hoặc khác biệt phiên bản; khi lỗi, kiểm tra tài liệu của phiên bản đang dùng và nhờ quản trị viên xác nhận, không kết luận edition chỉ từ lỗi quyền truy cập.

### Bước 3A — Nếu tự quản lý: kiểm tra bộ cài/triển khai

Với Docker, có thể đối chiếu image thực tế:

~~~bash
docker ps --format "table {{.Names}}\t{{.Image}}"
~~~

Theo quy ước image chính thức, tag Neo4j Community thường không có hậu tố <code>-enterprise</code>; tag Enterprise thường có hậu tố này (ví dụ <code>neo4j:2026.10.2-enterprise</code>). Kết hợp **tag image**, kết quả <code>dbms.components()</code> và thông tin giấy phép để xác minh. Không lấy mỗi tên container làm bằng chứng edition.

Với bản cài trực tiếp, đối chiếu gói cài đặt và cấu hình triển khai. Nếu dùng Neo4j Desktop, bản thân ứng dụng Desktop không phải edition của DBMS: cần kiểm tra DBMS cụ thể đang mở.

### Bước 3B — Nếu dùng AuraDB: đọc tier trong Console

1. Mở [Neo4j Aura Console](https://console.neo4j.io/), chọn đúng **organization/project**.
2. Tìm **instance** mà URI ứng dụng đang sử dụng, đối chiếu instance ID/tên và vùng triển khai.
3. Đọc **tier / plan** trong thông tin instance (Free, Professional, Business Critical hoặc Virtual Dedicated Cloud), xem cấu hình tài nguyên và mục backup.
4. Nếu bạn có quyền quản lý thanh toán, đối chiếu subscription/hợp đồng. Chỉ người có quyền phù hợp mới thấy một số mục billing hoặc quản trị.

**Không dùng** <code>CALL dbms.components()</code> để suy ra gói AuraDB. Kết quả có thể chỉ nêu edition engine. Ví dụ, cùng hiển thị <code>enterprise</code> không chứng minh đang trả phí cho Business Critical hay có SLA 99,95%.

### Bước 4 — Ghi lại “hồ sơ môi trường”

Điền bảng dựa trên thông tin đã kiểm chứng của **chính instance đang kết nối**:

| Thuộc tính cần ghi | Giá trị cần xác minh |
|---|---|
| Nơi triển khai | Self-managed / AuraDB |
| Edition của DBMS | Community / Enterprise / chưa đủ quyền xác nhận |
| AuraDB tier (nếu có) | Free / Professional / Business Critical / VDC |
| Version | Giá trị từ <code>dbms.components()</code> |
| Database ứng dụng | Tên database mà Driver/Cypher đang chọn |
| Giới hạn/tính năng quan trọng | Số database, quota, HA, backup, quyền truy cập |
| Nguồn bằng chứng | Truy vấn DBMS, thông tin instance, cấu hình triển khai, hợp đồng |

Hồ sơ này quan trọng với ứng dụng Java: cùng một đoạn code dùng Neo4j Java Driver hoặc Spring Data Neo4j có thể kết nối nhiều môi trường, nhưng **quyền tạo database, tính năng sao lưu, quota, khả năng clustering và quyền quản trị không giống nhau**.

## 6. Thực hành an toàn: quan sát những tính năng chung

Trước khi thử lệnh quản trị Enterprise, hãy chạy một ví dụ property graph nhỏ trên **database được phép ghi**. Đoạn mã sau dùng <code>MERGE</code> để chạy lặp không tạo thêm cặp node cùng khóa trong tình huống một người dùng chạy tuần tự.

~~~cypher
MERGE (u:User {userId: 'u-001'})
SET u.name = 'An'
MERGE (p:Product {sku: 'neo4j-book'})
SET p.name = 'Sách về Cypher'
MERGE (u)-[:VIEWED]->(p);
~~~

~~~cypher
MATCH (u:User {userId: 'u-001'})-[:VIEWED]->(p:Product)
RETURN u.name AS userName, p.name AS productName;
~~~

Với database mới tạo cho mục đích thực hành, có thể cân nhắc constraint unique cho khóa nhận diện:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.userId IS UNIQUE;
~~~

Constraint unique, index và truy vấn graph cơ bản **không phải lý do mặc định buộc phải mua Enterprise**. Trong hệ thống đã có dữ liệu, kiểm tra trước các giá trị trùng và quyền tạo constraint; lệnh có thể thất bại nếu dữ liệu vi phạm hoặc người dùng không có quyền. Ví dụ <code>MERGE</code> ở trên minh họa cú pháp, không thay thế chiến lược xử lý đồng thời trong production.

Bạn cũng có thể đọc metadata index và constraint tại database hiện tại (chạy riêng từng lệnh):

~~~cypher
SHOW INDEXES;
SHOW CONSTRAINTS;
~~~

Hai lệnh này giúp xem cấu trúc truy vấn nhưng **không xác định tier AuraDB**. Các lệnh như <code>CREATE DATABASE</code>, <code>SHOW ROLES</code>, thao tác server/cluster hoặc restore phụ thuộc edition, tier và quyền của tài khoản. Không thử tạo/xóa database hay chỉnh cấu hình production chỉ để “test” xem có hỗ trợ hay không.

## 7. Chọn phương án phù hợp theo yêu cầu

| Bài toán | Phương án nên đánh giá trước | Lý do |
|---|---|---|
| Học node, relationship, Cypher, index, constraint; chạy local | **Community** hoặc **AuraDB Free** | Đủ năng lực graph nền tảng; Free có quota dữ liệu riêng |
| Ứng dụng nhỏ do nhóm tự vận hành; chấp nhận cửa sổ bảo trì và backup offline | **Community** | Giảm chi phí license, đổi lại nhóm tự chịu trách nhiệm phục hồi và độ sẵn sàng |
| Tự vận hành graph cho nhiều nhóm, nhiều database, RBAC, cluster, backup online | **Enterprise** | Có các tính năng quản trị và vận hành chuyên sâu; cần license, hạ tầng và cấu hình |
| Muốn dịch vụ quản lý, ứng dụng tăng trưởng nhưng chưa yêu cầu HA theo SLA | **AuraDB Professional** | Có thể tăng tài nguyên và dùng backup định kỳ theo gói |
| Dịch vụ đặt hàng/đề xuất hoặc phát hiện gian lận yêu cầu HA và SLA rõ ràng | **AuraDB Business Critical** | Hỗ trợ HA và SLA đã công bố; vẫn cần kiến trúc ứng dụng phù hợp |
| Cần môi trường cloud dedicated và yêu cầu cách ly/tùy chỉnh hạ tầng nghiêm ngặt | **AuraDB VDC** | Dedicated environment và các tùy chọn doanh nghiệp theo cấu hình/hợp đồng |

### Ví dụ đưa ra quyết định

Một nhóm xây graph **người dùng — đã xem — sản phẩm — thuộc danh mục** để thử tính năng gợi ý. Ở giai đoạn học mô hình và Cypher, Community hoặc AuraDB Free thường đủ nếu đồ thị nhỏ. Khi triển khai ứng dụng thật, nhóm phải đo số node/relationship, thời gian truy vấn và nhu cầu backup trước khi chọn cấp tiếp theo.

Nếu hệ thống giao dịch chạy 24/7, yêu cầu khôi phục khi mất máy chủ và phân quyền theo vai trò, chỉ chạy một container Enterprise là chưa đủ. Cần kiến trúc cluster hoặc dịch vụ có HA, có phương án backup, khôi phục đã diễn tập và điều khoản SLA phù hợp.

### Những ngộ nhận thường gặp

- **“Community không hỗ trợ Cypher/index.”** Sai. Đây là nền tảng chung của Neo4j; khác biệt lớn tập trung ở khả năng doanh nghiệp và vận hành.
- **“Community bị giới hạn 200.000 node.”** Sai. Đây là quota được công bố cho **AuraDB Free**, không phải hạn mức chung của Community self-managed.
- **“Cứ có Enterprise là tự động có HA.”** Sai. Clustering phải được triển khai, vận hành và kiểm chứng.
- **“Có cluster là không cần backup.”** Sai. Hỏng logic dữ liệu hoặc xóa nhầm vẫn cần phục hồi từ bản sao phù hợp.
- **“AuraDB Professional chắc chắn có HA/SLA như Business Critical.”** Sai theo bảng giới hạn AuraDB hiện hành.
- **“Truy vấn trả <code>enterprise</code> thì tôi đang dùng AuraDB Business Critical.”** Sai. Edition và cloud tier là hai thông tin khác nhau.
- **“Không chạy được <code>SHOW ROLES</code> tức là Community.”** Không đủ cơ sở: có thể do quyền hoặc hạn chế của môi trường được quản lý.

## 8. Tự kiểm tra sau bài học

Hãy chọn một instance Neo4j bạn thực sự có quyền truy cập và hoàn thành các bước:

1. Chạy <code>CALL dbms.components()</code>, ghi version và edition trả về.
2. Xác định instance tự quản lý hay AuraDB; nếu là AuraDB, mở Console xác minh **tier**.
3. Ghi lại giới hạn về database, dung lượng, HA, backup và quyền truy cập từ tài liệu/console áp dụng cho instance đó.
4. Chạy truy vấn <code>MATCH</code> trên graph thực hành; xem <code>SHOW INDEXES</code> và <code>SHOW CONSTRAINTS</code> nếu được cấp quyền.
5. Với một kịch bản có 1 triệu node, cần backup hằng ngày và không bắt buộc HA, hãy giải thích vì sao không thể mặc định chọn AuraDB Free; nêu ít nhất hai phương án thay thế và những chi phí vận hành cần cân nhắc.
6. Với kịch bản yêu cầu không ngừng dịch vụ khi mất một node, nêu rõ edition/tier hỗ trợ **khả năng** HA, cách triển khai/điều khoản bảo đảm, và vì sao vẫn phải có backup.

**Tiêu chí hoàn thành:** bạn có thể trình bày riêng ba thông tin “deployment — edition — tier”, đưa ra bằng chứng đang dùng cấu hình nào, và nối từng yêu cầu (số database, phân quyền, HA, backup, quota) với tính năng thực tế.

## Tài liệu tham khảo

Các trang Neo4j chính thức là nguồn để kiểm tra tính năng và hạn mức khi phiên bản hoặc gói dịch vụ thay đổi:

- [Neo4j Operations Manual — Introduction / editions](https://neo4j.com/docs/operations-manual/current/introduction/): phân biệt Community, Enterprise và bảng khả năng.
- [Neo4j Operations Manual — Database administration](https://neo4j.com/docs/operations-manual/current/database-administration/): giới hạn số database theo edition.
- [Neo4j Operations Manual — Built-in procedures](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/): thủ tục <code>dbms.components()</code>.
- [Neo4j Operations Manual — Docker introduction](https://neo4j.com/docs/operations-manual/current/docker/introduction/): cách đặt tag image theo edition và yêu cầu giấy phép.
- [Neo4j Aura — Quotas and limits](https://neo4j.com/docs/aura/quotas-and-limits/): hạn mức node, relationship, database, HA, SLA và backup theo tier.
- [Neo4j Aura — Backup, restore and export](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/): lịch snapshot, restore và các điều kiện theo gói.
- [Neo4j Pricing](https://neo4j.com/pricing/): đối chiếu các gói, tính năng và điều kiện thương mại cập nhật.

*Thông tin edition và tier được tổng hợp theo tài liệu Neo4j tại thời điểm soạn bài, tháng 11/2026. Hạn mức, tên gói, khả năng và chính sách license có thể thay đổi; tài liệu và hợp đồng áp dụng cho môi trường thực tế luôn là căn cứ cuối cùng.*

