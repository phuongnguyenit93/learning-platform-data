# Cân đối tốc độ đọc với chi phí ghi, dung lượng và bảo trì chỉ mục

Trong Neo4j, chỉ mục (*index*) giúp Cypher tìm node và relationship nhanh hơn mà không phải duyệt toàn bộ đồ thị. Nhưng mỗi chỉ mục cũng là một cấu trúc dữ liệu cần lưu trữ, duy trì và theo dõi. Với hệ thống **DATABASE_ENGINE_GRAPH_NEO4J**, bài toán không phải “tạo càng nhiều index càng tốt”, mà là lựa chọn index giúp các truy vấn quan trọng đạt hiệu năng cần thiết với chi phí ghi, dung lượng và vận hành chấp nhận được.

Chương **Chỉ mục tra cứu** tập trung vào **token lookup index**, tức chỉ mục tra cứu **nhãn của node** và **loại của relationship**. Để cân đối các chi phí chính xác, cần phân biệt chúng với **property index** như range, text và point, vốn giải quyết điều kiện trên giá trị thuộc tính.

## 1. Lookup index hỗ trợ truy vấn nào?

Property graph trong Neo4j gồm node, relationship và thuộc tính. Trong hệ thống bán hàng, có thể có các node **Customer**, **Product**, **Order** và quan hệ **PURCHASED**, **VIEWED**. Khi chạy:

~~~cypher
MATCH (c:Customer)
RETURN c
LIMIT 20;
~~~

Neo4j cần tìm node mang nhãn **Customer**. **Node label lookup index** có thể giúp truy cập tập node này. Tương tự:

~~~cypher
MATCH ()-[r:PURCHASED]->()
RETURN r
LIMIT 20;
~~~

**Relationship type lookup index** có thể giúp tra cứu các quan hệ loại **PURCHASED**. Bộ lập kế hoạch truy vấn (*query planner*) sẽ chọn dùng chỉ mục hoặc chiến lược truy cập khác tùy truy vấn, dữ liệu, thống kê và phiên bản.

| Đặc tính | Node label lookup | Relationship type lookup |
|---|---|---|
| Ánh xạ | Nhãn → các node mang nhãn | Loại → các relationship thuộc loại |
| Điều kiện hỗ trợ | **MATCH (n:Customer)** | **MATCH ()-[r:PURCHASED]->()** |
| Không giải quyết trực tiếp | **n.email = $email**, **n.age > 18** | **r.amount > 100**, **r.createdAt > $t** |
| Phạm vi | Toàn bộ nhãn trong database | Toàn bộ loại relationship trong database |
| Số lượng tối đa | **Một** | **Một** |

Trong database Neo4j mới, **hai lookup index được tạo sẵn theo mặc định**. Chúng còn hỗ trợ quá trình *population* (xây dựng ban đầu) của những chỉ mục khác. Xóa chúng có thể gây suy giảm hiệu năng nghiêm trọng và không phải cách tối ưu ghi thường dùng.

**Giới hạn rất quan trọng:** lookup index **không phải** index trên một thuộc tính. Dù có lookup index cho nhãn Customer, truy vấn tìm Customer theo email vẫn có thể phải quét tập Customer rồi lọc email nếu không có property index thích hợp.

**Tương thích phiên bản:** database được tạo trên **Neo4j 4.3 trở lên** thường có cả hai lookup index mặc định. Database tạo trước 4.3 rồi nâng cấp có thể thiếu relationship type lookup index; cần dùng lệnh **SHOW** để xác nhận thay vì suy đoán.

## 2. Bốn mặt của quyết định lập chỉ mục

| Mặt đánh đổi | Lợi ích hoặc chi phí | Cần kiểm chứng |
|---|---|---|
| **Tốc độ đọc** | Thu hẹp tập node/relationship phải xem xét | Truy vấn p95 tốt hơn bao nhiêu? Giảm bao nhiêu DB Hits? |
| **Chi phí ghi** | Thay đổi dữ liệu liên quan làm phát sinh cập nhật index | Độ trễ ghi và thông lượng giao dịch thay đổi thế nào? |
| **Dung lượng** | Index chiếm đĩa, tạo thêm tải I/O và có thể tăng áp lực page cache | Dung lượng index, tốc độ tăng và mức I/O thực tế? |
| **Bảo trì** | Index cần được xây dựng, quan sát trạng thái, triển khai và khôi phục khi cần | Có ONLINE không? Population mất bao lâu? Có lỗi FAILED? |

Không có công thức cố định như “thêm một index khiến ghi chậm 10%”. Tác động phụ thuộc số node và relationship, kiểu ghi, số nhãn, số index trên thuộc tính, dữ liệu phân bố ra sao, truy vấn nào chạy thường xuyên, phần cứng và phiên bản Neo4j.

### 2.1. Đọc nhanh hơn phụ thuộc độ chọn lọc

Ví dụ:

~~~cypher
MATCH (c:Customer {email: $email})
RETURN c;
~~~

Nếu dữ liệu có hàng triệu Customer và email gần như duy nhất, việc chỉ tìm nhãn rồi lọc email có thể tốn nhiều công việc. Một **range index** hoặc **uniqueness constraint** phù hợp trên Customer.email cho phép planner cân nhắc truy cập trực tiếp theo giá trị thuộc tính, thường với toán tử dạng **NodeIndexSeek**. Với vài node, planner lại có thể thấy quét nhãn rẻ hơn.

**Một index chỉ có lợi khi truy vấn thực sự có đường truy cập tận dụng nó.** Truy vấn trả phần lớn database, tính tổng hợp toàn đồ thị hoặc đi theo các relationship đã biết chưa chắc nhanh lên vì có thêm property index.

### 2.2. Ghi tốn chi phí ở những nơi dữ liệu được index thay đổi

| Thao tác | Ảnh hưởng đến lookup index | Ảnh hưởng đến property index |
|---|---|---|
| Tạo node có nhãn | Bổ sung ánh xạ nhãn–node | Cập nhật các index thuộc tính áp dụng cho node |
| Thêm/bỏ nhãn của node | Cập nhật ánh xạ nhãn–node | Có thể thêm/bỏ các mục index gắn với nhãn |
| Tạo/xóa relationship | Cập nhật ánh xạ loại–relationship | Cập nhật các index thuộc tính trên relationship liên quan |
| Đổi thuộc tính **không được index**, giữ nguyên nhãn và loại | Thông thường không đổi mục lookup | Không đổi các index không liên quan |
| Đổi thuộc tính **được index** | Không cần sửa lookup chỉ vì giá trị thuộc tính đổi | Duy trì các index phụ thuộc thuộc tính ấy |

Vì vậy, một hệ thống cập nhật **lastSeenAt** liên tục không phải cập nhật token lookup index chỉ vì thuộc tính này thay đổi, nếu nhãn của node giữ nguyên. Nhưng thêm property index trên lastSeenAt có thể khiến mỗi lần cập nhật phải bảo trì thêm index đó.

Index được Neo4j tự cập nhật cùng dữ liệu, không cần ứng dụng Java Driver hay Spring Data Neo4j tự làm mới thủ công sau mỗi lần ghi. Đặc biệt với các performance index thông thường, không nên xem index như một cache bất đồng bộ độc lập với giao dịch.

### 2.3. Dung lượng và over-indexing

Lookup index là hai cấu trúc **dùng chung cho mọi nhãn và mọi loại quan hệ**, không thể tạo một lookup index riêng cho từng nhãn. Hiện tượng tạo dư index thường cần xem xét ở **property index**: nhiều index đơn lẻ trên các thuộc tính ít được lọc, index trùng ý nghĩa hoặc index được tạo vì phỏng đoán mà không có workload chứng minh.

Không thể suy ra con số byte hoặc RAM từ số lượng index một cách chính xác. Để quyết định có đáng đánh đổi hay không, cần quan sát dung lượng database/index, I/O, page cache, độ trễ và thông lượng trên dữ liệu đại diện.

## 3. Kiểm tra hiện trạng trên database

Các truy vấn đọc trạng thái có thể chạy trên hệ thống được cấp quyền xem index. Những ví dụ **CREATE** và **SET** phía sau chỉ nên chạy ở cơ sở dữ liệu thử nghiệm.

### 3.1. Liệt kê token lookup index

~~~cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
RETURN name, entityType, state, populationPercent
ORDER BY entityType;
~~~

Ý nghĩa:

- **name:** tên index; index mặc định có thể có tên tự sinh.
- **entityType:** **NODE** hoặc **RELATIONSHIP**.
- **state:** **ONLINE** khi sẵn sàng dùng; **POPULATING** khi đang xây dựng; **FAILED** nếu xây dựng thất bại.
- **populationPercent:** tiến độ tạo index, **không phải** phần trăm truy vấn dùng index.

Để phân biệt các loại index và phát hiện index thuộc constraint:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, state, owningConstraint
RETURN name, type, entityType, state, owningConstraint
ORDER BY type, name;
~~~

**type = LOOKUP** là token lookup index; **RANGE**, **TEXT**, **POINT** là các loại performance index dùng cho thuộc tính; **FULLTEXT** và **VECTOR** phục vụ các bài toán tìm kiếm chuyên biệt. Nếu **owningConstraint** có giá trị, cần xét constraint quản lý index trước khi thay đổi schema.

**ONLINE** không có nghĩa planner đang dùng index ở truy vấn quan trọng; để kết luận cần xem kế hoạch truy vấn thực tế.

### 3.2. Đọc EXPLAIN và PROFILE

~~~cypher
EXPLAIN
MATCH (c:Customer)
WHERE c.region = $region
RETURN c.customerId
LIMIT 20;
~~~

**EXPLAIN** lập kế hoạch mà **không thực thi**. Khi truy vấn chạy thực tế:

~~~cypher
PROFILE
MATCH (c:Customer)
WHERE c.region = $region
RETURN c.customerId
LIMIT 20;
~~~

**PROFILE** thực thi truy vấn và trình bày số hàng, **DB Hits** cùng các toán tử trong kế hoạch. Các toán tử có thể gặp là **NodeByLabelScan**, **NodeIndexSeek**, **NodeIndexScan** hoặc những toán tử khác tùy phiên bản và cách tối ưu. Nếu planner quét phần lớn node mang nhãn Customer rồi mới lọc region, có thể cần điều chỉnh đường truy cập bằng một property index phù hợp.

Lưu ý: **LIMIT 20** chỉ giới hạn số hàng trả về; hệ thống vẫn có thể phải xem xét rất nhiều ứng viên để tìm đủ 20 bản ghi thỏa điều kiện.

## 4. Ví dụ tự chạy: khi nào lookup là đủ, khi nào chưa đủ?

Chạy **một lần trên database dùng cho thử nghiệm**, vì lệnh tạo dữ liệu bên dưới sẽ tạo bản sao nếu thực thi lại:

~~~cypher
CREATE
  (c1:DemoLookupCustomer {code: 'DL-001', region: 'north'}),
  (c2:DemoLookupCustomer {code: 'DL-002', region: 'south'}),
  (c3:DemoLookupCustomer {code: 'DL-003', region: 'north'}),
  (p1:DemoLookupProduct {sku: 'DL-P-001'}),
  (c1)-[:DEMO_VIEWED]->(p1),
  (c2)-[:DEMO_VIEWED]->(p1);
~~~

### 4.1. Truy vấn theo nhãn hoặc loại

~~~cypher
EXPLAIN
MATCH (c:DemoLookupCustomer)
RETURN c.code, c.region;
~~~

~~~cypher
EXPLAIN
MATCH ()-[r:DEMO_VIEWED]->()
RETURN r;
~~~

Trong database có hai lookup index mặc định, planner có đường truy cập theo **nhãn node** và **loại relationship**. Với ví dụ rất nhỏ, kết quả EXPLAIN chủ yếu giúp học viên đọc kế hoạch; **không dùng thời gian của ba node để kết luận hiệu năng sản xuất**.

### 4.2. Lọc theo thuộc tính

~~~cypher
PROFILE
MATCH (c:DemoLookupCustomer)
WHERE c.code = 'DL-001'
RETURN c.code, c.region;
~~~

**code** là thuộc tính, không phải nhãn. Nếu truy vấn tương tự xuất hiện thường xuyên trên tập dữ liệu lớn và có độ chọn lọc cao, cân nhắc thêm range index:

~~~cypher
CREATE RANGE INDEX ix_demo_lookup_customer_code IF NOT EXISTS
FOR (c:DemoLookupCustomer) ON (c.code);
~~~

Theo dõi trạng thái:

~~~cypher
SHOW RANGE INDEXES
YIELD name, state, populationPercent
WHERE name = 'ix_demo_lookup_customer_code'
RETURN name, state, populationPercent;
~~~

Sau khi index ở trạng thái **ONLINE**, chạy lại truy vấn PROFILE để so sánh. Planner **có thể vẫn chọn quét nhãn** trên dataset quá nhỏ; đây là quyết định hợp lý nếu quét rẻ hơn truy cập index.

Nếu **code** là mã định danh phải duy nhất, một **uniqueness constraint** phù hợp có thể tốt hơn index đơn lẻ vì vừa bảo đảm tính toàn vẹn vừa tạo index hỗ trợ tra cứu. Kiểm tra các constraint đã tồn tại để tránh tạo cấu hình trùng lặp.

### 4.3. Thay đổi thuộc tính khác với thay đổi nhãn

~~~cypher
MATCH (c:DemoLookupCustomer {code: 'DL-001'})
SET c.region = 'central'
RETURN c.code, c.region;
~~~

Lệnh này không đổi nhãn của node: lookup index không phải cập nhật ánh xạ nhãn chỉ vì giá trị region đổi. Nếu có một **property index trên region**, hệ thống lại cần duy trì index đó.

~~~cypher
MATCH (c:DemoLookupCustomer {code: 'DL-001'})
SET c:DemoLookupPriority
RETURN labels(c) AS labels;
~~~

Thao tác **SET c:DemoLookupPriority** thay đổi tập nhãn và vì vậy liên quan đến **node label lookup index**. Nếu mô hình dữ liệu thay đổi nhãn liên tục để biểu diễn trạng thái ngắn hạn, hãy cân nhắc cả chi phí cập nhật nhãn và ý nghĩa truy vấn trước khi quyết định dùng nhãn hay thuộc tính.

## 5. Bảo vệ lookup index mặc định và quản lý property index

Do chỉ có tối đa **một lookup index node** và **một lookup index relationship** trong database, không thể tạo thêm index lookup độc lập để “tối ưu riêng” từng loại node. Việc xóa lookup index có thể ảnh hưởng nghiêm trọng đến hiệu năng truy vấn và thời gian population index khác. Đó là một thay đổi nền tảng, chỉ nên được đánh giá trong tình huống vận hành đặc biệt với dữ liệu và phép đo rõ ràng.

Nếu index lookup bị thiếu, cú pháp khôi phục là:

~~~cypher
CREATE LOOKUP INDEX node_label_lookup IF NOT EXISTS
FOR (n) ON EACH labels(n);
~~~

~~~cypher
CREATE LOOKUP INDEX relationship_type_lookup IF NOT EXISTS
FOR ()-[r]-() ON EACH type(r);
~~~

Nếu đã có index tương đương, **IF NOT EXISTS** làm lệnh không tạo thêm index và có thể trả thông báo. Token lookup index **không có OPTIONS cấu hình được hỗ trợ**.

Với database lớn thiếu relationship type lookup index do nguồn gốc trước 4.3, việc xây dựng lại có thể phải quét rất nhiều relationship. Hãy lên kế hoạch về tải I/O, thời gian population và theo dõi trạng thái đến khi **ONLINE**.

Đối với **property index** thực sự dư thừa, nên đánh giá: index có phục vụ truy vấn hiếm nhưng quan trọng không? Nó có do constraint sở hữu không? Nếu bỏ đi, kế hoạch **PROFILE** và p95 truy vấn sẽ thay đổi ra sao? Có phương án hoàn tác schema an toàn không? Không xóa index chỉ dựa vào việc không thấy lượt đọc trong một khoảng quan sát ngắn.

## 6. Chọn chiến lược theo mẫu sử dụng

| Workload | Chiến lược xem xét | Nguyên nhân |
|---|---|---|
| Truy vấn thường xuyên theo node label, relationship type | Giữ hai lookup index | Chúng là đường truy cập chung cho nhãn và loại |
| Tra cứu một Customer theo email/mã | Range index hoặc uniqueness constraint phù hợp | Lookup index không hỗ trợ bộ lọc giá trị thuộc tính |
| Ghi nhiều lần vào thuộc tính thay đổi liên tục | Chỉ index thuộc tính khi lợi ích đọc đủ lớn | Tránh bảo trì index cho mỗi lần thay đổi không cần thiết |
| Nạp hàng loạt node và relationship | Đo tốc độ nạp cùng chi phí index; lập kế hoạch population property index | Index cần được cập nhật khi ghi; tạo index sau nạp cũng có chi phí và thời gian |
| Lọc theo nhiều thuộc tính cùng lúc | Kiểm chứng composite range index | Có thể phù hợp hơn một số index đơn lẻ nhưng phải xét mẫu predicate thực tế |
| Database tăng nhanh và áp lực dung lượng | Đo index nào có ích trên workload, ưu tiên rà soát property index | Không hy sinh hai lookup index nền tảng một cách tùy tiện |
| Thuộc tính yêu cầu duy nhất | Dùng uniqueness constraint khi thích hợp | Bảo đảm dữ liệu và có index hỗ trợ bên dưới |

### Ví dụ dễ quyết định sai

Ứng dụng ghi nhận hoạt động của người dùng:

~~~cypher
MATCH (u:User {id: $userId})
SET u.lastSeenAt = datetime();
~~~

Nếu hệ thống hiếm khi lọc theo **lastSeenAt**, tạo một property index cho thuộc tính này có thể làm tăng cập nhật index mà không cải thiện đáng kể truy vấn quan trọng. Việc tìm User theo **id** mới cần đường truy cập thuộc tính thích hợp. Ngược lại, nếu truy vấn “người dùng hoạt động trong 5 phút gần đây” chạy liên tục và có SLO chặt chẽ, index thời gian có thể đem lại lợi ích đáng kể. Quyết định phải dựa trên đo đạc.

## 7. Đo đạc thay vì đoán hiệu năng

Để đánh giá một **property index dự kiến bổ sung hoặc loại bỏ**, giữ lookup index mặc định ở cả hai cấu hình thử nghiệm và so sánh trong điều kiện gần giống nhau.

**Bước 1 – Chọn workload đại diện.** Thu thập những truy vấn đọc/ghi quan trọng, phân bố tham số, độ chọn lọc, lượng node/relationship và tỷ lệ giao dịch đọc/ghi. Truy vấn ít chạy nhưng rất quan trọng với nghiệp vụ vẫn phải được tính đến.

**Bước 2 – Đo mốc ban đầu.** Ghi p50/p95 truy vấn đọc, **DB Hits**, số hàng và toán tử từ **PROFILE**; với ghi, ghi p95 transaction, số transaction/giây, CPU, I/O; với dung lượng, ghi không gian index và ảnh hưởng page cache.

**Bước 3 – Thay đổi một quyết định index.** Thực thi thay đổi trong môi trường đại diện, chờ index chuyển sang **ONLINE**, chạy lại workload với cùng bộ tham số, dữ liệu, phần cứng và tải tương đương. Chạy đủ lượt làm nóng trước khi so sánh.

**Bước 4 – So sánh cả mặt lợi và hại.** Nếu p95 đọc giảm nhưng p95 ghi vượt SLO hoặc dung lượng tăng quá ngân sách, index đó chưa chắc đáng giữ. Quyết định cần phản ánh tổng tác động, không chỉ một con số latency đẹp.

| Chỉ số | Trước thay đổi | Sau thay đổi | Điều kiện chấp nhận |
|---|---|---|---|
| p95 truy vấn đọc quan trọng | Đo thực tế | Đo thực tế | Đạt SLO đọc |
| **PROFILE** / DB Hits | Ghi lại | Ghi lại | Giảm đọc không cần thiết |
| p95 transaction ghi | Đo thực tế | Đo thực tế | Không vượt SLO ghi |
| Thông lượng transaction/giây | Đo thực tế | Đo thực tế | Đủ tải giờ cao điểm |
| Dung lượng, I/O và page cache | Đo thực tế | Đo thực tế | Trong ngân sách tài nguyên |
| **SHOW INDEXES** | Ghi lại | Ghi lại | Index cần thiết ở ONLINE |

Bảng trên là **mẫu biên bản thí nghiệm**, không phải số đo hiệu năng được bảo đảm bởi Neo4j.

## 8. Vận hành và bảo trì

### 8.1. Vòng đời index

- **POPULATING:** đang xây dựng. Chưa thể coi index đã sẵn sàng phục vụ truy vấn bình thường.
- **ONLINE:** index đã sẵn sàng để planner xem xét sử dụng khi điều kiện phù hợp.
- **FAILED:** cần tìm nguyên nhân trong trạng thái/thông báo lỗi và nhật ký vận hành, rồi có phương án khắc phục phù hợp.

Chạy **SHOW INDEXES** định kỳ theo quy trình giám sát. Để quản lý index cần các quyền thích hợp, ví dụ **SHOW INDEX** khi đọc trạng thái và quyền tạo/xóa schema khi thay đổi. Không mặc định tạo hoặc xóa schema vào mỗi lần khởi động ứng dụng mà thiếu kiểm soát triển khai.

### 8.2. Các ngộ nhận thường gặp

1. **“Index nào cũng tốt cho đọc”** – Không; một truy vấn phải có đường truy cập hưởng lợi từ index và đủ chọn lọc.
2. **“Lookup index giúp tra cứu nhanh email”** – Không; lookup chỉ giải quyết nhãn node và loại relationship.
3. **“Mỗi nhãn cần một lookup index”** – Không; một node label lookup index dùng chung tất cả nhãn.
4. **“Index ONLINE nghĩa là đang được dùng”** – Không; cần kiểm tra **EXPLAIN** hoặc **PROFILE**.
5. **“Sửa thuộc tính nào cũng ghi lại lookup index”** – Không; chỉ thay đổi thuộc tính không đồng nghĩa thay đổi nhãn/loại quan hệ.
6. **“Xóa hai lookup index để tối ưu ghi”** – Rủi ro cao do tác động đến nhiều truy vấn và xây dựng index khác.
7. **“Property index không được đọc trong một tuần chắc chắn vô dụng”** – Chưa đủ; phải xét truy vấn định kỳ, truy vấn sự cố và index thuộc constraint.

### 8.3. Danh sách kiểm tra trước khi đổi schema

- Xác định truy vấn trọng tâm, độ chọn lọc và SLO cần đạt.
- Xem **SHOW INDEXES** để phân loại lookup, property và index được constraint quản lý.
- Ghi lại kế hoạch **EXPLAIN/PROFILE** cùng số liệu đọc/ghi ban đầu.
- Đánh giá dung lượng, I/O, chi phí population và tác động ghi trên dữ liệu đại diện.
- Có cửa sổ triển khai, cách xác nhận **ONLINE** và kế hoạch hoàn tác thích hợp.
- Theo dõi số liệu sau thay đổi để phát hiện hồi quy.

## 9. Bài tập thực hành

**Bài 1 – Nhận dạng index.** Cho ba truy vấn:

~~~cypher
MATCH (n:Customer) RETURN n LIMIT 10;

MATCH ()-[r:PURCHASED]->() RETURN r LIMIT 10;

MATCH (n:Customer {email: $email}) RETURN n;
~~~

Hãy xác định lookup index nào có thể hỗ trợ hai truy vấn đầu, vì sao truy vấn cuối có thể cần thêm property index hoặc constraint.

**Bài 2 – Cân đối chi phí.** Một ứng dụng tạo 20 triệu quan hệ sự kiện mỗi ngày nhưng chỉ vài báo cáo lọc theo **eventTime**. Nêu các phép đo cần có trước khi bổ sung property index cho eventTime. Có nên xóa relationship type lookup index để giảm chi phí ghi không?

**Bài 3 – Đọc kế hoạch.** Trên dữ liệu thử nghiệm của mục 4, chạy **PROFILE** trước và sau khi tạo range index cho **DemoLookupCustomer.code**. Giải thích vì sao kết quả trên ba khách hàng chưa thể đại diện cho 10 triệu khách hàng.

**Bài 4 – Theo dõi population.** Một index mới ở trạng thái **POPULATING** và **populationPercent = 35**. Vì sao chưa được kết luận index đã làm truy vấn nhanh hơn? Cần chờ và kiểm tra gì?

## Kết luận

**Token lookup index** là nền tảng để Neo4j tìm node theo **nhãn** và relationship theo **loại**; đa số database hiện đại đã có đủ hai index mặc định. Việc tối ưu cân bằng đọc–ghi–dung lượng thường bắt đầu bằng cách **giữ lookup index nền tảng**, sau đó đánh giá thật kỹ từng **property index** hoặc **constraint** theo truy vấn và tải thực tế. Mọi quyết định cần kiểm tra bằng **EXPLAIN/PROFILE**, trạng thái **SHOW INDEXES** và phép đo trước/sau trên cả đọc lẫn ghi.

### Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual – Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/)
- [Neo4j Cypher Manual – Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual – Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Cypher Manual – The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
- [Neo4j Operations Manual – Index configuration](https://neo4j.com/docs/operations-manual/current/performance/index-configuration/)
