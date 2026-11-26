# Cài đặt, cấu hình danh sách cho phép và giới hạn quyền thủ tục

## 1. APOC là gì và vì sao phải kiểm soát quyền?

**APOC** (*Awesome Procedures On Cypher*) là thư viện mở rộng cho Neo4j, cung cấp các **procedure** và **user-defined function** dùng trực tiếp từ Cypher. Chúng hỗ trợ những tác vụ như xử lý chuỗi, biến đổi dữ liệu, đọc nguồn bên ngoài và một số công việc vận hành đồ thị. APOC bổ sung cho khả năng có sẵn của **Cypher**, chứ không thay thế mô hình **property graph** gồm node, relationship, property, index và constraint.

Trong module **DATABASE_ENGINE_GRAPH_NEO4J**, hệ thống có thể gọi APOC từ Neo4j Browser, **Java Driver** hoặc **Spring Data Neo4j**. Chính vì có thể được gọi từ nhiều lớp ứng dụng, việc cài thư viện phải đi kèm chính sách **chỉ nạp chức năng cần thiết, chỉ cấp quyền thực thi cần thiết và chỉ bật quyền truy cập tài nguyên bên ngoài khi đã có nhu cầu**.

Bài học thuộc chương **APOC và phần mở rộng**, tập trung vào ba câu hỏi:

1. Cài APOC Core/Extended đúng với môi trường và **phiên bản Neo4j** như thế nào?
2. Cấu hình **dbms.security.procedures.allowlist** và **dbms.security.procedures.unrestricted** khác nhau ra sao?
3. Giới hạn **quyền EXECUTE PROCEDURE/FUNCTION theo role**, đồng thời kiểm soát tác động lên file, mạng và dữ liệu, như thế nào?

**Nguyên tắc:** một procedure có mặt trong JAR không đồng nghĩa đã được nạp; được nạp không đồng nghĩa user được phép thực thi; được phép thực thi cũng không đồng nghĩa được phép đọc/ghi mọi dữ liệu.

## 2. Phân biệt APOC Core, APOC Extended và Cypher thuần

Từ Neo4j 5, APOC được tách rõ thành hai phần:

| Lựa chọn | Bản chất | Khi nào dùng | Vận hành |
|---|---|---|---|
| **Cypher tích hợp** | Ngôn ngữ truy vấn của Neo4j, không cần JAR APOC | Câu truy vấn có chức năng Cypher tương đương | Ít phụ thuộc hơn; nên ưu tiên khi đáp ứng yêu cầu |
| **APOC Core** | Phần thư viện APOC được Neo4j hỗ trợ chính thức từ Neo4j 5 | Biến đổi dữ liệu, hàm tiện ích, một số thủ tục đồ thị | Có gói phù hợp với bản Neo4j; thường có trong bộ cài nhưng cần kích hoạt |
| **APOC Extended** | Phần bổ sung do cộng đồng duy trì, có các tính năng tích hợp/phụ thuộc ngoài | Chỉ khi Core/Cypher không đáp ứng | Tải JAR riêng, kiểm tra phiên bản/phụ thuộc và đánh giá rủi ro kỹ hơn |

Không nên suy ra rằng **Core + Extended** luôn là một JAR duy nhất, hoặc mọi procedure xuất hiện trong tài liệu APOC cũ vẫn còn ở Core hiện tại. Một số chức năng APOC đã có tương đương Cypher và có thể bị **deprecated** hoặc loại bỏ theo các bản phát hành. Khi nâng cấp, kiểm tra danh mục procedure, migration guide và các thông báo thay đổi của đúng phiên bản.

### 2.1. Khớp phiên bản Neo4j và APOC

APOC sử dụng API bên trong Neo4j, vì thế **phiên bản không tương thích có thể khiến plugin không được nạp** hoặc gây lỗi khi khởi động:

- Với các nhánh **Neo4j 5.x** truyền thống, đối chiếu **major.minor** của Neo4j và gói APOC theo ma trận tương thích được công bố.
- Với nhánh phiên bản dạng **năm.tháng** của Neo4j hiện đại (ví dụ 2025.06 hoặc 2026.10), chọn APOC có cùng **năm và tháng**; số patch có thể khác nếu tài liệu tương thích cho phép.
- **Core** và **Extended** phải được chọn đúng bản tương ứng; không cài hai JAR khác phiên bản chỉ vì tên file đều chứa APOC.
- Khi nâng cấp Neo4j, nâng cấp/đối chiếu lại APOC **trước** khi đưa instance vào phục vụ.

Không sử dụng tên bản JAR trong ví dụ tài liệu như phiên bản chuẩn cho mọi hệ thống. Kiểm tra phiên bản server thực tế, tài liệu tương thích và gói được phát hành trước khi triển khai.

## 3. Cài APOC theo môi trường

### 3.1. Máy chủ Neo4j tự quản lý

Với bản Neo4j có kèm **APOC Core** trong thư mục **labs**, quy trình thông thường:

1. Xác định phiên bản Neo4j server và chọn đúng phiên bản APOC.
2. Sao chép JAR APOC Core từ **$NEO4J_HOME/labs** sang **$NEO4J_HOME/plugins**; hoặc tải bản JAR khớp phiên bản từ nguồn phát hành chính thức nếu môi trường yêu cầu.
3. Nếu cần **APOC Extended**, tải JAR Extended tương thích và các thư viện phụ thuộc được nhà phát hành yêu cầu vào thư mục **plugins**; không coi Extended là bản thay thế Core.
4. Cấu hình danh sách cho phép, các quyền thực thi và tùy chọn APOC theo mục 4–6 bên dưới.
5. Khởi động lại Neo4j bằng cơ chế quản lý dịch vụ của môi trường, rồi kiểm tra danh sách procedure/function.

Trong **cluster**, bảo đảm những server có thể nhận truy vấn cần cùng tập JAR và cấu hình phù hợp. Một máy chủ có plugin nhưng máy chủ khác thiếu plugin có thể tạo lỗi không ổn định khi routing chuyển kết nối.

**Lưu ý:** chỉ người quản trị được phép chỉnh sửa thư mục plugin/cấu hình hoặc restart dịch vụ. Không tải JAR từ nguồn không rõ xuất xứ hoặc để tài khoản ứng dụng ghi được vào thư mục **plugins**.

### 3.2. Neo4j Desktop

Ở **Neo4j Desktop**, mở DBMS đang quản lý, chọn mục **Plugins**, chọn cài **APOC** và khởi động lại khi giao diện yêu cầu. Mục APOC trong giao diện này thường cài **APOC Core**. Muốn dùng **Extended**, cần làm theo hướng dẫn cài JAR thủ công tương ứng bản Desktop/DBMS, sau đó kiểm tra khả năng nạp.

Desktop thuận tiện cho học tập nhưng **mức quyền mặc định của môi trường phát triển không phải cấu hình bảo mật sản xuất**. Dù gọi từ Browser hay một ứng dụng Java, procedure vẫn chạy trên Neo4j server với những quyền server cho phép.

### 3.3. Neo4j Docker

Hình ảnh Docker Neo4j cung cấp biến **NEO4J_PLUGINS** nhận một danh sách JSON, ví dụ **["apoc"]** cho Core. Ví dụ Docker Compose tối giản cho **môi trường phát triển**:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_security_procedures_allowlist: "apoc.version,apoc.text.clean,apoc.help"
    volumes:
      - neo4j_data:/data
volumes:
  neo4j_data:
~~~

**Trước khi chạy**, đặt biến môi trường **NEO4J_PASSWORD** thành mật khẩu thử nghiệm đủ mạnh; không commit mật khẩu vào Git. Version **2026.10.2** là phiên bản minh họa; thay bằng tag được dự án sử dụng và đối chiếu tương thích.

Cơ chế **NEO4J_PLUGINS** tự tải/cấu hình plugin khi container khởi động được tài liệu Neo4j định hướng cho **development**. Với production, nên cố định phiên bản plugin, kiểm tra nguồn JAR và cung cấp thư mục **/plugins** qua image hoặc volume được quản lý, thay vì phụ thuộc việc tải khi mỗi container start.

Nếu dùng **Extended**, Docker hỗ trợ giá trị **apoc-extended** tương ứng, nhưng cần kiểm tra bản phát hành và các dependency. Đừng tự động bật cả hai phần chỉ vì chúng có sẵn.

### 3.4. Neo4j Aura

**Aura** cung cấp sẵn **một tập con APOC Core** do dịch vụ quản lý. Người dùng không tự chép JAR vào **plugins**, không sửa **neo4j.conf** và không cài APOC Extended tùy ý như trên server tự quản lý.

Trước khi chọn một procedure cho Aura, tra danh sách **APOC support** chính thức của Aura và kiểm tra bằng **SHOW PROCEDURES/SHOW FUNCTIONS** trên instance thực tế. Không giả định mọi hàm của APOC Core đều khả dụng trên mọi sản phẩm/tier Aura.

## 4. Ba lớp kiểm soát: nạp, mở hạn chế và cấp quyền gọi

Các lớp kiểm soát có thể hình dung như sau:

~~~mermaid
flowchart TD
  A["JAR có trên server và đúng phiên bản"] --> B["allowlist: được nạp vào DBMS?"]
  B --> C["unrestricted: có được dùng API nội bộ bị hạn chế?"]
  C --> D["Quyền EXECUTE PROCEDURE/FUNCTION theo role"]
  D --> E["Quyền truy cập graph và nguồn ngoài"]
  E --> F["Truy vấn Cypher thực thi trong phạm vi quyền được cấp"]
~~~

| Lớp | Điều khiển | Ý nghĩa | Thay thế cho lớp khác? |
|---|---|---|---|
| **Cài plugin** | JAR và dependencies trong plugins | Có mã triển khai để Neo4j nạp | **Không** |
| **Danh sách nạp** | **dbms.security.procedures.allowlist** | Chỉ nạp tên thủ tục/hàm được khớp | **Không** cấp quyền cho role |
| **Bỏ hạn chế nội bộ** | **dbms.security.procedures.unrestricted** | Cho một số thủ tục/hàm dùng API nội bộ với quyền đặc biệt | **Không** tự làm các tên ngoài allowlist xuất hiện |
| **Phân quyền thực thi** | **EXECUTE PROCEDURE / EXECUTE FUNCTION** | Ai có quyền gọi thủ tục/hàm đã nạp | **Không** tự cho quyền đọc/ghi dữ liệu |
| **Phân quyền dữ liệu/tài nguyên** | Các quyền Cypher, file, mạng, cấu hình APOC | Thao tác nào được phép khi procedure chạy | Phải xem riêng, đặc biệt nếu có boosted execution |

**Quan trọng:** cả **allowlist** lẫn **unrestricted** đều là cấu hình cấp DBMS, áp dụng ở lúc server khởi động/nạp extension. Chúng **không phải** danh sách quyền per-user. Việc giới hạn user nào được gọi từng procedure thuộc **role privilege**, được hỗ trợ chi tiết trong **Neo4j Enterprise Edition**.

## 5. dbms.security.procedures.allowlist: chỉ nạp điều cần dùng

### 5.1. Cấu hình trong neo4j.conf

Tệp **$NEO4J_HOME/conf/neo4j.conf** là nơi khai báo:

~~~properties
# Chỉ nạp 2 function và 1 procedure APOC cần cho bài thực hành.
dbms.security.procedures.allowlist=apoc.version,apoc.text.clean,apoc.help
~~~

Danh sách phân tách bằng dấu phẩy; có thể dùng tên đầy đủ hoặc ký tự đại diện **\***. Ví dụ nếu ứng dụng thực sự cần nhiều hàm thuộc nhóm xử lý chuỗi:

~~~properties
dbms.security.procedures.allowlist=apoc.version,apoc.text.*,apoc.help
~~~

Mẫu **apoc.text.\*** nạp **cả nhóm**, nên phạm vi rộng hơn việc liệt kê từng tên. Nếu chỉ dùng **apoc.text.clean**, chọn tên cụ thể sẽ dễ kiểm soát hơn.

Quy tắc quan trọng:

- Mặc định **allowlist = \***: các procedure/function được phát hiện từ plugin có thể được nạp nếu không bị cơ chế hạn chế khác chặn.
- Cấu hình **allowlist rỗng** khiến các extension không được nạp; không hiểu nó là “giữ nguyên mặc định”.
- Cấu hình allowlist ảnh hưởng đến **mọi thư viện extension**, không chỉ APOC. Nếu hệ thống còn dùng Graph Data Science hoặc plugin khác, phải đưa vào danh sách các chức năng được chấp thuận của chúng.
- Nếu một tên không được allowlist, **GRANT EXECUTE** cho tên đó cũng không thể khiến nó xuất hiện: phải sửa cấu hình nạp trước.
- Không cho phép cả **apoc.\*** hoặc **\*** một cách tùy tiện trên production chỉ để tránh lỗi “unknown procedure”.

**Phân biệt dấu hoa thị:** ở đây **\*** là wildcard khớp tên function/procedure trong file cấu hình, không phải cú pháp đường đi biến độ dài của Cypher.

### 5.2. Xác minh các tên đã được nạp

Sau khi restart Neo4j và đăng nhập bằng tài khoản có quyền xem danh sách thủ tục/hàm:

~~~cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

**apoc.help** là **procedure**, còn **apoc.version** và **apoc.text.clean** là **function**. Vì vậy, chỉ chạy **SHOW PROCEDURES** sẽ không phản ánh đầy đủ các chức năng APOC đã được nạp.

Kiểm thử đơn giản, không sửa graph:

~~~cypher
RETURN apoc.version() AS apocVersion,
       apoc.text.clean('Hello World!') AS cleanedText;
~~~

Kỳ vọng **cleanedText = 'helloworld'**. Nếu function không được nhận dạng, kiểm tra việc nạp JAR, phiên bản, allowlist, restart và lỗi khởi động trước khi mở rộng quyền.

## 6. dbms.security.procedures.unrestricted: quyền đặc biệt cho API nội bộ

Một số extension dùng API nội bộ Neo4j không được phép chạy với giới hạn mặc định. Cấu hình **dbms.security.procedures.unrestricted** cho phép chỉ định tên được **bỏ hạn chế** này:

~~~properties
# Ví dụ từ tài liệu Neo4j: chỉ khi một workload được duyệt thực sự cần.
dbms.security.procedures.unrestricted=apoc.cypher.runFirstColumn
~~~

Đây là **ví dụ về cú pháp**, không phải cấu hình khuyến nghị chung cho hệ thống bài tập. Mặc định **unrestricted** là danh sách rỗng, và nên **giữ rỗng** khi các chức năng đang sử dụng không yêu cầu nó.

Các nguyên tắc:

1. **Không mặc định đặt unrestricted=apoc.\***. Điều này cho phép một phạm vi rất rộng các procedure/function sử dụng API nội bộ, làm tăng rủi ro so với cấp tối thiểu.
2. Muốn một procedure có hiệu lực, nó phải **được nạp**, được **bỏ hạn chế nếu thực sự cần**, và người gọi phải có **quyền EXECUTE** cùng các quyền dữ liệu thích hợp.
3. **unrestricted không phải thuốc chữa mọi lỗi quyền**. Nếu lỗi là user thiếu quyền EXECUTE hay graph WRITE, việc bật unrestricted có thể vừa không giải quyết đúng nguyên nhân, vừa làm tăng rủi ro.
4. Trước khi dùng một procedure truy cập nội bộ, phải đọc **trang tài liệu riêng của procedure**, xác định nhu cầu bảo mật và kiểm tra tác động lên các role.

Trong các ví dụ cấu hình tại mục 5, **apoc.version**, **apoc.text.clean** và **apoc.help** không cần cấu hình **unrestricted** để dạy cách nạp và gọi hàm đơn giản. Giữ cấu hình unrestricted không khai báo là lựa chọn phù hợp cho bài thực hành này.

### 6.1. Nếu cả allowlist và unrestricted cùng xuất hiện

Giả sử cấu hình:

~~~properties
dbms.security.procedures.allowlist=apoc.text.clean,apoc.version,apoc.help
dbms.security.procedures.unrestricted=apoc.cypher.runFirstColumn
~~~

**apoc.cypher.runFirstColumn** vẫn **không** được nạp vì không có trong allowlist. Để nó khả dụng cần cả điều kiện nạp lẫn bỏ hạn chế, và sau đó tiếp tục xét quyền thực thi của user. Không nhầm hai cấu hình thành toán tử “hoặc”.

## 7. Quyền theo role: EXECUTE, quyền dữ liệu và BOOSTED

Với **Neo4j Enterprise Edition**, các câu lệnh quản trị có thể quy định **role nào được gọi procedure/function**. Ví dụ một service chỉ cần chuẩn hóa chuỗi và tra cứu trợ giúp:

~~~cypher
// Chạy trong database system bằng tài khoản quản trị.
CREATE ROLE apoc_text_reader IF NOT EXISTS;

GRANT EXECUTE FUNCTION apoc.text.clean
ON DBMS TO apoc_text_reader;

GRANT EXECUTE FUNCTION apoc.version
ON DBMS TO apoc_text_reader;

GRANT EXECUTE PROCEDURE apoc.help
ON DBMS TO apoc_text_reader;
~~~

Các câu lệnh trên là **quản trị role**, không tạo dữ liệu graph và không tự gán role cho user. Sau khi kiểm tra người dùng ứng dụng thật, quản trị viên mới gán role đó cho tài khoản tương ứng theo quy trình của tổ chức.

**Một số lưu ý để diễn giải đúng:**

- **EXECUTE PROCEDURE** cho phép gọi thủ tục; **EXECUTE FUNCTION** cho phép gọi user-defined function. Hai quyền này không thể tráo cho nhau.
- Một procedure đọc graph vẫn chịu các quyền **TRAVERSE/READ** phù hợp; procedure ghi graph phải có quyền ghi tương ứng, trừ trường hợp chủ động cấp **BOOSTED**.
- **GRANT** ví dụ không tự “thu hồi” những quyền rộng mà user đã được cấp qua role khác. Phải kiểm tra **quyền hiệu lực** của tất cả role và các lệnh **DENY** hiện có.
- **GRANT EXECUTE BOOSTED PROCEDURE** là quyền nâng cao **riêng**, có thể cho thao tác bên trong procedure vượt quyền dữ liệu bình thường của user; chỉ cấp khi có thiết kế và phê duyệt đặc biệt.
- Theo tài liệu Neo4j hiện đại, để **BOOSTED** thực sự được sử dụng, user cần cả quyền **EXECUTE PROCEDURE** và quyền **EXECUTE BOOSTED PROCEDURE** tương ứng. Không dùng BOOSTED như bước “fix permission” đầu tiên.
- Khả năng quản lý role/privilege chi tiết thuộc **Enterprise**; không sao chép nguyên các lệnh này sang Community Edition hoặc Aura rồi giả định hành vi y hệt. Xem cơ chế bảo mật và giới hạn của môi trường đang dùng.

### 7.1. Kiểm tra quyền thực thi dưới tài khoản ứng dụng

Đăng nhập bằng **chính tài khoản ứng dụng** hoặc tài khoản có quyền kiểm tra tương ứng:

~~~cypher
SHOW PROCEDURES EXECUTABLE BY CURRENT USER
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS EXECUTABLE BY CURRENT USER
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

Hai truy vấn này giúp phân biệt **function/procedure được nạp** và **function/procedure user hiện tại được phép thực thi**. Một tài khoản quản trị có thể thấy nhiều chức năng hơn tài khoản API.

**SHOW PROCEDURES** không thay được bước kiểm tra **quyền graph**. Procedure có thể hiển thị là executable nhưng truy vấn vẫn thất bại khi cố sửa node, truy cập file hoặc kết nối mạng mà user/instance không được phép.

### 7.2. Minh họa nguyên tắc tối thiểu quyền

| Tài khoản | Nhu cầu | Hướng cấp quyền |
|---|---|---|
| **api_reader** | Tìm graph và gọi một số hàm chuyển chuỗi | Graph TRAVERSE/READ phù hợp + EXECUTE FUNCTION tên cụ thể |
| **import_worker** | Nhập dữ liệu đã xác thực | Quyền WRITE có phạm vi thích hợp; chỉ procedure import được chấp thuận nếu thực sự cần |
| **db_maintainer** | Cập nhật cấu hình, plugin, theo dõi lỗi | Quyền vận hành tương ứng, không dùng làm tài khoản API |
| **auditor** | Đánh giá danh sách chức năng và quyền | Quyền xem cấu hình/role phù hợp, không mặc định cấp WRITE |

Không đưa một tài khoản quản trị toàn quyền vào code Java Driver hoặc Spring Data Neo4j chỉ để tránh việc cấp các quyền hẹp. Mỗi ứng dụng nên kết nối bằng tài khoản riêng có quyền vừa đủ.

## 8. apoc.conf: giới hạn file, export và tính năng ngoài database

Từ **APOC 5**, các cấu hình bắt đầu bằng **apoc.** cần đặt trong **$NEO4J_HOME/conf/apoc.conf** hoặc bằng biến môi trường phù hợp. **Không đặt apoc.* trong neo4j.conf** như các tài liệu APOC phiên bản cũ; với strict validation, cấu hình sai có thể làm Neo4j không khởi động, hoặc bị bỏ qua.

Ví dụ **apoc.conf** an toàn cho môi trường **không cần đọc/ghi file cục bộ qua APOC**:

~~~properties
apoc.import.file.enabled=false
apoc.export.file.enabled=false
~~~

Đây là hai cơ chế **khác** với **allowlist**:

| Điều khiển | Tệp | Mục đích |
|---|---|---|
| **dbms.security.procedures.allowlist** | **neo4j.conf** | Procedure/function nào được nạp |
| **dbms.security.procedures.unrestricted** | **neo4j.conf** | Procedure/function nào được bỏ hạn chế API nội bộ |
| **apoc.import.file.enabled** | **apoc.conf** | Cho phép tính năng APOC đọc file cục bộ |
| **apoc.export.file.enabled** | **apoc.conf** | Cho phép tính năng APOC xuất dữ liệu ra file cục bộ |
| **apoc.import.file.use_neo4j_config** | **apoc.conf** | Khi bật, việc truy cập file dựa vào cấu hình Neo4j về import directory/quyền đọc file |

Theo tài liệu hiện hành, **apoc.import.file.enabled** và **apoc.export.file.enabled** mặc định là **false**. Nếu phải cho phép một tác vụ import/export file:

1. Xác định procedure cụ thể cần chạy, nguồn hoặc đích file, user thực thi và quyền dữ liệu.
2. Chỉ nạp procedure cần thiết vào allowlist; không mở cả namespace APOC nếu không cần.
3. Cân nhắc bật đúng **một** chức năng import/export trong **apoc.conf**.
4. Giữ cơ chế giới hạn file theo **server.directories.import** và cấu hình liên quan khi thích hợp.
5. Cấp quyền thực thi/ghi graph cho đúng vai trò; giám sát request, quyền OS và thư mục chứa file.

**Không hiểu apoc.import.file.enabled=false là “mọi truy cập mạng đã bị chặn”.** Nó liên quan đến **đọc file cục bộ** bằng tính năng APOC tương ứng. Việc gọi HTTP/HTTPS, cloud storage hay đọc URI ngoài cần chính sách cho procedure, xác thực, quyền mạng, egress/firewall và các cấu hình riêng. Đồng thời, việc bật import file ở **apoc.conf** không tự mở tất cả quyền hệ điều hành của tiến trình Neo4j.

### 8.1. Nguyên tắc bảo vệ nguồn ngoài

Procedure có khả năng tải URL hoặc chạy câu Cypher động cần được đánh giá kỹ hơn hàm xử lý chuỗi thuần túy. Với mọi nguồn do client chỉ định:

- Chỉ dùng nguồn tin cậy, kiểm soát domain/địa chỉ được phép ở tầng ứng dụng và hạ tầng.
- Không truyền URL, thông tin xác thực hoặc câu lệnh tùy ý từ user vào các procedure nhạy cảm mà không có validation.
- Không bật quyền unrestricted hàng loạt để giải quyết lỗi truy cập file hoặc HTTP.
- Đảm bảo container/server không có quyền đọc file bí mật ngoài phạm vi làm việc được cấp.
- Tránh bật tính năng **export** nếu tài khoản không có nhu cầu xuất dữ liệu.

**APOC không thay thế phân quyền dữ liệu của Neo4j**; khi có procedure nội bộ mạnh hoặc quyền BOOSTED, biên bảo mật càng cần được kiểm chứng bằng thử nghiệm âm tính (đảm bảo yêu cầu bị cấm thật sự thất bại).

## 9. Quy trình triển khai cấu hình có thể kiểm chứng

### 9.1. Xác định danh sách tối thiểu

Trước khi sửa cấu hình, thống kê những chỗ ứng dụng đang gọi **CALL apoc....** và **apoc....(...)** từ code hoặc truy vấn đã phê duyệt; ghi lại:

- Tên đầy đủ và kiểu **procedure/function**.
- Gói **Core/Extended**, phiên bản yêu cầu, dependency bổ sung.
- Có thực sự cần **unrestricted** hay không theo tài liệu procedure.
- Role nào cần gọi, quyền READ/WRITE và quyền tài nguyên bên ngoài nào liên quan.
- Có cú pháp Cypher thuần phù hợp hơn để giảm phụ thuộc APOC không.

Ví dụ workload của bài chỉ cần **apoc.text.clean**, **apoc.version** và **apoc.help**. Chúng không cần được mở rộng thành **apoc.\***.

### 9.2. Thay đổi và khởi động lại

1. Sao lưu cấu hình và ghi nhận phiên bản Neo4j/JAR hiện có theo quy trình vận hành.
2. Đưa đúng JAR đã kiểm tra vào **plugins**, kiểm tra quyền file.
3. Đặt **allowlist** tối thiểu và chỉ đặt **unrestricted** nếu chức năng được duyệt yêu cầu.
4. Tạo **apoc.conf** với các tùy chọn file/network cần thiết; không trộn nhầm vị trí cấu hình.
5. Áp dụng đồng bộ ở những server cần thiết; restart có kiểm soát.
6. Chạy **SHOW PROCEDURES**, **SHOW FUNCTIONS** và các truy vấn thử với user quản trị lẫn user ứng dụng.
7. Quan sát log khởi động, hiệu năng truy vấn và phản hồi lỗi; sẵn sàng hoàn tác cấu hình/JAR nếu chức năng bắt buộc không nạp được.

### 9.3. Kiểm thử cả trường hợp được phép và bị từ chối

| Phép kiểm tra | Kỳ vọng |
|---|---|
| Admin gọi **apoc.version()** và **apoc.text.clean(...)** | Thành công khi Core đã nạp và allowlist chứa hai tên |
| User có EXECUTE FUNCTION tương ứng gọi **apoc.text.clean(...)** | Thành công nếu quyền hiệu lực cho phép |
| Một function APOC không có trong allowlist | Không hiện trong danh mục được nạp |
| User bị từ chối EXECUTE procedure nhạy cảm | Bị từ chối ngay cả khi procedure được nạp |
| Procedure cần file khi **apoc.import.file.enabled=false** | Thao tác đọc file cục bộ qua APOC liên quan không được cho phép |
| Procedure có truy cập nội bộ nhưng không được unrestricted | Không được tự động dùng đầy đủ API nội bộ |

Đối với bài thực hành, có thể quan sát danh mục đã nạp mà không cần cố gọi một procedure nguy hiểm. Trong môi trường kiểm thử riêng, quản trị viên có thể thêm các bài kiểm tra quyền âm tính với một role hạn chế.

## 10. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **Unknown procedure/function** | Chưa cài plugin, sai bản JAR, chưa restart, thiếu tên trong allowlist | Xem plugins, version, startup log và SHOW PROCEDURES/FUNCTIONS |
| Một số APOC hoạt động, một số không | Core/Extended khác nhau, allowlist chỉ gồm một phần, chức năng deprecated | Kiểm tra package/phiên bản và danh mục chức năng thực sự nạp |
| **Unauthorized** hoặc **permission denied** | Role thiếu EXECUTE/READ/WRITE hoặc chịu DENY | SHOW ... EXECUTABLE BY CURRENT USER; xem quyền hiệu lực |
| Lỗi liên quan **restricted procedure** | Procedure cần API nội bộ nhưng chưa được unrestrict | Đọc trang procedure; chỉ mở đúng tên đã duyệt |
| Lỗi **Import from files not enabled** | **apoc.import.file.enabled** chưa bật | Kiểm tra **apoc.conf** và yêu cầu nghiệp vụ |
| Không đọc được đường dẫn file | Vị trí file là phía server, import directory/OS permission khác mong đợi | Kiểm tra đường dẫn thực tế, quyền và cấu hình directory |
| Lỗi truy cập URL | Không có route DNS/network/egress, xác thực hoặc nguồn không hợp lệ | Kiểm tra cấu hình mạng và chính sách URL |
| Server không khởi động sau đổi config | Đặt **apoc.*** sai vào neo4j.conf, JAR không tương thích, thiếu dependency | Đối chiếu log, tệp cấu hình và ma trận phiên bản |
| Desktop chạy được nhưng Aura lỗi | Aura chỉ cung cấp một tập APOC Core được hỗ trợ | Tra tài liệu Aura APOC support và đổi sang chức năng sẵn có |
| Test chạy được bằng admin nhưng API lỗi | Tài khoản Java Driver/Spring Data Neo4j ít quyền hơn admin | Thử bằng đúng tài khoản API, kiểm tra role và quyền dữ liệu |

### 10.1. Tách bốn nhóm lỗi trước khi sửa

**Không tìm thấy tên** thường là vấn đề **cài đặt/allowlist/phiên bản**. **Tìm thấy nhưng không được gọi** là vấn đề **quyền thực thi**. **Gọi được nhưng thiếu quyền graph hoặc file** là vấn đề **quyền tài nguyên**. **Plugin có mặt nhưng không khởi động được** thường phải điều tra **JAR, dependency hoặc cấu hình**. Tách rõ các nhóm này sẽ tránh giải pháp dễ gây rủi ro như bật **unrestricted=apoc.\*** cho mọi lỗi.

## 11. Bài tập và tình huống thực hành

### Bài 1 — Phân loại quyền

Cho cấu hình:

~~~properties
dbms.security.procedures.allowlist=apoc.text.clean,apoc.version,apoc.help
~~~

Hãy giải thích:

1. Vì sao **apoc.text.clean** có thể xuất hiện trong **SHOW FUNCTIONS**, nhưng **apoc.help** xuất hiện trong **SHOW PROCEDURES**?
2. Một tài khoản không có quyền EXECUTE FUNCTION tương ứng có chắc gọi được **apoc.text.clean** hay không?
3. Vì sao thêm **apoc.load.json** vào **unrestricted** mà không vào **allowlist** vẫn chưa đủ để gọi nó?

### Bài 2 — Bài toán role tối thiểu

Ứng dụng chỉ cần chuẩn hóa tên sản phẩm bằng **apoc.text.clean**, không cần truy cập file hay mạng qua APOC. Thiết kế cấu hình **neo4j.conf**, **apoc.conf** và quyền EXECUTE tối thiểu. Đề xuất truy vấn kiểm tra cả vai trò admin lẫn tài khoản API.

### Bài 3 — Sửa cấu hình sai

Một nhóm vận hành dùng:

~~~properties
dbms.security.procedures.allowlist=apoc.*
dbms.security.procedures.unrestricted=apoc.*
~~~

Họ chỉ thực sự cần một procedure đọc JSON từ HTTPS. Hãy nêu rủi ro cấp quyền quá rộng và đề xuất cách lập **allowlist theo tên**, điều tra có cần **unrestricted** hay không, quản lý **HTTP egress**, xác thực và quyền đọc dữ liệu. Không bật mở rộng API nội bộ theo cả package khi chưa được kiểm chứng.

### Bài 4 — Nhập liệu trên Aura

Một ứng dụng viết cho Neo4j tự quản lý yêu cầu APOC Extended nhưng chuyển sang **Aura**. Hãy trình bày cách kiểm tra danh sách APOC được hỗ trợ, tìm chức năng thay bằng Cypher hoặc đổi thiết kế ETL qua ứng dụng Java Driver/Spring Data Neo4j khi procedure Extended không khả dụng.

### Bài 5 — Đọc triệu chứng lỗi

Sau khi deploy, admin chạy được **apoc.version()** nhưng user ứng dụng bị từ chối **CALL apoc.help('text')**. Xác định vì sao thử nghiệm này chưa chứng minh JAR hỏng. Liệt kê lệnh **SHOW PROCEDURES**, **SHOW PROCEDURES EXECUTABLE BY CURRENT USER** và quyền cần kiểm tra.

## 12. Ghi nhớ

Để dùng APOC an toàn trong Neo4j, cần phân biệt **cài JAR**, **nạp bằng allowlist**, **bỏ hạn chế API nội bộ bằng unrestricted**, **cấp quyền EXECUTE theo role** và **quyền graph/file/network khi thực thi**. Đây là những lớp độc lập, cùng quyết định một procedure có hoạt động hay không và hoạt động trong phạm vi nào.

Trong production, ưu tiên **Cypher tích hợp hoặc APOC Core khi đủ nhu cầu**, khớp phiên bản plugin với server, chỉ nạp tên được phê duyệt và để **unrestricted** ở trạng thái tối thiểu. Đặt **dbms.security.procedures.*** trong **neo4j.conf**, đặt tùy chọn **apoc.*** trong **apoc.conf** từ APOC 5, rồi kiểm chứng trên **tài khoản ứng dụng thật**, không chỉ tài khoản quản trị.

### Tài liệu chính thức

- [Neo4j APOC Core – Installation](https://neo4j.com/docs/apoc/current/installation/)
- [Neo4j APOC Core – Configuration Options](https://neo4j.com/docs/apoc/current/config/)
- [Neo4j APOC Core – Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/)
- [Neo4j Operations Manual – Securing extensions](https://neo4j.com/docs/operations-manual/current/security/securing-extensions/)
- [Neo4j Operations Manual – Configure plugins](https://neo4j.com/docs/operations-manual/current/configuration/plugins/)
- [Neo4j Operations Manual – Procedure and user-defined function privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/)
- [Neo4j Operations Manual – Docker plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/)
- [Neo4j APOC Extended – Installation](https://neo4j.com/labs/apoc/5/installation/)
- [Neo4j Aura – APOC support](https://neo4j.com/docs/aura/apoc/)
